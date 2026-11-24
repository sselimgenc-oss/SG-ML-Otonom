"""F1: sahte kirilim / SFP donusu (swing dibi suprmesi + geri alma; Ek-K K-3; PA-KIR-03, PA-YAP-01, PA-MUM-01, PA-STP-01,
PA-HDF-02).

Long: A = min(l[t-N .. t-5]), k* = bu asgarinin en son indeksi, k* >= t-N+2 (pencere kenarinda degil). `s` = {t-1, t} icinde
dusuk olan (esitlikte t), Lsw = min(l[s..t]), Hsw = max(h[s..t]). Supurme: Lsw < A - 0,1 ATR ve c[t-2] >= A; geri alma:
c[t] > A ve c[t] > o[t]; ret gucu rej = (c - Lsw)/(Hsw - Lsw) >= 0,6; derinlik (A - Lsw)/ATR <= 1,5. t-1 ham adayi yoksa sinyal.
Stop = Lsw - 0,2 ATR; hedef = max(h[t-20 .. t-1]) - 0,2 ATR; cikis: hedef + zaman durdurma (EXIT_MODE target).
Short: aynasi (`_pa` ayna koordinati). Tum pencereler t'yi icermez."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import ArmInput
from . import _pa as P

SETUP = "F1"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
CORE = False
EXIT_MODE = "target"
PRIORITY = 70
# defter anahtari -> tasiyici sutun (SIGNAL_COLUMNS); seviye -> ema_value (fiyat), tamsayi -> pullback_ema
FEATURES = {"level": "ema_value", "sweep_depth_atr": "edge_dist_atr", "rej_ratio": "wick_ratio",
            "body_ratio": "body_ratio", "level_age": "pullback_ema", "rr": "rr"}

LOOKBACK = {"15m": 60, "1h": 60, "4h": 60, "1d": 40}
N_LVL = {"15m": 40, "1h": 40, "4h": 40, "1d": 20}
LVL_GAP = 5
SWEEP_ATR = 0.1
REJ_MIN = 0.6
DEPTH_MAX = 1.5
STOP_ATR = 0.2
TGT_WIN = 20
TGT_IN_ATR = 0.2
SDA_MIN = 0.5
SDA_MAX = 2.0
ALLOWED = {"long": ("range", "unclear", "trend_up"), "short": ("range", "unclear", "trend_down")}


def _raw(p: P.Prep, side: str, tf: str):
    """Yon icin ham aday (kosullar tamam, stop/hedef kontrolu oncesi): (maske, t -> ayrinti)."""
    o, h, l, c = P.mirror(p, side)
    atr = p.atr
    n = len(c)
    N = N_LVL[tf]
    reg = np.isin(p.regime, ALLOWED[side])
    raw = np.zeros(n, dtype=bool)
    info: dict[int, dict] = {}
    with np.errstate(invalid="ignore"):
        for t in range(N, n):
            if not (p.ok[t] and reg[t]):
                continue
            a = t - N
            win = l[a:t - LVL_GAP + 1]                              # [t-N, t-5]
            m = float(np.min(win))
            ks = a + (len(win) - 1 - int(np.argmin(win[::-1])))     # asgarinin en son indeksi
            if ks < a + 2:
                continue
            s = t - 1 if l[t - 1] < l[t] else t
            lsw = float(np.min(l[s:t + 1]))
            hsw = float(np.max(h[s:t + 1]))
            a_t = float(atr[t])
            if not (lsw < m - SWEEP_ATR * a_t and c[t - 2] >= m and c[t] > m and c[t] > o[t]):
                continue
            rej = (c[t] - lsw) / (hsw - lsw)
            depth = (m - lsw) / a_t
            if not (rej >= REJ_MIN and depth <= DEPTH_MAX):
                continue
            raw[t] = True
            info[t] = dict(level=m, lsw=lsw, rej=rej, depth=depth, age=t - ks, atr=a_t, close=c[t], body=abs(c[t] - o[t])
                           / (h[t] - l[t]), regime=p.regime[t])
    return raw, info


def _scan(p: P.Prep, side: str, tf: str, rr_min: float):
    """Yon icin aday maskesi (t-1 ham adayi varsa t atlanir) ve ayrinti (stop/hedef/atlama)."""
    o, h, l, c = P.mirror(p, side)
    raw, info = _raw(p, side, tf)
    prev = np.concatenate(([False], raw[:-1]))
    mask = raw & ~prev
    out: dict[int, dict] = {}
    for t in np.flatnonzero(mask):
        t = int(t)
        d = info[t]
        stop = d["lsw"] - STOP_ATR * d["atr"]
        sda = (d["close"] - stop) / d["atr"]
        tgt = float(np.max(h[t - TGT_WIN:t])) - TGT_IN_ATR * d["atr"]       # h[t-20 .. t-1]
        rr = (tgt - d["close"]) / (d["close"] - stop)
        skip = None
        if not (SDA_MIN <= sda <= SDA_MAX):
            skip = "stop_width"
        elif not (np.isfinite(rr) and rr >= rr_min):
            skip = "rr_below_min"
        out[t] = dict(d, stop=stop, sda=sda, target=tgt, rr=rr, skip=skip)
    return mask, out


def compute(inp: ArmInput):
    tf = inp.tf
    p = P.prepare(inp)
    tab = P.Table(p.core)
    if len(p.c) < LOOKBACK[tf]:                       # isinma: aday yok, hata yok
        return tab.frame()
    rr_min = float(inp.params.rr_min)
    mask_l, info_l = _scan(p, "long", tf, rr_min)
    mask_s, info_s = _scan(p, "short", tf, rr_min)
    for t in np.flatnonzero(mask_l | mask_s):
        t = int(t)
        if mask_l[t] and mask_s[t]:
            tab.both(t, SETUP)
            continue
        side, info = ("long", info_l) if mask_l[t] else ("short", info_s)
        d = info[t]
        s = P.SIGN[side]
        tab.put(t, setup=SETUP, side=side, skip=d["skip"], labels=[d["regime"], "sweep", "recover", "rej_ok", "depth_ok"],
                entry=s * d["close"], stop=s * d["stop"], target=s * d["target"], rr=d["rr"], sda=d["sda"],
                ema=s * d["level"], body=d["body"], wick=d["rej"], edge=d["depth"], pb=d["age"])
    return tab.frame()
