"""WP-B8: testnet golge servisi (birim/install/env), status.exchange + dry_run, saglik alarmlari. Ag yok."""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests" / "readiness"))
from trader_core import health as H  # noqa: E402
from trader_core.health import Status  # noqa: E402
from readiness_support import render_env_files, render_units, unit_kv  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_b8", ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _load("health_run")
NOW = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)
UNIT = DEPLOY / "trader-engine-testnet.service"


def z(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================ birim / install
def test_testnet_unit_hardening_matches_paper_engine():
    t = dict(unit_kv(UNIT.read_text(encoding="utf-8")))
    p = dict(unit_kv((DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")))
    assert t["Slice"] == "trader.slice"
    for k in ("User", "Group", "WorkingDirectory", "NoNewPrivileges", "PrivateTmp", "ProtectSystem", "ProtectHome",
              "CPUQuota", "Nice", "Restart"):
        assert t[k] == p[k], k
    assert "run --bot learner --env testnet" in t["ExecStart"]
    assert "run --bot learner --env testnet" in t["ExecStart"] and t["ExecStart"].endswith("--ensure-ledger")   # DD-9: init-ledger ExecStartPre'den run --ensure-ledger'a
    assert "var-testnet" in t["ReadWritePaths"] and "/opt/trader/shared" in t["ReadWritePaths"]
    assert int(t["MemoryHigh"][:-1]) < int(t["MemoryMax"][:-1])


def test_testnet_unit_uses_only_testnet_key_file():
    files = [v.lstrip("-") for k, v in unit_kv(UNIT.read_text(encoding="utf-8")) if k == "EnvironmentFile"]
    assert "/etc/trader-testnet.env" in files
    assert set(files) <= {"/etc/trader-testnet.env"}
    # canli anahtar dosyasi yok (canli birim/dosya adi henuz yok; yine de ad ipucu verilmez)
    assert not any("live" in f for f in files)
    assert "LIVE_CONFIRM" not in UNIT.read_text(encoding="utf-8")


def test_testnet_unit_config_paths_are_isolated():
    cfg = json.loads((ROOT / "config" / "engine.testnet.json").read_text())
    assert cfg["var_dir"] == "var-testnet"
    assert cfg["kill_file"] == "shared/testnet/KILL" and cfg["pause_file"] == "shared/testnet/PAUSE"


def test_testnet_unit_renders_and_exec_resolves(tmp_path):
    txt = render_units(tmp_path)["trader-engine-testnet.service"]
    assert "/opt/trader" not in txt and "/usr/bin/python3" not in txt
    assert "/.venv/bin/python -m trader_engine run --bot learner --env testnet" in txt


def test_testnet_env_example_stub_empty_keys_and_install_perms(tmp_path):
    ex = (DEPLOY / "trader-testnet.env.example").read_text(encoding="utf-8")
    kv = dict(l.split("=", 1) for l in ex.splitlines() if l and not l.startswith("#") and "=" in l)
    assert kv == {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""}
    out = render_env_files(tmp_path)
    assert out["trader-testnet.env"] == {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": ""}
    assert stat.S_IMODE((tmp_path / "trader-testnet.env").stat().st_mode) == 0o600
    inst = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert re.search(r'copy_env "\$REL_DIR/deploy/trader-testnet\.env\.example"\s+/etc/trader-testnet\.env\s+"root:root"\s+0600', inst)


def test_install_gates_testnet_unit_on_both_keys_and_creates_dirs():
    inst = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert not re.search(r"^enable_now trader-engine-testnet\.service", inst, re.M)
    m = re.search(r"if has_value /etc/trader-testnet\.env BINANCE_API_KEY && has_value /etc/trader-testnet\.env "
                  r"BINANCE_API_SECRET; then.*?enable_now trader-engine-testnet\.service.*?\nelse MISSING", inst, re.S)
    assert m, "testnet birimi anahtar denetimi olmadan aciliyor"
    assert '"$TRADER_DIR/var-testnet"' in inst and '"$TRADER_DIR/shared/testnet"' in inst
    assert "/etc/trader-testnet.env" in (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")


def test_install_gate_executes_empty_vs_filled(tmp_path):
    """Kapi blogunu gercekten calistirir: bos anahtar -> enable_now cagrilmaz; dolu -> cagrilir."""
    inst = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    a = inst.index("has_value() {")
    b = inst.index("MISSING=()")
    g0 = inst.index("# Testnet golge motoru (WP-B8)")
    g1 = inst.index("# ---- 11. ozet")
    for key, secret, expect in (("", "", False), ("k" * 40, "", False), ("k" * 40, "s" * 40, True)):
        envf = tmp_path / f"t{expect}{bool(key)}.env"
        envf.write_text(f"BINANCE_API_KEY={key}\nBINANCE_API_SECRET={secret}\n")
        hf = tmp_path / "health.env"
        hf.write_text("ENGINE_VAR_DIR=/x\n")
        block = inst[g0:g1].replace("/etc/trader-testnet.env", str(envf)).replace("/etc/trader-health.env", str(hf))
        script = ("set -euo pipefail\nMISSING=()\nTRADER_DIR=/srv/t\nenable_now() { echo ENABLED:$1; }\n"
                  + inst[a:b] + block + "\necho missing=${#MISSING[@]}\n")
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout
        assert ("ENABLED:trader-engine-testnet.service" in r) is expect, r
        assert ("missing=0" in r) is expect
        if expect:
            assert "HEALTH_SHADOW_VAR_DIR=/srv/t/var-testnet" in hf.read_text()


def test_testnet_unit_has_memory_cap_and_fits_slice_soft_cap():
    def kv(n):
        return dict(unit_kv((DEPLOY / n).read_text(encoding="utf-8")))
    sl = kv("trader.slice")
    assert sl["MemoryHigh"] == "1100M" and sl["MemoryMax"] == "1300M"   # ayrilmis 2 GB sunucu: degismez
    hi = lambda n: int(kv(n)["MemoryHigh"][:-1])  # noqa: E731
    soft = hi("trader-feed.service") + hi("trader-engine@.service") + hi("trader-engine-testnet.service")   # DD-12: ikiz yok
    assert soft <= int(sl["MemoryHigh"][:-1]), soft
    assert int(kv("trader-engine-testnet.service")["MemoryMax"][:-1]) <= 350


def test_docs_have_memory_note_and_testnet_env_path():
    doc = (ROOT / "docs" / "sunucu-kurulum.md").read_text(encoding="utf-8")
    assert "/etc/trader-testnet.env" in doc and "trader-engine-testnet" in doc
    assert "systemd-cgtop" in doc and "MemoryPeak" in doc and "ENGINE_VAR_DIR" in doc and "PAUSE_FILE" in doc
    env = (DEPLOY / "trader-health.env.example").read_text(encoding="utf-8")
    assert "CANLIYA CIKISTA" not in env and "HEALTH_SHADOW_VAR_DIR=" in env      # DD-9: elle cevirme talimati silindi (install.sh --live yazar)
    assert "LIVE_VAR_DIR=" in env


# ============================================================ status.py
def _fields(exchange=None, positions=()):
    f = {"tf": "1h", "param_version_id": 1, "strategy_name": "s", "strategy_version": "1", "entries_blocked_reason": None,
         "gate_code": "ok", "entries_open": True, "kill": False, "kill_state": None, "wallet": 1000.0, "equity": 1000.0,
         "day_start_equity": 1000.0, "open_positions": list(positions), "counters": {}, "last_minute_ts": None,
         "last_decision_close": None, "last_candle_open": None, "ml": None, "pause": None}
    if exchange is not None:
        f["exchange"] = exchange
    return f


def _build(mode, exchange=None, last_ban=None):
    from trader_engine.status import StatusWriter
    cfg = SimpleNamespace(bot="learner", mode=mode, loop_sleep_s=5.0)
    clock = SimpleNamespace(now=lambda: NOW)
    eng = SimpleNamespace(status_fields=lambda: _fields(exchange), broker=SimpleNamespace(last_ban=last_ban))
    return StatusWriter("x", clock, cfg).build(eng)


@pytest.mark.parametrize("mode,dry", [("paper", True), ("backtest", True), ("testnet", True), ("live", False)])
def test_status_dry_run_follows_mode(mode, dry):
    assert _build(mode)["dry_run"] is dry


def test_status_paper_has_no_exchange_block():
    assert "exchange" not in _build("paper")


def test_status_exchange_block_published():
    ex = {"reachable": False, "last_sync_ts": "2026-12-20T11:58:00Z", "clock_offset_ms": 12, "used_weight": 33,
          "ban_until_ms": int(NOW.timestamp() * 1000), "exchange_bans": 1,
          "naked": [{"trade_id": 4, "pair": "BTC/USDT", "seconds": 3.5}, {"bozuk": 1}]}
    d = _build("testnet", ex, last_ban=(418, 120))
    b = d["exchange"]
    assert b["env"] == "testnet" and b["reachable"] is False and b["last_sync"] == "2026-12-20T11:58:00Z"
    assert b["naked"] == [{"trade_id": 4, "pair": "BTC/USDT", "seconds": 3.5}]
    assert b["last_ban"] == {"http": 418, "retry_after_s": 120}
    assert b["ban_until"] == "2026-12-20T12:00:00Z" and b["used_weight"] == 33 and b["clock_offset_ms"] == 12
    json.dumps(d)


def test_status_exchange_block_defaults_when_broker_silent():
    b = _build("live", {"naked": []})["exchange"]
    assert b["reachable"] is None and b["last_ban"] is None and b["naked"] == [] and b["ban_until"] is None


# ============================================================ saglik: probe_status
def _doc(**kw):
    d = {"schema": "engine-status/1", "bot": "learner", "mode": "testnet", "loop_at": z(NOW - timedelta(seconds=5)),
         "started_at": z(NOW - timedelta(hours=1)), "last_candle_open": z(NOW - timedelta(minutes=10)), "trigger_tf": "1h",
         "gate": {"ok": True, "code": "ok"}, "kill": False, "open_positions": [], "open_trade_ids": [], "dry_run": True,
         "counters": {"ledger_errors": 0},
         "exchange": {"env": "testnet", "reachable": True, "last_sync": z(NOW - timedelta(seconds=3)), "naked": []}}
    d.update(kw)
    return d


def _probe(tmp_path, doc):
    p = tmp_path / "learner" / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc))
    return R.probe_status(str(p), "learner", NOW)[0]


def _snap(api, **kw):
    return H.HealthSnapshot(now=NOW, timeframe_s=3600, api={"learner": api}, ledger={}, disk_free_bytes=50 * H.GIB,
                            
                            last_backup_at=NOW - timedelta(hours=1), **kw)


def _ev(api, cfg=None, **kw):
    cfg = cfg or H.HealthConfig(require_bots=("learner",))
    rep = H.evaluate(_snap(api, **kw), cfg)
    return {r.name: r for r in rep.results}


def test_probe_maps_exchange_block(tmp_path):
    p = _probe(tmp_path, _doc(exchange={"reachable": False, "last_sync": z(NOW - timedelta(seconds=90)),
                                         "naked": [{"trade_id": 2, "pair": "XRP/USDT", "seconds": 4}]}))
    assert p.has_exchange and p.mode == "testnet" and p.exchange_reachable is False
    assert p.exchange_last_sync == NOW - timedelta(seconds=90) and p.naked == ((2, "XRP/USDT", 4.0),)


def test_probe_paper_has_no_exchange_block(tmp_path):
    d = _doc(mode="paper")
    del d["exchange"]
    p = _probe(tmp_path, d)
    assert not p.has_exchange and p.naked is None
    r = _ev(p)
    assert "naked_position:learner" not in r and "exchange_reachable:learner" not in r


@pytest.mark.parametrize("naked", ["x", [{"trade_id": 1}], [{"trade_id": 1, "pair": "A", "seconds": -1}]])
def test_probe_malformed_naked_is_unknown(tmp_path, naked):
    p = _probe(tmp_path, _doc(exchange={"reachable": True, "naked": naked}))
    assert p.naked is None
    assert _ev(p)["naked_position:learner"].status is Status.UNKNOWN


# ============================================================ saglik: naked / exchange
def test_naked_position_is_immediate_crit():
    api = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "testnet", True, True, NOW, ((3, "BTC/USDT", 4.0),))
    r = _ev(api)["naked_position:learner"]
    assert r.status is Status.CRIT and r.code == "naked_position" and "BTC/USDT#3" in r.detail
    assert "naked_position" in H.IMMEDIATE_CODES


def test_naked_threshold_configurable():
    api = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "live", True, True, NOW, ((3, "BTC/USDT", 4.0),))
    cfg = H.HealthConfig(require_bots=("learner",), naked_alarm_s=10.0)
    assert _ev(api, cfg)["naked_position:learner"].status is Status.OK
    cfg = H.HealthConfig(require_bots=("learner",), naked_alarm_s=3.0)
    assert _ev(api, cfg)["naked_position:learner"].status is Status.CRIT


def test_naked_clear_and_status_unprotected_position():
    ok = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "live", True, True, NOW, ())
    assert _ev(ok)["naked_position:learner"].status is Status.OK
    bad = H.ApiProbe(True, NOW, NOW, (9,), True, "ok", False, 0, (9,), "live", True, True, NOW, ())
    assert _ev(bad)["naked_position:learner"].code == "naked_position"


def test_alert_plan_sends_naked_in_one_run():
    api = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "testnet", True, True, NOW, ((3, "BTC/USDT", 4.0),))
    cfg = H.HealthConfig(require_bots=("learner",), multiple_threshold=50)
    rep = H.evaluate(_snap(api), cfg)
    alerts, _ = H.plan_alerts(rep, H.empty_state(), NOW, cfg)
    assert any(a.code == "naked_position" and a.level is Status.CRIT for a in alerts)


def test_exchange_unreachable_grades_by_last_sync():
    def mk(age):
        return H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "testnet", True, False,
                          None if age is None else NOW - timedelta(seconds=age), ())
    assert _ev(mk(20))["exchange_reachable:learner"].status is Status.WARN
    r = _ev(mk(61))["exchange_reachable:learner"]
    assert r.status is Status.CRIT and r.code == "exchange_unreachable"
    assert _ev(mk(None))["exchange_reachable:learner"].status is Status.CRIT
    ok = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "testnet", True, True, NOW, ())
    assert _ev(ok)["exchange_reachable:learner"].status is Status.OK
    unk = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "testnet", True, None, None, ())
    assert _ev(unk)["exchange_reachable:learner"].status is Status.UNKNOWN


def test_config_validation_and_env_overrides():
    with pytest.raises(ValueError):
        H.HealthConfig(naked_alarm_s=-1)
    with pytest.raises(ValueError):
        H.HealthConfig(exchange_unreachable_s=0)
    c = R.make_cfg({"NAKED_ALARM_S": "7", "EXCHANGE_UNREACH_S": "90"})
    assert c.naked_alarm_s == 7.0 and c.exchange_unreachable_s == 90
    d = R.make_cfg({"NAKED_ALARM_S": "", "EXCHANGE_UNREACH_S": "abc"})
    assert d.naked_alarm_s == 0.0 and d.exchange_unreachable_s == 60


# ============================================================ saglik: pause denetim
def _pause_files(tmp_path, holds, ops):
    base = tmp_path / "shared" / "PAUSE"
    base.parent.mkdir(parents=True, exist_ok=True)
    if holds is not None:
        base.with_name("PAUSE.learner").write_text(json.dumps(
            {"schema": "pause/1", "bot": "learner", "holds": [{"reason": h, "by": "x", "at": None, "note": ""} for h in holds]})
            if holds else "")
        if not holds:
            base.with_name("PAUSE.learner").unlink()
    audit = tmp_path / "var" / "learner" / "pause_audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text("".join(json.dumps({"at": "t", "op": op, "reason": r, "by": "x", "note": ""}) + "\n" for op, r in ops))
    return R.probe_pause(str(base), str(audit), "learner")


def _pcheck(probe, prev=()):
    api = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "paper")
    return _ev(api, pause={"learner": probe}, prev_pause_holds={"learner": tuple(prev)})["pause_audit:learner"]


# ============================================================ urllib3 gunlugu
def test_quiet_http_loggers_raises_debug_to_info():
    lg = logging.getLogger("urllib3")
    old = lg.level
    try:
        lg.setLevel(logging.DEBUG)
        H.quiet_http_loggers()
        assert lg.getEffectiveLevel() >= logging.INFO
    finally:
        lg.setLevel(old)


def test_entrypoints_set_urllib3_level():
    for rel in ("scripts/health_run.py", "scripts/telegram_run.py", "src/trader_engine/cli.py"):
        t = (ROOT / rel).read_text(encoding="utf-8")
        assert "quiet_http_loggers()" in t or 'getLogger("urllib3").setLevel(logging.INFO)' in t, rel
