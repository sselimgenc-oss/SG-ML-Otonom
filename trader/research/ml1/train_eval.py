#!/usr/bin/env python3
"""ML1 egitim + degerlendirme: aday tablosu -> ozellikler -> walk-forward + holdout -> rapor (md + json) + model paketi.

  python research/ml1/train_eval.py --table var/ml1 --out var/ml1_out --hist-dir var/history [--holdout-months 3]

  --hist-dir  pa_/reg_/vol_ mum ozellikleri icin tarihsel mumlar (yoksa yalniz konfluans/grup/tf/yon ozellikleri; kalan NaN->0 olur)
Ciktilar: <out>/ml1_report.md, ml1_report.json, ml1_package.json."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from trader_ml.ml1 import data as D
from trader_ml.ml1 import evaluate as EV
from trader_ml.ml1 import features as FE
from trader_ml.ml1 import model as M
from trader_ml.ml1 import train as TR
from trader_ml.ml1.table import CandidateTable


def load_features(table_dir: str, hist_dir: str | None) -> pd.DataFrame:
    c = CandidateTable(table_dir).read()
    if len(c) == 0:
        return c
    lookup = None
    if hist_dir:
        cache: dict = {}

        def lookup(pair: str, tf: str):
            if (pair, tf) not in cache:
                cache[(pair, tf)] = D.load_pair_tf(hist_dir, pair, tf)
            return cache[(pair, tf)]
    return FE.build_features(c, lookup)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hist-dir", default=None)
    ap.add_argument("--holdout-months", type=int, default=3)
    ap.add_argument("--test-months", type=int, default=3)
    ap.add_argument("--min-train-months", type=int, default=6)
    ap.add_argument("--min-trades", type=int, default=200)
    a = ap.parse_args(argv)
    df = load_features(a.table, a.hist_dir)
    if len(df) == 0:
        print("tablo bos")
        return 1
    res = TR.run(df, holdout_months=a.holdout_months, test_months=a.test_months, min_train_months=a.min_train_months,
                 min_trades=a.min_trades)
    rep = EV.build_report(res)
    _jp, mp = EV.write_report(rep, a.out)
    if res["package"] is not None:
        M.save_package(res["package"], Path(a.out) / "ml1_package.json")
    v, h = rep["verdict"], rep["holdout"]
    print(f"karar: {v['verdict']} ({'; '.join(v['reasons'])})")
    print(f"ridge={rep['ridge']} esik={rep['threshold']} OOS ML: {rep['oos'].get('ml')}")
    print(f"holdout ML: {h.get('ml')}  rapor: {mp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
