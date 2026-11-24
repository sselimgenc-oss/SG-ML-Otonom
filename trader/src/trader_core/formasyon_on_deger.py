"""24.11 kullanici karari: formasyon kutuphanesi on degerleri (gecmis testin ilk bilgisi).

`config/formasyon_on_deger.json`: {"MF1-PINBAR@15m": {"r": -0.235, "n": 5951}, ...}. Kullanici karari: dosya BOS verilir; hicbir hucre
kucuk ya da kapali baslamaz (hepsi tam boy). Mekanizma yine de bulunur: yalniz `gates._kol_karari` icinde, kolun gercek aile
ortalamasi `None` ise aile ortalamasi yerine `r` verilir. Baska yerde kullanilmaz. Okunamazsa bos sayilir (fail-open: yalniz
kucultmeyi atlar)."""
from __future__ import annotations

import json
import math
from pathlib import Path

DOSYA = Path(__file__).resolve().parents[2] / "config" / "formasyon_on_deger.json"
_ONBELLEK: dict[str, tuple[float, dict]] = {}


def yukle(path=None) -> dict[str, dict]:
    """{arm_id: {"r": float, "n": int}}; dosya yok/bozuk -> {}. Gecersiz kayitlar atlanir. Degisen dosya yeniden okunur."""
    p = Path(path) if path is not None else DOSYA
    try:
        mt = p.stat().st_mtime
        hit = _ONBELLEK.get(str(p))
        if hit is not None and hit[0] == mt:
            return hit[1]
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    if isinstance(doc, dict):
        for k, v in doc.items():
            r = v.get("r") if isinstance(v, dict) else None
            if isinstance(k, str) and isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(float(r)):
                out[k] = {"r": float(r), "n": int(v.get("n", 0) or 0)}
    _ONBELLEK[str(p)] = (mt, out)
    return out


def r_of(arm_id: str, path=None) -> float | None:
    """Kolun on deger ortalama net R'si; yoksa None."""
    v = yukle(path).get(arm_id)
    return None if v is None else float(v["r"])
