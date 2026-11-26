"""S1: sikisma kirilimi (ic bar / NR7 kutusu; bayrak devami; Ek-K K-4; PA-MUM-05, PA-TRD-04, PA-YTY-05, PA-KIR-07, PA-FLT-03).

Kutu (t-1 itibarıyla): barlar t-8 .. t-1, BH = max(h), BL = min(l); A0 = ATR[t-9]; (BH - BL) <= 3,0 A0; son 3 barin
(t-3 .. t-1) en az biri ic bar ya da NR7. Giris (long): c[t] > BH + 0,1 ATR, c > o, govde >= 0,5, rejim trend_up/range/
unclear; t-3 .. t-1'de ham aday yoksa (soguma). Stop = BL - 0,2 ATR; hedef yok; cikis: iz suren stop (EXIT_MODE trail).
Bayrak olcusu pole_atr = (c[t-9] - c[t-19]) / A0 (islem yonune gore isaretli) bir ozelliktir, kosul degildir."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import ArmInput
from . import _pa as P

SETUP = "S1"
TIMEFRAMES = ("1h", "4h", "1d")
CORE = False
EXIT_MODE = "trail"
PRIORITY = 60
# defter anahtari -> tasiyici sutun; kutu kenari -> ema_value (fiyat), tamsayi -> pullback_ema
FEATURES = {"box_w_atr": "edge_dist_atr", "box_edge": "ema_value", "pole_atr": "wick_ratio",
            "body_ratio": "body_ratio", "nr_count": "pullback_ema"}

LOOKBACK = {"15m": 45, "1h": 45, "4h": 45, "1d": 45}
BOX_M = 8
BOX_W_ATR = 3.0
NR_WIN = 3
NR_N = 7
BRK_ATR = 0.1
BODY_MIN = 0.5
POLE_P = 10
COOLDOWN = 3
STOP_ATR = 0.2
SDA_MIN = 0.5
SDA_MAX = 3.0
ALLOWED = {"long": ("trend_up", "range", "unclear"), "short": ("trend_down", "range", "unclear")}


def _scan(p: P.Prep, side: str, tf: str):
    """Yon icin aday maskesi (soguma uygulanmis) ve t -> ayrinti. Tum pencereler t'yi icermez (t-1'e kadar)."""
    o, h, l, c = P.mirror(p, side)
    atr = p.atr
    n = len(c)
    reg = np.isin(p.regime, ALLOWED[side])
    hs, ls, cs = pd.Series(h), pd.Series(l), pd.Series(c)
    atrs = pd.Series(atr)
    with np.errstate(invalid="ignore", divide="ignore"):
        bh = hs.rolling(BOX_M).max().shift(1).to_numpy(dtype=float)        # max h[t-8 .. t-1]
        bl = ls.rolling(BOX_M).min().shift(1).to_numpy(dtype=float)        # min l[t-8 .. t-1]
        a0 = atrs.shift(BOX_M + 1).to_numpy(dtype=float)                    # ATR[t-9]
        box_w = (bh - bl) / a0
        inside = np.zeros(n, dtype=bool)
        inside[1:] = (h[1:] <= h[:-1]) & (l[1:] >= l[:-1])
        hl = h - l
        nr7 = hl == pd.Series(hl).rolling(NR_N).min().to_numpy(dtype=float)  # hl[k] = min hl[k-6 .. k]
        ev = pd.Series((inside | nr7).astype(float))
        nrc = (ev.shift(1) + ev.shift(2) + ev.shift(3)).to_numpy(dtype=float)  # son 3 barda ic/NR7 sayisi
        pole = (cs.shift(BOX_M + 1) - cs.shift(BOX_M + 1 + POLE_P)).to_numpy(dtype=float) / a0
        body = np.abs(c - o) / (h - l)
        raw = (p.ok & reg & np.isfinite(bh) & np.isfinite(bl) & np.isfinite(a0) & (a0 > 0)
               & (box_w <= BOX_W_ATR) & (nrc >= 1) & (c > bh + BRK_ATR * atr) & (c > o) & (body >= BODY_MIN))
    cool = np.zeros(n, dtype=bool)
    for k in range(1, COOLDOWN + 1):
        cool[k:] |= raw[:-k]
    mask = raw & ~cool
    info: dict[int, dict] = {}
    for t in np.flatnonzero(mask):
        t = int(t)
        stop = float(bl[t]) - STOP_ATR * float(atr[t])
        sda = (c[t] - stop) / float(atr[t])
        skip = None if SDA_MIN <= sda <= SDA_MAX else "stop_width"
        info[t] = dict(stop=stop, sda=sda, skip=skip, close=c[t], body=float(body[t]), edge_bh=float(bh[t]),
                       box_w=float(box_w[t]), pole=float(pole[t]), nr=int(nrc[t]), regime=p.regime[t])
    return mask, info


def compute(inp: ArmInput):
    tf = inp.tf
    p = P.prepare(inp)
    tab = P.Table(p.core)
    if len(p.c) < LOOKBACK[tf]:                       # isinma: aday yok, hata yok
        return tab.frame()
    mask_l, info_l = _scan(p, "long", tf)
    mask_s, info_s = _scan(p, "short", tf)
    for t in np.flatnonzero(mask_l | mask_s):
        t = int(t)
        if mask_l[t] and mask_s[t]:
            tab.both(t, SETUP)
            continue
        side, info = ("long", info_l) if mask_l[t] else ("short", info_s)
        d = info[t]
        s = P.SIGN[side]
        tab.put(t, setup=SETUP, side=side, skip=d["skip"], labels=[d["regime"], "box_ok", "nr_ok", "brk_close", "body_ok"],
                entry=s * d["close"], stop=s * d["stop"], target=None, rr=np.nan, sda=d["sda"],
                ema=s * d["edge_bh"], body=d["body"], wick=d["pole"], edge=d["box_w"], pb=d["nr"])
    return tab.frame()
