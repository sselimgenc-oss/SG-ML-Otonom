"""Alinmayan sinyal x sonuc raporu (ml.alinmayan_sonuc.v1; docs/alinmayan-sonuc-spec.md). Sentetik (tmp_path), ag yok, kilitli donem/var/history yok."""
import json

import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from panel_support import Env
from trader_core import alinmayan_sonuc as AS
from trader_core import counterfactual as CF
from trader_core import panel_data as P
from trader_panel.data import PanelData, load_config

UTC = timezone.utc
NOW = datetime(2026, 11, 19, 18, 0, tzinfo=UTC)


@pytest.fixture()
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.close()


def cf(i, gun, neden, r):
    return {"decision_id": i, "skip_reason": neden, "ts": NOW - timedelta(days=gun), "r": r}


def atl(i, gun, neden):
    return {"id": i, "skip_reason": neden, "ts": NOW - timedelta(days=gun)}


CFR = [cf(1, 1, "max_positions", 1.5), cf(2, 2, "max_positions", -1.0), cf(3, 3, "ml_filter", 0.5),
       cf(4, 20, "ml_filter", -1.0), cf(5, 30, "cluster_cap", 2.0)]
ATL = [atl(i, g, n) for i, g, n in [(1, 1, "max_positions"), (2, 2, "max_positions"), (3, 3, "ml_filter"), (4, 20, "ml_filter"),
                                    (5, 30, "cluster_cap"), (6, 1, "max_positions"), (7, 2, "flat_bar"), (8, 25, "flat_bar")]]
ALN = [{"ts": NOW - timedelta(days=1), "r": 2.0}, {"ts": NOW - timedelta(days=4), "r": -1.0}, {"ts": NOW - timedelta(days=40), "r": 1.0}]


def test_sayim_isabet_neden_kirilimi():
    t = AS.topla(CFR, ATL, ALN, NOW)
    d = {r["etiket"]: r for r in t["tablolar"]["neden"]}
    assert list(d) == ["max_positions", "ml_filter", "alınan işlemler"]                  # sabit sira, alinan sonda
    assert d["max_positions"] == {"etiket": "max_positions", "n": 2, "kazanan": 1, "isabet_yuzde": 50.0, "toplam_pnl": 0.5, "ortalama_pnl": 0.25}
    assert d["ml_filter"]["n"] == 1 and d["ml_filter"]["isabet_yuzde"] == 100.0
    assert d["alınan işlemler"]["n"] == 2 and d["alınan işlemler"]["toplam_pnl"] == 1.0
    assert t["tablolar_cozulmedi"] == {"max_positions": 1, "flat_bar": 1}                # cozum yok = uydurma yok, cozulmedi
    allz = {r["etiket"]: r["n"] for r in t["tum_zamanlar"]["neden"]}
    assert allz == {"max_positions": 2, "cluster_cap": 1, "ml_filter": 2, "alınan işlemler": 3}
    assert t["tum_zamanlar_cozulmedi"] == {"max_positions": 1, "flat_bar": 2}      # id 8 (25 gun once, 2026-10-25) kilit ACIK: artik sayilir


def test_acik_kilitte_kilitli_donem_cozulmedi_sayilir(monkeypatch):
    kilit = {"id": 99, "skip_reason": "flat_bar", "ts": CF.HOLDOUT_START + timedelta(days=3)}
    assert AS.topla([], [kilit], [], NOW)["tum_zamanlar_cozulmedi"] == {"flat_bar": 1}      # 23.11.2026: kilit acik
    monkeypatch.setattr(CF, "KILIT_ACIK", False)                                           # kapali kilit: eski davranis
    assert AS.topla([], [kilit], [], NOW)["tum_zamanlar_cozulmedi"] == {}


def test_bos_durum_ve_sema():
    v = AS.olustur([], [], [], NOW)
    assert v["sema"] == "ml.alinmayan_sonuc.v1" and v["birim"] == "R" and v["uretim"] == "2026-11-19T18:00:00Z"
    assert v["tablolar"] == {"neden": []} and v["tum_zamanlar"] == {"neden": []} and "not" in v and "R" in v["not"]
    assert {"sema", "uretim", "tablolar", "tum_zamanlar", "not"} <= set(v)


def test_ct_sutun_uyumu():
    v = AS.olustur(CFR, ATL, ALN, NOW)
    for tb in (v["tablolar"], v["tum_zamanlar"]):
        for r in tb["neden"]:
            assert tuple(r) == AS.SUTUNLAR            # CT rejim_sonuc_v1 satir alanlari (sira dahil)


def test_gecersiz_r_ve_bilinmeyen_neden():
    t = AS.topla([cf(1, 1, "yeni_neden", float("nan")), cf(2, 1, "yeni_neden", 1.0), cf(3, 1, "a_baska", -1.0)], [], [], NOW)
    assert [r["etiket"] for r in t["tablolar"]["neden"]] == ["a_baska", "yeni_neden"] and t["tablolar"]["neden"][1]["n"] == 1


def _depo(tmp_path):
    yol = tmp_path / "var/learner/counterfactual.sqlite"
    yol.parent.mkdir(parents=True)
    st = CF.CounterfactualStore(yol)
    ts = CF._fmt(NOW - timedelta(days=1))
    for i, (m, r, v) in enumerate([("plan", 1.2, 2), ("barrier", 9.0, 2), ("plan", None, 2), ("plan", 7.0, 1)], 1):
        st._db.execute("INSERT INTO cf_outcomes (bot,decision_id,method,pair,side,setup,trigger_tf,skip_reason,decision_ts,planned_entry,planned_stop,"
                       "window_start_ts,window_end_ts,hyp_r_net,exit_reason,computed_at,version) VALUES "
                       "('learner',?,?,'BTC/USDT','long','T1','1h','flat_bar',?,100,99,?,?,?,'target',?,?)",
                       (i, m, ts, ts, ts, r, ts, v))
    st.close()
    return yol


def test_depodan_okuma_yalniz_plan_v2_cozulmus(tmp_path):
    rows = AS._cf_satirlari(_depo(tmp_path), "learner")
    assert [(r["decision_id"], r["r"]) for r in rows] == [(1, 1.2)]
    assert AS._cf_satirlari(tmp_path / "yok.sqlite", "learner") == []


def test_yaz_atomik_ve_defter_yok(tmp_path):
    out = tmp_path / "var/durum/alinmayan_sonuc_v1.json"
    v = AS.yaz_defterden(tmp_path / "yok.sqlite", _depo(tmp_path), "learner", NOW, out)
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d == v and d["tablolar"]["neden"][0]["etiket"] == "flat_bar" and not list(out.parent.glob(".hs-*"))
    led = NS(list_decisions=lambda **k: [NS(id=1, skip_reason="flat_bar", bar_close_ts=NOW - timedelta(days=1)),
                                         NS(id=2, skip_reason="flat_bar", bar_close_ts=NOW - timedelta(days=1))],
             list_closed_trades=lambda limit: [NS(exit_ts=NOW - timedelta(days=1), r_multiple=1.0)], LIST_CLOSED_MAX=10)
    v2 = AS.yaz(led, _depo_yol(tmp_path), "learner", NOW, out)
    assert v2["cozulmedi"]["tablolar"] == {"flat_bar": 1} and v2["tablolar"]["neden"][-1]["etiket"] == "alınan işlemler"
    assert AS.yaz_defterden(tmp_path / "x.sqlite", tmp_path / "y.sqlite", "learner", NOW, tmp_path / "bos" / "a.json")["tablolar"] == {"neden": []}


def _depo_yol(tmp_path):
    return tmp_path / "var/learner/counterfactual.sqlite"


def test_panel_karti(env):
    pd_ = PanelData(load_config(env.cfg_path), clock=lambda: NOW)
    assert pd_.alinmayansonuc()["ok"] and pd_.alinmayansonuc()["neden"] == "dosya_yok"
    p = env.root / "var/durum/alinmayan_sonuc_v1.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(AS.olustur(CFR, ATL, ALN, NOW)), encoding="utf-8")
    r = pd_.alinmayansonuc()
    assert r["ok"] and r["var"] and r["birim"] == "R" and r["pencere_gun"] == 7 and tuple(r["tablolar"]["neden"][0]) == AS.SUTUNLAR
    assert r["cozulmedi"]["tablolar"]["flat_bar"] == 1
    p.write_text(json.dumps(AS.olustur([], [], [], NOW)), encoding="utf-8")
    assert pd_.alinmayansonuc()["neden"] == "kayit_yok"
    p.write_text("{bozuk", encoding="utf-8")
    assert pd_.alinmayansonuc()["var"] is False
    p.write_text(json.dumps({"sema": "x"}), encoding="utf-8")
    assert pd_.alinmayansonuc()["neden"] == "sema_yanlis"
    assert P.alinmayan_sonuc_view("")["var"] is False
