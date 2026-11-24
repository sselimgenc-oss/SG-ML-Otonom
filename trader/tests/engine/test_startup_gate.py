"""Paper acilis kapisi (10/10 ya da hicbiri): kural + taze 1m last/mark; sinirli bekleme; EngineExit(7).
Gercek MarketStore/StoreSource + SimClock; ag yok."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_engine.bars import to_ms
from trader_engine.clock import SimClock
from trader_engine.config import load_engine_config
from trader_engine.engine import EXIT_STARTUP_GATE, EngineExit, build_engine
from trader_engine.exchange.rules import extract_all_rules, spec_to_json
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar

REAL_STARTUP_GATE = True       # tests/conftest.py: bu modulde kapi gercekten calisir

ROOT = Path(__file__).resolve().parents[2]
FIXT = Path(__file__).parent / "fixtures" / "binance" / "exchange_info_sample.json"
NOW = datetime(2026, 12, 1, 9, 30, 20, tzinfo=timezone.utc)
PAIRS = ("BTC/USDT", "ETH/USDT")


def _write_rules(store, pairs):
    info = json.loads(FIXT.read_text())
    res = extract_all_rules(info, [p.replace("/", "") for p in pairs])
    for p in pairs:
        store.put_rules(p, spec_to_json(res[p.replace("/", "")]), to_ms(NOW))


def _write_minutes(store, pair, *, last_open, n=4, mark=True):
    for i in range(n):
        t = last_open - timedelta(minutes=i)
        store.put_bars([Bar(pair, "last", "1m", t, 100, 101, 99, 100.5, 1.0)], now_ms=to_ms(NOW))
        if mark:
            store.put_bars([Bar(pair, "mark", "1m", t, 100, 101, 99, 100.5, 0.0)], now_ms=to_ms(NOW))


def _engine(tmp_path, *, rules=PAIRS, last_open=None, mark_for=PAIRS, data_for=PAIRS, wait=60.0):
    last_open = last_open or (NOW - timedelta(minutes=1)).replace(second=0)
    store = MarketStore(tmp_path / "market.sqlite")
    _write_rules(store, rules)
    for p in data_for:
        _write_minutes(store, p, last_open=last_open, mark=p in mark_for)
    store.close()
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(pairs=list(PAIRS), var_dir=str(tmp_path / "var"), market_db=str(tmp_path / "market.sqlite"),
               history_dir=str(tmp_path / "hist"),
               kill_file=str(tmp_path / "KILL"), startup_wait_s=wait, bot="learner")
    b = tmp_path / "engine.json"
    b.write_text(json.dumps(raw))
    cfg = load_engine_config(b)
    clock = SimClock(NOW)
    return build_engine(cfg, clock=clock), clock


def test_gate_all_good_passes_and_counters_zero(tmp_path):
    eng, clock = _engine(tmp_path)
    eng._startup_gate()
    assert (clock.now() - NOW).total_seconds() == 0
    c = eng.status_fields()["counters"]
    assert c["rules_missing"] == 0 and c["data_stale"] == 0
    eng.status.write(eng, force=True)                                  # status.json'da acikca bulunur
    st = json.loads(Path(eng.cfg.status_path).read_text())
    assert st["counters"]["rules_missing"] == 0 and st["counters"]["data_stale"] == 0


def test_gate_one_pair_missing_rules_exits_after_bounded_wait(tmp_path, caplog):
    eng, clock = _engine(tmp_path, rules=("BTC/USDT",), wait=45.0)
    with caplog.at_level(logging.CRITICAL), pytest.raises(EngineExit) as ei:
        eng.start()
    assert ei.value.code == EXIT_STARTUP_GATE != 0
    crit = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(crit) == 1 and "ETH/USDT" in crit[0].getMessage() and "kural eksik" in crit[0].getMessage()
    assert 45 <= (clock.now() - NOW).total_seconds() < 45 + 20          # bekleme sinirli (config), sonsuz degil
    assert eng.status_fields()["counters"]["rules_missing"] == 1


def test_gate_stale_data_exits(tmp_path):
    eng, clock = _engine(tmp_path, last_open=NOW - timedelta(hours=2), wait=10.0)
    with pytest.raises(EngineExit) as ei:
        eng.start()
    assert ei.value.code == EXIT_STARTUP_GATE and "veri bayat" in str(ei.value)
    assert eng.status_fields()["counters"]["data_stale"] == 2


def test_gate_missing_mark_for_one_pair_counts_as_stale(tmp_path):
    eng, _ = _engine(tmp_path, mark_for=("BTC/USDT",), wait=0.0)
    with pytest.raises(EngineExit) as ei:
        eng.start()
    assert "ETH/USDT" in str(ei.value) and eng.status_fields()["counters"]["data_stale"] == 1


def test_gate_no_data_for_one_pair_exits(tmp_path):
    eng, _ = _engine(tmp_path, data_for=("BTC/USDT",), wait=0.0)
    with pytest.raises(EngineExit):
        eng.start()


def test_gate_waits_then_passes_when_feed_catches_up(tmp_path):
    eng, clock = _engine(tmp_path, rules=("BTC/USDT",), wait=120.0)
    calls = {"n": 0}
    real_sleep = clock.sleep

    def sleep(s):                       # feed 30 sn sonra ETH kuralini yazar
        real_sleep(s)
        calls["n"] += 1
        if calls["n"] == 2:
            st = MarketStore(tmp_path / "market.sqlite")
            _write_rules(st, ("ETH/USDT",))
            st.close()
    clock.sleep = sleep
    eng._startup_gate()                 # EngineExit yok
    assert calls["n"] == 2
    assert eng.status_fields()["counters"]["rules_missing"] == 0


def test_gate_full_start_ok_when_all_good(tmp_path):
    eng, _ = _engine(tmp_path)
    rep = eng.start()                   # EngineExit yok: motor tam baslar
    assert rep.reconcile.ok
    assert eng.status_fields()["counters"]["rules_missing"] == 0


def test_gate_is_not_applied_in_backtest_mode(tmp_path):
    eng, clock = _engine(tmp_path, rules=())
    eng.cfg = eng.cfg.__class__(**{**eng.cfg.__dict__, "mode": "backtest"})
    called = []
    eng._startup_gate = lambda: called.append(1)
    try:
        eng.start()
    except Exception:  # noqa: BLE001
        pass
    assert not called
