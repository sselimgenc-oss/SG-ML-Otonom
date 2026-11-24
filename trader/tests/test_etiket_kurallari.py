"""Etiket kurallari (docs/etiket-kurallari-spec.md): yalniz SABIT rejim kurali; duygu/haber/otomatik mekanizma SILINDI (21 Kasim 2026)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trader_core import alinmayan_sonuc as AS
from trader_core import etiket_kurallari as EK
from trader_core import telegram as TG
from trader_engine.config import ConfigError, load_cli_config

ROOT = Path(__file__).resolve().parents[1]
CFG = EK.build_config({"rejim": {}})


def test_rejim_karsiti_engeller_ve_izin_verir():
    assert EK.degerlendir("long", "trend_down", CFG)[0][0][0] == EK.REJIM
    assert EK.degerlendir("short", "trend_up", CFG)[0][0][0] == EK.REJIM
    for side, reg in (("long", "trend_up"), ("short", "trend_down"), ("long", "range"), ("short", "volatile"), ("long", "unclear")):
        assert EK.degerlendir(side, reg, CFG)[0] == []


def test_yalniz_rejim_kurali_var_duygu_kalabalik_otomatik_yok():
    assert EK.KURALLAR == (EK.REJIM,) and set(EK.VARSAYILAN) == {"rejim"}
    for gone in ("DUYGU", "KALABALIK", "FEATURE_ANAHTAR", "DOSYA", "guncelle", "durum_oku", "yaz_gece", "kart_verisi", "olay_satiri"):
        assert not hasattr(EK, gone), gone
    for bad in ({"duygu": {"acik": True}}, {"otomatik": {"pencere": 10}}, {"kalabalik": {"acik": True}}):
        with pytest.raises(EK.EtiketConfigHatasi):
            EK.build_config(bad)
    with pytest.raises(TypeError):                                        # duygu parametre olarak bile alinmaz
        EK.degerlendir("long", "range", {"deger": 5}, CFG, 1)


def test_rejim_yoksa_fail_open_ve_kaydedilir():
    tet, yok = EK.degerlendir("long", None, CFG)
    assert tet == [] and yok == [EK.REJIM]


def test_kapali_config_hic_degerlendirmez():
    assert EK.degerlendir("long", "trend_down", {}) == ([], [])
    assert EK.degerlendir("long", "trend_down", EK.build_config({"rejim": {"acik": False}})) == ([], [])


def test_build_config_dogrulama():
    assert EK.build_config(None) == {} and EK.build_config({}) == {}
    assert EK.build_config({"rejim": {}}) == {"rejim": {"acik": True}}
    for bad in ([], {"rejim": 1}, {"rejim": {"acik": "evet"}}, {"rejim": {"x": 1}}, {"yok": {}}):
        with pytest.raises(EK.EtiketConfigHatasi):
            EK.build_config(bad)




def test_paper_config_yalniz_sabit_rejim_kurali():
    raw = json.loads((ROOT / "config" / "engine.paper.json").read_text())
    assert raw["etiket_kurallari"] == {"rejim": {"acik": True}}
    cfg = load_cli_config(ROOT / "config", "learner", "paper")
    assert cfg.etiket_kurallari == {"rejim": {"acik": True}}


@pytest.mark.parametrize("mode", ["live", "testnet"])
def test_live_testnet_etiket_kurallari_yok(mode):
    try:
        cfg = load_cli_config(ROOT / "config", "learner" if mode == "testnet" else "live", mode)
    except ConfigError:
        return
    assert not cfg.etiket_kurallari


def test_eski_satirlarin_adlari_okunur_kalir():
    """Defter semasi degismedi: eski etiket_duygu/etiket_kalabalik satirlari gosterimde adiyla okunur."""
    for kod in (EK.REJIM, "etiket_duygu", "etiket_kalabalik"):
        assert kod in AS.NEDEN_SIRA
    assert TG.ATLAMA_TR[EK.REJIM] and TG.ATLAMA_TR["etiket_duygu"]
    from trader_core import ledger as L
    assert "etiket_duygu" in L._SKIP


def test_otomatik_olay_telegram_satiri_yok():
    st = {"counters": {"steps": 5, "decisions": 3, "enter": 1, "skip:etiket_rejim": 2}, "loop_at": "2026-11-20T12:00:00Z",
          "etiket_kurallari": {"kurallar": {EK.REJIM: {"son_olay": {"ts": "2026-11-20T03:00:00Z", "olay": "kapandi"}}}}}
    satirlar = TG._aktivite_satirlari(st)
    assert any("rejim etiketi ters yöndeydi" in s for s in satirlar)
    assert not any("Etiket kuralı" in s for s in satirlar)
