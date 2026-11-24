"""Funding hesaplari (03 §5). Saf fonksiyonlar; isaret: POZITIF = odenen (ledger isareti)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Sequence

from .types import FundingPoint, Side, require_utc

_FUNDING_HOURS = (0, 8, 16)


def funding_payment(side: Side, qty: float, mark: float, rate: float) -> float:
    if side not in ("long", "short"):
        raise ValueError(f"gecersiz side: {side!r}")
    for name, v in (("qty", qty), ("mark", mark), ("rate", rate)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"{name} sonlu sayi olmali: {v!r}")
    if qty <= 0:
        raise ValueError(f"qty > 0 olmali: {qty!r}")
    if mark <= 0:
        raise ValueError(f"mark > 0 olmali: {mark!r}")
    p = qty * mark * rate
    return p if side == "long" else -p


def floor_funding_time(t: datetime) -> datetime:
    """Ham fundingTime'i 8 saatlik izgaraya (00/08/16 UTC) tabana yuvarlar (saat basini birkac ms gecen zaman damgasi)."""
    require_utc(t, "t")
    return t.replace(hour=t.hour - t.hour % 8, minute=0, second=0, microsecond=0)


def floor_funding_hour(t: datetime) -> datetime:
    """Ham fundingTime'i saat basina tabana yuvarlar. Aralik-bagimsiz: 1h/4h/8h funding kayitlarinin KENDI zamani kullanilir
    (sabit 00/08/16 izgarasi yok); saat basini birkac ms gecen zaman damgasi saate iner."""
    require_utc(t, "t")
    return t.replace(minute=0, second=0, microsecond=0)


def due_funding_times(last_ts: datetime | None, upto: datetime) -> list[datetime]:
    require_utc(upto, "upto")
    if last_ts is None:
        start = upto - timedelta(hours=8)
    else:
        require_utc(last_ts, "last_ts")
        start = last_ts
    if start >= upto:
        return []
    t = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    out: list[datetime] = []
    while t <= upto:
        if t.hour in _FUNDING_HOURS:
            out.append(t)
        t += timedelta(hours=1)
    return out


def accrue(position_opened_ts: datetime, points: Sequence[FundingPoint], side: Side, qty: float,
           mark_fallback: float) -> tuple[float, int]:
    total = 0.0
    used = 0
    for p in points:
        if position_opened_ts >= p.ts:
            continue
        mark = p.mark if p.mark is not None else mark_fallback
        total += funding_payment(side, qty, mark, p.rate)
        used += 1
    return total, used
