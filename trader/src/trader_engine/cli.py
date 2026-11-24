"""Komut satiri (05 §9). Ince sarmalayici: agir moduller alt komut icinde tembel import edilir."""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import signal
import sys
from pathlib import Path

EXIT_OK, EXIT_REPEATED, EXIT_FAZ_B, EXIT_ENGINE, EXIT_FINDINGS = 0, 3, 2, 4, 5
EXIT_PERMISSION = 8   # 11 §3.3: borsa yetki/izin/bolge reddi (RestartPreventExitStatus=7 8)

# 11 §3.4 acilis denetimi icin enjekte edilebilir kabuk: callable(cfg, api_key, api_secret) -> None;
# reddederse EngineExit(8, kod) firlatir. Gercek denetim LiveBroker.startup_check() (B3/B7) ile baglanir.
STARTUP_CHECKER = None


def _load_cfg(a):
    from .config import load_cli_config
    return load_cli_config(a.config_dir, getattr(a, "bot", None) or "learner", getattr(a, "env", None))   # DD-8 E1: kill/pause/var_dir cwd'den bagimsiz


def _live_startup(cfg, checker) -> int | None:
    """testnet/live on kosullari (11 §3.1-3.4). None => devam; aksi cikis kodu.
    Sira: anahtarlar (keys_missing, kod 2) -> acilis denetimi (ret: kod 8) -> broker yok (faz_b, kod 2).
    LIVE_CONFIRM burada denetlenir (yalniz kosu yolu; kill/pause/init-ledger/reconcile/backtest istemez).
    B3: startup_check icinde ExchangeBan/yetki -> kod 8, ulasilamaz -> kod 5 eslemesi yapilir (11 §3.4); burada
    yalniz EngineExit.code aynen iletilir."""
    import os

    from .config import check_live_confirm, load_keys
    from .engine import EngineExit
    from .errors import ConfigError
    try:
        check_live_confirm(cfg, os.environ)
        key, secret = load_keys(os.environ)
    except ConfigError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    checker = checker if checker is not None else STARTUP_CHECKER
    if checker is not None:
        try:
            checker(cfg, key, secret)
        except EngineExit as e:
            print(f"acilis denetimi reddetti: {e}", file=sys.stderr)
            return e.code
        print("faz_b: acilis denetimi enjekte edildi; motor kurulmadi", file=sys.stderr)
        return EXIT_FAZ_B
    return None


def _cmd_run(a, *, checker=None) -> int:
    from .engine import EngineExit, build_engine
    from .errors import ConfigError, EngineError
    from .strategies.registry import StrategyError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    logging.getLogger("engine.cli").warning("KILL dosyasi (mutlak yol): %s", cfg.kill_file)    # DD-2 D7
    logging.getLogger("engine.cli").warning("PAUSE dosyasi (mutlak yol): %s.%s", cfg.pause_file, cfg.bot)    # DD-8 E1
    if cfg.mode in ("testnet", "live"):
        from trader_core import proc_guard      # DD-9 §4.3: anahtar okunmadan once ortam okunamaz hale gelir (paper/backtest: cagrilmaz)
        if not proc_guard.set_nondumpable():
            if cfg.mode == "live":
                print(f"yapilandirma hatasi: {ConfigError('proc_guard_failed')}", file=sys.stderr)
                return EXIT_FAZ_B
            logging.getLogger("engine.cli").warning("proc_guard: surec dokulemez yapilamadi (testnet; devam)")
        rc = _live_startup(cfg, checker)       # anahtar + LIVE_CONFIRM (+ enjekte denetim); None => gercek kurulum
        if rc is not None:
            return rc
    if getattr(a, "ensure_ledger", False):     # DD-9 §2.1: ExecStartPre=init-ledger yerine ayni surecte (cikis 8 birimi dongüye sokmaz)
        rc = _ensure_ledger_step(cfg, getattr(a, "ledger_reason", "paper_start"))
        if rc != EXIT_OK:
            return rc
    try:
        eng = build_engine(cfg)
    except EngineExit as e:                    # 11 §3.3/§3.4: acilis denetimi reddi (8) / ulasilamaz (5)
        print(f"acilis denetimi reddetti: {e}", file=sys.stderr)
        return e.code
    except StrategyError as e:
        print(f"strateji hatasi: {e.code}: {e}", file=sys.stderr)
        return EXIT_ENGINE
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    except EngineError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_REPEATED
    _attach_symbol_watch(eng, cfg)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: eng.stop())
    try:
        eng.run_forever()
    except StrategyError as e:
        print(f"strateji hatasi: {e.code}: {e}", file=sys.stderr)
        return EXIT_ENGINE
    except EngineExit as e:
        return e.code
    except EngineError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_REPEATED
    return EXIT_OK


def _attach_symbol_watch(eng, cfg) -> None:
    """4f: saatlik sembol (TRADING) izleyicisi; herkese acik exchangeInfo, anahtarsiz. `TRADER_SEMBOL_IZLEME_KAPALI=1` kapatir.
    Yalniz kosu yolunda (testlerin build_engine'i ag acmaz). Kurulamazsa motor yine calisir (log)."""
    import os
    if cfg.mode not in ("paper", "testnet", "live") or os.environ.get("TRADER_SEMBOL_IZLEME_KAPALI") == "1":
        return
    try:
        from .marketdata.feed import _make_guarded_rest
        from .sembol_izleme import SembolIzleyici
        rest = _make_guarded_rest(eng.clock, cfg.market_db)
        eng.sembol_izleyici = SembolIzleyici(cfg.pairs, rest.exchange_info,
                                             contract_types=cfg.contract_types or ("PERPETUAL",),
                                             has_open_fn=lambda p: eng.state.position_for_pair(p) is not None,
                                             arka_plan=True)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("engine.cli").error("sembol izleyici kurulamadi: %r", e)


def _cmd_arm_quarantine(a) -> int:
    """4b: kurulum karantinasi. `list` status.json'dan okur; `release <kurulum|hepsi>` istek dosyasi yazar (motor dakikada
    bir isler; motor durukken bir sonraki acilista)."""
    import json

    from .arm_quarantine import request_release
    from .clock import SystemClock
    from .errors import ConfigError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    if a.action == "release":
        if not a.target:
            print("release icin kurulum (ya da 'hepsi') gerekli", file=sys.stderr)
            return EXIT_FAZ_B
        p = request_release(Path(cfg.path("x")).parent, a.target, "cli", SystemClock().now())
        print(f"karantina kaldirma istegi yazildi: {p}")
        return EXIT_OK
    try:
        doc = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        rows = (doc.get("dayaniklilik") or {}).get("karantina") or []
    except (OSError, ValueError):
        print("status.json okunamadi", file=sys.stderr)
        return EXIT_ENGINE
    for r in rows:
        print(f"{r.get('birim')}\t{r.get('durum')}\t{','.join(r.get('kollar') or [])}\t{r.get('hata')}")
    if not rows:
        print("karantinada kurulum yok")
    return EXIT_OK


def _cmd_init_ledger(a) -> int:
    from .errors import ConfigError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    return _init_ledger_work(cfg, a.reason, a.strategy)


def _ledger_user_version(path: str) -> int | None:
    """Salt okunur PRAGMA user_version; dosya yok/0 bayt -> None."""
    import sqlite3
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return None
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        return int(c.execute("PRAGMA user_version").fetchone()[0])
    finally:
        c.close()


def _ensure_ledger_step(cfg, reason: str) -> int:
    """`run --ensure-ledger` (DD-9 §2.1). testnet/live'de eski semali defter `init-ledger` isine (migrate=False -> cikis 4, birimi
    dongüye sokar) HIC girmez: once salt okunur damga bakilir. Yabanci damga / okunamayan dosya / damgasiz eski sema -> 8 (dosyaya
    dokunulmaz); damga == want ve eski sema -> init isi atlanir, goc build_engine'de (premigrate yedegiyle) yapilir."""
    if cfg.mode in ("testnet", "live"):
        from trader_core import ledger as L

        from .stamp import want_stamp
        try:
            lp = L.peek_meta(cfg.ledger_path, "account_stamp")
            uv = _ledger_user_version(cfg.ledger_path)
        except Exception as e:  # noqa: BLE001 - okunamayan defter: fail-closed, dosyaya dokunulmaz
            print(f"defter damgasi okunamadi: {type(e).__name__} (ledger_stamp_mismatch)", file=sys.stderr)
            return EXIT_PERMISSION
        old_schema = uv is not None and 0 < uv < L.SCHEMA_VERSION
        if lp is not None and lp != want_stamp(cfg):
            print("defter baska mod/hesap damgali: reddedildi (ledger_stamp_mismatch)", file=sys.stderr)
            return EXIT_PERMISSION
        if old_schema and lp is None:
            print("eski semali damgasiz defter: goc yapilmadi (ledger_stamp_missing)", file=sys.stderr)
            return EXIT_PERMISSION
        if old_schema:
            return EXIT_OK
    return _init_ledger_work(cfg, reason, None)


def _init_ledger_work(cfg, reason: str, strategy: str | None) -> int:
    """`init-ledger` alt komutunun isi (DD-9 §2.1: `run --ensure-ledger` ayni isi ayni surecte yapar)."""
    from trader_core import ledger as L
    from trader_core.signals import DEFAULT_SIGNAL_PARAMS

    from .strategies.registry import StrategyError, get_strategy, make_label
    try:
        strat = get_strategy(strategy or cfg.strategy)
    except StrategyError as e:
        print(f"strateji hatasi: {e.code}: {e}", file=sys.stderr)
        return EXIT_ENGINE
    label = make_label(strat.info.name, strat.info.version)
    Path(cfg.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    params = {k: getattr(DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    try:
        # create=True yeni dosya kurar; var olan eski sema dosyasi BURADA goc ettirilmez (goc yalniz motor surecinde)
        led = L.open_ledger(cfg.ledger_path, cfg.bot, create=True, migrate=False)
    except L.LedgerSchemaError as e:
        # paper: var olan ESKI semali defter hata degildir; goc motor surecinde (yedekle) yapilir. Birim ExecStartPre'si
        # (trader-engine@.service init-ledger) burada 4 donerse motor hic acilamaz ve goc hic olmaz (18 Kasim sunucu olayi).
        # testnet/live bu yola girmez: `run --ensure-ledger` damga denetimiyle ayri karar verir (DD-9 F1).
        if cfg.mode == "paper" and "eski" in str(e) and Path(cfg.ledger_path).exists():
            print(f"defter eski semada: {e}; goc motor baslarken yapilacak", file=sys.stderr)
            return EXIT_OK
        print(f"defter sema hatasi: {e} (goc motor baslarken yapilir)", file=sys.stderr)
        return EXIT_ENGINE
    try:
        # DD-8 (O8): yabanci damgali defterde hicbir sey yazilmaz. testnet/live: damga != want; paper: her damga yabancidir.
        # `init-ledger` damga YAZMAZ (damgayi motor acilisi yazar).
        try:
            led_stamp = led.get_meta("account_stamp")
        except L.LedgerError as e:
            print(f"defter damgasi okunamadi: {e}", file=sys.stderr)
            return EXIT_PERMISSION
        if led_stamp is not None:
            from .stamp import want_stamp
            if cfg.mode == "paper" or (cfg.mode in ("testnet", "live") and led_stamp != want_stamp(cfg)):
                print("defter baska mod/hesap damgali: init-ledger reddedildi (ledger_stamp_mismatch)", file=sys.stderr)
                return EXIT_PERMISSION
        try:
            led.get_active_params()
            exists = True
        except L.LedgerError:
            exists = False
        if exists and reason != "strategy_update":
            print("etkin parametre var: dokunulmadi")
        elif not exists:
            led.init_params(params, reason=f"{label} {reason}")
        else:
            cur = led.get_active_params()
            try:
                cur_reason = led.get_version(cur.version_id).reason or ""
            except L.LedgerError:
                cur_reason = ""
            from .strategies.registry import parse_label
            if parse_label(cur_reason) == parse_label(label):
                print(f"etkin surum zaten {label}: dokunulmadi")
                return EXIT_OK
            # strateji etiketi degisimi: params ayni kalir (AKTIF params, varsayilan DEGIL), yalniz etiket tasinir
            vid = led.create_user_version(dict(cur.params), reason=f"{label} {reason}", allow_same_params=True)
            led.activate_version(vid, actor="user", reason=f"{label} {reason}")
            print(f"strateji etiketi guncellendi: {'@'.join(x for x in parse_label(cur_reason) if x)} -> {label} (surum {vid})")
    finally:
        led.close()
    return EXIT_OK


def _cmd_reconcile(a) -> int:
    from .engine import build_engine
    from .engine import EngineExit
    from .errors import ConfigError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    if cfg.mode in ("testnet", "live"):
        print("faz_b: testnet/live reconcile henuz uygulanmadi", file=sys.stderr)
        return EXIT_FAZ_B
    if getattr(a, "apply", False):
        return _reconcile_run(cfg)
    # DD-2 D8: varsayilan SALT OKUR. State ve defter gecici kopyada mutabakata sokulur; gercek dosyalara (state, defter,
    # spool, status, kilit) dokunulmaz. Eski (yazan) davranis: `--apply` (motor DURUKEN).
    import shutil
    import sqlite3
    import tempfile

    from .config import apply_overrides
    src_state, src_ledger = Path(cfg.state_path), Path(cfg.ledger_path)
    if not src_state.exists() or src_state.stat().st_size == 0:
        print(f"state yok: {src_state}", file=sys.stderr)
        return EXIT_FAZ_B
    with tempfile.TemporaryDirectory(prefix="reconcile-ro-") as tmp:
        tcfg = apply_overrides(cfg, var_dir=tmp)
        Path(tcfg.state_path).parent.mkdir(parents=True, exist_ok=True)
        for src, dst in ((src_state, tcfg.state_path), (src_ledger, tcfg.ledger_path)):
            if not src.exists():
                continue
            sc = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
            try:
                sc.execute("VACUUM INTO ?", (dst,))              # tutarli kopya (WAL dahil); kaynak salt okunur
            finally:
                sc.close()
        spool = Path(str(src_ledger) + ".spool.jsonl")
        if spool.exists():
            shutil.copyfile(spool, tcfg.ledger_path + ".spool.jsonl")
        rc = _reconcile_run(tcfg)
    print("salt-okur: gercek state/defter degismedi (yazan mutabakat icin --apply)", file=sys.stderr)
    return rc


def _reconcile_run(cfg) -> int:
    from .engine import EngineExit, build_engine
    eng = build_engine(cfg)
    try:
        eng.start()
    except EngineExit as e:
        return e.code
    rep = eng.reconciler.run(eng.clock.now())
    print(json.dumps({"ok": rep.ok, "fatal": rep.fatal, "actions": rep.actions, "findings": rep.findings}))
    return EXIT_OK if rep.ok else EXIT_FINDINGS


def _cmd_kill(a) -> int:
    from .clock import SystemClock
    cfg = _load_cfg(a)
    from .killswitch import Killswitch
    k = Killswitch(cfg.kill_file, SystemClock())
    print(f"kill_file: {cfg.kill_file}")                       # DD-2 D7: cozumlenmis mutlak yol
    if a.clear:
        k.clear()
    else:
        k.set(a.by, a.reason)
    return EXIT_OK


def _cmd_unblock(a) -> int:
    """DD-2 (D6 = dunku O6): elle kalkan giris engeli nedenlerini (`engine_errors`, `strategy_mismatch`) kaldirir. Yalniz motor
    DURUYORKEN (state kilidi alinamazsa reddedilir); once `block_audit.jsonl`a kayit (fsync), sonra kume guncellenir. Baska
    nedenlere (otomatik kalkanlar dahil) dokunmaz. `--list`: kumeyi yazdirir (kilit alinir; motor calisiyorsa reddedilir)."""
    import os

    from .clock import SystemClock
    from .errors import ConfigError, StateError
    from .fileio import fmt_ts
    from .state import MANUAL_CLEAR_REASONS, StateStore
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    if not a.list:
        if a.reason not in MANUAL_CLEAR_REASONS:
            print(f"hata: --reason {'|'.join(MANUAL_CLEAR_REASONS)} olmali (otomatik kalkan nedenler elle kaldirilmaz)",
                  file=sys.stderr)
            return EXIT_FAZ_B
        by = _by_of(a)
        if by is None:
            return EXIT_FAZ_B
    sp = Path(cfg.state_path)
    if not sp.exists() or sp.stat().st_size == 0:
        print(f"state yok: {sp}", file=sys.stderr)
        return EXIT_FAZ_B
    try:
        st = StateStore(str(sp), bot=cfg.bot, ledger_path=cfg.ledger_path)
    except StateError as e:
        print(f"hata: {e} (motor durdurulmadan engel kaldirilmaz)", file=sys.stderr)
        return EXIT_FAZ_B
    try:
        cur = st.block_reasons()
        if a.list:
            print(json.dumps({"bot": cfg.bot, "reasons": cur, "primary": st.kv_get("entries_blocked_reason"),
                              "manual_clear": [r for r in cur if r in MANUAL_CLEAR_REASONS]}, ensure_ascii=False))
            return EXIT_OK
        if a.reason not in cur:
            print(f"neden kumede yok: {a.reason} (mevcut: {cur})", file=sys.stderr)
            return EXIT_FINDINGS
        remaining = [r for r in cur if r != a.reason]
        row = {"at": fmt_ts(SystemClock().now()), "op": "unblock", "reason": a.reason, "by": by,
               "note": a.note or "", "bot": cfg.bot, "remaining": remaining}
        ap = Path(cfg.path("block_audit.jsonl"))
        try:
            ap.parent.mkdir(parents=True, exist_ok=True)
            with open(ap, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            print(f"hata: denetim kaydi yazilamadi ({type(e).__name__}); engel kaldirilmadi", file=sys.stderr)
            return EXIT_ENGINE
        st.block_remove(a.reason)
        print(json.dumps({"unblocked": a.reason, "remaining": remaining}, ensure_ascii=False))
        if a.reason == "strategy_mismatch":
            print("not: strateji surumu hala uyusmuyorsa motor acilista nedeni yeniden ekler", file=sys.stderr)
        return EXIT_OK
    finally:
        st.close()


def _cmd_outbox_quarantine(a) -> int:
    """DD-11 Z-4: defter dogrulama hatasi veren (teslim edilemez) outbox satirlarini karantinaya tasir. Yalniz motor DURUKEN
    (state kilidi alinamazsa reddedilir). Varsayilan dry-run; `--apply` uygular. Dogrulama, defterin GECICI kopyasinda sirayla
    denenir (gercek defter degismez); yalniz LedgerValidationError veren satirlar tasinir, gecerli satirlara dokunulmaz."""
    import shutil
    import sqlite3
    import tempfile

    from trader_core import ledger as L

    from .clock import SystemClock
    from .errors import ConfigError, StateError
    from .state import StateStore, _write_ledger
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return EXIT_FAZ_B
    sp, lp = Path(cfg.state_path), Path(cfg.ledger_path)
    if not sp.exists() or sp.stat().st_size == 0:
        print(f"state yok: {sp}", file=sys.stderr)
        return EXIT_FAZ_B
    if not lp.exists() or lp.stat().st_size == 0:
        print(f"defter yok: {lp}", file=sys.stderr)
        return EXIT_FAZ_B
    try:
        st = StateStore(str(sp), bot=cfg.bot, ledger_path=cfg.ledger_path)
    except StateError as e:
        print(f"hata: {e} (motor calisirken outbox karantinaya alinmaz)", file=sys.stderr)
        return EXIT_FAZ_B
    apply = bool(getattr(a, "apply", False))
    try:
        try:
            rows = st.outbox_pending()
        except (KeyError, TypeError, ValueError) as e:      # bozuk payload JSON (JSONDecodeError ValueError alt sinifi)
            print(f"hata: bozuk outbox yuku ({type(e).__name__}: {e}); hicbir sey tasinmadi", file=sys.stderr)
            return EXIT_ENGINE
        bad: list[tuple] = []
        with tempfile.TemporaryDirectory(prefix="outbox-quarantine-") as tmp:
            tl = str(Path(tmp) / "ledger.sqlite")
            sc = sqlite3.connect(f"file:{lp}?mode=ro", uri=True)
            try:
                sc.execute("VACUUM INTO ?", (tl,))
            finally:
                sc.close()
            led = L.open_ledger(tl, cfg.bot, create=False, migrate=False)
            try:
                for row in rows:
                    try:
                        _write_ledger(led, row)
                    except L.LedgerValidationError as e:
                        bad.append((row, str(e) or type(e).__name__))
                    except (KeyError, TypeError, ValueError) as e:
                        print(f"hata: bozuk outbox yuku (satir {row.id}): {type(e).__name__}: {e}; hicbir sey tasinmadi",
                              file=sys.stderr)
                        return EXIT_ENGINE
                    except L.LedgerError as e:
                        print(f"hata: dogrulama disi defter hatasi (satir {row.id}): {e}; hicbir sey tasinmadi", file=sys.stderr)
                        return EXIT_ENGINE
            finally:
                led.close()
        for row, why in bad:
            p = row.payload
            pos = st.get_position(row.trade_id)
            orders = [o for o in st.orders_for_trade(row.trade_id) if o.role == ("entry" if row.kind == "entry" else "exit")]
            print(json.dumps({"outbox_id": row.id, "kind": row.kind, "trade_id": row.trade_id,
                              "pair": getattr(pos, "pair", None), "side": getattr(pos, "side", None),
                              "qty": p.get("qty", getattr(pos, "qty", None)),
                              "price": p.get("entry_price" if row.kind == "entry" else "exit_price"),
                              "client_id": orders[-1].client_id if orders else None, "reason": why}, ensure_ascii=False))
        if not apply:
            print(json.dumps({"dry_run": True, "pending": len(rows), "would_quarantine": len(bad)}))
            return EXIT_OK
        if bad:
            logging.getLogger("trader_engine.cli").warning("outbox-quarantine: %d satir tasiniyor, ids=%s", len(bad),
                                                           [r.id for r, _ in bad])
        n = st.outbox_quarantine([(r.id, why) for r, why in bad], SystemClock().now()) if bad else 0
        print(json.dumps({"dry_run": False, "pending": len(rows), "quarantined": n}))
        return EXIT_OK
    finally:
        st.close()


def _cmd_pause(a) -> int:
    """11 §9.5: duraklatma tutuslari. `remove` motor kodunda yalniz burada cagrilir (AST korumasi)."""
    from .clock import SystemClock
    from .pause import EntryPause
    cfg = _load_cfg(a)
    p = EntryPause(f"{cfg.pause_file}.{cfg.bot}", SystemClock(), audit_path=cfg.path("pause_audit.jsonl"), bot=cfg.bot)
    try:
        if a.list:
            print(json.dumps({"bot": cfg.bot, "active": p.active(), "pause_file": p.path,
                              "holds": [dataclasses.asdict(h) for h in p.holds()]}, ensure_ascii=False))
            return EXIT_OK
        if a.clear:
            if not a.reason or not a.by:
                print("hata: --clear icin --reason ve --by zorunlu (ornek: --reason manual --by ad)", file=sys.stderr)
                return EXIT_FAZ_B
            ok = p.remove(a.reason, a.by)
            print("kaldirildi" if ok else "tutus yok / kaldirilamadi")
            return EXIT_OK if ok else EXIT_FINDINGS
        ok = p.add(a.reason or "manual", a.by or "cli", a.note)
        print("eklendi" if ok else "zaten var / eklenemedi")
        return EXIT_OK
    except ValueError as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_FAZ_B


# ====================================================================== 12 (RK-1): sermaye ve kademe CLI'si
EXIT_LADDER = EXIT_FINDINGS   # 12 §5 (v1.1): 5 = bulgu (bozuk gunluk, kosulu tutmayan step-up); 4 = EXIT_ENGINE ile cakismaz


def _ladder_ctx(a, *, write: bool):
    """-> (cfg, LadderLog, hata_kodu). write=True: yalniz backtest'te ret (cikis 2); 24.11: kagitta dosya gunlugu var."""
    from trader_core import risk_ladder as RL

    from .errors import ConfigError
    try:
        cfg = _load_cfg(a)
    except ConfigError as e:
        print(f"yapilandirma hatasi: {e}", file=sys.stderr)
        return None, None, EXIT_FAZ_B
    if write and cfg.mode == "backtest":
        print("backtest kipinde sermaye kaydi yok (yazan komut reddedildi)", file=sys.stderr)
        return cfg, None, EXIT_FAZ_B
    return cfg, RL.LadderLog(cfg.path("risk_ladder.jsonl")), None


def _by_of(a) -> str | None:
    import re
    by = getattr(a, "by", None)
    if not isinstance(by, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", by):
        print("hata: --by zorunlu (1-32 karakter: harf, rakam, _ . -)", file=sys.stderr)
        return None
    return f"cli:{by}"


def _state_or_exit(log, *, need: bool):
    """-> (state, rows, kod). Bozuk gunluk: kod 4; gerekli ama yok: kod 2."""
    from trader_core import risk_ladder as RL
    try:
        rows = log.rows()
        st = RL.fold(rows)
    except RL.LadderLogError as e:
        print(f"gunluk bozuk: {e}", file=sys.stderr)
        return None, None, EXIT_LADDER
    if need and st is None:
        print("gunluk bos: once `capital init --amount <tutar>`", file=sys.stderr)
        return None, rows, EXIT_FAZ_B
    return st, rows, None


def _status_equity(cfg, now):
    """12 §4.3: status.json `equity` (loop_at en cok STATUS_FRESH_S eski) -> (equity | None, neden)."""
    import math

    from trader_core import risk_ladder as RL
    try:
        d = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        loop = RL.parse_at(d["loop_at"])
        eq = d["equity"]
    except (OSError, ValueError, KeyError, TypeError, RL.LadderLogError):
        return None, "status.json okunamadi"
    if (now - loop).total_seconds() > RL.STATUS_FRESH_S:
        return None, f"status.json bayat (> {int(RL.STATUS_FRESH_S)} sn)"
    if isinstance(eq, bool) or not isinstance(eq, (int, float)) or not math.isfinite(eq) or eq <= 0:
        return None, "status.json equity gecersiz"
    return float(eq), ""


def _equity_arg(a, cfg, now):
    import math
    if getattr(a, "equity", None) is not None:
        e = a.equity
        if not math.isfinite(e) or e <= 0:
            print("hata: --equity sonlu ve > 0 olmali", file=sys.stderr)
            return None
        return float(e)
    eq, why = _status_equity(cfg, now)
    if eq is None:
        print(f"hata: ozsermaye bilinmiyor ({why}); --equity verin", file=sys.stderr)
    return eq


def _print_levels(st) -> None:
    from trader_core import risk_ladder as RL
    print(json.dumps({"basamak": RL.STEP_NAMES[st.step], "durum": st.status, "dep_net": st.dep_net, "base": st.base,
                      "durma_seviyesi": round(RL.STOP_RATIO * st.base, 8),
                      "taban_seviyesi": round(RL.FLOOR_RATIO * st.dep_net, 8)}, ensure_ascii=False))


def _ladder_pause(cfg):
    from .clock import SystemClock
    from .pause import EntryPause
    return EntryPause(f"{cfg.pause_file}.{cfg.bot}", SystemClock(), audit_path=cfg.path("pause_audit.jsonl"),
                      bot=cfg.bot)


def _write_row(log, kind, a, now, **fields):
    from trader_core import risk_ladder as RL
    by = _by_of(a)
    if by is None:
        return None, EXIT_FAZ_B
    try:
        row = log.append(kind, by, now, note=getattr(a, "note", "") or "", **fields)
    except RL.LadderLogError as e:
        print(f"gecersiz istek, hicbir sey yazilmadi: {e}", file=sys.stderr)
        return None, EXIT_FAZ_B
    except OSError as e:
        print(f"gunluk yazilamadi: {type(e).__name__}", file=sys.stderr)
        return None, EXIT_LADDER
    return row, None


def _testnet_wallet_balance() -> float:
    """Testnet hesabinin USDT cuzdan bakiyesi (totalWalletBalance; motorun acilista okudugu alan). Hata: ValueError."""
    import math
    import os

    from .clock import SystemClock
    from .config import load_keys
    from .errors import ConfigError
    from .exchange.binance_rest import ExchangeError, SignedRestClient
    try:
        key, secret = load_keys(os.environ)
        saat = SystemClock()
        rest = SignedRestClient(env="testnet", api_key=key, api_secret=secret,
                                now_ms=lambda: int(saat.now().timestamp() * 1000), sleep=saat.sleep)
        rest.sync_time()
        acct = rest.account()
    except (ConfigError, ExchangeError, OSError) as e:
        raise ValueError(f"testnet bakiyesi okunamadi: {type(e).__name__}") from e
    raw = acct.get("totalWalletBalance") if isinstance(acct, dict) else None
    try:
        bal = float(raw)
    except (TypeError, ValueError):
        raise ValueError("testnet bakiyesi okunamadi: totalWalletBalance gecersiz") from None
    if not math.isfinite(bal) or bal <= 0:
        raise ValueError("testnet bakiyesi pozitif sonlu degil")
    return bal


def _cmd_capital_from_exchange(a, *, fetch=None) -> int:
    """YALNIZ testnet: gunluk bossa `initial` satirini testnet borsasindan okunan bakiyeyle yazar (kurulum adimi).
    Dolu gunluk: dokunmaz (cikis 0). Okuma hatasi: hicbir sey yazmaz, cikis != 0."""
    if getattr(a, "env", None) != "testnet":
        print("hata: init-from-exchange yalniz --env testnet (paper/live reddedildi)", file=sys.stderr)
        return EXIT_FAZ_B
    cfg, log, rc = _ladder_ctx(a, write=True)
    if rc is not None:
        return rc
    if cfg.mode != "testnet":
        print("hata: init-from-exchange yalniz testnet kipinde", file=sys.stderr)
        return EXIT_FAZ_B
    if _by_of(a) is None:
        return EXIT_FAZ_B
    st, rows, rc = _state_or_exit(log, need=False)
    if rc is not None:
        return rc
    if rows:
        print("gunluk dolu: dokunulmadi (init-from-exchange yalniz bos gunluge yazar)")
        return EXIT_OK
    try:
        bal = (fetch or _testnet_wallet_balance)()
    except ValueError as e:
        print(f"hata: {e}; hicbir sey yazilmadi", file=sys.stderr)
        return EXIT_FAZ_B
    a.amount = bal
    a.note = "testnet bakiye (borsadan okundu, totalWalletBalance)"
    a.cap_cmd = "init"
    return _cmd_capital(a)


def _cmd_capital(a) -> int:
    import math

    from trader_core import risk_ladder as RL  # noqa: F401 - list/withdraw yollari

    from .clock import SystemClock
    op = a.cap_cmd
    if op == "init-from-exchange":
        return _cmd_capital_from_exchange(a)
    write = op != "list"
    cfg, log, rc = _ladder_ctx(a, write=write)
    if rc is not None:
        return rc
    now = SystemClock().now()
    if op == "list":
        st, rows, rc = _state_or_exit(log, need=False)
        if rc is not None:
            return rc
        sd = None
        if st is not None:
            sd = {k: (RL.fmt_at(v) if hasattr(v, "tzinfo") and v is not None else v)
                  for k, v in dataclasses.asdict(st).items()}
            sd["fired"] = sorted(st.fired)
            sd["step_name"] = RL.STEP_NAMES[st.step]
        print(json.dumps({"bot": cfg.bot, "rows": rows, "state": sd}, ensure_ascii=False))
        return EXIT_OK
    if _by_of(a) is None:
        return EXIT_FAZ_B
    st, rows, rc = _state_or_exit(log, need=(op != "init"))
    if rc is not None:
        return rc
    if op == "init":
        if cfg.mode == "paper":
            print("kagitta `capital init` yok: ilk satiri motor yazar (wallet_start)", file=sys.stderr)
            return EXIT_FAZ_B
        if rows:
            print("gunluk dolu: ikinci `capital init` yok (duzeltme icin `capital adjust`)", file=sys.stderr)
            return EXIT_FAZ_B
        # 23.11 kullanici karari: canli = kagit; canli gunluk %1 (K2) basamagindan baslar (testnet K0)
        # 24.11: start_step testnet icin de yazilir
        extra = {"start_step": RL.LIVE_START_STEP} if cfg.mode in ("live", "testnet") else {}
        row, rc = _write_row(log, "initial", a, now, amount=a.amount, **extra)
    elif op == "deposit":
        row, rc = _write_row(log, "deposit", a, now, amount=a.amount)
    elif op == "adjust":
        if not (a.note or "").strip():
            print("hata: adjust icin --note zorunlu", file=sys.stderr)
            return EXIT_FAZ_B
        row, rc = _write_row(log, "adjust", a, now, amount=a.amount)
    else:                                               # withdraw (§4.3: once karden)
        eq = _equity_arg(a, cfg, now)
        if eq is None:
            return EXIT_FAZ_B
        if not (math.isfinite(a.amount) and a.amount > 0):
            print("hata: --amount > 0 olmali", file=sys.stderr)
            return EXIT_FAZ_B
        cap = max(0.0, a.amount - max(0.0, eq - st.base))
        row, rc = _write_row(log, "withdraw", a, now, amount=a.amount, equity=eq, capital_part=cap)
    if rc is not None:
        return rc
    st2 = log.state()
    print(f"yazildi: seq={row['seq']} {row['kind']}")
    _print_levels(st2)
    if op in ("deposit", "withdraw"):
        print("Canlida bu kayit borsadaki aktarimla eslesene kadar yeni giris kapalidir.")
    return EXIT_OK


def _closed_trades_for_cli(cfg, since):
    from trader_core import ledger as L
    if not Path(cfg.ledger_path).exists():
        return []
    led = L.open_ledger(cfg.ledger_path, cfg.bot, create=False, read_only=True)
    try:
        return led.list_closed_trades(since=since, limit=L.Ledger.LIST_CLOSED_MAX)
    finally:
        led.close()


def _cmd_ladder(a) -> int:
    from trader_core import risk_ladder as RL

    from .clock import SystemClock
    op = a.lad_cmd
    write = op != "status"
    cfg, log, rc = _ladder_ctx(a, write=write)
    if rc is not None:
        return rc
    now = SystemClock().now()
    if op == "status":
        try:
            blk = json.loads(Path(cfg.status_path).read_text(encoding="utf-8")).get("risk_ladder")
        except (OSError, ValueError, AttributeError):
            blk = None
        if isinstance(blk, dict):
            print(json.dumps({"bot": cfg.bot, "source": "status.json", "risk_ladder": blk}, ensure_ascii=False))
            return EXIT_OK
        st, _rows, rc = _state_or_exit(log, need=False)
        if rc is not None:
            return rc
        out = None if st is None else {
            "state": st.status, "step": st.step, "step_name": RL.STEP_NAMES[st.step], "dep_net": st.dep_net,
            "base": st.base, "peak": st.peak, "stop_at": round(RL.STOP_RATIO * st.base, 8),
            "floor_at": round(RL.FLOOR_RATIO * st.dep_net, 8), "log_seq": st.seq}
        print(json.dumps({"bot": cfg.bot, "source": "log", "risk_ladder": out}, ensure_ascii=False))
        return EXIT_OK
    by = _by_of(a)
    if by is None:
        return EXIT_FAZ_B
    st, rows, rc = _state_or_exit(log, need=True)
    if rc is not None:
        return rc
    pause = _ladder_pause(cfg)
    if op == "resume":
        hold = any(h.reason == "drawdown_review" for h in pause.holds())
        if st.status == "floor":
            print("durum floor: `ladder floor-restart` gerekir", file=sys.stderr)
            return EXIT_FAZ_B
        if st.status == "ok":
            if not hold:
                print("kademe incelemesi yok (durum ok, drawdown_review tutusu yok)", file=sys.stderr)
                return EXIT_FAZ_B
            print("durum zaten ok: yalniz artik tutus kaldiriliyor")
        else:
            eq = _equity_arg(a, cfg, now)
            if eq is None:
                return EXIT_FAZ_B
            row, rc = _write_row(log, "review_resume", a, now, equity=eq, rebase=not a.no_rebase,
                                 decision=a.decision or "")
            if rc is not None:
                return rc
            print(f"yazildi: seq={row['seq']} review_resume")
        ok = pause.remove("drawdown_review", by)               # satir yazildi, SONRA tutus kalkar
        print("drawdown_review tutusu kaldirildi" if ok else "drawdown_review tutusu yoktu")
        _print_levels(log.state())
        return EXIT_OK
    if op == "floor-restart":
        if not (a.decision or "").strip():
            print("hata: --decision (yazili karar referansi) zorunlu", file=sys.stderr)
            return EXIT_FAZ_B
        if st.status != "floor":
            print(f"durum floor degil ({st.status})", file=sys.stderr)
            return EXIT_FAZ_B
        eq = _equity_arg(a, cfg, now)
        if eq is None:
            return EXIT_FAZ_B
        row, rc = _write_row(log, "floor_restart", a, now, equity=eq, decision=a.decision)
        if rc is not None:
            return rc
        print(f"yazildi: seq={row['seq']} floor_restart")
        for reason in ("capital_floor", "drawdown_review"):
            ok = pause.remove(reason, by)
            print(f"{reason} tutusu kaldirildi" if ok else f"{reason} tutusu yoktu")
        _print_levels(log.state())
        return EXIT_OK
    # step-up
    if not (a.decision or "").strip():
        print("hata: --decision (karar referansi) zorunlu", file=sys.stderr)
        return EXIT_FAZ_B
    try:
        trades = _closed_trades_for_cli(cfg, st.started_at)
    except Exception as e:  # noqa: BLE001
        print(f"defter okunamadi: {type(e).__name__}", file=sys.stderr)
        return EXIT_LADDER
    cnt = RL.counters(trades, st, now)
    bad = RL.step_up_problems(st, cnt, now)
    if bad:
        for b in bad:
            print(f"kosul tutmuyor: {b}", file=sys.stderr)
        return EXIT_LADDER
    row, rc = _write_row(log, "step_up", a, now, step=st.step + 1, decision=a.decision)
    if rc is not None:
        return rc
    print(f"yazildi: seq={row['seq']} step_up")
    _print_levels(log.state())
    return EXIT_OK


def _cmd_feed(a) -> int:
    from .marketdata import feed as F  # noqa: F401
    runner = getattr(F, "main", None)
    if runner is None:
        print("feed komutu bu surumde 01 modulunden calistirilir", file=sys.stderr)
        return EXIT_FAZ_B
    return int(runner(a.rest) or 0)


def _cmd_backtest(a) -> int:
    """`backtest` alt komutu tum argumanlari backtest.py'nin ayristiricisina gecirir (WP-3: `--record-shadow` orada
    tanimlidir; golge satirlar geri testte varsayilan KAPALI, tf_15m desteklenmez)."""
    from . import backtest as B
    return int(B.main(a.rest) or 0)


def _cmd_rules(a) -> int:
    from .marketdata import feed as F  # noqa: F401
    runner = getattr(F, "rules_snapshot_main", None)
    if runner is None:
        print("rules-snapshot: 01 islevi bu surumde yok", file=sys.stderr)
        return EXIT_FAZ_B
    return int(runner(a.rest) or 0)


def _cmd_smoke(a) -> int:
    print("faz_b")
    return EXIT_FAZ_B


_PASSTHROUGH = {"feed": _cmd_feed, "backtest": _cmd_backtest, "rules-snapshot": _cmd_rules}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="trader_engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def env_arg(p):
        p.add_argument("--env", default=None, choices=("testnet", "live", "paper"),
                       help="config/engine.<env>.json katmani (kip + live blogu + env'e ozgu kill/pause yolu)")

    def bot_args(p, need_bot=True):
        p.add_argument("--bot", required=need_bot, choices=("learner",))
        p.add_argument("--config-dir", default="config")

    p = sub.add_parser("run")
    bot_args(p)
    env_arg(p)
    p.add_argument("--ensure-ledger", action="store_true",
                   help="DD-9: acilista init-ledger isini ayni surecte yap (ret kodu run'in cikis kodudur)")
    p.add_argument("--ledger-reason", default="paper_start")
    p.set_defaults(fn=_cmd_run)
    p = sub.add_parser("init-ledger")
    bot_args(p)
    p.add_argument("--reason", default="paper_start")
    p.add_argument("--strategy", default=None)
    env_arg(p)
    p.set_defaults(fn=_cmd_init_ledger)
    p = sub.add_parser("reconcile")
    bot_args(p)
    p.add_argument("--apply", action="store_true", help="eski davranis: gercek state/defter uzerinde yazan mutabakat (motor duruyorken)")
    env_arg(p)
    p.set_defaults(fn=_cmd_reconcile)
    p = sub.add_parser("kill")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--by", default="cli")
    p.add_argument("--reason", default="manual")
    p.add_argument("--config-dir", default="config")
    env_arg(p)
    p.set_defaults(fn=_cmd_kill)
    p = sub.add_parser("unblock")                       # DD-2 D6: elle kalkan giris engelleri (motor durukken)
    bot_args(p)
    p.add_argument("--list", action="store_true")
    p.add_argument("--reason", default=None, help="engine_errors | strategy_mismatch")
    p.add_argument("--by", default=None)
    p.add_argument("--note", default="")
    env_arg(p)
    p.set_defaults(fn=_cmd_unblock)
    p = sub.add_parser("outbox-quarantine")             # DD-11 Z-4: teslim edilemeyen outbox satirlari (motor durukken)
    bot_args(p)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="varsayilan: yalniz raporlar")
    g.add_argument("--apply", action="store_true", help="gecersiz satirlari ledger_outbox_quarantine'a tasir")
    env_arg(p)
    p.set_defaults(fn=_cmd_outbox_quarantine)
    p = sub.add_parser("arm-quarantine")                # 4b: kurulum kod hatasi karantinasi (list | release)
    bot_args(p)
    p.add_argument("action", choices=("list", "release"))
    p.add_argument("target", nargs="?", default=None, help="release: kurulum kimligi (T1@1h) ya da 'hepsi'")
    env_arg(p)
    p.set_defaults(fn=_cmd_arm_quarantine)
    p = sub.add_parser("pause")
    bot_args(p)
    p.add_argument("--clear", action="store_true")
    p.add_argument("--list", action="store_true")
    p.add_argument("--reason", default=None)
    p.add_argument("--by", default=None)
    p.add_argument("--note", default="")
    env_arg(p)
    p.set_defaults(fn=_cmd_pause)
    p = sub.add_parser("capital")                       # 12 §5
    csub = p.add_subparsers(dest="cap_cmd", required=True)
    for name in ("init", "deposit", "withdraw", "adjust", "list"):
        q = csub.add_parser(name)
        bot_args(q)
        env_arg(q)
        q.add_argument("--note", default="")
        if name != "list":
            q.add_argument("--by", default=None, required=True)
            q.add_argument("--amount", type=float, required=True)
        if name == "withdraw":
            q.add_argument("--equity", type=float, default=None)
        q.set_defaults(fn=_cmd_capital)
    q = csub.add_parser("init-from-exchange")          # yalniz testnet: bakiye borsadan okunur (docs/sunucu-kurulum.md)
    bot_args(q)
    env_arg(q)
    q.add_argument("--by", default=None, required=True)
    q.set_defaults(fn=_cmd_capital, note="")
    p = sub.add_parser("ladder")
    lsub = p.add_subparsers(dest="lad_cmd", required=True)
    for name in ("status", "resume", "floor-restart", "step-up"):
        q = lsub.add_parser(name)
        bot_args(q)
        env_arg(q)
        if name != "status":
            q.add_argument("--by", default=None, required=True)
            q.add_argument("--note", default="")
            q.add_argument("--decision", default="")
        if name in ("resume", "floor-restart"):
            q.add_argument("--equity", type=float, default=None)
        if name == "resume":
            q.add_argument("--no-rebase", action="store_true")
        q.set_defaults(fn=_cmd_ladder)
    for name, fn in (("feed", _cmd_feed), ("backtest", _cmd_backtest), ("rules-snapshot", _cmd_rules)):
        p = sub.add_parser(name)
        p.add_argument("rest", nargs=argparse.REMAINDER)
        p.set_defaults(fn=fn)
    p = sub.add_parser("smoke")
    p.set_defaults(fn=_cmd_smoke)
    return ap


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.INFO)     # DEBUG istek satirlari (imzali sorgu dizgisi) yazilmasin
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in _PASSTHROUGH:
        # argparse.REMAINDER `--secenek` ile baslayan kalani (ornegin `feed --config-dir config`) reddeder: dogrudan ilet
        return int(_PASSTHROUGH[argv[0]](argparse.Namespace(cmd=argv[0], rest=argv[1:])))
    a = build_parser().parse_args(argv)
    return int(a.fn(a))
