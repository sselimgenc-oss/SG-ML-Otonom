"""23.11 fikir 7 (uzun donem yon filtresi) ve fikir 8 (kol karnesi buzulmesi); kagit = canli."""
from __future__ import annotations

import dataclasses
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from trader_core import kol_kucultme as KK  # noqa: E402
from trader_engine import uzun_yon as UY  # noqa: E402
from trader_engine.config import ConfigError, apply_overrides, load_cli_config  # noqa: E402

from test_asama_b_esikleri import BOS, PAPER, LIVE, _go, mk  # noqa: E402,F401
from test_engine_05_impl_smoke import T0  # noqa: E402
from test_dd12_wp04_impl import env as kol_env, _go as _kol_go  # noqa: E402,F401

UTC = timezone.utc
CFG = {"ema": 50, "egim_gun": 10, "min_gun": 60}


def _gun_barlari(kapanislar, son_gun_bitis):
    """Gunluk kapanislardan 4h barlar (her gun 6 bar; gunun son bari gunluk kapanisi tasir). son_gun_bitis: son tam gunun ertesi 00:00."""
    idx, c = [], []
    n = len(kapanislar)
    for i, k in enumerate(kapanislar):
        gun = son_gun_bitis - timedelta(days=n - i)
        for h in range(0, 24, 4):
            idx.append(gun + timedelta(hours=h))
            c.append(k if h == 20 else k)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0}, index=pd.DatetimeIndex(idx, tz="UTC"))


BUGUN = T0.replace(hour=0)                                  # 2026-12-01 00:00; son tam gun = 30 Kasim
YUKARI = list(np.linspace(100, 160, 90))
ASAGI = list(np.linspace(160, 100, 90))
YATAY = YUKARI[:89] + [100.0]                         # kapanis EMA altinda ama EMA egimi yukari: karisik => yatay


def _e(mk, cfg, rejim_serisi, **kw):
    e = mk(cfg, **{**BOS, "uzun_yon": CFG, **kw})
    df = _gun_barlari(rejim_serisi, BUGUN)
    e.g.uzun_yon = UY.UzunYon(CFG, lambda p, tf, until, n: df[df.index + timedelta(hours=4) <= until])
    return e


# ---- saf siniflandirma -------------------------------------------------------------------------------------------
def test_siniflandirma():
    assert UY.sinifla(YUKARI, 50, 10, 60) == "boga"
    assert UY.sinifla(ASAGI, 50, 10, 60) == "ayi"
    assert UY.sinifla(YATAY, 50, 10, 60) == "yatay"
    assert UY.sinifla(YUKARI[:59], 50, 10, 60) == "veri_yok"
    assert UY.reddeder("boga", "short") and not UY.reddeder("boga", "long")
    assert UY.reddeder("ayi", "long") and not UY.reddeder("ayi", "short")
    assert not UY.reddeder("yatay", "short") and not UY.reddeder("yatay", "long") and not UY.reddeder("veri_yok", "short")


@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_boga_short_red_long_serbest(mk, cfg):
    e = _e(mk, cfg, YUKARI)
    o = _go(e, "BTC/USDT", "short")
    assert o.action == "skip" and o.event.skip_reason == "risk_denied" and o.event.veto_reason == "gate:uzun_yon"
    assert o.event.features["uzun_yon"] == "boga" and e.g.counters["uzun_yon_blok"] == 1
    l = _go(e, "ETH/USDT", "long")
    assert l.action == "enter" and l.event.features["uzun_yon"] == "boga"


@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_ayi_long_red_short_serbest(mk, cfg):
    e = _e(mk, cfg, ASAGI)
    o = _go(e, "BTC/USDT", "long")
    assert o.action == "skip" and o.event.veto_reason == "gate:uzun_yon" and o.event.features["uzun_yon"] == "ayi"
    assert _go(e, "ETH/USDT", "short").action == "enter"


def test_yatay_iki_yon_serbest(mk):
    e = _e(mk, PAPER, YATAY)
    assert _go(e, "BTC/USDT", "short").action == "enter"
    assert _go(e, "ETH/USDT", "long").event.features["uzun_yon"] == "yatay"
    assert e.g.counters["uzun_yon_blok"] == 0


def test_veri_yok_serbest_ve_sayac(mk):
    e = _e(mk, PAPER, YUKARI[-40:])
    o = _go(e, "BTC/USDT", "short")
    assert o.action == "enter" and o.event.features["uzun_yon"] == "veri_yok"
    assert e.g.counters["uzun_yon_veri_yok"] == 1 and e.g.counters["uzun_yon_blok"] == 0


def test_bugunku_acik_mum_kullanilmaz(mk):
    """Son tam gun yatay/boga degil; yalniz bugunun (kapanmamis) 4h mumlari ayi yonunde cok farkli: rejim DEGISMEMELI."""
    df = _gun_barlari(YUKARI, BUGUN)
    bugun = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                         index=pd.DatetimeIndex([BUGUN + timedelta(hours=h) for h in (0, 4)], tz="UTC"))   # 09:00'da 00:00 ve 04:00 mumlari kapali
    df2 = pd.concat([df, bugun])
    tam = UY.gunluk_kapanislar(df2, T0)
    assert tam == UY.gunluk_kapanislar(df, T0) and len(tam) == 90                       # eksik (2 mumlu) gun atilir
    assert UY.sinifla(tam, 50, 10, 60) == "boga"
    # henuz kapanmamis 4h mumu (08:00-12:00) kapanis sayilmaz
    ac = pd.concat([df, pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([T0 - timedelta(hours=1)], tz="UTC"))])
    assert UY.gunluk_kapanislar(ac, T0) == UY.gunluk_kapanislar(df, T0)
    # kapanis, ertesi gun 00:00'da (D+1) gunun tamamlanmasiyla girer
    assert len(UY.gunluk_kapanislar(df, BUGUN - timedelta(hours=4))) == 89


def test_onbellek_gunde_bir_hesap():
    n = {"c": 0}
    df = _gun_barlari(YUKARI, BUGUN)

    def bars(p, tf, until, k):
        n["c"] += 1
        return df
    u = UY.UzunYon(CFG, bars)
    assert u.rejim("BTC/USDT", T0) == "boga" and u.rejim("BTC/USDT", T0 + timedelta(hours=5)) == "boga"
    assert n["c"] == 1
    u.rejim("BTC/USDT", T0 + timedelta(days=1))
    assert n["c"] == 2


def test_config_yoksa_kapali_ve_veri_kaynagi_hatasi_serbest(mk):
    e = mk(PAPER, **{**BOS, "uzun_yon": {}})                                  # uzun_yon bos
    assert e.g.uzun_yon is None
    assert _go(e, "BTC/USDT", "short").action == "enter" and "uzun_yon" not in e.g.counters
    e2 = mk(PAPER, **{**BOS, "uzun_yon": CFG})
    assert e2.g.uzun_yon is not None and e2.g.uzun_yon.bars_fn is None       # bagsiz: veri_yok => serbest
    assert _go(e2, "BTC/USDT", "short").event.features["uzun_yon"] == "veri_yok"

    def patla(*a):
        raise RuntimeError("db")
    e3 = mk(PAPER, **{**BOS, "uzun_yon": CFG})
    e3.g.uzun_yon.bars_fn = patla
    assert _go(e3, "BTC/USDT", "short").action == "enter" and e3.g.counters["uzun_yon_hata"] == 1


# ---- config / parite ---------------------------------------------------------------------------------------------
def test_config_paper_live_ayni_ve_dogrulama():
    assert PAPER.uzun_yon == LIVE.uzun_yon
    with pytest.raises(ConfigError):
        apply_overrides(PAPER, uzun_yon={"ema": 50})
    with pytest.raises(ConfigError):
        apply_overrides(PAPER, uzun_yon={"ema": 0, "egim_gun": 10, "min_gun": 60})
    with pytest.raises(ConfigError):
        apply_overrides(PAPER, mode="backtest", uzun_yon=CFG)
    assert apply_overrides(PAPER, uzun_yon={}).uzun_yon == {}


# ---- fikir 8: buzulme --------------------------------------------------------------------------------------------
def test_buzulme_formulu():
    assert KK.K_BUZULME == 10
    assert KK.buzulme(5, -1.0, 0.5) == pytest.approx((5 * -1.0 + 10 * 0.5) / 15)
    assert KK.buzulme(0, None, 0.4) == 0.4 and KK.buzulme(0, 3.0, 0.4) == 0.4        # n = 0: aile degeri
    assert KK.buzulme(10_000, -1.0, 5.0) == pytest.approx(-1.0, abs=0.01)             # n buyuk: kola yakin


def test_aile_ortalamasi_tum_tf():
    o = KK.aile_ortalamasi({"R1@15m": [1.0, 1.0], "R1@1h": [-1.0, -1.0, -1.0, -1.0], "T1@1h": [2.0]})
    assert o["R1"] == pytest.approx(-1 / 3) and o["T1"] == 2.0


def test_karar_buzulmus_esikler():
    zarar5 = [-0.1] * 5                                     # ham: toplam -0.5 < 0 => 0.5
    assert KK.karar(zarar5).carpan == 0.5
    k = KK.karar(zarar5, aile_ort=0.5)                      # saglikli aile: (5*-0.1+10*0.5)/15 = 0.3 > 0 => kucultme yok
    assert k.carpan == 1.0 and k.buz_5 == pytest.approx(0.3) and k.aile == 0.5
    assert KK.karar([0.1] * 5, aile_ort=-0.5).carpan == 0.5   # ham 1.0; kotu aile: (0.5-5)/15 < 0 => 0.5
    assert KK.karar([-1.0] * 10, aile_ort=0.2).carpan == 0.3  # cok kotu kol: aile kurtarmaz ((-10+2)/20 < 0)
    assert KK.karar([-1.0] * 10, aile_ort=None).carpan == 0.3
    assert KK.karar([-0.1] * 4, aile_ort=-5.0).carpan == 1.0  # 5'ten az islem: asla kucultme
    o = KK.ozellikler(k)
    assert o["kol_aile_r"] == 0.5 and o["kol_buz_r_5"] == pytest.approx(0.3)


def test_azaltilanlar_buzulmeli():
    veri = {"R1@1h": [-0.1] * 5, "R1@4h": [2.0] * 30}      # R1 ailesi cok kazancli
    assert set(KK.azaltilanlar(veri)) == set()              # buzulme: kol kucultulmez
    assert set(KK.azaltilanlar(veri, buzulmeli=False)) == {"R1@1h"}


def test_kapi_buzulme_kullanir(kol_env):
    """Karar yolu: ham kural 0.5 verirdi; saglikli aile ortalamasiyla tam boyut."""
    kol_env.led.arm_recent_results = lambda aid, n: [-0.1] * 5          # type: ignore[method-assign]
    kol_env.led.arm_family_mean_r = lambda aid: None                    # type: ignore[method-assign]
    ham = _kol_go(kol_env)
    assert ham.event.features["kol_boyut_carpani"] == 0.5
    kol_env.led.arm_family_mean_r = lambda aid: 0.5                     # type: ignore[method-assign]
    b = _kol_go(kol_env)
    assert b.event.features["kol_boyut_carpani"] == 1.0 and b.event.features["kol_aile_r"] == 0.5
    assert b.size.qty > ham.size.qty


def test_defter_aile_ortalamasi(tmp_path):
    from datetime import datetime as D
    from panel_support import mkledger
    from trader_core import ledger as L
    mkledger(str(tmp_path / "l.sqlite"), "learner", [(True, True, D(2026, 11, 1, tzinfo=UTC) + timedelta(hours=2 * i)) for i in range(4)])
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=False, read_only=True, migrate=False)
    try:
        assert led.arm_family_mean_r("R1@4h") == pytest.approx(np.mean(led.arm_recent_results("R1@1h", 100)))
        assert led.arm_family_mean_r("T9@1h") is None
    finally:
        led.close()
