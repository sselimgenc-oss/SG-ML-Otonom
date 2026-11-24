#!/usr/bin/env python3
"""DD-12 WP-14: kagit kayitlarini JSON satiri olarak disa aktarir (defter SALT OKUNUR; yazmaz).

Her karar icin: decision_id, arm_id, pair, side, bar_close_ts, outcome_ts, r (net R), taken (alindi mi), source
("trade" = kapanan islem R'si; "cf" = alinmayan adayin barrier sonucu). Egitim (research/pa_proposer_build.py) bu dosyayi okur.
KILIT (2026-05-01..2026-11-01, trader_ml.pa_proposer.train.in_lock): karar ile sonuc arasindaki aralik kilide kesisiyorsa
satir DUSURULUR; sonucu (outcome_ts) ya da karar zamani bilinmeyen satir da dusurulur (dogrulanamaz = kilitli sayilir).
Cikis: 0 basarili; 1 kullanim; 3 defter/okuma hatasi.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import ledger as L  # noqa: E402
from trader_ml.pa_proposer.train import in_lock  # noqa: E402  (kilit penceresi tek kaynak)


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def _utc(s: str | None) -> datetime | None:
    if not s:
        return None
    t = datetime.fromisoformat(s)
    return t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)


def drop_locked_rows(rows: list[dict]) -> tuple[list[dict], int]:
    """Kilit penceresiyle kesisen ya da dogrulanamayan (karar/sonuc zamani yok) satirlari dusurur -> (kalan, dusen)."""
    kept, dropped = [], 0
    for r in rows:
        ts, end = _utc(r["bar_close_ts"]), _utc(r["outcome_ts"])
        if ts is None or end is None or in_lock(ts, end):
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


def export(led, cf_path=None, *, bot: str = "learner") -> tuple[list[dict], int]:
    from trader_core import counterfactual as CF
    trades = led.list_closed_trades(limit=led.LIST_CLOSED_MAX)
    trade_of = {t.decision_id: t for t in trades}
    out: dict[int, dict] = {}
    for t in trades:
        if t.r_multiple is not None:
            out[t.decision_id] = {"r": float(t.r_multiple), "outcome_ts": t.exit_ts, "source": "trade", "taken": True}
    if cf_path is not None:
        try:
            with CF.CounterfactualStore(cf_path, read_only=True) as st:
                for r in st._db.execute("SELECT decision_id, hyp_r_net, window_end_ts FROM cf_outcomes WHERE bot=? AND method='barrier' "
                                        "AND hyp_r_net IS NOT NULL", (bot,)):
                    did = int(r["decision_id"])
                    if did not in out:
                        out[did] = {"r": float(r["hyp_r_net"]), "outcome_ts": L._parse_ts(r["window_end_ts"]), "source": "cf",
                                    "taken": False}
        except CF.CounterfactualError:
            pass
    rows = []
    for d in led.list_decisions():
        o = out.get(d.id)
        if o is None or not d.arm_id:
            continue
        rows.append({"decision_id": d.id, "arm_id": d.arm_id, "pair": d.pair, "side": d.side,
                     "bar_close_ts": d.bar_close_ts.isoformat() if d.bar_close_ts else None,
                     "outcome_ts": o["outcome_ts"].isoformat() if o["outcome_ts"] else None,
                     "r": o["r"], "taken": o["taken"], "source": o["source"]})
    return drop_locked_rows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="export_paper_records.py")
    ap.add_argument("--ledger", default="var/learner/ledger.sqlite")
    ap.add_argument("--cf")
    ap.add_argument("--out", required=True, help="JSON satirlari (jsonl) yazilacak dosya")
    ap.add_argument("--arm-prefix", default="", help="yalniz bu onekle baslayan arm_id (ornek: M1@)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    lp = _resolve(args.ledger)
    cf = _resolve(args.cf) if args.cf else str(Path(lp).with_name("counterfactual.sqlite"))
    try:
        led = L.open_ledger(lp, "learner", create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        print(f"defter acilamadi: {type(e).__name__}", file=sys.stderr)
        return 3
    try:
        rows, lock_dropped = export(led, cf if os.path.exists(cf) else None)
    except Exception as e:  # noqa: BLE001
        print(f"disa aktarma hatasi: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    finally:
        led.close()
    if args.arm_prefix:
        rows = [r for r in rows if r["arm_id"].startswith(args.arm_prefix)]
    outp = Path(_resolve(args.out))
    outp.parent.mkdir(parents=True, exist_ok=True)
    tmp = outp.with_name(outp.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, allow_nan=False) + "\n")
    os.replace(tmp, outp)
    print(json.dumps({"status": "ok", "rows": len(rows), "lock_dropped": lock_dropped, "out": str(outp)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
