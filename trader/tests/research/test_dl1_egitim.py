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
    ts, o, h, l, c, atr = _bariyer({3: 103.2}, {})                    # long hedefi 103 (3 ATR); short stopu 101.5 ayni barda vurulur
    ok, y, rb, vol = C.etiketle(ts, o, h, l, c, atr)
    assert ok[0] and y[0].tolist() == [1, 0] and rb[0].tolist() == [2.0, -1.0]
    ts, o, h, l, c, atr = _bariyer({3: 104.0}, {3: 96.0})             # ayni barda iki bariyer: stop (muhafazakar)
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert y[0].tolist() == [0, 0] and rb[0].tolist() == [-1.0, -1.0]
    ts, o, h, l, c, atr = _bariyer({}, {})                            # hicbiri: zaman asimi, son mumun kapanisi (100) -> R = 0
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert ok[0] and y[0].tolist() == [0, 0] and rb[0].tolist() == [0.0, 0.0]


def test_etiket_ufuk_24_saat_ve_gozlenmemis_ufuk_gecersiz():
    ts, o, h, l, c, atr = _bariyer({25: 110.0}, {}, n=60)             # 25. saatte hedef: ufuk disi
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert y[0, 0] == 0 and rb[0, 0] == 0.0 and y[1, 0] == 1           # bar 1 icin 24 saat icinde
    ok2, *_ = C.etiketle(ts, o, h, l, c, atr)
    assert not ok2[-1] and not ok2[-24] and ok2[len(ts) - 26]          # son 24 saat ufku tam gozlenmedi


def test_etiket_takvim_boslugu_ufku_asan_mum_sayilmaz():
    ts, o, h, l, c, atr = _bariyer({3: 110.0}, {}, n=60)
    ts = ts.copy()
    ts[3:] += 30 * H                                                   # 3. mumdan once 30 saatlik bosluk (seans): ufuk disinda
    ok, y, rb, _ = C.etiketle(ts, o, h, l, c, atr)
    assert y[0, 0] == 0


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
    assert k["toplam_aday"] == sum(d["n"] for d in dil)


def _d(n, ort, kripto=None):
    r = np.full(n, ort)
    return {"n": n, "ort_r": ort if n else None, "_r": r, "_sn": np.zeros(n, dtype=int),
            "sinif": {"kripto": {"n": n, "ort_r": ort if n else None}, "hisse": {"n": 0, "ort_r": None}, "emtia": {"n": 0, "ort_r": None}}}


def test_kapi_kosullari():
    iyi = [_d(20, 0.2), _d(20, 0.1), _d(20, 0.3), _d(20, -0.05), _d(20, 0.2)]               # 4/5 pozitif, ort > 0
    assert C.kapi(iyi)["gecti"] is True
    assert C.kapi([_d(20, 0.2), _d(20, 0.2), _d(20, -0.1), _d(20, -0.1), _d(20, -0.1)])["gecti"] is False    # 2/5 < %60 (ort > 0 olsa da)
    assert C.kapi([_d(20, -0.2), _d(20, -0.2), _d(20, 0.01)])["gecti"] is False                          # ort <= 0
    assert C.kapi([_d(5, 0.5), _d(5, 0.5), _d(5, 0.5)])["gecti"] is False                                # toplam aday < 30
    assert C.kapi([_d(20, 0.2), _d(0, 0), _d(20, 0.2), _d(20, 0.2), _d(20, 0.2)])["pozitif_oran"] == pytest.approx(0.8)
    assert C.kapi([])["gecti"] is False


# ------------------------------------------------------------------------------------------- yayin karari (gunluk)
Y = {"n": 100, "ort_r": 0.30}
M = {"n": 100, "ort_r": 0.20}


@pytest.mark.parametrize("gecti,mevcut,kalan,rm,ry,yayin,neden", [
    (False, "yok", None, None, None, False, "kapi_gecmedi"),
    (False, "gecerli", 3.0, M, Y, False, "kapi_gecmedi"),                  # kapi gecmediyse suresi yakin olsa da yayin yok
    (True, "yok", None, None, None, True, "mevcut_yok"),
    (True, "gecerli", 6.9, M, {"n": 100, "ort_r": 0.0}, True, "mevcut_suresi_yakin"),   # <7 gun: iyilesme aranmaz
    (True, "gecerli", 7.0, M, {"n": 100, "ort_r": 0.0}, False, "iyilesme_yok"),
    (True, "gecerli", 30.0, M, {"n": 100, "ort_r": 0.25}, True, "iyilesme"),            # tam +0,05 esik
    (True, "gecerli", 30.0, M, {"n": 100, "ort_r": 0.2499}, False, "iyilesme_yok"),
    (True, "gecerli", 30.0, M, {"n": 5, "ort_r": 0.9}, False, "yetersiz_aday"),
    (True, "gecerli", 30.0, M, None, False, "yetersiz_aday"),
    (True, "gecerli", 30.0, {"n": 0, "ort_r": None}, Y, True, "mevcut_aday_uretmedi"),
    (True, "gecerli", 30.0, None, Y, True, "mevcut_aday_uretmedi"),
])
def test_yayin_karari(gecti, mevcut, kalan, rm, ry, yayin, neden):
    d = C.yayin_karari(gecti, mevcut, kalan, rm, ry)
    assert d["yayinla"] is yayin and d["neden"] == neden and d["esik_iyilesme"] == 0.05 and d["son_dilim_gun"] == 14


def test_son_dilim_ileriye_bakma_yok(kucuk):
    v, kesim = kucuk
    tr, ev = C.son_dilim(v, kesim)
    bas = (kesim - pd.Timedelta(days=C.SON_DILIM_GUN)).value
    assert len(ev) and len(tr) and (v.ts[ev] >= bas).all() and v.bitis[tr].max() < bas - 24 * H


def test_aday_r_ve_mevcut_durum(kucuk, tmp_path):
    v, kesim = kucuk
    ag, (o, s) = C.ilk_ag(3), C.olcekleyici(v, np.arange(len(v.g)))
    rows = np.arange(0, len(v.g), 3)
    r = C.aday_r(v, rows, ag, o, s, 0.0)
    assert r["n"] == 2 * len(rows)                                       # esik 0: iki yon de aday
    assert C.aday_r(v, rows, ag, o, s, 1.1)["n"] == 0 and C.aday_r(v, rows, ag, o, s, 1.1)["ort_r"] is None
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
