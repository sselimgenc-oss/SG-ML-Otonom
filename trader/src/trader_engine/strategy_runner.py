"""Sinyal kaynagi (05 §3): MarketView'dan pencere cekip stratejiyi calistirir (eski adaptorun populate_indicators
karsiligi). Hata o cifte ozgudur; giris yok, cikislar etkilenmez."""
from __future__ import annotations

import dataclasses
import logging
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import numpy as np
import pandas as pd

from trader_core import ledger as L
from trader_core.signals import SignalParams

from . import arm_guard as AG
from .arm_quarantine import unit_for
from .errors import is_strategy_error
from .bars import (ARM_TFS, BARS_PER_DAY_4H, MIN_CONTIG_ARM, STARTUP_BARS_ARM, WINDOW_ARM, aggregate_4h_to_1d, arm_closing_tfs,
                   arm_tf_delta, tf_delta)
from .marketdata.sources import MarketView
from .position_manager import ExitContext
from .strategies.arms import ArmInput, exit_rule_of, priority_of
from .strategies.base import Strategy, StrategyContext, StrategyError, validate_row, validate_table
from .types import Position
from .vol_tahmin import vol_ozellikleri

log = logging.getLogger("engine.runner")
_OHLC = ["open", "high", "low", "close"]
_FILTERED_SKIPS = ("stop_width", "rr_below_min")   # gates._FILTERED_SKIPS ile ayni (kaydedilen elenmis adaylar)


@dataclass(frozen=True)
class SignalRow:
    pair: str
    bar_open_ts: datetime
    bar_close_ts: datetime
    signal: bool
    setup: str | None
    side: str | None
    skip_reason: str | None
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    rr: float | None
    stop_dist_atr: float | None
    atr_tf: float | None
    atr_4h: float | None
    atr_ratio: float | None
    regime: str
    rh: float | None
    rl: float | None
    rh_touches: int
    rl_touches: int
    ema_value: float | None
    body_ratio: float | None
    wick_ratio: float | None
    edge_dist_atr: float | None
    pullback_ema: int
    reasons: str
    param_version_id: int
    arm_id: str | None = None              # DD-12 WP-11: bilesik strateji satiri `<kurulum>@<tf>`; tekli stratejide None
    tf: str | None = None                  # DD-12 WP-11: satirin tetik zaman dilimi; tekli stratejide None (bar suresinden bulunur)
    vol_tahmin: float | None = None        # fikir 10: GJR oynaklik tahmini / ATR oynakligi (yalniz gece suzgecinin ek ozelligi)
    vol_asim: float | None = None          # fikir 10: oynaklik asimetrisi (kaldirac bileseni), [-1, 1]


@dataclass(frozen=True)
class SignalFrame:
    pair: str
    status: Literal["ok", "no_history", "data_gap", "error"]
    detail: str | None
    last: SignalRow | None
    table: pd.DataFrame | None
    trigger_bar: tuple[float, float, float] | None = None   # DD-12 WP-04: (high, low, volume) son kapanmis tetik bari; yoksa None
    extras: tuple["SignalFrame", ...] = ()                  # DD-12 WP-11: ayni adimda baska kurulumlarin adaylari (onceliksirali)


class SignalSource(Protocol):
    def frame(self, pair: str, D: datetime, params: SignalParams, version_id: int) -> SignalFrame: ...

    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None: ...


_WIDEN_MAX = 8        # seansli enstrumanda pencereyi en cok bu kadar katina genisletir (olu mum orani <= %87)
_WIDEN_MAX_1D = 3     # 1g yolu (4s'ten toplanir): dolu gun orani >= %33 varsayilir (hisse ~%71): en cok 3 x pencere gun okunur
_RETRY_MARGIN = 1.15  # tek yeniden okumada tahmine eklenen pay (daha eski gecmis biraz daha olu olabilir)
_LIVE_FRAC: dict[tuple[str, str], float] = {}     # (cift, tf) -> son gozlenen dolu bar orani; YALNIZ ilk okuma boyunu secer (sonuc degismez)


def _live_window(fetch, n: int, key: tuple[str, str], cap_mult: int = _WIDEN_MAX) -> pd.DataFrame:
    """Son `n` DOLU bari (+ aralarindaki olu mumlari) dondurur. `fetch(m) -> (tablo, bitti)` en cok `m` son birimi verir; `bitti` = depodaki gecmis
    tukendi (ham satir sayisina gore; 1g'de delikli gun atilsa da dogru). Okuma: ilk + tek yeniden okuma, gerekirse tavana kadar ucuncu
    okuma => sonuc yalniz (depo, D, n, tavan)'in fonksiyonu. Ilk okuma boyu: o cift/tf icin daha once gozlenen dolu orandan (`_LIVE_FRAC`; yoksa/kriptoda n); yeniden
    okuma boyu: gozlenen orandan (+pay). Sonuc ilk okuma boyuna BAGLI DEGIL (tail_active ayni son n dolu bari verir) => canli/geri test
    ayni. Gecmis yetmezse (depo bitti) ya da tavana (`cap_mult` x n) varildiysa n'den AZ dolu bar donebilir: bilincli, hata degil."""
    cap = n * cap_mult
    hint = _LIVE_FRAC.get(key, 1.0)
    m = n if hint >= 1.0 else min(cap, int(math.ceil(n / hint * 1.1)) + 32)
    df, ex = fetch(m)
    keep = AG.active_mask(df)
    if keep is None:
        if len(df):
            _LIVE_FRAC[key] = 1.0
        return df.iloc[-n:]
    got = int(keep.sum())
    if len(df):
        _LIVE_FRAC[key] = max(got, 1) / len(df)
    if got >= n or ex or m >= cap:                          # yeterli / magazadaki tum gecmis okundu / tavan
        return AG.tail_active(df, n)
    m2 = min(cap, int(math.ceil(n * len(df) / max(got, 1) * _RETRY_MARGIN)) + 32)
    if m2 > m:
        df, ex = fetch(m2)
        keep = AG.active_mask(df)
        if keep is not None and int(keep.sum()) < n and not ex and m2 < cap:
            df, _ = fetch(cap)                  # eski gecmis daha olu: tavana kadar oku (sonuc okuma gecmisine/ipucuna BAGLI OLMASIN)
    return AG.tail_active(df, n)


def _bars_window(view: MarketView, pair: str, tf: str, D: datetime, n: int) -> pd.DataFrame:
    """`view.bars(n)` ile ayni, ama pencere n DOLU bar sayar: olu mum (hacim 0, o=h=l=c) olan seansli enstrumanda pencereyi genisletip
    son n dolu bari (+ aralarindaki olu mumlari) dondurur. Olu mum yoksa tam olarak `view.bars(pair, tf, D, n)` (kripto: degismez). Boylece
    EMA/ATR tohum etkisi 7/24 enstrumanla ayni mertebede kalir ve canli pencere kesiti tum gecmis (geri test) hesabiyla ayni degeri verir."""
    def fetch(m: int):
        df = view.bars(pair, tf, D, m)
        return df, len(df) < m
    return _live_window(fetch, n, (pair, tf))


def _bars_1d(view: MarketView, pair: str, D: datetime, n: int) -> pd.DataFrame:
    """Son `n` DOLU 1g bar: 4s barlardan (UTC gunu = 6 x 4s) toplanir; 1g penceresi 4s penceresinden (WINDOW_ARM['4h']) BAGIMSIZ ve daha
    uzundur (EMA(50) tohum etkisi <= 1e-9 icin ~600 gun): 4s okumasi yalniz bu yolda buyur. Depoda daha az gecmis varsa var olan kullanilir."""
    def fetch(m: int):
        k = BARS_PER_DAY_4H * m + BARS_PER_DAY_4H - 1                  # +5: bas kismi gun atilsa da m tam gun
        h4 = view.bars(pair, "4h", D, k)
        return aggregate_4h_to_1d(h4), len(h4) < k
    return _live_window(fetch, n, (pair, "1d"), _WIDEN_MAX_1D)


def _opt(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _int0(x) -> int:
    v = _opt(x)
    return int(v) if v is not None else 0


def _text(x, default: str | None = None) -> str | None:
    return x if isinstance(x, str) else default


def _vol(setup, side, trig, atr, tf) -> dict:
    """Yalniz aday satirlar icin (ucuz): karar mumuna kadar KAPANMIS mumlardan oynaklik ozellikleri; hata/eksik => bos."""
    if not (setup and side) or trig is None or "close" not in trig.columns:
        return {}
    try:
        keep = AG.active_mask(trig)                       # olu (hacim 0, o=h=l=c) mumlar sifir getiri uretip varyansi kucultmesin
        c = trig["close"].to_numpy(dtype=float)
        return vol_ozellikleri(c if keep is None else c[keep], atr, tf)
    except Exception:  # noqa: BLE001 - ek ozellik asla motoru durdurmaz
        return {}


def _to_row(pair: str, open_ts: datetime, close_ts: datetime, r: pd.Series, version_id: int, trig=None, tf=None) -> SignalRow:
    pe, ps = _opt(r["planned_entry"]), _opt(r["planned_stop"])
    vf = _vol(_text(r["setup"]), _text(r["side"]), trig, _opt(r["atr_tf"]), tf)
    return SignalRow(
        pair=pair, bar_open_ts=open_ts, bar_close_ts=close_ts, signal=bool(r["signal"]),
        setup=_text(r["setup"]), side=_text(r["side"]), skip_reason=_text(r["skip_reason"]),
        planned_entry=pe if pe is not None else float("nan"), planned_stop=ps if ps is not None else float("nan"),
        planned_target=_opt(r["planned_target"]), rr=_opt(r["rr"]), stop_dist_atr=_opt(r["stop_dist_atr"]),
        atr_tf=_opt(r["atr_tf"]), atr_4h=_opt(r["atr_4h"]), atr_ratio=_opt(r["atr_ratio"]),
        regime=_text(r["regime"], "unclear"), rh=_opt(r["rh"]), rl=_opt(r["rl"]),
        rh_touches=_int0(r["rh_touches"]), rl_touches=_int0(r["rl_touches"]), ema_value=_opt(r["ema_value"]),
        body_ratio=_opt(r["body_ratio"]), wick_ratio=_opt(r["wick_ratio"]), edge_dist_atr=_opt(r["edge_dist_atr"]),
        pullback_ema=_int0(r["pullback_ema"]), reasons=_text(r["reasons"], "") or "", param_version_id=int(version_id),
        vol_tahmin=vf.get("vol_tahmin"), vol_asim=vf.get("vol_asim"))


def _params_map(params) -> Mapping[str, object]:
    if isinstance(params, SignalParams):
        return {k: getattr(params, k) for k in L.PARAM_KEYS}
    return params


class WindowedSignalSource:
    """Paper/canli: her karar adiminda pencere cek, stratejiyi calistir."""

    def __init__(self, view: MarketView, strategy: Strategy, *, strict: bool = False,
                 last_exit_fn: Callable[[str, datetime], tuple[datetime, str] | None] | None = None,
                 pairs: Sequence[str] | None = None) -> None:
        self.view = view
        self.strategy = strategy
        self.strict = strict
        self.last_exit_fn = last_exit_fn
        self.counters: Counter = Counter()
        self._cache: dict[tuple[str, datetime, int], SignalFrame] = {}
        self._latest: dict[tuple[str, datetime], SignalFrame] = {}
        self._cache_d: datetime | None = None
        self.pairs = list(pairs) if pairs is not None else []        # taranacak ciftler (biliniyorsa 1g tur ozeti tur biter bitmez yazilir)

    def _new_step(self, D: datetime) -> None:
        return None

    # ------------------------------------------------------------------ frame
    def frame(self, pair: str, D: datetime, params, version_id: int) -> SignalFrame:
        if self._cache_d != D:
            self._cache.clear()
            self._latest.clear()
            self._cache_d = D
            self._new_step(D)
        key = (pair, D, int(version_id))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        fr = self._build(pair, D, _params_map(params), int(version_id))
        self._cache[key] = fr
        self._latest[(pair, D)] = fr
        return fr

    def _bad(self, pair: str, status: str, detail: str, *, error: bool = False) -> SignalFrame:
        self.counters["errors" if error else status] += 1
        log.log(logging.CRITICAL if error else logging.WARNING, "sinyal karesi %s: %s (%s)", pair, status, detail)
        return SignalFrame(pair=pair, status=status, detail=detail, last=None, table=None)  # type: ignore[arg-type]

    def _gather(self, pair: str, D: datetime, params: Mapping[str, object]):
        """Yan etkisiz pencere toplama -> (bars, trig, None) ya da (None, None, (durum, ayrinti))."""
        info = self.strategy.info
        tf = str(params["trigger_tf"])
        if tf not in info.allowed_trigger_tfs:
            raise StrategyError("bad_table", f"trigger_tf izinli degil: {tf}")
        names = {("trigger" if t == "trigger" else t): (tf if t == "trigger" else t) for t in info.timeframes}
        bars: dict[str, pd.DataFrame] = {}
        for key, real in names.items():
            bars[real] = _bars_window(self.view, pair, real, D, info.window_bars[real])
        trig = bars[tf]
        for key, real in names.items():
            if len(bars[real]) < info.warmup_bars[real]:
                return None, None, ("no_history", f"{real}:{len(bars[real])}<{info.warmup_bars[real]}")
        if len(trig) == 0 or trig.index[-1].to_pydatetime() != D - tf_delta(tf):
            return None, None, ("data_gap", "trigger_bar_missing")
        for key, real in names.items():
            need = info.min_contiguous.get(key)
            if need is not None and self.view.contiguous_tail(pair, real, D) < need:
                return None, None, ("data_gap", "hole")
        return bars, trig, None

    def _build(self, pair: str, D: datetime, params: Mapping[str, object], version_id: int) -> SignalFrame:
        info = self.strategy.info
        try:
            tf = str(params["trigger_tf"])
            if tf not in info.allowed_trigger_tfs:
                raise StrategyError("bad_table", f"trigger_tf izinli degil: {tf}")
            bars, trig, bad = self._gather(pair, D, params)
            if bad is not None:
                return self._bad(pair, bad[0], bad[1])
            ctx = StrategyContext(pair=pair, D=D, tf=tf, params=params, bars=bars, last_exit=None)
            sig = self.strategy.compute(ctx)
            validate_table(sig, info, trig.index)
            last_exit = self.last_exit_fn(pair, D) if self.last_exit_fn is not None else None
            fctx = StrategyContext(pair=pair, D=D, tf=tf, params=params, bars=bars, last_exit=last_exit)
            last_row = self.strategy.post_filter(sig.iloc[-1], fctx)
            validate_row(last_row, info)
            if bool(last_row["signal"]) and not bool(sig.iloc[-1]["signal"]):
                raise StrategyError("bad_table", "post_filter aday ekleyemez")
            if bool(last_row["signal"]):
                for k in ("planned_entry", "planned_stop", "planned_target", "setup", "side"):
                    a, b = last_row[k], sig.iloc[-1][k]
                    same = (a == b) or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))
                    if not same:
                        raise StrategyError("bad_table", f"post_filter {k} degistiremez")
            table = sig.join(trig[_OHLC])
            for c in ("signal", "skip_reason", "reasons"):
                table.iloc[-1, table.columns.get_loc(c)] = last_row[c]
            open_ts = trig.index[-1].to_pydatetime()
            row = _to_row(pair, open_ts, D, table.iloc[-1], version_id, trig, tf)
            tb = None
            if "volume" in trig.columns:
                lt = trig.iloc[-1]
                tb = (float(lt["high"]), float(lt["low"]), float(lt["volume"]))
            return SignalFrame(pair=pair, status="ok", detail=None, last=row, table=table, trigger_bar=tb)
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self.counters["callback_errors"] += 1
            return self._bad(pair, "error", f"{type(e).__name__}: {e}", error=True)

    # ------------------------------------------------------------------ exit_context
    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None:
        fr = self._latest.get((pair, D))
        if fr is None or fr.status != "ok" or fr.table is None or pos.entry_bar_open is None:
            return None
        t = fr.table
        sl = t[t.index >= pd.Timestamp(pos.entry_bar_open)]
        return ExitContext(bar_close_ts=D, highs=sl["high"].to_numpy(dtype=float), lows=sl["low"].to_numpy(dtype=float),
                           atrs=sl["atr_tf"].to_numpy(dtype=float), regime_last=_text(t["regime"].iloc[-1]),
                           last_close=float(t["close"].iloc[-1]), n_closed=len(sl))


# ====================================================================== DD-12 WP-11: cok kurulumlu kaynak
class MultiArmSignalSource(WindowedSignalSource):
    """Bilesik strateji (`price_action_lab_ml`) kaynagi: 15 dakikalik karar adiminda YALNIZ kapanan zaman dilimlerinin kurulumlarini
    hesaplar (D-T16). Cift basina tek `SignalFrame`: `last` = oncelikli aday (buyuk zaman dilimi; sinyal > elenmis > diger),
    `extras` = diger kurulum adaylari (sinyal ise motor `arm_conflict` yazar). `table` YOKTUR (bellek): acik pozisyonun cikis
    baglami (kendi zaman dilimi kapandiginda) kucuk bir gorunum olarak tutulur. Bellek: adimlar arasi yalniz cift basina
    rejim tablosu (lab._reg_cache); tablolar adim sonunda atilir."""

    def __init__(self, *a, position_fn=None, quarantine=None, **k) -> None:
        super().__init__(*a, **k)
        self.quarantine = quarantine                    # arm_quarantine.ArmQuarantine | None (kurulum kod hatasi karantinasi)
        self.position_fn = position_fn                  # cift -> (trigger_tf, entry_bar_open | None) | None (motor tedarik eder)
        self._exit_views: dict[tuple[str, datetime], tuple[str, ExitContext]] = {}
        self._d1: tuple[datetime, int, int] | None = None      # (D, taranan cift, aday) - 1g tarama turu ozeti (yalniz gunluk log)

    def _d1_note(self, D: datetime, candidate: bool | None) -> None:
        """1g kurulum turu sayaci: candidate=None -> bir cift tarandi; True -> o ciftte aday (setup+yon) uretildi. Tur, tum
        ciftler tarandiginda (pairs biliniyorsa) ya da sonraki karar adiminda tek INFO satiri olarak yazilir. Davranis degismez."""
        d, n, m = self._d1 if self._d1 is not None and self._d1[0] == D else (D, 0, 0)
        self._d1 = (d, n + (candidate is None), m + (candidate is True))

    def _d1_flush(self) -> None:
        if self._d1 is None:
            return
        d, n, m = self._d1
        self._d1 = None
        log.info("1d tarama: %d cift, %d aday (%s)", n, m, d.isoformat())

    def _new_step(self, D: datetime) -> None:
        self._exit_views.clear()
        if self._d1 is not None and self._d1[0] != D:
            self._d1_flush()

    # ------------------------------------------------------------------ veri
    def _arm_gather(self, pair: str, D: datetime, tf: str, h4: pd.DataFrame):
        """tf icin (trig, None) ya da (None, (durum, ayrinti)). 1s `_gather` ile ayni denetimler (ısınma, tetik bari, bosluk)."""
        if tf == "4h":
            trig = h4
        elif tf == "1d":
            trig = _bars_1d(self.view, pair, D, WINDOW_ARM["1d"])
        else:
            trig = _bars_window(self.view, pair, tf, D, WINDOW_ARM[tf])
        if len(trig) < STARTUP_BARS_ARM[tf]:
            return None, ("no_history", f"{tf}:{len(trig)}<{STARTUP_BARS_ARM[tf]}")
        if trig.index[-1].to_pydatetime() != D - arm_tf_delta(tf):
            return None, ("data_gap", f"trigger_bar_missing:{tf}")
        if not self._tail_ok(trig.index, tf, MIN_CONTIG_ARM["trigger"]):
            return None, ("data_gap", f"hole:{tf}")
        return trig, None

    @staticmethod
    def _tail_ok(index: pd.DatetimeIndex, tf: str, need: int) -> bool:
        if len(index) < need:
            return False
        idx = index[-need:]
        return bool((idx[1:] - idx[:-1] == pd.Timedelta(arm_tf_delta(tf))).all())

    def _h4_checked(self, pair: str, D: datetime, h4: pd.DataFrame):
        if len(h4) < STARTUP_BARS_ARM["4h"]:
            return ("no_history", f"4h:{len(h4)}<{STARTUP_BARS_ARM['4h']}")
        if not self._tail_ok(h4.index, "4h", MIN_CONTIG_ARM["4h"]):
            return ("data_gap", "hole:4h")
        return None

    # ------------------------------------------------------------------ frame
    def _build(self, pair: str, D: datetime, params: Mapping[str, object], version_id: int) -> SignalFrame:
        try:
            return self._build_multi(pair, D, params, version_id)
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self.counters["callback_errors"] += 1
            return self._bad(pair, "error", f"{type(e).__name__}: {e}", error=True)
        finally:                                        # 1g turu tamamlandi (tum ciftler tarandi): tek ozet satiri
            if self._d1 is not None and self._d1[0] == D and self.pairs and self._d1[1] >= len(self.pairs):
                self._d1_flush()

    def _build_multi(self, pair: str, D: datetime, params: Mapping[str, object], version_id: int) -> SignalFrame:
        lab = self.strategy
        closing = arm_closing_tfs(D)
        pos = self.position_fn(pair) if self.position_fn is not None else None
        pos_tf = pos[0] if (pos is not None and pos[0] in closing) else None
        tfs = [tf for tf in ARM_TFS if tf in closing and (lab.arms_at(tf) or tf == pos_tf)]
        if not tfs:
            return SignalFrame(pair=pair, status="ok", detail="no_arm_closed", last=None, table=None)
        # 4s (rejim kaynagi + 4s/1g tetigi): 1s penceresi toplandiysa 4s oradan alinir
        h4 = None
        g = None
        if "1h" in tfs:
            g = self._gather(pair, D, params)
            if g[2] is None:
                h4 = g[0]["4h"]
        if h4 is None:
            h4 = _bars_window(self.view, pair, "4h", D, WINDOW_ARM["4h"])
        h4_bad = self._h4_checked(pair, D, h4)
        if "1d" in tfs:
            self._d1_note(D, None)
        cands: list[tuple[int, str, SignalRow, tuple | None]] = []
        bad: dict[str, tuple[str, str]] = {}
        exit_view = None
        rule_in: tuple | None = None                    # 24.11: kural cikisi icin (trig, ctx) - pozisyonun zaman dilimi
        for tf in tfs:
            if h4_bad is not None:
                bad[tf] = h4_bad
                continue
            if tf == "1h":
                if g[2] is not None:
                    bad[tf] = g[2]
                    continue
                trig = g[1]
            else:
                trig, why = self._arm_gather(pair, D, tf, h4)
                if why is not None:
                    bad[tf] = why
                    continue
            bars = {tf: trig, "4h": h4}
            le = self.last_exit_fn(pair, D, tf) if self.last_exit_fn is not None else None
            ctx = StrategyContext(pair=pair, D=D, tf=tf, params=params, bars=bars, last_exit=None)
            if tf == pos_tf:
                rule_in = (trig, ctx)
            fctx = StrategyContext(pair=pair, D=D, tf=tf, params=params, bars=bars, last_exit=le)
            info = lab.info
            q = self.quarantine
            hooks = {}
            if q is not None:
                units = {k: unit_for(lab, tf, k) for k in ["core"] + [m.SETUP for m in lab.arms_at(tf)]}
                hooks = {"skip": {k for k, (u, _a) in units.items() if q.blocked(u)},
                         "on_error": lambda k, e, units=units: q.error(units[k][0], units[k][1], e),
                         "on_ok": lambda k, units=units: q.ok(units[k][0])}
            for key, sig in lab.compute_tf(ctx, force_core=(tf == pos_tf), **hooks).items():
                validate_table(sig, info, trig.index)
                if q is not None and q.blocked(units[key][0]):
                    # karantinada: yeni aday YOK; acik pozisyonun cikis baglami yine kurulur (stop/hedef yonetimi surer)
                    if tf == pos_tf and (key == "core" or exit_view is None):
                        exit_view = self._exit_view(sig, trig, sig.iloc[-1], pos, D)
                    continue
                if q is not None:
                    try:
                        last_row = lab.filter_row(key, sig.iloc[-1], fctx)
                    except Exception as e:  # noqa: BLE001
                        if not is_strategy_error(e):
                            raise
                        q.error(units[key][0], units[key][1], e)
                        continue
                else:
                    last_row = lab.filter_row(key, sig.iloc[-1], fctx)
                validate_row(last_row, info)
                if bool(last_row["signal"]) and not bool(sig.iloc[-1]["signal"]):
                    raise StrategyError("bad_table", "post_filter aday ekleyemez")
                if bool(last_row["signal"]):
                    for k in ("planned_entry", "planned_stop", "planned_target", "setup", "side"):
                        a, b = last_row[k], sig.iloc[-1][k]
                        same = (a == b) or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))
                        if not same:
                            raise StrategyError("bad_table", f"post_filter {k} degistiremez")
                lr = sig.iloc[-1].copy()
                for c in ("signal", "skip_reason", "reasons"):
                    lr[c] = last_row[c]
                open_ts = trig.index[-1].to_pydatetime()
                row = _to_row(pair, open_ts, D, lr, version_id, trig, tf)
                if row.setup:
                    row = dataclasses.replace(row, arm_id=f"{row.setup}@{tf}", tf=tf)
                else:
                    row = dataclasses.replace(row, tf=tf)
                lt = trig.iloc[-1]
                tb = (float(lt["high"]), float(lt["low"]), float(lt["volume"])) if "volume" in trig.columns else None
                is_filtered = bool(row.setup and row.side and row.skip_reason in _FILTERED_SKIPS)
                cls = 0 if row.signal else (1 if is_filtered else 2)
                cands.append((cls * 10 - ARM_TFS.index(tf), key, row, tb))
                if tf == "1d" and row.setup and row.side:
                    self._d1_note(D, True)
                if tf == pos_tf and (key == "core" or exit_view is None):
                    exit_view = self._exit_view(sig, trig, lr, pos, D)
        if exit_view is not None and rule_in is not None and len(pos) > 2:
            exit_view = self._rule_exit(exit_view, lab, pos[2], rule_in, h4, params, D, pos[3] if len(pos) > 3 else None)
        if exit_view is not None:
            self._exit_views[(pair, D)] = (pos_tf, exit_view)
        if not cands:
            st, det = next(iter(bad.values()))
            return self._bad(pair, st, det)
        for tf, (st, det) in bad.items():                         # kismi bosluk: kalan zaman dilimleri yine calisir
            self.counters[f"arm_tf_{st}:{tf}"] += 1
        cands.sort(key=lambda c: (c[0], priority_of(c[2].setup), c[1]))     # tf (buyuk once), sonra kurulum onceligi (K-7 md. 3)
        frames = [SignalFrame(pair=pair, status="ok", detail=None, last=row, table=None, trigger_bar=tb)
                  for _, _, row, tb in cands]
        head = frames[0]
        extras = tuple(f for f in frames[1:] if f.last.signal or (f.last.setup and f.last.side and f.last.skip_reason in _FILTERED_SKIPS))
        return dataclasses.replace(head, extras=extras)

    def _rule_exit(self, view: ExitContext, lab, setup, rule_in: tuple, h4, params, D: datetime,
                   side: str | None = None) -> ExitContext:
        """24.11 kullanici karari: kutuphane kural cikisi (EXIT_RULE): yalniz son kapanmis mum okunur. Hata olursa
        `rule_exit` False kalir (stop ve zaman stopu yine calisir) ve sayac artar."""
        rule = exit_rule_of(setup)
        if rule is None:
            return view
        trig, ctx = rule_in
        try:
            keep = AG.active_mask(trig)
            trig_a = trig if keep is None else trig[keep]
            inp = ArmInput(pair=ctx.pair, tf=ctx.tf, D=D, trig=trig_a, h4=h4, params=SignalParams.from_mapping(params),
                           core_fn=lambda c=ctx: lab._core_compact(c), side=side)
            if bool(rule(inp)):
                return dataclasses.replace(view, rule_exit=True)
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self.counters["exit_rule_error"] += 1
            log.warning("kural cikisi hesaplanamadi (%s): %s: %s", setup, type(e).__name__, e)
        return view

    @staticmethod
    def _exit_view(sig: pd.DataFrame, trig: pd.DataFrame, lr: pd.Series, pos, D: datetime) -> ExitContext:
        t = sig.join(trig[_OHLC])
        eb = pos[1]
        sl = t[t.index >= pd.Timestamp(eb)] if eb is not None else t.iloc[0:0]
        return ExitContext(bar_close_ts=D, highs=sl["high"].to_numpy(dtype=float), lows=sl["low"].to_numpy(dtype=float),
                           atrs=sl["atr_tf"].to_numpy(dtype=float), regime_last=_text(t["regime"].iloc[-1]),
                           last_close=float(t["close"].iloc[-1]), n_closed=len(sl))

    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None:
        v = self._exit_views.get((pair, D))
        if v is None or v[0] != pos.trigger_tf or pos.entry_bar_open is None:
            return None
        return v[1]
