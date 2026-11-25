"""ML1 izole cikis simulatoru: TEK adayi (portfoy/kapasite/kume YOK) 15 dk izgarada motorun cikis mantigiyla oynatir.

Motoru aday basina calistirmaz; motorun SAF cikis islevlerini yeniden kullanir ve 15 dk adim semantigini
(`target_mode="resting"`, kagit: `exit_counterfactual.replay_trail(step_15m=True)` ile ledger-parite testli) taklit eder:
  * `exit_modes` (be_stop / tighter / partial_qty / reached_r esigi / resolve), `signals` (regime_flip_exit, time_stop_due,
    TRAIL_START_R, EPS; iz yolu `trail_stop_path` ile birebir esdeger artimli adim `trail_step`), `exit_counterfactual.funding_payment`
    (vektorel esdeger; testle esitlik), `risk.loss_at_stop` (R birimi, costs.CostConfig.r_unit), `arms.exit_mode/time_stop_of`.

Semantik (docs/ml1 plani bolum 2):
  * Giris: karar D (= kurulum tf'sinin KAPANIS zamani, tf sinirinda) sonrasi ilk 15 dk mumunun ACILISI + giris kaymasi (taraf aleyhine).
  * Dinlenen stop (+ hedef kurulumlarda dinlenen hedef) giris mumundan itibaren gecerli. Ayni mumda stop ve hedef: STOP once.
    Mum acilisi stop'u asmissa dolum acilista (kayma: stop 5 bps); hedef icin dolum min(hedef|acilis, last_high) + cikis kaymasi.
  * Basa-bas ve kismi kar alma HER 15 dk kapanisinda (motorun 15 dk karar adimi) o ana dek en iyi uca (15 dk high/low, giris dolumundan
    itibaren; motor: dakikalik mfe/mae) bakar: BE stopu sonraki 15 dk mumundan gecerli (stop zaten asilmissa -> would_trigger: piyasa
    cikisi sonraki acilista, neden `trail_stop`); kismi sonraki 15 dk acilisinda `pt_frac` kadar piyasada dolar (bir kez).
  * Iz suren stop (trail kurulumlari), rejim cikisi, zaman durdurma, kural cikisi (EXIT_RULE) YALNIZ kurulumun KENDI tf kapanisinda
    degerlenir; cikis sonraki 15 dk acilisinda piyasa dolumu (cikis kaymasi). Sira motorla ayni: once evaluate_exit karari
    (regime_flip -> trail crossed -> stop_update; hedef kipinde kural cikisi -> time_stop), karar cikis degilse BE, kismi, sonra iz stopu.
  * Ufuk: 30 gun (`horizon_days`; zaman stopu olan hedef kollarinda max(30 gun, (time_stop+1) x tf)) -> son 15 dk kapanisinda piyasaya gore degerlendirilir: exit_reason='horizon', censored=1.
    Veri biterse (ufuktan once) status='open', exit_ts=None, exit_reason='open', censored=1, R NaN (sonra yeniden simule edilir).
    Veri deligi: status='data_gap'.
  * Funding: (giris, cikis] araligindaki funding noktalari; odenen = side x adet x mark x rate (mark: noktanin mark'i, yoksa o 15 dk mumunun
    acilisi). Kismi cikista kapanan parca kismi anina dek, kalan parca sonuna dek oder.
  * Maliyet: costs.CostConfig (taker 5 bps/taraf; kayma 2/2/5 bps; hisse/emtia cift-seans ezmeleri DOLUM anina gore).
  * Net R = (brut - ucretler - funding) / (adet x R_unit); R_unit = |e-s| + (e+s) x 0,001 (e = entry_ref = planlanan giris, s = stop;
    ledger `planned_risk = loss_at_stop(qty, planned_entry, stop)`, `r_multiple = realized / planned_risk`).

ADAY ALANLARI (`simulate_rows` satirlari; dict ya da DataFrame satiri):
  zorunlu:
    decision_ts   karar zamani = sinyal mumunun KAPANISI (kurulum tf sinirinda). epoch ms (int) / pandas Timestamp / datetime / datetime64.
                  Scan tarafi: sinyal mumunun acilisi + tf.
    pair          'BTC/USDT' (yalniz maliyet ezmeleri icin)
    tf            '15m' | '1h' | '4h' | '1d'
    setup         kurulum kodu ('T1', 'H2-YARI', ...; cikis kipi ve zaman stopu kayit defterinden)
    side          'long' | 'short'
    entry_ref     planlanan giris (motor planned_entry; R_unit icin). Genellikle sinyal mumunun kapanisi.
    stop          planlanan ilk stop (planned_stop)
  istege bagli:
    qty           yalniz `SimConfig.lot_rules` ile: kismi adet yuvarlamasi icin pozisyon adedi (R adetten bagimsizdir)
    arm_id        'T1@1h' (yoksa setup@tf; yalniz gecirilir)
    target        planlanan hedef (planned_target; NaN/None -> hedef yok). Yalniz EXIT_MODE='target' kurulumlarda kullanilir.
    atr           bilgi amacli (iz stopu simulatorde `bars_tf['atr_tf']` serisinden hesaplanir; motorla ayni)
    exit_mode     'trail' | 'target' (yoksa arms.exit_mode(setup))
    time_stop     tf mumu cinsinden zaman stopu (yoksa arms.time_stop_of(setup, tf); trail kurulumlarda kullanilmaz)
    trail_atr     iz carpani (yoksa signals.DEFAULT_SIGNAL_PARAMS.trail_atr = 3.0)
    exit_modes    exit_modes.ExitModes | None (yoksa `cfg_modes` + resolve(): motorun cift/kurulum/default cozumu; engine.paper.json
                  default = basa-bas + kismi, H2-YARI: kismi 2R)
    rule_exit_ts  EXIT_RULE kurulumlari icin: kural cikisinin dogru oldugu tf-KAPANIS zamanlarinin (ms) sirali listesi (kapanis
                  zamani t icin kural yalniz t'ye kadar olan mumlardan hesaplanir); yoksa kural cikisi yok.
BARLAR:
  bars_15m   DataFrame, indeks = acilis zamani (UTC), sutunlar open/high/low/close (futures `last`; mark yok). Tek cift.
  bars_tf    DataFrame (satirlardaki tf'nin barlari) ya da {tf: DataFrame}: open/high/low/close + `atr_tf` (core compute_signals ATR(14),
             yoksa hesaplanir) + `regime` (hizalanmis 4s rejimi; yoksa rejim cikisi yok). Indeks = acilis zamani. `prepare_tf(trig, core)`.
  funding    None (funding 0) ya da DataFrame/Series: indeks = funding zamani, `funding_rate` [+ `mark`].
CIKTI (aday basina dict; girdi sirasi korunur): aday kimligi alanlari + status ('ok'|'open'|'invalid'|'no_data'|'data_gap'),
  entry_ts, entry_px, exit_ts, exit_px (adet agirlikli karma; ledger gibi), exit_px_last, exit_reason ('stop'|'trail_stop'|'target'|
  'time_stop'|'regime_flip'|'other'|'horizon'|'open'|...), partial_ts, partial_px, partial_frac, fee, funding (birim adet icin para),
  r_unit, gross_R, fee_R, funding_R, net_R, mfe_R, mae_R, bars_held (15 dk mum), censored (0/1), be_moved (0/1). *_ts: epoch ms.
  `to_frame(sonuc)` UTC datetime sutunlarina cevirir.

Bilinen sapmalar (motorla): tetik kaynagi mark degil last (1 dk yok; 15 dk mum ici sira); adet yuvarlamasi yok (isteğe bagli `lot_rules`+`qty`);
likidasyon yok; tick yuvarlamasi yok; ayni 15 dk mumunda giris dakikasindan once olusan stop vurusu giris mumu stop'una dahil.
"""
from __future__ import annotations

import json
import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from trader_core import exit_modes as XM
from trader_core import signals as S
from trader_core.exit_counterfactual import funding_payment  # noqa: F401  (esitlik testi: vektorel funding bununla ayni)

from .costs import CostConfig, exit_fill, entry_fill, load_cost_config

M15_MS = 900_000
TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
HORIZON_DAYS = 30
EPS = S.EPS
_NAN = float("nan")

STATUS_OK, STATUS_OPEN, STATUS_INVALID, STATUS_NO_DATA, STATUS_GAP = "ok", "open", "invalid", "no_data", "data_gap"


# ---------------------------------------------------------------------------------------------------------- zaman / veri
def to_ms(x) -> int:
    """epoch ms (int/float) | Timestamp | datetime (tz yoksa UTC) | datetime64 -> int ms."""
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, float):
        return int(x)
    if isinstance(x, np.datetime64):
        return int(x.astype("datetime64[ms]").astype("int64"))
    if isinstance(x, pd.Timestamp):
        return int(x.value // 1_000_000)                  # value: UTC ns (tz yoksa UTC sayilir)
    if isinstance(x, datetime):
        x = x if x.tzinfo is not None else x.replace(tzinfo=timezone.utc)
        return int(round(x.timestamp() * 1000))
    raise TypeError(f"zaman cevrilemedi: {x!r}")


def _index_ms(idx: pd.DatetimeIndex) -> np.ndarray:
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    return np.asarray(idx.as_unit("ms").asi8, dtype=np.int64)


class Bars15:
    """15 dk son-fiyat barlari (liste tabanli; dongu icin hizli). Kesintisiz kosu sonlari onceden hesaplanir."""

    def __init__(self, df: pd.DataFrame) -> None:
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()
        t = _index_ms(df.index)
        if len(t) and len(np.unique(t)) != len(t):
            raise ValueError("bars_15m indeksi tekrar iceriyor")
        self.n = len(t)
        self.t_np = t
        self.t = t.tolist()
        self.o = df["open"].to_numpy(float).tolist()
        self.h = df["high"].to_numpy(float).tolist()
        self.l = df["low"].to_numpy(float).tolist()
        self.c = df["close"].to_numpy(float).tolist()
        self.o_np = df["open"].to_numpy(float)
        gaps = np.flatnonzero(np.diff(t) != M15_MS) if self.n > 1 else np.empty(0, dtype=np.int64)
        pos = np.searchsorted(gaps, np.arange(self.n), side="left")
        end = np.append(gaps, max(self.n - 1, 0))[pos]
        self.run_end = end.astype(np.int64).tolist()                      # i'den baslayan kesintisiz kosunun son dizini

    def ix(self, ms: int) -> int | None:
        i = bisect_left(self.t, ms)
        return i if i < self.n and self.t[i] == ms else None


class TfBars:
    """Kurulum tf'sinin barlari: high/low/close + atr_tf + regime; acilis zamani -> dizin sozlugu."""

    def __init__(self, df: pd.DataFrame, tf: str) -> None:
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()
        self.tf = tf
        t = _index_ms(df.index)
        self.pos = {int(m): i for i, m in enumerate(t.tolist())}
        self.h = df["high"].to_numpy(float).tolist()
        self.l = df["low"].to_numpy(float).tolist()
        self.c = df["close"].to_numpy(float).tolist()
        if "atr_tf" in df.columns:
            atr = df["atr_tf"].to_numpy(float)
        else:
            from trader_core import indicators as I
            atr = I.atr(df[["high", "low", "close"]], S.ATR_LEN).to_numpy(float)
        self.atr = atr.tolist()
        self.regime = df["regime"].tolist() if "regime" in df.columns else [None] * len(df)


def prepare_tf(trig: pd.DataFrame, core: pd.DataFrame) -> pd.DataFrame:
    """Scan tarafi yardimcisi: tf mumlari + core tablosundan `atr_tf`/`regime` (ayni indeks)."""
    out = trig[["open", "high", "low", "close"]].copy()
    out["atr_tf"] = core["atr_tf"].reindex(out.index).to_numpy(float)
    out["regime"] = core["regime"].reindex(out.index).to_numpy(dtype=object)
    return out


class Funding:
    """Funding noktalari (sirali) + kumulatif mark x rate; kapali aralik toplami O(1)."""

    def __init__(self, df: pd.DataFrame | pd.Series | None, b15: Bars15) -> None:
        if df is None or len(df) == 0:
            self.t: list[int] = []
            self.cum = np.zeros(1)
            return
        if isinstance(df, pd.Series):
            df = df.to_frame("funding_rate")
        df = df.sort_index()
        t = _index_ms(df.index)
        rate = df["funding_rate"].to_numpy(float)
        if "mark" in df.columns:
            mark = df["mark"].to_numpy(float)
        else:
            mark = np.full(len(t), np.nan)
        miss = ~np.isfinite(mark)
        if miss.any():                                                   # nokta mark'i yok: o anki (ya da onceki) 15 dk mumunun acilisi
            ii = np.clip(np.searchsorted(b15.t_np, t, side="right") - 1, 0, max(b15.n - 1, 0))
            mark = np.where(miss, b15.o_np[ii] if b15.n else np.nan, mark)
        self.t = t.tolist()
        self.cum = np.concatenate([[0.0], np.cumsum(np.nan_to_num(mark * rate))])

    def span(self, a_ms: int, b_ms: int) -> float:
        """(a, b] araligindaki toplam mark x rate (birim adet, long odemesi)."""
        if not self.t or b_ms <= a_ms:
            return 0.0
        i0 = bisect_right(self.t, a_ms)
        i1 = bisect_right(self.t, b_ms)
        return float(self.cum[i1] - self.cum[i0])


# ---------------------------------------------------------------------------------------------------------- iz stopu adimi
def trail_step(long: bool, cur: float, ext: float, fill: float, risk_px: float, atr: float, trail_atr: float) -> float:
    """`signals.trail_stop_path`in tek adimi (ext: kosan en yuksek (long) / en dusuk (short), mevcut mum dahil). Monoton.
    risk_px = |fill - initial_stop|. Testle `trail_stop_path` ile esitlik denetlenir."""
    if atr != atr:                                       # NaN
        return cur
    if long:
        if ext >= fill + S.TRAIL_START_R * risk_px - EPS:
            cand = ext - trail_atr * atr
            if cand > cur:
                return cand
    else:
        if ext <= fill - S.TRAIL_START_R * risk_px + EPS:
            cand = ext + trail_atr * atr
            if cand < cur:
                return cand
    return cur


# ---------------------------------------------------------------------------------------------------------- yapilandirma
@dataclass
class SimConfig:
    cost: CostConfig
    cfg_modes: Mapping[str, Mapping] = field(default_factory=dict)       # exit_modes.build_config(...) ciktisi
    horizon_days: int = HORIZON_DAYS
    lot_rules: tuple[float, float, float] | None = None                   # (adim, min adet, min notional); verilirse kismi adet motorla ayni yuvarlanir
    qty: float | None = None                                              # lot_rules ile birlikte (kismi yuvarlamasi icin); R adetten bagimsizdir


def load_sim_config(config_dir: str | Path | None = None, **kw) -> SimConfig:
    """engine.base.json + engine.paper.json: maliyet + exit_modes (kagit varsayilani)."""
    from .costs import CONFIG_DIR
    d = Path(config_dir) if config_dir is not None else CONFIG_DIR
    cost = load_cost_config(d)
    raw = json.loads((d / "engine.paper.json").read_text(encoding="utf-8")).get("exit_modes")
    return SimConfig(cost=cost, cfg_modes=XM.build_config(raw), **kw)


_ARM_CACHE: dict[tuple, tuple] = {}


def _arm_info(setup: str, tf: str) -> tuple[str | None, int]:
    k = (setup, tf)
    v = _ARM_CACHE.get(k)
    if v is None:
        from trader_engine.strategies import arms as _arms
        v = (_arms.exit_mode(setup), _arms.time_stop_of(setup, tf))
        _ARM_CACHE[k] = v
    return v


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and x != x)


# ---------------------------------------------------------------------------------------------------------- tek aday
def _blank(c: Mapping, status: str) -> dict:
    return {"decision_ts": c.get("decision_ts"), "pair": c.get("pair"), "tf": c.get("tf"), "setup": c.get("setup"),
            "arm_id": c.get("arm_id") or f"{c.get('setup')}@{c.get('tf')}", "side": c.get("side"), "status": status,
            "entry_ts": None, "entry_px": _NAN, "exit_ts": None, "exit_px": _NAN, "exit_px_last": _NAN, "exit_reason": status,
            "partial_ts": None, "partial_px": _NAN, "partial_frac": 0.0, "fee": _NAN, "funding": _NAN, "r_unit": _NAN,
            "gross_R": _NAN, "fee_R": _NAN, "funding_R": _NAN, "net_R": _NAN, "mfe_R": _NAN, "mae_R": _NAN,
            "bars_held": None, "censored": 1 if status in (STATUS_OPEN, STATUS_GAP) else 0, "be_moved": 0}


def simulate_one(c: Mapping, B: Bars15, tfs: Mapping[str, TfBars], F: Funding, cfg: SimConfig) -> dict:
    out = _blank(c, STATUS_INVALID)
    side = c["side"]
    if side not in ("long", "short"):
        return out
    long = side == "long"
    sg = 1.0 if long else -1.0
    tf = c["tf"]
    tfms = TF_MS.get(tf)
    if tfms is None:
        return out
    D = to_ms(c["decision_ts"])
    if D % tfms != 0:
        out["exit_reason"] = "decision_not_on_tf_boundary"
        return out
    e = B.ix(D)
    if e is None:
        out["status"] = out["exit_reason"] = STATUS_NO_DATA
        return out
    setup = c["setup"]
    pair = c.get("pair")
    cost = cfg.cost
    mode = c.get("exit_mode")
    tstop = c.get("time_stop")
    if mode is None or tstop is None:
        m0, t0 = _arm_info(setup, tf)
        mode = m0 if mode is None else mode
        tstop = t0 if tstop is None else tstop
    if mode not in ("trail", "target"):
        out["exit_reason"] = "unknown_exit_mode"
        return out
    trail_mode = mode == "trail"
    T = tfs.get(tf)
    if T is None:
        out["status"] = out["exit_reason"] = STATUS_NO_DATA
        return out
    if "exit_modes" in c:
        modes = c["exit_modes"]
    else:
        modes = XM.resolve(cfg.cfg_modes, setup, tf)
    trail_atr = float(c.get("trail_atr") if c.get("trail_atr") is not None else S.DEFAULT_SIGNAL_PARAMS.trail_atr)
    stop0 = float(c["stop"])
    entry_ref = float(c["entry_ref"])
    tgt = c.get("target")
    has_target = (not trail_mode) and (not _nan(tgt)) and math.isfinite(float(tgt))
    tgt = float(tgt) if has_target else _NAN
    qty_c = c.get("qty")
    rule_ts = c.get("rule_exit_ts")
    rule_set = set(int(x) for x in rule_ts) if (rule_ts is not None and len(rule_ts)) else None

    has_ov = pair in cost.overrides
    base = cost.base
    t_, o_, h_, l_, c_ = B.t, B.o, B.h, B.l, B.c
    taker = cost.taker_fee
    sl0 = cost.slips(pair, t_[e]) if has_ov else base
    fill = entry_fill(side, o_[e], sl0.entry_bps)
    if not (math.isfinite(fill) and math.isfinite(stop0) and math.isfinite(entry_ref)):
        return out
    if (long and not stop0 < fill) or ((not long) and not stop0 > fill):
        out["exit_reason"] = "stop_wrong_side"
        return out
    r_unit = cost.r_unit(entry_ref, stop0)
    if not r_unit > 0:
        return out
    risk_px = abs(fill - stop0)
    H15 = int(cfg.horizon_days) * 96
    if not trail_mode and tstop:                            # zaman stopu olan kollarda ufuk zaman stopundan ONCE kesmez: >= (tstop+1) tf mumu
        H15 = max(H15, (int(tstop) + 1) * tfms // M15_MS)
    last_h = e + H15 - 1                                   # ufuk mumu (kapanista degerlenir)
    kend = min(B.run_end[e], e + H15)                       # e+H15: yalniz bekleyen piyasa cikisinin acilis dolumu icin
    be_on = modes is not None and modes.breakeven
    pt_on = modes is not None and modes.partial
    if be_on:
        be_thr = fill + modes.be_trigger_r * risk_px - XM.EPS if long else fill - modes.be_trigger_r * risk_px + XM.EPS
    if pt_on:
        pt_thr = fill + modes.pt_trigger_r * risk_px - XM.EPS if long else fill - modes.pt_trigger_r * risk_px + XM.EPS

    cur = stop0
    best = fill                                            # kosan en iyi/en kotu uc (giris dolumundan; motor mfe/mae)
    worst = fill
    ext = -math.inf if long else math.inf                   # tf mumlarinin kosan ucu (iz yolu)
    trail_val = stop0
    n_closed = 0
    pend: str | None = None                                 # bekleyen piyasa cikisi (sonraki acilista dolar)
    part_at = -1
    part_tried = False
    part_frac = 0.0
    part_px = _NAN
    part_ts = None
    be_moved = 0
    be_done = not be_on
    res: tuple | None = None                                # (neden, ts_ms, px)
    Tpos, Th, Tl, Tc, Ta, Tr = T.pos, T.h, T.l, T.c, T.atr, T.regime
    time_stop_due, regime_flip = S.time_stop_due, S.regime_flip_exit

    k = e
    while k <= kend:
        tk = t_[k]
        ok = o_[k]
        sl = cost.slips(pair, tk) if has_ov else base
        # ---- (1) bekleyen emirler acilista dolar (stop tetiginden once)
        if pend is not None:
            res = (pend, tk, exit_fill(side, ok, sl.exit_bps))
            break
        if part_at == k:
            part_px = exit_fill(side, ok, sl.exit_bps)
            part_ts = tk
            part_at = -1
        if k > last_h:
            break
        hk = h_[k]
        lk = l_[k]
        # ---- (2) dinlenen stop / hedef (ayni mumda stop once; bosluk -> acilis)
        if (lk <= cur) if long else (hk >= cur):
            gap = (ok <= cur) if long else (ok >= cur)
            res = ("trail_stop" if cur != stop0 else "stop", tk, exit_fill(side, ok if gap else cur, sl.stop_bps))
            break
        if has_target and ((hk >= tgt) if long else (lk <= tgt)):
            gap = (ok >= tgt) if long else (ok <= tgt)
            b = ok if gap else tgt
            b = min(b, hk) if long else max(b, lk)
            res = ("target", tk, exit_fill(side, b, sl.exit_bps))
            break
        if long:
            if hk > best:
                best = hk
            if lk < worst:
                worst = lk
        else:
            if lk < best:
                best = lk
            if hk > worst:
                worst = hk
        # ---- (3) bu 15 dk mumunun kapanisi (motor karar adimi)
        C = tk + M15_MS
        ck = c_[k]
        upd = None
        if C % tfms == 0:                                   # kurulumun kendi tf kapanisi
            j = Tpos.get(C - tfms)
            if j is not None:
                n_closed += 1
                if trail_mode:
                    if long:
                        if Th[j] == Th[j] and Th[j] > ext:
                            ext = Th[j]
                    else:
                        if Tl[j] == Tl[j] and Tl[j] < ext:
                            ext = Tl[j]
                    trail_val = trail_step(long, trail_val, ext, fill, risk_px, Ta[j], trail_atr)
                    if regime_flip(side, Tr[j]):
                        pend = "regime_flip"
                    elif trail_val != stop0 and ((trail_val >= Tc[j]) if long else (trail_val <= Tc[j])):
                        pend = "trail_stop"
                    elif (trail_val > cur + EPS) if long else (trail_val < cur - EPS):
                        upd = trail_val
                else:
                    if rule_set is not None and C in rule_set:
                        pend = "other"
                    elif time_stop_due(n_closed, tstop):
                        pend = "time_stop"
        if pend is None:
            if not be_done and ((best >= be_thr) if long else (best <= be_thr)):
                be_done = True                              # tek seferlik: stop yalniz sikilasir
                lvl = XM.be_stop(side, fill, stop0, best, modes)
                if lvl is not None and XM.tighter(side, lvl, cur):
                    if (lvl >= ck) if long else (lvl <= ck):  # would_trigger: stop zaten asilmis -> piyasa cikisi, eski stop kalir
                        pend = "trail_stop"
                    else:
                        cur = lvl
                        be_moved = 1
            if pend is None:
                if pt_on and not part_tried and ((best >= pt_thr) if long else (best <= pt_thr)):
                    part_tried = True
                    part_frac = modes.pt_frac
                    if cfg.lot_rules is not None and (qty_c or cfg.qty):
                        qq = float(qty_c or cfg.qty)
                        q = XM.partial_qty(qq, modes.pt_frac, cfg.lot_rules[0], cfg.lot_rules[1], cfg.lot_rules[2], ck)
                        part_frac = 0.0 if q is None else q / qq
                    if part_frac > 0.0:
                        part_at = k + 1
                if upd is not None and ((upd > cur + EPS) if long else (upd < cur - EPS)):
                    cur = upd
                if k == last_h and res is None:
                    res = ("horizon", C, exit_fill(side, ck, sl.exit_bps))
                    break
        k += 1
    # ---- sonuc
    if res is None:
        out["status"] = STATUS_OPEN if B.run_end[e] == B.n - 1 else STATUS_GAP
        out["exit_reason"] = "open" if out["status"] == STATUS_OPEN else STATUS_GAP
        out["censored"] = 1
        out["entry_ts"] = t_[e]
        out["entry_px"] = fill
        out["r_unit"] = r_unit
        return out
    reason, x_ts, x_px = res
    f = part_frac if part_ts is not None else 0.0
    fin_px = (f * part_px + (1.0 - f) * x_px) if f else x_px
    gross = sg * (fin_px - fill)                            # birim adet
    fee_tot = fill * taker + taker * ((f * part_px + (1.0 - f) * x_px) if f else x_px)
    e_ts = t_[e]
    fund = sg * ((1.0 - f) * F.span(e_ts, x_ts) + (f * F.span(e_ts, part_ts) if f else 0.0))
    out.update(
        status=STATUS_OK, entry_ts=e_ts, entry_px=fill, exit_ts=x_ts, exit_px=fin_px, exit_px_last=x_px, exit_reason=reason,
        partial_ts=part_ts if f else None, partial_px=part_px if f else _NAN, partial_frac=f, fee=fee_tot, funding=fund,
        r_unit=r_unit, gross_R=gross / r_unit, fee_R=fee_tot / r_unit, funding_R=fund / r_unit,
        net_R=(gross - fee_tot - fund) / r_unit, mfe_R=sg * (best - fill) / r_unit, mae_R=sg * (fill - worst) / r_unit,
        bars_held=(x_ts - e_ts) // M15_MS, censored=1 if reason == "horizon" else 0, be_moved=be_moved)
    return out


# ---------------------------------------------------------------------------------------------------------- toplu API
def _as_rows(rows) -> list[Mapping]:
    if isinstance(rows, pd.DataFrame):
        return rows.to_dict("records")
    return list(rows)


def simulate_rows(rows: Iterable[Mapping] | pd.DataFrame, bars_15m: pd.DataFrame | Bars15,
                  bars_tf: pd.DataFrame | Mapping[str, pd.DataFrame] | Mapping[str, TfBars],
                  funding: pd.DataFrame | pd.Series | None = None, *, cfg: SimConfig | None = None,
                  tf: str | None = None) -> list[dict]:
    """Bir CIFT icin aday satirlarini (modul docstring'indeki alanlar) bagimsiz simule eder; girdi sirasinda sonuc listesi doner.
    `bars_tf`: tek DataFrame ise `tf` (ya da satirdaki tf hepsi ayni) kullanilir; sozluk {tf: DataFrame}. `cfg` yoksa config'ten yuklenir."""
    cfg = cfg or load_sim_config()
    rl = _as_rows(rows)
    B = bars_15m if isinstance(bars_15m, Bars15) else Bars15(bars_15m)
    tfs: dict[str, TfBars] = {}
    if isinstance(bars_tf, pd.DataFrame):
        t0 = tf or (rl[0]["tf"] if rl else "1h")
        tfs[t0] = TfBars(bars_tf, t0)
    else:
        for k, v in bars_tf.items():
            tfs[k] = v if isinstance(v, TfBars) else TfBars(v, k)
    F = funding if isinstance(funding, Funding) else Funding(funding, B)
    return [simulate_one(c, B, tfs, F, cfg) for c in rl]


def to_frame(results: Sequence[Mapping]) -> pd.DataFrame:
    """Sonuc sozluklerini DataFrame'e cevirir; *_ts sutunlari UTC datetime (eksikse NaT)."""
    df = pd.DataFrame(list(results))
    for c in ("decision_ts", "entry_ts", "exit_ts", "partial_ts"):
        if c in df.columns:
            df[c] = pd.to_datetime(pd.array([None if (v is None or (isinstance(v, float) and v != v)) else to_ms(v) for v in df[c]], dtype="Int64"),
                                   unit="ms", utc=True)
    return df
