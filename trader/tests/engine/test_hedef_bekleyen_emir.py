"""24.11 kullanici karari: hedef bekleyen emir (`target_mode="resting"`); basa-bas tasima ve kismi kar alma 15 dk karar adiminda.
Kagit motoru: hedef emri bar ici (1 dk) dolar; ayni dakikada stop da degerse stop once; hedefi atlayan bosluk acilista dolar.
Sentetik veri; var/history yok. Canli yol: tests/engine/test_hedef_bekleyen_emir_canli.py."""
from __future__ import annotations

from datetime import timedelta

import pytest
from test_engine_05_spec import BTC, H, M1, T0, Env

from trader_engine.config import ConfigError

M15 = timedelta(minutes=15)
TARGET = 104.0
BOTH = {"default": {"breakeven": True, "partial": True}}


def renv(tmp, *, target_mode="resting", modes=None, multi=False, **over):
    """Kagit motoru + R1 (hedef kipi) pozisyonu icin duzenek. `multi`: motor 15 dk karar adimli (cok zaman dilimli) calisir."""
    cfg = {"target_mode": target_mode, **over}
    if modes is not None:
        cfg["exit_modes"] = modes
    env = Env(tmp, **cfg)
    env.start()
    if multi:
        env.engine.step_tf = "15m"
        env.engine._multi_tf = True
    return env


R1_KW = dict(regime="range", rh=106.0, rl=94.0, wick_ratio=0.5, rr=2.0, edge_dist_atr=0.5)    # R1 defter ozellikleri (range rejimi: rh/rl dolu)


def open_r1(env, tf="1h", target=TARGET, stop=98.0, **kw):
    return env.open_pos(BTC, T0, setup="R1", entry=100.0, stop=stop, planned_target=target, tf=tf, **{**R1_KW, **kw})


def flat(env, a, b, price=100.0):
    """[a, b) dakikalari sabit fiyat."""
    t = a
    while t < b:
        env.step(t, pairs=(BTC,), price=price, hi=price, lo=price)
        t += M1


def broker_orders(env, role):
    return [o for o in env.broker._orders.values() if o.role == role]


def trade(env, tid):
    return env.real_ledger.get_trade(tid)


# ----------------------------------------------------------------------------------------------- yapilandirma
def test_target_mode_resting_gecerli_bar_close_korunur_digeri_reddedilir(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    from test_engine_05_spec import make_cfg
    assert make_cfg(tmp_path / "a", target_mode="resting").target_mode == "resting"
    assert make_cfg(tmp_path / "b").target_mode == "bar_close"                       # taban dosya degismedi
    with pytest.raises(ConfigError, match="target_mode"):
        make_cfg(tmp_path / "c", target_mode="limit")


# ----------------------------------------------------------------------------------------------- giriste bekleyen hedef emri
def test_giriste_hedef_emri_kurulur_stop_ile_birlikte(tmp_path):
    env = renv(tmp_path)
    p = open_r1(env)
    tg = broker_orders(env, "target")
    assert len(tg) == 1 and tg[0].status == "new" and tg[0].reduce_only and tg[0].order_side == "sell"
    assert tg[0].trigger_price == TARGET and tg[0].qty == pytest.approx(p.qty)
    assert len(broker_orders(env, "stop")) == 1
    assert env.state.kv_get(f"target:{p.trade_id}")["state"] == "active"
    row = env.state.get_order(tg[0].client_id)
    assert row.role == "target" and row.status == "accepted" and row.trade_id == p.trade_id
    env.close()


def test_bar_close_modunda_hedef_emri_kurulmaz(tmp_path):
    env = renv(tmp_path, target_mode="bar_close")
    p = open_r1(env)
    assert broker_orders(env, "target") == [] and env.state.kv_get(f"target:{p.trade_id}") is None
    env.close()


def test_hedefsiz_ve_trail_kurulumunda_hedef_emri_yok(tmp_path):
    env = renv(tmp_path)
    env.open_pos(BTC, T0, setup="T1", entry=100.0, stop=98.0, tf="1h")                   # T1 = iz suren stop kipi (hedef yok)
    assert broker_orders(env, "target") == []
    env.close()


def test_hedef_tick_yuvarlama_girise_dogru(tmp_path):
    env = renv(tmp_path)
    open_r1(env, target=104.0004)                    # tick 0.01: long hedef asagi -> 104.0
    assert broker_orders(env, "target")[0].trigger_price == pytest.approx(104.0)
    env.close()


# ----------------------------------------------------------------------------------------------- bar ici dolum
def test_hedef_bar_ici_dolar_hedef_fiyatinda_ve_stop_iptal(tmp_path):
    env = renv(tmp_path)
    p = open_r1(env)
    flat(env, T0 + M1, T0 + 10 * M1)
    t_hit = T0 + 10 * M1
    env.step(t_hit, pairs=(BTC,), price=101.0, hi=104.5, lo=100.5)          # yalniz bu dakika hedefe degdi; kapanis hedefin altinda
    t = trade(env, p.trade_id)
    assert t.exit_reason == "target" and t.planned_exit == TARGET
    assert t.exit_price == pytest.approx(TARGET * (1 - 2e-4), abs=0.1)        # hedef fiyati - cikis kaymasi (2 bps); bar kapanisi/acilisi DEGIL
    assert t.exit_price < TARGET and t.exit_price > 103.5
    assert env.state.get_position(p.trade_id).status == "closed"
    assert broker_orders(env, "stop")[0].status == "canceled"                 # kardes koruyucu emir iptal
    assert env.engine.counters()["target_fills"] == 1
    env.close()


def test_hedef_ayni_dakikada_stop_ve_hedef_degerse_stop_once(tmp_path):
    env = renv(tmp_path)
    p = open_r1(env)
    flat(env, T0 + M1, T0 + 5 * M1)
    env.step(T0 + 5 * M1, pairs=(BTC,), price=100.0, hi=105.0, lo=97.0)     # ayni dakikada hem 98 hem 104
    t = trade(env, p.trade_id)
    assert t.exit_reason == "stop"
    assert broker_orders(env, "target")[0].status == "canceled"
    env.close()


def test_hedefi_atlayan_bosluk_acilista_dolar(tmp_path):
    env = renv(tmp_path)
    p = open_r1(env)
    flat(env, T0 + M1, T0 + 5 * M1)
    env.step(T0 + 5 * M1, pairs=(BTC,), price=107.0, hi=108.0, lo=106.5)    # acilis 107 > hedef 104
    t = trade(env, p.trade_id)
    assert t.exit_reason == "target"
    assert t.exit_price == pytest.approx(107.0 * (1 - 2e-4), abs=0.1)         # acilis fiyati (hedef degil)
    assert t.exit_price > TARGET
    env.close()


def test_short_hedef_bar_ici_ve_tick_yuvarlama(tmp_path):
    env = renv(tmp_path)
    p = env.open_pos(BTC, T0, setup="R1", side="short", entry=100.0, stop=102.0, planned_target=96.0004, tf="1h", **R1_KW)
    tg = broker_orders(env, "target")[0]
    assert tg.order_side == "buy" and tg.trigger_price == pytest.approx(96.01)      # short: yukari (girise dogru)
    flat(env, T0 + M1, T0 + 3 * M1)
    env.step(T0 + 3 * M1, pairs=(BTC,), price=97.0, hi=99.0, lo=95.5)
    t = trade(env, p.trade_id)
    assert t.exit_reason == "target" and t.exit_price == pytest.approx(96.01 * (1 + 2e-4), abs=0.1)
    env.close()


# ----------------------------------------------------------------------------------------------- bar kapanisi yedegi
def test_hedef_aktifken_bar_kapanisinda_hedef_kontrolu_yok_zaman_durdurma_var(tmp_path):
    """Hedef bekleyen emirdeyken kendi tf kapanisinda hedef piyasa cikisi VERILMEZ; zaman durdurma yine calisir."""
    import numpy as np

    from trader_engine.position_manager import ExitContext
    env = renv(tmp_path)
    p = open_r1(env)
    D1 = T0 + H
    flat(env, T0 + M1, D1)
    env.src.ctx[(BTC, D1)] = ExitContext(bar_close_ts=D1, highs=np.array([105.0]), lows=np.array([99.0]), atrs=np.array([1.0]),
                                         regime_last="trend_up", last_close=101.0, n_closed=1)   # bar hedefe degdi ama emir henuz dolmadi (sentetik)
    env.decide(D1)
    assert env.state.get_position(p.trade_id).status == "open"                  # bar_close yolu olsaydi cikis verilirdi
    env.src.ctx[(BTC, D1 + H)] = ExitContext(bar_close_ts=D1 + H, highs=np.array([101.0]), lows=np.array([99.0]),
                                             atrs=np.array([1.0]), regime_last="trend_up", last_close=100.0, n_closed=200)
    env.decide(D1 + H)
    env.step(D1 + H, pairs=(BTC,), price=100.0)
    t = trade(env, p.trade_id)
    assert t.exit_reason == "time_stop"
    env.close()


def test_bar_close_modunda_hedef_eski_yolla_piyasada_kapanir(tmp_path):
    import numpy as np

    from trader_engine.position_manager import ExitContext
    env = renv(tmp_path, target_mode="bar_close")
    p = open_r1(env)
    D1 = T0 + H
    flat(env, T0 + M1, D1)
    env.src.ctx[(BTC, D1)] = ExitContext(bar_close_ts=D1, highs=np.array([105.0]), lows=np.array([99.0]), atrs=np.array([1.0]),
                                         regime_last="trend_up", last_close=101.0, n_closed=1)
    env.decide(D1)
    env.step(D1, pairs=(BTC,), price=101.0)
    t = trade(env, p.trade_id)
    assert t.exit_reason == "target" and t.exit_price == pytest.approx(101.0, abs=0.1)     # piyasa (sonraki acilis), hedef fiyati degil
    env.close()


def test_hedef_girisle_ayni_anda_asilmissa_piyasada_target_cikisi(tmp_path):
    """Bekleyen emir semantigi: hedef zaten asilmis (would_trigger) => hemen tetiklenir: piyasada `target` cikisi (kagit = canli)."""
    env = renv(tmp_path)
    p = open_r1(env, target=99.0)                                           # long hedef mark'in (100) altinda
    assert env.engine.counters()["target_instant_exit"] == 1
    assert env.state.kv_get(f"target:{p.trade_id}")["state"] == "hit"
    env.step(T0 + M1, pairs=(BTC,), price=100.0)
    t = trade(env, p.trade_id)
    assert t.exit_reason == "target" and t.planned_exit == 99.0
    assert [o.status for o in broker_orders(env, "stop")] == ["canceled"]
    env.close()


def test_hedef_kurulamazsa_bar_close_yedegi_calisir(tmp_path):
    """Gecici/kalici red (would_trigger DEGIL): durum `failed` (n=1), pozisyon kapanmaz, hedef bar kapanisinda piyasada denetlenir."""
    import numpy as np

    from trader_engine.position_manager import ExitContext
    from trader_engine.types import OrderResult
    env = renv(tmp_path)
    env.broker.place_target = lambda req: OrderResult(status="rejected", client_id=req.client_id, reason="fault_injected",
                                                       ts=env.clock.now())
    p = open_r1(env)
    assert [o for o in broker_orders(env, "target") if o.status == "new"] == []
    tk = env.state.kv_get(f"target:{p.trade_id}")
    assert tk["state"] == "failed" and tk["n"] == 1
    assert env.state.get_position(p.trade_id).status == "open"
    D1 = T0 + H
    flat(env, T0 + M1, D1)
    env.src.ctx[(BTC, D1)] = ExitContext(bar_close_ts=D1, highs=np.array([105.0]), lows=np.array([99.5]), atrs=np.array([1.0]),
                                         regime_last="trend_up", last_close=104.5, n_closed=1)
    env.decide(D1)
    env.step(D1, pairs=(BTC,), price=104.5)
    assert trade(env, p.trade_id).exit_reason == "target"
    env.close()


def test_kagit_hedef_dolumu_last_fiyat_yolunu_asamaz(tmp_path):
    """Tetik mark ile; mark yuksek hedefe degdi ama last high hedefin altinda: dolum min(hedef, last_high) (muhafazakar)."""
    from trader_engine.types import MinuteBar
    env = renv(tmp_path)
    p = open_r1(env)
    flat(env, T0 + M1, T0 + 5 * M1)
    ts = T0 + 5 * M1
    env.set_clock(ts + M1)
    from trader_engine.marketdata.sources import MinuteStep
    bar = MinuteBar(BTC, ts, 60, 101.0, 103.5, 100.5, 101.0, 101.0, 105.0, 100.5, 101.0, 1.0)     # last_h 103.5 < hedef 104 <= mark_h 105
    env.engine.process_step(MinuteStep(ts, {BTC: bar}))
    t = trade(env, p.trade_id)
    assert t.exit_reason == "target"
    assert t.exit_price == pytest.approx(103.5 * (1 - 2e-4), abs=0.05) and t.exit_price < TARGET
    env.close()


def test_basabas_would_trigger_ayni_adimda_pozisyon_kapaniyorsa_adim_biter(tmp_path):
    """15 dk adiminda basa-bas stopu zaten asilmis (would_trigger): piyasa cikisi tek kez; ikinci cikis/stop yok."""
    env = renv(tmp_path, modes={"default": {"breakeven": True}}, multi=True)
    p = env.open_pos(BTC, T0, setup="T1", entry=100.0, stop=98.0, tf="1d")
    flat(env, T0 + M1, T0 + 10 * M1, price=103.0)
    flat(env, T0 + 10 * M1, T0 + 15 * M1, price=99.5)                               # en iyi uc 103, son fiyat basa-bas stopunun altinda
    env.decide(T0 + M15)
    assert env.state.get_position(p.trade_id).status in ("closing", "closed")
    exits = [r for r in env.state.orders_for_trade(p.trade_id) if r.role == "exit"]
    assert len(exits) == 1
    env.close()


# ----------------------------------------------------------------------------------------------- baska yolla kapanista iptal
def test_stop_ile_kapanista_hedef_iptal(tmp_path):
    env = renv(tmp_path)
    p = open_r1(env)
    flat(env, T0 + M1, T0 + 4 * M1)
    env.step(T0 + 4 * M1, pairs=(BTC,), price=97.0, hi=100.0, lo=96.5)
    assert trade(env, p.trade_id).exit_reason == "stop"
    assert [o.status for o in broker_orders(env, "target")] == ["canceled"]
    assert env.state.get_order(broker_orders(env, "target")[0].client_id).status == "canceled"
    env.close()


def test_zaman_durdurma_ile_kapanista_hedef_iptal(tmp_path):
    import numpy as np

    from trader_engine.position_manager import ExitContext
    env = renv(tmp_path)
    p = open_r1(env)
    D1 = T0 + H
    flat(env, T0 + M1, D1)
    env.src.ctx[(BTC, D1)] = ExitContext(bar_close_ts=D1, highs=np.array([101.0]), lows=np.array([99.0]), atrs=np.array([1.0]),
                                         regime_last="trend_up", last_close=100.0, n_closed=500)
    env.decide(D1)
    env.step(D1, pairs=(BTC,), price=100.0)
    assert trade(env, p.trade_id).exit_reason == "time_stop"
    assert [o.status for o in broker_orders(env, "target")] == ["canceled"]
    assert [o.status for o in broker_orders(env, "stop")] == ["canceled"]
    env.close()


# ----------------------------------------------------------------------------------------------- kismi sonrasi yeniden boyutlandirma
def test_kismi_sonrasi_hedef_kalan_adede_yeniden_kurulur(tmp_path):
    env = renv(tmp_path, modes={"default": {"partial": True}}, multi=True)
    p = open_r1(env, tf="1h", target=110.0)                                 # hedef uzak; kismi +1.5R = 103
    q0 = p.qty
    flat(env, T0 + M1, T0 + 14 * M1, price=103.5)
    env.step(T0 + 14 * M1, pairs=(BTC,), price=103.5, hi=103.5, lo=103.5)
    D = T0 + M15                                                            # kendi tf (1s) kapanisi DEGIL: 15 dk adimi
    env.decide(D)
    env.step(D, pairs=(BTC,), price=103.5, hi=103.5, lo=103.5)             # kismi piyasa emri dolar
    cur = env.state.get_position(p.trade_id)
    assert cur.status == "open" and cur.qty < q0
    tg = broker_orders(env, "target")
    live = [o for o in tg if o.status == "new"]
    assert len(tg) == 2 and len(live) == 1 and live[0].qty == pytest.approx(cur.qty)
    assert [o.status for o in tg if o.status != "new"] == ["canceled"]
    assert env.state.kv_get(f"target:{p.trade_id}")["cid"] == live[0].client_id
    assert env.engine.counters()["target_resized"] == 1
    sp = [o for o in broker_orders(env, "stop") if o.status == "new"]
    assert len(sp) == 1 and sp[0].qty == pytest.approx(cur.qty)             # stop da kalan adede (mevcut davranis)
    # kalan parca hedefte dolar: kalan adet, hedef fiyatinda
    env.step(D + M1, pairs=(BTC,), price=105.0, hi=111.0, lo=105.0)
    t = trade(env, p.trade_id)
    assert t.exit_reason == "target"
    env.close()


# ----------------------------------------------------------------------------------------------- 15 dk adiminda basa-bas / kismi
def _be_scenario(tmp, target_mode):
    env = renv(tmp, target_mode=target_mode, modes={"default": {"breakeven": True}}, multi=True)
    p = env.open_pos(BTC, T0, setup="T1", entry=100.0, stop=98.0, tf="1d")           # 1g islem
    flat(env, T0 + M1, T0 + 14 * M1, price=103.0)                                   # en iyi uc 103 >= +1R (102)
    env.step(T0 + 14 * M1, pairs=(BTC,), price=103.0, hi=103.0, lo=103.0)
    env.decide(T0 + M15)                                                            # 15 dk adimi; 1g kapanisi degil
    return env, p


def test_1g_islemde_basabas_15dk_adiminda_tetiklenir(tmp_path):
    env, p = _be_scenario(tmp_path, "resting")
    cur = env.state.get_position(p.trade_id)
    assert cur.current_stop == pytest.approx(cur.entry_price * 1.0015, abs=0.1)
    sp = [o for o in broker_orders(env, "stop") if o.status == "new"]
    assert len(sp) == 1 and sp[0].trigger_price == pytest.approx(cur.current_stop)
    assert env.engine.counters()["be_moves_15m"] == 1
    env.decide(T0 + M15)                                                            # ayni adimi tekrar: ikinci tasima yok
    assert env.engine.counters()["be_moves_15m"] == 1
    env.close()


def test_bar_close_modunda_1g_islemde_basabas_kendi_tf_kapanisini_bekler(tmp_path):
    (tmp_path / "bc").mkdir()
    env, p = _be_scenario(tmp_path / "bc", "bar_close")
    cur = env.state.get_position(p.trade_id)
    assert cur.current_stop == 98.0                                                  # eski davranis: 15 dk adiminda tasima YOK
    env.close()


def test_1g_islemde_kismi_15dk_adiminda_tetiklenir(tmp_path):
    env = renv(tmp_path, modes={"default": {"partial": True}}, multi=True)
    p = env.open_pos(BTC, T0, setup="T1", entry=100.0, stop=98.0, tf="1d")
    flat(env, T0 + M1, T0 + 14 * M1, price=103.5)
    env.step(T0 + 14 * M1, pairs=(BTC,), price=103.5, hi=103.5, lo=103.5)
    env.decide(T0 + M15)
    env.step(T0 + M15, pairs=(BTC,), price=103.5)
    cur = env.state.get_position(p.trade_id)
    assert cur.status == "open" and cur.qty < p.qty
    assert env.state.kv_get(f"partial:{p.trade_id}")["state"] == "done"
    env.close()


def test_basabas_henuz_tetiklenmediyse_15dk_adiminda_dokunmaz(tmp_path):
    env = renv(tmp_path, modes={"default": {"breakeven": True}}, multi=True)
    p = env.open_pos(BTC, T0, setup="T1", entry=100.0, stop=98.0, tf="1d")
    flat(env, T0 + M1, T0 + 15 * M1, price=101.0)                                   # +0.5R < +1R
    env.decide(T0 + M15)
    assert env.state.get_position(p.trade_id).current_stop == 98.0
    assert env.engine.counters().get("be_moves_15m", 0) == 0
    env.close()


def test_kendi_tf_kapanisinda_basabas_iz_suren_stopla_birlikte(tmp_path):
    """Kendi tf kapanisinda (1s) basabas once, iz suren stop sonra: stop yalniz sikilasir, gevsemez (exit_policy_loosen sayilmaz)."""
    import numpy as np

    from trader_engine.position_manager import ExitContext
    env = renv(tmp_path, modes={"default": {"breakeven": True}})
    p = env.open_pos(BTC, T0, setup="T1", entry=100.0, stop=98.0, tf="1h")
    D1 = T0 + H
    flat(env, T0 + M1, D1, price=103.0)
    env.src.ctx[(BTC, D1)] = ExitContext(bar_close_ts=D1, highs=np.array([103.0]), lows=np.array([99.5]), atrs=np.array([1.0]),
                                         regime_last="trend_up", last_close=103.0, n_closed=1)
    env.decide(D1)
    cur = env.state.get_position(p.trade_id)
    assert cur.current_stop == pytest.approx(cur.entry_price * 1.0015, abs=0.1)
    assert env.engine.counters().get("exit_policy_loosen", 0) == 0
    env.close()
