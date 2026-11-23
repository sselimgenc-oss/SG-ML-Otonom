"""HB1 'ayni haberle yeniden giris yok' kapisi: ayni olay -> red; yeni olay / ters yon / baska kol serbest; defter hatasi yalniz HB1'i durdurur;
olay kimligi ML ozelliklerine girmez; canli = kagit parite."""
from __future__ import annotations

import dataclasses
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import ledger as L
from trader_core import ml_live_v2 as MV
from trader_engine import ogrenme_filtre as OF
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
    e.led.last_closed_decision_features = boom                            # type: ignore[method-assign]
    o = _go(e, _hb1(4242))
    assert o.action == "skip" and o.code == "hb1_olay_okunamadi" and o.event.veto_reason == "gate:hb1_olay_okunamadi"
    assert e.g.counters["hb1_olay_okunamadi"] == 1
    assert _go(e, _row()).action == "enter"                              # T1 etkilenmez


def test_olay_kimligi_ml_ozelliklerine_girmez(e):
    row = _hb1(4242)
    f = _features(row)
    assert f["hb1_olay"] == "4242" and isinstance(f["hb1_olay"], str)     # metin: sayisal ozellik cikarimi atlar
    for k in ("edge_dist_atr", "hb1_body", "hb1_wick", "hb1_rr"):
        assert f.get(k) != 4242.0
    d = OF.ozellikler(side="long", regime="trend_up", atr_ratio=1.0, session_tag=None, pair="BTC/USDT", planned_entry=100.0,
                      planned_stop=98.0, features=f)
    assert not any("hb1_olay" in k for k in d)
    for names in MV.RECIPE_NAMES.values():
        assert not any("hb1_olay" in n for n in names)
    assert not any("hb1_olay" in n for n in MV.SETUP_BASE_FEATURES)
    assert hb1_olay_of(_hb1(0)) is None and hb1_olay_of(_row()) is None


def test_defterde_olay_kimligi_karar_ozelligi_olarak_yazilir(e):
    _kapat(e, _hb1(777), 1)
    assert e.led.last_closed_decision_features("HB1@1h", "BTC/USDT", "long")["hb1_olay"] == "777"
    assert e.led.last_closed_decision_features("HB1@1h", "BTC/USDT", "short") is None


def test_canli_kagit_parite(e):
    _kapat(e, _hb1(4242), 1)
    paper = _go(e, _hb1(4242))
    e.g.cfg = dataclasses.replace(CFG, mode="live")
    e.g.ml_filtre = type("F", (), {"karar": lambda self, arm, oz, simdi: OF.Karar(True, 0.9, "ok")})()
    live = _go(e, _hb1(4242))
    assert (paper.action, paper.code, paper.event.veto_reason) == (live.action, live.code, live.event.veto_reason)
    assert live.code == "hb1_ayni_olay"
    assert _go(e, _hb1(4243)).action == "enter"
