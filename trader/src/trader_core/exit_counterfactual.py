"""Cikis karsi-olgusu gece isi (plan 25c; docs/cikis-karsi-olgu-spec.md): KAPANMIS her T1 islemin giris sonrasi fiyat yolu,
alternatif `trail_atr` degerleriyle yeniden oynatilir ("o degerle cikseydik net R ne olurdu"). Bir KANIT islemidir: ders menusune
bilgi olarak girer (lesson.build_exit_counterfactual); hicbir sey bloklamaz, hicbir kurulumu kapatmaz, otomatik uygulanmaz.

Kapsam v1 (on kayit exitcf-v1): TEK parametre `trail_atr`, TEK adim, iki yon (up = v + adim, down = v - adim) => n_trials = 2.
Taban = ayni yolun AKTIF degerle yeniden oynatimi; Delta = alternatif - taban (ayni 15 dk izgarasi, ayni maliyet modeli).
Isleme ozgu kendi degeri (`param_version_id`) aktiften farkliysa ayrica `own` oynatimi yapilir; parite (tani) yalniz o satirda.

Bagimlilik: stdlib + sqlite. pandas/numpy/trader_core.signals|regime|indicators YALNIZCA oynatim aninda (`prepare_h1`, `replay_trail`)
tembel ice aktarilir: ders servisi bu modulu (deltas/parity_stats okuma API'si) ice aktarirken pandas yuklenmez. trader_engine ice
aktarilmaz (08-no-framework-guard): kilitli donem sabiti ve funding formulu KOPYADIR, esitlik tests/test_exit_cf_*.py ile kilitlenir.
Iz suren stop formulu KOPYALANMAZ: `trader_core.signals.trail_stop_path` aynen cagrilir (tek kaynak).
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from trader_core import exit_modes as XM

__all__ = ["REGISTRY_ID", "VERSION", "PARAM", "ROLES", "RunResult", "ExitCfError", "TradeInput", "ExitCfStore", "MarketSource",
           "replay_trail", "run_modes_once", "deltas_modes", "ModesRunResult", "MODES_REGISTRY_ID", "prepare_h1", "price_result", "run_once", "deltas", "parity_stats", "summary", "holdout_hit",
           "funding_grid_times", "funding_payment", "registry_row", "EXCLUDED_EXIT_REASONS", "SOURCES_VERDICT"]

REGISTRY_ID = "exitcf-v1"            # on kayit kimligi (research/trial_registry.csv); CLI --registry-id bu sabite esit degilse calismaz
VERSION = 1                          # kural surumu: sabit/formul degisirse artar; ders yalniz en yuksek surumu okur
PARAM = "trail_atr"
MODES_REGISTRY_ID = "exitcf-v2"      # cikis kipleri (basa-bas / kismi) on kaydi; v1 satiri/sabitleri degismez (docs/cikis-kipleri-spec.md 6)
MODES_VERSION = 2                    # ecf_modes kural surumu (v1 tablosundan bagimsiz); 2: kismi adet motorla ayni yuvarlama (parite, 19.11)
MODE_NAMES = ("breakeven", "partial")
MODE_VARIANTS = ("off",) + MODE_NAMES
ROLES = ("base", "up", "down", "own")
SOURCES = ("paper", "testnet", "live", "backtest")
SOURCES_VERDICT = ("paper", "testnet")           # hukum yalniz kendi bot defterinden (live: gercek para askida; spec 6)
EXCLUDED_EXIT_REASONS = ("liquidation", "manual", "force_exit")
SIM_REASONS = ("stop", "trail_stop", "regime_flip", "horizon", "data_gap", "no_data")

# --- on kayitli sabitler (degisirse exitcf-v2 + VERSION artisi)
MAX_BARS = 720                       # EXIT_CF_MAX_BARS: 30 gun x 24 (1h mum); dolmayan yol 720. kapanista piyasaya gore degerlenir
WARMUP_DAYS = 50                     # EXIT_CF_WARMUP_DAYS: motorun baslangic penceresi (STARTUP_BARS_4H=300 -> 50 gun)
MAX_TRADES_PER_RUN = 2000            # EXIT_CF_MAX_TRADES_PER_RUN
GRID_MIN = 15                        # stop vurusu 15 dk mumlarla oynatilir
GAP_GRACE = timedelta(hours=24)
# 23.11.2026 kullanici karari: kilit ACIK (trader_engine.holdout.KILIT_ACIK'in kopyasi; esitlik testle denetlenir)
KILIT_ACIK = True
HOLDOUT_START = datetime(2026, 5, 1, tzinfo=timezone.utc)      # trader_engine.holdout.HOLDOUT'un kopyasi (esitlik testi)
HOLDOUT_END = datetime(2026, 11, 1, tzinfo=timezone.utc)
MARKET_SCHEMA_VERSION = 1            # trader_engine.marketdata.store.SCHEMA_VERSION kopyasi
STORE_SCHEMA_VERSION = 1
HR_MS = 3_600_000
M15_MS = 900_000
H4_MS = 14_400_000
H8_MS = 28_800_000
DAY_MS = 86_400_000
EPS = 1e-9                           # signals.EPS kopyasi (iz sikilasma esigi; esitlik testi)
TRAIL_BOUND_NOTE = "alternatif lesson_bounds disina cikarsa uretilmez"

CF_EXIT_BLOCK_DAYS = 7
PARITY_MIN_N = 20
PARITY_MEDIAN_ABS_R = 0.10
PARITY_MEAN_ABS_R = 0.05
PARITY_REASON_MATCH = 0.85


class ExitCfError(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


def registry_row() -> dict:
    """research/trial_registry.csv icin on kayit satiri (docs/cikis-karsi-olgu-spec.md 0). Sunucuda research/ yoktur: satirin
    varligini ve surum eslesmesini depo birim testi zorlar."""
    return {"id": REGISTRY_ID, "strategy": "TraderV1b", "params": json.dumps({"grid": "cur±LESSON_STEP", "params": ["trail_atr"]},
                                                                             ensure_ascii=False, separators=(",", ":")),
            "n_trials": 2, "version": VERSION}


# ------------------------------------------------------------------------------------------------ zaman / funding (saf)
def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ExitCfError("saat dilimi olmayan zaman", "bad_time")
    return dt.astimezone(timezone.utc)


def to_ms(dt: datetime) -> int:
    return int(_utc(dt).timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def fmt_ms(ms: int) -> str:
    return from_ms(ms).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _fmt(dt: datetime) -> str:
    return _utc(dt).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)


def funding_grid_times(entry_ms: int, exit_ms: int) -> list[int]:
    """(entry, exit] araligindaki 00/08/16 UTC funding zamanlari (trader_engine.funding.due_funding_times + accrue ile ayni kume:
    pozisyon acilisindan SONRAki zamanlar; esitlik testi). Eksik kayit denetimi bu izgaraya baglidir; izgara disi (4s/1s)
    kayitlar `_funding_fn` icinde kendi saatinde eklenir."""
    if exit_ms <= entry_ms:
        return []
    t = (entry_ms // H8_MS + 1) * H8_MS
    out = []
    while t <= exit_ms:
        out.append(t)
        t += H8_MS
    return out


def funding_payment(side: str, qty: float, mark: float, rate: float) -> float:
    """trader_engine.funding.funding_payment kopyasi; POZITIF = odenen."""
    if side not in ("long", "short"):
        raise ValueError(f"gecersiz side: {side!r}")
    p = qty * mark * rate
    return p if side == "long" else -p


def holdout_hit(start_ms: int, end_ms: int, holdout: tuple[datetime, datetime] | None = None) -> bool:
    """[start, end] pencere kilitli donemle kesisir mi (yari acik [HOLDOUT_START, HOLDOUT_END))."""
    if holdout is None and KILIT_ACIK:       # acik kilitte varsayilan pencere yok (acik `holdout` verilirse yine uygulanir)
        return False
    hs, he = holdout or (HOLDOUT_START, HOLDOUT_END)
    return start_ms < to_ms(he) and end_ms >= to_ms(hs)


# ------------------------------------------------------------------------------------------------ girdi tipi
@dataclass(frozen=True)
class TradeInput:
    trade_id: int
    pair: str
    side: str
    setup: str
    trigger_tf: str
    entry_ts: datetime
    exit_ts: datetime | None
    entry_price: float
    qty: float
    planned_risk: float
    initial_stop: float
    fee_entry: float
    exit_reason: str | None
    exit_price: float | None
    actual_net_r: float | None
    param_version_id: int
    own_value: float | None            # islemin kendi surumundeki trail_atr (yoksa None)
    source: str = "paper"
    run_id: str = ""
    own_modes: XM.ExitModes | None = None   # islemin kendi surumunde acik cikis kipleri (v1 oynatimlari bunlarla; yoksa None = kapali)


def _fin(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _vkey(v: float) -> float:
    return round(float(v), 6)


# ------------------------------------------------------------------------------------------------ oynatim (saf)
@dataclass
class H1Series:
    """Motorun 1h tablosu: kapanis-zamani sirali; `idx0` = giris mumunun (floor_1h(entry_ts)) dizindeki yeri."""
    ms: list
    o: list
    h: list
    l: list
    c: list
    atr: list
    regime: list


@dataclass
class ReplayResult:
    status: str                         # ok | pending | gap
    reason: str | None = None           # stop | trail_stop | regime_flip | horizon
    exit_ms: int | None = None
    exit_price: float | None = None
    bars_held: int | None = None
    mfe_r: float | None = None
    censored: int = 0
    gap_ms: int | None = None           # eksik mumun acilisi (status=gap) ya da beklenen bar (pending)
    gap_kind: str | None = None         # bars15 | bars1h
    partial_ms: int | None = None       # kismi kar alma (yalniz kip aciksa): dolum zamani / karma fiyat / pozisyon payi
    partial_price: float | None = None
    partial_frac: float | None = None


def _slip(price: float, side: str, bps: float) -> float:
    """Cikis emri: long satar (-), short alir (+)."""
    f = bps / 10000.0
    return price * (1.0 - f) if side == "long" else price * (1.0 + f)


def replay_trail(*, side: str, entry_price: float, initial_stop: float, entry_ms: int, trail_atr: float, h1: H1Series,
                 m15: Mapping[int, tuple], now_ms: int, slip_exit_bps: float, slip_stop_bps: float,
                 max_bars: int | None = None, modes: XM.ExitModes | None = None, qty: float | None = None,
                 lot_rules: tuple[float, float, float] | None = None) -> ReplayResult:
    """T1 cikisini (position_manager.evaluate_exit sirasi) 1h kapanislarinda + 15 dk stop vurusuyla oynatir.

    `h1`: ms/o/h/l/c/atr/regime (acilis zamani sirali, bosluksuz olmali); `m15`: {acilis_ms: (o,h,l,c)} tetik serisi.
    Sira (her kapanan 1h mumu D): (a) regime_flip -> D'den sonraki ilk 15 dk acilisinda piyasa cikisi; (b) iz stop `armed` ise
    ve stop D kapanisinda gecildiyse -> trail_stop piyasa cikisi; (c) stop sikilastiysa yeni stop D'den sonraki ilk 15 dk
    mumundan itibaren gecerli; o mumun ACILISI zaten asmissa (would_trigger) -> trail_stop piyasa cikisi. 15 dk mumunda stop
    vurusu: long low<=stop / short high>=stop; ayni mumda her sey stop once; bosluk -> dolum mum acilisi; sonra stop kaymasi.
    Veri sonu (now) -> pending; veri deligi -> gap (gap_ms).
    `modes` (docs/cikis-kipleri-spec.md; varsayilan None = kapali, davranis bayt bayt eski): basa-bas -> stop = iz stopu ile
    `exit_modes.be_stop`un siki olani (1h kapanista, motorla ayni islev); kismi -> 1h kapanista tetik varsa D'den sonraki ilk
    15 dk acilisinda `pt_frac` kadari piyasada kapanir (bir kez; cikis karari verilmediyse), kalan surer.
    `qty` + `lot_rules` (adim, min adet, min notional; verilirse): kismi adet MOTORLA AYNI yuvarlamayla (`exit_modes.partial_qty`:
    adim tabanina, 1h kapanis fiyatiyla min notional) hesaplanir, kapanan oran = adet/qty; kapanan ya da kalan parca limit altindaysa
    kismi bir kez ATLANIR (motor `partial:<id> = skipped`). Verilmezse tam oran `pt_frac` (eski davranis)."""
    from trader_core import signals as S          # tembel: pandas yalniz oynatimda yuklenir
    max_bars = MAX_BARS if max_bars is None else max_bars

    sgn = 1.0 if side == "long" else -1.0
    h_entry = entry_ms - entry_ms % HR_MS
    idx0 = None
    if h1.ms:
        # giris mumu dizinde mi (ms sirali): ikili arama yerine dogrusal (kisa pencere)
        for i, m in enumerate(h1.ms):
            if m == h_entry:
                idx0 = i
                break
    last_closed_h1 = (now_ms // HR_MS) * HR_MS - HR_MS      # son kapanmis 1h mumunun acilisi
    last_closed_15 = (now_ms // M15_MS) * M15_MS - M15_MS
    if idx0 is None:
        if h_entry > last_closed_h1:
            return ReplayResult("pending", gap_ms=h_entry, gap_kind="bars1h")
        return ReplayResult("gap", gap_ms=h_entry, gap_kind="bars1h")
    # bosluksuz 1h onek (idx0'dan): iz yolu YALNIZ bu onek icin tek seferde hesaplanir (onek-nedensel)
    n_av = 0
    while n_av < max_bars and idx0 + n_av < len(h1.ms) and h1.ms[idx0 + n_av] == h_entry + n_av * HR_MS:
        n_av += 1
    import pandas as pd
    path = None
    if n_av:
        sl = slice(idx0, idx0 + n_av)
        path = S.trail_stop_path(side, entry_price, initial_stop, pd.Series(h1.h[sl], dtype="float64"),
                                 pd.Series(h1.l[sl], dtype="float64"), pd.Series(h1.atr[sl], dtype="float64"),
                                 float(trail_atr)).to_numpy()
    r_price = abs(entry_price - initial_stop)
    cur = float(initial_stop)
    best = entry_price
    first_bar_ms = entry_ms - entry_ms % M15_MS
    fresh_ms: int | None = None          # yeni stopun gecerli oldugu ilk 15 dk mumunun acilisi (would_trigger denetimi)
    part_at: int | None = None           # kismi kapanisin dolacagi 15 dk mumunun acilisi (bekleyen)
    part_done: tuple[int, float, float] | None = None
    part_frac = float(modes.pt_frac) if modes is not None else 0.0   # kapanacak oran (adet yuvarlamasiyla ayarlanabilir)
    part_tried = False                   # motor kismiyi bir kez dener (done | skipped): tekrar yok
    best_h1 = -math.inf if side == "long" else math.inf     # kapanmis 1h mumlarin en iyi ucu (giris mumu dahil; motor ctx ile ayni)

    def mfe_r() -> float | None:
        return abs(best - entry_price) / r_price if r_price > 0 else None

    def fin(res: ReplayResult) -> ReplayResult:
        if part_done is not None:
            res.partial_ms, res.partial_price, res.partial_frac = part_done
        return res

    def market(bar_ms, k, reason) -> ReplayResult:
        o = m15[bar_ms][0]
        return fin(ReplayResult("ok", reason, bar_ms, _slip(o, side, slip_exit_bps), k + 1, mfe_r()))

    for k in range(max_bars):
        h_k = h_entry + k * HR_MS
        d_k = h_k + HR_MS
        # ---- (1) bu saatin 15 dk mumlari: bekleyen stop vurusu
        b = h_k if k else first_bar_ms
        while b < d_k:
            bar = m15.get(b)
            if bar is None:
                return ReplayResult("pending" if b > last_closed_15 else "gap", gap_ms=b, gap_kind="bars15")
            o, hi, lo, _c = bar
            if part_at == b:                                  # kismi kar alma: bu mumun acilisinda piyasa dolumu (stoptan once)
                part_done = (b, _slip(o, side, slip_exit_bps), part_frac)
                part_at = None
            if fresh_ms == b:
                fresh_ms = None
                beyond = o <= cur if side == "long" else o >= cur
                if beyond:                                    # would_trigger: yeni stop acilista zaten asilmis
                    best = max(best, hi) if side == "long" else min(best, lo)
                    return fin(ReplayResult("ok", "trail_stop", b, _slip(o, side, slip_exit_bps), k + 1, mfe_r()))
            best = max(best, hi) if side == "long" else min(best, lo)
            hit = (lo <= cur) if side == "long" else (hi >= cur)
            if hit:
                gap = (o <= cur) if side == "long" else (o >= cur)
                base = o if gap else cur
                reason = "trail_stop" if cur != initial_stop else "stop"
                return fin(ReplayResult("ok", reason, b, _slip(base, side, slip_stop_bps), k + 1, mfe_r()))
            b += M15_MS
        # ---- (2) 1h kapanisi D: motor siralamasi
        if k >= n_av:
            return ReplayResult("pending" if h_k > last_closed_h1 else "gap", gap_ms=h_k, gap_kind="bars1h")
        if S.regime_flip_exit(side, h1.regime[idx0 + k]):
            if d_k not in m15:
                return ReplayResult("pending" if d_k > last_closed_15 else "gap", gap_ms=d_k, gap_kind="bars15")
            return market(d_k, k, "regime_flip")
        stop = float(path[k])
        if modes is not None:
            hk, lk = h1.h[idx0 + k], h1.l[idx0 + k]
            if side == "long":
                best_h1 = max(best_h1, hk) if hk == hk else best_h1
            else:
                best_h1 = min(best_h1, lk) if lk == lk else best_h1
            bh = best_h1 if math.isfinite(best_h1) else None
            stop = XM.merge_stop(side, stop, XM.be_stop(side, entry_price, initial_stop, bh, modes))
        armed = stop != initial_stop
        close = h1.c[idx0 + k]
        if armed and ((stop >= close) if side == "long" else (stop <= close)):
            if d_k not in m15:
                return ReplayResult("pending" if d_k > last_closed_15 else "gap", gap_ms=d_k, gap_kind="bars15")
            return market(d_k, k, "trail_stop")
        tighter = (stop > cur + EPS) if side == "long" else (stop < cur - EPS)
        if tighter:
            cur = stop
            fresh_ms = d_k
        if (modes is not None and modes.partial and not part_tried and XM.partial_due(side, entry_price, initial_stop, bh, modes)):
            part_tried = True
            if lot_rules is not None and qty:
                q = XM.partial_qty(float(qty), modes.pt_frac, lot_rules[0], lot_rules[1], lot_rules[2], float(close))
                part_frac = 0.0 if q is None else q / float(qty)
            if part_frac > 0.0:
                if d_k not in m15:
                    return ReplayResult("pending" if d_k > last_closed_15 else "gap", gap_ms=d_k, gap_kind="bars15")
                part_at = d_k
        if k == max_bars - 1:                                  # ufuk: piyasaya gore degerle (dislanmaz; censored)
            px = _slip(close, side, slip_exit_bps)
            return fin(ReplayResult("ok", "horizon", d_k, px, max_bars, mfe_r(), censored=1))
    return ReplayResult("pending")                              # pragma: no cover (dongu horizon'da doner)


def prepare_h1(h1_rows: Sequence[tuple], h4_rows: Sequence[tuple], signal_params=None) -> H1Series:
    """1h/4h mumlarindan ATR(14, 1h) ve hizalanmis 4h rejim dizileri: MOTORLA AYNI kaynak (compute_signals'in `atr_tf` ve
    `regime` sutunlari; `regime.classify_series` + `align_to_base`). `signal_params`: islemin kendi surumunun SignalParams'i."""
    import pandas as pd

    from trader_core import arm_time as AT
    from trader_core import signals as S
    cols = ["open", "high", "low", "close"]

    def frame(rows):
        idx = pd.to_datetime([r[0] for r in rows], unit="ms", utc=True)
        df = pd.DataFrame([r[1:5] for r in rows], index=idx, columns=cols, dtype="float64")
        if rows and all(len(r) > 5 for r in rows):          # hacim varsa olu mum (hacim 0, o=h=l=c) tespiti mumkun; yoksa eski yol
            df["volume"] = [float(r[5]) for r in rows]
        return df
    p = signal_params if signal_params is not None else S.DEFAULT_SIGNAL_PARAMS
    h1, h4 = frame(h1_rows), frame(h4_rows)
    # MOTORLA AYNI olu mum cikarimi (seansli hisse/emtia perp'i): rejim 4s'in dolu mumlarindan, ATR/rejim 1s'in dolu mumlarindan; olu satirlar
    # son dolu satirdan tasinir. Olu mum yoksa (kripto) eski yol AYNEN (arm_time.regime_series/core_signals).
    reg = AT.regime_series(h4, p.regime_params())
    sig, _, _ = AT.core_signals(h1, reg, p)
    return H1Series([int(r[0]) for r in h1_rows], h1["open"].tolist(), h1["high"].tolist(), h1["low"].tolist(),
                    h1["close"].tolist(), sig["atr_tf"].tolist(), sig["regime"].tolist())


def price_result(res: ReplayResult, tr: TradeInput, *, taker_fee: float,
                 funding_of: Callable[[int, int], tuple[float | None, int | None]]) -> dict:
    """Oynatim sonucunu net R'ye cevirir. `funding_of(entry_ms, exit_ms)` -> (toplam odenen funding [para], eksik_ms|None).
    Eksik funding orani -> {'status': 'gap', ...}. Net R = (brut - fee_entry - fee_exit - funding) / planned_risk (defter payda)."""
    sgn = 1.0 if tr.side == "long" else -1.0
    entry_ms = to_ms(tr.entry_ts)
    fund, miss = funding_of(entry_ms, res.exit_ms)
    if miss is not None:
        return {"status": "gap", "gap_ms": miss, "gap_kind": "funding"}
    if res.partial_ms is not None and res.partial_price is not None and res.partial_frac:
        # kismi kar alma (docs/cikis-kipleri-spec.md): iki parca; funding adetle dogrusal (kalan parca tum sure, kapanan parca partial_ms'e dek)
        f = float(res.partial_frac)
        fund_p, miss_p = funding_of(entry_ms, res.partial_ms)
        if miss_p is not None:
            return {"status": "gap", "gap_ms": miss_p, "gap_kind": "funding"}
        fund = f * fund_p + (1.0 - f) * fund
        gross = sgn * (f * (res.partial_price - tr.entry_price) + (1.0 - f) * (res.exit_price - tr.entry_price)) * tr.qty
        fee_exit = tr.qty * (f * res.partial_price + (1.0 - f) * res.exit_price) * taker_fee
    else:
        gross = sgn * (res.exit_price - tr.entry_price) * tr.qty
        fee_exit = tr.qty * res.exit_price * taker_fee
    risk = tr.planned_risk
    return {"status": "ok", "gross_r": gross / risk, "fee_r": (tr.fee_entry + fee_exit) / risk, "funding_r": fund / risk,
            "net_r": (gross - tr.fee_entry - fee_exit - fund) / risk}


# ------------------------------------------------------------------------------------------------ depo
_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ecf_outcomes (
  bot TEXT NOT NULL CHECK (bot IN ('learner','twin')),
  source TEXT NOT NULL CHECK (source IN ('paper','testnet','live','backtest')),
  run_id TEXT NOT NULL DEFAULT '',
  trade_id INTEGER NOT NULL,
  pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT, trigger_tf TEXT,
  entry_ts TEXT NOT NULL, exit_ts_actual TEXT, actual_exit_reason TEXT, actual_net_r REAL, param_version_id INTEGER,
  param TEXT NOT NULL, value REAL NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('base','up','down','own')),
  exit_reason_sim TEXT NOT NULL CHECK (exit_reason_sim IN ('stop','trail_stop','regime_flip','horizon','data_gap','no_data')),
  exit_ts_sim TEXT, bars_held_sim INTEGER,
  gross_r REAL, fee_r REAL, funding_r REAL, net_r REAL, censored INTEGER, mfe_r_sim REAL,
  parity_gap_r REAL, reason_match INTEGER,
  trigger_source TEXT, grid_min INTEGER, cost_json TEXT, window_start_ts TEXT, window_end_ts TEXT,
  computed_at TEXT NOT NULL, version INTEGER NOT NULL, registry_id TEXT NOT NULL,
  PRIMARY KEY (bot, source, run_id, trade_id, param, value));
CREATE INDEX IF NOT EXISTS ix_ecf_entry ON ecf_outcomes (bot, source, entry_ts);
CREATE TABLE IF NOT EXISTS ecf_modes (
  bot TEXT NOT NULL CHECK (bot IN ('learner','twin')),
  source TEXT NOT NULL CHECK (source IN ('paper','testnet','live','backtest')),
  run_id TEXT NOT NULL DEFAULT '',
  trade_id INTEGER NOT NULL,
  pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT, trigger_tf TEXT,
  entry_ts TEXT NOT NULL, exit_ts_actual TEXT, actual_exit_reason TEXT, actual_net_r REAL, param_version_id INTEGER,
  trail_atr REAL NOT NULL,
  variant TEXT NOT NULL CHECK (variant IN ('off','breakeven','partial')),
  exit_reason_sim TEXT NOT NULL CHECK (exit_reason_sim IN ('stop','trail_stop','regime_flip','horizon','data_gap','no_data')),
  exit_ts_sim TEXT, bars_held_sim INTEGER,
  gross_r REAL, fee_r REAL, funding_r REAL, net_r REAL, censored INTEGER, mfe_r_sim REAL,
  partial_ts_sim TEXT, partial_price REAL, partial_frac REAL,
  trigger_source TEXT, grid_min INTEGER, cost_json TEXT, window_start_ts TEXT, window_end_ts TEXT,
  computed_at TEXT NOT NULL, version INTEGER NOT NULL, registry_id TEXT NOT NULL,
  PRIMARY KEY (bot, source, run_id, trade_id, variant));
CREATE INDEX IF NOT EXISTS ix_ecfm_entry ON ecf_modes (bot, source, entry_ts);
"""
_MCOLS = ("bot", "source", "run_id", "trade_id", "pair", "side", "setup", "trigger_tf", "entry_ts", "exit_ts_actual",
          "actual_exit_reason", "actual_net_r", "param_version_id", "trail_atr", "variant", "exit_reason_sim", "exit_ts_sim",
          "bars_held_sim", "gross_r", "fee_r", "funding_r", "net_r", "censored", "mfe_r_sim", "partial_ts_sim", "partial_price",
          "partial_frac", "trigger_source", "grid_min", "cost_json", "window_start_ts", "window_end_ts", "computed_at", "version",
          "registry_id")
_COLS = ("bot", "source", "run_id", "trade_id", "pair", "side", "setup", "trigger_tf", "entry_ts", "exit_ts_actual",
         "actual_exit_reason", "actual_net_r", "param_version_id", "param", "value", "role", "exit_reason_sim", "exit_ts_sim",
         "bars_held_sim", "gross_r", "fee_r", "funding_r", "net_r", "censored", "mfe_r_sim", "parity_gap_r", "reason_match",
         "trigger_source", "grid_min", "cost_json", "window_start_ts", "window_end_ts", "computed_at", "version", "registry_id")


class ExitCfStore:
    """exit_counterfactual.sqlite (var/<bot>/; bu isin TEK yazari). journal_mode=DELETE; `read_only=True` -> mode=ro, yazma yok."""

    def __init__(self, path, *, read_only: bool = False):
        self.path = os.fspath(path)
        self.read_only = read_only
        try:
            if read_only:
                if not os.path.exists(self.path):
                    raise ExitCfError("depo yok", "store_missing")
                self._db = sqlite3.connect("file:" + quote(os.path.abspath(self.path)) + "?mode=ro", uri=True, timeout=5.0,
                                           isolation_level=None)
                self._db.execute("PRAGMA busy_timeout=5000")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver != STORE_SCHEMA_VERSION:
                    raise ExitCfError(f"depo sema surumu {ver}", "store_schema")
            else:
                self._db = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
                self._db.execute("PRAGMA busy_timeout=5000")
                self._db.execute("PRAGMA journal_mode=DELETE")
                self._db.execute("PRAGMA synchronous=FULL")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver not in (0, STORE_SCHEMA_VERSION):
                    raise ExitCfError(f"depo sema surumu {ver}, beklenen {STORE_SCHEMA_VERSION}", "store_schema")
                self._db.executescript(_DDL)
                self._db.execute(f"PRAGMA user_version={STORE_SCHEMA_VERSION}")
        except sqlite3.Error as e:
            raise ExitCfError(f"depo acilamadi: {type(e).__name__}", "store_io") from e
        self._db.row_factory = sqlite3.Row

    def close(self) -> None:
        try:
            self._db.close()
        except sqlite3.Error:  # pragma: no cover
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def have(self, bot: str, source: str, run_id: str) -> dict[int, set]:
        """trade_id -> yazilmis `value` anahtarlari (round 6)."""
        out: dict[int, set] = {}
        try:
            for r in self._db.execute("SELECT trade_id, value FROM ecf_outcomes WHERE bot=? AND source=? AND run_id=? AND param=? "
                                      "AND version=?", (bot, source, run_id, PARAM, VERSION)):
                out.setdefault(r[0], set()).add(_vkey(r[1]))
        except sqlite3.Error as e:
            raise ExitCfError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
        return out

    def insert(self, rows: Iterable[Mapping]) -> int:
        """Idempotent: ayni anahtar varsa dokunmaz. Doner: yeni eklenen satir sayisi."""
        if self.read_only:
            raise ExitCfError("depo salt okunur", "read_only")
        sql = (f"INSERT INTO ecf_outcomes ({','.join(_COLS)}) VALUES ({','.join('?' * len(_COLS))}) "
               "ON CONFLICT (bot, source, run_id, trade_id, param, value) DO NOTHING")
        n = 0
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for r in rows:
                    n += self._db.execute(sql, [r.get(c) for c in _COLS]).rowcount
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.Error as e:
            raise ExitCfError(f"depo yazma hatasi: {type(e).__name__}", "store_io") from e
        return n


    def have_modes(self, bot: str, source: str, run_id: str) -> dict[int, set]:
        """trade_id -> yazilmis `variant` kumesi (ecf_modes)."""
        out: dict[int, set] = {}
        try:
            for r in self._db.execute("SELECT trade_id, variant FROM ecf_modes WHERE bot=? AND source=? AND run_id=? AND version=?",
                                      (bot, source, run_id, MODES_VERSION)):
                out.setdefault(r[0], set()).add(r[1])
        except sqlite3.Error as e:
            raise ExitCfError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
        return out

    def insert_modes(self, rows: Iterable[Mapping]) -> int:
        """Idempotent (ecf_modes): ayni anahtar varsa dokunmaz. Doner: yeni eklenen satir sayisi."""
        if self.read_only:
            raise ExitCfError("depo salt okunur", "read_only")
        sql = (f"INSERT INTO ecf_modes ({','.join(_MCOLS)}) VALUES ({','.join('?' * len(_MCOLS))}) "
               "ON CONFLICT (bot, source, run_id, trade_id, variant) DO NOTHING")
        n = 0
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for r in rows:
                    n += self._db.execute(sql, [r.get(c) for c in _MCOLS]).rowcount
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.Error as e:
            raise ExitCfError(f"depo yazma hatasi: {type(e).__name__}", "store_io") from e
        return n


# ------------------------------------------------------------------------------------------------ piyasa (salt okunur)
def _split_ranges(a: int, b: int, holdout: tuple[datetime, datetime] | None = None) -> list[tuple[int, int]]:
    """[a, b) araligini kilitli donemin DISINDA kalan en fazla iki parcaya boler: ust sinir <= HOLDOUT_START ya da alt sinir >=
    HOLDOUT_END. Hicbir sorgu kilitli aralik icinde bir deger sormaz (spec 4)."""
    if holdout is None and KILIT_ACIK:
        return [(a, b)] if a < b else []
    hs, he = (to_ms(holdout[0]), to_ms(holdout[1])) if holdout else (to_ms(HOLDOUT_START), to_ms(HOLDOUT_END))
    out = []
    if a < min(b, hs):
        out.append((a, min(b, hs)))
    if max(a, he) < b:
        out.append((max(a, he), b))
    return out


class MarketSource:
    """var/market.sqlite (mode=ro, duz sqlite3). Mum sorgulari kilitli donem disindaki iki parcaya bolunur; yalniz kapanistan
    SONRA yazilmis mumlar (written_ms >= acilis + tf) doner."""

    def __init__(self, path, *, holdout: tuple[datetime, datetime] | None = None):
        if not os.path.exists(path):
            raise ExitCfError("market.sqlite yok", "market_missing")
        self.holdout = holdout
        try:
            self._db = sqlite3.connect("file:" + quote(os.path.abspath(path)) + "?mode=ro", uri=True, timeout=5.0,
                                       isolation_level=None)
            self._db.execute("PRAGMA busy_timeout=5000")
            ver = self._db.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error as e:
            raise ExitCfError(f"market.sqlite acilamadi: {type(e).__name__}", "market_unreadable") from e
        if ver != MARKET_SCHEMA_VERSION:
            self._db.close()
            raise ExitCfError(f"market.sqlite user_version={ver}", "market_schema")

    def close(self) -> None:
        self._db.close()

    def bars(self, pair: str, tf: str, start_ms: int, end_ms: int, kind: str = "last") -> list[tuple]:
        tf_ms = {"15m": M15_MS, "1h": HR_MS, "4h": H4_MS}[tf]
        out: list[tuple] = []
        try:
            for a, b in _split_ranges(start_ms, end_ms, self.holdout):
                out += self._db.execute(
                    "SELECT open_ms,o,h,l,c,v FROM bars WHERE kind=? AND pair=? AND tf=? AND open_ms>=? AND open_ms<? "
                    "AND written_ms>=open_ms+? ORDER BY open_ms", (kind, pair, tf, a, b, tf_ms)).fetchall()
        except sqlite3.Error as e:
            raise ExitCfError(f"market okuma hatasi: {type(e).__name__}", "market_unreadable") from e
        return [tuple(r) for r in out]

    def rules_json(self, pair: str) -> str | None:
        """market.sqlite `rules` tablosundaki ham kural JSON'u (yoksa/okunamazsa None); ayristirma cagirana ait (trader_core -> trader_engine yok)."""
        try:
            row = self._db.execute("SELECT json FROM rules WHERE pair=?", (pair,)).fetchone()
        except sqlite3.Error:
            return None
        return None if row is None else row[0]

    def funding(self, pair: str, start_ms: int, end_ms: int) -> list[tuple]:
        """(ts_ms, rate, mark) satirlari, start <= ts < end (8 saatlik izgaraya yuvarlama cagirana ait)."""
        out: list[tuple] = []
        try:
            for a, b in _split_ranges(start_ms, end_ms, self.holdout):
                out += self._db.execute("SELECT ts_ms, rate, mark FROM funding WHERE pair=? AND ts_ms>=? AND ts_ms<? ORDER BY ts_ms",
                                        (pair, a, b)).fetchall()
        except sqlite3.Error as e:
            raise ExitCfError(f"market okuma hatasi: {type(e).__name__}", "market_unreadable") from e
        return [tuple(r) for r in out]


# ------------------------------------------------------------------------------------------------ is
@dataclass
class RunResult:
    scanned: int = 0
    already: int = 0
    computed: int = 0
    pending: int = 0
    no_data: int = 0
    data_gap: int = 0
    censored: int = 0
    holdout_skipped: int = 0
    skipped_15m: int = 0
    excluded_exit_reason: int = 0
    rows_written: int = 0
    horizon_mtm: int = 0


def _alternatives(active: float, step: float, bounds: tuple[float, float]) -> list[tuple[str, float]]:
    """Aktif degerden (rol, deger): base her zaman; up/down yalniz lesson_bounds icinde."""
    lo, hi = bounds
    out = [("base", _vkey(active))]
    up, dn = _vkey(active + step), _vkey(active - step)
    if up <= hi + 1e-9:
        out.append(("up", up))
    if dn >= lo - 1e-9:
        out.append(("down", dn))
    return out


def _funding_fn(points: Sequence[tuple], now_ms: int, side: str, qty: float, fallback_mark: float):
    rates: dict[int, tuple[float, float | None]] = {}
    for ts, rate, mark in points:
        rates.setdefault(ts - ts % HR_MS, (float(rate), mark))   # kaydin KENDI saati (1s/4s/8s; trader_engine.funding.floor_funding_hour ile ayni)

    def fn(entry_ms: int, exit_ms: int):
        total = 0.0
        own = [t for t in rates if entry_ms < t <= exit_ms]       # izgara disi (4s/1s) kayit saatleri de odenir
        for t in sorted(set(funding_grid_times(entry_ms, exit_ms)) | set(own)):
            r = rates.get(t)
            if r is None:
                return None, t
            mk = r[1] if r[1] is not None and r[1] > 0 else fallback_mark
            total += funding_payment(side, qty, float(mk), r[0])
        return total, None
    return fn


def run_once(*, bot: str, trades: Sequence[TradeInput], market, store: ExitCfStore, now: datetime, active_value: float,
             step: float, bounds: tuple[float, float], cost_for: Callable[[TradeInput], Mapping],
             signal_params_for: Callable[[TradeInput], object | None] = lambda t: None, trigger_source: str = "last",
             holdout: tuple[datetime, datetime] | None = None, dry_run: bool = False,
             max_trades: int = MAX_TRADES_PER_RUN, feeds_for: Callable[[TradeInput], object] | None = None) -> RunResult:
    """Kapanmis T1 islemlerini oynatir. `market`: .bars(pair, tf, start_ms, end_ms, kind) ve .funding(pair, start_ms, end_ms)
    sunan nesne (MarketSource ya da gelistirme makinesinde feather kaynagi). Tek islem: tum roller (base/up/down/own) AYNI
    gece birlikte yazilir; veri sonuna gelindiyse `pending` (sonraki gece). `now` enjekte edilir. Ayni calisma tekrarlanirsa
    ayni satirlar (idempotans)."""
    now = _utc(now)
    now_ms = to_ms(now)
    res = RunResult()
    have_cache: dict[tuple[str, str], dict[int, set]] = {}
    batch: list[dict] = []
    done_this_run = 0
    for tr in sorted(trades, key=lambda t: (to_ms(t.entry_ts), t.trade_id)):
        if tr.setup != "T1":
            continue
        res.scanned += 1
        if tr.trigger_tf != "1h":
            res.skipped_15m += 1
            continue
        if tr.exit_reason in EXCLUDED_EXIT_REASONS:
            res.excluded_exit_reason += 1
            continue
        if tr.exit_ts is None or to_ms(tr.exit_ts) > now_ms:
            continue                                              # henuz kapanmamis (exit_ts <= now sarti)
        if not _valid_trade(tr):
            res.no_data += 1
            continue
        entry_ms = to_ms(tr.entry_ts)
        w_start = entry_ms - WARMUP_DAYS * DAY_MS
        w_end = min(entry_ms + MAX_BARS * HR_MS + 2 * HR_MS, now_ms)
        if holdout_hit(w_start, w_end, holdout):
            res.holdout_skipped += 1
            continue
        key = (tr.source, tr.run_id)
        if key not in have_cache:
            have_cache[key] = store.have(bot, tr.source, tr.run_id)
        have = have_cache[key].get(tr.trade_id, set())
        wanted = _alternatives(active_value, step, bounds)
        own = _vkey(tr.own_value) if tr.own_value is not None and _fin(tr.own_value) else None
        if own is not None and own not in {v for _, v in wanted}:
            wanted.append(("own", own))
        missing = [(role, v) for role, v in wanted if v not in have]
        if not missing:
            res.already += 1
            continue
        if done_this_run >= max_trades:
            res.pending += 1
            continue
        out = _compute_trade(tr, missing, own=own, market=market, now_ms=now_ms, cost=cost_for(tr),
                             signal_params=signal_params_for(tr), trigger_source=trigger_source, bot=bot, now=now,
                             holdout=holdout, w_start=w_start, w_end=w_end)
        if out is None:
            res.pending += 1
            continue
        rows, flags = out
        done_this_run += 1
        batch += rows
        res.computed += 1
        res.no_data += int("no_data" in flags)
        res.data_gap += int("data_gap" in flags)
        res.censored += sum(1 for r in rows if r.get("censored") == 1)
        res.horizon_mtm += sum(1 for r in rows if r["exit_reason_sim"] == "horizon")
    if not dry_run and batch:
        res.rows_written = store.insert(batch)
    elif dry_run:
        res.rows_written = 0
    return res


def _valid_trade(tr: TradeInput) -> bool:
    if tr.side not in ("long", "short"):
        return False
    if not all(_fin(x) for x in (tr.entry_price, tr.qty, tr.planned_risk, tr.initial_stop, tr.fee_entry)):
        return False
    if tr.planned_risk <= 0 or tr.qty <= 0 or tr.entry_price <= 0:
        return False
    return (tr.initial_stop < tr.entry_price) if tr.side == "long" else (tr.initial_stop > tr.entry_price)


def _row(tr: TradeInput, bot: str, role: str, value: float, now: datetime, trigger_source: str, cost: Mapping,
         w_start: int, w_end_ms: int | None, sim: dict | None, reason: str, rr: ReplayResult | None, own: float | None) -> dict:
    base = {"bot": bot, "source": tr.source, "run_id": tr.run_id, "trade_id": tr.trade_id, "pair": tr.pair, "side": tr.side,
            "setup": tr.setup, "trigger_tf": tr.trigger_tf, "entry_ts": _fmt(tr.entry_ts),
            "exit_ts_actual": _fmt(tr.exit_ts) if tr.exit_ts else None, "actual_exit_reason": tr.exit_reason,
            "actual_net_r": tr.actual_net_r, "param_version_id": tr.param_version_id, "param": PARAM, "value": value,
            "role": role, "exit_reason_sim": reason, "exit_ts_sim": None, "bars_held_sim": None, "gross_r": None,
            "fee_r": None, "funding_r": None, "net_r": None, "censored": None, "mfe_r_sim": None, "parity_gap_r": None,
            "reason_match": None, "trigger_source": trigger_source, "grid_min": GRID_MIN,
            "cost_json": json.dumps(dict(cost), sort_keys=True), "window_start_ts": fmt_ms(w_start),
            "window_end_ts": fmt_ms(w_end_ms) if w_end_ms is not None else None, "computed_at": _fmt(now),
            "version": VERSION, "registry_id": REGISTRY_ID}
    if sim is not None and rr is not None:
        base.update(exit_ts_sim=fmt_ms(rr.exit_ms), bars_held_sim=rr.bars_held, gross_r=sim["gross_r"], fee_r=sim["fee_r"],
                    funding_r=sim["funding_r"], net_r=sim["net_r"], censored=rr.censored, mfe_r_sim=rr.mfe_r)
        if own is not None and abs(value - own) < 1e-9 and tr.actual_net_r is not None:
            base["parity_gap_r"] = sim["net_r"] - float(tr.actual_net_r)
            base["reason_match"] = int(reason == tr.exit_reason)
    return base


def _compute_trade(tr: TradeInput, missing: list, *, own, market, now_ms, cost, signal_params, trigger_source, bot, now,
                   holdout, w_start, w_end):
    """-> (satirlar, bayraklar) ya da None (pending). Okuma hatasi (veri yok) -> no_data satirlari."""
    pair = tr.pair
    entry_ms = to_ms(tr.entry_ts)
    kind = "mark" if trigger_source == "mark" else "last"
    flags: set[str] = set()

    def finalize(rows_spec):
        return rows_spec, flags

    def nodata(reason="no_data"):
        flags.add(reason)
        return [_row(tr, bot, role, v, now, trigger_source, cost, w_start, w_end, None, reason, None, own)
                for role, v in missing], flags
    try:
        m15_rows = market.bars(pair, "15m", entry_ms - entry_ms % M15_MS, w_end, kind)
        h1_rows = market.bars(pair, "1h", w_start, w_end, "last")
        h4_rows = market.bars(pair, "4h", w_start - H4_MS, w_end, "last")
        f_pts = market.funding(pair, entry_ms - H8_MS, w_end + H8_MS)
    except ExitCfError:
        raise
    except Exception:                                               # noqa: BLE001  kaynak okunamadi: yapisal veri yok
        return nodata()
    if not m15_rows or not h1_rows or len(h4_rows) < 120:          # seri hic yok / rejim isinmasi yetersiz: yapisal no_data
        return nodata()
    h1 = prepare_h1(h1_rows, h4_rows, signal_params)
    m15 = {r[0]: r[1:5] for r in m15_rows}
    fund = _funding_fn(f_pts, now_ms, tr.side, tr.qty, tr.entry_price)
    taker = float(cost.get("taker_fee", 0.0005))
    rows: list[dict] = []
    for role, v in missing:
        rr = replay_trail(side=tr.side, entry_price=tr.entry_price, initial_stop=tr.initial_stop, entry_ms=entry_ms,
                          trail_atr=v, h1=h1, m15=m15, now_ms=now_ms, slip_exit_bps=float(cost.get("slip_exit_bps", 2.0)),
                          slip_stop_bps=float(cost.get("slip_stop_bps", 5.0)), modes=tr.own_modes)
        if rr.status == "ok":
            sim = price_result(rr, tr, taker_fee=taker, funding_of=fund)
            if sim["status"] == "ok":
                rows.append(_row(tr, bot, role, v, now, trigger_source, cost, w_start, rr.exit_ms, sim, rr.reason, rr, own))
                continue
            gap_ms, gkind = sim["gap_ms"], "funding"
        else:
            gap_ms, gkind = rr.gap_ms, rr.gap_kind
        if rr.status == "pending" or gap_ms is None or now_ms < gap_ms + int(GAP_GRACE.total_seconds() * 1000):
            return None                                           # bekle: tum roller birlikte yazilir
        reason = "no_data" if gkind == "funding" else "data_gap"
        flags.add(reason)
        rows.append(_row(tr, bot, role, v, now, trigger_source, cost, w_start, gap_ms, None, reason, None, own))
    return finalize(rows)


# ------------------------------------------------------------------------------------------------ cikis kipleri (exitcf-v2)
@dataclass
class ModesRunResult:
    scanned: int = 0
    already: int = 0
    computed: int = 0
    pending: int = 0
    no_data: int = 0
    data_gap: int = 0
    censored: int = 0
    holdout_skipped: int = 0
    skipped_15m: int = 0
    excluded_exit_reason: int = 0
    rows_written: int = 0
    partial_fired: int = 0


def _mrow(tr: TradeInput, bot: str, variant: str, trail: float, now: datetime, trigger_source: str, cost: Mapping, w_start: int,
          w_end_ms: int | None, sim: dict | None, reason: str, rr: ReplayResult | None) -> dict:
    row = {"bot": bot, "source": tr.source, "run_id": tr.run_id, "trade_id": tr.trade_id, "pair": tr.pair, "side": tr.side,
           "setup": tr.setup, "trigger_tf": tr.trigger_tf, "entry_ts": _fmt(tr.entry_ts),
           "exit_ts_actual": _fmt(tr.exit_ts) if tr.exit_ts else None, "actual_exit_reason": tr.exit_reason,
           "actual_net_r": tr.actual_net_r, "param_version_id": tr.param_version_id, "trail_atr": _vkey(trail),
           "variant": variant, "exit_reason_sim": reason, "exit_ts_sim": None, "bars_held_sim": None, "gross_r": None,
           "fee_r": None, "funding_r": None, "net_r": None, "censored": None, "mfe_r_sim": None, "partial_ts_sim": None,
           "partial_price": None, "partial_frac": None, "trigger_source": trigger_source, "grid_min": GRID_MIN,
           "cost_json": json.dumps(dict(cost), sort_keys=True), "window_start_ts": fmt_ms(w_start),
           "window_end_ts": fmt_ms(w_end_ms) if w_end_ms is not None else None, "computed_at": _fmt(now),
           "version": MODES_VERSION, "registry_id": MODES_REGISTRY_ID}
    if sim is not None and rr is not None:
        row.update(exit_ts_sim=fmt_ms(rr.exit_ms), bars_held_sim=rr.bars_held, gross_r=sim["gross_r"], fee_r=sim["fee_r"],
                   funding_r=sim["funding_r"], net_r=sim["net_r"], censored=rr.censored, mfe_r_sim=rr.mfe_r)
        if rr.partial_ms is not None:
            row.update(partial_ts_sim=fmt_ms(rr.partial_ms), partial_price=rr.partial_price, partial_frac=rr.partial_frac)
    return row


def _modes_for_variant(variant: str) -> XM.ExitModes | None:
    """`off`: kip yok; `breakeven` / `partial`: yalniz o kip, varsayilan sayilarla (spec 3; on kayitli, degismez)."""
    if variant == "off":
        return None
    return XM.from_flags(variant == "breakeven", variant == "partial")


def _compute_modes_trade(tr: TradeInput, missing: list[str], *, trail: float, market, now_ms, cost, signal_params,
                         trigger_source, bot, now, w_start, w_end, lot_rules=None):
    """-> (satirlar, bayraklar) ya da None (pending). v1 `_compute_trade` ile ayni veri/oynatim; fark yalniz `modes`."""
    pair = tr.pair
    entry_ms = to_ms(tr.entry_ts)
    kind = "mark" if trigger_source == "mark" else "last"
    flags: set[str] = set()

    def nodata(reason="no_data"):
        flags.add(reason)
        return [_mrow(tr, bot, v, trail, now, trigger_source, cost, w_start, w_end, None, reason, None) for v in missing], flags
    try:
        m15_rows = market.bars(pair, "15m", entry_ms - entry_ms % M15_MS, w_end, kind)
        h1_rows = market.bars(pair, "1h", w_start, w_end, "last")
        h4_rows = market.bars(pair, "4h", w_start - H4_MS, w_end, "last")
        f_pts = market.funding(pair, entry_ms - H8_MS, w_end + H8_MS)
    except ExitCfError:
        raise
    except Exception:                                               # noqa: BLE001
        return nodata()
    if not m15_rows or not h1_rows or len(h4_rows) < 120:
        return nodata()
    h1 = prepare_h1(h1_rows, h4_rows, signal_params)
    m15 = {r[0]: r[1:5] for r in m15_rows}
    fund = _funding_fn(f_pts, now_ms, tr.side, tr.qty, tr.entry_price)
    taker = float(cost.get("taker_fee", 0.0005))
    rows: list[dict] = []
    for v in missing:
        rr = replay_trail(side=tr.side, entry_price=tr.entry_price, initial_stop=tr.initial_stop, entry_ms=entry_ms,
                          trail_atr=trail, h1=h1, m15=m15, now_ms=now_ms, slip_exit_bps=float(cost.get("slip_exit_bps", 2.0)),
                          slip_stop_bps=float(cost.get("slip_stop_bps", 5.0)), modes=_modes_for_variant(v), qty=tr.qty,
                          lot_rules=lot_rules)
        if rr.status == "ok":
            sim = price_result(rr, tr, taker_fee=taker, funding_of=fund)
            if sim["status"] == "ok":
                rows.append(_mrow(tr, bot, v, trail, now, trigger_source, cost, w_start, rr.exit_ms, sim, rr.reason, rr))
                continue
            gap_ms, gkind = sim["gap_ms"], "funding"
        else:
            gap_ms, gkind = rr.gap_ms, rr.gap_kind
        if rr.status == "pending" or gap_ms is None or now_ms < gap_ms + int(GAP_GRACE.total_seconds() * 1000):
            return None
        reason = "no_data" if gkind == "funding" else "data_gap"
        flags.add(reason)
        rows.append(_mrow(tr, bot, v, trail, now, trigger_source, cost, w_start, gap_ms, None, reason, None))
    return rows, flags


def run_modes_once(*, bot: str, trades: Sequence[TradeInput], market, store: ExitCfStore, now: datetime, active_value: float,
                   cost_for: Callable[[TradeInput], Mapping], signal_params_for: Callable[[TradeInput], object | None] = lambda t: None,
                   trigger_source: str = "last", holdout: tuple[datetime, datetime] | None = None, dry_run: bool = False,
                   max_trades: int = MAX_TRADES_PER_RUN,
                   rules_for: Callable[[str], tuple[float, float, float] | None] | None = None) -> ModesRunResult:
    """Kapanmis T1 islemlerini cikis kipleriyle de oynatir: her islem icin `off` (kip yok), `breakeven` (yalniz basa-bas),
    `partial` (yalniz kismi) -- hepsi AKTIF `trail_atr` ile, ayni gece birlikte. Uygunluk/kilitli donem/ufuk/pending kurallari v1 ile
    ayni (spec 2-4). `rules_for(pair)` -> (adim, min adet, min notional) | None: kismi adet motorla ayni yuvarlamayla hesaplanir
    (spec 5 Parite); None/verilmezse tam oran (`pt_frac`)."""
    now = _utc(now)
    now_ms = to_ms(now)
    res = ModesRunResult()
    have_cache: dict[tuple[str, str], dict[int, set]] = {}
    batch: list[dict] = []
    done_this_run = 0
    for tr in sorted(trades, key=lambda t: (to_ms(t.entry_ts), t.trade_id)):
        if tr.setup != "T1":
            continue
        res.scanned += 1
        if tr.trigger_tf != "1h":
            res.skipped_15m += 1
            continue
        if tr.exit_reason in EXCLUDED_EXIT_REASONS:
            res.excluded_exit_reason += 1
            continue
        if tr.exit_ts is None or to_ms(tr.exit_ts) > now_ms:
            continue
        if not _valid_trade(tr):
            res.no_data += 1
            continue
        entry_ms = to_ms(tr.entry_ts)
        w_start = entry_ms - WARMUP_DAYS * DAY_MS
        w_end = min(entry_ms + MAX_BARS * HR_MS + 2 * HR_MS, now_ms)
        if holdout_hit(w_start, w_end, holdout):
            res.holdout_skipped += 1
            continue
        key = (tr.source, tr.run_id)
        if key not in have_cache:
            have_cache[key] = store.have_modes(bot, tr.source, tr.run_id)
        have = have_cache[key].get(tr.trade_id, set())
        missing = [v for v in MODE_VARIANTS if v not in have]
        if not missing:
            res.already += 1
            continue
        if done_this_run >= max_trades:
            res.pending += 1
            continue
        out = _compute_modes_trade(tr, missing, trail=_vkey(active_value), market=market, now_ms=now_ms, cost=cost_for(tr),
                                   signal_params=signal_params_for(tr), trigger_source=trigger_source, bot=bot, now=now,
                                   w_start=w_start, w_end=w_end, lot_rules=rules_for(tr.pair) if rules_for else None)
        if out is None:
            res.pending += 1
            continue
        rows, flags = out
        done_this_run += 1
        batch += rows
        res.computed += 1
        res.no_data += int("no_data" in flags)
        res.data_gap += int("data_gap" in flags)
        res.censored += sum(1 for r in rows if r.get("censored") == 1)
        res.partial_fired += sum(1 for r in rows if r.get("partial_ts_sim"))
    if not dry_run and batch:
        res.rows_written = store.insert_modes(batch)
    return res


def deltas_modes(path, bot: str, *, now: datetime, days: int = 120, mode: str, sources: Sequence[str] = SOURCES_VERDICT,
                 run_id: str | None = None, with_r: bool = False) -> list[dict]:
    """(`with_r=True`: her satira `on_r`/`off_r` eklenir; otomatik geri alma olcutu icin.)
    Her islem icin Delta_r = net_r(mode acik) - net_r(kapali) (yalniz window_end_ts <= now; ikisi de sayisal; en yuksek
    `version`). Tablo/dosya yoksa [] (kanit yok). Doner: [{source, run_id, trade_id, entry_ts, delta_r, censored,
    partial_fired}]. Salt okunur; depo bozuksa ExitCfError."""
    if mode not in MODE_NAMES:
        raise ExitCfError("mode breakeven|partial olmali", "bad_args")
    now = _utc(now)
    lo, hi = _fmt(now - timedelta(days=days)), _fmt(now)
    with _open_ro(path) as st:
        try:
            ver = st._db.execute("SELECT MAX(version) FROM ecf_modes WHERE bot=?", (bot,)).fetchone()[0]
        except sqlite3.OperationalError:
            return []                                              # eski depo: tablo yok (kanit yok)
        except sqlite3.Error as e:
            raise ExitCfError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
        if ver is None:
            return []
        try:
            qs = ",".join("?" * len(sources))
            args: list = [bot, ver, *sources, lo, hi, hi]
            sql = ("SELECT source, run_id, trade_id, entry_ts, variant, net_r, censored, partial_ts_sim FROM ecf_modes "
                   f"WHERE bot=? AND version=? AND source IN ({qs}) AND entry_ts>=? AND entry_ts<? AND window_end_ts<=? "
                   "AND net_r IS NOT NULL")
            if run_id is not None:
                sql += " AND run_id=?"
                args.append(run_id)
            rows = st._db.execute(sql, args).fetchall()
        except sqlite3.Error as e:
            raise ExitCfError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    by_trade: dict[tuple, dict] = {}
    for r in rows:
        by_trade.setdefault((r["source"], r["run_id"], r["trade_id"]), {})[r["variant"]] = r
    out = []
    for (src, rid, tid), vs in sorted(by_trade.items(), key=lambda kv: ((kv[1].get("off") or next(iter(kv[1].values())))["entry_ts"], kv[0][2])):
        off, on = vs.get("off"), vs.get(mode)
        if off is None or on is None:
            continue
        out.append({"source": src, "run_id": rid, "trade_id": tid, "entry_ts": off["entry_ts"],
                    "delta_r": float(on["net_r"]) - float(off["net_r"]),
                    "censored": int(bool(off["censored"]) or bool(on["censored"])),
                    "partial_fired": int(bool(on["partial_ts_sim"])),
                    **({"on_r": float(on["net_r"]), "off_r": float(off["net_r"])} if with_r else {})})
    return out


# ------------------------------------------------------------------------------------------------ okuma (ders / rapor)
def _open_ro(path):
    if not os.path.exists(path):
        raise ExitCfError("depo yok", "store_missing")
    return ExitCfStore(path, read_only=True)


def deltas(path, bot: str, *, now: datetime, days: int = 120, direction: str, sources: Sequence[str] = SOURCES_VERDICT,
           run_id: str | None = None) -> list[dict]:
    """Her islem icin Delta_r = net_r(alt) - net_r(taban) (yalniz window_end_ts <= now; taban VE alternatif ikisi de sayisal;
    en yuksek `version`). Taban: islemin en son hesaplanan `base` satiri; alternatif: taban degerinin +/- LESSON_STEP'i (up/down)
    rolunde. Doner: [{source, run_id, trade_id, entry_ts, delta_r, censored, base_value, alt_value, base_net_r, alt_net_r}].
    `censored` = taban ya da alternatif yolu ufukta kesildiyse 1. Salt okunur; depo yok/bozuk => ExitCfError."""
    if direction not in ("up", "down"):
        raise ExitCfError("direction up|down olmali", "bad_args")
    now = _utc(now)
    lo = _fmt(now - timedelta(days=days))
    hi = _fmt(now)
    with _open_ro(path) as st:
        try:
            ver = st._db.execute("SELECT MAX(version) FROM ecf_outcomes WHERE bot=?", (bot,)).fetchone()[0]
            if ver is None:
                return []
            qs = ",".join("?" * len(sources))
            args: list = [bot, ver, PARAM, *sources, lo, hi, hi]
            sql = ("SELECT source, run_id, trade_id, entry_ts, value, role, net_r, censored, computed_at FROM ecf_outcomes "
                   f"WHERE bot=? AND version=? AND param=? AND source IN ({qs}) AND entry_ts>=? AND entry_ts<? "
                   "AND window_end_ts<=? AND net_r IS NOT NULL")
            if run_id is not None:
                sql += " AND run_id=?"
                args.append(run_id)
            rows = st._db.execute(sql, args).fetchall()
        except sqlite3.Error as e:
            raise ExitCfError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    by_trade: dict[tuple, list] = {}
    for r in rows:
        by_trade.setdefault((r["source"], r["run_id"], r["trade_id"]), []).append(r)
    out = []
    for (src, rid, tid), rs in sorted(by_trade.items(), key=lambda kv: (kv[1][0]["entry_ts"], kv[0][2])):
        bases = [r for r in rs if r["role"] == "base"]
        if not bases:
            continue
        b = max(bases, key=lambda r: (r["computed_at"], r["value"]))
        want = _vkey(b["value"] + (_step() if direction == "up" else -_step()))
        alts = [r for r in rs if r["role"] == direction and abs(_vkey(r["value"]) - want) < 1e-9]
        if not alts:
            continue
        a = alts[0]
        out.append({"source": src, "run_id": rid, "trade_id": tid, "entry_ts": b["entry_ts"],
                    "delta_r": float(a["net_r"]) - float(b["net_r"]),
                    "censored": int(bool(b["censored"]) or bool(a["censored"])), "base_value": b["value"],
                    "alt_value": a["value"], "base_net_r": float(b["net_r"]), "alt_net_r": float(a["net_r"])})
    return out


def _step() -> float:
    from trader_core import ledger as L              # ledger stdlib+sqlite (pandas yok); LESSON_STEP tek kaynak
    return float(L.LESSON_STEP[PARAM])


def parity_stats(path, bot: str, *, now: datetime, days: int = 120, sources: Sequence[str] = SOURCES_VERDICT) -> dict:
    """Kanit penceresindeki TUM parite satirlari (kendi degerinde oynatim): n, medyan |gap|, ortalama gap, neden uyumu.
    Gecerli oynatim (net_r sayisal ve parity_gap_r dolu) olmayan satirlar sayilmaz. Esikler spec 8 (on kayitli)."""
    now = _utc(now)
    lo, hi = _fmt(now - timedelta(days=days)), _fmt(now)
    qs = ",".join("?" * len(sources))
    with _open_ro(path) as st:
        try:
            ver = st._db.execute("SELECT MAX(version) FROM ecf_outcomes WHERE bot=?", (bot,)).fetchone()[0]
            rows = [] if ver is None else st._db.execute(
                f"SELECT parity_gap_r, reason_match FROM ecf_outcomes WHERE bot=? AND version=? AND param=? "
                f"AND source IN ({qs}) AND entry_ts>=? AND entry_ts<? AND window_end_ts<=? AND parity_gap_r IS NOT NULL",
                [bot, ver, PARAM, *sources, lo, hi, hi]).fetchall()
        except sqlite3.Error as e:
            raise ExitCfError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    n = len(rows)
    if not n:
        return {"n": 0, "median_abs_r": None, "mean_r": None, "reason_match_rate": None, "status": "parity_unknown"}
    gaps = sorted(abs(float(r[0])) for r in rows)
    med = gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2.0
    mean = sum(float(r[0]) for r in rows) / n
    match = sum(int(r[1] or 0) for r in rows) / n
    if n < PARITY_MIN_N:
        status = "parity_unknown"
    elif med <= PARITY_MEDIAN_ABS_R and abs(mean) <= PARITY_MEAN_ABS_R and match >= PARITY_REASON_MATCH:
        status = "ok"
    else:
        status = "degraded"
    return {"n": n, "median_abs_r": med, "mean_r": mean, "reason_match_rate": match, "status": status}


def summary(path, bot: str, *, now: datetime, days: int = 120) -> dict:
    """Satir sayilari (tani / rapor): {rows, trades, no_data, data_gap}."""
    with _open_ro(path) as st:
        try:
            r = st._db.execute(
                "SELECT COUNT(*), COUNT(DISTINCT source||'/'||run_id||'/'||trade_id), "
                "SUM(exit_reason_sim='no_data'), SUM(exit_reason_sim='data_gap') FROM ecf_outcomes WHERE bot=? AND version=?",
                (bot, VERSION)).fetchone()
        except sqlite3.Error as e:
            raise ExitCfError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    return {"rows": r[0] or 0, "trades": r[1] or 0, "no_data": r[2] or 0, "data_gap": r[3] or 0}


# ------------------------------------------------------------------------------------------------ kayit denetimi
def registry_check(csv_path, registry_id: str | None = None) -> tuple[bool, str]:
    """research/trial_registry.csv (yalniz gelistirme makinesinde var) icinde on kayit satiri var mi? Sunucuda CSV yoktur:
    cagiran dosya yoksa denetimi atlar (spec 0). `registry_id` verilmezse v1 (`REGISTRY_ID`)."""
    import csv
    rid = registry_id or REGISTRY_ID
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("id") or "").strip() == rid or (row.get("id") or "").strip().startswith(rid + "_"):
                    return True, "ok"
    except OSError as e:
        return False, f"kayit dosyasi okunamadi: {type(e).__name__}"
    return False, f"{rid} satiri yok"


def modes_registry_row() -> dict:
    """exitcf-v2 on kayit satiri (docs/cikis-kipleri-spec.md 6): 2 alternatif (breakeven, partial) => n_trials katkisi 2."""
    return {"id": MODES_REGISTRY_ID, "strategy": "TraderV1b",
            "params": json.dumps({"modes": list(MODE_NAMES), "breakeven": {"trigger_r": XM.BE_TRIGGER_R, "offset_bps": XM.BE_OFFSET_BPS},
                                  "partial": {"trigger_r": XM.PT_TRIGGER_R, "frac": XM.PT_FRAC}},
                                 ensure_ascii=False, separators=(",", ":")),
            "n_trials": 2, "version": MODES_VERSION}


# ------------------------------------------------------------------------------------------------ backtest kaynagi (YALNIZ gelistirme)
BACKTEST_RUNS_ALLOWED = ("1h_IS_f1_s0_native_last",)      # spec 2.2: sabit tek kosu; digerleri listeye girmez


class FeatherSource:
    """`var/history/<PAIR>_<QUOTE>-<tf>-futures.feather` (pyarrow; sunucuda yok => yalniz gelistirme makinesi). Kilitli donem: once
    yalniz `date` sutunu okunur, sonra OHLC YALNIZ kilitli donemin disindaki satir dilimlerinden alinir (spec 4)."""

    def __init__(self, history_dir, *, holdout: tuple[datetime, datetime] | None = None):
        self.dir = history_dir
        self.holdout = holdout

    @staticmethod
    def stem(pair: str) -> str:
        c = pair.strip().upper().split(":", 1)[0]
        return c.replace("/", "_") + "_" + c.split("/")[1]

    def _path(self, pair: str, suffix: str) -> str:
        return os.path.join(os.fspath(self.dir), f"{self.stem(pair)}-{suffix}.feather")

    def _load(self, path: str, cols: Sequence[str], ranges_fn):
        """-> (ms int64 dizi, {kolon: dizi}) YALNIZ `ranges_fn(ms)` ile secilen satir dilimleri icin. Dosya yoksa FileNotFoundError."""
        import numpy as np
        import pyarrow as pa
        import pyarrow.feather as pf
        t0 = pf.read_table(path, columns=["date"], memory_map=True)
        col = t0.column("date")
        raw = col.combine_chunks().cast(pa.int64()).to_numpy(zero_copy_only=False)
        ms = {"ms": raw, "s": raw * 1000, "us": raw // 1000, "ns": raw // 1_000_000}[col.type.unit].astype("int64", copy=False)
        spans = ranges_fn(ms)
        if not spans:
            return np.zeros(0, dtype="int64"), {c: np.zeros(0) for c in cols}
        t = pf.read_table(path, columns=list(cols), memory_map=True)
        parts = {c: [] for c in cols}
        mparts = []
        for i, j in spans:
            mparts.append(ms[i:j])
            for c in cols:
                parts[c].append(t.column(c).slice(i, j - i).combine_chunks().to_numpy(zero_copy_only=False).astype("float64"))
        return np.concatenate(mparts), {c: np.concatenate(v) for c, v in parts.items()}

    def _spans(self, a: int, b: int):
        def fn(ms):
            import numpy as np
            out = []
            for x, y in _split_ranges(a, b, self.holdout):
                i, j = int(np.searchsorted(ms, x, "left")), int(np.searchsorted(ms, y, "left"))
                if j > i:
                    out.append((i, j))
            return out
        return fn

    def bars(self, pair: str, tf: str, start_ms: int, end_ms: int, kind: str = "last") -> list[tuple]:
        suffix = f"{tf}-futures" if kind == "last" else f"{tf}-mark"
        path = self._path(pair, suffix)
        if not os.path.exists(path):
            return []
        ms, cols = self._load(path, ("open", "high", "low", "close", "volume"), self._spans(start_ms, end_ms))
        return [(int(m), float(o), float(h), float(lo), float(c), float(v))
                for m, o, h, lo, c, v in zip(ms, cols["open"], cols["high"], cols["low"], cols["close"], cols["volume"])]

    def funding(self, pair: str, start_ms: int, end_ms: int) -> list[tuple]:
        path = self._path(pair, "1h-funding_rate")
        if not os.path.exists(path):
            return []
        ms, cols = self._load(path, ("funding_rate",), self._spans(start_ms, end_ms))
        return [(int(m), float(r), None) for m, r in zip(ms, cols["funding_rate"])]
