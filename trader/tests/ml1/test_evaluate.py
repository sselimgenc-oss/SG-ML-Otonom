"""ML1 degerlendirme: olay basina tek pozisyon, rapor, 'edge yok' gecerli sonuc."""
from __future__ import annotations

import json

import pandas as pd
from test_train_destek import sentetik_tablo

from trader_ml.ml1 import evaluate as EV
from trader_ml.ml1 import train as TR


def _mini() -> pd.DataFrame:
    t = pd.to_datetime(["2022-01-01 00:00", "2022-01-01 01:00", "2022-01-01 02:00", "2022-01-02 00:00"], utc=True)
    return pd.DataFrame({"event_id": ["a", "a", "a", "b"], "decision_ts": t, "arm_id": ["Z", "Y", "X", "Q"],
                         "p": [0.2, 0.9, 0.9, 0.1], "r_net": [1.0, -1.0, 2.0, 0.5], "tf": "1h", "group": "G"})


def test_olay_basina_tek_pozisyon():
    d = _mini()
    best = EV.select_one_per_event(d, "p")
    assert len(best) == 2 and best.loc[best["event_id"] == "a", "arm_id"].iloc[0] == "Y"   # esitlikte en erken
    first = EV.select_one_per_event(d, None)
    assert len(first) == 2 and first.loc[first["event_id"] == "a", "arm_id"].iloc[0] == "Z"
    s = EV.summarize(best)
    assert s["trades"] == 2 and s["total_R"] == -0.5 and s["win_pct"] == 50.0
    assert EV.summarize(d.iloc[0:0])["trades"] == 0
    assert EV.select_one_per_event(d.iloc[0:0], "p").empty


def test_edge_yok_raporlanir_cokmez(tmp_path):
    d = sentetik_tablo(4000, seed=11, sinyal=0.0, p_kazan=0.42)       # saf gurultu, ortalama R < 0
    res = TR.run(d, holdout_months=3, test_months=3, min_train_months=6, min_trades=20)
    rep = EV.build_report(res)
    assert rep["verdict"]["verdict"] in ("no_edge", "insufficient")
    assert rep["verdict"]["reasons"]
    jp, mp = EV.write_report(rep, tmp_path)
    assert json.loads(jp.read_text())["verdict"]["verdict"] == rep["verdict"]["verdict"]
    md = mp.read_text()
    assert "no_edge" in md or "insufficient" in md
    assert rep["oos"]["baseline_first_per_event"]["mean_R"] < 0
    assert len(rep["oos"]["calibration_deciles"]) == 10 and rep["data"]["censored_share"] == 0.0


def test_sinyalli_veri_edge_adayi_ve_kirilimlar():
    d = sentetik_tablo(6000, seed=5, sinyal=2.0)
    res = TR.run(d, holdout_months=3, test_months=3, min_train_months=6, min_trades=20)
    rep = EV.build_report(res)
    o = rep["oos"]
    assert o["ml"]["mean_R"] > o["baseline_first_per_event"]["mean_R"]
    assert {r["tf"] for r in o["by_tf"]["ml"]} <= {"1h", "4h"} and o["by_year"]["ml"] and o["by_group"]["ml"]
    assert set(o["fixed_thresholds"]) == {"0.50", "0.55", "0.60"}
    assert rep["holdout"]["n_candidates"] > 0
    assert "Holdout" in EV.render_markdown(rep)


def test_censored_pay_ayri_ve_veri_yetersiz_cokmez():
    d = sentetik_tablo(1200, seed=2, sinyal=1.0)
    d.loc[d.index[:100], "censored"] = 1
    d.loc[d.index[100:130], "status"] = "no_data"
    res = TR.run(d, holdout_months=3, test_months=3, min_train_months=6, min_trades=20)
    assert abs(res["data"]["censored_share"] - 100 / 1170) < 1e-9 and res["data"]["n_labeled"] == 1070
    tiny = TR.run(d.iloc[:30], min_trades=200)                       # cok kucuk: karar 'insufficient', hata yok
    rep = EV.build_report(tiny)
    assert rep["verdict"]["verdict"] == "insufficient"
    EV.render_markdown(rep)
    empty = TR.run(d.iloc[0:0])
    assert EV.build_report(empty)["verdict"]["verdict"] == "insufficient"
