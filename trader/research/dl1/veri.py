"""DL1 egitim verisi: Binance Vision acik arsivi, 1h USDT-M vadeli klines (mevcut `scripts/fetch_binance_vision.py` yardimcilari yeniden kullanilir:
fetch_zip (sha256 .CHECKSUM dogrulamali, onbellekli), read_kline_zip, build). Sembol: BTC/USDT -> BTCUSDT; hisse/emtia da ayni adlandirma
(NVDAUSDT, XAUUSDT, BZUSDT, COPPERUSDT ... arsivde listelendikleri aydan itibaren; once yoksa o enstrumanin gecmisi kisadir).

Kilit acik (trader_ml.config.KILIT_ACIK, 23.11 kullanici karari): indirici aracin 2026-05 sinirini bu surecte kaldirir (modul global'i; arac dosyasina
dokunulmaz). Kilit kapaliysa HIC veri indirilmez (hata). Kesim: `kesim` gununden (dislayici, UTC 00:00) onceki veri; deterministik.
Gecen aylar aylik zip; kesimin ayi ve (aylik dosya henuz yayinlanmamissa) bir onceki ay gunluk zip."""
from __future__ import annotations

import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
_F = None


def arac():
    global _F
    if _F is None:
        spec = importlib.util.spec_from_file_location("fetch_binance_vision", ROOT / "scripts" / "fetch_binance_vision.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        _F = m
    return _F


def indir(pairs: list[str], bas_ay: str, kesim: date, ham_dir: Path, isci: int = 8, log=print) -> dict[str, pd.DataFrame]:
    """pairs ("BTC/USDT") -> {pair: DataFrame(date, open, high, low, close, volume)} (date < kesim). Arsivde olmayan cift atlanir (raporlanir)."""
    from trader_ml.config import KILIT_ACIK
    if not KILIT_ACIK:
        raise RuntimeError("kilit kapali: DL1 egitim verisi indirilmez")
    F = arac()
    F.HOLDOUT_START = datetime(2100, 1, 1, tzinfo=timezone.utc)      # arac korumasi: yalniz kilit acikken (yukarida denetlendi)
    son = kesim - timedelta(days=1)
    bas = date(int(bas_ay[:4]), int(bas_ay[5:7]), 1)
    aylar = F.months(bas, son)
    gunluk_ay = set(aylar[-2:])

    def al(url, dest):
        """fetch_zip (sha256 dogrulamali). .CHECKSUM YOKSA dosya atlanir (uyari; kayit yok); checksum UYUSMAZLIGI hata (egitim durur)."""
        try:
            return F.fetch_zip(url, dest, True)
        except F.ChecksumError as e:
            if ".CHECKSUM yok" not in str(e):
                raise
            log(f"UYARI: {url}: .CHECKSUM yok; dosya atlandi")
            return "atlandi"

    def is_(pair, mo):
        sym = F.vision_symbol(pair)
        base = f"{F.BASE_URL}/monthly/klines/{sym}/1h/{sym}-1h-{mo}.zip"
        dest = Path(ham_dir) / "monthly" / f"{sym}-1h-{mo}.zip"
        dosyalar = []
        if mo != aylar[-1]:
            st = al(base, dest)
            if st not in ("missing", "atlandi"):
                return [dest]
        if mo in gunluk_ay:
            for gun in F.days_of(mo, son):
                u = f"{F.BASE_URL}/daily/klines/{sym}/1h/{sym}-1h-{gun}.zip"
                d = Path(ham_dir) / "daily" / f"{sym}-1h-{gun}.zip"
                if al(u, d) not in ("missing", "atlandi"):
                    dosyalar.append(d)
        return dosyalar

    gorev = [(p, mo) for p in pairs for mo in aylar]
    with ThreadPoolExecutor(isci) as ex:
        sonuc = list(ex.map(lambda t: (t[0], is_(*t)), gorev))
    dosya: dict[str, list[Path]] = {p: [] for p in pairs}
    for p, fl in sonuc:
        dosya[p] += fl
    out = {}
    for p in pairs:
        if not dosya[p]:
            log(f"UYARI: {p}: arsivde dosya yok; atlandi")
            continue
        df = F.build(sorted(dosya[p]), F.read_kline_zip)
        df = df[df["date"] < pd.Timestamp(kesim, tz="UTC")].reset_index(drop=True)
        out[p] = df
        log(f"{p}: {len(df)} mum ({df['date'].iloc[0]:%Y-%m-%d} -> {df['date'].iloc[-1]:%Y-%m-%d})")
    return out
