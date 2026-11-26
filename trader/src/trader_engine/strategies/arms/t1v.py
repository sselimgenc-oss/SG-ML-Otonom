"""T1 varyantlari (24.11 kullanici karari: PA varyantlari; kaynak: fikirler/gorev/2026-11-24-45480527826/gorev_sonuc.md).
Ana kol T1 (trend ici geri cekilme; `t1.py`) AYNEN kalir; varyantlar ayri kimlikli kurulum. Cikis ana kolla ayni (iz suren stop).

GERI3: trendde (4s rejimi trend_up) art arda 3 dusen tepe (h[t-3] > h[t-2] > h[t-1]) sonra c[t] > h[t-1]. Stop = son 4 mumun dibi
(tampon yok). Kitaptaki isteye bagli Force Index (EMA3 <= 0, EMA13 >= 0) kosulu EKLENMEDI (isteye bagli).
SEVIYE: trendde, kirilmis eski direnc seviyesine (onayli pivot tepe: sol 10, sag 2, indeks <= t-2) ilk geri donus: pivottan sonra
ilk kapanis kirilimi k0; [k0, t-1] kapanislari >= seviye, (k0, t-1] diplerinde temas yok (l > S + 0,3 ATR); l[t] <= S + 0,3 ATR,
c[t] > S, c[t] > o[t]. Stop = min(l[t], l[t-1]). En yakin pivot sirasiyla aranir (en cok 100 mum)."""
from __future__ import annotations

import numpy as np

from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, sonuc

SETUP = "T1"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "trail"
PRIORITY = 10                        # ana kolun hemen arkasi: ana 10, varyantlar 11, 12 ...
PIVOT_SOL, PIVOT_SAG, PIVOT_MAX, YAKIN_ATR = 10, 2, 100, 0.3


def geri3(g):
    t = g.t
    if not g.trend_ok():
        return None
    if g.h[t - 1] < g.h[t - 2] < g.h[t - 3] and g.c[t] > g.h[t - 1]:
        stop = float(g.l[t - 3:t + 1].min())
        return sonuc(stop, "geri3", seviye=g.h[t - 1], olcu=g.c[t] - stop, yas=3)
    return None


def seviye(g):
    t = g.t
    if not g.trend_ok():
        return None
    tol = YAKIN_ATR * float(g.atr[t])
    if not (g.c[t] > g.o[t]):
        return None
    for p in range(t - PIVOT_SAG, max(t - PIVOT_MAX, PIVOT_SOL) - 1, -1):
        S = float(g.h[p])
        if not (S >= g.h[p - PIVOT_SOL:p].max() and S > g.h[p + 1:p + 1 + PIVOT_SAG].max()):
            continue
        if not (g.l[t] <= S + tol and g.c[t] > S):
            continue
        kirilim = np.flatnonzero(g.c[p + 1:t] > S)
        if kirilim.size == 0:
            continue
        k0 = p + 1 + int(kirilim[0])
        if g.c[k0:t].min() < S or (k0 + 1 < t and g.l[k0 + 1:t].min() <= S + tol):
            continue
        stop = float(min(g.l[t], g.l[t - 1]))
        return sonuc(stop, "seviye", seviye=S, olcu=g.c[t] - stop, yas=t - k0)
    return None


FORMASYONLAR = {
    "GERI3": Formasyon("GERI3", "T1 varyant: 3 dusen tepe geri cekilmesi", 1, TUM_ZD, None, geri3, kip="trail"),
    "SEVIYE": Formasyon("SEVIYE", "T1 varyant: eski direnc seviyesine geri cekilme", 2, TUM_ZD, None, seviye, kip="trail"),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
