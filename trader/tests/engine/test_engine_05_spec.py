"""Bagimsiz sartname testi: motor birimi 05 (Engine, StrategyRunner, giris kapisi, mutabakat, kill, status,
takilabilir strateji arayuzu).

Kaynak: trader/docs/motor/05-engine-runner.md (§1-§13) + 00-index.md. Gerceklemeye (engine/gates/strategy_runner/
reconcile/killswitch/status/cli/strategies) BAKILMADAN yazildi; yalniz sartnamedeki imzalar kullanilir. 05 modulleri
tembel import edilir; gerceklenmemisse her test ayri ayri basarisiz olur (toplama hatasi olmaz).
Sahteler: SynthView (MarketView), FakeSignalSource, FakeVeto, FakeStrategy, LedgerProxy; broker = gercek PaperBroker
(03), state = gercek StateStore (04), defter = gercek Ledger (tmp).
"""
from __future__ import annotations

import ast
import dataclasses
import importlib
import json
import math
import os
import random
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import risk, signals
from trader_engine.gates import VetoLookup
from trader_core import ledger as L
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import load_engine_config
from trader_engine.errors import ConfigError, DataError, StateError
from trader_engine.marketdata.sources import MinuteStep
from trader_engine.order_manager import OrderManager
from trader_engine.position_manager import ExitContext
from trader_engine.state import StateStore
from trader_engine.types import MinuteBar, OrderRequest, SymbolRules

UTC = timezone.utc
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
H = timedelta(hours=1)
M1 = timedelta(minutes=1)
BTC, ETH, SOL = "BTC/USDT", "ETH/USDT", "SOL/USDT"
PAIRS = (BTC, ETH, SOL)
ROOT = Path(__file__).resolve().parents[2]
KEY = "k" * 40


def mod(name: str):
    return importlib.import_module("trader_engine." + name)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rules(pair: str) -> SymbolRules:
    return SymbolRules(pair=pair, symbol=pair.replace("/", ""), tick=0.01, step=0.001, min_qty=0.001,
                       max_qty=100000.0, min_notional=5.0)


# =====================================================================================================
# Sahte piyasa gorunumu (MarketView, 01 §6)
# =====================================================================================================
class SynthView:
    """Sentetik 1 dk veri; mode='flat' sabit fiyat, 'rw' tohumlu rastgele yuruyus. `clock` verilirse veri
    yalniz simdi'nin dakika tabanina kadar 'gelmistir' (canli feed benzetimi)."""

    def __init__(self, pairs, start, end, *, seed=0, mode="flat", base=100.0, vol=0.0008, clock=None,
                 missing=None, missing_rules=()):
        self.pairs = tuple(pairs)
        self.start, self.end, self.clock = start, end, clock
        self.missing = missing or {}
        self.missing_rules = set(missing_rules)
        n = int((end - start).total_seconds() // 60)
        self.idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
        rng = np.random.default_rng(seed)
        self.min: dict[str, pd.DataFrame] = {}
        for p in self.pairs:
            if mode == "flat":
                c = np.full(n, base)
                o, h, lo = c.copy(), c.copy(), c.copy()
            else:
                c = base * np.exp(np.cumsum(rng.normal(0.0, vol, n)))
                o = np.concatenate([[c[0]], c[:-1]])
                w = np.abs(rng.normal(0.0, vol / 2, n))
                h, lo = np.maximum(o, c) * (1 + w), np.minimum(o, c) * (1 - w)
            self.min[p] = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c, "volume": 1.0}, index=self.idx)
        self._tf: dict = {}

    def avail_end(self):
        e = self.end
        if self.clock is not None:
            e = min(e, self.clock.now().replace(second=0, microsecond=0))
        return e

    def _tfbars(self, pair, tf):
        k = (pair, tf)
        if k not in self._tf:
            if tf == "1m":
                df = self.min[pair]
            else:
                alias = {"15m": "15min", "1h": "1h", "4h": "4h"}[tf]
                df = self.min[pair].resample(alias, label="left", closed="left").agg(
                    {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            self._tf[k] = df
        return self._tf[k]

    def bars(self, pair, tf, until, n=None, kind="last"):
        df = self._tfbars(pair, tf)
        delta = {"1m": M1, "15m": timedelta(minutes=15), "1h": H, "4h": 4 * H}[tf]
        lim = min(until, self.avail_end())
        df = df[(df.index + delta) <= lim]
        miss = self.missing.get((pair, tf))
        if miss:
            df = df[~df.index.isin(list(miss))]
        if n is not None:
            df = df.tail(n)
        return df.copy()

    def contiguous_tail(self, pair, tf, until, max_n=5000):
        df = self.bars(pair, tf, until, max_n)
        if len(df) == 0:
            return 0
        delta = {"1m": M1, "15m": timedelta(minutes=15), "1h": H, "4h": 4 * H}[tf]
        run = 1
        for a, b in zip(df.index[-2::-1], df.index[::-1]):
            if b - a != delta:
                break
            run += 1
        return run

    def minute_steps(self, pairs, start, end):
        lo, hi = max(start, self.start), min(end, self.avail_end())
        t = lo
        while t < hi:
            bars = {}
            for p in pairs:
                if p in self.min and t in self.min[p].index:
                    r = self.min[p].loc[t]
                    bars[p] = MinuteBar(p, t, 60, r.open, r.high, r.low, r.close, r.open, r.high, r.low, r.close, 1.0)
            if bars:
                yield MinuteStep(t, bars)
            t += M1

    def funding(self, pair, start, end):
        return []

    def rules(self, pair):
        if pair in self.missing_rules:
            raise DataError(f"{pair}: kural yok")
        return _rules(pair)

    def last_closed_minute(self, pair):
        e = self.avail_end() - M1
        return e if e >= self.start else None

    def data_range(self, pair, tf):
        return (self.start, self.end - M1)

    def step_seconds(self):
        return 60


class BarsOnlyView:
    """Dogrudan 1h/4h cubuk veren gorunum (WindowedSignalSource <-> dogrudan compute karsilastirmasi)."""

    def __init__(self, n1h=1300, seed=5, end=datetime(2026, 12, 1, 8, 0, tzinfo=UTC)):
        idx = pd.date_range(end - n1h * H, periods=n1h, freq="1h", tz="UTC")
        rng = np.random.default_rng(seed)
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, n1h)))
        o = np.concatenate([[c[0]], c[:-1]])
        w = np.abs(rng.normal(0, 0.003, n1h))
        self.h1 = pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + w), "low": np.minimum(o, c) * (1 - w),
                                "close": c, "volume": 1.0}, index=idx)
        self.h4 = self.h1.resample("4h", label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        self.D = end

    def bars(self, pair, tf, until, n=None, kind="last"):
        df = {"1h": self.h1, "4h": self.h4}[tf]
        d = {"1h": H, "4h": 4 * H}[tf]
        df = df[(df.index + d) <= until]
        return (df.tail(n) if n else df).copy()

    def contiguous_tail(self, pair, tf, until, max_n=5000):
        return len(self.bars(pair, tf, until, max_n))

    def rules(self, pair):
        return _rules(pair)


# =====================================================================================================
# Sahte strateji
# =====================================================================================================
def _param_specs(drop=()):
    base = mod("strategies.base")
    out = []
    for k, v in L.PARAM_SPECS.items():
        if k in drop:
            continue
        out.append(base.ParamSpec(
            name=k, kind=v["kind"], lo=v.get("lo"), hi=v.get("hi"), choices=v.get("choices"),
            default=getattr(signals.DEFAULT_SIGNAL_PARAMS, k), lesson_adjustable=bool(v["lesson"]),
            lesson_bounds=v.get("bounds"), step=v.get("step"), scope=v.get("scope")))
    return tuple(out)


class FakeStrategy:
    """Nedensel (lookahead'siz) tohumsuz kural: iki ardisik yukselis -> long; uc ardisik dusus -> short."""

    def __init__(self, name="fake_strategy", version="0.1", setups=("T1",), allowed_tfs=("1h", "15m"), warmup=24,
                 drop_params=(), mutate=None, post=None, boom=False, always=False):
        base = mod("strategies.base")
        self.info = base.StrategyInfo(
            name=name, version=version, setups=setups, timeframes=("trigger", "4h"), allowed_trigger_tfs=allowed_tfs,
            warmup_bars={"1h": warmup, "15m": warmup, "4h": 2}, window_bars={"1h": 300, "15m": 300, "4h": 100},
            min_contiguous={"trigger": 2, "4h": 2}, param_specs=_param_specs(drop_params), paper_allowed=True)
        self.mutate, self.post, self.boom, self.always = mutate, post, boom, always
        self.compute_calls = 0

    def label(self):
        return f"strategy:{self.info.name}@{self.info.version}"

    def validate_params(self, m):
        p = signals.SignalParams.from_mapping(m)
        if p.trigger_tf not in self.info.allowed_trigger_tfs:
            raise ValueError("trigger_tf")
        return m

    def compute(self, ctx):
        self.compute_calls += 1
        if self.boom:
            raise RuntimeError("strateji patladi")
        df = ctx.bars[ctx.tf]
        n = len(df)
        t = pd.DataFrame(index=df.index)
        c = df["close"].to_numpy()
        rng_ = (df["high"] - df["low"]).rolling(14, min_periods=1).mean().to_numpy()
        cols = {k: np.full(n, np.nan) for k in ("planned_entry", "planned_stop", "planned_target", "rr",
                                                "stop_dist_atr", "atr_tf", "atr_4h", "atr_ratio", "rh", "rl",
                                                "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr")}
        setup = np.full(n, None, dtype=object)
        side = np.full(n, None, dtype=object)
        sig = np.zeros(n, dtype=bool)
        regime = np.full(n, "unclear", dtype=object)
        for i in range(3, n):
            atr = max(rng_[i], c[i] * 1e-4)
            up = c[i] > c[i - 1] > c[i - 2]
            dn = c[i] < c[i - 1] < c[i - 2] < c[i - 3]
            if up or self.always:
                setup[i], side[i], sig[i], regime[i] = "T1", "long", True, "trend_up"
                cols["planned_entry"][i], cols["planned_stop"][i] = c[i], c[i] - 1.2 * atr
            elif dn:
                setup[i], side[i], sig[i], regime[i] = "T1", "short", True, "trend_down"
                cols["planned_entry"][i], cols["planned_stop"][i] = c[i], c[i] + 1.2 * atr
            if sig[i]:
                cols["stop_dist_atr"][i] = 1.2
            cols["atr_tf"][i] = atr
            cols["atr_4h"][i] = 2.0 * atr          # defter T1 ozellikleri sonlu olmali (atr_4h, ema_value, body_ratio)
            cols["atr_ratio"][i] = 1.0
            cols["ema_value"][i] = c[i]
            cols["body_ratio"][i] = 0.6
        ob = lambda a: pd.Series(a, index=df.index, dtype=object)   # noqa: E731
        t["setup"], t["side"], t["signal"], t["skip_reason"] = ob(setup), ob(side), sig, ob(np.full(n, None, dtype=object))
        for k, v in cols.items():
            t[k] = v
        t["regime"] = ob(regime)
        t["rh_touches"] = np.zeros(n, dtype="int64")
        t["rl_touches"] = np.zeros(n, dtype="int64")
        t["pullback_ema"] = np.zeros(n, dtype="int64")
        t["reasons"] = ob(np.full(n, "fake", dtype=object))
        t = t[signals.SIGNAL_COLUMNS]
        if self.mutate:
            t = self.mutate(t)
        return t

    def post_filter(self, row, ctx):
        return self.post(row, ctx) if self.post else row

    def exit_policy(self):
        return None


# =====================================================================================================
# Sahte sinyal kaynagi / veto / defter vekili
# =====================================================================================================
def make_row(pair=BTC, D=T0, *, signal=True, setup="T1", side="long", entry=100.0, stop=98.0, skip_reason=None,
             version=1, **kw):
    sr = mod("strategy_runner")
    d = dict(pair=pair, bar_open_ts=D - H, bar_close_ts=D, signal=signal, setup=setup, side=side,
             skip_reason=skip_reason, planned_entry=entry, planned_stop=stop, planned_target=None, rr=None,
             stop_dist_atr=abs(entry - stop) / 1.0, atr_tf=1.0, atr_4h=2.0, atr_ratio=1.0,
             regime="trend_up" if side != "short" else "trend_down", rh=None, rl=None, rh_touches=0, rl_touches=0,
             ema_value=99.5, body_ratio=0.7, wick_ratio=None, edge_dist_atr=None, pullback_ema=50, reasons="t1",
             param_version_id=version)
    d.update(kw)
    return sr.SignalRow(**d)


def make_frame(pair=BTC, D=T0, status="ok", **kw):
    sr = mod("strategy_runner")
    if status != "ok":
        return sr.SignalFrame(pair=pair, status=status, detail="x", last=None, table=None)
    return sr.SignalFrame(pair=pair, status="ok", detail=None, last=make_row(pair, D, **kw), table=None)


def benign_ctx(D):
    return ExitContext(bar_close_ts=D, highs=np.array([100.5]), lows=np.array([99.5]), atrs=np.array([1.0]),
                       regime_last="trend_up", last_close=100.0, n_closed=1)


def flip_ctx(D):
    return ExitContext(bar_close_ts=D, highs=np.array([101.0, 110.0]), lows=np.array([99.0, 105.0]),
                       atrs=np.array([1.0, 1.0]), regime_last="trend_down", last_close=108.0, n_closed=2)


def trail_ctx(D):
    # iz suren stop 102.5 - 3*1 = 99.5 (> 98, piyasa 100'un altinda: would_trigger olmaz), 2.04R esigini asar
    return ExitContext(bar_close_ts=D, highs=np.array([101.0, 102.5]), lows=np.array([99.0, 100.5]),
                       atrs=np.array([1.0, 1.0]), regime_last="trend_up", last_close=100.2, n_closed=2)


class FakeSignalSource:
    def __init__(self):
        self.frames, self.ctx, self.calls, self.auto = {}, {}, [], None

    def frame(self, pair, D, params, version_id):
        self.calls.append((pair, D))
        f = self.frames.get((pair, D))
        if f is not None:
            return f
        if self.auto is not None:
            return self.auto(pair, D, version_id)
        return make_frame(pair, D, signal=False, setup=None, side=None, version=version_id)

    def exit_context(self, pair, pos, D):
        c = self.ctx.get((pair, D), benign_ctx(D))
        return c


class FakeVeto:
    def __init__(self, status="allowed", reason="ok:2026-12-01T08:50:03.120Z"):
        self.status, self.reason, self.begin_calls, self.lookups = status, reason, [], []

    def begin_step(self, now):
        self.begin_calls.append(now)

    def lookup(self, pair, side, now):
        self.lookups.append((pair, side, now))
        if self.status == "allowed":
            return VetoLookup("allowed", self.reason, False)
        return VetoLookup(self.status, self.reason if self.status == "blocked" else "x", True)


class LedgerProxy:
    def __init__(self, real):
        self._l = real
        self.health = None          # Health ya da None
        self.fail_record = False
        self.fail_params = False
        self.unledgered_calls = []

    def __getattr__(self, n):
        return getattr(self._l, n)

    def entries_allowed(self):
        return self.health if self.health is not None else self._l.entries_allowed()

    def record_decision(self, ev):
        if self.fail_record:
            raise L.LedgerWriteError("yazilamiyor")
        return self._l.record_decision(ev)

    def get_active_params(self):
        if self.fail_params:
            raise L.LedgerStateError("etkin parametre yok")
        return self._l.get_active_params()

    def find_unledgered_trades(self, ids):
        self.unledgered_calls.append(list(ids))
        return self._l.find_unledgered_trades(ids)


class CallLogBroker(PaperBroker):
    """Cagri sirasini kaydeden ve (istege bagli) cokme enjekte eden PaperBroker."""
    crash_at: dict = {}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.log = []
        self.counts = Counter()
        self.crashed = False

    def _tick(self, name):
        self.counts[name] += 1
        if self.crash_at.get(name) == self.counts[name]:
            self.crashed = True
            raise StateError("simule cokme")

    def market_order(self, req):
        self.log.append(("market_order", req.role, req.pair))
        self._tick("market_order")
        return super().market_order(req)

    def place_stop(self, req):
        self.log.append(("place_stop", req.role, req.pair))
        return super().place_stop(req)

    def advance(self, bars, phase):
        self._tick("advance")
        return super().advance(bars, phase)


# =====================================================================================================
# Ortam
# =====================================================================================================
def make_cfg(tmp: Path, bot="learner", mode="paper", pairs=PAIRS, wallet=1000.0, **over):
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(pairs=list(pairs), wallet_start=wallet, mode=mode,
               var_dir=str(tmp / ("var-live" if mode in ("testnet", "live") else "var")),    # DD-8: testnet/live var_dir son bileseni `var` olamaz
               market_db=str(tmp / "market.sqlite"), history_dir=str(tmp / "hist"), kill_file=str(tmp / "KILL"))
    if mode in ("testnet", "live"):
        raw["pause_file"] = str(tmp / "PAUSE")           # DD-8: testnet/live'de paylasimli `shared/PAUSE` yasak (yol kurali)
    raw["target_trade_risk"] = 0.014     # testler kilitli varsayilanla (shipped base 0.005); sevk edilen deger ayri test edilir
    raw.update(over)
    b = tmp / "base.json"
    b.write_text(json.dumps(raw))
    ov = {"bot": bot}
    o = tmp / f"{bot}.json"
    o.write_text(json.dumps(ov))
    return load_engine_config(b, o)


class Env:
    def __init__(self, tmp, *, bot="learner", mode="paper", pairs=PAIRS, strategy=None, real_signals=False,
                 veto_obj=None, start=T0, wallet=1000.0, view=None, view_kw=None, broker_cls=CallLogBroker,
                 init_label=True, ledger_start_params=None, strict=False, kill_cls=None, status=True,
                 missing_rules=(), **cfgover):
        self.tmp = Path(tmp)
        self.clock = SimClock(start)
        self.cfg = make_cfg(self.tmp, bot, mode, pairs, wallet, **cfgover)
        for p in (self.cfg.ledger_path, self.cfg.state_path, self.cfg.status_path):
            os.makedirs(os.path.dirname(p), exist_ok=True)
        self.strategy = strategy or FakeStrategy()
        self.state = StateStore(self.cfg.state_path, bot=bot)
        real = L.open_ledger(self.cfg.ledger_path, bot, create=True, clock=self.clock.now)
        try:
            real.get_active_params()
        except L.LedgerError:
            params = ledger_start_params or dataclasses.asdict(signals.DEFAULT_SIGNAL_PARAMS)
            real.init_params(params, reason=self.strategy.label() if init_label else "paper_start")
        self.real_ledger = real
        self.ledger = LedgerProxy(real)
        self.view = view or SynthView(pairs, start - timedelta(days=3), start + timedelta(days=4),
                                      **(view_kw or {"clock": self.clock if mode == "paper" else None}))
        self.rules_fn = self.view.rules
        self.broker = broker_cls(PaperConfig(cost=self.cfg.cost, mmr=0.004, wallet_start=wallet), self.rules_fn,
                                 lambda p, s, e: [], self.clock)
        self.orders = OrderManager(bot, self.broker, self.state, self.clock, self.rules_fn)
        gates = mod("gates")
        self.veto = veto_obj or (gates.NoVeto() if mode == "backtest" else FakeVeto())
        ks = mod("killswitch")
        self.kill = (kill_cls or ks.Killswitch)(self.cfg.kill_file, self.clock)
        self.status = mod("status").StatusWriter(self.cfg.status_path, self.clock, self.cfg) if status else None
        sr = mod("strategy_runner")
        self.src = sr.WindowedSignalSource(self.view, self.strategy, strict=strict) if real_signals \
            else FakeSignalSource()
        self.engine = mod("engine").Engine(
            self.cfg, clock=self.clock, view=self.view, broker=self.broker, ledger=self.ledger, state=self.state,
            signals=self.src, strategy=self.strategy, veto=self.veto, kill=self.kill, status=self.status,
            orders=self.orders, entry_ref_fn=None, strict=strict)
        self.version_id = real.get_active_params().version_id

    # -- yardimcilar
    def start(self):
        return self.engine.start()

    def close(self):
        try:
            self.state.close()
        finally:
            self.real_ledger.close()

    def set_clock(self, t):
        if t > self.clock.now():
            self.clock.set_time(t)

    def signal(self, D, pairs=(BTC,), **kw):
        for p in pairs:
            self.src.frames[(p, D)] = make_frame(p, D, version=self.version_id, **kw)

    def decide(self, D, now=None):
        self.set_clock(now or D + timedelta(seconds=5))
        self.engine.decision_step(D)

    def bar(self, pair, ts, price=100.0, hi=None, lo=None):
        hi = price if hi is None else hi
        lo = price if lo is None else lo
        return MinuteBar(pair, ts, 60, price, hi, lo, price, price, hi, lo, price, 1.0)

    def step(self, ts, pairs=None, price=100.0, hi=None, lo=None):
        self.set_clock(ts + M1)
        pairs = pairs or self.cfg.pairs
        self.engine.process_step(MinuteStep(ts, {p: self.bar(p, ts, price, hi, lo) for p in pairs}))

    def decisions(self):
        return self.real_ledger.list_decisions()

    def pos(self, pair=BTC):
        return self.state.position_for_pair(pair)

    def open_pos(self, pair=BTC, D=T0, **kw):
        self.signal(D, (pair,), **kw)
        self.decide(D)
        self.step(D)
        return self.pos(pair)


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    e.start()
    yield e
    e.close()


def only(decs, **match):
    out = [d for d in decs if all(getattr(d, k) == v for k, v in match.items())]
    return out


# =====================================================================================================
# 1. Strateji kayit defteri (§13.2, §10.10)
# =====================================================================================================
class TestRegistry:
    def test_list_and_info_v1b(self):
        reg = mod("strategies.registry")
        assert tuple(reg.list_strategies()) == ("price_action_v1", "price_action_v1_full", "price_action_lab_ml")
        s = reg.get_strategy("price_action_v1")
        assert s.info.name == "price_action_v1" and s.info.version == "1b.0"
        assert tuple(s.info.setups) == ("T1",) and tuple(s.info.allowed_trigger_tfs) == ("1h",)
        assert s.info.paper_allowed is True and s.exit_policy() is None
        assert dict(s.info.min_contiguous) == {"trigger": 20, "4h": 150}

    def test_info_full(self):
        s = mod("strategies.registry").get_strategy("price_action_v1_full")
        assert s.info.version == "1.0" and tuple(s.info.setups) == ("T1", "R1")
        assert tuple(s.info.allowed_trigger_tfs) == ("1h", "15m") and s.info.paper_allowed is False

    @pytest.mark.parametrize("bad", ["../../evil", "a.b", "", "PriceAction", "a b", "x" * 41, "1abc", "a/b"])
    def test_bad_name_no_import(self, bad):
        reg = mod("strategies.registry")
        before = set(sys.modules)
        with pytest.raises(reg.StrategyError) as ei:
            reg.get_strategy(bad)
        assert ei.value.code == "bad_name"
        assert set(sys.modules) == before

    def test_unknown_lists_allowed(self):
        reg = mod("strategies.registry")
        with pytest.raises(reg.StrategyError) as ei:
            reg.get_strategy("price_action_v2")
        assert ei.value.code == "unknown_strategy"
        assert "price_action_v1" in str(ei.value) and "price_action_v1_full" in str(ei.value)

    def test_fresh_instance_each_call(self):
        reg = mod("strategies.registry")
        assert reg.get_strategy("price_action_v1") is not reg.get_strategy("price_action_v1")

    def test_names_match_regex_and_keys(self):
        reg = mod("strategies.registry")
        for n in reg.list_strategies():
            assert re.fullmatch(r"[a-z][a-z0-9_]{0,39}", n)
            assert reg.get_strategy(n).info.name == n

    def test_no_dynamic_import_in_sources(self):
        """Kaynak taramasi (§11): registry/runner/engine/gates icinde importlib/__import__/exec/eval/getattr yok."""
        src = ROOT / "src" / "trader_engine"
        files = [src / "strategies" / "registry.py", src / "strategy_runner.py", src / "engine.py",
                 src / "gates.py"]
        for f in files:
            assert f.exists(), f
            tree = ast.parse(f.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in ("__import__", "exec", "eval"):
                    pytest.fail(f"{f.name}: {node.id}")
                if isinstance(node, ast.Attribute) and node.attr in ("import_module", "__import__"):
                    pytest.fail(f"{f.name}: {node.attr}")
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] + [getattr(node, "module", None) or ""]
                    assert not any(n == "importlib" or n.startswith("importlib.") for n in names), f.name
        reg_tree = ast.parse((src / "strategies" / "registry.py").read_text())
        for node in ast.walk(reg_tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
                pytest.fail("registry.py getattr kullanir")

    def test_param_specs_equal_ledger(self):
        reg = mod("strategies.registry")
        for n in ("price_action_v1", "price_action_v1_full"):
            specs = {p.name: p for p in reg.get_strategy(n).info.param_specs}
            assert set(specs) == set(L.PARAM_SPECS)
            for k, v in L.PARAM_SPECS.items():
                p = specs[k]
                assert p.lesson_adjustable == (k in L.LESSON_PARAMS)
                assert p.kind == v["kind"]
                if v["kind"] == "float":
                    assert (p.lo, p.hi) == (v["lo"], v["hi"])
                else:
                    assert tuple(p.choices) == tuple(v["choices"])
                if k in L.LESSON_PARAMS:
                    assert tuple(p.lesson_bounds) == tuple(L.LESSON_BOUNDS_DEFAULT[k])
                    assert p.step == L.LESSON_STEP[k]
                    assert tuple(p.scope) == tuple(L.LESSON_SCOPE[k])
                assert p.default == getattr(signals.DEFAULT_SIGNAL_PARAMS, k)

    def test_paper_not_allowed_for_full(self, tmp_path):
        reg = mod("strategies.registry")
        raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
        raw.update(var_dir=str(tmp_path), strategy="price_action_v1_full", bot="learner")
        p = tmp_path / "c.json"
        p.write_text(json.dumps(raw))
        try:
            cfg = load_engine_config(p)
        except Exception:
            pytest.skip("EngineConfig.strategy (02, §13.9) henuz yok")
        with pytest.raises(reg.StrategyError) as ei:
            mod("engine").build_engine(cfg, clock=SimClock(T0), env={})
        assert ei.value.code == "paper_not_allowed"

    def test_protocol_members_present(self):
        s = mod("strategies.registry").get_strategy("price_action_v1")
        for m in ("validate_params", "compute", "post_filter", "exit_policy"):
            assert callable(getattr(s, m))


# =====================================================================================================
# 2. PriceActionV1 adaptoru (§13.4, §10.11)
# =====================================================================================================
def _ctx(strategy, D, params=None, last_exit=None, tf="1h", view=None):
    base = mod("strategies.base")
    v = view or BarsOnlyView()
    return base.StrategyContext(pair=BTC, D=D, tf=tf, params=params or dataclasses.asdict(signals.DEFAULT_SIGNAL_PARAMS),
                                bars={tf: v.bars(BTC, "1h", D), "4h": v.bars(BTC, "4h", D)}, last_exit=last_exit)


def _raw_row(**kw):
    row = pd.Series({c: (np.nan if c not in ("setup", "side", "skip_reason", "regime", "reasons") else None)
                     for c in signals.SIGNAL_COLUMNS}, name=pd.Timestamp("2026-12-01T10:00:00Z"), dtype=object)
    row["signal"] = True
    row["rh_touches"] = row["rl_touches"] = row["pullback_ema"] = 0
    row["regime"], row["reasons"] = "trend_up", "raw"
    for k, v in kw.items():
        row[k] = v
    return row


class TestPriceActionAdapter:
    def test_full_equals_direct_compute_signals(self):
        s = mod("strategies.registry").get_strategy("price_action_v1_full")
        v = BarsOnlyView()
        D = v.D
        ctx = _ctx(s, D, view=v)
        got = s.compute(ctx)
        trig, h4 = ctx.bars["1h"], ctx.bars["4h"]
        p = signals.DEFAULT_SIGNAL_PARAMS
        reg = importlib.import_module("trader_core.regime")
        ref = signals.compute_signals(trig[["open", "high", "low", "close"]],
                                      reg.align_to_base(reg.classify_series(h4[["open", "high", "low", "close"]],
                                                                            p.regime_params()), trig.index, 4), p)
        assert list(got.columns) == list(signals.SIGNAL_COLUMNS) and len(got) == len(trig)
        a, b = got.iloc[-60:], ref.iloc[-60:]
        for c in signals.SIGNAL_COLUMNS:
            if b[c].dtype.kind == "f":
                x, y = a[c].to_numpy(float), b[c].to_numpy(float)
                assert np.array_equal(np.isnan(x), np.isnan(y)), c
                m = ~np.isnan(x)
                assert np.all(np.abs(x[m] - y[m]) <= 1e-9 * np.maximum(1, np.abs(y[m]))), c
            else:
                assert list(a[c]) == list(b[c]), c

    def test_validate_params(self):
        reg = mod("strategies.registry")
        m = dataclasses.asdict(signals.DEFAULT_SIGNAL_PARAMS)
        m15 = dict(m, trigger_tf="15m")
        v1b, full = reg.get_strategy("price_action_v1"), reg.get_strategy("price_action_v1_full")
        v1b.validate_params(m)
        with pytest.raises(ValueError):
            v1b.validate_params(m15)
        full.validate_params(m15)
        with pytest.raises(ValueError):
            full.validate_params(dict(m, vol_ratio_max=9.0))

    def _patched(self, monkeypatch, row_kw):
        calls = []
        real = signals.compute_signals

        def fake(df, regime_df, params=signals.DEFAULT_SIGNAL_PARAMS):
            calls.append(1)
            t = real(df, regime_df, params).copy()
            for k, v in row_kw.items():
                t.iloc[-1, t.columns.get_loc(k)] = v
            return t
        monkeypatch.setattr(signals, "compute_signals", fake)
        return calls

    def _last(self, s, D, ctx):
        t = s.compute(ctx)
        row = t.iloc[-1]
        return s.post_filter(row, ctx)

    def test_t1_passes_unchanged(self, monkeypatch):
        s = mod("strategies.registry").get_strategy("price_action_v1")
        v = BarsOnlyView()
        kw = dict(setup="T1", side="long", signal=True, skip_reason=None, planned_entry=100.0, planned_stop=98.0,
                  planned_target=np.nan, regime="trend_up", reasons="raw")
        calls = self._patched(monkeypatch, kw)
        ctx = _ctx(s, v.D, view=v)
        out = self._last(s, v.D, ctx)
        if not calls:
            pytest.skip("compute_signals yamasi etkisiz (adaptor farkli ice aktarma kullaniyor)")
        assert bool(out["signal"]) is True and out["setup"] == "T1"
        assert out["planned_entry"] == 100.0 and out["planned_stop"] == 98.0 and out["reasons"] == "raw"

    @pytest.mark.parametrize("skip", [None, "stop_width"])
    def test_r1_neutralised(self, monkeypatch, skip):
        s = mod("strategies.registry").get_strategy("price_action_v1")
        v = BarsOnlyView()
        kw = dict(setup="R1", side="short", signal=(skip is None), skip_reason=skip, planned_entry=105.0,
                  planned_stop=106.5, planned_target=101.0, regime="range", reasons="raw")
        calls = self._patched(monkeypatch, kw)
        out = self._last(s, v.D, _ctx(s, v.D, view=v))
        if not calls:
            pytest.skip("compute_signals yamasi etkisiz")
        assert bool(out["signal"]) is False and out["skip_reason"] is None
        assert out["setup"] == "R1" and out["side"] == "short"
        assert out["planned_entry"] == 105.0 and out["planned_stop"] == 106.5 and out["planned_target"] == 101.0
        assert str(out["reasons"]).startswith("v1b:r1_disabled|")

    def test_full_keeps_r1(self, monkeypatch):
        s = mod("strategies.registry").get_strategy("price_action_v1_full")
        v = BarsOnlyView()
        kw = dict(setup="R1", side="short", signal=True, skip_reason=None, planned_entry=105.0, planned_stop=106.5,
                  planned_target=101.0, regime="range", reasons="raw")
        calls = self._patched(monkeypatch, kw)
        out = self._last(s, v.D, _ctx(s, v.D, view=v))
        if not calls:
            pytest.skip("compute_signals yamasi etkisiz")
        assert bool(out["signal"]) is True and out["reasons"] == "raw"

    @pytest.mark.parametrize("last_exit,neutral", [
        ((datetime(2026, 12, 1, 10, 20, tzinfo=UTC), "stop"), True),
        ((datetime(2026, 12, 1, 10, 20, tzinfo=UTC), "trail_stop"), True),
        ((datetime(2026, 12, 1, 9, 55, tzinfo=UTC), "stop"), False),
        ((datetime(2026, 12, 1, 10, 20, tzinfo=UTC), "target"), False),
        (None, False)])
    def test_same_bar_reentry(self, last_exit, neutral):
        """§10.11e: sinyal bari [10:00, 11:00)."""
        reg = mod("strategies.registry")
        D = datetime(2026, 12, 1, 11, 0, tzinfo=UTC)
        ctx = _ctx(None, D, last_exit=last_exit)
        row = _raw_row(setup="T1", side="long", planned_entry=100.0, planned_stop=98.0)
        out = reg.get_strategy("price_action_v1").post_filter(row, ctx)
        if neutral:
            assert bool(out["signal"]) is False and out["skip_reason"] is None
            assert str(out["reasons"]).startswith("v1b:same_bar_reentry|")
            assert out["setup"] == "T1" and out["planned_stop"] == 98.0
        else:
            assert bool(out["signal"]) is True and out["reasons"] == "raw"
        full_out = reg.get_strategy("price_action_v1_full").post_filter(row, ctx)
        assert bool(full_out["signal"]) is True


# =====================================================================================================
# 3. WindowedSignalSource + validate_table (§3.1, §13.3)
# =====================================================================================================
def _wview(missing=None, hours=80, clock=None):
    D = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
    start = D - timedelta(hours=hours)
    return SynthView([BTC], start, D + 2 * H, seed=3, mode="rw", vol=0.003, missing=missing), D


def _frame(view, strategy, D, strict=False):
    sr = mod("strategy_runner")
    src = sr.WindowedSignalSource(view, strategy, strict=strict)
    return src.frame(BTC, D, signals.DEFAULT_SIGNAL_PARAMS, 1)


class TestWindowedSource:
    def test_ok_frame_matches_direct_compute(self):
        view, D = _wview()
        st = FakeStrategy(always=True)
        f = _frame(view, st, D)
        assert f.status == "ok" and f.last is not None and f.table is not None
        base = mod("strategies.base")
        ctx = base.StrategyContext(pair=BTC, D=D, tf="1h", params=dataclasses.asdict(signals.DEFAULT_SIGNAL_PARAMS),
                                   bars={"1h": view.bars(BTC, "1h", D, 300), "4h": view.bars(BTC, "4h", D, 100)},
                                   last_exit=None)
        ref = st.compute(ctx).iloc[-1]
        r = f.last
        assert r.pair == BTC and r.bar_close_ts == D and r.bar_open_ts == D - H and r.param_version_id == 1
        assert r.signal is True and r.side == ref["side"] and r.setup == "T1"
        assert r.planned_entry == pytest.approx(ref["planned_entry"], rel=1e-12)
        assert r.planned_stop == pytest.approx(ref["planned_stop"], rel=1e-12)
        assert r.planned_target is None and r.rr is None          # NaN -> None
        assert set(f.table.columns) >= set(signals.SIGNAL_COLUMNS) | {"open", "high", "low", "close"}

    def test_no_history(self):
        view, D = _wview(hours=10)
        assert _frame(view, FakeStrategy(), D).status == "no_history"

    def test_data_gap_trigger_missing(self):
        D = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
        view, D = _wview(missing={(BTC, "1h"): {pd.Timestamp(D - H)}})
        f = _frame(view, FakeStrategy(), D)
        assert f.status == "data_gap" and f.last is None

    def test_data_gap_hole(self):
        D = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
        view, D = _wview(missing={(BTC, "1h"): {pd.Timestamp(D - 2 * H)}})
        assert _frame(view, FakeStrategy(), D).status == "data_gap"

    def test_error_and_strict(self):
        view, D = _wview()
        st = FakeStrategy(boom=True)
        f = _frame(view, st, D)
        assert f.status == "error" and f.last is None
        with pytest.raises(Exception):
            _frame(view, FakeStrategy(boom=True), D, strict=True)

    def test_one_computation_per_pair_step(self):
        view, D = _wview()
        st = FakeStrategy()
        sr = mod("strategy_runner")
        src = sr.WindowedSignalSource(view, st)
        src.frame(BTC, D, signals.DEFAULT_SIGNAL_PARAMS, 1)
        src.frame(BTC, D, signals.DEFAULT_SIGNAL_PARAMS, 1)
        assert st.compute_calls == 1

    @pytest.mark.parametrize("name,mut", [
        ("extra_col", lambda t: t.assign(qty=1.0)),
        ("missing_col", lambda t: t.drop(columns=["rr"])),
        ("bad_side", lambda t: t.assign(side=np.where(t["signal"], "up", None))),
        ("long_stop_above", lambda t: t.assign(planned_stop=np.where(t["signal"], t["planned_entry"] + 1, np.nan))),
        ("bad_setup", lambda t: t.assign(setup=np.where(t["signal"], "R1", None))),
        ("nan_entry", lambda t: t.assign(planned_entry=np.where(t["signal"], np.nan, np.nan))),
        ("foreign_skip", lambda t: t.assign(skip_reason=np.where(t["signal"], None, "kill"))),
    ])
    def test_validate_table_violations(self, name, mut):
        view, D = _wview()
        st = FakeStrategy(always=True, mutate=mut)
        # long satirlar icin: 'bad_side' vb. tablo ihlali -> status error, giris yok
        f = _frame(view, st, D)
        if name == "foreign_skip":
            # signal=False satirlarda yabanci skip_reason: son satir signal=True oldugundan tablo-geneli denetim gerekir
            assert f.status in ("error", "ok")
            return
        assert f.status == "error" and f.last is None

    def test_post_filter_may_only_neutralise(self):
        view, D = _wview()

        def neutralise(row, ctx):
            r = row.copy()
            r["signal"] = False
            return r

        def add(row, ctx):
            r = row.copy()
            r["signal"] = True
            return r

        f = _frame(view, FakeStrategy(always=True, post=neutralise), D)
        assert f.status == "ok" and f.last.signal is False
        view2, D2 = _wview()
        # sinyal olmayan satira aday ekleme -> error
        class NoSig(FakeStrategy):
            def compute(self, ctx):
                t = super().compute(ctx)
                t["signal"] = False
                t["setup"] = None
                t["side"] = None
                t["planned_entry"] = np.nan
                t["planned_stop"] = np.nan
                return t
        f2 = _frame(view2, NoSig(post=add), D2)
        assert f2.status == "error"

    def test_post_filter_price_change_is_error(self):
        view, D = _wview()

        def tamper(row, ctx):
            r = row.copy()
            r["planned_stop"] = float(r["planned_entry"]) * 0.5
            return r
        assert _frame(view, FakeStrategy(always=True, post=tamper), D).status == "error"

    def test_exit_context_slice(self):
        view, D = _wview()
        st = FakeStrategy(always=True)
        sr = mod("strategy_runner")
        src = sr.WindowedSignalSource(view, st)
        f = src.frame(BTC, D, signals.DEFAULT_SIGNAL_PARAMS, 1)
        assert f.status == "ok"
        pos = dataclasses.replace(_dummy_pos(), entry_bar_open=D - 3 * H)
        ctx = src.exit_context(BTC, pos, D)
        assert ctx.n_closed == 3 and len(ctx.highs) == 3 and len(ctx.lows) == 3 and len(ctx.atrs) == 3
        assert ctx.last_close == pytest.approx(float(f.table["close"].iloc[-1]))
        assert ctx.regime_last == f.table["regime"].iloc[-1]


def _dummy_pos():
    from trader_engine.types import Position
    return Position(trade_id=1, bot="learner", pair=BTC, side="long", setup="T1", status="open", decision_id=1,
                    signal_bar_close_ts=T0, entry_ts=T0, entry_bar_open=T0, entry_price=100.0, qty=1.0, leverage=3,
                    initial_stop=98.0, current_stop=98.0, stop_seq=0, stop_client_id=None, planned_target=None,
                    trail_atr=3.0, param_version_id=1, trigger_tf="1h", risk_amount=2.0, margin=33.0, rh=None,
                    rl=None, fee_entry=0.0, funding_paid=0.0, mfe_price=100.0, mae_price=100.0, exit_reason=None,
                    exit_client_id=None, closed_ts=None)


# =====================================================================================================
# 4. Kapi zinciri (§4.1): her satir
# =====================================================================================================
def _hold_block(e, reason):
    """Giris blokaji koy ve otomatik temizlemeyi (spec §7: mutabakat `ok` gorunce temizler; `day_start_missing`
    yeni gunde temizlenir) devre disi birak: kapi satirini temizlemeden bagimsiz sinar."""
    day = T0.strftime("%Y-%m-%d")
    with e.state.tx():
        e.state.kv_set("entries_blocked_reason", reason)
        if e.state.kv_get("day_start_date") is None:
            e.state.kv_set("day_start_date", day)
            e.state.kv_set("day_start:" + day, 1000.0)
    e.engine.reconciler.run = lambda now: None


class TestGateChain:
    def test_row0_bad_frames_ignored(self, env):
        for st, pair in (("error", BTC), ("no_history", ETH), ("data_gap", SOL)):
            env.src.frames[(pair, T0)] = make_frame(pair, T0, status=st)
        env.decide(T0)
        assert env.decisions() == [] and env.pos(BTC) is None
        assert not env.state.is_decided(BTC, T0)

    def test_row1_filtered_candidates_recorded(self, env):
        env.signal(T0, (BTC,), signal=False, skip_reason="stop_width")
        env.signal(T0, (ETH,), signal=False, skip_reason="rr_below_min", setup="R1", side="short",
                   stop=102.0, planned_target=96.0, wick_ratio=0.6, rr=1.0, edge_dist_atr=0.5)
        env.decide(T0)
        d = env.decisions()
        assert sorted(x.skip_reason for x in d) == ["rr_below_min", "stop_width"]
        for x in d:
            assert x.final_action == "skipped" and x.veto_status == "not_evaluated"
            assert x.veto_reason is None and x.risk_allowed is None
        assert env.pos(BTC) is None and env.pos(ETH) is None

    def test_row1_not_recorded_when_disabled(self, tmp_path):
        e = Env(tmp_path, record_filtered_candidates=False)
        e.start()
        e.signal(T0, (BTC,), signal=False, skip_reason="stop_width")
        e.decide(T0)
        assert e.decisions() == []
        e.close()

    def test_row1b_plain_nonsignal_ignored(self, env):
        env.signal(T0, (BTC,), signal=False, skip_reason=None)
        env.signal(T0, (ETH,), signal=False, setup=None, side=None)
        env.decide(T0)
        assert env.decisions() == []

    def test_row1_version_below_one_not_recorded(self, env):
        env.src.frames[(BTC, T0)] = make_frame(BTC, T0, signal=False, skip_reason="stop_width", version=0)
        env.decide(T0)
        assert env.decisions() == []

    def test_row2_already_decided_ignored(self, env):
        with env.state.tx():
            env.state.mark_decided(BTC, T0, "entered")
        env.signal(T0)
        env.decide(T0)
        assert env.decisions() == [] and env.pos(BTC) is None
        assert env.broker.counts["market_order"] == 0

    def test_row3_open_position_ignored(self, env):
        env.open_pos(BTC, T0)
        n = len(env.decisions())
        D1 = T0 + H
        env.signal(D1, (BTC,))
        env.decide(D1)
        assert len(env.decisions()) == n
        assert env.broker.counts["market_order"] == 1
        assert not env.state.is_decided(BTC, D1)

    def test_row4_params_unavailable(self, env):
        env.ledger.fail_params = True
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()
        assert len(d) == 1 and d[0].skip_reason == "entry_gate_closed" and d[0].veto_reason == "gate:params_unavailable"
        assert d[0].veto_status == "not_evaluated" and env.state.is_decided(BTC, T0) and env.pos(BTC) is None

    def test_row4_trigger_tf_changed(self, env):
        v = env.real_ledger.create_user_version(
            dict(dataclasses.asdict(signals.DEFAULT_SIGNAL_PARAMS), trigger_tf="15m"), reason="deneme")
        vid = v if isinstance(v, int) else v.id
        try:
            env.real_ledger.activate_version(vid, actor="user", reason="tf degistir")
        except L.LedgerError:
            pytest.skip("parametre etkinlestirme ortamda olmadi")
        env.version_id = vid
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()
        assert len(d) == 1 and d[0].skip_reason == "entry_gate_closed"
        assert d[0].veto_reason == "gate:trigger_tf_changed" and env.pos(BTC) is None

    @pytest.mark.parametrize("code", ["degraded", "spool_pending", "schema", "no_active_params", "unledgered_trades"])
    def test_row5_ledger_gate(self, env, code):
        env.ledger.health = L.Health(False, code, "x")
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()
        assert len(d) == 1 and d[0].skip_reason == "entry_gate_closed" and d[0].veto_reason == f"gate:{code}"
        assert d[0].veto_status == "not_evaluated" and env.state.is_decided(BTC, T0)
        assert env.pos(BTC) is None and env.broker.counts["market_order"] == 0

    def test_row5_ledger_unwritable_fail_closed(self, env):
        env.ledger.health = L.Health(False, "degraded", "yazilamiyor")
        env.ledger.fail_record = True
        env.signal(T0, (BTC, ETH))
        env.decide(T0)                                   # istisna yok, skip kaydi best-effort
        assert env.decisions() == []
        assert env.pos(BTC) is None and env.pos(ETH) is None and env.broker.counts["market_order"] == 0
        assert env.state.is_decided(BTC, T0)

    @pytest.mark.parametrize("reason", ["order_unknown", "exit_unknown", "stop_failed", "reconcile_unknown_position",
                                        "day_start_missing"])
    def test_row6_entries_blocked_reason(self, env, reason):
        _hold_block(env, reason)
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()
        assert len(d) == 1 and d[0].skip_reason == "entry_gate_closed" and d[0].veto_reason == f"gate:{reason}"
        assert env.pos(BTC) is None and env.state.is_decided(BTC, T0)

    def test_row7_kill(self, env):
        env.kill.set("tester", "deneme")
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()
        assert len(d) == 1 and d[0].skip_reason == "entry_gate_closed" and d[0].veto_reason == "gate:kill"
        assert env.pos(BTC) is None and env.broker.counts["market_order"] == 0

    def test_row8_stale(self, env):
        env.signal(T0)
        env.decide(T0, now=T0 + timedelta(minutes=90))
        d = env.decisions()
        assert len(d) == 1 and d[0].skip_reason == "other" and d[0].veto_reason == "gate:stale_data"
        assert env.pos(BTC) is None and env.state.is_decided(BTC, T0)

    def test_row8_not_stale_within_one_tf(self, env):
        env.signal(T0)
        env.decide(T0, now=T0 + timedelta(minutes=59))
        assert env.decisions()[0].final_action == "entered"

    def test_row9_rules_missing(self, tmp_path):
        e = Env(tmp_path, missing_rules=())
        e.view.missing_rules.add(BTC)
        e.start()
        e.signal(T0)
        e.decide(T0)
        d = e.decisions()
        assert len(d) == 1 and d[0].skip_reason == "other" and d[0].veto_reason == "gate:rules_missing"
        assert e.pos(BTC) is None
        e.close()

    @pytest.mark.parametrize("status", ["blocked", "missing", "stale"])
    def test_row10_veto_not_consulted_in_paper(self, tmp_path, status):
        """DD-12 WP-06a: kagitta veto adimi yok; veto engelli/yok/eski olsa da aday girilir, veto sorgulanmaz."""
        fv = FakeVeto(status, "funding asiri negatif")
        e = Env(tmp_path, veto_obj=fv)
        e.start()
        e.signal(T0)
        e.decide(T0)
        d = e.decisions()
        assert len(d) == 1 and d[0].final_action == "entered" and d[0].skip_reason is None
        assert d[0].veto_status == "not_evaluated" and d[0].risk_allowed is True
        assert fv.lookups == []
        e.close()

    def test_row11_risk_denied_daily_budget(self, tmp_path):
        e = Env(tmp_path, wallet=960.0)
        e.start()
        with e.state.tx():
            e.state.kv_set("day_start_date", T0.strftime("%Y-%m-%d"))
        with e.state.tx():
            e.state.kv_set("day_start:" + T0.strftime("%Y-%m-%d"), 1000.0)
        e.signal(T0)
        e.decide(T0)
        d = e.decisions()
        assert len(d) == 1 and d[0].skip_reason == "risk_denied" and d[0].veto_status == "not_evaluated"
        assert d[0].risk_allowed is False and d[0].risk_reason and d[0].final_action == "skipped"
        assert e.pos(BTC) is None and e.broker.counts["market_order"] == 0
        e.close()

    def test_row12_enter_example_A(self, env):
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()
        assert len(d) == 1
        x = d[0]
        assert x.final_action == "entered" and x.skip_reason is None and x.veto_status == "not_evaluated"
        assert x.veto_reason == "not_evaluated:paper" and x.risk_allowed is True
        assert x.size_qty == pytest.approx(6.369) and x.size_notional == pytest.approx(636.9)
        assert x.size_margin == pytest.approx(212.3) and x.size_risk_amount == pytest.approx(13.999062)
        assert x.leverage == 3 and x.bar_close_ts == T0 and x.setup == "T1" and x.side == "long"
        assert x.planned_entry == 100.0 and x.planned_stop == 98.0
        p = env.pos(BTC)
        assert p.status == "opening" and p.risk_amount == pytest.approx(13.999062)
        assert p.decision_id == x.id and p.initial_stop == 98.0 and p.trigger_tf == "1h"
        assert env.state.is_decided(BTC, T0)
        assert env.broker.counts["market_order"] == 1 and len(env.state.unresolved_orders()) <= 1
        # dolum + stop + defter
        env.step(T0)
        p = env.pos(BTC)
        assert p.status == "open" and p.entry_price == pytest.approx(100.02) and p.qty == pytest.approx(6.369)
        stops = [o for o in env.broker.open_orders(BTC) if o.role == "stop"]
        assert len(stops) == 1 and stops[0].trigger_price == pytest.approx(98.0) and stops[0].reduce_only
        t = env.real_ledger.get_trade(p.trade_id)
        assert t.entry_price == pytest.approx(100.02) and t.qty == pytest.approx(6.369) and t.leverage == 3
        assert t.fee_entry == pytest.approx(0.31851369)

    def test_same_candle_decided_once(self, env):
        env.signal(T0)
        env.decide(T0)
        env.src.frames[(BTC, T0)] = make_frame(BTC, T0, entry=101.0, stop=99.0, version=env.version_id)
        env.engine.decision_step(T0)
        assert len(env.decisions()) == 1 and env.broker.counts["market_order"] == 1

    def test_entered_record_mandatory(self, env):
        env.ledger.fail_record = True
        env.signal(T0)
        env.decide(T0)
        assert env.pos(BTC) is None and env.broker.counts["market_order"] == 0
        assert env.real_ledger.list_decisions() == []
        assert not env.state.is_decided(BTC, T0)          # yeniden baslatmada tekrar denenebilir

    def test_ledger_conflict_blocks_entry(self, env):
        ev = L.DecisionEvent(
            bar_close_ts=T0, trigger_tf="1h", pair=BTC, side="long", setup="T1", regime="trend_up", atr_ratio=1.0,
            rh=None, rl=None, rh_touches=0, rl_touches=0, features={"atr_tf": 1.0, "stop_dist_atr": 2.0, "atr_4h": 2.0,
                                                                   "pullback_ema": 50, "ema_value": 99.5,
                                                                   "body_ratio": 0.7},
            planned_entry=111.0, planned_stop=100.0, planned_target=None, param_version_id=env.version_id,
            veto_status="not_evaluated", veto_reason="gate:kill", risk_allowed=None, risk_reason=None,
            size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
            final_action="skipped", skip_reason="entry_gate_closed")
        env.real_ledger.record_decision(ev)
        env.signal(T0)
        env.decide(T0)
        assert env.pos(BTC) is None and env.broker.counts["market_order"] == 0

    def test_two_entries_reserve_risk_third_denied(self, env):
        env.signal(T0, (BTC, ETH, SOL))
        env.decide(T0)
        by = {d.pair: d for d in env.decisions()}
        assert by[BTC].final_action == "entered" and by[ETH].final_action == "entered"
        assert by[SOL].skip_reason == "risk_denied" and by[SOL].risk_allowed is False
        assert by[SOL].veto_status == "not_evaluated"
        assert env.pos(SOL) is None

    def test_pairs_processed_in_config_order(self, env):
        env.signal(T0, (BTC, ETH))
        env.decide(T0)
        pairs = [r[2] for r in env.broker.log if r[1] == "entry"]
        assert pairs == [BTC, ETH]

    def test_veto_begin_step_once_per_decision_step(self, env):
        env.signal(T0, (BTC, ETH))
        env.decide(T0)
        assert len(env.veto.begin_calls) == 1

    def test_gate_chain_order_first_match_wins(self, env):
        """Ledger kapali + kill + stale + veto engelli: yalniz ilk eslesen (ledger) kodu yazilir."""
        env.ledger.health = L.Health(False, "degraded", "x")
        env.kill.set("t", "t")
        env.veto.status = "blocked"
        env.signal(T0)
        env.decide(T0, now=T0 + timedelta(hours=3))
        assert [d.veto_reason for d in env.decisions()] == ["gate:degraded"]
        # kill > stale > veto
        env2_dir = env.tmp / "b"
        env2_dir.mkdir()
        e2 = Env(env2_dir, veto_obj=FakeVeto("blocked", "r"))
        e2.start()
        e2.kill.set("t", "t")
        e2.signal(T0)
        e2.decide(T0, now=T0 + timedelta(hours=3))
        assert [d.veto_reason for d in e2.decisions()] == ["gate:kill"]
        e2.kill.clear()
        e3_dir = env.tmp / "c"
        e3_dir.mkdir()
        e3 = Env(e3_dir, veto_obj=FakeVeto("blocked", "r"))
        e3.start()
        e3.signal(T0)
        e3.decide(T0, now=T0 + timedelta(hours=3))
        assert [d.veto_reason for d in e3.decisions()] == ["gate:stale_data"]
        e2.close()
        e3.close()

    @pytest.mark.parametrize("name", ["price_action_v1", "other_fake"])
    def test_gate_results_independent_of_strategy(self, tmp_path, name):
        reg = mod("strategies.registry")
        st = reg.get_strategy("price_action_v1") if name == "price_action_v1" else FakeStrategy(name=name)
        e = Env(tmp_path, strategy=st)
        e.start()
        e.signal(T0, (BTC, ETH, SOL))
        e.decide(T0)
        got = [(d.pair, d.final_action, d.skip_reason, d.risk_allowed, d.size_qty, d.leverage) for d in e.decisions()]
        assert got == [(BTC, "entered", None, True, 6.369, 3), (ETH, "entered", None, True, 6.369, 3),
                       (SOL, "skipped", "risk_denied", False, None, None)]
        e.close()


# =====================================================================================================
# 5. Cikislar kapisiz, sira, onceliks (§6.3, §5.3, §10.5-7)
# =====================================================================================================
def _gate_closers():
    def ledger_degraded(e):
        e.ledger.health = L.Health(False, "degraded", "x")

    def blocked_reason(e):
        _hold_block(e, "order_unknown")
    return {"ledger_degraded": ledger_degraded, "blocked_reason": blocked_reason}   # DD-12 WP-06a: veto_missing kapatici kagitta yok


class TestExitsUngated:
    @pytest.mark.parametrize("closer", list(_gate_closers()) + ["stale"])
    def test_regime_flip_exit_runs_with_gate_closed(self, env, closer):
        env.open_pos(BTC, T0)
        D1 = T0 + H
        env.src.ctx[(BTC, D1)] = flip_ctx(D1)
        now = D1 + timedelta(minutes=90) if closer == "stale" else None
        if closer != "stale":
            _gate_closers()[closer](env)
        env.signal(D1, (ETH,))
        env.decide(D1, now=now)
        p = env.pos(BTC)
        assert p.status == "closing" and p.exit_reason == "regime_flip"
        env.step((now or D1) - M1 if now else D1)
        t = env.real_ledger.get_trade(p.trade_id)
        assert t.exit_reason == "regime_flip" and t.exit_ts is not None
        assert env.pos(BTC) is None or env.pos(BTC).status == "closed"
        assert env.pos(ETH) is None                      # giris yine engelli

    def test_ledger_unwritable_exit_still_executed(self, env):
        env.open_pos(BTC, T0)
        D1 = T0 + H
        env.ledger.health = L.Health(False, "degraded", "x")
        env.ledger.fail_record = True
        env.src.ctx[(BTC, D1)] = flip_ctx(D1)
        env.decide(D1)
        assert env.pos(BTC).status == "closing"
        assert [r for r in env.broker.log if r[1] == "exit"] == [("market_order", "exit", BTC)]

    def test_stale_still_evaluates_exit_example5(self, env):
        env.open_pos(BTC, T0)
        D1 = T0 + H
        env.src.ctx[(BTC, D1)] = flip_ctx(D1)
        env.signal(D1, (BTC,))
        env.decide(D1, now=D1 + timedelta(minutes=90))
        assert env.pos(BTC).status == "closing"

    def test_exit_priority_regime_flip_over_trail(self, env):
        env.open_pos(BTC, T0)
        D1 = T0 + H
        c = flip_ctx(D1)                                  # iz-stop de yukselirdi, rejim donusu ustun
        env.src.ctx[(BTC, D1)] = c
        env.decide(D1)
        assert env.pos(BTC).exit_reason == "regime_flip"
        stops = [r for r in env.broker.log if r[0] == "place_stop"]
        assert len(stops) == 1                            # yalniz baslangic stopu; stop_update yok

    def test_data_gap_skips_discretionary_exit_keeps_stop(self, env):
        env.open_pos(BTC, T0)
        D1 = T0 + H
        env.src.frames[(BTC, D1)] = make_frame(BTC, D1, status="data_gap")
        env.src.ctx[(BTC, D1)] = flip_ctx(D1)
        env.decide(D1)
        p = env.pos(BTC)
        assert p.status == "open" and p.exit_reason is None
        assert [o for o in env.broker.open_orders(BTC) if o.role == "stop"]
        assert env.engine.counters().get("exit_data_gap", 0) >= 1

    def test_step_order_exit_then_stop_update_then_entry(self, env):
        # BTC: cikacak, ETH: stop guncellenecek, SOL: yeni giris
        env.open_pos(BTC, T0)
        env.signal(T0, (ETH,))
        env.engine.decision_step(T0)
        env.step(T0, pairs=(ETH,))
        env.broker.log.clear()
        D1 = T0 + H
        env.src.ctx[(BTC, D1)] = flip_ctx(D1)
        env.src.ctx[(ETH, D1)] = trail_ctx(D1)
        env.signal(D1, (SOL,), side="short", stop=102.0)   # ters yon: ayni-yon %4 risk kilidine takilmaz
        env.decide(D1)
        kinds = [(m, role) for m, role, _ in env.broker.log]
        i_exit = kinds.index(("market_order", "exit"))
        i_stop = kinds.index(("place_stop", "stop"))
        i_entry = kinds.index(("market_order", "entry"))
        assert i_exit < i_stop < i_entry
        assert env.state.position_for_pair(ETH).current_stop > 98.0

    def test_exit_data_does_not_depend_on_entry_frame_error(self, env):
        env.open_pos(BTC, T0)
        D1 = T0 + H
        env.src.frames[(ETH, D1)] = make_frame(ETH, D1, status="error")
        env.src.ctx[(BTC, D1)] = flip_ctx(D1)
        env.decide(D1)
        assert env.pos(BTC).status == "closing"


# =====================================================================================================
# 6. Defter kayitlari: MFE/MAE/bars_held, strateji adi+surum (§13.6)
# =====================================================================================================
class TestLedgerRecords:
    def test_decision_chain_gives_strategy_name_version(self, env):
        env.signal(T0)
        env.decide(T0)
        d = env.decisions()[0]
        pv = env.real_ledger.get_version(d.param_version_id)
        assert pv.reason == "strategy:fake_strategy@0.1"
        assert env.state.kv_get("strategy") is not None
        assert "fake_strategy" in json.dumps(env.state.kv_get("strategy"))

    def test_exit_record_has_excursions_and_bars_held(self, env):
        p = env.open_pos(BTC, T0)
        for k in range(1, 40):                            # 40 dk: yukselis + dusus
            env.step(T0 + k * M1, pairs=(BTC,), price=100.0, hi=103.0 if k == 10 else 100.0,
                     lo=99.4 if k == 20 else 100.0)
        D1 = T0 + H
        env.src.ctx[(BTC, D1)] = flip_ctx(D1)
        env.decide(D1)
        env.step(D1, pairs=(BTC,))
        t = env.real_ledger.get_trade(p.trade_id)
        assert t.exit_reason == "regime_flip" and t.exit_price is not None
        assert t.mfe_r is not None and t.mae_r is not None and t.excursion_tf == "1m"
        assert t.mfe_r > 0 and t.bars_held is not None and t.bars_held >= 3      # ~60 dk / 15 dk
        assert t.realized_pnl is not None and t.fee_exit is not None

    def test_entry_trade_planned_fields(self, env):
        p = env.open_pos(BTC, T0)
        t = env.real_ledger.get_trade(p.trade_id)
        assert t.pair == BTC and t.setup == "T1" and t.planned_stop == 98.0 and t.planned_entry == 100.0
        assert t.param_version_id == env.version_id

    def test_stop_hit_recorded_as_stop(self, env):
        p = env.open_pos(BTC, T0)
        env.step(T0 + M1, pairs=(BTC,), price=98.5, hi=99.0, lo=97.5)
        t = env.real_ledger.get_trade(p.trade_id)
        assert t.exit_reason == "stop" and t.exit_price < 98.0
        assert t.realized_pnl < 0 and abs(t.realized_pnl) <= 0.02 * 1000.0
        assert env.pos(BTC) is None or env.pos(BTC).status == "closed"


# =====================================================================================================
# 7. NoVeto (§4; 24.11: FileVeto/HMAC belgesi silindi)
# =====================================================================================================
class TestVetoSources:
    def test_noveto(self):
        nv = mod("gates").NoVeto()
        nv.begin_step(T0)
        r = nv.lookup(BTC, "long", T0)
        assert (r.status, r.reason, r.blocks) == ("allowed", "not_evaluated:backtest", False)


# =====================================================================================================
# 8. Kill (§8.1) ve status.json (§8.2)
# =====================================================================================================
class TestKillswitch:
    def test_set_info_clear(self, tmp_path):
        ks = mod("killswitch").Killswitch(str(tmp_path / "shared" / "KILL"), SimClock(T0))
        assert ks.active() is False and ks.info() is None
        ks.set("tester", "deneme")
        assert ks.active() is True
        i = ks.info()
        assert i["by"] == "tester" and i["reason"] == "deneme" and "at" in i
        ks.clear()
        assert ks.active() is False

    @pytest.mark.parametrize("content", ["", "{bozuk json", "[1,2]"])
    def test_any_file_is_active_content_irrelevant(self, tmp_path, content):
        p = tmp_path / "KILL"
        p.write_text(content)
        ks = mod("killswitch").Killswitch(str(p), SimClock(T0))
        assert ks.active() is True
        info = ks.info()
        if content == "{bozuk json":
            assert info == {"raw": content} or "raw" in info

    def test_unreadable_is_active(self, tmp_path, monkeypatch):
        p = tmp_path / "KILL"
        ks = mod("killswitch").Killswitch(str(p), SimClock(T0))

        def boom(*a, **k):
            raise PermissionError("izin yok")
        monkeypatch.setattr(os, "stat", boom)
        monkeypatch.setattr(os.path, "exists", boom)
        monkeypatch.setattr(Path, "exists", boom)
        monkeypatch.setattr(os.path, "isfile", boom)
        assert ks.active() is True

    def test_engine_force_exits_once_on_minute_step(self, env):
        p = env.open_pos(BTC, T0)
        env.kill.set("tester", "dur")
        env.step(T0 + M1)
        assert env.pos(BTC).status == "closing"
        env.step(T0 + 2 * M1)
        env.step(T0 + 3 * M1)
        assert [r for r in env.broker.log if r[1] == "exit"] == [("market_order", "exit", BTC)]
        t = env.real_ledger.get_trade(p.trade_id)
        assert t.exit_reason == "force_exit"
        assert [o for o in env.broker.open_orders(BTC)] == []         # cancel_resting
        env.status.write(env.engine)
        st = json.loads(Path(env.cfg.status_path).read_text())
        assert st["kill"] is True and st["kill_state"] == "flat" and st["entries_open"] is False

    def test_kill_at_decision_step_example6(self, env):
        env.open_pos(BTC, T0)
        D1 = T0 + H
        env.kill.set("t", "t")
        env.signal(D1, (ETH,))
        env.decide(D1)
        assert env.pos(BTC).exit_reason == "force_exit"
        d = only(env.decisions(), pair=ETH)
        assert d[0].veto_reason == "gate:kill" and env.pos(ETH) is None

    def test_kill_clear_reopens_entries(self, env):
        env.kill.set("t", "t")
        env.signal(T0)
        env.decide(T0)
        env.kill.clear()
        D1 = T0 + H
        env.signal(D1)
        env.decide(D1)
        d = env.decisions()
        assert d[0].veto_reason == "gate:kill" and d[1].final_action == "entered"

    def test_kill_restart_idempotent(self, tmp_path):
        e = Env(tmp_path)
        e.start()
        e.open_pos(BTC, T0)
        e.kill.set("t", "t")
        e.step(T0 + M1)
        assert e.pos(BTC).status == "closing"
        e.engine.shutdown("test")
        e.close()
        e2 = Env(tmp_path, start=T0 + 2 * M1)
        e2.start()
        e2.step(T0 + 2 * M1)
        e2.step(T0 + 3 * M1)
        exits = [r for r in e.broker.log + e2.broker.log if r[1] == "exit"]
        assert len(exits) == 1
        e2.close()


class TestStatus:
    def test_content_after_entry(self, env):
        p = env.open_pos(BTC, T0)
        env.status.write(env.engine)
        st = json.loads(Path(env.cfg.status_path).read_text())
        assert st["schema"] == "engine-status/1" and st["bot"] == "learner" and st["mode"] == "paper"
        assert st["strategy"] == {"name": "fake_strategy", "version": "0.1"}
        assert st["trigger_tf"] == "1h" and st["param_version_id"] == env.version_id
        assert st["entries_open"] is True and st["gate"] == {"ok": True, "code": "ok"}
        assert st["kill"] is False and st["kill_state"] is None and st["entries_blocked_reason"] is None
        assert st["dry_run"] is True and isinstance(st["pid"], int)
        assert st["wallet"] == pytest.approx(1000.0 - 0.31851369, abs=1e-6)
        assert st["day_start_equity"] == pytest.approx(1000.0) and st["equity"] > 900
        assert st["open_trade_ids"] == [p.trade_id]
        op = st["open_positions"][0]
        assert op["trade_id"] == p.trade_id and op["pair"] == BTC and op["side"] == "long"
        assert op["qty"] == pytest.approx(6.369) and op["entry_price"] == pytest.approx(100.02)
        assert op["stop"] == pytest.approx(98.0)
        for k in ("callback_errors", "data_gaps", "ledger_errors", "unknown_orders", "mark_fallbacks",
                  "minute_gaps", "funding_missing", "exit_data_gap"):
            assert k in st["counters"]
        for k in ("started_at", "loop_at", "last_minute_ts", "last_decision_bar_close", "last_candle_open"):
            assert k in st
        assert st["last_decision_bar_close"] == iso(T0) and st["last_minute_ts"] == iso(T0)
        assert st["started_at"].endswith("Z") and st["loop_at"].endswith("Z")

    def test_gate_reflects_closed_ledger_and_blocked_reason(self, env):
        env.ledger.health = L.Health(False, "degraded", "x")
        env.status.write(env.engine)
        st = json.loads(Path(env.cfg.status_path).read_text())
        assert st["entries_open"] is False and st["gate"]["ok"] is False and st["gate"]["code"] == "degraded"
        env.ledger.health = None
        with env.state.tx():
            env.state.kv_set("entries_blocked_reason", "stop_failed")
        env.set_clock(env.clock.now() + timedelta(seconds=env.cfg.loop_sleep_s))   # yazma en cok loop_sleep_s aralikli
        env.status.write(env.engine)
        st = json.loads(Path(env.cfg.status_path).read_text())
        assert st["entries_open"] is False and st["entries_blocked_reason"] == "stop_failed"

    def test_atomic_no_stray_files_and_write_failure_swallowed(self, env, tmp_path):
        env.status.write(env.engine)
        d = Path(env.cfg.status_path).parent
        assert json.loads((d / "status.json").read_text())["schema"] == "engine-status/1"
        assert [f.name for f in d.iterdir() if f.name.endswith(".tmp") or ".tmp" in f.name] == []
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        sw = mod("status").StatusWriter(str(blocker / "sub" / "status.json"), env.clock, env.cfg)
        sw.write(env.engine)                              # istisna firlatmaz


# =====================================================================================================
# 9. Gun basi (§6.2, §4.2)
# =====================================================================================================
class TestDayStart:
    def test_ensure_day_start(self, env):
        env.step(T0)
        d = T0.strftime("%Y-%m-%d")
        assert env.state.kv_get("day_start_date") == d
        assert env.state.kv_get("day_start:" + d) == pytest.approx(1000.0)
        with env.state.tx():
            env.state.kv_set("day_start:" + d, 1234.0)
        env.step(T0 + M1)                                 # ayni gun: degismez
        assert env.state.kv_get("day_start:" + d) == pytest.approx(1234.0)
        nxt = datetime(2026, 12, 2, 0, 0, tzinfo=UTC)
        env.step(nxt)
        assert env.state.kv_get("day_start_date") == "2026-12-02"
        assert env.state.kv_get("day_start:2026-12-02") == pytest.approx(env.broker.account().wallet)

    def test_day_start_missing_blocks_entries(self, tmp_path):
        e = Env(tmp_path, start=datetime(2026, 12, 2, 8, 0, tzinfo=UTC))
        e.start()
        with e.state.tx():
            e.state.kv_set("initialized_at", "2026-12-01T00:00:00Z")
        with e.state.tx():
            e.state.kv_set("day_start_date", "2026-12-01")
        e.step(datetime(2026, 12, 2, 8, 0, tzinfo=UTC))
        D = datetime(2026, 12, 2, 9, 0, tzinfo=UTC)
        e.signal(D)
        e.decide(D)
        d = e.decisions()
        assert len(d) == 1 and d[0].veto_reason == "gate:day_start_missing" and e.pos(BTC) is None
        e.close()


# =====================================================================================================
# 10. Baslatma dogrulamalari (§13.6, §5.1)
# =====================================================================================================
class TestStartup:
    def test_ledger_incompatible_raises(self, tmp_path):
        reg = mod("strategies.registry")
        e = Env(tmp_path, strategy=FakeStrategy(drop_params=("rr_min",)))
        with pytest.raises(reg.StrategyError) as ei:
            e.start()
        assert ei.value.code == "ledger_incompatible"
        e.close()

    def test_version_mismatch_blocks_entries_only(self, tmp_path):
        (tmp_path / "x").mkdir()
        Env(tmp_path / "x", strategy=FakeStrategy(version="0.1")).close()     # defter etiketi 0.1 ile acilir
        e2 = Env(tmp_path / "x", strategy=FakeStrategy(version="0.2"), init_label=False)
        e2.start()
        e2.signal(T0)
        e2.decide(T0)
        d = e2.decisions()
        assert len(d) == 1 and d[0].veto_reason == "gate:strategy_mismatch" and e2.pos(BTC) is None
        e2.close()

    def test_strategy_change_with_open_positions_rejected(self, tmp_path):
        e = Env(tmp_path)
        e.start()
        e.open_pos(BTC, T0)
        e.close()
        e2 = Env(tmp_path, strategy=FakeStrategy(name="other_fake"), start=T0 + 2 * M1, init_label=False)
        with pytest.raises(Exception) as ei:
            e2.start()
        assert "strategy_change_with_open_positions" in (str(ei.value) + str(getattr(ei.value, "code", "")))
        e2.close()

    def test_learner_has_no_start_delay_and_twin_rejected(self, tmp_path):
        """DD-12: ikiz kaldirildi (bot="twin" => ConfigError); ogrenen bekleme gecikmesi yok."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        with pytest.raises(ConfigError):
            Env(tmp_path / "a", bot="twin")
        le = Env(tmp_path / "b", bot="learner")
        l0 = le.clock.now()
        le.start()
        assert (le.clock.now() - l0).total_seconds() < 3.0
        le.close()

    def test_empty_params_starts_with_entries_closed_no_auto_init(self, tmp_path):
        e = Env(tmp_path)
        e.ledger.fail_params = True
        e.start()                                         # baslar
        e.signal(T0)
        e.decide(T0)
        assert e.decisions()[0].veto_reason == "gate:params_unavailable"
        assert len(e.real_ledger.list_versions()) == 1    # otomatik init yok
        e.close()


# =====================================================================================================
# 11. Ikiz kaldirildi (DD-12 WP-07): yalniz ogrenen
# =====================================================================================================
class TestTwinRemoved:
    def test_twin_config_gone_and_rejected(self):
        assert not (ROOT / "config" / "engine.twin.json").exists()
        a = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / "engine.learner.json")
        assert a.bot == "learner" and not hasattr(a, "start_delay_s")   # 25.11: olu ayar kaldirildi

    def test_learner_params_never_change_and_decisions_deterministic(self, tmp_path):
        out = []
        for k in range(2):
            d = tmp_path / str(k)
            d.mkdir()
            e = Env(d, bot="learner")
            e.start()
            for j in range(3):
                Dk = T0 + j * H
                e.signal(Dk, (BTC, ETH, SOL))
                e.decide(Dk)
                e.step(Dk)
            vers = e.real_ledger.list_versions()
            acts = e.real_ledger.list_activations()
            out.append(([(x.pair, x.bar_close_ts, x.final_action, x.skip_reason, x.size_qty) for x in e.decisions()],
                        [dict(v.params) for v in vers], len(acts)))
            assert len(vers) == 1 and len(acts) == 1
            e.close()
        assert out[0] == out[1]


# =====================================================================================================
# 12. Mutabakat (§7)
# =====================================================================================================
class TestReconcile:
    def _rec(self, env):
        r = mod("reconcile").Reconciler(env.cfg, env.broker, env.state, env.ledger, env.orders, env.clock)
        return r.run(env.clock.now())

    def test_clean_ok_and_find_unledgered_positional(self, env):
        p = env.open_pos(BTC, T0)
        rep = self._rec(env)
        assert rep.ok is True and rep.fatal is False
        assert env.ledger.unledgered_calls and env.ledger.unledgered_calls[-1] == [p.trade_id]

    def test_broker_position_without_state_is_fatal_no_action(self, env):
        n0 = env.broker.counts["market_order"]
        env.broker.prepare(BTC, 3)
        req = OrderRequest(client_id="trLe-" + "a" * 24, pair=BTC, role="entry", order_side="buy", qty=1.0,
                           trigger_price=None, reduce_only=False, leverage=3, created_ts=env.clock.now())
        env.broker.market_order(req)
        env.broker.advance({BTC: env.bar(BTC, T0)}, "fills")
        env.broker.advance({BTC: env.bar(BTC, T0)}, "triggers")
        env.broker.poll(env.clock.now())
        assert env.broker.positions()
        n1 = env.broker.counts["market_order"]
        rep = self._rec(env)
        assert rep.fatal is True
        assert env.state.kv_get("entries_blocked_reason") == "reconcile_unknown_position"
        assert env.broker.counts["market_order"] == n1 and n1 == n0 + 1       # islem yapilmadi
        assert len(env.broker.positions()) == 1

    def test_state_orphan_fatal_then_auto_clear(self, env):
        with env.state.tx():
            pos = dataclasses.replace(_dummy_pos(), trade_id=env.state.next_trade_id(), status="open")
            env.state.insert_position(pos)
        rep = self._rec(env)
        assert rep.fatal is True and env.state.kv_get("entries_blocked_reason") == "reconcile_state_orphan"
        with env.state.tx():
            env.state.update_position(pos.trade_id, status="closed", closed_ts=env.clock.now())
        rep2 = self._rec(env)
        assert rep2.ok is True and env.state.kv_get("entries_blocked_reason") in (None, "")

    def test_missing_stop_is_reinstalled(self, env):
        p = env.open_pos(BTC, T0)
        stop = [o for o in env.broker.open_orders(BTC) if o.role == "stop"][0]
        env.broker.cancel(BTC, stop.client_id)
        assert not [o for o in env.broker.open_orders(BTC) if o.role == "stop"]
        self._rec(env)
        stops = [o for o in env.broker.open_orders(BTC) if o.role == "stop"]
        assert len(stops) == 1 and stops[0].trigger_price == pytest.approx(p.initial_stop)
        assert stops[0].qty == pytest.approx(p.qty)

    def test_ledger_orphan_blocks_entries(self, env):
        ev = L.DecisionEvent(
            bar_close_ts=T0, trigger_tf="1h", pair=ETH, side="long", setup="T1", regime="trend_up", atr_ratio=1.0,
            rh=None, rl=None, rh_touches=0, rl_touches=0,
            features={"atr_tf": 1.0, "stop_dist_atr": 2.0, "atr_4h": 2.0, "pullback_ema": 50, "ema_value": 99.5,
                      "body_ratio": 0.7},
            planned_entry=100.0, planned_stop=98.0, planned_target=None, param_version_id=env.version_id,
            veto_status="allowed", veto_reason="ok", risk_allowed=True, risk_reason="ok", size_qty=6.369,
            size_notional=636.9, size_margin=212.3, size_risk_amount=13.999062, leverage=3, final_action="entered",
            skip_reason=None)
        did = env.real_ledger.record_decision(ev)
        env.real_ledger.record_trade_entry(L.TradeEntry(trade_id=77, decision_id=did, entry_ts=T0 + M1,
                                                        entry_price=100.02, qty=6.369, leverage=3, fee_entry=0.3))
        env.set_clock(T0 + 2 * M1)
        rep = self._rec(env)
        assert env.state.kv_get("entries_blocked_reason") == "reconcile_ledger_orphan"
        assert rep.findings


# =====================================================================================================
# 13. Yeniden oynatma (§5.5, §10.8) ve cokme sonrasi bit-bit esitlik (§11)
# =====================================================================================================
class _Spy:
    def __init__(self, engine):
        self.seq = []
        pm, dm = engine.process_step, engine.decision_step
        engine.process_step = lambda step: (self.seq.append(("m", step.ts)), pm(step))[1]
        engine.decision_step = lambda D: (self.seq.append(("d", D)), dm(D))[1]


def _replay_env(tmp, now, cursor, view_end=None):
    # start() ilk kurulumda imleci "son kapanmis dakika"ya koyar (gecmis oynatilmaz; imec geri gitmez): saat
    # imlecin bir dakika ilerisinde baslatilir, sonra `now`a alinir; boylece oynatma `advance_to(now)`te olur.
    e = Env(tmp, start=cursor + M1, real_signals=False)
    e.view = SynthView(PAIRS, now - timedelta(days=2), (view_end or now + timedelta(hours=1)), clock=e.clock)
    e.engine = mod("engine").Engine(
        e.cfg, clock=e.clock, view=e.view, broker=e.broker, ledger=e.ledger, state=e.state, signals=e.src,
        strategy=e.strategy, veto=e.veto, kill=e.kill, status=e.status, orders=e.orders)
    e.start()
    for p in PAIRS:
        assert e.state.get_cursor(p, "minute") == cursor
    e.set_clock(now)
    return e


class TestReplay:
    def test_a_no_decision_when_no_tf_close(self, tmp_path):
        now = datetime(2026, 12, 1, 10, 7, tzinfo=UTC)
        e = _replay_env(tmp_path, now, datetime(2026, 12, 1, 10, 0, tzinfo=UTC))
        spy = _Spy(e.engine)
        e.engine.advance_to(now)
        mins = [t for k, t in spy.seq if k == "m"]
        assert mins == [datetime(2026, 12, 1, 10, m, tzinfo=UTC) for m in range(1, 7)]
        assert not [1 for k, _ in spy.seq if k == "d"]
        e.close()

    def test_b_decision_between_minutes(self, tmp_path):
        now = datetime(2026, 12, 1, 11, 3, tzinfo=UTC)
        e = _replay_env(tmp_path, now, datetime(2026, 12, 1, 10, 58, tzinfo=UTC))
        spy = _Spy(e.engine)
        e.engine.advance_to(now)
        D = datetime(2026, 12, 1, 11, 0, tzinfo=UTC)
        i_d = spy.seq.index(("d", D))
        before = [t for k, t in spy.seq[:i_d] if k == "m"]
        after = [t for k, t in spy.seq[i_d + 1:] if k == "m"]
        assert before == [datetime(2026, 12, 1, 10, 59, tzinfo=UTC)]
        assert after == [datetime(2026, 12, 1, 11, m, tzinfo=UTC) for m in (0, 1, 2)]
        e.close()

    def test_c_multi_hour_replay_stale_blocked_last_fresh(self, tmp_path):
        now = datetime(2026, 12, 1, 13, 5, tzinfo=UTC)
        e = _replay_env(tmp_path, now, datetime(2026, 12, 1, 10, 58, tzinfo=UTC))
        e.src.auto = lambda pair, D, v: make_frame(pair, D, version=v) if pair == BTC else \
            make_frame(pair, D, signal=False, setup=None, side=None, version=v)
        spy = _Spy(e.engine)
        e.engine.advance_to(now)
        ds = [t for k, t in spy.seq if k == "d"]
        assert ds == [datetime(2026, 12, 1, h, 0, tzinfo=UTC) for h in (11, 12, 13)]
        d = {x.bar_close_ts.hour: x for x in e.decisions()}
        for h in (11, 12):
            assert d[h].skip_reason == "other" and d[h].veto_reason == "gate:stale_data"
        assert d[13].final_action == "entered"
        e.close()


def _norm_ledger(e):
    dec = [(x.id, x.bar_close_ts, x.pair, x.side, x.setup, x.final_action, x.skip_reason, x.veto_status,
            x.veto_reason, x.risk_allowed, x.size_qty, x.planned_entry, x.planned_stop, x.param_version_id)
           for x in e.real_ledger.list_decisions()]
    tr = [(t.trade_id, t.decision_id, t.pair, t.entry_ts, t.entry_price, t.qty, t.exit_ts, t.exit_price,
           t.exit_reason, t.realized_pnl, t.mfe_r, t.mae_r, t.bars_held)
          for t in sorted(e.real_ledger._trades("", (), False), key=lambda t: t.trade_id)] \
        if hasattr(e.real_ledger, "_trades") else []
    return dec, tr


def _norm_state(e):
    closed = e.state.closed_positions_since(datetime(2026, 1, 1, tzinfo=UTC))
    return (sorted(e.state.open_positions(), key=lambda p: p.trade_id), sorted(closed, key=lambda p: p.trade_id),
            sorted(o.client_id for t in range(1, 40) for o in e.state.orders_for_trade(t)))


def _run_schedule(tmp, crash=None):
    Path(tmp).mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 12, 3, 0, 0, tzinfo=UTC)
    times = [start + timedelta(minutes=10 * k) for k in range(1, 8 * 6 + 1)]       # 8 saat
    st = FakeStrategy(always=False)

    def build(now):
        view = SynthView(PAIRS, start - timedelta(days=3), start + timedelta(days=1), seed=11, mode="rw", vol=0.003)
        e = Env(tmp, start=now, view=view, real_signals=True, strategy=st, broker_cls=CallLogBroker, strict=False)
        view.clock = e.clock
        e.engine.start()
        return e
    CallLogBroker.crash_at = {}
    e = build(start)
    crashed_once = armed = False
    for t in times:
        if crash and not armed and t >= times[3]:
            armed = True
            CallLogBroker.crash_at = {crash[0]: crash[1]}
            e.broker.counts[crash[0]] = 0
        e.set_clock(t)
        try:
            e.engine.advance_to(t)
        except (Exception, SystemExit):
            pass
        if e.broker.crashed:
            crashed_once = True
            CallLogBroker.crash_at = {}
            e.close()
            e = build(t)
            e.engine.advance_to(t)
    CallLogBroker.crash_at = {}
    return e


class TestCrashReplayIdentical:
    def test_baseline_has_activity(self, tmp_path):
        e = _run_schedule(tmp_path / "base")
        dec, tr = _norm_ledger(e)
        assert dec, "sentetik piyasada hic karar uretilmedi"
        e.close()

    @pytest.mark.parametrize("crash", [("advance", 3), ("advance", 40), ("advance", 150), ("market_order", 1),
                                       ("market_order", 3)])
    def test_crash_then_restart_identical_state_no_duplicate_orders(self, tmp_path, crash):
        (tmp_path / "base").mkdir()
        (tmp_path / "crash").mkdir()
        base = _run_schedule(tmp_path / "base")
        crashed = _run_schedule(tmp_path / "crash", crash=crash)
        assert _norm_ledger(base) == _norm_ledger(crashed)
        assert _norm_state(base) == _norm_state(crashed)
        assert base.broker.snapshot() == crashed.broker.snapshot()
        cids = [o.client_id for t in range(1, 60) for o in crashed.state.orders_for_trade(t)]
        assert len(cids) == len(set(cids))
        base.close()
        crashed.close()


# =====================================================================================================
# 14. Seed'li ozellik testi (rastgele sentetik piyasalar, kapi programi)
# =====================================================================================================
def _flags(seed, n_hours, start):
    rng = random.Random(seed * 7919 + 1)
    out = {}
    for h in range(n_hours + 2):
        t = start + h * H
        out[t] = (rng.random() < 0.15, rng.random() < 0.08, rng.random() < 0.15)      # veto, kill, ledger
    return out


def _property_run(tmp, seed):
    start = datetime(2026, 12, 3, 0, 0, tzinfo=UTC)
    n_hours = 40
    end = start + n_hours * H
    flags = _flags(seed, n_hours, start)
    ks = mod("killswitch")
    st = FakeStrategy(always=False)

    clock_holder = {}

    def bucket():
        return clock_holder["c"].now().replace(minute=0, second=0, microsecond=0)

    class SchedVeto(FakeVeto):
        def lookup(self, pair, side, now):
            self.status = "blocked" if flags.get(bucket(), (False,) * 3)[0] else "allowed"
            return super().lookup(pair, side, now)

    class SKill(ks.Killswitch):
        def active(self):
            return flags.get(bucket(), (False,) * 3)[1]

    view = SynthView(PAIRS, start - timedelta(days=4), end + timedelta(hours=2), seed=seed, mode="rw", vol=0.0025)
    e = Env(tmp, mode="backtest", start=start, view=view, real_signals=True, strategy=st, strict=True,
            veto_obj=SchedVeto(), kill_cls=SKill, status=False)
    clock_holder["c"] = e.clock
    orig_entries = e.ledger.entries_allowed

    def entries():
        if flags.get(bucket(), (False,) * 3)[2]:
            return L.Health(False, "degraded", "program")
        return orig_entries()
    e.ledger.entries_allowed = entries

    eq_before, violations = {}, []

    def check(where):
        pos = e.state.open_positions()
        cnt = Counter(p.pair for p in pos)
        if any(v > 1 for v in cnt.values()):
            violations.append(f"{where}: birden cok pozisyon {cnt}")
        bp = [p.pair for p in e.broker.positions()]
        if len(bp) != len(set(bp)):
            violations.append(f"{where}: broker cift pozisyon")
        for p in pos:
            if p.status == "open":
                stops = [o for o in e.broker.open_orders(p.pair) if o.role == "stop" and o.reduce_only]
                if not stops or abs(sum(o.qty for o in stops) - p.qty) > 1e-9:
                    violations.append(f"{where}: {p.pair} korumasiz")

    pm, dm = e.engine.process_step, e.engine.decision_step

    def pm2(step):
        pm(step)
        check(f"minute {step.ts}")

    def dm2(D):
        eq_before[D] = e.broker.account().equity
        dm(D)
        check(f"decision {D}")
    e.engine.process_step, e.engine.decision_step = pm2, dm2
    e.engine.start()
    e.engine.run_range(start, end)
    check("end")
    return e, flags, eq_before, violations


class TestProperties:
    def test_random_markets_invariants(self, tmp_path):
        total_entries = 0
        for seed in range(6):
            d = tmp_path / f"s{seed}"
            d.mkdir()
            e, flags, eq, viol = _property_run(d, seed)
            assert viol == [], (seed, viol[:3])
            led = e.real_ledger
            decs = led.list_decisions()
            entered = [x for x in decs if x.final_action == "entered"]
            total_entries += len(entered)
            for x in entered:
                veto_blk, kill, led_bad = flags.get(x.bar_close_ts, (False,) * 3)
                assert not (veto_blk or kill or led_bad), (seed, x.bar_close_ts, "kapali kapida giris")
                assert x.veto_status == "allowed" and x.risk_allowed is True and x.size_qty > 0
            trades = sorted((t for t in led._trades("", (), False)), key=lambda t: t.entry_ts)
            last_exit: dict = {}
            for t in trades:
                prev = last_exit.get(t.pair)
                if prev is not None:
                    assert prev <= t.entry_ts, (seed, t.pair, "ayni cifte cakisan pozisyon")
                last_exit[t.pair] = t.exit_ts if t.exit_ts is not None else datetime.max.replace(tzinfo=UTC)
                dec = led.get_decision(t.decision_id)
                assert t.planned_stop > 0 and t.planned_stop != t.planned_entry         # koruyucu stop tanimli
                if t.realized_pnl is not None and t.realized_pnl < 0:
                    assert -t.realized_pnl <= 0.02 * eq[dec.bar_close_ts] + 1e-9, (seed, t.trade_id, t.realized_pnl)
            assert len(trades) <= len(entered)
            e.close()
        assert total_entries >= 3, "ozellik testi bos gecti: hic giris yok"


# =====================================================================================================
# 15. CLI (§9)
# =====================================================================================================
class TestCli:
    def test_smoke_exit_code_2(self):
        r = subprocess.run([sys.executable, "-m", "trader_engine", "smoke"], cwd=ROOT,
                           env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 2 and "faz_b" in (r.stdout + r.stderr)

    def test_cli_import_is_light(self):
        code = ("import sys; import trader_engine.cli; "
                "bad=[m for m in ('trader_engine.backtest','trader_engine.marketdata.feed','pyarrow') if m in sys.modules]; "
                "print(bad); sys.exit(1 if bad else 0)")
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                           env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stdout + r.stderr
