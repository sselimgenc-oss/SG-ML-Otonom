#!/usr/bin/env python3
"""DD-12 WP-14: M1 paketlerini SUNUCU DISINDA egitir (spec 5.3). Yalniz numpy + pandas (feather okuma).

Girdi: tarihsel barlar (`--history-dir`, `<BASE>_USDT_USDT-<tf>-futures.feather`, sütun `date`) ve opsiyonel kagit kayitlari
(`scripts/export_paper_records.py` ciktisi, jsonl). Tarihsel barlar kilit baslangicinda KESILIR (2026-05-01 oncesi); kagit
satirlarindan kilit donemiyle kesisenler dusurulur (sayilir) ve ozellik penceresi 2026-11-01 sonrasinda olmalidir.
Cikti: `<out-dir>/M1@<tf>.json` (+ .prev.json yedek) ve `research/paper_models.csv`'ye tf basina bir satir.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_ml.pa_proposer import features as PF  # noqa: E402
from trader_ml.pa_proposer import labels as LB  # noqa: E402
from trader_ml.pa_proposer import package as PK  # noqa: E402
from trader_ml.pa_proposer import train as TR  # noqa: E402
from trader_ml.pa_proposer.train import KILIT_ACIK, LOCK_END, LOCK_START  # noqa: E402

TF_DELTA = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def load_bars(history_dir: str, base: str, tf: str):
    """-> (ts list[datetime], o, h, l, c) ya da None. Dosya adi: <BASE>_USDT_USDT-<tf>-futures.feather."""
    import pandas as pd
    hits = sorted(glob.glob(os.path.join(history_dir, f"{base}_USDT_USDT-{tf}-futures.feather")))
    if not hits:
        return None
    df = pd.read_feather(hits[0])
    ts = pd.to_datetime(df["date"], utc=True).dt.to_pydatetime()
    ts = [t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t for t in ts]
    return ts, df["open"].to_numpy(float), df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)


def _hist_rows(bars, pair_name: str, cutoff: datetime) -> list[dict]:
    """Tarihsel satirlar: kilit kapaliyken yalniz kilit baslangicinin ONCESI (bar dizisi kesilir); kilit aciksa kesim yok."""
    ts, o, h, l, c = bars
    if KILIT_ACIK:
        return LB.label_rows(o, h, l, c, ts)
    k = int(np.searchsorted(np.array([t.timestamp() for t in ts]), cutoff.timestamp(), side="left"))
    return LB.label_rows(o[:k], h[:k], l[:k], c[:k], ts[:k])


def _veri_penceresi() -> str:
    """CSV veri_penceresi alani: kilit acikken kesim yok."""
    return "hist=tum;paper=tum;kilit=acik" if KILIT_ACIK else f"hist<{LOCK_START.date()};paper>={LOCK_END.date()}"


def _paper_rows(recs: list[dict], bars_by: dict, tf: str, tf_delta: timedelta) -> tuple[list[dict], dict]:
    """Kagit kayitlari -> egitim satirlari. Bar eslesmesi: yalniz (bar_close_ts - tf) = sinyal mumunun ACILIS zamani."""
    stats = {"no_bar": 0, "no_window": 0, "bad": 0, "used": 0}
    out, idx_cache = [], {}
    for r in recs:
        if not str(r.get("arm_id", "")).endswith(f"@{tf}") or r.get("bar_close_ts") is None or r.get("side") not in PF.SIDE_SIGN:
            continue
        pair = r.get("pair")
        if pair not in bars_by:
            stats["no_bar"] += 1
            continue
        ts, o, h, l, c = bars_by[pair]
        t0 = datetime.fromisoformat(r["bar_close_ts"])
        t0 = t0.replace(tzinfo=timezone.utc) if t0.tzinfo is None else t0
        if pair not in idx_cache:
            idx_cache[pair] = {t: k for k, t in enumerate(ts)}
        idx = idx_cache[pair]
        i = idx.get(t0 - tf_delta)                           # bar_close_ts = kapanis; dosya 'date' = acilis (tam eslesme sonraki mumu secer)
        if i is None or i < PF.WINDOW - 1:
            stats["no_bar"] += 1
            continue
        if not KILIT_ACIK and ts[i - PF.WINDOW + 1] < LOCK_END:                 # ozellik penceresi de kilit sonrasi olmali
            stats["no_window"] += 1
            continue
        x = PF.feature_vector(o, h, l, c, i, r["side"])
        if x is None or r.get("r") is None:
            stats["bad"] += 1
            continue
        ots = datetime.fromisoformat(r["outcome_ts"]) if r.get("outcome_ts") else t0
        ots = ots.replace(tzinfo=timezone.utc) if ots.tzinfo is None else ots
        row = LB.paper_row(x, r["side"], ts[i], ots, float(r["r"]))
        if row is not None:
            out.append(row)
            stats["used"] += 1
    return out, stats


def main(argv=None, *, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pa_proposer_build.py")
    ap.add_argument("--history-dir", default="var/history")
    ap.add_argument("--paper-records", help="scripts/export_paper_records.py jsonl ciktisi")
    ap.add_argument("--pairs", help="virgulle ayrilmis taban semboller (ornek: BTC,ETH); varsayilan: history'deki hepsi")
    ap.add_argument("--tfs", default="1h,4h")
    ap.add_argument("--out-dir", default="models/pa_proposer")
    ap.add_argument("--paper-models-csv", default="research/paper_models.csv")
    ap.add_argument("--max-rows", type=int, default=TR.MAX_ROWS)
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    now = now or datetime.now(timezone.utc)
    hdir = _resolve(args.history_dir)
    tfs = [t.strip() for t in args.tfs.split(",") if t.strip()]
    if any(t not in TF_DELTA for t in tfs):
        print(f"gecersiz zaman dilimi: {tfs}", file=sys.stderr)
        return 1
    bases = [b.strip() for b in args.pairs.split(",")] if args.pairs else sorted(
        {os.path.basename(p).split("_USDT_USDT-")[0] for p in glob.glob(os.path.join(hdir, "*_USDT_USDT-*-futures.feather"))})
    recs = []
    if args.paper_records:
        with open(_resolve(args.paper_records), encoding="utf-8") as fh:
            recs = [json.loads(line) for line in fh if line.strip()]
    csvp = Path(_resolve(args.paper_models_csv))
    csvp.parent.mkdir(parents=True, exist_ok=True)
    summary = {}
    try:
        for tf in tfs:
            bars_by, hist, n_missing = {}, [], 0
            for b in bases:
                bars = load_bars(hdir, b, tf)
                if bars is None:
                    n_missing += 1
                    continue
                pair = f"{b}/USDT"
                bars_by[pair] = bars
                hist.extend(_hist_rows(bars, pair, LOCK_START))
            paper, pstats = _paper_rows(recs, bars_by, tf, TF_DELTA[tf])
            paper_kept, dropped = TR.split_lock(paper)
            rows = hist + paper_kept
            pkg = TR.train_tf(rows, arm_id=f"M1@{tf}", created_at=now, max_rows=args.max_rows)
            status = "no_model" if pkg is None else "ok"
            sha = ""
            if pkg is not None:
                PK.save_package(pkg, _resolve(args.out_dir))
                sha = pkg["meta"]["model_hash"]
            summary[tf] = {"status": status, "hist_rows": len(hist), "paper_rows": len(paper_kept), "paper_stats": pstats,
                           "lock_dropped": dropped, "pairs_missing": n_missing}
            new = not csvp.exists()
            with open(csvp, "a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["ad", "sinif", "tarif", "veri_penceresi", "commit", "sha256", "tarih"])
                w.writerow([f"m1_build_{tf}_{now.date().isoformat()}", "build",
                            f"ridge_logistic;M1@{tf};stop={PF.STOP_ATR};tp={PF.TARGET_ATR};h={PF.HORIZON};q={TR.THRESHOLD_Q}",
                            f"{_veri_penceresi()};rows={len(rows)};lock_dropped={dropped};status={status}",
                            "", sha, now.isoformat()])
    except (TR.LockWindowError, ValueError, OSError) as e:
        print(f"egitim hatasi: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    print(json.dumps({"status": "ok", "pairs": len(bases), "tfs": summary}, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
