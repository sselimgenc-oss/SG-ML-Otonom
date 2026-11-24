"""24.11 kullanici karari: cikis kipleri (basa-bas / kismi) 15 dk karar adiminda. Karsi-olgu oynatimi (`replay_trail(step_15m=True)`)
ve motor (`target_mode="resting"`, 15 dk adim) AYNI sonucu verir; `step_15m=False` (varsayilan) eski 1h-kapanisi davranisini AYNEN korur.
Sentetik, elle hesapli yollar; kilitli donem disi."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from exit_cf_support import HR, M15, NOW_MS, T0_MS, build
from test_engine_05_spec import BTC, M1, Env
from test_engine_05_spec import T0 as ENGINE_T0

from trader_core import exit_counterfactual as EC
from trader_core import exit_modes as XM
from trader_engine.types import MinuteBar

BE = XM.from_flags(True, False)
PT = XM.from_flags(False, True)
M15M = 15 * M1


def replay(side, hours, *, modes, step_15m, entry=100.0, stop=98.0, atr=2.0, slip_stop=0.0, slip_exit=0.0, regime="trend_up", m15=None):
    h1, m15d = build(hours, atr=atr, regime=regime, m15_override=m15)
    return EC.replay_trail(side=side, entry_price=entry, initial_stop=stop, entry_ms=T0_MS, trail_atr=3.0, h1=h1, m15=m15d,
                           now_ms=NOW_MS, slip_exit_bps=slip_exit, slip_stop_bps=slip_stop, modes=modes, step_15m=step_15m)


# ----------------------------------------------------------------------------------------------- oynatim: elle hesap
HOUR_BE = [(100, 103, 99, 99.5), (99.5, 99.5, 99.5, 99.5)]       # tepe 2. mumda (103), sonra 99'a doner; 1s kapanisi 99.5


def test_step_15m_kapaliyken_eski_yol_bayt_bayt_ayni():
    a = replay("long", HOUR_BE, modes=BE, step_15m=False)
    h1, m15 = build(HOUR_BE, atr=2.0)
    b = EC.replay_trail(side="long", entry_price=100.0, initial_stop=98.0, entry_ms=T0_MS, trail_atr=3.0, h1=h1, m15=m15, now_ms=NOW_MS,
                        slip_exit_bps=0.0, slip_stop_bps=0.0, modes=BE)
    assert (a.reason, a.exit_price, a.exit_ms, a.partial_ms) == (b.reason, b.exit_price, b.exit_ms, b.partial_ms)
    assert a.reason == "trail_stop" and a.exit_price == 99.5 and a.exit_ms == T0_MS + HR            # 1h kapanisi: BE ancak orada, piyasa cikisi


def test_basabas_15dk_adiminda_ayni_saat_icinde_tasinir_ve_stopta_kapanir():
    r = replay("long", HOUR_BE, modes=BE, step_15m=True)
    assert r.reason == "trail_stop" and r.exit_price == pytest.approx(100.0 * 1.0015)
    assert r.exit_ms == T0_MS + 2 * M15                                          # tepe sonrasi ilk mum (3.): BE stopu orada vurulur


def test_basabas_15dk_ufuk_ve_tetik_alti_degismez():
    low = [(100, 101.9, 99, 99.5), (99.5, 99.5, 99.5, 99.5)]                       # +0.95R < +1R: basa-bas yok
    a, b = replay("long", low, modes=BE, step_15m=True), replay("long", low, modes=None, step_15m=True)
    assert (a.reason, a.exit_price, a.exit_ms) == (b.reason, b.exit_price, b.exit_ms)


def test_kismi_15dk_adiminda_sonraki_15dk_acilisinda_dolar():
    hours = [(100, 103.5, 100.5, 102.0), (102.0, 102.0, 97.0, 97.0)]
    r = replay("long", hours, modes=PT, step_15m=True)
    assert (r.partial_ms, r.partial_price, r.partial_frac) == (T0_MS + 2 * M15, 103.5, 0.5)   # 2. mum +1,75R; 3. mum acilisi
    old = replay("long", hours, modes=PT, step_15m=False)
    assert old.partial_ms == T0_MS + HR                                              # eski: 1h kapanisindan sonraki ilk acilis


def test_kismi_adet_yuvarlama_ve_min_adet_15dk_adiminda_da_motorla_ayni():
    hours = [(100, 103.5, 100.5, 102.0), (102.0, 102.0, 97.0, 97.0)]
    h1, m15 = build(hours, atr=2.0)
    kw = dict(side="long", entry_price=100.0, initial_stop=98.0, entry_ms=T0_MS, trail_atr=3.0, h1=h1, m15=m15, now_ms=NOW_MS,
              slip_exit_bps=0.0, slip_stop_bps=0.0, modes=PT, step_15m=True)
    r = EC.replay_trail(**kw, qty=6.369, lot_rules=(0.001, 0.001, 5.0))
    assert r.partial_frac == pytest.approx(XM.partial_qty(6.369, 0.5, 0.001, 0.001, 5.0, 103.5) / 6.369)
    skip = EC.replay_trail(**kw, qty=0.003, lot_rules=(0.001, 0.001, 5.0))             # kalan/kapanan min adet altinda: kismi atlanir
    assert skip.partial_ms is None


def test_surum_ayrimi_15dk_satirlari_ayri_surumde(tmp_path):
    """15 dk oynatim `MODES_VERSION_15M` (3) ile yazilir; eski (2) satirlari silinmez; `have_modes` surumu ayirir."""
    import exit_cf_support as S
    assert EC.MODES_VERSION_15M > EC.MODES_VERSION
    store = EC.ExitCfStore(str(tmp_path / "cf.sqlite"))
    try:
        assert store.have_modes("learner", "paper", "") == {}
        assert store.have_modes("learner", "paper", "", EC.MODES_VERSION_15M) == {}
        row = EC._mrow(S.trade(), "learner", "off", 3.0, datetime(2025, 6, 1, tzinfo=timezone.utc), "last",  # noqa: SLF001
                       {}, T0_MS, None, None, "no_data", None, EC.MODES_VERSION_15M)
        assert row["version"] == 3
        assert store.insert_modes([row]) == 1
        assert store.have_modes("learner", "paper", "", EC.MODES_VERSION_15M) == {1: {"off"}}
        assert store.have_modes("learner", "paper", "") == {}                                # eski surum bu satiri gormez
    finally:
        store.close()


# ----------------------------------------------------------------------------------------------- motor <-> oynatim parite
def _mbar(ts, o, h, l, c):
    return MinuteBar(BTC, ts, 60, o, h, l, c, o, h, l, c, 1.0)


def _engine_run(tmp, modes):
    env = Env(tmp, target_mode="resting", exit_modes=modes)
    env.start()
    env.engine.step_tf = "15m"
    env.engine._multi_tf = True
    env.open_pos(BTC, ENGINE_T0, setup="T1", entry=100.0, stop=98.0, tf="1h")
    return env


def _feed(env, minutes):
    from trader_engine.marketdata.sources import MinuteStep
    for k, (o, h, l, c) in enumerate(minutes):
        ts = ENGINE_T0 + k * M1
        if k == 0:
            continue                                                # giris dakikasi open_pos icinde islendi
        env.set_clock(ts + M1)
        env.engine.process_step(MinuteStep(ts, {BTC: _mbar(ts, o, h, l, c)}))
        if (k + 1) % 15 == 0:                                       # 15 dk karar adimi (bar kapanisi)
            env.decide(ENGINE_T0 + (k + 1) * M1)


def test_motor_ve_oynatim_basabas_ayni_neden_ve_fiyat(tmp_path):
    """Motor (kagit, 15 dk adim) ve oynatim (step_15m): 1. 15 dk'da +1.5R tepe, 2. 15 dk'da dusus -> basa-bas stopu (100.15) bar ici vurulur."""
    env = _engine_run(tmp_path, {"default": {"breakeven": True}})
    minutes = [(100, 100, 100, 100)] * 10 + [(100, 103, 100, 103)] + [(103, 103, 103, 103)] * 4 + [(103, 103, 103, 103)] * 5 \
        + [(103, 103, 99, 99)] + [(99, 99, 99, 99)] * 30
    _feed(env, minutes)
    t = env.real_ledger.get_trade(1)
    assert t is not None and t.exit_reason == "trail_stop"
    rep = replay("long", [(100, 103, 99, 99.0), (99.0, 99.0, 99.0, 99.0)], modes=BE, step_15m=True, slip_stop=5.0, entry=t.entry_price,
                 m15={T0_MS: (100, 103, 100, 103), T0_MS + M15: (103, 103, 99, 99), T0_MS + 2 * M15: (99, 99, 99, 99),
                      T0_MS + 3 * M15: (99, 99, 99, 99)})
    assert rep.reason == t.exit_reason == "trail_stop"
    assert t.exit_price == pytest.approx(rep.exit_price, abs=0.011)          # ayni stop fiyati (kayma 5 bps, tick yuvarlama farki <= 1 tick)
    assert t.exit_price == pytest.approx(t.entry_price * 1.0015 * (1 - 0.0005), abs=0.02)
    env.close()


def test_motor_ve_oynatim_kismi_ayni_anda_ve_fiyatta(tmp_path):
    env = _engine_run(tmp_path, {"default": {"partial": True}})
    minutes = [(100, 100, 100, 100)] * 10 + [(100, 103.5, 100, 103.5)] + [(103.5, 103.5, 103.5, 103.5)] * 20
    _feed(env, minutes)
    pk = env.state.kv_get("partial:1")
    assert pk["state"] == "done"
    rep = replay("long", [(100, 103.5, 100, 103.5), (103.5, 103.5, 97, 97)], modes=PT, step_15m=True, slip_exit=2.0,
                 m15={T0_MS: (100, 103.5, 100, 103.5), T0_MS + M15: (103.5, 103.5, 103.5, 103.5)})
    assert rep.partial_ms == T0_MS + M15                                      # 1. 15 dk kapanisindan sonraki ilk acilis
    assert datetime.fromisoformat(pk["ts"].replace("Z", "+00:00")) == ENGINE_T0 + M15M       # replay ile ayni: 1. 15 dk kapanisindan sonraki ilk dakika
    assert pk["price"] == pytest.approx(rep.partial_price, abs=0.1)
    env.close()


# ----------------------------------------------------------------------------------------------- en iyi uc: last serisi; surum secimi
def test_step_15m_en_iyi_uc_last_serisinden_stop_vurusu_markta():
    """Mark serisinde tepe yok (101), last serisinde 103 (+1,5R): basa-bas yalniz last serisi verilirse tetiklenir (motor mfe/mae = last)."""
    hours = [(100, 101, 99, 99.5), (99.5, 99.5, 99.5, 99.5)]
    h1, m15 = build(hours, atr=2.0)
    m15[T0_MS + M15] = (100, 101, 100, 100.5)                     # mark: tepe yalniz 101
    m15[T0_MS + 2 * M15] = (100.5, 100.5, 99, 99)
    last = dict(m15)
    last[T0_MS + M15] = (100, 103, 100, 100.5)                    # last: tepe 103
    kw = dict(side="long", entry_price=100.0, initial_stop=98.0, entry_ms=T0_MS, trail_atr=3.0, h1=h1, m15=m15, now_ms=NOW_MS,
              slip_exit_bps=0.0, slip_stop_bps=0.0, modes=BE, step_15m=True)
    plain = EC.replay_trail(**kw)
    with_last = EC.replay_trail(**kw, m15_best=last)
    assert plain.exit_price != pytest.approx(100.15) and with_last.exit_price == pytest.approx(100.0 * 1.0015)
    assert with_last.reason == "trail_stop" and with_last.exit_ms == T0_MS + 2 * M15


def test_okuyucu_surumu_aktif_target_mode_a_gore_secer(tmp_path):
    import json

    import exit_cf_support as S
    cfgd = tmp_path / "cfg"
    cfgd.mkdir()
    (cfgd / "engine.base.json").write_text(json.dumps({"target_mode": "bar_close"}))
    assert EC.modes_version_from_config(cfgd) == EC.MODES_VERSION
    (cfgd / "engine.paper.json").write_text(json.dumps({"target_mode": "resting"}))
    assert EC.modes_version_from_config(cfgd) == EC.MODES_VERSION_15M
    assert EC.modes_version_from_config(tmp_path / "yok") is None
    store = EC.ExitCfStore(str(tmp_path / "cf.sqlite"))
    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    try:
        rows = []
        for tid, ver, on_r in ((1, EC.MODES_VERSION, 0.5), (2, EC.MODES_VERSION_15M, 0.9)):
            for var, net in (("off", 0.0), ("breakeven", on_r), ("partial", on_r)):
                r = EC._mrow(S.trade(trade_id=tid), "learner", var, 3.0, now, "last", {}, T0_MS, None, None, "stop", None, ver)   # noqa: SLF001
                r.update(net_r=net, window_end_ts="2025-01-10T00:00:00.000Z", censored=0)
                rows.append(r)
        assert store.insert_modes(rows) == 6
    finally:
        store.close()
    db = str(tmp_path / "cf.sqlite")
    v2 = EC.deltas_modes(db, "learner", now=now, days=300, mode="breakeven", version=EC.MODES_VERSION)
    v3 = EC.deltas_modes(db, "learner", now=now, days=300, mode="breakeven", version=EC.MODES_VERSION_15M)
    legacy = EC.deltas_modes(db, "learner", now=now, days=300, mode="breakeven")            # surum verilmezse: eski yol (MAX)
    assert [r["trade_id"] for r in v2] == [1] and [r["trade_id"] for r in v3] == [2]
    assert [r["trade_id"] for r in legacy] == [2]
    assert EC.modes_version_for("resting") == 3 and EC.modes_version_for("bar_close") == 2
