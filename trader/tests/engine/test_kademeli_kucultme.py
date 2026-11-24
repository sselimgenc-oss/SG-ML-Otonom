"""Kademeli boyut kucultme (20 Kasim 2026, yalniz kagit): docs/motor/kademeli-kucultme-spec.md."""
from __future__ import annotations

import dataclasses
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from trader_core import kol_kucultme as KK  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_core import panel_pano as PP  # noqa: E402

from test_dd12_wp04_impl import env, _go  # noqa: E402,F401  (paper kapi fixture'i)

UTC = timezone.utc
AID = "R1@1h"


# ---- saf kural ---------------------------------------------------------------------------------------------------
def test_esikler():
    assert KK.karar([]).carpan == 1.0
    assert KK.karar([-1.0] * 4).carpan == 1.0                       # 4 islem: degismez
    assert KK.karar([-1.0] * 5).carpan == 0.5                       # 5 zararli
    assert KK.karar([-1.0] * 9).carpan == 0.5                       # 10'a kadar yari
    assert KK.karar([-1.0] * 10).carpan == 0.3                      # 10 zararli: asgari
    assert KK.karar([-1.0] * 50).carpan == 0.3                      # asgari boyutun altina inmez, kol kapanmaz
    assert KK.karar([0.0] * 10).carpan == 1.0                       # tam sifir: negatif degil


def test_geri_yukselis_basamakli():
    # son 10 negatif -> 0.3; son 5 pozitif olsa da son 10 hala negatifse 0.3 kalir
    assert KK.karar([+1, +1, +1, +1, +1, -2, -2, -2, -2, -2]).carpan == 0.3
    # son 10 toplam >= 0 ama son 5 < 0 -> 0.5
    k = KK.karar([-1, -1, -1, -1, -1, +2, +2, +2, +2, +2])
    assert k.carpan == 0.5 and k.net_5 == -5 and k.net_10 == 5
    # ikisi de >= 0 -> 1.0
    assert KK.karar([+1, 0, -1, +1, +1, -1, +1, -1, +1, -1]).carpan == 1.0
    # tam yol: zarar serisi sonra kazanc serisi (yeniden eskiye listesi, her adimda yeni islem basa eklenir)
    seri = [-1.0] * 10
    gor = [KK.karar(seri).carpan]
    for _ in range(10):
        seri = [+1.0] + seri
        gor.append(KK.karar(seri).carpan)
    assert gor[0] == 0.3 and gor[-1] == 1.0 and set(gor) <= {0.3, 0.5, 1.0}
    assert gor == sorted(gor)                                        # tek yonlu yukselis: 0.3 -> 0.5 -> 1.0


def test_carpan_yalniz_kucultur_ve_ozellikler():
    for n in range(0, 15):
        for v in (-1.0, 0.0, 1.0):
            assert 0.3 <= KK.karar([v] * n).carpan <= 1.0
    o = KK.ozellikler(KK.karar([-0.5] * 10))
    assert o == {"kol_boyut_carpani": 0.3, "kol_n": 10, "kol_net_r_5": -2.5, "kol_net_r_10": -5.0}
    assert set(KK.ozellikler(KK.karar([-1.0] * 3))) == {"kol_boyut_carpani", "kol_n"}      # pencere dolmadan net_r yok


def test_rapor_satiri():
    assert KK.satir({}) == ""
    az = KK.azaltilanlar({"R1@1h": [-1.0] * 5, "T1@4h": [1.0] * 12, "M1@1h": [-1.0] * 10})
    assert set(az) == {"R1@1h", "M1@1h"}
    s = KK.satir(az)
    assert "M1@1h %30" in s and "R1@1h %50" in s and "T1@4h" not in s and "_" not in s


# ---- defter sorgusu ----------------------------------------------------------------------------------------------
def _defter(tmp_path, kazanc_dizisi):
    """kazanc_dizisi eskiden yeniye: True = kazanc. Hepsi R1@1h (setup R1, tf 1h)."""
    from panel_support import mkledger
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    mkledger(str(tmp_path / "l.sqlite"), "learner", [(w, True, t0 + timedelta(hours=2 * i)) for i, w in enumerate(kazanc_dizisi)])
    return L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=False, read_only=True, migrate=False)


def test_defter_son_sonuclar_yeniden_eskiye(tmp_path):
    led = _defter(tmp_path, [True] * 3 + [False] * 6)
    try:
        r = led.arm_recent_results(AID, 5)
        assert len(r) == 5 and all(x < 0 for x in r)                 # en yeni 5 zararli
        assert KK.karar(led.arm_recent_results(AID, 10)).carpan == 0.5    # 9 islem: son 5 negatif
        assert led.arm_recent_results("T1@1h", 10) == []
        assert KK.azaltilanlar(led.arm_results_all(10)).keys() == {AID}
    finally:
        led.close()


# ---- motor kapisi: boyut gercekten yarilanir ---------------------------------------------------------------------
def _boyut(env, sonuc):
    env.led.arm_recent_results = lambda aid, n: list(sonuc)            # type: ignore[method-assign]
    out = _go(env)
    assert out.action == "enter"
    return out


def test_kapi_boyut_yarilanir_ve_kayit(env):
    temel = _boyut(env, [])
    assert temel.event.features["kol_boyut_carpani"] == 1.0 and "kol_net_r_5" not in temel.event.features
    d4 = _boyut(env, [-1.0] * 4)
    assert d4.size.qty == temel.size.qty
    yari = _boyut(env, [-1.0] * 5)
    assert yari.size.risk_amount == pytest.approx(temel.size.risk_amount * 0.5, rel=0.02)
    assert yari.size.qty == pytest.approx(temel.size.qty * 0.5, rel=0.02)
    assert yari.event.features["kol_boyut_carpani"] == 0.5 and yari.event.features["kol_net_r_5"] == -5.0
    assert yari.event.size_risk_amount == yari.size.risk_amount
    asgari = _boyut(env, [-1.0] * 10)
    assert asgari.size.risk_amount == pytest.approx(temel.size.risk_amount * 0.3, rel=0.02)
    assert asgari.event.features["kol_boyut_carpani"] == 0.3 and asgari.event.features["kol_net_r_10"] == -10.0
    assert asgari.leverage == temel.leverage                           # kaldirac degismez
    assert env.g.counters[f"kol_kucultme:{AID}"] >= 2 or any(k.startswith("kol_kucultme:") for k in env.g.counters)
    # geri yukselis: pencere donunce tam boyut
    assert _boyut(env, [+4.0] + [-1.0] * 4).size.qty == temel.size.qty


def test_kapi_okuma_hatasi_tam_boyut(env):
    temel = _boyut(env, [])

    def bozuk(aid, n):
        raise RuntimeError("x")
    env.led.arm_recent_results = bozuk                                 # type: ignore[method-assign]
    out = _go(env)
    assert out.action == "enter" and out.size.qty == temel.size.qty


def test_yalniz_kagit(env):
    """testnet/canli: kademeli kucultme ve kayit yok (kapi cfg.mode != paper)."""
    cfg = dataclasses.replace(env.g.cfg, mode="testnet")
    env.g.cfg = cfg
    temel = _go(env)
    env.led.arm_recent_results = lambda aid, n: [-1.0] * 10            # type: ignore[method-assign]
    out = _go(env)
    assert out.action == temel.action
    if out.action == "enter":
        assert out.size.qty == temel.size.qty and "kol_boyut_carpani" not in out.event.features


def test_asgari_boyut_emir_altina_dusunce_kol_kapanmaz(env):
    """0.3 boyut min_notional altinda kalirsa tam boyut denenir (kol asla kapanmaz); kayit geri dondugunu soyler."""
    temel = _boyut(env, [])
    notional = temel.size.notional
    rules0 = env.g.rules_fn
    env.g.rules_fn = lambda p: dataclasses.replace(rules0(p), min_notional=notional * 0.8)
    out = _boyut(env, [-1.0] * 10)
    assert out.size.qty == temel.size.qty
    assert out.event.features["kol_boyut_carpani"] == 1.0 and out.event.features["kol_boyut_geri"] == 1


# ---- panel / rapor -----------------------------------------------------------------------------------------------
def test_panel_karti(tmp_path):
    _defter(tmp_path, [False] * 5).close()
    v = PP.kucultme_view(str(tmp_path / "l.sqlite"), "learner")
    assert v == {"kollar": [{"kol": AID, "carpan": 0.5, "n": 5, "net_5": v["kollar"][0]["net_5"], "net_10": None,
                                      "aile": None, "aile_nedeni": False}]}      # 24.11 kullanici karari: aile destegi (ailesiz kol) and v["kollar"][0]["net_5"] < 0


def test_check_entry_scaled_sinirlari():
    from trader_core import risk as K
    with pytest.raises(ValueError):
        K.check_entry_scaled(None, None, K.LOCKED_CFG, 1.5)           # buyutme yok
    with pytest.raises(ValueError):
        K.check_entry_scaled(None, None, K.LOCKED_CFG, 0)
