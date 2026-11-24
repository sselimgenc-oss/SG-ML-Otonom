#!/usr/bin/env python3
"""Gece egitimi (DD-12 WP-18: M1). gece, zamanlayici deploy/trader-ml-retrain.timer (00:40 UTC), tek oneshot birim (MemoryMax).

M1 (`trader_ml.pa_proposer`, WP-18 (b)): tarihsel barlar (`var/history`; kilit kapaliyken kilit baslangicindan ONCE kesilir, KILIT_ACIK iken kesim yok) + kagit
kayitlari (`scripts/export_paper_records.py` ile AYNI disa aktarma: kilit penceresiyle kesisen satirlar dusurulur) ->
`var/learner/models/pa_proposer/M1@<tf>.json` (+ `.prev.json`). Bellek: ciftbasina kuyruk (tavan 50 000 satir; spec §5.2), feather
pyarrow ile okunur. Olcum (WP-18): tepe RSS ~263 MB; pandas `trader_core.indicators` (dondurulmus) uzerinden gelir
(~100 MB). Sert tavan: deploy/trader-ml-retrain.service MemoryMax=350M.
Her zaman dilimi `var/learner/paper_models.csv`'ye satir ekler.
Ciktilar YALNIZ calisma zamani dizinine yazilir (git-izli dosya asla degismez); okuyucular once calisma zamani dizinine,
sonra depodaki tohum paketlere (`models/pa_proposer/`, `research/paper_models.csv`) bakar. Kilit kapaliyken kilit donemi (2026-05-01..2026-11-01) egitime GIRMEZ (23.11 karari: KILIT_ACIK=True, kesim yok).
Cikis: 0 basarili (model olusmayan kol hata degil: `ml_no_model`); 1 kullanim; 3 defter acilamadi/yazma/egitim hatasi.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))                       # export_paper_records (scripts/)
sys.path.insert(0, str(_HERE.parent / "research"))   # pa_proposer_build (research/): tarihsel etiket + kagit satiri yardimcilari

from trader_core import ledger as L  # noqa: E402
from trader_ml.pa_proposer import package as PK  # noqa: E402
from trader_ml.pa_proposer import train as TR  # noqa: E402
from trader_ml.pa_proposer.train import KILIT_ACIK, LOCK_START  # noqa: E402


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


PB_TFS = ("15m", "1h", "4h", "1d")
M1_TFS = ("1h", "4h", "15m", "1d")    # config/engine.paper.json M1@1h, M1@4h, M1@15m, M1@1d
M1_MAX_ROWS = 50_000                  # gece tavani (spec §5.2: "tavan 50 bin satir"); ciftbasina kuyruk = 50 000 / cift sayisi


def _load_bars(history_dir: str, base: str, tf: str):
    """`PB.load_bars` ile ayni cikti (ts, o, h, l, c) ama pandas YOK (pyarrow ~54 MB, pandas ~100 MB): bellek butcesi icin."""
    import glob

    import numpy as np
    import pyarrow.feather as pf

    hits = sorted(glob.glob(os.path.join(history_dir, f"{base}_USDT_USDT-{tf}-futures.feather")))
    if not hits:
        return None
    t = pf.read_table(hits[0], columns=["date", "open", "high", "low", "close"])
    ms = t.column("date").cast("int64").to_numpy(zero_copy_only=False)
    unit = t.schema.field("date").type.unit
    ms = {"ms": ms, "s": ms * 1000, "us": ms // 1000, "ns": ms // 1_000_000}[unit]
    ts = [datetime.fromtimestamp(int(x) / 1000.0, tz=timezone.utc) for x in ms]
    arr = {n: t.column(n).to_numpy(zero_copy_only=False).astype(np.float64) for n in ("open", "high", "low", "close")}
    return ts, arr["open"], arr["high"], arr["low"], arr["close"]


def _hist_tail(bars, pair: str, cap: int, cutoff: datetime) -> list[dict]:
    """Kilit oncesi tarihsel satirlarin SON `cap` tanesi, yalniz gerekli bar dilimi etiketlenerek (bellek).

    Ozellik penceresi (WINDOW) geriye, etiket ufku (HORIZON) ileriye bakar; dilim `s = k - cap/2 - 70` ile baslar, boylece
    dilimdeki her satir tam gecmis penceresiyle ayni degerleri verir (tam etiketlemeyle bit bit ayni). Kesim `cutoff` oncesi."""
    import numpy as np

    from trader_ml.pa_proposer import labels as LB

    ts, o, h, l, c = bars
    k = len(ts) if KILIT_ACIK else int(np.searchsorted(np.array([t.timestamp() for t in ts]), cutoff.timestamp(), side="left"))
    s0 = max(0, k - cap // 2 - 70)
    rows = LB.label_rows(o[s0:k], h[s0:k], l[s0:k], c[s0:k], ts[s0:k])
    return rows[-cap:]


def _m1_tf(tf, recs, bases, *, history_dir, models_dir, now, max_rows, csv_rows, PB) -> dict:
    bars_by: dict = {}
    for b in bases:
        bars = _load_bars(history_dir, b, tf)
        if bars is not None:
            bars_by[f"{b}/USDT"] = bars
    cap = max(1, max_rows // max(1, len(bars_by)))
    hist: list = []
    for pair, bars in bars_by.items():
        hist.extend(_hist_tail(bars, pair, cap, LOCK_START))          # kilit oncesi; ciftbasina kuyruk
    paper, pstats = PB._paper_rows(recs, bars_by, tf, PB.TF_DELTA[tf])
    paper_kept, dropped = TR.split_lock(paper)
    rows = hist + paper_kept
    pkg = TR.train_tf(rows, arm_id=f"M1@{tf}", created_at=now, max_rows=max_rows)
    sha = ""
    if pkg is not None:
        PK.save_package(pkg, models_dir)
        sha = pkg["meta"]["model_hash"]
    status = "no_model" if pkg is None else "ok"
    reason = None
    if pkg is None:   # paket yok: nedeni gorunur yap ("model yok: N örnek, en az M"); esik uydurulmaz
        ys = {float(r["y"]) for r in rows}
        reason = TR.no_model_reason(len(rows), len(ys) if rows else None)
    res = {"status": status, "hist_rows": len(hist), "paper_rows": len(paper_kept), "lock_dropped": dropped,
               "paper_stats": pstats, "pairs": len(bars_by), "reason": reason}
    if csv_rows is not None:
        csv_rows.append([f"m1_nightly_{tf}_{now.date().isoformat()}", "nightly_m1",
                         f"ridge_logistic;M1@{tf};stop={PB.PF.STOP_ATR};tp={PB.PF.TARGET_ATR};h={PB.PF.HORIZON};q={TR.THRESHOLD_Q}",
                         f"{PB._veri_penceresi()};rows={len(rows)};lock_dropped={dropped};status={status}" + (f";{reason}" if reason else ""),
                         "", sha, now.isoformat()])
    del rows, hist, paper, paper_kept, pkg, bars_by
    return res


def m1_nightly(led, cf_path: str | None, *, history_dir: str, tfs, models_dir: str, now: datetime, max_rows: int = M1_MAX_ROWS,
               csv_rows: list | None = None) -> dict:
    """M1 (her zaman dilimi) gece egitimi. Kilit sonrasi kagit kayitlari + kilit oncesi tarihsel barlar; kilit disi tutulur.

    Bellek: tarihsel satirlar ciftbasina kuyrukla (son `max_rows // ciftSayisi`, bkz. `_hist_tail`) sinirlanir; tum gecmis
    etiketlenmez. Kagit satirlari dogrudan eklenir (az sayida). Donus: {tf: {status, rows, ...}} (sha256 `csv_rows`'a)."""
    import glob

    import export_paper_records as EPR  # noqa: E402  (scripts/)
    import pa_proposer_build as PB  # noqa: E402  (research/): _paper_rows, TF_DELTA (pandas'siz)

    recs, _ = EPR.export(led, cf_path if cf_path and os.path.exists(cf_path) else None)
    bases = sorted({os.path.basename(p).split("_USDT_USDT-")[0]
                    for p in glob.glob(os.path.join(history_dir, "*_USDT_USDT-*-futures.feather"))})
    out: dict = {}
    for tf in tfs:
        try:
            out[tf] = _m1_tf(tf, recs, bases, history_dir=history_dir, models_dir=models_dir, now=now, max_rows=max_rows,
                             csv_rows=csv_rows, PB=PB)
        except Exception as e:  # noqa: BLE001 - bir zaman diliminin hatasi digerlerini durdurmaz; durum 'error' (saglik gorunur)
            reason = f"{type(e).__name__}: {str(e)[:120]}"
            print(f"M1 {tf} egitim hatasi: {reason}", file=sys.stderr)
            out[tf] = {"status": "error", "reason": reason}
            if csv_rows is not None:
                csv_rows.append([f"m1_nightly_{tf}_{now.date().isoformat()}", "nightly_m1",
                                 f"ridge_logistic;M1@{tf}", f"status=error;{reason}", "", "", now.isoformat()])
    return out


def main(argv=None, *, now_fn=None, env=None) -> int:
    ap = argparse.ArgumentParser(prog="ml_retrain_run.py")
    ap.add_argument("--once", action="store_true", required=True)
    ap.add_argument("--ledger")
    ap.add_argument("--cf")
    ap.add_argument("--paper-models-csv", default="var/learner/paper_models.csv")
    ap.add_argument("--history-dir", default="var/history")
    ap.add_argument("--m1-models-dir", default="var/learner/models/pa_proposer")
    ap.add_argument("--m1-tfs", default=",".join(M1_TFS))
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    env = os.environ if env is None else env
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    lp = _resolve(args.ledger or env.get("LEDGER_PATH") or "var/learner/ledger.sqlite")
    cf = _resolve(args.cf) if args.cf else str(Path(lp).with_name("counterfactual.sqlite"))
    try:
        led = L.open_ledger(lp, "learner", create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        print(f"defter acilamadi: {type(e).__name__}", file=sys.stderr)
        return 3
    csv_rows: list = []
    m1: dict = {}
    m1_err: str | None = None
    try:
        tfs = [t.strip() for t in args.m1_tfs.split(",") if t.strip()]
        if any(t not in PB_TFS for t in tfs):
            print(f"gecersiz M1 zaman dilimi: {tfs}", file=sys.stderr)
            return 1
        try:   # M1 hatasi cikis kodu 3 (saglik alarmi); paper_models.csv satirlari yine yazilir
            m1 = m1_nightly(led, cf, history_dir=_resolve(args.history_dir), tfs=tfs,
                            models_dir=_resolve(args.m1_models_dir), now=now, max_rows=M1_MAX_ROWS, csv_rows=csv_rows)
        except Exception as e:  # noqa: BLE001
            m1_err = f"{type(e).__name__}: {e}"
            print(f"M1 egitim hatasi: {m1_err}", file=sys.stderr)
        failed = sorted(t for t, v in m1.items() if isinstance(v, dict) and v.get("status") == "error")
        if failed and m1_err is None:
            m1_err = f"tf hatasi: {','.join(failed)}"          # cikis kodu 3 (saglik gorunurlugu); digerleri egitildi
        csvp = Path(_resolve(args.paper_models_csv))
        csvp.parent.mkdir(parents=True, exist_ok=True)
        new = not csvp.exists()
        with open(csvp, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["ad", "sinif", "tarif", "veri_penceresi", "commit", "sha256", "tarih"])
            w.writerows(csv_rows)
    except Exception as e:  # noqa: BLE001
        print(f"egitim hatasi: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        led.close()
    print(json.dumps({"status": "ok" if m1_err is None else "m1_error", "m1": m1, "m1_error": m1_err}, sort_keys=True, default=str))
    return 0 if m1_err is None else 3


if __name__ == "__main__":
    sys.exit(main())
