"""Model paketi ortak yardimcilari: kanonik JSON ve sha256 (ML1 paket hash'i `trader_ml.ml1.model` tarafindan kullanilir).
Yalniz stdlib."""
from __future__ import annotations

import hashlib
import json


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
