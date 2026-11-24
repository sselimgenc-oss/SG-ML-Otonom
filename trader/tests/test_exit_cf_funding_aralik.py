"""Karsi-olgu funding: kaydin kendi saati (4s/1s kayitlar da odenir); 8s sonuclari eskisiyle ayni."""
from __future__ import annotations

import pytest

from exit_cf_support import HR, NOW_MS, T0_MS
from trader_core import exit_counterfactual as EC


def test_8s_izgara_sonucu_degismez():
    pts = [(T0_MS + 8 * HR * k, 0.0001, 100.0) for k in range(0, 4)]
    toplam, eksik = EC._funding_fn(pts, NOW_MS, "long", 2.0, 100.0)(T0_MS, T0_MS + 24 * HR)
    assert eksik is None and toplam == pytest.approx(3 * 2.0 * 100.0 * 0.0001)


def test_4s_kayitlar_kendi_saatinde_odenir():
    p8 = [(T0_MS + 8 * HR * k, 0.0001, 100.0) for k in range(0, 4)]
    p4 = p8 + [(T0_MS + (4 + 8 * k) * HR + 5, 0.0001, 100.0) for k in range(0, 3)]   # 04/12/20 (+5 ms)
    t8, _ = EC._funding_fn(p8, NOW_MS, "long", 2.0, 100.0)(T0_MS, T0_MS + 24 * HR)
    t4, eksik = EC._funding_fn(p4, NOW_MS, "long", 2.0, 100.0)(T0_MS, T0_MS + 24 * HR)
    assert eksik is None
    assert t4 == pytest.approx(t8 + 3 * 2.0 * 100.0 * 0.0001)


def test_1s_kayitlar_her_saat_odenir():
    pts = [(T0_MS + HR * k, 0.0001, 100.0) for k in range(0, 25)]
    toplam, eksik = EC._funding_fn(pts, NOW_MS, "short", 2.0, 100.0)(T0_MS, T0_MS + 24 * HR)
    assert eksik is None and toplam == pytest.approx(-24 * 2.0 * 100.0 * 0.0001)
