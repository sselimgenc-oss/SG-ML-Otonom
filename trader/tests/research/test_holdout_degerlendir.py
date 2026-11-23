"""research/holdout_degerlendir.py: TAMAMEN sentetik (tmp_path'te sahte muhur + sahte feather). Gercek veri/muhur okunmaz.
Holdout tarihleri trader_engine.holdout.HOLDOUT'tan turetilir (tarih dizesi yok)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core.stats import deflated_sharpe, return_moments
from trader_engine.holdout import HOLDOUT, BacktestArgError, check_holdout

ROOT = Path(__file__).resolve().parents[2]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


D = _load("holdout_degerlendir", "research/holdout_degerlendir.py")
MUHUR = _load("muhur_ref_for_tests", "research/holdout_muhur.py")
LO, HI = pd.Timestamp(HOLDOUT[0]), pd.Timestamp(HOLDOUT[1])
PAIR = "AAA/USDT"
ADAY = "T1@4h"


def _write_feather(d: Path, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(LO - pd.Timedelta(days=700), HI - pd.Timedelta(hours=4), freq="4h", tz="UTC")
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx))))
    o = np.concatenate(([100.0], c[:-1]))
    hi = np.maximum(o, c) * 1.002
    lo = np.minimum(o, c) * 0.998
    df = pd.DataFrame({"date": idx.astype("datetime64[ms, UTC]"), "open": o, "high": hi, "low": lo, "close": c, "volume": 1.0})
    d.mkdir(parents=True, exist_ok=True)
    df.to_feather(d / "AAA_USDT_USDT-4h-futures.feather")


@pytest.fixture
def env(tmp_path):
    hist = tmp_path / "hist"
    _write_feather(hist)
    muhur = tmp_path / "muhur.json"
    MUHUR.muhurle(hist, muhur)
    ozet = tmp_path / "pbo_ozet.json"
    ozet.write_text(json.dumps({"aileler": [{"aile": "TUM KUME", "n_yapilandirma": 712}]}), encoding="utf-8")
    return {"hist": hist, "muhur": muhur, "ozet": ozet, "out": tmp_path / "out"}


def _args(env, aday=ADAY):
    return ["--aday-kumesi", aday, "--history-dir", str(env["hist"]), "--muhur", str(env["muhur"]), "--out-dir", str(env["out"]),
            "--pbo-ozet", str(env["ozet"]), "--pairs", PAIR]


def _open(env, aday=ADAY):
    MUHUR.ac(aday, "test", env["muhur"])


@pytest.fixture
def no_data(monkeypatch):
    """Kapi reddinde HICBIR degerlendirme okumasi olmamali."""
    def boom(*a, **k):
        raise AssertionError("veri okundu")
    monkeypatch.setattr(D, "_oku", boom)
    monkeypatch.setattr(D, "islem_uret", boom)
    monkeypatch.setattr(D.pd, "read_feather", boom)   # kapi 1-2 dosya hash'ine bile girmez


def _no_outputs(env):
    assert not env["out"].exists() or not list(env["out"].iterdir())


# ------------------------------------------------------------------------------------------------ kapilar
def test_closed_seal_refuses_without_reading(env, no_data):
    assert D.main(_args(env)) == 2
    _no_outputs(env)


def test_wrong_candidate_set_refuses_without_reading(env, no_data):
    _open(env, "R1@4h")
    assert D.main(_args(env, "T1@4h")) == 2
    assert D.main(_args(env, "T1@4h,R1@4h")) == 2
    _no_outputs(env)


def test_missing_seal_refuses(env, no_data):
    env["muhur"].unlink()
    assert D.main(_args(env)) == 2


def test_hash_mismatch_refuses_before_evaluation(env, monkeypatch):
    _open(env)
    df = pd.read_feather(env["hist"] / "AAA_USDT_USDT-4h-futures.feather")
    i = int(np.flatnonzero(pd.DatetimeIndex(df["date"]) >= LO)[3])
    df.loc[i, "close"] = df.loc[i, "close"] * 1.01
    df.to_feather(env["hist"] / "AAA_USDT_USDT-4h-futures.feather")
    monkeypatch.setattr(D, "_oku", lambda *a, **k: (_ for _ in ()).throw(AssertionError("degerlendirme okumasi")))
    assert D.main(_args(env)) == 2
    _no_outputs(env)


def test_real_history_with_foreign_seal_refused(env, no_data):
    _open(env)
    with pytest.raises(D.Red):
        D.degerlendir(D.parse_aday(ADAY), history_dir=D.REAL_HISTORY, muhur_path=env["muhur"], out_dir=env["out"], pairs=[PAIR], pbo_ozet=env["ozet"])


def test_parse_aday():
    assert D.parse_aday("T1@4h, R1@1d") == ("R1@1d|def", "T1@4h|def")
    assert D.parse_aday("T1@4h|def,T1@4h") == ("T1@4h|def",)
    for bad in ("", "X9@4h", "T1@15m", "T1@4h|nope=1"):
        with pytest.raises(D.Red):
            D.parse_aday(bad)


# ------------------------------------------------------------------------------------------------ hesap
def test_open_seal_exact_metrics_on_synthetic_trades(env, monkeypatch):
    _open(env)
    hold_day = LO.floor("D")
    ns = lambda d, h=12: int((hold_day + pd.Timedelta(days=d, hours=h)).value)
    pre_ns = int((LO - pd.Timedelta(days=10)).value)

    def fake(history_dir, pair, setup, tf, tag, hi, entry_from):
        if entry_from is None:                                    # holdout oncesi
            return {k: [(pre_ns, 1.0), (pre_ns + 86_400 * 10**9, 2.0), (pre_ns + 2 * 86_400 * 10**9, -1.0)] for k in ("f1|s0", "f1|s5", "f2|s0", "f2|s5")}
        t = [(ns(0), 2.0), (ns(0, 15), -1.0), (ns(1), -3.0), (ns(2), 0.5)]
        return {"f1|s0": t, "f1|s5": t, "f2|s0": t, "f2|s5": [(ns(0), -1.0)]}
    monkeypatch.setattr(D, "islem_uret", fake)
    assert D.main(_args(env)) == 0
    o = json.loads((env["out"] / "degerlendirme_T1_4h_def.json").read_text(encoding="utf-8"))
    p = o["kume"]["f1|s5"]
    h = p["holdout"]
    days = np.zeros(184)
    days[0], days[1], days[2] = 1.0, -3.0, 0.5
    assert h["gun"] == 184 and h["n_islem"] == 4
    assert h["toplam_r"] == pytest.approx(-1.5)
    sd = days.std(ddof=1)
    assert h["sharpe_gun"] == pytest.approx(days.mean() / sd)
    assert h["sharpe_yillik"] == pytest.approx(days.mean() / sd * 365 ** 0.5)
    cum = np.concatenate(([0.0], np.cumsum(days)))
    assert h["max_dd_r"] == pytest.approx((np.maximum.accumulate(cum) - cum).max())
    assert h["isabet"] == pytest.approx(0.5)
    sk, ku = return_moments(days)
    assert p["dsr"] == pytest.approx(deflated_sharpe(days.mean() / sd, 184, sk, ku, n_trials=712))
    assert o["n_trials"] == 712
    pre = p["holdout_oncesi"]
    assert pre["toplam_r"] == pytest.approx(2.0) and pre["n_islem"] == 3
    assert p["dusus_orani_sharpe"] is not None                         # once > 0 -> tanimli
    assert p["dusus_orani_sharpe"] == pytest.approx(1 - h["sharpe_gun"] / pre["sharpe_gun"])
    g = o["gecme_olcutu"]
    assert g["kontroller"] == {"H1_sharpe_gt_0": False, "H2_dsr_ge_0_95": False, "H3_stres_toplam_r_gt_0": False}
    assert g["sonuc_oneri"] == "KALDI" and g["baglayici"] is False
    assert (env["out"] / "degerlendirme_T1_4h_def.md").read_text(encoding="utf-8").startswith("# Holdout degerlendirme")
    assert json.loads(env["muhur"].read_text(encoding="utf-8"))["acildi"] is True
    assert D.main(_args(env)) == 2                                     # tek seferlik: cikti var


def test_pass_branch_and_undefined_drop_ratio():
    days_h = pd.date_range(LO.floor("D"), periods=60, freq="D")
    days_p = pd.date_range(LO.floor("D") - pd.Timedelta(days=60), periods=60, freq="D")
    rng = np.random.default_rng(1)
    th = [(int(d.value), float(r)) for d, r in zip(days_h, rng.normal(0.8, 0.5, 60))]
    tp = [(int(d.value), -1.0) for d in days_p]                        # once: Sharpe < 0 -> dusus tanimsiz
    z = lambda t: {c: t for c in ("f1|s0", "f1|s5", "f2|s0", "f2|s5")}
    r = D.hesapla({"T1@4h|def": z(tp)}, {"T1@4h|def": z(th)}, days_p, days_h, 1)
    assert r["kume"]["f1|s5"]["dusus_orani_sharpe"] is None
    assert r["gecme_olcutu"]["sonuc_oneri"] == "GECTI"


def test_pipeline_runs_on_synthetic_bars(env):
    """Sahte mum verisinde gercek simulator hattini (arm_harness) uctan uca calistirir; seri/metrik tutarli."""
    _open(env)
    assert D.main(_args(env)) == 0
    o = json.loads((env["out"] / "degerlendirme_T1_4h_def.json").read_text(encoding="utf-8"))
    for c, v in o["kume"].items():
        assert v["holdout"]["gun"] == 184 and v["holdout_oncesi"]["gun"] > 300
        assert v["holdout"]["n_islem"] >= 0
    assert o["atlanan_ciftler_holdout"] == []


def test_hash_equals_reference_module(env):
    ref = {f["dosya"]: f for f in MUHUR.compute(env["hist"])}
    mine = {p.name: D._hash_file(p) for p in env["hist"].glob("*.feather")}
    assert mine == ref
    ok, diff = D.hash_esit(env["hist"], json.loads(env["muhur"].read_text(encoding="utf-8")))
    assert ok and not diff


# ------------------------------------------------------------------------------------------------ kilit statigi
def test_central_lock_open_and_real_seal_opened(monkeypatch):
    """23.11.2026 kullanici karari: kilit ACIK (KILIT_ACIK) ve gercek muhur acildi; kilit kapatilirsa merkezi kontrol eskisi gibi reddeder."""
    import trader_engine.holdout as H
    check_holdout(HOLDOUT[0], HOLDOUT[1])                                       # acik kilit: gecer
    monkeypatch.setattr(H, "KILIT_ACIK", False)
    with pytest.raises(BacktestArgError):
        check_holdout(HOLDOUT[0], HOLDOUT[1])
    with pytest.raises(BacktestArgError):
        check_holdout(HOLDOUT[0] - pd.Timedelta(days=1), HOLDOUT[0] + pd.Timedelta(days=1))
    real = json.loads((ROOT / "research" / "holdout" / "muhur.json").read_text(encoding="utf-8"))
    assert real["acildi"] is True and real["acilis"]["gerekce"] == "23.11 kullanici karari: kilit kaldirildi"
    assert real["acilis"]["birlesik_sha256"] == real["birlesik_sha256"]


def test_no_other_module_uses_holdout_degerlendir_and_it_never_imports_seal_module():
    me = "holdout_degerlendir"
    users = [p.relative_to(ROOT).as_posix() for base in ("research", "src", "scripts") for p in (ROOT / base).rglob("*.py")
             if p.name != "holdout_degerlendir.py" and me in p.read_text(encoding="utf-8")]
    assert not users, users
    src = (ROOT / "research" / "holdout_degerlendir.py").read_text(encoding="utf-8")
    assert "holdout_muhur" not in src                                  # muhur modulu baska betige iceri alinamaz (guard testi)
    assert "check_holdout" in src and "HOLDOUT" in src
