"""ML1 etiketli satir hizi (gercek+sanal) ve hedefe tahmini varis; saf hesap."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any


def hiz_hesapla(zamanlar: Sequence[Any], n: int, hedef: int, now: datetime, gun: int = 7) -> tuple[float | None, str | None]:
    """Etiketli (gercek+sanal) satir zamanlarindan (datetime/ISO) son `gun` gunluk ortalama hiz ve hedefe tahmini varis tarihi (ISO gun).
    Veri 1 gunden kisa ya da hiz 0 ise (None, None); n >= hedef ise hiz var, varis = bugun."""
    import pandas as pd
    ts = []
    for z in zamanlar:
        try:
            t = pd.Timestamp(z)
            ts.append(t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC"))
        except (ValueError, TypeError):
            continue
    if not ts:
        return None, None
    nowt = pd.Timestamp(now)
    nowt = nowt.tz_localize("UTC") if nowt.tzinfo is None else nowt.tz_convert("UTC")
    span = (nowt - min(ts)).total_seconds() / 86400.0
    if span < 1.0:
        return None, None
    c = sum(1 for t in ts if t >= nowt - pd.Timedelta(days=gun))
    hiz = c / min(float(gun), span)
    if hiz <= 0:
        return None, None
    kalan = max(0, int(hedef) - int(n))
    return round(hiz, 2), (nowt + pd.Timedelta(days=kalan / hiz)).strftime("%Y-%m-%d")
