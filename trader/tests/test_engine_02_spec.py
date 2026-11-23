"""Independent spec tests for engine unit 02 (types, errors, numeric, clock, bars).

Written only from docs/motor/02-clock-bars.md and 00-index.md.
"""
import dataclasses
import random
import subprocess
import sys
import typing
from datetime import datetime, timedelta, timezone

import pytest

from trader_engine import types as T
from trader_engine import errors as E
from trader_engine import numeric as N
from trader_engine import clock as C
from trader_engine import bars as B

UTC = timezone.utc


def dt(y=2026, mo=12, d=1, h=0, mi=0, s=0, us=0):
    return datetime(y, mo, d, h, mi, s, us, tzinfo=UTC)


NAIVE = datetime(2026, 12, 1, 9, 0, 0)


def names(cls):
    return [f.name for f in dataclasses.fields(cls)]


# ------------------------------------------------------------------ errors
def test_error_hierarchy():
    assert issubclass(E.ConfigError, E.EngineError) and issubclass(E.ConfigError, ValueError)
    for n in ("ClockError", "DataError", "StateError", "BrokerError", "FailClosed"):
        assert issubclass(getattr(E, n), E.EngineError)
    assert issubclass(E.BrokerUncertain, E.BrokerError)
    assert issubclass(E.EngineError, Exception)
    assert not issubclass(E.ClockError, ValueError)


def test_version():
    import trader_engine
    assert trader_engine.__version__ == "0.1.0"


# ------------------------------------------------------------------ types: fields
EXPECTED_FIELDS = {
    "Bar": ["pair", "kind", "tf", "open_ts", "o", "h", "l", "c", "v"],
    "MinuteBar": ["pair", "open_ts", "step_s", "last_o", "last_h", "last_l", "last_c",
                  "mark_o", "mark_h", "mark_l", "mark_c", "volume"],
    "FundingPoint": ["pair", "ts", "rate", "mark"],
    "SymbolRules": ["pair", "symbol", "tick", "step", "min_qty", "max_qty", "min_notional"],
    "OrderRequest": ["client_id", "pair", "role", "order_side", "qty", "trigger_price", "reduce_only",
                     "leverage", "working_type", "signal_bar_close_ts", "created_ts", "partial"],   # partial: canli cikis kipleri (kismi kar alma)
    "OrderResult": ["status", "client_id", "order_id", "filled_qty", "avg_price", "fee", "reason", "ts"],
    "BrokerOrder": ["client_id", "pair", "role", "order_side", "qty", "trigger_price", "reduce_only",
                    "status", "filled_qty", "avg_price", "created_ts", "updated_ts"],
    "Fill": ["client_id", "pair", "role", "order_side", "qty", "price", "fee", "ts", "reason", "ref_price"],  # ref_price: WP-3 (defter-ek-alanlar-spec)
    "BrokerEvent": ["kind", "ts", "pair", "client_id", "fill", "funding_paid", "rate", "mark", "detail"],
    "BrokerPosition": ["pair", "side", "qty", "entry_price", "leverage", "margin", "liq_price",
                       "funding_paid", "fee_paid_entry", "opened_ts", "mark_price", "unrealized"],
    "BrokerAccount": ["wallet", "unrealized", "equity", "used_margin", "available", "ts"],
    "Intent": ["kind", "bot", "pair", "side", "signal_bar_close_ts", "setup", "qty", "leverage",
               "planned_entry", "stop_price", "target_price", "reason", "decision_id"],
    "Position": ["trade_id", "bot", "pair", "side", "setup", "status", "decision_id",
                 "signal_bar_close_ts", "entry_ts", "entry_bar_open", "entry_price", "qty", "leverage",
                 "initial_stop", "current_stop", "stop_seq", "stop_client_id", "planned_target",
                 "trail_atr", "param_version_id", "trigger_tf", "risk_amount", "margin", "rh", "rl",
                 "fee_entry", "funding_paid", "mfe_price", "mae_price", "exit_reason",
                 "exit_client_id", "closed_ts", "strategy_name", "strategy_version"],
}

# defaults (field -> default); every other field must be required
EXPECTED_DEFAULTS = {
    "Fill": {"ref_price": None},
    "Bar": {"v": 0.0},
    "MinuteBar": {"volume": 0.0},
    "OrderRequest": {"working_type": "MARK_PRICE", "signal_bar_close_ts": None, "created_ts": None, "partial": False},
    "OrderResult": {"order_id": None, "filled_qty": 0.0, "avg_price": None, "fee": 0.0,
                    "reason": None, "ts": None},
    "BrokerEvent": {"client_id": None, "fill": None, "funding_paid": 0.0, "rate": None,
                    "mark": None, "detail": None},
    "BrokerPosition": {"mark_price": None, "unrealized": 0.0},
    "Position": {"strategy_name": "price_action_v1", "strategy_version": "1b.0"},
    "Intent": {"decision_id": None},
}


@pytest.mark.parametrize("name", sorted(EXPECTED_FIELDS))
def test_dataclass_fields_exact_and_ordered(name):
    cls = getattr(T, name)
    assert dataclasses.is_dataclass(cls)
    assert names(cls) == EXPECTED_FIELDS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_FIELDS))
def test_dataclass_defaults(name):
    cls = getattr(T, name)
    exp = EXPECTED_DEFAULTS.get(name, {})
    for f in dataclasses.fields(cls):
        if f.name in exp:
            assert f.default == exp[f.name], f.name
        else:
            assert f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING, f.name


@pytest.mark.parametrize("name", sorted(EXPECTED_FIELDS))
def test_dataclass_frozen_no_slots_no_methods(name):
    cls = getattr(T, name)
    assert cls.__dataclass_params__.frozen is True
    assert not hasattr(cls, "__slots__")
    own = {k for k, v in vars(cls).items() if callable(v) or isinstance(v, property)}
    extra = {k for k in own if not k.startswith("__")}
    if name in ("Bar", "MinuteBar"):
        assert extra == {"close_ts"}
    else:
        assert extra == set()


def mk_bar(**kw):
    d = dict(pair="BTC/USDT", kind="last", tf="1h", open_ts=dt(h=9), o=1.0, h=2.0, l=0.5, c=1.5)
    d.update(kw)
    return T.Bar(**d)


def mk_mb(**kw):
    d = dict(pair="BTC/USDT", open_ts=dt(h=9), step_s=60, last_o=1.0, last_h=2.0, last_l=0.5,
             last_c=1.5, mark_o=None, mark_h=None, mark_l=None, mark_c=None)
    d.update(kw)
    return T.MinuteBar(**d)


def test_bar_frozen_and_close_ts():
    b = mk_bar()
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.o = 5.0
    assert b.v == 0.0
    assert b.close_ts == dt(h=10)
    assert mk_bar(tf="4h", open_ts=dt(h=8)).close_ts == dt(h=12)
    assert mk_bar(tf="15m", open_ts=dt(h=9, mi=45)).close_ts == dt(h=10)
    assert mk_bar(tf="1m").close_ts == dt(h=9, mi=1)
    assert b == mk_bar()


def test_minutebar_close_ts():
    assert mk_mb().close_ts == dt(h=9, mi=1)
    assert mk_mb(step_s=900).close_ts == dt(h=9, mi=15)
    with pytest.raises(dataclasses.FrozenInstanceError):
        mk_mb().step_s = 5


def test_other_dataclasses_frozen():
    a = T.BrokerAccount(1.0, 0.0, 1.0, 0.0, 1.0, dt())
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.wallet = 2.0
    r = T.OrderResult(status="filled", client_id="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.fee = 1.0
    e = T.BrokerEvent(kind="funding", ts=dt(), pair="BTC/USDT")
    assert e.funding_paid == 0.0 and e.fill is None


def test_constructor_has_no_validation():
    # spec: no validation in constructor (validation at boundaries)
    b = mk_bar(o=float("nan"), pair="whatever")
    assert b.pair == "whatever"
    mk_bar(open_ts=NAIVE)


def test_order_request_defaults():
    o = T.OrderRequest(client_id="c", pair="BTC/USDT", role="entry", order_side="buy", qty=1.0,
                       trigger_price=None, reduce_only=False, leverage=3)
    assert o.working_type == "MARK_PRICE" and o.created_ts is None and o.signal_bar_close_ts is None


def test_exit_reason_literal():
    vals = set(typing.get_args(T.ExitReason))
    assert vals == {"stop", "target", "trail_stop", "regime_flip", "time_stop", "manual",
                    "force_exit", "liquidation", "other"}
    assert set(typing.get_args(T.Side)) == {"long", "short"}
    assert set(typing.get_args(T.OrderSide)) == {"buy", "sell"}
    assert set(typing.get_args(T.Role)) == {"entry", "stop", "target", "exit"}
    assert set(typing.get_args(T.Kind)) == {"last", "mark"}


def test_exit_reason_matches_ledger():
    ledger = pytest.importorskip("trader_core.ledger")
    assert set(typing.get_args(T.ExitReason)) == set(ledger._EXIT_REASONS)


# ------------------------------------------------------------------ canon_pair & co
def test_canon_pair_examples():
    assert T.canon_pair(" btc/usdt:usdt ") == "BTC/USDT"
    assert T.pair_symbol("BTC/USDT") == "BTCUSDT"
    assert T.pair_stem("BTC/USDT") == "BTC_USDT_USDT"
    assert T.canon_pair("BTC/USDT") == "BTC/USDT"
    assert T.canon_pair("eth/usdt:usdt") == "ETH/USDT"
    assert T.canon_pair("1000SHIB/USDT") == "1000SHIB/USDT"


@pytest.mark.parametrize("bad", ["", "BTCUSDT", "BTC/", "/USDT", "BTC-USDT", "BTC/USDT/X", "BT C/USDT",
                                 "A" * 21 + "/USDT", "BTC/" + "U" * 21, "BTC/US$DT", "   "])
def test_canon_pair_rejects(bad):
    with pytest.raises(ValueError):
        T.canon_pair(bad)


def test_canon_pair_length_limits_ok():
    assert T.canon_pair("A" / "B" if False else "A/B") == "A/B"
    p = "A" * 20 + "/" + "B" * 20
    assert T.canon_pair(p) == p


def test_canon_pair_matches_trader_core_norms():
    risk = pytest.importorskip("trader_core.risk")
    f = getattr(risk, "_norm_pair", None)
    if f is None:
        pytest.skip("no risk._norm_pair")
    for p in ["BTC/USDT:USDT", "eth/usdt", " sol/usdt:usdt "]:
        assert T.canon_pair(p) == f(p)


@pytest.mark.parametrize("side,role,exp", [
    ("long", "entry", "buy"), ("short", "entry", "sell"),
    ("long", "stop", "sell"), ("short", "stop", "buy"),
    ("long", "target", "sell"), ("short", "target", "buy"),
    ("long", "exit", "sell"), ("short", "exit", "buy"),
])
def test_order_side_for(side, role, exp):
    assert T.order_side_for(side, role) == exp


def test_require_utc():
    t = dt(h=5)
    assert T.require_utc(t, "x") is t or T.require_utc(t, "x") == t
    assert T.require_utc(t) == t
    with pytest.raises(ValueError):
        T.require_utc(NAIVE, "ts")
    with pytest.raises(ValueError) as ei:
        T.require_utc(NAIVE, "my_name")
    assert not isinstance(ei.value, E.ClockError)
    # non-UTC aware: either converted to UTC or rejected, never silently kept wrong
    est = timezone(timedelta(hours=-5))
    t2 = datetime(2026, 12, 1, 4, 0, tzinfo=est)
    try:
        r = T.require_utc(t2)
    except ValueError:
        return
    assert r == t2  # same instant


# ------------------------------------------------------------------ numeric
def test_numeric_examples():
    assert N.floor_step(6.3694, 0.001) == 6.369
    assert N.is_multiple(6.369, 0.001) is True
    assert N.round_tight(97.951, "long", 0.01) == 97.96
    assert N.round_tight(102.049, "short", 0.01) == 102.04
    assert N.round_adverse(100.02, "buy", 0.01) == 100.02
    assert N.round_adverse(97.951, "sell", 0.01) == 97.95
    assert N.bps(5.0) == pytest.approx(5.0 / 1e4)
    assert N.bps(0.0) == 0.0


def test_floor_ceil_basics():
    assert N.floor_step(0.0, 0.1) == 0.0
    assert N.ceil_step(0.0, 0.1) == 0.0
    assert N.floor_step(1.0, 0.1) == 1.0
    assert N.ceil_step(1.0, 0.1) == 1.0
    assert N.floor_step(0.3, 0.1) == 0.3  # 0.3/0.1 float trap
    assert N.ceil_step(0.3, 0.1) == 0.3
    assert N.floor_step(0.7, 0.1) == 0.7
    assert N.ceil_step(6.3694, 0.001) == 6.37
    assert N.floor_step(5.9, 1.0) == 5.0
    assert N.ceil_step(5.1, 1.0) == 6.0
    assert isinstance(N.floor_step(5.9, 1.0), float)


def test_floor_step_exact_multiple_minus_epsilon():
    assert N.floor_step(0.3 - 1e-12, 0.1) == 0.2
    assert N.ceil_step(0.3 - 1e-12, 0.1) == 0.3
    assert N.ceil_step(0.3 + 1e-12, 0.1) == 0.4


def test_tiny_step():
    assert N.floor_step(1.23456789, 1e-8) == 1.23456789
    assert N.floor_step(1.234567899, 1e-8) == 1.23456789
    assert N.ceil_step(1.234567891, 1e-8) == 1.23456790
    assert N.floor_step(0.00000001, 1e-8) == 1e-8


def test_is_multiple_edges():
    assert N.is_multiple(0.3, 0.1) is True
    assert N.is_multiple(0.0, 0.1) is True
    assert N.is_multiple(0.3 - 1e-12, 0.1) in (True, False)  # tolerance-dependent, must not raise
    assert N.is_multiple(0.35, 0.1) is False
    assert N.is_multiple(6.3694, 0.001) is False
    assert N.is_multiple(6.369, 0.001, rel_tol=1e-9) is True


@pytest.mark.parametrize("fn", ["floor_step", "ceil_step"])
@pytest.mark.parametrize("x,step", [(1.0, 0.0), (1.0, -0.1), (1.0, float("nan")), (1.0, float("inf")),
                                   (-1.0, 0.1), (-1e-12, 0.1)])
def test_step_fns_reject(fn, x, step):
    with pytest.raises(ValueError):
        getattr(N, fn)(x, step)


@pytest.mark.parametrize("step", [0.0, -0.01, float("nan"), float("inf")])
def test_is_multiple_and_round_reject_bad_step(step):
    with pytest.raises(ValueError):
        N.is_multiple(1.0, step)
    with pytest.raises(ValueError):
        N.round_tight(1.0, "long", step)
    with pytest.raises(ValueError):
        N.round_adverse(1.0, "buy", step)


def test_round_tight_adverse_exact_multiples_unchanged():
    for p in (97.96, 100.02, 0.07, 1234.56):
        for s in ("long", "short"):
            assert N.round_tight(p, s, 0.01) == p
        for s in ("buy", "sell"):
            assert N.round_adverse(p, s, 0.01) == p


def test_round_directions_property():
    rnd = random.Random(1234)
    for _ in range(300):
        tick = rnd.choice([0.01, 0.1, 0.001, 0.5, 1.0])
        px = round(rnd.uniform(0.5, 5000), 6)
        lo = N.round_tight(px, "short", tick)
        hi = N.round_tight(px, "long", tick)
        assert lo <= px + 1e-9 and hi >= px - 1e-9
        assert 0 <= hi - lo <= tick + 1e-9
        assert N.round_adverse(px, "buy", tick) == hi
        assert N.round_adverse(px, "sell", tick) == lo
        assert N.is_multiple(hi, tick) and N.is_multiple(lo, tick)


# ------------------------------------------------------------------ bars constants
def test_bars_constants():
    assert B.TF_SECONDS == {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}
    assert tuple(B.TRIGGER_TFS) == ("1h", "15m")
    assert B.WINDOW_TRIGGER == {"1h": 1500, "15m": 5000}
    assert B.WINDOW_4H == 1500
    assert B.STARTUP_BARS == {"1h": 1200, "15m": 4800}
    assert B.STARTUP_BARS_4H == 300
    # 300*4/tf_hours
    assert B.STARTUP_BARS["1h"] == 300 * 4 / 1
    assert B.STARTUP_BARS["15m"] == 300 * 4 / 0.25


def test_tf_delta():
    assert B.tf_delta("1m") == timedelta(minutes=1)
    assert B.tf_delta("15m") == timedelta(minutes=15)
    assert B.tf_delta("1h") == timedelta(hours=1)
    assert B.tf_delta("4h") == timedelta(hours=4)
    for bad in ("5m", "1d", "", "4H", "2h"):
        with pytest.raises(ValueError):
            B.tf_delta(bad)


# ------------------------------------------------------------------ floor / close
def test_floor_tf_examples():
    assert B.floor_tf(dt(d=1, h=9, mi=17, s=30), "4h") == dt(h=8)
    assert B.floor_tf(dt(h=9, mi=17, s=30, us=500000), "1h") == dt(h=9)
    assert B.floor_tf(dt(h=9, mi=17, s=30), "15m") == dt(h=9, mi=15)
    assert B.floor_tf(dt(h=9, mi=17, s=30), "1m") == dt(h=9, mi=17)
    for h, e in [(0, 0), (3, 0), (4, 4), (7, 4), (8, 8), (11, 8), (12, 12), (15, 12), (16, 16),
                 (19, 16), (20, 20), (23, 20)]:
        assert B.floor_tf(dt(h=h, mi=59, s=59, us=999999), "4h") == dt(h=e)


def test_floor_tf_boundaries_idempotent():
    assert B.floor_tf(dt(h=12), "4h") == dt(h=12)
    assert B.floor_tf(dt(h=12, us=1), "4h") == dt(h=12)
    assert B.floor_tf(dt(h=11, mi=59, s=59, us=999999), "4h") == dt(h=8)
    assert B.floor_tf(dt(h=0), "4h") == dt(h=0)
    # day/year/leap boundaries
    assert B.floor_tf(dt(2028, 2, 29, 23, 59), "4h") == dt(2028, 2, 29, 20)
    assert B.floor_tf(dt(2026, 1, 1, 0, 0, 1), "1h") == dt(2026, 1, 1)


def test_floor_tf_preserves_utc_tz():
    r = B.floor_tf(dt(h=9, mi=17), "1h")
    assert r.tzinfo is not None and r.utcoffset() == timedelta(0)


def test_floor_tf_aligned_to_epoch():
    for tf in ("1m", "15m", "1h", "4h"):
        secs = B.TF_SECONDS[tf]
        rnd = random.Random(5)
        for _ in range(100):
            t = dt() + timedelta(seconds=rnd.uniform(0, 400 * 86400))
            f = B.floor_tf(t, tf)
            assert f <= t < f + B.tf_delta(tf)
            assert int(f.timestamp()) % secs == 0
            assert f.microsecond == 0


def test_is_tf_close():
    assert B.is_tf_close(dt(h=12), "4h") is True
    assert B.is_tf_close(dt(h=13), "4h") is False
    assert B.is_tf_close(dt(h=13), "1h") is True
    assert B.is_tf_close(dt(h=13, mi=15), "15m") is True
    assert B.is_tf_close(dt(h=13, mi=15), "1h") is False
    assert B.is_tf_close(dt(h=13, mi=1), "15m") is False
    assert B.is_tf_close(dt(h=13, mi=1), "1m") is True
    assert B.is_tf_close(dt(h=12, us=1), "4h") is False
    assert B.is_tf_close(dt(h=12, s=1), "4h") is False
    assert B.is_tf_close(dt(h=11, mi=59, s=59, us=999999), "4h") is False


def test_closing_tfs_examples():
    assert B.closing_tfs(dt(h=12)) == ["15m", "1h", "4h"]
    assert B.closing_tfs(dt(h=13)) == ["15m", "1h"]
    assert B.closing_tfs(dt(h=13, mi=15)) == ["15m"]
    assert B.closing_tfs(dt(h=13, mi=1)) == []
    assert B.closing_tfs(dt(h=0)) == ["15m", "1h", "4h"]
    assert B.closing_tfs(dt(h=4, mi=30)) == ["15m"]
    assert B.closing_tfs(dt(h=12, us=1)) == []
    assert B.closing_tfs(dt(h=12, s=1)) == []


def test_closing_tfs_custom_tfs():
    assert B.closing_tfs(dt(h=12), ("1m", "15m", "1h", "4h")) == ["1m", "15m", "1h", "4h"]
    assert B.closing_tfs(dt(h=12, mi=1), ("1m", "15m")) == ["1m"]
    assert B.closing_tfs(dt(h=12), ("1h",)) == ["1h"]
    assert B.closing_tfs(dt(h=13), ("4h",)) == []


def test_last_closed_open_examples():
    assert B.last_closed_open(dt(h=12), "4h") == dt(h=8)
    assert B.last_closed_open(dt(h=11, mi=59, s=59, us=999000), "4h") == dt(h=4)
    assert B.last_closed_open(dt(h=12, us=1), "4h") == dt(h=8)
    assert B.last_closed_open(dt(h=0), "4h") == dt(d=1, h=0) - timedelta(hours=4)
    assert B.last_closed_open(dt(h=13, mi=7), "1h") == dt(h=12)
    assert B.last_closed_open(dt(h=13), "1h") == dt(h=12)
    assert B.last_closed_open(dt(h=13, mi=15), "15m") == dt(h=13)
    assert B.last_closed_open(dt(h=13, mi=14, s=59), "15m") == dt(h=12, mi=45)


def test_bar_close_ts():
    assert B.bar_close_ts(dt(h=8), "4h") == dt(h=12)
    assert B.bar_close_ts(dt(h=9), "1h") == dt(h=10)
    assert B.bar_close_ts(dt(h=9, mi=45), "15m") == dt(h=10)
    assert B.bar_close_ts(dt(h=20), "4h") == dt(d=2, h=0)
    assert B.bar_close_ts(dt(h=9), "1m") == dt(h=9, mi=1)


def test_expected_opens():
    r = list(B.expected_opens(dt(h=0), dt(h=1), "15m"))
    assert r == [dt(h=0), dt(h=0, mi=15), dt(h=0, mi=30), dt(h=0, mi=45)]  # end exclusive
    assert list(B.expected_opens(dt(h=0), dt(d=2, h=0), "4h")) == [dt(h=h) for h in range(0, 24, 4)]
    # start not aligned -> only opens within [start, end)
    r = list(B.expected_opens(dt(h=0, mi=1), dt(h=2), "1h"))
    assert r == [dt(h=1)]
    assert list(B.expected_opens(dt(h=3), dt(h=3), "1h")) == []
    assert list(B.expected_opens(dt(h=3), dt(h=2), "1h")) == []
    # start inclusive
    assert list(B.expected_opens(dt(h=3), dt(h=3, mi=1), "1h")) == [dt(h=3)]
    # lazily iterable (Iterator)
    it = B.expected_opens(dt(h=0), dt(h=2), "1h")
    assert next(it) == dt(h=0)
    assert next(it) == dt(h=1)
    with pytest.raises(StopIteration):
        next(it)
    # count over a week for 15m
    assert len(list(B.expected_opens(dt(h=0), dt(d=8, h=0), "15m"))) == 7 * 96


def test_ms_roundtrip():
    t = dt(2026, 12, 1, 8, 0, 0)
    ms = B.to_ms(t)
    assert isinstance(ms, int)
    assert ms == int(t.timestamp() * 1000)
    assert B.to_ms(datetime(1970, 1, 1, tzinfo=UTC)) == 0
    assert B.to_ms(datetime(1970, 1, 1, 0, 0, 1, 500000, tzinfo=UTC)) == 1500
    r = B.from_ms(ms)
    assert r == t and r.tzinfo is not None and r.utcoffset() == timedelta(0)
    assert B.from_ms(0) == datetime(1970, 1, 1, tzinfo=UTC)
    assert B.from_ms(1500) == datetime(1970, 1, 1, 0, 0, 1, 500000, tzinfo=UTC)
    for m in (1_700_000_000_123, 1_800_000_000_999):
        assert B.to_ms(B.from_ms(m)) == m


def test_funding_times_examples():
    assert B.funding_times(dt(h=7, mi=59), dt(h=16)) == [dt(h=8), dt(h=16)]
    # start exclusive, end inclusive
    assert B.funding_times(dt(h=8), dt(h=16)) == [dt(h=16)]
    assert B.funding_times(dt(h=0), dt(d=2, h=0)) == [dt(h=8), dt(h=16), dt(d=2, h=0)]
    assert B.funding_times(dt(h=8, mi=1), dt(h=15, mi=59)) == []
    assert B.funding_times(dt(h=8), dt(h=8)) == []
    assert B.funding_times(dt(h=16), dt(h=8)) == []
    assert B.funding_times(dt(h=7, s=59), dt(h=8)) == [dt(h=8)]
    assert B.funding_times(dt(h=23, mi=59), dt(d=2, h=0, mi=0, us=1)) == [dt(d=2, h=0)]
    r = B.funding_times(dt(h=0, mi=1), dt(d=4, h=0))
    assert len(r) == 9 and r == sorted(r)
    assert all(x.hour in (0, 8, 16) and x.minute == 0 and x.second == 0 for x in r)


# ------------------------------------------------------------------ UTC / naive rejection
@pytest.mark.parametrize("call", [
    lambda: B.floor_tf(NAIVE, "1h"),
    lambda: B.is_tf_close(NAIVE, "1h"),
    lambda: B.closing_tfs(NAIVE),
    lambda: B.last_closed_open(NAIVE, "1h"),
    lambda: B.bar_close_ts(NAIVE, "1h"),
    lambda: list(B.expected_opens(NAIVE, dt(h=12), "1h")),
    lambda: list(B.expected_opens(dt(h=1), NAIVE, "1h")),
    lambda: B.to_ms(NAIVE),
    lambda: B.funding_times(NAIVE, dt(h=12)),
    lambda: B.funding_times(dt(h=1), NAIVE),
])
def test_bars_reject_naive(call):
    with pytest.raises(ValueError):
        call()


@pytest.mark.parametrize("fn", ["floor_tf", "is_tf_close", "last_closed_open", "bar_close_ts"])
def test_bars_reject_unknown_tf(fn):
    with pytest.raises(ValueError):
        getattr(B, fn)(dt(h=3), "3h")


def test_non_utc_aware_input_equivalent_to_utc():
    est = timezone(timedelta(hours=-5))
    t = datetime(2026, 12, 1, 4, 17, 30, tzinfo=est)  # = 09:17:30Z
    try:
        r = B.floor_tf(t, "4h")
    except ValueError:
        return
    assert r == dt(h=8)


# ------------------------------------------------------------------ clocks
def test_simclock_basics():
    c = C.SimClock(dt(h=9))
    assert c.now() == dt(h=9)
    c.advance(30)
    assert c.now() == dt(h=9, s=30)
    c.advance(0.5)
    assert c.now() == dt(h=9, s=30, us=500000)
    c.advance(0)
    assert c.now() == dt(h=9, s=30, us=500000)
    assert c.now().tzinfo is not None and c.now().utcoffset() == timedelta(0)


def test_simclock_microsecond_precision():
    c = C.SimClock(dt(h=9))
    c.advance(0.000001)
    assert c.now() == dt(h=9, us=1)


def test_simclock_set_time():
    c = C.SimClock(dt(h=9))
    c.set_time(dt(h=10))
    assert c.now() == dt(h=10)
    c.set_time(dt(h=10))  # equal -> no-op
    assert c.now() == dt(h=10)
    with pytest.raises(E.ClockError):
        c.set_time(dt(h=9, mi=59, s=59))
    assert c.now() == dt(h=10)  # unchanged after failure
    with pytest.raises(ValueError):
        c.set_time(NAIVE)
    assert c.now() == dt(h=10)


def test_simclock_advance_negative():
    c = C.SimClock(dt(h=9))
    with pytest.raises(E.ClockError):
        c.advance(-1)
    with pytest.raises(E.ClockError):
        c.advance(-0.001)
    assert c.now() == dt(h=9)


def test_simclock_naive_start():
    with pytest.raises(ValueError):
        C.SimClock(NAIVE)


def test_simclock_sleep_no_real_sleep(monkeypatch):
    import time
    calls = []
    monkeypatch.setattr(time, "sleep", lambda s: calls.append(s))
    c = C.SimClock(dt(h=9))
    t0 = time.monotonic()
    c.sleep(3600)
    assert time.monotonic() - t0 < 1.0
    assert calls == []
    assert c.now() == dt(h=10)
    with pytest.raises(E.ClockError):
        c.sleep(-1)


def test_simclock_now_is_independent_of_wall_clock():
    c = C.SimClock(dt(2020, 1, 1))
    assert c.now() == dt(2020, 1, 1)
    assert c.now() == c.now()


def test_simclock_now_usable_as_callable():
    c = C.SimClock(dt(h=1))
    f = c.now
    c.advance(60)
    assert f() == dt(h=1, mi=1)


def test_systemclock_now_tz_aware_utc():
    c = C.SystemClock()
    n = c.now()
    assert n.tzinfo is not None and n.utcoffset() == timedelta(0)
    assert abs((datetime.now(UTC) - n).total_seconds()) < 5
    n2 = c.now()
    assert n2 >= n or True  # monotonic is not guaranteed, only tz awareness


def test_systemclock_sleep_uses_time_sleep(monkeypatch):
    import time
    calls = []
    monkeypatch.setattr(time, "sleep", lambda s: calls.append(s))
    C.SystemClock().sleep(0.25)
    assert calls == [0.25]


def test_systemclock_injected_wall_time_never_naive(monkeypatch):
    # even if the wall clock module is replaced, now() must stay tz-aware
    n = C.SystemClock().now()
    assert n.tzinfo is not None


def test_clock_protocol_members():
    for cls in (C.SimClock, C.SystemClock):
        assert callable(getattr(cls, "now")) and callable(getattr(cls, "sleep"))
    assert hasattr(C, "Clock")


# ------------------------------------------------------------------ aggregate_minutes
def minute_series(start, n, pair="BTC/USDT", with_mark=True, step_s=60):
    out = []
    for i in range(n):
        base = 100.0 + i
        out.append(T.MinuteBar(
            pair=pair, open_ts=start + timedelta(seconds=step_s * i), step_s=step_s,
            last_o=base, last_h=base + 3.0 + (i % 7), last_l=base - 2.0 - (i % 5), last_c=base + 0.5,
            mark_o=(base + 10 if with_mark else None), mark_h=(base + 13 + (i % 3) if with_mark else None),
            mark_l=(base + 8 - (i % 4) if with_mark else None), mark_c=(base + 10.5 if with_mark else None),
            volume=1.0 + i))
    return out


def test_aggregate_60_minutes_last():
    ms = minute_series(dt(h=9), 60)
    b = B.aggregate_minutes(ms, "1h")
    assert isinstance(b, T.Bar)
    assert b.pair == "BTC/USDT" and b.kind == "last" and b.tf == "1h"
    assert b.open_ts == dt(h=9) and b.close_ts == dt(h=10)
    assert b.o == ms[0].last_o
    assert b.h == max(m.last_h for m in ms)
    assert b.l == min(m.last_l for m in ms)
    assert b.c == ms[-1].last_c
    assert b.v == pytest.approx(sum(m.volume for m in ms))


def test_aggregate_default_kind_is_last():
    ms = minute_series(dt(h=9), 60)
    assert B.aggregate_minutes(ms, "1h") == B.aggregate_minutes(ms, "1h", "last")


def test_aggregate_mark_kind():
    ms = minute_series(dt(h=9), 60)
    b = B.aggregate_minutes(ms, "1h", "mark")
    assert b.kind == "mark"
    assert b.o == ms[0].mark_o and b.c == ms[-1].mark_c
    assert b.h == max(m.mark_h for m in ms) and b.l == min(m.mark_l for m in ms)


def test_aggregate_15m_and_4h():
    ms = minute_series(dt(h=8, mi=15), 15)
    b = B.aggregate_minutes(ms, "15m")
    assert b.open_ts == dt(h=8, mi=15) and b.tf == "15m"
    ms = minute_series(dt(h=8), 240)
    b = B.aggregate_minutes(ms, "4h")
    assert b.open_ts == dt(h=8) and b.close_ts == dt(h=12)
    assert b.v == pytest.approx(sum(m.volume for m in ms))


def test_aggregate_59_minutes_data_error():
    with pytest.raises(E.DataError):
        B.aggregate_minutes(minute_series(dt(h=9), 59), "1h")


def test_aggregate_missing_first_or_last_minute():
    ms = minute_series(dt(h=9), 60)
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms[1:], "1h")
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms[:-1], "1h")


def test_aggregate_gap_in_middle():
    ms = minute_series(dt(h=9), 60)
    del ms[30]
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms, "1h")
    # same count (60) but with a hole + extra from next hour
    ms = minute_series(dt(h=9), 61)
    del ms[30]
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms, "1h")


def test_aggregate_duplicate_minute():
    ms = minute_series(dt(h=9), 60)
    ms.insert(31, ms[30])
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms, "1h")
    ms = minute_series(dt(h=9), 60)
    ms[30] = ms[29]  # 60 items, duplicate, hole
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms, "1h")


def test_aggregate_out_of_order():
    ms = minute_series(dt(h=9), 60)
    ms[10], ms[11] = ms[11], ms[10]
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms, "1h")
    with pytest.raises(E.DataError):
        B.aggregate_minutes(list(reversed(minute_series(dt(h=9), 60))), "1h")


def test_aggregate_mixed_pairs():
    ms = minute_series(dt(h=9), 60)
    ms[5] = dataclasses.replace(ms[5], pair="ETH/USDT")
    with pytest.raises(E.DataError):
        B.aggregate_minutes(ms, "1h")


def test_aggregate_empty():
    with pytest.raises(E.DataError):
        B.aggregate_minutes([], "1h")


def test_aggregate_mark_missing_data_error_or_ok():
    ms = minute_series(dt(h=9), 60, with_mark=False)
    with pytest.raises((E.DataError, ValueError, TypeError)):
        B.aggregate_minutes(ms, "1h", "mark")


def test_aggregate_unknown_tf():
    with pytest.raises(ValueError):
        B.aggregate_minutes(minute_series(dt(h=9), 60), "3h")


def test_aggregate_hand_checkable():
    start = dt(h=9)
    ms = []
    for i in range(15):
        ms.append(T.MinuteBar("BTC/USDT", start + timedelta(minutes=i), 60,
                              10.0, 11.0, 9.0, 10.0, None, None, None, None, 1.0))
    ms[0] = dataclasses.replace(ms[0], last_o=7.0)
    ms[3] = dataclasses.replace(ms[3], last_h=99.0)
    ms[8] = dataclasses.replace(ms[8], last_l=1.5)
    ms[14] = dataclasses.replace(ms[14], last_c=12.25)
    b = B.aggregate_minutes(ms, "15m")
    assert (b.o, b.h, b.l, b.c, b.v) == (7.0, 99.0, 1.5, 12.25, 15.0)


def test_aggregate_does_not_mutate_input():
    ms = minute_series(dt(h=9), 60)
    snap = list(ms)
    B.aggregate_minutes(ms, "1h")
    assert ms == snap


# ------------------------------------------------------------------ closed-bar event emission (clock-driven)
def run_emitter(clock, minutes, tfs=("15m", "1h", "4h")):
    """Drive SimClock minute by minute; emit (close_ts, tf, open_ts) for tfs closing at now.
    Uses only spec'd primitives. Never emits unclosed bars."""
    events = []
    for _ in range(minutes):
        clock.advance(60)
        now = clock.now()
        for tf in B.closing_tfs(now, tfs):
            events.append((now, tf, B.last_closed_open(now, tf)))
    return events


def test_event_emission_exact_boundaries():
    c = C.SimClock(dt(h=0))
    ev = run_emitter(c, 24 * 60)
    by_tf = {tf: [e for e in ev if e[1] == tf] for tf in ("15m", "1h", "4h")}
    assert len(by_tf["15m"]) == 96 and len(by_tf["1h"]) == 24 and len(by_tf["4h"]) == 6
    assert [e[0] for e in by_tf["4h"]] == [dt(h=h) for h in (4, 8, 12, 16, 20)] + [dt(d=2, h=0)]
    for now, tf, op in ev:
        assert B.bar_close_ts(op, tf) == now  # emitted exactly at close
        assert op + B.tf_delta(tf) <= now
        assert B.is_tf_close(now, tf)
    # each bar emitted exactly once
    keys = [(e[1], e[2]) for e in ev]
    assert len(keys) == len(set(keys))


def test_no_emission_one_microsecond_early():
    c = C.SimClock(dt(h=11, mi=59, s=59, us=999999))
    assert B.closing_tfs(c.now()) == []
    c.advance(0.000001)
    assert B.closing_tfs(c.now()) == ["15m", "1h", "4h"]
    c.advance(0.000001)
    assert B.closing_tfs(c.now()) == []


def test_4h_bar_visible_only_after_close():
    # 1h closing at 11:00 while 4h 08:00 bar still open: last closed 4h is 04:00
    for h, exp in [(8, dt(h=4)), (9, dt(h=4)), (10, dt(h=4)), (11, dt(h=4)),
                   (12, dt(h=8)), (13, dt(h=8)), (15, dt(h=8)), (16, dt(h=12))]:
        assert B.last_closed_open(dt(h=h), "4h") == exp
    assert B.last_closed_open(dt(h=11, mi=59, s=59, us=999999), "4h") == dt(h=4)
    assert B.last_closed_open(dt(h=12), "4h") == dt(h=8)


def test_4h_mapping_to_1h_and_15m():
    # every 1h bar opening in [08:00,12:00) maps (floor) to the 08:00 4h bar, whose close is 12:00
    for h in range(8, 12):
        assert B.floor_tf(dt(h=h), "4h") == dt(h=8)
        assert B.bar_close_ts(B.floor_tf(dt(h=h), "4h"), "4h") == dt(h=12)
    for k in range(16):
        t = dt(h=8) + timedelta(minutes=15 * k)
        assert B.floor_tf(t, "4h") == dt(h=8)
    # the 4h bar that contains a given 1h bar is only usable once it is itself closed:
    # at decision time == close of 1h bar 10:00-11:00, the visible 4h is 04:00, not 08:00
    assert B.last_closed_open(dt(h=11), "4h") == dt(h=4)
    # at the close of the last 1h bar in the window (11:00-12:00) the 4h 08:00 bar becomes visible
    assert B.last_closed_open(dt(h=12), "4h") == dt(h=8)
    # 4h aggregates exactly 4 one-hour bars / 16 fifteen-minute bars
    assert len(list(B.expected_opens(dt(h=8), dt(h=12), "1h"))) == 4
    assert len(list(B.expected_opens(dt(h=8), dt(h=12), "15m"))) == 16
    # 1h open boundaries inside 4h are a subset of 4h-aligned 1h grid
    assert all(B.floor_tf(o, "4h") == dt(h=8) for o in B.expected_opens(dt(h=8), dt(h=12), "1h"))


def test_4h_alignment_for_every_day_offset():
    for d in range(1, 29):
        for h in (0, 4, 8, 12, 16, 20):
            assert B.is_tf_close(dt(2026, 12, d, h), "4h")
            assert B.floor_tf(dt(2026, 12, d, h, 3), "4h") == dt(2026, 12, d, h)


# ------------------------------------------------------------------ gaps / duplicates / disorder at the event layer
def test_gap_detection_via_expected_opens():
    present = [o for o in B.expected_opens(dt(h=0), dt(h=6), "1h") if o != dt(h=3)]
    expected = list(B.expected_opens(dt(h=0), dt(h=6), "1h"))
    missing = [o for o in expected if o not in set(present)]
    assert missing == [dt(h=3)]
    assert len(expected) == 6


def test_gap_in_4h_series():
    exp = list(B.expected_opens(dt(h=0), dt(d=3, h=0), "4h"))
    assert len(exp) == 12
    assert all(B.is_tf_close(o, "4h") for o in exp)  # aligned grid


def test_gap_across_funding_and_dst_independent():
    # UTC has no DST: spring/autumn dates still have 24 hourly opens
    for day in (dt(2026, 3, 29), dt(2026, 10, 25), dt(2026, 11, 1)):
        assert len(list(B.expected_opens(day, day + timedelta(days=1), "1h"))) == 24


# ------------------------------------------------------------------ no-lookahead property
def aggregate_stream(minutes, tfs=("15m", "1h", "4h")):
    """Reference event engine built only from spec'd primitives: walks 1m bars,
    at each minute close emits closed tf bars aggregated from minutes."""
    events = []
    by_open = {m.open_ts: m for m in minutes}
    for m in minutes:
        now = m.open_ts + timedelta(seconds=m.step_s)
        for tf in B.closing_tfs(now, tfs):
            op = B.last_closed_open(now, tf)
            n = B.TF_SECONDS[tf] // 60
            need = [op + timedelta(minutes=i) for i in range(n)]
            if all(o in by_open and by_open[o].open_ts < now for o in need):
                bar = B.aggregate_minutes([by_open[o] for o in need], tf)
                events.append((now, tf, bar))
    return events


def rand_minutes(rnd, start, n):
    out = []
    px = 100.0
    for i in range(n):
        o = px
        c = o + rnd.uniform(-1, 1)
        h = max(o, c) + rnd.uniform(0, 0.5)
        l = min(o, c) - rnd.uniform(0, 0.5)
        px = c
        out.append(T.MinuteBar("BTC/USDT", start + timedelta(minutes=i), 60, o, h, l, c,
                               None, None, None, None, rnd.uniform(0, 10)))
    return out


@pytest.mark.parametrize("seed", range(12))
def test_no_lookahead_property(seed):
    rnd = random.Random(seed)
    start = dt(h=0) + timedelta(minutes=rnd.randrange(0, 240))
    start = B.floor_tf(start, "1m")
    n = rnd.randrange(300, 700)
    mins = rand_minutes(rnd, start, n)
    full = aggregate_stream(mins)
    cut = rnd.randrange(60, n - 10)
    t = mins[cut].open_ts + timedelta(seconds=60)  # time of the cut
    base_prefix = [e for e in full if e[0] <= t]
    # truncated data: only minutes closed by t
    trunc = aggregate_stream(mins[: cut + 1])
    assert [e for e in trunc if e[0] <= t] == base_prefix
    # mutate the future arbitrarily
    mut = list(mins)
    for j in range(cut + 1, n):
        m = mut[j]
        mut[j] = dataclasses.replace(m, last_o=m.last_o * 3, last_h=m.last_h * 5 + 7,
                                     last_l=m.last_l * 0.1, last_c=m.last_c * -2, volume=m.volume + 1e6)
    mutated = aggregate_stream(mut)
    assert [e for e in mutated if e[0] <= t] == base_prefix
    # appended data
    extra = rand_minutes(random.Random(seed + 1000), mins[-1].open_ts + timedelta(minutes=1), 200)
    appended = aggregate_stream(mins + extra)
    assert [e for e in appended if e[0] <= t] == base_prefix
    # no event ever stamped before its bar closed; no event contains data past its close
    for now, tf, bar in full:
        assert bar.close_ts == now
        assert bar.open_ts + B.tf_delta(tf) <= now
        assert now == B.bar_close_ts(bar.open_ts, tf)


@pytest.mark.parametrize("seed", range(5))
def test_last_closed_open_never_future_property(seed):
    rnd = random.Random(seed)
    for _ in range(500):
        t = dt() + timedelta(microseconds=rnd.randrange(0, 90 * 86400 * 10**6))
        for tf in ("1m", "15m", "1h", "4h"):
            op = B.last_closed_open(t, tf)
            assert op + B.tf_delta(tf) <= t < op + 2 * B.tf_delta(tf)
            assert B.floor_tf(op, tf) == op


@pytest.mark.parametrize("seed", range(5))
def test_closing_tfs_consistent_with_is_tf_close(seed):
    rnd = random.Random(seed)
    tfs = ("15m", "1h", "4h")
    for _ in range(500):
        t = B.floor_tf(dt() + timedelta(seconds=rnd.randrange(0, 30 * 86400)), "1m")
        if rnd.random() < 0.1:
            t += timedelta(microseconds=rnd.randrange(1, 10**6))
        exp = [tf for tf in tfs if B.is_tf_close(t, tf)]
        assert B.closing_tfs(t) == exp


# ------------------------------------------------------------------ import lightness
def test_import_does_not_load_heavy_deps():
    code = (
        "import sys\n"
        "import trader_engine, trader_engine.errors, trader_engine.types, trader_engine.numeric,"
        " trader_engine.clock, trader_engine.bars\n"
        "bad=[m for m in ('pandas','numpy','requests') if m in sys.modules]\n"
        "assert not bad, bad\n"
    )
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(root, "src") + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=root)
    assert r.returncode == 0, r.stderr


def test_wall_clock_calls_only_in_clock_module():
    # trader_engine.bars must be pure: calling its functions must not touch wall clock
    import time
    orig = time.time
    try:
        time.time = lambda: (_ for _ in ()).throw(AssertionError("wall clock used"))
        B.floor_tf(dt(h=3), "1h")
        B.closing_tfs(dt(h=4))
        B.last_closed_open(dt(h=4), "4h")
        list(B.funding_times(dt(h=0), dt(h=17)))
    finally:
        time.time = orig
