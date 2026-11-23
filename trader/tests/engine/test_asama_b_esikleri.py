"""23.11 kullanici karari: asama B esikleri (kagit + canli; ENTRY-only).
1) max_same_dir_risk 0.06  2) korelasyon grubu (yon basina 4)  3) kayip freni  4) toplam buyukluk tavani (3 x kasa)."""
from __future__ import annotations

import dataclasses
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from trader_core import kayip_freni as KF  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_core import risk as K  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.config import ClusterSpec, ConfigError, load_cli_config  # noqa: E402
from trader_engine.gates import EntryGate, NoVeto  # noqa: E402
from trader_engine.killswitch import Killswitch  # noqa: E402
from trader_engine.korelasyon_grubu import KorelasyonGruplari  # noqa: E402
from trader_engine.state import StateStore  # noqa: E402
from trader_engine.strategy_runner import SignalFrame  # noqa: E402
from trader_engine.types import SymbolRules  # noqa: E402

from test_engine_05_impl_smoke import T0, _params, _row  # noqa: E402

UTC = timezone.utc
CONFIG = ROOT / "config"
PAPER = load_cli_config(CONFIG, "learner", "paper")
LIVE = load_cli_config(CONFIG, "learner", "live")
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "DOGE/USDT", "ADA/USDT", "TRX/USDT"]


def _j(name):
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ yapilandirma
def test_yapilandirma_kilitli_esikler_paper_ve_live():
    for name, cfg in (("engine.paper.json", PAPER), ("engine.live.json", LIVE)):
        raw = _j(name)
        assert raw["risk"]["max_same_dir_risk"] == 0.06 and "leverage" not in raw
        assert raw["korelasyon"] == {"esik": 0.7, "pencere_gun": 30, "yon_basina_max": 4}
        assert raw["kayip_freni"] == {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}
        assert raw["toplam_buyukluk_kat"] == 3
        assert cfg.risk_config.max_same_dir_risk == 0.06
        assert cfg.korelasyon == raw["korelasyon"] and cfg.kayip_freni == raw["kayip_freni"] and cfg.toplam_buyukluk_kat == 3.0
    # tavanlar yeni degerden gevsek (daha dusuk deger izinli)
    assert K.PAPER_LIMITS["max_same_dir_risk"] >= 0.06 and K.LIVE_LIMITS["max_same_dir_risk"] >= 0.06


def test_yeni_anahtarlar_testnet_ve_backtest_icin_yasak():
    base = _j("engine.paper.json")
    for mode in ("backtest",):
        with pytest.raises(ConfigError):
            from trader_engine.config import apply_overrides
            apply_overrides(PAPER, mode=mode, korelasyon={"esik": 0.7, "pencere_gun": 30, "yon_basina_max": 4})
    assert base["korelasyon"]                                        # paper'da var


def test_yanlis_blok_reddedilir():
    from trader_engine.config import apply_overrides
    with pytest.raises(ConfigError):
        apply_overrides(PAPER, korelasyon={"esik": 0.7})
    with pytest.raises(ConfigError):
        apply_overrides(PAPER, kayip_freni={"ardisik": 5, "gunluk_oran": 0.04, "carpan": 1.5})
    with pytest.raises(ConfigError):
        apply_overrides(PAPER, toplam_buyukluk_kat=0)


# ------------------------------------------------------------------------------------------------ kapi donanimi
def _env(tmp_path, cfg, *, equity=1000.0, **over):
    cfg = dataclasses.replace(cfg, **over)
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set(f"day_start:{T0:%Y-%m-%d}", 1000.0)
    held: list = []
    state.open_positions = lambda: list(held)                                    # type: ignore[method-assign]
    acct = SimpleNamespace(equity=equity, wallet=equity)
    broker = SimpleNamespace(account=lambda: acct)
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.001, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(cfg, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    return SimpleNamespace(g=g, held=held, led=led, state=state, acct=acct, clock=clock, cfg=cfg)


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


# yalniz ilgili kuralin denendigi yalin yapilandirma: baska tavan (kume/kol/hesap) araya girmez
BOS = dict(korelasyon={}, kayip_freni={}, toplam_buyukluk_kat=None, clusters={}, arm_max_positions={}, max_positions=None,
           etiket_kurallari={}, ml_mode="off")


def _go(e, pair="BTC/USDT", side="long", D=T0):
    stop = 90.0 if side == "long" else 110.0
    fr = SignalFrame(pair=pair, status="ok", detail=None, last=_row(pair=pair, side=side, planned_stop=stop), table=None,
                     trigger_bar=(110.0, 99.0, 5.0))
    return e.g.decide(fr, D, e.g.pre(D, "1h", True, "1h"), 1)


def _ac(e, out, pair, side="long"):
    """Girilen pozisyonu (gercek boyut) acik listeye ekler."""
    s = out.size
    e.held.append(SimpleNamespace(pair=pair, side=side, risk_amount=s.risk_amount, margin=s.margin, qty=s.qty,
                                  entry_price=100.0, leverage=out.leverage))


# ------------------------------------------------------------------------------------------------ 1) ayni yon 0.06
@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_ayni_yon_risk_siniri_006_gercek_risk_matematigi(mk, cfg):
    e = mk(cfg, **BOS)
    sonuc = []
    for i, p in enumerate(PAIRS[:7]):
        o = _go(e, p)
        sonuc.append(o)
        if o.action == "enter":
            _ac(e, o, p)
    assert all(o.action == "enter" for o in sonuc[:5])                           # 5. izinli (5 x %1 = %5 <= %6)
    toplam = sum(p.risk_amount for p in e.held)
    assert toplam <= 0.06 * 1000.0 + 1e-9                                        # sinir asla asilmaz
    assert sonuc[6].action == "skip" and sonuc[6].event.skip_reason == "risk_denied"   # 7. engellenir
    assert sonuc[6].event.risk_reason.startswith("aynı yön (long) risk sınırı")
    # ters yon ayri sayilir
    assert _go(e, "ADA/USDT", "short").action == "enter"


# ------------------------------------------------------------------------------------------------ 2) korelasyon grubu
def _bars(seed_ret, n=720, base=100.0, t_end=T0):
    idx = pd.DatetimeIndex([t_end - timedelta(hours=n - i) for i in range(n)], tz="UTC")
    c = base * np.exp(np.cumsum(seed_ret))
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1.0}, index=idx)


def _sentetik(n=720):
    rng = np.random.default_rng(7)
    ortak = rng.normal(0, 0.01, n)
    gurultu = lambda: rng.normal(0, 0.002, n)       # noqa: E731
    return {
        "BTC/USDT": ortak + gurultu(), "ETH/USDT": ortak + gurultu(), "SOL/USDT": ortak + gurultu(),   # ayni grup (corr ~ 0.97)
        "XRP/USDT": ortak + gurultu(), "BNB/USDT": ortak + gurultu(),
        "DOGE/USDT": rng.normal(0, 0.01, n),                                                           # bagimsiz
    }


def _kg(getiri, **kw):
    clusters = kw.pop("clusters", {})
    return KorelasyonGruplari(lambda p, tf, until, n: _bars(getiri[p], len(getiri[p])) if p in getiri else pd.DataFrame(),
                              list(getiri) + ["ADA/USDT"], clusters, 0.7, 30, **kw)


def test_korelasyon_matrisi_sentetik_barlar_esik_07():
    kg = _kg(_sentetik())
    assert kg.korelasyon("BTC/USDT", "ETH/USDT", T0) > 0.9
    assert abs(kg.korelasyon("BTC/USDT", "DOGE/USDT", T0)) < 0.2
    assert kg.ayni_grup("BTC/USDT", "ETH/USDT", T0) is True
    assert kg.ayni_grup("BTC/USDT", "DOGE/USDT", T0) is False


def test_korelasyon_saatlik_onbellek(mk):
    n = {"c": 0}
    g = _sentetik()

    def bars(p, tf, until, k):
        n["c"] += 1
        return _bars(g[p], len(g[p]))
    kg = KorelasyonGruplari(bars, list(g), {}, 0.7, 30)
    kg.ayni_grup("BTC/USDT", "ETH/USDT", T0)
    c1 = n["c"]
    kg.ayni_grup("BTC/USDT", "SOL/USDT", T0 + timedelta(minutes=59))             # saat dolmadi: yeniden hesap yok
    assert n["c"] == c1 and kg.yenileme == 1
    kg.ayni_grup("BTC/USDT", "SOL/USDT", T0 + timedelta(minutes=61))
    assert kg.yenileme == 2 and n["c"] == 2 * c1


def test_korelasyon_yedek_sabit_kume_ve_veri_hatasi_cokmez():
    cl = {"k": ClusterSpec(pairs=("ADA/USDT", "TRX/USDT"), max_positions=9)}
    g = _sentetik()
    kg = _kg(g, clusters=cl)
    # ADA verisi yok (bos DataFrame) -> yedek: ayni sabit kume
    assert kg.ayni_grup("ADA/USDT", "TRX/USDT", T0) is True
    assert kg.ayni_grup("ADA/USDT", "BTC/USDT", T0) is False                     # farkli kume, veri yok
    # kaynak patlarsa: hepsi yedege duser, istisna yok
    kg2 = KorelasyonGruplari(lambda *a: (_ for _ in ()).throw(RuntimeError("db")), ["ADA/USDT", "TRX/USDT"], cl, 0.7, 30)
    assert kg2.ayni_grup("ADA/USDT", "TRX/USDT", T0) is True
    # yetersiz ortak getiri (kisa seri) -> yedek
    kisa = {"BTC/USDT": g["BTC/USDT"][:50], "ETH/USDT": g["ETH/USDT"][:50]}
    kg3 = KorelasyonGruplari(lambda p, tf, u, n: _bars(kisa[p], 50), list(kisa), {}, 0.7, 30)
    assert kg3.korelasyon("BTC/USDT", "ETH/USDT", T0) is None
    # kaynak hic yok (None): sabit kume
    assert KorelasyonGruplari(None, ["ADA/USDT", "TRX/USDT"], cl, 0.7, 30).ayni_grup("ADA/USDT", "TRX/USDT", T0)


def test_korelasyon_seans_kapali_arac_eldeki_barlarla():
    """Hisse: gecelik/hafta sonu bar yok (aralikli seri) -> yalniz ardisik saatler arasi getiri; hesap cokmez."""
    g = _sentetik()
    df = _bars(g["ETH/USDT"], 720)
    gunduz = df[[(t.hour in range(14, 21)) and t.weekday() < 5 for t in df.index]]
    kg = KorelasyonGruplari(lambda p, tf, u, n: gunduz if p == "NVDA/USDT" else _bars(g[p], 720), ["BTC/USDT", "NVDA/USDT"], {}, 0.7, 30,
                            min_ortak=50)
    c = kg.korelasyon("BTC/USDT", "NVDA/USDT", T0)
    assert c is not None and c > 0.7


@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_korelasyon_grubu_4_ayni_yon_dolunca_engeller(mk, cfg):
    e = mk(cfg, **{**BOS, "korelasyon": {"esik": 0.7, "pencere_gun": 30, "yon_basina_max": 4}})
    g = _sentetik()
    e.g.korelasyon = _kg(g)
    # grup: BTC ETH SOL XRP BNB (corr ~ 0.97); 4 acik long
    for p in ("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT"):
        o = _go(e, p)
        assert o.action == "enter", (p, o.code)
        _ac(e, o, p)
    o5 = _go(e, "BNB/USDT")                                                      # 5.: grupta 4 long var -> engel
    assert o5.action == "skip" and o5.code == "korelasyon_grubu"
    assert o5.event.skip_reason == "risk_denied" and o5.event.risk_allowed is False
    assert o5.event.veto_reason == "gate:korelasyon_grubu" and "korelasyon grubu" in o5.event.risk_reason
    assert e.g.counters["skip:korelasyon_grubu"] == 1 and e.g.counters["korelasyon_grubu_blok"] == 1
    assert e.led.record_decision(o5.event)                                       # defter kabul eder
    assert _go(e, "BNB/USDT", "short").action == "enter"                         # ters yon sayilmaz
    assert _go(e, "DOGE/USDT").action == "enter"                                 # bagimsiz cift baska grup


def test_korelasyon_yedek_kumeyle_engel_ve_hata_serbest(mk):
    cl = {"k": ClusterSpec(pairs=("ADA/USDT", "TRX/USDT", "XRP/USDT", "SOL/USDT", "BNB/USDT"), max_positions=9)}
    e = mk(PAPER, **{**BOS, "korelasyon": {"esik": 0.7, "pencere_gun": 30, "yon_basina_max": 4}})
    e.g.korelasyon = KorelasyonGruplari(None, PAIRS, cl, 0.7, 30)                # veri yok -> sabit kume yedegi
    for p in ("TRX/USDT", "XRP/USDT", "SOL/USDT", "BNB/USDT"):
        _ac(e, _go(e, p), p)
    assert _go(e, "ADA/USDT").code == "korelasyon_grubu"
    e.g.korelasyon = SimpleNamespace(grup_sayisi=lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert _go(e, "ADA/USDT").action == "enter" and e.g.counters["korelasyon_grubu_hata"] == 1   # asla cokmez


# ------------------------------------------------------------------------------------------------ 3) kayip freni
def _kapat(led, kazanc_dizisi, gun=None, baslangic=None):
    """Eskiden yeniye: True = kazanc. Defterde kapanmis islemler (gercek yol: karar + giris + cikis)."""
    t0 = baslangic or (T0 - timedelta(hours=8))   # ayni UTC gun (seri yalniz bugunku kapanislari sayar)
    n0 = len(led.list_closed_trades(limit=1000)) + len(led.list_open_trades())
    for i, w in enumerate(kazanc_dizisi, start=n0 + 1):
        bar = t0 + timedelta(minutes=30 * i)
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup="R1", regime="range", atr_ratio=1.1, rh=105.0, rl=95.0,
            rh_touches=2, rl_touches=3, features={"atr_1h": 1.0, "stop_dist_atr": 2.0, "atr_4h": 2.0, "wick_ratio": 0.5, "rr": 2.5,
                                                   "edge_dist_atr": 0.1}, planned_entry=100.0, planned_stop=98.0, planned_target=105.0, param_version_id=1,
            veto_status="not_evaluated", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=1.0, size_notional=100.0,
            size_margin=33.0, size_risk_amount=10.0, leverage=3, final_action="entered", skip_reason=None))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 100.0, 1.0, 3, 0.05))
        led.record_trade_exit(L.TradeExit(i, bar + timedelta(minutes=20), 105.0 if w else 98.0, "target" if w else "stop", 105.0, 0.05, 0.1))


def _risk(o):
    return o.size.risk_amount


def test_fren_saf_kural():
    t = lambda pnl, r="stop": SimpleNamespace(realized_pnl=pnl, exit_reason=r)   # noqa: E731
    cfg = {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}
    assert KF.karar(cfg, [t(-1)] * 4, 1000, 1000).aktif is False                  # 4 kayip: yok
    assert KF.karar(cfg, [t(-1)] * 5, 1000, 1000) == KF.FrenKarari(True, "ardisik", 0.5, 5)
    assert KF.karar(cfg, [t(+1)] + [t(-1)] * 9, 1000, 1000).aktif is False        # ilk kazancli kapanis: kalkti
    assert KF.karar(cfg, [t(-1)] * 4 + [t(5, "manual")] + [t(-1)], 1000, 1000).aktif is True   # elle kapanis atlanir
    assert KF.karar(cfg, [], 960.0, 1000.0).neden == "gunluk"                     # tam %4
    assert KF.karar(cfg, [], 960.01, 1000.0).aktif is False
    assert KF.karar(None, [t(-1)] * 9, 1, 1000) is KF.YOK
    assert KF.goreli_carpan(KF.FrenKarari(True, "x", 0.5, 5), 0.01, 0.01) == 0.5
    assert KF.goreli_carpan(KF.FrenKarari(True, "x", 0.5, 5), 0.01, 0.0035) == 1.0   # kademe zaten dusuk: ARTIRMAZ
    assert KF.goreli_carpan(KF.YOK, 0.01, 0.01) == 1.0


@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_fren_ardisik_tetik_kalkis_ve_yeniden_baslatma(tmp_path, cfg):
    kw = {**BOS, "kayip_freni": {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}}
    e = _env(tmp_path, cfg, **kw)
    try:
        temel = _risk(_go(e))
        _kapat(e.led, [False] * 4)
        assert _risk(_go(e, "ETH/USDT")) == pytest.approx(temel, rel=1e-6)        # 4 kayip: tam boyut
        _kapat(e.led, [False])
        o = _go(e, "SOL/USDT")
        assert _risk(o) == pytest.approx(temel * 0.5, rel=0.02)                   # 5. kayip: yarim risk (0.01 -> 0.005)
        assert o.event.features["kayip_freni"] == "ardisik" and o.event.features["kayip_freni_carpani"] == 0.5
        assert e.g.counters["kayip_freni_yarim:ardisik"] == 1
        # yeniden baslatma: ayni defter + yeni kapi nesnesi => ayni durum (ek durum dosyasi yok)
        e2 = _env(tmp_path / "yeni", cfg, **kw) if (tmp_path / "yeni").mkdir() is None else None
        e2.g.ledger = e.led
        assert _risk(_go(e2, "XRP/USDT")) == pytest.approx(temel * 0.5, rel=0.02)
        e2.state.close(); e2.led.close()
        # ilk kazancli kapanista kalkar
        _kapat(e.led, [True])
        assert _risk(_go(e, "BNB/USDT")) == pytest.approx(temel, rel=1e-6)
    finally:
        e.state.close(); e.led.close()


def test_fren_ardisik_seri_yeni_utc_gununde_kalkar(mk):
    kw = {**BOS, "kayip_freni": {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}}
    e = mk(PAPER, **kw)
    temel = _risk(_go(e))
    _kapat(e.led, [False] * 5, baslangic=T0 - timedelta(hours=40))   # T0-40h .. dunden once: bugun degil
    D2 = T0 + timedelta(days=1)
    with e.state.tx():
        e.state.kv_set(f"day_start:{D2:%Y-%m-%d}", 1000.0)
    assert _risk(_go(e, "ETH/USDT", D=D2)) == pytest.approx(temel, rel=1e-6)     # yeni gun: fren yok


def test_fren_gunluk_yuzde4_ve_ertesi_gun_kalkar(mk):
    kw = {**BOS, "kayip_freni": {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}}
    e = mk(PAPER, **kw)
    temel = _risk(_go(e))
    e.acct.equity = 961.0                                                          # -%3.9
    assert _risk(_go(e, "ETH/USDT")) == pytest.approx(temel * 0.961, rel=0.02)     # fren yok (yalniz kasa orani)
    e.acct.equity = 960.0                                                          # -%4.0: fren
    o = _go(e, "SOL/USDT")
    assert o.event.features["kayip_freni"] == "gunluk"
    assert _risk(o) == pytest.approx(temel * 0.96 * 0.5, rel=0.02)
    # yeni UTC gunu: gun basi kasa = 960 (kv) -> fren kalkar
    D2 = T0 + timedelta(days=1)
    with e.state.tx():
        e.state.kv_set(f"day_start:{D2:%Y-%m-%d}", 960.0)
    e.clock.set(D2 + timedelta(seconds=5)) if hasattr(e.clock, "set") else None
    o2 = _go(e, "XRP/USDT", D=D2)
    assert "kayip_freni" not in (o2.event.features or {}) and _risk(o2) == pytest.approx(temel * 0.96, rel=0.02)


def test_fren_kademe_ve_kol_ile_asgari_alir_asla_artirmaz(mk):
    kw = {**BOS, "kayip_freni": {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}}
    e = mk(PAPER, **kw)
    temel = _risk(_go(e))
    _kapat(e.led, [False] * 5)
    # 1) kol kucultme 0.3 < fren 0.5 -> min = 0.3 (carpilmaz, 0.15 degil)
    e.led.arm_recent_results = lambda aid, n: [-1.0] * 10                          # type: ignore[method-assign]
    assert _risk(_go(e, "ETH/USDT")) == pytest.approx(temel * 0.3, rel=0.03)
    # 2) kol 0.5 ile fren 0.5 -> 0.5
    e.led.arm_recent_results = lambda aid, n: [-1.0] * 5                           # type: ignore[method-assign]
    assert _risk(_go(e, "SOL/USDT")) == pytest.approx(temel * 0.5, rel=0.02)
    e.led.arm_recent_results = lambda aid, n: []                                   # type: ignore[method-assign]
    # 3) kademe (ladder) hedefi 0.0035 < fren hedefi 0.005: fren artirmaz, kademe hedefi korunur
    e.g.ladder = SimpleNamespace(risk_config=K.tightened(PAPER.risk_config, target_trade_risk=0.0035), gate_code=lambda: None)
    assert _risk(_go(e, "XRP/USDT")) == pytest.approx(temel * 0.35, rel=0.03)
    # 4) kademe 0.005 (basamak 0) ile fren: 0.005 (0.0025 degil)
    e.g.ladder = SimpleNamespace(risk_config=K.tightened(PAPER.risk_config, target_trade_risk=0.005), gate_code=lambda: None)
    assert _risk(_go(e, "BNB/USDT")) == pytest.approx(temel * 0.5, rel=0.02)


def test_fren_asgari_boyut_altinda_tam_boyuta_donmez(mk):
    kw = {**BOS, "kayip_freni": {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}}
    e = mk(PAPER, **kw)
    temel = _go(e)
    _kapat(e.led, [False] * 5)
    r0 = e.g.rules_fn
    e.g.rules_fn = lambda p: dataclasses.replace(r0(p), min_notional=temel.size.notional * 0.8)
    o = _go(e, "ETH/USDT")
    assert o.action == "skip" and o.event.skip_reason == "risk_denied"             # yarim boyut emir altinda: tam boyuta ARTIRILMAZ
    assert e.g.counters["kayip_freni_boyut_reddi"] == 1


# ------------------------------------------------------------------------------------------------ 4) toplam buyukluk
@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_toplam_buyukluk_sinir_3_kat_kasa(mk, cfg):
    e = mk(cfg, **{**BOS, "toplam_buyukluk_kat": 3.0}, risk={"max_open_risk": 0.24, "max_same_dir_risk": 0.16, "daily_max_loss": 0.08})
    temel = _go(e)
    notional = temel.size.notional
    assert 0 < notional <= 1000.0
    # acik toplam + aday == 3 x kasa -> izinli; 1 kurus fazlasi -> engel
    e.held.append(SimpleNamespace(pair="ETH/USDT", side="long", risk_amount=0.01, margin=0.1, qty=1.0,
                                  entry_price=3000.0 - notional, leverage=3))
    assert _go(e, "SOL/USDT").action == "enter"
    e.held[0] = SimpleNamespace(pair="ETH/USDT", side="long", risk_amount=0.01, margin=0.1, qty=1.0,
                                entry_price=3000.0 - notional + 0.01, leverage=3)
    o = _go(e, "SOL/USDT")
    assert o.action == "skip" and o.code == "toplam_buyukluk" and o.event.skip_reason == "risk_denied"
    assert o.event.risk_allowed is False and o.event.risk_reason.startswith("toplam büyüklük tavanı")
    assert e.g.counters["skip:toplam_buyukluk"] == 1 and e.g.counters["toplam_buyukluk_blok"] == 1
    assert e.led.record_decision(o.event)
    # kasa buyudukce tavan buyur
    e.acct.equity = 1100.0
    assert _go(e, "XRP/USDT").action == "enter"


def test_toplam_buyukluk_kapali_serbest_hatada_kapali(mk):
    e = mk(PAPER, **{**BOS, "toplam_buyukluk_kat": None})
    e.held.append(SimpleNamespace(pair="ETH/USDT", side="long", risk_amount=0.01, margin=0.1, qty=1e9, entry_price=100.0, leverage=3))
    assert _go(e).action == "enter"
    e2 = mk(PAPER, **{**BOS, "toplam_buyukluk_kat": 3.0})
    e2.held.append(SimpleNamespace(pair="ETH/USDT", side="long", risk_amount=0.01, margin=0.1))   # bozuk satir (qty/leverage yok): istisna yutulur, giris serbest
    o = _go(e2)                                                                       # 23.11 inceleme: fail-CLOSED
    assert o.action == "skip" and o.code == "buyukluk_okunamadi" and e2.g.counters["toplam_buyukluk_hata"] == 1
    assert e2.g.counters["skip:buyukluk_okunamadi"] == 1 and e2.led.record_decision(o.event)


# ------------------------------------------------------------------------------------------------ yalniz paper/live
def test_testnet_ve_backtest_kapisi_etkilenmez(mk):
    """Kapi dali `paper = mode in (paper, live)` icinde: testnet/backtest ayni kodu GORMEZ (esikler cfg'de de yasak). Risk matematigi
    (K.check_entry) paylasilir ama yapilandirma yalniz paper/live'da 0.06 verir."""
    e = mk(PAPER, **{**BOS, "toplam_buyukluk_kat": 3.0, "kayip_freni": {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}})
    _kapat(e.led, [False] * 5)
    e.g.cfg = dataclasses.replace(e.g.cfg, mode="testnet")
    temel = _go(e, "ETH/USDT")
    assert not any(k.startswith("kayip_freni") for k in e.g.counters)
    if temel.action == "enter":
        assert "kayip_freni" not in (temel.event.features or {})
    assert e.g.korelasyon is None
    for name in ("engine.testnet.json", "engine.base.json", "engine.learner.json"):
        raw = _j(name)
        assert not {"korelasyon", "kayip_freni", "toplam_buyukluk_kat"} & set(raw)


def test_cikis_ve_acik_pozisyonlar_dokunulmaz():
    """Yeni kod yalniz gates.decide giris yolunda: pozisyon yoneticisi/emir yoneticisi/motor cikis kodu yeni modulleri hic ice aktarmaz."""
    for f in ("position_manager.py", "order_manager.py", "brokers/paper.py"):
        src = (ROOT / "src" / "trader_engine" / f).read_text(encoding="utf-8")
        assert "kayip_freni" not in src and "korelasyon_grubu" not in src and "toplam_buyukluk" not in src


def test_turkce_neden_metinleri():
    from trader_core import panel_pano as PP
    from trader_core import strateji_veri as SV
    from trader_core import telegram as TG
    for k in ("korelasyon_grubu", "toplam_buyukluk"):
        assert k in TG.ATLAMA_TR and k in PP.NEDEN_KISA
    assert SV.risk_limiti("korelasyon grubu sınırı: x") == "korelasyon_grubu"
    assert SV.risk_limiti("toplam büyüklük tavanı: x") == "toplam_buyukluk"


# ------------------------------------------------------------------------------------------------ inceleme duzeltmeleri
def test_fren_okunamazsa_giris_yok_fail_closed(mk):
    e = mk(PAPER, **{**BOS, "kayip_freni": {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}})
    e.led.list_closed_trades = lambda **k: (_ for _ in ()).throw(RuntimeError("db"))   # type: ignore[method-assign]
    o = _go(e)
    assert o.action == "skip" and o.code == "fren_okunamadi" and o.event.skip_reason == "risk_denied"
    assert e.g.counters["kayip_freni_hata"] == 1 and e.g.counters["skip:fren_okunamadi"] == 1


def test_fren_gunluk_ilk_kazancli_kapanista_kalkar_ve_basa_bas_notr():
    t = lambda pnl, r="stop": SimpleNamespace(realized_pnl=pnl, exit_reason=r, exit_ts=T0)   # noqa: E731
    cfg = {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}
    assert KF.karar(cfg, [t(-1)], 950.0, 1000.0, T0).neden == "gunluk"
    assert KF.karar(cfg, [t(+1), t(-1)], 950.0, 1000.0, T0).aktif is False        # en yeni kapanis kazanc: kalkar
    assert KF.karar(cfg, [t(0), t(+1), t(-1)], 950.0, 1000.0, T0).aktif is False  # basa-bas notr: kazanc hala en yeni
    assert KF.karar(cfg, [t(0), t(-1)], 950.0, 1000.0, T0).neden == "gunluk"      # basa-bas kaldirmaz
    # basa-bas seriyi ne keser ne sayar: 3 kayip, 0, 2 kayip = 5 ardisik
    assert KF.karar(cfg, [t(-1), t(-1), t(0), t(-1), t(-1), t(-1)], 1000.0, 1000.0, T0).neden == "ardisik"
    assert KF.ardisik_kayip([t(-1), t(0), t(+1), t(-1)], 5) == 1


def test_korelasyon_pencere_zamana_dayali_ve_yeniden_deneme_5dk():
    g = _sentetik()
    seen = {}

    def bars(p, tf, until, n):
        d = _bars(np.tile(g[p], 3)[:1500], 1500)                    # 62 gunluk veri; pencere zamanla 30 gune kirpilir
        seen["n"] = len(d)
        return d
    kg = KorelasyonGruplari(bars, list(g), {}, 0.7, 30)
    kg.korelasyon("BTC/USDT", "ETH/USDT", T0)
    assert kg.korelasyon("BTC/USDT", "ETH/USDT", T0) > 0.9
    df = kg._pencere(_bars(np.tile(g["BTC/USDT"], 3)[:1500], 1500), T0 - timedelta(days=30))
    assert df.index.min() >= T0 - timedelta(days=30) and len(df) <= 30 * 24 + 1
    # basarisiz hesap: 5 dk sonra tekrar, saat beklemez
    kg2 = KorelasyonGruplari(lambda *a: (_ for _ in ()).throw(RuntimeError("x")), list(g), {}, 0.7, 30)
    kg2.korelasyon("BTC/USDT", "ETH/USDT", T0)
    kg2.korelasyon("BTC/USDT", "ETH/USDT", T0 + timedelta(minutes=4))
    assert kg2.yenileme == 1
    kg2.korelasyon("BTC/USDT", "ETH/USDT", T0 + timedelta(minutes=6))
    assert kg2.yenileme == 2


def test_korelasyon_yetersiz_cift_icin_tek_log_satiri(caplog):
    import logging
    g = _sentetik()
    kisa = {**{k: v for k, v in g.items() if k in ("BTC/USDT", "ETH/USDT")}}
    kg = KorelasyonGruplari(lambda p, tf, u, n: _bars(g[p], 720) if p in kisa else pd.DataFrame(),
                            ["BTC/USDT", "ETH/USDT", "NVDA/USDT", "AAPL/USDT", "MSFT/USDT"] if False else list(g), {}, 0.7, 30)
    with caplog.at_level(logging.INFO, logger="engine.korelasyon"):
        kg.korelasyon("BTC/USDT", "ETH/USDT", T0)
    msgs = [r for r in caplog.records if "yetersiz" in r.getMessage()]
    assert len(msgs) == 1


def test_toplam_buyukluk_mark_fiyat_varsa_mark_kullanilir(mk):
    e = mk(PAPER, **{**BOS, "toplam_buyukluk_kat": 3.0})
    n = _go(e).size.notional
    e.held.append(SimpleNamespace(pair="ETH/USDT", side="long", risk_amount=0.01, margin=0.1, qty=1.0, entry_price=100.0, leverage=3))
    assert _go(e, "SOL/USDT").action == "enter"                                    # giris fiyati 100: kucuk
    e.g.broker.positions = lambda: [SimpleNamespace(pair="ETH/USDT", mark_price=3000.0 - n + 0.01)]   # type: ignore[attr-defined]
    assert _go(e, "SOL/USDT").code == "toplam_buyukluk"                            # mark 3000: tavani asar


def test_fren_ardisik_seri_gece_yarisini_asar_ve_tetik_gunu_sonrasi_sifirlanir():
    """23.11 kullanici karari b: seri gun sinirina bakmaz; fren tetik gununden sonraki gun basinda kalkar, sayac sifirlanir."""
    cfg = {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}
    gun = T0.replace(hour=0, minute=0, second=0, microsecond=0)
    t = lambda pnl, ts: SimpleNamespace(realized_pnl=pnl, exit_reason="stop", exit_ts=ts)   # noqa: E731
    dun = [t(-1, gun - timedelta(hours=h)) for h in (1, 2, 3)]            # dun 3 kayip (yeniden eskiye)
    bugun = [t(-1, gun + timedelta(hours=h)) for h in (2, 1)]             # bugun 2 kayip
    assert KF.karar(cfg, bugun + dun, 1000.0, 1000.0, gun) == KF.FrenKarari(True, "ardisik", 0.5, 5)   # 3 + 2 = 5: tetik
    assert KF.karar(cfg, bugun[1:] + dun, 1000.0, 1000.0, gun).aktif is False                         # 4 kayip: yok
    dun5 = [t(-1, gun - timedelta(hours=h)) for h in (1, 2, 3, 4, 5)]     # dun tetiklendi
    assert KF.karar(cfg, dun5, 1000.0, 1000.0, gun).aktif is False                                    # yeni gun: kalkti
    assert KF.karar(cfg, bugun + dun5, 1000.0, 1000.0, gun).ardisik_kayip == 2                       # sayac sifirdan
    bugun5 = [t(-1, gun + timedelta(hours=h)) for h in (5, 4, 3, 2, 1)]
    assert KF.karar(cfg, bugun5 + dun5, 1000.0, 1000.0, gun).neden == "ardisik"                      # 5 YENI kayip: yeniden
    assert KF.karar(cfg, [t(+1, gun + timedelta(hours=3))] + bugun + dun, 1000.0, 1000.0, gun).aktif is False   # kazanc keser
