"""24.11 kullanici karari: formasyon kutuphanesi, adim 2 (GF1 13 grafik formasyonu).
Sentetik ornek (long + short aynasi + bozulan kosul), setuplar_v3 esdegerligi (YATAY/UCGEN/IKILI/OBO), ileriye bakis (onay gecikmesi,
pencere bagimsizligi), simetrik ucgen/KAMA/TREND dislama, kesif ve kagit = canli."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from formasyon_destek import KAL, atr_of, bozan, core_inp, df_of, referans, rw, tara, zig
from trader_engine import config as C
from trader_engine.strategies import arms
from trader_engine.strategies.arms import _kutuphane as K
from trader_engine.strategies.arms import gf1

ROOT = Path(__file__).resolve().parents[2]
KODLAR = ("OBO", "UCLU", "KUPA", "IKILI", "KAMA", "UCGEN", "BAYRAK", "FLAMA", "RETEST", "SAHTE", "TREND", "KANAL", "YATAY")
TFS = ("1h", "4h", "1d")

# ------------------------------------------------------------------------------------------------ sentetik seriler
O = {
    "YATAY": (100, [(110, 15), (100, 12), (110.5, 12), (104, 6), (109, 5), (112.5, 1)]),
    "IKILI": (120, [(100, 20), (108, 6), (100.5, 8), (104, 3), (107.5, 3), (109.5, 1)]),
    "UCLU": (120, [(100, 20), (108, 12), (100.5, 12), (108.5, 12), (100.2, 12), (104, 3), (107, 3), (109.8, 1)]),
    "BAYRAK": (100, [(100.5, 30), (120, 8), (114, 6), (121, 1)]),
    "FLAMA": (100, [(100.5, 30), (120, 8), (116, 2), (119.5, 2), (117, 2), (118.5, 2), (117.5, 2), (118, 2), (121, 1)]),
    "KAMA": (110, [(120, 12), (105, 12), (114, 12), (103, 12), (108, 3), (111, 1)]),
    "TREND": (110, [(120, 12), (105, 12), (114, 12), (98, 12), (104, 3), (111, 1)]),
    "KANAL": (110, [(120, 12), (100.4, 12), (120.5, 12), (100.2, 12), (100.3, 1), (102, 1)]),
    "SAHTE": (110, [(120, 12), (100, 12), (108, 12), (100.5, 12), (102, 3), (98, 3), (101, 1)]),
    "KUPA": (100, [(110, 12), (90, 15), (110.5, 15), (106, 6), (109, 4), (112, 1)]),
    "RETEST": (100, [(110, 15), (100, 12), (110.5, 12), (104, 6), (109, 5), (112.5, 1), (114, 2), (110.7, 3), (112, 1)]),
    "OBO": (160, [(160.2, 30), (100, 20), (112, 12), (90, 12), (112.5, 12), (100.3, 12), (106, 4), (114, 1)]),
    "UCGEN_S": (100, [(120, 12), (104, 12), (114, 12), (108, 12), (109.5, 2), (111.5, 1)]),
    "UCGEN_A": (100, [(110, 12), (102, 12), (106.5, 1), (106, 4), (102.6, 8), (110.4, 12), (104, 6), (109, 5), (112.5, 1)]),
}


def _beklenen(ad, b, wp):
    """(stop, hedef | None) long uzayinda, ham mumlardan bagimsiz hesap."""
    a = np.array(b, float)
    h, l = a[:, 1], a[:, 2]
    n = len(a)
    if ad == "YATAY":
        L = max(h[wp[0]], h[wp[2]])
        return min(L, l[-1]), L + (L - l[wp[0]:wp[2] + 1].min())
    if ad == "IKILI":
        bo, dip = h[wp[0]:wp[2] + 1].max(), min(l[wp[0]], l[wp[2]])
        return dip, bo + (bo - dip)
    if ad == "UCLU":
        bo, dip = h[wp[0]:wp[4] + 1].max(), min(l[wp[0]], l[wp[2]], l[wp[4]])
        return dip, bo + (bo - dip)
    if ad in ("BAYRAK", "FLAMA"):
        P = wp[1]
        H = h[P] - l[P - 10:P + 1].min()
        return l[P + 1:n - 1].min(), h[P + 1:n - 1].max() + H
    if ad == "KAMA":
        return l[wp[3]], h[wp[0]]
    if ad == "TREND":
        return l[wp[3]], None
    if ad == "KANAL":
        return min(l[-1], l[wp[1]], l[wp[3]]), max(h[wp[0]], h[wp[2]])
    if ad == "SAHTE":
        return l[-3:].min(), None
    if ad == "KUPA":
        L = max(h[wp[0]], h[wp[2]])
        return l[wp[2]:].min(), L + (L - l[wp[0]:wp[2] + 1].min())
    if ad == "RETEST":
        L = max(h[wp[0]], h[wp[2]])
        return min(l[-1], L), L + (L - l[wp[0]:wp[2] + 1].min())
    if ad == "OBO":
        egim = (h[85] - h[61]) / (85 - 61)
        D = h[61] + egim * (73 - 61) - l[73]
        return l[73], h[61] + egim * (n - 1 - 61) + D
    if ad == "UCGEN_S":
        egim = (h[wp[2]] - h[wp[0]]) / (wp[2] - wp[0])
        return l[wp[3]], h[wp[0]] + egim * (n - 1 - wp[0]) + (h[wp[0]] - l[wp[1]])
    if ad == "UCGEN_A":
        return l[54], max(h[wp[0]], h[wp[5]]) + (h[wp[0]] - l[wp[1]])
    raise KeyError(ad)


def _ornek(ad):
    s, legs = O[ad]
    return zig(s, legs)


def _bul(kod, df, side):
    ham = K._Ham(df)
    assert ham.ok
    return gf1.FORMASYONLAR[kod].bul(ham.gorunum(side))


@pytest.mark.parametrize("ad", list(O))
def test_sentetik_long_short_ve_bozulan_kosul(ad):
    kod = ad.split("_")[0]
    b, wp = _ornek(ad)
    stop, hedef = _beklenen(ad, b, wp)
    r = _bul(kod, df_of(b), "long")
    assert r is not None, ad
    assert r["stop"] == pytest.approx(stop, abs=1e-9)
    if hedef is None:
        assert r["hedef"] is None                                   # 2R (hesapla doldurur)
    else:
        assert r["hedef"] == pytest.approx(hedef, abs=1e-9)
    assert _bul(kod, df_of(b), "short") is None                     # long serisinde short yok
    rs = _bul(kod, df_of(b, short=True), "short")                   # aynalanmis seri: ayni formasyon short olarak
    assert rs is not None, ad
    assert rs["stop"] == pytest.approx(stop - KAL, abs=1e-9)        # gorunum uzayi: -(KAL - fiyat)
    if hedef is not None:
        assert rs["hedef"] == pytest.approx(hedef - KAL, abs=1e-9)
    assert _bul(kod, df_of(b, short=True), "long") is None
    assert _bul(kod, df_of(bozan(b)), "long") is None               # kosul bozulunca tetiklemez


@pytest.mark.parametrize("ad", list(O))
def test_motor_yolu_tablo_satiri(ad):
    kod = ad.split("_")[0]
    b, wp = _ornek(ad)
    stop, hedef = _beklenen(ad, b, wp)
    mod = arms.find_arm(f"GF1-{kod}")
    for short in (False, True):
        df = df_of(b, short=short)
        t = mod.compute(core_inp(df, pair=f"G{ad}{short}/USDT"))
        row = t.iloc[-1]
        assert row["setup"] == f"GF1-{kod}" and row["side"] == ("short" if short else "long")
        assert bool(row["signal"]) and row["skip_reason"] is None, (ad, row["skip_reason"])
        s = -1.0 if short else 1.0
        c = float(df["close"].iloc[-1])
        assert row["planned_entry"] == pytest.approx(c)
        sd = abs(c - float(row["planned_stop"]))
        if hedef is None:
            assert float(row["planned_target"]) == pytest.approx(c + s * 2 * sd)
        else:
            assert float(row["planned_target"]) == pytest.approx(KAL - hedef if short else hedef)
        assert s * (float(row["planned_target"]) - c) > 0 and s * (c - float(row["planned_stop"])) > 0
        assert t["signal"].iloc[:-1].sum() == 0
    bos = mod.compute(core_inp(df_of(bozan(b)), pair=f"B{ad}/USDT"))
    assert not bool(bos["signal"].iloc[-1]) and bos["setup"].iloc[-1] is None


def test_pivot_onay_gecikmesi_yalniz_t_eksi_2():
    """Pivot i ancak i+2 kapanisinda bilinir: son mum eklenmeden (t = i+1) pivot yok; t = i+2'de var."""
    b, wp = _ornek("YATAY")
    df = df_of(b)
    ham = K._Ham(df.iloc[:wp[2] + 2])                   # t = T2 + 1
    HI, _ = ham.gorunum("long").pivotlar()
    assert wp[2] not in HI and wp[0] in HI
    ham = K._Ham(df.iloc[:wp[2] + 3])                   # t = T2 + 2
    assert wp[2] in ham.gorunum("long").pivotlar()[0]


def test_yatay_ilk_kirilim_yalniz_bir_kez():
    """Kirilimdan sonraki mumlarda (seviye ustunde kalinca) YATAY yeniden tetiklemez."""
    b, wp = _ornek("YATAY")
    b = b + [(112.5, 113.6, 112.5, 113.5)]
    assert _bul("YATAY", df_of(b[:-1]), "long") is not None
    assert _bul("YATAY", df_of(b), "long") is None


# ------------------------------------------------------------------------------------------------ rastgele yuruyus
def _tara_toplam(kod, n, seed, vol):
    o, h, l, c = rw(n, seed, vol)
    return tara(gf1, kod, o, h, l, c, atr_of(o, h, l, c), 40, n - 1)


def _esdeger(v3, kod, v3kod, o, h, l, c):
    """Bir seride kutuphane ile `gercek_sinyaller` ayni (t, yon, stop, hedef) mi; eslesen sinyal sayisini dondurur."""
    n = len(c)
    a = atr_of(o, h, l, c)
    Fd = {yon: v3.ozellik({"t": np.arange(n), "o": o, "h": h, "l": l, "c": c, "v": np.ones(n)}, yon) for yon in (1, -1)}
    ref = {}
    for t, d, sp, sa, ha, et in v3.gercek_sinyaller(v3kod, Fd):
        if 40 <= t <= n - 2:
            ref[(t, d)] = (sp["stop"], sp["hedef"])
    lib = tara(gf1, kod, o, h, l, c, a, 40, n - 2)
    lib_n = {}
    for (t, yon), r in lib.items():
        cc = c[t] if yon == 1 else -c[t]
        hh = r["hedef"] if r["hedef"] is not None else cc + 2 * (cc - r["stop"])
        lib_n[(t, yon)] = (yon * r["stop"], yon * hh)
    ikili = {t for (t, y) in lib_n if (t, -y) in lib_n}                     # iki yonlu mumda aday yok (motor)
    f = lambda d: {k: v for k, v in d.items() if k[0] not in ikili}        # noqa: E731
    assert f(ref).keys() == f(lib_n).keys(), (kod, sorted(set(f(ref)) ^ set(f(lib_n)))[:10])
    for k in f(ref):
        assert f(ref)[k][0] == pytest.approx(f(lib_n)[k][0], rel=1e-9), (kod, k)
        assert f(ref)[k][1] == pytest.approx(f(lib_n)[k][1], rel=1e-9), (kod, k)
    return len(f(ref))


@pytest.mark.parametrize("kod,v3kod,ornek", [("YATAY", "FOR_YATAY_KIRILIM", "YATAY"), ("UCGEN", "FOR_UCGEN", "UCGEN_S"),
                                              ("IKILI", "FOR_IKILI_DIP", "IKILI"), ("OBO", "FOR_OBO", "OBO")])
def test_setuplar_v3_esdegerligi(kod, v3kod, ornek):
    """Rastgele yuruyuste ve sentetik orneklerde (long + aynasi) her t icin kutuphane sonucu `gercek_sinyaller` ile ayni."""
    v3 = referans()
    toplam = 0
    for seed, vol in ((7, 0.012), (21, 0.02), (33, 0.008), (5, 0.015), (8, 0.01), (9, 0.025)):
        o, h, l, c = rw(3500, seed, vol)
        toplam += _esdeger(v3, kod, v3kod, o, h, l, c)
    assert toplam >= (1 if kod == "OBO" else 5), (kod, toplam)
    b, _ = _ornek(ornek)
    b = b + [(b[-1][3], b[-1][3] + 0.1, b[-1][3] - 0.1, b[-1][3])] * 3          # referans son mumu atlar: kirilimdan sonra birkac mum
    sentetik = 0
    for short in (False, True):                     # sentetik: ornek + kisa onekler; short = fiyat aynasi
        df = df_of(b, short=short)
        sentetik += _esdeger(v3, kod, v3kod, *(df[k].to_numpy() for k in ("open", "high", "low", "close")))
    assert sentetik >= 2, (kod, sentetik)


def test_simetrik_ucgen_kama_trend_ayni_mumda_birlikte_tetiklemez():
    gor = {"sim": 0, "kama": 0, "trend": 0}
    for seed, vol in ((1, 0.01), (2, 0.015), (3, 0.02), (4, 0.012)):
        n = 3000
        o, h, l, c = rw(n, seed, vol)
        a = atr_of(o, h, l, c)
        uc = {k for k, r in tara(gf1, "UCGEN", o, h, l, c, a, 40, n - 1).items() if r["etiket"] == "simetrik_ucgen"}
        ka = set(tara(gf1, "KAMA", o, h, l, c, a, 40, n - 1))
        tr = set(tara(gf1, "TREND", o, h, l, c, a, 40, n - 1))
        assert not (uc & ka) and not (uc & tr) and not (ka & tr)
        gor["sim"] += len(uc)
        gor["kama"] += len(ka)
        gor["trend"] += len(tr)
    assert all(v >= 1 for v in gor.values()), gor


def test_ileriye_bakis_ve_pencere_bagimsizligi():
    """t'den sonraki mumlar degisince t'deki karar degismez; son 600 mumluk pencere ayni adayi verir."""
    n = 3000
    o, h, l, c = rw(n, 11, 0.012)
    a = atr_of(o, h, l, c)
    rng = np.random.default_rng(3)
    toplam = 0
    kes = 1500
    o2, h2, l2, c2 = (x.copy() for x in (o, h, l, c))
    for x in (o2, h2, l2, c2):
        x[kes + 1:] = x[kes + 1:] * rng.uniform(0.5, 1.5, n - kes - 1)
    a2 = atr_of(o2, h2, l2, c2)
    for kod in KODLAR:
        tam = tara(gf1, kod, o, h, l, c, a, 40, n - 1)
        toplam += len(tam)
        deg = tara(gf1, kod, o2, h2, l2, c2, a2, 40, kes)
        onc = {k: v for k, v in tam.items() if k[0] <= kes}
        assert deg.keys() == onc.keys(), kod
        for k in onc:
            assert deg[k]["stop"] == pytest.approx(onc[k]["stop"], abs=1e-9)
        pen = tara(gf1, kod, o[-600:], h[-600:], l[-600:], c[-600:], atr_of(o[-600:], h[-600:], l[-600:], c[-600:]), 250, 599)
        gercek = {k: v for k, v in tam.items() if k[0] >= n - 600 + 250}
        assert {(t + n - 600, y) for (t, y) in pen} == set(gercek), kod
        for (t, y), v in pen.items():
            assert v["stop"] == pytest.approx(gercek[(t + n - 600, y)]["stop"], abs=1e-6)
    assert toplam > 40


def test_hic_bir_dedektor_ders_parametresi_okumaz():
    import re
    src = (ROOT / "src" / "trader_engine" / "strategies" / "arms" / "gf1.py").read_text(encoding="utf-8")
    assert re.search(r"\bparams\.\w", src) is None and "SignalParams" not in src


def test_kesif_13_formasyon_sanal_kurulum():
    ls = arms.list_arms()
    assert "GF1" not in ls
    assert sorted(s for s in ls if s.startswith("GF1-")) == sorted(f"GF1-{k}" for k in KODLAR)
    for k in KODLAR:
        m = arms.find_arm(f"GF1-{k}")
        assert m.TIMEFRAMES == TFS and m.CORE is False and m.EXIT_MODE == "target"
        assert arms.priority_of(f"GF1-{k}") == 200 + gf1.FORMASYONLAR[k].sira
        assert arms.time_stop_of(f"GF1-{k}") == 48 and arms.exit_rule_of(f"GF1-{k}") is None
    assert sorted(gf1.FORMASYONLAR[k].sira for k in KODLAR) == list(range(1, 14))
    assert [k for k in sorted(KODLAR, key=lambda k: gf1.FORMASYONLAR[k].sira)] == [
        "OBO", "UCLU", "KUPA", "IKILI", "KAMA", "UCGEN", "BAYRAK", "FLAMA", "RETEST", "SAHTE", "TREND", "KANAL", "YATAY"]
    for s in ("T1", "R1", "TF1", "B1", "H2", "S1", "F1"):
        assert arms.priority_of(s) < 200


def test_hiz_5000_mum_13_formasyon():
    o, h, l, c = rw(5000, 5)
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0},
                      index=pd.date_range("2026-01-01", periods=5000, freq="1h", tz="UTC"))
    for kod in KODLAR:
        arms.find_arm(f"GF1-{kod}").compute(core_inp(df, pair="GHIZ/USDT"))
    en_iyi = 1e9
    for r in range(3):
        inp = core_inp(df.copy(), pair=f"GHIZ{r}/USDT")
        t0 = time.perf_counter()
        for kod in KODLAR:
            arms.find_arm(f"GF1-{kod}").compute(inp)
        en_iyi = min(en_iyi, time.perf_counter() - t0)
    assert en_iyi < 0.1, en_iyi


# ------------------------------------------------------------------------------------------------ kagit = canli
def _cfg(ad):
    return json.loads((ROOT / "config" / ad).read_text(encoding="utf-8"))


def test_kagit_canli_ayni_ve_gf1_52_kimlik():
    p, l = _cfg("engine.paper.json"), _cfg("engine.live.json")
    for k in ("arms",):
        assert p[k] == l[k], k
    lib = [a for a in p["arms"] if a.startswith("GF1-")]
    from evren_destek import config_kollari
    beklenen = config_kollari(f"{s}@{tf}" for s in sorted(a for a in arms.list_arms() if a.startswith("GF1-")) for tf in TFS)
    assert sorted(lib) == sorted(beklenen) and len(lib) == 39 and len(set(p["arms"])) == len(p["arms"])
    for ad in ("engine.paper.json", "engine.live.json"):
        cfg = C.load_cli_config(ROOT / "config", "learner", ad.split(".")[1])
        assert all(a in cfg.arms for a in beklenen)


def test_telegram_adlari_gf1():
    from trader_core import tg_sade
    for k in KODLAR:
        ad = tg_sade.kurulum_adi(f"GF1-{k}@1h")
        assert ad.startswith("Grafik: ") and ad != f"GF1-{k}", k
