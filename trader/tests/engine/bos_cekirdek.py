"""Test yardimcisi: SIGNAL_COLUMNS sutunlu, hic sinyal icermeyen ortak (core) tablo (M1 kolundaki `empty_output` buraya tasindi)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core.signals import SIGNAL_COLUMNS


def empty_output(index) -> pd.DataFrame:
    n = len(index)
    obj = np.full(n, None, dtype=object)
    data = {c: np.full(n, np.nan) for c in SIGNAL_COLUMNS}
    data.update({"setup": obj, "side": obj.copy(), "skip_reason": obj.copy(), "regime": obj.copy(),
                 "reasons": np.full(n, "", dtype=object), "signal": np.zeros(n, dtype=bool),
                 "rh_touches": np.zeros(n, dtype="int64"), "rl_touches": np.zeros(n, dtype="int64"),
                 "pullback_ema": np.zeros(n, dtype="int64")})
    return pd.DataFrame({c: data[c] for c in SIGNAL_COLUMNS}, index=index)[SIGNAL_COLUMNS]
