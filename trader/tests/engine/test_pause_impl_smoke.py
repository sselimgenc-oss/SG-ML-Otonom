"""WP-B6 gerceklemesi duman testleri (11 §9): EntryPause, kapi sirasi, AST korumasi, CLI, eszamanli yazma."""
from __future__ import annotations

import ast
import json
import multiprocessing as mp
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_engine import cli
from trader_engine.clock import SimClock
from trader_engine.gates import EntryGate
from trader_engine.pause import REASONS, EntryPause

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 12, 30, 10, 0, tzinfo=timezone.utc)


def mkp(tmp_path, clock=None, bot="learner"):
    return EntryPause(str(tmp_path / f"PAUSE.{bot}"), clock or SimClock(T0), audit_path=str(tmp_path / "audit.jsonl"))


def test_file_exists_is_active_and_empty_otherwise(tmp_path):
    p = mkp(tmp_path)
    assert not p.active() and p.holds() == () and p.code() is None
    assert p.add("user_cmd", "telegram:482") is True
    assert p.active() and p.code() == "paused"
    d = json.loads((tmp_path / "PAUSE.learner").read_text())
    assert d["schema"] == "pause/1" and d["holds"][0] == {"reason": "user_cmd", "by": "telegram:482",
                                                          "at": "2026-12-30T10:00:00Z", "note": ""}


def test_corrupt_file_is_active_and_unreadable(tmp_path):
    p = mkp(tmp_path)
    for raw in ("", "{bozuk", '{"schema": "x"}', '{"schema": "pause/1", "holds": []}', "[]"):
        (tmp_path / "PAUSE.learner").write_text(raw)
        assert p.active() and p.code() == "paused"
        h = p.holds()
        assert len(h) == 1 and h[0].reason == "unreadable" and h[0].by == "system" and h[0].at is None
    (tmp_path / "PAUSE.learner").write_text("x" * 500)
    assert len(p.holds()[0].note) == 200
    assert p.remove("unreadable", "cli") is False and p.active()
    assert p.add("manual", "cli") is False and (tmp_path / "PAUSE.learner").read_text() == "x" * 500


def test_add_idempotent_keeps_first_origin(tmp_path):
    clk = SimClock(T0)
    p = mkp(tmp_path, clk)
    assert p.add("user_cmd", "telegram:111", "ilk")
    clk.advance(3600)
    assert p.add("user_cmd", "cli", "ikinci") is False
    (h,) = p.holds()
    assert (h.by, h.at, h.note) == ("telegram:111", "2026-12-30T10:00:00Z", "ilk")


def test_independent_holds_and_codes(tmp_path):
    p = mkp(tmp_path)
    p.add("user_cmd", "t")
    p.add("drawdown_review", "engine:rk1", "peak=1")
    assert [h.reason for h in p.holds()] == ["user_cmd", "drawdown_review"] and p.code() == "drawdown_review"
    assert p.remove("user_cmd", "t") is True
    assert [h.reason for h in p.holds()] == ["drawdown_review"] and p.active()
    assert p.remove("user_cmd", "t") is False
    assert p.remove("drawdown_review", "cli") is True
    assert not p.active() and not (tmp_path / "PAUSE.learner").exists()


def test_survives_restart(tmp_path):
    mkp(tmp_path).add("late_fill", "engine:reconcile")
    p2 = mkp(tmp_path)
    assert p2.active() and p2.holds()[0].reason == "late_fill"


def test_bad_reason(tmp_path):
    p = mkp(tmp_path)
    with pytest.raises(ValueError):
        p.add("nope", "x")
    with pytest.raises(ValueError):
        p.remove("nope", "x")
    assert set(REASONS) == {"user_cmd", "drawdown_review", "capital_floor", "unknown_position", "late_fill",
                            "exchange_ban", "exchange_auth", "manual", "stop_failed_repeat", "wallet_above_expected", "capital_latch"}   # 12: capital_floor; DD-6: stop_failed_repeat; DD-8: wallet_above_expected


def test_audit_log(tmp_path):
    p = mkp(tmp_path)
    p.add("manual", "cli", "n1")
    p.add("manual", "cli", "n2")                       # no-op: satir yok
    p.remove("manual", "cli")
    rows = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert [(r["op"], r["reason"], r["by"], r["note"]) for r in rows] == [("add", "manual", "cli", "n1"),
                                                                        ("remove", "manual", "cli", "")]
    assert rows[0]["at"] == "2026-12-30T10:00:00Z"


def _worker(path, audit, reason, q):
    p = EntryPause(path, SimClock(T0), audit_path=audit)
    q.put(p.add(reason, "proc:" + reason))


def test_concurrent_writes_two_processes_lossless(tmp_path):
    ctx = mp.get_context("fork")
    path, audit = str(tmp_path / "PAUSE.learner"), str(tmp_path / "audit.jsonl")
    for rnd in range(5):
        q = ctx.Queue()
        rs = ["user_cmd", "drawdown_review", "unknown_position", "late_fill", "exchange_ban", "exchange_auth", "manual"]
        ps = [ctx.Process(target=_worker, args=(path, audit, r, q)) for r in rs]
        [x.start() for x in ps]
        [x.join(30) for x in ps]
        assert [x.exitcode for x in ps] == [0] * len(ps)
        assert sorted(h.reason for h in EntryPause(path, SimClock(T0)).holds()) == sorted(rs)
        for r in rs:
            EntryPause(path, SimClock(T0), audit_path=audit).remove(r, "t")
        assert not Path(path).exists()


# ------------------------------------------------------------------------------------------------- kapi
class _Ledger:
    def entries_allowed(self):
        return SimpleNamespace(ok=True, code="ok")


class _State:
    def __init__(self, blocked=None):
        self.blocked = blocked

    def kv_get(self, k):
        return self.blocked if k == "entries_blocked_reason" else None


class _Kill:
    def __init__(self, on=False):
        self.on = on

    def active(self):
        return self.on


def _gate(pause, kill=False, blocked=None, stale=False):
    clock = SimClock(T0 + (timedelta(hours=5) if stale else timedelta(seconds=5)))
    return EntryGate(SimpleNamespace(stale_factor=1.5), _Ledger(), _State(blocked), _Kill(kill), None, clock, None,
                     lambda p: None, None, pause)


def test_gate_order_and_codes(tmp_path):
    p = mkp(tmp_path)
    ok = _gate(p).pre(T0, "1h", True, "1h")
    assert ok.ok and ok.code == "ok"
    p.add("user_cmd", "t")
    v = _gate(p).pre(T0, "1h", True, "1h")
    assert (v.ok, v.code, v.skip_reason) == (False, "paused", "entry_gate_closed")
    p.add("drawdown_review", "e")
    assert _gate(p).pre(T0, "1h", True, "1h").code == "drawdown_review"
    assert _gate(p, kill=True).pre(T0, "1h", True, "1h").code == "kill"                 # kill > pause
    assert _gate(p, blocked="clock_skew").pre(T0, "1h", True, "1h").code == "clock_skew"  # blocked > kill > pause
    assert _gate(p, stale=True).pre(T0, "1h", True, "1h").code == "drawdown_review"      # pause > stale
    assert _gate(p).pre(T0, "1h", False, "1h").code == "params_unavailable"
    assert _gate(p).pre(T0, "1h", True, "4h").code == "trigger_tf_changed"
    p.remove("drawdown_review", "c")
    p.remove("user_cmd", "c")
    assert _gate(p, stale=True).pre(T0, "1h", True, "1h").code == "stale_data"
    assert _gate(None).pre(T0, "1h", True, "1h").ok


def test_kill_pause_interaction_table(tmp_path):
    p = mkp(tmp_path)
    p.add("user_cmd", "t")
    assert _gate(p, kill=False).pre(T0, "1h", True, "1h").ok is False        # yalniz pause
    assert _gate(p, kill=True).pre(T0, "1h", True, "1h").code == "kill"       # ikisi
    p.remove("user_cmd", "t")
    assert _gate(p, kill=True).pre(T0, "1h", True, "1h").code == "kill"       # pause kalkti, kill duruyor
    p.add("user_cmd", "t")
    assert _gate(p, kill=False).pre(T0, "1h", True, "1h").code == "paused"    # kill kalkti, pause duruyor


# ------------------------------------------------------------------------------------ AST: remove yalniz cli.py
def test_engine_only_calls_add_remove_only_in_cli():
    base = ROOT / "src" / "trader_engine"
    offenders = []
    for f in base.rglob("*.py"):
        if f.name in ("cli.py", "pause.py"):
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "remove":
                recv = ast.unparse(n.func.value)
                if "pause" in recv.lower():
                    offenders.append(f"{f.name}:{n.lineno}")
    assert offenders == []
    cli_src = (base / "cli.py").read_text()
    assert ".remove(" in cli_src


# ------------------------------------------------------------------------------------------------ CLI
def _cfg_dir(tmp_path):
    d = tmp_path / "cfg"
    d.mkdir()
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(var_dir=str(tmp_path / "var"), pause_file=str(tmp_path / "shared" / "PAUSE"))
    (d / "engine.base.json").write_text(json.dumps(raw))
    (d / "engine.learner.json").write_text(json.dumps({"bot": "learner"}))
    return d


def test_cli_pause_add_list_clear(tmp_path, capsys):
    d = _cfg_dir(tmp_path)
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(d), "--by", "ops", "--note", "x"]) == 0
    f = tmp_path / "shared" / "PAUSE.learner"
    assert f.exists()
    capsys.readouterr()
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(d), "--list"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["active"] and out["holds"][0]["reason"] == "manual" and out["holds"][0]["by"] == "ops"
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(d), "--clear", "--reason", "manual", "--by", "ops"]) == 0
    assert not f.exists()
    audit = (tmp_path / "var" / "learner" / "pause_audit.jsonl").read_text().splitlines()
    assert [json.loads(x)["op"] for x in audit] == ["add", "remove"]
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(d), "--clear", "--reason", "manual", "--by", "ops"]) == 5
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(d), "--reason", "zzz"]) == 2


def test_config_pause_file_default_and_validation():
    from trader_engine.config import ConfigError, load_engine_config
    cfg = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / "engine.learner.json")
    assert cfg.pause_file == "shared/PAUSE" and cfg.path("pause_audit.jsonl").endswith("/learner/pause_audit.jsonl")
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(bot="learner", pause_file="")
    from trader_engine.config import _validate
    with pytest.raises(ConfigError):
        _validate(raw)


def test_cli_clear_requires_explicit_reason_and_by(tmp_path, capsys):
    d = _cfg_dir(tmp_path)
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(d), "--by", "ops"]) == 0
    f = tmp_path / "shared" / "PAUSE.learner"
    base = ["pause", "--bot", "learner", "--config-dir", str(d), "--clear"]
    assert cli.main(base) == 2 and f.exists()
    assert cli.main(base + ["--reason", "manual"]) == 2 and f.exists()
    assert cli.main(base + ["--by", "ops"]) == 2 and f.exists()
    assert "zorunlu" in capsys.readouterr().err
    assert cli.main(base + ["--reason", "manual", "--by", "ops"]) == 0 and not f.exists()


def test_audit_failure_after_state_write_does_not_raise(tmp_path, caplog):
    blocker = tmp_path / "blocked"
    blocker.write_text("x")                                   # audit dizini olusturulamaz (dosya var)
    p = EntryPause(str(tmp_path / "PAUSE.learner"), SimClock(T0), audit_path=str(blocker / "a.jsonl"))
    with caplog.at_level("CRITICAL"):
        assert p.add("user_cmd", "telegram:1") is True
        assert p.active() and [h.reason for h in p.holds()] == ["user_cmd"]
        assert p.add("user_cmd", "telegram:1") is False
        assert p.remove("user_cmd", "telegram:1") is True
    assert not p.active()
    assert sum(1 for r in caplog.records if r.levelname == "CRITICAL") == 2


def test_live_gate_code_params_unavailable_first():
    from trader_engine.engine import Engine
    e = Engine.__new__(Engine)
    e._params_ok, e._started = False, True
    e.ledger = SimpleNamespace(entries_allowed=lambda: SimpleNamespace(ok=False, code="ledger_x"))
    e.pause = SimpleNamespace(active=lambda: True, code=lambda: "paused")
    assert e._live_gate_code("blocked_x", True) == "params_unavailable"
    e._params_ok = True
    assert e._live_gate_code("blocked_x", True) == "ledger_x"
