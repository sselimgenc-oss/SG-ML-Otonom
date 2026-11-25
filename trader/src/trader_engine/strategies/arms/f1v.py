"""F1 varyanti (24.11 kullanici karari: PA varyantlari). Ana kol F1 (sahte kirilim / SFP donusu; `f1.py`) AYNEN kalir.

IKINCI: ayni seviyede ikinci supurmeden sonra gir. F1'in ham adayi (`f1._raw`: supurme + geri alma + ret gucu + derinlik) `t`'de var
ve t-20 .. t-2 arasinda daha once bir ham aday (ilk supurme) var; ikinci supurmenin seviyesi birincinin seviyesine ya da supurme
dibine <= 0,5 ATR yakin. Ana kolun 't-1 ham adayi yoksa' kurali burada aranmaz (tersi: onceki supurme sart).
Stop = Lsw - 0,2 ATR (F1 ile ayni); hedef = max(h[t-20 .. t-1]) - 0,2 ATR, girise 1R'den yakinsa 2R (kutuphane yedegi)."""
from __future__ import annotations

import numpy as np

from . import f1 as F1
from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, prep, sonuc

SETUP = "F1"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "target"
PRIORITY = 70
ONCEKI_PENCERE = 20
YAKIN_ATR = 0.5


def ikinci(g):
    t = g.t
    tf = g.ham.inp.tf
    if t + 1 < F1.LOOKBACK[tf]:
        return None
    oz = g.ham.oz
    key = ("f1raw", g.yon)
    if key not in oz:
        oz[key] = F1._raw(prep(g), g.yon, tf)
    raw, info = oz[key]
    if not raw[t]:
        return None
    d = info[t]
    tol = YAKIN_ATR * float(g.atr[t])
    var = False
    for tp in range(max(t - ONCEKI_PENCERE, F1.N_LVL[tf]), t - 1):
        if raw[tp] and (abs(d["level"] - info[tp]["level"]) <= tol or abs(d["level"] - info[tp]["lsw"]) <= tol):
            var = True
            break
    if not var:
        return None
    stop = d["lsw"] - F1.STOP_ATR * d["atr"]
    hedef = float(np.max(g.h[t - F1.TGT_WIN:t])) - F1.TGT_IN_ATR * d["atr"]
    if hedef - g.c[t] < g.c[t] - stop:
        hedef = None
    return sonuc(stop, "ikinci", hedef=hedef, seviye=d["level"], olcu=d["depth"] * d["atr"], yas=int(d["age"]))


FORMASYONLAR = {
    "IKINCI": Formasyon("IKINCI", "F1 varyant: ayni seviyede ikinci supurme", 1, TUM_ZD, 48, ikinci),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
