"""Mentor incelemesi (docs/motor/09-mentor-inceleme.md) A1, A2, B5, B6 duzeltmeleri."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import ledger as L
from trader_engine.funding import floor_funding_time
from trader_engine.marketdata.feed import _floor_funding_ms, _next_funding_boundary_ms
from trader_engine.types import FundingPoint

from test_engine_03_spec import PAIR, Env as BrokerEnv, T_F, fp, funding_env, mb
from test_engine_04_spec import ENTRY_PAYLOAD
from test_engine_05_spec import BTC, Env, M1, ROOT, T0, UTC

MIN = timedelta(minutes=1)


def _fund_events(env):
    return [e for e in env.events if e.kind == "funding"]


# ------------------------------------------------------------------ A1: funding
def test_funding_point_arrives_late_is_charged_once():
    env = funding_env("buy", 6.369)
    env.points = []                                   # 08:00 adiminda nokta henuz yok
    env.step(mb(T_F))
    env.step(mb(T_F + MIN))
    assert _fund_events(env) == [] and env.b.counters()["funding_missing"] == 0
    env.points = [fp(T_F, 0.0001, 101.0)]             # gec geldi
    w0 = env.b.account().wallet
    env.step(mb(T_F + 2 * MIN))
    assert len(_fund_events(env)) == 1
    assert env.b.account().wallet == pytest.approx(w0 - 0.0643269)
    env.step(mb(T_F + 3 * MIN))
    env.step(mb(T_F + 20 * MIN))
    assert len(_fund_events(env)) == 1 and env.b.counters()["funding_missing"] == 0


def test_funding_never_arrives_records_missing_after_max_wait_once():
    env = funding_env("buy", 6.369)
    env.points = []
    env.step(mb(T_F))
    env.step(mb(T_F + 14 * MIN))
    assert env.b.counters()["funding_missing"] == 0   # bekleme siniri (15 dk) dolmadi
    env.step(mb(T_F + 15 * MIN))
    assert env.b.counters()["funding_missing"] == 1
    for k in range(16, 30):
        env.step(mb(T_F + k * MIN))
    assert env.b.counters()["funding_missing"] == 1 and _fund_events(env) == []


def test_funding_ms_past_hour_timestamp_is_charged():
    env = funding_env("buy", 6.369)
    env.points = [FundingPoint(PAIR, T_F + timedelta(milliseconds=3), 0.0001, 101.0)]
    w0 = env.b.account().wallet
    env.step(mb(T_F + MIN))                            # ham ts (T_F+3ms) sinirin icinde ama izgara disi
    (fe,) = _fund_events(env)
    assert fe.ts == T_F and fe.funding_paid == pytest.approx(0.0643269)
    assert env.b.account().wallet == pytest.approx(w0 - 0.0643269)


def test_floor_funding_helpers():
    t = datetime(2026, 12, 1, 8, 0, 0, 3000, tzinfo=timezone.utc)
    assert floor_funding_time(t) == T_F
    assert floor_funding_time(datetime(2026, 12, 1, 15, 59, tzinfo=timezone.utc)) == datetime(2026, 12, 1, 8, tzinfo=timezone.utc)
    ms = int(T_F.timestamp() * 1000)
    assert _floor_funding_ms(ms + 3) == ms
    assert _next_funding_boundary_ms(ms + 3) == ms + 3_600_000       # saat sinirlari: 4s/1s kayitlar da zamaninda cekilir
    assert _next_funding_boundary_ms(ms - 1) == ms


# ------------------------------------------------------------------ A2: outbox
def _stuck(env):
    def boom(*a, **k):
        raise L.LedgerWriteError("gecersiz satir")
    env.ledger.record_trade_entry = boom
    with env.state.tx():
        env.state.outbox_add("entry", 1, ENTRY_PAYLOAD)


def test_outbox_stuck_blocks_entries_and_stays_blocked_after_close(tmp_path):
    env = Env(tmp_path)
    env.start()
    try:
        p = env.open_pos(BTC, T0)
        _stuck(env)
        env.engine._post_commit()
        assert env.state.kv_get("entries_blocked_reason") == "outbox_stuck"
        assert env.engine.counters()["outbox_failed"] == 1
        env.status.write(env.engine, force=True)
        st = json.loads(Path(env.cfg.status_path).read_text())
        assert st["entries_open"] is False and st["entries_blocked_reason"] == "outbox_stuck"
        assert st["counters"]["outbox_failed"] >= 1
        # islem kapaninca girisler yeniden ACILMAZ
        env.step(T0 + M1, pairs=(BTC,), price=98.5, hi=99.0, lo=97.5)
        assert env.pos(BTC) is None or env.pos(BTC).status == "closed"
        assert env.state.kv_get("entries_blocked_reason") == "outbox_stuck"
        env.status.write(env.engine, force=True)
        st = json.loads(Path(env.cfg.status_path).read_text())
        assert st["entries_open"] is False and st["entries_blocked_reason"] == "outbox_stuck"
        assert p is not None
    finally:
        env.close()


def test_outbox_stuck_clears_when_resolved(tmp_path):
    env = Env(tmp_path)
    env.start()
    try:
        _stuck(env)
        env.engine._post_commit()
        assert env.state.kv_get("entries_blocked_reason") == "outbox_stuck"
        env.ledger.record_trade_entry = lambda *a, **k: None   # cozuldu: yazim basarili
        env.engine._post_commit()
        assert env.state.outbox_pending() == []
        assert env.state.kv_get("entries_blocked_reason") is None
    finally:
        env.close()


# ------------------------------------------------------------------ B6: gun basi ozsermaye
def test_day_start_stores_equity_with_unrealized_pnl_at_midnight(tmp_path):
    env = Env(tmp_path)
    env.start()
    try:
        env.open_pos(BTC, T0)
        nxt = datetime(2026, 12, 2, 0, 0, tzinfo=UTC)
        env.step(nxt - M1, pairs=(BTC,), price=99.0, hi=99.2, lo=98.8)   # acik pozisyon zarar yaziyor (stop 98 icinde)
        acct = env.broker.account()
        assert acct.equity < acct.wallet - 1e-6
        env.step(nxt, pairs=(BTC,), price=99.0, hi=99.2, lo=98.8)
        ds = env.state.kv_get("day_start:2026-12-02")
        eq = env.broker.account().equity
        assert ds == pytest.approx(eq, abs=1.0) and ds < env.broker.account().wallet - 1e-6
        assert env.engine.status_fields()["day_start_equity"] == ds
    finally:
        env.close()


# ------------------------------------------------------------------ B5: 0.005
def test_shipped_base_config_uses_half_percent_and_sizing_follows(tmp_path):
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    assert raw["target_trade_risk"] == 0.005
    env = Env(tmp_path, target_trade_risk=raw["target_trade_risk"])
    try:
        assert env.cfg.target_trade_risk == 0.005 and env.cfg.risk_config.target_trade_risk == 0.005
        env.start()
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()[0]
        assert d.final_action == "entered" and d.size_risk_amount <= 0.005 * 1000.0 * 1.001
    finally:
        env.close()
