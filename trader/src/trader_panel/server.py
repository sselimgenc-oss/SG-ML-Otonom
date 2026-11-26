"""Salt okunur HTTP sunucusu: stdlib ThreadingHTTPServer, yalniz GET/HEAD, yalniz 127.0.0.1 (docs/panel-spec.md §1, §4, §6, §10).

- Bind adresi dogrulanir; farkliysa baslamaz. `Host` basligi 127.0.0.1:<port> / localhost:<port> disinda ise 400.
- Eszamanli is en cok 8 (semafor); istek basina zaman asimi (calisma suresi + soket); yanit boyutu ustu.
- Statik dosyalar sabit haritadan (bellekte), yol gezintisi yok. Veri yazilmaz, sir okunmaz.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .data import PanelConfig, PanelData

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {"/": ("index.html", "text/html; charset=utf-8"),
                "/static/panel.css": ("panel.css", "text/css; charset=utf-8"),
                "/static/panel.js": ("panel.js", "application/javascript; charset=utf-8")}
CSP = "default-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
SECURITY_HEADERS = {"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"}
ACQUIRE_WAIT_S = 1.0


def build_api(data: PanelData) -> dict:
    """Uc nokta haritasi (canli sunucu ve anlik goruntu ayni mantigi kullanir)."""
    return {"/api/status": lambda q: data.status(),
           "/api/ledger": lambda q: data.cached(("ledger", q.get("bot"), q.get("day")), lambda: data.ledger(q.get("bot"), q.get("day"))),
           "/api/curve": lambda q: data.cached(("curve", q.get("bot")), lambda: data.curve(q.get("bot"))),
           "/api/risk": lambda q: data.cached(("risk", q.get("bot")), lambda: data.risk(q.get("bot"))),
           "/api/pano": lambda q: data.cached(("pano", q.get("bot")), lambda: data.pano(q.get("bot"))),
           "/api/kapanan": lambda q: data.cached(("kapanan", q.get("bot"), q.get("period")), lambda: data.kapanan(q.get("bot"), q.get("period"))),
           "/api/budget": lambda q: data.cached(("budget",), data.budget),
           "/api/learning": lambda q: data.cached(("learning",), data.learning),
           "/api/tutarlilik": lambda q: data.cached(("tutarlilik",), data.tutarlilik),
           "/api/pbo": lambda q: data.cached(("pbo",), data.pbo),
           "/api/ciktikaniti": lambda q: data.cached(("ciktikaniti",), data.ciktikaniti),
           "/api/alinmayansonuc": lambda q: data.cached(("alinmayansonuc",), data.alinmayansonuc),
           "/api/health": lambda q: data.cached(("health",), data.health),
           "/api/system": lambda q: data.cached(("system",), data.system),
           "/healthz": lambda q: {"ok": True}}


def _load_static() -> dict[str, tuple[bytes, str]]:
    return {url: ((STATIC_DIR / name).read_bytes(), ctype) for url, (name, ctype) in STATIC_FILES.items()}


def make_server(cfg: PanelConfig, data: PanelData) -> ThreadingHTTPServer:
    static = _load_static()
    sem = threading.BoundedSemaphore(int(cfg.max_concurrent))
    allowed_hosts = {f"127.0.0.1:{cfg.port}", f"localhost:{cfg.port}"}
    timeout_s = float(cfg.request_timeout_s)
    max_bytes = int(cfg.max_response_bytes)

    api = build_api(data)

    class Handler(BaseHTTPRequestHandler):
        server_version = "trader-panel"
        sys_version = ""
        protocol_version = "HTTP/1.0"
        timeout = timeout_s                       # soket okuma/yazma zaman asimi

        def log_message(self, fmt, *args):       # yalniz yontem/yol/kod; baslik, sir yok
            sys.stderr.write("panel: %s %s\n" % (self.command, self.path.split("?", 1)[0][:80]))

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if len(body) > max_bytes:
                body = b'{"ok":false,"code":"yanit_buyuk"}'
                code = 500
            self._send(code, body, "application/json; charset=utf-8")

        def _handle(self) -> None:
            if self.command not in ("GET", "HEAD"):
                self.send_response(405)
                self.send_header("Allow", "GET, HEAD")
                self.send_header("Content-Length", "0")
                for k, v in SECURITY_HEADERS.items():
                    self.send_header(k, v)
                self.end_headers()
                return
            if self.headers.get("Host") not in allowed_hosts:
                self._json(400, {"ok": False, "code": "host_gecersiz"})
                return
            u = urlsplit(self.path)
            if u.path in static:
                body, ctype = static[u.path]
                self._send(200, body, ctype)
                return
            fn = api.get(u.path)
            if fn is None:
                self._json(404, {"ok": False, "code": "yok"})
                return
            try:
                q = {k: v[0] for k, v in parse_qs(u.query, max_num_fields=8).items() if v}
            except ValueError:
                self._json(400, {"ok": False, "code": "sorgu_gecersiz"})
                return
            if not sem.acquire(timeout=ACQUIRE_WAIT_S):
                self._json(503, {"ok": False, "code": "mesgul"})
                return
            box: dict = {}

            def work() -> None:
                try:
                    box["v"] = fn(q)
                except Exception as e:  # noqa: BLE001
                    box["v"] = {"ok": False, "code": type(e).__name__}
                finally:
                    sem.release()          # is bitmeden birakilmaz: zaman asimina ugrayan is de yuk sayilir

            t = threading.Thread(target=work, daemon=True)
            t.start()
            t.join(timeout_s)
            if "v" not in box:
                self._json(503, {"ok": False, "code": "zaman_asimi"})
                return
            self._json(200, box["v"])

        do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _handle

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 16

    srv = Server(("127.0.0.1", cfg.port), Handler)
    if srv.server_address[0] != "127.0.0.1":     # savunma: baska adres dinleniyorsa baslama
        srv.server_close()
        raise RuntimeError("yalniz 127.0.0.1 dinlenebilir")
    return srv
