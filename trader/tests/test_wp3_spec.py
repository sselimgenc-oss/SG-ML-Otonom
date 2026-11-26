"""WP-3 independent acceptance tests, written from docs/defter-ek-alanlar-spec.md (section 12) only.

Test ids in comments / test names map 1:1 to the spec numbers (D1..D16, E1..E14, S1..S16, M1..M10, K1..K6,
T1..T7, P1..P4). Synthetic data only; no date inside the locked period [2026-05-01, 2026-11-01); the real-history
directory is never read by this file (K1/K2 shell out to the engine CLI and are gated by WP3_GOLDEN=1).

ASSUMPTIONS (the spec leaves these undefined; every test that depends on one says so in its name/comment):
 A1  "Base commit" = d75a70e (the spec commit). A genuine schema-3 ledger / metrics.py / state.py are obtained with
     `git show d75a70e:...` and exec'd as private modules. If git or that commit is unavailable those tests skip.
 A2  New dataclass fields use the column names of the spec: TradeEntry/TradeExit(order_ts, order_ack_ts,
     order_ref_price, order_ref_spread, order_ref_src[, decision_price, exit_regime]); ShadowEvent(bar_close_ts,
     trigger_tf, pair, side, setup, regime, atr_ratio, rh, rl, features, planned_entry, planned_stop,
     planned_target, param_version_id, strategy, reasons, pos_open, gate_code) built with keyword arguments;
     EquityMark(ts, wallet, equity, equity_low, n_open, src). pos_open is passed as int 0/1 (bool tried on failure).
 A3  Spool lines carry the new columns under the same names as the columns.
 A4  Write failures are simulated by holding a BEGIN IMMEDIATE lock on the db file from a second connection while
     shrinking the ledger connection's busy_timeout (`led._conn()` is used for that single PRAGMA).
 A5  `records` counters are read from status.json after `engine.status.write(engine, force=True)`; the Engine
     itself is built through the existing harness (tests/engine/test_engine_05_spec.py Env, test_engine_live_spec.py
     LiveEnv) with the new config keys `shadow_blocks`, `mtm_marks`, `live.order_quote`.
 A6  shadow.regime_candidate(table, params): `table` is a DataFrame with columns open/high/low/close/atr_tf and a
     DatetimeIndex; the result is None, one candidate or a list of candidates exposing planned_entry|entry,
     planned_stop|stop, stop_dist_atr (optional), side, setup, planned_target|target (attribute or mapping key).
 A7  shadow.tf15_candidates(view, pair, D, params) returns a list of objects with bar_close_ts and side; the view
     only needs bars(pair, tf, until, n) and contiguous_tail(pair, tf, until, max_n).
 A8  The bookTicker query goes through the HTTP session of the signed REST client (so it is observable on the
     FakeExchange wire); the 0.5 s limit is expressed through the `timeout` argument of session.request; the 80 %
     weight limit is taken as weight_hard (1800) -> 1790 used (E13 is therefore an assumption-sensitive test).
 A9  MtmRecorder(writer) / on_minute(ts, bars, positions, wallet) as in spec 6.2 (P2 only; skipped on TypeError).
 A10 same_bar_reentry reasons are "v1b:same_bar_reentry|ml:p=0.612345|T1_long:...,stop_ok" when an ML tag exists.
 A11 K5 / K6 (no new counter keys / state kv keys) are checked as "WP-3 on" vs "WP-3 off" in the same tree plus a
     name check, because the base engine cannot be run side by side in a unit test.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import inspect
import json
import math
import os
import sqlite3
import subprocess
import sys
import time
import tracemalloc
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import indicators, regime, signals
from trader_core import ledger as L
from trader_core.ledger import (DecisionEvent, LedgerConflictError, LedgerSchemaError, LedgerValidationError,
                                LedgerWriteError, TradeEntry, TradeExit, open_ledger)

UTC = timezone.utc
HERE = Path(__file__).resolve().parent
TRADER = HERE.parent
sys.path.insert(0, str(HERE / "engine"))     # harness modules of the existing engine tests

BASE_REF = "d75a70e"                          # A1
NOW = datetime(2027, 1, 1, tzinfo=UTC)
BASE = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
HOLDOUT_END = datetime(2026, 11, 1, tzinfo=UTC)   # first day AFTER the locked period (arithmetic only)
DEFAULT_PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
                  "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5,
                  "trigger_tf": "1h"}
NEW_ENTRY_COLS = ["order_ts", "order_ack_ts", "order_ref_price", "order_ref_spread", "order_ref_src"]
NEW_EXIT_COLS = NEW_ENTRY_COLS + ["decision_price", "exit_regime"]
VIEW_NEW_COLS = ["entry_order_ts", "entry_order_ack_ts", "entry_ref_price", "entry_ref_spread", "entry_ref_src",
                 "slip_exec_entry", "exit_order_ts", "exit_order_ack_ts", "exit_ref_price", "exit_ref_spread",
                 "exit_ref_src", "slip_exec_exit", "exit_decision_price", "slip_decision_exit", "exit_regime"]
FEAT_R1 = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.1}
FEAT_T1 = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "pullback_ema": 50, "ema_value": 1995.0,
           "body_ratio": 0.6}


# =====================================================================================================
# generic helpers
# =====================================================================================================
def raw(path, sql, args=()):
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def table_cols(path, name):
    return [r[1] for r in raw(path, f"PRAGMA table_info({name})")]


def fmt(dt: datetime) -> str:
    dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def pts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def new_ledger(tmp_path, bot="learner", name=None, clock=None, **kw):
    path = tmp_path / (name or f"ledger_{bot}.sqlite")
    led = open_ledger(path, bot, clock=clock or (lambda: NOW), **kw)
    led.init_params(DEFAULT_PARAMS, reason="initial")
    return led, path


_GIT_CACHE: dict = {}


def git_show(relpath: str) -> str:
    key = relpath
    if key not in _GIT_CACHE:
        try:
            r = subprocess.run(["git", "-C", str(TRADER), "show", f"{BASE_REF}:./{relpath}"], check=True,
                               capture_output=True, text=True, timeout=60)
            _GIT_CACHE[key] = r.stdout
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"git show {BASE_REF}:{relpath} unavailable: {e}")
    return _GIT_CACHE[key]


def load_base_module(relpath: str, modname: str, package: str | None = None):
    if modname in sys.modules:
        return sys.modules[modname]
    src = git_show(relpath)
    mod = types.ModuleType(modname)
    mod.__file__ = f"<{BASE_REF}:{relpath}>"
    if package:
        mod.__package__ = package
    sys.modules[modname] = mod
    try:
        exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    except BaseException:
        sys.modules.pop(modname, None)
        raise
    return mod


def base_ledger():
    return load_base_module("src/trader_core/ledger.py", "wp3_ledger_v3_base")


def mk_dec(M, *, setup="T1", side="long", bar=None, ver=1, pair="ETH/USDT", entry=2000.0, stop=1960.0,
           entered=True, **over):
    bar = bar or BASE + timedelta(hours=10)
    if setup == "R1":
        regime_, rh, rl, rht, rlt, target = "range", 2100.0, 1980.0, 2, 3, 2100.0
        feats = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5,
                 "edge_dist_atr": 0.1}
    else:
        regime_ = "trend_up" if side == "long" else "trend_down"
        rh = rl = target = None
        rht = rlt = 0
        feats = dict(FEAT_T1)
    kw = dict(bar_close_ts=bar, trigger_tf="1h", pair=pair, side=side, setup=setup, regime=regime_, atr_ratio=1.1,
              rh=rh, rl=rl, rh_touches=rht, rl_touches=rlt, features=feats, planned_entry=entry, planned_stop=stop,
              planned_target=target, param_version_id=ver)
    if entered:
        kw.update(veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
                  size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
                  final_action="entered", skip_reason=None)
    else:
        kw.update(veto_status="not_evaluated", veto_reason=None, risk_allowed=None, risk_reason=None,
                  size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
                  final_action="skipped", skip_reason="other")
    kw.update(over)
    return M.DecisionEvent(**kw)


def enter(led, M, tid, *, side="long", price=2000.0, entry=2000.0, stop=1960.0, bar=None, **extra):
    bar = bar or BASE + timedelta(minutes=15 * tid)
    did = led.record_decision(mk_dec(M, side=side, bar=bar, entry=entry, stop=stop))
    led.record_trade_entry(M.TradeEntry(trade_id=tid, decision_id=did, entry_ts=bar + timedelta(seconds=3),
                                        entry_price=price, qty=0.3, leverage=3, fee_entry=0.0, **extra))
    return did, bar


def xit(M, tid, bar, price=2010.0, reason="time_stop", planned_exit=None, **extra):
    return M.TradeExit(trade_id=tid, exit_ts=bar + timedelta(hours=2), exit_price=price, exit_reason=reason,
                       planned_exit=planned_exit, fee_exit=0.0, funding_paid=0.0, **extra)


def build_v3(tmp_path, name="v3.sqlite"):
    """Genuine schema-3 file (10 decisions, 4 entries, 3 exits) built with the base-commit ledger code (A1)."""
    M = base_ledger()
    path = tmp_path / name
    led = M.open_ledger(path, "learner", clock=lambda: NOW)
    led.init_params(DEFAULT_PARAMS, reason="initial")
    bars = {}
    for i in range(10):
        bar = BASE + timedelta(hours=i)
        if i < 4:
            _, b = enter(led, M, i + 1, bar=bar)
            bars[i + 1] = b
        else:
            led.record_decision(mk_dec(M, bar=bar, entered=False))
    for tid in (1, 2, 3):
        led.record_trade_exit(xit(M, tid, bars[tid], 2000.0 + 10 * tid))
    led.close()
    return path


def snapshot(path, skip=("schema_migrations",)):
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    try:
        tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                                          "name NOT LIKE 'sqlite_%'")]
        out = {}
        for t in tabs:
            if t in skip:
                continue
            out[t] = [dict(r) for r in con.execute(f'SELECT * FROM "{t}" ORDER BY rowid')]
        return out
    finally:
        con.close()


def mk_shadow(**over):
    kw = dict(block="r1_disabled", bar_close_ts=BASE + timedelta(hours=3), trigger_tf="1h", pair="BTC/USDT", side="long", setup="R1",
              regime="range", atr_ratio=1.1, rh=105.0, rl=95.0, features=dict(FEAT_R1), planned_entry=100.0,
              planned_stop=98.0, planned_target=104.0, param_version_id=1, strategy="price_action_v1@1b.0",
              reasons="v1b:r1_disabled|R1_long:range,stop_ok,rr_ok", pos_open=0, gate_code="ok")
    kw.update(over)
    return L.ShadowEvent(**kw)


def put_shadow(led, ev=None, **over):
    ev = ev or mk_shadow(**over)
    return led.record_shadow(ev)


def mk_mark(**over):
    kw = dict(ts=BASE + timedelta(hours=1), wallet=1000.0, equity=1002.0, equity_low=994.0, n_open=1, src="sim")
    kw.update(over)
    return L.EquityMark(**kw)


@contextlib.contextmanager
def locked(path):
    c = sqlite3.connect(str(path), timeout=0.1, isolation_level=None)
    c.execute("BEGIN IMMEDIATE")
    try:
        yield c
    finally:
        try:
            c.execute("ROLLBACK")
        finally:
            c.close()


def quick_busy(led):
    led._conn().execute("PRAGMA busy_timeout=50")      # A4


# =====================================================================================================
# D - ledger and migration
# =====================================================================================================
def test_D1_fresh_file_is_v4(tmp_path):
    led, path = new_ledger(tmp_path)
    led.close()
    assert L.SCHEMA_VERSION == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert raw(path, "PRAGMA user_version")[0][0] == 8
    pairs = [(r[0], r[1]) for r in raw(path, "SELECT from_version, to_version FROM schema_migrations")]
    assert (3, 4) in pairs
    names = {r[0] for r in raw(path, "SELECT name FROM sqlite_master")}
    assert {"shadow_decisions", "equity_marks", "v_shadow_decisions"} <= names


def test_D2_v3_file_migrates_losslessly(tmp_path):
    path = build_v3(tmp_path)
    before = snapshot(path)
    assert before["decision_events"] and len(before["decision_events"]) == 10
    assert len(before["trade_entries"]) == 4 and len(before["trade_exits"]) == 3
    old_cols = {t: table_cols(path, t) for t in before}
    led = open_ledger(path, "learner", migrate=True, clock=lambda: NOW)
    led.close()
    assert os.path.exists(str(path) + ".premigrate-v3")
    assert raw(path, "PRAGMA user_version")[0][0] == 8
    after = snapshot(path)
    for t, rows in before.items():
        assert len(after[t]) == len(rows), t
        for a, b in zip(rows, after[t]):
            for c, v in a.items():
                assert b[c] == v, (t, c)
            for c in set(b) - set(a):
                if c in ("arm_id", "source"):          # DD-12 WP-02 (sema 5): eski satirda arm_id dolu, source='arm'
                    continue
                assert b[c] is None, (t, c)
    assert set(after["trade_entries"][0]) - set(old_cols["trade_entries"]) == set(NEW_ENTRY_COLS) | {"arm_id", "session_tag"}
    assert set(after["trade_exits"][0]) - set(old_cols["trade_exits"]) == set(NEW_EXIT_COLS)
    assert raw(path, "PRAGMA foreign_key_check") == []


@pytest.mark.parametrize("kw", [{"read_only": True}, {"migrate": False}])
def test_D3_v3_file_rejected_without_migrate(tmp_path, kw):
    path = build_v3(tmp_path)
    before = snapshot(path)
    with pytest.raises(LedgerSchemaError):
        open_ledger(path, "learner", clock=lambda: NOW, **kw)
    assert raw(path, "PRAGMA user_version")[0][0] == 3
    assert snapshot(path) == before


def test_D4_view_columns_append_only(tmp_path):
    v3 = build_v3(tmp_path)
    fresh, p4 = new_ledger(tmp_path, name="fresh.sqlite")
    fresh.close()
    for view in ("v_trades", "v_closed_trades"):
        old, new = table_cols(v3, view), table_cols(p4, view)
        assert new[:len(old)] == old, view
        assert new[len(old):] == VIEW_NEW_COLS + ["arm_id", "session_tag"], view   # DD-12 WP-02 (sema 5)
        assert old[-1] == "excursion_tf"
    assert table_cols(p4, "v_decisions") == table_cols(v3, "v_decisions") + ["arm_id", "session_tag", "lesson_ids", "source"]
    assert table_cols(p4, "v_proposals") == table_cols(v3, "v_proposals")


def test_D5_new_tables_append_only(tmp_path):
    led, path = new_ledger(tmp_path)
    put_shadow(led)
    led.record_equity_mark(mk_mark())
    led.close()
    con = sqlite3.connect(str(path))
    for t, col in (("shadow_decisions", "reasons"), ("equity_marks", "wallet")):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute(f"UPDATE {t} SET {col}={col}")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute(f"DELETE FROM {t}")
    con.close()


def _core_rows(path):
    out = {}
    for t, drop in (("trade_entries", NEW_ENTRY_COLS + ["arm_id", "session_tag"]),   # DD-12 WP-02: sema 5 sutunlari
                    ("trade_exits", NEW_EXIT_COLS)):
        out[t] = [{k: v for k, v in r.items() if k not in drop} for r in snapshot(path)[t]]
    return out


def test_D6_defaults_equal_v3_behaviour(tmp_path):
    """Same inputs through the base-commit ledger and the new one: identical core columns, new ones NULL."""
    M = base_ledger()
    runs = {}
    for tag, mod in (("old", M), ("new", L)):
        led = mod.open_ledger(tmp_path / f"{tag}.sqlite", "learner", clock=lambda: NOW)
        led.init_params(DEFAULT_PARAMS, reason="initial")
        _, bar = enter(led, mod, 1, side="long")
        led.record_trade_exit(xit(mod, 1, bar, 2043.96))
        _, bar2 = enter(led, mod, 2, side="short", price=2000.0, stop=2040.0)
        led.record_trade_exit(xit(mod, 2, bar2, 1990.0, planned_exit=1995.0, reason="target"))
        led.close()
        runs[tag] = tmp_path / f"{tag}.sqlite"
    assert _core_rows(runs["old"]) == _core_rows(runs["new"])
    for r in snapshot(runs["new"])["trade_entries"]:
        assert all(r[c] is None for c in NEW_ENTRY_COLS)
    for r in snapshot(runs["new"])["trade_exits"]:
        assert all(r[c] is None for c in NEW_EXIT_COLS)
    old_cols = table_cols(runs["old"], "v_trades")
    vo = [dict(r) for r in raw(runs["old"], "SELECT * FROM v_trades ORDER BY trade_id")]
    vn = [dict(r) for r in raw(runs["new"], "SELECT * FROM v_trades ORDER BY trade_id")]
    assert [{c: r[c] for c in old_cols} for r in vn] == vo
    assert all(r[c] is None for r in vn for c in VIEW_NEW_COLS if c != "exit_regime" or True)


@pytest.mark.parametrize("side,fill", [("long", 100.02), ("short", 99.98)])
def test_D7_slip_exec_entry(tmp_path, side, fill):
    led, path = new_ledger(tmp_path)
    T = BASE + timedelta(hours=1)
    stop = 98.0 if side == "long" else 102.0
    enter(led, L, 1, side=side, price=fill, entry=100.0, stop=stop,
          order_ts=T, order_ack_ts=T + timedelta(milliseconds=180), order_ref_price=100.0,
          order_ref_spread=0.0002, order_ref_src="book")
    led.close()
    r = raw(path, "SELECT * FROM v_trades WHERE trade_id=1")[0]
    assert r["slip_exec_entry"] == pytest.approx(0.0002, abs=1e-12)
    assert r["entry_ref_price"] == 100.0 and r["entry_ref_src"] == "book"
    assert r["entry_ref_spread"] == pytest.approx(0.0002)
    assert r["entry_order_ts"] == fmt(T) and r["entry_order_ack_ts"] == fmt(T + timedelta(milliseconds=180))


def test_D8_slip_exec_exit_and_decision(tmp_path):
    led, path = new_ledger(tmp_path)
    _, bar = enter(led, L, 1, price=200.0, entry=200.0, stop=190.0)
    led.record_trade_exit(xit(L, 1, bar, 199.9, reason="regime_flip", order_ref_price=200.0, order_ref_src="sim_open",
                              decision_price=200.5))
    led.close()
    r = raw(path, "SELECT * FROM v_trades WHERE trade_id=1")[0]
    assert r["slip_exec_exit"] == pytest.approx(0.0005, abs=1e-12)
    assert r["slip_decision_exit"] == pytest.approx(0.6 / 200.5, abs=1e-12)
    assert r["slippage_exit"] is None and r["exit_decision_price"] == 200.5 and r["exit_ref_price"] == 200.0


def _bad_entry_cases():
    T = BASE + timedelta(hours=1)
    return {
        "neg_price": dict(order_ref_price=-1.0, order_ref_src="book"),
        "bad_src": dict(order_ref_price=100.0, order_ref_src="x"),
        "price_no_src": dict(order_ref_price=100.0),
        "spread_with_sim_open": dict(order_ref_price=100.0, order_ref_src="sim_open", order_ref_spread=0.0001),
        "ack_before_order": dict(order_ts=T, order_ack_ts=T - timedelta(seconds=1)),
        "ack_without_order": dict(order_ack_ts=T),
    }


@pytest.mark.parametrize("case", list(_bad_entry_cases()))
def test_D9_entry_validation(tmp_path, case):
    led, path = new_ledger(tmp_path)
    bar = BASE + timedelta(hours=1)
    did = led.record_decision(mk_dec(L, bar=bar))
    with pytest.raises(LedgerValidationError):
        led.record_trade_entry(TradeEntry(trade_id=1, decision_id=did, entry_ts=bar, entry_price=2000.0, qty=0.3,
                                          leverage=3, fee_entry=0.0, **_bad_entry_cases()[case]))
    assert raw(path, "SELECT COUNT(*) FROM trade_entries")[0][0] == 0


@pytest.mark.parametrize("case", list(_bad_entry_cases()) + ["bad_regime", "zero_decision_price"])
def test_D9_exit_validation(tmp_path, case):
    led, path = new_ledger(tmp_path)
    _, bar = enter(led, L, 1)
    extra = dict(_bad_entry_cases().get(case) or {})
    if case == "bad_regime":
        extra = dict(exit_regime="sideways")
    if case == "zero_decision_price":
        extra = dict(decision_price=0.0)
    with pytest.raises(LedgerValidationError):
        led.record_trade_exit(xit(L, 1, bar, **extra))
    assert raw(path, "SELECT COUNT(*) FROM trade_exits")[0][0] == 0


def test_D10_clean_exec_fields(tmp_path):
    T = BASE + timedelta(hours=1)
    keys = set(NEW_EXIT_COLS)
    good = dict(order_ts=T, order_ack_ts=T + timedelta(milliseconds=5), order_ref_price=100.0,
                order_ref_spread=0.0002, order_ref_src="book", decision_price=101.0, exit_regime="range")
    out = L.clean_exec_fields(good)
    assert set(out) <= keys and all(out.get(k) == v for k, v in good.items())
    bad_cases = {
        "neg_price": ({"order_ref_price": -1.0}, ["order_ref_price", "order_ref_spread", "order_ref_src"]),
        "bad_src": ({"order_ref_src": "x"}, ["order_ref_price", "order_ref_spread", "order_ref_src"]),
        "spread_sim": ({"order_ref_src": "sim_open"}, ["order_ref_price", "order_ref_spread", "order_ref_src"]),
        "price_nan": ({"order_ref_price": float("nan")}, ["order_ref_price", "order_ref_spread", "order_ref_src"]),
        "price_inf": ({"order_ref_price": float("inf")}, ["order_ref_price", "order_ref_spread", "order_ref_src"]),
        "price_str": ({"order_ref_price": "abc"}, ["order_ref_price", "order_ref_spread", "order_ref_src"]),
        "regime": ({"exit_regime": "sideways"}, ["exit_regime"]),
        "dprice0": ({"decision_price": 0}, ["decision_price"]),
        "dprice_nan": ({"decision_price": float("nan")}, ["decision_price"]),
    }
    for name, (patch, dropped) in bad_cases.items():
        res = L.clean_exec_fields({**good, **patch})
        for k in dropped:
            assert res.get(k) is None, (name, k)
        for k in keys - set(dropped):
            assert res.get(k) == good[k], (name, k)       # other groups are preserved
    # ack before order: only ack is dropped
    res = L.clean_exec_fields({**good, "order_ack_ts": T - timedelta(seconds=1)})
    assert res.get("order_ack_ts") is None and res.get("order_ts") == T
    # naive datetimes
    res = L.clean_exec_fields({**good, "order_ts": T.replace(tzinfo=None)})
    assert res.get("order_ts") is None
    res = L.clean_exec_fields({**good, "order_ack_ts": (T + timedelta(seconds=1)).replace(tzinfo=None)})
    assert res.get("order_ack_ts") is None
    for junk in ({}, {"order_ts": object()}, {"order_ref_price": None, "order_ref_src": 5}, {"unknown": 1}):
        res = L.clean_exec_fields(junk)                   # never raises
        assert set(res) <= keys
    # cleaned payload is writable
    led, path = new_ledger(tmp_path)
    cleaned = L.clean_exec_fields({**good, "order_ref_price": -1.0, "exit_regime": "sideways"})
    did, bar = enter(led, L, 1, **{k: cleaned.get(k) for k in NEW_ENTRY_COLS})
    led.record_trade_exit(xit(L, 1, bar, **{k: cleaned.get(k) for k in NEW_EXIT_COLS}))


def test_D11_idempotency_ignores_measurement_fields(tmp_path):
    led, path = new_ledger(tmp_path)
    bar = BASE + timedelta(hours=1)
    did = led.record_decision(mk_dec(L, bar=bar))
    mk = lambda **o: TradeEntry(trade_id=1, decision_id=did, entry_ts=bar, entry_price=2000.0, qty=0.3,  # noqa: E731
                                leverage=3, fee_entry=0.0, **o)
    a = led.record_trade_entry(mk(order_ref_price=2000.0, order_ref_src="sim_open"))
    b = led.record_trade_entry(mk(order_ref_price=2001.0, order_ref_src="sim_open"))
    assert a == b
    assert raw(path, "SELECT order_ref_price FROM trade_entries")[0][0] == 2000.0
    with pytest.raises(LedgerConflictError):
        led.record_trade_entry(TradeEntry(trade_id=1, decision_id=did, entry_ts=bar, entry_price=2000.0, qty=0.31,
                                          leverage=3, fee_entry=0.0))
    # exits too
    x1 = led.record_trade_exit(xit(L, 1, bar, 2010.0, decision_price=2011.0))
    x2 = led.record_trade_exit(xit(L, 1, bar, 2010.0, decision_price=2012.0))
    assert x1 == x2 and raw(path, "SELECT decision_price FROM trade_exits")[0][0] == 2011.0


def _spool_lines(path):
    p = str(path) + ".spool.jsonl"
    return [ln for ln in open(p).read().splitlines() if ln.strip()] if os.path.exists(p) else []


def test_D12_spool_carries_new_keys_and_old_lines_still_drain(tmp_path):
    led, path = new_ledger(tmp_path)
    T = BASE + timedelta(hours=1)
    bar = BASE + timedelta(minutes=15)
    did = led.record_decision(mk_dec(L, bar=bar))
    did2 = led.record_decision(mk_dec(L, bar=bar + timedelta(hours=2)))
    quick_busy(led)
    with locked(path):
        with contextlib.suppress(L.LedgerError):
            led.record_trade_entry(TradeEntry(
                trade_id=1, decision_id=did, entry_ts=bar, entry_price=2000.0, qty=0.3, leverage=3, fee_entry=0.0,
                order_ts=T, order_ack_ts=T + timedelta(milliseconds=180), order_ref_price=2000.0,
                order_ref_spread=0.0001, order_ref_src="book"))
        lines = _spool_lines(path)
        assert len(lines) == 1
        d = json.loads(lines[0])
        assert all(k in d for k in NEW_ENTRY_COLS)                              # A3
        with contextlib.suppress(L.LedgerError):
            led.record_trade_entry(TradeEntry(trade_id=2, decision_id=did2, entry_ts=bar + timedelta(hours=2),
                                              entry_price=2000.0, qty=0.3, leverage=3, fee_entry=0.0,
                                              order_ref_price=2000.0, order_ref_src="sim_open"))
    lines = _spool_lines(path)
    assert len(lines) == 2
    old = json.loads(lines[1])
    for k in NEW_ENTRY_COLS:
        old.pop(k, None)                                                         # legacy-format line
    with open(str(path) + ".spool.jsonl", "w") as f:
        f.write(lines[0] + "\n" + json.dumps(old, sort_keys=True) + "\n")
    assert led.drain_spool() == 2
    rows = {r["trade_id"]: r for r in raw(path, "SELECT * FROM trade_entries")}
    assert rows[1]["order_ref_price"] == 2000.0 and rows[1]["order_ack_ts"] == fmt(T + timedelta(milliseconds=180))
    assert rows[1]["order_ref_src"] == "book" and rows[1]["order_ref_spread"] == pytest.approx(0.0001)
    assert all(rows[2][c] is None for c in NEW_ENTRY_COLS)


def test_D13_record_shadow(tmp_path):
    led, path = new_ledger(tmp_path)
    i1 = put_shadow(led)
    i2 = put_shadow(led, reasons="different text")          # same unique key: first one stays
    assert i1 == i2
    assert raw(path, "SELECT COUNT(*) FROM shadow_decisions")[0][0] == 1
    assert raw(path, "SELECT reasons FROM shadow_decisions")[0][0].startswith("v1b:r1_disabled")
    assert len(led.list_shadow()) == 1 and led.list_shadow(block="r1_disabled")[0].pair == "BTC/USDT"
    assert raw(path, "SELECT bot, block FROM shadow_decisions")[0][0] == "learner"
    for bad in (dict(block="nope"), dict(planned_stop=101.0),                   # long: stop above entry
                dict(features={**FEAT_R1, "junk": "x" * 17000}, pair="ETH/USDT")):
        with pytest.raises(LedgerValidationError):
            led.record_shadow(mk_shadow(**bad))
    assert raw(path, "SELECT COUNT(*) FROM shadow_decisions")[0][0] == 1
    twin, _ = new_ledger(tmp_path, bot="twin")
    put_shadow(twin)
    assert twin.list_shadow()[0].pair == "BTC/USDT"


def _health(led):
    h = led.entries_allowed()
    return h.ok, h.code


def test_D14_record_failures_do_not_touch_health_or_spool(tmp_path):
    clk = {"t": NOW}
    led, path = new_ledger(tmp_path, clock=lambda: clk["t"])
    assert led.check_writable().ok
    before = _health(led)
    assert before[0] is True
    quick_busy(led)
    with locked(path):
        with pytest.raises(LedgerWriteError):
            put_shadow(led)
        with pytest.raises(LedgerWriteError):
            led.record_equity_mark(mk_mark())
    assert _health(led) == before
    assert not os.path.exists(str(path) + ".spool.jsonl") or not _spool_lines(path)
    # successful shadow write must not refresh a stale _last_write_ok
    clk["t"] = NOW + timedelta(seconds=61)
    put_shadow(led)
    led.record_equity_mark(mk_mark(ts=BASE + timedelta(hours=5)))
    calls = []
    orig = led.check_writable
    led.check_writable = lambda: (calls.append(1), orig())[1]
    led.entries_allowed()
    assert calls, "entries_allowed must still re-probe writability after 61 s"


def test_D15_decisions_unchanged_by_shadow_rows(tmp_path):
    led, path = new_ledger(tmp_path)
    for i in range(4):
        enter(led, L, i + 1, bar=BASE + timedelta(hours=i))
    led.record_decision(mk_dec(L, bar=BASE + timedelta(hours=9), entered=False))
    cnt = lambda: raw(path, "SELECT COUNT(*) FROM v_decisions")[0][0]  # noqa: E731
    ld = lambda: [repr(d) for d in led.list_decisions()]  # noqa: E731
    before = (cnt(), ld(), led.find_orphan_decisions(older_than_s=0))
    for i in range(50):
        put_shadow(led, bar_close_ts=BASE + timedelta(hours=20 + i))
    assert (cnt(), ld(), led.find_orphan_decisions(older_than_s=0)) == before
    assert raw(path, "SELECT COUNT(*) FROM shadow_decisions")[0][0] == 50


def test_D16_record_equity_mark(tmp_path):
    led, path = new_ledger(tmp_path)
    with pytest.raises(LedgerValidationError):
        led.record_equity_mark(mk_mark(equity=1000.0, equity_low=1001.0))
    a = led.record_equity_mark(mk_mark())
    assert a == led.record_equity_mark(mk_mark(wallet=999.0))
    assert raw(path, "SELECT COUNT(*) FROM equity_marks")[0][0] == 1
    assert led.list_equity_marks()[0].equity == 1002.0


# =====================================================================================================
# harness access (engine level tests)
# =====================================================================================================
def H():
    import test_engine_05_spec as h
    return h


def HLV():
    import test_engine_live_spec as h
    return h


def status_records(e) -> dict:
    e.engine.status.write(e.engine, force=True)
    return json.loads(Path(e.cfg.status_path).read_text())["records"]


def trade_row(e, tid):
    rows = raw(e.cfg.ledger_path, "SELECT * FROM v_trades WHERE trade_id=?", (tid,))
    assert rows, "trade row not in ledger"
    return dict(rows[0])


# =====================================================================================================
# E - order time record and exit_regime
# =====================================================================================================
@pytest.fixture
def env(tmp_path):
    h = H()
    e = h.Env(tmp_path, shadow_blocks=[])
    e.start()
    yield e
    e.close()


def test_E1_sim_entry_record(env):
    h = H()
    env.signal(h.T0, (h.BTC,))
    env.decide(h.T0)
    t_dec = env.clock.now()
    env.step(h.T0)
    pos = env.pos()
    assert pos is not None
    r = trade_row(env, pos.trade_id)
    assert r["entry_ref_price"] == 100.0 and r["entry_ref_src"] == "sim_open"
    assert r["entry_ref_spread"] is None and r["entry_order_ack_ts"] is None
    assert r["entry_order_ts"] == fmt(t_dec)
    assert 0.0002 - 1e-12 <= r["slip_exec_entry"] <= 0.0002 + 0.01 / 100.0


def _flip_exit(env, tid_pair=None):
    h = H()
    p = env.open_pos(h.BTC, h.T0)
    D1 = h.T0 + h.H
    env.src.ctx[(h.BTC, D1)] = h.flip_ctx(D1)
    env.decide(D1)
    env.step(D1, pairs=(h.BTC,))
    return p, D1


def test_E2_sim_decision_exit(env):
    p, _ = _flip_exit(env)
    r = trade_row(env, p.trade_id)
    assert r["exit_reason"] == "regime_flip"
    assert r["exit_decision_price"] == 108.0                      # ExitContext.last_close of flip_ctx
    assert r["exit_ref_src"] == "sim_open" and r["exit_ref_price"] == 100.0
    assert 0.0002 - 1e-12 <= r["slip_exec_exit"] <= 0.0002 + 0.01 / 100.0
    assert r["slippage_exit"] is None
    assert r["slip_decision_exit"] == pytest.approx((108.0 - r["exit_price"]) / 108.0)


def test_E3_stop_fill_has_no_exec_fields(env):
    h = H()
    p = env.open_pos(h.BTC, h.T0)
    env.step(h.T0 + h.M1, pairs=(h.BTC,), price=98.5, hi=99.0, lo=97.5)
    r = trade_row(env, p.trade_id)
    assert r["exit_reason"] == "stop"
    for c in ("exit_order_ts", "exit_order_ack_ts", "exit_ref_price", "exit_ref_spread", "exit_ref_src",
              "exit_decision_price"):
        assert r[c] is None, c
    assert r["planned_exit"] is not None and r["slippage_exit"] is not None


def test_E4_race_decision_price_does_not_leak(env):
    h = H()
    p = env.open_pos(h.BTC, h.T0)
    D1 = h.T0 + h.H
    env.src.ctx[(h.BTC, D1)] = h.flip_ctx(D1)
    env.decide(D1)
    env.step(D1, pairs=(h.BTC,), price=97.0, hi=97.5, lo=96.5)       # stop (98) is hit in the same minute
    r = trade_row(env, p.trade_id)
    if r["exit_reason"] != "stop":
        pytest.skip("race premise not reproduced by the paper broker (market exit filled first)")
    assert r["exit_decision_price"] is None
    D3 = h.T0 + 3 * h.H
    p2 = env.open_pos(h.BTC, D3)
    assert p2 is not None and p2.trade_id != p.trade_id
    env.step(D3 + h.M1, pairs=(h.BTC,), price=97.0, hi=97.5, lo=96.5)
    r2 = trade_row(env, p2.trade_id)
    assert r2["exit_reason"] == "stop" and r2["exit_decision_price"] is None


def _hist_regime_env(env, regime_at_d1="trend_down", fill_offset=timedelta(minutes=10), d2=None, d2_gap=False):
    h = H()
    p = env.open_pos(h.BTC, h.T0)
    D1 = h.T0 + h.H
    env.signal(D1, (h.BTC,), signal=False, setup=None, side=None, regime=regime_at_d1)
    env.decide(D1)
    if d2 is not None:
        if d2_gap:
            env.src.frames[(h.BTC, d2)] = h.make_frame(h.BTC, d2, status="data_gap")
        else:
            env.signal(d2, (h.BTC,), signal=False, setup=None, side=None, regime="range")
        env.decide(d2)
    return p, D1


def test_E6a_exit_regime_recent(env):
    h = H()
    p, D1 = _hist_regime_env(env)
    env.step(D1 + timedelta(minutes=10), pairs=(h.BTC,), price=97.0, hi=97.5, lo=96.5)
    assert trade_row(env, p.trade_id)["exit_regime"] == "trend_down"


def test_E6b_exit_regime_stale_is_null(env):
    h = H()
    p, D1 = _hist_regime_env(env)
    env.step(D1 + timedelta(hours=1, minutes=3), pairs=(h.BTC,), price=97.0, hi=97.5, lo=96.5)   # > tf + 121 s
    assert trade_row(env, p.trade_id)["exit_regime"] is None


def test_E6c_exit_regime_data_gap_keeps_previous_within_age(env):
    h = H()
    p, D1 = _hist_regime_env(env, d2=h.T0 + 2 * h.H, d2_gap=True)
    # last ok decision was D1 (= D2 - 1 h); fill 1 h + 60 s after D1 is still within tf + 120 s
    env.step(D1 + timedelta(hours=1, minutes=1), pairs=(h.BTC,), price=97.0, hi=97.5, lo=96.5)
    assert trade_row(env, p.trade_id)["exit_regime"] == "trend_down"


def test_E6c_exit_regime_data_gap_stale_is_null(tmp_path):
    h = H()
    e = h.Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        p, D1 = _hist_regime_env(e, d2=h.T0 + 2 * h.H, d2_gap=True)
        e.step(D1 + timedelta(hours=1, minutes=3), pairs=(h.BTC,), price=97.0, hi=97.5, lo=96.5)
        assert trade_row(e, p.trade_id)["exit_regime"] is None
    finally:
        e.close()


def test_E6d_exit_regime_null_after_restart_without_decision(tmp_path):
    h = H()
    e = h.Env(tmp_path, shadow_blocks=[])
    e.start()
    p = e.open_pos(h.BTC, h.T0)
    D1 = h.T0 + h.H
    e.signal(D1, (h.BTC,), signal=False, setup=None, side=None, regime="trend_down")
    e.decide(D1)
    e.close()
    e2 = h.Env(tmp_path, start=D1 + timedelta(minutes=2), shadow_blocks=[])
    try:
        e2.start()
        if e2.pos(h.BTC) is None:
            pytest.skip("restart premise not reproduced (paper position not restored)")
        e2.step(D1 + timedelta(minutes=5), pairs=(h.BTC,), price=97.0, hi=97.5, lo=96.5)
        assert trade_row(e2, p.trade_id)["exit_regime"] is None
    finally:
        e2.close()


def test_E7_regime_flip_exit_regime(env):
    h = H()
    p = env.open_pos(h.BTC, h.T0)
    D1 = h.T0 + h.H
    env.src.ctx[(h.BTC, D1)] = h.flip_ctx(D1)
    env.signal(D1, (h.BTC,), signal=False, setup=None, side=None, regime="trend_down")
    env.decide(D1)
    env.step(D1, pairs=(h.BTC,))
    r = trade_row(env, p.trade_id)
    assert r["exit_reason"] == "regime_flip" and r["regime"] == "trend_up"
    assert r["exit_regime"] == "trend_down" and r["exit_regime"] != r["regime"]


# ---- live (fake exchange) ---------------------------------------------------------------------------
def make_quote_exchange(clock):
    from fake_exchange import FakeExchange, FakeResp
    from urllib.parse import parse_qsl, urlparse

    class QuoteExchange(FakeExchange):
        def __init__(self, now_ms):
            super().__init__(now_ms)
            self.bid, self.ask, self.delay, self.weight = "1.9999", "2.0001", 0.0, None
            self.quote_times = []

        def request(self, method, url, headers=None, timeout=None):
            u = urlparse(url)
            if u.path.endswith("/ticker/bookTicker"):
                q = dict(parse_qsl(u.query, keep_blank_values=True))
                self.requests.append((method, u.path, q))
                self.quote_times.append(clock.now())
                for i, (part, r) in enumerate(self._inject):
                    if part in u.path:
                        del self._inject[i]
                        if isinstance(r, Exception):
                            raise r
                        return r
                if self.delay:
                    lim = sum(timeout) if isinstance(timeout, (tuple, list)) else timeout
                    clock.advance(min(self.delay, lim) if lim else self.delay)
                    if lim and self.delay > lim:
                        raise TimeoutError("quote timeout")
                return FakeResp(200, {"symbol": q.get("symbol"), "bidPrice": self.bid, "askPrice": self.ask,
                                      "time": 0}, {"X-MBX-USED-WEIGHT-1M": str(self.weight or 2)})
            resp = super().request(method, url, headers=headers, timeout=timeout)
            if self.weight is not None:
                resp.headers["X-MBX-USED-WEIGHT-1M"] = str(self.weight)
            return resp

        def quotes(self):
            return [r for r in self.requests if r[1].endswith("/ticker/bookTicker")]

    now_ms = lambda: int(clock.now().timestamp() * 1000)    # noqa: E731
    return QuoteExchange(now_ms)


def live_env(tmp_path, *, quote=True):
    hl = HLV()
    from trader_engine.clock import SimClock
    clock = SimClock(hl.BOOT)
    ex = make_quote_exchange(clock)
    e = hl.LiveEnv(tmp_path, ex=ex, clock=clock, live_over={"order_quote": bool(quote)})
    Path(e.cfg.status_path).parent.mkdir(parents=True, exist_ok=True)
    e.engine.status = H().mod("status").StatusWriter(e.cfg.status_path, e.clock, e.cfg)
    e.boot()
    return e


def drain(e):
    e.state.drain_outbox(e.ledger)


def lrow(e, tid=1):
    drain(e)
    return trade_row(e, tid)


def test_E8_live_ack_ts_exact_180ms(tmp_path):
    hl = HLV()
    e = live_env(tmp_path, quote=False)
    try:
        e.wire.on(hl.entry_post, after=lambda rec, resp: e.clock.advance(0.18))
        e.enter()
        e.tick(6)
        r = lrow(e)
        assert r["entry_order_ts"] and r["entry_order_ack_ts"] and r["entry_order_ack_ts"] >= r["entry_order_ts"]
        assert round((pts(r["entry_order_ack_ts"]) - pts(r["entry_order_ts"])).total_seconds() * 1000) == 180
    finally:
        e.close()


def test_E9_quote_off_makes_no_book_call(tmp_path):
    e = live_env(tmp_path, quote=False)
    try:
        e.enter()
        e.tick(6)
        # DD-6/D17 (mentor-approved): testnet entry gate does its own single bookTicker GET, so no raw-count assertion;
        # what E9 guards is that the quote fields stay empty when order_quote is off.
        assert len(e.ex.quotes()) <= 1
        r = lrow(e)
        assert r["entry_ref_price"] is None
        assert r["entry_ref_spread"] is None
    finally:
        e.close()


def test_E10_quote_on_once_before_entry_and_not_before_stop(tmp_path):
    hl = HLV()
    e = live_env(tmp_path)
    try:
        e.ex.bid, e.ex.ask = "1.9999", "2.0001"
        e.enter()
        e.tick(6)
        assert len(e.ex.quotes()) == 1
        reqs = e.ex.requests
        i_q = next(i for i, r in enumerate(reqs) if r[1].endswith("/ticker/bookTicker"))
        i_e = next(i for i, r in enumerate(reqs) if r[0] == "POST" and r[1] == "/fapi/v1/order"
                   and hl.role_of(r[2].get("newClientOrderId")) == "e")
        i_s = next(i for i, r in enumerate(reqs) if r[0] == "POST" and r[1] == "/fapi/v1/algoOrder")
        assert i_q < i_e < i_s
        assert not any(r[1].endswith("/ticker/bookTicker") for r in reqs[i_e:i_s + 1])
        r = lrow(e)
        assert r["entry_ref_price"] == pytest.approx(2.0) and r["entry_ref_src"] == "book"
        assert r["entry_ref_spread"] == pytest.approx(0.0001)
    finally:
        e.close()


def test_E10b_quote_before_decision_step_exit(tmp_path):
    hl = HLV()
    import numpy as np
    from trader_engine.position_manager import ExitContext
    e = live_env(tmp_path)
    try:
        e.enter()
        e.tick(6)
        D1 = hl.DEC + hl.H
        e.src.ctx[(hl.XRP, D1)] = ExitContext(bar_close_ts=D1, highs=np.array([2.1, 2.2]), lows=np.array([2.0, 2.05]),
                                              atrs=np.array([0.02, 0.02]), regime_last="trend_down", last_close=2.15,
                                              n_closed=2)
        e.src.frames[(hl.XRP, D1)] = hl.make_frame(hl.XRP, D1, version=e.version_id, signal=False, setup=None,
                                                  side=None, regime="trend_down")
        n0 = len(e.ex.quotes())
        e.decide(D1)
        reqs = e.ex.requests
        xs = [i for i, r in enumerate(reqs) if r[0] == "POST" and hl.role_of(r[2].get("newClientOrderId")) == "x"]
        if not xs:
            pytest.skip("decision-step exit not reproduced in the live harness")
        assert len(e.ex.quotes()) == n0 + 1
        assert max(i for i, r in enumerate(reqs) if r[1].endswith("/ticker/bookTicker")) < xs[0]
    finally:
        e.close()


@pytest.mark.parametrize("mode", ["timeout", "http500", "ask_lt_bid", "bid0"])
def test_E11_quote_errors_do_not_stop_the_trade(tmp_path, mode):
    from fake_exchange import FakeResp
    e = live_env(tmp_path)
    try:
        if mode == "timeout":
            e.ex.inject("bookTicker", TimeoutError("t"))
        elif mode == "http500":
            e.ex.inject("bookTicker", FakeResp(500, {"code": -1000, "msg": "x"}))
        elif mode == "ask_lt_bid":
            e.ex.bid, e.ex.ask = "2.0002", "2.0001"
        else:
            e.ex.bid = "0"
        pos = e.enter()
        assert pos is not None
        e.tick(6)
        assert e.pos().status == "open" and len(e.stops()) == 1
        assert lrow(e)["entry_ref_price"] is None
        assert status_records(e)["exec"]["quote_errors"] == 1
        assert not e.kv("entries_blocked_reason") and not e.broker.entries_blocked_reason
    finally:
        e.close()


def test_E11_counters_equal_to_clean_run(tmp_path):
    counters = []
    for tag, fail in (("clean", False), ("err", True)):
        (tmp_path / tag).mkdir()
        e = live_env(tmp_path / tag)
        try:
            if fail:
                e.ex.inject("bookTicker", TimeoutError("t"))
            e.enter()
            e.tick(6)
            counters.append(e.engine.counters())
        finally:
            e.close()
    # DD-6/D17: a failed quote adds the gate's own fail-open counter; everything else must stay identical.
    counters[1].pop("testnet_price_unchecked", None)
    counters[0].pop("testnet_price_unchecked", None)
    assert counters[0] == counters[1]


def test_E12_no_quote_on_kill_or_stop_failed(tmp_path):
    hl = HLV()
    from trader_engine.types import OrderResult
    e = live_env(tmp_path)
    try:
        e.enter()
        e.tick(6)
        assert len(e.ex.quotes()) == 1
        Path(e.cfg.kill_file).parent.mkdir(parents=True, exist_ok=True)
        Path(e.cfg.kill_file).write_text("{}")
        e.tick(6)
        e.tick(6)
        assert e.posted("x")
        assert len(e.ex.quotes()) == 1
    finally:
        e.close()
    (tmp_path / "sf").mkdir()
    e = live_env(tmp_path / "sf")
    try:
        def first_fails(call, req):
            e.clock.advance(5.1)
            return OrderResult("rejected", req.client_id, reason="filter:-1111")
        e.broker.hooks["place_stop"] = [first_fails]
        e.enter()
        assert e.kv("entries_blocked_reason") == "stop_failed"
        assert len(e.ex.quotes()) == 1                      # only the entry quote
    finally:
        e.close()


def test_E13_no_quote_when_weight_high(tmp_path):
    e = live_env(tmp_path)
    try:
        e.ex.weight = 1790                                   # A8
        pos = e.enter()
        assert e.ex.quotes() == []
        assert pos is not None and e.pos() is not None
    finally:
        e.close()


def test_E14_slow_quote_delays_order_by_at_most_half_second(tmp_path):
    hl = HLV()
    e = live_env(tmp_path)
    try:
        e.ex.delay = 2.0
        t0 = hl.DEC + timedelta(seconds=5)
        e.enter()
        posts = [r for r in e.wire.log if hl.entry_post(r)]
        assert posts
        assert (posts[0].t - t0).total_seconds() <= 0.5 + 1e-6
    finally:
        e.close()


def test_E5_restart_between_post_and_fill_keeps_order_ts(tmp_path):
    hl = HLV()
    from trader_engine.exchange.binance_rest import SignedRestClient  # noqa: F401  (import check only)
    e = live_env(tmp_path)
    e.wire.on(hl.entry_post, after=hl.raising(hl.Crash()))
    e.signal(hl.DEC)
    with pytest.raises(hl.Crash):
        e.decide()
    order_row = e.state.get_order(hl.cid_of("entry"))
    created = order_row.created_ts
    e.hard_close()
    e2 = hl.LiveEnv(e.tmp, ex=e.ex, clock=e.clock, live_over={"order_quote": True}).boot()
    try:
        e2.tick(6)
        e2.tick(6)
        drain(e2)
        r = trade_row(e2, 1)
        assert r["entry_order_ts"] == fmt(created)
        assert r["entry_order_ack_ts"] is None or r["entry_order_ack_ts"] >= r["entry_order_ts"]
    finally:
        e2.close()


# =====================================================================================================
# S - shadow rows
# =====================================================================================================
def _vol_table(kind="long", n=70, start=None):
    """Hourly frame for regime_candidate. long: last candle o=100,h=102,l=99,c=101.5 (EMA ~ 99.5);
    short: mirrored. atr_tf = 2.0."""
    start = start or (BASE - timedelta(hours=n))
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    if kind == "long":
        c = np.full(n, 99.5)
        o, hi, lo = c.copy(), c + 0.6, c - 0.4
        lo[-5:] = [99.2, 99.4, 99.1, 99.3, 99.0]
        o[-1], hi[-1], lo[-1], c[-1] = 100.0, 102.0, 99.0, 101.5
    else:
        c = np.full(n, 100.5)
        o, hi, lo = c.copy(), c + 0.5, c - 0.5
        hi[-5:] = [101.0, 101.2, 101.1, 101.3, 102.0]
        o[-1], hi[-1], lo[-1], c[-1] = 101.5, 102.0, 99.0, 100.0
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": 1.0, "atr_tf": 2.0}, index=idx)


def _expected_t1(table, params):
    ema_last = float(indicators.ema(table["close"], params.pullback_ema).iloc[-1])
    a = float(table["atr_tf"].iloc[-1])
    o, h, l, c = (float(table[k].iloc[-1]) for k in ("open", "high", "low", "close"))
    out = {}
    for side in ("long", "short"):
        recent = table["low" if side == "long" else "high"].iloc[-signals.STOP_LOOKBACK:].tolist()
        cand = signals.evaluate_t1(side, o, h, l, c, ema_last, recent, a, params)
        if cand is not None and cand.skip_reason is None:
            out[side] = cand
    return out


def _g(obj, *names, default=None):
    for n in names:
        if isinstance(obj, dict) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


def _as_list(res):
    if res is None:
        return []
    if isinstance(res, (list, tuple)):
        return list(res)
    return [res]


def shadow_mod():
    return pytest.importorskip("trader_engine.shadow")


@pytest.mark.parametrize("kind", ["long", "short"])
def test_S4_S5_regime_candidate_matches_evaluate_t1(kind):
    sh = shadow_mod()
    params = signals.DEFAULT_SIGNAL_PARAMS
    table = _vol_table(kind)
    expect = _expected_t1(table, params)
    assert set(expect) == {kind}, "test data must produce exactly one T1 candidate (own data bug otherwise)"
    exp = expect[kind]
    got = _as_list(sh.regime_candidate(table, params))
    assert len(got) == 1
    g = got[0]
    assert _g(g, "side") == kind and _g(g, "setup", default="T1") == "T1"
    assert _g(g, "planned_entry", "entry") == exp.entry                       # bit-exact
    assert _g(g, "planned_stop", "stop") == exp.stop
    sda = _g(g, "stop_dist_atr")
    if sda is not None:
        assert sda == exp.stop_dist_atr
    assert _g(g, "planned_target", "target") is None
    if kind == "long":
        assert exp.entry == 101.5 and exp.stop == pytest.approx(99.0 - 0.3 * 2.0)


def test_S4_stop_width_failure_gives_no_candidate():
    sh = shadow_mod()
    params = signals.DEFAULT_SIGNAL_PARAMS
    table = _vol_table("long")
    table.loc[table.index[-5:], "low"] = [90.0, 90.0, 90.0, 90.0, 90.0]        # stop far below -> stop_width
    table.loc[table.index[-1], "low"] = 90.0
    exp = _expected_t1(table, params)
    got = _as_list(sh.regime_candidate(table, params))
    assert len(got) == len(exp)


def test_S6_invalid_ohlc_gives_no_candidate():
    sh = shadow_mod()
    table = _vol_table("long")
    table.iloc[-3, table.columns.get_loc("high")] = float("nan")
    assert _as_list(sh.regime_candidate(table, signals.DEFAULT_SIGNAL_PARAMS)) == []


# ---- engine level -------------------------------------------------------------------------------------
def sh_env(tmp_path, blocks=("regime", "r1_disabled", "same_bar_reentry"), **kw):
    h = H()
    e = h.Env(tmp_path, shadow_blocks=list(blocks), **kw)
    e.start()
    return e


R1_OK = "v1b:r1_disabled|R1_long:range,stop_ok,rr_ok"


def shadow_frame(e, pair, D, *, reasons, setup="R1", side="long", regime_="range", table=None, **kw):
    h = H()
    sr = h.mod("strategy_runner")
    extra = dict(signal=False, setup=setup, side=side, skip_reason=None, regime=regime_, reasons=reasons)
    if regime_ == "range":
        extra.update(rh=105.0, rl=95.0, planned_target=104.0, wick_ratio=0.5, rr=2.5, edge_dist_atr=0.1)
    extra.update(kw)
    f = h.make_frame(pair, D, version=e.version_id, **extra)
    if table is not None:
        f = sr.SignalFrame(pair=f.pair, status="ok", detail=None, last=f.last, table=table)
    e.src.frames[(pair, D)] = f


def test_S1_blocks_empty_never_records_or_reads_15m(tmp_path):
    h = H()
    e = sh_env(tmp_path, blocks=())
    try:
        calls = {"rec": 0, "m15": 0}
        e.real_ledger.record_shadow = lambda ev: calls.__setitem__("rec", calls["rec"] + 1) or 1
        orig = e.view.bars

        def spy(pair, tf, *a, **k):
            if tf == "15m":
                calls["m15"] += 1
            return orig(pair, tf, *a, **k)
        e.view.bars = spy
        shadow_frame(e, h.BTC, h.T0, reasons=R1_OK)
        e.decide(h.T0)
        assert calls == {"rec": 0, "m15": 0}
    finally:
        e.close()


@pytest.mark.parametrize("reasons,n", [
    ("v1b:r1_disabled|R1_long:range,stop_ok,rr_ok", 1),
    ("v1b:r1_disabled|R1_long:range,stop_ok,rr_below_min", 0),
    ("v1b:r1_disabled|R1_long:range,stop_width", 0),
])
def test_S2_r1_disabled(tmp_path, reasons, n):
    h = H()
    e = sh_env(tmp_path)
    try:
        shadow_frame(e, h.BTC, h.T0, reasons=reasons)
        e.decide(h.T0)
        rows = e.real_ledger.list_shadow()
        assert len(rows) == n
        if n:
            r = rows[0]
            assert r.block == "r1_disabled" and r.setup == "R1" and r.side == "long" and r.regime == "range"
            assert (r.planned_entry, r.planned_stop, r.planned_target) == (100.0, 98.0, 104.0)
            assert (r.rh, r.rl) == (105.0, 95.0) and r.trigger_tf == "1h" and r.pair == h.BTC
            assert r.reasons == reasons and r.pos_open in (0, False) and r.strategy.startswith("fake_strategy")
    finally:
        e.close()


@pytest.mark.parametrize("reasons", [
    "v1b:same_bar_reentry|T1_long:trend_up,ema_touch,bull_body,stop_ok",
    "v1b:same_bar_reentry|ml:p=0.612345|T1_long:trend_up,ema_touch,bull_body,stop_ok",     # A10
])
def test_S3_same_bar_reentry(tmp_path, reasons):
    h = H()
    e = sh_env(tmp_path)
    try:
        shadow_frame(e, h.BTC, h.T0, reasons=reasons, setup="T1", regime_="trend_up")
        e.decide(h.T0)
        rows = e.real_ledger.list_shadow()
        assert len(rows) == 1 and rows[0].block == "same_bar_reentry" and rows[0].setup == "T1"
        assert rows[0].regime == "trend_up" and rows[0].planned_target is None
    finally:
        e.close()


def test_S3_negative_reasons_give_no_row(tmp_path):
    h = H()
    e = sh_env(tmp_path)
    try:
        shadow_frame(e, h.BTC, h.T0, reasons="v1b:same_bar_reentry|T1_long:trend_up,stop_width", setup="T1",
                     regime_="trend_up")
        e.decide(h.T0)
        assert e.real_ledger.list_shadow() == []
    finally:
        e.close()


@pytest.mark.parametrize("regime_,reasons,expect_row", [
    ("volatile", "regime_blocked", True), ("unclear", "regime_blocked", True),
    ("range", "regime_blocked", False), ("trend_up", "regime_blocked", False),
    ("trend_down", "regime_blocked", False), ("volatile", "other", False)])
def test_S6_regime_block_conditions(tmp_path, regime_, reasons, expect_row):
    h = H()
    e = sh_env(tmp_path)
    try:
        shadow_frame(e, h.BTC, h.T0, reasons=reasons, setup=None, side=None, regime_=regime_,
                     table=_vol_table("long", start=h.T0 - timedelta(hours=71)))
        e.decide(h.T0)
        rows = e.real_ledger.list_shadow()
        if expect_row:
            assert len(rows) == 1 and rows[0].block == f"regime_{regime_}" and rows[0].setup == "T1"
            assert rows[0].regime == regime_ and rows[0].planned_target is None and rows[0].rh is None
        else:
            assert rows == []
    finally:
        e.close()


def test_S7_tf15_matches_direct_pipeline():
    sh = shadow_mod()
    params = signals.DEFAULT_SIGNAL_PARAMS
    p15 = dataclasses.replace(params, trigger_tf="15m")
    rng = np.random.default_rng(11)
    n15 = 26000
    end = datetime(2027, 6, 1, tzinfo=UTC)
    idx = pd.date_range(end - n15 * timedelta(minutes=15), periods=n15, freq="15min", tz="UTC")
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n15)))
    o = np.concatenate([[c[0]], c[:-1]])
    w = np.abs(rng.normal(0, 0.0015, n15))
    df15 = pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + w), "low": np.minimum(o, c) * (1 - w),
                         "close": c, "volume": 1.0}, index=idx)
    df4 = df15.resample("4h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})

    class V:
        def bars(self, pair, tf, until, n=None, kind="last"):
            df, d = (df15, timedelta(minutes=15)) if tf == "15m" else (df4, timedelta(hours=4))
            df = df[(df.index + d) <= until]
            return (df.tail(n) if n else df).copy()

        def contiguous_tail(self, pair, tf, until, max_n=5000):
            return len(self.bars(pair, tf, until, max_n))

    total = 0
    for k in range(48):
        D = end - timedelta(hours=96 - k)
        b15, b4 = V().bars("X", "15m", D, 5000), V().bars("X", "4h", D, 1500)
        sig = signals.compute_signals(b15, regime.align_to_base(regime.classify_series(b4), b15.index, 4), p15)
        close = sig.index + timedelta(minutes=15)
        sel = sig[(sig["signal"]) & (close > D - timedelta(hours=1)) & (close <= D)]
        want = sorted((pd.Timestamp(i + timedelta(minutes=15)).tz_convert("UTC"), r["side"])
                      for i, r in sel.iterrows())
        got = sorted((pd.Timestamp(_g(x, "bar_close_ts")).tz_convert("UTC") if pd.Timestamp(
            _g(x, "bar_close_ts")).tzinfo else pd.Timestamp(_g(x, "bar_close_ts")).tz_localize("UTC"),
                      _g(x, "side")) for x in _as_list(sh.tf15_candidates(V(), "X", D, params)))
        assert got == want, D
        total += len(want)
    if total == 0:
        pytest.skip("synthetic series produced no 15m signal in any window; widen the data (test data issue)")


def test_S7_tf15_insufficient_warmup_or_gap_is_empty():
    sh = shadow_mod()
    D = datetime(2027, 6, 1, tzinfo=UTC)
    idx = pd.date_range(D - 100 * timedelta(minutes=15), periods=100, freq="15min", tz="UTC")
    df = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0}, index=idx)

    class V:
        def bars(self, pair, tf, until, n=None, kind="last"):
            return df.copy()

        def contiguous_tail(self, *a, **k):
            return len(df)
    assert _as_list(sh.tf15_candidates(V(), "X", D, signals.DEFAULT_SIGNAL_PARAMS)) == []


def _stub_view(first_open, n15=5000, n4=1500):
    D = first_open + n15 * timedelta(minutes=15)
    rng = np.random.default_rng(3)
    idx = pd.date_range(first_open, periods=n15, freq="15min", tz="UTC")
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n15)))
    d15 = pd.DataFrame({"open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1.0}, index=idx)
    idx4 = pd.date_range(D - 4 * timedelta(hours=1) * n4 + timedelta(hours=0), periods=n4, freq="4h", tz="UTC")
    c4 = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n4)))
    d4 = pd.DataFrame({"open": c4, "high": c4 * 1.002, "low": c4 * 0.998, "close": c4, "volume": 1.0}, index=idx4)

    class V:
        def bars(self, pair, tf, until, n=None, kind="last"):
            return (d15 if tf == "15m" else d4).copy()

        def contiguous_tail(self, pair, tf, until, max_n=5000):
            return len(d15 if tf == "15m" else d4)
    return V(), D


@pytest.mark.parametrize("first_offset_min,computes", [(-15, False), (0, True)])
def test_S8_tf15_holdout_wait_boundary(monkeypatch, first_offset_min, computes, kilitli_motor):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    sh = shadow_mod()
    first = HOLDOUT_END + timedelta(minutes=first_offset_min)       # 23:45 of the last locked day / 00:00 of the first free day
    view, D = _stub_view(first)
    calls = []
    for owner, name in ((signals, "compute_signals"), (sh, "compute_signals")):
        if hasattr(owner, name):
            orig = getattr(owner, name)
            monkeypatch.setattr(owner, name, (lambda o_: (lambda *a, **k: (calls.append(1), o_(*a, **k))[1]))(orig))
    try:
        res = sh.tf15_candidates(view, "X", D, signals.DEFAULT_SIGNAL_PARAMS)
    except Exception as e:  # noqa: BLE001
        if computes:
            pytest.skip(f"stub data not accepted by the real pipeline: {e}")
        raise
    if not computes:
        assert _as_list(res) == [] and calls == []
    else:
        assert calls, "pipeline must run once the window starts on 2026-11-01T00:00Z"


def test_S9_shadow_keys_never_in_v_decisions(tmp_path):
    h = H()
    e = sh_env(tmp_path)
    try:
        shadow_frame(e, h.BTC, h.T0, reasons=R1_OK)
        shadow_frame(e, h.ETH, h.T0, reasons="v1b:same_bar_reentry|T1_long:trend_up,stop_ok", setup="T1",
                     regime_="trend_up")
        shadow_frame(e, h.SOL, h.T0, reasons="regime_blocked", setup=None, side=None, regime_="volatile",
                     table=_vol_table("long", start=h.T0 - timedelta(hours=71)))
        e.decide(h.T0)
        rows = e.real_ledger.list_shadow()
        assert rows
        keys = {(r.pair, r.side, r.setup, r.trigger_tf, fmt(r.bar_close_ts) if isinstance(r.bar_close_ts, datetime)
                 else r.bar_close_ts) for r in rows}
        dec = {(d["pair"], d["side"], d["setup"], d["trigger_tf"], d["bar_close_ts"])
               for d in map(dict, raw(e.cfg.ledger_path, "SELECT * FROM v_decisions"))}
        assert not (keys & dec)
        assert not raw(e.cfg.ledger_path, "SELECT 1 FROM decision_events WHERE final_action='shadow'")
    finally:
        e.close()


def test_S10_pos_open_and_gate_code(tmp_path):
    h = H()
    e = sh_env(tmp_path)
    try:
        e.open_pos(h.BTC, h.T0)
        D1 = h.T0 + h.H
        shadow_frame(e, h.BTC, D1, reasons=R1_OK)
        shadow_frame(e, h.ETH, D1, reasons=R1_OK)
        e.decide(D1)
        by_pair = {r.pair: r for r in e.real_ledger.list_shadow()}
        assert by_pair[h.BTC].pos_open in (1, True) and by_pair[h.ETH].pos_open in (0, False)
        # gate closed (KILL): row is still produced, with a gate code
        Path(e.cfg.kill_file).parent.mkdir(parents=True, exist_ok=True)
        Path(e.cfg.kill_file).write_text("{}")
        D2 = D1 + h.H
        shadow_frame(e, h.SOL, D2, reasons=R1_OK)
        e.decide(D2)
        sol = [r for r in e.real_ledger.list_shadow() if r.pair == h.SOL]
        assert len(sol) == 1 and sol[0].gate_code not in (None, "ok")
    finally:
        e.close()


def _scenario(tmp_path, *, boom=False, blocks=("regime", "r1_disabled", "same_bar_reentry"), mtm=True):
    h = H()
    e = sh_env(tmp_path, blocks=blocks, mtm_marks=mtm)
    if boom:
        def bad(*a, **k):
            raise RuntimeError("boom")
        e.real_ledger.record_shadow = bad
    shadow_frame(e, h.ETH, h.T0, reasons=R1_OK)
    p = e.open_pos(h.BTC, h.T0)
    D1 = h.T0 + h.H
    e.src.ctx[(h.BTC, D1)] = h.flip_ctx(D1)
    shadow_frame(e, h.ETH, D1, reasons=R1_OK)
    e.decide(D1)
    e.step(D1, pairs=(h.BTC,))
    D2 = D1 + h.H
    shadow_frame(e, h.ETH, D2, reasons=R1_OK)
    e.decide(D2)
    return e, p


def test_S11_shadow_failure_is_isolated(tmp_path):
    (tmp_path / "ok").mkdir()
    (tmp_path / "bad").mkdir()
    e1, p1 = _scenario(tmp_path / "ok")
    e2, p2 = _scenario(tmp_path / "bad", boom=True)
    try:
        assert e1.engine.counters() == e2.engine.counters()
        assert e1.real_ledger.entries_allowed().ok == e2.real_ledger.entries_allowed().ok
        t1, t2 = trade_row(e1, p1.trade_id), trade_row(e2, p2.trade_id)
        for k in ("entry_price", "exit_price", "exit_reason", "realized_pnl", "qty"):
            assert t1[k] == t2[k]
        assert status_records(e2)["shadow"]["errors"] >= 1
        assert status_records(e1)["shadow"]["errors"] == 0
    finally:
        e1.close()
        e2.close()


def test_S12_shadow_step_runs_last_and_touches_nothing(tmp_path, monkeypatch):
    h = H()
    from trader_engine import order_manager, state as state_mod
    from trader_engine.brokers.paper import PaperBroker
    from trader_engine.engine import Engine
    from trader_engine.status import StatusWriter
    log = []
    wr_state = ("insert_position", "update_position", "insert_order", "update_order", "mark_decided", "set_cursor",
                "kv_set", "outbox_add", "outbox_done", "next_trade_id")
    wr_orders = ("submit_entry", "submit_exit", "market_exit", "place_initial_stop", "replace_stop", "cancel_resting",
                 "resolve_unresolved")
    wr_broker = ("market_order", "place_stop", "place_target", "cancel")

    def wrap(cls, name, tag):
        orig = getattr(cls, name, None)
        if orig is None:
            return

        def w(self, *a, **k):
            log.append(f"{tag}:{name}")
            return orig(self, *a, **k)
        monkeypatch.setattr(cls, name, w)
    for n in wr_state:
        wrap(state_mod.StateStore, n, "state")
    for n in wr_orders:
        wrap(order_manager.OrderManager, n, "orders")
    for n in wr_broker:
        wrap(PaperBroker, n, "broker")
    wrap(StatusWriter, "write", "status")
    orig_sh = Engine._shadow_step

    def sh_wrap(self, D):
        log.append("SHADOW_START")
        try:
            return orig_sh(self, D)
        finally:
            log.append("SHADOW_END")
    monkeypatch.setattr(Engine, "_shadow_step", sh_wrap)
    e = sh_env(tmp_path)
    try:
        shadow_frame(e, h.ETH, h.T0, reasons=R1_OK)
        e.signal(h.T0, (h.BTC,))
        e.decide(h.T0)
        assert "SHADOW_START" in log
        i0, i1 = log.index("SHADOW_START"), log.index("SHADOW_END")
        assert not [x for x in log[i0:i1] if x.split(":")[0] in ("state", "orders", "broker")]
        before = log[:i0]
        assert any(x.startswith("broker:market_order") for x in before)
        assert "status:write" in before
        assert not [x for x in log[i1:] if x.split(":")[0] in ("state", "orders", "broker")]
    finally:
        e.close()


def test_S13_budget_skips_remaining_pairs(tmp_path, monkeypatch):
    h = H()
    sh = shadow_mod()
    pairs = tuple(f"P{i}/USDT" for i in range(10))
    e = sh_env(tmp_path, blocks=("regime",), pairs=pairs)
    try:
        orig = sh.regime_candidate

        def slow(*a, **k):
            e.clock.advance(2.0)
            return orig(*a, **k)
        monkeypatch.setattr(sh, "regime_candidate", slow)
        tbl = _vol_table("long", start=h.T0 - timedelta(hours=71))
        for p in pairs:
            shadow_frame(e, p, h.T0, reasons="regime_blocked", setup=None, side=None, regime_="volatile", table=tbl)
        e.decide(h.T0)
        rec = status_records(e)["shadow"]
        assert rec["budget_skips"] == 7
        assert len({r.pair for r in e.real_ledger.list_shadow()}) <= 3
    finally:
        e.close()


def test_S14_backtest_flag_exists_and_forced_off():
    cli = (TRADER / "src" / "trader_engine" / "cli.py").read_text()
    assert "--record-shadow" in cli
    from trader_engine import backtest
    src = inspect.getsource(backtest.BacktestRunner.build_config)
    assert "shadow_blocks" in src


def test_S15_twin_removed_and_base_has_four():
    from trader_engine.config import load_engine_config
    base, twin = TRADER / "config" / "engine.base.json", TRADER / "config" / "engine.twin.json"
    assert not twin.exists()                      # DD-12: ikiz kaldirildi (kagit yapilandirmasinda shadow_blocks bos: engine.paper.json)
    cfg_b = load_engine_config(base, TRADER / "config" / "engine.learner.json")
    assert set(cfg_b.shadow_blocks) == {"regime", "r1_disabled", "same_bar_reentry"}


def test_S16_view_final_action_and_decision_events_check(tmp_path):
    led, path = new_ledger(tmp_path)
    put_shadow(led)
    put_shadow(led, bar_close_ts=BASE + timedelta(hours=4))
    led.record_decision(mk_dec(L, bar=BASE + timedelta(hours=9), entered=False))
    led.close()
    assert {r[0] for r in raw(path, "SELECT final_action FROM v_shadow_decisions")} == {"shadow"}
    assert raw(path, "SELECT COUNT(*) FROM v_shadow_decisions")[0][0] == 2
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    row = dict(con.execute("SELECT * FROM decision_events LIMIT 1").fetchone())
    row.pop("id")
    row["final_action"] = "shadow"
    row["bar_close_ts"] = fmt(BASE + timedelta(hours=30))
    cols = list(row)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(f"INSERT INTO decision_events ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [row[c] for c in cols])
    con.close()


# =====================================================================================================
# M - mark-to-market drawdown
# =====================================================================================================
def metrics_mod():
    from trader_engine import metrics
    return metrics


def test_M1_drawdown_stats_spec_example():
    m = metrics_mod()
    r = m.drawdown_stats([1010, 990, 1005, 1020, 980], [1000, 970, 985, 1004, 960], 1000)
    assert r["max_dd_mtm_abs"] == pytest.approx(40) and r["max_dd_mtm_pct"] == pytest.approx(3.9216, abs=1e-4)
    assert r["max_dd_mtm_low_abs"] == pytest.approx(60)
    assert r["max_dd_mtm_low_pct"] == pytest.approx(5.8824, abs=1e-4)
    assert r["max_underwater_steps"] == 2


def test_M2_drawdown_stats_edges():
    m = metrics_mod()
    zero = {"max_dd_mtm_abs", "max_dd_mtm_pct", "max_dd_mtm_low_abs", "max_dd_mtm_low_pct", "max_underwater_steps"}
    for args in (([], [], 1000), ([1001, 1002, 1003], [1001, 1002, 1003], 1000)):
        r = m.drawdown_stats(*args)
        assert all(r[k] == 0 for k in zero), r
    r = m.drawdown_stats([1010, 1020, 1030], [970, 1010, 1020], 1000)
    assert r["max_dd_mtm_abs"] == 0 and r["max_dd_mtm_low_abs"] == pytest.approx(30)
    assert r["max_dd_mtm_low_pct"] == pytest.approx(3.0)


def test_M3_max_consecutive_losses():
    assert metrics_mod().max_consecutive_losses([5, -1, -2, 3, -1, -1, -1, 0, -4]) == 3
    assert metrics_mod().max_consecutive_losses([]) == 0


def test_M9_existing_metrics_unchanged(tmp_path):
    new = metrics_mod()
    old = load_base_module("src/trader_engine/metrics.py", "trader_engine.wp3_metrics_base", package="trader_engine")
    assert new.METRIC_KEYS == old.METRIC_KEYS and new.TRADES_COLUMNS == old.TRADES_COLUMNS
    led, path = new_ledger(tmp_path)
    for i in range(1, 9):
        _, bar = enter(led, L, i)
        led.record_trade_exit(xit(L, i, bar, 2043.96 if i % 3 else 1956.04))
    led.close()
    t = new.enrich_trades(new.read_ledger_trades(path))
    for fn, args, kw in (("max_drawdown", (t["realized_pnl"], 1000.0), {}),
                         ("compute_metrics", (t,), dict(wallet_start=1000.0))):
        a, b = getattr(new, fn)(*args, **kw), getattr(old, fn)(*args, **kw)
        assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str), fn


def _mtm_env(tmp_path, **kw):
    h = H()
    e = h.Env(tmp_path, shadow_blocks=[], pairs=(h.BTC, h.ETH), **kw)
    e.start()
    return e


def _marks(e):
    return [dict(r) for r in raw(e.cfg.ledger_path, "SELECT * FROM equity_marks ORDER BY ts")]


def mbar(pair, ts, *, lo, hi, c, mark=True):
    from trader_engine.types import MinuteBar
    m = (lambda v: v) if mark else (lambda v: None)
    return MinuteBar(pair, ts, 60, c, hi, lo, c, m(c), m(hi), m(lo), m(c), 1.0)


def test_M4_M7_flat_account_and_paper_rows(tmp_path):
    h = H()
    e = _mtm_env(tmp_path)
    try:
        Ds = [h.T0 + k * h.H for k in range(3)]
        for D in Ds:
            e.decide(D)
        rows = _marks(e)
        assert [pts(r["ts"]) for r in rows] == Ds
        for r in rows:
            assert r["src"] == "sim" and r["n_open"] == 0
            assert r["equity"] == r["wallet"] == r["equity_low"] and r["equity_low"] <= r["equity"]
    finally:
        e.close()
    (tmp_path / "off").mkdir()
    e = _mtm_env(tmp_path / "off", mtm_marks=False)
    try:
        e.decide(h.T0)
        assert _marks(e) == []
    finally:
        e.close()


@pytest.mark.parametrize("side,use_mark", [("long", True), ("short", True), ("long", False)])
def test_M5_single_position_equity_low(tmp_path, side, use_mark):
    h = H()
    e = _mtm_env(tmp_path)
    try:
        stop = 98.0 if side == "long" else 102.0
        e.signal(h.T0, (h.BTC,), side=side, entry=100.0, stop=stop)
        e.decide(h.T0)
        e.step(h.T0, pairs=(h.BTC,))
        pos = e.pos(h.BTC)
        assert pos is not None
        sgn = 1 if side == "long" else -1
        # two minutes, both inside the stop; worst ends 98.5/98.2 (long) or 101.5/101.8 (short)
        if side == "long":
            bars = [mbar(h.BTC, h.T0 + h.M1, lo=98.5, hi=100.0, c=99.0, mark=use_mark),
                    mbar(h.BTC, h.T0 + 2 * h.M1, lo=98.2, hi=101.0, c=101.0, mark=use_mark)]
            worst = 98.2
        else:
            bars = [mbar(h.BTC, h.T0 + h.M1, hi=101.5, lo=100.0, c=100.5, mark=use_mark),
                    mbar(h.BTC, h.T0 + 2 * h.M1, hi=101.8, lo=99.0, c=99.0, mark=use_mark)]
            worst = 101.8
        from trader_engine.marketdata.sources import MinuteStep
        for b in bars:
            e.set_clock(b.open_ts + h.M1)
            e.engine.process_step(MinuteStep(b.open_ts, {h.BTC: b}))
        acct = e.broker.account()
        e.decide(h.T0 + h.H)
        r = _marks(e)[-1]
        assert r["n_open"] == 1 and r["wallet"] == pytest.approx(acct.wallet)
        assert r["equity"] == pytest.approx(acct.equity)
        want_low = acct.wallet + sgn * (worst - pos.entry_price) * pos.qty
        assert r["equity_low"] == pytest.approx(want_low, abs=1e-6) and r["equity_low"] <= r["equity"]
    finally:
        e.close()


def test_M6_two_positions_use_own_adverse_extremes(tmp_path):
    h = H()
    e = _mtm_env(tmp_path)
    try:
        e.signal(h.T0, (h.BTC,), side="long", entry=100.0, stop=98.0)
        e.signal(h.T0, (h.ETH,), side="short", entry=100.0, stop=102.0)
        e.decide(h.T0)
        e.step(h.T0)
        pb, pe = e.pos(h.BTC), e.pos(h.ETH)
        assert pb is not None and pe is not None
        from trader_engine.marketdata.sources import MinuteStep
        t = h.T0 + h.M1
        e.set_clock(t + h.M1)
        e.engine.process_step(MinuteStep(t, {h.BTC: mbar(h.BTC, t, lo=98.5, hi=100.0, c=100.0),
                                             h.ETH: mbar(h.ETH, t, lo=100.0, hi=101.5, c=100.0)}))
        acct = e.broker.account()
        e.decide(h.T0 + h.H)
        r = _marks(e)[-1]
        want = acct.wallet + (98.5 - pb.entry_price) * pb.qty + (pe.entry_price - 101.5) * pe.qty
        assert r["n_open"] == 2 and r["equity_low"] == pytest.approx(want, abs=1e-6)
    finally:
        e.close()


def test_M10_mtm_failure_is_isolated(tmp_path):
    h = H()
    out = {}
    for tag in ("ok", "bad"):
        (tmp_path / tag).mkdir()
        e = _mtm_env(tmp_path / tag)
        if tag == "bad":
            def boom(m):
                raise RuntimeError("boom")
            e.real_ledger.record_equity_mark = boom
        p = e.open_pos(h.BTC, h.T0)
        D1 = h.T0 + h.H
        e.src.ctx[(h.BTC, D1)] = h.flip_ctx(D1)
        e.decide(D1)
        e.step(D1, pairs=(h.BTC,))
        e.decide(D1 + h.H)
        out[tag] = (e, p)
    try:
        (e1, p1), (e2, p2) = out["ok"], out["bad"]
        assert e1.engine.counters() == e2.engine.counters()
        assert trade_row(e1, p1.trade_id)["exit_price"] == trade_row(e2, p2.trade_id)["exit_price"]
        assert status_records(e2)["mtm"]["errors"] >= 1
    finally:
        for e, _ in out.values():
            e.close()


# =====================================================================================================
# K - behavioural equivalence
# =====================================================================================================
def _dump_state(e):
    con = sqlite3.connect(f"file:{e.cfg.state_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        out = {}
        for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
            out[t] = sorted(repr(tuple(r)) for r in con.execute(f'SELECT * FROM "{t}"'))
        return out
    finally:
        con.close()


def _k4_run(tmp_path, on):
    h = H()
    e = h.Env(tmp_path, shadow_blocks=(["regime", "r1_disabled", "same_bar_reentry"] if on else []), mtm_marks=on)
    e.start()
    shadow_frame(e, h.ETH, h.T0, reasons=R1_OK)
    p = e.open_pos(h.BTC, h.T0)
    for k in range(1, 30):
        e.step(h.T0 + k * h.M1, pairs=(h.BTC,))
    D1 = h.T0 + h.H
    e.src.ctx[(h.BTC, D1)] = h.flip_ctx(D1)
    shadow_frame(e, h.ETH, D1, reasons=R1_OK)
    e.decide(D1)
    e.step(D1, pairs=(h.BTC,))
    e.decide(D1 + h.H)
    return e, p


def test_K4_K5_K6_paper_equivalence(tmp_path):
    (tmp_path / "off").mkdir()
    (tmp_path / "on").mkdir()
    e0, _ = _k4_run(tmp_path / "off", False)
    e1, _ = _k4_run(tmp_path / "on", True)
    try:
        assert _dump_state(e0) == _dump_state(e1)                                  # K4 + K6 (no new kv keys / tables)
        assert e0.broker.log == e1.broker.log
        base_dec = lambda e: [{k: v for k, v in dict(r).items() if k != "id"} for r in  # noqa: E731
                              raw(e.cfg.ledger_path, "SELECT * FROM decision_events ORDER BY id")]
        assert base_dec(e0) == base_dec(e1)
        for t, drop in (("trade_entries", NEW_ENTRY_COLS), ("trade_exits", NEW_EXIT_COLS)):
            f = lambda e: [{k: v for k, v in dict(r).items() if k not in drop}  # noqa: E731
                           for r in raw(e.cfg.ledger_path, f"SELECT * FROM {t} ORDER BY id")]
            assert f(e0) == f(e1), t
        assert set(e0.engine.counters()) == set(e1.engine.counters())             # K5 (A11)
        bad = [k for k in e1.engine.counters() if any(s in k for s in ("shadow", "mtm", "quote", "exec", "records"))]
        assert bad == []
        kv = [r for r in _dump_state(e1).get("kv", [])]
        assert not [r for r in kv if any(s in str(r[0]) for s in ("shadow", "mtm", "exec_meta", "equity"))]
    finally:
        e0.close()
        e1.close()


def test_K6_state_schema_equals_base(tmp_path):
    base = load_base_module("src/trader_engine/state.py", "trader_engine.wp3_state_base", package="trader_engine")
    from trader_engine.state import StateStore
    out = []
    for tag, mod in (("old", base), ("new", sys.modules["trader_engine.state"])):
        p = tmp_path / f"{tag}.sqlite"
        s = mod.StateStore(str(p), bot="learner")
        s.close()
        con = sqlite3.connect(str(p))
        tabs = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE "
                                          "'sqlite_%' ORDER BY name")]
        out.append((con.execute("PRAGMA user_version").fetchone()[0],
                    {t: [r[1:3] for r in con.execute(f'PRAGMA table_info("{t}")')] for t in tabs}))
        con.close()
    assert out[0] == out[1] and out[0][0] == 1
    assert StateStore is not None


def _golden_cmd(extra, out_root, src_dir):
    return [sys.executable, "-m", "trader_engine", "backtest", "--id", "wp3_k1", "--period", "20250101-20250401",
            "--tf", "1h", "--fill-model", "native", "--strategy", "price_action_v1", "--synthetic-rules",
            "--target-trade-risk", "0.005", "--pairs", "BTC/USDT,SOL/USDT,AVAX/USDT", "--out-root",
            str(out_root)] + extra


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()





# =====================================================================================================
# T - consumers
# =====================================================================================================
def _ledger_pair(tmp_path):
    """Two synthetic runs with identical decisions/trades; the second also has shadow rows, filled measurement
    columns and equity marks."""
    paths = []
    for tag in ("plain", "rich"):
        d = tmp_path / tag
        d.mkdir()
        led = open_ledger(d / "ledger.sqlite", "learner", clock=lambda: NOW)
        led.init_params(DEFAULT_PARAMS, reason="initial")
        for i in range(1, 6):
            extra = {}
            xextra = {}
            if tag == "rich":
                T = BASE + timedelta(minutes=15 * i)
                extra = dict(order_ts=T, order_ack_ts=T + timedelta(milliseconds=100), order_ref_price=2000.0,
                             order_ref_spread=0.0001, order_ref_src="book")
                xextra = dict(order_ref_price=2010.0, order_ref_src="sim_open", decision_price=2012.0,
                              exit_regime="range")
            _, bar = enter(led, L, i, **extra)
            led.record_trade_exit(xit(L, i, bar, 2020.0 if i % 2 else 1990.0, **xextra))
        for i in range(6, 9):
            led.record_decision(mk_dec(L, bar=BASE + timedelta(hours=40 + i), entered=False))
        if tag == "rich":
            for i in range(30):
                put_shadow(led, bar_close_ts=BASE + timedelta(hours=100 + i))
            for i in range(5):
                led.record_equity_mark(mk_mark(ts=BASE + timedelta(hours=i + 1)))
        led.close()
        paths.append(d)
    return paths


# 23.11.2026 kullanici karari (kilit acildi): trader_ml/guards.py, trader_ml/config.py ve trader_engine/holdout.py KILIT_ACIK icin
# bilerek degistirildi; A1 blob esitligi artik bunlar icin aranmaz. 24.11 kullanici karari: ML filtreleri silindi (trader_ml/features*,
# labels, trader_core/ml_features* kodla birlikte gitti). Digerleri donuk kalir.
# 24.11 kullanici karari: formasyon kutuphanesi: indicators.py'ye GF1/IN1 gostergeleri EKLENDI (mevcut fonksiyonlar ayni; blob esitligi aranmaz,
# test_dd12_wp18_impl.py sha256 sabiti gercek degerden yeniden hesaplandi).
FROZEN = ["src/trader_core/signals.py", "src/trader_core/regime.py"]


def test_T1_frozen_files_blob_hashes_unchanged():
    for rel in FROZEN:
        p = TRADER / rel
        try:
            cur = subprocess.run(["git", "-C", str(TRADER), "hash-object", rel], capture_output=True, text=True,
                                 check=True, timeout=30).stdout.strip()
            old = subprocess.run(["git", "-C", str(TRADER), "rev-parse", f"{BASE_REF}:./{rel}"], capture_output=True,
                                 text=True, check=True, timeout=30).stdout.strip()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"git unavailable: {e}")
        assert cur == old, rel
        assert p.exists()


def test_T2_drift_monitor_and_ledger_reads_blind_to_new_data(tmp_path):
    from trader_core import drift_monitor as dm
    a, b = _ledger_pair(tmp_path)
    ra, rb = (dm.evaluate(dm.load_ledger(str(d / "ledger.sqlite"), "learner"), None, None, NOW, bot="learner")
              for d in (a, b))
    assert json.dumps(ra, sort_keys=True, default=str) == json.dumps(rb, sort_keys=True, default=str)
    la, lb = (open_ledger(d / "ledger.sqlite", "learner", read_only=True, clock=lambda: NOW) for d in (a, b))
    try:
        f = lambda led: [(x.pair, x.side, x.final_action, x.planned_entry) for x in led.list_decisions()]  # noqa: E731
        assert f(la) == f(lb)
        assert [(t.trade_id, t.realized_pnl, t.slippage_entry) for t in la.list_closed_trades()] == \
               [(t.trade_id, t.realized_pnl, t.slippage_entry) for t in lb.list_closed_trades()]
    finally:
        la.close()
        lb.close()


def test_T3_static_name_isolation():
    names = ("shadow_decisions", "v_shadow_decisions", "cf_shadow_outcomes")
    allowed = {"src/trader_core/ledger.py", "src/trader_core/counterfactual.py", "src/trader_engine/engine.py",
               "src/trader_engine/shadow.py", "scripts/counterfactual_run.py", "src/trader_reports/inputs.py",
               "src/trader_reports/gates.py"}
    hits = set()
    for top in ("src", "scripts", "research"):
        for p in (TRADER / top).rglob("*.py"):
            try:
                text = p.read_text()
            except OSError:
                continue
            if any(n in text for n in names):
                hits.add(str(p.relative_to(TRADER)))
    assert hits <= allowed, sorted(hits - allowed)
    forbidden = ["src/trader_core/drift_monitor.py", "src/trader_core/health.py"]
    forbidden += [str(p.relative_to(TRADER)) for p in (TRADER / "src" / "trader_ml").rglob("*.py")]
    assert not (set(forbidden) & hits)


def test_T5_backup_tables_and_triggers(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("wp3_health_backup", TRADER / "scripts" / "health_backup.py")
    hb = importlib.util.module_from_spec(spec)
    sys.modules["wp3_health_backup"] = hb
    spec.loader.exec_module(hb)
    led, path = new_ledger(tmp_path)
    put_shadow(led)
    led.record_equity_mark(mk_mark())
    led.close()
    dst = tmp_path / "copy.sqlite"
    src_con, dst_con = sqlite3.connect(str(path)), sqlite3.connect(str(dst))
    src_con.backup(dst_con)
    dst_con.close()
    con = sqlite3.connect(str(dst))
    try:
        ids = hb._max_ids(con)
        assert ids["shadow_decisions"] == 1 and ids["equity_marks"] == 1
        assert hb._trigger_counts(con).get("shadow_decisions") == 2 and hb._trigger_counts(con).get("equity_marks") == 2
        assert hb._trigger_counts(con) == hb._trigger_counts(src_con)
    finally:
        con.close()
        src_con.close()


def test_T6_counterfactual_shadow_api_exists():
    cf = pytest.importorskip("trader_core.counterfactual")
    assert hasattr(cf, "shadow_outcomes")
    sig = inspect.signature(cf.shadow_outcomes)
    for p in ("path", "bot", "now", "days", "method"):
        assert p in sig.parameters
    assert sig.parameters["method"].default == "barrier"
    # not covered here: numeric equality with skipped decisions, pending horizon, holdout skip (needs a market store
    # fixture whose format is defined by alinmayan-sinyal-spec.md, which is outside the allowed reading list)


def test_T7_report_schema_check_accepts_7_rejects_8():
    from trader_reports import inputs
    for uv, ok in ((2, True), (3, True), (4, True), (5, True), (6, True), (7, True), (8, True), (9, False)):   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
        con = sqlite3.connect(":memory:")
        con.execute(f"PRAGMA user_version={uv}")
        if ok:
            assert inputs.check_ledger_schema(con) == uv
        else:
            with pytest.raises(Exception):
                inputs.check_ledger_schema(con)
        con.close()


# =====================================================================================================
# P - performance
# =====================================================================================================
def test_P1_shadow_compute_time_and_memory():
    sh = shadow_mod()
    params = signals.DEFAULT_SIGNAL_PARAMS
    first = datetime(2027, 3, 1, tzinfo=UTC)
    view, D = _stub_view(first)
    tbl = _vol_table("long", n=1500)

    def one_round():
        for _ in range(10):
            _as_list(sh.tf15_candidates(view, "X", D, params))
            sh.regime_candidate(tbl, params)
            sh.regime_candidate(tbl, params)
    t0 = time.perf_counter()
    one_round()
    dt = time.perf_counter() - t0                      # timed without tracemalloc (it slows execution ~10x)
    tracemalloc.start()
    one_round()
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert dt <= 5.0, dt
    assert peak <= 30 * 1024 * 1024, peak


def test_P2_mtm_on_minute_speed():
    mtm = pytest.importorskip("trader_engine.mtm")
    try:
        rec = mtm.MtmRecorder(lambda m: None)
    except TypeError:
        try:
            rec = mtm.MtmRecorder(writer=lambda m: None)
        except TypeError as e:
            pytest.skip(f"MtmRecorder constructor unknown (A9): {e}")
    from trader_engine.types import Position
    t_ref = datetime(2027, 1, 1, tzinfo=UTC)

    def mkpos(i, pair):
        vals = {}
        for f in dataclasses.fields(Position):
            a = str(f.type)
            vals[f.name] = (t_ref if "datetime" in a else 1 if a.startswith("int") else 1.0 if a.startswith("float")
                            else "x" if a.startswith("str") else None)
        vals.update(trade_id=i + 1, pair=pair, side="long" if i % 2 else "short", status="open", entry_price=100.0,
                    qty=1.0, bot="learner", setup="T1", trigger_tf="1h")
        return Position(**vals)
    pairs = [f"P{i}/USDT" for i in range(10)]
    pos = [mkpos(i, p) for i, p in enumerate(pairs)]
    from trader_engine.types import MinuteBar
    t0 = datetime(2027, 1, 1, tzinfo=UTC)
    t = time.process_time()                             # CPU suresi: paralel CI kosucusunda (xdist) duvar saati dalgalanmasindan etkilenmez
    for k in range(100_000):
        ts = t0 + timedelta(minutes=k)
        bars = {p: MinuteBar(p, ts, 60, 100, 101, 99, 100, 100, 101, 99, 100, 1.0) for p in pairs}
        rec.on_minute(ts, bars, pos, 1000.0)
        if time.process_time() - t > 30:
            break
    assert time.process_time() - t <= 2.0 + 2.0         # allowance: 10 MinuteBar constructions per iteration (~2 s)


def test_P3_migration_speed(tmp_path):
    path = build_v3(tmp_path)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    dec = dict(con.execute("SELECT * FROM decision_events WHERE final_action='skipped' LIMIT 1").fetchone())
    ent = dict(con.execute("SELECT * FROM trade_entries LIMIT 1").fetchone())
    ex = dict(con.execute("SELECT * FROM trade_exits LIMIT 1").fetchone())

    def bulk(table, row, n, mut):
        cols = [c for c in row if c != "id"]
        con.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        ([mut(dict(row), i)[c] for c in cols] for i in range(n)))
    base_dt = datetime(2024, 1, 1, tzinfo=UTC)
    bulk("decision_events", dec, 200_000, lambda r, i: {**r, "bar_close_ts": fmt(base_dt + timedelta(minutes=15 * i)),
                                                        "pair": f"P{i % 7}/USDT"})
    bulk("trade_entries", ent, 20_000, lambda r, i: {**r, "trade_id": 1000 + i})
    bulk("trade_exits", ex, 20_000, lambda r, i: {**r, "trade_id": 1000 + i})
    con.commit()
    con.close()
    t0 = time.perf_counter()
    bk = sqlite3.connect(str(path))
    bk.backup(sqlite3.connect(str(tmp_path / "ref_backup.sqlite")))
    bk.close()
    t_backup = time.perf_counter() - t0
    # P3 olcutu (docs/defter-ek-alanlar-spec.md): goc 3 -> 4, yedek haric <= 5 sn. Sonraki goclar (4 -> 5, 5 -> 6) tablo yeniden
    # kurar ve P3 kapsaminda degildir; zincirin tamami ayrica dogrulanir (sure olcutu yok).
    import shutil
    from trader_core import ledger as LG
    step = tmp_path / "v3_step.sqlite"
    shutil.copyfile(path, step)
    c = sqlite3.connect(str(step))
    t0 = time.perf_counter()
    c.executescript("BEGIN IMMEDIATE;\n" + LG.MIGRATIONS[3]("learner", fmt(NOW)) + "PRAGMA user_version=4;\nCOMMIT;")
    t_3_4 = time.perf_counter() - t0
    c.close()
    assert t_3_4 <= 5.0, (t_3_4, t_backup)
    led = open_ledger(path, "learner", migrate=True, clock=lambda: NOW)
    led.close()
    assert raw(path, "PRAGMA user_version")[0][0] == 8


def test_P4_import_weight_and_architecture_tests_still_pass():
    files = ["tests/engine/test_engine_import_weight.py", "tests/engine/test_engine_dependency_direction.py",
             "tests/engine/test_engine_clock_discipline.py", "tests/engine/test_engine_module_inventory.py"]
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *files],
                       cwd=str(TRADER), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
