"""Lojistik model degerlendiricisi (M1 paketleri): `trader_ml.pa_proposer.train.fit_logistic` sozlugunu okur; YALNIZ numpy.
lightgbm/sklearn/scipy/pandas import ETMEZ (motor tarafina tasinabilir).

Model: p = sigmoid(a * z + b), z = ((x - mean) / std) @ coef + intercept; eksik (NaN) ozellik `fill` degeriyle doldurulur.
"""
from __future__ import annotations

import numpy as np


def _sigmoid(z):
    z = np.asarray(z, dtype=np.float64)
    out = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    e = np.exp(z[~pos])
    out[~pos] = e / (1.0 + e)
    return out


class TreeModel:
    """kind='logistic'. predict_raw -> marj, predict_proba -> kalibre. (Ad eski; agac degerlendirici kaldirildi, API sabit.)"""

    def __init__(self, model: dict, calibration: dict | None = None):
        self.kind = model["kind"]
        self.n_features = int(model["n_features"])
        self.calibration = calibration or {"a": 1.0, "b": 0.0}
        if self.kind == "logistic":
            self.coef = np.asarray(model["coef"], dtype=np.float64)
            self.intercept = float(model["intercept"])
            self.mean = np.asarray(model["mean"], dtype=np.float64)
            self.std = np.asarray(model["std"], dtype=np.float64)
            self.fill = np.asarray(model["fill"], dtype=np.float64)
        else:
            raise ValueError(f"bilinmeyen model turu: {self.kind}")

    def _check(self, X) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, dtype=np.float64))
        if X.shape[1] != self.n_features:
            raise ValueError(f"ozellik sayisi {X.shape[1]} != {self.n_features}")
        return X

    def predict_raw(self, X) -> np.ndarray:
        X = self._check(X)
        Xf = np.where(np.isnan(X), self.fill, X)
        return ((Xf - self.mean) / self.std) @ self.coef + self.intercept

    def predict_uncalibrated(self, X) -> np.ndarray:
        return _sigmoid(self.predict_raw(X))

    def predict_proba(self, X) -> np.ndarray:
        z = self.predict_raw(X)
        return _sigmoid(self.calibration["a"] * z + self.calibration["b"])

    def predict_one(self, row) -> float:
        return float(self.predict_proba(np.asarray(row, dtype=np.float64)[None, :])[0])
