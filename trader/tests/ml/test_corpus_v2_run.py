"""Derlem v2 + katman -> kosu tablosu, manifest dogrulamasi, CLI (sha/manifest/sira korumalari). Yalniz sentetik (tmp_path); ag/veri yok."""
from __future__ import annotations

import dataclasses
import json

import numpy as np
import pandas as pd
import pytest

from trader_engine.holdout import HOLDOUT
from trader_ml import config, corpus_v2, pipeline, recipes
from trader_ml.guards import HoldoutViolation

R02, R03 = recipes.R02_ID, recipes.R03_ID
HOLD0 = pd.Timestamp(HOLDOUT[0])
END_ISO, END_COMPACT = f"{HOLD0:%Y-%m-%d}", f"{HOLD0:%Y%m%d}"          # kayitli donem sonu = kilitli donem baslangici (turetilir)
PERIOD_COMPACT = f"20210101-{END_COMPACT}"
PAIRS = corpus_v2.CORPUS_PAIRS
FEATS = list(recipes.get(R02).features)
EXTRA3 = corpus_v2.R03_EXTRA


def make_corpus(n_per_pair=1300, seed=0, *, end=None) -> pd.DataFrame:
    """Sentetik derlem v2 (r02 40 + r03 ek 3 ozellik, label_1r/1p5r/2r sutunlari); ts 2021-01 .. kilitli donemden once."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2021-02-01", tz="UTC")
    end = end or (HOLD0 - pd.Timedelta(days=12))
    span = int((end - start) / pd.Timedelta(hours=1))
    parts = []
    for p in PAIRS:
        idx = np.sort(rng.choice(span, size=n_per_pair, replace=False))
        ts = start + pd.to_timedelta(idx, unit="h")
        side = rng.choice(["long", "short"], n_per_pair)
        entry = rng.uniform(50, 100, n_per_pair)
        stop = np.where(side == "long", entry * 0.98, entry * 1.02)
        d = pd.DataFrame({"pair": p, "ts": ts, "setup": "T1", "side": side, "planned_entry": entry, "planned_stop": stop,
                          "planned_target": np.nan, "source": "native_v1b", "cost_r": rng.uniform(0.02, 0.1, n_per_pair)})
        for tag in ("1r", "1p5r", "2r"):
            lab = (rng.random(n_per_pair) < 0.4).astype(float)
            d[f"label_{tag}"] = lab
            d[f"label_end_ts_{tag}"] = ts + pd.to_timedelta(rng.integers(1, 72, n_per_pair), unit="h")
            d[f"barrier_net_r_{tag}"] = np.where(lab == 1, 1.0, -1.0) - d["cost_r"]
        for f in FEATS + EXTRA3:
            d[f] = rng.normal(size=n_per_pair)
        parts.append(d)
    c = pd.concat(parts, ignore_index=True).sort_values(["ts", "pair"], kind="mergesort").reset_index(drop=True)
    c["f_same_bar_signals"] = c.groupby("ts")["pair"].transform("nunique").astype(float)
    c.loc[c.index[:5], "f_funding_last"] = np.nan
    return c


def make_overlay(c: pd.DataFrame, frac=0.6, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pick = c[rng.random(len(c)) < frac]
    return pd.DataFrame({"pair": pick["pair"].to_numpy(), "ts": pick["ts"].to_numpy(), "side": pick["side"].to_numpy(),
                         "setup": "T1", "exit_ts": (pick["ts"] + pd.Timedelta(hours=6)).to_numpy(),
                         "r_multiple": rng.normal(0.05, 1.0, len(pick)), "exit_reason": "tp"}).reset_index(drop=True)


# ------------------------------------------------------------------ load_run_table
def test_load_run_table_mapping():
    c = make_corpus(n_per_pair=60)
    c.loc[c.index[:3], "label_1r"] = np.nan                       # cozulmemis: atilir
    c = c.assign(f_not_in_recipe=1.0)                              # tarifte olmayan f_*
    ov = make_overlay(c, 0.5)
    t, info = corpus_v2.load_run_table(c, ov, recipes.get(R02))
    unresolved = c["label_1r"].isna().sum()
    assert info["dropped_unresolved"] == int(unresolved) == 3 and info["overlay_unmatched_entered"] == 0
    assert (t["source"] == "backtest").all()
    kc = c.set_index(["pair", "ts", "side"])
    ko = ov.set_index(["pair", "ts", "side"])
    for _, r in t.sample(40, random_state=0).iterrows():
        key = (r["pair"], r["ts"], r["side"])
        src = kc.loc[key]
        assert r["label"] == src["label_1r"] and r["label_end_ts"] == src["label_end_ts_1r"]
        if key in ko.index:
            assert r["taken"] and r["net_r"] == ko.loc[key, "r_multiple"] and r["exit_ts"] == ko.loc[key, "exit_ts"]
        else:
            assert not r["taken"] and r["net_r"] == src["barrier_net_r_1r"] and pd.isna(r["exit_ts"])
        assert r["cost_r"] == src["cost_r"] and r["setup"] == "T1"
    assert info["taken"] == int(t["taken"].sum()) and info["rows"] == len(t)


def test_non_recipe_features_never_reach_model_input():
    c = make_corpus(n_per_pair=40).assign(f_not_in_recipe=1.0)
    ov = make_overlay(c)
    for rid in (R02, R03):
        rec = recipes.get(rid)
        t, _ = corpus_v2.load_run_table(c, ov, rec)
        fcols = [x for x in t.columns if x.startswith("f_")]
        assert fcols == list(rec.features) and "f_not_in_recipe" not in t.columns
    t3, _ = corpus_v2.load_run_table(c, ov, recipes.get(R03))
    assert not {"f_vol_1h", "f_funding_last"} & set(t3.columns)       # r03: r02'nin 40'indan yalniz ortak 5'i


def test_open_taken_trades_dropped_and_counted():
    c = make_corpus(n_per_pair=40)
    ov = make_overlay(c)
    ov.loc[ov.index[:4], "exit_ts"] = pd.NaT
    t, info = corpus_v2.load_run_table(c, ov, recipes.get(R02))
    assert info["dropped_taken_open_at_end"] == 4
    assert not t[t["taken"]]["exit_ts"].isna().any()


def test_unmatched_entered_reported():
    c = make_corpus(n_per_pair=40)
    ov = make_overlay(c)
    ov.loc[ov.index[0], "ts"] = c["ts"].min() - pd.Timedelta(hours=1)
    _, info = corpus_v2.load_run_table(c, ov, recipes.get(R02))
    assert info["overlay_unmatched_entered"] == 1


def test_holdout_guard_on_corpus_and_overlay(monkeypatch):
    from trader_ml import guards as _G
    monkeypatch.setattr(_G, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    c = make_corpus(n_per_pair=40)
    ov = make_overlay(c)
    bad = c.copy()
    bad.loc[bad.index[-1], "ts"] = HOLD0
    with pytest.raises(HoldoutViolation):
        corpus_v2.load_run_table(bad, ov, recipes.get(R02))
    bad_ov = ov.copy()
    bad_ov.loc[bad_ov.index[0], "exit_ts"] = HOLD0 + pd.Timedelta(hours=1)
    with pytest.raises(HoldoutViolation):
        corpus_v2.load_run_table(c, bad_ov, recipes.get(R02))
    bad_end = c.copy()
    bad_end.loc[bad_end.index[0], "label_end_ts_1r"] = HOLD0 + pd.Timedelta(hours=1)
    with pytest.raises(HoldoutViolation):
        corpus_v2.load_run_table(bad_end, ov, recipes.get(R02))


def test_missing_columns_rejected():
    c = make_corpus(n_per_pair=20)
    with pytest.raises(corpus_v2.CorpusError, match="eksik"):
        corpus_v2.load_run_table(c.drop(columns=["f_vol_1h"]), make_overlay(c), recipes.get(R02))
    with pytest.raises(corpus_v2.CorpusError, match="katman"):
        corpus_v2.load_run_table(c, make_overlay(c).drop(columns=["r_multiple"]), recipes.get(R02))


# ------------------------------------------------------------------ fixture: derlem + manifest + katman diske
CODE_REL = "src/trader_ml/config.py"


def make_manifest(corpus_path, **over) -> dict:
    man = {
        "corpus_version": "corpus_v2", "recipe_ids": [R02, R03], "source": "native_v1b",
        "candidate_definition": "pre-post_filter native v1b: feature_frame+candidate_rows (19b), signal True, setup T1, post_filter YOK; iki yon; 10 cift",
        "period": {"start": "2021-01-01 00:00:00+00:00", "end_exclusive": f"{END_ISO} 00:00:00+00:00", "holdout_read": False,
                   "ts_max": str(HOLD0 - pd.Timedelta(days=12))},
        "pairs": PAIRS, "horizon_bars": 72, "target_rs": [1.0, 1.5, 2.0],
        "git": {"commit": "abc123def456", "dirty": [], "tree_clean": True},
        "r02_features": list(FEATS), "r03_features": list(recipes.get(R03).features), "n_features": 43,
        "feature_columns": FEATS + EXTRA3,
        "same_bar": {"rows_unique_pair_ts": True, "feature_matches_distinct_pairs": True},
        "corpus": {"file": corpus_path.name, "sha256": corpus_v2.sha256_path(corpus_path)},
        "code_sha256": {k: corpus_v2.sha256_path(corpus_v2.ROOT / k) for k in corpus_v2.EXPECTED_CODE_KEYS},
        "inputs_sha256": {"x.feather": {"sha256": "0"}}, "input_slices": {PAIRS[0]: {"candle_gaps": 0}},
    }
    man.update(over)
    return man


def make_overlay_manifest(overlay_path, corpus_path, **over) -> dict:
    man = {"overlay_version": "corpus_v2_taken", "sha256": corpus_v2.sha256_path(overlay_path), "corpus_sha256": corpus_v2.sha256_path(corpus_path),
           "unmatched_entered": 0, "taken_missing_r": 0, "period": PERIOD_COMPACT, "backtest_period": ["2021-01-01", END_ISO],
           "holdout_read": False, "git": {"commit": "abc123def456", "tree_clean": True}, "config_hash": "h",
           "taken_per_fold": [{"fold": k, "test_start": "x", "test_end": "y", "taken": 10} for k in range(4)], "gate_closed_skips": {}}
    man.update(over)
    return man


@pytest.fixture(autouse=True)
def _clean_git(monkeypatch):
    """Gercek r02/r03 kosusu temiz agac ister (fix 7); test ortami calisma agaci kirli olabilir -> temiz damga."""
    monkeypatch.setattr(pipeline, "git_state", lambda: {"commit": "abc123def456", "tree_clean": True, "dirty": []})


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    d = tmp_path_factory.mktemp("v2")
    c = make_corpus(n_per_pair=1500)
    ov = make_overlay(c, 0.6)
    cp, op = d / "corpus_v2.parquet", d / "corpus_v2_taken.parquet"
    c.to_parquet(cp, index=False)
    ov.to_parquet(op, index=False)
    mp = d / "corpus_v2.manifest.json"
    mp.write_text(json.dumps(make_manifest(cp)))
    omp = d / "corpus_v2_taken.manifest.json"
    omp.write_text(json.dumps(make_overlay_manifest(op, cp)))
    (d / "corpus_v2.sample_check.md").write_text("# kontrol\n\nBagimsiz yeniden hesap uyumu: 150/150 (etiket + bitis zamani).\n", encoding="utf-8")
    return {"dir": d, "corpus": cp, "overlay": op, "manifest": mp, "omanifest": omp,
            "csha": corpus_v2.sha256_path(cp), "osha": corpus_v2.sha256_path(op)}


def _argv(f, *extra, recipe=R02, out=None):
    return ["--recipe", recipe, "--corpus", str(f["corpus"]), "--overlay", str(f["overlay"]), "--manifest", str(f["manifest"]),
            "--out", str(out or f["dir"] / "out"), "--research", *extra]


# ------------------------------------------------------------------ manifest dogrulamasi
def test_manifest_good_and_each_field_mismatch(files):
    good = json.loads(files["manifest"].read_text())
    errs, _ = corpus_v2.verify_corpus_manifest(good, files["corpus"])
    assert errs == []
    cases = {
        "corpus_version": "corpus_v1", "recipe_ids": [R02], "source": "x", "pairs": PAIRS[:9], "horizon_bars": 48,
        "target_rs": [1.0, 2.0], "n_features": 42, "r02_features": FEATS[::-1], "r03_features": [],
        "feature_columns": FEATS, "period": {**good["period"], "holdout_read": True},
        "git": {"commit": "a", "dirty": [" M x"], "tree_clean": False},
        "same_bar": {"rows_unique_pair_ts": True, "feature_matches_distinct_pairs": False},
        "corpus": {"sha256": "0" * 64}, "code_sha256": {**good["code_sha256"], CODE_REL: "0" * 64}, "inputs_sha256": {}, "candidate_definition": "x",
    }
    for k, v in cases.items():
        errs, _ = corpus_v2.verify_corpus_manifest({**good, k: v}, files["corpus"])
        assert errs, k
    bad_period = {**good["period"], "start": "2021-02-01 00:00:00+00:00"}
    assert corpus_v2.verify_corpus_manifest({**good, "period": bad_period}, files["corpus"])[0]
    late = {**good["period"], "ts_max": str(HOLD0)}
    assert corpus_v2.verify_corpus_manifest({**good, "period": late}, files["corpus"])[0]


# ------------------------------------------------------------------ CLI: sha / manifest / sira korumasi / n_trials
def test_cli_sha_mismatch_refused_with_distinct_code(files, capsys):
    rc = pipeline.main(_argv(files, "--expect-corpus-sha256", "0" * 64, "--expect-overlay-sha256", files["osha"]))
    assert rc == pipeline.EXIT_SHA == 5 and "sha256 uyusmuyor" in capsys.readouterr().err
    rc = pipeline.main(_argv(files, "--expect-corpus-sha256", files["csha"], "--expect-overlay-sha256", "1" * 64))
    assert rc == pipeline.EXIT_SHA
    assert pipeline.main(_argv(files)) == pipeline.EXIT_SHA              # gercek kosu beklenen sha olmadan baslamaz


def test_cli_manifest_mismatch_refused_incl_code_sha(files, tmp_path, capsys):
    man = json.loads(files["manifest"].read_text())
    man["code_sha256"] = {**man["code_sha256"], CODE_REL: "0" * 64}        # kod manifestten sonra degismis
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(man))
    f = {**files, "manifest": mp}
    rc = pipeline.main(_argv(f, "--expect-corpus-sha256", files["csha"], "--expect-overlay-sha256", files["osha"]))
    assert rc == pipeline.EXIT_MANIFEST == 6 and "code_sha256" in capsys.readouterr().err
    assert pipeline.EXIT_SHA != pipeline.EXIT_MANIFEST != pipeline.EXIT_ORDER


def test_cli_overlay_manifest_unmatched_refused(files, tmp_path, capsys):
    om = tmp_path / "om.json"
    om.write_text(json.dumps(make_overlay_manifest(files["overlay"], files["corpus"], unmatched_entered=2)))
    rc = pipeline.main(_argv(files, "--overlay-manifest", str(om), "--expect-corpus-sha256", files["csha"],
                             "--expect-overlay-sha256", files["osha"]))
    assert rc == pipeline.EXIT_MANIFEST and "unmatched_entered" in capsys.readouterr().err


def test_cli_n_trials_can_only_raise(files, tmp_path):
    base = _argv(files, "--precheck-only", "--expect-corpus-sha256", files["csha"], "--expect-overlay-sha256", files["osha"])
    with pytest.raises(SystemExit) as e:
        pipeline.main(base + ["--n-trials", "9"])
    assert e.value.code == 2
    reg = tmp_path / "reg.csv"
    reg.write_text("recipe_id,registered_at,note\n" + "\n".join(f"{r},d,n" for r in ("a", "b", R02)) + "\n")
    with pytest.raises(SystemExit):                                       # defterde r02 yoksa / n_trials alt sinir
        pipeline.main(base + ["--registry", str(reg), "--n-trials", "5"])
    assert pipeline.main(base + ["--registry", str(reg)]) in (0, pipeline.EXIT_POWER)   # defter 3 satir -> 6
    assert pipeline.main(base + ["--n-trials", "50"]) in (0, pipeline.EXIT_POWER)


def test_n_trials_uses_registry_for_recipe_id(files, capsys):
    pipeline.main(_argv(files, "--precheck-only", "--expect-corpus-sha256", files["csha"], "--expect-overlay-sha256", files["osha"]))
    out = capsys.readouterr().out
    assert "n_trials=10" in out and "Gereken IC rho" in out and "Ozellik sagligi" in out


def test_precheck_only_with_recipe_features_and_rho(files, capsys):
    rc = pipeline.main(_argv(files, "--precheck-only", recipe=R03) + ["--prior-result", str(_prior(files["dir"], False, files=files))])
    out = capsys.readouterr().out
    assert rc in (0, pipeline.EXIT_POWER) and "TEMIZ" in out and "rho" in out


def _prior(d, passed, recipe_id=R02, *, files=None, **over):
    """r02 sonucu (gate_result.json bicimi). files verilirse sha256'lar bu girdilerinki, synthetic false."""
    body = {"recipe_id": recipe_id, "passed": passed, "synthetic": False,
            "corpus_sha256": files["csha"] if files else None, "overlay_sha256": files["osha"] if files else None, **over}
    p = d / f"prior_{recipe_id}_{passed}_{abs(hash(json.dumps(body, sort_keys=True)))}.json"
    p.write_text(json.dumps(body))
    return p


def test_order_guard_r03(files, capsys):
    rec3 = recipes.get(R03)
    assert pipeline.check_order_guard(recipes.get(R02), None) is None            # r02 icin sira korumasi yok
    assert pipeline.check_order_guard(rec3, None)                                 # onceki sonuc yok
    assert pipeline.check_order_guard(rec3, files["dir"] / "yok.json")
    assert pipeline.check_order_guard(rec3, _prior(files["dir"], True))           # r02 KABUL -> r03 kosulmaz
    assert pipeline.check_order_guard(rec3, _prior(files["dir"], None))           # belirsiz sonuc de red
    assert pipeline.check_order_guard(rec3, _prior(files["dir"], False, R03))     # yanlis tarif
    assert pipeline.check_order_guard(rec3, _prior(files["dir"], False)) is None  # r02 RED -> serbest
    for prior in (None, _prior(files["dir"], True)):
        rc = pipeline.main(_argv(files, recipe=R03) + (["--prior-result", str(prior)] if prior else []))
        assert rc == pipeline.EXIT_ORDER == 7
    assert "sira korumasi" in capsys.readouterr().err
    # serbest birakilinca korumadan gecer (sonraki adim: sha beklentisi yok -> EXIT_SHA)
    assert pipeline.main(_argv(files, recipe=R03) + ["--prior-result", str(_prior(files["dir"], False, files=files))]) == pipeline.EXIT_SHA


def test_v2_recipe_rejects_candidates_flag(files):
    with pytest.raises(SystemExit):
        pipeline.main(["--recipe", R02, "--synthetic", "--out", str(files["dir"] / "o")])


# ------------------------------------------------------------------ tam CLI kosusu + CalibrationClamped (cikis 4)
def test_full_cli_run_writes_both_sha256(files, capsys, monkeypatch):
    pytest.importorskip("lightgbm")
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 1.0)                      # sentetik gun sayisi veto ile ilgisiz
    out = files["dir"] / "full"
    rc = pipeline.main(_argv(files, "--expect-corpus-sha256", files["csha"], "--expect-overlay-sha256", files["osha"], out=out))
    assert rc in (0, 4)
    res = json.loads((out / "gate_result.json").read_text())
    assert res["corpus_sha256"] == files["csha"] and res["overlay_sha256"] == files["osha"] and res["recipe_id"] == R02
    md = (out / "gate_report.md").read_text(encoding="utf-8")
    assert files["csha"] in md and files["osha"] in md
    assert pd.read_parquet(out / "oof_predictions.parquet")["fold"].nunique() == 4
    assert res["weight_scheme"] == "uniq_decay"
    if rc == 4:
        assert res["passed"] is False and not (out / "model_candidate.json").exists()
    else:
        assert json.loads((out / "model_candidate.json").read_text())["meta"]["version"] == R02


def test_cli_exit_4_on_clamped_package(files, monkeypatch):
    pytest.importorskip("lightgbm")
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 1.0)
    real = pipeline.models.fit_platt_info
    monkeypatch.setattr(pipeline.models, "fit_platt_info", lambda z, y, *a, **k: (real(z, y, *a, **k)[0], True))
    out = files["dir"] / "clamped"
    rc = pipeline.main(_argv(files, "--expect-corpus-sha256", files["csha"], "--expect-overlay-sha256", files["osha"], out=out))
    assert rc == 4
    res = json.loads((out / "gate_result.json").read_text())
    assert res["passed"] is False and "CalibrationClamped" in res["reason"] and res["overlay_sha256"] == files["osha"]
    assert (out / "gate_report.md").exists() and not (out / "model_candidate.json").exists()


def test_power_veto_blocks_run(files, monkeypatch):
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 0.0001)
    out = files["dir"] / "veto"
    rc = pipeline.main(_argv(files, "--expect-corpus-sha256", files["csha"], "--expect-overlay-sha256", files["osha"], out=out))
    assert rc == pipeline.EXIT_POWER and not (out / "gate_result.json").exists()
    assert "güç yetersiz" in (out / "gate_report.md").read_text(encoding="utf-8")


# ------------------------------------------------------------------ mentor inceleme duzeltmeleri (fix 1, 3, 4, 6, 7, 8, 9, 11 + kaynak limitleri)
def _full_argv(f, out, recipe=R02, *extra):
    return _argv(f, "--expect-corpus-sha256", f["csha"], "--expect-overlay-sha256", f["osha"], *extra, recipe=recipe, out=out)


def test_fix1_single_run_guard_exit_9_never_overwrites(files, monkeypatch):
    out = files["dir"] / "once"
    out.mkdir()
    (out / "gate_result.json").write_text('{"sentinel": 1}')
    assert pipeline.main(_full_argv(files, out)) == pipeline.EXIT_EXISTS == 9
    assert (out / "gate_result.json").read_text() == '{"sentinel": 1}'
    assert len({pipeline.EXIT_SHA, pipeline.EXIT_MANIFEST, pipeline.EXIT_ORDER, pipeline.EXIT_POWER, pipeline.EXIT_EXISTS, pipeline.EXIT_DIRTY}) == 6
    # yalniz oof varsa da reddeder
    out2 = files["dir"] / "once2"
    out2.mkdir()
    (out2 / "oof_predictions.parquet").write_bytes(b"x")
    assert pipeline.main(_full_argv(files, out2)) == pipeline.EXIT_EXISTS
    # guc vetosu dali mevcut sonucu/raporu EZMEZ (once: 8 degil 9)
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 0.0001)
    out3 = files["dir"] / "once3"
    out3.mkdir()
    (out3 / "gate_result.json").write_text('{"sentinel": 3}')
    (out3 / "gate_report.md").write_text("ESKI RAPOR")
    assert pipeline.main(_full_argv(files, out3)) == pipeline.EXIT_EXISTS
    assert (out3 / "gate_report.md").read_text() == "ESKI RAPOR" and (out3 / "gate_result.json").read_text() == '{"sentinel": 3}'
    # --precheck-only sonucu uretmez: tek kosu korumasina takilmaz
    assert pipeline.main(_argv(files, "--precheck-only", out=out)) in (0, pipeline.EXIT_POWER)


def test_fix1_real_run_then_rerun_refused(files, monkeypatch):
    pytest.importorskip("lightgbm")
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 1.0)
    out = files["dir"] / "twice"
    assert pipeline.main(_full_argv(files, out)) in (0, 4)
    before = (out / "gate_result.json").read_text()
    assert pipeline.main(_full_argv(files, out)) == pipeline.EXIT_EXISTS
    assert (out / "gate_result.json").read_text() == before


def test_fix3_cli_rejects_overlay_built_from_other_corpus(files, tmp_path, capsys):
    om = tmp_path / "om.json"
    om.write_text(json.dumps(make_overlay_manifest(files["overlay"], files["corpus"], corpus_sha256="9" * 64)))
    rc = pipeline.main(_argv(files, "--overlay-manifest", str(om), "--expect-corpus-sha256", files["csha"],
                             "--expect-overlay-sha256", files["osha"]))
    assert rc == pipeline.EXIT_MANIFEST and "corpus_sha256" in capsys.readouterr().err


def test_fix4_order_guard_requires_same_hashes_and_real_r02(files):
    rec3, d = recipes.get(R03), files["dir"]
    kw = dict(corpus_sha256=files["csha"], overlay_sha256=files["osha"])
    assert pipeline.check_order_guard(rec3, _prior(d, False, files=files), **kw) is None
    assert "corpus_sha256" in pipeline.check_order_guard(rec3, _prior(d, False, files=files, corpus_sha256="0" * 64), **kw)
    assert "overlay_sha256" in pipeline.check_order_guard(rec3, _prior(d, False, files=files, overlay_sha256="0" * 64), **kw)
    assert "synthetic" in pipeline.check_order_guard(rec3, _prior(d, False, files=files, synthetic=True), **kw)
    p = _prior(d, False, files=files)                                                  # synthetic anahtari hic yok -> red
    body = json.loads(p.read_text())
    body.pop("synthetic")
    p2 = d / "prior_nosyn.json"
    p2.write_text(json.dumps(body))
    assert "synthetic" in pipeline.check_order_guard(rec3, p2, **kw)
    assert pipeline.check_order_guard(rec3, _prior(d, False, files=files, corpus_sha256=None), **kw)


def test_fix4_cli_exit7_when_prior_hashes_differ(files, capsys):
    prior = _prior(files["dir"], False, files=files, corpus_sha256="0" * 64)
    rc = pipeline.main(_full_argv(files, files["dir"] / "r3x", R03, "--prior-result", str(prior)))
    assert rc == pipeline.EXIT_ORDER and "corpus_sha256" in capsys.readouterr().err


def test_fix4_r02_blocked_exits_leave_no_gate_result(files, monkeypatch):
    """r02 cikis 8 (guc vetosu) ya da 3 (ozellik sagligi) gate_result.json yazmaz -> r03 icin --prior-result YOK -> r03 BLOKE (mentor karari)."""
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 0.0001)
    out = files["dir"] / "blocked_r02"
    assert pipeline.main(_full_argv(files, out)) == pipeline.EXIT_POWER
    assert not (out / "gate_result.json").exists()
    assert pipeline.check_order_guard(recipes.get(R03), out / "gate_result.json")        # dosya yok -> r03 reddedilir


def test_fix6_code_sha256_requires_all_13_keys(files):
    good = json.loads(files["manifest"].read_text())
    assert len(corpus_v2.EXPECTED_CODE_KEYS) == 13 and "src/trader_core/ml_features_v2.py" in corpus_v2.EXPECTED_CODE_KEYS
    assert set(good["code_sha256"]) == set(corpus_v2.EXPECTED_CODE_KEYS)
    assert corpus_v2.verify_corpus_manifest(good, files["corpus"])[0] == []
    for k in corpus_v2.EXPECTED_CODE_KEYS:
        short = {kk: v for kk, v in good["code_sha256"].items() if kk != k}
        errs, _ = corpus_v2.verify_corpus_manifest({**good, "code_sha256": short}, files["corpus"])
        assert any("eksik" in e and k in e for e in errs), k
    errs, _ = corpus_v2.verify_corpus_manifest({**good, "code_sha256": {CODE_REL: good["code_sha256"][CODE_REL]}}, files["corpus"])
    assert errs


def test_fix7_dirty_tree_refused_and_git_in_result(files, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "git_state", lambda: {"commit": "abc", "tree_clean": False, "dirty": [" M src/x.py"]})
    out = files["dir"] / "dirty"
    assert pipeline.main(_full_argv(files, out)) == pipeline.EXIT_DIRTY == 10
    assert "kirli" in capsys.readouterr().err and not (out / "gate_result.json").exists()


def test_fix7_gate_result_records_git_and_synthetic(files, monkeypatch):
    pytest.importorskip("lightgbm")
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 1.0)
    out = files["dir"] / "gitres"
    assert pipeline.main(_full_argv(files, out)) in (0, 4)
    res = json.loads((out / "gate_result.json").read_text())
    assert res["git"] == {"commit": "abc123def456", "tree_clean": True, "dirty": []} and res["synthetic"] is False
    guard = pipeline.check_order_guard(recipes.get(R03), out / "gate_result.json", corpus_sha256=files["csha"], overlay_sha256=files["osha"])
    assert (guard is None) == (res["passed"] is False)                                 # RED (4 ya da passed=false) r03'u acar, KABUL acmaz


def test_fix8_unresolved_taken_counted_separately():
    c = make_corpus(n_per_pair=40)
    c.loc[c.index[:6], "label_1r"] = np.nan
    ov = make_overlay(c, 0.5)
    ov.loc[ov.index[:3], "exit_ts"] = pd.NaT                                           # donem sonunda acik (ayri sayim)
    t, info = corpus_v2.load_run_table(c, ov, recipes.get(R02))
    keys = set(zip(ov["pair"], ov["ts"], ov["side"]))
    want = sum((r.pair, r.ts, r.side) in keys for r in c.iloc[:6].itertuples())
    assert info["dropped_unresolved"] == 6 and info["dropped_unresolved_taken"] == want
    assert info["dropped_taken_open_at_end"] >= 0 and "dropped_unresolved_taken" in info


def test_fix8_open_at_end_in_reports(files, monkeypatch):
    pytest.importorskip("lightgbm")
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 1.0)
    out = files["dir"] / "cnt"
    rc = pipeline.main(_full_argv(files, out))
    assert rc in (0, 4)
    md = (out / "gate_report.md").read_text(encoding="utf-8")
    assert "AÇIK kalan alınmış işlem" in md and "ALINMIŞ olup atılan" in md
    assert "dropped_taken_open_at_end" in json.loads((out / "gate_result.json").read_text())["run_table_info"]
    # kelepceli (RED) yol: rapor + gate_result.json ayni sayimlari tasir
    real = pipeline.models.fit_platt_info
    monkeypatch.setattr(pipeline.models, "fit_platt_info", lambda z, y, *a, **k: (real(z, y, *a, **k)[0], True))
    out2 = files["dir"] / "cnt_clamped"
    assert pipeline.main(_full_argv(files, out2)) == 4
    assert "AÇIK kalan alınmış işlem" in (out2 / "gate_report.md").read_text(encoding="utf-8")
    assert "dropped_unresolved_taken" in json.loads((out2 / "gate_result.json").read_text())["run_table_info"]


def test_fix9_sample_check_required_for_real_run(files, tmp_path, capsys):
    d = tmp_path / "sc"
    d.mkdir()
    for n in ("corpus_v2.parquet", "corpus_v2_taken.parquet", "corpus_v2.manifest.json", "corpus_v2_taken.manifest.json"):
        (d / n).write_bytes((files["dir"] / n).read_bytes())
    f = {**files, "dir": d, "corpus": d / "corpus_v2.parquet", "overlay": d / "corpus_v2_taken.parquet", "manifest": d / "corpus_v2.manifest.json"}
    assert pipeline.main(_full_argv(f, d / "o")) == pipeline.EXIT_MANIFEST and "elle kontrol" in capsys.readouterr().err   # dosya yok
    (d / "corpus_v2.sample_check.md").write_text("Bagimsiz yeniden hesap uyumu: 149/150\n", encoding="utf-8")
    assert pipeline.main(_full_argv(f, d / "o")) == pipeline.EXIT_MANIFEST and "150/150" in capsys.readouterr().err
    assert corpus_v2.verify_sample_check(files["manifest"]) == []
    # on hesap (--precheck-only) bu sarti aramaz
    assert pipeline.main(_argv(f, "--precheck-only", out=d / "o")) in (0, pipeline.EXIT_POWER)


def test_fix11_holdout_and_schema_errors_map_to_exit_6(files, monkeypatch, capsys):
    from trader_ml.schema import SchemaError
    for exc in (HoldoutViolation("kilitli donem"), SchemaError("sema")):
        def boom(*a, _e=exc, **k):
            raise _e
        monkeypatch.setattr(corpus_v2, "load_run_table", boom)
        assert pipeline.main(_full_argv(files, files["dir"] / "e6")) == pipeline.EXIT_MANIFEST == 6
        assert type(exc).__name__ in capsys.readouterr().err


def test_fix11_real_holdout_row_in_corpus_exits_6(files, tmp_path, capsys, monkeypatch):
    from trader_ml import guards as _G
    monkeypatch.setattr(_G, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    d = tmp_path / "ho"
    d.mkdir()
    c = pd.read_parquet(files["corpus"])
    c.loc[c.index[-1], "ts"] = HOLD0
    cp = d / "corpus_v2.parquet"
    c.to_parquet(cp, index=False)
    mp = d / "corpus_v2.manifest.json"
    mp.write_text(json.dumps(make_manifest(cp)))
    (d / "corpus_v2.sample_check.md").write_text("Bagimsiz yeniden hesap uyumu: 150/150\n", encoding="utf-8")
    (d / "corpus_v2_taken.manifest.json").write_text(json.dumps(make_overlay_manifest(files["overlay"], cp)))
    f = {**files, "dir": d, "corpus": cp, "manifest": mp, "csha": corpus_v2.sha256_path(cp)}
    om = d / "corpus_v2_taken.parquet"
    om.write_bytes(files["overlay"].read_bytes())
    f["overlay"] = om
    assert pipeline.main(_full_argv(f, d / "o")) == pipeline.EXIT_MANIFEST
    assert "HoldoutViolation" in capsys.readouterr().err                                    # manifest degil, gercek yukleme korumasi


def test_resource_limits_are_recipe_level_r01_unchanged():
    from trader_ml import resources
    assert recipes.get(config.RECIPE_ID).limits == {}                                      # r01: config varsayilanlari (450 MB / 20 dk)
    for rid in (R02, R03):
        lim = recipes.get(rid).limits
        assert lim["mem_mb"] > config.TRAIN_MEM_CAP_MB and lim["cpu_seconds"] >= config.TRAIN_TIME_LIMIT_S
    assert config.TRAIN_MEM_CAP_MB == 450 and config.TRAIN_TIME_LIMIT_S == 1200            # dondurulmus sabitler dokunulmaz
    import inspect
    assert inspect.signature(resources.apply_limits).parameters["mem_mb"].default == 450


def test_cli_applies_recipe_limits_not_research(files, monkeypatch):
    seen = []
    monkeypatch.setattr(pipeline, "apply_limits", lambda **kw: seen.append(kw))
    monkeypatch.setattr(pipeline, "POWER_VETO_RHO", 0.0001)                                # kosmadan veto ile dur
    out = files["dir"] / "lim"
    argv = [a for a in _full_argv(files, out) if a != "--research"]
    assert pipeline.main(argv) == pipeline.EXIT_POWER
    assert seen == [dict(recipes.get(R02).limits)]
