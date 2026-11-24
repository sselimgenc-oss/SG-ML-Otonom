"""TF1: trend yonunde kapanis kirilimi (momentum devami; Ek-K K-1; PA-YAP-03, PA-KIR-01, PA-FLT-01/02/04, PA-STP-02a).

Long: rejim trend_up, c > EMA_S ve EMA_F > EMA_S, taze kapanis kirilimi (c > HC + 0,2 ATR; onceki bar kirilim degil),
govde >= 0,5, yukari kapanis, uzama (c - EMA_S)/ATR <= 3. Stop = HC - 1 ATR; hedef yok; cikis iz suren stop (trail).
Short: aynasi (`_pa` ayna koordinati). Sinyal bari = son KAPANMIS tetik bari; pencereler t'yi icermez."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core import indicators as I

from . import ArmInput
from . import _pa as P

SETUP = "TF1"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
CORE = False
EXIT_MODE = "trail"
PRIORITY = 30
# defter anahtari -> tasiyici sutun (SIGNAL_COLUMNS); tamsayi tasiyici yalniz pullback_ema
FEATURES = {"brk_dist_atr": "edge_dist_atr", "ema_value": "ema_value", "body_ratio": "body_ratio",
            "ext_atr": "wick_ratio", "brk_n": "pullback_ema"}

LOOKBACK = {"15m": 120, "1h": 120, "4h": 120, "1d": 50}
N_BRK = {"15m": 50, "1h": 50, "4h": 50, "1d": 20}
EMA_F = {"15m": 20, "1h": 20, "4h": 20, "1d": 10}
EMA_S = {"15m": 50, "1h": 50, "4h": 50, "1d": 30}
BRK_ATR = 0.2
BODY_MIN = 0.5
EXT_MAX = 3.0
STOP_ATR = 1.0
SDA_MIN = 0.5
SDA_MAX = 3.0
TREND = {"long": "trend_up", "short": "trend_down"}


def _scan(p: P.Prep, side: str, tf: str):
    """Yon icin (aday maskesi, t -> ayrinti). Aday maskesi skip'ten once (iki yon kontrolu icin)."""
    o, h, l, c = P.mirror(p, side)
    atr = p.atr
    n_brk = N_BRK[tf]
    cs = pd.Series(c)
    ema_f = I.ema(cs, EMA_F[tf]).to_numpy(dtype=float)
    ema_s = I.ema(cs, EMA_S[tf]).to_numpy(dtype=float)
    hc = cs.shift(1).rolling(n_brk).max().to_numpy(dtype=float)          # HC(t) = max c[t-N .. t-1]
    with np.errstate(invalid="ignore", divide="ignore"):
        body = np.abs(c - o) / (h - l)
        brk = c > hc + BRK_ATR * atr                                       # brk(k)
        brk_prev = np.concatenate(([False], brk[:-1]))
        ext = (c - ema_s) / atr
        mask = (p.ok & (p.regime == TREND[side]) & (c > ema_s) & (ema_f > ema_s) & np.isfinite(hc)
                & brk & ~brk_prev & (c > o) & (body >= BODY_MIN) & (ext <= EXT_MAX))
    info: dict[int, dict] = {}
    for t in np.flatnonzero(mask):
        stop = hc[t] - STOP_ATR * atr[t]
        sda = (c[t] - stop) / atr[t]
        info[int(t)] = dict(stop=stop, sda=sda, ema=ema_s[t], body=body[t], ext=ext[t],
                            edge=(c[t] - hc[t]) / atr[t], close=c[t], skip=None)
        if not (SDA_MIN <= sda <= SDA_MAX):
            info[int(t)]["skip"] = "stop_width"
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
        tab.put(t, setup=SETUP, side=side, skip=d["skip"], labels=[TREND[side], "ema_ok", "close_brk", "body_ok",
                                                                  "ext_ok"],
                entry=s * d["close"], stop=s * d["stop"], target=None, rr=np.nan, sda=d["sda"],
                ema=s * d["ema"], body=d["body"], wick=d["ext"], edge=d["edge"], pb=N_BRK[tf])
    return tab.frame()
