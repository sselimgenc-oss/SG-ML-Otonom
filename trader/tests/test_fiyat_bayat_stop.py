"""Fiyat gelmeyen acik pozisyon: paper stop davranisi (bosluk), saglik uyarisi, mutabakat 'fiyat bekleniyor', ozet tekrari."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from panel_support import NOW, ROOT
from trader_core import health as H
from trader_core import mutabakat as M
from trader_core import panel_pano as PN
from trader_core import tg_sade as TS
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import CostModel
from trader_engine.types import MinuteBar, OrderRequest, SymbolRules

UTC = timezone.utc
P = "TSLA/USDT"
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
RULES = SymbolRules(pair=P, symbol="TSLAUSDT", tick=0.01, step=0.001, min_qty=0.001, max_qty=1000.0, min_notional=5.0)


def _bar(minute, o, h, l, c):
    return MinuteBar(pair=P, open_ts=T0 + timedelta(minutes=minute), step_s=60, last_o=o, last_h=h, last_l=l, last_c=c,
                     mark_o=o, mark_h=h, mark_l=l, mark_c=c)


def _step(b, bars):
    b.advance(bars, "fills")
    ev = b.poll(T0)
    b.advance(bars, "triggers")
    return ev + b.poll(T0)


def _long_with_stop(stop=98.0):
    b = PaperBroker(PaperConfig(cost=CostModel(), mmr=0.004), lambda p: RULES, lambda p, a, z: [], SimClock(T0), None)
    b.prepare(P, 3)
    b.market_order(OrderRequest(client_id="e1", pair=P, role="entry", order_side="buy", qty=6.369, trigger_price=None,
                                reduce_only=False, leverage=3))
    _step(b, {P: _bar(0, 100.0, 100.0, 100.0, 100.0)})
    assert b.place_stop(OrderRequest(client_id="s1", pair=P, role="stop", order_side="sell", qty=6.369, trigger_price=stop,
                                     reduce_only=True, leverage=None)).status == "accepted"
    return b


def test_piyasa_kapali_bosluk_acilista_stop_acilis_fiyatindan_dolar():
    """(a) Bar gelmedikce stop islenmez (fiyat da oynamaz); yeniden acilista stop'u GEREN bosluk ilk barin ACILISINDAN dolar (stoptan kotu)."""
    b = _long_with_stop(98.0)
    for _ in range(300):                                   # kapali seans: motor adimlari bar tasimaz
        assert b.advance({}, "fills") is None and b.advance({}, "triggers") is None
    assert len(b.positions()) == 1 and b.poll(T0) == []    # stop sessizce dolmadi, kayboldu da degil
    ev = _step(b, {P: _bar(900, 95.0, 96.0, 94.0, 95.5)})   # ertesi gun bosluk: acilis 95 < stop 98
    f = [e.fill for e in ev if e.fill][0]
    assert f.reason == "stop" and f.price < 98.0
    assert f.price == pytest.approx(95.0 * (1 - 0.0005), rel=1e-3) or f.price == pytest.approx(95.0, abs=0.2)
    assert f.price < 98.0 - 1.0                            # stop seviyesinden belirgin kotu (acilis fiyati), stop fiyatindan degil
    assert b.positions() == []


def test_veri_kesintisi_bar_gelince_stop_islenir_dokunus_stop_fiyatindan():
    """(b) Besleme koptu, piyasa isliyordu: stop bar gelene dek beklemede; ilk barda stop dokunulduysa ve acilis stopun USTUNDEyse stop fiyatindan dolar."""
    b = _long_with_stop(98.0)
    for _ in range(30):
        b.advance({}, "fills")
        b.advance({}, "triggers")
    assert len(b.positions()) == 1
    ev = _step(b, {P: _bar(31, 99.0, 99.2, 97.0, 97.5)})   # acilis 99 > stop 98, dip 97: stop dokundu
    f = [e.fill for e in ev if e.fill][0]
    assert f.reason == "stop" and f.price == pytest.approx(98.0 * (1 - 0.0005), rel=1e-3) or abs(f.price - 98.0) < 0.2
    assert b.positions() == []


def test_bar_gelmeyen_adimlar_stop_emrini_silmez_ve_bosluk_sayilir():
    b = _long_with_stop(98.0)
    before = b.counters()["minute_gaps"]
    b.advance({}, "fills")                                  # bos adim: pozisyonlu cift bar yok -> minute_gaps artar
    assert b.counters()["minute_gaps"] == before + 1        # pozisyonlu cift icin bar yok: bosluk sayaci artar; stop yerinde
    assert any(o for o in b._new_orders() if o.role == "stop")
    _step(b, {P: _bar(5, 99.5, 99.6, 99.4, 99.5)})          # stop dokunulmadi
    assert len(b.positions()) == 1 and any(o for o in b._new_orders() if o.role == "stop")


# ------------------------------------------------------------------------------------------------ saglik
def _snap(now, open_pairs, newest):
    return H.HealthSnapshot(
        now=now, timeframe_s=3600,
        api={"learner": H.ApiProbe(ping_ok=True, last_process_at=now, last_candle_open=now, open_pairs=open_pairs)},
        market=H.MarketProbe(feed_status_state="ok", feed_status_at=now, db_state="ok", pairs=tuple(newest), newest_bar_at=newest))


SAAT = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)          # Car 11:00 New York: hisse seansi acik


def test_kripto_fiyat_bayat_uyarir_taze_uyarmaz():
    now = SAAT
    bayat = H._c_open_price(_snap(now, (("SOL/USDT", "kripto"),), {"SOL/USDT": now - timedelta(minutes=11)}), "learner", H.DEFAULT_CFG)
    assert bayat.status is H.Status.WARN and bayat.detail == "SOL için fiyat gelmiyor; açık pozisyonun stopu fiyat gelince işler"
    taze = H._c_open_price(_snap(now, (("SOL/USDT", "kripto"),), {"SOL/USDT": now - timedelta(minutes=2)}), "learner", H.DEFAULT_CFG)
    assert taze.status is H.Status.OK
    yok = H._c_open_price(_snap(now, (("SOL/USDT", "kripto"),), {}), "learner", H.DEFAULT_CFG)
    assert yok.status is H.Status.WARN                      # hic mum yok = bayat


@pytest.mark.parametrize("an,sinif,beklenen", [
    (datetime(2026, 11, 21, 16, 0, tzinfo=UTC), "hisse", H.Status.OK),      # Cumartesi: kapali, uyari yok
    (datetime(2026, 11, 18, 22, 0, tzinfo=UTC), "hisse", H.Status.OK),      # Car 17:00 NY: seans disi
    (datetime(2026, 11, 18, 14, 35, tzinfo=UTC), "hisse", H.Status.OK),     # acilisin 5. dakikasi: sahte uyari yok
    (datetime(2026, 11, 18, 16, 0, tzinfo=UTC), "hisse", H.Status.WARN),    # seans acik, 3 saattir mum yok
    (datetime(2026, 11, 21, 12, 0, tzinfo=UTC), "emtia", H.Status.OK),      # emtia hafta sonu
    (datetime(2026, 11, 18, 16, 0, tzinfo=UTC), "emtia", H.Status.WARN),
])
def test_seans_kapaliyken_uyari_yok(an, sinif, beklenen):
    r = H._c_open_price(_snap(an, (("TSLA/USDT", sinif),), {"TSLA/USDT": an - timedelta(hours=3)}), "learner", H.DEFAULT_CFG)
    assert r.status is beklenen


def test_evaluate_kontrolu_yalniz_sinif_biliniyorsa_uretir():
    now = SAAT
    s = _snap(now, None, {"SOL/USDT": now})
    assert not any(r.name.startswith("acik_pozisyon_fiyat_bayat") for r in H.evaluate(s).results)
    s = _snap(now, (("SOL/USDT", "kripto"),), {"SOL/USDT": now - timedelta(minutes=30)})
    rep = H.evaluate(s)
    assert any(r.name == "acik_pozisyon_fiyat_bayat:learner" and r.status is H.Status.WARN for r in rep.results)


def test_telegram_metni_sade_ve_coin_adli():
    now = SAAT
    r = H._c_open_price(_snap(now, (("SOL/USDT", "kripto"),), {"SOL/USDT": now - timedelta(minutes=30)}), "learner", H.DEFAULT_CFG)
    r = H.CheckResult("acik_pozisyon_fiyat_bayat:learner", r.status, r.code, r.detail, r.value, r.threshold)
    rep = H.HealthReport(now, (r,), H.Status.WARN, True)
    a1, st = H.plan_alerts(rep, None, now)
    a2, st = H.plan_alerts(rep, st, now + timedelta(minutes=5))
    al = [a for a in a1 + a2 if a.fingerprint.startswith("acik_pozisyon_fiyat_bayat")]
    assert len(al) == 1
    tur, metin, _ = TS.saglik_mesaji(al[0])
    assert tur == "alarm" and "SOL için fiyat gelmiyor; açık pozisyonun stopu fiyat gelince işler" in metin
    assert "_" not in metin and not TS.kontrol(metin)


# ------------------------------------------------------------------------------------------------ mutabakat
def test_fiyat_yok_uyusmazlik_sayilmaz_ayri_durum():
    pos = [{"trade_id": i, "side": "long", "entry_price": 100.0, "qty": 2.0, "mark": None} for i in (15, 17)]
    panel = [{"id": i, "simdi": None, "kz": None} for i in (15, 17)]
    k = M.kontrol_acik_kz({"open_positions": pos}, panel)
    assert k["sonuc"] == "geçti" and "anlık fiyat yok" not in k["ayrinti"] and M.FIYAT_BEKLENIYOR in k["ayrinti"]
    assert k["fiyat_bekleniyor"] == [15, 17]
    doc = M.ozet([], [k], [], now=NOW)
    assert doc["uyusmazlik_sayisi"] == 0 and doc["uyusmazliklar"] == [] and doc["fiyat_bekleniyor"] == [15, 17]
    doc = {**doc, "satirlar": [], "kontroller": [k]}
    t = TS.islem_kontrolu_ozet(doc)
    assert "uyuşmazlık 0" in t and "ℹ️ Fiyat bekleniyor (piyasa kapalı/veri yok): #15, #17" in t
    assert "anlık fiyat yok" not in t
    # gercek fark hala uyusmazlik; fiyat bekleyen ayri
    pos2 = pos + [{"trade_id": 7, "side": "long", "entry_price": 100.0, "qty": 2.0, "mark": 101.0}]
    k2 = M.kontrol_acik_kz({"open_positions": pos2}, panel + [{"id": 7, "simdi": 101.0, "kz": 9.0}])
    assert k2["sonuc"] == "kaldı" and "#7" in k2["ayrinti"]


def test_panel_acik_satiri_fiyat_bekleniyor_bayragi():
    class Ctx:
        open = [type("T", (), dict(trade_id=15, pair="AMD/USDT", side="long", entry_price=100.0, qty=1.0, decision_id=None, regime=None,
                                   setup="R1", entry_ts=NOW, planned_stop=95.0, planned_target=110.0, leverage=3))()]
        dec = {}
        kol = staticmethod(lambda t: "kol")
    st = {"open_positions": [{"trade_id": 15, "mark": None, "unrealized_pnl_usd": None, "stop": 95.0}], "equity": 1000.0}
    r = PN.open_view(Ctx, st, NOW)["rows"][0]
    assert r["fiyat_bekleniyor"] is True and r["simdi"] is None and r["kz"] is None
    st["open_positions"][0].update(mark=101.0, unrealized_pnl_usd=1.0)
    assert PN.open_view(Ctx, st, NOW)["rows"][0]["fiyat_bekleniyor"] is False
    js = (ROOT / "src/trader_panel/static/panel.js").read_text(encoding="utf-8")
    assert "fiyat bekleniyor" in js and "r.fiyat_bekleniyor" in js


# ------------------------------------------------------------------------------------------------ ozet tekrari
def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def test_ayni_parmak_izi_yeni_kurulumda_ve_gunluk_uyaride_tekrar_gonderilmez(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    R = _load("mutabakat_run")
    doc = {"uretim": "2026-11-20T11:00:00Z", "islem_sayisi": 24, "acik": 8, "kapanan": 16, "uyusmazlik_sayisi": 1,
           "uyusmazliklar": ["x"], "satirlar": [], "kontroller": [{"ad": "Kasa = başlangıç", "sonuc": "geçti", "ayrinti": ""}]}
    tg, durum = tmp_path / "tg", tmp_path / "durum"
    assert R.kurulum_ozeti(tg, durum, doc, NOW, surum="a") is True
    kayit = json.loads((durum / R.OZET_KAYIT).read_text(encoding="utf-8"))
    assert kayit["surum"] == "a" and kayit["parmak_izi"] == R.parmak_izi(doc)
    assert R.kurulum_ozeti(tg, durum, {**doc, "uretim": "2026-11-20T12:04:00Z"}, NOW, surum="b") is False   # yeni kurulum, ayni sonuc
    assert json.loads((durum / R.OZET_KAYIT).read_text(encoding="utf-8"))["surum"] == "b"
    assert R.telegram_bildir(tg, durum, doc, NOW) is False                                            # gunluk WARN de ayni sonuc: yok
    degisti = {**doc, "uyusmazliklar": ["x", "y"], "uyusmazlik_sayisi": 2}
    assert R.kurulum_ozeti(tg, durum, degisti, NOW, surum="c") is True
    assert R.telegram_bildir(tg, durum, degisti, NOW) is False                                        # degisen sonuc ozetle gitti: ayni mesaj tekrar yok
    assert R.parmak_izi(degisti) != R.parmak_izi(doc)


def test_sorunlar_fiyat_yok_seans_disinda_sorun_degil_seans_icinde_sorun():
    rows = [{"islem_no": 20, "coin": "AMD", "uyusmazlik": []}]
    k = M.kontrol_acik_kz({"open_positions": [{"trade_id": 20, "side": "long", "entry_price": 1.0, "qty": 1.0, "mark": None}]},
                          [{"id": 20, "simdi": None, "kz": None}])
    st = lambda: {"open_positions": [{"trade_id": 20, "pair": "AMD/USDT", "asset_class": "hisse"}]}   # noqa: E731
    acik = datetime(2026, 11, 18, 16, 0, tzinfo=UTC)          # Car 11:00 New York
    assert M.sorunlar(rows, [k], [], st(), datetime(2026, 11, 21, 16, 0, tzinfo=UTC)) == []      # hafta sonu: mesaj yok
    assert M.sorunlar(rows, [k], [], st(), datetime(2026, 11, 18, 22, 0, tzinfo=UTC)) == []      # seans disi: mesaj yok
    s = M.sorunlar(rows, [k], [], st(), acik)
    assert s == ["AMD işleminin güncel fiyatı alınamıyor"]
    t = TS.islem_kontrolu({"sorunlar": s})
    assert t == "[ML] ⚠️ AMD işleminin güncel fiyatı alınamıyor" and "#" not in t
    kasa = {"ad": "Kasa = başlangıç + Σ net K/Z", "sonuc": "kaldı", "ayrinti": "Kasa 1.023,64 $ olmalı, kayıtta 1.020,90 $ · fark 2,74 $"}
    assert M.sorunlar([], [kasa], [], None, acik) == ["Kasa kayıtla tutmuyor: 1.023,64 $ olmalı, kayıtta 1.020,90 $"]


def test_sorunlar_motor_yeni_basladiysa_fiyat_yok_sorun_degil_kripto():
    """Kurulum sonrasi motor yeniden basladi, ilk 1 dk mumu gelmeden mutabakat kostu: kripto (7/24) icin yanlis uyari olmamali."""
    rows = [{"islem_no": 7, "coin": "XRP", "uyusmazlik": []}]
    k = M.kontrol_acik_kz({"open_positions": [{"trade_id": 7, "side": "short", "entry_price": 1.0, "qty": 1.0, "mark": None}]},
                          [{"id": 7, "simdi": None, "kz": None}])
    now = datetime(2026, 11, 20, 14, 6, tzinfo=UTC)
    st = lambda bas: {"started_at": bas, "open_positions": [{"trade_id": 7, "pair": "XRP/USDT", "asset_class": "kripto"}]}   # noqa: E731
    assert M.sorunlar(rows, [k], [], st("2026-11-20T14:05:10Z"), now) == []                         # 1 dk once basladi: mesaj yok
    assert M.sorunlar(rows, [k], [], st("2026-11-20T13:30:00Z"), now) == ["XRP işleminin güncel fiyatı alınamıyor"]   # gercek kesinti


# ------------------------------------------------------------------------------------------------ fiyat bicimi / sessiz mesajlar
@pytest.mark.parametrize("v,beklenen", [(8.87, "8,87"), (2001, "2.001,00"), (1.0, "1,00"), (123.456, "123,46"), (0.1234, "0,1234"),
                                        (0.5, "0,50"), (0.12349, "0,1235"), (0.00001234, "0,000012")])
def test_tek_fiyat_bicimi(v, beklenen):
    assert TS.fiyat(v) == beklenen


def test_islem_mesajlari_ayni_fiyat_bicimini_kullanir():
    t = TS.islem_acildi("Kol", "DOGE/USDT", "long", 0.123456, 100, 0.1)
    assert "Giriş 0,1235" in t and "Stop 0,10" in t
    t = TS.islem_acildi("Kol", "SOL/USDT", "long", 8.8712, 100, 2001.0)
    assert "Giriş 8,87" in t and "Stop 2.001,00" in t
    from trader_core import telegram as T
    assert T._fiyat(8.8712) == "8,87" and T._fiyat(0.123456) == "0,1235"


def test_haftalik_telegrama_gitmez():
    from types import SimpleNamespace as NS

    from trader_core import telegram as T
    gonderilen = []
    n = T.TelegramNotifier.__new__(T.TelegramNotifier)
    n.send_text = lambda *a, **k: gonderilen.append(a) or True
    n.kayit = NS(gunde_bir=lambda *a: True)
    n.now = lambda: NOW
    assert T.haftalik_gonder(None, n, datetime(2026, 11, 22, 12, 0, tzinfo=UTC)) is False and gonderilen == []
