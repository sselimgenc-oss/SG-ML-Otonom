"""Kilitli donem korumasi (§3.1, §8): egitim/arastirma kodu 2026-05-01 ve sonrasini okumaz."""
from __future__ import annotations

import pandas as pd

from .config import HOLDOUT_START, KILIT_ACIK


class HoldoutViolation(RuntimeError):
    """Kilitli doneme (>= 2026-05-01 UTC) ait veri egitim koduna girmeye calisti."""


def _utc(ts) -> pd.Series | pd.DatetimeIndex:
    if isinstance(ts, pd.DatetimeIndex):
        return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")
    s = pd.to_datetime(pd.Series(ts), utc=True)
    return s


def assert_pre_holdout(ts, what: str = "veri") -> None:
    """ts (Series/Index/liste) icinde HOLDOUT_START ve sonrasi varsa HoldoutViolation."""
    if KILIT_ACIK:                       # 23.11.2026 kullanici karari: kilit acik
        return
    t = _utc(ts)
    if len(t) == 0:
        return
    mx = t.max()
    if pd.notna(mx) and mx >= HOLDOUT_START:
        raise HoldoutViolation(f"{what}: kilitli donem verisi okunamaz (max={mx}, sinir={HOLDOUT_START})")


def clip_to_train_window(df: pd.DataFrame, ts_col: str | None = None) -> pd.DataFrame:
    """Yalniz kaynak katmani (19b disa aktarimi) icin: kilitli satirlari atar. Egitim yollari
    bunu KULLANMAZ; onlar assert_pre_holdout ile hata verir."""
    if KILIT_ACIK:
        return df
    t = _utc(df.index if ts_col is None else df[ts_col])
    return df[(t < HOLDOUT_START).to_numpy()]
