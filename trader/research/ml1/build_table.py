#!/usr/bin/env python3
"""ML1 aday tablosunu kurar / yeni mumlarla uzatir (parquet pair/tf/ay + manifest.json).

  python research/ml1/build_table.py --hist-dir var/history --out var/ml1 --tf 1h,4h --pairs BTC/USDT,ETH/USDT --since 2021-01-01

  --pairs   virgullu liste ya da `all` (config/engine.paper.json `pairs`); verisi olmayan cift atlanir
  --since   yalniz ILK kurulumda alt sinir (decision_ts >= since); sonraki calistirmalar manifest'ten devam eder
  --force   secili cift x tf'yi silip bastan tara
  --no-exit cikis simulasyonunu atla (trader_ml.ml1.exitsim varsa varsayilan: bos cikis satirlari simule edilir)
Kol kaynaklari/parametreler degisirse (arms_hash) tum tablo otomatik yeniden kurulur."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from trader_ml.ml1 import build as B  # noqa: E402
from trader_ml.ml1 import data as D  # noqa: E402
from trader_ml.ml1.table import CandidateTable  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tf", default=",".join(D.TFS))
    ap.add_argument("--pairs", default="all")
    ap.add_argument("--since", default=None)
    ap.add_argument("--until", default=None, help="dislayici UTC tarih (veri bu tarihe kadar yuklenir)")
    ap.add_argument("--hist-dir", default=str(ROOT / "var" / "history"))
    ap.add_argument("--out", default=str(ROOT / "var" / "ml1"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-exit", action="store_true")
    a = ap.parse_args(argv)
    tfs = [x for x in a.tf.split(",") if x]
    bad = [t for t in tfs if t not in D.TFS]
    if bad:
        ap.error(f"gecersiz tf: {bad}")
    if a.pairs == "all":
        pairs = json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))["pairs"]
    else:
        pairs = [x for x in a.pairs.split(",") if x]
    since = pd.Timestamp(a.since, tz="UTC") if a.since else None
    until = pd.Timestamp(a.until, tz="UTC").to_pydatetime() if a.until else None
    t0 = time.time()
    res = B.build(CandidateTable(a.out), a.hist_dir, pairs, tfs, since=since, until=until, force=a.force, simulate=not a.no_exit)
    print(f"bitti: {sum(r['new'] for r in res)} yeni aday, {len(res)} cift x tf, {time.time() - t0:.0f} sn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
