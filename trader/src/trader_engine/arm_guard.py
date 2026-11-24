"""DD-12 WP-04 (spec §4.1/§4.2): saf yardimcilar - kume uyeligi, tavan sayimi, `session_tag`, tatil/duz bar.
Girdi/cikti yalniz deger; G/C, saat, durum yok. Seans yuzunden giris ENGELLENMEZ: etiket yalniz kayittir;
`session_closed` ancak dersin kapattigi seans icindir (gates.py)."""
from __future__ import annotations

import json
import math
from collections.abc import Collection, Mapping, Sequence

from trader_core.arm_time import CLASS_CRYPTO, CLASS_COMMODITY, CLASS_EQUITY, arm_id_of, session_tag

from .config import ClusterSpec

EQUITY_CLUSTER = "hisse"
COMMODITY_CLUSTERS = ("metal", "enerji_sanayi")


def clusters_of(pair: str, clusters: Mapping[str, ClusterSpec]) -> list[str]:
    """Cift hangi kumelerin uyesi (yapilandirma sirasiyla; birden cok olabilir)."""
    return [name for name, spec in clusters.items() if pair in spec.pairs]


def count_in_cluster(held_pairs: Collection[str] | Sequence[str], spec: ClusterSpec) -> int:
    return sum(1 for p in held_pairs if p in spec.pairs)


def full_cluster(pair: str, held_pairs: Sequence[str], clusters: Mapping[str, ClusterSpec]) -> str | None:
    """Giris icin yeri olmayan ilk kume adi (acik + acilmakta pozisyonlar `held_pairs`); hepsinde yer varsa None."""
    for name in clusters_of(pair, clusters):
        if count_in_cluster(held_pairs, clusters[name]) >= clusters[name].max_positions:
            return name
    return None


def account_full(n_open: int, max_positions: int | None) -> bool:
    return max_positions is not None and n_open >= max_positions


def asset_class(pair: str, clusters: Mapping[str, ClusterSpec]) -> str:
    """kripto | hisse | emtia; kume adlarindan (`hisse`, `metal`, `enerji_sanayi`) cikarilir, aksi kripto."""
    for name in clusters_of(pair, clusters):
        if name == EQUITY_CLUSTER:
            return CLASS_EQUITY
        if name in COMMODITY_CLUSTERS:
            return CLASS_COMMODITY
    return CLASS_CRYPTO


def is_flat_bar(high: float | None, low: float | None, volume: float | None) -> bool:
    """Tatil/olu mum: volume == 0 ya da high == low. Veri yoksa (None/NaN) False (karar verilemez)."""
    def ok(x) -> bool:
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))
    if ok(volume) and float(volume) == 0.0:
        return True
    return ok(high) and ok(low) and float(high) == float(low)


# Olu mum yardimcilari (flat_mask/active_mask/expand_rows/tail_active/regime_series/core_signals) trader_core.arm_time'dadir (TEK yer:
# trader_core -> trader_engine yasak; ML v2 ve cikis karsi-olgusu da ayni kodu kullanir). Burada yeniden disa aktarilir.
from trader_core.arm_time import (CARRY_REGIME, CARRY_SIGNAL, active_mask, core_signals, expand_rows,   # noqa: E402,F401
                                  flat_mask, regime_series, strip_dead, tail_active)


def load_arms_off(path) -> frozenset[str]:
    """DD-12 WP-13 (D-T22): ders kapattigi kurulumlar (`var/<bot>/arms_off.json`, yazan: lesson.write_arms_state). Salt
    okuma; dosya yoksa ya da bozuksa bos kume (hepsi acik). Kayit yapisi: {"arms": {arm_id: {"state": "closed", ...}}}."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        arms = doc.get("arms") if isinstance(doc, dict) else None
        if not isinstance(arms, dict):
            return frozenset()
        return frozenset(str(k) for k, v in arms.items() if isinstance(v, dict) and v.get("state") == "closed")
    except (OSError, ValueError):
        return frozenset()


def session_closed_by_lesson(session_off: Mapping[str, Collection[str]] | None, cls: str, pair: str, tag: str) -> bool:
    """Ders `session_off`: anahtar varlik sinifi ya da cift adi, deger kapatilan etiketler. Varsayilan: hepsi acik."""
    if not session_off:
        return False
    return tag in (session_off.get(cls) or ()) or tag in (session_off.get(pair) or ())


# ---------------------------------------------------------------------------------------------------------------------
# DD-12 WP-11 (D-T16): kurulum (arm) basina acik pozisyon tavani. Saf yardimcilar (durum/saat yok).
# ---------------------------------------------------------------------------------------------------------------------
def arm_cap(caps: Mapping[str, int] | None, arm_id: str, setup: str | None) -> int | None:
    """Tavan arama sirasi: tam arm_id, kurulum kodu, `default`; hicbiri yoksa None (tavan yok)."""
    if not caps:
        return None
    for key in (arm_id, setup, "default"):
        if key is not None and key in caps:
            return int(caps[key])
    return None


def arm_cap_is_setup_total(caps: Mapping[str, int] | None, arm_id: str, setup: str | None) -> bool:
    """Tavan `X@tf` ya da `default` anahtarindan gelirse kurulum x zaman dilimi basinadir (False). Zaman dilimsiz kurulum
    anahtari (`M1`: 4) ise o sayi kurulumun TUM zaman dilimlerindeki toplamidir (True)."""
    if not caps or arm_id in caps:
        return False
    return setup is not None and setup in caps


def arm_full(held_arm_ids: Sequence[str], arm_id: str, cap: int | None, setup_total: bool = False) -> bool:
    """`held_arm_ids`: acik + acilmakta pozisyonlarin arm_id'leri. cap None => dolu degil.
    `setup_total`: sayim kurulumun tum zaman dilimlerinde (`M1@15m` + `M1@1h` + ...) yapilir."""
    if cap is None:
        return False
    if setup_total:
        base = arm_id.split("@")[0]
        return sum(1 for a in held_arm_ids if a.split("@")[0] == base) >= cap
    return sum(1 for a in held_arm_ids if a == arm_id) >= cap
