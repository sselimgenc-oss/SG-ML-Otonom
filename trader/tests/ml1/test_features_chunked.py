"""Bellek-dostu (cift basina) ozellik kurulumu, eski tek-seferlik yolla ayni sonucu verir; parcali lojistik/standartlastirma da ayni."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_ml.ml1 import features as F
from trader_ml.ml1 import model as M

from ml1_destek import PAIR


def _iki_cift(scanned: pd.DataFrame) -> pd.DataFrame:
    a = scanned.assign(pair=PAIR)
    b = scanned.iloc[::2].assign(pair="SYN2/USDT")
    c = pd.concat([a, b], ignore_index=True)
    c["r_net"] = 0.5
    c["exit_ts"] = c["decision_ts"] + pd.Timedelta(hours=8)
    c["status"] = "ok"
    c["censored"] = 0
    return c.sort_values(["decision_ts", "arm_id", "pair"], kind="stable").reset_index(drop=True)


def test_parcali_kurulum_eskisiyle_ayni(scanned, bars4h):
    c = _iki_cift(scanned)

    def lookup(pair, tf):
        return bars4h, bars4h

    eski = F.build_features(c, lookup)
    parcalar = [g for _, g in c.groupby("pair", sort=True)]
    slims = []
    for i, p in enumerate(parcalar):
        s = F.build_features_chunked([p], lambda pair: lookup)
        s["event_id"] = s["event_id"] + i * 1_000_000_000
        slims.append(s)
    yeni = F.assemble(slims)
    assert len(yeni) == len(eski)
    # ayni satir sirasi (decision_ts, arm_id, pair) ve ayni degerler (float32 tolerans)
    for col in ("decision_ts", "pair", "tf", "group", "side", "arm_id"):
        assert list(yeni[col].astype(str)) == list(eski[col].astype(str)), col
    for col in F.feature_columns() + list(F.RAW_FOR_DESIGN):
        np.testing.assert_allclose(yeni[col].to_numpy(float), eski[col].to_numpy(float), rtol=1e-6, atol=1e-7, equal_nan=True, err_msg=col)
    np.testing.assert_allclose(yeni["event_weight"], eski["event_weight"])
    # olay bolumlemesi ayni (kimlik farkli: int)
    assert pd.factorize(yeni["event_id"])[0].tolist() == pd.factorize(eski["event_id"])[0].tolist()
    # tasarim matrisi (model girdisi) ayni
    np.testing.assert_allclose(M.design_matrix(yeni, dtype=np.float32), M.design_matrix(eski), rtol=1e-5, atol=1e-6, equal_nan=True)
    assert set(F.ID_COLS) - {"status", "censored", "exit_ts"} <= set(yeni.columns)


def test_parcali_lojistik_ayni():
    rng = np.random.default_rng(1)
    n, k = 5000, 6
    X = rng.standard_normal((n, k))
    X[rng.random((n, k)) < 0.05] = np.nan
    y = (rng.random(n) < 0.5).astype(float)
    w = rng.uniform(0.2, 1.0, n)
    st1 = M.fit_standardizer(X, chunk=10 ** 9)
    st2 = M.fit_standardizer(X, rows=np.arange(n), chunk=700)
    for key in ("fill", "mean", "std"):
        np.testing.assert_allclose(st1[key], st2[key], rtol=1e-10)
    Z = M.standardize(X, st1)
    c1, b1 = M.fit_logistic(Z, y, w, 1.0, chunk=10 ** 9)
    c2, b2 = M.fit_logistic(M.standardize(X, st1, np.arange(n), dtype=np.float32, chunk=700), y, w, 1.0, chunk=700)
    np.testing.assert_allclose(c1, c2, atol=1e-4)
    assert abs(b1 - b2) < 1e-4
