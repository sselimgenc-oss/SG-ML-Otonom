"""WP-2 uygulayici testleri (sentetik; sabit now; gercek veri yok). Bagimsiz sartname testleri test_drift_monitor_spec.py'dedir."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from trader_core import drift_monitor as D  # noqa: E402

NOW = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)


def z(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def trade(i, r=0.5, *, exit_at=None, entry_at=None, reason="stop", fee_bp=5.0, se=2.2e-4, sx=5.2e-4, risk=10.0, fund=0.0, **kw):
    ex = exit_at or NOW - timedelta(hours=200 - i)
    t = dict(trade_id=i, entry_ts=z(entry_at or ex - timedelta(hours=5)), exit_ts=z(ex), exit_reason=reason, qty=1.0,
             entry_price=100.0, exit_price=100.0, planned_entry=100.0, planned_exit=100.0, planned_risk=risk,
             fee_entry=fee_bp * 1e-4 * 100.0, fee_exit=fee_bp * 1e-4 * 100.0, funding_paid=fund, slippage_entry=se,
             slippage_exit=sx, r_multiple=r)
    t.update(kw)
    return t


def decs(n, *, days=40, skip="veto_blocked", start=None):
    start = start or NOW - timedelta(days=days)
    out = [dict(bar_close_ts=z(start), final_action="skipped", skip_reason="stop_width", veto_status="not_evaluated")]
    for k in range(n):
        out.append(dict(bar_close_ts=z(NOW - timedelta(hours=1 + k * 2 % 300)), final_action="skipped", skip_reason=skip,
                        veto_status="blocked"))
    return out


def run(trades=(), decisions=(), acts=(), status=None, state=None, mode="paper"):
    data = {"trades": list(trades), "decisions": list(decisions), "activations": list(acts)}
    return D.evaluate(data, status, state, NOW, bot="learner", mode=mode)


def lv(res, k):
    return res[0]["rules"][k]["level"]


# ------------------------------------------------------------------ S rules
@pytest.mark.parametrize("n,want", [(21, "OK"), (20, "IZLE"), (16, "IZLE"), (15, "UYARI"), (54, "OK"), (55, "IZLE"), (62, "UYARI")])
def test_s2_bounds(n, want):
    d = [dict(bar_close_ts=z(NOW - timedelta(days=20)), final_action="skipped", skip_reason="stop_width", veto_status="x")]
    d += [dict(bar_close_ts=z(NOW - timedelta(minutes=30 + k)), final_action="skipped", skip_reason="veto_blocked", veto_status="b")
          for k in range(n)]
    assert lv(run(decisions=d), "S2") == want


def test_s2_warmup_and_candidate_definition():
    d = [dict(bar_close_ts=z(NOW - timedelta(days=13)), final_action="skipped", skip_reason="stop_width", veto_status="x")]
    d += [dict(bar_close_ts=z(NOW - timedelta(hours=1 + k)), final_action="skipped", skip_reason="veto_blocked", veto_status="b") for k in range(30)]
    assert lv(run(decisions=d), "S2") == "YETERSIZ"
    d2 = [dict(bar_close_ts=z(NOW - timedelta(days=20)), final_action="skipped", skip_reason="stop_width", veto_status="x")]
    d2 += [dict(bar_close_ts=z(NOW - timedelta(minutes=10 + k)), final_action="skipped", skip_reason="stop_width", veto_status="x") for k in range(30)]
    assert lv(run(decisions=d2), "S2") == "UYARI"      # stop_width sayilmaz -> 0 aday
    d3 = d2[:1] + [dict(bar_close_ts=z(NOW - timedelta(minutes=10 + k)), final_action="skipped", skip_reason="entry_gate_closed", veto_status="x") for k in range(30)]
    assert lv(run(decisions=d3), "S2") == "OK"


@pytest.mark.parametrize("h,want", [(96, "OK"), (97, "IZLE"), (121, "UYARI")])
def test_s1(h, want):
    d = [dict(bar_close_ts=z(NOW - timedelta(days=50)), final_action="skipped", skip_reason="stop_width", veto_status="x"),
         dict(bar_close_ts=z(NOW - timedelta(hours=h)), final_action="entered", skip_reason=None, veto_status="allowed")]
    assert lv(run(decisions=d), "S1") == want


def test_s1_no_decisions_yetersiz():
    assert lv(run(), "S1") == "YETERSIZ"


def test_s2_downgraded_by_param_change_s1_not():
    d = [dict(bar_close_ts=z(NOW - timedelta(days=50)), final_action="skipped", skip_reason="stop_width", veto_status="x")]
    acts = [dict(activated_at=z(NOW - timedelta(days=3)), kind="apply", version_id=2)]
    res = run(decisions=d, acts=acts)
    assert lv(res, "S2") == "IZLE" and "ayar degisti" in res[0]["rules"]["S2"]["note"]
    assert lv(res, "S1") == "UYARI"        # son aday yok -> ilk karar 50 gun once; indirilmez


# ------------------------------------------------------------------ M / F rules
def test_m1():
    for bp, want in ((5.0, "OK"), (5.3, "IZLE"), (5.6, "UYARI")):
        assert lv(run([trade(i, fee_bp=bp) for i in range(20)]), "M1") == want
    assert lv(run([trade(i) for i in range(9)]), "M1") == "YETERSIZ"


def test_m2_and_paper_floor():
    for se, want in ((4.3e-4, "OK"), (4.4e-4, "IZLE"), (6.5e-4, "UYARI")):
        assert lv(run([trade(i, se=se) for i in range(20)]), "M2_giris") == want
    res = run([trade(i, se=1.4e-4) for i in range(20)], mode="paper")
    assert lv(res, "M2_giris") == "UYARI" and "benzetim tutarliligi" in res[0]["rules"]["M2_giris"]["note"]
    assert lv(run([trade(i, se=1.4e-4) for i in range(20)], mode="testnet"), "M2_giris") == "OK"
    # bos slippage_exit ortalamaya girmez
    ts = [trade(i, sx=None) for i in range(20)]
    assert lv(run(ts), "M2_stop") == "YETERSIZ"
    assert lv(run([trade(i, reason="time_stop", sx=7e-4) for i in range(20)]), "M2_piyasa") == "UYARI"


def test_m3_hand_formula():
    ts = [trade(i, qty=2.0, planned_entry=50.0, planned_exit=None, exit_price=60.0, fee_entry=0.01, fee_exit=0.02,
                slippage_entry=1e-4, slippage_exit=3e-4, risk=0.5) for i in range(20)]
    want = (0.01 + 0.02 + 2.0 * 50.0 * 1e-4 + 2.0 * 60.0 * 3e-4) / 0.5
    res = run(ts)
    assert abs(res[0]["rules"]["M3"]["value"] - want) < 1e-6
    for risk_scale, lvl in ((0.18, "OK"), (0.19, "IZLE"), (0.22, "UYARI")):
        ts = [trade(i, fee_entry=risk_scale / 2 * 10, fee_exit=risk_scale / 2 * 10, se=0.0, sx=0.0, risk=10.0) for i in range(20)]
        assert lv(run(ts), "M3") == lvl


def test_f1_f2():
    for v, want in ((0.020, "OK"), (0.021, "IZLE"), (0.031, "UYARI"), (-0.05, "IZLE")):
        assert lv(run([trade(i, fund=v * 10.0) for i in range(20)]), "F1") == want
    st = {"schema": "engine-status/1", "bot": "learner", "mode": "paper", "counters": {"funding_missing": 1}}
    assert lv(run(status=st), "F2") == "UYARI"
    st["counters"]["funding_missing"] = 0
    assert lv(run(status=st), "F2") == "OK"
    assert lv(run(status=None), "F2") == "YETERSIZ"


# ------------------------------------------------------------------ P1
def test_p1_interp_and_levels():
    assert D.interp_p1(60)[0] == pytest.approx(-28.2) and D.interp_p1(60)[1] == pytest.approx(-19.72)
    assert D.interp_p1(19) is None and D.interp_p1(301) is None

    def p1(total, n):
        ts = [trade(i, r=total / n) for i in range(n)]
        return run(ts)[0]["rules"]["P1"]
    assert p1(-28.0, 60)["level"] == "IZLE"
    assert p1(-28.3, 60)["level"] == "UYARI"
    assert p1(-1.0, 19)["level"] == "YETERSIZ"
    r = p1(1.0, 301)
    assert r["level"] == "YETERSIZ" and "tablo uzatilmali" in r["note"]


# ------------------------------------------------------------------ CUSUM
def test_cusum_formula_and_cooldown():
    cu = D.cusum_replay([-1.0] * 13)
    assert cu["S"] == pytest.approx(13 * 0.2263, abs=1e-2 * 0.5) and cu["alarms"] == []
    cu = D.cusum_replay([-1.0] * 20)
    assert cu["alarms"] == [20] and cu["S"] == 0.0
    cu = D.cusum_replay([-1.0] * 60)
    assert all(a - 20 >= 31 or a == 20 for a in cu["alarms"]) and cu["alarms"][0] == 20 and cu["alarms"][1] > 50
    # n<20 -> YETERSIZ gorunur, ama S ilk islemden birikir
    res = run([trade(i, r=-1.0) for i in range(18)])
    assert lv(res, "C1") == "YETERSIZ"
    assert D.cusum_replay([-1.0] * 18)["S"] == pytest.approx(4.07, abs=0.01)
    assert lv(run([trade(i, r=-1.0, exit_at=NOW - timedelta(hours=20 - i)) for i in range(20)]), "C1") == "UYARI"
    # once 20 kazanan, sonra kayiplar
    rs = [0.5] * 20 + [-1.0] * 14
    assert D.cusum_replay(rs)["S"] == pytest.approx(3.17, abs=0.01)
    assert lv(run([trade(i, r=r) for i, r in enumerate(rs)]), "C1") == "IZLE"
    assert D.cusum_replay([0.5] * 20 + [-1.0] * 18)["alarms"] == [38]
    assert D.cusum_replay([-1.0] * 10 + [10.0])["S"] == 0.0


def test_cusum_missed_days_equals_incremental():
    rs = [(-1.0 if i % 3 else 2.0) for i in range(80)]
    full = D.cusum_replay(rs)
    # parca parca ayni sonuc (her seferinde bastan isleme belirleyicidir)
    assert [D.cusum_replay(rs[:k])["S"] for k in (30, 60, 80)][-1] == full["S"]
    assert D.cusum_replay(rs[:75])["alarms"] == [a for a in full["alarms"] if a <= 75]


def test_c1_uyari_reported_once_then_sticky_then_gone():
    ts = [trade(i, r=-1.0, exit_at=NOW - timedelta(hours=20 - i)) for i in range(20)]
    data = {"trades": ts, "decisions": [], "activations": []}
    res, st = D.evaluate(data, None, None, NOW, bot="learner", mode="paper")
    assert res["rules"]["C1"]["level"] == "UYARI"
    # ayni gun yeniden calistirma (yeni islem yok): UYARI duser degil, kalir
    res_b, st_b = D.evaluate(data, None, st, NOW + timedelta(hours=6), bot="learner", mode="paper")
    assert res_b["rules"]["C1"]["level"] == "UYARI"
    assert st_b["cusum"]["uyari_reported_at"] == st["cusum"]["uyari_reported_at"]
    # 20 saati asinca (yeni islem yok) duser
    res2, _ = D.evaluate(data, None, st_b, NOW + timedelta(hours=21), bot="learner", mode="paper")
    assert res2["rules"]["C1"]["level"] != "UYARI"


def test_alarm_not_lost_without_state_or_status():
    ts = [trade(i, r=-1.0, exit_at=NOW - timedelta(hours=20 - i)) for i in range(20)]       # alarm islemi (20.) son 36 saat icinde kapandi
    data = {"trades": ts, "decisions": [], "activations": []}
    res, st = D.evaluate(data, None, None, NOW, bot="learner")
    assert res["rules"]["C1"]["level"] == "UYARI"
    old = [trade(i, r=-1.0, exit_at=NOW - timedelta(days=10, hours=-i)) for i in range(20)]
    res3, _ = D.evaluate({"trades": old, "decisions": [], "activations": []}, None, None, NOW, bot="learner")
    assert res3["rules"]["C1"]["level"] != "UYARI"
    # mod durumdan geri alinir; status.json okunamazsa kip kaybolmaz; pencere yalniz baslangictan eslesir
    s1 = {"schema": "engine-status/1", "bot": "learner", "mode": "testnet", "strategy": {"name": "a", "version": "1"}}
    _, st1 = D.evaluate(data, s1, None, NOW, bot="learner")
    res4, st4 = D.evaluate(data, None, st1, NOW + timedelta(hours=1), bot="learner")
    assert res4["mode"] == "testnet" and st4["mode"] == "testnet"


def test_window_start_uses_status_started_at_when_sane():
    base = {"schema": "engine-status/1", "bot": "learner", "mode": "paper", "ml": {"mode": "off"}}
    data = {"trades": [], "decisions": [], "activations": []}
    _, s1 = D.evaluate(data, dict(base, strategy={"name": "a", "version": "1"}), None, NOW, bot="learner")
    sa = NOW - timedelta(hours=3)
    r2, _ = D.evaluate(data, dict(base, strategy={"name": "a", "version": "2"}, started_at=z(sa)), s1, NOW, bot="learner")
    assert r2["window"]["start"] == z(sa)
    fut = dict(base, strategy={"name": "a", "version": "2"}, started_at=z(NOW + timedelta(hours=1)))
    r3, _ = D.evaluate(data, fut, s1, NOW, bot="learner")
    assert r3["window"]["start"] == z(NOW)


def test_skip_downgrade_flag_and_report_lines():
    ts = [trade(i, r=0.5) for i in range(30)] + [trade(99, planned_risk=0.0)]
    res = run(ts)[0]
    assert res["rules"]["M1"].get("skip_downgraded") is True
    lines = D.report_lines(res)
    assert any("1 kayıt okunamadı; karşılaştırma yaklaşık" in l for l in lines)
    assert not any("maliyeti beklenenin dışında" in l for l in lines)


def test_p1_report_line_range_and_f2_missing_key():
    res = run([trade(i, r=-0.1) for i in range(60)])[0]
    p1 = res["rules"]["P1"]
    assert p1["p10"] == pytest.approx(-19.72) and p1["p90"] > 30
    line = [l for l in D.report_lines(res) if "Kâr/zarar" in l][0]
    assert "olağan aralık −19,7 … +" in line and "," in line
    st = {"schema": "engine-status/1", "bot": "learner", "mode": "paper", "counters": {}}
    assert lv(run(status=st), "F2") == "YETERSIZ"


def test_future_activation_ignored_for_pv():
    acts = [dict(activated_at=z(NOW - timedelta(days=9)), kind="initial", version_id=1),
            dict(activated_at=z(NOW + timedelta(days=2)), kind="apply", version_id=7)]
    assert "|pv1" in run(acts=acts)[0]["window"]["key"]


# ------------------------------------------------------------------ pencere
def test_window_reset_on_activation():
    acts = [dict(activated_at=z(NOW - timedelta(days=100)), kind="initial", version_id=1),
            dict(activated_at=z(NOW - timedelta(hours=100)), kind="apply", version_id=2)]
    old = [trade(i, r=-1.0, entry_at=NOW - timedelta(hours=300 + i), exit_at=NOW - timedelta(hours=250 + i)) for i in range(30)]
    new = [trade(100 + i, r=0.0, entry_at=NOW - timedelta(hours=90 - i), exit_at=NOW - timedelta(hours=80 - i)) for i in range(5)]
    # eski pencerenin acik islemi yeni pencere baslayinca kapandi: eski pencereye yazilir (entry < activation)
    straddle = trade(200, r=-1.0, entry_at=NOW - timedelta(hours=150), exit_at=NOW - timedelta(hours=60))
    res = run(old + new + [straddle], acts=acts)[0]
    assert res["window"]["n"] == 5
    assert res["rules"]["P1"]["level"] == "YETERSIZ" and res["rules"]["C1"]["level"] == "YETERSIZ"
    assert res["window"]["start"] == z(NOW - timedelta(hours=100))


def test_window_reset_on_strategy_change_detected_across_runs():
    st1 = {"schema": "engine-status/1", "bot": "learner", "mode": "paper", "strategy": {"name": "a", "version": "1"}}
    res1, s1 = run(status=st1)
    st2 = dict(st1, strategy={"name": "a", "version": "2"})
    data = {"trades": [], "decisions": [], "activations": []}
    res2, s2 = D.evaluate(data, st2, s1, NOW, bot="learner", mode="paper")
    assert res2["window"]["start"] == z(NOW) and res1["window"]["start"] is None
    # 24.11: ML filtreleri silindi; durum dosyasindaki (eski) `ml` blogu pencereyi sifirlamaz, anahtar soneki sabit kalir
    st3 = dict(st1, ml={"mode": "active", "model_id": "m1"})
    res3, _ = D.evaluate(data, st3, s1, NOW, bot="learner", mode="paper")
    assert res3["window"]["start"] is None
    assert s1["window"]["status_key"] == "a@1|ml=inactive"


def test_bad_row_skipped():
    ts = [trade(i, r=0.5) for i in range(30)] + [trade(99, planned_risk=0.0), trade(98, r_multiple=float("nan"))]
    res = run(ts)[0]
    assert res["skipped_rows"] == 2
    for k in ("M1", "M3", "P1", "C1"):
        assert res["rules"][k]["level"] in ("IZLE", "UYARI")


def test_level_ceiling_and_schema_and_checkpoint():
    res = run([trade(i, r=-3.0, fee_bp=99) for i in range(40)], decisions=decs(500))[0]
    assert all(r["level"] in ("OK", "IZLE", "UYARI", "YETERSIZ") for r in res["rules"].values())
    assert res["overall"] in ("OK", "IZLE", "UYARI", "YETERSIZ") and res["plan_version"] == "kdp-v1" and res["schema"] == "drift/1"
    assert res["next_checkpoint"] == {"n": 100, "remaining": 60}
    assert D._next_checkpoint(200) == {"n": 300, "remaining": 100}
    assert D._next_checkpoint(0) == {"n": 30, "remaining": 30}
    assert D._worst(["OK", "YETERSIZ"]) == "YETERSIZ" and D._worst(["OK", "IZLE", "UYARI"]) == "UYARI"


def test_no_ledger_data_all_yetersiz():
    res = D.evaluate(None, None, None, NOW, bot="learner")[0]
    assert res["overall"] == "YETERSIZ" and all(r["level"] == "YETERSIZ" for r in res["rules"].values())


def test_reference_constants_pinned():
    assert D.REF_TRADES_SHA256 == "5fd204a0a34be9a2ced0d55a29f6893b1de361d897016062d6d557c2a7b69061"
    assert D.REF_SUMMARY_SHA256 == "ea2f58ca9a75f77895015978ec2beb8fa3af41924f39daa541531cba5a73228c"
    assert (D.CUSUM_MU0, D.CUSUM_SIGMA0, D.CUSUM_K, D.LAMBDA0) == (-0.111, 1.224, 0.5, 2.49)
    assert len(D.P1_TABLE) == 12 and D.P1_TABLE[0] == (20, -14.5, -11.1, -1.1, 16.9) and D.P1_TABLE[-1][0] == 300


# ------------------------------------------------------------------ gercek defter, salt okunurluk, kilitli donem
def _real_ledger(tmp_path):
    from trader_core import ledger as L
    bot_dir = tmp_path / "learner"
    bot_dir.mkdir()
    p = bot_dir / "ledger.sqlite"
    led = L.open_ledger(str(p), "learner", create=True)
    led.close()
    return p


def test_run_bot_readonly_ledger_writes_drift_json(tmp_path):
    p = _real_ledger(tmp_path)
    before = hashlib.sha256(p.read_bytes()).hexdigest()
    body, broken = D.run_bot(str(tmp_path), "learner", NOW)
    assert not broken and body["overall"] in D.LEVELS
    assert hashlib.sha256(p.read_bytes()).hexdigest() == before
    d = json.loads((tmp_path / "learner" / "drift.json").read_text())
    assert d["schema"] == "drift/1" and d["bot"] == "learner" and set(d) >= {
        "generated_at", "mode", "window", "rules", "overall", "skipped_rows", "next_checkpoint", "plan_version"}
    assert not list((tmp_path / "learner").glob("KILL*")) and not list((tmp_path / "learner").glob("PAUSE*"))


def test_run_bot_missing_and_corrupt_ledger(tmp_path):
    (tmp_path / "learner").mkdir()
    body, broken = D.run_bot(str(tmp_path), "learner", NOW)
    assert body["overall"] == "YETERSIZ" and not broken
    (tmp_path / "learner" / "ledger.sqlite").write_bytes(b"not a database" * 50)
    body, broken = D.run_bot(str(tmp_path), "learner", NOW)
    assert broken and body["overall"] == "YETERSIZ"


def test_load_ledger_is_read_only(tmp_path):
    p = _real_ledger(tmp_path)
    uri = "file:" + str(p) + "?mode=ro"
    c = sqlite3.connect(uri, uri=True)
    with pytest.raises(sqlite3.OperationalError):
        c.execute("CREATE TABLE x (a)")
    c.close()


def test_module_has_no_backtest_or_holdout_access():
    src = (ROOT / "src/trader_core/drift_monitor.py").read_text(encoding="utf-8")
    for bad in ("holdout", "backtest", "var/history", "trader_engine", "requests", "telegram", "subprocess"):
        assert bad not in src.replace("Telegram'a", "").replace("backtest_run_ml", "").replace("geri test", ""), bad


# ------------------------------------------------------------------ runner + saglik kancasi + dagitim
def test_runner_end_to_end_and_health_probe(tmp_path):
    import drift_run
    import health_run as HR
    from trader_core import health as H
    _real_ledger(tmp_path)
    rc = drift_run.main(["--bot", "learner", "--once", "--var-dir", str(tmp_path)], now_fn=lambda: NOW)
    assert rc == 0
    pr = HR.probe_drift(str(tmp_path / "learner" / "drift.json"), "learner")
    assert pr.file_state == "ok" and pr.generated_at == NOW and pr.overall in D.LEVELS
    assert HR.probe_drift(str(tmp_path / "twin" / "drift.json"), "twin").file_state == "missing"
    (tmp_path / "learner" / "drift.json").write_text("{bozuk")
    assert HR.probe_drift(str(tmp_path / "learner" / "drift.json"), "learner").file_state == "unreadable"
    assert HR.probe_drift(str(tmp_path / "learner" / "drift.json"), "twin").file_state in ("unreadable", "missing")
    assert drift_run.main(["--bot", "learner"]) == 1


def test_health_probe_collects_uyari_rules(tmp_path):
    import health_run as HR
    (tmp_path / "learner").mkdir()
    (tmp_path / "learner" / "drift.json").write_text(json.dumps(
        {"schema": "drift/1", "bot": "learner", "generated_at": z(NOW), "overall": "UYARI",
         "rules": {"S2": {"level": "UYARI"}, "M3": {"level": "OK"}, "C1": {"level": "UYARI"}}}))
    pr = HR.probe_drift(str(tmp_path / "learner" / "drift.json"), "learner")
    assert pr.overall == "UYARI" and pr.rules_at_uyari == ("C1", "S2")
    assert HR.collect_drift({"HEALTH_BOTS": "learner"}, str(tmp_path)) is None          # kapali
    on = HR.collect_drift({"HEALTH_BOTS": "learner,twin", "DRIFT_CHECK_ENABLED": "1"}, str(tmp_path))
    assert on["learner"].overall == "UYARI" and on["twin"].file_state == "missing"
    assert HR.make_cfg({"DRIFT_CHECK_ENABLED": "1"}).drift_check_enabled is True
    assert HR.make_cfg({"DRIFT_CHECK_ENABLED": ""}).drift_check_enabled is False


def test_deploy_units_and_install_wiring():
    dep = ROOT / "deploy"
    svc = (dep / "trader-drift@.service").read_text(encoding="utf-8")
    tm = (dep / "trader-drift@.timer").read_text(encoding="utf-8")
    ins = (dep / "install.sh").read_text(encoding="utf-8")
    assert "Slice=trader.slice" in svc and "Type=oneshot" in svc and "MemoryMax=64M" in svc and "PrivateNetwork=true" in svc and "RestrictAddressFamilies=AF_UNIX" in svc and "--bot %i --once" in svc
    assert "OnFailure=trader-health-fail@%n.service" in svc and "Telegram" not in svc.replace("Telegram'a", "")
    assert "EnvironmentFile=/etc/trader-telegram.env" not in svc
    assert "Europe/Istanbul" in tm and "WantedBy=timers.target" in tm
    assert "enable_now trader-drift@learner.timer" in ins and "enable_now trader-drift@twin.timer" not in ins   # DD-12
    assert "DRIFT_CHECK_ENABLED=1" in ins
    assert "DRIFT_CHECK_ENABLED=" in (dep / "trader-health.env.example").read_text(encoding="utf-8")


def test_install_first_run_and_env_newline_safe():
    ins = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")
    assert 'systemctl start "trader-drift@$1.service" || true' in ins and 'install -d -o "$TRADER_USER"' in ins
    assert "tail -c1 /etc/trader-health.env" in ins
