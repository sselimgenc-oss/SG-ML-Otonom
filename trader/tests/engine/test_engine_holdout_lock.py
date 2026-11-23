"""HOLDOUT kilidi ACIK (23.11.2026 kullanici karari, holdout.KILIT_ACIK): run_range kilitli donemle kesisen araligi da okur.
Kilit kapali (KILIT_ACIK=False) davranisi bayrak monkeypatch ile ayrica sinanir."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from trader_engine import holdout as H
from trader_engine.engine import Engine
from trader_engine.holdout import BacktestArgError

UTC = timezone.utc


class _Touched(Exception):
    pass


class _FailingView:
    def __getattr__(self, name):
        raise _Touched(name)


def _engine(mode: str) -> Engine:
    e = object.__new__(Engine)
    e.cfg = SimpleNamespace(mode=mode)
    e.view = _FailingView()
    e.tf = "1h"
    e.step_tf = "1h"                       # DD-12 WP-11: karar adimi tf (tekli stratejide tf ile ayni)
    return e


def _d(y, m, d):
    return datetime(y, m, d, tzinfo=UTC)


def test_kilit_acik_bayragi():
    assert H.KILIT_ACIK is True


def test_acik_kilitte_check_holdout_gecer():
    H.check_holdout(_d(2026, 5, 1), _d(2026, 11, 1))
    H.check_holdout(_d(2026, 10, 1), _d(2026, 10, 2))
    assert not H.in_holdout(_d(2026, 6, 1))


def test_acik_kilitte_run_range_holdout_icinde_bar_okumaya_gecer():
    # kilit reddi yok -> ilk view erisimi (_Touched) gelir
    for s, e in ((_d(2026, 10, 1), _d(2026, 10, 2)), (_d(2026, 4, 30), _d(2026, 5, 2)), (_d(2026, 10, 31), _d(2026, 11, 2))):
        with pytest.raises(_Touched):
            _engine("backtest").run_range(s, e)


def test_paper_mode_not_guarded():
    with pytest.raises(_Touched):
        _engine("paper").run_range(_d(2026, 10, 1), _d(2026, 10, 2))


def test_kapali_kilitte_eski_davranis(monkeypatch):
    monkeypatch.setattr(H, "KILIT_ACIK", False)
    assert H.in_holdout(_d(2026, 6, 1))
    with pytest.raises(BacktestArgError) as ei:
        _engine("backtest").run_range(_d(2026, 10, 1), _d(2026, 10, 2))
    assert ei.value.code == "holdout_locked"
    for s, e in ((_d(2026, 4, 30), _d(2026, 5, 2)), (_d(2026, 10, 31), _d(2026, 11, 2))):
        with pytest.raises(BacktestArgError):
            _engine("backtest").run_range(s, e)
    for s, e in ((_d(2026, 4, 1), _d(2026, 5, 1)), (_d(2026, 11, 1), _d(2026, 11, 2))):
        with pytest.raises(_Touched):
            _engine("backtest").run_range(s, e)
