"""Durust kapanis nedeni etiketleri (pano ve Telegram ayni `tg_sade.kapanis_neden`): 'elle' yalniz borsadan kapatilan (manual) icin."""
from __future__ import annotations

import pytest

from trader_core import ledger as L
from trader_core import tg_sade as TS

TABLO = [   # (kod, pnl, setup, etiket)
    ("stop", -3.0, "T1@1h", "stop"),
    ("stop", None, "T1@1h", "stop"),
    ("stop", 2.0, "T1@1h", "kâr al (stop)"),
    ("trail_stop", 1.0, "T1@1h", "iz süren stop"),
    ("target", 5.0, "T1@1h", "kâr al"),
    ("time_stop", -1.0, "T1@1h", "süre doldu"),
    ("regime_flip", 0.5, "T1@1h", "piyasa değişti"),
    ("other", -0.4, "MF1-YUTAN@1h", "bot kapattı (kural/koruma)"),
    ("force_exit", -2.0, "M1@1h", "kol kaldırıldı"),
    ("force_exit", -2.0, "T1@1h", "bot kapattı (zorunlu)"),
    ("manual", 1.0, "T1@1h", "elle (borsadan)"),
    ("liquidation", -9.0, "T1@1h", "tasfiye"),
]


@pytest.mark.parametrize("kod,pnl,setup,etiket", TABLO)
def test_tablodaki_her_satir(kod, pnl, setup, etiket):
    assert TS.kapanis_neden(kod, pnl, setup) == etiket
    assert TS.kapanis_aciklama(kod, pnl, setup).endswith(".")


def test_bilinmeyen_ve_bos_kod_bilinmiyor_elle_degil():
    for k in ("yok_boyle_kod", "", None, "None"):
        assert TS.kapanis_neden(k) == "bilinmiyor" and "kayıtta yok" in TS.kapanis_aciklama(k)


@pytest.mark.parametrize("aile", ["M1", "DL1", "HB1", "C1"])
def test_kaldirilan_ailelerde_force_exit_kol_kaldirildi(aile):
    assert TS.kapanis_neden("force_exit", -1.0, f"{aile}@4h") == "kol kaldırıldı"
    assert TS.kapanis_neden("force_exit", -1.0, f"{aile}-X@4h") == "kol kaldırıldı"          # aile = '-' oncesi
    assert TS.kapanis_neden("force_exit", -1.0, "T1@4h") == "bot kapattı (zorunlu)"
    assert TS.kapanis_neden("force_exit", -1.0, None) == "bot kapattı (zorunlu)"


def test_defterdeki_her_cikis_kodu_icin_elle_yalniz_manual():
    for kod in L._EXIT_REASONS:
        for pnl in (-1.0, 0.0, 1.0):
            e = TS.kapanis_neden(kod, pnl, "T1@1h")
            assert e != "bilinmiyor", kod                                        # defterin her kodu sozlukte
            assert ("elle" in e) == (kod == "manual"), (kod, e)
            assert "elle" not in TS.kapanis_aciklama(kod, pnl, "T1@1h").lower() or kod == "manual"


def test_turkce_ilk_harf_buyutme():
    assert TS.ilk_buyuk("iz süren stop") == "İz süren stop" and TS.ilk_buyuk("kâr al") == "Kâr al" and TS.ilk_buyuk("") == ""


def test_basabas_stopu_hedefli_kolda_kar_al_stop_gorunur():
    """5-01: hedefli (iz sürmeyen) kolda `trail_stop` = başa-baş stop; kârdaysa 'kâr al (stop)'. Kayıt kodu değişmez."""
    assert TS.kapanis_neden("trail_stop", 0.4, "R1@1h", 105.0) == "kâr al (stop)"
    assert TS.kapanis_aciklama("trail_stop", 0.4, "R1@1h", 105.0).endswith(".")
    assert TS.kapanis_neden("trail_stop", -0.4, "R1@1h", 105.0) == "iz süren stop"   # zararda değişmez
    assert TS.kapanis_neden("trail_stop", 0.4, "T1@1h", None) == "iz süren stop"     # iz süren kol (hedefsiz)
    assert TS.kapanis_neden("trail_stop", 0.4, "T1@1h") == "iz süren stop"
