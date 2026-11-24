"""Ortak ogrenme paketi parca 2 (spec bolum 4): ML ile esdegerlik (karne, sanal kasa, CUSUM).

ML referanslari: counterfactual.arm_scorecard / arm_virtual_bankroll, drift_monitor.cusum_replay. Paket tarafi yalniz standart kutuphane.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from trader_core.counterfactual import arm_scorecard, arm_virtual_bankroll
from trader_core.drift_monitor import cusum_replay

from ortak_ogrenme import drift, karne
from ortak_ogrenme.kayit import Aday

T0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
KURULUMLAR = ("T1", "R1", "X9")          # X9: adayi olmayan (sifir satir) kurulum
SINIFLAR = ("kripto", "hisse", "emtia")


def _adaylar(rng, n=240, kurulumlar=("T1", "R1")):
    out = []
    for i in range(n):
        r = None if rng.random() < 0.1 else float(rng.normal(0.1, 1.2))
        if i == 3:
            r = -150.0                     # kasayi sifira indiren kayip (max(0, ...) dalinin testi)
        out.append(Aday(
            id=str(i), proje="ML", kurulum=str(rng.choice(kurulumlar)), enstruman="BTC/USDT",
            varlik_sinifi=str(rng.choice(SINIFLAR)), yon="long",
            # saat olcegi: esitlikler (ayni ts) kasitli olarak olusur
            ts=T0 + timedelta(hours=int(rng.integers(0, 400))),
            alindi=bool(rng.random() < 0.5), r=r,
            ozellikler={"a": float(rng.normal()), "b": float(rng.normal(size=1)[0]) * 3}
            if rng.random() < 0.85 else {"a": "yok", "c": float(i)},
        ))
    return out


def _ml_cands(adaylar):
    return [{"arm_id": a.kurulum, "ts": a.ts, "r": a.r, "taken": a.alindi, "asset_class": a.varlik_sinifi}
            for a in adaylar]


def _ort_esle(ours, ref):
    if ref is None:
        assert ours is None
    else:
        assert ours == pytest.approx(ref, rel=1e-12, abs=1e-12)


def _blok_esle(ml, k):
    assert k["aday"] == ml["candidates"]
    assert k["alinan"] == ml["taken"]
    assert k["cozulen"] == ml["resolved"]
    _ort_esle(k["ort_r_alinan"], ml["mean_r_taken"])
    _ort_esle(k["ort_r_tum"], ml["mean_r_taken_cf"])


def _seri_esle(ml, k):
    assert k["n"] == ml["n"]
    assert k["kasa"] == ml["equity"]
    assert k["getiri_pct"] == ml["return_pct"]
    assert k["en_derin_pct"] == ml["max_dd_pct"]


# --------------------------------------------------------------------------- karne / sanal kasa
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_karne_arm_scorecard_esdeger(seed):
    rng = np.random.default_rng(seed)
    adaylar = _adaylar(rng)
    ml = arm_scorecard(_ml_cands(adaylar), arms=KURULUMLAR)
    k = karne.karne(adaylar, kurulumlar=KURULUMLAR)
    assert list(k) == list(ml)                       # sira: once kurulumlar, sonra goruldugu sira
    for arm in ml:
        _blok_esle(ml[arm], k[arm])
        assert set(k[arm]["sinif"]) == set(ml[arm]["by_class"])
        for cls, mb in ml[arm]["by_class"].items():
            _blok_esle(mb, k[arm]["sinif"][cls])
        assert "kasa" in k[arm] and "sinif" in k[arm]
    assert k["X9"]["aday"] == 0 and k["X9"]["sinif"] == {}


@pytest.mark.parametrize("seed", [0, 1])
def test_sanal_kasa_arm_virtual_bankroll_esdeger(seed):
    rng = np.random.default_rng(seed)
    adaylar = _adaylar(rng)
    ml = arm_virtual_bankroll(_ml_cands(adaylar), start=1000.0, risk=0.01, arms=KURULUMLAR)
    kasa = karne.sanal_kasa(adaylar, baslangic=1000.0, risk=0.01, kurulumlar=KURULUMLAR)
    assert list(kasa) == list(ml)
    for arm in ml:
        _seri_esle(ml[arm]["taken"], kasa[arm]["alinan"])
        _seri_esle(ml[arm]["cf"], kasa[arm]["tum"])


def test_karne_kasa_arm_scorecard_kasa_ile_ayni():
    rng = np.random.default_rng(7)
    adaylar = _adaylar(rng)
    ml = arm_scorecard(_ml_cands(adaylar), arms=KURULUMLAR)
    k = karne.karne(adaylar, kurulumlar=KURULUMLAR)
    for arm in ml:
        _seri_esle(ml[arm]["kasa"]["taken"], k[arm]["kasa"]["alinan"])
        _seri_esle(ml[arm]["kasa"]["cf"], k[arm]["kasa"]["tum"])


def test_sanal_kasa_parametre_dogrulama():
    with pytest.raises(ValueError):
        karne.sanal_kasa([], baslangic=0.0)
    with pytest.raises(ValueError):
        karne.sanal_kasa([], risk=0.0)


# --------------------------------------------------------------------------- CUSUM (ML cusum_replay)
@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_cusum_cusum_replay_esdeger(seed):
    rng = np.random.default_rng(seed)
    rs = list(rng.normal(-0.8, 1.1, 260)) + [-12.0, 9.0] + list(rng.normal(0.2, 1.0, 120))
    ml = cusum_replay(rs)
    ours = drift.cusum(rs)
    assert ml["alarms"], "test serisi alarm uretmeli"
    assert ours["alarms"] == ml["alarms"]
    assert ours["n"] == ml["n"]
    assert ours["cooldown"] == ml["cooldown"]
    assert ours["S"] == pytest.approx(ml["S"], rel=1e-12, abs=1e-12)


def test_cusum_sabitleri_ml_ile_ayni():
    from trader_core import drift_monitor as DM
    assert drift.CUSUM_MU0 == DM.CUSUM_MU0 and drift.CUSUM_SIGMA0 == DM.CUSUM_SIGMA0
    assert drift.CUSUM_K == DM.CUSUM_K and drift.CUSUM_CLIP == (DM.CUSUM_CLIP_LO, DM.CUSUM_CLIP_HI)
    assert drift.CUSUM_UYARI == DM.CUSUM_UYARI and drift.CUSUM_COOLDOWN == DM.CUSUM_COOLDOWN
    assert drift.MIN_N == DM.MIN_N


def test_kurulum_drift_durum_uyari():
    rng = np.random.default_rng(5)
    rs = list(rng.normal(-0.9, 1.0, 60))
    adaylar = [Aday(id=str(i), proje="ML", kurulum="T1", enstruman="BTC/USDT", varlik_sinifi="kripto",
                    yon="long", ts=T0 + timedelta(hours=i), alindi=True, r=float(r))
               for i, r in enumerate(rs)]
    sonuc = drift.kurulum_drift(adaylar)["T1"]
    assert sonuc["alarms"] and sonuc["alarms"] == cusum_replay(rs)["alarms"]
    kalan = sonuc["n"] - sonuc["alarms"][-1]
    assert sonuc["durum"] == ("uyari" if kalan < drift.CUSUM_COOLDOWN else "normal")
