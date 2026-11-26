"""Paket 2 / D2 (26.11 sahip karari #10): ML1 acikken kapi/ogrenici kurulamazsa YENI islem acilmaz (yalniz kagit; cikislar ASLA kapanmaz).

`ml1_kapi_yok` (kurulum arizasi; saglikli yeniden baslatma kaldirir) ve `ml1_paket_bozuk` (ogrenici YOKKEN dosya var ama gecersiz).
Paket dosyasi hic YOKKEN (ogrenme asamasi) engel KURULMAZ: "ogrenmede herkes gecer" kurali degismez."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_engine_05_spec import BTC, Env, FakeSignalSource, H, M1, T0

from trader_engine import engine as EN
from trader_engine import ml1_gate as MG


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml1"))


@pytest.fixture(autouse=True)
def _ml1_kaynagi(monkeypatch):
    monkeypatch.setattr(FakeSignalSource, "ml1", None, raising=False)         # motor ML1 kapisini bu kaynaga baglayabilsin


def _ml1(tmp, *, ogrenme: bool):
    d = {"aktif": True, "paket_yolu": str(tmp / "models" / "ml1_package.json")}
    d["ogrenme"] = {"aktif": ogrenme, "kuru": False, "min_islem": 200, "min_islem_tf": 0, "esik": 0.50}
    return d


def _patla(monkeypatch):
    def boom(self, *a, **k):
        raise RuntimeError("kapi kurulamadi")
    monkeypatch.setattr(MG.Ml1Gate, "__init__", boom)


def test_kapi_kurulamayinca_engel_ve_giris_vetosu(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        _patla(m)
        e = Env(tmp_path, ml1=_ml1(tmp_path, ogrenme=True))
        try:
            assert e.engine._ml1_ariza.startswith("kapi:RuntimeError")
            e.start()
            assert e.state.block_has("ml1_kapi_yok")
            e.signal(T0, (BTC,))
            e.decide(T0)
            assert e.pos(BTC) is None                                       # pozisyon acilmaz
            dec = [d for d in e.decisions() if d.pair == BTC]
            assert dec and dec[-1].veto_reason == "gate:ml1_kapi_yok"       # gate: vetosu
        finally:
            e.close()


def test_kapi_ariza_modunda_acik_pozisyon_stopla_kapanir(tmp_path, monkeypatch):
    e0 = Env(tmp_path)
    assert e0.start() is not None
    assert e0.open_pos(BTC, T0) is not None
    tid = e0.pos(BTC).trade_id
    e0.close()
    with monkeypatch.context() as m:
        _patla(m)
        e = Env(tmp_path, start=T0 + H, ml1=_ml1(tmp_path, ogrenme=True))
        try:
            e.start()
            assert e.state.block_has("ml1_kapi_yok")
            e.step(T0 + H + M1, pairs=(BTC,), price=98.5, hi=99.0, lo=97.5)
            t = e.real_ledger.get_trade(tid)
            assert t.exit_reason == "stop"                                  # cikislar ASLA kapanmaz
        finally:
            e.close()


def test_saglikli_yeniden_baslatma_engeli_kaldirir(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        _patla(m)
        e = Env(tmp_path, ml1=_ml1(tmp_path, ogrenme=True))
        e.start()
        assert e.state.block_has("ml1_kapi_yok")
        e.close()
    e2 = Env(tmp_path, ml1=_ml1(tmp_path, ogrenme=True))                     # yama kalkti
    try:
        e2.start()
        assert e2.engine.ml1 is not None and e2.engine._ml1_ariza is None
        assert not e2.state.block_has("ml1_kapi_yok")
        from trader_engine.state import MANUAL_CLEAR_REASONS
        assert "ml1_kapi_yok" not in MANUAL_CLEAR_REASONS and "ml1_paket_bozuk" not in MANUAL_CLEAR_REASONS
    finally:
        e2.close()


def test_ogrenici_yokken_bozuk_paket_engeli_duzelince_kalkar(tmp_path):
    cfg = _ml1(tmp_path, ogrenme=False)
    pk = tmp_path / "models" / "ml1_package.json"
    pk.parent.mkdir(parents=True)
    pk.write_text("{bozuk", encoding="utf-8")
    e = Env(tmp_path, ml1=cfg)
    try:
        e.start()
        assert e.engine.ogren is None and e.engine.ml1 is not None
        e.signal(T0, (BTC,))
        e.decide(T0)
        assert e.state.block_has("ml1_paket_bozuk") and e.pos(BTC) is None
        pk.unlink()                                                          # silinince (= ogrenme asamasi) kalkar
        e.decide(T0 + H)
        assert not e.state.block_has("ml1_paket_bozuk")
        pk.write_text("{bozuk", encoding="utf-8")
        e.decide(T0 + 2 * H)
        assert e.state.block_has("ml1_paket_bozuk")
        from ml1_motor_destek import write_package
        write_package(pk, threshold=0.5)                                     # gecerli paket
        e.decide(T0 + 3 * H)
        assert not e.state.block_has("ml1_paket_bozuk")
    finally:
        e.close()


def test_paket_hic_yokken_engel_kurulmaz(tmp_path):
    e = Env(tmp_path, ml1=_ml1(tmp_path, ogrenme=False))
    try:
        e.start()
        e.decide(T0)
        assert not e.state.block_has("ml1_paket_bozuk") and not e.state.block_has("ml1_kapi_yok")
    finally:
        e.close()


def test_ogrenici_varken_bozuk_paket_engel_degil(tmp_path):
    pk = tmp_path / "models" / "ml1_package.json"
    pk.parent.mkdir(parents=True)
    pk.write_text("{bozuk", encoding="utf-8")
    e = Env(tmp_path, ml1=_ml1(tmp_path, ogrenme=True))
    try:
        e.start()
        assert e.engine.ogren is not None
        e.decide(T0)
        assert not e.state.block_has("ml1_paket_bozuk")                      # geri donus denetimi duzeltir; ogrenme asamasi kurali korunur
    finally:
        e.close()


def test_canli_kipte_yeni_engel_kodu_kurulmaz():
    class Durum:
        def block_add(self, *a):
            raise AssertionError("canlida engel kurulmamali")

        def block_remove(self, *a):
            raise AssertionError("canlida engel kaldirma/kurma yok")

    eng = object.__new__(EN.Engine)
    eng.cfg = SimpleNamespace(mode="live", ml1={"aktif": True})
    eng._ml1_ariza = "kapi:RuntimeError"
    eng.state = Durum()
    eng.ml1 = None
    eng.ogren = None
    eng._ml1_ariza_engeli()
    eng._ml1_paket_engeli(T0)                                                # ml1 None: hicbir sey


def test_telegram_neden_tr_iki_kod_icin_turkce():
    from trader_core import telegram as TG
    assert "yeni işlem açılmaz" in TG.neden_tr("ml1_kapi_yok") and "açık işlemler yönetiliyor" in TG.neden_tr("ml1_kapi_yok")
    assert TG.neden_tr("ml1_paket_bozuk") == "ML1 paketi bozuk (yeni işlem açılmaz)"
