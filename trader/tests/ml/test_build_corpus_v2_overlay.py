"""scripts/build_corpus_v2_overlay.py (on kayit 2.2): sentetik ledger fixture (tmp_path); backtest KOSULMAZ, ag/gercek veri yok."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

from trader_engine.holdout import HOLDOUT
from trader_ml import corpus_v2
from test_corpus_v2_run import make_manifest
from trader_ml.guards import HoldoutViolation

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "abc123def456"
HOLD0 = pd.Timestamp(HOLDOUT[0])
END_ISO, END_COMPACT = f"{HOLD0:%Y-%m-%d}", f"{HOLD0:%Y%m%d}"          # kayitli donem sonu = kilitli donem baslangici (turetilir)
PERIOD_COMPACT = f"20210101-{END_COMPACT}"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("build_corpus_v2_overlay", ROOT / "scripts" / "build_corpus_v2_overlay.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus_v2_overlay"] = m
    spec.loader.exec_module(m)
    return m


T0 = pd.Timestamp("2022-03-01 10:00", tz="UTC")
ROWS = [  # (pair ledger adi, ts, side, final_action, exit_ts, r)
    ("BTC/USDT", T0, "long", "entered", T0 + pd.Timedelta(hours=5), 1.25),
    ("ETH/USDT", T0, "short", "entered", T0 + pd.Timedelta(hours=9), -1.0),
    ("SOL/USDT", T0 + pd.Timedelta(hours=1), "long", "entered", None, None),                  # donem sonunda acik
    ("BTC/USDT", T0 + pd.Timedelta(hours=2), "long", "skipped", None, None),
    ("ETH/USDT", T0 + pd.Timedelta(hours=3), "long", "skipped", None, None),
    ("BTC/USDT", pd.Timestamp("2023-06-01 10:00", tz="UTC"), "long", "entered", pd.Timestamp("2023-06-01 14:00", tz="UTC"), 0.5),   # dilim 1
    ("BTC/USDT", pd.Timestamp("2024-06-01 10:00", tz="UTC"), "short", "entered", pd.Timestamp("2024-06-01 14:00", tz="UTC"), -1.0),  # dilim 2
    ("BTC/USDT", pd.Timestamp("2025-06-01 10:00", tz="UTC"), "long", "entered", pd.Timestamp("2025-06-01 14:00", tz="UTC"), 2.0),   # dilim 3
]


def make_run(tmp_path, rows=ROWS, *, period=("2021-01-01", END_ISO), argv=None):
    rd = tmp_path / "run"
    rd.mkdir()
    con = sqlite3.connect(rd / "ledger.sqlite")
    con.execute("CREATE TABLE v_decisions (id INTEGER, bar_close_ts TEXT, pair TEXT, side TEXT, setup TEXT, planned_entry REAL, "
                "planned_stop REAL, planned_target REAL, final_action TEXT, skip_reason TEXT, veto_reason TEXT)")
    con.execute("CREATE TABLE v_trades (decision_id INTEGER, exit_ts TEXT, r_multiple REAL, exit_reason TEXT)")
    for i, (pair, ts, side, act, ex, r) in enumerate(rows, 1):
        con.execute("INSERT INTO v_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (i, ts.isoformat(), pair, side, "T1", 100.0, 98.0, None, act, None if act == "entered" else "risk", None))
        if act == "entered" and ex is not None:
            con.execute("INSERT INTO v_trades VALUES (?,?,?,?)", (i, ex.isoformat(), r, "tp"))
    con.commit()
    con.close()
    if argv is None:                                                       # gercek kosudaki gibi TAM bayraklar (--id/--out-root + bt_args)
        argv = ["--id", "run", "--out-root", str(tmp_path), *sys.modules["build_corpus_v2_overlay"].bt_args()]
    meta = {"id": "run", "flags": {"argv": argv}, "rules_source": "synthetic",
            "git_commit": COMMIT[:12], "period": list(period), "fill_model": "native", "engine_version": "t", "strategy_label": "price_action_v1",
            "cost": {"fee": 0.0005}, "trigger_tf": "1h", "granularity": "1h", "param_version_id": "p"}
    (rd / "meta.json").write_text(json.dumps(meta))
    return rd


def corpus_for(tmp_path, rows=ROWS, extra=(), *, manifest=True):
    keys = [(p + ":USDT", ts, side) for p, ts, side, *_ in rows]
    keys += list(extra)
    df = pd.DataFrame(keys, columns=["pair", "ts", "side"])
    p = tmp_path / "corpus_v2.parquet"
    df.to_parquet(p, index=False)
    if manifest:                                                           # fix 5: betik backtest'ten ONCE derlem manifestini dogrular
        (tmp_path / "corpus_v2.manifest.json").write_text(json.dumps(make_manifest(p)))
    return p


@pytest.fixture
def clean(mod, monkeypatch):
    monkeypatch.setattr(mod, "git_stamp", lambda *a, **k: (COMMIT, []))


def test_bt_args_are_19b_flags_with_registered_period(mod):
    a = mod.bt_args()
    assert a[a.index("--period") + 1] == PERIOD_COMPACT and mod.PERIOD == PERIOD_COMPACT
    for flag, val in (("--tf", "1h"), ("--fill-model", "native"), ("--strategy", "price_action_v1"), ("--target-trade-risk", "0.005")):
        assert a[a.index(flag) + 1] == val
    assert "--synthetic-rules" in a


def test_overlay_built_from_ledger(mod, clean, tmp_path):
    rd = make_run(tmp_path)
    corpus = corpus_for(tmp_path)
    out = tmp_path / "out"
    assert mod.run(["--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(out)]) == 0
    ov = pd.read_parquet(out / "corpus_v2_taken.parquet")
    man = json.loads((out / "corpus_v2_taken.manifest.json").read_text())
    assert len(ov) == 6 and set(ov["pair"]) == {"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"}      # ledger pair -> derlem pair
    r = ov[ov["pair"] == "BTC/USDT:USDT"].iloc[0]
    assert r["r_multiple"] == 1.25 and r["exit_ts"] == T0 + pd.Timedelta(hours=5) and r["side"] == "long"
    assert ov["exit_ts"].isna().sum() == 1
    assert man["sha256"] == mod.sha256_file(out / "corpus_v2_taken.parquet") and man["git"] == {"commit": COMMIT, "tree_clean": True}
    assert (man["corpus_rows"], man["entered_total"], man["taken_matched"], man["skipped"]) == (8, 6, 6, 2)
    assert man["unmatched_entered"] == 0 and man["taken_open_at_end"] == 1 and man["holdout_read"] is False
    assert man["config_hash"] and man["period"] == PERIOD_COMPACT and man["corpus_sha256"] == mod.sha256_file(corpus)
    assert man["backtest_period"] == ["2021-01-01", END_ISO] and man["overlay_version"] == "corpus_v2_taken" and man["taken_missing_r"] == 0
    assert corpus_v2.verify_overlay_manifest(man, out / "corpus_v2_taken.parquet", corpus) == []


def test_overlay_feeds_loader_end_to_end(mod, clean, tmp_path):
    """Katman dosyasi load_run_table ile uyumlu (anahtar/sutun sozlesmesi)."""
    rd = make_run(tmp_path)
    corpus = corpus_for(tmp_path)
    out = tmp_path / "out"
    mod.run(["--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(out)])
    ov = pd.read_parquet(out / "corpus_v2_taken.parquet")
    assert set(corpus_v2.OVERLAY_REQUIRED) <= set(ov.columns)


def test_unmatched_entered_refused(mod, clean, tmp_path, capsys):
    rd = make_run(tmp_path)
    corpus = corpus_for(tmp_path, rows=ROWS[1:])                        # BTC alinmis islemin derlemde karsiligi yok
    out = tmp_path / "out"
    rc = mod.run(["--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(out)])
    assert rc == mod.UNMATCHED_EXIT != 0 and "karsiligi olmayan" in capsys.readouterr().err
    man = json.loads((out / "corpus_v2_taken.manifest.json").read_text())
    assert man["unmatched_entered"] == 1
    assert corpus_v2.verify_overlay_manifest(man, out / "corpus_v2_taken.parquet", corpus)        # yuklemeyi de reddeder


def test_period_end_after_holdout_refused(mod, clean, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    rd = make_run(tmp_path)
    corpus = corpus_for(tmp_path)
    late = (HOLD0 + pd.Timedelta(days=1)).strftime("%Y%m%d")
    with pytest.raises(HoldoutViolation):
        mod.run(["--period", f"20210101-{late}", "--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(tmp_path / "o")])
    assert not (tmp_path / "o").exists()
    with pytest.raises(SystemExit, match="on kayitla"):
        mod.check_period("20220101-20230101")
    with pytest.raises(HoldoutViolation):                                           # kosu meta'si kilitli doneme giriyorsa
        mod.check_period(f"20210101-{(HOLD0 + pd.Timedelta(days=30)):%Y%m%d}")
    (tmp_path / "x").mkdir()
    bad_meta = make_run(tmp_path / "x", period=("2021-01-01", str(HOLD0 + pd.Timedelta(days=3))[:10]))
    with pytest.raises(SystemExit, match="on kayda uymuyor"):
        mod.run(["--run-dir", str(bad_meta), "--corpus", str(corpus), "--out-dir", str(tmp_path / "o2")])


def test_dirty_tree_refused(mod, monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "git_stamp", lambda *a, **k: (COMMIT, [" M src/x.py"]))
    rd = make_run(tmp_path)
    with pytest.raises(SystemExit, match="KIRLI"):
        mod.run(["--run-dir", str(rd), "--corpus", str(corpus_for(tmp_path)), "--out-dir", str(tmp_path / "o")])


def test_run_meta_must_match_registered_run(mod, clean, tmp_path):
    rd = make_run(tmp_path)
    meta = json.loads((rd / "meta.json").read_text())
    meta["flags"]["argv"] = ["--target-trade-risk", "0.005"]                       # --synthetic-rules yok
    (rd / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(SystemExit, match="synthetic-rules"):
        mod.run(["--run-dir", str(rd), "--corpus", str(corpus_for(tmp_path)), "--out-dir", str(tmp_path / "o")])


# ------------------------------------------------------------------ mentor inceleme duzeltmeleri (fix 2, 3, 5)
def test_fix2_run_period_must_be_exact_not_just_in_range(mod, clean, tmp_path):
    """Kisa/erken biten kosu (2021-01-01 .. daha once) kilitli doneme girmese de REDDEDILIR; tam kayitli donem sart."""
    corpus = corpus_for(tmp_path)
    for i, per in enumerate((("2021-01-01", "2025-01-01"), ("2021-06-01", END_ISO))):
        d = tmp_path / f"p{i}"
        d.mkdir()
        rd = make_run(d, period=per)
        with pytest.raises(SystemExit, match="on kayda uymuyor"):
            mod.run(["--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(d / "o")])


def test_fix2_run_argv_must_equal_bt_args(mod, clean, tmp_path):
    corpus = corpus_for(tmp_path)
    good = ["--id", "run", "--out-root", str(tmp_path), *mod.bt_args()]
    assert mod.run_argv_matches(good)
    extra = good + ["--pairs", "BTC/USDT"]                                         # fazladan bayrak
    drop = [x for x in good if x != "--synthetic-rules"]
    other = list(good)
    other[other.index("--tf") + 1] = "4h"                                          # farkli deger
    assert not mod.run_argv_matches(extra) and not mod.run_argv_matches(drop) and not mod.run_argv_matches(other)
    d = tmp_path / "e"
    d.mkdir()
    rd = make_run(d, argv=extra)
    with pytest.raises(SystemExit, match="bt_args"):
        mod.run(["--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(d / "o")])


def test_fix2_manifest_period_comes_from_run_meta(mod, clean, tmp_path):
    rd = make_run(tmp_path, period=("2021-01-01T00:00:00.000Z", f"{END_ISO}T00:00:00.000Z"))
    out = tmp_path / "out"
    assert mod.run(["--run-dir", str(rd), "--corpus", str(corpus_for(tmp_path)), "--out-dir", str(out)]) == 0
    man = json.loads((out / "corpus_v2_taken.manifest.json").read_text())
    assert man["period"] == PERIOD_COMPACT and man["backtest_period"][0].startswith("2021-01-01")


def test_fix3_overlay_manifest_checks(mod, clean, tmp_path):
    rd = make_run(tmp_path)
    corpus = corpus_for(tmp_path)
    out = tmp_path / "out"
    assert mod.run(["--run-dir", str(rd), "--corpus", str(corpus), "--out-dir", str(out)]) == 0
    good = json.loads((out / "corpus_v2_taken.manifest.json").read_text())
    ovp = out / "corpus_v2_taken.parquet"
    assert corpus_v2.verify_overlay_manifest(good, ovp, corpus) == []
    other = tmp_path / "other"
    other.mkdir()
    other_corpus = corpus_for(other, rows=ROWS[:3], manifest=False)             # baska derlem (sha256 farkli)
    assert any("corpus_sha256" in e for e in corpus_v2.verify_overlay_manifest(good, ovp, other_corpus))
    bad = {"overlay_version": "x", "taken_missing_r": 2, "holdout_read": True, "git": {"tree_clean": False},
           "backtest_period": ["2021-01-01", "2025-01-01"], "corpus_sha256": None}
    for k, v in bad.items():
        errs = corpus_v2.verify_overlay_manifest({**good, k: v}, ovp, corpus)
        assert errs, k
    assert corpus_v2.verify_overlay_manifest({k: v for k, v in good.items() if k != "corpus_sha256"}, ovp, corpus)


def test_fix5_corpus_manifest_verified_before_backtest(mod, clean, tmp_path, monkeypatch):
    """Derlem manifesti (sha256 / code_sha256) tutmuyorsa UZUN backtest hic baslamaz."""
    called = []
    monkeypatch.setattr(mod, "run_backtest", lambda rd: called.append(rd))
    corpus = corpus_for(tmp_path)
    man_path = tmp_path / "corpus_v2.manifest.json"
    man = json.loads(man_path.read_text())
    man["code_sha256"]["src/trader_ml/labels.py"] = "0" * 64                        # kod manifestten sonra degismis
    man_path.write_text(json.dumps(man))
    run_dir = tmp_path / "yok_run"                                                  # ledger yok -> backtest kosulacakti
    with pytest.raises(SystemExit, match="backtest baslatilmaz"):
        mod.run(["--run-dir", str(run_dir), "--corpus", str(corpus), "--out-dir", str(tmp_path / "o")])
    man = json.loads(man_path.read_text())
    man["corpus"]["sha256"] = "1" * 64                                              # derlem degismis
    man_path.write_text(json.dumps(man))
    with pytest.raises(SystemExit, match="backtest baslatilmaz"):
        mod.run(["--run-dir", str(run_dir), "--corpus", str(corpus), "--out-dir", str(tmp_path / "o")])
    man_path.unlink()
    with pytest.raises(SystemExit, match="manifesti yok"):
        mod.run(["--run-dir", str(run_dir), "--corpus", str(corpus), "--out-dir", str(tmp_path / "o")])
    assert called == []
