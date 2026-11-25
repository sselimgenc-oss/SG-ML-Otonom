"""PA2: price action kutuphanesi (24.11 kullanici karari; tasarim: fikirler/gorev/2026-11-24-45480527826/gorev_sonuc.md,
'Yeni PA2 formasyonlari'). 8 formasyon, her biri ayri kurulum (`PA2-BOLGE` ...); 29 kol (6 formasyon x 4 ZD, ONCEKI 3 ZD, TUKENIS 2 ZD).
Dedektorler long uzayinda (short = fiyat aynasi), YALNIZ `t` ve oncesini okur; giris = kapanis `c[t]`; tampon yok (stop seviyenin
kendisi); "yedek 2R": hedef girise 1R'den yakin ya da yanlis taraftaysa 2R. Pivot: sol 10, sag 2, kesin esitsizlik, indeks <= t-2.
Gunluk/haftalik donemler mum ACILIS zamanindan (UTC; hafta Pazartesi 00:00). Gunluk ATR(14): onceki 14 tam gunun ortalama gercek
araligi (pencere uzunlugundan bagimsiz); 15 tam gun yoksa aday yok. Kitap kurallari sabit: ders parametresi okunmaz."""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from . import ArmInput
from ._kutuphane import Formasyon, hesapla

SETUP = "PA2"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
CORE = False
EXIT_MODE = "target"
PRIORITY = 250                       # GF1 200 < PA2 250 < MF1 300 (mevcut kollar hep onde)
FEATURES = {"body_ratio": "body_ratio", "wick_ratio": "wick_ratio", "rr": "rr", "f_seviye": "ema_value",
            "f_olcu_atr": "edge_dist_atr", "f_yas": "pullback_ema"}

_GUN = 86400
_HAFTA_OFS = 4 * _GUN                # 1970-01-01 Persembe; ilk Pazartesi gun 4
_ZD_SN = {"15m": 900, "1h": 3600}


def _sonuc(stop, etiket, *, hedef=None, seviye=None, olcu=None, yas=0):
    return {"stop": float(stop), "hedef": None if hedef is None else float(hedef),
            "seviye": float(stop if seviye is None else seviye), "olcu": None if olcu is None else float(olcu),
            "yas": int(yas), "etiket": etiket}


def _yedek(entry, stop, hedef):
    r = entry - stop
    return hedef if hedef - entry >= r else entry + 2.0 * r


def _pivot_dip(g) -> list[int]:
    """Onayli pivot dipler (en yeni once, en fazla 2): l[i] < onceki 10 ve < sonraki 2; i <= t-2. Taramasi son ~400 mum."""
    hit = g.onb.get(("piv", g.t))
    if hit is not None:
        return hit
    t, l = g.t, g.l
    lo = max(10, t - 400)
    out: list[int] = []
    if t - 2 >= lo:
        sol = sliding_window_view(l[lo - 10:t - 2], 10).min(axis=1)
        sag = np.minimum(l[lo + 1:t], l[lo + 2:t + 1])
        m = (l[lo:t - 1] < sol) & (l[lo:t - 1] < sag)
        out = [int(lo + i) for i in np.flatnonzero(m)[::-1][:2]]
    g.onb[("piv", g.t)] = out
    return out


# ------------------------------------------------------------------------------------------------ BOLGE
def bolge(g):
    o, h, l, c, atr, t = g.o, g.h, g.l, g.c, g.atr, g.t
    if not (c[t] > o[t]):
        return None
    for k in range(t - 3, max(t - 50, 7) - 1, -1):
        ar = h[k] - l[k]
        a = atr[k - 1]
        if not (c[k] > o[k] and ar > 0 and c[k] - o[k] >= 0.6 * ar and a == a and ar >= a):
            continue
        n, j = 0, k - 1
        while n < 5 and j >= 0 and abs(c[j] - o[j]) <= 0.5 * (h[j] - l[j]):
            n += 1
            j -= 1
        if n == 0:
            continue
        ust = float(np.maximum(o[k - n:k], c[k - n:k]).max())
        alt = float(l[k - n:k].min())
        if not (ust - alt <= 1.5 * a and c[k] > h[k - n:k].max()):
            continue
        if l[k + 1:t].min() <= ust:                      # ilk donus: arada bolgeye temas yok (tek hak)
            continue
        if l[t] <= ust and c[t] > alt:
            e = float(c[t])
            return _sonuc(alt, "bolge", hedef=e + 3.0 * (e - alt), seviye=ust, olcu=ust - alt, yas=t - k)
    return None


# ------------------------------------------------------------------------------------------------ EMIRBLOK
def emirblok(g):
    o, h, l, c, atr, t = g.o, g.h, g.l, g.c, g.atr, g.t
    if not (c[t] > o[t]):
        return None
    for k in range(t - 2, max(t - 50, 21) - 1, -1):
        ar = h[k] - l[k]
        if not (c[k] > o[k] and ar > 0 and c[k] - o[k] >= 0.6 * ar and c[k] > h[k - 20:k].max()):
            continue
        j = next((k - d for d in (1, 2, 3) if c[k - d] < o[k - d]), None)
        if j is None:
            continue
        arj = h[j] - l[j]
        a = atr[j]
        if not (arj > 0 and o[j] - c[j] > 0.5 * arj and a == a):
            continue
        ust = float(o[j])
        alt = float(l[j:k + 1].min())
        if c[k] - alt < 1.5 * a or l[k + 1:t].min() <= ust:
            continue
        if l[t] <= ust and c[t] > alt:
            e = float(c[t])
            return _sonuc(alt, "emir_blok", hedef=_yedek(e, alt, float(h[k:t].max())), seviye=ust, olcu=ust - alt, yas=t - k)
    return None


# ------------------------------------------------------------------------------------------------ FVG
def fvg(g):
    o, h, l, c, atr, t = g.o, g.h, g.l, g.c, g.atr, g.t
    if not (c[t] > o[t]):
        return None
    for gi in range(t - 1, max(t - 20, 3) - 1, -1):
        a = atr[gi - 2]
        ar1 = h[gi - 1] - l[gi - 1]
        if not (a == a and l[gi] > h[gi - 2] and l[gi] - h[gi - 2] >= 0.25 * a
                and c[gi - 1] > o[gi - 1] and ar1 > 0 and c[gi - 1] - o[gi - 1] >= 0.6 * ar1):
            continue
        if t - 1 > gi and l[gi + 1:t].min() <= l[gi]:
            continue
        if l[t] <= l[gi] and c[t] > h[gi - 2]:
            e = float(c[t])
            st = float(min(l[gi - 2], l[t]))
            return _sonuc(st, "fvg", hedef=_yedek(e, st, float(h[gi:t].max())), seviye=float(h[gi - 2]),
                          olcu=float(l[gi] - h[gi - 2]), yas=t - gi)
    return None


# ------------------------------------------------------------------------------------------------ ONCEKI
def _donem(g, hafta: bool):
    """(onceki donem dilimi [p0, s0), bu donem baslangici s0) ya da None (onceki donem eksik/tam degil)."""
    sec = g.sec
    if sec is None:
        return None
    t = g.t
    ofs, uz = (_HAFTA_OFS, 7 * _GUN) if hafta else (0, _GUN)
    ids = (sec[:t + 1] - ofs) // uz
    cur = ids[t]
    s0 = int(np.searchsorted(ids, cur, "left"))
    p0 = int(np.searchsorted(ids, cur - 1, "left"))
    if p0 >= s0 or sec[p0] != (cur - 1) * uz + ofs:       # onceki donem yok ya da acilisi pencerede degil
        return None
    return p0, s0


def _oncekinin(g, hafta: bool, etiket: str):
    h, l, o, c, t = g.h, g.l, g.o, g.c, g.t
    d = _donem(g, hafta)
    if d is None or not (c[t] > o[t]):
        return None
    p0, s0 = d
    L = float(l[p0:s0].min())
    Hh = float(h[p0:s0].max())
    if not c[t] > L:
        return None
    below = np.flatnonzero(l[s0:t + 1] < L)
    if len(below) == 0:
        return None
    s = s0 + int(below[0])
    if s < t - 2 or (c[s0:s] < L).any():
        return None
    if s < t and ((c[s:t] > L) & (c[s:t] > o[s:t])).any():     # donemde ilk boyle mum
        return None
    st = float(l[s:t + 1].min())
    e = float(c[t])
    return _sonuc(st, etiket, hedef=_yedek(e, st, (Hh + L) / 2.0), seviye=L, olcu=Hh - L, yas=t - s)


def onceki(g):
    ad = _adim(g)
    if ad is None or ad > 14400:
        return None
    return _oncekinin(g, ad == 14400, "onceki")


def _adim(g):
    if g.sec is None or g.t < 1:
        return None
    return int(np.diff(g.sec[max(0, g.t - 5):g.t + 1]).min())


# ------------------------------------------------------------------------------------------------ TUKENIS
def _tuk_kosul(g, m, s0, dATR):
    """`m` mumunda gunun (s0..m) tukenis kosulu (tetik dahil)."""
    h, l, c = g.h, g.l, g.c
    if m <= s0 or not c[m] > h[m - 1]:
        return False
    gh, gl = h[s0:m + 1], l[s0:m + 1]
    iH, iL = int(np.argmax(gh)), int(np.argmin(gl))
    return bool(gh[iH] - gl[iL] >= 2.0 * dATR and iH < iL and iL >= m - 3 - s0)


def tukenis(g):
    ad = _adim(g)
    sec, t, h, l, c, o = g.sec, g.t, g.h, g.l, g.c, g.o
    if ad not in (900, 3600):
        return None
    ids = (sec[:t + 1]) // _GUN
    cur = ids[t]
    s0 = int(np.searchsorted(ids, cur, "left"))
    a0 = int(np.searchsorted(ids, cur - 15, "left"))
    if s0 - a0 != 15 * (_GUN // ad) or sec[a0] != (cur - 15) * _GUN:           # 15 tam gun gerekir
        return None
    sid = ids[a0:s0]
    bas = np.flatnonzero(np.diff(sid, prepend=sid[0] - 1))
    if len(bas) != 15 or (np.diff(np.append(bas, len(sid))) != _GUN // ad).any():
        return None
    gH = np.maximum.reduceat(h[a0:s0], bas)
    gL = np.minimum.reduceat(l[a0:s0], bas)
    gC = c[a0:s0][np.append(bas[1:], len(sid)) - 1]
    tr = np.maximum(gH[1:] - gL[1:], np.maximum(np.abs(gH[1:] - gC[:-1]), np.abs(gL[1:] - gC[:-1])))
    dATR = float(tr.mean())
    if not (dATR > 0 and np.isfinite(dATR)):
        return None
    if not _tuk_kosul(g, t, s0, dATR):
        return None
    if any(_tuk_kosul(g, m, s0, dATR) for m in range(s0 + 1, t)):                 # gun icinde ilk boyle mum
        return None
    gl = float(l[s0:t + 1].min())
    e = float(c[t])
    return _sonuc(gl, "tukenis", hedef=e + 0.5 * dATR, seviye=float(h[s0:t + 1].max()), olcu=dATR, yas=t - int(np.argmin(l[s0:t + 1])) - s0)


# ------------------------------------------------------------------------------------------------ TCIZGI
def tcizgi(g):
    o, h, l, c, atr, t = g.o, g.h, g.l, g.c, g.atr, g.t
    p = _pivot_dip(g)
    if len(p) < 2 or not c[t] > o[t]:
        return None
    d2, d1 = p
    if not (l[d2] > l[d1] and d2 - d1 >= 5 and t - d1 <= 100 and t - d2 >= 3):
        return None
    x = np.arange(d1, t + 1)
    cz = l[d1] + (l[d2] - l[d1]) * (x - d1) / (d2 - d1)
    if (c[d1:t + 1] < cz).any():
        return None
    a = atr[d1:t + 1]
    temas = (l[d1:t + 1] <= cz + 0.25 * a) & (c[d1:t + 1] > cz) & (c[d1:t + 1] > o[d1:t + 1])
    if not temas[-1] or temas[d2 + 1 - d1:t - d1].any():                           # D2'den beri ilk temas
        return None
    e = float(c[t])
    risk = float(atr[t])
    return _sonuc(e - risk, "tcizgi", hedef=e + 2.5 * risk, seviye=float(cz[-1]), olcu=float(l[d2] - l[d1]), yas=t - d2)


# ------------------------------------------------------------------------------------------------ SEVIYE
def _mum_ok(g, m):
    """MF1-PINBAR govde/golge kosullari ya da MF1-YUTAN dort mum kosulu (dip10/dip5 yok)."""
    o, h, l, c = g.o, g.h, g.l, g.c
    ar = h[m] - l[m]
    if ar <= 0:
        return False
    gov = abs(c[m] - o[m])
    alt, ust = min(o[m], c[m]) - l[m], h[m] - max(o[m], c[m])
    if alt >= 2 * gov and ust < 0.1 * ar and c[m] >= l[m] + 0.5 * ar:
        return True
    return bool(c[m - 1] < o[m - 1] and c[m] > o[m] and o[m] <= c[m - 1] and c[m] >= o[m - 1])


def seviye(g):
    o, h, l, c, atr, t = g.o, g.h, g.l, g.c, g.atr, g.t
    p = _pivot_dip(g)
    if len(p) < 2:
        return None
    d2, d1 = p
    a = atr[t]
    if not (abs(l[d1] - l[d2]) <= 0.5 * a and d2 - d1 >= 5 and t >= d2 + 3):
        return None
    S = float(min(l[d1], l[d2]))
    if (c[d2:t] < S).any() or not c[t] > S:
        return None

    def ok(m):
        return S - 0.5 * atr[m] <= l[m] <= S + 0.3 * atr[m] and c[m] > S and _mum_ok(g, m)
    if not ok(t) or any(ok(m) for m in range(d2 + 1, t)):
        return None
    e = float(c[t])
    st = float(min(l[t], l[t - 1]))
    return _sonuc(st, "seviye", hedef=_yedek(e, st, float(h[d1:t].max())), seviye=S, olcu=float(a), yas=t - d2)


# ------------------------------------------------------------------------------------------------ UCVURUS
def ucvurus(g):
    o, h, l, c, t = g.o, g.h, g.l, g.c, g.t
    for i in (t - 3, t - 2, t - 1):
        if not (c[i] < o[i] and (c[i] - l[i]) <= 0.25 * (h[i] - l[i])):
            return None
    if not (l[t - 2] < l[t - 3] and l[t - 1] < l[t - 2] and o[t] <= c[t - 1] and c[t] > h[t - 3]):
        return None
    return _sonuc(l[t], "ucvurus", olcu=c[t] - l[t])


_TF = TIMEFRAMES
FORMASYONLAR = {
    "EMIRBLOK": Formasyon("EMIRBLOK", "PA: emir bloğu", 1, _TF, 48, emirblok),
    "BOLGE": Formasyon("BOLGE", "PA: arz/talep bölgesi", 2, _TF, 48, bolge),
    "FVG": Formasyon("FVG", "PA: değer boşluğu", 3, _TF, 48, fvg),
    "ONCEKI": Formasyon("ONCEKI", "PA: önceki dönem dibi", 4, ("15m", "1h", "4h"), 48, onceki),
    "TCIZGI": Formasyon("TCIZGI", "PA: trend çizgisi", 5, _TF, 48, tcizgi),
    "SEVIYE": Formasyon("SEVIYE", "PA: seviyede mum", 6, _TF, 48, seviye),
    "UCVURUS": Formasyon("UCVURUS", "PA: üç çizgi vuruşu", 7, _TF, 5, ucvurus),
    "TUKENIS": Formasyon("TUKENIS", "PA: günlük tükeniş", 8, ("15m", "1h"), {"15m": 48, "1h": 12}, tukenis),
}


def compute(kod: str, inp: ArmInput):
    return hesapla(SETUP, FORMASYONLAR, kod, inp)
