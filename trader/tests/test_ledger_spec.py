"""Spec-driven tests for trader_core.ledger (docs/defter-spec.md v1).

Written from the spec only; independent of the implementation.
Root-safe: file permission tricks do not work for uid 0, so write failures are
simulated with a foreign write lock (raw sqlite3 connection), os.statvfs
patching, closed connections and read-only opens.
"""
import contextlib
import dataclasses
import hashlib
import json
import math
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import pytest

from trader_core import ledger as L

UTC = timezone.utc
BASE = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
EX_TS = datetime(2026, 12, 1, 10, 0, tzinfo=UTC)  # spec 12.2 candle close

PARAMS = {
    "range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25,
    "pullback_ema": 50, "stop_buffer_atr": 0.3, "trail_atr": 3.0,
    "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h",
}
HASH0 = "de6ff80013f1ae38fbe23322363fb0d0d6aa031569ef22ac2e7efd03da1c0514"
HASH_RR125 = "dc7f7c8cc75741d8b0673da580efecfcea977006d88b4bed12949ff011d7a3bf"

F_R1 = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0,
        "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.2}
F_T1 = {"atr_1h": 20.0, "stop_dist_atr": 1.0, "atr_4h": 40.0,
        "pullback_ema": 50, "ema_value": 99.0, "body_ratio": 0.6}


# ----------------------------------------------------------------- helpers
class Clock:
    def __init__(self, now=datetime(2026, 12, 1, 10, 0, 5, tzinfo=UTC)):
        self.now = now

    def __call__(self):
        return self.now

    def set(self, dt):
        self.now = dt

    def advance(self, **kw):
        self.now = self.now + timedelta(**kw)


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False)


def raw(path, sql, args=()):
    c = sqlite3.connect(str(path))
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


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


def failed(fn):
    """True if fn raises a LedgerError or returns a result with ok=False."""
    try:
        r = fn()
    except L.LedgerError:
        return True
    return getattr(r, "ok", True) is False


def dec(**over):
    base = dict(
        bar_close_ts=EX_TS, trigger_tf="1h", pair="ETH/USDT", side="long",
        setup="R1", regime="range", atr_ratio=1.1, rh=2100.0, rl=1980.0,
        rh_touches=2, rl_touches=3, features=dict(F_R1),
        planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0,
        param_version_id=1, veto_status="allowed", veto_reason=None,
        risk_allowed=True, risk_reason="ok", size_qty=0.3,
        size_notional=600.0, size_margin=200.0, size_risk_amount=13.188,
        leverage=3, final_action="entered", skip_reason=None,
    )
    base.update(over)
    return L.DecisionEvent(**base)


def skipped(**over):
    base = dict(veto_status="not_evaluated", risk_allowed=None, risk_reason=None,
                size_qty=None, size_notional=None, size_margin=None,
                size_risk_amount=None, leverage=None, final_action="skipped",
                skip_reason="rr_below_min")
    base.update(over)
    return dec(**base)


def t1_short(**over):
    base = dict(setup="T1", side="short", regime="trend_down", atr_ratio=1.0,
                rh=None, rl=None, rh_touches=0, rl_touches=0,
                features=dict(F_T1), planned_entry=100.0, planned_stop=101.0,
                planned_target=None, size_qty=10.0, size_notional=1000.0,
                size_margin=333.0, size_risk_amount=12.01)
    base.update(over)
    return dec(**base)


def entry(trade_id=7, decision_id=1, **over):
    kw = dict(trade_id=trade_id, decision_id=decision_id,
              entry_ts=datetime(2026, 12, 1, 10, 0, 3, tzinfo=UTC),
              entry_price=2001.0, qty=0.3, leverage=3, fee_entry=0.30015)
    kw.update(over)
    return L.TradeEntry(**kw)


def xit(trade_id=7, **over):
    kw = dict(trade_id=trade_id,
              exit_ts=datetime(2026, 12, 2, 9, 0, 0, tzinfo=UTC),
              exit_price=2079.0, exit_reason="target", planned_exit=2100.0,
              fee_exit=0.31185, funding_paid=0.1)
    kw.update(over)
    return L.TradeExit(**kw)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def dbpath(tmp_path):
    return tmp_path / "ledger_learner.sqlite"


@pytest.fixture
def led(dbpath, clock):
    lg = L.open_ledger(dbpath, "learner", clock=clock)
    yield lg
    lg.close()


@pytest.fixture
def lp(led):
    """learner ledger with params initialised (version 1)."""
    assert led.init_params(PARAMS, reason="init") == 1
    return led


class Filler:
    """Creates decision+entry(+exit) triples with hand-picked numbers."""

    def __init__(self, led):
        self.led = led
        self.n = 100

    def add(self, *, setup="R1", side="long", version=1, pnl=10.0, risk=10.0,
            close=True, fee_entry=0.0, fee_exit=0.0, funding=0.0,
            planned_exit=None, reason="manual", trade_id=None, pair="ETH/USDT",
            entry_ts=None, exit_ts=None):
        self.n += 1
        tid = trade_id or self.n
        bar = BASE + timedelta(minutes=15 * tid)
        if setup == "R1":
            regime, extra = "range", dict(rh=110.0, rl=90.0, rh_touches=2,
                                          rl_touches=3, planned_target=110.0,
                                          features=dict(F_R1))
        else:
            regime = "trend_up" if side == "long" else "trend_down"
            extra = dict(rh=None, rl=None, rh_touches=0, rl_touches=0,
                         planned_target=None, features=dict(F_T1))
        stop = 95.0 if side == "long" else 105.0
        ev = dec(bar_close_ts=bar, pair=pair, side=side, setup=setup,
                 regime=regime, planned_entry=100.0, planned_stop=stop,
                 size_qty=1.0, size_notional=100.0, size_margin=33.0,
                 size_risk_amount=risk, param_version_id=version, **extra)
        did = self.led.record_decision(ev)
        ets = entry_ts or (bar + timedelta(seconds=3))
        self.led.record_trade_entry(L.TradeEntry(
            trade_id=tid, decision_id=did, entry_ts=ets, entry_price=100.0,
            qty=1.0, leverage=3, fee_entry=fee_entry))
        if close:
            px = 100.0 + pnl + fee_entry + fee_exit + funding if side == "long" \
                else 100.0 - pnl - fee_entry - fee_exit - funding
            self.led.record_trade_exit(L.TradeExit(
                trade_id=tid, exit_ts=exit_ts or (ets + timedelta(hours=1)),
                exit_price=px, exit_reason=reason, planned_exit=planned_exit,
                fee_exit=fee_exit, funding_paid=funding))
        return tid

    def many(self, n, **kw):
        return [self.add(**kw) for _ in range(n)]


@pytest.fixture
def fill(lp):
    return Filler(lp)


def last_status(path, pid):
    r = raw(path, "SELECT status FROM proposal_status_events WHERE proposal_id=? "
                  "ORDER BY id DESC LIMIT 1", (pid,))
    return r[0][0] if r else None


def n_status(path, pid):
    return raw(path, "SELECT COUNT(*) FROM proposal_status_events WHERE proposal_id=?",
               (pid,))[0][0]


def propose(lg, changes, base=1, claimed=None, rationale="because", source="test-src"):
    return lg.propose_change(base_version_id=base, changes=changes,
                             rationale=rationale,
                             claimed_evidence=claimed if claimed is not None else {"n_closed": 99},
                             source=source)


# ============================================================ 1. open/schema
class TestOpenSchema:
    def test_new_file_schema(self, led, dbpath):
        assert led.bot == "learner"
        assert led.min_evidence_trades == 20
        assert raw(dbpath, "PRAGMA user_version")[0][0] == 7
        assert raw(dbpath, "PRAGMA journal_mode")[0][0].lower() == "wal"
        assert L.SCHEMA_VERSION == 7
        meta = dict(raw(dbpath, "SELECT key, value FROM meta"))
        assert meta["bot"] == "learner"
        assert meta["schema_version"] == "1"
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", meta["created_at"])

    def test_tables_views_present(self, led, dbpath):
        names = {r[0] for r in raw(dbpath, "SELECT name FROM sqlite_master")}
        for n in ["meta", "decision_events", "trade_entries", "trade_exits",
                  "param_versions", "param_activations", "lesson_proposals",
                  "proposal_status_events", "health_probes", "schema_migrations",
                  "v_decisions", "v_trades", "v_closed_trades", "v_proposals"]:
            assert n in names

    def test_constants(self):
        assert tuple(L.LESSON_PARAMS) == ("vol_ratio_max", "stop_buffer_atr",
                                          "trail_atr", "range_target_frac", "rr_min",
                                          "session_off", "post_stop_wait",   # DD-12 WP-08 genisletmesi
                                          "exit_breakeven", "exit_partial")   # cikis kipleri (docs/cikis-kipleri-spec.md)
        assert L.LESSON_MIN_INTERVAL_DAYS == 7
        for k, v in {"vol_ratio_max": 0.25, "stop_buffer_atr": 0.1, "trail_atr": 0.5,
                     "range_target_frac": 0.125, "rr_min": 0.25}.items():
            assert L.LESSON_STEP[k] == pytest.approx(v)
        for k, (a, b) in {"vol_ratio_max": (1.3, 1.7), "stop_buffer_atr": (0.2, 0.5),
                          "trail_atr": (2.5, 3.5), "range_target_frac": (0.6, 0.9),
                          "rr_min": (1.2, 2.0)}.items():
            assert list(L.LESSON_BOUNDS_DEFAULT[k]) == pytest.approx([a, b])
        assert len(L.PARAM_SPECS) == 9

    def test_reopen_existing(self, dbpath, clock):
        a = L.open_ledger(dbpath, "learner", clock=clock)
        a.init_params(PARAMS, reason="r")
        a.close()
        b = L.open_ledger(dbpath, "learner", clock=clock)
        assert b.get_active_params().version_id == 1
        b.close()

    def test_bot_mismatch(self, dbpath, clock):
        L.open_ledger(dbpath, "learner", clock=clock).close()
        with pytest.raises(L.LedgerSchemaError):
            L.open_ledger(dbpath, "twin", clock=clock)

    def test_invalid_bot(self, tmp_path):
        with pytest.raises(L.LedgerError):
            L.open_ledger(tmp_path / "x.sqlite", "nobody")

    def test_create_false_missing(self, tmp_path):
        with pytest.raises(L.LedgerSchemaError):
            L.open_ledger(tmp_path / "none.sqlite", "learner", create=False)

    def test_newer_schema_rejected(self, dbpath, clock):
        L.open_ledger(dbpath, "learner", clock=clock).close()
        c = sqlite3.connect(str(dbpath)); c.execute("PRAGMA user_version=8"); c.commit(); c.close()
        with pytest.raises(L.LedgerSchemaError):
            L.open_ledger(dbpath, "learner", clock=clock)

    def test_old_schema_no_migrate(self, dbpath, clock):
        L.open_ledger(dbpath, "learner", clock=clock).close()
        c = sqlite3.connect(str(dbpath)); c.execute("PRAGMA user_version=0"); c.commit(); c.close()
        with pytest.raises(L.LedgerSchemaError):
            L.open_ledger(dbpath, "learner", migrate=False, clock=clock)

    def test_dropped_trigger_detected(self, dbpath, clock):
        L.open_ledger(dbpath, "learner", clock=clock).close()
        c = sqlite3.connect(str(dbpath))
        name = c.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
                         "AND tbl_name='decision_events'").fetchone()[0]
        c.execute(f'DROP TRIGGER "{name}"'); c.commit(); c.close()
        with pytest.raises(L.LedgerSchemaError):
            L.open_ledger(dbpath, "learner", clock=clock)

    def test_corrupt_file(self, dbpath, clock):
        dbpath.write_bytes(b"this is definitely not a sqlite database" * 100)
        with pytest.raises(L.LedgerError):
            L.open_ledger(dbpath, "learner", clock=clock)

    def test_min_evidence_floor(self, tmp_path, clock):
        with pytest.raises(L.LedgerValidationError):
            L.open_ledger(tmp_path / "a.sqlite", "learner", min_evidence_trades=10, clock=clock)
        lg = L.open_ledger(tmp_path / "b.sqlite", "learner", min_evidence_trades=25, clock=clock)
        assert lg.min_evidence_trades == 25
        lg.close()

    def test_read_only_writes_state_error(self, lp, dbpath):
        ro = L.open_ledger(dbpath, "learner", read_only=True)
        assert ro.get_active_params().version_id == 1
        with pytest.raises(L.LedgerStateError):
            ro.record_decision(dec())
        with pytest.raises(L.LedgerStateError):
            ro.init_params(PARAMS, reason="x")
        with pytest.raises(L.LedgerStateError):
            propose(ro, {"rr_min": 1.25})
        with pytest.raises(L.LedgerStateError):
            ro.rollback(actor="user", reason="x")
        ro.close()

    def test_backup(self, lp, dbpath, tmp_path):
        lp.record_decision(dec())
        dest = tmp_path / "bk.sqlite"
        lp.backup(dest)
        b = L.open_ledger(dest, "learner", read_only=True)
        assert b.get_active_params().version_id == 1
        assert len(b.list_decisions()) == 1
        b.close()
        with pytest.raises(L.LedgerValidationError):
            lp.backup(dest)

    def test_clock_used_for_recorded_at(self, lp, dbpath):
        lp.record_decision(dec())
        assert raw(dbpath, "SELECT recorded_at FROM decision_events")[0][0] == "2026-12-01T10:00:05.000Z"

    def test_active_activation_id(self, led):
        assert led.active_activation_id() is None
        led.init_params(PARAMS, reason="r")
        assert led.active_activation_id() == 1


# ===================================================== 2. append-only triggers
class TestAppendOnly:
    def test_every_table_blocks_update_delete(self, lp, dbpath, fill):
        fill.add(trade_id=7)
        r = propose(lp, {"rr_min": 1.25})
        assert r.ok
        assert lp.check_writable().ok
        tables = ["meta", "decision_events", "trade_entries", "trade_exits",
                  "param_versions", "param_activations", "lesson_proposals",
                  "proposal_status_events", "health_probes"]
        for t in tables:
            assert raw(dbpath, f"SELECT COUNT(*) FROM {t}")[0][0] >= 1, t
            c = sqlite3.connect(str(dbpath))
            for stmt in (f"UPDATE {t} SET id=id" if t != "meta" else "UPDATE meta SET value=value",
                         f"DELETE FROM {t}"):
                with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                    c.execute(stmt)
            c.close()
        trg = raw(dbpath, "SELECT tbl_name, COUNT(*) FROM sqlite_master WHERE type='trigger' GROUP BY tbl_name")
        counts = dict(trg)
        for t in tables + ["schema_migrations"]:
            assert counts.get(t, 0) >= 2, t

    def test_data_unchanged_after_failed_update(self, lp, dbpath):
        lp.record_decision(dec())
        c = sqlite3.connect(str(dbpath))
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE decision_events SET planned_stop=1")
        c.close()
        assert raw(dbpath, "SELECT planned_stop FROM decision_events")[0][0] == 1960.0

    def test_correction_chain_via_supersedes(self, lp, dbpath):
        assert lp.record_decision(dec()) == 1
        corr = dec(final_action="skipped", skip_reason="order_failed", supersedes_id=1)
        # skipped + order_failed after an allowed/risk-ok decision
        assert lp.record_decision(corr) == 2
        assert [r[0] for r in raw(dbpath, "SELECT id FROM v_decisions")] == [2]
        assert [d for d in lp.list_decisions()] and len(lp.list_decisions()) == 1


# ========================================================== 3. decision records
class TestRecordDecision:
    def test_first_id_and_idempotent(self, lp):
        assert lp.record_decision(dec()) == 1
        assert lp.record_decision(dec()) == 1

    def test_conflict_on_different_content(self, lp):
        lp.record_decision(dec())
        with pytest.raises(L.LedgerConflictError):
            lp.record_decision(dec(planned_stop=1961.0))

    def test_stored_values(self, lp, dbpath):
        lp.record_decision(dec())
        row = raw(dbpath, "SELECT bot, bar_close_ts, trigger_tf, pair, side, setup, regime, "
                          "rh, rl, rh_touches, rl_touches, risk_allowed, final_action, "
                          "param_version_id, features FROM decision_events")[0]
        assert row[:14] == ("learner", "2026-12-01T10:00:00.000Z", "1h", "ETH/USDT", "long",
                            "R1", "range", 2100.0, 1980.0, 2, 3, 1, "entered", 1)
        assert json.loads(row[14])["rr"] == 2.5
        assert row[14] == canon(F_R1)

    def test_pair_side_normalised(self, lp, dbpath):
        lp.record_decision(t1_short(pair="btc/usdt:usdt", side="  Short ", bar_close_ts=EX_TS))
        r = raw(dbpath, "SELECT pair, side FROM decision_events")[0]
        assert r == ("BTC/USDT", "short")

    def test_tz_aware_converted_to_utc(self, lp, dbpath):
        tz = timezone(timedelta(hours=3))
        lp.record_decision(dec(bar_close_ts=datetime(2026, 12, 1, 13, 0, tzinfo=tz)))
        assert raw(dbpath, "SELECT bar_close_ts FROM decision_events")[0][0] == "2026-12-01T10:00:00.000Z"

    def test_two_decisions_same_bar_different_pair_ok(self, lp):
        a = lp.record_decision(dec())
        b = lp.record_decision(dec(pair="BTC/USDT"))
        assert b == a + 1

    def test_valid_skip_variants(self, lp):
        lp.record_decision(skipped())  # rr_below_min
        lp.record_decision(skipped(pair="A/USDT", skip_reason="stop_width"))
        lp.record_decision(skipped(pair="B/USDT", skip_reason="other"))
        for i, (vs, sr) in enumerate([("blocked", "veto_blocked"), ("missing", "veto_missing"),
                                      ("stale", "veto_stale")]):
            lp.record_decision(skipped(pair=f"C{i}/USDT", veto_status=vs, skip_reason=sr,
                                       veto_reason="why"))
        lp.record_decision(skipped(pair="D/USDT", veto_status="allowed", risk_allowed=False,
                                   risk_reason="denied", skip_reason="risk_denied"))
        assert len(lp.list_decisions()) == 7

    @pytest.mark.parametrize("over", [
        dict(bar_close_ts=datetime(2026, 12, 1, 10, 0)),                      # naive
        dict(bar_close_ts=datetime(2026, 12, 1, 10, 7, tzinfo=UTC)),          # not 15m multiple
        dict(bar_close_ts=datetime(2026, 12, 1, 10, 0, 1, tzinfo=UTC)),       # seconds
        dict(bar_close_ts=datetime(2026, 12, 1, 10, 15, tzinfo=UTC)),         # future > +5s
        dict(trigger_tf="5m"), dict(side="up"), dict(setup="X"), dict(regime="sideways"),
        dict(rh=None), dict(rl=None),                                         # range needs both
        dict(regime="trend_up"),                                              # rh given outside range
        dict(planned_entry=float("nan")), dict(planned_entry=float("inf")),
        dict(planned_entry=True), dict(planned_entry="2000"), dict(planned_entry=None),
        dict(features={k: v for k, v in F_R1.items() if k != "rr"}),
        dict(features={**F_R1, "rr": float("nan")}),
        dict(features={**F_R1, "pad": "x" * 17000}),
        dict(veto_status="maybe"),
        dict(veto_status="blocked"),                                          # entered + blocked
        dict(veto_status="stale"), dict(veto_status="missing"),
        dict(risk_allowed=False), dict(risk_allowed=None),                    # (not_evaluated + entered gecerli: v6, WP-06a)
        dict(size_qty=None), dict(size_risk_amount=None), dict(leverage=None),
        dict(skip_reason="other"),                                            # entered + skip_reason
        dict(final_action="done"),
        dict(veto_reason="x" * 501),
        dict(risk_reason="x" * 501),
        dict(size_qty=float("nan")),
    ])
    def test_invalid_rejected_nothing_written(self, lp, dbpath, over):
        with pytest.raises(L.LedgerValidationError):
            lp.record_decision(dec(**over))
        assert raw(dbpath, "SELECT COUNT(*) FROM decision_events")[0][0] == 0

    def test_entered_not_evaluated_valid_since_v6(self, lp, dbpath):
        """DD-12 WP-06a: kagitta veto yok; girilen satir veto_status='not_evaluated' yazar (sema v6)."""
        lp.record_decision(dec(veto_status="not_evaluated"))
        assert raw(dbpath, "SELECT veto_status, final_action FROM decision_events")[0] == ("not_evaluated", "entered")

    @pytest.mark.parametrize("ev", [
        lambda: skipped(skip_reason=None),                                    # skipped needs reason
        lambda: skipped(skip_reason="made_up"),
        lambda: skipped(risk_allowed=True),                                   # not_evaluated => risk NULL
        lambda: skipped(skip_reason="risk_denied"),                           # not_evaluated limits codes
        lambda: skipped(veto_status="blocked", skip_reason="rr_below_min"),
        lambda: skipped(veto_status="blocked", skip_reason="veto_blocked", final_action="entered"),
        lambda: skipped(veto_status="allowed", risk_allowed=False, skip_reason="other"),
        lambda: skipped(regime="range", rh=None),
    ])
    def test_invalid_skip_combos(self, lp, ev):
        with pytest.raises(L.LedgerValidationError):
            lp.record_decision(ev())

    def test_unknown_param_version(self, lp):
        with pytest.raises(L.LedgerError):
            lp.record_decision(dec(param_version_id=99))

    def test_timestamp_ms_floor_for_aware(self, lp, dbpath, clock):
        # bar ts must be 15m multiple; ms floor is exercised via trade entries elsewhere
        lp.record_decision(dec())
        assert raw(dbpath, "SELECT bar_close_ts FROM decision_events")[0][0].endswith(".000Z")

    def test_get_and_list_decisions(self, lp):
        ids = []
        for i in range(4):
            ids.append(lp.record_decision(skipped(
                bar_close_ts=EX_TS - timedelta(minutes=15 * (3 - i)) , pair=f"P{i}/USDT",
                setup="R1" if i % 2 == 0 else "T1",
                **({} if i % 2 == 0 else dict(regime="trend_up", rh=None, rl=None,
                                              rh_touches=0, rl_touches=0, features=dict(F_T1),
                                              planned_target=None)))))
        assert lp.get_decision(ids[0]) is not None
        allv = lp.list_decisions()
        assert len(allv) == 4
        assert len(lp.list_decisions(limit=2)) == 2
        assert len(lp.list_decisions(setup="T1")) == 2
        assert len(lp.list_decisions(final_action="entered")) == 0
        assert len(lp.list_decisions(final_action="skipped")) == 4
        mid = EX_TS - timedelta(minutes=25)
        assert len(lp.list_decisions(since_ts=mid)) == 2
        assert len(lp.list_decisions(until_ts=mid)) == 2
        # ascending bar_close_ts
        assert [d.pair for d in allv] == ["P0/USDT", "P1/USDT", "P2/USDT", "P3/USDT"]


# ========================================================== 4. trades / R / slippage
class TestTrades:
    def test_winner_example_12_3(self, lp, dbpath):
        assert lp.record_decision(dec()) == 1
        assert lp.record_trade_entry(entry()) == 1
        t = lp.get_trade(7)
        assert t.slippage_entry == pytest.approx(0.0005)
        assert t.planned_risk == pytest.approx(13.188)
        assert t.exit_ts is None and t.realized_pnl is None
        assert [x.trade_id for x in lp.list_open_trades()] == [7]
        assert lp.record_trade_exit(xit()) == 1
        t = lp.get_trade(7)
        assert t.gross_pnl == pytest.approx(23.4)
        assert t.realized_pnl == pytest.approx(22.688)
        assert t.r_multiple == pytest.approx(1.720352, abs=1e-5)
        assert t.slippage_exit == pytest.approx(0.01)
        assert t.exit_reason == "target"
        assert t.fee_entry == pytest.approx(0.30015) and t.fee_exit == pytest.approx(0.31185)
        assert t.funding_paid == pytest.approx(0.1)
        assert t.pair == "ETH/USDT" and t.side == "long" and t.setup == "R1"
        assert t.regime == "range" and t.param_version_id == 1 and t.decision_id == 1
        assert lp.list_open_trades() == []

    def test_entry_copies_from_decision(self, lp, dbpath):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        r = raw(dbpath, "SELECT bot, pair, side, setup, param_version_id, planned_entry, "
                        "planned_stop, planned_target, planned_risk, leverage, qty, entry_ts "
                        "FROM trade_entries")[0]
        assert r == ("learner", "ETH/USDT", "long", "R1", 1, 2000.0, 1960.0, 2100.0,
                     13.188, 3, 0.3, "2026-12-01T10:00:03.000Z")

    def test_ms_floor(self, lp, dbpath):
        lp.record_decision(dec())
        lp.record_trade_entry(entry(entry_ts=datetime(2026, 12, 1, 10, 0, 3, 123987, tzinfo=UTC)))
        assert raw(dbpath, "SELECT entry_ts FROM trade_entries")[0][0] == "2026-12-01T10:00:03.123Z"

    def test_loser_t1_short_example_12_4(self, lp):
        did = lp.record_decision(t1_short())
        lp.record_trade_entry(L.TradeEntry(8, did, EX_TS + timedelta(seconds=2), 100.0, 10.0, 3, 0.5))
        lp.record_trade_exit(L.TradeExit(8, EX_TS + timedelta(hours=5), 101.0, "stop",
                                         101.0, 0.505, -0.05))
        t = lp.get_trade(8)
        assert t.gross_pnl == pytest.approx(-10.0)
        assert t.realized_pnl == pytest.approx(-10.955)
        assert t.r_multiple == pytest.approx(-10.955 / 12.01, abs=1e-6)
        assert t.r_multiple == pytest.approx(-0.9122, abs=1e-4)
        assert t.slippage_entry == pytest.approx(0.0)
        assert t.slippage_exit == pytest.approx(0.0)
        assert t.side == "short" and t.setup == "T1" and t.regime == "trend_down"

    def test_slippage_signs(self, lp):
        d1 = lp.record_decision(dec())  # long planned 2000
        lp.record_trade_entry(entry(entry_price=1999.0))
        assert lp.get_trade(7).slippage_entry == pytest.approx(-0.0005)
        d2 = lp.record_decision(t1_short())  # short planned 100
        lp.record_trade_entry(L.TradeEntry(8, d2, EX_TS, 99.9, 10.0, 3, 0.0))
        assert lp.get_trade(8).slippage_entry == pytest.approx(0.001)  # (100-99.9)/100
        lp.record_trade_exit(L.TradeExit(8, EX_TS + timedelta(hours=1), 102.0, "stop", 101.0, 0, 0))
        assert lp.get_trade(8).slippage_exit == pytest.approx((102 - 101) / 101)  # short exit
        lp.record_trade_exit(xit(exit_price=2090.0, planned_exit=2100.0))
        assert lp.get_trade(7).slippage_exit == pytest.approx((2100 - 2090) / 2100)  # long exit

    def test_no_planned_exit_no_slippage(self, lp):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        lp.record_trade_exit(xit(exit_reason="time_stop", planned_exit=None))
        assert lp.get_trade(7).slippage_exit is None

    def test_derived_fields_not_caller_supplied(self):
        names = {f.name for f in dataclasses.fields(L.TradeExit)}
        assert not names & {"gross_pnl", "realized_pnl", "r_multiple", "slippage_exit"}
        names = {f.name for f in dataclasses.fields(L.TradeEntry)}
        assert not names & {"slippage_entry", "planned_risk"}

    def test_dataclasses_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            entry().qty = 5

    def test_get_trade_unknown_none(self, lp):
        assert lp.get_trade(12345) is None

    def test_entry_idempotent_and_conflicts(self, lp):
        lp.record_decision(dec())
        a = lp.record_trade_entry(entry())
        assert lp.record_trade_entry(entry()) == a
        with pytest.raises(L.LedgerConflictError):
            lp.record_trade_entry(entry(entry_price=2002.0))
        lp.record_decision(dec(pair="BTC/USDT"))
        with pytest.raises(L.LedgerConflictError):
            lp.record_trade_entry(entry(decision_id=2))

    def test_entry_supersede(self, lp):
        lp.record_decision(dec())
        a = lp.record_trade_entry(entry())
        b = lp.record_trade_entry(entry(entry_price=2002.0, supersedes_id=a))
        assert b != a
        lp.record_trade_exit(xit())
        assert lp.get_trade(7).slippage_entry == pytest.approx(2 / 2000)

    def test_entry_requires_entered_decision(self, lp):
        lp.record_decision(skipped())
        with pytest.raises(L.LedgerError):
            lp.record_trade_entry(entry(decision_id=1))
        with pytest.raises(L.LedgerError):
            lp.record_trade_entry(entry(decision_id=999))

    @pytest.mark.parametrize("over", [
        dict(qty=0.0), dict(qty=-1.0), dict(entry_price=0.0), dict(entry_price=-5.0),
        dict(leverage=0), dict(leverage=2.5), dict(leverage=True), dict(fee_entry=-0.1),
        dict(entry_price=float("nan")), dict(qty=True), dict(trade_id="7"),
        dict(entry_ts=datetime(2026, 12, 1, 10, 0, 3)),
    ])
    def test_entry_invalid(self, lp, dbpath, over):
        lp.record_decision(dec())
        with pytest.raises(L.LedgerValidationError):
            lp.record_trade_entry(entry(**over))
        assert raw(dbpath, "SELECT COUNT(*) FROM trade_entries")[0][0] == 0

    def test_planned_risk_must_be_positive(self, lp):
        with pytest.raises(L.LedgerValidationError):
            did = lp.record_decision(dec(size_risk_amount=0.0))
            lp.record_trade_entry(entry(decision_id=did))

    def test_exit_requires_entry(self, lp):
        with pytest.raises(L.LedgerError):
            lp.record_trade_exit(xit())

    @pytest.mark.parametrize("over", [
        dict(exit_ts=datetime(2026, 12, 1, 10, 0, 2, tzinfo=UTC)),  # before entry_ts
        dict(exit_ts=datetime(2026, 12, 2, 9, 0)),                  # naive
        dict(exit_price=0.0), dict(exit_price=-1.0), dict(exit_reason="whim"),
        dict(fee_exit=-0.01), dict(funding_paid=float("nan")), dict(funding_paid=True),
        dict(exit_price=float("inf")),
    ])
    def test_exit_invalid(self, lp, dbpath, over):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        with pytest.raises(L.LedgerValidationError):
            lp.record_trade_exit(xit(**over))
        assert raw(dbpath, "SELECT COUNT(*) FROM trade_exits")[0][0] == 0

    @pytest.mark.parametrize("reason", ["stop", "target", "trail_stop", "regime_flip", "time_stop",
                                        "manual", "force_exit", "liquidation", "other"])
    def test_exit_reasons_accepted(self, lp, reason):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        pe = 2100.0 if reason in ("stop", "target", "trail_stop") else None
        assert lp.record_trade_exit(xit(exit_reason=reason, planned_exit=pe)) >= 1

    def test_negative_funding_allowed(self, lp):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        lp.record_trade_exit(xit(funding_paid=-0.2))
        assert lp.get_trade(7).realized_pnl == pytest.approx(23.4 - 0.30015 - 0.31185 + 0.2)

    def test_exit_idempotent_and_conflict(self, lp):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        a = lp.record_trade_exit(xit())
        assert lp.record_trade_exit(xit()) == a
        with pytest.raises(L.LedgerConflictError):
            lp.record_trade_exit(xit(exit_price=2050.0))

    def test_exit_correction_supersedes(self, lp):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        a = lp.record_trade_exit(xit())
        b = lp.record_trade_exit(xit(exit_price=2050.0, supersedes_id=a))
        assert b != a
        assert lp.get_trade(7).gross_pnl == pytest.approx(0.3 * (2050 - 2001))

    def test_r_not_recomputed_planned_risk_frozen(self, lp, dbpath):
        lp.record_decision(dec()); lp.record_trade_entry(entry()); lp.record_trade_exit(xit())
        assert raw(dbpath, "SELECT planned_risk FROM trade_entries")[0][0] == 13.188
        assert raw(dbpath, "SELECT r_multiple FROM trade_exits")[0][0] == pytest.approx(22.688 / 13.188)

    def test_views(self, lp, dbpath, fill):
        fill.add(trade_id=1, close=True)
        fill.add(trade_id=2, close=False)
        assert len(raw(dbpath, "SELECT * FROM v_trades")) == 2
        assert len(raw(dbpath, "SELECT * FROM v_closed_trades")) == 1

    def test_orphan_decisions(self, lp, clock):
        d = lp.record_decision(dec())
        clock.advance(hours=2)
        assert lp.find_orphan_decisions(older_than_s=3600) == [d]
        assert lp.find_orphan_decisions(older_than_s=3 * 3600) == []
        lp.record_trade_entry(entry())
        assert lp.find_orphan_decisions(older_than_s=3600) == []

    def test_orphan_corrected_by_supersede(self, lp, clock):
        lp.record_decision(dec())
        lp.record_decision(dec(final_action="skipped", skip_reason="order_failed", supersedes_id=1))
        clock.advance(hours=2)
        assert lp.find_orphan_decisions(older_than_s=3600) == []

    def test_find_unledgered(self, lp):
        lp.record_decision(dec()); lp.record_trade_entry(entry(trade_id=7))
        did = lp.record_decision(dec(pair="BTC/USDT"))
        lp.record_trade_entry(entry(trade_id=8, decision_id=did))
        assert lp.find_unledgered_trades([7, 8, 9]) == [9]
        assert lp.find_unledgered_trades([]) == []
        assert lp.find_unledgered_trades(iter([7])) == []


# ================================================================ 5. params
class TestParams:
    def test_init_example_12_1(self, led, dbpath):
        assert led.init_params(PARAMS, reason="initial") == 1
        ap = led.get_active_params()
        assert ap.version_id == 1 and ap.activation_id == 1
        assert ap.params_hash == HASH0
        assert dict(ap.params) == PARAMS
        assert raw(dbpath, "SELECT id, kind, actor, prev_version_id FROM param_activations") == \
            [(1, "initial", "system", None)]
        v = raw(dbpath, "SELECT params, params_hash, author, parent_version_id, bot FROM param_versions")[0]
        assert v[0] == canon(PARAMS) and v[1] == HASH0 and v[2] == "initial"
        assert v[3] is None and v[4] == "learner"
        assert hashlib.sha256(canon(PARAMS).encode()).hexdigest() == HASH0

    def test_hash_order_and_float_normalisation(self, led):
        p = dict(reversed(list(PARAMS.items())))
        p["pullback_ema"] = 50.0
        led.init_params(p, reason="r")
        assert led.get_active_params().params_hash == HASH0
        assert led.get_active_params().params["pullback_ema"] == 50
        assert isinstance(led.get_active_params().params["pullback_ema"], int)

    def test_hash_rr125(self, lp, dbpath):
        v = lp.create_user_version({**PARAMS, "rr_min": 1.25}, reason="r")
        assert raw(dbpath, "SELECT params_hash FROM param_versions WHERE id=?", (v,))[0][0] == HASH_RR125
        assert hashlib.sha256(canon({**PARAMS, "rr_min": 1.25}).encode()).hexdigest() == HASH_RR125

    def test_float_rounding_6(self, led):
        led.init_params({**PARAMS, "rr_min": 1.5000004}, reason="r")
        assert led.get_active_params().params["rr_min"] == 1.5
        assert led.get_active_params().params_hash == HASH0

    def test_second_init_state_error(self, lp):
        with pytest.raises(L.LedgerStateError):
            lp.init_params(PARAMS, reason="again")

    def test_no_active_before_init(self, led):
        with pytest.raises(L.LedgerStateError):
            led.get_active_params()

    @pytest.mark.parametrize("mod", [
        lambda p: {**p, "max_leverage": 3},
        lambda p: {k: v for k, v in p.items() if k != "rr_min"},
        lambda p: {**p, "vol_ratio_max": 1.2},
        lambda p: {**p, "vol_ratio_max": 2.01},
        lambda p: {**p, "range_width_atr": 2.9}, lambda p: {**p, "range_width_atr": 6.1},
        lambda p: {**p, "edge_zone_atr": 0.14}, lambda p: {**p, "edge_zone_atr": 0.51},
        lambda p: {**p, "pullback_ema": 30},
        lambda p: {**p, "stop_buffer_atr": 0.05}, lambda p: {**p, "stop_buffer_atr": 1.1},
        lambda p: {**p, "trail_atr": 1.9}, lambda p: {**p, "trail_atr": 4.1},
        lambda p: {**p, "range_target_frac": 0.4}, lambda p: {**p, "range_target_frac": 1.1},
        lambda p: {**p, "rr_min": 0.9}, lambda p: {**p, "rr_min": 2.1},
        lambda p: {**p, "trigger_tf": "5m"},
        lambda p: {**p, "rr_min": float("nan")}, lambda p: {**p, "rr_min": True},
        lambda p: {**p, "rr_min": "1.5"},
    ])
    def test_init_invalid(self, led, dbpath, mod):
        with pytest.raises(L.LedgerValidationError):
            led.init_params(mod(PARAMS), reason="r")
        assert raw(dbpath, "SELECT COUNT(*) FROM param_versions")[0][0] == 0
        with pytest.raises(L.LedgerStateError):
            led.get_active_params()

    @pytest.mark.parametrize("key,lo,hi", [
        ("range_width_atr", 3.0, 6.0), ("vol_ratio_max", 1.25, 2.0), ("edge_zone_atr", 0.15, 0.5),
        ("stop_buffer_atr", 0.1, 1.0), ("trail_atr", 2.0, 4.0), ("range_target_frac", 0.5, 1.0),
        ("rr_min", 1.0, 2.0)])
    def test_range_ends_inclusive(self, tmp_path, clock, key, lo, hi):
        for i, val in enumerate((lo, hi)):
            lg = L.open_ledger(tmp_path / f"{key}{i}.sqlite", "learner", clock=clock)
            lb = {"lesson_bounds": {}}
            p = {**PARAMS, key: val}
            # lesson bounds must contain the initial value; use a widened one if needed
            bounds = {k: tuple(v) for k, v in L.LESSON_BOUNDS_DEFAULT.items()}
            if key in bounds:
                bounds[key] = (lo, hi)
            lg.init_params(p, reason="r", lesson_bounds=bounds)
            assert lg.get_active_params().params[key] == val
            lg.close()

    def test_pullback_20_and_trigger_15m(self, led):
        led.init_params({**PARAMS, "pullback_ema": 20, "trigger_tf": "15m"}, reason="r")
        p = led.get_active_params().params
        assert p["pullback_ema"] == 20 and p["trigger_tf"] == "15m"

    def test_default_lesson_bounds(self, lp):
        lb = lp.get_active_params().lesson_bounds
        assert set(lb) == set(L.LESSON_PARAMS)
        assert list(lb["rr_min"]) == pytest.approx([1.2, 2.0])

    def test_custom_bounds_and_validation(self, led):
        b = {k: tuple(v) for k, v in L.LESSON_BOUNDS_DEFAULT.items()}
        for bad in [(1.6, 1.9),          # excludes initial value 1.5
                    (1.8, 1.4),          # lo > hi
                    (0.5, 2.0),          # below sweep range
                    (1.0, 2.5)]:         # above sweep range
            with pytest.raises(L.LedgerValidationError):
                led.init_params(PARAMS, reason="r", lesson_bounds={**b, "rr_min": bad})
        led.init_params(PARAMS, reason="r", lesson_bounds={**b, "rr_min": (1.4, 1.6)})
        assert list(led.get_active_params().lesson_bounds["rr_min"]) == pytest.approx([1.4, 1.6])

    def test_empty_reason(self, led):
        for r in ("", "   "):
            with pytest.raises(L.LedgerValidationError):
                led.init_params(PARAMS, reason=r)

    def test_active_params_readonly_and_frozen(self, lp):
        ap = lp.get_active_params()
        with pytest.raises(TypeError):
            ap.params["rr_min"] = 9
        with pytest.raises(dataclasses.FrozenInstanceError):
            ap.version_id = 5
        assert re.fullmatch(r"[0-9a-f]{64}", ap.params_hash)

    def test_user_version_not_activated_until_asked(self, lp, dbpath):
        v = lp.create_user_version({**PARAMS, "range_width_atr": 5.0}, reason="new backtest")
        assert v == 2
        assert lp.get_active_params().version_id == 1
        res = lp.activate_version(v, actor="user", reason="approved")
        assert res.ok and res.version_id == 2
        ap = lp.get_active_params()
        assert ap.version_id == 2 and ap.params["range_width_atr"] == 5.0
        assert raw(dbpath, "SELECT kind, actor, prev_version_id, version_id FROM param_activations "
                           "ORDER BY id DESC LIMIT 1") == [("apply", "user", 1, 2)]
        assert raw(dbpath, "SELECT author, parent_version_id FROM param_versions WHERE id=2") == [("user", 1)]

    def test_user_version_validation(self, lp):
        with pytest.raises(L.LedgerValidationError):
            lp.create_user_version({**PARAMS, "max_leverage": 1}, reason="r")
        with pytest.raises(L.LedgerValidationError):
            lp.create_user_version({**PARAMS, "rr_min": 2.5}, reason="r")
        with pytest.raises(L.LedgerValidationError):
            lp.create_user_version({**PARAMS, "rr_min": 1.4}, reason=" ")

    def test_user_version_new_bounds(self, lp):
        b = {k: tuple(v) for k, v in L.LESSON_BOUNDS_DEFAULT.items()}
        v = lp.create_user_version({**PARAMS, "rr_min": 1.6}, reason="r",
                                   lesson_bounds={**b, "rr_min": (1.4, 1.8)})
        lp.activate_version(v, actor="user", reason="ok")
        assert list(lp.get_active_params().lesson_bounds["rr_min"]) == pytest.approx([1.4, 1.8])

    def test_activate_unknown_and_already_active(self, lp):
        assert failed(lambda: lp.activate_version(99, actor="user", reason="r"))
        res = lp.activate_version(1, actor="user", reason="r")
        assert res.ok is False

    def test_versions_listing(self, lp):
        lp.create_user_version({**PARAMS, "rr_min": 1.25}, reason="r")
        assert len(lp.list_versions()) == 2
        assert lp.get_version(1) is not None
        with pytest.raises(L.LedgerError):
            lp.get_version(99)
        assert len(lp.list_activations()) == 1
        lp.activate_version(2, actor="user", reason="r")
        assert len(lp.list_activations()) == 2
        assert len(lp.list_activations(limit=1)) == 1

    def test_twin_rules(self, tmp_path, clock):
        tw = L.open_ledger(tmp_path / "t.sqlite", "twin", clock=clock)
        tw.init_params(PARAMS, reason="r")
        assert tw.get_active_params().params_hash == HASH0
        # decisions/trades are allowed
        did = tw.record_decision(dec())
        tw.record_trade_entry(entry(decision_id=did))
        tw.record_trade_exit(xit())
        assert raw(tmp_path / "t.sqlite", "SELECT DISTINCT bot FROM decision_events") == [("twin",)]
        with pytest.raises(L.LedgerStateError):
            propose(tw, {"rr_min": 1.25})
        with pytest.raises(L.LedgerStateError):
            tw.rollback(actor="user", reason="r")
        with pytest.raises(L.LedgerStateError):
            tw.create_user_version({**PARAMS, "rr_min": 1.25}, reason="r")
        assert failed(lambda: tw.apply_proposal(1, actor="user", reason="r"))
        assert raw(tmp_path / "t.sqlite", "SELECT COUNT(*) FROM lesson_proposals")[0][0] == 0
        tw.close()


# ============================================================ 6. propose rules
class TestPropose:
    @pytest.mark.parametrize("changes,status,code", [
        ({"trail_atr": 3.5}, "proposed", None),
        ({"trail_atr": 2.5}, "proposed", None),
        ({"trail_atr": 4.0}, "rejected", "out_of_bounds"),
        ({"trail_atr": 2.0}, "rejected", "out_of_bounds"),
        ({"stop_buffer_atr": 0.5}, "rejected", "step_too_large"),
        ({"stop_buffer_atr": 0.4}, "proposed", None),       # float tolerance 0.30000000000000004
        ({"stop_buffer_atr": 0.2}, "proposed", None),
        ({"stop_buffer_atr": 0.6}, "rejected", "out_of_bounds"),
        ({"rr_min": 1.25}, "proposed", None),
        ({"rr_min": 1.75}, "proposed", None),
        ({"rr_min": 1.2}, "rejected", "step_too_large"),
        ({"rr_min": 2.0}, "rejected", "step_too_large"),
        ({"rr_min": 1.5}, "rejected", "no_change"),
        ({"vol_ratio_max": 1.3}, "proposed", None),
        ({"vol_ratio_max": 1.4}, "proposed", None),
        ({"vol_ratio_max": 1.7}, "needs_user", "needs_user"),
        ({"vol_ratio_max": 1.6}, "needs_user", "needs_user"),
        ({"vol_ratio_max": 1.75}, "rejected", "out_of_bounds"),
        ({"range_target_frac": 0.875}, "proposed", None),
        ({"range_target_frac": 0.9}, "rejected", "step_too_large"),
        ({"range_width_atr": 3.5}, "rejected", "immutable_param"),
        ({"edge_zone_atr": 0.2}, "rejected", "immutable_param"),
        ({"pullback_ema": 20}, "rejected", "immutable_param"),
        ({"trigger_tf": "15m"}, "rejected", "immutable_param"),
        ({"rr_min": 1.25, "trail_atr": 3.5}, "rejected", "multiple_changes"),
        ({"max_leverage": 4}, "rejected", "unknown_param"),
        ({"rr_min": True}, "rejected", "bad_value"),
        ({"rr_min": "1.3"}, "rejected", "bad_value"),
        ({"rr_min": float("nan")}, "rejected", "bad_value"),
        ({"rr_min": float("inf")}, "rejected", "bad_value"),
        ({}, "rejected", "empty_changes"),
    ])
    def test_table_12_6(self, lp, dbpath, changes, status, code):
        r = propose(lp, changes)
        assert r.status == status
        if code:
            assert r.code == code
        assert r.ok is (status != "rejected")
        assert isinstance(r.proposal_id, int)
        assert last_status(dbpath, r.proposal_id) == status
        # audit trail: every proposal (even rejects) is written
        assert raw(dbpath, "SELECT COUNT(*) FROM lesson_proposals WHERE id=?", (r.proposal_id,))[0][0] == 1
        assert lp.get_proposal(r.proposal_id) is not None

    def test_stale_base(self, lp, dbpath):
        r = propose(lp, {"rr_min": 1.25}, base=3)
        assert (r.status, r.code, r.ok) == ("rejected", "stale_base", False)
        r = propose(lp, {}, base=3)           # rule 2 precedes rule 3
        assert r.code == "stale_base"

    def test_rule_order(self, lp):
        assert propose(lp, {"range_width_atr": 3.5, "rr_min": 1.3}).code == "multiple_changes"
        assert propose(lp, {"max_leverage": 1}).code == "unknown_param"
        assert propose(lp, {"trail_atr": 4.0}).code == "out_of_bounds"   # before step rule

    def test_custom_bounds_apply(self, led):
        b = {k: tuple(v) for k, v in L.LESSON_BOUNDS_DEFAULT.items()}
        led.init_params(PARAMS, reason="r", lesson_bounds={**b, "rr_min": (1.4, 1.6)})
        assert propose(led, {"rr_min": 1.25}).code == "out_of_bounds"
        assert propose(led, {"rr_min": 1.4}).status == "proposed"

    def test_empty_text_fields(self, lp):
        for kw in (dict(rationale=""), dict(source=" ")):
            with pytest.raises(L.LedgerValidationError):
                propose(lp, {"rr_min": 1.25}, **kw)

    def test_list_and_get(self, lp):
        a = propose(lp, {"rr_min": 1.25}); b = propose(lp, {"trail_atr": 4.0})
        assert len(lp.list_proposals()) == 2
        assert len(lp.list_proposals(status="rejected")) == 1
        assert len(lp.list_proposals(status="proposed")) == 1
        assert len(lp.list_proposals(limit=1)) == 1
        assert a.proposal_id != b.proposal_id

    def test_reject_proposal(self, lp, dbpath):
        a = propose(lp, {"rr_min": 1.25})
        lp.reject_proposal(a.proposal_id, actor="user", reason="no thanks")
        assert last_status(dbpath, a.proposal_id) == "rejected"
        assert raw(dbpath, "SELECT code FROM proposal_status_events WHERE proposal_id=? "
                           "ORDER BY id DESC LIMIT 1", (a.proposal_id,))[0][0] == "rejected_by_actor"
        with pytest.raises(L.LedgerStateError):
            lp.reject_proposal(a.proposal_id, actor="user", reason="again")
        with pytest.raises(L.LedgerStateError):
            lp.apply_proposal(a.proposal_id, actor="lesson", reason="r")
        nu = propose(lp, {"vol_ratio_max": 1.7})
        lp.reject_proposal(nu.proposal_id, actor="user", reason="no")
        assert last_status(dbpath, nu.proposal_id) == "rejected"

    def test_apply_unknown_proposal(self, lp):
        with pytest.raises(L.LedgerError):
            lp.apply_proposal(404, actor="lesson", reason="r")


# =========================================================== 7. evidence / apply
class TestApplyEvidence:
    def test_threshold_12_7(self, lp, fill, dbpath):
        fill.many(15, setup="R1"); fill.many(30, setup="T1")
        pr = propose(lp, {"rr_min": 1.25}, claimed={"n_closed": 99})
        assert pr.status == "proposed"
        ev0 = n_status(dbpath, pr.proposal_id)
        res = lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go")
        assert res.ok is False and res.code == "insufficient_evidence"
        assert last_status(dbpath, pr.proposal_id) == "proposed"
        assert n_status(dbpath, pr.proposal_id) == ev0   # transient: no event
        fill.many(4, setup="R1")  # 19
        res = lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go")
        assert res.code == "insufficient_evidence"
        fill.add(setup="R1")      # 20
        res = lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go")
        assert res.ok is True and res.version_id == 2 and res.activation_id == 2
        assert res.proposal_id == pr.proposal_id
        v = raw(dbpath, "SELECT author, params, evidence, proposal_id, parent_version_id, params_hash "
                        "FROM param_versions WHERE id=2")[0]
        assert v[0] == "lesson"
        p2 = json.loads(v[1])
        assert p2["rr_min"] == 1.25
        assert {k: x for k, x in p2.items() if k != "rr_min"} == {k: x for k, x in PARAMS.items() if k != "rr_min"}
        ev = json.loads(v[2])
        assert ev["n_closed"] == 20 and ev["scope"] == "R1+B1+F1" and ev["base_version_id"] == 1   # 24.11: kapsam = rr_min okuyan kurulumlar
        assert ev["claimed_mismatch"] is True
        assert ev["mean_r"] == pytest.approx(1.0) and ev["sum_r"] == pytest.approx(20.0)
        assert ev["win_rate"] == pytest.approx(1.0)
        assert "first_exit_ts" in ev and "last_exit_ts" in ev
        assert v[3] == pr.proposal_id and v[4] == 1 and v[5] == HASH_RR125
        assert raw(dbpath, "SELECT id, kind, version_id, prev_version_id, actor, proposal_id "
                           "FROM param_activations WHERE id=2") == [(2, "apply", 2, 1, "lesson", pr.proposal_id)]
        assert last_status(dbpath, pr.proposal_id) == "applied"
        assert raw(dbpath, "SELECT version_id FROM proposal_status_events WHERE proposal_id=? "
                           "ORDER BY id DESC LIMIT 1", (pr.proposal_id,))[0][0] == 2
        ap = lp.get_active_params()
        assert ap.version_id == 2 and ap.params["rr_min"] == 1.25
        assert ap.params_hash == HASH_RR125
        assert lp.active_activation_id() == 2

    def test_claimed_match_flag(self, lp, fill, dbpath):
        fill.many(20, setup="R1")
        pr = propose(lp, {"rr_min": 1.25}, claimed={"n_closed": 20})
        assert lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go").ok
        ev = json.loads(raw(dbpath, "SELECT evidence FROM param_versions WHERE id=2")[0][0])
        assert ev["claimed_mismatch"] is False

    def test_open_trades_dont_count(self, lp, fill):
        fill.many(19, setup="R1"); fill.add(setup="R1", close=False)
        pr = propose(lp, {"rr_min": 1.25})
        assert lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go").code == "insufficient_evidence"

    def test_other_version_trades_dont_count(self, lp, fill):
        fill.many(20, setup="R1", version=1)
        v = lp.create_user_version({**PARAMS, "range_width_atr": 5.0}, reason="r")
        lp.activate_version(v, actor="user", reason="r")
        fill.many(5, setup="R1", version=2)
        pr = propose(lp, {"rr_min": 1.25}, base=2)
        assert lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go").code == "insufficient_evidence"

    def test_scope_t1_plus_r1(self, lp, fill):
        fill.many(30, setup="T1"); fill.many(15, setup="R1")
        pr = propose(lp, {"vol_ratio_max": 1.3})
        assert lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go").ok

    def test_scope_t1_only(self, lp, fill):
        fill.many(30, setup="T1")
        tr = propose(lp, {"trail_atr": 3.5})
        rr = propose(lp, {"rr_min": 1.25})
        assert lp.apply_proposal(rr.proposal_id, actor="lesson", reason="go").code == "insufficient_evidence"
        res = lp.apply_proposal(tr.proposal_id, actor="lesson", reason="go")
        assert res.ok

    def test_scope_r1_only_for_target_frac(self, lp, fill):
        fill.many(30, setup="T1")
        pr = propose(lp, {"range_target_frac": 0.875})
        assert lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go").code == "insufficient_evidence"

    def test_min_evidence_25(self, dbpath, clock):
        lg = L.open_ledger(dbpath, "learner", min_evidence_trades=25, clock=clock)
        lg.init_params(PARAMS, reason="r")
        f = Filler(lg)
        f.many(24, setup="R1")
        pr = propose(lg, {"rr_min": 1.25})
        assert lg.apply_proposal(pr.proposal_id, actor="lesson", reason="go").code == "insufficient_evidence"
        f.add(setup="R1")
        assert lg.apply_proposal(pr.proposal_id, actor="lesson", reason="go").ok
        lg.close()

    def test_user_path_needs_user(self, lp, fill, dbpath):
        fill.many(30, setup="T1"); fill.many(15, setup="R1")
        pr = propose(lp, {"vol_ratio_max": 1.7})
        assert last_status(dbpath, pr.proposal_id) == "needs_user"
        assert failed(lambda: lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go"))
        assert last_status(dbpath, pr.proposal_id) == "needs_user"
        assert lp.get_active_params().version_id == 1
        res = lp.apply_proposal(pr.proposal_id, actor="user", reason="approved")
        assert res.ok
        assert last_status(dbpath, pr.proposal_id) == "applied"
        assert raw(dbpath, "SELECT author FROM param_versions WHERE id=?", (res.version_id,))[0][0] == "lesson"
        assert raw(dbpath, "SELECT actor, kind FROM param_activations ORDER BY id DESC LIMIT 1") == [("user", "apply")]
        assert lp.get_active_params().params["vol_ratio_max"] == 1.7

    def test_user_approval_still_needs_evidence(self, lp, fill):
        fill.many(10, setup="T1")
        pr = propose(lp, {"vol_ratio_max": 1.7})
        assert lp.apply_proposal(pr.proposal_id, actor="user", reason="ok").code == "insufficient_evidence"

    def test_user_approval_does_not_widen_bounds(self, lp, fill, dbpath):
        fill.many(30, setup="T1"); fill.many(15, setup="R1")
        pr = propose(lp, {"vol_ratio_max": 1.7})
        # user tightens bounds afterwards; stale base -> terminal rejection
        v = lp.create_user_version({**PARAMS, "range_width_atr": 5.0}, reason="r")
        lp.activate_version(v, actor="user", reason="r")
        res = lp.apply_proposal(pr.proposal_id, actor="user", reason="ok")
        assert res.ok is False and res.code == "stale_base"
        assert last_status(dbpath, pr.proposal_id) == "rejected"

    def test_stale_after_other_apply(self, lp, fill, dbpath):
        fill.many(20, setup="R1"); fill.many(20, setup="T1")
        a = propose(lp, {"rr_min": 1.25}); b = propose(lp, {"trail_atr": 3.5})
        assert lp.apply_proposal(a.proposal_id, actor="lesson", reason="go").ok
        res = lp.apply_proposal(b.proposal_id, actor="lesson", reason="go")
        assert res.ok is False and res.code == "stale_base"
        assert last_status(dbpath, b.proposal_id) == "rejected"

    def test_apply_twice_state_error(self, lp, fill):
        fill.many(20, setup="R1")
        a = propose(lp, {"rr_min": 1.25})
        assert lp.apply_proposal(a.proposal_id, actor="lesson", reason="go").ok
        with pytest.raises(L.LedgerStateError):
            lp.apply_proposal(a.proposal_id, actor="lesson", reason="go")

    def test_apply_atomic_on_failure(self, lp, fill, dbpath):
        fill.many(20, setup="R1")
        a = propose(lp, {"rr_min": 1.25})
        with locked(dbpath):
            with pytest.raises(L.LedgerError):
                lp.apply_proposal(a.proposal_id, actor="lesson", reason="go")
        assert raw(dbpath, "SELECT COUNT(*) FROM param_versions")[0][0] == 1
        assert raw(dbpath, "SELECT COUNT(*) FROM param_activations")[0][0] == 1
        assert last_status(dbpath, a.proposal_id) == "proposed"
        assert lp.get_active_params().version_id == 1

    def test_lesson_cannot_activate_via_activate_version(self, lp, fill):
        fill.many(20, setup="R1")
        a = propose(lp, {"rr_min": 1.25})
        lp.apply_proposal(a.proposal_id, actor="lesson", reason="go")
        lp.rollback(to_version_id=1, actor="user", reason="back")
        assert failed(lambda: lp.activate_version(2, actor="user", reason="r"))
        assert lp.get_active_params().version_id == 1


# ======================================================= 8. weekly / rollback
def build_chain(lp, clock, fill):
    """v1 -> v2 (lesson, 2026-12-10T12:00) -> v3 (lesson, 2026-12-17T12:00)."""
    fill.many(20, setup="R1", version=1)
    clock.set(datetime(2026, 12, 10, 12, 0, tzinfo=UTC))
    p2 = propose(lp, {"rr_min": 1.25})
    assert lp.apply_proposal(p2.proposal_id, actor="lesson", reason="go").ok
    fill.many(20, setup="T1", version=2)
    clock.set(datetime(2026, 12, 14, 12, 0, tzinfo=UTC))
    p3 = propose(lp, {"trail_atr": 3.5}, base=2)
    assert p3.status == "proposed"
    r = lp.apply_proposal(p3.proposal_id, actor="lesson", reason="go")
    assert r.ok is False and r.code == "weekly_limit"
    clock.set(datetime(2026, 12, 17, 11, 59, 59, tzinfo=UTC))
    assert lp.apply_proposal(p3.proposal_id, actor="lesson", reason="go").code == "weekly_limit"
    clock.set(datetime(2026, 12, 17, 12, 0, 0, tzinfo=UTC))   # exactly 7d: still counted (>=), fail-closed
    assert lp.apply_proposal(p3.proposal_id, actor="lesson", reason="go").code == "weekly_limit"
    clock.set(datetime(2026, 12, 17, 12, 0, 1, tzinfo=UTC))
    r = lp.apply_proposal(p3.proposal_id, actor="lesson", reason="go")
    assert r.ok and r.version_id == 3
    return p3


class TestWeeklyAndRollback:
    def test_weekly_limit_12_8(self, lp, clock, fill, dbpath):
        p3 = build_chain(lp, clock, fill)
        assert last_status(dbpath, p3.proposal_id) == "applied"
        assert lp.get_active_params().version_id == 3
        assert lp.get_active_params().params["trail_atr"] == 3.5

    def test_weekly_limit_transient_no_event(self, lp, clock, fill, dbpath):
        fill.many(20, setup="R1")
        clock.set(datetime(2026, 12, 10, 12, 0, tzinfo=UTC))
        a = propose(lp, {"rr_min": 1.25})
        lp.apply_proposal(a.proposal_id, actor="lesson", reason="go")
        fill.many(20, setup="T1", version=2)
        b = propose(lp, {"trail_atr": 3.5}, base=2)
        n = n_status(dbpath, b.proposal_id)
        clock.set(datetime(2026, 12, 14, tzinfo=UTC))
        assert lp.apply_proposal(b.proposal_id, actor="lesson", reason="go").code == "weekly_limit"
        assert n_status(dbpath, b.proposal_id) == n
        assert last_status(dbpath, b.proposal_id) == "proposed"

    def test_user_actor_bypasses_weekly(self, lp, clock, fill, dbpath):
        fill.many(20, setup="R1")
        clock.set(datetime(2026, 12, 10, 12, 0, tzinfo=UTC))
        a = propose(lp, {"rr_min": 1.25})
        lp.apply_proposal(a.proposal_id, actor="lesson", reason="go")
        fill.many(20, setup="T1", version=2)
        b = propose(lp, {"trail_atr": 3.5}, base=2)
        clock.set(datetime(2026, 12, 11, tzinfo=UTC))
        assert lp.apply_proposal(b.proposal_id, actor="lesson", reason="go").code == "weekly_limit"
        assert lp.apply_proposal(b.proposal_id, actor="user", reason="approved").ok

    def test_rollbacks_and_user_activations_dont_count_for_weekly(self, lp, clock, fill):
        fill.many(20, setup="R1")
        clock.set(datetime(2026, 12, 10, 12, 0, tzinfo=UTC))
        v = lp.create_user_version({**PARAMS, "range_width_atr": 5.0}, reason="r")
        assert lp.activate_version(v, actor="user", reason="r").ok
        lp.rollback(to_version_id=1, actor="user", reason="r")
        a = propose(lp, {"rr_min": 1.25}, base=1)
        assert lp.apply_proposal(a.proposal_id, actor="lesson", reason="go").ok

    def test_rollback_12_8(self, lp, clock, fill, dbpath):
        p3 = build_chain(lp, clock, fill)
        nv = raw(dbpath, "SELECT COUNT(*) FROM param_versions")[0][0]
        res = lp.rollback(actor="user", reason="bad week")
        assert res.ok and res.version_id == 2
        assert raw(dbpath, "SELECT kind, version_id, prev_version_id, actor, proposal_id "
                           "FROM param_activations ORDER BY id DESC LIMIT 1") == [("rollback", 2, 3, "user", None)]
        assert raw(dbpath, "SELECT COUNT(*) FROM param_versions")[0][0] == nv
        assert last_status(dbpath, p3.proposal_id) == "applied"
        ap = lp.get_active_params()
        assert ap.version_id == 2 and ap.params["trail_atr"] == 3.0 and ap.params["rr_min"] == 1.25
        assert lp.active_activation_id() == res.activation_id
        # again -> forward to 3
        assert lp.rollback(actor="user", reason="forward").version_id == 3
        assert lp.get_active_params().params["trail_atr"] == 3.5

    def test_rollback_errors(self, lp, clock, fill):
        build_chain(lp, clock, fill)
        r = lp.rollback(to_version_id=3, actor="user", reason="r")
        assert r.ok is False and r.code == "already_active"
        r = lp.rollback(to_version_id=99, actor="user", reason="r")
        assert r.ok is False and r.code == "unknown_version"
        assert lp.get_active_params().version_id == 3
        with pytest.raises(L.LedgerValidationError):
            lp.rollback(actor="user", reason="")
        assert failed(lambda: lp.rollback(actor="system", reason="r"))
        assert lp.get_active_params().version_id == 3

    def test_rollback_explicit_target_and_lesson_actor(self, lp, clock, fill, dbpath):
        build_chain(lp, clock, fill)
        res = lp.rollback(to_version_id=1, actor="lesson", reason="auto")
        assert res.ok and res.version_id == 1
        assert lp.get_active_params().params_hash == HASH0
        assert raw(dbpath, "SELECT kind, actor, prev_version_id FROM param_activations "
                           "ORDER BY id DESC LIMIT 1") == [("rollback", "lesson", 3)]

    def test_rollback_not_weekly_limited_and_no_evidence(self, lp, fill):
        fill.many(20, setup="R1")
        a = propose(lp, {"rr_min": 1.25})
        lp.apply_proposal(a.proposal_id, actor="lesson", reason="go")
        assert lp.rollback(actor="lesson", reason="immediately").ok

    def test_rollback_with_nothing_to_roll_back_to(self, lp):
        assert failed(lambda: lp.rollback(actor="user", reason="r"))
        assert lp.get_active_params().version_id == 1

    def test_user_path_after_chain_and_get_active_each_step(self, lp, clock, fill, dbpath):
        build_chain(lp, clock, fill)
        fill.many(20, setup="R1", version=3)
        pr = propose(lp, {"stop_buffer_atr": 0.4}, base=3)
        assert lp.apply_proposal(pr.proposal_id, actor="lesson", reason="go").code == "weekly_limit"
        res = lp.apply_proposal(pr.proposal_id, actor="user", reason="approved")
        assert res.ok and res.version_id == 4
        ap = lp.get_active_params()
        assert ap.version_id == 4 and ap.params["stop_buffer_atr"] == 0.4
        assert ap.params["rr_min"] == 1.25 and ap.params["trail_atr"] == 3.5
        lp.rollback(actor="user", reason="r")
        assert lp.get_active_params().version_id == 3
        lp.rollback(to_version_id=1, actor="user", reason="r")
        assert lp.get_active_params().params_hash == HASH0
        assert raw(dbpath, "SELECT COUNT(*) FROM param_activations")[0][0] == 6


# ======================================================== 9. read / aggregate
def abc(fill):
    """Spec 12.5: A T1/trend_up/long r=+2 pnl=+20; B T1/trend_down/short r=-1 pnl=-10;
    C R1/range/long r=+0.5 pnl=+5."""
    base = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    a = fill.add(setup="T1", side="long", pnl=20.0, trade_id=1, entry_ts=base)
    b = fill.add(setup="T1", side="short", pnl=-10.0, trade_id=2, entry_ts=base + timedelta(minutes=1))
    c = fill.add(setup="R1", side="long", pnl=5.0, trade_id=3, entry_ts=base + timedelta(minutes=2))
    return a, b, c


class TestAggregate:
    def test_example_12_5(self, lp, fill):
        abc(fill)
        fill.add(setup="R1", trade_id=4, close=False)   # open: excluded
        rows = lp.aggregate_trades(["setup"])
        assert [r.key for r in rows] == [{"setup": "R1"}, {"setup": "T1"}]
        r1, t1 = rows
        assert (t1.n, t1.wins, t1.win_rate) == (2, 1, 0.5)
        assert t1.sum_r == pytest.approx(1.0) and t1.mean_r == pytest.approx(0.5)
        assert t1.median_r == pytest.approx(0.5) and t1.sum_pnl == pytest.approx(10.0)
        assert (r1.n, r1.wins, r1.win_rate) == (1, 1, 1.0)
        assert r1.sum_r == pytest.approx(0.5) and r1.mean_r == pytest.approx(0.5)
        assert r1.median_r == pytest.approx(0.5) and r1.sum_pnl == pytest.approx(5.0)

    def test_two_group_keys(self, lp, fill):
        abc(fill)
        rows = lp.aggregate_trades(["setup", "side"])
        assert len(rows) == 3
        assert [(r.key["setup"], r.key["side"]) for r in rows] == \
            [("R1", "long"), ("T1", "long"), ("T1", "short")]

    def test_other_group_keys(self, lp, fill):
        abc(fill)
        assert [r.key["regime"] for r in lp.aggregate_trades(["regime"])] == \
            ["range", "trend_down", "trend_up"]
        assert [r.n for r in lp.aggregate_trades(["pair"])] == [3]
        pv = lp.aggregate_trades(["param_version_id"])
        assert pv[0].key == {"param_version_id": 1} and pv[0].n == 3

    @pytest.mark.parametrize("gb", [[], ["bogus"], ["setup", "setup"], ["setup", "nope"]])
    def test_invalid_group_by(self, lp, gb):
        with pytest.raises(L.LedgerValidationError):
            lp.aggregate_trades(gb)

    def test_median_odd_even_and_fees(self, lp, fill):
        for pnl in (1.0, 2.0, 9.0):
            fill.add(setup="T1", pnl=pnl, fee_entry=0.1, fee_exit=0.2, funding=0.05,
                     planned_exit=100.0 + pnl)
        row = lp.aggregate_trades(["setup"])[0]
        assert row.n == 3 and row.wins == 3
        assert row.median_r == pytest.approx(0.2)           # r = [0.1, 0.2, 0.9]
        assert row.sum_pnl == pytest.approx(12.0)
        assert row.sum_fees == pytest.approx(0.9)
        assert row.sum_funding == pytest.approx(0.15)
        fill.add(setup="T1", pnl=3.0)
        row = lp.aggregate_trades(["setup"])[0]
        assert row.median_r == pytest.approx((0.2 + 0.3) / 2)

    def test_slippage_means(self, lp, fill):
        fill.add(setup="T1", pnl=1.0)  # entry slippage 0, no planned exit
        row = lp.aggregate_trades(["setup"])[0]
        assert row.mean_slippage_entry == pytest.approx(0.0)
        assert row.mean_slippage_exit is None
        fill.add(setup="T1", pnl=-2.0, planned_exit=98.0, reason="stop")  # exit == planned -> 0
        row = lp.aggregate_trades(["setup"])[0]
        assert row.mean_slippage_exit == pytest.approx(0.0)

    def test_wins_strictly_positive(self, lp, fill):
        fill.add(setup="T1", pnl=0.0)
        fill.add(setup="T1", pnl=1.0)
        row = lp.aggregate_trades(["setup"])[0]
        assert row.wins == 1 and row.win_rate == 0.5

    def test_window_since_inclusive_until_exclusive(self, lp, fill):
        t0 = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
        for i in range(3):
            fill.add(setup="T1", pnl=1.0, entry_ts=t0 + timedelta(days=i),
                     exit_ts=t0 + timedelta(days=i, hours=1))
        s = t0 + timedelta(days=1, hours=1)   # exit_ts of 2nd
        n = lambda **kw: sum(r.n for r in lp.aggregate_trades(["setup"], **kw))
        assert n() == 3
        assert n(since_ts=s) == 2
        assert n(until_ts=s) == 1
        assert n(since_ts=s, until_ts=s + timedelta(days=1)) == 1

    def test_version_filter_exact_and_not(self, lp, fill):
        abc(fill)
        v = lp.create_user_version({**PARAMS, "range_width_atr": 5.0}, reason="r")
        lp.activate_version(v, actor="user", reason="r")
        fill.add(setup="T1", version=2, pnl=3.0, trade_id=4)
        n = lambda **kw: sum(r.n for r in lp.aggregate_trades(["setup"], **kw))
        assert n(version_id=1) == 3
        assert n(version_id=2) == 1
        assert n(version_id=1, exact_version=False) == 4
        assert n() == 4

    def test_count_closed_trades(self, lp, fill):
        abc(fill); fill.add(setup="R1", close=False, trade_id=4)
        assert lp.count_closed_trades(version_id=1) == 3
        assert lp.count_closed_trades(version_id=1, setup="T1") == 2
        assert lp.count_closed_trades(version_id=1, setup="R1") == 1
        assert lp.count_closed_trades(version_id=2) == 0

    def test_trades_since_version_12_5(self, lp, fill):
        a, b, c = abc(fill)
        ids = lambda xs: [t.trade_id for t in xs]
        assert ids(lp.trades_since_version(1, exact=True)) == [a, b, c]
        assert ids(lp.trades_since_version(1, exact=True, setup="T1")) == [a, b]
        v = lp.create_user_version({**PARAMS, "range_width_atr": 5.0}, reason="r")
        lp.activate_version(v, actor="user", reason="r")
        d = fill.add(setup="T1", version=2, pnl=1.0, trade_id=4,
                     entry_ts=datetime(2026, 12, 1, 12, 5, tzinfo=UTC))
        assert ids(lp.trades_since_version(1, exact=True)) == [a, b, c]
        assert ids(lp.trades_since_version(1, exact=False)) == [a, b, c, d]
        assert ids(lp.trades_since_version(2)) == [d]
        e = fill.add(setup="T1", version=2, close=False, trade_id=5,
                     entry_ts=datetime(2026, 12, 1, 12, 6, tzinfo=UTC))
        assert ids(lp.trades_since_version(2)) == [d]
        assert ids(lp.trades_since_version(2, closed_only=False)) == [d, e]

    def test_trades_since_version_after_rollback(self, lp, fill):
        a, b, c = abc(fill)
        v = lp.create_user_version({**PARAMS, "range_width_atr": 5.0}, reason="r")
        lp.activate_version(v, actor="user", reason="r")
        d = fill.add(setup="T1", version=2, pnl=1.0, trade_id=4,
                     entry_ts=datetime(2026, 12, 1, 12, 5, tzinfo=UTC))
        lp.rollback(to_version_id=1, actor="user", reason="back")
        f = fill.add(setup="T1", version=1, pnl=1.0, trade_id=6,
                     entry_ts=datetime(2026, 12, 1, 12, 7, tzinfo=UTC))
        ids = lambda xs: [t.trade_id for t in xs]
        assert ids(lp.trades_since_version(1, exact=False)) == [f]
        assert ids(lp.trades_since_version(1, exact=True)) == [a, b, c, f]
        assert ids(lp.trades_since_version(2, exact=False)) == [d, f]

    def test_trade_list_ordering(self, lp, fill):
        t0 = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
        fill.add(trade_id=30, setup="T1", entry_ts=t0 + timedelta(minutes=5))
        fill.add(trade_id=20, setup="T1", entry_ts=t0)
        fill.add(trade_id=10, setup="T1", entry_ts=t0)
        assert [t.trade_id for t in lp.trades_since_version(1, exact=True)] == [10, 20, 30]

    def test_aggregate_row_frozen(self, lp, fill):
        abc(fill)
        with pytest.raises(dataclasses.FrozenInstanceError):
            lp.aggregate_trades(["setup"])[0].n = 5


# ====================================================== 10. fail-closed / spool
class TestFailClosed:
    def test_healthy_gate(self, lp, dbpath):
        h = lp.check_writable()
        assert h.ok is True and h.code == "ok"
        assert raw(dbpath, "SELECT COUNT(*), MIN(bot) FROM health_probes") == [(1, "learner")]
        assert lp.entries_allowed().ok is True

    def test_no_params_blocks_gate(self, led):
        h = led.entries_allowed()
        assert h.ok is False and h.code == "no_active_params"

    def test_disk_low(self, lp, monkeypatch):
        class SV:
            f_bavail = 10; f_bfree = 10; f_frsize = 4096; f_bsize = 4096; f_blocks = 100000
        monkeypatch.setattr(os, "statvfs", lambda p: SV())
        h = lp.check_writable()
        assert h.ok is False and h.code == "disk_low"
        assert lp.entries_allowed().ok is False

    def test_disk_ok_when_plenty(self, lp, monkeypatch):
        class SV:
            f_bavail = 10**7; f_bfree = 10**7; f_frsize = 4096; f_bsize = 4096; f_blocks = 10**8
        monkeypatch.setattr(os, "statvfs", lambda p: SV())
        assert lp.check_writable().ok is True

    def test_locked_db(self, lp, dbpath):
        with locked(dbpath):
            h = lp.check_writable()
        assert h.ok is False and h.code == "locked"

    def test_lock_timeout_is_write_error_with_code(self, lp, dbpath):
        with locked(dbpath):
            with pytest.raises(L.LedgerWriteError) as ei:
                lp.record_decision(dec())
        assert getattr(ei.value, "code", "locked") == "locked"
        assert raw(dbpath, "SELECT COUNT(*) FROM decision_events")[0][0] == 0

    def test_write_failure_degrades_gate_then_recovers_12_9(self, lp, dbpath):
        with locked(dbpath):
            with pytest.raises(L.LedgerWriteError):
                lp.record_decision(dec())
        h = lp.entries_allowed()
        assert h.ok is False and h.code == "degraded"
        assert lp.check_writable().ok is True
        assert lp.entries_allowed().ok is True

    def test_read_only_connection_blocks_entries(self, lp, dbpath):
        ro = L.open_ledger(dbpath, "learner", read_only=True)
        h = ro.check_writable()
        assert h.ok is False and h.code == "read_only"
        assert ro.entries_allowed().ok is False
        ro.close()

    def test_closed_connection_blocks_writes_and_gate(self, dbpath, clock):
        lg = L.open_ledger(dbpath, "learner", clock=clock)
        lg.init_params(PARAMS, reason="r")
        lg.close()
        with pytest.raises(L.LedgerError):
            lg.record_decision(dec())
        h = lg.check_writable()
        assert h.ok is False
        assert lg.entries_allowed().ok is False

    def test_corrupt_after_open_blocks_gate(self, lp, dbpath, monkeypatch):
        # sqlite errors during probe are wrapped; simulate by corrupting statvfs raising OSError
        def boom(p):
            raise OSError("io")
        monkeypatch.setattr(os, "statvfs", boom)
        h = lp.check_writable()
        assert h.ok is False and h.code in ("io_error", "disk_low")

    def test_schema_code_when_triggers_dropped_midlife(self, lp, dbpath):
        c = sqlite3.connect(str(dbpath))
        name = c.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
                         "AND tbl_name='decision_events'").fetchone()[0]
        c.execute(f'DROP TRIGGER "{name}"'); c.commit(); c.close()
        h = lp.check_writable()
        # either detected at probe time or still passes; gate must never be ok if detected
        if not h.ok:
            assert h.code == "schema"

    def test_unledgered_blocks_gate(self, lp):
        import inspect
        lp.record_decision(dec()); lp.record_trade_entry(entry(trade_id=7))
        assert lp.find_unledgered_trades([7, 9]) == [9]
        params = [p for p in inspect.signature(lp.entries_allowed).parameters.values()]
        if not params:
            pytest.skip("spec does not define how entries_allowed receives freqtrade ids")
        h = lp.entries_allowed(**{params[0].name: [7, 9]})
        assert h.ok is False and h.code == "unledgered_trades"

    # ---- spool
    def test_entry_failure_spools_and_drains_12_9(self, lp, dbpath):
        lp.record_decision(dec())
        spool = str(dbpath) + ".spool.jsonl"
        with locked(dbpath):
            try:
                lp.record_trade_entry(entry())
            except L.LedgerError:
                pass
            lines = [l for l in open(spool).read().splitlines() if l.strip()]
            assert len(lines) == 1
            json.loads(lines[0])
            h = lp.entries_allowed()
            assert h.ok is False and h.code in ("spool_pending", "degraded")
        assert raw(dbpath, "SELECT COUNT(*) FROM trade_entries")[0][0] == 0
        assert lp.drain_spool() == 1
        assert not os.path.exists(spool) or open(spool).read().strip() == ""
        assert lp.get_trade(7) is not None
        assert lp.check_writable().ok
        assert lp.entries_allowed().ok is True
        # same spool line drained twice -> single ledger row
        with open(spool, "a") as f:
            f.write(lines[0] + "\n" + lines[0] + "\n")
        lp.drain_spool()
        assert raw(dbpath, "SELECT COUNT(*) FROM trade_entries")[0][0] == 1
        assert not os.path.exists(spool) or open(spool).read().strip() == ""

    def test_exit_failure_spools_never_blocks(self, lp, dbpath):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        spool = str(dbpath) + ".spool.jsonl"
        with locked(dbpath):
            try:
                lp.record_trade_exit(xit())
            except L.LedgerError:
                pass
            lines = [l for l in open(spool).read().splitlines() if l.strip()]
            assert len(lines) == 1 and json.loads(lines[0])
            assert lp.entries_allowed().ok is False
        assert lp.get_trade(7).exit_ts is None
        assert lp.drain_spool() == 1
        t = lp.get_trade(7)
        assert t.realized_pnl == pytest.approx(22.688)
        assert lp.check_writable().ok and lp.entries_allowed().ok

    def test_exit_allowed_while_gate_closed(self, lp, dbpath):
        lp.record_decision(dec()); lp.record_trade_entry(entry())
        with locked(dbpath):
            with pytest.raises(L.LedgerWriteError):
                lp.record_decision(dec(pair="BTC/USDT"))   # degrade
        assert lp.entries_allowed().ok is False
        # DB writable again but gate still closed (degraded): exit must go through
        assert lp.record_trade_exit(xit()) >= 1
        assert lp.get_trade(7).realized_pnl == pytest.approx(22.688)
        assert raw(dbpath, "SELECT COUNT(*) FROM trade_exits")[0][0] == 1

    def test_exit_allowed_when_disk_low(self, lp, monkeypatch):
        lp.record_decision(dec()); lp.record_trade_entry(entry())

        class SV:
            f_bavail = 1; f_bfree = 1; f_frsize = 4096; f_bsize = 4096; f_blocks = 100
        monkeypatch.setattr(os, "statvfs", lambda p: SV())
        assert lp.check_writable().code == "disk_low"
        assert lp.record_trade_exit(xit()) >= 1

    def test_spool_survives_restart(self, lp, dbpath, clock):
        lp.record_decision(dec())
        with locked(dbpath):
            try:
                lp.record_trade_entry(entry())
            except L.LedgerError:
                pass
        lp.close()
        lg = L.open_ledger(dbpath, "learner", clock=clock)
        h = lg.entries_allowed()
        if h.ok:      # entries_allowed drains the spool on its own
            assert lg.get_trade(7) is not None
        else:
            assert h.code in ("spool_pending", "degraded")
        lg.close()

    def test_drain_empty(self, lp):
        assert lp.drain_spool() == 0

    def test_validation_error_writes_nothing_and_no_spool(self, lp, dbpath):
        with pytest.raises(L.LedgerValidationError):
            lp.record_decision(dec(side="sideways"))
        assert not os.path.exists(str(dbpath) + ".spool.jsonl")


# =========================================================== 11. concurrency
class TestConcurrency:
    def test_reader_sees_committed_writes(self, lp, dbpath):
        rd = L.open_ledger(dbpath, "learner", read_only=True)
        assert rd.list_decisions() == []
        lp.record_decision(dec())
        assert len(rd.list_decisions()) == 1
        rd.close()

    def test_reader_not_blocked_by_writer_lock(self, lp, dbpath):
        rd = L.open_ledger(dbpath, "learner", read_only=True)
        lp.record_decision(dec())
        with locked(dbpath) as c:
            c.execute("INSERT INTO health_probes(bot, probed_at) VALUES ('learner','2026-12-01T00:00:00.000Z')")
            assert rd.get_active_params().version_id == 1
            assert len(rd.list_decisions()) == 1
            assert rd.aggregate_trades(["setup"]) == []
            assert rd.list_open_trades() == []
        assert raw(dbpath, "SELECT COUNT(*) FROM health_probes")[0][0] == 0
        rd.close()

    def test_second_writer_blocked_while_locked(self, lp, dbpath, clock):
        w2 = L.open_ledger(dbpath, "learner", clock=clock)
        with locked(dbpath):
            with pytest.raises(L.LedgerWriteError):
                w2.record_decision(dec())
        w2.close()

    def test_two_writers_alternate(self, lp, dbpath, clock):
        w2 = L.open_ledger(dbpath, "learner", clock=clock)
        ids = []
        for i in range(6):
            w = lp if i % 2 == 0 else w2
            ids.append(w.record_decision(dec(pair=f"P{i}/USDT")))
        assert ids == sorted(set(ids)) and len(ids) == 6
        assert len(lp.list_decisions()) == 6 == len(w2.list_decisions())
        w2.close()

    def test_proposer_and_bot_interleave(self, lp, dbpath, clock):
        svc = L.open_ledger(dbpath, "learner", clock=clock)       # lesson service writer
        bot = lp
        r = propose(svc, {"rr_min": 1.25})
        bot.record_decision(dec())
        assert r.status == "proposed"
        assert bot.get_proposal(r.proposal_id) is not None
        svc.close()

    def test_threads_share_one_ledger(self, lp, dbpath):
        errs = []

        def work(k):
            try:
                for i in range(5):
                    lp.record_decision(dec(pair=f"T{k}x{i}/USDT"))
            except Exception as e:      # pragma: no cover
                errs.append(e)
        ts = [threading.Thread(target=work, args=(k,)) for k in range(4)]
        [t.start() for t in ts]; [t.join() for t in ts]
        assert errs == []
        assert raw(dbpath, "SELECT COUNT(*) FROM decision_events")[0][0] == 20
        ids = [r[0] for r in raw(dbpath, "SELECT id FROM decision_events ORDER BY id")]
        assert ids == list(range(1, 21))

    def test_ordering_is_by_id_not_clock(self, lp, dbpath, clock):
        lp.record_decision(dec())
        clock.set(datetime(2026, 12, 1, 9, 0, tzinfo=UTC))   # clock goes backwards
        lp.record_decision(dec(pair="BTC/USDT", bar_close_ts=datetime(2026, 12, 1, 9, 0, tzinfo=UTC)))
        assert [r[0] for r in raw(dbpath, "SELECT id FROM decision_events ORDER BY id")] == [1, 2]
        assert lp.get_active_params().version_id == 1
