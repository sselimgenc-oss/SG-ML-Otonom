"""Tur 1 olcum raporu: onayli rapor duzeltmeleri ve yeni bolumler (sentetik veriyle)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "paket"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trader_reports import tur1_olcum as T  # noqa: E402
from test_tur1_olcum import H, NOW, T0, iso, market, mk  # noqa: E402


# ---------------------------------------------------------------- Duzeltme 1: canli aile paketi semasi
def test_yon_onemi_canli_aile_paketi_ozellikler_ve_side_long(tmp_path):
    from ortak_ogrenme import filtre
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, 3))
    side = (rng.random(200) > 0.5).astype(float)
    X[:, 1] = side
    y = (side * 2.0 + X[:, 0] * 0.1 + rng.normal(0, 0.3, 200) > 1.0).astype(float)
    model = filtre.fit_logistic(X, y)
    md = tmp_path / "models" / "ortak_filtre"
    md.mkdir(parents=True)
    pkg = {"meta": {"ozellikler": ["atr_ratio", "side_long", "stop_dist_pct"]}, "model": model, "esik": 0.4}
    (md / "aile_T1.json").write_text(json.dumps(pkg))
    (md / "aile_R1.json").write_text(json.dumps({"meta": {"ozellikler": ["atr_ratio"]}, "model": {"kind": "logistic", "coef": [1.0]}}))
    eski = md / "eski_kol"
    eski.mkdir()
    (eski / "T1@1h.json").write_text(json.dumps(pkg))
    d = T.yon_ozelligi_onemi(tmp_path / "models")
    assert d["durum"] == "ok"
    p = {r["paket"]: r for r in d["paketler"]}
    assert set(p) == {"aile_T1.json", "aile_R1.json"}          # eski_kol taranmaz
    t1 = p["aile_T1.json"]
    c = np.abs(model["coef"])
    assert t1["sema"] == "ozellikler" and t1["ozellik"] == "side_long" and t1["sira"] == 1
    assert t1["onem_payi"] == pytest.approx(c[1] / c.sum()) and t1["katsayi"] == pytest.approx(model["coef"][1])
    assert p["aile_R1.json"]["durum"] == "ozellik_listede_yok"


def test_yon_onemi_arastirma_semasi_hala_calisir(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"meta": {"features": ["f_a", "f_side_sign"]},
                                                "model": {"kind": "logistic", "coef": [1.0, 3.0]}}))
    r = T.yon_ozelligi_onemi(tmp_path)["paketler"][0]
    assert r["sema"] == "features" and r["ozellik"] == "f_side_sign" and r["onem_payi"] == pytest.approx(0.75)
