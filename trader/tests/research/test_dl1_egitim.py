"""research/dl1/cekirdek.py: numpy-only kisimlar (torch GEREKTIRMEZ; torch'lu egitim/parite research/dl1/duman.py'de, Actions'ta).
Sentetik veri; ag/gercek veri yok."""
from __future__ import annotations

import importlib.util
import json
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
    assert DL.UFUK == signals.TIME_STOP_BARS == 48 and C.PURGE_MUM == DL.UFUK + 24 == 72 and C.EMBARGO_MUM == 24


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
    for tf in DL.ZAMAN_DILIMLERI:
        assert C.cikis_kipleri(tf=tf).breakeven                                  # DL1 icin tum zaman dilimlerinde ortak varsayilan
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
    monkeypatch.setitem(C.AYARLAR, "1h", C.TfAyar("1h", "2025-01", 40, 10, 10, 5))
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
    # 24.11: kapi YALNIZ metrik; paket kapsami TUM egitilen ciftlerdir (sinif elemesi yok)
    ag = C.ilk_ag(1)
    sn = {"A/USDT": 0, "NVDA/USDT": 1, "XAU/USDT": 2}
    p = C.paket_kur(ag, np.zeros(DL.N_KANAL), np.ones(DL.N_KANAL), 0.7, sn, k, datetime(2026, 11, 24, tzinfo=UTC), {})
    assert p["kapsam"]["siniflar"] == sn


def test_aday_sec_cift_basina_ufukta_bir_en_iyi_yon():
    class V:  # yalniz aday_sec'in kullandigi alanlar
        bar_ns = H
        ts = np.array([0, 1, 2, 47, 48, 49, 100, 0, 1]) * H
        cift = np.array([0, 0, 0, 0, 0, 0, 0, 1, 1], dtype=np.int16)
    rows = np.arange(9)
    p = np.array([[0.9, 0.1], [0.95, 0.1], [0.2, 0.99], [0.99, 0.1], [0.99, 0.0], [0.8, 0.0], [0.5, 0.97], [0.6, 0.1], [0.1, 0.99]])
    pos, yon = C.aday_sec(V, rows, p, 0.9)
    # cift 0: t=0 (long, 0,9) secilir; t=1,2 ufuk icinde (48 saat) atlanir; t=47 icinde; t=48 >= 0+48 secilir (long); t=49 ufukta; t=100 (short, 0,97) secilir
    # cift 1: t=1 (short 0,99) secilir (t=0 esik alti)
    assert sorted(zip(pos.tolist(), yon.tolist())) == [(0, 0), (4, 0), (6, 1), (8, 1)]


def test_yayin_karari_kapi_engellemez():
    """24.11 kullanici karari: kalite kapisi YAYINI ENGELLEMEZ; her gece en yeni paket yayinlanir (gecti True/False ve metrik bos olsa da)."""
    for gecti in (True, False):
        d = C.yayin_karari({"gecti": gecti, "toplam_ort_r": -1.0})
        assert d["yayinla"] is True and d["kapi_gecti"] is gecti and d["neden"] == "otomatik_kapisiz"
    assert C.yayin_karari({})["yayinla"] is True
    assert not hasattr(C, "mevcut_durum") and not hasattr(C, "son_dilim") and not hasattr(C, "aday_r")        # iyilesme karsilastirmasi kaldirildi


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
    pk_kapi = C.paket_kur(ag, o, s, 0.7, v.siniflar, {"gecti": False, "toplam_ort_r": -1, "pozitif_oran": 0.1}, now, {})
    C.paket_yaz(pk_kapi, tmp_path / "k.json")
    pk2, neden2 = DL.paket_yukle(tmp_path / "k.json", now)                          # 24.11: kapi gecmemis paket de yuklenir (engellenmez)
    assert neden2 is None and pk2 is not None and set(pk2.siniflar) == set(v.siniflar)


def test_puanlar_motorla_ayni_ileri_gecis(kucuk):
    v, _ = kucuk
    ag = C.ilk_ag(2)
    o, s = C.olcekleyici(v, np.arange(len(v.g)))
    rows = np.array([5, 50, 500])
    p = C.puanlar(v, rows, ag, o, s)
    w = C.pencereler(C.olcekli_x(v, o, s), v.g[rows]).astype(np.float64)
    assert np.allclose(p, DL.sigmoid(DL.ileri(ag, w)[:, :2]))


def test_workflow_ve_betik_sozlesmesi():
    import yaml
    yol = ROOT.parent / ".github" / "workflows" / "dl1-egitim.yml"
    doc = yaml.safe_load(yol.read_text(encoding="utf-8"))               # gecerli YAML (':' iceren adlar tirnakli)
    on = doc.get("on", doc.get(True))
    crons = [x["cron"] for x in on["schedule"]]
    assert crons == ["0 1 * * *", "0 2 * * *"] and "workflow_dispatch" in on          # 01:00 UTC ana, 02:00 UTC yedek
    assert "push" not in on and "pull_request" not in on                               # sonsuz dongu yok
    assert doc["permissions"]["contents"] == "write" and doc["env"]["DAL"] == "claude/charming-hawking-ab5w5q"
    egit, kontrol = doc["jobs"]["egit"], doc["jobs"]["kontrol"]
    assert 300 <= egit["timeout-minutes"] <= 360 and egit["needs"] == "kontrol" and "atla" in egit["if"] and "always()" in egit["if"]
    adimlar = {a.get("id"): a for a in egit["steps"] if a.get("id")}
    toplam = 0
    for tf in DL.ZAMAN_DILIMLERI:
        a = adimlar[f"egit_{tf}"]
        assert f"--tf {tf}" in a["run"] and a["continue-on-error"] is True and "--cikti models/dl1" in a["run"]
        assert f"egit_{tf}" in a["if"] and f"egit_{tf}" in kontrol["outputs"]                  # yedek kosu: zaman dilimi basina karar
        toplam += a["timeout-minutes"]
    assert toplam + 15 <= egit["timeout-minutes"]                                      # adim zaman asimlari + kurulum is zaman asimina sigar
    it = adimlar["it"]
    assert "!cancelled()" in it["if"] and "paket_yazildi" not in it["if"] and "DL1@*.json" in it["run"]   # kapi/iyilesme sarti YOK: egitilen her paket itilir
    assert "push origin" in it["run"] and "for deneme in 1 2 3 4 5" in it["run"] and "git pull --rebase" in it["run"]     # itme yeniden denemeli
    kullan = {a.get("uses", "").split("@")[0] for a in egit["steps"]}
    assert {"actions/cache/restore", "actions/cache/save"} <= kullan and "actions/cache" not in kullan
    kaydet = [a for a in egit["steps"] if a.get("uses", "").startswith("actions/cache/save")][0]
    assert kaydet["if"] == "always()"
    tst = [a for a in egit["steps"] if "tests.yml" in a.get("run", "")]
    assert len(tst) == 1 and "itildi == '1'" in tst[0]["if"]
    # yedek kosu bugun basarili kosu varsa atlar
    kr = "\n".join(a.get("run", "") for a in kontrol["steps"])
    assert "0 2 * * *" in kr and "gunluk_kontrol.py" in kr and "atla=0" in kr and "gh run list" not in kr and "--yedek" in kr
    wf = "\n".join(x for x in yol.read_text(encoding="utf-8").splitlines() if not x.lstrip().startswith("#"))
    assert "torch==" in wf and "DL1 paketleri:" in wf
    t = (ROOT.parent / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "trader/models/**" in t
    assert "torch" not in (ROOT / "requirements.lock").read_text(encoding="utf-8").lower()
    for ad in ("egit.py", "duman.py", "veri.py", "cekirdek.py", "gunluk_kontrol.py"):
        assert (ROOT / "research" / "dl1" / ad).exists()


def test_gunluk_kontrol_zaman_dilimi_basina_karar(tmp_path, capsys):
    """Yedek kosu yalniz bugun (UTC) yenilenmemis zaman dilimlerini egitir; dortu yenilenmisse atla=1; yedek degilse hepsi egitilir."""
    import gunluk_kontrol as G
    bugun = "2026-11-25"
    d = tmp_path / "dl1"
    d.mkdir()

    def yaz(tf, olusturma):
        (d / f"DL1@{tf}.json").write_text(json.dumps({"olusturma": olusturma}), encoding="utf-8")
    yaz("1d", "2026-11-25T01:20:03+00:00")
    yaz("4h", "2026-11-24T23:59:59+00:00")                      # dun
    yaz("1h", "2026-11-25T03:30:00+03:00")                      # UTC'de 00:30 -> bugun
    (d / "DL1@15m.json").write_text("{bozuk", encoding="utf-8")   # bozuk -> yenilenmedi
    assert G.karar(d, bugun, True) == {"15m": True, "1h": False, "4h": True, "1d": False}
    assert all(G.karar(d, bugun, False).values())               # ana cron/elle: hepsi
    assert G.main(["--bugun", bugun, "--dizin", str(d), "--yedek"]) == 0
    cikti = capsys.readouterr().out.split()
    assert cikti == ["egit_15m=1", "egit_1h=0", "egit_4h=1", "egit_1d=0", "atla=0"]
    for tf in ("15m", "4h"):
        yaz(tf, "2026-11-25T01:59:00+00:00")
    assert G.main(["--bugun", bugun, "--dizin", str(d), "--yedek"]) == 0
    assert capsys.readouterr().out.split()[-1] == "atla=1" and all(G.karar(d, bugun, True)[tf] is False for tf in ("15m", "1h", "4h", "1d"))
    assert G.karar(tmp_path / "yok", bugun, True) == {tf: True for tf in ("15m", "1h", "4h", "1d")}        # dosya yok -> egit


def test_zaman_dilimi_ayarlari():
    """Dort zaman dilimi icin veri penceresi: 15m kisa tarihce (cok mum), digerleri 2021'den; mum sayisi takvim gunune bagli."""
    assert set(C.AYARLAR) == set(DL.ZAMAN_DILIMLERI)
    assert C.AYARLAR["15m"].bas_ay == "2024-01" and C.AYARLAR["1h"].bas_ay == C.AYARLAR["4h"].bas_ay == C.AYARLAR["1d"].bas_ay == "2021-01"
    assert C.AYARLAR["1h"].mum(365) == 365 * 24 and C.AYARLAR["15m"].mum(60) == 60 * 96 and C.AYARLAR["4h"].mum(120) == 720 and C.AYARLAR["1d"].mum(120) == 120
    for tf in DL.ZAMAN_DILIMLERI:
        assert C.AYARLAR[tf].bar_ns == DL.BAR_NS[tf]


def _df_tf(tf, n, tohum=1):
    rg = np.random.default_rng(tohum)
    t = pd.date_range("2025-01-01", periods=n, freq={"15m": "15min", "1h": "h", "4h": "4h", "1d": "D"}[tf], tz="UTC").as_unit("ms")
    c = 100 * np.exp(np.cumsum(rg.normal(0, 0.004, n)))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + rg.uniform(0.0005, 0.003, n))
    l = np.minimum(o, c) * (1 - rg.uniform(0.0005, 0.003, n))
    return pd.DataFrame({"date": t, "open": o, "high": h, "low": l, "close": c, "volume": rg.uniform(10, 100, n)})


@pytest.mark.parametrize("tf", ["15m", "4h", "1d"])
def test_diger_zaman_dilimlerinde_ornek_etiket_ve_dilimler(tf, monkeypatch):
    """15m/4h/1d: karar zamani = mum acilisi + 1 mum; ufuk 48 MUM; walk-forward o zaman diliminin izgarasinda, purge/embargo mum biriminde."""
    ns = DL.BAR_NS[tf]
    n = {"15m": 5000, "4h": 1500, "1d": 1000}[tf]
    X, t = C.cift_ornekleri(_df_tf(tf, n), 0, bar_ns=ns)
    assert len(t["i"]) > 0.5 * n and (np.diff(t["ts"]) == ns).all()                     # ardisik dolu mumlar: karar zamani adimi = mum suresi
    ts0 = pd.Timestamp("2025-01-01", tz="UTC").value
    assert t["ts"][0] == ts0 + (t["i"][0] + 1) * ns and t["ts"][-1] + (DL.UFUK - 1) * ns <= ts0 + n * ns
    g = {"15m": C.TfAyar("15m", "2025-01", 20, 5, 5, 2), "4h": C.TfAyar("4h", "2025-01", 60, 20, 20, 10), "1d": C.TfAyar("1d", "2025-01", 100, 30, 30, 10)}[tf]
    monkeypatch.setitem(C.AYARLAR, tf, g)
    seri = {f"P{k}/USDT": _df_tf(tf, n, k) for k in range(2)}
    v = C.veri_kur(seri, {p: i for i, p in enumerate(seri)}, bar_ns=ns)
    assert v.bar_ns == ns and (v.bitis - v.ts == DL.UFUK * ns).all()
    kesim = pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(ns, unit="ns") * n
    fl = [f for f in C.foldlar(v, kesim) if len(f["test_rows"]) and len(f["train_rows"])]      # (yuru: orneksiz/bos dilimleri atlar; ilk ~192 mum isinma)
    assert len(fl) >= 2
    for f in fl:
        t0 = pd.Timestamp(f["test_start"]).value
        assert v.bitis[f["train_rows"]].max() < t0 - C.EMBARGO_MUM * ns and v.ts[f["train_rows"]].max() < t0
        assert v.ts[f["test_rows"]].min() >= t0 and v.ts[f["test_rows"]].max() <= pd.Timestamp(f["test_end"]).value


def test_paket_kur_dort_zaman_dilimi_arm_id_ve_tum_kapsam(tmp_path):
    ag = C.ilk_ag(6)
    sn = {"A/USDT": 0, "NVDA/USDT": 1, "XAU/USDT": 2}
    now = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)
    for tf in DL.ZAMAN_DILIMLERI:
        p = C.paket_kur(ag, np.zeros(DL.N_KANAL), np.ones(DL.N_KANAL), 0.7, sn, {"gecti": False, "toplam_ort_r": None, "pozitif_oran": 0.0, "korunan_idx": []}, now, {}, tf)
        assert p["arm_id"] == f"DL1@{tf}" and p["tf"] == tf and p["kapsam"]["siniflar"] == sn and p["kapi"]["gecti"] is False
        yol = tmp_path / f"DL1@{tf}.json"
        assert C.paket_yaz(p, yol)
        pk, neden = DL.paket_yukle(yol, now + timedelta(days=100), tf=tf)                 # kapisiz ve 100 gun yasli: yine yuklenir
        assert neden is None and pk.tf == tf and pk.eski(now + timedelta(days=100))


def test_veri_indir_url_plani_zaman_dilimine_gore(tmp_path, monkeypatch):
    """15m/4h/1d: Vision yolu ve dosya adi zaman dilimini tasir (varsayilan 1h)."""
    import veri as V
    F = V.arac()
    istekler = []
    monkeypatch.setattr(F, "fetch_zip", lambda url, dest, req=False: (istekler.append(url), "missing")[1])
    for tf in ("15m", "4h", "1d"):
        istekler.clear()
        V.indir(["BTC/USDT"], "2026-09", datetime(2026, 11, 23).date(), tmp_path, isci=1, log=lambda *_: None, tf=tf)
        assert any(u.endswith(f"monthly/klines/BTCUSDT/{tf}/BTCUSDT-{tf}-2026-09.zip") for u in istekler)
        assert any(u.endswith(f"daily/klines/BTCUSDT/{tf}/BTCUSDT-{tf}-2026-11-22.zip") for u in istekler)
        assert not any("/1h/" in u for u in istekler)


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


@pytest.mark.parametrize("tf", ["1h", "4h"])
def test_egit_main_kapi_gecmese_de_paket_yazilir(tf, tmp_path, monkeypatch):
    """Egitim betigi uctan uca (torch yerine numpy ilk agirlik, parite sahte): kapi GECMESE de paket yazilir, rapor + GITHUB_OUTPUT uretilir (24.11)."""
    import egit as E
    ns = DL.BAR_NS[tf]
    n = {"1h": 2500, "4h": 1500}[tf]
    monkeypatch.setitem(C.AYARLAR, tf, C.TfAyar(tf, "2025-01", 40 if tf == "1h" else 120, 10 if tf == "1h" else 30, 10 if tf == "1h" else 30, 5 if tf == "1h" else 10))
    seri = {p: _df_tf(tf, n, k) for k, p in enumerate(["BTC/USDT", "NVDA/USDT", "XAU/USDT"])}
    monkeypatch.setattr(E.V, "indir", lambda pairs, bas_ay, kesim, ham, tf="1h", **k: seri)
    monkeypatch.setattr(E, "torch_trainer", lambda *a, **k: (lambda v, rows, ort, std, tohum: C.ilk_ag(tohum)))
    monkeypatch.setattr(E, "parite", lambda *a, **k: {"n": 1, "max_fark_olasilik": 0.0, "max_fark_logit": 0.0})
    monkeypatch.setattr(C, "ESIK_ORNEK", 3000)
    monkeypatch.setattr(C, "EGIT_TAVAN_FOLD", 3000)
    monkeypatch.setattr(C, "EGIT_TAVAN_SON", 5000)
    cikti = tmp_path / "paketler" / "dl1"
    out = tmp_path / "gh_out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    kesim = (pd.Timestamp("2025-01-01") + pd.Timedelta(ns, unit="ns") * n).date().isoformat()
    assert E.main(["--tf", tf, "--kesim", kesim, "--cikti", str(cikti), "--rapor", str(tmp_path / "rapor")]) == 0
    assert (cikti / f"DL1@{tf}.json").exists() and "paket_yazildi=1" in out.read_text()
    rapor = json.loads((tmp_path / "rapor" / f"dl1_rapor_{tf}.json").read_text())
    assert rapor["tf"] == tf and rapor["karar"]["yayinla"] is True and rapor["paket_yazildi"] is True
    md = (tmp_path / "rapor" / f"dl1_rapor_{tf}.md").read_text()
    assert "(YALNIZ BILGI" in md and "Kapsam: 3/43, eksikler:" in md and "UYARI: kapsam eksik" in md and rapor["kapsam"]["n"] == 3
    pk, neden = DL.paket_yukle(cikti / f"DL1@{tf}.json", datetime.now(UTC) + timedelta(days=3), tf=tf)
    assert neden is None and pk.tf == tf and set(pk.siniflar) == {"BTC/USDT", "NVDA/USDT", "XAU/USDT"}


def test_egit_main_walk_forward_zaman_asimi_paket_yine_yazilir(tmp_path, monkeypatch):
    """4: paket walk-forward'dan ONCE yazilir; walk-forward bitmezse paket vardir, kapi/metrik alanlari bos, rapor 'TAMAMLANMADI' der."""
    import egit as E
    tf, n = "1h", 2500
    monkeypatch.setitem(C.AYARLAR, tf, C.TfAyar(tf, "2025-01", 40, 10, 10, 5))
    seri = {p: _df_tf(tf, n, k) for k, p in enumerate(["BTC/USDT", "NVDA/USDT", "XAU/USDT"])}
    monkeypatch.setattr(E.V, "indir", lambda pairs, bas_ay, kesim, ham, tf="1h", **k: seri)
    monkeypatch.setattr(E, "torch_trainer", lambda *a, **k: (lambda v, rows, ort, std, tohum: C.ilk_ag(tohum)))
    monkeypatch.setattr(E, "parite", lambda *a, **k: {"n": 1, "max_fark_olasilik": 0.0, "max_fark_logit": 0.0})
    monkeypatch.setattr(C, "ESIK_ORNEK", 3000)
    monkeypatch.setattr(C, "EGIT_TAVAN_SON", 5000)

    def yuru_patla(*a, **k):
        raise TimeoutError("walk-forward bitmedi")
    monkeypatch.setattr(C, "yuru", yuru_patla)
    cikti = tmp_path / "dl1"
    kesim = (pd.Timestamp("2025-01-01") + pd.Timedelta(DL.BAR_NS[tf], unit="ns") * n).date().isoformat()
    assert E.main(["--tf", tf, "--kesim", kesim, "--cikti", str(cikti), "--rapor", str(tmp_path / "rapor")]) == 0
    pk, neden = DL.paket_yukle(cikti / f"DL1@{tf}.json", datetime.now(UTC) + timedelta(days=3), tf=tf)
    assert neden is None and pk is not None
    ham = json.loads((cikti / f"DL1@{tf}.json").read_text())
    assert ham["kapi"]["gecti"] is None and ham["metrikler"]["dilimler"] is None
    rapor = json.loads((tmp_path / "rapor" / f"dl1_rapor_{tf}.json").read_text())
    assert rapor["kapi"] is None and rapor["paket_yazildi"] is True
    assert "TAMAMLANMADI" in (tmp_path / "rapor" / f"dl1_rapor_{tf}.md").read_text()
