"""DD-12 WP-02 gerceklemenin duman testleri (v4 -> v5 goc, yeniden deneme, yeni nedenler)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.engine.test_dd12_wp02_spec import V4_DATA_TABLES, build_v4, dump, raw  # noqa: F401
from trader_core import ledger as L

NOW = datetime(2026, 12, 2, tzinfo=timezone.utc)


def clock():
    return NOW


def test_migrate_counts_fk_and_arm_id(tmp_path):
    p = build_v4(tmp_path / "l.sqlite")
    before = {t: len(dump(p, t)) for t in V4_DATA_TABLES}
    L.open_ledger(p, "learner", clock=clock).close()
    assert raw(p, "PRAGMA foreign_key_check") == []
    assert raw(p, "PRAGMA integrity_check")[0][0] == "ok"
    assert raw(p, "PRAGMA user_version")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    for t, n in before.items():
        assert len(dump(p, t)) == n
    assert all(a == f"{s}@{tf}" for a, s, tf in raw(p, "SELECT arm_id, setup, trigger_tf FROM decision_events"))
    assert raw(p, "SELECT arm_id FROM trade_entries") == [("T1@1h",)]


def test_retry_after_interrupted_migration_makes_new_backup(tmp_path, monkeypatch):
    p = build_v4(tmp_path / "l.sqlite")
    orig = L.MIGRATIONS[4]
    broken = list(L.MIGRATIONS)
    broken[4] = lambda bot, now: orig(bot, now) + "\nSELECT * FROM no_such_table;\n"
    monkeypatch.setattr(L, "MIGRATIONS", broken)
    with pytest.raises(L.LedgerError):
        L.open_ledger(p, "learner", clock=clock)
    with pytest.raises(L.LedgerError):
        L.open_ledger(p, "learner", clock=clock)       # ikinci basarisiz deneme de yedek hatasi vermez
    monkeypatch.undo()
    first = Path(f"{p}.premigrate-v4")
    assert first.exists() and raw(p, "PRAGMA user_version")[0][0] == 4
    first_bytes = first.read_bytes()
    L.open_ledger(p, "learner", clock=clock).close()
    assert raw(p, "PRAGMA user_version")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert first.read_bytes() == first_bytes                       # ezilmedi
    for suf in (".1", ".2"):
        b = Path(f"{p}.premigrate-v4{suf}")
        assert b.exists()
        assert raw(b, "PRAGMA user_version")[0][0] == 4


def _ev(**kw):
    base = dict(bar_close_ts=datetime(2026, 12, 1, 10, tzinfo=timezone.utc), trigger_tf="1d", pair="ETH/USDT",
                side="long", setup="TF1", regime="trend_up", atr_ratio=1.0, rh=None, rl=None, rh_touches=0,
                rl_touches=0, features={"stop_dist_atr": 2.0, "atr_1h": 1.0, "atr_4h": 2.0},
                planned_entry=100.0, planned_stop=95.0, planned_target=None, param_version_id=1,
                veto_status="not_evaluated", veto_reason=None, risk_allowed=None, risk_reason=None,
                size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
                final_action="skipped", skip_reason="arm_conflict", session_tag="weekend", source="m1")
    base.update(kw)
    return L.DecisionEvent(**base)


def test_new_skip_requires_not_evaluated_and_roundtrip(tmp_path):
    lg = L.open_ledger(tmp_path / "n.sqlite", "learner", clock=clock)
    lg.init_params({"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
                    "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5,
                    "trigger_tf": "1h"}, reason="r")
    did = lg.record_decision(_ev(lesson_ids=[3, 4]))
    r = lg.get_decision(did)
    assert (r.arm_id, r.session_tag, r.lesson_ids, r.source) == ("TF1@1d", "weekend", (3, 4), "m1")
    with pytest.raises(L.LedgerValidationError):
        lg.record_decision(_ev(veto_status="allowed", pair="BTC/USDT"))
    with pytest.raises(L.LedgerValidationError):
        lg.record_decision(_ev(setup="X", pair="SOL/USDT"))
    lg.close()
