"""capital_latch (kullanici karari): equity <= 0.85 x dep_net -> yeni giris mandali. Tum kiplerde (paper dahil), yeniden
baslatmada kalir, yalniz kullanici acar; -%20 kurali (STOP_RATIO) aynen korunur."""
from __future__ import annotations

from datetime import timedelta

import test_risk_ladder_spec as S
from test_risk_ladder_impl import M1, T0, _env05, D, H  # noqa: F401
from trader_core import risk_ladder as rl
from trader_engine.pause import EntryPause, last_audit_op

LATCH = "capital_latch"


def _paper(tmp_path):
    return S.Env(tmp_path, mode="paper", enforce=False)


def test_latch_constant():
    assert rl.CAPITAL_LATCH_RATIO == 0.85


def test_paper_849_holds_after_confirm(tmp_path):
    e = _paper(tmp_path)                                   # paper: wallet_start 1000 -> esik 850
    e.tick(849.0)
    assert e.reasons() == []                               # tek olcum yetmez (CONFIRM_N)
    e.tick(849.0)
    assert e.reasons() == [LATCH]
    assert (e.rl.status()["would"] or {}).get("kind") != "review_stop"   # -%20 (800) degil
    assert "review_stop" not in e.kinds()                  # gunluk zinciri degismez


def test_paper_851_no_hold(tmp_path):
    e = _paper(tmp_path)
    for _ in range(4):
        e.tick(851.0)
    assert e.reasons() == []


def test_single_dip_does_not_hold(tmp_path):
    e = _paper(tmp_path)
    e.tick(849.0)
    e.tick(900.0)
    e.tick(849.0)
    assert e.reasons() == []


def test_threshold_is_inclusive(tmp_path):
    e = _paper(tmp_path)
    e.tick(850.0)
    e.tick(850.0)
    assert e.reasons() == [LATCH]


def test_restart_keeps_hold(tmp_path):
    e = _paper(tmp_path)
    e.tick(849.0)
    e.tick(849.0)
    rl2 = e.mk()                                           # motor yeniden kuruldu; pause dosyasi ayni
    e.clock.advance(60)
    rl2.tick(e.clock.now(), 900.0, 900.0)                  # kasa toparlansa da tutus kendiliginden kalkmaz
    assert e.reasons() == [LATCH]


def test_unlock_below_threshold_does_not_relatch_then_rearms(tmp_path):
    e = _paper(tmp_path)
    e.tick(849.0)
    e.tick(849.0)
    assert e.pause.remove(LATCH, "telegram:1")             # kullanici acti
    for _ in range(4):
        e.tick(849.0)                                      # hala esikte: yeniden kurulmaz
    assert e.reasons() == []
    e.tick(860.0)                                          # esigin ustune cikti: yeniden silahlanir
    e.tick(849.0)
    e.tick(849.0)
    assert e.reasons() == [LATCH]


def test_restart_after_unlock_while_below_stays_unlatched(tmp_path):
    e = _paper(tmp_path)
    e.tick(849.0)
    e.tick(849.0)
    e.pause.remove(LATCH, "telegram:1")
    assert last_audit_op(e.pause.audit_path, LATCH) == "remove"
    rl2 = e.mk()
    for _ in range(4):
        e.clock.advance(60)
        rl2.tick(e.clock.now(), 849.0, 849.0)
    assert e.reasons() == []
    e.clock.advance(60)
    rl2.tick(e.clock.now(), 900.0, 900.0)                  # yukari, sonra yeniden asagi: silahlanir
    for _ in range(2):
        e.clock.advance(60)
        rl2.tick(e.clock.now(), 840.0, 840.0)
    assert e.reasons() == [LATCH]


def test_restart_below_without_prior_unlock_latches(tmp_path):
    e = _paper(tmp_path)
    rl2 = e.mk()
    for _ in range(2):
        e.clock.advance(60)
        rl2.tick(e.clock.now(), 800.0, 800.0)
    assert e.reasons() == [LATCH]


def test_last_audit_op_reader(tmp_path):
    p = tmp_path / "a.jsonl"
    assert last_audit_op(str(p), LATCH) is None
    p.write_text('{"op":"add","reason":"capital_latch"}\nnot json\n{"op":"add","reason":"manual"}\n'
                 '{"op":"remove","reason":"capital_latch"}\n{"op":"add","reason":"manual"}\n')
    assert last_audit_op(str(p), LATCH) == "remove"
    assert last_audit_op(str(p), "manual") == "add"


def test_live_uses_dep_net_with_deposits(tmp_path):
    e = S.Env(tmp_path, mode="testnet", enforce=True)
    e.log.append("deposit", "cli:t", S.NOW0 + timedelta(minutes=30), amount=500.0)     # dep_net 1500 -> esik 1275
    e.tick(1300.0)
    e.tick(1300.0)
    assert e.reasons() == []                               # 1300 > 1275 (1000'e gore -%30 olsa da)
    e.tick(1270.0)
    e.tick(1270.0)
    assert e.reasons() == [LATCH]
    assert "review_stop" not in e.kinds()                  # -%20 (taban 1500 -> 1200) henuz degil


def test_minus20_rule_unchanged_paper_observe_only(tmp_path):
    e = _paper(tmp_path)
    e.tick(800.0)
    e.tick(800.0)
    assert e.reasons() == [LATCH]                          # -%20 tutusu (drawdown_review) paper'de yok
    assert e.rl.status()["would"]["kind"] == "review_stop"


def test_open_position_not_closed_stop_still_works(tmp_path):
    e, lad, pause, b = _env05(tmp_path, enforce=False)
    e.start()
    try:
        D1 = T0 + 2 * H
        e.signal(D1)
        e.engine.ladder = None
        e.engine.gate.ladder = None
        e.decide(D1)
        e.step(D1)
        assert e.pos() is not None
        e.engine.ladder, e.engine.gate.ladder = lad, lad
        pause.add(LATCH, "engine:rk1")
        e.step(D1 + M1, lo=1.0, hi=1.0, price=1.0)         # mandal pozisyonu kapatmaz; stop yine calisir
        assert e.pos() is None
        assert [h.reason for h in pause.holds()] == [LATCH]
    finally:
        e.close()


def test_open_position_survives_latch_tick(tmp_path):
    e, lad, pause, b = _env05(tmp_path, enforce=False)
    e.start()
    try:
        D1 = T0 + 2 * H
        e.signal(D1)
        e.engine.ladder = None
        e.engine.gate.ladder = None
        e.decide(D1)
        e.step(D1)
        assert e.pos() is not None
        e.engine.ladder, e.engine.gate.ladder = lad, lad
        lad.tick(D1 + M1, 800.0, 800.0)
        lad.tick(D1 + 3 * M1, 800.0, 800.0)
        assert [h.reason for h in pause.holds()] == [LATCH]
        assert e.pos() is not None                         # acik pozisyon dokunulmadi
    finally:
        e.close()
