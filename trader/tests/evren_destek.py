"""26.11 sahip karari testleri icin ortak sabitler: evren 14 cift, giris zaman dilimleri 1h/4h/1d, 16 kurulum kaldirildi.
Kaldirilan kurulumlar koddan da silindi (Paket 3: discover() 55 kurulum); sabit 'kayitta da yok' negatif testleri icindir."""
from __future__ import annotations

EVREN = tuple(f"{b}/USDT" for b in ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BTC", "ETH", "SOL", "XRP", "TRX", "XAU", "BZ"))
GIRIS_TFS = ("1h", "4h", "1d")
KALDIRILAN_KURULUM = frozenset({"S1-HACIM", "R1-ALT", "R1-ERKEN", "R1-HA", "TF1-FITIL", "TF1-HACIM", "H2-YARI", "B1-MUM", "F1-IKINCI",
                                "PA2-UCVURUS", "PA2-SEVIYE", "PA2-TUKENIS", "MF1-MARUBOZU", "MF1-TERSCEKIC", "MF1-UCASKER", "MF1-YILDIZ"})
KOL_SAYISI, KURULUM_SAYISI, GRUP_SAYISI = 162, 55, 18      # 18 grup: CANDLE_STAR3 ve EXHAUSTION uyesiz kaldi


def config_kollari(arm_ids):
    """Modullerden turetilen kol kimliklerinden config'te OLMASI gerekenler (15m giris kolu ve kaldirilan 16 kurulum zaten kayitta yok)."""
    return [a for a in arm_ids if a.partition("@")[2] != "15m" and a.partition("@")[0] not in KALDIRILAN_KURULUM]
