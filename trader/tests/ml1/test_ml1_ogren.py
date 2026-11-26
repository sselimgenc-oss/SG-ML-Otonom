"""ML1 sifirdan ogrenme (26.11 sahip karari): birim testleri.

Ogrenici YALNIZ gercekten acilip kapanan kagit islemlerden ogrenir: etiket = gercek net r_multiple > 0; baglanti trade_id + decision_id;
tohum paket / taban model / KUTU siniri / exitsim ile etiketleme / alinmayan aday ogrenmesi YOK. Ilk paket `min_islem` kapanan islemden sonra."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("pyarrow")

import ml1_motor_destek as T  # noqa: E402

from trader_engine import ml1_gate as MG  # noqa: E402
from trader_engine import ml1_ogren as OG  # noqa: E402
from trader_ml.ml1 import model as M  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
K = len(M.feature_names())
SINYAL = M.feature_names().index("stop_dist_atr")           # sentetik veride etiketi belirleyen ozellik


class SahteDefter:
    """Yalniz `list_closed_trades` (kapanan islemler: trade_id, decision_id, pair, side, r_multiple, exit_ts, exit_reason)."""

    def __init__(self) -> None:
        self.kapanan: list = []

    def kapat(self, trade_id: int, decision_id: int, pair: str, side: str, r: float | None, exit_ts: datetime) -> None:
        self.kapanan.append(SimpleNamespace(trade_id=trade_id, decision_id=decision_id, pair=pair, side=side, r_multiple=r, exit_ts=exit_ts,
                                            exit_reason="stop"))

    def list_closed_trades(self, since=None, until=None, limit=200):
        return [t for t in self.kapanan if (since is None or t.exit_ts >= since) and (until is None or t.exit_ts < until)][:limit]


def _x(rng, y: int) -> list[float]:
    v = rng.normal(size=K)
    v[SINYAL] = 1.0 + 2.0 * y + 0.3 * rng.normal()          # y=1 -> buyuk stop_dist_atr: ogrenilebilir sinyal
    return [float(a) for a in v]


def _ogrenici(tmp: Path, defter, **kw) -> OG.Ml1Ogrenici:
    og = OG.Ml1Ogrenici(tmp / "og", tmp / "models" / "ml1_package.json", now_fn=lambda: NOW, ledger=defter, **kw)
    assert og.baslat(NOW)
    return og


def _al(og: OG.Ml1Ogrenici, i: int, *, tf="1h", y=None, pair="BTC/USDT", side="long", rng=None, gun_once: float = 5.0) -> int:
    """i. islem: alinir (x kaydi) -- trade_id = decision_id = 1000 + i. Doner etiket."""
    rng = rng or np.random.default_rng(i)
    y = int(rng.random() < 0.5) if y is None else y
    ts = NOW - timedelta(days=gun_once) + timedelta(hours=7 * (i % 100) + i // 100)      # hep gecmiste (< NOW)
    og.islem_alindi({"pair": pair, "tf": tf, "setup": "T1", "arm_id": f"T1@{tf}", "group": "PULLBACK_1LEG", "side": side, "entry_ref": 100.0,
                     "stop": 99.0, "target": None, "stop_dist_atr": 1.0, "decision_ts": ts.isoformat(), "decision_id": 1000 + i,
                     "trade_id": 1000 + i, "x": _x(rng, y)})
    return y


def _kapat(defter: SahteDefter, og: OG.Ml1Ogrenici, i: int, y: int, *, pair="BTC/USDT", side="long") -> None:
    defter.kapat(1000 + i, 1000 + i, pair, side, 0.8 if y else -1.0, NOW - timedelta(hours=1))


# ================================================================================================================ saf matematik
def _tampon(n: int, *, yas_gun=0.0, ayri_olay=True, seed=0, y=None):
    rng = np.random.default_rng(seed)
    yy = (rng.random(n) < 0.5).astype(float) if y is None else np.asarray(y, float)
    X = np.array([_x(rng, int(v)) for v in yy]) if n else np.zeros((0, K))
    base = pd.Timestamp(NOW) - pd.Timedelta(days=yas_gun)
    ts = [base - pd.Timedelta(hours=10 * i) if ayri_olay else base - pd.Timedelta(hours=i) for i in range(n)]
    d = pd.DataFrame({"k": [f"p|a|long|{i}" for i in range(n)], "decision_ts": pd.to_datetime(ts, utc=True), "y": yy,
                      "pair": "BTC/USDT", "side": "long", "tf": "1h"})
    return d, X


def test_uydur_veri_yok_ya_da_tek_sinif_none():
    d, X = _tampon(0)
    assert OG.uydur(d, X, NOW) is None
    d, X = _tampon(5, yas_gun=OG.PENCERE_GUN + 50)                      # pencere disi
    assert OG.uydur(d, X, NOW) is None
    d, X = _tampon(30, y=np.ones(30))                                   # tek sinif
    assert OG.uydur(d, X, NOW) is None


def test_uydur_sifir_merkezli_kendi_standardizasyonu_ve_kutu_siniri_yok():
    d, X = _tampon(300, seed=3)
    r = OG.uydur(d, X, NOW)
    assert r["n_sonuc"] == 300
    # standardizasyon KENDI verisinden (sabit bir tabandan degil)
    st = M.fit_standardizer(X)
    assert np.allclose(r["st"]["mean"], st["mean"]) and np.allclose(r["st"]["std"], st["std"])
    # sinyal sutunu pozitif ogrenilir; 0,25'lik taban-kutusu YOK (tabana bagli degil)
    assert r["coef"][SINYAL] > 0.25
    # sifir merkezli: sinyalsiz sutunlarin agirliklari ridge ile sifira yakin
    other = np.delete(r["coef"], SINYAL)
    assert np.abs(other).max() < r["coef"][SINYAL]
    # girdi sirasindan bagimsiz (kanonik sira)
    perm = np.random.default_rng(1).permutation(len(d))
    r2 = OG.uydur(d.iloc[perm].reset_index(drop=True), X[perm], NOW)
    assert np.allclose(r["coef"], r2["coef"]) and r["b"] == pytest.approx(r2["b"])


def test_uydur_yari_omur_30_gun_eski_sonuc_az_agirlik():
    assert OG.YARI_OMUR_GUN == 30.0
    d, X = _tampon(40, yas_gun=0.0, seed=1)
    old, Xo = _tampon(40, yas_gun=60.0, seed=2)
    old["k"] = "e" + old["k"]
    dd, XX = pd.concat([d, old], ignore_index=True), np.vstack([X, Xo])
    r = OG.uydur(dd, XX, NOW)
    assert 40.0 < r["n_etkin"] <= 40 + 40 * 0.25 + 1e-9                # >= 60 gunluk (2+ yari omur) sonuclar en cok 1/4 agirlikta


def test_denetle_paket_gecerliligi_esik_ozellik_adlari():
    d, X = _tampon(120, seed=4)
    r = OG.uydur(d, X, NOW)
    yeni = OG.yeni_paket(r, esik=0.5, surum=1, simdi=NOW)
    assert OG.denetle(yeni, 0.5)[0] is None and M.verify_package(yeni) is None
    assert yeni["threshold"] == 0.5 and yeni["feature_names"] == M.feature_names() and yeni["online"]["kaynak"] == "gercek_kagit_islemleri"
    assert OG.denetle(yeni, 0.6)[0].startswith("esik_ayarla_uyusmuyor")           # esik config'ten sabit
    bad = json.loads(json.dumps(yeni))
    bad["weights"]["coef"][0] = None
    assert OG.denetle(bad, 0.5)[0] is not None
    bad = json.loads(json.dumps(yeni))
    bad["sha256"] = "0" * 64
    assert OG.denetle(bad, 0.5)[0].startswith("paket_gecersiz")
    bad = json.loads(json.dumps(yeni))
    bad["feature_names"] = bad["feature_names"][:-1]
    bad["weights"]["coef"] = bad["weights"]["coef"][:-1]
    for k in ("fill", "mean", "std"):
        bad["standardization"][k] = bad["standardization"][k][:-1]
    bad["sha256"] = M.package_hash(bad)
    assert OG.denetle(bad, 0.5)[0] == "ozellik_adlari_kodla_uyusmuyor"
    assert "taban" not in json.dumps(yeni.get("online", {}))                       # tohum/taban paket kavrami yok


def test_ozellik_adlari_yalniz_giris_zaman_dilimleri_ve_18_grup():
    names = M.feature_names()
    assert [n for n in names if n.startswith("tf_")] == ["tf_1h", "tf_4h", "tf_1d"] and "tf_15m" not in names
    assert len([n for n in names if n.startswith("grp_")]) == 18 and "grp_CANDLE_STAR3" not in names
    from trader_ml.ml1 import data as D
    assert D.TFS == ("15m", "1h", "4h", "1d") and M.TFS == D.MODEL_TFS == ("1h", "4h", "1d")      # 15m veri/cikis hatti icin KALIR


# ================================================================================================================ ogrenici: gercek islemlerden
def test_ilk_paket_yalniz_min_islem_kapanan_islemden_sonra(tmp_path):
    defter = SahteDefter()
    og = _ogrenici(tmp_path, defter, min_islem=12, esik=0.5)
    pk = tmp_path / "models" / "ml1_package.json"
    ys = [_al(og, i, y=i % 2) for i in range(14)]
    for i in range(11):                                                 # 11 kapanan < min_islem 12
        _kapat(defter, og, i, ys[i])
        og.adim(NOW)                                                    # her adim: yeni sonuc olsa da paket YOK
        assert not pk.exists(), i
    assert og.n_kapali == 11 and og.asama() == "ogrenme"
    dur = json.loads((tmp_path / "og" / "durum.json").read_text())
    assert dur["asama"] == "ogrenme" and dur["kapali_islem"] == 11 and dur["min_islem"] == 12 and dur["surum"] == 0
    _kapat(defter, og, 11, ys[11])                                      # 12. kapanan islem: ilk paket
    og.adim(NOW)
    assert pk.exists() and og.surum == 1 and og.asama() == "suzme"
    got, why = M.load_package(pk)
    assert why is None and got["threshold"] == 0.5 and got["online"]["surum"] == 1 and got["n_train"] == 12
    dur = json.loads((tmp_path / "og" / "durum.json").read_text())
    assert dur["asama"] == "suzme" and dur["kapali_islem"] == 12 and dur["surum"] == 1 and dur["son_guncelleme"] and dur["guncellendi"]
    assert not (tmp_path / "models" / "ml1_package.son_iyi.json").exists()      # onceki ogrenilmis paket yoktu: son_iyi de yok (tohum YOK)
    # her yeni kapanan islemde (adim basina en cok bir kez) yeniden uydurulur
    _kapat(defter, og, 12, ys[12])
    og.adim(NOW)
    assert og.surum == 2 and (tmp_path / "models" / "ml1_package.son_iyi.json").exists()
    og.adim(NOW)                                                        # yeni sonuc yok: yeniden uydurma yok
    assert og.surum == 2
    _kapat(defter, og, 13, ys[13])
    og.adim(NOW)
    assert og.surum == 3


def test_min_islem_tf_her_zaman_dilimi_icin_alt_sinir(tmp_path):
    defter = SahteDefter()
    og = _ogrenici(tmp_path, defter, min_islem=6, min_islem_tf=3)
    pk = tmp_path / "models" / "ml1_package.json"
    for i in range(8):                                                  # 8 islem (>= 6) ama hepsi 1h: 4h/1d icin 3 sart saglanmadi
        _kapat(defter, og, i, _al(og, i, tf="1h", y=i % 2))
        og.adim(NOW)
    assert og.n_kapali == 8 and not pk.exists() and not og.esik_asildi()
    for j, tf in enumerate(("4h", "4h", "4h", "1d", "1d")):
        i = 100 + j
        _kapat(defter, og, i, _al(og, i, tf=tf, y=j % 2))
        og.adim(NOW)
    assert not pk.exists()                                              # 1d yalniz 2
    i = 200
    _kapat(defter, og, i, _al(og, i, tf="1d", y=1))
    og.adim(NOW)
    assert pk.exists() and og.n_tf["1h"] == 8 and og.n_tf["4h"] == 3 and og.n_tf["1d"] == 3
    # min_islem_tf = 0 -> zaman dilimi sarti yok
    og2 = _ogrenici(tmp_path / "b", SahteDefter(), min_islem=6, min_islem_tf=0)
    og2.n_kapali, og2.n_tf = 6, __import__("collections").Counter({"1h": 6})
    assert og2.esik_asildi()


def test_etiket_gercek_net_r_multiple_pozitif_ve_siki_baglanti(tmp_path):
    defter = SahteDefter()
    og = _ogrenici(tmp_path, defter, min_islem=1000)
    _al(og, 1, y=1)
    _al(og, 2, y=1)
    _al(og, 3, y=0)
    _al(og, 4, y=0)
    _al(og, 5, y=0)
    defter.kapat(1001, 1001, "BTC/USDT", "long", 0.0001, NOW - timedelta(hours=1))      # +: y=1
    defter.kapat(1002, 1002, "BTC/USDT", "long", 0.0, NOW - timedelta(hours=1))         # tam 0: y=0 (> 0 degil)
    defter.kapat(1003, 9999, "BTC/USDT", "long", 2.0, NOW - timedelta(hours=1))         # ayni trade_id, FARKLI decision_id: ogrenilmez
    defter.kapat(7777, 1004, "BTC/USDT", "long", 2.0, NOW - timedelta(hours=1))         # ayni zaman/cift/yon/arm ama FARKLI trade_id: eslesmez
    defter.kapat(1005, 1005, "BTC/USDT", "short", 2.0, NOW - timedelta(hours=1))        # yon uyusmuyor: ogrenilmez
    og.adim(NOW)
    sonuc = {r["trade_id"]: r for r in map(json.loads, (tmp_path / "og").glob("sonuclar-*.jsonl").__next__().read_text().splitlines()) if "y" in r}
    assert set(sonuc) == {1001, 1002} and sonuc[1001]["y"] == 1 and sonuc[1002]["y"] == 0
    assert sonuc[1001]["r_net"] == pytest.approx(0.0001) and len(sonuc[1001]["x"]) == K
    assert og.n_kapali == 2 and og.sayac["kapandi_eslesme_hatasi"] == 2 and set(og.bekleyen) == {1004}      # 1004 hala bekler: kapanmadi
    assert og.sayac["kapandi_eslesme_hatasi"] == 2


def test_acik_islem_beklenir_ve_alinmayan_aday_dosyaya_yazilmaz(tmp_path):
    defter = SahteDefter()
    og = _ogrenici(tmp_path, defter, min_islem=1)
    _al(og, 1, y=1)
    og.adim(NOW)                                                        # defterde kapanmadi: sonuc yok
    assert og.n_kapali == 0 and set(og.bekleyen) == {1001}
    dosyalar = sorted(p.name for p in (tmp_path / "og").glob("*.jsonl"))
    assert dosyalar == ["alinanlar-2026-11.jsonl"] or dosyalar == [p for p in dosyalar if p.startswith("alinanlar-")]
    assert not hasattr(og, "kaydet") and not hasattr(og, "coz") and not hasattr(og, "taban")     # puanlanan-aday / exitsim / taban hatti kalmadi
    assert not (tmp_path / "og" / "adaylar-2026-11.jsonl").exists()


def test_yeniden_baslatma_cift_sayim_yok_ve_bekleyenler_geri_gelir(tmp_path):
    defter = SahteDefter()
    og = _ogrenici(tmp_path, defter, min_islem=1000)
    for i in range(5):
        _al(og, i, y=i % 2)
    for i in range(3):
        _kapat(defter, og, i, i % 2)
    og.adim(NOW)
    assert og.n_kapali == 3 and set(og.bekleyen) == {1003, 1004}
    og2 = _ogrenici(tmp_path, defter, min_islem=1000)                   # ayni dizin
    assert og2.n_kapali == 3 and set(og2.bekleyen) == {1003, 1004} and len(og2._sn) == 3
    assert og2.islem_alindi({"pair": "BTC/USDT", "tf": "1h", "setup": "T1", "arm_id": "T1@1h", "side": "long", "decision_ts": NOW.isoformat(),
                             "decision_id": 1000, "trade_id": 1000, "x": [0.0] * K}) is False          # bilinen trade_id tekrar yazilmaz
    og2.adim(NOW)
    assert og2.n_kapali == 3


def test_geri_donus_onceki_ogrenilmis_pakete_ya_da_hicbirine_tohuma_asla(tmp_path):
    defter = SahteDefter()
    og = _ogrenici(tmp_path, defter, min_islem=6)
    pk, iyi = tmp_path / "models" / "ml1_package.json", tmp_path / "models" / "ml1_package.son_iyi.json"
    ys = [_al(og, i, y=i % 2) for i in range(8)]
    for i in range(6):
        _kapat(defter, og, i, ys[i])
    og.adim(NOW)                                                        # surum 1 (onceki yok)
    assert og.surum == 1 and pk.exists() and not iyi.exists()
    b1 = pk.read_bytes()
    # surum 1 bozulur -> geri donus: onceki ogrenilmis paket YOK -> paket silinir (ogrenme asamasi), 24 saat duraklatma
    pk.write_text("bozuk", encoding="utf-8")
    og.adim(NOW + timedelta(minutes=15))
    assert not pk.exists() and og.asama() == "ogrenme" and og.sayac["geri_donus"] == 1
    assert og.son_geri_donus["son_iyi"] is False and og.duraklat_bitis is not None
    _kapat(defter, og, 6, ys[6])
    og.adim(NOW + timedelta(hours=1))                                   # duraklatma: yeni sonuc olsa da uydurma yok
    assert not pk.exists() and og.n_kapali == 7
    og.adim(NOW + timedelta(hours=25))                                  # duraklatma bitti: biriken sonuc ile yeniden uydurulur
    assert pk.exists() and og.surum == 2
    _kapat(defter, og, 7, ys[7])
    og.adim(NOW + timedelta(hours=26))
    assert og.surum == 3
    b2 = pk.read_bytes()                                                # surum 3
    assert b2 != b1
    # ikinci ogrenilmis paket sonrasi bir yenisi yazilir ve bozulursa: onceki ogrenilmis pakete (son_iyi) donulur
    _al(og, 8, y=1)
    _kapat(defter, og, 8, 1)
    og.adim(NOW + timedelta(hours=27))
    assert og.surum == 4 and iyi.read_bytes() == b2                     # yeni yazimda onceki ogrenilmis paket son_iyi olur
    pk.write_text("{bozuk", encoding="utf-8")
    og.adim(NOW + timedelta(hours=28))
    assert pk.read_bytes() == b2 and og.son_geri_donus["son_iyi"] is True
    got, why = M.load_package(pk)
    assert why is None and got["online"]["surum"] == 3


def test_geri_donus_gecme_orani_sifir_ve_kapi_hatasi(tmp_path):
    defter = SahteDefter()
    kapi = SimpleNamespace(counters={"ml1_hata": 0, "ml1_gecti": 0, "ml1_ayni_olay": 0, "ml1_esik_alti": 0}, paket_durumu=lambda: (False, None))
    og = _ogrenici(tmp_path, defter, kapi=kapi, min_islem=4)
    for i in range(5):
        _kapat(defter, og, i, _al(og, i, y=i % 2))
    og.adim(NOW)
    assert og.surum == 1 and og._izle is not None
    pk = tmp_path / "models" / "ml1_package.json"
    kapi.counters["ml1_esik_alti"] = 40                                 # 40 aday, hicbiri gecmedi: paket her seyi reddediyor
    og.adim(NOW + timedelta(minutes=15))
    assert not pk.exists() and og.son_geri_donus["neden"].startswith("gecme_orani")
    # kapi puanlama hatasi
    og2 = _ogrenici(tmp_path / "x", SahteDefter(), kapi=kapi, min_islem=1)
    og2._izle = {"sha": "a", "hata0": 0, "gecti0": 0, "alt0": 0}
    kapi.counters["ml1_hata"] = 1
    og2.adim(NOW)
    assert og2.son_geri_donus["neden"] == "kapi_puanlama_hatasi"
    # %100 gecme KORUNMAZ (gecmeye dair ust sinir yok: sifirdan ogrenmede normal)
    kapi2 = SimpleNamespace(counters={"ml1_hata": 0, "ml1_gecti": 50, "ml1_ayni_olay": 0, "ml1_esik_alti": 0}, paket_durumu=lambda: (False, None))
    og3 = _ogrenici(tmp_path / "y", SahteDefter(), kapi=kapi2, min_islem=1)
    og3._izle = {"sha": "a", "hata0": 0, "gecti0": 0, "alt0": 0}
    og3.adim(NOW)
    assert og3.son_geri_donus is None and og3._izle is None


def test_kuru_calisir_paketi_yazmaz(tmp_path):
    defter = SahteDefter()
    og = _ogrenici(tmp_path, defter, min_islem=4, kuru=True)
    for i in range(6):
        _kapat(defter, og, i, _al(og, i, y=i % 2))
    og.adim(NOW)
    assert not (tmp_path / "models" / "ml1_package.json").exists() and og.surum == 0 and og.asama() == "ogrenme"
    upd = [json.loads(x) for x in (tmp_path / "og" / "guncellemeler.jsonl").read_text().splitlines()]
    assert upd and upd[-1]["sonuc"] == "kuru"


def test_adim_istisnasi_firlatmaz_ve_durum_alanlari(tmp_path):
    class Bozuk(SahteDefter):
        def list_closed_trades(self, *a, **k):
            raise RuntimeError("defter okunamadi")
    og = _ogrenici(tmp_path, Bozuk(), min_islem=1)
    _al(og, 1, y=1)
    og.adim(NOW)                                                        # firlatmaz
    assert og.sayac["defter_hata"] == 1
    dur = json.loads((tmp_path / "og" / "durum.json").read_text())
    for k in ("asama", "kapali_islem", "min_islem", "min_islem_tf", "surum", "son_guncelleme", "guncellendi", "esik", "kapali_islem_tf"):
        assert k in dur, k
    assert dur["asama"] == "ogrenme" and dur["esik"] == 0.5 and dur["min_islem_tf"] == 0
    assert not hasattr(OG, "KUTU_COEF") and not hasattr(OG, "N0") and not hasattr(OG, "TOHUM")


# ================================================================================================================ kapi: yalniz ALINAN adayin x'i
@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    d = tmp_path_factory.mktemp("ogren_unit_hist") / "hist"
    T.write_history(d)
    return d


def _frame(tf, pair, i, hist, setup, side="long"):
    trig, h4 = __import__("trader_ml.ml1.data", fromlist=["x"]).load_pair_tf(hist, pair, tf)
    Dts = trig.index[i] + pd.Timedelta(tf)
    w = trig.iloc[max(0, i - 1499):i + 1]
    h4w = h4[h4.index + pd.Timedelta("4h") <= Dts].iloc[-1500:]
    px = float(trig["close"].iloc[i])
    r = {"setup": setup, "side": side, "planned_entry": px, "planned_stop": px * 0.99, "planned_target": None, "stop_dist_atr": 1.5}
    row = SimpleNamespace(signal=True, setup=setup, side=side, arm_id=f"{setup}@{tf}", tf=tf, pair=pair, bar_close_ts=Dts.to_pydatetime())
    return Dts.to_pydatetime(), r, w, h4w, SimpleNamespace(last=row)


@pytest.mark.parametrize("paketli", [False, True])
def test_kapi_yalniz_alinan_adayin_vektorunu_ogreniciye_verir(hist, tmp_path, paketli):
    """3 aday puanlanir/gecer; yalniz biri GERCEKTEN alinir (note_taken): ogreniciye tam bir kayit gider, digerleri hicbir yere yazilmaz."""
    pk = tmp_path / "p.json"
    if paketli:
        T.write_package(pk, threshold=0.0)
    g = MG.Ml1Gate({"aktif": True, "paket_yolu": str(pk)})
    alinanlar = []
    g.ogren = SimpleNamespace(islem_alindi=lambda r: alinanlar.append(r))
    Dd = None
    cs = []
    for setup in ("T1", "R1", "MF1-YUTAN"):
        Dd, r, w, h4w, c = _frame("1h", "BTC/USDT", 3000, hist, setup)
        g.observe("BTC/USDT", Dd, "1h", r, w, h4w)
        cs.append(c)
    g.prepare("BTC/USDT", Dd, tuple(cs))
    assert alinanlar == []                                              # puanlama/gecirme tek basina HICBIR sey kaydetmez
    g.note_entry("BTC/USDT", "long", "1h", Dd, "R1@1h")                 # olay penceresi (kayit degil)
    assert alinanlar == []
    g.note_taken("BTC/USDT", "R1@1h", "long", Dd, 77, 55)
    assert len(alinanlar) == 1
    a = alinanlar[0]
    assert a["arm_id"] == "R1@1h" and a["trade_id"] == 55 and a["decision_id"] == 77 and a["pair"] == "BTC/USDT" and a["tf"] == "1h"
    assert a["decision_ts"] == pd.Timestamp(Dd).isoformat() and len(a["x"]) == K
    assert a["x"][M.feature_names().index("tf_1h")] == 1.0 and a["x"][M.feature_names().index("tf_4h")] == 0.0
    assert a["x"][M.feature_names().index("grp_RANGE_EDGE")] == 1.0
    g.note_taken("BTC/USDT", "T1@4h", "long", Dd, 78, 56)               # bu adimda puanlanmamis aday: kayit yok
    assert len(alinanlar) == 1 and g.counters["ml1_ogren_x_yok"] == 1
    g.end_step()
    g.note_taken("BTC/USDT", "R1@1h", "long", Dd, 79, 57)               # adim bitti: vektorler birakildi
    assert len(alinanlar) == 1


def test_ogrenici_yok_ya_da_kayit_hatasi_kapi_kararini_etkilemez(hist, tmp_path):
    g = MG.Ml1Gate({"aktif": True, "paket_yolu": str(tmp_path / "yok.json")})
    Dd, r, w, h4w, c = _frame("1h", "BTC/USDT", 3000, hist, "T1")
    g.observe("BTC/USDT", Dd, "1h", r, w, h4w)
    g.prepare("BTC/USDT", Dd, (c,))
    g.note_taken("BTC/USDT", "T1@1h", "long", Dd, 1, 1)                 # ogren=None: sessiz
    assert g.verdict(c.last).code is None
    g.end_step()
    g.ogren = SimpleNamespace(islem_alindi=lambda r: (_ for _ in ()).throw(OSError("disk")))
    g.observe("BTC/USDT", Dd, "1h", r, w, h4w)
    g.prepare("BTC/USDT", Dd, (c,))
    g.note_taken("BTC/USDT", "T1@1h", "long", Dd, 1, 1)                 # firlatmaz, sayar
    assert g.counters["ml1_ogren_log_hata"] == 1 and g.verdict(c.last).code is None
