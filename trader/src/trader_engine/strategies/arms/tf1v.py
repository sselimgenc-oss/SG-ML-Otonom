"""TF1 varyantlari (24.11 kullanici karari: PA varyantlari). Ana kol TF1 (trend yonunde kapanis kirilimi; `tf1.py`) AYNEN kalir;
varyant, ana kolun `t` mumundaki ayni yonlu sinyaline bir giris sarti ekler (stop ana kolun; cikis iz suren stop).

HACIM: kirilim mumunun hacmi >= 1,5 x onceki 20 mumun ortalamasi (t dahil degil).
FITIL: kirilim mumunun ust fitili (islem yonunde zirve ile govde ucu farki) <= aralik x 0,25 (fitil esigi secimdir; kitap sayi vermez).
TF1 / H2 'iz suren stop olarak hareketli ortalama ya da onceki mumun dibi' EKLENMEDI: cikis kipi degisir (EXIT_RULE pozisyon
yonunu/giris bilgisini okuyamaz; yeni cikis kipi motora ve ders kapsamina dokunur)."""
from __future__ import annotations

from . import tf1 as TF1
from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, ana_sonuc, hacim_oran

SETUP = "TF1"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "trail"
PRIORITY = 30
HACIM_KAT = 1.5
FITIL_MAX = 0.25


def hacim(g):
    r = hacim_oran(g)
    return ana_sonuc(g, TF1, "hacim", hedef_yok=True) if r >= HACIM_KAT else None


def fitil(g):
    t = g.t
    ar = g.h[t] - g.l[t]
    if not (ar > 0 and (g.h[t] - max(g.o[t], g.c[t])) <= FITIL_MAX * ar):
        return None
    return ana_sonuc(g, TF1, "fitil", hedef_yok=True)


FORMASYONLAR = {
    "HACIM": Formasyon("HACIM", "TF1 varyant: hacim onayli kirilim", 1, TUM_ZD, 48, hacim, kip="trail"),
    "FITIL": Formasyon("FITIL", "TF1 varyant: ust fitilsiz kirilim", 2, TUM_ZD, 48, fitil, kip="trail"),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
