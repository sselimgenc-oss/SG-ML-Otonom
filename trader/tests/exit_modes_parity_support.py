"""Cikis kipleri motor <-> karsi-olgu parite testi icin sentetik veri ve kosucu (docs/cikis-kipleri-spec.md 9).
Yalniz sentetik 1 dk yolu; var/history yok; tarihler kilitli donemin disinda."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pa = pytest.importorskip("pyarrow")
import pyarrow.feather as pf  # noqa: E402

from trader_core import exit_counterfactual as EC  # noqa: E402
from trader_core import signals as S  # noqa: E402
from trader_engine.strategies.price_action_v1 import PriceActionV1  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PAIR = "BTC/USDT"
HIST_START, HIST_END = "2025-01-01", "2025-04-05"
PERIOD = "20250301-20250401"


def _wf(path: Path, dates: pd.DatetimeIndex, cols: dict) -> None:
    arrs = {"date": pa.array(dates.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
    for k, v in cols.items():
        arrs[k] = pa.array(np.asarray(v, dtype="float64"))
    pf.write_feather(pa.table(arrs), str(path), compression="uncompressed")


def make_history(hist: Path, seed: int = 5) -> None:
    """1 dk son fiyat yolu (rejim degisen surukleme: +/-1R ve +/-1,5R gezileri ve geri donusler uretir); 15m/1h/4h bundan turetilir;
    mark = son fiyat; funding sabit oran. Fiyatlar ~30000 duzeyinde 1 ondalik, hacimler 3 ondalik (sentetik kural: tick 0,1, adim 0,001)."""
    hist.mkdir(parents=True)
    idx = pd.date_range(HIST_START, HIST_END, freq="1min", tz="UTC", inclusive="left")
    rng = np.random.default_rng(seed)
    n = len(idx)
    seg = 360                                                    # 6 saatlik suruklenme dilimleri
    drift = np.repeat(rng.choice([-1.0, 0.0, 1.0], size=n // seg + 1, p=[0.35, 0.3, 0.35]), seg)[:n] * 0.00006
    close = np.round(30000.0 * np.exp(np.cumsum(drift + rng.normal(0, 0.0006, n))), 1)
    op = np.concatenate([[close[0]], close[:-1]])
    hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0003, n))), 1)
    lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0003, n))), 1)
    df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close, "volume": np.round(rng.uniform(100, 500, n), 3)}, index=idx)
    stem = PAIR.replace("/", "_") + "_USDT"
    for tf, rule in (("1m", None), ("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
        g = df if rule is None else pd.DataFrame({
            "open": df.resample(rule)["open"].first(), "high": df.resample(rule)["high"].max(),
            "low": df.resample(rule)["low"].min(), "close": df.resample(rule)["close"].last(),
            "volume": df.resample(rule)["volume"].sum()}).dropna()
        _wf(hist / f"{stem}-{tf}-futures.feather", g.index, g.to_dict("list"))
    _wf(hist / f"{stem}-1m-mark.feather", idx, {"open": op, "high": hi, "low": lo, "close": close, "volume": np.zeros(n)})
    fidx = pd.date_range(HIST_START, HIST_END, freq="8h", tz="UTC", inclusive="left")
    _wf(hist / f"{stem}-1h-funding_rate.feather", fidx, {"funding_rate": [0.0001] * len(fidx)})


class EveryNth(PriceActionV1):
    """Gercek strateji tablosu (ATR ve rejim motorunkiyle ayni) + sabit aralikli sentetik T1 girisleri (rejimle ayni yon: trend_up long, trend_down short)."""
    EVERY = 3

    def __init__(self, name: str = "parity_nth") -> None:
        super().__init__(name=name, version="0.1", setups_enabled=("T1",), allowed_trigger_tfs=("1h",),
                         block_same_bar_reentry=False, paper_allowed=False)

    def compute(self, ctx):
        df = super().compute(ctx).copy()
        n = len(df)
        pos = np.arange(n)
        c = ctx.bars[ctx.tf]["close"].astype("float64").to_numpy()
        atr = df["atr_tf"].to_numpy(dtype="float64")
        reg = df["regime"].to_numpy(dtype=object)
        long_ = reg == "trend_up"
        cond = (pos % self.EVERY == 0) & np.isfinite(atr) & (atr > 0) & (long_ | (reg == "trend_down"))
        df["signal"] = cond
        df["setup"] = pd.Series(np.where(cond, "T1", None), index=df.index, dtype=object)
        df["side"] = pd.Series(np.where(cond, np.where(long_, "long", "short"), None), index=df.index, dtype=object)
        df["skip_reason"] = pd.Series([None] * n, index=df.index, dtype=object)
        df["planned_entry"] = pd.Series(np.where(cond, c, np.nan), index=df.index)
        df["planned_stop"] = pd.Series(np.where(cond, np.where(long_, c - 2.0 * atr, c + 2.0 * atr), np.nan), index=df.index)
        df["planned_target"] = np.nan
        df["rr"] = 2.0
        df["ema_value"] = df["ema_value"].fillna(pd.Series(c, index=df.index))
        for k, v in (("body_ratio", 0.6), ("wick_ratio", 0.2), ("edge_dist_atr", 0.5)):
            df[k] = df[k].fillna(v)
        df["stop_dist_atr"] = 2.0
        return df[S.SIGNAL_COLUMNS]


# ------------------------------------------------------------------------------------------------ kosucu
def setup_workspace(ws: Path, monkeypatch, hist_template: Path) -> None:
    """`ws/hist` (sablonun kopyasi) + `ws/config/engine.base.json`; cwd = ws; strateji kayitli."""
    from trader_engine.strategies import registry as REG
    hist = ws / "hist"
    hist.mkdir()
    for f in hist_template.iterdir():
        (hist / f.name).write_bytes(f.read_bytes())
    (ws / "config").mkdir()
    cfg = json.loads((REPO / "config" / "engine.base.json").read_text())
    cfg.update(pairs=[PAIR], history_dir=str(hist), var_dir=str(ws / "var"), market_db=str(ws / "var" / "market.sqlite"),
               kill_file=str(ws / "KILL"))
    (ws / "config" / "engine.base.json").write_text(json.dumps(cfg))
    monkeypatch.chdir(ws)
    monkeypatch.setitem(REG._FACTORIES, "parity_nth", lambda: EveryNth())


def run_engine(ws: Path, run_id: str, modes: dict | None) -> Path:
    """Geri test (native, 1 dk adim, tetik `last`; kipler acik) -> kosu dizini."""
    from trader_engine import backtest as B
    args = ["--id", run_id, "--period", PERIOD, "--tf", "1h", "--fill-model", "native", "--granularity", "1m", "--trigger-source", "last",
            "--synthetic-rules", "--no-record-filtered", "--strategy", "parity_nth", "--pairs", PAIR]
    if modes is not None:
        args += ["--exit-modes", json.dumps(modes)]
    assert int(B.main(["--env", "eski", *args]) or 0) == 0
    return ws / "var" / "backtests" / run_id


def load_inputs(run_dir: Path, run_id: str) -> list[EC.TradeInput]:
    from trader_core import ledger as L
    led = L.open_ledger(run_dir / "ledger.sqlite", "learner", create=False, read_only=True, migrate=False)
    try:
        trades = led.list_closed_trades(limit=L.Ledger.LIST_CLOSED_MAX)
    finally:
        led.close()
    return [EC.TradeInput(trade_id=t.trade_id, pair=t.pair, side=t.side, setup=t.setup, trigger_tf="1h", entry_ts=t.entry_ts,
                          exit_ts=t.exit_ts, entry_price=t.entry_price, qty=t.qty, planned_risk=t.planned_risk,
                          initial_stop=t.planned_stop, fee_entry=t.fee_entry, exit_reason=t.exit_reason, exit_price=t.exit_price,
                          actual_net_r=t.r_multiple, param_version_id=t.param_version_id, own_value=3.0, source="backtest",
                          run_id=run_id) for t in trades]


def lot_rules(ws: Path):
    """Motorun kullandigi sentetik kurallar (HistoricalSource, `--synthetic-rules`) -> replay `rules_for`."""
    from trader_engine.marketdata.sources import HistoricalSource
    src = HistoricalSource(ws / "hist", granularity="1m", synthetic_rules=True)

    def fn(pair: str):
        r = src.rules(pair)
        return float(r.step), float(r.min_qty), float(r.min_notional)
    return fn


def replay_rows(ws: Path, run_dir: Path, trades: list[EC.TradeInput], *, tag: str = "", **kw) -> dict[tuple[int, str], dict]:
    """`run_modes_once` (15 dk izgara; 1a ile ayni giris) -> {(trade_id, variant): ecf_modes satiri}."""
    from datetime import datetime, timezone
    meta = json.loads((run_dir / "meta.json").read_text())
    c = meta["cost"]
    cost = {"taker_fee": float(c["taker_fee"]), "slip_exit_bps": float(c["slip_exit_bps"]), "slip_stop_bps": float(c["slip_stop_bps"])}
    db = ws / f"cf_{run_dir.name}{tag}.sqlite"
    store = EC.ExitCfStore(str(db))
    try:
        res = EC.run_modes_once(bot="learner", trades=trades, market=EC.FeatherSource(ws / "hist"), store=store,
                                now=datetime(2025, 6, 1, tzinfo=timezone.utc), active_value=3.0, cost_for=lambda t: cost,
                                trigger_source="last", **kw)
    finally:
        store.close()
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM ecf_modes")]
    finally:
        con.close()
    assert res.pending == 0 and res.data_gap == 0 and res.no_data == 0, res
    return {(r["trade_id"], r["variant"]): r for r in rows}


def replay_exit_price(row: dict, tr: EC.TradeInput) -> float:
    """Satirdaki brut R'den (karma) cikis fiyati: gross = yon x (cikis - giris) x adet / planned_risk."""
    sgn = 1.0 if tr.side == "long" else -1.0
    return tr.entry_price + sgn * row["gross_r"] * tr.planned_risk / tr.qty
