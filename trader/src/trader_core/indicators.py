# Portions of this file (indicator math and the regime-label interface skeleton)
# are adapted from regime-trading-bot (https://github.com/danny123-sudo/regime-trading-bot,
# commit 508d7d9), licensed under the MIT License.
#
# MIT License
#
# Copyright (c) 2026 danny123-sudo
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Modifications: NaN warm-up, state-carrying NaN policy, label set and all
# classification rules are original to this project (see docs/rejim-spec.md).
"""Gosterge matematigi: EMA, SMA, true range, ATR (Wilder). Yalnizca pandas + numpy.

Formuller ve NaN/isinma kurallari docs/rejim-spec.md ile birebir aynidir.
"""
from __future__ import annotations

import numbers

import numpy as np
import pandas as pd


def _check_length(length) -> int:
    if isinstance(length, bool) or not isinstance(length, numbers.Integral) or int(length) < 1:
        raise ValueError(f"length tam sayi >= 1 olmali: {length!r}")
    return int(length)


def _to_float_series(series, name: str = "series") -> pd.Series:
    if not isinstance(series, pd.Series):
        raise ValueError(f"{name} pandas.Series olmali")
    s = pd.to_numeric(series, errors="coerce").astype("float64")
    if np.isinf(s.to_numpy()).any():
        raise ValueError(f"{name} sonsuz deger iceriyor")
    return s


def _recursive(x: np.ndarray, alpha: float, length: int, wilder: bool = False) -> np.ndarray:
    """e_t = e_{t-1} + alpha*(x_t - e_{t-1}); ilk gercek gozlem tohum; NaN'da durum tasinir."""
    out = np.full(len(x), np.nan)
    state = None
    count = 0
    for i, v in enumerate(x):
        if np.isnan(v):
            continue
        if state is None:
            state = v
        elif wilder:
            state = state + (v - state) / length
        else:
            state = alpha * v + (1.0 - alpha) * state
        count += 1
        if count >= length:
            out[i] = state
    return out


def ema(series: pd.Series, length: int) -> pd.Series:
    length = _check_length(length)
    s = _to_float_series(series)
    alpha = 2.0 / (length + 1)
    return pd.Series(_recursive(s.to_numpy(), alpha, length), index=s.index, name=series.name)


def sma(series: pd.Series, length: int) -> pd.Series:
    length = _check_length(length)
    s = _to_float_series(series)
    return s.rolling(length, min_periods=length).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    if not isinstance(df, pd.DataFrame):
        raise ValueError("df pandas.DataFrame olmali")
    for c in ("high", "low", "close"):
        if c not in df.columns:
            raise ValueError(f"zorunlu sutun yok: {c}")
    high = _to_float_series(df["high"], "high")
    low = _to_float_series(df["low"], "low")
    close = _to_float_series(df["close"], "close")
    prev = close.shift(1)
    parts = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1)
    tr = parts.max(axis=1, skipna=True)
    tr[high.isna() | low.isna()] = np.nan
    tr.name = None
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    length = _check_length(length)
    tr = true_range(df)
    return pd.Series(_recursive(tr.to_numpy(), 1.0 / length, length, wilder=True), index=tr.index)


# ---------------------------------------------------------------------------------------------------------------------
# 24.11 kullanici karari: formasyon kutuphanesi (GF1 grafik + IN1 gostergeler) icin numpy gostergeleri. Yalniz ekleme.
# Hepsi nedensel (t anindaki deger yalniz <= t verisinden); basi NaN. Tohum: ilk n degerin ortalamasi (yeni_kollar/gostergeler.py
# ve setuplar_v3.py ile ayni sonuc; mevcut pandas `ema`/`atr` ilk gozlemle tohumlar, onlara dokunulmaz).
# ---------------------------------------------------------------------------------------------------------------------
def _tohumlu(x, n: int, alfa: float) -> np.ndarray:
    """Ilk gecerli n degerin ortalamasiyla tohumla, sonra y += alfa*(x-y); basta NaN olabilir."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(~np.isnan(x))
    if len(ok) == 0 or len(x) - ok[0] < n:
        return out
    s = int(ok[0])
    y = float(np.mean(x[s:s + n]))
    out[s + n - 1] = y
    for i in range(s + n, len(x)):
        y += alfa * (x[i] - y)
        out[i] = y
    return out


def ema_np(x, n: int) -> np.ndarray:
    return _tohumlu(x, n, 2.0 / (n + 1))


def sma_np(x, n: int) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        from numpy.lib.stride_tricks import sliding_window_view
        out[n - 1:] = sliding_window_view(x, n).mean(axis=1)
    return out


def std_pop(x, n: int) -> np.ndarray:
    """Populasyon standart sapmasi (ddof=0), pencere n (t dahil)."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        from numpy.lib.stride_tricks import sliding_window_view
        out[n - 1:] = sliding_window_view(x, n).std(axis=1)
    return out


def rsi(c, n: int = 14) -> np.ndarray:
    """Wilder RSI (ilk n degisimin ortalamasiyla tohumlu)."""
    c = np.asarray(c, dtype=float)
    d = np.diff(c)
    ag = _tohumlu(np.maximum(d, 0.0), n, 1.0 / n)
    al = _tohumlu(np.maximum(-d, 0.0), n, 1.0 / n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(al == 0, np.where(ag == 0, 50.0, 100.0), 100.0 - 100.0 / (1.0 + ag / al))
    r = np.where(np.isnan(ag), np.nan, r)
    return np.r_[np.nan, r]


def bollinger(c, n: int = 20, k: float = 2.0):
    """(orta, alt, ust): SMA(n) +- k * populasyon std."""
    m = sma_np(c, n)
    sd = std_pop(c, n)
    return m, m - k * sd, m + k * sd


def macd(c, hizli: int = 12, yavas: int = 26, sinyal: int = 9):
    """(macd, sinyal, histogram)."""
    m = ema_np(c, hizli) - ema_np(c, yavas)
    s = _tohumlu(m, sinyal, 2.0 / (sinyal + 1))
    return m, s, m - s


def _pencere(x, n: int, fn: str) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        from numpy.lib.stride_tricks import sliding_window_view
        w = sliding_window_view(x, n)
        out[n - 1:] = w.max(axis=1) if fn == "max" else w.min(axis=1)
    return out


def stoch(h, l, c, n: int = 14, k: int = 3, d: int = 3):
    """Yavas stokastik: ham %K = 100*(c-LL)/(HH-LL); %K = SMA(k) ham; %D = SMA(d) %K. (K, D)."""
    c = np.asarray(c, dtype=float)
    hh, ll = _pencere(h, n, "max"), _pencere(l, n, "min")
    with np.errstate(invalid="ignore", divide="ignore"):
        ham = np.where(hh - ll > 0, 100.0 * (c - ll) / (hh - ll), np.nan)
    sk = sma_np(ham, k)
    return sk, sma_np(sk, d)


def ichimoku(h, l, c, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52):
    """(tenkan, kijun, span_a, span_b); bulut degerleri `t`de CIZILEN deger: t-kijun ve oncesinin verisinden (ileri kaydirma)."""
    h = np.asarray(h, dtype=float)
    l = np.asarray(l, dtype=float)
    tk = (_pencere(h, tenkan, "max") + _pencere(l, tenkan, "min")) / 2.0
    kj = (_pencere(h, kijun, "max") + _pencere(l, kijun, "min")) / 2.0
    sb = (_pencere(h, senkou_b, "max") + _pencere(l, senkou_b, "min")) / 2.0
    sa = (tk + kj) / 2.0

    def kay(x):
        out = np.full(len(x), np.nan)
        if kijun < len(x):
            out[kijun:] = x[:len(x) - kijun]
        return out
    return tk, kj, kay(sa), kay(sb)


def vwap_gunluk(h, l, c, v, gun) -> np.ndarray:
    """UTC gunune demirli VWAP (tipik fiyat (h+l+c)/3); `gun` bar basina gun numarasi. Hacim toplami 0 ise NaN."""
    tp = (np.asarray(h, float) + np.asarray(l, float) + np.asarray(c, float)) / 3.0
    v = np.asarray(v, dtype=float)
    gun = np.asarray(gun)
    pv, vv = np.cumsum(tp * v), np.cumsum(v)
    bas = np.r_[True, gun[1:] != gun[:-1]]
    idx = np.maximum.accumulate(np.where(bas, np.arange(len(v)), 0))
    pv0 = np.where(idx > 0, pv[idx - 1], 0.0)
    vv0 = np.where(idx > 0, vv[idx - 1], 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        den = vv - vv0
        return np.where(den > 0, (pv - pv0) / den, np.nan)


def pivot_dip(l, sol: int = 10, sag: int = 2) -> np.ndarray:
    """i pivot dip: l[i] sol `sol` mumun HEPSINDEN ve sag `sag` mumun HEPSINDEN kesin dusuk (kesin esitsizlik). Pivot i'de isaretlenir
    ama ANCAK i+sag kapanisinda bilinir: kullanan taraf yalniz indeksi <= t-sag olanlari kullanmalidir."""
    from numpy.lib.stride_tricks import sliding_window_view
    l = np.asarray(l, dtype=float)
    n = len(l)
    out = np.zeros(n, bool)
    if n < sol + sag + 1:
        return out
    idx = np.arange(sol, n - sag)
    sm = sliding_window_view(l, sol)[idx - sol].min(axis=1)
    rm = sliding_window_view(l, sag)[idx + 1].min(axis=1)
    out[idx] = (l[idx] < sm) & (l[idx] < rm)
    return out


def pivot_tepe(h, sol: int = 10, sag: int = 2) -> np.ndarray:
    return pivot_dip(-np.asarray(h, dtype=float), sol, sag)
