"""r02/r03 tarifleri (on kayit docs/ml/r02-r03-on-kayit.md 3-7): tarif tablosu, yuruyen pencere, model ayari, boru hatti (sentetik)."""
from __future__ import annotations

import dataclasses
import json

import numpy as np
import pandas as pd
import pytest

from trader_core.ml_features_v2 import R02_FEATURE_NAMES, R03_FEATURE_NAMES
from trader_core.stats import walk_forward_splits
from trader_ml import config, models, pipeline, recipes
from trader_ml.registry import DEFAULT_REGISTRY, n_trials_from_registry
from trader_ml.schema import feature_columns
from trader_ml.walkforward import make_folds

R02, R03 = recipes.R02_ID, recipes.R03_ID


def test_feature_lists_and_ids():
    assert list(recipes.get(R02).features) == list(R02_FEATURE_NAMES) and len(R02_FEATURE_NAMES) == 40
    assert list(recipes.get(R03).features) == list(R03_FEATURE_NAMES) and len(R03_FEATURE_NAMES) == 8
    assert recipes.get(config.RECIPE_ID).id == config.RECIPE_ID
    with pytest.raises(KeyError):
        recipes.get("yok")


def test_every_recipe_in_registry():
    for rid in recipes.RECIPES:
        assert n_trials_from_registry(DEFAULT_REGISTRY, recipe_id=rid) >= 10        # defter: 5 satir x 2 model (en az)


def test_r01_is_current_config():
    r = recipes.get(config.RECIPE_ID)
    assert r.weight_scheme == config.WEIGHT_SCHEME and r.platt_nonneg is config.PLATT_NONNEG_SLOPE
    assert r.lgbm_params == config.LGBM_PARAMS and r.logit_params == config.LOGIT_PARAMS and r.features == ()
    assert r.wf == {"start": config.DATA_START, "end": config.EGITIM_KESIMI, "train_bars": config.TRAIN_BARS,
                    "test_bars": config.TEST_BARS, "step_bars": config.STEP_BARS, "min_test_bars": config.MIN_TEST_BARS}
    assert r.label_col == "label" and r.label_end_col == "label_end_ts" and r.source_map == {}


def test_r02_r03_settings():
    r2, r3 = recipes.get(R02), recipes.get(R03)
    assert r2.lgbm_params == config.LGBM_PARAMS
    diff = {k for k in config.LGBM_PARAMS if r3.lgbm_params[k] != config.LGBM_PARAMS[k]}
    assert diff == {"max_depth", "num_leaves", "min_data_in_leaf"}
    assert (r3.lgbm_params["max_depth"], r3.lgbm_params["num_leaves"], r3.lgbm_params["min_data_in_leaf"]) == (2, 4, 100)
    for r in (r2, r3):
        assert (r.label_col, r.label_end_col) == ("label_1r", "label_end_ts_1r")
        assert r.weight_scheme == "uniq_decay" and r.platt_nonneg is True and r.logit_params == config.LOGIT_PARAMS
        assert r.source_map == {"native_v1b": "backtest"} and r.wf == recipes.get(R02).wf
    assert config.LGBM_PARAMS["max_depth"] == 4 and config.LGBM_PARAMS["num_leaves"] == 15      # sabitler dokunulmadi


def test_walk_forward_exactly_four_folds_with_registered_starts():
    w = recipes.get(R02).wf
    n = int((w["end"] - w["start"]) / config.BAR)
    assert n == 46704 and (w["train_bars"], w["test_bars"], w["step_bars"], w["min_test_bars"]) == (8784, 9456, 9456, 9456)
    splits = walk_forward_splits(n, w["train_bars"], w["test_bars"], w["step_bars"], anchored=True, purge=72, embargo=24,
                                 min_test=w["min_test_bars"])
    assert len(splits) == 4
    assert [str((w["start"] + int(te[0]) * config.BAR).date()) for _, te in splits] == \
        ["2022-01-06", "2023-02-04", "2024-03-04", "2025-04-02"]
    # make_folds ayni pencereyi tarif kwarg'lariyla kullanir (bos tablo bile 4 dilim dondurur)
    ts = pd.date_range(w["start"] + config.BAR, periods=200, freq="1D", tz="UTC")
    t = pd.DataFrame({"ts": ts, "label_end_ts": ts + pd.Timedelta(hours=5)})
    assert len(make_folds(t, **w)) == 4


# ------------------------------------------------------------------ models.fit_lgbm params
def _xy(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 5))
    y = (X[:, 0] + 0.5 * X[:, 1] * X[:, 2] + rng.normal(scale=0.8, size=n) > 0).astype(float)
    return X, y, np.ones(n)


def test_fit_lgbm_default_identical_to_explicit_config():
    pytest.importorskip("lightgbm")
    X, y, w = _xy()
    b0, n0 = models.fit_lgbm(X, y, w)
    b1, n1 = models.fit_lgbm(X, y, w, params=dict(config.LGBM_PARAMS))
    assert n0 == n1 and models.lgbm_dump(b0) == models.lgbm_dump(b1)
    assert b0.model_to_string() == b1.model_to_string()
    f0, _ = models.fit_lgbm(X, y, w, num_rounds=20)
    f1, _ = models.fit_lgbm(X, y, w, num_rounds=20, params=dict(config.LGBM_PARAMS))
    assert f0.model_to_string() == f1.model_to_string()
    assert models._lgb_params() == models._lgb_params(config.LGBM_PARAMS)


def test_fit_lgbm_depth2_trees_have_at_most_4_leaves():
    pytest.importorskip("lightgbm")
    X, y, w = _xy()
    p = recipes.get(R03).lgbm_params
    b, _ = models.fit_lgbm(X, y, w, params=p)
    leaves = [ti["num_leaves"] for ti in models.lgbm_dump(b)["tree_info"]]
    assert leaves and max(leaves) <= 4
    b4, _ = models.fit_lgbm(X, y, w)
    assert max(ti["num_leaves"] for ti in models.lgbm_dump(b4)["tree_info"]) > 4        # r01 daha derin
    pe = dict(p, n_estimators_max=7, early_stopping_rounds=1000)
    b7, best = models.fit_lgbm(X, y, w, params=pe)
    assert b7.num_trees() <= 7                                                            # n_estimators_max params'tan


# ------------------------------------------------------------------ boru hatti (sentetik, tarif secimi)
def _like(base: recipes.Recipe, table: pd.DataFrame, k: int, *, platt_nonneg: bool | None = None) -> recipes.Recipe:
    """r02/r03 AYARLARI (agirlik, LightGBM, Platt), sentetik tablo icin r01 penceresi ve k adet f_* sutunu."""
    base = base if platt_nonneg is None else dataclasses.replace(base, platt_nonneg=platt_nonneg)
    return dataclasses.replace(base, features=tuple(feature_columns(table)[:k]), label_col="label", label_end_col="label_end_ts",
                               wf=recipes.get(config.RECIPE_ID).wf, source_map={})


@pytest.fixture(scope="module")
def r01_summary(table, tmp_path_factory):
    pytest.importorskip("lightgbm")
    return pipeline.run(table, tmp_path_factory.mktemp("r01"), synthetic=True, n_boot=100, n_trials=10)


def test_r01_default_and_explicit_recipe_identical(table, r01_summary, tmp_path):
    s = pipeline.run(table, tmp_path, synthetic=True, n_boot=100, n_trials=10, recipe=recipes.get(config.RECIPE_ID))
    for k in ("passed", "model", "threshold", "parity_max_abs_diff", "checks", "n_oof", "platt_clamped_folds", "weight_scheme"):
        assert s[k] == r01_summary[k], k
    assert s["recipe_id"] == config.RECIPE_ID and r01_summary["recipe_id"] == config.RECIPE_ID


@pytest.mark.parametrize("rid,k", [(R02, 14), (R03, 8)])
def test_pipeline_runs_r02_r03_like(table, tmp_path, monkeypatch, rid, k):
    pytest.importorskip("lightgbm")
    rec = _like(recipes.get(rid), table, k, platt_nonneg=False)    # sentetik gurultude a>=0 paketi reddeder (asagidaki test); burada tam yol
    seen = {}
    real_fit = models.fit_lgbm
    monkeypatch.setattr(pipeline.models, "fit_lgbm", lambda *a, **kw: (seen.setdefault("p", kw.get("params")), real_fit(*a, **kw))[1])
    s = pipeline.run(table, tmp_path, synthetic=True, n_boot=100, n_trials=10, recipe=rec)
    assert s["recipe_id"] == rid and s["weight_scheme"] == "uniq_decay"
    assert seen["p"] == rec.lgbm_params                                   # tarifin LightGBM ayari fit_lgbm'e gecti
    pkg = json.loads((tmp_path / "model_candidate.json").read_text())
    assert pkg["meta"]["version"] == rid and pkg["meta"]["features"] == list(rec.features)
    md = (tmp_path / "gate_report.md").read_text(encoding="utf-8")
    assert "kısıtlanan" in md and rid in md and "uniq_decay" in md
    oof = pd.read_parquet(tmp_path / "oof_predictions.parquet")
    assert oof["fold"].nunique() == 4


def test_calibration_clamped_writes_red_result_no_package(table, tmp_path, monkeypatch):
    pytest.importorskip("lightgbm")
    real = models.fit_platt_info
    monkeypatch.setattr(pipeline.models, "fit_platt_info", lambda z, y, *a, **k: (real(z, y, *a, **k)[0], True))
    rec = _like(recipes.get(R02), table, 10)
    with pytest.raises(pipeline.CalibrationClamped) as ei:
        pipeline.run(table, tmp_path, synthetic=True, n_boot=50, n_trials=10, recipe=rec)
    assert not (tmp_path / "model_candidate.json").exists()
    res = json.loads((tmp_path / "gate_result.json").read_text())
    assert res["passed"] is False and "CalibrationClamped" in res["reason"] and res["recipe_id"] == R02
    assert res["package"] is None and res["oof_metrics"] and (tmp_path / "oof_predictions.parquet").exists()
    md = (tmp_path / "gate_report.md").read_text(encoding="utf-8")
    assert "RED" in md and "Platt" in md and ei.value.summary["passed"] is False
