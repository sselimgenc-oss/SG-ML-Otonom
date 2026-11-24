"""24.11 denetim: M1 kagit satiri sinyal mumuna (kapanis - tf) eslesir; KILIT_ACIK iken tarihsel/kagit kesimi uygulanmaz."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "scripts", ROOT / "research", ROOT / "paket", ROOT / "src"):
    sys.path.insert(0, str(_p))
import ml_retrain_run as R  # noqa: E402
import pa_proposer_build as PB  # noqa: E402

UTC = timezone.utc


def _bars(n=200, start=datetime(2026, 8, 1, tzinfo=UTC), delta=timedelta(hours=1)):
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    ts = [start + k * delta for k in range(n)]
    return ts, c - 0.1, c + 0.3, c - 0.3, c


def test_kagit_satiri_sinyal_mumuna_eslesir(monkeypatch):
    monkeypatch.setattr(PB, "KILIT_ACIK", True)
    d = timedelta(hours=1)
    bars = _bars(delta=d)
    ts = bars[0]
    k = 150
    kapanis = ts[k] + d                      # karar ani = k. mumun kapanisi
    rec = {"arm_id": "M1@1h", "pair": "X/USDT", "side": "long", "bar_close_ts": kapanis.isoformat(),
           "outcome_ts": (kapanis + d).isoformat(), "r": 1.0}
    seen = []
    orig = PB.PF.feature_vector
    monkeypatch.setattr(PB.PF, "feature_vector", lambda o, h, l, c, i, s: (seen.append(i), orig(o, h, l, c, i, s))[1])
    rows, st = PB._paper_rows([rec], {"X/USDT": bars}, "1h", d)
    assert seen == [k] and st["used"] == 1 and rows[0]["ts"] == ts[k]
    # tam eslesme (kapanis zamaninda ACILAN mum) artik kullanilmaz: bar yoksa no_bar
    son = {**rec, "bar_close_ts": ts[-1].isoformat()}                 # ts[-1] - tf mevcut ama t0 == acilis; yalniz t0-tf aranir
    seen.clear()
    PB._paper_rows([son], {"X/USDT": bars}, "1h", d)
    assert seen == [len(ts) - 2]


def test_kilit_acikken_tarihsel_kesim_yok(monkeypatch):
    bars = _bars(n=700)                                               # tamami kilit donemi (2026-08)
    monkeypatch.setattr(PB, "KILIT_ACIK", True)
    assert len(PB._hist_rows(bars, "X/USDT", PB.LOCK_START)) > 0
    monkeypatch.setattr(R, "KILIT_ACIK", True)
    assert len(R._hist_tail(bars, "X/USDT", 400, R.LOCK_START)) > 0
    monkeypatch.setattr(PB, "KILIT_ACIK", False)
    assert PB._hist_rows(bars, "X/USDT", PB.LOCK_START) == []
    monkeypatch.setattr(R, "KILIT_ACIK", False)
    assert R._hist_tail(bars, "X/USDT", 400, R.LOCK_START) == []


def test_kagit_pencere_kilit_kesimi_yalniz_kapaliyken(monkeypatch):
    d = timedelta(hours=1)
    start = datetime(2026, 10, 31, tzinfo=UTC)                        # pencere LOCK_END oncesine deger
    bars = _bars(n=120, start=start, delta=d)
    k = PB.PF.WINDOW + 5
    rec = {"arm_id": "M1@1h", "pair": "X/USDT", "side": "long", "bar_close_ts": (bars[0][k] + d).isoformat(),
           "outcome_ts": (bars[0][k] + 2 * d).isoformat(), "r": 1.0}
    monkeypatch.setattr(PB, "KILIT_ACIK", False)
    assert PB._paper_rows([rec], {"X/USDT": bars}, "1h", d)[1]["no_window"] == 1
    monkeypatch.setattr(PB, "KILIT_ACIK", True)
    assert PB._paper_rows([rec], {"X/USDT": bars}, "1h", d)[1]["used"] == 1


def test_veri_penceresi_alani(monkeypatch):
    monkeypatch.setattr(PB, "KILIT_ACIK", True)
    assert "kilit=acik" in PB._veri_penceresi()
    monkeypatch.setattr(PB, "KILIT_ACIK", False)
    assert PB._veri_penceresi().startswith("hist<2026-05-01")
