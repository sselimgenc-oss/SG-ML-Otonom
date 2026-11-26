"""S1 varyantlari (24.11 kullanici karari: PA varyantlari). Ana kol S1 (sikisma kirilimi; `s1.py`) AYNEN kalir; stop ana kolun.

OLCULU: ayni giris; hedef = kutu dibi + direk boyu (BL + (c[t-9] - c[t-19])); cikis hedef + zaman stopu (48). Direk <= 0 ya da hedef
girisin altindaysa `rr_below_min` ile elenir. Ana kolun cikisi (iz suren stop) degismez; GF1-BAYRAK ayri fikirdir."""
from __future__ import annotations

from . import s1 as S1
from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, sonuc

SETUP = "S1"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "trail"
PRIORITY = 60


def olculu(g):
    a = g.ana(S1)
    if a is None:
        return None
    t = g.t
    bl = float(g.l[t - S1.BOX_M:t].min())
    direk = float(g.c[t - S1.BOX_M - 1] - g.c[t - S1.BOX_M - 1 - S1.POLE_P])
    return sonuc(a["stop"], "olculu", hedef=bl + direk, seviye=bl, olcu=abs(float(g.c[t]) - a["stop"]), yas=S1.POLE_P)


FORMASYONLAR = {
    "OLCULU": Formasyon("OLCULU", "S1 varyant: olculu hedef (kutu dibi + direk)", 2, TUM_ZD, 48, olculu),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
