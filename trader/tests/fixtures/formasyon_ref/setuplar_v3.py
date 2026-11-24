"""v3: setup_secimi.md'deki 12 kitap setupu (KITAPTA YAZDIGI GIBI; kendi teyit/filtre eklenmez). Karar t kapanisinda; giris t+1 acilisi
(IC_CUBUK haric: kitapta bekleyen stop emri). Her setup long uzayinda yazilir, short = fiyat aynalamasi (ozellikler.aynala: o,h,l,c -> -o,-l,-h,-c), yuzdeler |fiyat| ile.
Kategori: MUM_* -> MF1, FOR_* -> GF1, IND_* -> IN1. Setup kimligi = tam ad.

Kitapta sayi VERILMEYEN yerlerde yapilan tek tek (README'de de listeli) tamamlamalar:
  * tampon yok: "hemen otesi / altinda" stoplari seviyenin kendisidir (stop <= seviye dokunusu tetikler).
  * "son N mumun en dusugu" = N mumluk pencere, sinyal mumu DAHIL (pin 10, yutan 5 [onceki mum icin], yildiz 2).
  * pivot = sol 10 / sag 2, KESIN esitsizlik (kitap: "hepsinden buyuk"); onay gecikmesi 2 mum (pivot i, i+2 kapanisinda kullanilir).
  * seviye/boyun penceresi: seviye, o pivotun (i+2) onayindan, ayni turden SONRAKI pivotun onayina kadar gecerli; kirilim = bu pencerede
    ilk kapanis (seviyenin ote yaninda); pencere oncesi ve icinde daha once kapanisla kirilmissa kurulum yok.
  * IKILI/OBO/yatay: 'birbirine %3 yakin' = |a-b| <= 0.03 * min(|a|,|b|). Yatay aralik dibi = pivotlar arasindaki en dusuk dip (fiyat).
  * ucgen: yapi yasi sinirsiz olamaz -> en eski pivottan kirilima en fazla UCGEN_MAX_YAS=100 mum (simetrik ucgen).
  * OBO onceki hareket: sol omuzdan once, formasyon genisligi (sol omuz->sag omuz) kadar geriye en uc deger -> sol omuz; >= 2 * (baş-boyun).
  * stop'u olmayan setuplarda (MA kesisim, fiyat-MA) R birimi = 2 ATR(14) (cikisi etkilemez; yalniz R olcegi) ve MIN_RISK tabani uygulanmaz."""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

import gostergeler as G

TOL = 0.03
UCGEN_MAX_YAS = 100
IC_PENCERE = 2
KATEGORI = {"MUM": "MF1", "FOR": "GF1", "IND": "IN1"}
NAN = float("nan")


# ----------------------------------------------------------------------------------------------- ozellikler
def pivot_dip_kesin(l, sol=10, sag=2):
    l = np.asarray(l, float)
    n = len(l)
    out = np.zeros(n, bool)
    if n < sol + sag + 1:
        return out
    idx = np.arange(sol, n - sag)
    sm = sliding_window_view(l, sol)[idx - sol].min(axis=1)
    rm = sliding_window_view(l, sag)[idx + 1].min(axis=1)
    out[idx] = (l[idx] < sm) & (l[idx] < rm)
    return out


def sma(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).mean(axis=1)
    return out


def std_pop(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(x, n).std(axis=1)
    return out


def pencere_min(x, n):
    """t'de x[t-n+1..t] en kucugu (t dahil)."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = sliding_window_view(np.asarray(x, float), n).min(axis=1)
    return out


def kay(x, k):
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:len(x) - k]
    return out


def ozellik(D: dict, yon: int) -> dict:
    """D: ham seri (gercek fiyat). Long uzayi ozellikleri; hicbiri t'den sonraki veriye bakmaz (pivotlar i+2'de bilinir)."""
    if yon == 1:
        S = D
    else:
        S = {"t": D["t"], "o": -D["o"], "h": -D["l"], "l": -D["h"], "c": -D["c"], "v": D["v"]}
    o, h, l, c = S["o"], S["h"], S["l"], S["c"]
    F = {"yon": yon, "n": len(c), "t": S["t"], "o": o, "h": h, "l": l, "c": c, "v": S["v"]}
    F["atr"] = G.atr(h, l, c, 14)
    F["rsi"] = G.rsi(c, 14)
    F["s20"], F["sd20"] = sma(c, 20), std_pop(c, 20)
    F["s50"], F["s200"] = sma(c, 50), sma(c, 200)
    F["piv_d"] = pivot_dip_kesin(l)
    F["piv_t"] = pivot_dip_kesin(-h)
    _, F["dip_val"] = G.kesinlesmis_son(F["piv_d"], l, 2)
    return F


def yakin(a, b):
    return abs(a - b) <= TOL * min(abs(a), abs(b))


def _ilk_kirilim(c, seviye, ref, bas, bitis):
    """seviye: skaler ya da bar basina dizi (kirilim cizgisi). Ilk t in [bas, bitis) ile c[t] > seviye[t]; (ref, bas) araliginda kapanisla
    kirilmis olmamali. -> t ya da None."""
    if bas >= bitis or bas >= len(c):
        return None
    bitis = min(bitis, len(c))
    sev = seviye if np.ndim(seviye) else None
    pre = c[ref + 1:bas]
    if len(pre) and (pre > (seviye if sev is None else seviye[ref + 1:bas])).any():
        return None
    seg = c[bas:bitis] > (seviye if sev is None else seviye[bas:bitis])
    if not seg.any():
        return None
    return bas + int(np.argmax(seg))


def _sonraki_onay(idx_dizi, k, n):
    return int(idx_dizi[k + 1]) + 2 if k + 1 < len(idx_dizi) else n


# ----------------------------------------------------------------------------------------------- MUM
def mum_pinbar(F):
    o, h, l, c = F["o"], F["h"], F["l"], F["c"]
    n = F["n"]
    govde, aralik = np.abs(c - o), h - l
    alt, ust = np.minimum(o, c) - l, h - np.maximum(o, c)
    dip10 = pencere_min(l, 10)
    with np.errstate(invalid="ignore"):
        m = (aralik > 0) & (alt >= 2 * govde) & (ust < 0.1 * aralik) & (c >= l + 0.5 * aralik) & (l <= dip10)
    m[n - 1] = False
    return [(int(t), l[t], c[t] + 2 * (c[t] - l[t]), "pinbar", {}) for t in np.flatnonzero(m)]


def mum_ic_cubuk(F):
    """Ana mum t-1, ic mum t. t kapaniminda ana mumun en yuksegine alis-stop; stop = ana mumun en dusugu; hedef 2R (seviyeden). Emir 2 mum gecerli.
    short: aynalanmis ayni emir (cift yonlu OCO: calistirici iki yonu birlikte ele alir)."""
    h, l = F["h"], F["l"]
    n = F["n"]
    h1, l1 = kay(h, 1), kay(l, 1)
    with np.errstate(invalid="ignore"):
        m = (h < h1) & (l > l1)
    m[n - 1] = False
    out = []
    for t in np.flatnonzero(m):
        seviye, stop = h1[t], l1[t]
        out.append((int(t), stop, seviye + 2 * (seviye - stop), "ic_cubuk", {"emir": seviye, "pencere": IC_PENCERE, "ref": seviye}))
    return out


def mum_yutan(F):
    o, h, l, c = F["o"], F["h"], F["l"], F["c"]
    n = F["n"]
    o1, c1, l1 = kay(o, 1), kay(c, 1), kay(l, 1)
    dip5_prev = kay(pencere_min(l, 5), 1)                  # t-1 dahil son 5 mum
    with np.errstate(invalid="ignore"):
        m = (c1 < o1) & (c > o) & (o <= c1) & (c >= o1) & (l1 <= dip5_prev)
    m[n - 1] = False
    return [(int(t), l[t], c[t] + 2 * (c[t] - l[t]), "yutan", {}) for t in np.flatnonzero(m)]


def mum_yildiz(F):
    o, h, l, c = F["o"], F["h"], F["l"], F["c"]
    n = F["n"]
    o1, c1 = kay(o, 1), kay(c, 1)
    o2, c2, l2, l3 = kay(o, 2), kay(c, 2), kay(l, 2), kay(l, 3)
    with np.errstate(invalid="ignore"):
        b1 = (c2 <= o2 - 0.015 * np.abs(o2)) & (l2 <= l3)             # 1. mum: >=%1.5 dusus; dibi son 2 mumun en dusugu
        b2 = (np.abs(c1 - o1) <= 0.003 * np.abs(o1)) & (np.maximum(o1, c1) <= c2)
        b3 = (c > o) & (c > (o2 + c2) / 2.0)
        m = b1 & b2 & b3
    m[n - 1] = False
    return [(int(t), c[t] - 0.03 * abs(c[t]), c[t] + 0.09 * abs(c[t]), "yildiz", {}) for t in np.flatnonzero(m)]


# ----------------------------------------------------------------------------------------------- FORMASYON
def for_yatay(F):
    h, l, c = F["h"], F["l"], F["c"]
    n = F["n"]
    HI = np.flatnonzero(F["piv_t"])
    out = []
    for k in range(1, len(HI)):
        i1, i2 = int(HI[k - 1]), int(HI[k])
        if not yakin(h[i1], h[i2]):
            continue
        L = max(h[i1], h[i2])
        t = _ilk_kirilim(c, L, i1, i2 + 2, _sonraki_onay(HI, k, n))
        if t is None or t >= n - 1:
            continue
        yuk = L - l[i1:i2 + 1].min()
        if yuk <= 0:
            continue
        out.append((t, min(L, l[t]), L + yuk, "yatay", {}))
    return out


def for_ucgen(F):
    h, l, c = F["h"], F["l"], F["c"]
    n = F["n"]
    HI, LI = np.flatnonzero(F["piv_t"]), np.flatnonzero(F["piv_d"])
    dip_val = F["dip_val"]
    out = []
    # (a) yukselen ucgen (long) / alcalan (short, aynasi): yatay tepe + aradaki >=2 yukselen pivot dip
    for k in range(1, len(HI)):
        i1, i2 = int(HI[k - 1]), int(HI[k])
        if not yakin(h[i1], h[i2]):
            continue
        ara = LI[(LI > i1) & (LI < i2)]
        if len(ara) < 2 or not (np.diff(l[ara]) > 0).all():
            continue
        L = max(h[i1], h[i2])
        t = _ilk_kirilim(c, L, i1, i2 + 2, _sonraki_onay(HI, k, n))
        if t is None or t >= n - 1:
            continue
        st = dip_val[t]
        gen = h[i1] - l[ara[0]]
        if not (st < c[t]) or not (gen > 0):
            continue
        out.append((t, st, L + gen, ("yukselen", "alcalan"), {}))
    # (b) simetrik: son 2 pivot tepe dusuyor, son 2 pivot dip yukseliyor; yukari cizgi disinda kapanis -> long (short: aynasi = alt cizgi)
    olay = sorted([(int(i) + 2, 1, int(i)) for i in HI] + [(int(i) + 2, 0, int(i)) for i in LI])
    tp, dp = [], []
    for e, (conf, tip, i) in enumerate(olay):
        (tp if tip == 1 else dp).append(i)
        bitis = olay[e + 1][0] if e + 1 < len(olay) else n
        if len(tp) < 2 or len(dp) < 2:
            continue
        ta, tb, da, db = tp[-2], tp[-1], dp[-2], dp[-1]
        if not (h[ta] > h[tb] and l[da] < l[db]):
            continue
        ilk = min(ta, da)
        bitis = min(bitis, ilk + UCGEN_MAX_YAS + 1)
        if conf >= bitis:
            continue
        x = np.arange(conf - 1, bitis, dtype=float)
        U = h[ta] + (h[tb] - h[ta]) / (tb - ta) * (x - ta)
        Lo = l[da] + (l[db] - l[da]) / (db - da) * (x - da)
        ok = (c[conf - 1:bitis] > U) & (U > Lo)
        if not ok.any():
            continue
        j = int(np.argmax(ok))
        if j == 0:                                   # onay aninda zaten disarida: taze kirilim degil
            continue
        t = conf - 1 + j
        st = dip_val[t]
        gen = h[ta] - l[da]
        if t >= n - 1 or not (st < c[t]) or not (gen > 0):
            continue
        out.append((t, st, U[j] + gen, ("simetrik", "simetrik"), {}))
    return sorted(out, key=lambda x: x[0])


def for_ikili_dip(F):
    h, l, c = F["h"], F["l"], F["c"]
    n = F["n"]
    LI = np.flatnonzero(F["piv_d"])
    out = []
    for k in range(1, len(LI)):
        i1, i2 = int(LI[k - 1]), int(LI[k])
        if not (5 <= i2 - i1 <= 25) or not yakin(l[i1], l[i2]):
            continue
        boyun = h[i1:i2 + 1].max()
        dip = min(l[i1], l[i2])
        t = _ilk_kirilim(c, boyun, i1, i2 + 2, _sonraki_onay(LI, k, n))
        if t is None or t >= n - 1:
            continue
        out.append((t, dip, boyun + (boyun - dip), ("ikili_dip", "ikili_tepe"), {}))
    return out


def for_obo(F):
    """long = TOBO (3 pivot dip, orta en dusuk), short = OBO (ayna). Boyun: omuz-bas-omuz arasindaki en yuksek iki pivot tepeden gecen dogru.
    Onceki hareket sarti: >= 2 * (bas-boyun). Stop = bas ucu. Hedef = boyun(t) + bas-boyun."""
    h, l, c = F["h"], F["l"], F["c"]
    n = F["n"]
    LI, HI = np.flatnonzero(F["piv_d"]), np.flatnonzero(F["piv_t"])
    out = []
    for k in range(2, len(LI)):
        ia, ib, ic = int(LI[k - 2]), int(LI[k - 1]), int(LI[k])
        la, lb, lc = l[ia], l[ib], l[ic]
        if not (lb < la and lb < lc and yakin(la, lc)):
            continue
        p1s, p2s = HI[(HI > ia) & (HI < ib)], HI[(HI > ib) & (HI < ic)]
        if len(p1s) == 0 or len(p2s) == 0:
            continue
        p1, p2 = int(p1s[np.argmax(h[p1s])]), int(p2s[np.argmax(h[p2s])])
        egim = (h[p2] - h[p1]) / (p2 - p1)
        boyun_b = h[p1] + egim * (ib - p1)
        D = boyun_b - lb
        w = ic - ia
        if D <= 0 or ia - w < 0:
            continue
        onceki = h[ia - w:ia + 1].max() - la
        if onceki < 2 * D:
            continue
        line = h[p1] + egim * (np.arange(n, dtype=float) - p1)
        t = _ilk_kirilim(c, line, ic, ic + 2, _sonraki_onay(LI, k, n))
        if t is None or t >= n - 1:
            continue
        out.append((t, lb, line[t] + D, ("tobo", "obo"), {}))
    return out


# ----------------------------------------------------------------------------------------------- INDIKATOR
def ind_rsi(F):
    l, c, rsi = F["l"], F["c"], F["rsi"]
    n = F["n"]
    dip10 = pencere_min(l, 10)
    with np.errstate(invalid="ignore"):
        m = (rsi < 30) & (kay(rsi, 1) >= 30) & (F["s50"] > F["s200"]) & (dip10 < c)
        cx = rsi > 70
    m[n - 1] = False
    return [(int(t), dip10[t], None, "rsi", {"cx": cx}) for t in np.flatnonzero(m)]


def ind_ma_kesisim(F):
    n = F["n"]
    a, b = F["s50"], F["s200"]
    a1, b1 = kay(a, 1), kay(b, 1)
    with np.errstate(invalid="ignore"):
        yukari = (a > b) & (a1 <= b1)
        asagi = (a < b) & (a1 >= b1)
    yukari[n - 1] = False
    atr = F["atr"]
    return [(int(t), None, None, "ma_kesisim", {"cx": asagi, "rbirim": 2 * atr[t]}) for t in np.flatnonzero(yukari)]


def ind_boll(F):
    l, c = F["l"], F["c"]
    n = F["n"]
    alt = F["s20"] - 2 * F["sd20"]
    hd = kay(F["s20"], 1)                                   # bar j icin emir seviyesi = j-1 kapanisindaki orta bant
    with np.errstate(invalid="ignore"):
        m = (l <= alt) & (l < c)
    m[n - 1] = False
    return [(int(t), l[t], None, "boll", {"hd": hd, "ha_hedef": F["s20"][t]}) for t in np.flatnonzero(m)]


def ind_fiyat_ma(F):
    c, s = F["c"], F["s50"]
    n = F["n"]
    with np.errstate(invalid="ignore"):
        yukari = (c > s) & (kay(c, 1) <= kay(s, 1))
        cx = c < s
    yukari[n - 1] = False
    atr = F["atr"]
    return [(int(t), None, None, "fiyat_ma", {"cx": cx, "rbirim": 2 * atr[t]}) for t in np.flatnonzero(yukari)]


SETUPLAR = {
    "MUM_PINBAR": (mum_pinbar, 48), "MUM_IC_CUBUK": (mum_ic_cubuk, 48), "MUM_YUTAN": (mum_yutan, 48), "MUM_YILDIZ": (mum_yildiz, 20),
    "FOR_YATAY_KIRILIM": (for_yatay, 48), "FOR_UCGEN": (for_ucgen, 48), "FOR_IKILI_DIP": (for_ikili_dip, 48), "FOR_OBO": (for_obo, 48),
    "IND_RSI_3070": (ind_rsi, 48), "IND_MA_KESISIM": (ind_ma_kesisim, 48), "IND_BOLL_DONUS": (ind_boll, 48), "IND_FIYAT_MA": (ind_fiyat_ma, 48),
}


def kategori(kod: str) -> str:
    return KATEGORI[kod.split("_")[0]]


def gercek_sinyaller(kod: str, Fd: dict) -> list:
    """-> [(t, d, sp, sa, ha, etiket)] gercek fiyat. sp: simulasyon_v3 sozlugu; sa/ha: stop/hedef mesafesi (ATR cinsinden; yoksa nan/inf)."""
    fn, _ = SETUPLAR[kod]
    out = []
    for d in (1, -1):
        F = Fd[d]
        atr, c = F["atr"], F["c"]
        onbellek, gorulen = {}, set()
        for t, stop, hedef, et, ex in fn(F):
            at = atr[t]
            if not (at > 0) or t in gorulen:                  # ayni t'de iki alt tur (or. yukselen + simetrik ucgen): ilki
                continue
            gorulen.add(t)
            sp = {"stop": None if stop is None else d * float(stop), "hedef": None if hedef is None else d * float(hedef)}
            if "emir" in ex:
                sp["emir"] = d * float(ex["emir"])
                sp["pencere"] = ex["pencere"]
            for a in ("hd", "cx"):
                if a in ex:
                    k = (a, id(ex[a]))
                    if k not in onbellek:
                        onbellek[k] = d * ex[a] if a == "hd" else ex[a]
                    sp[a] = onbellek[k]
            if "rbirim" in ex:
                sp["rbirim"] = float(ex["rbirim"])
            ref = ex.get("ref", c[t])
            sa = (ref - stop) / at if stop is not None else NAN
            hh = hedef if hedef is not None else ex.get("ha_hedef")
            ha = (hh - ref) / at if hh is not None else float("inf")
            etiket = et[0 if d == 1 else 1] if isinstance(et, tuple) else et
            out.append((t, d, sp, float(sa), float(ha), etiket))
    out.sort(key=lambda x: (x[0], -x[1]))
    return out
