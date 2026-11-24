"""Takilabilir strateji arayuzu (05 §13.2-13.3): protokoller, sema dogrulamasi. Strateji yalniz aday tablosu uretir;
boyut, kaldirac, emir, ledger, state, saat ve ag gormez."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import pandas as pd

from trader_core.signals import SIGNAL_COLUMNS

from ..position_manager import ExitContext, ExitDecision
from ..types import Position

_SKIP_OK = (None, "stop_width", "rr_below_min")


class StrategyError(Exception):
    """Strateji kayit/yukleme/uyum hatasi; `code` makine tarafindan okunur."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: Literal["float", "int", "choice"]
    lo: float | None
    hi: float | None
    choices: tuple | None
    default: object
    lesson_adjustable: bool
    lesson_bounds: tuple[float, float] | None
    step: float | None
    scope: tuple[str, ...] | None


@dataclass(frozen=True)
class StrategyInfo:
    name: str
    version: str
    setups: tuple[str, ...]
    timeframes: tuple[str, ...]
    allowed_trigger_tfs: tuple[str, ...]
    warmup_bars: Mapping[str, int]
    window_bars: Mapping[str, int]
    min_contiguous: Mapping[str, int]
    param_specs: tuple[ParamSpec, ...]
    paper_allowed: bool


@dataclass(frozen=True)
class StrategyContext:
    pair: str
    D: datetime
    tf: str
    params: Mapping[str, object]
    bars: Mapping[str, pd.DataFrame]
    last_exit: tuple[datetime, str] | None = None


class ExitPolicy(Protocol):
    def evaluate(self, pos: Position, ctx: ExitContext | None) -> ExitDecision: ...


class Strategy(Protocol):
    info: StrategyInfo

    def validate_params(self, m: Mapping) -> Mapping: ...

    def compute(self, ctx: StrategyContext) -> pd.DataFrame: ...

    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series: ...

    def exit_policy(self) -> ExitPolicy | None: ...


def _fin_pos(x) -> bool:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0


def _bad(msg: str) -> StrategyError:
    return StrategyError("bad_table", msg)


def validate_row(row: pd.Series, info: StrategyInfo) -> None:
    """Tek satir sema denetimi (§13.3). Ihlal -> StrategyError('bad_table')."""
    side = row["side"]
    if side is not None and not (isinstance(side, str) and side in ("long", "short")):
        raise _bad(f"side gecersiz: {side!r}")
    sr = row["skip_reason"]
    if sr is not None and not (isinstance(sr, str) and sr in _SKIP_OK):
        raise _bad(f"skip_reason gecersiz: {sr!r}")
    if bool(row["signal"]):
        if row["setup"] not in info.setups:
            raise _bad(f"setup {row['setup']!r} info.setups disinda")
        if side is None:
            raise _bad("signal=True iken side bos")
        e, s = row["planned_entry"], row["planned_stop"]
        if not (_fin_pos(e) and _fin_pos(s)):
            raise _bad("signal=True iken planned_entry/planned_stop sonlu ve pozitif olmali")
        e, s = float(e), float(s)
        if (side == "long" and not s < e) or (side == "short" and not s > e):
            raise _bad("stop yanlis tarafta")
        t = row["planned_target"]
        if t is not None and not (isinstance(t, float) and math.isnan(t)):
            if not _fin_pos(t) or (side == "long" and not float(t) > e) or (side == "short" and not float(t) < e):
                raise _bad("planned_target yanlis tarafta")


def validate_table(df: pd.DataFrame, info: StrategyInfo, index: pd.Index | None = None) -> None:
    """compute ciktisinin tam sema denetimi (§13.3). `index` verilirse uzunluk/indeks esitligi aranir."""
    if not isinstance(df, pd.DataFrame):
        raise _bad("DataFrame bekleniyor")
    cols = set(df.columns)
    want = set(SIGNAL_COLUMNS)
    if cols != want:
        raise _bad(f"sutun kumesi hatali: fazla={sorted(cols - want)} eksik={sorted(want - cols)}")
    if index is not None and (len(df) != len(index) or not df.index.equals(index)):
        raise _bad("indeks/uzunluk ctx.bars ile ayni degil")
    if len(df) == 0:
        return
    side = df["side"]
    if not side.map(lambda x: x is None or (isinstance(x, str) and x in ("long", "short"))).all():
        raise _bad("side gecersiz")
    if not df["skip_reason"].map(lambda x: x is None or (isinstance(x, str) and x in _SKIP_OK)).all():
        raise _bad("skip_reason gecersiz")
    sig = df["signal"].astype(bool)
    if not bool(sig.any()):
        return
    s = df[sig]
    if not s["setup"].isin(list(info.setups)).all():
        raise _bad("signal=True satirinda setup info.setups disinda")
    if s["side"].isna().any():
        raise _bad("signal=True iken side bos")
    e = s["planned_entry"].astype(float)
    st = s["planned_stop"].astype(float)
    import numpy as np
    if not (np.isfinite(e).all() and np.isfinite(st).all() and (e > 0).all() and (st > 0).all()):
        raise _bad("signal=True iken planned_entry/planned_stop sonlu ve pozitif olmali")
    lg = s["side"] == "long"
    if not ((st[lg] < e[lg]).all() and (st[~lg] > e[~lg]).all()):
        raise _bad("stop yanlis tarafta")
    t = s["planned_target"].astype(float)
    has = t.notna()
    if has.any():
        if not (np.isfinite(t[has]).all() and (t[has] > 0).all()):
            raise _bad("planned_target sonlu degil")
        if not ((t[has & lg] > e[has & lg]).all() and (t[has & ~lg] < e[has & ~lg]).all()):
            raise _bad("planned_target yanlis tarafta")
