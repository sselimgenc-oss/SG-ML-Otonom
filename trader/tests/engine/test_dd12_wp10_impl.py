"""DD-12 WP-10 (impl): M1 paketi (hash/sure/kilit), cok paketli sicak yukleme (`PackageSet`), gece birimi dosyalari ve gece betigi
(sentetik veri). 24.11 kullanici karari: kurulum suzgeci (setup_filter) silindi; paket okuyucu ve gece egitimi yalniz M1 icindir."""
from __future__ import annotations

import configparser
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

TRADER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TRADER / "scripts"))

from trader_core import ml_package as MP
from trader_engine import holdout as H
from trader_ml.pa_proposer import features as PF
from trader_ml.pa_proposer import package as PK
from trader_ml.pa_proposer import train as T

# 23.11.2026 kullanici karari: kilit ACIK. Bu dosya kilit mekanizmasini sinar -> kilit KAPALI bayragiyla (conftest.egitim_kilitli); acik davranis tests/ml/test_kilit_acik_egitim.py.
pytestmark = pytest.mark.usefixtures("egitim_kilitli")

UTC = timezone.utc
T0 = datetime(2026, 11, 2, tzinfo=UTC)
NOW = datetime(2026, 11, 20, 3, 10, tzinfo=UTC)
NF = len(PF.FEATURE_NAMES)


def _row(i, y, *, ts=None, ts_end=None):
    rng = np.random.default_rng(100 + i)
    x = rng.normal(size=NF)
    x[0] += 2.0 * y                                   # ilk ozellik sonucla bagli (ogrenilebilir)
    return {"ts": ts or T0 + timedelta(hours=i), "ts_end": ts_end, "side": "long" if i % 2 else "short", "x": x, "y": float(y)}


def _rows(n=60, **kw):
    return [_row(i, i % 2 == 0, **kw) for i in range(n)]


def _pkg(arm="M1@1h", n=60, created=NOW):
    pkg = T.train_tf(_rows(n), arm_id=arm, created_at=created)
    assert pkg is not None
    return pkg


def _score(ps, arm, y):
    v = ps.view(arm)
    return float(v.score(_row(3, y)["x"][None, :])[0])


# ------------------------------------------------------------------ kilit sabitleri ve yapisal ret
def test_lock_constants_match_holdout():
    assert (T.LOCK_START, T.LOCK_END) == H.HOLDOUT


@pytest.mark.parametrize("ts,end,locked", [
    (datetime(2026, 4, 30, tzinfo=UTC), None, False), (datetime(2026, 5, 1, tzinfo=UTC), None, True),
    (datetime(2026, 10, 31, 23, tzinfo=UTC), None, True), (datetime(2026, 11, 1, tzinfo=UTC), None, False),
    (datetime(2026, 4, 29, tzinfo=UTC), datetime(2026, 5, 2, tzinfo=UTC), True)])
def test_in_lock(ts, end, locked):
    assert T.in_lock(ts, end) is locked


def test_train_refuses_lock_rows_structurally():
    rows = _rows(10) + [_row(99, 1, ts=datetime(2026, 6, 1, tzinfo=UTC))]
    with pytest.raises(T.LockWindowError):
        T.train_tf(rows, arm_id="M1@1h")
    with pytest.raises(T.LockWindowError):
        T.in_lock(datetime(2026, 6, 1))                      # naif zaman reddi


def test_split_lock_drops_and_counts():
    rows = _rows(20) + [_row(100 + i, 1, ts=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(hours=i)) for i in range(5)]
    kept, dropped = T.split_lock(rows)
    assert len(kept) == 20 and dropped == 5


def test_no_model_when_data_missing_or_single_class():
    assert T.train_tf([], arm_id="M1@1h") is None
    assert T.train_tf([_row(0, 1), _row(1, 1)], arm_id="M1@1h") is None            # tek sinif
    pkg = T.train_tf([_row(0, 1), _row(1, 0)], arm_id="M1@1h", created_at=NOW)     # iki satir, iki sinif => model
    assert pkg is not None and pkg["meta"]["n_train"] == 2
    assert T.no_model_reason(1).startswith("model yok")


def test_row_cap_keeps_newest():
    assert T.train_tf(_rows(60), arm_id="M1@1h", created_at=NOW, max_rows=30)["meta"]["n_train"] == 30


# ------------------------------------------------------------------ paket butunlugu (hash / sure)
def test_package_has_sha256_and_arm_id():
    m = _pkg()["meta"]
    assert re.fullmatch(r"[0-9a-f]{64}", m["model_hash"]) and re.fullmatch(r"[0-9a-f]{64}", m["feature_list_hash"])
    assert m["arm_id"] == "M1@1h" and m["created_at"] and m["expires_at"]


def test_package_hash_expiry_roundtrip(tmp_path):
    pkg = _pkg()
    path = PK.save_package(pkg, tmp_path)
    MP.load_package(path, now=NOW)
    assert pkg["meta"]["expires_at"] == (NOW + timedelta(days=21)).isoformat()
    with pytest.raises(MP.PackageError):
        MP.load_package(path, now=NOW + timedelta(days=22))
    bad = json.loads(path.read_text())
    bad["threshold"] = 0.99
    with pytest.raises(MP.PackageError):
        MP.load_package(bad, now=NOW)


def test_extended_expires_at_cannot_outlive_21_days():
    pkg = _pkg()
    pkg["meta"]["expires_at"] = (NOW + timedelta(days=400)).isoformat()
    with pytest.raises(MP.PackageError):
        MP.load_package(pkg, now=NOW + timedelta(days=30))


def test_save_keeps_one_prev_version(tmp_path):
    p1 = _pkg()
    PK.save_package(p1, tmp_path)
    PK.save_package(_pkg(n=40, created=NOW + timedelta(days=1)), tmp_path)
    assert json.loads((tmp_path / "M1@1h.prev.json").read_text())["meta"]["model_hash"] == p1["meta"]["model_hash"]


# ------------------------------------------------------------------ PackageSet: cok paket, sicak yukleme, tohum
def test_packageset_empty_dir_has_no_views(tmp_path):
    ps = MP.PackageSet(tmp_path / "yok")                     # dizin yok
    assert ps.reload(now=NOW) == {"loaded": [], "removed": [], "rejected": {}} and ps.view("M1@1h") is None


def test_packageset_scores_winners_above_losers(tmp_path):
    PK.save_package(_pkg(), tmp_path)
    ps = MP.PackageSet(tmp_path)
    assert ps.reload(now=NOW)["loaded"] == ["M1@1h"] and ps.arms() == ["M1@1h"]
    assert _score(ps, "M1@1h", 1) > _score(ps, "M1@1h", 0)
    assert 0.0 < ps.view("M1@1h").threshold < 1.0 and _score(ps, "M1@1h", 0) < ps.view("M1@1h").threshold   # esik %98 (en yuksek ~%2)


def test_packageset_multi_arm_hot_reload_and_removal(tmp_path):
    ps = MP.PackageSet(tmp_path)
    PK.save_package(_pkg("M1@1h"), tmp_path)
    PK.save_package(_pkg("M1@4h"), tmp_path)
    (tmp_path / "bozuk.json").write_text("{nope")
    r = ps.reload(now=NOW)
    assert r["loaded"] == ["M1@1h", "M1@4h"] and "bozuk" in r["rejected"]
    assert ps.reload(now=NOW)["loaded"] == []                                                # degismeyen dosya atlanir
    first = ps.view("M1@1h").model_id
    PK.save_package(_pkg("M1@1h", n=40, created=NOW + timedelta(hours=1)), tmp_path)        # sicak yukleme
    assert ps.reload(now=NOW + timedelta(hours=2))["loaded"] == ["M1@1h"]
    assert ps.view("M1@1h").model_id != first
    (tmp_path / "M1@1h.json").unlink()
    assert "M1@1h" in ps.reload(now=NOW)["removed"] and ps.view("M1@1h") is None


def test_expired_view_reports_expired(tmp_path):
    PK.save_package(_pkg(), tmp_path)
    ps = MP.PackageSet(tmp_path)
    ps.reload(now=NOW)
    v = ps.view("M1@1h")
    assert not v.expired(NOW) and v.expired(NOW + timedelta(days=MP.MODEL_EXPIRY_DAYS + 1))
    assert ps.reload(now=NOW + timedelta(days=30))["loaded"] == []                          # suresi dolmus paket yuklenmez


def test_tampered_file_is_rejected_by_set(tmp_path):
    path = PK.save_package(_pkg(), tmp_path)
    pkg = json.loads(path.read_text())
    pkg["threshold"] = 0.999
    path.write_text(json.dumps(pkg))
    res = MP.PackageSet(tmp_path).reload(now=NOW)
    assert res["loaded"] == [] and res["rejected"]


def test_arm_id_must_match_file_name(tmp_path):
    path = PK.save_package(_pkg("M1@1h"), tmp_path)
    path.rename(tmp_path / "OTHER@1h.json")
    assert MP.PackageSet(tmp_path).reload(now=NOW)["loaded"] == []


def test_paper_only_refused_when_not_allowed(tmp_path):
    """Testnet/canliya kapidan gecmemis model yuklenmez (paper_only paketleri)."""
    PK.save_package(_pkg(), tmp_path)
    ps = MP.PackageSet(tmp_path, allow_paper_only=False)
    assert ps.reload(now=NOW)["loaded"] == [] and "M1@1h" in ps.rejected()


def test_packageset_runtime_dir_wins_then_seed_fallback(tmp_path):
    """Calisma zamani dizini once; depodaki tohum yalniz calisma zamaninda olmayan dosyayi tamamlar (tohum yazilmaz)."""
    runtime, seed = tmp_path / "runtime", tmp_path / "seed"
    PK.save_package(_pkg("M1@1h"), seed)
    PK.save_package(_pkg("M1@4h"), seed)
    PK.save_package(_pkg("M1@4h", n=40), runtime)
    seed_before = {p.name: p.read_bytes() for p in seed.glob("*.json")}
    ps = MP.PackageSet(runtime, fallback_dirs=(seed,))
    assert ps.reload(now=NOW)["loaded"] == ["M1@1h", "M1@4h"]
    assert json.loads((runtime / "M1@4h.json").read_text())["meta"]["n_train"] == 40
    assert not (runtime / "M1@1h.json").exists()                              # tohum okunur, kopyalanmaz
    assert {p.name: p.read_bytes() for p in seed.glob("*.json")} == seed_before  # tohum degismez


def test_ml_package_api_surface():
    for n in ("load_package", "PackageError", "MODEL_EXPIRY_DAYS", "view_from_package", "PackageSet"):
        assert hasattr(MP, n), n
    assert MP.MODEL_EXPIRY_DAYS == 21
    for n in ("load_model_view", "ml_score_from_reasons", "SetupDecision"):         # 24.11: ML filtre arayuzu silindi
        assert not hasattr(MP, n), n


# ------------------------------------------------------------------ gece birimi dosyalari (spec 5.2, 9)
def _unit(name):
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string((TRADER / "deploy" / name).read_text())
    return cp


def test_expected_files_exist():
    for rel in ("src/trader_ml/pa_proposer/train.py", "src/trader_ml/pa_proposer/package.py", "scripts/ml_retrain_run.py",
                "deploy/trader-ml-retrain.service", "deploy/trader-ml-retrain.timer"):
        assert (TRADER / rel).is_file(), rel
    assert not (TRADER / "src" / "trader_ml" / "setup_filter").exists()


def test_service_limits_and_oneshot():
    s = _unit("trader-ml-retrain.service")["Service"]
    assert s.get("Type") == "oneshot"
    assert s.get("MemoryHigh") == "250M" and s.get("MemoryMax") == "350M"   # WP-18: M1 olcumu (tepe ~263 MB) ile MemoryMax 300M -> 350M
    assert s.get("CPUQuota") == "50%" and s.get("Nice") == "10"
    assert "ml_retrain_run" in s.get("ExecStart", "")


def test_timer_runs_0340_utc_after_notes():
    txt = (TRADER / "deploy" / "trader-ml-retrain.timer").read_text()
    assert re.search(r"OnCalendar=\*-\*-\* 03:40:00 UTC", txt)
    assert "Persistent" in txt
    notes = (TRADER / "deploy" / "trader-notes.timer").read_text()
    m = re.search(r"OnCalendar=.*?(\d\d):(\d\d)", notes)
    if m:
        assert (int(m.group(1)), int(m.group(2))) < (3, 40), "retrain must run after the 02:55 notes job"


def test_trader_ml_uses_no_trader_engine():
    for f in (TRADER / "src" / "trader_ml").rglob("*.py"):
        assert not re.search(r"^\s*(import|from)\s+trader_engine", f.read_text(), re.M), f"{f.name} imports trader_engine"


# ------------------------------------------------------------------ gece betigi (yalniz M1)
def _snapshot(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).rglob("*")) if p.is_file()}


def test_script_end_to_end_empty_ledger_and_missing_ledger(tmp_path):
    import ml_retrain_run as R
    from trader_core import ledger as L
    lp = tmp_path / "ledger.sqlite"
    L.open_ledger(lp, "learner", create=True, migrate=True).close()
    md, csvp = tmp_path / "m1", tmp_path / "pm.csv"
    rc = R.main(["--once", "--ledger", str(lp), "--m1-models-dir", str(md), "--paper-models-csv", str(csvp),
                 "--history-dir", str(tmp_path / "hist")], now_fn=lambda: NOW, env={})
    assert rc == 0
    rows = csvp.read_text().splitlines()
    assert len(rows) == 1 + len(R.M1_TFS) and all(r.startswith("m1_nightly_") for r in rows[1:])   # veri yok: tf basina satir, paket yok
    assert not list(md.glob("*.json")) if md.exists() else True
    assert not (tmp_path / "setup_filter").exists()
    assert R.main(["--once", "--ledger", str(tmp_path / "yok.sqlite")], now_fn=lambda: NOW, env={}) == 3
    assert R.main(["--once", "--ledger", str(lp), "--no-m1"], now_fn=lambda: NOW, env={}) == 1      # kurulum suzgeci bayragi kalmadi
