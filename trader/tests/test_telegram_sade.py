"""Sade Telegram mesajlari: onek, satir siniri, yasak kelimeler, 6 saat tekrar kurali, Duzeldi, "Bot durdu" muafiyeti,
gunluk zarar %80 (gunde bir), islem acildi/kapandi bicimi, susturulan turler."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from test_telegram_report import DAY, NOW, mkledger
from trader_core import health as H
from trader_core import lesson as LS
from trader_core import telegram as T
from trader_core import tg_sade as TS

UTC = timezone.utc
T0 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
YASAK = re.compile(r"_|journalctl|systemctl|sunucu|\.py|\.service|\.timer|\.json|\.sqlite|trader_|\.sh\b", re.I)


class Clk:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t

    def adv(self, **kw):
        self.t += timedelta(**kw)


class Fake:
    def __init__(self):
        self.texts = []

    def __call__(self, url, json=None, timeout=None):
        if url.endswith("sendMessage"):
            self.texts.append(json["text"])
        return 200, {"ok": True, "result": {"message_id": len(self.texts)}}


@pytest.fixture
def rig(tmp_path):
    clk, fake = Clk(), Fake()
    env = {"TELEGRAM_BOT_TOKEN": "1:tok", "TELEGRAM_CHAT_ID": "5", "TELEGRAM_VAR_DIR": str(tmp_path / "tg"),
           "ENGINE_STATUS_PATH": str(tmp_path / "status.json"), "LEDGER_PATH": str(tmp_path / "l.sqlite")}
    n = T.notifier_from_env(env, fake, clk, lambda s: None)
    cfg = T.TelegramConfig.from_env(env)
    return type("R", (), {"clk": clk, "fake": fake, "n": n, "cfg": cfg, "tmp": tmp_path})


def alert(code, level=H.Status.WARN, fp=None, title="t", now=T0):
    return H.Alert(level, code, title, "b", fp or f"x|{code}", now)


def ok_form(text, max_satir=TS.MAX_SATIR):
    assert text.startswith("[ML] "), text
    assert len(text.splitlines()) <= max_satir, text
    assert not YASAK.search(text), text


# ------------------------------------------------------------------ bicim: onek, satir siniri, yasak kelime
def test_tum_bicimleyiciler_kurallara_uyar(tmp_path):
    sp = tmp_path / "status.json"
    sp.write_text(json.dumps({"open_positions": [{"pair": "SOL/USDT", "stop": 1.0}, {"pair": "BTC/USDT", "stop": 2.0}]}))
    metinler = [
        TS.islem_acildi("M1 · 1s", "SOL/USDT", "long", 142.3, 300, 139.1),
        TS.islem_kapandi("T1 · 15dk", "SOL/USDT", "long", 9.6, 300, "target"),
        TS.islem_kapandi("T1 · 15dk", "BTC/USDT", "short", -6.4, 300, "trail_stop"),
        TS.limit_uyari(40.0, 50.0), TS.limit_doldu(50.0, 50.0), TS.bot_durdu(str(sp)), TS.bot_durdu(None),
        TS.bot_duzeldi(), TS.duzeldi("hesap_ayarı yeniden doğru"),
        TS.onay_istegi("rr_min", 1.5, 1.8, "kanıt_sayısı yeterli", "17.11 10:00"),
        TS.ders_mesaji("info", "applied", "t", "rr_min 1.5 -> 1.8 (otomatik). Kapsam: R1+T1. Kanit: x")[0],
        TS.ders_mesaji("warn", "rolled_back", "t", "rr_min 1.8 -> 1.5: kotu Kapsam: M1.")[0],
        TS.ders_mesaji("warn", "brake")[0],
        TS.birim_metni("trader-feed.service"), TS.birim_metni("trader-engine-live.service", str(sp)),
        TS.birim_metni("trader-backup.service"),
        T.build_report(T.TelegramConfig("1:t", 5, str(tmp_path), "", str(sp), ledger_path=str(tmp_path / "l")), NOW, DAY),
    ]
    for m in metinler:
        assert m is not None
        ok_form(m, TS.MAX_SATIR_OZET if "Günlük özet" in m else TS.MAX_SATIR)
    for kod in list(TS._SADE):
        t = TS.saglik_mesaji(alert(kod, H.Status.CRIT, fp=f"x|{kod}"))[1]
        ok_form(t)
        ok_form(TS.saglik_mesaji(alert(kod, H.Status.OK, fp=f"x|{kod}"))[1])


def test_yasak_izler_temizlenir():
    t = TS.temizle("sunucuda trader_engine.service durdu, journalctl bak: rr_min")
    assert not YASAK.search(t) and "durdu" in t


# ------------------------------------------------------------------ islem mesajlari
def test_acildi_tam_iki_satir():
    t = TS.islem_acildi("M1 · 1s", "SOL/USDT", "long", 142.3, 300, 139.1)
    assert t == "[ML] 🟩 M1 · 1s · SOL · long\nGiriş 142,30 · Tutar 300 $ · Stop 139,10"
    assert "USDT" not in t and len(t.splitlines()) == 2
    assert "short" in TS.islem_acildi("M1 · 1s", "BTC/USDT", "short", 60000, 500, 61000)


def test_kapandi_sonuc_neden_ve_ikon():
    k = TS.islem_kapandi("T1 · 15dk", "SOL/USDT", "long", 9.6, 300, "target")
    assert k == "[ML] 🟢 T1 · 15dk · SOL · long kapandı\nSonuç +9,60 $ (+3,2%) · kâr al"
    z = TS.islem_kapandi("T1 · 15dk", "BTC/USDT", "short", -6.4, 300, "stop")
    assert z.splitlines()[0].startswith("[ML] 🔻") and "−6,40 $ (−2,1%) · stop" in z
    assert "🔴" not in z and "🔴" in TS.islem_kapandi("T1 · 15dk", "BTC/USDT", "short", -6.4, 300, "stop", kritik=True)
    assert "süre" in TS.islem_kapandi("T1 · 15dk", "ETH/USDT", "long", 1, 100, "time_stop")
    assert "elle" in TS.islem_kapandi("T1 · 15dk", "ETH/USDT", "long", 1, 100, "manual")


def test_islem_tick_acilan_ve_kapanani_bildirir_tekrar_etmez(rig):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, True), (False, False)])
    (rig.tmp / "tg").mkdir(exist_ok=True)
    (rig.tmp / "tg" / "islem_imleci.json").write_text(json.dumps({"acilan": [], "kapanan": []}))
    n = T.islem_tick(rig.cfg, rig.n, NOW)
    assert n == 3                                          # 2 acilis + 1 kapanis
    assert sum("kapandı" in t for t in rig.fake.texts) == 1
    assert sum(t.splitlines()[1].startswith("Giriş") for t in rig.fake.texts if "kapandı" not in t) == 2
    for t in rig.fake.texts:
        ok_form(t, 2)
    assert T.islem_tick(rig.cfg, rig.n, NOW) == 0          # ayni islem ikinci kez gitmez


def test_islem_tick_ilk_calismada_gecmis_yagmuru_yok(rig):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, True), (False, True)])
    (rig.tmp / "tg").mkdir(exist_ok=True)
    assert T.islem_tick(rig.cfg, rig.n, NOW) == 0 and rig.fake.texts == []


# ------------------------------------------------------------------ 6 saat kurali + Duzeldi
def test_ayni_alarm_6_saatte_bir_ve_duzeldi_bir_kez(rig):
    a = alert("account_mode_drift", fp="account_mode:learner|account_mode_drift")
    assert rig.n.send(a) is True
    assert len(rig.fake.texts) == 1
    ok_form(rig.fake.texts[0])
    assert rig.fake.texts[0].splitlines()[2].startswith("Senden:")
    rig.clk.adv(hours=5, minutes=59)
    rig.n.send(a)
    assert len(rig.fake.texts) == 1                        # 6 saat dolmadi
    rig.clk.adv(minutes=2)
    rig.n.send(a)
    assert len(rig.fake.texts) == 2                        # 6 saat doldu: bir hatirlatma
    duz = alert("account_mode_drift", H.Status.OK, fp="account_mode:learner|account_mode_drift")
    rig.n.send(duz)
    rig.n.send(duz)
    assert len(rig.fake.texts) == 3 and rig.fake.texts[-1].startswith("[ML] ✅ Düzeldi")   # tek Duzeldi


def test_uyarisi_gitmemis_sey_icin_duzeldi_gitmez(rig):
    rig.n.send(alert("account_mode_drift", H.Status.OK, fp="a|account_mode_drift"))
    assert rig.fake.texts == []


def test_ek_uyari_parmak_izi_zaman_damgali_olsa_da_6_saat_kurali(rig):
    for i in range(3):
        rig.n.send(alert("disk_dolu", fp=f"disk|dolu|{rig.clk().isoformat()}", title="Disk dolmak üzere (%85)"))
        rig.clk.adv(hours=1)
    assert len(rig.fake.texts) == 1 and "(%85)" in rig.fake.texts[0]
    rig.n.send(alert("disk_dolu", H.Status.OK, fp=f"disk|dolu|duzeldi|{rig.clk().isoformat()}"))
    assert len(rig.fake.texts) == 2 and "Düzeldi" in rig.fake.texts[1]


# ------------------------------------------------------------------ Bot durdu
def test_bot_durdu_6_saat_kuralindan_muaf_ve_pozisyon_bilgisi_verir(rig):
    (rig.tmp / "status.json").write_text(json.dumps({"open_positions": [{"pair": "SOL/USDT", "stop": 139.1}]}))
    a = alert("api_unreachable", H.Status.CRIT, fp="api_reachable:learner|api_unreachable")
    rig.n.send(a)
    rig.clk.adv(minutes=20)
    rig.n.send(a)
    rig.clk.adv(minutes=20)
    rig.n.send(a)
    assert len(rig.fake.texts) == 3                        # her seferinde gider (6 saat kurali yok)
    t = rig.fake.texts[0]
    assert t.startswith("[ML] 🔴 Bot durdu") and "Açık pozisyon: 1" in t and "stoplar izlenmiyor" in t and "yerinde" not in t
    ok_form(t)
    rig.n.send(alert("api_unreachable", H.Status.OK, fp="api_reachable:learner|api_unreachable"))
    rig.n.send(alert("api_unreachable", H.Status.OK, fp="api_reachable:learner|api_unreachable"))
    assert rig.fake.texts[3] == "[ML] ✅ Düzeldi: bot yeniden çalışıyor." and len(rig.fake.texts) == 4


def test_bot_durdu_durum_dosyasi_yoksa_stopu_kontrol_ettirir(rig):
    t = TS.bot_durdu(None)
    assert "bilgisi okunamadı" in t
    assert "Açık pozisyon yok" in TS.bot_durdu(_bos_durum(rig))


def _bos_durum(rig):
    p = rig.tmp / "bos.json"
    p.write_text(json.dumps({"open_positions": []}))
    return str(p)


def test_motor_deneme_tukendi_ve_birim_basarisiz_bot_durdu_olur(rig):
    a = H.Alert(H.Status.CRIT, "engine_retry_exhausted", "x", "y", "engine-retry-exhausted:learner", T0)
    rig.n.send(a)
    assert rig.fake.texts[0].startswith("[ML] 🔴 Bot durdu")
    assert "feed" not in TS.birim_metni("trader-feed.service").lower()
    assert TS.birim_metni("trader-telegram.service") is None


# ------------------------------------------------------------------ gunluk zarar %80
def _ayar_orani():
    """Gercek kagit ayari (config/engine.paper.json risk.daily_max_loss); sabit yazilmaz."""
    from pathlib import Path
    cfg = Path(__file__).resolve().parent.parent / "config" / "engine.paper.json"
    return float(json.loads(cfg.read_text(encoding="utf-8"))["risk"]["daily_max_loss"])


def _durum(rig, eq, dse=1000.0):
    (rig.tmp / "status.json").write_text(json.dumps({"equity": eq, "day_start_equity": dse}))


def test_zarar_80_yuzde_gunde_bir_kez(rig):
    lim = _ayar_orani() * 1000.0
    _durum(rig, 1000.0 - 0.6 * lim)                        # %60: sessiz
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 0
    _durum(rig, 1000.0 - 0.8 * lim)                        # %80
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 1
    assert T.zarar_tick(rig.cfg, rig.n, T0 + timedelta(hours=1)) == 0       # ayni gun ikinci uyari yok
    assert "%80" in rig.fake.texts[0] and "Günlük zarar sınırına yaklaşıldı" in rig.fake.texts[0]
    ok_form(rig.fake.texts[0])
    assert T.zarar_tick(rig.cfg, rig.n, T0 + timedelta(days=1)) == 1        # ertesi gun yine
    assert len(rig.fake.texts) == 2


def test_limit_doldu_acik_pozisyonlarin_akibetini_soyler(rig):
    _durum(rig, 1000.0 - 1.1 * _ayar_orani() * 1000.0)
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 1
    t = rig.fake.texts[0]
    assert "limiti doldu" in t and "stoplarıyla yönetilmeye devam" in t and "yeni işlem açılmaz" in t
    ok_form(t)
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 0


# ------------------------------------------------------------------ susturulan turler
@pytest.mark.parametrize("kod", ["pa_proposer_stale", "tutarlilik_sapma", "heartbeat_send_failed",
                                 "ml_expiring_7d", "ml_expiring_3d", "ml_shadow_down", "drift_stale", "bilinmeyen_kod"])
def test_teknik_uyarilar_susar(rig, kod):
    assert rig.n.send(alert(kod)) is True
    assert rig.n.send(alert(kod, H.Status.OK)) is True
    assert rig.fake.texts == []


def test_ders_uygulandi_ve_geri_alindi_telegrama_gitmez(rig):
    def nt(code, body):
        return LS.LessonNotice("info" if code == "applied" else "warn", code, "t", body, f"{code}|d|1", T0)
    ap = nt("applied", "rr_min 1.5 -> 1.8 (otomatik). Kapsam: R1+T1. Kanit: n=5. Geri alma: dugme")
    rb = nt("rolled_back", "rr_min 1.8 -> 1.5: ders etkisi kotu. Kapsam: M1@1h.")
    for x in (ap, ap, rb, rb):
        assert rig.n.notify(x) is True
    assert rig.fake.texts == []                           # ders mesajlari artik yalniz gunluge gider
    # metin uretimi (gunluk/panel icin) degismedi
    assert TS.ders_mesaji("info", "applied", "t", ap.body)[0] == "[ML] Ders uygulandı: en düşük kazanç/risk oranı 1.5 → 1.8 · Yatay piyasa kenarı + Trend geri çekilmesi"


def test_ders_teknik_hata_ve_zaman_asimi_susar(rig):
    for lvl, code in (("info", "needs_user_expired"), ("warn", "run_failed"), ("warn", "llm_error")):
        assert rig.n.notify(LS.LessonNotice(lvl, code, "t", "b", f"{code}|d|1", T0)) is True
    assert rig.fake.texts == []


def test_kol_adi_bicimi():
    assert TS.kol_adi("M1@1h") == "Yapay zekâ adayı · 1 saat" and TS.kol_adi("T1@15m") == "Trend geri çekilmesi · 15 dakika"
    assert "Kadro" not in TS.KURULUM_AD.get("C1", "") and "C1" not in TS.KURULUM_AD and TS.kol_adi("R1@1d") == "Yatay piyasa kenarı · 1 gün"
    assert TS.kol_adi("R1@4h") == "Yatay piyasa kenarı · 4 saat"
    assert TS.kol_adi("M1", "1h") == "Yapay zekâ adayı · 1 saat" and TS.kol_adi("M1") == "Yapay zekâ adayı"
    assert TS.kol_adi("XY9@1h") == "XY9 · 1 saat"          # bilinmeyen kod ham kalir (uydurma ad yok)


def test_islem_mesajinda_kol_adi_ledgerdan_gelir(rig):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, True)])
    (rig.tmp / "tg").mkdir(exist_ok=True)
    (rig.tmp / "tg" / "islem_imleci.json").write_text(json.dumps({"acilan": [], "kapanan": []}))
    T.islem_tick(rig.cfg, rig.n, NOW)
    assert rig.fake.texts[0].splitlines()[0] == "[ML] 🟩 Yatay piyasa kenarı · 1 saat · ETH · long"
    assert "öğrenen" not in "".join(rig.fake.texts)


def test_limit_orani_ayardan_okunur(tmp_path, monkeypatch):
    from trader_core import risk as R
    cd = tmp_path / "config"
    cd.mkdir()
    (cd / "engine.paper.json").write_text(json.dumps({"risk": {"daily_max_loss": 0.04}}))
    assert TS.limit_orani(cd, "paper") == 0.04
    # 23.11 kullanici karari: canli = kagit (canli engine.live.json'daki risk.daily_max_loss'u okur; dosya yoksa kilitli)
    assert TS.limit_orani(cd, "live") == R.LOCKED_CFG.daily_max_loss
    (cd / "engine.live.json").write_text(json.dumps({"risk": {"daily_max_loss": 0.08}}))
    assert TS.limit_orani(cd, "live") == 0.08
    assert TS.limit_orani(tmp_path / "yok", "paper") == R.LOCKED_CFG.daily_max_loss
    (cd / "engine.paper.json").write_text(json.dumps({"risk": {"daily_max_loss": R.PAPER_LIMITS["daily_max_loss"]}}))
    assert TS.limit_orani(cd, "paper") == R.PAPER_LIMITS["daily_max_loss"]       # paper ust siniri gecerli
    (cd / "engine.paper.json").write_text(json.dumps({"risk": {"daily_max_loss": R.PAPER_LIMITS["daily_max_loss"] + 0.01}}))
    assert TS.limit_orani(cd, "paper") == R.LOCKED_CFG.daily_max_loss          # siniri asan deger -> kilitli
    assert TS.limit_orani(None, "paper") == _ayar_orani()                      # varsayilan: gercek ayar dosyasi


def test_kagitta_yuzde_80_uyarisi_ayardaki_limite_gore(rig, monkeypatch):
    from trader_core import risk as R
    cd = rig.tmp / "cfg"
    cd.mkdir()
    (cd / "engine.paper.json").write_text(json.dumps({"risk": {"daily_max_loss": 0.08}}))
    rig.cfg.config_dir = str(cd)
    (rig.tmp / "status.json").write_text(json.dumps({"mode": "paper", "equity": 940.0, "day_start_equity": 1000.0}))
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 0                       # 60 $ < 64 $
    (rig.tmp / "status.json").write_text(json.dumps({"mode": "paper", "equity": 936.0, "day_start_equity": 1000.0}))
    assert T.zarar_tick(rig.cfg, rig.n, T0) == 1 and "sınır 80,00 $" in rig.fake.texts[0]
    rep_cfg = rig.cfg
    (rig.tmp / "status.json").write_text(json.dumps({"mode": "paper", "equity": 950.0, "day_start_equity": 1000.0,
                                                     "loop_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    assert "Günlük zarar sınırı: 50,00 $ / 80,00 $ kullanıldı" in T.build_report(rep_cfg, NOW, DAY)


def test_onay_istegi_karar_mesaji_kisa_ve_sade(rig):
    req = LS.ApprovalRequest(request_id="lr-2026-11-16-1", proposal_id=3, base_version_id=1, param="rr_min", from_value=1.5,
                             to_value=1.8, scope="s", reason_code="rc", shadow_period=False, provisional=False, title="T",
                             body="kanıt_sayısı yeterli, kâr artıyor", evidence={"n": 1}, created_at=T0,
                             expires_at=T0 + timedelta(hours=24))
    assert rig.n.request_approval(req) is True
    t = rig.fake.texts[0]
    assert t.startswith("[ML] 🗳 Karar gerekiyor: en düşük kazanç/risk oranı")
    assert len(t.splitlines()) <= 6 and "rr_min" not in t and "kanıt sayısı" in t
    assert "/onayla lr-2026-11-16-1" in t


def test_gunluk_ozet_12_satiri_asmaz_ve_haftalik_yalniz_pazar(rig):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, True), (False, True)] * 4)
    (rig.tmp / "tg").mkdir(exist_ok=True)
    pos = [{"pair": f"P{i}/USDT", "side": "long", "stop": 1.0} for i in range(9)]
    (rig.tmp / "status.json").write_text(json.dumps({
        "mode": "live", "equity": 900.0, "day_start_equity": 1000.0, "entries_open": False, "open_positions": pos,
        "loop_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}))
    rep = T.build_report(rig.cfg, NOW, DAY, {})
    ok_form(rep, TS.MAX_SATIR_OZET)
    assert not T.haftalik_gonder(rig.cfg, rig.n, NOW)                         # 16 Kasim 2026 pazartesi
    pazar = datetime(2026, 11, 22, 18, 0, tzinfo=UTC)
    assert T.haftalik_gonder(rig.cfg, rig.n, pazar) is False and rig.fake.texts == []   # haftalik ozet Telegram'a gitmez (varsayilan)
    T.HAFTALIK_TELEGRAM = True                                               # metin hala uretilebilir (panel/rapor icin)
    try:
        assert T.haftalik_gonder(rig.cfg, rig.n, pazar) is True
        assert T.haftalik_gonder(rig.cfg, rig.n, pazar) is False              # haftada bir
    finally:
        T.HAFTALIK_TELEGRAM = False
    ok_form(rig.fake.texts[-1])
    assert rig.fake.texts[-1].startswith("[ML] 🗓 Haftalık özet")


# ------------------------------------------------------------------ saatlik sinir, gruplama, gunluk ozet satirlari
def _ac_kapa_ledger(rig, n):
    mkledger(rig.tmp / "l.sqlite", "learner", [(True, i % 2 == 0) for i in range(n)])
    (rig.tmp / "tg").mkdir(exist_ok=True)
    (rig.tmp / "tg" / "islem_imleci.json").write_text(json.dumps({"acilan": [], "kapanan": []}))


def test_islemler_saatte_en_cok_6_mesaj_fazlasi_saat_sonunda_ozet(rig):
    _ac_kapa_ledger(rig, 8)                                 # 8 acilis (farkli dakikalar) + 4 kapanis = 12 olay
    now = datetime(2026, 11, 16, 18, 5, tzinfo=UTC)
    T.islem_tick(rig.cfg, rig.n, now)
    assert len(rig.fake.texts) == 6
    sessiz = [c for c in rig.fake.texts]
    assert all("Son 1 saatte" not in t for t in sessiz)
    T.islem_tick(rig.cfg, rig.n, now + timedelta(minutes=10))
    assert len(rig.fake.texts) == 6                         # ayni saat: sinir
    T.islem_tick(rig.cfg, rig.n, now + timedelta(hours=1))
    assert len(rig.fake.texts) == 7
    o = rig.fake.texts[-1]
    assert o.startswith("[ML] Son 1 saatte 6 işlem daha: ") and "açıldı" in o and "kapandı" in o and "net " in o
    ok_form(o)


def test_islem_mesajlari_sessiz_gider(rig):
    _ac_kapa_ledger(rig, 1)
    sessiz = []
    orig = rig.n.client.send_message
    rig.n.client.send_message = lambda c, t, disable_notification=False, **k: (sessiz.append(disable_notification), orig(c, t, disable_notification=disable_notification, **k))[1]
    T.islem_tick(rig.cfg, rig.n, NOW)
    assert sessiz and all(sessiz)


def test_ayni_dakikadaki_acilislar_tek_mesaj():
    t = TS.islemler_acildi([("M1 · 1s", "SOL/USDT", "long", 142.3, 300, 139.1), ("T1 · 15dk", "BTC/USDT", "short", 60000, 200, 61000)])
    assert t.splitlines()[0] == "[ML] 🟩 2 işlem açıldı" and len(t.splitlines()) == 3
    assert "M1 · 1s · SOL · long" in t and "T1 · 15dk · BTC · short" in t
    ok_form(t)
    buyuk = TS.islemler_acildi([("M1 · 1s", "SOL/USDT", "long", 1, 1, 1)] * 9)
    ok_form(buyuk)
    assert "ve 5 işlem daha" in buyuk


def test_gunluk_ozet_ders_ve_model_satirlari(tmp_path):
    sp = tmp_path / "status.json"
    mkledger(tmp_path / "l.sqlite", "learner", [])
    def yaz(ml):
        sp.write_text(json.dumps({"mode": "paper", "equity": 1000.0, "day_start_equity": 1000.0, "entries_open": True,
                                  "open_positions": [], "loop_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "ml": ml}))
    cfg = T.TelegramConfig("1:t", 5, str(tmp_path), "", str(sp), ledger_path=str(tmp_path / "l.sqlite"))
    yaz({"mode": "active", "state": "ok", "expires_at": "2026-12-30T00:00:00Z"})
    r = T.build_report(cfg, NOW, DAY)
    assert "Dersler: bugün 0 uygulandı, 0 geri alındı · işlemlere etkili" in r and "Model: güncel, işlemlere etkili" in r
    yaz({"mode": "active", "state": "expired", "expires_at": None})
    r = T.build_report(cfg, NOW, DAY)
    assert "Model süresi doldu, kararlar kuralla veriliyor" in r
    ok_form(r, TS.MAX_SATIR_OZET)


def test_ornek_render_acildi_ve_kapandi(rig, capsys):
    _ac_kapa_ledger(rig, 2)
    T.islem_tick(rig.cfg, rig.n, NOW)
    with capsys.disabled():
        print("\nORNEK ACILDI:\n" + next(t for t in rig.fake.texts if "kapandı" not in t))
        print("ORNEK KAPANDI:\n" + next(t for t in rig.fake.texts if "kapandı" in t))
