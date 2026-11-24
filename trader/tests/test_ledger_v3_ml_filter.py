"""Sema 3 (ML-0a, 19a; docs/defter-spec.md 3.3 ve 10.2): `ml_filter` atlama nedeni + `ml_score` sutunu, ekleyici goc 2 -> 3."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from trader_core import ledger as L
from trader_core.ledger import LedgerSchemaError, LedgerValidationError, open_ledger

from test_ledger_v2_spec import BASE, DEFAULT_PARAMS, clock, cols, enter, mk_decision, new_ledger, raw


def _build_v2(path, bot="learner"):
    """Gercek goc 0->1->2 betikleriyle sema 2 dosyasi kurar (sonra elle satir ekler)."""
    con = sqlite3.connect(str(path))
    for n in (0, 1):
        con.executescript("BEGIN IMMEDIATE;\n" + L.MIGRATIONS[n](bot, "2026-12-01T00:00:00.000Z")
                          + f"INSERT INTO schema_migrations (from_version,to_version,applied_at) "
                            f"VALUES ({n},{n + 1},'2026-12-01T00:00:00.000Z');\nPRAGMA user_version={n + 1};\nCOMMIT;")
    con.close()


def _populate_v2_via_v3_code(tmp_path):
    """v2 dosyasi + bir param surumu, bir giris karari, bir islem (FK zinciri) ve bir atlanan karar."""
    p = tmp_path / "v2.sqlite"
    _build_v2(p)
    ts = "2026-12-01T09:00:00.000Z"
    con = sqlite3.connect(str(p))
    import json
    canon = json.dumps(DEFAULT_PARAMS, sort_keys=True, separators=(",", ":"))
    con.execute("INSERT INTO param_versions (bot,params,params_hash,lesson_bounds,author,reason,created_at) "
                "VALUES ('learner',?,?,'{}','initial','init',?)", (canon, "0" * 64, ts))
    con.execute("INSERT INTO param_activations (bot,version_id,kind,actor,reason,activated_at) "
                "VALUES ('learner',1,'initial','system','init',?)", (ts,))
    feats = '{"atr_1h":20.0,"stop_dist_atr":2.0,"atr_4h":40.0,"pullback_ema":50,"ema_value":1.0,"body_ratio":0.5}'
    con.execute(
        "INSERT INTO decision_events (bot,bar_close_ts,trigger_tf,pair,side,setup,regime,rh_touches,rl_touches,features,"
        "planned_entry,planned_stop,param_version_id,activation_id,veto_status,risk_allowed,risk_reason,size_qty,"
        "size_notional,size_margin,size_risk_amount,leverage,final_action,recorded_at) VALUES "
        "('learner','2026-12-01T10:00:00.000Z','1h','ETH/USDT','long','T1','trend_up',0,0,?,2000,1960,1,1,'allowed',1,"
        "'ok',0.3,600,200,13.2,3,'entered',?)", (feats, ts))
    con.execute(
        "INSERT INTO decision_events (bot,bar_close_ts,trigger_tf,pair,side,setup,regime,rh_touches,rl_touches,features,"
        "planned_entry,planned_stop,param_version_id,activation_id,veto_status,final_action,skip_reason,recorded_at) "
        "VALUES ('learner','2026-12-01T11:00:00.000Z','1h','ETH/USDT','long','T1','trend_up',0,0,?,2000,1960,1,1,"
        "'not_evaluated','skipped','rr_below_min',?)", (feats, ts))
    con.execute(
        "INSERT INTO trade_entries (bot,trade_id,decision_id,param_version_id,activation_id,pair,side,setup,entry_ts,"
        "entry_price,planned_entry,planned_stop,qty,leverage,planned_risk,fee_entry,slippage_entry,recorded_at) VALUES "
        "('learner',1,1,1,1,'ETH/USDT','long','T1','2026-12-01T10:00:03.000Z',2000,2000,1960,0.3,3,13.2,0,0,?)", (ts,))
    con.commit()
    con.close()
    return p


def _table_rows(p, t):
    return raw(p, f"SELECT * FROM {t} ORDER BY id")


def test_v2_to_v3_migration_preserves_rows_and_fk(tmp_path):
    p = _populate_v2_via_v3_code(tmp_path)
    assert raw(p, "PRAGMA user_version")[0][0] == 2
    assert "ml_score" not in cols(p, "decision_events")
    before = {t: _table_rows(p, t) for t in ("decision_events", "trade_entries", "param_versions")}
    led = open_ledger(p, "learner", clock=clock)                # migrate=True (varsayilan)
    led.close()
    assert raw(p, "PRAGMA user_version")[0][0] == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert (2, 3) in raw(p, "SELECT from_version, to_version FROM schema_migrations")
    assert "ml_score" in cols(p, "decision_events")
    after = raw(p, "SELECT " + ", ".join(c for c in cols(p, "decision_events")
                                  if c not in ("ml_score", "arm_id", "session_tag", "lesson_ids", "source"))
                + " FROM decision_events ORDER BY id")
    assert after == before["decision_events"]                    # satirlar ayni id ve icerikle
    assert [r[0] for r in raw(p, "SELECT ml_score FROM decision_events")] == [None, None]
    # sema 4 (WP-3) trade_entries'e 5 ekleyici NULL sutun getirir; mevcut sutunlar degismez
    # sema 5 (DD-12 WP-02) sona arm_id ve session_tag ekler (arm_id dolu, session_tag NULL)
    assert [r[:-7] for r in _table_rows(p, "trade_entries")] == before["trade_entries"]
    assert all(r[-7:-2] == (None,) * 5 for r in _table_rows(p, "trade_entries"))
    assert raw(p, "PRAGMA foreign_key_check") == []
    assert raw(p, "SELECT COUNT(*) FROM v_decisions")[0][0] == 2
    assert raw(p, "SELECT COUNT(*) FROM v_trades")[0][0] == 1
    assert raw(p, "SELECT name FROM sqlite_master WHERE name IN ('ux_decision_key','ix_decision_supersedes')")
    assert raw(p, "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'decision_events%'") \
        == [("decision_events",)]
    # premigrate yedegi
    assert (tmp_path / "v2.sqlite.premigrate-v2").exists()


def test_v3_append_only_triggers_survive_migration(tmp_path):
    p = _populate_v2_via_v3_code(tmp_path)
    open_ledger(p, "learner", clock=clock).close()
    con = sqlite3.connect(str(p))
    for sql in ("UPDATE decision_events SET pair='X' WHERE id=1", "DELETE FROM decision_events WHERE id=1"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute(sql)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert {"trg_decision_events_no_update", "trg_decision_events_no_delete",
            "trg_trade_exits_excursion_check"} <= names
    con.close()


def test_v2_read_only_never_migrates(tmp_path):
    p = _populate_v2_via_v3_code(tmp_path)
    with pytest.raises(LedgerSchemaError):
        open_ledger(p, "learner", create=False, read_only=True, migrate=False, clock=clock)
    assert raw(p, "PRAGMA user_version")[0][0] == 2


def test_ml_filter_skip_reason_and_score_roundtrip(tmp_path):
    led, path = new_ledger(tmp_path)
    ev = mk_decision(setup="T1", bar=BASE + timedelta(hours=3), veto_status="not_evaluated", risk_allowed=None,
                     risk_reason=None, size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None,
                     leverage=None, final_action="skipped", skip_reason="ml_filter", ml_score=0.4123)
    did = led.record_decision(ev)
    d = led.get_decision(did)
    assert d.skip_reason == "ml_filter" and d.ml_score == pytest.approx(0.4123) and d.final_action == "skipped"
    assert led.record_decision(ev) == did                         # idempotent
    led.close()
    assert raw(path, "SELECT skip_reason, ml_score FROM v_decisions") == [("ml_filter", 0.4123)]


def test_ml_filter_only_valid_as_not_evaluated_and_score_range(tmp_path):
    led, path = new_ledger(tmp_path)
    base = dict(setup="T1", veto_status="not_evaluated", risk_allowed=None, risk_reason=None, size_qty=None,
                size_notional=None, size_margin=None, size_risk_amount=None, leverage=None, final_action="skipped")
    with pytest.raises(LedgerValidationError):
        led.record_decision(mk_decision(bar=BASE + timedelta(hours=4), skip_reason="ml_filter", ml_score=1.5, **base))
    with pytest.raises(LedgerValidationError):                    # entered + ml_filter olamaz
        led.record_decision(mk_decision(bar=BASE + timedelta(hours=5), skip_reason="ml_filter"))
    # entered karar ml_score tasiyabilir (golge modu)
    did = enter(led, 1, setup="T1", bar=BASE + timedelta(hours=6), ml_score=0.61)
    assert led.get_decision(did).ml_score == pytest.approx(0.61)
    led.close()
    con = sqlite3.connect(str(path))
    with pytest.raises(sqlite3.IntegrityError):                   # ham SQL'de CHECK da tutar
        con.execute("INSERT INTO decision_events (bot,bar_close_ts,trigger_tf,pair,side,setup,regime,rh_touches,"
                    "rl_touches,features,planned_entry,planned_stop,param_version_id,veto_status,final_action,"
                    "skip_reason,ml_score,recorded_at) VALUES ('learner','2026-12-02T01:00:00.000Z','1h','A/B','long','T1',"
                    "'trend_up',0,0,'{}',1,0.5,1,'not_evaluated','skipped','ml_filter',2.0,'x')")
    con.close()


def test_ml_score_not_part_of_idempotency_compare(tmp_path):
    led, _ = new_ledger(tmp_path)
    a = mk_decision(setup="T1", bar=BASE + timedelta(hours=7), ml_score=0.5)
    did = led.record_decision(a)
    from dataclasses import replace
    assert led.record_decision(replace(a, ml_score=None)) == did   # tekrar oynatma ml_score farki catisma degil
    led.close()
