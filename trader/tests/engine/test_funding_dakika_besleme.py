"""Funding: dakika adimlari, ms kaymasi, gec gelen kayit, anlik goruntu; canli besleme 4s kaydi kendi saatine yazar."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from trader_engine.bars import to_ms
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import CostModel
from trader_engine.marketdata.feed import Feed, _floor_funding_ms
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import FundingPoint

from test_engine_03_impl_smoke import P, RULES, T0, bar, enter, step

QTY = 6.369
ODEME = QTY * 101.0 * 0.0001


def _broker(pts_list):
    b = PaperBroker(PaperConfig(cost=CostModel(), mmr=0.004), lambda p: RULES,
                    lambda p, a, z: [x for x in pts_list if a < x.ts <= z], SimClock(T0), None)
    enter(b, QTY)
    return b


def _dakikalar(b, bas, son, ekle=None):
    olay = []
    for dk in range(bas, son + 1):
        if ekle:
            ekle(dk)
        olay += [e for e in step(b, {P: bar(dk)}) if e.kind == "funding"]
    return olay


def test_4s_ms_kayan_kayit_dakika_adimlarinda_bir_kez_odenir():
    pts = []
    b = _broker(pts)
    pts.append(FundingPoint(P, T0 + timedelta(hours=3, milliseconds=5), 0.0001, 101.0))   # 12:00:00.005
    olay = _dakikalar(b, 1, 5 * 60)
    assert [e.ts.hour for e in olay] == [12]
    assert b.positions()[0].funding_paid == pytest.approx(ODEME)
    assert b.counters()["funding_missing"] == 0


def test_4s_gec_gelen_kayit_bekleme_icinde_odenir_tekrar_odenmez():
    pts = []
    b = _broker(pts)
    h12 = T0 + timedelta(hours=3)

    def ekle(dk):
        if dk == 3 * 60 + 7:                       # kayit 12:07'de depoya geldi (saat basi damgali)
            pts.append(FundingPoint(P, h12, 0.0001, 101.0))
    olay = _dakikalar(b, 1, 5 * 60, ekle)
    assert [e.ts for e in olay] == [h12]
    assert b.positions()[0].funding_paid == pytest.approx(ODEME)


def test_8s_ms_kayan_kayit_eskisi_gibi_odenir():
    pts = []
    b = _broker(pts)
    pts.append(FundingPoint(P, T0 + timedelta(hours=7, milliseconds=3), 0.0001, 101.0))   # 16:00:00.003
    olay = _dakikalar(b, 1, 9 * 60)
    assert [e.ts.hour for e in olay] == [16]
    assert b.counters()["funding_missing"] == 0


def test_anlik_goruntu_odenen_saatleri_tasir():
    pts = []
    b = _broker(pts)
    pts.append(FundingPoint(P, T0 + timedelta(hours=3), 0.0001, 101.0))
    _dakikalar(b, 1, 3 * 60 + 2)
    snap = b.snapshot()
    assert snap["funding_paid_ts"][P]
    b2 = _broker(pts)
    b2.restore(snap)
    assert b2._funding_paid == b._funding_paid


def test_besleme_4s_kayit_saatine_yazilir_8s_izgaraya_dusmez(tmp_path):
    s = MarketStore(tmp_path / "m.sqlite")
    t12 = to_ms(T0 + timedelta(hours=3))
    assert _floor_funding_ms(t12 + 5) == t12                          # 12:00:00.005 -> 12:00 (eskiden 08:00)
    rows = [{"fundingTime": t12 - 4 * 3_600_000 + 2, "fundingRate": "0.0001"},    # 08:00:00.002
            {"fundingTime": t12 + 5, "fundingRate": "0.0002"}]                    # 12:00:00.005
    fake = SimpleNamespace(store=s, rest=SimpleNamespace(funding_rates=lambda sym, start_ms=None: rows),
                           _rest=lambda fn, *a, **k: fn(*a, **k), _mark_at=lambda pair, ts: None,
                           _ok=lambda *a, **k: None)
    Feed._funding(fake, P, "BTCUSDT", t12 + 60_000)
    got = s.query_funding(P, 0, t12 + 3_600_000)
    assert [(to_ms(p.ts), p.rate) for p in got] == [(t12 - 4 * 3_600_000, 0.0001), (t12, 0.0002)]
