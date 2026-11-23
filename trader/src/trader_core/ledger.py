"""Islem defteri ve parametre degisiklik gunlugu (sqlite3, stdlib). Bkz. docs/defter-spec.md (v1 + Revizyon 2-4, sema 4;
sema 4 = docs/defter-ek-alanlar-spec.md).

Yalnizca ekleme (append-only), fail-closed. pandas/numpy ve dis cerceve import edilmez.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
import numbers
import os
import re
import sqlite3
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any
from urllib.parse import quote

log = logging.getLogger("trader_core.ledger")

SCHEMA_VERSION = 7
BOTS = ("learner", "twin")
MIN_FREE_BYTES = 50 * 1024 * 1024
MAX_REASON = 500
MAX_JSON = 16 * 1024
LESSON_MIN_INTERVAL_DAYS = 7

# ---------------------------------------------------------------------------
# Hatalar
# ---------------------------------------------------------------------------


class LedgerError(Exception):
    pass


class LedgerValidationError(LedgerError, ValueError):
    pass


class LedgerConflictError(LedgerError):
    pass


class LedgerWriteError(LedgerError):
    def __init__(self, message: str = "", code: str = "io_error"):
        super().__init__(message)
        self.code = code


class LedgerSchemaError(LedgerError):
    pass


class LedgerStateError(LedgerError):
    pass


# ---------------------------------------------------------------------------
# Parametre sozlugu
# ---------------------------------------------------------------------------

PARAM_SPECS: dict[str, dict[str, Any]] = {
    "range_width_atr": dict(kind="float", lo=3.0, hi=6.0, lesson=False, step=None, scope=None),
    "vol_ratio_max": dict(kind="float", lo=1.25, hi=2.0, lesson=True, step=0.25, scope=("T1", "R1"),
                          bounds=(1.3, 1.7)),
    "edge_zone_atr": dict(kind="float", lo=0.15, hi=0.50, lesson=False, step=None, scope=None),
    "pullback_ema": dict(kind="choice", choices=(20, 50), lesson=False, step=None, scope=None),
    "stop_buffer_atr": dict(kind="float", lo=0.1, hi=1.0, lesson=True, step=0.1, scope=("T1", "R1"),
                            bounds=(0.2, 0.5)),
    "trail_atr": dict(kind="float", lo=2.0, hi=4.0, lesson=True, step=0.5, scope=("T1",),
                      bounds=(2.5, 3.5)),
    "range_target_frac": dict(kind="float", lo=0.5, hi=1.0, lesson=True, step=0.125, scope=("R1",),
                              bounds=(0.6, 0.9)),
    "rr_min": dict(kind="float", lo=1.0, hi=2.0, lesson=True, step=0.25, scope=("R1",),
                   bounds=(1.2, 2.0)),
    "trigger_tf": dict(kind="choice", choices=("1h", "15m"), lesson=False, step=None, scope=None),
}
PARAM_KEYS = tuple(PARAM_SPECS)
# DD-12 WP-08: ders servisinin dokunabildigi iki ek (istege bagli) parametre. Eski surumlerde yoktur; yokluk = varsayilan.
#   session_off: kapali-seans merdiveni (0 hepsi acik, 1 hafta sonu kapali, 2 hafta sonu + 'closed' kapali, 3 hepsi kapali)
#   post_stop_wait: stop sonrasi yeniden giris icin beklenen mum sayisi (0-3)
OPTIONAL_PARAM_SPECS: dict[str, dict[str, Any]] = {
    "session_off": dict(kind="int", lo=0, hi=3, lesson=True, step=1, scope=("T1", "R1"), bounds=(0, 3), default=0),
    "post_stop_wait": dict(kind="int", lo=0, hi=3, lesson=True, step=1, scope=("T1", "R1"), bounds=(0, 3), default=0),
    # Revizyon 7 (docs/cikis-kipleri-spec.md): cikis kipleri (0 kapali, 1 acik); yalniz kanit-yalniz ders girdisiyle (kullanici onayi) acilir
    "exit_breakeven": dict(kind="int", lo=0, hi=1, lesson=True, step=1, scope=("T1",), bounds=(0, 1), default=0),
    "exit_partial": dict(kind="int", lo=0, hi=1, lesson=True, step=1, scope=("T1",), bounds=(0, 1), default=0),
}
OPTIONAL_PARAM_KEYS = tuple(OPTIONAL_PARAM_SPECS)
_ALL_SPECS: dict[str, dict[str, Any]] = {**PARAM_SPECS, **OPTIONAL_PARAM_SPECS}
CORE_LESSON_PARAMS = ("vol_ratio_max", "stop_buffer_atr", "trail_atr", "range_target_frac", "rr_min")
LESSON_PARAMS = CORE_LESSON_PARAMS + OPTIONAL_PARAM_KEYS
LESSON_BOUNDS_DEFAULT: Mapping[str, tuple[float, float]] = MappingProxyType(
    {k: tuple(_ALL_SPECS[k]["bounds"]) for k in LESSON_PARAMS})
LESSON_STEP: Mapping[str, float] = MappingProxyType({k: _ALL_SPECS[k]["step"] for k in LESSON_PARAMS})
LESSON_SCOPE: Mapping[str, tuple[str, ...]] = MappingProxyType({k: _ALL_SPECS[k]["scope"] for k in LESSON_PARAMS})
PARAM_DEFAULTS: Mapping[str, Any] = MappingProxyType({k: v["default"] for k, v in OPTIONAL_PARAM_SPECS.items()})

_TRIGGER_TFS = ("15m", "1h", "4h", "1d")     # sema 5 (DD-12 WP-02): karar/islem zaman dilimleri
_SHADOW_TFS = ("1h", "15m")                  # golge satirlari (sema 4 tablosu) eski kalir
_SETUPS = ("T1", "R1")                       # golge satirlari ve v1 kurulumlari
_SESSION_TAGS = ("open", "closed", "weekend")
_SOURCES = ("arm", "m1", "l1")
_SETUP_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")
_REGIMES = ("trend_up", "trend_down", "range", "volatile", "unclear")
_VETO = ("allowed", "blocked", "missing", "stale", "not_evaluated")
_SKIP = ("stop_width", "rr_below_min", "veto_blocked", "veto_missing", "veto_stale", "risk_denied",
         "entry_gate_closed", "order_failed", "other", "ml_filter",
         "arm_conflict", "arm_disabled", "session_closed", "flat_bar", "cluster_cap", "max_positions",
         "ml_no_model", "llm_invalid", "etiket_rejim", "etiket_duygu", "etiket_kalabalik")
# DD-12: kagit botta veto yok; asagidaki yeni nedenlerle atlanan karar satirlari veto_status='not_evaluated' yazar
# (record_decision bunu zorlar; eski nedenler icin kural degismedi).
_NEW_SKIP = ("arm_conflict", "arm_disabled", "session_closed", "flat_bar", "cluster_cap", "max_positions",
             "ml_no_model", "llm_invalid", "etiket_rejim", "etiket_duygu", "etiket_kalabalik")
_NOT_EVAL_SKIP = ("stop_width", "rr_below_min", "other", "entry_gate_closed", "ml_filter",
                  "arm_conflict", "arm_disabled", "session_closed", "flat_bar", "cluster_cap", "max_positions",
                  "ml_no_model", "llm_invalid", "etiket_rejim", "etiket_duygu", "etiket_kalabalik")
_EXIT_REASONS = ("stop", "target", "trail_stop", "regime_flip", "time_stop", "manual", "force_exit",
                 "liquidation", "other")
_EXCURSION_TFS = ("1m", "5m", "15m")
_SHADOW_BLOCKS = ("regime_volatile", "regime_unclear", "r1_disabled", "same_bar_reentry", "tf_15m")
_REF_SRCS = ("sim_open", "book")
_EQ_SRCS = ("sim", "exchange")
_PROPOSAL_ACTORS = ("lesson", "user", "system")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_BAR = timedelta(minutes=15)
_TOL = 1e-9

_ALL_SCOPE = ("T1", "R1")


def _affects(q: str, key: str) -> bool:
    """Bolum 5.4: q parametresi key'in kanit kapsamini etkiler mi (sabit tablo)."""
    if q not in LESSON_PARAMS:
        return True
    s_key = LESSON_SCOPE[key] if key in LESSON_PARAMS else _ALL_SCOPE
    return bool(set(LESSON_SCOPE[q]) & set(s_key))


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _num(x, name: str = "deger") -> float:
    if isinstance(x, bool) or not isinstance(x, numbers.Real):
        raise LedgerValidationError(f"{name} sayi olmali")
    v = float(x)
    if not math.isfinite(v):
        raise LedgerValidationError(f"{name} sonlu olmali")
    return v


def _opt_num(x, name):
    return None if x is None else _num(x, name)


def _int(x, name: str, *, minimum: int | None = None) -> int:
    v = _num(x, name)
    if v != int(v):
        raise LedgerValidationError(f"{name} tam sayi olmali")
    v = int(v)
    if minimum is not None and v < minimum:
        raise LedgerValidationError(f"{name} >= {minimum} olmali")
    return v


def _opt_int(x, name, minimum=None):
    return None if x is None else _int(x, name, minimum=minimum)


def _text(x, name: str, *, required: bool = False, limit: int = MAX_REASON) -> str | None:
    if x is None:
        if required:
            raise LedgerValidationError(f"{name} zorunlu")
        return None
    if not isinstance(x, str):
        raise LedgerValidationError(f"{name} metin olmali")
    if required and not x.strip():
        raise LedgerValidationError(f"{name} bos olamaz")
    if len(x) > limit:
        raise LedgerValidationError(f"{name} en fazla {limit} karakter")
    return x


def _norm_side(side) -> str:
    if not isinstance(side, str):
        raise LedgerValidationError("yon metin olmali")
    s = side.strip().lower()
    if s not in ("long", "short"):
        raise LedgerValidationError("yon 'long' veya 'short' olmali")
    return s


def _norm_pair(pair) -> str:
    if not isinstance(pair, str):
        raise LedgerValidationError("cift metin olmali")
    p = pair.strip().upper().split(":", 1)[0].strip()
    if not p:
        raise LedgerValidationError("cift bos olamaz")
    return p


def _choice(x, name, allowed) -> str:
    if not isinstance(x, str) or x not in allowed:
        raise LedgerValidationError(f"{name} {tuple(allowed)} icinden olmali")
    return x


def _setup_code(x, name="setup") -> str:
    """Sema 5: kurulum kodu 2-8 karakter (buyuk harf/rakam); T1/R1 ve yeni kurulumlar (TF1, B1, F1, S1, M1, L1...)."""
    if not isinstance(x, str) or not _SETUP_RE.match(x):
        raise LedgerValidationError(f"{name} 2-8 karakterlik kurulum kodu olmali")
    return x


def _opt_choice(x, name, allowed) -> str | None:
    return None if x is None else _choice(x, name, allowed)


def _lesson_ids_json(x) -> str | None:
    if x is None:
        return None
    if isinstance(x, (str, bytes)) or not isinstance(x, Iterable):
        raise LedgerValidationError("lesson_ids kimlik listesi olmali")
    out = []
    for i in x:
        if isinstance(i, bool) or not isinstance(i, (int, str)):
            raise LedgerValidationError("lesson_ids ogeleri int/str olmali")
        out.append(i)
    return _cj(out)


def _cj(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


def _json_safe(obj):
    if isinstance(obj, Mapping):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else str(obj)
    if isinstance(obj, numbers.Real):
        f = float(obj)
        return f if math.isfinite(f) else str(f)
    return repr(obj)


_ETIKET_ANAHTARLARI = ("duygu", "haber", "etiket_atlardi")        # ESKI satirlardaki yalniz-kayit etiketleri (21 Kasim 2026: yeni yazilmaz; eski satirlar okunur kalir)


def _json_limited(obj, name) -> str:
    try:
        s = _cj(obj)
    except (TypeError, ValueError) as e:
        raise LedgerValidationError(f"{name} JSON'a cevrilemedi: {e}") from e
    if len(s.encode("utf-8")) > MAX_JSON:
        raise LedgerValidationError(f"{name} 16 KiB'i asiyor")
    return s


def _fmt_ts(dt: datetime) -> str:
    d = dt.astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + ".%03dZ" % (d.microsecond // 1000)


def _to_utc(dt, name: str) -> datetime:
    if not isinstance(dt, datetime):
        raise LedgerValidationError(f"{name} datetime olmali")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise LedgerValidationError(f"{name} tz-aware olmali")
    return dt.astimezone(timezone.utc)


def _ts(dt, name: str) -> str:
    return _fmt_ts(_to_utc(dt, name))


def _parse_ts(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def _hash_params(params: Mapping[str, Any]) -> str:
    return hashlib.sha256(_cj(dict(params)).encode("utf-8")).hexdigest()


def _norm_params(params) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        raise LedgerValidationError("params Mapping olmali")
    keys = set(params)
    if not set(PARAM_KEYS) <= keys <= set(PARAM_KEYS) | set(OPTIONAL_PARAM_KEYS):
        missing = sorted(set(PARAM_KEYS) - keys, key=str)
        extra = sorted((k for k in keys if k not in _ALL_SPECS), key=str)
        raise LedgerValidationError(f"params 9 anahtar olmali; eksik={missing} fazla={extra}")
    out: dict[str, Any] = {}
    for k in OPTIONAL_PARAM_KEYS:
        if k in keys:
            spec = OPTIONAL_PARAM_SPECS[k]
            n = _int(params[k], k)
            if n < spec["lo"] or n > spec["hi"]:
                raise LedgerValidationError(f"{k}={n} tarama araligi disinda [{spec['lo']}, {spec['hi']}]")
    for k in PARAM_KEYS:
        spec = PARAM_SPECS[k]
        v = params[k]
        if spec["kind"] == "float":
            f = round(_num(v, k), 6)
            if f < spec["lo"] - _TOL or f > spec["hi"] + _TOL:
                raise LedgerValidationError(f"{k}={f} tarama araligi disinda [{spec['lo']}, {spec['hi']}]")
            out[k] = f
        elif k == "pullback_ema":
            n = _int(v, k)
            if n not in spec["choices"]:
                raise LedgerValidationError(f"{k} 20 veya 50 olmali")
            out[k] = n
        else:
            if not isinstance(v, str) or v not in spec["choices"]:
                raise LedgerValidationError(f"{k} {spec['choices']} icinden olmali")
            out[k] = v
    for k in OPTIONAL_PARAM_KEYS:
        if k in keys:
            out[k] = _int(params[k], k)
    return out


def _norm_bounds(bounds, params: Mapping[str, Any], *, require_contain: bool) -> dict[str, list[float]]:
    if bounds is None:
        return {k: list(LESSON_BOUNDS_DEFAULT[k]) for k in CORE_LESSON_PARAMS}
    if not isinstance(bounds, Mapping) or not set(CORE_LESSON_PARAMS) <= set(bounds) <= set(LESSON_PARAMS):
        raise LedgerValidationError(f"lesson_bounds anahtarlari {CORE_LESSON_PARAMS} (+ istege bagli) olmali")
    out: dict[str, list[float]] = {}
    for k in LESSON_PARAMS:
        if k not in bounds:
            continue                                      # istege bagli parametre: okurken varsayilan sinir
        b = bounds[k]
        if not isinstance(b, (list, tuple)) or len(b) != 2:
            raise LedgerValidationError(f"lesson_bounds[{k}] [alt, ust] olmali")
        lo, hi = round(_num(b[0], k), 6), round(_num(b[1], k), 6)
        spec = _ALL_SPECS[k]
        if lo > hi:
            raise LedgerValidationError(f"lesson_bounds[{k}] alt <= ust olmali")
        if lo < spec["lo"] - _TOL or hi > spec["hi"] + _TOL:
            raise LedgerValidationError(f"lesson_bounds[{k}] tarama araligi disinda")
        if require_contain and not (lo - _TOL <= params.get(k, PARAM_DEFAULTS.get(k)) <= hi + _TOL):
            raise LedgerValidationError(f"lesson_bounds[{k}] baslangic degerini icermeli")
        out[k] = [lo, hi]
    return out


# ---------------------------------------------------------------------------
# Sema 4 olcum alanlari (defter-ek-alanlar-spec 2.1, 2.2, 3.3, 3.4)
# ---------------------------------------------------------------------------

EXEC_KEYS = ("order_ts", "order_ack_ts", "order_ref_price", "order_ref_spread", "order_ref_src",
             "decision_price", "exit_regime")


def _aware_dt(x) -> bool:
    return isinstance(x, datetime) and x.tzinfo is not None and x.utcoffset() is not None


def _good_num(x, *, positive: bool) -> bool:
    if isinstance(x, bool) or not isinstance(x, numbers.Real):
        return False
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(v) and (v > 0 if positive else v >= 0)


def clean_exec_fields(d: Mapping) -> dict:
    """Spec 3.3: yalniz yedi olcum anahtarini dondurur; 2.1 kurallarini ciglayen GRUBU None yapar.
    Hicbir girdide istisna atmaz."""
    out: dict[str, Any] = dict.fromkeys(EXEC_KEYS)
    try:
        get = d.get if isinstance(d, Mapping) else (lambda k, default=None: default)
        ts, ack = get("order_ts"), get("order_ack_ts")
        if ts is not None and _aware_dt(ts):
            out["order_ts"] = ts
            if ack is not None and _aware_dt(ack):
                try:
                    if _fmt_ts(ack) >= _fmt_ts(ts):
                        out["order_ack_ts"] = ack
                except Exception:       # noqa: BLE001 - olcum hicbir zaman yazimi dusurmez
                    pass
        price, spread, src = get("order_ref_price"), get("order_ref_spread"), get("order_ref_src")
        if price is not None and _good_num(price, positive=True) and src in _REF_SRCS:
            if spread is None:
                out["order_ref_price"], out["order_ref_src"] = float(price), src
            elif src == "book" and _good_num(spread, positive=False):
                out["order_ref_price"], out["order_ref_spread"], out["order_ref_src"] = \
                    float(price), float(spread), src
        dp = get("decision_price")
        if dp is not None and _good_num(dp, positive=True):
            out["decision_price"] = float(dp)
        xr = get("exit_regime")
        if isinstance(xr, str) and xr in _REGIMES:
            out["exit_regime"] = xr
    except Exception:                   # noqa: BLE001
        return dict.fromkeys(EXEC_KEYS)
    return out


def _prep_exec(obj, *, exit_: bool) -> dict[str, Any]:
    """Sikı dogrulama (LedgerValidationError) -> sutun degerleri."""
    ts, ack = obj.order_ts, obj.order_ack_ts
    ts_s = None if ts is None else _ts(ts, "order_ts")
    ack_s = None if ack is None else _ts(ack, "order_ack_ts")
    if ack_s is not None:
        if ts_s is None:
            raise LedgerValidationError("order_ack_ts icin order_ts gerekli")
        if ack_s < ts_s:
            raise LedgerValidationError("order_ack_ts >= order_ts olmali")
    price = _opt_num(obj.order_ref_price, "order_ref_price")
    spread = _opt_num(obj.order_ref_spread, "order_ref_spread")
    src = obj.order_ref_src
    if src is not None:
        _choice(src, "order_ref_src", _REF_SRCS)
    if price is not None and price <= 0:
        raise LedgerValidationError("order_ref_price > 0 olmali")
    if spread is not None and spread < 0:
        raise LedgerValidationError("order_ref_spread >= 0 olmali")
    if (src is None) != (price is None):
        raise LedgerValidationError("order_ref_src ve order_ref_price birlikte dolu ya da birlikte NULL olmali")
    if spread is not None and src != "book":
        raise LedgerValidationError("order_ref_spread yalniz order_ref_src='book' ile verilir")
    vals: dict[str, Any] = dict(order_ts=ts_s, order_ack_ts=ack_s, order_ref_price=price,
                                order_ref_spread=spread, order_ref_src=src)
    if exit_:
        dp = _opt_num(obj.decision_price, "decision_price")
        if dp is not None and dp <= 0:
            raise LedgerValidationError("decision_price > 0 olmali")
        xr = obj.exit_regime
        if xr is not None:
            _choice(xr, "exit_regime", _REGIMES)
        vals.update(decision_price=dp, exit_regime=xr)
    return vals


# ---------------------------------------------------------------------------
# Veri sinifları
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionEvent:
    bar_close_ts: datetime
    trigger_tf: str
    pair: str
    side: str
    setup: str
    regime: str
    atr_ratio: float | None
    rh: float | None
    rl: float | None
    rh_touches: int
    rl_touches: int
    features: Mapping[str, float | int | str]
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    param_version_id: int
    veto_status: str
    veto_reason: str | None
    risk_allowed: bool | None
    risk_reason: str | None
    size_qty: float | None
    size_notional: float | None
    size_margin: float | None
    size_risk_amount: float | None
    leverage: int | None
    final_action: str
    skip_reason: str | None
    supersedes_id: int | None = None
    ml_score: float | None = None          # sema 3: ML filtre puani (kalibre olasilik, [0,1]); yoksa None
    arm_id: str | None = None               # sema 5: None => setup@trigger_tf
    session_tag: str | None = None          # sema 5: open/closed/weekend ya da None
    lesson_ids: Sequence[int | str] | None = None
    source: str = "arm"                     # sema 5: arm/m1/l1


@dataclass(frozen=True)
class TradeEntry:
    trade_id: int
    decision_id: int
    entry_ts: datetime
    entry_price: float
    qty: float
    leverage: int
    fee_entry: float
    supersedes_id: int | None = None
    order_ts: datetime | None = None            # sema 4 (defter-ek-alanlar-spec 2.1): hepsi NULL olabilir
    order_ack_ts: datetime | None = None
    order_ref_price: float | None = None
    order_ref_spread: float | None = None
    order_ref_src: str | None = None


@dataclass(frozen=True)
class TradeExit:
    trade_id: int
    exit_ts: datetime
    exit_price: float
    exit_reason: str
    planned_exit: float | None
    fee_exit: float
    funding_paid: float
    supersedes_id: int | None = None
    max_favorable_price: float | None = None   # sema 2 (3.4.1): uclu birlikte verilir ya da birlikte None
    max_adverse_price: float | None = None
    excursion_tf: str | None = None            # "1m" | "5m" | "15m"
    order_ts: datetime | None = None            # sema 4 (2.2): hepsi NULL olabilir
    order_ack_ts: datetime | None = None
    order_ref_price: float | None = None
    order_ref_spread: float | None = None
    order_ref_src: str | None = None
    decision_price: float | None = None
    exit_regime: str | None = None
    # Kismi cikis sonrasi: SON bacagin gercek dolum fiyati. YALNIZ `slippage_exit` hesabinda (planlanan cikisa karsi) kullanilir;
    # `exit_price` (karma), brut/gerceklesen PnL ve mutabakat degismez. Sema degismez (yeni sutun yok).
    leg_exit_price: float | None = None


@dataclass(frozen=True)
class ShadowEvent:
    """Sema 4 (2.4): aday bastiran bloklarin golge karar satiri. `decision_events`'e girmez."""
    block: str
    bar_close_ts: datetime
    trigger_tf: str
    pair: str
    side: str
    setup: str
    regime: str
    atr_ratio: float | None
    rh: float | None
    rl: float | None
    features: Mapping[str, float | int | str]
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    param_version_id: int
    strategy: str
    reasons: str
    pos_open: bool
    gate_code: str | None = None


@dataclass(frozen=True)
class ShadowRecord(ShadowEvent):
    id: int = 0
    bot: str = ""
    recorded_at: datetime | None = None


@dataclass(frozen=True)
class EquityMark:
    """Sema 4 (2.5): karar adimi basina oz varlik isareti."""
    ts: datetime
    wallet: float
    equity: float
    equity_low: float
    n_open: int
    src: str


@dataclass(frozen=True)
class EquityMarkRecord(EquityMark):
    id: int = 0
    bot: str = ""
    recorded_at: datetime | None = None


@dataclass(frozen=True)
class ProposalResult:
    ok: bool
    proposal_id: int
    status: str
    code: str
    reason: str


@dataclass(frozen=True)
class ActivationResult:
    ok: bool
    code: str
    reason: str
    version_id: int | None
    activation_id: int | None
    proposal_id: int | None


@dataclass(frozen=True)
class Health:
    ok: bool
    code: str
    detail: str


@dataclass(frozen=True)
class ActiveParams:
    version_id: int
    activation_id: int
    params: Mapping[str, Any]
    lesson_bounds: Mapping[str, tuple[float, float]]
    params_hash: str
    activated_at: datetime


@dataclass(frozen=True)
class ParamVersion:
    id: int
    bot: str
    params: Mapping[str, Any]
    params_hash: str
    lesson_bounds: Mapping[str, tuple[float, float]]
    parent_version_id: int | None
    author: str
    reason: str
    evidence: Mapping[str, Any] | None
    proposal_id: int | None
    created_at: datetime

    @property
    def version_id(self) -> int:
        return self.id


@dataclass(frozen=True)
class ActivationEvent:
    id: int
    bot: str
    version_id: int
    prev_version_id: int | None
    kind: str
    actor: str
    reason: str
    proposal_id: int | None
    activated_at: datetime


@dataclass(frozen=True)
class DecisionRecord:
    id: int
    bot: str
    bar_close_ts: datetime
    trigger_tf: str
    pair: str
    side: str
    setup: str
    regime: str
    atr_ratio: float | None
    rh: float | None
    rl: float | None
    rh_touches: int
    rl_touches: int
    features: Mapping[str, Any]
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    param_version_id: int
    veto_status: str
    veto_reason: str | None
    risk_allowed: bool | None
    risk_reason: str | None
    size_qty: float | None
    size_notional: float | None
    size_margin: float | None
    size_risk_amount: float | None
    leverage: int | None
    final_action: str
    skip_reason: str | None
    supersedes_id: int | None
    recorded_at: datetime
    activation_id: int | None
    ml_score: float | None = None
    arm_id: str | None = None
    session_tag: str | None = None
    lesson_ids: tuple | None = None
    source: str = "arm"


@dataclass(frozen=True)
class TradeRecord:
    trade_id: int
    decision_id: int
    pair: str
    side: str
    setup: str
    regime: str
    atr_ratio: float | None
    param_version_id: int
    activation_id: int | None
    entry_ts: datetime
    entry_price: float
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    qty: float
    leverage: int
    planned_risk: float
    fee_entry: float
    slippage_entry: float
    exit_ts: datetime | None
    exit_price: float | None
    exit_reason: str | None
    planned_exit: float | None
    fee_exit: float | None
    funding_paid: float | None
    gross_pnl: float | None
    realized_pnl: float | None
    r_multiple: float | None
    slippage_exit: float | None
    mfe_r: float | None = None
    mae_r: float | None = None
    bars_held: int | None = None
    excursion_tf: str | None = None
    entry_order_ts: datetime | None = None           # sema 4 (2.3): gorunum sutunlari, ayni adlarla
    entry_order_ack_ts: datetime | None = None
    entry_ref_price: float | None = None
    entry_ref_spread: float | None = None
    entry_ref_src: str | None = None
    slip_exec_entry: float | None = None
    exit_order_ts: datetime | None = None
    exit_order_ack_ts: datetime | None = None
    exit_ref_price: float | None = None
    exit_ref_spread: float | None = None
    exit_ref_src: str | None = None
    slip_exec_exit: float | None = None
    exit_decision_price: float | None = None
    slip_decision_exit: float | None = None
    exit_regime: str | None = None


@dataclass(frozen=True)
class ProposalRecord:
    id: int
    bot: str
    base_version_id: int
    proposal: Mapping[str, Any]
    claimed_evidence: Mapping[str, Any]
    source: str
    created_at: datetime
    status: str
    code: str
    reason: str
    version_id: int | None
    status_actor: str
    status_event_id: int

    @property
    def proposal_id(self) -> int:
        return self.id

    @property
    def changes(self) -> Mapping[str, Any]:
        return self.proposal.get("changes", {})

    @property
    def rationale(self) -> str:
        return self.proposal.get("rationale", "")


@dataclass(frozen=True)
class AggregateRow:
    key: Mapping[str, str | int]
    n: int
    wins: int
    win_rate: float
    sum_r: float
    mean_r: float
    median_r: float
    sum_pnl: float
    sum_fees: float
    sum_funding: float
    mean_slippage_entry: float
    mean_slippage_exit: float | None


# ---------------------------------------------------------------------------
# Sema
# ---------------------------------------------------------------------------

_APPEND_ONLY_TABLES_V3 = ("meta", "decision_events", "trade_entries", "trade_exits", "param_versions",
                          "param_activations", "lesson_proposals", "proposal_status_events",
                          "health_probes", "schema_migrations")
_APPEND_ONLY_TABLES = _APPEND_ONLY_TABLES_V3 + ("shadow_decisions", "equity_marks")


def _bot_check():
    return "CHECK (bot IN ('learner','twin'))"


_DDL_V1 = f"""
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE schema_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL, applied_at TEXT NOT NULL);
CREATE TABLE health_probes (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    probed_at TEXT NOT NULL);
CREATE TABLE lesson_proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    base_version_id INTEGER NOT NULL, proposal TEXT NOT NULL, claimed_evidence TEXT NOT NULL,
    source TEXT NOT NULL CHECK (length(trim(source)) > 0), created_at TEXT NOT NULL);
CREATE TABLE param_versions (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    params TEXT NOT NULL, params_hash TEXT NOT NULL CHECK (length(params_hash) = 64),
    lesson_bounds TEXT NOT NULL,
    parent_version_id INTEGER REFERENCES param_versions(id),
    author TEXT NOT NULL CHECK (author IN ('initial','lesson','user')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    evidence TEXT, proposal_id INTEGER REFERENCES lesson_proposals(id),
    created_at TEXT NOT NULL,
    CHECK (author <> 'lesson' OR evidence IS NOT NULL));
CREATE TABLE param_activations (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    version_id INTEGER NOT NULL REFERENCES param_versions(id), prev_version_id INTEGER,
    kind TEXT NOT NULL CHECK (kind IN ('initial','apply','rollback')),
    actor TEXT NOT NULL CHECK (actor IN ('system','lesson','user')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    proposal_id INTEGER REFERENCES lesson_proposals(id), activated_at TEXT NOT NULL);
CREATE TABLE proposal_status_events (id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES lesson_proposals(id),
    status TEXT NOT NULL CHECK (status IN ('proposed','applied','rejected','needs_user')),
    code TEXT NOT NULL, reason TEXT NOT NULL, version_id INTEGER REFERENCES param_versions(id),
    actor TEXT NOT NULL CHECK (actor IN ('lesson','user','system')), recorded_at TEXT NOT NULL);
CREATE TABLE decision_events (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    bar_close_ts TEXT NOT NULL, trigger_tf TEXT NOT NULL CHECK (trigger_tf IN ('1h','15m')),
    pair TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('long','short')),
    setup TEXT NOT NULL CHECK (setup IN ('T1','R1')),
    regime TEXT NOT NULL CHECK (regime IN ('trend_up','trend_down','range','volatile','unclear')),
    atr_ratio REAL, rh REAL, rl REAL, rh_touches INTEGER NOT NULL, rl_touches INTEGER NOT NULL,
    features TEXT NOT NULL, planned_entry REAL NOT NULL, planned_stop REAL NOT NULL, planned_target REAL,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id),
    activation_id INTEGER,
    veto_status TEXT NOT NULL CHECK (veto_status IN ('allowed','blocked','missing','stale','not_evaluated')),
    veto_reason TEXT, risk_allowed INTEGER CHECK (risk_allowed IS NULL OR risk_allowed IN (0,1)),
    risk_reason TEXT, size_qty REAL, size_notional REAL, size_margin REAL, size_risk_amount REAL,
    leverage INTEGER,
    final_action TEXT NOT NULL CHECK (final_action IN ('entered','skipped')),
    skip_reason TEXT CHECK (skip_reason IS NULL OR skip_reason IN
        ('stop_width','rr_below_min','veto_blocked','veto_missing','veto_stale','risk_denied',
         'entry_gate_closed','order_failed','other')),
    supersedes_id INTEGER REFERENCES decision_events(id), recorded_at TEXT NOT NULL,
    CHECK ((regime = 'range' AND rh IS NOT NULL AND rl IS NOT NULL)
        OR (regime <> 'range' AND rh IS NULL AND rl IS NULL)),
    CHECK (final_action <> 'entered' OR (veto_status = 'allowed' AND risk_allowed = 1
        AND size_qty IS NOT NULL AND size_notional IS NOT NULL AND size_margin IS NOT NULL
        AND size_risk_amount IS NOT NULL AND leverage IS NOT NULL AND skip_reason IS NULL)),
    CHECK (final_action <> 'skipped' OR skip_reason IS NOT NULL),
    CHECK (veto_status NOT IN ('blocked','missing','stale') OR final_action = 'skipped'),
    CHECK (risk_allowed IS NOT 0 OR (final_action = 'skipped' AND skip_reason = 'risk_denied')),
    CHECK (veto_status <> 'not_evaluated' OR (risk_allowed IS NULL
        AND skip_reason IN ('stop_width','rr_below_min','other','entry_gate_closed'))));
CREATE UNIQUE INDEX ux_decision_key ON decision_events
    (bot, pair, side, setup, trigger_tf, bar_close_ts) WHERE supersedes_id IS NULL;
CREATE INDEX ix_decision_supersedes ON decision_events (supersedes_id);
CREATE TABLE trade_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    trade_id INTEGER NOT NULL, decision_id INTEGER NOT NULL REFERENCES decision_events(id),
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id), activation_id INTEGER,
    pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT NOT NULL, entry_ts TEXT NOT NULL,
    entry_price REAL NOT NULL, planned_entry REAL NOT NULL, planned_stop REAL NOT NULL,
    planned_target REAL, qty REAL NOT NULL, leverage INTEGER NOT NULL, planned_risk REAL NOT NULL,
    fee_entry REAL NOT NULL CHECK (fee_entry >= 0), slippage_entry REAL NOT NULL,
    supersedes_id INTEGER REFERENCES trade_entries(id), recorded_at TEXT NOT NULL);
CREATE UNIQUE INDEX ux_entry_trade ON trade_entries (bot, trade_id) WHERE supersedes_id IS NULL;
CREATE INDEX ix_entry_supersedes ON trade_entries (supersedes_id);
CREATE TABLE trade_exits (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    trade_id INTEGER NOT NULL, exit_ts TEXT NOT NULL, exit_price REAL NOT NULL,
    exit_reason TEXT NOT NULL CHECK (exit_reason IN ('stop','target','trail_stop','regime_flip',
        'time_stop','manual','force_exit','liquidation','other')),
    planned_exit REAL, fee_exit REAL NOT NULL CHECK (fee_exit >= 0), funding_paid REAL NOT NULL,
    gross_pnl REAL NOT NULL, realized_pnl REAL NOT NULL, r_multiple REAL NOT NULL, slippage_exit REAL,
    supersedes_id INTEGER REFERENCES trade_exits(id), recorded_at TEXT NOT NULL);
CREATE UNIQUE INDEX ux_exit_trade ON trade_exits (bot, trade_id) WHERE supersedes_id IS NULL;
CREATE INDEX ix_exit_supersedes ON trade_exits (supersedes_id);
CREATE VIEW v_decisions AS
    SELECT d.* FROM decision_events d
    WHERE NOT EXISTS (SELECT 1 FROM decision_events s WHERE s.supersedes_id = d.id);
CREATE VIEW v_trades AS
    SELECT e.bot AS bot, e.trade_id AS trade_id, e.id AS entry_id, e.decision_id AS decision_id,
           e.pair AS pair, e.side AS side, e.setup AS setup, d.regime AS regime, d.atr_ratio AS atr_ratio,
           e.param_version_id AS param_version_id, e.activation_id AS activation_id,
           e.entry_ts AS entry_ts, e.entry_price AS entry_price, e.planned_entry AS planned_entry,
           e.planned_stop AS planned_stop, e.planned_target AS planned_target, e.qty AS qty,
           e.leverage AS leverage, e.planned_risk AS planned_risk, e.fee_entry AS fee_entry,
           e.slippage_entry AS slippage_entry,
           x.id AS exit_id, x.exit_ts AS exit_ts, x.exit_price AS exit_price,
           x.exit_reason AS exit_reason, x.planned_exit AS planned_exit, x.fee_exit AS fee_exit,
           x.funding_paid AS funding_paid, x.gross_pnl AS gross_pnl, x.realized_pnl AS realized_pnl,
           x.r_multiple AS r_multiple, x.slippage_exit AS slippage_exit
    FROM trade_entries e
    JOIN decision_events d ON d.id = e.decision_id
    LEFT JOIN trade_exits x ON x.bot = e.bot AND x.trade_id = e.trade_id
         AND NOT EXISTS (SELECT 1 FROM trade_exits sx WHERE sx.supersedes_id = x.id)
    WHERE NOT EXISTS (SELECT 1 FROM trade_entries se WHERE se.supersedes_id = e.id);
CREATE VIEW v_closed_trades AS SELECT * FROM v_trades WHERE exit_ts IS NOT NULL;
CREATE VIEW v_proposals AS
    SELECT p.id AS id, p.bot AS bot, p.base_version_id AS base_version_id, p.proposal AS proposal,
           p.claimed_evidence AS claimed_evidence, p.source AS source, p.created_at AS created_at,
           ev.status AS status, ev.code AS code, ev.reason AS reason, ev.version_id AS version_id,
           ev.actor AS status_actor, ev.id AS status_event_id
    FROM lesson_proposals p
    JOIN proposal_status_events ev ON ev.id =
        (SELECT MAX(e2.id) FROM proposal_status_events e2 WHERE e2.proposal_id = p.id);
"""


def _trigger_ddl(tables: Sequence[str] = _APPEND_ONLY_TABLES_V3) -> str:
    """Goc n -> n+1 SQL'i o surumun tablolariyla kurulur (eski goc yeni tabloya tetikleyici koymaz)."""
    parts = []
    for t in tables:
        parts.append(f"CREATE TRIGGER trg_{t}_no_update BEFORE UPDATE ON {t} "
                     f"BEGIN SELECT RAISE(ABORT, 'append-only'); END;")
        parts.append(f"CREATE TRIGGER trg_{t}_no_delete BEFORE DELETE ON {t} "
                     f"BEGIN SELECT RAISE(ABORT, 'append-only'); END;")
    return "\n".join(parts)


_EXPECTED_TRIGGERS = ({f"trg_{t}_{k}" for t in _APPEND_ONLY_TABLES for k in ("no_update", "no_delete")}
                      | {"trg_trade_exits_excursion_check"})


def _migration_0_to_1(bot: str, now_s: str) -> str:
    return (_DDL_V1 + "\n" + _trigger_ddl() + "\n"
            + f"INSERT INTO meta (key, value) VALUES ('bot', '{bot}'), ('created_at', '{now_s}'), "
              f"('schema_version', '1');\n")


_VIEWS_V2 = """
CREATE VIEW v_trades AS
    SELECT e.bot AS bot, e.trade_id AS trade_id, e.id AS entry_id, e.decision_id AS decision_id,
           e.pair AS pair, e.side AS side, e.setup AS setup, d.regime AS regime, d.atr_ratio AS atr_ratio,
           e.param_version_id AS param_version_id, e.activation_id AS activation_id,
           e.entry_ts AS entry_ts, e.entry_price AS entry_price, e.planned_entry AS planned_entry,
           e.planned_stop AS planned_stop, e.planned_target AS planned_target, e.qty AS qty,
           e.leverage AS leverage, e.planned_risk AS planned_risk, e.fee_entry AS fee_entry,
           e.slippage_entry AS slippage_entry,
           x.id AS exit_id, x.exit_ts AS exit_ts, x.exit_price AS exit_price,
           x.exit_reason AS exit_reason, x.planned_exit AS planned_exit, x.fee_exit AS fee_exit,
           x.funding_paid AS funding_paid, x.gross_pnl AS gross_pnl, x.realized_pnl AS realized_pnl,
           x.r_multiple AS r_multiple, x.slippage_exit AS slippage_exit,
           x.mfe_r AS mfe_r, x.mae_r AS mae_r, x.bars_held AS bars_held, x.excursion_tf AS excursion_tf
    FROM trade_entries e
    JOIN decision_events d ON d.id = e.decision_id
    LEFT JOIN trade_exits x ON x.bot = e.bot AND x.trade_id = e.trade_id
         AND NOT EXISTS (SELECT 1 FROM trade_exits sx WHERE sx.supersedes_id = x.id)
    WHERE NOT EXISTS (SELECT 1 FROM trade_entries se WHERE se.supersedes_id = e.id);
CREATE VIEW v_closed_trades AS SELECT * FROM v_trades WHERE exit_ts IS NOT NULL;
"""

_EXCURSION_TRIGGER = "trg_trade_exits_excursion_check"
_EXCURSION_TRIGGER_DDL = f"""
CREATE TRIGGER {_EXCURSION_TRIGGER} BEFORE INSERT ON trade_exits
WHEN NOT (
    ((NEW.mfe_r IS NULL) = (NEW.mae_r IS NULL)) AND ((NEW.mae_r IS NULL) = (NEW.excursion_tf IS NULL))
    AND (NEW.mfe_r IS NULL OR (NEW.mfe_r >= 0 AND NEW.mae_r >= 0 AND NEW.excursion_tf IN ('1m','5m','15m')))
    AND (NEW.bars_held IS NULL OR NEW.bars_held >= 0))
BEGIN SELECT RAISE(ABORT, 'excursion_check'); END;
"""


def _migration_1_to_2(bot: str, now_s: str) -> str:
    """Bolum 10.1: yalnizca ekleyici; mevcut satirlara dokunulmaz."""
    drops = "\n".join(f"DROP TRIGGER IF EXISTS trg_{t}_{k};" for t in _APPEND_ONLY_TABLES_V3
                      for k in ("no_update", "no_delete"))
    return ("ALTER TABLE trade_exits ADD COLUMN mfe_r REAL;\n"
            "ALTER TABLE trade_exits ADD COLUMN mae_r REAL;\n"
            "ALTER TABLE trade_exits ADD COLUMN bars_held INTEGER;\n"
            "ALTER TABLE trade_exits ADD COLUMN excursion_tf TEXT;\n"
            "DROP VIEW v_closed_trades;\nDROP VIEW v_trades;\n"
            + _VIEWS_V2 + "\n" + drops + "\n" + _trigger_ddl() + "\n" + _EXCURSION_TRIGGER_DDL + "\n")


def _decision_events_ddl_v3(name: str) -> str:
    """Sema 3 `decision_events`: skip_reason sozlugune 'ml_filter', yeni `ml_score` sutunu. Oz-referans adi
    (`decision_events`) tablo yeniden adlandirilinca dogru cozulur."""
    return f"""
CREATE TABLE {name} (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    bar_close_ts TEXT NOT NULL, trigger_tf TEXT NOT NULL CHECK (trigger_tf IN ('1h','15m')),
    pair TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('long','short')),
    setup TEXT NOT NULL CHECK (setup IN ('T1','R1')),
    regime TEXT NOT NULL CHECK (regime IN ('trend_up','trend_down','range','volatile','unclear')),
    atr_ratio REAL, rh REAL, rl REAL, rh_touches INTEGER NOT NULL, rl_touches INTEGER NOT NULL,
    features TEXT NOT NULL, planned_entry REAL NOT NULL, planned_stop REAL NOT NULL, planned_target REAL,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id),
    activation_id INTEGER,
    veto_status TEXT NOT NULL CHECK (veto_status IN ('allowed','blocked','missing','stale','not_evaluated')),
    veto_reason TEXT, risk_allowed INTEGER CHECK (risk_allowed IS NULL OR risk_allowed IN (0,1)),
    risk_reason TEXT, size_qty REAL, size_notional REAL, size_margin REAL, size_risk_amount REAL,
    leverage INTEGER,
    final_action TEXT NOT NULL CHECK (final_action IN ('entered','skipped')),
    skip_reason TEXT CHECK (skip_reason IS NULL OR skip_reason IN
        ('stop_width','rr_below_min','veto_blocked','veto_missing','veto_stale','risk_denied',
         'entry_gate_closed','order_failed','other','ml_filter')),
    supersedes_id INTEGER REFERENCES decision_events(id), recorded_at TEXT NOT NULL,
    ml_score REAL CHECK (ml_score IS NULL OR (ml_score >= 0 AND ml_score <= 1)),
    CHECK ((regime = 'range' AND rh IS NOT NULL AND rl IS NOT NULL)
        OR (regime <> 'range' AND rh IS NULL AND rl IS NULL)),
    CHECK (final_action <> 'entered' OR (veto_status = 'allowed' AND risk_allowed = 1
        AND size_qty IS NOT NULL AND size_notional IS NOT NULL AND size_margin IS NOT NULL
        AND size_risk_amount IS NOT NULL AND leverage IS NOT NULL AND skip_reason IS NULL)),
    CHECK (final_action <> 'skipped' OR skip_reason IS NOT NULL),
    CHECK (veto_status NOT IN ('blocked','missing','stale') OR final_action = 'skipped'),
    CHECK (risk_allowed IS NOT 0 OR (final_action = 'skipped' AND skip_reason = 'risk_denied')),
    CHECK (veto_status <> 'not_evaluated' OR (risk_allowed IS NULL
        AND skip_reason IN ('stop_width','rr_below_min','other','entry_gate_closed','ml_filter'))));
"""


_DECISION_COLS_V2 = ("id, bot, bar_close_ts, trigger_tf, pair, side, setup, regime, atr_ratio, rh, rl, rh_touches, "
                     "rl_touches, features, planned_entry, planned_stop, planned_target, param_version_id, "
                     "activation_id, veto_status, veto_reason, risk_allowed, risk_reason, size_qty, size_notional, "
                     "size_margin, size_risk_amount, leverage, final_action, skip_reason, supersedes_id, recorded_at")

_V_DECISIONS = """
CREATE VIEW v_decisions AS
    SELECT d.* FROM decision_events d
    WHERE NOT EXISTS (SELECT 1 FROM decision_events s WHERE s.supersedes_id = d.id);
"""


def _migration_2_to_3(bot: str, now_s: str) -> str:
    """Sema 3 (ML-0a, 19a): `decision_events.skip_reason` CHECK'ine 'ml_filter' ve yeni `ml_score` sutunu.
    SQLite CHECK'i degistirmez: tablo yeniden kurulur (kopya, tum satirlar ayni `id` ile; hicbiri degismez/silinmez).
    SQLite'in resmi yeniden-kurma yordami: `PRAGMA foreign_keys=OFF` islemin DISINDA (`_FK_OFF_MIGRATIONS`),
    goc sonrasi `foreign_key_check`; goruntuler once dusurulur (RENAME/DROP hata vermesin), sonra kurulur;
    append-only tetikleyicileri yeniden kurulur."""
    drops = "\n".join(f"DROP TRIGGER IF EXISTS trg_{t}_{k};" for t in _APPEND_ONLY_TABLES_V3
                      for k in ("no_update", "no_delete"))
    return ("DROP VIEW IF EXISTS v_closed_trades;\nDROP VIEW IF EXISTS v_trades;\nDROP VIEW IF EXISTS v_decisions;\n"
            + _decision_events_ddl_v3("decision_events_v3") + "\n"
            f"INSERT INTO decision_events_v3 ({_DECISION_COLS_V2}) SELECT {_DECISION_COLS_V2} FROM decision_events;\n"
            "DROP TABLE decision_events;\n"
            "ALTER TABLE decision_events_v3 RENAME TO decision_events;\n"
            "CREATE UNIQUE INDEX ux_decision_key ON decision_events\n"
            "    (bot, pair, side, setup, trigger_tf, bar_close_ts) WHERE supersedes_id IS NULL;\n"
            "CREATE INDEX ix_decision_supersedes ON decision_events (supersedes_id);\n"
            + _V_DECISIONS + _VIEWS_V2 + "\n" + drops + "\n" + _trigger_ddl() + "\n")   # excursion tetikleyicisi trade_exits'te zaten var


# Sirali goc listesi: MIGRATIONS[n] = n -> n+1 icin SQL ureten fonksiyon (bot, now_s).
_EXEC_COLS_ENTRY = (
    ("order_ts", "TEXT"),
    ("order_ack_ts", "TEXT CHECK (order_ack_ts IS NULL OR (order_ts IS NOT NULL AND order_ack_ts >= order_ts))"),
    ("order_ref_price", "REAL CHECK (order_ref_price IS NULL OR order_ref_price > 0)"),
    ("order_ref_spread", "REAL CHECK (order_ref_spread IS NULL OR order_ref_spread >= 0)"),
    ("order_ref_src", "TEXT CHECK ((order_ref_src IS NULL) = (order_ref_price IS NULL) "
                      "AND (order_ref_src IS NULL OR order_ref_src IN ('sim_open','book')) "
                      "AND (order_ref_spread IS NULL OR order_ref_src = 'book'))"),
)
_EXEC_COLS_EXIT = _EXEC_COLS_ENTRY + (
    ("decision_price", "REAL CHECK (decision_price IS NULL OR decision_price > 0)"),
    ("exit_regime", "TEXT CHECK (exit_regime IS NULL OR exit_regime IN "
                    "('trend_up','trend_down','range','volatile','unclear'))"),
)

_SHADOW_DDL = f"""
CREATE TABLE shadow_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    block TEXT NOT NULL CHECK (block IN ('regime_volatile','regime_unclear','r1_disabled','same_bar_reentry','tf_15m')),
    bar_close_ts TEXT NOT NULL, trigger_tf TEXT NOT NULL CHECK (trigger_tf IN ('1h','15m')),
    pair TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('long','short')),
    setup TEXT NOT NULL CHECK (setup IN ('T1','R1')),
    regime TEXT NOT NULL CHECK (regime IN ('trend_up','trend_down','range','volatile','unclear')),
    atr_ratio REAL, rh REAL, rl REAL, features TEXT NOT NULL,
    planned_entry REAL NOT NULL CHECK (planned_entry > 0), planned_stop REAL NOT NULL CHECK (planned_stop > 0),
    planned_target REAL,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id),
    strategy TEXT NOT NULL, reasons TEXT NOT NULL,
    pos_open INTEGER NOT NULL CHECK (pos_open IN (0,1)), gate_code TEXT, recorded_at TEXT NOT NULL,
    CHECK ((side='long' AND planned_stop < planned_entry) OR (side='short' AND planned_stop > planned_entry)),
    UNIQUE (bot, block, pair, side, setup, trigger_tf, bar_close_ts));
CREATE INDEX ix_shadow_ts ON shadow_decisions (bot, bar_close_ts);
CREATE VIEW v_shadow_decisions AS SELECT s.*, 'shadow' AS final_action FROM shadow_decisions s;
CREATE TABLE equity_marks (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    ts TEXT NOT NULL, wallet REAL NOT NULL, equity REAL NOT NULL, equity_low REAL NOT NULL,
    n_open INTEGER NOT NULL CHECK (n_open >= 0), src TEXT NOT NULL CHECK (src IN ('sim','exchange')),
    recorded_at TEXT NOT NULL, CHECK (equity_low <= equity), UNIQUE (bot, ts));
"""

_VIEWS_V4 = """
CREATE VIEW v_trades AS
    SELECT e.bot AS bot, e.trade_id AS trade_id, e.id AS entry_id, e.decision_id AS decision_id,
           e.pair AS pair, e.side AS side, e.setup AS setup, d.regime AS regime, d.atr_ratio AS atr_ratio,
           e.param_version_id AS param_version_id, e.activation_id AS activation_id,
           e.entry_ts AS entry_ts, e.entry_price AS entry_price, e.planned_entry AS planned_entry,
           e.planned_stop AS planned_stop, e.planned_target AS planned_target, e.qty AS qty,
           e.leverage AS leverage, e.planned_risk AS planned_risk, e.fee_entry AS fee_entry,
           e.slippage_entry AS slippage_entry,
           x.id AS exit_id, x.exit_ts AS exit_ts, x.exit_price AS exit_price,
           x.exit_reason AS exit_reason, x.planned_exit AS planned_exit, x.fee_exit AS fee_exit,
           x.funding_paid AS funding_paid, x.gross_pnl AS gross_pnl, x.realized_pnl AS realized_pnl,
           x.r_multiple AS r_multiple, x.slippage_exit AS slippage_exit,
           x.mfe_r AS mfe_r, x.mae_r AS mae_r, x.bars_held AS bars_held, x.excursion_tf AS excursion_tf,
           e.order_ts AS entry_order_ts, e.order_ack_ts AS entry_order_ack_ts,
           e.order_ref_price AS entry_ref_price, e.order_ref_spread AS entry_ref_spread,
           e.order_ref_src AS entry_ref_src,
           CASE WHEN e.order_ref_price IS NULL THEN NULL
                WHEN e.side = 'long' THEN (e.entry_price - e.order_ref_price) / e.order_ref_price
                ELSE (e.order_ref_price - e.entry_price) / e.order_ref_price END AS slip_exec_entry,
           x.order_ts AS exit_order_ts, x.order_ack_ts AS exit_order_ack_ts,
           x.order_ref_price AS exit_ref_price, x.order_ref_spread AS exit_ref_spread,
           x.order_ref_src AS exit_ref_src,
           CASE WHEN x.order_ref_price IS NULL THEN NULL
                WHEN e.side = 'long' THEN (x.order_ref_price - x.exit_price) / x.order_ref_price
                ELSE (x.exit_price - x.order_ref_price) / x.order_ref_price END AS slip_exec_exit,
           x.decision_price AS exit_decision_price,
           CASE WHEN x.decision_price IS NULL THEN NULL
                WHEN e.side = 'long' THEN (x.decision_price - x.exit_price) / x.decision_price
                ELSE (x.exit_price - x.decision_price) / x.decision_price END AS slip_decision_exit,
           x.exit_regime AS exit_regime
    FROM trade_entries e
    JOIN decision_events d ON d.id = e.decision_id
    LEFT JOIN trade_exits x ON x.bot = e.bot AND x.trade_id = e.trade_id
         AND NOT EXISTS (SELECT 1 FROM trade_exits sx WHERE sx.supersedes_id = x.id)
    WHERE NOT EXISTS (SELECT 1 FROM trade_entries se WHERE se.supersedes_id = e.id);
CREATE VIEW v_closed_trades AS SELECT * FROM v_trades WHERE exit_ts IS NOT NULL;
"""


def _migration_3_to_4(bot: str, now_s: str) -> str:
    """Sema 4 (defter-ek-alanlar-spec 2.6): yalnizca ekleyici; tablo yeniden kurulmaz."""
    drops = "\n".join(f"DROP TRIGGER IF EXISTS trg_{t}_{k};" for t in _APPEND_ONLY_TABLES_V3
                      for k in ("no_update", "no_delete"))
    alters = "\n".join(f"ALTER TABLE trade_entries ADD COLUMN {c} {d};" for c, d in _EXEC_COLS_ENTRY) + "\n" \
        + "\n".join(f"ALTER TABLE trade_exits ADD COLUMN {c} {d};" for c, d in _EXEC_COLS_EXIT) + "\n"
    return (alters + _SHADOW_DDL
            + "DROP VIEW v_closed_trades;\nDROP VIEW v_trades;\n" + _VIEWS_V4 + "\n"
            + drops + "\n" + _trigger_ddl(_APPEND_ONLY_TABLES) + "\n")


_NEW_SKIPS_SQL = ("'arm_conflict','arm_disabled','session_closed','flat_bar','cluster_cap','max_positions',"
                  "'ml_no_model','llm_invalid','etiket_rejim','etiket_duygu','etiket_kalabalik'")


def _decision_events_ddl_v5(name: str) -> str:
    """Sema 5 (DD-12 WP-02): trigger_tf {15m,1h,4h,1d}; setup uzunluk denetimi 2..8; yeni sutunlar arm_id,
    session_tag, lesson_ids, source; skip_reason sozlugu genisler. `bot` CHECK'i eski satirlar icin kalir."""
    return f"""
CREATE TABLE {name} (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL {_bot_check()},
    bar_close_ts TEXT NOT NULL,
    trigger_tf TEXT NOT NULL CHECK (trigger_tf IN ('15m','1h','4h','1d')),
    pair TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('long','short')),
    setup TEXT NOT NULL CHECK (length(setup) BETWEEN 2 AND 8),
    regime TEXT NOT NULL CHECK (regime IN ('trend_up','trend_down','range','volatile','unclear')),
    atr_ratio REAL, rh REAL, rl REAL, rh_touches INTEGER NOT NULL, rl_touches INTEGER NOT NULL,
    features TEXT NOT NULL, planned_entry REAL NOT NULL, planned_stop REAL NOT NULL, planned_target REAL,
    param_version_id INTEGER NOT NULL REFERENCES param_versions(id),
    activation_id INTEGER,
    veto_status TEXT NOT NULL CHECK (veto_status IN ('allowed','blocked','missing','stale','not_evaluated')),
    veto_reason TEXT, risk_allowed INTEGER CHECK (risk_allowed IS NULL OR risk_allowed IN (0,1)),
    risk_reason TEXT, size_qty REAL, size_notional REAL, size_margin REAL, size_risk_amount REAL,
    leverage INTEGER,
    final_action TEXT NOT NULL CHECK (final_action IN ('entered','skipped')),
    skip_reason TEXT CHECK (skip_reason IS NULL OR skip_reason IN
        ('stop_width','rr_below_min','veto_blocked','veto_missing','veto_stale','risk_denied',
         'entry_gate_closed','order_failed','other','ml_filter',{_NEW_SKIPS_SQL})),
    supersedes_id INTEGER REFERENCES decision_events(id), recorded_at TEXT NOT NULL,
    ml_score REAL CHECK (ml_score IS NULL OR (ml_score >= 0 AND ml_score <= 1)),
    arm_id TEXT CHECK (arm_id IS NULL OR length(arm_id) > 0),
    session_tag TEXT CHECK (session_tag IS NULL OR session_tag IN ('open','closed','weekend')),
    lesson_ids TEXT,
    source TEXT NOT NULL DEFAULT 'arm' CHECK (source IN ('arm','m1','l1')),
    CHECK ((regime = 'range' AND rh IS NOT NULL AND rl IS NOT NULL)
        OR (regime <> 'range' AND rh IS NULL AND rl IS NULL)),
    CHECK (final_action <> 'entered' OR (veto_status = 'allowed' AND risk_allowed = 1
        AND size_qty IS NOT NULL AND size_notional IS NOT NULL AND size_margin IS NOT NULL
        AND size_risk_amount IS NOT NULL AND leverage IS NOT NULL AND skip_reason IS NULL)),
    CHECK (final_action <> 'skipped' OR skip_reason IS NOT NULL),
    CHECK (veto_status NOT IN ('blocked','missing','stale') OR final_action = 'skipped'),
    CHECK (risk_allowed IS NOT 0 OR (final_action = 'skipped' AND skip_reason = 'risk_denied')),
    CHECK (veto_status <> 'not_evaluated' OR (risk_allowed IS NULL
        AND skip_reason IN ('stop_width','rr_below_min','other','entry_gate_closed','ml_filter',
                            {_NEW_SKIPS_SQL}))));
"""


_DECISION_COLS_V3 = _DECISION_COLS_V2 + ", ml_score"

_TRADE_NOTES_DDL = """
CREATE TABLE trade_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id INTEGER NOT NULL,
    note_date TEXT NOT NULL, tags TEXT NOT NULL, text TEXT NOT NULL, model TEXT,
    cost_usd REAL CHECK (cost_usd IS NULL OR cost_usd >= 0));
CREATE INDEX ix_trade_notes_trade ON trade_notes (trade_id);
"""

_VIEWS_V5 = _VIEWS_V4.replace(
    "           x.exit_regime AS exit_regime\n",
    "           x.exit_regime AS exit_regime,\n           e.arm_id AS arm_id, e.session_tag AS session_tag\n")


def _migration_4_to_5(bot: str, now_s: str) -> str:
    """Sema 5 (DD-12 WP-02): decision_events yeniden kurulur (CHECK degisir); trade_entries'e arm_id/session_tag
    eklenir; trade_notes yeni. Eski satirlar `arm_id = setup||'@'||trigger_tf`; hicbir satir silinmez/degismez
    (id'ler korunur). Goruntuler ve append-only tetikleyicileri once dusurulur, sonra kurulur. FK denetimi
    islem disinda kapali (`_FK_OFF_MIGRATIONS`), goc sonrasi `foreign_key_check`."""
    drops = "\n".join(f"DROP TRIGGER IF EXISTS trg_{t}_{k};" for t in _APPEND_ONLY_TABLES
                      for k in ("no_update", "no_delete"))
    cols = _DECISION_COLS_V3
    return ("DROP VIEW IF EXISTS v_closed_trades;\nDROP VIEW IF EXISTS v_trades;\n"
            "DROP VIEW IF EXISTS v_decisions;\n" + drops + "\n"
            + _decision_events_ddl_v5("decision_events_v5") + "\n"
            f"INSERT INTO decision_events_v5 ({cols}, arm_id, session_tag, lesson_ids, source) "
            f"SELECT {cols}, setup || '@' || trigger_tf, NULL, NULL, 'arm' FROM decision_events;\n"
            "DROP TABLE decision_events;\n"
            "ALTER TABLE decision_events_v5 RENAME TO decision_events;\n"
            "CREATE UNIQUE INDEX ux_decision_key ON decision_events\n"
            "    (bot, pair, side, setup, trigger_tf, bar_close_ts) WHERE supersedes_id IS NULL;\n"
            "CREATE INDEX ix_decision_supersedes ON decision_events (supersedes_id);\n"
            "ALTER TABLE trade_entries ADD COLUMN arm_id TEXT;\n"
            "ALTER TABLE trade_entries ADD COLUMN session_tag TEXT "
            "CHECK (session_tag IS NULL OR session_tag IN ('open','closed','weekend'));\n"
            "UPDATE trade_entries SET arm_id = setup || '@' || "
            "(SELECT d.trigger_tf FROM decision_events d WHERE d.id = trade_entries.decision_id);\n"
            + _TRADE_NOTES_DDL
            + _V_DECISIONS + _VIEWS_V5 + "\n" + _trigger_ddl(_APPEND_ONLY_TABLES) + "\n")


def _decision_events_ddl_v6(name: str) -> str:
    """Sema 6 (DD-12 WP-06a): kagit botta veto yok; girilen/risk_denied/order_failed satirlari veto_status='not_evaluated'
    yazabilir. Yalniz iki CHECK degisir; sutunlar v5 ile ayni."""
    d = _decision_events_ddl_v5(name)
    d = d.replace("CHECK (final_action <> 'entered' OR (veto_status = 'allowed' AND risk_allowed = 1",
                  "CHECK (final_action <> 'entered' OR (veto_status IN ('allowed','not_evaluated') AND risk_allowed = 1", 1)
    old = d[d.index("    CHECK (veto_status <> 'not_evaluated' OR (risk_allowed IS NULL"):]
    new = ("    CHECK (veto_status <> 'not_evaluated' OR final_action = 'entered'\n"
           "        OR skip_reason IN ('risk_denied','order_failed')\n"
           "        OR (risk_allowed IS NULL AND skip_reason IN ('stop_width','rr_below_min','other','entry_gate_closed',\n"
           "                            'ml_filter',{_NEW_SKIPS_SQL}))));\n").replace("{_NEW_SKIPS_SQL}", _NEW_SKIPS_SQL)
    return d.replace(old, new)


def _migration_5_to_6(bot: str, now_s: str) -> str:
    """Sema 6 (DD-12 WP-06a): decision_events yeniden kurulur (CHECK gevsemesi); satirlar/id'ler korunur."""
    drops = "\n".join(f"DROP TRIGGER IF EXISTS trg_{t}_{k};" for t in _APPEND_ONLY_TABLES
                      for k in ("no_update", "no_delete"))
    cols = _DECISION_COLS_V3 + ", arm_id, session_tag, lesson_ids, source"
    return ("DROP VIEW IF EXISTS v_closed_trades;\nDROP VIEW IF EXISTS v_trades;\n"
            "DROP VIEW IF EXISTS v_decisions;\n" + drops + "\n"
            + _decision_events_ddl_v6("decision_events_v6") + "\n"
            f"INSERT INTO decision_events_v6 ({cols}) SELECT {cols} FROM decision_events;\n"
            "DROP TABLE decision_events;\n"
            "ALTER TABLE decision_events_v6 RENAME TO decision_events;\n"
            "CREATE UNIQUE INDEX ux_decision_key ON decision_events\n"
            "    (bot, pair, side, setup, trigger_tf, bar_close_ts) WHERE supersedes_id IS NULL;\n"
            "CREATE INDEX ix_decision_supersedes ON decision_events (supersedes_id);\n"
            + _V_DECISIONS + _VIEWS_V5 + "\n" + _trigger_ddl(_APPEND_ONLY_TABLES) + "\n")


def _migration_6_to_7(bot: str, now_s: str) -> str:
    """Sema 7 (etiket kurallari, 20 Kasim): skip_reason sozlugune etiket_rejim/etiket_duygu/etiket_kalabalik eklenir; decision_events
    yeniden kurulur (satirlar/id'ler korunur)."""
    return _migration_5_to_6(bot, now_s).replace("decision_events_v6", "decision_events_v7")


MIGRATIONS: list[Callable[[str, str], str]] = [_migration_0_to_1, _migration_1_to_2, _migration_2_to_3,
                                                _migration_3_to_4, _migration_4_to_5, _migration_5_to_6, _migration_6_to_7]
_FK_OFF_MIGRATIONS = frozenset({2, 4, 5, 6})     # tablo yeniden kurulan goclar (n -> n+1): FK denetimi islem disinda kapali


def _map_sqlite_error(e: sqlite3.Error) -> LedgerError:
    msg = str(e)
    low = msg.lower()
    if "not a database" in low or "malformed" in low:
        return LedgerSchemaError(f"bozuk veritabani dosyasi: {msg}")
    if "locked" in low or "busy" in low:
        return LedgerWriteError(msg, "locked")
    if "readonly" in low or "read-only" in low or "read only" in low:
        return LedgerWriteError(msg, "read_only")
    if "full" in low:
        return LedgerWriteError(msg, "disk_low")
    return LedgerWriteError(msg, "io_error")


def _health_code(e: LedgerError) -> str:
    if isinstance(e, LedgerWriteError):
        return e.code
    if isinstance(e, LedgerSchemaError):
        return "schema"
    return "io_error"


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def peek_meta(path, key: str) -> str | None:
    """DD-9 §9.4: `meta` tablosundan tek anahtarin SALT OKUNUR gozlemi. Goc, sema kurulumu, yazma YOK.
    Dosya yok ya da 0 bayt -> None; `meta` tablosu ya da satir yok -> None; okunamayan/bozuk dosya -> LedgerError."""
    p = os.fspath(path)
    try:
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            return None
    except OSError as e:
        raise LedgerError(f"defter okunamadi: {e}") from e
    try:
        conn = sqlite3.connect("file:" + quote(os.path.abspath(p)) + "?mode=ro", uri=True, timeout=5.0,
                               isolation_level=None)
    except sqlite3.Error as e:
        raise LedgerError(f"defter acilamadi: {e}") from e
    try:
        has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        if has is None:
            return None
        r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if r is None else r[0]
    except sqlite3.Error as e:
        raise LedgerError(f"defter meta okunamadi: {e}") from e
    finally:
        conn.close()


def open_ledger(path, bot: str, *, create: bool = True, read_only: bool = False,
                migrate: bool | None = None, clock: Callable[[], datetime] | None = None,
                min_evidence_trades: int = 20, paper_lesson: bool = False) -> "Ledger":
    return Ledger(path, bot, create=create, read_only=read_only, migrate=migrate, clock=clock,
                  min_evidence_trades=min_evidence_trades, paper_lesson=paper_lesson)


def open_migrated_copy(src, dst, bot: str) -> "Ledger":
    """Kaynak defteri (salt okunur) `dst`'ye kopyalar ve YALNIZ kopyayi gocurur; kaynak asla degismez.
    Eski semali (or. backtest kosusu) defterleri okumak icin."""
    import sqlite3
    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
    finally:
        s.close()
        d.close()
    return Ledger(dst, bot, create=False, migrate=True)


class Ledger:
    def __init__(self, path, bot: str, *, create: bool = True, read_only: bool = False,
                 migrate: bool | None = None, clock: Callable[[], datetime] | None = None,
                 min_evidence_trades: int = 20, paper_lesson: bool = False):
        if bot not in BOTS:
            raise LedgerValidationError("bot 'learner' veya 'twin' olmali")
        if not isinstance(paper_lesson, bool):
            raise LedgerValidationError("paper_lesson bool olmali")
        # DD-12 WP-08 (kagit): `paper_lesson=True` => kanit esigi 0 olabilir, haftalik sinir ve vol_ratio_max artirimi
        # onay kurali yoktur (ders ilk islemden etkin, esiksiz). Varsayilan (testnet/canli) davranis aynen.
        if isinstance(min_evidence_trades, bool) or not isinstance(min_evidence_trades, int) \
                or min_evidence_trades < (0 if paper_lesson else 20):
            raise LedgerValidationError("min_evidence_trades >= 20 olmali")
        self.paper_lesson = paper_lesson
        self.bot = bot
        self.min_evidence_trades = min_evidence_trades
        self.path = os.fspath(path)
        self.read_only = bool(read_only)
        self._create = bool(create)
        self._migrate = (not self.read_only) if migrate is None else bool(migrate)
        if self.read_only:
            self._migrate = False
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._local = threading.local()
        self._conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        self._spool_lock = threading.RLock()
        self._closed = False
        self._degraded = False
        self._last_write_ok: datetime | None = None
        self._last_degraded_attempt: datetime | None = None
        self._unledgered: list[int] = []

        if (self.read_only or not self._create) and not os.path.exists(self.path):
            raise LedgerSchemaError("defter dosyasi yok")
        conn = self._connect()
        self._local.conn = conn
        try:
            self._setup_schema(conn)
        except BaseException:
            self.close()
            raise
        self._degraded = self._spool_pending()

    # -- baglanti ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        try:
            if self.read_only:
                uri = "file:" + quote(os.path.abspath(self.path)) + "?mode=ro"
                conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None,
                                       check_same_thread=False)
            else:
                conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None,
                                       check_same_thread=False)
        except sqlite3.Error as e:
            raise _map_sqlite_error(e) from e
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=5000")
            if not self.read_only:
                conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as e:
            conn.close()
            raise _map_sqlite_error(e) from e
        with self._conns_lock:
            self._conns.append(conn)
        return conn

    def _conn(self) -> sqlite3.Connection:
        if self._closed:
            raise LedgerStateError("defter kapali")
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._connect()
            try:
                self._verify(c)
            except BaseException:
                c.close()
                raise
            self._local.conn = c
        return c

    def close(self) -> None:
        self._closed = True
        with self._conns_lock:
            conns, self._conns = self._conns, []
        for c in conns:
            with contextlib.suppress(Exception):
                c.close()
        self._local = threading.local()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- sema --------------------------------------------------------------

    def _setup_schema(self, conn: sqlite3.Connection) -> None:
        try:
            uv = conn.execute("PRAGMA user_version").fetchone()[0]
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        except sqlite3.Error as e:
            raise _map_sqlite_error(e) from e
        if uv > SCHEMA_VERSION:
            raise LedgerSchemaError(f"sema surumu ({uv}) koddan yeni ({SCHEMA_VERSION})")
        if not tables and uv == 0:
            if self.read_only or not self._create:
                raise LedgerSchemaError("defterde sema yok")
            self._run_migrations(conn, 0)
        elif uv < SCHEMA_VERSION:
            if not self._migrate:
                raise LedgerSchemaError(f"sema surumu eski ({uv}); migrate=False")
            if uv < 1 or uv > len(MIGRATIONS):
                raise LedgerSchemaError(f"bilinmeyen eski sema surumu ({uv})")
            self.backup(self._premigrate_dest(uv))
            self._run_migrations(conn, uv)
        self._verify(conn)

    def _premigrate_dest(self, uv: int) -> str:
        """Goc oncesi yedek yolu. Yarida kesilen gocun yeniden denemesinde onceki yedek ezilmez ve atlanmaz:
        ayni surum icin yeni, sonek numarali yedek yazilir (`.premigrate-v4`, `.premigrate-v4.1`, ...)."""
        base = f"{self.path}.premigrate-v{uv}"
        dest, n = base, 0
        while os.path.exists(dest):
            n += 1
            dest = f"{base}.{n}"
        return dest

    def _run_migrations(self, conn: sqlite3.Connection, from_v: int) -> None:
        now_s = _fmt_ts(self._now())
        for n in range(from_v, SCHEMA_VERSION):
            fk_off = n in _FK_OFF_MIGRATIONS
            sql = (("PRAGMA foreign_keys=OFF;\n" if fk_off else "")
                   + "BEGIN IMMEDIATE;\n" + MIGRATIONS[n](self.bot, now_s)
                   + (f"INSERT INTO schema_migrations (from_version, to_version, applied_at) "
                      f"VALUES ({n}, {n + 1}, '{now_s}');\n" if True else "")
                   + f"PRAGMA user_version={n + 1};\nCOMMIT;")
            try:
                conn.executescript(sql)
                if fk_off:
                    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
                    if bad:
                        raise LedgerSchemaError(f"goc {n}->{n + 1} sonrasi yabanci anahtar ihlali: {len(bad)} satir")
            except sqlite3.Error as e:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
                raise _map_sqlite_error(e) from e
            finally:
                if fk_off:
                    with contextlib.suppress(sqlite3.Error):
                        conn.execute("PRAGMA foreign_keys=ON")

    def _verify(self, conn: sqlite3.Connection) -> None:
        try:
            uv = conn.execute("PRAGMA user_version").fetchone()[0]
            if uv != SCHEMA_VERSION:
                raise LedgerSchemaError(f"sema surumu {uv}, beklenen {SCHEMA_VERSION}")
            meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM meta")}
            trig = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            mig = conn.execute("SELECT MAX(to_version) FROM schema_migrations").fetchone()[0]
        except sqlite3.Error as e:
            raise LedgerSchemaError(f"sema okunamadi: {e}") from e
        if meta.get("bot") != self.bot:
            raise LedgerSchemaError(f"bot uyusmazligi: dosya={meta.get('bot')!r} istenen={self.bot!r}")
        mirror = max(int(meta.get("schema_version", "0")), int(mig or 0))
        if mirror != uv:
            raise LedgerSchemaError("meta.schema_version ile user_version farkli")
        missing = _EXPECTED_TRIGGERS - trig
        if missing:
            raise LedgerSchemaError(f"eksik tetikleyici: {sorted(missing)[:3]}")

    # -- ortak -------------------------------------------------------------

    def _now(self) -> datetime:
        d = self._clock()
        if not isinstance(d, datetime):
            raise LedgerWriteError("clock datetime dondurmedi")
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)

    def _require_writable(self) -> None:
        if self._closed:
            raise LedgerStateError("defter kapali")
        if self.read_only:
            raise LedgerStateError("defter salt okunur")

    def _require_learner(self) -> None:
        if self.bot == "twin":
            raise LedgerStateError("ikiz botta bu islem yasak")

    @contextlib.contextmanager
    def _tx(self):
        c = self._conn()
        try:
            c.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as e:
            raise _map_sqlite_error(e) from e
        try:
            yield c
            c.execute("COMMIT")
        except sqlite3.Error as e:
            with contextlib.suppress(sqlite3.Error):
                c.execute("ROLLBACK")
            raise _map_sqlite_error(e) from e
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                c.execute("ROLLBACK")
            raise

    @contextlib.contextmanager
    def _read(self):
        c = self._conn()
        try:
            c.execute("BEGIN")
        except sqlite3.Error as e:
            raise _map_sqlite_error(e) from e
        try:
            yield c
        except sqlite3.Error as e:
            raise _map_sqlite_error(e) from e
        finally:
            with contextlib.suppress(sqlite3.Error):
                c.execute("ROLLBACK")

    @staticmethod
    def _insert(c, table: str, vals: Mapping[str, Any]) -> int:
        cols = list(vals)
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
        return c.execute(sql, [vals[k] for k in cols]).lastrowid

    @staticmethod
    def _active_row(c, bot: str):
        return c.execute(
            "SELECT a.id AS act_id, a.version_id AS version_id, a.activated_at AS activated_at "
            "FROM param_activations a WHERE a.bot=? ORDER BY a.id DESC LIMIT 1", (bot,)).fetchone()

    def _on_write_failure(self) -> None:
        self._degraded = True
        # the failed write counts as the latest probe: retry only after >=30 s
        self._last_degraded_attempt = self._now()

    # -- karar -------------------------------------------------------------

    def record_decision(self, ev: DecisionEvent) -> int:
        self._require_writable()
        now = self._now()
        vals, sup = self._prep_decision(ev, now)
        try:
            with self._tx() as c:
                return self._write_decision(c, vals, sup, now)
        except LedgerWriteError:
            self._on_write_failure()
            raise

    def _prep_decision(self, ev, now: datetime):
        if not isinstance(ev, DecisionEvent):
            raise LedgerValidationError("DecisionEvent bekleniyor")
        bar = _to_utc(ev.bar_close_ts, "bar_close_ts")
        if bar.second or bar.microsecond or bar.minute % 15:
            raise LedgerValidationError("bar_close_ts 15 dakikanin tam kati olmali")
        if bar > now + timedelta(seconds=5):
            raise LedgerValidationError("bar_close_ts gelecekte")
        tf = _choice(ev.trigger_tf, "trigger_tf", _TRIGGER_TFS)
        pair, side = _norm_pair(ev.pair), _norm_side(ev.side)
        setup = _setup_code(ev.setup)
        regime = _choice(ev.regime, "regime", _REGIMES)
        atr_ratio = _opt_num(ev.atr_ratio, "atr_ratio")
        rh, rl = _opt_num(ev.rh, "rh"), _opt_num(ev.rl, "rl")
        if regime == "range":
            if rh is None or rl is None:
                raise LedgerValidationError("regime=range iken rh ve rl dolu olmali")
        elif rh is not None or rl is not None:
            raise LedgerValidationError("range disinda rh/rl NULL olmali")
        rht, rlt = _int(ev.rh_touches, "rh_touches", minimum=0), _int(ev.rl_touches, "rl_touches", minimum=0)
        feats = self._prep_features(ev.features, setup)
        pe, ps = _num(ev.planned_entry, "planned_entry"), _num(ev.planned_stop, "planned_stop")
        pt = _opt_num(ev.planned_target, "planned_target")
        if setup == "R1" and pt is None:
            raise LedgerValidationError("R1'de planned_target dolu olmali")
        if setup == "T1" and pt is not None:
            raise LedgerValidationError("T1'de planned_target NULL olmali")
        pvid = _int(ev.param_version_id, "param_version_id", minimum=1)
        veto = _choice(ev.veto_status, "veto_status", _VETO)
        veto_reason = _text(ev.veto_reason, "veto_reason")
        if ev.risk_allowed is not None and not isinstance(ev.risk_allowed, bool):
            raise LedgerValidationError("risk_allowed bool veya None olmali")
        ra = None if ev.risk_allowed is None else int(ev.risk_allowed)
        risk_reason = _text(ev.risk_reason, "risk_reason")
        sq, sn = _opt_num(ev.size_qty, "size_qty"), _opt_num(ev.size_notional, "size_notional")
        sm, sr = _opt_num(ev.size_margin, "size_margin"), _opt_num(ev.size_risk_amount, "size_risk_amount")
        lev = _opt_int(ev.leverage, "leverage", minimum=1)
        final = _choice(ev.final_action, "final_action", ("entered", "skipped"))
        skip = ev.skip_reason
        if skip is not None:
            skip = _choice(skip, "skip_reason", _SKIP)
        sup = None if ev.supersedes_id is None else _int(ev.supersedes_id, "supersedes_id", minimum=1)
        ml_score = _opt_num(ev.ml_score, "ml_score")
        if ml_score is not None and not 0.0 <= ml_score <= 1.0:
            raise LedgerValidationError("ml_score [0,1] araliginda olmali")
        arm_id = ev.arm_id
        if arm_id is None:
            arm_id = f"{setup}@{tf}"
        elif not isinstance(arm_id, str) or not arm_id.strip() or len(arm_id) > 32:
            raise LedgerValidationError("arm_id bos olmayan kisa metin olmali")
        session_tag = _opt_choice(ev.session_tag, "session_tag", _SESSION_TAGS)
        lesson_ids = _lesson_ids_json(ev.lesson_ids)
        source = _choice(ev.source, "source", _SOURCES)
        sizes = (sq, sn, sm, sr, lev)
        if ra == 1 and any(s is None for s in sizes):
            raise LedgerValidationError("risk_allowed=True iken size_* ve leverage dolu olmali")
        if final == "entered":
            if veto not in ("allowed", "not_evaluated") or ra != 1 or skip is not None:
                raise LedgerValidationError("entered => veto allowed|not_evaluated, risk_allowed True, skip_reason NULL")
        else:
            if skip is None:
                raise LedgerValidationError("skipped => skip_reason zorunlu")
        if veto in ("blocked", "missing", "stale"):
            if final != "skipped" or skip != f"veto_{veto}":
                raise LedgerValidationError(f"veto_status={veto} => skipped ve skip_reason=veto_{veto}")
        if skip in ("veto_blocked", "veto_missing", "veto_stale") and veto != skip[5:]:
            raise LedgerValidationError("skip_reason veto_status ile uyumsuz")
        if ra == 0 and (final != "skipped" or skip != "risk_denied"):
            raise LedgerValidationError("risk_allowed=False => skipped, skip_reason=risk_denied")
        if skip in _NEW_SKIP and veto != "not_evaluated":
            raise LedgerValidationError(f"skip_reason={skip} => veto_status='not_evaluated' (veto kagit botta yok)")
        if veto == "not_evaluated" and ra is not None and not (
                final == "entered" or skip in ("risk_denied", "order_failed")):
            raise LedgerValidationError("not_evaluated + risk_allowed dolu => entered | risk_denied | order_failed")
        if veto == "not_evaluated" and ra is None and skip not in _NOT_EVAL_SKIP:
            raise LedgerValidationError("not_evaluated => risk_allowed None, skip_reason stop_width/rr_below_min/other")
        vals = dict(bar_close_ts=_fmt_ts(bar), trigger_tf=tf, pair=pair, side=side, setup=setup, regime=regime,
                    atr_ratio=atr_ratio, rh=rh, rl=rl, rh_touches=rht, rl_touches=rlt, features=feats,
                    planned_entry=pe, planned_stop=ps, planned_target=pt, param_version_id=pvid,
                    veto_status=veto, veto_reason=veto_reason, risk_allowed=ra, risk_reason=risk_reason,
                    size_qty=sq, size_notional=sn, size_margin=sm, size_risk_amount=sr, leverage=lev,
                    final_action=final, skip_reason=skip, ml_score=ml_score,
                    arm_id=arm_id, session_tag=session_tag, lesson_ids=lesson_ids, source=source)
        return vals, sup

    @staticmethod
    def _prep_features(features, setup: str) -> str:
        if not isinstance(features, Mapping):
            raise LedgerValidationError("features Mapping olmali")
        req = ["stop_dist_atr", "atr_4h"]
        if "atr_1h" not in features and "atr_tf" not in features:
            raise LedgerValidationError("features: atr_1h (veya atr_tf) eksik")
        if setup == "T1":
            req += ["pullback_ema", "ema_value", "body_ratio"]
        elif setup == "R1":
            req += ["wick_ratio", "rr", "edge_dist_atr"]
        for k in req:
            if k not in features:
                raise LedgerValidationError(f"features: {k} eksik")
            _num(features[k], f"features.{k}")
        clean = {}
        for k, v in features.items():
            if not isinstance(k, str):
                raise LedgerValidationError("features anahtarlari metin olmali")
            if isinstance(v, float) and not math.isfinite(v):
                raise LedgerValidationError(f"features.{k} sonlu olmali")
            if k in _ETIKET_ANAHTARLARI and isinstance(v, Mapping):      # haber/duygu etiketi (yalniz kayit): ic ice sozluk
                v = json.loads(_json_limited(v, f"features.{k}"))
            elif v is not None and not isinstance(v, (str, int, float, bool)):
                if isinstance(v, numbers.Real):
                    v = float(v)
                else:
                    raise LedgerValidationError(f"features.{k} turu gecersiz")
            clean[k] = v
        return _json_limited(clean, "features")

    _DECISION_CMP = ("bar_close_ts", "trigger_tf", "pair", "side", "setup", "regime", "atr_ratio", "rh", "rl",
                     "rh_touches", "rl_touches", "features", "planned_entry", "planned_stop", "planned_target",
                     "param_version_id", "veto_status", "veto_reason", "risk_allowed", "risk_reason",
                     "size_qty", "size_notional", "size_margin", "size_risk_amount", "leverage",
                     "final_action", "skip_reason", "arm_id", "session_tag", "lesson_ids", "source")

    @staticmethod
    def _cmp_deger(k: str, v):
        """Ayni-karar karsilastirmasi: `features` icindeki yalniz-kayit etiketleri (haber/duygu: onbellek saatlik degisir) sayilmaz;
        boylece etiket, yeniden denenen ayni kararin cakisma sonucunu degistiremez."""
        if k != "features" or not isinstance(v, str):
            return v
        try:
            d = json.loads(v)
        except ValueError:
            return v
        return {a: b for a, b in d.items() if a not in _ETIKET_ANAHTARLARI} if isinstance(d, dict) else v

    def _write_decision(self, c, vals, sup, now: datetime) -> int:
        bot = self.bot
        if not c.execute("SELECT 1 FROM param_versions WHERE id=? AND bot=?",
                         (vals["param_version_id"], bot)).fetchone():
            raise LedgerValidationError("param_version_id mevcut degil")

        def same(row) -> bool:
            return all(self._cmp_deger(k, row[k]) == self._cmp_deger(k, vals[k]) for k in self._DECISION_CMP)

        if sup is None:
            row = c.execute(
                "SELECT * FROM decision_events WHERE bot=? AND pair=? AND side=? AND setup=? AND trigger_tf=? "
                "AND bar_close_ts=? AND supersedes_id IS NULL",
                (bot, vals["pair"], vals["side"], vals["setup"], vals["trigger_tf"], vals["bar_close_ts"])
            ).fetchone()
            if row is not None:
                if same(row):
                    return row["id"]
                raise LedgerConflictError("ayni mum/kurulum icin farkli icerik; duzeltme icin supersedes_id kullanin")
        else:
            target = c.execute("SELECT id FROM decision_events WHERE id=? AND bot=?", (sup, bot)).fetchone()
            if target is None:
                raise LedgerValidationError("supersedes_id mevcut degil")
            row = c.execute("SELECT * FROM decision_events WHERE supersedes_id=? AND bot=?", (sup, bot)).fetchone()
            if row is not None:
                if same(row):
                    return row["id"]
                raise LedgerConflictError("bu karar zaten farkli icerikle duzeltilmis")
        act = c.execute("SELECT MAX(id) FROM param_activations WHERE bot=?", (bot,)).fetchone()[0]
        return self._insert(c, "decision_events", dict(vals, bot=bot, activation_id=act, supersedes_id=sup,
                                                       recorded_at=_fmt_ts(now)))

    # -- islem girisi / cikisi ----------------------------------------------

    def record_trade_entry(self, e: TradeEntry) -> int:
        self._require_writable()
        return self._record_entry(e, spool=True)

    def _record_entry(self, e: TradeEntry, *, spool: bool) -> int:
        if not isinstance(e, TradeEntry):
            raise LedgerValidationError("TradeEntry bekleniyor")
        now = self._now()
        tid = _int(e.trade_id, "trade_id")
        did = _int(e.decision_id, "decision_id", minimum=1)
        ets = _ts(e.entry_ts, "entry_ts")
        price, qty = _num(e.entry_price, "entry_price"), _num(e.qty, "qty")
        if price <= 0 or qty <= 0:
            raise LedgerValidationError("entry_price ve qty > 0 olmali")
        lev = _int(e.leverage, "leverage", minimum=1)
        fee = _num(e.fee_entry, "fee_entry")
        if fee < 0:
            raise LedgerValidationError("fee_entry >= 0 olmali")
        sup = None if e.supersedes_id is None else _int(e.supersedes_id, "supersedes_id", minimum=1)
        ex = _prep_exec(e, exit_=False)
        try:
            with self._tx() as c:
                return self._write_entry(c, tid, did, ets, price, qty, lev, fee, sup, now, ex)
        except LedgerWriteError:
            self._on_write_failure()
            if spool:
                self._spool_append({"type": "entry", "trade_id": tid, "decision_id": did, "entry_ts": ets,
                                    "entry_price": price, "qty": qty, "leverage": lev, "fee_entry": fee,
                                    "supersedes_id": sup, **ex})
            raise

    def _write_entry(self, c, tid, did, ets, price, qty, lev, fee, sup, now, ex=None) -> int:
        bot = self.bot
        d = c.execute("SELECT * FROM decision_events WHERE id=? AND bot=?", (did, bot)).fetchone()
        if d is None:
            raise LedgerValidationError("decision_id mevcut degil")
        if d["final_action"] != "entered":
            raise LedgerValidationError("karar final_action='entered' olmali")
        risk = d["size_risk_amount"]
        if risk is None or risk <= 0:
            raise LedgerValidationError("planned_risk (size_risk_amount) > 0 olmali")
        side = d["side"]
        pe = d["planned_entry"]
        slip = (price - pe) / pe if side == "long" else (pe - price) / pe
        cmp_keys = ("decision_id", "entry_ts", "entry_price", "qty", "leverage", "fee_entry")
        want = dict(decision_id=did, entry_ts=ets, entry_price=price, qty=qty, leverage=lev, fee_entry=fee)

        def same(row):
            return all(row[k] == want[k] for k in cmp_keys)

        if sup is None:
            row = c.execute("SELECT * FROM trade_entries WHERE bot=? AND trade_id=? AND supersedes_id IS NULL",
                            (bot, tid)).fetchone()
            if row is not None:
                if same(row):
                    return row["id"]
                raise LedgerConflictError("trade_id icin farkli giris zaten var")
        else:
            t = c.execute("SELECT * FROM trade_entries WHERE id=? AND bot=?", (sup, bot)).fetchone()
            if t is None or t["trade_id"] != tid:
                raise LedgerValidationError("supersedes_id bu trade_id icin mevcut bir giris olmali")
            row = c.execute("SELECT * FROM trade_entries WHERE supersedes_id=? AND bot=?", (sup, bot)).fetchone()
            if row is not None:
                if same(row):
                    return row["id"]
                raise LedgerConflictError("bu giris zaten farkli icerikle duzeltilmis")
        other = c.execute(
            "SELECT trade_id FROM trade_entries e WHERE e.bot=? AND e.decision_id=? AND e.trade_id<>? "
            "AND NOT EXISTS (SELECT 1 FROM trade_entries s WHERE s.supersedes_id=e.id)", (bot, did, tid)).fetchone()
        if other is not None:
            raise LedgerConflictError("karar baska bir trade_id'ye bagli")
        return self._insert(c, "trade_entries", dict(
            bot=bot, trade_id=tid, decision_id=did, param_version_id=d["param_version_id"],
            activation_id=d["activation_id"], pair=d["pair"], side=side, setup=d["setup"], entry_ts=ets,
            entry_price=price, planned_entry=pe, planned_stop=d["planned_stop"],
            planned_target=d["planned_target"], qty=qty, leverage=lev, planned_risk=risk, fee_entry=fee,
            slippage_entry=slip, supersedes_id=sup, recorded_at=_fmt_ts(now),
            arm_id=d["arm_id"], session_tag=d["session_tag"], **(ex or {})))

    def record_trade_exit(self, x: TradeExit) -> int:
        self._require_writable()
        return self._record_exit(x, spool=True)

    def _record_exit(self, x: TradeExit, *, spool: bool) -> int:
        if not isinstance(x, TradeExit):
            raise LedgerValidationError("TradeExit bekleniyor")
        now = self._now()
        tid = _int(x.trade_id, "trade_id")
        xts = _ts(x.exit_ts, "exit_ts")
        price = _num(x.exit_price, "exit_price")
        if price <= 0:
            raise LedgerValidationError("exit_price > 0 olmali")
        reason = _choice(x.exit_reason, "exit_reason", _EXIT_REASONS)
        pex = _opt_num(x.planned_exit, "planned_exit")
        if pex is not None and pex <= 0:
            raise LedgerValidationError("planned_exit > 0 olmali")
        fee = _num(x.fee_exit, "fee_exit")
        if fee < 0:
            raise LedgerValidationError("fee_exit >= 0 olmali")
        fund = _num(x.funding_paid, "funding_paid")
        sup = None if x.supersedes_id is None else _int(x.supersedes_id, "supersedes_id", minimum=1)
        mfp = _opt_num(x.max_favorable_price, "max_favorable_price")
        map_ = _opt_num(x.max_adverse_price, "max_adverse_price")
        etf = x.excursion_tf
        given = [mfp is not None, map_ is not None, etf is not None]
        if any(given) and not all(given):
            raise LedgerValidationError(
                "max_favorable_price, max_adverse_price ve excursion_tf birlikte verilmeli ya da birlikte None")
        if etf is not None:
            _choice(etf, "excursion_tf", _EXCURSION_TFS)
            if mfp <= 0 or map_ <= 0:
                raise LedgerValidationError("uc fiyatlar > 0 olmali")
        ex = _prep_exec(x, exit_=True)
        leg = _opt_num(x.leg_exit_price, "leg_exit_price")
        if leg is not None and leg <= 0:
            raise LedgerValidationError("leg_exit_price > 0 olmali")
        try:
            with self._tx() as c:
                return self._write_exit(c, tid, xts, price, reason, pex, fee, fund, sup, now,
                                        mfp, map_, etf, ex, leg)
        except LedgerWriteError:
            self._on_write_failure()
            if spool:
                self._spool_append({"type": "exit", "trade_id": tid, "exit_ts": xts, "exit_price": price,
                                    "exit_reason": reason, "planned_exit": pex, "fee_exit": fee,
                                    "funding_paid": fund, "supersedes_id": sup,
                                    "max_favorable_price": mfp, "max_adverse_price": map_,
                                    "excursion_tf": etf, "leg_exit_price": leg, **ex})
            raise

    def _write_exit(self, c, tid, xts, price, reason, pex, fee, fund, sup, now,
                    mfp=None, map_=None, etf=None, ex=None, leg=None) -> int:
        bot = self.bot
        ent = c.execute(
            "SELECT * FROM trade_entries e WHERE e.bot=? AND e.trade_id=? "
            "AND NOT EXISTS (SELECT 1 FROM trade_entries s WHERE s.supersedes_id=e.id)", (bot, tid)).fetchone()
        if ent is None:
            raise LedgerValidationError("trade_id icin gecerli bir giris yok")
        if xts < ent["entry_ts"]:
            raise LedgerValidationError("exit_ts >= entry_ts olmali")
        q, ep, side = ent["qty"], ent["entry_price"], ent["side"]
        mfe = mae = None
        if etf is not None:
            if side == "long":
                if mfp < max(ep, price) or map_ > min(ep, price):
                    raise LedgerValidationError("uc fiyat gerceklesen fiyatlardan daha ilimli olamaz")
                sgn = 1.0
            else:
                if mfp > min(ep, price) or map_ < max(ep, price):
                    raise LedgerValidationError("uc fiyat gerceklesen fiyatlardan daha ilimli olamaz")
                sgn = -1.0
            risk = ent["planned_risk"]
            mfe = round(max(0.0, sgn * (mfp - ep) * q / risk), 6)
            mae = round(max(0.0, sgn * (ep - map_) * q / risk), 6)
        bars = (_parse_ts(xts) - _EPOCH) // _BAR - (_parse_ts(ent["entry_ts"]) - _EPOCH) // _BAR
        want = dict(exit_ts=xts, exit_price=price, exit_reason=reason, planned_exit=pex, fee_exit=fee,
                    funding_paid=fund, mfe_r=mfe, mae_r=mae, bars_held=bars, excursion_tf=etf)

        def same(row):
            return all(row[k] == v for k, v in want.items())

        if sup is None:
            row = c.execute("SELECT * FROM trade_exits WHERE bot=? AND trade_id=? AND supersedes_id IS NULL",
                            (bot, tid)).fetchone()
            if row is not None:
                if same(row):
                    return row["id"]
                raise LedgerConflictError("islem baska bir cikisla zaten kapali")
        else:
            t = c.execute("SELECT * FROM trade_exits WHERE id=? AND bot=?", (sup, bot)).fetchone()
            if t is None or t["trade_id"] != tid:
                raise LedgerValidationError("supersedes_id bu trade_id icin mevcut bir cikis olmali")
            row = c.execute("SELECT * FROM trade_exits WHERE supersedes_id=? AND bot=?", (sup, bot)).fetchone()
            if row is not None:
                if same(row):
                    return row["id"]
                raise LedgerConflictError("bu cikis zaten farkli icerikle duzeltilmis")
        gross = q * (price - ep) if side == "long" else q * (ep - price)
        realized = gross - ent["fee_entry"] - fee - fund
        r = realized / ent["planned_risk"]
        slip = None
        if pex is not None:
            sp = price if leg is None else leg          # kismi cikista kayma SON bacagin dolumundan (karma fiyattan degil)
            slip = (pex - sp) / pex if side == "long" else (sp - pex) / pex
        return self._insert(c, "trade_exits", dict(
            bot=bot, trade_id=tid, exit_ts=xts, exit_price=price, exit_reason=reason, planned_exit=pex,
            fee_exit=fee, funding_paid=fund, gross_pnl=gross, realized_pnl=realized, r_multiple=r,
            slippage_exit=slip, mfe_r=mfe, mae_r=mae, bars_held=bars, excursion_tf=etf,
            supersedes_id=sup, recorded_at=_fmt_ts(now), **(ex or {})))

    # -- islem notlari (sema 5) ---------------------------------------------

    def record_trade_note(self, trade_id: int, note_date: str, tags: Sequence[str], text: str,
                          model: str | None = None, cost_usd: float | None = None) -> int:
        """Gece notu satiri. Islem defterde (v_trades) var olmali; etiket sozlugu bu katmanda denetlenmez."""
        self._require_writable()
        tid = _int(trade_id, "trade_id")
        if not isinstance(note_date, str) or not re.fullmatch(r"\d{4}-\d\d-\d\d", note_date):
            raise LedgerValidationError("note_date YYYY-AA-GG olmali")
        if isinstance(tags, (str, bytes)) or not isinstance(tags, Iterable):
            raise LedgerValidationError("tags metin listesi olmali")
        tl = list(tags)
        if not all(isinstance(t, str) and t.strip() for t in tl):
            raise LedgerValidationError("tags ogeleri bos olmayan metin olmali")
        if not isinstance(text, str) or not text.strip():
            raise LedgerValidationError("text bos olmayan metin olmali")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            raise LedgerValidationError("model bos olmayan metin ya da None olmali")
        cost = _opt_num(cost_usd, "cost_usd")
        if cost is not None and cost < 0:
            raise LedgerValidationError("cost_usd >= 0 olmali")
        tags_j = _json_limited(tl, "tags")
        try:
            with self._tx() as c:
                if c.execute("SELECT 1 FROM trade_entries WHERE bot=? AND trade_id=?", (self.bot, tid)).fetchone() is None:
                    raise LedgerValidationError("trade_id icin islem yok")
                return self._insert(c, "trade_notes", dict(trade_id=tid, note_date=note_date, tags=tags_j,
                                                           text=text, model=model, cost_usd=cost))
        except LedgerWriteError:
            self._on_write_failure()
            raise

    def list_trade_notes(self, trade_id: int | None = None) -> list[dict]:
        sql, args = "SELECT * FROM trade_notes", []
        if trade_id is not None:
            sql += " WHERE trade_id=?"
            args.append(_int(trade_id, "trade_id"))
        with self._read() as c:
            rows = c.execute(sql + " ORDER BY id", args).fetchall()
        return [dict(id=r["id"], trade_id=r["trade_id"], note_date=r["note_date"], tags=json.loads(r["tags"]),
                     text=r["text"], model=r["model"], cost_usd=r["cost_usd"]) for r in rows]

    # -- golge karar satirlari ve oz varlik isaretleri (sema 4) -----------------
    # Spec 5.5 / 0.3: LedgerWriteError'da `_on_write_failure` CAGRILMAZ, spool'a yazilmaz, basarida
    # `_last_write_ok` GUNCELLENMEZ: bu kayitlar islem yolunun sagligini etkilemez.

    def record_shadow(self, ev: ShadowEvent) -> int:
        self._require_writable()
        if not isinstance(ev, ShadowEvent):
            raise LedgerValidationError("ShadowEvent bekleniyor")
        now = self._now()
        block = _choice(ev.block, "block", _SHADOW_BLOCKS)
        bar = _to_utc(ev.bar_close_ts, "bar_close_ts")
        if bar.second or bar.microsecond or bar.minute % 15:
            raise LedgerValidationError("bar_close_ts 15 dakikanin tam kati olmali")
        if bar > now + timedelta(seconds=5):
            raise LedgerValidationError("bar_close_ts gelecekte")
        tf = _choice(ev.trigger_tf, "trigger_tf", _SHADOW_TFS)
        pair, side = _norm_pair(ev.pair), _norm_side(ev.side)
        setup = _choice(ev.setup, "setup", _SETUPS)
        regime = _choice(ev.regime, "regime", _REGIMES)
        atr_ratio = _opt_num(ev.atr_ratio, "atr_ratio")
        rh, rl = _opt_num(ev.rh, "rh"), _opt_num(ev.rl, "rl")
        feats = self._prep_features(ev.features, setup)
        pe, ps = _num(ev.planned_entry, "planned_entry"), _num(ev.planned_stop, "planned_stop")
        pt = _opt_num(ev.planned_target, "planned_target")
        if pe <= 0 or ps <= 0:
            raise LedgerValidationError("planned_entry ve planned_stop > 0 olmali")
        if (side == "long" and not ps < pe) or (side == "short" and not ps > pe):
            raise LedgerValidationError("planned_stop yon ile uyumsuz")
        pvid = _int(ev.param_version_id, "param_version_id", minimum=1)
        strategy = _text(ev.strategy, "strategy", required=True)
        reasons = _text(ev.reasons if ev.reasons is not None else "", "reasons", limit=10 ** 9)
        reasons = reasons[:MAX_REASON]
        if not isinstance(ev.pos_open, (bool, int)) or ev.pos_open not in (0, 1):
            raise LedgerValidationError("pos_open bool olmali")
        gate = _text(ev.gate_code, "gate_code")
        vals = dict(bot=self.bot, block=block, bar_close_ts=_fmt_ts(bar), trigger_tf=tf, pair=pair, side=side,
                    setup=setup, regime=regime, atr_ratio=atr_ratio, rh=rh, rl=rl, features=feats,
                    planned_entry=pe, planned_stop=ps, planned_target=pt, param_version_id=pvid,
                    strategy=strategy, reasons=reasons, pos_open=int(ev.pos_open), gate_code=gate,
                    recorded_at=_fmt_ts(now))
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM param_versions WHERE id=? AND bot=?", (pvid, self.bot)).fetchone():
                raise LedgerValidationError("param_version_id mevcut degil")
            row = c.execute(
                "SELECT id FROM shadow_decisions WHERE bot=? AND block=? AND pair=? AND side=? AND setup=? "
                "AND trigger_tf=? AND bar_close_ts=?",
                (self.bot, block, pair, side, setup, tf, vals["bar_close_ts"])).fetchone()
            if row is not None:
                return row["id"]
            return self._insert(c, "shadow_decisions", vals)

    @staticmethod
    def _shadow_from(r) -> ShadowRecord:
        return ShadowRecord(
            block=r["block"], bar_close_ts=_parse_ts(r["bar_close_ts"]), trigger_tf=r["trigger_tf"],
            pair=r["pair"], side=r["side"], setup=r["setup"], regime=r["regime"], atr_ratio=r["atr_ratio"],
            rh=r["rh"], rl=r["rl"], features=MappingProxyType(json.loads(r["features"])),
            planned_entry=r["planned_entry"], planned_stop=r["planned_stop"], planned_target=r["planned_target"],
            param_version_id=r["param_version_id"], strategy=r["strategy"], reasons=r["reasons"],
            pos_open=bool(r["pos_open"]), gate_code=r["gate_code"], id=r["id"], bot=r["bot"],
            recorded_at=_parse_ts(r["recorded_at"]))

    def list_shadow(self, *, since_ts: datetime | None = None, until_ts: datetime | None = None,
                    block: str | None = None, limit: int | None = None) -> list[ShadowRecord]:
        where, args = ["bot=?"], [self.bot]
        if since_ts is not None:
            where.append("bar_close_ts>=?")
            args.append(_ts(since_ts, "since_ts"))
        if until_ts is not None:
            where.append("bar_close_ts<?")
            args.append(_ts(until_ts, "until_ts"))
        if block is not None:
            where.append("block=?")
            args.append(_choice(block, "block", _SHADOW_BLOCKS))
        sql = f"SELECT * FROM v_shadow_decisions WHERE {' AND '.join(where)} ORDER BY bar_close_ts, id"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(_int(limit, "limit", minimum=0))
        with self._read() as c:
            rows = c.execute(sql, args).fetchall()
        return [self._shadow_from(r) for r in rows]

    def record_equity_mark(self, m: EquityMark) -> int:
        self._require_writable()
        if not isinstance(m, EquityMark):
            raise LedgerValidationError("EquityMark bekleniyor")
        now = self._now()
        ts = _ts(m.ts, "ts")
        wallet, eq, low = _num(m.wallet, "wallet"), _num(m.equity, "equity"), _num(m.equity_low, "equity_low")
        if low > eq:
            raise LedgerValidationError("equity_low <= equity olmali")
        n_open = _int(m.n_open, "n_open", minimum=0)
        src = _choice(m.src, "src", _EQ_SRCS)
        with self._tx() as c:
            row = c.execute("SELECT id FROM equity_marks WHERE bot=? AND ts=?", (self.bot, ts)).fetchone()
            if row is not None:
                return row["id"]
            return self._insert(c, "equity_marks", dict(bot=self.bot, ts=ts, wallet=wallet, equity=eq,
                                                         equity_low=low, n_open=n_open, src=src,
                                                         recorded_at=_fmt_ts(now)))

    def list_equity_marks(self, *, since_ts: datetime | None = None,
                          until_ts: datetime | None = None) -> list[EquityMarkRecord]:
        where, args = ["bot=?"], [self.bot]
        if since_ts is not None:
            where.append("ts>=?")
            args.append(_ts(since_ts, "since_ts"))
        if until_ts is not None:
            where.append("ts<?")
            args.append(_ts(until_ts, "until_ts"))
        with self._read() as c:
            rows = c.execute(f"SELECT * FROM equity_marks WHERE {' AND '.join(where)} ORDER BY ts, id",
                             args).fetchall()
        return [EquityMarkRecord(ts=_parse_ts(r["ts"]), wallet=r["wallet"], equity=r["equity"],
                                 equity_low=r["equity_low"], n_open=r["n_open"], src=r["src"], id=r["id"],
                                 bot=r["bot"], recorded_at=_parse_ts(r["recorded_at"])) for r in rows]

    # -- meta (yalniz ekleme) ------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        """DD-8: `meta` tablosundan tek anahtar; yoksa None. Salt okunur."""
        with self._read() as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if r is None else r[0]

    def set_meta_once(self, key: str, value: str) -> None:
        """DD-8: `meta` yalniz-ekleme tablosudur. Anahtar yoksa ekler; ayni deger varsa sessiz; farkli deger varsa
        LedgerError (satir degismez)."""
        self._require_writable()
        key = _text(key, "key", required=True)
        value = _text(value, "value", required=True)
        with self._tx() as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if r is not None:
                if r[0] == value:
                    return
                raise LedgerError(f"meta.{key} zaten farkli degerde")
            c.execute("INSERT INTO meta (key, value) VALUES (?, ?)", (key, value))

    # -- parametre surumleri -------------------------------------------------

    def init_params(self, params: Mapping[str, Any], *, reason: str,
                    lesson_bounds: Mapping[str, tuple[float, float]] | None = None) -> int:
        self._require_writable()
        p = _norm_params(params)
        reason = _text(reason, "reason", required=True)
        bounds = _norm_bounds(lesson_bounds, p, require_contain=True)
        if lesson_bounds is None:
            # varsayilan sinirlar baslangic degerini icermiyorsa kullanici acik sinir vermeli
            _norm_bounds(bounds, p, require_contain=True)
        now = self._now()
        with self._tx() as c:
            if c.execute("SELECT 1 FROM param_activations WHERE bot=?", (self.bot,)).fetchone():
                raise LedgerStateError("init_params zaten cagrildi")
            vid = self._insert(c, "param_versions", dict(
                bot=self.bot, params=_cj(p), params_hash=_hash_params(p), lesson_bounds=_cj(bounds),
                parent_version_id=None, author="initial", reason=reason, evidence=None, proposal_id=None,
                created_at=_fmt_ts(now)))
            self._insert(c, "param_activations", dict(
                bot=self.bot, version_id=vid, prev_version_id=None, kind="initial", actor="system",
                reason=reason, proposal_id=None, activated_at=_fmt_ts(now)))
        return vid

    def create_user_version(self, params: Mapping[str, Any], *, reason: str,
                            lesson_bounds: Mapping[str, tuple[float, float]] | None = None,
                            allow_same_params: bool = False) -> int:
        """allow_same_params: yalniz strateji etiketi degisimi (`init-ledger --reason strategy_update`); params ayni kalir,
        yeni surum yalniz `reason` etiketini tasir (ML golge deneyi, 18 Kasim 2026)."""
        self._require_writable()
        self._require_learner()
        p = _norm_params(params)
        reason = _text(reason, "reason", required=True)
        explicit = _norm_bounds(lesson_bounds, p, require_contain=True) if lesson_bounds is not None else None
        now = self._now()
        with self._tx() as c:
            act = self._active_row(c, self.bot)
            parent = None
            bounds_s = None
            if act is not None:
                parent = c.execute("SELECT * FROM param_versions WHERE id=?", (act["version_id"],)).fetchone()
            if explicit is not None:
                bounds_s = _cj(explicit)
            elif parent is not None:
                bounds_s = parent["lesson_bounds"]
            else:
                bounds_s = _cj({k: list(v) for k, v in LESSON_BOUNDS_DEFAULT.items()})
            h = _hash_params(p)
            if (not allow_same_params and parent is not None and parent["params_hash"] == h
                    and parent["lesson_bounds"] == bounds_s):
                raise LedgerValidationError("no_change: params ve lesson_bounds etkin surumle ayni")
            return self._insert(c, "param_versions", dict(
                bot=self.bot, params=_cj(p), params_hash=h, lesson_bounds=bounds_s,
                parent_version_id=None if parent is None else parent["id"], author="user", reason=reason,
                evidence=None, proposal_id=None, created_at=_fmt_ts(now)))

    def activate_version(self, version_id: int, *, actor: str, reason: str) -> ActivationResult:
        self._require_writable()
        self._require_learner()
        vid = _int(version_id, "version_id")
        _choice(actor, "actor", ("user",))
        reason = _text(reason, "reason", required=True)
        now = self._now()
        with self._tx() as c:
            v = c.execute("SELECT * FROM param_versions WHERE id=? AND bot=?", (vid, self.bot)).fetchone()
            if v is None:
                return ActivationResult(False, "unknown_version", "surum yok", None, None, None)
            if v["author"] not in ("initial", "user"):
                return ActivationResult(False, "lesson_version_forbidden",
                                        "lesson surumleri yalnizca apply_proposal ile etkinlesir", vid, None, None)
            act = self._active_row(c, self.bot)
            if act is not None and act["version_id"] == vid:
                return ActivationResult(False, "already_active", "surum zaten etkin", vid, act["act_id"], None)
            aid = self._insert(c, "param_activations", dict(
                bot=self.bot, version_id=vid, prev_version_id=None if act is None else act["version_id"],
                kind="apply", actor="user", reason=reason, proposal_id=None, activated_at=_fmt_ts(now)))
        return ActivationResult(True, "activated", reason, vid, aid, None)

    # -- oneri / uygulama / geri alma ---------------------------------------

    @staticmethod
    def _check_change(changes, params: Mapping[str, Any], bounds: Mapping[str, Any]):
        """Bolum 5.3 kural 3-10. (code, reason, (param, yeni, eski)|None)."""
        if len(changes) == 0:
            return "empty_changes", "changes bos", None
        if len(changes) > 1:
            return "multiple_changes", "tek oneride yalnizca bir parametre degisebilir", None
        k, raw = next(iter(changes.items()))
        if not isinstance(k, str) or k not in _ALL_SPECS:
            return "unknown_param", f"bilinmeyen parametre: {k!r}", None
        if k not in LESSON_PARAMS:
            return "immutable_param", f"{k} ders servisine kapali", None
        try:
            v = round(_num(raw, k), 6)
        except LedgerValidationError as e:
            return "bad_value", str(e), None
        lo, hi = bounds[k] if k in bounds else LESSON_BOUNDS_DEFAULT[k]
        if v < lo - _TOL or v > hi + _TOL:
            return "out_of_bounds", f"{k}={v} sinir [{lo}, {hi}] disinda", None
        old = params[k] if k in params else PARAM_DEFAULTS[k]
        if abs(v - old) > LESSON_STEP[k] + _TOL:
            return "step_too_large", f"|{v}-{old}| > {LESSON_STEP[k]}", None
        if abs(v - old) < _TOL:
            return "no_change", f"{k} zaten {old}", None
        return None, "", (k, v, old)

    def propose_change(self, *, base_version_id: int, changes: Mapping[str, Any], rationale: str,
                       claimed_evidence: Mapping[str, Any], source: str,
                       require_user: bool = False) -> ProposalResult:
        self._require_writable()
        self._require_learner()
        if not isinstance(require_user, bool):
            raise LedgerValidationError("require_user bool olmali")
        base = _int(base_version_id, "base_version_id")
        if not isinstance(changes, Mapping):
            raise LedgerValidationError("changes Mapping olmali")
        rationale = _text(rationale, "rationale", required=True)
        source = _text(source, "source", required=True)
        if not isinstance(claimed_evidence, Mapping):
            raise LedgerValidationError("claimed_evidence Mapping olmali")
        prop_s = _json_limited({"changes": _json_safe(changes), "rationale": rationale}, "proposal")
        claimed_s = _json_limited(_json_safe(claimed_evidence), "claimed_evidence")
        now = self._now()
        with self._tx() as c:
            act = self._active_row(c, self.bot)
            if act is None:
                raise LedgerStateError("etkin parametre yok")
            status, code, reason = "proposed", "proposed", "oneri kabul edildi"
            if base != act["version_id"]:
                status, code, reason = "rejected", "stale_base", "base_version_id etkin surum degil"
            else:
                v = c.execute("SELECT * FROM param_versions WHERE id=?", (base,)).fetchone()
                bad, why, parsed = self._check_change(changes, json.loads(v["params"]),
                                                      json.loads(v["lesson_bounds"]))
                if bad is not None:
                    status, code, reason = "rejected", bad, why
                elif parsed[0] == "vol_ratio_max" and parsed[1] > parsed[2] and not self.paper_lesson:
                    status, code, reason = "needs_user", "needs_user", "vol_ratio_max artirimi kullanici onayi ister"
                elif require_user:
                    status, code, reason = ("needs_user", "user_approval_required",
                                            "cagiran kullanici onayi istedi (require_user)")
            pid = self._insert(c, "lesson_proposals", dict(
                bot=self.bot, base_version_id=base, proposal=prop_s, claimed_evidence=claimed_s,
                source=source, created_at=_fmt_ts(now)))
            self._insert(c, "proposal_status_events", dict(
                proposal_id=pid, status=status, code=code, reason=reason, version_id=None, actor="lesson",
                recorded_at=_fmt_ts(now)))
        return ProposalResult(status != "rejected", pid, status, code, reason)

    def _pool(self, c, base_row, key: str) -> tuple[int, ...]:
        """Bolum 5.4 POOL(base, key): kapsami etkileyen tum parametreleri base ile esit olan surumler."""
        bp = json.loads(base_row["params"])
        affecting = [q for q in PARAM_KEYS + OPTIONAL_PARAM_KEYS if _affects(q, key)]
        out = []
        for r in c.execute("SELECT id, params FROM param_versions WHERE bot=? ORDER BY id", (self.bot,)):
            vp = json.loads(r["params"])
            if all(vp.get(q, PARAM_DEFAULTS.get(q)) == bp.get(q, PARAM_DEFAULTS.get(q)) for q in affecting):
                out.append(r["id"])
        return tuple(out)

    def pool_version_ids(self, base_version_id: int, param: str) -> tuple[int, ...]:
        base = _int(base_version_id, "base_version_id")
        if not isinstance(param, str) or param not in _ALL_SPECS:
            raise LedgerValidationError(f"bilinmeyen parametre: {param!r}")
        with self._read() as c:
            row = c.execute("SELECT * FROM param_versions WHERE id=? AND bot=?", (base, self.bot)).fetchone()
            if row is None:
                raise LedgerValidationError("surum yok")
            return self._pool(c, row, param)

    def _proposal_status(self, c, pid: int):
        return c.execute("SELECT * FROM proposal_status_events WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
                         (pid,)).fetchone()

    def apply_proposal(self, proposal_id: int, *, actor: str, reason: str) -> ActivationResult:
        self._require_writable()
        self._require_learner()
        pid = _int(proposal_id, "proposal_id")
        _choice(actor, "actor", ("lesson", "user"))
        reason = _text(reason, "reason", required=True)
        now = self._now()
        now_s = _fmt_ts(now)
        with self._tx() as c:
            p = c.execute("SELECT * FROM lesson_proposals WHERE id=? AND bot=?", (pid, self.bot)).fetchone()
            if p is None:
                raise LedgerValidationError("oneri yok")
            st = self._proposal_status(c, pid)
            if st["status"] == "needs_user" and actor != "user":
                return ActivationResult(False, "user_approval_required", "kullanici onayi gerekli",
                                        None, None, pid)
            if st["status"] not in ("proposed", "needs_user"):
                raise LedgerStateError(f"oneri durumu {st['status']}: uygulanamaz")

            def terminal(code: str, why: str) -> ActivationResult:
                self._insert(c, "proposal_status_events", dict(
                    proposal_id=pid, status="rejected", code=code, reason=why, version_id=None,
                    actor=actor, recorded_at=now_s))
                return ActivationResult(False, code, why, None, None, pid)

            act = self._active_row(c, self.bot)
            if act is None:
                raise LedgerStateError("etkin parametre yok")
            if p["base_version_id"] != act["version_id"]:
                return terminal("stale_base", "base_version_id artik etkin degil")
            base = c.execute("SELECT * FROM param_versions WHERE id=?", (p["base_version_id"],)).fetchone()
            params, bounds = json.loads(base["params"]), json.loads(base["lesson_bounds"])
            changes = json.loads(p["proposal"])["changes"]
            bad, why, parsed = self._check_change(changes, params, bounds)
            if bad is not None:
                return terminal(bad, why)
            key, newv, _old = parsed
            # kanit
            scope = LESSON_SCOPE[key]
            marks = ",".join("?" * len(scope))
            pool = self._pool(c, base, key)
            pmarks = ",".join("?" * len(pool))
            rows = c.execute(
                f"SELECT exit_ts, r_multiple, realized_pnl, param_version_id FROM v_closed_trades WHERE bot=? "
                f"AND param_version_id IN ({pmarks}) AND setup IN ({marks}) ORDER BY exit_ts, trade_id",
                (self.bot, *pool, *scope)).fetchall()
            n = len(rows)
            if n < self.min_evidence_trades:
                return ActivationResult(False, "insufficient_evidence",
                                        f"kanit yetersiz: {n} < {self.min_evidence_trades}", None, None, pid)
            if actor == "lesson" and not self.paper_lesson:
                since = _fmt_ts(now - timedelta(days=LESSON_MIN_INTERVAL_DAYS))
                if c.execute("SELECT 1 FROM param_activations WHERE bot=? AND kind='apply' AND actor='lesson' "
                             "AND activated_at>=?", (self.bot, since)).fetchone():
                    return ActivationResult(False, "weekly_limit", "son 7 gunde bir ders degisikligi var",
                                            None, None, pid)
            sum_r = sum(r["r_multiple"] for r in rows)
            claimed = json.loads(p["claimed_evidence"]).get("n_closed")
            by_ver: dict[str, int] = {}
            for r in rows:
                by_ver[str(r["param_version_id"])] = by_ver.get(str(r["param_version_id"]), 0) + 1
            evidence = {"n_closed": n, "scope": "+".join(scope), "base_version_id": base["id"],
                        "pooled_version_ids": list(pool), "n_by_version": by_ver,
                        "first_exit_ts": rows[0]["exit_ts"] if n else None,
                        "last_exit_ts": rows[-1]["exit_ts"] if n else None,
                        "mean_r": sum_r / n if n else 0.0, "sum_r": sum_r,
                        "win_rate": sum(1 for r in rows if r["realized_pnl"] > 0) / n if n else 0.0,
                        "claimed_mismatch": claimed is not None and claimed != n}
            newp = dict(params)
            newp[key] = newv
            newp = _norm_params(newp)
            vid = self._insert(c, "param_versions", dict(
                bot=self.bot, params=_cj(newp), params_hash=_hash_params(newp), lesson_bounds=base["lesson_bounds"],
                parent_version_id=base["id"], author="lesson", reason=reason, evidence=_cj(evidence),
                proposal_id=pid, created_at=now_s))
            aid = self._insert(c, "param_activations", dict(
                bot=self.bot, version_id=vid, prev_version_id=act["version_id"], kind="apply", actor=actor,
                reason=reason, proposal_id=pid, activated_at=now_s))
            self._insert(c, "proposal_status_events", dict(
                proposal_id=pid, status="applied", code="applied", reason=reason, version_id=vid,
                actor=actor, recorded_at=now_s))
        return ActivationResult(True, "applied", reason, vid, aid, pid)

    def reject_proposal(self, proposal_id: int, *, actor: str, reason: str) -> None:
        self._require_writable()
        self._require_learner()
        pid = _int(proposal_id, "proposal_id")
        _choice(actor, "actor", _PROPOSAL_ACTORS)
        reason = _text(reason, "reason", required=True)
        now_s = _fmt_ts(self._now())
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM lesson_proposals WHERE id=? AND bot=?", (pid, self.bot)).fetchone():
                raise LedgerValidationError("oneri yok")
            st = self._proposal_status(c, pid)
            if st["status"] not in ("proposed", "needs_user"):
                raise LedgerStateError(f"oneri durumu {st['status']}: reddedilemez")
            self._insert(c, "proposal_status_events", dict(
                proposal_id=pid, status="rejected", code="rejected_by_actor", reason=reason, version_id=None,
                actor=actor, recorded_at=now_s))

    def rollback(self, to_version_id: int | None = None, *, actor: str, reason: str) -> ActivationResult:
        self._require_writable()
        self._require_learner()
        target = None if to_version_id is None else _int(to_version_id, "to_version_id")
        _choice(actor, "actor", ("lesson", "user"))
        reason = _text(reason, "reason", required=True)
        now_s = _fmt_ts(self._now())
        with self._tx() as c:
            act = self._active_row(c, self.bot)
            if act is None:
                raise LedgerStateError("etkin parametre yok")
            cur = act["version_id"]
            if target is None:
                row = c.execute("SELECT version_id FROM param_activations WHERE bot=? AND version_id<>? "
                                "ORDER BY id DESC LIMIT 1", (self.bot, cur)).fetchone()
                if row is None:
                    return ActivationResult(False, "no_previous_version", "geri alinacak surum yok",
                                            None, None, None)
                target = row["version_id"]
            elif not c.execute("SELECT 1 FROM param_versions WHERE id=? AND bot=?", (target, self.bot)).fetchone():
                return ActivationResult(False, "unknown_version", "surum yok", target, None, None)
            if target == cur:
                return ActivationResult(False, "already_active", "surum zaten etkin", target, act["act_id"], None)
            aid = self._insert(c, "param_activations", dict(
                bot=self.bot, version_id=target, prev_version_id=cur, kind="rollback", actor=actor,
                reason=reason, proposal_id=None, activated_at=now_s))
        return ActivationResult(True, "rolled_back", reason, target, aid, None)

    # -- okuma -------------------------------------------------------------

    @staticmethod
    def _bounds_out(s: str) -> Mapping[str, tuple[float, float]]:
        d = {k: (v[0], v[1]) for k, v in json.loads(s).items()}
        for k in OPTIONAL_PARAM_KEYS:
            d.setdefault(k, tuple(LESSON_BOUNDS_DEFAULT[k]))
        return MappingProxyType(d)

    def _version_from(self, r) -> ParamVersion:
        return ParamVersion(
            id=r["id"], bot=r["bot"], params=MappingProxyType(json.loads(r["params"])),
            params_hash=r["params_hash"], lesson_bounds=self._bounds_out(r["lesson_bounds"]),
            parent_version_id=r["parent_version_id"], author=r["author"], reason=r["reason"],
            evidence=None if r["evidence"] is None else MappingProxyType(json.loads(r["evidence"])),
            proposal_id=r["proposal_id"], created_at=_parse_ts(r["created_at"]))

    def get_active_params(self) -> ActiveParams:
        with self._read() as c:
            r = c.execute(
                "SELECT a.id AS act_id, a.activated_at AS activated_at, v.* FROM param_activations a "
                "JOIN param_versions v ON v.id=a.version_id WHERE a.bot=? ORDER BY a.id DESC LIMIT 1",
                (self.bot,)).fetchone()
        if r is None:
            raise LedgerStateError("etkin parametre yok")
        return ActiveParams(version_id=r["id"], activation_id=r["act_id"],
                            params=MappingProxyType(json.loads(r["params"])), lesson_bounds=self._bounds_out(r["lesson_bounds"]),
                            params_hash=r["params_hash"], activated_at=_parse_ts(r["activated_at"]))

    def active_activation_id(self) -> int | None:
        with self._read() as c:
            return c.execute("SELECT MAX(id) FROM param_activations WHERE bot=?", (self.bot,)).fetchone()[0]

    def get_version(self, version_id: int) -> ParamVersion:
        with self._read() as c:
            r = c.execute("SELECT * FROM param_versions WHERE id=? AND bot=?", (version_id, self.bot)).fetchone()
        if r is None:
            raise LedgerValidationError("surum yok")
        return self._version_from(r)

    def list_versions(self) -> list[ParamVersion]:
        with self._read() as c:
            rows = c.execute("SELECT * FROM param_versions WHERE bot=? ORDER BY id", (self.bot,)).fetchall()
        return [self._version_from(r) for r in rows]

    def list_activations(self, limit: int | None = None) -> list[ActivationEvent]:
        sql = "SELECT * FROM param_activations WHERE bot=? ORDER BY id DESC"
        args: list[Any] = [self.bot]
        if limit is not None:
            sql += " LIMIT ?"
            args.append(_int(limit, "limit", minimum=0))
        with self._read() as c:
            rows = c.execute(sql, args).fetchall()
        return [ActivationEvent(r["id"], r["bot"], r["version_id"], r["prev_version_id"], r["kind"], r["actor"],
                                r["reason"], r["proposal_id"], _parse_ts(r["activated_at"])) for r in rows]

    @staticmethod
    def _decision_from(r) -> DecisionRecord:
        ra = r["risk_allowed"]
        return DecisionRecord(
            id=r["id"], bot=r["bot"], bar_close_ts=_parse_ts(r["bar_close_ts"]), trigger_tf=r["trigger_tf"],
            pair=r["pair"], side=r["side"], setup=r["setup"], regime=r["regime"], atr_ratio=r["atr_ratio"],
            rh=r["rh"], rl=r["rl"], rh_touches=r["rh_touches"], rl_touches=r["rl_touches"],
            features=MappingProxyType(json.loads(r["features"])), planned_entry=r["planned_entry"],
            planned_stop=r["planned_stop"], planned_target=r["planned_target"],
            param_version_id=r["param_version_id"], veto_status=r["veto_status"], veto_reason=r["veto_reason"],
            risk_allowed=None if ra is None else bool(ra), risk_reason=r["risk_reason"], size_qty=r["size_qty"],
            size_notional=r["size_notional"], size_margin=r["size_margin"],
            size_risk_amount=r["size_risk_amount"], leverage=r["leverage"], final_action=r["final_action"],
            skip_reason=r["skip_reason"], supersedes_id=r["supersedes_id"],
            recorded_at=_parse_ts(r["recorded_at"]), activation_id=r["activation_id"], ml_score=r["ml_score"],
            arm_id=r["arm_id"], session_tag=r["session_tag"],
            lesson_ids=None if r["lesson_ids"] is None else tuple(json.loads(r["lesson_ids"])),
            source=r["source"])

    def get_decision(self, decision_id: int) -> DecisionRecord:
        with self._read() as c:
            r = c.execute("SELECT * FROM decision_events WHERE id=? AND bot=?", (decision_id, self.bot)).fetchone()
        if r is None:
            raise LedgerValidationError("karar yok")
        return self._decision_from(r)

    def list_decisions(self, *, since_ts: datetime | None = None, until_ts: datetime | None = None,
                       setup: str | None = None, final_action: str | None = None,
                       limit: int | None = None) -> list[DecisionRecord]:
        where, args = ["bot=?"], [self.bot]
        if since_ts is not None:
            where.append("bar_close_ts>=?")
            args.append(_ts(since_ts, "since_ts"))
        if until_ts is not None:
            where.append("bar_close_ts<?")
            args.append(_ts(until_ts, "until_ts"))
        if setup is not None:
            where.append("setup=?")
            args.append(_setup_code(setup))
        if final_action is not None:
            where.append("final_action=?")
            args.append(_choice(final_action, "final_action", ("entered", "skipped")))
        sql = f"SELECT * FROM v_decisions WHERE {' AND '.join(where)} ORDER BY bar_close_ts, id"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(_int(limit, "limit", minimum=0))
        with self._read() as c:
            rows = c.execute(sql, args).fetchall()
        return [self._decision_from(r) for r in rows]

    @staticmethod
    def _trade_from(r) -> TradeRecord:
        return TradeRecord(
            trade_id=r["trade_id"], decision_id=r["decision_id"], pair=r["pair"], side=r["side"],
            setup=r["setup"], regime=r["regime"], atr_ratio=r["atr_ratio"],
            param_version_id=r["param_version_id"], activation_id=r["activation_id"],
            entry_ts=_parse_ts(r["entry_ts"]), entry_price=r["entry_price"], planned_entry=r["planned_entry"],
            planned_stop=r["planned_stop"], planned_target=r["planned_target"], qty=r["qty"],
            leverage=r["leverage"], planned_risk=r["planned_risk"], fee_entry=r["fee_entry"],
            slippage_entry=r["slippage_entry"], exit_ts=_parse_ts(r["exit_ts"]), exit_price=r["exit_price"],
            exit_reason=r["exit_reason"], planned_exit=r["planned_exit"], fee_exit=r["fee_exit"],
            funding_paid=r["funding_paid"], gross_pnl=r["gross_pnl"], realized_pnl=r["realized_pnl"],
            r_multiple=r["r_multiple"], slippage_exit=r["slippage_exit"], mfe_r=r["mfe_r"],
            mae_r=r["mae_r"], bars_held=r["bars_held"], excursion_tf=r["excursion_tf"],
            entry_order_ts=_parse_ts(r["entry_order_ts"]), entry_order_ack_ts=_parse_ts(r["entry_order_ack_ts"]),
            entry_ref_price=r["entry_ref_price"], entry_ref_spread=r["entry_ref_spread"],
            entry_ref_src=r["entry_ref_src"], slip_exec_entry=r["slip_exec_entry"],
            exit_order_ts=_parse_ts(r["exit_order_ts"]), exit_order_ack_ts=_parse_ts(r["exit_order_ack_ts"]),
            exit_ref_price=r["exit_ref_price"], exit_ref_spread=r["exit_ref_spread"],
            exit_ref_src=r["exit_ref_src"], slip_exec_exit=r["slip_exec_exit"],
            exit_decision_price=r["exit_decision_price"], slip_decision_exit=r["slip_decision_exit"],
            exit_regime=r["exit_regime"])

    def _trades(self, where: str = "", args: Sequence[Any] = (), closed: bool = False) -> list[TradeRecord]:
        view = "v_closed_trades" if closed else "v_trades"
        sql = f"SELECT * FROM {view} WHERE bot=?" + (f" AND {where}" if where else "") + \
              " ORDER BY entry_ts, trade_id"
        with self._read() as c:
            rows = c.execute(sql, [self.bot, *args]).fetchall()
        return [self._trade_from(r) for r in rows]

    def get_trade(self, trade_id: int) -> TradeRecord | None:
        r = self._trades("trade_id=?", [trade_id])
        return r[0] if r else None

    def list_open_trades(self) -> list[TradeRecord]:
        return self._trades("exit_ts IS NULL")

    LIST_CLOSED_MAX = 10000

    def list_closed_trades(self, since: datetime | None = None, until: datetime | None = None,
                           limit: int = 200) -> list[TradeRecord]:
        """Kapanan islemler (salt okunur): `since <= exit_ts < until`, cikis zamani yeniden eskiye
        (esitlikte trade_id azalan), en cok `limit` (>= 0, <= LIST_CLOSED_MAX) kayit."""
        where, args = ["bot=?"], [self.bot]
        if since is not None:
            where.append("exit_ts>=?")
            args.append(_ts(since, "since"))
        if until is not None:
            where.append("exit_ts<?")
            args.append(_ts(until, "until"))
        lim = _int(limit, "limit", minimum=0)
        if lim > self.LIST_CLOSED_MAX:
            raise LedgerValidationError(f"limit en cok {self.LIST_CLOSED_MAX} olmali")
        sql = (f"SELECT * FROM v_closed_trades WHERE {' AND '.join(where)} "
               "ORDER BY exit_ts DESC, trade_id DESC LIMIT ?")
        args.append(lim)
        with self._read() as c:
            rows = c.execute(sql, args).fetchall()
        return [self._trade_from(r) for r in rows]

    def arm_recent_results(self, arm_id: str, limit: int = 10) -> list[float]:
        """Kolun son kapanan islemlerinin net R degerleri (r_multiple = komisyon/funding dusulmus), EN YENIDEN ESKIYE
        (exit_ts, trade_id azalan), en cok `limit` (kademeli kucultme, docs/motor/kademeli-kucultme-spec.md). Salt okunur."""
        lim = _int(limit, "limit", minimum=0)
        with self._read() as c:
            rows = c.execute("SELECT r_multiple FROM v_closed_trades WHERE bot=? AND arm_id=? "
                             "ORDER BY exit_ts DESC, trade_id DESC LIMIT ?", (self.bot, str(arm_id), lim)).fetchall()
        return [float(r["r_multiple"]) for r in rows]

    def closed_decision_features_since(self, arm_id: str, pair: str, side: str, since: datetime) -> list[dict]:
        """Kolun (arm_id) bu cift+yondeki `since` ve sonrasinda (exit_ts) kapanmis TUM islemlerinin giris karari features sozlukleri
        (yeniden eskiye). Salt okunur (HB1 'ayni haberle yeniden giris yok' kapisi)."""
        with self._read() as c:
            rows = c.execute("SELECT d.features AS f FROM v_closed_trades t JOIN decision_events d ON d.id = t.decision_id "
                             "WHERE t.bot=? AND t.arm_id=? AND t.pair=? AND t.side=? AND t.exit_ts>=? "
                             "ORDER BY t.exit_ts DESC, t.trade_id DESC", (self.bot, str(arm_id), str(pair), str(side), _ts(since, "since"))).fetchall()
        out = []
        for r in rows:
            f = json.loads(r["f"])
            out.append(f if isinstance(f, dict) else {})
        return out

    FAMILY_WINDOW_DAYS = 90
    FAMILY_HOLDOUT = (datetime(2026, 5, 1, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc))   # trader_engine.holdout.HOLDOUT kopyasi (parite testi)

    def arm_family_mean_r(self, arm_id: str, until: datetime | None = None) -> float | None:
        """Kolun AILESININ (ayni kurulum, tum TF'ler: arm_id '@' oncesi) kolun KENDISI HARIC kapanmis islemlerinin ortalama net R'si
        (kol buzulmesi, kol_kucultme.buzulme): `until - 90 gun <= exit_ts < until` (until karar zamani; None ise tum zaman), HOLDOUT [2026-05-01, 2026-11-01) cikis zamanlari dislanir.
        Islem yoksa None. Salt okunur."""
        fam = str(arm_id).split("@")[0]
        esc = fam.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where = ["bot=?", "(arm_id=? OR arm_id LIKE ? ESCAPE '\\')", "arm_id<>?", "(exit_ts<? OR exit_ts>=?)"]
        args: list[Any] = [self.bot, fam, esc + "@%", str(arm_id), _ts(self.FAMILY_HOLDOUT[0], "holdout"), _ts(self.FAMILY_HOLDOUT[1], "holdout")]
        if until is not None:
            where += ["exit_ts>=?", "exit_ts<?"]
            args += [_ts(until - timedelta(days=self.FAMILY_WINDOW_DAYS), "since"), _ts(until, "until")]
        with self._read() as c:
            row = c.execute("SELECT AVG(r_multiple) AS m, COUNT(*) AS n FROM v_closed_trades WHERE " + " AND ".join(where), args).fetchone()
        return float(row["m"]) if row is not None and row["n"] else None

    def arm_results_all(self, limit: int = 10) -> dict[str, list[float]]:
        """{arm_id: son `limit` kapanan islemin net R'si (yeniden eskiye)} (rapor/panel; salt okunur)."""
        lim = _int(limit, "limit", minimum=0)
        out: dict[str, list[float]] = {}
        with self._read() as c:
            rows = c.execute("SELECT arm_id, r_multiple FROM v_closed_trades WHERE bot=? AND arm_id IS NOT NULL "
                             "ORDER BY exit_ts DESC, trade_id DESC", (self.bot,)).fetchall()
        for r in rows:
            lst = out.setdefault(r["arm_id"], [])
            if len(lst) < lim:
                lst.append(float(r["r_multiple"]))
        return out

    def _since_where(self, c, version_id: int, exact: bool):
        if exact:
            return "param_version_id=?", [version_id]
        a = c.execute("SELECT MAX(id) FROM param_activations WHERE bot=? AND version_id=?",
                      (self.bot, version_id)).fetchone()[0]
        if a is None:
            return "0", []
        return "activation_id>=?", [a]

    def trades_since_version(self, version_id: int, *, closed_only: bool = True, exact: bool = False,
                             setup: str | None = None) -> list[TradeRecord]:
        vid = _int(version_id, "version_id")
        view = "v_closed_trades" if closed_only else "v_trades"
        with self._read() as c:
            where, args = self._since_where(c, vid, exact)
            where = f"bot=? AND {where}"
            args = [self.bot, *args]
            if setup is not None:
                where += " AND setup=?"
                args.append(_setup_code(setup))
            rows = c.execute(f"SELECT * FROM {view} WHERE {where} ORDER BY entry_ts, trade_id", args).fetchall()
        return [self._trade_from(r) for r in rows]

    def _check_versions(self, c, version_ids) -> list[int]:
        if isinstance(version_ids, (str, bytes, Mapping)) or not isinstance(version_ids, Iterable):
            raise LedgerValidationError("version_ids bir dizi olmali")
        ids = sorted({_int(v, "version_id", minimum=1) for v in version_ids})
        if ids:
            marks = ",".join("?" * len(ids))
            have = {r[0] for r in c.execute(
                f"SELECT id FROM param_versions WHERE bot=? AND id IN ({marks})", (self.bot, *ids))}
            if have != set(ids):
                raise LedgerValidationError(f"surum yok: {sorted(set(ids) - have)}")
        return ids

    def trades_for_versions(self, version_ids: Sequence[int], *, closed_only: bool = True,
                            setup: str | None = None, until_ts: datetime | None = None) -> list[TradeRecord]:
        with self._read() as c:
            ids = self._check_versions(c, version_ids)
            if not ids:
                return []
            view = "v_closed_trades" if closed_only else "v_trades"
            where = ["bot=?", f"param_version_id IN ({','.join('?' * len(ids))})"]
            args: list[Any] = [self.bot, *ids]
            if setup is not None:
                where.append("setup=?")
                args.append(_setup_code(setup))
            if until_ts is not None:
                u = _ts(until_ts, "until_ts")
                where.append("entry_ts<? AND (exit_ts IS NULL OR exit_ts<?)")
                args += [u, u]
            rows = c.execute(f"SELECT * FROM {view} WHERE {' AND '.join(where)} "
                             "ORDER BY exit_ts IS NULL, exit_ts, trade_id", args).fetchall()
        return [self._trade_from(r) for r in rows]

    def count_closed_trades(self, *, version_id: int, setup: str | None = None) -> int:
        where, args = "bot=? AND param_version_id=?", [self.bot, _int(version_id, "version_id")]
        if setup is not None:
            where += " AND setup=?"
            args.append(_setup_code(setup))
        with self._read() as c:
            return c.execute(f"SELECT COUNT(*) FROM v_closed_trades WHERE {where}", args).fetchone()[0]

    _GROUP_COLS = ("setup", "regime", "side", "param_version_id", "pair")

    def aggregate_trades(self, group_by: Sequence[str], *, version_id: int | None = None,
                         exact_version: bool = True, since_ts: datetime | None = None,
                         until_ts: datetime | None = None,
                         version_ids: Sequence[int] | None = None) -> list[AggregateRow]:
        if isinstance(group_by, str) or not isinstance(group_by, Sequence) or len(group_by) == 0:
            raise LedgerValidationError("group_by bos olmayan bir dizi olmali")
        keys = list(group_by)
        if len(set(keys)) != len(keys) or any(k not in self._GROUP_COLS for k in keys):
            raise LedgerValidationError(f"group_by {self._GROUP_COLS} alt kumesi ve tekrarsiz olmali")
        if version_ids is not None and version_id is not None:
            raise LedgerValidationError("version_ids ile version_id birlikte verilemez")
        where, args = ["bot=?"], [self.bot]
        if since_ts is not None:
            where.append("exit_ts>=?")
            args.append(_ts(since_ts, "since_ts"))
        if until_ts is not None:
            where.append("exit_ts<?")
            args.append(_ts(until_ts, "until_ts"))
        with self._read() as c:
            if version_ids is not None:
                ids = self._check_versions(c, version_ids)
                if not ids:
                    return []
                where.append(f"param_version_id IN ({','.join('?' * len(ids))})")
                args += ids
            elif version_id is not None:
                w, a = self._since_where(c, _int(version_id, "version_id"), bool(exact_version))
                where.append(w)
                args += a
            rows = c.execute(f"SELECT * FROM v_closed_trades WHERE {' AND '.join(where)}", args).fetchall()
        groups: dict[tuple, list] = {}
        for r in rows:
            groups.setdefault(tuple(r[k] for k in keys), []).append(r)
        out = []
        for gk in sorted(groups):
            rs = groups[gk]
            n = len(rs)
            rv = sorted(r["r_multiple"] for r in rs)
            med = rv[n // 2] if n % 2 else (rv[n // 2 - 1] + rv[n // 2]) / 2
            wins = sum(1 for r in rs if r["realized_pnl"] > 0)
            sx = [r["slippage_exit"] for r in rs if r["slippage_exit"] is not None]
            sum_r = sum(rv)
            out.append(AggregateRow(
                key=dict(zip(keys, gk)), n=n, wins=wins, win_rate=wins / n, sum_r=sum_r, mean_r=sum_r / n,
                median_r=med, sum_pnl=sum(r["realized_pnl"] for r in rs),
                sum_fees=sum(r["fee_entry"] + r["fee_exit"] for r in rs),
                sum_funding=sum(r["funding_paid"] for r in rs),
                mean_slippage_entry=sum(r["slippage_entry"] for r in rs) / n,
                mean_slippage_exit=(sum(sx) / len(sx)) if sx else None))
        return out

    @staticmethod
    def _proposal_from(r) -> ProposalRecord:
        return ProposalRecord(
            id=r["id"], bot=r["bot"], base_version_id=r["base_version_id"],
            proposal=MappingProxyType(json.loads(r["proposal"])),
            claimed_evidence=MappingProxyType(json.loads(r["claimed_evidence"])), source=r["source"],
            created_at=_parse_ts(r["created_at"]), status=r["status"], code=r["code"], reason=r["reason"],
            version_id=r["version_id"], status_actor=r["status_actor"], status_event_id=r["status_event_id"])

    def get_proposal(self, proposal_id: int) -> ProposalRecord:
        with self._read() as c:
            r = c.execute("SELECT * FROM v_proposals WHERE id=? AND bot=?", (proposal_id, self.bot)).fetchone()
        if r is None:
            raise LedgerValidationError("oneri yok")
        return self._proposal_from(r)

    def list_proposals(self, *, status: str | None = None, limit: int | None = None) -> list[ProposalRecord]:
        sql, args = "SELECT * FROM v_proposals WHERE bot=?", [self.bot]
        if status is not None:
            sql += " AND status=?"
            args.append(_choice(status, "status", ("proposed", "applied", "rejected", "needs_user")))
        sql += " ORDER BY id"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(_int(limit, "limit", minimum=0))
        with self._read() as c:
            rows = c.execute(sql, args).fetchall()
        return [self._proposal_from(r) for r in rows]

    # -- yedek -------------------------------------------------------------

    def backup(self, dest_path) -> None:
        dest = os.fspath(dest_path)
        if os.path.exists(dest):
            raise LedgerValidationError("hedef dosya zaten var")
        src = self._conn()
        try:
            dst = sqlite3.connect(dest)
            try:
                src.backup(dst)
            finally:
                dst.close()
        except sqlite3.Error as e:
            raise _map_sqlite_error(e) from e

    # -- saglik / kapi -----------------------------------------------------

    def _spool_path(self) -> str:
        return self.path + ".spool.jsonl"

    def _spool_pending(self) -> bool:
        try:
            return os.path.getsize(self._spool_path()) > 0
        except OSError:
            return False

    def _corrupt_path(self) -> str:
        return self.path + ".spool.corrupt.jsonl"

    def _spool_tail_torn(self) -> bool:
        """O14 / D2: spool son bayti satir sonu degilse (guc kesintisi/yarim yazim) True. Yeni kayit o parcaya yapismamali."""
        try:
            with open(self._spool_path(), "rb") as f:
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    return False
                f.seek(-1, os.SEEK_END)
                return f.read(1) != b"\n"
        except OSError:
            return False

    def _quarantine(self, rows: list[str], why: str) -> bool:
        """Islenemeyen spool satirlarini `<defter>.spool.corrupt.jsonl`a tasir (fsync). Basarisizsa False (satir spool'da kalir)."""
        try:
            with open(self._corrupt_path(), "a", encoding="utf-8") as f:
                for ln in rows:
                    f.write(json.dumps({"at": _fmt_ts(self._now()), "why": why, "row": ln}, ensure_ascii=False,
                                       separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return True
        except OSError as e:
            log.critical("spool karantina dosyasi yazilamadi (satirlar spool'da korunuyor): %s", e)
            return False

    def _spool_append(self, payload: Mapping[str, Any]) -> bool:
        try:
            with self._spool_lock, open(self._spool_path(), "a", encoding="utf-8") as f:
                if self._spool_tail_torn():
                    f.write("\n")                  # yarim satiri kapat: yeni kayit onunla ayni satira yapismaz
                f.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return True
        except OSError as e:
            log.critical("spool yazilamadi, kayit kayboldu: %s (%s)", payload, e)
            return False

    def drain_spool(self) -> int:
        self._require_writable()
        done = 0
        with self._spool_lock:
            try:
                with open(self._spool_path(), encoding="utf-8") as f:
                    lines = [ln for ln in f.read().splitlines() if ln.strip()]
            except OSError:
                return 0
            remaining: list[str] = []
            corrupt: list[tuple[str, str]] = []
            stop = False
            for ln in lines:
                if stop:
                    remaining.append(ln)
                    continue
                try:
                    d = json.loads(ln)
                except ValueError as e:
                    d = None
                    why = f"{type(e).__name__}: {e}"
                else:
                    why = None
                    if not isinstance(d, dict):
                        why = "not_a_dict"
                    elif d.get("type") not in ("entry", "exit"):
                        why = f"unknown_type:{d.get('type')!r}"
                if why is not None:
                    # O14: YALNIZ yapisal olarak okunamayan satir (JSON hatasi, dict degil, type yok/bilinmiyor) karantinaya
                    # alinir. Ayristirilabilen ama kayda reddedilen satir (eksik alan, gecersiz deger, durum hatasi) eskisi
                    # gibi spool'da KALIR (CRIT, girisler kapali, insan onarimi): aksi halde yarim giris + gecerli cikis ikisi de
                    # karantinaya girip spool'u bosaltir ve kapi yeniden acilirdi (gunluk zarar eksik sayilir).
                    log.critical("spool satiri okunamiyor, karantinaya aliniyor: %s (%s)", ln, why)
                    corrupt.append((ln, why))
                    continue
                try:
                    if d["type"] == "entry":
                        self._record_entry(TradeEntry(
                            d["trade_id"], d["decision_id"], _parse_ts(d["entry_ts"]), d["entry_price"],
                            d["qty"], d["leverage"], d["fee_entry"], d.get("supersedes_id"),
                            _parse_ts(d.get("order_ts")), _parse_ts(d.get("order_ack_ts")),
                            d.get("order_ref_price"), d.get("order_ref_spread"), d.get("order_ref_src")),
                            spool=False)
                    else:
                        self._record_exit(TradeExit(
                            d["trade_id"], _parse_ts(d["exit_ts"]), d["exit_price"], d["exit_reason"],
                            d["planned_exit"], d["fee_exit"], d["funding_paid"], d.get("supersedes_id"),
                            d.get("max_favorable_price"), d.get("max_adverse_price"), d.get("excursion_tf"),
                            _parse_ts(d.get("order_ts")), _parse_ts(d.get("order_ack_ts")),
                            d.get("order_ref_price"), d.get("order_ref_spread"), d.get("order_ref_src"),
                            d.get("decision_price"), d.get("exit_regime"), d.get("leg_exit_price")),
                            spool=False)
                    done += 1
                except LedgerWriteError:
                    remaining.append(ln)
                    stop = True
                except (LedgerError, ValueError, KeyError, TypeError) as e:
                    log.critical("spool satiri islenemedi (korunuyor): %s (%s)", ln, e)
                    remaining.append(ln)
            for ln, why in corrupt:
                if not self._quarantine([ln], why):
                    remaining.append(ln)
            try:
                tmp = self._spool_path() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write("".join(ln + "\n" for ln in remaining))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self._spool_path())
            except OSError as e:
                log.critical("spool yeniden yazilamadi: %s", e)
        if not self._spool_pending():
            self.check_writable()
        return done

    def check_writable(self) -> Health:
        if self._closed:
            return Health(False, "io_error", "defter kapali")
        if self.read_only:
            return Health(False, "read_only", "salt okunur baglanti")
        try:
            st = os.statvfs(os.path.dirname(os.path.abspath(self.path)) or ".")
            free = st.f_bavail * st.f_frsize
        except OSError as e:
            self._degraded = True
            return Health(False, "io_error", str(e))
        if free < MIN_FREE_BYTES:
            self._degraded = True
            return Health(False, "disk_low", f"bos alan {free} bayt < {MIN_FREE_BYTES}")
        try:
            now = self._now()
            with self._tx() as c:
                self._insert(c, "health_probes", dict(bot=self.bot, probed_at=_fmt_ts(now)))
        except LedgerError as e:
            self._degraded = True
            return Health(False, _health_code(e), str(e))
        self._last_write_ok = now
        if not self._spool_pending():
            self._degraded = False
        return Health(True, "ok", "")

    def _age(self, t: datetime | None) -> float | None:
        return None if t is None else (self._now() - t).total_seconds()

    def entries_allowed(self) -> Health:
        try:
            if not self.read_only and self._spool_pending():
                with contextlib.suppress(Exception):
                    self.drain_spool()
            if self._spool_pending():
                return Health(False, "spool_pending", "spool'da bekleyen kayit var")
            if self._degraded:
                age = self._age(self._last_degraded_attempt)
                if age is None or age < 0 or age >= 30:
                    self._last_degraded_attempt = self._now()
                    self.check_writable()
                if self._degraded:
                    return Health(False, "degraded", "defter yazilamiyor (degraded)")
            c = self._conn()
            try:
                uv = c.execute("PRAGMA user_version").fetchone()[0]
                has_active = c.execute("SELECT 1 FROM param_activations WHERE bot=? LIMIT 1",
                                       (self.bot,)).fetchone() is not None
            except sqlite3.Error as e:
                raise _map_sqlite_error(e) from e
            if uv != SCHEMA_VERSION:
                return Health(False, "schema", f"sema surumu {uv}")
            if not has_active:
                return Health(False, "no_active_params", "etkin parametre yok")
            age = self._age(self._last_write_ok)
            if age is None or age < 0 or age > 60:
                h = self.check_writable()
                if not h.ok:
                    return Health(False, "degraded", h.detail)
            if self._unledgered:
                return Health(False, "unledgered_trades", f"defterde girisi olmayan islemler: {self._unledgered}")
            return Health(True, "ok", "")
        except LedgerError as e:
            return Health(False, "degraded", str(e))

    def find_orphan_decisions(self, *, older_than_s: int = 3600) -> list[int]:
        cutoff = _fmt_ts(self._now() - timedelta(seconds=_int(older_than_s, "older_than_s", minimum=0)))
        with self._read() as c:
            rows = c.execute(
                "SELECT d.id FROM v_decisions d WHERE d.bot=? AND d.final_action='entered' AND d.recorded_at<=? "
                "AND NOT EXISTS (SELECT 1 FROM v_trades t WHERE t.decision_id=d.id) ORDER BY d.id",
                (self.bot, cutoff)).fetchall()
        return [r[0] for r in rows]

    def find_unledgered_trades(self, open_trade_ids: Iterable[int]) -> list[int]:
        ids = sorted({_int(i, "trade_id") for i in open_trade_ids})
        with self._read() as c:
            have = {r[0] for r in c.execute("SELECT trade_id FROM v_trades WHERE bot=?", (self.bot,))}
        missing = [i for i in ids if i not in have]
        self._unledgered = missing
        return missing
