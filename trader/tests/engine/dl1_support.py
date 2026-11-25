"""DL1 testleri icin ortak yardimcilar (test dosyasi degil): sentetik paket, sentetik mum serisi."""
from __future__ import annotations

import json
from datetime import timedelta

import numpy as np
import pandas as pd

from trader_engine import dl1_cikarim as DL

CIFTLER = {"BTC/USDT": 0, "NVDA/USDT": 1, "XAU/USDT": 2}


def sifir_agirlik(bias_long=0.0, bias_short=0.0):
    ag = {ad: np.zeros(sek) for ad, sek in DL.agirlik_sekilleri().items()}
    ag["head.b"] = np.array([bias_long, bias_short, 0.0])
    return ag


def paket_sozlugu(olusturma, *, esik=0.5, agirlik=None, son=None, kapi=True, siniflar=None, tf="1h", **ek):
    p = {"schema": DL.SEMA, "arm_id": DL.arm_id(tf), "pencere": DL.PENCERE, "kanallar": list(DL.KANALLAR), "ufuk": DL.UFUK, "tf": tf, "etiket": {"stop_atr": DL.STOP_ATR, "hedef_atr": DL.HEDEF_ATR},
         "olusturma": olusturma.isoformat(), "son_kullanma": (son or olusturma + timedelta(days=DL.SON_KULLANMA_GUN)).isoformat(),
         "esik": esik, "olcekleyici": {"ort": [0.0] * DL.N_KANAL, "std": [1.0] * DL.N_KANAL},
         "kapsam": {"siniflar": dict(siniflar or CIFTLER)}, "kapi": {"gecti": kapi},
         "agirliklar": DL.agirlik_paketle(agirlik if agirlik is not None else sifir_agirlik()), "metrikler": {}}
    p.update(ek)
    p["sha256"] = DL.paket_ozeti(p)
    return p


def yaz(yol, paket):
    yol.write_text(paket if isinstance(paket, str) else json.dumps(paket), encoding="utf-8")
    return yol


def seri(son_ts, n=300, tohum=3, yukari=True, tf="1h"):
    """n adet tf mumu, dolu (son mumun KAPANIS zamani = son_ts; indeks = acilis). DataFrame + ns zaman damgasi."""
    son_ts = son_ts.replace(tzinfo=None)
    adim = timedelta(seconds=DL.BAR_NS[tf] // 1_000_000_000)
    idx = pd.DatetimeIndex([son_ts - adim * (n - k) for k in range(n)])
    rg = np.random.default_rng(tohum)
    c = 100 + np.cumsum(rg.normal(0, 0.5, n))
    o = np.r_[c[0], c[:-1]]
    c[-1] = o[-1] + (0.8 if yukari else -0.8)
    h = np.maximum(o, c) + 0.4
    lo = np.minimum(o, c) - 0.4
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": rg.uniform(10, 100, n)}, index=idx)
