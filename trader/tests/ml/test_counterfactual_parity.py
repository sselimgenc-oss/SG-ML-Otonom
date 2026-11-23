"""trader_core.counterfactual (bagimsiz kopya formul) ile trader_ml.labels.label_candidates ayni etiketi/net R'yi uretir."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader_core import counterfactual as CF
from trader_ml import config as C
from trader_ml.labels import label_candidates


def test_constants_locked_to_ml_config():
    assert (CF.HORIZON_BARS, CF.TARGET_R, CF.FEE_RATE, CF.SLIPPAGE_RATE) == (C.HORIZON_BARS, C.TARGET_R, C.FEE_RATE, C.SLIPPAGE_RATE)
    assert pd.Timedelta(milliseconds=CF.BAR_MS) == C.BAR
    assert CF.HOLDOUT_START == C.HOLDOUT_START.to_pydatetime() and CF.HOLDOUT_END == C.HOLDOUT_END.to_pydatetime()
    from trader_engine.holdout import KILIT_ACIK
    assert CF.KILIT_ACIK == C.KILIT_ACIK == KILIT_ACIK     # tek anahtar kopyalari esit (23.11.2026 kilit acik)


def _candles(n, seed):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-03-01", periods=n, freq="1h", tz="UTC")
    close = 100 + np.cumsum(rng.normal(0, 0.6, n))
    hi = close + rng.uniform(0, 1.0, n)
    lo = close - rng.uniform(0, 1.0, n)
    return pd.DataFrame({"open": close, "high": hi, "low": lo, "close": close}, index=idx)


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("side", ["long", "short"])
def test_random_paths_identical_to_ml_labels(seed, side):
    df = _candles(400, seed)
    rows = []
    for bar in range(5, 300, 7):                        # tam ufku olan adaylar (bar+72 < 400)
        e = float(df["close"].iloc[bar])
        s = e - 1.2 if side == "long" else e + 1.2
        tg = e + 1.9 * (1 if side == "long" else -1)
        rows.append({"ts": df.index[bar] + C.BAR, "side": side, "planned_entry": e, "planned_stop": s, "planned_target": tg, "bar": bar})
    cands = pd.DataFrame(rows)
    ml = label_candidates(df, cands.drop(columns="bar"))
    hi, lo, cl = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    n_cmp = 0
    for k, r in cands.iterrows():
        a = int(r["bar"]) + 1
        sl = slice(a, a + CF.HORIZON_BARS)
        e, s = r["planned_entry"], r["planned_stop"]
        up = e + (1 if side == "long" else -1) * CF.TARGET_R * abs(e - s)
        bar = CF.replay(hi[sl], lo[sl], cl[sl], side, e, s, up)
        plan = CF.replay(hi[sl], lo[sl], cl[sl], side, e, s, r["planned_target"], horizon=CF.HORIZON_BARS)
        assert bar is not None and plan is not None
        assert bar["outcome"] == ml["label"].iloc[k]
        assert bar["r_net"] == pytest.approx(ml["barrier_net_r"].iloc[k], abs=1e-12)
        assert bar["cost_r"] == pytest.approx(ml["cost_r"].iloc[k], abs=1e-12)
        end = df.index[a + bar["bars_held"] - 1] + C.BAR
        assert end == ml["label_end_ts"].iloc[k]
        n_cmp += 1
    assert n_cmp > 30


def test_same_bar_ambiguity_and_time_barrier_match_ml():
    idx = pd.date_range("2025-03-01", periods=120, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0}, index=idx)
    df.iloc[13, df.columns.get_loc("low")] = 98.9
    df.iloc[13, df.columns.get_loc("high")] = 103.0
    cand = pd.DataFrame({"ts": [idx[10] + C.BAR], "side": ["long"], "planned_entry": [100.0], "planned_stop": [99.0],
                         "planned_target": [np.nan]})
    ml = label_candidates(df, cand)
    sl = slice(11, 11 + 72)
    mine = CF.replay(df["high"].to_numpy()[sl], df["low"].to_numpy()[sl], df["close"].to_numpy()[sl], "long", 100.0, 99.0, 102.0)
    assert mine["outcome"] == ml["label"].iloc[0] == 0 and mine["exit_reason"] == "stop"
    assert mine["r_net"] == pytest.approx(ml["barrier_net_r"].iloc[0])
    flat = pd.DataFrame({"open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0}, index=idx)
    ml = label_candidates(flat, cand)
    mine = CF.replay(flat["high"].to_numpy()[sl], flat["low"].to_numpy()[sl], flat["close"].to_numpy()[sl], "long", 100.0, 99.0, 102.0)
    assert mine["exit_reason"] == "time" and mine["r_net"] == pytest.approx(ml["barrier_net_r"].iloc[0])
    assert mine["bars_held"] == 72
