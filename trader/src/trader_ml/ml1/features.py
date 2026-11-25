"""ML1: karar-mumu ozellikleri (HEPSI nedensel: satir D icin yalniz decision_ts <= D bilgisi).

  - pa_*      `trader_core.pa_features.feature_vector` (M1 ile ortak 64-mumluk pencere; yon-isaretli); pencere yetersizse NaN
  - reg_*     karar anindaki 4s rejimi ve ATR/menzil olculeri (core tablosu; 4s mumlar yalniz KAPANMIS olanlar)
  - vol_*     gerceklesen oynaklik (20/100 getiri std), hacim orani, mum menzili/ATR (rolling; yalniz <= t)
  - conf_*    konfluans: AYNI cift ve AYNI yonde, kendisi HARIC adaylarin sayisi, decision_ts in [D - k*tf, D]:
                conf_same_tf   ayni tf'deki adaylar
                conf_all_tf    tum tf'lerdeki adaylar (zaman damgasina gore, <= D)
                conf_groups    bu adaylardaki, satirin KENDI grubundan FARKLI fikir gruplarinin sayisi (tum tf)
                conf_opp       ters yondeki adaylar (ayni pencere, tum tf)
  - hour_utc, dow  takvim (karar aninda bilinir)
`event_id`/`event_weight` EGITIM agirligidir (ozellik DEGIL; gelecekteki adaylara bagli): ayni cift+yon+tf'de ardisik adaylar arasi
bosluk <= k mum ise ayni olay; agirlik = 1 / olay buyuklugu."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from trader_core import arm_time as AT
from trader_core import pa_features as PF
from trader_core import signals as S

K_BARS = 3                                                    # konfluans penceresi (mum, satirin kendi tf'i)
BarsLookup = Callable[[str, str], "tuple[pd.DataFrame, pd.DataFrame] | None"]


def _delta_ns(tf: str) -> int:
    return int(AT.arm_tf_delta(tf).total_seconds() * 1e9)


def _ns(s: pd.Series) -> np.ndarray:
    return pd.DatetimeIndex(s).as_unit("ns").asi8


# ----------------------------------------------------------------------------------------------------------- konfluans
def confluence(c: pd.DataFrame, k: int = K_BARS) -> pd.DataFrame:
    """Konfluans sutunlari (c ile ayni indeks). c: pair, tf, side, group, decision_ts sutunlari; c kendi satirlarini icerir."""
    n = len(c)
    out = {k_: np.zeros(n, dtype=np.int64) for k_ in ("conf_same_tf", "conf_all_tf", "conf_groups", "conf_opp")}
    if n == 0:
        return pd.DataFrame(out, index=c.index)
    ts = _ns(c["decision_ts"])
    w = np.array([k * _delta_ns(t) for t in c["tf"].to_numpy()], dtype=np.int64)
    pair = c["pair"].to_numpy()
    side = c["side"].to_numpy()
    tf = c["tf"].to_numpy()
    grp = c["group"].to_numpy()

    def cnt(sorted_ts: np.ndarray, d: np.ndarray, ww: np.ndarray) -> np.ndarray:
        return np.searchsorted(sorted_ts, d, side="right") - np.searchsorted(sorted_ts, d - ww, side="left")

    for p in np.unique(pair):
        mp = pair == p
        for sd, op in (("long", "short"), ("short", "long")):
            rows = np.flatnonzero(mp & (side == sd))
            if len(rows) == 0:
                continue
            d, ww = ts[rows], w[rows]
            tsa = np.sort(ts[mp & (side == sd)])
            out["conf_all_tf"][rows] = cnt(tsa, d, ww) - 1
            for t in np.unique(tf[rows]):
                mt = tf[rows] == t
                tst = np.sort(ts[mp & (side == sd) & (tf == t)])
                out["conf_same_tf"][rows[mt]] = cnt(tst, d[mt], ww[mt]) - 1
            gcount = np.zeros(len(rows), dtype=np.int64)
            for g in np.unique(grp[mp & (side == sd)]):
                tsg = np.sort(ts[mp & (side == sd) & (grp == g)])
                cg = cnt(tsg, d, ww)
                gcount += (cg > 0) & (grp[rows] != g)                    # kendi grubu haric: BASKA fikir gruplari
            out["conf_groups"][rows] = gcount
            mo = mp & (side == op)
            if mo.any():
                out["conf_opp"][rows] = cnt(np.sort(ts[mo]), d, ww)
    return pd.DataFrame(out, index=c.index)


def events(c: pd.DataFrame, k: int = K_BARS) -> pd.DataFrame:
    """event_id / event_size / event_weight (egitim agirligi; gelecege bagli, ozellik degil)."""
    n = len(c)
    eid = np.empty(n, dtype=object)
    if n:
        ts = _ns(c["decision_ts"])
        key = (c["pair"].astype(str) + "|" + c["side"].astype(str) + "|" + c["tf"].astype(str)).to_numpy()
        for kk in np.unique(key):
            rows = np.flatnonzero(key == kk)
            rows = rows[np.argsort(ts[rows], kind="stable")]
            gap = _delta_ns(kk.split("|")[2]) * k
            new = np.r_[True, np.diff(ts[rows]) > gap]
            start = ts[rows][np.flatnonzero(new)[np.cumsum(new) - 1]]
            eid[rows] = [f"{kk}|{s}" for s in start]
    size = pd.Series(eid, index=c.index).map(pd.Series(eid).value_counts()) if n else pd.Series(dtype=float)
    return pd.DataFrame({"event_id": eid, "event_size": size.to_numpy() if n else [], "event_weight": 1.0 / size.to_numpy() if n else []},
                        index=c.index)


# ----------------------------------------------------------------------------------------------------------- mum ozellikleri
def _vol_table(trig: pd.DataFrame) -> pd.DataFrame:
    c = trig["close"].astype(float)
    ret = np.log(c / c.shift(1))
    v20, v100 = ret.rolling(20).std(), ret.rolling(100).std()
    vol = trig["volume"].astype(float) if "volume" in trig.columns else pd.Series(1.0, index=trig.index)
    vmean = vol.rolling(50).mean()
    rng = (trig["high"] - trig["low"]).astype(float)
    return pd.DataFrame({"vol_20": v20, "vol_100": v100, "vol_ratio": v20 / v100.replace(0, np.nan),
                         "vol_volume_ratio": vol / vmean.replace(0, np.nan), "_rng": rng}, index=trig.index)


def bar_features(c: pd.DataFrame, lookup: BarsLookup, params: S.SignalParams | None = None) -> pd.DataFrame:
    """pa_* / reg_* / vol_* / takvim sutunlari (c ile ayni indeks). `lookup(pair, tf) -> (trig, h4)`. Karar mumu yoksa NaN."""
    params = params or S.DEFAULT_SIGNAL_PARAMS
    names = ["pa_" + x for x in PF.FEATURE_NAMES]
    cols = names + ["reg_atr_ratio", "reg_atr_pct", "reg_atr4h_pct", "reg_rh_dist_atr", "reg_rl_dist_atr", "reg_rh_touches",
                    "reg_rl_touches", "reg_trend_align", "vol_20", "vol_100", "vol_ratio", "vol_volume_ratio", "vol_range_atr",
                    "hour_utc", "dow"]
    out = pd.DataFrame(np.nan, index=c.index, columns=cols)
    if len(c) == 0:
        return out
    pos_of = {ix: j for j, ix in enumerate(c.index)}
    for (pair, tf), sub in c.groupby(["pair", "tf"], sort=False):
        got = lookup(pair, tf)
        if got is None:
            continue
        trig, h4 = got
        i = trig.index.get_indexer(pd.DatetimeIndex(sub["bar_ts"]))
        good = i >= 0
        if not good.any():
            continue
        o, h, l, cl = (trig[x].to_numpy(float) for x in ("open", "high", "low", "close"))
        reg = AT.regime_series(h4, params.regime_params())
        core, _, _ = AT.core_signals(trig, reg, params)
        vt = _vol_table(trig)
        atr = core["atr_tf"].to_numpy(float)
        rows = sub.index[good]
        ii = i[good]
        sides = sub.loc[rows, "side"].to_numpy()
        pa = np.full((len(rows), len(PF.FEATURE_NAMES)), np.nan)
        for j, (t, sd) in enumerate(zip(ii, sides)):
            v = PF.feature_vector(o, h, l, cl, int(t), str(sd))
            if v is not None:
                pa[j] = v
        out.loc[rows, names] = pa
        a = atr[ii]
        out.loc[rows, "reg_atr_ratio"] = core["atr_ratio"].to_numpy(float)[ii]
        out.loc[rows, "reg_atr_pct"] = a / cl[ii]
        out.loc[rows, "reg_atr4h_pct"] = core["atr_4h"].to_numpy(float)[ii] / cl[ii]
        out.loc[rows, "reg_rh_dist_atr"] = (core["rh"].to_numpy(float)[ii] - cl[ii]) / a
        out.loc[rows, "reg_rl_dist_atr"] = (cl[ii] - core["rl"].to_numpy(float)[ii]) / a
        out.loc[rows, "reg_rh_touches"] = core["rh_touches"].to_numpy(float)[ii]
        out.loc[rows, "reg_rl_touches"] = core["rl_touches"].to_numpy(float)[ii]
        rg = core["regime"].to_numpy(dtype=object)[ii]
        out.loc[rows, "reg_trend_align"] = np.where(((rg == "trend_up") & (sides == "long")) | ((rg == "trend_down") & (sides == "short")), 1.0,
                                                    np.where(((rg == "trend_up") & (sides == "short")) | ((rg == "trend_down") & (sides == "long")), -1.0, 0.0))
        for col in ("vol_20", "vol_100", "vol_ratio", "vol_volume_ratio"):
            out.loc[rows, col] = vt[col].to_numpy(float)[ii]
        out.loc[rows, "vol_range_atr"] = vt["_rng"].to_numpy(float)[ii] / a
        idx = trig.index[ii]
        out.loc[rows, "hour_utc"] = idx.hour.to_numpy(float)
        out.loc[rows, "dow"] = idx.day_of_week.to_numpy(float)
    return out


def build_features(c: pd.DataFrame, lookup: BarsLookup | None = None, k: int = K_BARS, with_events: bool = True) -> pd.DataFrame:
    """Aday tablosu + ozellikler (+ olay agirligi). `lookup` None ise yalniz konfluans/olay (mum ozellikleri atlanir)."""
    parts = [c, confluence(c, k)]
    if lookup is not None:
        parts.append(bar_features(c, lookup))
    if with_events:
        parts.append(events(c, k))
    return pd.concat(parts, axis=1)


# ----------------------------------------------------------------------------------------------------------- bellek-dostu yol
# Tam tabloda (milyonlarca satir) build_features OOM yapar: cift+tf parcalari halinde kurup yalniz gerekli sutunlari (izin listesi
# ozellikleri + etiket/olay/degerlendirme sutunlari) float32/category olarak tutariz. Yontem (etiket, olay, konfluans) AYNI;
# konfluans/olay cift basina hesaplanir (zaten cift icinde: anahtar pair|side|tf).
ID_COLS = ("decision_ts", "exit_ts", "pair", "tf", "group", "side", "arm_id", "event_id", "event_weight", "r_net", "status", "censored")
RAW_FOR_DESIGN = ("entry_ref", "stop", "target", "stop_dist_atr")          # model.design_matrix bunlardan stop/hedef turetir (float64 kalir)
CAT_COLS = ("pair", "tf", "group", "side", "arm_id", "status")


def feature_columns() -> list[str]:
    """Izin listesindeki HAM sutunlar (design_matrix'in dogrudan okudugu pa_/reg_/vol_/conf_)."""
    from . import model as M
    return ["pa_" + x for x in PF.FEATURE_NAMES] + list(M.REG_COLS) + list(M.VOL_COLS) + list(M.CONF_COLS)


def slim(df: pd.DataFrame, event_offset: int = 0) -> tuple[pd.DataFrame, int]:
    """build_features cikisindan yalniz gerekli sutunlari birakir: ozellikler float32, event_id int64 (offset'li; pair|side|tf anahtari
    cift icinde oldugundan eslesme/bolunme bozulmaz). Doner (slim_df, kullanilan_event_sayisi)."""
    out = pd.DataFrame(index=df.index)
    for c in ID_COLS:
        if c in df.columns and c != "event_id":
            out[c] = df[c]
    if "event_id" in df.columns:
        codes, uniq = pd.factorize(df["event_id"])
        out["event_id"] = codes.astype(np.int64) + event_offset
        n_ev = len(uniq)
    else:
        n_ev = 0
    for c in RAW_FOR_DESIGN:
        if c in df.columns:
            out[c] = df[c].astype("float64")
    for c in feature_columns():
        if c in df.columns:
            out[c] = df[c].astype("float32")
    return out, n_ev


def build_features_chunked(chunks, lookup_factory: Callable[[str], "BarsLookup | None"] | None = None, k: int = K_BARS,
                           sink: Callable[[str, pd.DataFrame], None] | None = None) -> pd.DataFrame | None:
    """`chunks`: cift basina aday tablolari (her biri TEK cift, tum tf'ler; konfluans icin gerekli). `lookup_factory(pair)` o cifte ait
    mum arama fonksiyonunu verir (fonksiyon birakilinca mumlar serbest kalir). Her parca build_features -> slim. `sink(pair, slim_df)`
    verilirse parcalar oraya yazilir ve None doner; yoksa birlestirilmis slim tablo doner (indeks sifirlanir)."""
    parts, off = [], 0
    for c in chunks:
        if len(c) == 0:
            continue
        pairs = c["pair"].unique()
        assert len(pairs) == 1, "chunk tek cift icermeli"
        lk = lookup_factory(str(pairs[0])) if lookup_factory is not None else None
        f = build_features(c, lk, k)
        del lk
        s, n_ev = slim(f, off)
        off += n_ev
        if sink is not None:
            sink(str(pairs[0]), s)
        else:
            parts.append(s)
    if sink is not None or not parts:
        return None
    return pd.concat(parts, ignore_index=True)


def assemble(parts: list[pd.DataFrame]) -> pd.DataFrame:
    """Cift basina slim tablolari tek tabloya birlestirir (sutun sutun; gecici bellek ~1 sutun), CAT_COLS category (kategoriler siralidir),
    satirlar (decision_ts, arm_id, pair) sirasina dizilir (CandidateTable.read ile ayni sira -> egitimde esit-zaman sirasi ayni)."""
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    cols = list(parts[0].columns)
    cats: dict[str, pd.Index] = {}
    codes: dict[str, np.ndarray] = {}
    for c in CAT_COLS:
        if c not in cols:
            continue
        uniq = pd.Index(sorted({str(x) for p in parts for x in pd.unique(p[c].astype(object)) if pd.notna(x)}))
        cats[c] = uniq
        codes[c] = np.concatenate([uniq.get_indexer(p[c].astype(object).astype(str).where(p[c].notna(), None)) for p in parts]).astype(np.int32)
    ts = np.concatenate([_ns(p["decision_ts"]) for p in parts])
    order = np.lexsort(tuple(codes[c] for c in ("pair", "arm_id") if c in codes) + (ts,))      # son anahtar = birincil
    out: dict[str, object] = {}
    for c in cols:
        if c in cats:
            out[c] = pd.Categorical.from_codes(codes[c][order], categories=cats[c])
        elif isinstance(parts[0][c].dtype, pd.DatetimeTZDtype):
            out[c] = pd.concat([p[c] for p in parts], ignore_index=True).iloc[order].reset_index(drop=True)
        else:
            out[c] = np.concatenate([p[c].to_numpy() for p in parts])[order]
    return pd.DataFrame(out)


def cache_meta(table_dir, hist_dir, k: int = K_BARS) -> dict:
    """Onbellek gecerlilik anahtari: tablo manifesti (kol/cikis hash + satir sayilari), hist dizini, konfluans penceresi."""
    import json
    from pathlib import Path
    mp = Path(table_dir) / "manifest.json"
    m = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}
    return {"arms_hash": m.get("arms_hash"), "exit_hash": m.get("exit_hash"),
            "n_rows": {p: v.get("n_rows") for p, v in sorted(m.get("pairs", {}).items())},
            "hist_dir": None if hist_dir is None else str(hist_dir), "k": k, "v": 2}
