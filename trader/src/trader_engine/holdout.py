"""Kilitli donem (HOLDOUT) yapisal kilidi: backtest.py ve Engine.run_range ayni kontrolu kullanir.

23.11.2026 KULLANICI KARARI: kilit ACILDI (`KILIT_ACIK = True`). Tek davranis anahtari budur; kilit kapali (False) iken eski
kilit davranisi aynen geri gelir. `HOLDOUT` tarih sabiti kayit/rapor amaciyla kalir; davranis yalniz `KILIT_ACIK`a baglidir.
Kopyalar (trader_core, trader_ml) ayni bayragi kendi modullerinde tasir; esitlik testle denetlenir.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .errors import EngineError

# 23.11.2026 kullanici karari ("ac"): 2026-05-01 -> 2026-11-01 donemi egitim/arastirma/rapor/motor tarafinda okunabilir.
# Bagimsiz sinav hakki bilerek terk edildi (research/holdout/muhur.json acildi=true). True iken hicbir kilit/atlama calismaz.
KILIT_ACIK = True

HOLDOUT = (datetime(2026, 5, 1, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc))


class BacktestArgError(EngineError):
    def __init__(self, code: str, msg: str = "") -> None:
        super().__init__(msg or code)
        self.code = code


def in_holdout(ts: datetime) -> bool:
    """ts kilitli donemde mi? Kilit aciksa her zaman False."""
    return (not KILIT_ACIK) and HOLDOUT[0] <= ts < HOLDOUT[1]


def check_holdout(start: datetime, end: datetime) -> None:
    if KILIT_ACIK:
        return
    if start < HOLDOUT[1] and end > HOLDOUT[0]:
        raise BacktestArgError("holdout_locked", f"HOLDOUT [{HOLDOUT[0]:%Y%m%d}, {HOLDOUT[1]:%Y%m%d}) ile kesisen donem")
