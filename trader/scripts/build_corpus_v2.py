#!/usr/bin/env python3
"""ML-G6: Derlem v2 kurulumu (19b ile AYNI aday kodu, uzun donem). Model egitilmez, kapi calistirilmaz.

Ne uretir (`--out-dir`, varsayilan research/ml; ad `--name`, varsayilan corpus_v2):
  <name>.parquet                 aday tablosu (satir = yerel v1b aday: post_filter ONCESI, iki yon, 10 cift)
  <name>.manifest.json           girdi dosya sha256'lari, kod commit'i, satir sayilari, etiket cozulme, ozellik NaN oranlari, derlem sha256
  <name>.sample_check.md         (yalniz --sample-check N) elle kontrol icin N rastgele etiketli aday + mum pencereleri

Aday tanimi (ml-guclendirme-plani 3.2.1 madde 5, G5): `trader_ml.features.feature_frame` + `candidate_rows` (19b kodu, DEGISMEDEN)
-> signal True ve setup == T1 (v1b `setups_enabled`), strateji `post_filter` (ayni mumda stop ile cikis yeniden giris engeli)
UYGULANMAZ: motorun yerel aday kumesi ("pre-post_filter native"). Boylece `f_same_bar_signals` (ayni ts'de ayri cift sayisi)
motorun iki gecisli degerlendirmesiyle ayni sayida mum/aday uzerinden hesaplanir. Alinmis/alinmamis ayrimi YOKTUR (taken/net_r
yok): etiketler yalniz fiyat bariyerleridir (`trader_ml.labels.multi_r_labels`: 1R / 1.5R / 2R, 72 mum, stop once).
Ozellikler `trader_ml.features_v2.feature_frame_v2` (kilitli donem korumali sarmalayici): r02 (40) + r03'un ek 3 sutunu
(`f_btc_vr`, `f_btc_vol_1d_pct90`, `f_side_x_btc_slope_1d`); ortak sutunlar r02/r03'te birebir ayni olmak zorunda (kosuda dogrulanir).
Fonlama: `<PAIR>-1h-funding_rate.feather` (var/history). Kaynak sutunu: `source = "native_v1b"`.

KILITLI DONEM: bitis > 2026-05-01 ise SERT RED (trader_engine.holdout + trader_ml.guards). Mum/fonlama dosyalari okunurken
>= 2026-05-01 satirlar dosya okumasinda filtrelenir (hic yuklenmez). Son 72 mumun etiketi (ufuk kilitli doneme tasar) cozulmemis (NaN) kalir.

Bellek (sunucu 2 GB): cift cift (sinyal + etiket, aday satirlari tutulur, mum cercevesi birakilir); ozellikler yil yil
(ayni ts'nin adaylari ayni parcada), her yil parquet'e satir grubu olarak akitilir. Tepe RSS manifestte (`peak_rss_mb`).

Kullanim (sunucu komutu docs/sunucu-kurulum.md "Derlem v2" bolumunde):
  PYTHONPATH=src .venv/bin/python scripts/build_corpus_v2.py [--start 2021-01-01] [--end 2026-05-01] [--sample-check 50]
  --allow-dirty  (yalniz yerel duman kosusu; sunucu kosusu temiz agac ister)   --skip-build  (yalniz --sample-check, var olan derlem)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_engine.holdout import BacktestArgError, check_holdout  # noqa: E402
from trader_ml.config import BAR, HORIZON_BARS, HOLDOUT_START, KILIT_ACIK  # noqa: E402
from trader_ml.features import candidate_rows, feature_frame  # noqa: E402
from trader_ml.features_v2 import R02_FEATURE_NAMES, R03_FEATURE_NAMES  # noqa: E402
from trader_ml.features_v2 import feature_frame_v2 as guarded_v2  # noqa: E402
from trader_ml.features_v2 import CORE_SOURCE_FILE  # noqa: E402
from trader_ml.guards import HoldoutViolation, assert_pre_holdout  # noqa: E402
from trader_ml.labels import cost_in_r, multi_r_labels  # noqa: E402

CORPUS_VERSION = "corpus_v2"
SOURCE = "native_v1b"
SETUPS = ("T1",)                                   # v1b setups_enabled (price_action_v1.make_v1b)
TARGET_RS = (1.0, 1.5, 2.0)
R_TAGS = ("1r", "1p5r", "2r")
DEFAULT_START = pd.Timestamp("2021-01-01", tz="UTC")
DEFAULT_END = HOLDOUT_START                         # dislayici
PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT",
         "DOGE/USDT:USDT", "ADA/USDT:USDT", "TRX/USDT:USDT", "LINK/USDT:USDT", "AVAX/USDT:USDT"]
R03_EXTRA = [c for c in R03_FEATURE_NAMES if c not in R02_FEATURE_NAMES]
FEATURE_COLUMNS = list(R02_FEATURE_NAMES) + R03_EXTRA
BASE_COLUMNS = ["pair", "ts", "setup", "side", "planned_entry", "planned_stop", "planned_target", "source", "cost_r"]
LABEL_COLUMNS = [f"{k}_{t}" for t in R_TAGS for k in ("label", "label_end_ts", "barrier_net_r")]
CORPUS_COLUMNS = BASE_COLUMNS + LABEL_COLUMNS + FEATURE_COLUMNS
CODE_FILES = ["scripts/build_corpus_v2.py", "research/ml_build_candidates.py", "src/trader_ml/features.py",
              "src/trader_ml/features_v2.py", "src/trader_ml/labels.py", "src/trader_ml/guards.py", "src/trader_ml/config.py",
              "src/trader_core/ml_features.py", "src/trader_core/signals.py",
              "src/trader_core/regime.py", "src/trader_core/indicators.py", "src/trader_engine/holdout.py"]


# ------------------------------------------------------------------ yardimcilar
def _load_19b():
    """19b derleyicisinin yardimcilari (sha256_file, git_stamp, to_ml_pair) AYNEN yeniden kullanilir."""
    spec = importlib.util.spec_from_file_location("ml_build_candidates_19b", ROOT / "research" / "ml_build_candidates.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_B19 = _load_19b()
sha256_file = _B19.sha256_file
git_stamp = _B19.git_stamp


def stem(pair: str) -> str:
    return pair.replace("/", "_").replace(":", "_")


def check_period(start: pd.Timestamp, end: pd.Timestamp) -> None:
    """Sert red: bitis kilitli doneme (>= 2026-05-01) giriyorsa. start < end zorunlu."""
    if not KILIT_ACIK and end > HOLDOUT_START:
        raise HoldoutViolation(f"bitis {end} kilitli donem sinirini ({HOLDOUT_START}) asiyor; derlem uretilmez")
    if not start < end:
        raise SystemExit(f"--start ({start}) --end ({end}) oncesinde olmali")
    try:
        check_holdout(start.to_pydatetime(), end.to_pydatetime())
    except BacktestArgError as e:                                 # motor tarafi kilidi (ikinci, bagimsiz kontrol)
        raise HoldoutViolation(str(e)) from e


def _read_feather(path: Path, columns: list[str], end: pd.Timestamp) -> pd.DataFrame:
    """Kilitli donem satirlari DOSYA OKUMASINDA filtrelenir (date < end; end <= HOLDOUT_START)."""
    import pyarrow as pa
    import pyarrow.dataset as ds
    cut = pa.scalar(end.to_pydatetime(), type=pa.timestamp("ms", tz="UTC"))
    t = ds.dataset(str(path), format="feather").to_table(columns=columns, filter=ds.field("date") < cut)
    df = t.to_pandas()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df.set_index("date").sort_index()


def load_candles(hist: Path, pair: str, end: pd.Timestamp) -> pd.DataFrame:
    df = _read_feather(hist / f"{stem(pair)}-1h-futures.feather", ["date", "open", "high", "low", "close", "volume"], end)
    df = df[~df.index.duplicated(keep="last")]
    assert_pre_holdout(df.index, f"{pair} mum")
    return df


def load_funding(hist: Path, pair: str, end: pd.Timestamp) -> pd.DataFrame:
    f = _read_feather(hist / f"{stem(pair)}-1h-funding_rate.feather", ["date", "funding_rate"], end)
    assert_pre_holdout(f.index, f"{pair} fonlama")
    return f


def frame_hash(df: pd.DataFrame) -> str:
    """Kullanilan dilimin deger karmasi (dosyanin kilitli doneme ait baytlarindan bagimsiz)."""
    h = pd.util.hash_pandas_object(df, index=True).to_numpy()
    return hashlib.sha256(h.tobytes()).hexdigest()


def content_hash(df: pd.DataFrame) -> str:
    """Parquet surumunden bagimsiz, satir degerlerine dayanan karma (NaN ve NaT sabit kodlanir)."""
    d = df.copy()
    for c in d.columns:
        if str(d[c].dtype).startswith("datetime64"):
            d[c] = d[c].astype("int64")
    h = pd.util.hash_pandas_object(d, index=False).to_numpy()
    return hashlib.sha256(h.tobytes()).hexdigest()


# ------------------------------------------------------------------ 1. faz: aday + etiket (cift cift)
def native_candidates(df: pd.DataFrame, pair: str) -> pd.DataFrame:
    """19b aday kodu: feature_frame + candidate_rows (DEGISMEDEN); v1b setup suzgeci; post_filter UYGULANMAZ."""
    c = candidate_rows(feature_frame(df, None, None), pair)
    c = c[c["setup"].isin(SETUPS)]
    keep = ["pair", "ts", "setup", "side", "planned_entry", "planned_stop", "planned_target"]
    return c[keep].reset_index(drop=True)


def phase1(hist: Path, pairs: list[str], start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    parts, info = [], {}
    for p in pairs:
        df = load_candles(hist, p, end)
        gaps = int((df.index.to_series().diff().dropna() != BAR).sum())
        c = native_candidates(df, p)
        c = c[(c["ts"] >= start) & (c["ts"] < end)].reset_index(drop=True)   # ts < end: kapanis kilitli donemde olamaz
        lab = multi_r_labels(df, c, target_rs=TARGET_RS, horizon=HORIZON_BARS)
        out = c.assign(source=SOURCE)
        out["planned_target"] = out["planned_target"].astype(float)
        out["cost_r"] = cost_in_r(out["planned_entry"], out["planned_stop"])
        out = pd.concat([out, lab], axis=1)
        parts.append(out)
        info[p] = {"candle_rows": int(len(df)), "candle_first": str(df.index.min()), "candle_last": str(df.index.max()),
                   "candle_gaps": gaps, "slice_sha256": frame_hash(df)}
        del df
    t = pd.concat(parts, ignore_index=True)
    t = t.sort_values(["ts", "pair"], kind="mergesort").reset_index(drop=True)
    return t, info


# ------------------------------------------------------------------ 2. faz: ozellikler (yil yil)
def features_for(frames: dict[str, pd.DataFrame], funding: dict[str, pd.DataFrame], cands: pd.DataFrame) -> pd.DataFrame:
    """Korumali sarmalayici: r02 (40) + r03 ek 3 sutun. Ortak sutunlar iki tarifte birebir ayni olmali."""
    a = guarded_v2(frames, cands, funding=funding, recipe="r02")
    b = guarded_v2(frames, cands, funding=funding, recipe="r03")
    for c in b.columns:
        if c in a.columns and not np.array_equal(a[c].to_numpy(float), b[c].to_numpy(float), equal_nan=True):
            raise SystemExit(f"r02/r03 ortak ozellik {c} ayrisiyor; derlem uretilmez")
    out = a.copy()
    for c in R03_EXTRA:
        out[c] = b[c]
    out.attrs["funding_stale"] = a.attrs.get("funding_stale", 0)
    return out[FEATURE_COLUMNS]


def _arrow_schema(df: pd.DataFrame):
    import pyarrow as pa
    return pa.Schema.from_pandas(df, preserve_index=False)


def write_corpus(t: pd.DataFrame, frames, funding, pq_path: Path, chunk: str = "year") -> dict:
    """Yil yil ozellik + parquet satir grubu (akitma). Doner: ozellik NaN sayaclari ve bayat fonlama toplami."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    tmp = pq_path.with_suffix(".parquet.part")
    years = t["ts"].dt.year.to_numpy()
    nan_tot = {c: 0 for c in FEATURE_COLUMNS}
    nan_year, rows_year, stale = {}, {}, 0
    writer = None
    try:
        for y in sorted(set(years.tolist())):
            sub = t[years == y].reset_index(drop=True)
            f = features_for(frames, funding, sub[["pair", "ts", "side", "planned_entry", "planned_stop"]])
            stale += int(f.attrs.get("funding_stale", 0))
            sub = pd.concat([sub, f], axis=1)[CORPUS_COLUMNS]
            nan_year[int(y)] = {c: int(sub[c].isna().sum()) for c in FEATURE_COLUMNS}
            rows_year[int(y)] = int(len(sub))
            for c in FEATURE_COLUMNS:
                nan_tot[c] += nan_year[int(y)][c]
            tab = pa.Table.from_pandas(sub, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(str(tmp), tab.schema, compression="zstd", use_dictionary=True, write_statistics=True)
            writer.write_table(tab, row_group_size=len(sub) or 1)
            del sub, f, tab
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        raise SystemExit("hic aday yok; derlem bos")
    tmp.replace(pq_path)
    return {"nan_total": nan_tot, "nan_by_year": nan_year, "rows_by_year": rows_year, "funding_stale": stale}


# ------------------------------------------------------------------ manifest
def label_stats(t: pd.DataFrame) -> dict:
    out = {}
    for tag in R_TAGS:
        lab = t[f"label_{tag}"]
        out[tag] = {"pos": int((lab == 1).sum()), "neg": int((lab == 0).sum()), "unresolved": int(lab.isna().sum()),
                    "pos_rate": round(float((lab == 1).sum() / max(int(lab.notna().sum()), 1)), 4)}
    return out


def build_manifest(*, args, t: pd.DataFrame, pq_path: Path, hist: Path, pairs: list[str], info: dict, wr: dict,
                   commit: str, dirty: list[str], t0: float) -> dict:
    n = max(len(t), 1)
    years = t["ts"].dt.year
    per_pair_year = {p: {int(y): int(k) for y, k in g.groupby(g["ts"].dt.year).size().items()} for p, g in t.groupby("pair")}
    inputs = {}
    for p in pairs:
        for kind in ("1h-futures", "1h-funding_rate"):
            f = hist / f"{stem(p)}-{kind}.feather"
            inputs[f.name] = {"bytes": f.stat().st_size, "sha256": sha256_file(f)}
    ct = pd.read_parquet(pq_path)
    peak = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    sbs = t.groupby("ts")["pair"].nunique()
    return {
        "corpus_version": CORPUS_VERSION, "recipe_ids": ["ml1-r02-long-ctx-1r", "ml1-r03-long-regime8"], "source": SOURCE,
        "candidate_definition": "pre-post_filter native v1b: feature_frame+candidate_rows (19b), signal True, setup T1, post_filter YOK; iki yon; 10 cift",
        "period": {"start": str(args.start), "end_exclusive": str(args.end), "holdout_start": str(HOLDOUT_START),
                   "holdout_read": False, "ts_min": str(t["ts"].min()), "ts_max": str(t["ts"].max())},
        "pairs": pairs, "horizon_bars": HORIZON_BARS, "target_rs": list(TARGET_RS),
        "git": {"commit": commit, "dirty": dirty, "tree_clean": not dirty},
        "code_sha256": {**{f: sha256_file(ROOT / f) for f in CODE_FILES},
                        str(Path(CORE_SOURCE_FILE).resolve().relative_to(ROOT)): sha256_file(Path(CORE_SOURCE_FILE))},
        "env": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                "pyarrow": __import__("pyarrow").__version__},
        "inputs_sha256": inputs, "input_slices": info,
        "corpus": {"file": pq_path.name, "sha256": sha256_file(pq_path), "content_sha256": content_hash(ct),
                   "bytes": pq_path.stat().st_size},
        "rows": int(len(t)), "rows_per_pair": {k: int(v) for k, v in t.groupby("pair").size().items()},
        "rows_per_year": wr["rows_by_year"], "rows_per_pair_year": per_pair_year,
        "label_resolution": label_stats(t),
        "label_resolution_by_year": {int(y): label_stats(g) for y, g in t.groupby(years)},
        "columns": list(ct.columns), "feature_columns": FEATURE_COLUMNS, "n_features": len(FEATURE_COLUMNS),
        "r02_features": list(R02_FEATURE_NAMES), "r03_features": list(R03_FEATURE_NAMES),
        "feature_nan_rate": {c: round(v / n, 6) for c, v in wr["nan_total"].items()},
        "feature_nan_rate_by_year": {y: {c: round(v / max(wr["rows_by_year"][y], 1), 6) for c, v in d.items()}
                                     for y, d in wr["nan_by_year"].items()},
        "funding_stale_count": wr["funding_stale"],
        "same_bar": {"rows_unique_pair_ts": bool(not t.duplicated(["pair", "ts"]).any()),
                     "max_distinct_pairs_at_ts": int(sbs.max()) if len(sbs) else 0,
                     "feature_matches_distinct_pairs": bool(np.array_equal(
                         ct["f_same_bar_signals"].to_numpy(float), t.groupby("ts")["pair"].transform("nunique").to_numpy(float)))},
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime_s": round(time.time() - t0, 1), "peak_rss_mb": peak,
        "chunking": "cift cift (faz 1), yil yil (faz 2, parquet satir grubu)",
    }


# ------------------------------------------------------------------ 50 etiket elle kontrol
def _independent_label(h, l, c, side, e, s, r, horizon):
    """Kasitli olarak labels.py'den bagimsiz, duz dongu: (label|None, bitis konumu|None)."""
    rr = abs(e - s)
    sgn = 1.0 if side == "long" else -1.0
    up = e + sgn * r * rr
    n = len(h)
    for i in range(min(horizon, n)):
        stop = (l[i] <= s) if side == "long" else (h[i] >= s)
        hit = (h[i] >= up) if side == "long" else (l[i] <= up)
        if stop:
            return 0.0, i
        if hit:
            return 1.0, i
    if n >= horizon:
        return 0.0, horizon - 1
    return None, None


def sample_check(t: pd.DataFrame, hist: Path, end: pd.Timestamp, n: int, seed: int, md_path: Path, manifest_rel: str) -> dict:
    ok = t[[f"label_{g}" for g in R_TAGS]].notna().all(axis=1)
    pool = t[ok]
    if len(pool) == 0:
        raise SystemExit("etiketi tam cozulmus aday yok")
    pick = pool.sample(n=min(n, len(pool)), random_state=seed).sort_values(["ts", "pair"])
    candles, lines, agree, total = {}, [], 0, 0
    lines += [f"# Derlem v2: {len(pick)} etiket elle kontrol (seed {seed})", "",
              f"Derlem: `{manifest_rel}`; aday ts = sinyal mumunun KAPANISI; bariyerler ts'den itibaren sonraki {HORIZON_BARS} mumda taranir "
              "(ayni mumda stop ve hedef birlikte degerse STOP once). Kontrol: her mum icin tabloda bariyer temaslari isaretli; "
              "'bagimsiz yeniden hesap' labels.py'den ayri duz bir dongudur. Elle kontrol sonucunu her baslikta `[ ]` kutusuna isaretleyin.", ""]
    for k, (_, r) in enumerate(pick.iterrows(), 1):
        if r["pair"] not in candles:
            candles[r["pair"]] = load_candles(hist, r["pair"], end)
        df = candles[r["pair"]]
        p = df.index.searchsorted(r["ts"] - BAR)
        e, s, side = float(r["planned_entry"]), float(r["planned_stop"]), r["side"]
        rr, sgn = abs(e - s), (1.0 if side == "long" else -1.0)
        win = df.iloc[p + 1:p + 1 + HORIZON_BARS]
        h, l, c = (win[x].to_numpy(float) for x in ("high", "low", "close"))
        lines += [f"## {k}. {r['pair']} {side} ts={r['ts']:%Y-%m-%d %H:%M} UTC  [ ] elle dogru  [ ] hatali", "",
                  f"giris {e:.6g}, stop {s:.6g}, R = {rr:.6g}; "
                  + ", ".join(f"{tag.upper()} hedef {e + sgn * rv * rr:.6g}" for tag, rv in zip(R_TAGS, TARGET_RS)), ""]
        res = []
        for tag, rv in zip(R_TAGS, TARGET_RS):
            lab, j = _independent_label(h, l, c, side, e, s, rv, HORIZON_BARS)
            got = float(r[f"label_{tag}"])
            got_end = pd.Timestamp(r[f"label_end_ts_{tag}"])
            exp_end = (win.index[j] + BAR) if j is not None else None
            same = lab == got and exp_end == got_end
            agree += int(same)
            total += 1
            res.append(f"{tag.upper()}: derlem label={got:g} bitis={got_end:%m-%d %H:%M}; bagimsiz label={lab} "
                       f"bitis={'-' if exp_end is None else format(exp_end, '%m-%d %H:%M')} -> {'UYUMLU' if same else 'FARKLI'}")
        lines += ["- " + x for x in res] + [""]
        ctx = df.iloc[max(p - 3, 0):p + 1]
        lines += ["| mum acilis | rol | high | low | close | stop | 1R | 1.5R | 2R |", "|---|---|---|---|---|---|---|---|---|"]
        for ix, row in ctx.iterrows():
            lines.append(f"| {ix:%m-%d %H:%M} | {'SINYAL' if ix == df.index[p] else 'once'} | {row.high:.6g} | {row.low:.6g} | {row.close:.6g} | | | | |")
        ends = [pd.Timestamp(r[f"label_end_ts_{g}"]) - BAR for g in R_TAGS]
        last = max(ends)
        for i, (ix, row) in enumerate(win.iterrows(), 1):
            if ix > last:
                break
            sh = (row.low <= s) if side == "long" else (row.high >= s)
            marks = []
            for rv in TARGET_RS:
                up = e + sgn * rv * rr
                marks.append("x" if ((row.high >= up) if side == "long" else (row.low <= up)) else "")
            lines.append(f"| {ix:%m-%d %H:%M} | +{i} | {row.high:.6g} | {row.low:.6g} | {row.close:.6g} | {'x' if sh else ''} | "
                         f"{marks[0]} | {marks[1]} | {marks[2]} |")
        lines.append("")
    lines += ["## Ozet", "", f"Bagimsiz yeniden hesap uyumu: {agree}/{total} (etiket + bitis zamani).", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"sample_n": int(len(pick)), "agree": agree, "total": total, "path": str(md_path)}


# ------------------------------------------------------------------ ana akis
def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default=str(DEFAULT_START.date()))
    ap.add_argument("--end", default=str(DEFAULT_END.date()), help="dislayici; 2026-05-01'den buyukse SERT RED")
    ap.add_argument("--history-dir", default=str(ROOT / "var" / "history"))
    ap.add_argument("--out-dir", default=str(ROOT / "research" / "ml"))
    ap.add_argument("--name", default=CORPUS_VERSION)
    ap.add_argument("--pairs", default=",".join(PAIRS))
    ap.add_argument("--sample-check", type=int, default=0, metavar="N", help="N rastgele etiketli aday icin Markdown dosyasi")
    ap.add_argument("--seed", type=int, default=20261117)
    ap.add_argument("--skip-build", action="store_true", help="derlemi yeniden uretme; var olan derlemle yalniz --sample-check")
    ap.add_argument("--allow-dirty", action="store_true", help="kirli agac izni (yalniz yerel duman kosusu)")
    a = ap.parse_args(argv)
    a.start, a.end = pd.Timestamp(a.start, tz="UTC"), pd.Timestamp(a.end, tz="UTC")
    check_period(a.start, a.end)
    pairs = [p.strip() for p in a.pairs.split(",") if p.strip()]
    for need in ("BTC/USDT:USDT", "ETH/USDT:USDT"):
        if need not in pairs:
            raise SystemExit(f"{need} cift listesinde olmali (v2 baglam ozellikleri)")
    hist, out_dir = Path(a.history_dir), Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pq_path, man_path = out_dir / f"{a.name}.parquet", out_dir / f"{a.name}.manifest.json"
    t0 = time.time()
    if not a.skip_build:
        commit, dirty = git_stamp()
        if dirty and not a.allow_dirty:
            raise SystemExit("KIRLI AGAC: commit'lenmemis degisiklik var, derlem uretilmez (yerel duman icin --allow-dirty):\n  "
                             + "\n  ".join(dirty[:20]))
        print(f"commit {commit}; dirty={len(dirty)}; {a.start.date()} .. {a.end.date()} (dislayici)", flush=True)
        t, info = phase1(hist, pairs, a.start, a.end)
        print(f"faz1: {len(t)} aday ({time.time() - t0:.0f} s)", flush=True)
        frames = {p: load_candles(hist, p, a.end) for p in pairs}
        funding = {p: load_funding(hist, p, a.end) for p in pairs}
        wr = write_corpus(t, frames, funding, pq_path)
        del frames, funding
        man = build_manifest(args=a, t=t, pq_path=pq_path, hist=hist, pairs=pairs, info=info, wr=wr, commit=commit, dirty=dirty, t0=t0)
        man_path.write_text(json.dumps(man, indent=1, sort_keys=True, default=str), encoding="utf-8")
        print(json.dumps({k: man[k] for k in ("rows", "rows_per_year", "label_resolution", "funding_stale_count", "runtime_s",
                                              "peak_rss_mb")}, default=str), flush=True)
        print(f"corpus sha256 {man['corpus']['sha256']}", flush=True)
    if a.sample_check:
        if not pq_path.exists():
            raise SystemExit("derlem yok; once derleyin")
        t = pd.read_parquet(pq_path)
        res = sample_check(t, hist, a.end, a.sample_check, a.seed, out_dir / f"{a.name}.sample_check.md", pq_path.name)
        print("sample-check:", json.dumps(res), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(run())
