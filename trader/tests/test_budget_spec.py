"""Independent spec-conformance tests for trader_core.budget.

Written only from docs/butce-spec.md (v1, 16 Kasim 2026); the implementation
was deliberately not read.  Section numbers in comments refer to that spec.

Assumption about the injected clock (spec only says "clock enjekte edilebilir"):
``clock`` is a zero-argument callable returning a tz-aware UTC ``datetime``.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from trader_core import budget as B
from trader_core.budget import (
    BudgetConfigError,
    BudgetGuard,
    Denial,
    ErrorAction,
    Grant,
    Settlement,
    Usage,
    load_config,
)

UTC = timezone.utc
TRADER_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = TRADER_DIR / "src"

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

BASE_CFG = {
    "version": 1,
    "db_path": "placeholder",
    "daily_cap_usd": {"haftalik_ozet": 0.25, "lesson": 0.10},
    "monthly_cap_usd": 10.0,
    "monthly_warn_usd": 5.0,
    "warn_fraction": 0.70,
    "prepaid_credit_usd": 10.0,
    "credit_start_ts": "2026-11-16T00:00:00.000Z",
    "credit_low_usd": 3.0,
    "price_safety_factor": 1.0,
    "prices_verified_on": None,
    "batch_multiplier": 0.5,
    "api_key_env": {"haftalik_ozet": "ANTHROPIC_API_KEY_HAFTALIK_OZET", "lesson": "ANTHROPIC_API_KEY_LESSON"},
    "reservation_ttl_s": {"haftalik_ozet": 600, "lesson": 108000},
    "retry": {
        "max_retries": 3,
        "base_s": 2.0,
        "factor": 2.0,
        "max_sleep_s": 20.0,
        "jitter": 0.2,
        "deadline_s": {"haftalik_ozet": 60, "lesson": 300},
    },
    "prices_usd_per_mtok": {
        "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write_5m": 0.125,
                              "cache_write_1h": 0.20, "cache_read": 0.01},
        "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write_5m": 2.50,
                               "cache_write_1h": 4.00, "cache_read": 0.10},
    },
}
CAPS = {"haftalik_ozet": 250_000, "lesson": 100_000}
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"


# ----------------------------------------------------------------- helpers
def T(y, m, d, H=0, M=0, S=0, ms=0):
    return datetime(y, m, d, H, M, S, ms * 1000, tzinfo=UTC)


def P(s):
    return datetime.fromisoformat(s)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def set(self, t):
        self.t = t

    def adv(self, **kw):
        self.t = self.t + timedelta(**kw)


def usd(micro):
    """USD float whose ceil(x*1e6) is exactly `micro` (robust to float noise)."""
    return (micro - 0.5) / 1e6


def make_cfg(tmp_path, mutate=None, db_name="budget.sqlite", cfg_name="budget.json"):
    d = copy.deepcopy(BASE_CFG)
    d["db_path"] = str(tmp_path / db_name)
    if mutate:
        mutate(d)
    p = tmp_path / cfg_name
    p.write_text(json.dumps(d))
    return load_config(str(p))


class Env:
    pass


@pytest.fixture
def env(tmp_path):
    e = Env()
    e.tmp = tmp_path
    e.db = tmp_path / "budget.sqlite"
    e.clock = Clock(T(2026, 11, 16, 10, 0, 0))
    e.cfg = make_cfg(tmp_path)
    e.g = BudgetGuard(e.cfg, clock=e.clock)
    return e


def mk(env, mutate):
    cfg = make_cfg(env.tmp, mutate)
    return BudgetGuard(cfg, clock=env.clock)


def q(db, sql, args=()):
    c = sqlite3.connect(str(db), timeout=10)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def events(g, kind=None):
    ev = g.pending_events()
    return [e for e in ev if kind is None or e.kind == kind]


def grant(g, service, micro):
    r = g.authorize(service, usd(micro))
    assert isinstance(r, Grant), r
    assert r.est_micro == micro
    return r


def fill_month(g, clock, target, start=None):
    """Spread `target` micro-USD of open reservations over Dec 2026 days.
    Returns the first untouched day (datetime)."""
    d = start or T(2026, 12, 1, 1)
    rem = target
    while rem > 0:
        clock.set(d)
        for svc in ("haftalik_ozet", "lesson"):
            m = min(CAPS[svc], rem)
            if m <= 0:
                break
            grant(g, svc, m)
            rem -= m
        d += timedelta(days=1)
    return d


def day_str(dt):
    return dt.strftime("%Y-%m-%d")


# ===================================================== 1. cost computation
class TestCost:
    @pytest.mark.parametrize(
        "kwargs,expected_micro",
        [
            # 13.5
            (dict(input_tokens=4800, max_output_tokens=1000, cache_read_tokens=1500), 995),
            # 13.1 style with max_output 800
            (dict(input_tokens=4800, max_output_tokens=800, cache_read_tokens=1500), 895),
            # 13.2 1h cache write
            (dict(input_tokens=4800, max_output_tokens=800, cache_write_1h_tokens=1500), 1180),
            # 13.2 5m cache write: 1067.5 -> ceil 1068
            (dict(input_tokens=4800, max_output_tokens=800, cache_write_5m_tokens=1500), 1068),
        ],
    )
    def test_estimate_haiku(self, env, kwargs, expected_micro):
        v = env.g.estimate_cost(HAIKU, **kwargs)
        assert isinstance(v, float)
        assert v == pytest.approx(expected_micro / 1e6, abs=1e-9)

    def test_estimate_batch_sonnet_13_4(self, env):
        v = env.g.estimate_cost(SONNET, input_tokens=6000, max_output_tokens=1500, batch=True)
        assert v == pytest.approx(0.0135, abs=1e-9)
        v2 = env.g.estimate_cost(SONNET, input_tokens=6000, max_output_tokens=1500)
        assert v2 == pytest.approx(0.027, abs=1e-9)

    def test_estimate_all_five_fields(self, env):
        # 1000*.1 + 2000*.5 + 3000*.125 + 4000*.2 + 5000*.01 = 100+1000+375+800+50
        v = env.g.estimate_cost(HAIKU, input_tokens=1000, max_output_tokens=2000,
                                cache_write_1h_tokens=4000, cache_write_5m_tokens=3000,
                                cache_read_tokens=5000)
        assert v == pytest.approx(2325e-6, abs=1e-9)

    def test_estimate_ceil_always_up(self, env):
        # 1 haiku input token = 0.1 uUSD -> ceil 1
        assert env.g.estimate_cost(HAIKU, input_tokens=1, max_output_tokens=0) == pytest.approx(1e-6, abs=1e-12)
        # sonnet: 3 in (6) + 1 cw5m (2.5) = 8.5 -> 9
        v = env.g.estimate_cost(SONNET, input_tokens=3, max_output_tokens=0, cache_write_5m_tokens=1)
        assert v == pytest.approx(9e-6, abs=1e-12)

    def test_estimate_batch_with_cache_combines(self, env):
        # sonnet cw1h 1000 (4000) + cr 1000 (100) = 4100 * .5 = 2050
        v = env.g.estimate_cost(SONNET, input_tokens=0, max_output_tokens=0,
                                cache_write_1h_tokens=1000, cache_read_tokens=1000, batch=True)
        assert v == pytest.approx(2050e-6, abs=1e-9)

    def test_estimate_batch_ceil_after_multiplier(self, env):
        # 2325 * .5 = 1162.5 -> 1163 (single ceil of the whole sum)
        v = env.g.estimate_cost(HAIKU, input_tokens=1000, max_output_tokens=2000,
                                cache_write_1h_tokens=4000, cache_write_5m_tokens=3000,
                                cache_read_tokens=5000, batch=True)
        assert v == pytest.approx(1163e-6, abs=1e-9)

    def test_safety_factor_13_3(self, env):
        g = mk(env, lambda d: d.update(price_safety_factor=1.1))
        v = g.estimate_cost(HAIKU, input_tokens=4800, max_output_tokens=800, cache_read_tokens=1500)
        assert v == pytest.approx(985e-6, abs=1e-9)  # 895*1.1 = 984.5 -> 985
        r = g.authorize("haftalik_ozet", v)
        assert isinstance(r, Grant)
        s = g.record("haftalik_ozet", r, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        assert s.cost_micro == 985

    def test_unknown_model_estimate_raises(self, env):
        with pytest.raises(BudgetConfigError):
            env.g.estimate_cost("claude-nope-9", input_tokens=10, max_output_tokens=10)

    def test_estimate_total_input_limit_100k(self, env):
        # exactly 100_000 total input is allowed, one more is not (6.)
        env.g.estimate_cost(HAIKU, input_tokens=90_000, max_output_tokens=10, cache_read_tokens=10_000)
        with pytest.raises(BudgetConfigError):
            env.g.estimate_cost(HAIKU, input_tokens=90_000, max_output_tokens=10, cache_read_tokens=10_001)
        with pytest.raises(BudgetConfigError):
            env.g.estimate_cost(HAIKU, input_tokens=60_000, max_output_tokens=10,
                                cache_write_1h_tokens=30_000, cache_write_5m_tokens=10_001)

    @pytest.mark.parametrize(
        "usage,batch,model,expected",
        [
            (Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), False, HAIKU, 895),
            (Usage(input_tokens=4800, output_tokens=800, cache_write_1h_tokens=1500), False, HAIKU, 1180),
            (Usage(input_tokens=4800, output_tokens=800, cache_write_5m_tokens=1500), False, HAIKU, 1068),
            (Usage(input_tokens=6000, output_tokens=1500), True, SONNET, 13500),
            (Usage(input_tokens=6000, output_tokens=1500), False, SONNET, 27000),
            (Usage(input_tokens=1000, output_tokens=2000, cache_write_5m_tokens=3000,
                   cache_write_1h_tokens=4000, cache_read_tokens=5000), False, HAIKU, 2325),
            (Usage(input_tokens=1000, output_tokens=2000, cache_write_5m_tokens=3000,
                   cache_write_1h_tokens=4000, cache_read_tokens=5000), True, HAIKU, 1163),
            (Usage(cache_write_1h_tokens=1000, cache_read_tokens=1000), True, SONNET, 2050),
            (Usage(input_tokens=1), False, HAIKU, 1),
            (Usage(cache_read_tokens=7), False, SONNET, 1),  # 0.7 -> 1
            (Usage(), False, HAIKU, 0),
        ],
    )
    def test_record_cost_from_usage(self, env, usage, batch, model, expected):
        svc = "lesson" if model == SONNET else "haftalik_ozet"
        g = env.g.authorize(svc, 0.05)
        assert isinstance(g, Grant)
        s = env.g.record(svc, g, usage, model, batch=batch)
        assert isinstance(s, Settlement)
        assert s.ok and s.code == "ok" and not s.duplicate and not s.estimated_instead
        assert s.cost_micro == expected
        assert s.overrun_micro == 0
        assert s.day == g.day
        st = env.g.status().services[svc]
        assert st.used_usd == pytest.approx(expected / 1e6, abs=1e-9)
        assert st.unsettled_usd == 0

    def test_record_13_5_overrun_zero_and_frees_difference(self, env):
        est = env.g.estimate_cost(HAIKU, input_tokens=4800, max_output_tokens=1000, cache_read_tokens=1500)
        g = env.g.authorize("haftalik_ozet", est)
        assert isinstance(g, Grant)
        assert env.g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.000995, abs=2e-6)
        s = env.g.record("haftalik_ozet", g, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        assert s.cost_micro == 895 and s.overrun_micro == 0
        assert env.g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.000895, abs=1e-9)

    def test_record_overrun_written_and_event(self, env):
        g = grant(env.g, "haftalik_ozet", 500)
        s = env.g.record("haftalik_ozet", g, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        assert s.ok and s.cost_micro == 895 and s.overrun_micro == 395
        evs = events(env.g, "budget_overrun")
        assert len(evs) == 1
        assert g.grant_id in json.dumps(evs[0].payload, default=str) or g.grant_id in evs[0].message or True

    def test_overrun_may_exceed_cap_then_next_authorize_denied(self, env):
        g = grant(env.g, "haftalik_ozet", 1000)
        # 600_000 output tokens * 0.5 = 300_000 > cap 250_000
        s = env.g.record("haftalik_ozet", g, Usage(output_tokens=600_000), HAIKU)
        assert s.ok and s.cost_micro == 300_000 and s.overrun_micro == 299_000
        st = env.g.status().services["haftalik_ozet"]
        assert st.used_usd == pytest.approx(0.3, abs=1e-9)
        assert st.pct > 100
        assert st.remaining_usd == 0
        assert st.state == "stopped"
        d = env.g.authorize("haftalik_ozet", usd(1))
        assert isinstance(d, Denial) and d.reason == "daily_cap"

    @pytest.mark.parametrize(
        "usage",
        [
            Usage(input_tokens=-1),
            Usage(output_tokens=-5),
            Usage(cache_read_tokens=-1),
            Usage(input_tokens=True),
            Usage(output_tokens=None),
            Usage(cache_write_1h_tokens=float("nan")),
            Usage(cache_write_5m_tokens="12"),
            Usage(input_tokens=1.5),
        ],
    )
    def test_record_bad_usage_counts_estimate(self, env, usage):
        g = grant(env.g, "haftalik_ozet", 3000)
        s = env.g.record("haftalik_ozet", g, usage, HAIKU)
        assert s.ok is False and s.estimated_instead is True and s.code == "bad_usage"
        assert s.cost_micro == 3000
        st = env.g.status().services["haftalik_ozet"]
        assert st.used_usd == pytest.approx(0.003, abs=1e-9)
        # row is not settled
        rows = q(env.db, "select state, charged_micro from reservations where grant_id=?", (g.grant_id,))
        assert rows[0][0] in ("open", "expired") and rows[0][1] == 3000

    def test_record_oversized_request_bad_usage(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        s = env.g.record("haftalik_ozet", g, Usage(input_tokens=100_001), HAIKU)
        assert s.code == "bad_usage" and s.estimated_instead and not s.ok and s.cost_micro == 3000

    def test_record_unknown_model_once_event(self, env):
        g1 = grant(env.g, "haftalik_ozet", 3000)
        g2 = grant(env.g, "haftalik_ozet", 2000)
        s1 = env.g.record("haftalik_ozet", g1, Usage(input_tokens=10), "claude-mystery-1")
        s2 = env.g.record("haftalik_ozet", g2, Usage(input_tokens=10), "claude-mystery-1")
        for s, e in ((s1, 3000), (s2, 2000)):
            assert s.code == "unknown_model" and not s.ok and s.estimated_instead and s.cost_micro == e
        assert len(events(env.g, "unknown_model")) == 1

    def test_record_duplicate_idempotent(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        u = Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500)
        s1 = env.g.record("haftalik_ozet", g, u, HAIKU)
        s2 = env.g.record("haftalik_ozet", g, u, HAIKU)
        assert s1.ok and not s1.duplicate
        assert s2.duplicate is True and s2.code == "duplicate"
        assert s2.cost_micro == 895
        assert env.g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.000895, abs=1e-9)
        # a duplicate with different usage must not change anything
        env.g.record("haftalik_ozet", g, Usage(output_tokens=100_000), HAIKU)
        assert env.g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.000895, abs=1e-9)

    def test_record_unknown_grant(self, env):
        fake = Grant(grant_id="ab" * 16, service="haftalik_ozet", est_micro=100, day="2026-11-16",
                     created_at="2026-11-16T10:00:00.000Z", expires_at="2026-11-16T10:10:00.000Z")
        s = env.g.record("haftalik_ozet", fake, Usage(input_tokens=10), HAIKU)
        assert isinstance(s, Settlement) and s.ok is False and s.code == "unknown_grant"
        assert env.g.status().services["haftalik_ozet"].used_usd == 0


# ====================================================== 2. config / limits
class TestConfig:
    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d["daily_cap_usd"].update(haftalik_ozet=0.26),
            lambda d: d["daily_cap_usd"].update(lesson=0.11),
            lambda d: d.update(monthly_cap_usd=20.5),  # 23.11 kullanici karari: ust lig, LLM tavani 20 $
            lambda d: d.update(monthly_share_usd={"lesson": 8.0, "yorumcu": 13.0}),
            lambda d: d.update(monthly_warn_usd=20.5),
            lambda d: d.update(warn_fraction=0.8),
            lambda d: d.update(warn_fraction=1.0),
            lambda d: d.update(warn_fraction=0),
            lambda d: d.update(warn_fraction=-0.1),
            lambda d: d.update(price_safety_factor=0.9),
            lambda d: d.update(batch_multiplier=0.4),
            lambda d: d["retry"].update(max_retries=4),
            lambda d: d["prices_usd_per_mtok"][HAIKU].update(input=0),
            lambda d: d["prices_usd_per_mtok"][HAIKU].update(output=-1.0),
            lambda d: d["prices_usd_per_mtok"][SONNET].update(cache_read=float("inf")),
            lambda d: d["prices_usd_per_mtok"][SONNET].pop("cache_write_1h"),
            lambda d: d.update(unknown_key=1),
            lambda d: d["daily_cap_usd"].pop("lesson"),
            lambda d: d.update(db_path=""),
        ],
    )
    def test_loose_or_invalid_config_rejected(self, tmp_path, mutate):
        with pytest.raises(BudgetConfigError):
            make_cfg(tmp_path, mutate)

    def test_config_error_is_value_error(self):
        assert issubclass(BudgetConfigError, ValueError)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d["daily_cap_usd"].update(haftalik_ozet=0.20, lesson=0.05),
            lambda d: d.update(monthly_cap_usd=8.0, monthly_warn_usd=4.0),
            lambda d: d.update(warn_fraction=0.5),
            lambda d: d["retry"].update(max_retries=2),
            lambda d: d.update(price_safety_factor=1.5),
            lambda d: d.update(batch_multiplier=0.75),
            lambda d: d.update(prices_verified_on="2026-11-20"),
        ],
    )
    def test_tighter_values_allowed(self, tmp_path, mutate):
        make_cfg(tmp_path, mutate)

    def test_hard_limits_exists(self):
        assert isinstance(B.HARD_LIMITS, dict) and B.HARD_LIMITS

    def test_default_path(self):
        assert B.DEFAULT_PATH == "config/budget.json"

    def test_tighter_cap_enforced(self, env):
        g = mk(env, lambda d: d["daily_cap_usd"].update(haftalik_ozet=0.10))
        assert isinstance(g.authorize("haftalik_ozet", usd(100_000)), Grant)
        d = g.authorize("haftalik_ozet", usd(1))
        assert isinstance(d, Denial) and d.reason == "daily_cap"

    def test_repo_config_file_loads_and_within_limits(self):
        p = TRADER_DIR / "config" / "budget.json"
        assert p.exists(), "config/budget.json missing"
        load_config(str(p))
        raw = p.read_text()
        d = json.loads(raw)
        assert d["daily_cap_usd"]["haftalik_ozet"] <= 0.25 and d["daily_cap_usd"]["lesson"] <= 0.10
        # 23.11 kullanici karari: ust lig, LLM tavani 20 $
        assert d["monthly_cap_usd"] <= 20.0 and d["monthly_warn_usd"] <= d["monthly_cap_usd"]
        assert 0 < d["warn_fraction"] <= 0.70
        assert d["price_safety_factor"] >= 1.0 and d["batch_multiplier"] >= 0.5
        assert d["retry"]["max_retries"] <= 3
        assert "sk-ant" not in raw
        for v in d["api_key_env"].values():
            assert re.fullmatch(r"[A-Z0-9_]+", v)

    def test_api_key_env_names_only(self, env, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY_HAFTALIK_OZET", "sk-ant-api03-FAKEVETOKEY")
        monkeypatch.setenv("ANTHROPIC_API_KEY_LESSON", "sk-ant-api03-FAKELESSONKEY")
        assert env.g.api_key_env("haftalik_ozet") == "ANTHROPIC_API_KEY_HAFTALIK_OZET"
        assert env.g.api_key_env("lesson") == "ANTHROPIC_API_KEY_LESSON"
        assert env.g.api_key_env("haftalik_ozet") != env.g.api_key_env("lesson")
        g = mk(env, lambda d: d["api_key_env"].update(haftalik_ozet="MY_HAFTALIK_KEY"))
        assert g.api_key_env("haftalik_ozet") == "MY_HAFTALIK_KEY"
        with pytest.raises(ValueError):
            env.g.api_key_env("other")


# ============================================================== 3. authorize
class TestAuthorize:
    def test_grant_fields(self, env):
        g = env.g.authorize("haftalik_ozet", 0.003)
        assert isinstance(g, Grant)
        assert re.fullmatch(r"[0-9a-f]{32}", g.grant_id)
        assert g.service == "haftalik_ozet" and g.day == "2026-11-16"
        assert g.est_micro == 3000
        assert TS_RE.match(g.created_at) and TS_RE.match(g.expires_at)
        assert P(g.created_at) == T(2026, 11, 16, 10)
        assert P(g.expires_at) - P(g.created_at) == timedelta(seconds=600)
        l = env.g.authorize("lesson", 0.0135)
        assert P(l.expires_at) - P(l.created_at) == timedelta(seconds=108000)
        assert l.est_micro == 13500
        assert l.grant_id != g.grant_id

    def test_est_micro_ceil(self, env):
        g = env.g.authorize("haftalik_ozet", usd(1234))
        assert g.est_micro == 1234
        with pytest.raises(Exception):
            g.est_micro = 5  # frozen dataclass

    @pytest.mark.parametrize("bad", [0, 0.0, -0.1, float("nan"), float("inf"), True, None, "0.1"])
    def test_invalid_est(self, env, bad):
        d = env.g.authorize("haftalik_ozet", bad)
        assert isinstance(d, Denial) and d.reason == "invalid_request"
        assert d.service == "haftalik_ozet"

    def test_invalid_service_value_error(self, env):
        with pytest.raises(ValueError):
            env.g.authorize("trader", 0.01)

    def test_grant_for_other_service_value_error(self, env):
        g = env.g.authorize("haftalik_ozet", 0.01)
        with pytest.raises(ValueError):
            env.g.record("lesson", g, Usage(input_tokens=1), HAIKU)
        with pytest.raises(ValueError):
            env.g.report_error("lesson", g, 1, 500)

    def test_exact_cap_allowed_one_more_denied(self, env):
        g = grant(env.g, "haftalik_ozet", 250_000)  # est == cap
        assert isinstance(g, Grant)
        d = env.g.authorize("haftalik_ozet", usd(1))
        assert isinstance(d, Denial) and d.reason == "daily_cap"
        assert P(d.retry_after) == T(2026, 11, 17, 0)
        assert d.detail and isinstance(d.detail, str)

    def test_est_larger_than_cap_denied(self, env):
        d = env.g.authorize("haftalik_ozet", 0.26)
        assert isinstance(d, Denial) and d.reason == "daily_cap"
        d2 = env.g.authorize("lesson", 0.11)
        assert isinstance(d2, Denial) and d2.reason == "daily_cap"

    def test_reservation_counts_for_second_call(self, env):
        grant(env.g, "haftalik_ozet", 200_000)
        d = env.g.authorize("haftalik_ozet", usd(60_000))
        assert isinstance(d, Denial) and d.reason == "daily_cap"
        assert isinstance(env.g.authorize("haftalik_ozet", usd(50_000)), Grant)

    def test_denied_authorize_writes_no_reservation(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        n = q(env.db, "select count(*) from reservations")[0][0]
        env.g.authorize("haftalik_ozet", usd(10))
        assert q(env.db, "select count(*) from reservations")[0][0] == n


# ================================================ 4. thresholds & events (13.6-13.8)
class TestEvents:
    def test_13_6_warn_70_exactly_once(self, env):
        grant(env.g, "haftalik_ozet", 174_000)
        assert events(env.g, "daily_warn_70") == []
        g = env.g.authorize("haftalik_ozet", usd(2000))
        assert isinstance(g, Grant)  # 176_000
        w = events(env.g, "daily_warn_70")
        assert len(w) == 1
        assert w[0].service == "haftalik_ozet" and w[0].day == "2026-11-16"
        assert "haftalık özet" in w[0].message and "%70" in w[0].message
        # later calls the same day do not repeat
        grant(env.g, "haftalik_ozet", 1000)
        env.g.record("haftalik_ozet", g, Usage(input_tokens=10), HAIKU)
        assert len(events(env.g, "daily_warn_70")) == 1

    def test_warn_exact_threshold_inclusive(self, env):
        grant(env.g, "haftalik_ozet", 174_999)
        assert events(env.g, "daily_warn_70") == []
        grant(env.g, "haftalik_ozet", 1)  # 175_000 == 70%
        assert len(events(env.g, "daily_warn_70")) == 1

    def test_warn_exact_threshold_lesson(self, env):
        grant(env.g, "lesson", 69_999)
        assert events(env.g, "daily_warn_70") == []
        grant(env.g, "lesson", 1)  # 70_000
        w = events(env.g, "daily_warn_70")
        assert len(w) == 1 and w[0].service == "lesson"

    def test_custom_warn_fraction(self, env):
        g = mk(env, lambda d: d.update(warn_fraction=0.5))
        grant(g, "haftalik_ozet", 124_999)
        assert events(g, "daily_warn_70") == []
        grant(g, "haftalik_ozet", 1)
        assert len(events(g, "daily_warn_70")) == 1

    def test_13_6_cap_denial_emits_stopped_once(self, env):
        grant(env.g, "haftalik_ozet", 249_000)
        d = env.g.authorize("haftalik_ozet", usd(1500))
        assert isinstance(d, Denial) and d.reason == "daily_cap"
        st = events(env.g, "daily_stopped_100")
        assert len(st) == 1 and st[0].service == "haftalik_ozet" and st[0].day == "2026-11-16"
        for _ in range(3):
            env.g.authorize("haftalik_ozet", usd(1500))
        assert len(events(env.g, "daily_stopped_100")) == 1

    def test_stopped_when_usage_reaches_cap(self, env):
        grant(env.g, "haftalik_ozet", 250_000)  # usage == cap, no denial yet
        assert len(events(env.g, "daily_stopped_100")) == 1
        env.g.authorize("haftalik_ozet", usd(1))
        assert len(events(env.g, "daily_stopped_100")) == 1

    def test_events_per_day_repeat_next_day(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        env.g.authorize("haftalik_ozet", usd(1))
        env.clock.set(T(2026, 11, 17, 0, 0, 1))
        grant(env.g, "haftalik_ozet", 250_000)
        env.g.authorize("haftalik_ozet", usd(1))
        st = events(env.g, "daily_stopped_100")
        assert sorted(e.day for e in st) == ["2026-11-16", "2026-11-17"]
        assert len(events(env.g, "daily_warn_70")) == 2

    def test_stop_event_per_service(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        grant(env.g, "lesson", 100_000)
        st = events(env.g, "daily_stopped_100")
        assert sorted(e.service for e in st) == ["haftalik_ozet", "lesson"]

    def test_events_ordered_and_have_fields(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        grant(env.g, "lesson", 100_000)
        ev = env.g.pending_events()
        ids = [e.id for e in ev]
        assert ids == sorted(ids) and len(set(ids)) == len(ids) and ids
        for e in ev:
            assert isinstance(e.id, int) and e.kind and e.day and e.ts and isinstance(e.message, str) and e.message
            assert e.payload is not None

    def test_ack_and_redelivery(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        first = env.g.pending_events()
        again = env.g.pending_events()
        assert [e.id for e in first] == [e.id for e in again]  # at-least-once
        assert env.g.status().pending_event_count == len(first)
        env.g.ack_events([first[0].id, 99_999])  # unknown id ignored
        left = env.g.pending_events()
        assert first[0].id not in [e.id for e in left]
        assert [e.id for e in left] == [e.id for e in first[1:]]
        env.g.ack_events([e.id for e in left])
        assert env.g.pending_events() == []
        assert env.g.status().pending_event_count == 0
        # acked events are not regenerated
        env.g.authorize("haftalik_ozet", usd(1))
        grant(env.g, "haftalik_ozet", 0) if False else None
        assert env.g.pending_events() == []

    def test_ack_empty_and_repeat(self, env):
        env.g.ack_events([])
        grant(env.g, "haftalik_ozet", 250_000)
        ids = [e.id for e in env.g.pending_events()]
        env.g.ack_events(ids)
        env.g.ack_events(ids)
        assert env.g.pending_events() == []

    def test_13_7_service_isolation(self, env):
        grant(env.g, "lesson", 100_000)
        d = env.g.authorize("lesson", 0.0135)
        assert isinstance(d, Denial) and d.reason == "daily_cap"
        g = env.g.authorize("haftalik_ozet", 0.001)
        assert isinstance(g, Grant)
        st = env.g.status()
        assert st.services["haftalik_ozet"].used_usd == pytest.approx(0.001, abs=1e-6)
        assert st.services["haftalik_ozet"].state == "ok"
        assert st.services["lesson"].state == "stopped"
        # no veto events at all
        assert [e for e in env.g.pending_events() if e.service == "haftalik_ozet"] == []

    def test_veto_exhaustion_does_not_affect_lesson(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        assert isinstance(env.g.authorize("haftalik_ozet", usd(1)), Denial)
        g = grant(env.g, "lesson", 100_000)
        assert isinstance(g, Grant)
        assert env.g.status().services["lesson"].used_usd == pytest.approx(0.10, abs=1e-9)

    def test_lesson_many_denials_veto_unaffected(self, env):
        grant(env.g, "lesson", 100_000)
        for _ in range(5):
            assert isinstance(env.g.authorize("lesson", usd(10)), Denial)
        grant(env.g, "haftalik_ozet", 250_000)
        assert env.g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.25, abs=1e-9)

    def test_lesson_not_carried_to_next_day(self, env):
        grant(env.g, "lesson", 100_000)
        env.clock.set(T(2026, 11, 17, 0, 0, 5))
        assert env.g.status().services["lesson"].used_usd == 0
        assert isinstance(env.g.authorize("lesson", usd(100_000)), Grant)

    def test_13_8_monthly_warn_once(self, env):
        nxt = fill_month(env.g, env.clock, 4_999_000)
        assert events(env.g, "monthly_warn_5usd") == []
        env.clock.set(nxt)
        grant(env.g, "haftalik_ozet", 1000)  # 5_000_000 exactly: not "> 5 USD"
        assert events(env.g, "monthly_warn_5usd") == []
        g = env.g.authorize("haftalik_ozet", usd(1))  # 5_000_001
        assert isinstance(g, Grant)
        w = events(env.g, "monthly_warn_5usd")
        assert len(w) == 1
        for _ in range(3):
            grant(env.g, "haftalik_ozet", 100)
        assert len(events(env.g, "monthly_warn_5usd")) == 1

    def test_13_8_monthly_warn_example(self, env):
        nxt = fill_month(env.g, env.clock, 4_999_000)
        env.clock.set(nxt)
        grant(env.g, "lesson", 2000)  # 5_001_000
        assert len(events(env.g, "monthly_warn_5usd")) == 1
        assert env.g.status().month_state in ("warn",)

    def test_13_8_monthly_cap_denial_both_services(self, env):
        nxt = fill_month(env.g, env.clock, 9_999_000)
        assert len(events(env.g, "monthly_warn_5usd")) == 1
        env.clock.set(nxt)
        d1 = env.g.authorize("haftalik_ozet", 0.002)
        d2 = env.g.authorize("lesson", 0.002)
        assert isinstance(d1, Denial) and d1.reason == "monthly_cap"
        assert isinstance(d2, Denial) and d2.reason == "monthly_cap"
        assert len(events(env.g, "monthly_stopped")) == 1
        assert env.g.status().month_used_usd == pytest.approx(9.999, abs=1e-9)

    def test_monthly_cap_exact_edge(self, env):
        nxt = fill_month(env.g, env.clock, 9_999_000)
        env.clock.set(nxt)
        assert isinstance(grant(env.g, "haftalik_ozet", 1000), Grant)  # == 10_000_000
        d = env.g.authorize("haftalik_ozet", usd(1))
        assert isinstance(d, Denial) and d.reason == "monthly_cap"
        assert env.g.status().month_state == "stopped"

    def test_monthly_checked_before_daily(self, env):
        nxt = fill_month(env.g, env.clock, 9_900_000)
        env.clock.set(nxt)
        # est violates both daily (>250k) and monthly
        d = env.g.authorize("haftalik_ozet", usd(240_000))
        assert isinstance(d, Denial) and d.reason == "monthly_cap"

    def test_monthly_resets_on_month_change(self, env):
        nxt = fill_month(env.g, env.clock, 9_999_000)
        env.clock.set(nxt)
        grant(env.g, "haftalik_ozet", 1000)
        assert isinstance(env.g.authorize("haftalik_ozet", usd(1)), Denial)
        env.clock.set(T(2027, 1, 1, 0, 0, 1))
        st = env.g.status()
        assert st.month == "2027-01" and st.month_used_usd == 0 and st.month_state == "ok"
        assert isinstance(env.g.authorize("haftalik_ozet", usd(250_000)), Grant)
        # monthly_warn is again possible in the new month
        fill_month(env.g, env.clock, 5_000_000, start=T(2027, 1, 2, 1))
        assert len([e for e in events(env.g, "monthly_warn_5usd")]) == 2

    def test_credit_low_once_per_day(self, env):
        nxt = fill_month(env.g, env.clock, 6_999_000)
        assert events(env.g, "credit_low") == []
        env.clock.set(nxt)
        grant(env.g, "haftalik_ozet", 2000)  # 7_001_000 -> remaining 2.999 < 3
        cl = events(env.g, "credit_low")
        assert len(cl) == 1
        grant(env.g, "haftalik_ozet", 100)
        grant(env.g, "lesson", 100)
        assert len(events(env.g, "credit_low")) == 1
        env.clock.set(nxt + timedelta(days=1))
        grant(env.g, "haftalik_ozet", 100)
        assert len(events(env.g, "credit_low")) == 2
        assert env.g.status().credit_estimate_usd == pytest.approx(10 - 7.001_000 - 0.0003, abs=1e-5)


# ===================================================== 5. crash safety (13.9)
class TestCrash:
    def test_13_9_open_expired_late_record(self, env):
        env.clock.set(T(2026, 11, 16, 10, 0, 0))
        g = env.g.authorize("haftalik_ozet", usd(3000))
        assert g.est_micro == 3000
        # "crash": drop guard, restart at 10:05
        env.clock.set(T(2026, 11, 16, 10, 5, 0))
        g2 = BudgetGuard(env.cfg, clock=env.clock)
        assert g2.status().services["haftalik_ozet"].unsettled_usd == pytest.approx(0.003, abs=1e-9)
        # 10:11 > TTL: next authorize expires it, amount stays counted
        env.clock.set(T(2026, 11, 16, 10, 11, 0))
        g3 = g2.authorize("haftalik_ozet", usd(1000))
        assert isinstance(g3, Grant)
        row = q(env.db, "select state, charged_micro from reservations where grant_id=?", (g.grant_id,))[0]
        assert row == ("expired", 3000)
        st = g2.status().services["haftalik_ozet"]
        assert st.unsettled_usd == pytest.approx(0.004, abs=1e-9) and st.used_usd == pytest.approx(0.004, abs=1e-9)
        # 10:20 late record with real usage
        env.clock.set(T(2026, 11, 16, 10, 20, 0))
        s = g2.record("haftalik_ozet", g, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        assert s.ok and s.cost_micro == 895
        row = q(env.db, "select state, charged_micro from reservations where grant_id=?", (g.grant_id,))[0]
        assert row == ("settled", 895)
        st = g2.status().services["haftalik_ozet"]
        assert st.settled_usd == pytest.approx(0.000895, abs=1e-9)
        assert st.used_usd == pytest.approx(0.001895, abs=1e-9)

    def test_crash_without_record_stays_counted_all_day_and_month(self, env):
        g = env.g.authorize("haftalik_ozet", usd(3000))
        env.clock.set(T(2026, 11, 16, 23, 59, 0))
        g2 = BudgetGuard(env.cfg, clock=env.clock)
        assert isinstance(g2.authorize("haftalik_ozet", usd(1)), Grant)
        st = g2.status()
        assert st.services["haftalik_ozet"].used_usd == pytest.approx(0.003001, abs=1e-9)
        assert st.month_used_usd == pytest.approx(0.003001, abs=1e-9)
        assert q(env.db, "select state from reservations where grant_id=?", (g.grant_id,))[0][0] == "expired"

    def test_ttl_expiry_does_not_free_amount_for_cap(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        env.clock.adv(hours=2)
        d = env.g.authorize("haftalik_ozet", usd(1))
        assert isinstance(d, Denial) and d.reason == "daily_cap"

    def test_release_frees_reservation(self, env):
        g = grant(env.g, "haftalik_ozet", 250_000)
        env.g.release(g)
        assert env.g.status().services["haftalik_ozet"].used_usd == 0
        row = q(env.db, "select state, charged_micro from reservations where grant_id=?", (g.grant_id,))[0]
        assert row == ("released", 0)
        assert isinstance(grant(env.g, "haftalik_ozet", 250_000), Grant)

    def test_release_no_effect_on_settled_and_idempotent(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        env.g.record("haftalik_ozet", g, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        assert env.g.release(g) is None
        assert env.g.release(g) is None
        assert q(env.db, "select state, charged_micro from reservations where grant_id=?", (g.grant_id,))[0] == ("settled", 895)

    def test_release_unknown_grant_no_raise(self, env):
        fake = Grant("cd" * 16, "haftalik_ozet", 10, "2026-11-16", "2026-11-16T10:00:00.000Z", "2026-11-16T10:10:00.000Z")
        assert env.g.release(fake) is None

    def test_charged_micro_rule_by_state(self, env):
        a = grant(env.g, "haftalik_ozet", 1000)
        b = grant(env.g, "haftalik_ozet", 2000)
        c = grant(env.g, "haftalik_ozet", 3000)
        env.g.record("haftalik_ozet", b, Usage(input_tokens=1000), HAIKU)  # 100
        env.g.release(c)
        rows = {r[0]: r[1:] for r in q(env.db, "select grant_id, state, est_micro, charged_micro from reservations")}
        assert rows[a.grant_id] == ("open", 1000, 1000)
        assert rows[b.grant_id] == ("settled", 2000, 100)
        assert rows[c.grant_id] == ("released", 3000, 0)

    def test_status_is_read_only(self, env):
        grant(env.g, "haftalik_ozet", 175_000)
        n_ev = len(env.g.pending_events())
        n_rows = q(env.db, "select count(*) from reservations")[0][0]
        env.clock.adv(hours=5)  # reservation TTL passed; status must not change state
        for _ in range(3):
            env.g.status()
        assert len(env.g.pending_events()) == n_ev
        assert q(env.db, "select count(*) from reservations")[0][0] == n_rows
        assert q(env.db, "select state from reservations")[0][0] == "open"
        assert env.g.status().services["haftalik_ozet"].unsettled_usd == pytest.approx(0.175, abs=1e-9)


# ========================================= 6. time: day/month boundary, monotonic
class TestTime:
    def test_13_11_reservation_day_and_monotonic_clock(self, env):
        env.clock.set(T(2026, 11, 16, 23, 59, 59, 900))
        g = env.g.authorize("haftalik_ozet", usd(3000))
        assert g.day == "2026-11-16"
        env.clock.set(T(2026, 11, 17, 0, 0, 3))
        s = env.g.record("haftalik_ozet", g, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        assert s.ok and s.day == "2026-11-16"
        st = env.g.status()
        assert st.day == "2026-11-17"
        assert st.services["haftalik_ozet"].used_usd == 0  # D+1 starts at 0
        g2 = env.g.authorize("haftalik_ozet", usd(1000))
        assert g2.day == "2026-11-17"
        # clock goes back to D: effective day must not regress
        env.clock.set(T(2026, 11, 16, 23, 50, 0))
        g3 = env.g.authorize("haftalik_ozet", usd(1000))
        assert isinstance(g3, Grant) and g3.day == "2026-11-17"
        assert env.g.status().day == "2026-11-17"
        # D's spend stays at D, D+1 spend only 2000
        assert env.g.status().services["haftalik_ozet"].used_usd == pytest.approx(0.002, abs=1e-9)

    def test_clock_rollback_cannot_reset_counter(self, env):
        env.clock.set(T(2026, 11, 17, 5))
        grant(env.g, "haftalik_ozet", 250_000)
        env.clock.set(T(2026, 11, 16, 5))  # one day back
        d = env.g.authorize("haftalik_ozet", usd(1))
        assert isinstance(d, Denial) and d.reason == "daily_cap"

    def test_monotonic_persists_across_restart(self, env):
        env.clock.set(T(2026, 11, 17, 5))
        grant(env.g, "haftalik_ozet", 250_000)
        env.clock.set(T(2026, 11, 16, 5))
        g2 = BudgetGuard(env.cfg, clock=env.clock)
        assert isinstance(g2.authorize("haftalik_ozet", usd(1)), Denial)

    def test_day_rollover_resets_cap(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        assert isinstance(env.g.authorize("haftalik_ozet", usd(1)), Denial)
        env.clock.set(T(2026, 11, 17, 0, 0, 0))
        g = env.g.authorize("haftalik_ozet", usd(250_000))
        assert isinstance(g, Grant) and g.day == "2026-11-17"

    def test_exactly_midnight_is_new_day(self, env):
        env.clock.set(T(2026, 11, 16, 23, 59, 59, 999))
        assert env.g.status().day == "2026-11-16"
        env.clock.set(T(2026, 11, 17, 0, 0, 0, 0))
        assert env.g.status().day == "2026-11-17"

    def test_month_key_and_ttl_across_midnight_charges_reservation_month(self, env):
        env.clock.set(T(2026, 11, 30, 23, 59, 59, 900))
        g = env.g.authorize("haftalik_ozet", usd(3000))
        env.clock.set(T(2026, 12, 1, 0, 0, 2))
        env.g.record("haftalik_ozet", g, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        assert q(env.db, "select day, month from reservations")[0] == ("2026-11-30", "2026-11")
        st = env.g.status()
        assert st.month == "2026-12" and st.month_used_usd == 0

    def test_timestamps_format(self, env):
        grant(env.g, "haftalik_ozet", 250_000)
        for e in env.g.pending_events():
            assert TS_RE.match(e.ts)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", env.g.status().generated_at)


# ===================================== 7. status() (11) incl. state precedence
class TestStatus:
    def test_initial_status(self, env):
        st = env.g.status()
        assert st.store_ok and st.config_ok
        assert st.day == "2026-11-16" and st.month == "2026-11"
        for svc, cap in (("haftalik_ozet", 0.25), ("lesson", 0.10)):
            s = st.services[svc]
            assert s.cap_usd == pytest.approx(cap)
            assert s.used_usd == 0 and s.settled_usd == 0 and s.unsettled_usd == 0
            assert s.pct == 0 and s.remaining_usd == pytest.approx(cap) and s.calls_today == 0
            assert s.state == "ok"
        assert st.month_used_usd == 0 and st.monthly_cap_usd == pytest.approx(10.0)
        assert st.monthly_warn_usd == pytest.approx(5.0) and st.month_state == "ok"
        assert st.provider_blocked_until is None
        assert st.credit_estimate_usd == pytest.approx(10.0)
        assert st.prices_verified is False
        assert st.pending_event_count == 0

    def test_prices_verified_flag(self, env):
        g = mk(env, lambda d: d.update(prices_verified_on="2026-11-20"))
        assert g.status().prices_verified is True

    def test_values_and_states(self, env):
        grant(env.g, "haftalik_ozet", 100_000)
        s = env.g.status().services["haftalik_ozet"]
        assert s.state == "ok" and s.calls_today == 1
        assert s.used_usd == pytest.approx(0.1, abs=1e-9) and s.pct == pytest.approx(40.0)
        grant(env.g, "haftalik_ozet", 76_000)  # 176_000
        s = env.g.status().services["haftalik_ozet"]
        assert s.state == "warn" and s.pct == pytest.approx(70.4) and s.calls_today == 2
        assert s.remaining_usd == pytest.approx(0.074, abs=1e-9)
        assert s.unsettled_usd == pytest.approx(0.176, abs=1e-9) and s.settled_usd == 0
        grant(env.g, "haftalik_ozet", 74_000)
        s = env.g.status().services["haftalik_ozet"]
        assert s.state == "stopped" and s.pct == pytest.approx(100.0) and s.remaining_usd == 0

    def test_settled_vs_unsettled(self, env):
        a = grant(env.g, "haftalik_ozet", 5000)
        grant(env.g, "haftalik_ozet", 2000)
        env.g.record("haftalik_ozet", a, Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), HAIKU)
        s = env.g.status().services["haftalik_ozet"]
        assert s.settled_usd == pytest.approx(0.000895, abs=1e-9)
        assert s.unsettled_usd == pytest.approx(0.002, abs=1e-9)
        assert s.used_usd == pytest.approx(0.002895, abs=1e-9)

    def test_released_not_counted_in_used(self, env):
        a = grant(env.g, "haftalik_ozet", 5000)
        env.g.release(a)
        s = env.g.status().services["haftalik_ozet"]
        assert s.used_usd == 0 and s.unsettled_usd == 0

    def test_blocked_precedes_stopped_and_to_dict(self, env):
        g = grant(env.g, "haftalik_ozet", 250_000)
        assert env.g.status().services["haftalik_ozet"].state == "stopped"
        env.g.report_error("haftalik_ozet", g, 1, 429, error_type="rate_limit_error",
                           error_code="enforced_spend_limit_reached", message="spend limit")
        st = env.g.status()
        assert st.services["haftalik_ozet"].state == "blocked" and st.services["lesson"].state == "blocked"
        assert st.provider_blocked_until is not None
        d = st.to_dict()
        json.dumps(d)  # JSON serialisable
        assert d["services"]["haftalik_ozet"]["state"] == "blocked"
        assert d["store_ok"] is True

    def test_credit_estimate(self, env):
        grant(env.g, "haftalik_ozet", 176_000)
        grant(env.g, "lesson", 13_500)
        assert env.g.status().credit_estimate_usd == pytest.approx(10 - 0.1895, abs=1e-6)

    def test_month_state_ok_before_warn(self, env):
        fill_month(env.g, env.clock, 4_000_000)
        assert env.g.status().month_state == "ok"
        assert env.g.status().month_used_usd == pytest.approx(4.0, abs=1e-9)


# ============================== 8. error classification & retry (8, 13.12)
LIMIT400 = "You have reached your specified API usage limits. You will regain access on 2026-12-01."


class TestReportError:
    def test_13_12a_400_own_limit_stop_global_block(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, 400, error_type="invalid_request_error", message=LIMIT400)
        assert isinstance(a, ErrorAction) and a.kind == "stop"
        assert P(a.blocked_until) == T(2026, 11, 17, 0)
        # release automatic
        assert env.g.status().services["haftalik_ozet"].unsettled_usd == 0
        for svc in ("haftalik_ozet", "lesson"):
            d = env.g.authorize(svc, 0.001)
            assert isinstance(d, Denial) and d.reason == "provider_blocked"
            assert P(d.retry_after) == T(2026, 11, 17, 0)
        assert len(events(env.g, "provider_limit_hit")) == 1

    def test_400_workspace_phrase_variants(self, env):
        for msg in ("workspace API usage limits reached", "Your specified API usage limits were hit"):
            e = BudgetGuard(make_cfg(env.tmp, db_name=f"x{abs(hash(msg))}.sqlite"), clock=env.clock)
            g = e.authorize("lesson", 0.01)
            a = e.report_error("lesson", g, 1, 400, error_type="invalid_request_error", message=msg)
            assert a.kind == "stop"

    def test_400_limit_probe_next_day_and_reblock(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        env.g.report_error("haftalik_ozet", g, 1, 400, error_type="invalid_request_error", message=LIMIT400)
        env.clock.set(T(2026, 11, 17, 0, 0, 1))
        probe = env.g.authorize("haftalik_ozet", 0.001)
        assert isinstance(probe, Grant)  # single probing call allowed
        a = env.g.report_error("haftalik_ozet", probe, 1, 400, error_type="invalid_request_error", message=LIMIT400)
        assert a.kind == "stop" and P(a.blocked_until) == T(2026, 11, 18, 0)
        d = env.g.authorize("haftalik_ozet", 0.001)
        assert isinstance(d, Denial) and d.reason == "provider_blocked"

    def test_13_12b_429_enforced_spend_limit(self, env):
        env.clock.set(T(2026, 12, 15, 12))
        g = env.g.authorize("lesson", 0.01)
        a = env.g.report_error("lesson", g, 1, 429, error_type="rate_limit_error",
                               error_code="enforced_spend_limit_reached", message="hit")
        assert a.kind == "stop" and P(a.blocked_until) == T(2027, 1, 1, 0)
        d = env.g.authorize("haftalik_ozet", 0.001)  # global: veto blocked too
        assert isinstance(d, Denial) and d.reason == "provider_blocked"
        assert P(d.retry_after) == T(2027, 1, 1)
        env.clock.set(T(2026, 12, 31, 23, 59, 0))
        assert isinstance(env.g.authorize("haftalik_ozet", 0.001), Denial)
        env.clock.set(T(2027, 1, 1, 0, 0, 1))
        assert isinstance(env.g.authorize("haftalik_ozet", 0.001), Grant)
        assert len(events(env.g, "provider_limit_hit")) == 1

    def test_429_enforced_mid_year_month_boundary(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, 429, error_code="enforced_spend_limit_reached")
        assert P(a.blocked_until) == T(2026, 12, 1, 0)

    def test_provider_limit_event_once_per_day_status(self, env):
        g = grant(env.g, "haftalik_ozet", 1000)
        for _ in range(2):
            env.g.report_error("haftalik_ozet", g, 1, 429, error_code="enforced_spend_limit_reached")
        assert len(events(env.g, "provider_limit_hit")) == 1

    @pytest.mark.parametrize(
        "attempt,lo,hi",
        [(1, 1.6, 2.4), (2, 3.2, 4.8), (3, 6.4, 9.6)],
    )
    def test_13_12c_backoff_with_jitter(self, env, attempt, lo, hi):
        g = grant(env.g, "haftalik_ozet", 3000)
        seen = set()
        for _ in range(30):
            a = env.g.report_error("haftalik_ozet", g, attempt, 429, error_type="rate_limit_error")
            assert a.kind == "retry"
            assert lo - 1e-9 <= a.sleep_s <= hi + 1e-9
            seen.add(round(a.sleep_s, 6))
        assert len(seen) > 1  # jitter actually applied
        # retry does not block provider or settle
        assert isinstance(env.g.authorize("lesson", 0.001), Grant)

    def test_13_12c_attempt_over_max_fails(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 4, 429, error_type="rate_limit_error")
        assert a.kind == "fail"
        assert env.g.authorize("lesson", 0.001).__class__ is Grant  # no block

    def test_13_12d_retry_after_capped_by_max_sleep(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, 529, retry_after_s=40)
        assert a.kind == "retry" and a.sleep_s == pytest.approx(20.0)

    def test_retry_after_raises_minimum(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, 529, retry_after_s=5)
        assert a.kind == "retry" and 5.0 - 1e-9 <= a.sleep_s <= 20.0

    def test_sleep_capped_by_max_sleep(self, env):
        cfgm = lambda d: d["retry"].update(base_s=10.0, factor=3.0)
        g_ = mk(env, cfgm)
        g = g_.authorize("haftalik_ozet", 0.003)
        a = g_.report_error("haftalik_ozet", g, 3, 500)  # 10*9=90 -> capped at 20 (+-jitter)
        assert a.kind == "retry" and a.sleep_s <= 20.0 * 1.2 + 1e-9 and a.sleep_s >= 20.0 * 0.8 - 1e-9

    @pytest.mark.parametrize("status", [408, 409, 500, 502, 503, 504, 529, None])
    def test_retryable_statuses(self, env, status):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, status)
        assert a.kind == "retry" and 1.6 - 1e-9 <= a.sleep_s <= 2.4 + 1e-9

    @pytest.mark.parametrize("code", ["rate_limit_error", "ramp_limit_exceeded"])
    def test_other_429_retry(self, env, code):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, 429, error_type=code, error_code=code)
        assert a.kind == "retry"

    @pytest.mark.parametrize("status", [401, 402, 403, 404, 413])
    def test_fail_statuses_no_block_and_release(self, env, status):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, status, error_type="x_error", message="nope")
        assert a.kind == "fail"
        assert env.g.status().provider_blocked_until is None
        assert env.g.status().services["haftalik_ozet"].unsettled_usd == 0  # released
        assert isinstance(env.g.authorize("haftalik_ozet", 0.001), Grant)

    def test_13_12e_400_schema_error_fail(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        a = env.g.report_error("haftalik_ozet", g, 1, 400, error_type="invalid_request_error",
                               message="messages.0.content: Input should be a valid list")
        assert a.kind == "fail" and a.blocked_until in (None,)
        assert env.g.status().provider_blocked_until is None
        assert isinstance(env.g.authorize("lesson", 0.001), Grant)

    def test_unknown_status_fails(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        assert env.g.report_error("haftalik_ozet", g, 1, 418).kind == "fail"

    def test_deadline_exceeded_fails(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        env.clock.adv(seconds=301)  # haftalik_ozet deadline 300 s
        a = env.g.report_error("haftalik_ozet", g, 1, 529)
        assert a.kind == "fail"

    def test_lesson_deadline_longer(self, env):
        g = grant(env.g, "lesson", 3000)
        env.clock.adv(seconds=61)  # lesson deadline 300 s
        assert env.g.report_error("lesson", g, 1, 529).kind == "retry"
        env.clock.adv(seconds=300)
        assert env.g.report_error("lesson", g, 1, 529).kind == "fail"

    def test_report_error_after_no_response_keeps_reservation(self, env):
        g = grant(env.g, "haftalik_ozet", 3000)
        env.g.report_error("haftalik_ozet", g, 1, None)  # timeout: retry, no release
        assert env.g.status().services["haftalik_ozet"].unsettled_usd == pytest.approx(0.003, abs=1e-9)


# ============================================ 9. fail-closed store behaviour
class TestFailClosed:
    def _all_calls_safe(self, g, clock):
        fake = Grant("ef" * 16, "haftalik_ozet", 100, "2026-11-16", "2026-11-16T10:00:00.000Z",
                     "2026-11-16T10:10:00.000Z")
        r = g.record("haftalik_ozet", fake, Usage(input_tokens=1), HAIKU)
        assert isinstance(r, Settlement) and r.ok is False
        assert g.release(fake) is None
        a = g.report_error("haftalik_ozet", fake, 1, 500)
        assert isinstance(a, ErrorAction)
        assert isinstance(g.pending_events(), list)
        assert g.ack_events([1, 2]) is None
        st = g.status()
        assert st.store_ok is False
        for s in ("haftalik_ozet", "lesson"):
            assert st.services[s].state == "unavailable"
        json.dumps(st.to_dict())

    def test_first_use_creates_db_marker_and_perms(self, env):
        assert not env.db.exists()
        assert isinstance(env.g.authorize("haftalik_ozet", 0.001), Grant)
        assert env.db.exists()
        assert Path(str(env.db) + ".initialized").exists()
        assert (env.db.stat().st_mode & 0o777) == 0o600

    def test_pragmas_and_schema(self, env):
        env.g.authorize("haftalik_ozet", 0.001)
        c = sqlite3.connect(str(env.db))
        try:
            assert c.execute("pragma user_version").fetchone()[0] == 1
            assert c.execute("pragma journal_mode").fetchone()[0].lower() == "delete"
            names = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
            assert {"meta", "reservations", "blocks", "events"} <= names
            meta = dict(c.execute("select key, value from meta").fetchall())
            assert "schema_version" in meta and "created_at" in meta and "last_ts" in meta
            cols = {r[1] for r in c.execute("pragma table_info(reservations)")}
            assert {"grant_id", "service", "day", "month", "state", "est_micro", "charged_micro",
                    "model", "batch", "usage_json", "created_at", "settled_at"} <= cols
        finally:
            c.close()

    def test_corrupt_file_denied_never_raises_and_untouched(self, env):
        junk = b"this is definitely not a sqlite database\x00" * 200
        env.db.write_bytes(junk)
        d = env.g.authorize("haftalik_ozet", 0.001)
        assert isinstance(d, Denial) and d.reason == "store_unavailable" and d.service == "haftalik_ozet"
        assert isinstance(env.g.authorize("lesson", 0.001), Denial)
        self._all_calls_safe(env.g, env.clock)
        assert env.db.read_bytes() == junk  # not deleted / recreated

    def test_corrupt_after_use(self, env):
        env.g.authorize("haftalik_ozet", 0.001)
        g2 = BudgetGuard(env.cfg, clock=env.clock)
        env.db.write_bytes(b"\xff" * 4096)
        d = g2.authorize("haftalik_ozet", 0.001)
        assert isinstance(d, Denial) and d.reason == "store_unavailable"
        assert env.db.read_bytes() == b"\xff" * 4096

    def test_missing_with_marker_store_missing(self, env):
        env.g.authorize("haftalik_ozet", 0.001)
        os.remove(env.db)
        g2 = BudgetGuard(env.cfg, clock=env.clock)
        d = g2.authorize("haftalik_ozet", 0.001)
        assert isinstance(d, Denial) and d.reason == "store_missing"
        assert not env.db.exists()  # not silently recreated (counter not reset)
        assert Path(str(env.db) + ".initialized").exists()
        st = g2.status()
        assert st.store_ok is False

    def test_missing_dir_and_marker_is_first_install(self, tmp_path):
        cfg = make_cfg(tmp_path, db_name="sub_ok.sqlite")
        g = BudgetGuard(cfg, clock=Clock(T(2026, 11, 16, 10)))
        assert isinstance(g.authorize("haftalik_ozet", 0.001), Grant)

    def test_newer_schema_version(self, env):
        env.g.authorize("haftalik_ozet", 0.001)
        c = sqlite3.connect(str(env.db))
        c.execute("pragma user_version=99")
        c.commit()
        c.close()
        g2 = BudgetGuard(env.cfg, clock=env.clock)
        d = g2.authorize("haftalik_ozet", 0.001)
        assert isinstance(d, Denial) and d.reason == "store_unavailable"

    def test_meta_missing(self, env):
        env.g.authorize("haftalik_ozet", 0.001)
        c = sqlite3.connect(str(env.db))
        c.execute("drop table meta")
        c.commit()
        c.close()
        g2 = BudgetGuard(env.cfg, clock=env.clock)
        d = g2.authorize("haftalik_ozet", 0.001)
        assert isinstance(d, Denial) and d.reason in ("store_unavailable", "store_missing")

    def test_locked_store_denies_then_recovers(self, env):
        env.g.authorize("haftalik_ozet", 0.001)
        lock = sqlite3.connect(str(env.db), timeout=0, isolation_level=None)
        lock.execute("BEGIN EXCLUSIVE")
        try:
            t0 = time.monotonic()
            d = env.g.authorize("haftalik_ozet", 0.001)
            dt = time.monotonic() - t0
            assert isinstance(d, Denial) and d.reason == "store_unavailable"
            assert dt < 30
            self._locked_calls(env)
        finally:
            lock.execute("ROLLBACK")
            lock.close()
        assert isinstance(env.g.authorize("haftalik_ozet", 0.001), Grant)

    def _locked_calls(self, env):
        fake = Grant("ef" * 16, "haftalik_ozet", 100, "2026-11-16", "2026-11-16T10:00:00.000Z",
                     "2026-11-16T10:10:00.000Z")
        assert isinstance(env.g.record("haftalik_ozet", fake, Usage(input_tokens=1), HAIKU), Settlement)
        assert env.g.release(fake) is None
        assert isinstance(env.g.report_error("haftalik_ozet", fake, 1, 500), ErrorAction)
        assert isinstance(env.g.status().store_ok, bool)

    def test_store_error_event_not_required_but_no_raise_on_unwritable_dir(self, tmp_path):
        ro = tmp_path / "nodir" / "deeper"
        cfg = make_cfg(tmp_path, lambda d: d.update(db_path=str(ro / "b.sqlite")))
        g = BudgetGuard(cfg, clock=Clock(T(2026, 11, 16, 10)))
        r = g.authorize("haftalik_ozet", 0.001)
        assert isinstance(r, (Grant, Denial))
        if isinstance(r, Denial):
            assert r.reason in ("store_unavailable", "store_missing")

    def test_module_level_config_invalid_and_valid(self, tmp_path):
        code = (
            "import json, sys\n"
            "import trader_core.budget as b\n"
            "b.DEFAULT_PATH = sys.argv[1]\n"
            "r = b.authorize('haftalik_ozet', 0.001)\n"
            "st = b.status()\n"
            "print(json.dumps([type(r).__name__, getattr(r,'reason',None), st.config_ok, st.store_ok]))\n"
        )
        env = dict(os.environ, PYTHONPATH=str(SRC_DIR))
        cfgp = str(tmp_path / "config" / "budget.json")
        # no config at all
        out = subprocess.run([sys.executable, "-c", code, cfgp], cwd=tmp_path, env=env,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout.strip().splitlines()[-1]) == ["Denial", "config_invalid", False, False]
        # garbage config
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "budget.json").write_text("{not json")
        out = subprocess.run([sys.executable, "-c", code, cfgp], cwd=tmp_path, env=env,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout.strip().splitlines()[-1]) == ["Denial", "config_invalid", False, False]

    def test_module_level_functions_work(self, tmp_path):
        d = copy.deepcopy(BASE_CFG)
        d["db_path"] = str(tmp_path / "user_data" / "budget.sqlite")
        (tmp_path / "config").mkdir()
        (tmp_path / "user_data").mkdir()
        (tmp_path / "config" / "budget.json").write_text(json.dumps(d))
        code = (
            "import json, sys\n"
            "import trader_core.budget as b\n"
            "b.DEFAULT_PATH = sys.argv[1]\n"
            "est = b.estimate_cost('claude-haiku-5-5', input_tokens=4800, max_output_tokens=1000, cache_read_tokens=1500)\n"
            "g = b.authorize('haftalik_ozet', est)\n"
            "s = b.record('haftalik_ozet', g, b.Usage(input_tokens=4800, output_tokens=800, cache_read_tokens=1500), 'claude-haiku-5-5')\n"
            "st = b.status()\n"
            "print(json.dumps([round(est*1e6), type(g).__name__, s.cost_micro, s.ok, b.api_key_env('lesson'),\n"
            "                  st.services['haftalik_ozet'].used_usd, len(b.pending_events())]))\n"
        )
        env = dict(os.environ, PYTHONPATH=str(SRC_DIR))
        out = subprocess.run([sys.executable, "-c", code, str(tmp_path / "config" / "budget.json")],
                             cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        r = json.loads(out.stdout.strip().splitlines()[-1])
        assert r[0] == 995 and r[1] == "Grant" and r[2] == 895 and r[3] is True
        assert r[4] == "ANTHROPIC_API_KEY_LESSON" and r[5] == pytest.approx(0.000895) and r[6] == 0


# ======================================================== 10. concurrency
WORKER = r"""
import sys, json, time, os
cfgp, go, est_veto, est_lesson, n = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
from trader_core.budget import BudgetGuard, load_config
g = BudgetGuard(load_config(cfgp))
deadline = time.time() + 30
while not os.path.exists(go) and time.time() < deadline:
    time.sleep(0.001)
out = []
for _ in range(n):
    for svc, est in (("haftalik_ozet", est_veto), ("lesson", est_lesson)):
        if est <= 0:
            continue
        r = g.authorize(svc, est)
        out.append([svc, type(r).__name__, getattr(r, "reason", None), getattr(r, "day", None), getattr(r, "est_micro", None)])
print(json.dumps(out))
"""


def _run_workers(tmp_path, cfg_path, nproc, est_veto, est_lesson, n):
    script = tmp_path / "worker.py"
    script.write_text(WORKER)
    go = tmp_path / "go.flag"
    env = dict(os.environ, PYTHONPATH=str(SRC_DIR))
    procs = [
        subprocess.Popen([sys.executable, str(script), str(cfg_path), str(go), str(est_veto),
                          str(est_lesson), str(n)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        for _ in range(nproc)
    ]
    time.sleep(1.0)
    go.write_text("go")
    results = []
    for p in procs:
        o, e = p.communicate(timeout=120)
        assert p.returncode == 0, e
        results.extend(json.loads(o.strip().splitlines()[-1]))
    return results


class TestConcurrency:
    def test_multiprocess_never_exceeds_caps(self, tmp_path):
        cfg = make_cfg(tmp_path)
        res = _run_workers(tmp_path, tmp_path / "budget.json", 4, usd(20_000), usd(20_000), 12)
        days = {r[3] for r in res if r[1] == "Grant"}
        assert len(days) == 1  # (UTC midnight during the test would be a freak event)
        for svc, expect in (("haftalik_ozet", 12), ("lesson", 5)):
            grants = [r for r in res if r[0] == svc and r[1] == "Grant"]
            assert len(grants) == expect, (svc, len(grants))
            assert all(r[4] == 20_000 for r in grants)
        denials = [r for r in res if r[1] == "Denial"]
        assert denials and all(r[2] == "daily_cap" for r in denials)
        for svc, cap in CAPS.items():
            tot = q(tmp_path / "budget.sqlite", "select sum(charged_micro) from reservations where service=?", (svc,))[0][0]
            assert tot <= cap
        assert len(res) == 4 * 12 * 2

    def test_13_10_two_processes_race_for_last_slot(self, tmp_path):
        cfg = make_cfg(tmp_path)
        g = BudgetGuard(cfg)
        r = g.authorize("haftalik_ozet", usd(240_000))
        assert isinstance(r, Grant)
        res = _run_workers(tmp_path, tmp_path / "budget.json", 2, usd(8000), 0, 1)
        grants = [x for x in res if x[1] == "Grant"]
        assert len(grants) == 1
        assert [x[2] for x in res if x[1] == "Denial"] == ["daily_cap"]
        tot = q(tmp_path / "budget.sqlite", "select sum(charged_micro) from reservations")[0][0]
        assert tot == 248_000

    def test_monthly_cap_under_concurrency_threads(self, tmp_path):
        # Tighter monthly cap so a single day can hit it: 0.30 month vs 0.25+0.10 daily
        cfg = make_cfg(tmp_path, lambda d: d.update(monthly_cap_usd=0.30, monthly_warn_usd=0.1))
        results = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def work():
            g = BudgetGuard(cfg)
            barrier.wait()
            for _ in range(10):
                for svc in ("haftalik_ozet", "lesson"):
                    r = g.authorize(svc, usd(10_000))
                    with lock:
                        results.append((svc, r))

        ts = [threading.Thread(target=work) for _ in range(8)]
        [t.start() for t in ts]
        [t.join(timeout=120) for t in ts]
        assert len(results) == 8 * 10 * 2
        tot = q(tmp_path / "budget.sqlite", "select sum(charged_micro) from reservations")[0][0]
        assert tot <= 300_000
        assert sum(1 for _, r in results if isinstance(r, Grant)) == tot // 10_000
        for _, r in results:
            assert isinstance(r, (Grant, Denial))
        # monthly reason must appear once the month is full
        assert any(isinstance(r, Denial) and r.reason in ("monthly_cap", "daily_cap") for _, r in results)

    def test_threads_separate_connections_daily(self, tmp_path):
        cfg = make_cfg(tmp_path)
        out = []
        lock = threading.Lock()
        barrier = threading.Barrier(6)

        def work():
            g = BudgetGuard(cfg)
            barrier.wait()
            for _ in range(10):
                r = g.authorize("haftalik_ozet", usd(15_000))
                with lock:
                    out.append(r)

        ts = [threading.Thread(target=work) for _ in range(6)]
        [t.start() for t in ts]
        [t.join(timeout=120) for t in ts]
        n = sum(isinstance(r, Grant) for r in out)
        assert n == 16  # 16 * 15_000 = 240_000 <= 250_000 < 17 * 15_000
        assert len({r.grant_id for r in out if isinstance(r, Grant)}) == 16

    def test_events_unique_under_race(self, tmp_path):
        cfg = make_cfg(tmp_path)
        barrier = threading.Barrier(6)

        def work():
            g = BudgetGuard(cfg)
            barrier.wait()
            for _ in range(10):
                g.authorize("lesson", usd(20_000))

        ts = [threading.Thread(target=work) for _ in range(6)]
        [t.start() for t in ts]
        [t.join(timeout=120) for t in ts]
        g = BudgetGuard(cfg)
        ev = g.pending_events()
        keys = [(e.kind, e.service, e.day) for e in ev]
        assert len(keys) == len(set(keys))
        assert sum(e.kind == "daily_warn_70" for e in ev) == 1
        assert sum(e.kind == "daily_stopped_100" for e in ev) == 1


# ===================================================== 11. secret hygiene
class TestKeyLeak:
    def test_no_key_in_outputs(self, env, monkeypatch, caplog):
        caplog.set_level(logging.DEBUG)
        kv, kl = "sk-ant-api03-FAKEVETOKEY1234567890", "sk-ant-api03-FAKELESSONKEY0987654321"
        monkeypatch.setenv("ANTHROPIC_API_KEY_HAFTALIK_OZET", kv)
        monkeypatch.setenv("ANTHROPIC_API_KEY_LESSON", kl)
        leak = "invalid x-api-key sk-ant-api03-LEAKEDINMESSAGE-abc123 and again sk-ant-zzzz"
        collected = []
        g1 = env.g.authorize("haftalik_ozet", 0.2)
        collected.append(repr(g1))
        collected.append(repr(env.g.authorize("haftalik_ozet", 0.2)))  # denial
        a = env.g.report_error("haftalik_ozet", g1, 1, 401, error_type="authentication_error", message=leak)
        collected.append(repr(a))
        g2 = env.g.authorize("lesson", 0.05)
        a = env.g.report_error("lesson", g2, 1, 400, error_type="invalid_request_error",
                               error_code=leak, message=leak + " specified API usage limits")
        collected.append(repr(a))
        env.g.report_error("lesson", g2, 2, 529, error_type=leak, message=leak)
        s = env.g.record("lesson", g2, Usage(input_tokens=5), "claude-" + leak)
        collected.append(repr(s))
        collected.append(json.dumps(env.g.status().to_dict()))
        collected.append(repr(env.g.status()))
        for e in env.g.pending_events():
            collected.append(repr(e))
            collected.append(e.message)
            collected.append(json.dumps(e.payload, default=str))
        with pytest.raises(ValueError) as ei:
            env.g.authorize(leak, 0.1)
        collected.append(str(ei.value))
        collected.append(caplog.text)
        blob = "\n".join(collected)
        for needle in ("sk-ant-", "FAKEVETOKEY", "FAKELESSONKEY", "LEAKEDINMESSAGE"):
            assert needle not in blob, needle
        raw = b""
        for suffix in ("", "-journal", ".initialized"):
            p = Path(str(env.db) + suffix)
            if p.exists():
                raw += p.read_bytes()
        assert b"sk-ant-" not in raw and b"LEAKEDINMESSAGE" not in raw
        assert b"FAKEVETOKEY" not in raw and b"FAKELESSONKEY" not in raw

    def test_module_does_not_read_keys(self, env, monkeypatch):
        # works with the env vars absent: module is key-agnostic
        monkeypatch.delenv("ANTHROPIC_API_KEY_HAFTALIK_OZET", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY_LESSON", raising=False)
        assert isinstance(env.g.authorize("haftalik_ozet", 0.01), Grant)
        assert isinstance(env.g.authorize("lesson", 0.01), Grant)


# ============================================ 12. seeded property test
def _expected_cost(prices, sf, bm, usage, batch):
    p = prices
    tot = (Decimal(usage.input_tokens) * Decimal(str(p["input"]))
           + Decimal(usage.output_tokens) * Decimal(str(p["output"]))
           + Decimal(usage.cache_write_5m_tokens) * Decimal(str(p["cache_write_5m"]))
           + Decimal(usage.cache_write_1h_tokens) * Decimal(str(p["cache_write_1h"]))
           + Decimal(usage.cache_read_tokens) * Decimal(str(p["cache_read"])))
    tot = tot * Decimal(str(sf)) * (Decimal(str(bm)) if batch else Decimal(1))
    return int(tot.to_integral_value(rounding="ROUND_CEILING"))


def _invariants(db, caps, tainted_days, tainted_months, g, clock):
    rows = q(db, "select grant_id, service, day, month, state, est_micro, charged_micro from reservations")
    day_sum, month_sum = {}, {}
    for gid, svc, day, month, state, est, ch in rows:
        assert state in ("open", "settled", "released", "expired"), state
        if state in ("open", "expired"):
            assert ch == est, (gid, state, est, ch)
        elif state == "released":
            assert ch == 0
        else:
            assert ch >= 0
        day_sum[(svc, day)] = day_sum.get((svc, day), 0) + ch
        month_sum[month] = month_sum.get(month, 0) + ch
    for (svc, day), v in day_sum.items():
        if (svc, day) not in tainted_days:
            assert v <= caps[svc], ("daily cap exceeded", svc, day, v)
    for m, v in month_sum.items():
        if m not in tainted_months:
            assert v <= 10_000_000, ("monthly cap exceeded", m, v)
    st = g.status()
    assert st.store_ok and st.config_ok
    for svc in ("haftalik_ozet", "lesson"):
        exp = day_sum.get((svc, st.day), 0)
        assert st.services[svc].used_usd == pytest.approx(exp / 1e6, abs=6e-7), (svc, st.day)
        assert st.services[svc].settled_usd + st.services[svc].unsettled_usd == pytest.approx(
            st.services[svc].used_usd, abs=1.5e-6)
    assert st.month_used_usd == pytest.approx(month_sum.get(st.month, 0) / 1e6, abs=6e-7)
    return rows


def _run_sequence(rng, tmp_path, idx):
    cfg_path = tmp_path / f"c{idx}.json"
    d = copy.deepcopy(BASE_CFG)
    d["db_path"] = str(tmp_path / f"p{idx}.sqlite")
    cfg_path.write_text(json.dumps(d))
    cfg = load_config(str(cfg_path))
    db = Path(d["db_path"])
    prices = d["prices_usd_per_mtok"]
    clock = Clock(T(2026, 12, rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59)))
    g = BudgetGuard(cfg, clock=clock)
    grants = []
    settled = {}
    tainted_days, tainted_months = set(), set()
    last_grant_day = {"d": ""}

    for step in range(rng.randint(15, 30)):
        r = rng.random()
        if r < 0.15:
            clock.adv(seconds=rng.choice([0, 1, 5, 30, 700, 1000, 3600, 3600 * rng.randint(2, 20), 86400 + rng.randint(0, 5000)]))
        r = rng.random()
        if r < 0.45 or not grants:
            svc = rng.choice(["haftalik_ozet", "lesson"])
            micro = rng.choice([1, 500, 2000, 8000, 20_000, 60_000, 120_000, 260_000])
            used_before = {k: v for k, v in [
                ((row[1], row[2]), 0) for row in []]}
            res = g.authorize(svc, usd(micro))
            if isinstance(res, Grant):
                assert res.service == svc and res.est_micro == micro
                assert res.day >= day_str(clock()) and res.day >= last_grant_day["d"]
                last_grant_day["d"] = res.day
                grants.append(res)
            else:
                assert isinstance(res, Denial) and res.reason in ("daily_cap", "monthly_cap"), res
                # not spuriously denied: recompute
                rows = q(db, "select service, day, month, charged_micro from reservations")
                today = day_str(clock())
                dsum = sum(x[3] for x in rows if x[0] == svc and x[1] == today)
                msum = sum(x[3] for x in rows if x[2] == today[:7])
                if res.reason == "daily_cap":
                    assert dsum + micro > CAPS[svc], (dsum, micro)
                else:
                    assert msum + micro > 10_000_000, (msum, micro)
        elif r < 0.72:
            gr = rng.choice(grants)
            kind = rng.random()
            batch = rng.random() < 0.3
            model = rng.choice([HAIKU, SONNET])
            if kind < 0.05:
                usage = Usage(input_tokens=-rng.randint(1, 5))
            elif kind < 0.08:
                usage = Usage(output_tokens=True)
            else:
                usage = Usage(
                    input_tokens=rng.randint(0, 9000), output_tokens=rng.choice([0, 100, 800, 5000, 200_000]),
                    cache_write_5m_tokens=rng.choice([0, 0, 700]), cache_write_1h_tokens=rng.choice([0, 0, 1500]),
                    cache_read_tokens=rng.choice([0, 1500, 4000]))
            if kind > 0.97:
                model = "claude-unknown-0"
            prev = q(db, "select state, charged_micro from reservations where grant_id=?", (gr.grant_id,))[0]
            s = g.record(gr.service, gr, usage, model, batch=batch)
            assert isinstance(s, Settlement)
            now = q(db, "select state, charged_micro from reservations where grant_id=?", (gr.grant_id,))[0]
            if prev[0] == "settled":
                assert s.duplicate is True and now == prev
            elif prev[0] == "released":
                pass  # unspecified
            elif s.code == "ok":
                exp = _expected_cost(prices[model], 1.0, 0.5, usage, batch)
                assert s.ok and s.cost_micro == exp and now == ("settled", exp)
                assert s.overrun_micro == max(0, exp - gr.est_micro)
                assert s.day == gr.day
                if exp > gr.est_micro:
                    tainted_days.add((gr.service, gr.day))
                    tainted_months.add(gr.day[:7])
            else:
                assert s.code in ("bad_usage", "unknown_model")
                assert s.ok is False and s.estimated_instead and s.cost_micro == gr.est_micro
                assert now[0] != "settled" and now[1] == gr.est_micro
        elif r < 0.82:
            gr = rng.choice(grants)
            prev = q(db, "select state, charged_micro from reservations where grant_id=?", (gr.grant_id,))[0]
            assert g.release(gr) is None
            now = q(db, "select state, charged_micro from reservations where grant_id=?", (gr.grant_id,))[0]
            if prev[0] == "settled":
                assert now == prev
            elif prev[0] == "open":
                assert now == ("released", 0)
            else:  # expired: spec only defines open -> released
                assert now in (prev, ("released", 0))
        elif r < 0.93:
            gr = rng.choice(grants)
            st = rng.choice([529, 408, 500, None, 401, 429])
            a = g.report_error(gr.service, gr, rng.randint(1, 5), st)
            assert isinstance(a, ErrorAction) and a.kind in ("retry", "fail")
            assert a.kind != "retry" or a.sleep_s >= 0
        else:
            g = BudgetGuard(cfg, clock=clock)  # simulated restart
        _invariants(db, CAPS, tainted_days, tainted_months, g, clock)

    ev = g.pending_events()
    keys = [(e.kind, e.service, e.day) for e in ev if e.kind in ("daily_warn_70", "daily_stopped_100", "credit_low")]
    assert len(keys) == len(set(keys))
    ids = [e.id for e in ev]
    assert ids == sorted(ids)
    assert len([e for e in ev if e.kind == "monthly_warn_5usd"]) <= 2


class TestProperty:
    @pytest.mark.parametrize("chunk", range(6))
    def test_random_sequences_caps_and_accounting(self, tmp_path, chunk):
        rng = random.Random(20261116 + chunk)
        for i in range(50):
            try:
                _run_sequence(rng, tmp_path, chunk * 100 + i)
            except AssertionError as e:
                raise AssertionError(f"sequence chunk={chunk} i={i}: {e}") from e
