"""Claude API harcama korumasi (butce) -- docs/butce-spec.md (v1) uygulamasi.

Yalnizca standart kutuphane. HTTP cagrisi yapmaz, API anahtarini okumaz.
Her ic hata fail-closed: butce dogrulanamiyorsa Claude cagrisina izin verilmez.
Para ic olarak tam sayi mikro-dolardir.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import logging
import math
import numbers
import os
import random
import re
import sqlite3
from urllib.parse import quote
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

log = logging.getLogger("trader_core.budget")

Service = Literal["haftalik_ozet", "lesson", "haber_kolu", "yorumcu"]
SERVICES: tuple[str, ...] = ("haftalik_ozet", "lesson", "haber_kolu", "yorumcu")
# Cekirdek servisler yapilandirmada zorunlu; ust lig servisleri (haber_kolu, yorumcu) eksikse
# varsayilanla tamamlanir (eski yapilandirmalar bozulmaz).
CORE_SERVICES: tuple[str, ...] = ("haftalik_ozet", "lesson")
_EXTRA_DEFAULTS: dict[str, dict[str, Any]] = {
    "daily_cap_usd": {"haber_kolu": 0.10, "yorumcu": 0.15},
    "api_key_env": {"haber_kolu": "ANTHROPIC_API_KEY_HABER", "yorumcu": "ANTHROPIC_API_KEY_YORUMCU"},
    "reservation_ttl_s": {"haber_kolu": 3600, "yorumcu": 108000},
}
_EXTRA_DEADLINE_S = {"haber_kolu": 120, "yorumcu": 300}
DEFAULT_PATH = "config/budget.json"
SCHEMA_VERSION = 1
MAX_TOTAL_INPUT_TOKENS = 100_000
PRICE_KEYS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")

HARD_LIMITS: dict[str, Any] = {
    "daily_cap_usd": {"haftalik_ozet": 0.25, "lesson": 0.10, "haber_kolu": 0.10, "yorumcu": 0.15},
    # 23.11 kullanici karari: ust lig, LLM tavani 20 $
    "monthly_cap_usd": 20.0,
    "warn_fraction_max": 0.70,
    "price_safety_factor_min": 1.0,
    "batch_multiplier_min": 0.5,
    "max_retries_max": 3,
}


class BudgetConfigError(ValueError):
    """Yapilandirma gecersiz / hard limiti gevsetiyor / fiyat-model bilinmiyor."""


# --------------------------------------------------------------------------- yardimcilar

_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]*")


def _scrub(text: Any) -> str:
    return _KEY_RE.sub("***", str(text))


def _dec(x: Any, name: str, *, allow_zero: bool = True) -> Decimal:
    """Sayi kabulu: bool/None/metin/NaN/inf/negatif gecersiz."""
    if isinstance(x, bool) or x is None or not isinstance(x, (int, float, Decimal, numbers.Real)):
        raise BudgetConfigError(f"{name}: gecersiz sayi")
    try:
        d = Decimal(str(x))
    except (InvalidOperation, ValueError):
        raise BudgetConfigError(f"{name}: gecersiz sayi") from None
    if not d.is_finite() or d < 0 or (d == 0 and not allow_zero):
        raise BudgetConfigError(f"{name}: sonlu ve negatif olmayan sayi olmali")
    return d


def _ceil(d: Decimal) -> int:
    return int(d.to_integral_value(rounding=ROUND_CEILING))


def _micro_ceil(usd: Decimal) -> int:
    return _ceil(usd * 1_000_000)


def _usd(micro: int) -> float:
    return round(micro / 1_000_000, 6)


_TS_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z$")


def _fmt(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _parse(ts: str) -> datetime:
    m = _TS_RE.match(ts) if isinstance(ts, str) else None
    if not m:
        raise ValueError("gecersiz zaman damgasi")
    y, mo, d, h, mi, s, frac = m.groups()
    us = int((frac or "0").ljust(6, "0"))
    return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), us, tzinfo=timezone.utc)


def _trunc_ms(dt: datetime) -> datetime:
    return dt.replace(microsecond=(dt.microsecond // 1000) * 1000)


def _next_midnight(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)


def _next_month_start(dt: datetime) -> datetime:
    d = dt.astimezone(timezone.utc)
    return datetime(d.year + (d.month == 12), 1 if d.month == 12 else d.month + 1, 1,
                    tzinfo=timezone.utc)


# --------------------------------------------------------------------------- yapilandirma

_DEFAULT_PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write_5m": 0.125,
                         "cache_write_1h": 0.20, "cache_read": 0.01},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write_5m": 2.50,
                          "cache_write_1h": 4.00, "cache_read": 0.10},
    # 24.11: fiyat claude-api tablosundan (giris 8, cikis 40, onbellek okuma 0.20 $/MTok); yazma fiyatlari 1.25x/2x kuralindan turetildi (kullanilmaz)
    "claude-fable-5-2": {"input": 8.00, "output": 40.00, "cache_write_5m": 10.00,
                         "cache_write_1h": 16.00, "cache_read": 0.20},
}


def _default_retry() -> dict:
    return {"max_retries": 3, "base_s": 2.0, "factor": 2.0, "max_sleep_s": 20.0, "jitter": 0.2,
            "deadline_s": {"haftalik_ozet": 300, "lesson": 300}}


@dataclass(frozen=True)
class BudgetConfig:
    version: int = 1
    db_path: str = "user_data/budget.sqlite"
    daily_cap_usd: dict = field(default_factory=lambda: {"haftalik_ozet": 0.25, "lesson": 0.10})
    monthly_cap_usd: float = 10.0
    monthly_warn_usd: float = 5.0
    warn_fraction: float = 0.70
    prepaid_credit_usd: float = 10.0
    credit_start_ts: str = "2026-11-16T00:00:00.000Z"
    credit_low_usd: float = 3.0
    price_safety_factor: float = 1.0
    prices_verified_on: str | None = None
    batch_multiplier: float = 0.5
    api_key_env: dict = field(default_factory=lambda: {"haftalik_ozet": "ANTHROPIC_API_KEY_HAFTALIK_OZET",
                                                       "lesson": "ANTHROPIC_API_KEY_LESSON"})
    reservation_ttl_s: dict = field(default_factory=lambda: {"haftalik_ozet": 3600, "lesson": 108000})
    retry: dict = field(default_factory=_default_retry)
    prices_usd_per_mtok: dict = field(default_factory=lambda: copy.deepcopy(_DEFAULT_PRICES))

    monthly_share_usd: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        for n in ("daily_cap_usd", "api_key_env", "reservation_ttl_s", "retry",
                  "prices_usd_per_mtok", "monthly_share_usd"):
            object.__setattr__(self, n, copy.deepcopy(getattr(self, n)))
        # ust lig servisleri eksikse varsayilanla tamamla (yalniz dict ise; dogrulama sonra)
        for n, extra in _EXTRA_DEFAULTS.items():
            v = getattr(self, n)
            if isinstance(v, dict):
                for k, dv in extra.items():
                    v.setdefault(k, dv)
        r = self.retry
        if isinstance(r, dict) and isinstance(r.get("deadline_s"), dict):
            for k, dv in _EXTRA_DEADLINE_S.items():
                r["deadline_s"].setdefault(k, dv)
        self._validate()

    # -- dogrulama
    def _validate(self) -> None:
        E = BudgetConfigError
        if isinstance(self.version, bool) or self.version != 1:
            raise E("version 1 olmali")
        if not isinstance(self.db_path, str) or not self.db_path.strip():
            raise E("db_path bos")
        for name in ("daily_cap_usd", "api_key_env", "reservation_ttl_s"):
            v = getattr(self, name)
            if not isinstance(v, dict) or set(v) != set(SERVICES):
                raise E(f"{name}: servis anahtarlari gerekli")
        for s in SERVICES:
            cap = _dec(self.daily_cap_usd[s], f"daily_cap_usd.{s}")
            if cap > Decimal(str(HARD_LIMITS["daily_cap_usd"][s])):
                raise E(f"daily_cap_usd.{s} kilitli ust siniri asiyor")
            env = self.api_key_env[s]
            if not isinstance(env, str) or not env.strip():
                raise E(f"api_key_env.{s} bos")
            _dec(self.reservation_ttl_s[s], f"reservation_ttl_s.{s}", allow_zero=False)
        sh = self.monthly_share_usd
        if not isinstance(sh, dict) or not set(sh) <= set(SERVICES):
            raise E("monthly_share_usd: bilinen servis anahtarlari olmali")
        mcap = _dec(self.monthly_cap_usd, "monthly_cap_usd")
        if sum((_dec(v, f"monthly_share_usd.{k}") for k, v in sh.items()), Decimal(0)) > mcap:
            raise E("monthly_share_usd toplami monthly_cap_usd'yi asiyor")
        if mcap > Decimal(str(HARD_LIMITS["monthly_cap_usd"])):
            raise E("monthly_cap_usd kilitli ust siniri asiyor")
        if _dec(self.monthly_warn_usd, "monthly_warn_usd") > mcap:
            raise E("monthly_warn_usd monthly_cap_usd'yi asamaz")
        wf = _dec(self.warn_fraction, "warn_fraction", allow_zero=False)
        if wf > 1 or wf > Decimal(str(HARD_LIMITS["warn_fraction_max"])):
            raise E("warn_fraction (0, 0.70] araliginda olmali")
        _dec(self.prepaid_credit_usd, "prepaid_credit_usd")
        _dec(self.credit_low_usd, "credit_low_usd")
        try:
            _parse(self.credit_start_ts)
        except ValueError:
            raise E("credit_start_ts gecersiz (YYYY-MM-DDTHH:MM:SS[.mmm]Z)") from None
        if _dec(self.price_safety_factor, "price_safety_factor") < 1:
            raise E("price_safety_factor >= 1.0 olmali")
        if _dec(self.batch_multiplier, "batch_multiplier") < Decimal(
                str(HARD_LIMITS["batch_multiplier_min"])):
            raise E("batch_multiplier >= 0.5 olmali")
        if self.prices_verified_on is not None and not isinstance(self.prices_verified_on, str):
            raise E("prices_verified_on metin veya null olmali")
        r = self.retry
        req = {"max_retries", "base_s", "factor", "max_sleep_s", "jitter", "deadline_s"}
        if not isinstance(r, dict) or set(r) != req:
            raise E("retry anahtarlari eksik/fazla")
        mr = r["max_retries"]
        if isinstance(mr, bool) or not isinstance(mr, int) or not 0 <= mr <= HARD_LIMITS["max_retries_max"]:
            raise E("retry.max_retries 0..3 tam sayi olmali")
        for k in ("base_s", "factor", "max_sleep_s"):
            _dec(r[k], f"retry.{k}")
        if _dec(r["jitter"], "retry.jitter") > 1:
            raise E("retry.jitter <= 1 olmali")
        if not isinstance(r["deadline_s"], dict) or set(r["deadline_s"]) != set(SERVICES):
            raise E("retry.deadline_s tum servisleri gerektirir")
        for s in SERVICES:
            _dec(r["deadline_s"][s], f"retry.deadline_s.{s}", allow_zero=False)
        p = self.prices_usd_per_mtok
        if not isinstance(p, dict) or not p:
            raise E("prices_usd_per_mtok bos")
        for model, row in p.items():
            if not isinstance(model, str) or not model or not isinstance(row, dict) \
                    or set(row) != set(PRICE_KEYS):
                raise E(f"fiyat satiri gecersiz/eksik alan: {_scrub(model)}")
            for k in PRICE_KEYS:
                _dec(row[k], f"prices.{model}.{k}", allow_zero=False)

    # -- turetilmis degerler (mikro-dolar)
    def cap_micro(self, service: str) -> int:
        return _micro_ceil(Decimal(str(self.daily_cap_usd[service])))

    @property
    def monthly_cap_micro(self) -> int:
        return _micro_ceil(Decimal(str(self.monthly_cap_usd)))

    @property
    def monthly_warn_micro(self) -> int:
        return _micro_ceil(Decimal(str(self.monthly_warn_usd)))

    def warn_threshold_micro(self, service: str) -> int:
        return _ceil(Decimal(self.cap_micro(service)) * Decimal(str(self.warn_fraction)))


_CFG_KEYS = {f.name for f in dataclasses.fields(BudgetConfig)}


def load_config(path: str | os.PathLike = DEFAULT_PATH) -> BudgetConfig:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise BudgetConfigError(f"yapilandirma okunamadi: {type(e).__name__}") from None
    if not isinstance(data, dict):
        raise BudgetConfigError("yapilandirma bir JSON nesnesi olmali")
    unknown = set(data) - _CFG_KEYS
    if unknown:
        raise BudgetConfigError(f"bilinmeyen anahtar: {sorted(map(_scrub, unknown))}")
    return BudgetConfig(**data)


# --------------------------------------------------------------------------- veri tipleri

@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0


@dataclass(frozen=True)
class Grant:
    grant_id: str
    service: Service
    est_micro: int
    day: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class Denial:
    service: Service
    reason: str
    detail: str
    retry_after: str | None = None


@dataclass(frozen=True)
class Settlement:
    ok: bool
    cost_micro: int
    overrun_micro: int
    day: str
    duplicate: bool
    estimated_instead: bool
    code: str


@dataclass(frozen=True)
class ErrorAction:
    kind: Literal["retry", "stop", "fail"]
    sleep_s: float = 0.0
    blocked_until: str | None = None


@dataclass(frozen=True)
class BudgetEvent:
    id: int
    kind: str
    service: str | None
    day: str
    ts: str
    message: str
    payload: dict


@dataclass(frozen=True)
class ServiceStatus:
    cap_usd: float
    settled_usd: float
    unsettled_usd: float
    used_usd: float
    pct: float
    remaining_usd: float
    calls_today: int
    state: str


@dataclass(frozen=True)
class BudgetStatus:
    generated_at: str
    day: str
    month: str
    store_ok: bool
    config_ok: bool
    services: dict
    month_used_usd: float
    monthly_cap_usd: float
    monthly_warn_usd: float
    month_state: str
    provider_blocked_until: str | None
    credit_estimate_usd: float
    prices_verified: bool
    pending_event_count: int

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class _StoreFail(Exception):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


# --------------------------------------------------------------------------- cost

def _cost_micro(cfg: BudgetConfig, model: str, usage: Usage | tuple, batch: bool) -> int:
    row = cfg.prices_usd_per_mtok.get(model) if isinstance(model, str) else None
    if row is None:
        raise BudgetConfigError(f"model fiyat tablosunda yok: {_scrub(model)}")
    inp, out, w5, w1, rd = usage
    total_in = inp + w5 + w1 + rd
    if total_in > MAX_TOTAL_INPUT_TOKENS:
        raise BudgetConfigError("toplam girdi 100000 token ustu: fiyat bandi tanimli degil")
    P = {k: Decimal(str(v)) for k, v in row.items()}
    raw = (inp * P["input"] + out * P["output"] + w5 * P["cache_write_5m"]
           + w1 * P["cache_write_1h"] + rd * P["cache_read"])
    factor = Decimal(str(cfg.price_safety_factor))
    if batch:
        factor *= Decimal(str(cfg.batch_multiplier))
    return _ceil(factor * raw)


def _valid_tokens(*vals: Any) -> bool:
    return all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in vals)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS reservations(
  grant_id TEXT PRIMARY KEY, service TEXT NOT NULL, day TEXT NOT NULL, month TEXT NOT NULL,
  state TEXT NOT NULL, est_micro INTEGER NOT NULL, charged_micro INTEGER NOT NULL,
  model TEXT, batch INTEGER NOT NULL DEFAULT 0, usage_json TEXT,
  created_at TEXT NOT NULL, settled_at TEXT);
CREATE INDEX IF NOT EXISTS idx_res_service_day ON reservations(service, day);
CREATE INDEX IF NOT EXISTS idx_res_month ON reservations(month);
CREATE TABLE IF NOT EXISTS blocks(id INTEGER PRIMARY KEY CHECK (id=1), blocked_until TEXT,
  reason TEXT, set_at TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, ev_key TEXT UNIQUE,
  kind TEXT NOT NULL, service TEXT, day TEXT, ts TEXT, payload_json TEXT,
  acked INTEGER NOT NULL DEFAULT 0);
"""

_SVC_TR = {"haftalik_ozet": "haftalık özet", "lesson": "ders", "haber_kolu": "haber kolu",
           "yorumcu": "yorumcu"}


# --------------------------------------------------------------------------- guard

class BudgetGuard:
    def __init__(self, config: BudgetConfig | str | os.PathLike | None,
                 clock: Callable[[], datetime] | None = None, *, read_only: bool = False):
        # read_only=True: depo `file:...?mode=ro` acilir; PRAGMA journal_mode/synchronous, sema kurulumu ve BEGIN IMMEDIATE yok
        # (panel/yayin birimi /opt/trader'i salt okunur baglar; okuma yazma gerektirmemeli).
        self._read_only = read_only
        self._config_error: str | None = None
        self.config: BudgetConfig | None = None
        if isinstance(config, BudgetConfig):
            self.config = config
        else:
            try:
                self.config = load_config(config if config is not None else DEFAULT_PATH)
            except BudgetConfigError as e:
                self._config_error = _scrub(e)
                log.error("butce yapilandirmasi gecersiz: %s", self._config_error)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._rng = random.Random()

    # ---- zaman / depo
    def _clock_now(self) -> datetime:
        d = self._clock()
        if isinstance(d, str):
            d = _parse(d)
        elif isinstance(d, (int, float)) and not isinstance(d, bool):
            d = datetime.fromtimestamp(d, timezone.utc)
        if not isinstance(d, datetime) or d.tzinfo is None:
            raise ValueError("clock tz-aware datetime dondurmeli")
        return _trunc_ms(d.astimezone(timezone.utc))

    def _paths(self) -> tuple[Path, Path]:
        db = Path(self.config.db_path)  # type: ignore[union-attr]
        return db, db.with_name(db.name + ".initialized")

    def _init_schema(self, conn: sqlite3.Connection, now: datetime) -> None:
        for stmt in [s for s in _SCHEMA.split(";") if s.strip()]:
            conn.execute(stmt)
        ts = _fmt(now)
        for k, v in (("schema_version", str(SCHEMA_VERSION)), ("created_at", ts), ("last_ts", ts)):
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES(?,?)", (k, v))
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _open_ro(self) -> sqlite3.Connection:
        db, _marker = self._paths()
        try:
            if not db.exists() or db.stat().st_size == 0:
                raise _StoreFail("store_missing", "veritabani dosyasi yok")
            uri = "file:" + quote(os.path.abspath(db)) + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
        except (sqlite3.Error, OSError) as e:
            raise _StoreFail("store_unavailable", f"depo acilamadi: {type(e).__name__}") from None
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            last = conn.execute("SELECT value FROM meta WHERE key='last_ts'").fetchone()
            if row is None or last is None:
                raise _StoreFail("store_unavailable", "meta eksik")
            if ver > SCHEMA_VERSION or int(row[0]) > SCHEMA_VERSION:
                raise _StoreFail("store_unavailable", "sema surumu koddan yeni")
            return conn
        except _StoreFail:
            conn.close()
            raise
        except (sqlite3.Error, OSError, ValueError) as e:
            conn.close()
            raise _StoreFail("store_unavailable", f"depo hatasi: {type(e).__name__}") from None

    def _open(self) -> sqlite3.Connection:
        if self._read_only:
            return self._open_ro()
        db, marker = self._paths()
        try:
            exists = db.exists()
            if not exists and marker.exists():
                raise _StoreFail("store_missing", "veritabani dosyasi yok ama .initialized isareti var")
            first = (not exists or db.stat().st_size == 0) and not marker.exists()
            if first:
                db.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db), timeout=5.0, isolation_level=None)
        except sqlite3.Error as e:
            raise _StoreFail("store_unavailable", f"depo acilamadi: {type(e).__name__}") from None
        except OSError as e:
            raise _StoreFail("store_unavailable", f"depo acilamadi: {type(e).__name__}") from None
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
            if first:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    has = conn.execute("SELECT 1 FROM sqlite_master WHERE name='meta'").fetchone()
                    if not has:
                        self._init_schema(conn, self._clock_now())
                    conn.execute("COMMIT")
                except BaseException:
                    try:
                        conn.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                    raise
                try:
                    os.chmod(db, 0o600)
                    marker.touch()
                except OSError:
                    pass
            ver = conn.execute("PRAGMA user_version").fetchone()[0]
            row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            last = conn.execute("SELECT value FROM meta WHERE key='last_ts'").fetchone()
            if row is None or last is None:
                raise _StoreFail("store_unavailable", "meta eksik")
            if ver > SCHEMA_VERSION or int(row[0]) > SCHEMA_VERSION:
                raise _StoreFail("store_unavailable", "sema surumu koddan yeni")
            return conn
        except _StoreFail:
            conn.close()
            raise
        except (sqlite3.Error, OSError, ValueError) as e:
            conn.close()
            raise _StoreFail("store_unavailable", f"depo hatasi: {type(e).__name__}") from None

    def _run(self, fn: Callable[[sqlite3.Connection, datetime], Any], write: bool = True) -> Any:
        if self.config is None:
            raise _StoreFail("config_invalid", self._config_error or "yapilandirma gecersiz")
        if write and self._read_only:
            raise _StoreFail("store_unavailable", "depo salt okunur acildi")
        conn = self._open()
        try:
            try:
                conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            except sqlite3.Error as e:
                raise _StoreFail("store_unavailable", f"kilit alinamadi: {type(e).__name__}") from None
            try:
                last = conn.execute("SELECT value FROM meta WHERE key='last_ts'").fetchone()[0]
                now = max(self._clock_now(), _parse(last))
                res = fn(conn, now)
                if write and _fmt(now) > last:
                    conn.execute("UPDATE meta SET value=? WHERE key='last_ts'", (_fmt(now),))
                conn.execute("COMMIT")
                return res
            except BaseException:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise
        except _StoreFail:
            raise
        except (sqlite3.Error, OSError, ValueError) as e:
            raise _StoreFail("store_unavailable", f"depo hatasi: {type(e).__name__}") from None
        finally:
            conn.close()

    # ---- olaylar
    @staticmethod
    def _event(conn, key: str, kind: str, service: str | None, day: str, now: datetime,
               message: str, data: dict | None = None) -> bool:
        payload = {"message": message, **(data or {})}
        cur = conn.execute(
            "INSERT OR IGNORE INTO events(ev_key,kind,service,day,ts,payload_json,acked) "
            "VALUES(?,?,?,?,?,?,0)",
            (_scrub(key), kind, service, day, _fmt(now), _scrub(json.dumps(payload, ensure_ascii=False))))
        return cur.rowcount > 0

    def _day_used(self, conn, service: str, day: str) -> int:
        return conn.execute("SELECT COALESCE(SUM(charged_micro),0) FROM reservations "
                            "WHERE service=? AND day=?", (service, day)).fetchone()[0]

    def _month_used(self, conn, month: str) -> int:
        return conn.execute("SELECT COALESCE(SUM(charged_micro),0) FROM reservations "
                            "WHERE month=?", (month,)).fetchone()[0]

    def _credit_spent(self, conn) -> int:
        return conn.execute("SELECT COALESCE(SUM(charged_micro),0) FROM reservations "
                            "WHERE created_at>=?", (self.config.credit_start_ts,)).fetchone()[0]

    def _post_events(self, conn, now: datetime, service: str, day: str, month: str) -> None:
        cfg = self.config
        cap = cfg.cap_micro(service)
        used = self._day_used(conn, service, day)
        name = _SVC_TR[service]
        capd = f"{cap / 1e6:g}"
        if cap > 0 and used >= cfg.warn_threshold_micro(service):
            pct = f"{cfg.warn_fraction * 100:g}"
            self._event(conn, f"daily_warn_70:{service}:{day}", "daily_warn_70", service, day, now,
                        f"{name} günlük bütçesi %{pct}'e ulaştı: {used / 1e6:.3f} / {capd} $",
                        {"used_usd": _usd(used), "cap_usd": _usd(cap)})
        if cap > 0 and used >= cap:
            self._stopped_event(conn, now, service, day, used)
        mtotal = self._month_used(conn, month)
        if mtotal > cfg.monthly_warn_micro:
            self._event(conn, f"monthly_warn_5usd:{month}", "monthly_warn_5usd", None, day, now,
                        f"Claude API aylık harcaması {mtotal / 1e6:.3f} $ ile "
                        f"{cfg.monthly_warn_usd:g} $ uyarı eşiğini geçti (sınır {cfg.monthly_cap_usd:g} $)",
                        {"month_used_usd": _usd(mtotal)})
        if mtotal >= cfg.monthly_cap_micro:
            self._monthly_stopped_event(conn, now, day, month, mtotal)
        left = Decimal(str(cfg.prepaid_credit_usd)) - Decimal(self._credit_spent(conn)) / 1_000_000
        if left < Decimal(str(cfg.credit_low_usd)):
            self._event(conn, f"credit_low:{day}", "credit_low", None, day, now,
                        f"Tahmini kalan Claude kredisi {float(left):.3f} $ (eşik "
                        f"{cfg.credit_low_usd:g} $; tahmindir, Console bakiyesi gerçektir)",
                        {"credit_estimate_usd": float(round(left, 6))})

    def _stopped_event(self, conn, now, service, day, used) -> None:
        cap = self.config.cap_micro(service)
        tail = {"haftalik_ozet": "haftalık özet atlandı", "haber_kolu": "haber sinyali durdu",
                "yorumcu": "bugünkü yorum atlandı"}.get(service, "bugünkü ders atlandı")
        self._event(conn, f"daily_stopped_100:{service}:{day}", "daily_stopped_100", service, day,
                    now, f"{_SVC_TR[service]} günlük bütçesi doldu: {tail} "
                    f"({used / 1e6:.3f} / {cap / 1e6:g} $)",
                    {"used_usd": _usd(used), "cap_usd": _usd(cap)})

    def _monthly_stopped_event(self, conn, now, day, month, total) -> None:
        self._event(conn, f"monthly_stopped:{month}", "monthly_stopped", None, day, now,
                    f"Claude API aylık bütçesi doldu ({total / 1e6:.3f} / "
                    f"{self.config.monthly_cap_usd:g} $): yeni çağrı yapılmayacak",
                    {"month_used_usd": _usd(total)})

    def _fail_denial(self, service: str, f: _StoreFail) -> Denial:
        log.error("butce reddi %s: %s", f.reason, _scrub(f.detail))
        return Denial(service, f.reason, _scrub(f.detail), None)

    # ---- authorize
    def authorize(self, service: str, est_cost_usd: float) -> Grant | Denial:
        _check_service(service)
        try:
            est = _dec(est_cost_usd, "est_cost_usd", allow_zero=False)
            est_micro = _micro_ceil(est)
        except BudgetConfigError:
            return Denial(service, "invalid_request", "est_cost_usd sonlu ve > 0 olmali", None)
        if est_micro <= 0:
            return Denial(service, "invalid_request", "est_cost_usd sonlu ve > 0 olmali", None)
        if self.config is None:
            return Denial(service, "config_invalid", self._config_error or "yapilandirma gecersiz", None)
        cfg = self.config

        def fn(conn, now: datetime):
            day, month = _fmt(now)[:10], _fmt(now)[:7]
            ts = _fmt(now)
            for s in SERVICES:
                thr = _fmt(now - timedelta(seconds=float(cfg.reservation_ttl_s[s])))
                conn.execute("UPDATE reservations SET state='expired' "
                             "WHERE state='open' AND service=? AND created_at<=?", (s, thr))
            blk = conn.execute("SELECT blocked_until FROM blocks WHERE id=1").fetchone()
            if blk and blk[0] and blk[0] > ts:
                return Denial(service, "provider_blocked",
                              "saglayici limiti nedeniyle engelli", blk[0])
            mtotal = self._month_used(conn, month)
            if mtotal + est_micro > cfg.monthly_cap_micro:
                self._monthly_stopped_event(conn, now, day, month, mtotal)
                self._post_events(conn, now, service, day, month)
                return Denial(service, "monthly_cap", "aylik butce yetersiz",
                              _fmt(_next_month_start(now)))
            used = self._day_used(conn, service, day)
            if used + est_micro > cfg.cap_micro(service):
                self._stopped_event(conn, now, service, day, used)
                self._post_events(conn, now, service, day, month)
                return Denial(service, "daily_cap", "gunluk butce yetersiz",
                              _fmt(_next_midnight(now)))
            gid = uuid.uuid4().hex
            exp = _fmt(now + timedelta(seconds=float(cfg.reservation_ttl_s[service])))
            conn.execute("INSERT INTO reservations(grant_id,service,day,month,state,est_micro,"
                         "charged_micro,batch,created_at) VALUES(?,?,?,?,'open',?,?,0,?)",
                         (gid, service, day, month, est_micro, est_micro, ts))
            self._post_events(conn, now, service, day, month)
            return Grant(gid, service, est_micro, day, ts, exp)  # type: ignore[arg-type]

        try:
            return self._run(fn)
        except _StoreFail as f:
            return self._fail_denial(service, f)

    # ---- record
    def record(self, service: str, grant: Grant, actual_usage: Usage, model: str,
               batch: bool = False) -> Settlement:
        _check_service(service)
        _check_grant(service, grant)
        day0 = grant.day
        if self.config is None:
            return Settlement(False, 0, 0, day0, False, False, "store_error")
        cfg = self.config
        u = actual_usage
        fields = tuple(getattr(u, n, None) for n in (
            "input_tokens", "output_tokens", "cache_write_5m_tokens",
            "cache_write_1h_tokens", "cache_read_tokens"))
        code, cost = "ok", 0
        if not _valid_tokens(*fields):
            code = "bad_usage"
        elif not isinstance(model, str) or model not in cfg.prices_usd_per_mtok:
            code = "unknown_model"
        else:
            try:
                cost = _cost_micro(cfg, model, fields, bool(batch))
            except BudgetConfigError:
                code = "bad_usage"

        def fn(conn, now: datetime):
            row = conn.execute("SELECT service,day,month,state,est_micro,charged_micro FROM "
                               "reservations WHERE grant_id=?", (grant.grant_id,)).fetchone()
            if row is None or row[0] != service:
                return Settlement(False, 0, 0, day0, False, False, "unknown_grant")
            _, day, month, state, est, charged = row
            if state == "settled":
                return Settlement(True, charged, max(0, charged - est), day, True, False, "duplicate")
            if state == "released":
                return Settlement(False, 0, 0, day, False, False, "unknown_grant")
            if code != "ok":
                if code == "unknown_model":
                    self._event(conn, f"unknown_model:{_scrub(model)}", "unknown_model", None, day,
                                now, f"Fiyat tablosunda olmayan model: {_scrub(model)}",
                                {"model": _scrub(model)})
                return Settlement(False, est, 0, day, False, True, code)
            usage_json = json.dumps(dict(zip(("input_tokens", "output_tokens",
                                              "cache_write_5m_tokens", "cache_write_1h_tokens",
                                              "cache_read_tokens"), fields)))
            conn.execute("UPDATE reservations SET state='settled', charged_micro=?, model=?, "
                         "batch=?, usage_json=?, settled_at=? WHERE grant_id=?",
                         (cost, _scrub(model), 1 if batch else 0, usage_json, _fmt(now),
                          grant.grant_id))
            over = max(0, cost - est)
            if over > 0:
                self._event(conn, f"budget_overrun:{grant.grant_id}", "budget_overrun", service,
                            day, now, f"{_SVC_TR[service]}: gerçek maliyet tahmini aştı "
                            f"({cost / 1e6:.6f} $ > {est / 1e6:.6f} $)",
                            {"cost_usd": _usd(cost), "est_usd": _usd(est)})
            self._post_events(conn, now, service, day, month)
            return Settlement(True, cost, over, day, False, False, "ok")

        try:
            return self._run(fn)
        except _StoreFail as f:
            log.error("record basarisiz: %s", _scrub(f.detail))
            return Settlement(False, 0, 0, day0, False, False, "store_error")

    # ---- release
    def release(self, grant: Grant) -> None:
        if not isinstance(grant, Grant):
            raise ValueError("grant gecersiz")
        if self.config is None:
            return

        def fn(conn, now):
            conn.execute("UPDATE reservations SET state='released', charged_micro=0, settled_at=? "
                         "WHERE grant_id=? AND state='open'", (_fmt(now), grant.grant_id))

        try:
            self._run(fn)
        except _StoreFail as f:
            log.error("release basarisiz: %s", _scrub(f.detail))

    # ---- report_error
    def report_error(self, service: str, grant: Grant, attempt: int, status_code: int | None,
                     error_type: str | None = None, error_code: str | None = None,
                     message: str | None = None, retry_after_s: float | None = None) -> ErrorAction:
        _check_service(service)
        _check_grant(service, grant)
        if self.config is None:
            return ErrorAction("fail", 0.0, None)
        cfg = self.config
        r = cfg.retry
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            attempt = 1
        sc = status_code if isinstance(status_code, int) and not isinstance(status_code, bool) else None
        msg = str(message).lower() if message is not None else ""
        etype = error_type if isinstance(error_type, str) else None
        ecode = error_code if isinstance(error_code, str) else None
        kind: str
        until_fn = None
        if sc == 400 and etype in (None, "invalid_request_error") and "api usage limits" in msg:
            kind, until_fn = "stop", _next_midnight
        elif sc == 429 and "enforced_spend_limit_reached" in (ecode, etype):
            kind, until_fn = "stop", _next_month_start
        elif sc in (400, 401, 402, 403, 404, 413):
            kind = "fail"
        elif sc is None or sc in (408, 409, 429) or 500 <= sc <= 599:
            kind = "retry"
        else:
            kind = "fail"
        responded = sc is not None

        def fn(conn, now: datetime):
            k = kind
            blocked = None
            if k == "stop":
                blocked = _fmt(until_fn(now))
                cur = conn.execute("SELECT blocked_until FROM blocks WHERE id=1").fetchone()
                if cur and cur[0] and cur[0] > blocked:
                    blocked = cur[0]
                conn.execute("INSERT OR REPLACE INTO blocks(id,blocked_until,reason,set_at) "
                             "VALUES(1,?,?,?)", (blocked, f"http_{sc}", _fmt(now)))
                day = _fmt(now)[:10]
                self._event(conn, f"provider_limit_hit:{day}:{sc}", "provider_limit_hit", service,
                            day, now, f"Anthropic harcama limiti doldu (HTTP {sc}); "
                            f"{blocked} tarihine kadar Claude çağrısı yok",
                            {"status": sc, "blocked_until": blocked})
            elif k == "retry":
                deadline = float(r["deadline_s"][service])
                try:
                    elapsed = (now - _parse(grant.created_at)).total_seconds()
                except ValueError:
                    elapsed = 0.0
                if attempt > r["max_retries"] or elapsed > deadline:
                    k = "fail"
            if k in ("stop", "fail") and responded:
                conn.execute("UPDATE reservations SET state='released', charged_micro=0, "
                             "settled_at=? WHERE grant_id=? AND state='open'",
                             (_fmt(now), grant.grant_id))
            if k == "retry":
                sleep = min(float(r["max_sleep_s"]),
                            float(r["base_s"]) * float(r["factor"]) ** (attempt - 1))
                sleep *= 1 + self._rng.uniform(-float(r["jitter"]), float(r["jitter"]))
                if isinstance(retry_after_s, (int, float)) and not isinstance(retry_after_s, bool) \
                        and math.isfinite(retry_after_s) and retry_after_s >= 0:
                    sleep = max(sleep, min(float(retry_after_s), float(r["max_sleep_s"])))
                return ErrorAction("retry", float(sleep), None)
            return ErrorAction(k, 0.0, blocked)  # type: ignore[arg-type]

        try:
            res = self._run(fn)
        except _StoreFail as f:
            log.error("report_error basarisiz: %s", _scrub(f.detail))
            return ErrorAction("fail", 0.0, None)
        log.info("report_error %s status=%s -> %s", service, sc, res.kind)
        return res

    # ---- estimate / events / status
    def estimate_cost(self, model: str, input_tokens: int, max_output_tokens: int,
                      cache_write_1h_tokens: int = 0, cache_write_5m_tokens: int = 0,
                      cache_read_tokens: int = 0, batch: bool = False) -> float:
        if self.config is None:
            raise BudgetConfigError(self._config_error or "yapilandirma gecersiz")
        if not _valid_tokens(input_tokens, max_output_tokens, cache_write_1h_tokens,
                             cache_write_5m_tokens, cache_read_tokens):
            raise BudgetConfigError("token sayilari tam sayi >= 0 olmali")
        micro = _cost_micro(self.config, model, (input_tokens, max_output_tokens,
                            cache_write_5m_tokens, cache_write_1h_tokens, cache_read_tokens),
                            bool(batch))
        return micro / 1_000_000

    def pending_events(self) -> list[BudgetEvent]:
        def fn(conn, now):
            return conn.execute("SELECT id,kind,service,day,ts,payload_json FROM events "
                                "WHERE acked=0 ORDER BY id").fetchall()
        try:
            rows = self._run(fn, write=False)
        except _StoreFail as f:
            log.error("pending_events basarisiz: %s", _scrub(f.detail))
            return []
        out = []
        for i, kind, svc, day, ts, pj in rows:
            try:
                p = json.loads(pj)
            except (TypeError, ValueError):
                p = {}
            msg = p.pop("message", "")
            out.append(BudgetEvent(i, kind, svc, day, ts, msg, p))
        return out

    def ack_events(self, event_ids: Sequence[int]) -> None:
        ids = [i for i in (event_ids or []) if isinstance(i, int) and not isinstance(i, bool)]
        if not ids:
            return

        def fn(conn, now):
            conn.executemany("UPDATE events SET acked=1 WHERE id=?", [(i,) for i in ids])
        try:
            self._run(fn)
        except _StoreFail as f:
            log.error("ack_events basarisiz: %s", _scrub(f.detail))

    def api_key_env(self, service: Service) -> str:
        """Anahtarın okunacağı ortam değişkeninin ADI (değer asla döndürülmez)."""
        _check_service(service)
        cfg = self.config
        return cfg.api_key_env[service] if cfg else _DEFAULT_KEY_ENV[service]

    def status(self) -> BudgetStatus:
        cfg = self.config
        try:
            now0 = self._clock_now()
        except ValueError:
            now0 = datetime.now(timezone.utc)
        ts0 = _fmt(now0)
        if cfg is None:
            return self._bad_status(None, ts0, False)

        def fn(conn, now):
            ts = _fmt(now)
            day, month = ts[:10], ts[:7]
            svcs = {}
            blk = conn.execute("SELECT blocked_until FROM blocks WHERE id=1").fetchone()
            blocked = blk[0] if blk and blk[0] and blk[0] > ts else None
            for s in SERVICES:
                settled = conn.execute(
                    "SELECT COALESCE(SUM(charged_micro),0) FROM reservations WHERE service=? "
                    "AND day=? AND state='settled'", (s, day)).fetchone()[0]
                unsettled = conn.execute(
                    "SELECT COALESCE(SUM(charged_micro),0) FROM reservations WHERE service=? "
                    "AND day=? AND state IN ('open','expired')", (s, day)).fetchone()[0]
                calls = conn.execute(
                    "SELECT COUNT(*) FROM reservations WHERE service=? AND day=? "
                    "AND state!='released'", (s, day)).fetchone()[0]
                used = settled + unsettled
                cap = cfg.cap_micro(s)
                if blocked:
                    st = "blocked"
                elif cap > 0 and used >= cap or cap == 0:
                    st = "stopped"
                elif used >= cfg.warn_threshold_micro(s):
                    st = "warn"
                else:
                    st = "ok"
                svcs[s] = ServiceStatus(_usd(cap), _usd(settled), _usd(unsettled), _usd(used),
                                        round(used / cap * 100, 1) if cap else 0.0,
                                        _usd(max(0, cap - used)), calls, st)
            mtotal = self._month_used(conn, month)
            mstate = ("stopped" if mtotal >= cfg.monthly_cap_micro else
                      "warn" if mtotal > cfg.monthly_warn_micro else "ok")
            left = Decimal(str(cfg.prepaid_credit_usd)) - Decimal(self._credit_spent(conn)) / 1_000_000
            pend = conn.execute("SELECT COUNT(*) FROM events WHERE acked=0").fetchone()[0]
            return BudgetStatus(ts, day, month, True, True, svcs, _usd(mtotal),
                                float(cfg.monthly_cap_usd), float(cfg.monthly_warn_usd), mstate,
                                blocked, float(round(left, 6)),
                                cfg.prices_verified_on is not None, pend)

        try:
            return self._run(fn, write=False)
        except _StoreFail as f:
            log.error("status: %s", _scrub(f.detail))
            return self._bad_status(cfg, ts0, f.reason != "config_invalid")

    def _bad_status(self, cfg: BudgetConfig | None, ts: str, config_ok: bool) -> BudgetStatus:
        svcs = {}
        for s in SERVICES:
            cap = float(cfg.daily_cap_usd[s]) if cfg else 0.0
            svcs[s] = ServiceStatus(cap, 0.0, 0.0, 0.0, 0.0, 0.0, 0, "unavailable")
        return BudgetStatus(ts, ts[:10], ts[:7], False, bool(cfg) and config_ok, svcs, 0.0,
                            float(cfg.monthly_cap_usd) if cfg else 0.0,
                            float(cfg.monthly_warn_usd) if cfg else 0.0, "stopped", None,
                            0.0, bool(cfg and cfg.prices_verified_on is not None), 0)

    # ---- operator araci (dondurulmus arayuze dahil degil)
    def reinitialize(self, assumed_spent_today_usd: dict) -> None:
        if self.config is None:
            raise BudgetConfigError(self._config_error or "yapilandirma gecersiz")
        spent = {}
        for s in SERVICES:
            spent[s] = _micro_ceil(_dec(assumed_spent_today_usd.get(s, 0), f"assumed.{s}"))
        db, marker = self._paths()
        now = self._clock_now()
        if db.exists():
            db.rename(db.with_name(f"{db.name}.old-{now.strftime('%Y%m%dT%H%M%S')}"))
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db), timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("BEGIN IMMEDIATE")
            self._init_schema(conn, now)
            ts = _fmt(now)
            for s, m in spent.items():
                conn.execute("INSERT INTO reservations(grant_id,service,day,month,state,est_micro,"
                             "charged_micro,model,batch,created_at,settled_at) "
                             "VALUES(?,?,?,?,'settled',?,?,'recovery',0,?,?)",
                             (uuid.uuid4().hex, s, ts[:10], ts[:7], m, m, ts, ts))
            conn.execute("COMMIT")
        finally:
            conn.close()
        try:
            os.chmod(db, 0o600)
            marker.touch()
        except OSError:
            pass


def _check_service(service: Any) -> None:
    if service not in SERVICES:
        raise ValueError(f"gecersiz servis: {_scrub(service)!r}")


def _check_grant(service: str, grant: Any) -> None:
    if not isinstance(grant, Grant):
        raise ValueError("grant gecersiz")
    if grant.service != service:
        raise ValueError("grant baska servise ait")


# --------------------------------------------------------------------------- modul duzeyi

_guard: BudgetGuard | None = None
_guard_lock = threading.Lock()


def _get_guard() -> BudgetGuard:
    global _guard
    with _guard_lock:
        if _guard is not None:
            return _guard
        path = Path(DEFAULT_PATH)
        root = Path(__file__).resolve().parents[2]
        used_root = False
        if not path.is_absolute() and not path.exists() and (root / path).exists():
            path, used_root = root / path, True
        try:
            cfg = load_config(path)
        except BudgetConfigError as e:
            log.error("butce yapilandirmasi gecersiz: %s", _scrub(e))
            g = BudgetGuard(None)
            g.config, g._config_error = None, _scrub(e)
            return g  # onbelege alinmaz: duzelince yeniden denenir
        if used_root and not Path(cfg.db_path).is_absolute():
            cfg = dataclasses.replace(cfg, db_path=str(root / cfg.db_path))
        _guard = BudgetGuard(cfg)
        return _guard


def _set_default_guard(guard: BudgetGuard | None) -> None:
    """Test/ozel yapilandirma icin tekil ornegi degistirir."""
    global _guard
    with _guard_lock:
        _guard = guard


def authorize(service: Service, est_cost_usd: float) -> Grant | Denial:
    return _get_guard().authorize(service, est_cost_usd)


def record(service: Service, grant: Grant, actual_usage: Usage, model: str,
           batch: bool = False) -> Settlement:
    return _get_guard().record(service, grant, actual_usage, model, batch)


def release(grant: Grant) -> None:
    return _get_guard().release(grant)


def report_error(service: Service, grant: Grant, attempt: int, status_code: int | None,
                 error_type: str | None = None, error_code: str | None = None,
                 message: str | None = None, retry_after_s: float | None = None) -> ErrorAction:
    return _get_guard().report_error(service, grant, attempt, status_code, error_type,
                                     error_code, message, retry_after_s)


def estimate_cost(model: str, input_tokens: int, max_output_tokens: int,
                  cache_write_1h_tokens: int = 0, cache_write_5m_tokens: int = 0,
                  cache_read_tokens: int = 0, batch: bool = False) -> float:
    return _get_guard().estimate_cost(model, input_tokens, max_output_tokens,
                                      cache_write_1h_tokens, cache_write_5m_tokens,
                                      cache_read_tokens, batch)


def status() -> BudgetStatus:
    return _get_guard().status()


def pending_events() -> list[BudgetEvent]:
    return _get_guard().pending_events()


def ack_events(event_ids: Sequence[int]) -> None:
    return _get_guard().ack_events(event_ids)


_DEFAULT_KEY_ENV = {"haftalik_ozet": "ANTHROPIC_API_KEY_HAFTALIK_OZET", "lesson": "ANTHROPIC_API_KEY_LESSON",
                    **_EXTRA_DEFAULTS["api_key_env"]}


def api_key_env(service: Service) -> str:
    _check_service(service)
    cfg = _get_guard().config
    return cfg.api_key_env[service] if cfg else _DEFAULT_KEY_ENV[service]
