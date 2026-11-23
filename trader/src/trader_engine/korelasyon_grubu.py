"""Korelasyon grubu (23.11 kullanici karari: asama B esikleri). Iki cift, son `pencere_gun` gunun 1 saatlik getiri korelasyonu
>= `esik` ise AYNI grupta. Matris market.sqlite barlarindan hesaplanir (en cok saatte bir yenilenir, bellekte onbellek).
Yeterli ortak getiri yoksa (ya da hesap/veri hatasi) o cift icin SABIT kume uyeligi (`clusters`) yedektir. Asla istisna yaymaz.
Seans disi araclar (hisse/emtia) eldeki barlarla hesaplanir; eksik saatler getiri uretmez (ardisik olmayan barlar arasi getiri yok)."""
from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta

from . import arm_guard as AG

log = logging.getLogger("engine.korelasyon")

MIN_ORTAK_GETIRI = 200          # bu sayidan az ortak saatlik getiri => yetersiz veri => sabit kume yedegi
YENILE_S = 3600.0


def getiriler(df):
    """1s kapanislardan (ardisik saatler arasi) getiri serisi; yetersiz/bozuk girdide None."""
    if df is None or len(df) < 3 or "close" not in df.columns:
        return None
    c = df["close"].astype("float64")
    c = c[~c.index.duplicated(keep="last")]
    prev = c.copy()
    prev.index = prev.index + timedelta(hours=1)
    prev = prev.reindex(c.index)
    r = (c / prev - 1.0).replace([float("inf"), float("-inf")], float("nan")).dropna()
    return r if len(r) else None


class KorelasyonGruplari:
    def __init__(self, bars_fn: Callable | None, pairs: Sequence[str], clusters: Mapping, esik: float, pencere_gun: int,
                 min_ortak: int = MIN_ORTAK_GETIRI, yenile_s: float = YENILE_S) -> None:
        self.bars_fn = bars_fn                       # (pair, tf, until, n) -> DataFrame (index UTC, 'close'); None = hep sabit kume
        self.pairs = tuple(pairs)
        self.clusters = clusters
        self.esik = float(esik)
        self.pencere_gun = int(pencere_gun)
        self.min_ortak = int(min_ortak)
        self.yenile_s = float(yenile_s)
        self._corr: dict[str, dict[str, float]] = {}
        self._son: datetime | None = None
        self.yenileme = 0                            # kac kez hesaplandi (test/izleme)
        self.hesaplanan_cift = 0

    # ------------------------------------------------------------------ matris
    def _yenile(self, now: datetime) -> None:
        if self._son is not None and (now - self._son).total_seconds() < self.yenile_s:
            return
        self._son = now                               # hata olsa da saatte bir denenir
        self.yenileme += 1
        corr: dict[str, dict[str, float]] = {}
        try:
            if self.bars_fn is None:
                self._corr = {}
                return
            import pandas as pd
            seri = {}
            n = self.pencere_gun * 24 + 1
            for p in self.pairs:
                try:
                    r = getiriler(self.bars_fn(p, "1h", now, n))
                except Exception as e:  # noqa: BLE001 - tek cift hatasi yalniz o cifti yedege dusurur
                    log.warning("korelasyon: %s barlari okunamadi: %s: %s", p, type(e).__name__, e)
                    r = None
                if r is not None:
                    seri[p] = r
            if len(seri) >= 2:
                m = pd.DataFrame(seri).corr(min_periods=self.min_ortak)
                for a in m.columns:
                    row = {}
                    for b in m.columns:
                        v = m.at[a, b]
                        if a != b and isinstance(v, float) and math.isfinite(v):
                            row[b] = float(v)
                    corr[a] = row
            self._corr = corr
            self.hesaplanan_cift = sum(len(v) for v in corr.values()) // 2
        except Exception as e:  # noqa: BLE001
            log.warning("korelasyon matrisi hesaplanamadi, sabit kume yedegi: %s: %s", type(e).__name__, e)
            self._corr = {}

    def korelasyon(self, a: str, b: str, now: datetime) -> float | None:
        self._yenile(now)
        v = self._corr.get(a, {}).get(b)
        if v is None:
            v = self._corr.get(b, {}).get(a)
        return v

    # ------------------------------------------------------------------ grup
    def ayni_grup(self, a: str, b: str, now: datetime) -> bool:
        if a == b:
            return True
        c = self.korelasyon(a, b, now)
        if c is not None:
            return c >= self.esik
        try:
            return bool(set(AG.clusters_of(a, self.clusters)) & set(AG.clusters_of(b, self.clusters)))
        except Exception:  # noqa: BLE001
            return False

    def grup_sayisi(self, aday: str, yon: str, pozisyonlar: Sequence, now: datetime) -> int:
        """Adayla ayni gruptaki, AYNI yonde acik pozisyon sayisi."""
        return sum(1 for p in pozisyonlar if p.side == yon and p.pair != aday and self.ayni_grup(aday, p.pair, now))
