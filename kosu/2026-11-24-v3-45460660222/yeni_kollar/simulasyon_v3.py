"""v3 (kitap setuplari) islem simulasyonu. simulasyon.py ile AYNI kurallar (stop onceligi, bosluk dolumu, masraf, fonlama, mum boslugu, veri sonu);
ek olarak kitaplardaki cikis bicimleri:
  * stop yok (IND_MA_KESISIM, IND_FIYAT_MA): R birimi = sp["rbirim"] (gercek fiyat mesafesi; cikisi ETKILEMEZ, yalniz R olcegi).
  * hedef yok ya da sabit ya da mum basina degisen (sp["hd"]: bar j icin emir seviyesi, gercek fiyat, NaN = o barda hedef yok).
  * sinyal cikisi (sp["cx"]: bool dizi; j kapanisinda True ise j+1 ACILISINDA cikilir; karar t kapanisi -> islem t+1 acilisi kurali cikis icin de).
  * bekleyen emir girisi (IC_CUBUK): emir_dolum().
Donus: (netR, tur, tutma, giris_idx, cikis_idx, fonlama_R, son_karar_min). tur: 0 stop, 1 hedef, 2 zaman, 3 sinyal cikisi.
son_karar_min = bu indeksten itibaren (dahil) yeni karar verilebilir (acilista cikista cikis_idx - 1: ayni acilista ters yone gecis serbest)."""
from __future__ import annotations

import numpy as np

TUR = {0: "stop", 1: "hedef", 2: "zaman", 3: "sinyal"}


def emir_dolum(S: dict, t: int, d: int, seviye: float, pencere: int, step_ns: int):
    """Karar t kapanisinda konan alis(d=1)/satis(d=-1) STOP emri; t+1..t+pencere mumlarinda gecerli.
    -> (giris_idx, dolum_fiyati) ya da None. Bosluk: acilis seviyeyi gectiyse acilistan dolar."""
    n = len(S["t"])
    for b in range(t + 1, min(n, t + pencere + 1)):
        if S["t"][b] - S["t"][b - 1] != step_ns:
            return None
        if d == 1 and S["h"][b] >= seviye:
            return b, max(S["o"][b], seviye)
        if d == -1 and S["l"][b] <= seviye:
            return b, min(S["o"][b], seviye)
    return None


def simule_v3(S: dict, e: int, fill_ham: float, d: int, sp: dict, maxmum: int, mal: tuple, step_ns: int, fonh=None, min_risk: float = 0.0):
    n = len(S["t"])
    if e >= n:
        return None
    taker, k_g, k_c, k_s = mal
    o, h, l, c = S["o"], S["h"], S["l"], S["c"]
    stop, hedef, hd, cx, rb = sp.get("stop"), sp.get("hedef"), sp.get("hd"), sp.get("cx"), sp.get("rbirim")
    if stop is not None and d * (fill_ham - stop) <= 0:
        return None                                   # giris stopun ustten/yanlis yanda
    if hedef is not None and d * (hedef - fill_ham) <= 0:
        return None
    bit = min(n, e + maxmum)
    m = bit - e
    giris = fill_ham * (1 + d * k_g)
    if hd is not None:
        tg = hd[e:bit].astype(float)
        if np.isfinite(tg[0]) and d * (tg[0] - fill_ham) <= 0:
            return None
    elif hedef is not None:
        tg = np.full(m, float(hedef))
    else:
        tg = None
    if d == 1:
        sh = l[e:bit] <= stop if stop is not None else np.zeros(m, bool)
        with np.errstate(invalid="ignore"):
            th = h[e:bit] >= tg if tg is not None else np.zeros(m, bool)
    else:
        sh = h[e:bit] >= stop if stop is not None else np.zeros(m, bool)
        with np.errstate(invalid="ignore"):
            th = l[e:bit] <= tg if tg is not None else np.zeros(m, bool)
    ks = int(np.argmax(sh)) if sh.any() else m
    kh = int(np.argmax(th)) if th.any() else m
    kx = m
    if cx is not None and m > 1:
        w = np.flatnonzero(cx[e:bit - 1])              # j kapanisinda sinyal -> j+1 acilisi; son mumda zaman stopu zaten kapanista
        if len(w):
            kx = int(w[0]) + 1
    kint = min(ks, kh)
    if kint < m and kint < kx:                        # mum ici olay: stop/hedef
        if ks <= kh:                                  # ayni mumda ikisi de: stop
            k, fill, tur, kay = ks, stop, 0, k_s
            if k > 0 and d * (o[e + k] - stop) < 0:
                fill = o[e + k]
        else:
            k, tur, kay = kh, 1, k_c
            fill = tg[k]
            if k > 0 and d * (o[e + k] - fill) > 0:
                fill = o[e + k]
        t_cik = S["t"][e + k] + step_ns
        son_min = e + k
    elif kx < m:                                      # sinyal cikisi: j+1 acilisinda
        k, tur, kay = kx, 3, k_c
        fill = o[e + k]
        t_cik = S["t"][e + k]
        son_min = e + k - 1
    else:
        if m < maxmum:
            return None                               # veri bitti, zaman stopuna ulasilamadi
        k, tur, kay = m - 1, 2, k_c
        fill = c[bit - 1]
        t_cik = S["t"][e + k] + step_ns
        son_min = e + k
    cik = fill * (1 - d * kay)
    risk = d * (giris - stop) if stop is not None else rb
    if risk is None or not (risk > 0):
        return None
    if stop is not None and risk / giris < min_risk:
        return None
    if k > 0 and (np.diff(S["t"][e:e + k + 1]) != step_ns).any():
        return None                                   # tutma penceresinde mum boslugu
    ham = d * (cik - giris) - taker * (giris + cik)
    fR = 0.0
    if fonh is not None:
        ft = fonh["t"]
        lo = np.searchsorted(ft, S["t"][e], side="right")
        hi = np.searchsorted(ft, t_cik, side="right" if tur != 3 else "left")
        if hi > lo:
            fR = -d * (fonh["cum"][hi] - fonh["cum"][lo]) * giris / risk
    return (ham / risk + fR, tur, k + 1, e, e + k, fR, son_min)
