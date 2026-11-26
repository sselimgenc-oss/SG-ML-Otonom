import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import ledger
from trader_engine import bars, config, errors, numeric, types
from trader_engine.clock import SimClock, SystemClock

ROOT = Path(__file__).resolve().parents[1]
U = timezone.utc


def dt(*a):
    return datetime(*a, tzinfo=U)


def test_pairs():
    assert types.canon_pair(" btc/usdt:usdt ") == "BTC/USDT"
    assert types.pair_symbol("BTC/USDT") == "BTCUSDT"
    assert types.pair_stem("BTC/USDT") == "BTC_USDT_USDT"
    with pytest.raises(ValueError):
        types.canon_pair("BTCUSDT")
    assert types.order_side_for("long", "entry") == "buy"
    assert types.order_side_for("long", "stop") == "sell"
    assert types.order_side_for("short", "exit") == "buy"


def test_exit_reasons():
    from typing import get_args
    assert get_args(types.ExitReason) == tuple(ledger._EXIT_REASONS)


def test_bars():
    assert bars.floor_tf(dt(2026, 12, 1, 9, 17, 30), "4h") == dt(2026, 12, 1, 8)
    assert bars.floor_tf(dt(2026, 12, 1, 9, 17, 30, 500000), "1h") == dt(2026, 12, 1, 9)
    assert bars.is_tf_close(dt(2026, 12, 1, 12), "4h")
    assert bars.closing_tfs(dt(2026, 12, 1, 12)) == ["15m", "1h", "4h"]
    assert bars.closing_tfs(dt(2026, 12, 1, 13)) == ["15m", "1h"]
    assert bars.closing_tfs(dt(2026, 12, 1, 13, 15)) == ["15m"]
    assert bars.closing_tfs(dt(2026, 12, 1, 13, 1)) == []
    assert bars.last_closed_open(dt(2026, 12, 1, 12), "4h") == dt(2026, 12, 1, 8)
    assert bars.last_closed_open(dt(2026, 12, 1, 11, 59, 59, 999000), "4h") == dt(2026, 12, 1, 4)
    assert bars.funding_times(dt(2026, 12, 1, 7, 59), dt(2026, 12, 1, 16)) == [
        dt(2026, 12, 1, 8), dt(2026, 12, 1, 16)]
    assert bars.from_ms(bars.to_ms(dt(2026, 1, 1, 0, 0, 1))) == dt(2026, 1, 1, 0, 0, 1)
    assert list(bars.expected_opens(dt(2026, 1, 1, 0, 10), dt(2026, 1, 1, 1, 0), "15m")) == [
        dt(2026, 1, 1, 0, 15), dt(2026, 1, 1, 0, 30), dt(2026, 1, 1, 0, 45)]
    with pytest.raises(ValueError):
        bars.floor_tf(datetime(2026, 1, 1), "1h")
    with pytest.raises(ValueError):
        bars.tf_delta("5m")


def _mins(n, start=dt(2026, 1, 1, 10)):
    return [types.MinuteBar("BTC/USDT", start + timedelta(minutes=i), 60, 10 + i, 20 + i, 5 + i,
                            11 + i, None, None, None, None, 1.0) for i in range(n)]


def test_aggregate():
    b = bars.aggregate_minutes(_mins(60), "1h")
    assert (b.o, b.h, b.l, b.c, b.v) == (10, 79, 5, 70, 60.0)
    assert b.close_ts == dt(2026, 1, 1, 11)
    with pytest.raises(errors.DataError):
        bars.aggregate_minutes(_mins(59), "1h")
    with pytest.raises(errors.DataError):
        bars.aggregate_minutes(_mins(60), "1h", "mark")


def test_numeric():
    assert numeric.round_tight(97.951, "long", 0.01) == 97.96
    assert numeric.round_tight(102.049, "short", 0.01) == 102.04
    assert numeric.round_adverse(100.02, "buy", 0.01) == 100.02
    assert numeric.round_adverse(97.951, "sell", 0.01) == 97.95
    assert numeric.floor_step(6.3694, 0.001) == 6.369
    assert numeric.is_multiple(6.369, 0.001)
    assert numeric.floor_step(0.0, 0.1) == 0.0
    for bad in ((-1.0, 0.1), (1.0, 0), (float("nan"), 0.1)):
        with pytest.raises(ValueError):
            numeric.floor_step(*bad)


def test_clock():
    c = SimClock(dt(2026, 1, 1))
    c.advance(5)
    c.sleep(5)
    assert c.now() == dt(2026, 1, 1, 0, 0, 10)
    c.set_time(c.now())
    with pytest.raises(errors.ClockError):
        c.set_time(dt(2026, 1, 1))
    with pytest.raises(errors.ClockError):
        c.advance(-1)
    with pytest.raises(ValueError):
        c.set_time(datetime(2030, 1, 1))
    with pytest.raises(ValueError):
        SimClock(datetime(2030, 1, 1))
    assert SystemClock().now().tzinfo is not None


def test_config():
    cfg = config.load_engine_config(ROOT / "config/engine.base.json", ROOT / "config/engine.learner.json")
    assert len(cfg.pairs) == 5 and cfg.ledger_path == "var/learner/ledger.sqlite"
    assert not hasattr(cfg, "start_delay_s") and cfg.state_path == "var/learner/state.sqlite"
    assert not (ROOT / "config/engine.twin.json").exists()      # DD-12: ikiz kaldirildi
    with pytest.raises(errors.ConfigError):
        config.load_engine_config(ROOT / "config/engine.base.json")  # bot eksik
    with pytest.raises(errors.ConfigError, match="live blogu"):  # 11 B2: faz_b reddi kalkti
        config.apply_overrides(cfg, mode="live")
    with pytest.raises(errors.ConfigError):
        config.apply_overrides(cfg, cost={"fill_model": "legacy_compat"})
    with pytest.raises(errors.ConfigError):
        config.apply_overrides(cfg, max_trade_risk=0.03)
    # 23.11 kullanici karari: canli = kagit; 24.11: veto_mode anahtari silindi
    with pytest.raises(errors.ConfigError):
        config.apply_overrides(cfg, veto_mode="off")
    with pytest.raises(errors.ConfigError, match="live blogu"):
        config.apply_overrides(cfg, mode="live")
    ok = config.apply_overrides(cfg, mode="backtest",
                                cost={"fill_model": "legacy_compat", "trigger_source": "last",
                                      "granularity": "15m"})
    assert ok.cost.fill_model == "legacy_compat"
    with pytest.raises(errors.ConfigError):
        config.apply_overrides(cfg, wallet_start=True)


def test_light_imports():
    code = ("import sys, trader_engine.types, trader_engine.numeric, trader_engine.clock, "
            "trader_engine.bars, trader_engine.errors, trader_engine.config;"
            "bad=[m for m in ('pandas','numpy','requests') if m in sys.modules];"
            "sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src")},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
