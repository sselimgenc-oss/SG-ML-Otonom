"""HB1 haber kolu (ust lig): sinyal dosyasi -> aday; yok/bozuk/bayat/sizinti -> aday yok; parite; kol tavani."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import haber_sinyal as HS
from trader_core.signals import SIGNAL_COLUMNS
from trader_engine.strategies.arms import ArmInput, discover, exit_mode, find_arm
import trader_engine.strategies.arms.hb1 as HB1

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
D = datetime(2026, 11, 24, 13, 0, tzinfo=UTC)          # karar zamani = son 1s mumun kapanisi
H = 3_600_000


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _belge(uretim, ens, **kw):
    b = {"schema": HS.SEMA, "uretim_ms": _ms(uretim), "gecerlilik_sonu_ms": _ms(uretim) + 3 * H, "enstrumanlar": ens}
    b.update(kw)
    return b


GUCLU = {"puan": 1.2, "kaynak_sayisi": 2, "max_siddet": 2, "oge_sayisi": 2}


@pytest.fixture
def sinyal(tmp_path, monkeypatch):
    yol = tmp_path / "haber_sinyal.json"
    monkeypatch.setattr(HB1, "SINYAL_YOLU", yol)
    HB1.COUNTERS.clear()
    HB1._ONBELLEK.update(key=None, belge=None, neden=None)

    def yaz(belge):
        yol.write_text(belge if isinstance(belge, str) else json.dumps(belge), encoding="utf-8")
        HB1._ONBELLEK.update(key=None)
        return yol
    yaz.yol = yol
    return yaz


def _inp(pair="BTC/USDT", yon_yukari=True, n=80, D_=D):
    idx = pd.DatetimeIndex([D_ - timedelta(hours=n - k) for k in range(n)])
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    o = np.r_[c[0], c[:-1]]
    c[-1] = o[-1] + (0.8 if yon_yukari else -0.8)
    h = np.maximum(o, c) + 0.4
    lo = np.minimum(o, c) - 0.4
    trig = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)

    def core():
        t = pd.DataFrame(index=idx, columns=SIGNAL_COLUMNS)
        t["regime"] = "none"
        t["signal"] = False
        t["pullback_ema"] = 0
        return t
    return ArmInput(pair=pair, tf="1h", D=D_, trig=trig, h4=trig, params=None, core_fn=core)


def _son(out):
    return out.iloc[-1]


def test_kontrat_ve_kimlik():
    m = discover(refresh=True)["HB1"]
    assert m.TIMEFRAMES == ("1h",) and m.EXIT_MODE == "target" and exit_mode("HB1") == "target" and find_arm("HB1") is m
    assert m.ESIK_PUAN == 0.6 and m.MIN_KAYNAK == 2 and m.SIDDET_YETERLI == 3 and m.SIZINTI_MARJ_S == 60


def test_taze_guclu_sinyal_ve_mum_long_aday(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": GUCLU}))
    out = HB1.compute(_inp())
    r = _son(out)
    assert bool(r["signal"]) and r["setup"] == "HB1" and r["side"] == "long"
    assert r["planned_stop"] < r["planned_entry"] < r["planned_target"]
    atr_stop = r["planned_entry"] - r["planned_stop"]
    assert (r["planned_target"] - r["planned_entry"]) == pytest.approx(2 * atr_stop)   # stop 1,5 ATR, hedef 3 ATR
    assert r["rr"] == pytest.approx(2.0) and not out.iloc[:-1]["signal"].any()


def test_negatif_puan_ve_dusen_mum_short_aday(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"ETH/USDT": {"puan": -1.0, "kaynak_sayisi": 1, "max_siddet": 3, "oge_sayisi": 1}}))
    r = _son(HB1.compute(_inp("ETH/USDT", yon_yukari=False)))
    assert bool(r["signal"]) and r["side"] == "short" and r["planned_target"] < r["planned_entry"] < r["planned_stop"]


@pytest.mark.parametrize("satir", [
    {"puan": 0.59, "kaynak_sayisi": 3, "max_siddet": 3, "oge_sayisi": 3},     # esik alti
    {"puan": 1.5, "kaynak_sayisi": 1, "max_siddet": 2, "oge_sayisi": 1},      # tek kaynak, siddet < 3
])
def test_zayif_ya_da_tek_kaynak_aday_yok(sinyal, satir):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": satir}))
    assert not _son(HB1.compute(_inp()))["signal"]


def test_mum_ters_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": GUCLU}))            # long sinyali, mum asagi kapanmis
    assert not _son(HB1.compute(_inp(yon_yukari=False)))["signal"]
    assert HB1.COUNTERS["mum_ters"] == 1


def test_enstruman_dosyada_yok_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"ETH/USDT": GUCLU}))
    assert not _son(HB1.compute(_inp("BTC/USDT")))["signal"]


def test_bayat_dosya_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(hours=3, minutes=1), {"BTC/USDT": GUCLU}))
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["bayat"] == 1


def test_gecerlilik_alani_uzatilsa_da_uretim_arti_3_saat_tavan(sinyal):
    sinyal(_belge(D - timedelta(hours=4), {"BTC/USDT": GUCLU}, gecerlilik_sonu_ms=_ms(D) + 10 * H))
    assert not _son(HB1.compute(_inp()))["signal"]


def test_sizinti_mum_kapanisi_uretimden_once_ya_da_60sn_icinde(sinyal):
    for fark in (timedelta(minutes=-5), timedelta(seconds=-30), timedelta(0), timedelta(seconds=-60)):   # uretim = D - fark
        sinyal(_belge(D - fark, {"BTC/USDT": GUCLU}))
        assert not _son(HB1.compute(_inp()))["signal"], fark
    sinyal(_belge(D - timedelta(seconds=61), {"BTC/USDT": GUCLU}))
    assert bool(_son(HB1.compute(_inp()))["signal"])
    assert HB1.COUNTERS["sizinti"] == 4


@pytest.mark.parametrize("icerik", [None, "{bozuk json", "[]", json.dumps({"schema": "x/9", "uretim_ms": 1}),
                                    json.dumps({"schema": HS.SEMA, "uretim_ms": "a", "gecerlilik_sonu_ms": 2, "enstrumanlar": {}}),
                                    json.dumps({"schema": HS.SEMA, "uretim_ms": 1, "gecerlilik_sonu_ms": 2, "enstrumanlar": []})])
def test_yok_bozuk_sema_disi_dosya_aday_yok_istisna_yok(sinyal, icerik):
    if icerik is not None:
        sinyal(icerik)
    out = HB1.compute(_inp())
    assert list(out.columns) == SIGNAL_COLUMNS and len(out) == 80 and not out["signal"].any()
    assert sum(HB1.COUNTERS.values()) == 1


def test_bozuk_satir_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": {"puan": "yuksek", "kaynak_sayisi": 2, "max_siddet": 3}}))
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["satir_bozuk"] == 1


def test_bozuk_dosya_diger_kollari_etkilemez(sinyal):
    """HB1 bozuk dosyada bos tablo doner; baska kol (M1: paket yok) bagimsiz calisir, HB1 modulu baska kolun durumuna dokunmaz."""
    sinyal("{bozuk")
    import trader_engine.strategies.arms.m1 as M1
    inp = _inp()
    assert not HB1.compute(inp)["signal"].any()
    assert not M1.compute(inp)["signal"].any()        # M1 de bagimsiz (paketsiz) bos doner; ikisi birbirinin hatasini tasimaz
    assert "HB1" not in str(M1.__dict__.get("COUNTERS", ""))


def test_hb1_sinyal_sozlesmesi_uretici_ile_ayni():
    """Motor trader_core.haber_sinyal'i ice aktarmaz; sabitler elle kopyalandi, burada esitlik sinanir."""
    from trader_core import haber_sinyal as HS
    from trader_engine.strategies.arms import hb1
    assert (hb1.HS_SEMA, hb1.HS_GECERLILIK_SAAT, hb1.HS_PUAN_SINIR, hb1.HS_H_MS, hb1.HS_CIKTI_DOSYASI) == \
        (HS.SEMA, HS.GECERLILIK_SAAT, HS.PUAN_SINIR, HS.H_MS, HS.CIKTI_DOSYASI)
