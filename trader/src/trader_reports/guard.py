"""Kilitli donem korumasi (tek gecit). Sabitler trader_engine.holdout'tan alinir.

23.11.2026 kullanici karari: `KILIT_ACIK` iken kilit penceresi BOS (1970-01-01 noktasi): hicbir islem/karar/mum kilitli sayilmaz,
SQL parcalari hicbir satiri eslemez. Kilit kapaliyken (KILIT_ACIK=False) eski HOLDOUT penceresi gecerlidir."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from trader_engine.holdout import HOLDOUT, KILIT_ACIK, BacktestArgError, check_holdout

PAD_HOURS = 72
H0, H1 = (datetime(1970, 1, 1, tzinfo=timezone.utc),) * 2 if KILIT_ACIK else HOLDOUT   # acik kilit: bos pencere
H0_MS = int(H0.timestamp() * 1000)
H1_MS = int(H1.timestamp() * 1000)
HOUR_MS = 3_600_000


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


H1_ISO = iso(H1)
H0_PAD_ISO = iso(H0 - timedelta(hours=PAD_HOURS))

# SQL parcalari (adli parametreler :h1 ve :h0p ile baglanir)
PARAMS = {"h1": H1_ISO, "h0p": H0_PAD_ISO}
TRADE_LOCK_SQL = "(t.entry_ts < :h1 AND t.exit_ts >= :h0p)"
TS_LOCK_SQL = "({col} < :h1 AND {col} >= :h0p)"


def ts_lock_sql(col: str) -> str:
    return TS_LOCK_SQL.format(col=col)


def trade_locked(entry_ts: str, exit_ts: str) -> bool:
    return entry_ts < H1_ISO and exit_ts >= H0_PAD_ISO


def ts_locked(ts: str) -> bool:
    return ts < H1_ISO and ts >= H0_PAD_ISO


def check_run(start: datetime, end: datetime) -> None:
    """Kosu duzeyi: kesisirse BacktestArgError('holdout_locked')."""
    check_holdout(start, end)


def check_window(start_ms: int, n: int, tf_ms: int) -> None:
    """Mum duzeyi: her pencere okumasindan ONCE cagrilir; kesisirse BacktestArgError."""
    s = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    e = datetime.fromtimestamp((start_ms + n * tf_ms) / 1000, tz=timezone.utc)
    check_holdout(s, e)


__all__ = ["BacktestArgError", "HOLDOUT", "KILIT_ACIK", "check_holdout", "check_run", "check_window", "iso", "PARAMS",
           "trade_locked", "ts_locked", "ts_lock_sql", "H0_PAD_ISO", "H1_ISO", "H0_MS", "H1_MS"]
