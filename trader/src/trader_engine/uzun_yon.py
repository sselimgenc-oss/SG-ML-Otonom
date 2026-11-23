"""Uzun donem yon filtresi (23.11 fikir 7; kagit + canli ayni; ENTRY-only, cikislara dokunmaz).

Enstrumanin gunluk (1d) rejimi: kapanis, 1d EMA(`ema`) ve EMA'nin son `egim_gun` gundeki egimi.
  boga  = kapanis > EMA ve egim > 0      -> SHORT girisi reddedilir
  ayi   = kapanis < EMA ve egim < 0      -> LONG girisi reddedilir
  yatay = digerleri                      -> iki yon serbest
  veri_yok = tam kapanmis gun sayisi < max(min_gun, ema + egim_gun)  -> filtre UYGULANMAZ (fail-open BILINCLI: veri eksikligi
             yuzunden tum girisleri kesmek istemiyoruz; sayac `uzun_yon_veri_yok` artar).
Gunluk mumlar market.sqlite'in 4h barlarindan kurulur (store 1d tutmaz). Kapanmis her UTC gunu (gun < bugun UTC) icin gunluk
kapanis = o gunun mevcut 4h mumlarinin SON mumunun kapanisi (en az 1 mum; seansli hisse/emtia da gun uretir). Bugunku acik gun
asla girmez; `view.bars(until=simdi)` yalniz kapanmis 4h bari doner => gelecek bilgi yok. Onbellek anahtari (cift, son tam
gun, o gunun son mum zamani): gece yarisi son mum henuz yazilmadiysa sonuc sabitlenmez (gun basindan 8 saat gecene dek her
cagrida yeniden okunur; sonra ayni anahtarla gun boyu tekrar kullanilir)."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from trader_core.indicators import ema as _ema

from . import arm_guard as AG

BOGA, AYI, YATAY, VERI_YOK = "boga", "ayi", "yatay", "veri_yok"
SETTLE_SAAT = 8                  # gece yarisindan bu kadar sonra son tam gunun mumlari yerlesmis sayilir (onbellek sabitlenir)
GERI_BAKIS_EK_GUN = 200          # min gerekenin uzerine okunan ek gun (EMA isinmasi)


def _gunluk(df, now: datetime) -> list[tuple[pd.Timestamp, pd.Timestamp, float]]:
    """[(gun, gunun son 4h mumunun acilisi, gunluk kapanis)] eskiden yeniye; yalniz gun < bugun (UTC) ve kapanmis 4h mumlar."""
    if df is None or len(df) == 0 or "close" not in df.columns:
        return []
    keep = AG.active_mask(df)                                        # olu (hacim 0, o=h=l=c) 4s mumlar: hafta sonu/tatil gunleri gunluk seriye girmez
    if keep is not None:
        df = df[keep]
        if len(df) == 0:
            return []
    c = df["close"].astype("float64")
    c = c[~c.index.duplicated(keep="last")].sort_index()
    c = c[c.index + timedelta(hours=4) <= now]                      # yalniz kapanmis 4h mumlar (cagiran zaten sinirlar; ikinci emniyet)
    bugun = pd.Timestamp(now).normalize()
    c = c[c.index.normalize() < bugun]                               # bugunku acik gun asla girmez
    return [(gun, g.index[-1], float(g.iloc[-1])) for gun, g in c.groupby(c.index.normalize())]


def gunluk_kapanislar(df, now: datetime) -> list[float]:
    """4h barlardan (index = acilis, UTC) `now`a kadar KAPANMIS UTC gunlerinin kapanislari (gunun son mumu; eskiden yeniye)."""
    return [k for _g, _t, k in _gunluk(df, now)]


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
        self._onbellek: dict[str, tuple[tuple, str]] = {}    # cift -> ((son tam gun, son mum zamani), rejim)

    def rejim(self, pair: str, now: datetime) -> str:
        if self.bars_fn is None:
            return VERI_YOK
        gun0 = pd.Timestamp(now).normalize()
        hit = self._onbellek.get(pair)
        if hit is not None and hit[0][0] == gun0 and (now - gun0 >= timedelta(hours=SETTLE_SAAT) or hit[0][1].hour == 24 - 4):
            return hit[1]                                           # ayni gun, son tam gunun mumlari yerlesmis: anahtar degismez
        n = 6 * (max(self.min_gun, self.ema + self.egim_gun) + GERI_BAKIS_EK_GUN)
        gunler = _gunluk(self.bars_fn(pair, "4h", now, n), now)
        anahtar = (gun0, gunler[-1][1]) if gunler else (gun0, pd.Timestamp(0, tz="UTC"))
        if hit is not None and hit[0] == anahtar:
            return hit[1]
        r = sinifla([k for _g, _t, k in gunler], self.ema, self.egim_gun, self.min_gun)
        self._onbellek[pair] = (anahtar, r)
        return r
