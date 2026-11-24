"""Fikir 10 (23.11): oynaklik tahmini ozellikleri (`vol_tahmin`, `vol_asim`; karar ozelligi olarak deftere yazilir).
Ileriye bakis yok, olcek degismez, NaN/kisa guvenli."""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from trader_engine.gates import _features
from trader_engine.vol_tahmin import MIN_GETIRI, vol_ozellikleri

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_engine_05_impl_smoke import _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 11, 2, tzinfo=timezone.utc)


def _seri(n=300, seed=7):
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


def test_ileriye_bakis_yok():
    c = _seri(400)
    t = 300
    a = vol_ozellikleri(c[: t + 1], 1.0, "1h")
    b = vol_ozellikleri(c[: t + 1], 1.0, "1h")
    assert a and a == b
    # t aninda hesap, gelecek mumlar eklenince (kesit ayni) degismez: gelecek veri girdi olamaz
    assert vol_ozellikleri(c[:301].copy(), 1.0, "1h") == a
    assert vol_ozellikleri(c[:301], 1.0, "1h") != vol_ozellikleri(c[:350], 1.0, "1h")


def test_olcek_degismez():
    c = _seri()
    a = vol_ozellikleri(c, 0.8, "1h")
    for k in (0.001, 1000.0, 65000.0):
        b = vol_ozellikleri(c * k, 0.8 * k, "1h")
        assert math.isclose(a["vol_tahmin"], b["vol_tahmin"], rel_tol=1e-9)
        assert math.isclose(a["vol_asim"], b["vol_asim"], rel_tol=1e-9)
    assert -1.0 <= a["vol_asim"] <= 1.0


def test_nan_kisa_guvenli():
    c = _seri()
    assert vol_ozellikleri(c[:MIN_GETIRI], 1.0) == {}
    assert vol_ozellikleri([], 1.0) == {} and vol_ozellikleri(None, 1.0) == {}
    bad = c.copy(); bad[-5] = float("nan")
    assert vol_ozellikleri(bad, 1.0) == {}
    neg = c.copy(); neg[-10] = -1.0
    assert vol_ozellikleri(neg, 1.0) == {}
    for atr in (None, float("nan"), 0.0, -1.0, "x"):
        assert vol_ozellikleri(c, atr) == {}
    assert vol_ozellikleri(np.full(100, 5.0), 1.0) == {}        # sabit fiyat: varyans 0
    assert vol_ozellikleri(c, 1.0, "bilinmeyen") != {}


def test_asimetri_isareti():
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.005, 200)
    r[-3:] = [-0.03, -0.02, -0.025]          # son sert dususler: asagi varyans payi baskin
    a = vol_ozellikleri(100 * np.exp(np.cumsum(r)), 1.0)
    assert a["vol_asim"] > 0.3
    r[-3:] = [0.03, 0.02, 0.025]
    assert vol_ozellikleri(100 * np.exp(np.cumsum(r)), 1.0)["vol_asim"] < -0.3


def test_karar_ozelliklerinde():
    f = _features(_row(vol_tahmin=1.3, vol_asim=-0.2))
    assert f["vol_tahmin"] == 1.3 and f["vol_asim"] == -0.2
    f0 = _features(_row())                                      # eksik => yazilmaz, cokmez
    assert "vol_tahmin" not in f0 and "vol_asim" not in f0
    assert "vol_tahmin" not in _features(_row(vol_tahmin=float("nan")))


def test_runner_satira_yazar_yalniz_adayda():
    import pandas as pd
    from trader_engine.strategy_runner import _to_row
    c = _seri(300)
    trig = pd.DataFrame({"close": c}, index=pd.date_range("2026-01-01", periods=300, freq="1h", tz="UTC"))
    r = _row()
    s = pd.Series({k: getattr(r, k) for k in r.__dataclass_fields__ if k not in ("pair", "bar_open_ts", "bar_close_ts")})
    s["atr_tf"] = 1.0
    row = _to_row("BTC/USDT", T0, T0, s, 1, trig, "1h")
    assert row.vol_tahmin is not None and row.vol_asim is not None
    assert _features(row)["vol_tahmin"] == row.vol_tahmin
    s2 = s.copy(); s2["setup"] = None
    assert _to_row("BTC/USDT", T0, T0, s2, 1, trig, "1h").vol_tahmin is None
    assert _to_row("BTC/USDT", T0, T0, s, 1, None, "1h").vol_tahmin is None


def test_deploy_sonrasi_ayni_karar_yeniden_yazilinca_cakisma_yok(tmp_path):
    from trader_core import ledger as L
    from trader_engine.clock import SimClock
    from trader_engine.gates import build_decision_event
    from test_engine_05_impl_smoke import _params
    from test_engine_05_impl_smoke import T0 as T0S
    clock = SimClock(T0S + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    try:
        led.init_params(_params(), reason="t")
        eski = build_decision_event(_row(), "1h", skip_reason="stop_width")                          # deploy oncesi: vol ozelligi yok
        i1 = led.record_decision(eski)
        yeni = build_decision_event(_row(vol_tahmin=1.2, vol_asim=0.1), "1h", skip_reason="stop_width")   # restart sonrasi ayni mum, yeni ozellikli
        assert "vol_tahmin" in yeni.features
        assert led.record_decision(yeni) == i1                              # LedgerConflictError YOK
    finally:
        led.close()
