"""23.11: toplu sok raporu (bilgi) + tasfiye mesafesi kapisi (giris; kagit = canli ayni kod)."""
from __future__ import annotations

import dataclasses
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import risk as K
from trader_engine import status as TS
from trader_engine.config import load_cli_config
from trader_engine.status import StatusWriter

import test_etiket_kurallari_gate as G

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)

# Ornek set: kasa 1000; BTC long 0,01 x 100.000 (notional 1000), NVDA short 5 x 200 (notional 1000), XAU long 1 x 300 (300)
POS = [
    {"pair": "BTC/USDT", "side": "long", "qty": 0.01, "entry_price": 100000.0, "mark": 100000.0, "stop": 98000.0, "asset_class": "kripto"},
    {"pair": "NVDA/USDT", "side": "short", "qty": 5.0, "entry_price": 200.0, "mark": 200.0, "stop": 204.0, "asset_class": "hisse"},
    {"pair": "XAU/USDT", "side": "long", "qty": 1.0, "entry_price": 300.0, "mark": 300.0, "stop": 297.0, "asset_class": "emtia"},
]


# ------------------------------------------------------------------ A: toplu sok
def test_ortak_sok_elle_hesap():
    d = TS.hesapla(POS, 1000.0, gunluk_limit=0.08)
    assert d["notional"] == 2300.0 and d["pozisyon_sayisi"] == 3
    assert d["ortak"]["10"] == {"usd": 230.0, "kasa_yuzde": 23.0}            # 0,10 x 2300
    assert d["ortak"]["2"]["usd"] == 46.0 and d["ortak"]["5"]["usd"] == 115.0 and d["ortak"]["20"]["usd"] == 460.0


def test_iliskili_sok_kripto_x_diger_yarisi():
    d = TS.hesapla(POS, 1000.0)
    assert d["iliskili"]["10"]["usd"] == 100.0 + 0.05 * 1300                  # kripto %10 x 1000 + (hisse+emtia) %5 x 1300 = 165
    assert d["iliskili"]["10"]["usd"] == 165.0 and d["iliskili"]["10"]["kasa_yuzde"] == 16.5


def test_stop_dolumu_taban_ve_stres():
    d = TS.hesapla(POS, 1000.0, taker_fee=0.0005, kayma_bps={"*": 5.0})
    # BTC long: dolum = 98000 x (1 - 5e-4) = 97951; (100000-97951) x 0,01 + 0,0005 x 0,01 x 97951
    btc = (100000 - 98000 * (1 - 5e-4)) * 0.01 + 0.0005 * 0.01 * 98000 * (1 - 5e-4)
    nv = -1 * (200 - 204 * (1 + 5e-4)) * 5 + 0.0005 * 5 * 204 * (1 + 5e-4)   # short: dolum stop'un ustunde
    xa = (300 - 297 * (1 - 5e-4)) * 1 + 0.0005 * 297 * (1 - 5e-4)
    assert d["stop_dolumu"]["taban"]["usd"] == pytest.approx(round(btc + nv + xa, 2), abs=0.011)
    t2 = TS.hesapla(POS, 1000.0, kayma_bps={"*": 10.0}, taker_fee=0.0005)["stop_dolumu"]["taban"]["usd"]
    assert d["stop_dolumu"]["stres_2x"]["usd"] == t2                        # stres = 2 x kayma
    assert d["stop_dolumu"]["stres_2x"]["usd"] > d["stop_dolumu"]["taban"]["usd"]


def test_stopsuz_sayilir_ve_gecersiz_atlanir():
    pos = POS + [{"pair": "X/USDT", "side": "long", "qty": 1, "entry_price": 10, "stop": None, "asset_class": "kripto"},
                 {"pair": "Y/USDT", "side": "long", "qty": 0, "entry_price": 10, "stop": 9}]
    d = TS.hesapla(pos, 1000.0)
    assert d["stop_dolumu"]["stopsuz"] == 1 and d["atlanan"] == 1


def test_equity_yok_ve_pozisyonsuz():
    assert TS.hesapla(POS, None)["ortak"] is None
    d = TS.hesapla([], 1000.0, gunluk_limit=0.08)
    assert d["ortak"]["10"]["usd"] == 0.0 and d["uyari"] is False


def test_izole_teminat_tavani():
    p = [{**POS[0], "leverage": 3.0}]
    assert TS.hesapla(p, 1000.0)["ortak"]["20"]["usd"] == 200.0             # 0,20 x 1000 < teminat 333
    big = [{**POS[0], "qty": 0.01, "leverage": 3.0}]
    assert _zarar_tavan(big) <= 1000.0 / 3 + 1e-9


def _zarar_tavan(p):
    return TS._zarar_sok(TS._norm(p), 90.0, 90.0)                          # %90 sok: tavan = notional/kaldirac


def test_uyari_gunluk_limite_karsi():
    d = TS.hesapla(POS, 1000.0, gunluk_limit=0.08)                          # %10 sok = %23 > %8
    assert d["uyari"] is True and d["gunluk_limit"]["usd"] == 80.0
    kucuk = [{**POS[0], "qty": 0.0005}]                                      # notional 50: %10 = 5$ = %0,5
    assert TS.hesapla(kucuk, 1000.0, gunluk_limit=0.08)["uyari"] is False
    assert TS.hesapla(POS, 1000.0)["uyari"] is None


def test_kayma_haritasi_en_buyuk_seans():
    ov = {"NVDA/USDT": {"open": {"slip_stop_bps": 10.0}, "weekend": {"slip_stop_bps": 20.0}}}
    m = TS.kayma_haritasi(["NVDA/USDT", "BTC/USDT"], 5.0, ov)
    assert m["NVDA/USDT"] == 20.0 and m["*"] == 5.0 and "BTC/USDT" not in m


def test_status_blogu_ve_json_dosyasi(tmp_path):
    cfg = load_cli_config(ROOT / "config", "learner", "paper")
    sp = tmp_path / "var" / "learner" / "status.json"
    sw = StatusWriter(str(sp), SimpleNamespace(now=lambda: NOW), cfg)
    pos = [{"trade_id": 1, **POS[0]}]
    blok = sw._toplu_sok(None, pos, 1000.0)
    assert blok["uyari"] is True and blok["ortak"]["10"]["usd"] == 100.0
    js = json.loads((tmp_path / "var" / "durum" / "toplu_sok_paper_v1.json").read_text())
    assert js["sema"] == TS.SEMA and js["mod"] == "paper" and js["gunluk_limit"]["oran"] == cfg.risk_config.daily_max_loss
    assert TS.oku(TS.durum_yolu(sp, "paper"))["ortak"]["10"]["usd"] == 100.0


# ------------------------------------------------------------------ B: tasfiye mesafesi
def test_liq_formulu_elle_hesap():
    # long, giris 100, kaldirac 3, mmr 0,005: 100 x (1 - 1/3 + 0,005) = 67,1666...; short: 100 x (1 + 1/3 - 0,005) = 132,8333...
    assert K.liquidation_price(100, "long", 3, 0.005) == pytest.approx(67.16666667)
    assert K.liquidation_price(100, "short", 3, 0.005) == pytest.approx(132.83333333)
    t = K.tasfiye_mesafesi(100, 98, "long", 3, 0.005)
    assert t["liq_mesafe"] == pytest.approx(32.83333333) and t["stop_mesafe"] == 2 and t["guvenli"] is True
    assert t["oran"] == pytest.approx(16.4166667)


def test_sinif_mmr_sabitleri():
    assert K.sinif_mmr("kripto") == 0.005 and K.sinif_mmr("hisse") == 0.02 and K.sinif_mmr("emtia") == 0.02
    assert K.sinif_mmr(None) == 0.02 and K.sinif_mmr("kripto", 0.01) == 0.01      # cfg buyukse onun altina inmez


def test_sinir_ve_max_kaldirac():
    # mesafe tam 1,5 x stop: guvenli (>=); biraz otesi degil. kaldirac 3, mmr 0: liq mesafe 33,33; stop 22,2222 -> sinir
    assert K.tasfiye_mesafesi(100, 100 - 33.3333333333 / 1.5, "long", 3, 0.0)["guvenli"] is True
    t = K.tasfiye_mesafesi(100, 70, "long", 3, 0.005)                          # stop mesafesi 30 => 45 gerek; kaldirac 3'te 32,8 yetmez
    assert t["guvenli"] is False and t["max_kaldirac"] == 2                      # kaldirac 2: mesafe 49,5 >= 45


def _gate(tmp_path, mode):
    e = G._kur(tmp_path)
    e.g.cfg = dataclasses.replace(G.CFG, mode=mode)
    e.g._etiket_karari = lambda *a, **k: None
    return e


def test_guvenli_mesafede_etki_yok_ve_kagit_canli_ayni(tmp_path):
    sonuc = {}
    for i, mode in enumerate(("paper", "live")):
        d = tmp_path / mode
        d.mkdir()
        e = _gate(d, mode)
        try:
            o = G._go(e)                                                          # varsayilan stop 98: guvenli
            sonuc[mode] = (o.action, o.code, o.size, o.leverage, e.g.counters["tasfiye_mesafesi"])
        finally:
            e.state.close(); e.led.close()
    assert sonuc["paper"] == sonuc["live"] and sonuc["paper"][0] == "enter" and sonuc["paper"][4] == 0


def test_tehlikeli_mesafede_atlar_paper_ve_live_ayni(tmp_path, monkeypatch):
    # cekirdek 0,4% ile gecer (stop mesafesi 21 <= 21,95), sinif MMR'si 3% yapilinca (<= 20,2) tasfiye kapisi atlar
    monkeypatch.setitem(K.MMR_SINIF, "kripto", 0.03)
    sonuc = {}
    for mode in ("paper", "live"):
        d = tmp_path / mode
        d.mkdir()
        e = _gate(d, mode)
        try:
            o = G._go(e, planned_stop=79.0)
            sonuc[mode] = (o.action, o.code, o.event.veto_reason, o.event.skip_reason, e.g.counters["tasfiye_mesafesi"], o.size)
        finally:
            e.state.close(); e.led.close()
    assert sonuc["paper"] == sonuc["live"]
    assert sonuc["paper"][:5] == ("skip", "tasfiye_mesafesi", "gate:tasfiye_mesafesi", "risk_denied", 1) and sonuc["paper"][5] is None


def test_guvenli_giriste_boyut_ve_kaldirac_degismez(tmp_path):
    e = _gate(tmp_path, "paper")
    try:
        o = G._go(e)
        assert o.action == "enter" and o.leverage == K.LOCKED_CFG.min_leverage and o.size.qty > 0
        assert e.g.counters["tasfiye_mesafesi_hata"] == 0
    finally:
        e.state.close(); e.led.close()
