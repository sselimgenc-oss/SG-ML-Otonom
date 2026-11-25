"""B1 varyantlari (24.11 kullanici karari: PA varyantlari). Ana kol B1 (kirilim + yeniden test; `b1.py`) AYNEN kalir.

MUM: ana kolun `t` retest sinyaline ek sart: t mumu pin bar (alt golge >= 2 x govde, ust golge < 0,1 x aralik, kapanis aralik
ortasinin ustunde) ya da yutan mum (onceki dusus mumunu govdeyle yutan yukselis). Stop/hedef (2R) ana kolun.
BOLGE: seviye yerine bolge: B1'in kirilim bari ve seviyesi L ayni; bolge = [L - 1 ATR[i0], L]. Retest (i0 < t <= i0+10): (i0, t]'de
kapanis bolge dibinin (L - 1 ATR) altinda degil, ters kirilim yok, l <= L + 0,25 ATR dokunma var, t'de c > o ve c > bolge dibi.
Kirilim basina ILK gecerli retest tek sinyal. Stop = min(l(i0, t]) (tampon yok); hedef 2R (kutuphane yedegi). Rejim B1 ile ayni.
'Karmasik (cok mumlu, gidip gelen) kirilimda retest' EKLENMEDI: kitapta 'karmasik' icin sayisal tanim yok."""
from __future__ import annotations

import numpy as np

from . import b1 as B1
from ._kutuphane import Formasyon, hesapla
from ._varyant import TUM_ZD, ana_sonuc, pin_geometri, prep, sonuc, yutan_geometri

SETUP = "B1"
TIMEFRAMES = TUM_ZD
CORE = False
EXIT_MODE = "target"
PRIORITY = 40
BOLGE_ATR = 1.0


def mum(g):
    return ana_sonuc(g, B1, "mum") if (pin_geometri(g) or yutan_geometri(g)) else None


def _kirilimlar(g):
    oz = g.ham.oz
    key = ("b1brk", g.yon)
    if key not in oz:
        p = prep(g)
        ters = "short" if g.yon == "long" else "long"
        brk, lvl = B1._breaks(p, g.yon, g.ham.inp.tf)
        brk_o, _ = B1._breaks(p, ters, g.ham.inp.tf)
        oz[key] = (brk, lvl, brk_o, p)
    return oz[key]


def bolge(g):
    t = g.t
    if t + 1 < B1.LOOKBACK[g.ham.inp.tf]:
        return None
    brk, lvl, brk_o, p = _kirilimlar(g)
    idx = np.flatnonzero(brk[max(0, t - B1.RETEST_W):t])
    if idx.size == 0:
        return None
    i0 = max(0, t - B1.RETEST_W) + int(idx[-1])
    L = float(lvl[i0])
    zd = L - BOLGE_ATR * float(g.atr[i0])
    izinli = B1.ALLOWED[g.yon]
    for tt in range(i0 + 1, t + 1):
        seg = slice(i0 + 1, tt + 1)
        if np.any(g.c[seg] < zd) or np.any(brk_o[seg]):
            return None
        if not (p.ok[tt] and p.regime[tt] in izinli):
            continue
        if not np.any(g.l[seg] <= L + B1.RETEST_ATR * g.atr[seg]):
            continue
        if not (g.c[tt] > g.o[tt] and g.c[tt] > zd):
            continue
        if tt != t:
            return None                      # ilk gecerli retest daha once; kirilim basina tek sinyal
        stop = float(g.l[seg].min())
        return sonuc(stop, "bolge", seviye=L, olcu=g.c[t] - stop, yas=t - i0)
    return None


FORMASYONLAR = {
    "MUM": Formasyon("MUM", "B1 varyant: retestte pin bar / yutan mum", 1, TUM_ZD, 48, mum),
    "BOLGE": Formasyon("BOLGE", "B1 varyant: kirilan bolgeye geri donus", 2, TUM_ZD, 48, bolge),
}


def compute(kod: str, inp):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
