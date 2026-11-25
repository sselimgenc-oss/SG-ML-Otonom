"""ML1 testleri icin ortak yardimcilar: sentetik veri (CI de var/history yok): rejim degisen rastgele yuruyus, 4s mumlar."""
from __future__ import annotations

import numpy as np
import pandas as pd

PAIR = "SYN/USDT"
TF = "4h"
STARTUP = 60                       # testte kucuk isinma (uretimde STARTUP_BARS_ARM)


def sentetik(n: int = 1500, seed: int = 7, start: str = "2022-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    drift = np.zeros(n)
    sig = np.zeros(n)
    i = 0
    while i < n:
        L = int(rng.integers(60, 220))
        drift[i:i + L] = rng.choice([-0.0010, 0.0, 0.0, 0.0012])
        sig[i:i + L] = rng.choice([0.004, 0.007, 0.011])
        i += L
    ret = drift + sig * rng.standard_normal(n)
    c = 100.0 * np.exp(np.cumsum(ret))
    o = np.r_[100.0, c[:-1]] * (1 + 0.0005 * rng.standard_normal(n))
    wick = sig * np.abs(rng.standard_normal((2, n))) * 0.6
    h = np.maximum(o, c) * (1 + wick[0])
    l = np.minimum(o, c) * (1 - wick[1])
    v = rng.lognormal(3.0, 0.5, n)
    idx = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)
