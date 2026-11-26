"""Saglik toplayicisi: motor status.json esleme testleri (docs/saglik-spec.md Bolum 14)."""
import ast
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import health as H
from trader_core.health import Status

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 16, 12, 30, tzinfo=timezone.utc)


def _load(name):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _load("health_run")


def z(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def status_doc(bot="learner", **kw):
    d = {"schema": "engine-status/1", "bot": bot, "mode": "paper", "pid": 1, "started_at": z(NOW - timedelta(hours=5)),
         "loop_at": z(NOW - timedelta(seconds=10)), "last_minute_ts": z(NOW), "last_decision_bar_close": z(NOW),
         "last_candle_open": z(NOW - timedelta(minutes=45)), "trigger_tf": "1h", "param_version_id": 1,
         "strategy": {"name": "price_action_v1", "version": "1b.0"}, "entries_open": True,
         "gate": {"ok": True, "code": "ok"}, "kill": False, "kill_state": None, "entries_blocked_reason": None,
         "dry_run": True, "wallet": 1000.0, "equity": 1000.0, "day_start_equity": 1000.0,
         "open_positions": [{"trade_id": 7, "pair": "BTC/USDT", "side": "long", "qty": 1.0, "entry_price": 100.0,
                             "stop": 98.0}],
         "open_trade_ids": [7],
         "counters": {"callback_errors": 0, "data_gaps": 0, "ledger_errors": 0, "unknown_orders": 0,
                      "mark_fallbacks": 0, "minute_gaps": 0, "funding_missing": 0, "exit_data_gap": 0}}
    d.update(kw)
    return d


def put(var, bot, doc=None, raw=None):
    p = Path(var) / bot / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw if raw is not None else json.dumps(doc), encoding="utf-8")
    return str(p)


def probe(var, bot="learner", now=NOW):
    return R.probe_status(R.status_path(str(var), bot), bot, now)


def ledger_ok():
    return H.LedgerProbe(NOW - timedelta(minutes=5), 0, (), True, True, 0)


def evaluate(api, ledger=None, containers=None, tf=3600, **kw):
    bots = ("learner", "twin")
    snap = H.HealthSnapshot(
        now=NOW, timeframe_s=tf, api=api, ledger=ledger or {b: ledger_ok() for b in bots},
        disk_free_bytes=50 * H.GIB, 
        containers=containers if containers is not None else {
            f"trader-{b}": H.ContainerProbe("running", 4, NOW - timedelta(hours=5), None) for b in bots},
        prev_restart_counts={"trader-learner": 4, "trader-twin": 4},
        last_backup_at=NOW - timedelta(hours=3), **kw)
    return H.evaluate(snap, H.HealthConfig(require_bots=bots))   # DD-12: varsayilan yalniz learner; genel coklu bot denetimi


def by(rep, name):
    return next(r for r in rep.results if r.name == name)


def api_from(var):
    return {b: probe(var, b)[0] for b in ("learner", "twin")}


# --------------------------------------------------------------------------- probe_status
def test_fresh_status_maps_all_fields(tmp_path):
    put(tmp_path, "learner", status_doc())
    p, tf = probe(tmp_path)
    assert p.ping_ok is True and p.dry_run is True
    assert p.last_process_at == NOW - timedelta(seconds=10)
    assert p.last_candle_open == NOW - timedelta(minutes=45)
    assert p.open_trade_ids == (7,) and p.gate_code == "ok" and p.kill is False and p.ledger_errors == 0
    assert p.unprotected_ids == () and tf == 3600


def test_stale_status_ping_false_but_loop_age_graded(tmp_path):
    put(tmp_path, "learner", status_doc(loop_at=z(NOW - timedelta(seconds=400))))
    put(tmp_path, "twin", status_doc("twin"))
    p, _ = probe(tmp_path)
    assert p.ping_ok is False and p.last_process_at == NOW - timedelta(seconds=400)
    rep = evaluate(api_from(tmp_path))
    assert by(rep, "bot_loop_age:learner").status is Status.CRIT
    c = R.engine_container(R.status_path(str(tmp_path), "learner"), "learner", NOW, H.empty_state(), "trader-learner")
    assert c.state == "not_running"
    rep2 = evaluate(api_from(tmp_path), containers={"trader-learner": c, "trader-twin": H.ContainerProbe(
        "running", 4, NOW, None)})
    assert by(rep2, "container_restarts:trader-learner").code == "container_not_running"
    assert not rep.healthy


def test_status_just_inside_ping_window(tmp_path):
    put(tmp_path, "learner", status_doc(loop_at=z(NOW - timedelta(seconds=120))))
    assert probe(tmp_path)[0].ping_ok is True


def test_missing_file_is_unreachable(tmp_path):
    p, tf = probe(tmp_path)
    assert p == H.ApiProbe(ping_ok=False) and tf is None


@pytest.mark.parametrize("raw", ["{bozuk", "", "[]", '{"schema": "engine-status/9", "bot": "learner"}',
                                 "\xff\xfe"])
def test_corrupt_status_all_unknown(tmp_path, raw):
    put(tmp_path, "learner", raw=raw)
    p, tf = probe(tmp_path)
    assert p == H.ApiProbe() and tf is None


def test_wrong_bot_in_file_unknown(tmp_path):
    put(tmp_path, "learner", status_doc("twin"))
    assert probe(tmp_path)[0] == H.ApiProbe()


def test_future_loop_at_is_clock_skew_unknown(tmp_path):
    put(tmp_path, "learner", status_doc(loop_at=z(NOW + timedelta(seconds=60))))
    put(tmp_path, "twin", status_doc("twin"))
    p, _ = probe(tmp_path)
    assert p.ping_ok is None
    rep = evaluate(api_from(tmp_path))
    assert by(rep, "bot_loop_age:learner").code == "clock_skew"
    assert not rep.healthy


def test_unreadable_path_is_unknown(tmp_path):
    (tmp_path / "learner" / "status.json").mkdir(parents=True)     # dosya yerine dizin -> OSError
    assert probe(tmp_path)[0] == H.ApiProbe()


def test_missing_gate_field_is_closed(tmp_path):
    d = status_doc()
    del d["gate"]
    put(tmp_path, "learner", d)
    put(tmp_path, "twin", status_doc("twin"))
    assert probe(tmp_path)[0].gate_code == "status_malformed"
    rep = evaluate(api_from(tmp_path))
    assert by(rep, "ledger_gate:learner").status is Status.CRIT


def test_no_candle_yet_is_unknown(tmp_path):
    put(tmp_path, "learner", status_doc(last_candle_open=None))
    put(tmp_path, "twin", status_doc("twin"))
    rep = evaluate(api_from(tmp_path))
    assert by(rep, "candle_age:learner").status is Status.UNKNOWN and not rep.healthy


# --------------------------------------------------------------------------- kontrol esleme
def test_healthy_both_bots(tmp_path):
    put(tmp_path, "learner", status_doc())
    put(tmp_path, "twin", status_doc("twin"))
    rep = evaluate(api_from(tmp_path))
    assert rep.overall is Status.OK and rep.healthy
    assert len([r for r in rep.results if r.status is not Status.SKIPPED]) >= 11


def test_candle_age_uses_trigger_tf(tmp_path):
    put(tmp_path, "learner", status_doc(last_candle_open=z(NOW - timedelta(hours=4)), trigger_tf="1h"))
    put(tmp_path, "twin", status_doc("twin"))
    _, tf = probe(tmp_path)
    rep = evaluate(api_from(tmp_path), tf=tf)
    assert by(rep, "candle_age:learner").status is Status.CRIT       # 4h > 3*1h + 120 sn
    assert by(rep, "candle_age:twin").status is Status.OK


def test_killswitch_on_warns_and_stays_healthy(tmp_path):
    put(tmp_path, "learner", status_doc(kill=True, kill_state="exiting", gate={"ok": False, "code": "kill"},
                                        entries_open=False))
    put(tmp_path, "twin", status_doc("twin"))
    rep = evaluate(api_from(tmp_path))
    r = by(rep, "ledger_gate:learner")
    assert r.status is Status.WARN and r.code == "engine_kill"
    assert rep.overall is Status.WARN and rep.healthy
    assert by(rep, "ledger_gate:twin").status is Status.OK


@pytest.mark.parametrize("code", ["degraded", "spool_pending", "reconcile_unknown_position", "stop_failed",
                                  "engine_errors", "clock_skew", "params_unavailable"])
def test_engine_gate_closed_is_crit(tmp_path, code):
    put(tmp_path, "learner", status_doc(gate={"ok": False, "code": code}, entries_open=False,
                                        entries_blocked_reason=code))
    put(tmp_path, "twin", status_doc("twin"))
    rep = evaluate(api_from(tmp_path))
    r = by(rep, "ledger_gate:learner")
    assert r.status is Status.CRIT and r.code == "engine_gate_closed" and code in r.detail
    assert not rep.healthy


def test_ledger_errors_counter_warns(tmp_path):
    d = status_doc()
    d["counters"]["ledger_errors"] = 3
    put(tmp_path, "learner", d)
    put(tmp_path, "twin", status_doc("twin"))
    rep = evaluate(api_from(tmp_path))
    r = by(rep, "ledger_gate:learner")
    assert r.status is Status.WARN and r.code == "ledger_errors" and rep.healthy


def test_unledgered_open_trade_from_status_ids(tmp_path):
    put(tmp_path, "learner", status_doc())
    put(tmp_path, "twin", status_doc("twin"))
    api = api_from(tmp_path)
    led = {"learner": H.LedgerProbe(NOW, 0, tuple(api["learner"].open_trade_ids), True, True, 0),
           "twin": ledger_ok()}
    assert by(evaluate(api, led), "ledger_gate:learner").code == "unledgered_trades"


def test_unprotected_position_detected(tmp_path):
    d = status_doc()
    d["open_positions"][0]["stop"] = None
    put(tmp_path, "learner", d)
    assert probe(tmp_path)[0].unprotected_ids == (7,)


# --------------------------------------------------------------------------- twin eksik
def test_twin_status_missing_is_unhealthy(tmp_path):
    put(tmp_path, "learner", status_doc())
    api = api_from(tmp_path)
    assert api["twin"] == H.ApiProbe(ping_ok=False)
    rep = evaluate(api, containers={"trader-learner": H.ContainerProbe("running", 4, NOW - timedelta(hours=5), None),
                                    "trader-twin": H.ContainerProbe()})
    assert by(rep, "bot_loop_age:twin").status is Status.UNKNOWN
    assert by(rep, "candle_age:twin").status is Status.UNKNOWN
    assert by(rep, "container_restarts:trader-twin").status is Status.UNKNOWN
    assert by(rep, "bot_loop_age:learner").status is Status.OK
    assert rep.overall is Status.UNKNOWN and not rep.healthy


def test_twin_probe_missing_entirely_is_missing_check():
    rep = evaluate({"learner": H.ApiProbe(True, NOW, NOW - timedelta(minutes=30), (), True)})
    assert by(rep, "bot_loop_age:twin").code == "missing_check" and not rep.healthy


# --------------------------------------------------------------------------- toplayici (collect)
def _env(tmp_path):
    (tmp_path / "bk").mkdir(exist_ok=True)
    return {"ENGINE_VAR_DIR": str(tmp_path / "var"), "BACKUP_DIR": str(tmp_path / "bk"), "HEARTBEAT_URL": "https://h/x",
            "HEALTH_BOTS": "learner,twin"}


def test_collect_reads_both_instances(tmp_path):
    env = _env(tmp_path)
    put(tmp_path / "var", "learner", status_doc())
    put(tmp_path / "var", "twin", status_doc("twin", trigger_tf="4h"))
    snap = R.collect(env, H.empty_state(), NOW)
    assert snap.api["learner"].ping_ok is True and snap.api["twin"].ping_ok is True
    assert snap.timeframe_s == 3600
    assert snap.containers["trader-learner"].state == "running"
    assert snap.containers["trader-learner"].oom_killed is None
    assert snap.ledger["learner"].spool_lines in (0, None)      # defter dosyasi yok -> kapali/UNKNOWN, istisna yok


def test_collect_twin_missing(tmp_path):
    env = _env(tmp_path)
    put(tmp_path / "var", "learner", status_doc())
    snap = R.collect(env, H.empty_state(), NOW)
    assert snap.api["twin"].ping_ok is False and snap.containers["trader-twin"].state is None
    assert not H.evaluate(snap).healthy


def test_restart_counter_derived_from_started_at(tmp_path):
    env = _env(tmp_path)
    put(tmp_path / "var", "learner", status_doc())
    put(tmp_path / "var", "twin", status_doc("twin"))
    st = H.empty_state()
    st["restart_counts"] = {"trader-learner": 4, "trader-twin": 4}
    st["engine_started_at"] = {"trader-learner": z(NOW - timedelta(days=1)),
                               "trader-twin": z(NOW - timedelta(hours=5))}
    snap = R.collect(env, st, NOW)
    assert snap.containers["trader-learner"].restart_count == 5       # started_at degisti
    assert snap.containers["trader-twin"].restart_count == 4          # ayni surec
    r = by(H.evaluate(snap), "container_restarts:trader-learner")
    assert r.status is Status.WARN and r.code == "container_restarted"


def test_run_once_persists_started_at_and_counter(tmp_path):
    env = _env(tmp_path)
    put(tmp_path / "var", "learner", status_doc())
    put(tmp_path / "var", "twin", status_doc("twin"))

    class S:
        def ok(self, rep):
            return True

        def fail(self, rep):
            return True
    sp = tmp_path / "state.json"
    R.run_once(env, now=NOW, state_path=sp, notifier=H.NullNotifier(), sender=S())
    st = json.loads(sp.read_text())
    assert st["engine_started_at"]["trader-learner"] == z(NOW - timedelta(hours=5))
    put(tmp_path / "var", "learner", status_doc(started_at=z(NOW - timedelta(minutes=1))))
    R.run_once(env, now=NOW + timedelta(minutes=5), state_path=sp, notifier=H.NullNotifier(), sender=S())
    assert json.loads(sp.read_text())["restart_counts"]["trader-learner"] == 1


def test_load_env_requires_engine_var_dir():
    with pytest.raises(ValueError):
        R.load_env({"HEARTBEAT_URL": "x", "BACKUP_DIR": "y"})
    R.load_env({"HEARTBEAT_URL": "x", "BACKUP_DIR": "y", "ENGINE_VAR_DIR": "z"})


# --------------------------------------------------------------------------- kurtarma R7/R8
def test_recover_r7_r8_from_status(tmp_path):
    Rec = _load("health_recover")
    env = _env(tmp_path)
    d = status_doc()
    d["open_positions"][0]["stop"] = None
    put(tmp_path / "var", "learner", d)
    env.pop("HEALTH_BOTS")                                    # DD-12: varsayilan yalniz learner
    snap = R.collect(env, H.empty_state(), NOW)
    rows = {(r["step"], r["detail"].split()[0]): r["status"]
            for r in Rec.run_checks(env, snap, H.empty_state(), run=lambda *a, **k: (_ for _ in ()).throw(OSError()))}
    assert rows[("R7", "learner")] == "FAIL" and rows[("R8", "learner")] == "PASS"
    assert not [k for k in rows if k[1] == "twin"]


# --------------------------------------------------------------------------- freqtrade yok
@pytest.mark.parametrize("rel", ["src/trader_core/health.py", "scripts/health_run.py", "scripts/health_backup.py",
                                 "scripts/health_recover.py"])
def test_no_forbidden_imports_or_freqtrade_sources(rel):
    tree = ast.parse((ROOT / rel).read_text("utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert not mods & {"freqtrade", "ccxt", "binance", "docker", "urllib", "requests", "subprocess"} - (
        {"urllib"} if rel.endswith("health.py") else set()) - ({"subprocess"} if rel.endswith("recover.py") else set())
    src = (ROOT / rel).read_text("utf-8").lower()
    for bad in ("tradesv3", "/api/v1", "docker inspect", "freqtrade_api", "freqtrade_user_data"):
        assert bad not in src
