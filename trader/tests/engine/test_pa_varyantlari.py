"""24.11 kullanici karari: PA varyantlari (26.11 Paket 3 sonrasi 5 varyant x 3 ZD = 15 kol; ana kol davranisi degismez).
Her varyant: sentetik long + short aynasi + bozulan kosul; ileriye bakis / pencere bagimsizligi; kimlik, kapasite, kagit = canli."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import indicators as I
from trader_core.signals import SignalParams
from trader_engine import arm_guard as AG
from trader_engine import config as C
from trader_engine.strategies import arms
from trader_engine.strategies.arms import _kutuphane as K
from trader_engine.strategies.arms import b1 as B1M
from trader_engine.strategies.arms import h2v, t1v
from trader_engine.strategies.arms import h2 as H2M
import bos_cekirdek as M1MOD
from trader_engine.strategies.arms import s1 as S1M
from trader_engine.strategies.arms import tf1 as TF1M

ROOT = Path(__file__).resolve().parents[2]
TFS = ("1h", "4h", "1d")
KAL = 320.0
ANA = {"T1": ("GERI3", "SEVIYE"), "B1": ("BOLGE",), "H2": ("MINI",), "S1": ("OLCULU",)}
VARYANTLAR = [f"{a}-{k}" for a, ks in ANA.items() for k in ks]
ANA_PRI = {"T1": 10, "R1": 20, "TF1": 30, "B1": 40, "H2": 50, "S1": 60, "F1": 70}
ANA_EXIT = {"T1": "trail", "R1": "target", "TF1": "trail", "B1": "target", "H2": "trail", "S1": "trail", "F1": "target"}


# ------------------------------------------------------------------------------------------------ yardimcilar
def mk_df(bars, short=False, vol=1.0):
    arr = np.array(bars, float)
    if short:
        arr = np.column_stack([KAL - arr[:, 0], KAL - arr[:, 2], KAL - arr[:, 1], KAL - arr[:, 3]])
    idx = pd.date_range("2026-01-01", periods=len(arr), freq="1h", tz="UTC")
    v = np.full(len(arr), vol) if np.isscalar(vol) else np.asarray(vol, float)
    return pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3], "volume": v}, index=idx)


def mk_inp(df, pair, regime="trend_up", tf="1h", core_edit=None):
    core = M1MOD.empty_output(df.index)
    core["regime"] = regime
    if core_edit is not None:
        core_edit(core)
    return arms.ArmInput(pair=pair, tf=tf, D=df.index[-1].to_pydatetime() + timedelta(hours=1), trig=df, h4=None, params=SignalParams(),
                         core_fn=lambda: core)


def satir(setup, side, stop, hedef=np.nan):
    return pd.Series({"setup": setup, "side": side, "signal": True, "planned_stop": stop, "planned_target": hedef})


def calistir(ad, df, pair, *, ana=None, regime="trend_up", short=False, core_edit=None, tf="1h"):
    """Varyant compute(): son satir. `ana` = ana kol satiri (ana kol hesabi yerine enjekte edilir; karar mantigi ayni)."""
    inp = mk_inp(df, pair, regime=regime, tf=tf, core_edit=core_edit)
    if ana is not None:
        K.ortak(inp)._ana[ad.split("-")[0]] = ana
    return arms.find_arm(ad).compute(inp).iloc[-1]


def sade(df, yon, regime):
    inp = mk_inp(df, f"S{yon}{regime}{len(df)}{float(df['close'].iloc[-1])}/USDT", regime=regime)
    return K.ortak(inp).gorunum(yon)


def uptrend(n=60, bas=100.0, adim=0.5):
    out = []
    for i in range(n):
        c = bas + adim * i
        out.append((c - 0.3, c + 0.4, c - 0.5, c))
    return out


def beklenen_yon(row, short, stop):
    s = -1.0 if short else 1.0
    assert row["setup"] and row["side"] == ("short" if short else "long")
    assert bool(row["signal"]), row["skip_reason"]
    assert row["planned_stop"] == pytest.approx(KAL - stop if short else stop, abs=1e-9)
    assert s * (row["planned_entry"] - row["planned_stop"]) > 0


# ------------------------------------------------------------------------------------------------ kimlik / kesif
def test_kesif_5_varyant_ana_kollar_degismez():
    ls = arms.list_arms()
    for ad in VARYANTLAR:
        m = arms.find_arm(ad)
        aile, kod = ad.split("-")
        assert ad in ls and m.TIMEFRAMES == TFS and m.CORE is False and m.AILE == aile
        assert arms.family_of(ad) == aile
        assert arms.parse_arm_id(f"{ad}@1h") == (ad, "1h")
        sira = m.FORMASYON.sira
        assert arms.priority_of(ad) == ANA_PRI[aile] + sira and 0 < sira < 10      # ana kolun hemen arkasi
        assert arms.priority_of(ad) > arms.priority_of(aile)
        assert arms.exit_mode(ad) == ANA_EXIT[aile] or ad == "S1-OLCULU"
        assert len(m.FEATURES) <= arms.MAX_FEATURES
    assert arms.exit_mode("S1-OLCULU") == "target" and arms.exit_mode("S1") == "trail"
    assert arms.time_stop_of("S1-OLCULU") == 48 and arms.time_stop_of("B1-BOLGE") == 48
    assert len(VARYANTLAR) == 5 and len({a for a in ls if a.split("-")[0] in ANA and "-" in a}) == 5
    for aile in ANA:                                   # ana kollar: kimlik, kip, oncelik AYNI
        m = arms.find_arm(aile)
        assert m.EXIT_MODE == ANA_EXIT[aile] and m.PRIORITY == ANA_PRI[aile]
    assert arms.find_arm("T1").CORE is True and arms.find_arm("R1").CORE is True
    assert arms.find_arm("TF1").FEATURES == TF1M.FEATURES and "rr" not in arms.find_arm("T1-GERI3").FEATURES


def test_varyant_dosyalari_ders_parametresi_okumaz():
    import re
    for d in ("t1v", "b1v", "h2v", "s1v", "_varyant"):
        src = (ROOT / "src" / "trader_engine" / "strategies" / "arms" / f"{d}.py").read_text(encoding="utf-8")
        assert re.search(r"\bparams\.\w", src) is None and "SignalParams" not in src, d


# ------------------------------------------------------------------------------------------------ T1 / H2 (kendi dedektoru)
GERI3 = [(130.0, 131.0, 129.0, 129.5), (129.5, 130.6, 128.6, 129.0), (129.0, 130.2, 128.0, 128.8), (128.8, 131.0, 128.7, 130.8)]
SEVIYE_BARS = ([(100.0, 100.5, 99.5, 100.0)] * 50 + [(100.0, 105.0, 99.5, 100.2)] + [(100.2, 100.8, 99.6, 100.4)] * 2
               + [(100.4, 106.2, 100.3, 106.0), (106.2, 108.0, 106.0, 107.8), (107.8, 109.5, 107.5, 109.0),
                  (106.5, 108.0, 105.2, 107.5)])
MINI = [(130.0, 131.0, 128.5, 129.0), (129.0, 130.5, 127.8, 128.2), (128.2, 130.0, 127.0, 127.5), (127.5, 130.9, 127.4, 130.6)]
BOZAN = (128.8, 129.5, 128.7, 129.0)


def _uc(ad, bars, stop, pair, *, regime_long="trend_up"):
    for short in (False, True):
        df = mk_df(bars, short=short)
        reg = "trend_down" if short else regime_long
        r = calistir(ad, df, f"{pair}{short}/USDT", regime=reg)
        beklenen_yon(r, short, stop)
        assert r["setup"] == ad
        if arms.exit_mode(ad) == "trail":
            assert np.isnan(r["planned_target"])
        # ters rejim: tetiklemez
        r2 = calistir(ad, df, f"{pair}{short}R/USDT", regime="range")
        assert not bool(r2["signal"]) and r2["setup"] is None


def test_t1_geri3():
    taban = uptrend(60)
    _uc("T1-GERI3", taban + GERI3, 128.0, "G3")
    r = calistir("T1-GERI3", mk_df(taban + GERI3[:3] + [BOZAN]), "G3B/USDT")
    assert not bool(r["signal"]) and r["setup"] is None
    # 3. tepe dusmuyor -> yok
    kot = list(GERI3)
    kot[2] = (129.0, 130.8, 128.0, 128.8)
    assert not bool(calistir("T1-GERI3", mk_df(taban + kot), "G3C/USDT")["signal"])


def test_t1_seviye():
    r = calistir("T1-SEVIYE", mk_df(SEVIYE_BARS), "SV1/USDT")
    assert bool(r["signal"]) and r["side"] == "long" and r["setup"] == "T1-SEVIYE"
    assert r["planned_stop"] == pytest.approx(105.2, abs=1e-9)
    assert r["ema_value"] == pytest.approx(105.0)                         # seviye (pivot tepe)
    rs = calistir("T1-SEVIYE", mk_df(SEVIYE_BARS, short=True), "SV1S/USDT", regime="trend_down")
    beklenen_yon(rs, True, 105.2)
    bz = list(SEVIYE_BARS)
    bz[-1] = (107.0, 108.0, 106.5, 107.5)                                  # seviyeye dokunmuyor
    assert not bool(calistir("T1-SEVIYE", mk_df(bz), "SV2/USDT")["signal"])
    bz2 = list(SEVIYE_BARS)
    bz2[-2] = (107.8, 109.5, 104.0, 104.5)                                 # arada seviye altinda kapanis
    assert not bool(calistir("T1-SEVIYE", mk_df(bz2), "SV3/USDT")["signal"])
    assert not bool(calistir("T1-SEVIYE", mk_df(SEVIYE_BARS), "SV4/USDT", regime="range")["signal"])


def test_h2_mini():
    taban = uptrend(60)
    _uc("H2-MINI", taban + MINI, 127.0, "MN")
    # mini cizgiyi kiran ama h[t-1]'i gecmeyen mum: MINI tetikler, T1-GERI3 tetiklemez
    ara = list(MINI)
    ara[-1] = (127.5, 130.0, 127.4, 129.8)
    df = mk_df(taban + ara)
    assert bool(calistir("H2-MINI", df, "MN2/USDT")["signal"])
    assert not bool(calistir("T1-GERI3", df, "MN3/USDT")["signal"])
    bz = list(MINI)
    bz[-1] = (127.5, 130.0, 127.4, 129.0)                                  # c <= cizgi (129.5)
    assert not bool(calistir("H2-MINI", mk_df(taban + bz), "MN4/USDT")["signal"])


# ------------------------------------------------------------------------------------------------ ana kol satiri enjekte edilen varyantlar
@pytest.mark.parametrize("short", [False, True])
def test_s1_olculu(short):
    # kutu: t-8..t-1 hacim 0.5, daha onceki 20 mum hacim 1.0; kirilim hacmi yuksek
    n = 60
    bars = [(100.0 + 0.1 * i, 100.3 + 0.1 * i, 99.7 + 0.1 * i, 100.0 + 0.1 * i) for i in range(n - 9)]
    kutu = [(105.0, 105.4, 104.8, 105.1)] * 8
    son = [(105.2, 106.6, 105.1, 106.4)]
    v = np.concatenate([np.full(n - 9 - 20 + 0, 1.0)[:0], np.full(n - 9, 1.0), np.full(8, 0.5), [3.0]])
    df = mk_df(bars + kutu + son, short=short, vol=v)
    stop_g = 104.6 - 0.2 * 0.3
    ana = lambda: satir("S1", "short" if short else "long", KAL - stop_g if short else stop_g)
    # olculu: hedef = kutu dibi + direk (c[t-9] - c[t-19])
    ro = calistir("S1-OLCULU", df, f"SO{short}/USDT", ana=ana())
    c9 = 100.0 + 0.1 * (n - 10)
    direk = 0.1 * 10
    hedef = 104.8 + direk
    assert bool(ro["signal"]) is (hedef > 106.4)
    kutu2 = [(105.0, 105.4, 104.8, 105.1)] * 8
    bars2 = [(90.0 + 1.0 * i, 90.3 + 1.0 * i, 89.7 + 1.0 * i, 90.0 + 1.0 * i) for i in range(n - 9)]    # buyuk direk
    d2 = mk_df(bars2 + kutu2 + son, short=short, vol=v)
    ro2 = calistir("S1-OLCULU", d2, f"SO2{short}/USDT", ana=ana())
    direk2 = bars2[-1 - 0][3] - bars2[-1 - S1M.POLE_P][3] if False else (bars2[-1][3] - bars2[-1 - S1M.POLE_P][3])
    hedef2 = 104.8 + direk2
    assert hedef2 > 106.4 and bool(ro2["signal"])
    assert ro2["planned_target"] == pytest.approx(KAL - hedef2 if short else hedef2, abs=1e-9)
    assert arms.exit_mode("S1-OLCULU") == "target" and c9 > 0


# ------------------------------------------------------------------------------------------------ B1-BOLGE
def _b1_taban():
    out = []
    for i in range(72):
        yuksek = (i % 8) in (2, 3)
        c = 99.9 if yuksek else 99.0
        out.append((c - 0.2, 100.5 if (i % 8) in (2, 3) else c + 0.4, c - 0.5, c))
    return out


B1_KIRILIM = (100.6, 102.6, 100.5, 102.5)
B1_RETEST = [(102.5, 102.8, 101.8, 102.0), (102.0, 102.2, 101.5, 101.8), (99.8, 101.0, 98.8, 100.3)]


@pytest.mark.parametrize("short", [False, True])
def test_b1_bolge(short):
    bars = _b1_taban() + [B1_KIRILIM] + B1_RETEST
    df = mk_df(bars, short=short)
    ad = "B1-BOLGE"
    kenar = lambda core: None
    r = calistir(ad, df, f"BB{short}/USDT", regime="range", core_edit=kenar)
    assert bool(r["signal"]) and r["side"] == ("short" if short else "long"), r["skip_reason"]
    assert r["planned_stop"] == pytest.approx(KAL - 98.8 if short else 98.8, abs=1e-9)
    assert r["ema_value"] == pytest.approx(KAL - 100.5 if short else 100.5, abs=1e-9)        # seviye L
    # B1 ana kolu bu retesti ALMAZ (kapanis seviyenin altina indi)
    inp = mk_inp(df, f"BBa{short}/USDT", regime="range")
    assert not bool(B1M.compute(inp)["signal"].iloc[-1])
    # bolge dibinin altinda kapanis -> yok
    kot = list(B1_RETEST)
    kot[1] = (101.5, 101.8, 98.0, 98.5)
    assert not bool(calistir(ad, mk_df(_b1_taban() + [B1_KIRILIM] + kot, short=short), f"BBb{short}/USDT", regime="range")["signal"])
    # t mumu kirmizi -> yok
    kot2 = list(B1_RETEST)
    kot2[2] = (100.6, 101.0, 99.7, 100.2)
    assert not bool(calistir(ad, mk_df(_b1_taban() + [B1_KIRILIM] + kot2, short=short), f"BBc{short}/USDT", regime="range")["signal"])
    # ilk gecerli retest daha once oldu (t tekrar degil): tek sinyal
    iki = B1_RETEST + [(100.3, 101.2, 100.0, 100.9)]
    assert not bool(calistir(ad, mk_df(_b1_taban() + [B1_KIRILIM] + iki, short=short), f"BBd{short}/USDT", regime="range")["signal"])
    # 11. mumdan sonra retest yok
    uzun = [(102.5, 102.8, 101.8, 102.0)] * 10 + [B1_RETEST[2]]
    assert not bool(calistir(ad, mk_df(_b1_taban() + [B1_KIRILIM] + uzun, short=short), f"BBe{short}/USDT", regime="range")["signal"])


# ------------------------------------------------------------------------------------------------ ileriye bakis / pencere
class SahteHam:
    def __init__(self, rejim):
        self.rejim, self.oz = rejim, {}

    def rejim_t(self):
        return self.rejim

    def ana_satir(self, modul, yon):
        return None


def _g(o, h, l, c, yon, t, rejim):
    atr = I.atr(pd.DataFrame({"high": h[:t + 1], "low": l[:t + 1], "close": c[:t + 1]}), 14).to_numpy(dtype=float)
    ham = SahteHam(rejim)
    if yon == "long":
        return K.Gorunum(o, h, l, c, atr, t, np.ones(len(c)), "long", ham)
    return K.Gorunum(-o, -l, -h, -c, atr, t, np.ones(len(c)), "short", ham)


def _rw(n, seed, vol=0.012):
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    o = np.concatenate(([100.0], c[:-1])) * np.exp(rng.normal(0, vol / 3, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    return o, h, l, c, 1.0 + rng.random(n) * 2.0


@pytest.mark.parametrize("fn", [t1v.geri3, t1v.seviye, h2v.mini])
def test_dedektor_gelecegi_okumaz(fn):
    n = 3000
    o, h, l, c, v = _rw(n, 21, 0.012)
    rng = np.random.default_rng(5)
    say = 0
    for yon, rejim in (("long", "trend_up"), ("short", "trend_down")):
        for t in range(120, 2600, 7):
            tam = fn(_g(o, h, l, c, yon, t, rejim))
            o2, h2, l2, c2 = (x.copy() for x in (o, h, l, c))
            for x in (o2, h2, l2, c2):
                x[t + 1:] = x[t + 1:] * rng.uniform(0.5, 1.5, n - t - 1)       # gelecek bozuldu
            ayni = fn(_g(o2, h2, l2, c2, yon, t, rejim))
            kes = fn(_g(o[:t + 1], h[:t + 1], l[:t + 1], c[:t + 1], yon, t, rejim))   # gelecek hic yok
            assert (tam is None) == (ayni is None) == (kes is None), (fn.__name__, yon, t)
            if tam is not None:
                say += 1
                assert tam["stop"] == pytest.approx(ayni["stop"], abs=1e-9) == pytest.approx(kes["stop"], abs=1e-9)
    assert say > 5, (fn.__name__, say)


def _rejim_core(df):
    gun = (df.index.day_of_year // 3) % 3
    return np.where(gun == 0, "trend_up", np.where(gun == 1, "trend_down", "range")).astype(object)


def _rastgele_inp(o, h, l, c, v, idx, pair):
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v}, index=idx)
    core = M1MOD.empty_output(df.index)
    core["regime"] = _rejim_core(df)
    return arms.ArmInput(pair=pair, tf="1h", D=df.index[-1].to_pydatetime() + timedelta(hours=1), trig=df, h4=None, params=SignalParams(),
                         core_fn=lambda: core)


def test_tum_varyantlar_pencere_bagimsiz_ve_aday_uretir():
    """Her mumda ana kol (gercek hesap) + varyant: 500 mumluk pencere = tum gecmis (t sabit); aday sayisi > 0."""
    n = 1400
    o, h, l, c, v = _rw(n, 33, 0.012)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    adaylar: dict[str, int] = {}
    for k, t in enumerate(range(700, n, 21)):
        tam = _rastgele_inp(o[:t + 1], h[:t + 1], l[:t + 1], c[:t + 1], v[:t + 1], idx[:t + 1], f"W{k}/USDT")
        pen = _rastgele_inp(o[t - 499:t + 1], h[t - 499:t + 1], l[t - 499:t + 1], c[t - 499:t + 1], v[t - 499:t + 1],
                            idx[t - 499:t + 1], f"P{k}/USDT")
        for ad in VARYANTLAR:
            m = arms.find_arm(ad)
            a, b = m.compute(tam).iloc[-1], m.compute(pen).iloc[-1]
            assert bool(a["signal"]) == bool(b["signal"]) and a["side"] == b["side"], (ad, t)
            if bool(a["signal"]):
                adaylar[ad] = adaylar.get(ad, 0) + 1
                assert a["planned_stop"] == pytest.approx(b["planned_stop"], rel=1e-6)
                assert a["planned_entry"] == pytest.approx(float(c[t]) if a["side"] == "long" else float(c[t]))
    assert adaylar.get("T1-GERI3", 0) > 0 and sum(adaylar.values()) >= 3, adaylar


# ------------------------------------------------------------------------------------------------ kapasite / yapilandirma
def _cfg(ad):
    return json.loads((ROOT / "config" / ad).read_text(encoding="utf-8"))


def test_kagit_canli_ayni_ve_15_kol():
    p, l = _cfg("engine.paper.json"), _cfg("engine.live.json")
    for k in ("arms", "exit_modes"):
        assert p[k] == l[k], k
    from evren_destek import config_kollari
    beklenen = config_kollari(f"{s}@{tf}" for s in VARYANTLAR for tf in TFS)       # 26.11: 9 varyant kaldirildi, 15m yok: 5 x 3
    assert all(a in p["arms"] for a in beklenen) and len(beklenen) == 15 and len(set(p["arms"])) == len(p["arms"])
    for ad in ("engine.paper.json", "engine.live.json"):
        cfg = C.load_cli_config(ROOT / "config", "learner", ad.split(".")[1])
        assert all(a in cfg.arms for a in beklenen)
        assert "H2-YARI" not in cfg.exit_modes


def test_telegram_adlari_varyant():
    from trader_core import tg_sade
    from evren_destek import KALDIRILAN_KURULUM
    for ad in VARYANTLAR:
        assert ad not in KALDIRILAN_KURULUM
        assert tg_sade.kurulum_adi(f"{ad}@1h") != ad, ad
    assert "Sıkışma kırılımı" in tg_sade.kol_adi("S1-OLCULU@1h")


# ---------------------------------------------------------------- Paket 2 / D3 (sahip karari #13): iz suren kurulumda zaman stopu YOK
def _trail_kurulumlari():
    return {s: m for s, m in arms.discover().items() if getattr(m, "EXIT_MODE", None) == "trail" and getattr(m, "FORMASYON", None) is not None}


def test_trail_kipli_sanal_kurulumlarda_time_stop_none_ve_time_stop_of_48():
    tr = _trail_kurulumlari()
    assert tr
    for setup, m in tr.items():
        assert m.TIME_STOP is None and m.FORMASYON.zaman_stopu is None, setup
        assert arms.time_stop_of(setup, "1h") == 48                           # None -> 48 (yalniz target kolu/scan sutunu okur)


def test_trail_kipli_pozisyon_100_kapanmis_mumda_time_stop_ile_cikmaz():
    from types import SimpleNamespace
    from trader_engine import position_manager as PM
    setup = next(iter(_trail_kurulumlari()))
    pos = SimpleNamespace(setup=setup, side="long", initial_stop=98.0, entry_bar_open=object(), entry_price=100.0, trail_atr=3.0,
                          current_stop=98.0, planned_target=None, trigger_tf="1h")
    n = 100
    ctx = PM.ExitContext(bar_close_ts=None, highs=np.full(n, 100.4), lows=np.full(n, 99.6), atrs=np.full(n, 1.0),
                         regime_last="trend_up", last_close=100.0, n_closed=n, rule_exit=False)
    d = PM.evaluate_exit(pos, ctx)
    assert d.reason != "time_stop"


def test_trail_kipi_ile_zaman_stopu_tanimi_arm_error():
    from types import SimpleNamespace
    from trader_engine.strategies.arms import _kutuphane as KK
    f = KK.Formasyon("X", "x", 1, ("1h",), 48, lambda g: None, kip="trail")
    mod = SimpleNamespace(SETUP="ZZ", FORMASYONLAR={"X": f}, PRIORITY=900)
    with pytest.raises(arms.ArmError):
        KK.sanal_kurulumlar(mod)
    ok = KK.Formasyon("X", "x", 1, ("1h",), None, lambda g: None, kip="trail")
    assert KK.sanal_kurulumlar(SimpleNamespace(SETUP="ZZ", FORMASYONLAR={"X": ok}, PRIORITY=900))["ZZ-X"].TIME_STOP is None
