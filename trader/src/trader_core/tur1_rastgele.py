"""Tur 1 olcum raporu icin rastgele-giris yapistirmasi (yalniz raporlama; canli/paper etkisi yok).

Rapor paketi pandas kullanmaz (statik kural); k2 simulasyonu (`stats.k2_simulasyon`) pandas ister, bu yuzden cerceve kurma ve
simulasyon cagrisi burada. Girdi sade sozluk/dizi: mum dizileri {'ms','open','high','low','close'} (numpy)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr as _atr
from .stats import k2_simulasyon as K2


def cerceve(mum: dict) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(np.asarray(mum["ms"], dtype="int64"), unit="ms", utc=True),
                         "open": mum["open"], "high": mum["high"], "low": mum["low"], "close": mum["close"]})


def atr_onceki(mum: dict, giris_ms: list[int], periyot: int = 14) -> list[float]:
    """Her giris mumu icin bir onceki mumun ATR'si (k2'nin stop_carpan paydasi); mum yoksa NaN."""
    a = _atr(cerceve(mum), periyot).to_numpy(float)
    ms = np.asarray(mum["ms"], dtype="int64")
    out = []
    for g in giris_ms:
        j = int(np.searchsorted(ms, g, "left"))
        out.append(float(a[j - 1]) if 1 <= j < len(ms) and ms[j] == g else float("nan"))
    return out


def k2_toplam(gruplar: dict, gercek: float, b: int, seed: int, alt_sinir_ms: int, maliyet_fn=None) -> dict:
    """gruplar: {(pair, tf, parca): (mum, [(giris_ms, yon, stop_carpan, tutma), ...])}. Mevcut `k2_testi` ile iki asamali test.
    maliyet_fn: pair -> K2.K2Maliyet (verilmezse k2 varsayilani). -> {'sim': dizi, 'p', 'asama'}."""
    son: dict = {}
    cf = {k: cerceve(v[0]) for k, v in gruplar.items()}

    def simule(n_sim: int, tohum: int):
        tot = np.zeros(n_sim)
        for k, (key, (_, sat)) in enumerate(sorted(gruplar.items(), key=lambda kv: kv[0])):
            tab = pd.DataFrame({"giris_zamani": [pd.Timestamp(g, unit="ms", tz="UTC") for g, *_ in sat],
                                "yon": [s[1] for s in sat], "stop_carpan": [s[2] for s in sat], "tutma": [s[3] for s in sat]})
            alt = pd.Timestamp(alt_sinir_ms, unit="ms", tz="UTC") if key[2] == "sonra" else None
            kw = {} if maliyet_fn is None else {"maliyet": maliyet_fn(key[0])}
            tot += K2.k2_simule(tab, cf[key], n_sim, tohum + 7919 * k, alt_sinir=alt, **kw)["toplam_r"]
        son["sim"] = tot
        return tot
    test = K2.k2_testi(gercek, simule, seed, b1=min(500, b), b2=b)
    return {"sim": np.asarray(son["sim"], float), "p": test["p"], "asama": test["asama"]}
