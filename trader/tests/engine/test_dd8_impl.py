"""DD-8 (canli baslangic guvenligi) gerceklestirme testleri: O4, O8, O6, D7, D2, E1, E2. Yalniz sahteler; ag yok.
(Sartname testleri `test_dd8_spec.py`te ayri ajan tarafindan; bu dosya gerceklemenin kendi sinamasidir.)"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import test_engine_live_spec as T
from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from test_live_broker_impl_smoke import XRP, build, req
from trader_core import ledger as L
from trader_engine import stamp as ST
from trader_engine.config import (absolutize_paths, load_cli_config, load_engine_config)
from trader_engine.engine import EngineExit, build_engine
from trader_engine.errors import ConfigError, StateError
from trader_engine.state import StateStore

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


# ============================================================================================ config (O8 2.1, E1)
def _tree(tmp: Path, mode="testnet", **over):
    cdir = tmp / "config"
    cdir.mkdir(parents=True, exist_ok=True)
    base = json.loads((ROOT / "config" / "engine.base.json").read_text())
    (cdir / "engine.base.json").write_text(json.dumps(base))
    (cdir / "engine.learner.json").write_text(json.dumps({"bot": "learner"}))
    ov = json.loads((ROOT / "config" / "engine.testnet.json").read_text())
    ov["mode"] = mode
    ov.update(over)
    (cdir / f"engine.{mode}.json").write_text(json.dumps(ov))
    return cdir


@pytest.mark.parametrize("mode", ["testnet", "live"])
@pytest.mark.parametrize("vd", ["var", "./var", "var/", "/x/y/var"])
def test_var_dir_var_rejected_for_testnet_live(tmp_path, mode, vd):
    cdir = _tree(tmp_path, mode, var_dir=vd)
    with pytest.raises(ConfigError, match="var_dir"):
        load_engine_config(cdir / "engine.base.json", cdir / "engine.learner.json", overlay_path=cdir / f"engine.{mode}.json")


def test_var_dir_ok_variants_and_paper_unchanged(tmp_path):
    for vd in ("var-testnet", "/x/var-live"):
        cdir = _tree(tmp_path / vd.strip("/").replace("/", "_"), "testnet", var_dir=vd)
        load_engine_config(cdir / "engine.base.json", cdir / "engine.learner.json", overlay_path=cdir / "engine.testnet.json")
    paper = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / "engine.learner.json")
    assert paper.var_dir == "var" and paper.kill_file == "shared/KILL"


@pytest.mark.parametrize("field,val", [("kill_file", "shared/KILL"), ("kill_file", "/r/shared/KILL"),
                                       ("pause_file", "shared/PAUSE"), ("pause_file", "/r/shared/PAUSE")])
def test_shared_paper_files_rejected(tmp_path, field, val):
    cdir = _tree(tmp_path, "testnet", **{field: val})
    with pytest.raises(ConfigError):
        load_engine_config(cdir / "engine.base.json", cdir / "engine.learner.json", overlay_path=cdir / "engine.testnet.json")


def test_load_cli_config_absolutizes_testnet_and_paper(tmp_path):
    cdir = _tree(tmp_path, "testnet")
    cfg = load_cli_config(cdir, env="testnet")
    assert cfg.kill_file == str(tmp_path / "shared/testnet/KILL")
    assert cfg.pause_file == str(tmp_path / "shared/testnet/PAUSE")
    assert cfg.var_dir == str(tmp_path / "var-testnet")
    p = load_cli_config(cdir)
    assert p.kill_file == str(tmp_path / "shared/KILL") and p.pause_file == str(tmp_path / "shared/PAUSE")
    assert p.var_dir == "var" and p.market_db == "var/market.sqlite"
    # dizin adi `config` degilse kok = dizinin kendisi
    other = tmp_path / "cfgx"
    other.mkdir()
    for f in (cdir).iterdir():
        (other / f.name).write_text(f.read_text())
    assert load_cli_config(other, env="testnet").pause_file == str(other / "shared/testnet/PAUSE")
    # mutlak alan degismez
    assert absolutize_paths(cfg, cdir / "engine.base.json") == cfg


def test_build_engine_rejects_relative_paths(tmp_path):
    cfg = T.make_live_cfg(tmp_path, var_dir=str(tmp_path / "var-testnet"))
    import dataclasses
    for fld in ("kill_file", "pause_file", "var_dir"):
        bad = dataclasses.replace(cfg, **{fld: "rel/" + ("x" if fld == "var_dir" else "y")})
        with pytest.raises(ConfigError, match=f"relative_path:{fld}"):
            build_engine(bad, env={})


# ============================================================================================ ledger meta + state
def test_set_meta_once_and_get_meta(tmp_path):
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True)
    try:
        assert led.get_meta("account_stamp") is None
        led.set_meta_once("account_stamp", "testnet:x")
        led.set_meta_once("account_stamp", "testnet:x")
        assert led.get_meta("account_stamp") == "testnet:x"
        with pytest.raises(L.LedgerError):
            led.set_meta_once("account_stamp", "live:x")
        assert led.get_meta("account_stamp") == "testnet:x"
    finally:
        led.close()


def test_state_zero_byte_check_uses_given_ledger_path_only(tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    led = L.open_ledger(str(other / "led.sqlite"), "learner", create=True)
    led.init_params({k: getattr(__import__("trader_core.signals", fromlist=["x"]).DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS},
                    reason="t")
    led.close()
    con = sqlite3.connect(other / "led.sqlite")
    con.execute("PRAGMA journal_mode=DELETE")
    con.close()
    # defter dolu degil (karar/islem satiri yok): StateError yok
    sp = tmp_path / "s" / "state.sqlite"
    sp.parent.mkdir()
    sp.write_bytes(b"")
    StateStore(str(sp), bot="learner", ledger_path=str(other / "led.sqlite")).close()
    sp.write_bytes(b"")
    StateStore(str(sp), bot="learner", ledger_path=None).close()
    assert "ledger.sqlite" not in (SRC / "trader_engine" / "state.py").read_text()


# ============================================================================================ stamp (O8)
def _stamp_env(tmp: Path, mode="testnet", tag="sub-acct"):
    tmp.mkdir(parents=True, exist_ok=True)
    cfg = T.make_live_cfg(tmp, mode=mode, var_dir=str(tmp / "var-x"), live_over={"account_tag": tag})
    for p in (cfg.ledger_path, cfg.state_path):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    return cfg


def _open(cfg):
    st = StateStore(cfg.state_path, bot="learner")
    led = L.open_ledger(cfg.ledger_path, "learner", create=True)
    return st, led


def _verify(cfg):
    st, led = _open(cfg)
    try:
        ST.verify_or_init_stamp(cfg, st, led)
        return st.kv_get("account_stamp"), led.get_meta("account_stamp")
    finally:
        st.close()
        led.close()


def _code(cfg):
    with pytest.raises(EngineExit) as ei:
        _verify(cfg)
    assert ei.value.code == 8
    return str(ei.value)


def test_stamp_first_open_writes_both_then_idempotent(tmp_path):
    cfg = _stamp_env(tmp_path)
    assert _verify(cfg) == ("testnet:sub-acct", "testnet:sub-acct")
    assert _verify(cfg) == ("testnet:sub-acct", "testnet:sub-acct")


def test_stamp_foreign_account_or_mode(tmp_path):
    cfg = _stamp_env(tmp_path)
    _verify(cfg)
    other = T.make_live_cfg(tmp_path, mode="testnet", var_dir=str(tmp_path / "var-x"), live_over={"account_tag": "other-acct"})
    assert _code(other) == "state_stamp_mismatch"
    live = T.make_live_cfg(tmp_path, mode="live", var_dir=str(tmp_path / "var-x"), live_over={"account_tag": "sub-acct"})
    assert _code(live) == "state_stamp_mismatch"


def test_stamp_state_deleted_is_state_missing(tmp_path):
    cfg = _stamp_env(tmp_path)
    _verify(cfg)
    for suf in ("", "-wal", "-shm"):
        try:
            os.unlink(cfg.state_path + suf)
        except FileNotFoundError:
            pass
    assert _code(cfg) == "state_missing"
    assert not _has_stamp(cfg.state_path)                              # yeni state damga icermez
    # 0 bayta kesilmis: ayni
    Path(cfg.state_path).write_bytes(b"")
    assert _code(cfg) == "state_missing"


def _has_stamp(path):
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT 1 FROM kv WHERE k='account_stamp'").fetchone() is not None
    finally:
        con.close()


def test_stamp_half_first_open_and_ledger_missing_or_mismatch(tmp_path, monkeypatch):
    cfg = _stamp_env(tmp_path)
    st, led = _open(cfg)
    with st.tx():
        st.kv_set("account_stamp", "testnet:sub-acct")                 # yarim ilk acilis: yalniz state damgali
    st.close()
    led.close()
    assert _verify(cfg) == ("testnet:sub-acct", "testnet:sub-acct")    # 7: defter bos -> damgalanir
    # 8: defter dolu + damgasiz  -> yeni dizin kur, defteri doldur
    cfg2 = _stamp_env(tmp_path / "b")
    st, led = _open(cfg2)
    with st.tx():
        st.kv_set("account_stamp", "testnet:sub-acct")
    st.close()
    led.close()
    monkeypatch.setattr(ST, "ledger_has_history", lambda path: True)        # defter dolu (islem/karar satiri var)
    assert _code(cfg2) == "ledger_stamp_missing"
    monkeypatch.undo()
    # 2: defter baska damgali
    cfg3 = _stamp_env(tmp_path / "c")
    st, led = _open(cfg3)
    with st.tx():
        st.kv_set("account_stamp", "testnet:sub-acct")
    led.set_meta_once("account_stamp", "testnet:zzz-acct")
    st.close()
    led.close()
    assert _code(cfg3) == "ledger_stamp_mismatch"


def test_stamp_unstamped_nonvirgin_and_paper_trace(tmp_path):
    cfg = _stamp_env(tmp_path)
    st, led = _open(cfg)
    with st.tx():
        st.kv_set("initialized_at", "2026-01-01T00:00:00Z")
    st.close()
    led.close()
    assert _code(cfg) == "state_stamp_missing"
    cfg2 = _stamp_env(tmp_path / "p")
    st, led = _open(cfg2)
    with st.tx():
        st.kv_set("broker_snapshot", "{}")
    st.close()
    led.close()
    assert _code(cfg2) == "state_stamp_mismatch"


def test_stamp_paper_read_only(tmp_path):
    cfg = T.make_live_cfg(tmp_path, mode="testnet", var_dir=str(tmp_path / "var-x"))
    import dataclasses
    paper = dataclasses.replace(cfg, mode="paper", live=None)
    for p in (paper.ledger_path, paper.state_path):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    assert _verify(paper) == (None, None)
    st, led = _open(paper)
    with st.tx():
        st.kv_set("account_stamp", "live:x")
    st.close()
    led.close()
    assert _code(paper) == "state_stamp_mismatch"


def test_init_ledger_refuses_foreign_stamp(tmp_path):
    from trader_engine import cli
    cdir = _tree(tmp_path, "testnet", var_dir=str(tmp_path / "var-testnet"))
    cfg = load_cli_config(cdir, env="testnet")
    Path(cfg.ledger_path).parent.mkdir(parents=True)
    led = L.open_ledger(cfg.ledger_path, "learner", create=True)
    led.set_meta_once("account_stamp", "live:sub-acct")
    led.close()
    rc = cli.main(["init-ledger", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"])
    assert rc == 8
    led = L.open_ledger(cfg.ledger_path, "learner", create=False, read_only=True)
    with pytest.raises(L.LedgerError):
        led.get_active_params()
    led.close()


# ============================================================================================ O6 izin denetimi
FIELDS = (("enableReading", True), ("enableFutures", True), ("enableWithdrawals", False),
          ("enableInternalTransfer", False), ("permitsUniversalTransfer", False), ("ipRestrict", True))


def _exit(env="live", pre=None, environ=None):
    with pytest.raises(EngineExit) as ei:
        build(env=env, pre=pre, environ=environ)
    return ei.value.code, str(ei.value)


@pytest.mark.parametrize("attest", [None, "TODAY"])
@pytest.mark.parametrize("field,want", FIELDS)
def test_permission_wrong_value_each_field(field, want, attest):
    environ = {} if attest is None else {"LIVE_PERMISSION_ATTESTED": "2026-12-28"}
    code, msg = _exit(pre=lambda ex: ex.restrictions.__setitem__(field, not want), environ=environ)
    assert (code, msg) == (8, f"key_permission:{field}")


def test_permission_violation_beats_missing_fields():
    def pre(ex):
        ex.restrictions.clear()
        ex.restrictions["enableWithdrawals"] = True
    assert _exit(pre=pre, environ={"LIVE_PERMISSION_ATTESTED": "2026-12-28"}) == (8, "key_permission:enableWithdrawals")


@pytest.mark.parametrize("attest", [None, "2026-12-28"])
@pytest.mark.parametrize("kind", ["list", "missing", "string_bool"])
def test_permission_unverifiable(kind, attest):
    def pre(ex):
        if kind == "list":
            ex.restrictions = []
        elif kind == "missing":
            ex.restrictions.pop("ipRestrict")
        else:
            ex.restrictions["enableReading"] = "true"
    environ = {} if attest is None else {"LIVE_PERMISSION_ATTESTED": attest}
    assert _exit(pre=pre, environ=environ) == (8, "key_permission_unverifiable")


def test_permission_all_ok_passes_and_attestation_warns(caplog):
    caplog.set_level(logging.WARNING)
    b, ex, _ = build(env="live", environ={"LIVE_PERMISSION_ATTESTED": "2026-12-28"})
    assert ex.count("apiRestrictions") == 1
    assert any("LIVE_PERMISSION_ATTESTED" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("resp,exp", [
    (FakeResp(503, {"code": -1001, "msg": "x"}), (5, "exchange_unreachable")),
    (FakeResp(451, {"code": 0, "msg": "x"}), (8, "region_blocked")),
    (FakeResp(403, {"code": 0, "msg": "x"}), (8, "region_blocked")),
    (FakeResp(401, {"code": -2015, "msg": "x"}), (8, "auth_failed")),
    (FakeResp(400, {"code": -1100, "msg": "x"}), (8, "key_permission_unverifiable")),
    (FakeResp(400, {"code": -1021, "msg": "x"}), (5, "exchange_unreachable")),
])
def test_permission_error_mapping(resp, exp):
    def pre(ex):
        for _ in range(8):
            ex.inject("apiRestrictions", resp)
    assert _exit(pre=pre, environ={"LIVE_PERMISSION_ATTESTED": "2026-12-28"}) == exp


def test_permission_testnet_skips_and_no_attest_code_in_src():
    b, ex, _ = build(env="testnet")
    assert ex.count("apiRestrictions") == 0
    for f in (SRC).rglob("*.py"):
        t = f.read_text()
        assert "fromisoformat(att" not in t
        for m in re.finditer(r"LIVE_PERMISSION_ATTESTED", t):
            line = t[:m.start()].count("\n")
            ctx = "\n".join(t.splitlines()[max(0, line - 1):line + 2])
            assert "log." in ctx or "logging" in ctx or '"""' in ctx or "#" in ctx, (f, ctx)


# ============================================================================================ O4 cuzdan tavani
def _wenv(tmp, wallet="100", **kw):
    e = T.LiveEnv(tmp, var_dir=str(tmp / "var-testnet"), **kw)
    e.ex.wallet = Decimal(wallet)
    return e


def _holds(e):
    return {h.reason: h for h in e.engine.pause.holds()}


def test_startup_wallet_cap_findings_and_unreadable():
    b, ex, _ = build(env="testnet", pre=lambda e: setattr(e, "wallet", Decimal("1000.01")))
    assert b.startup_findings == ("wallet_above_expected",)
    b, ex, _ = build(env="live", pre=lambda e: setattr(e, "wallet", Decimal("1000")))
    assert b.startup_findings == ()
    b, ex, _ = build(env="live", pre=lambda e: setattr(e, "wallet", Decimal("999.99")))
    assert b.startup_findings == ()
    for bad in (None, "abc", "nan"):
        with pytest.raises(EngineExit) as ei:
            build(env="live", pre=lambda ex, bad=bad: _inject_wallet(ex, bad))
        assert ei.value.code == 8 and "wallet_unreadable" in str(ei.value)


def _inject_wallet(ex, bad):
    body = {"canTrade": True} if bad is None else {"canTrade": True, "totalWalletBalance": bad}
    ex.inject("/fapi/v2/account", FakeResp(200, body))


def test_o4_start_with_wallet_above_cap_holds_entries_and_protects(tmp_path):
    e = _wenv(tmp_path, "1000.01")
    try:
        e.boot()
        h = _holds(e)["wallet_above_expected"]
        assert h.by == "engine:wallet_cap" and "wallet=" in h.note and "max=" in h.note
        assert e.engine.gate.pre  # kapi var
        assert e.engine._live_gate_code(None, False) == "paused"
        e.enter()
        assert e.posted("e") == [] and e.pos() is None
    finally:
        e.close()


def test_o4_hold_added_before_protect_first(tmp_path):
    e = _wenv(tmp_path, "1000.01")
    order = []
    real_pf = e.engine.protect_first
    e.engine.protect_first = lambda: (order.append(("pf", "wallet_above_expected" in _holds(e))), real_pf())[1]
    try:
        e.boot()
        assert order[0] == ("pf", True)
    finally:
        e.close()


def test_o4_runtime_hold_persistence_and_clear(tmp_path):
    from trader_engine import cli
    e = _wenv(tmp_path, "100")
    try:
        e.boot()
        assert "wallet_above_expected" not in _holds(e)
        n0 = e.ex.count("/fapi/v2/account")
        e.ex.wallet = Decimal("1500")
        e.tick(6)                                                     # hesap onbellegi (2 sn) doldu
        assert "wallet_above_expected" in _holds(e)
        e.ex.wallet = Decimal("100")
        for _ in range(3):
            e.tick(6)
        assert "wallet_above_expected" in _holds(e)                   # kendiliginden kalkmaz
        # CLI ile kaldirilir
        cdir = e.tmp
        _ = n0, cdir
        assert e.engine.pause.remove("wallet_above_expected", "x") is True
        e.tick(6)
        assert "wallet_above_expected" not in _holds(e)
        e.ex.wallet = Decimal("1500")
        e.tick(6)
        assert "wallet_above_expected" in _holds(e)                   # hala ustteyse yeniden eklenir
        assert cli  # noqa
    finally:
        e.close()


def test_o4_runtime_no_extra_account_requests(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    a = _wenv(tmp_path / "a", "100")
    b = _wenv(tmp_path / "b", "100")
    try:
        a.boot()
        b.boot()
        a.ex.wallet = Decimal("1500")
        na, nb = a.ex.count("/fapi/v2/account"), b.ex.count("/fapi/v2/account")
        a.tick(6)
        b.tick(6)
        assert a.ex.count("/fapi/v2/account") - na == b.ex.count("/fapi/v2/account") - nb
    finally:
        a.close()
        b.close()


def test_o4_pause_add_failure_memory_lock(tmp_path):
    e = _wenv(tmp_path, "1000.01")
    e.engine.pause.add = lambda *a, **k: False
    try:
        e.boot()
        assert "wallet_above_expected" not in _holds(e)
        assert e.engine._wallet_lock is True
        assert e.engine._live_gate_code(None, False) == "paused"
        e.enter()
        assert e.posted("e") == [] and e.pos() is None
        # korumalar calismaya devam eder
        e.tick(6)
    finally:
        e.close()


def test_o4_paper_never_runs_wallet_step(tmp_path):
    import dataclasses
    e = _wenv(tmp_path, "100")
    try:
        e.boot()
        paper_cfg = dataclasses.replace(e.engine.cfg, mode="paper", live=None)
        e.engine.cfg = paper_cfg
        e.engine._wallet_cap_step(1e9)
        assert "wallet_above_expected" not in _holds(e)
    finally:
        e.close()


def test_pause_reasons_all_have_telegram_text():
    from trader_core.telegram import NEDEN_TR
    from trader_engine.pause import REASONS
    for r in REASONS:
        assert r in NEDEN_TR, r
    assert "wallet_above_expected" in REASONS


# ============================================================================================ D2 hesap modu
def _prep():
    b, ex, clock = build()
    b.prepare(XRP, 3)
    return b, ex, clock


@pytest.mark.parametrize("mut", ["lev", "cross"])
def test_d2_drift_blocks_entry(mut, caplog):
    b, ex, clock = _prep()
    if mut == "lev":
        ex.lev["XRPUSDT"] = 4
    else:
        ex.margin_type["XRPUSDT"] = "cross"
    caplog.set_level(logging.CRITICAL)
    r = b.market_order(req("entry", 10.0))
    assert r.status == "rejected" and r.reason == "not_prepared"
    assert ex.count("/fapi/v1/order", "POST") == 0
    assert b.counters()["account_mode_drift"] == 1
    assert any("account_mode_drift" in x.getMessage() for x in caplog.records)
    # duzeltilirse sonraki giris yeniden baslatmadan gecer
    ex.lev["XRPUSDT"], ex.margin_type["XRPUSDT"] = 3, "isolated"
    assert b.market_order(req("entry", 10.0, seq=1)).status == "filled"


def test_d2_fresh_read_before_post_one_per_entry_and_stale_cache_trap():
    b, ex, clock = _prep()
    n0 = sum(1 for m, p, q in ex.requests if p == "/fapi/v2/positionRisk" and q.get("symbol") == "XRPUSDT")
    assert b.market_order(req("entry", 10.0)).status == "filled"
    n1 = sum(1 for m, p, q in ex.requests if p == "/fapi/v2/positionRisk" and q.get("symbol") == "XRPUSDT")
    assert n1 - n0 == 1
    idx_read = max(i for i, (m, p, q) in enumerate(ex.requests) if p == "/fapi/v2/positionRisk" and q.get("symbol") == "XRPUSDT")
    idx_post = max(i for i, (m, p, q) in enumerate(ex.requests) if p == "/fapi/v1/order" and m == "POST")
    assert idx_read < idx_post
    b.poll(clock_now(b))
    ex.lev["XRPUSDT"] = 5                                             # _sync'ten sonra degisti
    assert b.market_order(req("entry", 10.0, seq=2)).reason == "not_prepared"


def clock_now(b):
    return b._clock.now()


def test_d2_unverified_cases_and_exit_unaffected():
    from trader_engine.marketdata.rest_public import ExchangeBan  # noqa: F401
    cases = [FakeResp(503, {"code": -1001, "msg": "x"}), FakeResp(429, {"code": -1003, "msg": "x"}, {"Retry-After": "30"}),
             FakeResp(200, []), FakeResp(200, [{"symbol": "XRPUSDT", "marginType": "isolated"}])]
    for resp in cases:
        b, ex, _ = _prep()
        for _ in range(6):
            ex.inject("/fapi/v2/positionRisk", resp)
        n_orders = ex.count("/fapi/v1/order", "POST")
        r = b.market_order(req("entry", 10.0))
        assert r.status == "rejected" and r.reason == "not_prepared"
        assert ex.count("/fapi/v1/order", "POST") == n_orders
        assert b.counters()["account_mode_unverified"] == 1
    # cikis/stop sapmada reddedilmez ve ek okuma yapmaz
    b, ex, _ = _prep()
    assert b.market_order(req("entry", 10.0)).status == "filled"
    ex.lev["XRPUSDT"] = 9
    n = sum(1 for m, p, q in ex.requests if p == "/fapi/v2/positionRisk" and q.get("symbol") == "XRPUSDT")
    assert b.place_stop(req("stop", 10.0, 1.9)).status == "accepted"
    assert b.market_order(req("exit", 10.0)).status == "accepted"
    assert sum(1 for m, p, q in ex.requests if p == "/fapi/v2/positionRisk" and q.get("symbol") == "XRPUSDT") == n
    assert ex.count("marginType", "POST") + ex.count("leverage", "POST") <= 4   # yalniz acilis (2 cift x 2)


# ============================================================================================ D7 sira
def _market(cfg):
    from trader_engine.marketdata.store import MarketStore
    Path(cfg.market_db).parent.mkdir(parents=True, exist_ok=True)
    MarketStore(cfg.market_db).close()


def test_d7_lock_before_any_http(tmp_path, monkeypatch):
    import fcntl
    from trader_engine.exchange import binance_rest as BR
    cfg = T.make_live_cfg(tmp_path, var_dir=str(tmp_path / "var-testnet"))
    Path(cfg.state_path).parent.mkdir(parents=True, exist_ok=True)
    _market(cfg)
    ex = FakeExchange(lambda: 1_800_000_000_000)
    orig = BR.SignedRestClient
    monkeypatch.setattr(BR, "SignedRestClient", lambda *a, **k: orig(*a, **{**k, "session": ex}))
    fd = os.open(cfg.state_path + ".lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(StateError):
            build_engine(cfg, env={"BINANCE_API_KEY": KEY, "BINANCE_API_SECRET": SECRET})
    finally:
        os.close(fd)
    assert ex.requests == []


def test_d7_startup_failure_releases_lock(tmp_path):
    import dataclasses

    class Boom:
        def startup_check(self):
            raise EngineExit(8, "account_cannot_trade")

        def __getattr__(self, n):
            raise AssertionError(f"broker.{n} stamp/kilit oncesi cagrildi")

    cfg = T.make_live_cfg(tmp_path, var_dir=str(tmp_path / "var-testnet"))
    _market(cfg)
    # enjekte broker: kilit + damga broker'a dokunmadan tamamlanir; sonra motor kurulumu surer / hata kilidi sizdirmaz
    try:
        build_engine(cfg, broker=Boom(), env={})
    except Exception:  # noqa: BLE001
        pass
    StateStore(cfg.state_path, bot="learner").close()                  # kilit sizmamis
    assert dataclasses  # noqa


# ============================================================================================ E2 kaynak denetimi + guard
def test_e2_scripts_use_load_cli_config():
    for n in ("smoke_live.py", "smoke_testnet.py"):
        t = (ROOT / "scripts" / n).read_text()
        assert "load_engine_config(" not in t and "load_cli_config(" in t, n


def test_e2_guard_config_looks_only_at_last_components():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import smoke_testnet_lib as S
    cdir_root = Path("/tmp/testnet-x")

    class C:
        mode = "testnet"
        var_dir = str(cdir_root / "var")
        kill_file = str(cdir_root / "shared" / "KILL")
        pause_file = str(cdir_root / "shared" / "PAUSE")
    with pytest.raises(S.SafetyError):
        S.guard_config(C)
    C.var_dir, C.kill_file, C.pause_file = (str(cdir_root / "var-testnet"), str(cdir_root / "shared/testnet/KILL"),
                                            str(cdir_root / "shared/testnet/PAUSE"))
    S.guard_config(C)


# ============================================================================================ E4
def test_e4_health_and_backup(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import health_backup as HB
    import health_run as HR
    led = tmp_path / "ledger.sqlite"
    Path(str(led) + ".spool.corrupt.jsonl").write_text('{"a":1}\n{"b":2}\n')
    assert HR.probe_ledger(str(led), "learner", None).spool_corrupt_lines == 2
    Path(str(led) + ".spool.corrupt.jsonl").unlink()
    assert HR.probe_ledger(str(led), "learner", None).spool_corrupt_lines == 0
    Path(str(led) + ".spool.corrupt.jsonl").mkdir()
    assert HR.probe_ledger(str(led), "learner", None).spool_corrupt_lines is None
    # yedek
    dest = tmp_path / "dest"
    dest.mkdir()
    Path(str(led) + ".spool.corrupt.jsonl").rmdir()
    assert HB._copy_corrupt(led, dest, "ledger_learner.sqlite") == 0
    Path(str(led) + ".spool.corrupt.jsonl").write_text('{"a":1}\n')
    assert HB._copy_corrupt(led, dest, "ledger_learner.sqlite") == 8
    assert (dest / "ledger_learner.sqlite.spool.corrupt.jsonl").read_text() == '{"a":1}\n'


def test_e4_health_checks_and_alerts():
    import trader_core.health as H
    assert "spool_corrupt" in H.IMMEDIATE_CODES
    lp = H.LedgerProbe(None, 5, (), (), True, True, 1)
    snap = _snap(lp)
    rep = H.evaluate(snap)
    codes = {r.name: r.code for r in rep.results}
    assert codes["ledger_gate:learner"] == "spool_pending" and codes["spool_corrupt:learner"] == "spool_corrupt"
    assert rep.overall is H.Status.CRIT
    for n, exp in ((0, "ok"), (None, "spool_corrupt_unreadable")):
        r = {x.name: x for x in H.evaluate(_snap(H.LedgerProbe(None, 0, (), (), True, True, n))).results}["spool_corrupt:learner"]
        assert r.code == exp
    H.LedgerProbe(None, 1, (), (), True, True)      # konumsal 6 argumanli kurucu bozulmaz


def _snap(lp):
    import trader_core.health as H
    return H.HealthSnapshot(now=datetime(2026, 12, 28, 10, 0, tzinfo=timezone.utc), ledger={"learner": lp})


def _boom(path):
    raise sqlite3.OperationalError("disk I/O error")


def test_stamp_f1_ledger_history_read_error_virgin_state_fails_closed(tmp_path, monkeypatch):
    """Mentor F1: bakir+damgasiz state, damgasiz defter, gecmis sorgusu hata -> 8 ledger_stamp_mismatch, hicbir damga yazilmaz."""
    cfg = _stamp_env(tmp_path)
    st, led = _open(cfg)
    st.close()
    led.close()
    monkeypatch.setattr(ST, "ledger_has_history", _boom)
    assert _code(cfg) == "ledger_stamp_mismatch"
    monkeypatch.undo()
    st, led = _open(cfg)
    try:
        assert st.kv_get("account_stamp") is None
        assert led.get_meta("account_stamp") is None
    finally:
        st.close()
        led.close()


def test_stamp_f1_ledger_history_read_error_state_stamped_fails_closed(tmp_path, monkeypatch):
    """Mentor F1: S=want, defter damgasiz, gecmis sorgusu hata -> 8, defter damgalanmaz."""
    cfg = _stamp_env(tmp_path)
    st, led = _open(cfg)
    with st.tx():
        st.kv_set("account_stamp", "testnet:sub-acct")
    st.close()
    led.close()
    monkeypatch.setattr(ST, "ledger_has_history", _boom)
    assert _code(cfg) == "ledger_stamp_mismatch"
    monkeypatch.undo()
    st, led = _open(cfg)
    try:
        assert led.get_meta("account_stamp") is None
    finally:
        st.close()
        led.close()
