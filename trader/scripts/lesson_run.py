#!/usr/bin/env python3
"""Gunluk ders servisi calistiricisi (docs/ders-spec.md Bolum 13.2). systemd timer saatte bir `--once` calistirir.

Cikis kodlari: 0 basarili (atlama/degisiklik yok/uygulama dahil); 1 yapilandirma/kullanim hatasi (bildirimci
yapilandirilmamis dahil); 2 calisma `failed` (beklenen; bildirim gider, systemd SuccessExitStatus=2); 3 BOZULMUS calisma
(ledger_only/magaza yok, yedek yazilamadi, saat kilidi, defter acilamadi): systemd icin BASARISIZ => OnFailure.
Bildirimci (Revizyon 3): `notifier=` enjekte edilir ya da `cfg.notifier` adi `lesson.NOTIFIER_FACTORIES`'ten kurulur;
yoksa cikis 1 (`--dry-run` ya da test bayragi `--allow-log-notifier` disinda). Log bildirimcisi teslim SAYILMAZ.
`--bot` secenegi yoktur (yalniz ogrenen). `--dry-run`: istatistik + menu + istem metni; API/butce/defter yazimi yok.
API anahtari yalnizca `LazyAnthropicClient` icinde okunur; log/cikti hicbir anahtar ya da istem icerigi yazmaz
(dry-run ciktisi disinda; dry-run da yalnizca sayi/numaralandirma icerir).
Test icin `main(..., client=, budget=, notifier=, now_fn=, env=, sleep_fn=)` enjekte edilebilir.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import lesson as LS  # noqa: E402
from trader_core import proc_guard  # noqa: E402
from trader_core import telegram as _TG  # noqa: E402,F401  (NOTIFIER_FACTORIES["telegram"] kaydi)

EXIT_OK, EXIT_CONFIG, EXIT_FAILED, EXIT_DEGRADED = LS.EXIT_OK, LS.EXIT_CONFIG, LS.EXIT_FAILED, LS.EXIT_DEGRADED
log = logging.getLogger("trader.lesson.run")


class _ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = LS.scrub(record.getMessage())
            record.args = None
        except Exception:  # noqa: BLE001
            pass
        return True


def _resolve(path: str) -> str:
    p = Path(path)
    return str(p if p.is_absolute() else _HERE.parent / p)


def _build_cfg(args, env):
    cfg = LS.load_config(args.config)
    over = {}
    if args.mode:
        over["mode"] = args.mode
    over["ledger_path"] = _resolve(env.get("LEDGER_PATH") or cfg.ledger_path)
    over["store_path"] = _resolve(env.get("LESSON_STORE_PATH") or cfg.store_path)
    return dataclasses.replace(cfg, **over)


def _resolve_request(args, cfg, clock, env, sleep_fn) -> int:
    """Telegram daemon'u ders defterini acmaz; onay bu alt surecle `lesson.lock` altinda cozulur (karar 3).
    Cikis: 0 cozuldu/bilinen durum; 1 kullanim; 2 hata/kilit alinamadi. Tek satir JSON yazar."""
    import re
    if args.approve == args.reject:
        print("--approve ya da --reject (yalniz biri) gerekli", file=sys.stderr)
        return EXIT_CONFIG
    if not re.fullmatch(r"lr-\d{4}-\d{2}-\d{2}-\d+", args.resolve):
        print("gecersiz request_id", file=sys.stderr)
        return EXIT_CONFIG
    lock = _resolve(os.path.join(os.path.dirname(cfg.store_path), "lesson.lock"))
    fl = LS.FileLock(lock)
    try:
        got = fl.acquire()
    except OSError:
        got = False
    if not got:
        print(json.dumps({"status": "error", "code": "lock_busy", "message": "lesson.lock alinamadi",
                          "request_id": args.resolve}))
        return EXIT_FAILED
    try:
        svc = LS.LessonService(cfg, notifier=LS.LogNotifier(), clock=clock, sleep_fn=sleep_fn)
        res = svc.resolve_request(args.resolve, bool(args.approve), "telegram")
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"status": "error", "code": "exception", "message": LS.scrub(type(e).__name__),
                          "request_id": args.resolve}))
        return EXIT_FAILED
    finally:
        fl.release()
    print(json.dumps({"status": res.status, "code": res.code, "message": LS.scrub(res.message),
                      "request_id": res.request_id}))
    return EXIT_OK


def main(argv=None, *, client=None, budget=None, notifier=None, now_fn=None, env=None, sleep_fn=None) -> int:
    if not proc_guard.set_nondumpable():                  # DD-9 §4.3: ortam (API anahtari) ayni kimlikli sureclerce okunamasin
        logging.getLogger("lesson_run").warning("proc_guard: surec dokulemez yapilamadi; devam")
    ap = argparse.ArgumentParser(prog="lesson_run.py", add_help=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--once", action="store_true")
    g.add_argument("--rollback-to-user-approved", action="store_true")
    g.add_argument("--resolve", metavar="REQUEST_ID", help="onay talebini coz (--approve|--reject); lesson.lock alir")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--reject", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--mode", choices=("llm", "rule_proxy", "both"))
    ap.add_argument("--day")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-log-notifier", action="store_true",
                    help="yalniz test/gecis: bildirimci yoksa log bildirimcisi (teslim sayilmaz)")
    ap.add_argument("--reason")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_CONFIG if e.code else EXIT_OK
    env = os.environ if env is None else env
    root = logging.getLogger()
    if not any(isinstance(f, _ScrubFilter) for f in root.filters):
        root.addFilter(_ScrubFilter())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = _build_cfg(args, env)
    except LS.LessonConfigError as e:
        print(f"yapilandirma hatasi: {LS.scrub(e)}", file=sys.stderr)
        return EXIT_CONFIG
    clock = now_fn or (lambda: datetime.now(timezone.utc))
    if args.day and not LS._valid_day(args.day):
        print("--day YYYY-MM-DD olmali", file=sys.stderr)
        return EXIT_CONFIG
    if args.day and not args.dry_run and args.day > LS._aware(clock()).date().isoformat():
        print("--day gelecekte olamaz (yalniz --dry-run serbest)", file=sys.stderr)
        return EXIT_CONFIG
    if cfg.dondurulmus and (args.once or args.resolve):    # 25.11: ders sistemi dondurulmus; servis/LLM/bildirimci/defter acilmaz
        log.info("ders sistemi dondurulmus: calisma atlandi")
        out = {"status": "dondurulmus", "code": "dondurulmus"}
        if args.resolve:
            out["request_id"] = args.resolve
        print(json.dumps(out))
        return EXIT_OK
    if args.resolve:
        return _resolve_request(args, cfg, clock, env, sleep_fn)
    if args.rollback_to_user_approved:
        if not args.reason or not args.reason.strip():
            print("--reason gerekli", file=sys.stderr)
            return EXIT_CONFIG
        svc = LS.LessonService(cfg, clock=clock)
        try:
            res = svc.rollback_to_user_approved(args.reason, "cli")
        except Exception as e:  # noqa: BLE001
            print(f"geri alma yapilamadi: {LS.scrub(e)}", file=sys.stderr)
            return EXIT_FAILED
        print(json.dumps({"ok": res.ok, "code": res.code, "version_id": res.version_id}))
        return EXIT_OK if (res.ok or res.code == "already_active") else EXIT_FAILED
    if notifier is None and not args.dry_run:
        notifier = LS.build_notifier(cfg, env)
        if notifier is None:
            if args.allow_log_notifier:
                notifier = LS.LogNotifier()
            else:
                print("bildirimci yapilandirilmamis (cfg.notifier / NOTIFIER_FACTORIES; Telegram madde 18): "
                      "oneriler kullaniciya ulasmaz; test icin --allow-log-notifier ya da --dry-run", file=sys.stderr)
                return EXIT_CONFIG
    llm = client
    if llm is None and cfg.mode in ("llm", "both") and not args.dry_run:
        llm = LS.LazyAnthropicClient(env=env, budget=budget)
    lock = _resolve(os.path.join(os.path.dirname(cfg.store_path), "lesson.lock"))
    svc = LS.LessonService(cfg, llm=llm, budget=budget, notifier=notifier, clock=clock, sleep_fn=sleep_fn,
                           lock_path=None if args.dry_run else lock)
    try:
        if args.dry_run:
            out = svc.dry_run(args.day)
            print(json.dumps(out, indent=1, sort_keys=True))
            return EXIT_OK
        now = None
        if args.day:
            hh, mm = cfg.run_at_utc.split(":")
            now = LS.as_of_for(args.day).replace(hour=int(hh), minute=int(mm))
        res = svc.run_tick(now)
    except LS.LessonError as e:
        print(f"hata: {LS.scrub(e)}", file=sys.stderr)
        return EXIT_CONFIG
    except Exception as e:  # noqa: BLE001  fail-safe
        log.error("beklenmeyen hata: %s", LS.scrub(e))
        return EXIT_FAILED
    print(json.dumps({"status": res.status, "run_day": res.run_day, "code": res.code}))
    return res.exit_code


if __name__ == "__main__":
    sys.exit(main())
