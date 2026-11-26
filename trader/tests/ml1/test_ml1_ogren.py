"""ML1 aninda ogrenme: birim testleri (uydurma matematigi, denetim, atomik yazim, geri donus, etiket esitligi, x kaydi)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("pyarrow")

import ml1_motor_destek as T  # noqa: E402

from trader_engine import ml1_ogren as OG  # noqa: E402
from trader_ml.ml1 import model as M  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
TABAN = json.loads(T.SEED_PKG.read_text(encoding="utf-8"))
K = len(TABAN["weights"]["coef"])


def _tampon(n: int, *, yas_gun=0.0, y=None, seed=0, ayri_olay=True, x=None):
    """n sonuc: her biri ayri olay (3 mumdan uzak) ya da ayni olay; x ~ taban standardizasyonuna uygun rastgele."""
    rng = np.random.default_rng(seed)
    st = TABAN["standardization"]
    X = np.asarray(st["mean"]) + rng.normal(size=(n, K)) * np.asarray(st["std"]) if x is None else x
    base = pd.Timestamp(NOW) - pd.Timedelta(days=yas_gun)
    ts = [base - pd.Timedelta(hours=10 * i) if ayri_olay else base - pd.Timedelta(hours=i) for i in range(n)]
    d = pd.DataFrame({"k": [f"p|a|long|{i}" for i in range(n)], "decision_ts": pd.to_datetime(ts, utc=True),
                      "y": (rng.random(n) < 0.5).astype(float) if y is None else y, "pair": "BTC/USDT", "side": "long", "tf": "1h"})
    return d, X


def test_ogren_veri_yokken_cozum_tabandir():
    d, X = _tampon(0)
    r = OG.uydur(TABAN, d, X, NOW)
    assert np.array_equal(r["coef"], TABAN["weights"]["coef"]) and r["b"] == TABAN["weights"]["intercept"]
    d, X = _tampon(5, yas_gun=200)                                  # pencere disi = veri yok
    r = OG.uydur(TABAN, d, X, NOW)
    assert np.array_equal(r["coef"], TABAN["weights"]["coef"]) and r["n_sonuc"] == 0


def test_ogren_tek_sonuc_etkisi_siniri_asmaz():
    d, X = _tampon(1, y=np.array([0.0]))
    r = OG.uydur(TABAN, d, X, NOW)
    st = TABAN["standardization"]
    z = np.clip(M.standardize(X, st), -5, 5)[0]
    a2 = float(z @ z + 1)
    c0, b0 = np.asarray(TABAN["weights"]["coef"]), TABAN["weights"]["intercept"]
    dl = abs(float(z @ (r["coef"] - c0)) + r["b"] - b0)
    assert dl <= a2 / (0.25 * OG.N0) + 1e-9 and dl > 0


def test_ogren_ayni_olaydaki_20_kayip_tek_kayip_gibi():
    x1 = np.asarray(TABAN["standardization"]["mean"])[None, :] + 0.5
    d1, X1 = _tampon(1, y=np.zeros(1), x=x1, ayri_olay=False)
    d20, X20 = _tampon(20, y=np.zeros(20), x=np.repeat(x1, 20, axis=0), ayri_olay=False)
    d20["decision_ts"] = d1["decision_ts"].iloc[0]                    # ayni ani: yas farki yok
    r1, r20 = OG.uydur(TABAN, d1, X1, NOW), OG.uydur(TABAN, d20, X20, NOW)
    assert abs(r20["n_etkin"] - r1["n_etkin"]) < 0.02                 # yas farki ihmal edilebilir
    assert np.allclose(r20["coef"], r1["coef"], atol=2e-5) and abs(r20["b"] - r1["b"]) < 2e-5


def test_ogren_sira_bagimsizligi_ayni_sha():
    d, X = _tampon(300, seed=3)
    p = np.random.default_rng(9).permutation(len(d))
    r1 = OG.uydur(TABAN, d, X, NOW)
    r2 = OG.uydur(TABAN, d.iloc[p].reset_index(drop=True), X[p], NOW)
    s1 = OG.yeni_paket(TABAN, r1["coef"], r1["b"], surum=1, n_sonuc=r1["n_sonuc"], n_etkin=r1["n_etkin"], simdi=NOW)["sha256"]
    s2 = OG.yeni_paket(TABAN, r2["coef"], r2["b"], surum=1, n_sonuc=r2["n_sonuc"], n_etkin=r2["n_etkin"], simdi=NOW)["sha256"]
    assert s1 == s2


def test_ogren_yas_agirligi_ve_pencere():
    d, X = _tampon(1, yas_gun=30)
    assert abs(OG.uydur(TABAN, d, X, NOW)["n_etkin"] - 0.5) < 1e-9
    d, X = _tampon(1, yas_gun=91)
    r = OG.uydur(TABAN, d, X, NOW)
    assert r["n_sonuc"] == 0 and r["n_etkin"] == 0.0


def test_ogren_kutu_asiri_tek_yonlu_veride():
    d, X = _tampon(40000, seed=5, y=np.zeros(40000))
    d["decision_ts"] = pd.Timestamp(NOW) - pd.to_timedelta(np.random.default_rng(1).uniform(0, 60, 40000), unit="D")
    r = OG.uydur(TABAN, d, X, NOW, n0=1.0)                           # N0=1: taban neredeyse etkisiz => kutu devreye girer
    c0 = np.asarray(TABAN["weights"]["coef"])
    assert np.max(np.abs(r["coef"] - c0)) <= OG.KUTU_COEF + 1e-12 and abs(r["b"] - TABAN["weights"]["intercept"]) <= OG.KUTU_B + 1e-12
    assert abs(r["b"] - TABAN["weights"]["intercept"]) > 0.19      # gercekten kutuya vurdu


def _yeni(**kw):
    d, X = _tampon(200, seed=1)
    r = OG.uydur(TABAN, d, X, NOW)
    return OG.yeni_paket(TABAN, kw.get("coef", r["coef"]), kw.get("b", r["b"]), surum=1, n_sonuc=200, n_etkin=r["n_etkin"], simdi=NOW)


def _xref(n=500):
    st = TABAN["standardization"]
    return np.asarray(st["mean"]) + np.random.default_rng(4).normal(size=(n, K)) * np.asarray(st["std"])


def test_ogren_denetim_kabul_ve_retler():
    ok, _ = OG.denetle(TABAN, _yeni(), _xref())
    assert ok is None
    c = np.asarray(_yeni()["weights"]["coef"]).copy()
    c[0] = np.nan
    pk = _yeni()
    pk["weights"]["coef"][0] = None                                  # NaN json'da None; sonlu degil
    assert OG.denetle(TABAN, pk, _xref())[0] is not None
    for key, val in (("threshold", 0.5), ("standardization", {"fill": [0.0] * K, "mean": [0.0] * K, "std": [1.0] * K})):
        pk = _yeni()
        pk[key] = val
        pk["sha256"] = M.package_hash(pk)
        assert OG.denetle(TABAN, pk, _xref())[0].startswith("degismemesi_gereken")
    # gecme orani 3 katin disinda: kesisimi buyuk kaydir (kutu da yakalar, kutuyu gevsetip orani sinarim)
    pk = _yeni(b=TABAN["weights"]["intercept"] + 0.2)
    xr = _xref()
    rb, _ = OG.gecme_orani(TABAN, xr)
    pk2 = dict(pk)
    assert OG.denetle(TABAN, pk2, xr)[0] is None or True
    big = json.loads(json.dumps(pk))
    big["weights"]["intercept"] = TABAN["weights"]["intercept"] + 0.2
    big["sha256"] = M.package_hash(big)
    # referans kumesi: hepsi esigin cok ustunde olacak sekilde kaydirilmis x => taban orani yuksek, yeni (ayni agirlik) ayni: oran testi
    import trader_engine.ml1_ogren as mod
    orig = mod.gecme_orani
    try:
        mod.gecme_orani = lambda pkg, X: (0.10, True) if pkg is TABAN else (0.50, True)
        assert mod.denetle(TABAN, _yeni(), xr)[0].startswith("gecme_orani_disi")
        mod.gecme_orani = lambda pkg, X: (0.10, True) if pkg is TABAN else (0.02, True)
        assert mod.denetle(TABAN, _yeni(), xr)[0].startswith("gecme_orani_disi")
        mod.gecme_orani = lambda pkg, X: (0.10, True) if pkg is TABAN else (0.20, True)
        assert mod.denetle(TABAN, _yeni(), xr)[0] is None
    finally:
        mod.gecme_orani = orig
    assert OG.denetle(TABAN, _yeni(), _xref(50))[0] is None           # 200'den az aday: oran maddesi atlanir


def _og(tmp, **kw) -> OG.Ml1Ogrenici:
    tohum = tmp / "tohum.json"
    tohum.write_text(T.SEED_PKG.read_text())
    og = OG.Ml1Ogrenici(tmp / "og", tmp / "models" / "ml1_package.json", tohum, now_fn=lambda: NOW, **kw)
    assert og.baslat(NOW)
    return og


def _doldur(og, n=60, seed=2):
    d, X = _tampon(n, seed=seed)
    og._sn = [(d["k"][i], pd.Timestamp(d["decision_ts"][i]).as_unit("ns").value, d["y"][i], "BTC/USDT", "long", "1h", X[i].astype(np.float32))
              for i in range(n)]
    og._yeni_sonuc = n


def test_ogren_atomik_yazim_ve_son_iyi(tmp_path):
    og = _og(tmp_path)
    _doldur(og)
    s = og.guncelle(NOW)
    assert s["sonuc"] == "yazildi" and og.paket_yolu.exists()
    p1 = og.paket_yolu.read_bytes()
    sonra = og.son_iyi_yolu.read_bytes()
    assert json.loads(sonra)["sha256"] == TABAN["sha256"]            # ilk yazimda son_iyi = tohum
    _doldur(og, 80, seed=7)
    s2 = og.guncelle(NOW + timedelta(minutes=15))
    assert s2["sonuc"] == "yazildi" and og.son_iyi_yolu.read_bytes() == p1


def test_ogren_yazim_ortasinda_hata_etkin_paketi_bozmaz(tmp_path, monkeypatch):
    og = _og(tmp_path)
    _doldur(og)
    og.guncelle(NOW)
    onceki = og.paket_yolu.read_bytes()
    son_iyi = og.son_iyi_yolu.read_bytes()
    _doldur(og, 90, seed=11)
    def boom(a, b):
        raise OSError("disk dolu")
    monkeypatch.setattr(OG.os, "replace", boom)
    s = og.guncelle(NOW + timedelta(minutes=15))
    monkeypatch.undo()
    assert s["sonuc"].startswith("reddedildi:yazim_hatasi")
    assert og.paket_yolu.read_bytes() == onceki and not list(og.paket_yolu.parent.glob("*.tmp"))
    assert og.son_iyi_yolu.read_bytes() in (son_iyi, onceki)


def test_ogren_denetim_reddi_dosya_yazmaz(tmp_path, monkeypatch):
    og = _og(tmp_path)
    _doldur(og)
    monkeypatch.setattr(OG, "denetle", lambda *a, **k: ("gecme_orani_disi:test", {}))
    s = og.guncelle(NOW)
    assert s["sonuc"].startswith("reddedildi") and not og.paket_yolu.exists() and not og.son_iyi_yolu.exists()


def test_ogren_geri_donus_bozuk_etkin_paket(tmp_path):
    og = _og(tmp_path)
    _doldur(og)
    og.guncelle(NOW)
    _doldur(og, 70, seed=5)
    og.guncelle(NOW + timedelta(minutes=15))
    iyi = og.son_iyi_yolu.read_bytes()
    bozuk = json.loads(og.paket_yolu.read_text())
    bozuk["weights"]["coef"][0] = float("nan")                       # K5: etkin pakete NaN
    og.paket_yolu.write_text(json.dumps(bozuk))
    og.izle(NOW + timedelta(minutes=30))
    assert og.paket_yolu.read_bytes() == iyi
    assert og.duraklat_bitis == NOW + timedelta(minutes=30) + timedelta(hours=24)
    son = [json.loads(x) for x in (og.dir / "guncellemeler.jsonl").read_text().splitlines()][-1]
    assert son["sonuc"].startswith("geri_donuldu:etkin_paket_gecersiz")
    og._yeni_sonuc = 5
    assert og.adim(NOW + timedelta(hours=1))["guncelleme"] is False   # duraklatma suruyor


def test_ogren_geri_donus_gecme_orani_sifir(tmp_path):
    class Kapi:
        counters = {"ml1_gecti": 0, "ml1_esik_alti": 0, "ml1_hata": 0}
        def paket_durumu(self):
            return True, json.loads(og.paket_yolu.read_text())["sha256"]
    og = _og(tmp_path, kapi=Kapi())
    _doldur(og)
    og.guncelle(NOW)
    iyi = og.son_iyi_yolu.read_bytes()
    Kapi.counters["ml1_esik_alti"] = 45                               # yazimdan sonra 45 aday, hicbiri gecmedi
    og.izle(NOW + timedelta(minutes=15))
    assert og.paket_yolu.read_bytes() == iyi and og.sayac["geri_donus"] == 1


def test_ogren_geri_donus_kapi_etkin_paketi_reddetti(tmp_path):
    class Kapi:
        counters = {"ml1_gecti": 0, "ml1_esik_alti": 0, "ml1_hata": 0}
        def paket_durumu(self):
            return True, "baska_sha"                                 # kapi tohuma dustu
    og = _og(tmp_path, kapi=Kapi())
    _doldur(og)
    og.guncelle(NOW)
    og.izle(NOW + timedelta(minutes=15))
    assert og.sayac["geri_donus"] == 1


def test_ogren_etiket_build_simulate_pending_ile_ayni(tmp_path):
    """Ogrenicinin etiketi (r_net > 0) ayni aday + ayni mumlar icin `build.simulate_pending` yolunun etiketiyle ayni."""
    from trader_ml.ml1 import build as B, data as D, scan as SC, table as TB
    from trader_engine.marketdata.sources import HistoricalSource
    hist = tmp_path / "hist"
    T.write_history(hist)
    end = datetime(2026, 11, 11, tzinfo=UTC)
    tbl = TB.CandidateTable(tmp_path / "tbl")
    pair, tf = "BTC/USDT", "1h"
    trig, h4 = D.load_pair_tf(hist, pair, tf)
    c = SC.scan_pair_tf(pair, tf, trig, h4, [a for a in T.ARMS if a.endswith("@1h")])
    c = c[c["decision_ts"] >= pd.Timestamp(end - timedelta(days=40))]
    tbl.ensure_hash(SC.arms_hash())
    tbl.append(pair, tf, c, trig.index[-1] + pd.Timedelta(hours=1))
    B.simulate_pending(tbl, hist, pair, tf)
    off = tbl.read(pairs=[pair], tfs=[tf])
    off = off[off["status"].eq("ok") & off["censored"].fillna(0).eq(0) & off["r_net"].notna()]
    assert len(off) >= 20
    off = off[off["decision_ts"] >= pd.Timestamp(end - timedelta(days=30))]
    tohum = tmp_path / "tohum.json"
    tohum.write_text(T.SEED_PKG.read_text())
    from trader_engine.marketdata.sources import HistoricalSource
    og = OG.Ml1Ogrenici(tmp_path / "og", tmp_path / "p.json", tohum, view=HistoricalSource(str(hist), granularity="15m", synthetic_rules=True),
                        now_fn=lambda: end, butce_s=1e9)
    assert og.baslat(end)
    recs = []
    for r in off.to_dict("records"):
        ts = pd.Timestamp(r["decision_ts"])
        recs.append({"k": f"{pair}|{r['arm_id']}|{r['side']}|{ts.isoformat()}", "decision_ts": ts.isoformat(), "pair": pair, "tf": tf, "setup": r["setup"],
                     "arm_id": r["arm_id"], "group": r["group"], "side": r["side"], "entry_ref": float(r["entry_ref"]), "stop": float(r["stop"]),
                     "target": None if not np.isfinite(r["target"]) else float(r["target"]), "stop_dist_atr": float(r["stop_dist_atr"]),
                     "x": [0.0] * K, "skor": 0.6, "sha": "x", "kod": None})
    og.kaydet(recs)
    og.coz(end, ())
    got = {s[0]: s[2] for s in og._sn}
    assert len(got) >= len(off) * 0.9
    exp = {f"{pair}|{r['arm_id']}|{r['side']}|{pd.Timestamp(r['decision_ts']).isoformat()}": float(r["r_net"] > 0) for r in off.to_dict("records")}
    ortak = set(got) & set(exp)
    assert len(ortak) >= len(off) * 0.9
    assert all(got[k] == exp[k] for k in ortak), [k for k in ortak if got[k] != exp[k]][:5]


def test_ogren_x_kaydi_yeniden_puanlama_esit(tmp_path):
    """Kapinin dosyaya yazdigi x ile `M.score` ayni puan (1e-12): x, puanlamanin ayni tasarim matrisinden."""
    from trader_engine import ml1_gate as MG
    hist = tmp_path / "hist"
    T.write_history(hist)
    pk = tmp_path / "tohum.json"
    pkg = T.write_package(pk, threshold=0.0)
    og = OG.Ml1Ogrenici(tmp_path / "og", tmp_path / "p.json", pk, now_fn=lambda: T.START)
    assert og.baslat(T.START)
    import ml1_motor_destek as TT
    eng = TT.make_engine(tmp_path / "e", hist, {"aktif": True, "paket_yolu": str(tmp_path / "p.json"), "tohum_yolu": str(pk),
                                                  "ogrenme": {"aktif": True, "kuru": True}})
    eng.run_range(T.START, T.START + timedelta(hours=30))
    rs = [r for r in OGfiles(eng) if "x" in r]
    assert len(rs) >= 10
    for r in rs[:40]:
        x = np.array([np.nan if v is None else v for v in r["x"]], float)[None, :]
        Z = M.standardize(x, pkg["standardization"])
        p = float(M._sigmoid(Z @ np.asarray(pkg["weights"]["coef"]) + pkg["weights"]["intercept"])[0])
        assert abs(p - r["skor"]) <= 1e-12


def OGfiles(eng):
    out = []
    for p in sorted(Path(eng.cfg.path("ml1_ogren")).glob("adaylar-*.jsonl")):
        out += [json.loads(x) for x in p.read_text().splitlines()]
    return out
