"""MF1: mum formasyonlari kutuphanesi (24.11 kullanici karari; tasarim: fikirler/gorev/2026-11-24-45474500845/gorev_sonuc.md).

8 formasyon, her biri ayri kurulum (`MF1-YUTAN` ...) ve 4 zaman diliminde ayri kol (`MF1-YUTAN@1h`). Dedektorler long
uzayinda yazilir (short = fiyat aynasi), YALNIZ `t` ve oncesini okur; giris = kapanis `c[t]`, stop/hedef formasyona gore
(hedef yazmiyorsa 2R = giris + 2 x (giris - stop)); zaman stopu yazmiyorsa 48 mum. Kitap kurallari sabit: ders parametresi okunmaz.
`[k]` = k mum once; `dipN` = `t` dahil son N mumun en dusugu. Mum aralik/govde bolmeleri aralik > 0 ister (ortak `ok`)."""
from __future__ import annotations

from . import ArmInput
from ._kutuphane import Formasyon, hesapla

SETUP = "MF1"
TIMEFRAMES = ("1h", "4h", "1d")
CORE = False
EXIT_MODE = "target"
PRIORITY = 300                       # kutuphane tabanlari: GF1 200, MF1 300, IN1 400 (mevcut kollar hep onde: en buyuk 95)
FEATURES = {"body_ratio": "body_ratio", "wick_ratio": "wick_ratio", "rr": "rr", "f_seviye": "ema_value",
            "f_olcu_atr": "edge_dist_atr", "f_yas": "pullback_ema"}


def _gv(g, k=0):
    """(o, h, l, c, govde, aralik) `t-k` mumu."""
    i = g.t - k
    o, h, l, c = g.o[i], g.h[i], g.l[i], g.c[i]
    return o, h, l, c, abs(c - o), h - l


def _sonuc(stop, etiket, *, hedef=None, seviye=None, olcu=None, yas=0):
    return {"stop": float(stop), "hedef": hedef, "seviye": float(stop if seviye is None else seviye),
            "olcu": olcu, "yas": yas, "etiket": etiket}


def pinbar(g):
    o, h, l, c, gov, ar = _gv(g)
    alt, ust = min(o, c) - l, h - max(o, c)
    if alt >= 2 * gov and ust < 0.1 * ar and c >= l + 0.5 * ar and l <= g.dip(10):
        return _sonuc(l, "pinbar", olcu=c - l)
    return None


def iccubuk(g):
    """Ana mum m, ic mum m+1 (h<h[m], l>l[m]); t in {m+2, m+3}; c[t] > h[m]; aradaki mum h[m] ustunde kapanmamis."""
    t = g.t
    for k in (2, 3):
        m = t - k
        if g.h[m + 1] < g.h[m] and g.l[m + 1] > g.l[m] and g.c[t] > g.h[m]:
            if k == 3 and not g.c[m + 2] <= g.h[m]:
                continue
            return _sonuc(g.l[m], "ic_cubuk", seviye=g.h[m], olcu=g.h[m] - g.l[m], yas=k)
    return None


def _yutan_kosulu(g) -> bool:
    o, h, l, c, *_ = _gv(g)
    o1, h1, l1, c1, *_ = _gv(g, 1)
    return bool(c1 < o1 and c > o and o <= c1 and c >= o1 and l1 <= g.dip(5, 1))


def yutan(g):
    if _yutan_kosulu(g):
        l, c = g.l[g.t], g.c[g.t]
        return _sonuc(l, "yutan", olcu=c - l)
    return None


def delici(g):
    o, h, l, c, gov, ar = _gv(g)
    o1, h1, l1, c1, gov1, ar1 = _gv(g, 1)
    if c1 < o1 and gov1 >= 0.5 * ar1 and o <= c1 and (o1 + c1) / 2 < c < o1 and min(l, l1) <= g.dip(10):
        st = min(l, l1)
        return _sonuc(st, "delici", olcu=c - st)
    return None


def harami(g):
    o, h, l, c, *_ = _gv(g)
    o1, h1, l1, c1, gov1, ar1 = _gv(g, 1)
    if c1 < o1 and gov1 >= 0.6 * ar1 and c > o and o > c1 and c < o1 and l1 <= g.dip(5, 1):
        st = min(l, l1)
        return _sonuc(st, "harami", olcu=c - st)
    return None


def cimbiz(g):
    o, h, l, c, *_ = _gv(g)
    o1, h1, l1, c1, *_ = _gv(g, 1)
    if (c1 < o1 and c > o and abs(l - l1) <= 0.1 * g.atr[g.t] and min(l, l1) <= g.dip(10)
            and not _yutan_kosulu(g)):
        st = min(l, l1)
        return _sonuc(st, "cimbiz", olcu=c - st)
    return None


def icsahte(g):
    o, h, l, c, *_ = _gv(g)
    h1, l1 = g.h[g.t - 1], g.l[g.t - 1]
    h2, l2 = g.h[g.t - 2], g.l[g.t - 2]
    if h1 < h2 and l1 > l2 and l < l2 and c > l1 and c > o:
        return _sonuc(l, "ic_sahte", seviye=l2, olcu=c - l)
    return None


def disbar(g):
    o, h, l, c, *_ = _gv(g)
    h1, l1 = g.h[g.t - 1], g.l[g.t - 1]
    if h > h1 and l < l1 and c > h1 and l <= g.dip(5):
        return _sonuc(l, "dis_bar", olcu=c - l)
    return None


_TF = TIMEFRAMES
FORMASYONLAR = {
    "DELICI": Formasyon("DELICI", "Mum: delici cizgi", 3, _TF, 48, delici),
    "ICSAHTE": Formasyon("ICSAHTE", "Mum: ic cubuk sahte kopus", 4, _TF, 48, icsahte),
    "DISBAR": Formasyon("DISBAR", "Mum: dis bar", 5, _TF, 48, disbar),
    "YUTAN": Formasyon("YUTAN", "Mum: yutan", 6, _TF, 48, yutan),
    "HARAMI": Formasyon("HARAMI", "Mum: harami", 7, _TF, 48, harami),
    "CIMBIZ": Formasyon("CIMBIZ", "Mum: cimbiz dip", 9, _TF, 48, cimbiz),
    "PINBAR": Formasyon("PINBAR", "Mum: pin bar", 10, _TF, 48, pinbar),
    "ICCUBUK": Formasyon("ICCUBUK", "Mum: ic cubuk", 11, _TF, 48, iccubuk),
}


def compute(kod: str, inp: ArmInput):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
