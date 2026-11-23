"""RK-1 saglik parcasi (12 §11): `risk_ladder:<bot>` denetimi (ApiProbe.ladder), status.json esleme (scripts/health_run.py),
uyari yolu (acil kodlar). Saf degerlendirme; saat enjekte, dosya yalniz tmp."""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import health as H
from trader_core.health import Status

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 12, 30, 12, 0, tzinfo=timezone.utc)
M = timedelta(minutes=1)


def z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def block(**kw):
    b = {"enforce": True, "state": "ok", "step": 0, "step_name": "K0", "dep_net": 1000.0, "base": 1000.0, "peak": 1000.0,
         "equity": 1000.0, "near": False, "gate_code": None, "gate_since": None, "last_down_at": None, "would": None,
         "pause_holds": []}
    b.update(kw)
    return b


def api(ladder, mode="testnet", open_ids=(7,)):
    return H.ApiProbe(True, NOW, NOW, open_ids, mode != "live", "ok", False, 0, (), mode, True, True, NOW, (), ladder)


def check(a, bot="learner"):
    cfg = H.HealthConfig(require_bots=(bot,))
    snap = H.HealthSnapshot(now=NOW, timeframe_s=3600, api={bot: a}, ledger={}, disk_free_bytes=50 * H.GIB,
                            mem_available_bytes=900 * H.MIB, swap_total_bytes=0, swap_used_bytes=0,
                            last_backup_at=NOW - timedelta(hours=1))
    rep = H.evaluate(snap, cfg)
    return {r.name: r for r in rep.results}.get(f"risk_ladder:{bot}"), rep


def expect(a, status, code):
    r, _ = check(a)
    assert r is not None and (r.status, r.code) == (status, code), r
    return r


# --------------------------------------------------------------------------------------- tablo satirlari
def test_ladder_missing_only_live_and_testnet():
    expect(api(None, "testnet"), Status.CRIT, "ladder_missing")
    expect(api(None, "live"), Status.CRIT, "ladder_missing")
    r, _ = check(api(None, "paper"))
    assert r is None                                       # kagitta blok yoksa denetim eklenmez
    r, _ = check(H.ApiProbe())                             # bilinmeyen kip (okunamadi): baska denetimler UNKNOWN verir
    assert r is None


def test_floor_is_crit_with_numbers():
    r = expect(api(block(state="floor", equity=590.0)), Status.CRIT, "capital_floor")
    assert "590.00" in r.detail and "1000.00" in r.detail and "/hepsini_kapat" in r.detail and "yazili karar" in r.detail


def test_review_is_crit_with_numbers():
    r = expect(api(block(state="review", equity=790.0), open_ids=(1, 2)), Status.CRIT, "drawdown_review")
    assert "taban 1000.00" in r.detail and "ozsermaye 790.00" in r.detail and "acik pozisyon 2" in r.detail
    assert "/kademe_devam" in r.detail


@pytest.mark.parametrize("state,gate,code", [("uninitialized", "capital_missing", "capital_missing"),
                                             ("invalid", "ladder_invalid", "ladder_invalid"),
                                             ("ok", "equity_unreadable", "equity_unreadable"),
                                             ("ok", "capital_missing", "capital_missing")])
def test_enforcing_gate_states_are_crit(state, gate, code):
    expect(api(block(state=state, gate_code=gate)), Status.CRIT, code)


def test_observation_mode_does_not_alarm_on_uninitialized():
    r, _ = check(api(block(enforce=False, state="uninitialized"), "paper"))
    assert r.status is Status.OK


@pytest.mark.parametrize("age_min,status", [(29, Status.WARN), (30, Status.WARN), (31, Status.CRIT)])
def test_capital_mismatch_escalates_after_30_min(age_min, status):
    expect(api(block(gate_code="capital_mismatch", gate_since=z(NOW - age_min * M))), status, "capital_mismatch")


def test_capital_mismatch_without_since_is_warn():
    expect(api(block(gate_code="capital_mismatch")), Status.WARN, "capital_mismatch")


def test_capital_unverified_warn():
    expect(api(block(gate_code="capital_unverified")), Status.WARN, "capital_unverified")


def test_near_and_step_down_and_would_warn():
    expect(api(block(near=True, equity=840.0)), Status.WARN, "ladder_near")
    expect(api(block(near=True, state="review")), Status.CRIT, "drawdown_review")          # near yalniz ok'ta
    expect(api(block(last_down_at=z(NOW - timedelta(hours=23)), step=-1, step_name="K-1")), Status.WARN, "ladder_step_down")
    expect(api(block(last_down_at=z(NOW - timedelta(hours=25)))), Status.OK, "ok")
    expect(api(block(enforce=False, would={"kind": "review_stop", "at": z(NOW - timedelta(hours=1))}), "paper"),
           Status.WARN, "ladder_would")
    expect(api(block(enforce=False, would={"kind": "review_stop", "at": z(NOW - timedelta(hours=30))}), "paper"),
           Status.OK, "ok")


@pytest.mark.parametrize("age_min,status,code", [(9, Status.OK, "ok"), (11, Status.WARN, "ladder_hold_stale")])
def test_hold_stale_after_10_min(age_min, status, code):
    holds = [{"reason": "drawdown_review", "at": z(NOW - age_min * M)}]
    expect(api(block(pause_holds=holds)), status, code)


def test_hold_stale_ignores_other_reasons_and_review_state():
    holds = [{"reason": "user_cmd", "at": z(NOW - 60 * M)}]
    expect(api(block(pause_holds=holds)), Status.OK, "ok")
    holds = [{"reason": "drawdown_review", "at": z(NOW - 60 * M)}]
    expect(api(block(state="review", pause_holds=holds)), Status.CRIT, "drawdown_review")


def test_all_clear_is_ok():
    expect(api(block()), Status.OK, "ok")


def test_worst_wins_among_conditions():
    a = api(block(state="review", gate_code="capital_mismatch", gate_since=z(NOW - 5 * M), near=True))
    expect(a, Status.CRIT, "drawdown_review")
    a = api(block(near=True, gate_code="capital_unverified", last_down_at=z(NOW - M)))
    r, _ = check(a)
    assert r.status is Status.WARN
    a = api(block(near=True, gate_code="capital_mismatch", gate_since=z(NOW - 40 * M)))
    expect(a, Status.CRIT, "capital_mismatch")


def test_malformed_block_never_raises():
    for bad in ({"state": 5, "near": "yes", "last_down_at": 7, "pause_holds": 3, "would": 4, "gate_since": []},
                {}, {"state": None, "pause_holds": [None, 1, {"reason": 3}]}):
        r, rep = check(api(bad))
        assert r is not None and r.status in (Status.OK, Status.WARN, Status.CRIT)


def test_critical_ladder_codes_alert_immediately_and_overall_is_crit():
    for code in ("capital_floor", "drawdown_review", "ladder_missing", "capital_missing", "ladder_invalid",
                 "equity_unreadable"):
        assert code in H.IMMEDIATE_CODES
    cfg = H.HealthConfig(require_bots=("learner",), multiple_threshold=50)
    snap = H.HealthSnapshot(now=NOW, timeframe_s=3600, api={"learner": api(block(state="floor"))}, ledger={},
                            disk_free_bytes=50 * H.GIB, mem_available_bytes=900 * H.MIB, swap_total_bytes=0,
                            swap_used_bytes=0, last_backup_at=NOW - timedelta(hours=1))
    rep = H.evaluate(snap, cfg)
    assert rep.overall is Status.CRIT
    a0, st0 = H.plan_alerts(rep, H.empty_state(), NOW, cfg)
    assert not a0                                   # kirmizi cift dogrulama: ilk tur mesaj yok
    alerts, _ = H.plan_alerts(rep, st0, NOW + timedelta(minutes=5), cfg)
    assert any(a.code == "capital_floor" and a.level is Status.CRIT for a in alerts)


# --------------------------------------------------------------------------------------- status.json esleme
def _load(name):
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_probe_status_maps_ladder_block_and_pause_holds(tmp_path):
    R = _load("health_run")
    doc = {"schema": "engine-status/1", "bot": "learner", "mode": "testnet", "loop_at": z(NOW - timedelta(seconds=5)),
           "gate": {"ok": False, "code": "drawdown_review"}, "kill": False, "open_trade_ids": [3], "open_positions": [],
           "exchange": {"reachable": True, "last_sync": z(NOW), "naked": []},
           "pause": {"active": True, "holds": [{"reason": "drawdown_review", "by": "engine:rk1", "at": z(NOW - 20 * M),
                                                "note": "x"}]},
           "risk_ladder": block(state="review", equity=790.0)}
    p = tmp_path / "learner" / "status.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps(doc))
    probe, _ = R.probe_status(str(p), "learner", NOW)
    assert probe.ladder["state"] == "review" and probe.ladder["pause_holds"][0]["reason"] == "drawdown_review"
    r, _ = check(probe)
    assert (r.status, r.code) == (Status.CRIT, "drawdown_review")
    del doc["risk_ladder"]
    p.write_text(json.dumps(doc))
    probe, _ = R.probe_status(str(p), "learner", NOW)
    assert probe.ladder is None
    r, _ = check(probe)
    assert r.code == "ladder_missing"                      # testnet + blok yok
    doc["risk_ladder"] = "bozuk"
    p.write_text(json.dumps(doc))
    assert R.probe_status(str(p), "learner", NOW)[0].ladder is None


# 19 Kasim: motor yeniden basladiginda (oto guncelleme) kademe blogu birkac dakika yok -> yanlis CRIT olmamali
def _check_warm(a, started_ago):
    cfg = H.HealthConfig(require_bots=("learner",))
    snap = H.HealthSnapshot(now=NOW, timeframe_s=3600, api={"learner": a}, ledger={}, disk_free_bytes=50 * H.GIB,
                            mem_available_bytes=900 * H.MIB, swap_total_bytes=0, swap_used_bytes=0,
                            last_backup_at=NOW - timedelta(hours=1),
                            containers={"trader-learner": H.ContainerProbe("running", 0, NOW - started_ago, False)})
    return {r.name: r for r in H.evaluate(snap, cfg).results}["risk_ladder:learner"]


def test_isinmada_kurulum_eksigi_alarm_degil_sonra_yine_crit():
    r = _check_warm(api(None, "testnet"), timedelta(minutes=3))
    assert r.status is Status.OK and "isiniyor" in r.detail
    r = _check_warm(api(block(state="uninitialized"), "testnet"), timedelta(minutes=3))
    assert r.status is Status.OK
    r = _check_warm(api(None, "testnet"), timedelta(minutes=30))          # isinma bitti: gercek sorun yine CRIT
    assert (r.status, r.code) == (Status.CRIT, "ladder_missing")


def test_isinmada_gercek_kademe_olayi_yine_bildirilir():
    r = _check_warm(api(block(state="floor", equity=500.0)), timedelta(minutes=3))
    assert (r.status, r.code) == (Status.CRIT, "capital_floor")


# --------------------------------------------------------------------------------------- capital_latch uyarisi
def test_capital_latch_hold_emits_warn_and_telegram_alert():
    b = block(pause_holds=[{"reason": "capital_latch", "at": z(NOW)}])
    r = expect(api(b), Status.WARN, "capital_latch")
    assert "capital_latch" in r.detail
    cfg = H.HealthConfig(require_bots=("learner",), multiple_threshold=50)
    snap = H.HealthSnapshot(now=NOW, timeframe_s=3600, api={"learner": api(b)}, ledger={}, disk_free_bytes=50 * H.GIB,
                            mem_available_bytes=900 * H.MIB, swap_total_bytes=0, swap_used_bytes=0,
                            last_backup_at=NOW - timedelta(hours=1))
    rep = H.evaluate(snap, cfg)
    a0, st0 = H.plan_alerts(rep, H.empty_state(), NOW, cfg)
    alerts = list(a0)
    for i in range(1, 4):
        a, st0 = H.plan_alerts(rep, st0, NOW + timedelta(minutes=5 * i), cfg)
        alerts += list(a)
    assert any(a.code == "capital_latch" for a in alerts)


def test_no_capital_latch_alert_without_hold():
    r, _ = check(api(block(pause_holds=[{"reason": "user_cmd", "at": z(NOW)}])))
    assert r.code != "capital_latch"
