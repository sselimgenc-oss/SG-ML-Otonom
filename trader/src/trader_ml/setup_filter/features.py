"""Egitim ozellikleri: motorla AYNI fonksiyon (`trader_core.ml_live_v2.setup_feature_dict`) -> parite. Not etiketleri (role=label)
ozellik OLAMAZ; yalniz `r` hedefi ve ders kimligi sozlugu icin kullanilir."""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import numpy as np

from trader_core.ml_live_v2 import SETUP_BASE_FEATURES, guess_asset_class, setup_feature_dict, setup_feature_vector  # noqa: F401

MAX_EXTRA_FEATURES = 24      # `f_*` ozellik tavani (en sik gorulenler; deterministik)
MAX_LESSON_FEATURES = 16
# Fikir 10 (23.11): oynaklik tahmini ozellikleri YALNIZ gece aile suzgecinin girdisidir; global (ml1) suzgece girmez.
HARIC_ONEKLER = ("f_vol_tahmin", "f_vol_asim")


def choose_feature_names(fdicts: Sequence[dict]) -> list[str]:
    """Taban + en sik `f_*` + en sik `ders:*` (deterministik: sayi azalan, ad artan). Sabit (tek degerli) sutunlar kalir; ridge halleder."""
    cf, cl = Counter(), Counter()
    for d in fdicts:
        for k in d:
            if k.startswith("f_") and not k.startswith(HARIC_ONEKLER):
                cf[k] += 1
            elif k.startswith("ders:"):
                cl[k] += 1
    top = lambda c, n: [k for k, _ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]  # noqa: E731
    return list(SETUP_BASE_FEATURES) + sorted(top(cf, MAX_EXTRA_FEATURES)) + sorted(top(cl, MAX_LESSON_FEATURES))


def matrix(names: Sequence[str], fdicts: Sequence[dict]) -> np.ndarray:
    return np.vstack([setup_feature_vector(names, d) for d in fdicts]) if fdicts else np.empty((0, len(names)))


def assert_no_label_features(names: Sequence[str]) -> None:
    bad = [n for n in names if n.startswith(("sonuc", "label", "role", "not:", "tag:", "r_", "kacinilabilir"))]
    if bad:
        raise ValueError(f"islem sonrasi etiket ozellik olamaz: {bad}")
