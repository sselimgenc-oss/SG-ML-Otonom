"""Terfi kapisi: yardimcilar, kabul ve ret yollari, walk-forward temizligi."""
import numpy as np
import pandas as pd
import pytest

from trader_ml.config import BAR, DATA_START, HORIZON_BARS, EMBARGO_BARS
from trader_ml.gate import max_drawdown, rankdata, rho_t, run_gate, select_threshold, spearman, stress_r
from trader_ml.walkforward import make_folds


def test_rankdata_ties_and_spearman_known_values():
    assert list(rankdata([10, 20, 20, 30])) == [1.0, 2.5, 2.5, 4.0]
    assert spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(0.8)
    assert rho_t(0.5, 12) == pytest.approx(0.5 * np.sqrt(10 / 0.75))


def test_select_threshold_respects_grid_and_min_fraction():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.2, 0.9, 1000)
    r = p - 0.5
    th, _ = select_threshold(p, r)
    assert th is not None and 0.45 <= th <= 0.70 and (p >= th).mean() >= 0.30
    th, _ = select_threshold(np.full(100, 0.3), np.zeros(100))     # hicbir esik uygun degil
    assert th is None


def test_max_drawdown_and_stress():
    assert max_drawdown(np.array([1, -2, -1, 3, -1.0])) == pytest.approx(3.0)
    df = pd.DataFrame({"net_r": [1.0], "cost_r": [0.2]})           # entry/R = 100
    assert stress_r(df)[0] == pytest.approx(1.0 - (0.001 + 0.0010) * 100)      # +5 bp PER SIDE = 10 bp tur


def _oof(oracle: bool, seed=0, n=900):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-09-01", periods=n, freq="7h", tz="UTC")
    s = rng.random(n) < 0.5
    net = np.where(s, 1.2, -0.7) + rng.normal(0, 0.4, n)
    lab = (rng.random(n) < np.where(s, 0.75, 0.10)).astype(float)
    df = pd.DataFrame({"ts": ts, "pair": rng.choice(list("ABCDEF"), n), "fold": np.repeat([0, 1, 2, 3], n // 4 + 1)[:n],
                       "taken": True, "label": lab, "net_r": net, "cost_r": 0.2, "base_rate": 0.42})
    sig = s if oracle else rng.random(n) < 0.5
    df["p_good"] = np.clip(np.where(sig, 0.62, 0.20) + rng.normal(0, 0.03, n), 0.01, 0.99)
    df["p_noise"] = np.clip(0.4 + rng.normal(0, 0.15, n), 0.01, 0.99)
    return df


def test_gate_accepts_a_genuine_edge():
    oof = _oof(True)
    r = run_gate(oof, ["p_good", "p_noise"], selected="p_good", parity_max_abs_diff=2e-16, n_trials=2, n_boot=400)
    failed = [c.name for c in r.checks if c.ok is False]
    # PBO: esikler arasi yapilandirmalar neredeyse ayni oldugundan bu sentetik durumda belirsiz olabilir
    assert set(failed) <= {"3e. PBO (CSCV)"}, [(c.name, c.value) for c in r.checks if c.ok is False]
    assert r.threshold is not None and 0.45 <= r.threshold <= 0.70
    assert [c.name[:2] for c in r.checks][:3] == ["1.", "2.", "3a"]           # sira: IC, kalibrasyon, Bolum 1


def test_gate_rejects_noise_and_reports_first_failure():
    oof = _oof(False, seed=1)
    r = run_gate(oof, ["p_good", "p_noise"], selected="p_good", parity_max_abs_diff=2e-16, n_trials=2, n_boot=400)
    assert not r.passed and r.first_failure is not None


def test_gate_rejects_failed_parity_and_cost_stress():
    oof = _oof(True)
    r = run_gate(oof, ["p_good", "p_noise"], selected="p_good", parity_max_abs_diff=1e-6, n_trials=2, n_boot=200)
    assert any(c.name.startswith("5.") and c.ok is False for c in r.checks) and not r.passed
    worse = oof.assign(net_r=oof["net_r"] - 1.5)
    r2 = run_gate(worse, ["p_good", "p_noise"], selected="p_good", parity_max_abs_diff=0.0, n_trials=2, n_boot=200)
    assert any(c.name.startswith("4.") and c.ok is False for c in r2.checks)


def test_gate_rejects_when_dsr_trials_explode():
    oof = _oof(True)
    rng = np.random.default_rng(9)
    oof["net_r"] = 0.05 + 0.25 * (oof["p_good"] > 0.4) + rng.normal(0, 1.0, len(oof))      # zayif kenar
    few = run_gate(oof, ["p_good", "p_noise"], selected="p_good", parity_max_abs_diff=0.0, n_trials=2, n_boot=200)
    many = run_gate(oof, ["p_good", "p_noise"], selected="p_good", parity_max_abs_diff=0.0, n_trials=10 ** 6, n_boot=200)
    assert many.metrics["dsr"] < few.metrics["dsr"] < 1.0


def test_walk_forward_folds_are_purged_and_non_overlapping(table):
    folds = make_folds(table)
    assert len(folds) == 7                                            # §3.3: kesim EGITIM_KESIMI (kilit acik: 2026-11-01) -> 7 test dilimi (kilit kapaliyken 2026-04 sonuna kadar 4)
    gap = (HORIZON_BARS + EMBARGO_BARS) * BAR
    for f in folds:
        tr, te = table.iloc[f["train_rows"]], table.iloc[f["test_rows"]]
        assert len(tr) and len(te)
        assert not set(f["train_rows"]) & set(f["test_rows"])
        assert tr["ts"].max() <= f["test_start"] - gap + BAR          # egitim, test baslamadan once biter
        assert tr["label_end_ts"].max() < f["test_start"] - EMBARGO_BARS * BAR   # etiket ufku testin icine girmez
        assert te["ts"].min() - BAR >= f["test_start"] and te["ts"].max() - BAR < f["test_end"]
    assert (folds[0]["test_start"] - DATA_START) >= pd.Timedelta(days=240)        # >= 8 ay egitim
    starts = [f["test_start"] for f in folds]
    assert all(b - a == pd.Timedelta(days=60) for a, b in zip(starts, starts[1:]))
    # genisleyen pencere
    assert all(len(b["train_rows"]) >= len(a["train_rows"]) for a, b in zip(folds, folds[1:]))
