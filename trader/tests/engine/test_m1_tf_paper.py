"""M1@15m ve M1@1d kagitta acik (20 Kasim): config, kayit, paketsiz davranis, gece egitimi (tf basina), kilit disi."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import ml_package as MP
from trader_ml.pa_proposer import train as TR
from trader_ml.pa_proposer.train import LOCK_END, LOCK_START

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _cfg(name):
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


def test_paper_config_has_m1_all_four_tfs_only_on_paper():
    arms = _cfg("engine.paper.json")["arms"]
    for tf in ("15m", "1h", "4h", "1d"):
        assert f"M1@{tf}" in arms
    assert len(arms) == len(set(arms)) == 85     # 24.11 kullanici karari: formasyon kutuphanesi (37 + MF1 48; GF1/IN1 sonraki adimlarda 203); 23.11: + HB1@1h (haber kolu); 24.11: + DL1@15m/1h/4h/1d
    assert _cfg("engine.live.json")["arms"] == arms      # 23.11 kullanici karari: canli = kagit (ayni kurulumlar)
    for other in ("engine.base.json", "engine.learner.json", "engine.testnet.json"):
        p = ROOT / "config" / other
        if p.exists():
            assert not any(str(a).startswith("M1@") for a in _cfg(other).get("arms", []))


def test_arm_registered_for_15m_and_1d():
    from trader_engine.strategies.arms import discover
    m1 = discover(refresh=True)["M1"]
    assert {"15m", "1d"} <= set(m1.TIMEFRAMES)
    import ml_retrain_run as R
    assert {"15m", "1d"} <= set(R.M1_TFS) and set(R.M1_TFS) <= set(R.PB_TFS)


@pytest.mark.parametrize("tf,freq,delta", [("15m", "15min", timedelta(minutes=15)), ("1d", "D", timedelta(days=1))])
def test_no_package_no_crash_no_candidate(tmp_path, tf, freq, delta):
    import trader_engine.strategies.arms.m1 as M1
    from trader_engine.strategies.arms import ArmInput
    n = 150
    idx = pd.date_range("2026-11-02", periods=n, freq=freq, tz="UTC")
    c = 100 + np.cumsum(np.random.default_rng(1).normal(0, 0.5, n))
    trig = pd.DataFrame({"open": c, "high": c + 0.3, "low": c - 0.3, "close": c}, index=idx)
    inp = ArmInput(pair="X/USDT", tf=tf, D=idx[-1] + delta, trig=trig, h4=trig, params=None,
                   core_fn=lambda: (_ for _ in ()).throw(AssertionError("core okunmamali")))
    old = M1._PS
    try:
        M1._PS = MP.PackageSet(tmp_path / "yok")
        out = M1.compute(inp)
    finally:
        M1._PS = old
    assert len(out) == n and int(out["signal"].sum()) == 0


def test_min_rows_reason_text():
    assert TR.no_model_reason(0, None) == "model yok: 0 örnek, en az 2"
    assert TR.no_model_reason(1, 1) == "model yok: 1 örnek, en az 2"
    assert "tek sınıf" in TR.no_model_reason(500, 1)
    assert TR.train_tf([], arm_id="M1@1d") is None


def _write(hist: Path, base: str, tf: str, start: datetime, n: int, step: timedelta, seed: int) -> None:
    import pyarrow as pa
    import pyarrow.feather as pf
    rng = np.random.default_rng(seed)
    idx = [start + step * k for k in range(n)]
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    op = np.concatenate([[close[0]], close[:-1]])
    hi = np.maximum(op, close) + np.abs(rng.normal(0, 0.2, n))
    lo = np.minimum(op, close) - np.abs(rng.normal(0, 0.2, n))
    pf.write_feather(pa.table({"date": pa.array(idx, type=pa.timestamp("ms", tz="UTC")), "open": op, "high": hi,
                               "low": lo, "close": close, "volume": np.ones(n)}),
                     str(hist / f"{base}_USDT_USDT-{tf}-futures.feather"), compression="uncompressed")


class _Led:
    LIST_CLOSED_MAX = 10

    def list_closed_trades(self, limit=10):
        return []

    def list_decisions(self):
        return []


def test_nightly_produces_per_tf_packages_and_excludes_lock(tmp_path, monkeypatch):
    import ml_retrain_run as R
    monkeypatch.setattr(R, "KILIT_ACIK", False)                  # 24.11 kullanici karari: denetim duzeltmeleri (kesim yalniz kilit kapaliyken)
    h = tmp_path / "h"
    h.mkdir()
    for k, b in enumerate(("BTC", "ETH")):                       # kilit icine uzanan veri
        _write(h, b, "15m", datetime(2026, 1, 1, tzinfo=UTC), 96 * 400, timedelta(minutes=15), 3 + k)
        _write(h, b, "1d", datetime(2024, 1, 1, tzinfo=UTC), 900, timedelta(days=1), 5 + k)
    csv_rows: list = []
    out = R.m1_nightly(_Led(), None, history_dir=str(h), tfs=["15m", "1d"], models_dir=str(tmp_path / "m"),
                       now=datetime(2026, 11, 20, 3, 10, tzinfo=UTC), max_rows=600, csv_rows=csv_rows)
    for tf in ("15m", "1d"):
        assert out[tf]["status"] == "ok" and out[tf]["reason"] is None and out[tf]["hist_rows"] > 0
        pkg = json.loads((tmp_path / "m" / f"M1@{tf}.json").read_text(encoding="utf-8"))
        assert pkg["meta"]["arm_id"] == f"M1@{tf}"
        assert datetime.fromisoformat(pkg["meta"]["train_window"]["end"]) < LOCK_START   # kilit donemi egitime girmedi
    assert len(csv_rows) == 2 and {r[0].split("_")[2] for r in csv_rows} == {"15m", "1d"}


def test_nightly_no_data_reports_visible_reason(tmp_path):
    import ml_retrain_run as R
    h = tmp_path / "h"
    h.mkdir()
    _write(h, "BTC", "1d", datetime(2026, 6, 1, tzinfo=UTC), 100, timedelta(days=1), 1)   # tamami kilit icinde
    csv_rows: list = []
    out = R.m1_nightly(_Led(), None, history_dir=str(h), tfs=["1d"], models_dir=str(tmp_path / "m"),
                       now=datetime(2026, 11, 20, tzinfo=UTC), csv_rows=csv_rows)
    assert out["1d"]["status"] == "no_model" and out["1d"]["reason"] == "model yok: 0 örnek, en az 2"
    assert not (tmp_path / "m" / "M1@1d.json").exists()
    assert "model yok: 0 örnek, en az 2" in csv_rows[0][3]


def test_kol_adi():
    from trader_core import tg_sade
    assert tg_sade.kol_adi("M1@15m") == "Yapay zekâ adayı · 15 dakika"
    assert tg_sade.kol_adi("M1@1d") == "Yapay zekâ adayı · 1 gün"
