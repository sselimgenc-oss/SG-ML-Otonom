"""Birim 06 gerceklestirme dumani (backtest/precomputed/metrics, bt_crosscheck, run_bt_engine, 1m fetch eki).
Sentetik veri; ag yok. Bagimsiz sartname testi: test_engine_06_spec.py (burada tekrarlanmaz)."""
from __future__ import annotations

import importlib
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pa = pytest.importorskip("pyarrow")
import pyarrow.feather as pf  # noqa: E402

from trader_core import signals as S  # noqa: E402
from trader_engine.strategies import registry as REG  # noqa: E402
from trader_engine.strategies.price_action_v1 import PriceActionV1  # noqa: E402

UTC = timezone.utc
REPO = Path(__file__).resolve().parents[2]
PAIRS = ("BTC/USDT", "ETH/USDT")
BASE = ["--period", "20250301-20250306", "--tf", "1h", "--fill-model", "legacy_compat", "--granularity", "15m",
        "--synthetic-rules", "--no-record-filtered"]


def _wf(path: Path, dates: pd.DatetimeIndex, cols: dict) -> None:
    arrs = {"date": pa.array(dates.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
    for k, v in cols.items():
        arrs[k] = pa.array(np.asarray(v, dtype="float64"))
    pf.write_feather(pa.table(arrs), str(path), compression="uncompressed")


def _history(hist: Path) -> None:
    hist.mkdir(parents=True)
    idx = pd.date_range("2025-01-01", "2025-03-12", freq="15min", tz="UTC", inclusive="left")
    for k, pair in enumerate(PAIRS):
        rng = np.random.default_rng(11 + k)
        close = np.round(100.0 * (1 + 0.3 * k) * np.exp(np.cumsum(rng.normal(0, 0.003, len(idx)))), 2)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0015, len(idx)))), 2)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0015, len(idx)))), 2)
        df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": rng.uniform(100, 500, len(idx))},
                          index=idx)
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        for tf, rule in (("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
            g = df if tf == "15m" else pd.DataFrame(
                {"open": df.resample(rule)["open"].first(), "high": df.resample(rule)["high"].max(),
                 "low": df.resample(rule)["low"].min(), "close": df.resample(rule)["close"].last(),
                 "volume": df.resample(rule)["volume"].sum()}).dropna()
            _wf(hist / f"{stem}-{tf}-futures.feather", g.index, g.to_dict("list"))
        fidx = pd.date_range("2025-01-01", "2025-03-12", freq="8h", tz="UTC", inclusive="left")
        _wf(hist / f"{stem}-1h-funding_rate.feather", fidx, {"funding_rate": [0.0001] * len(fidx)})


class _Fake(PriceActionV1):
    def __init__(self, name: str, cheat: bool) -> None:
        super().__init__(name=name, version="0.1", setups_enabled=("T1",), allowed_trigger_tfs=("1h",),
                         block_same_bar_reentry=False, paper_allowed=False)
        self.cheat = cheat

    def compute(self, ctx):
        trig = ctx.bars[ctx.tf]
        idx, n = trig.index, len(trig)
        c = trig["close"].astype("float64")
        cond = (c.shift(-1) > c) if self.cheat else ((c < c.shift(1)) & (c.shift(1) < c.shift(2)))
        cond = cond.fillna(False).astype(bool)
        fl = lambda v: pd.Series(v, index=idx, dtype="float64")  # noqa: E731
        df = pd.DataFrame({
            "setup": pd.Series(np.where(cond, "T1", None), index=idx, dtype=object),
            "side": pd.Series(np.where(cond, "long", None), index=idx, dtype=object), "signal": cond,
            "skip_reason": pd.Series([None] * n, index=idx, dtype=object),
            "planned_entry": c.where(cond), "planned_stop": (c * 0.98).where(cond), "planned_target": fl(np.nan),
            "rr": fl(2.0), "stop_dist_atr": fl(2.0), "atr_tf": c * 0.01, "atr_4h": c * 0.02, "atr_ratio": fl(1.0),
            "regime": pd.Series(["trend_up"] * n, index=idx, dtype=object), "rh": fl(np.nan), "rl": fl(np.nan),
            "rh_touches": pd.Series(0, index=idx, dtype="int64"), "rl_touches": pd.Series(0, index=idx, dtype="int64"),
            "ema_value": c, "body_ratio": fl(0.6), "wick_ratio": fl(0.2), "edge_dist_atr": fl(0.5),
            "pullback_ema": pd.Series(50, index=idx, dtype="int64"),
            "reasons": pd.Series(["fake"] * n, index=idx, dtype=object)}, index=idx)
        return df[S.SIGNAL_COLUMNS]


@pytest.fixture(scope="module")
def _tpl(tmp_path_factory):
    d = tmp_path_factory.mktemp("impl06_hist") / "hist"
    _history(d)
    return d


@pytest.fixture
def ws(tmp_path, monkeypatch, _tpl):
    hist = tmp_path / "hist"
    hist.mkdir()
    for f in _tpl.iterdir():
        (hist / f.name).write_bytes(f.read_bytes())
    (tmp_path / "config").mkdir()
    cfg = json.loads((REPO / "config" / "engine.base.json").read_text())
    cfg.update(pairs=list(PAIRS), history_dir=str(hist), var_dir=str(tmp_path / "var"),
               market_db=str(tmp_path / "var" / "market.sqlite"), kill_file=str(tmp_path / "KILL"))
    (tmp_path / "config" / "engine.base.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(REG._FACTORIES, "fake_clean", lambda: _Fake("fake_clean", False))
    monkeypatch.setitem(REG._FACTORIES, "fake_cheat", lambda: _Fake("fake_cheat", True))
    return tmp_path


def _bt(*args) -> int:
    from trader_engine import backtest as B
    return int(B.main(list(args)) or 0)


def test_impl06_run_outputs_and_determinism(ws):
    assert _bt("--id", "a", "--strategy", "fake_clean", *BASE) == 0
    assert _bt("--id", "b", "--strategy", "fake_clean", *BASE) == 0
    a, b = ws / "var/backtests/a", ws / "var/backtests/b"
    for f in ("trades.csv", "summary.json", "meta.json", "open_at_end.json", "ledger.sqlite"):
        assert (a / f).exists()
    ta, tb = pd.read_csv(a / "trades.csv"), pd.read_csv(b / "trades.csv")
    assert len(ta) > 0 and ta.equals(tb)
    s = json.loads((a / "summary.json").read_text())
    from trader_engine.metrics import METRIC_KEYS, RISKCHECK_KEYS
    assert set(METRIC_KEYS) <= set(s) and set(RISKCHECK_KEYS) == set(s["riskcheck"])
    m = json.loads((a / "meta.json").read_text())
    assert m["coarse"] is True and m["rules_source"] == "synthetic" and m["peek_uses"] > 0
    assert m["strategy"] == "fake_clean" and m["strategy_label"] == "strategy:fake_clean@0.1"
    assert _bt("--id", "a", "--strategy", "fake_clean", *BASE) == 2          # taze cikti dizini zorunlu


def test_impl06_flat_optimisation_equivalent(ws):
    assert _bt("--id", "f1", "--strategy", "fake_clean", *BASE) == 0
    assert _bt("--id", "f2", "--strategy", "fake_clean", "--no-skip-flat", *BASE) == 0
    pd.testing.assert_frame_equal(pd.read_csv(ws / "var/backtests/f1/trades.csv"),
                                  pd.read_csv(ws / "var/backtests/f2/trades.csv"))


def test_impl06_holdout_refused_and_no_output(ws, kilitli_motor):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    for per in ("20260501-20260601", "20260401-20260601", "20260101-20261231"):
        assert _bt("--id", "h", "--period", per, "--strategy", "fake_clean") == 2
    assert not (ws / "var/backtests/h").exists()


def test_impl06_paranoid_and_truncate(ws):
    assert _bt("--id", "p1", "--strategy", "fake_clean", "--paranoid", "20", *BASE) == 0
    assert _bt("--id", "p2", "--strategy", "fake_cheat", "--paranoid", "40", *BASE) == 3
    assert (ws / "var/backtests/p2/paranoid_diff.json").exists()
    assert _bt("--id", "t1", "--strategy", "fake_clean", "--truncate-check", "20250304T00", *BASE) == 0
    rcs = [_bt("--id", f"c{h}", "--strategy", "fake_cheat", "--truncate-check", f"20250304T{h:02d}", *BASE)
           for h in range(1, 9)]
    assert 5 in rcs and set(rcs) <= {0, 5}, rcs          # tek-bar gelecek-bakis yalniz son barda gorunur
    assert _bt("--id", "t3", "--strategy", "fake_clean", "--truncate-check", "20250304T00:30", *BASE) == 2


def test_impl06_guarded_view_and_missing_native_data(ws):
    from trader_engine.clock import SimClock
    from trader_engine.marketdata.sources import HistoricalSource
    from trader_engine.precomputed import GuardedView, LookaheadError
    clock = SimClock(datetime(2025, 3, 1, 12, tzinfo=UTC))
    g = GuardedView(HistoricalSource(ws / "hist", granularity="15m", synthetic_rules=True), clock)
    assert len(g.bars("BTC/USDT", "1h", clock.now())) > 0
    with pytest.raises(LookaheadError):
        g.bars("BTC/USDT", "1h", clock.now() + timedelta(hours=1))
    with pytest.raises(LookaheadError):
        g.open_at("BTC/USDT", clock.now())               # native kipte yasak
    assert _bt("--id", "n", "--period", "20250301-20250306", "--strategy", "fake_clean", "--synthetic-rules") == 4


def test_impl06_metrics_example_and_registry(tmp_path):
    from trader_engine.metrics import compute_metrics
    t = pd.DataFrame({"trade_id": [1, 2, 3], "pair": ["BTC/USDT"] * 3, "side": ["long"] * 3, "setup": ["T1"] * 3,
                      "regime": ["trend_up"] * 3, "entry_ts": ["2025-03-01T00:00:00.000Z"] * 3,
                      "exit_ts": ["2025-03-01T01:00:00.000Z", "2025-03-01T02:00:00.000Z", "2025-03-01T03:00:00.000Z"],
                      "entry_price": [100.0] * 3, "exit_price": [101.0, 99.0, 99.0], "qty": [1.0] * 3,
                      "planned_stop": [95.0] * 3, "fee_entry": [0.0] * 3, "fee_exit": [0.0] * 3,
                      "funding_paid": [0.0] * 3, "gross_pnl": [20.0, -10.0, -10.0], "realized_pnl": [20.0, -10.0, -10.0],
                      "r_multiple": [1.0, -0.5, -0.5], "exit_reason": ["target", "stop", "stop"]})
    m = compute_metrics(t, wallet_start=1000.0)
    assert m["profit_pct"] == 0.0 and m["profit_factor"] == 1.0 and abs(m["win_rate"] - 1 / 3) < 1e-12
    assert abs(m["max_dd_abs"] - 20.0) < 1e-9 and abs(m["max_dd_pct"] - 20 / 1020 * 100) < 1e-9
    sys.path.insert(0, str(REPO / "research"))
    try:
        rb = importlib.import_module("run_bt_engine")
    finally:
        sys.path.pop(0)
    reg = tmp_path / "reg.csv"
    assert rb.append_registry(reg, {"id": "x"}) == "001:x" and rb.append_registry(reg, {"id": "y"}) == "002:y"
    assert len(reg.read_text().splitlines()) == 3


def test_impl06_crosscheck_identical_and_diff(ws):
    assert _bt("--id", "x_compat", "--strategy", "fake_clean", *BASE) == 0
    out = ws / "var/backtests/x_compat"
    sys.path.insert(0, str(REPO / "research"))
    try:
        X = importlib.import_module("bt_crosscheck")
    finally:
        sys.path.pop(0)
    rep = X.crosscheck(out, out, "x")
    assert rep["passed"] and rep["unexplained"] == 0 and rep["accept"]["B"]["pct"] == 100.0
    assert X.main(["--id", "x", "--ref-dir", str(out), "--engine-dir", str(out), "--out-dir", str(ws / "xo")]) == 0
    assert (ws / "xo" / "x.json").exists() and (ws / "xo" / "x.md").exists()


def test_impl06_fetch_1m_extension(tmp_path, monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        F = importlib.import_module("fetch_binance_vision")
    finally:
        sys.path.pop(0)
    t0 = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)
    rows = "\n".join(f"{t0 + i * 60000},1,2,0.5,1.5,10,{t0 + i * 60000 + 59999},0,0,0,0,0" for i in range(31 * 1440))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", rows)
    blob = buf.getvalue()
    seen = []

    def fake_get(url, retries=5):
        seen.append(url)
        return None if url.endswith(".CHECKSUM") else blob
    monkeypatch.setattr(F, "http_get", fake_get)
    rc = None
    monkeypatch.setattr(sys, "argv", ["f", "--only-1m", "--pairs", "BTC", "--start", "2025-01", "--end", "2025-01",
                                      "--history-dir", str(tmp_path / "d" / "hist"), "--raw-dir", str(tmp_path / "d" / "raw"),
                                      "--workers", "1"])
    rc = F.main()
    assert rc == 0
    assert any("/klines/BTCUSDT/1m/" in u for u in seen) and any("/markPriceKlines/BTCUSDT/1m/" in u for u in seen)
    out = tmp_path / "d" / "hist"
    assert not any("1h" in p.name or "funding" in p.name for p in out.iterdir())
    for suffix in ("futures", "mark"):
        p = out / f"BTC_USDT_USDT-1m-{suffix}.feather"
        t = pf.read_table(str(p))
        assert t.column_names == ["date", "open", "high", "low", "close", "volume"] and t.num_rows == 31 * 1440
        assert os.path.getsize(p) > 0.9 * t.num_rows * 8 * 6                 # sikistirilmamis
