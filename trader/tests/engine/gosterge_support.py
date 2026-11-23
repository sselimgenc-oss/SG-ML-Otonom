"""Gosterge parite / olu mum testleri icin ortak sentetik veri (ag yok, tohumlu, deterministik).

Uretilen seriler: rejim degisimli (yukselis/dusus/aralik/patlama) 15 dakikalik OHLCV; kripto 7/24; seansli hisse (Pzt-Cum 13:30-20:00 UTC)
olu mumlu (hacim 0, o=h=l=c) ya da mumsuz (bar yok); emtia (Pazar 23:00 - Cuma 22:00 UTC) hafta sonu olu mumlu. 1s/4s mumlar 15 dakikalikten
toplanir (market.sqlite ve feather ayni mumlari tasir)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

UTC = timezone.utc
COLS = ["open", "high", "low", "close", "volume"]


def make_15m(seed: int, n: int, start: datetime, p0: float = 100.0) -> pd.DataFrame:
    """Rejim degisimli sentetik 15 dk mumlari (yukselis/dusus/aralik/patlama bolumleri)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    r = np.zeros(n)
    i = 0
    while i < n:
        seg_n = min(int(rng.integers(150, 700)), n - i)
        mode = rng.choice(["up", "down", "range", "burst"], p=[.3, .25, .3, .15])
        sig = {"up": .0016, "down": .0016, "range": .0012, "burst": .0045}[mode] * rng.uniform(.8, 1.3)
        mu = {"up": .00035, "down": -.00035, "range": 0.0, "burst": 0.0}[mode]
        seg = rng.normal(mu, sig, seg_n)
        if mode == "range":
            x, acc = 0.0, []
            for e in seg:
                x = 0.92 * x + e
                acc.append(x)
            seg = np.diff(np.concatenate([[0.0], acc]))
        r[i:i + seg_n] = seg
        i += seg_n
    close = p0 * np.exp(np.cumsum(r))
    op = np.concatenate([[p0], close[:-1]])
    hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0007, n)))
    lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0007, n)))
    vol = rng.uniform(100, 500, n)
    return pd.DataFrame({"open": np.round(op, 4), "high": np.round(hi, 4), "low": np.round(lo, 4),
                         "close": np.round(close, 4), "volume": np.round(vol, 2)}, index=idx)


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.resample(rule)
    return pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                         "close": g["close"].last(), "volume": g["volume"].sum()}).dropna()


def _session_series(seed: int, days: int, start: datetime, in_session, p0: float, flat: bool) -> pd.DataFrame:
    """Seansli enstruman: seans mumlari dolu; seans disi `flat=True` -> olu mum (hacim 0, o=h=l=c=son kapanis), `False` -> bar YOK.
    Her seans acilisinda fiyat bosluğu (gap) vardir."""
    grid = pd.date_range(start, periods=days * 96, freq="15min", tz="UTC")
    sess = np.asarray(in_session(grid), dtype=bool)
    n_s = int(sess.sum())
    core = make_15m(seed, n_s, start, p0)
    rng = np.random.default_rng(seed + 99)
    day_of = pd.Series(grid[sess].normalize())
    first = (day_of != day_of.shift(1)).to_numpy()
    f = np.cumprod(np.where(first, np.exp(rng.normal(0, 0.008, n_s)), 1.0))
    O = np.full(len(grid), np.nan)
    H, Lw, C, V = O.copy(), O.copy(), O.copy(), np.zeros(len(grid))
    O[sess], H[sess], Lw[sess], C[sess], V[sess] = (core["open"].to_numpy() * f, core["high"].to_numpy() * f,
                                                   core["low"].to_numpy() * f, core["close"].to_numpy() * f,
                                                   core["volume"].to_numpy())
    last = np.nan
    for i in range(len(grid)):
        if sess[i]:
            last = C[i]
        elif flat and not np.isnan(last):
            O[i] = H[i] = Lw[i] = C[i] = last
    df = pd.DataFrame({"open": O, "high": H, "low": Lw, "close": C, "volume": V}, index=grid).dropna().round(4)
    return df


def stock_session(grid) -> np.ndarray:
    mins = grid.hour * 60 + grid.minute
    return (grid.dayofweek < 5) & (mins >= 13 * 60 + 30) & (mins < 20 * 60)


def commodity_session(grid) -> np.ndarray:
    """Pazar 23:00 UTC -> Cuma 22:00 UTC (hafta sonu disinda hep acik)."""
    dow, hr = grid.dayofweek, grid.hour
    closed = ((dow == 5) | ((dow == 4) & (hr >= 22)) | ((dow == 6) & (hr < 23)))
    return ~closed


def make_stock_15m(seed: int, days: int, start: datetime, p0: float = 150.0, flat: bool = True) -> pd.DataFrame:
    return _session_series(seed, days, start, stock_session, p0, flat)


def make_commodity_15m(seed: int, days: int, start: datetime, p0: float = 2000.0, flat: bool = True) -> pd.DataFrame:
    return _session_series(seed, days, start, commodity_session, p0, flat)


def tf_frames(df15: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {"15m": df15, "1h": resample(df15, "1h"), "4h": resample(df15, "4h")}


def write_store(db: Path, series: dict[str, pd.DataFrame], now: datetime) -> None:
    """Gercek `MarketStore` (canli okuyucu `StoreSource` icin): her cift icin 15m/1h/4h `last` mumlari."""
    from trader_engine.bars import to_ms
    from trader_engine.marketdata.store import MarketStore
    from trader_engine.types import Bar
    st = MarketStore(db)
    try:
        for pair, df15 in series.items():
            for tf, g in tf_frames(df15).items():
                arr = g[COLS].to_numpy(dtype=float)
                bars = [Bar(pair, "last", tf, ts.to_pydatetime(), *map(float, r)) for ts, r in zip(g.index, arr)]
                for c in range(0, len(bars), 20000):
                    st.put_bars(bars[c:c + 20000], now_ms=to_ms(now))
    finally:
        st.close()


def write_feather(hist: Path, series: dict[str, pd.DataFrame]) -> None:
    """Geri test kaynagi (`HistoricalSource`): `<PAIR>_USDT_USDT-<tf>-futures.feather` (ayni mumlar)."""
    import pyarrow as pa
    import pyarrow.feather as pf
    hist.mkdir(parents=True, exist_ok=True)
    for pair, df15 in series.items():
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        for tf, g in tf_frames(df15).items():
            arrs = {"date": pa.array(g.index.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
            for c in COLS:
                arrs[c] = pa.array(g[c].to_numpy(dtype="float64"))
            pf.write_feather(pa.table(arrs), str(hist / f"{stem}-{tf}-futures.feather"), compression="uncompressed")
