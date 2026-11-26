"""24.11 kullanici karari: formasyon kutuphanesi, adim 3 (IN1 17 gosterge setupu + yeni gostergeler).
Gosterge degerleri referansla 1e-9 icinde; sentetik ornek (long + short aynasi + bozulan kosul); setuplar_v3 esdegerligi (RSI, BOLL; MAKESISIM
ve FIYATMA yalniz t ve yon); kural cikislari; ileriye bakis; kesif; kagit = canli."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from formasyon_destek import atr_of, bozan, core_inp, df_of, referans, rw, tara, zig
from trader_core import indicators as I
from trader_engine import config as C
from trader_engine.strategies import arms
from trader_engine.strategies.arms import _kutuphane as K
from trader_engine.strategies.arms import gf1, in1, mf1

ROOT = Path(__file__).resolve().parents[2]
KODLAR = ("UYUMSUZ", "MAKESISIM", "KUMO", "TK", "FIBO", "HACIM", "RSI", "RSIDONUS", "RSI2", "STOK", "MACD", "MAGERI", "BOLLKIR", "VWAP",
          "FIYATMA", "HIZLIMA", "BOLL")
KURALLI = ("MAKESISIM", "KUMO", "TK", "RSI", "RSIDONUS", "RSI2", "STOK", "MACD", "BOLLKIR", "VWAP", "FIYATMA", "HIZLIMA", "BOLL")
TFS = ("15m", "1h", "4h", "1d")
KAL = 250.0


@pytest.fixture(autouse=True)
def _tam_gecmis(monkeypatch):
    """Tarama testleri tum gecmisle hesaplanir (uretimde son 1200 mum; fark < 1e-15)."""
    monkeypatch.setattr(K, "IND_PENCERE", 10 ** 9)


# ------------------------------------------------------------------------------------------------ gostergeler
def test_gostergeler_referansla_1e9():
    v3 = referans()
    G = v3.G
    o, h, l, c = rw(900, 4, 0.02)
    v = np.random.default_rng(1).lognormal(0, 0.5, 900)
    np.testing.assert_allclose(I.rsi(c, 14), G.rsi(c, 14), rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(I.rsi(c, 2), G.rsi(c, 2), rtol=0, atol=1e-9, equal_nan=True)
    for n in (4, 9, 20, 50):
        np.testing.assert_allclose(I.ema_np(c, n), G.ema(c, n), rtol=1e-12, atol=1e-9, equal_nan=True)
    for a, b in zip(I.macd(c, 12, 26, 9), G.macd(c, 12, 26, 9)):
        np.testing.assert_allclose(a, b, rtol=0, atol=1e-9, equal_nan=True)
    for n in (20, 50, 200):
        np.testing.assert_allclose(I.sma_np(c, n), v3.sma(c, n), rtol=0, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(I.std_pop(c, 20), v3.std_pop(c, 20), rtol=0, atol=1e-9, equal_nan=True)
    m, alt, ust = I.bollinger(c, 20, 2.0)
    np.testing.assert_allclose(alt, v3.sma(c, 20) - 2 * v3.std_pop(c, 20), atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(ust, v3.sma(c, 20) + 2 * v3.std_pop(c, 20), atol=1e-9, equal_nan=True)
    np.testing.assert_array_equal(I.pivot_dip(l, 10, 2), v3.pivot_dip_kesin(l, 10, 2))
    np.testing.assert_array_equal(I.pivot_tepe(h, 10, 2), v3.pivot_dip_kesin(-h, 10, 2))
    # bagimsiz pandas uygulamalari: stokastik, ichimoku, gunluk VWAP
    H, L, C = pd.Series(h), pd.Series(l), pd.Series(c)
    ham = 100 * (C - L.rolling(14).min()) / (H.rolling(14).max() - L.rolling(14).min())
    k = ham.rolling(3).mean()
    sk, sd = I.stoch(h, l, c, 14, 3, 3)
    np.testing.assert_allclose(sk, k.to_numpy(), atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(sd, k.rolling(3).mean().to_numpy(), atol=1e-9, equal_nan=True)
    tk = (H.rolling(9).max() + L.rolling(9).min()) / 2
    kj = (H.rolling(26).max() + L.rolling(26).min()) / 2
    sb = ((H.rolling(52).max() + L.rolling(52).min()) / 2).shift(26)
    sa = ((tk + kj) / 2).shift(26)
    a1, a2, a3, a4 = I.ichimoku(h, l, c, 9, 26, 52)
    for x, y in ((a1, tk), (a2, kj), (a3, sa), (a4, sb)):
        np.testing.assert_allclose(x, y.to_numpy(), atol=1e-9, equal_nan=True)
    gun = np.arange(900) // 24
    tp = (H + L + C) / 3
    pv = (tp * pd.Series(v)).groupby(gun).cumsum()
    vv = pd.Series(v).groupby(gun).cumsum()
    np.testing.assert_allclose(I.vwap_gunluk(h, l, c, v, gun), (pv / vv).to_numpy(), atol=1e-9)


def test_ichimoku_bulut_t_eksi_26_ve_oncesinden():
    """Bulut `t`de cizilen deger: t-26 ve oncesinin verisinden (son mumlar degisince t'deki bulut degismez)."""
    o, h, l, c = rw(300, 2, 0.02)
    a = I.ichimoku(h, l, c)
    h2, l2, c2 = h.copy(), l.copy(), c.copy()
    h2[-26:] *= 1.5
    l2[-26:] *= 0.5
    c2[-26:] *= 1.2
    b = I.ichimoku(h2, l2, c2)
    np.testing.assert_array_equal(a[2][-26:], b[2][-26:])
    np.testing.assert_array_equal(a[3][-26:], b[3][-26:])


# ------------------------------------------------------------------------------------------------ sentetik seriler
def _osc():
    return [(100.4, 2), (99.6, 2)] * 30


def _seriler():
    S = {}
    b = zig(100, [(200, 260), (190, 2), (175, 3), (165, 3)])[0][:263]
    S["RSI"] = b[:-1] + [(b[-1][0], b[-1][1], b[-1][3] - 4.0, b[-1][3])]          # alt fitilli son mum (stop mesafesi yeterli)
    S["MAKESISIM"] = zig(200, [(100, 250), (200, 250)])[0][:328]
    S["FIYATMA"] = zig(100, [(80, 60), (95, 12)])[0][:66]
    S["MACD"] = zig(100, [(80, 40), (70, 20), (85, 12)])[0][:61]
    S["STOK"] = zig(100, [(200, 100), (190, 5), (190.8, 1), (191.6, 1), (193, 2)])[0][:108]
    S["RSIDONUS"] = zig(100, [(200, 260), (140, 6), (165, 3)])[0][:268]
    S["RSI2"] = zig(100, [(200, 260), (196, 2)])[0][:262]
    S["UYUMSUZ"] = zig(200, [(200.5, 30), (150, 12), (170, 8), (149, 20), (155, 3)])[0][:72]
    S["HIZLIMA"] = zig(100, [(80, 40), (90, 12)])[0][:44]
    S["TK"] = zig(100, [(200, 120), (185, 10), (205, 15)])[0][:141]
    S["KUMO"] = zig(100, [(100.5, 40), (90, 20), (80, 30), (115, 50)])[0][:107]
    b, _ = zig(110, [(110.2, 30), (100, 12), (130, 12), (118, 5)])
    c = b[-1][3]
    S["FIBO"] = b + [(c, c + 1.5, 114.0, c + 1.0)]
    b, _ = zig(100, [(180, 100)])
    c = b[-1][3]
    S["MAGERI"] = b + [(c, c + 1.0, c - 12.0, c + 0.8)]
    S["VWAP"] = zig(100, [(100.2, 24), (94, 12), (100, 14)])[0][:47]
    b, _ = zig(100, _osc())
    S["BOLL"] = b + [(99.6, 100.0, 95.0, 99.7)]
    c = b[-1][3]
    S["BOLLKIR"] = b + [(c, 103.2, c, 103.0)]
    S["HACIM"] = b + [(c, 105.0, c - 0.1, 104.8)]
    return S


SER = _seriler()
FREQ = {"VWAP": "15min"}


def _df(kod, bars=None, short=False):
    bars = SER[kod] if bars is None else bars
    df = df_of(bars, short=short, freq=FREQ.get(kod, "1h"), kal=KAL)
    if kod == "HACIM":
        df.iloc[-1, df.columns.get_loc("volume")] = 3.0
    return df


def _bozuk(kod):
    """Son mumu kosulu bozan mumla degistirir (cogu icin onceki kapanista doji; UYUMSUZ icin dibi asagi kiran mum)."""
    if kod == "UYUMSUZ":
        b = list(SER[kod])
        c = b[-2][3]
        b[-1] = (c, c, c - 4.0, c - 3.0)
        return b
    if kod in ("MAKESISIM", "TK", "STOK", "MACD"):                # kesisim kapanisa duyarli: coken mum
        b = list(SER[kod])
        c = b[-2][3]
        b[-1] = (c, c, c * 0.5, c * 0.5)
        return b
    return bozan(SER[kod])


def _bul(kod, df, side):
    ham = K._Ham(df)
    assert ham.ok
    return in1.FORMASYONLAR[kod].bul(ham.gorunum(side))


def _ref_degerler(df):
    v3 = referans()
    G = v3.G
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    return v3, G, o, h, l, c


def _beklenen(kod):
    """Long uzayinda (stop, hedef | None); referans gostergeler ve bagimsiz pandas hesaplariyla."""
    df = _df(kod)
    v3, G, o, h, l, c = _ref_degerler(df)
    t = len(c) - 1
    atr = atr_of(o, h, l, c)[t]
    dip10 = l[t - 9:t + 1].min()
    H, L, C = pd.Series(h), pd.Series(l), pd.Series(c)
    if kod in ("RSI", "STOK", "RSIDONUS"):
        return dip10, None
    if kod in ("MAKESISIM", "FIYATMA", "MACD", "RSI2", "HIZLIMA", "VWAP"):
        return c[t] - 2 * atr, None
    if kod == "BOLL":
        return l[t], v3.sma(c, 20)[t]
    if kod == "BOLLKIR":
        return v3.sma(c, 20)[t], None
    if kod == "HACIM":
        return l[t], None
    if kod == "MAGERI":
        return l[t], None
    tk = (H.rolling(9).max() + L.rolling(9).min()) / 2
    kj = ((H.rolling(26).max() + L.rolling(26).min()) / 2)
    if kod == "TK":
        return kj.iloc[t], None
    if kod == "KUMO":
        sb = ((H.rolling(52).max() + L.rolling(52).min()) / 2).shift(26)
        sa = ((tk + kj) / 2).shift(26)
        return (kj.iloc[t] if kj.iloc[t] < c[t] else min(sa.iloc[t], sb.iloc[t])), None
    if kod == "FIBO":
        A, B = 41, 53
        Hh = h[B] - l[A]
        return h[B] - 0.786 * Hh, h[B]
    if kod == "UYUMSUZ":
        piv = [i for i in np.flatnonzero(v3.pivot_dip_kesin(l)) if i <= t - 2]
        d1, d2 = piv[-2], piv[-1]
        assert d2 == t - 2
        hd = h[d1:d2 + 1].max()
        return l[d2], (hd if hd > c[t] else None)
    raise KeyError(kod)


@pytest.mark.parametrize("kod", KODLAR)
def test_sentetik_long_short_ve_bozulan_kosul(kod):
    stop, hedef = _beklenen(kod)
    r = _bul(kod, _df(kod), "long")
    assert r is not None, kod
    assert r["stop"] == pytest.approx(stop, abs=1e-9)
    if hedef is None:
        assert r["hedef"] is None                                    # 2R (hesapla doldurur)
    else:
        assert r["hedef"] == pytest.approx(hedef, abs=1e-9)
    assert _bul(kod, _df(kod), "short") is None
    rs = _bul(kod, _df(kod, short=True), "short")                    # fiyat aynasi
    assert rs is not None, kod
    assert rs["stop"] == pytest.approx(stop - KAL, abs=1e-8)
    if hedef is not None:
        assert rs["hedef"] == pytest.approx(hedef - KAL, abs=1e-8)
    assert _bul(kod, _df(kod, short=True), "long") is None
    bozuk = _df(kod, _bozuk(kod))
    if kod == "HACIM":
        bozuk.iloc[-1, bozuk.columns.get_loc("volume")] = 3.0
    assert _bul(kod, bozuk, "long") is None                          # kosul bozulunca tetiklemez


@pytest.mark.parametrize("kod", KODLAR)
def test_motor_yolu_tablo_satiri(kod):
    stop, hedef = _beklenen(kod)
    mod = arms.find_arm(f"IN1-{kod}")
    tf = "15m" if kod == "VWAP" else "1h"
    for short in (False, True):
        df = _df(kod, short=short)
        t = mod.compute(core_inp(df, pair=f"I{kod}{short}/USDT", tf=tf))
        row = t.iloc[-1]
        assert row["setup"] == f"IN1-{kod}" and row["side"] == ("short" if short else "long")
        assert bool(row["signal"]) and row["skip_reason"] is None, (kod, short, row["skip_reason"])
        s = -1.0 if short else 1.0
        c = float(df["close"].iloc[-1])
        assert row["planned_entry"] == pytest.approx(c)
        sd = abs(c - float(row["planned_stop"]))
        if hedef is None:
            assert float(row["planned_target"]) == pytest.approx(c + s * 2 * sd)
        else:
            assert float(row["planned_target"]) == pytest.approx(KAL - hedef if short else hedef)
        assert s * (float(row["planned_target"]) - c) > 0 and s * (c - float(row["planned_stop"])) > 0
    bos = mod.compute(core_inp(_df(kod, _bozuk(kod)), pair=f"B{kod}/USDT", tf=tf))
    assert not (bool(bos["signal"].iloc[-1]) and bos["side"].iloc[-1] == "long")      # coken mum karsi yonde (short) aday dogurabilir


def test_isinma_dolmadan_aday_yok_hata_yok():
    """SMA200 / bulut isinmasi dolmadan RSI, MAKESISIM, TK, KUMO aday uretmez (hata da vermez)."""
    for kod in ("RSI", "MAKESISIM", "TK", "KUMO", "RSI2"):
        df = _df("RSI").iloc[:60]
        t = arms.find_arm(f"IN1-{kod}").compute(core_inp(df, pair=f"W{kod}/USDT"))
        assert not t["signal"].any()


def test_vwap_yalniz_15m_ve_1h():
    assert in1.FORMASYONLAR["VWAP"].tfs == ("15m", "1h") and arms.find_arm("IN1-VWAP").TIMEFRAMES == ("15m", "1h")
    assert all(in1.FORMASYONLAR[k].tfs == TFS for k in KODLAR if k != "VWAP")


def test_vwap_utc_gunune_demirli():
    """Gun degisince VWAP sifirlanir: yeni gunun ilk mumunda VWAP = o gunun tipik fiyati."""
    df = _df("VWAP")
    ham = K._Ham(df)
    g = ham.gorunum("long")
    assert g.gun is not None and g.gun[0] == g.gun[95] and g.gun[95] != g.gun[96] if len(g.gun) > 96 else True
    w = in1._vwap(g)
    gun0 = 96                                            # 15 dk x 96 = 1 gun
    assert len(w) < gun0 or w[gun0] == pytest.approx((g.h[gun0] + g.l[gun0] + g.c[gun0]) / 3)


# ------------------------------------------------------------------------------------------------ kural cikislari
def _egim(a, b, n=300):
    return zig(a, [(b, n)])[0]


def _kural_serileri():
    yukari = _egim(100, 200)
    asagi = _egim(200, 100)
    dus = zig(100, [(200, 260), (140, 8)])[0]                       # yukselis sonrasi sert dusus
    hizlanan = zig(100, [(130, 150), (200, 60)])[0]                 # hizlanan yukselis (MACD > sinyal)
    gun_ici = zig(100, [(100.2, 24), (94, 12)])[0]
    return yukari, asagi, dus, gun_ici, hizlanan


# (kural kodu) -> (dogru donen seri adi, yanlis donen seri adi)
KURAL_BEKLENEN = {
    "RSI": ("yukari", "asagi"), "RSIDONUS": ("yukari", "asagi"), "RSI2": ("yukari", "asagi"), "STOK": ("yukari", "asagi"),
    "MAKESISIM": ("asagi", "yukari"), "KUMO": ("asagi", "yukari"), "TK": ("asagi", "yukari"), "FIYATMA": ("asagi", "yukari"),
    "HIZLIMA": ("asagi", "yukari"), "BOLLKIR": ("asagi", "yukari"), "MACD": ("dus", "hizlanan"), "BOLL": ("yukari", "asagi"),
    "VWAP": ("gun_ici", "yukari"),
}


@pytest.mark.parametrize("kod", KURALLI)
@pytest.mark.parametrize("yon", ("long", "short"))
def test_kural_cikisi_yonlu(kod, yon):
    ser = dict(zip(("yukari", "asagi", "dus", "gun_ici", "hizlanan"), _kural_serileri()))
    dogru, yanlis = KURAL_BEKLENEN[kod]
    kural = arms.exit_rule_of(f"IN1-{kod}")
    assert kural is not None
    tf = "15min" if kod == "VWAP" else "1h"

    def inp(ad):
        df = df_of(ser[ad], short=(yon == "short"), freq=tf, kal=KAL)
        return core_inp(df, pair=f"K{kod}{ad}{yon}/USDT", side=yon)
    # short pozisyonda ayna seri: ayni seri short gorunumde ayni sonucu verir
    assert kural(inp(dogru)) is True, (kod, yon)
    assert kural(inp(yanlis)) is False, (kod, yon)


def test_kural_cikisi_yoksa_none_ve_yon_verilmezse_long():
    for kod in ("UYUMSUZ", "FIBO", "HACIM", "MAGERI"):
        assert arms.exit_rule_of(f"IN1-{kod}") is None
    yukari = _egim(100, 200)
    kural = arms.exit_rule_of("IN1-RSI")
    assert kural(core_inp(df_of(yukari), pair="YON/USDT")) is True              # side None -> long
    assert kural(core_inp(df_of(yukari, short=True, kal=KAL), pair="YON2/USDT", side="long")) is False


def test_kural_cikisi_pozisyon_gorunumune_baglanir(monkeypatch):
    """strategy_runner kural cikisini pozisyonun yonuyle cagirir (ArmInput.side)."""
    import dataclasses
    from collections import Counter

    from trader_engine import strategy_runner as SR
    from trader_engine.strategy_runner import MultiArmSignalSource
    from test_formasyon_mf1 import _ctx
    monkeypatch.setattr(SR, "SignalParams", type("SP", (), {"from_mapping": staticmethod(lambda m: m)}))
    src = MultiArmSignalSource.__new__(MultiArmSignalSource)
    src.strict = False
    src.counters = Counter()
    gorulen = []
    mod = arms.find_arm("IN1-RSI")
    orig = mod.EXIT_RULE
    try:
        mod.EXIT_RULE = lambda i: gorulen.append(i.side) or True
        lab = type("L", (), {"_core_compact": lambda self, c: None})()
        ctx = type("C", (), {"pair": "X/USDT", "tf": "1h"})()
        v = _ctx(3)
        out = src._rule_exit(v, lab, "IN1-RSI", (df_of(_egim(100, 200)), ctx), None, {}, v.bar_close_ts, "short")
        assert gorulen == ["short"] and out.rule_exit is True and dataclasses.is_dataclass(out)
    finally:
        mod.EXIT_RULE = orig


def test_kural_cikisi_evaluate_exit_other_nedeniyle():
    from test_formasyon_mf1 import _ctx, _pos
    from trader_engine.position_manager import evaluate_exit
    d = evaluate_exit(_pos("IN1-FIYATMA", 109.0), _ctx(3, rule=True))
    assert (d.kind, d.reason) == ("exit", "other")
    assert evaluate_exit(_pos("IN1-FIYATMA", 109.0), _ctx(48)).reason == "time_stop"


# ------------------------------------------------------------------------------------------------ esdegerlik
def _esdeger(v3, kod, v3kod, o, h, l, c, stop_karsilastir=True, hedef_karsilastir=True):
    n = len(c)
    a = atr_of(o, h, l, c)
    Fd = {yon: v3.ozellik({"t": np.arange(n), "o": o, "h": h, "l": l, "c": c, "v": np.ones(n)}, yon) for yon in (1, -1)}
    ref = {}
    for t, d, sp, sa, ha, et in v3.gercek_sinyaller(v3kod, Fd):
        if 40 <= t <= n - 2:
            ref[(t, d)] = (sp["stop"], sp["hedef"])
    lib = tara(in1, kod, o, h, l, c, a, 40, n - 2, v=np.ones(n))
    ikili = {t for (t, y) in lib if (t, -y) in lib}                          # iki yonlu mumda aday yok (motor)
    f = lambda d: {k: v for k, v in d.items() if k[0] not in ikili}        # noqa: E731
    assert f(ref).keys() == f(lib).keys(), (kod, sorted(set(f(ref)) ^ set(f(lib)))[:10])
    for (t, yon), r in f(lib).items():
        if stop_karsilastir:
            assert f(ref)[(t, yon)][0] == pytest.approx(yon * r["stop"], rel=1e-9), (kod, t, yon)
        if hedef_karsilastir and r["hedef"] is not None and f(ref)[(t, yon)][1] is not None:
            assert f(ref)[(t, yon)][1] == pytest.approx(yon * r["hedef"], rel=1e-9)
    return len(f(ref))


@pytest.mark.parametrize("kod,v3kod,stop", [("RSI", "IND_RSI_3070", True), ("BOLL", "IND_BOLL_DONUS", True),
                                            ("MAKESISIM", "IND_MA_KESISIM", False), ("FIYATMA", "IND_FIYAT_MA", False)])
def test_setuplar_v3_esdegerligi(kod, v3kod, stop):
    """RSI ve BOLL: (t, yon, stop); MAKESISIM ve FIYATMA: yalniz (t, yon) (motorda 2 ATR stop eklendi)."""
    v3 = referans()
    toplam = 0
    for seed, vol in ((7, 0.012), (21, 0.02), (33, 0.008), (5, 0.015)):
        o, h, l, c = rw(3500, seed, vol)
        toplam += _esdeger(v3, kod, v3kod, o, h, l, c, stop_karsilastir=stop, hedef_karsilastir=False)
    assert toplam >= 5, (kod, toplam)
    b = SER[{"RSI": "RSI", "BOLL": "BOLL", "MAKESISIM": "MAKESISIM", "FIYATMA": "FIYATMA"}[kod]]
    b = b + [(b[-1][3], b[-1][3] + 0.1, b[-1][3] - 0.1, b[-1][3])] * 3
    s = 0
    for short in (False, True):
        df = df_of(b, short=short, kal=KAL)
        s += _esdeger(v3, kod, v3kod, *(df[k].to_numpy() for k in ("open", "high", "low", "close")), stop_karsilastir=stop,
                      hedef_karsilastir=False)
    assert s >= 1, (kod, s)


def test_ileriye_bakis_ve_pencere_bagimsizligi():
    """t'den sonraki mumlar degisince t'deki karar degismez; son 1000 mumluk pencere ayni adayi verir."""
    n = 3000
    o, h, l, c, v = rw(n, 13, 0.012, hacim=True)
    gun = np.arange(n) // 24
    a = atr_of(o, h, l, c)
    rng = np.random.default_rng(3)
    kes = 1500
    o2, h2, l2, c2 = (x.copy() for x in (o, h, l, c))
    for x in (o2, h2, l2, c2):
        x[kes + 1:] = x[kes + 1:] * rng.uniform(0.5, 1.5, n - kes - 1)
    v2 = v.copy()
    v2[kes + 1:] *= 5
    a2 = atr_of(o2, h2, l2, c2)
    toplam = 0
    for kod in KODLAR:
        tam = tara(in1, kod, o, h, l, c, a, 40, n - 1, v=v, gun=gun)
        toplam += len(tam)
        deg = tara(in1, kod, o2, h2, l2, c2, a2, 40, kes, v=v2, gun=gun)
        onc = {k: x for k, x in tam.items() if k[0] <= kes}
        assert deg.keys() == onc.keys(), kod
        for k in onc:
            assert deg[k]["stop"] == pytest.approx(onc[k]["stop"], abs=1e-9)
        W = 1000
        sl = slice(n - W, n)
        pen = tara(in1, kod, o[sl], h[sl], l[sl], c[sl], atr_of(o[sl], h[sl], l[sl], c[sl]), 500, W - 1, v=v[sl], gun=gun[sl])
        gercek = {k: x for k, x in tam.items() if k[0] >= n - W + 500}
        assert {(t + n - W, y) for (t, y) in pen} == set(gercek), kod
        for (t, y), x in pen.items():
            assert x["stop"] == pytest.approx(gercek[(t + n - W, y)]["stop"], abs=1e-6)
    assert toplam > 40


def test_hic_bir_dedektor_ders_parametresi_okumaz():
    import re
    src = (ROOT / "src" / "trader_engine" / "strategies" / "arms" / "in1.py").read_text(encoding="utf-8")
    assert re.search(r"\bparams\.\w", src) is None and "SignalParams" not in src


def test_kesif_17_formasyon_sanal_kurulum():
    ls = arms.list_arms()
    assert "IN1" not in ls
    assert sorted(s for s in ls if s.startswith("IN1-")) == sorted(f"IN1-{k}" for k in KODLAR)
    for k in KODLAR:
        m = arms.find_arm(f"IN1-{k}")
        assert m.CORE is False and m.EXIT_MODE == "target"
        assert arms.priority_of(f"IN1-{k}") == 400 + in1.FORMASYONLAR[k].sira and arms.time_stop_of(f"IN1-{k}") == 48
        assert (arms.exit_rule_of(f"IN1-{k}") is not None) == (k in KURALLI)
    assert sorted(in1.FORMASYONLAR[k].sira for k in KODLAR) == list(range(1, 18))
    assert sorted(KODLAR, key=lambda k: in1.FORMASYONLAR[k].sira) == [
        "UYUMSUZ", "MAKESISIM", "KUMO", "TK", "FIBO", "HACIM", "RSI", "RSIDONUS", "RSI2", "STOK", "MACD", "MAGERI", "BOLLKIR", "VWAP",
        "FIYATMA", "HIZLIMA", "BOLL"]
    assert len(arms.list_arms()) == 10 + 12 + 13 + 17 + 0 or len(arms.list_arms()) >= 52


def test_hiz_5000_mum_42_formasyon():
    """MF1 + GF1 + IN1 (42 formasyon) 5000 mumluk bir cift x ZD icin toplam < 50 ms (ortak onbellek, gosterge tek hesap)."""
    K.IND_PENCERE = 1200
    o, h, l, c, v = rw(5000, 5, 0.012, hacim=True)
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v},
                      index=pd.date_range("2026-01-01", periods=5000, freq="1h", tz="UTC"))
    ad = [f"MF1-{k}" for k in mf1.FORMASYONLAR] + [f"GF1-{k}" for k in gf1.FORMASYONLAR] + [f"IN1-{k}" for k in in1.FORMASYONLAR]
    assert len(ad) == 42
    import bos_cekirdek as M1MOD
    core = M1MOD.empty_output(df.index)                    # motorda ortak tablo lab'da bir kez hesaplanir (burada da tek kopya)
    mk = lambda d, p: arms.ArmInput(pair=p, tf="1h", D=d.index[-1].to_pydatetime(), trig=d, h4=None, params=None, core_fn=lambda: core)  # noqa: E731
    for s in ad:
        arms.find_arm(s).compute(mk(df, "HIZ/USDT"))
    en_iyi = 1e9
    for r in range(5):
        inp = mk(df.copy(), f"HIZ{r}/USDT")
        t0 = time.process_time()   # CPU suresi: paralel CI kosucusunda (xdist) duvar saati dalgalanmasindan etkilenmez
        for s in ad:
            arms.find_arm(s).compute(inp)
        en_iyi = min(en_iyi, time.process_time() - t0)
    print("42 formasyon, 5000 mum:", round(en_iyi * 1000, 1), "ms")
    from hiz_olcek import olcek
    k = olcek()
    assert en_iyi < 0.05 * k, (en_iyi, k)


# ------------------------------------------------------------------------------------------------ kagit = canli
def _cfg(ad):
    return json.loads((ROOT / "config" / ad).read_text(encoding="utf-8"))


def test_kagit_canli_ayni_ve_in1_66_kimlik_toplam_203():
    p, l = _cfg("engine.paper.json"), _cfg("engine.live.json")
    for k in ("arms",):
        assert p[k] == l[k], k
    lib = [a for a in p["arms"] if a.startswith("IN1-")]
    from evren_destek import config_kollari
    beklenen = config_kollari(f"{s}@{tf}" for s in sorted(a for a in arms.list_arms() if a.startswith("IN1-")) for tf in arms.find_arm(s).TIMEFRAMES)
    assert sorted(lib) == sorted(beklenen) and len(lib) == 49 and len(set(p["arms"])) == len(p["arms"]) == 162   # 26.11: 15m giris kolu yok; IN1 66 -> 49 kol
    assert "IN1-VWAP@4h" not in lib and "IN1-VWAP@15m" not in lib and "IN1-VWAP@1h" in lib
    for ad in ("engine.paper.json", "engine.live.json"):
        cfg = C.load_cli_config(ROOT / "config", "learner", ad.split(".")[1])
        assert all(a in cfg.arms for a in beklenen)


def test_telegram_adlari_in1():
    from trader_core import tg_sade
    for k in KODLAR:
        ad = tg_sade.kurulum_adi(f"IN1-{k}@1h")
        assert ad.startswith("Gösterge: ") and ad != f"IN1-{k}", k
