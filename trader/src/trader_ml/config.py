"""Donmus sabitler (tasarim §1, §3.1-3.4, §6). Esikler sonuc gorulduktan sonra gevsetilmez."""
from __future__ import annotations

import pandas as pd

# --- kilitli donem (§3.1): kilit kapaliyken egitim kodu bu tarihten itibaren veriyi OKUMAZ.
# 23.11.2026 KULLANICI KARARI: kilit ACIK (trader_engine.holdout.KILIT_ACIK'in kopyasi; esitlik testle denetlenir). Tarih sabitleri
# kayit/rapor icin kalir; davranis yalniz KILIT_ACIK'a baglidir.
KILIT_ACIK = True
HOLDOUT_START = pd.Timestamp("2026-05-01", tz="UTC")
HOLDOUT_END = pd.Timestamp("2026-11-01", tz="UTC")          # dislayici; 2026-05 -> 2026-10
# egitim/walk-forward kesimi (dislayici): kilit kapaliyken HOLDOUT_START, acikken veri sonu (= HOLDOUT_END, 2026-10-31 son bar)
EGITIM_KESIMI = HOLDOUT_END if KILIT_ACIK else HOLDOUT_START
DATA_START = pd.Timestamp("2024-12-21", tz="UTC")           # isinma sonrasi fiili baslangic (§3.3)

# --- etiket (§3.1)
TARGET_R = 2.0
HORIZON_BARS = 72                    # 1 saatlik mum
EMBARGO_BARS = 24
BAR = pd.Timedelta(hours=1)
FEE_RATE = 0.0005                    # taraf basina (risk.RiskConfig ile ayni)
SLIPPAGE_RATE = 0.0005               # taraf basina
EXIT_TIME_STOP_BARS = 48             # signals.TIME_STOP_BARS: referans cikis (sentetik net_r)

# --- ozellik (§3.2)
MAX_FEATURES = 40

# --- kaynak agirliklari (§3.3 adim 1) ve yasa gore azalma
SOURCE_WEIGHTS = {"real": 1.0, "paper": 0.7, "counterfactual": 0.5, "backtest": 0.3}
AGE_HALF_LIFE_DAYS = 270.0

# --- yuruyen pencere (§3.3 adim 2): >= 8 ay egitim, 2 ay test, 2 ay kaydirma
TRAIN_BARS = 240 * 24
TEST_BARS = 60 * 24
STEP_BARS = 60 * 24
MIN_TEST_BARS = 30 * 24

# --- esik ve kapi (§1, §3.3 adim 4, §3.4) -- DONDURULDU
THRESHOLD_GRID = tuple(round(0.45 + 0.01 * i, 2) for i in range(26))   # 0.45 .. 0.70
MIN_TAKEN_FRAC = 0.30
BURN_IN_THRESHOLD = 0.50             # ilk dilim: gecmis yok -> onceden yazili sabit esik (veriyle uydurulmaz)
GATE = {
    "ic_min_t": 2.0, "required_folds": 4, "ic_min_pos_folds": 3,
    "delta_net_r_min": 0.10, "bootstrap_alpha_two_sided": 0.20,      # %90 tek tarafli alt sinir
    "filtered_expectancy_min": 0.0, "dsr_min": 0.95, "pbo_max": 0.25,
    "min_taken_frac": MIN_TAKEN_FRAC, "stress_expectancy_min": -0.05,
    "stress_fee_mult": 2.0, "stress_extra_bp_per_side": 5.0, "parity_tol": 1e-9,
    "holm_alpha": 0.10,
}

# --- model paketi (§3.3 adim 5, §3.6)
from trader_core.ml_package import MODEL_EXPIRY_DAYS  # noqa: E402,F401  (tek kaynak: motor tarafi)

# --- kaynak plani (§6)
TRAIN_MEM_CAP_MB = 450
TRAIN_NICE = 19
TRAIN_THREADS = 1
TRAIN_TIME_LIMIT_S = 20 * 60

# --- sabit tarif (§3.3 adim 3)
LGBM_PARAMS = {
    "objective": "binary", "max_depth": 4, "num_leaves": 15, "min_data_in_leaf": 50,
    "learning_rate": 0.05, "n_estimators_max": 300, "early_stopping_rounds": 30,
    "feature_fraction": 1.0, "bagging_fraction": 1.0, "lambda_l2": 1.0,
    "num_threads": TRAIN_THREADS, "deterministic": True, "force_row_wise": True,
    "seed": 7, "verbosity": -1,
}
WEIGHT_SCHEME = "age_decay"           # ML-G2: r01 = kaynak x yasa gore ussel azalma; "uniq_decay" = weights.sample_weights_v2
PLATT_NONNEG_SLOPE = False            # ML-G2: True -> Platt egimi >= 0 (opt-in)
LOGIT_PARAMS = {"l2": 1.0, "max_iter": 100}
RECIPE_ID = "ml1-r01-v1b-native33"
