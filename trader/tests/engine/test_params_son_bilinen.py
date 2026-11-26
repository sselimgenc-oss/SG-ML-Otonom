"""Paket 2 / D1 (26.11 sahip karari #9): parametre defteri okunamazken (YALNIZ kagit) cikislar SON BILINEN surumle surer; girisler kapali kalir."""
from __future__ import annotations

import dataclasses

from test_engine_05_spec import BTC, Env, M1, T0, H

from trader_core import signals

TRAIL = 3.5                                                    # varsayilan (3.0) DEGIL


def _params(**kw):
    p = dataclasses.asdict(signals.DEFAULT_SIGNAL_PARAMS)
    p.update(kw)
    return p


def _once(tmp_path):
    """Defterde etkin surum (trail_atr = 3.5); motor kosar (son_params yazilir) ve kapanir."""
    e = Env(tmp_path, ledger_start_params=_params(trail_atr=TRAIL))
    e.start()
    assert e.engine._params_kaynak == "defter" and e.state.kv_get("son_params")["params"]["trail_atr"] == TRAIL
    return e


def test_son_bilinen_cikislar_etkin_surumle_girisler_kapali(tmp_path):
    e = _once(tmp_path)
    vid = e.version_id
    e.decide(T0)
    e.close()
    e2 = Env(tmp_path)                                         # YENI motor; defter okunamiyor
    e2.ledger.fail_params = True
    try:
        e2.start()
        eng = e2.engine
        assert eng._frame_params().trail_atr == TRAIL and eng._frame_params().trail_atr != signals.DEFAULT_SIGNAL_PARAMS.trail_atr
        assert eng._params_kaynak == "son_bilinen" and eng._version_id == vid and eng._act_id is None and eng._params_ok is False
        assert eng._c["params_son_bilinen"] == 1
        assert eng.status_fields()["params_kaynak"] == "son_bilinen"
        e2.signal(T0 + H, (BTC,))
        e2.decide(T0 + H)
        assert eng._live_gate_code(None, False) == "params_unavailable"        # saglik izleyicisi bu kodu CRIT alarm yapar (test_health_engine_status)
        assert e2.pos(BTC) is None                                              # giris kapali
        assert any(d.veto_reason == "gate:params_unavailable" or d.skip_reason for d in e2.decisions())
    finally:
        e2.close()


def test_son_bilinen_modda_acik_pozisyon_stopla_kapanir(tmp_path):
    e = _once(tmp_path)
    p = e.open_pos(BTC, T0)
    assert p is not None
    tid = p.trade_id
    e.close()
    e2 = Env(tmp_path, start=T0 + H)
    e2.ledger.fail_params = True
    try:
        e2.start()
        assert e2.engine._params_kaynak == "son_bilinen" and e2.engine._params_ok is False
        e2.step(T0 + H + M1, pairs=(BTC,), price=98.5, hi=99.0, lo=97.5)
        t = e2.real_ledger.get_trade(tid)
        assert t.exit_reason == "stop" and t.realized_pnl < 0                   # cikislar ASLA atlanmaz
    finally:
        e2.close()


def test_kv_kaydi_yokken_varsayilan_ve_ayri_alarm(tmp_path):
    e = Env(tmp_path)                                          # hic motor kosmadi: kv'de son_params yok
    e.ledger.fail_params = True
    try:
        e.start()
        assert e.state.kv_get("son_params") is None
        assert e.engine._params_kaynak == "varsayilan" and e.engine._c["params_varsayilan"] == 1 and e.engine._c["params_son_bilinen"] == 0
        assert e.engine._frame_params().trail_atr == signals.DEFAULT_SIGNAL_PARAMS.trail_atr
        assert e.engine._params_ok is False
    finally:
        e.close()


def test_defter_duzelince_defter_kaynagi_ve_girisler_acilir(tmp_path):
    _once(tmp_path).close()
    e = Env(tmp_path)
    e.ledger.fail_params = True
    try:
        e.start()
        assert e.engine._params_kaynak == "son_bilinen"
        e.ledger.fail_params = False
        e.signal(T0, (BTC,))
        e.decide(T0)
        assert e.engine._params_kaynak == "defter" and e.engine._params_ok is True and e.engine._act_id is not None
        assert e.engine._frame_params().trail_atr == TRAIL
        assert e.pos(BTC) is not None                                           # girisler yeniden acik
    finally:
        e.close()


def test_backtest_motorunda_kv_okunmaz_ve_yazilmaz(tmp_path):
    e = Env(tmp_path, mode="backtest")
    e.ledger.fail_params = True
    try:
        e.start()
        assert e.state.kv_get("son_params") is None
        assert e.engine._params_kaynak == "defter" and e.engine._params_ok is False
        assert e.engine._c["params_son_bilinen"] == 0 and e.engine._c["params_varsayilan"] == 0
    finally:
        e.close()
    (tmp_path / "b").mkdir()
    e2 = Env(tmp_path / "b", mode="backtest")                  # basarili okumada backtest kv'ye yazmaz
    try:
        e2.start()
        assert e2.state.kv_get("son_params") is None
    finally:
        e2.close()


def test_telegram_metni_son_bilinen_eki():
    from trader_core import telegram as TG
    assert TG.neden_tr("params_unavailable") == "strateji ayarları yüklenemedi"
    assert TG.neden_tr("params_unavailable", "son_bilinen").endswith("(çıkışlar son bilinen ayarla sürüyor)")
    st = {"entries_open": False, "gate_code": "params_unavailable", "params_kaynak": "son_bilinen"}
    assert "son bilinen ayarla" in TG._durum_satiri(st, "", False)
    assert TG._durum_satiri({"entries_open": False, "gate_code": "stale_data"}, "", False) == "Yeni işlemler kapalı."
