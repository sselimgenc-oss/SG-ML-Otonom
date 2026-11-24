"""research/arm_harness.py: yalniz sentetik barlar (tmp_path); gercek veri okunmaz."""
from __future__ import annotations

import importlib.util
import json
import math
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import counterfactual as CF
from trader_core import signals as S
from trader_engine.holdout import HOLDOUT

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("arm_harness", ROOT / "research" / "arm_harness.py")
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)


def _walk(n=600, seed=0, start="2022-01-01", freq="4h", drift=0.0, vol=0.01):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    c = 100.0 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    o = np.concatenate(([100.0], c[:-1]))
    hi = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": 1.0}, index=idx)


def _bars(df, tf="4h", regime=None):
    return H.Bars(df, np.full(len(df), "range", dtype=object) if regime is None else regime, tf)


# ------------------------------------------------------------------------------------------ iz suren stop paritesi
@pytest.mark.parametrize("sgn,side", [(1.0, "long"), (-1.0, "short")])
def test_trail_update_matches_signals_trail_stop_path(sgn, side):
    df = _walk(400, seed=3, drift=0.002 * sgn)
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    atr = np.full(len(df), 1.2)
    atr[:5] = np.nan
    fill = float(df["open"].iloc[0])
    init = fill - sgn * 2.0
    ref = S.trail_stop_path(side, fill, init, h, l, atr, 3.0).to_numpy()
    R = abs(fill - init)
    cur, ext, got = init, (-math.inf if sgn > 0 else math.inf), []
    for k in range(len(h)):
        ext = max(ext, h[k]) if sgn > 0 else min(ext, l[k])
        cur = H.trail_update(sgn, cur, ext, fill, R, atr[k], 3.0)
        got.append(cur)
    assert np.allclose(got, ref)
    assert (np.diff(np.array(got)) * sgn >= -1e-12).all()                # monoton


# ------------------------------------------------------------------------------------------ simulator
def test_target_mode_matches_counterfactual_replay_without_costs():
    df = _walk(900, seed=5, vol=0.004)
    b = _bars(df)
    rng = np.random.default_rng(7)
    checked = 0
    for t in range(30, 800, 17):
        sgn = 1.0 if rng.random() < 0.5 else -1.0
        e = t + 1
        entry = float(b.o[e])
        stop = entry - sgn * 0.012 * entry
        target = entry + sgn * 0.024 * entry
        res = H.simulate(b, [(t, sgn, stop, target)], "target", 0.0, 0.0, 3.0)
        ref = CF.replay(b.h[e:], b.l[e:], b.c[e:], "long" if sgn > 0 else "short", entry, stop, target, horizon=48, fee_rate=0.0, slippage_rate=0.0)
        assert ref is not None and len(res) == 1
        ts, r, why, _ = res[0]
        assert why == ref["exit_reason"] and r == pytest.approx(ref["r_gross"], abs=1e-9)
        checked += 1
    assert checked > 30


def _flat(n=10, p=100.0):
    idx = pd.date_range("2022-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p, "volume": 1.0}, index=idx)


def test_stop_first_when_both_hit_same_bar_and_costs_arithmetic():
    df = _flat()
    df.loc[df.index[3], ["high", "low"]] = [110.0, 90.0]                    # ayni barda hedef (105) ve stop (95) ikisi de
    b = _bars(df)
    res = H.simulate(b, [(1, 1.0, 95.0, 105.0)], "target", 0.0005, 5.0, 3.0)
    assert [x[2] for x in res] == ["stop"]
    fill = 100.0 * 1.0005
    xf = 95.0 * (1 - 0.0005)
    expect = ((xf - fill) - 0.0005 * (fill + xf)) / (fill - 95.0)
    assert res[0][1] == pytest.approx(expect)
    assert res[0][1] < -1.0                                                 # maliyet kaybi buyutur


def test_gap_through_stop_fills_at_open_and_unresolved_is_dropped():
    df = _flat()
    df.loc[df.index[4], ["open", "high", "low", "close"]] = [90.0, 91.0, 89.0, 90.0]
    b = _bars(df)
    res = H.simulate(b, [(1, 1.0, 95.0, float("nan"))], "target", 0.0, 0.0, 3.0)
    assert res[0][2] == "stop" and res[0][1] == pytest.approx((90.0 - 100.0) / 5.0)       # -2R (stop'tan kotu)
    assert H.simulate(_bars(_flat(6)), [(1, 1.0, 95.0, 105.0)], "target", 0.0, 0.0, 3.0) == []   # 48 mum dolmadi, bariyer yok


def test_one_position_at_a_time_and_no_same_bar_reentry():
    df = _flat(80)
    df.loc[df.index[5], "low"] = 94.0                                       # bar 5'te stop
    b = _bars(df)
    rows = [(1, 1.0, 95.0, 105.0), (3, 1.0, 95.0, 105.0), (5, 1.0, 95.0, 105.0), (6, 1.0, 95.0, 105.0)]
    res = H.simulate(b, rows, "target", 0.0, 0.0, 3.0)
    # t=1 giris bar 2, bar 5'te stop; t=3 acik pozisyon altinda; t=5 cikis barinda sinyal yok; t=6 yeni pozisyon (48 mum sonra zaman)
    assert [x[2] for x in res] == ["stop", "time"]


def test_trail_mode_arms_at_1r_and_exits_on_regime_flip():
    n = 40
    idx = pd.date_range("2022-01-01", periods=n, freq="4h", tz="UTC")
    c = np.concatenate(([100.0] * 3, np.linspace(100, 130, 20), np.full(n - 23, 130.0)))
    o = np.concatenate(([100.0], c[:-1]))
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.1, "low": np.minimum(o, c) - 0.1, "close": c, "volume": 1.0}, index=idx)
    reg = np.full(n, "trend_up", dtype=object)
    reg[30:] = "trend_down"
    b = _bars(df, regime=reg)
    res = H.simulate(b, [(1, 1.0, 95.0, float("nan"))], "trail", 0.0, 0.0, 3.0)
    assert len(res) == 1 and res[0][2] == "regime_flip" and res[0][1] > 1.0
    # rejim sabit ve fiyat duz: iz-stop silahlanir (1R) ama capraz yok; veri biter -> cozulmemis
    reg2 = np.full(n, "trend_up", dtype=object)
    assert H.simulate(_bars(df, regime=reg2), [(1, 1.0, 95.0, float("nan"))], "trail", 0.0, 0.0, 3.0) == []


# ------------------------------------------------------------------------------------------ veri / holdout
def _write_feather(d: Path, pair_stem: str, tf: str, df: pd.DataFrame):
    out = df.reset_index().rename(columns={"index": "date"})
    out["date"] = out["date"].astype("datetime64[ms, UTC]")
    out.to_feather(d / f"{pair_stem}-{tf}-futures.feather")


def test_load_pre_holdout_never_returns_locked_rows(tmp_path):
    start = pd.Timestamp(HOLDOUT[0]) - pd.Timedelta(days=60)
    df = _walk(60 * 6 + 6 * 40, seed=1, start=start)                         # kilit sinirini asar
    assert df.index[-1] >= pd.Timestamp(HOLDOUT[0])
    _write_feather(tmp_path, "BTC_USDT_USDT", "4h", df)
    got = H.load_pre_holdout(tmp_path, "BTC/USDT", "4h")
    assert len(got) and got.index[-1] < pd.Timestamp(HOLDOUT[0]) and got.index.is_monotonic_increasing
    assert H.load_pre_holdout(tmp_path, "ETH/USDT", "4h") is None


def test_day_grid_ends_before_holdout():
    d = H.day_grid()
    assert d[-1] + pd.Timedelta(days=1) <= pd.Timestamp(HOLDOUT[0])


# ------------------------------------------------------------------------------------------ izgara
def test_declared_grid_is_stable_and_counts_every_variant():
    g1, g2 = H.declared_grid(), H.declared_grid()
    assert g1 == g2 and H.grid_sha(g1) == H.grid_sha(g2)
    assert set(H.GRID) == {"T1", "R1", "TF1", "B1", "H2", "S1", "F1"}
    for s in H.GRID:
        v = H.variants(s)
        tags = [x["tag"] for x in v]
        assert tags[0] == "def" and len(tags) == len(set(tags)) and 5 <= len(tags) <= 8
    assert len(H.COSTS) == 4 and {c[0] for c in H.COSTS} == {1.0, 2.0} and {c[1] for c in H.COSTS} == {0.0, 5.0}


def test_patched_restores_module_constants():
    from trader_engine.strategies.arms import find_arm
    mod = find_arm("TF1")
    old = mod.BRK_ATR
    with H.patched(mod, {"BRK_ATR": 0.9}):
        assert mod.BRK_ATR == 0.9
    assert mod.BRK_ATR == old


def test_run_pair_on_synthetic_history(tmp_path, monkeypatch):
    start = pd.Timestamp(HOLDOUT[0]) - pd.Timedelta(days=700)
    df = _walk(4200, seed=11, start=start, vol=0.012, drift=0.0004)          # 4h, kilit sinirina kadar degil; load suzgeci uygular
    _write_feather(tmp_path, "BTC_USDT_USDT", "4h", df)
    monkeypatch.setitem(H.GRID, "TF1", {**H.GRID["TF1"], "tfs": ("4h",)})
    monkeypatch.setitem(H.GRID, "H2", {**H.GRID["H2"], "tfs": ("4h", "1d")})
    for setup in ("TF1", "H2"):
        r = H.run_pair((setup, "BTC/USDT", str(tmp_path)))
        ser = r["series"]
        nvar = len(H.variants(setup))
        tfs = H.GRID[setup]["tfs"]
        assert sum(1 for k in ser if not k.startswith("REF|")) == nvar * len(tfs) * len(H.COSTS)
        for k, (dns, rr, ntr) in ser.items():
            assert len(dns) == len(rr)
            if len(dns):
                assert pd.Timestamp(dns.max(), tz="UTC") < pd.Timestamp(HOLDOUT[0])
    r = H.run_pair(("TF1", "BTC/USDT", str(tmp_path)))
    assert sum(v[2] for v in r["series"].values()) > 0                        # sentetik trendli yuruyusle islem uretildi


# ------------------------------------------------------------------------------------------ M1 (egitim-disi donem)
def test_m1_oos_end_applies_embargo():
    ts = pd.Timestamp("2023-06-01 00:00", tz="UTC")
    from trader_core import pa_features as PF
    last = H.m1_oos_end(ts, "1h")
    assert last + (PF.HORIZON + 1) * pd.Timedelta(hours=1) < ts


def test_m1_series_only_before_train_window(tmp_path):
    from trader_ml.pa_proposer import labels as LB
    from trader_ml.pa_proposer import package as PK
    from trader_ml.pa_proposer import train as TR
    df = _walk(5200, seed=21, start="2021-03-01", freq="1h", vol=0.01)
    ts = list(df.index)
    rows = LB.label_rows(df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy(), ts)
    cut_i = 3500
    train_rows = [r for r in rows if r["ts"] >= ts[cut_i]]
    pkg = TR.train_tf(train_rows, arm_id="M1@1h")
    assert pkg is not None
    pkg["threshold"] = float(pkg["threshold"])
    path = PK.save_package(pkg, tmp_path / "pk")
    _write_feather(tmp_path, "BTC_USDT_USDT", "1h", df)
    train_start = pd.Timestamp(pkg["meta"]["train_window"]["start"])
    assert train_start == ts[cut_i]
    last_ok = H.m1_oos_end(train_start, "1h")
    r = H.run_m1_pair(("BTC/USDT", str(tmp_path), str(path), str(last_ok)))
    ser = r["series"]
    assert len(ser) == len(H.M1_GRID["thr_mult"]) * len(H.COSTS)
    for k, (dns, rr, _) in ser.items():
        if len(dns):
            # son cikis: son sinyal mumu + ufuk; egitim baslangicini asmaz
            assert pd.Timestamp(dns.max(), tz="UTC") <= train_start
    assert any(len(v[0]) for v in ser.values())


def test_no_holdout_literals_in_harness_use():
    src = (ROOT / "research" / "arm_harness.py").read_text(encoding="utf-8")
    assert "check_holdout" in src and "HOLDOUT" in src


# ------------------------------------------------------------------------------------------ pbo_rapor entegrasyonu
def _pbo():
    sp = importlib.util.spec_from_file_location("pbo_rapor_h", ROOT / "research" / "pbo_rapor.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def _fake_series(d: Path, days: pd.DatetimeIndex, setup="TF1", n=8, seed=0):
    rng = np.random.default_rng(seed)
    cols = [f"{setup}@4h|v{i}|f1|s0" for i in range(n)]
    pd.DataFrame(rng.normal(0, 1, (len(days), n)).astype("float32"), index=days, columns=cols).to_parquet(d / f"{setup}.parquet")
    (d / "meta.json").write_text(json.dumps({"kolonlar": {c: {"kurulum": setup, "tf": "4h", "n_islem": 5} for c in cols},
                                             "gun_izgarasi": ["a", "b"], "ciftler": ["X/USDT"], "dislanan": {"Q1@1h": "veri yok"}}))


def test_pbo_rapor_builds_harness_family_and_marks_arms(tmp_path):
    P = _pbo()
    arm = tmp_path / "arm"
    arm.mkdir()
    _fake_series(arm, pd.date_range("2024-01-01", periods=300, freq="D", tz="UTC"))
    res = P.build(tmp_path / "bt", ["TF1@4h", "Q1@1h", "S1@1h"], arm_dir=arm)
    fam = {f["aile"]: f for f in res["aileler"]}
    assert fam["Kural TF1 (harness)"]["durum"] == "tamam" and fam["Kural TF1 (harness)"]["n_yapilandirma"] == 8
    kay = {a["kurulum"]: a for a in res["kurulumlar"]}
    assert kay["TF1@4h"]["kayit"] == "harness" and kay["S1@1h"]["kayit"] == "yok" and kay["Q1@1h"]["neden"] == "veri yok"
    assert "Kural TF1 (harness)" in P.render_md(res)
    assert P.build(tmp_path / "bt", ["TF1@4h"], arm_dir=arm) == P.build(tmp_path / "bt", ["TF1@4h"], arm_dir=arm)


def test_pbo_rapor_refuses_series_touching_holdout(tmp_path, monkeypatch):
    import trader_engine.holdout as _H
    from trader_engine.holdout import BacktestArgError
    monkeypatch.setattr(_H, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    P = _pbo()
    arm = tmp_path / "arm"
    arm.mkdir()
    _fake_series(arm, pd.date_range(pd.Timestamp(HOLDOUT[0]) - timedelta(days=10), periods=30, freq="D", tz="UTC"))
    with pytest.raises(BacktestArgError):
        P.load_arm_series(arm)
