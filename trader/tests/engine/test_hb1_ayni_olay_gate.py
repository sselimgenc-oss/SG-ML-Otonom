"""HB1 'ayni haberle yeniden giris yok' kapisi: ayni olay -> red; yeni olay / ters yon / baska kol serbest; defter hatasi yalniz HB1'i durdurur;
olay kimligi metin ozellik olarak yazilir (sayisal ozellige girmez); canli = kagit parite."""
from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import ledger as L
from trader_engine.clock import SimClock
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate, NoVeto, _features, hb1_olay_of
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame
from trader_engine.types import SymbolRules

from test_engine_05_impl_smoke import T0, _params, _row  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CFG = load_cli_config(ROOT / "config", "learner", "paper")


def _kur(tmp_path):
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set("day_start:2026-12-01", 1000.0)
    state.open_positions = lambda: []   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(CFG, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    return SimpleNamespace(g=g, led=led, state=state)


@pytest.fixture
def e(tmp_path):
    x = _kur(tmp_path)
    yield x
    x.state.close()
    x.led.close()


def _hb1(olay, side="long", **kw):
    olay = "+".join(map(str, olay)) if isinstance(olay, (list, tuple)) else olay
    stop = 98.0 if side == "long" else 102.0
    d = dict(setup="HB1", side=side, arm_id="HB1@1h", tf="1h", planned_stop=stop, regime="trend_up",
             reasons=f"HB1_{side}:hb1,puan=+0.80,k=2,s=3,hb1_olay={olay}")
    d.update(kw)
    return _row(**d)


def _go(e, row):
    fr = SignalFrame(pair=row.pair, status="ok", detail=None, last=row, table=None, trigger_bar=(110.0, 99.0, 5.0))
    return e.g.decide(fr, T0, e.g.pre(T0, "1h", True, "1h"), 1)


def _kapat(e, row, n):
    """Adayi girise cevirip defterde KAPANMIS islem olarak yazar (stop)."""
    o = _go(e, row)
    assert o.action == "enter", o.code
    did = e.led.record_decision(o.event)
    e.led.record_trade_entry(L.TradeEntry(n, did, T0 + timedelta(seconds=3), 100.0, 0.3, 3, 0.03))
    e.led.record_trade_exit(L.TradeExit(n, T0 + timedelta(hours=1), 98.0, "stop", 98.0, 0.3, 0.1))


def test_ayni_olay_stop_sonrasi_reddedilir(e):
    _kapat(e, _hb1(4242), 1)
    o = _go(e, _hb1(4242))
    assert o.action == "skip" and o.code == "hb1_ayni_olay" and o.event.skip_reason == "risk_denied"
    assert o.event.veto_reason == "gate:hb1_ayni_olay" and o.size is None
    assert e.led.record_decision(dataclasses.replace(o.event, bar_close_ts=T0 - timedelta(hours=3))) > 0                           # skip olayi defter tarafindan kabul edilir
    assert e.g.counters["hb1_ayni_olay"] == 1


def test_yeni_olay_serbest(e):
    _kapat(e, _hb1(4242), 1)
    assert _go(e, _hb1(4243)).action == "enter"


def test_ters_yon_serbest(e):
    _kapat(e, _hb1(4242, "long"), 1)
    assert _go(e, _hb1(4242, "short")).action == "enter"


def test_yalniz_en_son_kapanmis_islem_sayilir(e):
    _kapat(e, _hb1(4242), 1)
    assert _go(e, _hb1(4242)).code == "hb1_ayni_olay"


def test_onceki_islem_yoksa_serbest(e):
    assert _go(e, _hb1(4242)).action == "enter"


def test_baska_kol_etkilenmez(e):
    _kapat(e, _hb1(4242), 1)
    t1 = _row(reasons="t1,hb1_olay=4242")                               # T1 satiri: kapi yalniz setup HB1 icin
    assert _go(e, t1).action == "enter"
    assert "hb1_olay" not in _features(t1)


def test_defter_hatasi_yalniz_hb1_reddeder(e):
    def boom(*a, **k):
        raise L.LedgerError("okunamadi") if hasattr(L, "LedgerError") else RuntimeError("okunamadi")
    e.led.closed_decision_features_since = boom                            # type: ignore[method-assign]
    o = _go(e, _hb1(4242))
    assert o.action == "skip" and o.code == "hb1_olay_okunamadi" and o.event.veto_reason == "gate:hb1_olay_okunamadi"
    assert e.g.counters["hb1_olay_okunamadi"] == 1
    assert _go(e, _row()).action == "enter"                              # T1 etkilenmez


def test_olay_kimligi_metin_ozellik_olarak_yazilir(e):
    row = _hb1(4242)
    f = _features(row)
    assert f["hb1_olay"] == "4242" and isinstance(f["hb1_olay"], str)     # metin: sayisal ozellik cikarimi atlar
    for k in ("edge_dist_atr", "hb1_body", "hb1_wick", "hb1_rr"):
        assert f.get(k) != 4242.0
    assert hb1_olay_of(_hb1(0)) is None and hb1_olay_of(_row()) is None


def test_defterde_olay_kimligi_karar_ozelligi_olarak_yazilir(e):
    _kapat(e, _hb1(777), 1)
    since = T0 - timedelta(hours=6)
    assert [f["hb1_olay"] for f in e.led.closed_decision_features_since("HB1@1h", "BTC/USDT", "long", since)] == ["777"]
    assert e.led.closed_decision_features_since("HB1@1h", "BTC/USDT", "short", since) == []
    assert e.led.closed_decision_features_since("HB1@1h", "BTC/USDT", "long", T0 + timedelta(hours=2)) == []


def test_canli_kagit_parite(e):
    _kapat(e, _hb1(4242), 1)
    paper = _go(e, _hb1(4242))
    e.g.cfg = dataclasses.replace(CFG, mode="live")
    live = _go(e, _hb1(4242))
    assert (paper.action, paper.code, paper.event.veto_reason) == (live.action, live.code, live.event.veto_reason)
    assert live.code == "hb1_ayni_olay"
    assert _go(e, _hb1(4243)).action == "enter"


def test_olay_kumesi_alt_kume_reddi_ve_yeni_kimlik_serbest(e):
    _kapat(e, _hb1([10, 20]), 1)                                        # A+B ile girildi, stop
    assert _go(e, _hb1([20])).code == "hb1_ayni_olay"                   # alt kume
    assert _go(e, _hb1([10, 20])).code == "hb1_ayni_olay"               # ayni kume
    assert _go(e, _hb1([10, 20, 30])).action == "enter"                 # C yeni kimlik: serbest
    assert _go(e, _hb1([30])).action == "enter"
    f = _features(_hb1([20, 10]))
    assert f["hb1_olay"] == "10,20"                                     # siralanmis, virgullu metin
    assert f["hb1_olay"] not in (None, 0)


def test_son_6_saat_penceresi_tum_islemler(e):
    _kapat(e, _hb1([10]), 1)                                            # en son kapanan (exit T0+1s saat): olay 10
    o = _go(e, _hb1([11]))
    assert o.action == "enter"
    ev = dataclasses.replace(o.event, bar_close_ts=T0 - timedelta(hours=2))   # daha eski kapanan ikinci islem: olay 11
    did = e.led.record_decision(ev)
    e.led.record_trade_entry(L.TradeEntry(2, did, T0 - timedelta(hours=2) + timedelta(seconds=3), 100.0, 0.3, 3, 0.03))
    e.led.record_trade_exit(L.TradeExit(2, T0 - timedelta(hours=1), 98.0, "stop", 98.0, 0.3, 0.1))
    assert _go(e, _hb1([11])).code == "hb1_ayni_olay"                   # LIMIT 1 olsaydi (yalniz olay 10) serbest kalirdi
    assert _go(e, _hb1([10, 11])).code == "hb1_ayni_olay"
    assert _go(e, _hb1([12])).action == "enter"


def test_olay_yok_sayaci_giris_serbest(e):
    assert _go(e, _hb1(0)).action == "enter"
    assert e.g.counters["hb1_olay_yok"] == 1


def test_bekleyen_cikis_outbox_fail_closed_paper_ve_canli(e):
    pos = SimpleNamespace(pair="BTC/USDT", setup="HB1")
    e.state.outbox_pending = lambda: [SimpleNamespace(kind="exit", trade_id=9)]   # type: ignore[method-assign]
    e.state.get_position = lambda tid: pos                                        # type: ignore[method-assign]
    paper = _go(e, _hb1(4242))
    assert paper.code == "hb1_olay_bekleyen_cikis" and paper.event.veto_reason == "gate:hb1_olay_bekleyen_cikis"
    e.g.cfg = dataclasses.replace(CFG, mode="live")
    assert _go(e, _hb1(4243)).code == "hb1_olay_bekleyen_cikis"                   # canli = kagit
    assert _go(e, _row()).action == "enter"                                       # T1 etkilenmez
    e.state.outbox_pending = lambda: []                                           # type: ignore[method-assign]
    assert _go(e, _hb1(4243)).action == "enter"


def test_pencere_sabiti_kolla_esit():
    from trader_engine.gates import HB1_OLAY_PENCERE
    from trader_engine.strategies.arms import hb1
    assert HB1_OLAY_PENCERE == timedelta(hours=hb1.HS_PENCERE_SAAT)
