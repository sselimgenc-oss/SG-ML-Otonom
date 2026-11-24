"""Seans disi kapisi ek testleri: ders kirlenmesi (S1), takvim eskimesi + tek uyari (S4), 2027 FOMC (N1), erken kapanis (N2)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from trader_core import lesson as LS
from trader_engine import seans_disi as SD

from test_emtia_hafta_sonu_gate import BTC, KOD, NVDA, ROOT, XAU, _go, _gecer, _kur, env, u  # noqa: F401,E402


# ------------------------------------------------------------------------------------------------ S1 ders kirlenmesi
def test_s1_seans_disi_atlamalari_ders_olcusune_girmez(monkeypatch):
    """session_closed yazan kapi atlamalari: yalniz `gate:session_closed` (ders parametresi) olcuye girer; gate:seans_disi_* girmez."""
    monkeypatch.setattr(LS, "would_take", lambda params, d: params["a"] == 1)
    mk = lambda i, vr: SimpleNamespace(id=i, final_action="skipped", skip_reason="session_closed", veto_reason=vr)  # noqa: E731
    decs = [mk(1, "gate:session_closed"), mk(2, "gate:seans_disi_hafta_sonu"), mk(3, "gate:seans_disi_tatil"), mk(4, "gate:seans_disi_haber")]
    t = datetime(2026, 12, 1, tzinfo=timezone.utc)
    eff = LS.measure_effect(None, SimpleNamespace(shrink_n=10), {"a": 1}, {"a": 2}, t, t + timedelta(days=1),
                            caps=object(), feats=object(), cf_r={1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5}, trade_rows={}, decisions=decs)
    assert eff.n == 1 and eff.n_added == 1


# ------------------------------------------------------------------------------------------------ S4 takvim eskimesi + tek uyari
def test_s4_takvim_eski_sayac_ve_tek_uyari(tmp_path, caplog):
    SD._UYARILDI.clear()
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"tatiller": [{"tarih": "2026-11-26"}], "olaylar": []}))
    assert SD.yukle(p).son_tarih == datetime(2026, 11, 26).date()
    e = _kur(tmp_path, "paper", takvim=p)
    try:
        with caplog.at_level(logging.WARNING, logger="engine.seans_disi"):
            _go(e, NVDA, u(2026, 12, 8, 15, 0))
            _go(e, XAU, u(2026, 12, 9, 15, 0))
            _go(e, BTC, u(2026, 12, 9, 15, 0))                      # kripto sayilmaz
        assert e.g.counters[SD.SAYAC_TAKVIM_ESKI] == 2
        assert sum("ESKI" in r.getMessage() for r in caplog.records) == 1
        _go(e, NVDA, u(2026, 11, 25, 15, 0))
        assert e.g.counters[SD.SAYAC_TAKVIM_ESKI] == 2              # kapsam icinde sayac artmaz
    finally:
        e.state.close()
        e.led.close()


def test_s4_takvim_yok_bir_kez_uyari(tmp_path, caplog):
    SD._UYARILDI.clear()
    with caplog.at_level(logging.WARNING, logger="engine.seans_disi"):
        assert SD.yukle(tmp_path / "yok.json") is None and SD.yukle(tmp_path / "yok.json") is None
    assert sum("okunamadi" in r.getMessage() for r in caplog.records) == 1


def test_s4_gercek_takvim_2027_sonuna_kadar_kapsar():
    t = SD.yukle()
    assert t is not None and t.son_tarih >= datetime(2027, 12, 24).date()


# ------------------------------------------------------------------------------------------------ N1 FOMC 2027
def test_n1_fomc_2027_tarihleri_ve_durum():
    raw = json.loads((ROOT / "config" / "seans_takvimi.json").read_text())
    f = [o for o in raw["olaylar"] if o["tur"] == "FOMC" and o["ts"].startswith("2027")]
    assert sorted(o["ts"][:10] for o in f) == ["2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28",
                                                "2027-09-15", "2027-10-27", "2027-11-17"]
    assert {o["durum"] for o in f} == {"estimated"}


# ------------------------------------------------------------------------------------------------ N2 erken kapanis
def test_n2_erken_kapanis_2026_11_27_yalniz_hisse(env):
    assert _gecer(_go(env, NVDA, u(2026, 11, 27, 17, 59)))          # 12:59 ET
    o = _go(env, NVDA, u(2026, 11, 27, 18, 0))                      # 13:00 ET
    assert o.code == KOD["tatil"] and o.event.veto_reason == "gate:seans_disi_tatil"
    assert _gecer(_go(env, XAU, u(2026, 11, 27, 18, 0)))            # emtia erken kapanistan etkilenmez
    assert _gecer(_go(env, BTC, u(2026, 11, 27, 18, 0)))
