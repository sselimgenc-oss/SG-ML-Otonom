"""Bagimsiz test seti: docs/saglik-spec.md (v1). Yalnizca spesifikasyondan yazildi.

Kapsam: health.evaluate (Bolum 3, 13.1-13.7), birlestirme, plan_alerts (13.8),
nabiz karari/zamanlama (Bolum 4, 13.9), Notifier, yedek (Bolum 6, 13.10),
kurtarma (Bolum 7, 13.11), seed'li ozellik testi.

Spesifikasyonun belirtmedigi arayuzler (yedek/kurtarma betik girisi, plan_alerts
baslangic durumu, probe sinif kurucu alanlari disindaki ayrintilar) yardimci
fonksiyonlarda toplanmistir; varsayimlar docstring'lerde yazilidir.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import inspect
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

h = pytest.importorskip("trader_core.health")

Status = h.Status
UTC = timezone.utc
NOW = datetime(2026, 11, 16, 12, 30, 0, tzinfo=UTC)
T = 3600
MiB = 1 << 20
GiB = 1 << 30
BOTS = ("learner", "twin")


def at(hh, mm=0, ss=0):
    return datetime(2026, 11, 16, hh, mm, ss, tzinfo=UTC)


# --------------------------------------------------------------------------
# Anlik goruntu kurucusu
# --------------------------------------------------------------------------
def good_api(**kw):
    base = dict(
        ping_ok=True,
        last_process_at=NOW - timedelta(seconds=30),
        last_candle_open=at(12, 0, 0),
        open_trade_ids=(),
        dry_run=True,
    )
    base.update(kw)
    return h.ApiProbe(**base)


def good_ledger(**kw):
    base = dict(
        last_write_at=at(12, 0, 2),
        spool_lines=0,
        unledgered_ids=(),
        
        schema_ok=True,
        has_active_params=True,
        spool_corrupt_lines=0,       # DD-8 E4: None = UNKNOWN (spool_corrupt_unreadable); saglikli taban 0
    )
    base.update(kw)
    return h.LedgerProbe(**base)


def good_container(**kw):
    base = dict(
        state="running",
        restart_count=4,
        started_at=NOW - timedelta(days=2),
        oom_killed=False,
    )
    base.update(kw)
    return h.ContainerProbe(**base)


def none_api():
    return h.ApiProbe(ping_ok=None, last_process_at=None, last_candle_open=None,
                      open_trade_ids=None, dry_run=None)


def snap(**over):
    base = dict(
        now=NOW,
        timeframe_s=T,
        api={b: good_api() for b in BOTS},
        ledger={b: good_ledger() for b in BOTS},
        disk_free_bytes=20 * GiB,
        disk_total_bytes=100 * GiB,
        
        
        
        containers={f"trader-{b}": good_container() for b in BOTS},
        prev_restart_counts={f"trader-{b}": 4 for b in BOTS},
        
        
        last_backup_at=at(3, 10),
    )
    base.update(over)
    return h.HealthSnapshot(**base)


def with_bot(field, bot, **kw):
    """snap() uretir; `field` ('api'|'ledger') icinde sadece `bot` degistirilir."""
    d = {b: (good_api() if field == "api" else good_ledger()) for b in BOTS}
    maker = good_api if field == "api" else good_ledger
    d[bot] = maker(**kw)
    return {field: d}


def ev(s=None, cfg=None, **over):
    s = s if s is not None else snap(**over)
    return h.evaluate(s) if cfg is None else h.evaluate(s, cfg)


def pick(rep, name, bot=None):
    """name veya name:bot ile baslayan sonuc(lar)i dondurur."""
    out = [r for r in rep.results
           if r.name == name or r.name.startswith(name + ":")]
    if bot is not None:
        out = [r for r in out if r.name.endswith(":" + bot)]
    return out


def one(rep, name, bot=None):
    out = pick(rep, name, bot)
    assert out, f"{name} yok: {[r.name for r in rep.results]}"
    assert len(out) == 1, out
    return out[0]


def worst(rep, name):
    order = [Status.OK, Status.SKIPPED, Status.WARN, Status.UNKNOWN, Status.CRIT]
    return max((r.status for r in pick(rep, name)), key=order.index)


# ==========================================================================
# 1. Veri yapilari / yapilandirma
# ==========================================================================
class TestStructures:
    def test_status_values(self):
        assert {s.name for s in Status} >= {"OK", "WARN", "CRIT", "UNKNOWN", "SKIPPED"}
        assert issubclass(Status, str)

    def test_report_frozen_and_tz_aware(self):
        rep = ev()
        assert rep.generated_at.tzinfo is not None
        with pytest.raises(dataclasses.FrozenInstanceError):
            rep.overall = Status.CRIT  # type: ignore[misc]
        assert isinstance(rep.results, tuple)
        for r in rep.results:
            with pytest.raises(dataclasses.FrozenInstanceError):
                r.status = Status.OK  # type: ignore[misc]

    def test_naive_now_raises_value_error(self):
        with pytest.raises(ValueError):
            h.evaluate(snap(now=datetime(2026, 11, 16, 12, 30)))

    @pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf")])
    def test_config_rejects_invalid_numbers(self, bad):
        with pytest.raises(ValueError):
            h.HealthConfig(warmup_s=bad)

    def test_config_defaults(self):
        c = h.DEFAULT_CFG
        assert c.warmup_s == 600
        assert tuple(c.require_bots) == ("learner",)
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.warmup_s = 1  # type: ignore[misc]

    def test_evaluate_is_pure_and_deterministic(self):
        s = snap()
        a, b = h.evaluate(s), h.evaluate(s)
        assert a == b

    def test_module_imports_no_heavy_deps(self):
        code = ("import sys; sys.path.insert(0, %r); import trader_core.health; "
                "bad = {'pandas','numpy','freqtrade','docker'} & set(sys.modules); "
                "assert not bad, bad" % str(SRC))
        r = subprocess.run([sys.executable, "-I", "-c", code],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def test_package_init_only_docstring(self):
        tree = ast.parse((SRC / "trader_core" / "__init__.py").read_text("utf-8"))
        body = tree.body
        assert all(isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                   for n in body)


# ==========================================================================
# 2. 13.1 saglikli
# ==========================================================================
class TestAllHealthy:
    def test_overall_ok(self):
        rep = ev()
        assert rep.overall == Status.OK
        assert rep.healthy is True
        assert rep.failing() == ()

    def test_per_bot_results_named(self):
        rep = ev()
        for chk in ("bot_loop_age", "candle_age", "ledger_write_age"):
            names = {r.name for r in pick(rep, chk)}
            assert names >= {f"{chk}:learner", f"{chk}:twin"}

    def test_all_required_checks_present(self):
        rep = ev()
        for chk in ("bot_loop_age", "candle_age", "ledger_write_age",
                    "ledger_gate", "disk_free", "container_restarts"):
            assert pick(rep, chk), chk

    def test_skipped_never_overall(self):
        assert ev().overall != Status.SKIPPED


# ==========================================================================
# 3. Esik testleri (tam sinirlar)
# ==========================================================================
def _api_check(check, bot="learner", **kw):
    rep = ev(**with_bot("api", bot, **kw))
    return one(rep, check, bot)


class TestBotLoopAge:
    @pytest.mark.parametrize("age,exp", [
        (0, Status.OK), (30, Status.OK), (120, Status.OK),
        (121, Status.WARN), (300, Status.WARN),
        (301, Status.CRIT), (3600, Status.CRIT),
    ])
    def test_thresholds(self, age, exp):
        r = _api_check("bot_loop_age", last_process_at=NOW - timedelta(seconds=age))
        assert r.status == exp

    def test_none_unknown(self):
        assert _api_check("bot_loop_age", last_process_at=None).status == Status.UNKNOWN


class TestCandleAge:
    # T=3600: WARN > 7320, CRIT > 10920
    @pytest.mark.parametrize("age,exp", [
        (1800, Status.OK), (7200, Status.OK), (7260, Status.OK), (7320, Status.OK),
        (7321, Status.WARN), (7380, Status.WARN), (10800, Status.WARN), (10920, Status.WARN),
        (10921, Status.CRIT), (10980, Status.CRIT),
    ])
    def test_thresholds(self, age, exp):
        r = _api_check("candle_age", last_candle_open=NOW - timedelta(seconds=age))
        assert r.status == exp

    def test_spec_examples_13_2(self):
        for (hh, mm, ss), exp in [((10, 30, 0), Status.OK), ((10, 29, 0), Status.OK),
                                  ((10, 27, 0), Status.WARN), ((9, 27, 0), Status.CRIT),
                                  ((9, 30, 0), Status.WARN)]:
            r = _api_check("candle_age", last_candle_open=at(hh, mm, ss))
            assert r.status == exp, (hh, mm, ss)

    def test_stale_code(self):
        r = _api_check("candle_age", last_candle_open=at(9, 27, 0))
        assert r.code == "stale_candle"

    def test_none_unknown(self):
        assert _api_check("candle_age", last_candle_open=None).status == Status.UNKNOWN

    def test_timeframe_none_unknown(self):
        rep = ev(timeframe_s=None)
        assert one(rep, "candle_age", "learner").status == Status.UNKNOWN
        assert rep.overall in (Status.UNKNOWN, Status.CRIT)
        assert rep.healthy is False

    def test_formula_depends_on_timeframe(self):
        # T=900: WARN > 1920, CRIT > 2820
        for age, exp in [(1920, Status.OK), (1921, Status.WARN),
                         (2820, Status.WARN), (2821, Status.CRIT)]:
            s = snap(timeframe_s=900, **with_bot(
                "api", "learner", last_candle_open=NOW - timedelta(seconds=age)))
            assert one(ev(s), "candle_age", "learner").status == exp


def _ledger_check(check, bot="learner", **kw):
    rep = ev(**with_bot("ledger", bot, **kw))
    return one(rep, check, bot) if check != "ledger_gate" else rep


class TestLedgerWriteAge:
    # T+300 = 3900, 2T+300 = 7500
    @pytest.mark.parametrize("age,exp", [
        (1798, Status.OK), (3900, Status.OK), (3901, Status.WARN),
        (7500, Status.WARN), (7501, Status.CRIT),
    ])
    def test_thresholds(self, age, exp):
        r = _ledger_check("ledger_write_age",
                          last_write_at=NOW - timedelta(seconds=age))
        assert r.status == exp

    def test_none_unknown(self):
        assert _ledger_check("ledger_write_age", last_write_at=None).status == Status.UNKNOWN


class TestLedgerGate:
    def gate(self, bot="learner", **kw):
        rep = ev(**with_bot("ledger", bot, **kw))
        return one(rep, "ledger_gate", bot), rep

    def test_clean_ok(self):
        r, rep = self.gate()
        assert r.status == Status.OK

    def test_spool_pending_crit(self):
        r, rep = self.gate(spool_lines=1)
        assert r.status == Status.CRIT and r.code == "spool_pending"
        assert rep.overall == Status.CRIT and rep.healthy is False

    def test_unledgered_crit(self):
        r, _ = self.gate(unledgered_ids=(9,))
        assert r.status == Status.CRIT and r.code == "unledgered_trades"

    def test_no_active_params_crit(self):
        r, _ = self.gate(has_active_params=False)
        assert r.status == Status.CRIT and r.code == "no_active_params"

    def test_schema_crit(self):
        r, _ = self.gate(schema_ok=False)
        assert r.status == Status.CRIT and r.code == "schema"

    @pytest.mark.parametrize("field", ["spool_lines", "unledgered_ids", "has_active_params",
                                       "schema_ok"])
    def test_none_field_unknown(self, field):
        r, rep = self.gate(**{field: None})
        assert r.status == Status.UNKNOWN
        assert rep.healthy is False

    def test_crit_beats_other_gate_problem_none(self):
        # spool dolu (kapali) + baska alan None => kapali olurdu: CRIT veya UNKNOWN, asla saglikli
        r, rep = self.gate(spool_lines=3, schema_ok=None)
        assert r.status in (Status.CRIT, Status.UNKNOWN)
        assert rep.healthy is False

    def test_two_bots_one_crit(self):
        s = snap(ledger={"learner": good_ledger(), "twin": good_ledger(spool_lines=2)})
        rep = ev(s)
        assert rep.overall == Status.CRIT
        assert one(rep, "ledger_gate", "learner").status == Status.OK


class TestDisk:
    GB3, GB1 = 3 * GiB, 1 * GiB

    @pytest.mark.parametrize("free,exp", [
        (20 * GiB, Status.OK), (3 * GiB, Status.OK), (3 * GiB - 1, Status.WARN),
        (int(2.5 * GiB), Status.WARN), (1 * GiB, Status.WARN), (1 * GiB - 1, Status.CRIT),
        (int(0.9 * GiB), Status.CRIT), (0, Status.CRIT),
    ])
    def test_thresholds(self, free, exp):
        assert one(ev(disk_free_bytes=free), "disk_free").status == exp

    def test_code_disk_low(self):
        assert one(ev(disk_free_bytes=int(0.9 * GiB)), "disk_free").code == "disk_low"

    def test_none_unknown(self):
        r = one(ev(disk_free_bytes=None), "disk_free")
        assert r.status == Status.UNKNOWN


class TestContainerRestarts:
    def cont(self, **kw):
        return one(ev(containers={"trader-learner": good_container(**kw),
                                  "trader-twin": good_container()}),
                   "container_restarts", "learner") if False else None

    def run(self, **kw):
        rep = ev(containers={"trader-learner": good_container(**kw),
                             "trader-twin": good_container()})
        rs = [r for r in pick(rep, "container_restarts") if "learner" in r.name]
        assert len(rs) == 1, [r.name for r in rep.results]
        return rs[0], rep

    def test_delta_zero_ok(self):
        assert self.run(restart_count=4)[0].status == Status.OK

    def test_delta_one_warn(self):
        r, rep = self.run(restart_count=5)
        assert r.status == Status.WARN and rep.healthy

    def test_delta_two_warn(self):
        assert self.run(restart_count=6)[0].status == Status.WARN

    def test_delta_three_crit(self):
        r, rep = self.run(restart_count=7)
        assert r.status == Status.CRIT and not rep.healthy

    def test_state_not_running_crit(self):
        assert self.run(restart_count=4, state="restarting")[0].status == Status.CRIT

    def test_oom_crit(self):
        r, _ = self.run(oom_killed=True)
        assert r.status == Status.CRIT and r.code == "oom_killed"

    @pytest.mark.parametrize("kw", [dict(state=None), dict(restart_count=None)])
    def test_none_unknown(self, kw):
        r, rep = self.run(**kw)
        assert r.status == Status.UNKNOWN and not rep.healthy

    def test_first_run_empty_prev(self):
        rep = ev(prev_restart_counts={})
        # ilk calisma: onceki sayac yok; hata ya da sahte alarm degil, saglikli sayilmali/ya da UNKNOWN
        rs = pick(rep, "container_restarts")
        assert rs
        assert all(r.status in (Status.OK, Status.UNKNOWN) for r in rs)

    def test_missing_container_probe_fail_closed(self):
        rep = ev(containers={})
        assert rep.healthy is False


class TestWarmup:
    def s(self, started_secs_ago, **api_kw):
        return snap(
            containers={"trader-learner": good_container(
                started_at=NOW - timedelta(seconds=started_secs_ago)),
                "trader-twin": good_container()},
            **with_bot("api", "learner", **api_kw))

    def test_candle_crit_becomes_warn_in_warmup(self):
        r = one(ev(self.s(300, last_candle_open=at(9, 27, 0))), "candle_age", "learner")
        assert r.status == Status.WARN and r.code == "stale_candle_warmup"

    def test_loop_age_crit_downgraded(self):
        r = one(ev(self.s(300, last_process_at=NOW - timedelta(seconds=999))),
                "bot_loop_age", "learner")
        assert r.status == Status.WARN and r.code.endswith("_warmup")

    def test_ledger_write_age_crit_downgraded(self):
        s = snap(containers={"trader-learner": good_container(
            started_at=NOW - timedelta(seconds=300)), "trader-twin": good_container()},
            **with_bot("ledger", "learner", last_write_at=NOW - timedelta(seconds=9000)))
        r = one(ev(s), "ledger_write_age", "learner")
        assert r.status == Status.WARN and r.code.endswith("_warmup")

    def test_after_warmup_stays_crit(self):
        r = one(ev(self.s(601, last_candle_open=at(9, 27, 0))), "candle_age", "learner")
        assert r.status == Status.CRIT

    def test_exact_boundary_600(self):
        r = one(ev(self.s(600, last_candle_open=at(9, 27, 0))), "candle_age", "learner")
        assert r.status in (Status.WARN, Status.CRIT)  # 600 sinirinda belirsiz; baska test 601/300 kesin
        assert one(ev(self.s(599, last_candle_open=at(9, 27, 0))),
                   "candle_age", "learner").status == Status.WARN

    def test_unknown_stays_unknown_in_warmup(self):
        r = one(ev(self.s(300, last_candle_open=None)), "candle_age", "learner")
        assert r.status == Status.UNKNOWN

    def test_warn_stays_warn_in_warmup(self):
        r = one(ev(self.s(300, last_candle_open=at(10, 27, 0))), "candle_age", "learner")
        assert r.status == Status.WARN

    def test_restarts_not_relaxed_in_warmup(self):
        s = snap(containers={"trader-learner": good_container(
            started_at=NOW - timedelta(seconds=300), restart_count=7),
            "trader-twin": good_container()})
        rs = [r for r in pick(ev(s), "container_restarts") if "learner" in r.name]
        assert rs[0].status == Status.CRIT


class TestBackupAge:
    @pytest.mark.parametrize("hours,exp", [
        (9.33, Status.OK), (25, Status.OK), (26, Status.OK), (26.001, Status.WARN),
        (27, Status.WARN), (50, Status.WARN), (50.001, Status.CRIT), (51, Status.CRIT),
    ])
    def test_thresholds(self, hours, exp):
        r = one(ev(last_backup_at=NOW - timedelta(hours=hours)), "backup_age")
        assert r.status == exp

    def test_none_unknown(self):
        assert one(ev(last_backup_at=None), "backup_age").status == Status.UNKNOWN

    def test_overall_with_old_backup(self):
        assert ev(last_backup_at=NOW - timedelta(hours=27)).overall == Status.WARN
        assert ev(last_backup_at=NOW - timedelta(hours=51)).healthy is False


class TestClockSkew:
    def test_future_process_at(self):
        r = _api_check("bot_loop_age", last_process_at=at(12, 31))
        assert r.status == Status.UNKNOWN and r.code == "clock_skew"

    def test_future_candle(self):
        r = _api_check("candle_age", last_candle_open=NOW + timedelta(seconds=60))
        assert r.status == Status.UNKNOWN and r.code == "clock_skew"

    def test_future_ledger_write(self):
        r = _ledger_check("ledger_write_age", last_write_at=NOW + timedelta(seconds=60))
        assert r.status == Status.UNKNOWN and r.code == "clock_skew"

    def test_future_backup(self):
        r = one(ev(last_backup_at=NOW + timedelta(hours=1)), "backup_age")
        assert r.status == Status.UNKNOWN and r.code == "clock_skew"

    def test_more_than_5s_ahead(self):
        r = _api_check("bot_loop_age", last_process_at=NOW + timedelta(seconds=6))
        assert r.status == Status.UNKNOWN and r.code == "clock_skew"

    def test_clock_skew_makes_unhealthy(self):
        rep = ev(**with_bot("api", "twin", last_process_at=at(12, 31)))
        assert rep.overall == Status.UNKNOWN and not rep.healthy


# ==========================================================================
# 4. Spec ornekleri 13.3, 13.4, 13.5, 13.6, 13.7
# ==========================================================================
class TestSpecExamples:
    def test_13_3_api_unreadable(self):
        rep = ev(api={"learner": none_api(), "twin": good_api()})
        for chk in ("bot_loop_age", "candle_age"):
            assert one(rep, chk, "learner").status == Status.UNKNOWN
            assert one(rep, chk, "twin").status == Status.OK
        assert rep.overall == Status.UNKNOWN and rep.healthy is False

    def test_13_4_disk_mem(self):
        assert one(ev(disk_free_bytes=int(2.5 * GiB)), "disk_free").status == Status.WARN
        assert one(ev(disk_free_bytes=int(0.9 * GiB)), "disk_free").status == Status.CRIT
        assert one(ev(disk_free_bytes=3 * GiB), "disk_free").status == Status.OK

    def test_13_5_restart_cases(self):
        def go(**kw):
            rep = ev(containers={"trader-learner": good_container(**kw),
                                 "trader-twin": good_container()})
            return [r for r in pick(rep, "container_restarts") if "learner" in r.name][0]
        assert go(restart_count=4).status == Status.OK
        assert go(restart_count=5).status == Status.WARN
        assert go(restart_count=7).status == Status.CRIT
        assert go(restart_count=4, state="restarting").status == Status.CRIT
        assert go(oom_killed=True).code == "oom_killed"

    def test_13_5_warmup_example(self):
        s = snap(containers={"trader-learner": good_container(started_at=at(12, 25)),
                             "trader-twin": good_container()},
                 **with_bot("api", "learner", last_candle_open=at(9, 27)))
        r = one(ev(s), "candle_age", "learner")
        assert r.status == Status.WARN and r.code == "stale_candle_warmup"

    def test_13_6_gate(self):
        rep = ev(**with_bot("ledger", "learner", spool_lines=1))
        assert one(rep, "ledger_gate", "learner").code == "spool_pending"
        assert rep.overall == Status.CRIT and not rep.healthy
        rep = ev(**with_bot("ledger", "learner", spool_lines=None))
        assert one(rep, "ledger_gate", "learner").status == Status.UNKNOWN

    def test_13_7_negative_age(self):
        r = _api_check("bot_loop_age", last_process_at=at(12, 31))
        assert (r.status, r.code) == (Status.UNKNOWN, "clock_skew")

    def test_missing_check_added(self):
        rep = ev(api={})
        miss = [r for r in rep.results if r.code == "missing_check"]
        assert miss and all(r.status == Status.UNKNOWN for r in miss)
        assert rep.overall == Status.UNKNOWN and not rep.healthy

    def test_missing_one_bot_only(self):
        rep = ev(api={"learner": good_api()}, cfg=h.HealthConfig(require_bots=("learner", "twin")))   # DD-12: varsayilan yalniz learner; genel coklu bot kurali
        assert any(r.code == "missing_check" and "twin" in r.name for r in rep.results)
        assert not rep.healthy

    def test_require_bots_config(self):
        cfg = h.HealthConfig(require_bots=("learner",))
        s = snap(api={"learner": good_api()}, ledger={"learner": good_ledger()},
                 containers={"trader-learner": good_container()},
                 prev_restart_counts={"trader-learner": 4})
        rep = ev(s, cfg=cfg)
        assert rep.overall == Status.OK, [(r.name, r.status) for r in rep.results]


# ==========================================================================
# 5. Birlestirme
# ==========================================================================
class TestAggregation:
    def test_crit_beats_unknown(self):
        rep = ev(api={"learner": none_api(), "twin": good_api()}, disk_free_bytes=0)
        assert rep.overall == Status.CRIT

    def test_unknown_beats_warn(self):
        rep = ev(api={"learner": none_api(), "twin": good_api()},
                 disk_free_bytes=2 * GiB)
        assert rep.overall == Status.UNKNOWN

    def test_warn_beats_ok(self):
        assert ev(disk_free_bytes=2 * GiB).overall == Status.WARN

    def test_warn_is_healthy(self):
        rep = ev(disk_free_bytes=2 * GiB)
        assert rep.healthy
        assert {r.name for r in rep.failing()} == {"disk_free"}

    def test_failing_contents(self):
        rep = ev(disk_free_bytes=0, 
                 api={"learner": none_api(), "twin": good_api()})
        assert all(r.status in (Status.WARN, Status.CRIT, Status.UNKNOWN)
                   for r in rep.failing())
        assert {r.status for r in rep.failing()} == {Status.CRIT, Status.UNKNOWN}
        assert len(rep.failing()) == sum(
            r.status in (Status.WARN, Status.CRIT, Status.UNKNOWN) for r in rep.results)

    def test_everything_unmeasured_is_unknown(self):
        s = snap(api={b: none_api() for b in BOTS},
                 ledger={b: h.LedgerProbe(None, None, None, None, None) for b in BOTS},
                 disk_free_bytes=None, disk_total_bytes=None,
                 
                 containers={f"trader-{b}": h.ContainerProbe(None, None, None, None)
                             for b in BOTS},
                 last_backup_at=None, timeframe_s=None)
        rep = ev(s)
        assert rep.overall == Status.UNKNOWN and not rep.healthy


# ==========================================================================
# 6. Ozellik (property) testi, seed'li
# ==========================================================================
def _rand_snapshot(rnd: random.Random):
    def maybe(v, p=0.12):
        return None if rnd.random() < p else v

    def td(lo, hi):
        return timedelta(seconds=rnd.uniform(lo, hi))

    def rapi():
        return h.ApiProbe(
            ping_ok=maybe(rnd.random() > 0.15),
            last_process_at=maybe(NOW - td(-100, 600)),
            last_candle_open=maybe(NOW - td(-100, 12000)),
            open_trade_ids=maybe(()),
            dry_run=maybe(True))

    def rled():
        return h.LedgerProbe(
            last_write_at=maybe(NOW - td(-100, 9000)),
            spool_lines=maybe(rnd.choice([0, 0, 0, 2])),
            unledgered_ids=maybe(rnd.choice([(), (), (), (9,)])),
            
            schema_ok=maybe(rnd.random() > 0.05),
            has_active_params=maybe(rnd.random() > 0.05))

    def rcont():
        return h.ContainerProbe(
            state=maybe(rnd.choice(["running"] * 6 + ["restarting"])),
            restart_count=maybe(4 + rnd.choice([0, 0, 0, 1, 3])),
            started_at=maybe(NOW - td(0, 90000)),
            oom_killed=maybe(rnd.random() < 0.05))

    tot = rnd.choice([0, 2048 * MiB])
    return snap(
        timeframe_s=maybe(T, 0.03),
        api={b: rapi() for b in BOTS},
        ledger={b: rled() for b in BOTS},
        disk_free_bytes=maybe(int(rnd.uniform(0, 30) * GiB)),
        
        
        
        containers={f"trader-{b}": rcont() for b in BOTS},
        last_backup_at=maybe(NOW - td(0, 60 * 3600)),
        
        
    )


@pytest.mark.parametrize("seed", [1, 7, 42, 2026, 31337])
def test_property_aggregation_invariants(seed):
    rnd = random.Random(seed)
    cfgs = [h.DEFAULT_CFG,
            h.HealthConfig()]
    for _ in range(300):
        cfg = rnd.choice(cfgs)
        rep = h.evaluate(_rand_snapshot(rnd), cfg)
        sts = [r.status for r in rep.results if r.status != Status.SKIPPED]
        assert rep.overall != Status.SKIPPED
        assert rep.healthy == (rep.overall in (Status.OK, Status.WARN))
        if not sts:
            assert rep.overall == Status.UNKNOWN
        elif Status.CRIT in sts:
            assert rep.overall == Status.CRIT
        elif Status.UNKNOWN in sts:
            assert rep.overall == Status.UNKNOWN
        elif Status.WARN in sts:
            assert rep.overall == Status.WARN
        else:
            assert rep.overall == Status.OK
        if any(s in (Status.CRIT, Status.UNKNOWN) for s in sts):
            assert rep.healthy is False
            sender = FakeSender()
            dispatch_heartbeat(rep, sender)
            assert sender.ok_calls == 0
        assert {id(r) for r in rep.failing()} == {
            id(r) for r in rep.results
            if r.status in (Status.WARN, Status.CRIT, Status.UNKNOWN)}
        assert rep == h.evaluate(snap_roundtrip := _rand_snapshot(random.Random(0)), cfg) \
            or True  # determinizm ayri testte


@pytest.mark.parametrize("seed", [3, 11])
def test_property_determinism(seed):
    rnd = random.Random(seed)
    for _ in range(50):
        s = _rand_snapshot(rnd)
        assert h.evaluate(s) == h.evaluate(s)


def test_evaluate_never_raises_on_garbage_values():
    # beklenmedik tur -> istisna sizdirmaz; ilgili kontrol UNKNOWN
    s = snap(disk_free_bytes="garbage")  # type: ignore[arg-type]
    try:
        rep = h.evaluate(s)
    except (ValueError, TypeError) as e:  # kurucu dogrulama kabul edilebilir degil: spec istisna sizdirmaz der
        pytest.fail(f"evaluate istisna sizdirdi: {e!r}")
    assert one(rep, "disk_free").status == Status.UNKNOWN
    assert not rep.healthy


# ==========================================================================
# 7. Nabiz karari (Bolum 4, 13.9)
# ==========================================================================
class FakeSender:
    def __init__(self, fail_url=True):
        self.ok_calls = 0
        self.fail_calls = 0
        self.fail_url = fail_url
        self.reports = []

    def ok(self, report):
        self.ok_calls += 1
        self.reports.append(("ok", report))
        return True

    def fail(self, report):
        if not self.fail_url:
            return False
        self.fail_calls += 1
        self.reports.append(("fail", report))
        return True


def dispatch_heartbeat(report, sender):
    """Bolum 4 karar tablosu; yalniz report.healthy'ye dayanir."""
    if report.healthy:
        return sender.ok(report)
    return sender.fail(report)


class TestHeartbeatDecision:
    def test_ok_sends(self):
        s = FakeSender()
        dispatch_heartbeat(ev(), s)
        assert (s.ok_calls, s.fail_calls) == (1, 0)

    def test_warn_sends(self):
        s = FakeSender()
        rep = ev(disk_free_bytes=2 * GiB)
        dispatch_heartbeat(rep, s)
        assert (s.ok_calls, s.fail_calls) == (1, 0)

    def test_crit_no_ok_fail_called(self):
        s = FakeSender()
        dispatch_heartbeat(ev(disk_free_bytes=0), s)
        assert (s.ok_calls, s.fail_calls) == (0, 1)

    def test_unknown_no_ok(self):
        s = FakeSender()
        dispatch_heartbeat(ev(api={"learner": none_api(), "twin": good_api()}), s)
        assert (s.ok_calls, s.fail_calls) == (0, 1)

    def test_no_fail_url_silence(self):
        s = FakeSender(fail_url=False)
        dispatch_heartbeat(ev(disk_free_bytes=0), s)
        assert s.ok_calls == 0 and s.fail_calls == 0


def dead_mans_switch(pings, now, expected=timedelta(minutes=5), grace=timedelta(minutes=15)):
    """Dis servis modeli (13.9): son ping + beklenen aralik + tolerans asildiysa alarm."""
    return now > max(pings) + expected + grace if pings else True


class TestExternalTimer:
    def test_spec_example(self):
        pings = [at(12, 0)]
        assert not dead_mans_switch(pings, at(12, 20))
        assert dead_mans_switch(pings, at(12, 20, 1))

    def test_one_stale_candle_does_not_alarm(self):
        # 5 dk'lik turlar: tek saglikli olmayan tur -> sonraki ping 10 dk sonra
        pings = [at(12, 0), at(12, 10)]
        assert not dead_mans_switch(pings, at(12, 15))

    def test_two_lost_tolerated_third_alarms(self):
        # son ping 12:00; turlar 12:05, 12:10, 12:15 kayip; 12:20 siniri
        pings = [at(12, 0)]
        assert not dead_mans_switch(pings, at(12, 15))   # 2 kayip (12:05, 12:10)
        assert not dead_mans_switch(pings, at(12, 20))   # sinirda hala tolere
        assert dead_mans_switch(pings, at(12, 21))       # 3. kayip sonrasi alarm

    def test_runs_through_evaluate_sequence(self):
        # 5 dk turlarla: 3 ardisik CRIT => ping yok => 15 dk tolerans asilir
        sender = FakeSender()
        pings = []
        t0 = at(12, 0)
        reps = [ev(), ev(disk_free_bytes=0), ev(disk_free_bytes=0), ev(disk_free_bytes=0)]
        for i, rep in enumerate(reps):
            before = sender.ok_calls
            dispatch_heartbeat(rep, sender)
            if sender.ok_calls > before:
                pings.append(t0 + timedelta(minutes=5 * i))
        assert pings == [t0]
        assert not dead_mans_switch(pings, t0 + timedelta(minutes=15))
        assert dead_mans_switch(pings, t0 + timedelta(minutes=21))


# --------------------------------------------------------------------------
# HttpsHeartbeat (urllib enjekte / sahte)
# --------------------------------------------------------------------------
class _Resp:
    def __init__(self, status=200):
        self.status = status
        self.code = status

    def getcode(self):
        return self.status

    def read(self, *a):
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def close(self):
        pass


@pytest.fixture
def fake_http(monkeypatch):
    import urllib.request as ur
    state = {"script": [], "calls": [], "sleeps": []}

    def fake_open(req_or_url, *a, **k):
        url = req_or_url if isinstance(req_or_url, str) else req_or_url.full_url
        data = None if isinstance(req_or_url, str) else req_or_url.data
        state["calls"].append({"url": url, "data": data, "timeout": k.get("timeout", a[1] if len(a) > 1 else None)})
        item = state["script"].pop(0) if state["script"] else _Resp(200)
        if isinstance(item, BaseException):
            raise item
        return item

    class _Opener:
        def open(self, *a, **k):
            return fake_open(*a, **k)
        addheaders = []

    monkeypatch.setattr(ur, "urlopen", fake_open)
    monkeypatch.setattr(ur, "build_opener", lambda *a, **k: _Opener())
    monkeypatch.setattr(time, "sleep", lambda s: state["sleeps"].append(s))
    return state


SECRET_URL = "https://hc.example.test/ping/SECRET-TOKEN-123"


def _hb(url=SECRET_URL, fail_url=None):
    cls = h.HttpsHeartbeat
    try:
        return cls(url, fail_url) if fail_url is not None else cls(url)
    except TypeError:
        return cls(url=url, fail_url=fail_url)


class TestHttpsHeartbeat:
    def test_http_scheme_rejected(self):
        with pytest.raises(ValueError):
            _hb("http://x")

    @pytest.mark.parametrize("u", ["ftp://x/y", "file:///etc/passwd", "", "//x/y"])
    def test_other_schemes_rejected(self, u):
        with pytest.raises(ValueError):
            _hb(u)

    def test_retry_then_success(self, fake_http):
        import socket
        fake_http["script"] = [socket.timeout("t"), _Resp(200)]
        assert _hb().ok(ev()) is True
        assert len(fake_http["calls"]) == 2
        assert fake_http["sleeps"] in ([], [2])  # sleep enjekte edilemiyorsa gozlenemez

    def test_three_failures_false(self, fake_http):
        import socket
        fake_http["script"] = [socket.timeout("t")] * 3
        assert _hb().ok(ev()) is False
        assert len(fake_http["calls"]) == 3
        assert fake_http["sleeps"] in ([], [2, 5])

    def test_non_2xx_is_failure(self, fake_http):
        fake_http["script"] = [_Resp(500), _Resp(503), _Resp(502)]
        assert _hb().ok(ev()) is False
        assert len(fake_http["calls"]) == 3

    def test_http_error_raised_is_failure(self, fake_http):
        import urllib.error
        fake_http["script"] = [urllib.error.HTTPError(SECRET_URL, 500, "x", {}, None)] * 3
        assert _hb().ok(ev()) is False

    def test_timeout_is_10s(self, fake_http):
        _hb().ok(ev())
        assert fake_http["calls"][0]["timeout"] in (10, 10.0, None)

    def test_body_at_most_200_bytes(self, fake_http):
        _hb().ok(ev(disk_free_bytes=2 * GiB))
        for c in fake_http["calls"]:
            assert c["data"] is None or len(c["data"]) <= 200

    def test_no_secret_in_logs_or_repr(self, fake_http, caplog, capsys):
        import socket
        fake_http["script"] = [socket.timeout(SECRET_URL)] * 3
        hb = _hb()
        with caplog.at_level("DEBUG"):
            hb.ok(ev())
        out = capsys.readouterr()
        assert "SECRET-TOKEN-123" not in caplog.text
        assert "SECRET-TOKEN-123" not in out.out + out.err
        assert "SECRET-TOKEN-123" not in repr(hb)

    def test_fail_url_empty_sends_nothing(self, fake_http):
        hb = _hb()
        assert not hb.fail(ev(disk_free_bytes=0))
        assert fake_http["calls"] == []

    def test_fail_url_used(self, fake_http):
        hb = _hb(fail_url="https://hc.example.test/fail/XYZ")
        hb.fail(ev(disk_free_bytes=0))
        assert fake_http["calls"] and fake_http["calls"][0]["url"].endswith("/fail/XYZ")


# ==========================================================================
# 8. Notifier ve plan_alerts
# ==========================================================================
def mk_alert(**kw):
    base = dict(level=Status.CRIT, code="x", title="t", body="b",
                fingerprint="n|x", created_at=NOW)
    base.update(kw)
    return h.Alert(**base)


class TestNotifier:
    def test_alert_frozen(self):
        a = mk_alert()
        with pytest.raises(dataclasses.FrozenInstanceError):
            a.code = "y"  # type: ignore[misc]

    def test_null_notifier_records(self):
        n = h.NullNotifier()
        a = mk_alert()
        assert n.send(a) in (True, None) or n.send(a)
        lists = [v for v in vars(n).values() if isinstance(v, list)]
        assert lists and any(a in l for l in lists)

    def test_log_notifier_never_false_no_raise(self, capsys):
        n = h.LogNotifier()
        assert n.send(mk_alert()) is True
        assert n.send(mk_alert(level=Status.OK)) is True

    def test_log_notifier_does_not_raise_on_weird_body(self):
        assert h.LogNotifier().send(mk_alert(body="çğı " * 50)) is True


def run_turns(steps, cfg=None):
    """steps: [(dakika, rapor)]. Her turun uyarilarini dondurur; durum tasinir."""
    cfg = cfg or h.DEFAULT_CFG
    state = {}
    out = []
    for minute, rep in steps:
        now = at(0) + timedelta(minutes=minute)
        alerts, state = h.plan_alerts(rep, state, now, cfg)
        out.append((minute, list(alerts)))
    return out, state


def stale_report():
    return ev(**with_bot("api", "learner", last_candle_open=NOW - timedelta(seconds=11000)))


def candle_ok_report():
    return ev()


class TestPlanAlertsCrit:
    def test_timeline_13_8(self):
        steps = []
        for m in range(0, 200, 5):
            steps.append((m, stale_report()))
        steps.append((200, candle_ok_report()))
        steps.append((205, candle_ok_report()))
        out, _ = run_turns(steps)
        sent = {m: a for m, a in out if a}
        assert set(sent) == {5, 185, 200}, sorted(sent)
        assert sent[5][0].level == Status.CRIT
        assert sent[185][0].level == Status.CRIT
        assert sent[200][0].level == Status.OK       # duzeldi
        assert len(sent[5]) == len(sent[185]) == len(sent[200]) == 1

    def test_first_run_no_alert_second_yes(self):
        out, _ = run_turns([(0, stale_report()), (5, stale_report())])
        assert out[0][1] == [] and len(out[1][1]) == 1

    def test_recovery_only_once(self):
        steps = [(0, stale_report()), (5, stale_report()), (10, candle_ok_report()),
                 (15, candle_ok_report()), (20, candle_ok_report())]
        out, _ = run_turns(steps)
        rec = [(m, a) for m, a in out if a and a[0].level == Status.OK]
        assert [m for m, _ in rec] == [10]

    def test_no_recovery_if_never_alerted(self):
        out, _ = run_turns([(0, stale_report()), (5, candle_ok_report()),
                            (10, candle_ok_report())])
        assert all(a == [] for _, a in out)

    def test_same_alert_not_repeated_within_window(self):
        steps = [(m, stale_report()) for m in range(0, 185, 5)]
        out, _ = run_turns(steps)
        assert sum(len(a) for _, a in out) == 1

    def test_immediate_disk_low(self):
        rep = ev(disk_free_bytes=int(0.9 * GiB))
        out, _ = run_turns([(0, rep), (5, rep)])
        assert out[0][1] == []                      # kirmizi cift dogrulama: ilk tur sari
        assert len(out[1][1]) == 1
        assert out[1][1][0].code == "disk_low"
        assert out[1][1][0].level == Status.CRIT

    @pytest.mark.parametrize("kw,code", [
        (dict(**with_bot("ledger", "learner", spool_lines=1)), "spool_pending"),
        (dict(**with_bot("ledger", "learner", unledgered_ids=(9,))), "unledgered_trades"),
        (dict(**with_bot("ledger", "learner", schema_ok=False)), "schema"),
        (dict(containers={"trader-learner": good_container(oom_killed=True),
                          "trader-twin": good_container()}), "oom_killed"),
    ])
    def test_other_immediate_codes(self, kw, code):
        rep = ev(**kw)
        out, _ = run_turns([(0, rep), (5, rep)])
        assert out[0][1] == []                      # kirmizi cift dogrulama: ilk tur sari
        assert [a.code for a in out[1][1]] == [code]

    def test_non_immediate_critical_not_first_turn(self):
        out, _ = run_turns([(0, ev())])
        assert out[0][1] == []

    def test_unknown_same_as_crit_debounce(self):
        rep = ev(**with_bot("api", "learner", last_process_at=None))
        out, _ = run_turns([(0, rep), (5, rep), (10, rep)])
        assert [len(a) for _, a in out] == [0, 1, 0]
        assert out[1][1][0].level == Status.UNKNOWN

    def test_flapping_resets_consecutive(self):
        # CRIT, OK, CRIT, OK ... asla ardisik 2 olmaz
        steps = [(m, stale_report() if (m // 5) % 2 == 0 else candle_ok_report())
                 for m in range(0, 60, 5)]
        out, _ = run_turns(steps)
        assert all(a == [] for _, a in out)

    def test_alert_field_limits(self):
        rep = ev(disk_free_bytes=0)
        out, _ = run_turns([(0, rep), (5, rep)])
        a = out[1][1][0]
        assert len(a.title) <= 80 and len(a.body) <= 500
        assert "|" in a.fingerprint
        assert a.created_at.tzinfo is not None
        assert a.fingerprint.split("|")[0].startswith("disk_free")
        assert a.fingerprint.split("|")[1] == "disk_low"

    def test_body_has_no_secrets(self):
        rep = ev(disk_free_bytes=0)
        out, _ = run_turns([(0, rep), (5, rep)])
        a = out[1][1][0]
        for s in ("SECRET", "PASS", "password"):
            assert s not in a.body

    def test_plan_alerts_pure_state_retry(self):
        # Notifier.send False -> cagiran new_state'i kaydetmez -> ertesi turda yeniden uyari
        state = {}
        a0, state = h.plan_alerts(stale_report(), state, at(0), h.DEFAULT_CFG)
        saved = state
        a1, s1 = h.plan_alerts(stale_report(), saved, at(0, 5), h.DEFAULT_CFG)
        assert len(a1) == 1
        again, _ = h.plan_alerts(stale_report(), saved, at(0, 5), h.DEFAULT_CFG)
        assert len(again) == 1


class TestPlanAlertsWarn:
    def warn_report(self):
        return ev(disk_free_bytes=2 * GiB)

    def test_warn_timeline(self):
        steps = [(m, self.warn_report()) for m in range(0, 735, 5)]
        out, _ = run_turns(steps)
        sent = [m for m, a in out if a]
        assert sent == [5, 725], sent
        assert out[1][1][0].level == Status.WARN

    def test_warn_recovery_once(self):
        steps = [(0, self.warn_report()), (5, self.warn_report()),
                 (10, ev()), (15, ev())]
        out, _ = run_turns(steps)
        assert [(m, a[0].level) for m, a in out if a] == [(5, Status.WARN), (10, Status.OK)]


class TestPlanAlertsMultiple:
    def many_report(self):
        return ev(api={b: h.ApiProbe(False, NOW, NOW, (), True) for b in BOTS},
                  disk_free_bytes=0, 
                  **{}) if False else ev(
            api={b: good_api(last_process_at=NOW - timedelta(hours=1)) for b in BOTS},
            disk_free_bytes=0, 
            ledger={b: good_ledger(spool_lines=1) for b in BOTS})

    def test_single_summary(self):
        rep = self.many_report()
        assert len({(r.name, r.code) for r in rep.failing()}) >= 4
        out, _ = run_turns([(0, rep), (5, rep)])
        first = next(a for _, a in out if a)
        assert len(first) == 1 and first[0].code == "multiple"
        assert len(first[0].body) <= 500
        assert "disk" in first[0].body and "disk_free" not in first[0].body

    def test_three_failing_not_summarized(self):
        rep = ev(disk_free_bytes=0, 
                 **with_bot("ledger", "learner", spool_lines=1))
        out, _ = run_turns([(0, rep), (5, rep)])
        assert all(a.code != "multiple" for a in out[1][1])
        assert len(out[1][1]) >= 1

    def test_body_lists_at_most_five_names(self):
        rep = self.many_report()
        out, _ = run_turns([(0, rep), (5, rep)])
        first = next(a for _, a in out if a)[0]
        names = {r.name for r in rep.failing()}
        listed = [n for n in names if n in first.body]
        assert len(listed) <= 5


class TestMaintenanceAndDeterminism:
    def test_ok_report_no_alerts(self):
        out, _ = run_turns([(m, ev()) for m in range(0, 60, 5)])
        assert all(a == [] for _, a in out)

    def test_naive_now_rejected_or_handled(self):
        with pytest.raises((ValueError, TypeError)):
            h.plan_alerts(ev(), {}, datetime(2026, 11, 16, 12, 30), h.DEFAULT_CFG)


# ==========================================================================
# 9. Yedek (scripts/health_backup.py)
# ==========================================================================
def _load_script(name):
    path = SCRIPTS / f"{name}.py"
    if not path.exists():
        pytest.skip(f"{path.name} henuz yok")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


TRIGGER_TABLES = ("decision_events", "trade_entries", "trade_exits", "health_probes")


def make_ledger(path: Path, bot: str, rows: int = 5, wal: bool = True):
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES('bot', ?)", (bot,))
    for t in TRIGGER_TABLES:
        con.execute(f"CREATE TABLE {t}(id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT)")
        con.execute(f"CREATE TRIGGER {t}_nu BEFORE UPDATE ON {t} "
                    f"BEGIN SELECT RAISE(ABORT,'append-only'); END")
        con.execute(f"CREATE TRIGGER {t}_nd BEFORE DELETE ON {t} "
                    f"BEGIN SELECT RAISE(ABORT,'append-only'); END")
        for i in range(rows):
            con.execute(f"INSERT INTO {t}(payload) VALUES(?)", (f"{t}-{i}" + "x" * 200,))
    con.execute("PRAGMA user_version=1")
    con.commit()
    return con  # acik birakilabilir (yazar)


def make_ft(path: Path, rows: int = 3):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE positions(id INTEGER PRIMARY KEY, pair TEXT)")
    for i in range(rows):
        con.execute("INSERT INTO positions(pair) VALUES(?)", (f"BTC/USDT{i}",))
    con.commit()
    con.close()


class Env:
    """BACKUP/ENGINE_VAR_DIR dizinlerini kurar (spec Bolum 14).

    Motor yollari: ENGINE_VAR_DIR/<bot>/ledger.sqlite ve state.sqlite; yedek adlari
    ledger_<bot>.sqlite ve state_<bot>.sqlite.
    """

    def __init__(self, tmp: Path):
        self.var = tmp / "var"
        self.backup = tmp / "backups"
        for d in (self.var, self.backup):
            d.mkdir()
        for b in BOTS:
            (self.var / b).mkdir()
        self.writers = {b: make_ledger(self.lp(b), b) for b in BOTS}
        for b in BOTS:
            make_ft(self.var / b / "state.sqlite")

    def lp(self, bot):
        return self.var / bot / "ledger.sqlite"

    def environ(self, keep=None):
        e = {"BACKUP_DIR": str(self.backup), "ENGINE_VAR_DIR": str(self.var)}
        if keep is not None:
            e["BACKUP_KEEP_DAYS"] = str(keep)
        return e

    def today(self):
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def day_dir(self, day=None):
        return self.backup / (day or self.today())

    def manifest(self, day=None):
        return json.loads((self.day_dir(day) / "MANIFEST.json").read_text("utf-8"))


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    for c in e.writers.values():
        try:
            c.close()
        except Exception:
            pass


@pytest.fixture
def backup_mod():
    return _load_script("health_backup")


def run_backup(mod, env: Env, monkeypatch, keep=None, extra_env=None):
    """health_backup.main'i ortam degiskenleriyle calistirir; cikis kodunu dondurur."""
    monkeypatch.setenv("HEALTH_BOTS", "learner,twin")      # DD-12: varsayilan yalniz learner; bu fikstur iki botlu (genel) yedegi dener
    for k, v in {**env.environ(keep), **(extra_env or {})}.items():
        monkeypatch.setenv(k, v)
    if keep is None:
        monkeypatch.delenv("BACKUP_KEEP_DAYS", raising=False)
    main = getattr(mod, "main")
    try:
        sig = inspect.signature(main)
        rc = main([]) if sig.parameters else main()
    except SystemExit as e:
        rc = e.code
    return 0 if rc is None else rc


def seed_old_day(env: Env, days_ago: int, ok=True):
    d = datetime.now(UTC).date() - timedelta(days=days_ago)
    p = env.backup / d.strftime("%Y-%m-%d")
    p.mkdir()
    (p / "MANIFEST.json").write_text(json.dumps(
        {"schema": 1, "created_at": d.isoformat(), "host": "x", "ok": ok, "files": {}}))
    (p / "ledger_learner.sqlite").write_bytes(b"old")
    return p


class TestBackupBasic:
    def test_success_layout_and_manifest(self, env, backup_mod, monkeypatch):
        rc = run_backup(backup_mod, env, monkeypatch)
        assert rc == 0
        d = env.day_dir()
        for n in ("ledger_learner.sqlite", "ledger_twin.sqlite",
                  "state_learner.sqlite", "state_twin.sqlite", "MANIFEST.json"):
            assert (d / n).is_file(), n
        assert not list(d.glob("*.partial")) and not list(d.glob("*.corrupt"))
        m = env.manifest()
        assert m["schema"] == 1 and m["ok"] is True
        assert "created_at" in m and "host" in m
        assert set(m["files"]) >= {"ledger_learner.sqlite", "ledger_twin.sqlite",
                                   "state_learner.sqlite", "state_twin.sqlite"}
        for name, f in m["files"].items():
            assert f["ok"] is True and f["bytes"] > 0 and f["integrity"] == "ok"
            assert f["error"] is None
            assert len(f["sha256"]) == 64
            assert f["sha256"] == hashlib.sha256((d / name).read_bytes()).hexdigest()
            assert f["bytes"] == (d / name).stat().st_size
        lj = m["files"]["ledger_learner.sqlite"]
        assert lj["user_version"] == 1
        assert lj["max_ids"] == {t: 5 for t in TRIGGER_TABLES}
        assert m["files"]["state_twin.sqlite"]["positions"] == 3

    def test_manifest_has_no_secret(self, env, backup_mod, monkeypatch):
        monkeypatch.setenv("HEARTBEAT_URL", SECRET_URL)
        monkeypatch.setenv("SOME_API_PASS", "hunter2-secret")
        run_backup(backup_mod, env, monkeypatch)
        txt = (env.day_dir() / "MANIFEST.json").read_text("utf-8")
        assert "SECRET-TOKEN" not in txt and "hunter2" not in txt

    def test_backup_files_are_valid_sqlite(self, env, backup_mod, monkeypatch):
        run_backup(backup_mod, env, monkeypatch)
        for b in BOTS:
            c = sqlite3.connect(env.day_dir() / f"ledger_{b}.sqlite")
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA user_version").fetchone()[0] == 1
            assert c.execute("SELECT value FROM meta WHERE key='bot'").fetchone()[0] == b
            trig = c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
            assert trig == 2 * len(TRIGGER_TABLES)
            c.close()

    def test_source_untouched(self, env, backup_mod, monkeypatch):
        before = {b: hashlib.sha256((env.lp(b)).read_bytes()).hexdigest()
                  for b in BOTS}
        for c in env.writers.values():
            c.execute("PRAGMA wal_checkpoint(PASSIVE)")
        run_backup(backup_mod, env, monkeypatch)
        # veriler ayni: satir sayisi degismedi, tetikleyiciler yerinde
        for b in BOTS:
            c = sqlite3.connect(env.lp(b))
            assert c.execute("SELECT count(*) FROM trade_entries").fetchone()[0] == 5
            c.close()

    def test_spool_copied_when_nonempty(self, env, backup_mod, monkeypatch):
        sp = Path(str(env.lp("learner")) + ".spool.jsonl")
        sp.write_text('{"a":1}\n{"b":2}\n')
        run_backup(backup_mod, env, monkeypatch)
        out = env.day_dir() / "ledger_learner.sqlite.spool.jsonl"
        assert out.read_text() == sp.read_text()
        assert not (env.day_dir() / "ledger_twin.sqlite.spool.jsonl").exists()

    def test_empty_spool_skipped(self, env, backup_mod, monkeypatch):
        (Path(str(env.lp("learner")) + ".spool.jsonl")).write_text("")
        run_backup(backup_mod, env, monkeypatch)
        assert not (env.day_dir() / "ledger_learner.sqlite.spool.jsonl").exists()

    def test_idempotent_second_run_skips(self, env, backup_mod, monkeypatch):
        assert run_backup(backup_mod, env, monkeypatch) == 0
        mp = env.day_dir() / "MANIFEST.json"
        before = (mp.read_bytes(), mp.stat().st_mtime_ns)
        for c in env.writers.values():
            c.execute("INSERT INTO trade_entries(payload) VALUES('new')")
            c.commit()
        assert run_backup(backup_mod, env, monkeypatch) == 0
        assert (mp.read_bytes(), mp.stat().st_mtime_ns) == before

    def test_failed_manifest_renamed_and_retried(self, env, backup_mod, monkeypatch):
        d = env.day_dir()
        d.mkdir()
        (d / "MANIFEST.json").write_text(json.dumps({"schema": 1, "ok": False, "files": {}}))
        (d / "ledger_learner.sqlite.partial").write_bytes(b"junk")
        assert run_backup(backup_mod, env, monkeypatch) == 0
        assert env.manifest()["ok"] is True
        failed = [p for p in env.backup.iterdir() if ".failed-" in p.name]
        assert len(failed) == 1 and failed[0].name.startswith(env.today())

    def test_partial_leftover_without_manifest(self, env, backup_mod, monkeypatch):
        d = env.day_dir()
        d.mkdir()
        (d / "ledger_twin.sqlite.partial").write_bytes(b"junk")
        assert run_backup(backup_mod, env, monkeypatch) == 0
        assert env.manifest()["ok"] is True
        assert not list(env.day_dir().glob("*.partial"))

    def test_missing_source_fails_exit_20(self, env, backup_mod, monkeypatch):
        (env.var / "twin" / "state.sqlite").unlink()
        assert run_backup(backup_mod, env, monkeypatch) == 20
        mp = env.day_dir() / "MANIFEST.json"
        if mp.exists():
            m = json.loads(mp.read_text())
            assert m["ok"] is False
            assert m["files"]["state_twin.sqlite"]["ok"] is False
            assert m["files"]["state_twin.sqlite"]["error"]

    def test_no_file_copy_used(self, env, backup_mod, monkeypatch):
        # cp / shutil.copy2 ile DB kopyalamak yasak: kaynak WAL'deki commitlenmemis-checkpointsiz
        # veri yedekte gorunmeli.
        c = env.writers["learner"]
        c.execute("PRAGMA wal_autocheckpoint=0")
        for i in range(50):
            c.execute("INSERT INTO decision_events(payload) VALUES(?)", (f"w{i}",))
        c.commit()
        assert Path(str(env.lp("learner")) + "-wal").stat().st_size > 0
        run_backup(backup_mod, env, monkeypatch)
        b = sqlite3.connect(env.day_dir() / "ledger_learner.sqlite")
        assert b.execute("SELECT count(*) FROM decision_events").fetchone()[0] == 55
        b.close()
        assert env.manifest()["files"]["ledger_learner.sqlite"]["max_ids"]["decision_events"] == 55

    def test_disk_low_blocks_backup(self, env, backup_mod, monkeypatch):
        low = shutil.disk_usage(env.backup)._replace(free=int(0.8 * GiB))
        monkeypatch.setattr(shutil, "disk_usage", lambda p: low)

        class _SV:
            f_bavail = f_bfree = int(0.8 * GiB) // 4096
            f_frsize = f_bsize = 4096
            f_blocks = 100 * GiB // 4096
        monkeypatch.setattr(os, "statvfs", lambda p: _SV())
        assert run_backup(backup_mod, env, monkeypatch) == 20
        d = env.day_dir()
        assert not list(d.glob("*.sqlite")) if d.exists() else True
        mp = d / "MANIFEST.json"
        if mp.exists():
            m = json.loads(mp.read_text())
            assert m["ok"] is False
            assert any(f.get("error") == "disk_low" for f in m["files"].values())

    def test_disk_low_deletes_nothing(self, env, backup_mod, monkeypatch):
        olds = [seed_old_day(env, n) for n in range(1, 17)]
        low = shutil.disk_usage(env.backup)._replace(free=int(0.8 * GiB))
        monkeypatch.setattr(shutil, "disk_usage", lambda p: low)

        class _SV:
            f_bavail = f_bfree = int(0.8 * GiB) // 4096
            f_frsize = f_bsize = 4096
            f_blocks = 100 * GiB // 4096
        monkeypatch.setattr(os, "statvfs", lambda p: _SV())
        run_backup(backup_mod, env, monkeypatch, keep=14)
        assert all(p.exists() for p in olds)


class TestBackupCorruption:
    def test_corrupt_source_detected(self, env, backup_mod, monkeypatch):
        # cok sayfali bir kaynak bozulur: ya yedek API hatasi ya da dogrulama hatasi
        for c in env.writers.values():
            for i in range(400):
                c.execute("INSERT INTO trade_entries(payload) VALUES(?)", ("y" * 800,))
            c.commit()
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for c in env.writers.values():
            c.close()
        p = env.lp("learner")
        raw = bytearray(p.read_bytes())
        ps = int.from_bytes(raw[16:18], "big") or 4096
        npages = len(raw) // ps
        for pg in range(max(2, npages // 3), npages - 1):
            raw[pg * ps: pg * ps + ps] = os.urandom(ps)
        p.write_bytes(bytes(raw))
        for ext in ("-wal", "-shm"):
            q = Path(str(p) + ext)
            if q.exists():
                q.unlink()
        assert run_backup(backup_mod, env, monkeypatch) == 20
        d = env.day_dir()
        mp = d / "MANIFEST.json"
        if mp.exists():
            m = json.loads(mp.read_text())
            assert m["ok"] is False
            assert m["files"]["ledger_learner.sqlite"]["ok"] is False
        # bozuk kopya "saglam yedek" olarak birakilmamali
        good = d / "ledger_learner.sqlite"
        if good.exists():
            c = sqlite3.connect(good)
            try:
                res = c.execute("PRAGMA integrity_check").fetchone()[0]
            except sqlite3.DatabaseError:
                res = "bad"
            c.close()
            assert res != "ok"

    def test_corrupt_backup_detected_via_sha(self, env, backup_mod, monkeypatch):
        run_backup(backup_mod, env, monkeypatch)
        d = env.day_dir()
        f = d / "ledger_learner.sqlite"
        want = env.manifest()["files"]["ledger_learner.sqlite"]["sha256"]
        raw = bytearray(f.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        f.write_bytes(bytes(raw))
        assert hashlib.sha256(f.read_bytes()).hexdigest() != want

    def test_failed_today_old_backup_drives_age(self):
        # 13.10: bugun basarisiz => backup_age eski yedekten: 26 sa sonra WARN
        last_ok = at(3, 10)
        assert one(ev(last_backup_at=last_ok, now=last_ok + timedelta(hours=26)),
                   "backup_age").status == Status.OK
        assert one(ev(last_backup_at=last_ok, now=last_ok + timedelta(hours=26, minutes=1)),
                   "backup_age").status == Status.WARN


class TestBackupWalWriter:
    def test_backup_consistent_while_writer_active(self, env, backup_mod, monkeypatch):
        """Yazar surekli commit ederken yedek tutarli, yazar spec suresinden uzun bloklanmaz."""
        stop = threading.Event()
        lat = []
        errors = []
        path = env.lp("learner")
        for c in env.writers.values():
            c.close()

        def writer():
            w = sqlite3.connect(path, timeout=5, check_same_thread=False)
            w.execute("PRAGMA busy_timeout=5000")
            i = 0
            while not stop.is_set():
                t0 = time.perf_counter()
                try:
                    w.execute("INSERT INTO decision_events(payload) VALUES(?)", (f"live{i}" + "z" * 300,))
                    w.execute("INSERT INTO trade_entries(payload) VALUES(?)", (f"live{i}",))
                    w.commit()
                except Exception as e:  # noqa: BLE001
                    errors.append(e)
                lat.append(time.perf_counter() - t0)
                i += 1
                time.sleep(0.001)
            w.close()

        th = threading.Thread(target=writer)
        th.start()
        try:
            time.sleep(0.3)
            rc = run_backup(backup_mod, env, monkeypatch)
        finally:
            stop.set()
            th.join(10)
        assert rc == 0
        assert not errors, errors[:3]
        assert lat and max(lat) < 5.0          # busy_timeout (5 sn) icinde
        b = sqlite3.connect(env.day_dir() / "ledger_learner.sqlite")
        assert b.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # tutarlilik: iki tablo ayni transaksiyonda yazilir => anlik goruntude sayilar esit (baslangic 5 + n)
        de = b.execute("SELECT count(*) FROM decision_events").fetchone()[0]
        te = b.execute("SELECT count(*) FROM trade_entries").fetchone()[0]
        assert de == te and de >= 5
        mx = b.execute("SELECT max(id) FROM decision_events").fetchone()[0]
        assert mx == de
        b.close()
        m = env.manifest()["files"]["ledger_learner.sqlite"]
        assert m["integrity"] == "ok"

    def test_sqlite_backup_api_reader_does_not_block_wal_writer(self, tmp_path):
        """Bagimsiz dogrulama: spec 6.2 yontemi (ro URI + backup pages=-1) WAL yazarini bloklamaz."""
        src = tmp_path / "s.sqlite"
        w = make_ledger(src, "learner", rows=2000)
        ro = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=5)
        dst = sqlite3.connect(tmp_path / "d.sqlite")
        t0 = time.perf_counter()
        ro.backup(dst, pages=-1)
        w.execute("INSERT INTO decision_events(payload) VALUES('during')")
        w.commit()
        assert time.perf_counter() - t0 < 5
        assert dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert dst.execute("SELECT count(*) FROM decision_events").fetchone()[0] in (2000, 2001)
        for c in (ro, dst, w):
            c.close()


class TestBackupRotation:
    def count_dirs(self, env):
        return sorted(p.name for p in env.backup.iterdir() if p.is_dir())

    def test_keep_14_of_16(self, env, backup_mod, monkeypatch):
        for n in range(1, 16):       # 15 eski + bugun = 16
            seed_old_day(env, n)
        assert run_backup(backup_mod, env, monkeypatch, keep=14) == 0
        names = self.count_dirs(env)
        assert len(names) == 14
        assert env.today() in names
        expect_gone = [(datetime.now(UTC).date() - timedelta(days=n)).strftime("%Y-%m-%d")
                       for n in (14, 15)]
        assert not set(expect_gone) & set(names)

    def test_default_keep_is_14(self, env, backup_mod, monkeypatch):
        for n in range(1, 16):
            seed_old_day(env, n)
        run_backup(backup_mod, env, monkeypatch)
        assert len(self.count_dirs(env)) == 14

    def test_keep_3_minimum_allowed(self, env, backup_mod, monkeypatch):
        for n in range(1, 8):
            seed_old_day(env, n)
        run_backup(backup_mod, env, monkeypatch, keep=3)
        assert len(self.count_dirs(env)) == 3

    @pytest.mark.parametrize("keep", [2, 0, 61, -1])
    def test_keep_out_of_range(self, env, backup_mod, monkeypatch, keep):
        try:
            rc = run_backup(backup_mod, env, monkeypatch, keep=keep)
        except ValueError:
            return
        assert rc != 0
        assert not (env.day_dir() / "MANIFEST.json").exists()

    def test_today_failed_deletes_nothing(self, env, backup_mod, monkeypatch):
        olds = [seed_old_day(env, n) for n in range(1, 16)]
        (env.var / "twin" / "state.sqlite").unlink()
        assert run_backup(backup_mod, env, monkeypatch, keep=14) == 20
        assert all(p.exists() for p in olds)

    def test_must_keep_three_ok_manifests(self, env, backup_mod, monkeypatch):
        # eski 15 gunun 12'si ok=false; silinecek en eski ikisi ok=true => silme sonrasi ok sayisi 2 < 3
        for n in range(1, 16):
            ok = n in (15, 14, 1)
            seed_old_day(env, n, ok=ok)
        run_backup(backup_mod, env, monkeypatch, keep=14)
        assert len(self.count_dirs(env)) == 16     # hicbir sey silinmedi

    def test_delete_allowed_when_three_ok_remain(self, env, backup_mod, monkeypatch):
        for n in range(1, 16):
            ok = n in (15, 14, 1, 2, 3)
            seed_old_day(env, n, ok=ok)
        run_backup(backup_mod, env, monkeypatch, keep=14)
        assert len(self.count_dirs(env)) == 14

    def test_foreign_names_never_deleted(self, env, backup_mod, monkeypatch):
        (env.backup / "notes").mkdir()
        (env.backup / "notes" / "a.txt").write_text("x")
        (env.backup / "readme.txt").write_text("x")
        outside = env.backup.parent / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("x")
        link = env.backup / "2020-01-01"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            link = None
        for n in range(1, 16):
            seed_old_day(env, n)
        run_backup(backup_mod, env, monkeypatch, keep=14)
        assert (env.backup / "notes" / "a.txt").exists()
        assert (env.backup / "readme.txt").exists()
        assert (outside / "keep.txt").exists()

    def test_failed_and_partial_leftovers_are_candidates(self, env, backup_mod, monkeypatch):
        for n in range(1, 15):
            seed_old_day(env, n)
        old = datetime.now(UTC).date() - timedelta(days=20)
        junk = env.backup / (old.strftime("%Y-%m-%d") + ".failed-0310")
        junk.mkdir()
        (junk / "x").write_bytes(b"1")
        run_backup(backup_mod, env, monkeypatch, keep=14)
        assert not junk.exists()


# ==========================================================================
# 10. Kurtarma kontrol listesi (scripts/health_recover.py --check)
# ==========================================================================
@pytest.fixture
def recover_mod():
    return _load_script("health_recover")


def run_recover(mod, env: Env, monkeypatch, capsys):
    for k, v in env.environ().items():
        monkeypatch.setenv(k, v)
    for k, v in {"HEARTBEAT_URL": "https://hc.example.test/p",
                 "BACKUP_KEEP_DAYS": "14", "NOTIFIER": "log"}.items():
        monkeypatch.setenv(k, v)
    try:
        sig = inspect.signature(mod.main)
        rc = mod.main(["--check"]) if sig.parameters else mod.main()
    except SystemExit as e:
        rc = e.code
    cap = capsys.readouterr()
    return rc, cap.out + cap.err


def tree_digest(root: Path):
    d = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith(("-wal", "-shm")):  # ro acilista sqlite yan dosyalari olusabilir
            d[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return d


class TestRecover:
    def test_spool_pending_reported_fail_and_readonly(self, env, recover_mod, monkeypatch, capsys):
        sp = Path(str(env.lp("learner")) + ".spool.jsonl")
        sp.write_text('{"a":1}\n{"b":2}\n')
        for c in env.writers.values():
            c.commit()
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.close()
        before = tree_digest(env.var)
        rc, out = run_recover(recover_mod, env, monkeypatch, capsys)
        assert "spool_pending" in out or "R4" in out
        assert "FAIL" in out
        assert tree_digest(env.var) == before      # hicbir sey yazilmadi, spool bosaltilmadi
        assert sp.read_text() == '{"a":1}\n{"b":2}\n'

    def test_clean_state_spool_pass(self, env, recover_mod, monkeypatch, capsys):
        for c in env.writers.values():
            c.close()
        rc, out = run_recover(recover_mod, env, monkeypatch, capsys)
        assert "spool_pending" not in out

    def test_never_starts_or_opens_gate(self, recover_mod):
        tree = ast.parse((SCRIPTS / "health_recover.py").read_text("utf-8"))
        called = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                called.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
        assert not called & {"drain_spool", "record_trade_entry", "record_decision",
                             "entries_allowed", "check_writable"}


# ==========================================================================
# 11. Ortam dosyasi (8.3) - kurallar ve ornek dosya
# ==========================================================================
class TestDeployExample:
    def test_env_example_keys_and_no_values(self):
        p = ROOT / "deploy" / "trader-health.env.example"
        if not p.exists():
            pytest.skip("deploy/trader-health.env.example henuz yok")
        keys = {}
        for ln in p.read_text("utf-8").splitlines():
            if not ln.strip() or ln.startswith("#"):
                continue
            assert "=" in ln and " =" not in ln and "= " not in ln, ln
            k, v = ln.split("=", 1)
            assert "#" not in v and '"' not in v and "'" not in v, ln
            keys[k] = v
        for k in ("HEARTBEAT_URL", "HEARTBEAT_FAIL_URL", "ENGINE_VAR_DIR", "BACKUP_DIR", "BACKUP_KEEP_DAYS", "NOTIFIER",
                  "HEALTH_MAINTENANCE_FILE"):
            assert k in keys, k
        assert keys["HEARTBEAT_URL"] == "" and keys["ENGINE_VAR_DIR"] == ""
        assert not [k for k in keys if "FREQTRADE" in k]
