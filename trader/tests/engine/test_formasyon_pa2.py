"""24.11 kullanici karari: formasyon kutuphanesi, adim 3 (PA2 price action ailesi, 8 formasyon, 29 kol).
Sentetik ornek (long + short aynasi + bozulan kosul), motor yolu tablo satiri, ileriye bakis (rastgele yuruyus + sonradan degisen mumlar),
kimlik/kesif/zaman stopu, tavanlar, kagit = canli."""
from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_engine import config as C
from trader_engine.strategies import arms
from trader_engine.strategies.arms import _kutuphane as K
from trader_engine.strategies.arms import m1 as M1MOD
from trader_engine.strategies.arms import pa2

ROOT = Path(__file__).resolve().parents[2]
KODLAR = ("EMIRBLOK", "BOLGE", "FVG", "ONCEKI", "TCIZGI", "SEVIYE", "UCVURUS", "TUKENIS")
TFS = {"EMIRBLOK": ("15m", "1h", "4h", "1d"), "BOLGE": ("15m", "1h", "4h", "1d"), "FVG": ("15m", "1h", "4h", "1d"),
       "ONCEKI": ("15m", "1h", "4h"), "TCIZGI": ("15m", "1h", "4h", "1d"), "SEVIYE": ("15m", "1h", "4h", "1d"),
       "UCVURUS": ("15m", "1h", "4h", "1d"), "TUKENIS": ("15m", "1h")}
KAL = 180.0                      # short aynasi: gercek fiyat = KAL - long fiyati
BAS = "2026-01-05"               # Pazartesi 00:00 UTC


# ------------------------------------------------------------------------------------------------ sentetik seriler
def df_of(bars, freq="1h", start=BAS):
    a = np.array(bars, float)
    idx = pd.date_range(start, periods=len(a), freq=freq, tz="UTC")
    return pd.DataFrame({"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3], "volume": 1.0}, index=idx)


def duz(n, base=100.0):
    out, p = [], base
    for i in range(n):
        c = base + 0.4 * np.sin(i * 1.3)
        out.append((p, max(p, c) + 0.5, min(p, c) - 0.5, c))
        p = c
    return out


def yol(anch, start_c, dips=(), dus=(), eps=0.3):
    xs, ys = [a[0] for a in anch], [a[1] for a in anch]
    cs = np.interp(np.arange(xs[-1] + 1), xs, ys)
    out, p = [], start_c
    for c in cs:
        out.append((p, max(p, c) + eps, min(p, c) - eps, float(c)))
        p = c
    for d in dus:
        o, h, l, c = out[d]
        out[d] = (o, h, min(o, c), c)
    for d in dips:
        o, h, l, c = out[d]
        out[d] = (o, h, l - 0.3, c)
    return out


def s_bolge():
    return duz(40, 161.0) + [(161.0, 161.3, 160.6, 161.1), (161.1, 161.4, 160.8, 160.9), (161.0, 165.0, 160.9, 164.8),
                             (164.8, 166, 164.0, 165.5), (165.5, 166, 163.5, 164.0), (161.2, 162.5, 160.9, 162.2)]


def s_emirblok():
    return duz(40) + [(100.6, 100.8, 99.0, 99.2), (99.3, 104.5, 99.2, 104.3), (104.3, 105.5, 103.5, 105.0), (101.0, 103.2, 100.2, 102.5)]


def s_fvg():
    return duz(40) + [(100.0, 101.0, 99.5, 100.5), (100.6, 105.0, 100.4, 104.8), (104.8, 106.0, 102.0, 105.5),
                      (105.5, 106.5, 104.0, 105.0), (102.0, 104.2, 101.5, 102.9)]


def s_ucvurus():
    return duz(40) + [(100.5, 100.6, 98.9, 99.0), (99.2, 99.3, 97.5, 97.6), (97.8, 97.9, 96.2, 96.3), (96.2, 101.0, 95.9, 100.8)]


def s_onceki(freq="1h"):
    n = {"1h": 24, "4h": 42}[freq]                       # onceki donem: 1s -> gun (24), 4s -> hafta (42)
    once = [(105, 110 if i == 3 else 108, 100 if i == 10 else 102, 105) for i in range(n)]
    ek = [(105, 108, 102, 105)] * (n if freq == "1h" else 0)
    bu = [(105, 106, 104, 105)] * 5 + [(104, 104.5, 99.5, 100.5), (100.5, 103, 100.2, 102.5)]
    return df_of(ek + once + bu, freq)


def s_tcizgi():
    anch = [(0, 150), (40, 100), (52, 112), (62, 104), (72, 110), (85, 108.8)]
    return yol(anch, 150, dips=(40, 62), dus=(63,)) + [(108.8, 109.6, 107.8, 109.5)]


def s_seviye():
    anch = [(0, 150), (40, 100), (50, 110), (60, 100.1), (66, 104), (71, 100.6)]
    return yol(anch, 150, dips=(40, 60)) + [(100.0, 100.25, 99.3, 100.2)]


def s_tukenis():
    gun = [(100 + 0.3 * np.sin(i), 101.2, 98.9, 100 + 0.4 * np.sin(i + 1)) for i in range(24)]
    bugun = [(100, 103, 99.8, 102), (102, 106, 101.5, 105.5), (105.5, 105.8, 102, 103), (103, 103.5, 101, 101.5),
             (101.5, 102, 100.5, 100.8), (100.8, 101, 99.9, 100.0), (100.0, 100.4, 99.2, 99.5), (99.5, 99.6, 98.7, 98.9),
             (98.9, 101.2, 98.8, 101.0)]
    return gun * 15 + bugun


SERI = {"BOLGE": s_bolge, "EMIRBLOK": s_emirblok, "FVG": s_fvg, "UCVURUS": s_ucvurus, "TCIZGI": s_tcizgi, "SEVIYE": s_seviye,
        "TUKENIS": s_tukenis}


def seri(kod, *, short=False, bozuk=False, freq="1h"):
    df = s_onceki(freq) if kod == "ONCEKI" else df_of(SERI[kod](), freq)
    if bozuk:
        c = float(df["close"].iloc[-2])
        df.iloc[-1] = [c, c + 0.01, c - 0.01, c, 1.0]                 # son mum doji: her formasyon bozulur
    if short:
        o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
        df = df.copy()
        df["open"], df["high"], df["low"], df["close"] = KAL - o, KAL - l, KAL - h, KAL - c
    return df


def bul(kod, df, side="long"):
    ham = K._Ham(df)
    assert ham.ok
    return pa2.FORMASYONLAR[kod].bul(ham.gorunum(side))


def _gun_atr(df):
    g = df.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    pc = g["close"].shift(1)
    tr = pd.concat([g["high"] - g["low"], (g["high"] - pc).abs(), (g["low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.iloc[-16:-1].mean())          # bugunden onceki 15 gunun son 14 gercek araligi


def beklenen(kod, df):
    """(stop, hedef) long uzayinda; hedef hesaplari df'ten bagimsiz yoldan."""
    c = float(df["close"].iloc[-1])
    if kod == "BOLGE":
        alt = float(df["low"].iloc[-8:-3].min())        # taban: 5 mum (iki taban mumu + onceki 3 duz mum), k oncesi
        return alt, c + 3 * (c - alt)
    if kod == "EMIRBLOK":
        return 99.0, 109.5                               # 105.5 (tepe) girise 1R'den yakin -> 2R
    if kod == "FVG":
        return 99.5, 106.5
    if kod == "ONCEKI":
        return 99.5, 108.5                               # orta nokta 105 girise 1R'den yakin -> 2R
    if kod == "TCIZGI":
        a = pa2_atr(df)
        return c - a, c + 2.5 * a
    if kod == "SEVIYE":
        return 99.3, float(df["high"].iloc[:-1].iloc[40:].max())
    if kod == "UCVURUS":
        return 95.9, None
    if kod == "TUKENIS":
        return 98.7, c + 0.5 * _gun_atr(df)
    raise KeyError(kod)


def pa2_atr(df):
    return float(K._Ham(df).atr[-1])


@pytest.mark.parametrize("kod", KODLAR)
def test_sentetik_long_short_ve_bozulan_kosul(kod):
    df = seri(kod)
    stop, hedef = beklenen(kod, df)
    r = bul(kod, df)
    assert r is not None, kod
    assert r["stop"] == pytest.approx(stop, abs=1e-9)
    if hedef is None:
        assert r["hedef"] is None                                   # 2R (hesapla doldurur)
    else:
        assert r["hedef"] == pytest.approx(hedef, abs=1e-9)
    assert bul(kod, df, "short") is None                            # long serisinde short yok
    ds = seri(kod, short=True)
    rs = bul(kod, ds, "short")
    assert rs is not None, kod                                       # short, long'un fiyat aynasi
    assert rs["stop"] == pytest.approx(-(KAL - stop), abs=1e-9)
    if hedef is not None:
        assert rs["hedef"] == pytest.approx(-(KAL - hedef), abs=1e-9)
    assert bul(kod, ds, "long") is None
    assert bul(kod, seri(kod, bozuk=True), "long") is None          # kosul bozulunca tetiklemez


def test_onceki_haftalik_4s():
    """4s'de seviye onceki UTC haftasi (Pazartesi 00:00); onceki donem eksikse aday yok."""
    df = seri("ONCEKI", freq="4h")
    r = bul("ONCEKI", df)
    assert r is not None and r["stop"] == 99.5 and r["hedef"] == pytest.approx(108.5)
    assert bul("ONCEKI", seri("ONCEKI", short=True, freq="4h"), "short") is not None
    assert bul("ONCEKI", df.iloc[3:]) is None                         # onceki haftanin acilisi pencerede yok
    assert bul("ONCEKI", rw_df(120, 4, 0.02, "1D")) is None and "1d" not in pa2.FORMASYONLAR["ONCEKI"].tfs   # 1d: ONCEKI yok


def test_onceki_ozel_kosullar():
    df = seri("ONCEKI")
    d = df.copy()
    d.iloc[24 + 24 + 2] = [105, 105.5, 99.0, 99.4, 1.0]               # s'den once L altinda KAPANIS
    assert bul("ONCEKI", d) is None
    d = df.copy()
    d.iloc[-1] = [100.5, 103, 99.6, 99.9, 1.0]                        # kapanis L = 100 altinda
    assert bul("ONCEKI", d) is None
    d = df.copy()
    d.iloc[-2] = [100.0, 102.0, 99.5, 101.0, 1.0]                     # s = t-1 yesil kapandi: ilk sinyal oydu
    assert bul("ONCEKI", d) is None
    d = df.iloc[:-1]
    assert bul("ONCEKI", d) is None                                    # t = s kirmizi (kapanis L ustunde ama mum kirmizi)


def test_tukenis_ozel_kosullar():
    df = seri("TUKENIS")
    assert bul("TUKENIS", df.iloc[24:]) is None                       # 14 tam gun yok
    d = df.copy()
    d.iloc[-1] = [98.9, 99.0, 98.8, 98.95, 1.0]                        # c <= h[t-1]
    assert bul("TUKENIS", d) is None
    d = df.iloc[:-1].copy()                                            # dip son 4 mumdan eski: iki sakin mum eklenir
    sakin = pd.DataFrame([(101.0, 101.5, 100.6, 101.2, 1.0)] * 4 + [(101.2, 102.0, 101.1, 101.9, 1.0)], columns=d.columns,
                         index=pd.date_range(d.index[-1] + pd.Timedelta(hours=1), periods=5, freq="1h"))
    assert bul("TUKENIS", pd.concat([d, sakin])) is None
    # gun araligi 2 dATR altinda: tepeyi dusur
    e = df.copy()
    e.iloc[-9:, e.columns.get_loc("high")] = np.minimum(e["high"].iloc[-9:], 101.5)
    e.iloc[-9:, e.columns.get_loc("close")] = np.minimum(e["close"].iloc[-9:], 101.5)
    assert bul("TUKENIS", e) is None
    assert bul("TUKENIS", df.iloc[:-1]) is None


def test_bolge_tek_hak_ve_taban():
    df = seri("BOLGE")
    d = df.copy()
    d.iloc[-2] = [164.0, 164.2, 160.8, 163.0, 1.0]                     # k+2 bolgeye dokundu: ilk donus bu mumdu
    assert bul("BOLGE", d) is None
    d = df.copy()
    d.iloc[-1] = [163.0, 164.0, 162.0, 163.5, 1.0]                     # bolgeye inmedi
    assert bul("BOLGE", d) is None
    d = df.copy()
    d.iloc[-4] = [161.0, 165.0, 160.9, 161.5, 1.0]                     # kopus mumu c <= taban tepesi ya da govde kucuk
    assert bul("BOLGE", d) is None


def test_tcizgi_seviye_ucvurus_ozel_kosullar():
    df = seri("TCIZGI")
    d = df.copy()
    d.iloc[50] = [d["open"].iloc[50], d["high"].iloc[50], 90.0, 95.0, 1.0]     # cizgi alti kapanis (D1..t arasi)
    assert bul("TCIZGI", d) is None
    d = df.copy()
    d.iloc[-1] = [108.8, 109.6, 108.5, 109.5, 1.0]                              # cizgiye 0,25 ATR'den uzak
    assert bul("TCIZGI", d) is None
    s = seri("SEVIYE")
    d = s.copy()
    d.iloc[65] = [104.0, 104.3, 98.0, 99.0, 1.0]                                # D2'den beri S altinda kapanis
    assert bul("SEVIYE", d) is None
    d = s.copy()
    d.iloc[-1] = [100.0, 100.8, 98.0, 100.2, 1.0]                               # ust golge 0,1 aralik ustu / alt golge kisa degil
    assert bul("SEVIYE", d) is None
    u = seri("UCVURUS")
    d = u.copy()
    d.iloc[-2] = [97.8, 98.5, 96.2, 98.3, 1.0]                                  # kapanis dipte degil
    assert bul("UCVURUS", d) is None
    d = u.copy()
    d.iloc[-1] = [96.2, 100.0, 95.9, 99.9, 1.0]                                 # c <= h[t-3]
    assert bul("UCVURUS", d) is None


# ------------------------------------------------------------------------------------------------ motor yolu
def _core_inp(df, pair="BTC/USDT", tf="1h"):
    return arms.ArmInput(pair=pair, tf=tf, D=df.index[-1].to_pydatetime() + timedelta(hours=1), trig=df, h4=None, params=None,
                         core_fn=lambda: M1MOD.empty_output(df.index))


@pytest.mark.parametrize("kod", KODLAR)
def test_motor_yolu_tablo_satiri(kod):
    mod = arms.find_arm(f"PA2-{kod}")
    for short in (False, True):
        df = seri(kod, short=short)
        stop, hedef = beklenen(kod, seri(kod))
        t = mod.compute(_core_inp(df, pair=f"P{kod}{short}/USDT"))
        row = t.iloc[-1]
        assert row["setup"] == f"PA2-{kod}" and row["side"] == ("short" if short else "long")
        s = -1.0 if short else 1.0
        c = float(df["close"].iloc[-1])
        assert row["planned_entry"] == pytest.approx(c)
        assert row["planned_stop"] == pytest.approx(KAL - stop if short else stop)
        sd = abs(c - float(row["planned_stop"]))
        if hedef is None:
            assert float(row["planned_target"]) == pytest.approx(c + s * 2 * sd)
        else:
            assert float(row["planned_target"]) == pytest.approx(KAL - hedef if short else hedef)
        assert bool(row["signal"]) and row["skip_reason"] is None, (kod, short, row["skip_reason"])
        assert not t.iloc[:-1]["signal"].any()


def test_stop_dar_ise_elenir_ve_rr():
    """stop < %0,6 -> stop_width (aday var, sinyal yok). TUKENIS hedefi 0,5 dATR: R:R < 1 olabilir, yine de aday."""
    df = seri("UCVURUS")
    df.iloc[-1] = [96.2, 101.0, 100.7, 100.8, 1.0]          # stop = 100.7 ~ giris: dar
    row = arms.find_arm("PA2-UCVURUS").compute(_core_inp(df, pair="SW/USDT")).iloc[-1]
    assert row["setup"] is None or row["skip_reason"] == "stop_width"


# ------------------------------------------------------------------------------------------------ ileriye bakis
def rw(n, seed, vol=0.012):
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    o = np.concatenate(([100.0], c[:-1])) * np.exp(rng.normal(0, vol / 3, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    return o, h, l, c


def rw_df(n, seed, vol=0.012, freq="1h"):
    o, h, l, c = rw(n, seed, vol)
    idx = pd.date_range(BAS, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=idx)


def tara(kod, df, bas, son):
    """{(t, yon): (stop, hedef)}; her t icin taze Gorunum (dizilerin TAMAMI verilir, dedektor yalniz <= t okumali)."""
    ham = K._Ham(df)
    f = pa2.FORMASYONLAR[kod].bul
    out = {}
    for t in range(bas, son + 1):
        for yon, (o, h, l, c) in ((1, (ham.o, ham.h, ham.l, ham.c)), (-1, (-ham.o, -ham.l, -ham.h, -ham.c))):
            r = f(K.Gorunum(o, h, l, c, ham.atr, t, ham.sec))
            if r is not None:
                out[(t, yon)] = (r["stop"], r["hedef"])
    return out


def test_ileriye_bakis_rastgele_yuruyus():
    """t'den sonraki mumlar degisince t'deki karar degismez; son-mum penceresi (kesik dizi) ayni karari verir."""
    n, kes = 1500, 1000
    df = rw_df(n, 21, 0.015)
    rng = np.random.default_rng(3)
    d2 = df.copy()
    for k in ("open", "high", "low", "close"):
        d2.iloc[kes + 1:, d2.columns.get_loc(k)] = d2[k].iloc[kes + 1:].to_numpy() * rng.uniform(0.5, 1.5, n - kes - 1)
    d2["high"] = d2[["open", "high", "low", "close"]].max(axis=1)
    d2["low"] = d2[["open", "high", "low", "close"]].min(axis=1)
    toplam = 0
    kisa = df.iloc[:kes + 1]
    for kod in KODLAR:
        tam = tara(kod, df, 60, n - 1)
        toplam += len(tam)
        deg = tara(kod, d2, 60, kes)
        onc = {k: v for k, v in tam.items() if k[0] <= kes}
        assert deg.keys() == onc.keys(), kod
        for k in onc:
            assert deg[k][0] == pytest.approx(onc[k][0], abs=1e-9), kod
        ks = tara(kod, kisa, 60, kes)                                  # gelecegi hic olmayan seri
        assert ks.keys() == onc.keys(), kod
    assert toplam > 40, toplam


@pytest.mark.parametrize("kod", KODLAR)
def test_ileriye_bakis_sentetik_gelecek_degisir(kod):
    df = seri(kod)
    n = len(df)
    ek = pd.DataFrame({"open": 50.0, "high": 400.0, "low": 1.0, "close": 3.0, "volume": 1.0},
                      index=pd.date_range(df.index[-1] + (df.index[1] - df.index[0]), periods=6, freq=df.index[1] - df.index[0]))
    uzun = pd.concat([df, ek])
    assert tara(kod, uzun, n - 1, n - 1) == tara(kod, df, n - 1, n - 1) and (n - 1, 1) in tara(kod, df, n - 1, n - 1)


def test_pencere_bagimsizligi_gunluk_atr():
    """TUKENIS gunluk ATR'si pencere uzunlugundan bagimsiz (15 tam gun yeter; daha eski mumlar degisse de ayni)."""
    df = df_of(s_tukenis())
    uzun = pd.concat([df_of(duz(24 * 10, 130.0), start="2025-12-20"), df])
    a, b = bul("TUKENIS", df), bul("TUKENIS", uzun)
    assert a["stop"] == pytest.approx(b["stop"]) and a["hedef"] == pytest.approx(b["hedef"])


def test_hiz_5000_mum_8_formasyon():
    df = rw_df(5000, 5)
    inp = _core_inp(df, pair="HIZ/USDT")
    for kod in KODLAR:
        arms.find_arm(f"PA2-{kod}").compute(inp)
    en_iyi = 1e9
    for r in range(3):
        inp2 = _core_inp(df.copy(), pair=f"HIZ{r}/USDT")
        t0 = time.perf_counter()
        for kod in KODLAR:
            arms.find_arm(f"PA2-{kod}").compute(inp2)
        en_iyi = min(en_iyi, time.perf_counter() - t0)
    assert en_iyi < 0.15, en_iyi


# ------------------------------------------------------------------------------------------------ kesif ve kimlik
def test_kesif_8_formasyon_29_kol():
    ls = arms.list_arms()
    assert "PA2" not in ls
    assert sorted(s for s in ls if s.startswith("PA2-")) == sorted(f"PA2-{k}" for k in KODLAR)
    toplam = 0
    for k in KODLAR:
        m = arms.find_arm(f"PA2-{k}")
        assert m.TIMEFRAMES == TFS[k] and m.CORE is False and m.EXIT_MODE == "target"
        assert set(m.FEATURES) == {"body_ratio", "wick_ratio", "rr", "f_seviye", "f_olcu_atr", "f_yas"}
        assert arms.priority_of(f"PA2-{k}") == 250 + pa2.FORMASYONLAR[k].sira
        assert arms.exit_rule_of(f"PA2-{k}") is None
        toplam += len(m.TIMEFRAMES)
    assert toplam == 29
    assert sorted(pa2.FORMASYONLAR[k].sira for k in KODLAR) == list(range(1, 9))
    assert arms.family_of("PA2-BOLGE") == "PA2" and arms.parse_arm_id("PA2-EMIRBLOK@1h") == ("PA2-EMIRBLOK", "1h")
    assert 200 < arms.priority_of("PA2-EMIRBLOK") < 300 < arms.priority_of("MF1-YILDIZ")
    assert max(arms.priority_of(s) for s in ls if not s.startswith(("MF1-", "PA2-"))) < 250


def test_zaman_stopu_zd_basina():
    assert arms.time_stop_of("PA2-UCVURUS") == 5 and arms.time_stop_of("PA2-BOLGE") == 48
    assert arms.time_stop_of("PA2-TUKENIS", "15m") == 48 and arms.time_stop_of("PA2-TUKENIS", "1h") == 12
    assert arms.time_stop_of("T1", "1h") == 48 and arms.time_stop_of("MF1-YILDIZ", "1h") == 20


def test_ders_parametresi_okumaz():
    src = (ROOT / "src" / "trader_engine" / "strategies" / "arms" / "pa2.py").read_text(encoding="utf-8")
    import re
    assert re.search(r"\bparams\.\w", src) is None and "SignalParams" not in src


def _cfg(ad):
    return json.loads((ROOT / "config" / ad).read_text(encoding="utf-8"))


def test_kagit_canli_ayni_ve_pa2_29_kimlik():
    p, l = _cfg("engine.paper.json"), _cfg("engine.live.json")
    for k in ("arms", "arm_max_positions", "arm_family_max_positions"):
        assert p[k] == l[k], k
    assert p["arm_family_max_positions"] == {"MF1": 6, "PA2": 6}
    assert p["arm_max_positions"]["PA2-*"] == 3
    lib = [a for a in p["arms"] if a.startswith("PA2-")]
    beklenen_ids = [f"PA2-{k}@{tf}" for k in KODLAR for tf in TFS[k]]
    assert sorted(lib) == sorted(beklenen_ids) and len(lib) == 29 and len(set(p["arms"])) == len(p["arms"])
    for ad in ("engine.paper.json", "engine.live.json"):
        cfg = C.load_cli_config(ROOT / "config", "learner", ad.split(".")[1])
        assert cfg.arm_family_max_positions == {"MF1": 6, "PA2": 6} and cfg.arm_max_positions["PA2-*"] == 3
        assert all(a in cfg.arms for a in beklenen_ids)


def test_aile_ve_joker_tavani():
    from trader_engine import arm_guard as AG
    caps = {"default": 6, "PA2-*": 3}
    assert AG.arm_cap(caps, "PA2-BOLGE@1h", "PA2-BOLGE") == 3
    assert AG.family_full(["PA2-BOLGE"] * 5, "PA2-FVG", {"PA2": 6}) is None
    assert AG.family_full(["PA2-BOLGE"] * 3 + ["PA2-FVG"] * 3, "PA2-FVG", {"PA2": 6}) == "PA2"
    assert AG.family_full(["PA2-BOLGE"] * 6, "MF1-YUTAN", {"PA2": 6}) is None


def test_telegram_adlari():
    from trader_core import tg_sade
    for k in KODLAR:
        assert tg_sade.kurulum_adi(f"PA2-{k}@1h").startswith("PA: ") and tg_sade.kurulum_adi(f"PA2-{k}@1h") != f"PA2-{k}"
