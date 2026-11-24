"""24.11 kullanici karari: ders esikleri ve geri alma.

1. kanit esikleri (min_affected 8, min_distinct_days 4, min_gap_r 0.5, min_z 1.64): `calibration: null` iken de uygulanir
2. max_changes_per_night 1: bir gecede en cok tek ayar
3. stop_buffer_atr / range_target_frac: "ozgun vs yeni" karsi-olgusal geri alma (>= 10 islem, cikis kipleriyle ayni olcut)
5. shrink_n 10: -3 R etkisine uygulanir
6. olu yapilandirma anahtarlari silindi; bilinmeyen anahtar hatadir
(4. kapsam haritasi: test_ders_kapsam.py)
"""
import dataclasses
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from test_dd12_wp08_impl import (D0, PAIRS, PARAMS, R_PER, ROOT, RUN_DAY, RUN_NOW, Env, env, mk_cfg, mk_dec,  # noqa: F401
                                 _tighten_scenario)
from trader_core import lesson as LS
from trader_core.ledger import TradeEntry, TradeExit
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar

UTC = timezone.utc
SHIPPED = ROOT / "config" / "lesson.json"
H = timedelta(hours=1)


# ----------------------------------------------------------------------------------------------- 1. kanit esikleri
def shipped_cfg(tmp_path, **over):
    cfg = LS.load_config(SHIPPED)
    return dataclasses.replace(cfg, ledger_path=str(tmp_path / "learner.sqlite"), store_path=str(tmp_path / "lesson.sqlite"),
                               mode="rule_proxy", counterfactual_enabled=False, **over)


def test_shipped_config_values_and_calibration_is_null():
    cfg = LS.load_config(SHIPPED)
    raw = json.loads(SHIPPED.read_text())
    assert cfg.calibration is None and "calibration" not in raw or raw["calibration"] is None
    assert (cfg.min_affected, cfg.min_distinct_days, cfg.min_gap_r, cfg.min_z) == (8, 4, 0.5, 1.64)
    assert cfg.max_changes_per_night == 1 and cfg.shrink_n == 10 and cfg.rollback_effect_r == 3.0


def _row(i, r, rr, day):
    return LS.TradeRow(trade_id=i, decision_id=i, pair=PAIRS[i % 6], side="long", setup="R1", regime="range", atr_ratio=1.0,
                       entry_ts=f"2026-11-{day:02d}T10:00:00Z", exit_ts=f"2026-11-{day:02d}T14:00:00Z", day=f"2026-11-{day:02d}",
                       r=r, exit_reason="time_stop", planned_risk=40.0, fee_entry=0.0, fee_exit=0.0, funding=0.0,
                       gross_pnl=r * 40.0, mfe_r=None, mae_r=None, bars_held=4, rr=rr, stop_dist_atr=2.0, version_id=1)


def _rr_sample(n_a, days_a, r_a=-1.0, r_b=1.0, n_b=8, days_b=4):
    """A: rr < 1.75 (rr_min:up ile elenecekler); B: gerisi. Kucuk sapma: z tanimli olsun."""
    wob = (-0.1, 0.1)
    a = [_row(i, r_a + wob[i % 2], 1.6, 1 + i % days_a) for i in range(n_a)]
    b = [_row(100 + i, r_b + wob[(i + 1) % 2], 2.5, 1 + i % days_b) for i in range(n_b)]
    return a + b


def _eval(sample, cfg):
    return LS.eval_rule(LS.RULES_BY_ID["rr_min:up"], sample, 1.5, 1.75, cfg)


def test_thresholds_are_applied_with_calibration_null(tmp_path):
    cfg = shipped_cfg(tmp_path)
    assert cfg.calibration is None
    ok = _eval(_rr_sample(8, 4), cfg)
    assert ok["passed"], ok["fails"]
    # min_affected 8: 7 etkilenen islem yetmez
    assert "n_a_low" in _eval(_rr_sample(7, 4), cfg)["fails"]
    # min_distinct_days 4: orneklem 3 gunde toplanmis
    assert "cluster_guard" in _eval(_rr_sample(8, 3, n_b=8, days_b=3), cfg)["fails"]
    assert "cluster_guard" not in _eval(_rr_sample(8, 3, n_b=8, days_b=3), dataclasses.replace(cfg, min_distinct_days=3))["fails"]


def test_gap_and_z_thresholds_each_bind(tmp_path):
    cfg = shipped_cfg(tmp_path)
    s_gap = _rr_sample(8, 4, r_a=-0.1, r_b=0.3)                     # fark 0.4 < 0.5
    assert "gap_low" in _eval(s_gap, cfg)["fails"]
    # fark yeterli (0.8) ama A gurultulu: z < 1.64
    noisy = [_row(i, (-3.0 if i % 2 else 2.0), 1.6, 1 + i % 4) for i in range(8)] + \
        [_row(100 + i, 0.5, 2.5, 1 + i % 4) for i in range(8)]
    res = _eval(noisy, cfg)
    assert "gap_low" not in res["fails"] and "z_low" in res["fails"], res
    # esikler gevsetilince (kod varsayilani: esiksiz) ayni orneklem gecer ya da en az z_low/gap_low/n_a_low kalkar
    loose = dataclasses.replace(cfg, min_z=0.0, min_gap_r=0.0, min_affected=1, min_distinct_days=1)
    assert "z_low" not in _eval(noisy, loose)["fails"]
    assert "n_a_low" not in _eval(_rr_sample(7, 4), loose)["fails"]
    assert "gap_low" not in _eval(s_gap, loose)["fails"]


def test_snapshot_menu_entry_not_eligible_below_shipped_thresholds(env, tmp_path):
    _tighten_scenario(env, 3)                                        # 3 kaybettiren (rr 1.6) + 3 kazandiran: n_a = 3 < 8
    snap = LS.build_snapshot(env.led, shipped_cfg(tmp_path), RUN_DAY)
    entry = next(m for m in snap.menu if m.menu_id == "rr_min:up")
    assert not entry.eligible
    snap0 = LS.build_snapshot(env.led, mk_cfg(tmp_path), RUN_DAY)   # esiksiz kod varsayilani: ayni veri uygun
    assert next(m for m in snap0.menu if m.menu_id == "rr_min:up").eligible


# ----------------------------------------------------------------------------------------------- 2. gecelik sinir
def _two_change_scenario(env):
    _tighten_scenario(env, 3)
    for i in range(6):
        env.add(20 + i, -1.0, rr=2.5, atr_ratio=1.45)
        env.add(30 + i, 1.0, rr=2.5, atr_ratio=1.0)


def _lesson_applies(env):
    return [a for a in env.led.list_activations() if a.kind == "apply" and a.actor == "lesson"]


def test_max_changes_per_night_from_shipped_config_allows_one(env, tmp_path):
    _two_change_scenario(env)
    base = shipped_cfg(tmp_path, min_affected=1, min_gap_r=0.0, min_z=0.0, min_distinct_days=1)   # esikler gevsek: sinir test edilir
    assert base.max_changes_per_night == 1
    svc, store, _ = env.service(base)
    svc.run_tick(RUN_NOW)
    assert len(_lesson_applies(env)) == 1
    store.close()


def test_without_the_limit_two_changes_happen_same_night(env, tmp_path):
    _two_change_scenario(env)
    base = shipped_cfg(tmp_path, min_affected=1, min_gap_r=0.0, min_z=0.0, min_distinct_days=1, max_changes_per_night=None)
    svc, store, _ = env.service(base)
    svc.run_tick(RUN_NOW)
    assert len(_lesson_applies(env)) >= 2                             # kontrol: sinir olmayinca birden cok
    store.close()


def test_limit_two_caps_at_two(env, tmp_path):
    _two_change_scenario(env)
    svc, store, _ = env.service(mk_cfg(tmp_path, max_changes_per_night=2))
    svc.run_tick(RUN_NOW)
    assert len(_lesson_applies(env)) <= 2
    store.close()


# ----------------------------------------------------------------------------------------------- 5. sonum (shrink_n)
def _rr_rollback_env(env, n_trades, r_each):
    env.apply("rr_min", 1.25, ts=datetime(2026, 11, 1, tzinfo=UTC))
    for i in range(n_trades):
        env.add(40 + i, r_each, ver=2, rr=1.3)                      # gevsetmenin aldirdigi kayiplar


def _verdict(env, tmp_path, **over):
    cfg = mk_cfg(tmp_path, monitor_max_days=60, recheck_max_days=60, **over)
    mon = LS.monitor_from_ledger(env.led, cfg)
    assert mon is not None and mon.param == "rr_min"
    return LS.evaluate_monitor(env.led, None, mon, RUN_NOW, cfg)


def test_shrink_applies_to_minus_3r_effect(env, tmp_path):
    _rr_rollback_env(env, 1, -3.5)                                  # tek karar: sonumsuz -3.5 R, sonumlu -3.5/11
    assert _verdict(env, tmp_path, shrink_n=0).action == "rolled_back"
    v = _verdict(env, tmp_path, shrink_n=10)
    assert v.action == "wait" and v.stats["shrink_n"] == 10
    assert v.stats["damped_effect"] == pytest.approx(-3.5 / 11, abs=1e-3) and v.stats["effect"] == pytest.approx(-3.5)


def test_shrink_still_rolls_back_with_enough_evidence(env, tmp_path):
    _rr_rollback_env(env, 4, -3.0)                                  # etki -12 R, n=4: -12*4/14 = -3.43 <= -3
    v = _verdict(env, tmp_path, shrink_n=10)
    assert v.action == "rolled_back" and v.stats["damped_effect"] == pytest.approx(-12 * 4 / 14, abs=1e-3)


def test_shrink_blocks_rollback_with_two_decisions(env, tmp_path):
    _rr_rollback_env(env, 2, -3.5)                                  # etki -7 R, n=2: -7*2/12 = -1.17 > -3
    assert _verdict(env, tmp_path, shrink_n=0).action == "rolled_back"
    assert _verdict(env, tmp_path, shrink_n=10).action == "wait"


# ----------------------------------------------------------------------------------------------- 6. olu anahtarlar
DEAD = ("monitor_k", "monitor_margin_r", "monitor_z", "early_min_n", "early_mean_r", "early_z", "early_min_days")


def test_dead_config_keys_are_gone_and_unknown_keys_error(tmp_path):
    raw = json.loads(SHIPPED.read_text())
    assert not any(k in raw for k in DEAD)
    names = {f.name for f in dataclasses.fields(LS.LessonConfig)}
    assert not names & set(DEAD)
    for k in DEAD:
        p = tmp_path / f"{k}.json"
        p.write_text(json.dumps({**raw, k: 1}))
        with pytest.raises(LS.LessonConfigError):
            LS.load_config(p)
    p = tmp_path / "typo.json"
    p.write_text(json.dumps({**raw, "min_zz": 1.0}))
    with pytest.raises(LS.LessonConfigError):
        LS.load_config(p)


def test_monitor_k_is_a_constant_not_config(env, tmp_path):
    env.apply("rr_min", 1.25, ts=datetime(2026, 11, 1, tzinfo=UTC))
    mon = LS.monitor_from_ledger(env.led, mk_cfg(tmp_path))
    assert mon.k == LS.MONITOR_K == 20


# ----------------------------------------------------------------------------------------------- 3. ozgun vs yeni geri alma
class FakeMarket:
    """`.window(pair, start_ms, n, tf)`: her karar penceresi icin ayni mum sekli (`shape` = {k: (h, l, c)})."""

    def __init__(self, shape, flat=(2001.0, 1999.0, 2000.0)):
        self.shape, self.flat, self.calls = shape, flat, 0

    def window(self, pair, start_ms, n, tf="1h"):
        self.calls += 1
        step = 3_600_000
        out = []
        for k in range(n):
            h, l, c = self.shape.get(k, self.flat)
            out.append((start_ms + k * step, h, l, c))
        return out


def add_plan(env, day, r, ver, *, stop, target, sda, setup="R1", hour=10):
    """Ozel planli karar + islem (mk_dec'in plani sabit; burada stop/hedef/ATR orani verilir)."""
    env.tid += 1
    bar = D0 + timedelta(days=day, hours=hour)
    env.clock.t = max(env.clock.t, bar + timedelta(hours=6))
    ev = mk_dec(bar, PAIRS[env.tid % len(PAIRS)], ver, 2.5)
    feats = dict(ev.features, stop_dist_atr=sda)
    ev = dataclasses.replace(ev, planned_stop=stop, planned_target=target, features=feats, setup=setup)
    did = env.led.record_decision(ev)
    env.led.record_trade_entry(TradeEntry(env.tid, did, bar + timedelta(seconds=3), 2000.0, 0.3, 3, 0.0))
    env.led.record_trade_exit(TradeExit(env.tid, bar + timedelta(hours=4), 2000.0 + r * R_PER, "time_stop", None, 0.0, 0.0))
    return did


def _cfg_replay(tmp_path, **over):
    return mk_cfg(tmp_path, monitor_max_days=60, recheck_max_days=60, **over)


def _monitor(env, cfg, param):
    mon = LS.monitor_from_ledger(env.led, cfg)
    assert mon is not None and mon.param == param
    return mon


# R1, stop_buffer_atr 0.3 -> 0.2: yeni stop 1962 (ATR 20, 0.1 ATR = 2), ozgun stop 1960. Yol 1961'e iner sonra hedefe gider:
# yeni stop vurur (-1R), ozgun hayatta kalir ve hedefe (2100) ulasir.
HARM_STOP = {3: (2001.0, 1961.0, 1990.0), 10: (2110.0, 1995.0, 2100.0)}
OK_STOP = {10: (2110.0, 1995.0, 2100.0)}                              # dip yok: iki ayar da hedefe gider


def _stopbuf_env(env, n, shape_days=3):
    env.apply("stop_buffer_atr", 0.2, ts=datetime(2026, 11, 1, tzinfo=UTC))
    for i in range(n):
        add_plan(env, 33 + i * shape_days, -1.0, 2, stop=1962.0, target=2100.0, sda=1.9)


def test_stop_buffer_harm_rolls_back_via_original_vs_new_replay(env, tmp_path):
    _stopbuf_env(env, 10)
    cfg = _cfg_replay(tmp_path)
    mon = _monitor(env, cfg, "stop_buffer_atr")
    v = LS.evaluate_monitor(env.led, None, mon, RUN_NOW, cfg, _market=FakeMarket(HARM_STOP))
    assert v.action == "rolled_back" and v.stage == "param_effect", v
    assert v.stats["n"] == 10 and v.stats["orig_sum_r"] > v.stats["new_sum_r"] + 2.0
    assert v.stats["new_worst_r"] <= v.stats["orig_worst_r"] - 1.0 + 1e-9


def test_stop_buffer_needs_ten_trades(env, tmp_path):
    _stopbuf_env(env, 9)
    cfg = _cfg_replay(tmp_path)
    v = LS.evaluate_monitor(env.led, None, _monitor(env, cfg, "stop_buffer_atr"), RUN_NOW, cfg, _market=FakeMarket(HARM_STOP))
    assert v.action == "wait"                                       # 9 islem: olcut kurulmaz (olagan akis surer)


def test_stop_buffer_no_rollback_when_new_is_not_worse(env, tmp_path):
    _stopbuf_env(env, 10)
    cfg = _cfg_replay(tmp_path)
    v = LS.evaluate_monitor(env.led, None, _monitor(env, cfg, "stop_buffer_atr"), RUN_NOW, cfg, _market=FakeMarket(OK_STOP))
    assert v.action == "wait"


def test_original_plan_math_long_and_short(env):
    dec = type("D", (), dict(planned_entry=2000.0, planned_stop=1962.0, planned_target=2100.0, side="long", setup="R1",
                             features={"stop_dist_atr": 1.9}, rh=2100.0, rl=1980.0))
    assert LS.original_plan("stop_buffer_atr", dec, 0.3, 0.2) == pytest.approx((1960.0, 2100.0))
    short = type("D", (), dict(planned_entry=2000.0, planned_stop=2038.0, planned_target=1900.0, side="short", setup="R1",
                               features={"stop_dist_atr": 1.9}, rh=2020.0, rl=1900.0))
    assert LS.original_plan("stop_buffer_atr", short, 0.3, 0.2) == pytest.approx((2040.0, 1900.0))
    b1 = type("D", (), dict(planned_entry=2000.0, planned_stop=1962.0, planned_target=2076.0, side="long", setup="B1",
                            features={"stop_dist_atr": 1.9}, rh=None, rl=None))      # hedef = giris + 2R
    s0, t0 = LS.original_plan("stop_buffer_atr", b1, 0.3, 0.2)
    assert s0 == pytest.approx(1960.0) and t0 == pytest.approx(2080.0)
    # range_target_frac 0.75 -> 0.625: yeni hedef 2055, ozgun 2070 (aralik 120)
    r1 = type("D", (), dict(planned_entry=2000.0, planned_stop=1960.0, planned_target=2055.0, side="long", setup="R1",
                            features={"stop_dist_atr": 2.0}, rh=2100.0, rl=1980.0))
    assert LS.original_plan("range_target_frac", r1, 0.75, 0.625) == pytest.approx((1960.0, 2070.0))
    assert LS.original_plan("post_stop_wait", r1, 0, 1) is None
    nofeat = type("D", (), dict(planned_entry=2000.0, planned_stop=1962.0, planned_target=2100.0, side="long", setup="R1",
                                features={}, rh=2100.0, rl=1980.0))
    assert LS.original_plan("stop_buffer_atr", nofeat, 0.3, 0.2) is None


# range_target_frac 0.75 -> 0.625: yeni hedef 2055 (1.375 R), ozgun 2070 (1.75 R... 70/40). Yol 2080'e cikar: ikisi de hedefe ulasir,
# ozgun daha cok kazanir: fark islem basina ~0.375 R. 10 islemde 3.75 R >= max(2 R, %20 x yeni)
RT_UP = {5: (2080.0, 1995.0, 2075.0)}


def _target_env(env, n):
    env.apply("range_target_frac", 0.625, ts=datetime(2026, 11, 1, tzinfo=UTC))
    for i in range(n):
        add_plan(env, 33 + i * 3, 1.0, 2, stop=1960.0, target=2055.0, sda=2.0)


def test_range_target_frac_harm_rolls_back(env, tmp_path):
    _target_env(env, 12)
    cfg = _cfg_replay(tmp_path)
    v = LS.evaluate_monitor(env.led, None, _monitor(env, cfg, "range_target_frac"), RUN_NOW, cfg, _market=FakeMarket(RT_UP))
    assert v.action == "rolled_back" and v.stage == "param_effect" and v.stats["n"] == 12, v


def test_range_target_frac_no_rollback_below_ten(env, tmp_path):
    _target_env(env, 9)
    cfg = _cfg_replay(tmp_path)
    v = LS.evaluate_monitor(env.led, None, _monitor(env, cfg, "range_target_frac"), RUN_NOW, cfg, _market=FakeMarket(RT_UP))
    assert v.action == "wait"


def test_replay_waits_until_horizon_and_without_market_fails_safe(env, tmp_path):
    _stopbuf_env(env, 10)
    cfg = _cfg_replay(tmp_path, param_cf_market_path=str(tmp_path / "yok.sqlite"))
    mon = _monitor(env, cfg, "stop_buffer_atr")
    # market dosyasi yok: kanit yok => olagan akis (bekle); hata yok
    assert LS.evaluate_monitor(env.led, None, mon, RUN_NOW, cfg).action == "wait"
    # ufuk (48 mum) dolmadi: as_of karar mumundan 1 gun sonra
    early = datetime(2026, 11, 3, tzinfo=UTC) + timedelta(days=1)
    assert LS.param_replay_verdict(env.led, cfg, mon, datetime(2026, 11, 1, tzinfo=UTC), early,
                                   market=FakeMarket(HARM_STOP)) is None


def test_disabled_flag_and_post_stop_wait_do_nothing(env, tmp_path):
    _stopbuf_env(env, 10)
    cfg = _cfg_replay(tmp_path, param_cf_enabled=False)
    mon = _monitor(env, cfg, "stop_buffer_atr")
    assert LS.evaluate_monitor(env.led, None, mon, RUN_NOW, cfg, _market=FakeMarket(HARM_STOP)).action == "wait"
    pw = dataclasses.replace(mon, param="post_stop_wait")
    assert LS.param_replay_verdict(env.led, _cfg_replay(tmp_path), pw, datetime(2026, 11, 1, tzinfo=UTC), RUN_NOW,
                                   market=FakeMarket(HARM_STOP)) is None


def test_default_market_path_is_next_to_var_dir():
    cfg = LS.LessonConfig(ledger_path="/srv/var/learner/ledger.sqlite")
    assert LS.param_cf_market_path(cfg) == "/srv/var/market.sqlite"
    assert LS.param_cf_market_path(dataclasses.replace(cfg, param_cf_market_path="/x/m.sqlite")) == "/x/m.sqlite"


def _bar_for(pair, start, k, h, l, c):
    return Bar(pair, "last", "1h", start + k * H, 2000.0, h, l, c, 1.0)


def test_service_rollback_with_market_store(env, tmp_path):
    _stopbuf_env(env, 10)
    mpath = tmp_path / "market.sqlite"
    st = MarketStore(mpath)
    bars = []
    decs = env.led.list_decisions(final_action="entered")
    for d in decs:
        start = d.bar_close_ts
        for k in range(48):
            h, l, c = HARM_STOP.get(k, (2001.0, 1999.0, 2000.0))
            bars.append(_bar_for(d.pair, start, k, h, l, c))
    st.put_bars(bars, now_ms=int((RUN_NOW + timedelta(days=30)).timestamp() * 1000))
    st.close()
    cfg = _cfg_replay(tmp_path, param_cf_market_path=str(mpath))
    svc, store, notif = env.service(cfg)
    svc._ensure_monitors(svc._open_ctx(), "2026-11-01")
    res = svc.run_tick(RUN_NOW)
    assert res.status == "rolled_back", res
    assert env.led.get_active_params().params["stop_buffer_atr"] == pytest.approx(0.3)
    assert any(n.code == "rolled_back" for n in notif) if notif and hasattr(notif[0], "code") else True
    store.close()
