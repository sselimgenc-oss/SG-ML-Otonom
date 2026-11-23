"""Motor birimi 06 (backtester + metrikler + capraz dogrulama) -- bagimsiz sartname testleri.

Kaynak: docs/motor/06-backtester.md (+ 00-index.md). Birim-06 dosyalari okunmadan yazildi; yalnizca sartnamedeki
imzalara (`trader_engine.backtest.main(argv)`, `GuardedView`, `LedgerReplayVeto`, `LookaheadError`, `metrics`,
`research/bt_crosscheck.py`) dayanir. Sartnamenin tanimlamadigi ayrintilar (capraz dogrulama CLI bayraklari,
`--truncate-check` tarih bicimi, metrics islev adi) birden fazla aday ile denenir; hicbiri tutmazsa test BASARISIZ olur.

Not: sartname 06 bir "deneme kaydi (trial registry)" ya da HOLDOUT icin onay bayragi TANIMLAMAZ (§1: "geçersiz kılma
anahtarı yoktur"); bu yuzden o iki konu yalnizca sartnamedeki bicimiyle (holdout reddi, bayraksiz) test edilir.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyarrow")
import pyarrow as pa  # noqa: E402
import pyarrow.feather as pf  # noqa: E402

from trader_core import ledger as L  # noqa: E402
from trader_core import signals as S  # noqa: E402
from trader_core.risk import LOCKED_CFG, loss_at_stop  # noqa: E402
from trader_engine.strategies import registry as REG  # noqa: E402
from trader_engine.strategies.price_action_v1 import PriceActionV1  # noqa: E402

UTC = timezone.utc
REPO = Path(__file__).resolve().parents[2]
PAIRS = ("BTC/USDT", "ETH/USDT")
WALLET = 1000.0
PERIOD = "20250301-20250306"
BASE = ["--period", PERIOD, "--tf", "1h", "--fill-model", "legacy_compat", "--granularity", "15m",
        "--synthetic-rules", "--no-record-filtered", "--veto", "none"]

SUMMARY_KEYS = (
    "n_trades expectancy_R n_R median_R profit_factor profit_abs profit_pct max_dd_pct max_dd_abs avg_duration "
    "avg_duration_min fees_total fee_only slip_approx funding_net funding_paid costs_total gross_pnl gross_winners "
    "costs_over_gross costs_over_gross_winners win_rate backtest_start backtest_end by_setup by_regime by_pair "
    "by_side by_exit by_setup riskcheck engine").split()
RISK_KEYS = "n_viol_2pct max_loss_pct_eq n_loss_gt_1p1x_actual_risk n_R_lt_minus1 min_R viol over_plan".split()


# ----------------------------------------------------------------------------------------------- sentetik veri
def _write_feather(path: Path, dates: pd.DatetimeIndex, cols: dict) -> None:
    ms = dates.as_unit("ms").asi8.astype("int64")
    arrs = {"date": pa.array(ms, type=pa.timestamp("ms", tz="UTC"))}
    for k, v in cols.items():
        arrs[k] = pa.array(np.asarray(v, dtype="float64"))
    pf.write_feather(pa.table(arrs), str(path), compression="uncompressed")


def make_history(hist: Path, pairs=PAIRS, start="2025-01-01", end="2025-03-12", seed=5) -> None:
    hist.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(start, end, freq="15min", tz="UTC", inclusive="left")
    for k, pair in enumerate(pairs):
        rng = np.random.default_rng(seed + k)
        r = rng.normal(0.0, 0.003, len(idx))
        close = np.round(100.0 * (1 + 0.3 * k) * np.exp(np.cumsum(r)), 2)
        open_ = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.0015, len(idx)))), 2)
        lo = np.round(np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.0015, len(idx)))), 2)
        vol = np.round(rng.uniform(100, 500, len(idx)), 1)
        df = pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close, "volume": vol}, index=idx)
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        for tf, rule in (("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
            if tf == "15m":
                g = df
            else:
                gr = df.resample(rule, label="left", closed="left")
                g = pd.DataFrame({"open": gr["open"].first(), "high": gr["high"].max(), "low": gr["low"].min(),
                                  "close": gr["close"].last(), "volume": gr["volume"].sum()}).dropna()
            _write_feather(hist / f"{stem}-{tf}-futures.feather", g.index, g.to_dict("list"))
        fidx = pd.date_range(start, end, freq="8h", tz="UTC", inclusive="left")
        _write_feather(hist / f"{stem}-1h-funding_rate.feather", fidx, {"funding_rate": [0.0001] * len(fidx)})


class WS:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.hist = root / "hist"
        self.var = root / "var"

    def out(self, run_id: str) -> Path:
        return self.var / "backtests" / run_id


@pytest.fixture(scope="module")
def _hist_template(tmp_path_factory):
    d = tmp_path_factory.mktemp("hist_tpl")
    make_history(d / "hist")
    return d / "hist"


@pytest.fixture
def ws(tmp_path, monkeypatch, _hist_template):
    w = WS(tmp_path)
    w.hist.mkdir()
    for f in _hist_template.iterdir():
        os.link(f, w.hist / f.name) if hasattr(os, "link") else (w.hist / f.name).write_bytes(f.read_bytes())
    (tmp_path / "config").mkdir()
    cfg = json.loads((REPO / "config" / "engine.base.json").read_text())
    cfg.update(pairs=list(PAIRS), history_dir=str(w.hist), var_dir=str(w.var), market_db=str(w.var / "market.sqlite"),
               kill_file=str(tmp_path / "KILL"))
    (tmp_path / "config" / "engine.base.json").write_text(json.dumps(cfg))
    # sartname §3 akis 1: config/engine.base.json cwd'ye gore okunur
    monkeypatch.chdir(tmp_path)
    return w


def run_bt(args, expect=None) -> int:
    from trader_engine import backtest as B
    try:
        rc = B.main(list(args))
    except SystemExit as e:  # argparse
        rc = e.code if isinstance(e.code, int) else 2
    rc = int(rc or 0)
    if expect is not None:
        assert rc == expect, f"cikis kodu {rc} != {expect} (args={args})"
    return rc


# ------------------------------------------------------------------------------------------ sahte stratejiler
class _Fake(PriceActionV1):
    """T1 benzeri aday uretir. cheat=True ise bir sonraki barin kapanisina bakar (kasitli gelecek-bakan)."""

    def __init__(self, name: str, cheat: bool) -> None:
        super().__init__(name=name, version="0.1", setups_enabled=("T1",), allowed_trigger_tfs=("1h",),
                         block_same_bar_reentry=False, paper_allowed=False)
        self.cheat = cheat

    def compute(self, ctx):
        trig = ctx.bars[ctx.tf]
        idx = trig.index
        n = len(idx)
        c = trig["close"].astype("float64")
        cond = (c.shift(-1) > c) if self.cheat else ((c < c.shift(1)) & (c.shift(1) < c.shift(2)))
        cond = cond.fillna(False).astype(bool)

        def fl(v):
            return pd.Series(v, index=idx, dtype="float64")

        df = pd.DataFrame({
            "setup": pd.Series(np.where(cond, "T1", None), index=idx, dtype=object),
            "side": pd.Series(np.where(cond, "long", None), index=idx, dtype=object),
            "signal": cond,
            "skip_reason": pd.Series([None] * n, index=idx, dtype=object),
            "planned_entry": c.where(cond),
            "planned_stop": (c * 0.98).where(cond),
            "planned_target": fl(np.nan),
            "rr": fl(2.0), "stop_dist_atr": fl(2.0), "atr_tf": c * 0.01, "atr_4h": c * 0.02, "atr_ratio": fl(1.0),
            "regime": pd.Series(["trend_up"] * n, index=idx, dtype=object),
            "rh": fl(np.nan), "rl": fl(np.nan),
            "rh_touches": pd.Series(0, index=idx, dtype="int64"), "rl_touches": pd.Series(0, index=idx, dtype="int64"),
            "ema_value": c, "body_ratio": fl(0.6), "wick_ratio": fl(0.2), "edge_dist_atr": fl(0.5),
            "pullback_ema": pd.Series(50, index=idx, dtype="int64"),
            "reasons": pd.Series(["fake"] * n, index=idx, dtype=object),
        }, index=idx)
        return df[S.SIGNAL_COLUMNS]


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setitem(REG._FACTORIES, "fake_clean", lambda: _Fake("fake_clean", False))
    monkeypatch.setitem(REG._FACTORIES, "fake_cheat", lambda: _Fake("fake_cheat", True))


# ------------------------------------------------------------------------------------------------ yardimcilar
def dump_ledger(path: Path) -> list:
    c = sqlite3.connect(str(path))
    try:
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name<>'sqlite_sequence' ORDER BY name")]
        out = []
        for t in names:
            out.append((t, c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()))
        return out
    finally:
        c.close()


def ledger_hash(path: Path) -> str:
    return hashlib.sha256(repr(dump_ledger(path)).encode()).hexdigest()


def load_trades(out: Path) -> pd.DataFrame:
    return pd.read_csv(out / "trades.csv")


def load_summary(out: Path) -> dict:
    return json.loads((out / "summary.json").read_text())


def trade_run(ws_, run_id="a", extra=(), strategy="fake_clean") -> Path:
    run_bt(["--id", run_id, "--strategy", strategy, *BASE, *extra], expect=0)
    return ws_.out(run_id)


# ================================================================================================ 1. kapi / CLI
def test_missing_id_is_usage_error(ws):
    assert run_bt(BASE) == 2


@pytest.mark.parametrize("period", ["20260501-20260601", "20260401-20260601", "20261001-20261201",
                                    "20260601-20260701", "20260501-20261101"])
def test_holdout_periods_refused_with_exit_2_and_no_output(ws, period, kilitli_motor):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    rc = run_bt(["--id", "h", "--period", period, "--tf", "1h", "--veto", "none"])
    assert rc == 2
    assert not ws.out("h").exists(), "reddedilen holdout kosusu cikti dizini yaratmamali"


def test_holdout_has_no_override_flag(ws):
    for flag in (["--allow-holdout"], ["--holdout"], ["--force"], ["--i-know-what-i-am-doing"]):
        rc = run_bt(["--id", "h2", "--period", "20260501-20260601", *flag])
        assert rc == 2
        assert not ws.out("h2").exists()


def test_period_ending_at_holdout_start_is_not_holdout(ws):
    # [20260501, ...) yari-acik pencere: 20260501'de biten donem kesismez; veri yok -> 4 (holdout_locked=2 degil)
    rc = run_bt(["--id", "edge", "--period", "20260401-20260501", "--tf", "1h", "--veto", "none",
                 "--fill-model", "legacy_compat", "--granularity", "15m", "--synthetic-rules"])
    assert rc != 2


def test_bad_period_string_is_argument_error(ws):
    assert run_bt(["--id", "bad", "--period", "nonsense", "--tf", "1h"]) == 2


def test_no_data_in_range_exit_4(ws, fakes):
    rc = run_bt(["--id", "nodata", "--strategy", "fake_clean", "--period", "20250901-20250910", "--tf", "1h",
                 "--fill-model", "legacy_compat", "--granularity", "15m", "--synthetic-rules", "--veto", "none"])
    assert rc == 4


def test_missing_history_files_exit_4(ws, fakes):
    for f in ws.hist.iterdir():
        f.unlink()
    assert run_bt(["--id", "nofiles", "--strategy", "fake_clean", *BASE]) == 4


def test_existing_output_dir_refused(ws, fakes):
    trade_run(ws, "dup")
    marker = ws.out("dup") / "trades.csv"
    before = marker.read_bytes()
    rc = run_bt(["--id", "dup", "--strategy", "fake_clean", *BASE])
    assert rc != 0
    assert marker.read_bytes() == before, "var olan cikti dizini ezilmemeli"


def test_unknown_strategy_name_refused(ws):
    rc = run_bt(["--id", "unk", "--strategy", "does_not_exist", *BASE])
    assert rc != 0
    assert not (ws.out("unk") / "summary.json").exists()


def test_strategy_not_dynamically_importable_from_cli_string(ws):
    rc = run_bt(["--id", "unk2", "--strategy", "os.path", *BASE])
    assert rc != 0


def test_cli_module_entry_exit_code_holdout(ws):
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    p = subprocess.run([sys.executable, "-m", "trader_engine", "backtest", "--id", "sub", "--period",
                        "20260501-20260601"], cwd=ws.root, env=env, capture_output=True, text=True, timeout=120)
    assert "holdout_locked" not in (p.stdout + p.stderr), p.stderr[-500:]      # 23.11.2026: kilit acik -> kilit reddi yok (veri yoksa baska kod)


# ===================================================================== 2. strateji secimi (kayit defteri adi)
def test_strategy_selected_by_registry_name_tagged_everywhere(ws, fakes):
    out = trade_run(ws, "sel", strategy="fake_clean")
    assert "fake_clean" in (out / "summary.json").read_text()
    assert "fake_clean" in (out / "meta.json").read_text()
    reasons = [r[0] for r in sqlite3.connect(str(out / "ledger.sqlite")).execute("SELECT reason FROM param_versions")]
    assert any("strategy:fake_clean@0.1" in r for r in reasons), reasons


def test_default_strategy_is_price_action_v1(ws):
    run_bt(["--id", "dflt", *BASE], expect=0)
    out = ws.out("dflt")
    assert "price_action_v1" in (out / "meta.json").read_text()
    assert "price_action_v1" in (out / "summary.json").read_text()


def test_two_strategies_give_different_trades(ws, fakes):
    a = load_trades(trade_run(ws, "s1", strategy="fake_clean"))
    b = load_trades(trade_run(ws, "s2", strategy="fake_cheat"))
    assert len(a) > 0 and len(b) > 0
    assert not a[["pair", "entry_ts"]].equals(b[["pair", "entry_ts"]])


# ========================================================================================= 3. cikti dosyalari
def test_outputs_exist_and_columns(ws, fakes):
    out = trade_run(ws, "o1")
    for f in ("ledger.sqlite", "trades.csv", "summary.json", "meta.json", "open_at_end.json"):
        assert (out / f).exists(), f
    cols = ("trade_id pair side setup regime entry_ts exit_ts entry_price exit_price qty leverage planned_entry "
            "planned_stop planned_target exit_reason planned_exit planned_risk equity_at_entry gross_pnl fee_entry "
            "fee_exit funding_paid realized_pnl r_multiple mfe_r mae_r bars_held excursion_tf slippage_entry "
            "slippage_exit slip_cost decision_id param_version_id").split()
    df = load_trades(out)
    assert list(df.columns) == cols
    assert len(df) > 0


def test_meta_labels_for_compat_run(ws, fakes):
    meta = json.loads((trade_run(ws, "m1") / "meta.json").read_text())
    assert meta["fill_model"] == "legacy_compat"
    assert meta["granularity"] == "15m"
    assert meta["coarse"] is True
    assert meta["rules_source"] == "synthetic"
    for k in ("git_commit", "trigger_source", "data_range", "engine_version", "param_version_id"):
        assert k in meta, k


def test_summary_has_all_run_bt_keys(ws, fakes):
    s = load_summary(trade_run(ws, "k1"))
    missing = [k for k in SUMMARY_KEYS if k not in s]
    assert not missing, missing
    assert set(RISK_KEYS) <= set(s["riskcheck"])
    assert "freqtrade_pf" not in s and "unmatched_ledger_rows" not in s
    assert {"fill_model", "granularity", "coarse", "rules_source", "counters"} <= set(s["engine"])


def test_fresh_ledger_has_nine_param_keys_and_backtest_reason(ws, fakes):
    out = trade_run(ws, "l1")
    c = sqlite3.connect(str(out / "ledger.sqlite"))
    params, reason = c.execute("SELECT params, reason FROM param_versions ORDER BY id LIMIT 1").fetchone()
    assert set(json.loads(params)) == set(L.PARAM_KEYS)
    assert "backtest" in reason


def test_open_positions_not_closed_at_end_and_excluded(ws, fakes):
    out = trade_run(ws, "oe")
    df = load_trades(out)
    s = load_summary(out)
    assert s["n_trades"] == len(df)
    assert df["exit_ts"].notna().all()
    json.loads((out / "open_at_end.json").read_text())  # gecerli JSON


# ============================================================================================== 4. determinizm
def test_determinism_identical_ledger_trades_and_metrics(ws, fakes):
    a = trade_run(ws, "d1")
    b = trade_run(ws, "d2")
    assert (a / "trades.csv").read_bytes() == (b / "trades.csv").read_bytes()
    assert ledger_hash(a / "ledger.sqlite") == ledger_hash(b / "ledger.sqlite")
    sa, sb = load_summary(a), load_summary(b)
    for k in SUMMARY_KEYS:
        assert json.dumps(sa[k], sort_keys=True, default=str) == json.dumps(sb[k], sort_keys=True, default=str), k


def test_flat_optimisation_equivalent_to_no_skip_flat(ws, fakes):
    a = trade_run(ws, "f1")
    b = trade_run(ws, "f2", extra=["--no-skip-flat"])
    assert ledger_hash(a / "ledger.sqlite") == ledger_hash(b / "ledger.sqlite")
    assert (a / "trades.csv").read_bytes() == (b / "trades.csv").read_bytes()


# ================================================================================ 5. metrik formulleri (e2e)
def _recompute(df: pd.DataFrame):
    df = df.copy()
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    df["risk_amt"] = [loss_at_stop(q, e, s, LOCKED_CFG)
                      for q, e, s in zip(df["qty"], df["entry_price"], df["planned_stop"])]
    df["R"] = df["realized_pnl"] / df["risk_amt"]
    return df.sort_values(["exit_ts", "trade_id"], kind="stable")


def test_metrics_match_hand_recomputation_from_trades_csv(ws, fakes):
    out = trade_run(ws, "mx")
    df = _recompute(load_trades(out))
    s = load_summary(out)
    pnl = df["realized_pnl"]
    assert s["n_trades"] == len(df)
    assert s["profit_abs"] == pytest.approx(pnl.sum(), rel=1e-9, abs=1e-9)
    assert s["profit_pct"] == pytest.approx(pnl.sum() / WALLET * 100, rel=1e-9, abs=1e-9)
    assert s["expectancy_R"] == pytest.approx(df["R"].mean(), rel=1e-6, abs=1e-9)
    assert s["median_R"] == pytest.approx(df["R"].median(), rel=1e-6, abs=1e-9)
    assert s["n_R"] == len(df)
    pos, neg = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    if neg > 0:
        assert s["profit_factor"] == pytest.approx(pos / neg, rel=1e-9)
    elif pos > 0:
        assert math.isinf(float(s["profit_factor"]))
    assert s["win_rate"] == pytest.approx((pnl > 0).mean(), rel=1e-9)
    bal = WALLET + pnl.cumsum().to_numpy()
    peak = np.maximum.accumulate(np.concatenate([[WALLET], bal]))[1:]
    dd_abs = float((peak - bal).max())
    dd_pct = float(((peak - bal) / peak).max() * 100)
    assert s["max_dd_abs"] == pytest.approx(dd_abs, rel=1e-9, abs=1e-9)
    assert s["max_dd_pct"] == pytest.approx(dd_pct, rel=1e-9, abs=1e-9)
    dur = (df["exit_ts"] - df["entry_ts"]).dt.total_seconds() / 60.0
    assert s["avg_duration_min"] == pytest.approx(dur.mean(), rel=1e-9)
    fee_paid = (df["fee_entry"] + df["fee_exit"]).sum()
    assert s["fees_total"] == pytest.approx(fee_paid, rel=1e-9, abs=1e-9)
    assert s["funding_paid"] == pytest.approx(df["funding_paid"].sum(), rel=1e-9, abs=1e-9)
    assert s["funding_net"] == pytest.approx(-df["funding_paid"].sum(), rel=1e-9, abs=1e-9)
    assert s["costs_total"] == pytest.approx(fee_paid + df["funding_paid"].sum(), rel=1e-9, abs=1e-9)
    assert s["gross_pnl"] == pytest.approx(df["gross_pnl"].sum(), rel=1e-9, abs=1e-9)
    assert s["gross_winners"] == pytest.approx(df.loc[df["gross_pnl"] > 0, "gross_pnl"].sum(), rel=1e-9, abs=1e-9)
    if df["gross_pnl"].sum() != 0:
        assert s["costs_over_gross"] == pytest.approx(s["costs_total"] / df["gross_pnl"].sum(), rel=1e-6)
    # pnl dagilimi: realized = gross - fees - funding
    recon = df["gross_pnl"] - df["fee_entry"] - df["fee_exit"] - df["funding_paid"]
    np.testing.assert_allclose(recon.to_numpy(), pnl.to_numpy(), rtol=1e-9, atol=1e-9)
    rc = s["riskcheck"]
    assert rc["min_R"] == pytest.approx(df["R"].min(), rel=1e-6, abs=1e-9)
    assert rc["n_R_lt_minus1"] == int((df["R"] < -1).sum())


def test_breakdown_counts_sum_to_n_trades(ws, fakes):
    s = load_summary(trade_run(ws, "bd"))
    for k in ("by_pair", "by_side", "by_exit", "by_setup", "by_regime"):
        v = s[k]
        n = sum((x["n"] if isinstance(x, dict) and "n" in x else x.get("n_trades", 0)) if isinstance(x, dict) else x
                for x in (v.values() if isinstance(v, dict) else [])) if isinstance(v, dict) else None
        if n is not None and n:
            assert n == s["n_trades"], k


def _trades_df(pnls):
    n = len(pnls)
    t0 = datetime(2025, 3, 1, tzinfo=UTC)
    return pd.DataFrame({
        "trade_id": range(1, n + 1), "pair": "BTC/USDT", "side": "long", "setup": "T1", "regime": "trend_up",
        "entry_ts": [t0 + timedelta(hours=3 * i) for i in range(n)],
        "exit_ts": [t0 + timedelta(hours=3 * i + 2) for i in range(n)],
        "entry_price": 100.0, "exit_price": 101.0, "qty": 1.0, "leverage": 3, "planned_entry": 100.0,
        "planned_stop": 99.0, "planned_target": np.nan, "exit_reason": "stop", "planned_exit": np.nan,
        "planned_risk": 1.0, "equity_at_entry": 1000.0, "gross_pnl": pnls, "fee_entry": 0.0, "fee_exit": 0.0,
        "funding_paid": 0.0, "realized_pnl": pnls, "r_multiple": pnls, "mfe_r": 0.0, "mae_r": 0.0, "bars_held": 8,
        "excursion_tf": "15m", "slippage_entry": 0.0, "slippage_exit": 0.0, "slip_cost": 0.0, "decision_id": 1,
        "param_version_id": 1})


def test_metrics_module_spec_example_1(tmp_path):
    """§11 ornek 1: profit_abs=[+20,-10,-10], wallet 1000 -> profit_pct 0, pf 1, win_rate 1/3, maxDD 20 / 1.96%."""
    M = importlib.import_module("trader_engine.metrics")
    df = _trades_df([20.0, -10.0, -10.0])
    res, errs = None, []
    names = [n for n in ("analyze", "compute_metrics", "summarize", "build_summary", "summary_metrics", "compute")
             if hasattr(M, n)]
    assert names, "trader_engine.metrics beklenen islevlerden birini sunmali (analyze/compute_metrics/summarize/...)"
    for n in names:
        fn = getattr(M, n)
        for call in (lambda: fn(df, WALLET), lambda: fn(df, wallet_start=WALLET), lambda: fn(df, WALLET, {}),
                     lambda: fn(df, wallet_start=WALLET, meta={})):
            try:
                res = call()
                break
            except TypeError as e:
                errs.append(str(e))
        if res is not None:
            break
    assert res is not None, f"metrics islevi cagrilamadi: {errs}"
    assert res["n_trades"] == 3
    assert res["profit_abs"] == pytest.approx(0.0, abs=1e-9)
    assert res["profit_pct"] == pytest.approx(0.0, abs=1e-9)
    assert res["profit_factor"] == pytest.approx(1.0)
    assert res["win_rate"] == pytest.approx(1 / 3)
    assert res["max_dd_abs"] == pytest.approx(20.0)
    assert res["max_dd_pct"] == pytest.approx(20 / 1020 * 100, rel=1e-9)
    assert res["max_dd_pct"] == pytest.approx(1.96, abs=0.005)


# ================================================================================ 6. maliyet esleme (fee_eff)
@pytest.mark.parametrize("fee_mult,slip,rate", [(1, 0, 0.0005), (2, 5, 0.0015)])
def test_compat_fee_eff_mapping(ws, fakes, fee_mult, slip, rate):
    """§11 ornek 2: fee_eff = 0.0005*F + S/1e4; kayma komisyona katilir (ayri kayma yok)."""
    out = trade_run(ws, f"fe{fee_mult}{slip}", extra=["--fee-mult", str(fee_mult), "--slip-bps", str(slip)])
    df = load_trades(out)
    assert len(df) > 0
    np.testing.assert_allclose(df["fee_entry"], df["qty"] * df["entry_price"] * rate, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(df["fee_exit"], df["qty"] * df["exit_price"] * rate, rtol=1e-6, atol=1e-6)


def test_compat_default_slip_is_zero(ws, fakes):
    df = load_trades(trade_run(ws, "dz"))
    np.testing.assert_allclose(df["fee_entry"], df["qty"] * df["entry_price"] * 0.0005, rtol=1e-6, atol=1e-6)


def test_native_without_1m_data_is_data_error_exit_4(ws, fakes):
    rc = run_bt(["--id", "nat", "--strategy", "fake_clean", "--period", PERIOD, "--tf", "1h", "--fill-model", "native",
                 "--granularity", "1m", "--synthetic-rules", "--veto", "none"])
    assert rc == 4


def test_compat_requires_15m_granularity(ws, fakes):
    rc = run_bt(["--id", "g1", "--strategy", "fake_clean", "--period", PERIOD, "--tf", "1h", "--fill-model",
                 "legacy_compat", "--granularity", "1m", "--synthetic-rules", "--veto", "none"])
    assert rc != 0


# ======================================================================================== 7. lookahead kilitleri
def test_paranoid_passes_clean_strategy(ws, fakes):
    run_bt(["--id", "pc", "--strategy", "fake_clean", *BASE, "--paranoid", "60", "--seed", "17"], expect=0)


def test_paranoid_detects_cheating_strategy(ws, fakes):
    rc = run_bt(["--id", "pk", "--strategy", "fake_cheat", *BASE, "--paranoid", "100000"])
    assert rc == 3
    assert (ws.out("pk") / "paranoid_diff.json").exists()


def test_paranoid_without_value_uses_default_sample(ws, fakes):
    run_bt(["--id", "pd", "--strategy", "fake_clean", *BASE, "--paranoid"], expect=0)


def test_paranoid_n_larger_than_bars_uses_all(ws, fakes):
    run_bt(["--id", "pn", "--strategy", "fake_clean", *BASE, "--paranoid", "10000000"], expect=0)


def _truncate(ws_, strategy, run_id, hh="12"):
    last = None
    for ts in (f"2025-03-04T{hh}:00:00+00:00", f"2025-03-04T{hh}:00:00Z", f"20250304T{hh}0000",
               f"2025-03-04 {hh}:00", f"20250304{hh}"):
        rid = f"{run_id}_{abs(hash(ts)) % 10_000}"
        rc = run_bt(["--id", rid, "--strategy", strategy, *BASE, "--truncate-check", ts])
        if rc != 2:
            return rc, ws_.out(rid)
        last = rc
    return last, None


def test_truncate_check_passes_clean_strategy(ws, fakes):
    rc, _ = _truncate(ws, "fake_clean", "tc")
    assert rc == 0


def test_truncate_check_breaks_on_cheating_strategy(ws, fakes):
    rc, out = _truncate(ws, "fake_cheat", "tk")
    assert rc == 5
    assert out is not None and (out / "truncate_diff.csv").exists()


def test_truncate_check_end_not_a_bar_close_is_argument_error(ws, fakes):
    rc = run_bt(["--id", "tn", "--strategy", "fake_clean", *BASE, "--truncate-check", "2025-03-04T12:30:00+00:00"])
    assert rc == 2


def test_cheating_strategy_without_checks_runs_silently(ws, fakes):
    """Kilitler yalniz istenince tetiklenir; hile tek basina cikis 0 verir (kilitlerin gerekliligini kanitlar)."""
    run_bt(["--id", "silent", "--strategy", "fake_cheat", *BASE], expect=0)


def _view_clock(ws_):
    from trader_engine.clock import SimClock
    from trader_engine.marketdata.sources import HistoricalSource
    clock = SimClock(datetime(2025, 3, 1, 12, 0, tzinfo=UTC))
    return HistoricalSource(ws_.hist, granularity="15m", synthetic_rules=True), clock


def test_guarded_view_blocks_future_reads(ws):
    from trader_engine.precomputed import GuardedView, LookaheadError
    view, clock = _view_clock(ws)
    g = GuardedView(view, clock)
    now = clock.now()
    ok = g.bars("BTC/USDT", "1h", until=now)
    assert len(ok) > 0
    assert ok.index[-1] + timedelta(hours=1) <= now
    ok2 = g.bars("BTC/USDT", "1h", until=now - timedelta(hours=1))
    assert len(ok2) == len(ok) - 1
    with pytest.raises(LookaheadError):
        g.bars("BTC/USDT", "1h", until=now + timedelta(hours=1))
    with pytest.raises(LookaheadError):
        g.bars("BTC/USDT", "4h", until=now + timedelta(minutes=1))
    with pytest.raises(LookaheadError):
        g.funding("BTC/USDT", now - timedelta(days=1), now + timedelta(days=1))
    with pytest.raises(LookaheadError):
        list(g.minute_steps(["BTC/USDT"], now, now + timedelta(hours=2)))
    # saat ilerleyince ayni istek serbest
    clock.set_time(now + timedelta(hours=1))
    assert len(g.bars("BTC/USDT", "1h", until=now + timedelta(hours=1))) == len(ok) + 1


def test_lookahead_error_is_exception_class():
    from trader_engine.precomputed import LookaheadError
    assert issubclass(LookaheadError, Exception)


# ======================================================================================== 8. LedgerReplayVeto
PARAMS9 = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
           "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}
F_T1 = {"atr_1h": 20.0, "stop_dist_atr": 1.0, "atr_4h": 40.0, "pullback_ema": 50, "ema_value": 99.0,
        "body_ratio": 0.6}
NOW_LEDGER = lambda: datetime(2026, 12, 1, tzinfo=UTC)  # noqa: E731


def _dec(ts, pair="BTC/USDT", entered=True, veto="allowed", veto_reason=None, entry=100.0, stop=99.0, **kw):
    base = dict(bar_close_ts=ts, trigger_tf="1h", pair=pair, side="long", setup="T1", regime="trend_up",
                atr_ratio=1.0, rh=None, rl=None, rh_touches=0, rl_touches=0, features=dict(F_T1),
                planned_entry=entry, planned_stop=stop, planned_target=None, param_version_id=1,
                veto_status=veto, veto_reason=veto_reason)
    if veto == "allowed" and entered:
        base.update(risk_allowed=True, risk_reason="ok", size_qty=10.0, size_notional=1000.0, size_margin=333.0,
                    size_risk_amount=10.0, leverage=3, final_action="entered", skip_reason=None)
    else:
        base.update(risk_allowed=None, risk_reason=None, size_qty=None, size_notional=None, size_margin=None,
                    size_risk_amount=None, leverage=None, final_action="skipped",
                    skip_reason={"blocked": "veto_blocked", "missing": "veto_missing", "stale": "veto_stale"}.get(
                        veto, "other"))
        if veto == "allowed":
            base.update(veto_status="not_evaluated")
    base.update(kw)
    return L.DecisionEvent(**base)


def make_ledger(path: Path, trades: list[dict], extra_decisions=()):
    """trades: dict(pair, ts (karar/giris), entry_price, qty, exit_ts, exit_price, reason, fee_entry, fee_exit,
    funding, stop). Dondurur: ledger yolu."""
    lg = L.open_ledger(path, "learner", create=True, clock=NOW_LEDGER)
    lg.init_params(PARAMS9, reason="synthetic")
    for i, t in enumerate(trades, start=1):
        did = lg.record_decision(_dec(t["ts"], t.get("pair", "BTC/USDT"), entry=t["entry_price"],
                                      stop=t.get("stop", t["entry_price"] * 0.99)))
        lg.record_trade_entry(L.TradeEntry(trade_id=i, decision_id=did, entry_ts=t["ts"], entry_price=t["entry_price"],
                                           qty=t.get("qty", 10.0), leverage=3, fee_entry=t.get("fee_entry", 0.5)))
        if t.get("exit_ts") is not None:
            lg.record_trade_exit(L.TradeExit(trade_id=i, exit_ts=t["exit_ts"], exit_price=t["exit_price"],
                                             exit_reason=t.get("reason", "stop"), planned_exit=None,
                                             fee_exit=t.get("fee_exit", 0.5), funding_paid=t.get("funding", 0.0)))
    for ev in extra_decisions:
        lg.record_decision(ev)
    lg.close()
    return path


def test_ledger_replay_veto_allowed_blocked_missing(tmp_path):
    from trader_engine.precomputed import LedgerReplayVeto
    p = tmp_path / "paper.sqlite"
    t1 = datetime(2025, 3, 2, 10, tzinfo=UTC)
    t2 = datetime(2025, 3, 2, 11, tzinfo=UTC)
    t3 = datetime(2025, 3, 2, 12, tzinfo=UTC)
    lg = L.open_ledger(p, "learner", create=True, clock=NOW_LEDGER)
    lg.init_params(PARAMS9, reason="synthetic")
    lg.record_decision(_dec(t1, entered=False, veto="allowed"))
    lg.record_decision(_dec(t2, entered=False, veto="blocked", veto_reason="llm:no"))
    lg.close()
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    v = LedgerReplayVeto(p)
    v.begin_step(t1)
    a = v.lookup("BTC/USDT", "long", t1)
    b = v.lookup("BTC/USDT", "long", t2)
    m = v.lookup("BTC/USDT", "long", t3)
    o = v.lookup("ETH/USDT", "long", t1)
    assert a.status == "allowed" and not a.blocks
    assert b.status == "blocked" and b.reason == "llm:no" and b.blocks
    assert m.status == "missing" and m.blocks
    assert o.status == "missing" and o.blocks, "baska cift icin kayit yok -> missing (blok)"
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before, "ledger salt okunur olmali"


def test_ledger_replay_veto_stale_returned_verbatim(tmp_path):
    from trader_engine.precomputed import LedgerReplayVeto
    p = tmp_path / "paper.sqlite"
    t1 = datetime(2025, 3, 2, 10, tzinfo=UTC)
    lg = L.open_ledger(p, "learner", create=True, clock=NOW_LEDGER)
    lg.init_params(PARAMS9, reason="synthetic")
    lg.record_decision(_dec(t1, entered=False, veto="stale", veto_reason="age>limit"))
    lg.close()
    r = LedgerReplayVeto(p).lookup("BTC/USDT", "long", t1)
    assert r.status == "stale" and r.reason == "age>limit" and r.blocks


# ================================================================================= 9. capraz dogrulama araci
def _tr(day, hour, pair="BTC/USDT", entry=100.0, exit_=101.0, exit_h=None, reason="target", fee=0.5, funding=0.0):
    ts = datetime(2025, 3, day, hour, tzinfo=UTC)
    return dict(pair=pair, ts=ts, entry_price=entry, qty=10.0, exit_ts=ts + timedelta(hours=exit_h or 4),
                exit_price=exit_, reason=reason, fee_entry=fee, fee_exit=fee, funding=funding)


def _base_trades(n=10):
    out = []
    for i in range(n):
        d, h = 1 + i // 3, 2 + (i % 3) * 6
        out.append(_tr(d, h, pair="BTC/USDT" if i % 2 == 0 else "ETH/USDT", entry=100.0 + i,
                       exit_=101.0 + i if i % 2 == 0 else 99.5 + i, reason="target" if i % 2 == 0 else "stop"))
    return out


def run_crosscheck(tmp_path: Path, ref_trades, eng_trades, run_id="1h_IS_f1_s0"):
    """bt_crosscheck CLI bayraklari sartnamede yok: yaygin adaylar denenir. Dondurur (rc, rapor_metni)."""
    ref = tmp_path / "ref" / run_id
    eng = tmp_path / "eng" / f"{run_id}_compat"
    ref.mkdir(parents=True)
    eng.mkdir(parents=True)
    make_ledger(ref / "ledger.sqlite", ref_trades)
    make_ledger(eng / "ledger.sqlite", eng_trades)
    out = tmp_path / "xout"
    out.mkdir()
    sys.path.insert(0, str(REPO / "research"))
    sys.path.insert(0, str(REPO))
    try:
        X = importlib.import_module("bt_crosscheck")
    finally:
        sys.path.pop(0)
        sys.path.pop(0)
    cands = [
        ["--id", run_id, "--ref-dir", str(ref), "--engine-dir", str(eng), "--out-dir", str(out)],
        ["--id", run_id, "--reference", str(ref), "--engine", str(eng), "--out", str(out)],
        ["--id", run_id, "--ref", str(ref), "--engine", str(eng), "--out", str(out)],
        ["--id", run_id, "--ref-dir", str(ref), "--engine-dir", str(eng), "--out", str(out)],
        ["--id", run_id, "--ref-dir", str(ref), "--engine-dir", str(eng), "--outdir", str(out)],
        ["--id", run_id, "--reference-dir", str(ref), "--engine-dir", str(eng), "--output-dir", str(out)],
        [run_id, str(ref), str(eng), "--out", str(out)],
    ]
    cwd = os.getcwd()
    rc = None
    for argv in cands:
        try:
            for f in out.iterdir():
                f.unlink()
            os.chdir(tmp_path)
            rc = int(X.main(argv) or 0)
        except SystemExit as e:
            if e.code == 2:
                rc = None
                continue
            rc = int(e.code or 0)
        finally:
            os.chdir(cwd)
        break
    assert rc is not None, "bt_crosscheck.main hicbir aday bayrak kumesini kabul etmedi"
    texts = []
    for root in (tmp_path,):
        for f in root.rglob(f"{run_id}*"):
            if f.suffix in (".json", ".md") and "ledger" not in f.name:
                texts.append(f.read_text())
    return rc, "\n".join(texts)


def test_crosscheck_identical_runs_match(tmp_path):
    rc, rep = run_crosscheck(tmp_path, _base_trades(), _base_trades())
    assert rc == 0, rep[-800:]
    assert rep, "rapor (.json/.md) uretilmeli"
    assert "chained_after_first" not in rep or "unexplained" not in rep.lower().replace("unexplained: 0", "")


def test_crosscheck_within_price_tolerances_still_matches(tmp_path):
    ref = _base_trades()
    eng = _base_trades()
    eng[0]["entry_price"] = ref[0]["entry_price"] * (1 + 5e-10)      # giris 1e-9 icinde
    eng[0]["exit_price"] = ref[0]["exit_price"] * (1 + 5e-7)         # cikis 1e-6 icinde
    eng[3]["exit_price"] = ref[3]["exit_price"] * (1 - 5e-7)
    rc, rep = run_crosscheck(tmp_path, ref, eng)
    assert rc == 0, rep[-800:]


def test_crosscheck_entry_price_beyond_1e9_is_reported(tmp_path):
    ref = _base_trades()
    eng = _base_trades()
    for t in eng[:3]:
        t["entry_price"] = t["entry_price"] * (1 + 2e-9)             # sinirin disinda (3/10 > %1 tolerans)
    rc, rep = run_crosscheck(tmp_path, ref, eng)
    assert rc != 0 or "entry_price" in rep


def test_crosscheck_exit_price_beyond_1e6_fails(tmp_path):
    ref = _base_trades()
    eng = _base_trades()
    for t in eng[:4]:
        t["exit_price"] = t["exit_price"] * (1 + 3e-6)
    rc, rep = run_crosscheck(tmp_path, ref, eng)
    assert rc != 0 or "exit_price" in rep


def test_crosscheck_trail_timing_classified(tmp_path):
    ref = [_tr(1, 2, entry=100, exit_=103, reason="trail_stop", exit_h=10)] + _base_trades(9)[1:]
    eng = [_tr(1, 2, entry=100, exit_=103, reason="trail_stop", exit_h=9)] + _base_trades(9)[1:]
    rc, rep = run_crosscheck(tmp_path, ref, eng)
    assert "trail_timing" in rep or rc == 0, "tek-adim trail farki trail_timing olarak siniflanmali/kabul edilmeli"


def test_crosscheck_missing_engine_trade_reported_with_key(tmp_path):
    ref = _base_trades()
    eng = _base_trades()[:-1]
    rc, rep = run_crosscheck(tmp_path, ref, eng)
    assert rc != 0 or "2025-03" in rep
    missing = ref[-1]
    assert missing["pair"] in rep and missing["ts"].strftime("%Y-%m-%d") in rep


def test_crosscheck_exit_reason_mismatch_reported(tmp_path):
    ref = _base_trades()
    eng = _base_trades()
    for t in eng[:3]:
        t["reason"] = "time_stop"
    rc, rep = run_crosscheck(tmp_path, ref, eng)
    assert rc != 0 or "exit_reason" in rep


def test_crosscheck_totals_tolerances(tmp_path):
    """Komisyon farki > %2 (D duzeyi) hata; trade_id farkli olsa da anahtar (pair, side, entry_ts) ile eslesir."""
    ref = _base_trades()
    eng = _base_trades()
    for t in eng:
        t["fee_entry"] *= 1.10
        t["fee_exit"] *= 1.10
    rc, rep = run_crosscheck(tmp_path, ref, eng)
    assert rc != 0 or "fee" in rep.lower()


def test_crosscheck_never_launches_reference_engine(tmp_path, monkeypatch):
    """Freqtrade yeniden calistirilmaz: arac subprocess baslatmamali."""
    def boom(*a, **k):
        raise AssertionError("subprocess cagrildi")
    monkeypatch.setattr(subprocess, "Popen", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    run_crosscheck(tmp_path, _base_trades(), _base_trades())
