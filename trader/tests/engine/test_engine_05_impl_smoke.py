"""05 gerceklemesi duman testleri (gerceklemeyi yazan ajan). Bagimsiz sartname testleri: test_engine_05_spec.py."""
from __future__ import annotations

import dataclasses
import functools
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core import risk as K
from trader_core import signals as S
from trader_core import veto
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import apply_overrides, load_engine_config
from trader_engine.engine import Engine
from trader_engine.gates import EntryGate, GateVerdict, NoVeto, build_decision_event
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.status import StatusWriter
from trader_engine.strategies import base as B
from trader_engine.strategies.registry import StrategyError, get_strategy, list_strategies
from trader_engine.strategy_runner import SignalFrame, SignalRow, WindowedSignalSource
from trader_engine.types import Position, SymbolRules

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "var" / "history"
UTC = timezone.utc
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
H = timedelta(hours=1)


# ----------------------------------------------------------------------------------------- strateji kayit defteri
def test_registry_examples():
    s = get_strategy("price_action_v1")
    assert (s.info.name, s.info.version, s.info.setups) == ("price_action_v1", "1b.0", ("T1",))
    assert s.info.paper_allowed is True and s.exit_policy() is None
    assert list_strategies() == ("price_action_v1", "price_action_v1_full", "price_action_lab_ml")
    for bad in ("../../evil", "a.b", "", "PriceAction"):
        with pytest.raises(StrategyError) as e:
            get_strategy(bad)
        assert e.value.code == "bad_name"
    with pytest.raises(StrategyError) as e:
        get_strategy("price_action_v2")
    assert e.value.code == "unknown_strategy" and "price_action_v1_full" in str(e.value)
    with pytest.raises(StrategyError) as e:
        get_strategy("price_action_v1_full", mode="paper")
    assert e.value.code == "paper_not_allowed"
    assert get_strategy("price_action_v1_full").info.setups == ("T1", "R1")
    assert get_strategy("price_action_v1") is not get_strategy("price_action_v1")


def test_param_specs_follow_ledger():
    specs = {p.name: p for p in get_strategy("price_action_v1").info.param_specs}
    assert set(specs) == set(L.PARAM_SPECS)
    assert {n for n, p in specs.items() if p.lesson_adjustable} == set(L.CORE_LESSON_PARAMS)
    assert specs["trail_atr"].lesson_bounds == tuple(L.LESSON_BOUNDS_DEFAULT["trail_atr"])
    assert specs["trail_atr"].step == L.LESSON_STEP["trail_atr"] and specs["trail_atr"].scope == tuple(L.LESSON_SCOPE["trail_atr"])   # 24.11: kapsam ledger.LESSON_SCOPE tek yerden


def test_no_dynamic_import_in_strategies_and_runner():
    pat = re.compile(r"importlib|__import__|\bexec\(|\beval\(")
    files = list((ROOT / "src" / "trader_engine" / "strategies").glob("*.py")) + \
        [ROOT / "src" / "trader_engine" / "strategy_runner.py", ROOT / "src" / "trader_engine" / "engine.py"]
    for p in files:
        assert not pat.search(p.read_text(encoding="utf-8")), p.name


def _params(**over):
    d = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    d.update(over)
    return d


def test_v1b_validate_params_rejects_15m():
    s = get_strategy("price_action_v1")
    s.validate_params(_params())
    with pytest.raises(ValueError):
        s.validate_params(_params(trigger_tf="15m"))
    get_strategy("price_action_v1_full").validate_params(_params(trigger_tf="15m"))


def _table_row(**over) -> pd.Series:
    d = {c: None for c in S.SIGNAL_COLUMNS}
    d.update(signal=True, setup="T1", side="long", planned_entry=100.0, planned_stop=98.0, planned_target=float("nan"),
            regime="trend_up", reasons="x", rh_touches=0, rl_touches=0, pullback_ema=50)
    d.update(over)
    return pd.Series(d)


def _ctx(D, last_exit, tf="1h"):
    return B.StrategyContext(pair="BTC/USDT", D=D, tf=tf, params=_params(), bars={}, last_exit=last_exit)


def test_v1b_same_bar_reentry_neutralization():
    s = get_strategy("price_action_v1")
    row = _table_row()
    D = T0 + H                                                   # sinyal bari [10:00, 11:00) -> D=11:00? D = bar kapanisi
    D = datetime(2026, 12, 1, 11, 0, tzinfo=UTC)
    out = s.post_filter(row, _ctx(D, (datetime(2026, 12, 1, 10, 20, tzinfo=UTC), "stop")))
    assert out["signal"] is False or not bool(out["signal"])
    assert out["reasons"].startswith("v1b:same_bar_reentry|") and out["skip_reason"] is None
    assert s.counters["shadow_reentry"] == 1
    for le in ((datetime(2026, 12, 1, 9, 55, tzinfo=UTC), "stop"), (datetime(2026, 12, 1, 10, 20, tzinfo=UTC), "target"), None):
        assert bool(s.post_filter(row, _ctx(D, le))["signal"]) is True
    assert bool(get_strategy("price_action_v1_full").post_filter(
        row, _ctx(D, (datetime(2026, 12, 1, 10, 20, tzinfo=UTC), "stop")))["signal"]) is True


def test_validate_table_violations():
    info = get_strategy("price_action_v1").info
    idx = pd.DatetimeIndex([pd.Timestamp(T0)])

    def tbl(**over):
        return pd.DataFrame([_table_row(**over)], index=idx)
    B.validate_table(tbl(), info, idx)
    bad = [dict(side="up"), dict(setup="R1"), dict(planned_stop=101.0), dict(planned_entry=float("nan")),
           dict(skip_reason="veto_blocked"), dict(planned_target=99.0)]
    for over in bad:
        with pytest.raises(StrategyError) as e:
            B.validate_table(tbl(**over), info, idx)
        assert e.value.code == "bad_table", over
    with pytest.raises(StrategyError):
        B.validate_table(tbl().assign(qty=1.0), info, idx)
    with pytest.raises(StrategyError):
        B.validate_table(tbl().drop(columns=["reasons"]), info, idx)


# ----------------------------------------------------------------------------------------- kill
def test_killswitch(tmp_path):
    k = Killswitch(str(tmp_path / "shared" / "KILL"), SimClock(T0))
    assert k.active() is False and k.info() is None
    k.set("tester", "deneme")
    assert k.active() is True and k.info()["by"] == "tester"
    k.clear()
    k.clear()
    assert k.active() is False
    (tmp_path / "bad").mkdir()
    assert Killswitch(str(tmp_path / "bad"), SimClock(T0)).active() is True      # okunamayan -> etkin
    (tmp_path / "raw").write_text("not json")
    assert Killswitch(str(tmp_path / "raw"), SimClock(T0)).info() == {"raw": "not json"}


# ----------------------------------------------------------------------------------------- kapi zinciri (donuk satirlar)
class _FakeBroker:
    def __init__(self, equity=1000.0):
        self.equity = equity

    def account(self):
        return type("A", (), {"equity": self.equity, "wallet": self.equity})()


class _Veto:
    def __init__(self, status="allowed", reason="ok:2026-12-01T08:50:03.120Z"):
        self.status, self.reason = status, reason

    def begin_step(self, now):
        pass

    def lookup(self, pair, side, now):
        return veto.VetoLookup(self.status, self.reason, self.status != "allowed")


def _row(**kw) -> SignalRow:
    d = dict(pair="BTC/USDT", bar_open_ts=T0 - H, bar_close_ts=T0, signal=True, setup="T1", side="long",
             skip_reason=None, planned_entry=100.0, planned_stop=98.0, planned_target=None, rr=None,
             stop_dist_atr=2.0, atr_tf=1.0, atr_4h=2.0, atr_ratio=1.0, regime="trend_up", rh=None, rl=None,
             rh_touches=0, rl_touches=0, ema_value=99.5, body_ratio=0.7, wick_ratio=None, edge_dist_atr=None,
             pullback_ema=50, reasons="t1", param_version_id=1)
    d.update(kw)
    return SignalRow(**d)


@pytest.fixture
def gate_env(tmp_path):
    clock = SimClock(T0 + timedelta(seconds=5))
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(bot="learner", kill_file=str(tmp_path / "KILL"), target_trade_risk=0.014)   # sevk edilen paper degeri 0.005
    (tmp_path / "c.json").write_text(json.dumps(raw))
    cfg = load_engine_config(tmp_path / "c.json")
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", 1000.0)

    def rules(pair):
        return SymbolRules(pair, pair.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)

    def mk(vt=None, equity=1000.0, rules_fn=rules):
        return EntryGate(cfg, led, state, Killswitch(cfg.kill_file, clock), vt or _Veto(), clock, _FakeBroker(equity),
                         rules_fn)
    yield type("E", (), {"mk": staticmethod(mk), "state": state, "ledger": led, "clock": clock, "cfg": cfg})
    state.close()
    led.close()


def _frame(**kw):
    return SignalFrame(pair="BTC/USDT", status="ok", detail=None, last=_row(**kw), table=None)


def _decide(e, frame, gate=None, pre=None):
    g = gate or e.mk()
    pre = pre or g.pre(T0, "1h", True, "1h")
    return g.decide(frame, T0, pre, 1)


def test_gate_example_a_enter(gate_env):
    out = _decide(gate_env, _frame())
    assert out.action == "enter" and out.mandatory_record and out.leverage == 3
    assert out.size.qty == pytest.approx(6.369) and out.size.risk_amount == pytest.approx(13.999062)
    ev = out.event
    assert (ev.final_action, ev.veto_status, ev.risk_allowed, ev.leverage) == ("entered", "not_evaluated", True, 3)
    assert ev.veto_reason == "not_evaluated:paper" and ev.bar_close_ts == T0
    gate_env.ledger.record_decision(ev)               # ledger kabul eder


def test_gate_ignore_rows(gate_env):
    e = gate_env
    g = e.mk()
    bad = SignalFrame("BTC/USDT", "data_gap", "hole", None, None)
    assert g.decide(bad, T0, g.pre(T0, "1h", True, "1h"), 1).action == "ignore"                 # 0
    assert _decide(e, _frame(signal=False, skip_reason=None)).action == "ignore"              # 1b
    with e.state.tx():
        e.state.mark_decided("BTC/USDT", T0, "entered")
    assert _decide(e, _frame()).action == "ignore"                                          # 2


def test_gate_row1_filtered_candidate_records_without_mark(gate_env):
    out = _decide(gate_env, _frame(signal=False, skip_reason="stop_width"))
    assert out.action == "skip" and out.mark_decided is False and not out.mandatory_record
    ev = out.event
    assert (ev.skip_reason, ev.veto_status, ev.risk_allowed, ev.veto_reason) == ("stop_width", "not_evaluated", None, None)
    gate_env.ledger.record_decision(ev)


@pytest.mark.parametrize("prep,code,skip", [
    ("params", "params_unavailable", "entry_gate_closed"),
    ("tf", "trigger_tf_changed", "entry_gate_closed"),
    ("blocked", "order_unknown", "entry_gate_closed"),
    ("kill", "kill", "entry_gate_closed"),
    ("stale", "stale_data", "other"),
])
def test_gate_pre_rows(gate_env, prep, code, skip):
    e = gate_env
    g = e.mk()
    ok, active = (prep != "params"), ("15m" if prep == "tf" else "1h")
    if prep == "blocked":
        with e.state.tx():
            e.state.kv_set("entries_blocked_reason", "order_unknown")
    if prep == "kill":
        Killswitch(e.cfg.kill_file, e.clock).set("t", "t")
    if prep == "stale":
        e.clock.set_time(T0 + timedelta(minutes=90))
    pre = g.pre(T0, "1h", ok, active)
    assert (pre.ok, pre.code, pre.skip_reason) == (False, code, skip)
    out = _decide(e, _frame(), g, pre)
    assert out.action == "skip" and out.event.skip_reason == skip and out.event.veto_reason == "gate:" + code
    assert out.event.veto_status == "not_evaluated" and out.mark_decided
    e.ledger.record_decision(out.event)


def test_gate_rules_veto_and_risk_rows(gate_env):
    e = gate_env
    from trader_engine.errors import DataError

    def no_rules(pair):
        raise DataError("yok")
    out = _decide(e, _frame(), e.mk(rules_fn=no_rules))
    assert (out.action, out.event.skip_reason, out.event.veto_reason) == ("skip", "other", "gate:rules_missing")
    # DD-12 WP-06a: kagitta veto sorgulanmaz; engelli/yok veto girisi durdurmaz (testnet/canli veto kapisi wp04 spec'te)
    for st_, rs_ in (("blocked", "funding asiri negatif"), ("missing", "file_missing")):
        v = _Veto(st_, rs_)
        out = _decide(e, _frame(), e.mk(v))
        assert (out.action, out.event.veto_status, out.event.skip_reason) == ("enter", "not_evaluated", None)
    with e.state.tx():
        e.state.kv_set("day_start:2026-12-01", 1000.0)
    out = _decide(e, _frame(), e.mk(equity=960.0))
    assert (out.event.skip_reason, out.event.veto_status, out.event.risk_allowed) == ("risk_denied", "not_evaluated", False)
    e.ledger.record_decision(out.event)


def test_build_decision_event_features_only_finite():
    ev = build_decision_event(_row(ema_value=float("nan"), body_ratio=None), "1h")
    assert "ema_value" not in ev.features and "body_ratio" not in ev.features
    assert ev.features["pullback_ema"] == 50 and isinstance(ev.features["rh_touches"], int)
    assert ev.rh is None and ev.final_action == "skipped"
    rng = build_decision_event(_row(regime="range", rh=105.0, rl=95.0), "1h")
    assert (rng.rh, rng.rl) == (105.0, 95.0)


# ----------------------------------------------------------------------------------------- uc uca (gercek veri)
needs_data = pytest.mark.skipif(not DATA.exists(), reason="var/history yok")


class _CachedSource:
    """HistoricalSource sentetik kurallari her cagride yeniden hesaplar; testte onbelleklenir."""

    def __new__(cls, *a, **k):
        from trader_engine.marketdata.sources import HistoricalSource
        v = HistoricalSource(*a, **k)
        v.rules = functools.lru_cache(maxsize=None)(v.rules)
        return v


def _build(tmp, pairs, start, *, mode="backtest", strict=True, state_path=None, bot="learner"):
    cfg = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / f"engine.{bot}.json")
    cfg = apply_overrides(cfg, mode=mode, pairs=list(pairs), var_dir=str(tmp), kill_file=str(tmp / "KILL"),
                          veto_mode="off" if mode == "backtest" else "required",
                          cost=dict(fill_model="native", granularity="15m", trigger_source="last"))
    clock = SimClock(start)
    view = _CachedSource(str(DATA), granularity="15m", synthetic_rules=True)
    broker = PaperBroker(PaperConfig(cost=cfg.cost, mmr=K.LOCKED_CFG.maint_margin_rate, wallet_start=cfg.wallet_start),
                         view.rules, view.funding, clock)
    led = L.open_ledger(str(tmp / "ledger.sqlite"), bot, create=True, clock=clock.now)
    try:
        led.get_active_params()
    except L.LedgerError:
        led.init_params(_params(), reason="strategy:price_action_v1@1b.0 smoke")
    state = StateStore(state_path or str(tmp / "state.sqlite"), bot=bot, durability="off")
    strat = get_strategy("price_action_v1")
    eng = Engine(cfg, clock=clock, view=view, broker=broker, ledger=led, state=state,
                 signals=WindowedSignalSource(view, strat, strict=strict), strategy=strat, veto=NoVeto(),
                 kill=Killswitch(cfg.kill_file, clock), status=StatusWriter(cfg.status_path, clock, cfg), strict=strict)
    return eng, cfg


@needs_data
def test_end_to_end_one_month_backtest(tmp_path):
    pytest.importorskip("pyarrow")
    start, end = datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC)
    eng, cfg = _build(tmp_path, ["BTC/USDT", "ETH/USDT"], start)
    rep = eng.start()
    assert rep.reconcile.ok and rep.unresolved_orders == 0
    s = eng.run_range(start, end)
    c = s.counters
    # islemler oldu, hata yok
    assert s.trades_opened >= 5 and s.trades_closed >= 5 and s.decisions == 31 * 24
    assert c["callback_errors"] == 0 and c["ledger_errors"] == 0
    st = eng.state
    # her giris icin stop var ve ilk stop planlanan stopla (tick yuvarlamasiyla) esit
    done = st.closed_positions_since(start)
    assert len(done) == s.trades_closed and all(p.entry_price and p.qty for p in done)
    for p in done + st.open_positions():
        if p.entry_price is None:
            continue
        stops = [o for o in st.orders_for_trade(p.trade_id) if o.role == "stop"]
        assert stops, f"trade {p.trade_id} stopsuz"
        assert p.initial_stop > 0 and p.strategy_name == "price_action_v1" and p.strategy_version == "1b.0"
        assert (p.initial_stop < p.entry_price) if p.side == "long" else (p.initial_stop > p.entry_price)
        assert p.setup == "T1"                                    # v1b: R1 kapali
        rules = eng.broker.rules(p.pair)
        assert abs(stops[0].trigger_price - p.initial_stop) <= rules.tick + 1e-9
    # defter: her giris/cikis yazildi, kararlar entered
    led = eng.ledger
    entered = [d for d in led.list_decisions() if d.final_action == "entered"]
    assert len(entered) == s.trades_opened
    tr = [led.get_trade(p.trade_id) for p in done]
    assert all(t is not None and t.exit_ts is not None for t in tr)
    assert {t.exit_reason for t in tr} <= {"stop", "trail_stop", "regime_flip", "force_exit", "other"}
    assert all(d.setup == "T1" for d in led.list_decisions())
    assert led.entries_allowed().ok
    # gun basi + broker tutarliligi + status
    assert st.kv_get("entries_blocked_reason") is None
    assert abs(eng.broker.account().wallet - (cfg.wallet_start + sum(
        (t.realized_pnl or 0.0) for t in tr))) < 1e-6 + 0.01 * len(tr)
    eng.shutdown("test")
    status = json.loads(Path(cfg.status_path).read_text())
    assert status["schema"] == "engine-status/1" and status["strategy"] == {"name": "price_action_v1", "version": "1b.0"}
    assert status["mode"] == "backtest" and status["dry_run"] is True
    assert set(c) >= {"callback_errors", "data_gaps", "ledger_errors", "unknown_orders", "mark_fallbacks",
                      "minute_gaps", "funding_missing", "exit_data_gap"}


@needs_data
def test_windowed_source_equals_direct_compute_and_runs_gaps(tmp_path):
    pytest.importorskip("pyarrow")
    D = datetime(2026, 3, 1, tzinfo=UTC)
    view = _CachedSource(str(DATA), granularity="15m", synthetic_rules=True)
    src = WindowedSignalSource(view, get_strategy("price_action_v1_full"), strict=True)
    fr = src.frame("BTC/USDT", D, S.DEFAULT_SIGNAL_PARAMS, 1)
    assert fr.status == "ok" and fr.last.bar_close_ts == D and fr.last.param_version_id == 1
    from trader_core import regime as R
    trig = view.bars("BTC/USDT", "1h", D, 1500)
    h4 = view.bars("BTC/USDT", "4h", D, 1500)
    p = S.DEFAULT_SIGNAL_PARAMS
    ref = S.compute_signals(trig[["open", "high", "low", "close"]],
                            R.align_to_base(R.classify_series(h4[["open", "high", "low", "close"]], p.regime_params()),
                                            trig.index, 4), p).iloc[-1]
    assert fr.last.regime == ref["regime"] and fr.last.signal == bool(ref["signal"])
    assert fr.last.atr_tf == pytest.approx(ref["atr_tf"])
    assert src.frame("BTC/USDT", D, S.DEFAULT_SIGNAL_PARAMS, 1) is fr            # tek tur onbellek
    first = view.data_range("BTC/USDT", "1h")[0]
    early = first + timedelta(days=1)                      # verinin ilk gunu: 1500 bar penceresi icin yetersiz gecmis
    assert src.frame("BTC/USDT", early, S.DEFAULT_SIGNAL_PARAMS, 1).status == "no_history"
    soft = WindowedSignalSource(view, get_strategy("price_action_v1"), strict=False)
    bad = soft.frame("BTC/USDT", D, S.DEFAULT_SIGNAL_PARAMS.__class__(trigger_tf="15m"), 1)
    assert bad.status == "error" and bad.last is None and soft.counters["callback_errors"] == 1
    with pytest.raises(Exception):
        WindowedSignalSource(view, get_strategy("price_action_v1"), strict=True).frame(
            "BTC/USDT", D, S.DEFAULT_SIGNAL_PARAMS.__class__(trigger_tf="15m"), 1)


@needs_data
def test_paper_replay_and_kill(tmp_path):
    """Yeniden baslatma oynatmasi (§5.5) + bayat giris kapisi + kill: kapali giris, acik pozisyon yok."""
    pytest.importorskip("pyarrow")
    t0 = datetime(2026, 3, 9, 10, 0, tzinfo=UTC)
    eng, cfg = _build(tmp_path, ["BTC/USDT", "ETH/USDT"], t0, mode="paper", strict=False)
    # ilk kurulum: imlecler elle (t0 - adim); saat t0 + 3 saat 7 dk
    with eng.state.tx():
        for p in cfg.pairs:
            eng.state.set_cursor(p, "minute", t0 - timedelta(minutes=15))
            eng.state.set_cursor(p, "decision", t0)
    eng.clock.set_time(t0 + timedelta(hours=3, minutes=7))
    rep = eng.start()
    assert rep.replayed_minutes == 12 and rep.replayed_decisions == 3     # 10:00..12:45 dakikalari, 11/12/13 kararlari
    assert eng._cursor("decision") == t0 + timedelta(hours=3)
    # D=11:00 ve 12:00 bayat: yeni giris yok; 13:00 bayat degil
    ds = eng.ledger.list_decisions()
    assert all(d.final_action == "skipped" or d.bar_close_ts == t0 + timedelta(hours=3) for d in ds)
    stale = [d for d in ds if d.veto_reason == "gate:stale_data"]
    assert all(d.bar_close_ts < t0 + timedelta(hours=3) for d in stale)
    # kill: giris yok, durum "flat"
    eng.kill.set("tester", "deneme")
    assert eng.kill_state() == "flat"
    pre = eng.gate.pre(t0 + timedelta(hours=3), "1h", True, "1h")
    assert pre.code == "kill" or pre.code == "stale_data" or pre.code in ("degraded",)
    eng.kill.clear()
    assert eng.kill_state() is None
    eng.shutdown("test")


def test_config_strategy_field():
    cfg = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / "engine.learner.json")
    assert cfg.strategy == "price_action_v1"
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.pop("strategy")
    raw["bot"] = "learner"
    p = Path(__file__).parent / "_tmp_cfg.json"
    try:
        p.write_text(json.dumps(raw))
        assert load_engine_config(p).strategy == "price_action_v1"
        raw["strategy"] = "Bad-Name"
        p.write_text(json.dumps(raw))
        from trader_engine.errors import ConfigError
        with pytest.raises(ConfigError):
            load_engine_config(p)
    finally:
        p.unlink(missing_ok=True)


def test_position_frozen_strategy_fields_roundtrip():
    st = StateStore(":memory:", bot="learner")
    base = dict(trade_id=1, bot="learner", pair="BTC/USDT", side="long", setup="T1", status="opening", decision_id=1,
                signal_bar_close_ts=T0, entry_ts=None, entry_bar_open=None, entry_price=None, qty=None, leverage=3,
                initial_stop=98.0, current_stop=98.0, stop_seq=0, stop_client_id=None, planned_target=None,
                trail_atr=3.0, param_version_id=1, trigger_tf="1h", risk_amount=14.0, margin=200.0, rh=None, rl=None,
                fee_entry=0.0, funding_paid=0.0, mfe_price=None, mae_price=None, exit_reason=None,
                exit_client_id=None, closed_ts=None)
    with st.tx():
        st.insert_position(Position(**base, strategy_name="s_x", strategy_version="9.9"))
    p = st.get_position(1)
    assert (p.strategy_name, p.strategy_version) == ("s_x", "9.9")
    assert dataclasses.replace(p, trade_id=2).strategy_name == "s_x"
    st.close()
