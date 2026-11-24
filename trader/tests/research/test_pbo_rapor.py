"""research/pbo_rapor.py: yalniz sentetik getiri matrisleri / defterler (tmp_path); gercek veri okunmaz."""
from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_engine.holdout import HOLDOUT, BacktestArgError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pbo_rapor", ROOT / "research" / "pbo_rapor.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def _noise(T=400, N=10, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(rng.normal(0, 1, (T, N)), index=pd.date_range("2024-01-01", periods=T, freq="D", tz="UTC"),
                        columns=[f"c{i}" for i in range(N)])


def test_skill_matrix_has_low_pbo_and_noise_is_not_low():
    skill = _noise(seed=2)
    skill["c3"] += 0.4                                   # kalici ustunluk: IS kazananinin OOS'ta da iyi kalmasi beklenir
    r = P.family_stats(skill)
    assert r["durum"] == "tamam" and r["pbo"] < 0.2 and r["en_iyi_yapilandirma"] == "c3"
    n = P.family_stats(_noise(N=20, seed=3))
    assert n["pbo"] > 0.2 and n["pbo"] > r["pbo"]
    assert 0 <= n["dsr"] <= 1


def test_reproducible_and_trial_count_includes_constant_columns():
    M = _noise(seed=4)
    M["const"] = 0.0
    a, b = P.family_stats(M), P.family_stats(M)
    assert a == b
    assert a["n_yapilandirma"] == 11 and a["n_kullanilan"] == 10
    # daha fazla deneme sayisi -> DSR azalir
    more = P.family_stats(M, n_trials_total=200)
    assert more["dsr"] <= a["dsr"] and more["pbo"] == a["pbo"]


def test_unusable_family_reported_not_invented():
    one = _noise(N=1)
    assert P.family_stats(one)["durum"] == "hesaplanamadi"
    short = _noise(T=10, N=4)
    assert P.family_stats(short)["durum"] == "hesaplanamadi"
    assert P.family_stats(pd.DataFrame({"a": np.zeros(100), "b": np.zeros(100)}))["durum"] == "hesaplanamadi"


def _trades(setup_n: dict, seed=0, extra_after=None):
    rng = np.random.default_rng(seed)
    rows = []
    for setup, n in setup_n.items():
        for _ in range(n):
            x = P.RULE_WINDOW[0] + pd.Timedelta(hours=int(rng.integers(0, 24 * 365)))
            rows.append({"setup": setup, "exit_ts": x.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "r_multiple": float(rng.normal(0, 1))})
    if extra_after is not None:
        rows.append({"setup": "T1", "exit_ts": extra_after.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "r_multiple": 99.0})
    rows.append({"setup": "T1", "exit_ts": "", "r_multiple": 5.0})            # acik pozisyon: cikis yok
    return pd.DataFrame(rows)


def test_rule_series_window_and_holdout_cut(monkeypatch):
    import trader_engine.holdout as _H
    monkeypatch.setattr(_H, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    t = _trades({"T1": 200, "R1": 40}, extra_after=pd.Timestamp(HOLDOUT[0]) + timedelta(days=2))
    s = P.rule_series(t, P.RULE_WINDOW)
    assert set(s) == {"T1", "R1"} and len(s["T1"]) == 365
    assert s["T1"].abs().max() < 50                      # 99 R'lik pencere disi / holdout satiri girmedi, bos cikis girmedi
    with pytest.raises(BacktestArgError):                # pencere kilitli donemle kesisirse reddedilir
        P.rule_series(t, (pd.Timestamp(HOLDOUT[0]) - timedelta(days=5), pd.Timestamp(HOLDOUT[1])))


def _mk_run(bt: Path, name: str, trades: pd.DataFrame, period):
    d = bt / name
    d.mkdir(parents=True)
    trades.to_csv(d / "trades.csv", index=False)
    (d / "meta.json").write_text(json.dumps({"id": name, "period": period, "trigger_tf": "1h"}))


def test_build_end_to_end_synthetic(tmp_path):
    bt = tmp_path / "bt"
    lo, hi = P.RULE_WINDOW[0].strftime("%Y-%m-%dT00:00:00.000Z"), P.RULE_WINDOW[1].strftime("%Y-%m-%dT00:00:00.000Z")
    for i in range(4):
        _mk_run(bt, f"run{i}", _trades({"T1": 150, "R1": 30}, seed=i), [lo, hi])
    _mk_run(bt, "kisa", _trades({"T1": 10}), ["2025-11-01T00:00:00.000Z", "2026-04-30T00:00:00.000Z"])      # pencereyi kapsamaz
    arms = ["T1@1h", "R1@1h", "T1@4h", "S1@1h"]
    res = P.build(bt, arms)
    names = {f["aile"]: f for f in res["aileler"]}
    assert {"Kural T1", "Kural R1", "TUM KUME"} <= set(names) and not any(k.startswith("ML ") for k in names)   # 24.11: ML filtre aileleri silindi
    assert names["Kural T1"]["n_yapilandirma"] == 4 and names["Kural T1"]["durum"] == "tamam"
    assert {a["kurulum"]: a["kayit"] for a in res["kurulumlar"]} == {"T1@1h": "var", "R1@1h": "var", "T1@4h": "yok", "S1@1h": "yok"}
    assert [s["kosu"] for s in res["atlanan_defterler"]] == ["kisa"]
    assert P.build(bt, arms) == res                     # yeniden uretilebilir
    md = P.render_md(res)
    assert "S1@1h" in md and "Eksik kalan aileler" in md


def test_cli_files_written_only_where_configured():
    # modul sabitleri: cikti yollari spesifikasyondaki dosyalar
    assert P.OUT_MD == ROOT / "docs" / "ml" / "pbo-raporu.md"
    assert P.OUT_JSON == ROOT / "research" / "holdout" / "pbo_ozet.json"
