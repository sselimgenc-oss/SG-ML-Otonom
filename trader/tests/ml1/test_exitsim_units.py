"""ML1 izole cikis simulatoru: sentetik birim durumlari (stop once, bosluk, basa-bas, kismi, zaman stopu, iz, ufuk, short aynasi, maliyet/R)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader_core import exit_counterfactual as EC
from trader_core import exit_modes as XM
from trader_core import risk
from trader_core import signals as S
from trader_ml.ml1 import costs as C
from trader_ml.ml1 import exitsim as X

T0 = pd.Timestamp("2025-01-06 00:00", tz="UTC")          # Pazartesi, 15m/1h/4h/1d sinirinda
H = pd.Timedelta(hours=1)
E = 4                                                      # karar D = T0 + 1h -> giris mumu dizini 4
ZERO = X.SimConfig(cost=C.CostConfig(taker_fee=0.0, base=C.Slips(0.0, 0.0, 0.0)), cfg_modes={})
REAL = X.SimConfig(cost=C.CostConfig(taker_fee=0.0005, base=C.Slips(2.0, 2.0, 5.0)), cfg_modes={})


def ms(i: int) -> int:
    return int((T0 + pd.Timedelta(minutes=15 * i)).value // 1_000_000)


def mk15(n: int, specs: dict[int, tuple], base: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(T0, periods=n, freq="15min")
    o = np.full(n, base)
    h = np.full(n, base)
    l = np.full(n, base)
    c = np.full(n, base)
    for i, (a, b, d, e) in specs.items():
        o[i], h[i], l[i], c[i] = a, b, d, e
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)


def mktf(b15: pd.DataFrame, tf: str = "1h", atr: float = 1.0, regime=None) -> pd.DataFrame:
    rule = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}[tf]
    g = b15.resample(rule)
    df = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})
    df["atr_tf"] = atr
    df["regime"] = regime
    return df


def mirror(specs: dict) -> dict:
    return {i: (200 - o, 200 - l, 200 - h, 200 - c) for i, (o, h, l, c) in specs.items()}


def run(specs, *, setup="R1", side="long", entry=100.0, stop=98.0, target=106.0, modes=None, n=400, cfg=ZERO, atr=1.0, regime=None,
        funding=None, tf="1h", **extra):
    b15 = mk15(n, specs)
    tfb = mktf(b15, tf, atr, regime)
    cand = dict(decision_ts=T0 + H, pair="BTC/USDT", tf=tf, setup=setup, side=side, entry_ref=entry, stop=stop, target=target,
                exit_modes=modes, **extra)
    return X.simulate_rows([cand], b15, tfb, funding, cfg=cfg)[0]


# --------------------------------------------------------------------------------------------------------- stop / hedef / bosluk
def test_stop_first_on_same_bar():
    r = run({5: (100, 107, 97, 100)})                      # ayni mumda hem hedef (106) hem stop (98) degdi
    assert r["status"] == "ok" and r["exit_reason"] == "stop" and r["exit_px"] == 98.0
    assert r["exit_ts"] == ms(5) and r["entry_ts"] == ms(E) and r["censored"] == 0
    assert r["gross_R"] == pytest.approx(-2.0 / risk.loss_at_stop(1.0, 100.0, 98.0, risk.LOCKED_CFG))


def test_gap_through_stop_fills_at_open():
    r = run({5: (95, 96, 94, 95)})
    assert r["exit_reason"] == "stop" and r["exit_px"] == 95.0                 # stop 98 asildi: dolum acilista
    assert r["net_R"] < -2.0 / 2.2


def test_target_hit_and_gap_through_target():
    r = run({5: (100, 106.5, 100, 106)})
    assert r["exit_reason"] == "target" and r["exit_px"] == 106.0
    r = run({5: (108, 109, 107, 108)})                                         # acilis hedefi asmis: dolum acilista (min(open, high))
    assert r["exit_reason"] == "target" and r["exit_px"] == 108.0


def test_invalid_stop_side_and_unknown_bar():
    assert run({}, stop=101.0)["status"] == "invalid"
    b15 = mk15(50, {})
    cand = dict(decision_ts=T0 - H, pair="BTC/USDT", tf="1h", setup="R1", side="long", entry_ref=100.0, stop=98.0, target=106.0)
    assert X.simulate_rows([cand], b15, mktf(b15), cfg=ZERO)[0]["status"] == "no_data"


# --------------------------------------------------------------------------------------------------------- basa-bas / kismi
BE = XM.ExitModes(be_trigger_r=1.0, be_offset_bps=15.0)
PT = XM.ExitModes(pt_trigger_r=1.5, pt_frac=0.5)


def test_breakeven_then_stop_out_near_zero_r():
    specs = {5: (100, 103, 100, 103), 6: (103, 103, 100.1, 100.5)}
    r = run(specs, modes=BE, cfg=REAL)
    assert r["exit_reason"] == "trail_stop" and r["be_moved"] == 1 and r["exit_ts"] == ms(6)
    fill = 100.0 * 1.0002
    assert r["exit_px"] == pytest.approx(fill * 1.0015 * (1 - 0.0005))        # BE seviyesi (+15 bps) + stop kaymasi
    assert abs(r["net_R"]) < 0.15                                             # ~0 R
    z = run(specs, modes=BE)
    assert z["exit_px"] == pytest.approx(100.15) and z["net_R"] == pytest.approx(0.15 / z["r_unit"])


def test_breakeven_would_trigger_exits_at_next_open():
    r = run({5: (100, 103, 100, 100.1), 6: (100.0, 100.5, 99.9, 100.2)}, modes=BE)   # BE 100,15 > kapanis 100,1: stop zaten asilmis
    assert r["exit_reason"] == "trail_stop" and r["exit_ts"] == ms(6) and r["exit_px"] == 100.0


def test_partial_then_target():
    r = run({5: (100, 103, 100, 103), 6: (103, 103, 103, 103), 7: (103, 106.5, 103, 106)}, modes=PT)
    assert r["partial_frac"] == 0.5 and r["partial_ts"] == ms(6) and r["partial_px"] == 103.0
    assert r["exit_reason"] == "target" and r["exit_px_last"] == 106.0 and r["exit_px"] == pytest.approx(104.5)
    assert r["net_R"] == pytest.approx(4.5 / r["r_unit"])


def test_partial_fires_once_and_be_independent():
    hold = {i: (103.5, 103.5, 103.5, 103.5) for i in range(8, 13)}
    r = run({5: (100, 103, 100, 103), 6: (103, 103, 103, 103), 7: (103, 104, 103, 103.5), **hold}, modes=XM.ExitModes(1.0, 15.0, 1.5, 0.5),
            time_stop=2)
    assert r["partial_frac"] == 0.5 and r["be_moved"] == 1                      # ikisi acik; kismi tek kez
    assert r["exit_reason"] == "time_stop" and r["exit_ts"] == ms(12)


# --------------------------------------------------------------------------------------------------------- zaman stopu / iz / rejim / kural
def test_time_stop_exits_at_next_open_after_nth_own_close():
    r = run({}, target=200.0, time_stop=3)
    assert r["exit_reason"] == "time_stop" and r["exit_ts"] == ms(16) and r["exit_px"] == 100.0
    assert r["bars_held"] == 12


def test_time_stop_default_from_registry():
    r = run({}, target=200.0)                                                  # R1: 48 mum
    assert r["exit_reason"] == "time_stop" and r["exit_ts"] == ms(E + 48 * 4)


def test_trail_arms_then_hit():
    specs = {5: (100, 103, 100, 101), 6: (101, 101, 101, 101), 7: (101, 101, 101, 101), 8: (101, 101, 101, 101), 9: (101, 101, 99.5, 100.2)}
    r = run(specs, setup="T1")
    assert r["exit_reason"] == "trail_stop" and r["exit_px"] == 100.0 and r["exit_ts"] == ms(9)   # 103 - 3 x ATR(1) = 100


def test_trail_close_crossed_exits_next_open():
    specs = {5: (100, 103, 99.5, 99.9), 6: (99.9, 99.9, 99.9, 99.9), 7: (99.9, 99.9, 99.9, 99.9), 8: (99.7, 99.8, 99.7, 99.7)}
    r = run(specs, setup="T1")                                                 # iz stopu 100 >= kapanis 99,9 -> piyasa cikisi
    assert r["exit_reason"] == "trail_stop" and r["exit_ts"] == ms(8) and r["exit_px"] == 99.7


def test_regime_flip_exit_only_at_own_close():
    b15 = mk15(400, {})
    tfb = mktf(b15, atr=1.0, regime=None)
    tfb["regime"] = "trend_down"                                               # long icin dondurme
    cand = dict(decision_ts=T0 + H, pair="BTC/USDT", tf="1h", setup="T1", side="long", entry_ref=100.0, stop=98.0, exit_modes=None)
    r = X.simulate_rows([cand], b15, tfb, cfg=ZERO)[0]
    assert r["exit_reason"] == "regime_flip" and r["exit_ts"] == ms(8)
    assert S.regime_flip_exit("long", "trend_down")


def test_rule_exit_only_at_given_close():
    close = int((T0 + 3 * H).value // 1_000_000)
    r = run({}, target=200.0, rule_exit_ts=[close])
    assert r["exit_reason"] == "other" and r["exit_ts"] == ms(12)


# --------------------------------------------------------------------------------------------------------- ufuk / veri sonu
def test_horizon_cap_is_censored():
    cfg = X.SimConfig(cost=ZERO.cost, cfg_modes={}, horizon_days=1)
    r = run({}, setup="T1", cfg=cfg)
    assert r["exit_reason"] == "horizon" and r["censored"] == 1 and r["status"] == "ok"
    assert r["exit_ts"] == ms(E + 96)                                          # son 15 dk mumunun kapanisi (giris + 24 sa)
    assert r["exit_px"] == 100.0


def test_data_end_leaves_candidate_open():
    r = run({}, setup="T1", n=60)
    assert r["status"] == "open" and r["exit_ts"] is None and r["exit_reason"] == "open" and r["censored"] == 1
    assert np.isnan(r["net_R"])


def test_data_gap_flag():
    b15 = mk15(100, {})
    b15 = b15.drop(b15.index[30:40])
    cand = dict(decision_ts=T0 + H, pair="BTC/USDT", tf="1h", setup="T1", side="long", entry_ref=100.0, stop=98.0)
    r = X.simulate_rows([cand], b15, mktf(mk15(100, {})), cfg=ZERO)[0]
    assert r["status"] == "data_gap" and r["censored"] == 1


# --------------------------------------------------------------------------------------------------------- short aynasi
@pytest.mark.parametrize("specs,modes,kw", [
    ({5: (100, 107, 97, 100)}, None, {}),
    ({5: (95, 96, 94, 95)}, None, {}),
    ({5: (100, 103, 100, 103), 6: (103, 103, 100.1, 100.5)}, BE, {}),
    ({5: (100, 103, 100, 103), 6: (103, 103, 103, 103), 7: (103, 106.5, 103, 106)}, PT, {}),
    ({5: (100, 103, 100, 101), 6: (101, 101, 101, 101), 7: (101, 101, 101, 101), 8: (101, 101, 101, 101), 9: (101, 101, 99.5, 100.2)},
     None, {"setup": "T1"}),
])
def test_short_mirrors_long(specs, modes, kw):
    lg = run(specs, modes=modes, **kw)
    sh = run(mirror(specs), side="short", stop=102.0, target=94.0, modes=modes, **kw)
    assert sh["exit_reason"] == lg["exit_reason"] and sh["exit_ts"] == lg["exit_ts"]
    assert sh["exit_px"] == pytest.approx(200.0 - lg["exit_px"])
    assert sh["gross_R"] == pytest.approx(lg["gross_R"] * (lg["r_unit"] / sh["r_unit"]))


# --------------------------------------------------------------------------------------------------------- maliyet / R birimi / funding
def test_r_unit_matches_ledger_formula():
    cfg = C.load_cost_config()
    for e, s in ((100.0, 98.0), (30000.0, 29500.0), (100.0, 103.0)):
        assert cfg.r_unit(e, s) == pytest.approx(risk.loss_at_stop(1.0, e, s, risk.LOCKED_CFG))
    assert cfg.r_unit(100.0, 98.0) == pytest.approx(2.0 + 198.0 * 0.001)


def test_net_r_equals_ledger_realized_over_planned_risk():
    r = run({5: (100, 100.5, 97, 98)}, cfg=REAL)                              # stop 98 vurulur (kayma 5 bps)
    fill, xp = 100.0 * 1.0002, 98.0 * (1 - 0.0005)
    assert r["entry_px"] == pytest.approx(fill) and r["exit_px"] == pytest.approx(xp)
    gross = xp - fill
    fees = 0.0005 * (fill + xp)
    planned = risk.loss_at_stop(1.0, 100.0, 98.0, risk.LOCKED_CFG)
    assert r["net_R"] == pytest.approx((gross - fees) / planned)              # ledger: realized / planned_risk
    assert r["fee"] == pytest.approx(fees) and r["gross_R"] == pytest.approx(gross / planned)


def test_cost_overrides_per_pair_and_session():
    cfg = C.load_cost_config()
    assert cfg.slips("BTC/USDT", 0) == cfg.base
    open_ = int(pd.Timestamp("2025-01-07 15:00", tz="UTC").value // 1_000_000)
    closed = int(pd.Timestamp("2025-01-07 22:00", tz="UTC").value // 1_000_000)
    wknd = int(pd.Timestamp("2025-01-11 12:00", tz="UTC").value // 1_000_000)
    assert cfg.slips("NVDA/USDT", open_) == C.Slips(4.0, 4.0, 10.0)
    assert cfg.slips("NVDA/USDT", closed) == C.Slips(6.0, 6.0, 15.0)
    assert cfg.slips("NVDA/USDT", wknd) == C.Slips(8.0, 8.0, 20.0)
    assert cfg.taker_fee == 0.0005 and cfg.base == C.Slips(2.0, 2.0, 5.0)


def test_exit_modes_resolution_from_config():
    cfg = X.load_sim_config()
    m = XM.resolve(cfg.cfg_modes, "T1", "1h")
    assert m.breakeven and m.partial and m.pt_trigger_r == XM.PT_TRIGGER_R
    y = XM.resolve(cfg.cfg_modes, "H2-YARI", "1h")          # 26.11: H2-YARI config'ten kaldirildi -> varsayilan kip
    assert y.pt_trigger_r == XM.PT_TRIGGER_R


def test_funding_window_and_sign():
    fidx = pd.DatetimeIndex([T0 + H, T0 + 2 * H, T0 + 4 * H, T0 + 5 * H])     # giris ani haric, cikis ani dahil, sonrasi haric
    f = pd.DataFrame({"funding_rate": 0.001, "mark": 100.0}, index=fidx)
    lg = run({}, target=200.0, time_stop=3, funding=f)
    assert lg["funding"] == pytest.approx(2 * EC.funding_payment("long", 1.0, 100.0, 0.001))
    sh = run({}, side="short", stop=102.0, target=10.0, time_stop=3, funding=f)
    assert sh["funding"] == pytest.approx(2 * EC.funding_payment("short", 1.0, 100.0, 0.001)) and sh["funding"] < 0
    assert lg["net_R"] == pytest.approx((0.0 - lg["fee"] - lg["funding"]) / lg["r_unit"])


def test_funding_mark_falls_back_to_bar_open():
    f = pd.DataFrame({"funding_rate": [0.002]}, index=pd.DatetimeIndex([T0 + 2 * H]))
    r = run({}, target=200.0, time_stop=3, funding=f)
    assert r["funding"] == pytest.approx(100.0 * 0.002)


def test_partial_funding_is_weighted_by_quantity():
    f = pd.DataFrame({"funding_rate": 0.001, "mark": 100.0}, index=pd.DatetimeIndex([T0 + 5 * H]))        # kismidan sonra
    specs = {5: (100, 103, 100, 103), 6: (103, 103, 103, 103)}
    r = run(specs, modes=PT, target=200.0, time_stop=8, funding=f)
    assert r["partial_frac"] == 0.5 and r["exit_reason"] == "time_stop"
    assert r["funding"] == pytest.approx(0.5 * 100.0 * 0.001)                                           # yalniz kalan yarim parca


# --------------------------------------------------------------------------------------------------------- saf islev esitlikleri
@pytest.mark.parametrize("side", ["long", "short"])
def test_trail_step_equals_trail_stop_path(side):
    rng = np.random.default_rng(3)
    n = 300
    hi = 100 + np.cumsum(rng.normal(0, 0.6, n)) + 0.4
    lo = hi - np.abs(rng.normal(0.5, 0.2, n))
    atr = np.abs(rng.normal(1.0, 0.3, n))
    atr[5] = np.nan
    if side == "short":
        hi, lo = 200 - lo, 200 - hi
    fill, init = 100.0, (97.0 if side == "long" else 103.0)
    path = S.trail_stop_path(side, fill, init, hi, lo, atr, 3.0).to_numpy()
    long = side == "long"
    cur, ext = init, (-np.inf if long else np.inf)
    risk_px = abs(fill - init)
    for k in range(n):
        ext = max(ext, hi[k]) if long else min(ext, lo[k])
        cur = X.trail_step(long, cur, ext, fill, risk_px, float(atr[k]), 3.0)
        assert cur == path[k], k


def test_be_pt_thresholds_equal_exit_modes_reached_r():
    rng = np.random.default_rng(1)
    for _ in range(500):
        fill = float(rng.uniform(50, 150))
        stop = fill - float(rng.uniform(0.5, 5))
        best = fill + float(rng.uniform(-2, 12))
        trig = float(rng.choice([0.5, 1.0, 1.5, 2.0]))
        thr = fill + trig * abs(fill - stop) - XM.EPS
        assert (best >= thr) == XM.reached_r("long", fill, stop, best, trig)
        thr_s = fill - trig * abs(fill - stop) + XM.EPS
        assert (best <= thr_s) == XM.reached_r("short", fill, fill + abs(fill - stop), best, trig)


def test_batch_api_dataframe_rows_and_to_frame():
    b15 = mk15(400, {5: (100, 107, 97, 100)})
    rows = pd.DataFrame([dict(decision_ts=T0 + H, pair="BTC/USDT", tf="1h", setup="R1", side="long", entry_ref=100.0, stop=98.0, target=106.0),
                         dict(decision_ts=T0 + 2 * H, pair="BTC/USDT", tf="1h", setup="R1", side="short", entry_ref=100.0, stop=102.0, target=94.0)])
    res = X.simulate_rows(rows, b15, {"1h": mktf(b15)}, cfg=ZERO)
    df = X.to_frame(res)
    assert list(df["exit_reason"]) == ["stop", "time_stop"]
    assert str(df["entry_ts"].dt.tz) == "UTC" and len(df) == 2


def test_horizon_never_cuts_before_time_stop_1d_arm():
    n = 4 + 96 * 60
    b15 = mk15(n, {})
    tfb = mktf(b15, "1d")
    cand = dict(decision_ts=T0 + pd.Timedelta(days=1), pair="BTC/USDT", tf="1d", setup="R1", side="long", entry_ref=100.0, stop=98.0,
                target=200.0, exit_modes=None, time_stop=48)
    r = X.simulate_rows([cand], b15, tfb, cfg=ZERO)[0]                          # 48 gun > 30 gun ufku
    assert r["exit_reason"] == "time_stop" and r["censored"] == 0
    assert r["exit_ts"] == int((T0 + pd.Timedelta(days=49)).value // 1_000_000)
