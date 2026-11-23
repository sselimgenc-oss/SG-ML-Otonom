"""23.11 canli = kagit: bagimsiz inceleme duzeltmeleri. (1) canli TF-kapanisi telafisi, (2) optional cift position_risk reddi acilisi
durdurmaz, (3) canlida ML filtresi yoksa/suresi dolduysa giris YOK (fail-closed) + saglik bloku."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from decimal import Decimal

import pytest
import test_canli_kagit_parite as P
import test_live_broker_impl_smoke as LB
from trader_engine import ogrenme_filtre as OF
from trader_engine.brokers.binance_futures import LiveBroker
from trader_engine.errors import EngineExit
from trader_engine.exchange.binance_rest import ExchangeReject
from trader_engine.strategy_runner import SignalFrame

UTC = timezone.utc


# ----------------------------------------------------------------------------------------------- 1. canli TF telafisi
class _Sig:
    def __init__(self):
        self.frames = []

    def frame(self, pair, D, params, vid):
        self.frames.append(D)
        return SignalFrame(pair=pair, status="ok", detail=None, last=None, table=None)

    def exit_context(self, pair, pos, D):
        return SimpleNamespace(bar_close_ts=D, last_close=1.0)


def _pos(tf, sig_ts, tid=1):
    return SimpleNamespace(trade_id=tid, status="open", pair="BTC/USDT", trigger_tf=tf, signal_bar_close_ts=sig_ts, setup="T1")


def _catchup_engine(tmp_path, pos_list):
    cfg, eng = P._live_engine(tmp_path)
    assert eng._multi_tf
    sig, exits = _Sig(), []
    eng.signals = sig
    eng._frame_params = lambda: None
    eng.state.open_positions = lambda: pos_list
    eng.strategy.exit_policy = lambda: SimpleNamespace(
        evaluate=lambda pos, ctx: SimpleNamespace(kind="exit", reason="time_stop"))
    eng._submit_exit = lambda pos, reason, D, quote=False: exits.append((pos.trade_id, reason, D))
    return eng, sig, exits


def test_canli_kacirilan_4s_kapanisi_sonraki_adimda_degerlendirilir(tmp_path):
    t0 = datetime(2026, 11, 23, 4, 0, tzinfo=UTC)
    eng, sig, exits = _catchup_engine(tmp_path, [_pos("4h", t0)])
    try:
        D = datetime(2026, 11, 23, 10, 15, tzinfo=UTC)               # 08:00 4s kapanisi atlandi; D bir 4s siniri degil
        eng._exits(D, {})
        assert exits == [(1, "time_stop", datetime(2026, 11, 23, 8, 0, tzinfo=UTC))]      # son kapanmis 4s bar siniri
        assert sig.frames == [datetime(2026, 11, 23, 8, 0, tzinfo=UTC)]                   # baglam o sinir icin kuruldu; giris yok
        eng._exits(D + timedelta(minutes=15), {})                                          # ayni sinir tekrar degerlendirilmez
        assert len(exits) == 1
        eng._exits(datetime(2026, 11, 23, 12, 15, tzinfo=UTC), {})                         # yeni sinir (12:00) yeniden telafi
        assert [e[2].hour for e in exits] == [8, 12]
    finally:
        eng.state.close()
        eng.ledger.close()


def test_canli_telafi_giristen_onceki_siniri_degerlendirmez(tmp_path):
    t0 = datetime(2026, 11, 23, 9, 0, tzinfo=UTC)                     # giris karari 09:00; sonraki 4s siniri 12:00
    eng, sig, exits = _catchup_engine(tmp_path, [_pos("4h", t0)])
    try:
        eng._exits(datetime(2026, 11, 23, 10, 15, tzinfo=UTC), {})    # B=08:00 <= giris: telafi yok
        assert exits == [] and sig.frames == []
        eng._exits(datetime(2026, 11, 23, 12, 0, tzinfo=UTC), {"BTC/USDT": SignalFrame(
            pair="BTC/USDT", status="ok", detail=None, last=None, table=None)})   # normal sinir: eskisi gibi
        assert [e[2].hour for e in exits] == [12]
    finally:
        eng.state.close()
        eng.ledger.close()


# ----------------------------------------------------------------------------------------------- 2. optional position_risk
def _broker_with(optional, *, held_doge=False, reject_core=False):
    b0, ex, clock = LB.build(startup=False)
    if held_doge:
        ex.pos["DOGEUSDT"] = {"amt": Decimal("5"), "entry": Decimal("1"), "upd": 0}
    real = b0._rest.position_risk

    def pr(symbol=None, **kw):
        if symbol == "DOGEUSDT" or (reject_core and symbol == "XRPUSDT"):
            raise ExchangeReject("invalid symbol", code=-1121, http=400, msg="Invalid symbol.")
        return real(symbol, **kw)
    b0._rest.position_risk = pr
    b = LiveBroker(b0._live, "testnet", 3, [LB.XRP, LB.DOGE], b0._rest, clock, 0.0005, environ=None, optional_pairs=optional)
    return b


def test_optional_cift_position_risk_reddi_acilisi_durdurmaz_ve_cift_hazirlanmaz(caplog):
    b = _broker_with((LB.DOGE,))
    b.startup_check()                                                  # EngineExit YOK
    assert LB.XRP in b._prepared and LB.DOGE not in b._prepared      # TradFi cift hazirlanmadi: giris yok
    assert b._ctr["optional_position_risk_failed"] == 1
    assert any("optional_position_risk_failed:DOGE" in r.getMessage() for r in caplog.records)


def test_optional_cift_acik_pozisyonu_varsa_sessiz_atlanmaz_critical(caplog):
    import logging
    b = _broker_with((LB.DOGE,), held_doge=True)
    with caplog.at_level(logging.WARNING):
        b.startup_check()
    recs = [r for r in caplog.records if "optional_position_risk_failed:DOGE" in r.getMessage()]
    assert recs and recs[0].levelno == logging.CRITICAL and "held=True" in recs[0].getMessage()
    assert LB.DOGE not in b._prepared


def test_cekirdek_cift_position_risk_reddi_eskisi_gibi_fail_closed():
    b = _broker_with((LB.DOGE,), reject_core=True)                    # XRP optional degil
    with pytest.raises(EngineExit) as ei:
        b.startup_check()
    assert ei.value.code == 8
    b2 = _broker_with(())                                              # DOGE optional degilken de fail-closed
    with pytest.raises(EngineExit):
        b2.startup_check()


def test_build_live_broker_optional_pairs_gecirir():
    src = (P.ROOT / "src" / "trader_engine" / "engine.py").read_text(encoding="utf-8")
    assert "optional_pairs=cfg.optional_pairs" in src


# ----------------------------------------------------------------------------------------------- 3. ML filtresi canlida fail-closed
def _gate_outcome(tmp_path, *, mode, filtre):
    import dataclasses

    import test_etiket_kurallari_gate as G
    e = G._kur(tmp_path)
    e.g.cfg = dataclasses.replace(G.CFG, mode=mode, ml_mode="active")
    e.g.ml_filtre = filtre
    e.g._etiket_karari = lambda *a, **k: None
    try:
        return G._go(e), e
    except Exception:
        e.state.close()
        e.led.close()
        raise


class _Yok:
    def karar(self, arm, oz, simdi):
        return OF.Karar(True, None, "filtre_yok")


class _Hata:
    def karar(self, arm, oz, simdi):
        raise RuntimeError("bozuk")


class _Ok:
    def karar(self, arm, oz, simdi):
        return OF.Karar(True, 0.9, "ok")


def _kapat(e):
    e.state.close()
    e.led.close()


@pytest.mark.parametrize("filtre", [None, _Yok(), _Hata()])
def test_canlida_filtre_yoksa_bozuksa_giris_yok(tmp_path, filtre):
    o, e = _gate_outcome(tmp_path, mode="live", filtre=filtre)
    try:
        assert o.action == "skip" and o.event.skip_reason == "ml_filter"
        assert o.event.veto_reason == "gate:ml_filter_unavailable"
        assert e.g.counters["ml_filtre_kapali_blok"] == 1
    finally:
        _kapat(e)


@pytest.mark.parametrize("filtre", [None, _Yok(), _Hata()])
def test_kagitta_filtre_yoksa_giris_serbest_fail_open(tmp_path, filtre):
    o, e = _gate_outcome(tmp_path, mode="paper", filtre=filtre)
    try:
        assert o.action == "enter"
    finally:
        _kapat(e)


def test_canlida_gecerli_filtre_girisi_engellemez(tmp_path):
    o, e = _gate_outcome(tmp_path, mode="live", filtre=_Ok())
    try:
        assert o.action == "enter"
    finally:
        _kapat(e)


def test_filtre_saglik_dizin_yok_paket_yok_suresi_dolmus(tmp_path):
    now = datetime(2026, 11, 23, tzinfo=UTC)
    dep = OF.FiltreDeposu(tmp_path / "yok")
    if dep.calisiyor:
        assert dep.saglik(now, {"M1"})[0] == "no_model" and "dizin" in dep.saglik(now, {"M1"})[1]
    (tmp_path / "var").mkdir()
    dep2 = OF.FiltreDeposu(tmp_path / "var")
    st = dep2.saglik(now, {"M1"})[0]
    assert st == "no_model"                                            # dizin var ama paket yok
    # paket dosyasi var ama bozuk JSON => gecersiz (expired etiketi: gecerli paket yok)
    if dep2.calisiyor:
        (tmp_path / "var" / f"{dep2._mod[0]._guvenli_ad(OF.aile_kimligi('M1'))}.json").write_text("{bozuk")
        assert dep2.saglik(now, {"M1"})[0] == "expired"
    kapali = OF.FiltreDeposu(tmp_path / "var", kapali_=True)
    assert kapali.saglik(now, {"M1"})[0] == "no_model"


def test_canli_status_ml_blogu_saglik_icin_no_model_ve_entries_blocked(tmp_path):
    cfg, eng = P._live_engine(tmp_path)
    try:
        m = eng._ml_status(datetime(2026, 11, 23, tzinfo=UTC))
        assert m["mode"] == "active" and m["state"] in ("no_model", "expired") and m["entries_blocked"] is True
        assert m["error"]
        # health bu blogu CRIT ml_no_model/ml_expired olarak okur (IMMEDIATE_CODES: Telegram'a gider)
        from trader_core import health as H
        assert {"ml_no_model", "ml_expired"} <= set(H.IMMEDIATE_CODES)
    finally:
        eng.state.close()
        eng.ledger.close()


def test_canli_status_ml_blogu_gecerli_paketle_ok(tmp_path, monkeypatch):
    cfg, eng = P._live_engine(tmp_path)
    try:
        exp = datetime(2026, 12, 20, tzinfo=UTC)
        eng.gate.ml_filtre = SimpleNamespace(saglik=lambda now, aileler: ("ok", None, exp))
        m = eng._ml_status(datetime(2026, 11, 23, tzinfo=UTC))
        assert m["state"] == "ok" and m["entries_blocked"] is False and m["expires_at"] == exp.isoformat()
    finally:
        eng.state.close()
        eng.ledger.close()
