"""Olcum testleri icin ortak sentetik gorunum (1 dk serisinden 15 dk / 1 sa / 4 sa) ve islem kaydi yardimcilari."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

D0 = pd.Timestamp("2026-11-10 08:00", tz="UTC")
_DELTA = {"1m": pd.Timedelta(minutes=1), "15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}


def seri_1dk(fiyatlar, start=D0, genislik=0.05) -> pd.DataFrame:
    """Kapanis dizisinden 1 dk mumlari: acilis = onceki kapanis; high/low = +-genislik."""
    c = np.asarray(fiyatlar, float)
    o = np.concatenate([[c[0]], c[:-1]])
    idx = pd.date_range(start, periods=len(c), freq="1min", tz="UTC")
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + genislik, "low": np.minimum(o, c) - genislik, "close": c, "volume": 1.0}, index=idx)


def seri_bos(df: pd.DataFrame, dakikalar) -> pd.DataFrame:
    return df.drop(index=[df.index[0] + pd.Timedelta(minutes=m) for m in dakikalar])


class Gorunum:
    def __init__(self, m1: dict[str, pd.DataFrame]):
        self.m1 = m1
        self.cagri = 0

    def _tf(self, pair, tf):
        df = self.m1[pair]
        if tf == "1m":
            return df
        return df.resample(_DELTA[tf], label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

    def bars(self, pair, tf, until, n=None, kind="last"):
        self.cagri += 1
        df = self._tf(pair, tf)
        df = df[(df.index + _DELTA[tf]) <= pd.Timestamp(until)]
        return (df.tail(n) if n else df).copy()

    def funding(self, pair, a, b):
        return []


def islem(tid=1, *, setup="R1", side="long", tf="1h", stop=99.0, target=102.0, entry_ref=100.0, r_net=1.0, y=1, exit_reason="target",
          decision_ts=D0, exit_ts=None, **kw) -> dict:
    d = {"trade_id": tid, "decision_id": 100 + tid, "k": f"BTC/USDT|{setup}@{tf}|{side}|{decision_ts.isoformat()}", "decision_ts": decision_ts.isoformat(),
         "pair": "BTC/USDT", "tf": tf, "setup": setup, "arm_id": f"{setup}@{tf}", "group": "G", "side": side, "entry_ref": entry_ref, "stop": stop,
         "target": target, "stop_dist_atr": 1.0, "oz": 2, "exit_ts": (exit_ts or decision_ts + pd.Timedelta(hours=2)).isoformat(), "y": y, "r_net": r_net,
         "exit_reason": exit_reason}
    d.update(kw)
    return d


def sahte_ogren(*gercek, sanal_agirlik=1.0):
    return SimpleNamespace(gercek={int(g["trade_id"]): g for g in gercek}, sanal_agirlik=sanal_agirlik)
