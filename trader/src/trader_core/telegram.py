"""Telegram: bildirim, komut ve gunluk rapor (docs/telegram-spec.md). Yalniz stdlib + `requests`.

Giden: `TelegramNotifier` (spool + dogrudan, `dedup_key` zorunlu). Gelen: `TelegramDaemon` (long polling, tek chat,
yalniz ozel sohbet, iki adimli kod onayi, ders onayi alt surecle). Motor bu modulu ice aktarmaz; Telegram ticareti
asla bloke etmez. Token hicbir cikti/gunluk/spool/istisna metninde bulunmaz (`mask`).
HTTP enjekte edilir: `http_post(url, json=..., timeout=...) -> (status_code, body_dict)`; ag hatasi `(0, {})`.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import time
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


from . import lesson as LS
from . import risk_ladder as RL
from . import tg_sade as TS


# trader_core -> trader_engine bagimliligi yasak (08 §4.7): motorun fileio bicimiyle ayni kucuk yardimcilar.
def atomic_write_json(path, data: dict) -> Path:
    """Gecici dosya + fsync + os.replace (trader_engine.fileio.atomic_write_json ile ayni bicim)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=1, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    try:                                    # DD-2 D13: dizin girdisi de diske (en iyi caba)
        dfd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass
    return path


_TS_Z_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d{1,6})?Z$")


def parse_ts_z(s: str) -> datetime:
    """UTC 'YYYY-MM-DDTHH:MM:SSZ' ya da kesirli saniyeli ('.000Z', '.123456Z') zaman. Saat dilimsiz ya da UTC dışı
    (ofsetli) girdi ValueError: motorun ve panelin yazdığı iki biçim de (fileio.fmt_ts, lesson/panel '.%03dZ') kabul edilir."""
    m = _TS_Z_RE.match(s) if isinstance(s, str) else None
    if m is None:
        raise ValueError("zaman UTC 'Z' biçiminde olmalı")
    base = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    frac = m.group(2)
    us = int((frac[1:] + "000000")[:6]) if frac else 0
    return base.replace(microsecond=us, tzinfo=UTC)

log = logging.getLogger("trader.telegram")
UTC = timezone.utc
TR = timezone(timedelta(hours=3))          # Europe/Istanbul: sabit UTC+3 (DST yok)

API = "https://api.telegram.org"
MAX_TEXT = 3500
RETRY_DELAYS = (2, 5, 15)
SEND_BUDGET_S = 30.0
STALE_S = 120
CODE_TTL_S = 120
DEDUP_WINDOW_S = 600
SPOOL_MAX_FILES = 500
SPOOL_MAX_BYTES = 5 * 1024 * 1024
INFO_MAX_AGE_S = 24 * 3600
RATE_PER_MIN = 15
REQ_ID_RE = re.compile(r"^lr-\d{4}-\d{2}-\d{2}-\d+$")
CODE_RE = re.compile(r"^\d{4}$")
SEVERITIES = ("INFO", "WARN", "CRIT")
_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_\-]+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def mask(text: Any, token: str | None = None) -> str:
    t = str(text)
    if token:
        t = t.replace(token, "<gizli>")
    t = _TOKEN_RE.sub("bot<gizli>", t)
    return LS.scrub(t)


def tail3(x: Any) -> str:
    s = str(x)
    return s[-3:]


# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------
def neutralize(text: str) -> str:
    """Komut gibi gorunen '/' satirlarinin basina bosluk ekler; kontrol karakterlerini atar."""
    t = _CTRL_RE.sub(" ", LS.scrub(text))
    return "\n".join((" " + ln) if ln.startswith("/") else ln for ln in t.split("\n"))


def fit_text(body: str, pinned: str = "", limit: int = MAX_TEXT) -> str:
    """Govde kisalir, `pinned` (komut/kod satirlari) sona sabitlenir ve asla kesilmez."""
    body = neutralize(body)
    tail = ("\n" + pinned) if pinned else ""
    if len(body) + len(tail) <= limit:
        return body + tail
    lines = body.split("\n")
    note_room = 40
    out: list[str] = []
    used = 0
    for ln in lines:
        if used + len(ln) + 1 + len(tail) + note_room > limit:
            break
        out.append(ln)
        used += len(ln) + 1
    dropped = len(lines) - len(out)
    if not out:
        out = [lines[0][: max(0, limit - len(tail) - note_room)]]
        dropped = len(lines) - 1
    return "\n".join(out) + f"\n(kısaltıldı, {dropped} satır)" + tail


# ---------------------------------------------------------------------------
# Istemci
# ---------------------------------------------------------------------------
class TelegramError(Exception):
    def __init__(self, kind: str, status: int = 0, retry_after: float | None = None, desc: str = ""):
        super().__init__(f"{kind} {status} {desc}"[:200])
        self.kind = kind                      # transient | permanent | conflict
        self.status = status
        self.retry_after = retry_after


def default_http_post(url: str, json: Any = None, timeout: Any = None, token: str | None = None, files: Any = None):
    import requests
    try:
        if files:                      # sendDocument: multipart; alanlar form verisi (bool -> "true"/"false")
            data = {k: (str(v).lower() if isinstance(v, bool) else v) for k, v in (json or {}).items()}
            r = requests.post(url, data=data, files=files, timeout=timeout)
        else:
            r = requests.post(url, json=json, timeout=timeout)
    except Exception as e:  # noqa: BLE001  istisna metni token tasir: maskelenir, zincir basilmaz
        log.warning("http hatasi: %s", mask(type(e).__name__, token))
        return 0, {}
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, body if isinstance(body, dict) else {}


class TelegramClient:
    def __init__(self, token: str, http_post: Callable | None = None, sleep: Callable[[float], None] = time.sleep):
        if not token:
            raise ValueError("token yok")
        self._token = token
        self._post = http_post or (lambda url, json=None, timeout=None, files=None: default_http_post(url, json, timeout, token, files))
        self.sleep = sleep

    def call(self, method: str, payload: dict, timeout=(5, 10), files: dict | None = None) -> Any:
        try:
            if files:                           # yalniz dosya gonderiminde `files` iletilir (mevcut sahte gonderici imzalari bozulmaz)
                status, body = self._post(f"{API}/bot{self._token}/{method}", json=payload, timeout=timeout, files=files)
            else:
                status, body = self._post(f"{API}/bot{self._token}/{method}", json=payload, timeout=timeout)
        except Exception as e:  # noqa: BLE001
            raise TelegramError("transient", 0, desc=mask(type(e).__name__, self._token)) from None
        if status == 200 and body.get("ok") is True:
            return body.get("result")
        params = body.get("parameters") or {}
        desc = mask(body.get("description", ""), self._token)
        if status == 429:
            raise TelegramError("transient", 429, min(60.0, float(params.get("retry_after", 5) or 5)), desc)
        if status == 409:
            raise TelegramError("conflict", 409, desc=desc)
        if status in (400, 401, 403, 404):
            raise TelegramError("permanent", status, desc=desc)
        raise TelegramError("transient", status, desc=desc)

    def send_message(self, chat_id, text: str, *, disable_notification: bool = False, reply_markup=None) -> dict:
        p = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True,
             "disable_notification": bool(disable_notification)}
        if reply_markup is not None:
            p["reply_markup"] = reply_markup
        res = self.call("sendMessage", p)
        if not isinstance(res, dict) or "message_id" not in res:
            raise TelegramError("transient", 200, desc="message_id yok")
        return res

    def send_document(self, chat_id, filename: str, content: bytes, caption: str = "", *, disable_notification: bool = True) -> dict:
        """sendDocument (multipart/form-data): `content` bayt, `caption` <= 1024 karakter; varsayilan SESSIZ."""
        p = {"chat_id": chat_id, "disable_notification": bool(disable_notification)}
        if caption:
            p["caption"] = caption[:1024]
        res = self.call("sendDocument", p, timeout=(5, 60), files={"document": (filename, content, "text/markdown")})
        if not isinstance(res, dict) or "message_id" not in res:
            raise TelegramError("transient", 200, desc="message_id yok")
        return res

    def get_updates(self, offset: int | None, timeout: int = 30) -> list:
        p: dict = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            p["offset"] = offset
        res = self.call("getUpdates", p, timeout=(5, timeout + 10))
        return res if isinstance(res, list) else []

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> Any:
        return self.call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text[:190]})

    def edit_message_text(self, chat_id, message_id: int, text: str, reply_markup=None) -> Any:
        p = {"chat_id": chat_id, "message_id": message_id, "text": text, "disable_web_page_preview": True}
        p["reply_markup"] = reply_markup if reply_markup is not None else {"inline_keyboard": []}
        return self.call("editMessageText", p)


# ---------------------------------------------------------------------------
# Ortam / yapilandirma
# ---------------------------------------------------------------------------
class TelegramConfig:
    def __init__(self, token: str, chat_id: int, var_dir: str, kill_file: str = "", status_path: str = "",
                 lesson_run: str = "", health_state: str = "", ledger_path: str = "",
                 budget_config: str = "", lesson_store: str = "", config_dir: str = ""):
        self.config_dir = config_dir                 # gunluk zarar orani (engine.*.json risk blogu); bos -> kilitli deger
        self.ledger_path = ledger_path
        self.budget_config, self.lesson_store = budget_config, lesson_store
        self.token, self.chat_id, self.var_dir = token, chat_id, var_dir
        self.kill_file, self.status_path = kill_file, status_path
        self.lesson_run, self.health_state = lesson_run, health_state

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "TelegramConfig | None":
        tok = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
        cid = (env.get("TELEGRAM_CHAT_ID") or "").strip()
        if not tok or not cid:
            return None
        try:
            chat = int(cid)
        except ValueError:
            return None
        here = Path(__file__).resolve().parent.parent.parent
        dr = (env.get("TRADER_DATA_ROOT") or "").strip()      # DD-9 §4.1: root birimleri kodu root kopyadan, veriyi buradan okur
        if dr and Path(dr).is_absolute():
            here = Path(dr)
        return cls(tok, chat, env.get("TELEGRAM_VAR_DIR") or str(here / "var" / "telegram"),
                   env.get("KILL_FILE", ""), env.get("ENGINE_STATUS_PATH", ""),
                   env.get("LESSON_RUN_PATH") or str(here / "scripts" / "lesson_run.py"),
                   env.get("HEALTH_STATE_PATH", ""),
                   _abs_path(here, env.get("LEDGER_PATH") or "user_data/ledger_learner.sqlite"),
                   _abs_path(here, env.get("BUDGET_CONFIG_PATH") or "config/budget.json"),
                   _abs_path(here, env.get("LESSON_STORE_PATH") or "user_data/lesson.sqlite"),
                   (env.get("ENGINE_CONFIG_DIR") or "").strip() or str(here / "config"))


def _abs_path(base: Path, p: str) -> str:
    q = Path(p)
    return str(q if q.is_absolute() else base / q)


def _key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Spool
# ---------------------------------------------------------------------------
class Outbox:
    def __init__(self, base: str | Path, now_fn: Callable[[], datetime]):
        self.dir = Path(base) / "outbox"
        self.sent_dir = self.dir / "sent"
        self.now = now_fn
        self.dropped = 0

    def _mk(self) -> None:
        self.sent_dir.mkdir(parents=True, exist_ok=True)

    def sent_recently(self, key: str) -> bool:
        try:
            until = float((self.sent_dir / _key_hash(key)).read_text().strip())
        except (OSError, ValueError):
            return False
        return until > self.now().timestamp()

    def mark_sent(self, key: str, until_epoch: float | None = None) -> None:
        try:
            self._mk()
            until = until_epoch if until_epoch else self.now().timestamp() + DEDUP_WINDOW_S
            (self.sent_dir / _key_hash(key)).write_text(f"{until:.0f}\n")
        except OSError as e:
            log.warning("sent isareti yazilamadi: %s", type(e).__name__)

    def pending_for(self, key: str) -> list[Path]:
        try:
            return sorted(self.dir.glob(f"*-{_key_hash(key)}.json"))
        except OSError:
            return []

    def list(self) -> list[Path]:
        try:
            return sorted(p for p in self.dir.glob("*.json") if p.is_file())
        except OSError:
            return []

    def enqueue(self, item: dict) -> bool:
        """Ayni dedup_key icin ikinci dosya olmaz. Yazilamazsa False (yalniz gunluk)."""
        key = item["dedup_key"]
        if self.pending_for(key):
            return True
        try:
            self._mk()
            ns = int(self.now().timestamp() * 1e9)
            p = self.dir / f"{ns:020d}-{_key_hash(key)}.json"
            atomic_write_json(p, item)
            try:
                os.chmod(p, 0o660)
            except OSError:
                pass
        except Exception as e:  # noqa: BLE001
            log.error("spool yazilamadi: %s", type(e).__name__)
            return False
        self._enforce_limits()
        return True

    def _read(self, p: Path) -> dict | None:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) and "text" in d and "dedup_key" in d else None
        except (OSError, ValueError):
            return None

    def _enforce_limits(self) -> None:
        files = self.list()
        total = sum(p.stat().st_size for p in files if p.exists())
        if len(files) <= SPOOL_MAX_FILES and total <= SPOOL_MAX_BYTES:
            return
        for sev in ("INFO", "WARN"):
            for p in list(files):
                if len(files) <= SPOOL_MAX_FILES and total <= SPOOL_MAX_BYTES:
                    return
                d = self._read(p)
                if d and d.get("severity") == sev:
                    total -= p.stat().st_size
                    p.unlink(missing_ok=True)
                    files.remove(p)
                    self.dropped += 1

    def drain(self, client: TelegramClient, chat_id: int, sleep: Callable[[float], None] = time.sleep) -> int:
        """Eski->yeni. Basarili dosya silinir. Hata: dur (siradaki tur dener). Gonderilen sayisini dondurur."""
        now = self.now().timestamp()
        items: list[tuple[Path, dict]] = []
        for p in self.list():
            d = self._read(p)
            if d is None:
                continue
            exp = d.get("expires_at")
            if exp is not None and exp <= now:
                p.unlink(missing_ok=True)       # suresi dolmus onay talebi gonderilmez
                continue
            if d.get("severity") == "INFO" and now - float(d.get("created_at", now)) > INFO_MAX_AGE_S:
                p.unlink(missing_ok=True)
                continue
            if self.sent_recently(d["dedup_key"]):
                p.unlink(missing_ok=True)
                continue
            items.append((p, d))
        # hiz siniri: tur basina <= RATE_PER_MIN; asan INFO tek ozet
        budget = RATE_PER_MIN
        if len(items) > budget:
            info = [x for x in items if x[1].get("severity") == "INFO"]
            others = [x for x in items if x[1].get("severity") != "INFO"]
            keep_n = max(0, budget - len(others) - 1)
            merge = info[keep_n:]
            if len(merge) > 1:
                items = sorted(others + info[:keep_n], key=lambda x: x[0].name)
                try:
                    client.send_message(chat_id, f"{len(merge)} mesaj birlestirildi", disable_notification=True)
                    for p, d in merge:
                        p.unlink(missing_ok=True)
                        self.mark_sent(d["dedup_key"])
                except TelegramError:
                    pass
        sent = 0
        for p, d in items[:budget]:
            try:
                client.send_message(chat_id, d["text"], disable_notification=d.get("severity") == "INFO",
                                    reply_markup=d.get("reply_markup"))
            except TelegramError as e:
                if e.kind == "permanent":
                    log.error("CRIT spool gonderimi kalici hata %s", e.status)
                if e.retry_after:
                    sleep(e.retry_after)
                break
            self.mark_sent(d["dedup_key"], d.get("expires_at"))
            p.unlink(missing_ok=True)
            sent += 1
            sleep(1.0)
        return sent


# ---------------------------------------------------------------------------
# Giden: notifier
# ---------------------------------------------------------------------------
PROJE_ETIKETI = "[ML]"


def etiketle(text: str, severity: str) -> str:
    """Telegram standardi (docs/standart/telegram-standardi.md; ortak paket `telegram_cekirdek.etiketle` ile ayni): ilk satir
    `[ML] ` ile baslar; zaten etiketliyse dokunulmaz. Onem duzeyi metindeki isaretle (Dikkat/Sorun/Duzeldi) ve INFO'nun
    sessiz bildirimiyle gorunur."""
    if text.startswith(PROJE_ETIKETI):
        return text
    return f"{PROJE_ETIKETI} {text}"


class TelegramNotifier:
    def __init__(self, client: TelegramClient, chat_id: int, outbox: Outbox, now_fn: Callable[[], datetime] | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.client, self.chat_id, self.outbox = client, chat_id, outbox
        self.now = now_fn or (lambda: datetime.now(UTC))
        self.sleep = sleep
        self.status_path: str | None = None            # "Bot durdu" mesajinda acik pozisyon sayisi icin
        self.kayit = TS.Kayit(Path(outbox.dir).parent / "alarm_kaydi.json", self.now)

    def _send_retry(self, text: str, severity: str, reply_markup=None) -> bool:
        waited = 0.0
        delays = list(RETRY_DELAYS)
        while True:
            try:
                self.client.send_message(self.chat_id, text, disable_notification=severity == "INFO",
                                         reply_markup=reply_markup)
                return True
            except TelegramError as e:
                if e.kind in ("permanent", "conflict"):
                    log.error("CRIT telegram kalici gonderim hatasi %s", e.status)
                    return False
                wait = e.retry_after if e.retry_after else (delays.pop(0) if delays else None)
                if wait is None or waited + wait > SEND_BUDGET_S:
                    return False
                self.sleep(wait)
                waited += wait
            except Exception:  # noqa: BLE001
                return False

    def send_text(self, text: str, severity: str, dedup_key: str, *, expires_at: float | None = None,
                  reply_markup=None, pinned: str = "") -> bool:
        if not dedup_key or not isinstance(dedup_key, str):
            raise ValueError("dedup_key zorunlu")
        if severity not in SEVERITIES:
            raise ValueError("gecersiz severity")
        try:
            return self._deliver(text, severity, dedup_key, expires_at, reply_markup, pinned)
        except Exception as e:  # noqa: BLE001  istisna disariya sizmaz
            log.error("telegram gonderim istisnasi: %s", mask(type(e).__name__))
            return False

    def _deliver(self, text, severity, key, expires_at, reply_markup, pinned) -> bool:
        if self.outbox.sent_recently(key):
            return True                                   # zaten teslim edildi
        body = fit_text(etiketle(text, severity), pinned)
        if expires_at is not None and expires_at <= self.now().timestamp():
            return False
        if self._send_retry(body, severity, reply_markup):
            self.outbox.mark_sent(key, expires_at)
            for p in self.outbox.pending_for(key):
                p.unlink(missing_ok=True)
            return True
        self.outbox.enqueue({"text": body, "severity": severity, "dedup_key": key, "expires_at": expires_at,
                             "reply_markup": reply_markup, "created_at": self.now().timestamp()})
        return False                                      # spool'a yazmak teslim degildir

    # health.Notifier
    def send(self, alert) -> bool:
        """Saglik uyarisi -> sade metin. Susturulanlar (INFO, yapilacak bir sey yok) hicbir sey gondermez (True: teslim sayilir).
        Ayni uyari 6 saatte bir; duzelince tek 'Duzeldi' (yalniz uyarisi gitmisse); 'Bot durdu' 6 saat kuralindan muaf."""
        tur, text, key = TS.saglik_mesaji(alert, self.status_path)
        if text is None:
            return True
        if tur in ("bot_durdu", "bot_duzeldi"):
            key = "bot"
        if tur in ("duzeldi", "bot_duzeldi"):
            if not self.kayit.kapat(key):
                return True                                   # uyarisi hic gitmedi: Duzeldi de gitmez
            return self.send_text(text, "INFO", f"duzeldi:{key}:{self.now().isoformat()}")
        if tur == "bot_durdu":
            self.kayit.isaretle(key)
            return self.send_text(text, "CRIT", f"bot-durdu:{alert.fingerprint}:{int(self.now().timestamp() // 600)}")
        if not self.kayit.gonder_mi(key):
            return True
        sev = "CRIT" if text.startswith("🔴") else "WARN"
        return self.send_text(text, sev, f"alarm:{key}:{self.now().isoformat()}")

    # lesson.LessonNotifier
    def notify(self, notice) -> bool:
        r = TS.ders_mesaji(str(notice.level), str(getattr(notice, "code", "")), str(getattr(notice, "title", "")),
                           str(getattr(notice, "body", "")))
        if r is None:
            return True
        text, key = r
        if str(getattr(notice, "code", "")) in DERS_SESSIZ:       # ders uygulandi / geri alindi: Telegram'a gitmez (gunluk + panel)
            logging.getLogger(__name__).info("ders (Telegram'a gonderilmedi): %s", text.replace("\n", " "))
            return True
        if not self.kayit.gunde_bir(key, self.now().astimezone(TR).date().isoformat()):
            return True                                       # ayni ders icin gunde tek mesaj
        return self.send_text(text, "INFO" if notice.code == "applied" else "WARN", f"ders:{key}:{self.now().isoformat()}")

    def request_approval(self, req) -> bool:
        exp = req.expires_at.timestamp()
        rid = req.request_id
        text = TS.onay_istegi(str(req.param), req.from_value, req.to_value, str(req.body), LS.fmt_ts(req.expires_at))
        pinned = f"/onayla {rid}\n/reddet {rid}"
        kb = {"inline_keyboard": [[{"text": "Onayla", "callback_data": f"ok:{rid}:{int(exp)}"},
                                   {"text": "Reddet", "callback_data": f"no:{rid}:{int(exp)}"}]]}
        return self.send_text(text, "WARN", rid, expires_at=exp, reply_markup=kb, pinned=pinned)


def notifier_from_env(env: Mapping[str, str], http_post=None, now_fn=None, sleep=time.sleep) -> TelegramNotifier | None:
    cfg = TelegramConfig.from_env(env)
    if cfg is None:
        return None
    now_fn = now_fn or (lambda: datetime.now(UTC))
    n = TelegramNotifier(TelegramClient(cfg.token, http_post, sleep), cfg.chat_id, Outbox(cfg.var_dir, now_fn), now_fn, sleep)
    n.status_path = cfg.status_path or None
    return n


LS.NOTIFIER_FACTORIES["telegram"] = lambda cfg, env: notifier_from_env(env)


# ---------------------------------------------------------------------------
# Gelen: daemon
# ---------------------------------------------------------------------------
class _Clk:
    def __init__(self, fn):
        self._fn = fn

    def now(self):
        return self._fn()

    def sleep(self, s):
        time.sleep(s)


def _norm_cmd_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower().replace("ı", "i").replace("İ", "i"))


HELP = ("/durum  /rapor  /kurulumlar  /ders  /hepsini_kapat  /durdur  /devam  /kademe  /kademe_devam  /karantina_kaldir <kurulum>  /onayla <id>  /reddet <id>  /yardim\n"
        "/durdur: yeni girisleri durdurur, pozisyonlar acik kalir (tam kapatma icin /hepsini_kapat)")
PAUSE_USER = "user_cmd"
PAUSE_LATCH = "capital_latch"          # sermaye mandali: /devam + 4 haneli kodla kaldirilir
PAUSE_LIFTABLE = (PAUSE_USER, PAUSE_LATCH)


def pause_state(pauses: Mapping[str, Any] | None) -> dict[str, list]:
    """bot -> tutus listesi (yalniz etkin olanlar)."""
    out: dict[str, list] = {}
    for bot, p in (pauses or {}).items():
        try:
            if p.active():
                out[bot] = list(p.holds())
        except Exception as e:  # noqa: BLE001 - fail-closed: okunamayan duraklatma etkin sayilir
            log.warning("pause okunamadi: %s", type(e).__name__)
            out[bot] = []
    return out


def pause_lines(pauses: Mapping[str, Any], sadece_tutulan: bool = False) -> list[str]:
    """Bot başına duraklatma satırı: neden, kim, ne zaman (11 §9.5; /durum ve günlük rapor), düz Türkçe."""
    st = pause_state(pauses)
    lines = []
    for bot in pauses:
        ad = BOT_TR.get(bot, bot)
        if bot not in st:
            if not sadece_tutulan:
                lines.append(f"▶️ {ad}: yeni işlemler açık")
            continue
        nedenler = "; ".join(dict.fromkeys(neden_tr(h.reason) for h in st[bot])) or "duraklatma durumu okunamadı"
        kim = next((f" ({_kisi_tr(h.by)}" + (f", {z}" if (z := _zaman_tr(h.at)) else "") + ")" for h in st[bot]
                    if h.reason != "unreadable"), "")
        lines.append(f"⏸️ {ad}: yeni işlemler duraklatıldı — {nedenler}{kim}")
    return lines


@dataclass(frozen=True)
class LadderFiles:
    """12 §9: bot basina kademe gunlugu (okuma/yazma), motorun status.json yolu ve duraklatma (tutus kaldirma)."""
    log: Any
    status_path: str
    pause: Any


def _tr(x: Any, nd: int = 2) -> str:
    """Turkce ondalik: 262,40."""
    try:
        v = float(x)
        if not math.isfinite(v):
            return "?"
        return f"{v:.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "?"


def _num_ok(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def ladder_view(lf: LadderFiles, now: datetime) -> dict:
    """12 §9: status.json `risk_ladder` blogu (taze ise) ya da gunlukten katlama ("motor durumu bayat"). Asla istisna atmaz.
    Anahtarlar: state ok|review|floor|uninitialized|invalid, step_name, step_risk, dep_net, base, peak, equity, dd_base_pct,
    stop_at, floor_at, gate_code, counters, stopped_at (datetime|None), step, stale (bool), status_fresh, enforce."""
    out: dict = {"state": "invalid", "stale": True, "status_fresh": False, "equity": None, "gate_code": None,
                 "counters": None, "enforce": None, "step": None, "step_name": None, "step_risk": None,
                 "dep_net": None, "base": None, "peak": None, "stop_at": None, "floor_at": None, "dd_base_pct": None,
                 "dd_peak_pct": None, "stopped_at": None, "near": None, "loop_ok": False, "block_ok": False}
    blk, eq, fresh = None, None, False
    try:
        d = json.loads(Path(lf.status_path).read_text(encoding="utf-8"))
        loop = parse_ts_z(d["loop_at"])
        fresh = -RL.STATUS_FRESH_S <= (now - loop).total_seconds() <= RL.STATUS_FRESH_S
        eq = d.get("equity") if _num_ok(d.get("equity")) and d.get("equity") > 0 else None
        b = d.get("risk_ladder")
        blk = b if isinstance(b, dict) else None
    except Exception:  # noqa: BLE001
        pass
    out["status_fresh"] = fresh
    out["equity"] = eq if fresh else None
    out["loop_ok"] = fresh and eq is not None
    try:
        st = lf.log.state()
    except Exception:  # noqa: BLE001
        st = False
    if st is False:
        out["state"] = "invalid"
        return out
    if st is None:
        out["state"] = "uninitialized"
    else:
        sa = st.stopped_at
        out.update(state=st.status, step=st.step, step_name=RL.STEP_NAMES[st.step], step_risk=RL.STEPS[st.step],
                   dep_net=st.dep_net, base=st.base, peak=st.peak, stopped_at=sa,
                   stop_at=round(RL.STOP_RATIO * st.base, 8), floor_at=round(RL.FLOOR_RATIO * st.dep_net, 8))
        e = out["equity"]
        if e is not None:
            out["dd_base_pct"] = max(0.0, (st.base - e) / st.base * 100.0)
            out["dd_peak_pct"] = max(0.0, (st.peak - e) / st.peak * 100.0)
            out["near"] = e <= round(RL.NEAR_RATIO * st.base, 8)
    if fresh and blk is not None:
        # RK-1 fix 5: blok gunluk durumuyla ayni durumu bildirmeli (eksik/uyusmayan blok = motor durumu okunamiyor)
        out["block_ok"] = st is not None and blk.get("state") == st.status
        out["gate_code"] = blk.get("gate_code")
        out["counters"] = blk.get("counters")
        out["enforce"] = blk.get("enforce")
        if blk.get("equity") is not None and out["equity"] is None and _num_ok(blk.get("equity")):
            out["equity"] = blk.get("equity")
    out["stale"] = not fresh
    return out


def ladder_line(bot: str, v: dict) -> str:
    """12 §9 /durum ve rapor satiri (bot basina tek)."""
    pre = {"review": "İNCELEME ", "floor": "TABAN "}.get(v["state"], "")
    if v["state"] in ("uninitialized", "invalid"):
        return f"{bot}: Kademe: {'sermaye kaydı yok' if v['state'] == 'uninitialized' else 'günlük bozuk'}"
    n = (v.get("counters") or {}).get("total_trades")
    return (f"{bot}: {pre}Kademe: {v['step_name']} %{_tr(v['step_risk'] * 100)} | özsermaye {_tr(v['equity'])} | "
            f"taban {_tr(v['base'])} (düşüş %{_tr(v['dd_base_pct'], 1)}) | durma {_tr(v['stop_at'])} | "
            f"son taban {_tr(v['floor_at'])} | işlem {n if n is not None else '?'}")


class TelegramDaemon:
    def __init__(self, cfg: TelegramConfig, client: TelegramClient, *, now_fn: Callable[[], datetime] | None = None,
                 runner: Callable | None = None, killswitch=None, report_fn: Callable[[], str] | None = None,
                 sleep: Callable[[float], None] = time.sleep, random_code: Callable[[], str] | None = None,
                 pauses: Mapping[str, Any] | None = None, ladders: Mapping[str, LadderFiles] | None = None,
                 expect_status_mode: str | None = None):
        self.cfg, self.client = cfg, client
        self.expect_status_mode = expect_status_mode     # DD-9 §7: canli bot varken durum dosyasi `live` olmali (kagit dosyada KILL kalkmaz)
        self.now = now_fn or (lambda: datetime.now(UTC))
        if runner is None:
            raise ValueError("runner zorunlu (alt surec cagrisi scripts/telegram_run.py'de)")
        self.runner = runner
        self.report_fn = report_fn
        self.sleep = sleep
        self.base = Path(cfg.var_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.outbox = Outbox(self.base, self.now)
        self.killswitch = killswitch          # motorun Killswitch'i disaridan verilir (scripts/telegram_run.py)
        # bot -> EntryPause (active/holds/add/remove); yalniz scripts/telegram_run.py enjekte eder; yedek gerceklenim YOK (11 §9.5)
        self.pauses = dict(pauses) if pauses else None
        self.ladders = dict(ladders) if ladders else None       # 12 §9: bot -> LadderFiles (yalniz scripts/telegram_run.py enjekte eder)
        self.start_ts = self.now().timestamp()
        self._seen: set[int] = set()
        self._rand = random_code or (lambda: "%04d" % secrets.randbelow(10000))
        self._unauth: list[float] = []
        self._unauth_warned_at = 0.0
        self.kill_watch: float | None = None
        self._load_seen()

    # -- dosyalar -----------------------------------------------------------
    @property
    def _offset_p(self):
        return self.base / "offset.json"

    @property
    def _pending_p(self):
        return self.base / "pending.json"

    @property
    def _audit_p(self):
        return self.base / "audit.jsonl"

    def _audit(self, event: str, **kw) -> None:
        row = {"ts": LS.fmt_ts(self.now()), "event": event, **kw}
        try:
            with open(self._audit_p, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("audit yazilamadi: %s", type(e).__name__)

    def _load_seen(self) -> None:
        try:
            for ln in self._audit_p.read_text(encoding="utf-8").splitlines()[-1000:]:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("event") == "exec" and isinstance(r.get("update_id"), int):
                    self._seen.add(r["update_id"])
        except OSError:
            pass

    def _get_offset(self) -> int | None:
        try:
            return int(json.loads(self._offset_p.read_text())["offset"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _set_offset(self, uid: int) -> None:
        try:
            atomic_write_json(self._offset_p, {"offset": uid + 1})
        except Exception as e:  # noqa: BLE001
            log.warning("offset yazilamadi: %s", type(e).__name__)

    def _read_pending(self) -> dict | None:
        try:
            d = json.loads(self._pending_p.read_text())
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None

    def _clear_pending(self) -> None:
        self._pending_p.unlink(missing_ok=True)

    def _read_status(self) -> dict | None:
        try:
            d = json.loads(Path(self.cfg.status_path).read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    # -- yetki --------------------------------------------------------------
    def _authorized(self, chat: Mapping, frm: Mapping) -> bool:
        return (chat.get("type") == "private" and chat.get("id") == self.cfg.chat_id
                and frm.get("id") == chat.get("id") and not frm.get("is_bot"))

    def _reply(self, text: str, severity: str = "WARN") -> None:
        try:
            self.client.send_message(self.cfg.chat_id, fit_text(text), disable_notification=severity == "INFO")
        except Exception as e:  # noqa: BLE001
            log.warning("yanit gonderilemedi: %s", mask(type(e).__name__, self.cfg.token))

    # -- ana islem ----------------------------------------------------------
    def process_updates(self, updates: list) -> None:
        for u in updates:
            uid = u.get("update_id")
            if not isinstance(uid, int):
                continue
            if uid not in self._seen:
                try:
                    self._handle(u)
                except Exception as e:  # noqa: BLE001
                    log.error("komut hatasi: %s", mask(type(e).__name__, self.cfg.token))
                self._seen.add(uid)
            self._set_offset(uid)

    def _handle(self, u: dict) -> None:
        uid = u["update_id"]
        if "callback_query" in u:
            return self._handle_callback(uid, u["callback_query"])
        m = u.get("message")
        if not isinstance(m, dict):
            return                                        # edited_message vb.: yok say
        chat, frm = m.get("chat") or {}, m.get("from") or {}
        if not self._authorized(chat, frm):
            return self._unauthorized(uid, chat.get("id"), m.get("text"))
        text = m.get("text") or ""
        age = self.now().timestamp() - float(m.get("date", 0))
        if age > STALE_S or float(m.get("date", 0)) < self.start_ts:
            self._audit("exec", update_id=uid, cmd=text[:20], sonuc="stale")
            return self._reply(f"islenmedi, yeniden gonder (yas: {int(age)} sn)")
        result = self._dispatch_text(text, tail3(frm.get("id")))
        self._audit("exec", update_id=uid, cmd=text[:20] if not CODE_RE.match(text.strip()) else "<kod>",
                    sonuc=result)

    def _unauthorized(self, uid: int, chat_id: Any, text: Any) -> None:
        self._seen.add(uid)
        self._audit("unauthorized", update_id=uid, chat_tail=tail3(chat_id), cmd=str(text or "")[:20])
        now = self.now().timestamp()
        self._unauth = [t for t in self._unauth if now - t < 60] + [now]
        if len(self._unauth) > 10 and now - self._unauth_warned_at > 600:
            self._unauth_warned_at = now
            self._reply("yetkisiz komut denemesi")

    def _dispatch_text(self, text: str, who: str) -> str:
        t = text.strip()
        if CODE_RE.match(t):
            return self._on_code(t, who)
        n = _norm_cmd_text(t)
        if n == "hepsini kapat":
            return self._cmd_kill_start()
        parts = t.split()
        if not parts or not parts[0].startswith("/"):
            self._reply("anlasilmadi. " + HELP)
            return "unknown"
        cmd = parts[0].lower().split("@")[0]
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "/yardim" or cmd == "/start":
            self._reply(HELP, "INFO")
            return "ok"
        if cmd == "/durum":
            return self._cmd_status()
        if cmd == "/rapor":
            if self.report_fn is None:
                self._reply("rapor yapilandirilmadi")
                return "noreport"
            self._reply(self.report_fn() + "\n(manuel)", "INFO")
            return "ok"
        if cmd == "/kurulumlar":
            return self._cmd_info(lambda: kurulumlar_metni(self.cfg, self.now()))
        if cmd == "/ders":
            return self._cmd_info(lambda: ders_durum_metni(self.cfg, self.now()))
        if cmd == "/hepsini_kapat":
            return self._cmd_kill_start()
        if cmd == "/devam":
            return self._cmd_devam_start()
        if cmd == "/durdur":
            return self._cmd_durdur_start()
        if cmd == "/kademe":
            return self._cmd_kademe()
        if cmd == "/kademe_devam":
            return self._cmd_kademe_devam_start()
        if cmd == "/karantina_kaldir":
            return self._cmd_karantina_start(arg)
        if cmd in ("/onayla", "/reddet"):
            return self._lesson(arg, cmd == "/onayla")
        self._reply("bilinmeyen komut. " + HELP)
        return "unknown"

    def _cmd_info(self, fn) -> str:
        """Salt okunur bilgi komutu (/kurulumlar, /ders): okunamayan veri tek satırla bildirilir."""
        try:
            text = fn()
        except SectionError as e:
            self._reply(f"okunamadı: {e.code}", "INFO")
            return "unreadable"
        self._reply(text, "INFO")
        return "ok"

    # -- durum --------------------------------------------------------------
    def _cmd_status(self) -> str:
        st = self._read_status()
        if not st:
            self._reply("durum okunamadı")
            return "unreadable"
        eq = st.get("equity")
        try:
            dk = int((self.now() - parse_ts_z(st["loop_at"])).total_seconds() // 60)
        except Exception:  # noqa: BLE001
            dk = None
        lines = [f"📊 Anlık durum ({KIP_TR.get(str(st.get('mode')), 'kip bilinmiyor')})", AYRAC]
        if _num_ok(eq):
            lines.append(f"💰 Özsermaye: {tr_sayi(eq)} $")
        lines.append(f"📌 Açık pozisyon: {len(st.get('open_positions') or [])}")
        lines += _risk_satirlari(st) if not (dk is not None and dk >= 2) else \
            [f"🚨 Motor yanıt vermiyor! (son sinyal {dk} dk önce)"]
        if dk is not None and dk < 2:
            lines.append("🕒 Motor canlı")
        lines += self._pause_lines()
        lines += self._ladder_lines()
        self._reply("\n".join(lines), "INFO")
        return "ok"

    # -- duraklatma (11 §9) ---------------------------------------------------
    def _pause_state(self) -> dict[str, list]:
        return pause_state(self.pauses)

    def _pause_lines(self) -> list[str]:
        return [] if self.pauses is None else pause_lines(self.pauses)

    def _remaining_lines(self) -> str:
        st = self._pause_state()
        lines = []
        for bot in (self.pauses or {}):
            if bot in st:
                rs = ", ".join(h.reason for h in st[bot]) or "okunamadi"
                acik = ", ".join(dict.fromkeys(neden_tr(h.reason) for h in st[bot]))
                lines.append(f"{bot}: {rs} — girişler hâlâ kapalı" + (f" ({acik})" if acik else ""))
            else:
                lines.append(f"{bot}: girişler açık")
        return "\n".join(lines)

    def _cmd_durdur_start(self) -> str:
        if not self.pauses:
            self._reply("desteklenmiyor, tam kapatma icin /hepsini_kapat")
            return "unsupported"
        st = self._pause_state()
        have = {b: next((h for h in hs if h.reason == PAUSE_USER), None) for b, hs in st.items()}
        if all(have.get(b) is not None for b in self.pauses):
            who = "; ".join(f"{b}: {h.by}, {h.at}" for b, h in have.items() if h is not None)
            self._reply(f"Girişler zaten durdurulmuş ({who})")
            return "already"
        code = self._new_pending("pause")
        self._reply("Yeni giris durdurulacak; acik pozisyonlar zarar durdurlariyla acik kalir. Onay icin "
                    f"{CODE_TTL_S} sn icinde yalniz su 4 haneli kodu yanitla: {code}")
        return "code_sent"

    def _pause_devam_refusal(self) -> str | None:
        """KILL yokken /devam: kaldirilabilecek user_cmd tutusu var mi (None = var)."""
        st = self._pause_state()
        if any(h.reason in PAUSE_LIFTABLE for hs in st.values() for h in hs):
            return None
        others = sorted({h.reason for hs in st.values() for h in hs})
        if st and not others:
            others = ["unreadable"]
        if others:
            extra = (" (Son taban: sunucuda, yazılı kararla kaldırılır)" if "capital_floor" in others
                     else " (kademe inceleme akışıyla ya da sunucuda operatör tarafından kaldırılır)"
                     if "drawdown_review" in others else "; yalnız sunucuda kaldırılır")
            return f"Bu durdurma Telegram'dan kaldırılamaz: {', '.join(others)} ({'; '.join(dict.fromkeys(neden_tr(o) for o in others))}){extra}"
        return "KILL etkin degil"

    def _devam_layer(self) -> tuple[str, str | None]:
        """-> (katman, ret nedeni). Cagri basina tek katman: once KILL, sonra user_cmd duraklatmasi."""
        if self.killswitch is not None and self.killswitch.active():
            return "kill", self._devam_refusal()
        if self.pauses:
            return "pause", self._pause_devam_refusal()
        return "kill", self._devam_refusal()

    # -- risk kademesi (12 §9) ---------------------------------------------------
    def _ladder_views(self) -> dict[str, dict]:
        now = self.now()
        return {b: ladder_view(lf, now) for b, lf in (self.ladders or {}).items()}

    def _ladder_lines(self) -> list[str]:
        if not self.ladders:
            return []
        return [ladder_line(b, v) for b, v in self._ladder_views().items()]

    def _cmd_kademe(self) -> str:
        if not self.ladders:
            self._reply("kademe denetimi yapılandırılmadı", "INFO")
            return "noconfig"
        lines = []
        for b, v in self._ladder_views().items():
            if v["state"] in ("uninitialized", "invalid"):
                lines.append(f"{b}: {'sermaye kaydı yok' if v['state'] == 'uninitialized' else 'kademe günlüğü bozuk'}")
                continue
            dur = {"ok": "ok", "review": "inceleme", "floor": "taban"}[v["state"]]
            c = v.get("counters") or {}
            ln = [f"{b}: basamak {v['step_name']} (risk %{_tr(v['step_risk'] * 100)}) | durum {dur}",
                  f"  yatırılan {_tr(v['dep_net'])} | taban {_tr(v['base'])} | tepe {_tr(v['peak'])} | "
                  f"özsermaye {_tr(v['equity'])}",
                  f"  düşüş: tabandan %{_tr(v['dd_base_pct'], 1)}, tepeden %{_tr(v['dd_peak_pct'], 1)}",
                  f"  durma seviyesi {_tr(v['stop_at'])} USD | son taban {_tr(v['floor_at'])} USD"]
            if v.get("gate_code"):
                ln.append(f"  kapı: {v['gate_code']} ({neden_tr(v['gate_code'])})")
            if c:
                ln.append(f"  işlem {c.get('total_trades')} | basamakta {c.get('step_trades')} işlem / "
                          f"{c.get('step_days')} gün | ort. R {_tr(c.get('step_mean_r'))} | ardışık zarar "
                          f"{c.get('consec_losses')} | son30 R {_tr(c.get('last30_sum_r'))}")
            if v["stale"]:
                ln.append("  (motor durumu bayat: değerler günlükten; özsermaye bilinmiyor)")
            lines.append("\n".join(ln))
        self._reply("\n".join(lines), "INFO")
        return "ok"

    def _ladder_candidates(self) -> list[tuple[str, LadderFiles, Any]]:
        """review durumundaki botlar (ya da durum ok iken drawdown_review tutusu kalmis olanlar)."""
        out = []
        for b, lf in (self.ladders or {}).items():
            try:
                st = lf.log.state()
            except Exception:  # noqa: BLE001
                continue
            if st is None:
                continue
            if st.status == "review":
                out.append((b, lf, st))
            elif st.status == "ok":
                try:
                    if any(h.reason == "drawdown_review" for h in lf.pause.holds()):
                        out.append((b, lf, st))
                except Exception:  # noqa: BLE001
                    continue
        return out

    def _ladder_resume_refusal(self) -> tuple[str | None, list]:
        """12 §9 /kademe_devam ret kosullari (ilk tutan). -> (ret metni | None, [(bot, lf, st, view)])."""
        if not self.ladders:
            return "kademe denetimi yapılandırılmadı", []
        cands = self._ladder_candidates()
        if not cands:
            for b, lf in self.ladders.items():
                try:
                    st = lf.log.state()
                except Exception:  # noqa: BLE001
                    continue
                if st is not None and st.status == "floor":
                    return "Son taban: Telegram'dan açılamaz; yazılı karar + sunucu gerekir", []
            return "Bekleyen kademe incelemesi yok", []
        if self.killswitch is not None and self.killswitch.active():
            return "Önce KILL: /devam", []
        now = self.now()
        out = []
        for b, lf, st in cands:
            v = ladder_view(lf, now)
            if st.status == "review" and st.stopped_at is not None:
                wait = RL.RESUME_MIN_WAIT_S - (now - st.stopped_at).total_seconds()
                if wait > 0:
                    at = (st.stopped_at + timedelta(seconds=RL.RESUME_MIN_WAIT_S)).astimezone(TR)
                    return f"En erken {at.strftime('%d.%m.%Y %H:%M')} (kalan {math.ceil(wait / 3600)} saat)", []
            if not v["loop_ok"] or not v.get("block_ok"):          # RK-1 fix 5: blok yok / gunlukle uyusmuyor
                return "Motor durumu okunamıyor; sunucuda `ladder resume`", []
            if v.get("gate_code"):
                return f"Önce sermaye kaydı sorunu çözülmeli: {v['gate_code']} ({neden_tr(v['gate_code'])})", []
            out.append((b, lf, st, v))
        return None, out

    def _cmd_kademe_devam_start(self) -> str:
        why, items = self._ladder_resume_refusal()
        if why:
            self._reply(why)
            return "refused"
        code = self._new_pending("ladder_resume")
        parts = []
        for b, lf, st, v in items:
            e = v["equity"]
            nb = min(st.base, e) if st.status == "review" else st.base
            step = min(st.step, 0) if st.status == "review" else st.step
            parts.append(f"{b}: yeni taban {_tr(nb)} USD, yeni durma seviyesi {_tr(RL.STOP_RATIO * nb)} USD, "
                         f"basamak {RL.STEP_NAMES[step]}, son taban {_tr(RL.FLOOR_RATIO * st.dep_net)} USD")
        self._reply("Onaylarsan: " + "; ".join(parts) + f". Onay icin {CODE_TTL_S} sn icinde yalniz su 4 haneli kodu "
                    f"yanitla: {code}")
        return "code_sent"

    def _ladder_resume_apply(self, who: str) -> str:
        why, items = self._ladder_resume_refusal()           # kod aninda yeniden denetlenir
        if why:
            self._reply(why)
            return "refused"
        by = f"telegram:{who}"
        now = self.now()
        notes, crit = [], False
        for b, lf, st, v in items:
            if st.status == "review":
                try:
                    lf.log.append("review_resume", by, now, equity=float(v["equity"]), rebase=True, decision="")
                except Exception as e:  # noqa: BLE001 - satir yazilamadi: tutus KALDIRILMAZ
                    log.error("review_resume yazilamadi: %s", type(e).__name__)
                    notes.append(f"{b}: kademe satırı YAZILAMADI ({type(e).__name__}); tutuş kaldırılmadı; sunucuda "
                                 "`ladder resume`")
                    crit = True
                    continue
            try:
                lf.pause.remove("drawdown_review", by)
            except Exception as e:  # noqa: BLE001
                log.error("drawdown_review kaldirilamadi: %s", type(e).__name__)
                notes.append(f"{b}: kademe satırı yazıldı ama tutuş KALDIRILAMADI ({type(e).__name__}); komutu yineleyin "
                             "(yalnız tutuş kaldırılır)")
                crit = True
                continue
            notes.append(f"{b}: kademe incelemesi kapandı; yeni taban {_tr(min(st.base, v['equity']))} USD")
        rem = []
        for b, lf, *_ in items:
            try:
                rs = ", ".join(h.reason for h in lf.pause.holds())
            except Exception:  # noqa: BLE001
                rs = "okunamadi"
            rem.append(f"{b}: {rs + ' — girişler hâlâ kapalı' if rs else 'girişler açık'}")
        self._reply("\n".join(notes + rem), "CRIT" if crit else "WARN")
        return "ladder_partial" if crit else "ladder_resumed"

    # -- iki adimli kod -----------------------------------------------------
    def _new_pending(self, action: str, **extra) -> str:
        code = self._rand()
        salt = secrets.token_hex(8)
        now = self.now().timestamp()
        atomic_write_json(self._pending_p, {
            "token_hash": hashlib.sha256((salt + code).encode()).hexdigest(), "salt": salt, "action": action,
            "chat_id": self.cfg.chat_id, "created_at": now, "expires_at": now + CODE_TTL_S, **extra})
        return code

    # -- kurulum karantinasi (4b; motor `dayaniklilik.karantina` yazar, istegi motor isler)
    def _karantina_rows(self) -> list[dict]:
        st = self._read_status() or {}
        rows = (st.get("dayaniklilik") or {}).get("karantina") or []
        return [r for r in rows if isinstance(r, dict) and r.get("durum") == "aktif"]

    def _cmd_karantina_start(self, arg: str) -> str:
        rows = self._karantina_rows()
        if not rows:
            self._reply("karantinada kurulum yok", "INFO")
            return "none"
        names = ", ".join(str(r.get("birim")) for r in rows)
        t = arg.strip().lower()
        if not t:
            self._reply(f"Karantinada: {names}. Kullanim: /karantina_kaldir <kurulum | hepsi>", "INFO")
            return "usage"
        ok = t == "hepsi" or any(t == str(r.get("birim", "")).lower() or t in [str(a).lower() for a in r.get("kollar") or []]
                                 for r in rows)
        if not ok:
            self._reply(f"eslesen karantina yok ({names})")
            return "refused"
        code = self._new_pending("karantina", target=t)
        self._reply(f"{t}: karantina kaldirilacak, kurulum yeniden denenir (yine kod hatasi verirse hemen tekrar karantina). "
                    f"Onay icin {CODE_TTL_S} sn icinde yalniz su 4 haneli kodu yanitla: {code}")
        return "code_sent"

    def _cmd_kill_start(self) -> str:
        if self.killswitch is None:
            self._reply("kill dosyasi yapilandirilmadi")
            return "noconfig"
        if self.killswitch.active():
            info = self.killswitch.info() or {}
            self._reply(f"KILL zaten etkin ({info.get('by')}, {info.get('at')})")
            return "already"
        code = self._new_pending("kill")
        self._reply("Tum pozisyonlar piyasadan kapatilacak ve yeni giris durdurulacak. Onay icin "
                    f"{CODE_TTL_S} sn icinde yalniz su 4 haneli kodu yanitla: {code}")
        return "code_sent"

    def _devam_refusal(self) -> str | None:
        if self.killswitch is None:
            return "kill dosyasi yapilandirilmadi"
        if not self.killswitch.active():
            return "KILL etkin degil"
        st = self._read_status()
        if st is None:
            return "durum okunamadı, reddedildi"
        if self.expect_status_mode is not None and st.get("mode") != self.expect_status_mode:
            return "durum dosyası beklenen kipte değil, reddedildi"
        ks = st.get("kill_state")
        if ks == "exiting":
            return "kapanis suruyor, bekleyin"
        if st.get("mode") not in ("paper", "backtest"):       # canli ya da bilinmeyen
            info = self.killswitch.info() or {}
            if not (str(info.get("by", "")).startswith("telegram:") and info.get("reason") == "user_cmd"):
                return "Bu KILL Telegram'dan kurulmadi; yalniz sunucuda kaldirilir"
        if ks != "flat":                                      # DD-9 §7 (O7): HER kipte (paper dahil); eksik/yanlis tip = flat degil
            return "pozisyonlar kapanmadi (durum flat degil), reddedildi"
        return None

    def _cmd_devam_start(self) -> str:
        layer, why = self._devam_layer()
        if why:
            self._reply(why)
            return "refused"
        code = self._new_pending("devam", layer=layer)
        if layer == "kill":
            extra = ""
            if self.pauses and self._pause_state():
                extra = " Girisleri durduran duraklatma ayrica suruyor; o icin KILL kalkinca /devam'i yeniden gonder."
            self._reply(f"KILL kaldirilacak ve girisler yeniden acilabilir. {CODE_TTL_S} sn icinde yalniz su 4 haneli "
                        f"kodu yanitla: {code}.{extra}")
        else:
            self._reply(f"/durdur ile konan duraklatma ya da ana para kilidi kaldirilacak. {CODE_TTL_S} sn icinde yalniz su 4 haneli "
                        f"kodu yanitla: {code}")
        return "code_sent"

    def _on_code(self, code: str, who: str) -> str:
        p = self._read_pending()
        if not p or p.get("chat_id") != self.cfg.chat_id:
            self._reply("bekleyen onay yok")
            return "no_pending"
        self._clear_pending()                                 # tek kullanimlik / tek deneme
        if self.now().timestamp() > float(p.get("expires_at", 0)):
            self._reply("sure doldu, yeniden baslat")
            return "expired"
        want = hashlib.sha256((p["salt"] + code).encode()).hexdigest()
        if not hmac.compare_digest(want, p["token_hash"]):
            self._reply("yanlis kod, iptal edildi")
            return "wrong_code"
        if p["action"] == "ladder_resume":
            return self._ladder_resume_apply(who)
        if p["action"] == "karantina":
            try:                                              # motor ayni dizinde okur (trader_engine.arm_quarantine.RELEASE_FILE)
                atomic_write_json(Path(self.cfg.status_path).parent / "arm_quarantine_release.json",
                                  {"hedef": str(p.get("target") or ""), "zaman": LS.fmt_ts(self.now()), "kaynak": f"telegram:{who}"})
            except Exception as e:  # noqa: BLE001
                log.error("karantina istegi yazilamadi: %s", type(e).__name__)
                self._reply(f"karantina kaldirma istegi YAZILAMADI ({type(e).__name__}); sunucuda `arm-quarantine release`", "CRIT")
                return "karantina_failed"
            self._reply("Karantina kaldirma istegi yazildi; motor bir dakika icinde isler.", "WARN")
            return "karantina_release"
        if p["action"] == "kill":
            self.killswitch.set(by=f"telegram:{who}", reason="user_cmd")
            self.kill_watch = self.now().timestamp()
            self._reply("KILL kuruldu; motor pozisyonlari kapatiyor")
            return "kill_set"
        if p["action"] == "pause" and self.pauses:
            problems = []
            for bot, ps in self.pauses.items():
                try:
                    if ps.add(PAUSE_USER, f"telegram:{who}"):
                        continue
                    hs = ps.holds()
                    if any(h.reason == PAUSE_USER for h in hs):
                        continue                              # zaten var (idempotent)
                    problems.append(f"{bot}: duraklatma dosyası okunamıyor/bozuk; girişler kapalı (fail-closed) ama "
                                    "user_cmd tutuşu kaydedilemedi; sunucuda bakılmalı")
                except Exception as e:  # noqa: BLE001 - onayli kodun ardindan sessiz kalinmaz
                    log.error("pause add basarisiz: %s %s", bot, type(e).__name__)
                    problems.append(f"{bot}: duraklatma YAZILAMADI ({type(e).__name__}); sunucuda kontrol edin")
            msg = ("Yeni giriş durduruldu. Açık pozisyonlar zarar durdurlarıyla açık kalır. "
                   "Hepsini kapatmak için /hepsini_kapat.")
            if problems:
                msg = "Duraklatma kısmen uygulandı/uygulanamadı:\n" + "\n".join(problems) + "\n" + msg
            self._reply(msg, "CRIT" if problems else "WARN")
            return "pause_partial" if problems else "paused"
        if p["action"] == "devam":
            layer = p.get("layer", "kill")
            if layer == "pause" and self.pauses:
                if self.killswitch is not None and self.killswitch.active():
                    self._reply("KILL etkin; önce KILL akışı: /devam ile KILL kaldırılır, duraklatma ondan sonra")
                    return "refused"
                why = self._pause_devam_refusal()
                if why:
                    self._reply(why)
                    return "refused"
                failed = []
                for bot, ps in self.pauses.items():
                    try:
                        ps.remove(PAUSE_USER, f"telegram:{who}")
                        ps.remove(PAUSE_LATCH, f"telegram:{who}")
                    except Exception as e:  # noqa: BLE001
                        log.error("pause remove basarisiz: %s %s", bot, type(e).__name__)
                        failed.append(f"{bot}: kaldırılamadı ({type(e).__name__})")
                head = "Duraklatma (user_cmd / ana para kilidi) kaldirildi." if not failed else \
                    "Duraklatma kısmen kaldırıldı:\n" + "\n".join(failed)
                self._reply(head + "\n" + self._remaining_lines(), "CRIT" if failed else "WARN")
                return "pause_partial" if failed else "pause_cleared"
            why = self._devam_refusal()
            if why:
                self._reply(why)
                return "refused"
            self.killswitch.clear()
            rem = ("\n" + self._remaining_lines()) if self.pauses else ""
            self._reply("KILL kaldirildi" + rem)
            return "kill_cleared"
        return "bad_action"

    def tick_kill_watch(self) -> None:
        if self.kill_watch is not None and self.now().timestamp() - self.kill_watch >= 300:
            self.kill_watch = None
            st = self._read_status()
            if st is None or st.get("kill_state") != "flat":
                self._reply("CRIT kapatma tamamlanmadi (kill_state flat degil)", "CRIT")

    # -- ders onayi (alt surec) ---------------------------------------------
    def _run_resolve(self, rid: str, approve: bool) -> dict:
        if not REQ_ID_RE.match(rid or ""):
            return {"status": "invalid", "message": "gecersiz id"}
        argv = [sys.executable, "-I", self.cfg.lesson_run, "--resolve", rid,
                "--approve" if approve else "--reject"]
        env = {k: v for k, v in os.environ.items() if k != "TELEGRAM_BOT_TOKEN"}
        rc, out = self.runner(argv, 60, env)
        try:
            d = json.loads((out or "").strip().splitlines()[-1])
            if not isinstance(d, dict):
                raise ValueError
        except (ValueError, IndexError):
            d = {"status": "error", "message": "çıktı okunamadı"}
        d["rc"] = rc
        return d

    def _lesson(self, rid: str, approve: bool) -> str:
        d = self._run_resolve(rid, approve)
        self._reply(f"ders onayi {rid[:40]}: {d.get('status')} {str(d.get('message', ''))[:200]}")
        return str(d.get("status"))

    def _handle_callback(self, uid: int, cq: dict) -> None:
        msg = cq.get("message") or {}
        chat, frm = msg.get("chat") or {}, cq.get("from") or {}
        cid = cq.get("id", "")
        if not self._authorized(chat, frm):
            return self._unauthorized(uid, chat.get("id"), cq.get("data"))
        data = str(cq.get("data") or "")
        parts = data.split(":")
        mid = msg.get("message_id")

        def ans(t: str = "") -> None:
            try:
                self.client.answer_callback_query(cid, t)
            except Exception as e:  # noqa: BLE001
                log.warning("answer_callback_query: %s", type(e).__name__)

        def edit(t: str, kb=None) -> None:
            try:
                self.client.edit_message_text(chat["id"], mid, fit_text(t), kb)
            except Exception as e:  # noqa: BLE001
                log.warning("edit_message_text: %s", type(e).__name__)

        if len(parts) != 3 or parts[0] not in ("ok", "no", "ev", "vz") or not REQ_ID_RE.match(parts[1]):
            ans("gecersiz")
            return self._audit("exec", update_id=uid, cmd="cb", sonuc="bad_data")
        act, rid = parts[0], parts[1]
        try:
            exp = float(parts[2])
        except ValueError:
            ans("gecersiz")
            return self._audit("exec", update_id=uid, cmd="cb", sonuc="bad_exp")
        orig = str(msg.get("text") or "")
        if exp <= self.now().timestamp():
            ans("suresi doldu")
            edit(orig.split("\n\nEmin misin?")[0] + "\n(suresi doldu)")
            return self._audit("exec", update_id=uid, cmd="cb:" + act, sonuc="expired")
        base = orig.split("\n\nEmin misin?")[0]
        if act == "ok":
            ans()
            kb = {"inline_keyboard": [[{"text": "Evet, onayla", "callback_data": f"ev:{rid}:{int(exp)}"},
                                       {"text": "Vazgec", "callback_data": f"vz:{rid}:{int(exp)}"}]]}
            edit(base + "\n\nEmin misin? Onaylarsan degisiklik uygulanir.", kb)
            res = "confirm_asked"
        elif act == "vz":
            ans("vazgecildi")
            kb = {"inline_keyboard": [[{"text": "Onayla", "callback_data": f"ok:{rid}:{int(exp)}"},
                                       {"text": "Reddet", "callback_data": f"no:{rid}:{int(exp)}"}]]}
            edit(base, kb)
            res = "cancelled"
        else:
            ans()
            d = self._run_resolve(rid, act == "ev")
            edit(f"{base}\n\nSonuc: {d.get('status')} {str(d.get('message', ''))[:200]}")
            res = str(d.get("status"))
        self._audit("exec", update_id=uid, cmd="cb:" + act, sonuc=res)

    # -- dongu --------------------------------------------------------------
    def write_alive(self) -> None:
        try:
            atomic_write_json(self.base / "alive.json", {"ts": LS.fmt_ts(self.now())})
        except Exception:  # noqa: BLE001
            pass

    def poll_once(self, timeout: int = 30) -> bool:
        """Bir tur: getUpdates + yurutme. Hata durumunda False (cagiran bekler)."""
        try:
            ups = self.client.get_updates(self._get_offset(), timeout)
        except TelegramError as e:
            if e.kind == "conflict":
                log.error("CRIT 409 conflict: baska poller")
            return False
        self.process_updates(ups)
        return True

    def run_forever(self, stop: Callable[[], bool] = lambda: False) -> None:
        backoff = 1.0
        last_drain = 0.0
        last_islem = 0.0
        while not stop():
            self.write_alive()
            ok = self.poll_once()
            self.tick_kill_watch()
            nowt = self.now().timestamp()
            if nowt - last_islem >= 60:                      # yeni islem / gunluk zarar mesajlari (en cok dakikada bir bakilir)
                last_islem = nowt
                try:
                    n = TelegramNotifier(self.client, self.cfg.chat_id, self.outbox, self.now, self.sleep)
                    n.status_path = self.cfg.status_path or None
                    islem_tick(self.cfg, n, self.now())
                    dayaniklilik_tick(self.cfg, n, self.now())
                except Exception as e:  # noqa: BLE001
                    log.warning("islem bildirimi: %s", type(e).__name__)
            if nowt - last_drain >= 30:
                last_drain = nowt
                try:
                    self.outbox.drain(self.client, self.cfg.chat_id, self.sleep)
                except Exception as e:  # noqa: BLE001
                    log.warning("outbox bosaltma: %s", type(e).__name__)
            if ok:
                backoff = 1.0
            else:
                self.sleep(backoff)
                backoff = min(60.0, backoff * 2)


# ---------------------------------------------------------------------------
# Gunluk rapor
# ---------------------------------------------------------------------------
def report_decision(now_utc: datetime, last_day: str | None) -> tuple[str, str]:
    """-> (karar, gun): karar normal | gecikmis | atla. Kesimi betik uygular (karar 7)."""
    n = now_utc.astimezone(TR)
    sched = n.replace(hour=21, minute=0, second=0, microsecond=0)
    if n < sched:
        sched -= timedelta(days=1)
    day = sched.date().isoformat()
    if last_day == day:
        return "atla", day
    delay = (n - sched).total_seconds()
    if delay <= 600:
        return "normal", day
    if delay <= 150 * 60:                    # 23:30'a kadar
        return "gecikmis", day
    return "atla", day


# ---------------------------------------------------------------------------------------------- sade Türkçe biçimler
AYRAC = "━━━━━━━━━━━━━━"
KIP_TR = {"paper": "deneme parası", "testnet": "test ağı", "live": "GERÇEK PARA"}
AY_TR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
BOT_TR = {"learner": "ana bot"}
GUNLUK_ZARAR_ORANI = 0.05                    # günlük zarar bütçesi (risk kilidiyle aynı %5)
BUTCE_GOSTER_ORANI = 0.5                     # yapay zekâ bütçesi satırı: sınırın en az yarısı harcanınca görünür

# Neden kodu -> düz Türkçe (duraklatma nedenleri + giriş kapısı kodları). Bilinmeyen kod ASLA ham yazılmaz.
NEDEN_TR = {
    "user_cmd": "senin /durdur komutun", "manual": "elle durduruldu", "kill": "acil durdurma (KILL) açık",
    "paused": "duraklatma var", "drawdown_review": "risk kademesi incelemesi bekliyor",
    "capital_floor": "sermaye tabanına inildi (yalnız sunucuda açılır)",
    "capital_latch": "Ana para kilidi (kasa ana paranın %15 altına indi)", "capital_missing": "sermaye kaydı yok",
    "ladder_invalid": "risk kademesi kaydı bozuk", "unknown_position": "borsada tanınmayan pozisyon bulundu",
    "late_fill": "geç gelen bir emir dolumu var", "exchange_ban": "borsa geçici engel koydu",
    "stop_failed_repeat": "24 saatte ikinci kez stop kurulamadı (yalnız sunucuda açılır)",
    "wallet_above_expected": "hesap bakiyesi izin verilen tavanı aştı (yalnız sunucuda açılır)",
    "exchange_auth": "borsa erişim anahtarı sorunlu", "exchange_unreachable": "borsaya ulaşılamıyor",
    "exchange_rate_limited": "borsa istek sınırına takıldı", "exchange_unknown_code": "borsadan beklenmedik yanıt geldi",
    "working_type_unverified": "borsa stop ayarı doğrulanamadı", "params_unavailable": "strateji ayarları yüklenemedi",
    "trigger_tf_changed": "zaman dilimi ayarı değişmiş", "degraded": "kayıt sistemi sorunlu",
    "stale_data": "piyasa verisi eski", "day_start_missing": "gün başı bakiyesi bilinmiyor",
    "clock_skew": "sunucu saati kaymış", "order_unknown": "sonucu belirsiz bir emir var",
    "exit_unknown": "sonucu belirsiz bir kapanış emri var", "reconcile": "borsayla kayıtlar uyuşmuyor",
    "unreadable": "duraklatma durumu okunamadı", "capital_mismatch": "sermaye kaydı borsadaki bakiyeyle uyuşmuyor",
    "capital_unverified": "sermaye kaydı doğrulanamadı", "equity_unreadable": "özsermaye okunamadı",
}
# Atlanan fırsat nedenleri (karar sayaçları `skip:<kod>`).
ATLAMA_TR = {
    "veto_missing": "veto hazır değildi", "veto_stale": "veto eskimişti", "veto_blocked": "veto izin vermedi",
    "stop_width": "stop çok genişti", "rr_below_min": "kazanç/risk oranı yetersizdi",
    "risk_denied": "risk kuralı izin vermedi", "entry_gate_closed": "yeni işlemler kapalıydı",
    "order_failed": "emir gönderilemedi", "ml_filter": "yapay zekâ filtresi eledi",
    "etiket_rejim": "rejim etiketi ters yöndeydi", "etiket_duygu": "piyasa duygusu uçtaydı ve ters yöndeydi",
    "etiket_kalabalik": "kalabalık aynı yöne yığılmıştı", "rules_missing": "borsa kuralı eksikti",
    "day_start_missing": "gün başı bakiyesi yoktu", "stale_data": "piyasa verisi eskiydi", "kill": "acil durdurma açıktı",
    "paused": "duraklatma vardı", "degraded": "kayıt sistemi hazır değildi", "params_unavailable": "ayarlar yüklenememişti",
    "trigger_tf_changed": "zaman dilimi ayarı değişmişti",
}
PARAM_TR = {"rr_min": "en düşük kazanç/risk oranı", "range_width_atr": "aralık genişliği sınırı",
            "vol_ratio_max": "oynaklık üst sınırı", "edge_zone_atr": "kenar bölgesi genişliği",
            "pullback_ema": "geri çekilme ortalaması", "stop_buffer_atr": "stop payı", "trail_atr": "iz süren stop mesafesi",
            "range_target_frac": "hedef oranı", "trigger_tf": "zaman dilimi",
            "exit_breakeven": "başa-baş stop kipi (0 kapalı, 1 açık)", "exit_partial": "kısmi kâr alma kipi (0 kapalı, 1 açık)"}


def tr_sayi(x: float, ondalik: int = 2) -> str:
    """1234.5 -> '1.234,50' (Türkçe gösterim)."""
    return f"{x:,.{ondalik}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tr_isaretli(x: float, ondalik: int = 2) -> str:
    """12.5 -> '+12,50'; -3 -> '−3,00'."""
    return ("+" if x >= 0 else "−") + tr_sayi(abs(x), ondalik)


def tr_yuzde(oran: float, ondalik: int = 2) -> str:
    """0.0125 -> '+%1,25'."""
    return ("+" if oran >= 0 else "−") + "%" + tr_sayi(abs(oran) * 100, ondalik)


def _usd(x: float) -> str:
    return tr_sayi(x, 0 if abs(x - round(x)) < 1e-9 else 2)


def _fiyat(x: Any) -> str:
    return TS.fiyat(x)                       # tek fiyat bicimi (tg_sade.fiyat)


def _gun_tr(day: str) -> str:
    try:
        d = datetime.fromisoformat(day)
        return f"{d.day} {AY_TR[d.month - 1]}"
    except (ValueError, TypeError):
        return str(day)


def neden_tr(kod: Any) -> str:
    """Duraklatma/kapı kodunu düz Türkçeye çevirir; bilinmeyen kod ham yazılmaz."""
    k = str(kod or "")
    if k == "ml_expired":
        return "modelin süresi doldu"
    if k == "ml_no_model":
        return "model yüklenemedi"
    if k.startswith("ml_"):
        return "yapay zekâ filtresi hazır değil"
    return NEDEN_TR.get(k, "bir güvenlik kuralı devrede")


def _kisi_tr(by: Any) -> str:
    b = str(by or "")
    return "Telegram'dan" if b.startswith("telegram") else "motor tarafından" if b.startswith("engine") else "sunucudan"


def _zaman_tr(at: Any) -> str:
    try:
        return parse_ts_z(str(at)).astimezone(TR).strftime("%d.%m %H:%M")
    except Exception:  # noqa: BLE001
        return ""


def _risk_satirlari(st: Mapping[str, Any], pause_text: str = "", gunluk_zarar_doldu: bool = False) -> list[str]:
    """Risk durumu: yeni işlem kapalıysa nedeni Türkçe söyler; yoksa 'her şey normal'."""
    if st.get("kill"):
        ks = "pozisyonlar kapatılıyor" if st.get("kill_state") == "exiting" else "yeni işlem açılmaz"
        return [f"🛑 Acil durdurma (KILL) açık: {ks}"]
    out: list[str] = []
    if pause_text:
        out.append(pause_text)
    if gunluk_zarar_doldu:
        out.append("🛑 Günlük zarar sınırına ulaşıldı: yeni işlemler bugün kapalı")
    if out:
        return out
    if st.get("entries_open") is False:
        kod = st.get("entries_blocked_reason") or (st.get("gate") or {}).get("code")
        if kod in (None, "ok"):
            return ["🛑 Yeni işlemler kapalı"]
        return [f"🛑 Yeni işlemler kapalı: {neden_tr(kod)}"]
    if st.get("entries_open") is True:
        return ["🛡️ Her şey normal, yeni işlemler açık"]
    return []


def _aktivite_satirlari(st: Mapping[str, Any]) -> list[str]:
    c = st.get("counters") or {}
    if not isinstance(c, Mapping) or "steps" not in c:
        return []
    ac = c.get("trades_opened", c.get("entries", c.get("enter", 0)))
    out = [f"🔎 Bot açıldığından beri {int(c.get('steps') or 0)} kez piyasaya bakıldı, {int(c.get('decisions') or 0)} fırsat değerlendirildi, "
           f"{int(ac or 0)} işlem açıldı"]
    atlanan = sorted(((k[5:], v) for k, v in c.items() if k.startswith("skip:") and v and k[5:] in ATLAMA_TR),
                     key=lambda kv: -kv[1])[:3]
    if atlanan:
        out.append("↳ Atlananlar: " + ", ".join(f"{int(v)} {ATLAMA_TR[k]}" for k, v in atlanan))
    return out


def _pozisyon_satirlari(st: Mapping[str, Any]) -> list[str]:
    pos = st.get("open_positions") or []
    if not pos:
        return ["📌 Açık pozisyon yok"]
    out = [f"📌 Açık pozisyonlar ({len(pos)}):"]
    for p in pos[:6]:
        uzun = str(p.get("side")).lower() in ("long", "buy", "b")
        out.append(f"{'🟩' if uzun else '🟥'} {p.get('pair')} · {'uzun' if uzun else 'kısa'} · giriş {_fiyat(p.get('entry_price'))}"
                   f" · stop {_fiyat(p.get('stop'))}")
    if len(pos) > 6:
        out.append(f"… ve {len(pos) - 6} pozisyon daha")
    return out


def _kasa_satiri(eq: Any, dse: Any) -> str | None:
    if not _num_ok(eq):
        return None
    return f"💰 Kasa: {tr_sayi(eq)} $" + (f" (gün başı {tr_sayi(dse)} $)" if _num_ok(dse) else "")


_BOLUM_SIRASI = ("Model", "Davranış", "Risk kademesi", "Bütçe", "Ders", "Öğrenme", "Kurulum karnesi",
                 "Alınmayan sinyaller (son 7 gün)")


def _durum_satiri(st: Mapping[str, Any] | None, pause_text: str, doldu: bool) -> str:
    if st is None:
        return "Bot durumu okunamadı."
    if st.get("kill"):
        return "Acil durdurma açık: yeni işlem açılmaz."
    if doldu:
        return "Günlük zarar sınırı doldu: bugün yeni işlem açılmaz."
    if pause_text:
        return "Yeni işlemler duraklatıldı."
    if st.get("entries_open") is False:
        return "Yeni işlemler kapalı."
    if st.get("entries_open") is True:
        return "Yeni işlemler açık."
    return ""


def _ders_gunluk(cfg: TelegramConfig, day: str) -> tuple[int, int] | None:
    """Istanbul gununde ders tarafindan uygulanan / geri alinan (fren haric) degisiklik sayisi; okunamazsa None."""
    from . import ledger as L  # noqa: PLC0415
    if not cfg.ledger_path or not Path(cfg.ledger_path).exists():
        return None
    try:
        a, b = _istanbul_day_bounds_utc(day)
        led = L.open_ledger(cfg.ledger_path, "learner", create=False, read_only=True, migrate=False)
        try:
            acts = [x for x in led.list_activations() if x.actor == "lesson"]
        finally:
            led.close()
        gun = [x for x in acts if a <= LS.fmt_ts(x.activated_at) < b]
        brake = lambda x: str(x.reason or "").startswith(LS.BRAKE_REASON_PREFIX)  # noqa: E731
        return (sum(1 for x in gun if x.kind == "apply"),
                sum(1 for x in gun if x.kind == "rollback" and not brake(x)))
    except Exception as e:  # noqa: BLE001
        log.warning("rapor: ders sayisi okunamadı: %s", type(e).__name__)
        return None


def _model_ozet(st: Mapping[str, Any] | None) -> str:
    """status.json `ml` blogu -> tek sade satir (yok/kapali -> bos)."""
    ml = (st or {}).get("ml")
    if not isinstance(ml, Mapping) or ml.get("mode") not in ("shadow", "active"):
        return ""
    state = ml.get("state")
    if state == "ok":
        return "Model: güncel, işlemlere etkili" if ml.get("mode") == "active" else "Model: güncel, gölgede izliyor"
    if state in ("expired", "no_model"):
        return "Model süresi doldu, kararlar kuralla veriliyor" if state == "expired" else "Model yüklenemedi, kararlar kuralla veriliyor"
    return ""


def _kucultulen_kollar(cfg: TelegramConfig) -> str:
    """Kademeli kucultme (docs/motor/kademeli-kucultme-spec.md): boyutu kucultulen kollar tek satir; yok/okunamazsa bos."""
    try:
        from . import kol_kucultme as KK  # noqa: PLC0415
        from . import ledger as L  # noqa: PLC0415
        if not cfg.ledger_path or not Path(cfg.ledger_path).exists():
            return ""
        led = L.open_ledger(cfg.ledger_path, "learner", create=False, read_only=True, migrate=False)
        try:
            return KK.satir(KK.azaltilanlar(led.arm_results_all(KK.KAYIT_SAYISI)))
        finally:
            led.close()
    except Exception as e:  # noqa: BLE001 - istege bagli satir
        log.warning("rapor: kol kucultme okunamadi: %s", type(e).__name__)
        return ""


def build_report(cfg: TelegramConfig, now: datetime, day: str, sections: Mapping[str, Callable[[], str]] | None = None
                 ) -> str:
    """Günlük özet (en çok 12 satır, sade Türkçe). `sections` yalnız 'Duraklatma' için okunur; diğer bölümler panelde."""
    problems = 0
    st: dict | None = None
    try:
        st = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        age = (now - parse_ts_z(st["loop_at"])).total_seconds()
    except Exception as e:  # noqa: BLE001
        log.warning("rapor: motor durumu okunamadı: %s", type(e).__name__)
        st, age, problems = None, 0.0, problems + 1
    stale = st is not None and age > STALE_S
    mod = KIP_TR.get(str((st or {}).get("mode")), "")
    out: list[str] = []
    if stale:
        out.append(f"🔴 Bot yanıt vermiyor (son sinyal {int(age // 60)} dk önce)")
    out.append(f"🌙 Günlük özet · {_gun_tr(day)}" + (" · gerçek para" if mod == KIP_TR["live"] else ""))
    pause_text = ""
    try:
        pause_text = str((sections or {}).get("Duraklatma", lambda: "")() or "").strip()
    except Exception:  # noqa: BLE001
        pass
    closed: list = []
    try:
        closed, _ = _ledger_day(cfg.ledger_path, "learner", day)
    except Exception as e:  # noqa: BLE001
        log.warning("rapor: defter okunamadı: %s", type(e).__name__)
        problems += 1
    if closed:
        pnl, _r = _sum(closed)
        win = sum(1 for t in closed if (t.realized_pnl or 0) > 0)
        out.append(f"Bugün {len(closed)} işlem kapandı ({win} kâr, {len(closed) - win} zarar) · {TS.isaretli(pnl)} $")
    elif not problems:
        out.append("Bugün kapanan işlem yok.")
    eq, dse = (st or {}).get("equity"), (st or {}).get("day_start_equity")
    doldu = False
    if _num_ok(eq):
        out.append(f"Kasa: {TS.sayi(eq)} $" + (f" (gün başı {TS.sayi(dse)} $)" if _num_ok(dse) else ""))
        if _num_ok(dse) and dse > 0:
            kayip, lim = max(0.0, dse - eq), TS.limit_orani(cfg.config_dir, (st or {}).get("mode")) * dse
            doldu = kayip >= lim
            out.append(f"Günlük zarar sınırı: {TS.sayi(kayip)} $ / {TS.sayi(lim)} $ kullanıldı")
    pos = (st or {}).get("open_positions") or []
    if st is not None:
        out.append("Açık pozisyon yok." if not pos else f"Açık pozisyon: {len(pos)} (" + ", ".join(
            f"{TS.coin(p.get('pair'))} {TS.yon(p.get('side'))}" for p in pos[:4]) + (", …" if len(pos) > 4 else "") + ")")
    d = _durum_satiri(st, pause_text, doldu)
    if d and not stale:
        out.append(d)
    dg = _ders_gunluk(cfg, day)
    if dg is not None:
        out.append(f"Dersler: bugün {dg[0]} uygulandı, {dg[1]} geri alındı · işlemlere etkili")
    ml = _model_ozet(st)
    if ml:
        out.append(ml)
    kk = _kucultulen_kollar(cfg)
    if kk:
        out.append(kk)
    if cfg.health_state:
        try:
            ov = json.loads(Path(cfg.health_state).read_text(encoding="utf-8")).get("last_overall")
            if isinstance(ov, str) and ov != "OK":
                out.append("⚠️ Bir sistem kontrolü sorunlu; panoya bak.")
        except Exception as e:  # noqa: BLE001
            log.warning("rapor: sağlık durumu okunamadı: %s", type(e).__name__)
    if problems:
        out.append("⚠️ Bazı bilgiler okunamadı")
    return TS.etiketle("\n".join(out[:TS.MAX_SATIR_OZET]))


class SectionError(Exception):
    """Rapor bölümü okunamadı; `code` satıra yazılır."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _istanbul_day_bounds_utc(day: str) -> tuple[str, str]:
    d0 = datetime.fromisoformat(day).replace(tzinfo=TR)
    f = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")  # noqa: E731
    return f(d0), f(d0 + timedelta(days=1))


def _fnum(x: Any, nd: int = 2) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "?"


def _ledger_day(path: str, bot: str, day: str) -> tuple[list, list]:
    from . import ledger as L  # noqa: PLC0415
    if not path or not Path(path).exists():
        raise SectionError("defter_yok")
    try:
        led = L.open_ledger(path, bot, create=False, read_only=True, migrate=False)
    except Exception as e:  # noqa: BLE001
        raise SectionError(getattr(e, "code", None) or type(e).__name__) from None
    try:
        a, b = _istanbul_day_bounds_utc(day)
        closed = led._trades("exit_ts>=? AND exit_ts<?", [a, b], closed=True)
        return closed, led.list_open_trades()
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        led.close()


def _sum(trades: list) -> tuple[float, float]:
    return (sum(t.realized_pnl or 0.0 for t in trades), sum(t.r_multiple or 0.0 for t in trades))


def section_ledger(cfg: TelegramConfig, day: str) -> str:
    closed, opened = _ledger_day(cfg.ledger_path, "learner", day)
    pnl, r = _sum(closed)
    win = sum(1 for t in closed if (t.realized_pnl or 0) > 0)
    loss = sum(1 for t in closed if (t.realized_pnl or 0) <= 0)
    eq = dse = None
    try:
        st = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        eq, dse = st.get("equity"), st.get("day_start_equity")
    except Exception:  # noqa: BLE001
        pass
    lines = [f"öğrenen: kapanan={len(closed)} PnL={pnl:+.2f}$ R={r:+.2f} kazanan/kaybeden={win}/{loss} "
             f"açık={len(opened)}"]
    if dse:
        lim = TS.limit_orani(cfg.config_dir, None) * float(dse)
        lines.append(f"  equity={_fnum(eq)} gün_başı={_fnum(dse)} günlük zarar={max(0.0, -pnl):.2f}$ / "
                     f"bütçe %{TS.limit_orani(cfg.config_dir, None) * 100:g}={lim:.2f}$")
    else:
        lines.append(f"  equity={_fnum(eq)} gün_başı=? günlük zarar={max(0.0, -pnl):.2f}$ / bütçe %{TS.limit_orani(cfg.config_dir, None) * 100:g}=?")
    return "\n" + "\n".join(lines)


def section_budget_status(cfg: TelegramConfig):
    """Bütçe durumu (salt okunur); okunamazsa SectionError(kod)."""
    import dataclasses  # noqa: PLC0415
    from . import budget as B  # noqa: PLC0415
    try:
        bc = B.load_config(cfg.budget_config)
        db = Path(bc.db_path)
        if not db.is_absolute():
            db = Path(cfg.budget_config).resolve().parent.parent / db
        bc = dataclasses.replace(bc, db_path=str(db))
    except Exception:  # noqa: BLE001
        raise SectionError("yapilandirma_gecersiz") from None
    if not db.exists():
        raise SectionError("depo_yok")
    st = B.BudgetGuard(bc).status()
    if not st.config_ok:
        raise SectionError("yapilandirma_gecersiz")
    if not st.store_ok:
        raise SectionError("depo_okunamadi")
    return st


def section_budget(cfg: TelegramConfig) -> str:
    """Teknik (ham) bütçe satırı; panel eşdeğerlik testi için. Kullanıcı raporu `rapor_butce` kullanır."""
    st = section_budget_status(cfg)
    sv = st.services
    names = {"haftalik_ozet": "haftalık özet", "lesson": "ders"}
    parts = [f"{names.get(k, k)} {v.used_usd:.2f}$/{v.cap_usd:.2f}$ ({v.state})" for k, v in sv.items()]
    out = f"ay {st.month_used_usd:.2f}$/{st.monthly_cap_usd:.2f}$ ({st.month_state}); bugün: " + ", ".join(parts)
    if not st.prices_verified:
        out += "; fiyatlar doğrulanmadı"
    return out


def section_lesson(cfg: TelegramConfig, now: datetime) -> str:
    if not cfg.lesson_store or not Path(cfg.lesson_store).exists():
        raise SectionError("depo_yok")
    try:
        store = LS.LessonStore(cfg.lesson_store, read_only=True, create=False)
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    try:
        lines = []
        reqs = store.open_requests()
        if reqs:
            lines.append(f"  bekleyen öneri: {len(reqs)}")
            for r in reqs[:5]:
                try:
                    d = json.loads(r["request_json"])
                    summ = f"{d.get('param')} {d.get('from_value')}→{d.get('to_value')} ({d.get('scope')})"
                except Exception:  # noqa: BLE001
                    summ = f"öneri #{r.get('proposal_id')}"
                lines.append(f"  {r['request_id']}: {summ} -> /onayla {r['request_id']}")
            if len(reqs) > 5:
                lines.append(f"  +{len(reqs) - 5}")
        else:
            lines.append("  bekleyen öneri yok")
        sd, ed = store.get_state("shadow_start_day"), store.get_state("shadow_end_day")
        if sd:
            today = now.astimezone(TR).date()
            n = (today - datetime.fromisoformat(sd).date()).days + 1
            tot = (datetime.fromisoformat(ed).date() - datetime.fromisoformat(sd).date()).days if ed else "?"
            lines.append(f"  gölge dönem: gün {max(n, 0)}/{tot} (bitiş {ed})")
        else:
            lines.append("  gölge dönem: başlamadı")
        rows = store._q("SELECT id, run_day FROM lesson_runs ORDER BY id DESC LIMIT 1")
        if rows:
            ev = store.run_events(rows[0]["id"])
            last = ev[-1] if ev else None
            res = f"{last.status}{'/' + last.code if last and last.code else ''}" if last else "olay yok"
            lines.append(f"  son çalışma: {rows[0]['run_day']} {res}")
        else:
            lines.append("  son çalışma: yok")
        if rows:
            with contextlib.suppress(Exception):
                snap = store.get_snapshot(rows[0]["id"])
                if snap is not None and snap.counterfactual:
                    lines.append("  " + LS.counterfactual_line(snap.counterfactual))
                if snap is not None:                       # Revizyon 6: cikis karsi-olgusu (kanit yoksa "henuz hesaplanmadi")
                    lines.append("  " + LS.exit_cf_line(snap.cf_exit))
                    mline = LS.exit_modes_cf_line(snap.cf_exit)         # Revizyon 7: yalniz kip kaniti varken
                    if mline:
                        lines.append("  " + mline)
        return "\n" + "\n".join(lines)
    except SectionError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        store.close()


def section_counterfactual(cfg: TelegramConfig, now: datetime) -> str:
    """Alınmayan sinyaller (plan 25a): öğrenen için son 7 günde hesaplanmış varsayımsal sonuçlar (salt okunur)."""
    if not cfg.ledger_path:
        raise SectionError("defter_yok")
    path = Path(cfg.ledger_path).parent / "counterfactual.sqlite"
    if not path.exists():
        return "henüz hesaplanmadı"
    from . import counterfactual as CF  # noqa: PLC0415
    try:
        sm = CF.summary(path, "learner", now=now, days=7)
    except CF.CounterfactualError as e:
        raise SectionError(e.code) from None
    if not sm["n"]:
        return "0"
    top = sorted(sm["by_reason"].items(), key=lambda kv: (-kv[1]["n"], kv[0]))[:3]
    parts = "; ".join(f"{k}: {b['n']}, {b['mean_r_net']:+.2f}R" for k, b in top)
    return (f"{sm['n']} (varsayımsal net R, üst sınır; sonraki kapıları ve dolumları yok sayar, işlem yapılabilir kâr "
            f"değildir) — {parts}")


def rapor_defter(cfg: TelegramConfig, day: str) -> str:
    """Rapor satırları: bugünün sonucu, kasa, kapanan işlemler."""
    closed, _opened = _ledger_day(cfg.ledger_path, "learner", day)
    pnl, r = _sum(closed)
    win = sum(1 for t in closed if (t.realized_pnl or 0) > 0)
    loss = len(closed) - win
    eq = dse = None
    try:
        s = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        eq, dse = s.get("equity"), s.get("day_start_equity")
    except Exception:  # noqa: BLE001
        pass
    oran = f" ({tr_yuzde(pnl / dse)})" if _num_ok(dse) and dse > 0 else ""
    lines = [f"{'📈' if pnl >= 0 else '📉'} Bugün: {tr_isaretli(pnl)} ${oran}"]
    if (k := _kasa_satiri(eq, dse)):
        lines.append(k)
    lines.append(f"🧾 Bugün kapanan işlem: {len(closed)} · kazanan {win} / kaybeden {loss}"
                 + (f" · {tr_isaretli(r)} R" if closed else ""))
    return "\n".join(lines)


def rapor_butce(cfg: TelegramConfig) -> str:
    """Yapay zekâ bütçesi: yalnız bir sınırın en az yarısı harcanmışsa ya da aşılmışsa görünür."""
    try:
        s = section_budget_status(cfg)
    except SectionError as e:
        if e.code == "depo_yok":                             # henüz hiç harcama yok
            return ""
        raise
    lines = []
    ay, ay_sinir = s.month_used_usd, s.monthly_cap_usd
    if ay_sinir > 0 and ay >= BUTCE_GOSTER_ORANI * ay_sinir:
        lines.append(f"🤖 Yapay zekâ bütçesi: ayda {tr_sayi(ay)} $ / {_usd(ay_sinir)} $"
                     + (" — doldu, yeni istek yapılmaz" if ay >= ay_sinir else ""))
    for k, v in s.services.items():
        if v.cap_usd > 0 and v.used_usd >= BUTCE_GOSTER_ORANI * v.cap_usd:
            ad = {"haftalik_ozet": "haftalık özet", "lesson": "ders"}.get(k, "yapay zekâ")
            lines.append(f"🤖 Yapay zekâ bütçesi: bugün {ad} {tr_sayi(v.used_usd)} $ / {_usd(v.cap_usd)} $"
                         + (" — doldu" if v.used_usd >= v.cap_usd else ""))
    return "\n".join(lines)


def rapor_ders(cfg: TelegramConfig, now: datetime) -> str:
    """Ders: yalnız onay bekleyen gerçek bir öneri varsa görünür (depo yoksa hiç)."""
    if not cfg.lesson_store or not Path(cfg.lesson_store).exists():
        return ""
    try:
        store = LS.LessonStore(cfg.lesson_store, read_only=True, create=False)
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    try:
        reqs = store.open_requests()
        lines = []
        for r in reqs[:3]:
            try:
                d = json.loads(r["request_json"])
                ad = PARAM_TR.get(str(d.get("param")), "bir strateji ayarı")
                lines.append(f"🎓 Öneri onay bekliyor: {ad} {d.get('from_value')} → {d.get('to_value')}"
                             f" (onay için /onayla {r['request_id']})")
            except Exception:  # noqa: BLE001
                lines.append(f"🎓 Bir öneri onay bekliyor (onay için /onayla {r['request_id']})")
        if len(reqs) > 3:
            lines.append(f"… ve {len(reqs) - 3} öneri daha")
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        raise SectionError(type(e).__name__) from None
    finally:
        store.close()


def rapor_kacirilan(cfg: TelegramConfig, now: datetime) -> str:
    """Alınmayan sinyaller (son 7 gün): tek satır; hesap yoksa ya da boşsa görünmez."""
    if not cfg.ledger_path:
        return ""
    path = Path(cfg.ledger_path).parent / "counterfactual.sqlite"
    if not path.exists():
        return ""
    from . import counterfactual as CF  # noqa: PLC0415
    try:
        sm = CF.summary(path, "learner", now=now, days=7)
    except CF.CounterfactualError as e:
        raise SectionError(e.code) from None
    if not sm["n"] or sm["mean_r_net"] is None:
        return ""
    return (f"🔭 Son 7 günde alınmayan {sm['n']} sinyal varsayımla hesaplandı: ortalama {tr_isaretli(sm['mean_r_net'])} R "
            f"(gerçek kâr değil)")


def rapor_duraklatma(pauses: Mapping[str, Any]) -> str:
    """Yalnız duraklatılmış botlar için satır; hiç duraklatma yoksa boş."""
    return "\n".join(pause_lines(pauses, sadece_tutulan=True))


def _ml_kalan_tr(kalan_s: float) -> str:
    g = int(kalan_s // 86400)
    return f"{g} gün" if g >= 1 else f"{max(1, int(kalan_s // 3600))} saat"


def _ml_health_flags(cfg: TelegramConfig, bot: str) -> set[str]:
    """Sağlık state.json: ml_seen[bot].stale ve son turdaki ml_package:<bot> kodları. Okunamazsa boş küme (satır yine yazılır)."""
    flags: set[str] = set()
    if not cfg.health_state:
        return flags
    try:
        d = json.loads(Path(cfg.health_state).read_text(encoding="utf-8"))
        seen = (d.get("ml_seen") or {}).get(bot)
        if isinstance(seen, Mapping) and seen.get("stale") is True:
            flags.add("ml_stale_data")
        for fp in (d.get("fingerprints") or {}):
            name, _, code = str(fp).partition("|")
            if name == f"ml_package:{bot}":
                flags.add(code)
    except Exception as e:  # noqa: BLE001
        log.warning("rapor: model sağlık durumu okunamadı: %s", type(e).__name__)
    return flags


_ML_EK = (("ml_restart_needed", "yeni model hazır, motorun yeniden başlatılması gerekiyor"),
          ("ml_stale_data", "yeni model eski veriyle üretilmiş görünüyor"),
          ("ml_score_errors", "bazı fırsatlar puanlanamadı"))


def ml_line(cfg: TelegramConfig, ml: Any, now: datetime, bot: str = "learner") -> str:
    """status.json `ml` bloğu -> tek satır sade Türkçe (16.5). Bozuk blok SectionError."""
    if ml is None:
        return "🤖 Model filtresi kapalı (bot filtresiz çalışıyor)"
    if not isinstance(ml, Mapping):
        raise SectionError("ml_blok")
    mode, state = ml.get("mode"), ml.get("state")
    if mode == "off":
        return "🤖 Model filtresi kapalı (bot filtresiz çalışıyor)"
    if mode not in ("shadow", "active") or state not in ("ok", "expired", "no_model"):
        raise SectionError("ml_blok")
    if state == "ok":
        try:
            kalan = (parse_ts_z(str(ml.get("expires_at"))) - now).total_seconds()
        except Exception:  # noqa: BLE001
            raise SectionError("ml_blok")
        sure = _ml_kalan_tr(kalan)
        if kalan > 7 * 86400:
            line = (f"🤖 Model gölgede izliyor, kararları etkilemiyor · süresi {sure} sonra doluyor" if mode == "shadow"
                    else f"🤖 Model filtresi açık · süresi {sure} sonra doluyor")
        elif mode == "active":
            line = f"⚠️ Model filtresi açık ama süresi {sure} sonra doluyor; yenilenmezse yeni işlemler durur"
        else:
            line = f"⚠️ Gölgedeki modelin süresi {sure} sonra doluyor (işlemler etkilenmez)"
    elif mode == "shadow":
        line = "⚠️ Gölgedeki model çalışmıyor (işlemler etkilenmiyor)"
    elif state == "expired":
        line = "🚨 Modelin süresi doldu: yeni işlem açılmıyor, açık pozisyonlar korunuyor"
    else:
        line = "🚨 Model yüklenemedi: yeni işlem açılmıyor, açık pozisyonlar korunuyor"
    flags = _ml_health_flags(cfg, bot)
    ek = [txt for kod, txt in _ML_EK if kod in flags]
    return line + "".join(f" · {t}" for t in ek)


def rapor_model(cfg: TelegramConfig, now: datetime, ladders: Mapping[str, LadderFiles] | None = None) -> str:
    """Bot başına tek satır. Motor durumu okunamıyorsa boş (genel satırı build_report yazar)."""
    kaynak: dict[str, str] = {"learner": cfg.status_path}
    for b, lf in (ladders or {}).items():
        if lf.status_path and lf.status_path != cfg.status_path and b not in kaynak:
            kaynak[b] = lf.status_path
    out = []
    for bot, path in kaynak.items():
        try:
            st = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - build_report motor durumunu zaten "okunamadı" sayar
            if bot == "learner":
                continue
            raise SectionError("durum")
        if not isinstance(st, Mapping):
            raise SectionError("durum")
        out.append(ml_line(cfg, st.get("ml"), now, bot))
    return "\n".join(out)


DAVRANIS_YOK = "📐 Davranış değerlendirmesi henüz yok"
DAVRANIS_MAX_YAS_S = 36 * 3600


def _davranis_satirlari(path: Path, now: datetime) -> list[str]:
    """`<var>/<bot>/drift.json` (şema drift/1) -> report_lines. Eksik/bayat (36 sa)/bozuk dosya -> tek 'henüz yok' satırı.
    Yalnız standart kütüphane; hiçbir hata dışarı sızmaz (günlük raporu bozmaz)."""
    try:
        raw = path.read_bytes()[:1_000_000]
        d = json.loads(raw.decode("utf-8"))
        if not isinstance(d, Mapping) or d.get("schema") != "drift/1":
            return [DAVRANIS_YOK]
        gen = parse_ts_z(d["generated_at"])
        if (now - gen).total_seconds() > DAVRANIS_MAX_YAS_S:
            return [DAVRANIS_YOK]
        lines = d.get("report_lines")
        if not isinstance(lines, list):
            return [DAVRANIS_YOK]
        out = [str(x) for x in lines if isinstance(x, str) and x.strip()]
        return out or [DAVRANIS_YOK]
    except Exception:  # noqa: BLE001
        return [DAVRANIS_YOK]


def rapor_davranis(cfg: TelegramConfig, now: datetime, ladders: Mapping[str, LadderFiles] | None = None) -> str:
    """Sapma izleyicisi satırları (docs/kagit-degerlendirme-plani.md 4.6): öğrenen. Asla istisna fırlatmaz."""
    try:
        base = Path(cfg.status_path).parent if cfg.status_path else (
            Path(cfg.ledger_path).parent if cfg.ledger_path else None)
        if base is None:
            return DAVRANIS_YOK
        out = _davranis_satirlari(base / "drift.json", now)
        return "\n".join(out)
    except Exception:  # noqa: BLE001
        return DAVRANIS_YOK


# ---- DD-12 WP-17: öğrenme (kurulum karnesi, ders, ML, seans/varlık kırılımı, harcama) ----
_OGR_SINIF = {"kripto": "kripto", "hisse": "hisse senedi", "emtia": "metal / enerji"}


def _ogr_view(cfg: TelegramConfig, now: datetime) -> dict:
    """Öğrenme görünümü; defter okunamazsa `ledger_error` ile döner (bölüm kendi satırını yazar)."""
    from . import panel_data as PD  # noqa: PLC0415
    try:
        return PD.learning_view(cfg.ledger_path, cfg.budget_config, now)
    except PD.SectionError as e:
        raise SectionError(e.code) from None


def _ogr_defter(cfg: TelegramConfig, now: datetime) -> dict:
    """Komutlar için: defter hatası varsa SectionError (komut 'okunamadı' yazar)."""
    lv = _ogr_view(cfg, now)
    if lv.get("ledger_error"):
        raise SectionError(lv["ledger_error"])
    return lv


def _r_or_dash(x: Any) -> str:
    return tr_isaretli(x) + " R" if _num_ok(x) else "—"


def _karne_satirlari(lv: Mapping[str, Any]) -> list[str]:
    out = []
    for row in lv.get("scorecard") or []:
        if not row.get("candidates"):
            continue
        durum = "KAPALI" if row.get("state") == "closed" else "açık"
        satir = (f"{row['arm']}: aday {row['candidates']} · alınan {row['taken']} · ort. R (alınan) "
                 f"{_r_or_dash(row.get('mean_r_taken'))} · alınsaydı {_r_or_dash(row.get('mean_r_taken_cf'))} · {durum}")
        taken_kasa = (row.get("kasa") or {}).get("taken")          # sanal kasa (yalniz alinan seri); yoksa satir eskisi gibi
        if taken_kasa:
            dd = taken_kasa["max_dd_pct"]
            satir += f" · kasa {taken_kasa['equity']:.2f} $ (en derin {('-' + format(dd, '.2f')) if dd > 0 else '0.00'}%)"
        out.append(satir)
    return out


def _harcama_satiri(lv: Mapping[str, Any]) -> str:
    bt = lv.get("budget") or {}
    if "month_used_usd" in bt:
        return f"🤖 Yapay zekâ harcaması (ay): {tr_sayi(bt['month_used_usd'])} $ / {_usd(bt['monthly_cap_usd'])} $"
    return "🤖 Yapay zekâ harcaması: okunamadı"


def kurulumlar_metni(cfg: TelegramConfig, now: datetime) -> str:
    """/kurulumlar: kurulum karnesi (tam); aday yoksa tek satır."""
    lv = _ogr_defter(cfg, now)
    satirlar = _karne_satirlari(lv)
    if not satirlar:
        return "🧪 Kurulum karnesi\nHenüz aday yok."
    return "🧪 Kurulum karnesi\n" + "\n".join(satirlar)


def rapor_kurulum_karnesi(cfg: TelegramConfig, now: datetime) -> str:
    lv = _ogr_view(cfg, now)
    if lv.get("ledger_error"):
        return ""
    satirlar = _karne_satirlari(lv)
    return ("🧪 Kurulum karnesi (haftalık ayrıntı için /kurulumlar)\n" + "\n".join(satirlar)) if satirlar else ""


def _seans_satiri(lv: Mapping[str, Any]) -> str:
    parcalar = []
    for s, ad in (("open", "açık"), ("closed", "kapalı"), ("weekend", "hafta sonu")):
        siniflar = lv.get("sessions", {}).get(s) or {}
        ops = [f"{_OGR_SINIF.get(k, k)} {_r_or_dash(b.get('mean_r_taken'))} ({b.get('taken', 0)} işlem)"
               for k, b in siniflar.items() if b.get("taken")]
        if ops:
            parcalar.append(f"{ad}: " + ", ".join(ops))
    return "🕒 Seans (ort. R, alınan): " + ("; ".join(parcalar) if parcalar else "henüz işlem yok")


def _ders_etki_satiri(ders: Mapping[str, Any]) -> str:
    e = ders.get("effect")
    if not e:
        return "Ders etkisi (referanstan beri): ölçülemedi"
    return f"Ders etkisi (referanstan beri): {tr_isaretli(e['damped_r'])} R ({e['n']} aday)"


def ders_durum_metni(cfg: TelegramConfig, now: datetime) -> str:
    """/ders: ders durumu (uygulanan, geri alma, fren, etki, kapalı kurulumlar), bekleyen öneri, harcama."""
    lv = _ogr_defter(cfg, now)
    ders = lv["lesson"]
    satirlar = ["🎓 Ders durumu",
                f"Uygulanan değişiklik: {ders['applied']} · geri alınan: {ders['rollbacks']} · "
                f"−10 R freni: {'AKTİF (referans sürüme dönüldü, otomatik uygulama durdu)' if ders['brake_active'] else 'yok'}",
                _ders_etki_satiri(ders)]
    kapali = ders.get("closed_arms") or []
    satirlar.append("Kapalı kurulumlar: " + (", ".join(kapali) if kapali else "yok"))
    for e in ders.get("events") or []:
        satirlar.append(f"  {fmt_tsi_tr(e['at'])} {e['kind']}" + (f" ({e['reason']})" if e.get("reason") else ""))
    bekleyen = rapor_ders(cfg, now)
    if bekleyen:
        satirlar.append(bekleyen)
    satirlar.append(_harcama_satiri(lv))
    return "\n".join(satirlar)


def fmt_tsi_tr(iso: str | None) -> str:
    try:
        return parse_ts_z(str(iso)).astimezone(TR).strftime("%d.%m %H:%M")
    except (TypeError, ValueError):
        return "?"


def rapor_ogrenme(cfg: TelegramConfig, now: datetime) -> str:
    """Günlük rapor: ders etkisi, ML etkisi, M1, seans kırılımı, açık pozisyonlar, harcama (her zaman), haftalık özet."""
    lv = _ogr_view(cfg, now)
    out: list[str] = []
    if lv.get("ledger_error"):
        pass                                  # defter yoksa Defter bölümü genel uyarıyı zaten yazar; yalnız harcama kalır
    else:
        ders, ml, op = lv["lesson"], lv["ml"], lv["open"]
        out.append("📚 Ders: uygulanan " + str(ders["applied"]) + " · geri alınan " + str(ders["rollbacks"])
                   + (" · −10 R freni AKTİF" if ders["brake_active"] else "") + " · " + _ders_etki_satiri(ders))
        etki = "" if ml["effect_r"] is None else f" (alınsaydı etkisi {tr_isaretli(ml['effect_r'])} R)"
        out.append(f"🤖 Model: elenen {ml['eliminated']} · geçen {ml['passed']}{etki} · M1 aday {ml['m1_candidates']}, "
                   f"giriş {ml['m1_taken']}")
        out.append(_seans_satiri(lv))
        sinif = [f"{_OGR_SINIF.get(k, k)} {_r_or_dash(b.get('mean_r_taken'))}" for k, b in (lv.get("asset_class") or {}).items()
                 if b.get("taken")]
        if sinif:
            out.append("🧭 Varlık sınıfı (ort. R, alınan): " + ", ".join(sinif))
        if op.get("total"):
            kume = ", ".join(f"{k} {v}" for k, v in op["by_cluster"].items()) or "—"
            kurulum = ", ".join(f"{k} {v}" for k, v in op["by_arm"].items()) or "—"
            out.append(f"📂 Açık pozisyon: {op['total']} · küme: {kume} · kurulum: {kurulum}")
    out.append(_harcama_satiri(lv))
    ws = lv.get("weekly_summary")
    if ws:
        out.append(_haftalik_ozet_metni(ws))
    return "\n".join(out)


def _haftalik_ozet_metni(ws: Mapping[str, Any]) -> str:
    """Haftalik ozet dosyasinin Telegram metni: '## Sabit bölüm' satirlari (LLM'siz; hepsi) ya da eski bicimde ilk metin satiri."""
    lines = str(ws.get("text") or "").splitlines()
    sabit: list[str] = []
    if "## Sabit bölüm" in lines:
        for x in lines[lines.index("## Sabit bölüm") + 1:]:
            if x.startswith("#"):
                break
            if x.strip():
                sabit.append(x.strip()[:300])
    if sabit:
        return f"🗓 Haftalık özet ({ws['week']}):\n" + "\n".join(sabit)
    satir = next((x.strip() for x in lines if x.strip() and not x.startswith("#")), "")
    return f"🗓 Haftalık özet ({ws['week']}): {satir[:300]}"


def default_sections(cfg: TelegramConfig, now: datetime, day: str, pauses: Mapping[str, Any] | None = None,
                     ladders: Mapping[str, LadderFiles] | None = None) -> dict[str, Callable[[], str]]:
    out: dict[str, Callable[[], str]] = {}
    if pauses:                                                   # 11 §9.5: bot basina duraklatma satiri
        out["Duraklatma"] = lambda: rapor_duraklatma(pauses)
    if ladders:                                                  # 12 §9: bot basina tek satir
        out["Risk kademesi"] = lambda: "\n".join(
            "📶 " + ladder_line(b, ladder_view(lf, now)) for b, lf in ladders.items())
    out["Model"] = lambda: rapor_model(cfg, now, ladders)
    out["Davranış"] = lambda: rapor_davranis(cfg, now, ladders)
    out.update({"Defter": lambda: rapor_defter(cfg, day), "Bütçe": lambda: rapor_butce(cfg),
                "Ders": lambda: rapor_ders(cfg, now), "Öğrenme": lambda: rapor_ogrenme(cfg, now),
                "Kurulum karnesi": lambda: rapor_kurulum_karnesi(cfg, now),
                "Alınmayan sinyaller (son 7 gün)": lambda: rapor_kacirilan(cfg, now)})
    return out


def run_report(cfg: TelegramConfig, notifier: TelegramNotifier, now: datetime, sections=None,
               pauses: Mapping[str, Any] | None = None, ladders: Mapping[str, LadderFiles] | None = None) -> str:
    """-> 'sent' | 'spooled' | 'skipped' | 'already'. last_report.json gun anahtari yalniz teslimde yazilir."""
    lp = Path(cfg.var_dir) / "last_report.json"
    try:
        last = json.loads(lp.read_text()).get("day")
    except (OSError, ValueError, AttributeError):
        last = None
    decision, day = report_decision(now, last)
    if decision == "atla":
        return "already" if last == day else "skipped"
    text = build_report(cfg, now, day, default_sections(cfg, now, day, pauses, ladders) if sections is None else sections)
    ok = notifier.send_text(text, "INFO", f"report-{day}")
    if ok:
        try:
            atomic_write_json(lp, {"day": day})
        except Exception:  # noqa: BLE001
            pass
        try:
            haftalik_gonder(cfg, notifier, now)
        except Exception as e:  # noqa: BLE001
            log.warning("haftalik ozet: %s", type(e).__name__)
        return "sent"
    return "spooled"


# ---------------------------------------------------------------------------
# Haftalik ozet (ayri, kisa mesaj; pazar gunu bir kez)
# ---------------------------------------------------------------------------
def haftalik_metni(cfg: TelegramConfig, now: datetime) -> str:
    """Son 7 gunun kapanan islemleri (defterden). 6 satiri asmaz."""
    from . import ledger as L  # noqa: PLC0415
    led = L.open_ledger(cfg.ledger_path, "learner", create=False, read_only=True, migrate=False)
    try:
        closed = led.list_closed_trades(since=now - timedelta(days=7), until=now + timedelta(minutes=1), limit=5000)
    finally:
        led.close()
    gun = now.astimezone(TR).date()
    bas = gun - timedelta(days=6)
    lines = [f"🗓 Haftalık özet · {bas.day} {AY_TR[bas.month - 1]} – {gun.day} {AY_TR[gun.month - 1]}"]
    if not closed:
        lines.append("Bu hafta kapanan işlem yok.")
    else:
        pnl, _ = _sum(closed)
        win = sum(1 for t in closed if (t.realized_pnl or 0) > 0)
        lines.append(f"{len(closed)} işlem kapandı ({win} kâr, {len(closed) - win} zarar) · {TS.isaretli(pnl)} $")
        en = max(closed, key=lambda t: t.realized_pnl or 0.0)
        kt = min(closed, key=lambda t: t.realized_pnl or 0.0)
        lines.append(f"En iyi: {TS.coin(en.pair)} {TS.isaretli(en.realized_pnl or 0.0)} $")
        if (kt.realized_pnl or 0.0) < 0:
            lines.append(f"En kötü: {TS.coin(kt.pair)} {TS.isaretli(kt.realized_pnl or 0.0)} $")
    return TS.etiketle("\n".join(lines[:TS.MAX_SATIR]))


HAFTALIK_TELEGRAM = False                       # haftalik ozet Telegram'a gitmez (panelde/raporda kalir)
DERS_SESSIZ = frozenset({"applied", "rolled_back"})


def haftalik_gonder(cfg: TelegramConfig, notifier: "TelegramNotifier", now: datetime) -> bool:
    if not HAFTALIK_TELEGRAM:
        return False
    tr = now.astimezone(TR)
    if tr.weekday() != 6:                       # yalniz pazar
        return False
    hafta = f"{tr.isocalendar()[0]}-W{tr.isocalendar()[1]:02d}"
    kayit = TS.Kayit(Path(cfg.var_dir) / "alarm_kaydi.json", lambda: now)
    if not kayit.gunde_bir("haftalik", hafta):
        return False
    return notifier.send_text(haftalik_metni(cfg, now), "INFO", f"haftalik-{hafta}")


# ---------------------------------------------------------------------------
# Islem acildi / kapandi + gunluk zarar uyarilari (defter + durum dosyasi okunur; yeni islem tablosu yok)
# ---------------------------------------------------------------------------
def _imlec_oku(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


SAATLIK_ISLEM_MESAJI = 6          # saatte en cok bu kadar tekil islem mesaji; fazlasi saat sonunda tek ozet


def _kol_haritasi(path: str) -> dict:
    """trade_id -> okunur kol adi ('M1 · 1s'); ledger salt okunur. arm_id yoksa setup@trigger_tf; okunamazsa bos."""
    import sqlite3  # noqa: PLC0415
    out: dict = {}
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            for q in ("SELECT e.trade_id, COALESCE(e.arm_id, e.setup || '@' || d.trigger_tf) FROM trade_entries e "
                      "JOIN decision_events d ON d.id = e.decision_id",
                      "SELECT e.trade_id, e.setup || '@' || d.trigger_tf FROM trade_entries e "
                      "JOIN decision_events d ON d.id = e.decision_id"):
                try:
                    for tid, arm in c.execute(q):
                        out[int(tid)] = TS.kol_adi(arm)
                    break
                except sqlite3.Error:
                    continue
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        pass
    return out


def gonderildi_yaz(var_dir, now: datetime, tur: str, t, pnl: float | None = None) -> None:
    """Islem mesaji GITTI -> `<var>/islem_gonderildi.jsonl`'e tek satir (yalniz ekleme; mutabakat icin). Mesaj metni YAZILMAZ. Gonderimi
    asla engellemez: her hata yutulur."""
    try:
        satir = {"ts": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "trade_id": int(t.trade_id), "tur": tur,
                 "yon": TS.yon(t.side), "coin": TS.coin(t.pair), "kz": None if pnl is None else round(float(pnl), 6)}
        p = Path(var_dir)
        p.mkdir(parents=True, exist_ok=True)
        with open(p / "islem_gonderildi.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(satir, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _saat_gonder(kayit, now: datetime, text: str, notifier: "TelegramNotifier", anahtar: str, delta: dict) -> int:
    """Saatlik sinir: ilk 6 mesaj sessiz gider; sonrakiler `delta` ile ozete eklenir."""
    st = kayit.durum("islem_saat")
    n = int(st.get("n", 0))
    if n < SAATLIK_ISLEM_MESAJI:
        ok = notifier.send_text(text, "INFO", anahtar)
        if ok:
            st["n"] = n + 1
            kayit.durum_yaz("islem_saat", st)
        return int(bool(ok))
    for k, v in delta.items():
        st["tasma"] = {**st.get("tasma", {}), k: st.get("tasma", {}).get(k, 0) + v}
    kayit.durum_yaz("islem_saat", st)
    return 0


def _saat_kaydi(kayit, now: datetime, notifier: "TelegramNotifier") -> int:
    """Saat degisti ise: tasan islemler icin tek ozet yolla ve sayaci sifirla."""
    saat = now.astimezone(TR).strftime("%Y-%m-%dT%H")
    st = kayit.durum("islem_saat")
    sent = 0
    if st.get("saat") != saat:
        t = st.get("tasma") or {}
        if t.get("acilan", 0) + t.get("kapanan", 0) > 0:
            if notifier.send_text(TS.saatlik_ozet(int(t.get("acilan", 0)), int(t.get("kapanan", 0)), float(t.get("net", 0.0))),
                                  "INFO", f"islem-ozet:{st.get('saat')}"):
                sent = 1
        kayit.durum_yaz("islem_saat", {"saat": saat, "n": 0})
    return sent


def islem_tick(cfg: TelegramConfig, notifier: "TelegramNotifier", now: datetime | None = None) -> int:
    """Yeni acilan/kapanan islemler (sessiz) ve gunluk zarar esikleri (sesli) icin mesaj yollar; yollanan sayiyi dondurur.
    Ilk calismada mevcut islemler 'bildirilmis' sayilir. Saatte en cok 6 tekil islem mesaji; ayni dakikadaki acilislar tek
    mesaj; fazlasi saat sonunda tek ozet. Imlec: <var>/islem_imleci.json."""
    from . import ledger as L  # noqa: PLC0415
    now = now or datetime.now(UTC)
    if not cfg.ledger_path or not Path(cfg.ledger_path).exists():
        return 0
    imp = Path(cfg.var_dir) / "islem_imleci.json"
    im = _imlec_oku(imp)
    ilk = im is None
    im = im or {"acilan": [], "kapanan": []}
    led = L.open_ledger(cfg.ledger_path, "learner", create=False, read_only=True, migrate=False)
    try:
        acik = led.list_open_trades()
        kap = led.list_closed_trades(since=now - timedelta(days=2), until=now + timedelta(minutes=1), limit=500)
    finally:
        led.close()
    kollar = _kol_haritasi(cfg.ledger_path)
    kol = lambda t: kollar.get(t.trade_id) or TS.kol_adi(t.setup)  # noqa: E731
    acilan, kapanan = set(im.get("acilan", [])), set(im.get("kapanan", []))
    kayit = notifier.kayit
    sent = _saat_kaydi(kayit, now, notifier)
    yeni_acilan: dict[str, list] = {}
    for t in sorted(acik + kap, key=lambda t: (t.entry_ts, t.trade_id)):
        if t.trade_id in acilan:
            continue
        acilan.add(t.trade_id)
        if ilk:
            continue
        yeni_acilan.setdefault(t.entry_ts.strftime("%Y-%m-%dT%H:%M"), []).append(
            (t, (kol(t), t.pair, t.side, t.entry_price, (t.qty or 0.0) * (t.entry_price or 0.0), t.planned_stop)))
    for dk, grup in yeni_acilan.items():
        gitti = _saat_gonder(kayit, now, TS.islemler_acildi([g[1] for g in grup]), notifier,
                             f"islem-ac:{'-'.join(str(g[0].trade_id) for g in grup)}", {"acilan": len(grup)})
        if gitti:
            for g in grup:
                gonderildi_yaz(cfg.var_dir, now, "acildi", g[0])
        sent += gitti
    for t in sorted(kap, key=lambda t: (t.exit_ts, t.trade_id)):
        if t.trade_id in kapanan:
            continue
        kapanan.add(t.trade_id)
        if ilk:
            continue
        pnl = float(t.realized_pnl or 0.0)
        gitti = _saat_gonder(kayit, now, TS.islem_kapandi(kol(t), t.pair, t.side, pnl, (t.qty or 0.0) * (t.entry_price or 0.0),
                                                          t.exit_reason), notifier, f"islem-kapat:{t.trade_id}",
                             {"kapanan": 1, "net": pnl})
        if gitti:
            gonderildi_yaz(cfg.var_dir, now, "kapandi", t, pnl)
        sent += gitti
    try:
        atomic_write_json(imp, {"acilan": sorted(acilan)[-500:], "kapanan": sorted(kapanan)[-500:]})
    except Exception:  # noqa: BLE001
        pass
    return sent + zarar_tick(cfg, notifier, now)


def dayaniklilik_tick(cfg: TelegramConfig, notifier: "TelegramNotifier", now: datetime) -> int:
    """Motor status.json `dayaniklilik` blogundan GECIS bildirimleri: kurulum karantinasi (WARN, birim basina tek mesaj;
    duzelince INFO) ve sembol TRADING disi (acik pozisyonsuz WARN / pozisyonlu CRIT; geri donunce INFO). Onceki durum
    `alarm_kaydi.json` durum('dayaniklilik') icinde; ilk okumada mevcut durum bildirilir (tek sefer)."""
    try:
        blk = json.loads(Path(cfg.status_path).read_text(encoding="utf-8")).get("dayaniklilik")
    except Exception:  # noqa: BLE001
        return 0
    if not isinstance(blk, dict):
        return 0
    kayit = notifier.kayit
    prev = kayit.durum("dayaniklilik") or {}
    q_now = {str(r.get("birim")): str(r.get("hata") or "") for r in blk.get("karantina") or []
             if isinstance(r, dict) and r.get("durum") == "aktif"}
    s_now = {str(r.get("cift")): str(r.get("alert") or "WARN") for r in blk.get("sembol") or [] if isinstance(r, dict)}
    q_prev, s_prev = dict(prev.get("karantina") or {}), dict(prev.get("sembol") or {})
    sent = 0

    def send(text: str, sev: str, key: str) -> None:
        nonlocal sent
        sent += int(bool(notifier.send_text(text, sev, key)))

    for u, err in q_now.items():
        if u not in q_prev:
            send(f"{u} kurulumu art arda kod hatasi verdi, yeni islem acmiyor; acik pozisyonlar stop/hedefle suruyor. "
                 f"Hata: {err[:120]}. Kaldirmak icin /karantina_kaldir {u}", "WARN", f"karantina:{u}:{int(now.timestamp())}")
    for u in q_prev:
        if u not in q_now:
            send(f"{u} kurulumu karantinadan cikti", "INFO", f"karantina-cikis:{u}:{int(now.timestamp())}")
    for c, sev in s_now.items():
        if c not in s_prev:
            send(f"{c} borsada islem disi; yeni giris yok" + (", acik pozisyon var (zorla kapatma yok)" if sev == "CRIT" else ""),
                 sev, f"sembol:{c}:{int(now.timestamp())}")
    for c in s_prev:
        if c not in s_now:
            send(f"{c} yeniden islemde; yeni girisler acildi", "INFO", f"sembol-geri:{c}:{int(now.timestamp())}")
    if q_now != q_prev or s_now != s_prev:
        kayit.durum_yaz("dayaniklilik", {"karantina": q_now, "sembol": s_now})
    return sent


def zarar_tick(cfg: TelegramConfig, notifier: "TelegramNotifier", now: datetime) -> int:
    """Gunluk zarar: sinirin %80'inde gunde bir uyari; sinira ulasinca gunde bir 'limit doldu'."""
    try:
        st = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        eq, dse = st.get("equity"), st.get("day_start_equity")
    except Exception:  # noqa: BLE001
        return 0
    if not (_num_ok(eq) and _num_ok(dse) and dse > 0):
        return 0
    zarar, lim = max(0.0, dse - eq), TS.limit_orani(cfg.config_dir, st.get("mode")) * dse
    gun = now.astimezone(TR).date().isoformat()
    kayit = notifier.kayit
    sent = 0
    if zarar >= lim:
        if kayit.gunde_bir("limit-doldu", gun):
            sent += int(bool(notifier.send_text(TS.limit_doldu(zarar, lim), "WARN", f"limit-doldu:{gun}")))
    elif zarar >= TS.UYARI_ORANI * lim:
        if kayit.gunde_bir("limit-uyari", gun):
            sent += int(bool(notifier.send_text(TS.limit_uyari(zarar, lim), "WARN", f"limit-uyari:{gun}")))
    return sent
