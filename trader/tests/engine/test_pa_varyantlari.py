"""24.11 kullanici karari: PA varyantlari (14 varyant x 4 ZD = 56 kol; ana kol davranisi degismez).
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
from trader_engine.strategies.arms import _varyant as V
from trader_engine.strategies.arms import b1 as B1M
from trader_engine.strategies.arms import b1v, f1v, h2v, r1v, s1v, t1v, tf1v
from trader_engine.strategies.arms import f1 as F1M
from trader_engine.strategies.arms import h2 as H2M
import bos_cekirdek as M1MOD
from trader_engine.strategies.arms import r1 as R1M
from trader_engine.strategies.arms import s1 as S1M
from trader_engine.strategies.arms import tf1 as TF1M

ROOT = Path(__file__).resolve().parents[2]
TFS = ("15m", "1h", "4h", "1d")
KAL = 320.0
ANA = {"T1": ("GERI3", "SEVIYE"), "R1": ("HA", "ALT", "ERKEN"), "TF1": ("HACIM", "FITIL"), "B1": ("MUM", "BOLGE"),
       "H2": ("MINI", "YARI"), "S1": ("HACIM", "OLCULU"), "F1": ("IKINCI",)}
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
def test_kesif_14_varyant_ana_kollar_degismez():
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
    assert arms.time_stop_of("R1-ERKEN") == 24 and arms.time_stop_of("R1") == 48 and arms.time_stop_of("R1-HA") == 48
    assert len(VARYANTLAR) == 14 and len({a for a in ls if a.split("-")[0] in ANA and "-" in a}) == 14
    for aile in ANA:                                   # ana kollar: kimlik, kip, oncelik AYNI
        m = arms.find_arm(aile)
        assert m.EXIT_MODE == ANA_EXIT[aile] and m.PRIORITY == ANA_PRI[aile]
    assert arms.find_arm("T1").CORE is True and arms.find_arm("R1").CORE is True
    assert arms.find_arm("TF1").FEATURES == TF1M.FEATURES and "rr" not in arms.find_arm("TF1-HACIM").FEATURES


def test_varyant_dosyalari_ders_parametresi_okumaz():
    import re
    for d in ("t1v", "r1v", "tf1v", "b1v", "h2v", "s1v", "f1v", "_varyant"):
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
def _kirilim_df(vol_son, vol_oncesi=1.0, ust_fitil=0.0, short=False):
    bars = [(100.0, 100.3, 99.7, 100.0)] * 60 + [(100.1, 101.3 + ust_fitil, 100.0, 101.2)]
    v = np.full(len(bars), vol_oncesi)
    v[-1] = vol_son
    return mk_df(bars, short=short, vol=v)


@pytest.mark.parametrize("short", [False, True])
def test_tf1_hacim_ve_fitil(short):
    stop_g = 99.4
    ana = lambda: satir("TF1", "short" if short else "long", KAL - stop_g if short else stop_g)
    yon = "short" if short else "long"
    r = calistir("TF1-HACIM", _kirilim_df(1.6, short=short), f"H{short}/USDT", ana=ana())
    beklenen_yon(r, short, stop_g)
    assert np.isnan(r["planned_target"]) and arms.exit_mode("TF1-HACIM") == "trail"
    assert not bool(calistir("TF1-HACIM", _kirilim_df(1.4, short=short), f"H{short}B/USDT", ana=ana())["signal"])   # hacim yetmiyor
    assert calistir("TF1-HACIM", _kirilim_df(1.6, short=short), f"H{short}C/USDT", ana=None)["setup"] is None        # ana kol yok
    ters = satir("TF1", "short", stop_g)
    if not short:                                                          # ana kol short der, seri long kirilimi: long adayi yok
        assert not bool(calistir("TF1-HACIM", _kirilim_df(1.6), f"H{short}D/USDT", ana=ters)["signal"])               # ters yon
    rf = calistir("TF1-FITIL", _kirilim_df(1.0, short=short), f"F{short}/USDT", ana=ana())
    beklenen_yon(rf, short, stop_g)
    assert not bool(calistir("TF1-FITIL", _kirilim_df(1.0, ust_fitil=1.0, short=short), f"F{short}B/USDT", ana=ana())["signal"])
    assert yon in ("long", "short")


@pytest.mark.parametrize("short", [False, True])
def test_b1_mum(short):
    taban = [(100.0, 100.4, 99.6, 100.0)] * 50
    pin = [(100.2, 100.5, 98.0, 100.4)]                                     # alt golge uzun, ust golge yok, kapanis ustte
    yut = [(101.0, 101.1, 99.9, 100.0), (99.9, 101.6, 99.8, 101.5)]
    doji = [(100.0, 100.4, 99.6, 100.05)]
    stop = 97.5
    ana = lambda: satir("B1", "short" if short else "long", KAL - stop if short else stop, KAL - 105.0 if short else 105.0)
    for i, bars in enumerate((pin, yut)):
        r = calistir("B1-MUM", mk_df(taban + bars, short=short), f"BM{i}{short}/USDT", ana=ana())
        beklenen_yon(r, short, stop)
        assert r["planned_target"] == pytest.approx(KAL - 105.0 if short else 105.0)
    assert not bool(calistir("B1-MUM", mk_df(taban + doji, short=short), f"BM9{short}/USDT", ana=ana())["signal"])


@pytest.mark.parametrize("short", [False, True])
def test_s1_hacim_ve_olculu(short):
    # kutu: t-8..t-1 hacim 0.5, daha onceki 20 mum hacim 1.0; kirilim hacmi yuksek
    n = 60
    bars = [(100.0 + 0.1 * i, 100.3 + 0.1 * i, 99.7 + 0.1 * i, 100.0 + 0.1 * i) for i in range(n - 9)]
    kutu = [(105.0, 105.4, 104.8, 105.1)] * 8
    son = [(105.2, 106.6, 105.1, 106.4)]
    v = np.concatenate([np.full(n - 9 - 20 + 0, 1.0)[:0], np.full(n - 9, 1.0), np.full(8, 0.5), [3.0]])
    df = mk_df(bars + kutu + son, short=short, vol=v)
    stop_g = 104.6 - 0.2 * 0.3
    ana = lambda: satir("S1", "short" if short else "long", KAL - stop_g if short else stop_g)
    r = calistir("S1-HACIM", df, f"SH{short}/USDT", ana=ana())
    beklenen_yon(r, short, stop_g)
    assert np.isnan(r["planned_target"])
    v2 = v.copy()
    v2[-9:-1] = 1.2                                                         # kutuda hacim dusuk degil
    assert not bool(calistir("S1-HACIM", mk_df(bars + kutu + son, short=short, vol=v2), f"SH{short}B/USDT", ana=ana())["signal"])
    v3 = v.copy()
    v3[-1] = 0.6                                                            # kirilimda hacim yuksek degil
    assert not bool(calistir("S1-HACIM", mk_df(bars + kutu + son, short=short, vol=v3), f"SH{short}C/USDT", ana=ana())["signal"])
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


@pytest.mark.parametrize("short", [False, True])
def test_h2_yari_ayni_giris_ve_exit_modes(short):
    stop_g = 127.0
    ana = satir("H2", "short" if short else "long", KAL - stop_g if short else stop_g)
    r = calistir("H2-YARI", mk_df(uptrend(60) + MINI, short=short), f"Y{short}/USDT", ana=ana)
    beklenen_yon(r, short, stop_g)
    assert np.isnan(r["planned_target"]) and arms.exit_mode("H2-YARI") == "trail"
    cfg = json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))["exit_modes"]
    assert "H2-YARI" not in cfg and cfg["default"]["partial"] is True      # 26.11 sahip karari: H2-YARI config'ten kaldirildi (modul yerinde)


# ------------------------------------------------------------------------------------------------ R1 varyantlari (gercek R1 yolu)
def _r1_core(stop, hedef, rh, rl, side="long"):
    def duzenle(core):
        ix = core.index[-1]
        for k, v in (("setup", "R1"), ("side", side), ("signal", True), ("planned_stop", stop), ("planned_target", hedef),
                     ("rh", rh), ("rl", rl), ("rr", 2.0)):
            core.at[ix, k] = v
    return duzenle


R1_DUS = [(200.0 - i + 1.0, 200.0 - i + 1.4, 200.0 - i - 0.4, 200.0 - i) for i in range(40)]


@pytest.mark.parametrize("short", [False, True])
def test_r1_ha_alt_erken(short):
    son = [(161.0, 165.2, 160.9, 165.0)]                                   # sert yukari mum: HA kirmizidan yesile
    stop, hedef = 160.5, 175.0
    kenar = lambda rl, rh: _r1_core(KAL - stop if short else stop, KAL - hedef if short else hedef,
                                    KAL - rl if short else rh, KAL - rh if short else rl, "short" if short else "long")
    # HA: long uzayinda donus
    df = mk_df(R1_DUS + son, short=short)
    r = calistir("R1-HA", df, f"R{short}/USDT", core_edit=kenar(160.0, 185.0))
    beklenen_yon(r, short, stop)
    assert r["planned_target"] == pytest.approx(KAL - hedef if short else hedef)
    devam = mk_df(R1_DUS + [(161.0, 161.1, 159.0, 159.2)], short=short)       # dusus devam: HA donusu yok
    assert not bool(calistir("R1-HA", devam, f"R{short}B/USDT", core_edit=kenar(150.0, 185.0))["signal"])
    # ALT: kapanis 165 bandin alt ucte birinde mi
    ra = calistir("R1-ALT", df, f"RA{short}/USDT", core_edit=kenar(160.0, 190.0))          # (165-160)/30 = 0.17
    beklenen_yon(ra, short, stop)
    assert not bool(calistir("R1-ALT", df, f"RA{short}B/USDT", core_edit=kenar(160.0, 170.0))["signal"])   # 0.5
    # ERKEN: ayni giris, zaman stopu 24
    re_ = calistir("R1-ERKEN", df, f"RE{short}/USDT", core_edit=kenar(160.0, 190.0))
    beklenen_yon(re_, short, stop)
    assert arms.time_stop_of("R1-ERKEN") == 24
    # ana kol R1 satiri yoksa varyant da yok
    assert calistir("R1-ERKEN", df, f"RE{short}C/USDT")["setup"] is None
    # ana kolun cikti tablosu varyant tarafindan DEGISMEZ
    inp = mk_inp(df, f"RZ{short}/USDT", core_edit=kenar(160.0, 190.0))
    once = R1M.compute(inp).copy()
    arms.find_arm("R1-HA").compute(inp)
    pd.testing.assert_frame_equal(once, R1M.compute(inp))


# ------------------------------------------------------------------------------------------------ B1-BOLGE ve F1-IKINCI
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


def _f1_sahte(t, ikinci_seviye, ilk_var=True, level=100.0, off=0.0):
    level, ikinci_seviye = level + off, ikinci_seviye + off
    raw = np.zeros(t + 1, dtype=bool)
    info = {}
    raw[t] = True
    info[t] = dict(level=level, lsw=level - 0.5, rej=0.8, depth=0.5, age=10, atr=1.0, close=0.0, body=0.6, regime="range")
    if ilk_var:
        raw[t - 8] = True
        info[t - 8] = dict(level=ikinci_seviye, lsw=ikinci_seviye - 0.6, rej=0.8, depth=0.5, age=10, atr=1.0, close=0.0, body=0.6,
                           regime="range")
    return raw, info


@pytest.mark.parametrize("short", [False, True])
def test_f1_ikinci(short, monkeypatch):
    bars = [(100.0, 100.6, 99.4, 100.0)] * 70 + [(99.6, 101.2, 99.4, 101.0)]
    df = mk_df(bars, short=short)
    t = len(bars) - 1
    off = -KAL if short else 0.0                                            # g-uzayi (short: long - KAL)
    for seviye, beklenen in ((100.2, True), (99.4, True), (97.0, False)):
        monkeypatch.setattr(F1M, "_raw", lambda p, side, tf, s=seviye: _f1_sahte(t, s, off=off) if side == ("short" if short else "long") else
                            (np.zeros(t + 1, dtype=bool), {}))
        r = calistir("F1-IKINCI", df, f"FI{short}{seviye}/USDT", regime="range")
        assert bool(r["signal"]) is beklenen, (seviye, r["skip_reason"])
        if beklenen:
            beklenen_yon(r, short, 99.5 - 0.2 * 1.0)
    # ilk supurme yok -> yok
    monkeypatch.setattr(F1M, "_raw", lambda p, side, tf: _f1_sahte(t, 100.0, ilk_var=False, off=off) if side == ("short" if short else "long") else
                        (np.zeros(t + 1, dtype=bool), {}))
    assert not bool(calistir("F1-IKINCI", df, f"FI{short}Z/USDT", regime="range")["signal"])
    # ilk supurme t-1'de (ayni olay) sayilmaz
    def yakin(p, side, tf):
        raw, info = _f1_sahte(t, 100.0, ilk_var=False, off=off)
        raw[t - 1] = True
        info[t - 1] = dict(info[t])
        return (raw, info) if side == ("short" if short else "long") else (np.zeros(t + 1, dtype=bool), {})
    monkeypatch.setattr(F1M, "_raw", yakin)
    assert not bool(calistir("F1-IKINCI", df, f"FI{short}Y/USDT", regime="range")["signal"])


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


def test_yardimcilar_gelecegi_okumaz_ve_pencere_bagimsiz():
    n = 2000
    o, h, l, c, v = _rw(n, 8, 0.01)
    rng = np.random.default_rng(9)
    for t in range(100, 1800, 11):
        g1 = _g(o, h, l, c, "long", t, "trend_up")
        o2, h2, l2, c2 = (x.copy() for x in (o, h, l, c))
        for x in (o2, h2, l2, c2):
            x[t + 1:] *= rng.uniform(0.5, 1.5, n - t - 1)
        g2 = _g(o2, h2, l2, c2, "long", t, "trend_up")
        assert V.ha_donus(g1) == V.ha_donus(g2) and V.pin_geometri(g1) == V.pin_geometri(g2)
        assert V.yutan_geometri(g1) == V.yutan_geometri(g2)
        assert V.hacim_oran(g1) == V.hacim_oran(g2)
        # HA son 30 mumdan: daha onceki mumlar degisse de ayni
        o3, h3, l3, c3 = (x.copy() for x in (o, h, l, c))
        for x in (o3, h3, l3, c3):
            x[:t - V.HA_PENCERE + 1] *= 1.7
        assert V.ha_donus(_g(o3, h3, l3, c3, "long", t, "trend_up")) == V.ha_donus(g1)


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
        if ad in KALDIRILAN_KURULUM:                         # 26.11: kurulum kaldirildi, etiketi de yok
            continue
        assert tg_sade.kurulum_adi(f"{ad}@1h") != ad, ad
    assert "Sıkışma kırılımı" in tg_sade.kol_adi("S1-OLCULU@1h")
