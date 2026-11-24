"""RK-1 gerceklemesinin kendi testleri (docs/motor/12-risk-kademe.md): spec dosyasinin (test_risk_ladder_spec.py) atladigi ya da
yalniz sinif duzeyinde kapsadigi motor kablolamasi: T-28 (backtest ozeti bit-bit), T-43 (kapi sirasi), T-47 (canli kablolama),
T-29/T-30/T-33/T-38 motor kisimlari, durum blogu, LiveBroker.transfers, CLI step-up/sermaye ayrintilari, yapilandirma.
Saat enjekte, ag yok, tum dosyalar tmp altinda; canli/testnet icin FakeExchange."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import test_risk_ladder_spec as S
from test_engine_05_spec import BTC, Env as Env05, T0, make_frame  # noqa: F401
from trader_core import risk as K
from trader_core import risk_ladder as rl
from trader_engine import cli as engine_cli
from trader_engine.clock import SimClock
from trader_engine.config import apply_overrides
from trader_engine.engine import Engine, build_engine
from trader_engine.errors import BrokerError, ConfigError
from trader_engine.gates import EntryGate
from trader_engine.killswitch import Killswitch
from trader_engine.ladder import RiskLadder
from trader_engine.pause import EntryPause

UTC = timezone.utc
ROOT = S.ROOT
H, D, M1 = S.H, S.D, S.M1


# =====================================================================================================
# T-43: kapi sirasi (EntryGate.pre ve Engine._live_gate_code)
# =====================================================================================================
class _Led:
    def entries_allowed(self):
        return SimpleNamespace(ok=True, code="ok")


class _St:
    def kv_get(self, key):
        return None


class _FakeLadder:
    def __init__(self, code):
        self.code = code

    def gate_code(self):
        return self.code


def _gate(tmp, ladder, *, hold=None, kill=False):
    _, cfg = S.write_cfg(tmp, "testnet")
    clock = SimClock(S.NOW0)
    os.makedirs(os.path.dirname(f"{cfg.pause_file}.{cfg.bot}"), exist_ok=True)
    pause = EntryPause(f"{cfg.pause_file}.{cfg.bot}", clock, audit_path=cfg.path("pause_audit.jsonl"), bot=cfg.bot)
    if hold:
        pause.add(hold, "t")
    k = Killswitch(cfg.kill_file, clock)
    if kill:
        k.set("t", "manual")
    g = EntryGate(cfg, _Led(), _St(), k, None, clock, None, lambda p: None, None, pause, ladder)
    return g, clock


@pytest.mark.parametrize("hold,kill,lad,stale,expect", [
    (None, False, "capital_missing", False, "capital_missing"),               # yalniz kademe -> kademe kodu
    ("drawdown_review", False, "capital_missing", False, "drawdown_review"),  # tutus + kademe -> tutus kodu
    ("capital_floor", False, "capital_mismatch", False, "capital_floor"),
    ("user_cmd", False, "ladder_invalid", False, "paused"),
    ("drawdown_review", True, "capital_missing", False, "kill"),              # KILL + tutus + kademe -> kill
    (None, True, "capital_missing", False, "kill"),
    (None, False, "capital_unverified", True, "capital_unverified"),          # stale_data en sonda
    (None, False, None, True, "stale_data"),
    (None, False, None, False, "ok"),
])
def test_t43_entry_gate_order(tmp_path, hold, kill, lad, stale, expect):
    g, clock = _gate(tmp_path, _FakeLadder(lad), hold=hold, kill=kill)
    D0 = clock.now() - (timedelta(hours=5) if stale else timedelta(minutes=1))
    v = g.pre(D0, "1h", True, "1h")
    assert v.code == expect and v.ok is (expect == "ok")
    if expect == "stale_data":
        assert v.skip_reason == "other"
    elif expect != "ok":
        assert v.skip_reason == "entry_gate_closed"


def test_t43_no_ladder_gate_unchanged(tmp_path):
    g, clock = _gate(tmp_path, None)
    assert g.pre(clock.now(), "1h", True, "1h").ok is True


@pytest.mark.parametrize("hold,kill,lad,expect", [
    (None, False, "capital_missing", "capital_missing"), ("drawdown_review", False, "capital_missing", "drawdown_review"),
    ("capital_floor", False, "capital_mismatch", "capital_floor"), ("drawdown_review", True, "ladder_invalid", "kill"),
    (None, False, None, "ok")])
def test_t43_engine_live_gate_code_same_order(tmp_path, hold, kill, lad, expect):
    g, clock = _gate(tmp_path, _FakeLadder(lad), hold=hold, kill=kill)
    ns = SimpleNamespace(_params_ok=True, _started=True, ledger=_Led(), pause=g.pause, ladder=g.ladder)
    assert Engine._live_gate_code(ns, None, kill) == expect


def test_pause_code_priority_capital_floor_first(tmp_path):
    clock = SimClock(S.NOW0)
    p = EntryPause(str(tmp_path / "PAUSE.x"), clock, audit_path=str(tmp_path / "a.jsonl"), bot="x")
    p.add("user_cmd", "t")
    assert p.code() == "paused"
    p.add("drawdown_review", "t")
    assert p.code() == "drawdown_review"
    p.add("capital_floor", "t")
    assert p.code() == "capital_floor"
    assert "capital_floor" in __import__("trader_engine.pause", fromlist=["REASONS"]).REASONS


# =====================================================================================================
# T-47 + kurulum kablolamasi (build_engine)
# =====================================================================================================
def _live_pieces(tmp_path, mode):
    import test_engine_live_spec as LS
    cfg = LS.make_live_cfg(Path(tmp_path), mode=mode)
    clock, broker, view = LS._injected(tmp_path, cfg)
    return LS, cfg, clock, broker, view


def test_t47_live_engine_requires_ladder_and_pause(tmp_path):
    LS, cfg, clock, broker, view = _live_pieces(tmp_path, "live")
    env = {"BINANCE_API_KEY": "k" * 40, "BINANCE_API_SECRET": "s" * 40, "LIVE_CONFIRM": LS.TAG}
    eng = build_engine(cfg, clock=clock, view=view, broker=broker, env=env)
    try:
        assert eng.ladder is not None and eng.gate.ladder is eng.ladder
        assert eng.ladder.enforce is True and eng.ladder.pause is not None
        assert eng.ladder.transfers_fn is not None            # canli: borsa aktarim yoklamasi bagli
        with pytest.raises(ConfigError, match="ladder"):      # ladder olmadan kurulamaz
            Engine(eng.cfg, clock=clock, view=view, broker=broker, ledger=eng.ledger, state=eng.state,
                   signals=eng.signals, strategy=eng.strategy, veto=eng.veto, kill=eng.kill, status=None)
        with pytest.raises(ConfigError):                      # pause olmadan zorlama kurulamaz
            RiskLadder(eng.cfg, clock, None, log=rl.LadderLog(None), enforce=True)
    finally:
        eng.state.close()
        eng.ledger.close()


def test_testnet_engine_enforces_without_transfers(tmp_path):
    LS, cfg, clock, broker, view = _live_pieces(tmp_path, "testnet")
    eng = build_engine(cfg, clock=clock, view=view, broker=broker, env={})
    try:
        assert eng.ladder.enforce is True and eng.ladder.transfers_fn is None
        assert eng.ladder.log.path == cfg.path("risk_ladder.jsonl")
        fields = eng.status_fields()
        blk = fields["risk_ladder"]
        assert blk["enforce"] is True and blk["state"] == "uninitialized" and blk["dep_net"] is None
        assert blk["transfer"] is None
        # kayit yokken kapi (zorlama): bir degerlendirmeden sonra capital_missing, durum kodu da buna doner
        eng._ladder_step(clock.now() + 5 * M1)
        assert eng.ladder.gate_code() == "capital_missing"
        built = eng.status.build(eng)
        assert built["risk_ladder"]["gate_code"] == "capital_missing"      # (gate.code: defter henuz baslatilmadi, ayri kapi)
    finally:
        eng.state.close()
        eng.ledger.close()


def test_paper_engine_observes_and_backtest_has_no_ladder(tmp_path):
    import test_engine_live_spec as LS
    from test_engine_05_spec import SynthView
    cfg = LS.make_cfg(tmp_path, "learner", "paper", (LS.BTC,), 1000.0)
    clock = SimClock(LS.BOOT)
    view = SynthView((LS.BTC,), LS.BOOT - timedelta(days=1), LS.BOOT + timedelta(days=1), clock=None)
    eng = build_engine(cfg, clock=clock, view=view, env={})
    try:
        lad = eng.ladder
        assert lad is not None and lad.enforce is False and lad.log.path is None
        assert lad.risk_config is cfg.risk_config                      # gozlem: boyutlama cfg ile (bit-bit ayni)
        st = lad.log.state()
        assert st.dep_net == cfg.wallet_start and lad.log.rows()[0]["by"] == "engine:paper"
        blk = eng.status.build(eng)["risk_ladder"]
        assert blk["enforce"] is False and blk["state"] == "ok" and blk["would"] is None
        assert not os.path.exists(cfg.path("risk_ladder.jsonl"))       # kagitta dosya yok
    finally:
        eng.state.close()
        eng.ledger.close()
    (tmp_path / "bt").mkdir()
    bcfg = apply_overrides(LS.make_cfg(tmp_path / "bt", "learner", "paper", (LS.BTC,), 1000.0), mode="backtest")
    beng = build_engine(bcfg, clock=SimClock(LS.BOOT), view=view, env={})
    try:
        assert beng.ladder is None and beng.gate.ladder is None
        assert "risk_ladder" not in beng.status.build(beng)
    finally:
        beng.state.close()
        beng.ledger.close()


# =====================================================================================================
# T-28: backtest bit-bit ayni (summary.json / trades.csv ozetleri RK-1 oncesiyle)
# =====================================================================================================
@pytest.mark.skipif(not (ROOT / "var" / "history").exists(), reason="var/history yok (gercek piyasa verisi)")
def test_t28_backtest_digest_unchanged(tmp_path):
    out = tmp_path / "bt"
    out.mkdir()
    r = subprocess.run([sys.executable, "-m", "trader_engine.backtest", "--id", "ref", "--period", "20260301-20260401",
                        "--strategy", "price_action_v1", "--fill-model", "native", "--synthetic-rules",
                        "--out-root", str(out)], cwd=str(ROOT), capture_output=True, text=True, timeout=900,
                       env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    if r.returncode != 0 and "veri" in (r.stdout + r.stderr).lower() and not (ROOT / "user_data").exists():
        pytest.skip("piyasa verisi yok")
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]
    summ = next(out.rglob("ref/summary.json"))
    trades = next(out.rglob("ref/trades.csv"))
    assert hashlib.sha256(summ.read_bytes()).hexdigest().startswith("2bce7db60e19")  # S2 0a: fee_only duzeltmesi (eski onek 5ee22e24485e; yalniz fee_only degisti)
    assert hashlib.sha256(trades.read_bytes()).hexdigest().startswith("89e530326f59")


# =====================================================================================================
# Motor kablolamasi (05 Env + kademe): T-29/T-30/T-33/T-38 motor kisimlari
# =====================================================================================================
def _env05(tmp_path, *, enforce, seed=1000.0, steps=None, **over):
    e = Env05(tmp_path, pause_file=str(tmp_path / "shared" / "PAUSE"), **over)
    os.makedirs(tmp_path / "shared", exist_ok=True)
    pause = EntryPause(f"{e.cfg.pause_file}.{e.cfg.bot}", e.clock, audit_path=e.cfg.path("pause_audit.jsonl"),
                       bot=e.cfg.bot)
    lg = rl.LadderLog(e.cfg.path("risk_ladder.jsonl") if enforce else None)
    b = S.B.__new__(S.B)
    b.log, b.t = lg, T0 - 10 * D
    if seed is not None:
        b.add("initial", amount=seed)
    for fn in steps or ():
        fn(b)
    lad = RiskLadder(e.cfg, e.clock, pause, log=lg, enforce=enforce)
    e.engine.ladder = lad
    e.engine.gate.ladder = lad
    return e, lad, pause, b


def test_t30_enforce_without_log_closes_entries_but_exits_work(tmp_path):
    e, lad, pause, _ = _env05(tmp_path, enforce=True, seed=None)
    e.start()
    try:
        pos = e.open_pos(BTC, T0)                        # kademe yokken giris kapali (kapi capital_missing)
        assert pos is None
        d = e.decisions()[0]
        assert d.final_action == "skipped" and d.veto_reason == "gate:capital_missing"
        assert d.skip_reason == "entry_gate_closed"
    finally:
        e.close()


def test_t30_exit_still_runs_while_gate_closed(tmp_path):
    e, lad, pause, b = _env05(tmp_path, enforce=True, steps=[])
    e.start()
    try:
        D1 = T0 + 2 * H
        e.signal(D1)
        e.engine.ladder = None                            # giris once (kademe olmadan acilir)
        e.engine.gate.ladder = None
        e.decide(D1)
        e.step(D1)
        pos = e.pos()
        assert pos is not None
        e.engine.ladder, e.engine.gate.ladder = lad, lad
        b.add("review_stop", "engine:rk1", equity=800.0, base=1000.0)
        pause.add("drawdown_review", "engine:rk1")
        e.step(D1 + M1, lo=1.0, hi=1.0, price=1.0)        # stop vurulur: cikislar kapisiz
        assert e.pos() is None
        assert pause.code() == "drawdown_review"
    finally:
        e.close()


def test_t29_paper_observation_sizing_unchanged_and_would(tmp_path):
    e, lad, pause, _ = _env05(tmp_path, enforce=False)
    e.start()
    try:
        class Acct:
            equity = wallet = 800.0
        e.broker.account = lambda: Acct()                 # ozsermaye tabanin %80'ine
        e.decide(T0)
        e.decide(T0 + H)
        blk = e.status.build(e.engine)["risk_ladder"]
        assert blk["would"]["kind"] == "review_stop" and blk["enforce"] is False
        assert [h.reason for h in pause.holds()] == ["capital_latch"] and lad.gate_code() is None   # kullanici karari: paper'de de sermaye mandali
        assert lad.risk_config is e.cfg.risk_config
        assert e.engine.status_fields()["gate_code"] == "paused"      # capital_latch tutusu girisleri kapatir; -%20 yine gozlem
    finally:
        e.close()


def test_t38_effective_risk_after_step_down_sizes_next_entry(tmp_path):
    def down(b):
        S.to_km1(b)
    e, lad, pause, b = _env05(tmp_path, enforce=True, steps=[down])
    e.start()
    try:
        lad.tick(e.clock.now() + M1, 1000.0, 1000.0)
        assert lad.risk_config.target_trade_risk == 0.0035 and lad.gate_code() is None
        e.signal(T0 + H)
        e.decide(T0 + H)
        d = [x for x in e.decisions() if x.final_action == "entered"]
        assert d, [x.skip_reason for x in e.decisions()]
        assert d[0].size_risk_amount == pytest.approx(0.0035 * 1000.0, rel=3e-2)      # 0,0035 x ozsermaye
    finally:
        e.close()


def test_t33_review_stop_end_to_end_via_decision_steps(tmp_path):
    e, lad, pause, b = _env05(tmp_path, enforce=True)
    e.start()
    try:
        class Acct:
            equity = wallet = 800.0
        e.broker.account = lambda: Acct()
        e.decide(T0)
        e.decide(T0 + H)                                  # iki ardisik degerlendirme (60 sn kismasi asildi)
        assert [h.reason for h in pause.holds()] == ["capital_latch", "drawdown_review"] and pause.holds()[0].by == "engine:rk1"
        assert b.state().status == "review"
        assert not os.path.exists(e.cfg.kill_file)
        st = e.status.build(e.engine)
        assert st["risk_ladder"]["state"] == "review" and st["gate"]["code"] == "drawdown_review"
        e.signal(T0 + 2 * H)
        e.decide(T0 + 2 * H)
        assert [x.veto_reason for x in e.decisions()][-1] == "gate:drawdown_review"
    finally:
        e.close()


# =====================================================================================================
# RiskLadder ayrintilari (saf sinif; spec testlerinin disinda)
# =====================================================================================================
def test_ladder_tick_never_raises_on_log_read_error(tmp_path):
    class Broken(rl.LadderLog):
        def rows(self):
            raise OSError("disk")

    e = S.Env(tmp_path, log=Broken(str(tmp_path / "x.jsonl")), seed=False)
    e.tick(1000.0)
    assert e.rl.gate_code() == "ladder_invalid" and e.rl.status()["state"] == "invalid"
    assert e.rl.risk_config is e.cfg.risk_config                    # bozukken yapilandirma riski (kapi zaten kapali)


def test_confirmation_counter_resets_after_apply_and_by_action_kind(tmp_path):
    e = S.Env(tmp_path)
    e.tick(900.0)                                         # step_down dd_peak_10 (1/2)
    e.tick(800.0)                                         # farkli eylem (review_stop): sayac 1'e doner
    assert e.kinds() == ["initial"] and e.rl.status()["pending"] == "review_stop"
    e.tick(800.0)
    assert e.kinds()[-1] == "review_stop"
    assert e.rl.status()["pending"] is None


def test_status_block_live_transfer_and_gate_since(tmp_path):
    xfer = [S.X_(S.NOW0 + 30 * M1, 750.0, "t1")]
    e = S.Env(tmp_path, transfers_fn=lambda a, b: list(xfer))
    e.tick(1750.0)
    s = e.rl.status()
    assert s["gate_code"] == "capital_mismatch" and s["gate_since"] is not None
    assert s["transfer"]["ok"] is False and s["transfer"]["unmatched"] == 1 and s["transfer"]["checked_at"] is not None
    assert s["follow"] is None and s["would"] is None
    e.log.append("deposit", "cli:t", e.clock.now(), amount=750.0)
    e.tick(1750.0)                                        # kayit eklendi: yoklama beklemeden eslesir
    s = e.rl.status()
    assert s["gate_code"] is None and s["transfer"]["ok"] is True and s["gate_since"] is None


def test_init_wallet_mismatch_reported_as_detail(tmp_path):
    e = S.Env(tmp_path, amount=250.0, transfers_fn=lambda a, b: [])
    e.tick(300.0, wallet=300.0, flat=True)
    assert e.rl.status()["transfer"]["detail"] == "init_wallet" and e.rl.status()["transfer"]["ok"] is False


def test_init_wallet_check_skipped_after_closed_trades(tmp_path):
    e = S.Env(tmp_path, amount=250.0, transfers_fn=lambda a, b: [])
    e.rl.trades_fn = lambda since: [S.tr(1, S.NOW0 + H, 1.0)]
    e.tick(300.0, wallet=300.0, flat=True)
    assert e.rl.gate_code() is None                       # kapanmis islem varken cuzdan sapmasi denetimi atlanir


def test_stop_states_skip_triggers_but_floor_applies_in_review(tmp_path):
    e = S.Env(tmp_path)
    e.tick(800.0)
    e.tick(800.0)
    assert e.rl.status()["state"] == "review"
    n = len(e.log.rows())
    e.tick(900.0)
    e.tick(1000.0)
    assert len(e.log.rows()) == n                         # inceleme sirasinda iniş/durma satiri yok
    e.tick(600.0)
    e.tick(600.0)
    assert e.rl.status()["state"] == "floor" and "capital_floor" in e.reasons()
    n = len(e.log.rows())
    for _ in range(3):
        e.tick(10.0)
    assert len(e.log.rows()) == n                         # floor: hicbir sey


def test_ladder_py_has_no_forbidden_text():
    src = (ROOT / "src" / "trader_engine" / "ladder.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            assert n.func.attr not in ("remove", "unlink", "replace"), n.func.attr
    for kind in S.FORBIDDEN_KINDS:
        assert f'"{kind}"' not in src, kind


def test_risk_constants_are_code_not_config():
    assert not (ROOT / "config" / "risk_ladder.json").exists()
    for p in (ROOT / "config").glob("*.json"):
        txt = p.read_text(encoding="utf-8")
        for needle in ("STEPS", "STOP_RATIO", "FLOOR_RATIO", "DOWN_1_RATIO", "KM1_MIN_CAPITAL", "ladder_steps"):
            assert needle not in txt, (p.name, needle)


# =====================================================================================================
# Yapilandirma
# =====================================================================================================
def test_config_risk_config_is_stable_object_and_follow_validation(tmp_path):
    _, cfg = S.write_cfg(tmp_path, "paper")
    assert cfg.risk_config is cfg.risk_config and cfg.ladder_follow is None
    (tmp_path / "e").mkdir()
    with pytest.raises(ConfigError):
        S.write_cfg(tmp_path / "e", "paper", {"ladder_follow": ""})
    (tmp_path / "f").mkdir()
    with pytest.raises(ConfigError):
        S.write_cfg(tmp_path / "f", "paper", {"ladder_follow": 5})
    assert apply_overrides(cfg, ladder_follow="/x/y.jsonl").ladder_follow == "/x/y.jsonl"
    with pytest.raises(ConfigError):
        apply_overrides(apply_overrides(cfg, ladder_follow="/x/y.jsonl"), mode="backtest")


# =====================================================================================================
# LiveBroker.transfers ([V-8])
# =====================================================================================================
def test_live_broker_transfers_reads_income_transfer_unsymboled(tmp_path):
    LS, cfg, clock, broker, view = _live_pieces(tmp_path, "testnet")
    calls = []
    base_ms = int(S.NOW0.timestamp() * 1000)
    rows = [{"incomeType": "TRANSFER", "income": "750.00000000", "asset": "USDT", "time": base_ms + 1000, "tranId": 11},
            {"incomeType": "TRANSFER", "income": "750.00000000", "asset": "USDT", "time": base_ms + 1000, "tranId": 11},
            {"incomeType": "TRANSFER", "income": "-100.5", "asset": "USDT", "time": base_ms + 500, "tranId": 12},
            {"incomeType": "TRANSFER", "income": "5", "asset": "BNB", "time": base_ms + 2000, "tranId": 13},
            ]

    def income(symbol, income_type, start_ms, end_ms):
        calls.append((symbol, income_type, start_ms, end_ms))
        return rows

    broker._rest.income = income
    out = broker.transfers(S.NOW0, S.NOW0 + D)
    assert calls == [(None, "TRANSFER", base_ms, base_ms + 86400000)]
    assert [(t.tran_id, t.amount, t.asset) for t in out] == [("12", -100.5, "USDT"), ("11", 750.0, "USDT"),
                                                              ("13", 5.0, "BNB")]
    assert out[0].ts == S.NOW0 + timedelta(milliseconds=500) and all(isinstance(t, rl.Transfer) for t in out)

    def boom(*a):
        raise __import__("trader_engine.marketdata.rest_public", fromlist=["ExchangeError"]).ExchangeError("x")

    broker._rest.income = boom
    with pytest.raises(BrokerError):
        broker.transfers(S.NOW0, S.NOW0 + D)


@pytest.mark.parametrize("bad", [{"income": "nan", "asset": "USDT", "time": 1000, "tranId": 14},
                                 {"income": "5", "asset": "USDT", "time": "x", "tranId": 15},
                                 "not-a-mapping"])
def test_live_broker_transfers_unparseable_row_raises(tmp_path, bad):
    """RK-1 fix 3: ayristirilamayan aktarim satiri atlanmaz (sessiz eksik), istisna yukselir -> cagiran capital_unverified."""
    LS, cfg, clock, broker, view = _live_pieces(tmp_path, "testnet")
    good = {"incomeType": "TRANSFER", "income": "750", "asset": "USDT", "time": int(S.NOW0.timestamp() * 1000), "tranId": 1}
    broker._rest.income = lambda *a: [good, bad]
    with pytest.raises(BrokerError):
        broker.transfers(S.NOW0, S.NOW0 + D)


def test_transfer_read_failure_from_bad_row_keeps_previous_and_goes_unverified(tmp_path):
    state = {"bad": False}

    def fn(since, until):
        if state["bad"]:
            raise BrokerError("transfers: ayristirilamayan aktarim satiri")
        return []

    e = S.Env(tmp_path, transfers_fn=fn)
    e.tick(1000.0)
    assert e.rl.gate_code() is None
    state["bad"] = True
    for _ in range(8):
        e.tick(1000.0, dt=130.0)
    assert e.rl.gate_code() == "capital_unverified"


# =====================================================================================================
# CLI: sermaye/kademe ayrintilari
# =====================================================================================================
def _step_up_ctx(c: S.Cli, *, since_days=60, trades=60, mean_r=0.1):
    """K-1 durumu: step_down `since_days` gun once; `trades` islem (ortalama R `mean_r`)."""
    c.log_path.parent.mkdir(parents=True, exist_ok=True)
    lg = rl.LadderLog(str(c.log_path))
    t0 = S.RN - (since_days + 5) * D
    lg.append("initial", "cli:t", t0, amount=1000.0)
    lg.append("step_down", "engine:rk1", S.RN - since_days * D, step=-1, trigger="dd_peak_10", equity=900.0, peak=1000.0)
    ts = [S.tr(i + 1, S.RN - since_days * D + (i + 1) * H, mean_r) for i in range(trades)]
    return ts


def test_t53b_step_up_conditions_one_by_one(tmp_path, monkeypatch, capsys):
    cases = [
        ({}, 0, None),
        ({"trades": 59}, 5, "islemi"),
        ({"since_days": 41}, 5, "gunu"),                  # 41 < 42 gun (basamak gunu ve son dusus 56'dan az)
        ({"mean_r": -0.01}, 5, "ortalama R"),
        ({"since_days": 55}, 5, "son dusus"),
    ]
    for i, (kw, rc, word) in enumerate(cases):
        d = tmp_path / f"c{i}"
        d.mkdir()
        c = S.Cli(d)
        ts = _step_up_ctx(c, **kw)
        monkeypatch.setattr(engine_cli, "_closed_trades_for_cli", lambda cfg, since, ts=ts: ts)
        n = len(c.rows())
        capsys.readouterr()
        got = c.run("ladder", "step-up", "--decision", "TK-7")
        err = capsys.readouterr().err
        assert got == rc, (kw, err)
        if rc:
            assert word in err and len(c.rows()) == n
        else:
            assert c.state().step == 0 and c.rows()[-1]["kind"] == "step_up" and c.rows()[-1]["decision"] == "TK-7"


def test_step_up_problems_boundaries():
    st = S.to_km1(S.book(1000.0, start=S.NOW0)).state()
    now = st.step_since + 56 * D
    ok = {"step_trades": 60, "step_days": 42, "step_mean_r": 0.0}
    assert rl.step_up_problems(st, ok, now) == []
    assert rl.step_up_problems(st, {**ok, "step_trades": 59}, now)
    assert rl.step_up_problems(st, {**ok, "step_days": 41}, now)
    assert rl.step_up_problems(st, {**ok, "step_mean_r": -0.01}, now)
    assert rl.step_up_problems(st, {**ok, "step_mean_r": None}, now)
    assert rl.step_up_problems(st, ok, st.step_since + 56 * D - timedelta(seconds=1))
    k0 = S.book(1000.0).state()
    assert any("onaylanamaz" in p for p in rl.step_up_problems(k0, ok, now))


def test_cli_capital_withdraw_prefers_profit_and_prints_notice(tmp_path, capsys):
    c = S.Cli(tmp_path)
    c.seed(lambda b: b.add("initial", amount=1000.0))
    capsys.readouterr()
    assert c.run("capital", "withdraw", "--amount", "300", "--equity", "1300") == 0
    out = capsys.readouterr().out
    assert c.rows()[-1]["capital_part"] == 0.0 and c.state().base == 1000.0
    assert "aktarimla eslesene kadar yeni giris kapalidir" in out
    assert c.run("capital", "withdraw", "--amount", "5000", "--equity", "900") == 2     # sermayeyi sifirlar: yazilmaz
    assert len(c.rows()) == 2


def test_cli_capital_list_and_ladder_status(tmp_path, capsys):
    c = S.Cli(tmp_path)
    assert c.run("ladder", "status", by=None) == 0
    assert json.loads(capsys.readouterr().out)["risk_ladder"] is None
    assert c.run("capital", "init", "--amount", "250") == 0
    capsys.readouterr()
    assert c.run("ladder", "status", by=None) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["source"] == "log" and d["risk_ladder"]["stop_at"] == 200.0 and d["risk_ladder"]["floor_at"] == 150.0
    c.write_status(250.0)
    sp = Path(c.cfg.status_path)
    body = json.loads(sp.read_text())
    body["risk_ladder"] = {"state": "ok", "step": 0}
    sp.write_text(json.dumps(body))
    assert c.run("ladder", "status", by=None) == 0
    assert json.loads(capsys.readouterr().out)["source"] == "status.json"


def test_cli_resume_floor_state_rejected_and_by_validated(tmp_path):
    c = S.Cli(tmp_path)
    c.seed(lambda b: (b.add("initial", amount=1000.0), S.to_floor(b)))
    n = len(c.rows())
    assert c.run("ladder", "resume", "--equity", "590") == 2
    assert c.run("capital", "deposit", "--amount", "5", by="x y") == 2                # gecersiz --by
    assert len(c.rows()) == n


def test_cli_write_commands_rejected_in_backtest_mode(tmp_path):
    c = S.Cli(tmp_path, mode="paper")
    for argv in (("capital", "deposit", "--amount", "5"), ("ladder", "resume", "--equity", "9"),
                 ("ladder", "step-up", "--decision", "x")):
        assert c.run(*argv) == 2
    assert not c.log_path.exists()
    assert c.run("capital", "list", by=None) == 0 and c.run("ladder", "status", by=None) == 0


# =====================================================================================================
# RK-1 mentor fixes (v1.1): 1 fail-open tutus, 2 stop satiri yazilamadi / saat gerisi, 4 yapiskan mandal, 6 cikis kodu
# =====================================================================================================
def _boom(*a, **k):
    raise OSError("salt okunur")


def test_fix1_hold_write_failure_latches_ladder_invalid_until_add_succeeds(tmp_path):
    e = S.Env(tmp_path)
    e.log.append("review_stop", "engine:rk1", S.NOW0 + 2 * H, equity=790.0, base=1000.0)
    real_add = e.pause.add
    e.pause.add = _boom
    e.tick(790.0)
    assert e.rl.gate_code() == "ladder_invalid" and e.reasons() == []        # eskiden: None (fail-open)
    e.tick(790.0)
    assert e.rl.gate_code() == "ladder_invalid"
    e.pause.add = real_add                                                   # sonraki basarili ekleme mandali kaldirir
    e.tick(790.0)
    assert sorted(e.reasons()) == ["capital_latch", "drawdown_review"] and e.rl.gate_code() is None


def test_fix1_floor_state_gate_never_none_without_verified_hold(tmp_path):
    e = S.Env(tmp_path)
    e.log.append("review_stop", "engine:rk1", S.NOW0 + 2 * H, equity=790.0, base=1000.0)
    e.log.append("floor_stop", "engine:rk1", S.NOW0 + 3 * H, equity=590.0, dep_net=1000.0)
    e.pause.add = _boom
    e.tick(590.0)
    assert e.rl.gate_code() == "ladder_invalid"


def test_fix1_trigger_with_log_and_pause_both_unwritable_closes_gate(tmp_path, monkeypatch):
    e = S.Env(tmp_path)
    e.log.append = _boom
    e.pause.add = _boom
    for _ in range(3):
        e.tick(700.0)
    assert e.rl.gate_code() == "ladder_invalid"


def test_fix2a_unwritten_stop_row_keeps_gate_closed_and_rehold(tmp_path):
    e = S.Env(tmp_path)
    real_append = e.log.append
    e.log.append = _boom
    e.tick(790.0)
    e.tick(790.0)                                                            # onay: review_stop yazilamadi
    assert e.rl._retry is not None and e.reasons() == ["capital_latch", "drawdown_review"]
    assert e.rl.gate_code() == "ladder_invalid"
    e.pause.remove("drawdown_review", "telegram:x")                          # harici kaldirma
    e.tick(810.0)                                                            # ozsermaye toparlandi
    assert e.reasons() == ["capital_latch", "drawdown_review"]                                # her adimda yeniden kurulur
    assert e.rl.gate_code() == "ladder_invalid"                              # (/kademe_devam red 6'ya takilir)
    assert e.rl._retry[0] == "review_stop"                                   # sonraki tetik stop retry'ini ezmez
    e.log.append = real_append
    e.tick(810.0)
    assert e.log.state().status == "review" and e.rl._retry is None
    assert e.rl.gate_code() is None and e.reasons() == ["capital_latch", "drawdown_review"]


def test_fix2b_retry_with_engine_clock_behind_last_row_is_written_not_dropped(tmp_path):
    e = S.Env(tmp_path)
    e.log.append("peak", "engine:rk1", S.NOW0 + 5 * H, value=1100.0)         # motor saati (NOW0+1h) gerisinde
    real_append = e.log.append
    calls = []

    def flaky(kind, by, now, **f):
        calls.append(kind)
        if len(calls) == 1:
            raise OSError("gecici")
        return real_append(kind, by, now, **f)

    e.log.append = flaky
    for _ in range(4):
        e.tick(790.0)                                                        # base 1000 -> durma; ilk yazma duser
    st = e.log.state()
    assert st.status == "review" and e.reasons() == ["capital_latch", "drawdown_review"]
    last = e.log.rows()[-1]
    assert last["kind"] == "review_stop" and rl.parse_at(last["at"]) >= S.NOW0 + 5 * H


def test_fix2b_clock_behind_direct_write_uses_last_row_at(tmp_path):
    e = S.Env(tmp_path)
    e.log.append("peak", "engine:rk1", S.NOW0 + 5 * H, value=1000.5)
    for _ in range(3):
        e.tick(700.0)
    assert e.log.state().status == "review" and e.rl._retry is None


def _xf(ts, amount=750.0, tid="t1"):
    return rl.Transfer(ts=ts, amount=amount, tran_id=tid, asset="USDT")


def test_fix4_unrecorded_exchange_transfer_stays_mismatch_after_five_days_and_sticky(tmp_path):
    x = [_xf(S.NOW0 + 2 * H)]
    e = S.Env(tmp_path, transfers_fn=lambda since, until: list(x))
    e.tick(1750.0)
    assert e.rl.gate_code() == "capital_mismatch"
    for _ in range(3):
        e.tick(250.0, dt=2 * D.total_seconds())                              # 6 gun sonra: hala 7 gun penceresinde
    assert e.rl.gate_code() == "capital_mismatch"
    assert not {"review_stop", "floor_stop", "step_down", "peak"} & set(e.kinds())
    for _ in range(3):
        e.tick(250.0, dt=3 * D.total_seconds())                              # pencereden dustu (>7 gun): mandal tutar
    assert e.rl.gate_code() == "capital_mismatch"
    assert not {"review_stop", "floor_stop", "step_down"} & set(e.kinds())
    e.log.append("adjust", "cli:t", e.clock.now(), amount=-750.0, note="operator duzeltti")   # operator eylemi: seq degisir
    e.tick(250.0, dt=130.0)
    assert e.rl.gate_code() is None


def test_fix4_logged_deposit_without_transfer_sticky_past_log_side_five_days(tmp_path):
    e = S.Env(tmp_path, transfers_fn=lambda since, until: [])
    e.log.append("deposit", "cli:t", S.NOW0 + 2 * H, amount=750.0)
    e.tick(250.0)
    assert e.rl.gate_code() == "capital_mismatch"
    for _ in range(3):
        e.tick(250.0, dt=3 * D.total_seconds())                              # gunluk tarafi 5 gunu asti
    assert e.rl.gate_code() == "capital_mismatch"
    assert not {"review_stop", "floor_stop"} & set(e.kinds())                # yanlis yon stop yok


def test_fix4_late_arriving_transfer_clears_latch_without_operator(tmp_path):
    x = []
    e = S.Env(tmp_path, transfers_fn=lambda since, until: list(x))
    e.log.append("deposit", "cli:t", S.NOW0 + 2 * H, amount=750.0)
    e.tick(1750.0)
    assert e.rl.gate_code() == "capital_mismatch"
    x.append(_xf(S.NOW0 + 3 * H))                                            # aktarim gec geldi: gercek eslesme
    e.tick(1750.0, dt=130.0)
    assert e.rl.gate_code() is None and e.rl.status()["transfer"]["ok"] is True


def test_fix4_r1_exchange_side_latch_not_cleared_by_window_rematch(tmp_path):
    """Mentor R1: kayitli 750 + eslesen B; 36 saat sonra kayitsiz A (+750). B 7 gun penceresinden dusunce gunluk satiri
    A ile yeniden eslesir; borsa tarafi mandal operator eylemi (seq) olmadan KALKMAMALI, tepe yazilmamali."""
    t0 = S.NOW0 + H / 2
    x = [_xf(t0, tid="B")]
    e = S.Env(tmp_path, transfers_fn=lambda since, until: [t for t in x if since <= t.ts <= until])
    e.log.append("deposit", "cli:t", t0, amount=750.0)
    e.tick(1750.0)
    assert e.rl.gate_code() is None
    seq0 = e.log.state().seq
    x.append(_xf(t0 + 36 * H, tid="A"))
    e.tick(2500.0, dt=36 * H.total_seconds())
    assert e.rl.gate_code() == "capital_mismatch"
    for _ in range(14):
        e.tick(2500.0, dt=12 * H.total_seconds())                            # ~9. gun: B pencereden duser
        assert e.rl.gate_code() == "capital_mismatch"
    assert e.log.state().seq == seq0 and "peak" not in e.kinds()


def test_fix6_exit_ladder_is_five_not_engine_four():
    assert engine_cli.EXIT_LADDER == engine_cli.EXIT_FINDINGS == 5
    assert engine_cli.EXIT_LADDER != engine_cli.EXIT_ENGINE == 4
