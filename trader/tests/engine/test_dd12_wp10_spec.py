"""Independent spec tests for DD-12 WP-10 (Kurulum bazli ML suzgeci + gece egitimi).

Written from docs/motor/dd12-capraz-varlik-spec.md (sec. 5, 5.2, 5.5, 9 WP-10, D-T26) and the owner decisions at the
end of otonom-trading-arastirma/tasarim-kararlari.md: ML is active from the FIRST trade, no minimum-sample threshold
(a model that cannot be fit => pass-through `ml_no_model`, never a block); training data = paper decisions
(+ counterfactual outcomes) + code-written trade-note tags (`trader_core.trade_notes.export_ml_rows`); one package per
setup (arm_id); sha256 + expiry integrity; training refuses any row dated 2026-05-01..2026-11-01 (lock period);
a new package is hot-reloaded; the retrain script is idempotent and safe on an empty ledger.
The implementation was not read.  Names not fixed by the spec are tested against the real public API (train.{collect_rows,build_rows,train_arm,train_all,in_lock,assert_no_lock,LockWindowError},
package.{build_package,save_package}, features.choose_feature_names, ml_package.PackageSet/SetupDecision, ml_live_v2.setup_feature_dict).
Synthetic data only; no network.
"""
from __future__ import annotations

import configparser
import hashlib
import importlib
import importlib.util
import inspect
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# 23.11.2026 kullanici karari: kilit ACIK. Bu dosya kilit mekanizmasini sinar -> kilit KAPALI bayragiyla (conftest.egitim_kilitli); acik davranis tests/ml/test_kilit_acik_egitim.py.
pytestmark = pytest.mark.usefixtures("egitim_kilitli")


UTC = timezone.utc
TRADER = Path(__file__).resolve().parents[2]
SRC = TRADER / "src"
LOCK_START = datetime(2026, 5, 1, tzinfo=UTC)
LOCK_END = datetime(2026, 11, 1, tzinfo=UTC)
NOW = datetime(2026, 11, 20, 3, 10, tzinfo=UTC)



# ------------------------------------------------------------------ files / deployment (spec sec. 5.2, 9)
def test_expected_files_exist():
    for rel in ("src/trader_ml/setup_filter/features.py", "src/trader_ml/setup_filter/train.py",
                "src/trader_ml/setup_filter/package.py", "scripts/ml_retrain_run.py",
                "deploy/trader-ml-retrain.service", "deploy/trader-ml-retrain.timer"):
        assert (TRADER / rel).is_file(), rel


def _unit(name):
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string((TRADER / "deploy" / name).read_text())
    return cp


def test_service_limits_and_oneshot():
    cp = _unit("trader-ml-retrain.service")
    s = cp["Service"]
    assert s.get("Type") == "oneshot"
    assert s.get("MemoryHigh") == "250M" and s.get("MemoryMax") == "350M"   # WP-18: M1 olcumu (tepe ~263 MB) ile MemoryMax 300M -> 350M
    assert s.get("CPUQuota") == "50%" and s.get("Nice") == "10"
    assert "ml_retrain_run" in s.get("ExecStart", "")


def test_timer_runs_0040_utc_before_dl1():
    """24.11 kullanici karari: M1 gece egitimi 00:40 UTC (03:40 TSI); DL1 egitimi 01:00 UTC'de arkasindan baslar (workflow cron'u). Not isi (02:55) sonradan."""
    txt = (TRADER / "deploy" / "trader-ml-retrain.timer").read_text()
    assert re.search(r"OnCalendar=\*-\*-\* 00:40:00 UTC", txt)
    assert "Persistent" in txt
    dl1 = (TRADER.parent / ".github" / "workflows" / "dl1-egitim.yml").read_text()
    assert 'cron: "0 1 * * *"' in dl1, "DL1 egitimi M1'in hemen arkasindan (01:00 UTC) baslar"


def test_setup_filter_uses_no_pandas_and_no_trader_engine():
    for f in (SRC / "trader_ml" / "setup_filter").glob("*.py"):
        t = f.read_text()
        assert not re.search(r"^\s*(import|from)\s+pandas", t, re.M), f"{f.name} imports pandas (spec: numpy+lightgbm only)"
        assert not re.search(r"^\s*(import|from)\s+trader_engine", t, re.M), f"{f.name} imports trader_engine"


# ------------------------------------------------------------------ real API
from trader_core import ml_live_v2 as LV  # noqa: E402
from trader_core import ml_package as MP  # noqa: E402
from trader_ml.setup_filter import features as F  # noqa: E402
from trader_ml.setup_filter import package as P  # noqa: E402
from trader_ml.setup_filter import train as T  # noqa: E402


def _x(win, lessons=(), session="open"):
    return LV.setup_feature_dict(
        side="long", regime="range", atr_ratio=1.1 + 0.2 * win, session_tag=session, asset_class="kripto",
        pair="ETH/USDT", planned_entry=2000.0, planned_stop=1960.0 - 20 * win, planned_target=2100.0,
        rh_touches=2 + win, rl_touches=3, lesson_ids=list(lessons), features={"wick_ratio": 0.2 + 0.5 * win, "rr": 2.0 + win})


def _row(i, arm, ts, win, *, ts_end=None, lessons=()):
    return {"id": i, "arm_id": arm, "ts": ts, "ts_end": ts_end, "x": _x(win, lessons), "r": 1.2 if win else -1.0}


def _rows(arm, n, *, start=datetime(2026, 11, 2, tzinfo=UTC), both=True):
    return [_row(i, arm, start + timedelta(hours=i), int((i % 2 == 0) if both else 1)) for i in range(n)]


def _has_pkg(pkgs, arm):
    return arm in pkgs and pkgs[arm]["model"] is not None


# ------------------------------------------------------------------ features: decision-time only
def test_setup_feature_dict_takes_session_tag_and_lesson_ids():
    sig = inspect.signature(LV.setup_feature_dict).parameters
    assert "session_tag" in sig and "lesson_ids" in sig and "asset_class" in sig
    d = _x(1, lessons=["L7"], session="weekend")
    assert d["sess_weekend"] == 1.0 and d["sess_open"] == 0.0
    assert d["ders:L7"] == 1.0 and d["cls_kripto"] == 1.0


def test_feature_names_exclude_post_trade_labels():
    names = F.choose_feature_names([_x(1, ["L7"]), _x(0)])
    blob = " ".join(names).lower()
    for bad in ("r_multiple", "exit_reason", "outcome", "giris_kalitesi", "stop_yeri", "kacinilabilir", "net_r", "pnl", "sonuc"):
        assert bad not in blob, names
    assert len(set(names)) == len(names)
    assert "ders:L7" in names and "sess_open" in names


def test_label_names_are_refused_as_features():
    with pytest.raises(Exception):
        F.assert_no_label_features(["atr_ratio", "r_multiple"])


def test_note_tags_do_not_change_feature_vector():
    """Post-trade note tags/labels attached to a decision must not reach the decision-time features."""
    base = dict(side="long", regime="range", atr_ratio=1.2, session_tag="open", asset_class="kripto", pair="ETH/USDT",
                planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, rh_touches=2, rl_touches=3,
                lesson_ids=["L1"], features={"rr": 2.0})
    a = LV.setup_feature_dict(**base)
    b = LV.setup_feature_dict(**dict(base, features={"rr": 2.0, "tags": "giris_kalitesi:kotu"}))
    assert a == b


def test_build_rows_uses_counterfactual_and_notes_only_as_target():
    dec = {"id": 1, "arm_id": "R1@1h", "pair": "ETH/USDT", "side": "long", "regime": "range", "atr_ratio": 1.1,
           "session_tag": "open", "lesson_ids": ["L1"], "features": {"rr": 2.0}, "planned_entry": 2000.0,
           "planned_stop": 1960.0, "planned_target": 2100.0, "rh_touches": 2, "rl_touches": 3,
           "bar_close_ts": datetime(2026, 11, 3, tzinfo=UTC), "trade_id": 5}
    dec2 = dict(dec, id=2, trade_id=None)
    out = {2: (-0.7, datetime(2026, 11, 4, tzinfo=UTC))}                     # not taken: counterfactual outcome
    notes = [{"trade_id": 5, "r": 1.5, "role": "label", "tags": {"giris_kalitesi": "iyi"}, "lesson_ids": ["L1"]}]
    rows = T.build_rows([dec, dec2], out, notes)
    assert {r["id"]: r["r"] for r in rows} == {1: 1.5, 2: -0.7}
    for r in rows:
        assert not any(k.startswith(("giris", "tag", "not:")) for k in r["x"])


# ------------------------------------------------------------------ training: no threshold, per-arm, pass-through
def test_two_opposite_class_rows_are_enough_for_a_model():
    pk, _ = T.train_all(_rows("R1@1h", 2), created_at=NOW)
    assert _has_pkg(pk, "R1@1h")


def test_single_class_gives_no_model_not_exception():
    pk, rep = T.train_all(_rows("R1@1h", 6, both=False), created_at=NOW)
    assert "R1@1h" not in pk and rep["arms"]["R1@1h"]["status"] == "no_model"
    assert T.train_arm("R1@1h", _rows("R1@1h", 6, both=False)) is None


def test_empty_rows_is_safe():
    pk, rep = T.train_all([], created_at=NOW)
    assert pk == {} and T.train_arm("R1@1h", []) is None


def test_one_package_per_arm_id():
    pk, _ = T.train_all(_rows("R1@1h", 10) + _rows("PB@4h", 10), created_at=NOW)
    assert set(pk) == {"R1@1h", "PB@4h"}
    assert pk["R1@1h"]["meta"]["arm_id"] == "R1@1h" and pk["PB@4h"]["meta"]["arm_id"] == "PB@4h"


def test_arm_with_single_class_does_not_block_other_arms():
    pk, _ = T.train_all(_rows("R1@1h", 10) + _rows("PB@4h", 6, both=False), created_at=NOW)
    assert set(pk) == {"R1@1h"}


def test_training_is_deterministic():
    rows = _rows("R1@1h", 12)
    a, _ = T.train_all(rows, created_at=NOW)
    b, _ = T.train_all(rows, created_at=NOW)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_lesson_ids_become_features_and_are_recorded():
    rows = [_row(i, "R1@1h", datetime(2026, 11, 2, tzinfo=UTC) + timedelta(hours=i), i % 2 == 0,
                 lessons=["L9"] if i % 2 == 0 else []) for i in range(8)]
    pk = T.train_arm("R1@1h", rows, created_at=NOW)
    assert "ders:L9" in pk["meta"]["features"] and "L9" in pk["meta"]["lesson_ids"]


def test_row_cap_50k():
    assert T.MAX_ROWS == 50_000


# ------------------------------------------------------------------ lock period
@pytest.mark.parametrize("ts", [LOCK_START, datetime(2026, 7, 15, 12, tzinfo=UTC), LOCK_END - timedelta(seconds=1)])
def test_training_refuses_row_inside_lock_period(ts):
    rows = _rows("R1@1h", 8)
    rows[3] = _row(3, "R1@1h", ts, 1)
    with pytest.raises(T.LockWindowError):
        T.train_arm("R1@1h", rows)
    with pytest.raises(T.LockWindowError):
        T.assert_no_lock(rows)


def test_row_whose_outcome_window_reaches_lock_is_locked():
    r = _row(1, "R1@1h", LOCK_START - timedelta(days=1), 1, ts_end=LOCK_START + timedelta(hours=1))
    assert T.in_lock(r["ts"], r["ts_end"])
    with pytest.raises(T.LockWindowError):
        T.train_arm("R1@1h", [r] + _rows("R1@1h", 4))


@pytest.mark.parametrize("ts", [LOCK_START - timedelta(seconds=1), LOCK_END, LOCK_END + timedelta(days=1)])
def test_training_accepts_rows_outside_lock_period(ts):
    rows = _rows("R1@1h", 8)
    rows[3] = _row(3, "R1@1h", ts, 1)
    assert T.train_arm("R1@1h", rows, created_at=NOW) is not None


def test_naive_timestamp_is_refused():
    with pytest.raises(T.LockWindowError):
        T.in_lock(datetime(2026, 11, 5))


def test_train_all_drops_and_counts_lock_rows_without_using_them():
    clean = _rows("R1@1h", 8)
    locked = [_row(100 + i, "R1@1h", datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=i), i % 2) for i in range(5)]
    a, rep = T.train_all(clean + locked, created_at=NOW)
    b, _ = T.train_all(clean, created_at=NOW)
    assert rep["lock_dropped"] == 5
    assert a["R1@1h"]["meta"]["data_hash"] == b["R1@1h"]["meta"]["data_hash"], "locked rows must not influence training"


def test_locked_only_arm_gets_no_model():
    locked = [_row(i, "R1@1h", datetime(2026, 6, 1, tzinfo=UTC) + timedelta(hours=i), i % 2) for i in range(6)]
    pk, rep = T.train_all(locked, created_at=NOW)
    assert pk == {} and rep["lock_dropped"] == 6


# ------------------------------------------------------------------ package integrity (hash / expiry)
def _pkg(arm="R1@1h"):
    pk = T.train_arm(arm, _rows(arm, 10), created_at=NOW)
    assert pk is not None
    return pk


def test_package_has_sha256_and_arm_id():
    m = _pkg()["meta"]
    assert re.fullmatch(r"[0-9a-f]{64}", m["model_hash"]) and re.fullmatch(r"[0-9a-f]{64}", m["feature_list_hash"])
    assert m["arm_id"] == "R1@1h" and m["created_at"] and m["expires_at"]


def test_saved_package_roundtrips_and_keeps_one_backup(tmp_path):
    p1 = P.save_package(_pkg(), tmp_path)
    assert p1.is_file()
    MP.load_package(p1, now=NOW)
    pkg2 = T.train_arm("R1@1h", _rows("R1@1h", 12), created_at=NOW + timedelta(days=1))
    P.save_package(pkg2, tmp_path)
    assert list(tmp_path.glob("*.prev.json")), "previous version must be kept as a backup"


def test_tampered_package_is_rejected(tmp_path):
    path = P.save_package(_pkg(), tmp_path)
    pkg = json.loads(path.read_text())
    pkg["threshold"] = 0.001
    path.write_text(json.dumps(pkg))
    with pytest.raises(MP.PackageError):
        MP.load_package(path, now=NOW)
    pkg = _pkg()
    pkg["meta"]["features"] = list(reversed(pkg["meta"]["features"]))
    with pytest.raises(MP.PackageError):
        MP.load_package(pkg, now=NOW)


def test_expired_package_is_rejected():
    pkg = _pkg()
    MP.load_package(pkg, now=NOW + timedelta(days=1))
    with pytest.raises(MP.PackageError):
        MP.load_package(pkg, now=NOW + timedelta(days=MP.MODEL_EXPIRY_DAYS + 1))


def test_extended_expires_at_cannot_outlive_21_days():
    pkg = _pkg()
    pkg["meta"]["expires_at"] = (NOW + timedelta(days=400)).isoformat()
    with pytest.raises(MP.PackageError):
        MP.load_package(pkg, now=NOW + timedelta(days=30))


# ------------------------------------------------------------------ engine: PackageSet pass-through + hot reload
def _live_row(win):
    return _x(win)


def test_no_model_for_arm_passes_through(tmp_path):
    ps = MP.PackageSet(tmp_path / "models")                  # directory does not even exist
    ps.reload(now=NOW)
    d = ps.decide("R1@1h", _live_row(0), now=NOW)
    assert d.passed is True and d.code == "ml_no_model" and d.score is None


def test_arm_without_package_passes_while_other_arm_is_scored(tmp_path):
    P.save_package(_pkg("R1@1h"), tmp_path)
    ps = MP.PackageSet(tmp_path)
    assert ps.reload(now=NOW)["loaded"] == ["R1@1h"]
    d = ps.decide("R1@1h", _live_row(1), now=NOW)
    assert d.code in ("ok", "ml_below_threshold") and d.score is not None and 0.0 <= d.score <= 1.0
    assert d.passed == (d.code == "ok")
    other = ps.decide("PB@4h", _live_row(0), now=NOW)
    assert other.passed and other.code == "ml_no_model"


def test_filter_prefers_winners_on_separable_data(tmp_path):
    P.save_package(_pkg(), tmp_path)
    ps = MP.PackageSet(tmp_path)
    ps.reload(now=NOW)
    assert ps.decide("R1@1h", _live_row(1), now=NOW).score > ps.decide("R1@1h", _live_row(0), now=NOW).score


def test_expired_package_passes_through(tmp_path):
    P.save_package(_pkg(), tmp_path)
    ps = MP.PackageSet(tmp_path)
    ps.reload(now=NOW)
    late = NOW + timedelta(days=MP.MODEL_EXPIRY_DAYS + 2)
    d = ps.decide("R1@1h", _live_row(0), now=late)
    assert d.passed and d.code == "ml_no_model"


def test_hot_reload_picks_up_new_package_without_restart(tmp_path):
    ps = MP.PackageSet(tmp_path)
    ps.reload(now=NOW)
    assert ps.decide("R1@1h", _live_row(0), now=NOW).code == "ml_no_model"
    P.save_package(_pkg(), tmp_path)
    res = ps.reload(now=NOW)
    assert res["loaded"] == ["R1@1h"] and ps.arms() == ["R1@1h"]
    assert ps.decide("R1@1h", _live_row(0), now=NOW).code in ("ok", "ml_below_threshold")
    first = ps.view("R1@1h").model_id
    pkg2 = T.train_arm("R1@1h", _rows("R1@1h", 14), created_at=NOW + timedelta(hours=1))
    P.save_package(pkg2, tmp_path)
    ps.reload(now=NOW + timedelta(hours=2))
    assert ps.view("R1@1h").model_id != first, "new package for the same arm must replace the old one"


def test_broken_file_only_affects_its_arm_and_engine_continues(tmp_path):
    P.save_package(_pkg("R1@1h"), tmp_path)
    ps = MP.PackageSet(tmp_path)
    ps.reload(now=NOW)
    (tmp_path / "PB@4h.json").write_text("{broken")
    res = ps.reload(now=NOW)
    assert "PB@4h" in res["rejected"] and ps.arms() == ["R1@1h"]
    assert ps.decide("PB@4h", _live_row(0), now=NOW).passed
    assert ps.decide("R1@1h", _live_row(1), now=NOW).code in ("ok", "ml_below_threshold")


def test_tampered_file_is_rejected_by_set(tmp_path):
    path = P.save_package(_pkg(), tmp_path)
    pkg = json.loads(path.read_text())
    pkg["threshold"] = 0.999
    path.write_text(json.dumps(pkg))
    ps = MP.PackageSet(tmp_path)
    res = ps.reload(now=NOW)
    assert res["loaded"] == [] and res["rejected"]
    assert ps.decide("R1@1h", _live_row(0), now=NOW).passed


def test_arm_id_must_match_file_name(tmp_path):
    path = P.save_package(_pkg("R1@1h"), tmp_path)
    path.rename(tmp_path / "OTHER@1h.json")
    ps = MP.PackageSet(tmp_path)
    assert ps.reload(now=NOW)["loaded"] == []


def test_paper_only_package_refused_when_not_allowed(tmp_path):
    """Testnet/live must never load a package that did not pass the gate (existing rule, kept)."""
    P.save_package(_pkg(), tmp_path)
    ps = MP.PackageSet(tmp_path, allow_paper_only=False)
    res = ps.reload(now=NOW)
    assert res["loaded"] == [] and res["rejected"]


# ------------------------------------------------------------------ retrain script
def _script():
    path = TRADER / "scripts" / "ml_retrain_run.py"
    assert path.is_file()
    spec = importlib.util.spec_from_file_location("ml_retrain_run_spec", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SRC))
    spec.loader.exec_module(mod)
    return mod


def _mk_ledger(path, n=6, start=datetime(2026, 11, 2, 6, tzinfo=UTC)):
    from trader_core import ledger as L
    led = L.open_ledger(path, "learner", clock=lambda: NOW)
    led.init_params({"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
                     "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5,
                     "trigger_tf": "1h"}, reason="x")
    for i in range(1, n + 1):
        bar = start + timedelta(hours=i)
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup="R1", regime="range",
            atr_ratio=1.1, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
            features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5,
                      "edge_dist_atr": 0.1},
            planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1,
            veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
            size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
            final_action="entered", skip_reason=None, arm_id="R1@1h", session_tag="open"))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        win = i % 2 == 0
        led.record_trade_exit(L.TradeExit(i, bar + timedelta(hours=1), 2079.0 if win else 1960.0,
                                          "target" if win else "stop", 2100.0, 0.3, 0.1))
    return led


def _run_script(mod, ledger, models_dir, csv_path, cf=None):
    argv = ["--once", "--ledger", str(ledger), "--models-dir", str(models_dir), "--paper-models-csv", str(csv_path),
            "--m1-models-dir", str(Path(models_dir).parent / "pa_proposer")]   # WP-18: M1 depoya yazmasin (gecici dizin)
    if cf:
        argv += ["--cf", str(cf)]
    return mod.main(argv, now_fn=lambda: NOW)


def _snapshot(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).rglob("*")) if p.is_file()}


def test_retrain_script_safe_on_empty_ledger(tmp_path):
    from trader_core import ledger as L
    p = tmp_path / "l.sqlite"
    L.open_ledger(p, "learner", clock=lambda: NOW).close()
    md = tmp_path / "models"
    assert _run_script(_script(), p, md, tmp_path / "pm.csv") == 0
    assert not list(md.glob("*.json")) if md.exists() else True
    ps = MP.PackageSet(md)
    ps.reload(now=NOW)
    assert ps.decide("R1@1h", _live_row(0), now=NOW).passed


def test_retrain_script_produces_packages_and_is_idempotent(tmp_path):
    mod = _script()
    p = tmp_path / "l.sqlite"
    _mk_ledger(p).close()
    md = tmp_path / "models"
    csvp = tmp_path / "pm.csv"
    assert _run_script(mod, p, md, csvp) == 0
    first = _snapshot(md)
    assert "R1@1h.json" in first, sorted(first)
    ps = MP.PackageSet(md)
    assert ps.reload(now=NOW)["loaded"] == ["R1@1h"]
    assert _run_script(mod, p, md, csvp) == 0
    second = _snapshot(md)
    assert second["R1@1h.json"] == first["R1@1h.json"], "same inputs and same clock => identical package"
    assert "nightly" in csvp.read_text()


def test_retrain_script_never_trains_on_locked_rows(tmp_path):
    mod = _script()
    p = tmp_path / "l.sqlite"
    _mk_ledger(p, start=datetime(2026, 7, 1, 6, tzinfo=UTC)).close()      # all decisions inside lock period
    md = tmp_path / "models"
    assert _run_script(mod, p, md, tmp_path / "pm.csv") in (0, 3)
    assert not list(md.glob("*.json")) if md.exists() else True


def test_retrain_script_missing_ledger_fails_cleanly(tmp_path):
    md = tmp_path / "models"
    rc = _run_script(_script(), tmp_path / "absent.sqlite", md, tmp_path / "pm.csv")
    assert rc == 3
    assert not list(md.glob("*.json")) if md.exists() else True


def test_ml_package_old_api_still_importable():
    for n in ("load_package", "PackageError", "MODEL_EXPIRY_DAYS", "view_from_package", "load_model_view"):
        assert hasattr(MP, n), n
    assert MP.MODEL_EXPIRY_DAYS == 21
