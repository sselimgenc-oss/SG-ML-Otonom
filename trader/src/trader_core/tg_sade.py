"""Telegram mesajlarini seyrek ve sade tutan katman (kullanici: teknik olmayan, Turkce).

Saf bicimleyiciler + kucuk bir durum defteri. Kurallar:
  * her mesaj "[ML] " ile baslar; en cok 6 satir (gunluk/haftalik ozet 10); mesaj basina en cok bir emoji (yalniz ilk satirda, izinli kume);
    dosya/servis/modul/kod adi, alt cizgi, journalctl/sunucu yok;
  * uyari sirasi: ne oldu -> ne yapiliyor -> "Senden: ..." (yalniz teknik olmayan biri bir sey yapabiliyorsa);
  * ayni uyari 6 saatte bir (EK_HATIRLATMA_SAAT); duzelince tek "Duzeldi"; "Bot durdu" bu kuraldan muaf;
  * gunluk zarar uyarisi sinirin %80'inde gunde bir kez.
Motor bu modulu ice aktarmaz; yalniz stdlib.
"""
from __future__ import annotations

import json
import os
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

ETIKET = "[ML] "
EK_HATIRLATMA_SAAT = 6
MAX_SATIR = 6
MAX_SATIR_OZET = 10
UYARI_ORANI = 0.80          # limitin %80'i
BOT_AD = {"learner": "öğrenen"}     # panelde gorunen ad (panel.js BOT_AD)
TR = timezone(timedelta(hours=3))

_YASAK = re.compile(r"journalctl|systemctl|sunucu|\.py\b|\.service\b|\.timer\b|\.json\b|\.sqlite\b|_", re.I)
# izinli emoji kumesi: acilis yonu, kapanis sonucu, dikkat, acil, duzeldi, gunluk, haftalik
EMOJI_IZINLI = ("🟩", "🟥", "🟢", "🔻", "⚪", "⚠", "🔴", "✅", "🌙", "🗓")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2139\u2934\u2935\u3030\u303D]")


# ----------------------------------------------------------------------------- bicim
def sayi(x: float, nd: int = 2) -> str:
    """1234.5 -> '1.234,50' (Turkce)."""
    s = f"{abs(float(x)):,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def isaretli(x: float, nd: int = 2) -> str:
    return ("+" if float(x) >= 0 else "−") + sayi(x, nd)


def coin(pair: Any) -> str:
    """'SOL/USDT' -> 'SOL'."""
    s = str(pair or "?").upper().split(":")[0]
    for suf in ("/USDT", "/USDC", "/BUSD", "USDT"):
        if s.endswith(suf) and len(s) > len(suf):
            return s[: -len(suf)]
    return s.split("/")[0]


def yon(side: Any) -> str:
    return "long" if str(side).lower() in ("long", "buy", "b", "uzun") else "short"


def fiyat(x: Any) -> str:
    """TEK Telegram fiyat bicimi (tum islem mesajlari): 1 $ ustu 2 ondalik, 1 $ alti en fazla 4 ondalik; Turkce ayraclar."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "?"
    if not math.isfinite(v):
        return "?"
    a = abs(v)
    if a >= 1 or a == 0:
        t = sayi(v, 2)                       # 1 $ ustu: 2 ondalik (8,87; 2.001,00)
    else:
        t = sayi(v, 4 if a >= 0.0001 else 6)  # 1 $ alti: en fazla 4 ondalik (0,1234); cok kucukte anlamli hane kalsin
        if "," in t:
            ip, ond = t.split(",")
            t = ip + "," + (ond.rstrip("0").ljust(2, "0"))   # 0,5000 -> 0,50
    return ("-" if v < 0 and any(c in "123456789" for c in t) else "") + t


def temizle(text: str) -> str:
    """Kullaniciya gitmemesi gereken izleri atar: alt cizgi, dosya/servis adi, sunucu/journalctl."""
    t = re.sub(r"\b[\w-]+\.(py|service|timer|json|sqlite|sh|md)\b", "", str(text))
    t = re.sub(r"journalctl\S*|systemctl\S*", "", t, flags=re.I)
    t = re.sub(r"\bsunucu(da|dan|nun|ya|yu)?\b", "bilgisayar", t, flags=re.I)
    t = t.replace("_", " ")
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def etiketle(text: str) -> str:
    return text if text.startswith(ETIKET) else ETIKET + text


def kontrol(text: str, max_satir: int = MAX_SATIR) -> list[str]:
    """Bicim ihlalleri (bos liste = uygun). Testler ve savunma amacli."""
    out = []
    if not text.startswith(ETIKET):
        out.append("onek")
    if len(text.splitlines()) > max_satir:
        out.append("satir")
    if _YASAK.search(re.sub(r"(?<![\w.])/[a-z0-9_]+", "", text)):          # komut adlari (/hepsini_kapat) alt cizgi sayilmaz
        out.append("yasak")
    emojiler = _EMOJI_RE.findall(text)
    if len(emojiler) > 1 or any(e not in EMOJI_IZINLI for e in emojiler) or _EMOJI_RE.search("\n".join(text.splitlines()[1:])):
        out.append("emoji")
    return out


def _bagla(satirlar: list[str], max_satir: int = MAX_SATIR) -> str:
    satirlar = [s for s in satirlar if s]
    return etiketle("\n".join(satirlar[:max_satir]))


# ----------------------------------------------------------------------------- kol adi
_TF_TR = {"15m": "15 dakika", "1h": "1 saat", "4h": "4 saat", "1d": "1 gün", "5m": "5 dakika", "1m": "1 dakika",
          "30m": "30 dakika", "1w": "1 hafta"}
# kurulum kodu -> Turkce ad (kaynak: src/trader_engine/strategies/arms/*.py belge dizgileri)
KURULUM_AD = {"T1": "Trend geri çekilmesi", "R1": "Yatay piyasa kenarı", "TF1": "Trend kırılımı", "B1": "Kırılım yeniden testi",
              "H2": "İki bacaklı geri çekilme", "S1": "Sıkışma kırılımı", "F1": "Sahte kırılım dönüşü",
              # 24.11 kullanici karari: formasyon kutuphanesi (MF1 mum formasyonlari)
              "MF1-DELICI": "Mum: delici çizgi",
              "MF1-ICSAHTE": "Mum: iç çubuk sahte kopuş", "MF1-DISBAR": "Mum: dış bar", "MF1-YUTAN": "Mum: yutan",
              "MF1-HARAMI": "Mum: harami", "MF1-CIMBIZ": "Mum: cımbız dip",
              "MF1-PINBAR": "Mum: pin bar", "MF1-ICCUBUK": "Mum: iç çubuk",
              # 24.11 kullanici karari: PA varyantlari (ana kol kimligi + varyant)
              "B1-BOLGE": "Kırılım yeniden testi: bölge", "H2-MINI": "İki bacaklı geri çekilme: mini çizgi", "S1-OLCULU": "Sıkışma kırılımı: ölçülü hedef", "T1-GERI3": "Trend geri çekilmesi: 3 düşen tepe", "T1-SEVIYE": "Trend geri çekilmesi: eski direnç",
              # 24.11 kullanici karari: formasyon kutuphanesi (GF1 grafik + IN1 gosterge)
              "GF1-OBO": "Grafik: ters omuz baş omuz",
              "GF1-UCLU": "Grafik: üçlü dip",
              "GF1-KUPA": "Grafik: kupa kulp",
              "GF1-IKILI": "Grafik: ikili dip",
              "GF1-KAMA": "Grafik: düşen kama",
              "GF1-UCGEN": "Grafik: üçgen",
              "GF1-BAYRAK": "Grafik: bayrak",
              "GF1-FLAMA": "Grafik: flama",
              "GF1-RETEST": "Grafik: kırılım retesti",
              "GF1-SAHTE": "Grafik: sahte kırılım",
              "GF1-TREND": "Grafik: düşen kanal",
              "GF1-KANAL": "Grafik: kanal dibi",
              "GF1-YATAY": "Grafik: yatay direnç kırılımı",
              "IN1-UYUMSUZ": "Gösterge: RSI uyumsuzluğu",
              "IN1-MAKESISIM": "Gösterge: SMA50/200 kesişimi",
              "IN1-KUMO": "Gösterge: bulut üstü kırılımı",
              "IN1-TK": "Gösterge: tenkan/kijun kesişimi",
              "IN1-FIBO": "Gösterge: fibonacci geri çekilme",
              "IN1-HACIM": "Gösterge: hacimli kırılım",
              "IN1-RSI": "Gösterge: RSI 30 dönüşü",
              "IN1-RSIDONUS": "Gösterge: RSI 30 üstüne dönüş",
              "IN1-RSI2": "Gösterge: RSI(2) dip",
              "IN1-STOK": "Gösterge: stokastik kesişimi",
              "IN1-MACD": "Gösterge: MACD kesişimi",
              "IN1-MAGERI": "Gösterge: EMA20 geri çekilmesi",
              "IN1-BOLLKIR": "Gösterge: Bollinger üst bant kırılımı",
              "IN1-VWAP": "Gösterge: VWAP üstüne geçiş",
              "IN1-FIYATMA": "Gösterge: fiyat SMA50 üstüne geçiş",
              "IN1-HIZLIMA": "Gösterge: EMA4/EMA9 kesişimi",
              "IN1-BOLL": "Gösterge: Bollinger alt bant dönüşü",
              # 24.11 kullanici karari: formasyon kutuphanesi (PA2 price action formasyonlari)
              "PA2-EMIRBLOK": "PA: emir bloğu", "PA2-BOLGE": "PA: arz/talep bölgesi", "PA2-FVG": "PA: değer boşluğu",
              "PA2-ONCEKI": "PA: önceki dönem dibi", "PA2-TCIZGI": "PA: trend çizgisi",
              }


def kurulum_adi(setup: Any) -> str:
    s = str(setup or "?").strip().partition("@")[0]
    return KURULUM_AD.get(s, s)


def kol_adi(setup: Any, tf: Any = None) -> str:
    """Kol/kurulum kimligi -> okunur Turkce ad: 'T1@4h' -> 'Trend geri çekilmesi · 4 saat', 'R1@1d' -> 'Yatay piyasa kenarı · 1 gün'.
    `tf` ayrica verilirse (setup '@' icermiyorsa) o kullanilir. Telegram ve panel AYNI fonksiyonu kullanir."""
    s = str(setup or "?").strip()
    _, _, zf = s.partition("@")
    zf = zf or str(tf or "")
    ad = kurulum_adi(s)
    return f"{ad} · {_TF_TR.get(zf, zf)}" if zf else ad


def trade_kol(t: Any) -> str:
    """Ledger TradeRecord -> kol adi (arm_id yoksa setup@trigger_tf)."""
    return kol_adi(getattr(t, "arm_id", None) or getattr(t, "setup", None), getattr(t, "trigger_tf", None))


# ----------------------------------------------------------------------------- islem mesajlari
def ilk_buyuk(t: str) -> str:
    """Turkce baş harf büyütme ('iz süren stop' -> 'İz süren stop')."""
    return {"i": "İ", "ı": "I"}.get(t[:1], t[:1].upper()) + t[1:]


def sure_metni(a: datetime | None, b: datetime | None) -> str:
    """'45 dk', '6s 20dk', '2g 3s' (pano ve Telegram ayni biçim)."""
    if a is None or b is None:
        return "—"
    m = max(int((b - a).total_seconds() // 60), 0)
    if m < 60:
        return f"{m} dk"
    if m < 1440:
        return f"{m // 60}s {m % 60}dk" if m % 60 else f"{m // 60}s"
    return f"{m // 1440}g {(m % 1440) // 60}s"


def zd_adi(zd: Any) -> str:
    """'4h' -> '4 saat' (zaman dilimi kodu ya da hazır ad)."""
    z = str(zd or "")
    return _TF_TR.get(z, z)


def iyelik_belirtme(n: int) -> str:
    """Sayi + 3. kisi iyelik + belirtme eki, sayinin okunusuna gore: 9 -> "'unu" (dokuzu), 61 -> "'ini" (altmis biri), 2 -> "'sini"."""
    n = abs(int(n))
    t = {0: "'ı", 1: "'ini", 2: "'sini", 3: "'ünü", 4: "'ünü", 5: "'ini", 6: "'sını", 7: "'sini", 8: "'ini", 9: "'unu"}
    o = {1: "'unu", 2: "'sini", 3: "'unu", 4: "'ını", 5: "'sini", 6: "'ını", 7: "'ini", 8: "'ini", 9: "'ını"}      # on, yirmi, otuz, ...
    if n == 0:
        return t[0]
    if n % 10:
        return t[n % 10]
    if n % 100:
        return o[(n % 100) // 10]
    if n % 1000:
        return "'ünü"                       # yuz
    if n % 1000000:
        return "'ini"                       # bin
    return "'unu"                           # milyon


def puan_metni(puan: Any) -> str | None:
    """ML1 puani 2 ondalik ('0,63'); sayi degilse None."""
    try:
        v = float(puan)
    except (TypeError, ValueError):
        return None
    return sayi(v, 2) if math.isfinite(v) else None


def islem_acildi(kol: str, pair: Any, side: Any, giris: Any, tutar: Any, stop: Any, *, zd: Any = None, puan: Any = None,
                 risk: Any = None) -> str:
    """3 satir: yon/coin/zaman dilimi · kurulum adi (+ ML1 puani) · giris/stop/tutar (+ risk). `kol` kurulum adi ya da 'kurulum · zaman
    dilimi' olabilir (ikincisinde zaman dilimi oradan alinir)."""
    ad, _, zf = str(kol).partition(" · ")
    zd_t = zd_adi(zd) or zf
    p = puan_metni(puan)
    t = f"{sayi(tutar, 0)} $" if tutar is not None else "?"
    r = f" · Risk {sayi(risk, 0)} $" if risk is not None and _sonlu(risk) else ""
    return _bagla([f"{'🟩' if yon(side) == 'long' else '🟥'} {coin(pair)} {yon(side)} açıldı" + (f" · {zd_t}" if zd_t else ""),
                   ad + (f" · ML1 puanı {p}" if p else ""),
                   f"Giriş {fiyat(giris)} · Stop {fiyat(stop)} · Tutar {t}{r}"])


def _sonlu(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


# kaldirilan kol aileleri (motordaki KALDIRILAN_KOLLAR ile esitligi testle sinanir; trader_engine ice aktarilmaz)
KALDIRILAN_AILELER = ("M1", "DL1", "HB1", "C1")


def kol_ailesi(setup: Any) -> str:
    return str(setup or "").partition("@")[0].split("-")[0]


# defter kodu -> (etiket, aciklama). stop / force_exit kosula gore ayrilir (kapanis_neden)
KAPANIS_NEDEN = {
    "stop": ("stop", "Zarar durdurma seviyesine geldi."),
    "trail_stop": ("iz süren stop", "Fiyatı izleyen stop çalıştı."),
    "target": ("kâr al", "Hedef fiyata ulaştı."),
    "time_stop": ("süre doldu", "İşlem izin verilen sürede sonuçlanmadı; bot kapattı."),
    "regime_flip": ("piyasa değişti", "Piyasa yapısı işlemin tersine döndü; bot kapattı."),
    "other": ("bot kapattı (kural/koruma)",
              "Stop ya da hedefe gelmeden bot kendi kuralıyla kapattı (formasyonun çıkış kuralı ya da koruma)."),
    "manual": ("elle (borsadan)", "Pozisyon bot dışında, borsadan kapatıldı."),
    "liquidation": ("tasfiye", "Borsa pozisyonu zorla kapattı."),
}
_STOP_KAR = ("kâr al (stop)", "Stop kâra taşınmıştı; kârla kapandı.")
_KOL_KALDIRILDI = ("kol kaldırıldı", "Bu işlemi açan kol sistemden kaldırıldı; bot açık pozisyonunu kapattı.")
_ZORUNLU = ("bot kapattı (zorunlu)", "Acil durdurma ya da zorunlu kapatma.")
_BILINMIYOR = ("bilinmiyor", "Kapanış nedeni kayıtta yok.")


def _kapanis(kod: Any, pnl: float | None, setup: Any, hedef: Any = None) -> tuple[str, str]:
    k = str(kod or "")
    # Hedefli (iz sürmeyen) kolda stop yalnız başa-baş ile taşınabilir; motor bu çıkışı `trail_stop` diye kaydeder (ML1 simülasyonuyla
    # birebir eşdeğerlik için kayıt kodu değişmez) -> gösterimde kârdaysa "kâr al (stop)".
    if k == "trail_stop" and hedef is not None and pnl is not None and pnl > 0:
        return _STOP_KAR
    if k == "stop" and pnl is not None and pnl > 0:
        return _STOP_KAR
    if k == "force_exit":
        return _KOL_KALDIRILDI if kol_ailesi(setup) in KALDIRILAN_AILELER else _ZORUNLU
    return KAPANIS_NEDEN.get(k, _BILINMIYOR)


def kapanis_neden(kod: Any, pnl: float | None = None, setup: Any = None, hedef: Any = None) -> str:
    """Kapanis nedeni -> dürüst sade etiket (Telegram ve pano ayni fonksiyon). 'elle' yalniz `manual` (borsadan, bot disi) icindir;
    bilinmeyen/bos kod 'bilinmiyor' olur."""
    return _kapanis(kod, pnl, setup, hedef)[0]


def kapanis_aciklama(kod: Any, pnl: float | None = None, setup: Any = None, hedef: Any = None) -> str:
    return _kapanis(kod, pnl, setup, hedef)[1]


def islem_kapandi(kol: str, pair: Any, side: Any, pnl: float, notional: float | None, neden: Any, kritik: bool = False, *,
                  r: Any = None, zd: Any = None, sure: str | None = None, setup: Any = None, hedef: Any = None) -> str:
    """2 satir: sonuc (K/Z ve R; R yoksa yuzde) · neden, zaman dilimi, sure."""
    if r is not None and _sonlu(r):
        yuz = f" ({isaretli(float(r), 2)} R)"
    else:
        yuz = f" ({isaretli(pnl / notional * 100, 1)}%)" if notional else ""
    isaret = "🔴" if kritik else ("🟢" if pnl > 0 else ("🔻" if pnl < 0 else "⚪"))
    et = kapanis_neden(neden, pnl, setup, hedef)
    ikinci = "Kol kaldırıldı: bot pozisyonu kapattı" if et == "kol kaldırıldı" else ilk_buyuk(et)
    if zd:
        ikinci += f" · {zd_adi(zd)}"
    if sure and sure != "—":
        ikinci += f" · {sure} sürdü"
    return _bagla([f"{isaret} {coin(pair)} {yon(side)} kapandı · {isaretli(pnl)} ${yuz}", ikinci])


def islemler_acildi(satirlar: list[tuple]) -> str:
    """Ayni dakikadaki acilislar tek mesaj; her satir (kol, pair, side, giris, tutar, stop[, zd, puan, risk]). Tek islem -> `islem_acildi`."""
    rows = [tuple(x) + (None,) * (9 - len(x)) for x in satirlar]
    if len(rows) == 1:
        k, pr, sd, g, t, st, zd, pu, rk = rows[0]
        return islem_acildi(k, pr, sd, g, t, st, zd=zd, puan=pu, risk=rk)
    out = [f"🟩 {len(rows)} işlem açıldı"]
    for k, pr, sd, g, t, st, zd, pu, rk in rows[:4]:
        zf = zd_adi(zd) or str(k).partition(" · ")[2]
        p = puan_metni(pu)
        out.append(f"{coin(pr)} {yon(sd)}" + (f" · {zf}" if zf else "") + f" · {sayi(t, 0)} $" + (f" · puan {p}" if p else ""))
    if len(rows) > 4:
        out.append(f"… ve {len(rows) - 4} işlem daha")
    return _bagla(out)


def saatlik_ozet(acilan: int, kapanan: int, net: float) -> str:
    return _bagla([f"Son 1 saatte {acilan + kapanan} işlem daha: {acilan} açıldı, {kapanan} kapandı · net {isaretli(net)} $"])


# ----------------------------------------------------------------------------- gunluk zarar
def limit_orani(config_dir: str | Path | None, mode: Any = "paper") -> float:
    """Gunluk zarar orani: kagitta engine.base/learner/paper, canlida (23.11 kullanici karari: canli = kagit) engine.base/learner/live
    ayarindaki risk.daily_max_loss (risk.paper_config / risk.live_config ile dogrulanir). Okunamazsa LOCKED_CFG.
    trader_engine ice aktarilmaz."""
    from . import risk as R  # noqa: PLC0415
    canli = str(mode) == "live"
    try:
        v = _risk_sozlugu(config_dir, canli).get("daily_max_loss")
        if v is None:
            return R.LOCKED_CFG.daily_max_loss
        return (R.live_config if canli else R.paper_config)(daily_max_loss=float(v)).daily_max_loss
    except (OSError, ValueError, TypeError):
        return R.LOCKED_CFG.daily_max_loss


def _ayar_dizini(config_dir: str | Path | None) -> str:
    return str(config_dir) if config_dir else ((os.environ.get("ENGINE_CONFIG_DIR") or "").strip()
                                               or str(Path(__file__).resolve().parent.parent.parent / "config"))


def motor_ayari(config_dir: str | Path | None, canli: bool = False) -> dict:
    """engine.base/learner/(live|paper) ayar dosyalarinin birlesimi (motorun kullandigi sira; ust anahtarlar, sozluk bolumleri
    birlesir). Dosya yoksa atlanir; bozuk dosya OSError/ValueError firlatir."""
    out: dict = {}
    for ad in ("engine.base.json", "engine.learner.json", "engine.live.json" if canli else "engine.paper.json"):
        p = Path(_ayar_dizini(config_dir)) / ad
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            for k, v in d.items():
                if isinstance(v, dict) and isinstance(out.get(k), dict):
                    out[k].update(v)
                else:
                    out[k] = v
    return out


def _risk_sozlugu(config_dir: str | Path | None, canli: bool) -> dict:
    """engine.base/learner/(live|paper) ayar dosyalarindaki `risk` bolumu (motorun kullandigi birlesim)."""
    r = motor_ayari(config_dir, canli).get("risk")
    return dict(r) if isinstance(r, dict) else {}


def risk_ayari(config_dir: str | Path | None, mode: Any = "paper"):
    """Kipin ayar dosyasindaki risk limitleri (max_open_risk, max_same_dir_risk, daily_max_loss); okunamazsa LOCKED_CFG."""
    from . import risk as R  # noqa: PLC0415
    canli = str(mode) == "live"
    try:
        kw = {k: float(v) for k, v in _risk_sozlugu(config_dir, canli).items() if k in R.PAPER_KEYS and k != "target_trade_risk"}
        return (R.live_config if canli else R.paper_config)(**kw)
    except (OSError, ValueError, TypeError):
        return R.LOCKED_CFG


def limit_uyari(zarar: float, limit: float) -> str:
    return _bagla(["⚠️ Günlük zarar sınırına yaklaşıldı",
                   f"Bugün {sayi(zarar, 0)} $ kaybedildi; sınır {sayi(limit, 0)} $ (%80'i doldu).",
                   "Sınır dolarsa bugün yeni işlem açılmaz."])


def limit_doldu(zarar: float, limit: float) -> str:
    return _bagla(["🔴 Günlük zarar sınırı doldu",
                   f"Bugün {sayi(zarar, 0)} $ kaybedildi (sınır {sayi(limit, 0)} $).",
                   "Açık işlemler stoplarıyla izleniyor; yarın 00:00'a kadar yeni işlem açılmaz."])


def _no_sil(x: Any) -> str:
    """'#12 SOL long: ...' -> 'SOL long: ...' (islem numarasi yerine coin adi kalir)."""
    return re.sub(r"\s*#\d+\s*", " ", str(x)).strip()


def islem_kontrolu(doc: Mapping[str, Any] | int) -> str:
    """Sorun bildirimi (yalniz gercek sorun varsa gonderilir): coin adli sade satirlar, islem numarasi yok. Sayi verilirse tek satir."""
    if not isinstance(doc, Mapping):
        return etiketle(f"⚠️ İşlem kontrolünde {int(doc)} uyuşmazlık bulundu")
    return islem_kontrolu_sorun(doc)


def islem_kontrolu_sorun(doc: Mapping[str, Any]) -> str:
    """doc['sorunlar'] (mutabakat.sorunlar) -> ilk satirda tek ⚠️ + en fazla 3 sorun satiri (toplam 4 satir)."""
    sor = [_no_sil(x)[:140] for x in list(doc.get("sorunlar") or [])]
    if not sor:
        return _bagla(["⚠️ İşlem kontrolünde sorun bulundu"])
    return _bagla([f"⚠️ İşlem kontrolünde {len(sor)} uyuşmazlık bulundu"] + sor[:3], 4)


def islem_kontrolu_ozet(doc: Mapping[str, Any]) -> str:
    """Islem mutabakati ozeti (<=4 satir; en fazla 3 ornek; sade Turkce, simge/formul yok)."""
    satir = doc.get("satirlar") or []
    long_n = sum(1 for r in satir if r.get("yon") == "long")
    short_n = sum(1 for r in satir if r.get("yon") == "short")
    kasa = next((k for k in doc.get("kontroller") or [] if str(k.get("ad", "")).startswith("Kasa")), None)
    kasa_t = "kasa tutuyor" if kasa and kasa.get("sonuc") == "geçti" else (
        "kasa tutmuyor" if kasa and kasa.get("sonuc") == "kaldı" else "kasa ölçülemedi")
    n, z = int(doc.get("islem_sayisi") or 0), int(doc.get("uyusmazlik_sayisi") or 0)
    sat = [f"İşlem kontrolü: {n} işlem (açık {int(doc.get('acik') or 0)} / kapanan {int(doc.get('kapanan') or 0)} · "
           f"long {long_n} / short {short_n}) · uyuşmazlık {z} · {kasa_t}"]
    sat += [f"- {_no_sil(u)[:120]}" for u in list(doc.get("uyusmazliklar") or [])[:3]]
    bek = [i for i in (doc.get("fiyat_bekleniyor") or []) if isinstance(i, int)]
    if bek:                                       # nötr bilgi satırı: uyuşmazlık sayılmaz
        coinler = {r.get("islem_no"): r.get("coin") for r in satir if isinstance(r, Mapping)}
        ad = [str(coinler[i]) for i in bek[:6] if coinler.get(i)]
        bilinmeyen = len(bek) - len(ad)
        sat.append("Fiyat bekleniyor (piyasa kapalı/veri yok): " + ", ".join(ad + ([f"{bilinmeyen} işlem"] if bilinmeyen > 0 else [])))
    return _bagla(sat)


# ----------------------------------------------------------------------------- sembol (dayaniklilik)
def sembol_disi(pair: Any, pozisyon_var: bool) -> str:
    c = coin(pair)
    if pozisyon_var:
        return _bagla([f"🔴 {c} borsada işlem dışı ve açık pozisyon var.", "Bot zorla kapatmıyor; stop borsada bekliyor."])
    return _bagla([f"⚠️ {c} borsada işlem dışı; bu coinde yeni işlem açılmıyor."])


def sembol_geri(pair: Any) -> str:
    return _bagla([f"✅ Düzeldi: {coin(pair)} yeniden işlemde."])


# ----------------------------------------------------------------------------- bot durdu
def _pozisyonlar(status_path: str | None) -> tuple[int | None, str | None]:
    """(acik pozisyon sayisi, kip); okunamazsa (None, None)."""
    try:
        st = json.loads(Path(str(status_path)).read_text(encoding="utf-8"))
        return len(st.get("open_positions") or []), str(st.get("mode") or "")
    except Exception:  # noqa: BLE001
        return None, None


def bot_durdu(status_path: str | None = None, ne: str = "Bot durdu") -> str:
    """Kagitta stop 'benzetilmis borsa'da (engine surecinin icinde; brokers/paper.py:298 place_stop, :545 stop_hit yalniz
    motor `advance` cagirinca) izlenir: motor durunca stoplar izlenmez. Canlida STOP_MARKET emri borsada durur
    (brokers/binance_futures.py:1129)."""
    n, mod = _pozisyonlar(status_path)
    if n is None:
        poz = "Açık pozisyon bilgisi okunamadı."
    elif n == 0:
        poz = "Açık pozisyon yok."
    elif mod == "live":
        poz = f"Açık pozisyon: {n}; stop emirleri borsada duruyor."
    else:
        poz = f"Açık pozisyon: {n}; bot durmuşken stoplar izlenmiyor."
    return _bagla([f"🔴 {ne}", poz, "Otomatik yeniden başlatma deneniyor."])


def bot_duzeldi() -> str:
    return _bagla(["✅ Düzeldi: bot yeniden çalışıyor."])


def duzeldi(ne: str) -> str:
    ne = temizle(ne).rstrip(".")
    kisalt = ne[1:2].isupper() or ne[:2].isupper()          # 'ML1 modeli ...' gibi kisaltmanin ilk harfi kucultulmez
    return _bagla([f"✅ Düzeldi: {ne if kisalt else ne[:1].lower() + ne[1:]}."])


# ----------------------------------------------------------------------------- saglik uyarilari
# kod ya da kontrol adi -> (ne oldu, ne yapiliyor, Senden | None, duzeldi)
_SADE: dict[str, tuple[str, str, str | None, str]] = {
    "ml_no_model": ("ML1 modeli yüklenemedi.", "Kural adayları atlanıyor; açık işlemler stoplarıyla izleniyor.", None,
                    "ML1 modeli yüklendi"),
    "exchange_ban_open_positions": ("Borsa geçici engel koydu, açık pozisyon var.",
                                    "Borsadaki stoplar yerinde; engel bitince bot emir göndermeye devam eder.",
                                    "Gerekirse pozisyonu Binance uygulamasından elle kapat.", "borsa engeli kalktı"),
    "exchange_ban": ("Borsa geçici engel koydu.", "Bot engel bitene kadar emir göndermiyor.", None, "borsa engeli kalktı"),
    "account_mode_drift": ("Hesap ayarı değişmiş, yeni işlem açılmıyor.", "Açık pozisyonlar stoplarıyla izleniyor.",
                           "Binance'te kaldıraç ya da marjin tipini elle değiştirdiysen eski haline getir.",
                           "hesap ayarı yeniden doğru"),
    "naked_position": ("Stopu olmayan açık pozisyon var!", "Bot stop koymayı deniyor.",
                       "Binance uygulamasında pozisyona stop koy ya da kapat.", "stopsuz pozisyon kalmadı"),
    "exchange_unreachable": ("Borsaya ulaşılamıyor.", "Bağlantı yeniden deneniyor.", None,
                             "borsa bağlantısı yeniden sağlandı"),
    "disk_dolu": ("Disk dolmak üzere.", "Haftalık bakım eski dosyaları temizliyor.", "Yetmezse yer açılması için bana haber ver.",
                  "disk doluluğu normale döndü"),
    "disk_kritik": ("Disk neredeyse dolu.", "Dolarsa kayıtlar yazılamaz.", "Hemen yer açılması gerekiyor; bana haber ver.",
                    "disk doluluğu kritik seviyeden indi"),
    "disk_low": ("Disk neredeyse dolu.", "Dolarsa kayıtlar yazılamaz.", "Hemen yer açılması gerekiyor; bana haber ver.",
                 "disk doluluğu normale döndü"),
    "candle_age": ("Piyasa verisi güncel değil.", "Yeni işlem açılmıyor; veri bekleniyor.", None, "piyasa verisi güncel"),
    "market_bar_age": ("Piyasa verisi güncel değil.", "Yeni işlem açılmıyor; veri bekleniyor.", None, "piyasa verisi güncel"),
    "ledger_write_age": ("Kayıt defterine uzun süredir yazılmadı.", "Kayıtlar gecikmiş olabilir; izleniyor.", None,
                         "kayıt defterine yeniden yazılıyor"),
    "ledger_gate": ("İşlem kayıt sistemi giriş kapısı kapalı.", "Yeni işlem açılmıyor; açık pozisyonlar izleniyor.", None,
                    "kayıt sistemi yeniden açık"),
    "spool_corrupt": ("Deftere yazılamayan bozuk kayıt var.", "Kayıtlar incelenmeli; açık pozisyonlar izleniyor.", "Bana haber ver.",
                      "bozuk kayıt kalmadı"),
    "risk_ladder": ("Risk koruması devrede.", "Sermaye koruma kuralları yeni işlemleri kısıtlayabilir.", None,
                    "risk koruması yeniden normal"),
    "backup_age": ("Yedek alınmıyor ya da çok eski.", "Yedekleme yeniden deneniyor.", None, "yedekleme düzenli"),
    "container_restarts": ("Bot sık sık yeniden başlıyor.", "Kendini toparlıyor; izleniyor.", None, "bot kararlı çalışıyor"),
}
# Panel (TEKNIK/OZET) icin: _SADE'de olmayan saglik kodlari -> (sade cumle, Senden | None). Telegram'a gitmeyen (_SUSTUR) kodlar da
# panelde adiyla gorunur. Kod/ad kullaniciya SIZMAZ; bilinmeyen kod -> SAGLIK_BILINMEYEN.
SAGLIK_BILINMEYEN = "Bir sistem kontrolü uyarı veriyor (kod gösterilmez)"
_SAGLIK_EK: dict[str, tuple[str, str | None]] = {
    # sunucu kaynaklari
    "disk_unknown": ("Disk doluluğu okunamıyor", None),
    "no_backup": ("Henüz yedek alınmamış", None),
    "clock_skew": ("Sunucu saati ile kayıt zamanları uyuşmuyor", None),
    "internal_error": ("Sağlık kontrolü kendi içinde hata verdi", None), "missing_check": ("Bir sağlık kontrolü çalışmadı", None),
    # bot / motor
    "loop_unknown": ("Bot döngüsü doğrulanamıyor", None),
    "container_not_running": ("Bot çalışmıyor", None), "container_restarted": ("Bot yeniden başladı", None),
    "container_unknown": ("Bot çalışma durumu okunamıyor", None), "oom_killed": ("Bot bellek yetmediği için kapandı", None),
    "restart_loop": ("Bot sık sık yeniden başlıyor", None), "engine_gate_closed": ("Yeni işlem kapısı kapalı", None),
    "engine_kill": ("Acil durdurma anahtarı açık; yeni işlem açılmıyor", "İstemeden açıldıysa bana haber ver."),
    "gate_unknown": ("Yeni işlem kapısı durumu okunamıyor", None), "no_active_params": ("Bot ayarları (aktif parametreler) bulunamadı", None),
    "naked_unknown": ("Stop emirleri doğrulanamıyor", None),
    # borsa ve piyasa verisi
    "exchange_unknown": ("Borsa bağlantısı doğrulanamıyor", None), "exchange_ban_file_corrupt": ("Borsa engel kaydı bozuk", None),
    "market_bars_stale": ("Piyasa verisi güncel değil", None),
    "market_db_missing": ("Piyasa veri dosyası yok", None), "market_db_unreadable": ("Piyasa veri dosyası okunamıyor", None),
    "candle_unknown": ("Piyasa mumları doğrulanamıyor", None), "pairs_unknown": ("İşlem çiftleri doğrulanamıyor", None),
    # kayit defteri
    "ledger_age_unknown": ("Kayıt defteri son yazım zamanı okunamıyor", None),
    "ledger_errors": ("Kayıt defterinde yazma hataları var", None),
    "schema": ("Kayıt defteri şeması beklenenden farklı", "Bana haber ver."),
    "spool_corrupt": ("Deftere yazılamayan bozuk kayıt var", None), "spool_pending": ("Deftere yazılmayı bekleyen kayıt birikti", None),
    "spool_corrupt_unreadable": ("Bozuk kayıt dosyası okunamıyor", None),
    "unledgered_trades": ("Deftere işlenmemiş işlem var", "Bana haber ver."),
    # risk, hesap, canli
    "ladder_missing": ("Risk kademesi bilgisi yok", None), "ladder_invalid": ("Risk kademesi bilgisi geçersiz", None),
    "capital_missing": ("Sermaye bilgisi okunamıyor", None), "equity_unreadable": ("Kasa bilgisi okunamıyor", None),
    "capital_latch": ("Ana para kilidi: kasa ana paranın %15 altına indi", "Yeni girişler kapalı; açmak için /devam yaz."),
    "capital_floor": ("Sermaye koruma alt sınırına yaklaşıldı", None), "drawdown_review": ("Zirveden düşüş incelemesi gerekiyor", None),
    "account_mode_unverified": ("Hesap ayarı doğrulanamadı, bir giriş atlandı", None),
    "account_mode_unknown": ("Hesap ayarı bilgisi okunamıyor", None),
    "live_paths_mismatch": ("Canlı bot ayar yolları tutarsız", "Kurulumun yeniden çalıştırılması gerekiyor; bana haber ver."),
}
_SAGLIK_EK_AD: dict[str, str] = {   # kod taninmazsa kontrol adinin (":bot" oncesi) genel cumlesi
    "disk_free": "Sunucuda boş disk alanı azaldı",
    "bot_loop_age": "Bot döngüsü durmuş görünüyor", "ledger_write_age": "Kayıt defterine uzun süredir yazılmadı",
    "ledger_gate": "Kayıt sistemi giriş kapısı kapalı", "spool_corrupt": "Deftere yazılamayan bozuk kayıt var",
    "account_mode": "Hesap ayarı bilgisi sorunlu", "exchange_reachable": "Borsaya ulaşılamıyor",
    "risk_ladder": "Risk kademesi sorunlu", "live_paths": "Canlı bot ayar yolları tutarsız",
}


def saglik_cumlesi(name: Any, code: Any) -> tuple[str, str | None]:
    """Panel icin: saglik kontrolu (ad, kod) -> (sade Turkce cumle, Senden | None). Tek sozluk: once Telegram uyari metinleri (_SADE),
    sonra _SAGLIK_EK; bilinmeyen -> SAGLIK_BILINMEYEN. `_warmup` eki (motor yeni basladi) kodun anlamini degistirmez."""
    c = str(code or "")
    if c.endswith("_warmup"):
        c = c[: -len("_warmup")]
    base = str(name or "").partition(":")[0]
    ent = _SADE.get(c) or _SADE.get(base)
    if ent is not None:
        return ent[0].rstrip("."), ent[2]
    if c in _SAGLIK_EK:
        return _SAGLIK_EK[c]
    if base in _SAGLIK_EK_AD:
        return _SAGLIK_EK_AD[base], None
    return SAGLIK_BILINMEYEN, None


# bu kodlar/adlar kullaniciya hic gitmez (yapabilecegi bir sey yok ya da isleme etkisi yok)
_SUSTUR = frozenset({
    "heartbeat_send_failed", "state_reset", "exchange_ban_file_corrupt", "account_mode_unverified", "account_mode_unknown",
    "live_paths_mismatch", "multiple"})
_BOT_DURDU = frozenset({"bot_loop_age", "engine_retry_exhausted"})


def _kod_ad(alert: Any) -> tuple[str, str]:
    code = str(getattr(alert, "code", "") or "")
    fp = str(getattr(alert, "fingerprint", "") or "")
    return code, fp.split("|")[0].split(":")[0]


def alarm_anahtari(alert: Any) -> str:
    """Kararli anahtar: zaman damgasi / 'duzeldi' eki atilir ('disk|dolu|<iso>' ve 'disk|dolu|duzeldi|<iso>' -> 'disk|dolu')."""
    fp = str(getattr(alert, "fingerprint", "") or getattr(alert, "code", ""))
    parts = fp.split("|")
    return "|".join(parts[:2])


def saglik_mesaji(alert: Any, status_path: str | None = None) -> tuple[str, str | None, str]:
    """Alert -> (tur, metin|None, anahtar). tur: 'alarm' | 'duzeldi' | 'bot_durdu' | 'bot_duzeldi' | 'sustur'.
    Metin None -> hicbir sey gonderilmez."""
    code, ad = _kod_ad(alert)
    key = alarm_anahtari(alert)
    lvl = str(getattr(getattr(alert, "level", ""), "value", getattr(alert, "level", ""))).upper()
    bot = code in _BOT_DURDU or ad in _BOT_DURDU
    ok = lvl in ("OK", "INFO")
    if code in _SUSTUR or ad in _SUSTUR or "@testnet" in str(getattr(alert, "fingerprint", "")):   # testnet golge botu Telegram'a gitmez
        return "sustur", None, key
    if bot:
        return ("bot_duzeldi", bot_duzeldi(), key) if ok else ("bot_durdu", bot_durdu(status_path), key)
    ent = _SADE.get(code) or _SADE.get(ad)
    if ent is None:
        # bilinmeyen kontrol: yalniz kritikse tek sade satir (kod adi sizmaz)
        if ok or lvl not in ("CRIT", "CRITICAL", "UNKNOWN", "FAIL"):
            return "sustur", None, key
        return "alarm", _bagla(["🔴 Bir sistem kontrolü ciddi şekilde sorunlu.", "Açık pozisyonlar stoplarıyla izleniyor; inceleniyor."]), key
    ne, yap, senden, duz = ent
    if ok:
        return "duzeldi", duzeldi(duz), key
    if code in ("disk_dolu", "disk_kritik"):
        m = re.search(r"%(\d+)", str(getattr(alert, "title", "")))
        if m:
            ne = ne.rstrip(".") + f" (%{m.group(1)})."
    ikon = "🔴" if lvl in ("CRIT", "CRITICAL", "UNKNOWN", "FAIL") else "⚠️"
    return "alarm", _bagla([f"{ikon} {ne}", yap, f"Senden: {senden}" if senden else ""]), key


def birim_metni(birim: str, status_path: str | None = None) -> str | None:
    """'Birim basarisiz: trader-xyz.service' (systemd OnFailure) -> sade metin; None = susturulur."""
    b = str(birim)
    if "engine" in b:
        return bot_durdu(status_path)
    if "feed" in b:
        return _bagla(["🔴 Fiyat akışı durdu", "Yeni işlem açılmıyor; yeniden başlatma deneniyor."])
    if "backup" in b:
        return _bagla(["⚠️ Yedekleme başarısız oldu", "Bir sonraki turda yeniden denenecek."])
    return None


# ----------------------------------------------------------------------------- durum defteri
class Kayit:
    """Alarm tekrar sinirlayici + gunluk-bir-kez isaretleri. Dosya: <var>/alarm_kaydi.json (bozuksa bos baslar)."""

    def __init__(self, path: str | Path, now_fn: Callable[[], datetime]):
        self.path, self.now = Path(path), now_fn

    def _oku(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _yaz(self, d: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def gonder_mi(self, key: str, saat: float = EK_HATIRLATMA_SAAT) -> bool:
        """Ayni uyari son `saat` icinde gittiyse False. Gidiyorsa kaydeder (aktif)."""
        d = self._oku()
        a = d.setdefault("alarm", {})
        e = a.get(key) if isinstance(a.get(key), dict) else {}
        now = self.now().timestamp()
        if e and now - float(e.get("son", 0)) < saat * 3600:
            return False
        a[key] = {"son": now}
        self._yaz(d)
        return True

    def isaretle(self, key: str) -> None:
        """6 saat kurali olmadan aktif isaretler (Bot durdu)."""
        d = self._oku()
        d.setdefault("alarm", {})[key] = {"son": self.now().timestamp()}
        self._yaz(d)

    def aktif_mi(self, key: str) -> bool:
        a = self._oku().get("alarm", {})
        return isinstance(a, dict) and key in a

    def kapat(self, key: str) -> bool:
        """Uyari kaydini siler; kayit varsa True (Duzeldi gonderilir)."""
        d = self._oku()
        a = d.get("alarm", {})
        if isinstance(a, dict) and key in a:
            del a[key]
            self._yaz(d)
            return True
        return False

    def durum(self, key: str) -> dict:
        v = self._oku().get("durum", {})
        e = v.get(key) if isinstance(v, dict) else None
        return e if isinstance(e, dict) else {}

    def durum_yaz(self, key: str, val: dict) -> None:
        d = self._oku()
        d.setdefault("durum", {})[key] = val
        self._yaz(d)

    def gunde_bir(self, key: str, gun: str) -> bool:
        """key bugun (gun) daha once isaretlenmediyse isaretler ve True doner."""
        d = self._oku()
        g = d.setdefault("gunluk", {})
        if g.get(key) == gun:
            return False
        g[key] = gun
        self._yaz(d)
        return True
