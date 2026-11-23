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
    assert tam == UY.gunluk_kapanislar(df, T0) and len(tam) == 90                       # bugunku (kismi, acik) gun girmez
    assert UY.sinifla(tam, 50, 10, 60) == "boga"
    # henuz kapanmamis 4h mumu (08:00-12:00) kapanis sayilmaz
    ac = pd.concat([df, pd.DataFrame({"close": [1.0]}, index=pd.DatetimeIndex([T0 - timedelta(hours=1)], tz="UTC"))])
    assert UY.gunluk_kapanislar(ac, T0) == UY.gunluk_kapanislar(df, T0)
    # kapanis, ertesi gun 00:00'da (D+1) gunun tamamlanmasiyla girer
    assert len(UY.gunluk_kapanislar(df, BUGUN - timedelta(hours=4))) == 89
    # gece yarisindan bir mum sonra: bugunun 00:00 mumu kapanmis olsa da bugun hala acik => 90 gun
    assert len(UY.gunluk_kapanislar(df2, BUGUN + timedelta(hours=5))) == 90


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
    assert KK.karar([-0.1] * 4, aile_ort=-5.0).carpan == 0.5  # 5'ten az islem de buzulmus degerle degerlendirilir
    o = KK.ozellikler(k)
    assert o["kol_aile_r"] == 0.5 and o["kol_buz_r_5"] == pytest.approx(0.3)


def test_azaltilanlar_buzulmeli():
    veri = {"R1@1h": [-0.1] * 5, "R1@4h": [2.0] * 30}      # R1 ailesi cok kazancli
    assert set(KK.azaltilanlar(veri)) == set()              # buzulme: kol kucultulmez
    assert set(KK.azaltilanlar(veri, buzulmeli=False)) == {"R1@1h"}


def test_kapi_buzulme_kullanir(kol_env):
    """Karar yolu: ham kural 0.5 verirdi; saglikli aile ortalamasiyla tam boyut."""
    kol_env.led.arm_recent_results = lambda aid, n: [-0.1] * 5          # type: ignore[method-assign]
    kol_env.led.arm_family_mean_r = lambda aid, until=None: None                    # type: ignore[method-assign]
    ham = _kol_go(kol_env)
    assert ham.event.features["kol_boyut_carpani"] == 0.5
    kol_env.led.arm_family_mean_r = lambda aid, until=None: 0.5                     # type: ignore[method-assign]
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


# ---- fikir 7 (duzeltme): seansli gun, gunun son mumu, gece yarisi yarisi, uc uca ------------------------------------
def _mumlar(gunler, saatler, kapanis_fn):
    idx, c = [], []
    for g in gunler:
        for h in saatler:
            idx.append(g + timedelta(hours=h))
            c.append(kapanis_fn(g, h))
    return pd.DataFrame({"close": c}, index=pd.DatetimeIndex(idx, tz="UTC"))


def test_seansli_gun_2_mumla_gun_uretir_ve_gunun_son_mumu_alinir():
    gunler = [BUGUN - timedelta(days=90 - i) for i in range(90)]
    df = _mumlar(gunler, (12, 16), lambda g, h: 100.0 + (g - gunler[0]).days + (0.5 if h == 12 else 0.9))   # gun ici mumlar farkli kapanisli
    k = UY.gunluk_kapanislar(df, BUGUN + timedelta(hours=9))
    assert len(k) == 90 and k[0] == pytest.approx(100.9) and k[-1] == pytest.approx(189.9)    # gunun SON mumu (16:00), 12:00 degil
    tek = _mumlar(gunler[:3], (8,), lambda g, h: 7.0)
    assert UY.gunluk_kapanislar(tek, BUGUN) == [7.0, 7.0, 7.0]                                  # tek mumlu gun de gun
    assert UY.sinifla(k, 50, 10, 60) == "boga"


def test_gece_yarisi_yarisi_onbellek_sabitlemez():
    gunler = [BUGUN - timedelta(days=90 - i) for i in range(90)]
    tam = _mumlar(gunler, (0, 4, 8, 12, 16, 20), lambda g, h: 100.0 + (g - gunler[0]).days)
    eksik = tam[tam.index != BUGUN - timedelta(hours=4)]                 # dunun 20:00 mumu henuz yazilmamis
    n = {"c": 0}
    kaynak = {"df": eksik}

    def bars(p, tf, until, k):
        n["c"] += 1
        return kaynak["df"]
    u = UY.UzunYon(CFG, bars)
    gece = BUGUN + timedelta(minutes=2)
    u.rejim("BTC/USDT", gece)
    assert u._onbellek["BTC/USDT"][0][1] == BUGUN - timedelta(hours=8)           # son mum 16:00
    kaynak["df"] = tam
    u.rejim("BTC/USDT", gece + timedelta(minutes=1))                             # yeniden hesap (sabitlenmedi)
    assert n["c"] == 2 and u._onbellek["BTC/USDT"][0][1] == BUGUN - timedelta(hours=4)
    u.rejim("BTC/USDT", gece + timedelta(minutes=2))                             # son mum 20:00: yerlesti, onbellekten
    assert n["c"] == 2


def test_uzun_yon_paper_live_json_anahtarlari_birebir():
    import json
    cfgdir = ROOT / "config"
    p = json.loads((cfgdir / "engine.paper.json").read_text(encoding="utf-8"))
    l = json.loads((cfgdir / "engine.live.json").read_text(encoding="utf-8"))
    assert p.get("uzun_yon") == l.get("uzun_yon")
    assert PAPER.uzun_yon == LIVE.uzun_yon


def test_engine_baglantisi_gercek_store_view_bars(tmp_path):
    """engine.py: gate.uzun_yon.bars_fn = view.bars; uzun_yon bu baglantiyla (sahte view.bars) rejim uretir."""
    import inspect
    from trader_engine import engine as E
    src = inspect.getsource(E)
    assert "self.gate.uzun_yon.bars_fn = lambda p, tf, until, n: self.view.bars(p, tf, until, n)" in src
    gunler = [BUGUN - timedelta(days=90 - i) for i in range(90)]
    df = _mumlar(gunler, (0, 4, 8, 12, 16, 20), lambda g, h: 100.0 + (g - gunler[0]).days)
    cagri = []

    class View:                                                    # store.view.bars(pair, tf, until, n) imzasi
        def bars(self, pair, tf, until, n):
            cagri.append((pair, tf, until, n))
            return df[df.index + timedelta(hours=4) <= until].tail(n)
    view = View()
    u = UY.UzunYon(CFG)
    u.bars_fn = lambda p, tf, until, n: view.bars(p, tf, until, n)
    assert u.rejim("BTC/USDT", T0) == "boga" and cagri[0][:2] == ("BTC/USDT", "4h")


# ---- fikir 8 (duzeltme): n gercek islem sayisi, aile kolun kendisi haric -------------------------------------------
def test_buzulme_n0_aile_degeri_ve_az_veri():
    k = KK.karar([], aile_ort=-0.2)
    assert k.carpan == 0.5 and k.n == 0 and k.buz_5 == pytest.approx(-0.2)             # n = 0: yalniz aile
    assert KK.karar([], aile_ort=0.2).carpan == 1.0
    assert KK.karar([-0.1] * 3, aile_ort=-0.5).carpan == 0.5                           # n < 5 kol, aile negatif: kucultulur
    assert KK.karar([-0.1] * 3, aile_ort=0.5).carpan == 1.0                            # aile pozitif: kucultulmez ((-0.3+5)/13 > 0)
    assert KK.karar([-0.1] * 3, aile_ort=-0.5).buz_5 == pytest.approx((3 * -0.1 + 10 * -0.5) / 13)
    assert KK.karar([-0.1] * 3).carpan == 1.0                                          # ham kural: n < 5 degismez
    assert KK.karar([-1.0] * 9, aile_ort=-0.5).carpan == 0.5                           # 0.3 yalniz dolu 10'luk pencerede
    assert KK.karar([-1.0] * 10, aile_ort=-0.5).carpan == 0.3


def test_azaltilanlar_aile_kolun_kendisini_icermez():
    veri = {"R1@1h": [-0.1] * 5}                                  # tek kol: aile (kendisi haric) yok => ham kural
    assert set(KK.azaltilanlar(veri)) == {"R1@1h"}
    veri["R1@4h"] = [2.0] * 5
    assert set(KK.azaltilanlar(veri)) == set()                    # diger kol kazancli aile


D0 = datetime(2026, 11, 1, tzinfo=UTC)


def _arm_defter(path, plan):
    """plan: [(arm_id, cikis_zamani, kazanc_mi)] -> ledger yolu; her islem ayri karar+giris+cikis (cikis = bar + 1 saat)."""
    from panel_support import PARAMS
    from trader_core import ledger as L
    led = L.open_ledger(path, "learner", clock=lambda: datetime(2027, 1, 1, tzinfo=UTC))
    led.init_params(PARAMS, reason="x")
    for i, (arm, cikis, win) in enumerate(plan, start=1):
        bar = cikis - timedelta(hours=1)
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup=arm.split("@")[0], regime="range", atr_ratio=1.1,
            rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
            features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.1},
            planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1, veto_status="allowed", veto_reason=None,
            risk_allowed=True, risk_reason="ok", size_qty=0.3, size_notional=600.0, size_margin=200.0, size_risk_amount=13.188,
            leverage=3, final_action="entered", skip_reason=None, arm_id=arm))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        led.record_trade_exit(L.TradeExit(i, cikis, 2079.0 if win else 1960.0, "target" if win else "stop", 2100.0, 0.3, 0.1))
    led.close()


def test_defter_aile_penceresi_holdout_kendisi_haric(tmp_path):
    from trader_core import ledger as L
    path = str(tmp_path / "l.sqlite")
    D = datetime(2026, 12, 1, tzinfo=UTC)
    gun = lambda n: D - timedelta(days=n)
    plan = [("R1@1h", gun(1), True),                      # kolun kendisi
            ("R1@15m", gun(2), True), ("R1@4h", gun(5), False),     # aile (diger TF'ler): +, -
            ("T9@1h", gun(2), False),                     # baska kurulum (kayip R'si referansi)
            ("R1@4h", D + timedelta(days=1), False),      # until sonrasi
            ("R1@4h", datetime(2026, 7, 1, tzinfo=UTC), False),     # holdout icinde
            ("R1@4h", gun(95), False)]                    # 90 gunden eski
    _arm_defter(path, plan)
    led = L.open_ledger(path, "learner", create=False, read_only=True, migrate=False)
    try:
        r15, r4 = led.arm_recent_results("R1@15m", 1)[0], led.arm_recent_results("T9@1h", 1)[0]      # kazanc / kayip net R
        assert r15 > 0 > r4
        assert led.arm_family_mean_r("R1@1h", D) == pytest.approx((r15 + r4) / 2)                              # yalniz R1@15m ve R1@4h(gun 5)
        kendi = led.arm_recent_results("R1@1h", 1)[0]
        assert led.arm_family_mean_r("R1@15m", D) == pytest.approx((kendi + r4) / 2)                          # cok-TF ailesi birlesir (1h + 4h)
        assert led.arm_family_mean_r("T9@1h", D) is None                                                      # baska kurulum karismaz
        assert led.arm_family_mean_r("R1@1h", gun(3)) == pytest.approx(r4)                                    # until = gun 3: yalniz gun-5 islemi
        assert led.arm_family_mean_r("R1@1h", D + timedelta(days=2)) == pytest.approx((r15 + r4 + r4) / 3)    # until sonrasi ancak yeni until ile girer
        assert led.FAMILY_HOLDOUT == __import__("trader_engine.holdout", fromlist=["HOLDOUT"]).HOLDOUT        # parite
    finally:
        led.close()
