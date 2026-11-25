"""ML1 modeli: ozellik izin listesi (allowlist), agirlikli ridge lojistik (numpy) ve imzali paket ("ml1/1").

Kurallar:
  - Ozellikler YALNIZ `feature_names()` izin listesinden gelir. event_weight/event_id ve karar SONRASI her sutun (exit_*, r_net, mfe_R,
    mae_R, bars_held, status, censored ...) ozellik OLAMAZ (`FORBIDDEN_PREFIXES`; testte denetlenir). Takvim (hour_utc, dow) v1'de YOK.
  - Standardizasyon istatistikleri yalniz egitim kati ustunden (mean/std/fill); NaN -> egitim ortalamasi (standartlasmis uzayda 0).
  - Paket: json, sha256 = kanonik json (sha256 alani HARIC) uzerinden. `load_package` hicbir kosulda yukari firlatmaz: (None, neden)."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader_core import pa_features as PF
from trader_core.ml_package import canon, sha256_text

from . import data as D
from . import groups as G

SCHEMA = "ml1/1"
TFS = tuple(D.TFS)
CONF_COLS = ("conf_same_tf", "conf_all_tf", "conf_groups", "conf_opp")
REG_COLS = ("reg_atr_ratio", "reg_atr_pct", "reg_atr4h_pct", "reg_rh_dist_atr", "reg_rl_dist_atr", "reg_rh_touches",
            "reg_rl_touches", "reg_trend_align")
VOL_COLS = ("vol_20", "vol_100", "vol_ratio", "vol_volume_ratio", "vol_range_atr")
# ozellik olamayacak ad oneklerine/adlarina karsi savunma (izin listesi zaten dar; bu ikinci kilit)
FORBIDDEN_PREFIXES = ("exit_", "r_net", "mfe", "mae", "bars_held", "gross_", "fee_", "funding_", "event_", "status", "censored",
                      "entry_ts", "entry_px", "be_moved", "partial_", "label", "hour_utc", "dow")


def feature_names() -> list[str]:
    """Sirali izin listesi (model girdisi). Turetilenler: side_sign, stop_dist_atr, tgt_stop_ratio, has_target, grp_*, tf_*."""
    pa = ["pa_" + x for x in PF.FEATURE_NAMES]
    return (pa + list(REG_COLS) + list(VOL_COLS) + list(CONF_COLS)
            + ["grp_" + g for g in G.GRUP_ADLARI] + ["tf_" + t for t in TFS]
            + ["side_sign", "stop_dist_atr", "tgt_stop_ratio", "has_target"])


def assert_no_leak(names: list[str]) -> None:
    for n in names:
        if n.startswith(FORBIDDEN_PREFIXES):
            raise ValueError(f"yasakli ozellik: {n}")


def design_matrix(df: pd.DataFrame, names: list[str] | None = None) -> np.ndarray:
    """Ham aday satirlari -> (n, k) float matris (NaN korunur). Eksik ham sutun (pa_/reg_/vol_) NaN sayilir."""
    names = names or feature_names()
    assert_no_leak(names)
    n = len(df)
    cols: dict[str, np.ndarray] = {}

    def raw(c: str) -> np.ndarray:
        return pd.to_numeric(df[c], errors="coerce").to_numpy(float) if c in df.columns else np.full(n, np.nan)

    side = df["side"].to_numpy() if "side" in df.columns else np.full(n, "long", dtype=object)
    cols["side_sign"] = np.where(side == "long", 1.0, -1.0)
    cols["stop_dist_atr"] = raw("stop_dist_atr")
    ref, stop, tgt = raw("entry_ref"), raw("stop"), raw("target")
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.abs(tgt - ref) / np.abs(ref - stop)
    has = np.isfinite(tgt) & np.isfinite(ratio)
    cols["has_target"] = has.astype(float)
    cols["tgt_stop_ratio"] = np.where(has, ratio, 0.0)                    # hedefsiz -> 0 + gosterge
    grp = df["group"].to_numpy() if "group" in df.columns else np.full(n, "", dtype=object)
    tf = df["tf"].to_numpy() if "tf" in df.columns else np.full(n, "", dtype=object)
    for g in G.GRUP_ADLARI:
        cols["grp_" + g] = (grp == g).astype(float)
    for t in TFS:
        cols["tf_" + t] = (tf == t).astype(float)
    out = np.empty((n, len(names)))
    for j, nm in enumerate(names):
        out[:, j] = cols[nm] if nm in cols else raw(nm)
    out[~np.isfinite(out)] = np.nan
    return out


# ----------------------------------------------------------------------------------------------------------- lojistik
def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def fit_standardizer(X: np.ndarray) -> dict:
    """Yalniz egitim kati: fill (nan-ortalama), mean, std (fill sonrasi)."""
    k = X.shape[1]
    ok = np.isfinite(X)
    cnt = ok.sum(axis=0)
    fill = np.where(cnt > 0, np.where(ok, X, 0.0).sum(axis=0) / np.maximum(cnt, 1), 0.0)
    Xf = np.where(ok, X, fill)
    mean = Xf.mean(axis=0) if len(X) else np.zeros(k)
    std = Xf.std(axis=0) if len(X) else np.ones(k)
    std = np.where(std < 1e-12, 1.0, std)
    return {"fill": fill, "mean": mean, "std": std}


def standardize(X: np.ndarray, st: dict) -> np.ndarray:
    Xf = np.where(np.isfinite(X), X, np.asarray(st["fill"], float))
    return (Xf - np.asarray(st["mean"], float)) / np.asarray(st["std"], float)


def fit_logistic(Z: np.ndarray, y: np.ndarray, w: np.ndarray | None, ridge: float, iters: int = 50) -> tuple[np.ndarray, float]:
    """Agirlikli ridge lojistik (Newton/IRLS; kesisim cezasiz). Z standartlasmis. Doner (coef, intercept)."""
    n, k = Z.shape
    w = np.ones(n) if w is None else np.asarray(w, float)
    sw = w.sum()
    if n == 0 or sw <= 0:
        return np.zeros(k), 0.0
    w = w * (n / sw)                                       # ortalama agirlik 1: ridge olcegi n'e bagli kalmaz
    A = np.hstack([Z, np.ones((n, 1))])
    ybar = float((w * y).sum() / w.sum())
    beta = np.zeros(k + 1)
    beta[-1] = np.log((ybar + 1e-3) / (1 - ybar + 1e-3))
    P = np.diag(np.r_[np.full(k, ridge), 0.0])
    for _ in range(iters):
        p = _sigmoid(A @ beta)
        g = A.T @ (w * (p - y)) + P @ beta
        H = (A * (w * p * (1 - p))[:, None]).T @ A + P + 1e-9 * np.eye(k + 1)
        step = np.linalg.solve(H, g)
        beta -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return beta[:-1], float(beta[-1])


def log_loss(p: np.ndarray, y: np.ndarray, w: np.ndarray | None = None) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    l = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    return float(np.average(l, weights=w)) if len(l) else float("nan")


# ----------------------------------------------------------------------------------------------------------- paket
def _clean(o):
    """json icin: numpy -> python, NaN/inf -> None (canon allow_nan=False)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating, float)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def package_hash(pkg: dict) -> str:
    return sha256_text(canon({k: v for k, v in pkg.items() if k != "sha256"}))


def build_package(names: list[str], st: dict, coef: np.ndarray, intercept: float, threshold: float | None, ridge: float, *,
                  train_start, train_end, n_train: int, metrics: dict | None = None, created_at: datetime | None = None) -> dict:
    assert_no_leak(list(names))
    pkg = _clean({
        "schema": SCHEMA, "feature_names": list(names),
        "standardization": {"fill": st["fill"], "mean": st["mean"], "std": st["std"]},
        "weights": {"coef": coef, "intercept": intercept}, "ridge": ridge, "threshold": threshold,
        "train_range": {"start": None if train_start is None else pd.Timestamp(train_start).isoformat(),
                        "end": None if train_end is None else pd.Timestamp(train_end).isoformat()},
        "n_train": int(n_train), "metrics": metrics or {},
        "created_at": (created_at or datetime.now(UTC)).isoformat()})
    pkg["sha256"] = package_hash(pkg)
    return pkg


def save_package(pkg: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(pkg, sort_keys=True, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def verify_package(pkg) -> str | None:
    """None = tamam, aksi halde neden metni. Hicbir kosulda firlatmaz."""
    try:
        if not isinstance(pkg, dict):
            return "paket sozluk degil"
        if pkg.get("schema") != SCHEMA:
            return f"sema uyusmuyor: {pkg.get('schema')!r}"
        if pkg.get("sha256") != package_hash(pkg):
            return "sha256 uyusmuyor"
        names = pkg["feature_names"]
        k = len(names)
        assert_no_leak(list(names))
        if len(pkg["weights"]["coef"]) != k:
            return "agirlik boyutu ozellik sayisina uymuyor"
        for key in ("fill", "mean", "std"):
            if len(pkg["standardization"][key]) != k:
                return f"standardizasyon.{key} boyutu uymuyor"
        return None
    except Exception as e:  # noqa: BLE001 - dogrulayici asla firlatmaz
        return f"paket gecersiz: {type(e).__name__}: {e}"


def load_package(path: str | Path) -> tuple[dict | None, str | None]:
    """(paket, None) ya da (None, neden). Dosya yok / bozuk json / sema / hash sorunlarinda firlatmaz."""
    try:
        pkg = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return None, f"okunamadi: {type(e).__name__}: {e}"
    why = verify_package(pkg)
    return (None, why) if why else (pkg, None)


def score(pkg: dict, features_df: pd.DataFrame) -> np.ndarray:
    """Olasilik (n,) - yalniz numpy. features_df ham aday+ozellik tablosu (design_matrix ayni turetmeyi yapar)."""
    names = list(pkg["feature_names"])
    X = design_matrix(features_df, names)
    Z = standardize(X, pkg["standardization"])
    return _sigmoid(Z @ np.asarray(pkg["weights"]["coef"], float) + float(pkg["weights"]["intercept"]))
