"""27.11 sahip karari: STOP TABANI (tek kural, tum kurulumlar). Taban = max(0.5 x ATR, c_rt / 0.20 x giris); c_rt = 2 x (fee + kayma).
d >= taban degismez; 0.7 x taban <= d < taban => stop tabana genisletilir (hedef ayni; rr yeniden); d < 0.7 x taban => stop_width.
Kural giris kararinda, ML1 puanlamasindan ve boyutlamadan once uygulanir (EntryGate.stop_tabani_uygula)."""
from __future__ import annotations

import dataclasses
import inspect
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from trader_core import risk as K  # noqa: E402
from trader_engine import stop_tabani as ST  # noqa: E402
from trader_engine import arm_guard as AG  # noqa: E402
from trader_engine.config import ConfigError, apply_overrides, load_cli_config  # noqa: E402
from trader_engine.strategy_runner import SignalFrame  # noqa: E402
from trader_engine.strategies.arms import _kutuphane  # noqa: E402

from test_asama_b_esikleri import BOS, PAPER, LIVE, _env  # noqa: E402,F401
from test_engine_05_impl_smoke import T0, _row  # noqa: E402

UTC = timezone.utc
CFG = {"aktif": True, "maliyet_payi": 0.20, "genislet_esik": 0.7, "atr_kat": 0.5}
RC = PAPER.risk_config
C_RT_KRIPTO = 2 * (RC.fee_rate + RC.slippage_rate)          # 0.002 => taban %1,0
D_ACIK = datetime(2026, 12, 1, 16, 0, tzinfo=UTC)           # Sal 16:00 UTC: ABD seansi acik


@pytest.fixture
def mk(tmp_path):
    made = []

    def f(cfg=PAPER, **kw):
        d = tmp_path / f"e{len(made)}"
        d.mkdir()
        e = _env(d, cfg, **kw)
        made.append(e)
        return e
    yield f
    for e in made:
        e.state.close()
        e.led.close()


def _fr(row):
    return SignalFrame(pair=row.pair, status="ok", detail=None, last=row, table=None, trigger_bar=(110.0, 99.0, 5.0))


def _trx(**kw):
    """TRX benzeri dusuk oynaklik: giris 0,304; kisa yon (stop ustte); ATR kucuk; kutuphane kurulumu (ust sinir yok)."""
    d = dict(pair="TRX/USDT", setup="MF1-YUTAN", arm_id="MF1-YUTAN@1h", tf="1h", side="short", planned_entry=0.304,
             planned_stop=0.3062, planned_target=None, rr=None, atr_tf=0.0016, stop_dist_atr=0.0022 / 0.0016)
    d.update(kw)
    return _row(**d)


def _uyg(e, rows, D=T0, params=None, ml1=None):
    return e.g.stop_tabani_uygula(rows[0].pair, D, tuple(_fr(r) for r in rows), params or {"rr_min": 1.5}, ml1)


# ------------------------------------------------------------------------------------------------ saf kural
def test_kripto_taban_yuzde_bir_ve_hisse_daha_yuksek():
    c_hisse = ST.rt_maliyet(RC, PAPER.cost, PAPER.cost_overrides, "AAPL/USDT", "open")
    c_kapali = ST.rt_maliyet(RC, PAPER.cost, PAPER.cost_overrides, "AAPL/USDT", "closed")
    c_hs = ST.rt_maliyet(RC, PAPER.cost, PAPER.cost_overrides, "AAPL/USDT", "weekend")
    assert ST.rt_maliyet(RC, PAPER.cost, PAPER.cost_overrides, "BTC/USDT", None) == pytest.approx(0.002)
    assert c_hisse == pytest.approx(2 * (0.0005 + 0.0007)) and c_kapali == pytest.approx(2 * (0.0005 + 0.00105))
    assert c_hs == pytest.approx(2 * (0.0005 + 0.0014)) and 0.002 < c_hisse < c_kapali < c_hs
    f_k, p_k = ST.taban_orani(0.002, 100.0, 0.1, CFG)
    f_h, p_h = ST.taban_orani(c_hisse, 100.0, 0.1, CFG)
    assert p_k == pytest.approx(0.01) and p_h == pytest.approx(0.012) and f_h > f_k


def test_atr_terimi_baskin_olabilir():
    f, p = ST.taban_orani(0.002, 100.0, 4.0, CFG)         # 0,5 x 4 = 2,0 > %1
    assert f == pytest.approx(2.0) and p == pytest.approx(0.02)


def test_d_tabandan_buyukse_degismez(mk):
    e = mk(PAPER, **BOS)
    r = _trx(planned_stop=0.3075)                         # d = 0,0035 = %1,15 >= %1
    (c,) = _uyg(e, [r])
    assert c.last.planned_stop == 0.3075 and c.last.signal and c.last.stop_genisletildi is False
    assert c.last.stop_dogal == 0.3075


def test_trx_cok_dar_stop_atlanir_stop_width(mk):
    e = mk(PAPER, **BOS)
    r = _trx(planned_stop=0.305)                          # d = 0,001 = %0,33 < %0,7
    (c,) = _uyg(e, [r])
    assert c.last.signal is False and c.last.skip_reason == "stop_width" and c.last.planned_stop == 0.305
    out = e.g.decide(c, T0, e.g.pre(T0, "1h", True, "1h"), 1)
    assert out.action == "skip" and out.event.skip_reason == "stop_width"      # mevcut elenmis aday yolu


def test_trx_orta_dar_stop_genisler_ayni_tarafta(mk):
    e = mk(PAPER, **BOS)
    r = _trx(planned_stop=0.3065)                         # d = 0,0025 = %0,82: [%0,7, %1,0)
    (c,) = _uyg(e, [r])
    a = c.last
    assert a.signal and a.stop_genisletildi is True and a.stop_dogal == 0.3065
    assert a.planned_stop == pytest.approx(0.304 + 0.00304) and a.planned_stop > a.planned_entry     # kisa: stop ustte kalir
    assert a.planned_target is None and a.stop_dist_atr == pytest.approx(0.00304 / 0.0016)


def test_long_taraf_asagi_genisler(mk):
    e = mk(PAPER, **BOS)
    (c,) = _uyg(e, [_trx(side="long", planned_stop=0.3015)])        # d = 0,0025
    assert c.last.signal and c.last.planned_stop == pytest.approx(0.304 - 0.00304) and c.last.planned_stop < 0.304


def test_hisse_cost_overrides_daha_yuksek_taban(mk):
    e = mk(PAPER)                                                    # kume/cost_overrides acik
    assert AG.session_tag(AG.asset_class("AAPL/USDT", e.cfg.clusters), D_ACIK) == "open"
    d_stop = 100.0 + 1.1                                              # %1,1: kriptoda yeterli, hissede (taban %1,2) genisler
    r_h = _row(pair="AAPL/USDT", setup="MF1-YUTAN", arm_id="MF1-YUTAN@1h", tf="1h", side="short", planned_entry=100.0,
               planned_stop=d_stop, atr_tf=0.4, stop_dist_atr=2.75, bar_close_ts=D_ACIK)
    r_k = dataclasses.replace(r_h, pair="BTC/USDT")
    (ch,) = _uyg(e, [r_h], D_ACIK)
    (ck,) = _uyg(e, [r_k], D_ACIK)
    assert ck.last.stop_genisletildi is False and ck.last.planned_stop == pytest.approx(d_stop)
    assert ch.last.stop_genisletildi is True and ch.last.planned_stop == pytest.approx(101.2)


def test_rr_yeniden_kontrol_rr_below_min(mk):
    e = mk(PAPER, **BOS)
    # R1: giris 100, stop 99.2 (d=%0,8 -> taban %1), hedef 101.2 => dogal rr 1,5; genislemis rr 1,2 < rr_min 1,5
    r = _row(setup="R1", arm_id="R1@1h", tf="1h", side="long", planned_entry=100.0, planned_stop=99.2, planned_target=101.2,
             rr=1.5, atr_tf=0.6, stop_dist_atr=0.8 / 0.6)
    (c,) = _uyg(e, [r])
    assert c.last.signal is False and c.last.skip_reason == "rr_below_min" and c.last.planned_stop == 99.2
    assert c.last.rr == pytest.approx(1.2)
    # hedef 102 => rr 2,0; genisler, hedef fiyati AYNI
    r2 = dataclasses.replace(r, planned_target=102.0, rr=2.5)
    (c2,) = _uyg(e, [r2])
    assert c2.last.signal and c2.last.planned_target == 102.0 and c2.last.planned_stop == pytest.approx(99.0)
    assert c2.last.rr == pytest.approx(2.0)


def test_rr_min_yok_ise_bir(mk):
    e = mk(PAPER, **BOS)
    assert ST.rr_min_of("R1", {"rr_min": 1.7}) == 1.7 and ST.rr_min_of("MF1-YUTAN", {"rr_min": 1.7}) == 1.0
    r = _row(setup="B1-BOLGE", arm_id="B1-BOLGE@1h", tf="1h", side="long", planned_entry=100.0, planned_stop=99.2,
             planned_target=100.9, rr=1.125, atr_tf=0.6, stop_dist_atr=1.33)
    (c,) = _uyg(e, [r])                                               # genislemis rr = 0,9 < 1,0
    assert c.last.skip_reason == "rr_below_min"


def test_iz_suren_kurulum_yalniz_genisler(mk):
    e = mk(PAPER, **BOS)
    r = _row(setup="TF1", arm_id="TF1@1h", tf="1h", side="long", planned_entry=100.0, planned_stop=99.2, planned_target=None,
             rr=None, atr_tf=0.6, stop_dist_atr=0.8 / 0.6)
    (c,) = _uyg(e, [r])
    assert c.last.signal and c.last.planned_stop == pytest.approx(99.0) and c.last.planned_target is None


def test_kurulum_ust_siniri_korunur(mk):
    e = mk(PAPER, **BOS)
    # cekirdek T1: ust sinir 2,0 ATR; taban 1,0 / ATR 0,4 = 2,5 ATR => genisletme siniri asar => stop_width
    r = _row(setup="T1", side="long", planned_entry=100.0, planned_stop=99.2, atr_tf=0.4, stop_dist_atr=2.0)
    (c,) = _uyg(e, [r])
    assert c.last.signal is False and c.last.skip_reason == "stop_width"
    assert ST.max_atr_of("T1") == 2.0 and ST.max_atr_of("TF1") == 3.0 and ST.max_atr_of("MF1-YUTAN") is None


def test_kapali_bayrak_eski_davranis(mk):
    e = mk(dataclasses.replace(PAPER, stop_tabani={"aktif": False}), **BOS)
    rows = [_trx(planned_stop=0.305)]
    cands = tuple(_fr(r) for r in rows)
    assert e.g.stop_tabani_uygula("TRX/USDT", T0, cands, {}, None) is cands
    e2 = mk(dataclasses.replace(PAPER, stop_tabani={}), **BOS)
    assert e2.g.stop_tabani_uygula("TRX/USDT", T0, cands, {}, None) is cands
    out = e.g.decide(cands[0], T0, e.g.pre(T0, "1h", True, "1h"), 1)
    assert out.action == "enter"                                       # dogal stop (%0,33) eskisi gibi girer


def test_elenen_aday_kalan_sinyali_engellemez(mk):
    e = mk(PAPER, **BOS)
    dar = _trx(planned_stop=0.305, arm_id="MF1-YUTAN@1d", tf="1d")
    iyi = _trx(planned_stop=0.3075, arm_id="MF1-PINBAR@1h", setup="MF1-PINBAR")
    out = _uyg(e, [dar, iyi])
    assert [c.last.signal for c in out] == [True, False] and out[0].last.arm_id == "MF1-PINBAR@1h"


def test_ml1_tamponu_son_stopla_guncellenir(mk):
    e = mk(PAPER, **BOS)
    cagri = []
    ml1 = SimpleNamespace(stop_guncelle=lambda *a: cagri.append(a))
    gen, dar = _trx(planned_stop=0.3065), _trx(planned_stop=0.305, arm_id="MF1-ICCUBUK@1h", setup="MF1-ICCUBUK")
    _uyg(e, [gen, dar], ml1=ml1)
    assert cagri[0][2:5] == ("MF1-YUTAN@1h", "short", pytest.approx(0.30704)) and cagri[0][5] == pytest.approx(0.00304 / 0.0016)
    assert len(cagri) == 1                                              # elenen aday tamponda kalir (konfluans baglami), guncellenmez


def test_ml1_gate_stop_guncelle_tamponu_degistirir():
    import pandas as pd
    from trader_engine.ml1_gate import Ml1Gate
    g = Ml1Gate({"aktif": True})
    k = ("MF1-YUTAN@1h", pd.Timestamp(T0), "short")
    g._buf["TRX/USDT"] = {k: {"stop": 0.3065, "stop_dist_atr": 1.5}}
    g.stop_guncelle("TRX/USDT", T0, "MF1-YUTAN@1h", "short", 0.30704, 1.9)
    assert g._buf["TRX/USDT"][k] == {"stop": 0.30704, "stop_dist_atr": 1.9}
    g.stop_guncelle("TRX/USDT", T0, "yok@1h", "short", 1.0, 1.0)      # firlatmaz


# ------------------------------------------------------------------------------------------------ boyut ve kayit
def test_boyut_kuculur_risk_ayni_ve_notional_tavani_baglamaz(mk):
    eq = 10000.0
    kapali = mk(dataclasses.replace(PAPER, stop_tabani={"aktif": False}), equity=eq, **BOS)
    acik = mk(PAPER, equity=eq, **BOS)
    r = _trx(planned_stop=0.3062)                                       # d = 0,0022 (%0,72): genisler
    o_eski = kapali.g.decide(_fr(r), T0, kapali.g.pre(T0, "1h", True, "1h"), 1)
    (c,) = _uyg(acik, [r])
    o_yeni = acik.g.decide(c, T0, acik.g.pre(T0, "1h", True, "1h"), 1)
    assert o_eski.action == "enter" and o_yeni.action == "enter"
    assert o_eski.size.notional == pytest.approx(RC.max_notional_ratio * eq, rel=1e-3)      # eski: notional tavani BAGLI
    assert o_yeni.size.notional < 0.9 * RC.max_notional_ratio * eq                          # yeni: tavan baglamaz
    assert o_yeni.size.qty < o_eski.size.qty
    hedef = PAPER.target_trade_risk * eq
    assert o_yeni.size.risk_amount == pytest.approx(hedef, rel=1e-3)                        # risk tutari hedefte
    assert o_eski.size.risk_amount < 0.95 * hedef                                           # eski: tavan yuzunden riskin altinda
    ev = o_yeni.event
    assert ev.planned_stop == pytest.approx(0.30704) and ev.features["stop_genisletildi"] is True
    assert ev.features["stop_dogal"] == pytest.approx(0.3062) and ev.features["stop_dist_atr"] == pytest.approx(0.00304 / 0.0016)
    acik.led.record_decision(ev)                                                              # defter bool/yeni anahtarlari kabul eder


def test_kutuphane_yuzde_06_kontrolu_kalkti_yeni_kural_yonetir(mk):
    assert "MIN_STOP_ORAN" not in inspect.getsource(_kutuphane.hesapla)
    e = mk(PAPER, **BOS)
    # eskiden %0,6'yi gecen kutuphane adayi: %0,6 < %0,7 => artik stop_width; %0,8 => genisler
    (a,) = _uyg(e, [_trx(planned_stop=0.304 + 0.304 * 0.006)])
    assert a.last.skip_reason == "stop_width"
    (b,) = _uyg(e, [_trx(planned_stop=0.304 + 0.304 * 0.008)])
    assert b.last.signal and b.last.stop_genisletildi


# ------------------------------------------------------------------------------------------------ yapilandirma
@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_yapilandirma_blogu_kagit_ve_canlida_ayni(cfg):
    assert cfg.stop_tabani == CFG
    raw = {n: json.loads((ROOT / "config" / n).read_text(encoding="utf-8"))["stop_tabani"] for n in ("engine.paper.json", "engine.live.json")}
    assert raw["engine.paper.json"] == raw["engine.live.json"]


@pytest.mark.parametrize("bad", [{"maliyet_payi": 0.2}, {"aktif": 1}, {"aktif": True, "maliyet_payi": 0},
                                 {"aktif": True, "genislet_esik": 1.5}, {"aktif": True, "atr_kat": -1}, {"aktif": True, "x": 1},
                                 {"aktif": True, "maliyet_payi": True}, "evet"])
def test_yapilandirma_gecersiz(bad):
    with pytest.raises(ConfigError):
        apply_overrides(PAPER, stop_tabani=bad)


def test_yapilandirma_varsayilan_ve_bos():
    assert apply_overrides(PAPER, stop_tabani={"aktif": True}).stop_tabani == CFG
    assert apply_overrides(PAPER, stop_tabani={}).stop_tabani == {}
