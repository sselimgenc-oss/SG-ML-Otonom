"""Emtia hafta sonu kapisi (23.11 kullanici karari b): hafta sonu emtiada YENI giris yok; kripto/hisse ve acik pozisyon etkilenmez.
Pencere tek kaynak trader_core.arm_time.session_tag: emtia Cum 21:00 UTC -> Paz 23:00 UTC (Paz 22:00 hala kapali)."""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import ledger as L
from trader_engine.clock import SimClock
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate, NoVeto
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame
from trader_engine.types import SymbolRules

from test_engine_05_impl_smoke import _params, _row  # noqa: E402

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
CFG = load_cli_config(ROOT / "config", "learner", "paper")
H = timedelta(hours=1)
SAT = datetime(2026, 12, 5, 12, 0, tzinfo=UTC)          # Cumartesi
FRI = datetime(2026, 12, 4, 0, 0, tzinfo=UTC)           # Cuma
SUN = datetime(2026, 12, 6, 0, 0, tzinfo=UTC)           # Pazar


def _kur(tmp_path, mode):
    clock = SimClock(SAT + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        for d in ("2026-12-04", "2026-12-05", "2026-12-06"):
            state.kv_set(f"day_start:{d}", 1000.0)
    state.open_positions = lambda: []   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(dataclasses.replace(CFG, mode=mode), led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock,
                  broker, rules)
    return SimpleNamespace(g=g, led=led, state=state, clock=clock)


@pytest.fixture(params=["paper", "live"])
def env(request, tmp_path):
    e = _kur(tmp_path, request.param)
    yield e
    e.state.close()
    e.led.close()


def _go(e, pair, D):
    e.g.clock = SimClock(D + timedelta(seconds=5))
    fr = SignalFrame(pair=pair, status="ok", detail=None,
                     last=_row(pair=pair, bar_open_ts=D - H, bar_close_ts=D), table=None, trigger_bar=(110.0, 99.0, 5.0))
    return e.g.decide(fr, D, e.g.pre(D, "1h", True, "1h"), 1)


def test_cumartesi_emtia_reddedilir_ve_defter_yazar(env):
    o = _go(env, "XAU/USDT", SAT)
    assert o.action == "skip" and o.code == "emtia_hafta_sonu"
    assert o.event.veto_reason == "gate:emtia_hafta_sonu" and o.event.skip_reason == "session_closed" and o.size is None
    assert env.g.counters["emtia_hafta_sonu"] == 1 and env.g.counters["skip:emtia_hafta_sonu"] == 1
    did = env.led.record_decision(o.event)
    got = env.led.get_decision(did)
    assert got.veto_reason == "gate:emtia_hafta_sonu" and got.final_action == "skipped"


@pytest.mark.parametrize("pair", ["XAU/USDT", "XAG/USDT", "BZ/USDT", "COPPER/USDT"])
def test_tum_emtia_ciftleri(env, pair):
    assert _go(env, pair, SAT).code == "emtia_hafta_sonu"


@pytest.mark.parametrize("D,beklenen", [
    (FRI.replace(hour=20, minute=59), "enter"),
    (FRI.replace(hour=21, minute=0), "emtia_hafta_sonu"),
    (SUN.replace(hour=21, minute=59), "emtia_hafta_sonu"),
    (SUN.replace(hour=22, minute=59), "emtia_hafta_sonu"),   # mevcut seans tanimi: Paz 23:00'a kadar kapali (arm_time.session_tag)
    (SUN.replace(hour=23, minute=0), "enter"),
])
def test_sinirlar(env, D, beklenen):
    o = _go(env, "XAU/USDT", D)
    if beklenen == "enter":      # kapidan gecti (canlida bu testte ML filtresi yok -> sonraki kapi fail-closed olabilir; bizim kapi tetiklenmemeli)
        assert o.code != "emtia_hafta_sonu", o.code
    else:
        assert o.code == beklenen, (o.action, o.code)


@pytest.mark.parametrize("pair", ["BTC/USDT", "NVDA/USDT"])
def test_kripto_ve_hisse_cumartesi_serbest(env, pair):
    o = _go(env, pair, SAT)
    assert o.code != "emtia_hafta_sonu" and env.g.counters["emtia_hafta_sonu"] == 0


def test_acik_emtia_pozisyonu_etkilenmez(env):
    env.state.position_for_pair = lambda p: SimpleNamespace(pair=p)   # type: ignore[method-assign]
    o = _go(env, "XAU/USDT", SAT)
    assert o.action == "ignore" and o.code == "position_exists" and env.g.counters["emtia_hafta_sonu"] == 0


def test_paper_live_esdeger(tmp_path):
    sonuc = {}
    for mode in ("paper", "live"):
        d = tmp_path / mode
        d.mkdir()
        e = _kur(d, mode)
        try:
            sonuc[mode] = [(_go(e, "XAU/USDT", t).code == "emtia_hafta_sonu", _go(e, "BTC/USDT", t).code == "emtia_hafta_sonu")
                           for t in (FRI.replace(hour=20, minute=59), SAT, SUN.replace(hour=23))]
        finally:
            e.state.close()
            e.led.close()
    assert sonuc["paper"] == sonuc["live"] == [(False, False), (True, False), (False, False)]


def test_sinif_bilinmiyorsa_engellemez(env):
    o = _go(env, "FOO/USDT", SAT)      # kume yok -> asset_class kripto
    assert o.code != "emtia_hafta_sonu"
