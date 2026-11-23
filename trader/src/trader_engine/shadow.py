"""WP-3 (defter-ek-alanlar 5): golge karar satirlari icin SAF hesap. Saat, ag, durum, defter yok; `datetime.now()` yok.
Motor bu modulun urettigi adaylari yalniz `shadow_decisions` tablosuna yazar; hicbir kapi/boyut/emir yoluna girmez.

Dondurulmus dosyalarin kamusal islevleri cagrilir (`signals.evaluate_t1`, `signals.compute_signals`,
`regime.classify_series`, `regime.align_to_base`, `indicators.ema`); icerikleri degismez."""
from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from trader_core import indicators as I
from trader_core import regime as R
from trader_core import signals as S

from .bars import tf_delta
from . import holdout as _H
from .holdout import HOLDOUT

_OHLC = ["open", "high", "low", "close"]
N15, N4H = 5000, 1500                     # tf_15m penceresi (WindowedSignalSource ile ayni)
WARM15, WARM4H = 4800, 300
CONTIG15, CONTIG4H = 20, 150
BLOCK_OF_KEY = {"regime": ("regime_volatile", "regime_unclear"), "r1_disabled": ("r1_disabled",),
                "same_bar_reentry": ("same_bar_reentry",), "tf_15m": ("tf_15m",)}


@dataclass(frozen=True)
class ShadowCand:
    """Motorun `ledger.ShadowEvent`'e cevirecegi saf aday (strategy/param_version/pos_open/gate_code motorda eklenir)."""
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
    features: Mapping[str, float | int]
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    reasons: str


def in_holdout(ts: datetime) -> bool:
    """Kilitli donem `[2026-05-01, 2026-11-01)`: bu bar_close_ts'li satir yazilmaz (spec 0.4)."""
    return _H.in_holdout(ts)


def _fin(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _opt(x) -> float | None:
    return float(x) if _fin(x) else None


# ------------------------------------------------------------------ reasons ayrisimi
def parse_reasons(reasons: str) -> tuple[frozenset[str], str]:
    """Bastaki `v1b:r1_disabled|`, `v1b:same_bar_reentry|` ve `ml:p=...|` on eklerini atar.
    -> (bulunan v1b bayraklari, kalan metin)."""
    flags: set[str] = set()
    s = reasons if isinstance(reasons, str) else ""
    while True:
        if s.startswith("v1b:r1_disabled|"):
            flags.add("r1_disabled")
            s = s[len("v1b:r1_disabled|"):]
        elif s.startswith("v1b:same_bar_reentry|"):
            flags.add("same_bar_reentry")
            s = s[len("v1b:same_bar_reentry|"):]
        elif s.startswith("ml:") and "|" in s:
            s = s.split("|", 1)[1]
        else:
            break
    return frozenset(flags), s


# ------------------------------------------------------------------ ozellikler (gates._features ile ayni anahtar kurali)
def _features(setup: str, get) -> dict:
    keys = ["atr_tf", "stop_dist_atr", "atr_4h"]
    keys += (["pullback_ema", "ema_value", "body_ratio"] if setup == "T1" else ["wick_ratio", "rr", "edge_dist_atr"])
    keys += ["rh_touches", "rl_touches"]
    out: dict = {}
    for k in keys:
        v = get(k)
        if _fin(v):
            out[k] = int(v) if k in ("pullback_ema", "rh_touches", "rl_touches") else float(v)
    return out


def _valid_levels(side, pe, ps) -> bool:
    if not (_fin(pe) and _fin(ps)) or float(pe) <= 0 or float(ps) <= 0:
        return False
    return float(ps) < float(pe) if side == "long" else float(ps) > float(pe)


# ------------------------------------------------------------------ 1-3: karar mumu satirindan
def row_candidates(row, blocks: Iterable[str], *, trigger_tf: str) -> list[ShadowCand]:
    """`r1_disabled` ve `same_bar_reentry` (spec 5.3-1,2). `row`: `SignalRow` benzeri (`fr.last`).
    `blocks`: etkin `block` adlari (`r1_disabled`, `same_bar_reentry`)."""
    blocks = set(blocks)
    out: list[ShadowCand] = []
    if row is None or row.signal or row.skip_reason is not None or row.side not in ("long", "short"):
        return out
    flags, rest = parse_reasons(row.reasons)
    block = None
    if "r1_disabled" in blocks and "r1_disabled" in flags and row.setup == "R1" and rest.endswith(",stop_ok,rr_ok"):
        block = "r1_disabled"
    elif ("same_bar_reentry" in blocks and "same_bar_reentry" in flags and row.setup == "T1"
          and rest.endswith(",stop_ok")):
        block = "same_bar_reentry"
    if block is None or row.setup not in ("T1", "R1"):
        return out
    if not _valid_levels(row.side, row.planned_entry, row.planned_stop):
        return out
    is_range = row.regime == "range"
    feats = _features(row.setup, lambda k: getattr(row, k, None))
    out.append(ShadowCand(
        block=block, bar_close_ts=row.bar_close_ts, trigger_tf=trigger_tf, pair=row.pair, side=row.side,
        setup=row.setup, regime=row.regime, atr_ratio=_opt(row.atr_ratio),
        rh=_opt(row.rh) if is_range else None, rl=_opt(row.rl) if is_range else None, features=feats,
        planned_entry=float(row.planned_entry), planned_stop=float(row.planned_stop),
        planned_target=_opt(row.planned_target), reasons=row.reasons))
    return out


def _valid_ohlc_rows(tail: pd.DataFrame) -> bool:
    for o, h, l, c in zip(tail["open"], tail["high"], tail["low"], tail["close"]):
        if not all(_fin(x) for x in (o, h, l, c)):
            return False
        o, h, l, c = float(o), float(h), float(l), float(c)
        if not (o > 0 and h > 0 and l > 0 and c > 0 and h >= l and c <= h and c >= l and o <= h and o >= l):
            return False
    return True


def regime_candidate(table: pd.DataFrame, params):
    """Koşul yasagi olmasaydi EMA geri cekilme tetigi ne yapardi (spec 5.3-3). Iki yone de `signals.evaluate_t1`
    cagrilir; `skip_reason is None` donen tek aday -> `signals.SetupCandidate`, yoksa None.
    Son STOP_LOOKBACK mumda ya da EMA penceresinde gecersiz OHLC varsa aday yok."""
    if not isinstance(params, S.SignalParams) or table is None or len(table) < S.STOP_LOOKBACK:
        return None
    n_ema = int(params.pullback_ema)
    tail = table.iloc[-max(S.STOP_LOOKBACK, n_ema):]
    if len(tail) < n_ema or not _valid_ohlc_rows(tail):
        return None
    ema_last = float(I.ema(table["close"], params.pullback_ema).iloc[-1])
    a = table["atr_tf"].iloc[-1]
    last = table.iloc[-1]
    recent5 = table.iloc[-S.STOP_LOOKBACK:]
    found = []
    for side in ("long", "short"):
        recent = recent5["low"].tolist() if side == "long" else recent5["high"].tolist()
        cand = S.evaluate_t1(side, last["open"], last["high"], last["low"], last["close"], ema_last, recent, a,
                             params)
        if cand is not None and cand.skip_reason is None:
            found.append(cand)
    return found[0] if len(found) == 1 else None


def regime_cands(row, table: pd.DataFrame | None, params, blocks: Iterable[str], *,
                 trigger_tf: str) -> list[ShadowCand]:
    blocks = set(blocks)
    out: list[ShadowCand] = []
    if row is None or table is None or row.reasons != "regime_blocked":
        return out
    block = {"volatile": "regime_volatile", "unclear": "regime_unclear"}.get(row.regime)
    if block is None or block not in blocks:
        return out
    cand = regime_candidate(table, params)
    if cand is None:
        return out
    atr_4h = table["atr_4h"].iloc[-1] if "atr_4h" in table.columns else row.atr_4h
    feats = dict(cand.features)
    if _fin(atr_4h):
        feats["atr_4h"] = float(atr_4h)
    else:
        return out
    feats["rh_touches"] = int(row.rh_touches or 0)
    feats["rl_touches"] = int(row.rl_touches or 0)
    if not _valid_levels(cand.side, cand.entry, cand.stop):
        return out
    out.append(ShadowCand(
        block=block, bar_close_ts=row.bar_close_ts, trigger_tf=trigger_tf, pair=row.pair, side=cand.side,
        setup="T1", regime=row.regime, atr_ratio=_opt(row.atr_ratio), rh=None, rl=None,
        features={k: (int(v) if k in ("pullback_ema", "rh_touches", "rl_touches") else float(v))
                  for k, v in feats.items() if _fin(v)},
        planned_entry=float(cand.entry), planned_stop=float(cand.stop), planned_target=None,
        reasons=row.reasons))
    return out


# ------------------------------------------------------------------ 4: 15 dk tetik
def tf15_window_start(D: datetime) -> datetime:
    return D - tf_delta("15m") * N15


def tf15_candidates(view, pair: str, D: datetime, params, *, counters: MutableMapping | None = None
                    ) -> list[ShadowCand]:
    """15 dk tetikle son saatte (D - 1 sa, D] kapanan `signal=True` mumlar (spec 5.3-4).
    Pencerenin ilk mumu kilitli donemin bitisinden (2026-11-01T00:00Z) onceyse hesap YAPILMAZ ve piyasa verisi
    OKUNMAZ (`tf15_holdout_wait`)."""
    if not _H.KILIT_ACIK and tf15_window_start(D) < HOLDOUT[1]:
        if counters is not None:
            counters["tf15_holdout_wait"] = counters.get("tf15_holdout_wait", 0) + 1
        return []
    d15, d4 = tf_delta("15m"), tf_delta("4h")
    b15 = view.bars(pair, "15m", D, N15)
    b4 = view.bars(pair, "4h", D, N4H)
    if len(b15) < WARM15 or len(b4) < WARM4H:
        return []
    if b15.index[-1].to_pydatetime() != D - d15:
        return []
    if not _H.KILIT_ACIK and b15.index[0].to_pydatetime() < HOLDOUT[1]:
        if counters is not None:
            counters["tf15_holdout_wait"] = counters.get("tf15_holdout_wait", 0) + 1
        return []
    if not _contiguous_tail(b15.index, d15, CONTIG15) or not _contiguous_tail(b4.index, d4, CONTIG4H):
        return []
    p15 = dataclasses.replace(params, trigger_tf="15m")
    reg = R.classify_series(b4[_OHLC], p15.regime_params())
    aligned = R.align_to_base(reg, b15.index, 4)
    sig = S.compute_signals(b15[_OHLC], aligned, p15)
    cutoff = D - tf_delta("1h")
    out: list[ShadowCand] = []
    for ts, r in sig.iloc[-8:].iterrows():           # (D - 1 sa, D] en cok 4 mum; 8 satir bol marj
        open_ts = ts.to_pydatetime()
        close_ts = open_ts + d15
        if not (cutoff < close_ts <= D) or not bool(r["signal"]):
            continue
        side, setup = r["side"], r["setup"]
        if side not in ("long", "short") or setup not in ("T1", "R1"):
            continue
        if not _valid_levels(side, r["planned_entry"], r["planned_stop"]):
            continue
        is_range = r["regime"] == "range"
        out.append(ShadowCand(
            block="tf_15m", bar_close_ts=close_ts, trigger_tf="15m", pair=pair, side=side, setup=setup,
            regime=str(r["regime"]), atr_ratio=_opt(r["atr_ratio"]),
            rh=_opt(r["rh"]) if is_range else None, rl=_opt(r["rl"]) if is_range else None,
            features=_features(setup, lambda k, r=r: r[k] if k in r.index else None),
            planned_entry=float(r["planned_entry"]), planned_stop=float(r["planned_stop"]),
            planned_target=_opt(r["planned_target"]), reasons=str(r["reasons"])))
    return out


def _contiguous_tail(idx: pd.DatetimeIndex, step: timedelta, need: int) -> bool:
    if len(idx) < need:
        return False
    tail = idx[-need:]
    return bool((tail[1:] - tail[:-1] == pd.Timedelta(step)).all())
