"""24.11 kullanici karari: PA varyantlari ortak yardimcilari (kurulum dosyasi DEGIL; `_` onekli, `discover` yok sayar).

Varyant = mevcut 7 kolun (T1 R1 TF1 B1 H2 S1 F1) ayri kimlikli yeni kurulumu (`H2-MINI@1h`); ana kolun ASIL davranisi
degismez. Kutuphane yapisi (`_kutuphane.py`): hepsi acik, tam boy, aile = ana kol (kapasite aile 6 / varyant x ZD 3). Dedektorler
long uzayinda yazilir (short = fiyat aynasi) ve YALNIZ `t` ve oncesini okur. Ders parametresi okunmaz (kitap kurallari sabit)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core import indicators as I

from . import _pa as P

TUM_ZD = ("1h", "4h", "1d")


def sonuc(stop, etiket, *, hedef=None, seviye=None, olcu=None, yas=0):
    return {"stop": float(stop), "hedef": hedef, "seviye": float(stop if seviye is None else seviye),
            "olcu": olcu, "yas": yas, "etiket": etiket}


def ema(g, n: int) -> np.ndarray:
    """g-uzayi kapanis EMA(n), cift x ZD x D basina yon bazinda bir kez (nedensel)."""
    key = ("ema", g.yon, n)
    oz = g.ham.oz
    if key not in oz:
        oz[key] = I.ema(pd.Series(g.c), n).to_numpy(dtype=float)
    return oz[key]


def prep(g) -> P.Prep:
    oz = g.ham.oz
    if "prep" not in oz:
        oz["prep"] = P.prepare(g.ham.inp)
    return oz["prep"]
