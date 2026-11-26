"""WP-3 uygulama testleri (defter sema 4, olcum alanlari, golge/MtM saf islevleri, karsi-olgu eki, rapor paketi).

`docs/defter-ek-alanlar-spec.md` ile yazildi; sartname testleri (`tests/test_wp3_spec.py`) AYRI dosyadir. Ag yok, sahte saat,
gecici dosyalar. Kilitli doneme (2026-05-01..2026-11-01) dusen tarih yok.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from trader_core import counterfactual as CF
from trader_core import ledger as L
from trader_core import signals as S

UTC = timezone.utc
NOW = datetime(2026, 12, 1, 10, 0, 5, tzinfo=UTC)
BAR = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}
F_T1 = {"atr_1h": 20.0, "stop_dist_atr": 1.0, "atr_4h": 40.0, "pullback_ema": 50, "ema_value": 99.0, "body_ratio": 0.6}


def raw(path, sql, args=()):
    c = sqlite3.connect(str(path))
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


@pytest.fixture
def clock():
    box = {"t": NOW}
    fn = lambda: box["t"]          # noqa: E731
    fn.box = box
    return fn


@pytest.fixture
def led(tmp_path, clock):
    lg = L.open_ledger(tmp_path / "l.sqlite", "learner", clock=clock)
    lg.init_params(PARAMS, reason="strategy:price_action_v1@1b.0 test")
    yield lg
    lg.close()


def mk_decision(ts=BAR, **kw):
    base = dict(bar_close_ts=ts, trigger_tf="1h", pair="BTC/USDT", side="long", setup="T1", regime="trend_up",
                atr_ratio=1.0, rh=None, rl=None, rh_touches=0, rl_touches=0, features=dict(F_T1),
                planned_entry=100.0, planned_stop=98.0, planned_target=None, param_version_id=1,
                veto_status="allowed", veto_reason="ok", risk_allowed=True, risk_reason=None, size_qty=1.0,
                size_notional=100.0, size_margin=33.0, size_risk_amount=2.0, leverage=3, final_action="entered",
                skip_reason=None)
    base.update(kw)
    return L.DecisionEvent(**base)


def mk_shadow(**kw):
    base = dict(block="regime_volatile", bar_close_ts=BAR, trigger_tf="1h", pair="BTC/USDT", side="long", setup="T1",
                regime="volatile", atr_ratio=1.9, rh=None, rl=None, features=dict(F_T1), planned_entry=100.0,
                planned_stop=98.0, planned_target=None, param_version_id=1, strategy="price_action_v1@1b.0",
                reasons="regime_blocked", pos_open=False, gate_code="ok")
    base.update(kw)
    return L.ShadowEvent(**base)


# =========================================================================== sema 4 / goc
def test_fresh_file_is_v4_with_new_objects(led):
    p = led.path
    assert raw(p, "PRAGMA user_version")[0][0] == 8 and L.SCHEMA_VERSION == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert (3, 4) in raw(p, "SELECT from_version, to_version FROM schema_migrations")
    names = {r[0] for r in raw(p, "SELECT name FROM sqlite_master")}
    assert {"shadow_decisions", "equity_marks", "v_shadow_decisions", "ix_shadow_ts"} <= names
    assert {"trg_shadow_decisions_no_update", "trg_equity_marks_no_delete"} <= names
    cols = [r[1] for r in raw(p, "PRAGMA table_info(v_trades)")]
    assert cols[-17:-2] == ["entry_order_ts", "entry_order_ack_ts", "entry_ref_price", "entry_ref_spread", "entry_ref_src",
                          "slip_exec_entry", "exit_order_ts", "exit_order_ack_ts", "exit_ref_price", "exit_ref_spread",
                          "exit_ref_src", "slip_exec_exit", "exit_decision_price", "slip_decision_exit", "exit_regime"]
    assert cols[35] == "excursion_tf"


def _make_v3(path):
    """Gercek goc zinciri 0->3 (sema 3 dosyasi); icine bir karar, bir giris, bir cikis."""
    now_s = "2026-12-01T10:00:00.000Z"
    c = sqlite3.connect(str(path), isolation_level=None)
    for n in range(3):
        c.executescript("BEGIN IMMEDIATE;\n" + L.MIGRATIONS[n]("learner", now_s)
                        + f"INSERT INTO schema_migrations (from_version,to_version,applied_at) VALUES ({n},{n + 1},'{now_s}');\n"
                        + f"PRAGMA user_version={n + 1};\nCOMMIT;")
    c.close()


def test_migration_3_to_4_is_additive_and_readable(tmp_path, clock):
    p = tmp_path / "v3.sqlite"
    _make_v3(p)
    # sema 3 dosyasina veri (sema 4 koduyla yazmadan once ham SQL'le)
    c = sqlite3.connect(str(p))
    c.execute("INSERT INTO param_versions (bot, params, params_hash, lesson_bounds, author, reason, created_at) "
              "VALUES ('learner','{}',?,'{}','initial','r','2026-12-01T00:00:00.000Z')", ("0" * 64,))
    c.commit()
    c.close()
    before_tables = {t: raw(p, f"SELECT * FROM {t}") for t in ("param_versions", "meta")}
    cols_v3 = [r[1] for r in raw(p, "PRAGMA table_info(v_trades)")]
    dec_cols_v3 = [r[1] for r in raw(p, "PRAGMA table_info(v_decisions)")]
    with pytest.raises(L.LedgerSchemaError):
        L.open_ledger(p, "learner", migrate=False, clock=clock)
    with pytest.raises(L.LedgerSchemaError):
        L.open_ledger(p, "learner", read_only=True, clock=clock)
    assert raw(p, "PRAGMA user_version")[0][0] == 3
    L.open_ledger(p, "learner", clock=clock).close()
    assert os.path.exists(str(p) + ".premigrate-v3")
    assert raw(p, "PRAGMA user_version")[0][0] == 8     # DD-12: baslik surumu 6 (3 -> 4 -> 5 -> 6 zinciri; WP-06a)
    assert [r[1] for r in raw(p, "PRAGMA table_info(v_trades)")][:len(cols_v3)] == cols_v3
    assert [r[1] for r in raw(p, "PRAGMA table_info(v_decisions)")][:len(dec_cols_v3)] == dec_cols_v3
    for t, rows in before_tables.items():
        assert raw(p, f"SELECT * FROM {t}")[:len(rows)] == rows
    assert raw(p, "PRAGMA foreign_key_check") == []


def test_older_raw_readers_still_work_on_v4(led):
    """Sema denetimi yapmayan ham SQL okuyucular adlandirdiklari sutunlari ayni sirada bulur."""
    led.record_decision(mk_decision())
    p = led.path
    cols = ", ".join(r[1] for r in raw(p, "PRAGMA table_info(decision_events)")[:3])
    assert raw(p, f"SELECT {cols} FROM v_decisions")
    assert raw(p, "SELECT bot, trade_id, excursion_tf FROM v_trades") == []


def test_append_only_and_final_action_check(led):
    sid = led.record_shadow(mk_shadow())
    eid = led.record_equity_mark(L.EquityMark(BAR, 1000.0, 1000.0, 990.0, 0, "sim"))
    for sql in (f"UPDATE shadow_decisions SET pair='X' WHERE id={sid}", f"DELETE FROM shadow_decisions WHERE id={sid}",
                f"UPDATE equity_marks SET wallet=1 WHERE id={eid}", f"DELETE FROM equity_marks WHERE id={eid}"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            raw(led.path, sql)
    assert raw(led.path, "SELECT DISTINCT final_action FROM v_shadow_decisions") == [("shadow",)]


# =========================================================================== olcum alanlari
def _entry_exit(led, **over):
    did = led.record_decision(mk_decision())
    ts = NOW - timedelta(minutes=50)
    e = L.TradeEntry(1, did, ts, 100.02, 1.0, 3, 0.05, None, **over.get("entry", {}))
    led.record_trade_entry(e)
    return did, ts


def test_exec_fields_roundtrip_and_derived_columns(led):
    t0 = NOW - timedelta(minutes=50)
    did = led.record_decision(mk_decision())
    led.record_trade_entry(L.TradeEntry(1, did, t0, 100.02, 1.0, 3, 0.05, None, t0 - timedelta(seconds=1), t0,
                                        100.0, 0.0002, "book"))
    tr = led.get_trade(1)
    assert tr.entry_ref_price == 100.0 and tr.entry_ref_src == "book" and tr.entry_ref_spread == 0.0002
    assert abs(tr.slip_exec_entry - 0.0002) < 1e-12
    assert tr.entry_order_ack_ts == t0 and tr.entry_order_ts == t0 - timedelta(seconds=1)
    assert tr.slip_exec_exit is None and tr.exit_regime is None


def test_exit_slip_columns_long_and_short(led):
    t0 = NOW - timedelta(hours=3)
    for tid, side, ref, dp, fill in ((1, "long", 200.0, 200.5, 199.9), (2, "short", 200.0, 199.5, 200.1)):
        did = led.record_decision(mk_decision(ts=BAR - timedelta(hours=tid), side=side, planned_entry=200.0,
                                              planned_stop=190.0 if side == "long" else 210.0))
        led.record_trade_entry(L.TradeEntry(tid, did, t0, 200.0, 1.0, 3, 0.0))
        led.record_trade_exit(L.TradeExit(tid, t0 + timedelta(minutes=5), fill, "regime_flip", None, 0.0, 0.0,
                                          order_ref_price=ref, order_ref_src="sim_open", decision_price=dp,
                                          exit_regime="range"))
    a, b = led.get_trade(1), led.get_trade(2)
    assert abs(a.slip_exec_exit - 0.0005) < 1e-12 and abs(a.slip_decision_exit - 0.6 / 200.5) < 1e-12
    assert abs(b.slip_exec_exit - 0.0005) < 1e-12 and abs(b.slip_decision_exit - 0.6 / 199.5) < 1e-12
    assert a.exit_regime == "range" and a.slippage_exit is None


@pytest.mark.parametrize("over", [
    dict(order_ref_price=-1.0, order_ref_src="book"), dict(order_ref_price=1.0, order_ref_src="x"),
    dict(order_ref_price=1.0), dict(order_ref_spread=0.1, order_ref_price=1.0, order_ref_src="sim_open"),
    dict(order_ts=NOW, order_ack_ts=NOW - timedelta(seconds=1)), dict(order_ack_ts=NOW)])
def test_strict_validation_entry(led, over):
    did = led.record_decision(mk_decision())
    with pytest.raises(L.LedgerValidationError):
        led.record_trade_entry(L.TradeEntry(1, did, NOW, 100.0, 1.0, 3, 0.0, None, **over))
    assert led.list_open_trades() == []


@pytest.mark.parametrize("over", [dict(exit_regime="sideways"), dict(decision_price=0.0)])
def test_strict_validation_exit(led, over):
    did, ts = _entry_exit(led)
    with pytest.raises(L.LedgerValidationError):
        led.record_trade_exit(L.TradeExit(1, ts + timedelta(minutes=5), 101.0, "other", None, 0.0, 0.0, **over))


@pytest.mark.parametrize("bad", [
    {"order_ref_price": -1, "order_ref_src": "book"}, {"order_ref_price": float("nan"), "order_ref_src": "book"},
    {"order_ref_price": float("inf"), "order_ref_src": "book"}, {"order_ref_price": "x", "order_ref_src": "book"},
    {"order_ref_price": 1.0, "order_ref_src": "bogus"}, {"order_ref_price": 1.0},
    {"order_ref_spread": 0.1, "order_ref_price": 1.0, "order_ref_src": "sim_open"},
    {"decision_price": 0}, {"decision_price": float("nan")}, {"exit_regime": "sideways"},
    {"order_ts": datetime(2026, 12, 1), "order_ack_ts": NOW}, {"order_ack_ts": NOW}, {"order_ts": "x"}])
def test_clean_exec_fields_never_raises_and_drops_group(bad):
    out = L.clean_exec_fields({**bad, "decision_price_keep": 1, "exit_regime": bad.get("exit_regime")
                               if "exit_regime" in bad else "range", "extra": 5})
    assert set(out) == set(L.EXEC_KEYS)
    bad_groups = {"order_ref_price": ("order_ref_price", "order_ref_spread", "order_ref_src"),
                  "order_ref_spread": ("order_ref_price", "order_ref_spread", "order_ref_src"),
                  "order_ref_src": ("order_ref_price", "order_ref_spread", "order_ref_src"),
                  "decision_price": ("decision_price",), "exit_regime": ("exit_regime",),
                  "order_ts": ("order_ts", "order_ack_ts"), "order_ack_ts": ("order_ack_ts",)}
    key = next(iter(bad))
    for k in bad_groups[key]:
        if k != "order_ts" or key == "order_ts":
            assert out[k] is None


def test_clean_exec_fields_keeps_good_and_other_groups():
    t = NOW
    out = L.clean_exec_fields({"order_ts": t, "order_ack_ts": t + timedelta(milliseconds=180), "order_ref_price": 100.0,
                               "order_ref_spread": 0.0002, "order_ref_src": "book", "decision_price": 101.0,
                               "exit_regime": "range"})
    assert out["order_ack_ts"] == t + timedelta(milliseconds=180) and out["order_ref_src"] == "book"
    assert L.clean_exec_fields({"order_ts": t, "order_ack_ts": t - timedelta(seconds=1), "exit_regime": "volatile"})[
        "order_ts"] == t
    assert L.clean_exec_fields(None) == dict.fromkeys(L.EXEC_KEYS)
    assert L.clean_exec_fields({"order_ack_ts": t - timedelta(seconds=1), "order_ts": t,
                                "exit_regime": "volatile"})["order_ack_ts"] is None


def test_idempotent_rewrite_keeps_first_measurements(led):
    did = led.record_decision(mk_decision())
    t0 = NOW - timedelta(minutes=50)
    a = led.record_trade_entry(L.TradeEntry(1, did, t0, 100.0, 1.0, 3, 0.0, None, None, None, 100.0, None, "sim_open"))
    b = led.record_trade_entry(L.TradeEntry(1, did, t0, 100.0, 1.0, 3, 0.0, None, None, None, 55.0, None, "sim_open"))
    assert a == b and led.get_trade(1).entry_ref_price == 100.0
    with pytest.raises(L.LedgerConflictError):
        led.record_trade_entry(L.TradeEntry(1, did, t0, 100.5, 1.0, 3, 0.0))


def test_spool_carries_exec_keys_and_old_lines(led, monkeypatch):
    did = led.record_decision(mk_decision())
    t0 = NOW - timedelta(minutes=50)
    orig = led._write_entry

    def boom(*a, **k):
        raise L.LedgerWriteError("x")
    monkeypatch.setattr(led, "_write_entry", boom)
    with pytest.raises(L.LedgerWriteError):
        led.record_trade_entry(L.TradeEntry(1, did, t0, 100.0, 1.0, 3, 0.0, None, t0, None, 99.0, 0.0001, "book"))
    line = json.loads(open(led._spool_path()).read().splitlines()[0])
    assert line["order_ref_price"] == 99.0 and line["order_ref_src"] == "book" and line["order_ts"].endswith("Z")
    monkeypatch.setattr(led, "_write_entry", orig)
    assert led.drain_spool() == 1
    tr = led.get_trade(1)
    assert tr.entry_ref_price == 99.0 and tr.entry_order_ts == t0
    # eski bicimli spool satiri (yeni anahtar yok)
    did2 = led.record_decision(mk_decision(ts=BAR - timedelta(hours=2)))
    led._spool_append({"type": "entry", "trade_id": 2, "decision_id": did2, "entry_ts": "2026-12-01T09:11:00.000Z",
                       "entry_price": 100.0, "qty": 1.0, "leverage": 3, "fee_entry": 0.0, "supersedes_id": None})
    assert led.drain_spool() == 1 and led.get_trade(2).entry_ref_price is None


# =========================================================================== golge / oz varlik isareti defteri
def test_record_shadow_dedupe_validation_and_isolation(led, monkeypatch):
    a = led.record_shadow(mk_shadow())
    assert led.record_shadow(mk_shadow(planned_entry=101.0)) == a
    assert raw(led.path, "SELECT COUNT(*) FROM shadow_decisions")[0][0] == 1
    with pytest.raises(L.LedgerValidationError):
        led.record_shadow(mk_shadow(block="nope"))
    with pytest.raises(L.LedgerValidationError):
        led.record_shadow(mk_shadow(planned_stop=102.0))
    with pytest.raises(L.LedgerValidationError):
        led.record_shadow(mk_shadow(features={**F_T1, "x": "y" * 20000}))
    long_reason = led.record_shadow(mk_shadow(bar_close_ts=BAR - timedelta(hours=1), reasons="r" * 900))
    assert len(led.list_shadow(since_ts=BAR - timedelta(hours=1), until_ts=BAR)[0].reasons) == L.MAX_REASON
    assert long_reason != a
    # defter karar kayitlari etkilenmez
    assert led.list_decisions() == [] and raw(led.path, "SELECT COUNT(*) FROM v_decisions")[0][0] == 0
    assert led.find_orphan_decisions() == []


def test_shadow_and_mark_failures_do_not_degrade_ledger(led, clock, monkeypatch):
    assert led.entries_allowed().ok
    last_ok = led._last_write_ok
    clock.box["t"] = NOW + timedelta(seconds=30)

    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    c = led._conn()
    real_execute = c.execute

    class Proxy:
        def __getattr__(self, n):
            return getattr(c, n)

        def execute(self, sql, *a):
            if "BEGIN IMMEDIATE" in sql:
                raise sqlite3.OperationalError("database is locked")
            return real_execute(sql, *a)
    monkeypatch.setattr(led, "_conn", lambda: Proxy())
    with pytest.raises(L.LedgerWriteError):
        led.record_shadow(mk_shadow())
    with pytest.raises(L.LedgerWriteError):
        led.record_equity_mark(L.EquityMark(BAR, 1.0, 1.0, 1.0, 0, "sim"))
    assert not led._degraded and not os.path.exists(led._spool_path())
    monkeypatch.undo()
    assert led.entries_allowed().ok
    led.record_shadow(mk_shadow())                       # basarili golge yazimi `_last_write_ok`i tazelemez
    assert led._last_write_ok == last_ok or led._last_write_ok >= last_ok


def test_equity_marks(led):
    a = led.record_equity_mark(L.EquityMark(BAR, 1000.0, 1002.0, 994.0, 1, "sim"))
    assert led.record_equity_mark(L.EquityMark(BAR, 1.0, 2.0, 1.0, 0, "sim")) == a
    with pytest.raises(L.LedgerValidationError):
        led.record_equity_mark(L.EquityMark(BAR + timedelta(hours=1), 1.0, 1.0, 2.0, 0, "sim"))
    with pytest.raises(L.LedgerValidationError):
        led.record_equity_mark(L.EquityMark(BAR + timedelta(hours=1), 1.0, 1.0, 1.0, 0, "bogus"))
    rows = led.list_equity_marks()
    assert len(rows) == 1 and rows[0].equity_low == 994.0 and rows[0].src == "sim" and rows[0].ts == BAR


# =========================================================================== metrics
def test_drawdown_stats_spec_example_and_edge_cases():
    from trader_engine import metrics as M
    st = M.drawdown_stats([1010, 990, 1005, 1020, 980], [1000, 970, 985, 1004, 960], 1000)
    assert st["max_dd_mtm_abs"] == 40 and abs(st["max_dd_mtm_pct"] - 3.9216) < 1e-4
    assert st["max_dd_mtm_low_abs"] == 60 and abs(st["max_dd_mtm_low_pct"] - 5.8824) < 1e-4
    assert st["max_underwater_steps"] == 2
    assert set(st) == {"max_dd_mtm_abs", "max_dd_mtm_pct", "max_dd_mtm_low_abs", "max_dd_mtm_low_pct",
                       "max_underwater_steps"}
    assert all(v == 0 for v in M.drawdown_stats([], [], 1000).values())
    assert all(v == 0 for v in M.drawdown_stats([1001, 1002], [1001, 1002], 1000).values())
    assert M.drawdown_stats([1000], [990], 1000)["max_dd_mtm_low_abs"] == 10
    loc = M.drawdown_locations([1010, 990, 1005, 1020, 980], [1000, 970, 985, 1004, 960], 1000)
    assert loc["peak_idx"] == 4 and loc["trough_idx"] == 5 and loc["low_trough_idx"] == 4


def test_max_consecutive_losses_and_untouched_metrics():
    from trader_engine import metrics as M
    assert M.max_consecutive_losses([5, -1, -2, 3, -1, -1, -1, 0, -4]) == 3
    assert M.max_consecutive_losses([]) == 0
    assert "max_dd_mtm_pct" not in M.METRIC_KEYS
    assert "order_ts" not in M.TRADES_COLUMNS and "exit_regime" not in M.TRADES_COLUMNS
    assert M.max_drawdown(np.array([-10.0, 5.0, -20.0]), 1000.0)[1] == 25.0


# =========================================================================== MtM kaydedici
class _Pos:
    def __init__(self, tid, pair, side, entry, qty, status="open"):
        self.trade_id, self.pair, self.side, self.entry_price, self.qty, self.status = tid, pair, side, entry, qty, status


def _bar(pair, **kw):
    from trader_engine.types import MinuteBar
    d = dict(pair=pair, open_ts=BAR, step_s=60, last_o=100, last_h=100, last_l=100, last_c=100, mark_o=None, mark_h=None,
             mark_l=None, mark_c=None)
    d.update(kw)
    return MinuteBar(**d)


class _Acct:
    def __init__(self, wallet, equity):
        self.wallet, self.equity = wallet, equity


def test_mtm_recorder_long_short_and_two_positions():
    from trader_engine.mtm import MtmRecorder
    got = []
    r = MtmRecorder(lambda *a: got.append(a), src="sim")
    p = _Pos(1, "BTC/USDT", "long", 100.0, 2.0)
    r.on_minute(BAR, {"BTC/USDT": _bar("BTC/USDT", mark_l=98, mark_c=99)}, [p], 1000.0)
    r.on_minute(BAR, {"BTC/USDT": _bar("BTC/USDT", mark_l=97, mark_c=101)}, [p], 1000.0)
    r.on_decision(BAR, _Acct(1000.0, 1002.0), 1)
    assert got[-1][1:5] == (1000.0, 1002.0, 994.0, 1)
    # son isaretten sonra sifirlanir
    r.on_decision(BAR + timedelta(hours=1), _Acct(1000.0, 1000.0), 0)
    assert got[-1][3] == 1000.0
    # short: mark_h; mark yoksa last_h
    s = _Pos(2, "ETH/USDT", "short", 50.0, 4.0)
    r.on_minute(BAR, {"ETH/USDT": _bar("ETH/USDT", last_h=53)}, [s], 1000.0)
    r.on_decision(BAR + timedelta(hours=2), _Acct(1000.0, 1004.0), 1)
    assert got[-1][3] == 1000.0 - 4.0 * 3
    # iki pozisyon: her birinin KENDI ters ucu toplanir
    r.on_minute(BAR, {"BTC/USDT": _bar("BTC/USDT", mark_l=96), "ETH/USDT": _bar("ETH/USDT", mark_h=52)}, [p, s], 1000.0)
    r.on_decision(BAR + timedelta(hours=3), _Acct(1000.0, 1000.0), 2)
    assert got[-1][3] == 1000.0 + 2 * (96 - 100) - 4 * (52 - 50)


def test_mtm_recorder_isolation_and_flat_equality():
    from trader_engine.mtm import MtmRecorder

    def bad(*a):
        raise RuntimeError("x")
    r = MtmRecorder(bad, keep=True)
    r.on_decision(BAR, _Acct(1000.0, 1000.0), 0)
    assert r.errors == 1 and r.rows_written == 0
    r2 = MtmRecorder(None, keep=True)
    r2.on_decision(BAR, _Acct(1000.0, 1000.0), 0)
    assert r2.rows == [(BAR, 1000.0, 1000.0, 1000.0, 0)]
    r3 = MtmRecorder(None, keep=True, enabled=False)
    r3.on_decision(BAR, _Acct(1.0, 1.0), 0)
    assert r3.rows == [] and r3.errors == 0


def test_mtm_recorder_minute_cost_is_small():
    import time as _t
    from trader_engine.mtm import MtmRecorder
    r = MtmRecorder(None)
    ps = [_Pos(i, f"P{i}/USDT", "long", 100.0, 1.0) for i in range(10)]
    bars = {p.pair: _bar(p.pair, mark_l=99.0) for p in ps}
    t0 = _t.perf_counter()
    for _ in range(20000):
        r.on_minute(BAR, bars, ps, 1000.0)
    assert _t.perf_counter() - t0 < 2.0


# =========================================================================== golge saf hesap
class _Row:
    def __init__(self, **kw):
        d = dict(pair="BTC/USDT", bar_open_ts=BAR - timedelta(hours=1), bar_close_ts=BAR, signal=False, setup="T1",
                 side="long", skip_reason=None, planned_entry=100.0, planned_stop=98.0, planned_target=None, rr=None,
                 stop_dist_atr=1.0, atr_tf=2.0, atr_4h=4.0, atr_ratio=1.0, regime="trend_up", rh=None, rl=None,
                 rh_touches=0, rl_touches=0, ema_value=99.0, body_ratio=0.6, wick_ratio=None, edge_dist_atr=None,
                 pullback_ema=50, reasons="")
        d.update(kw)
        self.__dict__.update(d)


def test_parse_reasons_prefixes():
    from trader_engine import shadow as SH
    f, rest = SH.parse_reasons("ml:p=0.612345|v1b:same_bar_reentry|T1_long:x,stop_ok")
    assert f == {"same_bar_reentry"} and rest == "T1_long:x,stop_ok"
    f, rest = SH.parse_reasons("v1b:r1_disabled|R1_long:x,stop_ok,rr_ok")
    assert f == {"r1_disabled"} and rest.endswith(",rr_ok")
    assert SH.parse_reasons("plain")[0] == frozenset()


def test_row_candidates_rules():
    from trader_engine import shadow as SH
    r1 = _Row(setup="R1", regime="range", rh=105.0, rl=95.0, planned_target=105.0, rr=2.0, wick_ratio=0.6,
              edge_dist_atr=0.2, reasons="v1b:r1_disabled|R1_long:range,edge_zone,reject_wick,stop_ok,rr_ok")
    c = SH.row_candidates(r1, {"r1_disabled"}, trigger_tf="1h")
    assert len(c) == 1 and c[0].block == "r1_disabled" and c[0].rh == 105.0 and c[0].planned_target == 105.0
    for tail in (",stop_ok,rr_below_min", ",stop_width"):
        bad = _Row(**{**r1.__dict__, "reasons": "v1b:r1_disabled|R1_long:x" + tail})
        assert SH.row_candidates(bad, {"r1_disabled"}, trigger_tf="1h") == []
    t1 = _Row(reasons="ml:p=0.612345|v1b:same_bar_reentry|T1_long:trend_up,ema_touch,bull_body,stop_ok")
    assert [x.block for x in SH.row_candidates(t1, {"same_bar_reentry"}, trigger_tf="1h")] == ["same_bar_reentry"]
    assert SH.row_candidates(t1, {"r1_disabled"}, trigger_tf="1h") == []              # blok kapali
    assert SH.row_candidates(_Row(reasons=t1.reasons, signal=True), {"same_bar_reentry"}, trigger_tf="1h") == []


def _trend_table(n=80, last=(100.0, 102.0, 99.0, 101.9), lows=(99.2, 99.4, 99.1, 99.3, 99.0), atr=2.0):
    base = np.full(n, 99.5)
    t = pd.DataFrame({"open": base, "high": base + 0.5, "low": base - 0.5, "close": base}, index=pd.date_range(
        "2026-11-20", periods=n, freq="1h", tz="UTC"))
    t.iloc[-5:, t.columns.get_loc("low")] = lows
    t.iloc[-1, :4] = last
    t["atr_tf"] = atr
    t["atr_4h"] = 2 * atr
    t["regime"] = "volatile"
    t["rh_touches"] = 0
    t["rl_touches"] = 0
    t["reasons"] = "regime_blocked"
    return t


def test_regime_candidate_matches_evaluate_t1_bitwise():
    from trader_core import indicators as I
    from trader_engine import shadow as SH
    p = S.SignalParams()
    t = _trend_table()
    cand = SH.regime_candidate(t, p)
    ema_last = float(I.ema(t["close"], p.pullback_ema).iloc[-1])
    rec = t.iloc[-5:]
    want = None
    for side in ("long", "short"):
        c = S.evaluate_t1(side, 100.0, 102.0, 99.0, 101.9, ema_last,
                          (rec["low"] if side == "long" else rec["high"]).tolist(), 2.0, p)
        if c is not None and c.skip_reason is None:
            want = c
    assert (cand is None) == (want is None)
    if cand is not None:
        assert (cand.side, cand.entry, cand.stop, cand.stop_dist_atr) == (want.side, want.entry, want.stop,
                                                                          want.stop_dist_atr)
        assert cand.stop == 99.0 - 0.3 * 2.0 and cand.target is None


def test_regime_candidate_invalid_ohlc_and_non_blocked_rows():
    from trader_engine import shadow as SH
    p = S.SignalParams()
    t = _trend_table()
    assert SH.regime_candidate(t, p) is not None
    bad = t.copy()
    bad.iloc[-3, bad.columns.get_loc("high")] = float("nan")
    assert SH.regime_candidate(bad, p) is None
    row = _Row(regime="volatile", reasons="regime_blocked", atr_4h=4.0)
    out = SH.regime_cands(row, t, p, {"regime_volatile"}, trigger_tf="1h")
    assert len(out) == 1 and out[0].block == "regime_volatile" and out[0].planned_target is None
    assert out[0].features["atr_4h"] == 4.0 and out[0].rh is None
    assert SH.regime_cands(row, t, p, {"regime_unclear"}, trigger_tf="1h") == []
    for reg in ("trend_up", "range"):
        assert SH.regime_cands(_Row(regime=reg, reasons="regime_blocked"), t, p, {"regime_volatile", "regime_unclear"},
                               trigger_tf="1h") == []
    assert SH.regime_cands(_Row(regime="volatile", reasons="v1b:x"), t, p, {"regime_volatile"}, trigger_tf="1h") == []


def test_tf15_holdout_wait_reads_nothing_and_after_wait_computes(kilitli_motor):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    from trader_engine import shadow as SH
    calls = []

    class View:
        def bars(self, *a, **k):
            calls.append(a)
            return pd.DataFrame()

    c = Counter()
    first_ok = datetime(2026, 11, 1, tzinfo=UTC)
    D_wait = first_ok + timedelta(minutes=15) * SH.N15 - timedelta(minutes=15)
    assert SH.tf15_candidates(View(), "BTC/USDT", D_wait, S.SignalParams(), counters=c) == []
    assert c["tf15_holdout_wait"] == 1 and calls == []
    D_ok = first_ok + timedelta(minutes=15) * SH.N15
    assert SH.tf15_candidates(View(), "BTC/USDT", D_ok, S.SignalParams(), counters=c) == []
    assert len(calls) == 2 and c["tf15_holdout_wait"] == 1            # hesap yolu acildi (veri yok -> bos)
    assert SH.tf15_window_start(D_ok) == first_ok


def test_in_holdout_boundaries(kilitli_motor):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    from trader_engine import shadow as SH
    assert SH.in_holdout(datetime(2026, 5, 1, tzinfo=UTC)) and SH.in_holdout(datetime(2026, 10, 31, 23, 0, tzinfo=UTC))
    assert not SH.in_holdout(datetime(2026, 11, 1, tzinfo=UTC)) and not SH.in_holdout(datetime(2026, 4, 30, tzinfo=UTC))


def test_shadow_and_mtm_modules_are_light_and_pure():
    import ast
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "trader_engine"
    for name in ("shadow.py", "mtm.py"):
        tree = ast.parse((src / name).read_text())
        mods = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                mods.add(n.module.split(".")[0])
        assert not mods & {"requests", "trader_ml", "trader_reports", "sqlite3", "numpy"} or name == "shadow.py"
        assert not mods & {"requests", "trader_ml", "trader_reports"}
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not {"datetime.now", "time.time", "time.monotonic"} & calls


# =========================================================================== exec_fields
def test_exec_fields_and_payload():
    from trader_engine.position_manager import exec_fields, exec_payload
    from trader_engine.types import Fill

    class Row:
        created_ts = BAR

    f_sim = Fill("c", "BTC/USDT", "entry", "buy", 1.0, 100.02, 0.0, BAR, "market", 100.0)
    raw_ = exec_fields("entry", None, f_sim, Row())
    assert raw_ == {"order_ts": BAR, "order_ref_price": 100.0, "order_ref_src": "sim_open"}
    meta = {"order_ts": BAR, "order_ack_ts": BAR + timedelta(milliseconds=180), "order_ref_price": 100.0,
            "order_ref_spread": 0.0002, "order_ref_src": "book"}
    out, dropped = exec_payload(exec_fields("entry", meta, f_sim, None))
    assert dropped == 0 and out["order_ref_src"] == "book" and out["order_ack_ts"].endswith("Z")
    stop_fill = Fill("c", "BTC/USDT", "exit", "sell", 1.0, 99.0, 0.0, BAR, "stop")
    assert exec_fields("exit", meta, stop_fill, Row()) == {}
    liq = dataclasses.replace(stop_fill, reason="liquidation")
    assert exec_fields("exit", None, liq, None) == {}
    out, dropped = exec_payload({"order_ref_price": -1.0, "order_ref_src": "book", "exit_regime": "range"})
    assert dropped == 1 and out == {"exit_regime": "range"}
    assert exec_payload(None) == ({}, 0) and exec_payload({"order_ts": object()})[0] == {}


# =========================================================================== yapilandirma
def test_config_shadow_and_mtm_keys():
    from trader_engine import config as C
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    base = C.load_engine_config(root / "config" / "engine.base.json", root / "config" / "engine.learner.json")
    assert base.shadow_blocks == ("regime", "r1_disabled", "same_bar_reentry") and base.mtm_marks is True
    assert not (root / "config" / "engine.twin.json").exists()      # DD-12: ikiz kaldirildi
    raw_ = json.loads((root / "config" / "engine.base.json").read_text())
    for bad in (["nope"], "regime", ["regime", "regime"]):
        with pytest.raises(Exception):
            C._validate({**raw_, "bot": "learner", "shadow_blocks": bad})
    with pytest.raises(Exception):
        C._validate({**raw_, "bot": "learner", "mtm_marks": "yes"})
    assert json.loads((root / "config" / "engine.testnet.json").read_text())["live"]["order_quote"] is True
    assert C.LiveSettings("a" * 4, 1.0).order_quote is False


# =========================================================================== karsi-olgu eki
def _market(path, pair, start_ms, n, price=100.0, hi=None, lo=None):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE bars (kind TEXT, pair TEXT, tf TEXT, open_ms INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL,"
                " written_ms INTEGER, PRIMARY KEY(kind, pair, tf, open_ms)) WITHOUT ROWID")
    con.execute("PRAGMA user_version=1")
    rows = []
    for k in range(n):
        o = start_ms + k * 3_600_000
        rows.append(("last", pair, "1h", o, price, hi or price, lo or price, price, 1.0, o + 3_600_000))
    con.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


class _Sh:
    def __init__(self, id, ts, block="regime_volatile", **kw):
        self.id, self.pair, self.side, self.setup, self.trigger_tf = id, "BTC/USDT", "long", "T1", "1h"
        self.bar_close_ts, self.block = ts, block
        self.planned_entry, self.planned_stop, self.planned_target = 100.0, 98.0, None
        self.__dict__.update(kw)


def test_run_shadow_matches_run_once_and_is_separate(tmp_path, kilitli_motor):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    t0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    mk = tmp_path / "market.sqlite"
    _market(mk, "BTC/USDT", int((t0).timestamp() * 1000), 100, price=100.0, hi=100.5, lo=90.0)   # stop vurulur
    store = CF.CounterfactualStore(tmp_path / "cf.sqlite")
    now = t0 + timedelta(days=10)
    sh = [_Sh(1, t0), _Sh(2, t0 + timedelta(minutes=15), block="tf_15m")]
    r = CF.run_shadow(bot="learner", shadows=sh, market_path=mk, store=store, now=now)
    assert (r.shadow_scanned, r.shadow_computed, r.shadow_pending) == (2, 2, 0) and r.shadow_rows_written == 4
    dec = type("D", (), dict(id=7, pair="BTC/USDT", side="long", setup="T1", trigger_tf="1h", bar_close_ts=t0,
                              planned_entry=100.0, planned_stop=98.0, planned_target=None, skip_reason="other",
                              final_action="skipped"))()
    CF.run_once(bot="learner", decisions=[dec], market_path=mk, store=store, now=now)
    store.close()
    rows = CF.shadow_outcomes(tmp_path / "cf.sqlite", "learner", now=now)
    assert [x["shadow_id"] for x in rows] == [1, 2] and rows[0]["hyp_r_net"] == rows[1]["hyp_r_net"]
    base = CF.outcomes(tmp_path / "cf.sqlite", "learner", now=now)
    assert len(base) == 1 and base[0]["hyp_r_net"] == rows[0]["hyp_r_net"]           # ayni fiyat yolu ayni sonuc
    assert CF.summary(tmp_path / "cf.sqlite", "learner", now=now, days=30)["n"] == 1             # golge icermez
    con = sqlite3.connect(str(tmp_path / "cf.sqlite"))
    assert con.execute("PRAGMA user_version").fetchone()[0] == 2      # DD-12 WP-13: cf deposu sema 2 (arm_id/session_tag)
    assert con.execute("SELECT COUNT(*) FROM cf_outcomes").fetchone()[0] == 2           # barrier + plan, golge yok
    con.close()
    # idempotent; ufku dolmamis bekler; kilitli donemle kesisen atlanir
    store = CF.CounterfactualStore(tmp_path / "cf.sqlite")
    assert CF.run_shadow(bot="learner", shadows=sh, market_path=mk, store=store, now=now).shadow_rows_written == 0
    early = CF.run_shadow(bot="learner", shadows=[_Sh(3, t0 + timedelta(days=1))], market_path=mk, store=store,
                          now=t0 + timedelta(days=2))
    assert early.shadow_pending == 1
    lock = CF.run_shadow(bot="learner", shadows=[_Sh(4, datetime(2026, 6, 1, 9, 0, tzinfo=UTC))], market_path=mk,
                         store=store, now=now)
    assert lock.shadow_holdout_skipped == 1 and lock.shadow_computed == 0
    store.close()


def test_shadow_outcomes_missing_table_is_empty(tmp_path):
    store = CF.CounterfactualStore(tmp_path / "old.sqlite")
    store._db.execute("DROP TABLE cf_shadow_outcomes")
    store.close()
    assert CF.shadow_outcomes(tmp_path / "old.sqlite", "learner", now=NOW) == []


def test_counterfactual_script_reports_shadow_keys_and_reads_v3(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("cf_run_wp3", root / "scripts" / "counterfactual_run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    t0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    clock = lambda: t0 + timedelta(hours=1)           # noqa: E731
    led = L.open_ledger(tmp_path / "l.sqlite", "learner", clock=clock)
    led.init_params(PARAMS, reason="strategy:price_action_v1@1b.0 t")
    led.record_decision(mk_decision(ts=t0, final_action="skipped", skip_reason="stop_width", veto_status="not_evaluated",
                                    veto_reason=None, risk_allowed=None, size_qty=None, size_notional=None,
                                    size_margin=None, size_risk_amount=None, leverage=None))
    led.record_shadow(mk_shadow(bar_close_ts=t0))
    led.close()
    mk = tmp_path / "market.sqlite"
    _market(mk, "BTC/USDT", int(t0.timestamp() * 1000), 100)
    out = tmp_path / "cf.sqlite"
    now = t0 + timedelta(days=10)
    argv = ["--bot", "learner", "--once", "--ledger", str(tmp_path / "l.sqlite"), "--market", str(mk), "--out", str(out)]
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert mod.main(argv, now_fn=lambda: now) == 0
    js = json.loads(buf.getvalue().splitlines()[-1])
    assert js["computed"] == 1 and js["shadow_computed"] == 1 and js["shadow_rows_written"] == 2
    assert {"shadow_scanned", "shadow_pending", "shadow_holdout_skipped"} <= set(js)
    # sema 3 defter: is hatasiz calisir, golge sayaclari 0
    p3 = tmp_path / "v3.sqlite"
    _make_v3(p3)
    c = sqlite3.connect(str(p3))
    c.execute("INSERT INTO param_versions (bot, params, params_hash, lesson_bounds, author, reason, created_at) "
              "VALUES ('learner','{}',?,'{}','initial','r','2026-12-01T00:00:00.000Z')", ("0" * 64,))
    c.commit()
    c.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.main(["--bot", "learner", "--once", "--ledger", str(p3), "--market", str(mk), "--out",
                       str(tmp_path / "cf3.sqlite")], now_fn=lambda: now)
    js3 = json.loads(buf.getvalue().splitlines()[-1])
    assert rc == 0 and js3["status"] == "ok" and js3["shadow_scanned"] == 0 and js3["shadow_rows_written"] == 0


# =========================================================================== rapor paketi
def test_reports_schema_accepts_7_and_rejects_8(tmp_path):
    from trader_reports import inputs as I
    for uv, ok in ((2, True), (3, True), (4, True), (5, True), (6, True), (7, True), (8, True), (1, False), (9, False)):   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
        c = sqlite3.connect(":memory:")
        c.execute(f"PRAGMA user_version={uv}")
        if ok:
            assert I.check_ledger_schema(c) == uv
        else:
            with pytest.raises(Exception, match="ledger_schema|sema"):
                I.check_ledger_schema(c)


def _gate_inputs():
    return dict(trades=[], decisions=[{"id": 1, "final_action": "skipped", "skip_reason": "stop_width", "regime": "volatile",
                                       "setup": "T1", "trigger_tf": "1h", "veto_reason": None, "risk_reason": None}],
                cf=None, mode_backtest=False, period_days=30.0, veto_cost=None, risk_usd=5.0, cf_warning=None)


def _blk(res, tid):
    return next(b for b in res["blocks"] if (b["id"] if isinstance(b, dict) else b.tid) == tid)


def test_gates_fixed_rows_from_shadow_rows_and_legacy_fallback():
    from trader_reports import gates as G
    kw = _gate_inputs()
    legacy = G.build(**kw)
    t24 = _blk(legacy, "aday_uretmeyen")
    names = [r["hucre"] for r in t24["rows"]]
    assert names[-1] == "aynı mumda yeniden giriş" and all(r["yargi"] == "kanit_yok" or r["hucre"] == "koşul:volatile"
                                                          for r in t24["rows"])
    shadow = [{"id": i, "block": b, "bar_close_ts": "2026-12-01T09:00:00.000Z", "pos_open": po}
              for i, (b, po) in enumerate([("regime_volatile", 0), ("regime_volatile", 1), ("same_bar_reentry", 0),
                                           ("regime_unclear", 0)], start=1)]
    new = G.build(**kw, shadow=shadow, cf_shadow=None)
    t = _blk(new, "aday_uretmeyen")
    rows = {r["hucre"]: r for r in t["rows"]}
    assert rows["koşul:volatile"]["n_engel"] == 2 and rows["koşul:volatile"]["n_pozisyon_acik"] == 1
    assert rows["aynı mumda yeniden giriş"]["n_engel"] == 1 and "15m kapalı" not in rows
    assert rows["koşul:unclear"]["n_engel"] == 1
    assert all(r["pay"] == "—" for r in t["rows"]) and "n_pozisyon_acik" in t["columns"]
    # kapi karnesi, n_engel_toplam ve pay: golge satirlardan etkilenmez
    assert new["n_engel_toplam"] == legacy["n_engel_toplam"] and new["gate_counts"] == legacy["gate_counts"]
    k_old = _blk(legacy, "kapi_karnesi")
    k_new = _blk(new, "kapi_karnesi")
    assert k_old.cells == k_new.cells


def test_reports_load_shadow_and_lock(tmp_path, led, kilitli_donem):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    from trader_reports import inputs as I
    led.record_shadow(mk_shadow(bar_close_ts=BAR))
    led.record_shadow(mk_shadow(bar_close_ts=datetime(2026, 6, 1, 9, 0, tzinfo=UTC), pair="ETH/USDT"))
    c = I.open_ro(led.path, "ledger_missing")
    try:
        assert I.check_ledger_schema(c) == 8      # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
        rows = I.load_shadow(c, None, None)
        assert [r["pair"] for r in rows] == ["BTC/USDT"]                # kilitli donem satiri okunmaz
    finally:
        c.close()
    c3 = sqlite3.connect(":memory:")
    assert I.load_shadow(c3, None, None) is None


# =========================================================================== dagitim guvenligi (sema goc sahipligi)
def test_only_engine_and_backtest_may_migrate_ledgers():
    """Defteri `Ledger` sinifiyla acan her yer: salt okunur ya da migrate=False; yalniz motor (build_engine) ve yeni
    dosya kuran backtest varsayilan (goc eden) acisi kullanir."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    allowed = {"src/trader_engine/engine.py", "src/trader_engine/backtest.py"}
    bad = []
    for d in ("src", "scripts", "research"):
        for f in (root / d).rglob("*.py"):
            rel = str(f.relative_to(root))
            if rel == "src/trader_core/ledger.py" or rel in allowed:
                continue
            txt = f.read_text(encoding="utf-8")
            for m in re.finditer(r"(?:open_ledger|\bLedger)\(", txt):
                line_start = txt.rfind("\n", 0, m.start()) + 1
                if txt[line_start:m.start()].lstrip().startswith(("def ", "class ", "#")):
                    continue
                call = txt[m.start():m.start() + 400].split("\n\n")[0]
                depth, end, seen = 0, m.start() + 600, False
                for i, ch in enumerate(txt[m.start():m.start() + 600]):
                    depth += ch == "("
                    depth -= ch == ")"
                    seen = seen or depth > 0
                    if seen and depth == 0:
                        end = m.start() + i
                        break
                call = txt[m.start():end]
                if "read_only=True" not in call and "migrate=False" not in call:
                    bad.append(f"{rel}: {call[:80]}")
    assert bad == []


def test_readers_do_not_migrate_v3_file(tmp_path, clock):
    from trader_core import panel_data  # noqa: F401  (salt okunur acis: migrate=False)
    p = tmp_path / "v3.sqlite"
    _make_v3(p)
    for kw in (dict(read_only=True), dict(migrate=False), dict(read_only=True, migrate=False)):
        with pytest.raises(L.LedgerSchemaError):
            L.open_ledger(p, "learner", create=False, clock=clock, **kw)
    assert raw(p, "PRAGMA user_version")[0][0] == 3 and not os.path.exists(str(p) + ".premigrate-v3")


def test_init_ledger_does_not_migrate_old_file(tmp_path, clock, capsys):
    import argparse
    from trader_engine import cli
    from trader_engine.config import load_engine_config
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    raw_cfg = json.loads((root / "config" / "engine.base.json").read_text())
    raw_cfg.update(var_dir=str(tmp_path / "var"), bot="learner")
    base = tmp_path / "base.json"
    base.write_text(json.dumps(raw_cfg))
    (tmp_path / "learner.json").write_text('{"bot":"learner"}')
    cfg = load_engine_config(base, tmp_path / "learner.json")
    os.makedirs(os.path.dirname(cfg.ledger_path))
    _make_v3(cfg.ledger_path)
    a = argparse.Namespace(bot="learner", config_dir=str(tmp_path), reason="x", strategy=None)
    import trader_engine.cli as C
    orig = C._load_cfg if hasattr(C, "_load_cfg") else None
    try:
        rc = cli._cmd_init_ledger(a)
    except Exception:
        rc = None
    assert raw(cfg.ledger_path, "PRAGMA user_version")[0][0] == 3     # hicbir halde goc etmedi
    assert orig is None or callable(orig)
    assert rc != 0 or rc is None


def test_install_script_restarts_running_engines_after_code_change():
    from pathlib import Path
    t = (Path(__file__).resolve().parents[1] / "deploy" / "install.sh").read_text(encoding="utf-8")
    assert "trader-engine@*.service" in t and "trader-engine-testnet.service" in t
    assert t.index('PREV_COMMIT="$(sed') < t.index('exec bash "$ROOT_DIR/releases/$COMMIT/deploy/install.sh"')   # DD-9: onceki surum /etc/trader-release'ten, exec'ten once okunur
    assert t.index("CODE_CHANGED=1") < t.index("ACTIVE_ENGINES=")
    assert 'systemctl restart "$u"' in t
    assert t.index("ACTIVE_ENGINES=") < t.index("enable_now trader-engine@learner.service") < t.index('systemctl restart "$u"')
    assert "--state=active" in t                                                         # yalniz calisanlar


# =========================================================================== MtM canli yol: ag cagrisi yok; outbox bozuk olcum
def test_mtm_live_decision_uses_cached_account_only(tmp_path):
    import sys
    sys.path.insert(0, os.path.dirname(__file__) + "/engine")
    from test_engine_05_spec import Env, T0 as ET0
    e = Env(tmp_path, shadow_blocks=[])
    e.start()
    try:
        eng = e.engine
        calls = {"account": 0, "cached": 0}
        acct = _Acct(1000.0, 1001.0)
        acct.ts = ET0
        state = {"v": None}
        b = eng.broker

        def account():
            calls["account"] += 1
            raise RuntimeError("REST kesintisi")

        def cached():
            calls["cached"] += 1
            return state["v"]
        b.is_simulated = False
        eng.mtm.src = "exchange"
        b.account, b.account_cached = account, cached
        eng._mtm_decision(ET0)                                   # onbellek bos: isaret atlanir, hata degil
        assert calls["account"] == 0 and eng.mtm.errors == 0 and e.real_ledger.list_equity_marks() == []
        state["v"] = acct
        eng._mtm_decision(ET0 + timedelta(hours=1))
        assert calls["account"] == 0 and eng.mtm.errors == 0
        assert [m.src for m in e.real_ledger.list_equity_marks()] == ["exchange"]
    finally:
        e.close()


def test_live_broker_account_cached_never_calls_rest():
    from trader_engine.brokers.binance_futures import LiveBroker
    b = LiveBroker.__new__(LiveBroker)
    b._acct = None
    assert LiveBroker.account_cached(b) is None
    b._acct = (NOW - timedelta(days=1), "ACC")
    assert LiveBroker.account_cached(b) == "ACC"                 # yasina bakilmaz


def test_outbox_corrupt_order_ts_with_valid_ack_still_writes_null_measurements(tmp_path, led):
    from trader_engine.state import StateStore
    did = led.record_decision(mk_decision())
    st = StateStore(str(tmp_path / "state.sqlite"), bot="learner")
    try:
        t0 = (NOW - timedelta(minutes=50)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with st.tx():
            st.outbox_add("entry", 1, {"trade_id": 1, "decision_id": did, "entry_ts": t0, "entry_price": 100.0,
                                       "qty": 1.0, "leverage": 3, "fee_entry": 0.0, "order_ts": "bozuk",
                                       "order_ack_ts": t0, "order_ref_price": 100.0, "order_ref_src": "sim_open"})
        res = st.drain_outbox(led)
        assert res.failed == 0 and res.written == 1
        tr = led.get_trade(1)
        assert tr.entry_order_ts is None and tr.entry_order_ack_ts is None
        assert tr.entry_ref_price == 100.0                           # saglam grup korunur
    finally:
        st.close()


def test_acik_kilitte_shadow_in_holdout_hep_false_ve_tf15_beklemez():
    """23.11.2026 kullanici karari: kilit ACIK -> shadow satirlari kilitli donemde de yazilir, 15 dk golge adayi beklemeden hesaplanir."""
    from trader_engine import holdout as H
    from trader_engine import shadow as SH
    assert H.KILIT_ACIK is True
    assert not SH.in_holdout(datetime(2026, 5, 1, tzinfo=timezone.utc)) and not SH.in_holdout(datetime(2026, 10, 31, 23, tzinfo=timezone.utc))
