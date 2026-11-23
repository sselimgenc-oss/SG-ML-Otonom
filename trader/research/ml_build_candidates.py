#!/usr/bin/env python3
"""ML 19b: tarihsel aday seti (NATIVE kip) -- motor backtester'indan (v1b = price_action_v1; kagit riski target_trade_risk=0.005).

Tarif `ml1-r01-v1b-native33`. KAYITLI ISTISNA: gercek borsa kurallari anlik goruntusu yok (bu ortam Binance'ten 451 aliyor);
kurallar `--synthetic-rules` ile YALNIZ 2026-05-01 oncesi mumlardan sentetik uretilir (min_notional: BTC 100, ETH 20, digerleri 5);
manifestte `rules_source: synthetic-preholdout`. Sunucuda gercek anlik goruntu gelince yalniz fark karsilastirmasi yapilir.
Kosu basinda git commit damgalanir; kirli agac reddedilir (yalniz research/ml/ ve research/logs/ altinda izlenmeyen dosya serbest).

Akis: (1) `trader_engine.backtest` ile [2024-11-01, 2026-05-01) araligini kosar (KILITLI DONEM 2026-05..10 okunmaz/kosulmaz),
(2) ledger'daki TUM karar olaylarini (alinan + atlanan; `v_decisions`) toplar, (3) alinan islemlerin GERCEK cikis zamani
ve net R'sini (`v_trades.r_multiple`: komisyon+kayma+funding sonrasi) yazar, (4) tum adaylara `trader_ml.labels`
ile uclu bariyer etiketi, (5) ozellikleri `trader_ml.features` (egitim hatti; canli ile ayni kod) ile uretir,
(6) `trader_ml.schema` semasinda parquet + damgali manifest yazar. Model egitilmez, kapi calistirilmaz.

Bellek: backtest ayri surec (stream); ozellik/etiket cift basina islenir, tum mumlar tutulmaz (tepe << 2 GB).

Kullanim (uzun kosu arka planda):
  PYTHONPATH=src nohup .venv/bin/python research/ml_build_candidates.py > research/logs/ml_build.log 2>&1 &
  --run-dir var/backtests/<id>   hazir bir kosuyu kullan (backtest'i atla)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_ml.config import BAR, DATA_START, HOLDOUT_START, KILIT_ACIK  # noqa: E402
from trader_ml.features import feature_frame  # noqa: E402
from trader_ml.guards import assert_pre_holdout  # noqa: E402
from trader_ml.labels import cost_in_r, label_candidates  # noqa: E402
from trader_ml.schema import REQUIRED, feature_columns, validate_candidates  # noqa: E402

RUN_ID = "ml_cand_v1b_native33"
RECIPE_ID = "ml1-r01-v1b-native33"
TARGET_TRADE_RISK = 0.005                         # kagit riski (backtest varsayilani 0.014 DEGIL); alinan/atlanan ayrimi kagidi yansitir
RULES_SOURCE = "synthetic-preholdout"
RULES_EXCEPTION = ("gercek borsa kurallari anlik goruntusu yok (bu ortam Binance'ten 451 aliyor); sentetik kurallar yalniz "
                   "2026-05-01 oncesi mumlardan, min_notional BTC 100 / ETH 20 / digerleri 5 (mentor karari, 17 Kasim 2026)")
ALLOWED_UNTRACKED = ("research/ml/", "research/logs/")
PERIOD = "20241101-20260501"                      # bitis dislayici = HOLDOUT_START
OUT_DIR = ROOT / "research" / "ml"
HISTORY = ROOT / "var" / "history"
BT_ARGS = ["--period", PERIOD, "--tf", "1h", "--fill-model", "native", "--strategy", "price_action_v1", "--synthetic-rules",
           "--target-trade-risk", str(TARGET_TRADE_RISK)]


def git_stamp(root: Path = ROOT) -> tuple[str, list[str]]:
    """(HEAD kisa commit, izin disi kirli yollar). Izinli: research/ml/ ve research/logs/ altinda IZLENMEYEN (??) dosyalar.
    Izlenen dosyada her degisiklik, baska yerde izlenmeyen dosya kirlidir."""
    def git(*a):
        r = subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"git basarisiz ({' '.join(a)}): {r.stderr.strip()}")
        return r.stdout
    commit = git("rev-parse", "--short=12", "HEAD").strip()
    prefix = git("rev-parse", "--show-prefix").strip()
    dirty = []
    for line in git("status", "--porcelain=v1", "--untracked-files=all").splitlines():
        code, path = line[:2], line[3:]
        rel = path[len(prefix):] if prefix and path.startswith(prefix) else path
        if code == "??" and rel.startswith(ALLOWED_UNTRACKED) and (not prefix or path.startswith(prefix)):
            continue
        dirty.append(line)
    return commit, dirty


def require_clean_tree(root: Path = ROOT) -> str:
    commit, dirty = git_stamp(root)
    if dirty:
        raise SystemExit("KIRLI AGAC: commit'lenmemis degisiklik var, derlem uretilmez:\n  " + "\n  ".join(dirty[:20]))
    return commit


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check_run_meta(run_dir: Path, commit: str) -> dict:
    """Hazir kosu (--run-dir) da kayitli kosulla ayni olmali: sentetik kural, kagit riski, ayni (temiz) commit."""
    meta = json.loads((run_dir / "meta.json").read_text())
    argv = meta.get("flags", {}).get("argv", [])
    if "--synthetic-rules" not in argv or meta.get("rules_source") != "synthetic":
        raise SystemExit("kosu --synthetic-rules ile degil")
    if "--target-trade-risk" not in argv or float(argv[argv.index("--target-trade-risk") + 1]) != TARGET_TRADE_RISK:
        raise SystemExit(f"kosu target_trade_risk={TARGET_TRADE_RISK} ile kosulmamis")
    gc = str(meta.get("git_commit", ""))
    if gc.endswith("+dirty") or not gc.startswith(commit[:7]):
        raise SystemExit(f"kosu commit'i ({gc}) baslangic damgasi ({commit}) ile uyusmuyor ya da kirli")
    return meta


def supersede_previous(out_dir: Path, name: str, superseded_by: str) -> list[str]:
    """Onceki derlemi SILMEDEN 'yerini aldi' isaretler: manifest -> *.superseded.json (+alan), parquet -> *.superseded.parquet."""
    moved = []
    man = out_dir / f"{name}.manifest.json"
    if man.exists():
        d = json.loads(man.read_text())
        if not d.get("superseded"):
            d.update(superseded=True, superseded_by=superseded_by,
                     superseded_reason="19b yeniden kurulumu (mentor, 17 Kasim 2026): kirli agac damgasi, spec disi --synthetic-rules "
                                       "(son 2000 mum kilitli doneme dokunuyordu), backtest riski 0.014")
            dst = out_dir / f"{name}.superseded.json"
            dst.write_text(json.dumps(d, indent=1, default=str))
            man.unlink()
            moved.append(dst.name)
    for suf in ("", "_prefiltered"):
        src = out_dir / f"{name}{suf}.parquet"
        if src.exists():
            dst = out_dir / f"{name}{suf}.superseded.parquet"
            if not dst.exists():
                src.rename(dst)
                moved.append(dst.name)
    return moved


def to_ml_pair(p: str) -> str:
    return p if ":" in p else f"{p}:{p.split('/')[1]}"


def load_pre_holdout_candles(pair: str) -> pd.DataFrame:
    """1s mumlar; kilitli donem satirlari DOSYA OKUMASINDA filtrelenir (hic yuklenmez)."""
    import pyarrow as pa
    import pyarrow.dataset as ds
    stem = pair.replace("/", "_").replace(":", "_")
    path = HISTORY / f"{stem}-1h-futures.feather"
    cut = pa.scalar(HOLDOUT_START.to_pydatetime(), type=pa.timestamp("ms", tz="UTC"))
    t = ds.dataset(str(path), format="feather").to_table(
        columns=["date", "open", "high", "low", "close", "volume"], filter=ds.field("date") < cut)
    df = t.to_pandas()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    assert_pre_holdout(df.index, f"{pair} mum")
    return df


def prefilter_rows(frame: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Yonu ve planli girisi olan TUM satirlar (sinyal True + stop_width gibi on-filtreyle elenenler); `signal` korunur.
    (`candidate_rows` yalniz sinyal True satirlari verir; ledger ise on-filtreyle elenenleri de karar olayi olarak yazar.)"""
    m = frame["side"].notna() & frame["planned_entry"].notna()
    r = frame[m].copy()
    r.insert(0, "pair", pair)
    r.insert(1, "ts", r.index + BAR)
    return r.reset_index(drop=True)


def run_backtest(run_dir: Path) -> None:
    cmd = [sys.executable, "-m", "trader_engine.backtest", "--id", run_dir.name, "--out-root", str(run_dir.parent), *BT_ARGS]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}
    print("backtest:", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit(f"backtest basarisiz (kod {r.returncode})")


def read_ledger(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    con = sqlite3.connect(f"file:{run_dir / 'ledger.sqlite'}?mode=ro", uri=True)
    try:
        dec = pd.read_sql("SELECT id, bar_close_ts, pair, side, setup, planned_entry, planned_stop, planned_target, "
                          "final_action, skip_reason FROM v_decisions", con)
        tr = pd.read_sql("SELECT decision_id, exit_ts, r_multiple, exit_reason FROM v_trades", con)
    finally:
        con.close()
    return dec, tr


def config_hash(run_dir: Path) -> tuple[str, dict]:
    meta = json.loads((run_dir / "meta.json").read_text())
    base = json.loads((ROOT / "config" / "engine.base.json").read_text())
    payload = {"engine_base": base, "cost": meta["cost"], "strategy": meta["strategy_label"], "tf": meta["trigger_tf"],
               "fill_model": meta["fill_model"], "granularity": meta["granularity"], "period": meta["period"],
               "rules_source": meta["rules_source"], "param_version_id": meta["param_version_id"],
               "bt_args": [a for a in meta["flags"]["argv"] if a not in ("--id", meta["id"])]}
    h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return h, payload


def build(run_dir: Path, out_name: str) -> tuple[pd.DataFrame, dict]:
    meta = json.loads((run_dir / "meta.json").read_text())
    if meta["fill_model"] != "native":
        raise SystemExit("yalniz native kip")
    end = pd.Timestamp(meta["period"][1])
    if not KILIT_ACIK and end > HOLDOUT_START:
        raise SystemExit(f"kosu kilitli doneme giriyor: {end}")
    dec, tr = read_ledger(run_dir)
    dec["ts"] = pd.to_datetime(dec["bar_close_ts"], utc=True)
    dec = dec[dec["final_action"].isin(["entered", "skipped"]) & dec["side"].notna() & dec["planned_entry"].notna()]
    dec = dec.merge(tr, how="left", left_on="id", right_on="decision_id")
    dec["pair_ml"] = dec["pair"].map(to_ml_pair)
    stats = {"decisions_total": int(len(dec)), "entered_total": int((dec["final_action"] == "entered").sum())}
    parts, per_pair, dropped = [], {}, {"before_data_start": 0, "taken_open_at_end": 0, "no_feature_row": 0}
    for pair, g in dec.groupby("pair_ml", sort=True):
        df = load_pre_holdout_candles(pair)
        frame = prefilter_rows(feature_frame(df, None, None), pair)
        feats = [c for c in frame.columns if c.startswith("f_")]
        g = g[g["ts"] >= DATA_START].copy()
        m = g.merge(frame[["ts", "side", "signal", *feats]], how="left", on=["ts", "side"], indicator=True)
        dropped["no_feature_row"] += int((m["_merge"] == "left_only").sum())
        m = m[m["_merge"] == "both"].drop(columns="_merge")
        taken = m["final_action"].eq("entered")
        open_end = taken & m["exit_ts"].isna()
        dropped["taken_open_at_end"] += int(open_end.sum())
        m = m[~open_end].copy()
        taken = m["final_action"].eq("entered")
        cands = pd.DataFrame({"ts": m["ts"].to_numpy(), "side": m["side"].to_numpy(), "planned_entry": m["planned_entry"].to_numpy(),
                              "planned_stop": m["planned_stop"].to_numpy(), "planned_target": m["planned_target"].to_numpy(float)},
                             index=m.index)
        lab = label_candidates(df, cands)
        out = pd.DataFrame(index=m.index)
        out["pair"] = pair
        out["ts"] = m["ts"]
        out["setup"] = m["setup"]
        out["side"] = m["side"]
        for c in ("planned_entry", "planned_stop", "planned_target"):
            out[c] = m[c].astype(float)
        out["source"] = "backtest"
        out["taken"] = taken
        out["label"] = lab["label"]
        out["label_end_ts"] = lab["label_end_ts"]
        # alinan: GERCEK cikis (motor ledger); alinmayan: referans cikis net R'si (basit kural; gercek cikis yok), exit_ts yok
        out["net_r"] = np.where(taken, m["r_multiple"], lab["net_r"])
        bad = out["net_r"].isna()                         # veri sonuna yakin: referans cikis cozulmedi -> aday cozulmemis sayilir
        out.loc[bad, "label"] = np.nan
        out.loc[bad, "label_end_ts"] = pd.NaT
        out["cost_r"] = cost_in_r(out["planned_entry"], out["planned_stop"])
        out["exit_ts"] = pd.to_datetime(m["exit_ts"], utc=True).where(taken)
        for c in feats:
            out[c] = m[c]
        out["ml_eligible"] = m["signal"].astype(bool)           # canlida ML'in puanlayacagi aday (strateji sinyali True)
        out["exit_reason"] = m["exit_reason"].where(taken)
        out["skip_reason"] = m["skip_reason"].where(~taken)
        parts.append(out)
        per_pair[pair] = {"taken": int(taken.sum()), "skipped": int((~taken).sum()),
                          "label_pos": int((out["label"] == 1).sum()), "label_neg": int((out["label"] == 0).sum()),
                          "label_unresolved": int(out["label"].isna().sum())}
        del df, frame
    t = pd.concat(parts, ignore_index=True)
    # sema disi yardimci sutunlar (exit_reason/skip_reason) yuklemeyi bozmaz ama ozellik degildir; sema dogrulamasi:
    t = validate_candidates(t)
    stats.update(dropped=dropped, per_pair_all_decisions=per_pair)
    return t, stats


def split_eligible(t: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ana set: canlida ML'in puanlayacagi adaylar (sinyal True: alinan + risk/emir reddi). On-filtreyle elenenler (stop_width)
    canlida ML'e hic gelmez; ayri dosyada tutulur (model/kapi bunlari gormez)."""
    e = t["ml_eligible"].astype(bool)
    return t[e].reset_index(drop=True), t[~e].reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("--out", default="candidates_v1b_native")
    a = ap.parse_args(argv)
    commit = require_clean_tree()                       # KOSU BASINDA damga + kirli agac reddi
    print(f"git commit (baslangic damgasi): {commit}; agac temiz", flush=True)
    run_dir = Path(a.run_dir) if a.run_dir else ROOT / "var" / "backtests" / RUN_ID
    if not (run_dir / "ledger.sqlite").exists():
        run_backtest(run_dir)
    check_run_meta(run_dir, commit)
    if git_stamp()[0] != commit or git_stamp()[1]:
        raise SystemExit("kosu sirasinda agac/commit degisti")
    t, stats = build(run_dir, a.out)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    superseded = supersede_previous(OUT_DIR, a.out, f"{a.out}.manifest.json ({RECIPE_ID}, commit {commit})")
    t_all = t
    t, pre = split_eligible(t_all)
    pq = OUT_DIR / f"{a.out}.parquet"
    t.to_parquet(pq, index=False)
    pre.to_parquet(OUT_DIR / f"{a.out}_prefiltered.parquet", index=False)
    meta = json.loads((run_dir / "meta.json").read_text())
    chash, payload = config_hash(run_dir)
    lab = t["label"].dropna()
    taken = t["taken"]
    manifest = {
        "recipe_id": RECIPE_ID, "target_trade_risk": TARGET_TRADE_RISK,
        "rules_source": RULES_SOURCE, "rules_exception": RULES_EXCEPTION,
        "git_commit_start": commit, "tree_clean_at_start": True, "run_id": run_dir.name,
        "sha256": {pq.name: sha256_file(pq), f"{a.out}_prefiltered.parquet": sha256_file(OUT_DIR / f"{a.out}_prefiltered.parquet")},
        "superseded_previous": superseded,
        "file": pq.name, "mode": "native", "source": "backtest", "schema": "trader_ml.schema (19b)",
        "engine_git_commit": meta["git_commit"], "engine_version": meta["engine_version"],
        "strategy": meta["strategy_label"], "config_hash_sha256": chash,
        "config": {k: payload[k] for k in ("cost", "tf", "fill_model", "granularity", "rules_source", "bt_args")},
        "backtest_period": meta["period"], "candidate_ts_min": str(t["ts"].min()), "candidate_ts_max": str(t["ts"].max()),
        "holdout_start": str(HOLDOUT_START), "holdout_read": False, "data_start": str(DATA_START),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(t)), "rows_all_decisions": int(len(t_all)), "taken": int(taken.sum()), "skipped": int((~taken).sum()),
        "label_balance": {"pos": int((lab == 1).sum()), "neg": int((lab == 0).sum()), "unresolved": int(t["label"].isna().sum()),
                          "pos_rate": round(float((lab == 1).mean()), 4)},
        "net_r_taken_mean": round(float(t.loc[taken, "net_r"].mean()), 4),
        "features": feature_columns(t), "n_features": len(feature_columns(t)),
        "extra_columns": [c for c in t.columns if not c.startswith("f_") and c not in REQUIRED],
        "notes": ["taken net_r = ledger r_multiple (komisyon+kayma+funding sonrasi, gercek cikis); skipped net_r = labels referans "
                  "cikisi (48 mum zaman cikisi / R1 hedefi; basit kural), exit_ts yok",
                  "alinan ama donem sonunda acik kalan islemler dislandi (exit_ts yok)",
                  "f_slope_1d: 1500 barlik canli pencereyle hesaplanir; BTC/ETH/funding/f_bars_since_exit aktif listede yok (karar 2a)",
                  "compat capraz dogrulamasi native davranisi degistirirse yeniden uretilir (karar 4)"],
        "per_pair": {k: {"taken": int(g["taken"].sum()), "skipped": int((~g["taken"]).sum()),
                         "label_pos": int((g["label"] == 1).sum()), "label_neg": int((g["label"] == 0).sum())}
                     for k, g in t.groupby("pair")},
        "prefiltered_file": f"{a.out}_prefiltered.parquet", "prefiltered_rows": int(len(pre)),
        "prefiltered_skip_reasons": pre["skip_reason"].value_counts().to_dict(),
        "skip_reasons_main": t.loc[~taken, "skip_reason"].value_counts().to_dict(),
        **stats,
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
    }
    (OUT_DIR / f"{a.out}.manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    print(json.dumps({k: manifest[k] for k in ("rows", "taken", "skipped", "label_balance", "dropped", "prefiltered_rows",
                                               "per_pair", "peak_rss_mb")}, default=str),
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
