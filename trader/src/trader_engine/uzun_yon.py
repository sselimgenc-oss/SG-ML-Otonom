"""Uzun donem yon filtresi (23.11 fikir 7; kagit + canli ayni; ENTRY-only, cikislara dokunmaz).

Enstrumanin gunluk (1d) rejimi: kapanis, 1d EMA(`ema`) ve EMA'nin son `egim_gun` gundeki egimi.
  boga  = kapanis > EMA ve egim > 0      -> SHORT girisi reddedilir
  ayi   = kapanis < EMA ve egim < 0      -> LONG girisi reddedilir
  yatay = digerleri                      -> iki yon serbest
  veri_yok = tam kapanmis gun sayisi < max(min_gun, ema + egim_gun)  -> filtre UYGULANMAZ (fail-open BILINCLI: veri eksikligi
             yuzunden tum girisleri kesmek istemiyoruz; sayac `uzun_yon_veri_yok` artar).
Gunluk mumlar market.sqlite'in 4h barlarindan kurulur (store 1d tutmaz; tam 6 mumlu UTC gunu). Yalniz KAPANMIS gunler
kullanilir: `view.bars(until=simdi)` yalniz kapanmis 4h bari doner ve eksik/yarim gun atilir => bugunku acik gun sizmaz,
gelecek bilgi yok. Hesap (cift, son tam gun) basina onbelleklenir."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from trader_core.indicators import ema as _ema

BOGA, AYI, YATAY, VERI_YOK = "boga", "ayi", "yatay", "veri_yok"
BAR_PER_GUN = 6
GERI_BAKIS_EK_GUN = 200          # min gerekenin uzerine okunan ek gun (EMA isinmasi)


def gunluk_kapanislar(df, now: datetime) -> list[float]:
    """4h barlardan (index = acilis, UTC) tam 6 mumlu, `now`a kadar KAPANMIS UTC gunlerinin kapanislari (eskiden yeniye)."""
    if df is None or len(df) == 0 or "close" not in df.columns:
        return []
    c = df["close"].astype("float64")
    c = c[~c.index.duplicated(keep="last")]
    c = c[c.index + timedelta(hours=4) <= now]                      # yalniz kapanmis 4h mumlar (cagiran zaten sinirlar; ikinci emniyet)
    gun = c.groupby(c.index.normalize())
    out: list[float] = []
    for _d, g in gun:
        if len(g) == BAR_PER_GUN and len({t.hour for t in g.index}) == BAR_PER_GUN:
            out.append(float(g.iloc[-1]))
    return out


def sinifla(kapanislar: list[float], ema_n: int, egim_gun: int, min_gun: int) -> str:
    if len(kapanislar) < max(min_gun, ema_n + egim_gun):
        return VERI_YOK
    s = _ema(pd.Series(kapanislar, dtype="float64"), ema_n).to_numpy()
    son, onceki = s[-1], s[-1 - egim_gun]
    if not (np.isfinite(son) and np.isfinite(onceki)):
        return VERI_YOK
    k, egim = kapanislar[-1], son - onceki
    if k > son and egim > 0:
        return BOGA
    if k < son and egim < 0:
        return AYI
    return YATAY


def reddeder(rejim: str, yon: str) -> bool:
    return (rejim == BOGA and yon == "short") or (rejim == AYI and yon == "long")


class UzunYon:
    def __init__(self, cfg: Mapping[str, int], bars_fn: Callable | None = None) -> None:
        self.ema = int(cfg["ema"])
        self.egim_gun = int(cfg["egim_gun"])
        self.min_gun = int(cfg["min_gun"])
        self.bars_fn = bars_fn                       # (pair, tf, until, n) -> DataFrame (4h; index UTC 'close'); None => hep veri_yok
        self._onbellek: dict[str, tuple[datetime, str]] = {}

    def rejim(self, pair: str, now: datetime) -> str:
        gun0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hit = self._onbellek.get(pair)
        if hit is not None and hit[0] == gun0:
            return hit[1]
        if self.bars_fn is None:
            return VERI_YOK
        n = BAR_PER_GUN * (max(self.min_gun, self.ema + self.egim_gun) + GERI_BAKIS_EK_GUN)
        r = sinifla(gunluk_kapanislar(self.bars_fn(pair, "4h", now, n), now), self.ema, self.egim_gun, self.min_gun)
        self._onbellek[pair] = (gun0, r)
        return r
