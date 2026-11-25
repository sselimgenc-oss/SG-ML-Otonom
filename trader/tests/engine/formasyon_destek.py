"""24.11 kullanici karari: formasyon kutuphanesi testleri icin ortak yardimcilar (zikzak serisi, rastgele yuruyus, referans yukleyici)."""
from __future__ import annotations

import importlib
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader_core import indicators as I
from trader_engine.strategies import arms
from trader_engine.strategies.arms import m1 as M1MOD

ROOT = Path(__file__).resolve().parents[2]
KAL = 200.0            # short aynasi: gercek fiyat = KAL - long fiyati (pozitif kalsin)


def zig(start, legs, eps=0.1):
    """Parcali dogrusal seri: legs = [(hedef_kapanis, mum_sayisi)]. Yukari mum ust fitil eps, asagi mum alt fitil eps tasir (tepe/dip KESIN).
    -> (mumlar [(o,h,l,c)], her ayagin son mum indeksi)."""
    bars, wp, prev = [], [], float(start)
    for hedef, n in legs:
        a = prev
        for k in range(1, n + 1):
            c = a + (hedef - a) * k / n
            o = prev
            bars.append((o, c + eps if c >= o else o, o if c >= o else c - eps, c))
            prev = c
        wp.append(len(bars) - 1)
    return bars, wp


def df_of(bars, short=False, freq="1h", kal=None):
    arr = np.array(bars, float)
    if short:
        k = KAL if kal is None else kal
        arr = np.column_stack([k - arr[:, 0], k - arr[:, 2], k - arr[:, 1], k - arr[:, 3]])
    idx = pd.date_range("2026-01-01", periods=len(arr), freq=freq, tz="UTC")
    return pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3], "volume": 1.0}, index=idx)


def bozan(bars):
    """Son mumu onceki kapanista doji ile degistirir (kirilim / kesisim / donus kosulunu bozar)."""
    b = list(bars)
    c = b[-2][3]
    b[-1] = (c, c + 0.05, c - 0.05, c)
    return b


def core_inp(df, pair="BTC/USDT", tf="1h", side=None):
    return arms.ArmInput(pair=pair, tf=tf, D=df.index[-1].to_pydatetime() + timedelta(hours=1), trig=df, h4=None, params=None,
                         core_fn=lambda: M1MOD.empty_output(df.index), side=side)


def rw(n, seed, vol=0.012, hacim=False):
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    o = np.concatenate(([100.0], c[:-1])) * np.exp(rng.normal(0, vol / 3, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    if hacim:
        return o, h, l, c, rng.lognormal(0, 0.6, n)
    return o, h, l, c


def atr_of(o, h, l, c):
    return I.atr(pd.DataFrame({"high": h, "low": l, "close": c}), 14).to_numpy(dtype=float)


def referans():
    d = str(ROOT / "tests" / "fixtures" / "formasyon_ref")
    sys.path.insert(0, d)
    try:
        for m in ("gostergeler", "setuplar_v3"):
            sys.modules.pop(m, None)
        return importlib.import_module("setuplar_v3")
    finally:
        sys.path.remove(d)


def tara(mod, kod, o, h, l, c, atr, bas=40, son=None, v=None, gun=None):
    """{(t, yon): sonuc} her `t` icin iki yon (long uzayi; short = aynali gorunum). Gorunum tum diziyle kurulur, `t` degisir
    (dedektor yalniz <= t okur)."""
    from trader_engine.strategies.arms import _kutuphane as K
    son = len(c) - 1 if son is None else son
    gl = K.Gorunum(o, h, l, c, atr, 0, v, gun)
    gs = K.Gorunum(-o, -l, -h, -c, atr, 0, v, gun)
    f = mod.FORMASYONLAR[kod].bul
    out = {}
    for t in range(bas, son + 1):
        for yon, g in ((1, gl), (-1, gs)):
            g.t = t
            r = f(g)
            if r is not None:
                out[(t, yon)] = r
    return out
