"""RK-1 bagimsiz sartname testi: saglik denetcisi kademe alarmlari (docs/motor/12-risk-kademe.md §11, T-60).
Gerceklemeye (health.py ic kodu) BAKILMADAN yazildi. Duzenek tests/test_health_spec.py yardimcilarini kullanir.
Denetim adi `risk_ladder:<bot>`; bot basina en agir tek sonuc. Blok bicimi §10 (status.json `risk_ladder`),
`ApiProbe.ladder` = blok (+ opsiyonel "pause_holds": [{reason, at}]).
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from test_health_spec import NOW, Status, good_api, h, one, pick, snap  # noqa: E402


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(**kw):
    return iso(NOW - timedelta(**kw))


def block(**over):
    b = {"enforce": True, "state": "ok", "step": 0, "step_name": "K0", "step_risk": 0.005, "effective_risk": 0.005,
         "lowest_step": 0, "step_since": ago(days=10), "started_at": ago(days=10), "dep_net": 250.0, "base": 250.0,
         "peak": 262.4, "equity": 258.1, "dd_base_pct": 0.0, "dd_peak_pct": 1.64, "stop_at": 200.0,
         "floor_at": 150.0, "near": False, "stopped_at": None, "last_down_at": None, "gate_code": None,
         "gate_since": None, "transfer": None, "pending": None, "would": None, "follow": None,
         "counters": {"total_trades": 37}, "log_seq": 4, "log_hash": "1c1cc11e"}
    b.update(over)
    return b


def rep_for(ladder, mode="live", bot="learner", **apikw):
    api = {b: good_api() for b in ("learner", "twin")}
    api[bot] = good_api(mode=mode, ladder=ladder, **apikw)
    return h.evaluate(snap(api=api))


def res(ladder, mode="live", bot="learner", **apikw):
    return one(rep_for(ladder, mode, bot, **apikw), "risk_ladder", bot)


# ---------------------------------------------------------------------------- tablonun her satiri
class TestTable:
    def test_none_ok(self):
        r = res(block())
        assert r.status == Status.OK and r.code == "ok"

    def test_ladder_missing_live(self):
        r = res(None, mode="live")
        assert (r.status, r.code) == (Status.CRIT, "ladder_missing")

    def test_floor(self):
        r = res(block(state="floor", equity=140.0, stopped_at=ago(hours=1)))
        assert (r.status, r.code) == (Status.CRIT, "capital_floor")
        assert "/hepsini_kapat" in r.detail

    def test_review(self):
        r = res(block(state="review", equity=195.0, stopped_at=ago(hours=1)))
        assert (r.status, r.code) == (Status.CRIT, "drawdown_review")
        assert "/hepsini_kapat" in r.detail and "/kademe_devam" in r.detail

    @pytest.mark.parametrize("state", ["uninitialized", "invalid"])
    def test_bad_state(self, state):
        # SPEC-AMBIGUOUS: "aynı kod" = durum adi ya da zorlayan kapi kodu (uninitialized -> capital_missing, invalid -> ladder_invalid)
        r = res(block(state=state, dep_net=None, base=None, peak=None, equity=None))
        assert r.status == Status.CRIT and r.code in (state, {"uninitialized": "capital_missing", "invalid": "ladder_invalid"}[state])

    @pytest.mark.parametrize("code", ["capital_missing", "ladder_invalid", "equity_unreadable"])
    def test_enforcing_gate_codes(self, code):
        r = res(block(gate_code=code, gate_since=ago(minutes=1)))
        assert (r.status, r.code) == (Status.CRIT, code)

    def test_capital_mismatch_warn(self):
        r = res(block(gate_code="capital_mismatch", gate_since=ago(minutes=5)))
        assert (r.status, r.code) == (Status.WARN, "capital_mismatch")

    def test_capital_unverified_warn(self):
        r = res(block(gate_code="capital_unverified", gate_since=ago(hours=5)))
        assert (r.status, r.code) == (Status.WARN, "capital_unverified")        # yukselmez

    def test_near_warn(self):
        r = res(block(near=True, equity=210.0))
        assert (r.status, r.code) == (Status.WARN, "ladder_near")

    def test_step_down_older_than_24h_ok(self):
        r = res(block(last_down_at=ago(hours=25)))
        assert r.status == Status.OK

    def test_step_down_ignored_when_not_ok_state_uses_state(self):
        r = res(block(state="review", last_down_at=ago(hours=1), stopped_at=ago(hours=1)))
        assert r.code == "drawdown_review"

    def test_hold_fresh_ok(self):
        r = res(block(pause_holds=[{"reason": "drawdown_review", "at": ago(minutes=9)}]))
        assert r.status == Status.OK

    def test_hold_other_reason_not_stale(self):
        r = res(block(pause_holds=[{"reason": "user_cmd", "at": ago(hours=3)}]))
        assert r.status == Status.OK

    def test_hold_stale_needs_state_ok(self):
        r = res(block(state="review", stopped_at=ago(hours=1),
                      pause_holds=[{"reason": "drawdown_review", "at": ago(hours=3)}]))
        assert r.code == "drawdown_review" and r.status == Status.CRIT

    def test_would_older_than_24h_ok(self):
        r = res(block(would={"kind": "review_stop", "at": ago(hours=25)}), mode="paper")
        assert r.status == Status.OK


# ---------------------------------------------------------------------------- capital_mismatch siniri
class TestMismatchBoundary:
    def test_29_min_warn(self):
        r = res(block(gate_code="capital_mismatch", gate_since=ago(minutes=29)))
        assert r.status == Status.WARN

    def test_31_min_crit(self):
        r = res(block(gate_code="capital_mismatch", gate_since=ago(minutes=31)))
        assert (r.status, r.code) == (Status.CRIT, "capital_mismatch")

    def test_unverified_never_escalates(self):
        r = res(block(gate_code="capital_unverified", gate_since=ago(days=2)))
        assert r.status == Status.WARN


# ---------------------------------------------------------------------------- ladder_missing yalniz live/testnet
class TestMissingModes:
    @pytest.mark.parametrize("mode", ["live", "testnet"])
    def test_missing_crit(self, mode):
        r = res(None, mode=mode)
        assert (r.status, r.code) == (Status.CRIT, "ladder_missing")

    @pytest.mark.parametrize("mode", ["paper", "backtest", None])
    def test_missing_not_alarm(self, mode):
        rs = pick(rep_for(None, mode=mode), "risk_ladder", "learner")      # denetim hic uretilmeyebilir (SKIPPED/yok)
        assert all(r.status not in (Status.WARN, Status.CRIT) and r.code != "ladder_missing" for r in rs)

    def test_per_bot_independent(self):
        api = {"learner": good_api(mode="live", ladder=block()), "twin": good_api(mode="live", ladder=None)}
        rep = h.evaluate(snap(api=api))
        assert one(rep, "risk_ladder", "learner").status == Status.OK
        assert one(rep, "risk_ladder", "twin").code == "ladder_missing"


# ---------------------------------------------------------------------------- en agir tek sonuc
class TestWorstWins:
    def test_one_result_per_bot(self):
        rep = rep_for(block(state="floor", near=True, gate_code="capital_mismatch", gate_since=ago(minutes=40),
                            last_down_at=ago(hours=1)))
        assert len(pick(rep, "risk_ladder", "learner")) == 1

    def test_floor_beats_everything(self):
        r = res(block(state="floor", near=True, gate_code="capital_mismatch", gate_since=ago(minutes=5),
                      last_down_at=ago(hours=1), would={"kind": "floor_stop", "at": ago(hours=1)}))
        assert (r.status, r.code) == (Status.CRIT, "capital_floor")

    def test_review_beats_warns(self):
        r = res(block(state="review", gate_code="capital_mismatch", gate_since=ago(minutes=5), near=True,
                      stopped_at=ago(hours=1)))
        assert (r.status, r.code) == (Status.CRIT, "drawdown_review")

    def test_ladder_invalid_beats_near(self):
        r = res(block(gate_code="ladder_invalid", near=True))
        assert (r.status, r.code) == (Status.CRIT, "ladder_invalid")

    def test_old_mismatch_crit_beats_near_and_step_down(self):
        r = res(block(gate_code="capital_mismatch", gate_since=ago(minutes=45), near=True,
                      last_down_at=ago(hours=2)))
        assert (r.status, r.code) == (Status.CRIT, "capital_mismatch")

    def test_several_warns_still_warn(self):
        r = res(block(near=True, last_down_at=ago(hours=2), gate_code="capital_unverified"))
        assert r.status == Status.WARN

    def test_crit_makes_report_unhealthy(self):
        rep = rep_for(block(state="review", stopped_at=ago(hours=1)))
        assert rep.overall == Status.CRIT and not rep.healthy
        assert any(x.name.startswith("risk_ladder") for x in rep.failing())

    def test_warn_report_overall_warn_at_least(self):
        rep = rep_for(block(near=True))
        assert one(rep, "risk_ladder", "learner").status == Status.WARN and not rep.healthy

    def test_ok_block_leaves_report_healthy_for_ladder(self):
        rep = rep_for(block())
        assert not any(x.name.startswith("risk_ladder") for x in rep.failing())


def test_garbage_block_never_raises():
    for g in ({}, {"state": 5}, {"state": "review"}, {"gate_code": 7, "near": "x"}, "str", 3):
        rep = rep_for(g)
        assert pick(rep, "risk_ladder", "learner")
