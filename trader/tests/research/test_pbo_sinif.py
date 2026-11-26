"""research/pbo_sinif.py: yalniz sentetik matrisler (tmp_path); gercek veri / holdout okunmaz."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pbo_sinif", ROOT / "research" / "pbo_sinif.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

END = pd.Timestamp("2025-06-30", tz="UTC")


def _mat(T, start_pad=0, N=6, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(END - pd.Timedelta(days=T + start_pad - 1), END, freq="D")
    X = rng.normal(0, 1, (len(idx), N))
    X[:start_pad] = 0.0
    return pd.DataFrame(X, index=idx, columns=[f"c{i}" for i in range(N)])


def test_n_splits_rule():
    assert S.n_splits_for(128) == 16 and S.n_splits_for(127) == 8 and S.n_splits_for(64) == 8 and S.n_splits_for(63) is None


def test_leading_zero_days_trimmed_and_rule_applied():
    r = S.class_stats(_mat(200, start_pad=300), END)
    assert r["T"] == 200 and r["n_splits"] == 16 and r["durum"] == "tamam"
    r8 = S.class_stats(_mat(100, start_pad=50), END)
    assert r8["T"] == 100 and r8["n_splits"] == 8 and r8["durum"] == "tamam"
    short = S.class_stats(_mat(40, start_pad=500), END)
    assert short["durum"] == "hesaplanmadi" and short["T"] == 40 and "pbo" not in short


def test_all_zero_and_trial_count():
    z = pd.DataFrame(0.0, index=_mat(300).index, columns=["a", "b", "c"])
    assert S.class_stats(z, END)["durum"] == "hesaplanmadi"
    M = _mat(300)
    M["const"] = 0.0
    r = S.class_stats(M, END)
    assert r["n_yapilandirma"] == 7 and r["n_kullanilan"] == 6
    assert r == S.class_stats(M, END)                                   # seed sabit


def test_pair_classes_from_config(tmp_path):
    cfg = {"pairs": ["A/USDT", "B/USDT", "C/USDT"], "clusters": {"kripto_buyuk": {"pairs": ["A/USDT"]}, "hisse": {"pairs": ["B/USDT"]},
                                                                  "hisse_teknoloji": {"pairs": ["B/USDT"]}, "metal": {"pairs": ["C/USDT"]}}}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(cfg))
    assert S.pair_classes(p) == {"A/USDT": "kripto", "B/USDT": "hisse", "C/USDT": "emtia"}
    cfg["pairs"].append("D/USDT")
    p.write_text(json.dumps(cfg))
    with pytest.raises(ValueError):
        S.pair_classes(p)


def test_real_config_has_14_pairs_in_three_classes():   # 26.11 sahip karari: evren 14 cift sabit
    pc = S.pair_classes()
    assert len(pc) == 14 and {v for v in pc.values()} == set(S.CLASSES)
    assert sum(v == "kripto" for v in pc.values()) == 5 and sum(v == "emtia" for v in pc.values()) == 2


def test_section_replaced_idempotently(tmp_path):
    f = tmp_path / "r.md"
    f.write_text("# x\n\nbody\n")
    S.write_md(S.SECTION + "\n\nA\n", f)
    S.write_md(S.SECTION + "\n\nB\n", f)
    t = f.read_text()
    assert t.count(S.SECTION) == 1 and "B" in t and "A\n" not in t.split(S.SECTION)[1] and t.startswith("# x\n\nbody")
