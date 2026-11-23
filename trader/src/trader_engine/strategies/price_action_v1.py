"""PriceActionV1: `trader_core.signals` + `regime` sarmalayici (05 §13.4). Yeni mantik yoktur; v1b notrlemeleri
yalniz satir duzeyinde (hesap degismez). Parametre sozlugu ledger'dan turetilir (kopya deger yok)."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import timedelta

import pandas as pd

from trader_core import ledger as L
from trader_core import regime as R
from trader_core import signals as S

from .. import arm_guard as AG
from ..bars import STARTUP_BARS, STARTUP_BARS_4H, WINDOW_4H, WINDOW_TRIGGER, tf_delta
from .base import ParamSpec, StrategyContext, StrategyInfo, ExitPolicy

_OHLC = ["open", "high", "low", "close"]
_REENTRY_BLOCK = ("stop", "trail_stop")


def _param_specs() -> tuple[ParamSpec, ...]:
    out = []
    for name, d in L.PARAM_SPECS.items():
        lesson = name in L.LESSON_PARAMS
        kind = d["kind"]
        dflt = getattr(S.DEFAULT_SIGNAL_PARAMS, name)
        out.append(ParamSpec(
            name=name, kind="float" if kind == "float" else "choice",
            lo=d.get("lo"), hi=d.get("hi"), choices=d.get("choices"), default=dflt,
            lesson_adjustable=lesson,
            lesson_bounds=tuple(L.LESSON_BOUNDS_DEFAULT[name]) if lesson else None,
            step=L.LESSON_STEP[name] if lesson else None,
            scope=tuple(L.LESSON_SCOPE[name]) if lesson else None))
    return tuple(out)


class PriceActionV1:
    def __init__(self, *, name: str, version: str, setups_enabled: tuple[str, ...],
                 allowed_trigger_tfs: tuple[str, ...], block_same_bar_reentry: bool, paper_allowed: bool) -> None:
        self.setups_enabled = tuple(setups_enabled)
        self.block_same_bar_reentry = bool(block_same_bar_reentry)
        self.counters: Counter = Counter()
        self.info = StrategyInfo(
            name=name, version=version, setups=self.setups_enabled, timeframes=("trigger", "4h"),
            allowed_trigger_tfs=tuple(allowed_trigger_tfs),
            warmup_bars={"1h": STARTUP_BARS["1h"], "15m": STARTUP_BARS["15m"], "4h": STARTUP_BARS_4H},
            window_bars={"1h": WINDOW_TRIGGER["1h"], "15m": WINDOW_TRIGGER["15m"], "4h": WINDOW_4H},
            min_contiguous={"trigger": 20, "4h": 150},
            param_specs=_param_specs(), paper_allowed=paper_allowed)

    def label(self) -> str:
        """param_versions.reason etiketi (05 §13.6)."""
        return f"strategy:{self.info.name}@{self.info.version}"

    # -- protokol
    def validate_params(self, m: Mapping) -> Mapping:
        p = S.SignalParams.from_mapping(m)
        if p.trigger_tf not in self.info.allowed_trigger_tfs:
            raise ValueError(f"trigger_tf {p.trigger_tf!r} bu strateji icin izinli degil: {self.info.allowed_trigger_tfs}")
        return m

    def compute(self, ctx: StrategyContext) -> pd.DataFrame:
        params = S.SignalParams.from_mapping(ctx.params)
        trig = ctx.bars[ctx.tf]
        h4 = ctx.bars["4h"]
        reg = AG.regime_series(h4, params.regime_params())     # olu (hacim 0, o=h=l=c) mumlar gosterge girdisinden cikar; kriptoda eski yol AYNEN
        sig, _, _ = AG.core_signals(trig, reg, params)
        off = sig["setup"].notna() & ~sig["setup"].isin(list(self.setups_enabled))
        if bool(off.any()):
            sig.loc[off, "signal"] = False
            sig.loc[off, "skip_reason"] = None
            sig.loc[off, "reasons"] = "v1b:r1_disabled|" + sig.loc[off, "reasons"].astype(str)
            if bool(off.iloc[-1]):
                self.counters["shadow_r1"] += 1
        return sig

    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        if not (self.block_same_bar_reentry and ctx.last_exit is not None and bool(row["signal"])):
            return row
        ts, reason = ctx.last_exit
        bar_open = ctx.D - tf_delta(ctx.tf)
        if reason in _REENTRY_BLOCK and bar_open <= ts < ctx.D:
            r = row.copy()
            r["signal"] = False
            r["skip_reason"] = None
            r["reasons"] = "v1b:same_bar_reentry|" + str(row["reasons"])
            self.counters["shadow_reentry"] += 1
            return r
        return row

    def exit_policy(self) -> ExitPolicy | None:
        return None


def make_v1b() -> PriceActionV1:
    return PriceActionV1(name="price_action_v1", version="1b.0", setups_enabled=("T1",),
                         allowed_trigger_tfs=("1h",), block_same_bar_reentry=True, paper_allowed=True)


def make_v1_full() -> PriceActionV1:
    return PriceActionV1(name="price_action_v1_full", version="1.0", setups_enabled=("T1", "R1"),
                         allowed_trigger_tfs=("1h", "15m"), block_same_bar_reentry=False, paper_allowed=False)
