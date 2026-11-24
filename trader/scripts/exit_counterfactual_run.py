#!/usr/bin/env python3
"""Gece isi: cikis karsi-olgusu (docs/cikis-karsi-olgu-spec.md; plan 25c). systemd timer `--once` calistirir.

KAPANMIS T1 islemlerinin giris sonrasi fiyat yolunu aktif `trail_atr` +/- adim ile yeniden oynatir; sonuc yalniz KANITTIR (ders
menusune bilgi; hicbir sey bloklamaz). Defteri (var/<bot>/ledger.sqlite) ve var/market.sqlite'i yalnizca SALT OKUNUR acar; yalnizca
var/<bot>/exit_counterfactual.sqlite'e yazar. Kilitli donem (trader_engine.holdout.HOLDOUT) bu betikte ice aktarilir ve saf
islevlere enjekte edilir; penceresi kilitli donemle kesisen islem hic okunmaz.
`--runs LISTE` (YALNIZ gelistirme makinesi): sabit backtest kosusu (1h_IS_f1_s0_native_last), `var/history` feather (pyarrow);
yalniz bilgi + parite testi, hukme girmez. Gece birimi `--runs` vermez.
Cikis kodlari: 0 basarili (defter yoksa da); 1 kullanim / `--registry-id` kayitsiz (`unregistered`); 3 bozulmus calisma
(market/defter/depo okunamadi) => systemd OnFailure.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import exit_counterfactual as EC  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_engine.holdout import HOLDOUT as _HOLDOUT, KILIT_ACIK, BacktestArgError, check_holdout  # noqa: E402

HOLDOUT = None if KILIT_ACIK else _HOLDOUT        # 23.11.2026 kullanici karari: kilit acik -> pencere yok (EC varsayilani de bos)

EXIT_OK, EXIT_CONFIG, EXIT_DEGRADED = 0, 1, 3
log = logging.getLogger("trader.exit_cf.run")
PARITY_DAYS = 120                      # lesson.LessonConfig.exit_cf_days varsayilani
BACKTEST_PARITY_DAYS = 3650


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def _parse_since(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit("--since: ISO zaman (UTC) bekleniyor, ornek 2026-12-01 ya da 2026-12-01T00:00:00Z") from None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def _paper_cfg(base_path: str, paper_path: str):
    """config/engine.base.json + engine.paper.json: (maliyet sozlugu, cost_overrides, varlik sinifi fonksiyonu). Okunamazsa tabanla."""
    from trader_core import arm_time as AT
    cost = {"taker_fee": 0.0005, "slip_exit_bps": 2.0, "slip_stop_bps": 5.0, "trigger_source": "mark"}
    over: dict = {}
    clusters: dict = {}
    for p in (base_path, paper_path):
        try:
            raw = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("yapilandirma okunamadi (%s); taban maliyet varsayilir", p)
            continue
        cost.update({k: v for k, v in (raw.get("cost") or {}).items() if k in cost})
        over.update(raw.get("cost_overrides") or {})
        clusters.update(raw.get("clusters") or {})
    cl = {k: SimpleNamespace(pairs=tuple(v.get("pairs", ()))) for k, v in clusters.items()}
    try:
        from trader_engine import arm_guard as AG
        cls_of = lambda pair: AG.asset_class(pair, cl)       # noqa: E731
    except Exception:                                         # noqa: BLE001
        cls_of = lambda pair: AT.CLASS_CRYPTO                # noqa: E731

    def cost_for(tr):
        row = ((over.get(tr.pair) or {}).get(AT.session_tag(cls_of(tr.pair), tr.entry_ts)))
        c = {"taker_fee": float(cost["taker_fee"]), "slip_exit_bps": float(cost["slip_exit_bps"]),
             "slip_stop_bps": float(cost["slip_stop_bps"])}
        if row:
            c["slip_exit_bps"] = float(row.get("slip_exit_bps", c["slip_exit_bps"]))
            c["slip_stop_bps"] = float(row.get("slip_stop_bps", c["slip_stop_bps"]))
        return c
    return cost_for, str(cost["trigger_source"])


class _Versions:
    """param_version_id -> (trail_atr, SignalParams | None) onbellegi (salt okunur defter)."""

    def __init__(self, led):
        self.led = led
        self._c: dict[int, tuple] = {}
        self._modes: dict[int, object] = {}            # param_version_id -> ExitModes | None (surumun acik cikis kipleri)

    def modes(self, vid: int):
        self.get(vid)
        return self._modes.get(vid)

    def get(self, vid: int):
        if vid not in self._c:
            try:
                params = dict(self.led.get_version(int(vid)).params)
            except Exception:                                  # noqa: BLE001
                self._c[vid] = (None, None)
                return self._c[vid]
            tv = params.get(EC.PARAM)
            self._modes[vid] = EC.XM.from_flags(int(params.get(EC.XM.PARAM_BREAKEVEN, 0) or 0) == 1,
                                                 int(params.get(EC.XM.PARAM_PARTIAL, 0) or 0) == 1)
            sp = None
            try:
                from trader_core import signals as S
                sp = S.SignalParams.from_mapping({k: params[k] for k in L.PARAM_KEYS if k in params})
            except Exception:                                  # noqa: BLE001
                sp = None
            self._c[vid] = (float(tv) if isinstance(tv, (int, float)) and not isinstance(tv, bool) else None, sp)
        return self._c[vid]


def _to_inputs(trades, vers: _Versions, source: str, run_id: str = "") -> list:
    out = []
    for t in trades:
        out.append(EC.TradeInput(
            trade_id=t.trade_id, pair=t.pair, side=t.side, setup=t.setup, trigger_tf=_tf_of(t), entry_ts=t.entry_ts,
            exit_ts=t.exit_ts, entry_price=t.entry_price, qty=t.qty, planned_risk=t.planned_risk, initial_stop=t.planned_stop,
            fee_entry=t.fee_entry, exit_reason=t.exit_reason, exit_price=t.exit_price, actual_net_r=t.r_multiple,
            param_version_id=t.param_version_id, own_value=vers.get(t.param_version_id)[0], source=source, run_id=run_id,
            own_modes=vers.modes(t.param_version_id)))
    return out


_TF_CACHE: dict = {}


def _tf_of(t) -> str:
    """Islemin tetik zaman dilimi: karar kaydindan (decision_id); bulunamazsa 'unknown' (1h degil => kanita girmez)."""
    return _TF_CACHE.get(t.decision_id, "unknown")


def _load_tf(led, trades) -> None:
    for d in led.list_decisions(final_action="entered"):
        _TF_CACHE[d.id] = d.trigger_tf


def _lot_rules(market):
    """Motorun kismi adet yuvarlamasi icin (adim, min adet, min notional): market.sqlite `rules` tablosundan; yoksa None (tam oran)."""
    def fn(pair):
        raw = market.rules_json(pair)
        if raw is None:
            return None
        try:
            from trader_engine.exchange.rules import spec_from_json, to_symbol_rules
            r = to_symbol_rules(pair, spec_from_json(raw))
            return float(r.step), float(r.min_qty), float(r.min_notional)
        except Exception:                                    # noqa: BLE001
            return None
    return fn


def _target_mode(base_path: str, paper_path: str) -> str:
    """Kagit motorunun `target_mode` degeri (taban + kagit katmani; okunamazsa 'bar_close'). 24.11: 'resting' ise cikis kipleri
    karsi-olgusu motorla ayni 15 dk adiminda oynatilir."""
    mode = "bar_close"
    for p in (base_path, paper_path):
        try:
            mode = json.loads(Path(p).read_text(encoding="utf-8")).get("target_mode", mode)
        except (OSError, ValueError):
            continue
    return mode


def _paper_block(args, now, store, source, since, modes_registered=True):
    led = L.open_ledger(_resolve(args.ledger or f"var/{args.bot}/ledger.sqlite"), args.bot, create=False, read_only=True,
                        migrate=False)
    try:
        trades = led.list_closed_trades(since=None, limit=L.Ledger.LIST_CLOSED_MAX)
        if since is not None:
            trades = [t for t in trades if t.exit_ts and t.exit_ts >= since]
        _load_tf(led, trades)
        act = led.get_active_params()
        active = float(act.params[EC.PARAM])
        bounds = tuple(float(x) for x in act.lesson_bounds[EC.PARAM])
        vers = _Versions(led)
        inputs = _to_inputs(trades, vers, source)
    finally:
        led.close()
    cost_for, trig = _paper_cfg(_resolve(args.base_config), _resolve(args.paper_config))
    market = EC.MarketSource(_resolve(args.market), holdout=HOLDOUT)
    try:
        r = EC.run_once(bot=args.bot, trades=inputs, market=market, store=store, now=now, active_value=active,
                        step=float(L.LESSON_STEP[EC.PARAM]), bounds=bounds, cost_for=cost_for,
                        signal_params_for=lambda t: vers.get(t.param_version_id)[1], trigger_source=trig,
                        holdout=HOLDOUT, dry_run=args.dry_run)
        # exitcf-v2: cikis kipleri (basa-bas / kismi) "acik olsaydi"; v1 sonucundan bagimsiz, ayni gece
        mr = EC.ModesRunResult() if not modes_registered else EC.run_modes_once(bot=args.bot, trades=inputs, market=market, store=store, now=now, active_value=active,
                               cost_for=cost_for, signal_params_for=lambda t: vers.get(t.param_version_id)[1],
                               trigger_source=trig, holdout=HOLDOUT, dry_run=args.dry_run, rules_for=_lot_rules(market),
                               step_15m=_target_mode(_resolve(args.base_config), _resolve(args.paper_config)) == "resting")
        return r, mr
    finally:
        market.close()


def _backtest_block(args, now, store, runs):
    """YALNIZ gelistirme makinesi: sabit backtest kosusu (yalniz bilgi + parite). Kilitli donemle kesisen kosu atlanir."""
    total = EC.RunResult()
    skipped = 0
    for run in runs:
        if run not in EC.BACKTEST_RUNS_ALLOWED:
            raise SystemExit(f"--runs: izinli liste disi kosu: {run} (izinli: {', '.join(EC.BACKTEST_RUNS_ALLOWED)})")
        d = Path(_resolve(args.backtests_dir)) / run
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        try:
            s, e = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in meta["period"])
            check_holdout(s, e)
        except BacktestArgError:
            skipped += 1
            continue
        # Eski semali kosu defteri (sema < guncel): ASLA yerinde gocmez; gecici kopyada gocurulur, kosu dizini degismez.
        tmpdir = tempfile.mkdtemp(prefix="exitcf_bt_")
        led = L.open_migrated_copy(d / "ledger.sqlite", Path(tmpdir) / "ledger.sqlite", "learner")
        try:
            trades = led.list_closed_trades(limit=L.Ledger.LIST_CLOSED_MAX)
            _load_tf(led, trades)
            act = led.get_active_params()
            vers = _Versions(led)
            inputs = _to_inputs(trades, vers, "backtest", run)
            active = float(act.params[EC.PARAM])
            bounds = tuple(float(x) for x in act.lesson_bounds[EC.PARAM])
        finally:
            led.close()
            shutil.rmtree(tmpdir, ignore_errors=True)
        c = meta.get("cost") or {}
        cost = {"taker_fee": float(c.get("taker_fee", 0.0005)), "slip_exit_bps": float(c.get("slip_exit_bps", 2.0)),
                "slip_stop_bps": float(c.get("slip_stop_bps", 5.0))}
        src = EC.FeatherSource(_resolve(args.history_dir), holdout=HOLDOUT)
        r = EC.run_once(bot="learner", trades=inputs, market=src, store=store, now=now, active_value=active,
                        step=float(L.LESSON_STEP[EC.PARAM]), bounds=bounds, cost_for=lambda t, cost=cost: cost,
                        signal_params_for=lambda t: vers.get(t.param_version_id)[1],
                        trigger_source=str(c.get("trigger_source", "last")), holdout=HOLDOUT, dry_run=args.dry_run)
        for k, v in vars(r).items():
            setattr(total, k, getattr(total, k) + v)
    return total, skipped


def main(argv=None, *, now_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bot", required=True, choices=("learner",))
    ap.add_argument("--once", action="store_true", help="tek tur (tek kullanim modu)")
    ap.add_argument("--registry-id", default=EC.REGISTRY_ID, help="on kayit kimligi; sabite esit olmali")
    ap.add_argument("--since", help="yalniz bu zamandan (UTC, ISO) sonra kapanan islemler")
    ap.add_argument("--runs", help="YALNIZ gelistirme: virgullu backtest kosu listesi (izinli: 1h_IS_f1_s0_native_last)")
    ap.add_argument("--dry-run", action="store_true", help="hesapla, yazma")
    ap.add_argument("--source", default="paper", choices=("paper", "testnet"))
    ap.add_argument("--ledger", help="varsayilan var/<bot>/ledger.sqlite")
    ap.add_argument("--market", default="var/market.sqlite")
    ap.add_argument("--out", help="varsayilan var/<bot>/exit_counterfactual.sqlite")
    ap.add_argument("--base-config", default="config/engine.base.json")
    ap.add_argument("--paper-config", default="config/engine.paper.json")
    ap.add_argument("--history-dir", default="var/history")
    ap.add_argument("--backtests-dir", default="var/backtests")
    ap.add_argument("--registry-csv", default="research/trial_registry.csv")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", stream=sys.stderr)
    if not args.once:
        print("yalniz --once desteklenir", file=sys.stderr)
        return EXIT_CONFIG
    if args.registry_id != EC.REGISTRY_ID:
        print(json.dumps({"bot": args.bot, "status": "unregistered", "registry_id": args.registry_id}))
        return EXIT_CONFIG
    csv_path = _resolve(args.registry_csv)
    if os.path.exists(csv_path):                                 # gelistirme makinesi: sunucuda research/ yoktur
        ok, why = EC.registry_check(csv_path)
        if not ok:
            log.error("on kayit denetimi: %s", why)
            print(json.dumps({"bot": args.bot, "status": "unregistered", "registry_id": EC.REGISTRY_ID, "detail": why}))
            return EXIT_CONFIG
    modes_registered = True                                      # exitcf-v2 (cikis kipleri): CSV varsa satir yoksa yalniz kip gecisi calismaz
    if os.path.exists(csv_path):
        modes_registered = EC.registry_check(csv_path, EC.MODES_REGISTRY_ID)[0]
        if not modes_registered:
            log.warning("exitcf-v2 on kayit satiri yok: cikis kipleri gecisi atlandi (v1 etkilenmez)")
    since = _parse_since(args.since)
    runs = [r.strip() for r in (args.runs or "").split(",") if r.strip()]
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    ledger_path = _resolve(args.ledger or f"var/{args.bot}/ledger.sqlite")
    out_path = _resolve(args.out or f"var/{args.bot}/exit_counterfactual.sqlite")
    if not os.path.exists(ledger_path) and not runs:
        log.info("defter yok; yapilacak is yok")
        print(json.dumps({"bot": args.bot, "status": "no_ledger"}))
        return EXIT_OK
    try:
        if args.dry_run:
            store = EC.ExitCfStore(out_path, read_only=True) if os.path.exists(out_path) else EC.ExitCfStore(":memory:")
        else:
            store = EC.ExitCfStore(out_path)
        try:
            r, mr = _paper_block(args, now, store, args.source, since, modes_registered) if os.path.exists(ledger_path) else (EC.RunResult(), EC.ModesRunResult())
            bt_skipped = 0
            if runs:
                bt, bt_skipped = _backtest_block(args, now, store, runs)
                for k, v in vars(bt).items():
                    setattr(r, k, getattr(r, k) + v)
        finally:
            store.close()
        par = bt_par = None
        if os.path.exists(out_path):
            try:
                par = EC.parity_stats(out_path, args.bot, now=now, days=PARITY_DAYS)
                bt_par = EC.parity_stats(out_path, args.bot, now=now, days=BACKTEST_PARITY_DAYS, sources=("backtest",)) if runs else None
            except EC.ExitCfError:
                par = None
    except (EC.ExitCfError, L.LedgerError, OSError) as e:
        log.error("bozulmus calisma: %s", getattr(e, "code", type(e).__name__))
        print(json.dumps({"bot": args.bot, "status": "degraded", "code": getattr(e, "code", type(e).__name__)}))
        return EXIT_DEGRADED
    out = {"bot": args.bot, "status": "ok", "dry_run": args.dry_run, "registry_id": EC.REGISTRY_ID, "version": EC.VERSION, **vars(r),
           "base_parity_median_abs_r": par["median_abs_r"] if par else None, "parity_mean_r": par["mean_r"] if par else None,
           "reason_match_rate": par["reason_match_rate"] if par else None, "parity_n": par["n"] if par else 0,
           "parity_status": par["status"] if par else "parity_unknown",
           "modes": {"registry_id": EC.MODES_REGISTRY_ID, "version": EC.modes_version_for(_target_mode(_resolve(args.base_config), _resolve(args.paper_config))),
                     "status": "ok" if modes_registered else "unregistered", **vars(mr)}}
    if runs:
        out["backtest_runs_skipped_holdout"] = bt_skipped
        out["backtest_parity"] = bt_par
    print(json.dumps(out, default=str))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
