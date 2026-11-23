"""docs/cikis-karsi-olgu-spec.md 9 test 3, 6, 7: gece isi (run_once), depo, idempotans, bekleme, kilitli donem, salt okunur yollar."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from exit_cf_support import HR, M15, NOW_MS, T0, T0_MS, FakeMarket, _sqlite_market, build, hour_to_15m, trade
from trader_core import exit_counterfactual as EC

UP = [(100, 103, 100.5, 102.5), (102.5, 110, 102, 109), (109, 109, 100, 100), (100, 100, 100, 100)]
NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)
COST = {"taker_fee": 0.0, "slip_exit_bps": 0.0, "slip_stop_bps": 0.0}


@pytest.fixture(autouse=True)
def fake_prepare(monkeypatch):
    """Rejim/ATR hesabi motor paritesi testinde sinanir; burada kontrollu seri (ATR 1.0, trend_up)."""
    def fake(h1_rows, h4_rows, signal_params=None):
        return EC.H1Series([r[0] for r in h1_rows], [r[1] for r in h1_rows], [r[2] for r in h1_rows], [r[3] for r in h1_rows],
                           [r[4] for r in h1_rows], [1.0] * len(h1_rows), ["trend_up"] * len(h1_rows))
    monkeypatch.setattr(EC, "prepare_h1", fake)


def market(hours=UP, start_ms=T0_MS, funding=None):
    h1, m15 = build(hours, start_ms=start_ms)
    h1r = [(m, h1.o[i], h1.h[i], h1.l[i], h1.c[i]) for i, m in enumerate(h1.ms)]
    m15r = sorted((k, *v) for k, v in m15.items())
    h4 = [(start_ms - (i + 1) * EC.H4_MS, 100.0, 101.0, 99.0, 100.0) for i in range(130)][::-1]
    return FakeMarket(h1r, m15r, h4, funding if funding is not None else [])


def go(tmp_path, trades, mk, *, now=NOW, active=3.0, dry=False, **kw):
    with EC.ExitCfStore(tmp_path / "x.sqlite") as st:
        r = EC.run_once(bot="learner", trades=trades, market=mk, store=st, now=now, active_value=active, step=0.5,
                        bounds=(2.5, 3.5), cost_for=lambda t: COST, dry_run=dry, **kw)
    return r


def rows(tmp_path):
    c = sqlite3.connect(tmp_path / "x.sqlite")
    c.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in c.execute("SELECT * FROM ecf_outcomes ORDER BY trade_id, value")]
    finally:
        c.close()


def test_roles_values_parity_and_idempotence(tmp_path):
    tr = trade(own_value=2.0, actual_net_r=1.0)
    r1 = go(tmp_path, [tr], market())
    assert (r1.scanned, r1.computed, r1.rows_written, r1.already) == (1, 1, 4, 0)
    rs = rows(tmp_path)
    assert [(x["role"], x["value"]) for x in rs] == [("own", 2.0), ("down", 2.5), ("base", 3.0), ("up", 3.5)]
    assert all(x["registry_id"] == "exitcf-v1" and x["version"] == 1 and x["grid_min"] == 15 and x["param"] == "trail_atr" for x in rs)
    own = rs[0]
    assert own["parity_gap_r"] == pytest.approx(own["net_r"] - 1.0) and own["reason_match"] in (0, 1)
    assert all(x["parity_gap_r"] is None for x in rs[1:])                   # parite yalniz kendi degerindeki satirda
    r2 = go(tmp_path, [tr], market())
    assert (r2.already, r2.computed, r2.rows_written) == (1, 0, 0)
    assert rows(tmp_path) == rs                                              # ayni sonuc, ayni satirlar


def test_own_equal_active_puts_parity_on_base(tmp_path):
    go(tmp_path, [trade(own_value=3.0, actual_net_r=2.0)], market())
    rs = {x["role"]: x for x in rows(tmp_path)}
    assert set(rs) == {"base", "up", "down"} and rs["base"]["parity_gap_r"] is not None
    assert rs["up"]["parity_gap_r"] is None


def test_alternatives_respect_lesson_bounds(tmp_path):
    go(tmp_path, [trade(own_value=3.5)], market(), active=3.5)               # 3.5 + 0.5 = 4.0 > 3.5 sinir disi: up uretilmez
    assert {x["role"] for x in rows(tmp_path)} == {"base", "down"}


def test_new_active_value_adds_rows_later_old_rows_remain(tmp_path):
    go(tmp_path, [trade(own_value=3.0)], market(), active=3.0)
    n0 = len(rows(tmp_path))
    r = go(tmp_path, [trade(own_value=3.0)], market(), active=3.5)         # ders uygulandi: yeni deger 3.5 -> 4.0 sinir disi, 3.0 var
    vals = {x["value"] for x in rows(tmp_path)}
    assert vals == {2.5, 3.0, 3.5} and len(rows(tmp_path)) == n0 and r.already == 1


def test_pending_until_data_arrives_all_roles_together(tmp_path):
    mk = market(UP[:2])                                                     # veri sonu: 2 saat var
    r = go(tmp_path, [trade(exit_ts=T0 + timedelta(hours=1))], mk, now=datetime.fromtimestamp((T0_MS + 2 * HR) / 1000, tz=timezone.utc))
    assert (r.pending, r.computed, r.rows_written) == (1, 0, 0) and rows(tmp_path) == []
    r = go(tmp_path, [trade(exit_ts=T0 + timedelta(hours=1))], market(UP))
    assert (r.pending, r.computed) == (0, 1) and len(rows(tmp_path)) == 3


def test_data_gap_waits_24h_then_permanent(tmp_path):
    hours = [(100, 100.5, 99.5, 100.2)] * 6
    mk = market(hours)
    hole = T0_MS + 2 * HR + M15
    mk.m15 = [r for r in mk.m15 if r[0] != hole]
    soon = datetime.fromtimestamp((hole + 3 * HR) / 1000, tz=timezone.utc)
    tr = trade(exit_ts=T0 + timedelta(hours=1))
    assert go(tmp_path, [tr], mk, now=soon).pending == 1 and rows(tmp_path) == []
    late = datetime.fromtimestamp((hole + 25 * HR) / 1000, tz=timezone.utc)
    r = go(tmp_path, [tr], mk, now=late)
    assert r.data_gap == 1 and r.computed == 1
    rs = rows(tmp_path)
    assert {x["exit_reason_sim"] for x in rs} == {"data_gap"} and all(x["net_r"] is None for x in rs)
    assert go(tmp_path, [tr], mk, now=late).already == 1               # kalici: bir daha denenmez


def test_eligibility_counters(tmp_path):
    trs = [trade(trade_id=1), trade(trade_id=2, trigger_tf="15m"), trade(trade_id=3, exit_reason="manual"),
           trade(trade_id=4, exit_reason="liquidation"), trade(trade_id=5, setup="R1"), trade(trade_id=6, qty=0.0),
           trade(trade_id=7, exit_ts=None), trade(trade_id=8, exit_ts=NOW + timedelta(days=1))]
    r = go(tmp_path, trs, market())
    assert (r.scanned, r.skipped_15m, r.excluded_exit_reason, r.no_data, r.computed) == (7, 1, 2, 1, 1)   # R1 taranmaz


def test_max_trades_per_run_defers_rest(tmp_path):
    trs = [trade(trade_id=i, entry_ts=T0 + timedelta(seconds=i)) for i in (1, 2, 3)]
    r = go(tmp_path, trs, market(), max_trades=2)
    assert (r.computed, r.pending) == (2, 1)


def test_dry_run_writes_nothing(tmp_path):
    r = go(tmp_path, [trade()], market(), dry=True)
    assert r.computed == 1 and r.rows_written == 0 and rows(tmp_path) == []


def test_horizon_rows_are_censored_and_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(EC, "MAX_BARS", 3)
    flat = [(100, 100.5, 99.5, 100.2)] * 4
    r = go(tmp_path, [trade()], market(flat))
    assert r.censored >= 3 and r.horizon_mtm >= 3
    assert {x["exit_reason_sim"] for x in rows(tmp_path)} == {"horizon"} and {x["censored"] for x in rows(tmp_path)} == {1}


# ---------------------------------------------------------------------------- kilitli donem (test 3)
# 23.11.2026 kullanici karari: varsayilan kilit ACIK (EC.KILIT_ACIK). Asagidaki "kilitli donem" mekanizma testleri, kilit KAPALI
# bayragiyla (fixture) ayni mekanizmanin hala dogru calistigini sinar; acik davranis test_acik_kilitte_* ile sinanir.
@pytest.fixture
def kilitli(monkeypatch):
    monkeypatch.setattr(EC, "KILIT_ACIK", False)


def test_acik_kilitte_varsayilan_pencere_yok():
    hs, he = EC.to_ms(EC.HOLDOUT_START), EC.to_ms(EC.HOLDOUT_END)
    assert EC.KILIT_ACIK is True
    assert EC.holdout_hit(hs, he) is False and EC.holdout_hit(hs - 5, hs + 5) is False
    assert EC._split_ranges(hs - 5, he + 5) == [(hs - 5, he + 5)]
    assert EC.holdout_hit(hs, he, (EC.HOLDOUT_START, EC.HOLDOUT_END)) is True      # acik `holdout` argumani yine uygulanir


@pytest.mark.usefixtures("kilitli")
def test_holdout_window_rule_dates():
    d = lambda y, m, dd: EC.to_ms(datetime(y, m, dd, tzinfo=timezone.utc))           # noqa: E731
    def hit(entry):
        e = entry
        return EC.holdout_hit(e - EC.WARMUP_DAYS * EC.DAY_MS, e + EC.MAX_BARS * HR)
    assert hit(d(2026, 12, 20)) is True and hit(d(2026, 12, 21)) is False
    assert hit(d(2026, 3, 31)) is False and hit(d(2026, 4, 1)) is True       # 30 gun ufku kilitli doneme girer
    assert hit(d(2026, 7, 1)) is True and hit(d(2025, 6, 1)) is False


@pytest.mark.usefixtures("kilitli")
def test_holdout_trade_never_reads_market_or_ledger_rows(tmp_path):
    mk = market()
    r = go(tmp_path, [trade(entry_ts=datetime(2026, 12, 20, tzinfo=timezone.utc), exit_ts=datetime(2026, 12, 25, tzinfo=timezone.utc))],
           mk, now=datetime(2027, 3, 1, tzinfo=timezone.utc))
    assert (r.holdout_skipped, r.computed) == (1, 0) and mk.calls == []         # ne mum ne funding sorgusu


@pytest.mark.usefixtures("kilitli")
def test_sql_never_touches_holdout_range(tmp_path):
    db = tmp_path / "m.sqlite"
    entry = datetime(2026, 12, 21, tzinfo=timezone.utc)
    _sqlite_market(db, entry)
    ms = EC.MarketSource(db)
    stmts: list = []
    ms._db.set_trace_callback(stmts.append)
    hs, he = EC.to_ms(EC.HOLDOUT_START), EC.to_ms(EC.HOLDOUT_END)
    e = EC.to_ms(entry)
    got = ms.bars("BTC/USDT", "1h", e - 50 * EC.DAY_MS, e + 10 * EC.DAY_MS)
    assert got and all(not (hs <= r[0] < he) for r in got)
    # bolunmus okuma: istek kilitli donemi kesse bile hicbir SQL kilitli aralikta bir sinir tasimaz
    ms.bars("BTC/USDT", "1h", hs - 10 * EC.DAY_MS, he + 10 * EC.DAY_MS)
    ms.funding("BTC/USDT", hs - 10 * EC.DAY_MS, he + 10 * EC.DAY_MS)
    import re
    for s in stmts:
        for a, b in re.findall(r"open_ms>=(\d+) AND open_ms<(\d+)", s) + re.findall(r"ts_ms>=(\d+) AND ts_ms<(\d+)", s):
            a, b = int(a), int(b)
            assert b <= hs or a >= he, s                                           # ust sinir <= 2026-05-01 ya da alt sinir >= 2026-11-01
    ms.close()


@pytest.mark.usefixtures("kilitli")
def test_split_ranges():
    hs, he = EC.to_ms(EC.HOLDOUT_START), EC.to_ms(EC.HOLDOUT_END)
    assert EC._split_ranges(hs - 5, he + 5) == [(hs - 5, hs), (he, he + 5)]
    assert EC._split_ranges(hs + 1, he - 1) == []
    assert EC._split_ranges(he, he + 9) == [(he, he + 9)]


# ---------------------------------------------------------------------------- salt okunur yollar (test 7)
def test_market_source_is_read_only(tmp_path):
    db = tmp_path / "m.sqlite"
    _sqlite_market(db, T0)
    ms = EC.MarketSource(db)
    with pytest.raises(sqlite3.OperationalError):
        ms._db.execute("INSERT INTO bars VALUES('last','X','1h',1,1,1,1,1,0,1)")
    ms.close()
    with pytest.raises(EC.ExitCfError):
        EC.MarketSource(tmp_path / "yok.sqlite")


def test_store_read_only_and_missing(tmp_path):
    p = tmp_path / "s.sqlite"
    with pytest.raises(EC.ExitCfError) as e:
        EC.ExitCfStore(p, read_only=True)
    assert e.value.code == "store_missing"
    EC.ExitCfStore(p).close()
    with EC.ExitCfStore(p, read_only=True) as st:
        with pytest.raises(EC.ExitCfError):
            st.insert([])
        with pytest.raises(sqlite3.OperationalError):
            st._db.execute("DELETE FROM ecf_outcomes")


# ---------------------------------------------------------------------------- okuma API
def _seed_deltas(tmp_path, n=3):
    trs = [trade(trade_id=i, entry_ts=T0 + timedelta(days=i), exit_ts=T0 + timedelta(days=i + 4), own_value=3.0) for i in range(1, n + 1)]
    with EC.ExitCfStore(tmp_path / "x.sqlite") as st:
        for t in trs:
            h1, m15 = build(UP, start_ms=EC.to_ms(t.entry_ts))
            mk = market(UP, start_ms=EC.to_ms(t.entry_ts))
            EC.run_once(bot="learner", trades=[t], market=mk, store=st, now=NOW, active_value=3.0, step=0.5, bounds=(2.5, 3.5),
                        cost_for=lambda x: COST)
    return tmp_path / "x.sqlite"


def test_deltas_pairs_base_with_alt_and_filters_window(tmp_path):
    p = _seed_deltas(tmp_path)
    up = EC.deltas(p, "learner", now=NOW, days=400, direction="up")
    dn = EC.deltas(p, "learner", now=NOW, days=400, direction="down")
    assert len(up) == len(dn) == 3
    d0 = up[0]
    assert d0["delta_r"] == pytest.approx(d0["alt_net_r"] - d0["base_net_r"]) and d0["alt_value"] == 3.5 and d0["base_value"] == 3.0
    assert up[0]["entry_ts"] < up[1]["entry_ts"]
    early = datetime(2025, 1, 3, 12, tzinfo=timezone.utc)                       # as_of: window_end_ts <= as_of olmayanlar yok
    assert len(EC.deltas(p, "learner", now=early, days=400, direction="up")) < 3
    assert EC.deltas(p, "learner", now=NOW, days=400, direction="up", sources=("backtest",)) == []   # kaynak ayrimi
    with pytest.raises(EC.ExitCfError):
        EC.deltas(p, "learner", now=NOW, direction="sideways")
    with pytest.raises(EC.ExitCfError):
        EC.deltas(tmp_path / "yok.sqlite", "learner", now=NOW, direction="up")


def test_parity_stats_thresholds(tmp_path):
    p = tmp_path / "x.sqlite"
    with EC.ExitCfStore(p) as st:
        base = trade(own_value=3.0)
        mk_rows = []
        for i in range(25):
            r = EC._row(trade(trade_id=i + 1, own_value=3.0, actual_net_r=1.0), "learner", "base", 3.0, NOW, "last", COST, T0_MS,
                        T0_MS + HR, {"gross_r": 1.0, "fee_r": 0.0, "funding_r": 0.0, "net_r": 1.02}, "trail_stop",
                        EC.ReplayResult("ok", "trail_stop", T0_MS + HR, 100.0, 1, 1.0), 3.0)
            r["entry_ts"] = "2025-02-01T00:00:00.000Z"
            r["window_end_ts"] = "2025-02-02T00:00:00.000Z"
            mk_rows.append(r)
        st.insert(mk_rows)
    s = EC.parity_stats(p, "learner", now=NOW, days=400)
    assert s["n"] == 25 and s["status"] == "ok" and s["reason_match_rate"] == 1.0
    assert s["median_abs_r"] == pytest.approx(0.02) and s["mean_r"] == pytest.approx(0.02)
    few = EC.parity_stats(p, "learner", now=datetime(2025, 2, 1, 12, tzinfo=timezone.utc), days=400)
    assert few["n"] == 0 and few["status"] == "parity_unknown"


# ---------------------------------------------------------------------------- backtest kaynagi (yalniz gelistirme): kilitli donem bolme
@pytest.mark.usefixtures("kilitli")
def test_feather_source_never_returns_rows_inside_holdout(tmp_path, monkeypatch):
    import numpy as np
    src = EC.FeatherSource(tmp_path)
    (tmp_path / "BTC_USDT_USDT-1h-futures.feather").write_bytes(b"x")          # varlik denetimi icin yer tutucu (okuma sahte)
    hs, he = EC.to_ms(EC.HOLDOUT_START), EC.to_ms(EC.HOLDOUT_END)
    ms_all = np.arange(hs - 5 * HR, he + 5 * HR, HR, dtype="int64")
    touched = []

    def fake_load(path, cols, ranges_fn):
        spans = ranges_fn(ms_all)
        touched.extend(spans)
        idx = np.concatenate([np.arange(i, j) for i, j in spans]) if spans else np.zeros(0, dtype=int)
        return ms_all[idx], {c: np.full(len(idx), 100.0) for c in cols}
    monkeypatch.setattr(src, "_load", fake_load)
    got = src.bars("BTC/USDT", "1h", hs - 10 * HR, he + 10 * HR)
    assert got and all(not (hs <= r[0] < he) for r in got)
    assert all(not (hs <= ms_all[i] < he) and not (hs <= ms_all[j - 1] < he) for i, j in touched)       # dilimler kilitli donemi icermez
    assert EC.FeatherSource.stem("BTC/USDT") == "BTC_USDT_USDT" and src.bars("XXX/USDT", "1h", 0, hs) == []


def test_open_migrated_copy_kaynagi_degistirmez(tmp_path):
    """Gocurulmus kopya: kaynak defter bayt bayt ayni kalir, kopya guncel semada acilir."""
    import hashlib
    from trader_core import ledger as L
    src = tmp_path / "kaynak.sqlite"
    L.open_ledger(str(src), "learner").close()
    once = hashlib.sha256(src.read_bytes()).hexdigest()
    led = L.open_migrated_copy(src, tmp_path / "kopya.sqlite", "learner")
    led.close()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == once
    assert (tmp_path / "kopya.sqlite").exists()
