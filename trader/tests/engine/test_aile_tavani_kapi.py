"""25.11 sadelestirme: kol/aile basina acik pozisyon tavani YOK; ayni ailenin acik pozisyonu ne olursa olsun giris kapisi tavan reddi uretmez
(EntryGate.decide, kagit ve canli ayar degerleriyle). Hesap/kume/korelasyon tavanlari bu testin konusu degil."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import ledger as L
from trader_engine.clock import SimClock
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate, NoVeto
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame
from trader_engine.types import SymbolRules

from test_engine_05_impl_smoke import T0, _params, _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TUTULAN = ["DOGE/USDT", "ADA/USDT", "TRX/USDT", "LINK/USDT", "BCH/USDT", "XLM/USDT"]   # kripto_diger (tavan 9): kume dolmaz
SETUPLAR = ["MF1-YUTAN", "MF1-PINBAR", "MF1-DISBAR", "MF1-DELICI", "MF1-YILDIZ", "MF1-ICBAR"]   # her kurulum x tf tavani (3) asilmaz


def _kur(tmp_path, env, n_mf1):
    cfg = load_cli_config(ROOT / "config", "learner", env)
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", 1000.0)
    acik = [SimpleNamespace(pair=p, setup=s, trigger_tf="1h", side=("long" if i % 2 else "short"), trade_id=i + 1, risk_amount=2.0, margin=20.0, leverage=3)
            for i, (p, s) in enumerate(zip(TUTULAN[:n_mf1], SETUPLAR))]
    state.open_positions = lambda: acik   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(cfg, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    return cfg, g, led, state


def _go(g, row):
    fr = SignalFrame(pair=row.pair, status="ok", detail=None, last=row, table=None, trigger_bar=(110.0, 99.0, 5.0))
    return g.decide(fr, T0, g.pre(T0, "1h", True, "1h"), 1)


@pytest.mark.parametrize("env", ["paper", "live"])
def test_ayni_ailede_alti_acik_pozisyon_varken_giris_reddedilmez(tmp_path, env):
    cfg, g, led, state = _kur(tmp_path, env, 6)
    try:
        assert not hasattr(cfg, "arm_family_max_positions") and not hasattr(cfg, "arm_max_positions")
        ok = _go(g, _row(pair="AVAX/USDT", setup="MF1-ZZZ", arm_id="MF1-ZZZ@1h", tf="1h"))
        assert ok.action == "enter", (ok.code, ok.event.veto_reason if ok.event else None)
    finally:
        state.close()
        led.close()
