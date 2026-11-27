"""Telegram ML1 metinleri (gunluk ozet, haftalik ozet, /ml1) ve sablon bicim taramasi; sayilar panodaki ML1 sekmesiyle AYNI."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from ml1_gorunum_destek import ml1_defter, ogrenme_defteri
from panel_support import NOW
from trader_core import ml1_gorunum as MG
from trader_core import panel_pano as PP
from trader_core import telegram as T
from trader_core import tg_sade as TS

UTC = timezone.utc
PAZAR = datetime(2026, 11, 22, 18, 0, tzinfo=UTC)
DAY = "2026-11-16"


@pytest.fixture()
def cfg(tmp_path):
    ml1_defter(str(tmp_path / "l.sqlite"))
    cd = tmp_path / "config"
    cd.mkdir()
    (cd / "engine.base.json").write_text(json.dumps({"wallet_start": 1000.0}))
    (cd / "engine.paper.json").write_text(json.dumps({"ml1": {"aktif": True}}))
    (tmp_path / "status.json").write_text(json.dumps({
        "mode": "paper", "equity": 915.5, "day_start_equity": 920.0, "entries_open": True, "unrealized_pnl_usd": 3.38,
        "open_positions": [{"pair": "ADA/USDT", "side": "long"}] * 5, "loop_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    return T.TelegramConfig("1:t", 5, str(tmp_path / "tg"), "", str(tmp_path / "status.json"), ledger_path=str(tmp_path / "l.sqlite"),
                            config_dir=str(cd))


def _pano_ml1(cfg):
    from panel_support import Env
    ctx = PP.Ctx(cfg.ledger_path, "learner")
    return PP.ml1_view(ctx, NOW, aktif=True)


def test_gunluk_ozet_haftalik_ve_ml1_sayilari_panodakiyle_ayni(cfg):
    m = _pano_ml1(cfg)
    e = m["eleme"]
    gun = T.build_report(cfg, NOW, DAY, {})
    assert f"ML1 bugün: {e['bugun']['puanlanan']} aday puanladı, {e['bugun']['islem']}{TS.iyelik_belirtme(e['bugun']['islem'])} işleme çevirdi" in gun
    assert "Kasa 915,50 $ · toplam −84,50 $" in gun and "Açık: 5 işlem · anlık +3,38 $" in gun
    ml = T.ml1_metni(cfg, NOW)
    assert f"Bugün: {e['bugun']['puanlanan']} aday, {e['bugun']['gecen']} geçti, {e['bugun']['islem']} işlem" in ml
    assert f"7 gün: {e['7g']['puanlanan']} aday, {e['7g']['gecen']} geçti, {e['7g']['islem']} işlem" in ml
    assert MG.durum_satiri(m) in ml and MG.tf_satiri(m) in ml and "ML1 · eşik 0,60" in ml and len(ml.splitlines()) == 6
    assert "Sınav" not in ml and "15" not in ml.replace("0,60", "")
    hf = T.haftalik_metni(cfg, NOW)                                              # ayni defter, ayni `now`
    assert f"ML1: {e['7g']['puanlanan']} aday puanladı" in hf and f"{e['7g']['islem']}{TS.iyelik_belirtme(e['7g']['islem'])} işleme çevirdi" in hf


def test_haftalik_ozet_ml1_satirlari_kapanan_yokken_de_yazilir(cfg, tmp_path):
    hf = T.haftalik_metni(cfg, datetime(2026, 12, 20, 18, 0, tzinfo=UTC))        # bu hafta kapanan yok, ML1 yok
    assert "Bu hafta kapanan işlem yok." in hf and "ML1: puanlanacak aday çıkmadı." in hf and "ML1 süzme aşamasında: " in hf and "Kapanan işlem: 1s " in hf and "Sınav" not in hf


def test_ml1_kapaliysa_tek_satir_ve_defter_yoksa_okunamadi(cfg, tmp_path):
    (tmp_path / "config" / "engine.paper.json").write_text(json.dumps({}))
    assert "ML1 kapalı." in T.build_report(cfg, NOW, DAY, {}) and "ML1 (kapalı)" in T.ml1_metni(cfg, NOW)
    cfg.ledger_path = str(tmp_path / "yok.sqlite")
    with pytest.raises(T.SectionError):
        T.ml1_metni(cfg, NOW)


def test_telegram_sablonlari_bicim_taramasi(cfg, tmp_path):
    """B.1'deki her sablon: kontrol() bos (onek, satir <= 6 / ozet <= 10, yasak iz yok, en cok bir emoji ilk satirda, izinli kume)."""
    metinler = [
        (TS.islem_acildi("Trend geri çekilmesi", "SOL/USDT", "long", 142.3, 250, 139.8, zd="4h", puan=0.63, risk=9), 6),
        (TS.islemler_acildi([("T1", "SOL/USDT", "long", 1.0, 250, 0.9, "4h", 0.63, 9)] * 7), 6),
        (TS.islem_kapandi("x", "SOL/USDT", "long", 9.6, 300, "target", r=1.07, zd="4h", sure="6s 20dk"), 6),
        (TS.islem_kapandi("x", "ETH/USDT", "short", -4.0, 300, "force_exit", setup="DL1@1h", zd="1h", sure="2g 3s", kritik=True), 6),
        (TS.saatlik_ozet(4, 3, 5.2), 6), (TS.limit_uyari(59, 73), 6), (TS.limit_doldu(73, 73), 6),
        (T.build_report(cfg, NOW, DAY, {}), 10), (T.haftalik_metni(cfg, PAZAR), 10), (T.ml1_metni(cfg, NOW), 6),
        (TS.sembol_disi("SOL/USDT", False), 6), (TS.sembol_disi("SOL/USDT", True), 6), (TS.sembol_geri("SOL/USDT"), 6),
        (TS.bot_duzeldi(), 6), (TS.birim_metni("trader-feed.service"), 6), (TS.birim_metni("trader-backup.service"), 6),
        (TS.islem_kontrolu({"sorunlar": ["SOL: panodaki K/Z ile defter 0,40 $ farklı", "ETH: kapanış mesajı gitmemiş"]}), 4),
        (TS.etiketle(T.yardim_metni(True)), 6), (TS.etiketle(T.KALDIRILDI_METNI), 6), (TS.etiketle(T.BILINMEYEN_METNI), 6),
    ]
    for kod in TS._SADE:
        metinler.append((TS.saglik_mesaji(type("A", (), {"code": kod, "fingerprint": f"x|{kod}", "level": "CRIT", "title": "t"})())[1], 6))
    for m, mx in metinler:
        assert m is not None and TS.kontrol(m, mx) == [], (m, TS.kontrol(m, mx))
        assert "UTC" not in m and "ders" not in m.lower() and "karantina" not in m.lower()
    ozet = T.build_report(cfg, NOW, DAY, {})
    assert len(ozet.splitlines()) <= 10 and ozet.splitlines()[0].startswith("[ML] 🌙 Günlük özet")


def test_kontrol_emoji_kurallari():
    assert TS.kontrol("[ML] 🟩 a\nb") == []
    assert "emoji" in TS.kontrol("[ML] 🟩 a\n🔴 b") and "emoji" in TS.kontrol("[ML] a\n🟩 b")          # ilk satir disinda / birden cok
    assert "emoji" in TS.kontrol("[ML] 🛑 a") and "emoji" in TS.kontrol("[ML] ❌ a") and "emoji" in TS.kontrol("[ML] ℹ️ a")  # izinli kume disi
    assert TS.kontrol("[ML] ⚠️ a") == [] and TS.kontrol("[ML] ✅ Düzeldi: x.") == []


def test_health_mesaji_ml1_paket_yok_ve_eski_ml_kodlari_silindi():
    assert "ml_expired" not in TS._SADE and "ml_expiring_1d" not in TS._SADE
    ne, yap, senden, duz = TS._SADE["ml_no_model"]
    assert ne == "ML1 modeli yüklenemedi." and yap.startswith("Kural adayları atlanıyor") and senden is None and duz == "ML1 modeli yüklendi"
    assert TS.duzeldi(duz) == "[ML] ✅ Düzeldi: ML1 modeli yüklendi."


def test_yazim_duzeltmeleri():
    from trader_core import health as H
    assert "/hepsini_kapat" in H._HEALTH_TR["naked_position"][2] and "/kapat " not in H._HEALTH_TR["naked_position"][2]


def test_ogrenme_asamasi_gunluk_haftalik_ve_ml1_komutu_cokmez(tmp_path):
    """26.11: paket yokken (puansiz) ML1 satirlari 'ogrenme asamasinda' der; /ml1 esik yerine asama yazar; sayilar panodaki ile ayni."""
    ogrenme_defteri(str(tmp_path / "l.sqlite"))
    cd = tmp_path / "config"
    cd.mkdir()
    (cd / "engine.base.json").write_text(json.dumps({"wallet_start": 1000.0}))
    (cd / "engine.paper.json").write_text(json.dumps({"ml1": {"aktif": True}}))
    (tmp_path / "status.json").write_text(json.dumps({"mode": "paper", "equity": 915.5, "day_start_equity": 920.0, "entries_open": True,
                                                      "unrealized_pnl_usd": 0.0, "open_positions": [], "loop_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    cfg = T.TelegramConfig("1:t", 5, str(tmp_path / "tg"), "", str(tmp_path / "status.json"), ledger_path=str(tmp_path / "l.sqlite"), config_dir=str(cd))
    gun = T.build_report(cfg, NOW, DAY, {})
    assert "ML1 öğrenme aşamasında (bugün): 4 aday süzülmeden geçti, 3'ünü işleme çevirdi" in gun
    hf = T.haftalik_metni(cfg, NOW)
    assert "ML1 öğrenme aşamasında: 4 aday süzülmeden geçti" in hf
    ml = T.ml1_metni(cfg, NOW)
    assert "eşik öğrenme aşaması" in ml and "okunamadı" not in ml


def test_ml1_metni_durum_dosyasindan_asama_ve_son_deneme(cfg, tmp_path):
    d = tmp_path / "learner" / "ml1_ogren"                                   # cfg.var_dir = <tmp>/tg -> kardes dizin
    d.mkdir(parents=True)
    (d / "durum.json").write_text(json.dumps({"asama": "ogrenme", "kapali_islem": 240, "min_islem": 200,
                                              "kapali_islem_tf": {"1h": 100, "4h": 90, "1d": 50},
                                              "son_sinama": {"gecti": False, "neden": "sinama_auc"}}))
    ml = T.ml1_metni(cfg, NOW)
    assert "ML1 öğrenme aşamasında: 240/200 kapanan işlem; süzme başlamadı (son deneme: geçmedi (sinama_auc))" in ml
    assert "Kapanan işlem: 1s 100 · 4s 90 · 1g 50" in ml
