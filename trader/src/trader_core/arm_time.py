"""Kurulum (arm) zaman dilimi ve seans/kimlik yardimcilari; stdlib (olu mum bolumu numpy/pandas'i islev icinde ice aktarir).

Tek kaynak: `trader_engine.bars` (ARM_TFS, ARM_TF_SECONDS, arm_tf_delta) ve `trader_engine.arm_guard`
(CLASS_*, session_tag, arm_id_of) bu modulu yeniden kullanir; `trader_core.counterfactual` da buradan alir
(trader_core -> trader_engine bagimliligi yasak, tests/engine/test_engine_dependency_direction.py).
Davranis degismez: degerler ve formuller onceki arm_guard/bars tanimlarinin aynisidir.
"""
from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
CLASS_CRYPTO, CLASS_EQUITY, CLASS_COMMODITY = "kripto", "hisse", "emtia"

ARM_TFS = ("15m", "1h", "4h", "1d")                       # kucukten buyuge; oncelik buyuk zaman dilimindedir
ARM_TF_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def arm_tf_delta(tf: str) -> timedelta:
    try:
        return timedelta(seconds=ARM_TF_SECONDS[tf])
    except (KeyError, TypeError):
        raise ValueError(f"bilinmeyen kurulum zaman dilimi: {tf!r}") from None


def arm_id_of(setup: str | None, tf: str | None) -> str:
    """`<kurulum>@<zaman dilimi>`; kurulum/tf yoksa `?` (tavan sayiminda eslesmez)."""
    return f"{setup or '?'}@{tf or '?'}"


def session_tag(cls: str, ts: datetime) -> str:
    """open | closed | weekend (spec §4.2). `ts` tz-bilincli. Hisse: New York 09:30-16:00 Pzt-Cum open (DST'e gore),
    hafta ici dis closed, Cts-Paz weekend. Emtia: Paz 23:00 -> Cum 21:00 UTC open, Cum 21:00 -> Paz 23:00 weekend. Kripto: open."""
    if ts.tzinfo is None:
        raise ValueError("ts tz-bilincli olmali")
    if cls == CLASS_CRYPTO:
        return "open"
    if cls == CLASS_EQUITY:
        t = ts.astimezone(_NY)
        if t.weekday() >= 5:
            return "weekend"
        return "open" if time(9, 30) <= t.time() < time(16, 0) else "closed"
    if cls == CLASS_COMMODITY:
        u = ts.astimezone(timezone.utc)
        wd, hm = u.weekday(), u.time()
        if wd == 5 or (wd == 4 and hm >= time(21, 0)) or (wd == 6 and hm < time(23, 0)):
            return "weekend"
        return "open"
    raise ValueError(f"bilinmeyen varlik sinifi: {cls!r}")


# ---------------------------------------------------------------------------------------------------------------------
# Olu (islem gormeyen) mumlar: seansli hisse/emtia perp'lerinde hafta sonu/tatil/seans disi mumlar hacim 0 ve o==h==l==c gelebilir.
# Bu mumlar gosterge girdisinden CIKARILIR (ATR'ye sifir gercek aralik, EMA'ya tekrarlanan kapanis eklemesinler); sonuc tabloya
# TAM izgara uzerinde geri genisletilir (olu satirlar: aday yok, baglam sutunlari son dolu satirdan tasinir). TEK yer: bu bolum (trader_engine.arm_guard yeniden disa aktarir).
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
    from . import regime as R
    keep = active_mask(h4)
    if keep is None:
        return R.classify_series(h4[_OHLC], rp)
    return expand_rows(R.classify_series(h4[keep][_OHLC], rp), h4.index, keep, CARRY_REGIME)


def core_signals(trig, reg, params):
    """Ortak `compute_signals` tablosu. Doner (tam_izgara_tablo, dolu_satir_tablosu, dolu_tetik): olu mum yoksa ucu de ayni nesne/yol
    (eski davranis AYNEN). `reg`: `regime_series` ciktisi (tam 4s izgarasi); dolu tetik barlarina hizalanir."""
    from . import regime as R
    from . import signals as S
    keep = active_mask(trig)
    if keep is None:
        core = S.compute_signals(trig[_OHLC], R.align_to_base(reg, trig.index, 4), params)
        return core, core, trig
    tc = trig[keep]
    core_c = S.compute_signals(tc[_OHLC], R.align_to_base(reg, tc.index, 4), params)
    return expand_rows(core_c, trig.index, keep, CARRY_SIGNAL), core_c, tc


def strip_dead(df):
    """Olu mumlari atilmis kopya (ML ozellikleri gibi tam izgara gerektirmeyen tuketiciler icin). Olu mum yoksa `df` AYNEN (ayni nesne)."""
    keep = active_mask(df)
    return df if keep is None else df[keep]
