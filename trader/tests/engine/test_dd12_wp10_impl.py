"""DD-12 WP-10 (impl): kurulum suzgeci egitimi, paket, cok paketli sicak yukleme, kilit reddi (sentetik veri)."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from trader_core import ml_live_v2 as LV
from trader_core import ml_package as MP
from trader_engine import holdout as H
from trader_ml.setup_filter import features as F
from trader_ml.setup_filter import package as P
from trader_ml.setup_filter import train as T

# 23.11.2026 kullanici karari: kilit ACIK. Bu dosya kilit mekanizmasini sinar -> kilit KAPALI bayragiyla (conftest.egitim_kilitli); acik davranis tests/ml/test_kilit_acik_egitim.py.
pytestmark = pytest.mark.usefixtures("egitim_kilitli")


UTC = timezone.utc
T0 = datetime(2026, 11, 2, tzinfo=UTC)
NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _row(i, arm, r, ts=None, sess="open", lessons=(), ts_end=None, atr=1.0):
    ts = ts or T0 + timedelta(hours=i)
    x = LV.setup_feature_dict(side="long", regime="range", atr_ratio=atr, session_tag=sess, asset_class=None, pair="SOL/USDT",
                              planned_entry=100.0, planned_stop=98.0, planned_target=104.0, lesson_ids=lessons,
                              features={"atr_1h": 2.0 + (i % 3)})
    return {"id": i, "arm_id": arm, "ts": ts, "ts_end": ts_end, "x": x, "r": r}


def _synth(arm, n=80):
    # kapali seans kaybeder, acik seans kazanir (ogrenilebilir)
    return [_row(i, arm, -1.0 if i % 2 else 1.5, sess="closed" if i % 2 else "open") for i in range(n)]


def test_lock_constants_match_holdout():
    assert (T.LOCK_START, T.LOCK_END) == H.HOLDOUT


@pytest.mark.parametrize("ts,end,locked", [
    (datetime(2026, 4, 30, tzinfo=UTC), None, False), (datetime(2026, 5, 1, tzinfo=UTC), None, True),
    (datetime(2026, 10, 31, 23, tzinfo=UTC), None, True), (datetime(2026, 11, 1, tzinfo=UTC), None, False),
    (datetime(2026, 4, 29, tzinfo=UTC), datetime(2026, 5, 2, tzinfo=UTC), True)])
def test_in_lock(ts, end, locked):
    assert T.in_lock(ts, end) is locked


def test_train_arm_refuses_lock_rows_structurally():
    rows = _synth("T1@1h", 10) + [_row(99, "T1@1h", 1.0, ts=datetime(2026, 6, 1, tzinfo=UTC))]
    with pytest.raises(T.LockWindowError):
        T.train_arm("T1@1h", rows)
    with pytest.raises(T.LockWindowError):
        T.in_lock(datetime(2026, 6, 1))                      # naif zaman reddi


def test_train_all_drops_lock_and_counts():
    rows = _synth("A", 20) + [_row(100 + i, "A", 1.0, ts=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(hours=i)) for i in range(5)]
    pkgs, rep = T.train_all(rows, created_at=NOW)
    assert rep["lock_dropped"] == 5 and pkgs["A"]["meta"]["n_train"] == 20 and pkgs["A"]["meta"]["lock_dropped"] == 5
    assert pkgs["A"]["meta"]["train_window"]["start"] >= T.LOCK_END.isoformat()


def test_no_threshold_trains_on_first_opposite_pair_else_none():
    assert T.train_arm("A", []) is None
    assert T.train_arm("A", [_row(0, "A", 1.0), _row(1, "A", 0.5)]) is None           # tek sinif
    pkg = T.train_arm("A", [_row(0, "A", 1.0), _row(1, "A", -1.0)], created_at=NOW)   # iki satir, iki sinif => model
    assert pkg is not None and pkg["meta"]["n_train"] == 2


def test_model_learns_and_threshold_blocks_bad_setup():
    pkg = T.train_arm("A", _synth("A"), created_at=NOW)
    v = MP.view_from_package(MP.load_package(pkg, now=NOW))
    good = F.setup_feature_vector(v.features, _row(0, "A", 0, sess="open")["x"])
    bad = F.setup_feature_vector(v.features, _row(0, "A", 0, sess="closed")["x"])
    pg, pb = float(v.score(good)[0]), float(v.score(bad)[0])
    assert pg > pb and pg >= v.threshold > pb


def test_features_are_decision_time_only_and_lessons_included():
    rows = _synth("A", 10)
    rows[0]["x"] = dict(rows[0]["x"], **{"ders:seans_kapali:R1": 1.0})
    names = F.choose_feature_names([r["x"] for r in rows])
    assert "ders:seans_kapali:R1" in names
    F.assert_no_label_features(names)
    with pytest.raises(ValueError):
        F.assert_no_label_features(["sonuc:kazanc"])


def test_build_rows_notes_only_complete_r_and_never_feature():
    dec = [{"id": 1, "trade_id": 7, "arm_id": "A", "pair": "AAPL", "side": "short", "regime": "trend_down", "atr_ratio": 1.1,
            "session_tag": "closed", "lesson_ids": ["x:R1"], "features": {"atr_1h": 1.0}, "planned_entry": 10.0,
            "planned_stop": 11.0, "planned_target": 8.0, "bar_close_ts": T0}]
    notes = [{"trade_id": 7, "r": 2.0, "role": "label", "tags": {"sonuc": "kazanc"}, "lesson_ids": ["x:R1"]}]
    rows = T.build_rows(dec, {}, notes)
    assert rows[0]["r"] == 2.0 and not any("sonuc" in k for k in rows[0]["x"])
    assert rows[0]["x"]["cls_hisse"] == 1.0 and rows[0]["x"]["ders:x:R1"] == 1.0


def test_row_cap_keeps_newest():
    pkg = T.train_arm("A", _synth("A", 60), created_at=NOW, max_rows=30)
    assert pkg["meta"]["n_train"] == 30


def test_package_hash_expiry_roundtrip(tmp_path):
    pkg = T.train_arm("T1@1h", _synth("T1@1h"), created_at=NOW)
    path = P.save_package(pkg, tmp_path)
    MP.load_package(path, now=NOW)
    assert pkg["meta"]["expires_at"] == (NOW + timedelta(days=21)).isoformat()
    with pytest.raises(MP.PackageError):
        MP.load_package(path, now=NOW + timedelta(days=22))
    bad = json.loads(path.read_text())
    bad["threshold"] = 0.99
    with pytest.raises(MP.PackageError):
        MP.load_package(bad, now=NOW)


def test_save_keeps_one_prev_version(tmp_path):
    p1 = T.train_arm("A", _synth("A"), created_at=NOW)
    P.save_package(p1, tmp_path)
    p2 = T.train_arm("A", _synth("A", 40), created_at=NOW + timedelta(days=1))
    P.save_package(p2, tmp_path)
    assert (tmp_path / "A.prev.json").exists()
    assert json.loads((tmp_path / "A.prev.json").read_text())["meta"]["model_hash"] == p1["meta"]["model_hash"]


def test_packageset_multi_arm_hot_reload_and_fallback(tmp_path):
    ps = MP.PackageSet(tmp_path)
    assert ps.decide("A", {}, now=NOW) == MP.SetupDecision(True, None, "ml_no_model")      # paket yok => gecer
    P.save_package(T.train_arm("A", _synth("A"), created_at=NOW), tmp_path)
    P.save_package(T.train_arm("T1@4h", _synth("T1@4h"), created_at=NOW), tmp_path)
    (tmp_path / "bozuk.json").write_text("{nope")
    r = ps.reload(now=NOW)
    assert r["loaded"] == ["A", "T1@4h"] and "bozuk" in r["rejected"]
    good = _row(0, "A", 0, sess="open")["x"]
    bad = _row(0, "A", 0, sess="closed")["x"]
    assert ps.decide("A", good, now=NOW).passed and not ps.decide("A", bad, now=NOW).passed
    assert ps.decide("A", bad, now=NOW + timedelta(days=30)).code == "ml_no_model"           # sure doldu => gecer
    assert ps.reload(now=NOW)["loaded"] == []                                                # degismeyen dosya atlanir
    P.save_package(T.train_arm("A", _synth("A", 40), created_at=NOW), tmp_path)             # sicak yukleme
    assert ps.reload(now=NOW)["loaded"] == ["A"]
    (tmp_path / "A.json").unlink()
    assert "A" in ps.reload(now=NOW)["removed"]


def test_paper_only_refused_when_not_allowed(tmp_path):
    P.save_package(T.train_arm("A", _synth("A"), created_at=NOW), tmp_path)
    ps = MP.PackageSet(tmp_path, allow_paper_only=False)
    assert ps.reload(now=NOW)["loaded"] == [] and "A" in ps.rejected()


def test_train_parity_with_engine_vector():
    pkg = T.train_arm("A", _synth("A"), created_at=NOW)
    names = pkg["meta"]["features"]
    x = _row(3, "A", 0, sess="open")["x"]
    assert np.array_equal(F.matrix(names, [x])[0], LV.setup_feature_vector(names, x), equal_nan=True)


def test_script_end_to_end_with_real_ledger(tmp_path):
    import ml_retrain_run as R
    from trader_core import ledger as L
    lp = tmp_path / "ledger.sqlite"
    L.open_ledger(lp, "learner", create=True, migrate=True).close()
    rc = R.main(["--once", "--ledger", str(lp), "--models-dir", str(tmp_path / "m"), "--no-m1",
                 "--paper-models-csv", str(tmp_path / "pm.csv")], now_fn=lambda: NOW, env={})
    assert rc == 0 and (tmp_path / "pm.csv").read_text().splitlines().__len__() == 2
    assert R.main(["--once", "--ledger", str(tmp_path / "yok.sqlite")], now_fn=lambda: NOW, env={}) == 3


def test_packageset_runtime_dir_wins_then_seed_fallback(tmp_path):
    """Calisma zamani dizini once; depodaki tohum yalniz calisma zamaninda olmayan dosyayi tamamlar (tohum yazilmaz)."""
    runtime, seed = tmp_path / "runtime", tmp_path / "seed"
    P.save_package(T.train_arm("M1@1h", _synth("M1@1h"), created_at=NOW), seed)
    P.save_package(T.train_arm("M1@4h", _synth("M1@4h"), created_at=NOW), seed)
    P.save_package(T.train_arm("M1@4h", _synth("M1@4h", 40), created_at=NOW), runtime)
    seed_before = {p.name: p.read_bytes() for p in seed.glob("*.json")}
    ps = MP.PackageSet(runtime, fallback_dirs=(seed,))
    r = ps.reload(now=NOW)
    assert r["loaded"] == ["M1@1h", "M1@4h"]
    assert json.loads((runtime / "M1@4h.json").read_text())["meta"]["n_train"] == 40
    assert not (runtime / "M1@1h.json").exists()                              # tohum okunur, kopyalanmaz
    assert {p.name: p.read_bytes() for p in seed.glob("*.json")} == seed_before  # tohum degismez
