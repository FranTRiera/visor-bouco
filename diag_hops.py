"""Diagnóstico temporal: sigue a mano la cadena de redirecciones de la sede."""
import http.client
import sys
import time
import urllib.parse

UA = "bouco-visor/1.0 (consulta personal)"


def trace(url, cookie=True, timeout=20):
    jar = {}
    for hop in range(10):
        p = urllib.parse.urlsplit(url)
        cls = http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
        conn = cls(p.hostname, p.port, timeout=timeout)
        path = p.path + (";" if False else "") + ("?" + p.query if p.query else "")
        headers = {"User-Agent": UA}
        if cookie and jar:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in jar.items())
        t = time.time()
        try:
            conn.request("GET", path or "/", headers=headers)
            r = conn.getresponse()
            body = r.read()
        except Exception as exc:
            print(f"  hop{hop} {url} -> ERROR {exc!r} tras {time.time() - t:.1f}s")
            return
        print(f"  hop{hop} {url} -> {r.status} {len(body)}B {time.time() - t:.2f}s "
              f"loc={r.getheader('location')} cookie={r.getheader('set-cookie')}")
        for c in r.headers.get_all("set-cookie") or []:
            k, _, v = c.split(";")[0].partition("=")
            jar[k] = v
        if r.status in (301, 302, 303, 307, 308):
            url = urllib.parse.urljoin(url, r.getheader("location"))
        else:
            return


for start in sys.argv[1:] or ["https://sede.uco.es/bouco/"]:
    for cookie in (True, False):
        print(f"{start} cookie={cookie}")
        trace(start, cookie)
