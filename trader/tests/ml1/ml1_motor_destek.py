"""ML1 kagit kapisi testleri icin ortak yardimcilar: sentetik cok-cift gecmis (15m/1h/4h feather), motor kurucu, paket yazici, cevrimdisi
boru hatti (scan + build_features + score). Ag yok; var/history yok."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from trader_core import ledger as L
from trader_core import signals as S
from trader_engine import engine as E
from trader_engine.clock import SimClock
from trader_engine.config import apply_overrides, load_cli_config
from trader_engine.marketdata.sources import HistoricalSource
from trader_ml.ml1 import data as D
from trader_ml.ml1 import features as F
from trader_ml.ml1 import model as M
from trader_ml.ml1 import scan as SC

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
PAPER = load_cli_config(ROOT / "config", "learner", "paper")
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
H_START, H_END = datetime(2026, 4, 5, tzinfo=UTC), datetime(2026, 11, 11, tzinfo=UTC)
START, END = datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 9, 6, tzinfo=UTC)
ARMS = tuple(f"{s}@{tf}" for s in ("T1", "R1", "TF1", "B1", "H2", "S1", "F1", "T1-GERI3", "R1-ERKEN", "MF1-YUTAN", "MF1-PINBAR", "MF1-HARAMI",
                                   "GF1-KANAL", "IN1-RSI", "IN1-MACD", "IN1-FIBO", "PA2-FVG", "PA2-BOLGE") for tf in ("1h", "4h"))
SEED_PKG = ROOT / "models" / "ml1" / "ml1_package.json"


def write_history(hist: Path, pairs=PAIRS, start=H_START, end=H_END) -> None:
    import pyarrow as pa
    import pyarrow.feather as pf
    hist.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(start, end, freq="15min", inclusive="left")
    t = np.arange(len(idx))
    for k, pair in enumerate(pairs):
        rng = np.random.default_rng(31 + k)
        wave = 0.07 * np.sin(2 * np.pi * t / (96 * 5 + k * 40)) + 0.012 * np.sin(2 * np.pi * t / (96 * 1.3))
        close = np.round(100 * (1 + 0.3 * k) * np.exp(wave + np.cumsum(rng.normal(0, 0.0018, len(idx)))), 3)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0009, len(idx)))), 3)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0009, len(idx)))), 3)
        df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close,
                           "volume": np.round(rng.uniform(100, 500, len(idx)), 1)}, index=idx)
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
        fidx = pd.date_range(start, end, freq="8h", inclusive="left")
        pf.write_feather(pa.table({"date": pa.array(fidx.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC")),
                                   "funding_rate": pa.array([0.0001] * len(fidx))}),
                         str(hist / f"{stem}-1h-funding_rate.feather"), compression="uncompressed")


def pmap() -> dict:
    return {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}


def write_package(path: Path, *, threshold: float | None = 0.0, base: Path = SEED_PKG) -> dict:
    """Tohum paketten tureyen GECERLI (yeniden imzali) paket; esik verilir (0 = her adayi gecir)."""
    pkg = json.loads(base.read_text(encoding="utf-8"))
    pkg["threshold"] = threshold
    pkg["sha256"] = M.package_hash(pkg)
    M.save_package(pkg, path)
    return pkg


def make_cfg(tmp: Path, ml1: dict | None, arms=ARMS, pairs=PAIRS, **kw):
    clusters = {"kripto_buyuk": {"pairs": ["BTC/USDT", "ETH/USDT"], "max_positions": 6}, "kripto_diger": {"pairs": ["SOL/USDT"], "max_positions": 6}}
    base = dict(pairs=tuple(pairs), optional_pairs=(), clusters=clusters, cost_overrides={}, arms=tuple(arms), var_dir=str(tmp / "var"),
                kill_file=str(tmp / "KILL"), pause_file=str(tmp / "PAUSE"), market_db=str(tmp / "m.sqlite"), history_dir=str(tmp / "h"),
                cost=dict(fill_model="native", granularity="15m", trigger_source="last"), ml1=ml1 or {},
                arm_max_positions={"default": 6}, arm_family_max_positions={}, max_positions=36)
    base.update(kw)
    return apply_overrides(PAPER, **base)


def make_engine(tmp: Path, hist: Path, ml1: dict | None, start=START, **kw):
    cfg = make_cfg(tmp, ml1, **kw)
    view = HistoricalSource(str(hist), granularity="15m", synthetic_rules=True)
    eng = E.build_engine(cfg, clock=SimClock(start), view=view, env={})
    s = eng.strategy
    eng.ledger.init_params(pmap(), reason=f"strategy:{s.info.name}@{s.info.version} ml1-test")
    eng.start()
    return eng


def rows(eng, sql: str) -> list[dict]:
    con = sqlite3.connect(eng.cfg.ledger_path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql)]
    finally:
        con.close()


def decisions(eng) -> list[dict]:
    out = rows(eng, "SELECT pair, trigger_tf, setup, arm_id, side, bar_close_ts, final_action, skip_reason, veto_reason, features FROM v_decisions ORDER BY id")
    for r in out:
        r["features"] = json.loads(r["features"])
    return out


# ----------------------------------------------------------------------------------------------------------- cevrimdisi boru hatti
def offline_scored(hist: Path, pkg: dict, arms=ARMS, pairs=PAIRS, since: datetime | None = None, until: datetime | None = None) -> pd.DataFrame:
    """Cevrimdisi hat: scan (tum tarih) -> build_features (konfluans tum aday tablosundan + mum ozellikleri) -> score. since/until: decision_ts suzgeci."""
    frames = []
    cache: dict = {}

    def lookup(pair, tf):
        k = (pair, tf)
        if k not in cache:
            cache[k] = D.load_pair_tf(hist, pair, tf)
        return cache[k]

    allc = []
    for pair in pairs:
        for tf in ("1h", "4h"):
            got = lookup(pair, tf)
            if got is None:
                continue
            ids = [a for a in arms if a.endswith("@" + tf)]
            c = SC.scan_pair_tf(pair, tf, got[0], got[1], ids)
            if len(c):
                allc.append(c)
    c = pd.concat(allc, ignore_index=True)
    for _, sub in c.groupby("pair", sort=False):
        frames.append(F.build_features(sub, lookup))
    f = pd.concat(frames)
    f["score"] = M.score(pkg, f)
    if since is not None:
        f = f[f["decision_ts"] >= pd.Timestamp(since)]
    if until is not None:
        f = f[f["decision_ts"] <= pd.Timestamp(until)]
    return f
