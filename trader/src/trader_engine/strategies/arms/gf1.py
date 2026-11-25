"""GF1: grafik formasyonlari kutuphanesi (24.11 kullanici karari; tasarim: fikirler/gorev/2026-11-24-45474500845/gorev_sonuc.md).

13 formasyon, her biri ayri kurulum (`GF1-YATAY` ...) ve 4 zaman diliminde ayri kol. Dedektorler long uzayinda (short = fiyat aynasi)
YALNIZ `t` ve oncesini okur. Pivot: sol 10, sag 2, kesin esitsizlik; pivot ancak indeksi <= t-2 ise kullanilir (onay gecikmesi).
`T1,T2` onayli son iki pivot tepe, `D1,D2` son iki pivot dip. "Yakin" = |a-b| <= 0.03*min(|a|,|b|). "Ilk kirilim" = ilgili pivottan `t-1`e
kadar hicbir kapanis seviyenin otesinde degil ve `c[t]` otesinde. Tampon yok: stop seviyenin kendisi. Kitap kurallari sabit:
ders parametresi okunmaz. Hedef yazmiyorsa 2R; zaman stopu 48 mum."""
from __future__ import annotations

import numpy as np

from . import ArmInput
from ._kutuphane import Formasyon, hesapla

SETUP = "GF1"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
CORE = False
EXIT_MODE = "target"
PRIORITY = 200                       # kutuphane tabanlari: GF1 200, MF1 300, IN1 400 (mevcut kollar hep onde: en buyuk 95)
FEATURES = {"body_ratio": "body_ratio", "wick_ratio": "wick_ratio", "rr": "rr", "f_seviye": "ema_value",
            "f_olcu_atr": "edge_dist_atr", "f_yas": "pullback_ema"}
TOL = 0.03
UCGEN_MAX_YAS = 100
KAMA_MAX_YAS = 100


def yakin(a, b) -> bool:
    return abs(a - b) <= TOL * min(abs(a), abs(b))


def _sonuc(stop, etiket, *, hedef=None, seviye=None, olcu=None, yas=0):
    return {"stop": float(stop), "hedef": None if hedef is None else float(hedef),
            "seviye": float(stop if seviye is None else seviye), "olcu": olcu, "yas": int(yas), "etiket": etiket}


def _kirildi_mi(c, seviye, bas: int, t: int) -> bool:
    """c[bas..t-1] icinde seviyeyi (skaler ya da dizi) kapanisla gecen var mi."""
    if t <= bas:
        return False
    sev = seviye if np.ndim(seviye) == 0 else seviye[bas:t]
    return bool((c[bas:t] > sev).any())


# ------------------------------------------------------------------------------------------------ yatay direnc ailesi
def _yatay(g, t):
    """(L, i1, i2, yuk) ya da None: T1,T2 yakin; T1'den beri ilk kirilim `t`de."""
    HI, _ = g.pivotlar(t)
    if len(HI) < 2:
        return None
    i1, i2 = int(HI[-2]), int(HI[-1])
    h, l, c = g.h, g.l, g.c
    if not yakin(h[i1], h[i2]):
        return None
    L = max(h[i1], h[i2])
    if not c[t] > L or _kirildi_mi(c, L, i1 + 1, t):
        return None
    yuk = L - l[i1:i2 + 1].min()
    if not yuk > 0:
        return None
    return L, i1, i2, yuk


def yatay(g):
    r = _yatay(g, g.t)
    if r is None:
        return None
    L, i1, i2, yuk = r
    return _sonuc(min(L, g.l[g.t]), "yatay", hedef=L + yuk, seviye=L, olcu=yuk, yas=g.t - i2)


def _yatay_ham(g, t):
    r = g.once(("yatay", t), lambda: _yatay(g, t) or False)
    return r or None


def ucgen(g):
    t, h, l, c = g.t, g.h, g.l, g.c
    HI, LI = g.pivotlar()
    if len(HI) < 2 or len(LI) < 1:
        return None
    st = float(l[LI[-1]])
    # (a) yukselen ucgen: T1,T2 yakin, aralarinda >= 2 yukselen pivot dip, ilk kirilim
    i1, i2 = int(HI[-2]), int(HI[-1])
    if yakin(h[i1], h[i2]):
        ara = LI[(LI > i1) & (LI < i2)]
        if len(ara) >= 2 and (np.diff(l[ara]) > 0).all():
            L = max(h[i1], h[i2])
            gen = h[i1] - l[ara[0]]
            if c[t] > L and not _kirildi_mi(c, L, i1 + 1, t) and st < c[t] and gen > 0:
                return _sonuc(st, "yukselen_ucgen", hedef=L + gen, seviye=L, olcu=gen, yas=t - i1)
    # (b) simetrik: tepeler dusuyor, dipler yukseliyor; ust cizgi disinda ilk kapanis; en eski pivottan en fazla 100 mum
    if len(LI) >= 2:
        ta, tb, da, db = int(HI[-2]), int(HI[-1]), int(LI[-2]), int(LI[-1])
        if h[ta] > h[tb] and l[da] < l[db] and t <= min(ta, da) + UCGEN_MAX_YAS:
            bas = max(tb, db) + 1
            x = np.arange(bas, t + 1, dtype=float)
            U = h[ta] + (h[tb] - h[ta]) / (tb - ta) * (x - ta)
            Lo = l[da] + (l[db] - l[da]) / (db - da) * (x - da)
            ok = (c[bas:t + 1] > U) & (U > Lo)
            if ok[-1] and not ok[:-1].any() and st < c[t]:
                gen = h[ta] - l[da]
                if gen > 0:
                    return _sonuc(st, "simetrik_ucgen", hedef=U[-1] + gen, seviye=U[-1], olcu=gen, yas=t - min(ta, da))
    return None


def ikili(g):
    t, h, l, c = g.t, g.h, g.l, g.c
    _, LI = g.pivotlar()
    if len(LI) < 2:
        return None
    i1, i2 = int(LI[-2]), int(LI[-1])
    if not (5 <= i2 - i1 <= 25) or not yakin(l[i1], l[i2]):
        return None
    boyun = h[i1:i2 + 1].max()
    dip = min(l[i1], l[i2])
    if c[t] > boyun and not _kirildi_mi(c, boyun, i1 + 1, t):
        return _sonuc(dip, "ikili_dip", hedef=boyun + (boyun - dip), seviye=boyun, olcu=boyun - dip, yas=t - i2)
    return None


def obo(g):
    """TOBO: 3 pivot dip, ortadaki en dusuk, omuzlar yakin; boyun = aradaki iki en yuksek pivot tepeden gecen dogru; onceki hareket >= 2 x (bas-boyun)."""
    t, h, l, c = g.t, g.h, g.l, g.c
    HI, LI = g.pivotlar()
    if len(LI) < 3:
        return None
    ia, ib, ic = (int(x) for x in LI[-3:])
    la, lb, lc = l[ia], l[ib], l[ic]
    if not (lb < la and lb < lc and yakin(la, lc)):
        return None
    p1s, p2s = HI[(HI > ia) & (HI < ib)], HI[(HI > ib) & (HI < ic)]
    if len(p1s) == 0 or len(p2s) == 0:
        return None
    p1, p2 = int(p1s[np.argmax(h[p1s])]), int(p2s[np.argmax(h[p2s])])
    egim = (h[p2] - h[p1]) / (p2 - p1)
    D = h[p1] + egim * (ib - p1) - lb
    w = ic - ia
    if D <= 0 or ia - w < 0 or h[ia - w:ia + 1].max() - la < 2 * D:
        return None
    line_t = h[p1] + egim * (t - p1)
    if not c[t] > line_t:
        return None
    xs = np.arange(ic + 1, t, dtype=float)
    if len(xs) and (c[ic + 1:t] > h[p1] + egim * (xs - p1)).any():
        return None
    return _sonuc(lb, "tobo", hedef=line_t + D, seviye=line_t, olcu=D, yas=t - ia)


def uclu(g):
    t, h, l, c = g.t, g.h, g.l, g.c
    _, LI = g.pivotlar()
    if len(LI) < 3:
        return None
    a, b, d = (int(x) for x in LI[-3:])
    if d - a > 60 or not (yakin(l[a], l[b]) and yakin(l[b], l[d]) and yakin(l[a], l[d])):
        return None
    boyun = h[a:d + 1].max()
    dip = min(l[a], l[b], l[d])
    if c[t] > boyun and not _kirildi_mi(c, boyun, a + 1, t):
        return _sonuc(dip, "uclu_dip", hedef=boyun + (boyun - dip), seviye=boyun, olcu=boyun - dip, yas=t - d)
    return None


# ------------------------------------------------------------------------------------------------ bayrak / flama
def _bayrak(g, daralma_ister: bool):
    t, h, l, c, atr = g.t, g.h, g.l, g.c, g.atr
    if t < 32:
        return None
    P = t - 20 + int(np.argmax(h[t - 20:t - 2]))          # [t-20, t-3]
    if P < t - 15:
        return None
    taban = l[P - 10:P + 1].min()
    H = h[P] - taban
    if not (H >= 3 * atr[P]):
        return None
    fh, fl = h[P + 1:t], l[P + 1:t]
    dip = fl.min()
    if dip < h[P] - 0.5 * H or not c[t] > fh.max():
        return None
    m = len(fh)
    dar = False
    if m >= 6:
        yarim = m // 2
        a1 = fh[:yarim].max() - fl[:yarim].min()
        a2 = fh[yarim:].max() - fl[yarim:].min()
        dar = bool(a2 < 0.7 * a1)
    if daralma_ister != dar or (daralma_ister and m < 6):
        return None
    seviye = fh.max()
    return _sonuc(dip, "flama" if daralma_ister else "bayrak", hedef=seviye + H, seviye=seviye, olcu=H, yas=t - P)


def bayrak(g):
    return _bayrak(g, False)


def flama(g):
    return _bayrak(g, True)


# ------------------------------------------------------------------------------------------------ kama / kanal
def _egimli(g):
    """(ta,tb,da,db,su,sl,bas) son iki tepe ve son iki dip; ya da None."""
    HI, LI = g.pivotlar()
    if len(HI) < 2 or len(LI) < 2:
        return None
    ta, tb, da, db = int(HI[-2]), int(HI[-1]), int(LI[-2]), int(LI[-1])
    h, l = g.h, g.l
    return ta, tb, da, db, (h[tb] - h[ta]) / (tb - ta), (l[db] - l[da]) / (db - da), max(tb, db) + 1


def _dusen_kirilim(g):
    """Dusen tepe + dusen dip yapisinda ust cizgi ustunde ilk kapanis: (U_t, Lo_t, su, sl, ta, da) ya da None."""
    e = _egimli(g)
    if e is None:
        return None
    t, h, l, c = g.t, g.h, g.l, g.c
    ta, tb, da, db, su, sl, bas = e
    if not (h[tb] < h[ta] and l[db] < l[da]) or t > min(ta, da) + KAMA_MAX_YAS or t < bas:
        return None
    x = np.arange(bas, t + 1, dtype=float)
    U = h[ta] + su * (x - ta)
    Lo = l[da] + sl * (x - da)
    ok = (c[bas:t + 1] > U) & (U > Lo)
    if not ok[-1] or ok[:-1].any():
        return None
    return U[-1], Lo[-1], su, sl, ta, da, tb, db


def kama(g):
    r = _dusen_kirilim(g)
    if r is None:
        return None
    U, Lo, su, sl, ta, da, tb, db = r
    if not su < sl:                                         # ust cizgi alttan dik: yakinsiyor
        return None
    return _sonuc(g.l[db], "dusen_kama", hedef=g.h[ta], seviye=U, olcu=g.h[ta] - g.l[db], yas=g.t - min(ta, da))


def trend(g):
    r = _dusen_kirilim(g)
    if r is None:
        return None
    U, Lo, su, sl, ta, da, tb, db = r
    if su < sl:
        return None
    return _sonuc(g.l[db], "dusen_kanal", seviye=U, olcu=U - Lo, yas=g.t - min(ta, da))


def kanal(g):
    t, h, l, c, o = g.t, g.h, g.l, g.c, g.o
    HI, LI = g.pivotlar()
    if len(HI) < 2 or len(LI) < 2:
        return None
    t1, t2, d1, d2 = int(HI[-2]), int(HI[-1]), int(LI[-2]), int(LI[-1])
    if not (yakin(h[t1], h[t2]) and yakin(l[d1], l[d2])):
        return None
    R, S = max(h[t1], h[t2]), min(l[d1], l[d2])
    a = g.atr[t]
    if R - S >= 3 * a and l[t] <= S + 0.25 * a and c[t] > S and c[t] > o[t]:
        return _sonuc(min(l[t], S), "kanal", hedef=R, seviye=S, olcu=R - S, yas=t - min(t1, t2, d1, d2))
    return None


# ------------------------------------------------------------------------------------------------ retest / sahte / kupa
def retest(g):
    """Son 20 mumda YATAY kirilimi olmus (seviye L); o gunden beri L altinda kapanis yok; temas mumu = kirilimdan sonraki ilk."""
    t, h, l, c, o, atr = g.t, g.h, g.l, g.c, g.o, g.atr
    if not c[t] > o[t]:
        return None
    for b in range(t - 1, t - 21, -1):
        r = _yatay_ham(g, b)
        if r is None:
            continue
        L, i1, i2, yuk = r
        if (c[b:t + 1] < L).any() or not c[t] > L or not l[t] <= L + 0.25 * atr[t]:
            return None
        j = np.arange(b + 1, t)
        if len(j) and ((l[j] <= L + 0.25 * atr[j]) & (c[j] > L) & (c[j] > o[j])).any():
            return None
        return _sonuc(min(l[t], L), "retest", hedef=L + yuk, seviye=L, olcu=yuk, yas=t - b)
    return None


def sahte(g):
    t, l, c = g.t, g.l, g.c
    _, LI = g.pivotlar()
    if len(LI) < 2:
        return None
    d1, d2 = int(LI[-2]), int(LI[-1])
    if not yakin(l[d1], l[d2]):
        return None
    S = min(l[d1], l[d2])
    if not c[t] > S:
        return None
    r = 0
    while r < 4 and t - r - 1 > d2 and c[t - r - 1] < S:
        r += 1
    if not 1 <= r <= 3 or not (t - r - 1 > d2 and c[t - r - 1] >= S):
        return None
    st = l[t - r:t + 1].min()
    return _sonuc(st, "sahte_kirilim", seviye=S, olcu=c[t] - st, yas=r)


def kupa(g):
    t, l = g.t, g.l
    r = _yatay(g, t)
    if r is None:
        return None
    L, i1, i2, yuk = r
    derinlik = L - l[i1:i2 + 1].min()
    if not (20 <= i2 - i1 <= 100) or not derinlik >= 3 * g.atr[t] or t - i2 < 3:
        return None
    kulp = l[i2:t + 1].min()
    if kulp < L - 0.5 * derinlik:
        return None
    return _sonuc(kulp, "kupa_kulp", hedef=L + derinlik, seviye=L, olcu=derinlik, yas=t - i1)


_TF = TIMEFRAMES
FORMASYONLAR = {
    "OBO": Formasyon("OBO", "Grafik: ters omuz bas omuz", 1, _TF, 48, obo),
    "UCLU": Formasyon("UCLU", "Grafik: uclu dip", 2, _TF, 48, uclu),
    "KUPA": Formasyon("KUPA", "Grafik: kupa kulp", 3, _TF, 48, kupa),
    "IKILI": Formasyon("IKILI", "Grafik: ikili dip", 4, _TF, 48, ikili),
    "KAMA": Formasyon("KAMA", "Grafik: dusen kama", 5, _TF, 48, kama),
    "UCGEN": Formasyon("UCGEN", "Grafik: ucgen", 6, _TF, 48, ucgen),
    "BAYRAK": Formasyon("BAYRAK", "Grafik: bayrak", 7, _TF, 48, bayrak),
    "FLAMA": Formasyon("FLAMA", "Grafik: flama", 8, _TF, 48, flama),
    "RETEST": Formasyon("RETEST", "Grafik: kirilim retesti", 9, _TF, 48, retest),
    "SAHTE": Formasyon("SAHTE", "Grafik: sahte kirilim", 10, _TF, 48, sahte),
    "TREND": Formasyon("TREND", "Grafik: dusen kanal", 11, _TF, 48, trend),
    "KANAL": Formasyon("KANAL", "Grafik: kanal dibi", 12, _TF, 48, kanal),
    "YATAY": Formasyon("YATAY", "Grafik: yatay direnc kirilimi", 13, _TF, 48, yatay),
}


def compute(kod: str, inp: ArmInput):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
