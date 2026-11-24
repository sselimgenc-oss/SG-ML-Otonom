"""Schema-v2 tests for the trade ledger, written only from docs/defter-spec.md.

ASSUMPTIONS (the spec has no literal v1 DDL):
* The v1 database is hand-built with raw SQL from the column lists in spec
  sections 3.2-3.9 and 7.1 (decision_events/trade_entries carry activation_id).
  Trigger names are assumed to be ``trg_<table>_no_update`` / ``_no_delete``;
  views v_decisions / v_trades / v_closed_trades / v_proposals are my own
  reading of 3.8. user_version=1, schema_migrations holds (0, 1).
* The "atomic migration" test induces a mid-way failure by pre-creating an
  object named ``trg_trade_exits_excursion_check`` in the v1 file (10.1 step 1
  says the migration creates that trigger after the ALTERs).
* Proposal status is read through raw SQL on proposal_status_events, and
  stored evidence through raw SQL on param_versions, to avoid depending on
  dataclass attribute names the spec does not fix.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from trader_core import ledger as L
from trader_core.ledger import (
    DecisionEvent,
    LedgerConflictError,
    LedgerError,
    LedgerSchemaError,
    LedgerStateError,
    LedgerValidationError,
    TradeEntry,
    TradeExit,
    open_ledger,
)

UTC = timezone.utc
NOW = datetime(2027, 1, 1, tzinfo=UTC)
BASE = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)

DEFAULT_PARAMS = {
    "range_width_atr": 4.0,
    "vol_ratio_max": 1.5,
    "edge_zone_atr": 0.25,
    "pullback_ema": 50,
    "stop_buffer_atr": 0.3,
    "trail_atr": 3.0,
    "range_target_frac": 0.75,
    "rr_min": 1.5,
    "trigger_tf": "1h",
}


ALT_BOUNDS = {"vol_ratio_max": (1.3, 1.7), "stop_buffer_atr": (0.2, 0.5),
              "trail_atr": (2.5, 3.5), "range_target_frac": (0.6, 0.9), "rr_min": (1.2, 1.9)}


def P(**over):
    d = dict(DEFAULT_PARAMS)
    d.update(over)
    return d


def clock():
    return NOW


def new_ledger(tmp_path, bot="learner", name=None, init=True, **kw):
    path = tmp_path / (name or f"ledger_{bot}.sqlite")
    led = open_ledger(path, bot, clock=clock, **kw)
    if init:
        led.init_params(DEFAULT_PARAMS, reason="initial")
    return led, path


def raw(path, sql, args=()):
    con = sqlite3.connect(str(path))
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def cols(path, table):
    return [r[1] for r in raw(path, f"PRAGMA table_info({table})")]


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------

def mk_decision(setup="R1", side="long", bar=None, ver=1, pair="ETH/USDT", **over):
    bar = bar or BASE + timedelta(hours=10)
    if setup == "R1":
        regime, rh, rl, rht, rlt = "range", 2100.0, 1980.0, 2, 3
        target = 2100.0
        feats = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0,
                 "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.1}
    else:
        regime = "trend_up" if side == "long" else "trend_down"
        rh = rl = None
        rht = rlt = 0
        target = None
        feats = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0,
                 "pullback_ema": 50, "ema_value": 1995.0, "body_ratio": 0.6}
    kw = dict(
        bar_close_ts=bar, trigger_tf="1h", pair=pair, side=side, setup=setup,
        regime=regime, atr_ratio=1.1, rh=rh, rl=rl, rh_touches=rht, rl_touches=rlt,
        features=feats, planned_entry=2000.0, planned_stop=1960.0,
        planned_target=target, param_version_id=ver, veto_status="allowed",
        veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
        size_notional=600.0, size_margin=200.0, size_risk_amount=13.188,
        leverage=3, final_action="entered", skip_reason=None,
    )
    kw.update(over)
    return DecisionEvent(**kw)


def enter(led, tid, setup="R1", ver=1, bar=None, entry_ts=None, **dec_over):
    bar = bar or BASE + timedelta(minutes=15 * tid)
    did = led.record_decision(mk_decision(setup=setup, ver=ver, bar=bar, **dec_over))
    led.record_trade_entry(TradeEntry(
        trade_id=tid, decision_id=did, entry_ts=entry_ts or bar + timedelta(seconds=3),
        entry_price=2000.0, qty=0.3, leverage=3, fee_entry=0.0))
    return did


def closed_trade(led, tid, setup="R1", ver=1, win=True, exit_after_min=120):
    """Long trade, zero fees: exit 2043.96 => +1.0R, 1956.04 => -1.0R."""
    bar = BASE + timedelta(minutes=15 * tid)
    enter(led, tid, setup, ver, bar)
    xp = 2043.96 if win else 1956.04
    led.record_trade_exit(TradeExit(
        trade_id=tid, exit_ts=bar + timedelta(seconds=3, minutes=exit_after_min),
        exit_price=xp, exit_reason="time_stop", planned_exit=None,
        fee_exit=0.0, funding_paid=0.0))


def last_status(path, pid):
    return raw(path, "SELECT status, code FROM proposal_status_events "
                     "WHERE proposal_id=? ORDER BY id DESC LIMIT 1", (pid,))[0]


def user_version(led_or_ver, path, ver, **over):
    """Create + activate a user version derived from defaults."""
    vid = led_or_ver.create_user_version(P(**over), reason="v")
    res = led_or_ver.activate_version(vid, actor="user", reason="a")
    assert res.ok, res
    return vid


# ==========================================================================
# v2 fresh schema
# ==========================================================================

def test_schema_version_constant():
    assert L.SCHEMA_VERSION == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)


def test_fresh_file_is_v2(tmp_path):
    led, path = new_ledger(tmp_path)
    led.close()
    assert raw(path, "PRAGMA user_version")[0][0] == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    c = cols(path, "trade_exits")
    for name in ("mfe_r", "mae_r", "bars_held", "excursion_tf"):
        assert name in c
    for view in ("v_trades", "v_closed_trades"):
        vc = cols(path, view)
        for name in ("mfe_r", "mae_r", "bars_held", "excursion_tf"):
            assert name in vc, (view, name)
    pairs = raw(path, "SELECT from_version, to_version FROM schema_migrations")
    assert (1, 2) in pairs


def test_fresh_excursion_trigger_and_append_only(tmp_path):
    led, path = new_ledger(tmp_path)
    closed_trade(led, 1)
    led.close()
    names = {r[0] for r in raw(path, "SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert "trg_trade_exits_excursion_check" in names
    con = sqlite3.connect(str(path))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("UPDATE trade_exits SET fee_exit=1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        con.execute("DELETE FROM trade_exits")
    con.close()


def test_raw_insert_violating_excursion_check_is_blocked(tmp_path):
    """CHECK trio (mfe_r/mae_r/excursion_tf all-or-none, >= 0) enforced in DB."""
    led, path = new_ledger(tmp_path)
    enter(led, 1)
    led.close()
    con = sqlite3.connect(str(path))
    base = ("INSERT INTO trade_exits (bot, trade_id, exit_ts, exit_price, exit_reason, "
            "fee_exit, funding_paid, gross_pnl, realized_pnl, r_multiple, recorded_at, "
            "mfe_r, mae_r, excursion_tf) VALUES ('learner', 1, '2026-12-02T00:00:00.000Z', "
            "2010, 'other', 0, 0, 3, 3, 0.2, '2026-12-02T00:00:00.000Z', ?, ?, ?)")
    for args in [(1.0, None, "1m"), (None, None, "1m"), (-1.0, 0.5, "1m"), (1.0, -0.5, "1m")]:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(base, args)
    con.close()


# ==========================================================================
# exit field computation + validation (spec 3.4.1 / 12.3 / 12.4)
# ==========================================================================

def _spec_trade_7(led, **exit_over):
    """12.2 / 12.3 trade 7."""
    bar = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)
    did = led.record_decision(mk_decision(bar=bar))
    led.record_trade_entry(TradeEntry(
        trade_id=7, decision_id=did, entry_ts=datetime(2026, 12, 1, 10, 0, 3, tzinfo=UTC),
        entry_price=2001.0, qty=0.3, leverage=3, fee_entry=0.30015))
    kw = dict(trade_id=7, exit_ts=datetime(2026, 12, 2, 9, 0, 0, tzinfo=UTC),
              exit_price=2079.0, exit_reason="target", planned_exit=2100.0,
              fee_exit=0.31185, funding_paid=0.1,
              max_favorable_price=2085.0, max_adverse_price=1992.0, excursion_tf="1m")
    kw.update(exit_over)
    return led.record_trade_exit(TradeExit(**kw))


def test_spec_example_mfe_mae_bars(tmp_path):
    led, _ = new_ledger(tmp_path)
    _spec_trade_7(led)
    t = led.get_trade(7)
    assert t.mfe_r == pytest.approx(25.2 / 13.188, abs=1e-5)
    assert t.mfe_r == pytest.approx(1.9109, abs=1e-4)
    assert t.mae_r == pytest.approx(2.7 / 13.188, abs=1e-5)
    assert t.mae_r == pytest.approx(0.2047, abs=1e-4)
    assert t.bars_held == 92
    assert t.excursion_tf == "1m"
    assert t.gross_pnl == pytest.approx(23.4)
    assert t.realized_pnl == pytest.approx(22.688, abs=1e-6)
    assert t.r_multiple == pytest.approx(1.720352, abs=1e-5)
    assert t.slippage_exit == pytest.approx(0.01)
    # gross/planned_risk <= mfe_r
    assert t.gross_pnl / t.planned_risk <= t.mfe_r
    assert t.mfe_r >= 0 and t.mae_r >= 0


def test_mfe_mae_rounded_to_six_decimals(tmp_path):
    led, _ = new_ledger(tmp_path)
    _spec_trade_7(led)
    t = led.get_trade(7)
    assert t.mfe_r == round(t.mfe_r, 6)
    assert t.mae_r == round(t.mae_r, 6)


def test_all_none_excursion_still_computes_bars_held(tmp_path):
    led, _ = new_ledger(tmp_path)
    _spec_trade_7(led, max_favorable_price=None, max_adverse_price=None, excursion_tf=None)
    t = led.get_trade(7)
    assert t.mfe_r is None and t.mae_r is None and t.excursion_tf is None
    assert t.bars_held == 92


def test_short_example_mfe_mae(tmp_path):
    led, _ = new_ledger(tmp_path)
    bar = BASE + timedelta(hours=10)
    did = led.record_decision(mk_decision(
        setup="T1", side="short", bar=bar, pair="BTC/USDT", planned_entry=100.0,
        planned_stop=101.0, size_qty=10.0, size_notional=1000.0, size_margin=333.33,
        size_risk_amount=12.01))
    led.record_trade_entry(TradeEntry(
        trade_id=8, decision_id=did, entry_ts=bar + timedelta(seconds=1), entry_price=100.0,
        qty=10.0, leverage=3, fee_entry=0.5))
    led.record_trade_exit(TradeExit(
        trade_id=8, exit_ts=bar + timedelta(hours=2), exit_price=101.0, exit_reason="stop",
        planned_exit=101.0, fee_exit=0.505, funding_paid=-0.05,
        max_favorable_price=99.2, max_adverse_price=101.0, excursion_tf="5m"))
    t = led.get_trade(8)
    assert t.mfe_r == pytest.approx(10 * 0.8 / 12.01, abs=1e-5)
    assert t.mfe_r == pytest.approx(0.6661, abs=1e-4)
    assert t.mae_r == pytest.approx(10 * 1.0 / 12.01, abs=1e-5)
    assert t.mae_r == pytest.approx(0.8326, abs=1e-4)
    assert t.realized_pnl == pytest.approx(-10.955, abs=1e-6)
    assert t.excursion_tf == "5m"


@pytest.mark.parametrize("entry,exit_,expected", [
    ((10, 0, 3), (10, 14, 59), 0),
    ((10, 0, 3), (10, 15, 0), 1),
    ((10, 0, 3), (10, 29, 59), 1),
    ((10, 15, 0), (10, 30, 0), 1),   # entry on boundary: entry < c <= exit
    ((10, 0, 0), (11, 0, 0), 4),
    ((10, 7, 0), (10, 8, 0), 0),
])
def test_bars_held_floor_formula(tmp_path, entry, exit_, expected):
    led, _ = new_ledger(tmp_path)
    e_ts = datetime(2026, 12, 1, *entry, tzinfo=UTC)
    x_ts = datetime(2026, 12, 1, *exit_, tzinfo=UTC)
    enter(led, 1, entry_ts=e_ts)
    led.record_trade_exit(TradeExit(
        trade_id=1, exit_ts=x_ts, exit_price=2010.0, exit_reason="other",
        planned_exit=None, fee_exit=0.0, funding_paid=0.0))
    assert led.get_trade(1).bars_held == expected


@pytest.mark.parametrize("over", [
    dict(max_favorable_price=2050.0),                       # below exit price 2079
    dict(max_favorable_price=2000.0),                       # below entry
    dict(max_adverse_price=2005.0),                         # above min(entry, exit)=2001
    dict(max_favorable_price=2085.0, max_adverse_price=None),
    dict(max_favorable_price=None),
    dict(excursion_tf=None),
    dict(excursion_tf="30m"),
    dict(excursion_tf="1h"),
    dict(excursion_tf=""),
    dict(max_favorable_price=0.0),
    dict(max_adverse_price=-5.0),
    dict(max_favorable_price=float("nan")),
    dict(max_favorable_price=float("inf")),
    dict(max_adverse_price=float("nan")),
    dict(max_favorable_price="2085"),
])
def test_invalid_excursion_rejected_and_nothing_written(tmp_path, over):
    led, path = new_ledger(tmp_path)
    with pytest.raises(LedgerValidationError):
        _spec_trade_7(led, **over)
    assert led.get_trade(7).exit_ts is None
    assert raw(path, "SELECT COUNT(*) FROM trade_exits")[0][0] == 0
    # a valid exit still works afterwards
    _spec_trade_7(led)
    assert led.get_trade(7).bars_held == 92


def test_all_excursion_tf_values_accepted(tmp_path):
    led, _ = new_ledger(tmp_path)
    for i, tf in enumerate(("1m", "5m", "15m"), start=1):
        enter(led, i)
        led.record_trade_exit(TradeExit(
            trade_id=i, exit_ts=BASE + timedelta(minutes=15 * i, hours=2),
            exit_price=2010.0, exit_reason="other", planned_exit=None,
            fee_exit=0.0, funding_paid=0.0,
            max_favorable_price=2020.0, max_adverse_price=1990.0, excursion_tf=tf))
        assert led.get_trade(i).excursion_tf == tf


def test_zero_excursions_allowed_and_nonnegative(tmp_path):
    led, _ = new_ledger(tmp_path)
    enter(led, 1)
    led.record_trade_exit(TradeExit(
        trade_id=1, exit_ts=BASE + timedelta(hours=3), exit_price=2010.0,
        exit_reason="other", planned_exit=None, fee_exit=0.0, funding_paid=0.0,
        max_favorable_price=2010.0, max_adverse_price=2000.0, excursion_tf="15m"))
    t = led.get_trade(1)
    assert t.mae_r == 0.0
    assert t.mfe_r == pytest.approx(0.3 * 10 / 13.188, abs=1e-5)


def test_bars_held_negative_impossible_exit_before_entry(tmp_path):
    led, _ = new_ledger(tmp_path)
    enter(led, 1)
    with pytest.raises(LedgerValidationError):
        led.record_trade_exit(TradeExit(
            trade_id=1, exit_ts=BASE, exit_price=2010.0, exit_reason="other",
            planned_exit=None, fee_exit=0.0, funding_paid=0.0))


def test_exit_idempotent_and_conflict_include_new_fields(tmp_path):
    led, _ = new_ledger(tmp_path)
    a = _spec_trade_7(led)
    assert _spec_trade_7(led) == a
    with pytest.raises(LedgerConflictError):
        _spec_trade_7(led, max_favorable_price=2090.0)
    with pytest.raises(LedgerConflictError):
        _spec_trade_7(led, excursion_tf="5m")


def test_v_closed_trades_exposes_excursion(tmp_path):
    led, path = new_ledger(tmp_path)
    _spec_trade_7(led)
    led.close()
    row = raw(path, "SELECT mfe_r, mae_r, bars_held, excursion_tf FROM v_closed_trades "
                    "WHERE trade_id=7")[0]
    assert row[0] == pytest.approx(1.9109, abs=1e-4)
    assert row[2] == 92 and row[3] == "1m"


# ==========================================================================
# v1 -> v2 migration (raw-SQL v1 fixture)
# ==========================================================================

_TABLES_V1 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE schema_migrations (id INTEGER PRIMARY KEY AUTOINCREMENT, from_version INTEGER,
  to_version INTEGER, applied_at TEXT);
CREATE TABLE health_probes (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL
  CHECK (bot IN ('learner','twin')), probed_at TEXT);
CREATE TABLE param_versions (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL
  CHECK (bot IN ('learner','twin')), params TEXT NOT NULL, params_hash TEXT NOT NULL,
  lesson_bounds TEXT NOT NULL, parent_version_id INTEGER, author TEXT NOT NULL,
  reason TEXT NOT NULL, evidence TEXT, proposal_id INTEGER, created_at TEXT NOT NULL);
CREATE TABLE param_activations (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL
  CHECK (bot IN ('learner','twin')), version_id INTEGER NOT NULL, prev_version_id INTEGER,
  kind TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, proposal_id INTEGER,
  activated_at TEXT NOT NULL);
CREATE TABLE lesson_proposals (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL
  CHECK (bot IN ('learner','twin')), base_version_id INTEGER NOT NULL, proposal TEXT NOT NULL,
  claimed_evidence TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE proposal_status_events (id INTEGER PRIMARY KEY AUTOINCREMENT, proposal_id INTEGER
  NOT NULL, status TEXT NOT NULL, code TEXT NOT NULL, reason TEXT NOT NULL, version_id INTEGER,
  actor TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE decision_events (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL
  CHECK (bot IN ('learner','twin')), bar_close_ts TEXT NOT NULL, trigger_tf TEXT NOT NULL,
  pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT NOT NULL, regime TEXT NOT NULL,
  atr_ratio REAL, rh REAL, rl REAL, rh_touches INTEGER NOT NULL, rl_touches INTEGER NOT NULL,
  features TEXT NOT NULL, planned_entry REAL NOT NULL, planned_stop REAL NOT NULL,
  planned_target REAL, param_version_id INTEGER NOT NULL, activation_id INTEGER,
  veto_status TEXT NOT NULL, veto_reason TEXT, risk_allowed INTEGER, risk_reason TEXT,
  size_qty REAL, size_notional REAL, size_margin REAL, size_risk_amount REAL, leverage INTEGER,
  final_action TEXT NOT NULL, skip_reason TEXT, supersedes_id INTEGER, recorded_at TEXT NOT NULL);
CREATE UNIQUE INDEX ux_decision ON decision_events (bot, pair, side, setup, trigger_tf,
  bar_close_ts) WHERE supersedes_id IS NULL;
CREATE TABLE trade_entries (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL
  CHECK (bot IN ('learner','twin')), trade_id INTEGER NOT NULL, decision_id INTEGER NOT NULL,
  param_version_id INTEGER NOT NULL, activation_id INTEGER, pair TEXT, side TEXT, setup TEXT,
  entry_ts TEXT NOT NULL, entry_price REAL NOT NULL, planned_entry REAL, planned_stop REAL,
  planned_target REAL, qty REAL NOT NULL, leverage INTEGER NOT NULL, planned_risk REAL NOT NULL,
  fee_entry REAL NOT NULL, slippage_entry REAL NOT NULL, supersedes_id INTEGER,
  recorded_at TEXT NOT NULL);
CREATE UNIQUE INDEX ux_entry ON trade_entries (bot, trade_id) WHERE supersedes_id IS NULL;
CREATE TABLE trade_exits (id INTEGER PRIMARY KEY AUTOINCREMENT, bot TEXT NOT NULL
  CHECK (bot IN ('learner','twin')), trade_id INTEGER NOT NULL, exit_ts TEXT NOT NULL,
  exit_price REAL NOT NULL, exit_reason TEXT NOT NULL, planned_exit REAL, fee_exit REAL NOT NULL,
  funding_paid REAL NOT NULL, gross_pnl REAL NOT NULL, realized_pnl REAL NOT NULL,
  r_multiple REAL NOT NULL, slippage_exit REAL, supersedes_id INTEGER, recorded_at TEXT NOT NULL);
CREATE UNIQUE INDEX ux_exit ON trade_exits (bot, trade_id) WHERE supersedes_id IS NULL;
"""

_VIEWS_V1 = """
CREATE VIEW v_decisions AS SELECT * FROM decision_events d WHERE NOT EXISTS
  (SELECT 1 FROM decision_events s WHERE s.supersedes_id = d.id);
CREATE VIEW v_trades AS
 SELECT e.trade_id, e.bot, e.decision_id, e.param_version_id, e.activation_id, e.pair, e.side,
  e.setup, d.regime, d.atr_ratio, e.entry_ts, e.entry_price, e.planned_entry, e.planned_stop,
  e.planned_target, e.qty, e.leverage, e.planned_risk, e.fee_entry, e.slippage_entry,
  x.exit_ts, x.exit_price, x.exit_reason, x.planned_exit, x.fee_exit, x.funding_paid,
  x.gross_pnl, x.realized_pnl, x.r_multiple, x.slippage_exit
 FROM trade_entries e JOIN decision_events d ON d.id = e.decision_id
 LEFT JOIN trade_exits x ON x.bot = e.bot AND x.trade_id = e.trade_id
   AND NOT EXISTS (SELECT 1 FROM trade_exits y WHERE y.supersedes_id = x.id)
 WHERE NOT EXISTS (SELECT 1 FROM trade_entries z WHERE z.supersedes_id = e.id);
CREATE VIEW v_closed_trades AS SELECT * FROM v_trades WHERE exit_ts IS NOT NULL;
CREATE VIEW v_proposals AS SELECT p.*, (SELECT status FROM proposal_status_events s
  WHERE s.proposal_id = p.id ORDER BY s.id DESC LIMIT 1) AS status FROM lesson_proposals p;
"""

_V1_TABLES = ["meta", "schema_migrations", "health_probes", "param_versions",
              "param_activations", "lesson_proposals", "proposal_status_events",
              "decision_events", "trade_entries", "trade_exits"]

CANON = ('{"edge_zone_atr":0.25,"pullback_ema":50,"range_target_frac":0.75,'
         '"range_width_atr":4.0,"rr_min":1.5,"stop_buffer_atr":0.3,"trail_atr":3.0,'
         '"trigger_tf":"1h","vol_ratio_max":1.5}')
HASH = "de6ff80013f1ae38fbe23322363fb0d0d6aa031569ef22ac2e7efd03da1c0514"
BOUNDS = ('{"range_target_frac":[0.6,0.9],"rr_min":[1.2,2.0],"stop_buffer_atr":[0.2,0.5],'
          '"trail_atr":[2.5,3.5],"vol_ratio_max":[1.3,1.7]}')


def build_v1(path, bot="learner"):
    con = sqlite3.connect(str(path))
    con.executescript(_TABLES_V1)
    trig = ""
    for t in _V1_TABLES:
        trig += (f"CREATE TRIGGER trg_{t}_no_update BEFORE UPDATE ON {t} "
                 f"BEGIN SELECT RAISE(ABORT,'append-only'); END;\n"
                 f"CREATE TRIGGER trg_{t}_no_delete BEFORE DELETE ON {t} "
                 f"BEGIN SELECT RAISE(ABORT,'append-only'); END;\n")
    con.executescript(trig)
    con.executescript(_VIEWS_V1)
    ts = "2026-12-01T09:00:00.000Z"
    con.execute("INSERT INTO meta VALUES ('bot', ?)", (bot,))
    con.execute("INSERT INTO meta VALUES ('created_at', ?)", (ts,))
    con.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    con.execute("INSERT INTO schema_migrations (from_version,to_version,applied_at) "
                "VALUES (0,1,?)", (ts,))
    con.execute("INSERT INTO param_versions (bot,params,params_hash,lesson_bounds,author,"
                "reason,created_at) VALUES (?,?,?,?, 'initial','init',?)",
                (bot, CANON, HASH, BOUNDS, ts))
    con.execute("INSERT INTO param_activations (bot,version_id,prev_version_id,kind,actor,"
                "reason,activated_at) VALUES (?,1,NULL,'initial','system','init',?)", (bot, ts))
    feats = json.dumps({"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5,
                        "rr": 2.5, "edge_dist_atr": 0.1}, sort_keys=True, separators=(",", ":"))
    con.execute(
        "INSERT INTO decision_events (bot,bar_close_ts,trigger_tf,pair,side,setup,regime,"
        "atr_ratio,rh,rl,rh_touches,rl_touches,features,planned_entry,planned_stop,"
        "planned_target,param_version_id,activation_id,veto_status,risk_allowed,risk_reason,"
        "size_qty,size_notional,size_margin,size_risk_amount,leverage,final_action,recorded_at)"
        " VALUES (?, '2026-12-01T10:00:00.000Z','1h','ETH/USDT','long','R1','range',1.1,2100,"
        "1980,2,3,?,2000,1960,2100,1,1,'allowed',1,'ok',0.3,600,200,13.188,3,'entered',"
        "'2026-12-01T10:00:00.000Z')", (bot, feats))
    con.execute(
        "INSERT INTO trade_entries (bot,trade_id,decision_id,param_version_id,activation_id,"
        "pair,side,setup,entry_ts,entry_price,planned_entry,planned_stop,planned_target,qty,"
        "leverage,planned_risk,fee_entry,slippage_entry,recorded_at) VALUES (?,7,1,1,1,"
        "'ETH/USDT','long','R1','2026-12-01T10:00:03.000Z',2001,2000,1960,2100,0.3,3,13.188,"
        "0.30015,0.0005,'2026-12-01T10:00:03.000Z')", (bot,))
    con.execute(
        "INSERT INTO trade_exits (bot,trade_id,exit_ts,exit_price,exit_reason,planned_exit,"
        "fee_exit,funding_paid,gross_pnl,realized_pnl,r_multiple,slippage_exit,recorded_at) "
        "VALUES (?,7,'2026-12-02T09:00:00.000Z',2079,'target',2100,0.31185,0.1,23.4,22.688,"
        "?,0.01,'2026-12-02T09:00:00.000Z')", (bot, 22.688 / 13.188))
    con.execute("PRAGMA user_version = 1")
    con.commit()
    con.close()


def snapshot(path):
    out = {}
    for t in _V1_TABLES:
        out[t] = raw(path, f"SELECT * FROM {t} ORDER BY id" if t != "meta"
                     else "SELECT * FROM meta ORDER BY key")
    return out


def test_v1_fixture_sanity(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    assert raw(p, "PRAGMA user_version")[0][0] == 1
    assert "mfe_r" not in cols(p, "trade_exits")


def test_v1_open_without_migrate_rejected(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    with pytest.raises(LedgerSchemaError):
        open_ledger(p, "learner", migrate=False, clock=clock)
    assert raw(p, "PRAGMA user_version")[0][0] == 1


def test_v1_read_only_never_migrates(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    with pytest.raises(LedgerSchemaError):
        open_ledger(p, "learner", create=False, read_only=True, migrate=False, clock=clock)
    assert raw(p, "PRAGMA user_version")[0][0] == 1
    assert not os.path.exists(str(p) + ".premigrate-v1")


def test_v1_migration_preserves_data_and_upgrades(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    before = snapshot(p)
    led = open_ledger(p, "learner", migrate=True, clock=clock)
    assert os.path.exists(str(p) + ".premigrate-v1")
    assert raw(str(p) + ".premigrate-v1", "PRAGMA user_version")[0][0] == 1
    assert raw(p, "PRAGMA user_version")[0][0] == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    c = cols(p, "trade_exits")
    for name in ("mfe_r", "mae_r", "bars_held", "excursion_tf"):
        assert name in c
    # old rows untouched (compare the common leading columns; new ones are NULL)
    after = snapshot(p)
    for t in _V1_TABLES:
        if t == "schema_migrations":
            assert after[t][: len(before[t])] == before[t]
            continue
        n = len(before[t][0]) if before[t] else 0
        assert [r[:n] for r in after[t]] == before[t], t
    assert raw(p, "SELECT mfe_r, mae_r, bars_held, excursion_tf FROM trade_exits")[0] == \
        (None, None, None, None)
    assert (1, 2) in raw(p, "SELECT from_version, to_version FROM schema_migrations")
    # view and API see new cols, old values unchanged
    vc = cols(p, "v_closed_trades")
    for name in ("mfe_r", "mae_r", "bars_held", "excursion_tf"):
        assert name in vc
    t = led.get_trade(7)
    assert t.r_multiple == pytest.approx(22.688 / 13.188)
    assert t.mfe_r is None and t.mae_r is None and t.bars_held is None
    assert t.excursion_tf is None
    assert led.get_active_params().version_id == 1
    assert led.entries_allowed().ok in (True, False)  # must not raise
    led.close()


def test_v1_migration_keeps_append_only_triggers(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    open_ledger(p, "learner", migrate=True, clock=clock).close()
    con = sqlite3.connect(str(p))
    for table in ("trade_exits", "trade_entries", "decision_events", "param_versions",
                  "param_activations"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute(f"UPDATE {table} SET bot=bot")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute(f"DELETE FROM {table}")
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert "trg_trade_exits_excursion_check" in names
    con.close()


def test_v1_migration_idempotent(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    open_ledger(p, "learner", migrate=True, clock=clock).close()
    snap = snapshot(p)
    bak = str(p) + ".premigrate-v1"
    bak_mtime = os.path.getmtime(bak)
    open_ledger(p, "learner", migrate=True, clock=clock).close()
    open_ledger(p, "learner", migrate=False, clock=clock).close()
    assert snapshot(p) == snap
    assert raw(p, "SELECT COUNT(*) FROM schema_migrations WHERE from_version=1 "
                  "AND to_version=2")[0][0] == 1
    assert raw(p, "PRAGMA user_version")[0][0] == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert os.path.getmtime(bak) == bak_mtime


def test_v1_migration_atomic_on_midway_failure(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    con = sqlite3.connect(str(p))
    # name collision makes the 10.1 step-1 CREATE TRIGGER fail after the ALTERs
    con.execute("CREATE TRIGGER trg_trade_exits_excursion_check BEFORE DELETE ON health_probes "
                "BEGIN SELECT 1; END")
    con.commit()
    con.close()
    before = snapshot(p)
    with pytest.raises(LedgerError):
        open_ledger(p, "learner", migrate=True, clock=clock)
    assert raw(p, "PRAGMA user_version")[0][0] == 1
    c = cols(p, "trade_exits")
    for name in ("mfe_r", "mae_r", "bars_held", "excursion_tf"):
        assert name not in c
    assert snapshot(p) == before
    assert "mfe_r" not in cols(p, "v_trades")
    # views still intact
    assert raw(p, "SELECT COUNT(*) FROM v_closed_trades")[0][0] == 1


def test_migrated_db_accepts_v2_exit_fields(tmp_path):
    p = tmp_path / "v1.sqlite"
    build_v1(p)
    led = open_ledger(p, "learner", migrate=True, clock=clock)
    enter(led, 9, bar=BASE + timedelta(hours=11))
    led.record_trade_exit(TradeExit(
        trade_id=9, exit_ts=BASE + timedelta(hours=13), exit_price=2010.0,
        exit_reason="other", planned_exit=None, fee_exit=0.0, funding_paid=0.0,
        max_favorable_price=2020.0, max_adverse_price=1990.0, excursion_tf="1m"))
    t = led.get_trade(9)
    assert t.mfe_r == pytest.approx(0.3 * 20 / 13.188, abs=1e-5)
    assert t.excursion_tf == "1m"
    assert led.get_trade(7).mfe_r is None
    led.close()


def test_user_version_5_and_0_rejected(tmp_path):
    led, path = new_ledger(tmp_path)
    led.close()
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA user_version=9")
    con.commit()
    con.close()
    with pytest.raises(LedgerSchemaError):
        open_ledger(path, "learner", clock=clock)
    con = sqlite3.connect(str(path))
    con.execute("PRAGMA user_version = 0")
    con.commit()
    con.close()
    with pytest.raises(LedgerSchemaError):
        open_ledger(path, "learner", migrate=False, clock=clock)


# ==========================================================================
# pooled evidence (5.4) and pool_version_ids
# ==========================================================================

def _versions(led):
    """v1 default; v2 rr_min=1.25 (R1 only); returns ids."""
    v2 = user_version(led, None, 1, rr_min=1.25)
    return v2


def test_pool_equal_versions_pool_together(tmp_path):
    led, _ = new_ledger(tmp_path)
    # identical params, different lesson_bounds => distinct version with equal params
    v2 = led.create_user_version(P(), reason="same params",
                                 lesson_bounds=ALT_BOUNDS)
    assert led.pool_version_ids(1, "trail_atr") == (1, v2)
    assert led.pool_version_ids(1, "rr_min") == (1, v2)
    assert led.pool_version_ids(v2, "rr_min") == (1, v2)


def test_pool_disjoint_scope_difference_pools(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = _versions(led)  # rr_min (R1) differs
    assert led.pool_version_ids(2, "trail_atr") == (1, v2)  # T1 key: R1 change is unrelated
    assert led.pool_version_ids(1, "trail_atr") == (1, v2)  # symmetric
    # key = rr_min itself differs => no pooling
    assert led.pool_version_ids(v2, "rr_min") == (v2,)
    assert led.pool_version_ids(1, "rr_min") == (1,)
    # range_target_frac is R1-scope; rr_min is R1 => intersecting => separated
    assert led.pool_version_ids(v2, "range_target_frac") == (v2,)
    # vol_ratio_max T1+R1 intersects rr_min R1
    assert led.pool_version_ids(v2, "vol_ratio_max") == (v2,)
    assert led.pool_version_ids(v2, "stop_buffer_atr") == (v2,)


def test_pool_t1_change_does_not_pool_for_r1_key_but_does_symmetrically(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = user_version(led, None, 1, trail_atr=3.5)  # T1 param
    assert led.pool_version_ids(v2, "rr_min") == (1, v2)
    assert led.pool_version_ids(v2, "range_target_frac") == (1, v2)
    assert led.pool_version_ids(v2, "trail_atr") == (v2,)
    assert led.pool_version_ids(v2, "vol_ratio_max") == (v2,)


def test_pool_shared_scope_param_change_resets_both_scopes(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = user_version(led, None, 1, vol_ratio_max=1.4)
    for key in ("trail_atr", "rr_min", "range_target_frac", "stop_buffer_atr"):
        assert led.pool_version_ids(v2, key) == (v2,), key


def test_pool_closed_params_always_split(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = user_version(led, None, 1, range_width_atr=4.5)
    v3 = user_version(led, None, 1, pullback_ema=20)
    v4 = user_version(led, None, 1, trigger_tf="15m")
    v5 = user_version(led, None, 1, edge_zone_atr=0.3)
    for v in (v2, v3, v4, v5):
        for key in ("trail_atr", "rr_min"):
            assert led.pool_version_ids(v, key) == (v,)
            assert led.pool_version_ids(1, key) == (1,)


def test_pool_non_lesson_param_and_unknown(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = user_version(led, None, 1, trail_atr=3.5)
    # non-lesson key => scope T1+R1: only identical-params versions
    assert led.pool_version_ids(v2, "range_width_atr") == (v2,)
    v3 = led.create_user_version(P(trail_atr=3.5), reason="dup", lesson_bounds=ALT_BOUNDS)
    assert led.pool_version_ids(v2, "range_width_atr") == (v2, v3)
    with pytest.raises(LedgerValidationError):
        led.pool_version_ids(1, "max_leverage")


def test_pool_sorted_includes_base(tmp_path):
    led, _ = new_ledger(tmp_path)
    ids = [user_version(led, None, 1, rr_min=r) for r in (1.25, 1.75, 2.0)]
    res = led.pool_version_ids(ids[-1], "trail_atr")
    assert list(res) == sorted(res)
    assert ids[-1] in res and 1 in res and len(res) == 4


def test_pooled_apply_t1_counts_across_r1_only_change(tmp_path):
    """Spec 12.7 pattern: R1 param change must not reset T1 evidence."""
    led, path = new_ledger(tmp_path)
    for i in range(1, 16):
        closed_trade(led, i, "T1", 1)
    v2 = _versions(led)
    for i in range(16, 24):
        closed_trade(led, i, "T1", v2)
    res = led.propose_change(base_version_id=v2, changes={"trail_atr": 3.5}, rationale="r",
                             claimed_evidence={"n_closed": 1}, source="test")
    assert res.status == "proposed"
    ap = led.apply_proposal(res.proposal_id, actor="lesson", reason="go")
    assert ap.ok, ap
    ev = json.loads(raw(path, "SELECT evidence FROM param_versions WHERE id=?",
                        (ap.version_id,))[0][0])
    assert ev["n_closed"] == 23
    assert ev["scope"] == "T1+H2+S1+TF1"      # 24.11: kapsam = trail_atr okuyan kurulumlar
    assert ev["pooled_version_ids"] == [1, v2]
    assert ev["n_by_version"] == {"1": 15, "2": 8}
    assert ev["claimed_mismatch"] is True
    # same trades, unpooled, would have been 8 < 20: prove via version-exact count
    assert led.count_closed_trades(version_id=v2, setup="T1") == 8


def test_pooled_apply_insufficient_without_enough_across_pool(tmp_path):
    led, path = new_ledger(tmp_path)
    for i in range(1, 8):
        closed_trade(led, i, "T1", 1)
    v2 = _versions(led)
    for i in range(8, 13):
        closed_trade(led, i, "T1", v2)       # 12 < 20 total
    res = led.propose_change(base_version_id=v2, changes={"trail_atr": 3.5}, rationale="r",
                             claimed_evidence={"n_closed": 99}, source="t")
    n_events = raw(path, "SELECT COUNT(*) FROM proposal_status_events")[0][0]
    ap = led.apply_proposal(res.proposal_id, actor="lesson", reason="go")
    assert not ap.ok and ap.code == "insufficient_evidence"
    assert raw(path, "SELECT COUNT(*) FROM proposal_status_events")[0][0] == n_events
    assert last_status(path, res.proposal_id)[0] == "proposed"


def test_related_param_change_resets_evidence(tmp_path):
    led, path = new_ledger(tmp_path)
    for i in range(1, 26):
        closed_trade(led, i, "R1", 1)       # plenty of R1 evidence under v1
    v2 = _versions(led)                     # rr_min changed => R1 evidence reset
    res = led.propose_change(base_version_id=v2, changes={"rr_min": 1.5}, rationale="r",
                             claimed_evidence={}, source="t")
    assert res.status == "proposed"
    ap = led.apply_proposal(res.proposal_id, actor="lesson", reason="go")
    assert not ap.ok and ap.code == "insufficient_evidence"
    # shared-scope key also reset by the rr_min change (T1+R1 intersect R1)
    for i in range(100, 125):
        closed_trade(led, i, "T1", 1)
    res2 = led.propose_change(base_version_id=v2, changes={"vol_ratio_max": 1.3},
                              rationale="r", claimed_evidence={}, source="t")
    ap2 = led.apply_proposal(res2.proposal_id, actor="lesson", reason="go")
    assert not ap2.ok and ap2.code == "insufficient_evidence"


def test_rollback_recombines_pool(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = _versions(led)
    assert led.pool_version_ids(v2, "rr_min") == (v2,)
    rb = led.rollback(1, actor="user", reason="back")
    assert rb.ok
    assert led.pool_version_ids(1, "rr_min") == (1,)
    assert led.pool_version_ids(1, "trail_atr") == (1, v2)


# ==========================================================================
# require_user (5.3 rule 11)
# ==========================================================================

def _t1_evidence(led, n=20, ver=1, start=1):
    for i in range(start, start + n):
        closed_trade(led, i, "T1", ver)


def test_require_user_forces_needs_user_and_blocks_lesson_apply(tmp_path):
    led, path = new_ledger(tmp_path)
    _t1_evidence(led)
    res = led.propose_change(base_version_id=1, changes={"trail_atr": 3.5}, rationale="r",
                             claimed_evidence={}, source="t", require_user=True)
    assert res.status == "needs_user"
    assert res.code == "user_approval_required"
    assert last_status(path, res.proposal_id)[0] == "needs_user"
    ap = led.apply_proposal(res.proposal_id, actor="lesson", reason="x")
    assert not ap.ok and ap.code == "user_approval_required"
    assert last_status(path, res.proposal_id)[0] == "needs_user"
    assert raw(path, "SELECT COUNT(*) FROM param_versions")[0][0] == 1
    ap2 = led.apply_proposal(res.proposal_id, actor="user", reason="ok")
    assert ap2.ok
    assert last_status(path, res.proposal_id)[0] == "applied"
    assert raw(path, "SELECT author FROM param_versions WHERE id=?", (ap2.version_id,))[0][0] \
        == "lesson"
    assert raw(path, "SELECT actor, kind FROM param_activations ORDER BY id DESC LIMIT 1")[0] \
        == ("user", "apply")


def test_require_user_false_is_plain_proposed(tmp_path):
    led, _ = new_ledger(tmp_path)
    res = led.propose_change(base_version_id=1, changes={"trail_atr": 3.5}, rationale="r",
                             claimed_evidence={}, source="t", require_user=False)
    assert res.status == "proposed"


def test_require_user_does_not_override_rejections(tmp_path):
    led, _ = new_ledger(tmp_path)
    cases = [
        ({"trail_atr": 4.0}, "out_of_bounds"),
        ({"stop_buffer_atr": 0.5}, "step_too_large"),
        ({"rr_min": 1.5}, "no_change"),
        ({"range_width_atr": 3.5}, "immutable_param"),
        ({"rr_min": 1.25, "trail_atr": 3.5}, "multiple_changes"),
        ({"max_leverage": 4}, "unknown_param"),
        ({}, "empty_changes"),
    ]
    for changes, code in cases:
        r = led.propose_change(base_version_id=1, changes=changes, rationale="r",
                               claimed_evidence={}, source="t", require_user=True)
        assert r.status == "rejected" and r.code == code, (changes, r)
    r = led.propose_change(base_version_id=9, changes={"trail_atr": 3.5}, rationale="r",
                           claimed_evidence={}, source="t", require_user=True)
    assert r.status == "rejected" and r.code == "stale_base"


def test_vol_ratio_loosening_code_needs_user_even_with_require_user(tmp_path):
    led, _ = new_ledger(tmp_path)
    r1 = led.propose_change(base_version_id=1, changes={"vol_ratio_max": 1.7}, rationale="r",
                            claimed_evidence={}, source="t")
    assert r1.status == "needs_user" and r1.code == "needs_user"
    r2 = led.propose_change(base_version_id=1, changes={"vol_ratio_max": 1.7}, rationale="r",
                            claimed_evidence={}, source="t", require_user=True)
    assert r2.status == "needs_user" and r2.code == "needs_user"   # both => needs_user
    r3 = led.propose_change(base_version_id=1, changes={"vol_ratio_max": 1.3}, rationale="r",
                            claimed_evidence={}, source="t", require_user=True)
    assert r3.status == "needs_user" and r3.code == "user_approval_required"


def test_user_approval_rechecks_evidence(tmp_path):
    led, path = new_ledger(tmp_path)
    res = led.propose_change(base_version_id=1, changes={"trail_atr": 3.5}, rationale="r",
                             claimed_evidence={"n_closed": 50}, source="t", require_user=True)
    ap = led.apply_proposal(res.proposal_id, actor="user", reason="ok")
    assert not ap.ok and ap.code == "insufficient_evidence"
    assert last_status(path, res.proposal_id)[0] == "needs_user"


def test_require_user_twin_forbidden(tmp_path):
    led, path = new_ledger(tmp_path, bot="twin")
    with pytest.raises(LedgerStateError):
        led.propose_change(base_version_id=1, changes={"trail_atr": 3.5}, rationale="r",
                           claimed_evidence={}, source="t", require_user=True)
    assert raw(path, "SELECT COUNT(*) FROM lesson_proposals")[0][0] == 0


# ==========================================================================
# trades_for_versions / aggregate_trades(version_ids=)
# ==========================================================================

def _mixed(led):
    v2 = _versions(led)
    closed_trade(led, 1, "T1", 1, win=True, exit_after_min=300)    # exits last of v1
    closed_trade(led, 2, "R1", 1, win=False, exit_after_min=60)
    closed_trade(led, 3, "T1", v2, win=True, exit_after_min=120)
    closed_trade(led, 4, "R1", v2, win=True, exit_after_min=45)
    enter(led, 5, "T1", v2)                                         # open
    return v2


def test_trades_for_versions_order_and_filters(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = _mixed(led)
    got = led.trades_for_versions([1, v2])
    # exit_ts: t4 = bar4+45m+3s (=105m+3s), t2 = bar2+60m (=90m), t3 = bar3+120m (=165m),
    # t1 = bar1+300m (=315m)  [bar_n = 15n min]
    assert [t.trade_id for t in got] == [2, 4, 3, 1]
    assert [t.trade_id for t in led.trades_for_versions([v2])] == [4, 3]
    assert [t.trade_id for t in led.trades_for_versions([1, v2], setup="T1")] == [3, 1]
    assert [t.trade_id for t in led.trades_for_versions([1, v2], closed_only=False)
            if t.exit_ts is None] == [5]
    assert led.trades_for_versions([]) == []
    cutoff = BASE + timedelta(minutes=100)  # between t2 (90m) and t4 (105m)
    assert [t.trade_id for t in led.trades_for_versions([1, v2], until_ts=cutoff)] == [2]


def test_trades_for_versions_tie_break_by_trade_id(tmp_path):
    led, _ = new_ledger(tmp_path)
    # same exit instant for ids 4 and 2: bar4 + 0 = bar2 + 30m
    for tid, after in ((4, 60), (2, 90)):
        bar = BASE + timedelta(minutes=15 * tid)
        enter(led, tid, "T1", 1, bar)
    x = BASE + timedelta(hours=4)
    for tid in (4, 2):
        led.record_trade_exit(TradeExit(trade_id=tid, exit_ts=x, exit_price=2010.0,
                                        exit_reason="other", planned_exit=None,
                                        fee_exit=0.0, funding_paid=0.0))
    assert [t.trade_id for t in led.trades_for_versions([1])] == [2, 4]


def test_trades_for_versions_unknown_version(tmp_path):
    led, _ = new_ledger(tmp_path)
    with pytest.raises(LedgerValidationError):
        led.trades_for_versions([1, 99])


def test_aggregate_version_ids(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = _mixed(led)
    rows = led.aggregate_trades(["setup"], version_ids=[1, v2])
    by = {r.key["setup"]: r for r in rows}
    assert [r.key["setup"] for r in rows] == ["R1", "T1"]
    assert by["T1"].n == 2 and by["T1"].wins == 2
    assert by["T1"].sum_r == pytest.approx(2.0, abs=1e-6)
    assert by["R1"].n == 2 and by["R1"].wins == 1
    assert by["R1"].sum_r == pytest.approx(0.0, abs=1e-6)
    assert by["R1"].win_rate == pytest.approx(0.5)
    assert by["R1"].mean_r == pytest.approx(0.0, abs=1e-6)
    only2 = led.aggregate_trades(["setup"], version_ids=[v2])
    assert {r.key["setup"]: r.n for r in only2} == {"R1": 1, "T1": 1}
    both_by_ver = led.aggregate_trades(["param_version_id"], version_ids=[1, v2])
    assert [(r.key["param_version_id"], r.n) for r in both_by_ver] == [(1, 2), (v2, 2)]


def test_aggregate_version_ids_excludes_open_and_empty(tmp_path):
    led, _ = new_ledger(tmp_path)
    v2 = _mixed(led)
    rows = led.aggregate_trades(["side"], version_ids=[v2])
    assert sum(r.n for r in rows) == 2          # open trade 5 excluded
    assert led.aggregate_trades(["side"], version_ids=[]) == []


def test_aggregate_version_ids_conflicts_with_version_id(tmp_path):
    led, _ = new_ledger(tmp_path)
    with pytest.raises(LedgerValidationError):
        led.aggregate_trades(["setup"], version_id=1, version_ids=[1])
    with pytest.raises(LedgerValidationError):
        led.aggregate_trades(["setup"], version_ids=[99])


def test_aggregate_hand_example_12_5_with_version_ids(tmp_path):
    led, _ = new_ledger(tmp_path)
    # A: T1 +2R  (exit = 2000 + 2*43.96), B: T1 short -1R, C: R1 +0.5R
    enter(led, 1, "T1", 1)
    led.record_trade_exit(TradeExit(trade_id=1, exit_ts=BASE + timedelta(hours=5),
                                    exit_price=2000 + 2 * 43.96, exit_reason="other",
                                    planned_exit=None, fee_exit=0.0, funding_paid=0.0))
    enter(led, 2, "T1", 1, side="short")
    led.record_trade_exit(TradeExit(trade_id=2, exit_ts=BASE + timedelta(hours=5),
                                    exit_price=2000 + 43.96, exit_reason="other",
                                    planned_exit=None, fee_exit=0.0, funding_paid=0.0))
    enter(led, 3, "R1", 1)
    led.record_trade_exit(TradeExit(trade_id=3, exit_ts=BASE + timedelta(hours=5),
                                    exit_price=2000 + 0.5 * 43.96, exit_reason="other",
                                    planned_exit=None, fee_exit=0.0, funding_paid=0.0))
    rows = led.aggregate_trades(["setup"], version_ids=[1])
    assert [r.key["setup"] for r in rows] == ["R1", "T1"]
    t1, r1 = rows[1], rows[0]
    assert (t1.n, t1.wins) == (2, 1)
    assert t1.win_rate == pytest.approx(0.5)
    assert t1.sum_r == pytest.approx(1.0, abs=1e-6)
    assert t1.mean_r == pytest.approx(0.5, abs=1e-6)
    assert t1.median_r == pytest.approx(0.5, abs=1e-6)
    assert (r1.n, r1.wins) == (1, 1)
    assert r1.sum_r == pytest.approx(0.5, abs=1e-6)
    assert r1.sum_pnl == pytest.approx(0.3 * 0.5 * 43.96, abs=1e-6)


# ==========================================================================
# twin read-only open (10.2) and twin rules
# ==========================================================================

def _twin_with_data(tmp_path):
    led, path = new_ledger(tmp_path, bot="twin")
    closed_trade(led, 1, "T1", 1)
    led.close()
    return path


def test_twin_read_only_reads_but_cannot_write(tmp_path):
    path = _twin_with_data(tmp_path)
    ro = open_ledger(path, "twin", create=False, read_only=True, migrate=False)
    assert ro.get_active_params().version_id == 1
    assert ro.get_trade(1).realized_pnl == pytest.approx(13.188, abs=1e-6)
    assert len(ro.list_decisions()) == 1
    assert ro.count_closed_trades(version_id=1) == 1
    assert ro.pool_version_ids(1, "trail_atr") == (1,)
    assert len(ro.trades_for_versions([1])) == 1
    assert ro.aggregate_trades(["setup"], version_ids=[1])[0].n == 1

    writes = [
        lambda: ro.record_decision(mk_decision(bar=BASE + timedelta(days=3))),
        lambda: ro.record_trade_entry(TradeEntry(trade_id=2, decision_id=1, entry_ts=NOW,
                                                 entry_price=2000.0, qty=0.3, leverage=3,
                                                 fee_entry=0.0)),
        lambda: ro.record_trade_exit(TradeExit(trade_id=1, exit_ts=NOW, exit_price=2010.0,
                                               exit_reason="other", planned_exit=None,
                                               fee_exit=0.0, funding_paid=0.0)),
        lambda: ro.init_params(DEFAULT_PARAMS, reason="x"),
        lambda: ro.create_user_version(P(trail_atr=3.5), reason="x"),
        lambda: ro.activate_version(1, actor="user", reason="x"),
        lambda: ro.propose_change(base_version_id=1, changes={"trail_atr": 3.5},
                                  rationale="r", claimed_evidence={}, source="t"),
        lambda: ro.apply_proposal(1, actor="user", reason="x"),
        lambda: ro.reject_proposal(1, actor="user", reason="x"),
        lambda: ro.rollback(1, actor="user", reason="x"),
    ]
    snap = snapshot(path)
    for w in writes:
        with pytest.raises(LedgerStateError):
            w()
    ro.close()
    assert snapshot(path) == snap


def test_twin_read_only_sees_only_twin_data(tmp_path):
    learner, lpath = new_ledger(tmp_path, bot="learner")
    for i in range(1, 6):
        closed_trade(learner, i, "T1", 1)
    twin, tpath = new_ledger(tmp_path, bot="twin")
    closed_trade(twin, 1, "R1", 1)
    twin.close()
    ro = open_ledger(tpath, "twin", create=False, read_only=True, migrate=False)
    assert ro.count_closed_trades(version_id=1) == 1
    assert ro.count_closed_trades(version_id=1, setup="T1") == 0
    assert [t.setup for t in ro.trades_for_versions([1])] == ["R1"]
    # learner keeps writing; twin RO connection unaffected by learner file
    closed_trade(learner, 6, "T1", 1)
    assert ro.count_closed_trades(version_id=1) == 1
    ro.close()
    learner.close()


def test_twin_read_only_open_failure_modes(tmp_path):
    missing = tmp_path / "nope.sqlite"
    with pytest.raises(LedgerSchemaError):
        open_ledger(missing, "twin", create=False, read_only=True, migrate=False)
    assert not missing.exists()
    # twin file still schema 1 => LedgerSchemaError (lesson service treats as "no twin")
    v1 = tmp_path / "twin_v1.sqlite"
    build_v1(v1, bot="twin")
    with pytest.raises(LedgerSchemaError):
        open_ledger(v1, "twin", create=False, read_only=True, migrate=False)
    assert raw(v1, "PRAGMA user_version")[0][0] == 1
    # bot mismatch
    path = _twin_with_data(tmp_path)
    with pytest.raises(LedgerSchemaError):
        open_ledger(path, "learner", create=False, read_only=True, migrate=False)


def test_twin_read_write_still_forbids_lesson_paths(tmp_path):
    led, path = new_ledger(tmp_path, bot="twin")
    with pytest.raises(LedgerStateError):
        led.propose_change(base_version_id=1, changes={"trail_atr": 3.5}, rationale="r",
                           claimed_evidence={}, source="t")
    with pytest.raises(LedgerStateError):
        led.rollback(1, actor="user", reason="x")
    with pytest.raises(LedgerStateError):
        led.create_user_version(P(trail_atr=3.5), reason="x")
    # decisions/trades (incl. v2 exit fields) are allowed on twin
    enter(led, 1)
    led.record_trade_exit(TradeExit(
        trade_id=1, exit_ts=BASE + timedelta(hours=3), exit_price=2010.0, exit_reason="other",
        planned_exit=None, fee_exit=0.0, funding_paid=0.0,
        max_favorable_price=2020.0, max_adverse_price=1995.0, excursion_tf="15m"))
    assert led.get_trade(1).mfe_r == pytest.approx(0.3 * 20 / 13.188, abs=1e-5)


def test_read_only_learner_write_raises_state_error(tmp_path):
    led, path = new_ledger(tmp_path)
    led.close()
    ro = open_ledger(path, "learner", create=False, read_only=True, migrate=False)
    with pytest.raises(LedgerStateError):
        ro.record_decision(mk_decision())
    ro.close()


def test_min_evidence_floor_unchanged(tmp_path):
    with pytest.raises(LedgerValidationError):
        open_ledger(tmp_path / "a.sqlite", "learner", min_evidence_trades=10, clock=clock)
