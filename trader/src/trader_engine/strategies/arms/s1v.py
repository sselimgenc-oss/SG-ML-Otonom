"""S1 varyantlari (24.11 kullanici karari: PA varyantlari). Ana kol S1 (sikisma kirilimi; `s1.py`) AYNEN kalir; stop ana kolun.

HACIM: kutuda hacim dusuk, kirilimda yuksek: ort(v[t-8 .. t-1]) <= ort(v[t-28 .. t-9]) ve v[t] >= 1,5 x ort(v[t-20 .. t-1]).
OLCULU: ayni giris; hedef = kutu dibi + direk boyu (BL + (c[t-9] - c[t-19])); cikis hedef + zaman stopu (48). Direk <= 0 ya da hedef
girisin altindaysa `rr_below_min` ile elenir. Ana kolun cikisi (iz suren stop) degismez; GF1-BAYRAK ayri fikirdir."""
from __future__ import annotations

import numpy as np

from . import s1 as S1
from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, ana_sonuc, hacim_oran, sonuc

SETUP = "S1"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "trail"
PRIORITY = 60
HACIM_KAT = 1.5


def hacim(g):
    t = g.t
    kutu = float(np.mean(g.v[t - S1.BOX_M:t]))
    onceki = float(np.mean(g.v[t - S1.BOX_M - 20:t - S1.BOX_M]))
    r = hacim_oran(g)
    if not (np.isfinite(kutu) and np.isfinite(onceki) and kutu <= onceki and r >= HACIM_KAT):
        return None
    return ana_sonuc(g, S1, "hacim", hedef_yok=True)


def olculu(g):
    a = g.ana(S1)
    if a is None:
        return None
    t = g.t
    bl = float(g.l[t - S1.BOX_M:t].min())
    direk = float(g.c[t - S1.BOX_M - 1] - g.c[t - S1.BOX_M - 1 - S1.POLE_P])
    return sonuc(a["stop"], "olculu", hedef=bl + direk, seviye=bl, olcu=abs(float(g.c[t]) - a["stop"]), yas=S1.POLE_P)


FORMASYONLAR = {
    "HACIM": Formasyon("HACIM", "S1 varyant: kutuda dusuk, kirilimda yuksek hacim", 1, TUM_ZD, 48, hacim, kip="trail"),
    "OLCULU": Formasyon("OLCULU", "S1 varyant: olculu hedef (kutu dibi + direk)", 2, TUM_ZD, 48, olculu),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
