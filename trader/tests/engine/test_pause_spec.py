"""WP-B6 bagimsiz sartname testi: giris duraklatma (docs/motor/11-canli-broker.md §9, §13 satir B6).

Yalniz sartnameden yazildi (pause.py / gates.py / status.py / cli.py gerceklemesine BAKILMADI). `pause` modulu tembel
import edilir; gerceklenmemisse testler tek tek basarisiz olur. Belirsiz noktalar `# SPEC-AMBIGUOUS:` ile isaretli.
Motor-duzeyi testler 05 duzenegini (tests/engine/test_engine_05_spec.py `Env`) yeniden kullanir.
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_engine.clock import SimClock

from test_engine_05_spec import BTC, ETH, H, M1, Env, _hold_block, flip_ctx  # noqa: E402

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TP = datetime(2026, 12, 30, 10, 0, 0, tzinfo=UTC)      # sartname ornegindeki an
TE = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)           # 05 duzeneginin T0'i

ALL_REASONS = ("user_cmd", "drawdown_review", "unknown_position", "late_fill", "exchange_ban", "exchange_auth", "manual")


def pmod():
    return importlib.import_module("trader_engine.pause")


def make_pause(tmp: Path, clock=None, bot="learner"):
    # path = f"{cfg.pause_file}.{bot}" (§3.1)
    path = tmp / "shared" / f"PAUSE.{bot}"
    return pmod().EntryPause(str(path), clock or SimClock(TP)), path


class _PZ:
    """EntryPause'a ince sarmalayici: yalniz test yardimci alanlari ekler."""

    def __init__(self, ep, tmp, clock, path):
        self._ep, self.tmp, self.clock_, self.path_ = ep, tmp, clock, path

    def __getattr__(self, name):
        return getattr(self._ep, name)


@pytest.fixture
def pz(tmp_path, monkeypatch):
    # SPEC-AMBIGUOUS: denetim gunlugu yolu `var/<bot>/pause_audit.jsonl`; EntryPause yalniz `path` alir, `var` kokunu
    # bilmez. Kok olarak cwd varsayilir (cwd = tmp) ve gunluk tmp altinda rglob ile aranir.
    monkeypatch.chdir(tmp_path)
    clock = SimClock(TP)
    ep, path = make_pause(tmp_path, clock)
    return _PZ(ep, tmp_path, clock, path)


def audit_rows(tmp: Path) -> list[dict]:
    rows = []
    for p in tmp.rglob("pause_audit.jsonl"):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rows.append(json.loads(ln))
    return rows


# =====================================================================================================
# 1. active() / holds() / code(): dosya var = etkin, bozuk dosya etkin
# =====================================================================================================
class TestActive:
    def test_reasons_constant(self):
        # 12 (RK-1) ile guncellendi: REASONS'a "capital_floor" eklendi (drawdown_review'dan sonra); ALL_REASONS 11 donemidir
        assert tuple(pmod().REASONS) == ALL_REASONS[:2] + ("capital_floor",) + ALL_REASONS[2:] + ("stop_failed_repeat", "wallet_above_expected", "capital_latch")  # capital_latch: kullanici karari; DD-6; DD-8: wallet_above_expected

    def test_no_file_inactive(self, pz):
        assert pz.active() is False
        assert pz.holds() == ()
        assert pz.code() is None

    def test_file_exists_is_active_after_add(self, pz):
        assert pz.add("user_cmd", by="telegram:482") is True
        assert pz.active() is True
        assert pz.code() == "paused"

    @pytest.mark.parametrize("content", ["", "{bozuk json", "[1,2]", '{"schema": "baska/9", "holds": []}',
                                         '{"schema": "pause/1", "holds": "x"}', "\x00\x01\x02"])
    def test_any_file_is_active_content_irrelevant(self, pz, content):
        pz.path_.parent.mkdir(parents=True, exist_ok=True)
        pz.path_.write_bytes(content.encode("latin-1"))
        assert pz.active() is True                      # değişmez (1)

    @pytest.mark.parametrize("content", ["", "{bozuk json", "[1,2]", '{"schema": "baska/9", "holds": []}'])
    def test_corrupt_file_yields_unreadable_hold(self, pz, content):
        pz.path_.parent.mkdir(parents=True, exist_ok=True)
        pz.path_.write_text(content)
        h = pz.holds()
        assert len(h) == 1
        assert h[0].reason == "unreadable" and h[0].by == "system" and h[0].at is None
        assert h[0].note == content[:200]
        assert pz.code() == "paused"

    def test_unreadable_note_truncated_to_200_chars(self, pz):
        pz.path_.parent.mkdir(parents=True, exist_ok=True)
        pz.path_.write_text("x" * 500)
        assert pz.holds()[0].note == "x" * 200

    def test_non_filenotfound_oserror_is_active_fail_closed(self, pz, tmp_path):
        # yol bir dosyanin "altinda" -> stat NotADirectoryError (FileNotFoundError DEGIL) -> etkin (fail-closed)
        blocker = tmp_path / "blocker"
        blocker.write_text("dosya")
        ep = pmod().EntryPause(str(blocker / "PAUSE.learner"), SimClock(TP))
        # SPEC-AMBIGUOUS: NotADirectoryError FileNotFoundError'in kardesidir; "FileNotFoundError disindaki her OSError"
        # en harfi harfine okununca etkin sayilir.
        assert ep.active() is True

    def test_permission_error_on_stat_is_active(self, pz, monkeypatch):
        real = os.stat
        target = str(pz.path_)

        def boom(p, *a, **k):
            if str(p) == target:
                raise PermissionError("izin yok")
            return real(p, *a, **k)
        monkeypatch.setattr(os, "stat", boom)
        assert pz.active() is True

    def test_holds_roundtrip_fields(self, pz):
        pz.add("user_cmd", by="telegram:482", note="n1")
        (h,) = pz.holds()
        assert (h.reason, h.by, h.at, h.note) == ("user_cmd", "telegram:482", "2026-12-30T10:00:00Z", "n1")

    def test_file_format(self, pz):
        pz.add("user_cmd", by="telegram:482")
        doc = json.loads(pz.path_.read_text())
        assert doc["schema"] == "pause/1"
        # SPEC-AMBIGUOUS: "bot" alani yoldan (`<pause_file>.<bot>` son eki) turetilir varsayildi; EntryPause bot almaz.
        assert doc["bot"] == "learner"
        assert doc["holds"] == [{"reason": "user_cmd", "by": "telegram:482", "at": "2026-12-30T10:00:00Z", "note": ""}]

    def test_code_drawdown_review_wins(self, pz):
        pz.add("user_cmd", by="telegram:1")
        assert pz.code() == "paused"
        pz.add("drawdown_review", by="engine:rk1", note="peak=1100 equity=870")
        assert pz.code() == "drawdown_review"
        pz.add("manual", by="ben")
        assert pz.code() == "drawdown_review"

    @pytest.mark.parametrize("reason", [r for r in ALL_REASONS if r != "drawdown_review"])
    def test_code_paused_for_every_other_reason(self, pz, reason):
        pz.add(reason, by="x")
        assert pz.code() == "paused"


# =====================================================================================================
# 2. add / remove semantigi
# =====================================================================================================
class TestAddRemove:
    def test_add_idempotent_keeps_first_origin(self, pz):
        assert pz.add("user_cmd", by="telegram:111", note="ilk") is True
        pz.clock_.advance(3600)
        assert pz.add("user_cmd", by="telegram:222", note="ikinci") is False
        (h,) = pz.holds()
        assert (h.by, h.at, h.note) == ("telegram:111", "2026-12-30T10:00:00Z", "ilk")

    def test_add_idempotent_file_bytes_unchanged_in_holds(self, pz):
        pz.add("manual", by="a")
        before = json.loads(pz.path_.read_text())["holds"]
        pz.clock_.advance(5)
        pz.add("manual", by="b")
        assert json.loads(pz.path_.read_text())["holds"] == before

    def test_two_holds_independent(self, pz):
        assert pz.add("user_cmd", by="telegram:1") is True
        assert pz.add("drawdown_review", by="engine:rk1", note="peak=1 equity=0.8") is True
        assert {h.reason for h in pz.holds()} == {"user_cmd", "drawdown_review"}
        assert pz.remove("user_cmd", by="telegram:1") is True
        assert [h.reason for h in pz.holds()] == ["drawdown_review"]
        assert pz.active() is True
        assert pz.code() == "drawdown_review"
        assert pz.remove("drawdown_review", by="cli") is True
        assert pz.active() is False and not pz.path_.exists()

    def test_remove_other_order(self, pz):
        pz.add("user_cmd", by="a")
        pz.add("late_fill", by="engine:reconcile")
        assert pz.remove("late_fill", by="cli") is True
        assert [h.reason for h in pz.holds()] == ["user_cmd"]

    def test_last_hold_removed_deletes_file(self, pz):
        pz.add("manual", by="a")
        assert pz.path_.exists()
        assert pz.remove("manual", by="a") is True
        assert not pz.path_.exists()
        assert pz.active() is False

    def test_remove_missing_returns_false(self, pz):
        assert pz.remove("user_cmd", by="a") is False
        pz.add("manual", by="a")
        assert pz.remove("user_cmd", by="a") is False
        assert [h.reason for h in pz.holds()] == ["manual"]

    def test_unreadable_hold_cannot_be_removed(self, pz):
        pz.path_.parent.mkdir(parents=True, exist_ok=True)
        pz.path_.write_text("{bozuk")
        assert pz.remove("unreadable", by="cli") is False
        assert pz.path_.exists() and pz.active() is True
        for r in ALL_REASONS:
            pz.remove(r, by="cli")
        assert pz.path_.exists() and pz.active() is True

    def test_unreadable_clears_only_after_manual_fix(self, pz):
        pz.path_.parent.mkdir(parents=True, exist_ok=True)
        pz.path_.write_text("{bozuk")
        assert pz.holds()[0].reason == "unreadable"
        # elle duzeltme: gecerli dosya
        pz.path_.write_text(json.dumps({"schema": "pause/1", "bot": "learner", "holds": [
            {"reason": "manual", "by": "ben", "at": "2026-12-30T10:00:00Z", "note": ""}]}))
        assert [h.reason for h in pz.holds()] == ["manual"]
        # elle silme gecerli acil yoldur
        pz.path_.unlink()
        assert pz.active() is False

    def test_add_invalid_reason_value_error(self, pz):
        with pytest.raises(ValueError):
            pz.add("uydurma", by="x")
        assert not pz.path_.exists()

    def test_remove_invalid_reason_value_error(self, pz):
        # SPEC-AMBIGUOUS: sartname "`reason` REASONS disinda ise ValueError" cumlesini add/remove paragrafinin sonunda
        # soyler; en literal okuma her ikisi icin gecerlidir.
        with pytest.raises(ValueError):
            pz.remove("uydurma", by="x")

    @pytest.mark.parametrize("reason", ALL_REASONS)
    def test_every_declared_reason_accepted(self, pz, reason):
        assert pz.add(reason, by="t") is True

    def test_persists_across_restart(self, pz, tmp_path):
        pz.add("user_cmd", by="telegram:482", note="x")
        pz.add("drawdown_review", by="engine:rk1")
        ep2 = pmod().EntryPause(str(pz.path_), SimClock(TP + timedelta(days=30)))
        assert ep2.active() is True
        assert [(h.reason, h.by, h.at) for h in ep2.holds()] == [
            ("user_cmd", "telegram:482", "2026-12-30T10:00:00Z"),
            ("drawdown_review", "engine:rk1", "2026-12-30T10:00:00Z")]
        assert ep2.code() == "drawdown_review"

    def test_does_not_lapse_with_time(self, pz):
        pz.add("user_cmd", by="a")
        pz.clock_.advance(400 * 86400)
        assert pz.active() is True and pz.code() == "paused"

    def test_file_written_atomically_no_tmp_leftovers(self, pz):
        pz.add("user_cmd", by="a")
        pz.add("manual", by="a")
        leftovers = [p.name for p in pz.path_.parent.iterdir() if p.name not in (pz.path_.name, pz.path_.name + ".lock", "pause_audit.jsonl")]
        assert leftovers == []

    def test_lock_file_name(self, pz):
        # oku-degistir-yaz `f"{path}.lock"` uzerinde flock
        pz.add("user_cmd", by="a")
        assert Path(str(pz.path_) + ".lock").exists()


# =====================================================================================================
# 3. Denetim gunlugu
# =====================================================================================================
class TestAudit:
    def test_add_then_remove_rows(self, pz):
        pz.add("user_cmd", by="telegram:482", note="n")
        pz.clock_.advance(60)
        pz.remove("user_cmd", by="telegram:482")
        rows = audit_rows(pz.tmp)
        assert [r["op"] for r in rows] == ["add", "remove"]
        assert set(rows[0]) >= {"at", "op", "reason", "by", "note"}
        assert rows[0]["reason"] == "user_cmd" and rows[0]["by"] == "telegram:482" and rows[0]["note"] == "n"
        assert rows[0]["at"] == "2026-12-30T10:00:00Z"
        assert rows[1]["at"] == "2026-12-30T10:01:00Z"
        assert rows[1]["reason"] == "user_cmd" and rows[1]["by"] == "telegram:482"

    def test_audit_path_is_var_bot_pause_audit(self, pz):
        pz.add("manual", by="a")
        found = list(pz.tmp.rglob("pause_audit.jsonl"))
        assert len(found) == 1
        # SPEC-AMBIGUOUS: `var/<bot>/pause_audit.jsonl`; EntryPause(path, clock) `var` kokunu bilmedigi icin yalniz
        # dosya adi ve varligi sinanir (konum sartnameden turetilemez).

    def test_each_op_appends_one_line(self, pz):
        pz.add("user_cmd", by="a")
        pz.add("manual", by="a")
        pz.remove("manual", by="a")
        assert len(audit_rows(pz.tmp)) == 3

    def test_audit_is_append_only_jsonl(self, pz):
        pz.add("user_cmd", by="a")
        first = next(pz.tmp.rglob("pause_audit.jsonl")).read_text()
        pz.add("manual", by="a")
        second = next(pz.tmp.rglob("pause_audit.jsonl")).read_text()
        assert second.startswith(first) and len(second) > len(first)

    def test_manual_unlink_leaves_no_audit_trace(self, pz):
        # değişmez (4): elle silme denetim günlüğünde iz bırakmaz
        pz.add("user_cmd", by="a")
        n = len(audit_rows(pz.tmp))
        pz.path_.unlink()
        assert len(audit_rows(pz.tmp)) == n

    def test_invalid_reason_writes_no_audit_row(self, pz):
        with pytest.raises(ValueError):
            pz.add("uydurma", by="a")
        assert audit_rows(pz.tmp) == []
        # SPEC-AMBIGUOUS: idempotent (False donen) `add`'in satir yazip yazmadigi sartnamede yok; test edilmez.


# =====================================================================================================
# 4. Eszamanli yazma (iki surec) kayipsiz
# =====================================================================================================
_WORKER = textwrap.dedent("""
    import sys, time
    from datetime import datetime, timezone
    sys.path.insert(0, {src!r})
    from trader_engine.pause import EntryPause

    class Clk:
        def now(self): return datetime.now(timezone.utc)
        def sleep(self, s): time.sleep(s)

    base, start_at, rounds, role = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    mine = {{"A": ("user_cmd", "manual", "late_fill"),
            "B": ("drawdown_review", "exchange_ban", "exchange_auth", "unknown_position")}}[role]
    for r in range(rounds):
        while time.time() < start_at + r * 0.03:
            pass
        ep = EntryPause(f"{{base}}/PAUSE{{r}}.learner", Clk())
        for reason in mine:
            ep.add(reason, by="proc-" + role)
""")

_CHURN = textwrap.dedent("""
    import sys, time
    from datetime import datetime, timezone
    sys.path.insert(0, {src!r})
    from trader_engine.pause import EntryPause

    class Clk:
        def now(self): return datetime.now(timezone.utc)
        def sleep(self, s): time.sleep(s)

    path, start_at, n, role = sys.argv[1], float(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    while time.time() < start_at:
        pass
    ep = EntryPause(path, Clk())
    if role == "adder":
        for r in ("manual", "late_fill", "exchange_ban", "exchange_auth", "unknown_position"):
            ep.add(r, by="adder")
            time.sleep(0.001)
    else:
        for _ in range(n):
            ep.add("user_cmd", by="churn")
            ep.remove("user_cmd", by="churn")
""")


def _spawn(code: str, *args, cwd):
    return subprocess.Popen([sys.executable, "-I", "-c", code.format(src=str(SRC)), *map(str, args)],
                            cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


class TestConcurrentWrites:
    def test_two_processes_lossless(self, tmp_path):
        base = tmp_path / "shared"
        base.mkdir()
        rounds = 25
        start = time.time() + 1.5
        procs = [_spawn(_WORKER, base, start, rounds, role, cwd=tmp_path) for role in ("A", "B")]
        outs = [p.communicate(timeout=120) for p in procs]
        for p, (o, e) in zip(procs, outs):
            assert p.returncode == 0, e
        expected = set(ALL_REASONS)
        for r in range(rounds):
            ep = pmod().EntryPause(str(base / f"PAUSE{r}.learner"), SimClock(TP))
            got = {h.reason for h in ep.holds()}
            assert got == expected, f"round {r}: kayip tutus {expected - got}"
            doc = json.loads((base / f"PAUSE{r}.learner").read_text())      # dosya bozulmadi
            assert len(doc["holds"]) == 7
        # denetim gunlugu: her satir tam JSON, 7 * rounds ekleme
        rows = audit_rows(tmp_path)
        assert len([x for x in rows if x["op"] == "add"]) == 7 * rounds

    def test_add_not_lost_while_other_process_churns_add_remove(self, tmp_path):
        base = tmp_path / "shared"
        base.mkdir()
        path = base / "PAUSE.learner"
        start = time.time() + 1.5
        procs = [_spawn(_CHURN, path, start, 150, "adder", cwd=tmp_path),
                 _spawn(_CHURN, path, start, 150, "churn", cwd=tmp_path)]
        for p in procs:
            _, e = p.communicate(timeout=120)
            assert p.returncode == 0, e
        ep = pmod().EntryPause(str(path), SimClock(TP))
        reasons = {h.reason for h in ep.holds()}
        assert {"manual", "late_fill", "exchange_ban", "exchange_auth", "unknown_position"} <= reasons
        assert "user_cmd" not in reasons              # son islem remove
        for ln in next(tmp_path.rglob("pause_audit.jsonl")).read_text().splitlines():
            json.loads(ln)                            # yarim satir yok


# =====================================================================================================
# 5. Motor kodunda `remove` yok (AST) — degismez (2)
# =====================================================================================================
def _remove_calls(py: Path) -> list[int]:
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    hits = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and f.attr == "remove":
                if isinstance(f.value, ast.Name) and f.value.id == "os":          # os.remove: dosya sistemi, pause degil
                    continue
                hits.append(n.lineno)
            elif isinstance(f, ast.Name) and f.id == "remove":
                hits.append(n.lineno)
            elif isinstance(f, ast.Name) and f.id == "getattr" and len(n.args) >= 2 \
                    and isinstance(n.args[1], ast.Constant) and n.args[1].value == "remove":
                hits.append(n.lineno)
    return hits


class TestNoRemoveInEngine:
    def test_remove_called_only_in_cli(self):
        offenders = {}
        for py in sorted((SRC / "trader_engine").rglob("*.py")):
            if py.name in ("cli.py",) or py.name == "pause.py":
                continue
            hits = _remove_calls(py)
            if hits:
                offenders[str(py.relative_to(SRC))] = hits
        assert offenders == {}, offenders

    def test_cli_is_the_remove_caller(self):
        # pozitif kontrol: tarayici gercekten cli.py'de bir `remove` cagrisi buluyor (`pause --clear`)
        assert _remove_calls(SRC / "trader_engine" / "cli.py") != []

    def test_engine_gates_status_import_pause_but_never_remove(self):
        for name in ("engine.py", "gates.py", "status.py", "reconcile.py"):
            assert _remove_calls(SRC / "trader_engine" / name) == [], name

    def test_scan_covers_whole_tree(self):
        files = list((SRC / "trader_engine").rglob("*.py"))
        assert any(p.name == "engine.py" for p in files) and len(files) > 15


# =====================================================================================================
# 6. Kapi sirasi ve kodlari + KILL etkilesim tablosu (§9.3), motor duzeyinde
# =====================================================================================================
def penv(tmp_path, **kw):
    # SPEC-AMBIGUOUS: Engine'e EntryPause'un nasil verildigi sartnamede yok (live broker ctor `pause: EntryPause`
    # alir ama Engine imzasi yazilmamis). En literal okuma: Engine, `cfg.pause_file` + "." + `cfg.bot` yolundan kendi
    # EntryPause'unu kurar; test ayni yolu dosya uzerinden surer.
    e = Env(tmp_path, pause_file=str(tmp_path / "shared" / "PAUSE"), **kw)
    e.start()
    e.pause_path = Path(e.cfg.pause_file + "." + e.cfg.bot)
    e.ep = pmod().EntryPause(str(e.pause_path), e.clock)
    return e


@pytest.fixture
def pe(tmp_path):
    e = penv(tmp_path)
    yield e
    e.close()


def one_decision(e, pair=BTC):
    d = [x for x in e.decisions() if x.pair == pair]
    assert len(d) >= 1
    return d[-1]


class TestGateOrderAndCodes:
    def test_paused_gate_code_and_verdict(self, pe):
        pe.ep.add("user_cmd", by="telegram:482")
        pe.signal(TE)
        pe.decide(TE)
        d = pe.decisions()
        assert len(d) == 1 and d[0].skip_reason == "entry_gate_closed" and d[0].veto_reason == "gate:paused"
        assert d[0].veto_status == "not_evaluated" and d[0].final_action == "skipped"
        assert pe.pos(BTC) is None and pe.broker.counts["market_order"] == 0

    def test_drawdown_review_gate_code(self, pe):
        pe.ep.add("drawdown_review", by="engine:rk1", note="peak=1100 equity=870")
        pe.signal(TE)
        pe.decide(TE)
        d = pe.decisions()
        assert len(d) == 1 and d[0].skip_reason == "entry_gate_closed" and d[0].veto_reason == "gate:drawdown_review"
        assert pe.pos(BTC) is None

    @pytest.mark.parametrize("reason", [r for r in ALL_REASONS if r not in ("drawdown_review",)])
    def test_other_reasons_all_gate_paused(self, pe, reason):
        pe.ep.add(reason, by="x")
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).veto_reason == "gate:paused"

    def test_corrupt_file_closes_gate_as_paused(self, pe):
        pe.pause_path.parent.mkdir(parents=True, exist_ok=True)
        pe.pause_path.write_text("{bozuk")
        pe.signal(TE)
        pe.decide(TE)
        d = one_decision(pe)
        assert d.skip_reason == "entry_gate_closed" and d.veto_reason == "gate:paused"
        assert pe.pos(BTC) is None

    def test_no_pause_entry_allowed(self, pe):
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).final_action == "entered"

    # -- sira: params_unavailable -> trigger_tf_changed -> defter -> entries_blocked_reason -> kill -> pause -> stale
    def test_params_unavailable_before_pause(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.ledger.fail_params = True
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).veto_reason == "gate:params_unavailable"

    def test_ledger_gate_before_pause(self, pe):
        from trader_core import ledger as L
        pe.ep.add("user_cmd", by="a")
        pe.ledger.health = L.Health(False, "degraded", "x")
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).veto_reason == "gate:degraded"

    def test_entries_blocked_reason_before_pause(self, pe):
        pe.ep.add("user_cmd", by="a")
        _hold_block(pe, "order_unknown")
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).veto_reason == "gate:order_unknown"

    def test_kill_before_pause(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.kill.set("t", "t")
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).veto_reason == "gate:kill"

    def test_pause_before_stale_data(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.signal(TE)
        pe.decide(TE, now=TE + timedelta(minutes=90))              # bayat veri, ama duraklatma once gelir
        d = pe.decisions()
        assert len(d) == 1 and d[0].veto_reason == "gate:paused" and d[0].skip_reason == "entry_gate_closed"

    def test_stale_without_pause_still_stale(self, pe):
        pe.signal(TE)
        pe.decide(TE, now=TE + timedelta(minutes=90))
        d = pe.decisions()
        assert d[0].veto_reason == "gate:stale_data" and d[0].skip_reason == "other"

    def test_decision_marked_decided_like_other_gates(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.signal(TE)
        pe.decide(TE)
        assert pe.state.is_decided(BTC, TE)


class TestKillInteractionTable:
    """§9.3 tablosu: alti satir."""

    # satir 1: yalniz duraklatma -> giris yok; pozisyonlar yasar
    def test_row1_pause_only_entries_closed_positions_live(self, pe):
        p = pe.open_pos(BTC, TE)
        assert p is not None and p.status == "open"
        pe.ep.add("user_cmd", by="telegram:482")
        pe.step(TE + M1)
        pe.step(TE + 2 * M1)
        D1 = TE + H
        pe.signal(D1, (ETH,))
        pe.decide(D1)
        assert one_decision(pe, ETH).veto_reason == "gate:paused" and pe.pos(ETH) is None
        assert pe.pos(BTC).status == "open"
        assert [r for r in pe.broker.log if r[1] == "exit"] == []

    def test_row1_exits_still_run_while_paused(self, pe):
        pe.open_pos(BTC, TE)
        pe.ep.add("user_cmd", by="telegram:482")
        D1 = TE + H
        pe.src.ctx[(BTC, D1)] = flip_ctx(D1)
        pe.signal(D1, (ETH,))
        pe.decide(D1)
        p = pe.pos(BTC)
        assert p.status == "closing" and p.exit_reason == "regime_flip"      # normal cikis kurallari surer
        assert pe.pos(ETH) is None and one_decision(pe, ETH).veto_reason == "gate:paused"

    # satir 2: yalniz KILL -> giris yok; pozisyonlar kapatilir
    def test_row2_kill_only(self, pe):
        pe.open_pos(BTC, TE)
        pe.kill.set("t", "t")
        pe.step(TE + M1)
        assert pe.pos(BTC).status == "closing" and pe.pos(BTC).exit_reason == "force_exit"
        pe.signal(TE + H, (ETH,))
        pe.decide(TE + H)
        assert one_decision(pe, ETH).veto_reason == "gate:kill"

    # satir 3: ikisi birden -> KILL davranisi; kapi kodu `kill`
    def test_row3_both_kill_behaviour_and_code_kill(self, pe):
        pe.open_pos(BTC, TE)
        pe.ep.add("user_cmd", by="a")
        pe.kill.set("t", "t")
        pe.step(TE + M1)
        assert pe.pos(BTC).status == "closing" and pe.pos(BTC).exit_reason == "force_exit"
        pe.signal(TE + H, (ETH,))
        pe.decide(TE + H)
        assert one_decision(pe, ETH).veto_reason == "gate:kill"

    def test_row3_both_status_gate_code_kill(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.kill.set("t", "t")
        pe.step(TE + M1)
        pe.status.write(pe.engine)
        st = json.loads(Path(pe.cfg.status_path).read_text())
        assert st["gate"] == {"ok": False, "code": "kill"} and st["entries_open"] is False

    # satir 4: KILL kaldirildi, duraklatma duruyor -> giris HALA kapali
    def test_row4_kill_cleared_pause_remains_entries_closed(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.kill.set("t", "t")
        pe.signal(TE)
        pe.decide(TE)
        pe.kill.clear()
        D1 = TE + H
        pe.signal(D1)
        pe.decide(D1)
        ds = pe.decisions()
        assert ds[0].veto_reason == "gate:kill" and ds[1].veto_reason == "gate:paused"
        assert pe.pos(BTC) is None
        assert pe.ep.active() is True                  # KILL duraklatmayi KALDIRMAZ

    # satir 5: duraklatma kaldirildi, KILL duruyor -> giris hala kapali
    def test_row5_pause_removed_kill_remains_entries_closed(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.kill.set("t", "t")
        pe.ep.remove("user_cmd", by="cli")             # test dosyasi motor degil: kaldirmak serbest
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).veto_reason == "gate:kill"
        assert pe.kill.active() is True               # duraklatma KILL'i KALDIRMAZ
        assert pe.pos(BTC) is None

    def test_row5_then_kill_cleared_entries_open(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.kill.set("t", "t")
        pe.ep.remove("user_cmd", by="cli")
        pe.kill.clear()
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).final_action == "entered"

    # satir 6: birden cok tutus -> hepsi kalkana kadar kapali; biri kalkinca digerleri etkilenmez
    def test_row6_multiple_holds_closed_until_all_removed(self, pe):
        pe.ep.add("user_cmd", by="telegram:482")
        pe.ep.add("drawdown_review", by="engine:rk1", note="peak=1 equity=0.8")
        pe.signal(TE)
        pe.decide(TE)
        assert one_decision(pe).veto_reason == "gate:drawdown_review"
        pe.ep.remove("drawdown_review", by="cli")
        D1 = TE + H
        pe.signal(D1)
        pe.decide(D1)
        assert pe.decisions()[-1].veto_reason == "gate:paused"
        assert [h.reason for h in pe.ep.holds()] == ["user_cmd"]          # digeri etkilenmedi
        pe.ep.remove("user_cmd", by="telegram:482")
        D2 = TE + 2 * H
        pe.signal(D2)
        pe.decide(D2)
        assert pe.decisions()[-1].final_action == "entered"


class TestNeverSelfClears:
    def test_survives_engine_restart_and_time(self, tmp_path):
        e = penv(tmp_path)
        e.ep.add("user_cmd", by="telegram:482")
        e.engine.shutdown("test")
        e.close()
        e2 = penv(tmp_path)               # ayni dizin: yeniden baslatma
        try:
            assert e2.ep.active() is True and [h.reason for h in e2.ep.holds()] == ["user_cmd"]
            e2.set_clock(TE + timedelta(days=3))
            e2.signal(TE + timedelta(days=3))
            e2.decide(TE + timedelta(days=3))
            assert one_decision(e2).veto_reason == "gate:paused"
            assert e2.ep.active() is True
        finally:
            e2.close()

    def test_reconcile_clean_does_not_clear_holds(self, pe):
        pe.ep.add("late_fill", by="engine:reconcile")
        pe.ep.add("user_cmd", by="telegram:482")
        pe.engine.reconciler.run(pe.clock.now())
        pe.step(TE + M1)
        assert {h.reason for h in pe.ep.holds()} == {"late_fill", "user_cmd"}

    def test_entries_blocked_reason_clearing_does_not_touch_pause(self, pe):
        pe.ep.add("user_cmd", by="a")
        _hold_block(pe, "order_unknown")
        with pe.state.tx():
            pe.state.kv_set("entries_blocked_reason", None)          # motorun kendi blokaj temizligi
        assert pe.ep.active() is True

    def test_equity_recovery_does_not_clear(self, pe):
        pe.ep.add("drawdown_review", by="engine:rk1", note="peak=1100 equity=870")
        for i in range(1, 6):
            pe.step(TE + i * M1, price=100.0 + i)
        assert pe.ep.active() is True and pe.ep.code() == "drawdown_review"


class TestStatusFields:
    def test_status_pause_block_inactive(self, pe):
        pe.status.write(pe.engine)
        st = json.loads(Path(pe.cfg.status_path).read_text())
        assert st["pause"] == {"active": False, "holds": []}

    def test_status_pause_block_with_holds_and_gate(self, pe):
        pe.ep.add("user_cmd", by="telegram:482")
        pe.ep.add("drawdown_review", by="engine:rk1", note="peak=1 equity=0.8")
        pe.status.write(pe.engine)
        st = json.loads(Path(pe.cfg.status_path).read_text())
        assert st["pause"]["active"] is True
        # SPEC-AMBIGUOUS: `holds` ogelerinin alan adlari (PauseHold alanlari: reason/by/at/note) varsayildi
        assert [h["reason"] for h in st["pause"]["holds"]] == ["user_cmd", "drawdown_review"]
        assert st["pause"]["holds"][0]["by"] == "telegram:482"
        assert st["gate"] == {"ok": False, "code": "drawdown_review"} and st["entries_open"] is False

    def test_status_paused_code(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.status.write(pe.engine)
        st = json.loads(Path(pe.cfg.status_path).read_text())
        assert st["gate"] == {"ok": False, "code": "paused"}
        assert st["entries_blocked_reason"] is None              # duraklatma entries_blocked_reason'u kullanmaz

    def test_pause_does_not_set_entries_blocked_reason(self, pe):
        pe.ep.add("user_cmd", by="a")
        pe.signal(TE)
        pe.decide(TE)
        assert pe.state.kv_get("entries_blocked_reason") in (None, "")


# =====================================================================================================
# 7. CLI: `pause` alt komutu (§9.5)
# =====================================================================================================
def _cli_dir(tmp: Path) -> Path:
    cfgd = tmp / "cfg"
    cfgd.mkdir()
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(var_dir=str(tmp / "var"), market_db=str(tmp / "market.sqlite"), history_dir=str(tmp / "hist"), kill_file=str(tmp / "KILL"),
               pause_file=str(tmp / "shared" / "PAUSE"), target_trade_risk=0.014)
    (cfgd / "engine.base.json").write_text(json.dumps(raw))
    (cfgd / "engine.learner.json").write_text(json.dumps({"bot": "learner"}))
    (cfgd / "engine.twin.json").write_text(json.dumps({"bot": "twin"}))
    return cfgd


def _run_cli(argv):
    cli = importlib.import_module("trader_engine.cli")
    return int(cli.main(argv))


class TestCli:
    def test_pause_set_creates_hold_for_that_bot_only(self, tmp_path):
        cfgd = _cli_dir(tmp_path)
        rc = _run_cli(["pause", "--bot", "learner", "--reason", "manual", "--by", "ben", "--note", "bakim",
                       "--config-dir", str(cfgd)])
        assert rc == 0
        ep = pmod().EntryPause(str(tmp_path / "shared" / "PAUSE.learner"), SimClock(TP))
        (h,) = ep.holds()
        assert (h.reason, h.by, h.note) == ("manual", "ben", "bakim")
        assert not (tmp_path / "shared" / "PAUSE.twin").exists()           # ikiz etkilenmez

    def test_pause_default_reason_manual(self, tmp_path):
        cfgd = _cli_dir(tmp_path)
        assert _run_cli(["pause", "--bot", "learner", "--config-dir", str(cfgd)]) == 0
        ep = pmod().EntryPause(str(tmp_path / "shared" / "PAUSE.learner"), SimClock(TP))
        assert [h.reason for h in ep.holds()] == ["manual"]

    def test_pause_clear_removes_only_named_reason(self, tmp_path):
        cfgd = _cli_dir(tmp_path)
        path = tmp_path / "shared" / "PAUSE.learner"
        ep = pmod().EntryPause(str(path), SimClock(TP))
        ep.add("drawdown_review", by="engine:rk1")
        ep.add("manual", by="ben")
        rc = _run_cli(["pause", "--bot", "learner", "--clear", "--reason", "drawdown_review", "--by", "ben",
                       "--config-dir", str(cfgd)])
        assert rc == 0
        assert [h.reason for h in ep.holds()] == ["manual"]
        rows = audit_rows(tmp_path)
        assert any(r["op"] == "remove" and r["reason"] == "drawdown_review" and r["by"] == "ben" for r in rows)

    def test_pause_list(self, tmp_path, capsys):
        cfgd = _cli_dir(tmp_path)
        ep = pmod().EntryPause(str(tmp_path / "shared" / "PAUSE.learner"), SimClock(TP))
        ep.add("user_cmd", by="telegram:482")
        capsys.readouterr()
        # SPEC-AMBIGUOUS: `--list` ciktisinin bicimi yok; yalniz neden ve `by` degerlerinin stdout'ta gectigine bakilir.
        rc = _run_cli(["pause", "--bot", "learner", "--list", "--config-dir", str(cfgd)])
        out = capsys.readouterr().out
        assert rc == 0 and "user_cmd" in out and "telegram:482" in out
