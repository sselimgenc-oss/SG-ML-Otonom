"""Tur 1 olcum raporundan gunluk TEK SATIR karar ("canliya hazir mi?") ve degisim tespiti. Saf mantik: dosya/ag acmaz.

Kaynak: rapor JSON'unun `canli_sartlari.maddeler` bolumu (BILGI maddeleri sayilmaz). Telegram yalniz HAZIR/HAYIR durumu ya da
eksik sartlar KUMESI degisince gider; yalniz sayi degisimi mesaj uretmez. Karar yetkisi yoktur: yalniz bilgi mesaji.
"""
from __future__ import annotations

import re

# (onek, kimlik, kisa ad) : maddenin `ad` alani bu onekle baslar. Siralama sabit; bilinmeyen madde kendi adiyla kimliklenir.
_BILINEN = (
    ("En az", "islem"), ("Masraf sonrası net >", "net"), ("En az 2 rejimde", "rejim"), ("Rastgele giriş", "rastgele"),
    ("Masraf x", "masraf"), ("Monte Carlo", "dusus"),
)


def _kimlik(ad: str) -> str:
    if ad.startswith("En az") and "rejimde" in ad:
        return "rejim"
    for onek, k in _BILINEN:
        if ad.startswith(onek):
            return k
    return ad[:60]


def _say(deger: str, desen: str) -> str | None:
    m = re.search(desen, deger or "")
    return m.group(1).replace(".", ",") if m else None


def _etiket(kimlik: str, ad: str, deger: str, gecti: bool) -> str:
    """Kisa, sade Turkce ad + anahtar sayi (sayi yalniz bilgi; degisim tespitine girmez)."""
    if kimlik == "islem":
        n = _say(deger, r"n = (\d+)")
        hedef = _say(ad, r"En az (\d+)")
        return f"işlem {n}/{hedef}" if n and hedef else "işlem sayısı"
    if kimlik == "net":
        net = _say(deger, r"net = ([+-]?[\d.]+) R")
        return ("masraf sonrası net kâr pozitif" if gecti else "masraf sonrası net kâr yok") + (f" ({net} R)" if net else "")
    if kimlik == "rejim":
        k = _say(deger, r"^(\d+) rejim pozitif")
        return ("yeterli rejimde pozitif" if gecti else "yeterli rejimde pozitif değil") + (f" ({k} rejim)" if k else "")
    if kimlik == "rastgele":
        y = _say(deger, r"yüzdelik = ([\d.]+)")
        return ("rastgele girişten iyi" if gecti else "rastgele girişten iyi değil") + (f" (yüzdelik {y})" if y else "")
    if kimlik == "masraf":
        c = _say(ad, r"Masraf x([\d.]+)")
        return f"masraf x{c} altında " + ("kâr sürüyor" if gecti else "kâr yok")
    if kimlik == "dusus":
        p = _say(deger, r"p95 = %([\d.]+)")
        return ("en kötü düşüş sınır içinde" if gecti else "en kötü düşüş sınırı aşıldı") + (f" (%{p})" if p else "")
    return ad[:60]


def karar(d: dict) -> dict | None:
    """{'hazir': bool, 'eksik': [kimlik...] (sirali), 'satir': str}; rapor canli_sartlari icermiyorsa None."""
    maddeler = ((d or {}).get("canli_sartlari") or {}).get("maddeler")
    if not isinstance(maddeler, list):
        return None
    eksik, tamam, eks_k = [], [], []
    for m in maddeler:
        if not isinstance(m, dict) or m.get("bilgi"):
            continue
        ad, deger, gecti = str(m.get("ad", "")), str(m.get("deger", "")), bool(m.get("gecti"))
        k = _kimlik(ad)
        e = _etiket(k, ad, deger, gecti)
        if gecti:
            tamam.append(e)
        else:
            eksik.append(e)
            eks_k.append(k)
    hazir = not eksik and bool(tamam)
    if hazir:
        satir = "Canlıya hazır: EVET — tüm şartlar geçti: " + ", ".join(tamam)
    else:
        satir = "Canlıya hazır: HAYIR — eksik: " + (", ".join(eksik) or "veri yok")
        if tamam:
            satir += "; tamam: " + ", ".join(tamam)
    return {"hazir": hazir, "eksik": sorted(eks_k), "satir": satir}


def degisti(onceki: dict | None, k: dict) -> bool:
    """Ilk calisma (onceki yok) ya da HAZIR durumu / eksik sart kumesi degistiyse True. Yalniz sayi farki False."""
    if not isinstance(onceki, dict) or "hazir" not in onceki or "eksik" not in onceki:
        return True
    return bool(onceki["hazir"]) != k["hazir"] or sorted(onceki["eksik"]) != sorted(k["eksik"])
