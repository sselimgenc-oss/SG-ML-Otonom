"""Donmus sabitler (kilit bayragi ve purged walk-forward izgarasi; DL1 egitimi ve M1 gece egitimi kullanir)."""
from __future__ import annotations

import pandas as pd

# --- kilitli donem: kilit kapaliyken egitim kodu bu tarihten itibaren veriyi OKUMAZ.
# 23.11.2026 KULLANICI KARARI: kilit ACIK (trader_engine.holdout.KILIT_ACIK'in kopyasi; esitlik testle denetlenir). Tarih sabitleri
# kayit/rapor icin kalir; davranis yalniz KILIT_ACIK'a baglidir.
KILIT_ACIK = True
HOLDOUT_START = pd.Timestamp("2026-05-01", tz="UTC")
HOLDOUT_END = pd.Timestamp("2026-11-01", tz="UTC")          # dislayici; 2026-05 -> 2026-10
# egitim/walk-forward kesimi (dislayici): kilit kapaliyken HOLDOUT_START, acikken veri sonu (= HOLDOUT_END, 2026-10-31 son bar)
EGITIM_KESIMI = HOLDOUT_END if KILIT_ACIK else HOLDOUT_START
DATA_START = pd.Timestamp("2024-12-21", tz="UTC")           # isinma sonrasi fiili baslangic

# --- etiket ufku
HORIZON_BARS = 72                    # 1 saatlik mum
EMBARGO_BARS = 24
BAR = pd.Timedelta(hours=1)

# --- yuruyen pencere: >= 8 ay egitim, 2 ay test, 2 ay kaydirma
TRAIN_BARS = 240 * 24
TEST_BARS = 60 * 24
STEP_BARS = 60 * 24
MIN_TEST_BARS = 30 * 24
