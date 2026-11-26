#!/usr/bin/env python3
"""1h iz-stop gecikmesi salt okunur tanisi (06-crosscheck-sonuc.md "Iz gecikmesi tanisi"; 17 Kasim "aciklanmis esdegerlik" kaydi, madde 3).
Uc 1h kosunun (1h_IS_f1_s0, 1h_WF_f1_s0, 1h_IS_f2_s5) bayrak KAPALI motor ciktisinda (var/bt_base) anahtari eslesen ve cikis
FIYATI 1 tikten fazla farkli her satir icin:
 (i)  referans cikis fiyati, motorun iz-stop yolunun BIR BAR ONCEKI degerine (tik hassasiyetinde) esit mi? Yol, motorun kendi
      `signals.trail_stop_path` + `PrecomputedSignalSource` tablolarindan yeniden uretilir (motor kodu degismez, kosu yapilmaz);
      saglama: yolun SON degeri (motorun kullandigi) motor cikis fiyatina esit olmali.
 (ii) referans cikisi saatin hangi 15 dk alt mumunda (1-4) (referans close_date dakikasi // 15 + 1).
Kullanim: python research/bt_trail_lag_diag.py [--out research/crosscheck/trail_lag_diag.json]
Freqtrade ve kilitli donem calistirilmaz (donemler IS/WF)."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trader_core import signals as S  # noqa: E402
from trader_core.signals import DEFAULT_SIGNAL_PARAMS  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_engine import backtest as BT  # noqa: E402
from trader_engine.bars import floor_tf  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.marketdata.sources import HistoricalSource  # noqa: E402
from trader_engine.precomputed import GuardedView, PrecomputedSignalSource  # noqa: E402
from trader_engine.strategies.registry import get_strategy  # noqa: E402
from trader_engine.numeric import round_nearest  # noqa: E402
import bt_crosscheck as X  # noqa: E402
import bt_chainfree_diag as CF  # noqa: E402

RUNS = ("1h_IS_f1_s0", "1h_WF_f1_s0", "1h_IS_f2_s5")
REF_ROOT = X.REF_ROOT
ENG_ROOT = ROOT / "var" / "bt_base"


def lag_path(signals_src, pair, side, entry_ts, entry_px, init_stop, trail_atr, exit_ts, tf="1h"):
    """Motor stop yolu: giris barindan, `exit_ts`'in saat barindan ONCE kapanmis son bara kadar (engine exit_context ile ayni dilim)."""
    t = signals_src._t[pair]
    D = floor_tf(pd.Timestamp(exit_ts).to_pydatetime(), tf)
    d_ms = int(pd.Timestamp(D).value // 1_000_000)
    tf_ms = 3_600_000
    k = int(np.searchsorted(t.ms, d_ms - tf_ms, side="right"))
    lo_ms = int(pd.Timestamp(floor_tf(pd.Timestamp(entry_ts).to_pydatetime(), tf)).value // 1_000_000)
    lo = int(np.searchsorted(t.ms, lo_ms, side="left"))
    if k == 0 or int(t.ms[k - 1]) != d_ms - tf_ms or k - lo < 3:
        return None
    path = S.trail_stop_path(side, entry_px, init_stop, t.high[lo:k], t.low[lo:k], t.atr[lo:k], trail_atr)
    return path.to_numpy(dtype=float)


def analyse(run: str) -> dict:
    meta = json.loads((ENG_ROOT / f"{run}_compat" / "meta.json").read_text())
    ap = BT.build_parser()
    argv = list(meta["flags"]["argv"])
    if "--env" not in argv:
        argv += ["--env", "eski"]                              # P6-03: bu tani eski taban yola dayanir (varsayilan artik kagit ortami)
    a = ap.parse_args(argv)
    spec = BT.spec_from_args(a, argv)          # holdout kilidi burada da dogrulanir
    runner = BT.BacktestRunner(spec)
    cfg = runner.build_config()
    raw = runner.build_view(cfg)
    view = GuardedView(raw, SimClock(spec.end), fill_model=cfg.cost.fill_model)
    strategy = get_strategy(spec.strategy, mode="backtest")
    params = {k: getattr(DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    params.update(spec.params)
    params["trigger_tf"] = spec.tf
    src = PrecomputedSignalSource(view, strategy, pairs=cfg.pairs, tf=spec.tf, params=params, version_id=1, end=spec.end, strict=True)
    trail_atr = float(params["trail_atr"])
    hist = HistoricalSource(cfg.history_dir if Path(cfg.history_dir).is_absolute() else str(ROOT / cfg.history_dir), granularity="15m", synthetic_rules=True)
    ref_dir, eng_dir = REF_ROOT / run, ENG_ROOT / f"{run}_compat"
    ex = CF.exits(ref_dir, eng_dir, hist, "1h")
    _, etr = X.read_ledger(eng_dir)
    etr["key"] = list(zip(etr["pair"], etr["side"], pd.to_datetime(etr["entry_ts"], utc=True)))
    em = {k: r for k, r in zip(etr["key"], etr.to_dict("records"))}
    rows = []
    for m in ex["mismatches"]:
        if m["px_ok"] or not (m["reason_ok"] and m["time_ok"]):
            continue                                              # yalniz fiyat farki olan satirlar (neden+zaman eslesen)
        e = em[(m["pair"], m["side"], pd.Timestamp(m["entry_ts"]))]
        tick = float(m["tick"])
        row = dict(pair=m["pair"], side=m["side"], entry_ts=m["entry_ts"], reason=m["ref_reason"], ref_exit=m["ref_exit"],
                   ref_px=m["ref_px"], eng_px=m["eng_px"], tick=tick)
        ts = pd.Timestamp(m["ref_exit"])
        row["subcandle"] = int(ts.minute // 15) + 1
        row["setup"] = e["setup"]
        if m["ref_reason"] != "trail_stop" or e["setup"] != "T1":
            row.update(path_ok=None, note="iz stop degil")
            rows.append(row)
            continue
        path = lag_path(src, m["pair"], m["side"], m["entry_ts"], float(e["entry_price"]), float(e["planned_stop"]), trail_atr, ts)
        if path is None:
            row.update(path_ok=None, note="yol yok (kisa)")
            rows.append(row)
            continue
        within = lambda x, y: abs(float(x) - float(y)) <= tick * (1 + 1e-9)       # noqa: E731
        row["path_last"], row["path_prev"], row["path_prev2"] = float(path[-1]), float(path[-2]), float(path[-3])
        row["sanity_last_eq_eng"] = bool(within(path[-1], m["eng_px"]))
        row["prev_exact_tick"] = bool(abs(round_nearest(path[-2], tick) - m["ref_px"]) <= tick * 1e-6) if tick else False
        # yonlu yuvarlama (kisa: asagi, uzun: yukari) tik'e: freqtrade stop yuvarlamasi
        dr = (math.floor(path[-2] / tick + 1e-9) if m["side"] == "short" else math.ceil(path[-2] / tick - 1e-9)) * tick
        row["prev_dir_round"] = bool(abs(dr - m["ref_px"]) <= tick * 1e-6)
        row["prev_le_1tick"] = bool(within(path[-2], m["ref_px"]))
        row["prev_eq_last"] = bool(abs(path[-2] - path[-1]) <= tick * 1e-9)       # yol bir bar once ayni (guncelleme yok)
        row["prev2_le_1tick"] = bool(within(path[-3], m["ref_px"]))
        rows.append(row)
    return dict(run=run, n_matched=ex["n_key_matched"], n_price_mismatch=len(rows), rows=rows)


def table(res: list[dict]) -> str:
    out = ["| Kosu | fiyat farkli satir | iz stop (analiz) | (i) ref = yol[-2] (en yakin tik, birebir) | (i) ref = yol[-2] (yonlu tik: kisa asagi / uzun yukari, birebir) | (i) ref <= 1 tik yol[-2] | yol[-2] == yol[-1] (guncelleme yok) | saglama yol[-1] ~ motor fiyati | (ii) alt mum 1 / 2 / 3 / 4 |", "|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    for r in res:
        a = [x for x in r["rows"] if x.get("path_ok", True) is not None]
        c = Counter(x["subcandle"] for x in r["rows"])
        d = dict(n=len(r["rows"]), t=len(a), ex=sum(x["prev_exact_tick"] for x in a), dr=sum(x["prev_dir_round"] for x in a), le=sum(x["prev_le_1tick"] for x in a),
                 same=sum(x["prev_eq_last"] for x in a), san=sum(x["sanity_last_eq_eng"] for x in a),
                 c1=c[1], c2=c[2], c3=c[3], c4=c[4])
        tot.update(d)
        out.append(f"| {r['run']} | {d['n']} | {d['t']} | {d['ex']} | {d['dr']} | {d['le']} | {d['same']} | {d['san']}/{d['t']} | {d['c1']} / {d['c2']} / {d['c3']} / {d['c4']} |")
    d = tot
    out.append(f"| **toplam** | {d['n']} | {d['t']} | {d['ex']} | {d['dr']} | {d['le']} | {d['same']} | {d['san']}/{d['t']} | {d['c1']} / {d['c2']} / {d['c3']} / {d['c4']} |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--out", default=str(ROOT / "research" / "crosscheck" / "trail_lag_diag.json"))
    ap.add_argument("--runs", default=",".join(RUNS))
    a = ap.parse_args(argv)
    res = [analyse(r) for r in a.runs.split(",")]
    Path(a.out).write_text(json.dumps(res, indent=1, default=str))
    print(table(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
