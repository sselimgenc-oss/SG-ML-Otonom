"""DD-12 WP-13 uygulayici duman testleri: 15dk/4s/1g pencereleri, seansa gore kayma, kurulum karnesi, kurulum dersi
(ac/kapa, geri alma; sonumlu ortalama, shrink_n varsayilan 0), arm_disabled kapisi ve durum dosyasi."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from trader_core import counterfactual as CF  # noqa: E402
from trader_core import kol_yasam as LS  # noqa: E402
from trader_engine import arm_guard as AG  # noqa: E402
from trader_engine.marketdata.store import MarketStore  # noqa: E402
from trader_engine.types import Bar  # noqa: E402

from test_dd12_wp04_impl import env, _go  # noqa: E402,F401  (paper kapi fixture'i)
from test_engine_05_impl_smoke import _row  # noqa: E402

UTC = timezone.utc
PAIR = "BTC/USDT"
T0 = datetime(2026, 12, 1, tzinfo=UTC)                 # holdout (2026-05..11) disinda
NOW = datetime(2026, 12, 10, tzinfo=UTC)


def _ms(dt):
    return int(dt.timestamp() * 1000)


def mk_bars(tmp_path, tf, start, n, *, flat=(101.0, 99.0, 100.0), open_=100.0, over=None, skip=(), pair=PAIR):
    p = tmp_path / f"market_{tf}.sqlite"
    st = MarketStore(p)
    step = timedelta(milliseconds=CF.ARM_TF_MS[tf])
    bars = []
    for k in range(n):
        if k in skip:
            continue
        h, l, c = (over or {}).get(k, flat)
        bars.append(Bar(pair, "last", tf, start + k * step, open_, h, l, c, 1.0))
    st.put_bars(bars, now_ms=_ms(start + (n + 2) * step))
    st.close()
    return p


def dec(i, *, tf="15m", ts=T0, side="long", entry=100.0, stop=99.0, target=None, reason="entry_gate_closed",
        session=None, arm=None, final="skipped", pair=PAIR):
    return SimpleNamespace(id=i, pair=pair, side=side, setup="R1", trigger_tf=tf, bar_close_ts=ts,
                           planned_entry=entry, planned_stop=stop, planned_target=target, skip_reason=reason,
                           final_action=final, session_tag=session, arm_id=arm)


def run(tmp_path, decisions, market, now, **kw):
    store = CF.CounterfactualStore(tmp_path / "cf.sqlite")
    try:
        r = CF.run_once(bot="learner", decisions=decisions, market_path=market, store=store, now=now, **kw)
        rows = {(x["decision_id"], x["method"]): dict(x) for x in store._db.execute("SELECT * FROM cf_outcomes")}
    finally:
        store.close()
    return r, rows


# ---- pencereler: her zaman dilimi kendi barlarindan --------------------------------------------------------------
def test_15m_window_reads_15m_bars(tmp_path):
    p = mk_bars(tmp_path, "15m", T0, 4)
    mk = CF._Market(p)
    try:
        rows = mk.window(PAIR, _ms(T0), 4, "15m")
    finally:
        mk.close()
    assert [r[0] for r in rows] == [_ms(T0) + k * 900_000 for k in range(4)]


def test_1d_window_is_built_from_full_4h_days_only(tmp_path):
    p = mk_bars(tmp_path, "4h", T0, 15, skip=(13, 14))           # gun 1 tam (6), gun 2 tam (6), gun 3 eksik
    mk = CF._Market(p)
    try:
        rows = mk.window(PAIR, _ms(T0), 3, "1d")
    finally:
        mk.close()
    assert [r[0] for r in rows] == [_ms(T0), _ms(T0 + timedelta(days=1))]    # gun 3 yok -> bosluk sayilir
    assert rows[0][1] == 101.0 and rows[0][2] == 99.0 and rows[0][3] == 100.0


def test_1d_decision_resolves_on_daily_barrier(tmp_path):
    over = {6: (103.0, 99.5, 102.5)}                             # 2. gun ilk 4s: hedef (2R = 102) vurulur
    p = mk_bars(tmp_path, "4h", T0, 12, over=over, flat=(101.0, 99.5, 100.0))   # dusuk 99,5: stop (99) degmez
    d = dec(1, tf="1d", ts=T0, target=None, reason="entry_gate_closed")
    _, rows = run(tmp_path, [d], p, T0 + timedelta(days=3), horizon=2)
    row = rows[(1, "barrier")]
    assert row["arm_id"] == "R1@1d" and row["exit_reason"] == "target"
    assert row["hyp_r_gross"] == pytest.approx(2.0)
    assert row["hyp_r_net"] == pytest.approx(2.0 - 0.2)          # kripto taban 5 bp/taraf (giris+cikis) + 2 x 5 bp ucret


# ---- seansa gore kayma -------------------------------------------------------------------------------------------
def test_slippage_follows_session_table(tmp_path):
    p = mk_bars(tmp_path, "15m", T0, 3, flat=(101.0, 99.5, 100.5))   # zaman cikisi: kapanis 100.5 -> brut +0,5 R
    table = {PAIR: {"open": {"slip_entry_bps": 4.0, "slip_exit_bps": 4.0, "slip_stop_bps": 10.0},
                    "closed": {"slip_entry_bps": 6.0, "slip_exit_bps": 6.0, "slip_stop_bps": 15.0}}}
    ds = [dec(1, session="open"), dec(2, session="closed")]
    _, rows = run(tmp_path, ds, p, T0 + timedelta(hours=2), horizon=3, cost_table=table,
                  asset_class_of=lambda pair: AG.CLASS_EQUITY)
    o, c = rows[(1, "barrier")], rows[(2, "barrier")]
    assert o["exit_reason"] == "time" and o["hyp_r_gross"] == pytest.approx(0.5)
    assert o["cost_r"] == pytest.approx(100 * (2 * 0.0005 + 0.0004 + 0.0004) / 1.0)     # 0,18 R
    assert c["cost_r"] == pytest.approx(100 * (2 * 0.0005 + 0.0006 + 0.0006) / 1.0)     # 0,22 R
    assert o["hyp_r_net"] == pytest.approx(0.32) and c["hyp_r_net"] == pytest.approx(0.28)
    assert o["arm_id"] == "R1@15m" and o["session_tag"] == "open" and o["asset_class"] == "hisse"
    assert c["session_tag"] == "closed"


def test_store_v1_is_migrated_in_place(tmp_path):
    path = tmp_path / "cf.sqlite"
    st = CF.CounterfactualStore(path)
    st._db.execute("ALTER TABLE cf_outcomes DROP COLUMN arm_id")
    st._db.execute("ALTER TABLE cf_outcomes DROP COLUMN session_tag")
    st._db.execute("ALTER TABLE cf_outcomes DROP COLUMN asset_class")
    st._db.execute("PRAGMA user_version=1")
    st.close()
    st = CF.CounterfactualStore(path)
    try:
        cols = {r[1] for r in st._db.execute("PRAGMA table_info(cf_outcomes)")}
        assert {"arm_id", "session_tag", "asset_class"} <= cols
        assert st._db.execute("PRAGMA user_version").fetchone()[0] == CF.STORE_SCHEMA_VERSION
    finally:
        st.close()


# ---- kurulum dersi: ac/kapa, geri alma -----------------------------------------------------------------------------
def c(hours, r, taken=False):
    return (T0 + timedelta(hours=hours), r, taken)


def test_single_loss_closes_with_default_shrink_zero_but_not_with_shrink_ten():
    st, ev = LS.arm_lifecycle_step(None, [c(0, -1.0)], NOW, shrink_n=0)
    assert ev == "closed" and st["state"] == "closed"
    st, ev = LS.arm_lifecycle_step(None, [c(0, -1.0)], NOW, shrink_n=10)     # -1 / 11 = -0,09 > -0,15
    assert ev is None and st["state"] == "open"


def test_closed_arm_reopens_at_plus_005_damped_mean():
    prev = {"state": "closed", "epoch_start": NOW.isoformat(), "closed_at": NOW.isoformat()}
    st, ev = LS.arm_lifecycle_step(prev, [(NOW + timedelta(hours=1), 1.0, False)], NOW + timedelta(days=1))
    assert ev == "reopened" and st["state"] == "open"


def test_closure_that_cost_three_r_is_rolled_back():
    prev = {"state": "closed", "epoch_start": NOW.isoformat(), "closed_at": NOW.isoformat()}
    post = [(NOW + timedelta(hours=k), 1.0, False) for k in (1, 2, 3)]        # kapanis sonrasi 3 x +1 R kacirildi
    st, ev = LS.arm_lifecycle_step(prev, post, NOW + timedelta(days=1))
    assert ev == "rolled_back" and st["state"] == "open" and st["closed_at"] is None


def test_pre_closure_candidates_do_not_count_after_closure():
    prev = {"state": "closed", "epoch_start": NOW.isoformat(), "closed_at": NOW.isoformat()}
    st, ev = LS.arm_lifecycle_step(prev, [(NOW - timedelta(hours=5), -1.0, True)], NOW + timedelta(days=1))
    assert ev is None and st["state"] == "closed" and st["n"] == 0


def test_state_file_roundtrip_and_fail_open(tmp_path):
    path = tmp_path / "arms_off.json"
    assert AG.load_arms_off(path) == frozenset()                             # yok -> hepsi acik
    LS.write_arms_state(path, {"R1@1h": {"state": "closed", "n": 1}, "T1@4h": {"state": "open"}}, NOW)
    assert AG.load_arms_off(path) == frozenset({"R1@1h"})
    assert LS.read_arms_state(path)["T1@4h"]["state"] == "open"
    path.write_text("{bozuk", encoding="utf-8")
    assert AG.load_arms_off(path) == frozenset() and LS.read_arms_state(path) == {}


# ---- kurulum karnesi -----------------------------------------------------------------------------------------------
def test_scorecard_taken_and_counterfactual_means():
    decs = [
        dec(1, tf="1h", ts=T0, final="entered", reason=None, arm="R1@1h", pair=PAIR),
        dec(2, tf="1h", ts=T0 + timedelta(hours=1), arm="R1@1h", pair="NVDA/USDT"),
        dec(3, tf="1h", ts=T0, reason=None, arm="R1@1h", final="ignored"),
        dec(4, tf="15m", ts=T0, final="entered", reason=None, arm="T1@15m"),
    ]
    decs[1].skip_reason = "arm_disabled"
    trades = [SimpleNamespace(decision_id=1, r_multiple=1.0)]
    cf = [{"decision_id": 2, "hyp_r_net": 2.0}]
    cands = CF.arm_candidates(decisions=decs, trades=trades, cf_rows=cf,
                              asset_class_of=lambda p: AG.CLASS_EQUITY if p == "NVDA/USDT" else AG.CLASS_CRYPTO)
    sc = CF.arm_scorecard(cands, arms=["R1@1h", "T1@15m", "TF1@4h"], closed={"R1@1h"})
    r1 = sc["R1@1h"]
    assert (r1["candidates"], r1["taken"], r1["state"]) == (2, 1, "closed")
    assert r1["mean_r_taken"] == pytest.approx(1.0) and r1["mean_r_taken_cf"] == pytest.approx(1.5)
    assert r1["by_class"]["hisse"]["mean_r_taken_cf"] == pytest.approx(2.0)
    assert sc["T1@15m"]["taken"] == 1 and sc["T1@15m"]["mean_r_taken"] is None and sc["T1@15m"]["state"] == "open"
    assert sc["TF1@4h"]["candidates"] == 0


# ---- motor kapisi ------------------------------------------------------------------------------------------------
def test_gate_never_blocks_closed_arm(env):
    """19 Kasim (sahip karari): ders kurulum kapatmaz; arms_off'taki kurulum yine girer, yalniz sayac artar."""
    row = _row(pair=PAIR)
    aid = row.arm_id or AG.arm_id_of(row.setup, getattr(row, "trigger_tf", "1h"))
    env.g.arms_off = lambda: frozenset({aid})
    out = _go(env)
    assert out.action == "enter" and out.code != "arm_disabled"
    assert env.g.counters["arm_would_close"] >= 1


# ---- yapilandirma koprusu ------------------------------------------------------------------------------------------
def test_runner_reads_paper_config_cost_table_and_arms():
    import counterfactual_run as RUN
    table, asset_of, arms = RUN._paper_maps(str(ROOT / "config" / "engine.paper.json"))
    assert table["NVDA/USDT"]["closed"]["slip_stop_bps"] == 15.0
    assert asset_of("NVDA/USDT") == AG.CLASS_EQUITY and asset_of("BTC/USDT") == AG.CLASS_CRYPTO
    assert "R1@1h" in arms and "F1@1d" in arms
    json.dumps(table)                                                        # duz JSON
