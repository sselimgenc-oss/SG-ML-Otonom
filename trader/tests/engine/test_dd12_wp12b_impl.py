"""DD-12 WP-12b uygulayici duman testleri: F1, S1, H2 kurulumlari (Ek-K K-3/K-4/K-5). Ag yok; yalniz sentetik seriler.
Bagimsiz spec testleri test_dd12_wp12b_spec.py'dadir (ayri yazar)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import signals as S
from trader_engine import position_manager as PM
from trader_engine.strategies import arms as A
from trader_engine.strategies.arms import ArmInput
from trader_engine.strategies.arms import _pa as P
from trader_engine.strategies.arms import f1, h2, s1
from trader_engine.strategies.base import StrategyInfo, validate_table

REPO = Path(__file__).resolve().parents[2]
OHLC = ["open", "high", "low", "close"]
NEW = {"F1": f1, "S1": s1, "H2": h2}
INFO = StrategyInfo("t", "1", ("F1", "S1", "H2"), ("1h",), ("1h",), {}, {}, {}, (), True)
CAND_COLS = ["setup", "side", "signal", "skip_reason", "planned_entry", "planned_stop", "planned_target", "rr",
             "stop_dist_atr", "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr", "pullback_ema"]
MIRROR_C = 200.0
SWAP = {"trend_up": "trend_down", "trend_down": "trend_up", "range": "range", "unclear": "unclear",
        "volatile": "volatile"}


# ----------------------------------------------------------------------------------------------- yardimcilar
def _bars(n: int, seed: int, drift: float = 0.0, vol: float = 0.6) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cl = 100 + np.cumsum(rng.normal(drift, vol, n))
    o = np.r_[cl[0], cl[:-1]] + rng.normal(0, 0.2, n)
    hi = np.maximum(o, cl) + np.abs(rng.normal(0.3, 0.2, n))
    lo = np.minimum(o, cl) - np.abs(rng.normal(0.3, 0.2, n))
    idx = pd.date_range("2026-02-01", periods=n, freq="h")
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": cl, "volume": 1.0}, index=idx)


def _labels(n: int, seed: int) -> list[str]:
    rng = np.random.default_rng(seed + 1000)
    return list(rng.choice(["trend_up", "trend_down", "range", "unclear"], size=n))


def _inp(trig: pd.DataFrame, labels, tf: str = "1h") -> ArmInput:
    idx = trig.index
    reg = pd.DataFrame({"regime": list(labels), "rh": np.nan, "rl": np.nan, "rh_touches": 0, "rl_touches": 0,
                        "atr": 1.0, "atr_ratio": 1.0}, index=idx)
    params = S.SignalParams()
    core = S.compute_signals(trig[OHLC], reg, params)
    return ArmInput(pair="T/X", tf=tf, D=idx[-1].to_pydatetime(), trig=trig, h4=trig, params=params,
                    core_fn=lambda: core)


def _mirror_bars(tr: pd.DataFrame) -> pd.DataFrame:
    C = MIRROR_C
    return pd.DataFrame({"open": C - tr["open"], "high": C - tr["low"], "low": C - tr["high"], "close": C - tr["close"],
                         "volume": tr["volume"]}, index=tr.index)


def _same(a: pd.DataFrame, b: pd.DataFrame, cols=CAND_COLS) -> bool:
    for col in cols:
        x, y = a[col].to_numpy(dtype=object), b[col].to_numpy(dtype=object)
        for u, v in zip(x, y):
            if u is None or v is None:
                if not (u is None and v is None):
                    return False
            elif isinstance(u, float) and isinstance(v, float) and np.isnan(u) and np.isnan(v):
                continue
            elif u != v:
                return False
    return True


# ----------------------------------------------------------------------------------------------- sozlesme
@pytest.mark.parametrize("setup", ["F1", "S1", "H2"])
def test_contract_fields(setup):
    mod = NEW[setup]
    A.validate_arm(mod, setup)                         # EXIT_MODE, PRIORITY, FEATURES (WP-12a sozlesmesi)
    assert mod.SETUP == setup
    assert mod.TIMEFRAMES == ("1h", "4h", "1d")
    assert mod.CORE is False
    assert len(mod.FEATURES) <= A.MAX_FEATURES


def test_exit_mode_and_priority_per_setup():
    assert (f1.EXIT_MODE, s1.EXIT_MODE, h2.EXIT_MODE) == ("target", "trail", "trail")
    assert (h2.PRIORITY, s1.PRIORITY, f1.PRIORITY) == (50, 60, 70)
    assert A.priority_of("H2") < A.priority_of("S1") < A.priority_of("F1")
    assert A.exit_mode("F1") == "target" and A.exit_mode("S1") == "trail" and A.exit_mode("H2") == "trail"
    assert PM.exit_mode_of("F1") == "target" and PM.exit_mode_of("H2") == "trail"


def test_registry_discovers_new_setups():
    assert {"F1", "S1", "H2"} <= set(A.list_arms())
    assert A.features_of("H2")["ema_value"] == "ema_value"


def test_paper_config_lists_new_arms():
    cfg = json.loads((REPO / "config" / "engine.paper.json").read_text(encoding="utf-8"))
    want = {f"{s_}@{tf}" for s_ in ("F1", "S1", "H2") for tf in ("1h", "4h", "1d")}      # 26.11 sahip karari: 15m giris kolu yok
    arms = cfg["arms"]
    assert len(arms) == len(set(arms))
    assert want <= set(arms)
    for aid in want:
        setup, tf = A.parse_arm_id(aid)
        assert tf in A.find_arm(setup).TIMEFRAMES


# ----------------------------------------------------------------------------------------------- davranis
@pytest.mark.parametrize("setup", ["F1", "S1", "H2"])
@pytest.mark.parametrize("tf", ["1h", "1d"])
def test_fires_and_table_valid(setup, tf):
    mod = NEW[setup]
    total = 0
    for seed in range(12):
        tr = _bars(600, seed, drift=0.05 * (seed % 3 - 1))
        out = mod.compute(_inp(tr, _labels(len(tr), seed), tf))
        validate_table(out, INFO, tr.index)
        sig = out[out["signal"].astype(bool)]
        total += len(sig)
        assert set(sig["setup"]) <= {setup}
        if len(sig):
            assert sig["stop_dist_atr"].between(0.5, 3.0).all()
    assert total > 0, f"{setup}@{tf}: sentetik serilerde hic aday yok"


@pytest.mark.parametrize("setup", ["F1", "S1", "H2"])
def test_features_finite_on_signal_rows(setup):
    mod = NEW[setup]
    for seed in range(8):
        tr = _bars(600, seed)
        out = mod.compute(_inp(tr, _labels(len(tr), seed)))
        sig = out[out["signal"].astype(bool)]
        for carrier in set(mod.FEATURES.values()):
            if carrier == "rr" and setup != "F1":
                continue
            assert np.isfinite(sig[carrier].astype(float)).all(), (setup, carrier)


@pytest.mark.parametrize("setup", ["F1", "S1", "H2"])
def test_mirror_symmetry(setup):
    """K-ORT-4: short, long'un fiyat aynasinda (rejim da aynalanir) ayni barlarda sinyal verir; stop/hedef aynalidir."""
    mod = NEW[setup]
    for seed in range(8):
        tr = _bars(600, seed)
        lab = _labels(len(tr), seed)
        orig = mod.compute(_inp(tr, lab))
        mir = mod.compute(_inp(_mirror_bars(tr), [SWAP[x] for x in lab]))
        assert orig["signal"].to_numpy().tolist() == mir["signal"].to_numpy().tolist()
        assert orig["skip_reason"].tolist() == mir["skip_reason"].tolist()
        sig = orig["signal"].to_numpy(dtype=bool)
        if not sig.any():
            continue
        o_, m_ = orig[sig], mir[sig]
        assert (o_["side"].to_numpy() == np.where(m_["side"].to_numpy() == "long", "short", "long")).all()
        assert np.allclose(o_["planned_entry"].astype(float), MIRROR_C - m_["planned_entry"].astype(float))
        assert np.allclose(o_["planned_stop"].astype(float), MIRROR_C - m_["planned_stop"].astype(float))
        tg_o, tg_m = o_["planned_target"].astype(float), MIRROR_C - m_["planned_target"].astype(float)
        assert np.allclose(tg_o, tg_m, equal_nan=True)
        assert np.allclose(o_["stop_dist_atr"].astype(float), m_["stop_dist_atr"].astype(float))


@pytest.mark.parametrize("setup", ["F1", "S1", "H2"])
def test_cut_invariance_and_future_poison(setup):
    """K-ORT-1/2: t'ye kadar olan veri ile t satiri, ileri barlar bozulsa da ayni; kesme testi."""
    mod = NEW[setup]
    tr = _bars(400, 3)
    lab = _labels(len(tr), 3)
    full = mod.compute(_inp(tr, lab))
    for k in range(len(tr) - 120, len(tr), 29):
        part = mod.compute(_inp(tr.iloc[:k + 1], lab[:k + 1]))
        assert _same(part.iloc[[-1]], full.iloc[[k]]), (setup, k)
    k = len(tr) - 120
    poisoned = tr.copy()
    poisoned.iloc[k + 1:] = poisoned.iloc[k + 1:] * 1.5 + 40
    pl = list(lab)
    pl[k + 1:] = ["trend_up"] * (len(lab) - k - 1)
    pois = mod.compute(_inp(poisoned, pl))
    assert _same(pois.iloc[:k + 1], full.iloc[:k + 1])


@pytest.mark.parametrize("setup", ["F1", "S1", "H2"])
def test_warmup_and_volatile_give_no_candidates(setup):
    mod = NEW[setup]
    short = _bars(20, 1)
    out = mod.compute(_inp(short, _labels(len(short), 1)))
    assert not out["signal"].any() and out["setup"].isna().all()
    tr = _bars(400, 5)
    out = mod.compute(_inp(tr, ["volatile"] * len(tr)))
    assert not out["signal"].any() and out["setup"].isna().all()


@pytest.mark.parametrize("setup", ["F1", "S1", "H2"])
def test_deterministic(setup):
    mod = NEW[setup]
    tr = _bars(500, 9)
    lab = _labels(len(tr), 9)
    a = mod.compute(_inp(tr, lab))
    b = mod.compute(_inp(tr.copy(), list(lab)))
    assert a.equals(b)
