"""Purged walk-forward (§3.3 adim 2): genisleyen pencere, >= 8 ay egitim, 2 ay test, 2 ay kaydirma.

Bolme, SAAT IZGARASI uzerinde trader_core.stats.walk_forward_splits ile yapilir (purge = 72 mum
etiket ufku, embargo = 24 mum); adaylar acilis mumlarinin izgara konumuyla dilimlere atanir. Boylece
ayni mumdaki birden cok cift ayni kumeye duser. Ek olarak egitim satirlarindan label_end_ts testin
embargo oncesi baslangicina tasanlar atilir.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core.stats import walk_forward_splits

from .config import (BAR, DATA_START, EMBARGO_BARS, EGITIM_KESIMI, HORIZON_BARS, MIN_TEST_BARS, STEP_BARS,
                     TEST_BARS, TRAIN_BARS)
from .guards import assert_pre_holdout


def make_folds(table: pd.DataFrame, *, train_bars: int = TRAIN_BARS, test_bars: int = TEST_BARS,
               step_bars: int = STEP_BARS, min_test_bars: int = MIN_TEST_BARS, start=DATA_START,
               end=EGITIM_KESIMI) -> list[dict]:
    """[{fold, train_rows, test_rows, test_start, test_end}] (satir = table'in konumsal indeksi)."""
    assert_pre_holdout(table["ts"], "aday tablosu")
    n = int((end - start) / BAR)
    splits = walk_forward_splits(n, train_bars, test_bars, step_bars, anchored=True, purge=HORIZON_BARS,
                                 embargo=EMBARGO_BARS, min_test=min_test_bars)
    pos = ((table["ts"] - BAR - start) / BAR).to_numpy().round().astype(np.int64)
    ends = table["label_end_ts"].to_numpy("datetime64[ns]")
    out = []
    for k, (tr, te) in enumerate(splits):
        t0 = start + int(te[0]) * BAR
        tr_rows = np.flatnonzero((pos >= tr[0]) & (pos <= tr[-1]) & (ends < (t0 - EMBARGO_BARS * BAR).tz_convert(None).to_datetime64()))
        te_rows = np.flatnonzero((pos >= te[0]) & (pos <= te[-1]))
        out.append({"fold": k, "train_rows": tr_rows, "test_rows": te_rows,
                    "test_start": t0, "test_end": start + (int(te[-1]) + 1) * BAR})
    return out
