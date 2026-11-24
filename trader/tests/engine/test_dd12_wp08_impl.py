"""DD-12 WP-08 duman testleri: ders ikizsiz ve esiksiz (docs/motor/dd12-capraz-varlik-spec.md 6.1-6.3, D-T10).

Gercek defter/magaza dosyalari (tmp); LLM yok (rule_proxy). Bagimsiz spec testleri `test_dd12_wp08_spec.py`'dedir.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import ledger as L
from trader_core import lesson as LS
from trader_core.ledger import DecisionEvent, TradeEntry, TradeExit

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5,
          "trigger_tf": "1h"}
R_PER = 43.96
D0 = datetime(2026, 10, 1, tzinfo=UTC)
RUN_DAY = "2026-12-09"
RUN_NOW = datetime(2026, 12, 9, 3, 0, tzinfo=UTC)
PAIRS = ["ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"]


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def mk_dec(bar, pair, ver, rr, atr_ratio=1.1, entered=True, skip=None, session=None):
    kw = dict(bar_close_ts=bar, trigger_tf="1h", pair=pair, side="long", setup="R1", regime="range",
              atr_ratio=atr_ratio, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
              features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": rr,
                        "edge_dist_atr": 0.1},
              planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=ver,
              veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
              size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
              final_action="entered", skip_reason=None, session_tag=session)
    if not entered:
        kw.update(final_action="skipped", skip_reason=skip, risk_allowed=None, veto_status="not_evaluated",
                  risk_reason=None, size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None,
                  leverage=None)
    return DecisionEvent(**kw)


class Env:
    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.clock = Clock(D0 - timedelta(days=1))
        self.led = L.open_ledger(tmp_path / "learner.sqlite", "learner", clock=self.clock,
                                 min_evidence_trades=0, paper_lesson=True)
        self.led.init_params(PARAMS, reason="baslangic")
        self.tid = 0
        self.store_path = tmp_path / "lesson.sqlite"

    def add(self, day, r, ver=1, rr=2.5, atr_ratio=1.1, pair=None, hour=10):
        self.tid += 1
        bar = D0 + timedelta(days=day, hours=hour)
        self.clock.t = max(self.clock.t, bar + timedelta(hours=6))
        pair = pair or PAIRS[self.tid % len(PAIRS)]
        did = self.led.record_decision(mk_dec(bar, pair, ver, rr, atr_ratio))
        self.led.record_trade_entry(TradeEntry(self.tid, did, bar + timedelta(seconds=3), 2000.0, 0.3, 3, 0.0))
        self.led.record_trade_exit(TradeExit(self.tid, bar + timedelta(hours=4), 2000.0 + r * R_PER, "time_stop",
                                             None, 0.0, 0.0))
        return did

    def apply(self, param, value, ts=None):
        if ts is not None:
            self.clock.t = ts
        a = self.led.get_active_params()
        p = self.led.propose_change(base_version_id=a.version_id, changes={param: value}, rationale="t",
                                    claimed_evidence={}, source="rule-proxy")
        assert p.ok, p
        r = self.led.apply_proposal(p.proposal_id, actor="lesson", reason="t")
        assert r.ok, r
        return r

    def service(self, cfg):
        self.clock.t = max(self.clock.t, RUN_NOW)
        store = LS.LessonStore(self.store_path, clock=self.clock)
        notif = []

        class N(LS.NullNotifier):
            def notify(self, n):
                notif.append(n)
                return True

        svc = LS.LessonService(cfg, ledger=self.led, store=store, clock=self.clock, notifier=N(),
                               sleep_fn=lambda s: None, lock_path=None)
        return svc, store, notif


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.led.close()


def mk_cfg(tmp_path, **over):
    d = dict(ledger_path=str(tmp_path / "learner.sqlite"), store_path=str(tmp_path / "lesson.sqlite"),
             mode="rule_proxy", counterfactual_enabled=False)
    d.update(over)
    return LS.LessonConfig(**d)


# --------------------------------------------------------------------------- yapilandirma

def test_shipped_config_is_twinless_and_thresholdless():
    cfg = LS.load_config(ROOT / "config" / "lesson.json")
    raw = json.loads((ROOT / "config" / "lesson.json").read_text())
    assert cfg.shadow_weeks == 0 and cfg.checkpoints == ()
    # 24.11 kullanici karari: ders esikleri ve geri alma (esiksiz kagit kaldirildi)
    assert cfg.min_affected == 8 and cfg.min_distinct_days == 4 and cfg.min_z == 1.64 and cfg.min_gap_r == 0.5
    assert cfg.max_steps_from_ref == 2 and cfg.max_changes_per_night == 1 and cfg.shrink_n == 10
    assert cfg.rollback_effect_r == 3.0 and cfg.brake_effect_r == 10.0
    assert not any(k.startswith("twin_") for k in raw) and "report_show_twin" not in raw
    assert "max_user_requests_per_week" not in raw and "checkpoints" not in raw
    assert cfg.twin_enabled is False


def test_legacy_twin_keys_are_ignored_not_fatal(tmp_path):
    p = tmp_path / "l.json"
    p.write_text(json.dumps({"twin_enabled": True, "twin_ledger_path": "x", "max_steps_from_twin": 1}))
    cfg = LS.load_config(p)
    assert cfg.twin_enabled is False and cfg.max_steps_from_ref == 1


def test_lesson_params_extended_and_optional_in_ledger(env):
    # 24.11 inceleme: motor okumaz => ders menusunde yok (defter parametre olarak tasir)
    assert "session_off" not in LS.LESSON_PARAMS and "post_stop_wait" not in LS.LESSON_PARAMS
    assert "session_off" in L.LESSON_PARAMS and "post_stop_wait" in L.LESSON_PARAMS
    assert L.LESSON_STEP["post_stop_wait"] == 1 and L.LESSON_BOUNDS_DEFAULT["post_stop_wait"] == (0, 3)
    r = env.apply("post_stop_wait", 1)
    assert env.led.get_active_params().params["post_stop_wait"] == 1
    assert env.led.get_active_params().lesson_bounds["session_off"] == (0, 3)
    with pytest.raises(Exception):
        env.apply("post_stop_wait", 3)             # tek adim siniri (1 -> 3)
    assert r.ok


# --------------------------------------------------------------------------- etki ve sonum

def test_damped_mean_and_effect_helpers():
    assert LS.damped_mean(-1.0, 1, 10) == pytest.approx(-1 / 11)
    assert LS.damped_mean(-1.0, 1, 0) == -1.0 and LS.damped_mean(5.0, 0, 0) == 0.0
    assert LS.lesson_effect([1.0, -2.0], [-0.5]) == pytest.approx(-0.5)
    assert LS.damped_effect(-3.0, 1, 0) == -3.0
    assert LS.damped_effect(-3.0, 1, 10) == pytest.approx(-3 / 11)


def test_measure_effect_uses_own_records_and_works_with_n_equal_one(env):
    env.add(0, -1.0, rr=1.6)                      # referans (1.5) alirdi, rr_min 1.75 almaz; gercek sonuc -1 R
    cur, ref = dict(PARAMS, rr_min=1.75), dict(PARAMS)
    eff = LS.measure_effect(env.led, mk_cfg(env.tmp), cur, ref, D0 - timedelta(days=1), RUN_NOW)
    assert eff.n == 1 and eff.n_removed == 1 and eff.effect == pytest.approx(1.0)
    eff2 = LS.measure_effect(env.led, mk_cfg(env.tmp), dict(PARAMS, rr_min=1.25), ref, D0 - timedelta(days=1), RUN_NOW)
    assert eff2.n == 0                              # rr 1.6 iki ayarda da alinir


# --------------------------------------------------------------------------- servis: esiksiz uygulama

def _tighten_scenario(env, n=3):
    # rr in [1.5, 1.75) islemleri kaybettirir, rr 2.5 kazandirir: rr_min:up (tighten) adayi
    for i in range(n):
        env.add(i * 2, -1.0, rr=1.6)
        env.add(i * 2 + 1, 1.0, rr=2.5)


def test_auto_apply_from_few_trades_without_user_or_thresholds(env, tmp_path):
    _tighten_scenario(env, 2)                       # toplam 4 islem
    cfg = mk_cfg(tmp_path)
    svc, store, notif = env.service(cfg)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "applied", res
    assert env.led.get_active_params().params["rr_min"] == 1.75
    assert not [p for p in env.led.list_proposals() if p.status == "needs_user"]
    store.close()


def test_two_changes_in_one_night_and_no_weekly_limit(env, tmp_path):
    _tighten_scenario(env, 3)
    for i in range(6):                              # vol_ratio_max:down icin: yuksek atr_ratio kaybettirir
        env.add(20 + i, -1.0, rr=2.5, atr_ratio=1.45)
        env.add(30 + i, 1.0, rr=2.5, atr_ratio=1.0)
    svc, store, notif = env.service(mk_cfg(tmp_path))
    res = svc.run_tick(RUN_NOW)
    assert res.status == "applied"
    applies = [a for a in env.led.list_activations() if a.kind == "apply" and a.actor == "lesson"]
    assert len(applies) >= 2                       # ayni gece birden cok ayar, haftalik sinir yok
    assert len({e["param"] for e in store._q("SELECT param FROM lesson_decisions WHERE outcome='applied'")}) >= 2
    store.close()


def test_max_changes_per_night_one_limits_to_single_change(env, tmp_path):
    _tighten_scenario(env, 3)
    for i in range(6):
        env.add(20 + i, -1.0, rr=2.5, atr_ratio=1.45)
        env.add(30 + i, 1.0, rr=2.5, atr_ratio=1.0)
    svc, store, _ = env.service(mk_cfg(tmp_path, max_changes_per_night=1))
    svc.run_tick(RUN_NOW)
    assert len([a for a in env.led.list_activations() if a.kind == "apply" and a.actor == "lesson"]) == 1
    store.close()


# --------------------------------------------------------------------------- geri alma (-3 R) ve fren (-10 R)

def test_single_change_rolled_back_when_effect_le_minus_3r(env, tmp_path):
    env.clock.t = datetime(2026, 11, 1, tzinfo=UTC)
    env.apply("rr_min", 1.25, ts=datetime(2026, 11, 1, tzinfo=UTC))       # gevsetme: rr 1.3 artik alinir
    env.add(40, -3.5, ver=2, rr=1.3)                                      # gevsetmenin aldirdigi kayip: -3.5 R
    svc, store, notif = env.service(mk_cfg(tmp_path, monitor_max_days=60, recheck_max_days=60))
    svc._ensure_monitors(svc._open_ctx(), "2026-11-01")
    res = svc.run_tick(RUN_NOW)
    assert res.status == "rolled_back", res
    assert env.led.get_active_params().params["rr_min"] == 1.5
    store.close()


def test_effect_above_minus_3r_does_not_roll_back(env, tmp_path):
    env.apply("rr_min", 1.25, ts=datetime(2026, 11, 1, tzinfo=UTC))
    env.add(40, -2.5, ver=2, rr=1.3)
    svc, store, _ = env.service(mk_cfg(tmp_path, monitor_max_days=60, recheck_max_days=60))
    svc._ensure_monitors(svc._open_ctx(), "2026-11-01")
    res = svc.run_tick(RUN_NOW)
    assert res.status != "rolled_back"
    store.close()


def test_cumulative_brake_returns_to_reference_and_stops_auto_apply(env, tmp_path):
    t = datetime(2026, 11, 1, tzinfo=UTC)
    env.apply("rr_min", 1.25, ts=t)
    for i in range(4):
        env.add(40 + i, -3.0, ver=2, rr=1.3)                              # toplam -12 R
    cfg = mk_cfg(tmp_path, monitor_max_days=60, recheck_max_days=60, rollback_effect_r=100.0)  # tek-degisiklik geri almasi kapali: yalniz fren
    bv = LS.evaluate_brake(env.led, cfg, RUN_NOW)
    assert bv.tripped and bv.effect.effect == pytest.approx(-12.0) and not LS.brake_active(env.led)
    svc, store, notif = env.service(cfg)
    res = svc.run_tick(RUN_NOW)
    assert res.status == "rolled_back" and res.code == "brake", res
    assert env.led.get_active_params().params["rr_min"] == 1.5
    assert LS.brake_active(env.led) and any(n.code == "brake" for n in notif)
    # ertesi gun: otomatik uygulama durdu (kanit olsa bile)
    _tighten_scenario(env, 3)
    env.clock.t = RUN_NOW + timedelta(days=1)
    res2 = svc.run_tick(env.clock.t)
    assert res2.status == "skipped_gate" and res2.code == "brake_active", res2
    store.close()


def test_brake_reference_is_last_owner_approved_version(env):
    env.apply("rr_min", 1.25, ts=datetime(2026, 11, 1, tzinfo=UTC))
    ref, since = LS._ref_activation(env.led, mk_cfg(env.tmp))
    assert ref == 1                                 # baslangic surum (actor=system); ders surumu referans degil


def test_no_twin_ledger_needed(env, tmp_path):
    _tighten_scenario(env, 1)
    svc, store, _ = env.service(mk_cfg(tmp_path))
    assert svc.run_tick(RUN_NOW).status in ("applied", "no_change", "skipped_gate")
    store.close()


def test_max_steps_from_reference_two(env, tmp_path):
    # referanstan zaten 2 adim (1.5 -> 2.0) uzaktayiz: rr_min:up artik uygun degil
    env.apply("rr_min", 1.75, ts=datetime(2026, 11, 1, tzinfo=UTC))
    env.apply("rr_min", 2.0, ts=datetime(2026, 11, 2, tzinfo=UTC))
    for i in range(3):
        env.add(i * 2, -1.0, ver=3, rr=1.9)
        env.add(i * 2 + 1, 1.0, ver=3, rr=2.5)
    snap = LS.build_snapshot(env.led, mk_cfg(tmp_path), RUN_DAY)
    for m in snap.menu:
        if m.menu_id == "rr_min:up":
            assert not m.eligible
