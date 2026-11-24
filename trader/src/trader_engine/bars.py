"""Bar aritmetigi (02 §7). Yalniz standart kutuphane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator, Sequence

from trader_core.arm_time import ARM_TFS, ARM_TF_SECONDS, arm_tf_delta

from .errors import DataError
from .types import Bar, Kind, MinuteBar, require_utc

TF_SECONDS = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}
TRIGGER_TFS = ("1h", "15m")
WINDOW_TRIGGER = {"1h": 1500, "15m": 5000}
WINDOW_4H = 1500
STARTUP_BARS = {"1h": 1200, "15m": 4800}
STARTUP_BARS_4H = 300

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_FUNDING_HOURS = (0, 8, 16)


def tf_delta(tf: str) -> timedelta:
    try:
        return timedelta(seconds=TF_SECONDS[tf])
    except (KeyError, TypeError):
        raise ValueError(f"bilinmeyen tf: {tf!r}") from None


def floor_tf(ts: datetime, tf: str) -> datetime:
    require_utc(ts)
    d = tf_delta(tf)
    return ts - ((ts - _EPOCH) % d)


def is_tf_close(ts: datetime, tf: str) -> bool:
    return ts == floor_tf(ts, tf)


def closing_tfs(ts: datetime, tfs: Sequence[str] = ("15m", "1h", "4h")) -> list[str]:
    return [tf for tf in tfs if is_tf_close(ts, tf)]


def last_closed_open(now: datetime, tf: str) -> datetime:
    return floor_tf(now, tf) - tf_delta(tf)


def bar_close_ts(open_ts: datetime, tf: str) -> datetime:
    require_utc(open_ts, "open_ts")
    return open_ts + tf_delta(tf)


def expected_opens(start: datetime, end: datetime, tf: str) -> Iterator[datetime]:
    require_utc(start, "start")
    require_utc(end, "end")
    d = tf_delta(tf)
    t = floor_tf(start, tf)
    if t < start:
        t += d
    while t < end:
        yield t
        t += d


def to_ms(ts: datetime) -> int:
    require_utc(ts)
    return (ts - _EPOCH) // timedelta(milliseconds=1)


def from_ms(ms: int) -> datetime:
    if isinstance(ms, bool) or not isinstance(ms, int):
        raise ValueError(f"ms int olmali: {ms!r}")
    return _EPOCH + timedelta(milliseconds=ms)


def aggregate_minutes(minutes: Sequence[MinuteBar], tf: str, kind: Kind = "last") -> Bar:
    if kind not in ("last", "mark"):
        raise ValueError(f"gecersiz kind: {kind!r}")
    d = tf_delta(tf)
    n = int(d.total_seconds() // 60)
    if len(minutes) != n:
        raise DataError(f"{tf} icin {n} dakika gerekir, {len(minutes)} geldi")
    first = minutes[0]
    require_utc(first.open_ts, "open_ts")
    if floor_tf(first.open_ts, tf) != first.open_ts:
        raise DataError(f"ilk dakika {tf}'ye hizali degil: {first.open_ts}")
    step = timedelta(seconds=60)
    for i, m in enumerate(minutes):
        if m.pair != first.pair or m.step_s != 60 or m.open_ts != first.open_ts + i * step:
            raise DataError(f"dakika serisi ardisik/sirali/tek cift degil (indeks {i})")
    p = kind + "_"
    try:
        os_ = [getattr(m, p + "o") for m in minutes]
        hs = [getattr(m, p + "h") for m in minutes]
        ls = [getattr(m, p + "l") for m in minutes]
        cs = [getattr(m, p + "c") for m in minutes]
    except AttributeError:  # pragma: no cover
        raise DataError("bozuk dakika") from None
    if any(x is None for x in os_ + hs + ls + cs):
        raise DataError(f"{kind} fiyati eksik dakika var")
    return Bar(pair=first.pair, kind=kind, tf=tf, open_ts=first.open_ts,
               o=os_[0], h=max(hs), l=min(ls), c=cs[-1], v=sum(m.volume for m in minutes))


def funding_times(start: datetime, end: datetime) -> list[datetime]:
    start = require_utc(start, "start").astimezone(timezone.utc)
    end = require_utc(end, "end").astimezone(timezone.utc)
    out: list[datetime] = []
    day = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    while day <= end:
        for h in _FUNDING_HOURS:
            t = day + timedelta(hours=h)
            if start < t <= end:
                out.append(t)
        day += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# DD-12 WP-11: cok zaman dilimli kurulumlar (arms). Yukaridaki sabitler/islevler (TF_SECONDS, tf_delta, floor_tf ...)
# DEGISMEZ (eski sozlesme: `tf_delta("1d")` hata verir); kurulum yolu `arm_*` ailesini kullanir.
# 1 gunluk bar feed'e/market.sqlite'a EKLENMEZ: UTC gununun 6 x 4s barindan motor icinde toplanir (D-T16).
# ---------------------------------------------------------------------------------------------------------------------
# cift x zaman dilimi basina son pencere (bellek siniri). 1d: 4s'ten toplanir ve 4s penceresinden BAGIMSIZ okunur (strategy_runner._bars_1d):
# 600 gun => EMA(50) tohum farki (1-2/51)^600 ~ 4e-11 (canli pencere == tum gecmis, 1e-9). ~3600 x 4s satir/cift (~150 KB), gunde bir okunur.
WINDOW_ARM = {"15m": 5000, "1h": 1500, "4h": 1500, "1d": 600}
STARTUP_BARS_ARM = {"15m": 4800, "1h": 1200, "4h": 300, "1d": 50}  # 1d: 300 x 4s / 6
MIN_CONTIG_ARM = {"trigger": 20, "4h": 150}
BARS_PER_DAY_4H = 6


def arm_floor_tf(ts: datetime, tf: str) -> datetime:
    require_utc(ts)
    d = arm_tf_delta(tf)
    return ts - ((ts - _EPOCH) % d)


def arm_is_tf_close(ts: datetime, tf: str) -> bool:
    return ts == arm_floor_tf(ts, tf)


def arm_closing_tfs(ts: datetime, tfs: Sequence[str] = ARM_TFS) -> list[str]:
    return [tf for tf in tfs if arm_is_tf_close(ts, tf)]


def aggregate_4h_to_1d(df4h):
    """4s OHLCV (UTC tz-bilincli DatetimeIndex, acilis zamani) -> 1g OHLCV. Yalniz TAM 6 x 4s barli UTC gunu bar uretir
    (eksik 4s barla 1g bar uretilmez, sessiz doldurma yok). Sutunlar: open high low close volume."""
    import pandas as pd
    cols = ["open", "high", "low", "close", "volume"]
    if len(df4h) == 0:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in cols},
                            index=pd.DatetimeIndex([], tz="UTC", name=getattr(df4h.index, "name", None)))
    day = df4h.index.floor("1D")
    g = df4h.groupby(day, sort=True)
    n = g["open"].count()
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
                volume=("volume", "sum"))
    out = out.loc[n[n == BARS_PER_DAY_4H].index][cols]
    out.index.name = df4h.index.name
    return out


def contiguous_tail_len(index, tf: str) -> int:
    """Indeksin sonundaki kesintisiz (tf adimli) bar sayisi."""
    k = len(index)
    if k == 0:
        return 0
    step = arm_tf_delta(tf)
    n = 1
    for i in range(k - 1, 0, -1):
        if index[i] - index[i - 1] != step:
            break
        n += 1
    return n
