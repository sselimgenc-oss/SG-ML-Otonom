"""Gostergeler (numpy; kendi kodumuz): EMA, ATR (Wilder), RSI (Wilder), MACD, pivot. Hepsi nedensel: t anindaki deger yalniz <= t verisinden."""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def sma_tohumlu_ozyinelemeli(x: np.ndarray, n: int, alfa: float) -> np.ndarray:
    """Ilk gecerli n degerin ortalamasi ile tohumla, sonra y = y + alfa*(x-y). Basta NaN olabilir (ilk gecerli yerden sayilir)."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) == 0:
        return out
    s = ok[0]
    if len(x) - s < n:
        return out
    y = float(np.mean(x[s:s + n]))
    out[s + n - 1] = y
    for i in range(s + n, len(x)):
        y += alfa * (x[i] - y)
        out[i] = y
    return out


def ema(x, n: int) -> np.ndarray:
    return sma_tohumlu_ozyinelemeli(x, n, 2.0 / (n + 1))


def gercek_aralik(h, l, c) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]
    return tr


def atr(h, l, c, n: int = 14) -> np.ndarray:
    """Wilder ATR: ilk n TR ortalamasi, sonra (onceki*(n-1)+TR)/n."""
    return sma_tohumlu_ozyinelemeli(gercek_aralik(np.asarray(h, float), np.asarray(l, float), np.asarray(c, float)), n, 1.0 / n)


def rsi(c, n: int = 14) -> np.ndarray:
    """Wilder RSI: ilk n degisimin ortalamasi ile tohum, sonra Wilder duzeltme."""
    c = np.asarray(c, dtype=float)
    d = np.diff(c)
    kazanc = np.maximum(d, 0.0)
    kayip = np.maximum(-d, 0.0)
    ag = sma_tohumlu_ozyinelemeli(kazanc, n, 1.0 / n)
    al = sma_tohumlu_ozyinelemeli(kayip, n, 1.0 / n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = ag / al
        r = np.where(al == 0, np.where(ag == 0, 50.0, 100.0), 100.0 - 100.0 / (1.0 + rs))
    r = np.where(np.isnan(ag), np.nan, r)
    return np.r_[np.nan, r]


def macd(c, hizli: int = 12, yavas: int = 26, sinyal: int = 9):
    """(macd, sinyal, histogram)."""
    m = ema(c, hizli) - ema(c, yavas)
    s = ema(m, sinyal)
    return m, s, m - s


def pivot_dip(l, sol: int = 5, sag: int = 3) -> np.ndarray:
    """i pivot dip: l[i] sol 'sol' mumun hepsinden kesin dusuk ve sag 'sag' mumun hepsinden <= . Pivot i'de isaretlenir ama ANCAK i+sag kapanisinda
    bilinir (kullanan taraf kesinlesme gecikmesini uygulamak zorunda: bkz. kesinlesmis_son)."""
    l = np.asarray(l, float)
    n = len(l)
    out = np.zeros(n, bool)
    if n < sol + sag + 1:
        return out
    pen_sol = sliding_window_view(l, sol)          # pen_sol[k] = l[k..k+sol-1]
    pen_sag = sliding_window_view(l, sag)
    idx = np.arange(sol, n - sag)
    sol_min = pen_sol[idx - sol].min(axis=1)
    sag_min = pen_sag[idx + 1].min(axis=1)
    out[idx] = (l[idx] < sol_min) & (l[idx] <= sag_min)
    return out


def pivot_tepe(h, sol: int = 5, sag: int = 3) -> np.ndarray:
    return pivot_dip(-np.asarray(h, float), sol, sag)


def kesinlesmis_son(piv: np.ndarray, deger: np.ndarray, sag: int = 3):
    """Her t icin t'de bilinen (idx <= t-sag) son pivotun (indeksi, degeri). Yoksa (-1, nan)."""
    n = len(piv)
    bilinen = np.zeros(n, bool)
    bilinen[sag:] = piv[:n - sag]                   # t anindan bilinen: pivot t-sag'de
    kaynak = np.where(bilinen, np.arange(n) - sag, -1)
    son = np.maximum.accumulate(kaynak)
    val = np.where(son >= 0, np.asarray(deger, float)[np.maximum(son, 0)], np.nan)
    return son, val
