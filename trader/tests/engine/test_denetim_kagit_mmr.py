"""24.11 denetim: kagit broker tasfiye MMR'ini giris kapisiyla AYNI kaynaktan (varlik sinifi) alir."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_core import risk as K
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import CostModel
from trader_engine.types import MinuteBar, OrderRequest, SymbolRules

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def _rules(p):
    return SymbolRules(pair=p, symbol=p.replace("/", ""), tick=0.01, step=0.001, min_qty=0.001, max_qty=1000.0, min_notional=5.0)


def _liq(mmr_fn, pair):
    b = PaperBroker(PaperConfig(cost=CostModel(), mmr=0.004, mmr_fn=mmr_fn), _rules, lambda p, a, z: [], SimClock(T0), None)
    b.prepare(pair, 3)
    b.market_order(OrderRequest(client_id="e1", pair=pair, role="entry", order_side="buy", qty=1.0, trigger_price=None,
                                reduce_only=False, leverage=3))
    bar = MinuteBar(pair=pair, open_ts=T0, step_s=60, last_o=100.0, last_h=100.0, last_l=100.0, last_c=100.0,
                    mark_o=100.0, mark_h=100.0, mark_l=100.0, mark_c=100.0)
    b.advance({pair: bar}, "fills")
    return b._pos[pair].liq_price


def test_broker_mmr_fn_sinifa_gore_tasfiye_fiyati():
    sabit = _liq(None, "TSLA/USDT")
    sinif = _liq(lambda p: K.sinif_mmr("hisse", 0.004), "TSLA/USDT")
    assert sinif > sabit                                   # hisse %2 MMR: long tasfiye fiyati girise daha yakin
    assert sinif / sabit == pytest.approx((1 - 1 / 3 + 0.02) / (1 - 1 / 3 + 0.004))


def test_motor_kagit_brokeri_kapiyla_ayni_sinif_mmr(tmp_path):
    import test_engine_live_spec as LS
    from trader_engine.config import apply_overrides, load_cli_config
    from trader_engine.engine import build_engine
    cfg = load_cli_config(ROOT / "config", "learner", "paper")
    cfg = apply_overrides(cfg, var_dir=str(tmp_path), kill_file=str(tmp_path / "KILL"), pause_file=str(tmp_path / "PAUSE"))
    _, _, view = LS._injected(tmp_path, LS.make_live_cfg(Path(tmp_path)))
    eng = build_engine(cfg, clock=SimClock(T0), view=view, env={})
    try:
        fn = eng.broker._cfg.mmr_fn
        rc = cfg.risk_config
        assert fn("BTC/USDT") == K.sinif_mmr("kripto", rc.maint_margin_rate) == 0.005
        assert fn("TSLA/USDT") == K.sinif_mmr("hisse", rc.maint_margin_rate) == 0.02
    finally:
        eng.state.close()
        eng.ledger.close()
