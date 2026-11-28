"""P1-a: kagit brokerde eksik 1 dk mumda 15 dk mumla temkinli stop (broker `gap_stop_kontrol` + motor `_gap15_*`)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_engine_05_spec import BTC, ETH, SOL, T0, Env, M1
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import CostModel
from trader_engine.types import MinuteBar, OrderRequest, SymbolRules

UTC = timezone.utc
P = "TSLA/USDT"
B0 = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
RULES = SymbolRules(pair=P, symbol="TSLAUSDT", tick=0.01, step=0.001, min_qty=0.001, max_qty=1000.0, min_notional=5.0)
SLIP_STOP = CostModel().slip_stop_bps / 1e4


def _bar(minute, px):
    return MinuteBar(pair=P, open_ts=B0 + timedelta(minutes=minute), step_s=60, last_o=px, last_h=px, last_l=px, last_c=px,
                     mark_o=px, mark_h=px, mark_l=px, mark_c=px)


def _broker(side="long", stop=None, target=None):
    b = PaperBroker(PaperConfig(cost=CostModel(), mmr=0.004), lambda p: RULES, lambda p, a, z: [], SimClock(B0), None)
    b.prepare(P, 3)
    buy = side == "long"
    b.market_order(OrderRequest(client_id="e1", pair=P, role="entry", order_side="buy" if buy else "sell", qty=6.369, trigger_price=None,
                                reduce_only=False, leverage=3))
    bars = {P: _bar(0, 100.0)}
    b.advance(bars, "fills")
    b.advance(bars, "triggers")
    b.poll(B0)
    stop = stop if stop is not None else (98.0 if buy else 102.0)
    assert b.place_stop(OrderRequest(client_id="s1", pair=P, role="stop", order_side="sell" if buy else "buy", qty=6.369, trigger_price=stop,
                                     reduce_only=True, leverage=None)).status == "accepted"
    if target is not None:
        assert b.place_target(OrderRequest(client_id="t1", pair=P, role="target", order_side="sell" if buy else "buy", qty=6.369,
                                           trigger_price=target, reduce_only=True, leverage=None)).status == "accepted"
    b.poll(B0)
    return b


TS = B0 + timedelta(minutes=29)


def test_stop_fiyati_salt_okunur():
    b = _broker("long")
    assert b.stop_fiyati(P) == 98.0 and b.stop_fiyati("YOK/USDT") is None
    assert len(b.positions()) == 1 and b.poll(B0) == []


def test_long_stop_vurulur_hedef_iptal():
    b = _broker("long", target=105.0)
    assert b.gap_stop_kontrol(P, 99.0, 99.5, 97.5, 98.0, ts=TS, acilis_gecerli=False) == "stop"
    ev = b.poll(B0)
    fills = [e.fill for e in ev if e.fill]
    assert len(fills) == 1 and fills[0].reason == "stop"
    assert fills[0].price == pytest.approx(98.0 * (1 - SLIP_STOP), abs=0.011)
    assert b.positions() == []
    assert any(e.kind == "order_canceled" and e.client_id == "t1" for e in ev)


def test_long_bosluk_acilis_gecerli_acilistan_dolar():
    b = _broker("long")
    assert b.gap_stop_kontrol(P, 97.0, 97.5, 96.0, 98.0, ts=TS, acilis_gecerli=True) == "stop"
    f = [e.fill for e in b.poll(B0) if e.fill][0]
    assert f.price == pytest.approx(97.0 * (1 - SLIP_STOP), abs=0.011)


def test_long_bosluk_acilis_gecersiz_stop_fiyatindan_dolar():
    b = _broker("long")
    assert b.gap_stop_kontrol(P, 97.0, 97.5, 96.0, 98.0, ts=TS, acilis_gecerli=False) == "stop"
    f = [e.fill for e in b.poll(B0) if e.fill][0]
    assert f.price == pytest.approx(98.0 * (1 - SLIP_STOP), abs=0.011)


def test_stop_degmiyor_none():
    b = _broker("long", target=105.0)
    assert b.gap_stop_kontrol(P, 99.0, 99.5, 98.01, 98.0, ts=TS, acilis_gecerli=True) is None
    assert len(b.positions()) == 1 and b.poll(B0) == []


def test_short_simetrik():
    b = _broker("short")
    assert b.stop_fiyati(P) == 102.0
    assert b.gap_stop_kontrol(P, 101.0, 102.5, 100.5, 102.0, ts=TS, acilis_gecerli=False) == "stop"
    f = [e.fill for e in b.poll(B0) if e.fill][0]
    assert f.price == pytest.approx(102.0 * (1 + SLIP_STOP), abs=0.011)
    b = _broker("short")
    assert b.gap_stop_kontrol(P, 103.0, 104.0, 102.5, 102.0, ts=TS, acilis_gecerli=True) == "stop"
    f = [e.fill for e in b.poll(B0) if e.fill][0]
    assert f.price == pytest.approx(103.0 * (1 + SLIP_STOP), abs=0.011)
    b = _broker("short")
    assert b.gap_stop_kontrol(P, 101.0, 101.99, 100.5, 102.0, ts=TS, acilis_gecerli=True) is None


def test_tasfiye_stoptan_once():
    b = _broker("long", stop=60.0)                      # 3x kaldirac: tasfiye ~67; stop tasfiyenin otesinde
    assert b.gap_stop_kontrol(P, 80.0, 81.0, 50.0, 60.0, ts=TS, acilis_gecerli=False) == "tasfiye"
    ev = b.poll(B0)
    assert [e for e in ev if e.kind == "liquidation"] and b.positions() == []


def test_hedef_aralikta_olsa_da_pozisyon_acik():
    b = _broker("long", target=101.0)
    assert b.gap_stop_kontrol(P, 100.0, 110.0, 99.0, 98.0, ts=TS, acilis_gecerli=True) is None
    assert len(b.positions()) == 1 and b.poll(B0) == []


def test_bir_dakikalik_yol_ayni_kalir():
    """Regresyon: 1 dk bosluklu stop dolumu acilis (last_o) tabanli; `_triggers_pair` degismedi."""
    b = _broker("long")
    bars = {P: MinuteBar(pair=P, open_ts=B0 + timedelta(minutes=5), step_s=60, last_o=95.0, last_h=96.0, last_l=94.0, last_c=95.5,
                         mark_o=95.0, mark_h=96.0, mark_l=94.0, mark_c=95.5)}
    b.advance(bars, "fills")
    b.advance(bars, "triggers")
    f = [e.fill for e in b.poll(B0) if e.fill][0]
    assert f.reason == "stop" and f.price == pytest.approx(95.0 * (1 - SLIP_STOP), abs=0.011)


# ============================================================================================ motor
W0 = T0                                   # 09:00
PEN = T0 + timedelta(minutes=15)         # pencere 09:15-09:30
D = T0 + timedelta(minutes=30)


def _ac(tmp_path, **kw):
    e = Env(tmp_path, pairs=(BTC, ETH, SOL), **kw)
    e.start()
    e.open_pos(BTC, T0)                                  # 09:00'da long; stop 98
    for m in range(1, 15):
        e.step(T0 + m * M1)
    return e


def _pencere(e, eksik=(2, 3, 4), son=14):
    """09:15..09:29: `eksik` dakikalarinda BTC mumu yok (diger ciftler var)."""
    for m in range(0, 15):
        ts = PEN + m * M1
        e.step(ts, pairs=(ETH, SOL) if m in eksik else None)


def _mum15(e, *, low):
    df = e.view.min[BTC]
    i = df.index.get_loc(PEN + 2 * M1)
    df.iloc[i, df.columns.get_loc("low")] = low
    e.view._tf.clear()


def _olcum(e):
    e.engine.olcum.adim(D)
    ozet = json.loads((Path(e.cfg.path("olcum")) / "ozet.json").read_text())
    return ozet["olcumler"]["eksik_dakika_stop"], list(Path(e.cfg.path("olcum")).glob("satirlar-*.jsonl"))


def test_eksik_dakika_stop_kapanir(tmp_path):
    e = _ac(tmp_path)
    try:
        assert e.pos(BTC).status == "open" and e.engine.broker.stop_fiyati(BTC) == pytest.approx(98.0, abs=0.5)
        _pencere(e)
        assert len(e.engine._gap15) == 1 and next(iter(e.engine._gap15.values()))["dakikalar"].__len__() == 3
        _mum15(e, low=90.0)
        e.set_clock(D + timedelta(seconds=5))
        e.engine._gap15_step(D)
        assert e.pos(BTC) is None and e.engine._gap15 == {}
        tr = e.real_ledger.list_closed_trades()
        assert len(tr) == 1 and tr[0].exit_reason == "stop"
        blok, dosyalar = _olcum(e)
        assert blok["sayac"]["stop"] == 1 and blok["sayac"]["kontrol"] == 1 and blok["stop_orani"] == 1.0
        satir = [json.loads(x) for f in dosyalar for x in f.read_text().splitlines()]
        assert len(satir) == 1 and satir[0]["olcum"] == "eksik_dakika_stop" and satir[0]["sonuc"] == "stop" and satir[0]["dolum"] is not None
    finally:
        e.close()


def test_eksik_dakika_stop_degmiyor(tmp_path):
    e = _ac(tmp_path)
    try:
        _pencere(e)
        e.set_clock(D + timedelta(seconds=5))
        e.engine._gap15_step(D)
        assert e.pos(BTC) is not None and e.engine._gap15 == {}
        blok, _ = _olcum(e)
        assert blok["sayac"]["kontrol"] == 1 and blok["sayac"].get("stop", 0) == 0
    finally:
        e.close()


def test_eksik_dakika_15dk_mum_gelmiyor(tmp_path):
    e = _ac(tmp_path)
    try:
        _pencere(e)
        e.view.missing[(BTC, "15m")] = [PEN]
        for k in range(4):
            assert e.engine._gap15 != {}
            e.set_clock(D + timedelta(seconds=5))
            e.engine._gap15_step(D)
        assert e.engine._gap15 == {} and e.pos(BTC) is not None
        blok, _ = _olcum(e)
        assert blok["sayac"]["veri_yok"] == 1
    finally:
        e.close()


def test_eksik_dakikadan_sonra_baska_yolla_kapanmis(tmp_path):
    e = _ac(tmp_path)
    try:
        e.step(PEN + 2 * M1, pairs=(ETH, SOL))
        e.step(PEN + 3 * M1, pairs=(ETH, SOL))
        assert len(e.engine._gap15) == 1
        e.step(PEN + 5 * M1, lo=90.0, hi=100.0)               # BTC mumu geldi, stop 1 dk yolundan vuruldu
        assert e.pos(BTC) is None
        e.set_clock(D + timedelta(seconds=5))
        e.engine._gap15_step(D)
        assert e.engine._gap15 == {} and len(e.real_ledger.list_closed_trades()) == 1
        blok, _ = _olcum(e)
        assert blok["sayac"]["kapanmis"] == 1 and blok["sayac"].get("stop", 0) == 0
    finally:
        e.close()


def test_yeniden_baslatma_kv_geri_gelir(tmp_path):
    e = _ac(tmp_path)
    try:
        _pencere(e)
        _mum15(e, low=90.0)
        assert e.state.kv_get("gap15")
        e.engine._gap15 = {}                                 # bellek kaybi
        e.engine.start()                                     # kv'den geri yuklenir
        assert len(e.engine._gap15) == 1
        e.set_clock(D + timedelta(seconds=5))
        e.engine._gap15_step(D)
        assert e.pos(BTC) is None
    finally:
        e.close()


def test_backtest_motorunda_gap15_dolmaz(tmp_path):
    e = Env(tmp_path, mode="backtest", pairs=(BTC, ETH, SOL))
    try:
        assert e.engine.olcum is None
        e.engine.start()
        e.open_pos(BTC, T0)
        e.step(T0 + M1, pairs=(ETH, SOL))
        assert e.engine._gap15 == {} and e.engine.olcum is None
        assert not (Path(e.cfg.path("olcum"))).exists()
    finally:
        e.close()


def test_canli_motorda_gap15_dolmaz(tmp_path):
    e = _ac(tmp_path)
    try:
        e.broker.is_simulated = False                        # is_paper == False: canli yol
        assert not e.engine.is_paper
        e.step(PEN, pairs=(ETH, SOL))
        assert e.engine._gap15 == {}
    finally:
        e.broker.is_simulated = True
        e.close()
