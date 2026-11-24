"""Ders servisi gerceklemesi icin hizli duman testleri (docs/ders-spec.md v1 + Revizyon 2).

Bagimsiz spec testleri `tests/test_lesson_spec.py`'dedir; burada gercek defter/butce/magaza dosyalari (tmp) ve
sahte `LlmClient` ile uctan uca akislar denenir. Gercek API cagrilmaz.
"""
import dataclasses
import json
import math
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import budget as B
from trader_core import ledger as L
from trader_core import lesson as LS
from trader_core.ledger import DecisionEvent, TradeEntry, TradeExit

# DD-12 WP-08: asagidaki testler kaldirilan davranislari (ikiz, golge donem, kanit esikleri/kalibrasyon sarti, haftalik sinir,
# 'her zaman kullaniciya sorulur', zaman/ikiz tabanli izleyici) sinar; yeni davranis tests/engine/test_dd12_wp08_impl.py ve
# bagimsiz spec testlerindedir.
OBSOLETE_DD12_WP08 = {
    "test_after_shadow_auto_apply_and_gates",
    "test_auto_closed_without_calibration_or_twin",
    "test_config_locks",
    "test_daily_summary_shape",
    "test_early_same_day_stops_do_not_rollback",
    "test_ledger_only_mode_rollback_and_fallback",
    "test_load_config_shipped_and_unknown",
    "test_monitor_early_rollback_and_same_day_shock_guard",
    "test_monitor_expiry_rolls_back_when_no_data",
    "test_monitor_m1_harm_rollback_and_blacklist",
    "test_monitor_m2_confirmed_and_rolled_back",
    "test_monitor_not_harm_pending_recheck_and_confirmed",
    "test_monitor_twin_benefit_conflict_blocks_rollback",
    "test_r3_ledger_only_monitor_runs_first_and_fallback_error_is_failsafe",
    "test_r3_log_notifier_never_counts_as_delivered",
    "test_r3_loosening_uses_missed_trades_mean_test_not_half_r_gap",
    "test_r3_reject_cooldown_blacklists_same_direction_only",
    "test_r3_twin_report_attributes_only_monitored_version",
    "test_runner_dry_run_and_once_rule_proxy",
    "test_snapshot_rr_min_up_candidate",
    "test_stop_buffer_always_user_and_extrapolated_route",
    "test_twin_codes",
    "test_twin_excludes_veto_and_gate_days",
    "test_twin_observed_loosening_and_ratchet",
    "test_twin_report_counts_and_verdict",
    "test_twin_unavailable_closes_auto",
    "test_user_approved_monitor_also_rolled_back",
    "test_user_version_not_rolled_back_and_superseded",
    "test_weekly_limit_gate_no_llm",
}


@pytest.fixture(autouse=True)
def _dd12_wp08_obsolete(request):
    if request.node.name in OBSOLETE_DD12_WP08:
        pytest.skip("DD-12 WP-08: kaldirilan eski davranis (ikiz/golge/esik/haftalik sinir/zaman-izleyici)")


UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5,
          "trigger_tf": "1h"}
PAIRS = ["ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"]
R_PER = 43.96   # exit fiyat farki basina 1R (planned_risk 13.188, qty 0.3)
D0 = datetime(2026, 10, 1, tzinfo=UTC)
RUN_DAY = "2026-12-09"
RUN_NOW = datetime(2026, 12, 9, 3, 0, tzinfo=UTC)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------------
# senaryo kurucular
# ---------------------------------------------------------------------------

def mk_dec(bar, pair, setup="R1", ver=1, rr=2.5, atr_ratio=1.1, stop=2.0, entered=True, skip=None, side="long"):
    if setup == "R1":
        regime, rh, rl, rht, rlt, target = "range", 2100.0, 1980.0, 2, 3, 2100.0
        feats = {"atr_1h": 20.0, "stop_dist_atr": stop, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": rr,
                 "edge_dist_atr": 0.1}
    else:
        regime, rh, rl, rht, rlt, target = ("trend_up" if side == "long" else "trend_down"), None, None, 0, 0, None
        feats = {"atr_1h": 20.0, "stop_dist_atr": stop, "atr_4h": 40.0, "pullback_ema": 50, "ema_value": 1995.0,
                 "body_ratio": 0.6}
    kw = dict(bar_close_ts=bar, trigger_tf="1h", pair=pair, side=side, setup=setup, regime=regime,
              atr_ratio=atr_ratio, rh=rh, rl=rl, rh_touches=rht, rl_touches=rlt, features=feats,
              planned_entry=2000.0, planned_stop=1960.0, planned_target=target, param_version_id=ver,
              veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
              size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
              final_action="entered", skip_reason=None)
    if not entered:
        vs = skip[5:] if skip and skip.startswith("veto_") else "not_evaluated"
        kw.update(final_action="skipped", skip_reason=skip, risk_allowed=None, veto_status=vs,
                  risk_reason=None, size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None,
                  leverage=None)
    return DecisionEvent(**kw)


class Env:
    """Gecici defter + ikiz + magaza; islem ekleme yardimcilari."""

    def __init__(self, tmp_path, now=RUN_NOW):
        self.tmp = tmp_path
        self.clock = Clock(now)
        self.led = L.open_ledger(tmp_path / "learner.sqlite", "learner", clock=self.clock)
        self.led.init_params(PARAMS, reason="baslangic")
        self.twin = L.open_ledger(tmp_path / "twin.sqlite", "twin", clock=self.clock)
        self.twin.init_params(PARAMS, reason="baslangic")
        self.tid = 0
        self.store_path = tmp_path / "lesson.sqlite"

    def add(self, day_offset, r, pair=None, setup="R1", ver=1, hour=10, led=None, rr=2.5, atr_ratio=1.1, stop=2.0,
            base=D0, side="long", exit_hours=4, bar_minute=0):
        led = led or self.led
        need = base + timedelta(days=day_offset, hours=hour + exit_hours + 1, minutes=bar_minute)
        if self.clock.t < need:
            self.clock.t = need
        self.tid += 1
        tid = self.tid
        bar = base + timedelta(days=day_offset, hours=hour, minutes=bar_minute)
        pair = pair or PAIRS[tid % len(PAIRS)]
        did = led.record_decision(mk_dec(bar, pair, setup, ver, rr, atr_ratio, stop, side=side))
        led.record_trade_entry(TradeEntry(tid, did, bar + timedelta(seconds=3), 2000.0, 0.3, 3, 0.0))
        xp = 2000.0 + r * R_PER if side == "long" else 2000.0 - r * R_PER
        led.record_trade_exit(TradeExit(tid, bar + timedelta(hours=exit_hours), xp, "time_stop", None, 0.0, 0.0))
        return did

    def add_pair(self, day_offset, r, **kw):
        """Ayni sinyal (anahtar) hem ogrenende hem ikizde (both)."""
        kw.setdefault("pair", PAIRS[(self.tid + 1) % len(PAIRS)])
        self.add(day_offset, r, led=self.led, **kw)
        self.add(day_offset, r, led=self.twin, **{**kw, "ver": 1})

    def close(self):
        self.led.close()
        self.twin.close()


def r1_scenario(env: Env, n=34, ver=1, twin=True, base=D0):
    """14.1 benzeri: ilk 30 islemde rr in [1.5,1.75) -> kotu (A), kalan iyi (B); her islem ayri gun."""
    a_r = [-1.0, 0.2, -0.6, -0.2, -1.0, 0.0, -0.8, -0.4, -0.2]
    b_r = [1.0, -0.5, 1.5, 0.3, 0.9, 0.4, 1.2, -0.2, 0.8, 0.6, 0.5, 1.1, 0.2, 0.7, 0.3, 1.4, 0.1, 0.9, 0.6, 0.5, 0.8]
    ai = bi = 0
    for i in range(n):
        pair = PAIRS[i % len(PAIRS)]
        if i < 30 and i % 3 == 0 and ai < len(a_r):
            r, rr = a_r[ai], 1.6
            ai += 1
        else:
            r, rr = b_r[bi % len(b_r)], 2.5
            bi += 1
        env.tid += 0
        if twin:
            env.add_pair(i, r, pair=pair, ver=ver, rr=rr, base=base)
        else:
            env.add(i, r, pair=pair, ver=ver, rr=rr, base=base)
    env.clock.t = max(env.clock.t, RUN_NOW)


LEGACY_CFG = dict(checkpoints=(30, 45, 60), min_affected=8, min_gap_r=0.5, min_z=2.0, min_distinct_days=8,
                  max_pair_share=0.5, max_user_requests_per_week=1, shadow_weeks=4)


def good_cal(day="2026-12-01", **over):
    cal = {"ok": True, "date": day, "rule_version": LS.RULES_VERSION, "min_z": 2.0, "min_gap_r": 0.5,
           "min_affected": 8, "monitor_z": 1.0, "monitor_margin_r": 0.3, "twin_z": 1.0, "twin_margin_r": 0.1}
    cal.update(over)
    return cal


def mk_cfg(tmp_path, **over):
    d = dict(ledger_path=str(tmp_path / "learner.sqlite"), store_path=str(tmp_path / "lesson.sqlite"),
             mode="rule_proxy", checkpoints=(30, 45, 60), min_affected=8, min_gap_r=0.5, min_z=2.0,
             min_distinct_days=8, max_pair_share=0.5,
             max_user_requests_per_week=1, shadow_weeks=4)      # eski esikli rejim (DD-12 WP-08 varsayilanlari esiksiz)
    d.update(over)
    for k in [k for k in d if k.startswith("twin_") or k in ("report_show_twin", "max_steps_from_twin")]:
        d.pop(k)                                       # ikiz kaldirildi (DD-12 WP-07/08)
    return LS.LessonConfig(**d)


def mk_budget(tmp_path, clk=None):
    return B.BudgetGuard(B.BudgetConfig(db_path=str(tmp_path / "budget.sqlite")), clock=clk or Clock(RUN_NOW))


def mk_service(env: Env, cfg, **kw):
    store = kw.pop("store", None) or LS.LessonStore(env.store_path, clock=env.clock)
    kw.setdefault("notifier", LS.NullNotifier())
    kw.setdefault("lock_path", None)
    svc = LS.LessonService(cfg, ledger=env.led, store=store, twin=env.twin, clock=env.clock,
                           sleep_fn=lambda s: None, **kw)
    return svc, store


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.close()


class FakeLlm:
    """Sahte LlmClient: gercek API yok."""

    def __init__(self, responder=None, ready_after=0, submit_errors=()):
        self.responder = responder
        self.submitted = []
        self.polls = 0
        self.ready_after = ready_after
        self.submit_errors = list(submit_errors)
        self.cancelled = []

    def submit(self, bundle, custom_id):
        if self.submit_errors:
            raise self.submit_errors.pop(0)
        self.submitted.append((bundle, custom_id))
        return "batch_fake_1"

    def poll(self, batch_id):
        self.polls += 1
        if self.polls <= self.ready_after:
            return LS.BatchPoll("in_progress")
        bundle, cid = self.submitted[-1]
        text, stop, usage = self.responder(bundle)
        return LS.BatchPoll("ended", (LS.BatchResult(cid, "succeeded", text, stop, usage),))

    def cancel(self, batch_id):
        self.cancelled.append(batch_id)


def run_snapshot(env, cfg, **kw):
    kw.setdefault("twin_ro", env.twin)
    return LS.build_snapshot(env.led, cfg, RUN_DAY, **kw)


def response_for(snap, menu_id="rr_min:up", **over):
    e = snap.entry(menu_id)
    keys = LS._required_cites(e)
    obj = {"schema": "lesson_response_v1", "decision": "change", "menu_id": menu_id, "param": e.param,
           "to": e.to_value, "rationale": "kanit yeterli", "confidence": "medium",
           "cited": [{"key": k, "value": snap.facts[k]} for k in keys]}
    obj.update(over)
    return json.dumps(obj)


# ---------------------------------------------------------------------------
# istatistik ilkelleri (14.1, 14.4, 14.6, 14.14)
# ---------------------------------------------------------------------------

def synth(n, m, s, tag):
    import random
    rnd = random.Random(1)
    x = [rnd.gauss(0, 1) for _ in range(n)]
    mu = sum(x) / n
    sdv = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1))
    return [((v - mu) / sdv * s + m, f"{tag}{i}") for i, v in enumerate(x)]


def test_cluster_diff_examples():
    z = LS.cluster_diff(synth(9, -0.4, 0.9, "a"), synth(21, 0.5, 1.1, "b"), 8)
    assert z.z == pytest.approx(2.4095, abs=1e-3)
    assert z.se == pytest.approx(0.373532, abs=1e-4)
    z = LS.cluster_diff(synth(27, -0.05, 1.0, "b"), synth(9, 0.6, 0.8, "a"), 8)
    assert z.z == pytest.approx(2.0382, abs=1e-3)
    z = LS.cluster_diff(synth(24, 0.30, 1.10, "p"), synth(20, -0.25, 1.0, "n"), 8)
    assert z.z == pytest.approx(-1.7566, abs=1e-3)
    zg = LS.cluster_mean(synth(12, 1.1, 0.8, "g"), 0.5, 8)
    assert zg.z == pytest.approx(2.598, abs=1e-3)


def test_cluster_small_g_undefined_and_same_day_cluster():
    a = [(-1.0, "d%d" % i) for i in range(3)]
    b = [(1.0, "e%d" % i) for i in range(3)]
    zr = LS.cluster_diff(a, b, 8)
    assert zr.z is None and not zr.defined and zr.g == 6
    # ayni gun kumelenmis: tek gun
    same = LS.cluster_diff([(0.0, "x")] * 5, [(-1.0, "x")] * 5, 1)
    assert same.z is None


# ---------------------------------------------------------------------------
# yapilandirma
# ---------------------------------------------------------------------------

def test_config_locks(tmp_path):
    LS.LessonConfig(**LEGACY_CFG)
    for bad in (dict(shadow_weeks=3), dict(shadow_weeks=7), dict(bot="twin"), dict(checkpoints=(20, 45)),
                dict(checkpoints=(30, 30)), dict(checkpoints=(30, 130)), dict(min_gap_r=0.4), dict(min_z=1.5),
                dict(max_pair_share=0.6),
                dict(blacklist_days=7), dict(max_user_requests_per_week=3), dict(batch_max_age_h=12),
                dict(max_output_tokens=4000), dict(mode="x"), dict(run_at_utc="25:00"), dict(paper_start_day="x"),
                dict(twin_min_keys=5), dict(monitor_recheck_n=10), dict(prompt_max_est_tokens=30000)):
        with pytest.raises(LS.LessonConfigError):
            LS.LessonConfig(**bad)
    with pytest.raises(LS.LessonConfigError):   # kalibre degerden gevsek olamaz
        LS.LessonConfig(min_z=2.0, calibration=good_cal(min_z=2.5))
    LS.LessonConfig(min_z=3.0, calibration=good_cal(min_z=2.5))


def test_load_config_shipped_and_unknown(tmp_path):
    cfg = LS.load_config(ROOT / "config" / "lesson.json")
    import dataclasses
    # gonderilen ayar = kod varsayilanlari + sunucu yollari/bildirimci (hazirlik denetimi OPEN-6)
    assert cfg == dataclasses.replace(LS.LessonConfig(**LEGACY_CFG), ledger_path="var/learner/ledger.sqlite",
                                      twin_ledger_path="var/twin/ledger.sqlite", notifier="telegram")
    assert cfg.shadow_weeks == 4 and cfg.model == "claude-sonnet-5-5"
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"zzz": 1}))
    with pytest.raises(LS.LessonConfigError):
        LS.load_config(p)
    p.write_text(json.dumps({"model": "gpt-x"}))
    with pytest.raises(LS.LessonConfigError):
        LS.load_config(p)


def test_calibration_status():
    assert LS.calibration_status(LS.LessonConfig(**LEGACY_CFG), RUN_DAY)[0] is False
    c = LS.LessonConfig(calibration=good_cal())
    assert LS.calibration_status(c, RUN_DAY) == (True, "ok")
    assert LS.calibration_status(c, "2027-06-01")[0] is False          # 90 gunden eski
    assert LS.calibration_status(LS.LessonConfig(calibration=good_cal(rule_version="old")), RUN_DAY)[0] is False
    assert LS.calibration_status(LS.LessonConfig(calibration=good_cal(ok=False)), RUN_DAY)[0] is False


# ---------------------------------------------------------------------------
# anlik goruntu, kontrol noktalari, havuz
# ---------------------------------------------------------------------------

def test_snapshot_rr_min_up_candidate(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal())
    snap = run_snapshot(env, cfg)
    e = snap.entry("rr_min:up")
    assert e.eligible and e.auto_capable and e.evidence_class == "observed_subset"
    assert e.from_value == 1.5 and e.to_value == 1.75 and e.n_scope == 34 and e.checkpoint_c == 30
    assert e.n_a == 9 and e.n_b == 21 and e.gap >= 0.5 and e.z >= 2.0
    assert snap.facts["menu.rr_min:up.n_scope"] == 34
    assert [c.c for c in snap.new_checkpoints if c.param == "rr_min"] == [30]
    assert snap.twin["available"] and snap.shadow["active"] is True          # paper_start yok -> run_day
    assert "rr_min:down" not in [m.menu_id for m in snap.menu if m.evidence_class == "observed_subset"]
    # stop_buffer_atr:up asla auto_capable degil; trail_atr:up/stop_buffer:down yok
    ids = {m.menu_id for m in snap.menu}
    assert "trail_atr:up" not in ids and "stop_buffer_atr:down" not in ids
    assert all(not m.auto_capable for m in snap.menu if m.menu_id == "stop_buffer_atr:up")


def test_checkpoint_frozen_and_below_first(env, tmp_path):
    r1_scenario(env, n=24)
    cfg = mk_cfg(tmp_path)
    snap = run_snapshot(env, cfg)
    e = snap.entry("rr_min:up")
    assert not e.eligible and e.fail_reasons == ("not_at_checkpoint",) and snap.new_checkpoints == []


def test_checkpoint_known_not_reevaluated(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path)
    s1 = run_snapshot(env, cfg)
    cps = list(s1.new_checkpoints)
    s2 = run_snapshot(env, cfg, known_checkpoints=cps)
    assert s2.new_checkpoints == []
    assert s2.entry("rr_min:up").eligible and s2.stats_hash == s1.stats_hash
    # gecerlilik: 8 gun sonra dusmus
    late = LS.build_snapshot(env.led, cfg, "2026-12-18", twin_ro=env.twin, known_checkpoints=cps)
    assert late.entry("rr_min:up").fail_reasons == ("not_at_checkpoint",)


def test_as_of_exclusive_and_hash_stable(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path)
    s1 = run_snapshot(env, cfg)
    # as_of sonrasi islem eklense bile hash ayni
    env.clock.t = datetime(2026, 12, 11, tzinfo=UTC)
    env.add(70, 1.0, pair="ETH/USDT", base=D0, rr=2.5)       # 2026-12-10 (as_of sonrasi)
    s2 = run_snapshot(env, cfg)
    assert s1.stats_hash == s2.stats_hash and s1.as_of == "2026-12-09T00:00:00.000Z"
    LS.assert_no_future(s1, LS.as_of_for(RUN_DAY))
    bad = dataclasses.replace(s1, max_source_ts="2026-12-09T00:00:00.000Z")
    with pytest.raises(LS.FutureLeakError):
        LS.assert_no_future(bad, LS.as_of_for(RUN_DAY))


def test_pooling_and_scope_disjoint_change(env, tmp_path):
    """14.10: kapsami ayrik degisiklik T1 kanitini sifirlamaz."""
    base = D0
    for i in range(21):
        env.add(i, 0.2, setup="R1", ver=1, pair=PAIRS[i % 6], base=base)
    for i in range(25):
        env.add(21 + i, 0.1, setup="T1", ver=1, pair=PAIRS[i % 6], base=base)
    pid = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x",
                                 claimed_evidence={}, source="t").proposal_id
    env.clock.t = datetime(2026, 11, 20, 12, tzinfo=UTC)
    assert env.led.apply_proposal(pid, actor="user", reason="onay").ok
    env.clock.t = RUN_NOW
    for i in range(13):
        env.add(50 + i, 0.1, setup="T1", ver=2, pair=PAIRS[i % 6], base=base, rr=2.5)
    cfg = mk_cfg(tmp_path)
    snap = LS.build_snapshot(env.led, cfg, "2026-12-20", twin_ro=env.twin)
    assert snap.scopes["T1"]["stats"]["n_closed"] == 38 and snap.scopes["R1"]["stats"]["n_closed"] == 0
    t1_entries = [m for m in snap.menu if m.scope == "T1+H2+S1+TF1"]      # 24.11: kapsam = trail_atr okuyan kurulumlar
    assert t1_entries and all(m.n_scope == 38 for m in t1_entries)
    cps = [c for c in snap.new_checkpoints if c.param == "trail_atr"]
    assert [c.c for c in cps] == [30]
    # rr_min akisi yeni (v2'de 0 R1 islemi)
    assert not any(c.param == "rr_min" for c in snap.new_checkpoints)


def test_prompt_no_leak_and_enum(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path)
    snap = run_snapshot(env, cfg)
    pb = LS.render_prompt(snap, cfg)
    text = pb.system + pb.user
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text) and "/USDT" not in text
    assert not re.search(r"btc|eth|sk-ant", text, re.I) and "sha256" not in text
    assert "<data>" in pb.user and pb.user.count("[recent_trades]") == 1
    assert pb.est_in_tokens == math.ceil(len(text.encode()) / 2) and not pb.too_large
    # kucultme
    small = dataclasses.replace(cfg, prompt_max_est_tokens=pb.est_in_tokens - 1)
    pb2 = LS.render_prompt(snap, small)
    assert pb2.recent_n_used < pb.recent_n_used
    tiny = dataclasses.replace(cfg, prompt_max_est_tokens=100)
    assert LS.render_prompt(snap, tiny).too_large
    assert pb.request_hash == LS.render_prompt(snap, cfg).request_hash       # belirleyici


# ---------------------------------------------------------------------------
# yanit dogrulama G0-G5 ve vekil
# ---------------------------------------------------------------------------

def test_parse_and_validate_codes(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path)
    snap = run_snapshot(env, cfg)
    ok = response_for(snap)
    v = LS.parse_and_validate(ok, "end_turn", snap, cfg)
    assert isinstance(v, LS.ProposalDraft) and v.menu_id == "rr_min:up" and v.to == 1.75
    pv = lambda t, stop="end_turn", **k: LS.parse_and_validate(t, stop, snap, cfg, **k)   # noqa: E731
    assert pv(ok, "max_tokens").code == "llm_bad_stop" and pv(ok, "refusal").code == "llm_bad_stop"
    assert pv(ok, "end_turn", result_type="errored").code == "llm_bad_stop"
    assert pv("```json\n" + ok + "\n```").code == "bad_json" and pv("nope").code == "bad_json"
    assert pv(ok.replace('"to"', '"to2"')).code == "bad_schema"
    assert pv(json.dumps({**json.loads(ok), "extra": 1})).code == "bad_schema"
    assert pv(json.dumps({**json.loads(ok), "to": True})).code == "bad_schema"
    assert pv(ok.replace("1.75", "NaN")).code == "bad_json"
    nc = {"schema": "lesson_response_v1", "decision": "no_change", "menu_id": None, "param": None, "to": None,
          "rationale": "yetersiz", "cited": [], "confidence": "low"}
    assert pv(json.dumps(nc)).decision == "no_change"
    assert pv(json.dumps({**nc, "menu_id": "rr_min:up"})).code == "bad_schema"
    obj = json.loads(ok)
    assert pv(json.dumps({**obj, "menu_id": "trail_atr:up", "param": "trail_atr"})).code == "unknown_menu_id"
    assert pv(json.dumps({**obj, "menu_id": "range_width_atr:up", "param": "range_width_atr"})).code == \
        "off_menu_not_allowed"
    assert pv(json.dumps({**obj, "to": 1.9})).code == "menu_mismatch"
    assert pv(json.dumps({**obj, "cited": obj["cited"][:2]})).code == "cited_missing"
    bad = [dict(c) for c in obj["cited"]]
    bad[2]["value"] = 3.1
    assert pv(json.dumps({**obj, "cited": bad})).code == "cited_mismatch"
    # uygun degil aday
    snap2 = run_snapshot(env, cfg)
    ineligible = next(m for m in snap2.menu if not m.eligible)
    o2 = {**obj, "menu_id": ineligible.menu_id, "param": ineligible.param, "to": ineligible.to_value}
    assert LS.parse_and_validate(json.dumps(o2), "end_turn", snap2, cfg).code == "candidate_ineligible"
    # allow_off_menu: menu disi ama iyi bicimli -> taslak off_menu
    cfg_off = dataclasses.replace(cfg, allow_off_menu=True)
    d = LS.parse_and_validate(json.dumps({**obj, "menu_id": "trail_atr:up", "param": "trail_atr", "to": 3.5}),
                              "end_turn", snap, cfg_off)
    assert d.off_menu and LS.classify_route(snap, d, cfg_off).reason_code == "shadow_period"
    assert "off_menu" in LS.classify_route(snap, d, cfg_off).reasons
    # rationale sanitize
    inj = LS.parse_and_validate(json.dumps({**obj, "rationale": "see http://x.io **bold** `rm -rf`\x00"}),
                                "end_turn", snap, cfg)
    assert "http" not in inj.rationale and "*" not in inj.rationale and "`" not in inj.rationale


def test_rule_proxy_selection(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal())
    snap = run_snapshot(env, cfg)
    d = LS.propose_rule_proxy(snap, cfg)
    assert d.menu_id == "rr_min:up" and d.source == "rule-proxy" and d.rationale.startswith("proxy: rr_min:up z=")
    assert len(d.cited) >= 3
    none = LS.propose_rule_proxy(dataclasses.replace(snap, menu=[
        dataclasses.replace(m, eligible=False) for m in snap.menu]), cfg)
    assert none.decision == "no_change"


# ---------------------------------------------------------------------------
# uctan uca: golge donem (rule_proxy)
# ---------------------------------------------------------------------------

def test_shadow_period_needs_user_then_approve(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-11-30")
    svc, store = mk_service(env, cfg)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "needs_user" and res.code == "shadow_period", res
    props = env.led.list_proposals()
    assert len(props) == 1 and props[0].status == "needs_user" and props[0].code == "user_approval_required"
    assert env.led.apply_proposal(props[0].id, actor="lesson", reason="x").code == "user_approval_required"
    nt = svc._notifier
    assert len(nt.requests) == 1
    rq = nt.requests[0]
    assert rq.shadow_period and rq.reason_code == "shadow_period" and rq.request_id == f"lr-{RUN_DAY}-{props[0].id}"
    assert rq.shadow_ends_on == "2026-12-28" and len(rq.title) <= 80 and len(rq.body) <= 700
    # idempotent ayni gun
    assert svc.run_tick(RUN_NOW).status == "idle"
    assert len(env.led.list_proposals()) == 1
    # kullanici onayi
    ok = svc.resolve_request(rq.request_id, True, "tg:42")
    assert ok.status == "approved" and ok.version_id == 2
    again = svc.resolve_request(rq.request_id, True, "tg:42")
    assert (again.status, again.code, again.version_id) == (ok.status, ok.code, ok.version_id)
    assert env.led.get_active_params().params["rr_min"] == 1.75
    mon = store.monitor_by_version(2)
    assert mon is not None and mon.origin == "user" and mon.base_version_id == 1 and mon.param == "rr_min"
    assert mon.scope == "R1+B1+F1" and mon.k == 20 and mon.recheck_n == 30      # 24.11: kapsam = rr_min'i okuyan tum kurulumlar
    store.close()


def test_shadow_reject_and_timeout(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-11-30")
    svc, store = mk_service(env, cfg)
    svc.run_tick(RUN_NOW)
    rid = svc._notifier.requests[0].request_id
    pid = svc._notifier.requests[0].proposal_id
    r = svc.resolve_request(rid, False, "tg")
    assert r.status == "rejected"
    assert env.led.get_proposal(pid).status == "rejected"
    assert svc.resolve_request("lr-none", True, "tg").status == "unknown"
    store.close()
    # zaman asimi
    env2 = Env(tmp_path / "b") if (tmp_path / "b").mkdir() is None else None
    try:
        r1_scenario(env2)
        cfg2 = mk_cfg(tmp_path / "b", calibration=good_cal(), paper_start_day="2026-11-30")
        svc2, st2 = mk_service(env2, cfg2)
        svc2.run_tick(RUN_NOW)
        pid2 = svc2._notifier.requests[0].proposal_id
        env2.clock.t = RUN_NOW + timedelta(days=3, hours=1)
        svc2.run_tick()
        assert env2.led.get_proposal(pid2).status == "rejected"
        assert any(n.code == "needs_user_expired" for n in svc2._notifier.notices)
        rr = svc2.resolve_request(svc2._notifier.requests[0].request_id, True, "tg")
        assert rr.status == "expired"
        st2.close()
    finally:
        env2.close()


def test_after_shadow_auto_apply_and_gates(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-10-01")
    svc, store = mk_service(env, cfg)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "applied", res
    assert env.led.get_active_params().params["rr_min"] == 1.75
    prop = env.led.list_proposals()[0]
    assert prop.status == "applied" and prop.source == "rule-proxy" and prop.status_actor == "lesson"
    mon = store.monitor_by_version(2)
    assert mon.origin == "auto" and mon.state == "open"
    assert any(n.code == "applied" for n in svc._notifier.notices)
    # ertesi gun: izleyici acik -> on kapi
    env.clock.t = RUN_NOW + timedelta(days=1)
    res2 = svc.run_tick()
    assert res2.status == "skipped_gate" and res2.code == "monitor_open"
    store.close()


def test_auto_closed_without_calibration_or_twin(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, paper_start_day="2026-10-01")         # kalibrasyon yok
    svc, store = mk_service(env, cfg)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "needs_user" and res.code == "calibration_required"
    rq = svc._notifier.requests[0]
    assert rq.provisional and not rq.shadow_period
    store.close()


def test_twin_unavailable_closes_auto(env, tmp_path):
    r1_scenario(env, twin=False)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-10-01")
    store = LS.LessonStore(env.store_path, clock=env.clock)
    svc = LS.LessonService(cfg, ledger=env.led, store=store, twin_code="twin_missing", clock=env.clock,
                           notifier=LS.NullNotifier(), lock_path=None)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "needs_user" and res.code == "twin_unavailable"
    store.close()


def test_stop_buffer_always_user_and_extrapolated_route(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-10-01")
    snap = run_snapshot(env, cfg)

    def draft(mid, to, p):
        return LS.ProposalDraft("change", mid, p, to, "x", (), "low")
    sb = LS.classify_route(snap, draft("stop_buffer_atr:up", 0.4, "stop_buffer_atr"), cfg)
    assert sb.klass == "ask_user" and sb.reason_code == "always_user"
    vu = LS.classify_route(snap, draft("vol_ratio_max:up", 1.7, "vol_ratio_max"), cfg)
    assert vu.klass == "ask_user" and vu.reason_code == "ledger_needs_user"
    rm = LS.classify_route(snap, draft("range_target_frac:down", 0.625, "range_target_frac"), cfg)
    assert rm.reason_code == "weak_evidence"
    auto = LS.classify_route(snap, draft("rr_min:up", 1.75, "rr_min"), cfg)
    assert auto.klass == "auto" and auto.reason_code is None


# ---------------------------------------------------------------------------
# LLM yolu: sahte istemci + gercek butce
# ---------------------------------------------------------------------------

def llm_env(env, tmp_path, **cfg_over):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, mode="llm", calibration=good_cal(), paper_start_day="2026-10-01", **cfg_over)
    snap = run_snapshot(env, cfg)
    usage = {"input_tokens": 5000, "output_tokens": 900}
    llm = FakeLlm(lambda b: (response_for(snap), "end_turn", usage))
    bud = mk_budget(tmp_path, env.clock)
    return cfg, snap, llm, bud


def test_llm_flow_poll_then_apply_and_budget(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    llm.ready_after = 1
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    r1 = svc.run_tick(RUN_NOW)
    assert r1.status == "in_progress" and len(llm.submitted) == 1
    ps = bud.status().services["lesson"]
    assert ps.unsettled_usd > 0                      # rezervasyon acik
    env.clock.t = RUN_NOW + timedelta(hours=1)
    r2 = svc.run_tick()
    assert r2.status == "applied", r2
    assert len(llm.submitted) == 1                   # tekrar gonderilmedi
    st = bud.status().services["lesson"]
    assert st.settled_usd == pytest.approx(0.0095) and st.unsettled_usd == 0
    run = store.get_run(RUN_DAY)
    call = store.get_call(run.id)
    res = store.get_result(call["id"])
    assert call["request_hash"] == LS.sha256_hex(call["request_text"])
    b0 = llm.submitted[0][0]
    assert b0.system in call["request_text"] and b0.user in call["request_text"] and call["batch_id"] == "batch_fake_1"
    assert call["request_hash"] == b0.request_hash
    assert res["cost_micro"] == 9500 and res["result_type"] == "succeeded"
    assert LS.sha256_hex(res["response_text"]) == res["response_hash"]
    assert "sk-ant" not in call["request_text"] + res["response_text"]
    assert env.led.get_proposal(1).source == "claude-sonnet-5-5-batch"
    assert svc.daily_summary(RUN_DAY)["llm_cost_usd"] == pytest.approx(0.0095)
    store.close()


def test_llm_invalid_cited_no_change(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    bad = json.loads(response_for(snap))
    bad["cited"][2]["value"] = 3.1
    llm.responder = lambda b: (json.dumps(bad), "end_turn", {"input_tokens": 100, "output_tokens": 50})
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "no_change" and res.code == "cited_mismatch"
    assert env.led.list_proposals() == []
    run = store.get_run(RUN_DAY)
    assert any(e.status == "llm_invalid" for e in store.run_events(run.id))
    assert store.get_result(store.get_call(run.id)["id"])["response_text"]      # yine saklanir
    store.close()


def test_llm_no_change_and_bad_stop(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    nc = json.dumps({"schema": "lesson_response_v1", "decision": "no_change", "menu_id": None, "param": None,
                     "to": None, "rationale": "yetersiz", "cited": [], "confidence": "low"})
    llm.responder = lambda b: (nc, "end_turn", {"input_tokens": 10, "output_tokens": 5})
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    assert svc.run_tick(RUN_NOW).status == "no_change"
    store.close()


def test_budget_denial_skips_but_deterministic_steps_run(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    tiny = B.BudgetGuard(B.BudgetConfig(db_path=str(tmp_path / "b2.sqlite"), daily_cap_usd={"haftalik_ozet": 0.25, "lesson": 0.01}),
                         clock=env.clock)
    svc, store = mk_service(env, cfg, llm=llm, budget=tiny)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "skipped_budget" and res.code == "daily_cap" and llm.submitted == []
    run = store.get_run(RUN_DAY)
    evs = [e.status for e in store.run_events(run.id)]
    assert "stats_done" in evs and store.get_snapshot(run.id) is not None
    store.close()


def test_llm_http_error_report_error_and_stop(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    llm.submit_errors = [LS.LlmHttpError(429, "rate_limit_error", None, "slow", None)]
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "applied"                   # 1 yeniden deneme sonrasi
    store.close()


def test_llm_provider_stop(tmp_path):
    env = Env(tmp_path)
    try:
        cfg, snap, llm, bud = llm_env(env, tmp_path)
        llm.submit_errors = [LS.LlmHttpError(400, "invalid_request_error", None,
                                             "You have reached your specified API usage limits", None)]
        svc, store = mk_service(env, cfg, llm=llm, budget=bud)
        res = svc.run_tick(RUN_NOW)
        assert res.status == "skipped_budget" and res.code == "provider_blocked"
        store.close()
    finally:
        env.close()


def test_submit_unknown_after_crash(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    # reserve olayi var, submitted yok (cokme)
    store.set_shadow_once("2026-10-01", "2026-10-29")
    run = store.create_run(cfg, RUN_DAY)
    store.add_event(run.id, "stats_done")
    store.add_event(run.id, "gates_passed")
    g = bud.authorize("lesson", 0.0165)
    store.add_event(run.id, "llm_reserved", None, {"grant": dataclasses.asdict(g), "call_id": 1})
    # stats_done sonrasi anlik goruntu gerekir
    store.save_snapshot(run.id, snap)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "failed" and res.code == "submit_unknown" and res.exit_code == 2
    assert llm.submitted == []
    store.close()


def test_llm_timeout(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    llm.ready_after = 10 ** 6
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    assert svc.run_tick(RUN_NOW).status == "in_progress"
    env.clock.t = RUN_NOW + timedelta(hours=26)
    svc.run_tick()
    last = store.run_events(store.get_run(RUN_DAY).id)[-1]
    assert last.status == "failed" and last.code == "llm_timeout" and llm.cancelled == ["batch_fake_1"]
    store.close()


def test_mode_both_records_shadow(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    cfg = dataclasses.replace(cfg, mode="both")
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    assert svc.run_tick(RUN_NOW).status == "applied"
    run = store.get_run(RUN_DAY)
    sh = store.decisions(run.id, "shadow")
    assert sh and sh[0]["menu_id"] == "rr_min:up" and sh[0]["source"] == "rule-proxy"
    summ = svc.daily_summary(RUN_DAY)
    assert summ["shadow"] == {"proxy_menu_id": "rr_min:up", "same": True}
    store.close()


# ---------------------------------------------------------------------------
# on kapilar
# ---------------------------------------------------------------------------

def test_weekly_limit_gate_no_llm(env, tmp_path):
    r1_scenario(env)
    # surum 2 5 gun once lesson tarafindan uygulandi
    env.clock.t = datetime(2026, 12, 5, 12, tzinfo=UTC)
    pid = env.led.propose_change(base_version_id=1, changes={"vol_ratio_max": 1.3}, rationale="x",
                                 claimed_evidence={}, source="t").proposal_id
    assert env.led.apply_proposal(pid, actor="lesson", reason="x").ok
    env.clock.t = RUN_NOW
    cfg = mk_cfg(tmp_path, mode="llm", calibration=good_cal(), paper_start_day="2026-10-01")
    llm = FakeLlm(lambda b: ("", "end_turn", {}))
    svc, store = mk_service(env, cfg, llm=llm, budget=mk_budget(tmp_path, env.clock))
    store.add_monitor(LS.Monitor(2, 1, "vol_ratio_max", 1.5, 1.3, "T1+R1", pid, "2026-12-05T12:00:00.000Z", 20, 30))
    store.add_monitor_event(1, "confirmed", {})        # izleyici kapali; haftalik kapi kalir
    res = svc.run_tick(RUN_NOW)
    assert res.status == "skipped_gate" and res.code == "weekly_limit" and llm.submitted == []
    store.close()


def test_no_data_gate(env, tmp_path):
    r1_scenario(env, n=24)
    cfg = mk_cfg(tmp_path, mode="llm", calibration=good_cal())
    llm = FakeLlm(lambda b: ("", "end_turn", {}))
    svc, store = mk_service(env, cfg, llm=llm, budget=mk_budget(tmp_path, env.clock))
    res = svc.run_tick(RUN_NOW)
    assert res.status == "skipped_no_data" and llm.submitted == []
    store.close()


def test_before_run_at_idle(env, tmp_path):
    cfg = mk_cfg(tmp_path)
    svc, store = mk_service(env, cfg)
    assert svc.run_tick(datetime(2026, 12, 9, 1, 0, tzinfo=UTC)).status == "idle"
    store.close()


# ---------------------------------------------------------------------------
# geri alma izleyicisi
# ---------------------------------------------------------------------------

def npos(i, r):
    return (i // 2, r)


def npos_kw(i):
    return {"pair": PAIRS[i % 6], "hour": 10 + 2 * (i % 2)}


def applied_env(env, tmp_path, n_new, r_new, base_r=0.3, n_p=24, *, user=False, new_days_start=70):
    """P: 24 R1 islemi surum 1 (ort ~ base_r); surum 2 etkinlesir; N: n_new islem."""
    for i in range(n_p):
        env.add(i, base_r + (0.8 if i % 2 else -0.8), pair=PAIRS[i % 6], ver=1, rr=2.5)
    env.clock.t = datetime(2026, 11, 28, 12, tzinfo=UTC)
    pid = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x", claimed_evidence={},
                                 source="t").proposal_id
    assert env.led.apply_proposal(pid, actor="user" if user else "lesson", reason="x").ok
    start = datetime(2026, 11, 29, tzinfo=UTC)
    env.clock.t = RUN_NOW
    for i, r in enumerate(r_new[:n_new]):
        env.add(*npos(i, r), ver=2, rr=2.5, base=start, **npos_kw(i))
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-10-01")
    svc, store = mk_service(env, cfg)
    store.add_monitor(LS.Monitor(2, 1, "rr_min", 1.5, 1.75, "R1", pid, "2026-11-28T12:00:00.000Z", 20, 30,
                                 origin="user" if user else "auto"))
    return svc, store, cfg


def test_monitor_m1_harm_rollback_and_blacklist(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 20, [-1.0, 0.3] * 10)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "rolled_back", res
    assert env.led.get_active_params().version_id == 1
    last = env.led.list_activations()[0]
    assert last.kind == "rollback" and last.actor == "lesson" and last.version_id == 1 and last.prev_version_id == 2
    assert len(env.led.list_versions()) == 2
    assert ("rr_min", "up") in store.blacklist()
    assert any(n.code == "rolled_back" and n.level == "warn" for n in svc._notifier.notices)
    snap = store.get_snapshot(store.get_run(RUN_DAY).id)
    assert snap is None            # B atlandi
    store.close()


def test_monitor_not_harm_pending_recheck_and_confirmed(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 20, [0.5, 0.1, 0.3, -0.2] * 5)
    res = svc.run_tick(RUN_NOW)
    mon = store.monitor_by_version(2)
    assert mon.state == "confirmed_pending_recheck", (res, mon)
    assert env.led.get_active_params().version_id == 2
    store.close()


def test_monitor_early_rollback_and_same_day_shock_guard(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 12, [-1.0, -0.8] * 6)
    assert svc.run_tick(RUN_NOW).status == "rolled_back"
    store.close()


def test_early_same_day_stops_do_not_rollback(tmp_path):
    env = Env(tmp_path)
    try:
        for i in range(24):
            env.add(i, 0.3 + (0.8 if i % 2 else -0.8), pair=PAIRS[i % 6], ver=1)
        env.clock.t = datetime(2026, 11, 28, 12, tzinfo=UTC)
        pid = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x",
                                     claimed_evidence={}, source="t").proposal_id
        assert env.led.apply_proposal(pid, actor="lesson", reason="x").ok
        start = datetime(2026, 11, 29, tzinfo=UTC)
        for i in range(7):            # ayni gun 7 stop
            env.add(0, -1.0, pair=PAIRS[i % 6], ver=2, base=start, hour=10, bar_minute=15 * i)
        env.add(1, 0.0, ver=2, base=start)
        env.add(2, 0.0, ver=2, base=start)
        env.add(2, 0.0, ver=2, base=start, hour=12, pair="ADA/USDT")
        env.clock.t = RUN_NOW
        cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-10-01")
        mon = LS.Monitor(2, 1, "rr_min", 1.5, 1.75, "R1", pid, "2026-11-28T12:00:00.000Z", 20, 30)
        v = LS.evaluate_monitor(env.led, env.twin, mon, LS.as_of_for("2026-12-09"), cfg, twin_code="twin_empty")
        assert v.stats["n_N"] == 10 and v.stats["exit_days_N"] == 3
        assert v.stats["mean"] <= -0.6 and v.action == "wait"
    finally:
        env.close()


def test_monitor_twin_benefit_conflict_blocks_rollback(env, tmp_path):
    """Zaman zarari ama ikiz `benefit` -> geri alma yok, conflict."""
    svc, store, cfg = applied_env(env, tmp_path, 20, [-1.0, 0.3] * 10)
    # ikiz: ayni sinyaller, ikiz daha kotu (r - 1.0) -> ogrenen avantajli
    N_start = datetime(2026, 11, 29, tzinfo=UTC)
    for i in range(20):
        r = [-1.0, 0.3][i % 2]
        env.add(*npos(i, r - 0.5 - 0.1 * (i % 5)), ver=1, base=N_start, led=env.twin, **npos_kw(i))
    mon = store.monitor_by_version(2)
    v = LS.evaluate_monitor(env.led, env.twin, mon, LS.as_of_for(RUN_DAY), cfg)
    assert v.stats["time_verdict"] == "harm" and v.stats["twin_verdict"] == "benefit"
    assert v.action == "confirmed_pending_recheck" and v.conflict
    store.close()


def test_monitor_expiry_rolls_back_when_no_data(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 0, [])
    # 28+ gun sonra
    env.clock.t = datetime(2026, 12, 30, 3, tzinfo=UTC)
    res = svc.run_tick()
    assert res.status == "rolled_back" and res.code == "expired_rolled_back"
    assert env.led.get_active_params().version_id == 1
    store.close()


def test_user_approved_monitor_also_rolled_back(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 20, [-1.0, 0.3] * 10, user=True)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "rolled_back"
    assert "kullanici onayli" in svc._notifier.notices[-1].body
    store.close()


def test_user_version_not_rolled_back_and_superseded(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 20, [-1.0, 0.3] * 10)
    v3 = env.led.create_user_version({**PARAMS, "rr_min": 1.75, "vol_ratio_max": 1.25}, reason="elle")
    assert env.led.activate_version(v3, actor="user", reason="elle").ok
    res = svc.run_tick(RUN_NOW)
    assert res.status != "rolled_back"
    assert store.monitor_by_version(2).state == "superseded"
    assert env.led.get_active_params().version_id == v3
    store.close()


# ---------------------------------------------------------------------------
# ikiz raporu
# ---------------------------------------------------------------------------

def test_twin_report_counts_and_verdict(env, tmp_path):
    cfg = mk_cfg(tmp_path)
    # 6 gun: ikiz alir, ogrenen rr_below_min ile atlar (only_twin)
    t_r = [-1.0, -1.0, 0.5, -0.6, -1.0, 1.1]
    for i, r in enumerate(t_r):
        bar = D0 + timedelta(days=i, hours=10)
        did = env.led.record_decision(mk_dec(bar, PAIRS[i % 6], entered=False, skip="rr_below_min"))
        env.add(i, r, pair=PAIRS[i % 6], led=env.twin)
    # 14 ortak islem
    for i in range(14):
        env.add_pair(10 + i, 0.2, pair=PAIRS[i % 6])
    rep = LS.build_twin_report(env.led, env.twin, (D0, LS.as_of_for(RUN_DAY)), cfg)
    assert rep.available and rep.n_both == 14 and rep.n_only_twin == 6 and rep.n_only_learner == 0
    assert rep.trade_count_diff == 14 - 20 and rep.only_diff == -6
    assert rep.mean_r_only_twin == pytest.approx(sum(t_r) / 6)
    assert rep.verdict in ("insufficient", "neutral", "harm", "benefit")
    # ilk 6 key'in adv sonucu (14.11): adv_mean ortalamasi, tek basina n_keys=6 < 10 -> insufficient
    only = LS.build_twin_report(env.led, env.twin, (D0, D0 + timedelta(days=8)), cfg)
    assert only.n_keys == 6 and only.verdict == "insufficient"
    assert only.adv_mean == pytest.approx(2.0 / 6) and only.z_twin == pytest.approx(0.8958, abs=1e-3)


def test_twin_codes(env, tmp_path):
    cfg = mk_cfg(tmp_path)
    w = (D0, LS.as_of_for(RUN_DAY))
    assert LS.build_twin_report(env.led, None, w, dataclasses.replace(cfg, twin_enabled=False)).code == "twin_disabled"
    assert LS.build_twin_report(env.led, None, w, cfg).code == "twin_missing"
    assert LS.build_twin_report(env.led, env.twin, w, cfg).code == "twin_empty"
    other = L.open_ledger(tmp_path / "t2.sqlite", "twin", clock=env.clock)
    other.init_params({**PARAMS, "rr_min": 1.75}, reason="x")
    assert LS.build_twin_report(env.led, other, w, cfg).code == "twin_params_mismatch"
    other.close()
    assert LS.open_twin(cfg, tmp_path / "nonexistent.sqlite") == (None, "twin_missing")
    ro, code = LS.open_twin(cfg)
    assert code is None
    with pytest.raises(L.LedgerStateError):
        ro.get_active_params() and ro.init_params(PARAMS, reason="x")
    ro.close()


def test_twin_excludes_veto_and_gate_days(env, tmp_path):
    cfg = mk_cfg(tmp_path)
    bar = D0 + timedelta(days=1, hours=10)
    env.add(1, 0.5, pair="ETH/USDT", led=env.led)
    env.twin.record_decision(mk_dec(bar, "ETH/USDT", entered=False, skip="veto_blocked"))
    env.add(5, 0.5, pair="SOL/USDT", led=env.led)
    env.twin.record_decision(mk_dec(D0 + timedelta(days=5, hours=10), "SOL/USDT", entered=False,
                                    skip="entry_gate_closed"))
    env.add_pair(8, 0.1, pair="BNB/USDT")
    rep = LS.build_twin_report(env.led, env.twin, (D0, LS.as_of_for(RUN_DAY)), cfg)
    assert rep.excluded_nonparam == 1 and rep.excluded_gate_days == 1 and rep.n_both == 1 and rep.n_only_learner == 0


def test_twin_observed_loosening_and_ratchet(env, tmp_path):
    """Ogrenen rr_min=1.75 (siki), ikiz 1.5: ikizin kacirilan islemleri kanittir."""
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-10-01")
    for i in range(10):
        env.add_pair(i, 0.0, pair=PAIRS[i % 6], rr=2.5)
    env.clock.t = datetime(2026, 11, 1, 12, tzinfo=UTC)
    pid = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x", claimed_evidence={},
                                 source="t").proposal_id
    # >= 20 kanit icin ek islem
    for i in range(12):
        env.add_pair(10 + i, 0.0, pair=PAIRS[i % 6], rr=2.5)
    assert env.led.apply_proposal(pid, actor="user", reason="x").ok
    env.clock.t = datetime(2026, 12, 1, tzinfo=UTC)
    start = datetime(2026, 11, 2, tzinfo=UTC)
    # only_twin (A): ogrenen rr_below_min, ikiz girdi, rr 1.6 < 1.75, iyi sonuc
    for i in range(10):
        env.led.record_decision(mk_dec(start + timedelta(days=i, hours=10), PAIRS[i % 6], ver=2, entered=False,
                                       skip="rr_below_min", rr=1.6))
        env.add(i, 1.0 + (i % 2) * 0.5, pair=PAIRS[i % 6], led=env.twin, base=start, rr=1.6)
    # both (B): ortalama dusuk
    for i in range(10):
        env.add_pair(i, -0.4 + (i % 2) * 0.2, pair=PAIRS[(i + 3) % 6], base=start, hour=12, ver=2, rr=2.5) \
            if False else None
        t = start + timedelta(days=i, hours=12)
        r = -0.4 + (i % 2) * 0.2
        for led, ver in ((env.led, 2), (env.twin, 1)):
            env.tid += 1
            did = led.record_decision(mk_dec(t, PAIRS[(i + 3) % 6], ver=ver, rr=2.5))
            led.record_trade_entry(TradeEntry(env.tid, did, t + timedelta(seconds=3), 2000.0, 0.3, 3, 0.0))
            led.record_trade_exit(TradeExit(env.tid, t + timedelta(hours=4), 2000.0 + r * R_PER, "time_stop", None,
                                            0.0, 0.0))
    env.clock.t = RUN_NOW
    snap = LS.build_snapshot(env.led, cfg, "2026-12-01", twin_ro=env.twin)
    e = snap.entry("rr_min:down")
    assert e is not None and e.evidence_class == "twin_observed" and e.to_value == 1.5
    assert e.extra["n_only_twin"] == 10 and e.extra["n_twin"] == 20 and e.n_scope == 20
    assert e.checkpoint_c is None and not e.eligible and "not_at_checkpoint" in e.fail_reasons   # 20 < 30
    # rr_min:up (ikizden uzaklasir): 1 adim -> 2 adim, <= max_steps_from_twin(2): ratchet yok
    up = snap.entry("rr_min:up")
    assert up.extra["steps_from_twin_now"] == 1 and up.extra["steps_from_twin_after"] == 2
    d = LS.ProposalDraft("change", "rr_min:up", "rr_min", 2.0, "x", (), "low")
    assert LS.steps_from_twin(2.0, 1.5, "rr_min") == 2
    strict = dataclasses.replace(cfg, max_steps_from_twin=1)
    assert "ratchet_guard" in LS.classify_route(snap, d, strict).reasons


# ---------------------------------------------------------------------------
# magaza, ledger_only, capa
# ---------------------------------------------------------------------------

def test_store_append_only_and_perms(tmp_path):
    st = LS.LessonStore(tmp_path / "s.sqlite")
    st.set_state("blind_since", "2026-12-01")
    c = sqlite3.connect(tmp_path / "s.sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("UPDATE lesson_state SET value='x'")
    with pytest.raises(sqlite3.DatabaseError):
        c.execute("DELETE FROM lesson_state")
    c.close()
    assert oct(os.stat(tmp_path / "s.sqlite").st_mode & 0o777) == "0o600"
    st.close()
    c = sqlite3.connect(tmp_path / "s.sqlite")
    c.execute("PRAGMA user_version=9")
    c.close()
    with pytest.raises(LS.LessonStoreError):
        LS.LessonStore(tmp_path / "s.sqlite")
    # eksik tetikleyici
    p = tmp_path / "s2.sqlite"
    LS.LessonStore(p).close()
    c = sqlite3.connect(p)
    c.execute("DROP TRIGGER trg_lesson_state_no_update")
    c.close()
    with pytest.raises(LS.LessonStoreError):
        LS.LessonStore(p)


def test_ledger_only_mode_rollback_and_fallback(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 20, [-1.0, 0.3] * 10)
    store.close()
    bad_store = tmp_path / "dir_as_store"
    bad_store.mkdir()
    cfg2 = dataclasses.replace(cfg, store_path=str(bad_store))
    notifier = LS.NullNotifier()
    svc2 = LS.LessonService(cfg2, ledger=env.led, twin=env.twin, clock=env.clock, notifier=notifier,
                            lock_path=None)
    res = svc2.run_tick(RUN_NOW)
    assert res.status == "rolled_back", res
    assert env.led.get_active_params().version_id == 1
    fb = LS.FallbackLog(bad_store)
    lines = fb.read()
    assert any(o.get("type") == "monitor_event" and o["event"] == "rolled_back" for o in lines)
    assert any(o.get("type") == "blind_since" for o in lines)
    last = env.led.list_activations()[0]
    assert last.actor == "lesson" and last.reason.startswith("ledger_only")


def test_blind_days_returns_to_user_approved(env, tmp_path):
    # id1 initial/system v1; id2 apply/user v2; id3 apply/lesson v3 (otomatik)
    for i in range(24):
        env.add(i, 0.1, pair=PAIRS[i % 6])
    env.clock.t = datetime(2026, 11, 20, 12, tzinfo=UTC)
    p2 = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x", claimed_evidence={},
                                source="t").proposal_id
    assert env.led.apply_proposal(p2, actor="user", reason="x").ok
    for i in range(24):
        env.add(i, 0.1, pair=PAIRS[i % 6], ver=2, base=datetime(2026, 11, 21, tzinfo=UTC), rr=2.5)
    env.clock.t = datetime(2026, 12, 3, 12, tzinfo=UTC)
    p3 = env.led.propose_change(base_version_id=2, changes={"vol_ratio_max": 1.3}, rationale="x", claimed_evidence={},
                                source="t").proposal_id
    assert env.led.apply_proposal(p3, actor="lesson", reason="x").ok
    assert LS.rollback_target_user_approved(env.led) == 2
    cfg = mk_cfg(tmp_path, store_path=str(tmp_path / "dir_store"), calibration=good_cal())
    (tmp_path / "dir_store").mkdir()
    svc = LS.LessonService(cfg, ledger=env.led, twin=env.twin, clock=env.clock, notifier=LS.NullNotifier(),
                           lock_path=None)
    fb = LS.FallbackLog(tmp_path / "dir_store")
    for d in ("2026-12-07", "2026-12-08"):
        fb.append({"type": "blind_since", "run_day": d, "fingerprint": "b" + d}) if d == "2026-12-07" else None
    r = svc.run_tick(RUN_NOW)                       # gun 3 (12-07, 12-08, 12-09)
    assert r.status == "rolled_back" and r.code == "blind_days", r
    assert env.led.get_active_params().version_id == 2
    # capa zaten etkin: yan etkisiz
    res = svc.rollback_to_user_approved("elle", "cli")
    assert not res.ok and res.code == "already_active"


def test_rollback_script_only_ledger(env, tmp_path, capsys):
    for i in range(22):
        env.add(i, 0.1, pair=PAIRS[i % 6])
    env.clock.t = datetime(2026, 11, 20, 12, tzinfo=UTC)
    p2 = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x", claimed_evidence={},
                                source="t").proposal_id
    assert env.led.apply_proposal(p2, actor="lesson", reason="x").ok
    cfgp = tmp_path / "l.json"
    cfgp.write_text(json.dumps({"ledger_path": str(tmp_path / "learner.sqlite"),
                                "store_path": str(tmp_path / "nostore.sqlite"),
                                "twin_ledger_path": str(tmp_path / "twin.sqlite")}))
    sys.path.insert(0, str(ROOT / "scripts"))
    import lesson_run
    env.led.close()
    rc = lesson_run.main(["--rollback-to-user-approved", "--reason", "test", "--config", str(cfgp)], env={})
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] and out["version_id"] == 1
    rc = lesson_run.main(["--rollback-to-user-approved", "--reason", "test", "--config", str(cfgp)], env={})
    assert rc == 0       # already_active
    assert lesson_run.main(["--rollback-to-user-approved", "--config", str(cfgp)], env={}) == 1
    assert not (tmp_path / "nostore.sqlite").exists()
    env.led = L.open_ledger(tmp_path / "learner.sqlite", "learner", clock=env.clock)


def test_runner_dry_run_and_once_rule_proxy(env, tmp_path, capsys):
    r1_scenario(env)
    cfgp = tmp_path / "l.json"
    cfgp.write_text(json.dumps({"ledger_path": str(tmp_path / "learner.sqlite"),
                                "store_path": str(tmp_path / "lesson.sqlite"),
                                "twin_ledger_path": str(tmp_path / "twin.sqlite"), "mode": "rule_proxy",
                                "paper_start_day": "2026-11-30"}))
    sys.path.insert(0, str(ROOT / "scripts"))
    import lesson_run
    rc = lesson_run.main(["--once", "--dry-run", "--day", RUN_DAY, "--config", str(cfgp)], env={},
                         now_fn=lambda: RUN_NOW)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["menu"] and "prompt_user" in out and not (tmp_path / "lesson.sqlite").exists()
    rc = lesson_run.main(["--once", "--day", RUN_DAY, "--config", str(cfgp)], env={},
                         notifier=LS.NullNotifier(), now_fn=lambda: RUN_NOW)
    assert rc == 0
    last = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert last["status"] == "needs_user" and last["code"] == "shadow_period"
    assert lesson_run.main(["--once", "--config", str(tmp_path / "missing.json")], env={}) == 1


def test_lock_excludes_second_process(env, tmp_path):
    cfg = mk_cfg(tmp_path)
    lock = LS.FileLock(tmp_path / "x.lock")
    assert lock.acquire()
    svc = LS.LessonService(cfg, ledger=env.led, twin=env.twin, clock=env.clock, lock_path=tmp_path / "x.lock",
                           store=LS.LessonStore(env.store_path))
    assert svc.run_tick(RUN_NOW).status == "locked"
    lock.release()


def test_capability_fallbacks(env, tmp_path):
    """13.5: havuz yok, require_user yok."""
    class Proxy:
        def __init__(self, inner):
            self._i = inner

        def __getattr__(self, name):
            if name in ("pool_version_ids", "trades_for_versions"):
                raise AttributeError(name)
            return getattr(self._i, name)

        def propose_change(self, *, base_version_id, changes, rationale, claimed_evidence, source):
            return self._i.propose_change(base_version_id=base_version_id, changes=changes, rationale=rationale,
                                          claimed_evidence=claimed_evidence, source=source)

        def aggregate_trades(self, group_by, *, version_id=None, exact_version=True, since_ts=None, until_ts=None):
            return self._i.aggregate_trades(group_by, version_id=version_id, exact_version=exact_version,
                                            since_ts=since_ts, until_ts=until_ts)

    r1_scenario(env)
    px = Proxy(env.led)
    caps = LS.detect_caps(px)
    assert not caps.pool and not caps.tfv and not caps.require_user and caps.excursion
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-11-30")
    snap = LS.build_snapshot(px, cfg, RUN_DAY, twin_ro=env.twin)
    assert "pooling_off" in snap.capabilities and snap.entry("rr_min:up").eligible
    # golge donem + require_user yok: oneri `proposed` kalir ama apply cagrilmaz
    store = LS.LessonStore(env.store_path, clock=env.clock)
    svc = LS.LessonService(cfg, ledger=px, store=store, twin=env.twin, clock=env.clock, notifier=LS.NullNotifier(),
                           lock_path=None)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "needs_user" and res.code == "shadow_period"
    assert env.led.list_proposals()[0].status == "proposed"
    assert env.led.get_active_params().version_id == 1
    store.close()


def test_off_menu_and_twin_ledger_never_written(env, tmp_path):
    r1_scenario(env)
    before = env.twin.list_versions(), len(env.twin.list_decisions())
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-11-30")
    svc, store = mk_service(env, cfg)
    svc.run_tick(RUN_NOW)
    assert (env.twin.list_versions(), len(env.twin.list_decisions())) == before
    store.close()
    with pytest.raises(LS.LessonConfigError):
        LS.LessonService(dataclasses.replace(cfg, bot="learner") if False else LS.LessonConfig(bot="twin"))


def test_no_key_in_stored_text(env, tmp_path):
    cfg, snap, llm, bud = llm_env(env, tmp_path)
    obj = json.loads(response_for(snap))
    obj["rationale"] = "key sk-ant-abc123_XYZ leaked"
    llm.responder = lambda b: (json.dumps(obj), "end_turn", {"input_tokens": 10, "output_tokens": 5})
    svc, store = mk_service(env, cfg, llm=llm, budget=bud)
    svc.run_tick(RUN_NOW)
    c = sqlite3.connect(env.store_path)
    blob = " ".join(str(v) for t in ("lesson_llm_results", "lesson_run_events", "lesson_decisions")
                    for row in c.execute(f"SELECT * FROM {t}") for v in row)
    c.close()
    assert "sk-ant-abc" not in blob
    assert "sk-ant-abc" not in env.led.list_proposals()[0].rationale
    store.close()


def test_daily_summary_shape(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-11-30")
    svc, store = mk_service(env, cfg)
    svc.run_tick(RUN_NOW)
    s = svc.daily_summary(RUN_DAY)
    for k in ("run_day", "status", "mode", "n_scope", "menu_eligible", "decision", "class", "applied_version_id",
              "proposal_id", "monitor", "llm_cost_usd", "skipped_reason", "shadow", "shadow_period", "checkpoints",
              "twin"):
        assert k in s
    assert s["status"] == "needs_user" and s["decision"] == "rr_min:up" and s["class"] == "ask_user"
    assert s["shadow_period"] == {"active": True, "ends_on": "2026-12-28", "days_left": 19}
    assert s["twin"]["report_visible"] is False and s["twin"]["available"] is True
    assert s["twin"]["day"]["n_learner_entered"] == 0 and s["n_scope"]["R1"] == 34
    store.close()


# ---------------------------------------------------------------------------
# kalibrasyon
# ---------------------------------------------------------------------------

def test_calibration_insufficient_and_deterministic(tmp_path):
    cfg = LS.LessonConfig(**LEGACY_CFG)
    e = Env(tmp_path)
    try:
        for i in range(30):
            e.add(i, 0.1)
        cal = LS.calibrate(e.led, None, cfg, seed=1, B=10, today="2026-12-09")
        assert not cal.ok and cal.code == "insufficient_backtest" and cal.rule_version == LS.RULES_VERSION
    finally:
        e.close()
    # yeterli sentetik backtest (>=400 islem, >=12 ay)
    e2 = Env(tmp_path / "c") if (tmp_path / "c").mkdir() is None else None
    try:
        import random
        rnd = random.Random(7)
        base = datetime(2025, 9, 1, tzinfo=UTC)
        for i in range(420):
            setup = "R1" if i % 3 else "T1"
            e2.add(i, rnd.gauss(0.05, 1.0), pair=PAIRS[i % 6], setup=setup, base=base,
                   rr=rnd.uniform(1.4, 3.0), atr_ratio=rnd.uniform(0.8, 1.7), stop=rnd.uniform(1.0, 3.0))
        c1 = LS.calibrate(e2.led, None, cfg, seed=3, B=25, today="2026-12-09")
        c2 = LS.calibrate(e2.led, None, cfg, seed=3, B=25, today="2026-12-09")
        assert c1.to_dict() == c2.to_dict()
        assert not c1.ok and c1.code in ("criteria_not_met", "insufficient_twin_backtest")    # ikiz yedek yok
        assert c1.FPR_aile is not None and 0 <= c1.FPR_aile <= 1 and c1.n_trades == 420
        d = c1.to_dict()
        assert set(LS._CAL_NUM) <= set(d) and d["rule_version"] == "RULES_V1"
        # ok=false iken yapilandirma esikleri serbest (kalibrasyon ok degil) ve otomatik kapali
        c = LS.LessonConfig(calibration=d)
        assert LS.calibration_status(c, "2026-12-10")[0] is False
    finally:
        e2.close()


def test_calibrate_script_writes_config(tmp_path):
    e = Env(tmp_path)
    try:
        for i in range(30):
            e.add(i, 0.1)
    finally:
        e.close()
    sys.path.insert(0, str(ROOT / "scripts"))
    import lesson_calibrate
    out = tmp_path / "out.json"
    rc = lesson_calibrate.main(["--backtest-ledger", str(tmp_path / "learner.sqlite"), "--out", str(out),
                                "--seed", "2", "--B", "5"])
    assert rc == 3
    data = json.loads(out.read_text())
    assert data["calibration"]["ok"] is False and data["calibration"]["code"] == "insufficient_backtest"
    assert lesson_calibrate.main(["--backtest-ledger", str(tmp_path / "none.sqlite"), "--out", str(out)]) == 1


# ---------------------------------------------------------------------------
# dagitim dosyalari ve notifier
# ---------------------------------------------------------------------------

def test_deploy_files():
    svc = (ROOT / "deploy" / "trader-lesson.service").read_text()
    for need in ("Type=oneshot", "User=trader", "EnvironmentFile=/etc/trader-lesson.env", "lesson_run.py --once",
                 "TimeoutStartSec=300", "MemoryMax=256M", "CPUQuota=30%", "Nice=10", "ProtectSystem=strict",
                 "NoNewPrivileges=true", "PrivateTmp=true", "OnFailure=trader-health-fail@%n.service",
                 "/opt/trader/user_data"):
        assert need in svc
    assert "var/twin" not in svc                                                  # DD-12: ikiz kaldirildi
    tm = (ROOT / "deploy" / "trader-lesson.timer").read_text()
    assert "OnCalendar=*-*-* *:17:00" in tm and "Persistent=true" in tm and "RandomizedDelaySec=60" in tm
    env = (ROOT / "deploy" / "trader-lesson.env.example").read_text()
    assert "ANTHROPIC_API_KEY_LESSON=" in env and not re.search(r"sk-ant-[A-Za-z0-9]", env)


def test_notifier_failure_does_not_break_pipeline(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-11-30")

    class Boom:
        def request_approval(self, req):
            raise RuntimeError("telegram yok")

        def notify(self, n):
            raise RuntimeError("telegram yok")

    svc, store = mk_service(env, cfg, notifier=Boom())
    res = svc.run_tick(RUN_NOW)
    assert res.status == "needs_user"
    rid = f"lr-{RUN_DAY}-1"
    assert [e["event"] for e in store.request_events(rid)] == ["open", "delivery_failed"]
    svc._notifier = LS.NullNotifier()
    env.clock.t = RUN_NOW + timedelta(hours=1)
    svc.run_tick()
    assert [e["event"] for e in store.request_events(rid)][-1] == "delivered"
    store.close()


# ---------------------------------------------------------------------------
# kural duzeyi (14.4, 14.5, 14.14) ve kontrol noktasi mantigi
# ---------------------------------------------------------------------------

def trow(i, r, *, setup="R1", rr=2.5, atr=1.1, stop=2.0, reason="time_stop", mfe=None, mae=None, gross=None,
         fee=0.0, day=None):
    ts = f"2026-10-{1 + i % 28:02d}T10:00:00.000Z"
    return LS.TradeRow(
        trade_id=i, decision_id=i, pair=PAIRS[i % 6], side="long", setup=setup, regime="range", atr_ratio=atr,
        entry_ts=ts, exit_ts=ts, day=day or f"d{i:03d}", r=r, exit_reason=reason, planned_risk=1.0, fee_entry=fee,
        fee_exit=0.0, funding=0.0, gross_pnl=r if gross is None else gross, mfe_r=mfe, mae_r=mae, bars_held=4,
        rr=rr, stop_dist_atr=stop, version_id=1)


def test_rule_vol_ratio_up_extrapolated_14_4():
    a = synth(9, 0.60, 0.80, "a")
    b = synth(27, -0.05, 1.00, "b")
    rows = [trow(i, v, atr=1.4) for i, (v, _) in enumerate(a)] + [trow(100 + i, v, atr=1.1) for i, (v, _) in enumerate(b)]
    rule = LS.RULES_BY_ID["vol_ratio_max:up"]
    res = LS.eval_rule(rule, rows, 1.5, 1.7, LS.LessonConfig(**LEGACY_CFG))
    assert res["passed"], res
    assert res["n_a"] == 9 and res["n_b"] == 27 and res["gap"] == pytest.approx(0.65, abs=1e-3)
    assert res["z"] == pytest.approx(2.25, abs=1e-3)
    assert rule.evidence_class == "extrapolated"


def test_rule_range_target_frac_down_14_5():
    rows = []
    for i in range(34):
        reason = "time_stop" if i < 14 else ("target" if i < 22 else "stop")
        r = -0.1 if reason == "time_stop" else (1.0 if reason == "target" else 0.2)
        rows.append(trow(i, r, reason=reason))
    res = LS.eval_rule(LS.RULES_BY_ID["range_target_frac:down"], rows, 0.75, 0.625, LS.LessonConfig(**LEGACY_CFG))
    assert res["passed"] and res["extra"]["share_time_stop"] == pytest.approx(0.4118, abs=1e-4)
    assert LS.rule_to_value(LS.RULES_BY_ID["range_target_frac:down"], 0.75, (0.6, 0.9)) == 0.625
    up = LS.eval_rule(LS.RULES_BY_ID["range_target_frac:up"], rows, 0.75, 0.875, LS.LessonConfig(**LEGACY_CFG))
    assert not up["passed"] and "share_low" in up["fails"]


def mfe_rows(runner_gb):
    mfes = [1.2, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.4]
    rows = []
    for i, m in enumerate(mfes):
        gb = runner_gb if m >= 2.0 else 1.0 + 0.02 * (i % 3)
        rows.append(trow(i, m - gb, setup="T1", reason="trail_stop", mfe=m, mae=0.3, gross=m - gb))
    for i in range(12, 36):
        rows.append(trow(i, 0.1, setup="T1", reason="time_stop", mfe=0.5, mae=0.5, gross=0.1))
    return rows


def test_rule_trail_atr_down_mfe_and_runner_guard():
    rule = LS.RULES_BY_ID["trail_atr:down"]
    res = LS.eval_rule(rule, mfe_rows(1.4), 3.0, 2.5, LS.LessonConfig(**LEGACY_CFG))
    assert res["passed"], res
    assert res["extra"]["giveback_mean"] >= 0.75 and res["extra"]["capture_ratio"] <= 0.45
    assert res["extra"]["n_runners"] == 5
    guard = LS.eval_rule(rule, mfe_rows(0.3), 3.0, 2.5, LS.LessonConfig(**LEGACY_CFG))
    assert not guard["passed"] and "runner_guard" in guard["fails"]
    # NULL mfe dislanir
    nulls = [dataclasses.replace(r, mfe_r=None, mae_r=None) for r in mfe_rows(1.4)]
    res2 = LS.eval_rule(rule, nulls, 3.0, 2.5, LS.LessonConfig(**LEGACY_CFG))
    assert not res2["passed"] and "n_a_low" in res2["fails"] and res2["extra"]["excluded_missing_excursion"] == 36


def test_rule_stop_buffer_third_and_cost_gap():
    rows = []
    for i in range(40):
        low = i < 14
        rows.append(trow(i, -0.4 + 0.1 * (i % 3) if low else 0.4 + 0.1 * (i % 3), stop=1.0 + i * 0.01 if low else 2.0 + i * 0.01,
                         fee=0.2 if low else 0.05, gross=(-0.4 if low else 0.4)))
    rule = LS.RULES_BY_ID["stop_buffer_atr:up"]
    res = LS.eval_rule(rule, rows, 0.3, 0.4, LS.LessonConfig(**LEGACY_CFG))
    assert res["n_a"] == 14 and res["passed"], res
    assert res["extra"]["cost_gap"] >= 0.10
    nocost = [dataclasses.replace(r, fee_entry=0.1) for r in rows]
    assert "cost_gap_low" in LS.eval_rule(rule, nocost, 0.3, 0.4, LS.LessonConfig(**LEGACY_CFG))["fails"]


def test_checkpoint_frozen_sample_and_largest_passing():
    cfg = LS.LessonConfig(**LEGACY_CFG)
    rule = LS.RULES_BY_ID["rr_min:up"]
    rows = []
    for i in range(46):
        bad = i % 3 == 0
        rows.append(trow(i, (-0.5 if bad else 0.5) + 0.05 * (i % 4), rr=1.6 if bad else 2.5))
    mk = lambda n, known=None: LS.CheckpointInput("s", "rr_min", ((rule, 1.5, 1.75),), RUN_DAY, tuple(rows[:n]), False, {}, known or {})  # noqa: E731
    r34 = LS.evaluate_checkpoints(mk(34), cfg)
    r40 = LS.evaluate_checkpoints(mk(40), cfg)
    assert [c.c for c in r34] == [30] and r34[0].sample_hash == r40[0].sample_hash
    assert r34[0].directions == r40[0].directions
    both = LS.evaluate_checkpoints(mk(46), cfg)
    assert [c.c for c in both] == [30, 45] and both[0].sample_hash != both[1].sample_hash
    assert all(c.passed for c in both), [c.directions for c in both]
    sel, d, state = LS.select_checkpoint({c.c: c for c in both}, "rr_min:up", LS.as_of_for(RUN_DAY))
    assert state == "passed" and sel.c == 45 and d["passed"]
    # bilinen sonuc yeniden test edilmez
    known = {c.c: c for c in both}
    assert LS.evaluate_checkpoints(mk(46, known), cfg) == []


def test_blacklist_makes_candidate_ineligible(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path)
    bl = {("rr_min", "up"): "2026-12-20T00:00:00.000Z"}
    snap = run_snapshot(env, cfg, blacklist=bl)
    e = snap.entry("rr_min:up")
    assert not e.eligible and "blacklisted" in e.fail_reasons and not e.checks["not_blacklisted"]
    later = LS.build_snapshot(env.led, cfg, "2026-12-21", twin_ro=env.twin, blacklist=bl)
    assert "blacklisted" not in later.entry("rr_min:up").fail_reasons


def test_monitor_m2_confirmed_and_rolled_back(tmp_path):
    for harmful in (False, True):
        sub = tmp_path / f"m{int(harmful)}"
        sub.mkdir()
        env = Env(sub)
        try:
            r_new = ([-1.0, 0.3] if harmful else [0.5, 0.1, 0.3, -0.2]) * 20
            for i in range(24):
                env.add(i, 0.3 + (0.8 if i % 2 else -0.8), pair=PAIRS[i % 6], ver=1, rr=2.5)
            env.clock.t = datetime(2026, 11, 28, 12, tzinfo=UTC)
            pid = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x",
                                         claimed_evidence={}, source="t").proposal_id
            assert env.led.apply_proposal(pid, actor="lesson", reason="x").ok
            for i in range(30):
                env.add(*npos(i, r_new[i]), ver=2, rr=2.5, base=datetime(2026, 11, 29, tzinfo=UTC), **npos_kw(i))
            cfg = mk_cfg(sub, calibration=good_cal())
            mon = LS.Monitor(2, 1, "rr_min", 1.5, 1.75, "R1", pid, "2026-11-28T12:00:00.000Z", 20, 30,
                             state="confirmed_pending_recheck")
            v = LS.evaluate_monitor(env.led, None, mon, LS.as_of_for("2026-12-20"), cfg, twin_code="twin_missing")
            assert v.stage == "M2" and v.stats["n_N"] == 30
            assert v.action == ("rolled_back" if harmful else "confirmed"), v
            # M1 (durum open) ilk K ornek
            v1 = LS.evaluate_monitor(env.led, None, dataclasses.replace(mon, state="open"), LS.as_of_for("2026-12-20"),
                                     cfg, twin_code="twin_missing")
            assert v1.stage == "M1" and v1.stats["n_N"] == 20
            # yeniden denetim suresi: veri yetmezse 42 gun sonra confirmed
            few = LS.evaluate_monitor(env.led, None, mon, LS.as_of_for("2026-12-09"), cfg, twin_code="twin_missing")
            assert few.action in ("wait", "rolled_back", "early_rolled_back")
        finally:
            env.close()


def test_pending_apply_retry_and_ttl(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, calibration=good_cal(), paper_start_day="2026-10-01")
    svc, store = mk_service(env, cfg)
    pid = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="proxy", claimed_evidence={},
                                 source="rule-proxy", require_user=False).proposal_id
    store.set_shadow_once("2026-10-01", "2026-10-29")
    run0 = store.create_run(cfg, "2026-12-08")
    store.add_event(run0.id, "no_change", "weekly_limit")
    store.add_decision(run0.id, "primary", "rule-proxy", "rr_min:up", "rr_min", 1.75, "weekly_limit", "auto", pid,
                       "apply_pending")
    res = svc.run_tick(RUN_NOW)
    assert res.status == "applied" and res.code == "retry_apply"
    assert env.led.get_active_params().params["rr_min"] == 1.75
    store.close()
    # TTL: 4 gun sonra reddedilir
    sub = tmp_path / "ttl"
    sub.mkdir()
    e2 = Env(sub)
    try:
        r1_scenario(e2)
        cfg2 = mk_cfg(sub, calibration=good_cal(), paper_start_day="2026-10-01")
        svc2, st2 = mk_service(e2, cfg2)
        pid2 = e2.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="proxy",
                                     claimed_evidence={}, source="rule-proxy").proposal_id
        r0 = st2.create_run(cfg2, "2026-12-01")
        st2.add_event(r0.id, "no_change", "weekly_limit")
        st2.add_decision(r0.id, "primary", "rule-proxy", "rr_min:up", "rr_min", 1.75, "weekly_limit", "auto", pid2,
                         "apply_pending")
        e2.clock.t = RUN_NOW + timedelta(days=4)
        svc2.run_tick()
        assert e2.led.get_proposal(pid2).status == "rejected"
        st2.close()
    finally:
        e2.close()


def test_prompt_lists_facts_and_menu(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path)
    snap = run_snapshot(env, cfg)
    pb = LS.render_prompt(snap, cfg)
    assert re.search(r"menu\.rr_min:up\.z = 6\.\d+", pb.user) and "rr_min:up: param=rr_min" in pb.user
    assert pb.params["model"] == "claude-sonnet-5-5" and "temperature" not in pb.params and "tools" not in pb.params
    assert pb.params["max_tokens"] == 1500 and pb.params["messages"][0]["role"] == "user"


def test_calibration_with_twin_pair(tmp_path):
    import random
    e = Env(tmp_path)
    try:
        rnd = random.Random(11)
        base = datetime(2025, 9, 1, tzinfo=UTC)
        for i in range(420):
            setup = "R1" if i % 3 else "T1"
            e.add(i, rnd.gauss(0.05, 1.0), pair=PAIRS[i % 6], setup=setup, base=base,
                   rr=rnd.uniform(1.4, 3.0), atr_ratio=rnd.uniform(0.8, 1.7), stop=rnd.uniform(1.0, 3.0))
        # ikiz: ogrenen rr_below_min ile atlar, ikiz girer (only_twin)
        for i in range(60):
            bar = base + timedelta(days=i * 6, hours=12)
            e.led.record_decision(mk_dec(bar, PAIRS[(i + 1) % 6], entered=False, skip="rr_below_min", rr=1.3))
            e.add(i * 6, rnd.gauss(0.0, 1.0), pair=PAIRS[(i + 1) % 6], led=e.twin, base=base, hour=12, rr=1.3)
        cfg = LS.LessonConfig(**LEGACY_CFG)
        c = LS.calibrate(e.led, e.twin, cfg, seed=5, B=20, today="2026-12-09")
        assert c.twin_fpr is not None and c.twin_guc is not None and c.details["twin_pool"] == 60
        assert 0.0 <= c.twin_fpr <= 1.0 and 0.0 <= c.geri_alma_tespit <= 1.0 and c.sok_erken == 0.0
        d = c.to_dict()
        assert d["seed"] == 5 and d["B"] == 20 and d["rule_version"] == "RULES_V1"
        assert LS.calibrate(e.led, e.twin, cfg, seed=5, B=20, today="2026-12-09").to_dict() == d
        assert LS.calibrate(e.led, e.twin, cfg, seed=6, B=20, today="2026-12-09").to_dict() != d
    finally:
        e.close()


# ---------------------------------------------------------------------------
# Revizyon 3 (mentor kod incelemesi)
# ---------------------------------------------------------------------------

def test_r3_log_notifier_never_counts_as_delivered(env, tmp_path):
    n = LS.LogNotifier()
    notice = LS.LessonNotice("info", "x", "t", "b", "fp", RUN_NOW)
    assert n.notify(notice) is False
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, paper_start_day="2026-10-01")
    svc, store = mk_service(env, cfg, notifier=LS.LogNotifier())
    res = svc.run_tick(RUN_NOW)
    assert res.status == "needs_user"
    rid = store.open_requests()[0]["request_id"]
    assert [e["event"] for e in store.request_events(rid)].count("delivery_failed") >= 1
    assert not any(e["event"] == "delivered" for e in store.request_events(rid))
    store.close()


def _runner_cfg(env, tmp_path):
    r1_scenario(env)
    cfgp = tmp_path / "l.json"
    cfgp.write_text(json.dumps({"ledger_path": str(tmp_path / "learner.sqlite"),
                                "store_path": str(tmp_path / "lesson.sqlite"),
                                "twin_ledger_path": str(tmp_path / "twin.sqlite"), "mode": "rule_proxy",
                                "paper_start_day": "2026-11-30"}))
    sys.path.insert(0, str(ROOT / "scripts"))
    import lesson_run
    return lesson_run, cfgp


def test_r3_runner_requires_notifier_and_rejects_future_day(env, tmp_path, capsys):
    lesson_run, cfgp = _runner_cfg(env, tmp_path)
    base = ["--once", "--day", RUN_DAY, "--config", str(cfgp)]
    rc = lesson_run.main(base, env={}, now_fn=lambda: RUN_NOW)
    assert rc == 1 and "bildirimci" in capsys.readouterr().err      # yapilandirilmamis => basarisiz cikis
    assert not (tmp_path / "lesson.sqlite").exists()
    assert lesson_run.main(["--once", "--day", "2027-01-01", "--config", str(cfgp)], env={},
                           notifier=LS.NullNotifier(), now_fn=lambda: RUN_NOW) == 1
    rc = lesson_run.main(base + ["--allow-log-notifier"], env={}, now_fn=lambda: RUN_NOW)
    assert rc == 0
    assert (tmp_path / "lesson.sqlite").exists()
    # sistem birimi: 1 ve 3 basari sayilmaz
    unit = (ROOT / "deploy" / "trader-lesson.service").read_text()
    assert "SuccessExitStatus=2\n" in unit and "OnFailure=" in unit


def test_r3_ledger_only_monitor_runs_first_and_fallback_error_is_failsafe(env, tmp_path):
    svc, store, cfg = applied_env(env, tmp_path, 20, [-1.0, 0.3] * 10)
    store.close()
    bad_store = tmp_path / "dir_as_store"
    bad_store.mkdir()
    (tmp_path / "dir_as_store.fallback.jsonl").mkdir()       # yedek dosyasi yazilamaz (OSError)
    cfg2 = dataclasses.replace(cfg, store_path=str(bad_store))
    notifier = LS.NullNotifier()
    svc2 = LS.LessonService(cfg2, ledger=env.led, twin=env.twin, clock=env.clock, notifier=notifier, lock_path=None)
    res = svc2.run_tick(RUN_NOW)
    assert res.status == "rolled_back", res
    assert env.led.get_active_params().version_id == 1             # izleyici yine de calisti
    assert res.exit_code == LS.EXIT_DEGRADED == 3                    # gorunur ariza (SuccessExitStatus disi)
    assert res.detail.get("fallback_write_failed") is True
    assert any(n.code == "run_failed" for n in notifier.notices)


def test_r3_ledger_only_quiet_day_is_degraded_exit(env, tmp_path):
    r1_scenario(env)
    bad_store = tmp_path / "dir_as_store"
    bad_store.mkdir()
    cfg = mk_cfg(tmp_path, store_path=str(bad_store))
    svc = LS.LessonService(cfg, ledger=env.led, twin=env.twin, clock=env.clock, notifier=LS.NullNotifier(),
                           lock_path=None)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "ledger_only" and res.exit_code == 3


def test_r3_clock_jump_ahead_alerts_and_fails(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, paper_start_day="2026-10-01")
    future = RUN_NOW + timedelta(days=10)
    st0 = LS.LessonStore(env.store_path, clock=Clock(future))
    run = st0.create_run(cfg, future.date().isoformat())
    st0.add_event(run.id, "no_change", "llm_no_change", {})
    st0.close()
    notifier = LS.NullNotifier()
    svc, store = mk_service(env, cfg, notifier=notifier)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "idle" and res.code == "already_ran"
    assert res.exit_code == LS.EXIT_DEGRADED and "clock_ahead" in res.detail
    assert any(n.code == "clock_ahead" for n in notifier.notices)
    store.close()


def test_r3_twin_report_attributes_only_monitored_version(env):
    for i in range(24):
        env.add_pair(i, 0.1 + (i % 3) * 0.1, ver=1)
    env.clock.t = datetime(2026, 10, 26, 12, tzinfo=UTC)
    pid = env.led.propose_change(base_version_id=1, changes={"rr_min": 1.75}, rationale="x", claimed_evidence={},
                                 source="t").proposal_id
    assert env.led.apply_proposal(pid, actor="user", reason="x").ok
    for i in range(12):
        env.add_pair(i, 0.2, ver=2, base=datetime(2026, 10, 27, tzinfo=UTC))
    cfg = LS.LessonConfig(**LEGACY_CFG)
    window = (D0, datetime(2027, 1, 1, tzinfo=UTC))
    allv = LS.build_twin_report(env.led, env.twin, window, cfg)
    only2 = LS.build_twin_report(env.led, env.twin, window, cfg, version_id=2)
    assert allv.available and allv.n_both == 36
    assert only2.n_both == 12 and only2.n_keys == 12


def test_r3_loosening_uses_missed_trades_mean_test_not_half_r_gap():
    rule = LS.RULES_BY_ID["vol_ratio_max:up"]
    a = synth(9, 0.60, 0.80, "a")
    b = synth(27, 0.30, 1.00, "b")                       # gap = 0.30 < 0.50 (eskiden gap_low)
    rows = [trow(i, v, atr=1.4) for i, (v, _) in enumerate(a)] + [trow(100 + i, v, atr=1.1) for i, (v, _) in enumerate(b)]
    res = LS.eval_rule(rule, rows, 1.5, 1.7, LS.LessonConfig(**LEGACY_CFG))
    assert res["passed"], res
    assert res["gap"] == pytest.approx(0.30, abs=1e-3)
    neg = [trow(i, v - 0.45, atr=1.4) for i, (v, _) in enumerate(a)] + \
          [trow(100 + i, v, atr=1.1) for i, (v, _) in enumerate(b)]
    res2 = LS.eval_rule(rule, neg, 1.5, 1.7, LS.LessonConfig(**LEGACY_CFG))
    assert not res2["passed"] and "sign" in res2["fails"]


def test_r3_shadow_measured_from_first_actual_decision(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, paper_start_day="2020-01-01")
    start = LS.resolve_shadow_start(cfg, env.led, RUN_DAY)
    assert start == "2026-10-01" == LS.day_of(env.led.list_decisions(limit=1)[0].bar_close_ts)
    assert LS.resolve_shadow_start(mk_cfg(tmp_path, paper_start_day="2026-11-30"), env.led, RUN_DAY) == "2026-11-30"
    svc, store = mk_service(env, cfg)
    svc.run_tick(RUN_NOW)
    assert store.get_state("shadow_start_day") == "2026-10-01"
    store.close()


def test_r3_llm_errors_notify(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, mode="llm", calibration=good_cal(), paper_start_day="2026-10-01")
    notifier = LS.NullNotifier()
    svc, store = mk_service(env, cfg, llm=None, notifier=notifier)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "failed" and res.code == "llm_unavailable"
    assert any(n.code == "llm_error" for n in notifier.notices)
    store.close()


def test_r3_calibration_file_guard(tmp_path):
    f = tmp_path / "lesson.json"
    cfg = mk_cfg(tmp_path, calibration=good_cal(), calibration_file=str(f))
    assert LS.calibration_status(cfg, RUN_DAY) == (False, "calibration_file_missing")
    f.write_text("{}")
    assert LS.calibration_status(cfg, RUN_DAY) == (True, "ok")
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"calibration": good_cal(), "mode": "rule_proxy"}))
    assert LS.load_config(p).calibration_file == str(p.resolve())


def test_r3_reject_cooldown_blacklists_same_direction_only(env, tmp_path):
    r1_scenario(env)
    cfg = mk_cfg(tmp_path, paper_start_day="2026-10-01")
    svc, store = mk_service(env, cfg)
    assert svc.run_tick(RUN_NOW).status == "needs_user"
    rid = store.open_requests()[0]["request_id"]
    res = svc.resolve_request(rid, False, "t")
    assert res.status == "rejected"
    cd = store.rejection_cooldowns(7)
    assert list(cd) == [("rr_min", "up")]
    assert LS.parse_ts(cd[("rr_min", "up")]) > env.clock.t + timedelta(days=6)
    assert store.rejection_cooldowns(0) == {}
    assert ("rr_min", "up") in svc._blacklist_with_cooldown(store)
    store.close()


def test_r3_checkpoint_cap_and_number_stripping():
    with pytest.raises(LS.LessonConfigError):
        LS.LessonConfig(checkpoints=tuple(range(30, 40)))
    txt = LS._strip_numbers("kazanc 3.2R, %40 dusus, 12 islem, 0,5")
    assert not any(ch.isdigit() for ch in txt) and "[sayi]" in txt
