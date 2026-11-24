"""Funding: kaydin KENDI zamani (aralik-bagimsiz). 8s semboller eskisiyle birebir; 4s/1s semboller her olayi bir kez oder."""
from __future__ import annotations

from datetime import timedelta

import pytest

from trader_engine.types import FundingPoint

from test_engine_03_impl_smoke import P, T0, bar, enter, mk, step

QTY = 6.369
ODEME = QTY * 101.0 * 0.0001          # tek funding olayi (long, mark 101, oran 1e-4)


def _calistir(saatler):
    """T0=09:00 girisi; funding noktalari `saatler` (gun saati, 24+ ertesi gun); her saat basinda bir dakikalik mum."""
    pts = [FundingPoint(P, T0 + timedelta(hours=h - 9), 0.0001, 101.0) for h in saatler]
    b, _ = mk(fpts=pts)
    enter(b, QTY)
    olaylar = []
    for h in range(10, 34):                      # ertesi gun 09:00'a kadar saat basi adimlari
        olaylar += [e for e in step(b, {P: bar((h - 9) * 60)}) if e.kind == "funding"]
    return b, olaylar


def test_8s_izgara_eskisiyle_ayni():
    b, ev = _calistir([16, 24, 32])               # 16:00, 00:00, 08:00
    assert [e.ts for e in ev] == [T0 + timedelta(hours=7), T0 + timedelta(hours=15), T0 + timedelta(hours=23)]
    assert [e.funding_paid for e in ev] == [pytest.approx(ODEME)] * 3
    assert b.positions()[0].funding_paid == pytest.approx(3 * ODEME)
    assert b.counters()["funding_missing"] == 0


def test_4s_aralik_her_olay_bir_kez_odenir():
    b, ev = _calistir([12, 16, 20, 24, 28, 32])   # 4 saatte bir
    assert [e.ts.hour for e in ev] == [12, 16, 20, 0, 4, 8]
    assert len({e.ts for e in ev}) == 6           # tekrar yok
    assert b.positions()[0].funding_paid == pytest.approx(6 * ODEME)
    assert b.counters()["funding_missing"] == 0


def test_1s_aralik_her_olay_bir_kez_odenir():
    b, ev = _calistir(list(range(10, 34)))        # her saat: 10:00 .. ertesi gun 09:00 = 24 olay
    assert len(ev) == len({e.ts for e in ev})
    assert len(ev) == 24
    assert b.positions()[0].funding_paid == pytest.approx(len(ev) * ODEME)


def test_4s_ayni_8s_dilimde_iki_olay_birlesmez():
    b, ev = _calistir([12, 16])                   # 08-16 diliminde iki olay: 12:00 izgara disi, 16:00 izgarada
    assert [e.ts.hour for e in ev] == [12, 16]
    assert b.positions()[0].funding_paid == pytest.approx(2 * ODEME)


def test_acilistan_once_ve_acilis_aninda_olay_odenmez():
    b, ev = _calistir([8, 9, 10])                 # 08:00 ve 09:00 (giris ani) odenmez; 10:00 odenir
    assert [e.ts.hour for e in ev] == [10]
