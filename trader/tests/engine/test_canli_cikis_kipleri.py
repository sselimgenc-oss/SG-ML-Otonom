"""Faz 2 (23.11 kullanici karari: canli = kagit): canli motor cikis kiplerini kagitla AYNI uygular.
24.11 kullanici karari: risk kademesi kaldirildi, risk ayardan (%1): giris adedi 13.4 (eski 4.8), kismi 4.4, kalan 9.0.
Duzenek: gercek LiveBroker + SignedRestClient + FakeExchange (HTTP duzeyi) + gercek Engine (mode='live', kademe denetimli)."""
from __future__ import annotations

import dataclasses as dc
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
from fake_exchange import FakeResp
from test_dd8_spec import DEnv
from test_engine_05_spec import BTC, Env
from test_engine_live_spec import DEC, H, SYM, XRP
from trader_core import exit_modes as XM
from trader_engine.order_manager import make_client_id
from trader_engine.position_manager import ExitContext, apply_exit_modes, partial_due
from trader_engine.types import Position

UTC = timezone.utc


class CEnv(DEnv):
    def ex_qty(self) -> Decimal:
        p = self.ex.pos.get(SYM)
        return p["amt"] if p else Decimal(0)


D2, D3 = DEC + H, DEC + 2 * H
BOTH = {"default": {"breakeven": True, "partial": {"trigger_r": 1.5, "frac": 0.33}}}
ONLY_BE = {"default": {"breakeven": True}}
ONLY_PT = {"default": {"partial": {"trigger_r": 1.5, "frac": 0.33}}}
PT_HALF = {"default": {"partial": True}}


def ctx(D, high, last_close=2.12):
    """XRP olcegi: giris 2.0, ilk stop 1.9 (R=0.1). ATR buyuk: iz suren stop sikilasmaz (yalniz cikis kipleri calisir)."""
    return ExitContext(bar_close_ts=D, highs=np.array([high]), lows=np.array([2.0]), atrs=np.array([0.5]),
                       regime_last="trend_up", last_close=last_close, n_closed=1)


def mk(tmp, modes, *, notional="1", ex=None, clock=None):
    e = CEnv(tmp, mode="live", ex=ex, clock=clock)
    e.engine.cfg = dc.replace(e.engine.cfg, exit_modes=XM.build_config(modes))
    if ex is None:
        e.ex.symbols[SYM]["notional"] = notional          # kural: min notional (varsayilan 5; XRP 13.4 adet = 26.8$)
    return e.boot()


def restart(old, modes):
    old.close()
    return mk(old.tmp, modes, ex=old.ex, clock=old.clock)


def reduce_markets(e):
    return [q for m, p, q in e.ex.requests if m == "POST" and p == "/fapi/v1/order" and q.get("reduceOnly") == "true"]


def order_writes(e, after=0):
    """(yontem, tur, adet, tetik) sirasi: emir POST/DELETE'leri."""
    out = []
    for m, p, q in e.ex.requests[after:]:
        if p == "/fapi/v1/order" and m == "POST":
            out.append((m, "MARKET", q.get("quantity"), None))
        elif p == "/fapi/v1/algoOrder" and m == "POST":
            out.append((m, "STOP", q.get("quantity"), q.get("triggerPrice") or q.get("stopPrice")))
        elif p == "/fapi/v1/algoOrder" and m == "DELETE":
            out.append((m, "STOP", None, None))
    return out


def trig(a):
    return Decimal(str(a["triggerPrice"]))


# ---------------------------------------------------------------------------------------------- basa-bas stop tasima
def test_basabas_yeni_stop_once_sonra_eski_iptal(tmp_path):
    e = mk(tmp_path, ONLY_BE)
    pos = e.enter()
    assert pos.qty == 13.4 and [trig(a) for a in e.stops()] == [Decimal("1.9")]
    n0 = len(e.ex.requests)
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.11)                   # en iyi uc >= giris + 1R (2.1)
    e.ex.set_mark(SYM, "2.11")
    e.decide(D2)
    w = order_writes(e, n0)
    assert [(m, k) for m, k, *_ in w] == [("POST", "STOP"), ("DELETE", "STOP")], w      # stopsuz an YOK: once yeni, sonra eski
    assert w[0][2] == "13.4" and Decimal(w[0][3]) == Decimal("2.003")                    # giris 2.0 + 15 bps
    st = e.stops()
    assert len(st) == 1 and trig(st[0]) == Decimal("2.003") and st[0]["qty"] == Decimal("13.4")
    p = e.pos()
    assert p.current_stop == pytest.approx(2.003) and p.stop_client_id == st[0]["cid"]
    assert e.state.get_order(make_client_id("learner", "stop", XRP, "long", DEC, 0)).status == "canceled"
    # ayni bar tekrar degerlendirilince ikinci tasima yok (daha siki degil)
    n1 = len(e.ex.requests)
    e.decide(D2)
    assert order_writes(e, n1) == []


def test_basabas_tasima_hatasinda_eski_stop_kalir_ve_sonra_yeniden_denenir(tmp_path):
    e = mk(tmp_path, ONLY_BE)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.11)
    e.src.ctx[(XRP, D3)] = ctx(D3, 2.12)
    e.ex.set_mark(SYM, "2.11")
    old = pos.stop_client_id
    e.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -1111, "msg": "x"}))          # yeni stop reddedilir
    n0 = len(e.ex.requests)
    e.decide(D2)
    assert [(m, k) for m, k, *_ in order_writes(e, n0)] == [("POST", "STOP")]               # eski iptal EDILMEDI
    st = e.stops()
    assert len(st) == 1 and st[0]["cid"] == old and trig(st[0]) == Decimal("1.9")           # pozisyon eski stopla korunur
    assert e.pos().current_stop == 1.9 and e.pos().stop_client_id == old
    assert e.engine.counters()["exit_mode_stop_replace_failed"] == 1
    e.decide(D3)                                                                            # sonraki adimda yeniden dener
    st = e.stops()
    assert len(st) == 1 and trig(st[0]) == Decimal("2.003") and e.pos().current_stop == pytest.approx(2.003)


def test_basabas_would_trigger_piyasada_kapatir_kagitla_ayni(tmp_path):
    e = mk(tmp_path, ONLY_BE)
    e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.11, last_close=2.0)
    e.ex.set_mark(SYM, "2.001")                      # yeni stop 2.003 mark'in USTUNDE: borsa reddeder (anlik tetik)
    e.decide(D2)
    assert e.ex_qty() == 0 and e.state.get_position(1).status in ("closing", "closed")


# ---------------------------------------------------------------------------------------------- kismi kar alma
def test_kismi_adim_yuvarlama_reduceonly_ve_stop_kalan_adede(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)             # >= giris + 1.5R (2.15)
    e.ex.set_mark(SYM, "2.12")
    n0 = len(e.ex.requests)
    e.decide(D2)
    mk_ = reduce_markets(e)
    assert len(mk_) == 1 and mk_[0]["quantity"] == "4.4"          # 13.4 * 0.33 = 4.422 -> adim 0.1 tabani 4.4
    assert XM.partial_qty(13.4, 0.33, 0.1, 0.1, 1.0, 2.12) == 4.4                          # kagitla ayni islev
    w = order_writes(e, n0)
    assert [(m, k) for m, k, *_ in w] == [("POST", "MARKET"), ("POST", "STOP"), ("DELETE", "STOP")], w
    assert w[1][2] == "9"                                       # yeni stop KALAN adede
    p = e.pos()
    assert p.status == "open" and p.qty == pytest.approx(9.0) and e.ex_qty() == Decimal("9")
    st = e.stops()
    assert len(st) == 1 and st[0]["qty"] == Decimal("9") and trig(st[0]) == Decimal("1.9")   # ayni fiyat
    pk = e.state.kv_get(f"partial:{pos.trade_id}")
    assert pk["state"] == "done" and pk["qty"] == 4.4 and pk["price"] == pytest.approx(2.12) and pk["fee"] > 0
    assert e.engine.counters()["partial_fills"] == 1 and e.broker.counters()["partial_exit_events"] == 1
    assert e.state.get_order(pk["cid"]).status == "filled"
    assert e.state.get_order(make_client_id("learner", "stop", XRP, "long", DEC, 0)).status == "canceled"


def test_kismi_min_notional_altinda_atlanir_ve_tekrarlanmaz(tmp_path):
    e = mk(tmp_path, PT_HALF, notional="14")         # 6.7 x 2.0 = 13.4 < 14: kalan/kapanan parca min notional altinda
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16, last_close=2.0)
    e.src.ctx[(XRP, D3)] = ctx(D3, 2.30, last_close=2.3)      # sonraki barda fiyat yukselse de ikinci deneme YOK
    e.ex.set_mark(SYM, "2.12")
    e.decide(D2)
    assert reduce_markets(e) == [] and e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "skipped"
    e.ex.set_mark(SYM, "2.3")
    e.decide(D3)
    assert reduce_markets(e) == [] and e.pos().qty == pytest.approx(13.4)
    assert XM.partial_qty(13.4, 0.5, 0.1, 0.1, 14.0, 2.0) is None                            # kagit kurali (ayni islev)


def test_kismi_yarim_oran_min_notional_uygun_oldugunda_dolar(tmp_path):
    e = mk(tmp_path, PT_HALF, notional="14")        # 6.7 x 2.12 = 14.2 >= 14
    e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16, last_close=2.12)
    e.ex.set_mark(SYM, "2.12")
    e.decide(D2)
    assert [q["quantity"] for q in reduce_markets(e)] == ["6.7"] and e.pos().qty == pytest.approx(6.7)


def test_kismi_ve_basabas_ayni_barda_son_stop_basabas_fiyati_kalan_adette(tmp_path):
    e = mk(tmp_path, BOTH)
    e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.decide(D2)
    st = e.stops()
    assert len(st) == 1 and st[0]["qty"] == Decimal("9") and trig(st[0]) == Decimal("2.003")
    assert e.pos().current_stop == pytest.approx(2.003) and e.ex_qty() == Decimal("9")


def test_kismi_stop_kurulamazsa_eski_stop_kalir_sayac(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.ex.inject("/fapi/v1/algoOrder", FakeResp(400, {"code": -1111, "msg": "x"}))
    e.decide(D2)
    st = e.stops()
    assert len(st) == 1 and st[0]["qty"] == Decimal("13.4")           # eski (genis) stop durur: pozisyon stopsuz kalmaz
    assert e.engine.counters()["partial_stop_resize_failed"] == 1 and e.pos().qty == pytest.approx(9.0)


# ---------------------------------------------------------------------------------------------- yeniden baslatma / idempotans
def test_yeniden_baslatmada_ikinci_kismi_emir_yok(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.decide(D2)
    assert len(reduce_markets(e)) == 1
    e2 = restart(e, ONLY_PT)
    try:
        e2.src.ctx[(XRP, D3)] = ctx(D3, 2.40, last_close=2.4)
        e2.ex.set_mark(SYM, "2.4")
        e2.decide(D3)
        assert len(reduce_markets(e2)) == 1                               # ikinci kismi emir YOK
        p = e2.pos()
        assert p.qty == pytest.approx(9.0) and e2.ex_qty() == Decimal("9")
        assert e2.state.kv_get(f"partial:{pos.trade_id}")["state"] == "done"
        assert len(e2.stops()) == 1 and e2.stops()[0]["qty"] == Decimal("9")
    finally:
        e2.close()


def test_yeniden_baslatmada_basabas_ayni_karar_ikinci_tasima_yok(tmp_path):
    e = mk(tmp_path, ONLY_BE)
    e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.11)
    e.ex.set_mark(SYM, "2.11")
    e.decide(D2)
    e2 = restart(e, ONLY_BE)
    try:
        e2.src.ctx[(XRP, D2)] = ctx(D2, 2.11)
        n0 = len(e2.ex.requests)
        e2.decide(D2)
        assert [w for w in order_writes(e2, n0) if w[0] == "DELETE" or w[1] == "STOP"] == []
        assert len(e2.stops()) == 1 and e2.pos().current_stop == pytest.approx(2.003)
    finally:
        e2.close()


def _crash_after_partial_post(tmp_path):
    """Kismi emir borsada dolmus ama motor olayi isleyemeden dusmus: kv `pending`, emir satiri yok."""
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    cid = make_client_id("learner", "exit", XRP, "long", D2, 1)
    with e.state.tx():
        e.state.kv_set(f"partial:{pos.trade_id}", {"state": "pending", "cid": cid, "qty": 4.4})
    e.ex.set_mark(SYM, "2.12")
    e.ex._fill(SYM, "SELL", Decimal("4.4"), Decimal("2.12"), cid, True)
    return e, pos, cid


def test_yeniden_baslatma_dolmus_kismi_emri_sorgulayip_benimser_tekrar_gondermez(tmp_path):
    e, pos, cid = _crash_after_partial_post(tmp_path)
    e2 = restart(e, ONLY_PT)
    try:
        e2.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
        e2.decide(D2)
        assert reduce_markets(e2) == []                                   # ikinci emir yok
        pk = e2.state.kv_get(f"partial:{pos.trade_id}")
        assert pk["state"] == "done" and pk["qty"] == 4.4 and pk["price"] == pytest.approx(2.12)
        assert e2.pos().qty == pytest.approx(9.0) and e2.engine.counters()["partial_recovered"] == 1
        st = e2.stops()
        assert len(st) == 1 and st[0]["qty"] == Decimal("9")
        e2.decide(D2)                                                      # ikinci degerlendirme: degisiklik yok
        assert e2.pos().qty == pytest.approx(9.0) and reduce_markets(e2) == []
    finally:
        e2.close()


def test_yeniden_baslatma_bulunamayan_kismi_emir_atlanir_tekrar_gonderilmez(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    cid = make_client_id("learner", "exit", XRP, "long", D2, 1)
    with e.state.tx():
        e.state.kv_set(f"partial:{pos.trade_id}", {"state": "pending", "cid": cid, "qty": 4.4})
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.src.ctx[(XRP, D3)] = ctx(D3, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.decide(D2)
    assert e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "pending"          # tek -2013 yetmez
    e.decide(D3)
    assert e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "skipped"
    assert reduce_markets(e) == [] and e.pos().qty == pytest.approx(13.4)


# ---------------------------------------------------------------------------------------------- kapanis: kismi bacak dislanir
@pytest.mark.parametrize("restart_before_close", [False, True])
def test_kismi_sonrasi_stop_kapanisi_yalniz_kalan_adet_ve_karma_fiyat(tmp_path, restart_before_close):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.decide(D2)
    assert e.pos().qty == pytest.approx(9.0)
    if restart_before_close:
        e = restart(e, ONLY_PT)
    try:
        e.ex.set_mark(SYM, "1.85")                                   # stop (1.9) tetiklenir, 9.0 adet kapanir
        e.tick(31)
        e.tick(31)
        p = e.state.get_position(pos.trade_id)
        assert p.status == "closed" and e.ex_qty() == 0
        last = [t for t in e.ex.trades if t["side"] == "SELL"][-1]
        assert Decimal(last["qty"]) == Decimal("9") and Decimal(last["price"]) == Decimal("1.85")
        t = e.real_ledger.get_trade(pos.trade_id)
        blended = (4.4 * 2.12 + 9.0 * 1.85) / 13.4                        # defter tek satir: adet agirlikli karma fiyat
        assert t.exit_reason == "stop" and t.exit_price == pytest.approx(blended)
    finally:
        e.close()


# ---------------------------------------------------------------------------------------------- kagit = canli (ayni tetik, ayni karar)
def _pos(side="long", entry=2.0, stop=1.9, qty=13.4):
    return Position(trade_id=1, bot="learner", pair=XRP, side=side, setup="T1", status="open", decision_id=1,
                    signal_bar_close_ts=DEC, entry_ts=DEC, entry_bar_open=DEC, entry_price=entry, qty=qty, leverage=3,
                    initial_stop=stop, current_stop=stop, stop_seq=0, stop_client_id="x", planned_target=None, trail_atr=3.0,
                    param_version_id=1, trigger_tf="1h", risk_amount=0.5, margin=3.2, rh=None, rl=None, fee_entry=0.0,
                    funding_paid=0.0, mfe_price=entry, mae_price=entry, exit_reason=None, exit_client_id=None,
                    closed_ts=None, strategy_name="fake_strategy", strategy_version="0.1")


def test_kagit_ve_canli_ayni_tetik_anda_ayni_karari_verir(tmp_path):
    modes = {"default": {"breakeven": True, "partial": True}, "T1@1h": {"breakeven": {"trigger_r": 0.8, "offset_bps": 20.0},
                                                                         "partial": {"trigger_r": 1.2, "frac": 0.4}}}
    (tmp_path / "live").mkdir()
    live = mk(tmp_path / "live", modes)
    (tmp_path / "paper").mkdir()
    paper = Env(tmp_path / "paper")
    paper.engine.cfg = dc.replace(paper.engine.cfg, exit_modes=XM.build_config(modes))
    try:
        for side, path in (("long", [2.02, 2.07, 2.081, 2.119, 2.121, 2.2]),
                           ("short", [1.98, 1.93, 1.919, 1.881, 1.879, 1.8])):
            pos = _pos(side, stop=1.9 if side == "long" else 2.1)
            for hi in path:
                hs, ls = (np.array([hi]), np.array([2.0])) if side == "long" else (np.array([2.0]), np.array([hi]))
                c = ExitContext(bar_close_ts=D2, highs=hs, lows=ls, atrs=np.array([0.5]), regime_last="trend_up",
                                last_close=hi, n_closed=1)
                ml, mp = live.engine._exit_modes(pos), paper.engine._exit_modes(pos)
                assert ml == mp and ml is not None
                none = dc.replace  # noqa: F841
                from trader_engine.position_manager import ExitDecision
                d0 = ExitDecision("none")
                assert apply_exit_modes(pos, c, d0, ml) == apply_exit_modes(pos, c, d0, mp)
                assert partial_due(pos, c, ml) == partial_due(pos, c, mp)
                assert XM.partial_qty(pos.qty, ml.pt_frac, 0.1, 0.1, 5.0, hi) == XM.partial_qty(pos.qty, mp.pt_frac, 0.1, 0.1, 5.0, hi)
    finally:
        live.close()
        paper.state.close()
        paper.real_ledger.close()


def test_testnet_cikis_kipi_kapali_kalir(tmp_path):
    e = CEnv(tmp_path, mode="testnet")
    e.engine.cfg = dc.replace(e.engine.cfg, exit_modes=XM.build_config(BOTH))
    try:
        assert e.engine._exit_modes(_pos()) is None
    finally:
        e.close()


# ---------------------------------------------------------------------------------------------- inceleme duzeltmeleri
BLENDED = (4.4 * 2.12 + 9.0 * 1.85) / 13.4


def _fee_sum(e, trade_id):
    t = e.real_ledger.get_trade(trade_id)
    return t, float(getattr(t, "fee_exit", 0.0) or 0.0)


def test_madde1_kismi_done_motor_kapaliyken_stop_tetiklenir_yeniden_baslatmada_tek_sayim(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.decide(D2)
    pk = e.state.kv_get(f"partial:{pos.trade_id}")
    assert pk["state"] == "done" and e.pos().qty == pytest.approx(9.0)
    e.close()
    e.ex.set_mark(SYM, "1.85")                                       # motor kapali: stop tetiklenir, borsa duz
    assert not e.ex.pos.get(SYM) or e.ex.pos[SYM]["amt"] == 0
    e2 = mk(e.tmp, ONLY_PT, ex=e.ex, clock=e.clock)
    try:
        e2.tick(31)
        e2.tick(31)
        assert e2.state.get_position(pos.trade_id).status == "closed"
        t, fee = _fee_sum(e2, pos.trade_id)
        assert t.exit_price == pytest.approx(BLENDED)                # kismi bacak tek kez karma fiyata girer
        stop_fee = 9.0 * 1.85 * 0.0004
        assert fee == pytest.approx(stop_fee + float(pk["fee"]), rel=1e-6)      # komisyon bir kez (stop bacagi + kismi)
    finally:
        e2.close()


def test_madde2_pending_kismi_dolmus_sonra_stop_kapanista_cozulur_ve_harmanlanir(tmp_path):
    e, pos, cid = _crash_after_partial_post(tmp_path)                # pending, borsada dolmus, motor haberdar degil
    try:
        e.engine._register(pos.trade_id)
        e.ex.set_mark(SYM, "1.85")
        e.tick(31)
        e.tick(31)
        e.tick(31)
        assert e.state.get_position(pos.trade_id).status == "closed"
        assert e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "done"
        t, _ = _fee_sum(e, pos.trade_id)
        assert t.exit_price == pytest.approx(BLENDED)                # kismi bacagin kari dusmez
    finally:
        e.close()


def test_madde2_pending_kismi_yeniden_baslatma_sonrasi_stop_kapanista_cozulur(tmp_path):
    e, pos, cid = _crash_after_partial_post(tmp_path)
    e.close()
    e.ex.set_mark(SYM, "1.85")                                       # kapaliyken stop tetiklenir
    e2 = mk(e.tmp, ONLY_PT, ex=e.ex, clock=e.clock)
    try:
        e2.tick(31)
        e2.tick(31)
        assert e2.state.get_position(pos.trade_id).status == "closed"
        t, _ = _fee_sum(e2, pos.trade_id)
        assert t.exit_price == pytest.approx(BLENDED)
    finally:
        e2.close()


@pytest.mark.parametrize("reason", [(429, -1003, "rate_limited"), (418, -1003, "exchange_ban")])
def test_madde3_gecici_ret_kismiyi_skipped_yapmaz_sonraki_barda_yeniden_dener(tmp_path, reason):
    status, code, _ = reason
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.src.ctx[(XRP, D3)] = ctx(D3, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.ex.inject("/fapi/v1/order", FakeResp(status, {"code": code, "msg": "x"}))
    e.decide(D2)
    pk = e.state.kv_get(f"partial:{pos.trade_id}")
    assert pk["state"] == "retry" and e.pos().qty == pytest.approx(13.4)
    assert e.engine.counters()["partial_retry_transient"] == 1
    e.decide(D2)                                                      # ayni bar: yeniden deneme yok
    assert reduce_markets(e) == [] or len(reduce_markets(e)) <= 1
    e.decide(D3)
    pk = e.state.kv_get(f"partial:{pos.trade_id}")
    assert pk["state"] == "done" and e.pos().qty == pytest.approx(9.0)
    assert len([m for m in e.ex.trades if m["side"] == "SELL"]) == 1          # tek kismi emir dolmus (cift emir yok)


def test_madde3_kalici_ret_skipped_kalir(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.src.ctx[(XRP, D3)] = ctx(D3, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.ex.inject("/fapi/v1/order", FakeResp(400, {"code": -2022, "msg": "ReduceOnly Order is rejected."}))
    e.decide(D2)
    assert e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "skipped"
    e.decide(D3)
    assert reduce_markets(e) == [] or len(reduce_markets(e)) == 1 and e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "skipped"


def test_madde4_bayat_last_pos_kismi_dolumu_olay_uretir_ve_kapanis_dogru(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.engine.broker._last_pos.pop(XRP, None)                          # bayat/bilinmeyen son miktar
    e.decide(D2)
    assert e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "done" and e.pos().qty == pytest.approx(9.0)
    assert e.engine.counters()["partial_fills"] == 1
    e.ex.set_mark(SYM, "1.85")
    e.tick(31)
    e.tick(31)
    t, _ = _fee_sum(e, pos.trade_id)
    assert e.state.get_position(pos.trade_id).status == "closed" and t.exit_price == pytest.approx(BLENDED)
    e.close()


def test_madde4_kismi_new_kalir_sonra_dolar_gecikmeli_user_trades(tmp_path):
    e = mk(tmp_path, ONLY_PT)
    pos = e.enter()
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
    e.ex.set_mark(SYM, "2.12")
    e.ex.hold_market = True
    e.decide(D2)
    pk = e.state.kv_get(f"partial:{pos.trade_id}")
    assert pk["state"] == "pending" and e.pos().qty == pytest.approx(13.4)
    e.ex.hold_market = False
    e.ex.release_market(pk["cid"])
    oid = e.ex.orders[pk["cid"]]["orderId"]
    e.ex.hide_trades_oids.add(oid)                                     # userTrades gecikmesi
    e.tick(31)
    e.ex.hide_trades_oids.clear()
    e.tick(31)
    e.decide(D2)
    assert e.state.kv_get(f"partial:{pos.trade_id}")["state"] == "done" and e.pos().qty == pytest.approx(9.0)
    assert len(reduce_markets(e)) == 1
    e.close()


def test_madde5_mutabakat_bekleyen_kismi_dolmus_ext_reduction_uretmez(tmp_path):
    e, pos, cid = _crash_after_partial_post(tmp_path)                   # state Q=13.4 pending(4.4), borsa 9.0
    e.close()
    e2 = mk(e.tmp, ONLY_PT, ex=e.ex, clock=e.clock)
    try:
        assert e2.state.kv_get(f"ext_reduction:{pos.trade_id}") is None
        ctr = e2.engine.reconciler.counters if hasattr(e2.engine, "reconciler") else None
        if ctr is not None:
            assert ctr.get("qty_reduced_external", 0) == 0
        e2.src.ctx[(XRP, D2)] = ctx(D2, 2.16)
        e2.decide(D2)
        assert e2.state.kv_get(f"partial:{pos.trade_id}")["state"] == "done" and e2.pos().qty == pytest.approx(9.0)
        assert e2.state.kv_get(f"ext_reduction:{pos.trade_id}") is None
    finally:
        e2.close()


def test_madde7_accept_then_trigger_basabas_yeniden_boyutlama(tmp_path):
    e = mk(tmp_path, BOTH)
    pos = e.enter()
    e.ex.immediate_trigger = "accept_then_trigger"
    e.src.ctx[(XRP, D2)] = ctx(D2, 2.16, last_close=2.0)               # basa-bas + kismi ayni barda
    e.ex.set_mark(SYM, "2.001")                                        # yeni stop mark'in ustunde: NEW kabul, hemen tetik
    e.decide(D2)
    e.tick(31)
    e.tick(31)
    p = e.state.get_position(pos.trade_id)
    assert p.status == "closed" and e.ex_qty() == 0
    assert [a for a in e.stops()] == []                                 # acik koruyucu stop kalmadi
    e.close()
