"""Paket ozellik vektoru: M1 kolunun (arms/m1.py) ve hafif donanim harness'inin ortak yardimcisi (yalniz numpy).

Paketin ozellik sirasina (`meta.features`) gore vektor kurar: sozlukte olmayan ozellik NaN olur (modelin `fill` degeri
doldurur); `ders:*` anahtarlari yoksa 0 (ders eslesmedi). Saf: dosya/ag/saat yok."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

__all__ = ["setup_feature_vector"]


def setup_feature_vector(names: Sequence[str], fdict: Mapping[str, float]) -> np.ndarray:
    """Paket ozellik sirasina gore vektor. Eksik `ders:*` -> 0 (ders eslesmedi); diger eksikler NaN (modelin `fill` degeri)."""
    out = np.empty(len(names), dtype=np.float64)
    for i, n in enumerate(names):
        v = fdict.get(n)
        out[i] = (0.0 if n.startswith("ders:") else float("nan")) if v is None else v
    return out
