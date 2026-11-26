#!/usr/bin/env python3
"""Telegram calistiricisi (docs/telegram-spec.md): `daemon` | `send` | `report`.

Cikis: 0 basarili (spool'a dusme dahil); 1 yapilandirma/kullanim hatasi. Token hicbir yere yazilmaz.
Test icin `main(argv, env=, http_post=, now_fn=, sleep=, stop=)` enjekte edilebilir.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from trader_core import live_paths as LP  # noqa: E402
from trader_core import proc_guard  # noqa: E402
from trader_core import risk_ladder as RL  # noqa: E402
from trader_core import telegram as T  # noqa: E402
from trader_core import tg_sade as TS  # noqa: E402
from trader_engine.killswitch import Killswitch  # noqa: E402
from trader_engine.pause import EntryPause  # noqa: E402


class _Clk:
    def __init__(self, fn):
        self._fn = fn

    def now(self):
        return self._fn()

EXIT_OK, EXIT_CONFIG = 0, 1


def _abs(root: Path, p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else root / q)


def build_pauses(env, now_fn, root: Path | None = None) -> dict:
    """bot -> EntryPause (11 §9.5). Yollar MUTLAK (cwd'ye bagli degil; systemd cwd=/ olabilir): goreli degerler repo
    kokune (trader/) gore cozulur, motor (WorkingDirectory=/opt/trader) ile ayni dosya. PAUSE_FILE (varsayilan
    shared/PAUSE) + `.<bot>`; PAUSE_BOTS (varsayilan learner); denetim ENGINE_VAR_DIR/<bot>/pause_audit.jsonl."""
    root = root or _HERE.parent
    base = _abs(root, env.get("PAUSE_FILE") or "shared/PAUSE")
    var = _abs(root, (env.get("ENGINE_VAR_DIR") or "var")).rstrip("/")
    bots = [b.strip() for b in (env.get("PAUSE_BOTS") or "learner").split(",") if b.strip()]
    clk = _Clk(now_fn)
    out = {}
    for b in bots:                      # DD-9 §6.2: canli bot LIVE_VAR_DIR / LIVE_PAUSE_FILE; kagit bot tabaninda (LIVE_BOTS bos -> ayni)
        bvar = LP.bot_var_dir(env, b, var).rstrip("/")
        bbase = LP.bot_pause_base(env, b, base)
        out[b] = EntryPause(f"{bbase}.{b}", clk, audit_path=f"{bvar}/{b}/pause_audit.jsonl", bot=b)
    return out


def _mode_risk(root: Path, env, bot: str) -> float | None:
    """Botun kipinin ayar dosyasindaki islem basi risk (canli bot: engine.live.json, digeri: engine.paper.json)."""
    import json
    mode = "live" if bot in LP.live_bots(env) else "paper"
    try:
        d = json.loads((root / "config" / f"engine.{mode}.json").read_text(encoding="utf-8"))
        r = (d.get("risk") or {}).get("target_trade_risk", d.get("target_trade_risk"))
        return float(r) if r is not None and float(r) > 0 else None
    except Exception:  # noqa: BLE001
        return None


def build_ladders(env, now_fn, root: Path | None = None) -> dict:
    """bot -> T.LadderFiles (12 §9). `LADDER_BOTS` (virgullu; varsayilan BOS: kademe komutlari kapali; canliya gecista
    canli bot yazilir). Yollar `build_pauses` ile ayni cozumle MUTLAK: kademe gunlugu ENGINE_VAR_DIR/<bot>/risk_ladder.jsonl,
    motor durumu ENGINE_VAR_DIR/<bot>/status.json, tutus PAUSE_FILE.<bot>."""
    root = root or _HERE.parent
    base = _abs(root, env.get("PAUSE_FILE") or "shared/PAUSE")
    var = _abs(root, (env.get("ENGINE_VAR_DIR") or "var")).rstrip("/")
    bots = [b.strip() for b in (env.get("LADDER_BOTS") or "").split(",") if b.strip()]
    clk = _Clk(now_fn)
    out = {}
    for b in bots:
        bvar = LP.bot_var_dir(env, b, var).rstrip("/")
        bbase = LP.bot_pause_base(env, b, base)
        out[b] = T.LadderFiles(log=RL.LadderLog(f"{bvar}/{b}/risk_ladder.jsonl"), status_path=f"{bvar}/{b}/status.json",
                               pause=EntryPause(f"{bbase}.{b}", clk, audit_path=f"{bvar}/{b}/pause_audit.jsonl", bot=b),
                               risk=_mode_risk(root, env, b))
    return out


def main(argv=None, *, env=None, http_post=None, now_fn=None, sleep=time.sleep, stop=None) -> int:
    ap = argparse.ArgumentParser(prog="telegram_run.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daemon")
    sp = sub.add_parser("send")
    sp.add_argument("--severity", choices=T.SEVERITIES, default="INFO")
    sp.add_argument("--dedup-key", required=True)
    sp.add_argument("text")
    sub.add_parser("report")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return EXIT_CONFIG if e.code else EXIT_OK
    env = os.environ if env is None else env
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("urllib3").setLevel(logging.INFO)    # DEBUG istek satirlari (sorgu dizgisi) yazilmasin
    if not proc_guard.set_nondumpable():                   # DD-9 §4.3: ortam (token) ayni kimlikli sureclerce okunamasin
        logging.getLogger("telegram_run").warning("proc_guard: surec dokulemez yapilamadi; devam")
    cfg = T.TelegramConfig.from_env(env)
    if cfg is None:
        print("telegram yapilandirilmamis (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)", file=sys.stderr)
        return EXIT_CONFIG
    if args.cmd in ("daemon", "report"):
        cdir = (env.get("ENGINE_CONFIG_DIR") or "").strip() or str(_HERE.parent / "config")
        issues = LP.check_against_config(env, cdir)         # DD-9 §6.2: yanlis dosyaya KILL/duraklatma yazan daemon calismaz
        if issues:
            print("telegram_run: canli yol tutarsizligi: " + ", ".join(issues), file=sys.stderr)
            return EXIT_CONFIG
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    client = T.TelegramClient(cfg.token, http_post, sleep)
    try:
        if args.cmd == "send":
            n = T.TelegramNotifier(client, cfg.chat_id, T.Outbox(cfg.var_dir, now_fn), now_fn, sleep)
            text = args.text
            if text.startswith("Birim basarisiz: "):        # systemd OnFailure: birim adi kullaniciya gitmez
                n.status_path = cfg.status_path or None
                birim = text.split(": ", 1)[1]
                text = TS.birim_metni(birim, n.status_path)
                if text is not None and "engine" in birim:
                    n.kayit.isaretle("bot")
                if text is None:
                    print("skipped")
                    return EXIT_OK
            ok = n.send_text(text, args.severity, args.dedup_key)
            print("sent" if ok else "spooled")
            return EXIT_OK
        if args.cmd == "report":
            n = T.TelegramNotifier(client, cfg.chat_id, T.Outbox(cfg.var_dir, now_fn), now_fn, sleep)
            print(T.run_report(cfg, n, now_fn(), pauses=build_pauses(env, now_fn), ladders=build_ladders(env, now_fn)))
            return EXIT_OK
        ks = Killswitch(cfg.kill_file, _Clk(now_fn)) if cfg.kill_file else None
        pauses = build_pauses(env, now_fn)
        ladders = build_ladders(env, now_fn)
        d = T.TelegramDaemon(cfg, client, now_fn=now_fn, sleep=sleep, killswitch=ks, pauses=pauses,
                             ladders=ladders, expect_status_mode="live" if LP.live_bots(env) else None,
                             report_fn=lambda: T.build_report(cfg, now_fn(), now_fn().astimezone(T.TR).date().isoformat(),
                                                       T.default_sections(cfg, now_fn(), now_fn().astimezone(T.TR).date().isoformat(), pauses,
                                                                          ladders)))
        flag = {"stop": False}
        signal.signal(signal.SIGTERM, lambda *_: flag.update(stop=True))
        d.run_forever(stop or (lambda: flag["stop"]))
        return EXIT_OK
    except Exception as e:  # noqa: BLE001  token sizmasin
        print(f"telegram_run: hata: {T.mask(type(e).__name__, cfg.token)}", file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
