"""Veri: mumlar (dl1.veri.indir, Binance Vision) + fonlama (fetch_binance_vision ayni yardimcilar) + maliyet (dl1.cekirdek.maliyet_tablosu)."""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

KOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOK / "research" / "dl1"))
sys.path.insert(0, str(KOK / "src"))

import veri as DV  # noqa: E402  (research/dl1/veri.py)

HAM_DIR = KOK / "var" / "vision_raw"
UST = {"15m": ["1h", "4h"], "1h": ["4h"], "4h": ["1d"], "1d": []}
TF_NS = {"15m": 15 * 60 * 10**9, "1h": 3600 * 10**9, "4h": 4 * 3600 * 10**9, "1d": 86400 * 10**9}
BAS_AY = {"15m": "2023-01", "1h": "2021-01", "4h": "2021-01", "1d": "2021-01"}


def gerekli_tf(tfler: list[str]) -> list[str]:
    s = set(tfler)
    for t in tfler:
        s.update(UST[t])
    return [t for t in ["15m", "1h", "4h", "1d"] if t in s]


def maliyetler():
    import cekirdek as C
    return C.maliyet_tablosu()


def fonlama_indir(pairs: list[str], bas_ay: str, kesim: date, ham_dir: Path = HAM_DIR, log=print) -> dict[str, pd.DataFrame]:
    """pair -> DataFrame(date, funding_rate). Inmeyen/eksik cift atlanir (veto o cift icin kapali)."""
    F = DV.arac()
    son = kesim - timedelta(days=1)
    aylar = F.months(date(int(bas_ay[:4]), int(bas_ay[5:7]), 1), son)

    def is_(pair):
        sym = F.vision_symbol(pair)
        dosya = []
        for mo in aylar:
            url = f"{F.BASE_URL}/monthly/fundingRate/{sym}/{sym}-fundingRate-{mo}.zip"
            dest = Path(ham_dir) / "monthly" / "fundingRate" / f"{sym}-fundingRate-{mo}.zip"
            try:
                st = F.fetch_zip(url, dest, True)
            except Exception as e:  # noqa: BLE001  (ag/checksum: bu ay atlanir)
                log(f"UYARI fonlama {pair} {mo}: {e}")
                continue
            if st not in ("missing", "atlandi"):
                dosya.append(dest)
        return pair, dosya

    with ThreadPoolExecutor(8) as ex:
        sonuc = list(ex.map(is_, pairs))
    out = {}
    for pair, dosya in sonuc:
        if not dosya:
            log(f"UYARI: {pair}: fonlama yok; veto kapali")
            continue
        df = F.build(sorted(dosya), F.read_funding_zip)
        df = df[df["date"] < pd.Timestamp(kesim, tz="UTC")].sort_values("date").drop_duplicates("date").reset_index(drop=True)
        out[pair] = df
    return out


def yukle(pairs: list[str], tfler: list[str], kesim: date, bas_ay: str | None = None, log=print):
    """-> (mumlar {tf: {pair: df}}, fonlama {pair: df}). tfler yukari zaman dilimleriyle genisletilir."""
    mum = {}
    for tf in gerekli_tf(tfler):
        mum[tf] = DV.indir(pairs, bas_ay or BAS_AY[tf], kesim, HAM_DIR, tf=tf, log=log)
    fon = fonlama_indir(pairs, bas_ay or "2021-01", kesim, log=log)
    return mum, fon


def _ns(seri: pd.Series) -> np.ndarray:
    return seri.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy().astype("datetime64[ns]").astype("int64")


def dizilere(df: pd.DataFrame) -> dict:
    """df -> numpy dizileri (acilis zamani ns int64)."""
    d = df.sort_values("date").drop_duplicates("date")
    return {"t": _ns(d["date"]), "o": d["open"].to_numpy(float), "h": d["high"].to_numpy(float), "l": d["low"].to_numpy(float),
            "c": d["close"].to_numpy(float), "v": d["volume"].to_numpy(float)}


def fonlama_dizi(df: pd.DataFrame | None):
    if df is None or len(df) == 0:
        return None
    return {"t": _ns(df["date"]), "r": df["funding_rate"].to_numpy(float)}
