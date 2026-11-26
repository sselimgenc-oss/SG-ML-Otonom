"""Alinmayan sinyal gece isi (docs/alinmayan-sinyal-spec.md): sizinti guvenligi, bariyerler, ayni-mum kurali, idempotans, CLI."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import counterfactual as CF
from trader_core import ledger as L
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar

from test_ledger_v2_spec import BASE, mk_decision, new_ledger

UTC = timezone.utc
H = timedelta(hours=1)
PAIR = "ETH/USDT"
E_, S_, T_ = 2000.0, 1960.0, 2100.0          # R = 40; +2R = 2080; plan hedefi 2100 = 2.5R
COST = 2 * 0.001 * 2000.0 / 40.0             # 0,1 R


def dec(i=1, ts=None, side="long", entry=E_, stop=S_, target=T_, reason="veto_blocked", final="skipped"):
    return SimpleNamespace(id=i, pair=PAIR, side=side, setup="R1", trigger_tf="1h", bar_close_ts=ts or BASE + 10 * H,
                           planned_entry=entry, planned_stop=stop, planned_target=target, skip_reason=reason,
                           final_action=final)


def mk_market(tmp_path, n=72 + 5, start=None, *, flat=(2001.0, 1999.0, 2000.0), over=None, written_after=True, skip=(), open_=2000.0):
    """Karar mumu BASE+10h kapanir -> pencere BASE+10h'ten baslar. over: {k: (h, l, c)} pencere mumu k icin."""
    p = tmp_path / "market.sqlite"
    st = MarketStore(p)
    start = start or BASE + 10 * H
    bars = []
    for k in range(n):
        if k in skip:
            continue
        h, l, c = (over or {}).get(k, flat)
        bars.append(Bar(PAIR, "last", "1h", start + k * H, open_, h, l, c, 1.0))
    now_ms = int((start + (n + 1) * H).timestamp() * 1000) if written_after else int(start.timestamp() * 1000)
    st.put_bars(bars, now_ms=now_ms)
    st.close()
    return p


def run(tmp_path, decisions, market, now, **kw):
    store = CF.CounterfactualStore(tmp_path / "cf.sqlite")
    try:
        r = CF.run_once(bot="learner", decisions=decisions, market_path=market, store=store, now=now, **kw)
        rows = {(x["decision_id"], x["method"]): dict(x) for x in store._db.execute("SELECT * FROM cf_outcomes")}
    finally:
        store.close()
    return r, rows


NOW_OK = BASE + (10 + 72) * H + H            # ufuk doldu (+1 saat)


# ---- sizinti guvenligi --------------------------------------------------------------------------------------
def test_horizon_not_elapsed_is_not_computed_even_if_barrier_already_hit(tmp_path):
    mk = mk_market(tmp_path, over={3: (2100.0, 1999.0, 2000.0)})                # +2R 4. mumda vurdu
    now = BASE + (10 + 72) * H - timedelta(seconds=1)                            # ufka 1 sn var
    r, rows = run(tmp_path, [dec()], mk, now)
    assert r.pending == 1 and r.computed == 0 and rows == {}
    r, rows = run(tmp_path, [dec()], mk, BASE + (10 + 72) * H)                   # tam ufuk dolunca hesaplanir
    assert r.computed == 1 and len(rows) == 2


def test_bars_written_before_their_close_are_ignored(tmp_path):
    mk = mk_market(tmp_path, written_after=False)                                # written_ms = pencere baslangici (kapanistan once)
    r, rows = run(tmp_path, [dec()], mk, NOW_OK)
    assert r.pending == 1 and rows == {}


def test_missing_bar_waits_then_data_gap_after_grace(tmp_path):
    mk = mk_market(tmp_path, skip={30})
    r, rows = run(tmp_path, [dec()], mk, NOW_OK)
    assert r.pending == 1 and rows == {}
    r, rows = run(tmp_path, [dec()], mk, NOW_OK + CF.GAP_GRACE)
    assert r.gap == 1 and {k[1] for k in rows} == {"barrier", "plan"}
    assert all(v["exit_reason"] == "data_gap" and v["hyp_r_net"] is None for v in rows.values())


def test_holdout_decisions_never_read(tmp_path, monkeypatch):
    monkeypatch.setattr(CF, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    ts = datetime(2026, 6, 1, tzinfo=UTC)
    mk = mk_market(tmp_path, start=ts)
    r, rows = run(tmp_path, [dec(ts=ts)], mk, datetime(2026, 12, 20, tzinfo=UTC))
    assert r.holdout_skipped == 1 and rows == {}


def test_entered_and_reasonless_decisions_ignored(tmp_path):
    mk = mk_market(tmp_path)
    r, rows = run(tmp_path, [dec(1, final="entered", reason=None), dec(2, reason=None)], mk, NOW_OK)
    assert r.scanned == 0 and rows == {}


# ---- bariyerler ------------------------------------------------------------------------------------------------
def test_target_barrier_and_plan_target_differ(tmp_path):
    mk = mk_market(tmp_path, over={4: (2085.0, 1999.0, 2050.0), 9: (2101.0, 2000.0, 2100.0)})
    _, rows = run(tmp_path, [dec()], mk, NOW_OK)
    b, p = rows[(1, "barrier")], rows[(1, "plan")]
    assert (b["exit_reason"], b["hyp_outcome"], b["bars_held"]) == ("target", 1, 5)
    assert b["hyp_r_gross"] == pytest.approx(2.0) and b["hyp_r_net"] == pytest.approx(2.0 - COST)
    assert (p["exit_reason"], p["bars_held"]) == ("target", 10) and p["hyp_r_gross"] == pytest.approx(2.5)
    assert b["version"] == CF.VERSION and b["computed_at"] and b["skip_reason"] == "veto_blocked"


def test_stop_barrier(tmp_path):
    mk = mk_market(tmp_path, over={2: (2001.0, 1959.0, 1970.0)})
    _, rows = run(tmp_path, [dec()], mk, NOW_OK)
    for m in ("barrier", "plan"):
        r = rows[(1, m)]
        assert (r["exit_reason"], r["hyp_outcome"], r["bars_held"]) == ("stop", 0, 3)
        assert r["hyp_r_gross"] == pytest.approx(-1.0) and r["hyp_r_net"] == pytest.approx(-1.0 - COST)


def test_time_barrier_marks_to_last_close(tmp_path):
    mk = mk_market(tmp_path, over={71: (2021.0, 1999.0, 2020.0), 47: (2011.0, 1999.0, 2010.0)})   # 72. kapanis +0.5R, 48. +0.25R
    _, rows = run(tmp_path, [dec()], mk, NOW_OK)
    r = rows[(1, "barrier")]
    assert (r["exit_reason"], r["hyp_outcome"], r["bars_held"]) == ("time", 0, 72)
    assert r["hyp_r_gross"] == pytest.approx(0.5) and r["hyp_r_net"] == pytest.approx(0.5 - COST)


def test_plan_horizon_is_48_bars_and_barrier_stays_72(tmp_path):             # bulgu 1+2: plan ufku 48
    assert CF.PLAN_HORIZON_BARS == 48 and CF.HORIZON_BARS == 72
    mk = mk_market(tmp_path, over={47: (2011.0, 1999.0, 2010.0), 60: (2101.0, 1999.0, 2050.0)})
    _, rows = run(tmp_path, [dec()], mk, NOW_OK)
    p, b = rows[(1, "plan")], rows[(1, "barrier")]
    assert (p["exit_reason"], p["bars_held"]) == ("time", 48) and p["hyp_r_gross"] == pytest.approx(0.25)
    assert p["version"] == CF.VERSION == 2
    assert b["exit_reason"] == "target" and b["bars_held"] == 61            # barrier 72 mum: 61. mumdaki hedef sayilir, plan gormez


def test_same_bar_both_barriers_stop_first(tmp_path):
    mk = mk_market(tmp_path, over={6: (2100.0, 1950.0, 2000.0)})
    _, rows = run(tmp_path, [dec()], mk, NOW_OK)
    assert rows[(1, "barrier")]["exit_reason"] == "stop" and rows[(1, "plan")]["exit_reason"] == "stop"


def test_short_side_and_no_plan_target(tmp_path):
    mk = mk_market(tmp_path, over={5: (2001.0, 1919.0, 1950.0)})                # short: +2R = 1920
    _, rows = run(tmp_path, [dec(side="short", stop=2040.0, target=None)], mk, NOW_OK)
    assert rows[(1, "barrier")]["exit_reason"] == "target" and rows[(1, "barrier")]["bars_held"] == 6
    assert rows[(1, "plan")]["exit_reason"] == "time"                           # T1: hedef yok -> yalniz stop/zaman


def test_first_window_bar_is_the_bar_after_decision_bar(tmp_path):
    # karar mumunun (BASE+9h..10h) kendisi tarama disi: bu mumda dev dalgalanma olsa da sayilmaz
    st = MarketStore(tmp_path / "market.sqlite")
    st.put_bars([Bar(PAIR, "last", "1h", BASE + 9 * H, 2000.0, 2200.0, 1800.0, 2000.0, 1.0)], now_ms=int((BASE + 100 * H).timestamp() * 1000))
    st.close()
    mk = mk_market(tmp_path)
    _, rows = run(tmp_path, [dec()], mk, NOW_OK)
    assert rows[(1, "barrier")]["exit_reason"] == "time"


def test_invalid_plan_recorded_without_numbers(tmp_path):
    mk = mk_market(tmp_path)
    _, rows = run(tmp_path, [dec(stop=2000.0)], mk, NOW_OK)
    assert all(v["exit_reason"] == "invalid_plan" and v["hyp_r_net"] is None for v in rows.values())


# ---- idempotans -------------------------------------------------------------------------------------------------
def test_idempotent_rows_never_recomputed(tmp_path):
    mk = mk_market(tmp_path, over={4: (2085.0, 1999.0, 2050.0)})
    store = CF.CounterfactualStore(tmp_path / "cf.sqlite")
    r1 = CF.run_once(bot="learner", decisions=[dec()], market_path=mk, store=store, now=NOW_OK)
    first = [tuple(x) for x in store._db.execute("SELECT * FROM cf_outcomes ORDER BY method")]
    r2 = CF.run_once(bot="learner", decisions=[dec()], market_path=mk, store=store, now=NOW_OK + 10 * H)
    again = [tuple(x) for x in store._db.execute("SELECT * FROM cf_outcomes ORDER BY method")]
    assert (r1.computed, r1.rows_written, r2.computed, r2.already, r2.rows_written) == (1, 2, 0, 1, 0)
    assert first == again                                                        # computed_at dahil degismez
    assert store.insert([{**{k: first[0][i] for i, k in enumerate(
        [c[1] for c in store._db.execute("PRAGMA table_info(cf_outcomes)")])}}]) == 0   # PK catismasi: dokunmaz
    store.close()


def test_dry_run_writes_nothing(tmp_path):
    mk = mk_market(tmp_path)
    r, rows = run(tmp_path, [dec()], mk, NOW_OK, dry_run=True)
    assert r.computed == 1 and r.rows_written == 0 and rows == {}


def test_market_is_opened_read_only(tmp_path):
    mk = mk_market(tmp_path)
    m = CF._Market(mk)
    with pytest.raises(sqlite3.OperationalError):
        m._db.execute("DELETE FROM bars")
    m.close()


# ---- okuma / rapor ----------------------------------------------------------------------------------------------
def test_summary_per_reason_and_window(tmp_path):
    mk = mk_market(tmp_path, over={2: (2001.0, 1959.0, 1970.0)})
    ds = [dec(1, reason="veto_blocked"), dec(2, reason="stop_width"),
          dec(3, ts=BASE - timedelta(days=30), reason="ml_filter")]             # pencere disi (eski)
    st = CF.CounterfactualStore(tmp_path / "cf.sqlite")
    # eski karar icin ayri bir piyasa penceresi gerek: yalniz ilk ikisi hesaplanir, ucuncu veri bosluguna duser
    CF.run_once(bot="learner", decisions=ds, market_path=mk, store=st, now=NOW_OK + CF.GAP_GRACE)
    st.close()
    s = CF.summary(tmp_path / "cf.sqlite", "learner", now=NOW_OK + CF.GAP_GRACE, days=7)
    assert s["n"] == 2 and s["mean_r_net"] == pytest.approx(-1.0 - COST)
    assert set(s["by_reason"]) == {"veto_blocked", "stop_width"}
    with pytest.raises(CF.CounterfactualError):
        CF.summary(tmp_path / "yok.sqlite", "learner", now=NOW_OK)
    assert not (tmp_path / "yok.sqlite").exists()


def test_telegram_report_line(tmp_path):
    from trader_core import telegram as T
    mk = mk_market(tmp_path, over={2: (2001.0, 1959.0, 1970.0)})
    out = tmp_path / "var"
    out.mkdir()
    st = CF.CounterfactualStore(out / "counterfactual.sqlite")
    CF.run_once(bot="learner", decisions=[dec()], market_path=mk, store=st, now=NOW_OK)
    st.close()
    cfg = T.TelegramConfig("1:tok", 5, str(tmp_path / "tg"), ledger_path=str(out / "ledger.sqlite"))
    now = NOW_OK + H
    # 26.11: "alinmayan sinyaller" Telegram'dan kalkti (gunluk ozette/komutlarda yok); varsayimsal sonuc hesabi ve ozeti (CF.summary) durur
    assert not hasattr(T, "section_counterfactual") and not hasattr(T, "rapor_kacirilan")
    assert "Alınmayan sinyaller (son 7 gün)" not in T.default_sections(cfg, now, "2026-12-05")
    sm = CF.summary(out / "counterfactual.sqlite", "learner", now=now, days=7)
    assert sm["n"] == 1 and sm["by_reason"]["veto_blocked"]["n"] == 1 and sm["by_reason"]["veto_blocked"]["mean_r_net"] == pytest.approx(-1.10, abs=0.005)      # bulgu 9


# ---- CLI (gercek defter, salt okunur) -------------------------------------------------------------------------
def _cli_env(tmp_path):
    led, lpath = new_ledger(tmp_path)
    sk = dict(veto_status="not_evaluated", risk_allowed=None, risk_reason=None, size_qty=None, size_notional=None,
              size_margin=None, size_risk_amount=None, leverage=None, final_action="skipped", skip_reason="stop_width")
    led.record_decision(mk_decision(bar=BASE + 10 * H, **sk))                    # atlanan
    led.record_decision(mk_decision(bar=BASE + 20 * H))                          # alinan: islenmez
    led.close()
    return lpath


def _main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import counterfactual_run
    return counterfactual_run.main


def test_cli_once_and_idempotent(tmp_path, capsys):
    lpath = _cli_env(tmp_path)
    mk = mk_market(tmp_path, over={2: (2001.0, 1959.0, 1970.0)})
    out = tmp_path / "cf.sqlite"
    argv = ["--bot", "learner", "--once", "--ledger", str(lpath), "--market", str(mk), "--out", str(out)]
    assert _main()(argv, now_fn=lambda: NOW_OK) == 0
    j = json.loads(capsys.readouterr().out)
    assert j["status"] == "ok" and j["scanned"] == 1 and j["computed"] == 1 and j["rows_written"] == 2
    assert _main()(argv, now_fn=lambda: NOW_OK + H) == 0
    j = json.loads(capsys.readouterr().out)
    assert j["already"] == 1 and j["rows_written"] == 0
    # --since sonrasi: karar kapsam disi
    assert _main()(argv + ["--since", "2027-01-01"], now_fn=lambda: NOW_OK) == 0
    assert json.loads(capsys.readouterr().out)["scanned"] == 0


def test_cli_exit_codes(tmp_path, capsys):
    lpath = _cli_env(tmp_path)
    base = ["--bot", "learner", "--ledger", str(lpath), "--out", str(tmp_path / "cf.sqlite")]
    assert _main()(base, now_fn=lambda: NOW_OK) == 1                             # --once yok
    assert _main()(base + ["--once", "--market", str(tmp_path / "yok.sqlite")], now_fn=lambda: NOW_OK) == 3
    with pytest.raises(SystemExit):                                              # DD-12: ikiz kaldirildi; --bot twin gecersiz
        _main()(["--bot", "twin", "--once", "--ledger", str(tmp_path / "yok.sqlite")], now_fn=lambda: NOW_OK)
    capsys.readouterr()


# ---- bulgu 3: hedef kar tarafinda degilse plan satiri invalid_plan ---------------------------------------------------
def test_plan_target_on_wrong_side_is_invalid_plan_not_a_fake_win(tmp_path):
    mk = mk_market(tmp_path, flat=(101.0, 99.7, 100.0), open_=100.0)           # fiyat 99,7..101
    r, rows = run(tmp_path, [dec(entry=100.0, stop=99.0, target=99.5)], mk, NOW_OK)   # long: hedef giris altinda (tam vaka)
    p, b = rows[(1, "plan")], rows[(1, "barrier")]
    assert p["exit_reason"] == "invalid_plan" and p["hyp_outcome"] is None and p["hyp_r_net"] is None
    assert b["exit_reason"] != "invalid_plan" and b["hyp_r_net"] is not None   # barrier etkilenmez
    _, rows = run(tmp_path, [dec(2, side="short", entry=100.0, stop=101.5, target=100.5)], mk, NOW_OK)
    assert rows[(2, "plan")]["exit_reason"] == "invalid_plan"
    _, rows = run(tmp_path, [dec(3, entry=100.0, stop=99.0, target=100.0)], mk, NOW_OK)   # hedef == giris: siki degil
    assert rows[(3, "plan")]["exit_reason"] == "invalid_plan"
    _, rows = run(tmp_path, [dec(4, entry=100.0, stop=99.0, target=100.8)], mk, NOW_OK)   # gecerli kontrol
    assert rows[(4, "plan")]["exit_reason"] != "invalid_plan"


def test_outcomes_only_known_by_as_of_and_plan_needs_version_2(tmp_path):    # bulgu 7
    mk = mk_market(tmp_path)
    run(tmp_path, [dec()], mk, NOW_OK)
    dts = BASE + 10 * H
    end = dts + 72 * H
    path = tmp_path / "cf.sqlite"
    assert len(CF.outcomes(path, "learner", now=end + 2 * H, days=30)) == 1
    assert CF.outcomes(path, "learner", now=end - H, days=30) == []             # pencere bitmeden bilinmez
    row = CF.outcomes(path, "learner", now=end + 2 * H, days=30, method="plan")[0]
    assert {"side", "trigger_tf", "planned_entry", "planned_stop", "planned_target"} <= set(row)
    db = sqlite3.connect(path)
    db.execute("UPDATE cf_outcomes SET version=1 WHERE method='plan'")
    db.commit()
    db.close()
    assert CF.outcomes(path, "learner", now=end + 2 * H, days=30, method="plan") == []


def test_summary_neden_basina_sayilar(tmp_path):                              # bulgu 9 (Telegram satiri kalkti; ozet hesabi durur)
    mk = mk_market(tmp_path)
    out = tmp_path / "var"
    out.mkdir()
    st = CF.CounterfactualStore(out / "counterfactual.sqlite")
    ds = [dec(1, reason="veto_blocked"), dec(2, reason="veto_blocked"), dec(3, reason="stop_width"),
          dec(4, reason="stop_width"), dec(5, reason="rr_below_min"), dec(6, reason="ml_filter")]
    CF.run_once(bot="learner", decisions=ds, market_path=mk, store=st, now=NOW_OK)
    st.close()
    sm = CF.summary(out / "counterfactual.sqlite", "learner", now=NOW_OK + H, days=7)
    assert sm["n"] == 6 and {k: b["n"] for k, b in sm["by_reason"].items()} == {"veto_blocked": 2, "stop_width": 2, "rr_below_min": 1, "ml_filter": 1}
