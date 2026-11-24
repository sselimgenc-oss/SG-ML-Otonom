"""24.11 kullanici karari: hedef bekleyen emir, CANLI yol (gercek LiveBroker + SignedRestClient + FakeExchange HTTP duzeyi + gercek Engine).
Giriste reduceOnly TAKE_PROFIT_MARKET; baska yolla kapanista iptal; kismi sonrasi kalan adede yeniden kurma; mutabakat; kagit = canli parite."""
from __future__ import annotations

import dataclasses as dc
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fake_exchange import FakeResp
from test_dd8_spec import DEnv
from test_engine_live_spec import DEC, H, SYM, XRP
from trader_core import exit_modes as XM
from trader_engine.config import load_cli_config
from trader_engine.order_manager import make_client_id

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
D2 = DEC + H
R1_KW = dict(setup="R1", planned_target=2.3, regime="range", rh=2.4, rl=1.8, wick_ratio=0.5, rr=3.0, edge_dist_atr=0.5)
PT = {"default": {"partial": {"trigger_r": 1.5, "frac": 0.33}}}
BE = {"default": {"breakeven": True}}


def mk(tmp, modes=None, *, target_mode="resting"):
    e = DEnv(tmp, mode="live")
    cfg = dc.replace(e.engine.cfg, target_mode=target_mode, exit_modes=XM.build_config(modes) if modes else {})
    e.engine.cfg = cfg
    e.engine.reconciler.cfg = cfg
    e.ex.symbols[SYM]["notional"] = "1"
    return e.boot()


def algos(e, typ=None, status="NEW"):
    return [a for a in e.ex.algos.values() if a["algoStatus"] == status and (typ is None or a["type"] == typ)]


def writes(e, after=0):
    """(yontem, tur, adet, tetik) sirasi: emir POST/DELETE'leri (piyasa + koruyucu/hedef)."""
    out = []
    for m, p, q in e.ex.requests[after:]:
        if p == "/fapi/v1/order" and m == "POST":
            out.append((m, "MARKET", q.get("quantity"), None))
        elif p == "/fapi/v1/algoOrder" and m == "POST":
            out.append((m, q.get("type"), q.get("quantity"), q.get("triggerPrice")))
        elif p == "/fapi/v1/algoOrder" and m == "DELETE":
            out.append((m, "ALGO", None, None))
    return out


def ex_qty(e) -> Decimal:
    p = e.ex.pos.get(SYM)
    return p["amt"] if p else Decimal(0)


def set_best(e, tid, price):
    with e.state.tx():
        e.state.update_position(tid, mfe_price=price)


# ----------------------------------------------------------------------------------------------- giriste kurulum
def test_giriste_stop_sonra_take_profit_market_reduceonly(tmp_path):
    e = mk(tmp_path)
    n0 = len(e.ex.requests)
    pos = e.enter(**R1_KW)
    w = [x for x in writes(e, n0) if x[1] in ("STOP_MARKET", "TAKE_PROFIT_MARKET")]
    assert [x[1] for x in w] == ["STOP_MARKET", "TAKE_PROFIT_MARKET"], w                 # once koruyucu stop, sonra hedef
    tp = algos(e, "TAKE_PROFIT_MARKET")
    assert len(tp) == 1 and tp[0]["triggerPrice"] == Decimal("2.3") and tp[0]["qty"] == Decimal(str(pos.qty))
    assert tp[0]["side"] == "SELL" and tp[0]["reduce"] is True and tp[0]["workingType"] == "MARK_PRICE"
    assert tp[0]["cid"] == make_client_id("learner", "target", XRP, "long", DEC, 0)
    row = e.state.get_order(tp[0]["cid"])
    assert row.role == "target" and row.status == "accepted" and row.trade_id == pos.trade_id
    assert e.state.kv_get(f"target:{pos.trade_id}")["state"] == "active"
    assert len(algos(e, "STOP_MARKET")) == 1
    e.close()


def test_bar_close_modunda_canlida_hedef_emri_yok(tmp_path):
    e = mk(tmp_path, target_mode="bar_close")
    e.enter(**R1_KW)
    assert algos(e, "TAKE_PROFIT_MARKET") == []
    e.close()


def test_hedef_reddedilirse_pozisyon_stopla_surer_bar_close_yedegi(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**{**R1_KW, "planned_target": 2.0})          # hedef = mark: borsa anlik tetik reddi (-2021)
    p = e.pos()
    assert p.status == "open" and len(algos(e, "STOP_MARKET")) == 1 and algos(e, "TAKE_PROFIT_MARKET") == []
    assert e.state.kv_get(f"target:{pos.trade_id}")["state"] == "failed"
    assert e.engine.counters()["target_place_failed"] == 1
    e.close()


# ----------------------------------------------------------------------------------------------- baska yolla kapanista iptal
def test_stop_tetiklenince_hedef_iptal_edilir(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    tcid = algos(e, "TAKE_PROFIT_MARKET")[0]["cid"]
    e.ex.set_mark(SYM, "1.85")                                 # stop (1.9) tetiklenir
    e.tick(31)
    e.tick(31)
    assert e.state.get_position(pos.trade_id).status == "closed" and ex_qty(e) == 0
    assert algos(e, "TAKE_PROFIT_MARKET") == [] and e.ex.algos[tcid]["algoStatus"] == "CANCELED"
    assert e.state.get_order(tcid).status == "canceled"
    assert e.real_ledger.get_trade(pos.trade_id).exit_reason == "stop"
    e.close()


def test_hedef_tetiklenince_pozisyon_target_ile_kapanir_stop_iptal(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    scid = algos(e, "STOP_MARKET")[0]["cid"]
    e.ex.set_mark(SYM, "2.31")                                 # hedef (2.3) tetiklenir
    e.tick(31)
    e.tick(31)
    assert e.state.get_position(pos.trade_id).status == "closed" and ex_qty(e) == 0
    t = e.real_ledger.get_trade(pos.trade_id)
    assert t.exit_reason == "target" and t.planned_exit == pytest.approx(2.3) and t.exit_price == pytest.approx(2.31)
    assert algos(e) == [] and e.ex.algos[scid]["algoStatus"] == "CANCELED"
    assert e.engine.counters()["target_fills"] == 1
    e.close()


def test_piyasa_cikisi_zaman_durdurma_ile_kapanista_hedef_iptal(tmp_path):
    import numpy as np

    from trader_engine.position_manager import ExitContext
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    tcid = algos(e, "TAKE_PROFIT_MARKET")[0]["cid"]
    e.src.ctx[(XRP, D2)] = ExitContext(bar_close_ts=D2, highs=np.array([2.05]), lows=np.array([1.95]), atrs=np.array([0.02]),
                                       regime_last="trend_up", last_close=2.0, n_closed=500)      # zaman durdurma
    e.decide(D2)
    e.tick(31)
    assert e.state.get_position(pos.trade_id).status == "closed" and ex_qty(e) == 0
    assert e.real_ledger.get_trade(pos.trade_id).exit_reason == "time_stop"
    assert algos(e) == [] and e.ex.algos[tcid]["algoStatus"] == "CANCELED"
    assert e.state.get_order(tcid).status == "canceled"
    e.close()


def test_hedef_aktifken_bar_kapanisinda_hedef_icin_piyasa_cikisi_yok(tmp_path):
    import numpy as np

    from trader_engine.position_manager import ExitContext
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    e.src.ctx[(XRP, D2)] = ExitContext(bar_close_ts=D2, highs=np.array([2.4]), lows=np.array([1.95]), atrs=np.array([0.02]),
                                       regime_last="trend_up", last_close=2.2, n_closed=1)      # bar hedefe degdi (mark degmedi)
    n0 = len(e.ex.requests)
    e.decide(D2)
    assert [x for x in writes(e, n0) if x[1] == "MARKET"] == [] and e.pos().status == "open"
    assert len(algos(e, "TAKE_PROFIT_MARKET")) == 1
    e.close()


# ----------------------------------------------------------------------------------------------- kismi sonrasi yeniden kurma (replace)
def test_kismi_sonrasi_stop_ve_hedef_kalan_adede_yeni_once_eski_sonra_iptal(tmp_path):
    e = mk(tmp_path, PT)
    pos = e.enter(**R1_KW)
    assert pos.qty == 4.8
    old_t = algos(e, "TAKE_PROFIT_MARKET")[0]["cid"]
    set_best(e, pos.trade_id, 2.16)                             # >= giris + 1.5R (2.15): 15 dk adiminin dakika dakika tuttugu en iyi uc
    e.ex.set_mark(SYM, "2.12")
    n0 = len(e.ex.requests)
    e.decide(D2)
    w = writes(e, n0)
    assert [(m, k) for m, k, *_ in w] == [("POST", "MARKET"), ("POST", "STOP_MARKET"), ("DELETE", "ALGO"),
                                         ("POST", "TAKE_PROFIT_MARKET"), ("DELETE", "ALGO")], w
    assert w[0][2] == "1.5" and w[1][2] == "3.3" and w[3][2] == "3.3" and Decimal(w[3][3]) == Decimal("2.3")
    tp = algos(e, "TAKE_PROFIT_MARKET")
    assert len(tp) == 1 and tp[0]["qty"] == Decimal("3.3") and tp[0]["cid"] != old_t
    assert e.ex.algos[old_t]["algoStatus"] == "CANCELED" and e.state.get_order(old_t).status == "canceled"
    assert e.state.kv_get(f"target:{pos.trade_id}")["cid"] == tp[0]["cid"]
    assert e.pos().qty == pytest.approx(3.3) and ex_qty(e) == Decimal("3.3")
    assert e.engine.counters()["target_resized"] == 1
    # kalan parca hedefte kapanir
    e.ex.set_mark(SYM, "2.31")
    e.tick(31)
    e.tick(31)
    t = e.real_ledger.get_trade(pos.trade_id)
    assert t.exit_reason == "target" and algos(e) == []
    e.close()


def test_kismi_sonrasi_hedef_kurulamazsa_eski_hedef_durur_sayac(tmp_path):
    e = mk(tmp_path, PT)
    pos = e.enter(**R1_KW)
    old_t = algos(e, "TAKE_PROFIT_MARKET")[0]["cid"]
    set_best(e, pos.trade_id, 2.16)
    e.ex.set_mark(SYM, "2.12")
    orig = e.ex._new_cond

    def deny_target(sym, side, typ, qty, trig, wt, cid, reduce=True):
        if typ == "TAKE_PROFIT_MARKET":
            return FakeResp(400, {"code": -1111, "msg": "x"})
        return orig(sym, side, typ, qty, trig, wt, cid, reduce)
    e.ex._new_cond = deny_target
    e.decide(D2)
    tp = algos(e, "TAKE_PROFIT_MARKET")
    assert len(tp) == 1 and tp[0]["cid"] == old_t and tp[0]["qty"] == Decimal("4.8")      # eski (genis) hedef durur
    assert e.engine.counters()["target_resize_failed"] == 1 and e.pos().qty == pytest.approx(3.3)
    e.close()


def test_basabas_15dk_adiminda_canlida_yeni_stop_once_eski_sonra(tmp_path):
    e = mk(tmp_path, BE)
    pos = e.enter(**R1_KW)
    set_best(e, pos.trade_id, 2.11)                             # >= giris + 1R
    e.ex.set_mark(SYM, "2.11")
    n0 = len(e.ex.requests)
    e.decide(D2)
    w = writes(e, n0)
    assert [(m, k) for m, k, *_ in w] == [("POST", "STOP_MARKET"), ("DELETE", "ALGO")], w
    assert Decimal(w[0][3]) == Decimal("2.003")
    assert len(algos(e, "TAKE_PROFIT_MARKET")) == 1             # hedef etkilenmez
    e.close()


# ----------------------------------------------------------------------------------------------- mutabakat
def _reconcile(e):
    return e.engine._reconcile(e.clock.now())


def test_mutabakat_borsada_kaybolan_hedefi_yeniden_kurar(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    old = algos(e, "TAKE_PROFIT_MARKET")[0]
    e.ex.algos[old["cid"]]["algoStatus"] = "CANCELED"           # borsada iptal/suresi doldu
    assert algos(e, "TAKE_PROFIT_MARKET") == []
    rep = _reconcile(e)
    tp = algos(e, "TAKE_PROFIT_MARKET")
    assert len(tp) == 1 and tp[0]["cid"] != old["cid"] and tp[0]["qty"] == old["qty"] and tp[0]["triggerPrice"] == Decimal("2.3")
    assert f"no_target:{pos.trade_id}" in rep.findings and f"target_installed:{pos.trade_id}" in rep.actions
    assert e.state.kv_get(f"target:{pos.trade_id}")["cid"] == tp[0]["cid"]
    assert len(algos(e, "STOP_MARKET")) == 1
    e.close()


def test_mutabakat_hedef_adedi_borsa_adedinden_farkliysa_degistirir(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    old = algos(e, "TAKE_PROFIT_MARKET")[0]
    e.ex.algos[old["cid"]]["qty"] = Decimal("2.0")              # adet uyumsuz (borsa 4.8)
    rep = _reconcile(e)
    tp = algos(e, "TAKE_PROFIT_MARKET")
    assert len(tp) == 1 and tp[0]["qty"] == Decimal("4.8") and tp[0]["cid"] != old["cid"]
    assert e.ex.algos[old["cid"]]["algoStatus"] == "CANCELED"
    assert f"target_qty_mismatch:{pos.trade_id}" in rep.findings
    e.close()


def test_mutabakat_uygun_hedefe_dokunmaz(tmp_path):
    e = mk(tmp_path)
    e.enter(**R1_KW)
    n0 = len(e.ex.requests)
    rep = _reconcile(e)
    assert [x for x in writes(e, n0) if x[0] in ("POST", "DELETE")] == [] and rep.ok
    e.close()


def test_mutabakat_orders_tablosunda_olmayan_hedefi_iptal_eder(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    foreign = make_client_id("learner", "target", XRP, "long", DEC, 7)
    e.ex._new_cond(SYM, "SELL", "TAKE_PROFIT_MARKET", Decimal("1.0"), Decimal("2.4"), "MARK_PRICE", foreign, True)
    rep = _reconcile(e)
    assert e.ex.algos[foreign]["algoStatus"] == "CANCELED" and f"untracked_target:{foreign}" in rep.findings
    assert len(algos(e, "TAKE_PROFIT_MARKET")) == 1
    e.close()


def test_mutabakat_kurulamamis_hedefi_her_turda_denemez(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**{**R1_KW, "planned_target": 2.0})
    n0 = len(e.ex.requests)
    _reconcile(e)
    assert [x for x in writes(e, n0) if x[1] == "TAKE_PROFIT_MARKET"] == []
    e.close()


def test_mutabakat_disaridan_kapanan_pozisyonun_hedefi_iptal_edilir(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    tcid = algos(e, "TAKE_PROFIT_MARKET")[0]["cid"]
    e.ex.external_close(SYM)                                    # pozisyon disaridan kapandi; hedef/stop borsada kaldi
    _reconcile(e)
    _reconcile(e)
    assert e.state.get_position(pos.trade_id).status == "closed"
    assert e.ex.algos[tcid]["algoStatus"] == "CANCELED" and algos(e) == []
    e.close()


def test_kapanis_atfi_icin_hedef_kimligi_ipucu_listesinde(tmp_path):
    e = mk(tmp_path)
    pos = e.enter(**R1_KW)
    tcid = algos(e, "TAKE_PROFIT_MARKET")[0]["cid"]
    assert tcid in e.engine.reconciler._hint_ids(e.pos())
    e.close()


# ----------------------------------------------------------------------------------------------- kagit = canli parite
def _j(name):
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def test_parite_target_mode_kagit_ve_canli_ayni_deger():
    paper, live = _j("engine.paper.json"), _j("engine.live.json")
    assert paper["target_mode"] == live["target_mode"] == "resting"
    assert paper["exit_modes"] == live["exit_modes"]
    assert _j("engine.base.json")["target_mode"] == "bar_close"               # taban (geri test / testnet) eski yolda kalir
    cp, cl = load_cli_config(CONFIG, "learner", "paper"), load_cli_config(CONFIG, "learner", "live")
    assert cp.target_mode == cl.target_mode == "resting" and cp.exit_modes == cl.exit_modes
    assert load_cli_config(CONFIG, "learner", "testnet").target_mode == "bar_close"


def test_parite_kagit_ve_canli_ayni_hedef_fiyati_ve_emir_yonu(tmp_path):
    """Ayni pozisyon icin kagit OrderManager ve canli OrderManager ayni hedef fiyatini/yonunu/adedini uretir (tek kod yolu)."""
    from test_engine_05_spec import BTC, T0, Env
    (tmp_path / "paper").mkdir()
    (tmp_path / "live").mkdir()
    pe = Env(tmp_path / "paper", target_mode="resting")
    pe.start()
    pos = pe.open_pos(BTC, T0, setup="R1", entry=100.0, stop=98.0, planned_target=104.0004, tf="1h",
                      regime="range", rh=106.0, rl=94.0, wick_ratio=0.5, rr=2.0, edge_dist_atr=0.5)
    paper_req = pe.orders._target_request(pos, pe.orders.target_price(pos), 0)           # noqa: SLF001
    e = mk(tmp_path / "live")
    lpos = e.enter(**R1_KW)
    live_req = e.engine.orders._target_request(lpos, e.engine.orders.target_price(lpos), 0)   # noqa: SLF001
    assert (paper_req.role, paper_req.order_side, paper_req.reduce_only) == (live_req.role, live_req.order_side, live_req.reduce_only)
    assert paper_req.trigger_price == pytest.approx(104.0) and live_req.trigger_price == pytest.approx(2.3)
    pe.close()
    e.close()
