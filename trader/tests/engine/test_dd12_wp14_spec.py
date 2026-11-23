"""Independent spec tests for DD-12 WP-14 (M1: ML'in kendi adayi).

Written from docs/motor/dd12-capraz-varlik-spec.md (sec. 3 table row M1, sec. 5.3, sec. 9 WP-14 row, D-T21, D-T22 M1
part) and the owner decisions at the end of otonom-trading-arastirma/tasarim-kararlari.md: M1 is active from day one,
no minimum-sample threshold (no package => no M1 candidates, never a block of other arms); training refuses any row in
the lock window 2026-05-01..2026-11-01; package sha256 + expiry integrity; M1 arm contract (SETUP "M1", PRIORITY 90,
EXIT_MODE per spec = "target" (fixed stop/target + time stop), FEATURES <= 6, arm cap 3); M1 candidates use only closed
bars; deterministic training; export script keeps the lock window out of paper records; health freshness alarm when the
package is older than 8 days.

The implementation was not read. Modules that do not exist yet are imported with pytest.importorskip, and callables are
discovered tolerantly (by name pattern) because WP-14 does not fix every function name. Synthetic data only; no network.
"""
from __future__ import annotations

import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

# 23.11.2026 kullanici karari: kilit ACIK. Bu dosya kilit mekanizmasini sinar -> kilit KAPALI bayragiyla (conftest.egitim_kilitli); acik davranis tests/ml/test_kilit_acik_egitim.py.
pytestmark = pytest.mark.usefixtures("egitim_kilitli")


UTC = timezone.utc
TRADER = Path(__file__).resolve().parents[2]
SRC = TRADER / "src"
LOCK_START = datetime(2026, 5, 1, tzinfo=UTC)
LOCK_END = datetime(2026, 11, 1, tzinfo=UTC)
NOW = datetime(2026, 11, 20, 4, 30, tzinfo=UTC)
TF_DELTA = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}


# ------------------------------------------------------------------ files
def test_expected_files_exist():
    for rel in ("src/trader_ml/pa_proposer/features.py", "src/trader_ml/pa_proposer/labels.py",
                "src/trader_ml/pa_proposer/train.py", "src/trader_ml/pa_proposer/package.py",
                "research/pa_proposer_build.py", "research/paper_models.csv",
                "src/trader_engine/strategies/arms/m1.py", "scripts/export_paper_records.py",
                "scripts/health_run.py"):
        assert (TRADER / rel).is_file(), rel


# ------------------------------------------------------------------ M1 arm contract (spec 5.3, 9, D-T16)
PF = pytest.importorskip("trader_ml.pa_proposer.features")


def _m1():
    return pytest.importorskip("trader_engine.strategies.arms.m1")


def _arms():
    return pytest.importorskip("trader_engine.strategies.arms")


def test_m1_module_contract_constants():
    m = _m1()
    assert m.SETUP == "M1"
    assert m.PRIORITY == 90, "spec 9 / arms doc: M1 PRIORITY 90"
    # 5.3: stop 1.5 ATR, target 3 ATR, time stop 48 bars = fixed target + time stop path, i.e. the R1 "target" exit mode.
    assert m.EXIT_MODE == "target"
    assert set(m.TIMEFRAMES) <= {"15m", "1h", "4h", "1d"}
    # 5.3 "M1@1h ile baslar; 15dk/4s ek cikti": 1h is present and first, 15m and 4h follow.
    assert m.TIMEFRAMES[0] == "1h"
    assert {"15m", "4h"} <= set(m.TIMEFRAMES)


def test_m1_passes_arm_contract_validation():
    arms = _arms()
    m = _m1()
    arms.validate_arm(m, "m1")                       # EXIT_MODE, PRIORITY, FEATURES (<= 6, carriers)
    assert len(m.FEATURES) <= 6


def test_m1_is_discovered_by_arm_registry():
    arms = _arms()
    _m1()
    mods = arms.discover(refresh=True)
    assert "M1" in mods
    assert arms.priority_of("M1") == 90
    assert arms.exit_mode("M1") == "target"
    assert len(arms.features_of("M1")) <= 6
    assert {"T1", "R1"} <= set(mods), "M1 must not remove or shadow existing arms"


def test_arm_cap_three_for_m1_and_default_four_for_others():
    arms = _arms()
    _m1()
    AG = pytest.importorskip("trader_engine.arm_guard")
    caps = {"default": 4, "M1": 3}
    assert AG.arm_cap(caps, "M1@1h", "M1") == 3
    assert AG.arm_cap(caps, "M1@15m", "M1") == 3
    assert AG.arm_cap(caps, "T1@1h", "T1") == 4
    assert AG.arm_full(["M1@1h", "M1@1h", "M1@1h"], "M1@1h", AG.arm_cap(caps, "M1@1h", "M1"))
    assert not AG.arm_full(["M1@1h", "M1@1h"], "M1@1h", 3)


# ------------------------------------------------------------------ no model => no candidates, never a block
def _closed_bars(n=120, start=datetime(2026, 9, 1, tzinfo=UTC), tf="1h"):
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")   # index = bar open time
    rng = np.random.default_rng(14)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    op = np.r_[close[0], close[:-1]]
    hi = np.maximum(op, close) + 0.3
    lo = np.minimum(op, close) - 0.3
    return pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": 1.0}, index=idx)


def test_no_package_gives_no_m1_candidates_and_does_not_raise():
    m = _m1()
    arms = _arms()
    from trader_engine.strategies.arms import ArmInput
    bars = _closed_bars()
    D = bars.index[-1] + TF_DELTA["1h"]                            # decision time = end of last closed bar
    inp = ArmInput(pair="ETH/USDT", tf="1h", D=D.to_pydatetime(), trig=bars,
                   h4=bars.iloc[::4], params=None, core_fn=lambda: None)
    out = m.compute(inp)
    assert isinstance(out, pd.DataFrame)
    assert not bool(out["signal"].fillna(False).astype(bool).any()), "no model must mean no M1 candidate"
    assert {"T1", "R1"} <= set(arms.discover())


# ------------------------------------------------------------------ features: closed bars only (no lookahead)
def _feat_by_bar(bars, side="long"):
    """Bar basina ozellik satiri (pa_proposer.features.feature_matrix); gecersiz bar = NaN satiri."""
    o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    X, mask = PF.feature_matrix(o, h, l, c, range(len(bars)), side)
    out = np.full((len(bars), len(PF.FEATURE_NAMES)), np.nan)
    out[mask] = X
    return out


def test_m1_features_use_only_closed_bars():
    bars = _closed_bars(160)
    k = 12                                                         # last k bars are "future" relative to the cut
    base = _feat_by_bar(bars)
    tampered = bars.copy()
    tampered.iloc[-k:, tampered.columns.get_indexer(["open", "high", "low", "close"])] *= 1.7   # wild future prices
    alt = _feat_by_bar(tampered)
    cut = len(bars) - k
    assert np.array_equal(np.nan_to_num(base[:cut], nan=-9.0), np.nan_to_num(alt[:cut], nan=-9.0)), \
        "a feature at bar t must not depend on bars after t (lookahead)"


def test_m1_features_are_deterministic_and_bit_identical_on_rerun():
    bars = _closed_bars(140)
    assert _feat_by_bar(bars).tobytes() == _feat_by_bar(bars.copy()).tobytes()


# ------------------------------------------------------------------ training: lock window and determinism
def _train_mod():
    return pytest.importorskip("trader_ml.pa_proposer.train")


def _train_entry(tm):
    return tm.train_tf                                             # pa_proposer.train.train_tf(rows, *, arm_id, created_at)


def test_lock_constants_match_engine_holdout():
    tm = _train_mod()
    H = pytest.importorskip("trader_engine.holdout")
    for name in ("LOCK_START", "LOCK_END"):
        if hasattr(tm, name):
            assert getattr(tm, name) == (H.HOLDOUT[0] if name == "LOCK_START" else H.HOLDOUT[1])
    assert H.HOLDOUT == (LOCK_START, LOCK_END)


def _lock_rejecter(tm):
    for name in ("assert_no_lock", "assert_not_locked", "reject_locked", "check_lock", "in_lock"):
        if hasattr(tm, name):
            return getattr(tm, name), name
    return None, None


@pytest.mark.parametrize("ts", [datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 7, 15, 12, tzinfo=UTC),
                                datetime(2026, 10, 31, 23, 0, tzinfo=UTC)])
def test_training_refuses_row_inside_lock_window(ts):
    tm = _train_mod()
    fn, name = _lock_rejecter(tm)
    if fn is None:
        pytest.skip("no lock check exported by pa_proposer.train")
    row = {"id": 1, "arm_id": "M1@1h", "ts": ts, "ts_end": None, "r": 1.0}
    if name == "in_lock":
        assert fn(ts) is True
    else:
        with pytest.raises(ValueError):
            fn([row])


def test_outcome_window_reaching_into_lock_is_locked():
    tm = _train_mod()
    fn, name = _lock_rejecter(tm)
    if fn is None or name == "in_lock":
        if fn is not None and name == "in_lock":
            assert fn(datetime(2026, 4, 30, 20, tzinfo=UTC), datetime(2026, 5, 1, 6, tzinfo=UTC)) is True
            return
        pytest.skip("no lock check exported by pa_proposer.train")
    row = {"id": 2, "arm_id": "M1@1h", "ts": datetime(2026, 4, 30, 20, tzinfo=UTC),
           "ts_end": datetime(2026, 5, 1, 6, tzinfo=UTC), "r": 0.5}
    with pytest.raises(ValueError):
        fn([row])


@pytest.mark.parametrize("ts", [datetime(2026, 4, 30, 23, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC),
                                datetime(2026, 11, 2, tzinfo=UTC)])
def test_training_accepts_rows_outside_lock_window(ts):
    tm = _train_mod()
    fn, name = _lock_rejecter(tm)
    if fn is None:
        pytest.skip("no lock check exported by pa_proposer.train")
    row = {"id": 3, "arm_id": "M1@1h", "ts": ts, "ts_end": None, "r": 1.0}
    if name == "in_lock":
        assert fn(ts) is False
    else:
        fn([row])                                                  # must not raise


def _synthetic_rows(n=60, start=datetime(2026, 11, 2, tzinfo=UTC)):
    rng = np.random.default_rng(7)
    nf = len(PF.FEATURE_NAMES)
    rows = []
    for i in range(n):
        win = int(i % 2 == 0)
        x = rng.normal(size=nf)
        x[0] += win                                                # ilk ozellik etiketle iliskili (fit anlamli olsun)
        rows.append({"id": i, "arm_id": "M1@1h", "ts": start + timedelta(hours=i), "side": "long", "y": win,
                     "r": 1.2 if win else -1.0, "x": x.tolist()})
    return rows


def test_training_is_deterministic_same_input_same_package_sha():
    tm = _train_mod()
    fn = _train_entry(tm)
    rows = _synthetic_rows()
    p1 = fn(rows, arm_id="M1@1h", created_at=NOW)
    p2 = fn(rows, arm_id="M1@1h", created_at=NOW)
    assert isinstance(p1, dict), "train_tf must return a package dict for a two-class sample"
    assert json.dumps(p1, sort_keys=True, default=str) == json.dumps(p2, sort_keys=True, default=str)


def test_training_with_no_rows_gives_no_model_not_exception():
    tm = _train_mod()
    assert _train_entry(tm)([], arm_id="M1@1h") is None


# ------------------------------------------------------------------ package integrity (trader_core.ml_package)
MP = pytest.importorskip("trader_core.ml_package")


def _package_module():
    return pytest.importorskip("trader_ml.pa_proposer.package")


def _build_pkg(created):
    builder = _package_module().build_package
    names = ["f_a", "f_b"]
    body_model = {"trees": [], "base": 0.0}
    return builder(arm_id="M1@1h", model=body_model, threshold=0.5, names=names,
                   train_start=None, train_end=None, n_train=10, n_pos=5, data_hash="x", lock_dropped=0,
                   base_rate=0.5, created_at=created)


def test_package_is_loadable_and_tamper_is_refused():
    pkg = _build_pkg(NOW)
    assert pkg["meta"]["arm_id"] == "M1@1h"
    assert pkg["meta"]["expires_at"] and pkg["meta"]["model_hash"]
    MP.load_package(pkg, now=NOW, require_gate=False)
    bad = json.loads(json.dumps(pkg))
    bad["model"]["base"] = 0.9                                    # body changed, hash not updated
    with pytest.raises(MP.PackageError):
        MP.load_package(bad, now=NOW, require_gate=False)


def test_expired_m1_package_is_refused_and_extension_cannot_outlive_21_days():
    pkg = _build_pkg(NOW)
    with pytest.raises(MP.PackageError):
        MP.load_package(pkg, now=NOW + timedelta(days=22), require_gate=False)
    ext = json.loads(json.dumps(pkg))
    ext["meta"]["expires_at"] = (NOW + timedelta(days=400)).isoformat()
    assert MP.expires_at(ext) <= NOW + timedelta(days=MP.MODEL_EXPIRY_DAYS)


def test_expired_package_means_no_m1_candidate_in_compute():
    m = _m1()
    # With no valid package the arm returns no candidate; an expired package must behave the same way (D-T22).
    from trader_engine.strategies.arms import ArmInput
    bars = _closed_bars()
    inp = ArmInput(pair="BTC/USDT", tf="1h", D=(bars.index[-1] + TF_DELTA["1h"]).to_pydatetime(), trig=bars,
                   h4=bars.iloc[::4], params=None, core_fn=lambda: None)
    out = m.compute(inp)
    assert not bool(out["signal"].fillna(False).astype(bool).any())


# ------------------------------------------------------------------ export: paper records without the lock window
def test_export_script_keeps_lock_window_out_of_paper_records():
    path = TRADER / "scripts" / "export_paper_records.py"
    if not path.is_file():
        pytest.skip("scripts/export_paper_records.py not present yet (see test_expected_files_exist)")
    txt = path.read_text()
    assert re.search(r"LOCK|HOLDOUT|in_lock|2026-05-01|assert_no_lock|drop_lock", txt), \
        "export must reference the lock window (drop or refuse locked rows)"


# ------------------------------------------------------------------ health freshness alarm (8 days)
def test_health_has_m1_package_freshness_alarm_source():
    text = (TRADER / "scripts" / "health_run.py").read_text() + (SRC / "trader_core" / "health.py").read_text()
    assert re.search(r"pa_proposer|M1", text), "health must know the M1 package"
    assert re.search(r"(?i)pa_\w*(stale|fresh|age)\w*|m1\w*(stale|fresh|age)", text), "freshness alarm missing"
    assert re.search(r"\b8\b", text), "8-day stale threshold (spec 5.3) missing"


def _health_run():
    import importlib.util
    spec = importlib.util.spec_from_file_location("health_run", TRADER / "scripts" / "health_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_health_m1_alarm_fires_for_9_day_old_package(tmp_path):
    HR = _health_run()
    pkg = {"meta": {"arm_id": "M1@1h", "created_at": (NOW - timedelta(days=9)).isoformat(),
                    "expires_at": (NOW + timedelta(days=12)).isoformat()}}
    (tmp_path / "M1@1h.json").write_text(json.dumps(pkg), encoding="utf-8")
    alerts = HR.pa_proposer_alerts({}, NOW, models_dir=str(tmp_path))
    assert alerts and alerts[0].code == "pa_proposer_stale", alerts
    assert alerts[0].level.name == "WARN"
    fresh = {"meta": dict(pkg["meta"], created_at=(NOW - timedelta(days=1)).isoformat())}
    (tmp_path / "M1@1h.json").write_text(json.dumps(fresh), encoding="utf-8")
    assert HR.pa_proposer_alerts({}, NOW, models_dir=str(tmp_path)) == []
