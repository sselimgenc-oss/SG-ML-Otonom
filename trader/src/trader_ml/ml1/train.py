"""ML1 egitimi: arindirilmis (purged) walk-forward + son holdout; ridge ve esik YALNIZ walk-forward OOS'tan secilir.

Akis:
  1. etiket: y = 1 if r_net > 0; yalniz status == "ok" ve censored degil (censored pay ayri raporlanir). Egitim agirligi = event_weight.
  2. holdout: verinin son `holdout_months` ayi (decision_ts >= holdout_start). Secimde HICBIR sekilde kullanilmaz. Cikisi holdout'a
     sarkan dev satirlari da dev'den atilir (etiketi holdout fiyatina bagli).
  3. walk-forward: genisleyen egitim, `test_months` aylik test pencereleri. Egitim satiri: exit_ts < test_start (purge) ve
     decision_ts < test_start - embargo (embargo = dev'deki maks. elde tutma suresi).
  4. ridge: ilk egitim katinin ic dogrulamasinda (son %25 zaman) bir kez secilir, sonra SABIT.
  5. esik: OOS tahminlerinde olay basina en yuksek puan; en az `min_trades` olay kosuluyla toplam net R'yi enbuyuk yapan esik.
  6. son model: tum dev (purge+embargo ile holdout'a gore) ile egitilir; holdout tek sefer degerlendirilir."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import evaluate as EV
from . import model as M

RIDGE_GRID = (0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0)
THRESHOLD_GRID = tuple(float(x) for x in np.round(np.arange(0.30, 0.9001, 0.005), 4))
MIN_FIT_ROWS = 50


# ----------------------------------------------------------------------------------------------------------- hazirlik
LAB_KEEP = ("decision_ts", "exit_ts", "pair", "tf", "group", "side", "arm_id", "event_id", "event_weight", "r_net", "status", "censored")


def prepare_labeled(df: pd.DataFrame, keep: tuple[str, ...] | None = None) -> tuple[pd.DataFrame, dict]:
    """Etiketli satirlar (y, w) + sayimlar. censored satirlar etiketten dislanir, payi ayri raporlanir.
    `keep` verilirse yalniz bu sutunlar (+ y, w, `_src` = df'teki konum) kalir (bellek); tum tablo kopyalanmaz."""
    n = len(df)
    status_ok = df["status"].eq("ok").to_numpy() if "status" in df.columns else np.ones(n, bool)
    cens = (pd.to_numeric(df["censored"], errors="coerce").fillna(0).astype(int) == 1).to_numpy() if "censored" in df.columns else np.zeros(n, bool)
    ok_rows = status_ok & df["r_net"].notna().to_numpy() & df["exit_ts"].notna().to_numpy()
    pos = np.flatnonzero(ok_rows & ~cens)
    pos = pos[np.argsort(df["decision_ts"].to_numpy()[pos], kind="stable")]
    cols = [c for c in (keep or df.columns) if c in df.columns]
    lab = df[cols].iloc[pos].reset_index(drop=True)
    lab["_src"] = pos
    lab["r_net"] = lab["r_net"].astype(float)
    lab["y"] = (lab["r_net"] > 0).astype(float)
    lab["w"] = lab["event_weight"].astype(float) if "event_weight" in lab.columns else 1.0
    n_ok = int(ok_rows.sum())
    info = {"n_rows": n, "n_status_ok": n_ok, "n_censored": int((ok_rows & cens).sum()),
            "censored_share": float((ok_rows & cens).sum() / n_ok) if n_ok else 0.0, "n_labeled": len(lab)}
    return lab, info


def split_holdout(lab: pd.DataFrame, holdout_months: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """(dev, holdout, holdout_start). dev: decision_ts < hs VE exit_ts < hs (etiket holdout'a sarkmaz)."""
    hs = lab["decision_ts"].max() - pd.DateOffset(months=holdout_months)
    dev = lab[(lab["decision_ts"] < hs) & (lab["exit_ts"] < hs)]
    hold = lab[lab["decision_ts"] >= hs]
    return dev, hold, hs


def max_holding(dev: pd.DataFrame) -> pd.Timedelta:
    return (dev["exit_ts"] - dev["decision_ts"]).max() if len(dev) else pd.Timedelta(0)


def train_mask(df: pd.DataFrame, test_start: pd.Timestamp, embargo: pd.Timedelta) -> np.ndarray:
    """Purge: exit_ts >= test_start olan satirlar dusurulur. Embargo: decision_ts >= test_start - embargo dusurulur."""
    return ((df["exit_ts"] < test_start) & (df["decision_ts"] < test_start - embargo)).to_numpy()


def make_folds(dev: pd.DataFrame, hs: pd.Timestamp, test_months: int, min_train_months: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if len(dev) == 0:
        return []
    s = dev["decision_ts"].min() + pd.DateOffset(months=min_train_months)
    out = []
    while s < hs:
        e = min(s + pd.DateOffset(months=test_months), hs)
        out.append((s, e))
        s = e
    return out


# ----------------------------------------------------------------------------------------------------------- uydurma
def _fit(df: pd.DataFrame, names: list[str], ridge: float, X: np.ndarray | None = None) -> tuple[dict, np.ndarray, float]:
    """X verilirse (n_tum, k) onceden kurulmus matris; satirlar df['_row'] ile secilir (kopya yok, blok blok). Z float32 (bellek)."""
    if X is None:
        X, rows, dt = M.design_matrix(df, names), None, None
    else:
        rows, dt = df["_row"].to_numpy(), np.float32
    st = M.fit_standardizer(X, rows)
    Z = M.standardize(X, st, rows, dtype=dt)
    coef, b = M.fit_logistic(Z, df["y"].to_numpy(float), df["w"].to_numpy(float), ridge)
    return st, coef, b


def _predict(df: pd.DataFrame, names: list[str], st: dict, coef: np.ndarray, b: float, X: np.ndarray | None = None) -> np.ndarray:
    if X is None:
        return M._sigmoid(M.standardize(M.design_matrix(df, names), st) @ coef + b)
    rows = df["_row"].to_numpy()
    out = np.empty(len(rows))
    for i in range(0, len(rows), M.CHUNK):
        out[i:i + M.CHUNK] = M._sigmoid(M.standardize(X, st, rows[i:i + M.CHUNK]) @ coef + b)
    return out


def choose_ridge(train: pd.DataFrame, names: list[str], embargo: pd.Timedelta, grid=RIDGE_GRID, inner_frac: float = 0.25,
                 X: np.ndarray | None = None) -> float:
    """Ilk egitim katinda ic dogrulama (son `inner_frac` zaman; purge+embargo ile) agirlikli log-kayip en kucuk ridge."""
    vs = train["decision_ts"].quantile(1 - inner_frac)
    vs = pd.Timestamp(vs)
    tr = train[train_mask(train, vs, embargo)]
    va = train[train["decision_ts"] >= vs]
    if len(tr) < MIN_FIT_ROWS or len(va) < 10 or tr["y"].nunique() < 2:
        return float(grid[len(grid) // 2])
    best, best_l = grid[0], np.inf
    for r in grid:
        st, coef, b = _fit(tr, names, r, X)
        loss = M.log_loss(_predict(va, names, st, coef, b, X), va["y"].to_numpy(float), va["w"].to_numpy(float))
        if loss <= best_l:                                   # esitlikte buyuk ridge
            best, best_l = r, loss
    return float(best)


def choose_threshold(oos: pd.DataFrame, min_trades: int, grid=THRESHOLD_GRID) -> tuple[float | None, str]:
    """OOS tahminlerinde (olay basina en yuksek puan) en az min_trades olayla toplam net R'yi enbuyuk yapan esik; yoksa None."""
    best = EV.select_one_per_event(oos, "p")
    if len(best) == 0:
        return None, "OOS tahmini yok"
    p, r = best["p"].to_numpy(float), best["r_net"].to_numpy(float)
    top, top_t = -np.inf, None
    for t in grid:
        m = p >= t
        if m.sum() < min_trades:
            continue
        tot = float(r[m].sum())
        if tot > top:
            top, top_t = tot, t
    if top_t is None:
        return None, f"hicbir esik >= {min_trades} olay saglamadi (OOS olay: {len(best)}); islem yok"
    return float(top_t), f"esik {top_t:.3f}: OOS toplam net R {top:.1f}, {int((p >= top_t).sum())} olay (min {min_trades})"


# ----------------------------------------------------------------------------------------------------------- ana akis
def run(df: pd.DataFrame, *, holdout_months: int = 3, test_months: int = 3, min_train_months: int = 6, min_trades: int = 200,
        embargo: pd.Timedelta | None = None, ridge_grid=RIDGE_GRID, names: list[str] | None = None) -> dict:
    """`df`: build_features cikisi (ozellikler + event_id/event_weight + cikis sutunlari). Doner sonuc sozlugu (evaluate.build_report girdisi)."""
    names = names or M.feature_names()
    M.assert_no_leak(names)
    lab, info = prepare_labeled(df, LAB_KEEP)
    # tasarim matrisi YALNIZ etiketli satirlar icin, float32, blok blok kurulur (lab ile ayni sira; satir = lab['_row'])
    X = np.empty((len(lab), len(names)), dtype=np.float32)
    src = lab["_src"].to_numpy()
    for i in range(0, len(lab), M.CHUNK):
        X[i:i + M.CHUNK] = M.design_matrix(df.iloc[src[i:i + M.CHUNK]], names, dtype=np.float32)
    lab = lab.drop(columns=["_src"])
    lab["_row"] = np.arange(len(lab), dtype=np.int64)
    cfg = {"holdout_months": holdout_months, "test_months": test_months, "min_train_months": min_train_months, "min_trades": min_trades}
    empty = pd.DataFrame(columns=list(lab.columns) + ["p"])
    res = {"config": cfg, "oos": empty, "holdout": empty, "threshold": None, "ridge": None, "folds": [], "package": None,
           "threshold_note": "veri yetersiz", "data": dict(info)}
    if len(lab) == 0:
        return res
    dev, hold, hs = split_holdout(lab, holdout_months)
    emb = embargo if embargo is not None else max_holding(dev)
    res["data"].update({"dev_start": str(dev["decision_ts"].min()) if len(dev) else None, "holdout_start": str(hs),
                        "data_end": str(lab["decision_ts"].max()), "embargo_days": float(emb / pd.Timedelta(days=1)),
                        "n_dev": len(dev), "n_holdout": len(hold)})
    folds = make_folds(dev, hs, test_months, min_train_months)
    ridge, parts, finfo = None, [], []
    for (s, e) in folds:
        tr = dev[train_mask(dev, s, emb)]
        te = dev[(dev["decision_ts"] >= s) & (dev["decision_ts"] < e)]
        if len(tr) < MIN_FIT_ROWS or tr["y"].nunique() < 2 or len(te) == 0:
            continue
        if ridge is None:                                    # ridge bir kez, ilk gecerli katin egitiminde
            ridge = choose_ridge(tr, names, emb, ridge_grid, X=X)
        st, coef, b = _fit(tr, names, ridge, X)
        t2 = te.copy()
        t2["p"] = _predict(te, names, st, coef, b, X)
        parts.append(t2)
        finfo.append({"test_start": str(s), "test_end": str(e), "n_train": len(tr), "n_test": len(te)})
    res["folds"] = finfo
    if not parts:
        res["threshold_note"] = "hic gecerli walk-forward kati yok (veri/sinif yetersiz)"
        return res
    oos = pd.concat(parts, ignore_index=True)
    thr, note = choose_threshold(oos, min_trades)
    # son model: tum dev (holdout'a gore purge+embargo; dev zaten exit_ts < hs) ile ayni (sabit) ridge
    final_tr = dev[train_mask(dev, hs, emb)]
    st, coef, b = _fit(final_tr, names, ridge, X)
    h2 = hold.copy()
    h2["p"] = _predict(hold, names, st, coef, b, X) if len(hold) else np.array([])
    res.update({"oos": oos, "holdout": h2, "threshold": thr, "threshold_note": note, "ridge": ridge})
    rep = EV.build_report(res)
    metrics = {"oos_ml": rep["oos"].get("ml"), "oos_baseline_first": rep["oos"].get("baseline_first_per_event"),
               "holdout_ml": rep["holdout"].get("ml"), "verdict": rep["verdict"]["verdict"]}
    res["package"] = M.build_package(names, st, coef, b, thr, ridge, train_start=final_tr["decision_ts"].min() if len(final_tr) else None,
                                     train_end=final_tr["decision_ts"].max() if len(final_tr) else None, n_train=len(final_tr),
                                     metrics=metrics)
    return res
