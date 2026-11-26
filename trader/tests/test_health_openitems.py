"""Hazirlik denetimi OPEN-3/4/5: NOTIFIER=auto, bos HEARTBEAT_URL, HEALTH_BOTS, veto tazeligi."""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from trader_core import health as H  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_t", ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _load("health_run")
B = _load("health_backup")
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ OPEN-3
def test_auto_notifier_without_telegram_env_is_log_with_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="trader.health.run"):
        n = R.make_notifier("auto", {})
    assert isinstance(n, H.LogNotifier)
    assert sum("NOTIFIER=auto" in r.getMessage() for r in caplog.records) == 1


def test_auto_notifier_with_telegram_env_is_spooling_telegram(tmp_path):
    from trader_core import telegram as T
    n = R.make_notifier("auto", {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42",
                                 "TELEGRAM_VAR_DIR": str(tmp_path)})
    assert isinstance(n, T.TelegramNotifier)       # Outbox (spool) + dedup_key = alert.fingerprint


def test_auto_notifier_half_configured_falls_back_to_log():
    assert isinstance(R.make_notifier("auto", {"TELEGRAM_BOT_TOKEN": "123:abc"}), H.LogNotifier)


def test_explicit_telegram_without_env_still_raises():
    with pytest.raises(ValueError):
        R.make_notifier("telegram", {})


def test_empty_heartbeat_url_is_allowed_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="trader.health.run"):
        env = R.load_env({"ENGINE_VAR_DIR": "v", "BACKUP_DIR": "b", "HEARTBEAT_URL": ""})
    assert env["HEARTBEAT_URL"] == "" and any("HEARTBEAT_URL" in r.getMessage() for r in caplog.records)
    assert R.NoHeartbeat().ok(None) is True and R.NoHeartbeat().fail(None) is True


def test_run_once_with_empty_heartbeat_does_not_return_hb_failed(tmp_path):
    env = {"ENGINE_VAR_DIR": str(tmp_path), "BACKUP_DIR": str(tmp_path), "HEARTBEAT_URL": "", "STATE_DIR": str(tmp_path),
           "NOTIFIER": "log", "HEALTH_BOTS": "learner"}
    snap = _healthy_snap()
    rc = R.run_once(env, now=NOW, notifier=H.NullNotifier(), snapshot_fn=lambda e, s, n: snap)
    assert rc == R.EXIT_OK


# ------------------------------------------------------------------ OPEN-4
def test_health_bots_default_and_override():
    assert R.bots_from_env({}) == ("learner",) == B.bots_from_env({})                    # DD-12: ikiz yok
    assert R.bots_from_env({"HEALTH_BOTS": "learner"}) == ("learner",) == B.bots_from_env({"HEALTH_BOTS": "learner"})
    assert R.bots_from_env({"HEALTH_BOTS": " learner , twin ,learner"}) == ("learner", "twin")
    assert R.bots_from_env({"HEALTH_BOTS": " , "}) == ("learner",)


def test_collect_only_probes_listed_bots(tmp_path):
    (tmp_path / "bk").mkdir()
    env = {"ENGINE_VAR_DIR": str(tmp_path / "var"), "BACKUP_DIR": str(tmp_path / "bk"), "HEALTH_BOTS": "learner"}
    snap = R.collect(env, H.empty_state(), NOW)
    assert set(snap.api) == {"learner"} and set(snap.containers) == {"trader-learner"}


def test_backup_main_passes_health_bots(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(B, "run_backup", lambda bd, vd, keep, **kw: (seen.update(kw) or (0, {"files": {}, "ok": True, "created_at": "x"})))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("ENGINE_VAR_DIR", str(tmp_path))
    monkeypatch.setenv("HEALTH_BOTS", "learner")
    assert B.main() == 0 and seen["bots"] == ("learner",)


# ------------------------------------------------------------------ OPEN-5
def test_veto_probe_removed_from_health_runner():
    assert not hasattr(R, "veto_file_from_env") and not hasattr(R, "probe_veto_mtime")


def _healthy_snap():
    api = {"learner": H.ApiProbe(True, NOW, NOW - timedelta(minutes=30), (), True, "ok", False, 0, ())}
    led = {"learner": H.LedgerProbe(NOW - timedelta(minutes=5), 0, (), True, True, 0)}
    cont = {"trader-learner": H.ContainerProbe("running", 0, NOW - timedelta(days=1), None)}
    return H.HealthSnapshot(now=NOW, timeframe_s=3600, api=api, ledger=led, disk_free_bytes=50 * 1024 ** 3,
                            containers=cont,
                            last_backup_at=NOW - timedelta(hours=1), installed_at=NOW - timedelta(days=5))


def test_healthy_paper_snapshot_is_healthy_with_essential_checks_only():
    rep = H.evaluate(_healthy_snap(), R.make_cfg({"HEALTH_BOTS": "learner"}))
    assert rep.healthy and not rep.failing()
    assert {r.name.partition(":")[0] for r in rep.results} == {
        "bot_loop_age", "candle_age", "ledger_write_age", "ledger_gate", "spool_corrupt", "disk_free", "container_restarts",
        "backup_age"}
