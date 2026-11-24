"""DD-12 WP-12b bagimsiz sartname testleri: kurulumlar F1, S1, H2 (Ek-K: docs/motor/dd12-ek-k-kurulumlar.md,
K-3, K-4, K-5, K-6, K-7, K-8) ve K-7 sozlesmesi (EXIT_MODE, FEATURES, PRIORITY, arm kimligi).

Gerceklemeye BAKILMADI: yalniz Ek-K ve WP-12a spec testlerinin fikstur kalibi kullanildi. Sentetik mumlar elle kurulur;
ag yok. Kurulum modulleri yoksa ilgili testler importorskip ile atlanir.

Ek-K yorumlari (SPEC-AMBIGUOUS, testler sartnamenin acik dediklerini sinar):
  * Fikstur mumlari sartnamedeki esikleri (0,1/0,2/0,5 ATR, rr, SDA) asacak sekilde elle kuruldu; her pozitif testin
    basinda ayni kosullar I.atr / I.ema ile yeniden hesaplanip sanity assert olarak sinanir.
  * FEATURES eslemesi K-7 madde 2 tablosudur. H2 `pb_bars` icin tablo acikca `wick_ratio` der.
"""
from __future__ import annotations

import dataclasses
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from trader_core import indicators as I
from trader_core import ledger as L
from trader_core import signals as S
from trader_engine.position_manager import ExitContext, evaluate_exit
from trader_engine.strategies import arms as AR
from trader_engine.strategies.arms import ArmError, ArmInput, make_arm_id, parse_arm_id
from trader_engine.strategies.base import validate_row, validate_table
from trader_engine.types import Position

UTC = timezone.utc
ALL_TFS = ("15m", "1h", "4h", "1d")
FREQ = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
TD = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}
ARM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}@(15m|1h|4h|1d)$")
SETUPS = ("F1", "S1", "H2")
N_BARS = 150
MIRROR_C = 200.0
REGIME_OK = {"F1": "trend_up", "S1": "range", "H2": "trend_up"}      # varsayilan izinli rejim (long)
MIRROR_REG = {"trend_up": "trend_down", "range": "range"}
LOOKBACK = {"F1": (60, 40), "S1": (45, 45), "H2": (60, 45)}          # (15dk/1s/4s, 1g)


def _f1():
    return pytest.importorskip("trader_engine.strategies.arms.f1")


def _s1():
    return pytest.importorskip("trader_engine.strategies.arms.s1")


def _h2():
    return pytest.importorskip("trader_engine.strategies.arms.h2")


def _mod(setup):
    return {"F1": _f1, "S1": _s1, "H2": _h2}[setup]()


def _n_lvl(tf):          # K-3 N_LVL (F1): 40 / 20 (1g)
    return 20 if tf == "1d" else 40


def _lookback(setup, tf):
    a, b = LOOKBACK[setup]
    return b if tf == "1d" else a


# ============================================================================================= sentetik mum kurucular
def _frame(rows, tf):
    arr = np.array(rows, dtype=float)                     # satir: (o, h, l, c)
    idx = pd.date_range("2026-02-02 00:00", periods=len(rows), freq=FREQ[tf], tz="UTC")
    return pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3],
                         "volume": 1.0}, index=idx)


def _mirror(df):
    out = df.copy()
    out["open"] = MIRROR_C - df["open"]
    out["high"] = MIRROR_C - df["low"]
    out["low"] = MIRROR_C - df["high"]
    out["close"] = MIRROR_C - df["close"]
    return out


def _uptrend(n, drift=0.3, p0=100.0):
    """Sakin yukselis: o = onceki kapanis, c = o + drift, h/l = max/min +- 0,25. ATR ~ 0,8."""
    rows, prev = [], p0
    for _ in range(n):
        o = prev
        c = o + drift
        rows.append((o, max(o, c) + 0.25, min(o, c) - 0.25, c))
        prev = c
    return rows


# ---- F1 (sahte kirilim / SFP): taban duz 100, seviye dibi t-12'de (A = 98), t-1 süpürme, t geri alma
F1_BASE = (100.0, 101.0, 99.0, 100.0)
F1_DIP = (100.0, 101.0, 98.0, 99.0)
F1_SWEEP = (98.2, 98.4, 97.5, 97.9)     # t-1: low 97,5 < A - 0,1 ATR; kapanis < A (t-1'de sinyal yok)
F1_RECL = (97.9, 98.4, 97.8, 98.3)      # t: kapanis > A, > acilis; rej = (c - 97,5)/(98,4 - 97,5) ~ 0,89


def _f1_frame(tf, *, n=N_BARS, dip_off=-12, ov=None, extra=0):
    T = n - 1
    rows = [F1_BASE] * (n + extra)
    if dip_off is not None:
        rows[T + dip_off] = F1_DIP
    ov_all = {-1: F1_SWEEP, 0: F1_RECL}
    ov_all.update(ov or {})
    for off, row in ov_all.items():
        rows[T + off] = row
    return _frame(rows, tf), T


F1_NEAR = {
    "deep_sweep": dict(ov={-1: (98.2, 98.4, 94.0, 97.9)}),          # derinlik > 1,5 ATR
    "weak_rejection": dict(ov={0: (97.9, 98.4, 97.8, 98.02)}),      # rej ~ 0,58 < 0,6
    "shallow_pierce": dict(ov={-1: (98.2, 98.4, 97.9, 97.9), 0: (97.9, 98.4, 97.9, 98.3)}),   # delme 0,05 ATR
    "no_reclaim": dict(ov={0: (97.9, 98.4, 97.8, 97.95)}),          # c <= A: geri alma yok
    "edge_window": dict(),                                           # k* = t-N+1 (pencere kenari)
}
F1_RR_LOW = dict(ov={0: (97.9, 100.0, 97.8, 99.9)})                  # hedef cok yakin -> rr_below_min


def _f1_near_kwargs(name, tf):
    if name == "edge_window":
        return dict(dip_off=-(_n_lvl(tf) - 1))
    return dict(F1_NEAR[name])


# ---- S1 (sikisma kirilimi): taban 100 (ATR 1), kutu t-8..t-1 = [99, 101] (genislik 2 = 2*A0), t kirilim
S1_PRE = (100.0, 100.5, 99.5, 100.0)
S1_BOX = (100.0, 101.0, 99.0, 100.0)
S1_BRK = (100.8, 101.9, 100.7, 101.6)


def _s1_frame(tf, *, n=N_BARS, box=S1_BOX, box_rows=None, brk=S1_BRK, extra=0):
    T = n - 1
    rows = [S1_PRE] * (n + extra)
    for off in range(-8, 0):
        rows[T + off] = box
    for off, row in (box_rows or {}).items():
        rows[T + off] = row
    rows[T] = brk
    return _frame(rows, tf), T


S1_NEAR = {
    "wide_box": dict(box=(100.0, 102.6, 98.9, 100.0), brk=(102.5, 103.6, 102.4, 103.5)),       # genislik 3,7 > 3 A0
    "nr_zero": dict(box_rows={-3: (100.0, 101.3, 99.0, 100.3), -2: (100.0, 101.6, 99.0, 100.0),
                              -1: (100.0, 101.9, 99.0, 100.0)},
                    brk=(101.0, 102.6, 100.9, 102.4)),                                          # nr_count = 0
    "close_inside_box": dict(brk=(100.2, 101.9, 100.0, 100.8)),                                 # fitil BH'yi gecer, kapanis icinde
    "weak_breakout": dict(brk=(100.6, 101.1, 100.5, 101.05)),                                   # c < BH + 0,1 ATR
    "small_body": dict(brk=(101.3, 102.0, 101.2, 101.6)),                                       # govde 0,375 < 0,5
}
S1_STOP_WIDTH_BRK = (102.0, 106.1, 102.0, 106.0)                                                  # sda ~ 3,2 > 3


# ---- H2 (iki bacakli geri cekilme): tepe s = t-7; t-6..t-4 dusen tepeler, t-3 H1, t-2..t-1 dusen, t H2
# Degerler tepe yuksekligi P'ye gore ofset (P = h[s]).
H2_TPL = {
    -6: (-0.3, -0.2, -0.5, -0.4),
    -5: (-0.4, -0.4, -0.9, -0.8),
    -4: (-0.8, -0.6, -1.3, -1.1),
    -3: (-1.1, -0.4, -1.1, -0.7),   # H1 (yukari: h = -0,4 > -0,6)
    -2: (-0.7, -0.6, -1.2, -1.1),
    -1: (-1.1, -0.8, -1.4, -1.2),
    0: (-1.2, -0.3, -1.3, -0.5),    # H2: h = -0,3 > h[t-1] = -0,8; kapanis -0,5 > h[t-1]
}
H2_SHALLOW_TPL = {k: (o, h, max(lo, -0.6), c) for k, (o, h, lo, c) in H2_TPL.items()}   # derinlik < 1 ATR
H2_NEAR = {
    "no_reclaim": dict(tpl={**H2_TPL, 0: (-1.2, -0.3, -1.3, -0.9)}),   # kapanis h[t-1] altinda (fitille gecis)
    "shallow_pullback": dict(tpl=H2_SHALLOW_TPL),                       # pb ~ 0,75 ATR
}


def _h2_frame(tf, *, n=N_BARS, tpl=None, extra=0):
    T = n - 1
    base = _uptrend(n + extra)
    P = base[T - 7][1]                                  # tepe h[s]
    rows = list(base)
    for off, (o, h, lo, c) in (tpl or H2_TPL).items():
        rows[T + off] = (P + o, P + h, P + lo, P + c)
    return _frame(rows, tf), T


def _positive(setup, tf, extra=0):
    if setup == "F1":
        trig, T = _f1_frame(tf, extra=extra)
    elif setup == "S1":
        trig, T = _s1_frame(tf, extra=extra)
    else:
        trig, T = _h2_frame(tf, extra=extra)
    return trig, T, REGIME_OK[setup]


def _rw(tf, n=300, seed=23):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 0.6, n))
    o = np.concatenate([[100.0], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0.05, 0.6, n)
    lo = np.minimum(o, c) - rng.uniform(0.05, 0.6, n)
    return _frame(list(zip(o, h, lo, c)), tf)


# ============================================================================================= calistirma
def _core(trig, regime):
    """`inp.core()` benzeri ortak tablo: aday sutunlari bos; regime ve baglam sutunlari (atr_tf = indicators.atr)."""
    idx = trig.index
    n = len(idx)
    reg = [regime] * n if isinstance(regime, str) else list(regime)
    df = pd.DataFrame(index=idx)
    df["setup"] = pd.Series([None] * n, index=idx, dtype=object)
    df["side"] = pd.Series([None] * n, index=idx, dtype=object)
    df["signal"] = np.zeros(n, dtype=bool)
    df["skip_reason"] = pd.Series([None] * n, index=idx, dtype=object)
    for c in ("planned_entry", "planned_stop", "planned_target", "rr", "stop_dist_atr"):
        df[c] = np.nan
    df["atr_tf"] = I.atr(trig, 14).to_numpy(dtype=float)
    df["atr_4h"] = 1.0
    df["atr_ratio"] = 1.0
    df["regime"] = pd.Series(reg, index=idx, dtype=object)
    df["rh"] = np.nan
    df["rl"] = np.nan
    df["rh_touches"] = np.zeros(n, dtype="int64")
    df["rl_touches"] = np.zeros(n, dtype="int64")
    for c in ("ema_value", "body_ratio", "wick_ratio", "edge_dist_atr"):
        df[c] = np.nan
    df["pullback_ema"] = np.zeros(n, dtype="int64")
    df["reasons"] = pd.Series([""] * n, index=idx, dtype=object)
    return df[list(S.SIGNAL_COLUMNS)]


def _run(mod, trig, regime, tf):
    core = _core(trig, regime)
    inp = ArmInput(pair="SYN/USDT", tf=tf, D=trig.index[-1].to_pydatetime() + TD[tf], trig=trig, h4=trig,
                   params=S.DEFAULT_SIGNAL_PARAMS, core_fn=lambda: core.copy())
    return mod.compute(inp)


def _checked(mod, trig, regime, tf, setup):
    out = _run(mod, trig, regime, tf)
    assert set(out.columns) == set(S.SIGNAL_COLUMNS)
    assert out.index.equals(trig.index)
    validate_table(out, SimpleNamespace(setups=(setup,)), trig.index)     # K-ORT-5: sema denetimi
    return out


def _row_ok(out, i, setup):
    row = out.iloc[i]
    validate_row(row, SimpleNamespace(setups=(setup,)))
    return row


def _arr(trig):
    return {k: trig[k].to_numpy() for k in ("open", "high", "low", "close")}


F1_FEATURES = {"level": "ema_value", "sweep_depth_atr": "edge_dist_atr", "rej_ratio": "wick_ratio",
               "body_ratio": "body_ratio", "level_age": "pullback_ema", "rr": "rr"}
S1_FEATURES = {"box_w_atr": "edge_dist_atr", "box_edge": "ema_value", "pole_atr": "wick_ratio",
               "body_ratio": "body_ratio", "nr_count": "pullback_ema"}
H2_FEATURES = {"ema_value": "ema_value", "pb_depth_atr": "edge_dist_atr", "pb_bars": "wick_ratio",
               "body_ratio": "body_ratio", "leg_gap": "pullback_ema"}
FEATURES_WANT = {"F1": F1_FEATURES, "S1": S1_FEATURES, "H2": H2_FEATURES}


# ============================================================================================= K-7: sozlesme
@pytest.mark.parametrize("setup", SETUPS)
def test_contract_module_attributes(setup):
    mod = _mod(setup)
    assert mod.SETUP == setup
    assert tuple(mod.TIMEFRAMES) == ALL_TFS
    assert mod.CORE is False                              # kendi hesabi; ortak tablo satiri secmez
    assert callable(mod.compute)
    assert isinstance(mod.PRIORITY, int) and not isinstance(mod.PRIORITY, bool)


def test_exit_mode_and_priority_per_spec():
    """K-7 madde 1 + madde 3: F1 hedefli (target), S1/H2 iz suren (trail); PRIORITY H2 50, S1 60, F1 70."""
    assert _f1().EXIT_MODE == "target"
    assert _s1().EXIT_MODE == "trail"
    assert _h2().EXIT_MODE == "trail"
    assert _f1().PRIORITY == 70
    assert _s1().PRIORITY == 60
    assert _h2().PRIORITY == 50


def test_priority_order_within_timeframe_full():
    """K-6 / K-7: ayni zaman diliminde T1 > R1 > TF1 > B1 > H2 > S1 > F1 (kucuk sayi once)."""
    prios = {"T1": AR.find_arm("T1").PRIORITY, "R1": AR.find_arm("R1").PRIORITY,
             "TF1": pytest.importorskip("trader_engine.strategies.arms.tf1").PRIORITY,
             "B1": pytest.importorskip("trader_engine.strategies.arms.b1").PRIORITY,
             "H2": _h2().PRIORITY, "S1": _s1().PRIORITY, "F1": _f1().PRIORITY}
    assert {k: prios[k] for k in ("H2", "S1", "F1")} == {"H2": 50, "S1": 60, "F1": 70}
    assert sorted(prios, key=lambda s: prios[s]) == ["T1", "R1", "TF1", "B1", "H2", "S1", "F1"]


@pytest.mark.parametrize("setup", SETUPS)
def test_features_mapping_and_carriers_in_signal_columns(setup):
    """K-7 madde 2: FEATURES defter anahtari -> SIGNAL_COLUMNS tasiyicisi; rh/rl/touch tasinmaz."""
    mod = _mod(setup)
    assert dict(mod.FEATURES) == FEATURES_WANT[setup]
    assert set(mod.FEATURES.values()) <= set(S.SIGNAL_COLUMNS)
    assert not ({"rh", "rl", "rh_touches", "rl_touches"} & set(mod.FEATURES.values()))


@pytest.mark.parametrize("setup", SETUPS)
def test_features_accepted_by_ledger(setup):
    """K-7 madde 2 + K-ORT-7: FEATURES tasiyicilariyla kurulan defter ozellik sozlugu ledger tarafindan kabul edilir."""
    mod = _mod(setup)
    trig, T, reg = _positive(setup, "1h")
    out = _checked(mod, trig, reg, "1h", setup)
    row = _row_ok(out, T, setup)
    assert bool(row.signal)
    feats = {"atr_tf": float(row.atr_tf), "stop_dist_atr": float(row.stop_dist_atr),
             "atr_4h": float(row.atr_4h), "rh_touches": 0, "rl_touches": 0}
    for key, col in mod.FEATURES.items():
        v = row[col]
        assert np.isfinite(float(v)), (key, col, v)       # K-ORT-7: sonlu sayi
        feats[key] = int(v) if col == "pullback_ema" else float(v)
    owners = [vars(getattr(L, n))["_prep_features"] for n in dir(L)
              if isinstance(getattr(L, n), type) and "_prep_features" in vars(getattr(L, n))]
    assert owners, "ledger _prep_features bulunamadi"
    prep = owners[0]
    fn = prep.__func__ if isinstance(prep, staticmethod) else prep
    fn(feats, setup)                                       # LedgerValidationError firlatirsa test kirar


def test_arm_discovery_and_arm_id_format():
    _f1()
    _s1()
    _h2()
    names = set(AR.list_arms())
    assert {"F1", "S1", "H2"} <= names
    for setup in SETUPS:
        for tf in ALL_TFS:
            arm = make_arm_id(setup, tf)
            assert ARM_RE.match(arm), arm
            assert parse_arm_id(arm) == (setup, tf)
    with pytest.raises(ArmError):
        parse_arm_id("F1@2h")
    with pytest.raises(ArmError):
        AR.find_arm("ZZ9")


# ============================================================================================= K-7: pozisyon cikisi
def _position(**kw):
    vals = {}
    for f in dataclasses.fields(Position):
        if f.name in kw:
            vals[f.name] = kw[f.name]
            continue
        if f.default is not dataclasses.MISSING or f.default_factory is not dataclasses.MISSING:
            continue
        ann = str(f.type)
        if "None" in ann or "Optional" in ann or "datetime" in ann:
            vals[f.name] = None
        elif "Literal" in ann or "str" in ann:
            vals[f.name] = ""
        elif "float" in ann:
            vals[f.name] = 0.0
        elif "int" in ann:
            vals[f.name] = 0
        else:
            vals[f.name] = None
    return Position(**vals)


T0 = datetime(2026, 2, 2, 12, 0, tzinfo=UTC)


def _exit(setup, *, target=None, highs, lows, atrs, regime_last, last_close, entry=100.0, stop=98.0):
    pos = _position(trade_id=1, bot="t", pair="BTC/USDT", side="long", setup=setup, status="open", decision_id=1,
                    signal_bar_close_ts=T0, entry_ts=T0, entry_bar_open=T0, entry_price=entry, qty=1.0,
                    leverage=1, initial_stop=stop, current_stop=stop, planned_target=target, trail_atr=3.0,
                    trigger_tf="1h", param_version_id=1)
    ctx = ExitContext(bar_close_ts=T0, highs=np.asarray(highs, float), lows=np.asarray(lows, float),
                      atrs=np.asarray(atrs, float), regime_last=regime_last, last_close=last_close,
                      n_closed=len(highs))
    return evaluate_exit(pos, ctx)


def _floats(d):
    return [v for v in dataclasses.astuple(d) if isinstance(v, float)]


@pytest.mark.parametrize("setup", ["S1", "H2"])
def test_trail_exit_for_trail_setups(setup):
    """K-7 madde 1: iz suren kurulumlar (S1, H2) 1R sonrasi en yuksek - 3 ATR stop kurar (hedef yok)."""
    highs = np.linspace(100.5, 110.0, 20)
    d = _exit(setup, highs=highs, lows=highs - 1.0, atrs=np.ones(20), regime_last="trend_up", last_close=109.5)
    assert d.kind == "stop_update", d
    assert any(abs(v - 107.0) < 1.0 for v in _floats(d)), d


def test_target_exit_for_f1():
    """K-7 madde 1: F1 hedefli (target); hedefe degen bar -> target cikisi."""
    highs = np.linspace(100.5, 104.5, 10)
    d = _exit("F1", target=104.0, highs=highs, lows=highs - 1.0, atrs=np.ones(10), regime_last="range",
              last_close=104.2)
    assert d.kind == "exit" and d.reason == "target", d


def test_f1_no_trailing_stop():
    """K-7: F1 pozisyonunda iz suren stop kurulmaz (en yuksek-3 ATR 100 > 98), regime_flip uygulanmaz."""
    highs = np.linspace(100.5, 103.0, 10)
    d = _exit("F1", target=104.0, highs=highs, lows=highs - 1.0, atrs=np.ones(10), regime_last="trend_down",
              last_close=102.8)
    assert d.kind == "none", d


# ============================================================================================= F1: giris kurali
@pytest.mark.parametrize("tf", ALL_TFS)
def test_f1_long_fires_on_sweep_and_reclaim(tf):
    mod = _f1()
    trig, T = _f1_frame(tf)
    out = _checked(mod, trig, "trend_up", tf, "F1")
    row = _row_ok(out, T, "F1")
    assert bool(row.signal) and row.setup == "F1" and row.side == "long"
    assert row.skip_reason is None or pd.isna(row.skip_reason)
    nl = _n_lvl(tf)
    a = _arr(trig)
    h, lo, o, c = a["high"], a["low"], a["open"], a["close"]
    atr = I.atr(trig, 14).iloc[T]
    win = lo[T - nl:T - 4]                                  # [t-N .. t-5]
    A = win.min()
    kstar = T - nl + int(np.where(win == A)[0][-1])         # asgarinin son indeksi
    lsw = min(lo[T - 1], lo[T])                             # s: {t-1, t} icinde en dusuk low (esitlikte t)
    hsw = max(h[T - 1], h[T])
    rej = (c[T] - lsw) / (hsw - lsw)
    stop = lsw - 0.2 * atr
    target = h[T - 20:T].max() - 0.2 * atr                  # son 20 bar tepesi - 0,2 ATR (t dahil degil)
    rr = (target - c[T]) / (c[T] - stop)
    # sartname kosullari gercekten saglanir (sanity)
    assert kstar >= T - nl + 2 and kstar <= T - 5
    assert c[T - 2] >= A and lsw < A - 0.1 * atr and c[T] > A and c[T] > o[T]
    assert rej >= 0.6 and (A - lsw) / atr <= 1.5 and rr >= 1.5
    assert (c[T] - stop) / atr <= 2.0
    # cikti
    assert row.planned_entry == pytest.approx(c[T], rel=1e-9)
    assert row.planned_stop == pytest.approx(stop, rel=1e-6)
    assert row.planned_target == pytest.approx(target, rel=1e-6)
    assert row.rr == pytest.approx(rr, rel=1e-6)
    assert row.stop_dist_atr == pytest.approx((c[T] - stop) / atr, rel=1e-6)
    assert row.atr_tf == pytest.approx(atr, rel=1e-6)
    assert row.regime == "trend_up"
    assert float(row.planned_stop) < float(row.planned_entry) < float(row.planned_target)   # K-ORT-5 yonu
    # sinyal oncesi barlarda (t-1 dahil) aday yok (K-F1 madde 5, geri alma sarti)
    assert not bool(out["signal"].iloc[:T].any())


@pytest.mark.parametrize("tf", ALL_TFS)
def test_f1_short_is_exact_mirror_of_long(tf):
    mod = _f1()
    trig, T, reg = _positive("F1", tf)
    lo_out = _checked(mod, trig, reg, tf, "F1")
    sh_out = _checked(mod, _mirror(trig), MIRROR_REG[reg], tf, "F1")
    a = _row_ok(lo_out, T, "F1")
    b = _row_ok(sh_out, T, "F1")
    assert bool(a.signal) and bool(b.signal) and b.side == "short"
    assert b.planned_entry == pytest.approx(MIRROR_C - a.planned_entry, rel=1e-9)
    assert b.planned_stop == pytest.approx(MIRROR_C - a.planned_stop, rel=1e-6)
    assert b.planned_target == pytest.approx(MIRROR_C - a.planned_target, rel=1e-6)
    assert b.rr == pytest.approx(a.rr, rel=1e-6)


@pytest.mark.parametrize("name", sorted(F1_NEAR))
@pytest.mark.parametrize("tf", ALL_TFS)
def test_f1_near_miss_does_not_fire(tf, name):
    mod = _f1()
    trig, T = _f1_frame(tf, **_f1_near_kwargs(name, tf))
    out = _checked(mod, trig, "trend_up", tf, "F1")
    assert not bool(_row_ok(out, T, "F1").signal), name


@pytest.mark.parametrize("tf", ALL_TFS)
def test_f1_rr_below_min_skip_reason(tf):
    """K-F1-5: hedef cok yakin (rr < 1,5) -> satir yazilir, signal=False, skip_reason='rr_below_min'."""
    mod = _f1()
    trig, T = _f1_frame(tf, **F1_RR_LOW)
    out = _checked(mod, trig, "trend_up", tf, "F1")
    row = _row_ok(out, T, "F1")
    a = _arr(trig)
    atr = I.atr(trig, 14).iloc[T]
    stop = min(a["low"][T - 1], a["low"][T]) - 0.2 * atr
    target = a["high"][T - 20:T].max() - 0.2 * atr
    assert (target - a["close"][T]) / (a["close"][T] - stop) < 1.5          # sanity
    assert not bool(row.signal) and row.skip_reason == "rr_below_min"


@pytest.mark.parametrize("regime", ["trend_down", "volatile"])
def test_f1_blocked_regimes(regime):
    """K-6 / K-ORT-6: F1 trend karsiti ve volatile'da aday yok (ayni sentetik kurulum)."""
    tf = "1h"
    trig, T = _f1_frame(tf)
    out = _checked(_f1(), trig, regime, tf, "F1")
    assert not bool(out["signal"].any())


@pytest.mark.parametrize("regime", ["trend_up", "range", "unclear"])
def test_f1_allowed_regimes(regime):
    """K-6: F1 trend (ayni yon), range ve unclear'da calisir."""
    tf = "1h"
    trig, T = _f1_frame(tf)
    out = _checked(_f1(), trig, regime, tf, "F1")
    assert bool(_row_ok(out, T, "F1").signal)


# ============================================================================================= S1: giris kurali
@pytest.mark.parametrize("tf", ALL_TFS)
def test_s1_long_fires_on_box_breakout(tf):
    mod = _s1()
    trig, T = _s1_frame(tf)
    out = _checked(mod, trig, "range", tf, "S1")
    row = _row_ok(out, T, "S1")
    assert bool(row.signal) and row.setup == "S1" and row.side == "long"
    assert row.skip_reason is None or pd.isna(row.skip_reason)
    a = _arr(trig)
    h, lo, o, c = a["high"], a["low"], a["open"], a["close"]
    atr = I.atr(trig, 14).iloc[T]
    a0 = I.atr(trig, 14).iloc[T - 9]                        # A0 = ATR[t-9] (kutu oncesi)
    bh = h[T - 8:T].max()
    bl = lo[T - 8:T].min()
    rng = h - lo

    def inside(k):
        return h[k] <= h[k - 1] and lo[k] >= lo[k - 1]

    def nr7(k):
        return rng[k] == rng[k - 6:k + 1].min()

    nr = sum(1 for k in (T - 3, T - 2, T - 1) if inside(k) or nr7(k))
    body = (c[T] - o[T]) / (h[T] - lo[T])
    # sartname kosullari (sanity)
    assert bh - bl <= 3.0 * a0 and nr >= 1
    assert c[T] > bh + 0.1 * atr and c[T] > o[T] and body >= 0.5
    assert (c[T] - (bl - 0.2 * atr)) / atr <= 3.0
    # cikti
    assert row.planned_entry == pytest.approx(c[T], rel=1e-9)
    assert row.planned_stop == pytest.approx(bl - 0.2 * atr, rel=1e-6)
    assert pd.isna(row.planned_target)                      # hedef yok (trail)
    assert row.stop_dist_atr == pytest.approx((c[T] - (bl - 0.2 * atr)) / atr, rel=1e-6)
    assert row.atr_tf == pytest.approx(atr, rel=1e-6)
    assert row.regime == "range"
    # FEATURES tasiyicilari (K-4 features)
    assert row.ema_value == pytest.approx(bh, rel=1e-9)                       # box_edge = BH
    assert row.edge_dist_atr == pytest.approx((bh - bl) / a0, rel=1e-6)       # box_w_atr
    assert row.wick_ratio == pytest.approx(0.0, abs=1e-9)                     # pole_atr: duz oncesi -> 0
    assert row.body_ratio == pytest.approx(body, rel=1e-6)
    assert int(row.pullback_ema) == nr == 3                                   # nr_count
    assert not bool(out["signal"].iloc[:T].any())


@pytest.mark.parametrize("tf", ALL_TFS)
def test_s1_short_is_exact_mirror_of_long(tf):
    mod = _s1()
    trig, T, reg = _positive("S1", tf)
    lo_out = _checked(mod, trig, reg, tf, "S1")
    sh_out = _checked(mod, _mirror(trig), MIRROR_REG[reg], tf, "S1")
    a = _row_ok(lo_out, T, "S1")
    b = _row_ok(sh_out, T, "S1")
    assert bool(a.signal) and bool(b.signal) and b.side == "short"
    assert b.planned_entry == pytest.approx(MIRROR_C - a.planned_entry, rel=1e-9)
    assert b.planned_stop == pytest.approx(MIRROR_C - a.planned_stop, rel=1e-6)


@pytest.mark.parametrize("name", sorted(S1_NEAR))
@pytest.mark.parametrize("tf", ALL_TFS)
def test_s1_near_miss_does_not_fire(tf, name):
    mod = _s1()
    trig, T = _s1_frame(tf, **S1_NEAR[name])
    out = _checked(mod, trig, "range", tf, "S1")
    assert not bool(_row_ok(out, T, "S1").signal), name


@pytest.mark.parametrize("tf", ALL_TFS)
def test_s1_stop_width_skip_reason(tf):
    """K-S1 stop genisligi: sda > 3,0 -> satir yazilir, signal=False, skip_reason='stop_width'."""
    mod = _s1()
    trig, T = _s1_frame(tf, brk=S1_STOP_WIDTH_BRK)
    out = _checked(mod, trig, "range", tf, "S1")
    row = _row_ok(out, T, "S1")
    atr = I.atr(trig, 14).iloc[T]
    stop = trig["low"].iloc[T - 8:T].min() - 0.2 * atr
    assert (trig["close"].iloc[T] - stop) / atr > 3.0                        # sanity
    assert not bool(row.signal) and row.skip_reason == "stop_width"


@pytest.mark.parametrize("regime", ["trend_down", "volatile"])
def test_s1_blocked_regimes_for_long(regime):
    """K-6 / K-S1-6: trend_down'da yukari kirilim yok; volatile'da hic aday yok."""
    tf = "1h"
    trig, T = _s1_frame(tf)
    out = _checked(_s1(), trig, regime, tf, "S1")
    assert not bool(out["signal"].any())


# ============================================================================================= H2: giris kurali
@pytest.mark.parametrize("tf", ALL_TFS)
def test_h2_long_fires_on_second_leg_close(tf):
    mod = _h2()
    trig, T = _h2_frame(tf)
    out = _checked(mod, trig, "trend_up", tf, "H2")
    row = _row_ok(out, T, "H2")
    assert bool(row.signal) and row.setup == "H2" and row.side == "long"
    assert row.skip_reason is None or pd.isna(row.skip_reason)
    a = _arr(trig)
    h, lo, o, c = a["high"], a["low"], a["open"], a["close"]
    atr = I.atr(trig, 14).iloc[T]
    s = T - 7                                                 # tepe: [t-20, t-3] icinde en yuksek h
    ema20 = I.ema(trig["close"], 20)
    ema50 = I.ema(trig["close"], 50)
    pb = (h[s] - lo[s + 1:T + 1].min()) / atr
    stop = lo[s + 1:T + 1].min() - 0.3 * atr
    # sartname kosullari (sanity)
    assert int(np.argmax(h[T - 20:T - 2])) + (T - 20) == s
    assert h[T] > h[T - 1] and c[T] > h[T - 1] and c[T] > o[T]               # H2 kapanis teyidi
    assert c[T] > ema20.iloc[T] and ema20.iloc[T] > ema20.iloc[T - 5]         # trend ve EMA20 egimi
    assert pb >= 1.0 and (c[T] - stop) / atr <= 2.5
    assert all(c[k] >= ema50.iloc[k] for k in range(s + 1, T + 1))            # EMA50 gecersizligi yok
    # cikti
    assert row.planned_entry == pytest.approx(c[T], rel=1e-9)
    assert row.planned_stop == pytest.approx(stop, rel=1e-6)
    assert pd.isna(row.planned_target)                                        # hedef yok (trail)
    assert row.stop_dist_atr == pytest.approx((c[T] - stop) / atr, rel=1e-6)
    assert row.atr_tf == pytest.approx(atr, rel=1e-6)
    assert row.regime == "trend_up"
    # FEATURES tasiyicilari (K-5 features)
    assert row.ema_value == pytest.approx(ema20.iloc[T], rel=1e-6)            # ema_value = EMA20
    assert row.edge_dist_atr == pytest.approx(pb, rel=1e-6)                   # pb_depth_atr
    assert row.wick_ratio == pytest.approx(7.0, rel=1e-9)                     # pb_bars = t - s
    assert int(row.pullback_ema) == 3                                         # leg_gap = k2 - k1
    assert not bool(out["signal"].iloc[:T].any())
    assert not bool(out["signal"].iloc[T - 3])                                # H1 barinda aday yok (K-H2-2)


@pytest.mark.parametrize("tf", ALL_TFS)
def test_h2_short_is_exact_mirror_of_long(tf):
    mod = _h2()
    trig, T, reg = _positive("H2", tf)
    lo_out = _checked(mod, trig, reg, tf, "H2")
    sh_out = _checked(mod, _mirror(trig), MIRROR_REG[reg], tf, "H2")
    a = _row_ok(lo_out, T, "H2")
    b = _row_ok(sh_out, T, "H2")
    assert bool(a.signal) and bool(b.signal) and b.side == "short"
    assert b.planned_entry == pytest.approx(MIRROR_C - a.planned_entry, rel=1e-9)
    assert b.planned_stop == pytest.approx(MIRROR_C - a.planned_stop, rel=1e-6)


@pytest.mark.parametrize("name", sorted(H2_NEAR))
@pytest.mark.parametrize("tf", ALL_TFS)
def test_h2_near_miss_does_not_fire(tf, name):
    mod = _h2()
    trig, T = _h2_frame(tf, **H2_NEAR[name])
    out = _checked(mod, trig, "trend_up", tf, "H2")
    assert not bool(_row_ok(out, T, "H2").signal), name


@pytest.mark.parametrize("regime", ["range", "unclear", "volatile", "trend_down"])
def test_h2_blocked_regimes(regime):
    """K-6: H2 yalniz trend_up (ayni yon); range, unclear, volatile ve ters trend'de aday yok."""
    tf = "1h"
    trig, T = _h2_frame(tf)
    out = _checked(_h2(), trig, regime, tf, "H2")
    assert not bool(out["signal"].any())


# ============================================================================================= nedensellik (K-ORT-1/2/3)
@pytest.mark.parametrize("setup", SETUPS)
@pytest.mark.parametrize("tf", ALL_TFS)
def test_kesme_prefix_equals_full_row(setup, tf):
    """K-ORT-1: her k icin compute(trig[:k+1]) son satiri = compute(trig)'in k. satiri (rastgele yuruyus, 300 bar)."""
    mod = _mod(setup)
    trig = _rw(tf)
    regime = REGIME_OK[setup]
    full = _checked(mod, trig, regime, tf, setup)
    for k in list(range(0, len(trig), 9)) + [len(trig) - 1]:
        pref = _run(mod, trig.iloc[:k + 1], regime, tf)
        pd.testing.assert_series_equal(full.iloc[k], pref.iloc[-1], check_names=False)


@pytest.mark.parametrize("setup", SETUPS)
@pytest.mark.parametrize("tf", ALL_TFS)
def test_no_lookahead_future_bars_do_not_change_rows(setup, tf):
    """K-ORT-2: t'den sonraki barlar asiri degerle degistirilse <= t satirlari degismez."""
    mod = _mod(setup)
    base, T, reg = _positive(setup, tf, extra=6)
    poison = base.copy()
    poison.iloc[T + 1:] = poison.iloc[T + 1:] * 1000.0 + 500.0
    a = _checked(mod, base, reg, tf, setup)
    b = _run(mod, poison, reg, tf)
    pd.testing.assert_frame_equal(a.iloc[:T + 1], b.iloc[:T + 1])


@pytest.mark.parametrize("setup", SETUPS)
@pytest.mark.parametrize("tf", ALL_TFS)
def test_warmup_is_candidate_free(setup, tf):
    """K-ORT-3: len(trig) = LOOKBACK-1 -> hepsi adaysiz, hata yok (kurulum deseni olsa bile)."""
    mod = _mod(setup)
    n = _lookback(setup, tf) - 1
    if setup == "F1":
        trig, T = _f1_frame(tf, n=n)
    elif setup == "S1":
        trig, T = _s1_frame(tf, n=n)
    else:
        trig, T = _h2_frame(tf, n=n)
    out = _checked(mod, trig, REGIME_OK[setup], tf, setup)
    assert not bool(out["signal"].any())


@pytest.mark.parametrize("setup", SETUPS)
@pytest.mark.parametrize("tf", ALL_TFS)
def test_volatile_regime_is_candidate_free(setup, tf):
    """K-ORT-6: rejim volatile -> bes kurulumda da adaysiz (sinyal deseni var iken)."""
    mod = _mod(setup)
    trig, T, _ = _positive(setup, tf)
    out = _checked(mod, trig, "volatile", tf, setup)
    assert not bool(out["signal"].any())


@pytest.mark.parametrize("setup", SETUPS)
def test_determinism_same_input_same_table(setup):
    tf = "4h"
    mod = _mod(setup)
    trig, T, reg = _positive(setup, tf)
    a = _run(mod, trig, reg, tf)
    b = _run(mod, trig.copy(), reg, tf)
    pd.testing.assert_frame_equal(a, b)
