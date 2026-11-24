"""M1: ML'in kendi adayi (DD-12 WP-14; spec 5.3). Aday, `trader_ml.pa_proposer` modelinin puanindan uretilir.

Paket yok / suresi dolmus / model yuklenemedi -> aday yok (motor calisir; D-T22). Paket kapi/onay aramaz (kagit, spec 5).
Yalniz karar barina (son kapanmis bar) puan verilir; long ve short ayni barda puanlanir, en yuksek esigi gecen yon secilir.
Stop = giris -/+ 1,5 ATR, hedef = giris +/- 3 ATR (egitim etiketiyle ayni kurallar). Esik altı/iki yon de esikte: aday yok.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from trader_core.ml_live_v2 import setup_feature_vector
from trader_core.ml_package import PackageSet
import pandas as pd
from trader_core.signals import SIGNAL_COLUMNS


def empty_output(index) -> pd.DataFrame:
    """SIGNAL_COLUMNS sutunlu, `index` uzunlugunda hic sinyal yok tablosu (signal=False; aday alanlari NaN).
    signals.py dondurulmus oldugu icin burada (M1'e ozel) tutulur."""
    n = len(index)
    obj = np.full(n, None, dtype=object)
    data = {c: np.full(n, np.nan) for c in SIGNAL_COLUMNS}
    data.update({"setup": obj, "side": obj.copy(), "skip_reason": obj.copy(), "regime": obj.copy(),
                 "reasons": np.full(n, "", dtype=object), "signal": np.zeros(n, dtype=bool),
                 "rh_touches": np.zeros(n, dtype="int64"), "rl_touches": np.zeros(n, dtype="int64"),
                 "pullback_ema": np.zeros(n, dtype="int64")})
    return pd.DataFrame({c: data[c] for c in SIGNAL_COLUMNS}, index=index)[SIGNAL_COLUMNS]
from trader_core import pa_features as PF

from . import ArmInput
from . import _pa as P

SETUP = "M1"
TIMEFRAMES = ("1h", "4h", "15m", "1d")   # spec: 1s ilk; her zaman dilimi kendi paketi (M1@<tf>.json); paket yoksa aday yok
CORE = False
EXIT_MODE = "target"
PRIORITY = 90
FEATURES = {"m1_body": "body_ratio", "m1_wick": "wick_ratio", "m1_rr": "rr"}
_REPO_ROOT = Path(__file__).resolve().parents[4]
SEED_MODELS_DIR = _REPO_ROOT / "models" / "pa_proposer"   # depodaki tohum paketler (salt okunur; asla yazilmaz)
# calisma zamani paketleri (gece egitimi burayi yazar); TRADER_ML_RUNTIME_DIR ile degistirilebilir (test/ozel kurulum)
MODELS_DIR = Path(os.environ.get("TRADER_ML_RUNTIME_DIR") or (_REPO_ROOT / "var" / "learner" / "models")) / "pa_proposer"
RR = PF.TARGET_ATR / PF.STOP_ATR

_PS = PackageSet(MODELS_DIR, fallback_dirs=(SEED_MODELS_DIR,))


def compute(inp: ArmInput):
    arm_id = f"{SETUP}@{inp.tf}"
    _PS.reload(now=inp.D)
    view = _PS.view(arm_id)
    # Paket yok / suresi dolmus: aday yok; kurulum tablosu (core) hic hesaplanmaz ve okunmaz (D-T22).
    if view is None or view.expired(inp.D):
        return empty_output(inp.trig.index)
    core = inp.core()
    if core is None:                 # ortak tablo yok: aday yok (kurulum engellenmez)
        return empty_output(inp.trig.index)
    p = P.prepare(inp, core)
    tab = P.Table(p.core)
    n = len(p.c)
    i = n - 1
    if n < PF.WINDOW or not bool(p.ok[i]):
        return tab.frame()
    best = None
    for side in P.SIDES:
        x = PF.feature_vector(p.o, p.h, p.l, p.c, i, side)
        if x is None:
            continue
        score = float(view.score(setup_feature_vector(view.features, dict(zip(PF.FEATURE_NAMES, x.tolist())))[None, :])[0])
        if np.isfinite(score) and score >= view.threshold and (best is None or score > best[1]):
            best = (side, score)
    if best is None:
        return tab.frame()
    side, score = best
    atr = PF.atr_at(p.h, p.l, p.c, i)
    s = P.SIGN[side]
    entry = float(p.c[i])
    stop = entry - s * PF.STOP_ATR * atr
    target = entry + s * PF.TARGET_ATR * atr
    body = float(abs(p.c[i] - p.o[i]) / (p.h[i] - p.l[i]))
    wick = float((p.h[i] - max(p.o[i], p.c[i])) / (p.h[i] - p.l[i])) if side == "long" else \
        float((min(p.o[i], p.c[i]) - p.l[i]) / (p.h[i] - p.l[i]))
    tab.put(i, setup=SETUP, side=side, skip=None, labels=["m1", f"p={score:.3f}"], entry=entry, stop=stop, target=target,
            rr=RR, sda=PF.STOP_ATR, ema=np.nan, body=body, wick=wick, edge=np.nan, pb=0)
    return tab.frame()
