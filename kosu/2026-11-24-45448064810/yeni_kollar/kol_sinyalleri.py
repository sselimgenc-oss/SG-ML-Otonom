"""Uc kolun sinyal uretimi (long uzayinda; short aynalanmis ozellikle ayni kod). Karar t kapanisinda. cfg = teyit bayraklari
(True = teyit acik): zd, seviye, hacim, fonlama, maliyet. rr >= 1.5 ve stop > 0 her zaman gecerli (sekil/stop-hedef tanimi).
Cikti: (t_idx, stop_f, hedef_f, etiket) dizileri (f = long uzayi; gercek fiyat = yon * deger; etiket = dokum icin sekil/seviye turu).
Tur 2: MF1 hacim+ust ZD teyidi yok; GF1 stop = boyun - 1 ATR; IN1 gevsek eslesme, seviye+hacim teyidi yok; 15m kapali."""
from __future__ import annotations

import numpy as np

import ozellikler as OZ

MAX_MUM = {"MF1": 16, "GF1": 48, "IN1": 24}
RR_MIN = 1.5
HEDEF_R_MF1 = 3.0           # MF1 hedef ust siniri (giris + 3R); onceden sabit, taranmaz
MALIYET_TABAN = 0.006
CFG_TAM = {"zd": True, "seviye": True, "hacim": True, "fonlama": True, "maliyet": True}
CFG_HIC = {k: False for k in CFG_TAM}
UYGULANAN = {"MF1": ["seviye", "fonlama", "maliyet"], "GF1": ["zd", "hacim", "fonlama", "maliyet"],
             "IN1": ["zd", "fonlama", "maliyet"]}


def cfg_listesi(kol: str) -> dict[str, dict]:
    """ad -> cfg: tam, her teyit tek tek kapali, hic_teyit."""
    out = {"tam": dict(CFG_TAM)}
    for k in UYGULANAN[kol]:
        c = dict(CFG_TAM)
        c[k] = False
        out[f"{k}_kapali"] = c
    out["hic_teyit"] = dict(CFG_HIC)
    return out


def _sh(x, k):
    return OZ.kaydir(x, k)


def zd_maske(F, kol):
    """GF1/IN1: ust ZD yukari/yatay (EMA hazir degilse gecersiz)."""
    return F["zd_gevsek"]


def ortak_hazir(F):
    atr = F["atr"]
    return atr > 0


def _maliyet_ok(c, stop, cfg):
    if cfg["maliyet"]:
        return (c - stop) / np.abs(c) >= MALIYET_TABAN
    return (c - stop) > 0


# -------------------------------------------------------------------------------------------------- MF1
def mf1_ham(F):
    o, h, l, c, atr = F["o"], F["h"], F["l"], F["c"], F["atr"]
    n = F["n"]
    o1, h1, l1, c1 = _sh(o, 1), _sh(h, 1), _sh(l, 1), _sh(c, 1)
    o2, h2, l2, c2 = _sh(o, 2), _sh(h, 2), _sh(l, 2), _sh(c, 2)
    govde = np.abs(c - o)
    aralik = h - l
    with np.errstate(invalid="ignore"):
        yutan = (c1 < o1) & (c > o) & (o <= c1) & (c >= o1)
        yutan_dip, yutan_tepe = np.minimum(l, l1), np.maximum(h, h1)
        alt = np.minimum(o, c) - l
        ust = h - np.maximum(o, c)
        cekic = (aralik > 0) & (alt >= 2 * govde) & (ust <= 0.1 * aralik) & (c >= l + aralik * 2.0 / 3.0)
        cekic_dip, cekic_tepe = l, h
        g2, r2 = np.abs(c2 - o2), h2 - l2
        yildiz = (c2 < o2) & (r2 > 0) & (g2 >= 0.6 * r2) & (np.abs(c1 - o1) <= 0.3 * g2) & (c > o) & (c > (o2 + c2) / 2.0)
        yildiz_dip, yildiz_tepe = np.minimum(np.minimum(l, l1), l2), np.maximum(np.maximum(h, h1), h2)
    # karsi seviye (onceki gun tepesi / son onayli tepe pivotu), kapanisin ustunde; sinyalde giris + 3R ile sinirlanir
    inf = np.inf
    a1 = np.where(F["pdh"] > c, F["pdh"], inf)
    a2 = np.where(F["tepe_val"] > c, F["tepe_val"], inf)
    hedef = np.minimum(a1, a2)
    adlar = F["seviye_adlari"]
    sek = []
    # seviye, formasyonun ilk mumundan ONCE bilinen deger: yutan t-2, cekic t-1, yildiz t-3
    for ad, m, dip, tepe, kay in (("yutan", yutan, yutan_dip, yutan_tepe, 2), ("cekic", cekic, cekic_dip, cekic_tepe, 1),
                                  ("yildiz", yildiz, yildiz_dip, yildiz_tepe, 3)):
        with np.errstate(invalid="ignore"):
            seviye = np.zeros(n, bool)
            seviye_ad = np.full(n, "yok", dtype=object)
            for L0, lad in zip(F["seviyeler"], adlar):
                L = _sh(L0, kay)
                ok = (dip <= L + 0.3 * atr) & (dip >= L - 1.0 * atr) & (c > L)      # delme en cok 1 ATR
                seviye_ad[ok & ~seviye] = lad
                seviye |= ok
            m = m & ((tepe - dip) >= atr)
        sek.append({"ad": ad, "maske": np.nan_to_num(m, nan=0).astype(bool), "stop": dip - 0.2 * atr, "seviye": seviye, "seviye_ad": seviye_ad})
    return {"sekiller": sek, "hedef": hedef}


def mf1_sinyal(F, ham, cfg):
    c, atr, n = F["c"], F["atr"], F["n"]
    ok = ortak_hazir(F)
    ortak = np.ones(n, bool)
    if cfg["fonlama"]:
        ortak &= ~F["fon_veto"]
    alinan = np.zeros(n, bool)
    t_l, s_l, h_l, e_l = [], [], [], []
    for s in ham["sekiller"]:
        stop = s["stop"]
        with np.errstate(invalid="ignore", divide="ignore"):
            hedef = np.minimum(ham["hedef"], c + HEDEF_R_MF1 * (c - stop))      # yakin olan: karsi seviye ya da giris + 3R
            rr = (hedef - c) / (c - stop)
            m = s["maske"] & ok & ortak & np.isfinite(hedef) & (rr >= RR_MIN) & _maliyet_ok(c, stop, cfg)
        if cfg["seviye"]:
            m &= s["seviye"]
        m[n - 1] = False
        m &= ~alinan
        alinan |= m
        i = np.flatnonzero(m)
        t_l.append(i); s_l.append(stop[i]); h_l.append(hedef[i]); e_l.append(s["seviye_ad"][i])
    return _birlestir(t_l, s_l, h_l, e_l)


def _birlestir(t_l, s_l, h_l, e_l):
    if not t_l:
        return np.zeros(0, np.int64), np.zeros(0), np.zeros(0), np.zeros(0, dtype=object)
    t = np.concatenate(t_l).astype(np.int64)
    sira = np.argsort(t, kind="stable")
    return t[sira], np.concatenate(s_l)[sira], np.concatenate(h_l)[sira], np.concatenate(e_l).astype(object)[sira]


# -------------------------------------------------------------------------------------------------- GF1
def _kurulumlar_gf1(F, pencere=30):
    """Sekil kurulumlari (teyitsiz): (t0, boyun, iptal, hedef, tur). t0 = son pivotun kesinlesme anidir (pivot idx + 3).
    iptal = formasyon dibi - 0,2 ATR: kapanis bunun altina inerse kurulum iptal (islem stopu degil; islem stopu = boyun - 1 ATR)."""
    h, l, c, atr = F["h"], F["l"], F["c"], F["atr"]
    n = F["n"]
    LI = np.flatnonzero(F["piv_dip"])
    HI = np.flatnonzero(F["piv_tepe"])
    ol = [(i + 3, 0, i) for i in LI if i + 3 < n] + [(i + 3, 1, i) for i in HI if i + 3 < n]
    ol.sort()
    atrl = atr
    cs_atr = np.r_[0.0, np.cumsum(np.nan_to_num(atr))]
    kur = {}
    lows, highs = [], []        # kesinlesmis pivot idx listeleri

    def daralma(basla, t0):
        mid = (basla + t0) // 2
        if mid <= basla or t0 <= mid:
            return False
        sol = (cs_atr[mid] - cs_atr[basla]) / (mid - basla)
        sag = (cs_atr[t0 + 1] - cs_atr[mid]) / (t0 + 1 - mid)
        return sag < sol

    def ekle(t0, boyun, stop, yuk, tur, basla, son_idx):
        a0 = atrl[t0]
        if not (a0 > 0) or yuk <= 0:
            return
        if not daralma(basla, t0):
            return
        if (c[son_idx + 1:t0 + 1] < stop).any():
            return
        anahtar = (tur, round(boyun, 10), round(stop, 10))
        if anahtar not in kur:
            kur[anahtar] = (t0, boyun, stop, boyun + yuk, tur)

    def arada_tepe(a, b, t0):
        """(a,b) araligindaki en yuksek tepe pivotu (kesinlesmis)."""
        k = [j for j in reversed(highs) if a < j < b]
        if not k:
            return None
        return max(k, key=lambda j: h[j])

    for t0, tip, i in ol:
        a0 = atr[t0]
        if not (a0 > 0):
            (lows if tip == 0 else highs).append(i)
            continue
        if tip == 0:
            if lows:
                i1 = lows[-1]
                if 8 <= i - i1 <= 60 and abs(l[i] - l[i1]) <= 0.5 * a0:
                    boyun = h[i1:i + 1].max()
                    if boyun - max(l[i], l[i1]) >= 2 * a0:
                        ekle(t0, boyun, l[i] - 0.2 * a0, boyun - min(l[i], l[i1]), "ikili_dip", i1, i)
            if len(lows) >= 2:
                a, b = lows[-2], lows[-1]
                if 5 <= b - a <= 60 and 5 <= i - b <= 60 and min(l[a], l[i]) - l[b] >= 0.5 * a0 and abs(l[a] - l[i]) <= 1.0 * a0:
                    j1, j2 = arada_tepe(a, b, t0), arada_tepe(b, i, t0)
                    if j1 is not None and j2 is not None and abs(h[j1] - h[j2]) <= 1.0 * a0:
                        boyun = max(h[j1], h[j2])
                        ekle(t0, boyun, l[i] - 0.2 * a0, boyun - l[b], "tobo", a, i)
            lows.append(i)
        else:
            highs.append(i)
        # yukselen ucgen: son 2 tepe yatay (0,3 ATR), son 2 dip yukselen
        if len(highs) >= 2 and len(lows) >= 2:
            j1, j2 = highs[-2], highs[-1]
            i1, i2 = lows[-2], lows[-1]
            basla = min(j1, i1)
            if t0 - basla <= 80 and abs(h[j2] - h[j1]) <= 0.3 * a0 and l[i2] > l[i1]:
                boyun = max(h[j1], h[j2])
                if boyun > l[i2]:
                    ekle(t0, boyun, l[i2] - 0.2 * a0, boyun - l[i1], "ucgen", basla, max(j2, i2))
    return sorted(kur.values())


def _cikti(cikti):
    ts = sorted(cikti)
    return (np.array(ts, np.int64), np.array([cikti[t][0] for t in ts], float), np.array([cikti[t][1] for t in ts], float),
            np.array([cikti[t][2] for t in ts], dtype=object))


def gf1_ham(F):
    return {"kur": _kurulumlar_gf1(F)}


def gf1_sinyal(F, ham, cfg, pencere=30):
    n = F["n"]
    o, h, l, c, atr = F["o"].tolist(), F["h"].tolist(), F["l"].tolist(), F["c"].tolist(), F["atr"].tolist()
    ortak = np.ones(n, bool)
    if cfg["zd"]:
        ortak &= zd_maske(F, "GF1")
    if cfg["fonlama"]:
        ortak &= ~F["fon_veto"]
    ortak = ortak.tolist()
    vr = np.nan_to_num(F["vr"], nan=0).tolist()
    hac = cfg["hacim"]
    mal = cfg["maliyet"]
    cikti = {}
    for t0, boyun, iptal, hedef, tur in ham["kur"]:
        bk = -1
        for t in range(t0, min(n - 1, t0 + pencere) + 1):
            ct = c[t]
            a = atr[t]
            if ct < iptal:
                break
            if bk >= 0 and ct < boyun:          # sahte kirilim: kurulum iptal
                break
            esik = boyun + 0.3 * a
            A = B = False
            if ct >= esik:
                if bk < 0:
                    bk = t
                rng = h[t] - l[t]
                A = (ct - boyun <= 1.5 * a) and (vr[t] >= 1.5 or not hac) and rng > 0 and ct >= l[t] + 0.75 * rng
            if bk >= 0 and bk < t <= bk + 10 and l[t] <= boyun and ct > boyun and ct > o[t]:
                B = True
            if bk >= 0 and t > bk + 10:
                break
            if (A or B) and ortak[t]:
                if t in cikti:
                    break                      # ayni karar mumunda baska kurulum zaten girdi
                stop = boyun - a                # Tur 2: boyun - 1 ATR (giris mumunun ATR'si); "risk > 3 ATR" sarti kalkti
                risk = ct - stop
                if risk <= 0 or hedef <= ct or (hedef - ct) / risk < RR_MIN:
                    continue
                if mal and risk / abs(ct) < MALIYET_TABAN:
                    continue
                cikti[t] = (stop, hedef, tur)
                break
    return _cikti(cikti)


# -------------------------------------------------------------------------------------------------- IN1
def in1_ham(F):
    """Ikinci dip olaylari (teyitsiz sekil kosullari): (i2, l2, hedef). Ikinci dip, 5-40 mum gerideki HER onayli dip pivotuyla eslenebilir;
    kosullari saglayan en yakin olan alinir (kosul: fiyatta >= 0,2 ATR daha dusuk, RSI >= +3 ve ilk dipte < 35, MACD hist. yuksek, arada tepe pivotu)."""
    h, l, atr, rsi, mh = F["h"], F["l"], F["atr"], F["rsi"], F["mh"]
    n = F["n"]
    LI = np.flatnonzero(F["piv_dip"])
    HI = np.flatnonzero(F["piv_tepe"])
    ev = []
    for k in range(1, len(LI)):
        i2 = int(LI[k])
        if i2 + 3 >= n:
            continue
        a2 = atr[i2]
        if not (a2 > 0):
            continue
        for k1 in range(k - 1, -1, -1):             # en yakin once
            i1 = int(LI[k1])
            if i2 - i1 > 40:
                break
            if i2 - i1 < 5:
                continue
            with np.errstate(invalid="ignore"):
                if not (l[i2] <= l[i1] - 0.2 * a2 and rsi[i2] >= rsi[i1] + 3 and rsi[i1] < 35 and mh[i2] > mh[i1]):
                    continue
            ara = HI[np.searchsorted(HI, i1, "right"):np.searchsorted(HI, i2, "left")]
            if len(ara) == 0:
                continue
            ev.append((i2, float(l[i2]), float(h[ara[np.argmax(h[ara])]])))
            break
    return {"ev": ev}


def in1_sinyal(F, ham, cfg, pencere=8):
    """Tur 2: seviye ve hacim teyidi yok (cfg'deki bayraklari yok sayilir); ust ZD, fonlama vetosu, maliyet tabani kalir."""
    n = F["n"]
    h, c, atr = F["h"], F["c"], F["atr"]
    ortak = np.ones(n, bool)
    if cfg["zd"]:
        ortak &= zd_maske(F, "IN1")
    if cfg["fonlama"]:
        ortak &= ~F["fon_veto"]
    cikti = {}
    for i2, l2, hedef in ham["ev"]:
        for t in range(i2 + 3, min(n - 1, i2 + pencere) + 1):
            a = atr[t]
            if not (a > 0):
                continue
            stop = l2 - 0.3 * a
            if c[t] < stop:
                break
            if c[t] > h[i2 + 1:t].max() and ortak[t] and t not in cikti:
                risk = c[t] - stop
                if hedef <= c[t] or (hedef - c[t]) / risk < RR_MIN:
                    continue
                if cfg["maliyet"] and risk / abs(c[t]) < MALIYET_TABAN:
                    continue
                cikti[t] = (stop, hedef, "gevsek_eslesme")
                break
    return _cikti(cikti)


KOLLAR = {"MF1": (mf1_ham, mf1_sinyal), "GF1": (gf1_ham, gf1_sinyal), "IN1": (in1_ham, in1_sinyal)}
