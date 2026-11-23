"""Tarif tanimlari (ML-1, on kayit docs/ml/r02-r03-on-kayit.md 3-7): r01 / r02 / r03 tek yerde, dondurulmus.

r01 = mevcut config varsayilanlari (davranis DEGISMEZ; ozellik listesi tablodaki tum f_* sutunlari, sirali: `features=()`).
r02/r03: ad ad ozellik listesi, etiket sutunlari, agirlik, Platt, LightGBM ayari, yuruyen pencere, kaynak eslemesi.
Bu modul config sabitlerini DEGISTIRMEZ; yalniz okur.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import config
from .features_v2 import R02_FEATURE_NAMES, R03_FEATURE_NAMES

R02_ID = "ml1-r02-long-ctx-1r"
R03_ID = "ml1-r03-long-regime8"
CORPUS_V2_START = pd.Timestamp("2021-01-01", tz="UTC")
CORPUS_V2_END = pd.Timestamp("2026-05-01", tz="UTC")           # dislayici = kilitli donem baslangici


@dataclass(frozen=True)
class Recipe:
    id: str
    features: tuple                       # sirali ozellik listesi; () = tablodaki tum f_* (r01)
    label_col: str
    label_end_col: str
    weight_scheme: str
    platt_nonneg: bool
    lgbm_params: dict = field(default_factory=dict)
    logit_params: dict = field(default_factory=dict)
    wf: dict = field(default_factory=dict)        # make_folds kwarg'lari: start,end,train_bars,test_bars,step_bars,min_test_bars
    source_map: dict = field(default_factory=dict)  # derlem source -> agirlik tablosu source
    limits: dict = field(default_factory=dict)      # apply_limits kwarg'lari (tarife ozgu); {} = config varsayilanlari (r01, degismez)


def _r01() -> Recipe:
    """Config'in O ANKI degerlerinden r01 (None tarif = bu; testler config'i monkeypatch edebilir)."""
    return Recipe(
        id=config.RECIPE_ID, features=(), label_col="label", label_end_col="label_end_ts",
        weight_scheme=config.WEIGHT_SCHEME, platt_nonneg=config.PLATT_NONNEG_SLOPE,
        lgbm_params=dict(config.LGBM_PARAMS), logit_params=dict(config.LOGIT_PARAMS),
        wf={"start": config.DATA_START, "end": config.EGITIM_KESIMI, "train_bars": config.TRAIN_BARS,
            "test_bars": config.TEST_BARS, "step_bars": config.STEP_BARS, "min_test_bars": config.MIN_TEST_BARS},
        source_map={})


def default_recipe() -> Recipe:
    return _r01()


_WF_V2 = {"start": CORPUS_V2_START, "end": CORPUS_V2_END, "train_bars": 8784, "test_bars": 9456,
          "step_bars": 9456, "min_test_bars": 9456}


# r02/r03 kaynak limitleri (olcum: docs/sunucu-kurulum.md "Kaynak limitleri"). 450 MB (r01) derlem v2 boyutunda (~5,5 bin satir)
# bile RLIMIT_DATA'yi asar (MemoryError; tek izinli yeniden baslatma yanar). Tepe RSS ~ 140 + 0,05 MB x satir (kapi bootstrap'i);
# 1200 MB ~ 16 bin satira kadar yeter. CPU: olculen 5-10 sn; 1200 sn (20 dk) 100x+ pay, degismedi.
V2_LIMITS = {"mem_mb": 1200, "cpu_seconds": 1200}


def _v2(rid: str, feats, lgbm: dict) -> Recipe:
    return Recipe(
        id=rid, features=tuple(feats), label_col="label_1r", label_end_col="label_end_ts_1r",
        weight_scheme="uniq_decay", platt_nonneg=True, lgbm_params=lgbm, logit_params=dict(config.LOGIT_PARAMS),
        wf=dict(_WF_V2), source_map={"native_v1b": "backtest"}, limits=dict(V2_LIMITS))


R03_LGBM_PARAMS = {**config.LGBM_PARAMS, "max_depth": 2, "num_leaves": 4, "min_data_in_leaf": 100}

RECIPES: dict[str, Recipe] = {
    config.RECIPE_ID: _r01(),
    R02_ID: _v2(R02_ID, R02_FEATURE_NAMES, dict(config.LGBM_PARAMS)),
    R03_ID: _v2(R03_ID, R03_FEATURE_NAMES, R03_LGBM_PARAMS),
}


def get(recipe_id: str) -> Recipe:
    try:
        return RECIPES[recipe_id]
    except KeyError:
        raise KeyError(f"bilinmeyen tarif: {recipe_id!r} (bilinenler: {sorted(RECIPES)})") from None
