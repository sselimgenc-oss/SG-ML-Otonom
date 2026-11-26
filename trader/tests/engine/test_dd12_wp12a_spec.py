"""DD-12 WP-12a bagimsiz sartname testleri: kurulumlar TF1 ve B1 (Ek-K: docs/motor/dd12-ek-k-kurulumlar.md, K-1, K-2,
K-6, K-7, K-8) ve K-7 sozlesmesi (EXIT_MODE kurulum basina, FEATURES defter/SIGNAL_COLUMNS, PRIORITY) + T1/R1 tarafsizligi.

Gerceklemeye BAKILMADI: yalniz Ek-K, HEAD'deki sozlesme (arms/__init__, t1, r1, position_manager, strategy_runner) ve
WP-11 spec fixture'lari. Sentetik mumlar elle kurulur; ag yok.

Ek-K yorumlari (SPEC-AMBIGUOUS, testler sartnamenin acik dediklerini sinar):
  * Kurulum modulu `compute(ArmInput)` ile calisir; `ArmInput` alanlari HEAD'deki `arms/__init__.py`'dan.
  * `inp.core()` ortak tablosu regime ve baglam sutunlarini (atr_tf dahil) verir (K-7 "Bağlam sütunları").
  * FEATURES eslemesi K-7 madde 2'deki tablodur (defter anahtari -> SIGNAL_COLUMNS tasiyicisi).
  * Pozisyon testleri `position_manager.evaluate_exit` ile; kurulum adi (TF1/B1) EXIT_MODE'u tasir.
Kurulumlar henuz yoksa ilgili testler `importorskip` ile atlanir; gerceklemeden sonra yeniden kosulur.
"""
from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from trader_core import indicators as I
from trader_core import ledger as L
from trader_engine.types import Position
from trader_core import signals as S
from trader_engine.position_manager import ExitContext, evaluate_exit
from trader_engine.strategies import arms as AR
from trader_engine.strategies.arms import ArmError, ArmInput, make_arm_id, parse_arm_id
from trader_engine.strategies.base import validate_row, validate_table

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
ALL_TFS = ("15m", "1h", "4h", "1d")
FREQ = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
TD = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}
ARM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}@(15m|1h|4h|1d)$")
N_BARS = 150
DRIFT = 0.002          # sakin yukselis: EMA50 gecikmesi ~0,05 fiyat (ATR ~0,5)
HALF = 0.25            # sakin mumun yarim fitili: aralik ~0,5 (ATR ~0,5)
MIRROR_C = 200.0       # fiyat aynasi: p -> C - p


def _tf1():
    return pytest.importorskip("trader_engine.strategies.arms.tf1")


def _b1():
    return pytest.importorskip("trader_engine.strategies.arms.b1")


def _tf1_p(tf):   # K-1: N_BRK, EMA_F, EMA_S; 1g icin kisa pencereler
    return {"N": 20, "EF": 10, "ES": 30} if tf == "1d" else {"N": 50, "EF": 20, "ES": 50}


def _b1_p(tf):    # K-2: N_LVL
    return {"N": 20} if tf == "1d" else {"N": 40}


def _lookback(setup, tf):   # K-1/K-2 LOOKBACK tablosu
    if setup == "TF1":
        return 50 if tf == "1d" else 120
    return 45 if tf == "1d" else 70


# ============================================================================================= sentetik mum kurucular
def _frame(rows, tf):
    arr = np.array(rows, dtype=float)                     # satir: (o, h, l, c)
    idx = pd.date_range("2026-02-02 00:00", periods=len(rows), freq=FREQ[tf], tz="UTC")
    return pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3],
                         "volume": 1.0}, index=idx)


def _tf1_bars(tf, events=None, *, n=N_BARS, drift=DRIFT, p0=100.0):
    """Sakin yukselis; `events[i] = (hareket, fitil)`: o=onceki kapanis, c=o+hareket, h/l = min/max +- fitil.
    Fitil None ise sakin mum (h=c+HALF, l=o-HALF)."""
    events = events or {}
    rows, prev = [], p0
    for i in range(n):
        o = prev
        mv, wk = events.get(i, (drift, None))
        c = o + mv
        if wk is None:
            h, lo = c + HALF, o - HALF
        else:
            h, lo = max(o, c) + wk, min(o, c) - wk
        rows.append((o, h, lo, c))
        prev = c
    return _frame(rows, tf)


BG = (99.0, 99.5, 98.5, 99.2)          # B1 zemini: h=99,5 < L - 0,25 ATR (dokunma sayilmaz)
SPK = (99.0, 100.0, 98.5, 99.2)        # seviye dokunusu: h=100,0 (= L)
BRK = (99.6, 101.2, 99.5, 101.0)       # kirilim: c=101,0 > L + 0,2 ATR; body ~0,82
TOUCH = (101.0, 101.0, 100.0, 100.4)   # retest dokunusu: l=100,0 <= L + 0,25 ATR; kapanis >= L
BEAR = (100.5, 100.6, 100.1, 100.3)    # ara bar: kapanis >= L, boga degil (c<o)
BULL = (100.3, 101.4, 100.2, 101.2)    # tetik: c>o, c>L, dokunma var (l=100,2)
NT_BEAR = (100.9, 101.0, 100.6, 100.7)  # dokunmasiz ara bar
NT_BULL = (100.7, 101.6, 100.5, 101.4)  # dokunmasiz tetik (l=100,5 > L + 0,25)


def _b1_bars(tf, *, gap=4, bulls_off=None, spike_mode="two", over=None, retest="touch", n=N_BARS):
    """Uzun taraf B1 senaryosu. t = n-1, kirilim i0 = t-gap. over: {i0'a gore ofset: (o,h,l,c)}."""
    nl = _b1_p(tf)["N"]
    t = n - 1
    i0 = t - gap
    rows = [BG] * n
    if spike_mode == "two":
        spikes = (i0 - nl + 3, i0 - nl + 12)
    elif spike_mode == "one":
        spikes = (i0 - nl + 3,)
    else:                                                  # "young": seviyeyi veren bar i0-2'de
        spikes = (i0 - 10, i0 - 2)
    for k in spikes:
        rows[k] = SPK
    rows[i0] = BRK
    bulls = {t} if bulls_off is None else {i0 + o for o in bulls_off}
    for k in range(i0 + 1, t + 1):
        if retest == "none":
            rows[k] = NT_BULL if k in bulls else NT_BEAR
        else:
            if k in bulls:
                rows[k] = BULL
            elif k == i0 + 1:
                rows[k] = TOUCH
            else:
                rows[k] = BEAR
    for off, row in (over or {}).items():
        rows[i0 + off] = row
    return _frame(rows, tf)


def _mirror(df):
    out = df.copy()
    out["open"] = MIRROR_C - df["open"]
    out["high"] = MIRROR_C - df["low"]
    out["low"] = MIRROR_C - df["high"]
    out["close"] = MIRROR_C - df["close"]
    return out


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


TF1_FEATURES = {"brk_dist_atr": "edge_dist_atr", "ema_value": "ema_value", "body_ratio": "body_ratio",
                "ext_atr": "wick_ratio", "brk_n": "pullback_ema"}
B1_FEATURES = {"level": "ema_value", "brk_dist_atr": "edge_dist_atr", "retest_depth_atr": "wick_ratio",
               "body_ratio": "body_ratio", "bars_since_brk": "pullback_ema", "rr": "rr"}


# ============================================================================================= K-7: sozlesme
@pytest.mark.parametrize("setup", ["TF1", "B1"])
def test_contract_module_attributes(setup):
    mod = _tf1() if setup == "TF1" else _b1()
    assert mod.SETUP == setup
    assert tuple(mod.TIMEFRAMES) == ("1h", "4h", "1d")                      # 26.11 sahip karari: 15m giris kolu yok
    assert mod.CORE is False                              # kendi hesabi; ortak tablo satiri secmez
    assert callable(mod.compute)
    assert mod.EXIT_MODE in ("trail", "target")
    assert isinstance(mod.PRIORITY, int) and not isinstance(mod.PRIORITY, bool)


def test_exit_mode_per_arm():
    """K-7 madde 1: cikis kipi kurulum basina; TF1 iz suren (trail), B1 hedefli (target). T1/R1 degismez."""
    assert _tf1().EXIT_MODE == "trail"
    assert _b1().EXIT_MODE == "target"
    assert AR.find_arm("T1").EXIT_MODE == "trail"
    assert AR.find_arm("R1").EXIT_MODE == "target"


@pytest.mark.parametrize("setup", ["TF1", "B1"])
def test_features_mapping_and_carriers_in_signal_columns(setup):
    """K-7 madde 2: FEATURES defter anahtari -> SIGNAL_COLUMNS tasiyicisi; sinyal satirinda tasiyicilar sonlu."""
    mod = _tf1() if setup == "TF1" else _b1()
    want = TF1_FEATURES if setup == "TF1" else B1_FEATURES
    assert dict(mod.FEATURES) == want
    assert set(mod.FEATURES.values()) <= set(S.SIGNAL_COLUMNS)
    assert not ({"rh", "rl", "rh_touches", "rl_touches"} & set(mod.FEATURES.values()))   # K-7: baglam tasinmaz


@pytest.mark.parametrize("setup", ["TF1", "B1"])
def test_features_accepted_by_ledger(setup):
    """K-7 madde 2: FEATURES tasiyicilariyla kurulan defter ozellik sozlugu ledger tarafindan kabul edilir."""
    mod = _tf1() if setup == "TF1" else _b1()
    tf = "1h"
    if setup == "TF1":
        trig, regime = _tf1_bars(tf, {N_BARS - 1: (0.8, 0.05)}), "trend_up"
    else:
        trig, regime = _b1_bars(tf), "range"
    out = _checked(mod, trig, regime, tf, setup)
    row = _row_ok(out, len(trig) - 1, setup)
    assert bool(row.signal)
    feats = {"atr_tf": float(row.atr_tf), "stop_dist_atr": float(row.stop_dist_atr),
             "atr_4h": float(row.atr_4h), "rh_touches": 0, "rl_touches": 0}
    for key, col in mod.FEATURES.items():
        v = row[col]
        feats[key] = int(v) if col == "pullback_ema" else float(v)
    owners = [vars(getattr(L, n))["_prep_features"] for n in dir(L)
              if isinstance(getattr(L, n), type) and "_prep_features" in vars(getattr(L, n))]
    assert owners, "ledger _prep_features bulunamadi"
    prep = owners[0]
    fn = prep.__func__ if isinstance(prep, staticmethod) else prep
    fn(feats, setup)                                       # LedgerValidationError firlatirsa test kirar


PRIORITY_WANT = {"T1": 10, "R1": 20, "TF1": 30, "B1": 40, "H2": 50, "S1": 60, "F1": 70}


def test_priority_values_and_order_within_timeframe():
    """K-7 madde 3 + K-6: ayni zaman diliminde T1 > R1 > TF1 > B1 > H2 > S1 > F1 (sayi kucuk = once)."""
    prios = {}
    for s in ("T1", "R1"):
        prios[s] = AR.find_arm(s).PRIORITY
    prios["TF1"] = _tf1().PRIORITY
    prios["B1"] = _b1().PRIORITY
    for s, v in prios.items():
        assert v == PRIORITY_WANT[s], (s, v)
    order = sorted(prios, key=lambda s: prios[s])
    assert order == ["T1", "R1", "TF1", "B1"]


def test_arm_discovery_and_arm_id_format():
    _tf1()
    _b1()
    names = set(AR.list_arms())
    assert {"TF1", "B1", "T1", "R1"} <= names
    for setup in ("TF1", "B1"):
        for tf in ALL_TFS:
            arm = make_arm_id(setup, tf)
            assert ARM_RE.match(arm), arm
            assert parse_arm_id(arm) == (setup, tf)
    with pytest.raises(ArmError):
        parse_arm_id("TF1@2h")
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


@pytest.mark.parametrize("setup", ["TF1", "T1"])
def test_trail_exit_for_trend_setups(setup):
    """K-7 madde 1 + K-6: trend kurulumlari (TF1, T1) iz suren stop kurar: 1R sonrasi en yuksek - 3 ATR."""
    highs = np.linspace(100.5, 110.0, 20)
    d = _exit(setup, highs=highs, lows=highs - 1.0, atrs=np.ones(20), regime_last="trend_up", last_close=109.5)
    assert d.kind == "stop_update", d
    assert any(abs(v - 107.0) < 1.0 for v in _floats(d)), d


@pytest.mark.parametrize("setup", ["TF1", "T1"])
def test_trend_setup_regime_flip_exit(setup):
    highs = np.linspace(100.5, 101.0, 5)
    d = _exit(setup, highs=highs, lows=highs - 1.0, atrs=np.ones(5), regime_last="trend_down", last_close=100.8)
    assert d.kind == "exit" and d.reason == "regime_flip", d


@pytest.mark.parametrize("setup", ["B1", "R1"])
def test_target_exit_for_target_setups(setup):
    """K-7 madde 1 + K-7 B1 hedefi: hedefe degen bar -> target cikisi (iz suren stop yok)."""
    highs = np.linspace(100.5, 104.5, 10)
    d = _exit(setup, target=104.0, highs=highs, lows=highs - 1.0, atrs=np.ones(10), regime_last="range",
              last_close=104.2)
    assert d.kind == "exit" and d.reason == "target", d


def test_b1_no_trailing_stop_and_no_regime_flip():
    """K-7 / K-B1-7: B1 pozisyonunda iz suren stop kurulmaz (en yuksek-3 ATR 100 > 98 olsa da), regime_flip yok."""
    highs = np.linspace(100.5, 103.0, 10)
    d = _exit("B1", target=104.0, highs=highs, lows=highs - 1.0, atrs=np.ones(10), regime_last="trend_down",
              last_close=102.8)
    assert d.kind == "none", d


# ============================================================================================= TF1: giris kurali
@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_long_fires_on_fresh_close_breakout(tf):
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 1: (0.8, 0.05)})
    out = _checked(mod, trig, "trend_up", tf, "TF1")
    t = len(trig) - 1
    row = _row_ok(out, t, "TF1")
    assert bool(row.signal) and row.setup == "TF1" and row.side == "long"
    assert row.skip_reason is None or pd.isna(row.skip_reason)
    p = _tf1_p(tf)
    c = trig["close"].to_numpy()
    o = trig["open"].to_numpy()
    h = trig["high"].to_numpy()
    lo = trig["low"].to_numpy()
    atr = I.atr(trig, 14).iloc[t]
    hc = c[t - p["N"]:t].max()                             # HC(t) = max(c[t-N .. t-1])
    stop = hc - 1.0 * atr                                  # stop = HC - 1,0 ATR
    ema_s = I.ema(trig["close"], p["ES"]).iloc[t]
    ext = (c[t] - ema_s) / atr
    assert c[t] > hc + 0.2 * atr and ext <= 3.0 and (c[t] - o[t]) / (h[t] - lo[t]) >= 0.5   # sartlar gercekten saglanir
    assert row.planned_entry == pytest.approx(c[t], rel=1e-9)
    assert row.planned_stop == pytest.approx(stop, rel=1e-6)
    assert pd.isna(row.planned_target)                     # hedef yok (trail)
    assert row.stop_dist_atr == pytest.approx((c[t] - stop) / atr, rel=1e-6)
    assert row.atr_tf == pytest.approx(atr, rel=1e-6)
    assert row.regime == "trend_up"
    # FEATURES tasiyicilari (K-1 features)
    assert row.ema_value == pytest.approx(ema_s, rel=1e-6)
    assert row.edge_dist_atr == pytest.approx((c[t] - hc) / atr, rel=1e-6)   # brk_dist_atr
    assert row.wick_ratio == pytest.approx(ext, rel=1e-6)                      # ext_atr
    assert row.body_ratio == pytest.approx((c[t] - o[t]) / (h[t] - lo[t]), rel=1e-6)
    assert int(row.pullback_ema) == p["N"]                                     # brk_n = N_BRK
    assert not bool(out["signal"].iloc[:t].any())          # sakin yukselisde onceki barlarda sinyal yok


@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_short_is_exact_mirror_of_long(tf):
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 1: (0.8, 0.05)})
    lo_out = _checked(mod, trig, "trend_up", tf, "TF1")
    sh_out = _checked(mod, _mirror(trig), "trend_down", tf, "TF1")
    t = len(trig) - 1
    a = _row_ok(lo_out, t, "TF1")
    b = _row_ok(sh_out, t, "TF1")
    assert bool(a.signal) and bool(b.signal)
    assert b.side == "short"
    assert b.planned_entry == pytest.approx(MIRROR_C - a.planned_entry, rel=1e-9)
    assert b.planned_stop == pytest.approx(MIRROR_C - a.planned_stop, rel=1e-6)


@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_weak_breakout_does_not_fire(tf):
    """Kirilim 0,2 ATR esiginin altinda (+0,05 < 0,2 ATR) -> aday yok. Govde 1,0 (fitil yok): yalniz esik sinanir."""
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 1: (0.05, 0.0)})
    out = _checked(mod, trig, "trend_up", tf, "TF1")
    t = len(trig) - 1
    atr = I.atr(trig, 14).iloc[t]
    assert trig["close"].iloc[t] - trig["close"].iloc[t - 1] < 0.2 * atr    # sanity: gercekten esik altinda
    assert not bool(_row_ok(out, t, "TF1").signal)


@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_too_extended_does_not_fire(tf):
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 1: (2.5, 0.05)})
    out = _checked(mod, trig, "trend_up", tf, "TF1")
    t = len(trig) - 1
    atr = I.atr(trig, 14).iloc[t]
    ema_s = I.ema(trig["close"], _tf1_p(tf)["ES"]).iloc[t]
    assert (trig["close"].iloc[t] - ema_s) / atr > 3.0                      # sanity: ext > 3
    assert not bool(_row_ok(out, t, "TF1").signal)


@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_stop_width_skip_reason(tf):
    """sda > 3,0: satir yazilir, signal=False, skip_reason='stop_width' (ext <= 3 iken)."""
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 1: (1.3, 0.05)})
    out = _checked(mod, trig, "trend_up", tf, "TF1")
    t = len(trig) - 1
    atr = I.atr(trig, 14).iloc[t]
    c = trig["close"].to_numpy()
    hc = c[t - _tf1_p(tf)["N"]:t].max()
    ema_s = I.ema(trig["close"], _tf1_p(tf)["ES"]).iloc[t]
    assert (c[t] - hc + atr) / atr > 3.0 and (c[t] - ema_s) / atr <= 3.0   # sanity: yalniz stop genisligi ihlal
    row = _row_ok(out, t, "TF1")
    assert not bool(row.signal) and row.skip_reason == "stop_width"


@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_consecutive_breakout_single_signal(tf):
    """K-TF1-3: ardisik iki kirilim barinda yalniz ilki sinyal (not brk(t-1))."""
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 2: (0.8, 0.05), N_BARS - 1: (0.8, 0.05)})
    out = _checked(mod, trig, "trend_up", tf, "TF1")
    t = len(trig) - 1
    assert bool(_row_ok(out, t - 1, "TF1").signal)
    assert not bool(_row_ok(out, t, "TF1").signal)


@pytest.mark.parametrize("regime", ["range", "trend_down", "unclear", "volatile"])
def test_tf1_only_trend_up_regime(regime):
    """K-6: TF1 yalniz trend_up (yon ayni). range/unclear/volatile/ters trend -> aday yok."""
    tf = "1h"
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 1: (0.8, 0.05)})
    out = _checked(mod, trig, regime, tf, "TF1")
    assert not bool(out["signal"].any())


@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_requires_ema_fast_above_slow(tf):
    """K-1 sart 2: EMA_F > EMA_S. Dusen seride tepe kirilimi olsa da EMA_F < EMA_S -> aday yok."""
    mod = _tf1()
    trig = _tf1_bars(tf, {N_BARS - 1: (0.8, 0.05)}, drift=-0.01)   # dik dusus: kirilim barinda da EMA_F < EMA_S
    out = _checked(mod, trig, "trend_up", tf, "TF1")
    p = _tf1_p(tf)
    t = len(trig) - 1
    ef = I.ema(trig["close"], p["EF"]).iloc[t]
    es = I.ema(trig["close"], p["ES"]).iloc[t]
    assert ef < es                                         # sanity: sart gercekten ihlal
    assert not bool(_row_ok(out, t, "TF1").signal)


@pytest.mark.parametrize("tf", ALL_TFS)
def test_tf1_warmup_is_candidate_free(tf):
    """K-ORT-3: len(trig) = LOOKBACK-1 -> hepsi adaysiz, hata yok (kirilim son barda olsa bile)."""
    mod = _tf1()
    n = _lookback("TF1", tf) - 1
    trig = _tf1_bars(tf, {n - 1: (0.8, 0.05)}, n=n)
    out = _checked(mod, trig, "trend_up", tf, "TF1")
    assert not bool(out["signal"].any())


# ============================================================================================= B1: giris kurali
@pytest.mark.parametrize("tf", ALL_TFS)
def test_b1_long_fires_on_retest_and_plans_2r(tf):
    mod = _b1()
    trig = _b1_bars(tf)
    out = _checked(mod, trig, "range", tf, "B1")
    t = len(trig) - 1
    i0 = t - 4
    row = _row_ok(out, t, "B1")
    assert bool(row.signal) and row.setup == "B1" and row.side == "long"
    atr = I.atr(trig, 14).iloc[t]
    lvl = 100.0                                            # L = RH(i0-1): iki dokunmali 100,0 seviyesi
    assert trig["close"].iloc[i0] > lvl + 0.2 * I.atr(trig, 14).iloc[i0]          # kirilim sarti (sanity)
    stop = trig["low"].iloc[i0 + 1:t + 1].min() - S.DEFAULT_SIGNAL_PARAMS.stop_buffer_atr * atr
    entry = trig["close"].iloc[t]
    target = entry + 2.0 * (entry - stop)
    assert row.planned_entry == pytest.approx(entry, rel=1e-9)
    assert row.planned_stop == pytest.approx(stop, rel=1e-6)
    assert row.planned_target == pytest.approx(target, rel=1e-6)
    assert row.rr == pytest.approx(2.0, rel=1e-6)
    # FEATURES (K-2): level, brk_dist_atr, retest_depth_atr, body_ratio, bars_since_brk, rr
    assert row.ema_value == pytest.approx(lvl, rel=1e-9)                                # level
    assert row.edge_dist_atr == pytest.approx(
        (trig["close"].iloc[i0] - lvl) / I.atr(trig, 14).iloc[i0], rel=1e-6)            # brk_dist_atr
    assert row.wick_ratio == pytest.approx(
        (trig["low"].iloc[i0 + 1:t + 1].min() - lvl) / atr, abs=1e-6)                   # retest_depth_atr (=0)
    assert int(row.pullback_ema) == 4                                                    # bars_since_brk = t-i0
    assert 0.0 <= row.body_ratio <= 1.0
    assert not bool(out["signal"].iloc[:t].any())


@pytest.mark.parametrize("tf", ALL_TFS)
def test_b1_short_is_exact_mirror_of_long(tf):
    mod = _b1()
    trig = _b1_bars(tf)
    lo_out = _checked(mod, trig, "range", tf, "B1")
    sh_out = _checked(mod, _mirror(trig), "range", tf, "B1")
    t = len(trig) - 1
    a = _row_ok(lo_out, t, "B1")
    b = _row_ok(sh_out, t, "B1")
    assert bool(a.signal) and bool(b.signal) and b.side == "short"
    assert b.planned_entry == pytest.approx(MIRROR_C - a.planned_entry, rel=1e-9)
    assert b.planned_stop == pytest.approx(MIRROR_C - a.planned_stop, rel=1e-6)
    assert b.planned_target == pytest.approx(MIRROR_C - a.planned_target, rel=1e-6)


B1_NEAR = {
    "weak_breakout": dict(over={0: (99.6, 100.2, 99.5, 100.1)}),        # c = 100,1 < L + 0,2 ATR
    "small_body": dict(over={0: (99.6, 102.0, 99.0, 101.0)}),           # govde 0,47 < 0,5
    "single_touch": dict(spike_mode="one"),                              # tek dokunus kumesi
    "level_too_young": dict(spike_mode="young"),                         # seviyeyi veren bar i0-2
    "close_below_level": dict(over={2: (100.5, 100.6, 99.7, 99.8)}),    # retest'te kapanis < L: kirilim olur
    "no_retest": dict(retest="none"),                                    # retest yok
    "retest_window_expired": dict(gap=11),                               # t - i0 = 11 > 10
}


@pytest.mark.parametrize("tf", ALL_TFS)
@pytest.mark.parametrize("name", sorted(B1_NEAR))
def test_b1_near_miss_does_not_fire(tf, name):
    mod = _b1()
    trig = _b1_bars(tf, **B1_NEAR[name])
    out = _checked(mod, trig, "range", tf, "B1")
    t = len(trig) - 1
    assert not bool(_row_ok(out, t, "B1").signal), name


@pytest.mark.parametrize("tf", ALL_TFS)
def test_b1_stop_width_skip_reason(tf):
    """retest dibi sda > 2,5 -> signal=False, skip_reason='stop_width'."""
    mod = _b1()
    trig = _b1_bars(tf, over={2: (100.5, 100.6, 96.0, 100.3)})
    out = _checked(mod, trig, "range", tf, "B1")
    t = len(trig) - 1
    row = _row_ok(out, t, "B1")
    assert not bool(row.signal) and row.skip_reason == "stop_width"


@pytest.mark.parametrize("tf", ALL_TFS)
def test_b1_one_signal_per_breakout(tf):
    """K-B1-5 / sart 4: ayni kirilimda iki uygun retest -> yalniz ilki (t-2) sinyal verir, ikincisi (t) vermez."""
    mod = _b1()
    trig = _b1_bars(tf, gap=6, bulls_off=(4, 6))
    out = _checked(mod, trig, "range", tf, "B1")
    t = len(trig) - 1
    assert bool(_row_ok(out, t - 2, "B1").signal)
    assert not bool(_row_ok(out, t, "B1").signal)


@pytest.mark.parametrize("regime", ["trend_down", "volatile"])
def test_b1_blocked_regimes(regime):
    """K-6: B1 trend_down ve volatile'da aday vermez."""
    tf = "1h"
    mod = _b1()
    out = _checked(mod, _b1_bars(tf), regime, tf, "B1")
    assert not bool(out["signal"].any())


@pytest.mark.parametrize("regime", ["trend_up", "range", "unclear"])
def test_b1_allowed_regimes(regime):
    """K-6: B1 trend_up, range, unclear'da calisir (ayni sentetik kurulum)."""
    tf = "1h"
    mod = _b1()
    out = _checked(mod, _b1_bars(tf), regime, tf, "B1")
    assert bool(_row_ok(out, len(out) - 1, "B1").signal)


@pytest.mark.parametrize("tf", ALL_TFS)
def test_b1_warmup_is_candidate_free(tf):
    mod = _b1()
    n = _lookback("B1", tf) - 1
    trig = _b1_bars(tf, n=n, gap=4)
    out = _checked(mod, trig, "range", tf, "B1")
    assert not bool(out["signal"].any())


# ============================================================================================= nedensellik (K-ORT-1/2)
def _rw(tf, n=300, seed=17):
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 0.6, n))
    o = np.concatenate([[100.0], c[:-1]])
    h = np.maximum(o, c) + rng.uniform(0.05, 0.6, n)
    lo = np.minimum(o, c) - rng.uniform(0.05, 0.6, n)
    return _frame(list(zip(o, h, lo, c)), tf)


@pytest.mark.parametrize("setup", ["TF1", "B1"])
@pytest.mark.parametrize("tf", ALL_TFS)
def test_kesme_prefix_equals_full_row(setup, tf):
    """K-ORT-1: her k icin compute(trig[:k+1]) son satiri = compute(trig)'in k. satiri (rastgele yuruyus, 300 bar)."""
    mod = _tf1() if setup == "TF1" else _b1()
    trig = _rw(tf)
    regime = "trend_up" if setup == "TF1" else "range"
    full = _checked(mod, trig, regime, tf, setup)
    for k in list(range(0, len(trig), 9)) + [len(trig) - 1]:
        pref = _run(mod, trig.iloc[:k + 1], regime, tf)
        pd.testing.assert_series_equal(full.iloc[k], pref.iloc[-1], check_names=False)


@pytest.mark.parametrize("setup", ["TF1", "B1"])
@pytest.mark.parametrize("tf", ALL_TFS)
def test_no_lookahead_future_bars_do_not_change_rows(setup, tf):
    """K-ORT-2: t'den sonraki barlar asiri degerle degistirilse <= t satirlari degismez."""
    mod = _tf1() if setup == "TF1" else _b1()
    if setup == "TF1":
        base = _tf1_bars(tf, {N_BARS - 1: (0.8, 0.05)}, n=N_BARS + 6)
        regime = "trend_up"
    else:
        base = _b1_bars(tf, n=N_BARS + 6, gap=4)
        regime = "range"
    k = N_BARS - 1
    poison = base.copy()
    poison.iloc[k + 1:] = poison.iloc[k + 1:] * 1000.0 + 500.0
    a = _checked(mod, base, regime, tf, setup)
    b = _run(mod, poison, regime, tf)
    pd.testing.assert_frame_equal(a.iloc[:k + 1], b.iloc[:k + 1])


@pytest.mark.parametrize("setup", ["TF1", "B1"])
def test_determinism_same_input_same_table(setup):
    tf = "4h"
    mod = _tf1() if setup == "TF1" else _b1()
    trig = _tf1_bars(tf, {N_BARS - 1: (0.8, 0.05)}) if setup == "TF1" else _b1_bars(tf)
    regime = "trend_up" if setup == "TF1" else "range"
    a = _run(mod, trig, regime, tf)
    b = _run(mod, trig.copy(), regime, tf)
    pd.testing.assert_frame_equal(a, b)


# ============================================================================================= tarafsizlik (T1/R1)
def test_neutrality_t1_r1_wp11_unchanged():
    """T1/R1 ciktilari degismez: WP-11 D-T18 esdegerligi (T1/R1@1h = price_action_v1_full) ve altin ozetler kosulur."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/engine/test_dd12_wp11_spec.py",
         "-k", "dt18_lab_t1_r1_at_1h or neutrality_existing_strategies"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=1500, env=env)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
