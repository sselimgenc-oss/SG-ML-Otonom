"""MF1/GF1/IN1 arastirma geri testi birim testleri (ag gerekmez; hepsi gecmeli)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calistir as CA  # noqa: E402
import gostergeler as G  # noqa: E402
import kol_sinyalleri as KS  # noqa: E402
import metrikler as MT  # noqa: E402
import ozellikler as OZ  # noqa: E402
import simulasyon as SM  # noqa: E402

H = 3600 * 10**9
T0 = 19702 * 86400 * 10**9          # 2023-... pazartesi 00:00 UTC (gun siniri ve hafta basi hizali)
SIFIR = (0.0, 0.0, 0.0, 0.0)


def seri(c, rng=None, v=None, t0=T0, step=H):
    c = np.asarray(c, float)
    n = len(c)
    o = np.r_[c[0], c[:-1]]
    r = np.full(n, 0.5) if rng is None else np.asarray(rng, float)
    return {"t": t0 + np.arange(n, dtype="int64") * step, "o": o, "h": np.maximum(o, c) + r / 2, "l": np.minimum(o, c) - r / 2, "c": c,
            "v": np.ones(n) if v is None else np.asarray(v, float)}


def yol(pts):
    out = [pts[0][1]]
    for (i0, y0), (i1, y1) in zip(pts[:-1], pts[1:]):
        out += list(np.linspace(y0, y1, i1 - i0 + 1)[1:])
    return np.array(out)


def sinyal(D, kol, cfg, yon=1, ust=None, fon=None, tf="1h"):
    F = OZ.ozellik(D, tf, ust or {}, fon, yon)
    ham, fn = KS.KOLLAR[kol]
    return F, fn(F, ham(F), cfg)


def cfg(**kw):
    c = dict(KS.CFG_HIC)
    c.update(kw)
    return c


# ------------------------------------------------------------------------------------------------ gostergeler
def test_ema_elle():
    e = G.ema(np.arange(1.0, 11.0), 3)
    assert np.isnan(e[:2]).all()
    np.testing.assert_allclose(e[2:], np.arange(2.0, 10.0))   # tohum SMA=2, alfa 0,5


def test_atr_wilder_elle():
    h = np.array([10, 12, 13, 15, 14.0])
    l = np.array([8, 9, 11, 12, 10.0])
    c = np.array([9, 11, 12, 14, 11.0])
    a = G.atr(h, l, c, 3)
    assert np.isnan(a[:2]).all()
    np.testing.assert_allclose(a[2:], [7 / 3, 23 / 9, 82 / 27])   # TR = 2,3,2,3,4


def test_rsi_wilder_bilinen():
    # Wilder/StockCharts ornegi; tablodaki 70,53 yuvarlanmis ara degerlerden gelir, tam hesap 70,46 (bagimsiz saf-python referansla da dogrulanir)
    c = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
    r = G.rsi(c, 14)
    assert np.isnan(r[:14]).all()
    np.testing.assert_allclose(r[14:], [70.53, 66.32, 66.55, 69.41, 66.36, 57.97], atol=0.1)
    d = np.diff(c)
    ag, al = np.mean(np.maximum(d[:14], 0)), np.mean(np.maximum(-d[:14], 0))      # saf-python Wilder referansi
    ref = [100 - 100 / (1 + ag / al)]
    for x in d[14:]:
        ag, al = (ag * 13 + max(x, 0)) / 14, (al * 13 + max(-x, 0)) / 14
        ref.append(100 - 100 / (1 + ag / al))
    np.testing.assert_allclose(r[14:], ref, atol=1e-9)


def test_rsi_uclar():
    assert G.rsi(np.arange(1.0, 30.0))[-1] == 100.0
    assert G.rsi(np.arange(30.0, 1.0, -1))[-1] == 0.0


def test_macd_dogrusal_seri():
    m, s, h = G.macd(np.arange(100.0))
    # dogrusal seride EMA gecikmesi (n-1)/2: macd = 12,5 - 5,5 = 7
    np.testing.assert_allclose(m[~np.isnan(m)], 7.0, atol=1e-9)
    np.testing.assert_allclose(s[~np.isnan(s)], 7.0, atol=1e-9)
    np.testing.assert_allclose(h[~np.isnan(h)], 0.0, atol=1e-9)
    assert np.isnan(m[:25]).all() and not np.isnan(m[25])
    assert np.isnan(s[:33]).all() and not np.isnan(s[33])


def test_pivot_ve_kesinlesme():
    l = np.array([5, 4, 3, 2, 1, 0, 1, 2, 3, 4, 5], float)   # tek dip idx 5 (sol 5 daha yuksek, sag 3 daha yuksek)
    p = G.pivot_dip(l)
    assert np.flatnonzero(p).tolist() == [5]
    idx, val = G.kesinlesmis_son(p, l)
    assert (idx[:8] == -1).all()            # 5+3=8'e kadar bilinmez
    assert idx[8] == 5 and val[8] == 0.0
    tp = G.pivot_tepe(-l)
    assert np.flatnonzero(tp).tolist() == [5]


# ------------------------------------------------------------------------------------------------ ileriye bakis
def _rastgele_seri(n, tohum, tf_ns=H, t0=T0):
    rg = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rg.normal(0, 0.006, n)))
    o = np.r_[c[0], c[:-1]]
    return {"t": t0 + np.arange(n, dtype="int64") * tf_ns, "o": o, "h": np.maximum(o, c) * (1 + rg.uniform(0, 0.004, n)),
            "l": np.minimum(o, c) * (1 - rg.uniform(0, 0.004, n)), "c": c, "v": rg.uniform(1, 3, n)}


def _boz(D, bas, tohum=7):
    """bas indeksinden sonrasini bozar (fiyat ve hacim)."""
    rg = np.random.default_rng(tohum)
    E = {k: v.copy() for k, v in D.items()}
    n = len(E["t"])
    sh = rg.normal(0, 0.05, n - bas)
    for k in ("o", "h", "l", "c"):
        E[k][bas:] = E[k][bas:] * (1 + 0.08 + sh)
    E["l"][bas:] = np.minimum(E["l"][bas:], E["c"][bas:] * 0.97)
    E["h"][bas:] = np.maximum(E["h"][bas:], E["c"][bas:] * 1.02)
    E["v"][bas:] *= 5
    return E


def _esit(a, b):
    return np.array_equal(np.asarray(a), np.asarray(b), equal_nan=True) if np.asarray(a).dtype.kind == "f" else np.array_equal(a, b)


def test_gelecek_degisince_t_sinyali_degismez():
    n, t0i = 1600, 1000
    D = _rastgele_seri(n, 3)
    U4 = _rastgele_seri(n // 4 + 5, 4, 4 * H)
    fon = {"t": T0 + np.arange(0, n, 8, dtype="int64") * H, "r": np.random.default_rng(5).normal(0.0002, 0.0004, len(range(0, n, 8)))}
    karar = D["t"][t0i] + H                       # t0i mumunun kapanisi
    E = _boz(D, t0i + 1)
    ub = int(np.searchsorted(U4["t"] + 4 * H, karar, side="right"))   # kapanmis ust mumlar [0, ub); acik/gelecek mumlar bozulur
    E4 = _boz(U4, ub)
    fb = int(np.searchsorted(fon["t"], karar, side="right"))
    fon2 = {"t": fon["t"], "r": fon["r"].copy()}
    fon2["r"][fb:] = 0.01
    topla = 0
    for yon in (1, -1):
        F1 = OZ.ozellik(D, "1h", {"4h": U4}, fon, yon)
        F2 = OZ.ozellik(E, "1h", {"4h": E4}, fon2, yon)
        for k, v1 in F1.items():
            if isinstance(v1, np.ndarray) and v1.shape == (n,):
                son = t0i - 2 if k in ("piv_dip", "piv_tepe") else t0i + 1      # ham pivot i'de isaretli ama i+3'te bilinir
                assert _esit(v1[:son], F2[k][:son]), f"{k} gelecege bakiyor (yon {yon})"
        # kesinlesmis pivot: t0i'de bilinen son pivot gelecege bagli degil
        assert F1["dip_idx"][t0i] <= t0i - 3 and F1["tepe_idx"][t0i] <= t0i - 3
        for kol in KS.KOLLAR:
            ham, fn = KS.KOLLAR[kol]
            for cf in (KS.CFG_HIC, KS.CFG_TAM):
                s1 = fn(F1, ham(F1), cf)
                s2 = fn(F2, KS.KOLLAR[kol][0](F2), cf)
                k1, k2 = s1[0] <= t0i, s2[0] <= t0i
                assert _esit(s1[0][k1], s2[0][k2]) and _esit(s1[1][k1], s2[1][k2]) and _esit(s1[2][k1], s2[2][k2]), f"{kol} sinyali degisti"
                topla += int(k1.sum())
    assert topla > 0                               # test anlamli: gercekten sinyal uretildi


def test_ust_zd_yalniz_kapanmis_mum_ve_durum():
    n = 400
    D = seri(np.full(n * 4, 100.0))
    up = seri(100 + np.arange(n) * 0.5, t0=T0, step=4 * H)      # surekli yukari
    F = OZ.ozellik(D, "1h", {"4h": up}, None, 1)
    assert F["zd_siki"][-1] and F["zd_gevsek"][-1]
    # acik 4h mum: t anindaki 1h mum 4h mumun ilk saati ise onceki 4h mum kullanilir (o da kapanmis olmali)
    idx, ok = OZ.eslestir(D["t"][:8] + H, OZ.ust_durum(up, "4h"))
    kap = up["t"] + 4 * H
    assert ((kap[idx[ok]]) <= (D["t"][:8] + H)[ok]).all()
    # asagi trend: long yok, short var
    dn = seri(300 - np.arange(n) * 0.5, t0=T0, step=4 * H)
    F = OZ.ozellik(D, "1h", {"4h": dn}, None, 1)
    assert not F["zd_gevsek"][-1]
    Fs = OZ.ozellik(D, "1h", {"4h": dn}, None, -1)
    assert Fs["zd_siki"][-1]


def test_ust_mum_kapanmadan_kullanilmaz():
    # 4h mum [0,4h): 1h karar 3. saatin kapanisi = 4h'de kapanir -> o an kullanilabilir; 2. saatin kapanisinda (3h) kullanilamaz
    ust = {"kapanis": np.array([4 * H, 8 * H], dtype="int64")}
    idx, ok = OZ.eslestir(np.array([3 * H, 4 * H, 7 * H, 8 * H], dtype="int64"), ust)
    assert ok.tolist() == [False, True, True, True] and idx.tolist()[1:] == [0, 0, 1]


def test_onceki_gun_hafta_vwap_hacim():
    n = 24 * 9
    c = np.arange(n, dtype=float) + 100
    D = seri(c, np.full(n, 2.0), np.arange(1.0, n + 1))
    pdl = OZ.onceki_donem(D["t"], D["l"], OZ.GUN_NS, 0, np.minimum)
    assert np.isnan(pdl[:24]).all()
    assert pdl[24] == D["l"][:24].min() and pdl[47] == D["l"][:24].min() and pdl[48] == D["l"][24:48].min()
    pwl = OZ.onceki_donem(D["t"], D["l"], OZ.HAFTA_NS, OZ.PZT_OFSET, np.minimum)
    assert np.isnan(pwl[:168]).all() and pwl[168] == D["l"][:168].min()
    vw = OZ.hafta_vwap(D["t"], D["h"], D["l"], D["c"], D["v"])
    assert np.isnan(vw[0])
    tp = (D["h"] + D["l"] + D["c"]) / 3
    np.testing.assert_allclose(vw[2], (tp[0] * 1 + tp[1] * 2) / 3)
    np.testing.assert_allclose(vw[170], (tp[168] * D["v"][168] + tp[169] * D["v"][169]) / (D["v"][168] + D["v"][169]))   # yeni hafta
    vr = OZ.hacim_orani(D["v"])
    np.testing.assert_allclose(vr[20], D["v"][20] / D["v"][:20].mean())
    assert np.isnan(vr[19])


def test_fonlama_veto():
    D = seri(np.full(40, 100.0))
    fon = {"t": np.array([T0 + 8 * H, T0 + 16 * H, T0 + 24 * H], dtype="int64"), "r": np.array([0.0001, 0.0006, -0.0006])}
    v = OZ.fonlama_veto(D["t"], "1h", fon, 1)
    assert not v[14]                 # karar 15h kapanisi: son fonlama 8h (0,0001)
    assert v[15]                     # karar 16h: 16h fonlamasi (+%0,06) kesinlesmis -> long veto
    s = OZ.fonlama_veto(D["t"], "1h", fon, -1)
    assert not s[15] and s[23]       # 24h kapanisinda -%0,06 -> short veto
    assert not OZ.fonlama_veto(D["t"], "1h", None, 1).any()
    assert not OZ.fonlama_veto(D["t"] + 100 * H, "1h", fon, 1).any()   # bayat veri -> veto yok


# ------------------------------------------------------------------------------------------------ simulasyon
def _d(o, h, l, c):
    n = len(o)
    return {"t": T0 + np.arange(n, dtype="int64") * H, "o": np.array(o, float), "h": np.array(h, float), "l": np.array(l, float),
            "c": np.array(c, float), "v": np.ones(n)}


def test_ayni_mumda_stop_ve_hedef_stop():
    D = _d([100, 100, 100], [100, 102.5, 100], [100, 98.5, 100], [100, 100, 100])
    r = SM.simule(D, 0, 1, 99.0, 102.0, 5, SIFIR, H)
    assert r[1] == 0 and r[0] == pytest.approx(-1.0)
    Ds = _d([100, 100, 100], [100, 101.5, 100], [100, 97.5, 100], [100, 100, 100])
    r = SM.simule(Ds, 0, -1, 101.0, 98.0, 5, SIFIR, H)      # short: ayni mumda ikisi
    assert r[1] == 0 and r[0] == pytest.approx(-1.0)


def test_bosluk_dolumu():
    D = _d([100, 100, 97, 97], [100, 100.5, 97.5, 97], [100, 99.5, 96.5, 97], [100, 100, 97, 97])
    r = SM.simule(D, 0, 1, 99.0, 105.0, 5, SIFIR, H)
    assert r[1] == 0 and r[0] == pytest.approx(-3.0)          # acilistan (97) dolum
    Dg = _d([100, 100, 106, 106], [100, 100.5, 107, 106], [100, 99.5, 105.5, 106], [100, 100, 106, 106])
    r = SM.simule(Dg, 0, 1, 99.0, 105.0, 5, SIFIR, H)
    assert r[1] == 1 and r[0] == pytest.approx(6.0)           # yukari bosluk: acilistan hedef dolumu
    Dk = _d([100, 98.5, 98], [100, 99, 98], [100, 98, 97], [100, 98.5, 98])
    assert SM.simule(Dk, 0, 1, 99.0, 105.0, 5, SIFIR, H) is None   # giris acilisi stopun altinda: islem yok


def test_zaman_stopu_ve_veri_sonu():
    c = [100, 100, 100.2, 100.4, 100.6, 100.8, 101.0]
    D = _d(c, [x + 0.1 for x in c], [x - 0.1 for x in c], c)
    r = SM.simule(D, 0, 1, 99.0, 110.0, 3, SIFIR, H)           # giris bar1; 3 mum: bar1..3; cikis bar3 kapanisi
    assert r[1] == 2 and r[2] == 3 and r[4] == 3 and r[0] == pytest.approx(0.4)
    # veri bitti, zaman stopuna ulasilamadi -> islem sayilmaz (Tur 2)
    assert SM.simule(D, 4, 1, 99.0, 110.0, 10, SIFIR, H) is None
    # ... ama veri bitmeden stop/hedef gelirse islem sayilir
    r = SM.simule(D, 4, 1, 99.0, 100.9, 10, SIFIR, H)
    assert r[1] == 1 and r[4] == 6


def test_masraf_ve_fonlama_R():
    D = _d([100, 100, 100, 100], [100, 102.2, 100, 100], [100, 99.5, 100, 100], [100, 102, 100, 100])
    mal = (0.0005, 0.0002, 0.0002, 0.0005)
    r = SM.simule(D, 0, 1, 99.0, 102.0, 5, mal, H)
    giris, cik = 100 * 1.0002, 102 * 0.9998
    beklenen = ((cik - giris) - 0.0005 * (giris + cik)) / (giris - 99.0)
    assert r[1] == 1 and r[0] == pytest.approx(beklenen)
    # fonlama cikis mumunun KAPANISINA kadar sayilir: giris/cikis ayni mum (T0+1h..T0+2h), odeme T0+2h (kapanis) -> long oder (Tur 2)
    fonh = SM.fonlama_hazirla({"t": np.array([T0 + 2 * H], dtype="int64"), "r": np.array([0.001])})
    assert SM.simule(D, 0, 1, 99.0, 102.0, 5, SIFIR, H, fonh)[5] == pytest.approx(-0.001 * 100 / 1.0)
    fonh = SM.fonlama_hazirla({"t": np.array([T0 + 2 * H + 1], dtype="int64"), "r": np.array([0.001])})     # kapanistan sonra: yok
    assert SM.simule(D, 0, 1, 99.0, 102.0, 5, SIFIR, H, fonh)[5] == 0.0
    # cikis bar 3'te (zaman stopu): fonlama T0+2h ve T0+3h icinde -> long oder
    D2 = _d([100, 100, 100, 100], [100, 100.5, 100.5, 100.5], [100, 99.5, 99.5, 99.5], [100, 100, 100, 100])
    fonh = SM.fonlama_hazirla({"t": np.array([T0 + 2 * H, T0 + 3 * H], dtype="int64"), "r": np.array([0.001, 0.001])})
    r = SM.simule(D2, 0, 1, 99.0, 110.0, 3, SIFIR, H, fonh)
    assert r[5] == pytest.approx(-0.002 * 100 / 1.0) and r[0] == pytest.approx(-0.2)     # cikis T0+4h kapanisi; T0+2h ve T0+3h odemeleri
    r = SM.simule(D2, 0, -1, 101.0, 90.0, 3, SIFIR, H, fonh)     # short ayni fonlamayi alir
    assert r[5] == pytest.approx(0.2)


def test_min_risk_ve_tutma_penceresi_boslugu():
    D = _d([100] * 6, [101] * 6, [99] * 6, [100] * 6)
    assert SM.simule(D, 0, 1, 99.5, 103.0, 3, SIFIR, H, None, 0.006) is None        # risk %0,5 < %0,6
    assert SM.simule(D, 0, 1, 99.0, 103.0, 3, SIFIR, H, None, 0.006) is not None    # risk %1
    Dg = _d([100] * 6, [101] * 6, [99] * 6, [100] * 6)
    Dg["t"][3:] += H                                # bar 3'ten itibaren bosluk: pencere 1..3 icinde
    assert SM.simule(Dg, 0, 1, 98.0, 103.0, 3, SIFIR, H) is None
    assert SM.simule(Dg, 0, 1, 98.0, 103.0, 2, SIFIR, H) is not None               # pencere 1..2: bosluk disinda


def test_bosluklu_veri_giris_yok():
    D = _d([100, 100, 100], [101] * 3, [99] * 3, [100] * 3)
    D["t"][1] += H                                  # t+1 mumu ardisik degil
    assert SM.simule(D, 0, 1, 98.0, 103.0, 3, SIFIR, H) is None


def test_ayni_cift_kol_acik_pozisyon_varken_yeni_giris_yok():
    c = [100] * 30
    D = _d(c, [100.1] * 30, [99.9] * 30, c)
    # (t, -yon, yon, stop, hedef, sa, ha): ilk islem bar1..4 (zaman stopu 4), 2. sinyal t=2 (acik) atlanir, 3. t=4 (cikis mumu) girer
    sig = [(0, -1, 1, 99.0, 105.0, 1, 5), (2, -1, 1, 99.0, 105.0, 1, 5), (4, -1, 1, 99.0, 105.0, 1, 5)]
    rows = CA.islem_dongusu(D, sig, 4, SIFIR, H, None, 0)
    assert [r[4] // H - T0 // H for r in rows] == [1, 5]


# ------------------------------------------------------------------------------------------------ kol sentetik ornekleri
def _mf1_seri(c_son=97.0, o_son=96.6, l_son=94.8, v_son=3.0):
    i = np.arange(60)
    D = seri(100 + 3 * np.sin(i * 2 * np.pi / 12), np.full(60, 1.0))
    for k, x in (("o", o_son), ("h", max(o_son, c_son) + 0.15), ("l", l_son), ("c", c_son), ("v", v_son)):
        D[k] = np.r_[D[k], x]
    D["t"] = np.r_[D["t"], D["t"][-1] + H]
    for k, x in (("o", c_son), ("h", c_son + 0.3), ("l", c_son - 0.3), ("c", c_son + 0.2), ("v", 1.0)):   # giris mumu
        D[k] = np.r_[D[k], x]
    D["t"] = np.r_[D["t"], D["t"][-1] + H]
    return D


def test_mf1_cekic_seviyede():
    D = _mf1_seri()
    F, s = sinyal(D, "MF1", cfg(seviye=True, maliyet=True))
    assert s[0].tolist() == [60] and s[3].tolist() == ["pdl"]       # seviye turu: onceki gun dibi
    assert s[1][0] == pytest.approx(94.8 - 0.2 * F["atr"][60]) and s[2][0] == pytest.approx(103.5)   # stop = dip - 0,2 ATR; hedef = onceki gun tepesi (3R'den yakin)
    # Tur 2: hacim teyidi yok -> dusuk hacimde de sinyal var
    assert sinyal(_mf1_seri(v_son=1.0), "MF1", KS.CFG_TAM)[1][0].tolist() == [60]
    # delme 1 ATR'den derin (dip 93,5; seviye 96,5; ATR 2,18) -> seviye teyidi keser, kapaliyken var
    Dd = _mf1_seri(l_son=93.5)
    assert len(sinyal(Dd, "MF1", cfg(seviye=True))[1][0]) == 0 and sinyal(Dd, "MF1", cfg())[1][0].tolist() == [60]
    # kapanis seviyenin altinda (pdl 96,5): seviye teyidi sinyali keser
    Ds = _mf1_seri(c_son=96.3, o_son=96.0, l_son=93.4)
    assert len(sinyal(Ds, "MF1", cfg(seviye=True))[1][0]) == 0 and sinyal(Ds, "MF1", cfg())[1][0].tolist() == [60]
    # hammer degil (govde buyuk) -> sekil yok
    Dh = _mf1_seri(c_son=97.0, o_son=94.0, l_son=93.5)
    assert len(sinyal(Dh, "MF1", cfg())[1][0]) == 0


def test_mf1_ust_zd_teyidi_yok_fonlama_vetosu_var():
    D = _mf1_seri()
    dn = seri(300 - np.arange(300) * 0.5, t0=T0 - 400 * 4 * H + 60 * H, step=4 * H)
    assert sinyal(D, "MF1", KS.CFG_TAM, ust={"4h": dn})[1][0].tolist() == [60]     # ust asagi trend olsa da MF1'de filtre yok
    fon = {"t": np.array([D["t"][50]], dtype="int64"), "r": np.array([0.0008])}
    assert len(sinyal(D, "MF1", cfg(fonlama=True), fon=fon)[1][0]) == 0
    assert "zd" not in KS.UYGULANAN["MF1"] and "hacim" not in KS.UYGULANAN["MF1"]


def test_mf1_hedef_3R_siniri():
    D = _mf1_seri()
    F, s = sinyal(D, "MF1", cfg())
    risk = F["c"][60] - s[1][0]
    assert s[2][0] == pytest.approx(103.5) and 103.5 < F["c"][60] + 3 * risk     # karsi seviye daha yakin
    # karsi seviyeyi uzaklastir: hedef giris + 3R (ham hedef 130 olsa da)
    F2 = OZ.ozellik(D, "1h", {}, None, 1)
    ham = KS.mf1_ham(F2)
    ham["hedef"] = np.full(F2["n"], 130.0)
    s2 = KS.mf1_sinyal(F2, ham, cfg())
    r2 = F2["c"][60] - s2[1][0]
    assert s2[0].tolist() == [60] and s2[2][0] == pytest.approx(F2["c"][60] + KS.HEDEF_R_MF1 * r2)


def test_mf1_seviye_formasyondan_once_bilinen_deger():
    # 1d'de onceki gun dibi listede yok; seviye zaman kaymali alinir (yutan t-2, cekic t-1, yildiz t-3)
    D = seri(np.full(300, 100.0))
    D = {k: v for k, v in D.items()}
    F = OZ.ozellik({"t": T0 + np.arange(300, dtype="int64") * 86400 * 10**9, "o": D["o"], "h": D["h"], "l": D["l"], "c": D["c"], "v": D["v"]}, "1d", {}, None, 1)
    assert F["seviye_adlari"] == ["pwl", "vwap", "kendi_pivot"] and len(F["seviyeler"]) == 3
    F1 = OZ.ozellik(_mf1_seri(), "1h", {}, None, 1)
    assert F1["seviye_adlari"][:3] == ["pdl", "pwl", "vwap"]
    ham = KS.mf1_ham(F1)
    assert [x["ad"] for x in ham["sekiller"]] == ["yutan", "cekic", "yildiz"]


def test_mf1_maliyet_tabani_ve_rr():
    D = _mf1_seri(c_son=97.0, o_son=96.99, l_son=96.5)           # dar mum: stop mesafesi < %0,6 (ve aralik < ATR)
    assert len(sinyal(D, "MF1", cfg(maliyet=True))[1][0]) == 0
    Dr = _mf1_seri(l_son=92.0)                                   # stop cok asagida: rr < 1,5
    assert len(sinyal(Dr, "MF1", cfg())[1][0]) == 0


def _in1_seri(ikinci=79.5, v=3.0):
    c = yol([(0, 100), (30, 100), (36, 80), (42, 92), (56, ikinci), (62, 86)])
    vol = np.ones(len(c))
    vol[59:63] = v
    return seri(c, np.full(len(c), 1.0), vol)


def test_in1_uyumsuzluk_sinyali():
    D = _in1_seri()
    F, s = sinyal(D, "IN1", KS.CFG_HIC)
    assert s[0].tolist() == [59] and s[3].tolist() == ["gevsek_eslesme"]            # pivot 56 + 3
    assert F["rsi"][36] < 35 and F["rsi"][56] >= F["rsi"][36] + 3 and F["mh"][56] > F["mh"][36]
    assert s[1][0] == pytest.approx(F["l"][56] - 0.3 * F["atr"][59]) and s[2][0] == pytest.approx(92.5)   # hedef: aradaki tepe pivotu
    # Tur 2: seviye ve hacim teyidi yok: seviyede olmayan ikinci dip ve dusuk hacim de sinyal verir
    c_ = cfg(fonlama=True, maliyet=True, seviye=True, hacim=True)           # (ust ZD verisi yok: zd kapali)
    assert sinyal(_in1_seri(v=1.0), "IN1", c_)[1][0].tolist() == [59]
    assert sinyal(_in1_seri(ikinci=79.0), "IN1", c_)[1][0].tolist() == [59]
    assert "seviye" not in KS.UYGULANAN["IN1"] and "hacim" not in KS.UYGULANAN["IN1"]


def test_in1_gevsek_eslesme_ardisik_olmayan_dip():
    # 36'daki derin dip (RSI<35) ile 56 arasinda, ara dip pivotu (46; 5 mumdan fazla uzak, ama kosulu saglamaz) var: eski kod yalniz 46'yi denerdi
    c = yol([(0, 100), (30, 100), (36, 80), (42, 92), (46, 87), (47, 89), (52, 93), (56, 78.5), (62, 86)])
    D = seri(c, np.full(len(c), 1.0))
    F = OZ.ozellik(D, "1h", {}, None, 1)
    LI = np.flatnonzero(F["piv_dip"]).tolist()
    assert 36 in LI and 46 in LI and 56 in LI
    ev = KS.in1_ham(F)["ev"]
    assert [e[0] for e in ev] == [56]                              # 36 ile eslesti (46 ile degil)
    assert ev[0][2] == pytest.approx(F["h"][52])                   # aradaki en yuksek tepe pivotu
    # 40 mumdan uzak dip eslesmez
    c2 = yol([(0, 100), (30, 100), (36, 80), (42, 92), (90, 79.5), (96, 86)])
    F2 = OZ.ozellik(seri(c2, np.full(len(c2), 1.0)), "1h", {}, None, 1)
    assert KS.in1_ham(F2)["ev"] == []


def test_in1_fiyat_dususu_yoksa_ya_da_rsi_uyumsuz_degilse_sinyal_yok():
    c = yol([(0, 100), (30, 100), (36, 80), (42, 92), (56, 85), (62, 90)])     # ikinci dip daha yuksek: uyumsuzluk degil
    D = seri(c, np.full(len(c), 1.0))
    assert len(sinyal(D, "IN1", KS.CFG_HIC)[1][0]) == 0


def _gf1_tobo(v77=3.0):
    pts = [(0, 104), (6, 100), (14, 103), (24, 94), (36, 103), (66, 101), (72, 102.5), (76, 103), (77, 105.6), (90, 108)]
    c = yol(pts)
    n = len(c)
    v = np.ones(n)
    v[77] = v77
    return seri(c, np.linspace(3.2, 1.2, n), v)


def test_gf1_tobo_kirilim():
    D = _gf1_tobo()
    F, s = sinyal(D, "GF1", KS.CFG_HIC)
    assert s[0].tolist() == [77]
    kur = KS.gf1_ham(F)["kur"]
    assert {k[4] for k in kur} >= {"tobo"}
    tobo = [k for k in kur if k[4] == "tobo"][0]
    assert tobo[0] == 69 and tobo[1] == pytest.approx(max(F["h"][14], F["h"][36])) and tobo[3] == pytest.approx(tobo[1] + (tobo[1] - F["l"][24]))
    assert tobo[2] == pytest.approx(F["l"][66] - 0.2 * F["atr"][69])                  # iptal seviyesi (dip - 0,2 ATR)
    assert s[1][0] == pytest.approx(tobo[1] - F["atr"][77]) and s[2][0] == pytest.approx(tobo[3])   # Tur 2: stop = boyun - 1 ATR
    assert s[3].tolist() == ["tobo"]
    # hacim teyidi: kirilim mumunda hacim yoksa A girisi olmaz (77'de giris yok)
    assert 77 not in sinyal(_gf1_tobo(v77=1.0), "GF1", cfg(hacim=True))[1][0].tolist()
    assert sinyal(D, "GF1", cfg(hacim=True))[1][0].tolist() == [77]


def test_gf1_sahte_kirilim_iptal_ve_stop_alti():
    D = _gf1_tobo()
    # kirilimdan hemen sonra boyun altinda kapanis: kurulum iptal, 78'den sonra giris yok
    for k in ("o", "h", "l", "c"):
        D[k] = D[k].copy()
    D["c"][78] = 103.0
    D["h"][78], D["l"][78], D["o"][78] = 105.7, 102.5, 105.6
    D["o"][79] = 103.0
    D["h"][79], D["l"][79], D["c"][79] = 106.2, 103.0, 106.0
    c2 = sinyal(D, "GF1", cfg(hacim=True))[1][0].tolist()
    assert c2 == [77]                                 # A girisi 77'de; sonrasi onemsiz
    D3 = _gf1_tobo(v77=1.0)
    D3["c"][78] = 103.0
    D3["l"][78] = 102.5
    assert 78 not in sinyal(D3, "GF1", cfg(hacim=True))[1][0].tolist()


def test_gf1_ikili_dip_kurulumu_ve_rr_filtresi():
    pts = [(0, 104), (8, 108), (14, 100), (24, 110), (34, 100), (44, 108), (50, 111), (52, 112), (60, 118), (70, 125)]
    c = yol(pts)
    D = seri(c, np.linspace(2.0, 0.6, len(c)), np.ones(len(c)))
    F, s = sinyal(D, "GF1", KS.CFG_HIC)
    kur = KS.gf1_ham(F)["kur"]
    assert [k[4] for k in kur] == ["ikili_dip"]
    t0, boyun, stop, hedef, _ = kur[0]
    assert t0 == 37 and boyun == pytest.approx(F["h"][24]) and hedef == pytest.approx(boyun + (boyun - min(F["l"][14], F["l"][34])))
    assert len(s[0]) == 0        # bu seride kirilimdan sonra geri test ve A girisi yok (kirilim mumlari ust ceyrekte kapanmiyor)


def _gf1_ikili_dip_cikis(c58):
    pts = [(0, 104), (8, 108), (14, 100), (24, 110), (34, 100), (44, 108), (50, 112.5), (54, 113.5), (58, c58), (60, 114), (70, 125)]
    c = yol(pts)
    return seri(c, np.linspace(2.0, 0.6, len(c)), np.ones(len(c)))


def test_gf1_ikili_dip_tur2_stop_boyun_eksi_1_atr_islem_acilir():
    # Tur 2 oncesi bu kurulum rr >= 1,5 sartini gecemezdi (stop dibin altinda); simdi stop = boyun - 1 ATR ile islem acilir
    F, s = sinyal(_gf1_ikili_dip_cikis(111.8), "GF1", KS.CFG_HIC)
    assert s[0].tolist() == [59] and s[3].tolist() == ["ikili_dip"]
    boyun = KS.gf1_ham(F)["kur"][0][1]
    assert s[1][0] == pytest.approx(boyun - F["atr"][59]) and s[2][0] == pytest.approx(122.38)
    assert (s[2][0] - F["c"][59]) / (F["c"][59] - s[1][0]) >= KS.RR_MIN


def test_gf1_B_girisi_geri_testi_boyuna_gore_olculur():
    # A (hacim) kapali: yalniz B girebilir. Geri test: low <= boyun (eski kural: boyun + 0,3 ATR)
    kur = lambda D: KS.gf1_ham(OZ.ozellik(D, "1h", {}, None, 1))["kur"][0][1]  # noqa: E731
    D1 = _gf1_ikili_dip_cikis(111.0)       # 59'un low'u boyunun altinda
    F1, s1 = sinyal(D1, "GF1", cfg(hacim=True))
    assert F1["l"][59] <= kur(D1) and 59 in s1[0].tolist()
    D2 = _gf1_ikili_dip_cikis(111.5)       # 59'un low'u boyun ile boyun + 0,3 ATR arasinda -> artik geri test sayilmaz
    F2, s2 = sinyal(D2, "GF1", cfg(hacim=True))
    assert kur(D2) < F2["l"][59] <= kur(D2) + 0.3 * F2["atr"][59] and 59 not in s2[0].tolist()


def test_gf1_ucgen_kurulumu():
    pts = [(0, 100), (10, 110), (20, 100), (30, 110.2), (40, 104), (50, 110.1), (60, 106), (68, 110.2)]
    c = yol(pts)
    D = seri(c, np.linspace(2.5, 0.6, len(c)))
    F = OZ.ozellik(D, "1h", {}, None, 1)
    kur = KS.gf1_ham(F)["kur"]
    assert any(k[4] == "ucgen" for k in kur)


def test_short_long_aynasi():
    K = 300.0
    for kol, Dl in (("IN1", _in1_seri()), ("MF1", _mf1_seri()), ("GF1", _gf1_tobo())):
        Ml = {"t": Dl["t"], "o": K - Dl["o"], "h": K - Dl["l"], "l": K - Dl["h"], "c": K - Dl["c"], "v": Dl["v"]}
        _, sl = sinyal(Dl, kol, KS.CFG_HIC, 1)
        _, ss = sinyal(Ml, kol, KS.CFG_HIC, -1)
        assert len(sl[0]) > 0 and sl[0].tolist() == ss[0].tolist(), kol
        np.testing.assert_allclose(-ss[1], -(sl[1] - K), atol=1e-9)   # gercek stop = K - long stop
        np.testing.assert_allclose(-ss[2], -(sl[2] - K), atol=1e-9)


# ------------------------------------------------------------------------------------------------ metrik / calistirici
def test_metrikler_elle():
    T = {"R": np.array([2.0, -1.0, 1.0, -1.0]), "tur": np.array([1, 0, 2, 0]), "tutma": np.array([4.0, 2.0, 6.0, 2.0]), "cift": np.array([0, 0, 1, 1]),
         "t_giris": np.array([0, 1, 2, 3]) * 10**18, "t_cikis": np.array([1, 2, 3, 4]) * 10**18, "d": np.array([1, 1, -1, -1])}
    m = MT.ozet(T, 1.0, ["A", "B"])
    assert m["islem"] == 4 and m["kazanma_orani"] == 0.5 and m["ort_net_R"] == 0.25 and m["toplam_net_R"] == 1.0
    assert m["kar_faktoru"] == pytest.approx(1.5) and m["en_buyuk_dusus_R"] == pytest.approx(1.0)
    assert m["cikis_turleri"] == {"stop": 2, "hedef": 1, "zaman": 1} and m["ort_tutma_mum"] == 3.5
    assert m["cift_en_iyi5"][0]["cift"] == "A" and m["cift_en_kotu5"][0]["cift"] == "B"
    assert MT.ozet({k: v[:0] for k, v in T.items()}, 1.0, ["A"]) == {"islem": 0}


def test_kilitli_donem_bayraksiz_hata(tmp_path):
    assert CA.main(["--donem", "kilitli", "--cikti", str(tmp_path / "x")]) == 2
    assert not (tmp_path / "x").exists()


def test_ablation_konfig_listesi():
    assert list(KS.cfg_listesi("MF1")) == ["tam", "seviye_kapali", "fonlama_kapali", "maliyet_kapali", "hic_teyit"]
    assert list(KS.cfg_listesi("IN1")) == ["tam", "zd_kapali", "fonlama_kapali", "maliyet_kapali", "hic_teyit"]
    assert "seviye_kapali" not in KS.cfg_listesi("GF1")
    assert not any(KS.cfg_listesi("IN1")["hic_teyit"].values())


# ------------------------------------------------------------------------------------------------ Tur 2: calistirici / olcum
def test_izinli_zaman_dilimleri_tablosu():
    assert CA.IZINLI == {"MF1": ["4h", "1d"], "GF1": ["1h", "4h", "1d"], "IN1": ["1h", "4h"]}
    assert "15m" not in CA.TFLER and not any("15m" in v for v in CA.IZINLI.values())


def test_ust_zd_ema_hazir_degilse_gecersiz():
    D = seri(np.full(40 * 4, 100.0))
    up = seri(100 + np.arange(40) * 0.5, t0=T0, step=4 * H)       # 40 ust mum: EMA50 hazir degil
    F = OZ.ozellik(D, "1h", {"4h": up}, None, 1)
    assert not F["zd_gevsek"].any() and not F["zd_siki"].any()   # 'yatay' sayilip gecmez
    assert not OZ.ust_durum(up, "4h")["gecerli"].any()
    up2 = seri(100 + np.arange(120) * 0.5, t0=T0, step=4 * H)
    g = OZ.ust_durum(up2, "4h")["gecerli"]
    assert not g[:54].any() and g[54:].all()                      # EMA50 (49) + 5 kaydirma


def test_rastgele_taban_ayni_yil_isinma_ve_eslestirme():
    n = 1200
    D = _rastgele_seri(n, 11)
    D["t"] = (np.datetime64("2023-06-01T00:00", "ns").astype("int64") + np.arange(n, dtype="int64") * H)
    atr = G.atr(D["h"], D["l"], D["c"], 14)
    yil = MT.yil_of(D["t"])
    t_gercek = int(D["t"][np.flatnonzero(yil == 2023)[400]])
    rows = [(0.0, 2, 3.0, 0, t_gercek, t_gercek, 1, 1.0, 2.0, "x"), (0.0, 2, 3.0, 0, t_gercek, t_gercek, -1, 1.0, 2.0, "x")]
    rg = np.random.default_rng(1)
    out = CA.rastgele_taban(D, atr, rows, rg, 16, SIFIR, H, None, 0, 0.0)
    assert [o[0] for o in out] == [1, -1] and all(0 < o[1] <= CA.RASTGELE_N for o in out)
    # yalniz 2024'e ait gercek islem: 2024 adayi yok -> n = 0 degil, 2024 mumlari var; 2022 yili icin aday yok -> n = 0
    t2022 = int(np.datetime64("2022-03-01T00:00", "ns").astype("int64"))
    out2 = CA.rastgele_taban(D, atr, [(0.0, 2, 3.0, 0, t2022, t2022, 1, 1.0, 2.0, "x")], rg, 16, SIFIR, H, None, 0, 0.0)
    assert out2[0][1] == 0
    # isinma: ilk 250 mumda giris yok -> tum mumlar ilk 250 ise hic cekilis olmaz
    out3 = CA.rastgele_taban({k: v[:240] for k, v in D.items()}, atr[:240], rows, rg, 16, SIFIR, H, None, 0, 0.0)
    assert all(o[1] == 0 for o in out3)


def test_rastgele_ozet_z_ve_yetersiz():
    rg = np.random.default_rng(0)
    R = rg.normal(0.3, 1.0, 60)
    Rr = np.array([[1, 200, 200 * -0.1, 200 * (0.01 + 1.0)]] * 60, float)    # ort -0,1, varyans ~1
    g = CA.rastgele_ozet(R, Rr)
    assert g["z_durum"] == "ok" and g["fark"] == pytest.approx(R.mean() + 0.1)
    se = np.hypot(R.std(ddof=1) / np.sqrt(60), 1.0 / np.sqrt(60))
    assert g["z"] == pytest.approx(g["fark"] / se, rel=0.01)
    k = CA.rastgele_ozet(R[:49], Rr[:49])
    assert k["z"] is None and k["z_durum"] == "yetersiz" and k["fark"] is not None


def test_etiket_dokumu_ve_islem_dongusu_etiketi():
    D = _d([100] * 30, [100.1] * 30, [99.9] * 30, [100] * 30)
    rows = CA.islem_dongusu(D, [(0, -1, 1, 99.0, 105.0, 1, 5, "tobo")], 4, SIFIR, H, None, 0)
    assert rows[0][9] == "tobo"
    T = CA.satirlar_tablo(rows)
    assert T["etiket"].tolist() == ["tobo"]
    assert CA.islem_dongusu(D, [(0, -1, 1, 99.5, 105.0, 1, 5, "x")], 4, SIFIR, H, None, 0, 0.006) == []    # risk < %0,6
