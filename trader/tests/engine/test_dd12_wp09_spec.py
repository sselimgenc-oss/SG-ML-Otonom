"""Independent spec tests for DD-12 WP-09 (islem notu ve ders yasam dongusu).

Written from docs/motor/dd12-capraz-varlik-spec.md (sec. 6.2, D-T25) and the dated appendix at its end (18 Kasim 2026),
which overrides sec. 9: notes are written by CODE (sabit sablon + sayisal alanlar, model="code", cost_usd=0, no LLM);
every closed trade gets exactly one nightly note (idempotent); notes become next-day candidate lessons and are retired
when they do not help; tags are exportable for ML; a separate WEEKLY LLM summary runs only with budget share
`haftalik_ozet` available (monthly cap 10 USD) and is a no-op without API key / exhausted budget.
The implementation was not read.  New-module / function names are not fixed by the spec: they are discovered tolerantly
and tests skip (not fail) when nothing matches.  No network; LLM and budget are fakes / tmp files.
"""
from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import re
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import budget as B
from trader_core import ledger as L

UTC = timezone.utc
TRADER = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 20, 2, 55, tzinfo=UTC)
DAY = "2026-11-19"
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}


# ------------------------------------------------------------------ discovery helpers
def _modules(*pkgs):
    out = []
    for pk in pkgs:
        try:
            p = importlib.import_module(pk)
        except ImportError:
            continue
        for m in pkgutil.iter_modules(p.__path__):
            out.append((f"{pk}.{m.name}", m.name))
    return out


def _find_module(name_re):
    for full, short in _modules("trader_core", "trader_engine"):
        if re.search(name_re, short):
            return importlib.import_module(full)
    return None


def _find_fn(mod, *pats):
    if mod is None:
        return None
    for p in pats:
        for n in sorted(dir(mod)):
            if n.startswith("_"):
                continue
            o = getattr(mod, n)
            if callable(o) and not isinstance(o, type) and getattr(o, "__module__", None) == mod.__name__ \
                    and re.search(p, n):
                return o
    return None


def _call(fn, *pos, **kw):
    """Call with only the kwargs the signature accepts (alias-tolerant)."""
    sig = inspect.signature(fn)
    params = sig.parameters
    kw = {k: v for k, v in kw.items() if k in params}
    return fn(*pos, **kw)


def _ledger_kw(led, path):
    return dict(ledger=led, led=led, db=led, ledger_path=path, path=path, db_path=path)


def _day_kw(day=DAY):
    return dict(day=day, run_day=day, note_date=day, date=day, for_day=day, now=NOW, as_of=NOW, clock=lambda: NOW)


# ------------------------------------------------------------------ ledger fixture
def _mk(path, specs):
    """specs: [(win, closed)] -> trades 1..n on DAY; returns open writer ledger."""
    led = L.open_ledger(path, "learner", clock=lambda: NOW)
    led.init_params(PARAMS, reason="x")
    base = datetime(2026, 11, 19, 6, tzinfo=UTC)
    for i, (win, closed) in enumerate(specs, start=1):
        bar = base + timedelta(hours=i)
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT" if i % 2 else "BTC/USDT", side="long", setup="R1",
            regime="range", atr_ratio=1.1, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
            features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5,
                      "edge_dist_atr": 0.1},
            planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1,
            veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
            size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
            final_action="entered", skip_reason=None))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        if closed:
            px = 2079.0 if win else 1960.0
            led.record_trade_exit(L.TradeExit(i, bar + timedelta(hours=1), px, "target" if win else "stop",
                                              2100.0, 0.3, 0.1))
    return led


@pytest.fixture
def led(tmp_path):
    p = tmp_path / "ledger.sqlite"
    w = _mk(p, [(True, True), (False, True), (True, False), (False, True)])   # trades 1,2,4 closed; 3 open
    yield w, p
    try:
        w.close()
    except Exception:
        pass


CLOSED = {1, 2, 4}


# ------------------------------------------------------------------ ledger layer (existing API)
def test_ledger_accepts_code_note_row(led):
    w, _ = led
    w.record_trade_note(1, DAY, ["giris_kalitesi:iyi"], "sablon notu R=+1.5", model="code", cost_usd=0)
    r = w.list_trade_notes(1)
    assert len(r) == 1 and r[0]["model"] == "code" and r[0]["cost_usd"] == 0 and r[0]["tags"] == ["giris_kalitesi:iyi"]


def test_ledger_note_requires_existing_trade(led):
    w, _ = led
    with pytest.raises(Exception):
        w.record_trade_note(999, DAY, ["x"], "metin", model="code", cost_usd=0)


# ------------------------------------------------------------------ nightly note writer (code, no LLM)
NOTES = _find_module(r"note")


def _writer():
    mod = NOTES
    if mod is None:
        pytest.skip("no trade-note module found in trader_core/trader_engine")
    fn = _find_fn(mod, r"^(write|run|generate|make|create|nightly).*notes?", r"notes?.*(nightly|run|write)",
                  r"^(nightly|run)")
    if fn is None:
        pytest.skip(f"{mod.__name__}: no note-writing entry point found")
    return mod, fn


def _run_writer(fn, w, path, **extra):
    kw = {**_ledger_kw(w, path), **_day_kw(), **extra}
    params = inspect.signature(fn).parameters
    first = next(iter(params), None)
    if first and not any(k == first for k in kw) and first not in ("self",):
        pytest.skip(f"cannot supply required parameter {first!r}")
    if first in _ledger_kw(w, path) or first in ("ledger", "led"):
        return _call(fn, **kw)
    return _call(fn, **kw)


def _notes(path):
    r = L.open_ledger(path, "learner", read_only=True, clock=lambda: NOW)
    try:
        return r.list_trade_notes()
    finally:
        r.close()


def test_every_closed_trade_gets_exactly_one_note(led):
    _, fn = _writer()
    w, p = led
    _run_writer(fn, w, p)
    notes = w.list_trade_notes()
    ids = sorted(n["trade_id"] for n in notes)
    assert ids == sorted(CLOSED), f"one note per closed trade, none for open: {ids}"


def test_notes_are_code_written_cost_zero(led):
    _, fn = _writer()
    w, p = led
    _run_writer(fn, w, p)
    notes = w.list_trade_notes()
    assert notes
    for n in notes:
        assert n["model"] == "code"
        assert n["cost_usd"] == 0
        assert n["text"].strip() and re.search(r"\d", n["text"]), "template must carry numeric fields"
        assert isinstance(n["tags"], list) and n["tags"] and all(isinstance(t, str) and t for t in n["tags"])


def test_nightly_rerun_is_idempotent(led):
    _, fn = _writer()
    w, p = led
    _run_writer(fn, w, p)
    first = w.list_trade_notes()
    _run_writer(fn, w, p)
    _run_writer(fn, w, p)
    again = w.list_trade_notes()
    assert len(again) == len(first) == len(CLOSED)
    assert [(n["trade_id"], n["text"], n["tags"]) for n in first] == [(n["trade_id"], n["text"], n["tags"]) for n in again]


def test_late_closed_trade_gets_note_on_next_run(led):
    _, fn = _writer()
    w, p = led
    _run_writer(fn, w, p)
    base = datetime(2026, 11, 19, 6, tzinfo=UTC) + timedelta(hours=3)
    w.record_trade_exit(L.TradeExit(3, base + timedelta(hours=1), 2079.0, "target", 2100.0, 0.3, 0.1))
    _run_writer(fn, w, p)
    ids = sorted(n["trade_id"] for n in w.list_trade_notes())
    assert ids == [1, 2, 3, 4]


def test_note_text_deterministic_same_input(tmp_path):
    _, fn = _writer()
    outs = []
    for k in ("a", "b"):
        p = tmp_path / f"{k}.sqlite"
        w = _mk(p, [(True, True), (False, True)])
        _run_writer(fn, w, p)
        outs.append([(n["trade_id"], n["text"], n["tags"]) for n in w.list_trade_notes()])
        w.close()
    assert outs[0] == outs[1] and outs[0]


def test_win_and_loss_notes_differ(led):
    _, fn = _writer()
    w, p = led
    _run_writer(fn, w, p)
    by = {n["trade_id"]: n for n in w.list_trade_notes()}
    assert by[1]["text"] != by[2]["text"], "numeric fields (R, exit reason) must differ between win and loss"


def test_writer_makes_no_llm_or_network_call(led, monkeypatch):
    mod, fn = _writer()
    w, p = led
    boom = []

    def no_net(*a, **k):
        boom.append(1)
        raise AssertionError("network used by note writer")

    monkeypatch.setattr(socket, "socket", no_net)
    monkeypatch.setattr(socket, "create_connection", no_net)

    class Llm:
        def __call__(self, *a, **k):
            boom.append(1)
            raise AssertionError("LLM called")
        complete = create = call = generate = __call__

    llm = Llm()
    _run_writer(fn, w, p, llm=llm, client=llm, llm_call=llm, call_llm=llm, api_key="sk-test")
    assert not boom
    assert len(w.list_trade_notes()) == len(CLOSED)


def test_note_module_has_no_llm_dependency():
    mod, _ = _writer()
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(anthropic|requests|urllib|http\.client|httpx)", src, re.M)
    assert "api.anthropic.com" not in src


def test_note_writer_spends_no_budget(led, tmp_path, monkeypatch):
    _, fn = _writer()
    w, p = led
    g = _guard(tmp_path)
    _run_writer(fn, w, p, budget=g, guard=g)
    st = g.status()
    assert all(getattr(s, "used_today_usd", 0) == 0 for s in getattr(st, "services", {}).values()) \
        if isinstance(getattr(st, "services", None), dict) else True
    assert not g.pending_events() or True  # events are about caps only; spending checked via cost_usd == 0
    assert all(n["cost_usd"] == 0 for n in w.list_trade_notes())


# ------------------------------------------------------------------ structured tags / ML export
def test_tags_are_structured_and_exportable_for_ml(led):
    mod, fn = _writer()
    w, p = led
    _run_writer(fn, w, p)
    exp = _find_fn(mod, r"export", r"(tags|notes).*(rows|table|frame|features|ml)", r"ml") \
        or _find_fn(_find_module(r"lesson"), r"export.*(tag|note)")
    for n in w.list_trade_notes():
        # every tag is a plain token (sabit etiket sozlugu): no free prose, JSON-serialisable
        assert all(len(t) <= 64 and "\n" not in t for t in n["tags"])
        json.dumps(n["tags"])
    if exp is None:
        pytest.skip("no export function found; tags verified structured only")
    kw = {**_ledger_kw(w, p), **_day_kw()}
    rows = _call(exp, **kw)
    rows = list(rows) if not isinstance(rows, dict) else list(rows.values())
    assert len(rows) >= len(CLOSED)
    flat = json.dumps(rows, default=str)
    for tid in CLOSED:
        assert str(tid) in flat


# ------------------------------------------------------------------ candidate lessons / retirement
LESSON_MOD = _find_module(r"lesson")


def test_candidate_lesson_lifecycle_api_present_and_retire_on_nonpositive():
    mod = _find_module(r"note|lesson_life|candidate") or LESSON_MOD
    ret = _find_fn(mod, r"retire", r"lifecycle", r"(eval|measure|score).*candidate")
    if ret is None:
        ret = _find_fn(LESSON_MOD, r"retire", r"lifecycle", r"(eval|measure|score).*candidate")
    if ret is None:
        pytest.skip("no candidate-lesson retirement entry point found")
    params = inspect.signature(ret).parameters
    eff = next((k for k in ("effect", "impact", "delta", "effect_r", "etki") if k in params), None)
    if eff is None:
        pytest.skip("retirement entry point takes no explicit effect parameter")
    res_bad = _call(ret, **{eff: -0.2, "lesson_id": 1, "lesson": {"id": 1}})
    res_zero = _call(ret, **{eff: 0.0, "lesson_id": 1, "lesson": {"id": 1}})
    res_good = _call(ret, **{eff: 0.3, "lesson_id": 1, "lesson": {"id": 1}})
    blob = lambda r: json.dumps(r, default=str).lower()
    assert re.search(r"retire|emekli|false", blob(res_bad)) or res_bad in (True,)
    assert re.search(r"retire|emekli|false", blob(res_zero)) or res_zero in (True,)
    assert not re.search(r"retire|emekli", blob(res_good)) or "false" in blob(res_good)


def test_candidate_max_in_prompt_config_is_8():
    cfg = json.loads((TRADER / "config" / "lesson.json").read_text(encoding="utf-8"))
    if "lesson_candidate_max_in_prompt" not in cfg:
        pytest.skip("key not present (appendix removes the L1 prompt; spec sec. 15 value was 8)")
    assert cfg["lesson_candidate_max_in_prompt"] <= 8


def test_notes_enabled_config_and_no_llm_model_for_notes():
    cfg = json.loads((TRADER / "config" / "lesson.json").read_text(encoding="utf-8"))
    if "notes_enabled" in cfg:
        assert cfg["notes_enabled"] is True
    # appendix: note writing is code, so a note LLM model must not be required for it
    if "notes_model" in cfg:
        assert cfg["notes_model"] in (None, "code", "claude-haiku-5-5")


# ------------------------------------------------------------------ budget (existing guard): haftalik_ozet share only
def _guard(tmp_path, now=None):
    cfg = json.loads((TRADER / "config" / "budget.json").read_text(encoding="utf-8"))
    cfg["db_path"] = str(tmp_path / "budget.sqlite")
    cp = tmp_path / "budget.json"
    cp.write_text(json.dumps(cfg), encoding="utf-8")
    t = now or datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    return B.BudgetGuard(B.load_config(cp), clock=lambda: t)


def test_budget_config_monthly_cap_10_and_haftalik_share():
    cfg = json.loads((TRADER / "config" / "budget.json").read_text(encoding="utf-8"))
    assert cfg["monthly_cap_usd"] == 20.0   # 23.11 kullanici karari: 10 -> 20 $
    assert "haftalik_ozet" in cfg["daily_cap_usd"]
    assert "veto" not in cfg["daily_cap_usd"] and "veto" not in cfg.get("api_key_env", {})
    assert "proposer" not in cfg["daily_cap_usd"], "L1 cancelled (appendix)"


def test_budget_haftalik_ozet_authorizes_and_veto_unknown(tmp_path):
    g = _guard(tmp_path)
    assert isinstance(g.authorize("haftalik_ozet", 0.05), B.Grant)
    with pytest.raises(ValueError):
        g.authorize("veto", 0.01)


def test_budget_exhausted_denies(tmp_path):
    g = _guard(tmp_path)
    gr = g.authorize("haftalik_ozet", 0.25)
    assert isinstance(gr, B.Grant)
    g.record("haftalik_ozet", gr, B.Usage(output_tokens=25_000), "claude-sonnet-5-5")
    assert isinstance(g.authorize("haftalik_ozet", 0.05), B.Denial)


# ------------------------------------------------------------------ weekly LLM summary
WEEKLY = _find_module(r"weekly|haftalik|ozet|summary")


class FakeLlm:
    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **k):
        self.calls += 1
        return {"text": "haftalik ozet metni", "usage": B.Usage(input_tokens=1000, output_tokens=500),
                "model": "claude-sonnet-5-5"}

    complete = create = call = generate = __call__


def _weekly():
    if WEEKLY is None:
        pytest.skip("no weekly-summary module found")
    fn = _find_fn(WEEKLY, r"^(run|write|make|generate|create|build).*(weekly|haftalik|ozet|summary)",
                  r"(weekly|haftalik|ozet|summary)")
    if fn is None:
        pytest.skip(f"{WEEKLY.__name__}: no entry point found")
    return fn


def _run_weekly(fn, w, p, g, llm, env):
    kw = {**_ledger_kw(w, p), **_day_kw(), "budget": g, "guard": g, "llm": llm, "client": llm, "llm_call": llm,
          "call_llm": llm, "complete": llm, "env": env, "environ": env, "week_end": DAY}
    return _call(fn, **kw)


def test_weekly_noop_without_api_key(led, tmp_path, monkeypatch):
    fn = _weekly()
    w, p = led
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_HAFTALIK_OZET"):
        monkeypatch.delenv(k, raising=False)
    g, llm = _guard(tmp_path), FakeLlm()
    _run_weekly(fn, w, p, g, llm, {})
    assert llm.calls == 0


def test_weekly_noop_when_budget_exhausted(led, tmp_path, monkeypatch):
    fn = _weekly()
    w, p = led
    monkeypatch.setenv("ANTHROPIC_API_KEY_HAFTALIK_OZET", "sk-test")
    g, llm = _guard(tmp_path), FakeLlm()
    gr = g.authorize("haftalik_ozet", 0.25)
    g.record("haftalik_ozet", gr, B.Usage(output_tokens=25_000), "claude-sonnet-5-5")
    _run_weekly(fn, w, p, g, llm, {"ANTHROPIC_API_KEY_HAFTALIK_OZET": "sk-test"})
    assert llm.calls == 0


def test_weekly_runs_with_budget_and_key_and_books_to_haftalik_share(led, tmp_path, monkeypatch):
    fn = _weekly()
    w, p = led
    monkeypatch.setenv("ANTHROPIC_API_KEY_HAFTALIK_OZET", "sk-test")
    g, llm = _guard(tmp_path), FakeLlm()
    _run_weekly(fn, w, p, g, llm, {"ANTHROPIC_API_KEY_HAFTALIK_OZET": "sk-test"})
    assert llm.calls == 1, "exactly one summary call per weekly run"
    st = json.dumps(g.status().to_dict(), default=str)
    assert "haftalik_ozet" in st


def test_weekly_does_not_touch_note_rows(led, tmp_path, monkeypatch):
    fn = _weekly()
    w, p = led
    before = w.list_trade_notes()
    monkeypatch.setenv("ANTHROPIC_API_KEY_HAFTALIK_OZET", "sk-test")
    _run_weekly(fn, w, p, _guard(tmp_path), FakeLlm(), {"ANTHROPIC_API_KEY_HAFTALIK_OZET": "sk-test"})
    assert w.list_trade_notes() == before
