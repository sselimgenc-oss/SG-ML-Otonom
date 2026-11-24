"""S2-1 (4 saatlik tetik) strateji testleri; bagimsiz yazar. Sartname: docs/ml/s2-on-kayit.md §5, H-1..H-12.
Yalniz sentetik mumlar; gercek veri yok."""
from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import regime as R
from trader_core import signals as S
from trader_engine.position_manager import ExitContext, ExitDecision, evaluate_exit
from trader_engine.strategies import registry as REG
from trader_engine.strategies.base import StrategyContext, StrategyError, validate_table
from trader_engine.types import Position

M = pytest.importorskip("trader_engine.strategies.price_action_v1_4h")

UTC = timezone.utc
OHLC = ["open", "high", "low", "close"]
PARAMS = dataclasses.asdict(S.DEFAULT_SIGNAL_PARAMS)
OFF = "s2_1:off_grid"
NUM_COLS = ["planned_entry", "planned_stop", "planned_target", "rr", "stop_dist_atr", "atr_tf", "atr_4h",
            "atr_ratio", "rh", "rl", "rh_touches", "rl_touches", "ema_value", "body_ratio", "wick_ratio",
            "edge_dist_atr", "pullback_ema"]
MAP_COLS = ["planned_entry", "planned_stop", "side", "setup", "atr_tf", "regime", "reasons"]


# ------------------------------------------------------------------ sentetik veri
def _bars(seed: int, n: int = 6400, drift: float = 0.0006, vol: float = 0.006) -> pd.DataFrame:
    """1 saatlik, 00:00 UTC'de baslayan, n % 4 == 0; donusumlu surukleme (trend + geri cekilme)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=n, freq="1h", tz="UTC")
    d = np.where((np.arange(n) // 400) % 2 == 0, drift, -drift)
    c = np.round(100 * np.exp(np.cumsum(rng.normal(d, vol))), 4)
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, .002, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, .002, n)))
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": 1.0}, index=idx)


def _h4(b: pd.DataFrame) -> pd.DataFrame:
    return b.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()


def _ctx(b, h4, D=None, last_exit=None) -> StrategyContext:
    D = D or (b.index[-1] + timedelta(hours=1)).to_pydatetime()
    return StrategyContext(pair="BTC/USDT", D=D, tf="1h", params=PARAMS, bars={"1h": b, "4h": h4}, last_exit=last_exit)


def _ref4(h4: pd.DataFrame) -> pd.DataFrame:
    reg = R.classify_series(h4[OHLC], S.SignalParams.from_mapping(PARAMS).regime_params())
    al = R.align_to_base(reg, h4.index, 4)
    return S.compute_signals(h4[OHLC], al, S.SignalParams.from_mapping(PARAMS))


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b):
        return True
    return a == b


@pytest.fixture(scope="module")
def world():
    best = None
    for seed in (0, 1, 2, 3, 4):
        b = _bars(seed)
        h4 = _h4(b)
        ref = _ref4(h4)
        n_sig = int(ref["signal"].sum())
        if best is None or n_sig > best[0]:
            best = (n_sig, b, h4, ref)
    n_sig, b, h4, ref = best
    strat = M.make_v1b_4h()
    sig = strat.compute(_ctx(b, h4))
    return dict(b=b, h4=h4, ref=ref, strat=strat, sig=sig, n_sig=n_sig)


def test_fixture_has_signals(world):
    assert world["n_sig"] >= 5        # veri uretici yeterli sinyal verir (testler bos gecmesin)


# ------------------------------------------------------------------ H-1
def test_h1_table_schema(world):
    sig, strat, b = world["sig"], world["strat"], world["b"]
    validate_table(sig, strat.info, b.index)
    assert set(sig.columns) == set(S.SIGNAL_COLUMNS)
    assert len(sig) == len(b) and sig.index.equals(b.index)


# ------------------------------------------------------------------ H-2
def test_h2_signals_only_on_h4_close_rows(world):
    sig = world["sig"]
    on = sig[sig["signal"].astype(bool)]
    assert len(on) >= 5
    assert (on.index.hour % 4 == 3).all()
    off = sig[sig.index.hour % 4 != 3]
    assert (off["reasons"] == OFF).all()
    assert not off["signal"].astype(bool).any()
    for c in ("setup", "side", "skip_reason", "regime"):
        assert off[c].isna().all(), c
    for c in NUM_COLS:
        assert off[c].isna().all(), c


# ------------------------------------------------------------------ H-3
def test_h3_mapping_to_h4_rows(world):
    sig, ref, h4, b = world["sig"], world["ref"], world["h4"], world["b"]
    rows = ref[ref["signal"].astype(bool) & (ref["setup"] == "T1")]
    assert len(rows) >= 5
    for T, r in rows.iterrows():
        row1 = sig.loc[T + timedelta(hours=3)]
        for c in MAP_COLS:
            assert _same(row1[c], r[c]), (T, c, row1[c], r[c])
        assert row1["planned_entry"] == pytest.approx(float(h4.loc[T, "close"]))
        assert bool(row1["signal"])
    # sinyal olmayan 4 saatlik satirlar da aynen kopyalanir (tam esleme)
    for T in ref.index[200:260]:
        T1 = T + timedelta(hours=3)
        if T1 not in sig.index or ref.loc[T, "setup"] == "R1":       # R1 satirlari H-5'te
            continue
        for c in S.SIGNAL_COLUMNS:
            assert _same(sig.loc[T1, c], ref.loc[T, c]) or (
                isinstance(ref.loc[T, c], (float, np.floating)) and np.isnan(ref.loc[T, c]) and pd.isna(sig.loc[T1, c])), (T, c)


def test_h3_missing_hourly_row_is_dropped(world):
    """4 saatlik satirin T+3s 1 saatlik mumu yoksa satir dusar (cikti 1 saatlik indeks uzerindedir)."""
    b, h4, ref = world["b"], world["h4"], world["ref"]
    T = ref.index[ref["signal"].astype(bool) & (ref["setup"] == "T1")][0]
    T1 = T + timedelta(hours=3)
    b2 = b.drop(T1)
    sig2 = world["strat"].compute(_ctx(b2, h4))
    assert T1 not in sig2.index and len(sig2) == len(b2)
    assert sig2["signal"].astype(bool).sum() == world["sig"]["signal"].astype(bool).sum() - 1


# ------------------------------------------------------------------ H-4
def test_h4_causality(world):
    b, h4, full, strat = world["b"], world["h4"], world["sig"], world["strat"]
    rng = np.random.default_rng(123)
    sig_pos = np.flatnonzero(full["signal"].to_numpy(bool))
    pool = np.arange(1700, len(b) - 1)
    cuts = list(rng.choice(pool, 14, replace=False))
    cuts += [int(sig_pos[len(sig_pos) // 2]), int(sig_pos[len(sig_pos) // 2]) - 1,
             int(sig_pos[0]), int(sig_pos[-1]), int(sig_pos[-1]) - 2, int(sig_pos[1]) + 1]
    assert len(set(cuts)) == 20
    for i in cuts:
        D = (b.index[i] + timedelta(hours=1)).to_pydatetime()
        bt = b.iloc[:i + 1]
        h4t = h4[h4.index + timedelta(hours=4) <= pd.Timestamp(D)]
        part = strat.compute(_ctx(bt, h4t, D=D))
        pd.testing.assert_frame_equal(part, full.iloc[:i + 1], check_exact=False, check_dtype=False)


# ------------------------------------------------------------------ H-5
def test_h5_r1_disabled(world):
    b, h4, ref, sig = world["b"], world["h4"], world["ref"], world["sig"]
    r1 = ref.index[ref["setup"] == "R1"]
    if len(r1) == 0:                                  # R1 uretmeyen seri: aralik agirlikli seriyle dene
        for seed in range(10, 40):
            b = _bars(seed, n=4800, drift=0.0, vol=0.004)
            h4 = _h4(b)
            ref = _ref4(h4)
            r1 = ref.index[ref["setup"] == "R1"]
            if len(r1):
                sig = world["strat"].compute(_ctx(b, h4))
                break
    assert len(r1) >= 1, "sentetik seri R1 kurulumu uretmedi"
    for T in r1:
        row = sig.loc[T + timedelta(hours=3)]
        assert not bool(row["signal"])
        assert str(row["reasons"]).startswith("v1b:r1_disabled|")
        assert row["setup"] == "R1"
        assert row["skip_reason"] is None
    # R1 oldugu icin signal=False olan satir, ham hesapta signal=True olabilirdi: toplamda R1 kaynakli sinyal yok
    on = sig[sig["signal"].astype(bool)]
    assert (on["setup"] == "T1").all()


# ------------------------------------------------------------------ H-6
def _a_signal_row(world):
    sig = world["sig"]
    return sig[sig["signal"].astype(bool)].iloc[0]


def test_h6_post_filter_reentry(world):
    strat, b, h4 = world["strat"], world["b"], world["h4"]
    row = _a_signal_row(world)
    D = datetime(2022, 6, 1, 8, 0, tzinfo=UTC)
    f = lambda ts, why: strat.post_filter(row, _ctx(b, h4, D=D, last_exit=(ts, why)))   # noqa: E731
    r = f(D - timedelta(hours=3, minutes=30), "stop")
    assert not bool(r["signal"]) and r["skip_reason"] is None
    assert str(r["reasons"]).startswith("v1b:same_bar_reentry|") and str(r["reasons"]).endswith(str(row["reasons"]))
    assert not bool(f(D - timedelta(hours=3, minutes=30), "trail_stop")["signal"])
    assert not bool(f(D - timedelta(hours=4), "stop")["signal"])                       # [D-4s, D) kapali alt sinir
    assert not bool(f(D - timedelta(minutes=1), "stop")["signal"])
    kept = f(D - timedelta(hours=4, minutes=1), "stop")
    assert bool(kept["signal"]) and kept["reasons"] == row["reasons"]
    assert bool(f(D - timedelta(hours=1), "regime_flip")["signal"])
    assert bool(f(D, "stop")["signal"])                                                 # D disi
    assert bool(strat.post_filter(row, _ctx(b, h4, D=D, last_exit=None))["signal"])
    # sinyal olmayan satira dokunulmaz
    off = world["sig"].iloc[0]
    out = strat.post_filter(off, _ctx(b, h4, D=D, last_exit=(D - timedelta(hours=1), "stop")))
    assert out["reasons"] == off["reasons"]


# ------------------------------------------------------------------ H-7
def test_h7_validate_params_and_info():
    strat = M.make_v1b_4h()
    ok = strat.validate_params(dict(PARAMS))
    assert ok is not None
    for bad in ("15m", "4h"):
        with pytest.raises(ValueError):
            strat.validate_params({**PARAMS, "trigger_tf": bad})
    assert strat.info.paper_allowed is False
    i = strat.info
    assert (i.name, i.version, i.setups) == ("price_action_v1_4h", "s2-1.0", ("T1",))
    assert i.timeframes == ("trigger", "4h") and i.allowed_trigger_tfs == ("1h",)
    from trader_engine.strategies import price_action_v1 as P1
    assert i.param_specs == P1._param_specs()
    assert strat.label() == "strategy:price_action_v1_4h@s2-1.0"
    assert isinstance(strat, M.PriceActionV1H4)


# ------------------------------------------------------------------ cikis yardimcilari
T0 = datetime(2022, 3, 1, 0, 0, tzinfo=UTC)


def _pos(side="long", entry=100.0, stop=98.0, current=None, trail_atr=3.0, **kw) -> Position:
    d = dict(trade_id=1, bot="learner", pair="BTC/USDT", side=side, setup="T1", status="open", decision_id=1,
             signal_bar_close_ts=T0, entry_ts=T0 + timedelta(minutes=1), entry_bar_open=T0, entry_price=entry,
             qty=1.0, leverage=3, initial_stop=stop, current_stop=stop if current is None else current, stop_seq=0,
             stop_client_id=None, planned_target=None, trail_atr=trail_atr, param_version_id=1, trigger_tf="1h",
             risk_amount=10.0, margin=100.0, rh=None, rl=None, fee_entry=0.0, funding_paid=0.0, mfe_price=entry,
             mae_price=entry, exit_reason=None, exit_client_id=None, closed_ts=None)
    d.update(kw)
    return Position(**d)


def _xctx(highs, lows, atrs, regime=None, last_close=100.0, n=None) -> ExitContext:
    return ExitContext(bar_close_ts=T0 + timedelta(hours=len(highs)), highs=np.array(highs, float),
                       lows=np.array(lows, float), atrs=np.array(atrs, float), regime_last=regime,
                       last_close=last_close, n_closed=len(highs) if n is None else n)


def _group(highs, lows, atrs):
    """Elle toplama (bagimsiz): atrs'i sonlu her satirda grup kapanir; NaN high/low atlanir."""
    gh, gl, ga = [], [], []
    hh, ll = -np.inf, np.inf
    for h, l, a in zip(highs, lows, atrs):
        if not np.isnan(h):
            hh = max(hh, h)
        if not np.isnan(l):
            ll = min(ll, l)
        if not np.isnan(a):
            gh.append(hh), gl.append(ll), ga.append(a)
            hh, ll = -np.inf, np.inf
    return gh, gl, ga


def _same_decision(a: ExitDecision, b: ExitDecision):
    assert a.kind == b.kind and a.reason == b.reason
    assert (a.new_stop is None) == (b.new_stop is None)
    if a.new_stop is not None:
        assert a.new_stop == pytest.approx(b.new_stop)
    assert a.planned_exit == b.planned_exit


# ------------------------------------------------------------------ H-8
def test_h8_non_h4_close_and_none_ctx():
    pol = M.make_v1b_4h().exit_policy()
    assert isinstance(pol, M.H4ExitPolicy)
    nan = np.nan
    d = pol.evaluate(_pos(), _xctx([101, 102], [99, 100], [nan, nan]))
    assert d.kind == "none"
    d = pol.evaluate(_pos(), _xctx([101, 102, 110], [99, 100, 105], [1.0, 1.0, nan], regime="trend_down"))
    assert d.kind == "none"                                  # atrs[-1] NaN: rejim donusu bile degerlendirilmez
    d = pol.evaluate(_pos(), _xctx([], [], []))
    assert d.kind == "none"
    d = pol.evaluate(_pos(), None)
    assert (d.kind, d.reason) == ("exit", "force_exit")
    _same_decision(d, evaluate_exit(_pos(), None))


# ------------------------------------------------------------------ H-9
NAN = np.nan
H12 = [101, 103, 104, 105,   106, 108, 107, 109,   110, 111, 112, 111]
L12 = [99,  100, 101, 102,   103, 104, 105, 106,   107, 108, 109, 108]
A12 = [NAN, NAN, NAN, 1.0,   NAN, NAN, NAN, 1.2,   NAN, NAN, NAN, 1.0]


def test_h9_equivalence_stop_update():
    pol = M.make_v1b_4h().exit_policy()
    pos = _pos()
    ctx = _xctx(H12, L12, A12, regime="trend_up", last_close=111.0)
    got = pol.evaluate(pos, ctx)
    gh, gl, ga = _group(H12, L12, A12)
    assert (gh, gl, ga) == ([105, 109, 112], [99, 103, 107], [1.0, 1.2, 1.0])
    exp = evaluate_exit(pos, _xctx(gh, gl, ga, regime="trend_up", last_close=111.0))
    _same_decision(got, exp)
    assert got.kind == "stop_update" and got.new_stop == pytest.approx(112 - 3.0 * 1.0)      # = 109
    # 1 saatlik satirlarla dogrudan degerlendirme farkli olurdu (grup ATR'si NaN satirlar iz surmez): sabitleme
    assert got.new_stop == pytest.approx(109.0)


def test_h9_trail_stop_exit_when_close_crossed():
    pol = M.make_v1b_4h().exit_policy()
    pos = _pos()
    ctx = _xctx(H12, L12, A12, regime="trend_up", last_close=108.5)       # iz 109 >= 108.5
    got = pol.evaluate(pos, ctx)
    assert (got.kind, got.reason) == ("exit", "trail_stop")
    gh, gl, ga = _group(H12, L12, A12)
    _same_decision(got, evaluate_exit(pos, _xctx(gh, gl, ga, regime="trend_up", last_close=108.5)))


def test_h9_regime_flip_exit_and_short_mirror():
    pol = M.make_v1b_4h().exit_policy()
    got = pol.evaluate(_pos(), _xctx(H12, L12, A12, regime="trend_down", last_close=111.0))
    assert (got.kind, got.reason) == ("exit", "regime_flip")
    gh, gl, ga = _group(H12, L12, A12)
    _same_decision(got, evaluate_exit(_pos(), _xctx(gh, gl, ga, regime="trend_down", last_close=111.0)))
    # short ayna
    hs = [100 - (x - 100) for x in L12]
    ls = [100 - (x - 100) for x in H12]
    ps = _pos(side="short", entry=100.0, stop=102.0)
    got = pol.evaluate(ps, _xctx(hs, ls, A12, regime="trend_down", last_close=89.0))
    gh, gl, ga = _group(hs, ls, A12)
    exp = evaluate_exit(ps, _xctx(gh, gl, ga, regime="trend_down", last_close=89.0))
    _same_decision(got, exp)
    assert got.kind == "stop_update" and got.new_stop == pytest.approx(88 + 3.0 * 1.0)
    got = pol.evaluate(ps, _xctx(hs, ls, A12, regime="trend_up", last_close=89.0))
    assert (got.kind, got.reason) == ("exit", "regime_flip")


def test_h9_no_loosening_and_not_armed():
    pol = M.make_v1b_4h().exit_policy()
    # mevcut stop zaten daha siki: guncelleme yok
    got = pol.evaluate(_pos(current=111.0), _xctx(H12, L12, A12, regime="trend_up", last_close=112.0))
    assert got.kind == "none"
    # fiyat 1R'ye ulasmadi (high < 102): iz silahlanmaz
    got = pol.evaluate(_pos(), _xctx([100.5, 100.8, 101, 101.2], [99.5, 99.6, 99.8, 100], [NAN, NAN, NAN, 1.0],
                                    regime="range", last_close=101.0))
    assert got.kind == "none"


def test_h9_nan_highs_lows_skipped():
    pol = M.make_v1b_4h().exit_policy()
    h = [101, NAN, 104, 105,   106, 108, NAN, 109]
    l = [99, 100, NAN, 102,    103, NAN, 105, 106]
    a = [NAN, NAN, NAN, 1.0,   NAN, NAN, NAN, 1.2]
    got = pol.evaluate(_pos(), _xctx(h, l, a, regime="trend_up", last_close=109.0))
    gh, gl, ga = _group(h, l, a)
    assert gh == [105, 109]
    _same_decision(got, evaluate_exit(_pos(), _xctx(gh, gl, ga, regime="trend_up", last_close=109.0)))
    assert got.new_stop == pytest.approx(109 - 3.0 * 1.2)


# ------------------------------------------------------------------ H-10
def test_h10_partial_first_group():
    """Giris D+2s: ilk grup 2 satir (kapanis 2. satirda), sonra tam gruplar."""
    pol = M.make_v1b_4h().exit_policy()
    h = [103, 105,   106, 107, 108, 109,   110, 112, 111, 111]
    l = [100, 101,   102, 104, 105, 106,   107, 108, 109, 108]
    a = [NAN, 1.0,   NAN, NAN, NAN, 1.1,   NAN, NAN, NAN, 1.0]
    ctx = _xctx(h, l, a, regime="trend_up", last_close=111.0)
    got = pol.evaluate(_pos(), ctx)
    gh, gl, ga = _group(h, l, a)
    assert (gh, gl, ga) == ([105, 109, 112], [100, 102, 107], [1.0, 1.1, 1.0])
    _same_decision(got, evaluate_exit(_pos(), _xctx(gh, gl, ga, regime="trend_up", last_close=111.0)))
    assert got.kind == "stop_update" and got.new_stop == pytest.approx(112 - 3.0 * 1.0)
    # yalniz ilk (eksik) grup: kapanista ATR 1.0, high 105 -> iz = 105 - 3
    got1 = pol.evaluate(_pos(), _xctx(h[:2], l[:2], a[:2], regime="trend_up", last_close=104.0))
    assert got1.kind == "stop_update" and got1.new_stop == pytest.approx(102.0)


def test_h10_missing_hourly_row_groups_close_on_finite_atr():
    """Aradaki 1 saatlik satir eksik (dizi kisa): grup yine atrs'in sonlu oldugu satirda kapanir."""
    pol = M.make_v1b_4h().exit_policy()
    h = [101, 104, 105,   106, 108, 107, 109]           # ilk grup 3 satir (biri eksik)
    l = [99, 101, 102,    103, 104, 105, 106]
    a = [NAN, NAN, 1.0,   NAN, NAN, NAN, 1.2]
    got = pol.evaluate(_pos(), _xctx(h, l, a, regime="trend_up", last_close=109.0))
    gh, gl, ga = _group(h, l, a)
    assert (gh, gl, ga) == ([105, 109], [99, 103], [1.0, 1.2])
    _same_decision(got, evaluate_exit(_pos(), _xctx(gh, gl, ga, regime="trend_up", last_close=109.0)))
    assert got.new_stop == pytest.approx(109 - 3.0 * 1.2)


def test_h10_n_closed_is_group_count():
    """n_closed = grup sayisi: R1 olmayan T1 yolunda sonuc, ctx.n_closed 1 saatlik sayidan bagimsizdir."""
    pol = M.make_v1b_4h().exit_policy()
    a = _xctx(H12, L12, A12, regime="trend_up", last_close=111.0, n=12)
    b = _xctx(H12, L12, A12, regime="trend_up", last_close=111.0, n=3)
    _same_decision(pol.evaluate(_pos(), a), pol.evaluate(_pos(), b))
    # n_closed == 0 ama atrs dolu degil -> none (grup yok)
    assert pol.evaluate(_pos(), _xctx([101], [99], [NAN], n=0)).kind == "none"


# ------------------------------------------------------------------ H-11 (uctan uca)
pa = pytest.importorskip("pyarrow")
import pyarrow.feather as pf  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PAIRS = ("BTC/USDT", "ETH/USDT")
BASE = ["--period", "20250301-20250320", "--tf", "1h", "--fill-model", "legacy_compat", "--granularity", "15m",
        "--synthetic-rules", "--no-record-filtered"]


def _wf(path: Path, dates: pd.DatetimeIndex, cols: dict) -> None:
    arrs = {"date": pa.array(dates.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
    for k, v in cols.items():
        arrs[k] = pa.array(np.asarray(v, dtype="float64"))
    pf.write_feather(pa.table(arrs), str(path), compression="uncompressed")


def _history(hist: Path) -> None:
    hist.mkdir(parents=True)
    idx = pd.date_range("2025-01-01", "2025-03-25", freq="15min", tz="UTC", inclusive="left")
    for k, pair in enumerate(PAIRS):
        rng = np.random.default_rng(31 + k)
        d = np.where((np.arange(len(idx)) // 1200) % 2 == 0, 0.00018, -0.00018)
        close = np.round(100.0 * (1 + 0.3 * k) * np.exp(np.cumsum(rng.normal(d, 0.0025))), 2)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0012, len(idx)))), 2)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0012, len(idx)))), 2)
        df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": rng.uniform(100, 500, len(idx))},
                          index=idx)
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        for tf, rule in (("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
            g = df if tf == "15m" else pd.DataFrame(
                {"open": df.resample(rule)["open"].first(), "high": df.resample(rule)["high"].max(),
                 "low": df.resample(rule)["low"].min(), "close": df.resample(rule)["close"].last(),
                 "volume": df.resample(rule)["volume"].sum()}).dropna()
            _wf(hist / f"{stem}-{tf}-futures.feather", g.index, g.to_dict("list"))
        fidx = pd.date_range("2025-01-01", "2025-03-25", freq="8h", tz="UTC", inclusive="left")
        _wf(hist / f"{stem}-1h-funding_rate.feather", fidx, {"funding_rate": [0.0001] * len(fidx)})


@pytest.fixture
def ws(tmp_path, monkeypatch):
    hist = tmp_path / "hist"
    _history(hist)
    (tmp_path / "config").mkdir()
    cfg = json.loads((REPO / "config" / "engine.base.json").read_text())
    cfg.update(pairs=list(PAIRS), history_dir=str(hist), var_dir=str(tmp_path / "var"),
               market_db=str(tmp_path / "var" / "market.sqlite"), kill_file=str(tmp_path / "KILL"))
    (tmp_path / "config" / "engine.base.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(REG._FACTORIES, "price_action_v1_4h", M.make_v1b_4h)
    return tmp_path


def _entry_signal_closes(run_dir: Path) -> list[pd.Timestamp]:
    """ledger.sqlite decision_events: girise donusen kararlarin bar_close_ts degerleri (= signal_bar_close_ts)."""
    con = sqlite3.connect(run_dir / "ledger.sqlite")
    try:
        rows = con.execute("select bar_close_ts, trigger_tf from decision_events where final_action='entered'").fetchall()
    finally:
        con.close()
    assert all(tf == "1h" for _, tf in rows)                 # defterde motor adim araligi 1h (§5 Kod)
    return [pd.Timestamp(t) for t, _ in rows]


def test_h11_end_to_end_smoke(ws):
    from trader_engine import backtest as B
    assert int(B.main(["--id", "h4a", "--strategy", "price_action_v1_4h", *BASE]) or 0) == 0
    run = ws / "var/backtests/h4a"
    meta = json.loads((run / "meta.json").read_text())
    assert meta["strategy"] == "price_action_v1_4h"
    assert meta["strategy_label"] == "strategy:price_action_v1_4h@s2-1.0"
    closes = _entry_signal_closes(run)
    assert len(closes) > 0, "sentetik gecmis hic giris uretmedi; fikstur guclendirilmeli"
    assert all(t.hour % 4 == 0 and t.minute == 0 for t in closes), closes[:5]
    trades = pd.read_csv(run / "trades.csv")
    assert 0 < len(trades) <= len(closes)


# ------------------------------------------------------------------ H-12
def test_h12_static_registry_unchanged():
    assert REG.list_strategies() == ("price_action_v1", "price_action_v1_full", "price_action_lab_ml")
    assert "price_action_v1_4h" not in REG._FACTORIES
    with pytest.raises(StrategyError) as e:
        REG.get_strategy("price_action_v1_4h")
    assert e.value.code == "unknown_strategy"


def test_h12_registered_at_runtime_only(monkeypatch):
    monkeypatch.setitem(REG._FACTORIES, "price_action_v1_4h", M.make_v1b_4h)
    s = REG.get_strategy("price_action_v1_4h")
    assert s.info.name == "price_action_v1_4h"
    with pytest.raises(StrategyError) as e:
        REG.get_strategy("price_action_v1_4h", mode="paper")
    assert e.value.code == "paper_not_allowed"
    monkeypatch.undo()
    assert REG.list_strategies() == ("price_action_v1", "price_action_v1_full", "price_action_lab_ml")
