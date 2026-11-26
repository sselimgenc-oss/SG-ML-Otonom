"""Anlik goruntu (docs/panel-spec.md §13): verisi gomulu, tek, kendi kendine yeten HTML.

Canli sunucuyla AYNI uc noktalar (server.build_api) cagrilir; mantik cogaltilmaz. Ag yok, sir yok:
cikti yalniz panelin zaten gosterdigi verileri icerir. Bayatlik seridi sayfada, uretim damgasindan istemci tarafinda hesaplanir.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from trader_core import panel_data as P

from .data import BOTS, PanelData
from .server import STATIC_DIR, build_api

SNAP_CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; "
            "base-uri 'none'; form-action 'none'")


def _paths() -> list[str]:
    p = ["/api/status", "/api/budget", "/api/tutarlilik", "/api/pbo", "/api/ciktikaniti", "/api/alinmayansonuc", "/api/health", "/api/system"]
    for b in BOTS:
        p += [f"/api/ledger?bot={b}", f"/api/curve?bot={b}", f"/api/risk?bot={b}", f"/api/pano?bot={b}"]
        p += [f"/api/kapanan?bot={b}&period={d}" for d in ("bugun", "7g", "30g", "tumu")]
    return p


def collect(data: PanelData) -> dict:
    api = build_api(data)
    out = {}
    for path in _paths():
        route, _, qs = path.partition("?")
        q = dict(kv.split("=", 1) for kv in qs.split("&")) if qs else {}
        out[path] = api[route](q)
    return out


def _js_json(obj: object) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render(data: PanelData) -> str:
    now = data.now()
    gen = P.fmt_z(now)
    stamp = P.fmt_tsi(gen)
    snap = {"generated_at": gen, "data": collect(data)}
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css = (STATIC_DIR / "panel.css").read_text(encoding="utf-8")
    js = (STATIC_DIR / "panel.js").read_text(encoding="utf-8")
    for bad in ("</style", "</script"):
        if bad in css.lower() or bad in js.lower():
            raise RuntimeError("statik dosya gomulemez")
    html = html.replace('<link rel="stylesheet" href="/static/panel.css">',
                        f'<meta http-equiv="Content-Security-Policy" content="{SNAP_CSP}">\n'
                        '<meta name="robots" content="noindex">\n'
                        f"<style>\n{css}\n</style>")
    html = html.replace('<span class="so" id="damga"></span>',
                        f'<span class="so" id="damga">Oluşturulma: {stamp}</span>')
    html = html.replace('<script src="/static/panel.js"></script>',
                        f"<script>window.__SNAPSHOT__={_js_json(snap)};</script>\n<script>\n{js}\n</script>")
    if "/static/" in html:
        raise RuntimeError("anlik goruntu kendi kendine yeten olmali")
    return html


def write_atomic(path: str, text: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".snap-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        try:                                # DD-2 D13: dizin girdisi de diske (en iyi caba)
            dfd = os.open(d, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run(cfg, out: str) -> int:
    write_atomic(out, render(PanelData(cfg)))
    return 0
