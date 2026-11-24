"""Islem simulasyonu: giris t+1 acilisi (kayma dahil); stop/hedef intrabar (ayni mumda ikisi: STOP); bosluk dolumu; zaman stopu = son mumun kapanisi;
masraf (ucret + kayma) ve fonlama R'ye islenir. R = (cikis - giris) / (giris - stop) (net).
Tur 2: fonlama cikis mumunun kapanisina kadar sayilir; giris acilisindaki risk < min_risk ise islem yok; tutma penceresinde mum
boslugu ya da (stop/hedef yokken) veri bitmeden zaman stopuna ulasilamamasi -> islem yok (None)."""
from __future__ import annotations

import numpy as np

TUR = {0: "stop", 1: "hedef", 2: "zaman"}


def fonlama_hazirla(fon):
    if fon is None:
        return None
    return {"t": fon["t"], "cum": np.r_[0.0, np.cumsum(fon["r"])]}


def simule(S: dict, t: int, yon: int, stop: float, hedef: float, maxmum: int, mal: tuple, step_ns: int, fonh=None, min_risk: float = 0.0):
    """S: gercek fiyat dizileri; stop/hedef GERCEK fiyat. Gecersiz kurulumda None.
    Donus: (netR, tur_kodu, tutma_mum, giris_idx, cikis_idx, fonlama_R)."""
    n = len(S["t"])
    e = t + 1
    if e >= n or S["t"][e] - S["t"][t] != step_ns:
        return None
    taker, k_g, k_c, k_s = mal
    o, h, l = S["o"], S["h"], S["l"]
    if yon * (o[e] - stop) <= 0 or yon * (hedef - o[e]) <= 0:
        return None                               # acilis stopun ustten/ yanlis yanda
    giris = o[e] * (1 + yon * k_g)
    bit = min(n, e + maxmum)
    if yon == 1:
        sh, th = l[e:bit] <= stop, h[e:bit] >= hedef
    else:
        sh, th = h[e:bit] >= stop, l[e:bit] <= hedef
    ks = int(np.argmax(sh)) if sh.any() else -1
    kh = int(np.argmax(th)) if th.any() else -1
    if ks >= 0 and (kh < 0 or ks <= kh):          # ayni mumda ikisi de: stop
        k = ks
        fill = stop
        if k > 0 and yon * (o[e + k] - stop) < 0:  # bosluk: acilistan dolum
            fill = o[e + k]
        tur, kay = 0, k_s
    elif kh >= 0:
        k = kh
        fill = hedef
        if k > 0 and yon * (o[e + k] - hedef) > 0:
            fill = o[e + k]
        tur, kay = 1, k_c
    else:
        if bit - e < maxmum:
            return None                               # veri bitti, zaman stopuna ulasilamadi
        k = bit - e - 1
        fill = S["c"][bit - 1]
        tur, kay = 2, k_c
    cik = fill * (1 - yon * kay)
    risk = yon * (giris - stop)
    if risk <= 0 or risk / giris < min_risk:
        return None
    if k > 0 and (np.diff(S["t"][e:e + k + 1]) != step_ns).any():
        return None                                   # tutma penceresinde mum boslugu
    ham = yon * (cik - giris) - taker * (giris + cik)
    fR = 0.0
    if fonh is not None:
        ft = fonh["t"]
        lo = np.searchsorted(ft, S["t"][e], side="right")
        hi = np.searchsorted(ft, S["t"][e + k] + step_ns, side="right")     # cikis mumunun kapanisina kadar
        if hi > lo:
            fR = -yon * (fonh["cum"][hi] - fonh["cum"][lo]) * giris / risk
    return (ham / risk + fR, tur, k + 1, e, e + k, fR)
