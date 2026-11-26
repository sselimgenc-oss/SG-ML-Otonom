"""Mounted Aurum statistics (trader_core.stats): independent checks against paper/textbook values.

Reference values are computed here with math.erfc / hand arithmetic, never with the mounted code.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trader_core.stats import (  # noqa: E402
    adjust_pvalues, cpcv_splits, deflated_sharpe, expected_max_sharpe, min_track_record_length, pbo_cscv,
    probabilistic_sharpe, purged_kfold, return_moments, stationary_bootstrap, stationary_bootstrap_indices,
    walk_forward_splits,
)
from trader_core.stats import stats as ST  # noqa: E402


def _phi(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def _bisect_ppf(p: float) -> float:
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if _phi(mid) < p else (lo, mid)
    return (lo + hi) / 2


# ---------------------------------------------------------------------------------------------- normal helpers
@pytest.mark.parametrize("p,z", [(0.5, 0.0), (0.8413447460685429, 1.0), (0.95, 1.6448536269514722),
                                 (0.975, 1.959963984540054), (0.99, 2.3263478740408408),
                                 (0.999, 3.090232306167813), (0.001, -3.090232306167813)])
def test_norm_ppf_known_quantiles(p, z):
    assert ST._norm_ppf(p) == pytest.approx(z, abs=1e-9)
    assert ST._norm_cdf(z) == pytest.approx(p, abs=1e-9)


def test_moments_match_textbook():
    x = np.array([1.0, 2.0, 3.0, 4.0, 10.0])
    m = x.mean()
    m2 = sum((v - m) ** 2 for v in x) / 5
    m3 = sum((v - m) ** 3 for v in x) / 5
    m4 = sum((v - m) ** 4 for v in x) / 5
    sk, ku = return_moments(x)
    assert sk == pytest.approx(m3 / m2 ** 1.5)
    assert ku == pytest.approx(m4 / m2 ** 2)


# ---------------------------------------------------------------------------------------------- PSR / DSR
def test_psr_hand_formula():
    sr, n, sk, ku, star = 0.1, 250, -0.5, 5.0, 0.02
    z = (sr - star) * math.sqrt(n - 1) / math.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    assert probabilistic_sharpe(sr, n, sk, ku, star) == pytest.approx(_phi(z), abs=1e-9)
    # normal returns, SR*=0 -> PSR = Phi(SR sqrt(n-1)/sqrt(1+SR^2/2))
    assert probabilistic_sharpe(0.05, 100) == pytest.approx(_phi(0.05 * math.sqrt(99) / math.sqrt(1 + 0.00125)), abs=1e-9)
    assert probabilistic_sharpe(0.0, 100) == pytest.approx(0.5)


def test_min_track_record_hand_formula():
    sr = 0.1
    expect = 1 + (1 + 0.5 * sr ** 2) * (1.6448536269514722 / sr) ** 2
    assert min_track_record_length(sr, prob=0.95) == pytest.approx(expect, rel=1e-8)
    assert min_track_record_length(-0.1) == math.inf


def test_deflated_sharpe_bailey_lopez_de_prado_2014_example():
    # Paper example: annualised SR 2.5 over 5y daily (T=1250, 250 d/y), skew -3, kurt 10, N=100 trials,
    # cross-trial variance of annualised SR = 0.5. Paper reports DSR ~ 0.90.
    periods = 250.0
    sr = 2.5 / math.sqrt(periods)
    var = 0.5 / periods
    # hand SR0 (annualised): sqrt(0.5) * ((1-g) Phi^-1(0.99) + g Phi^-1(1 - 1/(100 e)))
    g = 0.5772156649015329
    sr0_ann = math.sqrt(0.5) * ((1 - g) * 2.3263478740408408 + g * _bisect_ppf(1 - 1 / (100 * math.e)))
    assert expected_max_sharpe(100, var) * math.sqrt(periods) == pytest.approx(sr0_ann, abs=2e-3)
    assert sr0_ann == pytest.approx(1.79, abs=0.01)
    dsr = deflated_sharpe(sr, 1250, skew=-3.0, kurt=10.0, n_trials=100, trial_var=var)
    assert dsr == pytest.approx(0.90, abs=0.01)
    # hand PSR against SR0
    sr0 = sr0_ann / math.sqrt(periods)
    z = (sr - sr0) * math.sqrt(1249) / math.sqrt(1 + 3 * sr + 9 / 4 * sr ** 2)
    assert dsr == pytest.approx(_phi(z), abs=1e-4)
    # one trial -> DSR == PSR vs 0
    assert deflated_sharpe(sr, 1250, -3.0, 10.0, n_trials=1) == pytest.approx(probabilistic_sharpe(sr, 1250, -3.0, 10.0))


def test_expected_max_sharpe_monotone_in_trials():
    v = [expected_max_sharpe(n, 0.01) for n in (2, 10, 100, 1000)]
    assert v == sorted(v) and v[0] > 0


# ---------------------------------------------------------------------------------------------- Holm
def test_holm_hand_computed():
    p = [0.01, 0.04, 0.03, 0.005]
    # sorted 0.005,0.01,0.03,0.04 -> x4,x3,x2,x1 = .02,.03,.06,.04 -> running max .02,.03,.06,.06
    assert adjust_pvalues(p, "holm") == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert adjust_pvalues(p, "bonferroni") == pytest.approx([0.04, 0.16, 0.12, 0.02])
    assert adjust_pvalues([0.5, 0.9], "holm") == pytest.approx([1.0, 1.0])
    # Benjamini-Hochberg textbook: p=(.01,.02,.03,.04) m=4 -> all 0.04
    assert adjust_pvalues([0.01, 0.02, 0.03, 0.04], "bh") == pytest.approx([0.04] * 4)


# ---------------------------------------------------------------------------------------------- PBO / CSCV
def test_pbo_pure_noise_about_half():
    rng = np.random.default_rng(12345)
    res = pbo_cscv(rng.normal(0, 0.01, size=(960, 20)), n_splits=10, seed=1)
    assert 0.35 <= res.pbo <= 0.70
    assert res.n_combinations == math.comb(10, 5)


def test_pbo_strong_edge_is_low():
    rng = np.random.default_rng(7)
    m = rng.normal(0, 0.01, size=(960, 20))
    m[:, 3] += 0.01          # per-period Sharpe ~1 -> wins IS and OOS in every combination
    res = pbo_cscv(m, n_splits=10, seed=1)
    assert res.pbo <= 0.05
    assert set(res.selected.tolist()) == {3}


# ---------------------------------------------------------------------------------------------- bootstrap
def test_stationary_bootstrap_seed_and_mean():
    rng = np.random.default_rng(3)
    x = rng.normal(0.002, 0.01, 500)
    kw = dict(n_boot=3000, mean_block=10.0, return_samples=True)
    a = stationary_bootstrap(x, np.mean, seed=42, **kw)
    b = stationary_bootstrap(x, np.mean, seed=42, **kw)
    c = stationary_bootstrap(x, np.mean, seed=43, **kw)
    assert np.array_equal(a["samples"], b["samples"])
    assert not np.array_equal(a["samples"], c["samples"])
    se = x.std(ddof=1) / math.sqrt(x.size)
    assert float(np.mean(a["samples"])) == pytest.approx(float(x.mean()), abs=0.5 * se)  # mean preserved
    assert a["lower"] < x.mean() < a["upper"]


def test_stationary_bootstrap_indices_valid_and_block_length():
    idx = stationary_bootstrap_indices(1000, 200, 20.0, np.random.default_rng(0))
    assert idx.shape == (200, 1000) and idx.min() >= 0 and idx.max() < 1000
    # consecutive positions (idx[t+1] == idx[t]+1 mod n) occur with prob 1-1/mean_block = 0.95
    cont = np.mean(idx[:, 1:] == (idx[:, :-1] + 1) % 1000)
    assert cont == pytest.approx(0.95, abs=0.01)


# ---------------------------------------------------------------------------------------------- splits
def test_walk_forward_no_overlap_and_fold_count():
    n, train, test, purge, emb = 1000, 400, 100, 5, 3
    sp = walk_forward_splits(n, train, test, purge=purge, embargo=emb)
    # test starts at train+gap+j*test = 408+100j; last full block must end <= 1000 -> j=0..5 (508.. only if fits)
    starts = [t[0] for _, t in sp]
    assert starts == [408 + 100 * j for j in range(len(sp))]
    assert len(sp) == 6 and sp[-1][1][-1] < n
    for tr, te in sp:
        assert len(set(tr) & set(te)) == 0
        assert tr.max() + purge + emb < te.min()
        assert len(tr) == train
    anc = walk_forward_splits(n, train, test, anchored=True, purge=purge, embargo=emb)
    assert all(tr[0] == 0 for tr, _ in anc)
    assert [len(tr) for tr, _ in anc] == sorted(len(tr) for tr, _ in anc)


def test_purged_kfold_purge_and_embargo():
    n, k, purge, emb = 1000, 5, 7, 4
    sp = purged_kfold(n, k, purge=purge, embargo=emb)
    assert len(sp) == k
    assert sorted(np.concatenate([te for _, te in sp]).tolist()) == list(range(n))   # tests partition the sample
    for tr, te in sp:
        a, b = te.min(), te.max()
        assert not set(tr) & set(te)
        banned = set(range(max(0, a - purge), a)) | set(range(b + 1, min(n, b + 1 + purge + emb)))
        assert not (set(tr) & banned)
        # everything else outside the test block is kept
        rest = set(range(n)) - set(te) - banned
        assert set(tr) == rest


def test_cpcv_counts_and_disjointness():
    n, N, k, purge, emb = 600, 6, 2, 5, 2
    res = cpcv_splits(n, N, k, purge=purge, embargo=emb)
    assert res.n_splits == math.comb(N, k) == 15
    assert res.n_paths == math.comb(N - 1, k - 1) == 5
    assert res.paths.shape == (5, N)
    for (tr, te), tg in zip(res.splits, res.test_groups):
        assert len(tg) == k
        assert not set(tr) & set(te)
        for g in tg:                                    # purge zone before / embargo zone after each test group
            grp = res.groups[g]
            a, b = int(grp.min()), int(grp.max())
            banned = set(range(max(0, a - purge), a)) | set(range(b + 1, min(n, b + 1 + purge + emb)))
            assert not (set(tr) & banned)
    for g in range(N):                                  # each group is tested in C(N-1,k-1) splits
        assert sum(g in tg for tg in res.test_groups) == 5
        assert sorted(res.paths[:, g].tolist()) == sorted(i for i, tg in enumerate(res.test_groups) if g in tg)
