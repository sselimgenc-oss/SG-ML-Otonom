#!/usr/bin/env python3
"""ML1 egitim + degerlendirme: aday tablosu -> ozellikler -> walk-forward + holdout -> rapor (md + json) + model paketi.

  python research/ml1/train_eval.py --table var/ml1 --out var/ml1_out --hist-dir var/history [--holdout-months 3]

  --hist-dir  pa_/reg_/vol_ mum ozellikleri icin tarihsel mumlar (yoksa yalniz konfluans/grup/tf/yon ozellikleri; kalan NaN->0 olur)
Ciktilar: <out>/ml1_report.md, ml1_report.json, ml1_package.json."""
from __future__ import annotations

import argparse
import json
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


def _lookup_factory(hist_dir: str | None):
    """Cift basina mum arama fonksiyonu (cift bitince mumlar serbest kalir)."""
    if not hist_dir:
        return None

    def factory(pair: str):
        cache: dict = {}

        def lookup(p: str, tf: str):
            if (p, tf) not in cache:
                cache[(p, tf)] = D.load_pair_tf(hist_dir, p, tf)
            return cache[(p, tf)]
        return lookup
    return factory


def load_features(table_dir: str, hist_dir: str | None, feat_dir: str | None = None) -> pd.DataFrame:
    """Bellek-dostu ozellik kurulumu: cift (tum tf) basina kur -> slim (float32) -> `feat_dir`'e parquet (yeniden calistirmada atlanir)."""
    ct = CandidateTable(table_dir)
    names = sorted({p.parent.parent.name[5:] for p in ct.files()})
    if not names:
        return pd.DataFrame()
    factory = _lookup_factory(hist_dir)
    fd = Path(feat_dir) if feat_dir else None
    key = FE.cache_meta(table_dir, hist_dir)
    done: set[str] = set()
    if fd is not None:
        fd.mkdir(parents=True, exist_ok=True)
        mp = fd / "meta.json"
        old = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
        if old.get("key") == key:
            done = {n for n in old.get("done", []) if (fd / f"{n}.parquet").exists()}
        else:
            for f in fd.glob("*.parquet"):
                f.unlink()
    parts: list[pd.DataFrame] = []
    for i, n in enumerate(names):
        if n in done:
            print(f"[ozellik] {n}: onbellekten", flush=True)
            continue
        c = ct.read(pairs=[n])
        pair = str(c["pair"].iloc[0]) if len(c) else n
        # event_id cifte ozgu (anahtar pair|side|tf); cifter arasi benzersiz kalsin diye deterministik offset (cift sirasi * 1e9)
        s = FE.build_features_chunked([c], factory)
        del c
        if hist_dir:
            D.kaynak(hist_dir)._cache.clear()
        s["event_id"] = s["event_id"] + i * 1_000_000_000
        if fd is not None:
            s.to_parquet(fd / f"{n}.parquet", index=False)
            done.add(n)
            (fd / "meta.json").write_text(json.dumps({"key": key, "done": sorted(done)}), encoding="utf-8")
        else:
            parts.append(s)
        print(f"[ozellik] {n}: {len(s)} satir", flush=True)
        del s
    if fd is not None:
        parts = [pd.read_parquet(fd / f"{n}.parquet") for n in names]
    return FE.assemble(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hist-dir", default=None)
    ap.add_argument("--feat-dir", default=None, help="ozellik onbellegi (cift basina parquet); varsa ozellik kurulumu atlanir")
    ap.add_argument("--holdout-months", type=int, default=3)
    ap.add_argument("--test-months", type=int, default=3)
    ap.add_argument("--min-train-months", type=int, default=6)
    ap.add_argument("--min-trades", type=int, default=200)
    a = ap.parse_args(argv)
    df = load_features(a.table, a.hist_dir, a.feat_dir)
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
