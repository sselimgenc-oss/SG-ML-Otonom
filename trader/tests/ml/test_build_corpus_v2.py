"""ML-G6: scripts/build_corpus_v2.py -- yalniz sentetik veri (tmp_path); gercek var/history okunmaz, ag yok."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core.ml_features import BAR
from trader_core.ml_live_v2 import LiveContextV2
from trader_ml.features import candidate_rows, feature_frame
from trader_ml.features_v2 import feature_frame_v2 as guarded_v2
from trader_ml.fixture import synthetic_candles
from trader_ml.guards import HoldoutViolation
from trader_ml.labels import multi_r_labels

from trader_engine.holdout import HOLDOUT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PAIRS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT"]
START = pd.Timestamp("2025-06-01", tz="UTC")
END = pd.Timestamp(HOLDOUT[0])                     # kilitli donem baslangici (sabitten)


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("build_corpus_v2", ROOT / "scripts" / "build_corpus_v2.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus_v2"] = m
    spec.loader.exec_module(m)
    return m


def _write_history(hist: Path, candles, *, with_holdout_rows: bool) -> None:
    hist.mkdir(parents=True, exist_ok=True)
    for k, (p, df) in enumerate(candles.items()):
        rate = np.random.default_rng(100 + k).normal(0.0001, 0.0002, 5000)       # uzunluktan bagimsiz (ayni olaylar, ek kilitli olaylar sonda)
        d = df.copy()
        if with_holdout_rows:                                   # dosyada kilitli doneme ait satirlar VAR (sunucuda da olabilir)
            tail = d.iloc[-200:].copy()
            tail.index = tail.index + pd.Timedelta(hours=200)
            d = pd.concat([d, tail * 1.3])
        d.reset_index().rename(columns={"index": "date"}).to_feather(hist / f"{p.replace('/', '_').replace(':', '_')}-1h-futures.feather")
        ft = pd.date_range(START, END - pd.Timedelta(hours=8) + pd.Timedelta(days=5 if with_holdout_rows else 0), freq="8h", tz="UTC")
        pd.DataFrame({"date": ft, "funding_rate": rate[:len(ft)]}).to_feather(
            hist / f"{p.replace('/', '_').replace(':', '_')}-1h-funding_rate.feather")


@pytest.fixture(scope="module")
def candles():
    return synthetic_candles(PAIRS, start=START)


@pytest.fixture(scope="module")
def built(mod, candles, tmp_path_factory):
    """Iki ayri derleme (ikincisinde dosyalarda kilitli donem satirlari da var) + sample-check."""
    base = tmp_path_factory.mktemp("g6")
    out = {}
    for tag, hold in (("a", False), ("b", True)):
        hist = base / f"hist_{tag}"
        _write_history(hist, candles, with_holdout_rows=hold)
        od = base / f"out_{tag}"
        args = ["--history-dir", str(hist), "--out-dir", str(od), "--pairs", ",".join(PAIRS), "--allow-dirty"]
        if tag == "a":
            args += ["--sample-check", "50"]
        assert mod.run(args) == 0
        out[tag] = {"hist": hist, "dir": od, "man": json.loads((od / "corpus_v2.manifest.json").read_text()),
                    "table": pd.read_parquet(od / "corpus_v2.parquet")}
    return out


# ------------------------------------------------------------------ kilitli donem
def test_holdout_refusal(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    for end in ((END + pd.Timedelta(days=1)).strftime("%Y-%m-%d"), pd.Timestamp(HOLDOUT[1]).strftime("%Y-%m-%d"), "2027-01-01"):
        with pytest.raises(HoldoutViolation):
            mod.run(["--end", end, "--history-dir", str(tmp_path), "--out-dir", str(tmp_path / "o")])
    assert not (tmp_path / "o" / "corpus_v2.parquet").exists()
    mod.check_period(pd.Timestamp("2021-01-01", tz="UTC"), END)     # dislayici sinir serbest
    with pytest.raises(SystemExit):
        mod.check_period(pd.Timestamp("2026-04-01", tz="UTC"), pd.Timestamp("2026-03-01", tz="UTC"))


def test_holdout_rows_in_files_are_never_used(built):
    a, b = built["a"], built["b"]
    assert b["man"]["period"]["ts_max"] < END.strftime("%Y-%m-%d")
    assert b["man"]["period"]["holdout_read"] is False
    pd.testing.assert_frame_equal(a["table"], b["table"], check_exact=True)               # ek kilitli satirlar sonucu degistirmez
    assert a["man"]["input_slices"] == {p: {**v, "candle_rows": v["candle_rows"]} for p, v in b["man"]["input_slices"].items()}
    # dosya baytlari farkli (sha256 girdileri farkli) ama kullanilan dilim ayni
    assert a["man"]["inputs_sha256"] != b["man"]["inputs_sha256"]


# ------------------------------------------------------------------ manifest
def test_manifest_complete(mod, built):
    m, t = built["a"]["man"], built["a"]["table"]
    for k in ("corpus_version", "git", "code_sha256", "inputs_sha256", "corpus", "rows", "rows_per_pair", "rows_per_year",
              "rows_per_pair_year", "label_resolution", "feature_nan_rate", "feature_nan_rate_by_year", "period", "pairs",
              "peak_rss_mb", "runtime_s", "feature_columns", "same_bar", "funding_stale_count"):
        assert k in m, k
    assert m["git"]["commit"] and len(m["git"]["commit"]) >= 7
    assert m["rows"] == len(t) == sum(m["rows_per_pair"].values()) == sum(m["rows_per_year"].values())
    assert sum(sum(v.values()) for v in m["rows_per_pair_year"].values()) == len(t)
    assert set(m["pairs"]) == set(PAIRS) and set(m["rows_per_pair"]) <= set(PAIRS)
    for tag in ("1r", "1p5r", "2r"):
        lr = m["label_resolution"][tag]
        assert lr["pos"] + lr["neg"] + lr["unresolved"] == len(t)
    assert set(m["feature_nan_rate"]) == set(mod.FEATURE_COLUMNS) and m["n_features"] == 43
    assert all(0.0 <= v <= 1.0 for v in m["feature_nan_rate"].values())
    for p in PAIRS:                                                                       # her girdi dosyasinin sha256'si dogru
        for kind in ("1h-futures", "1h-funding_rate"):
            f = built["a"]["hist"] / f"{p.replace('/', '_').replace(':', '_')}-{kind}.feather"
            assert m["inputs_sha256"][f.name]["sha256"] == mod.sha256_file(f)
    for f, h in m["code_sha256"].items():
        assert h == mod.sha256_file(ROOT / f)
    assert m["corpus"]["sha256"] == mod.sha256_file(built["a"]["dir"] / "corpus_v2.parquet")
    assert list(t.columns) == m["columns"] == mod.CORPUS_COLUMNS


def test_deterministic_same_inputs_same_corpus_sha(built):
    a, b = built["a"]["man"], built["b"]["man"]
    assert a["corpus"]["sha256"] == b["corpus"]["sha256"]
    assert a["corpus"]["content_sha256"] == b["corpus"]["content_sha256"]
    assert a["rows_per_pair_year"] == b["rows_per_pair_year"]


def test_dirty_tree_refused_without_flag(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "git_stamp", lambda: ("abcdef123456", [" M src/x.py"]))
    with pytest.raises(SystemExit, match="KIRLI"):
        mod.run(["--history-dir", str(tmp_path), "--out-dir", str(tmp_path / "o")])


# ------------------------------------------------------------------ aday tanimi
def test_pre_post_filter_candidate_definition(candles, built):
    t = built["a"]["table"]
    assert t["setup"].eq("T1").all() and t["source"].eq("native_v1b").all()
    assert "taken" not in t.columns and "net_r" not in t.columns                            # alinma/ledger kavrami yok
    assert not t.duplicated(["pair", "ts"]).any() and set(t["side"]) == {"long", "short"}   # iki yon
    assert (t["ts"] < END).all() and (t["ts"] >= START).all()
    n_all_sig = 0
    for p in PAIRS:
        fr = feature_frame(candles[p], None, None)
        sig = candidate_rows(fr, p)
        sig = sig[(sig["setup"] == "T1") & (sig["ts"] >= START) & (sig["ts"] < END)]
        n_all_sig += len(sig)
        got = t[t["pair"] == p].reset_index(drop=True)
        assert len(got) == len(sig) > 0
        np.testing.assert_array_equal(got["ts"].to_numpy(), sig["ts"].to_numpy())
        for c in ("planned_entry", "planned_stop"):
            np.testing.assert_array_equal(got[c].to_numpy(float), sig[c].to_numpy(float))
        assert got["side"].tolist() == sig["side"].tolist()
        # on-filtreyle elenen (signal False ama yon+giris var) satirlar derleme GIRMEZ
        pre = fr[fr["side"].notna() & fr["planned_entry"].notna()]
        assert len(pre) >= len(sig)
    assert n_all_sig == len(t)


def test_same_bar_count_consistent_with_engine_definition(candles, built):
    t = built["a"]["table"]
    n = t.groupby("ts")["pair"].transform("nunique").to_numpy(float)                        # ayni ts'de AYRI cift (iki yon dahil)
    np.testing.assert_array_equal(t["f_same_bar_signals"].to_numpy(float), n)
    assert built["a"]["man"]["same_bar"]["feature_matches_distinct_pairs"] is True
    # motor yolu (LiveContextV2, mum mum): ayni mumun yerel adaylari -> ayni sayi
    eng = lambda p: p.split(":")[0]
    def bars_fn(p, D, k):
        d = candles[p if ":" in p else p + ":USDT"]
        return d[d.index + BAR <= pd.Timestamp(D)].iloc[-k:]
    def funding_fn(p, a, b):
        return pd.DataFrame({"funding_rate": []}, index=pd.DatetimeIndex([], tz="UTC"))
    ctx = LiveContextV2("r03", [eng(p) for p in PAIRS], bars_fn, funding_fn)
    first = candles[PAIRS[0]].index[0]
    multi = t.groupby("ts").filter(lambda g: len(g) >= 2 and g["ts"].iloc[0] >= first + pd.Timedelta(hours=4900))
    assert len(multi) > 0, "sentetik veride >= 2 cift ayni mumda aday yok"
    for ts, g in list(multi.groupby("ts"))[:5]:
        c = g.assign(pair=g["pair"].map(eng))
        bf = ctx.features_for_bar(ts.to_pydatetime(), c[["pair", "side", "planned_entry", "planned_stop"]])
        assert {r["f_same_bar_signals"] for r in bf.rows.values()} == {float(len(g))} == {float(g["pair"].nunique())}


# ------------------------------------------------------------------ etiketler ve ozellikler
def test_label_columns_equal_multi_r_labels(mod, candles, built):
    t = built["a"]["table"]
    for p in PAIRS:
        g = t[t["pair"] == p].reset_index(drop=True)
        ref = multi_r_labels(candles[p], g[["ts", "side", "planned_entry", "planned_stop"]], target_rs=(1.0, 1.5, 2.0), horizon=72)
        assert list(ref.columns) == mod.LABEL_COLUMNS
        pd.testing.assert_frame_equal(g[mod.LABEL_COLUMNS], ref, check_exact=True, check_dtype=False)
    # kilitli donem satirlari okunmadigindan hicbir bitis zamani sinirin otesine gecemez; cozulmusler var
    assert t["label_2r"].notna().sum() > 0
    assert (t["label_end_ts_2r"].dropna() <= END).all()


def test_features_equal_guarded_wrapper(mod, candles, built, monkeypatch):
    t = built["a"]["table"]
    funding = {p: mod.load_funding(built["a"]["hist"], p, END) for p in PAIRS}
    c = t[["pair", "ts", "side", "planned_entry", "planned_stop"]]
    assert t["ts"].dt.year.nunique() >= 2                                                    # yil parcalari birden cok: parcalama degismezligi sinanir
    r02 = guarded_v2(candles, c, funding=funding, recipe="r02")                              # TEK cagri (parcasiz)
    r03 = guarded_v2(candles, c, funding=funding, recipe="r03")
    pd.testing.assert_frame_equal(t[list(r02.columns)], r02, check_exact=True)
    for col in mod.R03_EXTRA:
        np.testing.assert_array_equal(t[col].to_numpy(float), r03[col].to_numpy(float))
    assert t[list(r02.columns)].notna().to_numpy().mean() > 0.5                             # anlamsiz (hep NaN) karsilastirma degil
    # sarmalayici kilitli donemi reddeder (23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir)
    from trader_ml import guards as _G
    monkeypatch.setattr(_G, "KILIT_ACIK", False)
    late = {p: d.copy() for p, d in candles.items()}
    late[PAIRS[1]].index = late[PAIRS[1]].index + pd.Timedelta(days=400)
    with pytest.raises(HoldoutViolation):
        mod.features_for(late, funding, c.head(5))


# ------------------------------------------------------------------ elle kontrol dosyasi
def test_sample_check_markdown(built):
    md = (built["a"]["dir"] / "corpus_v2.sample_check.md").read_text(encoding="utf-8")
    assert md.count("\n## ") >= 51 and "[ ] elle dogru" in md
    assert sum(1 for ln in md.splitlines() if ln.startswith("## ") and ln[3].isdigit()) == 50
    assert "150/150" in md                                                                   # bagimsiz yeniden hesap 50 x 3 etiketle uyumlu
    assert "| SINYAL |" in md
