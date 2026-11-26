"""ML1 gorunum cekirdegi (`trader_core.ml1_gorunum`): eleme sayilari, zaman dilimi tablosu, gruplar, esik kayittan, durum rozeti, 
Telegram ile pano ayni sayilar. Eslemenin `trader_ml` ile birebir ayniligi ve kaldirilan kol listesinin motorla esitligi de burada."""
from __future__ import annotations

import math

import pytest

from ml1_gorunum_destek import BUGUN, ESKI, NOW, kayit, ml1_defter
from trader_core import ledger as L
from trader_core import ml1_gorunum as MG
from trader_core import tg_sade as TS


def _oku(path):
    led = L.open_ledger(path, "learner", create=False, read_only=True, migrate=False)
    try:
        return led.list_decisions(), led.list_closed_trades(None, None, 1000), led.list_open_trades()
    finally:
        led.close()


@pytest.fixture()
def oz(tmp_path):
    p = tmp_path / "l.sqlite"
    ml1_defter(str(p))
    d, c, a = _oku(str(p))
    return MG.ml1_ozet(d, c, a, NOW), (d, c, a)


def test_grup_kurulum_trader_ml_ile_birebir_ayni_ve_her_grubun_adi_var():
    from trader_ml.ml1 import groups as G
    assert MG.GRUP_KURULUM == G._GRUP_KURULUM
    assert set(MG.GRUP_AD) == set(MG.GRUP_KURULUM) and all(MG.GRUP_AD.values())
    assert MG.grup_adi("PULLBACK_1LEG") == "Tek bacaklı geri çekilme" and MG.grup_adi("YOK_BOYLE_BIR_KOD") == "Diğer"
    assert MG.grup_kodu("T1@4h") == "PULLBACK_1LEG" and MG.grup_kodu("M1@1h") is None


def test_kaldirilan_ailer_motordaki_liste_ile_esit():
    from trader_engine.engine import KALDIRILAN_KOLLAR
    assert set(TS.KALDIRILAN_AILELER) == set(KALDIRILAN_KOLLAR)


def test_eleme_sayilari_zd_dort_satir_ve_kanitli_yalniz_4h_1d(oz):
    o, _ = oz
    b, h = o["eleme"]["bugun"], o["eleme"]["7g"]
    assert (b["puanlanan"], b["gecen"], b["islem"]) == (9, 7, 5)       # 5 girilen (biri acik), 4 atlanan: 1 ayni olay, 1 risk, 2 esik alti
    assert b["gecme_yuzde"] == pytest.approx(7 / 9 * 100, abs=0.06)
    assert b["alinmayan"] == {"ayni_olay": 1, "limit": 1, "diger": 0}
    assert (h["puanlanan"], h["gecen"], h["islem"]) == (11, 8, 6) and h["alinmayan"]["ayni_olay"] == 1
    assert [r["kod"] for r in o["zd"]] == ["15m", "1h", "4h", "1d"]
    assert [r["kanitli"] for r in o["zd"]] == [False, False, True, True]
    z = {r["kod"]: r for r in o["zd"]}
    assert z["4h"]["n"] == 2 and z["4h"]["kazanma"] == 50.0 and z["1d"]["n"] == 1 and z["15m"]["n"] == 1
    assert z["1h"]["n"] == 1 and z["1h"]["acik"] == 1                    # acik 1h islemi ve ESKI donemdeki kapanan
    assert o["zd_ozet"]["kanitli"]["n"] == 3 and o["zd_ozet"]["kanitsiz"]["n"] == 2
    assert o["toplam"]["n"] == 5 and o["eski"]["n"] == 3
    assert o["zd_ozet_7g"]["kanitli"]["n"] == 3                           # 7 gun icindeki ML1 islemleri


def test_zd_bos_donemde_dort_satir_ve_sayilar_none(tmp_path):
    from panel_support import NOW as N, PARAMS
    led = L.open_ledger(str(tmp_path / "b.sqlite"), "learner", clock=lambda: N)
    led.init_params(PARAMS, reason="x")
    led.close()
    d, c, a = _oku(str(tmp_path / "b.sqlite"))
    o = MG.ml1_ozet(d, c, a, N)
    assert len(o["zd"]) == 4 and all(r["n"] == 0 and r["net_r"] is None and r["kazanma"] is None for r in o["zd"])
    assert o["esik"] is None and o["eski"] is None and o["eleme"]["bugun"]["gecme_yuzde"] is None


def test_net_r_ve_kz_toplamlari_defterden(oz):
    o, (d, c, a) = oz
    dec = {x.id: x for x in d}
    ml1 = [t for t in c if MG.skor(dec[t.decision_id]) is not None]
    assert o["toplam"]["net_r"] == pytest.approx(math.fsum(t.r_multiple for t in ml1), abs=1e-3)
    assert o["toplam"]["kz"] == pytest.approx(math.fsum(t.realized_pnl for t in ml1), abs=1e-3)
    assert o["toplam"]["kazanma"] == pytest.approx(60.0)                 # 3 kazanan / 5 kapanan


def test_esik_kayittan_okunur_kodda_sabit_degil(tmp_path):
    p = tmp_path / "e.sqlite"
    ml1_defter(str(p), esik=0.6)
    d, c, a = _oku(str(p))
    assert MG.ml1_ozet(d, c, a, NOW)["esik"] == 0.6
    p2 = tmp_path / "e2.sqlite"
    ml1_defter(str(p2), esik=0.35)
    d, c, a = _oku(str(p2))
    o = MG.ml1_ozet(d, c, a, NOW)
    assert o["esik"] == 0.35 and o["eleme"]["bugun"]["gecen"] == 8       # esik 0.35: 0.40 puanli aday da gecer (kaydin kendi esigi)


def test_gruplar_islemi_olmayan_yok_eski_yalniz_tumu(oz):
    _, (d, c, a) = oz
    g = MG.gruplar(d, c)
    adlar_ml1 = [x["grup"] for x in g["ml1"]]
    assert MG.ESKI_GRUP_AD not in adlar_ml1
    assert "Yatay piyasa kenarı" not in adlar_ml1 or all(x["n"] > 0 for x in g["ml1"])          # n >= 1 olmayan grup yok
    assert all(x["n"] >= 1 and x["kollar"] and all(k["n"] >= 1 for k in x["kollar"]) for x in g["ml1"] + g["tumu"])
    assert g["tumu"][-1]["grup"] == MG.ESKI_GRUP_AD and g["tumu"][-1]["n"] == 1             # M1 islemi: kaldirilan kollar, en sonda
    assert not any(k["kol"] == "M1" for x in g["ml1"] for k in x["kollar"])
    sirali = [x["net_r"] for x in g["ml1"]]
    assert sirali == sorted(sirali, reverse=True)
    assert len(g["tumu"]) <= 21


def test_durum_rozeti_dort_hal(oz):
    _, (d, c, a) = oz
    assert MG.durum(d, NOW, None) == {"metin": "Kapalı: adayları ML1 seçmiyor", "renk": "gri"}
    assert MG.durum(d, NOW, False)["renk"] == "gri"
    assert MG.durum(d, NOW, True) == {"metin": "Açık: adayları ML1 seçiyor", "renk": "yesil"}
    assert MG.durum([x for x in d if x.bar_close_ts < BUGUN], NOW, True)["renk"] == "sari"       # son 24 saatte puanlanan yok
    # paket yok: kirmizi
    import types
    pk = types.SimpleNamespace(bar_close_ts=NOW, veto_reason="gate:ml1_paket_yok", skip_reason="ml_no_model", features={})
    assert MG.durum(d + [pk], NOW, True)["renk"] == "kirmizi"


def test_sinav_sabiti_ve_metinleri():
    s = MG.sinav()
    assert s["tarih"] == "26.11" and [r["sonuc"] for r in s["satirlar"]] == ["kazanıyor", "başa baş", "kaybediyor"]
    assert [r["renk"] for r in s["satirlar"]] == ["yesil", "gri", "kirmizi"]
    assert MG.sinav_satiri() == "Sınav (26.11): 4s+1g +0,11 R · 1s ≈ 0 · 15dk −0,04 R"


def test_iyelik_belirtme_eki():
    assert [f"{n}{TS.iyelik_belirtme(n)}" for n in (1, 2, 3, 6, 9, 10, 20, 61, 100)] == [
        "1'ini", "2'sini", "3'ünü", "6'sını", "9'unu", "10'unu", "20'sini", "61'ini", "100'ünü"]
