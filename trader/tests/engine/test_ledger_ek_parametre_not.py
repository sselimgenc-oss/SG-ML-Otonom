"""Defter: istege bagli parametreler (session_off, post_stop_wait) ve kodla yazilan islem notu satiri (sema degismez).

Ders sistemi kaldirildi (25.11); defter parametre surumu mekanizmasi ve tablolari kalir. Bu testler eski WP-08/WP-09
testlerinin defter katmanina ait kalan kismidir.
"""
from datetime import datetime, timedelta, timezone

import pytest

from trader_core import ledger as L

UTC = timezone.utc
NOW = datetime(2026, 11, 20, 2, 55, tzinfo=UTC)
DAY = "2026-11-19"
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}


def test_istege_bagli_parametreler_defterde_ve_sinirlari():
    assert "session_off" in L.LESSON_PARAMS and "post_stop_wait" in L.LESSON_PARAMS
    assert L.LESSON_STEP["post_stop_wait"] == 1 and tuple(L.LESSON_BOUNDS_DEFAULT["post_stop_wait"]) == (0, 3)
    assert tuple(L.LESSON_BOUNDS_DEFAULT["session_off"]) == (0, 3)
    for p in ("vol_ratio_max", "stop_buffer_atr", "trail_atr", "range_target_frac", "rr_min"):
        assert p in L.LESSON_PARAMS


@pytest.fixture
def led(tmp_path):
    w = L.open_ledger(tmp_path / "ledger.sqlite", "learner", clock=lambda: NOW)
    w.init_params(PARAMS, reason="x")
    bar = datetime(2026, 11, 19, 7, tzinfo=UTC)
    did = w.record_decision(L.DecisionEvent(
        bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup="R1",
        regime="range", atr_ratio=1.1, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
        features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.1},
        planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1,
        veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
        size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
        final_action="entered", skip_reason=None))
    w.record_trade_entry(L.TradeEntry(1, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
    w.record_trade_exit(L.TradeExit(1, bar + timedelta(hours=1), 2079.0, "target", 2100.0, 0.3, 0.1))
    yield w
    w.close()


def test_defter_kodla_yazilan_not_satirini_kabul_eder(led):
    led.record_trade_note(1, DAY, ["giris_kalitesi:iyi"], "sablon notu R=+1.5", model="code", cost_usd=0)
    r = led.list_trade_notes(1)
    assert len(r) == 1 and r[0]["model"] == "code" and r[0]["cost_usd"] == 0 and r[0]["tags"] == ["giris_kalitesi:iyi"]


def test_defter_not_icin_var_olan_islem_ister(led):
    with pytest.raises(Exception):
        led.record_trade_note(999, DAY, ["x"], "metin", model="code", cost_usd=0)
