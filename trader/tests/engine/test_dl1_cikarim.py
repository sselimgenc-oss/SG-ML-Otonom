"""DL1 cikarimi (dl1_cikarim): ileri gecis (elle kurulmus agirliklar + saf-python referans), kanallar (nedensellik/sizinti yok), paket dogrulama
(sha, son kullanma, bozuk, kapi), puanlama (bos mum / doluluk / kapsam), modul bagimliliklari."""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from trader_engine import dl1_cikarim as DL

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dl1_support as S  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)
SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture(autouse=True)
def _temiz():
    DL._ONBELLEK.clear()


def test_parametre_sayisi_30_50_bin_ve_kanal_listesi():
    assert 30_000 <= DL.parametre_sayisi() <= 50_000
    assert DL.N_KANAL == 11 and DL.KANALLAR[8:] == ("sinif_kripto", "sinif_hisse", "sinif_emtia") and DL.PENCERE == 96


def _ref_conv(x, w, b, adim):
    """Saf-python referans: x (T, Cin), w (Cout, Cin, K)."""
    T, K = x.shape[0], w.shape[2]
    out = []
    for t in range(0, T - K + 1, adim):
        out.append([b[o] + sum(w[o, c, k] * x[t + k, c] for c in range(x.shape[1]) for k in range(K)) for o in range(w.shape[0])])
    return np.array(out)


def test_ileri_saf_python_referansla_ayni():
    rg = np.random.default_rng(5)
    ag = {ad: rg.normal(0, 0.2, sek) for ad, sek in DL.agirlik_sekilleri().items()}
    x = rg.normal(0, 1, (2, DL.PENCERE, DL.N_KANAL))
    got = DL.ileri(ag, x)
    for bi in range(2):
        z = x[bi]
        for ad, tur, _g, _c, _k, adim in DL.KATMANLAR:
            if tur == "conv":
                z = np.maximum(_ref_conv(z, ag[ad + ".w"], ag[ad + ".b"], adim), 0.0)
        v = np.r_[z.mean(axis=0), z.max(axis=0)]
        v = np.maximum(ag["d1.w"] @ v + ag["d1.b"], 0.0)
        assert np.allclose(got[bi], ag["head.w"] @ v + ag["head.b"], atol=1e-9)


def test_ileri_elle_kurulmus_agirliklar():
    ag = S.sifir_agirlik()
    ag["c1.w"][0, 0, 4] = 1.0          # c1 kanal 0 [t] = relu(x[t+4, 0])
    ag["c2.w"][0, 0, 0] = 1.0          # c2 kanal 0 [u] = c1[2u]
    ag["c3.w"][0, 0, 0] = 1.0          # c3 kanal 0 [v] = c2[2v] = relu(x[4v+4, 0]), v = 0..19
    ag["d1.w"][0, 0] = 1.0             # ortalama
    ag["d1.w"][1, 64] = 1.0            # maksimum (havuz vektorunde 64. = ilk kanalin maksimumu)
    ag["head.w"][0, 0] = 1.0
    ag["head.w"][1, 1] = 2.0
    ag["head.b"][2] = 0.5
    x = np.random.default_rng(1).normal(0, 1, (DL.PENCERE, DL.N_KANAL))
    ch = np.maximum(x[4:4 + 4 * 20:4, 0], 0.0)
    assert len(ch) == 20
    z = DL.ileri(ag, x)[0]
    assert z == pytest.approx([ch.mean(), 2.0 * ch.max(), 0.5])


def test_sigmoid_ve_olcekle_sinif_kanali_dokunulmaz():
    assert DL.sigmoid(0.0) == 0.5 and DL.sigmoid(1e9) == pytest.approx(1.0)
    x = np.zeros((4, DL.N_KANAL))
    x[:, 0] = 1e6
    x[:, 9] = 1.0
    z = DL.olcekle(x, np.zeros(DL.N_KANAL), np.ones(DL.N_KANAL))
    assert (z[:, 0] == DL.KIRP).all() and (z[:, 9] == 1.0).all()


def _mumlar(n=300, tohum=2):
    d = S.seri(T0, n, tohum)
    return [d[k].to_numpy() for k in ("open", "high", "low", "close", "volume")]


def test_kanallar_nedensel_gelecek_degisince_gecmis_ayni():
    o, h, l, c, v = _mumlar()
    tam = DL.kanallar(o, h, l, c, v, 1)
    kes = DL.kanallar(o[:250], h[:250], l[:250], c[:250], v[:250], 1)
    assert np.array_equal(tam[:250], kes, equal_nan=True)            # sizinti yok: satir i yalniz <= i'ye bakar
    o2, h2, l2, c2, v2 = (a.copy() for a in (o, h, l, c, v))
    c2[260:] *= 1.5; h2[260:] *= 1.5; v2[260:] *= 3
    degisik = DL.kanallar(o2, h2, l2, c2, v2, 1)
    assert np.array_equal(tam[:260], degisik[:260], equal_nan=True)
    assert np.isfinite(tam[DL.HACIM_PENCERE - 1:]).all() and not np.isfinite(tam[:DL.HACIM_PENCERE - 1, 3]).any()
    assert (tam[:, 8:] == [0, 1, 0]).all()


def test_dolu_maske_ve_doluluk():
    h = np.array([2.0, 1.0, 3.0, np.nan]); l = np.array([1.0, 1.0, 2.0, 1.0]); v = np.array([5.0, 5.0, 0.0, 5.0])
    assert DL.dolu_maske(h, l, v).tolist() == [True, False, False, False]
    ts = (np.arange(96) * 3_600_000_000_000).astype(np.int64)
    assert DL.pencere_doluluk_ok(ts)[-1]                                   # oran 1
    ts2 = (np.arange(96) * 2 * 3_600_000_000_000).astype(np.int64)         # her 2 saatte 1 mum: 96/191 = 0,503
    assert DL.pencere_doluluk_ok(ts2)[-1]
    ts3 = (np.arange(96) * 3 * 3_600_000_000_000).astype(np.int64)         # 96/286 < 0,5
    assert not DL.pencere_doluluk_ok(ts3)[-1] and DL.MIN_DOLU_ORAN == 0.5


# ------------------------------------------------------------------------------------------- paket
def test_paket_gecerli_ve_son_kullanma(tmp_path):
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0 - timedelta(days=1)))
    p, neden = DL.paket_yukle(yol, T0)
    assert neden is None and p.esik == 0.5 and p.siniflar["NVDA/USDT"] == 1
    p2, n2 = DL.paket_yukle(yol, T0 + timedelta(days=43.5))
    assert n2 is None
    # 24.11: 45 gun yalniz YAS UYARISI; eski paket yine yuklenir (aday uretir), Paket.eski() True doner
    p3, n3 = DL.paket_yukle(yol, T0 - timedelta(days=1) + timedelta(days=45))
    assert n3 is None and p3 is not None and p3.eski(T0 - timedelta(days=1) + timedelta(days=45)) and not p.eski(T0)
    assert DL.paket_yukle(yol, T0 + timedelta(days=400))[1] is None


def test_son_kullanma_alani_uzatilsa_da_45_gun_tavan(tmp_path):
    ol = T0 - timedelta(days=1)
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(ol, son=ol + timedelta(days=400)))
    p, neden = DL.paket_yukle(yol, ol + timedelta(days=46))
    assert neden is None and p.eski(ol + timedelta(days=46)) and p.son_kullanma == ol + timedelta(days=45)


@pytest.mark.parametrize("neden,degis", [
    ("hash", lambda p: p.update(esik=0.6)),                                   # icerik degisti, sha eski
    ("sema", lambda p: p.update(schema="dl1/9")),
    ("sema", lambda p: p.update(arm_id="DL1@4h")),
])
def test_paket_bozuk_reddedilir(tmp_path, neden, degis):
    p = S.paket_sozlugu(T0 - timedelta(days=1))
    degis(p)
    assert DL.paket_yukle(S.yaz(tmp_path / "p.json", p), T0) == (None, neden)


def test_paket_yok_bozuk_json_buyuk_kapi_kanal_agirlik(tmp_path):
    assert DL.paket_yukle(tmp_path / "yok.json", T0) == (None, "yok")
    assert DL.paket_yukle(S.yaz(tmp_path / "a.json", "{bozuk"), T0) == (None, "bozuk")
    assert DL.paket_yukle(S.yaz(tmp_path / "b.json", S.paket_sozlugu(T0, kapi=False)), T0)[1] is None     # 24.11: kapi.gecti False engellemez
    assert DL.paket_yukle(S.yaz(tmp_path / "c.json", S.paket_sozlugu(T0, kanallar=["x"])), T0) == (None, "kanal")
    p = S.paket_sozlugu(T0)
    p["agirliklar"]["c1.w"]["veri"] = p["agirliklar"]["c1.w"]["veri"][:-1]
    p["sha256"] = DL.paket_ozeti(p)
    assert DL.paket_yukle(S.yaz(tmp_path / "d.json", p), T0) == (None, "bozuk")
    q = S.paket_sozlugu(T0, esik=1.5)
    assert DL.paket_yukle(S.yaz(tmp_path / "e.json", q), T0) == (None, "bozuk")
    big = tmp_path / "big.json"
    big.write_bytes(b" " * (DL.MAX_PAKET_BAYT + 1))
    assert DL.paket_yukle(big, T0) == (None, "buyuk")


def test_paket_boyutu_10mb_alti(tmp_path):
    rg = np.random.default_rng(0)
    ag = {ad: rg.normal(0, 0.3, sek) for ad, sek in DL.agirlik_sekilleri().items()}
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0, agirlik=ag))
    assert yol.stat().st_size < 1_500_000 and yol.stat().st_size < DL.MAX_PAKET_BAYT
    p, _ = DL.paket_yukle(yol, T0)
    assert np.allclose(p.agirlik["c2.w"], np.round(ag["c2.w"], 7))


def test_arm_id_ve_paket_yolu_dort_zaman_dilimi():
    from trader_core.arm_time import ARM_TF_SECONDS
    assert DL.ZAMAN_DILIMLERI == ("15m", "1h", "4h", "1d")
    assert {tf: ns // 1_000_000_000 for tf, ns in DL.BAR_NS.items()} == ARM_TF_SECONDS
    assert DL.arm_id("15m") == "DL1@15m" and DL.paket_yolu("1d").name == "DL1@1d.json" and DL.paket_yolu().name == "DL1@1h.json" == DL.PAKET_YOLU.name
    with pytest.raises(ValueError):
        DL.arm_id("2h")


@pytest.mark.parametrize("tf", DL.ZAMAN_DILIMLERI)
def test_paket_zaman_dilimine_baglidir(tmp_path, tf):
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0 - timedelta(days=1), tf=tf))
    p, neden = DL.paket_yukle(yol, T0, tf=tf)
    assert neden is None and p.tf == tf
    diger = "1h" if tf != "1h" else "4h"
    DL._ONBELLEK.clear()
    assert DL.paket_yukle(yol, T0, tf=diger) == (None, "sema")            # baska zaman diliminin paketi bu dosyada kabul edilmez


def test_doluluk_orani_mum_biriminde_dort_zaman_dilimi():
    for tf, ns in DL.BAR_NS.items():
        ok2 = DL.pencere_doluluk_ok((np.arange(96) * 2 * ns).astype(np.int64), bar_ns=ns)[-1]      # her 2 mumda 1 dolu: %50 -> gecer
        ok3 = DL.pencere_doluluk_ok((np.arange(96) * 3 * ns).astype(np.int64), bar_ns=ns)[-1]      # her 3 mumda 1: gecmez
        assert ok2 and not ok3, tf


def test_paket_yasi(tmp_path):
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0 - timedelta(days=10)))
    d, yas, kalan = DL.paket_yasi_gun(yol, T0)
    assert d == "ok" and yas == pytest.approx(10) and kalan == pytest.approx(35)
    assert DL.paket_yasi_gun(tmp_path / "yok", T0)[0] == "yok"
    assert DL.paket_yasi_gun(S.yaz(tmp_path / "x.json", "{"), T0)[0] == "bozuk"
    d, yas, kalan = DL.paket_yasi_gun(S.yaz(tmp_path / "e.json", S.paket_sozlugu(T0 - timedelta(days=60))), T0)
    assert d == "eski" and kalan < 0                                             # 45 gunden yasli: durum eski (saglik uyarisi); paket yine yuklenir


# ------------------------------------------------------------------------------------------- puanla
def _paket(tmp_path, bl=2.0, bs=-2.0):
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0 - timedelta(days=1), agirlik=S.sifir_agirlik(bl, bs)))
    return DL.paket_yukle(yol, T0)[0]


def _ts(d):
    return d.index.tz_localize("UTC").as_unit("ns").asi8


def test_puanla_sabit_ag_ve_kapsam(tmp_path):
    p = _paket(tmp_path)
    d = S.seri(T0)
    a = [d[k].to_numpy() for k in ("open", "high", "low", "close", "volume")]
    r = DL.puanla(p, "BTC/USDT", _ts(d), *a)
    assert r[0] == pytest.approx(float(DL.sigmoid(2.0))) and r[1] == pytest.approx(float(DL.sigmoid(-2.0))) and r[3] > 0
    assert DL.puanla(p, "DOGE/USDT", _ts(d), *a) is None                      # kapsam disi
    assert DL.puanla(p, "BTC/USDT", _ts(d)[:100], *(x[:100] for x in a)) is None   # < 192 bar


def test_puanla_son_mum_bos_ya_da_pencere_seyrek_puan_yok(tmp_path):
    p = _paket(tmp_path)
    d = S.seri(T0, 500)
    a = [d[k].to_numpy().copy() for k in ("open", "high", "low", "close", "volume")]
    ts = _ts(d)
    b = [x.copy() for x in a]
    b[4][-1] = 0.0                                                            # son mum hacimsiz (seans kapali): puan yok
    assert DL.puanla(p, "NVDA/USDT", ts, *b) is None
    # seyrek: dolu mumlar her 4 saatte bir (seans bosluklari); 96 dolu mum 381 saate yayilir (< %50) -> puan yok
    m = np.zeros(len(ts), dtype=bool)
    m[-1::-4] = True
    c = [x.copy() for x in a]
    c[4][~m] = 0.0
    assert DL.puanla(p, "NVDA/USDT", ts, *c) is None
    # her 2 saatte bir: 192 saatlik pencere sinirinda dolu bar sayisi yetersiz (500 bar -> 250 dolu); kabul (96 dolu <= 191 saat)
    m2 = np.zeros(len(ts), dtype=bool)
    m2[-1::-2] = True
    e = [x.copy() for x in a]
    e[4][~m2] = 0.0
    assert DL.puanla(p, "NVDA/USDT", ts, *e) is not None


def test_puanla_gelecek_bar_sizintisi_yok(tmp_path):
    """Ayni son bara kadar olan veri ile (daha uzun gecmis eklenerek) puan degismez; yalniz son 216 dolu bar kullanilir."""
    rg = np.random.default_rng(9)
    ag = {ad: rg.normal(0, 0.15, sek) for ad, sek in DL.agirlik_sekilleri().items()}
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0 - timedelta(days=1), agirlik=ag))
    p = DL.paket_yukle(yol, T0)[0]
    d = S.seri(T0, 600)
    a = [d[k].to_numpy() for k in ("open", "high", "low", "close", "volume")]
    r1 = DL.puanla(p, "BTC/USDT", _ts(d), *a)
    r2 = DL.puanla(p, "BTC/USDT", _ts(d)[-250:], *(x[-250:] for x in a))
    assert r1 is not None and r1 == pytest.approx(r2)


# ------------------------------------------------------------------------------------------- bagimlilik
def test_modul_yalniz_numpy_ve_stdlib_alir():
    tree = ast.parse((SRC / "trader_engine" / "dl1_cikarim.py").read_text(encoding="utf-8"))
    imps = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imps |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            imps.add(n.module.split(".")[0])
    assert imps <= {"__future__", "hashlib", "json", "math", "threading", "dataclasses", "datetime", "pathlib", "numpy"}, imps


def test_kol_dosyasi_torch_ve_trader_ml_almaz():
    tree = ast.parse((SRC / "trader_engine" / "strategies" / "arms" / "dl1.py").read_text(encoding="utf-8"))
    imps = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imps |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}
    assert not imps & {"torch", "trader_ml", "scipy", "sklearn", "lightgbm"}


def test_paket_gelecekten_damgali_erken_ve_yasi_simdi_zorunlu(tmp_path):
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0 + timedelta(hours=1)))
    assert DL.paket_yukle(yol, T0) == (None, "erken")
    assert DL.paket_yukle(yol, T0 + timedelta(hours=1))[1] is None
    with pytest.raises(TypeError):
        DL.paket_yasi_gun(yol)                                  # simdi zorunlu (motorda duvar saati yok)


def test_ufuk_canli_zaman_stopu_ile_ayni():
    from trader_core import signals
    assert DL.UFUK == signals.TIME_STOP_BARS


@pytest.mark.parametrize("ek", [{"ufuk": 24}, {"tf": "4h"}, {"etiket": {"stop_atr": 2.0, "hedef_atr": 3.0}},
                                {"etiket": {"stop_atr": 1.5, "hedef_atr": 4.0}}])
def test_paket_etiket_ufuk_tf_uyusmazsa_reddedilir(tmp_path, ek):
    """25.11 denetim #20: farkli etiket/ufuk/zaman dilimiyle egitilmis paket (ozeti dogru olsa bile) reddedilir."""
    yol = S.yaz(tmp_path / "p.json", S.paket_sozlugu(T0 - timedelta(days=1), **ek))
    p, neden = DL.paket_yukle(yol, T0)
    assert p is None and neden in ("bozuk", "sema")   # tf uyusmazligi arm_id ile de yakalanir
