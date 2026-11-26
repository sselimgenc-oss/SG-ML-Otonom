"""H2: trendde iki bacakli geri cekilme (Ek-K K-5; PA-TRD-02, PA-FLT-02, PA-YAP-05, PA-STP-01, PA-STP-02).

Sayim (long): s = [t-20, t-3] icinde h'si en yuksek barin en son indeksi. (s, t] icinde H1 = (s, k1) icinde bir asagi
bulunan ilk yukari bar; H2 = (k1, k2) icinde bir asagi bulunan, k1'den sonraki ilk yukari bar. Giris: t == k2, k2 - k1 <= 10,
c[t] > h[t-1] ve c > o, rejim trend_up, c > EMA20 ve EMA20 yukari (EMA20[t] > EMA20[t-5]), derinlik
(h[s] - min l(s..t]) / ATR >= 1,0, (s, t]'de c >= EMA50 (1g: EMA30). Stop = min l(s..t] - stop_buffer_atr ATR; hedef yok;
cikis: iz suren stop (EXIT_MODE trail). Short: aynasi."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core import indicators as I

from . import ArmInput
from . import _pa as P

SETUP = "H2"
TIMEFRAMES = ("1h", "4h", "1d")
CORE = False
EXIT_MODE = "trail"
PRIORITY = 50
# defter anahtari -> tasiyici sutun; EMA20 -> ema_value, derinlik -> edge_dist_atr, pb_bars -> wick_ratio, bacak farki -> pullback_ema
FEATURES = {"ema_value": "ema_value", "pb_depth_atr": "edge_dist_atr", "pb_bars": "wick_ratio",
            "body_ratio": "body_ratio", "leg_gap": "pullback_ema"}

LOOKBACK = {"15m": 60, "1h": 60, "4h": 60, "1d": 45}
PB_WIN = 20
LEG_GAP_MAX = 10
EMA_TREND = 20
EMA_SLOPE_LAG = 5
PB_MIN_ATR = 1.0
EMA_GUARD = {"15m": 50, "1h": 50, "4h": 50, "1d": 30}
SDA_MIN = 0.5
SDA_MAX = 2.5
ALLOWED = {"long": ("trend_up",), "short": ("trend_down",)}


def _scan(p: P.Prep, side: str, tf: str, buf: float):
    """Yon icin aday maskesi ve t -> ayrinti. Her t icin sayim (s, k1, k2) yalniz t'ye kadar bakar."""
    o, h, l, c = P.mirror(p, side)
    atr = p.atr
    n = len(c)
    reg = np.isin(p.regime, ALLOWED[side])
    cs = pd.Series(c)
    ema20 = I.ema(cs, EMA_TREND).to_numpy(dtype=float)
    ema_g = I.ema(cs, EMA_GUARD[tf]).to_numpy(dtype=float)
    mask = np.zeros(n, dtype=bool)
    info: dict[int, dict] = {}
    with np.errstate(invalid="ignore"):
        for t in range(PB_WIN + 1, n):
            if not (p.ok[t] and reg[t] and t > EMA_SLOPE_LAG):
                continue
            if not (c[t] > h[t - 1] and c[t] > o[t] and c[t] > ema20[t] and ema20[t] > ema20[t - EMA_SLOPE_LAG]):
                continue
            win = h[t - PB_WIN:t - 2]                                   # [t-20, t-3]
            if not np.all(np.isfinite(win)):
                continue
            s = (t - PB_WIN) + (len(win) - 1 - int(np.argmax(win[::-1])))
            seen_down = False
            k1 = None
            k2 = None
            for k in range(s + 1, t + 1):
                if h[k] < h[k - 1]:
                    seen_down = True
                elif h[k] > h[k - 1] and seen_down:
                    if k1 is None:
                        k1 = k
                        seen_down = False
                    else:
                        k2 = k
                        break
            if k1 is None or k2 != t or (k2 - k1) > LEG_GAP_MAX:
                continue
            lo_min = float(np.min(l[s + 1:t + 1]))
            pb = (h[s] - lo_min) / atr[t]
            if not pb >= PB_MIN_ATR:
                continue
            if np.any(c[s + 1:t + 1] < ema_g[s + 1:t + 1]):
                continue
            stop = lo_min - buf * atr[t]
            sda = (c[t] - stop) / atr[t]
            skip = None if SDA_MIN <= sda <= SDA_MAX else "stop_width"
            mask[t] = True
            info[t] = dict(stop=stop, sda=sda, skip=skip, close=c[t], ema=ema20[t], pb=pb, bars=t - s,
                           leg_gap=k2 - k1, body=abs(c[t] - o[t]) / (h[t] - l[t]), regime=p.regime[t])
    return mask, info


def compute(inp: ArmInput):
    tf = inp.tf
    p = P.prepare(inp)
    tab = P.Table(p.core)
    if len(p.c) < LOOKBACK[tf]:                       # isinma: aday yok, hata yok
        return tab.frame()
    buf = float(inp.params.stop_buffer_atr)
    mask_l, info_l = _scan(p, "long", tf, buf)
    mask_s, info_s = _scan(p, "short", tf, buf)
    for t in np.flatnonzero(mask_l | mask_s):
        t = int(t)
        if mask_l[t] and mask_s[t]:
            tab.both(t, SETUP)
            continue
        side, info = ("long", info_l) if mask_l[t] else ("short", info_s)
        d = info[t]
        s = P.SIGN[side]
        tab.put(t, setup=SETUP, side=side, skip=d["skip"], labels=[d["regime"], "ema_ok", "slope_ok", "h2", "close_up",
                                                                  "depth_ok"],
                entry=s * d["close"], stop=s * d["stop"], target=None, rr=np.nan, sda=d["sda"],
                ema=s * d["ema"], body=d["body"], wick=float(d["bars"]), edge=d["pb"], pb=d["leg_gap"])
    return tab.frame()
