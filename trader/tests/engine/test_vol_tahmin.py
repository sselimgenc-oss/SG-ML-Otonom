"""Fikir 10 (23.11): oynaklik tahmini ozellikleri (`f_vol_tahmin`, `f_vol_asim`) yalniz gece suzgecinin ek girdisi.
Ileriye bakis yok, olcek degismez, NaN/kisa guvenli, eski ML1 paketi ve eski gece paketi etkilenmez."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ortak_ogrenme import filtre as PF
from ortak_ogrenme.kayit import Aday
from trader_core.ml_live_v2 import setup_feature_dict, setup_feature_vector
from trader_core.ml_package import load_package
from trader_engine import ogrenme_filtre as OF
from trader_engine.gates import _features
from trader_engine.vol_tahmin import MIN_GETIRI, vol_ozellikleri

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_engine_05_impl_smoke import _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 2, tzinfo=timezone.utc)


def _seri(n=300, seed=7):
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


def test_ileriye_bakis_yok():
    c = _seri(400)
    t = 300
    a = vol_ozellikleri(c[: t + 1], 1.0, "1h")
    b = vol_ozellikleri(c[: t + 1], 1.0, "1h")
    assert a and a == b
    # t aninda hesap, gelecek mumlar eklenince (kesit ayni) degismez: gelecek veri girdi olamaz
    assert vol_ozellikleri(c[:301].copy(), 1.0, "1h") == a
    assert vol_ozellikleri(c[:301], 1.0, "1h") != vol_ozellikleri(c[:350], 1.0, "1h")


def test_olcek_degismez():
    c = _seri()
    a = vol_ozellikleri(c, 0.8, "1h")
    for k in (0.001, 1000.0, 65000.0):
        b = vol_ozellikleri(c * k, 0.8 * k, "1h")
        assert math.isclose(a["vol_tahmin"], b["vol_tahmin"], rel_tol=1e-9)
        assert math.isclose(a["vol_asim"], b["vol_asim"], rel_tol=1e-9)
    assert -1.0 <= a["vol_asim"] <= 1.0


def test_nan_kisa_guvenli():
    c = _seri()
    assert vol_ozellikleri(c[:MIN_GETIRI], 1.0) == {}
    assert vol_ozellikleri([], 1.0) == {} and vol_ozellikleri(None, 1.0) == {}
    bad = c.copy(); bad[-5] = float("nan")
    assert vol_ozellikleri(bad, 1.0) == {}
    neg = c.copy(); neg[-10] = -1.0
    assert vol_ozellikleri(neg, 1.0) == {}
    for atr in (None, float("nan"), 0.0, -1.0, "x"):
        assert vol_ozellikleri(c, atr) == {}
    assert vol_ozellikleri(np.full(100, 5.0), 1.0) == {}        # sabit fiyat: varyans 0
    assert vol_ozellikleri(c, 1.0, "bilinmeyen") != {}


def test_asimetri_isareti():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.005, 200)
    r[-3:] = [-0.03, -0.02, -0.025]          # son sert dususler: asagi varyans payi baskin
    a = vol_ozellikleri(100 * np.exp(np.cumsum(r)), 1.0)
    assert a["vol_asim"] > 0.3
    r[-3:] = [0.03, 0.02, 0.025]
    assert vol_ozellikleri(100 * np.exp(np.cumsum(r)), 1.0)["vol_asim"] < -0.3


def test_karar_ozelliklerinde_ve_egitim_matrisinde():
    f = _features(_row(vol_tahmin=1.3, vol_asim=-0.2))
    assert f["vol_tahmin"] == 1.3 and f["vol_asim"] == -0.2
    f0 = _features(_row())                                      # eksik => yazilmaz, cokmez
    assert "vol_tahmin" not in f0 and "vol_asim" not in f0
    assert "vol_tahmin" not in _features(_row(vol_tahmin=float("nan")))
    oz = OF.ozellikler(side="long", regime="trend_up", atr_ratio=1.0, session_tag=None, pair="BTC/USDT", planned_entry=100.0,
                       planned_stop=98.0, features=f)
    assert oz["f_vol_tahmin"] == 1.3 and oz["f_vol_asim"] == -0.2
    ad = [Aday(id=f"a{i}", proje="ML", kurulum="T1@1h", enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long",
               ts=T0 + timedelta(hours=i), alindi=True, r=1.0 if i % 2 else -1.0,
               ozellikler={**oz, "f_vol_tahmin": 1.0 + i * 0.01}) for i in range(40)]
    adlar = PF.ozellik_adlari(ad)
    assert "f_vol_tahmin" in adlar and "f_vol_asim" in adlar
    X = PF.matris(adlar, ad)
    assert np.isfinite(X[:, adlar.index("f_vol_tahmin")]).all()
    pk = PF.egit("T1", [Aday(**{**a.__dict__, "kurulum": "T1"}) for a in ad], olusturma=T0)
    assert "f_vol_tahmin" in pk["meta"]["ozellikler"]
    # eksik ozellik: filtre `fill` ile doldurur, cokmez
    p = PF.puan(pk, {k: v for k, v in oz.items() if not k.startswith("f_vol")})
    assert 0.0 <= p <= 1.0


def test_eski_ml1_paketinin_ozellik_vektoru_degismez():
    pk = load_package(ROOT / "models" / "ml1-r03.json", check_expiry=False, require_gate=False)
    names = pk["meta"]["features"] if isinstance(pk, dict) else pk.features
    base = dict(side="long", regime="trend_up", atr_ratio=1.0, session_tag="eu", asset_class=None, pair="BTC/USDT",
                planned_entry=100.0, planned_stop=98.0, rh_touches=1, rl_touches=2)
    eski = {"atr_tf": 1.0, "stop_dist_atr": 2.0, "atr_4h": 2.0, "ema_value": 99.0, "body_ratio": 0.5, "pullback_ema": 3,
            "btc_slope_4h": 0.1}
    yeni = {**eski, "vol_tahmin": 1.4, "vol_asim": 0.3}
    assert len(names) == 8
    v0 = setup_feature_vector(names, setup_feature_dict(**base, features=eski))
    v1 = setup_feature_vector(names, setup_feature_dict(**base, features=yeni))
    assert np.array_equal(v0, v1, equal_nan=True)
    assert np.isfinite(v0[names.index("f_btc_slope_4h")])
    assert not any(n in ("f_vol_tahmin", "f_vol_asim") for n in names)


def test_eski_gece_paketi_hala_skorlar():
    ad = [Aday(id=f"a{i}", proje="ML", kurulum="T1", enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long",
               ts=T0 + timedelta(hours=i), alindi=True, r=1.0 if i % 2 else -1.0,
               ozellikler={"x": 5.0 if i % 2 else -5.0}) for i in range(40)]
    eski = PF.egit("T1", ad, olusturma=T0)                       # vol ozellikleri OLMADAN egitilmis paket
    assert "f_vol_tahmin" not in eski["meta"]["ozellikler"]
    p = PF.puan(eski, {"x": 5.0, "f_vol_tahmin": 1.2, "f_vol_asim": 0.1})
    assert 0.0 <= p <= 1.0 and p == PF.puan(eski, {"x": 5.0})


def test_runner_satira_yazar_yalniz_adayda():
    import pandas as pd
    from trader_engine.strategy_runner import _to_row
    c = _seri(300)
    trig = pd.DataFrame({"close": c}, index=pd.date_range("2026-01-01", periods=300, freq="1h", tz="UTC"))
    r = _row()
    s = pd.Series({k: getattr(r, k) for k in r.__dataclass_fields__ if k not in ("pair", "bar_open_ts", "bar_close_ts")})
    s["atr_tf"] = 1.0
    row = _to_row("BTC/USDT", T0, T0, s, 1, trig, "1h")
    assert row.vol_tahmin is not None and row.vol_asim is not None
    assert _features(row)["vol_tahmin"] == row.vol_tahmin
    s2 = s.copy(); s2["setup"] = None
    assert _to_row("BTC/USDT", T0, T0, s2, 1, trig, "1h").vol_tahmin is None
    assert _to_row("BTC/USDT", T0, T0, s, 1, None, "1h").vol_tahmin is None
