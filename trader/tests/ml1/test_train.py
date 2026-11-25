"""ML1 egitim: izin listesi, purge, holdout dokunulmazligi, lojistik sinyal kurtarma, paket imzasi."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from test_train_destek import sentetik_tablo

from trader_ml.ml1 import model as M
from trader_ml.ml1 import train as TR

KW = {"holdout_months": 3, "test_months": 3, "min_train_months": 6, "min_trades": 20}


def test_ozellik_izin_listesi_sizinti_yok():
    names = M.feature_names()
    assert len(names) == len(set(names))
    for n in names:
        assert not n.startswith(M.FORBIDDEN_PREFIXES), n
    assert not {"event_weight", "event_id", "event_size", "r_net", "exit_ts", "hour_utc", "dow", "mfe_R", "mae_R", "bars_held"} & set(names)
    for kotu in ("event_weight", "r_net", "exit_price", "mfe_R", "bars_held", "censored", "hour_utc"):
        try:
            M.assert_no_leak(names + [kotu])
        except ValueError:
            continue
        raise AssertionError(f"{kotu} reddedilmedi")
    # tek ozellik kaynagi allowlist: karar-sonrasi sutunlari karistirmak matrisi DEGISTIRMEZ
    df = sentetik_tablo(300, sinyal=1.0)
    X0 = M.design_matrix(df)
    d2 = df.copy()
    rng = np.random.default_rng(0)
    for c in ("r_net", "event_weight", "event_size"):
        d2[c] = rng.permutation(d2[c].to_numpy())
    d2["exit_ts"] = d2["exit_ts"] + pd.Timedelta(days=3)
    d2["mfe_R"] = rng.normal(size=len(d2))
    np.testing.assert_array_equal(M.design_matrix(d2), X0)
    assert X0.shape[1] == len(names)


def test_purge_cakisan_satirlari_atar():
    s = pd.Timestamp("2022-06-01", tz="UTC")
    dec = pd.to_datetime(["2022-05-01", "2022-05-31", "2022-05-31", "2022-04-01"], utc=True)
    ex = pd.to_datetime(["2022-05-02", "2022-06-02", "2022-05-31 12:00", "2022-04-02"], utc=True, format="mixed")
    df = pd.DataFrame({"decision_ts": dec, "exit_ts": ex})
    m = TR.train_mask(df, s, pd.Timedelta(0))
    assert m.tolist() == [True, False, True, True]            # exit_ts >= s atilir
    m2 = TR.train_mask(df, s, pd.Timedelta(days=5))            # embargo: decision_ts >= s - 5g da atilir
    assert m2.tolist() == [True, False, False, True]
    # kat egitimlerinde hicbir egitim satirinin exit_ts'i test baslangicina ulasmaz
    d = sentetik_tablo(1500, sinyal=1.0)
    lab, _ = TR.prepare_labeled(d)
    dev, _, hs = TR.split_holdout(lab, 3)
    emb = TR.max_holding(dev)
    for (a, _b) in TR.make_folds(dev, hs, 3, 6):
        tr = dev[TR.train_mask(dev, a, emb)]
        assert (tr["exit_ts"] < a).all() and (tr["decision_ts"] < a - emb).all()


def test_holdout_secimde_kullanilmaz():
    d = sentetik_tablo(3000, sinyal=1.0)
    r1 = TR.run(d, **KW)
    hs = pd.Timestamp(r1["data"]["holdout_start"])
    d2 = d.copy()
    m = d2["decision_ts"] >= hs
    assert m.sum() > 50
    d2.loc[m, "r_net"] = -d2.loc[m, "r_net"]                    # holdout etiketlerini cevir
    r2 = TR.run(d2, **KW)
    assert r1["ridge"] == r2["ridge"] and r1["threshold"] == r2["threshold"]
    assert r1["threshold"] is not None
    np.testing.assert_allclose(r1["oos"]["p"].to_numpy(), r2["oos"]["p"].to_numpy())
    np.testing.assert_array_equal(r1["oos"]["r_net"].to_numpy(), r2["oos"]["r_net"].to_numpy())
    # son model egitimi de holdout'u gormez: holdout tahminleri ayni
    np.testing.assert_allclose(r1["holdout"]["p"].to_numpy(), r2["holdout"]["p"].to_numpy())
    assert (r1["oos"]["decision_ts"] < hs).all() and (r1["holdout"]["decision_ts"] >= hs).all()
    assert (r1["oos"]["exit_ts"] < hs).all()


def test_lojistik_planli_sinyali_bulur():
    rng = np.random.default_rng(1)
    n = 5000
    Z = rng.normal(size=(n, 4))
    p = 1 / (1 + np.exp(-(1.5 * Z[:, 0] - 1.0 * Z[:, 2])))
    y = (rng.random(n) < p).astype(float)
    coef, _b = M.fit_logistic(Z, y, np.ones(n), ridge=1.0)
    assert abs(coef[0] - 1.5) < 0.2 and abs(coef[2] + 1.0) < 0.2 and abs(coef[1]) < 0.15 and abs(coef[3]) < 0.15
    # uctan uca: planli conf_all_tf sinyali OOS'ta kazanma oranini ayirir
    r = TR.run(sentetik_tablo(4000, sinyal=1.5), **KW)
    names = r["package"]["feature_names"]
    c = np.asarray(r["package"]["weights"]["coef"])
    assert names[int(np.argmax(np.abs(c)))] == "conf_all_tf" and c[names.index("conf_all_tf")] > 0
    oos = r["oos"]
    hi = oos[oos["p"] >= oos["p"].quantile(0.8)]
    lo = oos[oos["p"] <= oos["p"].quantile(0.2)]
    assert hi["y"].mean() > lo["y"].mean() + 0.2


def test_paket_sha256_gidis_donus_ve_tahrif(tmp_path):
    r = TR.run(sentetik_tablo(2500, sinyal=1.0), **KW)
    pkg = r["package"]
    assert pkg["schema"] == "ml1/1" and M.verify_package(pkg) is None
    p = M.save_package(pkg, tmp_path / "pkg.json")
    got, why = M.load_package(p)
    assert why is None and got == json.loads(p.read_text())
    df = sentetik_tablo(200, sinyal=1.0)
    np.testing.assert_allclose(M.score(got, df), M.score(pkg, df))
    pr = M.score(got, df)
    assert ((pr > 0) & (pr < 1)).all()
    # tahrif: bir agirligi degistir -> None + neden
    bad = json.loads(p.read_text())
    bad["weights"]["coef"][0] += 0.1
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    g2, why2 = M.load_package(tmp_path / "bad.json")
    assert g2 is None and "sha256" in why2
    # sha alanini da yeniden hesaplamadan esigi degistir
    bad2 = json.loads(p.read_text())
    bad2["threshold"] = 0.99
    (tmp_path / "bad2.json").write_text(json.dumps(bad2))
    assert M.load_package(tmp_path / "bad2.json")[0] is None
    # bozuk / yok dosya / yanlis sema: asla firlatmaz
    (tmp_path / "junk.json").write_text("{not json")
    assert M.load_package(tmp_path / "junk.json")[0] is None
    assert M.load_package(tmp_path / "yok.json")[0] is None
    bad3 = dict(json.loads(p.read_text()), schema="ml1/2")
    assert M.verify_package(bad3) is not None
    assert M.verify_package(None) is not None and M.verify_package({"schema": "ml1/1"}) is not None
    # yasakli ozellik adli paket reddedilir (imzali olsa bile)
    leaky = dict(json.loads(p.read_text()))
    leaky["feature_names"] = ["event_weight"] + leaky["feature_names"][1:]
    leaky["sha256"] = M.package_hash(leaky)
    assert M.verify_package(leaky) is not None
