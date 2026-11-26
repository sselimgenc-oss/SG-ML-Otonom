"""Paket 2 / C3 (26.11 sahip karari #8): pencere ici delik GOZLEMI (kip `say`): sayac + karar ayrintisi; SONUC DEGISMEZ.

`bars.window_missing`: son `son_n` satirda eksik izgara adimi; olu (hacim 0) satirlar indekste durdugu icin delik DEGILDIR."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader_engine import bars as B
from trader_engine import strategy_runner as SR


def _idx(n: int, tf: str = "1h", atla=()):
    ix = pd.date_range("2026-03-02", periods=n + len(atla), freq={"1h": "1h", "4h": "4h", "1d": "1D"}[tf], tz="UTC")
    return ix.delete(list(atla)) if atla else ix


def test_window_missing_birim():
    assert B.window_missing(_idx(100), "1h", 50) == 0                           # deliksiz
    assert B.window_missing(_idx(100, atla=(60, 61, 62)), "1h", 100) == 3         # ortada 3 eksik adim
    assert B.window_missing(_idx(100, atla=(60, 61, 62)), "1h", 10) == 0          # delik pencere disinda (en eski taraf)
    assert B.window_missing(_idx(100, atla=(95,)), "1h", 10) == 1
    assert B.window_missing(_idx(0), "1h", 10) == 0


def test_olu_satir_delik_degil():
    ix = _idx(60)
    df = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0.0}, index=ix)      # tumu olu ama izgara tam
    assert B.window_missing(df.index, "1h", 60) == 0


def test_window_missing_series_ile_ayni():
    ix = _idx(300, atla=(100, 101, 200))
    s = B.window_missing_series(ix, "1h", 50)
    for t in (10, 99, 120, 150, 250, len(ix) - 1):
        assert s[t] == B.window_missing(ix[: t + 1], "1h", 50), t


class _Runner:
    """`_delik_say` yalniz sayac/durum kullanir."""
    def __init__(self):
        from collections import Counter
        self.counters = Counter()
        self._delik_tf = {}


def _runner_sinifi():
    for n in dir(SR):
        c = getattr(SR, n)
        if isinstance(c, type) and hasattr(c, "_delik_say"):
            return c
    pytest.fail("_delik_say sahibi sinif yok")


def test_say_kipinde_sayac_artar_sonuc_degismez():
    C = _runner_sinifi()
    r = _Runner()
    r._delik_say = C._delik_say.__get__(r)
    assert SR.PENCERE_DELIK_KIPI == "say"
    deliksiz = _idx(1300)
    delikli = _idx(1300, atla=(1250,))
    assert r._delik_say("1h", deliksiz) == 0 and not r.counters
    assert r._delik_say("1h", delikli) == 1 and r.counters["pencere_delik:1h"] == 1 and r._delik_tf["1h"] == 1
    # `_tail_ok` (karar kapisi) delikli pencerede DEGISMEZ: son 20 mum kesintisiz => gecer (say kipi kapi degildir)
    assert C._tail_ok(delikli, "1h", B.MIN_CONTIG_ARM["trigger"]) is True
