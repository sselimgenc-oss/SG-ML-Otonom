"""Paper-hazirlik testleri icin ortak yardimcilar (ag yok, systemd yok; tmp dizinler)."""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
INSTALL_SH = DEPLOY / "install.sh"
# install.sh'in kuruldugu sunucudaki varsayilan yol (render testi yalniz metin uretir, bu yol gercekte yoktur)
SERVER_TRADER_DIR = "/home/trader/SG-Github-AB-proje/trader"


def install_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


def render_units(out_dir: Path, trader_dir: str = SERVER_TRADER_DIR) -> dict[str, str]:
    """install.sh'in GERCEK `render()` fonksiyonunu (sed) calistirip tum trader-*.service/.timer birimlerini out_dir'e yazar."""
    m = re.search(r"^render\(\) \{.*?^\}", install_text(), re.S | re.M)
    assert m, "install.sh icinde render() bulunamadi"
    script = (f"set -euo pipefail\nTRADER_DIR={shlex.quote(trader_dir)}\n{m.group(0)}\n"
              f"for f in {shlex.quote(str(DEPLOY))}/trader-*.service {shlex.quote(str(DEPLOY))}/trader-*.timer; do\n"
              f"  render \"$f\" {shlex.quote(str(out_dir))}/\"$(basename \"$f\")\"\ndone\n")
    subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True)
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(out_dir.iterdir())}


def render_env_files(out_dir: Path, trader_dir: str = SERVER_TRADER_DIR, with_twin: int = 1) -> dict[str, dict[str, str]]:
    """install.sh'in env ornek kopyalama + yol sed adimlarini tmp dizinde calistirir; {ad: {ANAHTAR: deger}} doner."""
    t = install_text()
    a = t.index("copy_env() {")
    b = t.index("# ---- 8. systemd")
    snippet = t[a:b].replace("/etc/trader-", f"{out_dir}/trader-")
    snippet = snippet.replace('"$TRADER_DIR/deploy/', f'"{ROOT}/deploy/').replace('"$REL_DIR/deploy/', f'"{ROOT}/deploy/')   # DD-9: sablonlar surum dizininden
    # install -o/-g gercek kullanici gerektirir: sahip/grup bayraklarini tmp calismasi icin at
    snippet = snippet.replace('install -m "$4" -o "${3%%:*}" -g "${3##*:}" "$1" "$dst"', 'install -m "$4" "$1" "$dst"')
    snippet = snippet.replace("; chown root:root " + f"{out_dir}/trader-testnet.env", "")   # chown root yalniz root'ta calisir
    script = (f"set -euo pipefail\nTRADER_DIR={shlex.quote(trader_dir)}\nTRADER_USER=trader\nTG_GROUP=trader-tg\nWITH_TWIN={with_twin}\nLIVE=0\nfail() {{ echo \"$*\" >&2; exit 1; }}\n{snippet}\n")
    subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True)
    out: dict[str, dict[str, str]] = {}
    for p in sorted(out_dir.glob("trader-*.env")):
        kv = {}
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln and not ln.startswith("#") and "=" in ln:
                k, _, v = ln.partition("=")
                kv[k] = v
        out[p.name] = kv
    return out


def unit_kv(text: str) -> list[tuple[str, str]]:
    """Birim dosyasi -> [(anahtar, deger)] (yorum/bos satirsiz, sirali)."""
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith(("#", "[")) and "=" in ln:
            k, _, v = ln.partition("=")
            out.append((k, v))
    return out


def created_dirs() -> set[str]:
    """install.sh'in `install -d` ile olusturdugu dizinler (sunucudaki yollar)."""
    t = install_text().replace("\\\n", " ")
    subs = {"${TRADER_DIR}": SERVER_TRADER_DIR, "$TRADER_DIR": SERVER_TRADER_DIR,
            "$WRANGLER_DIR": SERVER_TRADER_DIR + "/var/wrangler", "${HOME_DIR}": "/home/trader", "$HOME_DIR": "/home/trader"}
    dirs: set[str] = set()
    for ln in t.splitlines():
        s = ln.strip()
        if "install -d" not in s:
            continue
        toks = shlex.split(s.split("install -d", 1)[1], comments=True)
        i = 0
        while i < len(toks):
            tk = toks[i]
            if tk in ("-m", "-o", "-g"):
                i += 2
                continue
            for k, v in subs.items():
                tk = tk.replace(k, v)
            if tk.startswith("/"):
                dirs.add(tk.rstrip("/"))
            i += 1
    return dirs


def with_ancestors(paths) -> set[str]:
    out = set()
    for p in paths:
        q = Path(p)
        out.add(str(q))
        out.update(str(a) for a in q.parents)
    return out


# ====================================================================== sahte Binance (ag yok) + sunucu agaci
import copy  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import shutil  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

EXCHANGE_FIXTURE = ROOT / "tests" / "engine" / "fixtures" / "binance" / "exchange_info_sample.json"
NOW0 = datetime(2026, 11, 30, 9, 0, 20, tzinfo=timezone.utc)            # paper baslangic gunu
_TF_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


def to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._b, self.headers, self.text = status, body, {}, text

    def json(self):
        return self._b


class FakeBinance:
    """requests.Session benzeri sahte oturum: mode = ok | 451 | down | 500 | dead (dead: 'olu' an sonrasi yeni mum yok)."""

    def __init__(self, clock, pairs, mode="ok"):
        self.clock, self.pairs, self.mode = clock, list(pairs), mode
        self.dead_at_ms: int | None = None
        self.paths: list[str] = []
        base = json.loads(EXCHANGE_FIXTURE.read_text())
        proto = base["symbols"][0]
        self.info = {"timezone": base.get("timezone", "UTC"), "symbols": []}
        for p in self.pairs:
            s = copy.deepcopy(proto)
            s["symbol"] = p.replace("/", "")
            self.info["symbols"].append(s)

    def _now_ms(self):
        return to_ms(self.clock.now())

    def _rows(self, symbol, interval, params):
        tf = _TF_MS[interval]
        now = self._now_ms() if self.dead_at_ms is None else min(self._now_ms(), self.dead_at_ms)
        limit = int(params.get("limit", 500))
        start = params.get("startTime")
        end = params.get("endTime", now)
        first = (now // tf) * tf - limit * tf if start is None else -(-int(start) // tf) * tf
        out, t = [], first
        base = 50.0 + (sum(map(ord, symbol)) % 90)
        while len(out) < limit and t <= min(end, now) and t + tf <= now:
            px = base * (1 + 0.002 * math.sin(t / 7.0e6))
            out.append([t, f"{px:.4f}", f"{px * 1.001:.4f}", f"{px * 0.999:.4f}", f"{px:.4f}", "10.0", t + tf - 1,
                        "0", 1, "0", "0", "0"])
            t += tf
        return out

    def get(self, url, params=None, timeout=None):
        path = url.split("fapi.binance.com")[1]
        self.paths.append(path)
        if self.mode == "down":
            raise ConnectionError("Network is unreachable")
        if self.mode == "451":
            return Resp(451, None, "Service unavailable from a restricted location")
        if self.mode == "500":
            return Resp(500, None, "boom")
        params = params or {}
        if path == "/fapi/v1/time":
            return Resp(200, {"serverTime": self._now_ms()})
        if path == "/fapi/v1/exchangeInfo":
            return Resp(200, self.info)
        if path in ("/fapi/v1/klines", "/fapi/v1/markPriceKlines"):
            return Resp(200, self._rows(params["symbol"], params["interval"], params))
        if path == "/fapi/v1/fundingRate":
            return Resp(200, [])
        return Resp(200, {} if "symbol" in params else [])


def write_config(tmp: Path, *, startup_wait_s: float = 0.0, relative: bool = False, pairs=None) -> Path:
    """Gercek config/ dizininin kopyasi (tmp/config). relative=False: motor/feed yollari tmp altinda mutlak (surec-ici testler);
    relative=True: birimdeki gibi goreli yollar (cwd=tmp ile alt surec testleri)."""
    cfg = tmp / "config"
    shutil.copytree(ROOT / "config", cfg)
    raw = json.loads((cfg / "engine.base.json").read_text())
    if pairs is not None:
        raw["pairs"] = list(pairs)
    raw["startup_wait_s"] = startup_wait_s
    if not relative:
        for k in ("var_dir", "market_db", "history_dir", "kill_file"):
            raw[k] = str(tmp / raw[k])
    (cfg / "engine.base.json").write_text(json.dumps(raw))
    return cfg
