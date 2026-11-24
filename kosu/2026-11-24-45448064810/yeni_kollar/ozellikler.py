"""Zaman dilimi ozellikleri (tek cift, tek yon). Long mantigi yazilir; short = fiyat aynalamasi (o,h,l,c -> -o,-l,-h,-c), boylece sekil/seviye/gosterge
tek kodla aynalanir. Hicbir ozellik t anindan sonraki veriye bakmaz (testle kanitlanir)."""
from __future__ import annotations

import numpy as np

import gostergeler as G

TF_NS = {"15m": 15 * 60 * 10**9, "1h": 3600 * 10**9, "4h": 4 * 3600 * 10**9, "1d": 86400 * 10**9}
UST = {"15m": ["1h", "4h"], "1h": ["4h"], "4h": ["1d"], "1d": []}
GUN_NS = TF_NS["1d"]
HAFTA_NS = 7 * GUN_NS
PZT_OFSET = 4 * GUN_NS          # 1970-01-05 (pazartesi) 00:00 UTC
FON_ESIK = 0.0005
FON_BAYAT_NS = 24 * 3600 * 10**9


def aynala(D: dict, yon: int) -> dict:
    """yon=+1 ayni; -1 aynali kopya."""
    if yon == 1:
        return D
    return {"t": D["t"], "o": -D["o"], "h": -D["l"], "l": -D["h"], "c": -D["c"], "v": D["v"]}


def kaydir(x: np.ndarray, k: int, dolgu=np.nan) -> np.ndarray:
    out = np.full(len(x), dolgu, dtype=float)
    if k < len(x):
        out[k:] = x[:len(x) - k]
    return out


def ust_durum(U: dict, tf_up: str) -> dict:
    """Ust zaman dilimi serisi (yon ayarli) -> durum(+1 yukari/-1 asagi/0 yatay), son kesinlesmis dip pivotu, kapanis zamani.
    Yukari: c > EMA50 ve EMA50[t] > EMA50[t-5]. 1d icin (kendi EMA50/200): c>EMA50 ve EMA50>EMA200.
    'gecerli' = EMA'lar hazir; hazir degilse durum 'yatay' degil 'gecersiz' sayilir (filtreden gecmez)."""
    e50 = G.ema(U["c"], 50)
    if tf_up == "1d":
        e200 = G.ema(U["c"], 200)
        yuk = (U["c"] > e50) & (e50 > e200)
        asa = (U["c"] < e50) & (e50 < e200)
        gecerli = ~np.isnan(e50) & ~np.isnan(e200)
    else:
        e5 = kaydir(e50, 5)
        yuk = (U["c"] > e50) & (e50 > e5)
        asa = (U["c"] < e50) & (e50 < e5)
        gecerli = ~np.isnan(e50) & ~np.isnan(e5)
    durum = np.where(yuk, 1, np.where(asa, -1, 0)).astype(np.int8)
    _, dip = G.kesinlesmis_son(G.pivot_dip(U["l"]), U["l"])
    return {"durum": durum, "gecerli": gecerli, "dip": dip, "kapanis": U["t"] + TF_NS[tf_up]}


def eslestir(t_karar_ns: np.ndarray, ust: dict):
    """Karar anina (mum kapanisi) kadar KAPANMIS son ust mum indeksi. -> (idx, gecerli)."""
    idx = np.searchsorted(ust["kapanis"], t_karar_ns, side="right") - 1
    return np.maximum(idx, 0), idx >= 0


def onceki_donem(t, x, birim_ns, ofset, fn):
    """Biten onceki takvim doneminin (gun/hafta, UTC) fn (max/min) degeri; bu donemin mumlarina yayilir. Ilk donemde NaN."""
    p = (t - ofset) // birim_ns
    basla = np.r_[0, np.flatnonzero(np.diff(p) != 0) + 1]
    agg = fn.reduceat(x, basla)
    sira = np.cumsum(np.r_[0, np.diff(p) != 0])
    onc = np.r_[np.nan, agg][sira]          # sira k -> agg[k-1]
    return onc


def hafta_vwap(t, h, l, c, v):
    """Haftalik VWAP (UTC pazartesi), t anindaki deger yalniz t-1 ve oncesi mumlardan (bu haftanin ilk mumunda NaN)."""
    tp = (h + l + c) / 3.0
    p = (t - PZT_OFSET) // HAFTA_NS
    basla_idx = np.r_[0, np.flatnonzero(np.diff(p) != 0) + 1]
    sira = np.cumsum(np.r_[0, np.diff(p) != 0])
    ws = basla_idx[sira]                     # haftanin ilk mum indeksi
    csv = np.r_[0.0, np.cumsum(tp * v)]      # csv[k] = ilk k mumun toplami
    cv = np.r_[0.0, np.cumsum(v)]
    i = np.arange(len(t))
    pay = csv[i] - csv[ws]                   # [ws, i-1]
    payda = cv[i] - cv[ws]
    with np.errstate(divide="ignore", invalid="ignore"):
        r = pay / payda
    return np.where((i > ws) & (payda > 0), r, np.nan)


def hacim_orani(v, n=20):
    cs = np.r_[0.0, np.cumsum(v)]
    i = np.arange(len(v))
    lo = np.maximum(i - n, 0)
    cnt = i - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        ort = (cs[i] - cs[lo]) / cnt
        r = v / ort
    return np.where((cnt >= n) & (ort > 0), r, np.nan)


def fonlama_veto(t_open, tf, fon, yon):
    """Karar aninda (mum kapanisi) once kesinlesmis son fonlama: yon*oran > %0,05 ise veto. Veri yok/bayat (>24s) ise veto yok."""
    n = len(t_open)
    if fon is None:
        return np.zeros(n, bool)
    kapanis = t_open + TF_NS[tf]
    j = np.searchsorted(fon["t"], kapanis, side="right") - 1
    jj = np.maximum(j, 0)
    taze = (j >= 0) & (kapanis - fon["t"][jj] <= FON_BAYAT_NS)
    return taze & (yon * fon["r"][jj] > FON_ESIK)


def ozellik(D: dict, tf: str, ustler: dict, fon, yon: int) -> dict:
    """D: ham seri (gercek fiyat); ustler: {tf_up: ham ust seri}; fon: {t, r} ya da None; yon: +1/-1. Cikti long-uzayindadir."""
    S = aynala(D, yon)
    o, h, l, c, v, t = S["o"], S["h"], S["l"], S["c"], S["v"], S["t"]
    n = len(t)
    F = {"yon": yon, "n": n, "t": t, "o": o, "h": h, "l": l, "c": c, "v": v, "tf": tf}
    F["atr"] = G.atr(h, l, c, 14)
    F["rsi"] = G.rsi(c, 14)
    F["mh"] = G.macd(c)[2]
    F["vr"] = hacim_orani(v)
    F["piv_dip"] = G.pivot_dip(l)
    F["piv_tepe"] = G.pivot_tepe(h)
    kapanis = t + TF_NS[tf]
    # ust ZD durumu
    gevsek = np.ones(n, bool)
    siki = np.ones(n, bool)
    dipler, dip_adlari = [], []
    if tf == "1d":
        st = ust_durum(S, "1d")
        gevsek, siki = st["gecerli"] & (st["durum"] != -1), st["durum"] == 1
        dipler.append(st["dip"])
    else:
        for tu in UST[tf]:
            if tu not in ustler:
                gevsek = np.zeros(n, bool)
                siki = np.zeros(n, bool)
                continue
            st = ust_durum(aynala(ustler[tu], yon), tu)
            idx, ok = eslestir(kapanis, st)
            gevsek &= ok & st["gecerli"][idx] & (st["durum"][idx] != -1)
            siki &= ok & (st["durum"][idx] == 1)
            dipler.append(np.where(ok, st["dip"][idx], np.nan))
            dip_adlari.append(f"ust_dip_{tu}")
    F["zd_gevsek"], F["zd_siki"] = gevsek, siki
    # seviyeler (destek tarafi); karsi seviye (hedef icin) onceki gun tepesi
    F["pdl"] = onceki_donem(t, l, GUN_NS, 0, np.minimum)
    F["pdh"] = onceki_donem(t, h, GUN_NS, 0, np.maximum)
    F["pwl"] = onceki_donem(t, l, HAFTA_NS, PZT_OFSET, np.minimum)
    F["vwap"] = hafta_vwap(t, h, l, c, v)
    seviyeler = [F["pdl"], F["pwl"], F["vwap"]] + dipler
    adlar = ["pdl", "pwl", "vwap"] + dip_adlari
    if tf == "1d":
        # 1d'de "onceki gun dibi" formasyonun kendi mumu olur (sart kendiliginden saglanir): listeden cikarildi
        _, own = G.kesinlesmis_son(F["piv_dip"], l)
        seviyeler = [F["pwl"], F["vwap"], own]
        adlar = ["pwl", "vwap", "kendi_pivot"]
    F["seviyeler"] = seviyeler
    F["seviye_adlari"] = adlar
    F["tepe_idx"], F["tepe_val"] = G.kesinlesmis_son(F["piv_tepe"], h)
    F["dip_idx"], F["dip_val"] = G.kesinlesmis_son(F["piv_dip"], l)
    F["fon_veto"] = fonlama_veto(D["t"], tf, fon, yon)
    return F
