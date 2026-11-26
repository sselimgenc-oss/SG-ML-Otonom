"""ML1: tarihsel mum yukleme (kagit motorunun HistoricalSource'u; `<PAIR>_USDT_USDT-<tf>-futures.feather`).

1d tarihte ayri dosyadan degil, 4s'ten toplanir (`aggregate_4h_to_1d`: yalniz TAM 6 x 4s barli UTC gunu; motorla ayni).
Doner: (trig, h4); trig tf mumlari (acilis zamani indeksli, UTC), h4 4s rejim kaynagi. Dosya yoksa None."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from trader_engine.bars import aggregate_4h_to_1d
from trader_engine.errors import DataError
from trader_engine.marketdata.sources import HistoricalSource

SONSUZ = datetime(2200, 1, 1, tzinfo=timezone.utc)
TFS = ("15m", "1h", "4h", "1d")             # veri/tarama: 15m KALIR (karar ve cikis yonetimi kadansi)
MODEL_TFS = ("1h", "4h", "1d")             # model ozelligi (tf_* one-hot) ve giris zaman dilimleri: 15m giris kolu yok (sahip karari)
_KAYNAK: dict[str, HistoricalSource] = {}


def kaynak(hist_dir: str | Path) -> HistoricalSource:
    key = str(Path(hist_dir).resolve())
    s = _KAYNAK.get(key)
    if s is None:
        s = _KAYNAK[key] = HistoricalSource(hist_dir, synthetic_rules=True)
    return s


def _bars(src: HistoricalSource, pair: str, tf: str, until: datetime) -> pd.DataFrame | None:
    try:
        return src.bars(pair, tf, until)
    except DataError:
        return None


def load_pair_tf(hist_dir: str | Path, pair: str, tf: str, until: datetime | None = None
                 ) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """(trig, h4) ya da None (tetik/4s dosyasi yok ya da bos). `until` dislayici (UTC); None = tum tarih."""
    src = kaynak(hist_dir)
    until = until or SONSUZ
    h4 = _bars(src, pair, "4h", until)
    if h4 is None or len(h4) == 0:
        return None
    if tf == "4h":
        return h4, h4
    if tf == "1d":
        d1 = aggregate_4h_to_1d(h4)
        return (d1, h4) if len(d1) else None
    trig = _bars(src, pair, tf, until)
    if trig is None or len(trig) == 0:
        return None
    return trig, h4
