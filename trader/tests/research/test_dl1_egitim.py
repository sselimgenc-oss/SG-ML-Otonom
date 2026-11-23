"""research/dl1/cekirdek.py: numpy-only kisimlar (torch GEREKTIRMEZ; torch'lu egitim/parite research/dl1/duman.py'de, Actions'ta).
Sentetik veri; ag/gercek veri yok."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import exit_modes as XM
from trader_engine import dl1_cikarim as DL

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "dl1"))
import cekirdek as C  # noqa: E402

H = C.H_NS
UTC = timezone.utc


def _df(n=1500, tohum=1, bas="2025-01-01", sil=None, bos=None):
    rg = np.random.default_rng(tohum)
    t = pd.date_range(bas, periods=n, freq="h", tz="UTC").as_unit("ms")
    c = 100 * np.exp(np.cumsum(rg.normal(0, 0.004, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rg.uniform(0.0005, 0.003, n))
    l = np.minimum(o, c) * (1 - rg.uniform(0.0005, 0.003, n))
    v = rg.uniform(10, 100, n)
    if bos is not None:                       # seans kapali: hacim 0, h == l
        v[bos] = 0.0
    df = pd.DataFrame({"date": t, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return df.drop(index=sil).reset_index(drop=True) if sil is not None else df


# ------------------------------------------------------------------------------------------- kapsam / sinif
def test_sinif_haritasi_43_enstruman():
    m = C.sinif_haritasi()
    assert len(m) == 43
    assert sum(v == 0 for v in m.values()) == 19 and sum(v == 1 for v in m.values()) == 20 and sum(v == 2 for v in m.values()) == 4
    assert m["BTC/USDT"] == 0 and m["NVDA/USDT"] == 1 and m["XAU/USDT"] == 2 and m["COPPER/USDT"] == 2


# ------------------------------------------------------------------------------------------- etiket
def _bariyer(hlist, llist, n=40):
    c = np.full(n, 100.0)
    h = np.full(n, 100.2)
    l = np.full(n, 99.8)
    for k, v in hlist.items():
        h[k] = v
    for k, v in llist.items():
        l[k] = v
    ts = np.arange(n, dtype=np.int64) * H
    atr = np.ones(n)
    return ts, c.copy(), h, l, c, atr


def test_etiket_hedef_once_stop_once_ayni_bar_zaman_asimi():
    ts, o, h, l, c, atr = _bariyer({3: 103.2}, {}, n=100)             # long hedefi 103 (3 ATR); short stopu 101.5 ayni barda vurulur
    ok, y, rb, vol = C.etiketle(ts, o, h, l, c, atr)
    assert ok[0] and y[0].tolist() == [1, 0] and rb[0].tolist() == [2.0, -1.0]
    ts, o, h, l, c, atr = _bariyer({3: 104.0}, {3: 96.0}, n=100)      # ayni barda iki bariyer: stop (muhafazakar)
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert y[0].tolist() == [0, 0] and rb[0].tolist() == [-1.0, -1.0]
    ts, o, h, l, c, atr = _bariyer({}, {}, n=100)                     # hicbiri: zaman asimi, son mumun kapanisi (100) -> R = 0
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert ok[0] and y[0].tolist() == [0, 0] and rb[0].tolist() == [0.0, 0.0]


def test_ufuk_canli_zaman_stopu_ile_ayni_ve_purge_yeterli():
    from trader_core import signals
    from trader_ml.config import HORIZON_BARS
    assert DL.UFUK == signals.TIME_STOP_BARS == 48 and HORIZON_BARS >= DL.UFUK + 24


def test_etiket_ufuk_ve_gozlenmemis_ufuk_gecersiz():
    ts, o, h, l, c, atr = _bariyer({DL.UFUK + 1: 110.0}, {}, n=100)    # ufuktan 1 sonra hedef: sayilmaz
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert y[0, 0] == 0 and rb[0, 0] == 0.0 and y[1, 0] == 1           # bar 1 icin ufuk icinde
    assert not ok[-1] and not ok[-DL.UFUK] and ok[len(ts) - DL.UFUK - 2]


def test_etiket_takvim_boslugu_ufku_asan_mum_sayilmaz():
    ts, o, h, l, c, atr = _bariyer({3: 110.0}, {}, n=100)
    ts = ts.copy()
    ts[3:] += 60 * H                                                   # 3. mumdan once 60 saatlik bosluk (seans): ufuk disinda
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert y[0, 0] == 0


# ------------------------------------------------------------------------------------------- canli cikis simulasyonu
def _sim(hl, ll, modes=None, ol=None, n=80, mal=(0.0, 0.0, 0.0, 0.0), cl=None):
    ts, o, h, l, c, atr = _bariyer(hl, ll, n=n)
    for k, v in (ol or {}).items():
        o[k] = v
    for k, v in (cl or {}).items():
        c[k] = v
    return C.simule_cikis(ts, o, h, l, c, atr, modes, mal)


def test_simule_stop_hedef_ayni_bar_ve_zaman():
    assert _sim({3: 103.2}, {})[0].tolist() == pytest.approx([2.0, -1.0])      # long hedef +2 R, short stop -1 R (maliyetsiz)
    assert _sim({3: 104.0}, {3: 96.0})[0].tolist() == pytest.approx([-1.0, -1.0])   # ayni barda ikisi: stop
    assert _sim({}, {})[0].tolist() == pytest.approx([0.0, 0.0])


def test_simule_bosluk_acilista_dolum():
    # long: stop 98.5; 3. bar 97 acilir (stopun altinda), low 96 -> dolum acilista 97: R = (97-100)/1,5 = -2
    r = _sim({}, {3: 96.0}, ol={3: 97.0})[0]
    assert r[0] == pytest.approx(-2.0)
    # short: stop 101.5; 3. bar 103 acilir -> dolum 103: R = -(103-100)/1,5 = -2
    r = _sim({3: 105.0}, {}, ol={3: 103.0})[0]
    assert r[1] == pytest.approx(-2.0)


def test_simule_basabas_ve_kismi_canli_kipler_gibi():
    m = XM.from_flags(True, True)                    # varsayilan: BE +1 R (stop girise +15 bps), kismi +1,5 R'de %50
    # long: bar 2 yuksek 101.6 (>= +1 R = 101.5) kapanis 100 -> stop 100.15; bar 3 low 100.1 -> 100.15'ten cikis (R = +0,1)
    r = _sim({2: 101.6}, {3: 100.1}, m, ol={3: 100.3})[0, 0]            # 3. bar stopun ustunde acilir -> dolum stop seviyesinde
    assert r == pytest.approx(0.15 / 1.5)
    assert _sim({2: 101.6}, {3: 100.1}, m)[0, 0] == pytest.approx(0.0)  # 3. bar 100'de acilir (BE stopunun altinda): bosluk -> acilista dolum, R = 0
    # BE yokken ayni senaryo: stop 98.5 dokunulmaz -> zaman asimi 0 R
    assert _sim({2: 101.6}, {3: 100.1}, None, ol={3: 100.3})[0, 0] == pytest.approx(0.0)
    # kismi: bar 2 yuksek 102.4 (+1,6 R), kapanis 102.0: %50 +2/1,5 R = 0,6667 realize; BE de tetiklenir (stop 100.15); kalan zaman asimi 100 -> 0 R
    r = _sim({2: 102.4}, {}, m, cl={2: 102.0})[0, 0]
    assert r == pytest.approx(0.5 * 2.0 / 1.5, abs=1e-9)
    # ayni bar: BE stopu SONRAKI bardan gecerli (ayni barda dusus stopu vurmaz)
    r = _sim({2: 101.6}, {2: 99.9}, m)[0, 0]
    assert r == pytest.approx(0.0)


def test_simule_masraf_enstruman_bazli():
    mal = (0.0005, 4e-4, 4e-4, 10e-4)                # hisse ('open'): giris/cikis 4 bp, stop 10 bp
    r_hedef = _sim({3: 103.2}, {}, mal=mal)[0, 0]
    assert r_hedef == pytest.approx(2.0 - 100.0 * (2 * 0.0005 + 4e-4 + 4e-4) / 1.5)
    r_stop = _sim({3: 103.2}, {}, mal=mal)[0, 1]      # short stop: stop kaymasi
    assert r_stop == pytest.approx(-1.0 - 100.0 * (2 * 0.0005 + 4e-4 + 10e-4) / 1.5)


def test_maliyet_ve_cikis_kipleri_config_ile_ayni():
    m = C.maliyet_tablosu()
    assert len(m) == 43 and m["BTC/USDT"] == pytest.approx((0.0005, 2e-4, 2e-4, 5e-4)) and m["NVDA/USDT"] == pytest.approx((0.0005, 4e-4, 4e-4, 10e-4))
    k = C.cikis_kipleri()
    assert k.breakeven and k.partial and (k.be_trigger_r, k.be_offset_bps, k.pt_trigger_r, k.pt_frac) == (1.0, 15.0, 1.5, 0.5)


def test_masraf_ve_ornek_tablosu():
    X, t = C.cift_ornekleri(_df(), 1)
    assert X.shape[1] == DL.N_KANAL and (X[:, 9] == 1).all() and (X[:, 8] == 0).all()    # sinif 1 = hisse tek-sicak
    assert len(t["i"]) > 600 and t["i"].min() >= 2 * DL.PENCERE - 2
    assert (np.diff(t["ts"]) > 0).all()
    assert t["ts"][-1] + (DL.UFUK - 1) * H <= (pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(hours=1500)).value   # ufuk gozlendi
    assert np.isfinite(t["r"]).all() and np.isfinite(t["vol"]).all()


def test_bos_mumlar_ornek_olmaz_ve_doldurulmaz():
    bos = np.arange(700, 760)
    X, t = C.cift_ornekleri(_df(bos=bos), 1)
    ts_bos = {(pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(hours=int(k))).value + H for k in bos}
    assert not ts_bos & set(t["ts"].tolist())                          # bos mum karar bari olamaz
    assert len(X) == 1500 - 60                                         # seri yalniz dolu mumlardan kurulur (satir yok)


def test_seyrek_pencere_ornek_vermez():
    sil = [k for k in range(300, 1200) if k % 4]                       # 300-1200 arasi her 4. saat mum: doluluk %25
    X, t = C.cift_ornekleri(_df(sil=sil), 1)
    ts0 = pd.Timestamp("2025-01-01", tz="UTC")
    aralik = [(ts0 + pd.Timedelta(hours=k)).value for k in range(300 + 140, 1190)]
    assert not (set(aralik) & set((t["ts"] - H).tolist()))             # seyrek bolgede (pencere dolulugu < %50) ornek yok
    assert (t["ts"] - H >= ts0.value + 1200 * H).any()                # seyrek bolge bitince ornekler geri gelir


# ------------------------------------------------------------------------------------------- walk-forward
@pytest.fixture
def kucuk(monkeypatch):
    monkeypatch.setattr(C, "TRAIN_BARS", 24 * 40)
    monkeypatch.setattr(C, "TEST_BARS", 24 * 10)
    monkeypatch.setattr(C, "STEP_BARS", 24 * 10)
    monkeypatch.setattr(C, "MIN_TEST_BARS", 24 * 5)
    monkeypatch.setattr(C, "ESIK_ORNEK", 3000)
    monkeypatch.setattr(C, "EGIT_TAVAN_FOLD", 3000)
    seri = {f"P{k}/USDT": _df(2200, tohum=k) for k in range(3)}
    return C.veri_kur(seri, {p: i for i, p in enumerate(seri)}), pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(hours=2200)


def test_yuru_purge_embargo_olcek_yalniz_egitimden(kucuk):
    v, kesim = kucuk
    gorulen = []

    def trainer(veri, rows, ort, std, tohum):
        gorulen.append((rows.copy(), ort.copy(), std.copy()))
        return C.ilk_ag(tohum)

    dil = C.yuru(v, trainer, kesim, log=lambda *_: None)
    fl = C.foldlar(v, kesim)
    assert len(dil) >= 3 and len(gorulen) == len(dil)
    for (rows, ort, std), d in zip(gorulen, dil):
        t0 = pd.Timestamp(d["test_basi"]).value
        assert v.bitis[rows].max() < t0 - 24 * H                       # purge + embargo: egitim etiketleri test oncesi bitmis
        assert v.ts[rows].max() < t0                                   # ayni saat butun enstrumanlar ayni dilimde (zamana gore bolme)
        x = v.X[v.g[rows]][:, :DL.N_FIYAT].astype(np.float64)
        assert np.allclose(ort[:DL.N_FIYAT], x.mean(axis=0)) and np.allclose(std[:DL.N_FIYAT], np.maximum(x.std(axis=0), 1e-8))
        assert (ort[DL.N_FIYAT:] == 0).all() and (std[DL.N_FIYAT:] == 1).all()
    for a, b in zip(fl, fl[1:]):
        assert not set(a["test_rows"].tolist()) & set(b["test_rows"].tolist())
        # ayni zaman damgasi iki dilime birden dusmez
        assert not set(v.ts[a["test_rows"]].tolist()) & set(v.ts[b["test_rows"]].tolist())
    assert all(d["n"] >= 0 and set(d["sinif"]) == set(DL.SINIFLAR) for d in dil)


def test_kapi_uc_sinif_ve_dilimler(kucuk):
    v, kesim = kucuk
    dil = C.yuru(v, lambda veri, rows, o, s, t: C.ilk_ag(t), kesim, log=lambda *_: None)
    k = C.kapi(dil)
    assert set(k["siniflar"]) == set(DL.SINIFLAR) and k["dilim_sayisi"] == len(dil) and isinstance(k["gecti"], bool)
    assert k["tum_siniflar_toplam"]["n"] == sum(d["n"] for d in dil) and set(k["korunan"]) | set(k["dusen"]) == set(DL.SINIFLAR)


def _d(n, ort, sn=0):
    r = np.full(n, ort)
    sinif = {a: {"n": 0, "ort_r": None} for a in DL.SINIFLAR}
    sinif[DL.SINIFLAR[sn]] = {"n": n, "ort_r": ort if n else None}
    return {"n": n, "ort_r": ort if n else None, "_r": r, "_sn": np.full(n, sn, dtype=int), "sinif": sinif}


def test_kapi_kosullari():
    iyi = [_d(20, 0.2), _d(20, 0.1), _d(20, 0.3), _d(20, -0.05), _d(20, 0.2)]               # 4/5 pozitif, ort > 0
    assert C.kapi(iyi)["gecti"] is True
    assert C.kapi([_d(20, 0.2), _d(20, 0.2), _d(20, -0.1), _d(20, -0.1), _d(20, -0.1)])["gecti"] is False    # 2/5 < %60 (ort > 0 olsa da)
    assert C.kapi([_d(20, -0.2), _d(20, -0.2), _d(20, 0.01)])["gecti"] is False                          # ort <= 0
    assert C.kapi([_d(5, 0.5), _d(5, 0.5), _d(5, 0.5)])["gecti"] is False                                # sinif n < 30: kapsamdan cikar, kapsam bos
    assert C.kapi([_d(20, 0.2), _d(0, 0), _d(20, 0.2), _d(20, 0.2), _d(20, 0.2)])["pozitif_oran"] == pytest.approx(0.8)
    assert C.kapi([])["gecti"] is False


def test_kapi_sinif_eleme_ve_kapsam():
    """Kripto iyi (n >= 30, ort > 0), hisse kotu (ort <= 0), emtia az (n < 30): yalniz kripto kapsamda; toplam yalniz kripto uzerinden."""
    dil = []
    for _ in range(5):
        d = _d(20, 0.2, 0)
        h = _d(20, -0.3, 1)
        e = _d(5, 0.9, 2)
        d["_r"] = np.r_[d["_r"], h["_r"], e["_r"]]
        d["_sn"] = np.r_[d["_sn"], h["_sn"], e["_sn"]]
        d["n"] = 45
        d["sinif"] = {"kripto": {"n": 20, "ort_r": 0.2}, "hisse": {"n": 20, "ort_r": -0.3}, "emtia": {"n": 5, "ort_r": 0.9}}
        dil.append(d)
    k = C.kapi(dil)
    assert k["korunan"] == ["kripto"] and k["dusen"] == {"hisse": "ort_r_pozitif_degil", "emtia": "aday_az"}
    assert k["gecti"] is True and k["toplam_ort_r"] == pytest.approx(0.2) and k["toplam_aday"] == 100       # tum sinif ortalamasi (negatif) kapiyi bozmaz
    # paket kapsami: yalniz korunan sinif ciftleri
    ag = C.ilk_ag(1)
    sn = {"A/USDT": 0, "NVDA/USDT": 1, "XAU/USDT": 2}
    p = C.paket_kur(ag, np.zeros(DL.N_KANAL), np.ones(DL.N_KANAL), 0.7, sn, k, datetime(2026, 11, 24, tzinfo=UTC), {})
    assert p["kapsam"]["siniflar"] == {"A/USDT": 0}


def test_aday_sec_cift_basina_ufukta_bir_en_iyi_yon():
    class V:  # yalniz aday_sec'in kullandigi alanlar
        ts = np.array([0, 1, 2, 47, 48, 49, 100, 0, 1]) * H
        cift = np.array([0, 0, 0, 0, 0, 0, 0, 1, 1], dtype=np.int16)
    rows = np.arange(9)
    p = np.array([[0.9, 0.1], [0.95, 0.1], [0.2, 0.99], [0.99, 0.1], [0.99, 0.0], [0.8, 0.0], [0.5, 0.97], [0.6, 0.1], [0.1, 0.99]])
    pos, yon = C.aday_sec(V, rows, p, 0.9)
    # cift 0: t=0 (long, 0,9) secilir; t=1,2 ufuk icinde (48 saat) atlanir; t=47 icinde; t=48 >= 0+48 secilir (long); t=49 ufukta; t=100 (short, 0,97) secilir
    # cift 1: t=1 (short 0,99) secilir (t=0 esik alti)
    assert sorted(zip(pos.tolist(), yon.tolist())) == [(0, 0), (4, 0), (6, 1), (8, 1)]


Y = {"n": 100, "ort_r": 0.30, "std": 1.0}
M = {"n": 100, "ort_r": 0.20, "std": 1.0}


@pytest.mark.parametrize("gecti,mevcut,kalan,gecen,rm,ry,yayin,neden", [
    (False, "yok", None, None, None, None, False, "kapi_gecmedi"),
    (False, "gecerli", 3.0, 40.0, M, Y, False, "kapi_gecmedi"),                  # kapi gecmediyse suresi yakin olsa da yayin yok
    (True, "yok", None, None, None, None, True, "mevcut_yok"),
    (True, "gecerli", 6.9, 2.0, M, {"n": 100, "ort_r": 0.0, "std": 1.0}, True, "mevcut_suresi_yakin"),   # <7 gun: iyilesme aranmaz
    (True, "gecerli", 30.0, 13.9, M, {"n": 400, "ort_r": 0.9, "std": 1.0}, False, "karsilastirma_erken"),   # <14 gun gecmis: iyilesme yayini yok
    (True, "gecerli", 30.0, 14.0, M, {"n": 400, "ort_r": 0.0, "std": 1.0}, False, "iyilesme_yok"),
    (True, "gecerli", 30.0, 14.0, {"n": 400, "ort_r": 0.20, "std": 1.0}, {"n": 400, "ort_r": 0.26, "std": 1.0}, True, "iyilesme"),   # se_fark = sqrt(2)/20 = 0,0707 > 0,05 -> gerekli 0,0707: 0,06 yetmez
    (True, "gecerli", 30.0, 14.0, M, {"n": 100, "ort_r": 0.9, "std": 1.0}, True, "iyilesme"),          # fark 0,7 >= max(0,05, 0,14)
    (True, "gecerli", 30.0, 20.0, M, {"n": 29, "ort_r": 0.9, "std": 1.0}, False, "yetersiz_aday"),
    (True, "gecerli", 30.0, 20.0, {"n": 29, "ort_r": 0.1, "std": 1.0}, Y, False, "yetersiz_aday"),     # mevcutta da n >= 30 sart
    (True, "gecerli", 30.0, 20.0, M, None, False, "yetersiz_aday"),
    (True, "gecerli", 30.0, 20.0, None, Y, False, "yetersiz_aday"),
])
def test_yayin_karari(gecti, mevcut, kalan, gecen, rm, ry, yayin, neden):
    d = C.yayin_karari(gecti, mevcut, kalan, gecen, rm, ry)
    if neden == "iyilesme" and rm["n"] == 400 and ry["ort_r"] == 0.26:
        yayin = False
        neden = "iyilesme_yok"
    assert d["yayinla"] is yayin and d["neden"] == neden and d["esik_iyilesme"] == 0.05 and d["kars_min_gun"] == 14


def test_yayin_karari_standart_hata_ve_esik_alt_siniri():
    se = {"n": 10000, "ort_r": 0.20, "std": 1.0}
    d = C.yayin_karari(True, "gecerli", 30.0, 20.0, se, {"n": 10000, "ort_r": 0.25, "std": 1.0})
    assert d["yayinla"] and d["gerekli_fark"] == pytest.approx(0.05)                                   # se_fark = 0,014 < 0,05 -> sabit esik
    d = C.yayin_karari(True, "gecerli", 30.0, 20.0, se, {"n": 10000, "ort_r": 0.249, "std": 1.0})
    assert not d["yayinla"] and d["neden"] == "iyilesme_yok"


def test_son_dilim_yalniz_olusturmadan_sonra_ve_ileriye_bakma_yok(kucuk):
    v, kesim = kucuk
    olus = kesim - pd.Timedelta(days=14)
    tr, ev = C.son_dilim(v, olus)
    assert len(ev) and len(tr) and (v.ts[ev] >= olus.value).all() and v.bitis[tr].max() < olus.value - 24 * H


def test_aday_r_ve_mevcut_durum(kucuk, tmp_path):
    v, kesim = kucuk
    ag, (o, s) = C.ilk_ag(3), C.olcekleyici(v, np.arange(len(v.g)))
    rows = np.arange(0, len(v.g), 4)                                           # (ayni zaman damgali ciftler ardisik: 3'luk adim tek cifti secerdi)
    r = C.aday_r(v, rows, ag, o, s, 0.0)
    assert 0 < r["n"] <= len(rows) and r["std"] is not None                  # esik 0: cift basina 48 saatte bir aday (ust uste binme yok)
    assert C.aday_r(v, rows, ag, o, s, 1.1)["n"] == 0 and C.aday_r(v, rows, ag, o, s, 1.1)["ort_r"] is None
    assert C.aday_r(v, rows, ag, o, s, 0.0, {"P0/USDT"})["n"] < r["n"]       # ciftler filtresi
    now = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)
    assert C.mevcut_durum(tmp_path / "yok.json", now) == ("yok", None, None)


# ------------------------------------------------------------------------------------------- paket
def test_paket_kur_yaz_oku_idempotent(kucuk, tmp_path):
    v, _ = kucuk
    ag = C.ilk_ag(5)
    o, s = C.olcekleyici(v, np.arange(len(v.g)))
    now = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)
    p = C.paket_kur(ag, o, s, 0.7, v.siniflar, {"gecti": True, "toplam_ort_r": 0.1, "pozitif_oran": 0.8}, now, {"x": 1})
    assert p["sha256"] == DL.paket_ozeti(p) and p["son_kullanma"] == (now + timedelta(days=45)).isoformat()
    yol = tmp_path / "models" / "dl1" / "DL1@1h.json"
    assert C.paket_yaz(p, yol) is True and C.paket_yaz(p, yol) is False
    pk, neden = DL.paket_yukle(yol, now + timedelta(days=1))
    assert neden is None and pk.esik == 0.7 and set(pk.siniflar) == set(v.siniflar)
    assert np.allclose(pk.agirlik["head.w"], np.round(ag["head.w"], 7))
    d, kalan = C.mevcut_durum(yol, now + timedelta(days=1))[0], C.mevcut_durum(yol, now + timedelta(days=1))[2]
    assert d == "gecerli" and kalan == pytest.approx(44.0)
    pk_kapi = C.paket_kur(ag, o, s, 0.7, v.siniflar, {"gecti": False, "toplam_ort_r": -1, "pozitif_oran": 0.1}, now, {})
    C.paket_yaz(pk_kapi, tmp_path / "k.json")
    assert DL.paket_yukle(tmp_path / "k.json", now) == (None, "kapi")


def test_puanlar_motorla_ayni_ileri_gecis(kucuk):
    v, _ = kucuk
    ag = C.ilk_ag(2)
    o, s = C.olcekleyici(v, np.arange(len(v.g)))
    rows = np.array([5, 50, 500])
    p = C.puanlar(v, rows, ag, o, s)
    w = C.pencereler(C.olcekli_x(v, o, s), v.g[rows]).astype(np.float64)
    assert np.allclose(p, DL.sigmoid(DL.ileri(ag, w)[:, :2]))


def test_workflow_ve_betik_sozlesmesi():
    wf = "\n".join(x for x in (ROOT.parent / ".github" / "workflows" / "dl1-egitim.yml").read_text(encoding="utf-8").splitlines()
                   if not x.lstrip().startswith("#"))
    assert "schedule" in wf and "workflow_dispatch" in wf and "contents: write" in wf and "claude/charming-hawking-ab5w5q" in wf
    assert "push:" not in wf.split("jobs:")[0] and "pull_request" not in wf.split("jobs:")[0]          # sonsuz dongu yok
    assert "torch==" in wf and "DL1 paket:" in wf and "paket_yazildi" in wf
    t = (ROOT.parent / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "trader/models/**" in t
    assert "torch" not in (ROOT / "requirements.lock").read_text(encoding="utf-8").lower()
    for ad in ("egit.py", "duman.py", "veri.py", "cekirdek.py"):
        assert (ROOT / "research" / "dl1" / ad).exists()


def test_veri_indir_url_plani_kilit_acik(tmp_path, monkeypatch):
    """Vision indirici: kilit acikken 2026-05 sonrasi istenir (arac korumasi kaldirilir); gecen aylar aylik, son iki ay eksikse gunluk; ag yok."""
    sys.path.insert(0, str(ROOT / "research" / "dl1"))
    import veri as V
    F = V.arac()
    istekler = []
    monkeypatch.setattr(F, "fetch_zip", lambda url, dest, req=False: (istekler.append(url), "missing")[1])
    monkeypatch.setattr(F, "HOLDOUT_START", F.HOLDOUT_START)
    out = V.indir(["NVDA/USDT", "BTC/USDT"], "2026-09", datetime(2026, 11, 23).date(), tmp_path, isci=2, log=lambda *_: None)
    assert out == {} and F.HOLDOUT_START.year == 2100
    nv = [u for u in istekler if "NVDAUSDT" in u]
    assert any(u.endswith("monthly/klines/NVDAUSDT/1h/NVDAUSDT-1h-2026-09.zip") for u in nv)
    assert any(u.endswith("monthly/klines/NVDAUSDT/1h/NVDAUSDT-1h-2026-10.zip") for u in nv)
    assert not any("monthly" in u and "2026-11" in u for u in nv)                       # kesim ayi: yalniz gunluk
    assert any(u.endswith("daily/klines/NVDAUSDT/1h/NVDAUSDT-1h-2026-11-22.zip") for u in nv)
    assert not any("2026-11-23.zip" in u for u in nv)                                    # kesim gunu (dislayici) istenmez


def test_motor_puanla_egitim_puanlar_ayni(kucuk, tmp_path):
    """Ayni bar, ayni agirlik: DL.puanla (canli yol: ham mumlar) == C.puanlar (egitim yolu: onceden hesaplanmis X, float32)."""
    v, _ = kucuk
    ag = C.ilk_ag(4)
    o, s = C.olcekleyici(v, np.arange(len(v.g)))
    p = C.paket_kur(ag, o, s, 0.5, v.siniflar, {"gecti": True, "toplam_ort_r": 0.1, "pozitif_oran": 1.0}, datetime(2026, 11, 24, tzinfo=UTC), {})
    paket = DL.paket_dogrula(p)
    seri = _df(2200, tohum=0)
    rows = np.flatnonzero(v.cift == 0)
    for r in rows[[len(rows) // 3, len(rows) // 2, -5]]:
        ts_ns = seri["date"].dt.as_unit("ns").astype("int64").to_numpy()
        k = int(np.flatnonzero(ts_ns == v.ts[r] - H)[0])
        a = [seri[c].to_numpy()[:k + 1] for c in ("open", "high", "low", "close", "volume")]
        motor = DL.puanla(paket, "P0/USDT", ts_ns[:k + 1], *a)
        egitim = C.puanlar(v, np.array([r]), ag, o, s)[0]
        assert motor is not None and motor[0] == pytest.approx(egitim[0], abs=1e-4) and motor[1] == pytest.approx(egitim[1], abs=1e-4)
