"""H2 varyantlari (24.11 kullanici karari: PA varyantlari). Ana kol H2 (iki bacakli geri cekilme; `h2.py`) AYNEN kalir.

MINI: tetik = 3 dusen tepeden (h[t-3] > h[t-2] > h[t-1]) gecen mini cizginin kirilimi: cizgi(t) = h[t-1] + (h[t-1] - h[t-3]) / 2,
c[t] > cizgi(t) ve c[t] > o[t]. Baglam H2 ile ayni: rejim trend_up, c > EMA20, EMA20[t] > EMA20[t-5], derinlik
(max h[t-20 .. t-3] - min l[t-3 .. t]) / ATR >= 1,0. Stop = min l[t-3 .. t] (tampon yok). Cikis iz suren stop (ana kolla ayni).
Opus'un 'dogrusallik olcusu' kullanilmadi (kitapta sayi yok)."""
from __future__ import annotations

from . import h2 as H2
from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, ema, sonuc

SETUP = "H2"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "trail"
PRIORITY = 50
DERINLIK_MIN = 1.0


def mini(g):
    t = g.t
    if not g.trend_ok():
        return None
    if not (g.h[t - 1] < g.h[t - 2] < g.h[t - 3]):
        return None
    cizgi = g.h[t - 1] + (g.h[t - 1] - g.h[t - 3]) / 2.0
    e = ema(g, H2.EMA_TREND)
    if not (g.c[t] > cizgi and g.c[t] > g.o[t] and g.c[t] > e[t] and e[t] > e[t - H2.EMA_SLOPE_LAG]):
        return None
    dip = float(g.l[t - 3:t + 1].min())
    if not ((float(g.h[t - H2.PB_WIN:t - 2].max()) - dip) / float(g.atr[t]) >= DERINLIK_MIN):
        return None
    return sonuc(dip, "mini", seviye=cizgi, olcu=g.c[t] - dip, yas=3)


FORMASYONLAR = {
    "MINI": Formasyon("MINI", "H2 varyant: mini cizgi kirilimi tetigi", 1, TUM_ZD, None, mini, kip="trail"),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
