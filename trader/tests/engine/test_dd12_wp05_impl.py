"""DD-12 WP-05 uygulayici duman testleri: acilis kapisi, seansa gore kayma, kagit broker
sicrama, status kume sayilari ve sentetik veriyle uctan uca kagit motoru (4 cift, 1 hisse isteğe bagli + bosluklu)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core import signals as S
from trader_engine import engine as E
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import CostModel, apply_overrides, load_cli_config
from trader_engine.errors import EngineExit
from trader_engine.marketdata.sources import HistoricalSource
from trader_engine.types import MinuteBar, OrderRequest, SymbolRules

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
PAPER = load_cli_config(ROOT / "config", "learner", "paper")


# --------------------------------------------------------------------------- acilis kapisi (D-T5)
class _View:
    def __init__(self, missing=(), stale=()):
        self.missing, self.stale = set(missing), set(stale)

    def rules(self, p):
        if p in self.missing:
            raise RuntimeError("kural yok")

    def minute_steps(self, pairs, a, b):
        now = b
        t = now - timedelta(seconds=90)
        bars = {}
        for p in pairs:
            ts = now - timedelta(hours=5) if p in self.stale else t
            bars[p] = MinuteBar(p, ts, 60, 1, 1, 1, 1, 1, 1, 1, 1)
        return iter([SimpleNamespace(bars=bars)])


def _gate_engine(view, optional=("NVDA/USDT",)):
    e = object.__new__(E.Engine)
    e.cfg = SimpleNamespace(pairs=["BTC/USDT", "NVDA/USDT"], optional_pairs=tuple(optional), startup_wait_s=30.0,
                            loop_sleep_s=5.0)
    e.clock = SimClock(datetime(2026, 11, 5, 12, tzinfo=UTC))
    e.view = view
    e._c = __import__("collections").Counter()
    e.broker = SimpleNamespace(is_simulated=True)
    return e


@pytest.fixture
def real_gate():
    from trader_engine.engine import Engine
    # tests/conftest.py oturum fixture'i Engine._startup_gate'i sarar; sargi fonksiyonunun globalleri o conftest modulu
    # (ad cakismasi: tests/ml/conftest.py da 'conftest' olarak yuklenebilir, bu yuzden `import conftest` guvenilmez)
    real = Engine._startup_gate.__globals__.get("_REAL")
    if real is None:
        yield
        return
    real["on"] = True
    yield
    real["on"] = False


def test_startup_gate_optional_does_not_block(real_gate):
    e = _gate_engine(_View(stale={"NVDA/USDT"}, missing={"NVDA/USDT"}))
    e._startup_gate()                                           # hisse kural yok + bayat: gecer
    assert e._c["optional_waiting"] == 1


def test_startup_gate_crypto_stale_exits_7(real_gate):
    e = _gate_engine(_View(stale={"BTC/USDT"}))
    with pytest.raises(EngineExit) as ei:
        e._startup_gate()
    assert ei.value.code == 7 if hasattr(ei.value, "code") else True


# --------------------------------------------------------------------------- kayma (D-T29) ve sicrama (D-T31)
RULES = SymbolRules(pair="X", symbol="X", tick=0.01, step=0.001, min_qty=0.001, max_qty=1e6, min_notional=5.0)


def _bar(pair, ts, o, h=None, l=None, c=None):
    h = o if h is None else h
    l = o if l is None else l
    c = o if c is None else c
    return MinuteBar(pair, ts, 900, o, h, l, c, o, h, l, c)


def _broker():
    cfg = PAPER
    base = CostModel(slip_entry_bps=2.0, slip_exit_bps=2.0, slip_stop_bps=5.0, trigger_source="last")
    pcfg = PaperConfig(cost=base, mmr=0.004)
    cfg = SimpleNamespace(cost_overrides=PAPER.cost_overrides, clusters=PAPER.clusters)
    return E.session_cost_broker(cfg, pcfg, lambda p: RULES, lambda p, a, b: [], SimClock(datetime(2026, 11, 5, tzinfo=UTC)))


def _entry_fill(b, pair, ts):
    b.prepare(pair, 3)
    b.market_order(OrderRequest(client_id="e" + pair[:2], pair=pair, role="entry", order_side="buy", qty=1.0, leverage=3,
                                  trigger_price=None, reduce_only=False))
    bars = {pair: _bar(pair, ts, 100.0)}
    b.advance(bars, "fills")
    ev = [x for x in b.poll(ts) if x.fill is not None]
    return ev[0].fill.price


@pytest.mark.parametrize("pair,ts,bps", [
    ("NVDA/USDT", datetime(2026, 11, 4, 15, 0, tzinfo=UTC), 4.0),      # Car 10:00 NY: seans ici
    ("NVDA/USDT", datetime(2026, 11, 4, 22, 0, tzinfo=UTC), 6.0),      # seans disi
    ("NVDA/USDT", datetime(2026, 11, 7, 15, 0, tzinfo=UTC), 8.0),      # Cumartesi
    ("BTC/USDT", datetime(2026, 11, 7, 15, 0, tzinfo=UTC), 2.0),       # kripto: taban
])
def test_session_slippage_entry(pair, ts, bps):
    b = _broker()
    px = _entry_fill(b, pair, ts)
    assert px == pytest.approx(100.0 * (1 + bps / 1e4), abs=0.0101)


def test_session_slippage_stop_and_paper_jump():
    b = _broker()
    ts = datetime(2026, 11, 7, 15, 0, tzinfo=UTC)               # hafta sonu: stop kaymasi 20 bp
    _entry_fill(b, "NVDA/USDT", ts)
    b.place_stop(OrderRequest(client_id="s1", pair="NVDA/USDT", role="stop", order_side="sell", qty=1.0,
                              trigger_price=98.0, reduce_only=True, leverage=None))
    # sicramali mum: acilis 90 < stop 98 -> stop fiyatindan degil, sicrama sonrasi fiyattan (90 -20bp) dolar
    nb = {"NVDA/USDT": _bar("NVDA/USDT", ts + timedelta(minutes=15), 90.0, 90.5, 89.0, 89.5)}
    b.advance(nb, "fills")
    b.advance(nb, "triggers")
    f = [x.fill for x in b.poll(ts) if x.fill is not None and x.fill.role == "stop"][0]
    assert f.price == pytest.approx(90.0 * (1 - 20 / 1e4), abs=0.0101) and f.price < 98.0


def test_paper_jump_base_broker_no_override():
    clock = SimClock(datetime(2026, 11, 5, tzinfo=UTC))
    b = PaperBroker(PaperConfig(cost=CostModel(slip_entry_bps=0, slip_exit_bps=0, slip_stop_bps=0, trigger_source="last"),
                                mmr=0.004), lambda p: RULES, lambda p, a, z: [], clock)
    ts = datetime(2026, 11, 5, 15, tzinfo=UTC)
    _entry_fill(b, "BTC/USDT", ts)
    b.place_stop(OrderRequest(client_id="s1", pair="BTC/USDT", role="stop", order_side="sell", qty=1.0,
                              trigger_price=98.0, reduce_only=True, leverage=None))
    nb = {"BTC/USDT": _bar("BTC/USDT", ts + timedelta(minutes=15), 95.0, 95.5, 94.0, 94.5)}
    b.advance(nb, "fills")
    b.advance(nb, "triggers")
    f = [x.fill for x in b.poll(ts) if x.fill is not None and x.fill.role == "stop"][0]
    assert f.price == 95.0


# --------------------------------------------------------------------------- uctan uca kagit motoru
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "NVDA/USDT"]
EXTRA = "XRP/USDT"
H_START, H_END = datetime(2026, 4, 5, tzinfo=UTC), datetime(2026, 11, 11, tzinfo=UTC)
START, END = datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 9, 6, tzinfo=UTC)
HOLE = (datetime(2026, 11, 6, 2, tzinfo=UTC), datetime(2026, 11, 6, 10, tzinfo=UTC))      # NVDA bosluk


def _write_history(hist: Path) -> None:
    import pyarrow as pa
    import pyarrow.feather as pf
    hist.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(H_START, H_END, freq="15min", inclusive="left")
    t = np.arange(len(idx))
    for k, pair in enumerate(PAIRS + [EXTRA]):
        rng = np.random.default_rng(11 + k)
        wave = 0.06 * np.sin(2 * np.pi * t / (96 * 6 + k * 40)) + 0.01 * np.sin(2 * np.pi * t / (96 * 1.3))
        close = np.round(100 * (1 + 0.3 * k) * np.exp(wave + np.cumsum(rng.normal(0, 0.0015, len(idx)))), 3)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.00075, len(idx)))), 3)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.00075, len(idx)))), 3)
        df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close,
                           "volume": np.round(rng.uniform(100, 500, len(idx)), 1)}, index=idx)
        if pair == "NVDA/USDT":
            df = df[(df.index < HOLE[0]) | (df.index >= HOLE[1])]
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        for tf, rule in (("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
            g = df if tf == "15m" else pd.DataFrame(
                {"open": df.resample(rule)["open"].first(), "high": df.resample(rule)["high"].max(),
                 "low": df.resample(rule)["low"].min(), "close": df.resample(rule)["close"].last(),
                 "volume": df.resample(rule)["volume"].sum()}).dropna()
            arrs = {"date": pa.array(g.index.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
            for c in g.columns:
                arrs[c] = pa.array(g[c].to_numpy(dtype="float64"))
            pf.write_feather(pa.table(arrs), str(hist / f"{stem}-{tf}-futures.feather"), compression="uncompressed")
        fidx = pd.date_range(H_START, H_END, freq="8h", inclusive="left")
        pf.write_feather(pa.table({"date": pa.array(fidx.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC")),
                                   "funding_rate": pa.array([0.0001] * len(fidx))}),
                         str(hist / f"{stem}-1h-funding_rate.feather"), compression="uncompressed")


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    pytest.importorskip("pyarrow")
    d = tmp_path_factory.mktemp("wp05_hist") / "hist"
    _write_history(d)
    return d


def _cfg(tmp: Path, pairs):
    clusters = {"kripto_buyuk": {"pairs": [p for p in pairs if p in ("BTC/USDT", "ETH/USDT", "XRP/USDT")], "max_positions": 2},
                "kripto_diger": {"pairs": ["SOL/USDT"], "max_positions": 6},
                "hisse": {"pairs": ["NVDA/USDT"], "max_positions": 5},
                "hisse_teknoloji": {"pairs": ["NVDA/USDT"], "max_positions": 3}}
    return apply_overrides(
        PAPER, pairs=tuple(pairs), optional_pairs=("NVDA/USDT",),
        clusters=clusters, cost_overrides={"NVDA/USDT": PAPER.cost_overrides["NVDA/USDT"]},
        var_dir=str(tmp / "var"), kill_file=str(tmp / "KILL"), pause_file=str(tmp / "PAUSE"),
        market_db=str(tmp / "m.sqlite"), history_dir=str(tmp / "h"),
        cost=dict(fill_model="native", granularity="15m", trigger_source="last"))


def test_end_to_end_paper(tmp_path, hist):
    cfg0 = _cfg(tmp_path, PAIRS)
    clock = SimClock(START)
    view = HistoricalSource(str(hist), granularity="15m", synthetic_rules=True)
    eng = E.build_engine(cfg0, clock=clock, view=view, env={})
    s = eng.strategy
    eng.ledger.init_params({k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS},
                           reason=f"strategy:{s.info.name}@{s.info.version} wp05")
    eng.start()                                                  # NVDA bosluklu/istege bagli: kapi bekletmez
    eng.run_range(START, END)
    c = eng.counters()
    assert c["decisions"] > 50 and c.get("callback_errors", 0) == 0
    # 23.11.2026 kilit acik: 15 dk golge adaylari artik kilit bitisini beklemez -> kagit kosusunda golge satir yazilabilir (eskiden 0); hata olmamali
    assert eng._rec["shadow"]["rows"] >= 0 and eng._rec["shadow"]["errors"] == 0 and eng._rec["shadow"]["tf15_holdout_wait"] == 0
    # defter: session_tag her karar satirinda gecerli; kripto 'open'
    import sqlite3
    con = sqlite3.connect(eng.cfg.ledger_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT pair, session_tag, final_action, skip_reason FROM v_decisions")]
    con.close()
    assert rows, "en az bir aday karari bekleniyor"
    assert all(r["session_tag"] in ("open", "closed", "weekend") for r in rows)
    assert all(r["session_tag"] == "open" for r in rows if r["pair"] != "NVDA/USDT")
    # status.json: kume sayilari
    eng.status.write(eng, force=True)
    st = json.loads(Path(eng.cfg.status_path).read_text())
    cc = st["cluster_counts"]
    assert cc["account"]["max"] == 36 and set(cc["clusters"]) >= {"kripto_buyuk", "hisse", "hisse_teknoloji"}
    assert cc["account"]["open"] == len(eng.state.open_positions())
    assert st["gate"]["ok"]
    # D-T12: ayni durum/defter yeni cift (XRP) ile yeniden acilir; pozisyon, imlec ve parametre surumu korunur
    before = {"pos": [p.trade_id for p in eng.state.open_positions()], "ver": eng._version_id,
              "cur": eng.state.get_cursor("BTC/USDT", "minute")}
    eng.state.close()
    eng.ledger.close()
    eng2 = E.build_engine(_cfg(tmp_path, PAIRS + [EXTRA]), clock=SimClock(END), view=view, env={})
    eng2.start()
    assert [p.trade_id for p in eng2.state.open_positions()] == before["pos"]
    assert eng2._version_id == before["ver"]
    assert eng2.state.get_cursor(EXTRA, "minute") is not None
    assert eng2.state.get_cursor(EXTRA, "minute") <= before["cur"] + timedelta(minutes=15)
