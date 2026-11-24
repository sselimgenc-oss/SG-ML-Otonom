"""M1 egitimi: ridge lojistik (numpy), kilit donemi YAPISAL reddi (D-T21).

Esik: egitim puanlarinin %98'i (en yuksek ~%2 aday). Model, veri, sinif tek ise None (aday uretilmez; motor durmaz).
Girdi satirlari {ts, ts_end, side, x, y}; ts ve ts_end tz-li olmali; herhangi bir satir kilit donemiyle kesisirse
LockWindowError (tek satir bile olsa egitim yapilmaz)."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone

import numpy as np

from trader_core.ml_eval import TreeModel

from . import features as F
from .package import build_package

KILIT_ACIK = True                                           # trader_engine.holdout.KILIT_ACIK kopyasi (23.11.2026 kullanici karari; parite testi)
LOCK_START = datetime(2026, 5, 1, tzinfo=timezone.utc)      # trader_engine.holdout.HOLDOUT'un kopyasi (parite testi)
LOCK_END = datetime(2026, 11, 1, tzinfo=timezone.utc)
RIDGE = 5.0                                                  # standartlastirilmis ozelliklerde L2; kucuk ornekte dogal sonumleme


class LockWindowError(ValueError):
    """Kilitli donem (2026-05-01..2026-11-01) ile kesisen satir egitime verildi."""


def in_lock(ts: datetime, ts_end: datetime | None = None) -> bool:
    """[ts, ts_end] aralagi kilitle kesisiyorsa True (sonuc penceresi kilide uzanan karar da kilitlidir)."""
    if ts.tzinfo is None or (ts_end is not None and ts_end.tzinfo is None):
        raise LockWindowError("tz-bilincli olmayan zaman reddedildi")
    if KILIT_ACIK:
        return False
    end = ts if ts_end is None or ts_end < ts else ts_end
    return ts < LOCK_END and end >= LOCK_START


def assert_no_lock(rows: Iterable[Mapping]) -> None:
    for r in rows:
        if in_lock(r["ts"], r.get("ts_end")):
            raise LockWindowError(f"kilit donemi satiri egitime giremez: {r['ts'].isoformat()}")


def drop_lock(rows: Iterable[Mapping]) -> tuple[list[dict], int]:
    keep, n = [], 0
    for r in rows:
        if in_lock(r["ts"], r.get("ts_end")):
            n += 1
        else:
            keep.append(dict(r))
    return keep, n


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic(X: np.ndarray, y: np.ndarray, ridge: float = RIDGE, iters: int = 40) -> dict:
    """Ridge lojistik (Newton/IRLS; kesisim cezasiz). Donus: TreeModel 'logistic' sozlugu (coef, intercept, mean, std, fill)."""
    n, k = X.shape
    fill = np.where(np.isfinite(X).any(axis=0), np.nanmean(np.where(np.isfinite(X), X, np.nan), axis=0), 0.0) if n else np.zeros(k)
    fill = np.nan_to_num(fill)
    Xf = np.where(np.isfinite(X), X, fill)
    mean = Xf.mean(axis=0)
    std = Xf.std(axis=0)
    std = np.where(std < 1e-12, 1.0, std)
    Z = (Xf - mean) / std
    A = np.hstack([Z, np.ones((n, 1))])
    w = np.zeros(k + 1)
    w[-1] = np.log((y.mean() + 1e-3) / (1 - y.mean() + 1e-3))
    P = np.diag(np.r_[np.full(k, ridge), 0.0])
    for _ in range(iters):
        p = _sigmoid(A @ w)
        g = A.T @ (p - y) + P @ w
        H = (A * (p * (1 - p))[:, None]).T @ A + P + 1e-9 * np.eye(k + 1)
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return {"kind": "logistic", "n_features": int(k), "coef": [float(v) for v in w[:-1]], "intercept": float(w[-1]),
            "mean": [float(v) for v in mean], "std": [float(v) for v in std], "fill": [float(v) for v in fill]}


THRESHOLD_Q = 0.98
MAX_ROWS = 400_000
MIN_ROWS = 2   # mevcut kural: en az 2 satir ve iki sinif; altinda model yok (esik uydurulmaz)


def train_tf(rows: Sequence[Mapping], *, arm_id: str, created_at: datetime | None = None, max_rows: int = MAX_ROWS) -> dict | None:
    """Tek zaman dilimi paketi (arm_id = 'M1@<tf>') ya da None. Kilit satiri -> LockWindowError."""
    assert_no_lock(rows)
    rows = sorted(rows, key=lambda r: (r["ts"], r["side"]))[-max_rows:]
    if len(rows) < MIN_ROWS:
        return None
    y = np.array([float(r["y"]) for r in rows])
    if y.min() == y.max():
        return None
    X = np.vstack([np.asarray(r["x"], dtype=np.float64) for r in rows])
    if not np.isfinite(X).all():
        raise ValueError("ozellik matrisinde sonlu olmayan deger")
    model = fit_logistic(X, y)
    scores = TreeModel(model, {"a": 1.0, "b": 0.0}).predict_proba(X)
    thr = float(np.quantile(scores, THRESHOLD_Q))
    return build_package(arm_id, model, thr, list(F.FEATURE_NAMES), train_start=rows[0]["ts"], train_end=rows[-1]["ts"],
                         n_train=len(rows), n_pos=int(y.sum()), data_hash=row_digest(rows), lock_dropped=0,
                         base_rate=float(y.mean()), created_at=created_at)


def no_model_reason(n_rows: int, y_classes: int | None = None) -> str:
    """Paket olusmayan kolun gorunur nedeni (gece ciktisi/paper_models.csv): 'model yok: N örnek, en az M'."""
    if n_rows < MIN_ROWS or y_classes is None or y_classes >= 2:
        return f"model yok: {n_rows} örnek, en az {MIN_ROWS}"
    return f"model yok: {n_rows} örnek, tek sınıf (iki sınıf gerekir)"


def split_lock(rows: Iterable[Mapping]) -> tuple[list[dict], int]:
    """Kilit satirlarini sayip dusurur (kâgit kaydi icin); tarihsel satirlar buradan gecmez, kilit ihlali TRAIN'de yakalanir."""
    return drop_lock(rows)


def row_digest(rows: Sequence[Mapping]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(f"{r['ts'].isoformat()}|{r['side']}|{r['y']}|{np.asarray(r['x']).tobytes().hex()}".encode())
    return h.hexdigest()
