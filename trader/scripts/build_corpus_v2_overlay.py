#!/usr/bin/env python3
"""Alinan-islem / gercek net R katmani (on kayit docs/ml/r02-r03-on-kayit.md 2.2). Model egitilmez, kapi calistirilmaz.

Motor backtest'i 19b ile AYNI ayarlarla kosulur (`--tf 1h --fill-model native --strategy price_action_v1 --synthetic-rules
--target-trade-risk 0.005`), YALNIZ donem 20210101-20260501 (dislayici; kilitli donem SERT RED). Defterden (`v_decisions`,
`v_trades`) `final_action == "entered"` kararlari alinir; esleme anahtari (pair, ts = bar_close_ts, side).

Cikti (`--out-dir`, varsayilan research/ml): `corpus_v2_taken.parquet` (alinmis kararlar: pair, ts, side, setup, exit_ts, r_multiple, ...)
ve `corpus_v2_taken.manifest.json` (sha256, config_hash, commit, alinan/alinmayan sayilari, ESLESMEYEN ALINMIS sayisi, donem sonu acik).
Butunluk sarti: defterde alinmis olup derlemde karsiligi olmayan islem = 0; degilse dosyalar yazilir ama cikis kodu 3 (kosu baslamaz).
Koruma (mentor karari 18 Kasim 2026, BT-1): manifeste `taken_per_fold` (r02 penceresi `recipes._WF_V2`, 4 dilim; fold, test_start,
test_end, taken), `taken_per_year`, `first_entry_ts`, `last_entry_ts` ve `gate_closed_skips` (defter kararlarinda
skip_reason == 'entry_gate_closed' sayisi, veto_reason'a gore) yazilir. Herhangi bir sinav diliminde alinan 0 ise ya da
gate_closed_skips bos degilse dosyalar yine yazilir ama cikis kodu 4 (GUARD_EXIT); ikisi birden olursa 3 oncelikli.
Cikis kodlari: 0 tamam; 3 eslesmeyen alinmis islem; 4 bos sinav dilimi / entry_gate_closed atlamasi.
Temiz agac zorunlu (19b git_stamp). Kullanim: PYTHONPATH=src .venv/bin/python scripts/build_corpus_v2_overlay.py [--run-dir DIR]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import resource
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_engine.holdout import BacktestArgError, check_holdout  # noqa: E402
from trader_ml import corpus_v2  # noqa: E402
from trader_ml.config import HOLDOUT_START, KILIT_ACIK  # noqa: E402
from trader_ml.guards import HoldoutViolation, assert_pre_holdout  # noqa: E402
from trader_ml.recipes import _WF_V2  # noqa: E402
from trader_ml.walkforward import make_folds  # noqa: E402


def _load_19b():
    spec = importlib.util.spec_from_file_location("ml_build_candidates_19b_overlay", ROOT / "research" / "ml_build_candidates.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_B19 = _load_19b()
sha256_file = _B19.sha256_file
read_ledger = _B19.read_ledger
config_hash = _B19.config_hash
to_ml_pair = _B19.to_ml_pair
git_stamp = _B19.git_stamp

RUN_ID = "corpus_v2_taken_v1b_native"
PERIOD = "20210101-20260501"                       # bitis dislayici = HOLDOUT_START
TARGET_TRADE_RISK = _B19.TARGET_TRADE_RISK
KEY = ["pair", "ts", "side"]
OUT_NAME = "corpus_v2_taken"
UNMATCHED_EXIT = 3
GUARD_EXIT = 4
GATE_CLOSED = "entry_gate_closed"


def bt_args(period: str = PERIOD) -> list[str]:
    """19b BT_ARGS aynen; yalniz donem degisir."""
    a = list(_B19.BT_ARGS)
    a[a.index("--period") + 1] = period
    return a


def check_period(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Kilitli doneme giren donem SERT RED; kayitli donemden baska donem de red."""
    try:
        s, e = (pd.Timestamp(x, tz="UTC") for x in period.split("-"))
    except Exception as ex:
        raise SystemExit(f"--period 'YYYYMMDD-YYYYMMDD' olmali: {period!r} ({ex})")
    if not KILIT_ACIK and e > HOLDOUT_START:
        raise HoldoutViolation(f"bitis {e} kilitli donem sinirini ({HOLDOUT_START}) asiyor; katman uretilmez")
    try:
        check_holdout(s.to_pydatetime(), e.to_pydatetime())            # motor tarafi kilidi (ikinci, bagimsiz kontrol)
    except BacktestArgError as ex:
        raise HoldoutViolation(str(ex)) from ex
    if period != PERIOD:
        raise SystemExit(f"donem on kayitla ayni olmali ({PERIOD}); verilen {period}")
    return s, e


def run_argv_matches(argv: list[str]) -> bool:
    """Kosunun bayraklari (--id/--out-root cikarilarak) kayitli bt_args() ile BIREBIR ayni mi (fazla/eksik bayrak = hayir)."""
    a, out, i = list(argv), [], 0
    while i < len(a):
        if a[i] in ("--id", "--out-root"):
            i += 2
            continue
        out.append(a[i])
        i += 1
    return out == bt_args()


def run_backtest(run_dir: Path) -> None:
    import os
    import subprocess
    cmd = [sys.executable, "-m", "trader_engine.backtest", "--id", run_dir.name, "--out-root", str(run_dir.parent), *bt_args()]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    print("backtest:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit(f"backtest basarisiz (kod {r.returncode})")


def entered_table(dec: pd.DataFrame, tr: pd.DataFrame) -> pd.DataFrame:
    """Defterden alinmis kararlar (final_action == entered) + gercek cikis; anahtar (pair, ts, side)."""
    d = dec[dec["final_action"].eq("entered") & dec["side"].notna()].copy()
    d = d.merge(tr, how="left", left_on="id", right_on="decision_id")
    out = pd.DataFrame({
        "pair": d["pair"].map(to_ml_pair).to_numpy(), "ts": pd.to_datetime(d["bar_close_ts"], utc=True).to_numpy(),
        "side": d["side"].to_numpy(), "setup": d["setup"].to_numpy(), "decision_id": d["id"].to_numpy(),
        "exit_ts": pd.to_datetime(d["exit_ts"], utc=True).to_numpy(), "r_multiple": d["r_multiple"].astype(float).to_numpy(),
        "exit_reason": d["exit_reason"].to_numpy()})
    if out.duplicated(KEY).any():
        raise SystemExit("defterde (pair, ts, side) tekrarli alinmis karar")
    return out.sort_values(["ts", "pair", "side"], kind="mergesort").reset_index(drop=True)


def match_counts(entered: pd.DataFrame, corpus_keys: pd.DataFrame) -> dict:
    ck = pd.MultiIndex.from_frame(corpus_keys[KEY])
    hit = pd.MultiIndex.from_frame(entered[KEY]).isin(ck)
    n_corpus = int(len(corpus_keys))
    open_end = entered["exit_ts"].isna()
    return {"corpus_rows": n_corpus, "entered_total": int(len(entered)), "taken_matched": int(hit.sum()),
            "skipped": n_corpus - int(hit.sum()), "unmatched_entered": int((~hit).sum()),
            "taken_open_at_end": int(open_end.sum()), "taken_missing_r": int((entered["exit_ts"].notna() & entered["r_multiple"].isna()).sum())}


def read_gate_closed(run_dir: Path) -> dict[str, int]:
    """Defter kararlarinda skip_reason == 'entry_gate_closed' sayisi, veto_reason'a gore (bos/NULL -> 'none')."""
    import sqlite3
    con = sqlite3.connect(f"file:{run_dir / 'ledger.sqlite'}?mode=ro", uri=True)
    try:
        try:
            rows = con.execute("SELECT veto_reason, COUNT(*) FROM v_decisions WHERE skip_reason = ? GROUP BY veto_reason",
                               (GATE_CLOSED,)).fetchall()
        except sqlite3.OperationalError as ex:
            raise SystemExit(f"defter v_decisions.veto_reason okunamadi: {ex}") from ex
    finally:
        con.close()
    out: dict[str, int] = {}
    for vr, n in rows:
        k = str(vr) if vr else "none"
        out[k] = out.get(k, 0) + int(n)
    return dict(sorted(out.items()))


def taken_stats(ent: pd.DataFrame) -> dict:
    """Yalniz ts ve alinan sayisindan: r02 penceresinde dilim basina, yil basina alinan; ilk/son giris ts."""
    w = _WF_V2
    empty = pd.DataFrame({"ts": pd.to_datetime([], utc=True), "label_end_ts": pd.to_datetime([], utc=True)})
    folds = make_folds(empty, train_bars=w["train_bars"], test_bars=w["test_bars"], step_bars=w["step_bars"],
                       min_test_bars=w["min_test_bars"], start=w["start"], end=w["end"])
    ts = pd.to_datetime(ent["ts"], utc=True)
    per_fold = [{"fold": int(f["fold"]), "test_start": f["test_start"].isoformat(), "test_end": f["test_end"].isoformat(),
                 "taken": int(((ts >= f["test_start"]) & (ts < f["test_end"])).sum())} for f in folds]
    per_year = {str(k): int(v) for k, v in ts.dt.year.value_counts().sort_index().items()}
    return {"taken_per_fold": per_fold, "taken_per_year": per_year,
            "first_entry_ts": ts.min().isoformat() if len(ts) else None, "last_entry_ts": ts.max().isoformat() if len(ts) else None}


def guard_failures(stats: dict, gate_closed: dict) -> list[str]:
    msgs = [f"sinav dilimi {f['fold']} ({f['test_start'][:10]}..{f['test_end'][:10]}) alinan islem 0" for f in stats["taken_per_fold"] if f["taken"] <= 0]
    if len(stats["taken_per_fold"]) != 4:
        msgs.append(f"sinav dilimi sayisi 4 degil: {len(stats['taken_per_fold'])}")
    if gate_closed:
        msgs.append(f"entry_gate_closed atlamasi var (bos olmali): {gate_closed}")
    return msgs


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--period", default=PERIOD)
    ap.add_argument("--run-dir", default=None, help="hazir backtest kosusu (yoksa var/backtests/%s kosulur)" % RUN_ID)
    ap.add_argument("--corpus", default=str(ROOT / "research" / "ml" / "corpus_v2.parquet"))
    ap.add_argument("--corpus-manifest", default=None, help="derlem manifesti (varsayilan: derlemin yaninda <corpus adi>.manifest.json)")
    ap.add_argument("--out-dir", default=str(ROOT / "research" / "ml"))
    a = ap.parse_args(argv)
    check_period(a.period)                                           # kilitli donem: ledger'a/backtest'e dokunmadan SERT RED
    commit, dirty = git_stamp()
    if dirty:
        raise SystemExit("KIRLI AGAC: commit'lenmemis degisiklik var, katman uretilmez:\n  " + "\n  ".join(dirty[:20]))
    print(f"commit {commit}; agac temiz; donem {a.period}", flush=True)
    corpus = Path(a.corpus)
    if not corpus.exists():
        raise SystemExit(f"derlem yok: {corpus}")
    cman = Path(a.corpus_manifest) if a.corpus_manifest else corpus.with_name(corpus.stem + ".manifest.json")
    if not cman.exists():
        raise SystemExit(f"derlem manifesti yok: {cman}")
    cerrs, _ = corpus_v2.verify_corpus_manifest(corpus_v2.load_manifest(cman), corpus)       # UZUN backtest'ten ONCE (sha256 + code_sha256)
    if cerrs:
        raise SystemExit("derlem manifesti dogrulanamadi, backtest baslatilmaz:\n  " + "\n  ".join(cerrs))
    run_dir = Path(a.run_dir) if a.run_dir else ROOT / "var" / "backtests" / RUN_ID
    if not (run_dir / "ledger.sqlite").exists():
        run_backtest(run_dir)
    meta = _B19.check_run_meta(run_dir, commit)                      # sentetik kural, kagit riski, ayni temiz commit
    p0, p1 = (pd.Timestamp(x, tz="UTC") for x in meta["period"])
    if p0 != pd.Timestamp("2021-01-01", tz="UTC") or p1 != HOLDOUT_START or meta["fill_model"] != "native":
        raise SystemExit(f"kosu donemi/kipi on kayda uymuyor (tam 2021-01-01..{HOLDOUT_START:%Y-%m-%d} olmali): {meta['period']} {meta['fill_model']}")
    if not run_argv_matches(meta.get("flags", {}).get("argv", [])):
        raise SystemExit(f"kosu bayraklari kayitli bt_args() ile ayni degil: {meta.get('flags', {}).get('argv')} != {bt_args()}")
    if git_stamp()[0] != commit or git_stamp()[1]:
        raise SystemExit("kosu sirasinda agac/commit degisti")
    dec, tr = read_ledger(run_dir)
    ent = entered_table(dec, tr)
    assert_pre_holdout(ent["ts"], "katman ts")
    assert_pre_holdout(ent["exit_ts"].dropna(), "katman exit_ts")
    stats = taken_stats(ent)
    gate_closed = read_gate_closed(run_dir)
    ckeys = pd.read_parquet(corpus, columns=KEY)
    ckeys["ts"] = pd.to_datetime(ckeys["ts"], utc=True)
    cnt = match_counts(ent, ckeys)
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pq = out_dir / f"{OUT_NAME}.parquet"
    ent.to_parquet(pq, index=False)
    chash, payload = config_hash(run_dir)
    man = {"overlay_version": "corpus_v2_taken", "file": pq.name, "sha256": sha256_file(pq), "period": f"{p0:%Y%m%d}-{p1:%Y%m%d}",
           "corpus_file": corpus.name, "corpus_sha256": sha256_file(corpus),
           "git": {"commit": commit, "tree_clean": True}, "run_id": run_dir.name,
           "engine_git_commit": meta["git_commit"], "engine_version": meta["engine_version"],
           "strategy": meta["strategy_label"], "config_hash": chash,
           "config": {k: payload[k] for k in ("cost", "tf", "fill_model", "granularity", "rules_source", "bt_args")},
           "rules_source": _B19.RULES_SOURCE, "rules_exception": _B19.RULES_EXCEPTION, "target_trade_risk": TARGET_TRADE_RISK,
           "backtest_period": meta["period"], "holdout_read": False, **cnt, **stats, "gate_closed_skips": gate_closed,
           "exit_reasons": {str(k): int(v) for k, v in ent["exit_reason"].value_counts().items()},
           "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}
    (out_dir / f"{OUT_NAME}.manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps({k: man[k] for k in ("sha256", "config_hash", *cnt)}, default=str), flush=True)
    if cnt["unmatched_entered"] > 0:
        print(f"REDDEDILDI: derlemde karsiligi olmayan alinmis islem {cnt['unmatched_entered']} (0 olmali); mentor inceler", file=sys.stderr)
        return UNMATCHED_EXIT
    gf = guard_failures(stats, gate_closed)
    if gf:
        print("REDDEDILDI (koruma): " + "; ".join(gf) + "; mentor inceler", file=sys.stderr)
        return GUARD_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(run())
