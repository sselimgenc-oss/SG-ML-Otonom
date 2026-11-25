"""ML1 egitim/hizmet paritesi GERCEK gecmiste (CI degil; veri CI'da yok).

Kagit motoru (HistoricalSource, tum kural kollari 15m/1h/4h/1d, ML1 acik, tohum paket) gecmisin son N gununde kosulur; canli hesaplanan
ozellik/puanlar ayni adaylar icin cevrimdisi hatla (scan + build_features(TUM gecmis mumlari) + score) karsilastirilir.
Kullanim: cd trader && PYTHONPATH=src python3 research/ml1/serve_parity_real.py --hist <dizin> --pairs BTC/USDT,SOL/USDT,XAU/USDT --days 7 [--cold]
Cikti: ozellik grubu basina (pa_/reg_/vol_/conf_/turetilen) en buyuk mutlak fark, puan farki, aday kumesi esitligi, 0.58 karar cevirmeleri."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "ml1"))
import ml1_motor_destek as T  # noqa: E402  (motor kurucu yardimcilari)

from trader_engine import ml1_gate as MG  # noqa: E402
from trader_engine.engine import Engine  # noqa: E402
from trader_ml.ml1 import data as D  # noqa: E402
from trader_ml.ml1 import features as F  # noqa: E402
from trader_ml.ml1 import groups as G  # noqa: E402
from trader_ml.ml1 import model as M  # noqa: E402
from trader_ml.ml1 import scan as SC  # noqa: E402

TFS = ("15m", "1h", "4h", "1d")


def offline(hist: Path, pkg: dict, pairs, arms, after) -> pd.DataFrame:
    cache: dict = {}

    def lookup(pair, tf):
        if (pair, tf) not in cache:
            cache[(pair, tf)] = D.load_pair_tf(hist, pair, tf)       # TUM gecmis (egitimle ayni)
        return cache[(pair, tf)]
    out = []
    for pair in pairs:
        parts = []
        for tf in TFS:
            got = lookup(pair, tf)
            ids = [a for a in arms if a.endswith("@" + tf)]
            if got is None or not ids:
                continue
            c = SC.scan_pair_tf(pair, tf, got[0], got[1], ids, after=after)
            if len(c):
                parts.append(c)
        if parts:
            out.append(F.build_features(pd.concat(parts, ignore_index=True), lookup))
    f = pd.concat(out)
    f["score"] = M.score(pkg, f)
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", required=True)
    ap.add_argument("--pairs", default="BTC/USDT,SOL/USDT,XAU/USDT")
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--cold", action="store_true", help="tamponu tohumlama (soguk baslangic)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    hist = Path(a.hist)
    pairs = a.pairs.split(",")
    Engine._startup_gate = lambda self: None
    seed = json.loads(T.SEED_PKG.read_text(encoding="utf-8"))
    thr = float(seed["threshold"])
    arms = tuple(G.rule_arm_ids())
    last = max(pd.read_feather(hist / (p.replace("/", "_") + "_USDT-15m-futures.feather"))["date"].max() for p in pairs)
    end = (last + pd.Timedelta("15min")).to_pydatetime()
    start = end - timedelta(days=a.days)
    print(f"pencere {start} -> {end}; kol {len(arms)}; esik {thr}", flush=True)

    cfg0 = T.PAPER
    clusters = {k: {"pairs": [p for p in v.pairs if p in pairs], "max_positions": v.max_positions} for k, v in cfg0.clusters.items()}
    clusters = {k: v for k, v in clusters.items() if v["pairs"]}
    tmp = Path(tempfile.mkdtemp(prefix="ml1_real_"))
    kw = dict(pairs=tuple(pairs), optional_pairs=tuple(p for p in pairs if p in cfg0.optional_pairs), clusters=clusters,
              cost_overrides={p: cfg0.cost_overrides[p] for p in pairs if p in cfg0.cost_overrides}, arms=arms, var_dir=str(tmp / "var"),
              kill_file=str(tmp / "KILL"), pause_file=str(tmp / "PAUSE"), market_db=str(tmp / "m.sqlite"), history_dir=str(tmp / "h"),
              ml1={"aktif": True, "paket_yolu": str(tmp / "yok.json"), "tohum_yolu": str(T.SEED_PKG)})
    # canli yapilandirmanin gercek kapi/risk ayarlari korunur (T.make_cfg degil): yalniz evren daraltilir
    from trader_engine import engine as E
    from trader_engine.clock import SimClock
    from trader_engine.config import apply_overrides
    from trader_engine.marketdata.sources import HistoricalSource
    cfg = apply_overrides(cfg0, **kw, cost=dict(fill_model="native", granularity="15m", trigger_source="last"))
    eng = E.build_engine(cfg, clock=SimClock(start), view=HistoricalSource(str(hist), granularity="15m", synthetic_rules=True), env={})
    eng.ledger.init_params(T.pmap(), reason=f"strategy:{eng.strategy.info.name}@{eng.strategy.info.version} real-parity")
    eng.start()
    frames, observed = [], set()
    obs, sc, real_m = MG.Ml1Gate.observe, MG.M.score, MG.M

    def observe(self, pair, D_, tf, r, trig, h4):
        obs(self, pair, D_, tf, r, trig, h4)
        if r["setup"] in G.GRUPLAR:
            observed.add((pair, f"{r['setup']}@{tf}", pd.Timestamp(D_), r["side"]))

    def score(pkg, df):
        frames.append(df.copy())
        return sc(pkg, df)
    MG.Ml1Gate.observe = observe
    MG.M = SimpleNamespace(load_package=real_m.load_package, score=score)

    after = pd.Timestamp(start) - timedelta(days=4)                 # tohum + konfluans penceresi icin
    off_all = offline(hist, seed, pairs, arms, after)
    off_all["decision_ts"] = pd.to_datetime(off_all["decision_ts"], utc=True)
    if not a.cold:
        eng.ml1.seed(off_all[off_all["decision_ts"] <= pd.Timestamp(start)])
    print("motor kosuyor...", flush=True)
    eng.run_range(start, end)
    ctr = eng.counters()
    print("sayaclar:", {k: v for k, v in ctr.items() if k.startswith("ml1_") or k in ("decisions", "callback_errors")}, flush=True)

    key = ["pair", "arm_id", "decision_ts", "side"]
    off = off_all[(off_all["decision_ts"] > pd.Timestamp(start)) & (off_all["decision_ts"] <= pd.Timestamp(end))].set_index(key).sort_index()
    live = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=key)
    live["decision_ts"] = pd.to_datetime(live["decision_ts"], utc=True)
    live = live.drop_duplicates(key).set_index(key).sort_index()
    off_keys = set(off.index)
    obs_keys = {(p, a_, ts, s) for p, a_, ts, s in observed if ts > pd.Timestamp(start)}
    res = {"pencere": [str(start), str(end)], "cift": pairs, "esik": thr, "offline_aday": len(off_keys), "motor_gozlenen_aday": len(obs_keys),
           "aday_kumesi_esit": obs_keys == off_keys, "yalniz_motor": sorted(map(str, obs_keys - off_keys))[:10],
           "yalniz_offline": sorted(map(str, off_keys - obs_keys))[:10], "puanlanan_aday": len(live)}
    common = live.index.intersection(off.index)
    res["puanlanan_ve_offline_ortak"] = len(common)
    res["cift_basina_aday(offline)"] = {k: int(v) for k, v in off.reset_index().groupby("pair").size().items()}
    res["cift_basina_puanlanan"] = {k: int(v) for k, v in common.to_frame(index=False)["pair"].value_counts().items()}
    names = M.feature_names()
    lx = M.design_matrix(live.loc[common].reset_index(), names)
    ox = M.design_matrix(off.loc[common].reset_index(), names)
    grp = {}
    for j, n in enumerate(names):
        g = next((p for p in ("pa_", "reg_", "vol_", "conf_") if n.startswith(p)), "turetilen")
        both = np.isnan(lx[:, j]) & np.isnan(ox[:, j])
        nan_mismatch = int((np.isnan(lx[:, j]) != np.isnan(ox[:, j])).sum())
        d = np.abs(lx[:, j] - ox[:, j])
        d = d[~both & ~np.isnan(d)]
        e = grp.setdefault(g, {"max_abs": 0.0, "max_rel": 0.0, "nan_uyusmaz": 0, "en_kotu": None})
        m = float(d.max()) if len(d) else 0.0
        rel = float((d / np.maximum(np.abs(ox[:, j][~both & ~np.isnan(np.abs(lx[:, j] - ox[:, j]))]), 1e-12)).max()) if len(d) else 0.0
        e["nan_uyusmaz"] += nan_mismatch
        e["max_rel"] = max(e["max_rel"], rel)
        if m > e["max_abs"]:
            e["max_abs"], e["en_kotu"] = m, n
    res["ozellik_gruplari"] = grp
    ls = M.score(seed, live.loc[common].reset_index())
    os_ = off.loc[common, "score"].to_numpy(float)
    res["puan_max_abs_fark"] = float(np.abs(ls - os_).max()) if len(ls) else None
    res["karar_cevirme_sayisi"] = int(((ls >= thr) != (os_ >= thr)).sum())
    res["esige_yakin(|p-esik|<0.01)"] = int((np.abs(os_ - thr) < 0.01).sum())
    bad = np.abs(ls - os_) > 1e-4 if len(ls) else np.array([], bool)
    res["puan_fark>1e-4"] = int(bad.sum())
    if bad.any():
        res["en_kotu_adaylar"] = [dict(zip(key, map(str, k)), live=float(l), off=float(o)) for k, l, o in
                                  list(zip(common[bad], ls[bad], os_[bad]))[:10]]
    print(json.dumps(res, indent=1, default=str))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
