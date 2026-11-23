"""Oynaklik tahmini ozellikleri (fikir 10; 23.11 kullanici karari): gece suzgecine EK girdi ozelligi. Stop, boyut ya da baska
HICBIR seyi degistirmez; kagit ve canli ayni kodu calistirir.

Girdi: karar zaman diliminin KAPANMIS mumlarinin kapanislari (yalniz karar aninda bilinen veri) + o mumun ATR'si.
Model: sabit parametreli GJR-GARCH(1,1) (log getiri, optimizer YOK, mum basina oturtma YOK):
    s2[t+1] = w + (a + g*1[r_t<0]) * r_t^2 + b * s2[t],   w = (1 - p) * L,   p = a + b + g/2
    L = penceredeki ornek varyans (yalniz GECMIS; varyans hedefleme). a=0.05, g=0.06, b=0.88 (p=0.96, saatlik kripto icin tipik).
Ileri N mum: E[s2[t+h]] = L + p^(h-1) * (s2[t+1] - L); N = ufuk(4 saat) / mum suresi (en az 1).
Ozellikler (oran, olcekten bagimsiz):
    vol_tahmin = sqrt(ortalama_h E[s2[t+h]]) / (ATR / kapanis)      -> ileri N mum oynakligi / mevcut ATR tabanli oynaklik
    vol_asim   = (Sd - Su) / (Sd + Su), Sd/Su = lambda=0.94 EWMA( r^2 * 1[r<0] ) / ( r^2 * 1[r>0] )   -> [-1, 1]; kaldirac (asimetri) bileseni
Eksik/kisa/gecersiz veri => bos sozluk (ozellik yazilmaz; suzgec eksik ozelligi `fill` ile doldurur). Duvar saati ve rastgelelik YOK.
"""
from __future__ import annotations

import math

import numpy as np

A, G, B = 0.05, 0.06, 0.88
LAM = 0.94
UFUK_DK = 240                 # "onumuzdeki saatler": 4 saat
PENCERE = 200                 # en fazla bu kadar kapanis (maliyet siniri; ~200 basit dongu adimi)
MIN_GETIRI = 30
_TF_DK = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def ufuk_mum(tf: str | None) -> int:
    dk = _TF_DK.get(str(tf), 60)
    return max(1, UFUK_DK // dk)


def vol_ozellikleri(kapanis, atr, tf: str | None = None) -> dict[str, float]:
    """`kapanis`: kapanmis mumlarin kapanislari (eskiden yeniye, son = karar mumu); `atr`: karar mumunun ATR'si (fiyat birimi)."""
    try:
        c = np.asarray(kapanis, dtype=np.float64)
        a = float(atr)
    except (TypeError, ValueError):
        return {}
    if c.ndim != 1:
        return {}
    c = c[-(PENCERE + 1):]
    if c.size < MIN_GETIRI + 1 or not math.isfinite(a) or a <= 0.0 or not np.all(np.isfinite(c)) or np.any(c <= 0.0):
        return {}
    r = np.diff(np.log(c))
    L = float(np.mean(r * r))
    if not L > 0.0:
        return {}
    p = A + B + G / 2.0
    w = (1.0 - p) * L
    s2, sd, su = L, 0.0, 0.0
    for x in r.tolist():
        x2 = x * x
        s2 = w + (A + (G if x < 0.0 else 0.0)) * x2 + B * s2
        sd = LAM * sd + (1.0 - LAM) * (x2 if x < 0.0 else 0.0)
        su = LAM * su + (1.0 - LAM) * (x2 if x > 0.0 else 0.0)
    n = ufuk_mum(tf)
    pk = p ** np.arange(n)
    ort = L + float(np.mean(pk)) * (s2 - L)
    atr_vol = a / float(c[-1])
    out: dict[str, float] = {}
    if ort > 0.0 and atr_vol > 0.0:
        v = math.sqrt(ort) / atr_vol
        if math.isfinite(v):
            out["vol_tahmin"] = float(v)
    if sd + su > 0.0:
        out["vol_asim"] = float((sd - su) / (sd + su))
    return out
