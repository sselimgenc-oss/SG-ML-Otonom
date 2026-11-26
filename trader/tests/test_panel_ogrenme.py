"""Pano 'Ogrenme' karti ve OGRENME tablosu (24.11 kullanici karari: pano ogrenme karti): kol x zaman dilimi, model kollari."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from panel_support import NOW, ROOT, STD_LEARNER, Env, mkledger
from trader_core import panel_pano as PP
from trader_panel.data import PanelData, load_config

UTC = timezone.utc


def _view(tmp_path, specs=STD_LEARNER, arms=None, kapali=None, m1=None):
    lp = tmp_path / "learner.sqlite"
    mkledger(str(lp), "learner", specs)
    if kapali:
        (tmp_path / "arms_off.json").write_text(json.dumps({"arms": {a: {"state": "closed"} for a in kapali}}), encoding="utf-8")
    ctx = PP.Ctx(str(lp), "learner")
    return PP.ogrenme_view(str(lp), ctx, NOW, arms=arms or [], m1_dizinleri=[m1 or tmp_path / "yok_m1"])


def test_kol_satirlari_dinamik_ve_sayilar(tmp_path):
    v = _view(tmp_path, arms=["T1@4h", "FORM9@1h", "M1@1h"], kapali=["T1@4h"])
    by = {r["arm"]: r for r in v["kollar"]}
    assert {"R1@1h", "T1@4h", "FORM9@1h", "M1@1h", "M1@15m", "M1@1d"} <= set(by)        # ayar + defter + yeni kimlik + model kollari
    r1 = by["R1@1h"]                                       # STD_LEARNER: 6 kapanan, 4 kazanc 2 kayip (hepsi R1@1h; biri acik)
    assert r1["n"] == 5 and r1["kazanma"] == 60.0 and r1["durum"] == "acik" and r1["carpan"] == 1.0
    assert r1["net_r"] > 0
    assert by["T1@4h"]["durum"] == "karantina" and by["T1@4h"]["n"] == 0 and by["T1@4h"]["net_r"] is None
    assert by["FORM9@1h"]["kol"] == "FORM9" and by["FORM9@1h"]["zd"] == "1 saat"
    z = v["ozet"]
    assert z["karantina"] == 1 and z["acik"] + z["kucultulmus"] + z["karantina"] == z["toplam"] == len(v["kollar"])
    assert [r["arm"] for r in z["en_iyi"]] == ["R1@1h"] and z["en_kotu"] == []             # tek olculen kol iki listede tekrar etmez


def test_kucultulmus_durum(tmp_path):
    zarar = [(False, True, datetime(2026, 11, 14, 1 + i, tzinfo=UTC)) for i in range(5)]
    v = _view(tmp_path, specs=zarar)
    r = {x["arm"]: x for x in v["kollar"]}["R1@1h"]
    assert r["n"] == 5 and r["kazanma"] == 0.0 and r["net_r"] < 0
    assert r["carpan"] == 0.5 and r["durum"] == "kucultulmus" and r["durum_ad"] == "Küçültülmüş"
    assert "son_ders" not in r                             # ders sistemi kaldirildi (25.11)
    assert v["ozet"]["kucultulmus"] == 1 and v["ozet"]["en_kotu"] == [] and v["ozet"]["en_iyi"][0]["arm"] == "R1@1h"


def test_model_kollari_paket_zamani_ve_bilinmiyor(tmp_path):
    m1 = tmp_path / "m1"
    m1.mkdir()
    (m1 / "M1@1h.json").write_text(json.dumps({"meta": {"created_at": "2026-11-14T06:00:00+00:00"}}), encoding="utf-8")
    (m1 / "M1@15m.json").write_text("{bozuk", encoding="utf-8")
    v = _view(tmp_path, arms=["M1@1h", "M1@4h"], m1=m1)
    m = {x["arm"]: x for x in v["modeller"]}
    assert m["M1@1h"]["egitim"] == "14.11 09:00" and m["M1@1h"]["yas_gun"] == pytest.approx(2.5)        # TSI = UTC+3
    assert m["M1@15m"]["paket"] == "okunamadi" and m["M1@15m"]["egitim"] is None and m["M1@15m"]["yas_gun"] is None
    assert m["M1@1d"]["paket"] == "yok" and m["M1@1d"]["egitim"] is None and m["M1@4h"]["egitim"] is None
    assert not any(a.startswith(("R1", "T1")) for a in m)                                    # yalniz model kollari
    assert m["M1@1h"]["bugun_aday"] == 0 and m["M1@1h"]["bugun_giris"] == 0


def test_bugun_aday_giris_sayisi(tmp_path, monkeypatch):
    import panel_support as PS
    gercek = PS.L

    class _M1Defter:                                      # yalniz fikstur kararlarinin kolunu M1 yapar; defter modulu aynen kalir
        def __getattr__(self, ad):
            return getattr(gercek, ad)

        @staticmethod
        def DecisionEvent(**kw):  # noqa: N802
            return gercek.DecisionEvent(**{**kw, "setup": "M1"})
    monkeypatch.setattr(PS, "L", _M1Defter())
    bugun = [(True, True, datetime(2026, 11, 16, 6 + i, tzinfo=UTC)) for i in range(2)]              # TSI 16.11 (NOW = 21:00 TSI)
    v = _view(tmp_path, specs=bugun + [(True, True, datetime(2026, 11, 15, 6, tzinfo=UTC))])
    m = {x["arm"]: x for x in v["modeller"]}
    assert m["M1@1h"]["bugun_aday"] == 2 and m["M1@1h"]["bugun_giris"] == 2                         # dunku karar sayilmaz
    assert {x["arm"]: x for x in v["kollar"]}["M1@1h"]["n"] == 3


def test_pano_govdesinde_ogrenme_ve_arayuz(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("ogr"))
    try:
        p = PanelData(load_config(e.cfg_path), clock=lambda: NOW).pano("learner")
    finally:
        e.close()
    o = p["ogrenme"]
    assert o is not None and {"ozet", "kollar", "modeller"} <= set(o)
    assert all({"arm", "kol", "zd", "n", "net_r", "kazanma", "carpan", "durum"} <= set(r) for r in o["kollar"])
    js = (ROOT / "src/trader_panel/static/panel.js").read_text(encoding="utf-8")
    for s in ("ogrenmeOzetKart", "ogrenmeTablolari", "'og_kol'", "'og_model'", "p.ogrenme", "Karantinada kol", "bilinmiyor", "Kademeli küçültme"):
        assert s in js
