"""DD-12 WP-02 (defter semasi v5) bagimsiz sartname testleri: docs/motor/dd12-capraz-varlik-spec.md (v4), §9 WP-02 satiri, D-T15.

Bagimsiz test ajani: yalniz sartnameden ve onceki (v4) defter API'sinden yazildi. v4 dosyasi, ledger.py'nin DEGISMEYEN
goc betikleriyle (`L.MIGRATIONS[0..3]`, mevcut test deseni: tests/test_ledger_v3_ml_filter.py) kurulur; satirlar ham SQL ile eklenir.
v4->v5 gocu `open_ledger(..., migrate=True)` ile tetiklenir. Gerceklemenin kodu okunmadi.

`# SPEC-AMBIGUOUS:` ile isaretli yerler sartnamenin adlandirmadigi noktalardaki tahminlerdir.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_core import ledger as L
from trader_core.ledger import LedgerError, LedgerSchemaError, open_ledger

UTC = timezone.utc
TS = "2026-12-01T09:00:00.000Z"
NOW = datetime(2026, 12, 2, 0, 0, tzinfo=UTC)
V4_DATA_TABLES = ("param_versions", "param_activations", "lesson_proposals", "proposal_status_events",
                  "decision_events", "trade_entries", "trade_exits", "shadow_decisions", "equity_marks")
NEW_SKIP = ("arm_conflict", "arm_disabled", "session_closed", "flat_bar", "cluster_cap", "max_positions",
            "ml_no_model", "llm_invalid", "etiket_rejim", "etiket_duygu", "etiket_kalabalik")
OLD_SKIP = ("stop_width", "rr_below_min", "veto_blocked", "veto_missing", "veto_stale", "risk_denied",
            "entry_gate_closed", "order_failed", "other", "ml_filter")


def clock():
    return NOW


# ------------------------------------------------------------------------------------------ yardimcilar
def raw(p, sql, args=()):
    con = sqlite3.connect(str(p))
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def dump(p, table):
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY id")]
    finally:
        con.close()


def cols(p, table):
    return [r[1] for r in raw(p, f"PRAGMA table_info({table})")]


def insert(con, table, **kw):
    names = ",".join(kw)
    con.execute(f"INSERT INTO {table} ({names}) VALUES ({','.join('?' * len(kw))})", tuple(kw.values()))


FEATS = '{"atr_1h":20.0,"stop_dist_atr":2.0}'
_PARAMS = json.dumps({"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
                      "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5,
                      "trigger_tf": "1h"}, sort_keys=True, separators=(",", ":"))


def seed_params(con, bot="learner"):
    insert(con, "param_versions", bot=bot, params=_PARAMS, params_hash="0" * 64, lesson_bounds="{}",
           author="initial", reason="init", created_at=TS)
    insert(con, "param_activations", bot=bot, version_id=1, kind="initial", actor="system", reason="init",
           activated_at=TS)


def dec_kwargs(*, bar="2026-12-03T10:00:00.000Z", pair="ETH/USDT", setup="T1", tf="1h", skip="other",
               veto="not_evaluated", bot="learner", **extra):
    kw = dict(bot=bot, bar_close_ts=bar, trigger_tf=tf, pair=pair, side="long", setup=setup, regime="trend_up",
              rh_touches=0, rl_touches=0, features=FEATS, planned_entry=2000, planned_stop=1960,
              param_version_id=1, activation_id=1, veto_status=veto, final_action="skipped", skip_reason=skip,
              recorded_at=TS)
    kw.update(extra)
    return kw


def build_v4(path, bot="learner"):
    """Gercek goc 0->3 betikleriyle v4 dosyasi + her tabloda satir (FK zinciri dahil)."""
    con = sqlite3.connect(str(path))
    for n in range(4):
        pre = "PRAGMA foreign_keys=OFF;\n" if n in L._FK_OFF_MIGRATIONS else ""
        con.executescript(pre + "BEGIN IMMEDIATE;\n" + L.MIGRATIONS[n](bot, TS)
                          + f"INSERT INTO schema_migrations (from_version,to_version,applied_at) "
                            f"VALUES ({n},{n + 1},'{TS}');\nPRAGMA user_version={n + 1};\nCOMMIT;")
    assert con.execute("PRAGMA user_version").fetchone()[0] == 4
    seed_params(con, bot)
    entered = dict(veto_status="allowed", risk_allowed=1, risk_reason="ok", size_qty=0.3, size_notional=600,
                   size_margin=200, size_risk_amount=13.2, leverage=3, final_action="entered", skip_reason=None)
    insert(con, "decision_events", **dec_kwargs(bar="2026-12-01T10:00:00.000Z", **entered))               # 1 T1@1h
    insert(con, "decision_events", **dec_kwargs(bar="2026-12-01T10:15:00.000Z", setup="R1", tf="15m",
                                                skip="rr_below_min"))                                       # 2 R1@15m
    insert(con, "decision_events", **dec_kwargs(bar="2026-12-01T10:30:00.000Z", tf="15m", skip="ml_filter",
                                                ml_score=0.4))                                              # 3 T1@15m
    insert(con, "decision_events", **dec_kwargs(bar="2026-12-01T11:00:00.000Z", setup="R1", regime="range",
                                                rh=2100.0, rl=1900.0, veto="blocked", skip="veto_blocked"))  # 4 R1@1h
    insert(con, "decision_events", **dec_kwargs(bar="2026-12-01T12:00:00.000Z", bot="twin"))                # 5 eski ikiz satiri
    insert(con, "trade_entries", bot=bot, trade_id=1, decision_id=1, param_version_id=1, activation_id=1,
           pair="ETH/USDT", side="long", setup="T1", entry_ts="2026-12-01T10:00:03.000Z", entry_price=2000,
           planned_entry=2000, planned_stop=1960, qty=0.3, leverage=3, planned_risk=13.2, fee_entry=0.1,
           slippage_entry=0, recorded_at=TS)
    insert(con, "trade_exits", bot=bot, trade_id=1, exit_ts="2026-12-01T14:00:00.000Z", exit_price=2040,
           exit_reason="target", fee_exit=0.1, funding_paid=0, gross_pnl=12, realized_pnl=11.8, r_multiple=0.9,
           recorded_at=TS)
    insert(con, "shadow_decisions", bot=bot, block="tf_15m", bar_close_ts="2026-12-01T10:15:00.000Z",
           trigger_tf="15m", pair="ETH/USDT", side="long", setup="T1", regime="trend_up", features=FEATS,
           planned_entry=2000, planned_stop=1960, param_version_id=1, strategy="s", reasons="[]", pos_open=0,
           recorded_at=TS)
    insert(con, "equity_marks", bot=bot, ts="2026-12-01T10:00:00.000Z", wallet=1000, equity=1001,
           equity_low=999, n_open=1, src="sim", recorded_at=TS)
    insert(con, "lesson_proposals", bot=bot, base_version_id=1, proposal="{}", claimed_evidence="{}", source="t",
           created_at=TS)
    insert(con, "proposal_status_events", proposal_id=1, status="proposed", code="c", reason="r", actor="lesson",
           recorded_at=TS)
    con.commit()
    con.close()
    return Path(path)


@pytest.fixture
def v4(tmp_path):
    return build_v4(tmp_path / "ledger.sqlite")


@pytest.fixture
def migrated(v4):
    before = {t: dump(v4, t) for t in V4_DATA_TABLES}
    open_ledger(v4, "learner", clock=clock).close()
    return v4, before


@pytest.fixture
def fresh(tmp_path):
    p = tmp_path / "fresh.sqlite"
    open_ledger(p, "learner", clock=clock).close()
    con = sqlite3.connect(str(p))
    seed_params(con)
    con.commit()
    con.close()
    return p


@pytest.fixture(params=["migrated", "fresh"])
def v5(request):
    """Ayni CHECK denetimleri hem goc edilmis hem sifirdan kurulmus v5 dosyasinda gecmeli."""
    if request.param == "migrated":
        return request.getfixturevalue("migrated")[0]
    return request.getfixturevalue("fresh")


_seq = iter(range(1, 10_000))


def try_decision(p, **kw):
    """Ham SQL ile karar satiri eklemeyi dener; kabul -> True, CHECK/NOT NULL ihlali -> False."""
    n = next(_seq)
    kw.setdefault("bar", f"2027-01-{1 + n // 96 % 28:02d}T{n // 4 % 24:02d}:{n % 4 * 15:02d}:00.000Z")
    kw.setdefault("pair", f"P{n}/USDT")
    extra = kw.pop("extra", {})
    con = sqlite3.connect(str(p))
    try:
        insert(con, "decision_events", **dec_kwargs(**kw, **extra))
        con.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()


def arm(setup, tf):
    return {"arm_id": f"{setup}@{tf}"}


# ------------------------------------------------------------------------------------------ surum
def test_schema_version_is_6():
    assert L.SCHEMA_VERSION == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert len(L.MIGRATIONS) == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert 4 in L._FK_OFF_MIGRATIONS                 # sartname §9 WP-02: _FK_OFF_MIGRATIONS'a 4


def test_fresh_ledger_is_v6(fresh):
    assert raw(fresh, "PRAGMA user_version")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert raw(fresh, "SELECT MAX(to_version) FROM schema_migrations")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert raw(fresh, "PRAGMA foreign_key_check") == []


# ------------------------------------------------------------------------------------------ goc 4 -> 5 (D-T15)
def test_migration_preserves_every_row_and_ids(migrated):
    p, before = migrated
    assert raw(p, "PRAGMA user_version")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert (4, 5) in raw(p, "SELECT from_version, to_version FROM schema_migrations")
    for t in V4_DATA_TABLES:
        after = dump(p, t)
        assert len(after) == len(before[t]), t
        assert len(before[t]) >= 1, t
        for b, a in zip(before[t], after):
            for k, v in b.items():                      # eski sutunlar ayni id ve icerikle
                assert a[k] == v, (t, k)


def test_migration_foreign_key_check_empty_and_integrity(migrated):
    p, _ = migrated
    assert raw(p, "PRAGMA foreign_key_check") == []
    assert raw(p, "PRAGMA integrity_check") == [("ok",)]
    con = sqlite3.connect(str(p))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        con.close()


def test_migration_other_tables_not_dropped(migrated):
    p, _ = migrated
    names = {r[0] for r in raw(p, "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    for t in V4_DATA_TABLES + ("meta", "schema_migrations", "health_probes", "v_decisions", "v_trades",
                               "v_closed_trades", "v_proposals", "v_shadow_decisions"):
        assert t in names, t
    assert raw(p, "SELECT COUNT(*) FROM v_decisions")[0][0] == 5
    assert raw(p, "SELECT COUNT(*) FROM v_trades")[0][0] == 1
    assert raw(p, "SELECT COUNT(*) FROM v_closed_trades")[0][0] == 1


def test_migration_keeps_unique_indexes_and_triggers(migrated):
    p, _ = migrated
    idx = {r[0] for r in raw(p, "SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"ux_decision_key", "ux_entry_trade", "ux_exit_trade"} <= idx
    con = sqlite3.connect(str(p))
    try:
        for sql in ("UPDATE decision_events SET pair='X' WHERE id=1", "DELETE FROM trade_entries WHERE id=1",
                    "UPDATE trade_exits SET exit_price=1 WHERE id=1"):
            with pytest.raises(sqlite3.DatabaseError):
                con.execute(sql)
    finally:
        con.close()


def test_migration_old_rows_arm_id_is_setup_at_trigger_tf(migrated):
    p, before = migrated
    rows = raw(p, "SELECT id, setup, trigger_tf, arm_id FROM decision_events ORDER BY id")
    assert len(rows) == 5
    for _id, setup, tf, arm_id in rows:
        assert arm_id == f"{setup}@{tf}"
    assert {r[3] for r in rows} == {"T1@1h", "R1@15m", "T1@15m", "R1@1h"}


def test_migration_trade_entries_arm_id_from_decision(migrated):
    p, _ = migrated
    assert "arm_id" in cols(p, "trade_entries")
    rows = raw(p, "SELECT e.arm_id, d.setup || '@' || d.trigger_tf FROM trade_entries e "
                  "JOIN decision_events d ON d.id = e.decision_id")
    assert rows == [("T1@1h", "T1@1h")]


def test_migration_new_columns_nullable_defaults_on_old_rows(migrated):
    p, _ = migrated
    for c in ("session_tag", "lesson_ids", "source"):
        assert c in cols(p, "decision_events"), c
    assert "session_tag" in cols(p, "trade_entries")
    assert all(r[0] is None for r in raw(p, "SELECT session_tag FROM decision_events"))      # bos-kabul
    assert all(r[0] is None for r in raw(p, "SELECT session_tag FROM trade_entries"))
    # SPEC-AMBIGUOUS: eski satirda lesson_ids/source varsayilani (NULL, '[]', 'arm') sartnamede yok.
    for (v,) in raw(p, "SELECT lesson_ids FROM decision_events"):
        assert v is None or isinstance(json.loads(v), list)
    assert {r[0] for r in raw(p, "SELECT source FROM decision_events")} <= {None, "arm"}


def test_migration_creates_premigrate_backup_with_v4_content(v4):
    before = {t: dump(v4, t) for t in V4_DATA_TABLES}
    bak = Path(f"{v4}.premigrate-v4")
    assert not bak.exists()
    open_ledger(v4, "learner", clock=clock).close()
    assert bak.exists()
    assert raw(bak, "PRAGMA user_version")[0][0] == 4                  # gocten ONCE alinmis
    for t in V4_DATA_TABLES:
        assert dump(bak, t) == before[t], t
    assert "arm_id" not in cols(bak, "decision_events")


def test_migration_migrated_ledger_old_read_api_works(migrated):
    p, _ = migrated
    led = open_ledger(p, "learner", clock=clock)
    try:
        assert len(led.list_decisions()) >= 1
        closed = led.list_closed_trades()
        assert len(closed) == 1 and closed[0].trade_id == 1
        assert led.get_trade(1) is not None
        assert led.get_active_params() is not None
    finally:
        led.close()


def test_migration_idempotent_reopen(migrated):
    p, before = migrated
    snap = {t: dump(p, t) for t in V4_DATA_TABLES}
    mig_before = raw(p, "SELECT from_version, to_version FROM schema_migrations ORDER BY id")
    for _ in range(2):
        open_ledger(p, "learner", clock=clock).close()
        open_ledger(p, "learner", clock=clock, migrate=False).close()   # v5 dosyada migrate=False sorunsuz
    assert raw(p, "SELECT from_version, to_version FROM schema_migrations ORDER BY id") == mig_before
    assert [m for m in mig_before if m == (4, 5)] == [(4, 5)]
    assert raw(p, "PRAGMA user_version")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    for t in V4_DATA_TABLES:
        assert dump(p, t) == snap[t]


def test_interrupted_migration_leaves_v4(v4, monkeypatch):
    before = {t: dump(v4, t) for t in V4_DATA_TABLES}
    orig = L.MIGRATIONS[4]
    broken = list(L.MIGRATIONS)
    broken[4] = lambda bot, now: orig(bot, now) + "\nSELECT * FROM no_such_table_xyz;\n"
    monkeypatch.setattr(L, "MIGRATIONS", broken)
    with pytest.raises(LedgerError):
        open_ledger(v4, "learner", clock=clock)
    assert raw(v4, "PRAGMA user_version")[0][0] == 4
    assert (4, 5) not in raw(v4, "SELECT from_version, to_version FROM schema_migrations")
    assert "arm_id" not in cols(v4, "decision_events")
    assert raw(v4, "PRAGMA foreign_key_check") == []
    for t in V4_DATA_TABLES:
        assert dump(v4, t) == before[t], t
    monkeypatch.undo()                         # sonra yeniden denenince tamamlanir
    open_ledger(v4, "learner", clock=clock).close()
    assert raw(v4, "PRAGMA user_version")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    for t in V4_DATA_TABLES:
        assert len(dump(v4, t)) == len(before[t])


def test_migrate_false_on_v4_raises_eski_sema_error(v4):
    with pytest.raises(LedgerSchemaError, match="eski"):
        open_ledger(v4, "learner", clock=clock, migrate=False)
    assert raw(v4, "PRAGMA user_version")[0][0] == 4
    assert not Path(f"{v4}.premigrate-v4").exists()                    # migrate=False yedek de almaz


def test_read_only_on_v4_raises_and_does_not_migrate(v4):
    with pytest.raises(LedgerSchemaError):
        open_ledger(v4, "learner", clock=clock, read_only=True)
    assert raw(v4, "PRAGMA user_version")[0][0] == 4


def test_read_only_open_on_v5_works(migrated):
    p, _ = migrated
    led = open_ledger(p, "learner", clock=clock, read_only=True)
    try:
        assert led.read_only
        assert len(led.list_decisions()) >= 1
        assert len(led.list_closed_trades()) == 1
        with pytest.raises(LedgerError):                               # salt okunur: yazma reddedilir
            led._require_writable()
    finally:
        led.close()
    assert raw(p, "PRAGMA user_version")[0][0] == 8   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)


def test_read_only_open_on_fresh_v5_works(fresh):
    led = open_ledger(fresh, "learner", clock=clock, read_only=True)
    led.close()


# ------------------------------------------------------------------------------------------ CHECK: trigger_tf
@pytest.mark.parametrize("tf", ["15m", "1h", "4h", "1d"])
def test_trigger_tf_accepts_new_set(v5, tf):
    assert try_decision(v5, tf=tf, extra=arm("T1", tf))


@pytest.mark.parametrize("tf", ["5m", "1m", "2h", "1w", "1H", "15M", "", "1d "])
def test_trigger_tf_rejects_others(v5, tf):
    assert not try_decision(v5, tf=tf, extra=arm("T1", tf))


# ------------------------------------------------------------------------------------------ CHECK: setup uzunlugu
@pytest.mark.parametrize("setup", ["T1", "R1", "TF1", "B1", "F1", "S1", "M1", "L1", "AB", "ABCDEFGH", "MF1-TERSCEKIC", "ABCDEFGH-ABCDEFGHIJ"])
def test_setup_length_2_to_8_accepted(v5, setup):
    assert try_decision(v5, setup=setup, extra=arm(setup, "1h"))


@pytest.mark.parametrize("setup", ["", "T", "ABCDEFGHIJKLMNOPQRST", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"])   # 24.11 kullanici karari: formasyon kutuphanesi (sinir 19)
def test_setup_length_outside_2_to_8_rejected(v5, setup):
    assert not try_decision(v5, setup=setup, extra=arm(setup, "1h"))


def test_setup_not_limited_to_t1_r1_on_entries(v5):
    con = sqlite3.connect(str(v5))
    try:
        insert(con, "trade_entries", bot="learner", trade_id=900, decision_id=1, param_version_id=1, activation_id=1,
               pair="BTC/USDT", side="long", setup="TF1", entry_ts="2027-01-01T00:00:03.000Z", entry_price=1,
               planned_entry=1, planned_stop=0.9, qty=1, leverage=1, planned_risk=0.1, fee_entry=0,
               slippage_entry=0, recorded_at=TS, arm_id="TF1@4h", session_tag="open")
        con.commit()
    except sqlite3.IntegrityError:
        pytest.fail("trade_entries yeni kurulum kodunu reddetti")
    finally:
        con.close()


# ------------------------------------------------------------------------------------------ CHECK: skip_reason
@pytest.mark.parametrize("reason", NEW_SKIP)
def test_new_skip_reasons_accepted(v5, reason):
    # SPEC-AMBIGUOUS: veto_status kapisi (veto kalkti) belirsiz; 'not_evaluated' ya da 'allowed' ile kabul yeterli.
    ok = any(try_decision(v5, skip=reason, veto=v, extra=arm("T1", "1h")) for v in ("not_evaluated", "allowed"))
    assert ok, reason


@pytest.mark.parametrize("reason", OLD_SKIP)
def test_old_skip_reasons_still_accepted(v5, reason):
    veto = {"veto_blocked": "blocked", "veto_missing": "missing", "veto_stale": "stale"}.get(reason)
    if veto is None:
        veto = "allowed" if reason in ("risk_denied", "order_failed") else "not_evaluated"
    extra = dict(arm("T1", "1h"))
    if reason == "risk_denied":
        extra.update(risk_allowed=0)
    if reason == "order_failed":
        extra.update(risk_allowed=1, risk_reason="ok")
    assert try_decision(v5, skip=reason, veto=veto, extra=extra), reason


@pytest.mark.parametrize("reason", ["bogus", "arm_conflicts", "", "Flat_Bar"])
def test_invalid_skip_reason_rejected(v5, reason):
    for v in ("not_evaluated", "allowed"):
        assert not try_decision(v5, skip=reason, veto=v, extra=arm("T1", "1h"))


def test_skipped_still_requires_skip_reason(v5):
    assert not try_decision(v5, skip=None, extra=arm("T1", "1h"))


# ------------------------------------------------------------------------------------------ yeni sutunlar / tablolar
def test_new_columns_exist_and_accept_values(v5):
    for c in ("arm_id", "session_tag", "lesson_ids", "source"):
        assert c in cols(v5, "decision_events"), c
    for c in ("arm_id", "session_tag"):
        assert c in cols(v5, "trade_entries"), c
    ok = try_decision(v5, skip="flat_bar", extra=dict(arm_id="T1@1h", session_tag="weekend",
                                                      lesson_ids="[3,7]", source="arm"))
    assert ok
    row = raw(v5, "SELECT arm_id, session_tag, lesson_ids, source FROM decision_events "
                  "WHERE skip_reason='flat_bar' ORDER BY id DESC LIMIT 1")[0]
    assert row == ("T1@1h", "weekend", "[3,7]", "arm")


@pytest.mark.parametrize("source", ["arm", "m1", "l1"])
def test_source_accepts_arm_m1_l1(v5, source):
    assert try_decision(v5, extra=dict(arm_id="T1@1h", source=source))


@pytest.mark.parametrize("source", ["x", "ARM", "llm", "m2"])
def test_source_rejects_others(v5, source):
    assert not try_decision(v5, extra=dict(arm_id="T1@1h", source=source))


def test_session_tag_may_be_null(v5):
    assert try_decision(v5, extra=dict(arm_id="T1@1h"))                # session_tag verilmez -> NULL kabul
    assert try_decision(v5, extra=dict(arm_id="T1@1h", session_tag=None))


def test_trade_entries_new_columns_roundtrip(v5):
    con = sqlite3.connect(str(v5))
    try:
        insert(con, "trade_entries", bot="learner", trade_id=901, decision_id=1, param_version_id=1, activation_id=1,
               pair="XAU/USDT", side="short", setup="F1", entry_ts="2027-01-01T00:00:03.000Z", entry_price=2,
               planned_entry=2, planned_stop=2.1, qty=1, leverage=1, planned_risk=0.1, fee_entry=0,
               slippage_entry=0, recorded_at=TS, arm_id="F1@1d", session_tag="closed")
        con.commit()
        assert con.execute("SELECT arm_id, session_tag FROM trade_entries WHERE trade_id=901").fetchall() \
            == [("F1@1d", "closed")]
    finally:
        con.close()


def test_trade_notes_table_columns(v5):
    names = {r[0] for r in raw(v5, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "trade_notes" in names
    assert {"trade_id", "note_date", "tags", "text", "model", "cost_usd"} <= set(cols(v5, "trade_notes"))


def test_trade_notes_accepts_row(v5):
    con = sqlite3.connect(str(v5))
    try:
        # SPEC-AMBIGUOUS: note_date/tags bicimi (ISO tarih, JSON liste) ve ek sutunlar (recorded_at?) belirsiz.
        insert(con, "trade_notes", trade_id=1, note_date="2026-12-02", tags='["giris_kalitesi"]',
               text="sabit sablon notu", model="code", cost_usd=0.0)
        con.commit()
    except sqlite3.IntegrityError as e:
        pytest.fail(f"trade_notes gecerli satiri reddetti: {e}")
    finally:
        con.close()
    r = raw(v5, "SELECT trade_id, note_date, tags, text, model, cost_usd FROM trade_notes")
    assert r == [(1, "2026-12-02", '["giris_kalitesi"]', "sabit sablon notu", "code", 0.0)]


def test_trade_notes_empty_after_migration(migrated):
    p, _ = migrated
    assert raw(p, "SELECT COUNT(*) FROM trade_notes")[0][0] == 0


# ------------------------------------------------------------------------------------------ bot CHECK / eski satirlar
def test_old_twin_rows_survive_and_bot_check_remains(migrated):
    p, before = migrated
    assert [r[0] for r in raw(p, "SELECT bot FROM decision_events ORDER BY id")] == ["learner"] * 4 + ["twin"]
    # "bot CHECK'i eski satirlar icin kalir": gecersiz bot degeri yine reddedilir
    assert not try_decision(p, bot="other", extra=arm("T1", "1h"))


def test_fresh_and_migrated_decision_tables_same_columns(migrated, fresh):
    p, _ = migrated
    assert sorted(cols(p, "decision_events")) == sorted(cols(fresh, "decision_events"))
    assert sorted(cols(p, "trade_entries")) == sorted(cols(fresh, "trade_entries"))
    assert sorted(cols(p, "trade_notes")) == sorted(cols(fresh, "trade_notes"))
