"""Sanal kasa (docs/motor/sanal-kasa-spec.md) uygulama testleri: arm_virtual_bankroll, karne 'kasa' anahtari, Telegram suffix."""
from datetime import datetime, timedelta, timezone

import pytest

from trader_core import counterfactual as CF

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _c(arm, i, r, taken=True, asset="kripto"):
    return {"arm_id": arm, "asset_class": asset, "taken": taken, "ts": T0 + timedelta(hours=i), "r": r, "decision_id": i}


def test_compounding_and_drawdown():
    cands = [_c("A", 1, 1.0), _c("A", 2, -2.0), _c("A", 3, 1.0)]
    res = CF.arm_virtual_bankroll(cands)["A"]
    # 1000 -> 1010 -> 1010*(1-0.02)=989.8 -> 989.8*1.01=999.698
    assert res["taken"]["n"] == 3
    assert res["taken"]["equity"] == 999.7
    assert res["taken"]["return_pct"] == pytest.approx(-0.03, abs=0.01)
    assert res["taken"]["max_dd_pct"] == pytest.approx((1010 - 989.8) / 1010 * 100, abs=0.01)


def test_taken_vs_cf_split_and_unresolved_excluded():
    cands = [_c("A", 1, 1.0, taken=True), _c("A", 2, 2.0, taken=False), _c("A", 3, None, taken=False),
             _c("A", 4, None, taken=True)]
    res = CF.arm_virtual_bankroll(cands)["A"]
    assert res["taken"]["n"] == 1 and res["cf"]["n"] == 2


def test_ordering_by_ts_and_stable_ties():
    a, b = _c("A", 2, -1.0), _c("A", 1, 1.0)
    res_sorted = CF.arm_virtual_bankroll([a, b])["A"]["taken"]
    res_direct = CF.arm_virtual_bankroll([b, a])["A"]["taken"]
    assert res_sorted == res_direct
    same_ts = [dict(_c("A", 1, 5.0), decision_id=1), dict(_c("A", 1, -1.0), decision_id=2)]
    assert CF.arm_virtual_bankroll(same_ts)["A"]["taken"]["equity"] == round(1000 * (1 + 0.05) * (1 - 0.01), 2)


def test_equity_floor_at_zero():
    cands = [_c("A", 1, -150.0), _c("A", 2, 1.0)]     # 1 + 0.01*-150 = -0.5 -> 0
    res = CF.arm_virtual_bankroll(cands)["A"]["taken"]
    assert res["equity"] == 0.0 and res["return_pct"] == -100.0 and res["max_dd_pct"] == 100.0


def test_empty_arm_listed_and_defaults():
    res = CF.arm_virtual_bankroll([_c("A", 1, 1.0)], arms=("B",))
    assert res["B"] == {"taken": {"n": 0, "equity": 1000.0, "return_pct": 0.0, "max_dd_pct": 0.0},
                        "cf": {"n": 0, "equity": 1000.0, "return_pct": 0.0, "max_dd_pct": 0.0}}


@pytest.mark.parametrize("kw", [{"start": 0}, {"start": -1.0}, {"risk": 0}, {"risk": -0.1}])
def test_invalid_params_raise(kw):
    with pytest.raises(ValueError):
        CF.arm_virtual_bankroll([], **kw)


def test_scorecard_kasa_key_and_existing_fields_unchanged():
    cands = [_c("A", 1, 1.0), _c("A", 2, 1.0, taken=False)]
    sc = CF.arm_scorecard(cands, arms=("A", "B"))
    assert sc["A"]["kasa"] == CF.arm_virtual_bankroll(cands, arms=("A", "B"))["A"]
    assert sc["B"]["kasa"]["taken"]["n"] == 0 and sc["B"]["candidates"] == 0
    assert sc["A"]["candidates"] == 2 and sc["A"]["taken"] == 1 and sc["A"]["state"] == "open"


def test_telegram_karne_satiri_kalkti_sanal_kasa_verisi_durur():
    """26.11: kurulum karnesi (ve sanal kasa soneki) Telegram'dan kalkti; `arm_scorecard` kasa verisi hesaplanmaya devam eder (yukarida)."""
    from trader_core import telegram as TG
    assert not hasattr(TG, "_karne_satirlari") and not hasattr(TG, "kurulumlar_metni")
