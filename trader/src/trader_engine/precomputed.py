"""Backtest sinyal kaynagi ve ileriye-bakma kilidi (06 §3.1-3.3): PrecomputedSignalSource, GuardedView, LedgerReplayVeto.
Ayri strateji/dolum kodu yoktur: strateji `Strategy.compute/post_filter` ayni, yalniz hesap cift basina bir kez yapilir."""
from __future__ import annotations

import math
import sqlite3
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd


from .bars import tf_delta, to_ms
from .clock import Clock
from .errors import DataError, EngineError
from .gates import VetoLookup
from .marketdata.sources import MarketView, MinuteStep
from .position_manager import ExitContext
from .strategies.base import Strategy, StrategyContext, StrategyError, validate_row, validate_table
from .strategy_runner import SignalFrame, SignalRow, _OHLC, _to_row, _text
from .types import FundingPoint, Kind, Position, SymbolRules, canon_pair


class LookaheadError(EngineError):
    """Saatten ileri veri okuma girisimi (06 §3.2) ya da kesme/paranoid denetimi ihlali."""


# ------------------------------------------------------------------------------------------ GuardedView
class GuardedView:
    """MarketView sarmalayici: her okuma `until/end <= clock.now()` degilse LookaheadError."""

    def __init__(self, view: MarketView, clock: Clock, *, fill_model: str = "native") -> None:
        self._v = view
        self._clock = clock
        self._compat = fill_model == "legacy_compat"
        self.peek_uses = 0
        self.checks = 0
        self._rules: dict[str, SymbolRules] = {}       # kurallar sabit: tekrar turetme (sentetik kurallar pahali)

    # -- yardimci
    def _need(self, t: datetime, what: str) -> None:
        self.checks += 1
        now = self._clock.now()
        if t > now:
            raise LookaheadError(f"{what}: {t.isoformat()} > saat {now.isoformat()}")

    # -- MarketView
    def bars(self, pair: str, tf: str, until: datetime, n: int | None = None, kind: Kind = "last") -> pd.DataFrame:
        self._need(until, f"bars({pair},{tf})")
        return self._v.bars(pair, tf, until, n, kind)

    def contiguous_tail(self, pair: str, tf: str, until: datetime, max_n: int = 5000) -> int:
        self._need(until, f"contiguous_tail({pair},{tf})")
        return self._v.contiguous_tail(pair, tf, until, max_n)

    def minute_steps(self, pairs: Sequence[str], start: datetime, end: datetime) -> Iterator[MinuteStep]:
        self._need(start, "minute_steps.start")
        for st in self._v.minute_steps(pairs, start, end):
            # adim acilisi saatin onune gecemez (surucu saati adim sonuna ilerletir)
            self._need(st.ts, f"minute_steps adim {st.ts.isoformat()}")
            yield st

    def funding(self, pair: str, start: datetime, end: datetime) -> list[FundingPoint]:
        self._need(end, f"funding({pair})")
        return self._v.funding(pair, start, end)

    def rules(self, pair: str) -> SymbolRules:
        r = self._rules.get(pair)
        if r is None:
            r = self._rules[pair] = self._v.rules(pair)
        return r

    def last_closed_minute(self, pair: str) -> datetime | None:
        return self._v.last_closed_minute(pair)

    def data_range(self, pair: str, tf: str) -> tuple[datetime, datetime] | None:
        return self._v.data_range(pair, tf)

    def step_seconds(self) -> int:
        return self._v.step_seconds()

    # -- uyum kipi istisnasi
    def open_at(self, pair: str, ts: datetime) -> float:
        if not self._compat:
            raise LookaheadError("open_at yalniz fill_model='legacy_compat' ile kullanilabilir")
        self._need(ts, f"open_at({pair})")
        self.peek_uses += 1
        return self._v.open_at(pair, ts)                                   # type: ignore[attr-defined]

    def tick_at(self, pair: str, ts: datetime) -> float:
        """Aylik tarihsel tick (referans sozlesmesi); ayin tum mumlarina bakar => yalniz uyum kipi."""
        if not self._compat:
            raise LookaheadError("tick_at yalniz fill_model='legacy_compat' ile kullanilabilir")
        return self._v.tick_at(pair, ts)                                   # type: ignore[attr-defined]

    def __getattr__(self, name: str):
        return getattr(self._v, name)


# ------------------------------------------------------------------------------------------ PrecomputedSignalSource
class _PairTable:
    __slots__ = ("pair", "ms", "run", "recs", "table", "high", "low", "atr", "regime", "close", "ms4", "run4")

    def __init__(self) -> None:
        pass


def _runs(ms: np.ndarray, step_ms: int) -> np.ndarray:
    n = len(ms)
    out = np.ones(n, dtype=np.int64)
    if n > 1:
        ok = np.diff(ms) == step_ms
        for i in range(1, n):
            out[i] = out[i - 1] + 1 if ok[i - 1] else 1
    return out


class PrecomputedSignalSource:
    """`strategy.compute` cift basina BIR kez (tum gecmis, `end`'e kadar kesilmis); `frame()` tablo satirini okur."""

    def __init__(self, view: MarketView, strategy: Strategy, *, pairs: Sequence[str], tf: str,
                 params: Mapping[str, object], version_id: int, end: datetime, strict: bool = True,
                 last_exit_fn: Callable[[str, datetime], tuple[datetime, str] | None] | None = None) -> None:
        self.view = view
        self.strategy = strategy
        self.tf = tf
        self.params = dict(params)
        self.params["trigger_tf"] = tf
        self.version_id = int(version_id)
        self.end = end
        self.strict = strict
        self.last_exit_fn = last_exit_fn
        self.counters: Counter = Counter()
        self._t: dict[str, _PairTable] = {}
        self.build_errors: dict[str, str] = {}
        info = strategy.info
        if tf not in info.allowed_trigger_tfs:
            raise StrategyError("bad_table", f"trigger_tf izinli degil: {tf}")
        self._tf_ms = int(tf_delta(tf).total_seconds() * 1000)
        self._h4_ms = int(tf_delta("4h").total_seconds() * 1000)
        for pair in pairs:
            try:
                self._t[pair] = self._build_pair(pair)
            except DataError:
                raise
            except Exception as e:  # noqa: BLE001
                if strict:
                    raise
                self.build_errors[pair] = f"{type(e).__name__}: {e}"
                self.counters["errors"] += 1

    # ------------------------------------------------------------------ kurucu hesap
    def _build_pair(self, pair: str) -> _PairTable:
        info = self.strategy.info
        tf = self.tf
        trig = self.view.bars(pair, tf, self.end, None)
        h4 = self.view.bars(pair, "4h", self.end, None)
        bars = {tf: trig, "4h": h4}
        ctx = StrategyContext(pair=pair, D=self.end, tf=tf, params=self.params, bars=bars, last_exit=None)
        sig = self.strategy.compute(ctx)
        validate_table(sig, info, trig.index)
        t = _PairTable()
        t.pair = pair
        t.ms = _ms_of(trig.index)
        t.ms4 = _ms_of(h4.index)
        t.run = _runs(t.ms, self._tf_ms)
        t.run4 = _runs(t.ms4, self._h4_ms)
        t.table = sig.join(trig[_OHLC])
        t.recs = sig.to_dict("records")
        t.high = trig["high"].to_numpy(dtype=float)
        t.low = trig["low"].to_numpy(dtype=float)
        t.close = trig["close"].to_numpy(dtype=float)
        t.atr = sig["atr_tf"].to_numpy(dtype=float)
        t.regime = sig["regime"].to_numpy(dtype=object)
        return t

    # ------------------------------------------------------------------ SignalSource
    def _bad(self, pair: str, status: str, detail: str, *, error: bool = False) -> SignalFrame:
        self.counters["errors" if error else status] += 1
        return SignalFrame(pair=pair, status=status, detail=detail, last=None, table=None)  # type: ignore[arg-type]

    def _locate(self, pair: str, D: datetime) -> tuple[_PairTable | None, int, SignalFrame | None]:
        info = self.strategy.info
        t = self._t.get(pair)
        if t is None:
            return None, -1, self._bad(pair, "error", self.build_errors.get(pair, "pair_not_built"), error=True)
        d_ms = to_ms(D)
        k = int(np.searchsorted(t.ms, d_ms - self._tf_ms, side="right"))        # D oncesi kapanmis bar sayisi
        k4 = int(np.searchsorted(t.ms4, d_ms - self._h4_ms, side="right"))
        if k < info.warmup_bars[self.tf]:
            return t, -1, self._bad(pair, "no_history", f"{self.tf}:{k}<{info.warmup_bars[self.tf]}")
        if k4 < info.warmup_bars["4h"]:
            return t, -1, self._bad(pair, "no_history", f"4h:{k4}<{info.warmup_bars['4h']}")
        if k == 0 or int(t.ms[k - 1]) != d_ms - self._tf_ms:
            return t, -1, self._bad(pair, "data_gap", "trigger_bar_missing")
        if int(t.run[k - 1]) < info.min_contiguous["trigger"] or int(t.run4[k4 - 1]) < info.min_contiguous["4h"]:
            return t, -1, self._bad(pair, "data_gap", "hole")
        return t, k - 1, None

    def frame(self, pair: str, D: datetime, params, version_id: int) -> SignalFrame:
        if int(version_id) != self.version_id:
            raise EngineError("params_changed_during_backtest")
        try:
            t, i, bad = self._locate(pair, D)
            if bad is not None:
                return bad
            rec = t.recs[i]
            if bool(rec["signal"]):
                last_exit = self.last_exit_fn(pair, D) if self.last_exit_fn is not None else None
                fctx = StrategyContext(pair=pair, D=D, tf=self.tf, params=self.params, bars={}, last_exit=last_exit)
                srow = pd.Series(rec)
                last_row = self.strategy.post_filter(srow, fctx)
                validate_row(last_row, self.strategy.info)
                if bool(last_row["signal"]) and not bool(rec["signal"]):
                    raise StrategyError("bad_table", "post_filter aday ekleyemez")
                if bool(last_row["signal"]):
                    for k in ("planned_entry", "planned_stop", "planned_target", "setup", "side"):
                        a, b = last_row[k], rec[k]
                        same = (a == b) or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))
                        if not same:
                            raise StrategyError("bad_table", f"post_filter {k} degistiremez")
                src = dict(rec)
                for c in ("signal", "skip_reason", "reasons"):
                    src[c] = last_row[c]
            else:
                src = rec
            open_ts = datetime.fromtimestamp(int(t.ms[i]) / 1000, tz=timezone.utc)
            row = _to_row(pair, open_ts, D, src, self.version_id)               # type: ignore[arg-type]
            return SignalFrame(pair=pair, status="ok", detail=None, last=row, table=None)
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self.counters["callback_errors"] += 1
            return self._bad(pair, "error", f"{type(e).__name__}: {e}", error=True)

    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None:
        t = self._t.get(pair)
        if t is None or pos.entry_bar_open is None:
            return None
        d_ms = to_ms(D)
        k = int(np.searchsorted(t.ms, d_ms - self._tf_ms, side="right"))
        if k == 0 or int(t.ms[k - 1]) != d_ms - self._tf_ms:
            return None
        lo = int(np.searchsorted(t.ms, to_ms(pos.entry_bar_open), side="left"))
        return ExitContext(bar_close_ts=D, highs=t.high[lo:k], lows=t.low[lo:k], atrs=t.atr[lo:k],
                           regime_last=_text(t.regime[k - 1]), last_close=float(t.close[k - 1]), n_closed=k - lo)

    def frame_table(self, pair: str, D: datetime) -> pd.DataFrame | None:
        """Paranoid/test: D'ye kadar kesilmis tablo (yalniz kapanmis barlar)."""
        t = self._t.get(pair)
        if t is None:
            return None
        k = int(np.searchsorted(t.ms, to_ms(D) - self._tf_ms, side="right"))
        return t.table.iloc[:k]


def _ms_of(idx: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(idx.tz_convert("UTC").tz_localize(None).values.astype("datetime64[ms]").astype("int64"))


# ------------------------------------------------------------------------------------------ LedgerReplayVeto
class LedgerReplayVeto:
    """Paper ledger'inin `decision_events` kayitlarindan veto durumunu tekrar oynatir (salt okunur)."""

    def __init__(self, path) -> None:
        self.path = str(path)
        self._c = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        self._map: dict[tuple[str, str, str], tuple[str, str | None]] = {}
        for pair, side, ts, st, rs in self._c.execute(
                "SELECT pair, side, bar_close_ts, veto_status, veto_reason FROM v_decisions"):
            self._map[(pair, side, ts)] = (st, rs)
        self._c.close()
        self.counters: Counter = Counter()
        self.no_paper_record: list[tuple[str, str, str]] = []

    @staticmethod
    def _iso(now: datetime) -> str:
        return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    def begin_step(self, now: datetime) -> None:
        return None

    def lookup(self, pair: str, side: str, now: datetime) -> VetoLookup:
        key = (canon_pair(pair), side, self._iso(now))
        rec = self._map.get(key)
        if rec is None:
            self.counters["no_paper_record"] += 1
            self.no_paper_record.append(key)
            return VetoLookup("missing", "no_paper_record", True)
        st, rs = rec
        if st == "not_evaluated":                       # paper'da kapi kapaliydi (paper_gap): veto verisi yok
            self.counters["not_evaluated"] += 1
            return VetoLookup("allowed", rs or "not_evaluated:replay", False)
        return VetoLookup(st, rs, st != "allowed")
