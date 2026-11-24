"""Veri toplama (YALNIZ KAYIT): ham haber ogeleri + Fear & Greed gecmisi -> `var/veri/haber/`. Belirtim: docs/veri-toplama-spec.md.

Bu veri HICBIR karar girdisi DEGILDIR (kapi, kural, ML ozelligi, not): golge/ust lig hatti icin biriktirilir. trader_engine bu modulu
iceri almaz (tests/test_veri_toplama.py bunu zorlar). Etiket/ton/kural YOKTUR; ham baslik, baglanti, ozet saklanir.
Cozuculer CT projesinin `haber.py` sozlesmesinden uyarlandi (THIRD_PARTY_NOTICES.md); ag stdlib `urllib`, yeni bagimlilik yok.

Depo (yalniz-ekleme JSONL; var/veri/haber/):
  haber.jsonl : {"ts": yayin ms (yoksa alim ms), "alim": alim ms, "kaynak": ad, "kategori": kripto|hisse|emtia, "baslik": ..., "baglanti": ..., "ozet": ...}
  fng.jsonl   : {"ts": endeksin kendi zaman damgasi (ms), "alim": alim ms, "deger": 0-100, "sinif": ...}
Tekillestirme: haber -> sha1(kaynak|baglanti veya baslik); fng -> ts. Var olan satir ASLA degistirilmez/silinmez.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

DUYGU_URL = "https://api.alternative.me/fng/?limit=10"
# TEK LISTE: (ad, url, kategori). Kategori: kripto / hisse / emtia (KARAR-2). Yeni kaynak = bu listeye bir satir.
# Hepsi anahtarsiz, https GET. Hisse/emtia kaynaklari genel piyasa/is bolumu beslemeleridir (21 hisse + 4 emtia icin tek tek beslemeye
# gerek yok; hangi enstrumani ilgilendirdigine `haber_sinyal` modeli karar verir). Sartlar THIRD_PARTY_NOTICES.md'de.
KAYNAK_LISTESI: tuple[tuple[str, str, str], ...] = (
    ("coindesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "kripto"),
    ("cointelegraph", "https://cointelegraph.com/rss", "kripto"),
    ("decrypt", "https://decrypt.co/feed", "kripto"),
    ("bitcoinmagazine", "https://bitcoinmagazine.com/.rss/full/", "kripto"),
    ("cnbc_earnings", "https://www.cnbc.com/id/15839135/device/rss/rss.html", "hisse"),
    ("cnbc_technology", "https://www.cnbc.com/id/19854910/device/rss/rss.html", "hisse"),
    ("cnbc_finance", "https://www.cnbc.com/id/10000664/device/rss/rss.html", "hisse"),
    ("marketwatch_top", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "hisse"),
    ("marketwatch_pulse", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse", "hisse"),
    ("nasdaq_markets", "https://www.nasdaq.com/feed/rssoutbound?category=Markets", "hisse"),
    ("yahoo_finance", "https://finance.yahoo.com/news/rssindex", "hisse"),
    ("oilprice", "https://oilprice.com/rss/main", "emtia"),
    ("mining_com", "https://www.mining.com/feed/", "emtia"),
    ("cnbc_energy", "https://www.cnbc.com/id/19836768/device/rss/rss.html", "emtia"),
)
# Yayinci = besleme adinin ilk parcasi (cnbc_*, marketwatch_* ayni yayinci); HB1 teyidinde (haber_sinyal.yayinci) tek kaynak sayilir.
KAYNAKLAR: dict[str, str] = {ad: url for ad, url, _ in KAYNAK_LISTESI}
KATEGORI: dict[str, str] = {ad: kat for ad, _, kat in KAYNAK_LISTESI}
KATEGORILER = ("kripto", "hisse", "emtia")
ZAMAN_ASIMI_SN = 8
TOPLAM_BUTCE_SN = 100
MAX_BAYT = 2_000_000
OZET_MAX = 500
BASLIK_MAX = 300
GELECEK_TOLERANS_MS = 3600_000

Getir = Callable[[str], Any]


def _indir(url: str, kabul: str) -> bytes:
    import urllib.request

    if not url.startswith("https://"):
        raise ValueError("adres https degil")
    req = urllib.request.Request(url, headers={"User-Agent": "trader-veri-haber/1", "Accept": kabul})
    with urllib.request.urlopen(req, timeout=ZAMAN_ASIMI_SN) as r:    # noqa: S310 (https denetlendi)
        if r.status != 200:
            raise ValueError(f"http {r.status}")
        veri = r.read(MAX_BAYT + 1)
    if len(veri) > MAX_BAYT:
        raise ValueError("yanit siniri asti")
    return veri


def getir_json(url: str) -> Any:
    return json.loads(_indir(url, "application/json").decode("utf-8"))


def getir_metin(url: str) -> bytes:
    return _indir(url, "application/rss+xml, application/xml, text/xml")


# ------------------------------------------------------------------ saf cozuculer
def duygu_coz(veri: Any, alim_ms: int) -> list[dict]:
    """alternative.me yaniti -> [{"ts","alim","deger","sinif"}]; bozuk satirlar atlanir. Istisna firlatmaz."""
    out: list[dict] = []
    try:
        for k in veri["data"]:
            try:
                d = int(float(k["value"]))
                s = str(k["value_classification"]).strip()
                ts = int(k["timestamp"]) * 1000
            except Exception:  # noqa: BLE001
                continue
            if 0 <= d <= 100 and s and ts > 0:
                out.append({"ts": ts, "alim": alim_ms, "deger": d, "sinif": s})
    except Exception:  # noqa: BLE001
        return []
    return sorted(out, key=lambda r: r["ts"])


_ETIKET = re.compile(r"<[^>]+>")


def _temiz(s: str | None, n: int) -> str:
    return re.sub(r"\s+", " ", html.unescape(_ETIKET.sub(" ", s or ""))).strip()[:n]


def _yerel(etiket: Any) -> str:
    return etiket.rsplit("}", 1)[-1] if isinstance(etiket, str) else ""


def _cocuk(oge: ET.Element, *adlar: str) -> ET.Element | None:
    for c in oge:
        if _yerel(c.tag) in adlar:
            return c
    return None


def _baglanti(oge: ET.Element) -> str:
    for c in oge:                                          # Atom: <link href=".." rel="alternate"/>; RSS: <link>metin</link>
        if _yerel(c.tag) == "link":
            h = (c.get("href") or "").strip()
            if h and c.get("rel", "alternate") == "alternate":
                return h[:500]
            if (c.text or "").strip():
                return c.text.strip()[:500]
    return ""


def _zaman_ms(oge: ET.Element, alim_ms: int) -> int:
    for ad in ("pubDate", "published", "updated", "date"):
        c = _cocuk(oge, ad)
        v = ((c.text if c is not None else "") or "").strip()
        if not v:
            continue
        try:
            if ad in ("pubDate", "date") and not v[:4].isdigit():
                t = parsedate_to_datetime(v)
            else:
                t = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            ms = int(t.timestamp() * 1000)
            return ms if ms <= alim_ms + GELECEK_TOLERANS_MS else alim_ms
        except (TypeError, ValueError):
            continue
    return alim_ms


def rss_coz(icerik: Any, kaynak: str, alim_ms: int, kategori: str | None = None) -> list[dict]:
    """RSS 2.0 ve Atom -> ham ogeler (+ `kategori`: kripto/hisse/emtia; verilmezse KATEGORI[kaynak], yoksa kripto).
    Tarih yoksa/bozuksa alim zamani; baslik bos oge atilir. DTD/ENTITY reddedilir; bozuk XML -> []."""
    try:
        ham = icerik if isinstance(icerik, (bytes, bytearray)) else str(icerik).encode("utf-8")
        if b"<!DOCTYPE" in ham.upper() or b"<!ENTITY" in ham.upper():
            return []
        kat = kategori or KATEGORI.get(kaynak, "kripto")
        out = []
        for oge in ET.fromstring(ham).iter():
            if _yerel(oge.tag) not in ("item", "entry"):
                continue
            t = _cocuk(oge, "title")
            baslik = _temiz("".join(t.itertext()) if t is not None else "", BASLIK_MAX)
            if not baslik:
                continue
            r = {"ts": _zaman_ms(oge, alim_ms), "alim": alim_ms, "kaynak": kaynak, "kategori": kat, "baslik": baslik,
                 "baglanti": _baglanti(oge)}
            d = _cocuk(oge, "description", "summary", "content")
            ozet = _temiz("".join(d.itertext()) if d is not None else "", OZET_MAX)
            if ozet:
                r["ozet"] = ozet
            out.append(r)
        return out
    except Exception:  # noqa: BLE001
        return []


def haber_anahtar(r: dict) -> str:
    return hashlib.sha1(f"{r['kaynak']}|{r.get('baglanti') or r['baslik']}".encode()).hexdigest()


# ------------------------------------------------------------------ yalniz-ekleme depo
def _satirlar(yol: Path) -> list[dict]:
    out = []
    try:
        with open(yol, encoding="utf-8") as f:
            for s in f:
                try:
                    out.append(json.loads(s))
                except ValueError:
                    continue            # yarim/bozuk satir: atla (dosyaya dokunulmaz)
    except FileNotFoundError:
        pass
    return out


def ekle(yol: Path, satirlar: list[dict]) -> int:
    """Satirlari dosya SONUNA ekler (tek yazim + fsync). Mevcut icerik yeniden yazilmaz. Onceki yazim yarim kaldiysa satir basi eklenir."""
    if not satirlar:
        return 0
    yol.parent.mkdir(parents=True, exist_ok=True)
    veri = "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n" for r in satirlar)
    with open(yol, "ab+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                f.write(b"\n")
        f.write(veri.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    return len(satirlar)


def haber_ekle(dizin: Path, ogeler: list[dict]) -> int:
    yol = dizin / "haber.jsonl"
    var = {haber_anahtar(r) for r in _satirlar(yol) if "kaynak" in r and "baslik" in r}
    yeni = []
    for r in ogeler:
        k = haber_anahtar(r)
        if k not in var:
            var.add(k)
            yeni.append(r)
    return ekle(yol, yeni)


def fng_ekle(dizin: Path, satirlar: list[dict]) -> int:
    yol = dizin / "fng.jsonl"
    var = {r.get("ts") for r in _satirlar(yol)}
    yeni = []
    for r in satirlar:
        if r["ts"] not in var:
            var.add(r["ts"])
            yeni.append(r)
    return ekle(yol, yeni)


# ------------------------------------------------------------------ toplayici
def topla(dizin: Path, alim_ms: int, gj: Getir | None = None, gm: Getir | None = None,
          kaynaklar: dict[str, str] | None = None, duygu_url: str = DUYGU_URL) -> dict:
    """Tum kaynaklari okur, yeni olanlari ekler. Kaynak hatasi yutulur (digerleri surer). Donus: {"haber","fng","hata"}."""
    gj, gm = gj or getir_json, gm or getir_metin
    kaynaklar = KAYNAKLAR if kaynaklar is None else kaynaklar        # KATEGORI.get(ad) yoksa rss_coz kripto varsayar
    bas = time.monotonic()
    ozet = {"haber": 0, "fng": 0, "hata": 0}
    if duygu_url:
        try:
            ozet["fng"] = fng_ekle(dizin, duygu_coz(gj(duygu_url), alim_ms))
        except Exception:  # noqa: BLE001
            ozet["hata"] += 1
    for ad, url in kaynaklar.items():
        if time.monotonic() - bas > TOPLAM_BUTCE_SN:
            ozet["hata"] += 1
            continue
        try:
            ozet["haber"] += haber_ekle(dizin, rss_coz(gm(url), ad, alim_ms, KATEGORI.get(ad)))
        except Exception:  # noqa: BLE001
            ozet["hata"] += 1
    return ozet
