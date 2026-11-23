"""Sentetik aday tablosu (19b hazir olana dek uctan uca kosu ve testler icin).

Sentetik 1s mumlar -> gercek trader_core rejim/sinyal cekirdegi -> aday satirlari -> ozellik ->
uclu bariyer etiketi. 19b gercek tabloyu ayni semada (schema.py) verince `load_candidates` onu okur;
bu dosya o zaman yalniz test fixture'i olarak kalir. `net_r` burada BASIT referans cikistir
(labels.label_candidates); 19b'de backtester'in gercek cikis kuralidir.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BAR, DATA_START, EGITIM_KESIMI
from trader_core.ml_features import INCLUDE_ENGINE_CONTEXT_FEATURES

from .features import BTC, ETH, add_bars_since_exit, candidate_rows, feature_frame
from .labels import label_candidates
from .schema import validate_candidates

DEFAULT_PAIRS = (BTC, ETH, "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT")


def synthetic_candles(pairs=DEFAULT_PAIRS, start=DATA_START, end=EGITIM_KESIMI, seed: int = 11) -> dict[str, pd.DataFrame]:
    """Rejim degistiren drift + ortak piyasa faktoru. end DISLAYICI (kilitli doneme girilmez)."""
    idx = pd.date_range(start, end - BAR, freq="1h", tz="UTC") if start.tzinfo else \
        pd.date_range(start, end - BAR, freq="1h")
    n = len(idx)
    rng = np.random.default_rng(seed)

    def drift_path(scale: float) -> np.ndarray:
        d = np.zeros(n)
        i = 0
        while i < n:
            L = int(rng.integers(80, 500))
            d[i:i + L] = rng.choice([-1.0, 0.0, 0.0, 1.0]) * scale
            i += L
        return d

    def vol_path() -> np.ndarray:
        v = np.zeros(n)
        i = 0
        while i < n:
            L = int(rng.integers(100, 400))
            v[i:i + L] = rng.choice([0.6, 1.0, 1.0, 1.8])
            i += L
        return v

    mkt_drift, mkt_vol = drift_path(0.00025), vol_path()
    mkt_noise = rng.normal(0, 0.004, n)
    out = {}
    for k, p in enumerate(pairs):
        own = rng.normal(0, 0.004, n)
        beta = 0.9 if k == 0 else rng.uniform(0.5, 1.1)
        r = mkt_drift * beta + (beta * mkt_noise + (1 - beta * 0.5) * own) * mkt_vol
        close = 100.0 * (1 + 10 * k) * np.exp(np.cumsum(r))
        open_ = np.concatenate([[close[0]], close[:-1]])
        wick = np.abs(rng.normal(0, 0.0025, (2, n))) * mkt_vol
        high = np.maximum(open_, close) * (1 + wick[0])
        low = np.minimum(open_, close) * (1 - wick[1])
        out[p] = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                               "volume": rng.uniform(1e3, 1e4, n)}, index=idx)
    return out


def build_candidate_table(candles: dict[str, pd.DataFrame], *, source: str = "backtest",
                          seed: int = 3) -> pd.DataFrame:
    """Mumlardan aday tablosu (19b'nin donecegi sema): ozellik + etiket + referans net R."""
    btc, eth = candles.get(BTC), candles.get(ETH)
    parts = []
    for pair, df in candles.items():
        rows = candidate_rows(feature_frame(df, btc, eth), pair)
        if rows.empty:
            continue
        lab = label_candidates(df, rows)
        rows = pd.concat([rows, lab], axis=1)
        parts.append(rows[rows["label"].notna() & rows["net_r"].notna()])
    t = pd.concat(parts, ignore_index=True)
    rng = np.random.default_rng(seed)
    t["source"] = source
    t["taken"] = rng.random(len(t)) < 0.8
    t.loc[~t["taken"], "exit_ts"] = pd.NaT                 # alinmayanin gercek cikisi yok
    t = t.sort_values(["ts", "pair"], kind="mergesort").reset_index(drop=True)
    if INCLUDE_ENGINE_CONTEXT_FEATURES:                    # karar 2a: motor baglami gelene dek aktif listede yok
        t = add_bars_since_exit(t)
    return validate_candidates(t)
