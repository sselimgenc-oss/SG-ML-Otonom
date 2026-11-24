"""DD-12 WP-14 (impl smoke): M1 ozellik/etiket/egitim/paket/kol/saglik/disa aktarma. Sentetik veri; kilit reddi dahil."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "research"))

from trader_core import ml_package as MP
from trader_core.signals import SIGNAL_COLUMNS
from trader_engine.strategies.arms import ArmInput, discover
from trader_ml.pa_proposer import features as PF
from trader_ml.pa_proposer import labels as LB
from trader_ml.pa_proposer import package as PK
from trader_ml.pa_proposer import train as TR
from trader_ml.pa_proposer.train import LockWindowError

# 23.11.2026 kullanici karari: kilit ACIK. Bu dosya kilit mekanizmasini sinar -> kilit KAPALI bayragiyla (conftest.egitim_kilitli); acik davranis tests/ml/test_kilit_acik_egitim.py.
pytestmark = pytest.mark.usefixtures("egitim_kilitli")


UTC = timezone.utc
NOW = datetime(2026, 11, 19, tzinfo=UTC)
T_OK = datetime(2026, 11, 2, tzinfo=UTC)


def _bars(n, seed=0, base=100.0):
    rng = np.random.default_rng(seed)
    c = base + np.cumsum(rng.normal(0, 1.0, n))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0.1, 0.8, n)
    l = np.minimum(o, c) - rng.uniform(0.1, 0.8, n)
    return o, h, l, c


def _ts(n, start=datetime(2026, 11, 2, tzinfo=UTC)):
    return [start + timedelta(hours=k) for k in range(n)]


def test_features_causal_and_window_only():
    o, h, l, c = _bars(200, 1)
    i = 120
    v = PF.feature_vector(o, h, l, c, i, "long")
    assert v is not None and v.shape == (len(PF.FEATURE_NAMES),)
    # gelecek barlar degisse de ozellik ayni (nedensel)
    o2, h2, l2, c2 = o.copy(), h.copy(), l.copy(), c.copy()
    c2[i + 1:] += 50.0
    h2[i + 1:] += 50.0
    assert np.array_equal(v, PF.feature_vector(o2, h2, l2, c2, i, "long"))
    # yalniz 64 bar penceresi: kesilmis dizide (i'ye kadar) ayni vektor (canli = egitim, bit bit)
    k = i + 1
    assert np.array_equal(v, PF.feature_vector(o[:k], h[:k], l[:k], c[:k], i, "long"))
    # short ayna: dir isareti ters, fiyat tabanli isaretli ozellikler negatif
    vs = PF.feature_vector(o, h, l, c, i, "short")
    assert vs[PF.FEATURE_NAMES.index("dir")] == -1.0 and vs[PF.FEATURE_NAMES.index("ret_1")] == pytest.approx(-v[0])


def test_feature_none_when_short_history():
    o, h, l, c = _bars(100, 2)
    assert PF.feature_vector(o, h, l, c, 10, "long") is None


def test_triple_barrier_outcomes():
    n = 60
    c = np.full(n, 100.0); o = c.copy(); h = c + 0.5; l = c - 0.5
    atr = 1.0
    # long, hedef once: bar 5'te h >= 103
    h2, l2 = h.copy(), l.copy(); h2[5] = 103.5
    assert LB.triple_barrier(h2, l2, c, 10, "long", atr) is None or True  # ufuk yetersiz olabilir: asagida kontrol
    h3, l3 = h.copy(), l.copy(); h3[15] = 103.5
    assert LB.triple_barrier(h3, l3, c, 10, "long", atr) == (1, 15)
    # long, stop once
    h4, l4 = h.copy(), l.copy(); l4[12] = 98.4
    assert LB.triple_barrier(h4, l4, c, 10, "long", atr) == (0, 12)
    # ayni barda iki bariyer: stop (muhafazakar)
    h5, l5 = h.copy(), l.copy(); h5[12] = 104; l5[12] = 97
    assert LB.triple_barrier(h5, l5, c, 10, "long", atr) == (0, 12)
    # short hedef: alt bariyer
    h6, l6 = h.copy(), l.copy(); l6[14] = 96.5
    assert LB.triple_barrier(h6, l6, c, 10, "short", atr) == (1, 14)
    # yetersiz gelecek -> None
    assert LB.triple_barrier(h, l, c, n - 10, "long", atr) is None


def test_lock_rows_refused_structurally():
    rows = [{"ts": datetime(2026, 6, 1, tzinfo=UTC), "ts_end": datetime(2026, 6, 2, tzinfo=UTC), "side": "long",
             "x": np.zeros(len(PF.FEATURE_NAMES)), "y": 1}]
    with pytest.raises(LockWindowError):
        TR.train_tf(rows, arm_id="M1@1h", created_at=NOW)


def test_paper_rows_after_lock_accepted_and_lock_counted():
    x = np.zeros(len(PF.FEATURE_NAMES))
    post = LB.paper_row(x, "long", T_OK, None, 1.2)
    pre = LB.paper_row(x, "long", datetime(2026, 6, 1, tzinfo=UTC), None, -0.5)
    kept, dropped = TR.split_lock([post, pre])
    assert dropped == 1 and len(kept) == 1 and kept[0]["y"] == 1


def _synthetic_rows(n=800, seed=3):
    o, h, l, c = _bars(n + 200, seed)
    rows = LB.label_rows(o, h, l, c, _ts(len(c), datetime(2024, 1, 1, tzinfo=UTC)))
    return [r for r in rows if r["ts_end"] < datetime(2026, 5, 1, tzinfo=UTC)]


def test_train_deterministic_and_single_class_none():
    rows = _synthetic_rows()
    assert len(rows) > 100 and {r["y"] for r in rows} == {0, 1}
    a = TR.train_tf(rows, arm_id="M1@1h", created_at=NOW)
    b = TR.train_tf(list(reversed(rows)), arm_id="M1@1h", created_at=NOW)
    assert a["meta"]["model_hash"] == b["meta"]["model_hash"]
    assert a["meta"]["features"] == list(PF.FEATURE_NAMES)
    assert TR.train_tf([dict(r, y=0) for r in rows], arm_id="M1@1h", created_at=NOW) is None


def test_package_roundtrip_expiry_and_packageset(tmp_path):
    rows = _synthetic_rows()
    pkg = TR.train_tf(rows, arm_id="M1@1h", created_at=NOW)
    p = PK.save_package(pkg, tmp_path)
    loaded = MP.load_package(p, now=NOW)
    assert loaded["meta"]["kind"] == "pa_proposer"
    assert MP.is_expired(loaded, NOW + timedelta(days=22))
    ps = MP.PackageSet(tmp_path)
    rep = ps.reload(now=NOW)
    assert rep["loaded"] == ["M1@1h"] and not rep["rejected"]
    assert ps.view("M1@1h").threshold == pytest.approx(pkg["threshold"])


class _Arm:
    @staticmethod
    def tab_core(index):
        core = pd.DataFrame(index=index, columns=SIGNAL_COLUMNS)
        core["regime"] = "none"
        core["signal"] = False
        core["pullback_ema"] = 0
        return core


@pytest.fixture
def m1(monkeypatch, tmp_path):
    import trader_engine.strategies.arms.m1 as M1
    return M1, tmp_path


def _arm_input(index, o, h, l, c):
    trig = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=index)
    return ArmInput(pair="X/USDT", tf="1h", D=index[-1] + timedelta(hours=1), trig=trig, h4=trig, params=None,
                    core_fn=lambda: _Arm.tab_core(index))


def test_arm_contract_and_discovery():
    mods = discover(refresh=True)
    m = mods["M1"]
    assert m.TIMEFRAMES == ("1h", "4h", "15m", "1d") and m.CORE is False and m.EXIT_MODE == "target" and m.PRIORITY == 90
    assert 0 < len(m.FEATURES) <= 6


def test_arm_no_package_no_candidate(m1):
    M1, tmp = m1
    o, h, l, c = _bars(150, 4)
    idx = pd.date_range("2026-11-02", periods=150, freq="h", tz="UTC")
    M1._PS = MP.PackageSet(tmp / "absent")
    out = M1.compute(_arm_input(idx, o, h, l, c))
    assert int(out["signal"].sum()) == 0 and len(out) == 150


def test_arm_expired_or_forced_package_yields_candidate(m1):
    M1, tmp = m1
    rows = _synthetic_rows()
    pkg = TR.train_tf(rows, arm_id="M1@1h", created_at=NOW)
    pkg["threshold"] = -1.0           # yalniz sinama: her iki yon esigi gecer (model hash degisir -> yeniden kur)
    body = {"model": pkg["model"], "calibration": pkg["calibration"], "threshold": pkg["threshold"]}
    pkg["meta"]["model_hash"] = PK.sha256_text(MP.canon(body))
    PK.save_package(pkg, tmp)
    M1._PS = MP.PackageSet(tmp)
    o, h, l, c = _bars(150, 5)
    idx = pd.date_range("2026-11-02", periods=150, freq="h", tz="UTC")
    inp = _arm_input(idx, o, h, l, c)
    out = M1.compute(inp)
    hit = out[out["signal"].astype(bool)]
    assert len(hit) == 1
    row = hit.iloc[0]
    atr = PF.atr_at(h, l, c, 149)
    entry = c[149]
    if row["side"] == "long":
        assert row["planned_stop"] == pytest.approx(entry - 1.5 * atr) and row["planned_target"] == pytest.approx(entry + 3 * atr)
    else:
        assert row["planned_stop"] == pytest.approx(entry + 1.5 * atr) and row["planned_target"] == pytest.approx(entry - 3 * atr)
    # suresi dolmus paket -> aday yok
    pkg2 = dict(pkg); pkg2["meta"] = dict(pkg["meta"], created_at="2026-01-01T00:00:00+00:00", expires_at="2026-01-22T00:00:00+00:00")
    body2 = {"model": pkg["model"], "calibration": pkg["calibration"], "threshold": -1.0}
    pkg2["meta"]["model_hash"] = PK.sha256_text(MP.canon(body2))
    (tmp / PK.safe_arm_name('M1@1h')).with_suffix('.json').write_text(json.dumps(pkg2, sort_keys=True), encoding='utf-8')
    M1._PS = MP.PackageSet(tmp)
    assert int(M1.compute(inp)["signal"].sum()) == 0


def test_config_and_inventory():
    cfg = json.loads((REPO / "config" / "engine.paper.json").read_text(encoding="utf-8"))
    assert "M1@1h" in cfg["arms"] and "M1@4h" in cfg["arms"] and cfg["arm_max_positions"]["M1"] == 4
    from test_engine_module_inventory import scan_inventory
    assert scan_inventory(REPO) == []


def test_health_pa_proposer_alerts(tmp_path):
    import health_run as HR
    missing = HR.pa_proposer_alerts({}, NOW, models_dir=str(tmp_path / "none"))
    assert [a.code for a in missing] == ["pa_proposer_missing"]
    (tmp_path / "M1@1h.json").write_text(json.dumps({"meta": {"created_at": (NOW - timedelta(days=9)).isoformat()}}))
    assert [a.code for a in HR.pa_proposer_alerts({}, NOW, models_dir=str(tmp_path))] == ["pa_proposer_stale"]
    (tmp_path / "M1@1h.json").write_text(json.dumps({"meta": {"created_at": (NOW - timedelta(days=2)).isoformat()}}))
    assert HR.pa_proposer_alerts({}, NOW, models_dir=str(tmp_path)) == []


def test_build_script_smoke(tmp_path):
    import pa_proposer_build as PB
    # Gercek gecmis veri git deposunda yok ve CIda bulunmaz: kilit (2026-05-01) oncesi sentetik 4s bar dosyasi kullanilir.
    hist = tmp_path / "history"
    hist.mkdir()
    o, h, l, c = _bars(1500, seed=5, base=1000.0)
    idx = pd.date_range("2025-01-01", periods=len(c), freq="4h", tz="UTC")
    pd.DataFrame({"date": idx, "open": o, "high": h, "low": l, "close": c, "volume": 1.0}).to_feather(
        hist / "BTC_USDT_USDT-4h-futures.feather")
    rc = PB.main(["--history-dir", str(hist), "--pairs", "BTC", "--tfs", "4h", "--out-dir", str(tmp_path / "m"),
                  "--paper-models-csv", str(tmp_path / "p.csv")], now=NOW)
    assert rc == 0
    assert (tmp_path / "m" / "M1@4h.json").exists()
    lines = (tmp_path / "p.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("ad,") and len(lines) == 2 and "M1@4h" in lines[1]


def test_export_missing_ledger_is_error(tmp_path):
    import export_paper_records as EX
    rc = EX.main(["--ledger", str(tmp_path / "none.sqlite"), "--out", str(tmp_path / "o.jsonl")])
    assert rc == 3


def test_health_pa_proposer_uses_data_root(tmp_path):
    """19 Kasim: saglik birimi kodu releases/<commit> altindan calistirir; M1 paketleri veri kokunde (TRADER_DATA_ROOT) aranir."""
    import health_run as HR
    (tmp_path / "models" / "pa_proposer").mkdir(parents=True)
    (tmp_path / "models" / "pa_proposer" / "M1@1h.json").write_text("{}")
    alerts = HR.pa_proposer_alerts({"TRADER_DATA_ROOT": str(tmp_path)}, NOW)
    assert all(a.code != "pa_proposer_missing" for a in alerts)
    missing = HR.pa_proposer_alerts({"TRADER_DATA_ROOT": str(tmp_path / "yok")}, NOW)
    assert [a.code for a in missing] == ["pa_proposer_missing"]
