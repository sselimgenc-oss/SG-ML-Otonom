"""Seans disi giris kapisi (23.11 kullanici karari, fikir 9 a): hafta sonu / tatil / buyuk haber penceresinde hisse+emtiada YENI giris yok.
Acik pozisyon ve kripto etkilenmez; kagit = canli. Takvim config/seans_takvimi.json (hash-pinli engine.*.json degil).
Not: ET->UTC DST'ye gore: kis 16:00 ET = 21:00 UTC, 09:30 ET = 14:30 UTC; yaz 20:00 / 13:30 UTC."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import ledger as L
from trader_engine import seans_disi as SD
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
XAU, NVDA, BTC = "XAU/USDT", "NVDA/USDT", "BTC/USDT"


def u(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


SAT = u(2026, 12, 5, 12, 0)                  # Cumartesi (kis)
KOD = {"hafta": "seans_disi_hafta_sonu", "tatil": "seans_disi_tatil", "haber": "seans_disi_haber"}


def _kur(tmp_path, mode, takvim=None):
    clock = SimClock(SAT + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        for m, days in ((7, (3, 6, 7)), (11, (26, 27, 29)), (12, (1, 4, 5, 6, 8, 9, 10)), (1, (12,))):
            for d in days:
                state.kv_set(f"day_start:{2026 if m != 1 else 2027}-{m:02d}-{d:02d}", 1000.0)
        for d in ("2026-07-03", "2026-07-04", "2026-07-06", "2026-06-29", "2026-07-02", "2026-07-07"):
            state.kv_set(f"day_start:{d}", 1000.0)
    state.open_positions = lambda: []   # type: ignore[method-assign]
    broker = SimpleNamespace(account=lambda: SimpleNamespace(equity=1000.0, wallet=1000.0))
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(dataclasses.replace(CFG, mode=mode), led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock,
                  broker, rules)
    if takvim is not None:
        g.seans_takvimi_yolu = str(takvim)
    return SimpleNamespace(g=g, led=led, state=state)


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


def _gecer(o):
    """Seans disi kapisi tetiklenmedi (sonraki kapilar - ornegin canlida ML filtresi - ayri konu)."""
    return not o.code.startswith("seans_disi_")


# ------------------------------------------------------------------------------------------------ emtia hafta sonu
def test_cumartesi_emtia_reddedilir_ve_defter_yazar(env):
    o = _go(env, XAU, SAT)
    assert o.action == "skip" and o.code == KOD["hafta"]
    assert o.event.veto_reason == "gate:seans_disi_hafta_sonu" and o.event.skip_reason == "session_closed" and o.size is None
    assert env.g.counters[KOD["hafta"]] == 1 and env.g.counters["skip:" + KOD["hafta"]] == 1
    got = env.led.get_decision(env.led.record_decision(o.event))
    assert got.veto_reason == "gate:seans_disi_hafta_sonu" and got.final_action == "skipped"


@pytest.mark.parametrize("pair", [XAU, "BZ/USDT"])      # 26.11 sahip karari: evrende yalniz XAU ve BZ
def test_tum_emtia_ciftleri(env, pair):
    assert _go(env, pair, SAT).code == KOD["hafta"]


@pytest.mark.parametrize("D,red", [
    (u(2026, 12, 4, 21, 59), False), (u(2026, 12, 4, 22, 0), True),        # kis: Cum 17:00 ET = 22:00Z
    (u(2026, 12, 6, 22, 59), True), (u(2026, 12, 6, 23, 0), False),        # kis: Paz 18:00 ET = 23:00Z
    (u(2026, 7, 17, 20, 59), False), (u(2026, 7, 17, 21, 0), True),        # yaz: Cum 21:00Z
    (u(2026, 7, 19, 21, 59), True), (u(2026, 7, 19, 22, 0), False),        # yaz: Paz 22:00Z
])
def test_emtia_sinirlar(env, D, red):
    o = _go(env, XAU, D)
    assert (o.code == KOD["hafta"]) is red, (o.action, o.code)


def test_acik_emtia_pozisyonu_etkilenmez(env):
    env.state.position_for_pair = lambda p: SimpleNamespace(pair=p)   # type: ignore[method-assign]
    o = _go(env, XAU, SAT)
    assert o.action == "ignore" and o.code == "position_exists" and env.g.counters[KOD["hafta"]] == 0


# ------------------------------------------------------------------------------------------------ hisse hafta sonu (DST dogru)
def test_hisse_cumartesi_reddedilir(env):
    assert _go(env, NVDA, SAT).code == KOD["hafta"]


@pytest.mark.parametrize("D,red", [
    (u(2026, 12, 4, 20, 59), False), (u(2026, 12, 4, 21, 0), True),        # kis: Cum kapanis 21:00 UTC
    (u(2026, 12, 7, 14, 29), True), (u(2026, 12, 7, 14, 30), False),       # kis: Pzt acilis 14:30 UTC
    (u(2026, 12, 7, 13, 29), True), (u(2026, 12, 7, 13, 30), True),        # 13:30 UTC kis = 08:30 ET: hala kapali
])
def test_hisse_kis_sinirlari(env, D, red):
    assert (_go(env, NVDA, D).code == KOD["hafta"]) is red


@pytest.mark.parametrize("D,red", [
    (u(2026, 7, 17, 19, 59), False), (u(2026, 7, 17, 20, 0), True),        # yaz: Cum kapanis 20:00 UTC
    (u(2026, 7, 20, 13, 29), True), (u(2026, 7, 20, 13, 30), False),       # yaz: Pzt acilis 13:30 UTC
])
def test_hisse_yaz_sinirlari(tmp_path, D, red):
    for mode in ("paper", "live"):
        d = tmp_path / mode
        d.mkdir()
        e = _kur(d, mode)
        try:
            o = _go(e, NVDA, D)
            assert (o.code == KOD["hafta"]) is red, (mode, o.code)
        finally:
            e.state.close()
            e.led.close()


# ------------------------------------------------------------------------------------------------ kripto her zaman serbest
@pytest.mark.parametrize("D", [SAT, u(2026, 12, 6, 3, 0), u(2026, 11, 26, 15, 0), u(2026, 12, 9, 18, 0)])
def test_kripto_her_zaman_serbest(env, D):
    assert _gecer(_go(env, BTC, D))
    assert not any(k.startswith("seans_disi_") for k in env.g.counters)


def test_sinif_bilinmiyorsa_engellemez(env):
    assert _gecer(_go(env, "FOO/USDT", SAT))       # kume yok -> asset_class kripto


# ------------------------------------------------------------------------------------------------ tatil
def test_sakin_gun_gecer_ama_tatil_reddeder(env):
    assert _gecer(_go(env, NVDA, u(2026, 11, 25, 15, 0)))                       # Carsamba
    o = _go(env, NVDA, u(2026, 11, 26, 15, 0))                                  # Sukran Gunu
    assert o.code == KOD["tatil"] and o.event.veto_reason == "gate:seans_disi_tatil"
    assert env.g.counters[KOD["tatil"]] == 1
    assert _go(env, XAU, u(2026, 11, 26, 15, 0)).code == KOD["tatil"]           # emtiaya da ayni liste


def test_tatil_penceresi_onceki_kapanistan_sonraki_acilisa(env):
    assert _gecer(_go(env, NVDA, u(2026, 11, 25, 20, 59)))                      # Car 15:59 ET
    assert _go(env, NVDA, u(2026, 11, 25, 21, 0)).code == KOD["tatil"]          # Car 16:00 ET
    assert _go(env, NVDA, u(2026, 11, 27, 14, 29)).code == KOD["tatil"]         # Cum 09:29 ET
    assert _gecer(_go(env, NVDA, u(2026, 11, 27, 14, 30)))                      # Cum 09:30 ET


def test_yaz_tatili_dst(env):
    # 3 Temmuz 2026 (Cuma, gozlenen 4 Temmuz): onceki islem gunu Per 2 Tem 16:00 EDT = 20:00 UTC; sonraki Pzt 6 Tem 09:30 EDT = 13:30 UTC
    assert _gecer(_go(env, NVDA, u(2026, 7, 2, 19, 59)))
    assert _go(env, NVDA, u(2026, 7, 2, 20, 0)).code == KOD["tatil"]
    assert _go(env, NVDA, u(2026, 7, 6, 13, 29)).code.startswith("seans_disi_") and _gecer(_go(env, NVDA, u(2026, 7, 6, 13, 30)))


# ------------------------------------------------------------------------------------------------ haber (FOMC 2026-01-28 19:00 UTC)
def _fomc_takvim(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"tatiller": [], "olaylar": [{"tur": "FOMC", "ts": "2026-12-09T19:00:00Z", "durum": "confirmed"}]}))
    return p


def test_haber_penceresi(tmp_path):
    for mode in ("paper", "live"):
        d = tmp_path / mode
        d.mkdir()
        e = _kur(d, mode, takvim=_fomc_takvim(d))
        try:
            assert _gecer(_go(e, NVDA, u(2026, 12, 9, 16, 59)))                 # penceredan 1 dk once
            for D in (u(2026, 12, 9, 17, 0), u(2026, 12, 9, 19, 0), u(2026, 12, 9, 19, 29)):
                o = _go(e, NVDA, D)
                assert o.code == KOD["haber"] and o.event.veto_reason == "gate:seans_disi_haber", D
                assert _go(e, XAU, D).code == KOD["haber"]
            assert _gecer(_go(e, NVDA, u(2026, 12, 9, 19, 30)))                 # +30 dk dahil degil
            assert _gecer(_go(e, BTC, u(2026, 12, 9, 19, 0)))                   # kripto serbest
            assert e.g.counters[KOD["haber"]] == 6
        finally:
            e.state.close()
            e.led.close()


# ------------------------------------------------------------------------------------------------ takvim eksik/bozuk -> engellemez, sayar
@pytest.mark.parametrize("icerik", [None, "{bozuk", json.dumps({"tatiller": [{"tarih": "yanlis"}], "olaylar": []})])
def test_takvim_eksik_veya_bozuk_engellemez(tmp_path, icerik):
    p = tmp_path / "t.json"
    if icerik is not None:
        p.write_text(icerik)
    e = _kur(tmp_path, "paper", takvim=p)
    try:
        assert _gecer(_go(e, NVDA, u(2026, 11, 26, 15, 0)))                     # tatil ama takvim yok -> serbest
        assert e.g.counters[SD.SAYAC_TAKVIM_YOK] == 1
        assert _go(e, NVDA, SAT).code == KOD["hafta"]                           # hafta sonu takvimsiz calisir
        assert _gecer(_go(e, BTC, u(2026, 11, 26, 15, 0))) and e.g.counters[SD.SAYAC_TAKVIM_YOK] == 2
    finally:
        e.state.close()
        e.led.close()


def test_gercek_takvim_dosyasi_gecerli_ve_2026_2027_kapsar():
    t = SD.yukle()
    assert t is not None and len(t.tatil_pencereleri) == 20 and len(t.olaylar) == 64
    yillar = {o.year for o in t.olaylar}
    assert yillar == {2026, 2027}
    raw = json.loads((ROOT / "config" / "seans_takvimi.json").read_text())
    assert {o["durum"] for o in raw["olaylar"]} <= {"confirmed", "estimated"}


# ------------------------------------------------------------------------------------------------ parite
def test_paper_live_esdeger(tmp_path):
    sonuc = {}
    ts = (u(2026, 12, 4, 20, 59), SAT, u(2026, 12, 6, 22, 0), u(2026, 11, 26, 15, 0), u(2026, 12, 9, 19, 0))
    for mode in ("paper", "live"):
        d = tmp_path / mode
        d.mkdir()
        e = _kur(d, mode)
        try:
            sonuc[mode] = [tuple(_go(e, p, t).code.startswith("seans_disi_") for p in (XAU, NVDA, BTC)) for t in ts]
        finally:
            e.state.close()
            e.led.close()
    assert sonuc["paper"] == sonuc["live"]
    assert sonuc["paper"][1] == (True, True, False)
