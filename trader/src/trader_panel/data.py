"""Panel yapilandirmasi ve uc nokta verileri (tum okumalar salt okunur; docs/panel-spec.md §3-§6, §10-§11).

Yalniz `trader_core.panel_data` (ve onun tuttugu ledger/budget/risk/health) kullanilir; `trader_engine` ve
`telegram` ice aktarilmaz. Sir/ortam degiskeni okunmaz.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trader_core import panel_data as P
from trader_core import panel_pano as PP
from trader_core import tg_sade as TS

BOTS = ("learner",)
DEFAULT_PORT = 8787
_PATH_KEYS = ("status_path", "ledger_path", "budget_config",
              "health_state", "kill_file", "engine_config", "tutarlilik_path", "pbo_path", "muhur_path", "exitcf_path", "alinmayan_sonuc_path")
_NUM_KEYS = {"health_stale_s": (60, 86400), "cache_s": (0, 60), "request_timeout_s": (0.5, 30),
             "max_concurrent": (1, 16), "max_response_bytes": (1024, 4 * 1024 * 1024),
             "closed_limit": (1, P.CLOSED_MAX), "curve_limit": (1, P.CLOSED_MAX)}
_LEGACY_KEYS = ("lesson_store",)         # ders sistemi kaldirildi (25.11); eski panel.json dosyalari bozulmasin diye kabul edilir, yok sayilir
_ALLOWED = {"schema", "host", "port", *_PATH_KEYS, *_NUM_KEYS, *_LEGACY_KEYS}


class ConfigError(Exception):
    pass


class PanelConfig:
    def __init__(self, raw: dict, base: Path):
        self.host = "127.0.0.1"
        self.port = int(raw.get("port", DEFAULT_PORT))
        self.base = base
        for k in _PATH_KEYS:
            v = raw.get(k, "")
            if not isinstance(v, str):
                raise ConfigError(f"{k} metin olmali")
            setattr(self, k, v if (not v or os.path.isabs(v)) else str(base / v))
        d = {"health_stale_s": 900, "cache_s": 5, "request_timeout_s": 3, "max_concurrent": 8,
             "max_response_bytes": 512 * 1024, "closed_limit": 200, "curve_limit": 5000}
        for k, (lo, hi) in _NUM_KEYS.items():
            v = raw.get(k, d[k])
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
                raise ConfigError(f"{k} {lo}..{hi} araliginda sayi olmali")
            setattr(self, k, v)


def load_config(path: str | os.PathLike) -> PanelConfig:
    p = Path(path).resolve()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigError("yapilandirma okunamadi") from None
    if not isinstance(raw, dict):
        raise ConfigError("yapilandirma bir JSON nesnesi olmali")
    unknown = set(raw) - _ALLOWED
    if unknown:
        raise ConfigError(f"bilinmeyen anahtar: {sorted(map(str, unknown))}")
    if raw.get("host", "127.0.0.1") != "127.0.0.1":
        raise ConfigError("host yalniz 127.0.0.1 olabilir")
    port = raw.get("port", DEFAULT_PORT)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigError("port 1..65535 olmali")
    cfg = PanelConfig(raw, p.parent.parent)
    for k in ("status_path", "ledger_path"):
        d = os.path.dirname(getattr(cfg, k) or "")
        if d and os.path.isdir(d) and os.access(d, os.W_OK):
            print(f"trader_panel: UYARI: yazilabilir dizin gosteriliyor ({k}); panel hesabina yalniz okuma izni verin",
                  file=sys.stderr)
    return cfg


class PanelData:
    def __init__(self, cfg: PanelConfig, clock: Callable[[], datetime] | None = None):
        self.cfg = cfg
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    # -- yardimcilar
    def now(self) -> datetime:
        return self._clock()

    def _status_path(self, bot: str) -> str:
        return self.cfg.status_path

    def _ledger_path(self, bot: str) -> str:
        return self.cfg.ledger_path

    def _live(self, bot: str) -> dict:
        return P.read_status(self._status_path(bot), self.now(), P.STALE_S)

    def _wrap(self, fn: Callable[[], dict]) -> dict:
        try:
            return {"ok": True, "generated_at": P.fmt_z(self.now()), **fn()}
        except P.SectionError as e:
            return {"ok": False, "code": e.code, "generated_at": P.fmt_z(self.now())}
        except Exception as e:  # noqa: BLE001 - yigin izi yok, yalniz kisa kod
            return {"ok": False, "code": type(e).__name__, "generated_at": P.fmt_z(self.now())}

    def cached(self, key: tuple, fn: Callable[[], dict]) -> dict:
        ttl = self.cfg.cache_s
        t = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and t - hit[0] < ttl:
                return hit[1]
        val = fn()
        with self._lock:
            if len(self._cache) >= 64:
                self._cache.pop(min(self._cache, key=lambda k: self._cache[k][0]))
            self._cache[key] = (t, val)
        return val

    def _day(self, day: str | None) -> str:
        if day is None or day == "":
            return P.today_tr(self.now())
        if not P.DAY_RE.match(day):
            raise P.SectionError("gecersiz_gun")
        try:
            P.day_bounds_utc(day)
        except ValueError:
            raise P.SectionError("gecersiz_gun") from None
        return day

    @staticmethod
    def _bot(bot: str | None) -> str:
        if bot not in BOTS:
            raise P.SectionError("gecersiz_bot")
        return bot

    # -- uc noktalar
    def status(self) -> dict:
        def fn() -> dict:
            bots = {}
            for b in BOTS:
                s = self._live(b)
                if s["state"] == "live":
                    banner = None
                else:
                    banner = (f"BAYAT: {P.fmt_tsi(s['loop_at'])}'dan beri" if s["loop_at"]
                              else f"BAYAT: durum dosyası okunamadı ({s['code']})")
                bots[b] = {**s, "banner": banner}
            kf = self.cfg.kill_file
            try:
                kill = os.path.exists(kf) if kf else None
            except OSError:
                kill = None
            return {"stale_s": P.STALE_S, "daily_max_loss": P.daily_loss_rate(), "kill_file_exists": kill,
                    "bots": bots}
        return self._wrap(fn)

    def _dse(self, bot: str) -> Any:
        s = self._live(bot)
        return s["data"].get("day_start_equity") if s["data"] else None

    def ledger(self, bot: str | None, day: str | None) -> dict:
        def fn() -> dict:
            b = self._bot(bot)
            by_day = bool(day)
            return P.ledger_view(self._ledger_path(b), b, self._day(day), self._dse(b), self.cfg.closed_limit, by_day)
        return self._wrap(fn)

    def _wallet_start(self) -> Any:
        try:
            v = json.loads(Path(self.cfg.engine_config).read_text(encoding="utf-8")).get("wallet_start")
            return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        except (OSError, ValueError, AttributeError):
            return None

    def _motor_ayari(self, mode: Any = "paper") -> dict:
        """engine.base/learner/paper(live) ayarlarinin birlesimi (`engine_config` dizininden); okunamazsa {} (sayi uydurulmaz)."""
        try:
            d = Path(self.cfg.engine_config).parent if self.cfg.engine_config else None
            return TS.motor_ayari(d, str(mode) == "live")
        except (OSError, ValueError, TypeError):
            return {}

    def _max_positions(self, mode: Any = "paper") -> int | None:
        v = self._motor_ayari(mode).get("max_positions")
        return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else None

    def curve(self, bot: str | None) -> dict:
        def fn() -> dict:
            b = self._bot(bot)
            return P.equity_curve(self._ledger_path(b), b, self._wallet_start(), self.cfg.curve_limit)
        return self._wrap(fn)

    def risk(self, bot: str | None) -> dict:
        def fn() -> dict:
            b = self._bot(bot)
            s = self._live(b)
            if s["state"] != "live":
                raise P.SectionError(s["code"])
            d = s["data"]
            return P.risk_usage(self._ledger_path(b), b, d.get("equity"), d.get("day_start_equity"),
                                P.today_tr(self.now()), d.get("mode"), self._max_positions(d.get("mode") or "paper"))
        return self._wrap(fn)

    def _kill_file(self) -> bool | None:
        kf = self.cfg.kill_file
        try:
            return os.path.exists(kf) if kf else None
        except OSError:
            return None

    def pano(self, bot: str | None) -> dict:
        """Pano govdesi: serit, ozet parcalari, acik, k/z, ml1, teknik (hepsi sade Turkce; gosterim)."""
        def fn() -> dict:
            b = self._bot(bot)
            now = self.now()
            s = self._live(b)
            live = s["state"] == "live"
            status = s["data"] if live else None
            lp = self._ledger_path(b)
            ctx = PP.Ctx(lp, b)
            start = self._wallet_start()
            try:
                curve = P.equity_curve(lp, b, start, self.cfg.curve_limit)
            except P.SectionError:
                curve = None
            tk = PP.toplam_kz(ctx, status, s["state"], start)         # TOPLAM K/Z tek kaynak: serit ve K/Z sekmesi ayni nesne
            serit = PP.serit_view(ctx, status, s["state"], self._kill_file(), start, now, curve, s.get("age_s"), tk)
            acik = PP.open_view(ctx, status, now)
            kz = PP.kz_view(ctx, start, now, curve, tk)
            mode = (status or {}).get("mode") or "paper"
            try:
                ml1 = PP.ml1_view(ctx, now, aktif=((self._motor_ayari(mode).get("ml1") or {}).get("aktif")))
            except Exception:  # noqa: BLE001 - ML1 gorunumu istege bagli; okunamazsa gizlenir
                ml1 = None
            safe = {}
            for k, f in (("health", lambda: P.health_view(self.cfg.health_state, now, self.cfg.health_stale_s)),
                         ("budget", lambda: P.budget_view(self.cfg.budget_config)),
                         ("risk", lambda: P.risk_usage(lp, b, status["equity"], status["day_start_equity"], P.today_tr(now),
                                                 status.get("mode"), self._max_positions(mode))["rows"]),
                         ("tut", lambda: P.tutarlilik_view(self._tut_path(), now)),
                         ("mut", lambda: PP.mutabakat_view(self._mut_path())),
                         ("pbo", lambda: P.pbo_view(self._holdout_path("pbo_path", "pbo_ozet.json"),
                                                    self._holdout_path("muhur_path", "muhur.json")))):
                try:
                    safe[k] = f()
                except Exception:  # noqa: BLE001
                    safe[k] = None
            teknik = PP.teknik_view(health=safe["health"], risk_rows=safe["risk"], budget=safe["budget"], tut=safe["tut"],
                                    pbo=safe["pbo"], ctx=ctx, mutabakat=safe["mut"],
                                    dayaniklilik=(status or {}).get("dayaniklilik"))
            isik = PP._problem(teknik.get("saglik"), s["state"], serit["risk"], safe["budget"], ml1)
            return {"bot_durum": s["state"], "mod": (status or {}).get("mode"), "serit": serit, "acik": acik, "kz": kz,
                    "son3": PP.closed_view(lp, b, "tumu", now, 3)["rows"], "ml1": ml1, "teknik": teknik,
                    "isik": isik, "yapmali": PP.ne_yapmali(s["state"], serit["risk"], acik["n"], None, teknik.get("saglik"))}
        return self._wrap(fn)

    def kapanan(self, bot: str | None, period: str | None) -> dict:
        def fn() -> dict:
            b = self._bot(bot)
            return PP.closed_view(self._ledger_path(b), b, period or "bugun", self.now(), self.cfg.closed_limit)
        return self._wrap(fn)

    def budget(self) -> dict:
        return self._wrap(lambda: P.budget_view(self.cfg.budget_config))

    def health(self) -> dict:
        return self._wrap(lambda: P.health_view(self.cfg.health_state, self.now(), self.cfg.health_stale_s))

    def system(self) -> dict:
        return self._wrap(lambda: P.system_view(os.path.dirname(self.cfg.ledger_path) or "/"))

    # -- tutarlilik / PBO (bos yol: veri koku = defter dizininin ustu; PBO/muhur = kod agaci research/holdout)
    def _tut_path(self) -> str:
        c = self.cfg.tutarlilik_path
        return c or (str(Path(self.cfg.ledger_path).parent.parent / "durum" / "tutarlilik_v1.json") if self.cfg.ledger_path else "")

    def _mut_path(self) -> str:
        return str(Path(self.cfg.ledger_path).parent.parent / "durum" / "mutabakat_v1.json") if self.cfg.ledger_path else ""

    def _holdout_path(self, key: str, name: str) -> str:
        return getattr(self.cfg, key) or str(self.cfg.base / "research" / "holdout" / name)

    def tutarlilik(self) -> dict:
        return self._wrap(lambda: P.tutarlilik_view(self._tut_path(), self.now()))

    def pbo(self) -> dict:
        return self._wrap(lambda: P.pbo_view(self._holdout_path("pbo_path", "pbo_ozet.json"),
                                             self._holdout_path("muhur_path", "muhur.json")))

    # -- cikis kaniti (bos yol: exitcf = defter dizini)
    def _exitcf_path(self) -> str:
        c = self.cfg.exitcf_path
        return c or (str(Path(self.cfg.ledger_path).parent / "exit_counterfactual.sqlite") if self.cfg.ledger_path else "")

    def ciktikaniti(self) -> dict:
        return self._wrap(lambda: P.exitcf_view(self._exitcf_path(), self.now()))

    def alinmayansonuc(self) -> dict:
        c = self.cfg.alinmayan_sonuc_path
        return self._wrap(lambda: P.alinmayan_sonuc_view(
            c or (str(Path(self.cfg.ledger_path).parent.parent / "durum" / "alinmayan_sonuc_v1.json") if self.cfg.ledger_path else "")))
