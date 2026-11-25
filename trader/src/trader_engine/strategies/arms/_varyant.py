"""24.11 kullanici karari: PA varyantlari ortak yardimcilari (kurulum dosyasi DEGIL; `_` onekli, `discover` yok sayar).

Varyant = mevcut 7 kolun (T1 R1 TF1 B1 H2 S1 F1) ayri kimlikli yeni kurulumu (`TF1-HACIM@1h`); ana kolun ASIL davranisi
degismez. Kutuphane yapisi (`_kutuphane.py`): hepsi acik, tam boy, aile = ana kol (kapasite aile 6 / varyant x ZD 3). Dedektorler
long uzayinda yazilir (short = fiyat aynasi) ve YALNIZ `t` ve oncesini okur. Ders parametresi okunmaz (kitap kurallari sabit)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_core import indicators as I

from . import _pa as P

TUM_ZD = ("15m", "1h", "4h", "1d")
HA_PENCERE = 30            # Heikin Ashi: her zaman SON 30 mumdan (ozyinelemeli ilk deger sabit => pencere bagimsiz)
HACIM_N = 20


def sonuc(stop, etiket, *, hedef=None, seviye=None, olcu=None, yas=0):
    return {"stop": float(stop), "hedef": hedef, "seviye": float(stop if seviye is None else seviye),
            "olcu": olcu, "yas": yas, "etiket": etiket}


def ha_donus(g) -> bool:
    """Heikin Ashi renk donusu (g-uzayinda long): HA[t-1] kirmizi (c < o), HA[t] yesil."""
    a = g.t - HA_PENCERE + 1
    o, h, l, c = (x[a:g.t + 1] for x in (g.o, g.h, g.l, g.c))
    hc = (o + h + l + c) / 4.0
    ho = np.empty_like(hc)
    ho[0] = (o[0] + c[0]) / 2.0
    for i in range(1, len(hc)):
        ho[i] = (ho[i - 1] + hc[i - 1]) / 2.0
    return bool(hc[-2] < ho[-2] and hc[-1] > ho[-1])


def hacim_oran(g, n: int = HACIM_N) -> float:
    """v[t] / ortalama(v[t-n .. t-1]); hacim yoksa ya da ortalama <= 0 ise nan (t dahil degil)."""
    v = g.v
    ort = float(np.mean(v[g.t - n:g.t]))
    if not (np.isfinite(ort) and ort > 0 and np.isfinite(v[g.t])):
        return float("nan")
    return float(v[g.t] / ort)


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


def pin_geometri(g) -> bool:
    o, h, l, c = g.o[g.t], g.h[g.t], g.l[g.t], g.c[g.t]
    ar = h - l
    return bool(ar > 0 and (min(o, c) - l) >= 2 * abs(c - o) and (h - max(o, c)) < 0.1 * ar and c >= l + 0.5 * ar)


def yutan_geometri(g) -> bool:
    t = g.t
    return bool(g.c[t - 1] < g.o[t - 1] and g.c[t] > g.o[t] and g.o[t] <= g.c[t - 1] and g.c[t] >= g.o[t - 1])


def ana_sonuc(g, modul, etiket, *, hedef_yok: bool = False):
    """Ana kolun `t` satiri varsa (ayni yon, signal=True) onun stop/hedefiyle sonuc; yoksa None."""
    a = g.ana(modul)
    if a is None:
        return None
    return sonuc(a["stop"], etiket, hedef=None if hedef_yok else a["hedef"], olcu=abs(float(g.c[g.t]) - a["stop"]))
