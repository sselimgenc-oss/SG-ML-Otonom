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


# ---------------------------------------------------------------------------------------------------------------------
# Olu (islem gormeyen) mumlar: seansli hisse/emtia perp'lerinde hafta sonu/tatil/seans disi mumlar hacim 0 ve o==h==l==c gelebilir.
# Bu mumlar gosterge girdisinden CIKARILIR (ATR'ye sifir gercek aralik, EMA'ya tekrarlanan kapanis eklemesinler); sonuc tabloya
# TAM izgara uzerinde geri genisletilir (olu satirlar: aday yok, baglam sutunlari son dolu satirdan tasinir). TEK yer: bu bolum.
# Kripto etkilenmez: olu mum yoksa `active_mask` None doner ve her cagiran eski yolu AYNEN calistirir (bayt-bayt ayni).
# ---------------------------------------------------------------------------------------------------------------------
_OHLC = ["open", "high", "low", "close"]
CARRY_SIGNAL = ("atr_tf", "atr_4h", "atr_ratio", "regime", "rh", "rl", "rh_touches", "rl_touches")
CARRY_REGIME = ("regime", "rh", "rl", "rh_touches", "rl_touches", "atr", "atr_ratio")


def flat_mask(df):
    """Olu mum maskesi (numpy bool): hacim == 0 VE high == low (o==h==l==c). Sutun yoksa/okunamazsa None (karar verilemez); NaN = olu degil."""
    import numpy as np
    try:
        v = df["volume"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        lo = df["low"].to_numpy(dtype=float)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    with np.errstate(invalid="ignore"):
        return (v == 0.0) & (h == lo)


def active_mask(df):
    """Gosterge girdisine GIRECEK (dolu) satirlarin maskesi; hic olu mum yoksa None (cagiran degistirilmemis yolu kullanir)."""
    m = flat_mask(df)
    if m is None or not bool(m.any()):
        return None
    return ~m


def _default_arr(dtype, n: int, col: str):
    import numpy as np
    if col == "reasons":
        return np.full(n, "", dtype=object)
    if col == "regime":
        return np.full(n, "unclear", dtype=object)
    if dtype == object:
        return np.full(n, None, dtype=object)
    if dtype.kind == "b":
        return np.zeros(n, dtype=bool)
    if dtype.kind in "iu":
        return np.zeros(n, dtype=dtype)
    return np.full(n, np.nan, dtype=dtype)


def expand_rows(df_c, full_index, keep, carry: Collection[str]):
    """Dolu satirlara hesaplanmis tabloyu (`df_c`, len == keep.sum()) tam izgaraya (`full_index`) genisletir. `carry` sutunlari olu
    satirlarda SON dolu satirdan tasinir (gecmis; ileri bakma yok; ilk dolu satirdan once varsayilan), digerleri olu satirda
    varsayilan (NaN/None/False/0; `reasons` bos; `regime` 'unclear')."""
    import numpy as np
    import pandas as pd
    n = len(full_index)
    keep = np.asarray(keep, dtype=bool)
    cum = np.cumsum(keep) - 1
    have = cum >= 0
    src = np.where(have, cum, 0)
    cols = {}
    for c in df_c.columns:
        a = df_c[c].to_numpy()
        if c in carry:
            if len(a) == 0:
                res = _default_arr(a.dtype, n, c)
            else:
                res = a[src].copy()
                if not bool(have.all()):
                    res[~have] = _default_arr(a.dtype, n, c)[~have]
        else:
            res = _default_arr(a.dtype, n, c)
            if len(a):
                res[keep] = a
        cols[c] = res
    return pd.DataFrame({c: pd.Series(v, index=full_index, dtype=v.dtype) for c, v in cols.items()}, index=full_index)   # object sutunlar object kalir (pandas 3: str'ye cevrilmesin, None korunur)


def tail_active(df, n: int):
    """Son `n` DOLU satiri (ve aralarindaki olu satirlari) kapsayan kuyruk. Olu satir yoksa `df.iloc[-n:]` (eski davranis AYNEN).
    Pencere boyu gosterge yariomrunu dolu bar sayisiyla olcmeli: seansli enstrumanda olu mumlar pencereyi 4-5 kat kisaltir."""
    keep = active_mask(df)
    if keep is None:
        return df.iloc[-n:] if n > 0 else df.iloc[0:0]
    import numpy as np
    pos = np.flatnonzero(keep)
    if len(pos) <= n:
        return df
    return df.iloc[int(pos[-n]):]


def regime_series(h4, rp):
    """4s rejim tablosu TAM 4s izgarasinda: olu 4s mumlar rejim hesabindan cikarilir, sonuc son dolu satirdan tasinir."""
    from trader_core import regime as R
    keep = active_mask(h4)
    if keep is None:
        return R.classify_series(h4[_OHLC], rp)
    return expand_rows(R.classify_series(h4[keep][_OHLC], rp), h4.index, keep, CARRY_REGIME)


def core_signals(trig, reg, params):
    """Ortak `compute_signals` tablosu. Doner (tam_izgara_tablo, dolu_satir_tablosu, dolu_tetik): olu mum yoksa ucu de ayni nesne/yol
    (eski davranis AYNEN). `reg`: `regime_series` ciktisi (tam 4s izgarasi); dolu tetik barlarina hizalanir."""
    from trader_core import regime as R
    from trader_core import signals as S
    keep = active_mask(trig)
    if keep is None:
        core = S.compute_signals(trig[_OHLC], R.align_to_base(reg, trig.index, 4), params)
        return core, core, trig
    tc = trig[keep]
    core_c = S.compute_signals(tc[_OHLC], R.align_to_base(reg, tc.index, 4), params)
    return expand_rows(core_c, trig.index, keep, CARRY_SIGNAL), core_c, tc


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


def arm_full(held_arm_ids: Sequence[str], arm_id: str, cap: int | None) -> bool:
    """`held_arm_ids`: acik + acilmakta pozisyonlarin arm_id'leri. cap None => dolu degil."""
    return cap is not None and sum(1 for a in held_arm_ids if a == arm_id) >= cap
