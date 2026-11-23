"""19b: research/ml_build_candidates.py -- ledger (karar olaylari) -> semaya uygun aday tablosu (sentetik mini ledger)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_ml.features import candidate_rows, feature_frame
from trader_ml.schema import feature_columns, load_candidates, validate_candidates
from trader_core import ml_features as core_feat

ROOT = Path(__file__).resolve().parents[2]
PAIR = "SOL/USDT:USDT"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("ml_build_candidates", ROOT / "research" / "ml_build_candidates.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fake_run(tmp_path, candles):
    df = candles[PAIR]
    rows = candidate_rows(feature_frame(df, None, None), PAIR)
    rows = rows[rows["ts"] >= df.index[0] + pd.Timedelta(hours=1600)].head(40).reset_index(drop=True)
    con = sqlite3.connect(tmp_path / "ledger.sqlite")
    con.execute("CREATE TABLE v_decisions (id INTEGER, bar_close_ts TEXT, pair TEXT, side TEXT, setup TEXT, planned_entry REAL,"
                " planned_stop REAL, planned_target REAL, final_action TEXT, skip_reason TEXT)")
    con.execute("CREATE TABLE v_trades (decision_id INTEGER, exit_ts TEXT, r_multiple REAL, exit_reason TEXT)")
    for i, r in rows.iterrows():
        taken = i % 3 == 0
        con.execute("INSERT INTO v_decisions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (i, r["ts"].strftime("%Y-%m-%dT%H:%M:%S.000Z"), "SOL/USDT", r["side"], r["setup"], r["planned_entry"],
                     r["planned_stop"], None if pd.isna(r["planned_target"]) else r["planned_target"],
                     "entered" if taken else "skipped", None if taken else "risk_denied"))
        if taken:
            con.execute("INSERT INTO v_trades VALUES (?,?,?,?)",
                        (i, (r["ts"] + pd.Timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S.000Z"), 1.25 if i % 2 else -1.0, "stop"))
    con.commit()
    con.close()
    meta = {"fill_model": "native", "period": ["2024-11-01T00:00:00.000Z", "2026-05-01T00:00:00.000Z"]}
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    return rows


def test_build_candidates_schema_taken_skipped_and_labels(mod, candles, tmp_path, monkeypatch):
    rows = _fake_run(tmp_path, candles)
    monkeypatch.setattr(mod, "load_pre_holdout_candles", lambda pair: candles[pair])
    monkeypatch.setattr(mod, "DATA_START", candles[PAIR].index[0])
    t, stats = mod.build(tmp_path, "x")
    assert len(t) == len(rows) == stats["decisions_total"]
    assert int(t["taken"].sum()) == (len(rows) + 2) // 3 and (~t["taken"]).sum() == len(rows) - t["taken"].sum()
    # alinan: ledger gercek cikis + net R; alinmayan: exit_ts yok
    tk = t[t["taken"]]
    assert tk["exit_ts"].notna().all() and ((tk["exit_ts"] - tk["ts"]) == pd.Timedelta(hours=5)).all()
    assert set(tk["net_r"].round(6)) <= {1.25, -1.0}
    assert t.loc[~t["taken"], "exit_ts"].isna().all()
    # etiket: tum adaylar icin uclu bariyer (cozulmus satirlarda 0/1) ve sema gecerli, ozellikler tam
    assert t["label"].dropna().isin([0, 1]).all() and t["label"].notna().sum() > 0.8 * len(t)
    validate_candidates(t)
    assert set(feature_columns(t)) == set(core_feat.FEATURE_NAMES)
    assert not t[feature_columns(t)].isna().all().any()
    assert (t["pair"] == PAIR).all() and (t["source"] == "backtest").all()
    # kilitli donem: etiket/cikis zamani sinirin altinda
    assert t["label_end_ts"].dropna().max() < pd.Timestamp("2026-05-01", tz="UTC")


def test_holdout_rows_never_loaded(mod, monkeypatch):
    # mum yukleyici dosya duzeyinde keser; sinir disindaki tarih HoldoutViolation ile reddedilir (23.11.2026: kilit acik -> kapali bayrakla sinanir)
    from trader_ml import guards as _G
    from trader_ml.guards import HoldoutViolation, assert_pre_holdout
    monkeypatch.setattr(_G, "KILIT_ACIK", False)
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.DatetimeIndex([pd.Timestamp("2026-05-01", tz="UTC")]))
    assert mod.PERIOD.endswith("20260501")


def test_real_candidate_file_loader_smoke():
    p = ROOT / "research" / "ml" / "candidates_v1b_native.parquet"
    mp = ROOT / "research" / "ml" / "candidates_v1b_native.manifest.json"
    if not p.exists() or not mp.exists():
        pytest.skip("gercek aday dosyasi yok (research/ml_build_candidates.py)")
    t = load_candidates(p)                       # sema + kilitli donem korumasi
    m = json.loads(mp.read_text())
    assert m["mode"] == "native" and m["holdout_read"] is False and m["rows"] == len(t)
    assert m["taken"] == int(t["taken"].sum())
    assert set(feature_columns(t)) == set(core_feat.FEATURE_NAMES)


def test_split_eligible_separates_prefiltered_rows(mod, candles, tmp_path, monkeypatch):
    rows = _fake_run(tmp_path, candles)
    monkeypatch.setattr(mod, "load_pre_holdout_candles", lambda pair: candles[pair])
    monkeypatch.setattr(mod, "DATA_START", candles[PAIR].index[0])
    t, _ = mod.build(tmp_path, "x")
    assert t["ml_eligible"].all()                       # sentetik ledger yalniz sinyal True satirlari icerir
    main, pre = mod.split_eligible(t)
    assert len(main) == len(t) and pre.empty
    t2 = t.copy()
    t2.loc[t2.index[:5], "ml_eligible"] = False
    main, pre = mod.split_eligible(t2)
    assert len(pre) == 5 and len(main) == len(t) - 5


# ------------------------------------------------------------------ 19b yeniden kurulum: damga, kirli agac, manifest
def _git(cwd, *a):
    import subprocess
    subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "trader" / "research" / "ml").mkdir(parents=True)
    (r / "trader" / "research" / "logs").mkdir(parents=True)
    (r / "trader" / "src.py").write_text("x = 1\n")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "init")
    return r


def test_git_stamp_clean_and_allowed_untracked(mod, repo):
    root = repo / "trader"
    c, dirty = mod.git_stamp(root)
    assert len(c) == 12 and dirty == [] and mod.require_clean_tree(root) == c
    (root / "research" / "ml" / "a.parquet").write_text("x")
    (root / "research" / "logs" / "b.log").write_text("x")
    assert mod.git_stamp(root)[1] == []                    # izinli: research/ml/ ve research/logs/ altinda izlenmeyen


def test_dirty_tree_refused(mod, repo):
    root = repo / "trader"
    (root / "src.py").write_text("x = 2\n")                # izlenen dosya degisti
    with pytest.raises(SystemExit, match="KIRLI"):
        mod.require_clean_tree(root)
    _git(repo, "checkout", "--", "trader/src.py")
    (root / "new.py").write_text("y")                       # izin disi izlenmeyen dosya
    with pytest.raises(SystemExit, match="KIRLI"):
        mod.require_clean_tree(root)
    (root / "new.py").unlink()
    (root / "research" / "other.txt").write_text("y")       # research/ altinda ama ml/ logs/ disi
    with pytest.raises(SystemExit, match="KIRLI"):
        mod.require_clean_tree(root)
    (root / "research" / "other.txt").unlink()
    (root / "research" / "ml" / "tracked.json").write_text("{}")
    _git(repo, "add", "-A")                                 # izlenen/staged yeni dosya izinli degil
    with pytest.raises(SystemExit, match="KIRLI"):
        mod.require_clean_tree(root)


def test_check_run_meta_requires_paper_risk_synthetic_and_commit(mod, tmp_path):
    good = {"rules_source": "synthetic", "git_commit": "abc1234",
            "flags": {"argv": ["--synthetic-rules", "--target-trade-risk", "0.005"]}}
    (tmp_path / "meta.json").write_text(json.dumps(good))
    assert mod.check_run_meta(tmp_path, "abc1234def00")["git_commit"] == "abc1234"
    for bad in ({"git_commit": "abc1234+dirty"}, {"git_commit": "ffffff0"},
                {"flags": {"argv": ["--synthetic-rules"]}},
                {"flags": {"argv": ["--synthetic-rules", "--target-trade-risk", "0.014"]}},
                {"rules_source": "snapshot"}):
        (tmp_path / "meta.json").write_text(json.dumps({**good, **bad}))
        with pytest.raises(SystemExit):
            mod.check_run_meta(tmp_path, "abc1234def00")


def test_supersede_previous_keeps_old_files(mod, tmp_path):
    (tmp_path / "c.manifest.json").write_text(json.dumps({"rows": 1}))
    (tmp_path / "c.parquet").write_text("a")
    (tmp_path / "c_prefiltered.parquet").write_text("b")
    moved = mod.supersede_previous(tmp_path, "c", "new")
    assert not (tmp_path / "c.manifest.json").exists() and not (tmp_path / "c.parquet").exists()
    d = json.loads((tmp_path / "c.superseded.json").read_text())
    assert d["superseded"] is True and d["superseded_by"] == "new" and d["rows"] == 1
    assert (tmp_path / "c.superseded.parquet").read_text() == "a" and len(moved) == 3
    assert mod.supersede_previous(tmp_path, "c", "new") == []          # tekrar: no-op


def test_main_manifest_fields_and_dirty_refusal(mod, candles, tmp_path, monkeypatch):
    _fake_run(tmp_path, candles)
    meta = json.loads((tmp_path / "meta.json").read_text())
    meta.update(rules_source="synthetic", git_commit="abc1234", engine_version="t", strategy_label="s", trigger_tf="1h",
                granularity="1m", param_version_id=1, id="x", cost={"c": 1},
                flags={"argv": ["--synthetic-rules", "--target-trade-risk", "0.005"]})
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    out = tmp_path / "out"
    monkeypatch.setattr(mod, "OUT_DIR", out)
    monkeypatch.setattr(mod, "load_pre_holdout_candles", lambda pair: candles[pair])
    monkeypatch.setattr(mod, "DATA_START", candles[PAIR].index[0])
    # kirli agac: hicbir cikti uretilmez
    monkeypatch.setattr(mod, "git_stamp", lambda root=mod.ROOT: ("abc1234def00", [" M x.py"]))
    with pytest.raises(SystemExit, match="KIRLI"):
        mod.main(["--run-dir", str(tmp_path), "--out", "t"])
    assert not out.exists()
    # temiz agac
    monkeypatch.setattr(mod, "git_stamp", lambda root=mod.ROOT: ("abc1234def00", []))
    assert mod.main(["--run-dir", str(tmp_path), "--out", "t"]) == 0
    m = json.loads((out / "t.manifest.json").read_text())
    assert m["recipe_id"] == "ml1-r01-v1b-native33" and m["target_trade_risk"] == 0.005
    assert m["rules_source"] == "synthetic-preholdout" and "451" in m["rules_exception"]
    assert m["git_commit_start"] == "abc1234def00" and m["tree_clean_at_start"] is True
    assert m["sha256"]["t.parquet"] == mod.sha256_file(out / "t.parquet")
    assert m["sha256"]["t_prefiltered.parquet"] == mod.sha256_file(out / "t_prefiltered.parquet")
    assert m["holdout_read"] is False


def test_backtest_arg_target_trade_risk_default_and_override():
    from trader_engine.backtest import BacktestRunner, build_parser, spec_from_args
    from trader_core import risk as K
    base = ["--id", "z", "--period", "20250301-20250303"]
    def cfg(extra):
        a = build_parser().parse_args(base + extra)
        return BacktestRunner(spec_from_args(a, base + extra)).build_config()
    assert cfg([]).target_trade_risk == K.LOCKED_CFG.target_trade_risk == 0.014      # varsayilan davranis degismedi
    assert cfg(["--target-trade-risk", "0.005"]).target_trade_risk == 0.005
    with pytest.raises(Exception):                                                    # gevsetme reddedilir
        cfg(["--target-trade-risk", "0.02"])
