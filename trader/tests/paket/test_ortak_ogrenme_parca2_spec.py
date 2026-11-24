"""Ortak öğrenme paketi parça 2 belirtiminden türetilmiş testler.

Kapsam: karne + sanal kasa (karne.py), CUSUM drift (drift.py). Testler yalnız belirtime göre yazıldı.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ortak_ogrenme import kayit, karne, drift

UTC = timezone.utc
BASLANGIC = datetime(2026, 1, 1, tzinfo=UTC)


def aday(i, *, r=None, alindi=True, kurulum="T1@1h", sinif="kripto",
         ozellikler=None, ts=None):
    return kayit.Aday(
        id=f"a{i}",
        proje="ML",
        kurulum=kurulum,
        enstruman="BTC/USDT",
        varlik_sinifi=sinif,
        yon="long",
        ts=ts if ts is not None else BASLANGIC + timedelta(hours=i),
        alindi=alindi,
        r=r,
        ozellikler=dict(ozellikler) if ozellikler is not None else {},
    )


# --------------------------------------------------------------------------
# karne.karne
# --------------------------------------------------------------------------

def test_karne_alanlari_ve_ortalamalar():
    adaylar = [
        aday(0, r=1.0, alindi=True, sinif="kripto"),
        aday(1, r=-0.5, alindi=True, sinif="kripto"),
        aday(2, r=2.0, alindi=False, sinif="hisse"),
        aday(3, r=None, alindi=True, sinif="hisse"),
    ]
    k = karne.karne(adaylar)["T1@1h"]

    assert set(k) == {"aday", "alinan", "cozulen", "ort_r_alinan",
                      "ort_r_tum", "sinif", "kasa"}
    assert k["aday"] == 4
    assert k["alinan"] == 3          # alindi olanlar, r None olsa da sayılır
    assert k["cozulen"] == 3         # r'si olan: 0, 1, 2
    assert k["ort_r_alinan"] == pytest.approx((1.0 - 0.5) / 2)
    assert k["ort_r_tum"] == pytest.approx((1.0 - 0.5 + 2.0) / 3)
    assert k["kasa"] == karne.sanal_kasa(adaylar)["T1@1h"]


def test_karne_sinif_kirilimi_kasasiz():
    adaylar = [
        aday(0, r=1.0, alindi=True, sinif="kripto"),
        aday(1, r=-0.5, alindi=True, sinif="kripto"),
        aday(2, r=2.0, alindi=False, sinif="hisse"),
        aday(3, r=None, alindi=True, sinif="hisse"),
    ]
    sinif = karne.karne(adaylar)["T1@1h"]["sinif"]

    assert set(sinif) == {"kripto", "hisse"}
    for girdi in sinif.values():
        assert set(girdi) == {"aday", "alinan", "cozulen", "ort_r_alinan", "ort_r_tum"}
        assert "kasa" not in girdi

    kripto = sinif["kripto"]
    assert kripto["aday"] == 2
    assert kripto["alinan"] == 2
    assert kripto["cozulen"] == 2
    assert kripto["ort_r_alinan"] == pytest.approx(0.25)
    assert kripto["ort_r_tum"] == pytest.approx(0.25)

    hisse = sinif["hisse"]
    assert hisse["aday"] == 2
    assert hisse["alinan"] == 1
    assert hisse["cozulen"] == 1
    assert hisse["ort_r_alinan"] is None   # alındı ama r yok
    assert hisse["ort_r_tum"] == pytest.approx(2.0)


def test_karne_r_yoksa_ortalamalar_none():
    adaylar = [aday(0, r=None, alindi=True), aday(1, r=None, alindi=False)]
    k = karne.karne(adaylar)["T1@1h"]
    assert k["aday"] == 2
    assert k["cozulen"] == 0
    assert k["ort_r_alinan"] is None
    assert k["ort_r_tum"] is None


def test_karne_alindi_olmayan_r_alinan_ortalamaya_girmez():
    adaylar = [aday(0, r=3.0, alindi=False), aday(1, r=1.0, alindi=True)]
    k = karne.karne(adaylar)["T1@1h"]
    assert k["ort_r_alinan"] == pytest.approx(1.0)
    assert k["ort_r_tum"] == pytest.approx(2.0)


def test_karne_adaysiz_kurulum_sifir_satir():
    sonuc = karne.karne([], kurulumlar=("Z",))
    assert list(sonuc) == ["Z"]
    k = sonuc["Z"]
    assert k["aday"] == 0
    assert k["alinan"] == 0
    assert k["cozulen"] == 0
    assert k["ort_r_alinan"] is None
    assert k["ort_r_tum"] is None
    assert k["sinif"] == {}
    assert k["kasa"]["alinan"]["n"] == 0
    assert k["kasa"]["alinan"]["kasa"] == pytest.approx(1000.0)


def test_karne_kurulum_sirasi_once_kurulumlar_sonra_gorulme():
    adaylar = [
        aday(0, r=1.0, kurulum="B"),
        aday(1, r=1.0, kurulum="A"),
    ]
    sonuc = karne.karne(adaylar, kurulumlar=("Z", "A"))
    assert list(sonuc) == ["Z", "A", "B"]
    assert sonuc["Z"]["aday"] == 0
    assert sonuc["A"]["aday"] == 1
    assert sonuc["B"]["aday"] == 1


# --------------------------------------------------------------------------
# karne.sanal_kasa
# --------------------------------------------------------------------------

def test_sanal_kasa_bilesik_getiri():
    res = karne.sanal_kasa([aday(0, r=2.0), aday(1, r=-1.0)])
    seri = res["T1@1h"]["alinan"]
    assert seri["n"] == 2
    assert seri["kasa"] == pytest.approx(1009.8)
    assert seri["getiri_pct"] == pytest.approx(0.98)


def test_sanal_kasa_alt_sinir_sifir():
    adaylar = [aday(0, r=-2.0), aday(1, r=1.0)]
    res = karne.sanal_kasa(adaylar, risk=1.0)
    assert res["T1@1h"]["alinan"]["kasa"] == 0.0


def test_sanal_kasa_dusus_baslangictan_olculur():
    res = karne.sanal_kasa([aday(0, r=-1.0), aday(1, r=2.0)])
    seri = res["T1@1h"]["alinan"]
    # 1000 -> 990 -> 1009.8: en derin nokta başlangıçtan %1 (işaret belirtimde
    # tanımlı değil; büyüklük kontrol edilir)
    assert abs(seri["en_derin_pct"]) == pytest.approx(1.0, abs=0.01)
    assert seri["kasa"] == pytest.approx(1009.8)


def test_sanal_kasa_ayni_ts_stabil_siralama():
    ts = BASLANGIC
    kayip_once = [aday(0, r=-1.0, ts=ts), aday(1, r=1.0, ts=ts)]
    kazanc_once = [aday(1, r=1.0, ts=ts), aday(0, r=-1.0, ts=ts)]

    seri_a = karne.sanal_kasa(kayip_once)["T1@1h"]["alinan"]
    seri_b = karne.sanal_kasa(kazanc_once)["T1@1h"]["alinan"]

    # Girdi sırası korunur: önce -1 (990), sonra +1 -> en derin %1 (büyüklük)
    assert abs(seri_a["en_derin_pct"]) == pytest.approx(1.0, abs=0.01)
    assert seri_a["kasa"] == pytest.approx(999.9)
    # (lider duzeltmesi) Dusus TEPEDEN olculur (ML ile ayni): 1000 -> 1010 -> 999.9 => (1010-999.9)/1010 = %1.0
    assert abs(seri_b["en_derin_pct"]) == pytest.approx(1.0, abs=0.01)
    assert seri_b["kasa"] == pytest.approx(999.9)
    # Sira korunur: once kayip => 990 dibi baslangictan; once kazanc => tepe 1010 (kasa yolu farkli, sonuc ayni)
    assert seri_a["kasa"] == seri_b["kasa"]


def test_sanal_kasa_ts_sirasina_gore_isler():
    gec = aday(5, r=-1.0)
    erken = aday(0, r=2.0)
    res = karne.sanal_kasa([gec, erken])
    assert res["T1@1h"]["alinan"]["kasa"] == pytest.approx(1009.8)


def test_sanal_kasa_alinan_ve_tum_ayrimi():
    adaylar = [
        aday(0, r=1.0, alindi=False),
        aday(1, r=1.0, alindi=True),
        aday(2, r=None, alindi=True),
    ]
    res = karne.sanal_kasa(adaylar)["T1@1h"]
    assert res["alinan"]["n"] == 1
    assert res["tum"]["n"] == 2


@pytest.mark.parametrize("kwargs", [
    {"baslangic": 0.0},
    {"baslangic": -5.0},
    {"risk": 0.0},
    {"risk": -0.01},
])
def test_sanal_kasa_gecersiz_parametre(kwargs):
    with pytest.raises(ValueError):
        karne.sanal_kasa([aday(0, r=1.0)], **kwargs)


# --------------------------------------------------------------------------
# drift
# --------------------------------------------------------------------------

def test_drift_sabitleri():
    assert drift.CUSUM_MU0 == -0.111
    assert drift.CUSUM_SIGMA0 == 1.224
    assert drift.CUSUM_K == 0.5
    assert tuple(drift.CUSUM_CLIP) == (-1.5, 3.0)
    assert drift.CUSUM_UYARI == 4.0
    assert drift.CUSUM_COOLDOWN == 30
    assert drift.MIN_N == 20


def test_cusum_kucuk_pozitif_sabit_alarm_yok():
    sonuc = drift.cusum([0.1] * 200)
    assert sonuc["alarms"] == []
    assert sonuc["S"] == pytest.approx(0.0)
    assert sonuc["n"] == 200


def test_cusum_uzun_kayip_serisi_alarm_ve_cooldown():
    sonuc = drift.cusum([-1.5] * 100)
    alarmlar = sonuc["alarms"]
    assert len(alarmlar) >= 2
    assert alarmlar[0] >= 20
    # cooldown 30: ardışık alarmlar arası en az 30 işlem
    for a, b in zip(alarmlar, alarmlar[1:]):
        assert b - a >= 30


def test_cusum_clip_kayip_sinirlanir():
    assert drift.cusum([-10.0] * 60) == drift.cusum([-1.5] * 60)


def test_kurulum_drift_uyari_ve_normal():
    adaylar = [aday(i, r=-1.5, kurulum="A") for i in range(25)]
    adaylar += [aday(100 + i, r=0.2, kurulum="B") for i in range(25)]
    sonuc = drift.kurulum_drift(adaylar)

    assert sonuc["A"]["durum"] == "uyari"
    assert sonuc["B"]["durum"] == "normal"


def test_kurulum_drift_alinmamis_satirlar_dislanir():
    adaylar = [aday(i, r=-1.5, alindi=False, kurulum="C") for i in range(25)]
    sonuc = drift.kurulum_drift(adaylar)
    # Satırı olmayan kurulum anahtarla hiç yer almayabilir; yer alıyorsa normal olmalı
    assert sonuc.get("C", {"durum": "normal"})["durum"] == "normal"


def test_kurulum_drift_ts_sirasi_girdi_sirasindan_bagimsiz():
    adaylar = [aday(i, r=-1.5, kurulum="A") for i in range(25)]
    assert drift.kurulum_drift(list(reversed(adaylar))) == drift.kurulum_drift(adaylar)


def test_kurulum_drift_eski_alarm_normal_doner():
    adaylar = [aday(i, r=-1.5, kurulum="D") for i in range(25)]
    adaylar += [aday(100 + i, r=0.0, kurulum="D") for i in range(40)]
    sonuc = drift.kurulum_drift(adaylar)
    assert sonuc["D"]["durum"] == "normal"
