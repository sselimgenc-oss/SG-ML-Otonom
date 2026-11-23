"""Kurulum bazli suzgec egitimi: sonlu, sonlandirilmis ridge lojistik (numpy). Kilit donemi YAPISAL reddi. Asgari ornek esigi YOK:
iki sinif da varsa model olusur; tek sinif/veri yoksa `None` (-> motor `ml_no_model`, aday gecer)."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime, timezone

import numpy as np

from . import features as F
from .package import build_package, data_hash_of

KILIT_ACIK = True                                           # trader_engine.holdout.KILIT_ACIK kopyasi (23.11.2026 kullanici karari; parite testi)
LOCK_START = datetime(2026, 5, 1, tzinfo=timezone.utc)      # trader_engine.holdout.HOLDOUT'un kopyasi (parite testi)
LOCK_END = datetime(2026, 11, 1, tzinfo=timezone.utc)
MAX_ROWS = 50_000
RIDGE = 5.0                                                  # standartlastirilmis ozelliklerde L2; kucuk ornekte dogal sonumleme
THR_FRAC = 0.9                                               # esik = 0.9 x taban oran (R>0): yalniz taban oranin belirgin altini eler


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


def build_rows(decisions: Iterable[Mapping], outcomes: Mapping[int, tuple[float, datetime | None]],
               notes: Iterable[Mapping] = (), *, asset_class_fn: Callable[[str], str] | None = None) -> list[dict]:
    """decisions: id, arm_id, pair, side, regime, atr_ratio, session_tag, lesson_ids, features, planned_*, rh/rl_touches, bar_close_ts.
    outcomes[id] = (net R, sonuc penceresi sonu): alinan = kapanan islem R'si, alinmayan = 'alinsaydi' R'si. `notes` (WP-09
    export_ml_rows): yalniz R'yi tamamlar (outcomes'ta yoksa `trade_id` esli `r`); etiketler ozellige GIRMEZ."""
    note_r = {n["trade_id"]: n["r"] for n in notes if n.get("r") is not None and n.get("role") == "label"}
    rows = []
    for d in decisions:
        o = outcomes.get(d["id"])
        if o is None and d.get("trade_id") in note_r:
            o = (note_r[d["trade_id"]], None)
        if o is None or o[0] is None or not np.isfinite(o[0]) or not d.get("arm_id"):
            continue
        fd = F.setup_feature_dict(
            side=d["side"], regime=d["regime"], atr_ratio=d.get("atr_ratio"), session_tag=d.get("session_tag"),
            asset_class=(asset_class_fn(d["pair"]) if asset_class_fn else None), pair=d.get("pair"),
            planned_entry=d["planned_entry"], planned_stop=d["planned_stop"], planned_target=d.get("planned_target"),
            rh_touches=d.get("rh_touches", 0), rl_touches=d.get("rl_touches", 0),
            lesson_ids=d.get("lesson_ids") or (), features=d.get("features") or {})
        rows.append({"id": d["id"], "arm_id": d["arm_id"], "ts": d["bar_close_ts"], "ts_end": o[1], "x": fd, "r": float(o[0])})
    return rows


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


def train_arm(arm_id: str, rows: Sequence[Mapping], *, created_at: datetime | None = None, max_rows: int = MAX_ROWS) -> dict | None:
    """Tek kol paketi ya da None (veri yok / tek sinif => `ml_no_model`). Kilit satiri -> LockWindowError (yapisal)."""
    assert_no_lock(rows)
    rows = sorted(rows, key=lambda r: (r["ts"], r.get("id", 0)))[-max_rows:]
    if not rows:
        return None
    y = np.array([1.0 if r["r"] > 0 else 0.0 for r in rows])
    if y.min() == y.max():
        return None
    names = F.choose_feature_names([r["x"] for r in rows])
    F.assert_no_label_features(names)
    X = F.matrix(names, [r["x"] for r in rows])
    model = fit_logistic(X, y)
    from trader_core.ml_eval import TreeModel
    p = TreeModel(model, {"a": 1.0, "b": 0.0}).predict_proba(X)
    base = float(y.mean())
    thr = float(THR_FRAC * base)
    lessons = sorted({n[5:] for n in names if n.startswith("ders:")})
    return build_package(arm_id, model, thr, names, train_start=rows[0]["ts"], train_end=rows[-1]["ts"], n_train=len(rows),
                         n_pos=int(y.sum()), data_hash=data_hash_of(rows), lock_dropped=0, base_rate=base, lesson_ids=lessons,
                         created_at=created_at)


def train_all(rows: Iterable[Mapping], *, created_at: datetime | None = None, max_rows: int = MAX_ROWS) -> tuple[dict, dict]:
    """Satirlari kolara bol; kilit satirlarini DUSUR (sayilir) ve egit. Donus: (paketler{arm}, rapor{arm: {...}})."""
    kept, dropped = drop_lock(rows)
    by: dict[str, list] = defaultdict(list)
    for r in kept:
        by[r["arm_id"]].append(r)
    pkgs, report = {}, {"lock_dropped": dropped, "arms": {}}
    for arm in sorted(by):
        pkg = train_arm(arm, by[arm], created_at=created_at, max_rows=max_rows)
        report["arms"][arm] = {"n": len(by[arm]), "status": "no_model" if pkg is None else "ok"}
        if pkg is not None:
            pkg["meta"]["lock_dropped"] = dropped
            pkgs[arm] = pkg
    return pkgs, report


def collect_rows(led, cf_path=None, *, asset_class_fn: Callable[[str], str] | None = None, bot: str = "learner") -> list[dict]:
    """Defter (salt okunur Ledger) + `counterfactual.sqlite` (varsa) + WP-09 not disa aktarimi -> egitim satirlari.
    Alinan: kapanan islem net R'si (cikis zamani = sonuc penceresi sonu). Alinmayan: `cf_outcomes` (barrier) `hyp_r_net`."""
    from trader_core import counterfactual as CF
    from trader_core import ledger as L
    from trader_core import trade_notes as TN
    outcomes: dict[int, tuple] = {}
    trades = led.list_closed_trades(limit=led.LIST_CLOSED_MAX)
    for t in trades:
        if t.r_multiple is not None:
            outcomes[t.decision_id] = (float(t.r_multiple), t.exit_ts)
    if cf_path is not None:
        try:
            with CF.CounterfactualStore(cf_path, read_only=True) as st:
                for r in st._db.execute("SELECT decision_id, hyp_r_net, window_end_ts FROM cf_outcomes WHERE bot=? AND method='barrier' "
                                        "AND hyp_r_net IS NOT NULL", (bot,)):
                    outcomes.setdefault(int(r["decision_id"]), (float(r["hyp_r_net"]), L._parse_ts(r["window_end_ts"])))
        except CF.CounterfactualError:
            pass                                          # depo yok: yalniz alinan islemlerle egit
    trade_of = {t.decision_id: t.trade_id for t in trades}
    decs = []
    for d in led.list_decisions():
        if d.id in outcomes and d.arm_id:
            decs.append({"id": d.id, "trade_id": trade_of.get(d.id), "arm_id": d.arm_id, "pair": d.pair, "side": d.side,
                         "regime": d.regime, "atr_ratio": d.atr_ratio, "session_tag": d.session_tag,
                         "lesson_ids": list(d.lesson_ids or ()), "features": dict(d.features), "planned_entry": d.planned_entry,
                         "planned_stop": d.planned_stop, "planned_target": d.planned_target, "rh_touches": d.rh_touches,
                         "rl_touches": d.rl_touches, "bar_close_ts": d.bar_close_ts})
    return build_rows(decs, outcomes, TN.export_ml_rows(led), asset_class_fn=asset_class_fn)
