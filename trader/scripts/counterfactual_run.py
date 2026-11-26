#!/usr/bin/env python3
"""Gece isi: alinmayan sinyallerin varsayimsal sonucu (docs/alinmayan-sinyal-spec.md) + kurulum karnesi ve kurulum dersi
(DD-12 WP-13). systemd timer `--once` calistirir.

Defteri (var/<bot>/ledger.sqlite) ve var/market.sqlite'i yalnizca SALT OKUNUR acar; yalnizca var/<bot>/counterfactual.sqlite
ve var/<bot>/arms_off.json'a yazar. Kurulum zaman dilimleri 15dk/1s/4s/1g; kayma seansa gore (config/engine.paper.json
`cost_overrides`). Kurulum dersi: sonumlu ortalama <= -0,15 R -> kurulum kapanir; >= +0,05 R -> acilir; tek degisikligin
etkisi <= -3 R -> geri alinir (kol_yasam.arm_lifecycle_step). Motor, kapali kurulumu `arm_disabled` ile atlar (gates.py).
Cikis kodlari: 0 basarili (hesaplanacak karar yoklugu ve defter yoklugu dahil); 1 kullanim/yapilandirma hatasi;
3 bozulmus calisma (market/defter/depo okunamadi ya da yazilamadi): systemd icin BASARISIZ => OnFailure.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import alinmayan_sonuc as AS  # noqa: E402
from trader_core import counterfactual as CF  # noqa: E402
from trader_core import ledger as L  # noqa: E402
from trader_core import kol_yasam as KY  # noqa: E402
from trader_engine import arm_guard as AG  # noqa: E402

EXIT_OK, EXIT_CONFIG, EXIT_DEGRADED = 0, 1, 3
log = logging.getLogger("trader.counterfactual.run")


def _resolve(p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else _HERE.parent / q)


def _parse_since(s: str | None):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit("--since: ISO zaman (UTC) bekleniyor, ornek 2026-12-01 ya da 2026-12-01T00:00:00Z") from None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def _paper_maps(path: str):
    """config/engine.paper.json'dan: (cost_overrides, varlik sinifi fonksiyonu, kurulum listesi). Okunamazsa tabanla devam."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("paper yapilandirmasi okunamadi (%s); taban kayma ve kripto varsayilir", path)
        return {}, (lambda pair: AG.CLASS_CRYPTO), []
    clusters = {k: SimpleNamespace(pairs=tuple(v.get("pairs", ()))) for k, v in (raw.get("clusters") or {}).items()}
    arms_raw = raw.get("arms") or []
    if isinstance(arms_raw, dict):
        arms = [f"{k}@{tf}" for k, tfs in arms_raw.items() for tf in tfs]
    else:
        arms = [str(a) for a in arms_raw]
    return dict(raw.get("cost_overrides") or {}), (lambda pair: AG.asset_class(pair, clusters)), arms


def _read_v3_skipped(path: str, bot: str, since) -> list:
    """Sema 3 dosya (goc henuz olmadi): `v_decisions` salt okunur ham SQL ile okunur. Baska surum ya da bozuk dosya
    `LedgerSchemaError` olarak yukselir (bozulmus calisma)."""
    import sqlite3
    from urllib.parse import quote
    try:
        c = sqlite3.connect("file:" + quote(os.path.abspath(path)) + "?mode=ro", uri=True, timeout=5.0)
        c.row_factory = sqlite3.Row
        try:
            if c.execute("PRAGMA user_version").fetchone()[0] != 3:
                raise L.LedgerSchemaError("sema surumu 3 degil")
            sql = "SELECT * FROM v_decisions WHERE bot=? AND final_action='skipped'"
            args: list = [bot]
            if since is not None:
                sql += " AND bar_close_ts>=?"
                args.append(L._fmt_ts(since))
            sql += " ORDER BY bar_close_ts, id"
            return [L.Ledger._decision_from(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()
    except sqlite3.Error as e:
        raise L.LedgerSchemaError(f"sema 3 defter okunamadi: {e}") from e


def _aile_ort(cands: list, arm: str, shrink_n: int) -> float | None:
    """24.11: kolun ailesi (ayni formasyon, kolun kendisi HARIC diger ZD'ler) cozulmus adaylarinin sonumlu ortalamasi:
    `toplam R / (n_aile + shrink_n)`; alinmayan aday 0,5 agirlikli. Aile verisi yoksa None (bugunku davranis)."""
    fam = arm.partition("@")[0]
    tot = n = 0.0
    for c in cands:
        if c["arm_id"] != arm and c["arm_id"].partition("@")[0] == fam and c["r"] is not None:
            w = 1.0 if c["taken"] else KY.ARM_CF_AGIRLIK
            tot += w * c["r"]
            n += w
    return KY.damped_mean(tot, n, shrink_n) if n > 0 else None


def _arm_lesson(led, cf_path: str, bot: str, state_path: str, arms: list, asset_of, now: datetime, dry_run: bool) -> dict:
    """WP-13: kurulum karnesi (tum adaylar) + kurulum dersi (ac/kapa, geri alma). Yazma yalnizca gercek kosuda."""
    decisions = led.list_decisions()                          # salt okunur; aday filtresi arm_candidates'ta
    trades = led.list_closed_trades(limit=10000)              # LIST_CLOSED_MAX ust sinirinda; asanlar cozulmemis sayilir
    cands = CF.arm_candidates(decisions=decisions, trades=trades, cf_rows=CF.arm_rows(cf_path, bot), asset_class_of=asset_of)
    prev = KY.read_arms_state(state_path)
    states, events = {}, []
    seen = dict.fromkeys([*arms, *(c["arm_id"] for c in cands)])
    for arm in seen:
        cs = [(c["ts"], c["r"], c["taken"]) for c in cands if c["arm_id"] == arm and c["r"] is not None]
        st, ev = KY.arm_lifecycle_step(prev.get(arm), cs, now, shrink_n=KY.SHRINK_N,
                                       rollback_r=KY.ROLLBACK_EFFECT_R, aile_ort=_aile_ort(cands, arm, KY.SHRINK_N),
                                       cf_weight=KY.ARM_CF_AGIRLIK)
        states[arm] = st
        if ev:
            events.append({"arm_id": arm, "event": ev})
            log.info("kurulum %s: %s", arm, ev)
    if not dry_run:
        KY.write_arms_state(state_path, states, now)
    closed = {a for a, s in states.items() if s["state"] == "closed"}
    return {"scorecard": CF.arm_scorecard(cands, arms=arms, closed=closed), "events": events,
            "closed": sorted(closed), "state_written": not dry_run}


def main(argv=None, *, now_fn=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bot", required=True, choices=("learner",))
    ap.add_argument("--once", action="store_true", help="tek tur (tek kullanim modu)")
    ap.add_argument("--since", help="yalniz bu zamandan (UTC, ISO) sonraki kararlar")
    ap.add_argument("--dry-run", action="store_true", help="hesapla, yazma")
    ap.add_argument("--ledger", help="varsayilan var/<bot>/ledger.sqlite")
    ap.add_argument("--market", default="var/market.sqlite")
    ap.add_argument("--out", help="varsayilan var/<bot>/counterfactual.sqlite")
    ap.add_argument("--paper-config", default="config/engine.paper.json", help="kayma (cost_overrides) ve kurulum listesi")
    ap.add_argument("--arms-state", help="varsayilan: defterin klasorunde arms_off.json (motor okur)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", stream=sys.stderr)
    if not args.once:
        print("yalniz --once desteklenir", file=sys.stderr)
        return EXIT_CONFIG
    since = _parse_since(args.since)
    now = (now_fn or (lambda: datetime.now(timezone.utc)))()
    ledger_path = _resolve(args.ledger or f"var/{args.bot}/ledger.sqlite")
    out_path = _resolve(args.out or f"var/{args.bot}/counterfactual.sqlite")
    arms_path = _resolve(args.arms_state) if args.arms_state else str(Path(ledger_path).parent / "arms_off.json")
    market_path = _resolve(args.market)
    cost_table, asset_of, arms = _paper_maps(_resolve(args.paper_config))
    if not os.path.exists(ledger_path):
        log.info("defter yok (%s kapali olabilir); yapilacak is yok", args.bot)
        print(json.dumps({"bot": args.bot, "status": "no_ledger"}))
        return EXIT_OK
    try:
        shadows: list = []
        lesson_block = None
        try:
            led = L.open_ledger(ledger_path, args.bot, create=False, read_only=True, migrate=False)
            try:
                decisions = led.list_decisions(since_ts=since, final_action="skipped")
                shadows = led.list_shadow(since_ts=since)           # WP-3 7: sema 4; ayri tablo, ayri sonuc
            finally:
                led.close()
        except L.LedgerSchemaError:
            decisions = _read_v3_skipped(ledger_path, args.bot, since)   # gecis donemi: sema 3 defter okunur, golge adimi atlanir
        if args.dry_run:                                    # dry-run: depoya yazilmaz (yoksa bos bellek deposu)
            store = CF.CounterfactualStore(out_path, read_only=True) if os.path.exists(out_path) \
                else CF.CounterfactualStore(":memory:")
        else:
            store = CF.CounterfactualStore(out_path)
        try:
            r = CF.run_once(bot=args.bot, decisions=decisions, market_path=market_path, store=store, now=now,
                            dry_run=args.dry_run, cost_table=cost_table, asset_class_of=asset_of)
            sr = CF.run_shadow(bot=args.bot, shadows=shadows, market_path=market_path, store=store, now=now,
                               dry_run=args.dry_run) if shadows else CF.ShadowRunResult()
        finally:
            store.close()
        if os.path.exists(ledger_path):                     # WP-13: karne + ders, bu turun karsi-olgusu yazildiktan sonra
            try:
                led = L.open_ledger(ledger_path, args.bot, create=False, read_only=True, migrate=False)
                try:
                    lesson_block = _arm_lesson(led, out_path, args.bot, arms_path, arms, asset_of, now, args.dry_run)
                finally:
                    led.close()
            except L.LedgerSchemaError:
                log.info("kurulum dersi atlandi: defter sema 5 degil")
    except (CF.CounterfactualError, L.LedgerError) as e:
        log.error("bozulmus calisma: %s", getattr(e, "code", type(e).__name__))
        print(json.dumps({"bot": args.bot, "status": "degraded", "code": getattr(e, "code", type(e).__name__)}))
        return EXIT_DEGRADED
    if not args.dry_run:                                    # alinmayan x sonuc raporu (yalniz bilgi; hata isi bozmaz; docs/alinmayan-sonuc-spec.md)
        AS.yaz_defterden(Path(ledger_path), Path(out_path), args.bot, now, Path(ledger_path).parent.parent / "durum" / AS.DOSYA)
    out = {"bot": args.bot, "status": "ok", "dry_run": args.dry_run, **vars(r), **vars(sr)}
    if lesson_block is not None:
        out["arms"] = lesson_block
    print(json.dumps(out, default=str))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
