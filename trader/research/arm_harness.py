#!/usr/bin/env python3
"""Hafif arastirma donanimi: kagit kurulumlarin (arm) gunluk R serilerini YALNIZ holdout oncesi tarihsel barlardan uretir.

Neden: tam kagit backtest (`backtest --env paper`) cok uzun donemlerde 15 dk adimi basina ~15 sn; PBO icin deneme serisi yok.
Bu donanim her kurulumun KENDI `compute()` fonksiyonunu (strategies/arms/*.py) tum tarih uzerinde bir kez cagirir
(sinyaller nedenseldir: satir t yalniz t'ye kadar bakar), adaylari muhafazakar bir bar-yolu simulatoruyle cozer, gunluk R
toplamlarini yazar. Sinyal mantigi yeniden yazilmadi.

Simulator (muhafazakar; motorun kagit semantigine yakin ama dakika cozunurlugu YOK):
  - giris: karar mumunun bir sonraki tetik mumunun ACILISI, taraf aleyhine kayma ile; stop bu bardan itibaren gecerli;
  - ayni barda stop ve hedef ikisi de degerse STOP once; acilis stop'u asmissa dolum acilista (kotu olan);
  - EXIT_MODE=target: hedef (limit; hedef kaymasi) + 48 mum zaman durdurma (kapanista);
  - EXIT_MODE=trail: signals.trail_stop_path ile ayni formul (1R'de silahlanir, `trail_atr` x ATR), rejim donusu
    (`signals.regime_flip_exit`) ve iz-stop kapanis-capraz cikisi bir SONRAKI barin acilisinda; stop guncellemesi sonraki barda gecerli;
  - kurulum+cift basina ayni anda tek pozisyon; ayni-mum yeniden giris yasagi (cikis barindan once/ayni barda sinyal yok);
  - maliyet: taraf basina taker ucreti (config: 5 bp) x carpan + kayma (giris/cikis/stop ayni `slip` bp); fonlama ve cost_overrides YOK;
  - cozulmemis (veri sonuna/holdout sinirina kadar bitmeyen) islemler DUSULUR (ileriye bakilmaz);
  - kapasite/risk tavanlari (max pozisyon, kume, gunluk kayip) uygulanmaz: seri, kurulumun ham aday akisidir.
Veri: `var/history` feather, okuma ANINDA `date < HOLDOUT[0]` suzgeci (holdout satiri hic yuklenmez) ve `check_holdout`.
Yalniz holdout oncesi; mevcut kurulum paketini degistirmez, `build_registry.py` calistirmaz.

  python research/arm_harness.py            # research/arm_series/*.parquet + meta.json
"""
from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core import indicators as I  # noqa: E402
from trader_core import regime as R  # noqa: E402
from trader_core import signals as S  # noqa: E402
from trader_engine.bars import MIN_CONTIG_ARM, STARTUP_BARS_ARM, aggregate_4h_to_1d  # noqa: E402
from trader_engine.holdout import HOLDOUT, check_holdout  # noqa: E402
from trader_engine.strategies.arms import ArmInput, find_arm  # noqa: E402
from trader_core.arm_time import arm_tf_delta  # noqa: E402

CUT = HOLDOUT[0]
GRID_START = pd.Timestamp("2021-01-01", tz="UTC")   # gun izgarasinin baslangici; daha eski mumlar (2020 listelenen cift) okunmaz, tum ciftlerde ayni baslangic
HISTORY = ROOT / "var" / "history"
HISTORY_PRE = ROOT / "var" / "history_pre"   # research/pbo_veri_indir.py: kagit evreninin geri kalani; holdout satiri YOK (muhurlu var/history'ye dokunulmaz)
OUT_DIR = ROOT / "research" / "arm_series"
TAKER_FEE = 0.0005                       # config/engine.base.json cost.taker_fee
CFG_SLIP = (2.0, 2.0, 5.0)               # config: slip_entry/exit/stop bp (yalniz referans satiri; deneme sayilmaz)
BASE_PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50, "stop_buffer_atr": 0.3,
               "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}   # = SignalParams() varsayilanlari
OHLC = ["open", "high", "low", "close"]
TFS = ("15m", "1h", "4h", "1d")
EPS = S.EPS
CORE_SENSITIVE = {"range_width_atr", "vol_ratio_max", "edge_zone_atr", "pullback_ema", "stop_buffer_atr", "range_target_frac", "rr_min"}

# ----------------------------------------------------------------------------------------- ON-KAYITLI IZGARA
# Sonuclara bakilmadan ONCE ilan edildi (research/arm_series/grid_declared.json + sha256; run meta'sinda tekrarlanir).
# Deneme = (kurulum, zaman dilimi, parametre varyanti, maliyet) uclusu; HER biri DSR deneme sayisina girer.
# Parametre varyantlari: tek-seferde-bir-parametre (OAT), 3 duzey, (varsayilan, dusuk, yuksek); varsayilan tek kez sayilir.
#   sig = SignalParams alani, mod = kurulum modulunun sabiti (modul degistirilmez; calisma sirasinda gecici setattr).
COSTS = ((1.0, 0.0), (1.0, 5.0), (2.0, 0.0), (2.0, 5.0))        # (ucret carpani, kayma bp: giris=cikis=stop)
GRID: dict[str, dict] = {
    "T1": {"tfs": ("4h", "1d"), "oat": {"sig:pullback_ema": (20, 50, 50), "sig:stop_buffer_atr": (0.2, 0.3, 0.5), "sig:trail_atr": (2.5, 3.0, 3.5)}},
    "R1": {"tfs": ("4h", "1d"), "oat": {"sig:range_target_frac": (0.6, 0.75, 0.9), "sig:rr_min": (1.25, 1.5, 1.75), "sig:stop_buffer_atr": (0.2, 0.3, 0.5)}},
    "TF1": {"tfs": TFS, "oat": {"mod:BRK_ATR": (0.1, 0.2, 0.3), "mod:BODY_MIN": (0.4, 0.5, 0.6), "sig:trail_atr": (2.5, 3.0, 3.5)}},
    "B1": {"tfs": TFS, "oat": {"mod:BRK_ATR": (0.1, 0.2, 0.3), "mod:TARGET_R": (1.5, 2.0, 2.5), "sig:stop_buffer_atr": (0.2, 0.3, 0.5)}},
    "H2": {"tfs": TFS, "oat": {"mod:PB_MIN_ATR": (0.75, 1.0, 1.5), "mod:LEG_GAP_MAX": (6, 10, 14), "sig:trail_atr": (2.5, 3.0, 3.5)}},
    "S1": {"tfs": TFS, "oat": {"mod:BOX_W_ATR": (2.5, 3.0, 3.5), "mod:BRK_ATR": (0.05, 0.1, 0.2), "sig:trail_atr": (2.5, 3.0, 3.5)}},
    "F1": {"tfs": TFS, "oat": {"mod:SWEEP_ATR": (0.05, 0.1, 0.2), "mod:REJ_MIN": (0.5, 0.6, 0.7), "sig:rr_min": (1.25, 1.5, 1.75)}},
}
# OAT'ta "varsayilan" ortadaki degerdir (T1 pullback_ema'da 50 = varsayilan, ucuncu deger tekrar: dusuk 20 / varsayilan 50 -> 2 varyant)


def variants(setup: str) -> list[dict]:
    """[{tag, sig, mod}] : varsayilan + her parametrenin varsayilan-disi duzeyleri (tekrarsiz)."""
    oat = GRID[setup]["oat"]
    out = [{"tag": "def", "sig": {}, "mod": {}}]
    mod_mod = find_arm(setup)
    for key, levels in oat.items():
        kind, name = key.split(":")
        default = BASE_PARAMS[name] if kind == "sig" else getattr(mod_mod, name)
        seen = {default}
        for v in levels:
            if v in seen:
                continue
            seen.add(v)
            out.append({"tag": f"{name}={v}", "sig": {name: v} if kind == "sig" else {}, "mod": {name: v} if kind == "mod" else {}})
    return out


def declared_grid() -> dict:
    g = {"costs_fee_mult_slip_bp": [list(c) for c in COSTS], "kurulumlar": {}}
    for s in GRID:
        g["kurulumlar"][s] = {"tfs": list(GRID[s]["tfs"]), "parametre_varyantlari": [v["tag"] for v in variants(s)]}
    return g


def grid_sha(g: dict | None = None) -> str:
    return hashlib.sha256(json.dumps(g or declared_grid(), sort_keys=True).encode()).hexdigest()


@contextmanager
def patched(mod, over: dict):
    """Kurulum modulunun sabitlerini gecici degistirir (dosya degismez); cikista geri koyar."""
    old = {k: getattr(mod, k) for k in over}
    for k, v in over.items():
        setattr(mod, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(mod, k, v)


# ----------------------------------------------------------------------------------------- veri
def history_stem(pair: str) -> str:
    return pair.replace("/", "_") + "_USDT"


def load_pre_holdout(history_dir: Path, pair: str, tf: str) -> pd.DataFrame | None:
    """Tarihsel mumlar; kilitli donem satirlari DOSYA OKUMASINDA suzulur (hic yuklenmez). Dosya yoksa None."""
    import pyarrow as pa
    import pyarrow.dataset as ds
    path = Path(history_dir) / f"{history_stem(pair)}-{tf}-futures.feather"
    if not path.exists() and Path(history_dir) == HISTORY:
        path = HISTORY_PRE / path.name
    if not path.exists():
        return None
    cut = pa.scalar(CUT, type=pa.timestamp("ms", tz="UTC"))
    t = ds.dataset(str(path), format="feather").to_table(columns=["date", *OHLC, "volume"], filter=(ds.field("date") < cut) & (ds.field("date") >= pa.scalar(GRID_START, type=pa.timestamp("ms", tz="UTC"))))
    df = t.to_pandas()
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df.set_index("date").sort_index()
    if len(df):
        check_holdout(df.index[0].to_pydatetime(), min(df.index[-1] + pd.Timedelta(days=1), pd.Timestamp(CUT)).to_pydatetime())   # satirlar zaten < CUT
    return df


def trigger_bars(history_dir: Path, pair: str, tf: str) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """(trig, h4): 1g = UTC gununun 6 x 4s barindan toplanir (motorla ayni)."""
    h4 = load_pre_holdout(history_dir, pair, "4h")
    if h4 is None or len(h4) == 0:
        return None
    if tf == "4h":
        return h4, h4
    if tf == "1d":
        return aggregate_4h_to_1d(h4), h4
    trig = load_pre_holdout(history_dir, pair, tf)
    return (None, h4) if trig is None else (trig, h4)


# ----------------------------------------------------------------------------------------- simulator
class Bars:
    """Tetik zaman dilimi dizileri (numpy), rejim ve sureklilik."""

    def __init__(self, trig: pd.DataFrame, regime: np.ndarray, tf: str) -> None:
        self.idx = trig.index
        self.t_ns = self.idx.as_unit("ns").asi8
        self.step_ns = int(arm_tf_delta(tf).total_seconds() * 1e9)
        self.o = trig["open"].to_numpy(float)
        self.h = trig["high"].to_numpy(float)
        self.l = trig["low"].to_numpy(float)
        self.c = trig["close"].to_numpy(float)
        self.atr = I.atr(trig[["high", "low", "close"]], S.ATR_LEN).to_numpy(float)
        self.regime = regime
        n = len(trig)
        d = np.diff(self.t_ns)
        gap = np.zeros(n, dtype=bool)                         # gap[k]: k ile k+1 arasi bosluk
        gap[:-1] = d != self.step_ns
        self.gap = gap
        run = np.ones(n, dtype=np.int64)                      # t'de biten kesintisiz bar sayisi
        for k in range(1, n):
            run[k] = run[k - 1] + 1 if not gap[k - 1] else 1
        self.run = run


def trail_update(sgn: float, cur: float, ext: float, fill: float, R: float, atr_k: float, tr: float) -> float:
    """signals.trail_stop_path'in tek adimi (ext: long icin kosan en yuksek, short icin kosan en dusuk). Monoton."""
    if not math.isfinite(atr_k):
        return cur
    if sgn > 0:
        if ext >= fill + S.TRAIL_START_R * R - EPS:
            cand = ext - tr * atr_k
            if cand > cur:
                return cand
    else:
        if ext <= fill - S.TRAIL_START_R * R + EPS:
            cand = ext + tr * atr_k
            if cand < cur:
                return cand
    return cur


def simulate(b: Bars, rows: list[tuple], mode: str, fee: float, slip_bp: float, trail_atr: float,
             horizon: int = S.TIME_STOP_BARS, slips: tuple[float, float, float] | None = None) -> list[tuple]:
    """rows: [(t, sgn, stop, target|nan)] zaman sirali. Doner: [(cikis_ns, r_net, neden, sgn)].
    slips = (giris, cikis, stop) bp; yoksa uc bacak da slip_bp."""
    se, sx, ss = ((slip_bp,) * 3 if slips is None else slips)
    se, sx, ss = se / 1e4, sx / 1e4, ss / 1e4
    n = len(b.c)
    o, h, l, c, atr, t_ns, gap, reg = b.o, b.h, b.l, b.c, b.atr, b.t_ns, b.gap, b.regime
    out: list[tuple] = []
    free_after = -1                                              # bu bara (dahil) kadar sinyal yok
    for t, sgn, stop, target in rows:
        if t <= free_after:
            continue
        e = t + 1
        if e >= n or gap[t]:
            continue
        fill = o[e] * (1.0 + sgn * se)
        risk = sgn * (fill - stop)
        if not (math.isfinite(fill) and math.isfinite(risk) and risk > 0):
            continue
        has_tgt = mode == "target" and math.isfinite(target)
        cur = stop
        ext = -math.inf if sgn > 0 else math.inf
        res = None
        k = e
        while k < n:
            if k > e and gap[k - 1]:
                break                                            # veri boslugu: cozulmemis
            hit_stop = (l[k] <= cur) if sgn > 0 else (h[k] >= cur)
            if hit_stop:                                         # stop ONCE (hedefle ayni barda da)
                px = min(cur, o[k]) if sgn > 0 else max(cur, o[k])
                res = (t_ns[k], px * (1.0 - sgn * ss), "stop", k)
                break
            if mode == "target":
                if has_tgt and ((h[k] >= target - EPS) if sgn > 0 else (l[k] <= target + EPS)):
                    res = (t_ns[k], target * (1.0 - sgn * sx), "target", k)
                    break
                if k - e + 1 >= horizon:
                    res = (t_ns[k] + b.step_ns, c[k] * (1.0 - sgn * sx), "time", k)
                    break
            else:
                ext = max(ext, h[k]) if sgn > 0 else min(ext, l[k])
                cur = trail_update(sgn, cur, ext, fill, risk, atr[k], trail_atr)
                flip = S.regime_flip_exit("long" if sgn > 0 else "short", reg[k])
                crossed = cur != stop and ((cur >= c[k]) if sgn > 0 else (cur <= c[k]))
                if (flip or crossed) and k + 1 < n and not gap[k]:
                    res = (t_ns[k + 1], o[k + 1] * (1.0 - sgn * sx), "regime_flip" if flip else "trail_stop", k)
                    break
            k += 1
        if res is None:
            free_after = n                                       # cozulmemis: sonraki adaylar da bu pozisyonun altinda
            break
        ts_ns, xfill, why, kx = res
        r = (sgn * (xfill - fill) - fee * (fill + xfill)) / risk
        out.append((int(ts_ns), float(r), why, sgn))
        free_after = kx
    return out


# ----------------------------------------------------------------------------------------- adaylar
def core_table(trig: pd.DataFrame, reg: pd.DataFrame, params: S.SignalParams) -> pd.DataFrame:
    aligned = R.align_to_base(reg, trig.index, 4)
    return S.compute_signals(trig[OHLC], aligned, params)


def candidate_rows(setup: str, tf: str, pair: str, trig: pd.DataFrame, h4: pd.DataFrame, params: S.SignalParams,
                   core: pd.DataFrame, bars: Bars) -> list[tuple]:
    """Kurulumun KENDI compute()'u ile tum tarih uzerinde aday satirlari -> [(t, sgn, stop, target)] (signal=True)."""
    mod = find_arm(setup)
    inp = ArmInput(pair=pair, tf=tf, D=trig.index[-1].to_pydatetime() + arm_tf_delta(tf), trig=trig, h4=h4, params=params, core_fn=lambda: core)
    tab = mod.compute(inp)
    sig = tab["signal"].to_numpy(dtype=bool)
    pos = np.flatnonzero(sig)
    start = STARTUP_BARS_ARM[tf]
    side = tab["side"].to_numpy(dtype=object)
    stop = tab["planned_stop"].to_numpy(float)
    tgt = tab["planned_target"].to_numpy(float)
    rows = []
    for t in pos:
        if t < start or bars.run[t] < MIN_CONTIG_ARM["trigger"]:
            continue
        sgn = 1.0 if side[t] == "long" else -1.0
        rows.append((int(t), sgn, float(stop[t]), float(tgt[t])))
    return rows


def day_sums(trades: list[tuple]) -> pd.Series:
    if not trades:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    ts = pd.to_datetime([x[0] for x in trades], unit="ns", utc=True).floor("D")
    return pd.Series([x[1] for x in trades], index=ts).groupby(level=0).sum()


def run_pair(task: tuple) -> dict:
    """Bir (kurulum, cift): tum tf x varyant x maliyet -> {kolon: (gun_ns[], r[], n_islem)}."""
    setup, pair, history_dir = task
    mod = find_arm(setup)
    out: dict[str, tuple] = {}
    stats = {"no_data": [], "n_cand": {}}
    for tf in GRID[setup]["tfs"]:
        got = trigger_bars(Path(history_dir), pair, tf)
        if got is None or got[0] is None or len(got[0]) < STARTUP_BARS_ARM[tf] + 100:
            stats["no_data"].append(tf)
            continue
        trig, h4 = got
        reg4 = R.classify_series(h4[OHLC], S.SignalParams.from_mapping(BASE_PARAMS).regime_params())
        core_cache: dict[tuple, tuple] = {}
        for var in variants(setup):
            sigd = {**BASE_PARAMS, **var["sig"]}
            params = S.SignalParams.from_mapping(sigd)
            key = tuple(sigd[k] for k in sorted(CORE_SENSITIVE)) if getattr(mod, "CORE", False) else None
            if key not in core_cache:
                core = core_table(trig, reg4, params if key is not None else S.SignalParams.from_mapping(BASE_PARAMS))
                core_cache[key] = (core, Bars(trig, core["regime"].to_numpy(dtype=object), tf))
            core, bars = core_cache[key]
            with patched(mod, var["mod"]):
                rows = candidate_rows(setup, tf, pair, trig, h4, params, core, bars)
            stats["n_cand"][f"{setup}@{tf}|{var['tag']}"] = len(rows)
            for fm, sl in COSTS:
                trades = simulate(bars, rows, mod.EXIT_MODE, TAKER_FEE * fm, sl, params.trail_atr)
                s = day_sums(trades)
                out[f"{setup}@{tf}|{var['tag']}|f{fm:g}|s{sl:g}"] = (s.index.as_unit("ns").asi8, s.to_numpy(float), len(trades))
            if var["tag"] == "def":                                # referans: config maliyeti (deneme sayilmaz)
                trades = simulate(bars, rows, mod.EXIT_MODE, TAKER_FEE, 0.0, params.trail_atr, slips=CFG_SLIP)
                s = day_sums(trades)
                out[f"REF|{setup}@{tf}|cfg"] = (s.index.as_unit("ns").asi8, s.to_numpy(float), len(trades))
    return {"series": out, "stats": stats}


# ----------------------------------------------------------------------------------------- toplama / yazma
def _merge(parts: list[dict], days: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict[str, int]]:
    acc: dict[str, np.ndarray] = {}
    ntr: dict[str, int] = {}
    pos = {int(d): i for i, d in enumerate(days.as_unit("ns").asi8)}
    for p in parts:
        for k, (dns, r, n) in p["series"].items():
            a = acc.setdefault(k, np.zeros(len(days)))
            for d, v in zip(dns, r):
                a[pos[int(d)]] += v
            ntr[k] = ntr.get(k, 0) + int(n)
    return pd.DataFrame(acc, index=days).sort_index(axis=1), ntr


def day_grid(start: pd.Timestamp = GRID_START) -> pd.DatetimeIndex:
    end = (pd.Timestamp(CUT) - pd.Timedelta(days=1)).floor("D")
    check_holdout(start.to_pydatetime(), (end + pd.Timedelta(days=1)).to_pydatetime())
    return pd.date_range(start, end, freq="D")


def available_pairs(history_dir: Path, config_pairs: list[str]) -> tuple[list[str], list[str]]:
    def _has(p: str) -> bool:
        name = f"{history_stem(p)}-4h-futures.feather"
        return (Path(history_dir) / name).exists() or (Path(history_dir) == HISTORY and (HISTORY_PRE / name).exists())
    have = [p for p in config_pairs if _has(p)]
    return have, [p for p in config_pairs if p not in have]


def main(argv=None) -> int:
    t0 = time.time()
    cfg = json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))
    pairs, missing = available_pairs(HISTORY, cfg["pairs"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    g = declared_grid()
    gp = OUT_DIR / "grid_declared.json"
    if gp.exists() and json.loads(gp.read_text(encoding="utf-8")) != {"sha256": grid_sha(g), "grid": g}:
        print("UYARI: ilan edilen izgara dosyasi bu kodla uyusmuyor; once ilan dosyasi yenilenmeli (sonuclardan sonra degistirilmez)", file=sys.stderr)
        return 2
    if not gp.exists():
        gp.write_text(json.dumps({"sha256": grid_sha(g), "grid": g}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    days = day_grid()
    meta: dict = {"izgara_sha256": grid_sha(g), "gun_izgarasi": [str(days[0].date()), str(days[-1].date())], "ciftler": pairs,
                  "gecmisi_olmayan_ciftler": missing, "kolonlar": {}, "referans_cfg_maliyet": {}, "dislanan": {}, "sure_sn": {}}
    with mp.get_context("fork").Pool(4) as pool:
        for setup in GRID:
            ts = time.time()
            parts = pool.map(run_pair, [(setup, p, str(HISTORY)) for p in pairs])
            df, ntr = _merge(parts, days)
            ref = {k: v for k, v in df.items() if k.startswith("REF|")}
            df = df[[c for c in df.columns if not c.startswith("REF|")]]
            df.astype("float32").to_parquet(OUT_DIR / f"{setup}.parquet")
            for c in df.columns:
                meta["kolonlar"][c] = {"kurulum": setup, "tf": c.split("@")[1].split("|")[0], "n_islem": ntr[c]}
            for k, v in ref.items():
                meta["referans_cfg_maliyet"][k[4:]] = {"n_islem": ntr[k], "toplam_r": float(v.sum()), "ort_r_islem": float(v.sum() / ntr[k]) if ntr[k] else None}
            meta["sure_sn"][setup] = round(time.time() - ts, 1)
            print(f"{setup}: {df.shape[1]} kolon, {time.time() - ts:.0f} sn", flush=True)
    meta["toplam_sure_sn"] = round(time.time() - t0, 1)
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"bitti: {meta['toplam_sure_sn']} sn")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
