import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest

from trader_core import budget as B
from trader_core.budget import (BudgetConfig, BudgetConfigError, BudgetGuard, Denial, Grant,
                                Usage, load_config)

T0 = datetime(2026, 11, 16, 10, 0, 0, tzinfo=timezone.utc)


class Clk:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def mk(tmp_path, clk=None, **kw):
    cfg = BudgetConfig(db_path=str(tmp_path / "b.sqlite"), **kw)
    return BudgetGuard(cfg, clock=clk or Clk())


def test_shipped_config_loads():
    cfg = load_config(str(Path(__file__).resolve().parents[1] / "config" / "budget.json"))
    # 23.11 kullanici karari: ust lig, LLM tavani 20 $
    assert cfg.daily_cap_usd == {"haftalik_ozet": 0.25, "lesson": 0.10, "haber_kolu": 0.10, "yorumcu": 0.15}
    assert cfg.monthly_cap_usd == 20.0


def test_cost_examples(tmp_path):
    g = mk(tmp_path)
    assert g.estimate_cost("claude-haiku-5-5", 4800, 1000, cache_read_tokens=1500) == pytest.approx(0.000995)
    assert g.estimate_cost("claude-sonnet-5-5", 6000, 1500, batch=True) == pytest.approx(0.0135)
    assert g.estimate_cost("claude-haiku-5-5", 4800, 800, cache_write_5m_tokens=1500) == pytest.approx(0.001068)
    g2 = mk(tmp_path, price_safety_factor=1.1)
    assert g2.estimate_cost("claude-haiku-5-5", 4800, 800, cache_read_tokens=1500) == pytest.approx(0.000985)
    with pytest.raises(BudgetConfigError):
        g.estimate_cost("nope", 1, 1)
    with pytest.raises(BudgetConfigError):
        g.estimate_cost("claude-haiku-5-5", 100_001, 1)


def test_hard_limits():
    for kw in ({"monthly_cap_usd": 21.0}, {"warn_fraction": 0.8}, {"price_safety_factor": 0.9},
               {"batch_multiplier": 0.4}, {"daily_cap_usd": {"haftalik_ozet": 0.3, "lesson": 0.1}},
               {"db_path": ""}):
        with pytest.raises(BudgetConfigError):
            BudgetConfig(**kw)


def test_authorize_record_settle(tmp_path):
    g = mk(tmp_path)
    gr = g.authorize("haftalik_ozet", 0.000995)
    assert isinstance(gr, Grant) and gr.est_micro == 995 and gr.day == "2026-11-16"
    assert g.status().services["haftalik_ozet"].unsettled_usd == pytest.approx(0.000995)
    s = g.record("haftalik_ozet", gr, Usage(4800, 800, cache_read_tokens=1500), "claude-haiku-5-5")
    assert s.ok and s.cost_micro == 895 and s.overrun_micro == 0
    assert g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.000895)
    d = g.record("haftalik_ozet", gr, Usage(1, 1), "claude-haiku-5-5")
    assert d.duplicate and d.code == "duplicate"
    bad = g.authorize("haftalik_ozet", 0.001)
    s = g.record("haftalik_ozet", bad, Usage(-1), "claude-haiku-5-5")
    assert s.estimated_instead and s.code == "bad_usage" and s.cost_micro == 1000
    s = g.record("haftalik_ozet", bad, Usage(1), "zzz")
    assert s.code == "unknown_model"


def test_daily_thresholds_isolation(tmp_path):
    g = mk(tmp_path)
    assert isinstance(g.authorize("haftalik_ozet", 0.174), Grant)
    assert isinstance(g.authorize("haftalik_ozet", 0.002), Grant)
    kinds = [e.kind for e in g.pending_events()]
    assert kinds.count("daily_warn_70") == 1
    assert isinstance(g.authorize("haftalik_ozet", 0.0001), Grant)
    assert [e.kind for e in g.pending_events()].count("daily_warn_70") == 1
    d = g.authorize("haftalik_ozet", 0.2)
    assert isinstance(d, Denial) and d.reason == "daily_cap" and d.retry_after == "2026-11-17T00:00:00.000Z"
    assert isinstance(g.authorize("lesson", 0.0135), Grant)
    ev = g.pending_events()
    assert any(e.kind == "daily_stopped_100" for e in ev)
    g.ack_events([e.id for e in ev] + [9999])
    assert g.pending_events() == []


def test_monthly_cap(tmp_path):
    clk = Clk()
    g = mk(tmp_path, clk)
    for day in range(16, 31):  # 15 * 0.35 = 5.25 > 5
        clk.t = T0.replace(day=day)
        assert isinstance(g.authorize("haftalik_ozet", 0.25), Grant)
        assert isinstance(g.authorize("lesson", 0.1), Grant)
    assert [e.kind for e in g.pending_events()].count("monthly_warn_5usd") == 1
    assert g.status().month_state == "warn"
    clk.t = datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert g.status().month_used_usd == 0


def test_monthly_denial(tmp_path):
    g = mk(tmp_path, monthly_cap_usd=0.3, monthly_warn_usd=0.1)
    assert isinstance(g.authorize("haftalik_ozet", 0.25), Grant)
    d = g.authorize("lesson", 0.06)
    assert d.reason == "monthly_cap" and d.retry_after == "2026-12-01T00:00:00.000Z"
    assert any(e.kind == "monthly_stopped" for e in g.pending_events())


def test_crash_expiry_and_late_record(tmp_path):
    clk = Clk()
    g = mk(tmp_path, clk)
    gr = g.authorize("haftalik_ozet", 0.003)
    clk.t = T0 + timedelta(minutes=11)
    g.authorize("haftalik_ozet", 0.001)
    st = g.status()
    assert st.services["haftalik_ozet"].unsettled_usd == pytest.approx(0.004)
    clk.t = T0 + timedelta(minutes=20)
    s = g.record("haftalik_ozet", gr, Usage(4800, 800, cache_read_tokens=1500), "claude-haiku-5-5")
    assert s.ok and s.cost_micro == 895
    # release only for open
    g2 = g.authorize("haftalik_ozet", 0.001)
    g.release(g2)
    g.release(gr)
    assert g.status().services["haftalik_ozet"].settled_usd == pytest.approx(0.000895)


def test_clock_monotonic_and_day_boundary(tmp_path):
    clk = Clk(datetime(2026, 11, 16, 23, 59, 59, 900000, tzinfo=timezone.utc))
    g = mk(tmp_path, clk)
    gr = g.authorize("haftalik_ozet", 0.01)
    clk.t = datetime(2026, 11, 17, 0, 0, 3, tzinfo=timezone.utc)
    s = g.record("haftalik_ozet", gr, Usage(100, 100), "claude-haiku-5-5")
    assert s.day == "2026-11-16"
    clk.t = datetime(2026, 11, 16, 23, 50, tzinfo=timezone.utc)
    assert g.status().day == "2026-11-17"
    assert g.authorize("haftalik_ozet", 0.01).day == "2026-11-17"


def test_report_error(tmp_path):
    g = mk(tmp_path)
    gr = g.authorize("haftalik_ozet", 0.01)
    a = g.report_error("haftalik_ozet", gr, 1, 429, "rate_limit_error")
    assert a.kind == "retry" and 1.6 <= a.sleep_s <= 2.4
    assert g.report_error("haftalik_ozet", gr, 3, 500).sleep_s == pytest.approx(8, rel=0.21)
    assert g.report_error("haftalik_ozet", gr, 4, 500).kind == "fail"
    assert g.report_error("haftalik_ozet", gr, 1, 529, retry_after_s=40).sleep_s == 20
    assert g.report_error("haftalik_ozet", gr, 1, 400, "invalid_request_error", message="bad schema").kind == "fail"
    gr = g.authorize("haftalik_ozet", 0.01)
    a = g.report_error("haftalik_ozet", gr, 1, 400, "invalid_request_error",
                       message="You have reached your specified API usage limits")
    assert a.kind == "stop" and a.blocked_until == "2026-11-17T00:00:00.000Z"
    for s in ("haftalik_ozet", "lesson"):
        d = g.authorize(s, 0.001)
        assert d.reason == "provider_blocked"
    assert g.status().services["haftalik_ozet"].state == "blocked"


def test_429_spend_limit_month_start(tmp_path):
    clk = Clk(datetime(2026, 12, 15, 5, tzinfo=timezone.utc))
    g = mk(tmp_path, clk)
    gr = g.authorize("lesson", 0.01)
    a = g.report_error("lesson", gr, 1, 429, error_code="enforced_spend_limit_reached")
    assert a.kind == "stop" and a.blocked_until == "2027-01-01T00:00:00.000Z"


def test_store_failures(tmp_path):
    p = tmp_path / "b.sqlite"
    g = mk(tmp_path)
    assert isinstance(g.authorize("haftalik_ozet", 0.001), Grant)
    p.unlink()
    d = g.authorize("haftalik_ozet", 0.001)
    assert d.reason == "store_missing"
    assert not g.status().store_ok
    p.write_bytes(b"garbage" * 100)
    assert g.authorize("haftalik_ozet", 0.001).reason == "store_unavailable"
    assert g.pending_events() == []
    with pytest.raises(ValueError):
        g.authorize("x", 0.1)
    assert g.authorize("haftalik_ozet", float("nan")).reason == "invalid_request"
    bad = BudgetGuard(str(tmp_path / "nope.json"))
    assert bad.authorize("haftalik_ozet", 0.1).reason == "config_invalid"
    assert bad.status().config_ok is False


def test_newer_schema(tmp_path):
    g = mk(tmp_path)
    g.authorize("haftalik_ozet", 0.001)
    c = sqlite3.connect(tmp_path / "b.sqlite")
    c.execute("PRAGMA user_version=9")
    c.close()
    assert g.authorize("haftalik_ozet", 0.001).reason == "store_unavailable"


def test_no_key_leak(tmp_path):
    g = mk(tmp_path)
    gr = g.authorize("haftalik_ozet", 0.01)
    g.report_error("haftalik_ozet", gr, 1, 401, message="bad key sk-ant-api03-SECRETSECRET")
    g.record("haftalik_ozet", gr, Usage(1), "sk-ant-api03-SECRETSECRET")
    assert b"SECRETSECRET" not in (tmp_path / "b.sqlite").read_bytes()


def test_module_level_wrappers(tmp_path, monkeypatch):
    B._set_default_guard(mk(tmp_path))
    try:
        assert B.api_key_env("haftalik_ozet") == "ANTHROPIC_API_KEY_HAFTALIK_OZET"
        g = B.authorize("haftalik_ozet", 0.01)
        assert isinstance(g, Grant)
        assert B.record("haftalik_ozet", g, Usage(10, 10), "claude-haiku-5-5").ok
        assert B.status().to_dict()["store_ok"] is True
        json.dumps(B.status().to_dict())
    finally:
        B._set_default_guard(None)


def test_reinitialize(tmp_path):
    g = mk(tmp_path)
    g.authorize("haftalik_ozet", 0.001)
    (tmp_path / "b.sqlite").unlink()
    g.reinitialize({"haftalik_ozet": 0.2, "lesson": 0.0})
    assert g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.2)
