"""Telegram mesajlarini seyrek ve sade tutan katman (kullanici: teknik olmayan, Turkce).

Saf bicimleyiciler + kucuk bir durum defteri. Kurallar:
  * her mesaj "[ML] " ile baslar; en cok 6 satir (gunluk ozet 12); dosya/servis/modul/kod adi, alt cizgi, journalctl/sunucu yok;
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
MAX_SATIR_OZET = 12
LIMIT_ORANI = 0.05          # gunluk zarar butcesi (risk kilidiyle ayni %5)
UYARI_ORANI = 0.80          # limitin %80'i
BOT_AD = {"learner": "öğrenen"}     # panelde gorunen ad (panel.js BOT_AD)
TR = timezone(timedelta(hours=3))

_YASAK = re.compile(r"journalctl|systemctl|sunucu|\.py\b|\.service\b|\.timer\b|\.json\b|\.sqlite\b|_", re.I)


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
    if _YASAK.search(text):
        out.append("yasak")
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
              "M1": "Yapay zekâ adayı"}


def kurulum_adi(setup: Any) -> str:
    s = str(setup or "?").strip().partition("@")[0]
    return KURULUM_AD.get(s, s)


def kol_adi(setup: Any, tf: Any = None) -> str:
    """Kol/kurulum kimligi -> okunur Turkce ad: 'M1@1h' -> 'Yapay zekâ adayı · 1 saat', 'R1@1d' -> 'Yatay piyasa kenarı · 1 gün'.
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
def islem_acildi(kol: str, pair: Any, side: Any, giris: Any, tutar: Any, stop: Any) -> str:
    t = f"{sayi(tutar, 0)} $" if tutar is not None else "?"
    return _bagla([f"{'🟩' if yon(side) == 'long' else '🟥'} {kol} · {coin(pair)} · {yon(side)}",
                   f"Giriş {fiyat(giris)} · Tutar {t} · Stop {fiyat(stop)}"])


KAPANIS_NEDEN = {"stop": "stop", "trail_stop": "stop", "liquidation": "stop", "target": "kâr al", "time_stop": "süre",
                 "manual": "elle", "force_exit": "elle", "regime_flip": "piyasa değişti"}


def kapanis_neden(kod: Any, pnl: float | None = None) -> str:
    """Kapanis nedeni -> sade metin (Telegram ve panel ayni fonksiyon). Iz suren stop ve kârla kapanan stop ayirt edilir."""
    k = str(kod)
    if k == "trail_stop":
        return "iz süren stop"
    if k == "stop" and pnl is not None and pnl > 0:
        return "kâr al (stop)"
    return KAPANIS_NEDEN.get(k, "elle")


def islem_kapandi(kol: str, pair: Any, side: Any, pnl: float, notional: float | None, neden: Any, kritik: bool = False) -> str:
    yuz = f" ({isaretli(pnl / notional * 100, 1)}%)" if notional else ""
    isaret = "🔴" if kritik else ("🟢" if pnl > 0 else ("🔻" if pnl < 0 else "⚪"))
    return _bagla([f"{isaret} {kol} · {coin(pair)} · {yon(side)} kapandı",
                   f"Sonuç {isaretli(pnl)} ${yuz} · {kapanis_neden(neden, pnl)}"])


def islemler_acildi(satirlar: list[tuple[str, Any, Any, Any, Any, Any]]) -> str:
    """Ayni dakikadaki acilislar tek mesaj; her satir bir islem. Tek islem -> `islem_acildi` (tam 2 satir)."""
    if len(satirlar) == 1:
        return islem_acildi(*satirlar[0])
    out = [f"🟩 {len(satirlar)} işlem açıldı"]
    for kol, pair, side, giris, tutar, stop in satirlar[: MAX_SATIR - 2]:
        out.append(f"{kol} · {coin(pair)} · {yon(side)} · {fiyat(giris)} · {sayi(tutar, 0)} $ · stop {fiyat(stop)}")
    if len(satirlar) > MAX_SATIR - 2:
        out.append(f"… ve {len(satirlar) - (MAX_SATIR - 2)} işlem daha")
    return _bagla(out)


def saatlik_ozet(acilan: int, kapanan: int, net: float) -> str:
    return _bagla([f"Son 1 saatte {acilan + kapanan} işlem daha: {acilan} açıldı, {kapanan} kapandı · net {isaretli(net)} $"])


# ----------------------------------------------------------------------------- gunluk zarar
def limit_orani(config_dir: str | Path | None, mode: Any = "paper") -> float:
    """Gunluk zarar orani: canlida kilitli (LOCKED_CFG), kagitta engine.base/learner/paper ayarindaki risk.daily_max_loss
    (risk.paper_config ile dogrulanir). Okunamazsa LOCKED_CFG. trader_engine ice aktarilmaz."""
    from . import risk as R  # noqa: PLC0415
    if str(mode) == "live":
        return R.LOCKED_CFG.daily_max_loss
    if not config_dir:
        config_dir = (os.environ.get("ENGINE_CONFIG_DIR") or "").strip() or str(Path(__file__).resolve().parent.parent.parent / "config")
    try:
        cfg: dict = {}
        for ad in ("engine.base.json", "engine.learner.json", "engine.paper.json"):
            p = Path(config_dir) / ad
            if p.exists():
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d.get("risk"), dict):
                    cfg.setdefault("risk", {}).update(d["risk"])
        v = (cfg.get("risk") or {}).get("daily_max_loss")
        if v is None:
            return R.LOCKED_CFG.daily_max_loss
        return R.paper_config(daily_max_loss=float(v)).daily_max_loss
    except (OSError, ValueError, TypeError):
        return R.LOCKED_CFG.daily_max_loss


def limit_uyari(zarar: float, limit: float) -> str:
    return _bagla(["⚠️ Günlük zarar sınırına yaklaşıldı",
                   f"Bugün {sayi(zarar)} $ kaybedildi; sınır {sayi(limit)} $ (%80 doldu).",
                   "Sınıra gelirse yeni işlem açılmaz."])


def limit_doldu(zarar: float, limit: float) -> str:
    return _bagla(["🛑 Günlük zarar limiti doldu",
                   f"Bugün {sayi(zarar)} $ kaybedildi (sınır {sayi(limit)} $).",
                   "Açık pozisyonlar stoplarıyla yönetilmeye devam ediyor; yarına kadar yeni işlem açılmaz."])


def islem_kontrolu(doc: Mapping[str, Any] | int) -> str:
    """Sorun bildirimi (yalniz gercek sorun varsa gonderilir): coin adli sade satirlar, islem numarasi yok. Sayi verilirse tek satir."""
    if not isinstance(doc, Mapping):
        return etiketle(f"⚠️ İşlem kontrolü: {int(doc)} uyuşmazlık bulundu, inceleniyor.")
    return islem_kontrolu_sorun(doc)


def islem_kontrolu_sorun(doc: Mapping[str, Any]) -> str:
    """doc['sorunlar'] (mutabakat.sorunlar) -> '[ML] ⚠️ ...' satirlari (en fazla 4)."""
    sat = [f"⚠️ {str(x)[:140]}" for x in list(doc.get("sorunlar") or [])[:4]]
    return _bagla(sat or ["⚠️ İşlem kontrolünde sorun bulundu, inceleniyor."])


def islem_kontrolu_ozet(doc: Mapping[str, Any]) -> str:
    """Islem mutabakati ozeti (<=4 satir; en fazla 3 ornek; sade Turkce, formul yok). Kurulum ozeti ve gunluk uyari bunu kullanir."""
    satir = doc.get("satirlar") or []
    long_n = sum(1 for r in satir if r.get("yon") == "long")
    short_n = sum(1 for r in satir if r.get("yon") == "short")
    kasa = next((k for k in doc.get("kontroller") or [] if str(k.get("ad", "")).startswith("Kasa")), None)
    kasa_t = "kasa tutuyor ✅" if kasa and kasa.get("sonuc") == "geçti" else (
        "kasa tutmuyor ❌" if kasa and kasa.get("sonuc") == "kaldı" else "kasa ölçülemedi")
    n, z = int(doc.get("islem_sayisi") or 0), int(doc.get("uyusmazlik_sayisi") or 0)
    sat = [f"İşlem kontrolü: {n} işlem (açık {int(doc.get('acik') or 0)} / kapanan {int(doc.get('kapanan') or 0)} · "
           f"long {long_n} / short {short_n}) · uyuşmazlık {z} · {kasa_t}"]
    sat += [f"- {str(u)[:120]}" for u in list(doc.get("uyusmazliklar") or [])[:3]]
    bek = [i for i in (doc.get("fiyat_bekleniyor") or []) if isinstance(i, int)]
    if bek:                                       # nötr bilgi satırı: uyuşmazlık sayılmaz
        sat.append("ℹ️ Fiyat bekleniyor (piyasa kapalı/veri yok): " + ", ".join(f"#{i}" for i in bek[:6]))
    return _bagla(sat)


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
    return _bagla([f"✅ Düzeldi: {ne[:1].lower() + ne[1:]}."])


# ----------------------------------------------------------------------------- saglik uyarilari
# kod ya da kontrol adi -> (ne oldu, ne yapiliyor, Senden | None, duzeldi)
_SADE: dict[str, tuple[str, str, str | None, str]] = {
    "ml_expired": ("Modelin süresi doldu.", "Yeni işlem açılmıyor; açık pozisyonlar stoplarıyla izleniyor.", None,
                   "model yenilendi, yeni işlemler açık"),
    "ml_no_model": ("Model yüklenemedi.", "Yeni işlem açılmıyor; açık pozisyonlar stoplarıyla izleniyor.", None,
                    "model yüklendi, yeni işlemler açık"),
    "ml_expiring_1d": ("Modelin süresi yarın doluyor.", "Yenilenmezse yeni işlemler durur.", None, "model yenilendi"),
    "budget_exhausted": ("Yapay zekâ bütçesi tükendi.", "Yeni işlem açılmıyor; açık pozisyonlar izleniyor.", None,
                         "yapay zekâ bütçesi yeniden yeterli"),
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
    "feed_status_age": ("Fiyat akışı durmuş görünüyor.", "Yeni işlem açılmıyor; akış yeniden başlatılıyor.", None,
                        "fiyat akışı yeniden çalışıyor"),
    "market_bar_age": ("Piyasa verisi güncel değil.", "Yeni işlem açılmıyor; veri bekleniyor.", None, "piyasa verisi güncel"),
    "acik_pozisyon_fiyat_bayat": ("Açık pozisyonun fiyatı gelmiyor.", "Stop, fiyat gelince işlenir; veri bekleniyor.", None,
                                  "açık pozisyonun fiyatı yeniden geliyor"),
    "open_price_stale": ("Açık pozisyonun fiyatı gelmiyor.", "Stop, fiyat gelince işlenir; veri bekleniyor.", None,
                         "açık pozisyonun fiyatı yeniden geliyor"),
    "veto_file_age": ("Yapay zekâ filtresi güncel değil.", "Yeni işlem açılmıyor; açık pozisyonlar korunuyor.", None,
                      "yapay zekâ filtresi güncel"),
    "backup_age": ("Yedek alınmıyor ya da çok eski.", "Yedekleme yeniden deneniyor.", None, "yedekleme düzenli"),
    "container_restarts": ("Bot sık sık yeniden başlıyor.", "Kendini toparlıyor; izleniyor.", None, "bot kararlı çalışıyor"),
}
# Panel (TEKNIK/OZET) icin: _SADE'de olmayan saglik kodlari -> (sade cumle, Senden | None). Telegram'a gitmeyen (_SUSTUR) kodlar da
# panelde adiyla gorunur. Kod/ad kullaniciya SIZMAZ; bilinmeyen kod -> SAGLIK_BILINMEYEN.
SAGLIK_BILINMEYEN = "Bir sistem kontrolü uyarı veriyor (kod gösterilmez)"
_SAGLIK_EK: dict[str, tuple[str, str | None]] = {
    # sunucu kaynaklari
    "disk_unknown": ("Disk doluluğu okunamıyor", None), "memory_low": ("Sunucuda bellek azaldı", None),
    "memory_unknown": ("Bellek durumu okunamıyor", None), "swap_high": ("Sunucu yavaşlıyor (takas belleği yüksek)", None),
    "swap_unknown": ("Takas belleği durumu okunamıyor", None), "no_backup": ("Henüz yedek alınmamış", None),
    "clock_skew": ("Sunucu saati ile kayıt zamanları uyuşmuyor", None),
    "veto_missing": ("Yapay zekâ filtresi dosyası yok", None), "veto_stale": ("Yapay zekâ filtresi güncel değil", None),
    "veto_unknown": ("Yapay zekâ filtresi durumu okunamıyor", None),
    "budget_warn": ("Yapay zekâ bütçesi azaldı", None), "budget_unknown": ("Yapay zekâ bütçesi okunamıyor", None),
    "internal_error": ("Sağlık kontrolü kendi içinde hata verdi", None), "missing_check": ("Bir sağlık kontrolü çalışmadı", None),
    # bot / motor
    "api_unreachable": ("Bot yanıt vermiyor", None), "api_unknown": ("Bot durumu doğrulanamıyor", None),
    "loop_unknown": ("Bot döngüsü doğrulanamıyor", None),
    "container_not_running": ("Bot çalışmıyor", None), "container_restarted": ("Bot yeniden başladı", None),
    "container_unknown": ("Bot çalışma durumu okunamıyor", None), "oom_killed": ("Bot bellek yetmediği için kapandı", None),
    "restart_loop": ("Bot sık sık yeniden başlıyor", None), "engine_gate_closed": ("Yeni işlem kapısı kapalı", None),
    "engine_kill": ("Acil durdurma anahtarı açık; yeni işlem açılmıyor", "İstemeden açıldıysa bana haber ver."),
    "gate_unknown": ("Yeni işlem kapısı durumu okunamıyor", None), "no_active_params": ("Bot ayarları (aktif parametreler) bulunamadı", None),
    "naked_unknown": ("Stop emirleri doğrulanamıyor", None),
    # borsa ve piyasa verisi
    "exchange_unknown": ("Borsa bağlantısı doğrulanamıyor", None), "exchange_ban_file_corrupt": ("Borsa engel kaydı bozuk", None),
    "feed_status_missing": ("Fiyat akışı durumu yok", None), "feed_status_stale": ("Fiyat akışı durmuş görünüyor", None),
    "feed_status_unknown": ("Fiyat akışı durumu okunamıyor", None), "market_bars_stale": ("Piyasa verisi güncel değil", None),
    "market_db_missing": ("Piyasa veri dosyası yok", None), "market_db_unreadable": ("Piyasa veri dosyası okunamıyor", None),
    "candle_unknown": ("Piyasa mumları doğrulanamıyor", None), "pairs_unknown": ("İşlem çiftleri doğrulanamıyor", None),
    "rules_incomplete": ("Bazı paritelerin borsa kuralı eksik", None), "rules_missing_increase": ("Borsa kuralı eksik parite sayısı arttı", None),
    "rules_stale": ("Borsa kuralları eski", None), "rules_unknown": ("Borsa kuralları okunamıyor", None),
    "rules_age_unknown": ("Borsa kuralı yaşı okunamıyor", None), "rules_missing_unknown": ("Borsa kuralı eksikliği okunamıyor", None),
    # kayit defteri
    "ledger_age_unknown": ("Kayıt defteri son yazım zamanı okunamıyor", None),
    "ledger_errors": ("Kayıt defterinde yazma hataları var", None), "orphan_decisions": ("Yeniden başlatma sırasında yarım kalan giriş kararları var; işlemleri etkilemez", None),
    "schema": ("Kayıt defteri şeması beklenenden farklı", "Bana haber ver."),
    "spool_corrupt": ("Deftere yazılamayan bozuk kayıt var", None), "spool_pending": ("Deftere yazılmayı bekleyen kayıt birikti", None),
    "spool_corrupt_unreadable": ("Bozuk kayıt dosyası okunamıyor", None),
    "unledgered_trades": ("Deftere işlenmemiş işlem var", "Bana haber ver."),
    "pause_audit": ("Duraklatma kaydı tutarsız", None), "pause_hold_lost": ("Duraklatma kaydı kaybolmuş", None),
    "pause_hold_unaudited": ("Duraklatma kaydı doğrulanamadı", None), "pause_audit_unreadable": ("Duraklatma kaydı okunamıyor", None),
    "pause_unknown": ("Duraklatma durumu okunamıyor", None),
    # risk, hesap, canli
    "ladder_missing": ("Risk kademesi bilgisi yok", None), "ladder_invalid": ("Risk kademesi bilgisi geçersiz", None),
    "capital_missing": ("Sermaye bilgisi okunamıyor", None), "equity_unreadable": ("Kasa bilgisi okunamıyor", None),
    "capital_latch": ("Ana para kilidi: kasa ana paranın %15 altına indi", "Yeni girişler kapalı; açmak için /devam yaz."),
    "capital_floor": ("Sermaye koruma alt sınırına yaklaşıldı", None), "drawdown_review": ("Zirveden düşüş incelemesi gerekiyor", None),
    "account_mode_unverified": ("Hesap ayarı doğrulanamadı, bir giriş atlandı", None),
    "account_mode_unknown": ("Hesap ayarı bilgisi okunamıyor", None),
    "live_paths_mismatch": ("Canlı bot ayar yolları tutarsız", "Kurulumun yeniden çalıştırılması gerekiyor; bana haber ver."),
    # yapay zeka / egitim / davranis
    "ml_shadow_down": ("Gölgedeki model çalışmıyor", None), "ml_expiring_7d": ("Modelin süresi 7 gün içinde doluyor", None),
    "ml_expiring_3d": ("Modelin süresi 3 gün içinde doluyor", None),
    "ml_restart_needed": ("Yeni model hazır ama devrede değil", None),
    "ml_stale_data": ("Yeni model eski veriyle üretilmiş", None), "ml_file_invalid": ("Model dosyası okunamıyor", None),
    "ml_score_errors": ("Model bazı fırsatları puanlayamıyor", None), "ml_status_unreadable": ("Model durumu okunamıyor", None),
    "drift_alert": ("Bot beklenenden farklı davranıyor", None), "drift_missing": ("Davranış izleyicisi çalışmıyor", None),
    "drift_stale": ("Davranış izleyicisi çalışmıyor", None), "drift_unreadable": ("Davranış izleyicisi çalışmıyor", None),
}
_SAGLIK_EK_AD: dict[str, str] = {   # kod taninmazsa kontrol adinin (":bot" oncesi) genel cumlesi
    "disk_free": "Sunucuda boş disk alanı azaldı", "memory": "Sunucuda bellek azaldı", "swap": "Sunucu yavaşlıyor (takas belleği yüksek)",
    "api_reachable": "Bot yanıt vermiyor", "bot_loop_age": "Bot döngüsü durmuş görünüyor", "ledger_write_age": "Kayıt defterine uzun süredir yazılmadı",
    "ledger_gate": "Kayıt sistemi giriş kapısı kapalı", "spool_corrupt": "Deftere yazılamayan bozuk kayıt var",
    "rules_coverage": "Borsa kuralları eksik", "rules_age": "Borsa kuralları eski", "rules_missing": "Bazı paritelerin borsa kuralı eksik",
    "ml_package": "Yapay zekâ modeli sorunlu", "drift_monitor": "Bot beklenenden farklı davranıyor",
    "account_mode": "Hesap ayarı bilgisi sorunlu", "exchange_reachable": "Borsaya ulaşılamıyor", "pause_audit": "Duraklatma kaydı tutarsız",
    "risk_ladder": "Risk kademesi sorunlu", "budget_status": "Yapay zekâ bütçesi sorunlu", "live_paths": "Canlı bot ayar yolları tutarsız",
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
    "ml_shadow_down", "ml_expiring_7d", "ml_expiring_3d", "ml_restart_needed", "ml_stale_data", "ml_file_invalid",
    "ml_score_errors", "drift_missing", "drift_stale", "drift_unreadable", "drift_monitor", "drift_unknown",
    "heartbeat_send_failed", "pa_proposer_stale", "pa_proposer_missing", "tutarlilik_sapma",
    "state_reset", "rules_age", "rules_coverage", "rules_missing", "swap", "memory", "ledger_write_age", "ledger_gate",
    "pause_audit", "risk_ladder", "exchange_ban_file_corrupt", "account_mode_unverified", "account_mode_unknown",
    "live_paths_mismatch", "spool_corrupt", "budget_status", "multiple"})
_BOT_DURDU = frozenset({"api_unreachable", "api_reachable", "bot_loop_age", "engine_retry_exhausted"})


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
    bot = code in _BOT_DURDU or ad in _BOT_DURDU or ad == "api_reachable"
    ok = lvl in ("OK", "INFO")
    if code in _SUSTUR or ad in _SUSTUR:
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
    govde = str(getattr(alert, "body", "") or "")
    if code == "open_price_stale" and "için fiyat gelmiyor" in govde:
        yap = govde[:200]                      # '<COIN> için fiyat gelmiyor; açık pozisyonun stopu fiyat gelince işler'
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


# ----------------------------------------------------------------------------- ders / onay
def _ders_ayrinti(title: str, body: str) -> tuple[str, str, str, str]:
    """Bildirim govdesinden (param, eski, yeni, kapsam)."""
    m = re.match(r"\s*(\w+) (\S+) -> (\S+)", body or "")
    k = re.search(r"Kapsam: ([A-Za-z0-9+@]+)", body or "")
    param, eski, yeni = (m.group(1), m.group(2), m.group(3).rstrip(":")) if m else ("", "", "")
    return param, eski, yeni, (k.group(1) if k else "")


def _ders_ne(param: str, eski: str, yeni: str) -> str:
    if not param:
        return "bir ayar"
    return f"{PARAM_AD.get(param, temizle(param))} {eski} → {yeni}".strip()


def _kapsam_oku(kapsam: str) -> str:
    return " + ".join(kol_adi(x) for x in kapsam.split("+") if x) if kapsam else ""


def ders_mesaji(level: str, code: str, title: str = "", body: str = "") -> tuple[str, str] | None:
    """Ders bildirimi -> (metin, tekrar anahtari) | None (susar). Uygulandi ve geri alindi kullaniciya gider (ders artik onaysiz
    uygulaniyor); onay-zaman-asimi/teknik hatalar susar; fren eski tek satir."""
    code = str(code)
    param, eski, yeni, kapsam = _ders_ayrinti(title, body)
    kol = _kapsam_oku(kapsam)
    if code == "applied":
        t = _bagla([f"Ders uygulandı: {_ders_ne(param, eski, yeni)}" + (f" · {kol}" if kol else "")])
        return t, f"ders|applied|{param}|{kapsam}"
    if code == "rolled_back":
        if param:
            t = _bagla([f"Ders geri alındı: {_ders_ne(param, eski, yeni)}" + (f" · {kol}" if kol else "") + " (sonuç kötüleşti)"])
        else:
            t = _bagla(["⚠️ Son ayar değişikliği geri alındı", "Bot önceki güvenli ayarla devam ediyor."])
        return t, f"ders|rolled_back|{param}|{kapsam}"
    if code == "brake":
        return _bagla(["⚠️ Ders freni devrede", "Bot önceki güvenli ayarla devam ediyor; yeni ders uygulanmıyor."]), "ders|brake"
    return None


PARAM_AD = {"rr_min": "en düşük kazanç/risk oranı", "range_width_atr": "aralık genişliği sınırı",
            "vol_ratio_max": "en yüksek oynaklık oranı", "edge_zone_atr": "kenar bölgesi genişliği",
            "pullback_ema": "geri çekilme ortalaması", "stop_buffer_atr": "stop payı", "trail_atr": "iz sürme mesafesi",
            "range_target_frac": "aralık hedef oranı", "trigger_tf": "tetik zaman dilimi"}


def onay_istegi(param: str, eski: Any, yeni: Any, neden: str, son: str) -> str:
    ad = PARAM_AD.get(param, temizle(param))
    return _bagla([f"🗳 Karar gerekiyor: {ad}", f"{eski} → {yeni}", f"Neden: {temizle(neden)[:140]}", f"Son geçerlilik: {son}"],
                  4)


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
