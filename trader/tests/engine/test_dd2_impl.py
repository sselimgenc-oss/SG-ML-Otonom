"""DD-2 (motor kucukleri): D6/O6 neden kumesi + `unblock`, O14 (spool son bayt / karantina), O9, D1/D13, D7, D9, D5/D4, D14,
D8, D11 (11-18) ve periyodik saat esitleme / stop_tick / max_attempts / canceled stop satiri (18: D5, D9, D10).

Yalniz sahteler (FakeExchange, SimClock); ag yok. Duzenek test_engine_live_spec.LiveEnv / test_b45_kill_multi.LiveEnv2'dir
(dosyalarina dokunulmaz).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import test_engine_live_spec as T
from test_b45_kill_multi import DOGE, LiveEnv2
from trader_core import ledger as L
from trader_engine import cli
from trader_engine import fileio
from trader_engine.config import apply_overrides, load_engine_config
from trader_engine.errors import ConfigError, DataError, StateError
from trader_engine.reconcile import apply_block_set
from trader_engine.state import StateStore
from trader_engine.types import OrderRequest

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
REAL_STARTUP_GATE = True


# ============================================================================================ D6 / O6: neden kumesi
def _st(tmp_path):
    return StateStore(str(tmp_path / "state.sqlite"), bot="learner")


def test_dd2_d6_set_does_not_overwrite_and_primary_is_manual_first(tmp_path):
    st = _st(tmp_path)
    try:
        st.block_add("engine_errors")
        st.block_add("stop_failed")                         # eskiden engine_errors'u eziyordu
        assert st.block_reasons() == ["engine_errors", "stop_failed"]
        assert st.kv_get("entries_blocked_reason") == "engine_errors"
        st.block_remove("stop_failed")                      # mutabakatin temizlemesi engine_errors'a dokunmaz
        assert st.block_reasons() == ["engine_errors"]
        assert st.kv_get("entries_blocked_reason") == "engine_errors"
        st.block_remove("engine_errors")
        assert st.block_reasons() == [] and st.kv_get("entries_blocked_reason") is None
        assert st.kv_get("entries_blocked_reasons") is None
        # elle kalkan neden, sonradan eklenen otomatik nedenden once gorunur; sirayla bagimsiz
        st.block_add("stop_failed")
        st.block_add("strategy_mismatch")
        assert st.kv_get("entries_blocked_reason") == "strategy_mismatch"
    finally:
        st.close()


def test_dd2_d6_legacy_single_value_and_external_write_are_respected(tmp_path):
    st = _st(tmp_path)
    try:
        with st.tx():
            st.kv_set("entries_blocked_reason", "stop_failed")      # eski state / test tohumu: kume kaydi yok
        assert st.block_reasons() == ["stop_failed"]
        st.block_add("engine_errors")
        assert st.block_reasons() == ["stop_failed", "engine_errors"]
        with st.tx():
            st.kv_set("entries_blocked_reason", None)               # disaridan temizleme esas alinir
        assert st.block_reasons() == []
        assert st.block_add("clock_skew") is True and st.block_add("clock_skew") is False
    finally:
        st.close()


def test_dd2_d6_reconcile_clears_only_its_own_reasons(tmp_path):
    st = _st(tmp_path)
    try:
        st.block_add("engine_errors")
        st.block_add("stop_failed")
        st.block_add("exchange_unreachable")
        acts: list[str] = []
        apply_block_set(st, [], acts)                       # mutabakat temiz: stop_failed kalkar, digerleri kalir
        assert st.block_reasons() == ["engine_errors", "exchange_unreachable"]
        assert acts == ["cleared:stop_failed"]
        apply_block_set(st, ["reconcile_unknown_position"], acts)
        assert st.block_reasons() == ["engine_errors", "exchange_unreachable", "reconcile_unknown_position"]
        assert st.kv_get("entries_blocked_reason") == "engine_errors"
        apply_block_set(st, [], acts)
        assert st.block_reasons() == ["engine_errors", "exchange_unreachable"]
    finally:
        st.close()


def test_dd2_o6_paper_reconcile_keeps_order_unknown_while_unresolved(tmp_path):
    """Kagit mutabakata canlidaki kosul eklendi: cozulmemis emir ya da `opening` pozisyon varken order_unknown kalkmaz."""
    st = _st(tmp_path)
    try:
        st.block_add("order_unknown")
        st.unresolved_orders = lambda: [object()]           # type: ignore[method-assign]
        acts: list[str] = []
        apply_block_set(st, [], acts)
        assert st.block_reasons() == ["order_unknown"] and acts == []
        st.unresolved_orders = lambda: []                   # type: ignore[method-assign]
        apply_block_set(st, [], acts)
        assert st.block_reasons() == [] and acts == ["cleared:order_unknown"]
    finally:
        st.close()


def test_dd2_d6_engine_errors_survives_stop_failed_reconcile_and_clock_skew_cycles(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.engine._block("engine_errors")
        e.engine._block("stop_failed")
        for _ in range(4):                                  # her tur: mutabakat + advance_to (clock_skew temizligi)
            e.tick(20)
        e.engine._reconcile(e.clock.now())
        assert e.state.block_has("engine_errors"), e.state.block_reasons()
        assert e.state.kv_get("entries_blocked_reason") == "engine_errors"
        assert not e.state.block_has("stop_failed")         # otomatik neden kendi yolundan kalkti
    finally:
        e.close()


# ------------------------------------------------------------------ unblock CLI
def _ns(**kw):
    base = dict(bot="learner", config_dir="config", env=None, list=False, reason=None, by="ali", note="")
    base.update(kw)
    return argparse.Namespace(**base)


@pytest.fixture
def ucfg(tmp_path, monkeypatch):
    cfg = T.make_live_cfg(tmp_path)
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    Path(cfg.state_path).parent.mkdir(parents=True, exist_ok=True)
    st = StateStore(cfg.state_path, bot="learner")
    st.block_add("engine_errors")
    st.block_add("stop_failed")
    st.close()
    return cfg


def test_dd2_unblock_removes_only_requested_manual_reason_and_writes_audit(ucfg, capsys):
    assert cli._cmd_unblock(_ns(reason="engine_errors", note="kok neden giderildi")) == cli.EXIT_OK
    st = StateStore(ucfg.state_path, bot="learner")
    try:
        assert st.block_reasons() == ["stop_failed"]            # otomatik neden dokunulmadi
    finally:
        st.close()
    rows = [json.loads(ln) for ln in Path(ucfg.path("block_audit.jsonl")).read_text().splitlines()]
    assert len(rows) == 1
    r = rows[0]
    assert (r["op"], r["reason"], r["by"], r["note"], r["remaining"]) == \
        ("unblock", "engine_errors", "cli:ali", "kok neden giderildi", ["stop_failed"])
    assert json.loads(capsys.readouterr().out.strip().splitlines()[0]) == {"unblocked": "engine_errors",
                                                                          "remaining": ["stop_failed"]}


def test_dd2_unblock_refuses_while_engine_runs_unknown_reason_non_manual_and_bad_by(ucfg):
    held = StateStore(ucfg.state_path, bot="learner")             # motor calisiyor benzetimi: state kilidi tutuluyor
    try:
        assert cli._cmd_unblock(_ns(reason="engine_errors")) == cli.EXIT_FAZ_B
        assert held.block_has("engine_errors")
    finally:
        held.close()
    assert not Path(ucfg.path("block_audit.jsonl")).exists()
    assert cli._cmd_unblock(_ns(reason="stop_failed")) == cli.EXIT_FAZ_B        # otomatik kalkan: elle kaldirilmaz
    assert cli._cmd_unblock(_ns(reason="engine_errors", by="a b")) == cli.EXIT_FAZ_B
    assert cli._cmd_unblock(_ns(reason=None)) == cli.EXIT_FAZ_B
    assert cli._cmd_unblock(_ns(reason="strategy_mismatch")) == cli.EXIT_FINDINGS   # kumede yok
    st = StateStore(ucfg.state_path, bot="learner")
    try:
        assert st.block_reasons() == ["engine_errors", "stop_failed"]
    finally:
        st.close()


def test_dd2_unblock_list_and_parser(ucfg, capsys):
    assert cli._cmd_unblock(_ns(list=True)) == cli.EXIT_OK
    d = json.loads(capsys.readouterr().out)
    assert d["reasons"] == ["engine_errors", "stop_failed"] and d["manual_clear"] == ["engine_errors"]
    a = cli.build_parser().parse_args(["unblock", "--bot", "learner", "--reason", "engine_errors", "--by", "ali"])
    assert a.fn is cli._cmd_unblock and a.reason == "engine_errors"


def test_dd2_unblock_no_state_file(tmp_path, monkeypatch):
    cfg = T.make_live_cfg(tmp_path)
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    assert cli._cmd_unblock(_ns(reason="engine_errors")) == cli.EXIT_FAZ_B
    assert not Path(cfg.state_path).exists()                       # komut yeni state yaratmaz


# ============================================================================================ O14 (altin test)
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}
T0 = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


def _led(tmp_path):
    lg = L.open_ledger(tmp_path / "l.sqlite", "learner", clock=lambda: T0)
    lg.init_params(PARAMS, reason="baslangic")
    return lg


def _decision(lg):
    from test_ledger_impl_smoke import r1
    return lg.record_decision(r1())


def _entry_payload(tid, did):
    return {"type": "entry", "trade_id": tid, "decision_id": did, "entry_ts": "2026-12-01T10:00:03.000Z",
            "entry_price": 2001.0, "qty": 0.3, "leverage": 3, "fee_entry": 0.3, "supersedes_id": None}


def test_dd2_o14_golden_spool_torn_tail_is_isolated_then_quarantined(tmp_path):
    """Yarim yazim (son bayt satir sonu degil): yeni kayit o parcaya YAPISMAZ; drain bozuk satiri karantinaya alir,
    gecerli kaydi isler; spool bosalir ve defter `degraded`dan cikar. Bayt bayt beklenen icerik."""
    lg = _led(tmp_path)
    try:
        did = _decision(lg)
        spool = lg._spool_path()
        torn = '{"type":"entry","trade_id":9,"decision_id":'
        with open(spool, "w", encoding="utf-8") as f:
            f.write(torn)                                       # guc kesintisi: satir sonu yok
        assert lg._spool_tail_torn() is True
        assert lg._spool_append(_entry_payload(7, did)) is True
        raw = Path(spool).read_bytes()
        good = json.dumps(_entry_payload(7, did), sort_keys=True, separators=(",", ":"))
        assert raw == (torn + "\n" + good + "\n").encode()      # parca kendi satirinda, yeni kayit tam
        assert lg._spool_tail_torn() is False
        assert lg.drain_spool() == 1                            # gecerli kayit islendi
        assert lg.get_trade(7) is not None
        assert Path(spool).read_bytes() == b""                  # spool bos (bozuk satir kuyrukta KALMADI)
        rows = [json.loads(ln) for ln in Path(lg._corrupt_path()).read_text().splitlines()]
        assert len(rows) == 1 and rows[0]["row"] == torn and rows[0]["why"].startswith("JSONDecodeError")
        assert rows[0]["at"] == "2026-12-01T12:00:00.000Z" or rows[0]["at"].startswith("2026-12-01T12:00:00")
        assert lg.entries_allowed().ok is True                   # kalici degraded/spool_pending yok
    finally:
        lg.close()


def test_dd2_o14_only_structurally_unreadable_rows_are_quarantined(tmp_path):
    lg = _led(tmp_path)
    try:
        spool = lg._spool_path()
        unreadable = ["not json at all", "[1,2]", '{"foo":1}', '{"type":"zzz"}']
        parseable_rejected = ['{"type":"entry"}', '{"type":"exit","trade_id":"x"}']   # ayristirilir ama kayda reddedilir
        with open(spool, "w", encoding="utf-8") as f:
            f.write("".join(b + "\n" for b in unreadable + parseable_rejected))
        assert lg.drain_spool() == 0
        assert Path(spool).read_text().splitlines() == parseable_rejected      # spool'da KALDI
        got = [json.loads(ln)["row"] for ln in Path(lg._corrupt_path()).read_text().splitlines()]
        assert got == unreadable
        assert lg.entries_allowed().ok is False                                # girisler kapali kalir
    finally:
        lg.close()


def test_dd2_o14_torn_entry_then_valid_exit_keeps_exit_and_entries_closed(tmp_path):
    """Yarim giris (trade 7) + gecerli cikis (trade 7): yalniz yarim satir karantinaya girer; cikis spool'da kalir, girisler
    kapali (aksi halde spool bosalir, kapi acilir, gunluk zarar eksik sayilirdi)."""
    lg = _led(tmp_path)
    try:
        spool = lg._spool_path()
        torn = '{"type":"entry","trade_id":7,"decision_id":'
        exit_row = json.dumps({"type": "exit", "trade_id": 7, "exit_ts": "2026-12-01T11:00:00.000Z", "exit_price": 2010.0,
                               "exit_reason": "trail_stop", "planned_exit": 2010.0, "fee_exit": 0.3, "funding_paid": 0.0},
                              sort_keys=True, separators=(",", ":"))
        Path(spool).write_text(torn)                                          # son bayt satir sonu degil
        assert lg._spool_append(json.loads(exit_row)) is True
        assert lg.drain_spool() == 0
        assert Path(spool).read_text().splitlines() == [exit_row]
        assert [json.loads(ln)["row"] for ln in Path(lg._corrupt_path()).read_text().splitlines()] == [torn]
        h = lg.entries_allowed()
        assert h.ok is False and h.code == "spool_pending"
    finally:
        lg.close()


def test_dd2_o14_quarantine_failure_keeps_row_in_spool(tmp_path, monkeypatch):
    lg = _led(tmp_path)
    try:
        spool = lg._spool_path()
        Path(spool).write_text("garbage\n", encoding="utf-8")
        monkeypatch.setattr(lg, "_quarantine", lambda rows, why: False)
        lg.drain_spool()
        assert Path(spool).read_text() == "garbage\n"           # karantina yazilamadiysa satir kaybolmaz
    finally:
        lg.close()


def test_dd2_o14_append_on_clean_spool_unchanged_format(tmp_path):
    lg = _led(tmp_path)
    try:
        assert lg._spool_append({"a": 1}) and lg._spool_append({"b": 2})
        assert Path(lg._spool_path()).read_bytes() == b'{"a":1}\n{"b":2}\n'
    finally:
        lg.close()


# ============================================================================================ O9: KILL dongusu yalitimi
def test_dd2_o9_kill_loop_exception_on_first_position_does_not_stop_second(tmp_path):
    e = LiveEnv2(tmp_path).boot()
    try:
        e.enter_both()
        calls: list[str] = []
        real = e.engine._submit_exit

        def flaky(pos, reason, at, quote=False):
            calls.append(pos.pair)
            if len(calls) == 1:
                raise RuntimeError("poll ag hatasi (sahte)")
            return real(pos, reason, at, quote)

        e.engine._submit_exit = flaky                           # type: ignore[method-assign]
        Path(e.cfg.kill_file).parent.mkdir(parents=True, exist_ok=True)
        Path(e.cfg.kill_file).write_text("{}")
        with pytest.raises(RuntimeError):                       # ilk hata dongu SONUNDA yeniden firlatilir
            e.engine._kill_step(e.clock.now())
        assert len(calls) == 2, calls                           # ikinci pozisyon AYNI turda denendi
        assert e.engine.counters()["kill_exit_errors"] == 1
        # _guard sayar: ardisik hata sayaci artar (CRIT / engine_errors / EngineExit(3) zinciri korunur)
        calls.clear()
        e.engine._submit_exit = real                            # type: ignore[method-assign]
        n0 = e.engine._consec_errors

        def always(pos, reason, at, quote=False):
            raise RuntimeError("hep hata")

        e.engine._submit_exit = always                          # type: ignore[method-assign]
        assert e.engine._guard("kill", lambda: e.engine._kill_step(e.clock.now())) is False
        assert e.engine._consec_errors == n0 + 1 and e.engine.counters()["callback_errors"] >= 1
    finally:
        e.close()


def test_dd2_o9_paper_and_strict_raise_immediately(tmp_path):
    """Kagit/strict: eski davranis (ilk hatada hemen firlat, sonraki pozisyonlara gecme)."""
    e = LiveEnv2(tmp_path).boot()
    try:
        e.enter_both()
        calls: list[str] = []

        def boom(pos, reason, at, quote=False):
            calls.append(pos.pair)
            raise RuntimeError("x")

        e.engine._submit_exit = boom                            # type: ignore[method-assign]
        Path(e.cfg.kill_file).write_text("{}")
        e.engine.strict = True
        with pytest.raises(RuntimeError):
            e.engine._kill_step(e.clock.now())
        assert len(calls) == 1
    finally:
        e.close()


def test_dd2_o9_state_error_in_kill_loop_still_propagates(tmp_path):
    e = LiveEnv2(tmp_path).boot()
    try:
        e.enter_both()

        def boom(pos, reason, at, quote=False):
            raise StateError("state yazilamadi")

        e.engine._submit_exit = boom                            # type: ignore[method-assign]
        Path(e.cfg.kill_file).write_text("{}")
        with pytest.raises(StateError):
            e.engine._kill_step(e.clock.now())
    finally:
        e.close()


# ============================================================================================ D1 / D13: dizin fsync
def test_dd2_d1_atomic_write_fsyncs_parent_directory(tmp_path, monkeypatch):
    seen: list[bool] = []
    real = os.fsync

    def spy(fd):
        seen.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return real(fd)

    monkeypatch.setattr(os, "fsync", spy)
    fileio.atomic_write_json(tmp_path / "shared" / "KILL", {"x": 1})
    assert seen == [False, True]                                # once dosya, sonra dizin
    assert json.loads((tmp_path / "shared" / "KILL").read_text()) == {"x": 1}
    seen.clear()
    from trader_core.telegram import atomic_write_json as tg_write
    tg_write(tmp_path / "t" / "a.json", {"y": 2})
    assert seen == [False, True]
    seen.clear()
    from trader_panel.snapshot import write_atomic
    write_atomic(str(tmp_path / "snap.html"), "<html/>")
    assert seen == [False, True]


def test_dd2_d1_dir_fsync_failure_is_silent(tmp_path, monkeypatch):
    real_open = os.open

    def fail_dir(p, flags, *a, **k):
        if flags == os.O_RDONLY and Path(p) == tmp_path:
            raise OSError("desteklenmiyor")
        return real_open(p, flags, *a, **k)

    monkeypatch.setattr(os, "open", fail_dir)
    fileio.atomic_write_text(tmp_path / "f.txt", "ok")
    assert (tmp_path / "f.txt").read_text() == "ok"


# ============================================================================================ D7: mutlak KILL yolu
def test_dd2_d7_relative_kill_file_resolved_against_config_dir_not_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                                 # baska dizinden calistirma
    a = argparse.Namespace(config_dir=str(ROOT / "config"), bot="learner", env=None)
    c = cli._load_cfg(a)
    assert c.kill_file == str(ROOT / "shared" / "KILL") and os.path.isabs(c.kill_file)
    c2 = cli._load_cfg(argparse.Namespace(config_dir=str(ROOT / "config"), bot="learner", env="testnet"))
    assert c2.kill_file == str(ROOT / "shared" / "testnet" / "KILL")
    # saf yukleyici ham degeri aynen dondurur (sozlesme: "paper config loads unchanged")
    raw = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / "engine.learner.json")
    assert raw.kill_file == "shared/KILL"


def test_dd2_d7_absolute_kill_file_untouched_and_cli_kill_writes_there(tmp_path, monkeypatch):
    cfg = T.make_live_cfg(tmp_path)
    assert cfg.kill_file == str(tmp_path / "KILL")
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    monkeypatch.chdir(tmp_path / "..")
    assert cli._cmd_kill(argparse.Namespace(clear=False, by="t", reason="x")) == cli.EXIT_OK
    assert (tmp_path / "KILL").exists()


# ============================================================================================ D9 (17): 0 bayt state
def test_dd2_d9_zero_byte_state_with_filled_ledger_is_error(tmp_path):
    lg = _led(tmp_path)
    try:
        _decision(lg)
    finally:
        lg.close()
    (tmp_path / "ledger.sqlite").write_bytes((tmp_path / "l.sqlite").read_bytes())
    sp = tmp_path / "state.sqlite"
    sp.write_bytes(b"")
    with pytest.raises(StateError, match="0 bayt"):
        StateStore(str(sp), bot="learner", ledger_path=str(tmp_path / "ledger.sqlite"))     # DD-8 E3: defter yolu acikca verilir
    StateStore(str(sp), bot="learner").close()                  # ledger_path=None: denetim yok (testnet/live'de damga karar tablosu yakalar)


def test_dd2_d9_zero_byte_state_with_empty_or_missing_ledger_is_fresh(tmp_path):
    sp = tmp_path / "state.sqlite"
    sp.write_bytes(b"")
    StateStore(str(sp), bot="learner", ledger_path=str(tmp_path / "ledger.sqlite")).close()    # defter yok: yeni durum
    sp.unlink()
    for ext in ("", "-wal", "-shm"):
        Path(str(sp) + ext).unlink(missing_ok=True)
    lg = L.open_ledger(tmp_path / "ledger.sqlite", "learner", clock=lambda: T0)    # yalniz sema + parametre: islem/karar yok
    lg.init_params(PARAMS, reason="x")
    lg.close()
    sp.write_bytes(b"")
    StateStore(str(sp), bot="learner", ledger_path=str(tmp_path / "ledger.sqlite")).close()    # ilk kurulumda coken bos defter `dolu` sayilmaz


# ============================================================================================ D5 (17) / D4 (18): yerel min_qty
def test_dd2_d5_local_min_qty_entry_only(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        ent = e.broker._rules[T.XRP]
        ent.rules = dataclasses.replace(ent.rules, min_qty=5.0)

        def req(role, qty):
            return OrderRequest(client_id="x", pair=T.XRP, role=role, order_side="buy" if role == "entry" else "sell",
                                qty=qty, trigger_price=None, reduce_only=role != "entry", leverage=3)

        assert e.broker._common_checks(req("entry", 1.0), ("entry", "exit"), False)[0] == "min_qty"
        assert e.broker._common_checks(req("entry", 5.0), ("entry", "exit"), False)[0] is None
        # koruyucu cikis ve stop yerel min_qty ile ENGELLENMEZ (borsa karar verir)
        assert e.broker._common_checks(req("exit", 1.0), ("entry", "exit"), True)[0] is None
        assert e.broker._common_checks(req("stop", 1.0), ("stop",), True)[0] is None
    finally:
        e.close()


# ============================================================================================ D14: live/testnet + twin
@pytest.mark.parametrize("mode", ["testnet", "live"])
def test_dd2_d14_twin_refused_in_live_modes(tmp_path, mode):
    cfg = T.make_live_cfg(tmp_path, mode="testnet")
    with pytest.raises(ConfigError, match="learner"):
        apply_overrides(cfg, mode=mode, bot="twin")


# ============================================================================================ D8 (17): salt-okur reconcile
def test_dd2_d8_paper_reconcile_is_read_only_by_default(tmp_path, monkeypatch, capsys):
    cfg = apply_overrides(T.make_live_cfg(tmp_path), mode="paper")
    Path(cfg.state_path).parent.mkdir(parents=True, exist_ok=True)
    st = StateStore(cfg.state_path, bot="learner")
    st.block_add("engine_errors")
    st.close()
    lg = L.open_ledger(cfg.ledger_path, "learner", create=True, clock=lambda: T0)
    lg.init_params(PARAMS, reason="x")
    lg.close()
    before = Path(cfg.state_path).read_bytes(), Path(cfg.ledger_path).read_bytes()
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    seen = {}

    def fake_run(c):
        seen["cfg"] = c
        s2 = StateStore(c.state_path, bot="learner")                # kopya okunabilir ve ayni icerikte
        try:
            seen["reasons"] = s2.block_reasons()
            s2.block_remove("engine_errors")                        # kopyada yazmak gercegi etkilemez
        finally:
            s2.close()
        seen["tmp_exists"] = Path(c.state_path).exists()
        return cli.EXIT_OK

    monkeypatch.setattr(cli, "_reconcile_run", fake_run)
    assert cli._cmd_reconcile(_ns(apply=False)) == cli.EXIT_OK
    assert seen["cfg"].var_dir != cfg.var_dir and seen["reasons"] == ["engine_errors"] and seen["tmp_exists"]
    assert not Path(seen["cfg"].state_path).exists()                # gecici kopya silindi
    assert (Path(cfg.state_path).read_bytes(), Path(cfg.ledger_path).read_bytes()) == before
    assert "salt-okur" in capsys.readouterr().err
    seen.clear()
    assert cli._cmd_reconcile(_ns(apply=True)) == cli.EXIT_OK       # eski yazan davranis acikca istenir
    assert seen["cfg"] is cfg


# ============================================================================================ D11 (17): yorum
def test_dd2_d11_health_env_comment_matches_install_mode():
    first = (ROOT / "deploy" / "trader-health.env.example").read_text(encoding="utf-8").splitlines()[0]
    inst = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8").splitlines()
    line = [ln for ln in inst if "copy_env" in ln and "/etc/trader-health.env" in ln][0]
    assert line.rstrip().endswith("0600")                        # DD-9 (O13): kurulum root:root 0600 (grup okuyamaz)
    assert "0600" in first and "0640" not in first


# ============================================================================================ D5 (18): periyodik saat esitleme
def test_dd2_d5_periodic_clock_sync_every_30_minutes_single_attempt(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        calls: list[int] = []
        rest = e.broker._rest
        orig = rest.sync_time_once
        rest.sync_time_once = lambda: (calls.append(1), orig())[1]
        e.tick(6)
        e.tick(600)
        assert calls == []                                       # 30 dk dolmadi
        e.tick(1300)
        assert len(calls) == 1
        e.tick(60)
        assert len(calls) == 1                                   # sayac sifirlandi
        e.tick(1800)
        assert len(calls) == 2
    finally:
        e.close()


def test_dd2_d5_periodic_sync_failure_is_swallowed_and_skipped_with_naked_position(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.tick(6)
        rest = e.broker._rest
        n = {"c": 0}

        def boom():
            n["c"] += 1
            raise RuntimeError("ag")

        rest.sync_time_once = boom
        e.broker._naked = [object()]                             # stopsuz pozisyon: koruyucu yol gecikmesin
        e.tick(2000)
        assert n["c"] == 0
        e.broker._naked = []
        e.broker.poll(e.clock.now())                             # hata yutulur, poll patlamaz
        assert n["c"] == 1
    finally:
        e.close()


# ============================================================================================ D9 (18): stop_tick bayat kural
def test_dd2_d9_stop_tick_uses_last_known_rules_when_stale(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        assert pos is not None
        ent = e.broker._rules[T.XRP]
        tick = ent.rules.tick
        ent.ts = e.clock.now() - timedelta(hours=7)               # > RULES_MAX_AGE_S
        with pytest.raises(DataError):
            e.broker.rules(T.XRP)                                 # piyasa tarafi bayat kuralda DataError verir (place_stop vermez)
        assert e.engine.orders.stop_tick(pos) == tick             # koruyucu yol bayat kuralla da calisir
        assert e.engine.orders.rules_tick(T.XRP) == tick
    finally:
        e.close()


# ============================================================================================ D10 (18)
def test_dd2_d10_max_attempts_pinned_to_one(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        assert e.engine.orders.max_attempts == 1
    finally:
        e.close()
    # 25.11 denetim #13: ayar yalniz 1 kabul eder (etkisiz 2 degeri sessizce yutulmaz)
    (tmp_path / "b").mkdir()
    with pytest.raises(Exception, match="max_attempts"):
        T.LiveEnv(tmp_path / "b", live_over={"max_attempts": 2}).boot()


def test_dd2_d10_replaced_stop_row_marked_canceled(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        old = pos.stop_client_id
        assert old and e.state.get_order(old).status == "accepted"
        out = e.engine.orders.replace_stop(pos, 1.95)
        assert out.ok
        assert e.state.get_order(old).status == "canceled"
        new = e.state.get_position(pos.trade_id).stop_client_id
        assert new != old and e.state.get_order(new).status == "accepted"
        assert len([a for a in e.ex.algos.values() if a["algoStatus"] == "NEW"]) == 1
    finally:
        e.close()


# ============================================================================================ review: clock sync, status, KILL yolu
def test_dd2_d5_poll_with_events_makes_no_clock_sync_and_timeout_is_short(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.tick(6)
        calls: list[int] = []
        e.broker._rest.sync_time_once = lambda: calls.append(1)
        e.broker._last_clock_sync = e.clock.now() - timedelta(hours=2)
        e.broker._queue.append((e.clock.now(), 0, object()))     # bu turda dolum/olay var
        evs = e.broker.poll(e.clock.now())
        assert evs and calls == []                                # olayli turda esitleme yok (koruyucu yol gecikmez)
        e.broker.poll(e.clock.now())
        assert calls == [1]                                       # olaysiz turda yapilir
        rest = e.broker._rest
        seen = {}
        rest._sync = lambda **kw: seen.update(kw) or 0
        type(rest).sync_time_once(rest)
        assert seen == {"attempts": 1, "timeout": rest.order_timeout_s} and rest.order_timeout_s == (2.0, 3.0)
    finally:
        e.close()


def test_dd2_status_json_has_additive_reasons_list_and_legacy_field(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.engine._block("stop_failed")
        e.engine._block("engine_errors")
        f = e.engine.status_fields()
        assert f["entries_blocked_reasons"] == ["stop_failed", "engine_errors"]
        assert f["entries_blocked_reason"] == "engine_errors"
        from trader_engine.status import StatusWriter
        d = StatusWriter(str(tmp_path / "st.json"), e.clock, e.cfg).build(e.engine)
        assert d["entries_blocked_reason"] == "engine_errors"
        assert d["entries_blocked_reasons"] == ["stop_failed", "engine_errors"]
    finally:
        e.close()


def test_dd2_mirror_broker_blocks_mirrors_all_reasons(tmp_path):
    e = T.LiveEnv(tmp_path).boot()
    try:
        e.broker._blocks.update({"exchange_auth", "working_type_unverified"})
        e.engine._mirror_broker_blocks()
        assert {"exchange_auth", "working_type_unverified"} <= set(e.state.block_reasons())
    finally:
        e.close()


def test_dd2_d7_kill_cli_prints_resolved_path_and_run_logs_it(tmp_path, monkeypatch, capsys):
    cfg = T.make_live_cfg(tmp_path)
    monkeypatch.setattr(cli, "_load_cfg", lambda a: cfg)
    assert cli._cmd_kill(argparse.Namespace(clear=False, by="t", reason="x")) == cli.EXIT_OK
    assert f"kill_file: {cfg.kill_file}" in capsys.readouterr().out
    src = Path(cli.__file__).read_text(encoding="utf-8")
    assert "KILL dosyasi (mutlak yol)" in src
