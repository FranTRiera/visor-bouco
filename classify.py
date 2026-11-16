"""Clasificación por palabras clave de los anuncios del BOUCO.

Añade a cada anuncio:
  - convocatorias: tipos de convocatoria (puede haber varios)
  - fase: momento del procedimiento (convocatoria, listas, tribunal...)
  - areas: áreas de conocimiento citadas en el texto
  - departamento: departamento citado, si lo hay
"""
import re
import unicodedata


def normalize(text: str) -> str:
    """Minúsculas y sin tildes, para comparar palabras clave."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


# Orden = prioridad de aparición en la interfaz. Patrones sobre texto normalizado.
CONVOCATORIA_RULES = [
    ("Profesorado (PDI)", r"profesor|catedratic|cuerpos docentes|plazas? docentes?|ayudante doctor"
                          r"|contratado doctor|personal docente|\bpdi\b|profesorado"),
    ("Bolsas de profesor sustituto", r"bolsa.{0,40}sustitut|sustitut.{0,40}bolsa"),
    ("PTGAS / PAS", r"\bptgas\b|\bpas\b|personal tecnico, de gestion|administracion y servicios"
                    r"|escala |funcionari|personal laboral|conserjeria|concurso de traslado"),
    ("Investigación / contratos", r"investigador|investigacion|predoctoral|postdoctoral|posdoctoral"
                                  r"|ramon y cajal|juan de la cierva|\bfpu\b|\bfpi\b|tecnico de apoyo"
                                  r"|contrato.{0,30}cargo"),
    ("Becas y ayudas", r"\bbecas?\b|\bayudas?\b|subvencion"),
    ("Movilidad", r"movilidad|erasmus|intercambio"),
    ("Premios", r"\bpremios?\b"),
    ("Elecciones", r"eleccion|electoral|candidatur|\bvotacion"),
    ("Normativa", r"reglamento|normativa|estatutos|instruccion|\bnormas?\b"),
    ("Nombramientos y ceses", r"\bnombra|\bcese|\bcesa\b"),
    ("Estudios y títulos", r"\bmaster|\bgrado\b|doctorado|titulo propio|plan de estudios|matricula"
                           r"|calendario academico|precios publicos"),
]

FASE_RULES = [
    ("Corrección de errores", r"correccion de errores|correccion errores|se corrige"),
    ("Lista provisional", r"provisional"),
    ("Lista definitiva", r"definitiv"),
    ("Tribunal / comisión", r"tribunal|comision (de seleccion|evaluadora|de valoracion)|comisiones evaluadoras"),
    ("Resolución / adjudicación", r"adjudica|propuesta de (provision|contratacion|nombramiento)|resuelve|"
                                  r"resolucion (final|definitiva)|concesion"),
    ("Convocatoria", r"convoca|se aprueba la convocatoria|bases"),
]

AREA_RE = re.compile(
    r"[ÁA]rea\s+(?:de\s+)?[Cc]onocimiento\s*:?\s*(?:[Cc]onocimiento\s+)?(?:de\s+)?[\"“«]?"
    r"([A-ZÁÉÍÓÚÑ][^.;,:\"”»()\n]+?)\s*(?=[\"”».;,:(]|$|\s+(?:y\s+(?:[Cc]ódigo|[Pp]laza)|[Dd]epartamento"
    r"|resultante|perteneciente|mediante|y del [ÁA]rea|en ejecuci|por [Rr]esoluci|para |con |de la [Uu]niversidad))"
)
DEPT_RE = re.compile(
    r"Departamento\s+(?:de\s+)?[:\-]?\s*[\"“«]?([A-ZÁÉÍÓÚÑ][^.;:\"”»()\n]+?)\s*(?=[\"”»]|[.;:(]|,|$|\s+[ÁA]rea)"
)


def _matches(rules, text):
    return [label for label, pattern in rules if re.search(pattern, text)]


def _tidy(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" ,-")
    name = re.sub(r"^[ÁA]rea\s+", "", name)
    return name[:1].upper() + name[1:]


def enrich(ad: dict) -> dict:
    """Devuelve una copia del anuncio con los campos derivados."""
    raw = f"{ad.get('titulo', '')}. {ad.get('descripcion', '')}"
    text = normalize(raw)
    convocatorias = _matches(CONVOCATORIA_RULES, text) or ["Otros"]
    fases = _matches(FASE_RULES, normalize(ad.get("titulo", ""))) or _matches(FASE_RULES, text)
    areas = sorted({_tidy(m) for m in AREA_RE.findall(raw) if len(m) > 3})
    dept = DEPT_RE.search(raw)
    return {
        **ad,
        "convocatorias": convocatorias,
        "fase": fases[0] if fases else "Otro",
        "areas": areas,
        "departamento": _tidy(dept.group(1)) if dept else "",
    }


def area_key(name: str) -> str:
    """Clave para agrupar variantes de un área (mayúsculas, tildes, artículos)."""
    words = normalize(name).split()
    return " ".join(w for w in words if w not in {"de", "la", "las", "los", "el", "del"})


def canonicalize_areas(ads: list[dict]) -> list[dict]:
    """Unifica la grafía de cada área con la variante más frecuente."""
    counts: dict[str, dict[str, int]] = {}
    for ad in ads:
        for name in ad["areas"]:
            variants = counts.setdefault(area_key(name), {})
            variants[name] = variants.get(name, 0) + (0 if name.isupper() else 1) + 1
    best = {k: max(v, key=v.get) for k, v in counts.items()}
    return [{**ad, "areas": sorted({best[area_key(n)] for n in ad["areas"]})} for ad in ads]
