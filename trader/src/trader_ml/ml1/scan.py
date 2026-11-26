"""ML1: bir cift x zaman dilimi icin TUM tarih boyunca kural kollarinin aday taramasi (nedensel; cikis simulasyonu YOK).

Yol (plan bolum 1):
  - taban kollar (T1 R1 TF1 B1 F1 H2 S1): `mod.compute(ArmInput)` tum tarih uzerinde BIR kez; `signal==True` satirlari alinir
    (satir t yalniz t'ye kadar bakar).
  - formasyon kollari (MF1/GF1/IN1/PA2 ve her `*v` varyanti): kutuphane yalniz SON mumu degerlendirir (`_kutuphane.hesapla`),
    bu yuzden her t icin `Gorunum(.., t)` kurulur; ham (`rejim_t`, `ana_satir`) tam tablodan t'ye gore beslenir (HamAt) ve
    `Gorunum.onb` (nedensel gosterge/pivot onbellegi) t'ler arasi PAYLASILIR (614 us -> 35 us / kol-mum).
    `IND_PENCERE` taramada kapatilir (tum seri tek ozyineleme; canli yolda son 1200 mumdan hesap, fark < 1e-15).

Aday satir alanlari (CAND_COLUMNS):
  bar_ts          karar mumunun ACILIS zamani (UTC); decision_ts = bar_ts + tf = karar (kapanis) ani; giris bir SONRAKI mumun acilisi
  pair, tf, arm_id (`SETUP@tf`), setup, family, group, side (long|short)
  entry_ref       planlanan giris = karar mumu kapanisi (gercek simulasyon girisi sonraki acilis; exitsim hesaplar)
  stop, target    gercek fiyat; target NaN = hedefsiz (iz suren stop kipi)
  atr, rr, stop_dist_atr
  exit_mode       "trail" | "target" (arm.EXIT_MODE); time_stop (arm TF mumu, `time_stop_of`; exitsim satir alani adi); rule_exit (kural cikisi var mi:
                  `exit_rule_of(setup)`); trail_atr (SignalParams.trail_atr)
  regime          karar anindaki 4s rejimi (core tablosu)
  ema_value, body_ratio, wick_ratio, edge_dist_atr, pullback_ema   kolun tasiyici ozellikleri
  label           kolun `reasons` etiketi
Cikis alanlari (exit_ts, exit_reason, ...) burada YOK; table.py bos (null) ekler, exitsim doldurur."""
from __future__ import annotations

import contextlib
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from trader_core import arm_time as AT
from trader_core import signals as S
from trader_engine.bars import MIN_CONTIG_ARM, STARTUP_BARS_ARM, window_missing_series
from trader_engine.strategies import arms as A
from trader_engine.strategies.arms import ArmInput
from trader_engine.strategies.arms import _kutuphane as K
from trader_engine.strategies.arms import _pa as P

from . import groups as G

WARMUP_BARS = 1500            # artimli taramada yeni mumlardan once ek isinma (tetik mumu)
WARMUP_DAYS = 120             # ... ve en az bu kadar gun (rejim/4s durumu icin)
CAND_COLUMNS = ["bar_ts", "decision_ts", "pair", "tf", "arm_id", "setup", "family", "group", "side", "entry_ref", "stop", "target",
                "atr", "rr", "stop_dist_atr", "exit_mode", "time_stop", "rule_exit", "trail_atr", "regime",
                "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr", "pullback_ema", "label"]
_SRC = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------------------------------------------- yardimcilar
def run_lengths(index: pd.DatetimeIndex, delta: timedelta) -> np.ndarray:
    """t'de biten kesintisiz mum sayisi (bosluk = ardisik iki mum arasi tf'den farkli)."""
    n = len(index)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    ns = index.as_unit("ns").asi8
    step = int(delta.total_seconds() * 1e9)
    brk = np.r_[True, np.diff(ns) != step]
    first = np.flatnonzero(brk)[np.cumsum(brk) - 1]
    return np.arange(n) - first + 1


@contextlib.contextmanager
def _penceresiz():
    """IN1 `_uz` son IND_PENCERE mumdan hesaplar (basi NaN); tam seride t < n-1200 NaN kalirdi. Tarama icin kapatilir."""
    eski = K.IND_PENCERE
    K.IND_PENCERE = 10 ** 9
    try:
        yield
    finally:
        K.IND_PENCERE = eski


class HamAt:
    """`_Ham`in t'ye gore vekili: yalniz Gorunum/dedektorlerin dokundugu uclar (rejim_t, ana_satir); kalan ham'dan gecer."""
    __slots__ = ("_h", "t", "_m", "_reg")

    def __init__(self, ham: K._Ham, t: int, ana_tablolar: dict, regime: np.ndarray) -> None:
        self._h, self.t, self._m, self._reg = ham, t, ana_tablolar, regime

    def __getattr__(self, n):
        return getattr(self._h, n)

    def rejim_t(self):
        return (str(self._reg[self.t]) or None)

    def ana_satir(self, modul, yon: str):
        tab = self._m.get(modul.SETUP)
        if tab is None:
            tab = self._m[modul.SETUP] = modul.compute(self._h.inp)
        row = tab.iloc[self.t]
        if row["setup"] != modul.SETUP or row["side"] != yon or not bool(row["signal"]):
            return None
        sg = P.SIGN[yon]
        tg = row["planned_target"]
        return {"stop": sg * float(row["planned_stop"]), "hedef": None if not np.isfinite(tg) else sg * float(tg), "satir": row}


def _is_formasyon(mod) -> bool:
    return hasattr(mod, "FORMASYON")


def arms_for_tf(tf: str, arm_ids: list[str] | None = None) -> list[tuple[str, str, object]]:
    """[(arm_id, setup, mod)] bu tf icin kural kollari (config sirasi)."""
    ids = G.rule_arm_ids() if arm_ids is None else list(arm_ids)
    mods = A.discover()
    out = []
    for aid in ids:
        setup, atf = G.split_arm_id(aid)
        if atf == tf and setup in mods and G.family(setup) not in G.DISLANAN_AILELER:
            out.append((aid, setup, mods[setup]))
    return out


def _cand_row(pair, tf, aid, setup, mod, bar_ts, delta, side, entry, stop, target, atr, rr, sda, regime, ema, body, wick, edge, pb,
              label, params) -> dict:
    return {"bar_ts": bar_ts, "decision_ts": bar_ts + delta, "pair": pair, "tf": tf, "arm_id": aid, "setup": setup,
            "family": G.family(setup), "group": G.group(setup), "side": side, "entry_ref": entry, "stop": stop, "target": target,
            "atr": atr, "rr": rr, "stop_dist_atr": sda, "exit_mode": mod.EXIT_MODE, "time_stop": A.time_stop_of(setup, tf),
            "rule_exit": A.exit_rule_of(setup) is not None, "trail_atr": float(params.trail_atr), "regime": regime,
            "ema_value": ema, "body_ratio": body, "wick_ratio": wick, "edge_dist_atr": edge, "pullback_ema": pb, "label": label}


def _empty() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in CAND_COLUMNS})


def _frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        df = _empty()
    else:
        df = pd.DataFrame(rows, columns=CAND_COLUMNS)
    for c in ("bar_ts", "decision_ts"):
        df[c] = pd.to_datetime(df[c], utc=True).astype("datetime64[ns, UTC]")
    for c in ("entry_ref", "stop", "target", "atr", "rr", "stop_dist_atr", "trail_atr", "ema_value", "body_ratio", "wick_ratio",
              "edge_dist_atr"):
        df[c] = df[c].astype("float64")
    df["time_stop"] = df["time_stop"].astype("int64")
    df["pullback_ema"] = df["pullback_ema"].astype("int64")
    df["rule_exit"] = df["rule_exit"].astype(bool)
    return df.sort_values(["decision_ts", "arm_id"], kind="stable").reset_index(drop=True)


# ----------------------------------------------------------------------------------------------------------- tarama
def scan_pair_tf(pair: str, tf: str, trig: pd.DataFrame, h4: pd.DataFrame, arm_ids: list[str] | None = None, *,
                 after: pd.Timestamp | None = None, warmup_bars: int = WARMUP_BARS, warmup_days: int = WARMUP_DAYS,
                 startup: int | None = None, min_contig: int | None = None, params: S.SignalParams | None = None,
                 share_onb: bool = True) -> pd.DataFrame:
    """Aday tablosu (CAND_COLUMNS). `after`: yalniz decision_ts > after olan satirlar (artimli tarama; oncesi isinma icin hesaplanir
    ama atilir). `startup`/`min_contig`: isinma ve kesintisizlik esikleri (varsayilan: bars.STARTUP_BARS_ARM / MIN_CONTIG_ARM;
    isinma TUM tarihe gore sayilir, artimli dilim bunu bozmaz). `share_onb=False`: t basina taze onbellek (yalniz test)."""
    params = params or S.DEFAULT_SIGNAL_PARAMS
    arms = arms_for_tf(tf, arm_ids)
    n_full = len(trig)
    if not arms or n_full == 0:
        return _frame([])
    delta = AT.arm_tf_delta(tf)
    gstart = STARTUP_BARS_ARM[tf] if startup is None else startup
    gcont = MIN_CONTIG_ARM["trigger"] if min_contig is None else min_contig
    run_full = run_lengths(trig.index, delta)
    i_emit, s0 = 0, 0
    if after is not None:
        i_emit = int(trig.index.as_unit("ns").searchsorted(pd.Timestamp(after) - delta, side="right"))      # bar_ts + delta > after
        if i_emit >= n_full:
            return _frame([])
        cut = trig.index[i_emit] - max(warmup_bars * delta, timedelta(days=warmup_days))
        s0 = int(trig.index.searchsorted(cut, side="left"))
    trig_s = trig.iloc[s0:]
    h4_s = h4 if s0 == 0 else h4[h4.index >= trig_s.index[0] - timedelta(days=warmup_days)]
    n = len(trig_s)
    reg = AT.regime_series(h4_s, params.regime_params())
    core, _, _ = AT.core_signals(trig_s, reg, params)
    inp = ArmInput(pair=pair, tf=tf, D=trig_s.index[-1].to_pydatetime() + delta, trig=trig_s, h4=h4_s, params=params,
                   core_fn=lambda: core)
    ham = K._Ham(trig_s, inp)
    regime = core["regime"].to_numpy(dtype=object)
    pos = np.arange(n)
    gecerli = ((s0 + pos) >= gstart) & (run_full[s0:] >= gcont) & (pos >= i_emit - s0)
    idx = trig_s.index
    rows: list[dict] = []
    nerr = 0
    with _penceresiz():
        # ---- taban kollar
        for aid, setup, mod in arms:
            if _is_formasyon(mod):
                continue
            tab = mod.compute(inp)
            sig = tab["signal"].to_numpy(dtype=bool) & gecerli
            for t in np.flatnonzero(sig):
                r = tab.iloc[t]
                rows.append(_cand_row(pair, tf, aid, setup, mod, idx[t], delta, str(r["side"]), float(r["planned_entry"]),
                                      float(r["planned_stop"]), float(r["planned_target"]), float(ham.atr[t]), float(r["rr"]),
                                      float(r["stop_dist_atr"]), str(r["regime"]), float(r["ema_value"]), float(r["body_ratio"]),
                                      float(r["wick_ratio"]), float(r["edge_dist_atr"]), int(r["pullback_ema"]), str(r["reasons"]),
                                      params))
        # ---- formasyon kollari
        forms = [(aid, setup, mod) for aid, setup, mod in arms if _is_formasyon(mod)]
        if forms:
            with np.errstate(invalid="ignore"):
                ok = (pos >= K.MIN_MUM) & gecerli & np.isfinite(ham.o) & np.isfinite(ham.h) & np.isfinite(ham.l) & \
                     np.isfinite(ham.c) & np.isfinite(ham.atr) & (ham.h - ham.l > 0) & (ham.atr > 0)
            ana: dict = {}
            neg = (-ham.o, -ham.l, -ham.h, -ham.c)
            onb = {"long": {}, "short": {}}
            for t in np.flatnonzero(ok):
                ha = HamAt(ham, int(t), ana, regime)
                gs = {"long": K.Gorunum(ham.o, ham.h, ham.l, ham.c, ham.atr, int(t), ham.v, "long", ha, ham.gun, ham.sec),
                      "short": K.Gorunum(neg[0], neg[1], neg[2], neg[3], ham.atr, int(t), ham.v, "short", ha, ham.gun, ham.sec)}
                if share_onb:
                    gs["long"].onb, gs["short"].onb = onb["long"], onb["short"]
                for aid, setup, mod in forms:
                    f = mod.FORMASYON
                    bulgu = {}
                    for side in P.SIDES:
                        try:
                            r = f.bul(gs[side])
                        except Exception:  # noqa: BLE001 - dedektor hatasi = aday yok (sayilir)
                            nerr += 1
                            r = None
                        if r is not None:
                            bulgu[side] = r
                    if len(bulgu) != 1:                      # bos ya da iki yon: aday yok
                        continue
                    side, r = next(iter(bulgu.items()))
                    g = gs[side]
                    s = P.SIGN[side]
                    entry = float(g.c[t])
                    stop = float(r["stop"])
                    risk = entry - stop
                    trail = f.kip == "trail"
                    hedef = r.get("hedef")
                    hedef = None if trail else (entry + 2.0 * risk if hedef is None else float(hedef))
                    if not (risk > 0) or risk < K.MIN_STOP_ORAN * abs(entry):
                        continue                              # stop_width
                    if not trail and not (hedef > entry):
                        continue                              # rr_below_min
                    rng = float(g.h[t] - g.l[t])
                    body = abs(float(g.c[t] - g.o[t])) / rng
                    wick = (float(min(g.o[t], g.c[t]) - g.l[t])) / rng
                    atr = float(ham.atr[t])
                    rr = np.nan if trail else (hedef - entry) / risk
                    etiket = str(r.get("etiket", setup.split("-", 1)[1].lower()))
                    rows.append(_cand_row(pair, tf, aid, setup, mod, idx[t], delta, side, s * entry, s * stop,
                                          np.nan if trail else s * hedef, atr, float(rr), risk / atr, str(regime[t]),
                                          s * float(r.get("seviye", stop)), body, wick, float(r.get("olcu", abs(risk))) / atr,
                                          int(r.get("yas", 0)), f"{setup}_{side}:{etiket}", params))
    df = _frame(rows)
    df.attrs["n_err"] = nerr
    # pencere ici delik GOZLEMI (Paket 2 / C3, motor `PENCERE_DELIK_KIPI = "say"` ile ayni olcu): gecerli karar mumlarindan son STARTUP_BARS_ARM[tf]
    # satirlik penceresinde eksik izgara adimi olanlarin sayisi. Sonuc (aday tablosu) DEGISMEZ.
    df.attrs["pencere_delik"] = int((gecerli & (window_missing_series(trig.index, tf, STARTUP_BARS_ARM[tf])[s0:] > 0)).sum())
    return df


def core_table(trig: pd.DataFrame, h4: pd.DataFrame, params: S.SignalParams | None = None) -> pd.DataFrame:
    """Ortak core tablosu (4s rejimi hizali; exitsim `prepare_tf` girdisi)."""
    params = params or S.DEFAULT_SIGNAL_PARAMS
    core, _, _ = AT.core_signals(trig, AT.regime_series(h4, params.regime_params()), params)
    return core


def rule_exit_close_ms(trig: pd.DataFrame, tf: str, setup: str, side: str) -> np.ndarray:
    """Kural cikisi (EXIT_RULE; IN1 `cikis.fn`) kosulunun dogru oldugu tf-KAPANIS zamanlari (epoch ms, sirali). Kural t'de yalniz
    t'ye kadar mumlari okur (canli: `_kural` son kapanmis mum, yon = acik pozisyonun yonu). exitsim `rule_exit_ts` girdisi."""
    fn = getattr(A.exit_rule_of(setup), "fn", None)
    if fn is None:
        return np.zeros(0, dtype=np.int64)
    ham = K._Ham(trig)
    n = len(trig)
    if side == "long":
        g = K.Gorunum(ham.o, ham.h, ham.l, ham.c, ham.atr, 0, ham.v, "long", None, ham.gun, ham.sec)
    else:
        g = K.Gorunum(-ham.o, -ham.l, -ham.h, -ham.c, ham.atr, 0, ham.v, "short", None, ham.gun, ham.sec)
    hit = []
    with _penceresiz(), np.errstate(invalid="ignore"):
        for t in range(1, n):
            g.t = t
            try:
                if fn(g, t):
                    hit.append(t)
            except Exception:  # noqa: BLE001 - kural hesaplanamazsa cikis yok
                pass
    ms = trig.index.as_unit("ms").asi8 + int(AT.arm_tf_delta(tf).total_seconds() * 1000)
    return ms[np.asarray(hit, dtype=np.int64)]


# ----------------------------------------------------------------------------------------------------------- canli (prefix) esdegeri
def prefix_recompute(pair: str, tf: str, trig: pd.DataFrame, h4: pd.DataFrame, arm_id: str, i: int,
                     params: S.SignalParams | None = None) -> dict | None:
    """Canli yol esdegeri: yalniz `trig[:i+1]` ve D anina kadar KAPANMIS 4s mumlarla `mod.compute`, son satir. Aday varsa
    {side, entry, stop, target} (gercek fiyat), yoksa None. Parite testi ve paranoid kontrol icin."""
    params = params or S.DEFAULT_SIGNAL_PARAMS
    setup, _ = G.split_arm_id(arm_id)
    mod = A.discover()[setup]
    delta = AT.arm_tf_delta(tf)
    pre = trig.iloc[:i + 1]
    D = pre.index[-1].to_pydatetime() + delta
    h4p = h4[h4.index + pd.Timedelta("4h") <= D]
    regp = AT.regime_series(h4p, params.regime_params())
    corep, _, _ = AT.core_signals(pre, regp, params)
    ip = ArmInput(pair=pair, tf=tf, D=D, trig=pre, h4=h4p, params=params, core_fn=lambda: corep)
    r = mod.compute(ip).iloc[-1]
    if not bool(r["signal"]):
        return None
    return {"side": str(r["side"]), "entry": float(r["planned_entry"]), "stop": float(r["planned_stop"]),
            "target": float(r["planned_target"])}


def prefix_rule_exit(pair: str, tf: str, trig: pd.DataFrame, h4: pd.DataFrame, setup: str, side: str, i: int,
                     params: S.SignalParams | None = None) -> bool:
    """Canli yol esdegeri: `EXIT_RULE(inp)` yalniz `trig[:i+1]` ile, `inp.side = side` (kural-cikisi parite testi)."""
    params = params or S.DEFAULT_SIGNAL_PARAMS
    delta = AT.arm_tf_delta(tf)
    pre = trig.iloc[:i + 1]
    D = pre.index[-1].to_pydatetime() + delta
    h4p = h4[h4.index + pd.Timedelta("4h") <= D]
    corep = core_table(pre, h4p, params)
    ip = ArmInput(pair=pair, tf=tf, D=D, trig=pre, h4=h4p, params=params, core_fn=lambda: corep, side=side)
    return bool(A.exit_rule_of(setup)(ip))


# ----------------------------------------------------------------------------------------------------------- hash
_HASH_DOSYALARI = ("trader_core/signals.py", "trader_core/regime.py", "trader_core/arm_time.py", "trader_core/indicators.py",
                   "trader_engine/bars.py", "trader_ml/ml1/scan.py", "trader_ml/ml1/groups.py")


def arms_hash(arm_ids: list[str] | None = None) -> str:
    """Aday tablosunu belirleyen her sey: kol kaynaklari (strategies/arms/*.py), ortak sinyal/rejim/gosterge kodu, tarama kodu,
    SignalParams ve kol listesi. Degisirse tablo YENIDEN kurulur."""
    h = hashlib.sha256()
    for p in sorted((_SRC / "trader_engine" / "strategies" / "arms").glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    for rel in _HASH_DOSYALARI:
        h.update(rel.encode())
        h.update((_SRC / rel).read_bytes())
    h.update(json.dumps(asdict(S.DEFAULT_SIGNAL_PARAMS), sort_keys=True, default=str).encode())
    h.update(json.dumps(sorted(G.rule_arm_ids() if arm_ids is None else arm_ids)).encode())
    return h.hexdigest()
