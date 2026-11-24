#!/usr/bin/env python3
"""DD-12 WP-18 (a): kapasite olcumu. Gercek kagit motor yapilandirmasi (`load_cli_config(config, 'learner', 'paper')`:
44 cift, config/engine.paper.json'daki tum kollar incl. M1) sentetik gecmiste N karar adimi kosar; tepe RSS ve adim suresi raporlar.

Pencereler uretimdeki boyutlarla ayni: 15dk 5000, 1s 1500, 4s 1500 bar (1g bar 4s'ten turer). Veri kaynagi: `HistoricalSource`
(feather); canli kolda `StoreSource` (market.sqlite) kullanilir, bu yuzden bellek olcumu bir ust sinirdir (feather tam okunur).
Bellek: karar motoru ayri bir alt surecte kosar; `ru_maxrss` yalniz motoru (ve betik ici ice gecen kutuphaneleri) olcer, veri
uretimini degil. Adim suresi: her `decision_step` cagrisi kronometrelenir ve adimin kapanan zaman dilimine gore siniflanir
(15dk: yalniz 15dk kollari; 1s: saat basi; 4s: 4 saatlik kapanis; 1g: gun basi).

Kullanim (sunucuda degil; olcum bu makinede):
  PYTHONPATH=src .venv/bin/python scripts/capacity_probe.py --steps 96 --json-out <dosya>
Cikis: 0 (olcum yapildi; esik asimi uyarisi JSON'da, kosu kirilmaz); 1 kullanim; 2 alt surec hatasi.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc

# Sunucu butcesi (docs/motor/dd12-capraz-varlik-spec.md §8, D-T20)
ENGINE_RSS_THRESHOLD_MB = 550.0        # ogrenen (learner) tavan hedefi
STEP_THRESHOLD_S = 120.0               # karar adimi (saat basi dahil) siniri
BAR_WINDOWS = {"15m": 5000, "1h": 1500, "4h": 1500}   # production pencereleri (spec §8 boyutlandirma kurali)
BASE_BARS_15M = 24000                  # 250 gun taban; 4s = 1500 bar, 1s = 6000 bar -> son 1500
END = datetime(2026, 4, 30, tzinfo=UTC)   # kilit baslangicindan (2026-05-01) ONCE: sentetik kural kilit oncesi 1h bar ister; olcum tarihten bagimsiz


def _stem(pair: str) -> str:
    return pair.replace("/", "_") + "_" + pair.split("/")[1]


def generate_history(hist: Path, pairs: list[str]) -> None:
    """Her cift icin 15dk/1s/4s feather + 1s funding. Sentetik, tohumlu (tekrarlanabilir)."""
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.feather as pf

    hist.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(END - timedelta(minutes=15 * BASE_BARS_15M), END, freq="15min", inclusive="left")
    t = np.arange(len(idx))
    for k, pair in enumerate(pairs):
        rng = np.random.default_rng(1000 + k)
        wave = 0.06 * np.sin(2 * np.pi * t / (96 * 6 + k * 40)) + 0.01 * np.sin(2 * np.pi * t / (96 * 1.3))
        close = np.round(100 * (1 + 0.05 * (k % 17)) * np.exp(wave + np.cumsum(rng.normal(0, 0.0015, len(idx)))), 4)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.00075, len(idx)))), 4)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.00075, len(idx)))), 4)
        df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close,
                           "volume": np.round(rng.uniform(100, 500, len(idx)), 1)}, index=idx)
        stem = _stem(pair)
        for tf, rule in (("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
            g = df if tf == "15m" else pd.DataFrame(
                {"open": df.resample(rule)["open"].first(), "high": df.resample(rule)["high"].max(),
                 "low": df.resample(rule)["low"].min(), "close": df.resample(rule)["close"].last(),
                 "volume": df.resample(rule)["volume"].sum()}).dropna()
            g = g.tail(BAR_WINDOWS[tf])
            arrs = {"date": pa.array(g.index.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
            for c in g.columns:
                arrs[c] = pa.array(g[c].to_numpy(dtype="float64"))
            pf.write_feather(pa.table(arrs), str(hist / f"{stem}-{tf}-futures.feather"), compression="uncompressed")
        fidx = pd.date_range(END - timedelta(days=30), END, freq="8h", inclusive="left")
        pf.write_feather(pa.table({"date": pa.array(fidx.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC")),
                                   "funding_rate": pa.array([0.0001] * len(fidx))}),
                         str(hist / f"{stem}-1h-funding_rate.feather"), compression="uncompressed")


def _cfg(work: Path, hist: Path):
    from trader_engine.config import apply_overrides, load_cli_config
    cfg0 = load_cli_config(ROOT / "config", "learner", "paper")
    return apply_overrides(
        cfg0, var_dir=str(work / "var"), kill_file=str(work / "KILL"), pause_file=str(work / "PAUSE"),
        market_db=str(work / "m.sqlite"), history_dir=str(hist),
        cost=dict(fill_model="native", granularity="15m", trigger_source="last"))


def budget_verdict(res: dict) -> dict:
    """Sonuc sozlugunden butce bayraklari (saf; aşım uyarisi uretir, kosuyu kirmaz). Eşikler spec §8 / D-T20."""
    per = res.get("per_step_s", {})
    maxima = [float(v["max"]) for v in per.values() if v.get("max") is not None]
    hourly = per.get("1s", {}).get("max")
    return {
        "rss_threshold_mb": ENGINE_RSS_THRESHOLD_MB, "step_threshold_s": STEP_THRESHOLD_S,
        "rss_over": float(res.get("rss_peak_mb", 0.0)) > ENGINE_RSS_THRESHOLD_MB,
        "hourly_over": hourly is not None and float(hourly) > STEP_THRESHOLD_S,
        "step_max_over": bool(maxima) and max(maxima) > STEP_THRESHOLD_S,
    }


def _category(D: datetime) -> str:
    if D.hour == 0 and D.minute == 0:
        return "1g"
    if D.minute == 0 and D.hour % 4 == 0:
        return "4s"
    if D.minute == 0:
        return "1s"
    return "15m"


def child(work: Path, hist: Path, steps: int, out: Path) -> None:
    """Motor alt sureci: yapilandirma -> motor -> N adim (kronometreli). Sonuc JSON'u `out`a yazilir."""
    from trader_core import signals as S
    from trader_core import ledger as L
    from trader_engine import engine as E
    from trader_engine.clock import SimClock
    from trader_engine.marketdata.sources import HistoricalSource

    def rss_mb() -> float:
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    rss = {"imports": rss_mb()}
    cfg = _cfg(work, hist)
    start = END - timedelta(minutes=15 * steps)
    clock = SimClock(start)
    view = HistoricalSource(str(hist), granularity="15m", synthetic_rules=True)
    eng = E.build_engine(cfg, clock=clock, view=view, env={})
    eng.ledger.init_params({k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS},
                           reason=f"strategy:{eng.strategy.info.name}@{eng.strategy.info.version} capacity_probe")
    # Acilis kapisi (veri tazeligi: 1m bar <= 300 sn) sentetik 15dk veriyle saglanamaz; olcum kapiyi degil adim maliyetini
    # olcer. Kapi ayri testlerde (test_dd12_wp05_impl.py, test_startup_gate.py) denetlenir.
    eng._startup_gate = lambda: None           # type: ignore[method-assign]
    eng.start()
    rss["after_start"] = rss_mb()
    times: dict[str, list[float]] = {"15m": [], "1s": [], "4s": [], "1g": []}
    orig = eng.decision_step

    def timed(D: datetime) -> None:
        t0 = time.perf_counter()
        orig(D)
        times[_category(D)].append(time.perf_counter() - t0)

    eng.decision_step = timed                    # run_range bu ornegi cagirir (instance attribute)
    t_run = time.perf_counter()
    eng.run_range(start, END)
    run_s = time.perf_counter() - t_run
    rss["after_run"] = rss_mb()
    c = eng.counters()
    res = {
        "pairs": len(cfg.pairs), "arms": len(cfg.arms), "steps": steps, "run_s": round(run_s, 2),
        "decisions": int(c.get("decisions", 0)), "rss_mb": rss, "rss_peak_mb": round(rss_mb(), 1),
        "per_step_s": {k: {"n": len(v), "median": round(sorted(v)[len(v) // 2], 3) if v else None,
                           "max": round(max(v), 3) if v else None} for k, v in times.items()},
        "arms_with_m1": [a for a in cfg.arms if a.startswith("M1@")],
    }
    out.write_text(json.dumps(res, sort_keys=True), encoding="utf-8")
    eng.shutdown("capacity_probe") if hasattr(eng, "shutdown") else None
    print(json.dumps(res, sort_keys=True))


def parent(args) -> int:
    from trader_engine.config import load_cli_config  # noqa: F401  (import guard: ortam hazir mi)
    work = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(prefix="capacity-probe-"))
    work.mkdir(parents=True, exist_ok=True)
    hist = work / "hist"
    import shutil
    shutil.rmtree(work / "var", ignore_errors=True)          # her kosu temiz defter/durum (init_params tek sefer)
    for f in ("m.sqlite", "KILL", "PAUSE"):
        (work / f).unlink(missing_ok=True)
    pairs = list(load_cli_config(ROOT / "config", "learner", "paper").pairs)
    if len(pairs) != 44:
        print(f"uyari: beklenen 44 cift, bulunan {len(pairs)}", file=sys.stderr)
    t0 = time.perf_counter()
    generate_history(hist, pairs)
    gen_s = round(time.perf_counter() - t0, 1)
    out = work / "probe_child.json"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    cmd = [sys.executable, str(Path(__file__).resolve()), "--child", "--workdir", str(work), "--hist", str(hist),
           "--steps", str(args.steps), "--out", str(out)]
    p = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if p.returncode != 0 or not out.exists():
        print(p.stderr[-4000:], file=sys.stderr)
        return 2
    res = json.loads(out.read_text(encoding="utf-8"))
    res["data_gen_s"] = gen_s
    res["child_maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0, 1)
    res["budget"] = budget_verdict(res)
    res["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="capacity_probe.py")
    ap.add_argument("--steps", type=int, default=96, help="15dk karar adimi sayisi (96 = 24 saat: saat/4s/1g kapanislari dahil)")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--hist", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--out", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.steps < 1:
        print("steps >= 1 olmali", file=sys.stderr)
        return 1
    if a.child:
        child(Path(a.workdir), Path(a.hist), a.steps, Path(a.out))
        return 0
    return parent(a)


if __name__ == "__main__":
    sys.exit(main())
