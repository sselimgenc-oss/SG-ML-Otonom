"""B1: seviye kirilimi + yeniden test (Ek-K K-2; PA-SDR-01/02, PA-KIR-01, PA-KIR-02 (a), PA-STP-01, PA-HDF-01).

Kirilim bari i0 (long): L = max h[i0-N .. i0-1]; c[i0] > L + 0,2 ATR, onceki bar kirilim degil, govde >= 0,5, seviyenin
yasi >= 3 bar (L'yi veren en son azami i0-3'ten eski), [i0-N, i0-1] icinde >= 2 ayrik dokunma kosusu.
Retest (t, i0 < t <= i0+10): (i0, t]'de dokunma, hepsi c >= L, t'de yukari kapanis (c > o, c > L); kirilim basina tek sinyal.
Stop = min(l(i0, t]) - stop_buffer_atr ATR; hedef = c + 2R (rr = 2,0); cikis: hedef + zaman durdurma (EXIT_MODE target)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import ArmInput
from . import _pa as P

SETUP = "B1"
TIMEFRAMES = ("1h", "4h", "1d")
CORE = False
EXIT_MODE = "target"
PRIORITY = 40
# defter anahtari -> tasiyici sutun; level -> ema_value (fiyat), retest_depth_atr -> wick_ratio, bars_since_brk -> pullback_ema
FEATURES = {"level": "ema_value", "brk_dist_atr": "edge_dist_atr", "retest_depth_atr": "wick_ratio",
            "body_ratio": "body_ratio", "bars_since_brk": "pullback_ema", "rr": "rr"}

LOOKBACK = {"15m": 70, "1h": 70, "4h": 70, "1d": 45}
N_LVL = {"15m": 40, "1h": 40, "4h": 40, "1d": 20}
BRK_ATR = 0.2
BODY_MIN = 0.5
TOUCH_ATR = 0.25
MIN_TOUCH = 2
LVL_AGE_MIN = 3
RETEST_W = 10
RETEST_ATR = 0.25
TARGET_R = 2.0
SDA_MIN = 0.5
SDA_MAX = 2.5
ALLOWED = {"long": ("trend_up", "range", "unclear"), "short": ("trend_down", "range", "unclear")}


def _breaks(p: P.Prep, side: str, tf: str):
    """Yon icin kirilim barlari (bool) ve seviye L (i0'da). Aynali koordinat."""
    o, h, l, c = P.mirror(p, side)
    n = len(c)
    atr = p.atr
    N = N_LVL[tf]
    rh = pd.Series(h).rolling(N).max().to_numpy(dtype=float)           # RH(k) = max h[k-N+1 .. k]
    brk = np.zeros(n, dtype=bool)
    lvl = np.full(n, np.nan)
    for i0 in range(N + 1, n):
        if not (p.ok[i0] and p.ok[i0 - 1]):
            continue
        L = rh[i0 - 1]
        if not (np.isfinite(L) and np.isfinite(rh[i0 - 2])):
            continue
        a = atr[i0]
        if not (c[i0] > L + BRK_ATR * a):
            continue
        if not (c[i0 - 1] <= rh[i0 - 2] + BRK_ATR * atr[i0 - 1]):
            continue
        if not (abs(c[i0] - o[i0]) / (h[i0] - l[i0]) >= BODY_MIN and c[i0] > o[i0]):
            continue
        win = h[i0 - N:i0]                                              # [i0-N, i0-1]
        last = i0 - N + (N - 1 - int(np.argmax(win[::-1])))              # L'yi veren en son azami
        if last > i0 - LVL_AGE_MIN:
            continue
        touch = win >= L - TOUCH_ATR * a
        runs = int(touch[0]) + int(np.count_nonzero(touch[1:] & ~touch[:-1]))
        if runs < MIN_TOUCH:
            continue
        brk[i0] = True
        lvl[i0] = L
    return brk, lvl


def _scan(p: P.Prep, side: str, tf: str, brk: np.ndarray, lvl: np.ndarray, brk_opp: np.ndarray,
          buffer_atr: float, rr_min: float):
    """Yon icin retest adaylari: (aday maskesi, t -> ayrinti). Kirilim basina tek sinyal; ters kirilim/seviye kapanisi oldurur."""
    o, h, l, c = P.mirror(p, side)
    n = len(c)
    atr = p.atr
    reg = np.isin(p.regime, ALLOWED[side])
    mask = np.zeros(n, dtype=bool)
    info: dict[int, dict] = {}
    last = -1
    fired = -1
    for t in range(n):
        if t >= 1 and brk[t - 1]:
            last = t - 1
        if last < 0 or t - last > RETEST_W:
            continue
        i0 = last
        if fired == i0 or not (p.ok[t] and reg[t]):
            continue
        L = lvl[i0]
        seg = slice(i0 + 1, t + 1)
        if np.any(c[seg] < L) or np.any(brk_opp[seg]):                  # seviye kapandi / ters kirilim
            continue
        if not np.any(l[seg] <= L + RETEST_ATR * atr[seg]):
            continue
        if not (c[t] > o[t] and c[t] > L):
            continue
        lo_min = float(np.min(l[seg]))
        stop = lo_min - buffer_atr * atr[t]
        sda = (c[t] - stop) / atr[t]
        rr = TARGET_R
        skip = None
        if not (SDA_MIN <= sda <= SDA_MAX):
            skip = "stop_width"
        elif rr < rr_min:
            skip = "rr_below_min"
        target = c[t] + TARGET_R * (c[t] - stop)
        mask[t] = True
        info[t] = dict(stop=stop, target=target, sda=sda, rr=rr, close=c[t], body=abs(c[t] - o[t]) / (h[t] - l[t]),
                       level=L, brk_dist=(c[i0] - L) / atr[i0], retest=(lo_min - L) / atr[t], bars=t - i0,
                       regime=p.regime[t], skip=skip)
        if skip is None:
            fired = i0
    return mask, info


def compute(inp: ArmInput):
    tf = inp.tf
    p = P.prepare(inp)
    tab = P.Table(p.core)
    if len(p.c) < LOOKBACK[tf]:                       # isinma: aday yok, hata yok
        return tab.frame()
    brk_l, lvl_l = _breaks(p, "long", tf)
    brk_s, lvl_s = _breaks(p, "short", tf)
    buf = float(inp.params.stop_buffer_atr)
    rr_min = float(inp.params.rr_min)
    mask_l, info_l = _scan(p, "long", tf, brk_l, lvl_l, brk_s, buf, rr_min)
    mask_s, info_s = _scan(p, "short", tf, brk_s, lvl_s, brk_l, buf, rr_min)
    for t in np.flatnonzero(mask_l | mask_s):
        t = int(t)
        if mask_l[t] and mask_s[t]:
            tab.both(t, SETUP)
            continue
        side, info = ("long", info_l) if mask_l[t] else ("short", info_s)
        d = info[t]
        s = P.SIGN[side]
        tab.put(t, setup=SETUP, side=side, skip=d["skip"], labels=[d["regime"], "retest", "close_up"],
                entry=s * d["close"], stop=s * d["stop"], target=s * d["target"], rr=d["rr"], sda=d["sda"],
                ema=s * d["level"], body=d["body"], wick=d["retest"], edge=d["brk_dist"], pb=d["bars"])
    return tab.frame()
