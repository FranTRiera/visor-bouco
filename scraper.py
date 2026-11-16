"""Descarga los anuncios del BOUCO (Boletín Oficial de la Universidad de Córdoba)
y genera data/bouco-data.js para el visor index.html.

Uso:
    python scraper.py            # actualización incremental (solo lo nuevo)
    python scraper.py --full     # recorre todo el histórico (≈40 min)

Solo usa la librería estándar de Python.
"""
import argparse
import html
import http.cookiejar
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from classify import canonicalize_areas, enrich

BASE = "https://sede.uco.es/bouco/"
ENDPOINT = BASE + "bandejaAnuncios.htm"
PERMALINK = "https://sede.uco.es/bouco/bandejaAnuncios/BOUCO/{year}/{num}"
DATA_DIR = Path(__file__).parent / "data"
JSON_PATH = DATA_DIR / "bouco.json"
JS_PATH = DATA_DIR / "bouco-data.js"
REQUEST_DELAY_S = 0.3
# La sede a veces se queda colgada varios minutos (acepta la conexión pero no responde):
# timeout corto y reintentos con espera creciente (5, 10, 20, 40, 60, 60... s) para
# aguantar unos 10 min de cuelgue antes de rendirse.
REQUEST_TIMEOUT_S = 30
MAX_RETRIES = 9
MAX_BACKOFF_S = 60
WORKERS = 4

ROW_RE = re.compile(r'rich-table-row')
NUM_RE = re.compile(r'N\.º\s*(\d{4})/(\d+)')
TITLE_RE = re.compile(r'j_id100[^>]*>(.*?)</a>', re.S)
DATE_RE = re.compile(r'<span style="font-style:italic">([^<]+)</span>')
DESC_RE = re.compile(r'width80"><table><tbody><tr><td><label>(.*?)</label>', re.S)
OPTION_RE = re.compile(r'<option value="(\d+)">([^<]+)')
LAST_PAGE_RE = re.compile(r'rich-datascr-act[^>]*>(\d+)')


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


class Session:
    """Sesión JSF/RichFaces: el estado (filtro, página) vive en el servidor."""

    def __init__(self):
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.opener.addheaders = [("User-Agent", "bouco-visor/1.0 (consulta personal)")]
        self._get(BASE)

    def _get(self, url):
        return self._open(url, None)

    def _open(self, url, data):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with self.opener.open(url, data, timeout=REQUEST_TIMEOUT_S) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            except OSError as exc:
                if attempt == MAX_RETRIES:
                    raise
                wait = min(MAX_BACKOFF_S, 5 * 2 ** (attempt - 1))
                print(f"  reintento {attempt} en {wait} s tras error: {exc}", file=sys.stderr)
                time.sleep(wait)

    def post(self, fields):
        time.sleep(REQUEST_DELAY_S)
        payload = {"AJAXREQUEST": "_viewRoot", "javax.faces.ViewState": "j_id1", **fields}
        return self._open(ENDPOINT, urllib.parse.urlencode(payload).encode())

    def select_tema(self, tema):
        return self.post({
            "j_id300": "j_id300", "j_id300:idCatItem": tema,
            "ajaxSingle": "j_id300:idCatItem", "j_id300:j_id305": "j_id300:j_id305",
        })

    def select_subtema(self, tema, subtema):
        return self.post({
            "j_id300": "j_id300", "j_id300:idCatItem": tema, "j_id300:idSubCatItem": subtema,
            "ajaxSingle": "j_id300:idSubCatItem", "j_id300:j_id312": "j_id300:j_id312",
        })

    def page(self, page):
        return self.post({
            "idBandejaAnuncios": "idBandejaAnuncios", "autoScroll": "",
            "ajaxSingle": "idBandejaAnuncios:j_id88:ds", "idBandejaAnuncios:j_id88:ds": str(page),
        })


def parse_rows(fragment):
    """Extrae los anuncios de un fragmento HTML de la bandeja."""
    rows = []
    for chunk in ROW_RE.split(fragment)[1:]:
        num, title, date = NUM_RE.search(chunk), TITLE_RE.search(chunk), DATE_RE.search(chunk)
        if not (num and title and date):
            continue
        desc = DESC_RE.search(chunk)
        year, n = num.groups()
        d, m, y = date.group(1).strip().split("/")
        rows.append({
            "id": f"{year}/{n}",
            "fecha": f"{y}-{m}-{d}",
            "titulo": clean(title.group(1)),
            "descripcion": clean(desc.group(1)) if desc else "",
            "url": PERMALINK.format(year=year, num=n),
        })
    return rows


def last_page(session):
    found = LAST_PAGE_RE.findall(session.page("last"))
    return int(found[-1]) if found else 1


def crawl(label, setup, known, full):
    """Recorre una bandeja filtrada. `setup(session)` aplica el filtro."""
    session = Session()
    setup(session)
    total = last_page(session) if full else None
    results, page = [], 1
    while True:
        rows = parse_rows(session.page(page))
        if not rows:
            break
        results.extend(rows)
        new = [r for r in rows if r["id"] not in known]
        if page % 50 == 0 or page == 1:
            print(f"[{label}] página {page}/{total or '?'} ({len(results)} anuncios)")
        if not full and not new:
            break
        if total and page >= total:
            break
        page += 1
    print(f"[{label}] terminado: {len(results)} anuncios")
    return label, results


def discover_filters():
    """Devuelve [(tema_id, tema, subtema_id, subtema)] con subtema None si no tiene."""
    session = Session()
    home = session._get(BASE)
    sel = home[home.find('id="j_id300:idCatItem"'):]
    temas = OPTION_RE.findall(sel[:sel.find("</select>")])
    filters = []
    for tema_id, tema in temas:
        # Sesión nueva por tema: si no, el servidor devuelve el selector de subtemas del tema anterior
        frag = Session().select_tema(tema_id)
        sub_sel = frag[frag.find("idSubCatItem"):]
        subs = OPTION_RE.findall(sub_sel[:sub_sel.find("</select>")]) if "idSubCatItem" in frag else []
        tema = clean(tema)
        if subs:
            filters += [(tema_id, tema, sid, clean(s)) for sid, s in subs]
        else:
            filters.append((tema_id, tema, None, None))
    return filters


def make_setup(tema_id, subtema_id):
    def setup(session):
        session.select_tema(tema_id)
        if subtema_id:
            session.select_subtema(tema_id, subtema_id)
    return setup


def strip_number(label):
    return re.sub(r"^\d+\.\s*", "", label or "")


def load_existing():
    if JSON_PATH.exists():
        return {a["id"]: a for a in json.loads(JSON_PATH.read_text(encoding="utf-8"))["anuncios"]}
    return {}


def madrid_now():
    try:
        return datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y-%m-%d %H:%M")
    except ZoneInfoNotFoundError:  # Windows sin el paquete tzdata
        return time.strftime("%Y-%m-%d %H:%M")


def to_json(payload):
    """Un anuncio por línea, para que git guarde solo los cambios."""
    rows = ",\n".join(json.dumps(a, ensure_ascii=False) for a in payload["anuncios"])
    return f'{{"actualizado": "{payload["actualizado"]}", "anuncios": [\n{rows}\n]}}\n'


def save(ads):
    DATA_DIR.mkdir(exist_ok=True)
    ordered = canonicalize_areas(sorted(ads.values(), key=lambda a: (a["fecha"], a["id"]), reverse=True))
    if JSON_PATH.exists() and json.loads(JSON_PATH.read_text(encoding="utf-8"))["anuncios"] == ordered:
        print("Sin anuncios nuevos.")
        return
    text = to_json({"actualizado": madrid_now(), "anuncios": ordered})
    JSON_PATH.write_text(text, encoding="utf-8")
    JS_PATH.write_text("window.BOUCO_DATA = " + text.rstrip() + ";\n", encoding="utf-8")
    print(f"Guardados {len(ordered)} anuncios en {JSON_PATH}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--full", action="store_true", help="recorrer todo el histórico")
    parser.add_argument("--reclasificar", action="store_true",
                        help="volver a aplicar classify.py a los datos guardados, sin descargar")
    args = parser.parse_args()

    ads = load_existing()
    if args.reclasificar:
        save({k: enrich(a) for k, a in ads.items()})
        return
    full = args.full or not ads
    known = set(ads)
    filters = discover_filters()
    print(f"{len(filters)} secciones del BOUCO. Modo {'completo' if full else 'incremental'}.")

    jobs = {f"{t}/{s or '-'}": (t, s, make_setup(tid, sid))
            for tid, t, sid, s in filters}
    jobs["todos"] = (None, None, lambda session: None)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(crawl, label, setup, known, full)
                   for label, (_, _, setup) in jobs.items()]
        results = dict(f.result() for f in futures)

    for label, rows in results.items():
        tema, subtema, _ = jobs[label]
        for row in rows:
            current = ads.get(row["id"], {})
            merged = {**current, **row}
            if tema:
                merged["tema"] = strip_number(tema)
                merged["subtema"] = strip_number(subtema)
            merged.setdefault("tema", "")
            merged.setdefault("subtema", "")
            ads[row["id"]] = enrich(merged)

    save(ads)


if __name__ == "__main__":
    main()
