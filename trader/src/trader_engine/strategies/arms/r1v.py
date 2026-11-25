"""R1 varyantlari (24.11 kullanici karari: PA varyantlari). Ana kol R1 (yatay piyasa kenari; `r1.py`) AYNEN kalir: varyant, ana
kolun `t` mumundaki ayni yonlu sinyalinin (R1 kenar + fitil reddi) ustune bir sart ya da farkli cikis ekler; stop/hedef ana kolun.

HA: ek teyit = Heikin Ashi renk donusu (HA[t-1] ters renk, HA[t] islem yonunde; son 30 mumdan hesaplanir).
ALT: yon filtresi = kapanis bandin islem yonundeki ilk ucte birinde (long: (c-rl)/(rh-rl) <= 1/3; short aynasi).
ERKEN: ayni giris, zaman stopu 48 yerine 24 mum (erken cikis). Kademeli cikis motorda ZATEN acik (exit_modes default partial);
'ilerlemeyen islem' sarti (pozisyon bilgisi ister; EXIT_RULE yalniz son mumu okur) EKLENMEDI."""
from __future__ import annotations

import numpy as np

from . import _pa as P
from . import r1 as R1
from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, ana_sonuc, ha_donus

SETUP = "R1"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "target"
PRIORITY = 20
ALT_ORAN = 1.0 / 3.0
ERKEN_ZAMAN_STOPU = 24


def ha(g):
    return ana_sonuc(g, R1, "ha") if ha_donus(g) else None


def alt(g):
    a = g.ana(R1)
    if a is None:
        return None
    r = a["satir"]
    rh, rl = float(r["rh"]), float(r["rl"])
    c = P.SIGN[g.yon] * float(g.c[g.t])
    if not (np.isfinite(rh) and np.isfinite(rl) and rh > rl):
        return None
    frac = (c - rl) / (rh - rl) if g.yon == "long" else (rh - c) / (rh - rl)
    return ana_sonuc(g, R1, "alt") if frac <= ALT_ORAN else None


def erken(g):
    return ana_sonuc(g, R1, "erken")


FORMASYONLAR = {
    "HA": Formasyon("HA", "R1 varyant: Heikin Ashi donus teyidi", 1, TUM_ZD, 48, ha),
    "ALT": Formasyon("ALT", "R1 varyant: bandin ilk ucte biri", 2, TUM_ZD, 48, alt),
    "ERKEN": Formasyon("ERKEN", "R1 varyant: erken zaman stopu (24 mum)", 3, TUM_ZD, ERKEN_ZAMAN_STOPU, erken),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
