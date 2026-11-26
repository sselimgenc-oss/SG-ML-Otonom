#!/usr/bin/env python3
"""Saglik runner (docs/saglik-spec.md Bolum 8). Her 5 dk systemd timer ile calisir; daemon degildir.

Salt okuma: motorun `status.json` dosyasi (learner), salt okunur sqlite. Islem acmaz, defter yazmaz, bot baslatmaz.
Cikis kodlari: 0 saglikli+nabiz gitti; 10 CRIT/UNKNOWN (nabiz yok); 11 saglikli ama nabiz gonderilemedi;
12 uyari iletilemedi; 1 beklenmeyen hata.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

from trader_core import health as H  # noqa: E402
from trader_core import live_paths as LP  # noqa: E402

log = logging.getLogger("trader.health.run")

EXIT_OK, EXIT_UNHEALTHY, EXIT_HB_FAILED, EXIT_ALERT_FAILED, EXIT_CRASH = 0, 10, 11, 12, 1
TOTAL_BUDGET_S = 60.0
STATUS_SCHEMA = "engine-status/1"
STATUS_MAX_BYTES = 2_000_000
PING_MAX_AGE_S = 120  # docs/motor/05 8.2: ping_ok = (simdi - loop_at) <= 120 sn
DEFAULT_BOTS = ("learner",)
BOTS = DEFAULT_BOTS   # geriye uyum; calisma zamani listesi: bots_from_env(env)
_ROOT = _HERE.parent
_TF_UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 7 * 86400}


def data_root(env) -> Path:
    """DD-9 §4.1: TRADER_DATA_ROOT tanimli ve mutlaksa veri koku; aksi halde kod koku (bugunku davranis).
    Root birimleri kodu /usr/local/lib/trader-root/current altindan, veriyi /opt/trader altindan okur."""
    v = (env.get("TRADER_DATA_ROOT") or "").strip()
    return Path(v) if v and os.path.isabs(v) else _ROOT


def bots_from_env(env) -> tuple[str, ...]:
    """HEALTH_BOTS (virgullu; varsayilan "learner"). Bos/gecersiz -> varsayilan."""
    raw = (env.get("HEALTH_BOTS") or "").strip()
    bots = tuple(dict.fromkeys(b for b in (x.strip() for x in raw.split(",")) if b))
    return bots or DEFAULT_BOTS


def _env_num(env, name, cast, default, *, minimum=0):
    try:
        v = cast(str(env.get(name) or "").strip())
    except ValueError:
        return default
    return v if v >= minimum and v == v and v not in (float("inf"),) else default


def install_quiet_until(env, now: datetime) -> datetime | None:
    """Kurulum sonrasi sessizlik: install.sh'in yazdigi isaretten (`kurulum.json`: {"at": ISO}) bitis zamani (at + 15 dk).
    Isaret yok/bozuk/pencere bitmis -> None (normal uyari akisi)."""
    path = (env.get("INSTALL_MARKER") or os.path.join(env.get("OTO_STATE_DIR", "/var/lib/trader-oto-guncelle"), "kurulum.json"))
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    at = _parse_dt(d.get("at")) if isinstance(d, dict) else None
    if at is None:
        return None
    until = at + timedelta(minutes=H.QUIET_MINUTES)
    return until if at <= now < until else None


def _cut_title(t: str) -> str:
    return t if len(t) <= 80 else t[:79] + "…"


def make_cfg(env) -> H.HealthConfig:
    import dataclasses
    return dataclasses.replace(H.DEFAULT_CFG, require_bots=bots_from_env(env),
                               naked_alarm_s=_env_num(env, "NAKED_ALARM_S", float, H.DEFAULT_CFG.naked_alarm_s),
                               exchange_unreachable_s=_env_num(env, "EXCHANGE_UNREACH_S", int,
                                                               H.DEFAULT_CFG.exchange_unreachable_s, minimum=1))


class NoHeartbeat:
    """HEARTBEAT_URL bos: dis nabiz kapali (WARN); rc=1 degil."""

    def ok(self, report) -> bool:
        return True

    def fail(self, report) -> bool:
        return True


def timeframe_to_s(tf) -> int | None:
    if not isinstance(tf, str) or len(tf) < 2 or tf[-1] not in _TF_UNITS or not tf[:-1].isdigit():
        return None
    n = int(tf[:-1])
    return n * _TF_UNITS[tf[-1]] if n > 0 else None


def _parse_dt(s):
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


# --------------------------------------------------------------------------- durum dosyasi
def load_state(path) -> tuple[dict, bool]:
    """(durum, sifirlandi_mi). Yok ya da bozuk -> bos durum; bozuksa sifirlandi=True (sessiz degil)."""
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and st.get("schema") == 1:
            return st, False
        return H.empty_state(), True
    except FileNotFoundError:
        return H.empty_state(), False
    except (OSError, ValueError):
        return H.empty_state(), True


def save_state(path, state) -> None:
    from health_backup import atomic_write_json
    atomic_write_json(path, state)
    # UMask=0007 (trader-health.service) state.json'u 0660 root:root yapar; panel/yayin (User=trader) okuyamaz -> "state_okunamadi".
    # Icerik gizli degil (sayaclar/parmak izleri); herkes okuyabilir, yalniz root yazar.
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass


# --------------------------------------------------------------------------- olcumler
def _bot_var(env, bot: str, default_var: str) -> str:
    """Bot basina var dizini (DD-9 §6.3); canli env gecersizse varsayilan (gecersizligi `live_path_issues` CRIT'ler)."""
    try:
        return LP.bot_var_dir(env, bot, default_var)
    except LP.LivePathError:
        return default_var


def status_path(var_dir: str, bot: str) -> str:
    return os.path.join(var_dir, bot, "status.json")


def ledger_path(var_dir: str, bot: str) -> str:
    return os.path.join(var_dir, bot, "ledger.sqlite")


def _ids(v):
    if not isinstance(v, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in v):
        return None
    return tuple(v)


def probe_status(path: str, bot: str, now: datetime) -> tuple[H.ApiProbe, int | None]:
    """Motor status.json -> (ApiProbe, timeframe_s). Fail-closed:
    dosya yok -> ping_ok=False (motor yazmiyor); okunamaz/bozuk/sema ya da bot uyusmaz -> hepsi None (UNKNOWN);
    loop_at 120 sn'den eskiyse ping_ok=False; gelecekteki (saat uyumsuz) loop_at -> ping_ok=None."""
    try:
        with open(path, "rb") as f:
            raw = f.read(STATUS_MAX_BYTES + 1)
    except FileNotFoundError:
        return H.ApiProbe(ping_ok=False), None
    except OSError:
        return H.ApiProbe(), None
    try:
        if len(raw) > STATUS_MAX_BYTES:
            raise ValueError("buyuk")
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return H.ApiProbe(), None
    if not isinstance(d, dict) or d.get("schema") != STATUS_SCHEMA or d.get("bot") != bot:
        return H.ApiProbe(), None
    loop_at = _parse_dt(d.get("loop_at"))
    ping = None
    if loop_at is not None:
        age = (now - loop_at).total_seconds()
        if age >= -H.DEFAULT_CFG.clock_skew_tolerance_s:
            ping = age <= PING_MAX_AGE_S
    gate = d.get("gate")
    gc = gate.get("code") if isinstance(gate, dict) else None
    gate_code = gc if isinstance(gc, str) and gc else "status_malformed"
    kill = d.get("kill") if isinstance(d.get("kill"), bool) else None
    cnt = d.get("counters")
    le = cnt.get("ledger_errors") if isinstance(cnt, dict) else None
    le = le if isinstance(le, int) and not isinstance(le, bool) and le >= 0 else None
    pos = d.get("open_positions")
    unprot = None
    if isinstance(pos, list) and all(isinstance(p, dict) for p in pos):
        try:
            unprot = tuple(int(p["trade_id"]) for p in pos
                           if not (isinstance(p.get("stop"), (int, float)) and not isinstance(p.get("stop"), bool)
                                   and p["stop"] > 0))
        except (KeyError, TypeError, ValueError):
            unprot = None
    dry = d.get("dry_run") if isinstance(d.get("dry_run"), bool) else None
    mode = d.get("mode") if isinstance(d.get("mode"), str) else None
    ex = d.get("exchange")
    has_ex = isinstance(ex, dict)
    reach = ex.get("reachable") if has_ex and isinstance(ex.get("reachable"), bool) else None
    last_sync = _parse_dt(ex.get("last_sync")) if has_ex else None
    naked = _naked_rows(ex.get("naked")) if has_ex else None
    acct_d = acct_u = None
    am = ex.get("account_mode") if has_ex else None
    if isinstance(am, dict):                     # DD-9 §8.1: dogrulanamama sayacindan yasak kaynaklilar dusulur
        dr, un, ub = (_int_or_none(am.get(k)) for k in ("drift", "unverified", "unverified_ban"))
        acct_d = dr
        acct_u = None if un is None or ub is None else max(un - ub, 0)
    probe = H.ApiProbe(ping, loop_at, _parse_dt(d.get("last_candle_open")), _ids(d.get("open_trade_ids")), dry,
                       gate_code, kill, le, unprot, mode, has_ex, reach, last_sync, naked, _ladder_block(d),
                       acct_drift=acct_d, acct_unverified=acct_u)
    return probe, timeframe_to_s(d.get("trigger_tf"))


def _ladder_block(d: dict):
    """12 §11: status.json `risk_ladder` blogu (+ status.pause.holds, 'capital_latch' icin). Blok yok/bozuk -> None."""
    b = d.get("risk_ladder")
    if not isinstance(b, dict):
        return None
    out = dict(b)
    p = d.get("pause")
    holds = p.get("holds") if isinstance(p, dict) else None
    out["pause_holds"] = [{"reason": h.get("reason"), "at": h.get("at")} for h in holds
                          if isinstance(h, dict)] if isinstance(holds, list) else []
    return out


def _naked_rows(v):
    """status.exchange.naked = [{trade_id, pair, seconds}] -> ((id, cift, sn), ...); bozuksa None (UNKNOWN)."""
    if not isinstance(v, list):
        return None
    out = []
    for r in v:
        try:
            sec = float(r["seconds"])
            if isinstance(r["seconds"], bool) or sec != sec or sec < 0:
                return None
            out.append((int(r["trade_id"]), str(r["pair"]), sec))
        except (KeyError, TypeError, ValueError):
            return None
    return tuple(out)


# --------------------------------------------------------------------------- PAUSE / denetim gunlugu (11 §9.2)


def engine_container(path: str, bot: str, now: datetime, state: dict, key: str) -> H.ContainerProbe:
    """Motor surec dogrulugu (docker yok): state = status taze mi; started_at = status.started_at;
    restart_count = kalici sayac (started_at degisince +1; durum dosyasinda saklanir); oom_killed bilinmez (None)."""
    try:
        with open(path, "rb") as f:
            d = json.loads(f.read(STATUS_MAX_BYTES).decode("utf-8"))
        if not isinstance(d, dict) or d.get("schema") != STATUS_SCHEMA or d.get("bot") != bot:
            return H.ContainerProbe()
        started = _parse_dt(d.get("started_at"))
        loop_at = _parse_dt(d.get("loop_at"))
    except (OSError, ValueError, UnicodeDecodeError):
        return H.ContainerProbe()
    if started is None or loop_at is None:
        return H.ContainerProbe()
    base = int(state.get("restart_counts", {}).get(key, 0) or 0)
    prev = state.get("engine_started_at", {}).get(key)
    count = base + (1 if prev and prev != H._iso(started) else 0)
    fresh = (now - loop_at).total_seconds() <= H.DEFAULT_CFG.loop_crit_s
    return H.ContainerProbe("running" if fresh else "not_running", count, started, None)


_TS_TABLES = (("health_probes", "probed_at"), ("decision_events", "recorded_at"),
              ("trade_entries", "recorded_at"), ("trade_exits", "recorded_at"))


def probe_ledger(db_path: str, bot: str, open_ids) -> H.LedgerProbe:
    """Salt okunur. Kapi, yazmadan turetilir (spec 3.2)."""
    last = spool = unl = schema_ok = active = None
    corrupt = None
    cp = db_path + ".spool.corrupt.jsonl"          # DD-8 (E4): dosya yok -> 0; okunur -> satir sayisi; baska OSError -> None
    try:
        corrupt = _count_lines(cp)
    except FileNotFoundError:
        corrupt = 0
    except OSError:
        corrupt = None
    try:
        spool = os.path.getsize(db_path + ".spool.jsonl") and _count_lines(db_path + ".spool.jsonl")
    except FileNotFoundError:
        spool = 0
    except OSError:
        spool = None
    try:
        from trader_core import ledger as L
        led = L.open_ledger(db_path, bot, create=False, read_only=True)
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        if name == "LedgerSchemaError":
            schema_ok = False
        return H.LedgerProbe(None, spool, None, schema_ok, None, corrupt)
    try:
        schema_ok = True
        try:
            if open_ids is not None:
                unl = tuple(led.find_unledgered_trades(open_ids))
        except Exception:  # noqa: BLE001
            unl = None
    finally:
        try:
            led.close()
        except Exception:  # noqa: BLE001
            pass
    try:
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            stamps = []
            for t, col in _TS_TABLES:
                v = c.execute(f"SELECT max({col}) FROM {t} WHERE bot=?", (bot,)).fetchone()[0]
                if v:
                    stamps.append(v)
            if stamps:
                last = _parse_dt(max(stamps))
            else:
                m = c.execute("SELECT value FROM meta WHERE key='created_at'").fetchone()
                last = _parse_dt(m[0]) if m else None
            active = c.execute("SELECT 1 FROM param_activations WHERE bot=? LIMIT 1", (bot,)).fetchone() is not None
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        pass
    return H.LedgerProbe(last, spool, unl, schema_ok, active, corrupt)


def _count_lines(path) -> int:
    n = 0
    with open(path, "rb") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def market_pairs(env: dict) -> tuple[str, ...]:
    """MARKET_PAIRS (virgullu) ya da ENGINE_CONFIG_DIR/engine.base.json `pairs`; ikisi de yoksa bos
    (probe_market feed-status.json listesine duser)."""
    raw = env.get("MARKET_PAIRS")
    if raw:
        return tuple(p for p in (x.strip() for x in raw.split(",")) if p)
    cd = env.get("ENGINE_CONFIG_DIR")
    if cd:
        try:
            with open(os.path.join(cd, "engine.base.json"), encoding="utf-8") as f:
                pairs = json.load(f).get("pairs")
            if isinstance(pairs, list) and all(isinstance(p, str) for p in pairs):
                return tuple(pairs)
        except (OSError, ValueError, AttributeError):
            pass
    return ()


def pair_classes(env: dict) -> dict:
    """ENGINE_CONFIG_DIR/universe.json: stocks_ordered -> hisse, commodities -> emtia (digerleri kripto = 7/24, haritada yok).
    Dosya yok/okunamaz -> {}."""
    from trader_core.arm_time import CLASS_COMMODITY, CLASS_EQUITY   # noqa: PLC0415
    cd = env.get("ENGINE_CONFIG_DIR")
    if not cd:
        return {}
    try:
        with open(os.path.join(cd, "universe.json"), encoding="utf-8") as f:
            u = json.load(f)
        out = {}
        for key, cls in (("stocks_ordered", CLASS_EQUITY), ("commodities", CLASS_COMMODITY)):
            lst = u.get(key)
            if isinstance(lst, list):
                out.update({str(p).strip().upper().split(":", 1)[0]: cls for p in lst if isinstance(p, str)})
        return out
    except (OSError, ValueError, AttributeError):
        return {}


def collect_market(env: dict, var_dir: str):
    """Opt-in: MARKET_DB yoksa None (piyasa denetimleri kapali). Salt okunur."""
    db = env.get("MARKET_DB")
    if not db:
        return None
    from trader_core.market_probe import probe_market
    fs = env.get("MARKET_FEED_STATUS") or os.path.join(var_dir, "feed-status.json")
    try:
        return probe_market(db_path=db, feed_status_path=fs, pairs=market_pairs(env), pair_classes=pair_classes(env),
                            engine_status_paths={b: status_path(_bot_var(env, b, var_dir), b) for b in bots_from_env(env)})
    except Exception:  # noqa: BLE001
        return H.MarketProbe(feed_status_state="unreadable", db_state="unreadable")


def probe_bans(ban_dir: str) -> tuple:
    """DD-7 §6: dizindeki her `ban.*.json` icin bir `H.BanProbe` (suresi dolmus olanlar dahil; karar cekirdekte).
    Gecersiz/okunamayan dosya -> corrupt=True, until=None. Dizin yok -> (). `.lock` ve gecici dosyalar satir uretmez."""
    from trader_core.ban_store import probe_ban_file
    try:
        names = sorted(n for n in os.listdir(ban_dir) if n.startswith("ban.") and n.endswith(".json") and len(n) > len("ban..json"))
    except FileNotFoundError:
        return ()
    except NotADirectoryError:
        return ()
    except OSError:
        return (H.BanProbe(host="?", until=None, http=None, source=None, corrupt=True),)
    now_ms = int(time.time() * 1000)
    rows = []
    for n in names:
        path = os.path.join(ban_dir, n)
        if not os.path.isfile(path):
            continue
        host = n[len("ban."):-len(".json")]
        try:
            rec = probe_ban_file(path, now_ms)
        except Exception:  # noqa: BLE001
            rec = None
            rows.append(H.BanProbe(host=host, until=None, http=None, source=None, corrupt=True))
        if rec is None:
            continue
        if rec.corrupt:
            rows.append(H.BanProbe(host=host, until=None, http=None, source=None, corrupt=True))
        else:
            rows.append(H.BanProbe(host=rec.host, until=datetime.fromtimestamp(rec.until_ms / 1000, tz=timezone.utc),
                                   http=rec.http, source=rec.source, corrupt=False))
    return tuple(rows)


def collect_bans(env: dict, var_dir: str):
    """DD-7 D2: HEALTH_BAN_DIR, yoksa MARKET_DB'nin dizini, yoksa var_dir (ENGINE_VAR_DIR). Asla None donmez; dizin yoksa ()
    (OK). Hata -> bozuk satir (fail-closed)."""
    d = (env.get("HEALTH_BAN_DIR") or "").strip()
    if not d:
        db = (env.get("MARKET_DB") or "").strip()
        d = os.path.dirname(os.path.abspath(db)) if db else var_dir
    try:
        return probe_bans(d)
    except Exception:  # noqa: BLE001
        return (H.BanProbe(host="?", until=None, http=None, source=None, corrupt=True),)


def probe_disk(paths) -> int | None:
    best = None
    for p in paths:
        try:
            st = os.statvfs(p)
        except OSError:
            return None
        free = st.f_bavail * st.f_frsize
        best = free if best is None else min(best, free)
    return best


# --------------------------------------------------------------------------- ortam
def load_env(environ=None) -> dict:
    env = dict(os.environ if environ is None else environ)
    need = ("ENGINE_VAR_DIR", "BACKUP_DIR")
    missing = [k for k in need if not env.get(k)]
    if missing:
        raise ValueError("eksik ortam degiskenleri: " + ", ".join(missing))
    if not (env.get("HEARTBEAT_URL") or "").strip():
        log.warning("HEARTBEAT_URL bos: dis nabiz KAPALI (dis servis sessizligi izlenmez)")
    return env


def make_notifier(name: str, environ=None):
    """telegram: TelegramNotifier (basarisizsa Outbox spool'una yazar, dedup_key = alert.fingerprint).
    auto: TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID varsa telegram, yoksa log + WARN."""
    environ = os.environ if environ is None else environ
    if name == "log":
        return H.LogNotifier()
    if name in ("telegram", "auto"):
        from trader_core import telegram as T
        n = T.notifier_from_env(environ)
        if n is None:
            if name == "auto":
                log.warning("NOTIFIER=auto: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID yok; uyarilar yalniz gunluge yazilir")
                return H.LogNotifier()
            raise ValueError("telegram yapilandirilmamis")
        return n
    raise ValueError("bilinmeyen NOTIFIER")


# --------------------------------------------------------------------------- ortak okuma yardimcilari
def _int_or_none(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def collect(env: dict, state: dict, now: datetime, *, deadline: float = 0.0) -> H.HealthSnapshot:
    var_dir = env["ENGINE_VAR_DIR"]
    api, ledger, containers = {}, {}, {}
    tf_s = None
    live = LP.live_bots(env)
    live_err = None                               # DD-9 §6.3: gecersiz canli env -> canli botlar icin bos yoklamalar + CRIT
    try:
        LP.validate_live_env(env)
    except LP.LivePathError as e:
        live_err = e
    for bot in bots_from_env(env):
        is_live = bot in live
        if is_live and live_err is not None:
            api[bot], ledger[bot], containers[f"trader-{bot}"] = H.ApiProbe(expect_exchange=True), H.LedgerProbe(), H.ContainerProbe()
            continue
        bvar = _bot_var(env, bot, var_dir)
        sp = status_path(bvar, bot)
        try:
            probe, t = probe_status(sp, bot, now)
        except Exception:  # noqa: BLE001
            probe, t = H.ApiProbe(), None
        if is_live:                               # canli kip yapilandirmadan turetilir (durum dosyasi okunamasa da)
            probe = dataclasses.replace(probe, expect_exchange=True)
        api[bot] = probe
        tf_s = tf_s or t
        try:
            ledger[bot] = probe_ledger(ledger_path(bvar, bot), bot, probe.open_trade_ids)
        except Exception:  # noqa: BLE001
            ledger[bot] = H.LedgerProbe()
        try:
            containers[f"trader-{bot}"] = engine_container(sp, bot, now, state, f"trader-{bot}")
        except Exception:  # noqa: BLE001
            containers[f"trader-{bot}"] = H.ContainerProbe()
    shadow = (env.get("HEALTH_SHADOW_VAR_DIR") or "").strip()
    if shadow:   # testnet golge motoru (var-testnet): yalniz status.json tabanli kontroller (dongu/mum/stopsuz/borsa)
        try:
            sprobe, _ = probe_status(status_path(shadow, "learner"), "learner", now)
        except Exception:  # noqa: BLE001
            sprobe = H.ApiProbe()
        api["learner@testnet"] = dataclasses.replace(sprobe, expect_exchange=True)
    live_path_issues = None
    if live:
        cdir = (env.get("ENGINE_CONFIG_DIR") or "").strip() or str(_ROOT / "config")
        issues = list(LP.check_against_config(env, cdir))
        for bot in live:                          # durum dosyasi okunabildigi halde kip canli degil -> yanlis dizin
            p = api.get(bot)
            if p is not None and p.mode is not None and p.mode != "live":
                issues.append(f"status_mode_mismatch:{bot}")
        live_path_issues = tuple(issues)
    disk_paths = [var_dir, env["BACKUP_DIR"]]
    if (env.get("LIVE_VAR_DIR") or "").strip():
        disk_paths.append(env["LIVE_VAR_DIR"].strip())
    free = probe_disk(disk_paths)
    last_backup = None
    try:
        from health_backup import latest_ok_backup
        last_backup = latest_ok_backup(env["BACKUP_DIR"])
    except Exception:  # noqa: BLE001
        pass
    market = collect_market(env, var_dir)
    prev_am = {}
    for b, v in (state.get("account_mode") if isinstance(state.get("account_mode"), dict) else {}).items():
        if isinstance(v, (list, tuple)) and len(v) == 2 and all(_int_or_none(x) is not None for x in v):
            prev_am[b] = (v[0], v[1])
    return H.HealthSnapshot(
        prev_account_mode=prev_am, live_path_issues=live_path_issues,
        market=market, bans=collect_bans(env, var_dir),
        now=now, timeframe_s=tf_s, api=api, ledger=ledger, disk_free_bytes=free, containers=containers,
        prev_restart_counts=dict(state.get("restart_counts", {})),
        consecutive_restart_runs=dict(state.get("consecutive_restart_runs", {})),
        installed_at=H._from_iso(state.get("installed_at")), last_backup_at=last_backup)


def run_once(env: dict, *, now: datetime | None = None, state_path=None, notifier=None, sender=None,
             snapshot_fn=None) -> int:
    now = now or datetime.now(timezone.utc)
    state_path = state_path or os.path.join(env.get("STATE_DIR", "/var/lib/trader-health"), "state.json")
    state, reset = load_state(state_path)
    if state.get("installed_at") is None:
        state["installed_at"] = H._iso(now)
    notifier = notifier or make_notifier(env.get("NOTIFIER", "log"), env)
    hb_url = (env.get("HEARTBEAT_URL") or "").strip()
    sender = sender or (H.HttpsHeartbeat(hb_url, env.get("HEARTBEAT_FAIL_URL") or None) if hb_url else NoHeartbeat())
    deadline = time.monotonic() + TOTAL_BUDGET_S
    snap = snapshot_fn(env, state, now) if snapshot_fn else collect(env, state, now, deadline=deadline)
    report = H.evaluate(snap, make_cfg(env))

    maint = None
    mf = env.get("HEALTH_MAINTENANCE_FILE")
    if mf:
        try:
            maint = H.parse_maintenance(Path(mf).read_text(encoding="utf-8"), now)
        except OSError:
            maint = None
    alerts, new_state = H.plan_alerts(report, state, now, maintenance_until=maint)
    quiet_until = install_quiet_until(env, now)
    alerts, held = H.quiet_split(alerts, report, now, quiet_until)
    if held:   # tutulan uyarilar iletilmis sayilmaz: durum geri alinir, sorun surerse pencere sonrasinda kendiliginden gider
        new_state = H.revert_failed_alerts(new_state, state, held)
    # sessizlik ozeti: pencerede tutulan uyari basliklari state'te birikir; pencere bitince TEK ozet gider
    tutulan = list(state.get("quiet_held") or [])
    if quiet_until is not None:
        tutulan = list(dict.fromkeys(tutulan + [a.title for a in held]))[:10]
        new_state["quiet_held"] = tutulan
    else:
        new_state["quiet_held"] = []
        if tutulan:
            alerts.append(H.Alert(H.Status.WARN, "quiet_summary", _cut_title("Kurulum sonrası tutulan uyarılar"),
                                  "Kurulumdan sonraki ilk 15 dakikada tutulan uyarılar: " + "; ".join(tutulan)[:380]
                                  + ". Sorun sürüyorsa ayrıca bildirilir.", "quiet|summary", now))
    if reset:
        alerts.append(H.Alert(H.Status.WARN, "state_reset", "Saglik durum dosyasi sifirlandi",
                              "state.json yok ya da bozuktu; sayaclar sifirdan basladi.", "state|state_reset", now))
    # restart sayaclari / ust uste restart turlari
    counts = dict(state.get("restart_counts", {}))
    runs = dict(state.get("consecutive_restart_runs", {}))
    for k, c in snap.containers.items():
        if c.restart_count is not None:
            prev = counts.get(k)
            runs[k] = runs.get(k, 0) + 1 if prev is not None and c.restart_count > prev else 0
            counts[k] = c.restart_count
    new_state["restart_counts"], new_state["consecutive_restart_runs"] = counts, runs
    starts = dict(state.get("engine_started_at", {}))
    for k, c in snap.containers.items():
        if c.started_at is not None:
            starts[k] = H._iso(c.started_at)
    new_state["engine_started_at"] = starts
    new_state["installed_at"] = state["installed_at"]

    am_state = dict(state.get("account_mode") if isinstance(state.get("account_mode"), dict) else {})
    for b, ap in snap.api.items():               # DD-9 §8.1: onceki tur sayaclari (None saklanmaz)
        if ap.acct_drift is not None and ap.acct_unverified is not None:
            am_state[b] = [ap.acct_drift, ap.acct_unverified]
    if am_state:
        new_state["account_mode"] = am_state

    failed = []
    for a in alerts:
        try:
            ok = notifier.send(a)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            failed.append(a)
    if failed:
        new_state = H.revert_failed_alerts(new_state, state, failed)

    code = EXIT_OK
    hb_ok = None
    if H.should_send_ok(report):
        hb_ok = sender.ok(report)
        if not hb_ok:
            log.critical("nabiz gonderilemedi")
            code = EXIT_HB_FAILED
            try:
                notifier.send(H.Alert(H.Status.WARN, "heartbeat_send_failed", "Nabiz gonderilemedi",
                                      "Dis nabiz gonderimi basarisiz; dis servis sessizlikten uyarir.",
                                      "heartbeat|heartbeat_send_failed", now))
            except Exception:  # noqa: BLE001
                pass
    else:
        try:
            sender.fail(report)
        except Exception:  # noqa: BLE001
            pass
        code = EXIT_UNHEALTHY
    if failed and code == EXIT_OK:
        code = EXIT_ALERT_FAILED
    try:
        save_state(state_path, new_state)
    except Exception:  # noqa: BLE001
        log.critical("durum dosyasi yazilamadi")
    print(json.dumps({"at": H._iso(now), "overall": report.overall.value, "heartbeat": hb_ok,
                      "failing": [{"name": r.name, "status": r.status.value, "code": r.code}
                                  for r in report.failing()]}, ensure_ascii=False))
    return code


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
    H.quiet_http_loggers()
    try:
        env = load_env()
        return run_once(env)
    except Exception as e:  # noqa: BLE001
        print(f"health_run: beklenmeyen hata: {type(e).__name__}", file=sys.stderr)
        return EXIT_CRASH


if __name__ == "__main__":
    sys.exit(main())
