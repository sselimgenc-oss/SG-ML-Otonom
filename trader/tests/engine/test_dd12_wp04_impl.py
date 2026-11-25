"""DD-12 WP-04 uygulayici duman testleri (arm_guard + paper kapilari)."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import ledger as L
from trader_engine import arm_guard as AG
from trader_engine.clock import SimClock
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate, NoVeto
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame
from trader_engine.types import SymbolRules

from test_engine_05_impl_smoke import H, T0, _params, _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
# 23.11 kullanici karari: asama B esikleri. Bu dosya sabit kume tavanlarini (cluster_cap) olcer; korelasyon grubu (ayri kural,
# test_asama_b_esikleri.py) burada kapali tutulur.
CFG = dataclasses.replace(load_cli_config(ROOT / "config", "learner", "paper"), korelasyon={}, toplam_buyukluk_kat=None)   # sahte pozisyonlarda nominal yok


def u(*a):
    return datetime(*a, tzinfo=UTC)


def test_session_tag_equity():
    c = AG.CLASS_EQUITY
    assert AG.session_tag(c, u(2026, 12, 5, 15, 0)) == "weekend"             # Cts
    assert AG.session_tag(c, u(2026, 12, 7, 14, 29)) == "closed"             # Pzt 09:29 NY (kis, UTC-5)
    assert AG.session_tag(c, u(2026, 12, 7, 14, 30)) == "open"
    assert AG.session_tag(c, u(2026, 12, 7, 21, 0)) == "closed"              # 16:00 NY
    assert AG.session_tag(c, u(2026, 7, 6, 13, 29)) == "closed"              # yaz (UTC-4)
    assert AG.session_tag(c, u(2026, 7, 6, 13, 30)) == "open"


def test_session_tag_commodity_crypto():
    c = AG.CLASS_COMMODITY
    assert AG.session_tag(c, u(2026, 12, 4, 20, 59)) == "open"
    assert AG.session_tag(c, u(2026, 12, 4, 21, 0)) == "weekend"
    assert AG.session_tag(c, u(2026, 12, 6, 22, 59)) == "weekend"
    assert AG.session_tag(c, u(2026, 12, 6, 23, 0)) == "open"
    assert AG.session_tag(AG.CLASS_CRYPTO, u(2026, 12, 5, 12, 0)) == "open"


def test_flat_bar_and_classes():
    assert AG.is_flat_bar(10, 9, 0) and AG.is_flat_bar(10, 10, 5) and not AG.is_flat_bar(10, 9, 1)
    assert not AG.is_flat_bar(None, None, None)
    assert AG.asset_class("NVDA/USDT", CFG.clusters) == "hisse"
    assert AG.asset_class("XAU/USDT", CFG.clusters) == "emtia"
    assert AG.asset_class("BTC/USDT", CFG.clusters) == "kripto"
    assert AG.clusters_of("NVDA/USDT", CFG.clusters) == ["hisse", "hisse_teknoloji"]


def test_cluster_caps_multi_membership():
    cl = CFG.clusters
    tech = ["NVDA/USDT", "MSFT/USDT", "AAPL/USDT", "AMZN/USDT", "META/USDT"]
    assert AG.full_cluster("GOOGL/USDT", tech, cl) == "hisse_teknoloji"
    assert AG.full_cluster("JPM/USDT", tech, cl) is None                      # teknoloji disi hisse girer
    eight = tech + ["JPM/USDT", "WMT/USDT", "HD/USDT"]
    assert AG.full_cluster("LLY/USDT", eight, cl) == "hisse"
    assert AG.account_full(24, 24) and not AG.account_full(23, 24) and not AG.account_full(99, None)


@pytest.fixture
def env(tmp_path):
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", 1000.0)
    held: list[str] = []
    state.open_positions = lambda: [SimpleNamespace(pair=p, side='long', risk_amount=0.01, margin=0.1) for p in held]   # type: ignore[method-assign]
    cfg = CFG
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(cfg, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    yield SimpleNamespace(g=g, held=held, led=led, state=state)
    state.close()
    led.close()


def _go(e, pair="BTC/USDT", bar=(110.0, 99.0, 5.0)):
    fr = SignalFrame(pair=pair, status="ok", detail=None, last=_row(pair=pair), table=None, trigger_bar=bar)
    pre = e.g.pre(T0, "1h", True, "1h")
    return e.g.decide(fr, T0, pre, 1)


def test_gate_paper_rows(env):
    out = _go(env)
    assert out.action == "enter" and out.event.session_tag == "open" and out.event.veto_status == "not_evaluated"
    out = _go(env, "NVDA/USDT")
    assert out.event.session_tag == "closed" and out.action == "enter"       # seans giris engellemez
    out = _go(env, bar=(100.0, 100.0, 5.0))
    assert (out.code, out.event.skip_reason, out.event.veto_status) == ("flat_bar", "flat_bar", "not_evaluated")
    assert _go(env, bar=(110.0, 99.0, 0.0)).code == "flat_bar"
    env.g.session_off = {"hisse": {"closed"}}
    assert _go(env, "NVDA/USDT").code == "session_closed"
    assert _go(env, "BTC/USDT").action == "enter"
    env.g.session_off = {"hisse": {"weekend"}}
    assert _go(env, "NVDA/USDT").action == "enter"                            # kapatilmamis seansta ret yok
    env.held[:] = ["NVDA/USDT", "MSFT/USDT", "AAPL/USDT", "AMZN/USDT", "META/USDT"]
    o = _go(env, "GOOGL/USDT")
    assert (o.code, o.event.skip_reason, o.event.veto_status) == ("cluster_cap", "cluster_cap", "not_evaluated")
    assert _go(env, "JPM/USDT").action == "enter"
    env.held[:] = [f"X{i}" for i in range(36)]   # 24.11 kullanici karari: max_positions 24 -> 36 (kagit = canli)
    o = _go(env, "XRP/USDT")
    assert o.code == "max_positions" and o.event.skip_reason == "max_positions"
    env.led.record_decision(o.event)                                          # defter CHECK'i kabul eder
