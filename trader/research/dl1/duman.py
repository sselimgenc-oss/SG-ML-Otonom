#!/usr/bin/env python3
"""DL1 duman betigi (YALNIZ Actions, torch gerekir): dort zaman dilimi icin sentetik veriyle kucuk egitim, numpy-PyTorch parite, paket kur/oku turu. Saniyeler (CPU).
Gercek egitimden ONCE calisir; basarisizsa egitim baslamaz."""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cekirdek as C  # noqa: E402
import egit as E  # noqa: E402
from trader_engine import dl1_cikarim as DL  # noqa: E402


FREQ = {"15m": "15min", "1h": "h", "4h": "4h", "1d": "D"}


def sentetik(n_cift=3, saat=24 * 60, tohum=1, tf="1h"):
    rg = np.random.default_rng(tohum)
    out, sn = {}, {}
    for k in range(n_cift):
        t = pd.date_range("2025-01-01", periods=saat, freq=FREQ[tf], tz="UTC").as_unit("ms")
        c = 100 * np.exp(np.cumsum(rg.normal(0, 0.004, saat)))
        o = np.r_[c[0], c[:-1]]
        h = np.maximum(o, c) * (1 + rg.uniform(0.0005, 0.003, saat))
        l = np.minimum(o, c) * (1 - rg.uniform(0.0005, 0.003, saat))
        out[f"P{k}/USDT"] = pd.DataFrame({"date": t, "open": o, "high": h, "low": l, "close": c, "volume": rg.uniform(10, 100, saat)})
        sn[f"P{k}/USDT"] = k % 3
    return out, sn


def tur(tf: str) -> None:
    seri, sn = sentetik(tf=tf)
    bar_ns = DL.BAR_NS[tf]
    v = C.veri_kur(seri, sn, bar_ns=bar_ns)
    rows = np.arange(len(v.g))
    ort, std = C.olcekleyici(v, rows)
    ag = E.torch_trainer(epoch=1, parti=256)(v, rows[:2000], ort, std, 7)
    pk = DL.agirlik_ac(DL.agirlik_paketle(ag))
    par = E.parite(v, pk, ort, std, n=300)
    assert par["max_fark_olasilik"] < C.PARITE_TOL, par
    esik = float(np.percentile(C.puanlar(v, rows[:2000], pk, ort, std).ravel(), 98))
    kapi = {"gecti": True, "toplam_ort_r": 0.1, "pozitif_oran": 1.0}
    paket = C.paket_kur(pk, ort, std, esik, v.siniflar, kapi, datetime.now(timezone.utc).replace(microsecond=0), {}, tf)
    with tempfile.TemporaryDirectory() as d:
        yol = Path(d) / f"DL1@{tf}.json"
        assert C.paket_yaz(paket, yol)
        p, neden = DL.paket_yukle(yol, datetime.now(timezone.utc), tf=tf)
        assert p is not None, neden
        # motor yolu (DL.puanla) ile egitim yolu (C.puanlar) ayni mi: bir ornek, ayni bardaki veriyle
        paket_obj = DL.paket_dogrula(paket, tf)
        r = int(np.flatnonzero(v.cift == 0)[len(v.cift[v.cift == 0]) // 2])
        df = seri["P0/USDT"]
        ts_ns = df["date"].dt.as_unit("ns").astype("int64").to_numpy()
        k = int(np.flatnonzero(ts_ns == v.ts[r] - bar_ns)[0])
        a = [df[c].to_numpy()[:k + 1] for c in ("open", "high", "low", "close", "volume")]
        motor = DL.puanla(paket_obj, "P0/USDT", ts_ns[:k + 1], *a)
        egitim = C.puanlar(v, np.array([r]), pk, ort, std)[0]
        assert motor is not None and abs(motor[0] - egitim[0]) < 1e-4 and abs(motor[1] - egitim[1]) < 1e-4, (motor, egitim)
        print(f"duman TAMAM {tf}; parite", par)


def main() -> int:
    for tf in DL.ZAMAN_DILIMLERI:
        tur(tf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
