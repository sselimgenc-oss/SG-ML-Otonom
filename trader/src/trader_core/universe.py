"""Aylik enstruman evreni (DD-12 WP-16; D-T28). Saf fonksiyonlar: ag, dosya ve saat yok.

Kural (kullanici karari, 18 Kasim 2026):
  * kripto 20: stabil ve sarili/stake kopyalar disarida; Binance vadelide TRADING olan, en yuksek siralama puanli 20.
  * hisse 20: sirali listeden (config/universe.json) TRADING olan ilk 20.
  * emtia 4 (XAU, XAG, BZ, COPPER): sabit; TRADING olmasa da listede kalir (motor o ciftte bekler).
  * `keep` (acik pozisyonu olan, artik listede olmayan ciftler): evrende kalir, `optional` olur (yonetim surer, yeni giris
    kapisi motorda; bkz. rapor). Toplam 44'ten yalniz bu durumda sapar.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

SCHEMA = "universe/1"
N_CRYPTO = 20
N_STOCKS = 20
_PAIR_RE = re.compile(r"^[A-Z0-9]{1,20}/[A-Z0-9]{1,20}$")


def base_of(pair: str) -> str:
    """'1000SHIB/USDT' -> '1000SHIB'."""
    return pair.split("/", 1)[0].upper()


def select_crypto(candidates: Iterable[Mapping[str, Any]], *, exclude_bases: Iterable[str], n: int = N_CRYPTO) -> list[str]:
    """candidates: {"pair", "score", "trading"}. Stabil/sarili (exclude_bases) ve TRADING olmayanlar elenir.
    Sira: puan azalan (esitlikte pair adi)."""
    excl = {b.upper() for b in exclude_bases}
    out: list[str] = []
    ranked = sorted((c for c in candidates if c.get("trading") and base_of(c["pair"]) not in excl),
                    key=lambda c: (-float(c.get("score", 0.0)), c["pair"]))
    for c in ranked:
        if len(out) >= n:
            break
        if c["pair"] not in out:
            out.append(c["pair"])
    return out[:n]


def select_stocks(ordered: Sequence[str], trading: Iterable[str], n: int = N_STOCKS) -> list[str]:
    """Sirali liste (ilk n + yedek) icinde TRADING olan ilk n. Yedek yoksa kisa kalir (sessiz doldurulmaz)."""
    tr = set(trading)
    out: list[str] = []
    for p in ordered:
        if p in tr and p not in out:
            out.append(p)
        if len(out) >= n:
            break
    return out


def compose(crypto: Sequence[str], stocks: Sequence[str], commodities: Sequence[str],
            keep: Sequence[str] = ()) -> dict[str, list[str]]:
    """Yeni `pairs` ve `optional_pairs`. Kripto disindaki her sey optional (kural/veri yoksa yalniz o cift bekler)."""
    pairs: list[str] = []
    optional: list[str] = []
    for p in list(crypto) + list(stocks) + list(commodities) + list(keep):
        if p not in pairs:
            pairs.append(p)
    for p in list(stocks) + list(commodities) + list(keep):
        if p not in optional and p not in crypto:
            optional.append(p)
    return {"pairs": pairs, "optional_pairs": optional}


def diff_pairs(old: Sequence[str], new: Sequence[str]) -> dict[str, list[str]]:
    o, n = list(old), list(new)
    return {"added": [p for p in n if p not in o], "removed": [p for p in o if p not in n]}


def validate_overlay(obj: Any) -> dict[str, list[str]]:
    """Kaplama dosyasini dogrular; gecersizse ValueError. Donus: {"pairs", "optional_pairs"}."""
    if not isinstance(obj, dict):
        raise ValueError("kaplama nesne olmali")
    if obj.get("schema") != SCHEMA:
        raise ValueError(f"schema {SCHEMA!r} olmali: {obj.get('schema')!r}")
    pairs, optional = obj.get("pairs"), obj.get("optional_pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError("pairs bos olmayan liste olmali")
    if not isinstance(optional, list):
        raise ValueError("optional_pairs liste olmali")
    for name, lst in (("pairs", pairs), ("optional_pairs", optional)):
        for p in lst:
            if not isinstance(p, str) or not _PAIR_RE.match(p):
                raise ValueError(f"{name} gecersiz cift: {p!r}")
        if len(set(lst)) != len(lst):
            raise ValueError(f"{name} yinelenen oge iceriyor")
    stray = [p for p in optional if p not in pairs]
    if stray:
        raise ValueError(f"optional_pairs pairs disinda cift iceriyor: {stray}")
    # WP-18: evrenden cikmis ama acik pozisyonu tutulan ciftler (yeni giris yok). Eski kaplamalarda anahtar yok = bos.
    retired = obj.get("retired_pairs", [])
    if not isinstance(retired, list):
        raise ValueError("retired_pairs liste olmali")
    for p in retired:
        if not isinstance(p, str) or not _PAIR_RE.match(p):
            raise ValueError(f"retired_pairs gecersiz cift: {p!r}")
    if len(set(retired)) != len(retired):
        raise ValueError("retired_pairs yinelenen oge iceriyor")
    stray = [p for p in retired if p not in pairs]
    if stray:
        raise ValueError(f"retired_pairs pairs disinda cift iceriyor: {stray}")
    return {"pairs": list(pairs), "optional_pairs": list(optional), "retired_pairs": list(retired)}


def overlay_document(pairs: Sequence[str], optional: Sequence[str], *, generated_at: str, source: str,
                     notes: Sequence[str] = (), retired: Sequence[str] = ()) -> dict[str, Any]:
    doc = {"schema": SCHEMA, "generated_at": generated_at, "source": source,
           "pairs": list(pairs), "optional_pairs": list(optional), "retired_pairs": list(retired), "notes": list(notes)}
    validate_overlay(doc)
    return doc


def dumps(doc: Mapping[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
