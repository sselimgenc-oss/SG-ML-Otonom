#!/usr/bin/env python3
"""Motor surumu backtest kosucusu (06 §2, §13): `research/run_bt.py` ile ayni CLI bayrak adlari
(`--id --period --fee-mult --slip-bps --tf --params --notes`), ama freqtrade yerine `trader_engine` (ayni Engine +
HistoricalSource + SimClock + PaperBroker). Cikti: var/backtests/<id>/ (+ research/runs/<id>.json ozeti ve
research/trial_registry.csv'ye bir deneme satiri eklenir). HOLDOUT ile kesisen donem reddedilir.

Kullanim: PYTHONPATH=src python research/run_bt_engine.py --id 1h_IS_f2_s2 --period IS --fee-mult 2 --slip-bps 2 --tf 1h \
          [--params '{"trail_atr":3.5}'] [--strategy price_action_v1] [--fill-model native|legacy_compat] [--notes "..."]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_engine import backtest as B  # noqa: E402

RUNS = ROOT / "research" / "runs"
REGISTRY = ROOT / "research" / "trial_registry.csv"
COLS = ["id", "timestamp", "git_commit", "strategy", "params", "period", "cost_arm", "trigger_tf", "trades",
        "expectancy_R", "PF", "maxDD", "notes"]


def append_registry(path: Path, row: dict) -> str:
    """Deneme kaydi ekler (satir no: mevcut satir + 1); donen deger: kayit kimligi `NNN:<id>`."""
    path = Path(path)
    rows = []
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    rid = f"{len(rows) + 1:03d}:{row['id']}"
    row = {c: row.get(c, "") for c in COLS}
    row["id"] = rid
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    return rid


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--id", required=True)
    ap.add_argument("--period", required=True, help="IS | WF | YYYYMMDD-YYYYMMDD")
    ap.add_argument("--fee-mult", type=float, default=2.0)
    ap.add_argument("--slip-bps", type=float, default=2.0)
    ap.add_argument("--tf", default="1h", choices=["1h", "15m"])
    ap.add_argument("--params", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--strategy", default="price_action_v1")
    ap.add_argument("--fill-model", default="native", choices=["native", "legacy_compat"])
    ap.add_argument("--granularity", default=None, choices=["1m", "15m"])
    ap.add_argument("--synthetic-rules", action="store_true")
    ap.add_argument("--no-record-filtered", action="store_true")
    ap.add_argument("--paranoid", nargs="?", const=200, type=int, default=None)
    ap.add_argument("--no-registry", action="store_true", help="deneme kaydina ekleme (yalniz gelistirme)")
    ap.add_argument("--registry", default=str(REGISTRY))
    a = ap.parse_args(argv)
    bt_args = ["--id", a.id, "--period", a.period, "--tf", a.tf, "--fill-model", a.fill_model, "--fee-mult", str(a.fee_mult),
               "--slip-bps", str(a.slip_bps), "--strategy", a.strategy,
               "--env", "eski"]                              # P6-03: bu betik 5 ciftli taban yola dayanir (varsayilan artik kagit ortami)
    if a.params:
        bt_args += ["--params", a.params]
    if a.granularity:
        bt_args += ["--granularity", a.granularity]
    if a.synthetic_rules:
        bt_args.append("--synthetic-rules")
    if a.no_record_filtered:
        bt_args.append("--no-record-filtered")
    if a.paranoid is not None:
        bt_args += ["--paranoid", str(a.paranoid)]
    ap2 = B.build_parser()
    try:
        spec = B.spec_from_args(ap2.parse_args(bt_args), bt_args)
        res = B.run_spec(spec)
    except B.BacktestArgError as e:
        print(f"{e.code}: {e}", file=sys.stderr)
        return B.EXIT_ARG
    except B.LookaheadError as e:
        print(f"lookahead: {e}", file=sys.stderr)
        return B.EXIT_LOOKAHEAD
    except B.DataError as e:
        print(f"veri hatasi: {e}", file=sys.stderr)
        return B.EXIT_DATA
    s = res.summary
    m = res.meta
    fee = B.fee_eff(a.fee_mult, a.slip_bps)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")   # arastirma kosucusu: motor cekirdegi degil
    params = json.loads(a.params) if a.params else {}
    meta = dict(id=a.id, timestamp=now, git_commit=m["git_commit"],
                strategy=f"engine:{m['strategy']}@{m['strategy_version']}", params=params, period=a.period,
                timerange=B.PERIODS.get(a.period, a.period), fee_mult=a.fee_mult, slip_bps=a.slip_bps, fee_eff=fee,
                trigger_tf=a.tf, notes=a.notes, fill_model=m["fill_model"], granularity=m["granularity"],
                coarse=m["coarse"], rules_source=m["rules_source"], duration_s=m["duration_s"])
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"{a.id}.json").write_text(json.dumps({**meta, **s}, indent=1, default=str))
    if not a.no_registry:
        arm = f"fee x{a.fee_mult:g} + {a.slip_bps:g}bps (fee_eff={fee * 100:.3f}%/taraf)"
        dd = s.get("max_dd_pct")
        append_registry(Path(a.registry), dict(
            id=a.id, timestamp=now, git_commit=m["git_commit"], strategy=meta["strategy"],
            params=json.dumps(params, sort_keys=True), period=f"{a.period} {meta['timerange']}", cost_arm=arm,
            trigger_tf=a.tf, trades=s.get("n_trades"),
            expectancy_R="" if s.get("expectancy_R") is None else round(s["expectancy_R"], 4),
            PF="" if s.get("profit_factor") is None else round(s["profit_factor"], 4),
            maxDD="" if dd is None else f"{dd:.2f}%", notes=f"{m['fill_model']}/{m['granularity']}; {a.notes}".strip("; ")))
    print(f"[{a.id}] n={s.get('n_trades')} expR={s.get('expectancy_R')} PF={s.get('profit_factor')} DD={s.get('max_dd_pct')} "
          f"sure={m['duration_s']}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
