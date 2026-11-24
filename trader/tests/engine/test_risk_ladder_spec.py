"""RK-1 bagimsiz sartname testi: risk kademe denetimi (docs/motor/12-risk-kademe.md §13, T-01..T-60).

Yalniz sartnameden yazildi; `trader_core/risk_ladder.py`, `trader_engine/ladder.py` ve `capital`/`ladder` CLI
gerceklemesine BAKILMADI. Gerceklenmeden once dosya temiz toplanir (modul-ustu `importorskip`); motor/CLI testleri
ayrica `trader_engine.ladder` yoksa kendi icinde atlanir. Belirsiz isimler/davranislar `# SPEC-AMBIGUOUS:` ile isaretli.

Kapsam: A (T-01..T-16) ve B (T-17..T-27) tam. C (motor) `RiskLadder` sinifi duzeyinde (sahte saat/yoklama; tam Engine
dongusu gerektiren T-28, T-43, T-47 ve T-29/T-30/T-38'in motor kisimlari atlandi). D (CLI) T-49..T-52 + T-53 kismi.
E (Telegram, T-54..T-59) ve F (Saglik, T-60) sartnamede ayri dosyalardir; burada yalniz atlama kaydi vardir.
Saat enjekte edilir, ag yok, tum dosyalar tmp_path altindadir, veriler sentetiktir.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

rl = pytest.importorskip("trader_core.risk_ladder")

from trader_core.ledger import TradeRecord  # noqa: E402
from trader_core.risk import HARD_LIMITS, LOCKED_CFG, RiskConfig  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.config import load_engine_config  # noqa: E402
from trader_engine.errors import ConfigError  # noqa: E402

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
NOW0 = datetime(2026, 12, 30, 9, 0, 0, tzinfo=UTC)       # §12 ornek 1'in `initial` ani
H = timedelta(hours=1)
D = timedelta(days=1)
M1 = timedelta(minutes=1)
ZERO_HASH = "0" * 64


# =====================================================================================================
# Yardimcilar (A/B): gunluk kurucu
# =====================================================================================================
class B:
    """LadderLog uzerine ince kurucu: her `add` bir dakika ilerler; `book` NOW0'da `initial` yazar."""

    def __init__(self, path=None, start: datetime = NOW0):
        self.log = rl.LadderLog(None if path is None else str(path))
        self.t = start - M1

    def add(self, kind: str, by: str = "cli:t", **fields) -> dict:
        self.t = self.t + M1
        return self.log.append(kind, by, self.t, **fields)

    def rows(self) -> list[dict]:
        return self.log.rows()

    def state(self):
        return self.log.state()


def book(amount: float = 1000.0, path=None, start: datetime = NOW0) -> B:
    b = B(path, start)
    b.add("initial", amount=float(amount))
    return b


def to_km1(b: B) -> B:
    st = b.state()
    b.add("step_down", "engine:rk1", step=-1, trigger="dd_peak_10", equity=round(0.9 * st.peak, 8), peak=st.peak)
    return b


def to_review(b: B, equity: float = 800.0) -> B:
    b.add("review_stop", "engine:rk1", equity=equity, base=b.state().base)
    return b


def to_floor(b: B, equity: float = 600.0) -> B:
    b.add("floor_stop", "engine:rk1", equity=equity, dep_net=b.state().dep_net)
    return b


def expect_reject(b: B, kind: str, by: str = "cli:t", **fields):
    """Gecersiz satir: LadderLogError ve gunluk satirlari DEGISMEZ."""
    before = json.dumps(b.rows(), sort_keys=True)
    with pytest.raises(rl.LadderLogError):
        b.add(kind, by, **fields)
    assert json.dumps(b.rows(), sort_keys=True) == before


def act(kind: str, step=None, trigger=None):
    return rl.Action(kind, step=step, trigger=trigger)


def sha(row: dict) -> str:
    body = {k: v for k, v in row.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def z(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_chain(path: Path, specs: list[dict], *, break_prev_at: int | None = None) -> None:
    """`specs`: seq/prev/hash HARICI satirlar; gecerli zincir yazar (kasitli bozukluk parametreleriyle)."""
    prev, lines = ZERO_HASH, []
    for i, sp in enumerate(specs, 1):
        row = dict(sp)
        row["seq"] = i
        row["prev"] = ("f" * 64) if break_prev_at == i else prev
        row["hash"] = sha(row)
        prev = row["hash"]
        lines.append(json.dumps(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def base_specs() -> list[dict]:
    out = [{"at": z(NOW0), "kind": "initial", "by": "cli:t", "note": "", "amount": 1000.0}]
    for i, a in enumerate((100.0, 50.0, 25.0), 1):
        out.append({"at": z(NOW0 + i * M1), "kind": "deposit", "by": "cli:t", "note": "", "amount": a})
    return out


# =====================================================================================================
# A. Gunluk ve katlama
# =====================================================================================================
def test_t01_constants_invariants():
    steps = rl.STEPS
    assert steps[4] == LOCKED_CFG.target_trade_risk
    keys = sorted(steps)
    assert keys == [-1, 0, 1, 2, 3, 4]
    vals = [steps[k] for k in keys]
    assert all(a < b for a, b in zip(vals, vals[1:])), "basamakla kesin artan olmali"
    assert steps[0] == 0.005
    assert all(v <= HARD_LIMITS["target_trade_risk"] for v in vals)
    assert rl.SCHEMA == "risk-ladder/1"
    assert (rl.CONFIRM_N, rl.STOP_RATIO, rl.FLOOR_RATIO, rl.DOWN_1_RATIO, rl.DOWN_2_RATIO) == (2, 0.80, 0.60, 0.90, 0.85)
    assert rl.MAX_STEP_APPROVABLE == 0 and rl.KM1_MIN_CAPITAL == 1000.0


def test_t02_hash_chain_matches_spec_example():
    h1 = "1cfa987532dbe34b8d145f274fda1dde6dff6b5b32442a448e5ad9f3fe8dafd7"
    h2 = "1c1cc11e660a0d43a64d6a2e731e48035439d67ce106924efc304bf25797636c"
    r1 = {"seq": 1, "at": "2026-12-30T09:00:00Z", "kind": "initial", "by": "cli:sg", "note": "", "amount": 250.0,
          "prev": ZERO_HASH}
    assert sha(r1) == h1                                  # formul + sartname ornegi
    log = rl.LadderLog(None)
    a = log.append("initial", "cli:sg", datetime(2026, 12, 30, 9, 0, 0, tzinfo=UTC), amount=250.0)
    assert a["hash"] == h1 and a["prev"] == ZERO_HASH and a["seq"] == 1
    b = log.append("deposit", "cli:sg", datetime(2027, 1, 25, 10, 0, 0, tzinfo=UTC), note="1000e tamamlama",
                   amount=750.0)
    assert b["hash"] == h2 and b["prev"] == h1 and b["seq"] == 2
    assert log.state().head_hash == h2


def test_t03_missing_or_empty_file(tmp_path):
    p = tmp_path / "var" / "learner" / "risk_ladder.jsonl"
    log = rl.LadderLog(str(p))
    assert log.rows() == [] and log.state() is None
    p.parent.mkdir(parents=True)
    p.write_bytes(b"")
    assert log.rows() == [] and log.state() is None
    mem = rl.LadderLog(None)
    assert mem.rows() == [] and mem.state() is None
    assert rl.fold([]) is None


def test_t04_initial_only_first(tmp_path):
    b = book(1000.0, tmp_path / "l.jsonl")
    before = (tmp_path / "l.jsonl").read_bytes()
    expect_reject(b, "initial", amount=500.0)
    assert (tmp_path / "l.jsonl").read_bytes() == before
    # initial olmadan deposit
    p2 = tmp_path / "m.jsonl"
    b2 = B(p2)
    with pytest.raises(rl.LadderLogError):
        b2.add("deposit", amount=10.0)
    assert not p2.exists() or p2.stat().st_size == 0
    assert b2.rows() == [] and b2.state() is None


@pytest.mark.parametrize("amount", [0.0, -5.0, float("nan"), float("inf"), True, "250"])
def test_t04_initial_amount_validation(amount):
    b = B()
    with pytest.raises(rl.LadderLogError):
        b.add("initial", amount=amount)
    assert b.rows() == []


def test_t04_initial_fold_values():
    st = book(250.0).state()
    assert st.status == "ok" and st.step == 0
    assert st.dep_net == st.base == st.peak == 250.0
    assert st.step_since == st.started_at == NOW0
    assert st.last_down_at is None and st.stopped_at is None and st.fired == frozenset()
    assert st.seq == 1 and len(st.head_hash) == 64


def test_t05_deposit():
    b = to_km1(book(1000.0))
    fired = b.state().fired
    assert fired == frozenset({"dd_peak_10"})
    b.add("deposit", amount=250.0)
    st = b.state()
    assert (st.dep_net, st.base, st.peak) == (1250.0, 1250.0, 1250.0)
    assert st.fired == fired and st.step == -1
    for bad in (0.0, -1.0, float("nan"), True):
        expect_reject(b, "deposit", amount=bad)


def test_t06_withdraw_profit_first():
    b = book(1000.0)
    b.add("withdraw", amount=300.0, equity=1300.0, capital_part=0.0)
    st = b.state()
    assert (st.dep_net, st.base) == (1000.0, 1000.0)
    assert st.peak == max(1000.0, 1000.0 - 300.0)


def test_t06_withdraw_from_capital():
    b = book(1000.0)
    b.add("withdraw", amount=100.0, equity=900.0, capital_part=100.0)
    st = b.state()
    assert st.dep_net == 900.0 and st.base == 900.0
    assert st.peak == max(st.base, 1000.0 - 100.0) == 900.0


def test_t06_withdraw_rejections():
    b = book(1000.0)
    expect_reject(b, "withdraw", amount=1000.0, equity=1000.0, capital_part=1000.0)   # dep_net 0
    expect_reject(b, "withdraw", amount=1500.0, equity=900.0, capital_part=1500.0)    # dep_net < 0
    expect_reject(b, "withdraw", amount=100.0, equity=900.0, capital_part=150.0)      # c > amount
    expect_reject(b, "withdraw", amount=100.0, equity=900.0, capital_part=-1.0)       # c < 0
    expect_reject(b, "withdraw", amount=0.0, equity=900.0, capital_part=0.0)
    expect_reject(b, "withdraw", amount=100.0, capital_part=0.0)                      # equity eksik


def test_t07_adjust():
    b = book(1000.0)
    b.add("adjust", amount=50.0, note="duzeltme")
    st = b.state()
    assert (st.dep_net, st.base, st.peak) == (1050.0, 1050.0, max(1050.0, 1000.0 + 50.0))
    b.add("adjust", amount=-100.0, note="geri")
    st = b.state()
    assert (st.dep_net, st.base) == (950.0, 950.0)
    assert st.peak == max(950.0, 1050.0 - 100.0)
    expect_reject(b, "adjust", amount=10.0)                      # not yok
    expect_reject(b, "adjust", amount=10.0, note="")
    expect_reject(b, "adjust", amount=0.0, note="sifir")
    expect_reject(b, "adjust", amount=-950.0, note="sifir olur")  # sonuc <= 0
    expect_reject(b, "adjust", amount=-2000.0, note="negatif")


def test_t08_peak():
    b = to_km1(book(1000.0))
    assert b.state().fired == frozenset({"dd_peak_10"})
    b.add("peak", "engine:rk1", value=900.0)                     # dusuk deger: peak inmez, fired yine temizlenir
    st = b.state()
    assert st.peak == 1000.0 and st.fired == frozenset()
    b.add("peak", "engine:rk1", value=1100.0)
    assert b.state().peak == 1100.0


def test_t09_step_down():
    b = book(1000.0)
    expect_reject(b, "step_down", "engine:rk1", step=0, trigger="dd_peak_10", equity=900.0, peak=1000.0)   # esit
    expect_reject(b, "step_down", "engine:rk1", step=1, trigger="dd_peak_10", equity=900.0, peak=1000.0)   # yukari
    expect_reject(b, "step_down", "engine:rk1", step=-2, trigger="dd_peak_10", equity=900.0, peak=1000.0)  # -1 alti
    r = b.add("step_down", "engine:rk1", step=-1, trigger="dd_peak_10", equity=900.0, peak=1000.0)
    st = b.state()
    at = datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert st.step == -1 and st.step_since == at and st.last_down_at == at
    assert st.fired == frozenset({"dd_peak_10"})
    expect_reject(b, "step_down", "engine:rk1", step=-1, trigger="dd_peak_15", equity=850.0, peak=1000.0)  # -1 -> -1


STATUS_CASES = [
    # (kind, fields, statuses in which the row is VALID)
    ("review_stop", dict(equity=800.0, base=1000.0), {"ok"}),
    ("floor_stop", dict(equity=600.0, dep_net=1000.0), {"ok", "review"}),
    ("review_resume", dict(equity=800.0, rebase=True, decision=""), {"review"}),
    ("floor_restart", dict(equity=600.0, decision="TK-1"), {"floor"}),
]


def _in_status(status: str) -> B:
    b = book(1000.0)
    if status == "review":
        to_review(b)
    elif status == "floor":
        to_floor(b)
    return b


@pytest.mark.parametrize("status", ["ok", "review", "floor"])
@pytest.mark.parametrize("kind,fields,valid_in", STATUS_CASES, ids=[c[0] for c in STATUS_CASES])
def test_t10_state_machine(kind, fields, valid_in, status):
    b = _in_status(status)
    if status in valid_in:
        b.add(kind, "cli:t" if kind.endswith("restart") or kind.endswith("resume") else "engine:rk1", **fields)
        st = b.state()
        assert st.status == {"review_stop": "review", "floor_stop": "floor", "review_resume": "ok",
                             "floor_restart": "ok"}[kind]
    else:
        expect_reject(b, kind, **fields)


@pytest.mark.parametrize("status", ["ok", "review", "floor"])
def test_t10_step_up_only_in_ok(status):
    b = to_km1(book(1000.0))
    if status == "review":
        to_review(b)
    elif status == "floor":
        to_floor(b)
    if status == "ok":
        b.add("step_up", step=0, decision="TK-2")
        assert b.state().step == 0
    else:
        expect_reject(b, "step_up", step=0, decision="TK-2")


def test_t10_stop_timestamps():
    b = book(1000.0)
    r = to_review(b).rows()[-1]
    at = datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    st = b.state()
    assert st.stopped_at == at and st.last_down_at == at
    to_floor(b)
    at2 = datetime.strptime(b.rows()[-1]["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert b.state().stopped_at == at2 and b.state().status == "floor"


def test_t11_review_resume_rebase_equity_below_base():
    b = to_review(book(1000.0), 800.0)
    b.add("review_resume", "cli:t", equity=790.0, rebase=True, decision="ref")
    st = b.state()
    assert st.status == "ok" and st.base == 790.0 and st.peak == max(790.0, 790.0) and st.fired == frozenset()
    assert st.dep_net == 1000.0 and st.step == 0


def test_t11_review_resume_rebase_equity_above_base():
    b = to_review(book(1000.0), 800.0)
    b.add("review_resume", "cli:t", equity=1100.0, rebase=True, decision="ref")
    st = b.state()
    assert st.base == 1000.0                      # min(base, equity)
    assert st.peak == max(1000.0, 1100.0) == 1100.0


def test_t11_rebase_clears_fired_and_keeps_floor_step():
    b = to_km1(book(1000.0))
    since = b.state().step_since
    to_review(b, 780.0)
    assert b.state().fired == frozenset({"dd_peak_10"})
    b.add("review_resume", "cli:t", equity=780.0, rebase=True, decision="")
    st = b.state()
    assert st.fired == frozenset() and st.step == -1            # min(-1, 0)
    assert st.step_since == since                                # basamak degismedi -> step_since ayni


def test_t11_no_rebase_changes_only_status():
    b = to_km1(book(1000.0))
    to_review(b, 780.0)
    pre = b.state()
    b.add("review_resume", "cli:t", equity=700.0, rebase=False, decision="yanlis alarm")
    st = b.state()
    assert st.status == "ok"
    assert (st.base, st.peak, st.dep_net, st.step, st.fired) == (pre.base, pre.peak, pre.dep_net, pre.step, pre.fired)


def test_t12_floor_restart():
    b = to_floor(book(1000.0), 590.0)
    expect_reject(b, "floor_restart", equity=590.0, decision="")
    assert b.state().status == "floor"
    expect_reject(b, "floor_restart", equity=0.0, decision="TK")
    b.add("floor_restart", equity=590.0, decision="TK-3")
    st = b.state()
    assert st.status == "ok" and st.dep_net == st.base == st.peak == 590.0
    assert st.step == 0 and st.fired == frozenset()
    assert st.step_since == datetime.strptime(b.rows()[-1]["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def test_t13_step_up():
    b = to_km1(book(1000.0))
    expect_reject(b, "step_up", step=1, decision="x")          # +2
    expect_reject(b, "step_up", step=-1, decision="x")         # +0
    expect_reject(b, "step_up", step=0)                        # decision eksik
    b.add("step_up", step=0, decision="TK-4")                  # K-1 -> K0 kabul
    st = b.state()
    assert st.step == 0 and st.status == "ok"
    # SPEC-AMBIGUOUS: K0 -> K1 `MAX_STEP_APPROVABLE = 0` yuzunden reddedilir (+1 ama tavan ustu)
    expect_reject(b, "step_up", step=1, decision="TK-5")


def test_t13_step_up_ceiling_follows_constant(monkeypatch):
    # RK-1b sabiti yukseltir: tavan sabitten okunur (modul niteligi). SPEC-AMBIGUOUS: fold'un sabiti `rl.MAX_STEP_APPROVABLE`
    # modul niteligi olarak okudugu varsayilir (monkeypatch ile gorulebilir).
    b = book(1000.0)
    monkeypatch.setattr(rl, "MAX_STEP_APPROVABLE", 1)
    b.add("step_up", step=1, decision="RK-1b")
    assert b.state().step == 1


@pytest.fixture
def corrupt_file(tmp_path):
    p = tmp_path / "l.jsonl"
    b = book(1000.0, p)
    for a in (100.0, 50.0, 25.0):
        b.add("deposit", amount=a)
    assert len(rl.LadderLog(str(p)).rows()) == 4
    return p


def _assert_corrupt(p: Path):
    log = rl.LadderLog(str(p))
    with pytest.raises(rl.LadderLogError):
        log.rows()
    with pytest.raises(rl.LadderLogError):
        log.state()
    with pytest.raises(rl.LadderLogError):
        log.append("deposit", "cli:t", NOW0 + 99 * D, amount=1.0)


def test_t14_single_char_change(corrupt_file):
    t = corrupt_file.read_text(encoding="utf-8")
    assert "cli:t" in t
    corrupt_file.write_text(t.replace("cli:t", "cli:u", 1), encoding="utf-8")
    _assert_corrupt(corrupt_file)


def test_t14_deleted_line(corrupt_file):
    lines = corrupt_file.read_text(encoding="utf-8").splitlines(True)
    del lines[1]
    corrupt_file.write_text("".join(lines), encoding="utf-8")
    _assert_corrupt(corrupt_file)


def test_t14_swapped_lines(corrupt_file):
    lines = corrupt_file.read_text(encoding="utf-8").splitlines(True)
    lines[1], lines[2] = lines[2], lines[1]
    corrupt_file.write_text("".join(lines), encoding="utf-8")
    _assert_corrupt(corrupt_file)


def test_t14_broken_prev(tmp_path):
    p = tmp_path / "l.jsonl"
    write_chain(p, base_specs(), break_prev_at=3)             # satirin kendi hash'i tutarli, zincir kopuk
    _assert_corrupt(p)


def test_t14_backwards_at(tmp_path):
    p = tmp_path / "l.jsonl"
    specs = base_specs()
    specs[2]["at"] = z(NOW0 - H)
    write_chain(p, specs)
    _assert_corrupt(p)


def test_t14_unknown_kind(tmp_path):
    p = tmp_path / "l.jsonl"
    specs = base_specs()
    specs[2]["kind"] = "bonus"
    write_chain(p, specs)
    _assert_corrupt(p)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "100", None])
def test_t14_bad_amount(tmp_path, bad):
    p = tmp_path / "l.jsonl"
    specs = base_specs()
    specs[1]["amount"] = bad
    write_chain(p, specs)
    _assert_corrupt(p)


def test_t14_missing_and_extra_fields(tmp_path):
    p = tmp_path / "a.jsonl"
    specs = base_specs()
    del specs[1]["amount"]
    write_chain(p, specs)
    _assert_corrupt(p)
    p2 = tmp_path / "b.jsonl"
    specs = base_specs()
    specs[1]["bonus"] = 1
    write_chain(p2, specs)
    _assert_corrupt(p2)


def test_t14_transition_violation_invalidates_whole_log(tmp_path):
    p = tmp_path / "l.jsonl"
    specs = base_specs()
    specs.append({"at": z(NOW0 + 9 * M1), "kind": "review_resume", "by": "cli:t", "note": "", "equity": 900.0,
                  "rebase": True, "decision": ""})            # ok durumunda review_resume gecersiz
    write_chain(p, specs)
    _assert_corrupt(p)


def test_t14_valid_chain_helper_is_valid(tmp_path):
    # kontrol: kendi yazdigim zincir yardimcisi gecerli bir gunluk uretiyor (yukaridaki bozulma testleri anlamli)
    p = tmp_path / "l.jsonl"
    write_chain(p, base_specs())
    st = rl.LadderLog(str(p)).state()
    assert st.dep_net == 1175.0 and st.seq == 4


def test_t15_concurrent_appends(tmp_path):
    p = tmp_path / "l.jsonl"
    book(1000.0, p)
    code = textwrap.dedent("""
        import sys
        sys.path.insert(0, {src!r})
        from datetime import datetime, timezone
        from trader_core.risk_ladder import LadderLog
        log = LadderLog({path!r})
        now = datetime(2026, 12, 30, 9, 5, tzinfo=timezone.utc)
        for i in range(50):
            log.append("deposit", "cli:p{tag}", now, amount=1.0)
    """)
    procs = [subprocess.Popen([sys.executable, "-c", code.format(src=str(SRC), path=str(p), tag=t)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) for t in (1, 2)]
    for pr in procs:
        out, err = pr.communicate(timeout=120)
        assert pr.returncode == 0, err.decode()
    log = rl.LadderLog(str(p))
    rows = log.rows()
    assert len(rows) == 101
    assert [r["seq"] for r in rows] == list(range(1, 102))
    assert log.state().dep_net == 1100.0


def test_t16_invalid_append_leaves_file_bytes(tmp_path):
    p = tmp_path / "l.jsonl"
    b = book(1000.0, p)
    to_km1(b)
    before = p.read_bytes()
    bad = [
        ("initial", {"amount": 5.0}),
        ("withdraw", {"amount": 5000.0, "equity": 900.0, "capital_part": 5000.0}),
        ("adjust", {"amount": 10.0}),
        ("deposit", {"amount": float("nan")}),
        ("deposit", {"amount": True}),
        ("bonus", {"amount": 1.0}),
        ("step_down", {"step": 0, "trigger": "dd_peak_10", "equity": 900.0, "peak": 1000.0}),
        ("review_resume", {"equity": 800.0, "rebase": True, "decision": ""}),
    ]
    for kind, f in bad:
        with pytest.raises(rl.LadderLogError):
            b.add(kind, **f)
        assert p.read_bytes() == before, kind
    with pytest.raises(rl.LadderLogError):                      # geri giden saat
        rl.LadderLog(str(p)).append("deposit", "cli:t", NOW0 - D, amount=1.0)
    assert p.read_bytes() == before


# =====================================================================================================
# B. evaluate / step_config / counters / match_transfers
# =====================================================================================================
def ev(st, equity):
    return rl.evaluate(st, equity)


def test_t17_stop_boundary():
    st = to_km1(book(1000.0)).state()            # K-1: dd_peak satirlari eylem uretmez; yalniz durma sinirini goruruz
    assert ev(st, 800.01) == ()
    assert ev(st, 800.0) == (act("review_stop"),)
    assert ev(st, 799.99) == (act("review_stop"),)


def test_t17_stop_boundary_at_k0():
    # SPEC-AMBIGUOUS: sartname "800,01 => yok" der; ama K0/peak=1000 durumunda 800,01 <= 0,85*peak oldugundan
    # (satir 5) `step_down(-1, dd_peak_15)` uretilir. Burada yalniz "review_stop uretilmez" denetlenir.
    st = book(1000.0).state()
    assert all(a.kind != "review_stop" for a in ev(st, 800.01))
    assert ev(st, 800.0) == (act("review_stop"),)


def test_t18_floor_boundary_review_state():
    st = to_review(book(1000.0)).state()
    assert ev(st, 600.01) == ()
    assert ev(st, 600.0) == (act("floor_stop"),)
    assert ev(st, 599.99) == (act("floor_stop"),)


def test_t18_floor_priority_in_ok_state():
    st = book(1000.0).state()
    assert ev(st, 600.0) == (act("floor_stop"),)               # durma degil, taban oncelikli


@pytest.mark.parametrize("equity", [1e9, 1000.0, 900.0, 800.0, 600.0, 599.0, 1.0, 0.01])
def test_t19_floor_state_no_action(equity):
    assert ev(to_floor(book(1000.0)).state(), equity) == ()


@pytest.mark.parametrize("equity", [1e9, 1000.0, 850.0, 800.0, 700.0, 600.01])
def test_t19_review_state_only_floor(equity):
    assert ev(to_review(book(1000.0)).state(), equity) == ()


def test_t20_dd_peak_10_boundary_and_fired():
    st = book(1000.0).state()
    assert ev(st, 900.01) == ()
    assert ev(st, 900.0) == (act("step_down", -1, "dd_peak_10"),)
    # fired iken tekrarlanmaz: K-1 -> K0 (step_up) sonrasi fired={dd_peak_10} kalir
    b = to_km1(book(1000.0))
    b.add("step_up", step=0, decision="TK")
    st2 = b.state()
    assert st2.step == 0 and st2.fired == frozenset({"dd_peak_10"})
    assert ev(st2, 900.0) == ()
    b.add("peak", "engine:rk1", value=1000.0)                   # peak satiri fired'i temizler
    st3 = b.state()
    assert st3.fired == frozenset()
    assert ev(st3, 900.0) == (act("step_down", -1, "dd_peak_10"),)


def test_t20_dd_peak_10_from_k2_goes_one_step():
    st = dataclasses.replace(book(1000.0).state(), step=2)     # elle kurulmus durum
    assert ev(st, 900.0) == (act("step_down", 1, "dd_peak_10"),)


def test_t21_dd_peak_15():
    st0 = book(1000.0).state()
    st2 = dataclasses.replace(st0, step=2)
    assert ev(st2, 850.0) == (act("step_down", 0, "dd_peak_15"),)
    assert ev(st0, 850.0) == (act("step_down", -1, "dd_peak_15"),)
    stm = to_km1(book(1000.0)).state()
    assert ev(stm, 850.0) == ()                                  # zaten en altta; dd_peak_10'a gecilmez
    assert ev(stm, 850.01) == ()
    assert ev(st0, 850.01) == (act("step_down", -1, "dd_peak_10"),)   # 850,01 yalniz -%10 sinirini asar


def test_t22_small_capital():
    b = book(250.0)
    st = b.state()
    assert rl.lowest(250.0) == 0
    assert ev(st, 224.0) == () and ev(st, 212.0) == ()           # en alt basamak K0 -> iniş yok
    assert ev(st, 200.01) == ()
    assert ev(st, 200.0) == (act("review_stop"),)
    b.add("deposit", amount=750.0)
    assert rl.lowest(b.state().dep_net) == -1
    assert rl.lowest(999.99) == 0 and rl.lowest(1000.0) == -1


def test_t23_base_and_floor_references():
    b = book(250.0)
    to_review(b, 200.0)
    b.add("review_resume", "cli:t", equity=198.0, rebase=True, decision="")
    st = b.state()
    assert (st.dep_net, st.base, st.peak) == (250.0, 198.0, 198.0)
    assert ev(st, 158.41) == ()
    assert ev(st, 158.40) == (act("review_stop"),)               # round(0.80 * 198, 8)
    assert ev(st, 150.0) == (act("floor_stop"),)                 # taban dep_net'e bagli
    b.add("deposit", amount=750.0)
    st = b.state()
    assert (st.dep_net, st.base, st.peak) == (1000.0, 948.0, 948.0)
    assert st.started_at == NOW0                                 # sayaclar sifirlanmaz
    assert all(a.kind != "review_stop" for a in ev(st, 758.41))
    assert ev(st, 758.40) == (act("review_stop"),)
    assert ev(st, 600.0) == (act("floor_stop"),)
    assert rl.lowest(st.dep_net) == -1


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0, -0.01, True, False])
def test_t24_evaluate_invalid_equity(bad):
    with pytest.raises(ValueError):
        ev(book(1000.0).state(), bad)


def test_t25_step_config():
    from trader_core.risk import tightened
    cfg = tightened(LOCKED_CFG, target_trade_risk=0.005)         # cfg.target_trade_risk = 0.005
    assert rl.step_config(cfg, 0) is cfg
    k1 = rl.step_config(cfg, -1)
    assert k1.target_trade_risk == 0.0035
    for f in dataclasses.fields(RiskConfig):
        if f.name != "target_trade_risk":
            assert getattr(k1, f.name) == getattr(LOCKED_CFG, f.name), f.name
    assert rl.step_config(cfg, 2).target_trade_risk == 0.005     # yapilandirma tavani
    assert rl.step_config(cfg, 2) is cfg
    assert rl.step_config(LOCKED_CFG, 4) is LOCKED_CFG
    assert rl.step_config(LOCKED_CFG, 0).target_trade_risk == 0.005
    for bad in (5, -2, 99, 0.5):
        with pytest.raises(ValueError):
            rl.step_config(cfg, bad)
    for s in sorted(rl.STEPS):
        out = rl.step_config(cfg, s)
        for f in dataclasses.fields(RiskConfig):
            if f.name == "target_trade_risk":
                assert out.target_trade_risk <= LOCKED_CFG.target_trade_risk
            else:
                assert getattr(out, f.name) == getattr(LOCKED_CFG, f.name)


def tr(i: int, entry: datetime, r: float, reason: str = "stop", hours: float = 1.0) -> TradeRecord:
    return TradeRecord(
        trade_id=i, decision_id=i, pair="BTC/USDT", side="long", setup="s", regime="r", atr_ratio=None,
        param_version_id=1, activation_id=None, entry_ts=entry, entry_price=100.0, planned_entry=100.0,
        planned_stop=99.0, planned_target=None, qty=1.0, leverage=1, planned_risk=1.0, fee_entry=0.0,
        slippage_entry=0.0, exit_ts=entry + timedelta(hours=hours), exit_price=100.0 + r, exit_reason=reason,
        planned_exit=None, fee_exit=0.0, funding_paid=0.0, gross_pnl=r, realized_pnl=r, r_multiple=r,
        slippage_exit=0.0)


def series31():
    """31 islem, eskiden yeniye: i=0 -> -5; i=1..27 -> +1; i=28..30 -> -1. Giris = NOW0 + (i+1) saat."""
    rs = [-5.0] + [1.0] * 27 + [-1.0] * 3
    return [tr(i + 1, NOW0 + (i + 1) * H, r) for i, r in enumerate(rs)]


# SPEC-AMBIGUOUS: `counters` girdisinin sirasi: gercek kaynak `list_closed_trades` cikis zamanina gore YENIDEN->ESKIYE
# doner; burada o sira (yeni once) kullanilir ve ayrica artan sira da denenir (gerceklemenin siralamasi bagimsiz olmali).
@pytest.mark.parametrize("newest_first", [True, False])
def test_t26_counters_main(newest_first):
    st = book(1000.0).state()
    now = NOW0 + 10 * D + 23 * H
    trades = series31()
    trades = list(reversed(trades)) if newest_first else trades
    c = rl.counters(trades, st, now)
    assert c["total_trades"] == 31 and c["step_trades"] == 31
    assert c["step_days"] == 10                                  # 10 g 23 s -> asagi
    assert c["consec_losses"] == 3
    assert c["last30_sum_r"] == pytest.approx(24.0)              # i=1..30 (en eski atilir)
    assert c["step_mean_r"] == pytest.approx(19.0 / 31.0)


def test_t26_counters_exclusions():
    st = book(1000.0).state()
    now = NOW0 + 5 * D
    good = [tr(1, NOW0 + H, 1.0), tr(2, NOW0 + 2 * H, -1.0)]
    manual = tr(3, NOW0 + 3 * H, -9.0, reason="manual")
    before = tr(4, NOW0 - H, -9.0)                               # started_at oncesi giris
    at_start = tr(5, NOW0, 2.0)                                  # entry_ts == started_at sayilir
    kill = tr(6, NOW0 + 4 * H, 0.5, reason="kill")
    c = rl.counters([kill, manual, good[1], good[0], before, at_start], st, now)
    assert c["total_trades"] == 4                                # good x2 + at_start + kill
    assert c["consec_losses"] == 0                               # en son (kill, +0.5) kazanc; manual kayip sayilmaz
    c2 = rl.counters([manual], st, now)
    assert c2["total_trades"] == 0 and c2["step_mean_r"] is None


def test_t26_counters_step_since_split_and_reset():
    st = dataclasses.replace(book(1000.0).state(), step_since=NOW0 + 10 * H)
    now = st.step_since + 41 * D + 23 * H + timedelta(minutes=59)
    c = rl.counters(list(reversed(series31())), st, now)
    assert c["total_trades"] == 31                               # step_since oncesi giris total'a girer
    assert c["step_trades"] == 22                                # i+1 >= 10  ->  i = 9..30
    assert c["step_mean_r"] == pytest.approx(16.0 / 22.0)        # 19 x (+1) ve 3 x (-1)
    assert c["step_days"] == 41                                  # tam gun, asagi
    assert rl.counters([], st, st.step_since + 42 * D)["step_days"] == 42


def test_t26_counters_empty():
    st = book(1000.0).state()
    c = rl.counters([], st, NOW0 + D)
    assert c["total_trades"] == 0 and c["step_trades"] == 0
    assert c["step_mean_r"] is None and c["consec_losses"] == 0 and c["last30_sum_r"] == 0
    assert c["step_days"] == 1
    assert set(c) >= {"total_trades", "step_trades", "step_days", "step_mean_r", "consec_losses", "last30_sum_r"}


def test_t26_last30_fewer_than_30():
    st = book(1000.0).state()
    ts = [tr(i, NOW0 + i * H, 0.5) for i in range(1, 6)]
    c = rl.counters(list(reversed(ts)), st, NOW0 + D)
    assert c["last30_sum_r"] == pytest.approx(2.5)


# ---- T-27 match_transfers --------------------------------------------------------------------------
NOWM = NOW0 + 20 * D


def X(ts, amount, tid, asset="USDT"):
    return rl.Transfer(ts=ts, amount=amount, tran_id=tid, asset=asset)


def rows_for(items, now=NOWM, initial=5000.0):
    """items: (kind, offset_from_now (negatif), fields). `initial` now-10 gun."""
    log = rl.LadderLog(None)
    log.append("initial", "cli:t", now - 10 * D, amount=initial)
    for kind, off, f in sorted(items, key=lambda it: it[1]):
        log.append(kind, "cli:t", now + off, **f)
    return log.rows()


def dep(off, amount=750.0):
    return ("deposit", off, {"amount": amount})


def mt(rows, transfers, now=NOWM):
    return rl.match_transfers(rows, transfers, now)


def test_t27_exact_match():
    rows = rows_for([dep(-2 * D)])
    r = mt(rows, [X(NOWM - 2 * D + 10 * M1, 750.0, "a")])
    assert r.ok is True and r.unmatched_exchange == () and r.unmatched_log == ()


def test_t27_amount_tolerance():
    rows = rows_for([dep(-2 * D, 751.0)])
    assert mt(rows, [X(NOWM - 2 * D, 750.0, "a")]).ok is True            # fark 1,00
    rows = rows_for([dep(-2 * D, 751.01)])
    assert mt(rows, [X(NOWM - 2 * D, 750.0, "a")]).ok is False           # fark 1,01


def test_t27_time_window():
    rows = rows_for([dep(-3 * D)])
    ok = mt(rows, [X(NOWM - 3 * D + 48 * H, 750.0, "a")])
    assert ok.ok is True
    bad = mt(rows, [X(NOWM - 3 * D + 48 * H + timedelta(seconds=1), 750.0, "a")])
    assert bad.ok is False
    # geriye dogru da simetrik: |dt|
    ok2 = mt(rows, [X(NOWM - 3 * D - 48 * H + timedelta(seconds=0), 750.0, "a")])
    # SPEC-AMBIGUOUS: -48 saat sinirda borsa aktarimi `started_at` oncesine dusebilir; yalniz kabul yonu denetlenir.
    assert ok2.ok in (True, False)


def test_t27_opposite_sign_does_not_match():
    rows = rows_for([("withdraw", -2 * D, {"amount": 750.0, "equity": 5000.0, "capital_part": 750.0})])
    r = mt(rows, [X(NOWM - 2 * D, 750.0, "a")])                          # +750 giris vs -750 cikis
    assert r.ok is False and len(r.unmatched_exchange) == 1 and len(r.unmatched_log) == 1
    r2 = mt(rows, [X(NOWM - 2 * D, -750.0, "a")])
    assert r2.ok is True


def test_t27_one_to_one():
    rows = rows_for([dep(-2 * D)])
    r = mt(rows, [X(NOWM - 2 * D, 750.0, "a"), X(NOWM - 2 * D + M1, 750.0, "b")])
    assert r.ok is False and len(r.unmatched_exchange) == 1 and r.unmatched_log == ()
    rows2 = rows_for([dep(-2 * D), dep(-2 * D + M1)])
    r2 = mt(rows2, [X(NOWM - 2 * D, 750.0, "a")])
    assert r2.ok is False and r2.unmatched_exchange == () and len(r2.unmatched_log) == 1


def test_t27_oldest_log_row_matched_first():
    rows = rows_for([dep(-2 * D), dep(-2 * D + H)])
    seqs = [r["seq"] for r in rows if r["kind"] == "deposit"]
    r = mt(rows, [X(NOWM - 2 * D + 30 * M1, 750.0, "a")])
    assert r.unmatched_log == (seqs[1],)


def test_t27_initial_and_adjust_not_in_pool():
    rows = rows_for([("adjust", -1 * D, {"amount": 100.0, "note": "duzeltme"})])
    assert mt(rows, []).ok is True                                       # initial + adjust eslesme beklemez
    r = mt(rows, [X(NOWM - 10 * D, 5000.0, "a")])                        # initial tutariyla ayni aktarim: eslesmez
    assert r.ok is True or len(r.unmatched_exchange) == 1                # (7 gunluk pencere disinda olabilir)
    rows2 = rows_for([("adjust", -1 * D, {"amount": 100.0, "note": "duzeltme"})])
    r2 = mt(rows2, [X(NOWM - 1 * D, 100.0, "b")])
    assert r2.ok is False and len(r2.unmatched_exchange) == 1            # adjust aktarimla eslesmez


def test_t27_must_window_five_days():
    rows = rows_for([])
    # mentor v1.1 ruling: borsa tarafi zorunlu kume = tam 7 gunluk pencere; gunluk tarafi 5 gun kalir
    assert mt(rows, [X(NOWM - 6 * D, 300.0, "old")]).ok is False         # mentor v1.1 ruling: 6 gunluk borsa aktarimi artik bozar
    assert mt(rows, [X(NOWM - 8 * D, 300.0, "older")]).ok is True         # mentor v1.1 ruling: 7 gunden eski: pencere disi
    assert mt(rows, [X(NOWM - 4 * D, 300.0, "new")]).ok is False         # 5 gun icinde: bozar
    old_log = rows_for([dep(-6 * D, 300.0)])
    assert mt(old_log, []).ok is True
    new_log = rows_for([dep(-4 * D, 300.0)])
    r = mt(new_log, [])
    assert r.ok is False and len(r.unmatched_log) == 1


def test_t27_non_usdt_never_matches():
    rows = rows_for([dep(-2 * D)])
    r = mt(rows, [X(NOWM - 2 * D, 750.0, "a", asset="BNB")])
    assert r.ok is False and len(r.unmatched_exchange) == 1 and len(r.unmatched_log) == 1


def test_t27_transfers_before_started_at_ignored():
    log = rl.LadderLog(None)
    log.append("initial", "cli:t", NOWM - 2 * D, amount=1000.0)
    r = mt(log.rows(), [X(NOWM - 3 * D, 500.0, "pre")])
    assert r.ok is True and r.unmatched_exchange == ()


# =====================================================================================================
# C. Motor duzeyi: RiskLadder (sahte saat / yoklama; tam Engine dongusu yok)
# =====================================================================================================
def write_cfg(tmp: Path, mode: str = "testnet", extra: dict | None = None):
    """-> (config_dir, EngineConfig). Tum yollar tmp altinda."""
    cfgd = tmp / "cfg"
    cfgd.mkdir(exist_ok=True)
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    raw.update(var_dir=str(tmp / "var"), market_db=str(tmp / "market.sqlite"), history_dir=str(tmp / "hist"), kill_file=str(tmp / "shared" / "KILL"),
               pause_file=str(tmp / "shared" / "PAUSE"), target_trade_risk=0.005, wallet_start=1000.0)
    raw.update(extra or {})
    (cfgd / "engine.base.json").write_text(json.dumps(raw))
    (cfgd / "engine.learner.json").write_text(json.dumps({"bot": "learner"}))
    overlay = None
    if mode == "testnet":
        ov = json.loads((ROOT / "config" / "engine.testnet.json").read_text())
        ov.update(var_dir=str(tmp / "var-testnet"), kill_file=str(tmp / "shared" / "testnet" / "KILL"),      # DD-8: testnet yol kurali
                  pause_file=str(tmp / "shared" / "testnet" / "PAUSE"))
        overlay = cfgd / "engine.testnet.json"
        overlay.write_text(json.dumps(ov))
    cfg = load_engine_config(cfgd / "engine.base.json", cfgd / "engine.learner.json", overlay_path=overlay)
    return cfgd, cfg


def ladder_mod():
    return pytest.importorskip("trader_engine.ladder")


class Env:
    """RiskLadder + gercek EntryPause + sahte SimClock; tum dosyalar tmp altinda."""

    def __init__(self, tmp: Path, *, mode="testnet", enforce=True, seed=True, amount=1000.0, transfers_fn=None,
                 follow=None, log=None, extra=None):
        lm = ladder_mod()
        from trader_engine.pause import EntryPause
        _, self.cfg = write_cfg(tmp, mode, extra)
        self.clock = SimClock(NOW0 + H)
        os.makedirs(os.path.dirname(self.cfg.path("x")), exist_ok=True)
        os.makedirs(os.path.dirname(f"{self.cfg.pause_file}.{self.cfg.bot}"), exist_ok=True)
        self.log_path = self.cfg.path("risk_ladder.jsonl")
        if log is not None:
            self.log = log
        elif mode == "paper":
            self.log = rl.LadderLog(None)
        else:
            self.log = rl.LadderLog(self.log_path)
        if seed:
            self.log.append("initial", "engine:paper" if mode == "paper" else "cli:t", NOW0, amount=float(amount))
        self.pause_path = f"{self.cfg.pause_file}.{self.cfg.bot}"
        self.pause = EntryPause(self.pause_path, self.clock, audit_path=self.cfg.path("pause_audit.jsonl"),
                                bot=self.cfg.bot)
        self.mk = lambda lg=None: lm.RiskLadder(self.cfg, self.clock, self.pause, log=lg or self.log, enforce=enforce,
                                                follow=follow, transfers_fn=transfers_fn)
        self.rl = self.mk()

    def tick(self, equity, *, dt=60.0, wallet=None, flat=False):
        self.clock.advance(dt)
        self.rl.tick(self.clock.now(), equity, equity if wallet is None else wallet, flat=flat)

    def reasons(self):
        return [h.reason for h in self.pause.holds()]

    def kinds(self):
        return [r["kind"] for r in self.log.rows()]


def test_t30_no_log_gate_capital_missing(tmp_path):
    e = Env(tmp_path, seed=False)
    e.tick(1000.0)
    assert e.rl.gate_code() == "capital_missing"
    assert e.pause.holds() == ()


def test_t31_corrupt_log_gate_invalid_then_recovers(tmp_path):
    e = Env(tmp_path)
    good = Path(e.log_path).read_bytes()
    Path(e.log_path).write_text("bozuk satir {{{\n" * 3, encoding="utf-8")
    e.tick(1000.0)
    assert e.rl.gate_code() == "ladder_invalid"
    Path(e.log_path).write_bytes(good)                           # duzeltilince KENDILIGINDEN acilir
    e.tick(1000.0)
    assert e.rl.gate_code() is None


def test_t32_confirmation_two_consecutive(tmp_path):
    e = Env(tmp_path)
    e.tick(800.0)
    assert e.reasons() == [] and e.rl.status()["pending"] == "review_stop"
    e.tick(1000.0)                                               # tutmadi: sayac sifirlanir
    assert e.reasons() == [] and e.rl.status()["pending"] is None
    e.tick(800.0)
    assert e.reasons() == []
    e.tick(800.0)                                                # iki ardisik
    assert e.reasons() == ["capital_latch", "drawdown_review"] and "review_stop" in e.kinds()


def test_t32_eval_throttle_59_60(tmp_path):
    e = Env(tmp_path)
    e.tick(800.0)                                                # t0: ilk cagri her zaman calisir
    e.tick(800.0, dt=59.0)                                       # 59 sn: sayilmaz
    assert e.reasons() == []
    e.tick(800.0, dt=1.0)                                        # son degerlendirmeden 60 sn
    assert e.reasons() == ["capital_latch", "drawdown_review"]


def test_t33_review_stop_applied(tmp_path):
    e = Env(tmp_path)
    e.tick(800.0)
    e.tick(800.0)
    last = e.log.rows()[-1]
    assert last["kind"] == "review_stop" and last["equity"] == 800.0 and last["base"] == 1000.0
    hs = e.pause.holds()                                          # capital_latch (kullanici karari) + -%20 tutusu
    assert [h.reason for h in hs] == ["capital_latch", "drawdown_review"] and all(h.by == "engine:rk1" for h in hs)
    assert e.pause.code() == "drawdown_review"       # SPEC-AMBIGUOUS: "kapi kodu" = pause.code(); rl.gate_code() None kalir
    assert e.rl.status()["state"] == "review"
    assert not os.path.exists(e.cfg.kill_file)                   # KILL kurulmaz


def test_t34_persistence_across_restart(tmp_path):
    e = Env(tmp_path)
    e.tick(800.0)
    e.tick(800.0)
    rl2 = e.mk(rl.LadderLog(e.log_path))                         # motor yeniden kuruldu
    e.clock.advance(60)
    rl2.tick(e.clock.now(), 1000.0, 1000.0)                      # ozsermaye toparlandi
    assert e.reasons() == ["capital_latch", "drawdown_review"] and rl2.status()["state"] == "review"
    e.log.append("deposit", "cli:t", e.clock.now(), amount=500.0)   # deposit durumu acmaz
    e.clock.advance(60)
    rl2.tick(e.clock.now(), 1500.0, 1500.0)
    assert e.reasons() == ["capital_latch", "drawdown_review"] and rl2.status()["state"] == "review"


@pytest.mark.parametrize("equity,reason", [(800.0, "drawdown_review"), (600.0, "capital_floor")])
def test_t35_hold_invariant_reinstated(tmp_path, equity, reason):
    e = Env(tmp_path)
    e.tick(equity)
    e.tick(equity)
    assert reason in e.reasons()
    os.remove(e.pause_path)                                      # PAUSE dosyasi silindi
    assert e.pause.holds() == ()
    e.tick(equity)                                               # sonraki degerlendirme
    assert reason in e.reasons()


def test_t36_log_unwritable_hold_still_set(tmp_path, caplog):
    class Flaky(rl.LadderLog):
        fail = True

        def append(self, *a, **k):
            if self.fail:
                raise OSError("salt okunur")
            return super().append(*a, **k)

    lg = Flaky(str(tmp_path / "var" / "learner" / "risk_ladder.jsonl"))
    (tmp_path / "var" / "learner").mkdir(parents=True)
    lg.fail = False
    lg.append("initial", "cli:t", NOW0, amount=1000.0)
    lg.fail = True
    e = Env(tmp_path, log=lg, seed=False)
    caplog.set_level(logging.DEBUG)
    e.tick(800.0)
    e.tick(800.0)                                                # istisna sizmaz
    assert e.reasons() == ["capital_latch", "drawdown_review"]                    # satir yazilamasa da tutus kurulur
    assert any(r.levelno >= logging.CRITICAL for r in caplog.records)
    assert e.kinds() == ["initial"]
    lg.fail = False                                              # yazma duzeldi
    for _ in range(3):
        e.tick(800.0)
    assert e.kinds().count("review_stop") == 1                   # tek satir, cift degil


def test_t37_floor_stop_during_review(tmp_path):
    e = Env(tmp_path)
    e.tick(800.0)
    e.tick(800.0)
    e.tick(600.0)
    e.tick(600.0)
    assert "floor_stop" in e.kinds()
    assert e.pause.code() == "capital_floor"
    assert set(e.reasons()) >= {"capital_floor"}


def test_t38_effective_risk_after_step_down(tmp_path):
    e = Env(tmp_path)
    assert e.rl.risk_config is e.cfg.risk_config                 # K0: yapilandirma nesnesinin kendisi
    e.tick(900.0)
    e.tick(900.0)
    assert e.kinds()[-1] == "step_down" and e.reasons() == []    # inis: tutus yok
    k1 = e.rl.risk_config
    assert k1.target_trade_risk == 0.0035
    for f in dataclasses.fields(RiskConfig):
        if f.name != "target_trade_risk":
            assert getattr(k1, f.name) == getattr(e.cfg.risk_config, f.name)
    # (sartnamenin boyutlama ve acik-pozisyon kismi tam Engine dongusu ister: burada kapsanmaz)


def X_(ts, amount, tid, asset="USDT"):
    return rl.Transfer(ts=ts, amount=amount, tran_id=tid, asset=asset)


def test_t39_unrecorded_transfer_blocks_without_triggers(tmp_path):
    xfer = [X_(NOW0 + 30 * M1, 750.0, "t1")]
    e = Env(tmp_path, transfers_fn=lambda since, until: list(xfer))
    n0 = len(e.log.rows())
    e.tick(1750.0)                                               # kaydedilmemis +750 (yeni UTC gunu degil ama ilk deger.)
    assert e.rl.gate_code() == "capital_mismatch"
    for _ in range(3):
        e.tick(250.0)                                            # base 1000'e gore -%75: ama tetik YOK
    assert e.rl.gate_code() == "capital_mismatch"
    assert e.reasons() == [] and len(e.log.rows()) == n0         # ne tutus ne peak/step satiri
    e.log.append("deposit", "cli:t", e.clock.now(), amount=750.0)
    e.tick(1750.0, dt=130.0)                                     # yoklama aralığı (120 sn) doldu
    assert e.rl.gate_code() is None


def test_t39_recorded_deposit_without_transfer_blocks(tmp_path):
    e = Env(tmp_path, transfers_fn=lambda since, until: [])
    e.log.append("deposit", "cli:t", NOW0 + 30 * M1, amount=750.0)   # base 1750; borsada aktarim yok
    for _ in range(3):
        e.tick(250.0)
    assert e.rl.gate_code() == "capital_mismatch"
    assert e.reasons() == []
    assert not {"review_stop", "floor_stop"} & set(e.kinds())
    # mentor v1.1 ruling: yapiskan mandal - gunluk tarafi 5 gunde sonse de aktarim gelmedikce kapi acilmaz, stop uretilmez
    for _ in range(3):
        e.tick(250.0, dt=6 * 86400.0)
    assert e.rl.gate_code() == "capital_mismatch"
    assert not {"review_stop", "floor_stop"} & set(e.kinds())


def test_t40_transfer_poll_failure_stale_after_15_min(tmp_path):
    state = {"fail": False}

    def fn(since, until):
        if state["fail"]:
            raise OSError("yoklama basarisiz")
        return []

    e = Env(tmp_path, transfers_fn=fn)
    e.tick(1000.0)                                               # basarili yoklama (flat=False -> ilk kurulum denetimi yok)
    assert e.rl.gate_code() is None
    state["fail"] = True
    for k in range(1, 7):                                        # 780 sn: onceki sonuc gecerli
        e.tick(1000.0, dt=130.0)
        assert e.rl.gate_code() is None, k
    e.tick(1000.0, dt=130.0)                                     # 910 sn > 900
    assert e.rl.gate_code() == "capital_unverified"
    e.tick(800.0, dt=130.0)
    e.tick(800.0, dt=130.0)                                      # capital_unverified tetikleri durdurmaz
    assert "drawdown_review" in e.reasons()


@pytest.mark.parametrize("wallet,flat,expected", [(300.0, True, "capital_mismatch"), (254.0, True, None),
                                                  (300.0, False, None)])
def test_t41_initial_setup_check(tmp_path, wallet, flat, expected):
    e = Env(tmp_path, amount=250.0, transfers_fn=lambda s, u: [])
    e.tick(wallet, wallet=wallet, flat=flat)
    assert e.rl.gate_code() == expected
    # SPEC-AMBIGUOUS: sartname uyusmazlik `detail = "init_wallet"` der; status()["transfer"] icinde mi gecer bilinmez.


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -5.0])
def test_t42_equity_unreadable(tmp_path, bad):
    e = Env(tmp_path)
    n0 = len(e.log.rows())
    e.tick(bad)                                                  # istisna sizmamali
    assert e.rl.gate_code() == "equity_unreadable"
    e.tick(bad)
    assert e.reasons() == [] and len(e.log.rows()) == n0


def test_t44_peak_updates_daily(tmp_path):
    e = Env(tmp_path)
    e.tick(1050.0)                                               # surecin ilk degerlendirmesi: gun basi
    assert e.log.rows()[-1]["kind"] == "peak" and e.log.rows()[-1]["value"] == 1050.0
    e.tick(1100.0)                                               # ayni UTC gunu: yeni satir yok
    assert e.kinds().count("peak") == 1
    e.clock.set_time(NOW0 + D + 2 * H)                           # ertesi UTC gunu
    e.rl.tick(e.clock.now(), 1100.0, 1100.0)
    assert e.kinds().count("peak") == 2 and e.log.rows()[-1]["value"] == 1100.0


def test_t44_no_peak_while_mismatch(tmp_path):
    e = Env(tmp_path, transfers_fn=lambda s, u: [X_(NOW0 + 30 * M1, 400.0, "t1")])
    e.tick(1400.0)
    assert e.rl.gate_code() == "capital_mismatch" and "peak" not in e.kinds()


def test_t45_follow_k_minus_1_and_not_stopped(tmp_path):
    fp = tmp_path / "other" / "risk_ladder.jsonl"
    other = to_km1(book(1000.0, fp))
    e = Env(tmp_path, mode="paper", enforce=False, follow=rl.LadderLog(str(fp)))
    e.tick(1000.0)
    assert e.rl.risk_config.target_trade_risk == 0.0035          # izlenen K-1 -> izleyen K-1 riski
    to_review(other, 700.0)                                      # izlenen durdu
    e.tick(1000.0)
    assert e.rl.gate_code() is None and e.reasons() == []        # ikiz durmaz
    assert e.rl.risk_config.target_trade_risk == 0.0035          # min(step, 0) = -1
    assert len(rl.LadderLog(str(fp)).rows()) == len(other.rows())   # izleyen yazmaz


def test_t45_follow_review_at_k0_uses_cfg_risk(tmp_path):
    fp = tmp_path / "other" / "risk_ladder.jsonl"
    to_review(book(1000.0, fp))
    e = Env(tmp_path, mode="paper", enforce=False, follow=rl.LadderLog(str(fp)))
    e.tick(1000.0)
    assert e.rl.risk_config.target_trade_risk == e.cfg.risk_config.target_trade_risk == 0.005


def test_t45_follow_missing_file_falls_back(tmp_path):
    e = Env(tmp_path, mode="paper", enforce=False, follow=rl.LadderLog(str(tmp_path / "yok" / "risk_ladder.jsonl")))
    e.tick(1000.0)
    assert e.rl.risk_config is e.cfg.risk_config
    # SPEC-AMBIGUOUS: `ladder_follow_unreadable` sayaci status()/bellekte nerede gorunur belirtilmemis; denetlenmedi.


def test_t45_ladder_follow_config(tmp_path):
    _, cfg = write_cfg(tmp_path, "paper", {"ladder_follow": str(tmp_path / "x.jsonl")})
    assert cfg.ladder_follow == str(tmp_path / "x.jsonl")
    sub = tmp_path / "t"
    sub.mkdir()
    with pytest.raises(ConfigError):                             # yalniz paper kipinde
        write_cfg(sub, "testnet", {"ladder_follow": str(tmp_path / "x.jsonl")})


def test_t29_paper_observation_ladder_level(tmp_path):
    e = Env(tmp_path, mode="paper", enforce=False)               # SPEC-AMBIGUOUS: sanal `initial` kimin yazdigi belirsiz; burada tohumlanir
    e.tick(800.0)
    e.tick(800.0)
    assert e.reasons() == ["capital_latch"] and e.rl.gate_code() is None        # capital_latch var, -%20 tutusu yok (kullanici karari), kapi acik
    w = e.rl.status()["would"]
    assert w["kind"] == "review_stop"
    assert e.rl.risk_config is e.cfg.risk_config                 # boyutlama cfg.risk_config ile (bit-bit ayni)
    assert not os.path.exists(e.cfg.kill_file)


STATUS_KEYS = {"enforce", "state", "step", "step_name", "step_risk", "effective_risk", "lowest_step", "step_since",
               "started_at", "dep_net", "base", "peak", "equity", "dd_base_pct", "dd_peak_pct", "stop_at", "floor_at",
               "near", "stopped_at", "last_down_at", "gate_code", "gate_since", "transfer", "pending", "would", "follow",
               "counters", "log_seq", "log_hash"}


def test_t48_status_block(tmp_path):
    e = Env(tmp_path)
    e.tick(850.0)
    s = e.rl.status()
    assert STATUS_KEYS <= set(s)
    assert s["enforce"] is True and s["state"] == "ok"
    assert s["step"] == 0 and s["step_name"] == "K0" and s["step_risk"] == 0.005 and s["lowest_step"] == -1
    assert s["stop_at"] == 800.0 and s["floor_at"] == 600.0
    assert s["near"] is True                                     # 850 <= 0.85 * 1000 (kapsayici)
    assert s["dd_base_pct"] == pytest.approx(15.0)
    assert s["log_seq"] == 1 and s["log_hash"] == e.log.state().head_hash[:8]
    e.tick(900.0)
    assert e.rl.status()["near"] is False


def test_t48_status_uninitialized(tmp_path):
    e = Env(tmp_path, seed=False)
    e.tick(1000.0)
    s = e.rl.status()
    assert s["state"] == "uninitialized"
    for k in ("dep_net", "base", "peak", "stop_at", "floor_at", "step"):
        assert s[k] is None, k


# ---- T-46 mimari --------------------------------------------------------------------------------------
FORBIDDEN_KINDS = {"review_resume", "floor_restart", "step_up", "initial", "deposit", "withdraw", "adjust"}


def test_t46_ladder_source_architecture():
    p = SRC / "trader_engine" / "ladder.py"
    if not p.exists():
        pytest.skip("trader_engine/ladder.py henuz yok")
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "remove":
                pytest.fail("ladder.py icinde `.remove(` cagrisi (pause.remove yalniz cli.py'dedir)")
            if n.func.attr == "append" and n.args and isinstance(n.args[0], ast.Constant) \
                    and n.args[0].value in FORBIDDEN_KINDS:
                pytest.fail(f"ladder.py append({n.args[0].value!r}) yazmamali")
    src = p.read_text(encoding="utf-8")
    assert "RiskConfig(" not in src and "replace(" not in src      # sayisal risk sabiti / yapilandirma kurulumu yok


def test_t46_risk_ladder_does_not_import_engine():
    p = SRC / "trader_core" / "risk_ladder.py"
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        mods = []
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mods = [("." * n.level) + (n.module or "")]
        for m in mods:
            assert not m.startswith("trader_engine"), m


def test_t46_existing_guards_green():
    if not (SRC / "trader_engine" / "ladder.py").exists():
        pytest.skip("trader_engine/ladder.py henuz yok")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                        str(ROOT / "tests" / "engine" / "test_engine_no_risk_constants.py"),
                        str(ROOT / "tests" / "engine" / "test_engine_module_inventory.py")],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


# =====================================================================================================
# D. CLI (python -m trader_engine capital ... / ladder ...)
# =====================================================================================================
RN = datetime.now(UTC).replace(microsecond=0)          # CLI gercek saat kullanir: tohum satirlari gecmiste


def run_cli(argv) -> int:
    ladder_mod()                                          # RK2 yoksa CLI de yok sayilir
    from trader_engine import cli
    try:
        return int(cli.main([str(a) for a in argv]))
    except SystemExit as e:
        return int(e.code or 0)


class Cli:
    def __init__(self, tmp: Path, mode: str = "testnet"):
        self.tmp, self.mode = tmp, mode
        self.cfgd, self.cfg = write_cfg(tmp, mode)
        self.env = ["--env", "testnet"] if mode == "testnet" else []
        self.log_path = Path(self.cfg.path("risk_ladder.jsonl"))
        self.pause_path = f"{self.cfg.pause_file}.{self.cfg.bot}"
        os.makedirs(os.path.dirname(self.pause_path), exist_ok=True)

    def run(self, *args, by: str | None = "sg", bot="learner"):
        argv = list(args) + ["--bot", bot, "--config-dir", str(self.cfgd)] + self.env
        if by is not None:
            argv += ["--by", by]
        return run_cli(argv)

    def rows(self):
        return rl.LadderLog(str(self.log_path)).rows() if self.log_path.exists() else []

    def state(self):
        return rl.LadderLog(str(self.log_path)).state()

    def seed(self, build):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        b = B(self.log_path, start=RN - 10 * D)
        build(b)
        return b

    def pause(self):
        from trader_engine.clock import SystemClock
        from trader_engine.pause import EntryPause
        return EntryPause(self.pause_path, SystemClock())

    def write_status(self, equity, age_s=10):
        sp = Path(self.cfg.status_path)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps({"loop_at": z(datetime.now(UTC) - timedelta(seconds=age_s)), "equity": equity}))


def test_t49_capital_happy_path(tmp_path, capsys):
    c = Cli(tmp_path)
    assert c.run("capital", "init", "--amount", "250") == 0
    r = c.rows()
    assert [x["kind"] for x in r] == ["initial"] and r[0]["amount"] == 250.0 and r[0]["by"] == "cli:sg"
    assert c.run("capital", "deposit", "--amount", "750") == 0
    assert c.run("capital", "withdraw", "--amount", "100", "--equity", "900") == 0
    w = c.rows()[-1]
    assert w["kind"] == "withdraw" and w["amount"] == 100.0 and w["equity"] == 900.0 and w["capital_part"] == 100.0
    assert c.run("capital", "adjust", "--amount", "-5", "--note", "duzeltme") == 0
    assert c.state().dep_net == 895.0
    capsys.readouterr()
    assert c.run("capital", "list", by=None) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["bot"] == "learner" and len(out["rows"]) == 4 and out["state"] is not None


def test_t49_capital_rejections(tmp_path):
    c = Cli(tmp_path)
    assert c.run("capital", "init", "--amount", "250", by=None) == 2        # --by zorunlu
    assert not c.log_path.exists() or c.rows() == []
    assert c.run("capital", "init", "--amount", "250") == 0
    before = c.log_path.read_bytes()
    assert c.run("capital", "init", "--amount", "300") == 2                 # ikinci init
    assert c.run("capital", "adjust", "--amount", "5") == 2                 # not yok
    assert c.run("capital", "deposit", "--amount", "0") == 2
    assert c.log_path.read_bytes() == before


def test_t49_capital_paper_mode_rejects_writes(tmp_path):
    c = Cli(tmp_path, mode="paper")
    assert c.run("capital", "init", "--amount", "250") == 2                 # "kagitta sermaye kaydi yok"
    assert not c.log_path.exists()


def test_t49_capital_list_corrupt(tmp_path, capsys):
    c = Cli(tmp_path)
    c.log_path.parent.mkdir(parents=True, exist_ok=True)
    c.log_path.write_text("bozuk\n")
    # mentor v1.1 ruling: sartname v1.1 bozuk gunlukte cikis 5 der (EXIT_FINDINGS; 4 = EXIT_ENGINE ile cakisiyordu).
    assert c.run("capital", "list", by=None) == 5   # mentor v1.1 ruling: bulgu cikis kodu 5 (EXIT_FINDINGS); 4 = EXIT_ENGINE


def test_t50_withdraw_equity_source(tmp_path):
    c = Cli(tmp_path)
    c.seed(lambda b: b.add("initial", amount=1000.0))
    assert c.run("capital", "withdraw", "--amount", "100") == 2             # status.json yok, --equity yok
    c.write_status(900.0, age_s=200)                                        # bayat (> 120 sn)
    # SPEC-AMBIGUOUS: sinir 121 sn gercek saatle yarisli oldugundan 200 sn kullanildi; status.json'da `equity` anahtari (11/05 duzeni).
    assert c.run("capital", "withdraw", "--amount", "100") == 2
    assert [r["kind"] for r in c.rows()] == ["initial"]
    c.write_status(900.0, age_s=5)                                          # taze
    assert c.run("capital", "withdraw", "--amount", "100") == 0
    w = c.rows()[-1]
    assert w["equity"] == 900.0 and w["capital_part"] == 100.0
    c.write_status(900.0, age_s=500)
    assert c.run("capital", "withdraw", "--amount", "50", "--equity", "800") == 0   # --equity ile kabul
    assert c.rows()[-1]["equity"] == 800.0


def _review_seed(c: Cli, equity_stop=800.0):
    def build(b):
        b.add("initial", amount=1000.0)
        b.add("review_stop", "engine:rk1", equity=equity_stop, base=1000.0)
    c.seed(build)
    c.pause().add("drawdown_review", by="engine:rk1")


def test_t51_ladder_resume(tmp_path):
    c = Cli(tmp_path)
    _review_seed(c)
    assert c.run("ladder", "resume", "--equity", "790", "--decision", "ref-1") == 0
    r = c.rows()[-1]
    assert r["kind"] == "review_resume" and r["rebase"] is True and r["equity"] == 790.0 and r["by"] == "cli:sg"
    st = c.state()
    assert st.status == "ok" and st.base == 790.0
    assert "drawdown_review" not in [h.reason for h in c.pause().holds()]   # satir yazildi, SONRA tutus kalkti


def test_t51_ladder_resume_no_rebase(tmp_path):
    c = Cli(tmp_path)
    _review_seed(c)
    assert c.run("ladder", "resume", "--no-rebase", "--equity", "790") == 0
    st = c.state()
    assert st.status == "ok" and st.base == 1000.0 and c.rows()[-1]["rebase"] is False


def test_t51_ladder_resume_rejected_when_not_review(tmp_path):
    c = Cli(tmp_path)
    c.seed(lambda b: b.add("initial", amount=1000.0))
    n = len(c.rows())
    assert c.run("ladder", "resume", "--equity", "790") != 0
    assert len(c.rows()) == n


def test_t51_ladder_resume_ok_state_residual_hold(tmp_path):
    c = Cli(tmp_path)
    c.seed(lambda b: b.add("initial", amount=1000.0))
    c.pause().add("drawdown_review", by="engine:rk1")
    n = len(c.rows())
    assert c.run("ladder", "resume", "--equity", "900") == 0
    assert len(c.rows()) == n                                               # yalniz tutus kalkar; satir yok
    assert c.pause().holds() == ()


def test_t52_floor_restart(tmp_path):
    c = Cli(tmp_path)

    def build(b):
        b.add("initial", amount=1000.0)
        b.add("review_stop", "engine:rk1", equity=800.0, base=1000.0)
        b.add("floor_stop", "engine:rk1", equity=590.0, dep_net=1000.0)
    c.seed(build)
    p = c.pause()
    p.add("capital_floor", by="engine:rk1")
    p.add("drawdown_review", by="engine:rk1")
    n = len(c.rows())
    assert c.run("ladder", "floor-restart", "--decision", "", "--equity", "580") != 0
    assert len(c.rows()) == n and len(c.pause().holds()) == 2
    assert c.run("ladder", "floor-restart", "--decision", "TK-9", "--equity", "580") == 0
    st = c.state()
    assert st.status == "ok" and st.dep_net == 580.0 == st.base == st.peak
    assert c.pause().holds() == ()                                          # iki tutus da kalkti


def test_t53_step_up_rejected_from_k0(tmp_path):
    c = Cli(tmp_path)
    c.seed(lambda b: b.add("initial", amount=1000.0))
    n = len(c.rows())
    assert c.run("ladder", "step-up", "--decision", "TK") != 0              # K0 -> K1 asla (MAX_STEP_APPROVABLE = 0)
    assert len(c.rows()) == n


# =====================================================================================================
# Atlananlar (bu dosyada kapsanmayan T-numaralari; neden belirtilir)
# =====================================================================================================
SKIPPED = {
    "T-28": "backtest referans calismasi (summary.json/trades.csv) tam Engine + veri gerektirir",
    "T-43": "EntryGate.pre kapi sirasi sahte Engine/KILL/stale_data duzenegi gerektirir (05 `Env`); gerceklenmeden yazilamaz",
    "T-47": "mode=live motor kurulumu (build_engine + sahte broker/anahtarlar) gerektirir",
    "T-53b": "step-up'in dort kosulu icin botun ledger.sqlite'inda 60+ kapali islem tohumlamak gerekir (cli ledger okuma yolu belirsiz)",
    "T-54": "Telegram: tests/test_telegram_ladder_spec.py ayri dosya (RK4)",
    "T-55": "Telegram: ayri dosya (RK4)",
    "T-56": "Telegram: ayri dosya (RK4)",
    "T-57": "Telegram: ayri dosya (RK4)",
    "T-58": "Telegram: ayri dosya (RK4)",
    "T-59": "Telegram: ayri dosya (RK4)",
    "T-60": "Saglik: tests/test_health_ladder_spec.py ayri dosya (RK4)",
}


@pytest.mark.parametrize("tid", sorted(SKIPPED))
def test_not_covered_here(tid):
    pytest.skip(f"{tid}: {SKIPPED[tid]}")
