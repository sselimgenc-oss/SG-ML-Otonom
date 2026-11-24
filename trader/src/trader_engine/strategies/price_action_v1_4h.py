"""PriceActionV1H4 (S2-1, docs/ml/s2-on-kayit.md §5): v1b kurallari, tetik mumu 4 saatlik. Motor adimi 1 saatlik kalir;
4 saatlik sinyal, kapanisi 4 saatlik kapanisa denk gelen 1 saatlik satira kopyalanir. Yeni sinyal mantigi yoktur."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import timedelta

import numpy as np
import pandas as pd

from trader_core import signals as S

from .. import arm_guard as AG
from .. import position_manager as PM
from ..bars import STARTUP_BARS, STARTUP_BARS_4H, WINDOW_4H, WINDOW_TRIGGER
from ..position_manager import ExitContext, ExitDecision
from ..types import Position
from .base import ExitPolicy, StrategyContext, StrategyInfo
from .price_action_v1 import _OHLC, _REENTRY_BLOCK, _param_specs

_H4 = timedelta(hours=4)
_SHIFT = timedelta(hours=3)
_TEXT_COLS = ("setup", "side", "skip_reason", "regime")
_NUM_COLS = tuple(c for c in S.SIGNAL_COLUMNS if c not in _TEXT_COLS and c not in ("signal", "reasons"))


class H4ExitPolicy:
    """Cikis kararini 4 saatlik gruplara toplayip motorun `evaluate_exit`'ine verir (§5 madde evaluate)."""

    def evaluate(self, pos: Position, ctx: ExitContext | None) -> ExitDecision:
        if ctx is None:
            return PM.evaluate_exit(pos, None)
        if len(ctx.atrs) == 0 or not np.isfinite(ctx.atrs[-1]):
            return ExitDecision("none")
        gh: list[float] = []
        gl: list[float] = []
        ga: list[float] = []
        run_h = -np.inf
        run_l = np.inf
        for h, l, a in zip(ctx.highs, ctx.lows, ctx.atrs):
            if not np.isnan(h):
                run_h = max(run_h, float(h))
            if not np.isnan(l):
                run_l = min(run_l, float(l))
            if np.isfinite(a):
                gh.append(run_h)
                gl.append(run_l)
                ga.append(float(a))
                run_h = -np.inf
                run_l = np.inf
        ctx4 = ExitContext(bar_close_ts=ctx.bar_close_ts, highs=np.asarray(gh, dtype=float),
                           lows=np.asarray(gl, dtype=float), atrs=np.asarray(ga, dtype=float),
                           regime_last=ctx.regime_last, last_close=ctx.last_close, n_closed=len(ga))
        return PM.evaluate_exit(pos, ctx4)


class PriceActionV1H4:
    def __init__(self) -> None:
        self.setups_enabled = ("T1",)
        self.counters: Counter = Counter()
        self.info = StrategyInfo(
            name="price_action_v1_4h", version="s2-1.0", setups=self.setups_enabled,
            timeframes=("trigger", "4h"), allowed_trigger_tfs=("1h",),
            warmup_bars={"1h": STARTUP_BARS["1h"], "15m": STARTUP_BARS["15m"], "4h": STARTUP_BARS_4H},
            window_bars={"1h": WINDOW_TRIGGER["1h"], "15m": WINDOW_TRIGGER["15m"], "4h": WINDOW_4H},
            min_contiguous={"trigger": 20, "4h": 150},
            param_specs=_param_specs(), paper_allowed=False)

    def label(self) -> str:
        return f"strategy:{self.info.name}@{self.info.version}"

    def validate_params(self, m: Mapping) -> Mapping:
        p = S.SignalParams.from_mapping(m)
        if p.trigger_tf != "1h":
            raise ValueError(f"trigger_tf {p.trigger_tf!r} bu strateji icin izinli degil: {self.info.allowed_trigger_tfs}")
        return m

    def compute(self, ctx: StrategyContext) -> pd.DataFrame:
        params = S.SignalParams.from_mapping(ctx.params)
        trig = ctx.bars[ctx.tf]
        h4 = ctx.bars["4h"]
        reg = AG.regime_series(h4, params.regime_params())     # olu (hacim 0, o=h=l=c) mumlar gosterge girdisinden cikar; kriptoda eski yol AYNEN
        sig4, _, _ = AG.core_signals(h4, reg, params)
        off = sig4["setup"].notna() & ~sig4["setup"].isin(list(self.setups_enabled))
        if bool(off.any()):
            sig4.loc[off, "signal"] = False
            sig4.loc[off, "skip_reason"] = None
            sig4.loc[off, "reasons"] = "v1b:r1_disabled|" + sig4.loc[off, "reasons"].astype(str)
            if bool(off.iloc[-1]):
                self.counters["shadow_r1"] += 1
        # 4 saatlik satir (acilis T) -> 1 saatlik satir (acilis T + 3s)
        src = sig4.copy()
        src.index = src.index + _SHIFT
        keep = src.index.isin(trig.index)
        src = src[keep]
        out = src.reindex(trig.index)
        mapped = trig.index.isin(src.index)
        off_grid = ~mapped
        out["signal"] = np.where(mapped, out["signal"].fillna(False).astype(bool), False).astype(bool)
        for c in _NUM_COLS:
            out[c] = out[c].astype("float64")
        for c in _TEXT_COLS:
            col = out[c].astype(object)
            col[off_grid] = None
            col = col.where(col.notna(), None)
            out[c] = col
        reasons = out["reasons"].astype(object)
        reasons[off_grid] = "s2_1:off_grid"
        out["reasons"] = reasons
        return out[S.SIGNAL_COLUMNS]

    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        if not (ctx.last_exit is not None and bool(row["signal"])):
            return row
        ts, reason = ctx.last_exit
        bar_open = ctx.D - _H4
        if reason in _REENTRY_BLOCK and bar_open <= ts < ctx.D:
            r = row.copy()
            r["signal"] = False
            r["skip_reason"] = None
            r["reasons"] = "v1b:same_bar_reentry|" + str(row["reasons"])
            self.counters["shadow_reentry"] += 1
            return r
        return row

    def exit_policy(self) -> ExitPolicy | None:
        return H4ExitPolicy()


def make_v1b_4h() -> PriceActionV1H4:
    return PriceActionV1H4()
