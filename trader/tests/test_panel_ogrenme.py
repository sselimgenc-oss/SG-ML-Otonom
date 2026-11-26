"""Pano 'Ogrenme' karti ve OGRENME tablosu (24.11 kullanici karari: pano ogrenme karti): kol x zaman dilimi, model kollari."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from panel_support import NOW, ROOT, STD_LEARNER, Env, mkledger
from trader_core import panel_pano as PP
from trader_panel.data import PanelData, load_config

UTC = timezone.utc


def _view(tmp_path, specs=STD_LEARNER, arms=None, kapali=None):
    lp = tmp_path / "learner.sqlite"
    mkledger(str(lp), "learner", specs)
    if kapali:
        (tmp_path / "arms_off.json").write_text(json.dumps({"arms": {a: {"state": "closed"} for a in kapali}}), encoding="utf-8")
    ctx = PP.Ctx(str(lp), "learner")
    return PP.ogrenme_view(str(lp), ctx, NOW, arms=arms or [])


def test_kol_satirlari_dinamik_ve_sayilar(tmp_path):
    v = _view(tmp_path, arms=["T1@4h", "FORM9@1h"], kapali=["T1@4h"])
    by = {r["arm"]: r for r in v["kollar"]}
    assert {"R1@1h", "T1@4h", "FORM9@1h"} <= set(by) and not any(a.startswith("M1@") for a in by)        # ayar + defter + yeni kimlik
    r1 = by["R1@1h"]                                       # STD_LEARNER: 6 kapanan, 4 kazanc 2 kayip (hepsi R1@1h; biri acik)
    assert r1["n"] == 5 and r1["kazanma"] == 60.0 and r1["durum"] == "acik" and "carpan" not in r1
    assert r1["net_r"] > 0
    assert by["T1@4h"]["durum"] == "kapali" and by["T1@4h"]["n"] == 0 and by["T1@4h"]["net_r"] is None
    assert by["FORM9@1h"]["kol"] == "FORM9" and by["FORM9@1h"]["zd"] == "1 saat"
    z = v["ozet"]
    assert z["kapali"] == 1 and z["acik"] + z["kapali"] == z["toplam"] == len(v["kollar"])
    assert [r["arm"] for r in z["en_iyi"]] == ["R1@1h"] and z["en_kotu"] == []             # tek olculen kol iki listede tekrar etmez


def test_zarardaki_kol_kucultulmez_giris_tavani_yok(tmp_path):
    zarar = [(False, True, datetime(2026, 11, 14, 1 + i, tzinfo=UTC)) for i in range(5)]
    v = _view(tmp_path, specs=zarar)
    r = {x["arm"]: x for x in v["kollar"]}["R1@1h"]
    assert r["n"] == 5 and r["kazanma"] == 0.0 and r["net_r"] < 0
    assert r["durum"] == "acik" and "carpan" not in r         # 25.11: performansa gore boyut kucultme/karantina yok
    assert "son_ders" not in r                                # ders sistemi kaldirildi (25.11)


def test_pano_govdesinde_ogrenme_ve_arayuz(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("ogr"))
    try:
        p = PanelData(load_config(e.cfg_path), clock=lambda: NOW).pano("learner")
    finally:
        e.close()
    o = p["ogrenme"]
    assert o is not None and {"ozet", "kollar"} <= set(o) and "modeller" not in o
    assert all({"arm", "kol", "zd", "n", "net_r", "kazanma", "durum"} <= set(r) for r in o["kollar"])
    js = (ROOT / "src/trader_panel/static/panel.js").read_text(encoding="utf-8")
    for s in ("ogrenmeOzetKart", "ogrenmeTablolari", "'og_kol'", "p.ogrenme", "Ders kapattı"):
        assert s in js
    assert "Kademeli küçültme" not in js and "Karantinada kol" not in js
