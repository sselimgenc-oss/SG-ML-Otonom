"""Saglik uygulamasi duman testleri (spec ornekleri 13.x'in alt kumesi)."""
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import health as H
from trader_core.health import (ApiProbe, ContainerProbe, HealthConfig, HealthSnapshot, LedgerProbe, Status)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


NOW = datetime(2026, 11, 16, 12, 30, tzinfo=timezone.utc)
GIB, MIB = 1024 ** 3, 1024 ** 2


def t(h, m, s=0):
    return datetime(2026, 11, 16, h, m, s, tzinfo=timezone.utc)


def snap(**kw):
    api = {b: ApiProbe(True, t(12, 29, 30), t(12, 0), (), True) for b in ("learner", "twin")}
    led = {b: LedgerProbe(t(12, 0, 2), 0, (), True, True, 0) for b in ("learner", "twin")}
    cont = {f"trader-{b}": ContainerProbe("running", 4, t(1, 0), False) for b in ("learner", "twin")}
    base = dict(now=NOW, timeframe_s=3600, api=api, ledger=led, disk_free_bytes=20 * GIB,
                containers=cont, prev_restart_counts={"trader-learner": 4, "trader-twin": 4},
                last_backup_at=t(3, 10))
    base.update(kw)
    return HealthSnapshot(**base)


def res(rep, name):
    return next(r for r in rep.results if r.name == name)


def test_all_ok():
    rep = H.evaluate(snap())
    assert rep.overall is Status.OK and rep.healthy
    assert H.should_send_ok(rep)


@pytest.mark.parametrize("candle,status", [(t(10, 30), Status.OK), (t(10, 29), Status.OK),
                                           (t(10, 27), Status.WARN), (t(9, 27), Status.CRIT),
                                           (t(9, 30), Status.WARN)])
def test_candle(candle, status):
    s = snap()
    api = dict(s.api)
    api["learner"] = ApiProbe(True, t(12, 29, 30), candle, (), True)
    r = res(H.evaluate(snap(api=api)), "candle_age:learner")
    assert r.status is status
    if status is Status.CRIT:
        assert r.code == "stale_candle"


def test_api_none_unknown_no_heartbeat():
    api = dict(snap().api)
    api["learner"] = ApiProbe()
    rep = H.evaluate(snap(api=api))
    assert rep.overall is Status.UNKNOWN and not rep.healthy and not H.should_send_ok(rep)


def test_disk():
    assert res(H.evaluate(snap(disk_free_bytes=3 * GIB)), "disk_free").status is Status.OK
    assert res(H.evaluate(snap(disk_free_bytes=int(2.5 * GIB))), "disk_free").status is Status.WARN
    r = res(H.evaluate(snap(disk_free_bytes=int(0.9 * GIB))), "disk_free")
    assert r.status is Status.CRIT and r.code == "disk_low"


def test_container_and_warmup():
    def cont(**kw):
        d = dict(state="running", restart_count=4, started_at=t(1, 0), oom_killed=False)
        d.update(kw)
        return {"trader-learner": ContainerProbe(**d), "trader-twin": ContainerProbe("running", 4, t(1, 0), False)}
    n = "container_restarts:trader-learner"
    assert res(H.evaluate(snap(containers=cont())), n).status is Status.OK
    assert res(H.evaluate(snap(containers=cont(restart_count=5))), n).status is Status.WARN
    assert res(H.evaluate(snap(containers=cont(restart_count=7))), n).status is Status.CRIT
    assert res(H.evaluate(snap(containers=cont(state="restarting"))), n).status is Status.CRIT
    r = res(H.evaluate(snap(containers=cont(oom_killed=True))), n)
    assert r.code == "oom_killed"
    # isinma: bayat mum CRIT -> WARN
    api = dict(snap().api)
    api["learner"] = ApiProbe(True, t(12, 29, 30), t(9, 27), (), True)
    rep = H.evaluate(snap(api=api, containers=cont(started_at=t(12, 25))))
    assert res(rep, "candle_age:learner").code == "stale_candle_warmup"
    assert res(rep, "candle_age:learner").status is Status.WARN


def test_gate():
    led = dict(snap().ledger)
    led["learner"] = LedgerProbe(t(12, 0, 2), 1, (), True, True, 0)
    rep = H.evaluate(snap(ledger=led))
    assert res(rep, "ledger_gate:learner").code == "spool_pending" and rep.overall is Status.CRIT
    led["learner"] = LedgerProbe(t(12, 0, 2), None, (), True, True, 0)
    assert res(H.evaluate(snap(ledger=led)), "ledger_gate:learner").status is Status.UNKNOWN


def test_combine_missing_skew_placeholders():
    R = lambda s: H.CheckResult("x", s, "c", "d")  # noqa: E731
    assert H.combine([R(Status.OK), R(Status.OK), R(Status.SKIPPED), R(Status.WARN)]) is Status.WARN
    assert H.combine([R(Status.OK), R(Status.UNKNOWN), R(Status.WARN)]) is Status.UNKNOWN
    assert H.combine([R(Status.SKIPPED)]) is Status.UNKNOWN and H.combine([]) is Status.UNKNOWN
    rep = H.evaluate(snap(ledger={}))
    assert res(rep, "ledger_gate:learner").code == "missing_check" and rep.overall is Status.UNKNOWN
    api = dict(snap().api)
    api["learner"] = ApiProbe(True, t(12, 31), t(12, 0), (), True)
    assert res(H.evaluate(snap(api=api)), "bot_loop_age:learner").code == "clock_skew"
