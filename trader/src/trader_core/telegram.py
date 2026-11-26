"""Telegram: bildirim, komut ve gunluk rapor (docs/telegram-spec.md). Yalniz stdlib + `requests`.

Giden: `TelegramNotifier` (spool + dogrudan, `dedup_key` zorunlu). Gelen: `TelegramDaemon` (long polling, tek chat,
yalniz ozel sohbet, iki adimli kod onayi). Motor bu modulu ice aktarmaz; Telegram ticareti
asla bloke etmez. Token hicbir cikti/gunluk/spool/istisna metninde bulunmaz (`mask`).
HTTP enjekte edilir: `http_post(url, json=..., timeout=...) -> (status_code, body_dict)`; ag hatasi `(0, {})`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


from . import ml1_gorunum as MG
from . import ortak as ORT
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
    (ofsetli) girdi ValueError: motorun ve panelin yazdığı iki biçim de (fileio.fmt_ts, panel '.%03dZ') kabul edilir."""
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
CODE_RE = re.compile(r"^\d{4}$")
# Ders sistemi kaldirildi (25.11): eski komutlar tek satirla yanitlanir, hicbir islem yapilmaz.
KALDIRILAN_KOMUTLAR = ("/ders", "/onayla", "/reddet", "/karantina_kaldir")
KALDIRILDI_METNI = "Bu komut kaldırıldı. Seçimi artık ML1 yapıyor; durum için /ml1 yaz."
SEVERITIES = ("INFO", "WARN", "CRIT")
_TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_\-]+")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def mask(text: Any, token: str | None = None) -> str:
    t = str(text)
    if token:
        t = t.replace(token, "<gizli>")
    t = _TOKEN_RE.sub("bot<gizli>", t)
    return ORT.scrub(t)


def tail3(x: Any) -> str:
    s = str(x)
    return s[-3:]


# ---------------------------------------------------------------------------
# Metin
# ---------------------------------------------------------------------------
def neutralize(text: str) -> str:
    """Komut gibi gorunen '/' satirlarinin basina bosluk ekler; kontrol karakterlerini atar."""
    t = _CTRL_RE.sub(" ", ORT.scrub(text))
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
                 health_state: str = "", ledger_path: str = "",
                 budget_config: str = "", config_dir: str = ""):
        self.config_dir = config_dir                 # gunluk zarar orani (engine.*.json risk blogu); bos -> kilitli deger
        self.ledger_path = ledger_path
        self.budget_config = budget_config
        self.token, self.chat_id, self.var_dir = token, chat_id, var_dir
        self.kill_file, self.status_path = kill_file, status_path
        self.health_state = health_state

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
                   env.get("HEALTH_STATE_PATH", ""),
                   _abs_path(here, env.get("LEDGER_PATH") or "user_data/ledger_learner.sqlite"),
                   _abs_path(here, env.get("BUDGET_CONFIG_PATH") or "config/budget.json"),
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
    """Sahiplik modeli: outbox dizini trader:trader-tg 2770'dir (install.sh kurar). Yazanlar farkli kullanicidir (saglik birimi root,
    motor/mutabakat trader); root'un olusturdugu her dosya/dizin dizinin sahibine (uid/gid) cevrilir, aksi halde trader okuyamaz."""

    def __init__(self, base: str | Path, now_fn: Callable[[], datetime]):
        self.dir = Path(base) / "outbox"
        self.sent_dir = self.dir / "sent"
        self.rejected_dir = self.dir / "rejected"
        self.now = now_fn
        self.dropped = 0

    def _sahip_duzelt(self, p: Path, dizin: bool = False) -> None:
        """p'yi outbox dizininin uid/gid'ine cevirir (yalniz farkliysa; yetki yoksa sessizce gecer). Dizinse mod 2770, dosyaysa 0660."""
        try:
            ref = os.stat(self.dir)
            st = os.lstat(p)
            if (st.st_uid, st.st_gid) != (ref.st_uid, ref.st_gid):
                os.chown(p, ref.st_uid, ref.st_gid)
                os.chmod(p, 0o2770 if dizin else 0o660)
        except OSError as e:
            log.warning("outbox sahiplik duzeltilemedi: %s", type(e).__name__)

    def _mk(self) -> None:
        self.sent_dir.mkdir(parents=True, exist_ok=True)
        self._sahip_duzelt(self.sent_dir, dizin=True)

    def _reddet(self, p: Path) -> None:
        """Kalici hatali ogeyi kuyruk basindan alip rejected/ altina tasir (inceleme icin saklanir); tasinamazsa kaydedilir, atlanir."""
        try:
            self.rejected_dir.mkdir(parents=True, exist_ok=True)
            self._sahip_duzelt(self.rejected_dir, dizin=True)
            hedef = self.rejected_dir / p.name
            os.replace(p, hedef)
            self._sahip_duzelt(hedef)
        except OSError as e:
            log.warning("outbox oge reddedilene tasinamadi: %s", type(e).__name__)

    def _sil(self, p: Path) -> None:
        """Silinemeyen (yetkisiz) dosya dongu/servisi dusurmez: kaydedilir, atlanir."""
        try:
            p.unlink(missing_ok=True)
        except OSError as e:
            log.warning("outbox dosyasi silinemedi: %s", type(e).__name__)

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
            f = self.sent_dir / _key_hash(key)
            f.write_text(f"{until:.0f}\n")
            self._sahip_duzelt(f)
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
            self._sahip_duzelt(p)
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
        total = 0
        for p in files:
            try:
                total += p.stat().st_size
            except OSError:
                pass
        if len(files) <= SPOOL_MAX_FILES and total <= SPOOL_MAX_BYTES:
            return
        for sev in ("INFO", "WARN"):
            for p in list(files):
                if len(files) <= SPOOL_MAX_FILES and total <= SPOOL_MAX_BYTES:
                    return
                d = self._read(p)
                if d and d.get("severity") == sev:
                    try:
                        total -= p.stat().st_size
                    except OSError:
                        pass
                    self._sil(p)
                    files.remove(p)
                    self.dropped += 1

    def drain(self, client: TelegramClient, chat_id: int, sleep: Callable[[float], None] = time.sleep) -> int:
        """Eski->yeni. Basarili dosya silinir. Gecici hata: dur (siradaki tur dener); kalici hata: oge rejected/ altina, siradakine gec. Gonderilen sayisini dondurur."""
        now = self.now().timestamp()
        items: list[tuple[Path, dict]] = []
        for p in self.list():
            d = self._read(p)
            if d is None:
                continue
            exp = d.get("expires_at")
            if exp is not None and exp <= now:
                self._sil(p)       # suresi dolmus onay talebi gonderilmez
                continue
            if d.get("severity") == "INFO" and now - float(d.get("created_at", now)) > INFO_MAX_AGE_S:
                self._sil(p)
                continue
            if self.sent_recently(d["dedup_key"]):
                self._sil(p)
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
                        self._sil(p)
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
                    log.error("CRIT spool gonderimi kalici hata %s; oge rejected/ altina tasindi", e.status)
                    self._reddet(p)
                    continue       # kuyruk basini tikamasin: siradaki ogeye gec
                if e.retry_after:
                    sleep(e.retry_after)
                break
            self.mark_sent(d["dedup_key"], d.get("expires_at"))
            self._sil(p)
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

def notifier_from_env(env: Mapping[str, str], http_post=None, now_fn=None, sleep=time.sleep) -> TelegramNotifier | None:
    cfg = TelegramConfig.from_env(env)
    if cfg is None:
        return None
    now_fn = now_fn or (lambda: datetime.now(UTC))
    n = TelegramNotifier(TelegramClient(cfg.token, http_post, sleep), cfg.chat_id, Outbox(cfg.var_dir, now_fn), now_fn, sleep)
    n.status_path = cfg.status_path or None
    return n


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


BILINMEYEN_METNI = "Bu komutu tanımıyorum. /yardim yaz."


def yardim_metni(kademe: bool = False) -> str:
    """/yardim: 3 satir (kademe komutlari yalniz kademe yapilandirilmissa listelenir)."""
    ek = " · /kademe · /kademe_devam" if kademe else ""
    return ("Komutlar: /durum · /rapor · /ml1 · /durdur · /devam · /hepsini_kapat" + ek + "\n"
            "/durdur: yeni işlem açmayı durdurur; açık işlemler stoplarıyla açık kalır.\n"
            "/hepsini_kapat: tüm işlemleri kapatır ve botu durdurur (4 haneli kodla onay ister).")
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
                lines.append(f"{ad}: yeni işlemler açık")
            continue
        nedenler = "; ".join(dict.fromkeys(neden_tr(h.reason) for h in st[bot])) or "duraklatma durumu okunamadı"
        kim = next((f" ({_kisi_tr(h.by)}" + (f", {z}" if (z := _zaman_tr(h.at)) else "") + ")" for h in st[bot]
                    if h.reason != "unreadable"), "")
        lines.append(f"{ad}: yeni işlemler duraklatıldı — {nedenler}{kim}")
    return lines


@dataclass(frozen=True)
class LadderFiles:
    """12 §9: bot basina kademe gunlugu (okuma/yazma), motorun status.json yolu ve duraklatma (tutus kaldirma)."""
    log: Any
    status_path: str
    pause: Any
    risk: float | None = None     # kipin ayarindaki islem basi risk (durum blogu yokken yedek); None: RL.LIVE_START_STEP


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


def _cfg_risk(lf: LadderFiles) -> float:
    """Etkin risk yedegi: kipin ayarindan (LadderFiles.risk), yoksa canli baslangic basamagi."""
    r = getattr(lf, "risk", None)
    return float(r) if _num_ok(r) and r > 0 else RL.STEPS[RL.LIVE_START_STEP]


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
        out.update(state=st.status, step=st.step, step_name=RL.STEP_NAMES[st.step], step_risk=_cfg_risk(lf),
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
        if _num_ok(blk.get("effective_risk")) and blk.get("effective_risk") > 0:      # 24.11: etkin risk durum blogundan
            out["step_risk"] = blk["effective_risk"]
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
    return (f"{bot}: {pre}Kademe: risk %{_tr(v['step_risk'] * 100)} (sabit) | özsermaye {_tr(v['equity'])} | "
            f"taban {_tr(v['base'])} (düşüş %{_tr(v['dd_base_pct'], 1)}) | durma {_tr(v['stop_at'])} | "
            f"son taban {_tr(v['floor_at'])} | işlem {n if n is not None else '?'}")


class TelegramDaemon:
    def __init__(self, cfg: TelegramConfig, client: TelegramClient, *, now_fn: Callable[[], datetime] | None = None,
                 killswitch=None, report_fn: Callable[[], str] | None = None,
                 sleep: Callable[[float], None] = time.sleep, random_code: Callable[[], str] | None = None,
                 pauses: Mapping[str, Any] | None = None, ladders: Mapping[str, LadderFiles] | None = None,
                 expect_status_mode: str | None = None):
        self.cfg, self.client = cfg, client
        self.expect_status_mode = expect_status_mode     # DD-9 §7: canli bot varken durum dosyasi `live` olmali (kagit dosyada KILL kalkmaz)
        self.now = now_fn or (lambda: datetime.now(UTC))
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
        self._kademe_okunamadi: set[str] = set()                # /kademe_devam: durumu okunamayan botlar ("bekleyen yok" denmesin)
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
        row = {"ts": ORT.fmt_ts(self.now()), "event": event, **kw}
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

    def _reply(self, text: str, severity: str = "WARN", etiket: bool = False) -> None:
        """`etiket=True`: bilgi yanitlari (/yardim, /durum, /ml1, bilinmeyen/kaldirilan komut) `[ML] ` onekiyle gider; onay kodu akisinin
        yanitlari eskisi gibi oneksiz (kod, red ve sonuc cumleleri)."""
        try:
            self.client.send_message(self.cfg.chat_id, fit_text(TS.etiketle(text) if etiket else text),
                                     disable_notification=severity == "INFO")
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
            return self._reply(f"İşlenmedi; yeniden gönder (yaş: {int(age)} sn)")
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
            self._reply("Yetkisiz komut denemesi.")

    def _dispatch_text(self, text: str, who: str) -> str:
        t = text.strip()
        if CODE_RE.match(t):
            return self._on_code(t, who)
        n = _norm_cmd_text(t)
        if n == "hepsini kapat":
            return self._cmd_kill_start()
        parts = t.split()
        if not parts or not parts[0].startswith("/"):
            self._reply(BILINMEYEN_METNI, etiket=True)
            return "unknown"
        cmd = parts[0].lower().split("@")[0]
        arg = parts[1] if len(parts) > 1 else ""
        if cmd == "/yardim" or cmd == "/start":
            self._reply(yardim_metni(bool(self.ladders)), "INFO", etiket=True)
            return "ok"
        if cmd == "/durum":
            return self._cmd_status()
        if cmd == "/rapor":
            if self.report_fn is None:
                self._reply("Rapor yapılandırılmamış.")
                return "noreport"
            self._reply(self.report_fn() + "\n(elle istendi)", "INFO")
            return "ok"
        if cmd in ("/ml1", "/kurulumlar"):                     # /kurulumlar eski ad: ayni yanit
            return self._cmd_info(lambda: ml1_metni(self.cfg, self.now()))
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
        if cmd in KALDIRILAN_KOMUTLAR:
            self._reply(KALDIRILDI_METNI, "INFO", etiket=True)
            return "removed"
        self._reply(BILINMEYEN_METNI, etiket=True)
        return "unknown"

    def _cmd_info(self, fn) -> str:
        """Salt okunur bilgi komutu (/ml1): okunamayan veri tek satırla bildirilir."""
        try:
            text = fn()
        except SectionError as e:
            self._reply(f"Okunamadı: {e.code}", "INFO", etiket=True)
            return "unreadable"
        self._reply(text, "INFO")
        return "ok"

    # -- durum --------------------------------------------------------------
    def _cmd_status(self) -> str:
        st = self._read_status()
        if not st:
            self._reply("Durum okunamadı.", etiket=True)
            return "unreadable"
        try:
            dk = int((self.now() - parse_ts_z(st["loop_at"])).total_seconds() // 60)
        except Exception:  # noqa: BLE001
            dk = None
        lines = [f"Anlık durum ({KIP_TR.get(str(st.get('mode')), 'kip bilinmiyor')})"]
        k = _kasa_toplam_satiri(self.cfg, st)
        if k:
            lines.append(k)
        lines.append(_acik_satiri(st))
        calisiyor = dk is None or dk < 2
        if calisiyor:
            pause_text = "\n".join(pause_lines(self.pauses, sadece_tutulan=True)) if self.pauses else ""
            doldu = _zarar_doldu(self.cfg, st)
            d = _durum_satiri(st, pause_text, doldu)
            if d and not (self.pauses and not st.get("kill") and not doldu):     # duraklatma satiri (asagida) bunu zaten soyler
                lines.append(d)
            lines.append("Bot çalışıyor.")
        else:
            lines.append(f"Bot yanıt vermiyor! (son sinyal {dk} dk önce)")
        lines += self._pause_lines()
        lines += self._ladder_lines()
        self._reply("\n".join(lines), "INFO", etiket=True)
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
            self._reply("Desteklenmiyor; tam kapatma için /hepsini_kapat")
            return "unsupported"
        st = self._pause_state()
        have = {b: next((h for h in hs if h.reason == PAUSE_USER), None) for b, hs in st.items()}
        if all(have.get(b) is not None for b in self.pauses):
            who = "; ".join(f"{b}: {h.by}, {h.at}" for b, h in have.items() if h is not None)
            self._reply(f"Yeni işlem açma zaten durdurulmuş ({who})")
            return "already"
        code = self._new_pending("pause")
        self._reply("Yeni işlem açma durdurulacak; açık işlemler stoplarıyla açık kalır. Onay için "
                    f"{CODE_TTL_S} sn içinde yalnız şu 4 haneli kodu yanıtla: {code}")
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
        return "Acil durdurma etkin değil"

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
            ln = [f"{b}: risk %{_tr(v['step_risk'] * 100)} (sabit) | durum {dur}",
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
        self._kademe_okunamadi = set()
        for b, lf in (self.ladders or {}).items():
            try:
                st = lf.log.state()
            except Exception as e:  # noqa: BLE001
                self._kademe_okunamadi.add(b)
                log.error("kademe durumu okunamadi (%s): %r", b, e)
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
                except Exception as e:  # noqa: BLE001
                    self._kademe_okunamadi.add(b)
                    log.error("kademe durumu okunamadi (%s): %r", b, e)
                    continue
                if st is not None and st.status == "floor":
                    return "Son taban: Telegram'dan açılamaz; yazılı karar + sunucu gerekir", []
            if self._kademe_okunamadi:
                return f"Kademe durumu okunamadı ({', '.join(sorted(self._kademe_okunamadi))}); sunucu günlüğüne bakın", []
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
            parts.append(f"{b}: yeni taban {_tr(nb)} USD, yeni durma seviyesi {_tr(RL.STOP_RATIO * nb)} USD, "
                         f"risk %{_tr(v['step_risk'] * 100)} (sabit), son taban {_tr(RL.FLOOR_RATIO * st.dep_net)} USD")
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

    def _cmd_kill_start(self) -> str:
        if self.killswitch is None:
            self._reply("Acil durdurma yapılandırılmamış.")
            return "noconfig"
        if self.killswitch.active():
            info = self.killswitch.info() or {}
            self._reply(f"Acil durdurma zaten etkin ({info.get('by')}, {info.get('at')})")
            return "already"
        code = self._new_pending("kill")
        self._reply("Tüm işlemler piyasadan kapatılacak ve yeni işlem açma durdurulacak (acil durdurma). Onay için "
                    f"{CODE_TTL_S} sn içinde yalnız şu 4 haneli kodu yanıtla: {code}")
        return "code_sent"

    def _devam_refusal(self) -> str | None:
        if self.killswitch is None:
            return "Acil durdurma yapılandırılmamış"
        if not self.killswitch.active():
            return "Acil durdurma etkin değil"
        st = self._read_status()
        if st is None:
            return "Durum okunamadı, reddedildi"
        if self.expect_status_mode is not None and st.get("mode") != self.expect_status_mode:
            return "Durum dosyası beklenen kipte değil, reddedildi"
        ks = st.get("kill_state")
        if ks == "exiting":
            return "Kapanış sürüyor, bekleyin"
        if st.get("mode") not in ("paper", "backtest"):       # canli ya da bilinmeyen
            info = self.killswitch.info() or {}
            if not (str(info.get("by", "")).startswith("telegram:") and info.get("reason") == "user_cmd"):
                return "Bu acil durdurma Telegram'dan kurulmadı; yalnız sunucuda kaldırılır"
        if ks != "flat":                                      # DD-9 §7 (O7): HER kipte (paper dahil); eksik/yanlis tip = flat degil
            return "Pozisyonlar kapanmadı (durum flat değil), reddedildi"
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
                extra = " Yeni işlemleri durduran duraklatma ayrıca sürüyor; onun için acil durdurma kalkınca /devam'ı yeniden gönder."
            self._reply(f"Acil durdurma kaldırılacak ve yeni işlemler yeniden açılabilir. {CODE_TTL_S} sn içinde yalnız şu 4 haneli "
                        f"kodu yanıtla: {code}.{extra}")
        else:
            held = {h.reason for hs in self._pause_state().values() for h in hs}
            what = " + ".join(t for r, t in ((PAUSE_USER, "Elle durdurma"), (PAUSE_LATCH, "Ana para kilidi")) if r in held)
            self._reply(f"Yeni işlemleri durduran duraklatma kaldırılacak ({what}). {CODE_TTL_S} sn içinde yalnız şu 4 haneli "
                        f"kodu yanıtla: {code}")
        return "code_sent"

    def _on_code(self, code: str, who: str) -> str:
        p = self._read_pending()
        if not p or p.get("chat_id") != self.cfg.chat_id:
            self._reply("Bekleyen onay yok.")
            return "no_pending"
        self._clear_pending()                                 # tek kullanimlik / tek deneme
        if self.now().timestamp() > float(p.get("expires_at", 0)):
            self._reply("Süre doldu; yeniden başlat.")
            return "expired"
        want = hashlib.sha256((p["salt"] + code).encode()).hexdigest()
        if not hmac.compare_digest(want, p["token_hash"]):
            self._reply("Yanlış kod; iptal edildi.")
            return "wrong_code"
        if p["action"] == "ladder_resume":
            return self._ladder_resume_apply(who)
        if p["action"] == "kill":
            self.killswitch.set(by=f"telegram:{who}", reason="user_cmd")
            self.kill_watch = self.now().timestamp()
            self._reply("Acil durdurma kuruldu; bot işlemleri kapatıyor.")
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
            msg = ("Yeni işlem açma durduruldu. Açık işlemler stoplarıyla açık kalır. "
                   "Hepsini kapatmak için /hepsini_kapat.")
            if problems:
                msg = "Duraklatma kısmen uygulandı/uygulanamadı:\n" + "\n".join(problems) + "\n" + msg
            self._reply(msg, "CRIT" if problems else "WARN")
            return "pause_partial" if problems else "paused"
        if p["action"] == "devam":
            layer = p.get("layer", "kill")
            if layer == "pause" and self.pauses:
                if self.killswitch is not None and self.killswitch.active():
                    self._reply("Acil durdurma etkin; önce onu kaldır: /devam ile acil durdurma kalkar, duraklatma ondan sonra")
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
                head = "Duraklatma (senin komutun / ana para kilidi) kaldırıldı." if not failed else \
                    "Duraklatma kısmen kaldırıldı:\n" + "\n".join(failed)
                self._reply(head + "\n" + self._remaining_lines(), "CRIT" if failed else "WARN")
                return "pause_partial" if failed else "pause_cleared"
            why = self._devam_refusal()
            if why:
                self._reply(why)
                return "refused"
            self.killswitch.clear()
            rem = ("\n" + self._remaining_lines()) if self.pauses else ""
            self._reply("Acil durdurma kaldırıldı" + rem)
            return "kill_cleared"
        return "bad_action"

    def tick_kill_watch(self) -> None:
        if self.kill_watch is not None and self.now().timestamp() - self.kill_watch >= 300:
            self.kill_watch = None
            st = self._read_status()
            if st is None or st.get("kill_state") != "flat":
                self._reply("Kapatma tamamlanmadı (işlemler hâlâ açık olabilir); panoya bak.", "CRIT")

    def _handle_callback(self, uid: int, cq: dict) -> None:
        """Eski ders onay dugmeleri (ok/no/ev/vz) artik islem yapmaz: yetkili kullaniciya 'kaldirildi' denir, denetim kaydi yazilir."""
        msg = cq.get("message") or {}
        chat, frm = msg.get("chat") or {}, cq.get("from") or {}
        if not self._authorized(chat, frm):
            return self._unauthorized(uid, chat.get("id"), cq.get("data"))
        try:
            self.client.answer_callback_query(cq.get("id", ""), "bu dugme kaldirildi")
        except Exception as e:  # noqa: BLE001
            log.warning("answer_callback_query: %s", type(e).__name__)
        self._audit("exec", update_id=uid, cmd="cb", sonuc="removed")

    # -- dongu --------------------------------------------------------------
    def write_alive(self) -> None:
        try:
            atomic_write_json(self.base / "alive.json", {"ts": ORT.fmt_ts(self.now())})
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
KIP_TR = {"paper": "deneme parası", "testnet": "test ağı", "live": "GERÇEK PARA"}
AY_TR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")
BOT_TR = {"learner": "ana bot"}

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
def tr_sayi(x: float, ondalik: int = 2) -> str:
    """1234.5 -> '1.234,50' (Türkçe gösterim)."""
    return f"{x:,.{ondalik}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tr_isaretli(x: float, ondalik: int = 2) -> str:
    """12.5 -> '+12,50'; -3 -> '−3,00'."""
    return ("+" if x >= 0 else "−") + tr_sayi(abs(x), ondalik)


def tr_yuzde(oran: float, ondalik: int = 2) -> str:
    """0.0125 -> '+%1,25'."""
    return ("+" if oran >= 0 else "−") + "%" + tr_sayi(abs(oran) * 100, ondalik)


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


def _baslangic_kasasi(cfg: TelegramConfig) -> float | None:
    """Toplam K/Z icin baslangic sermayesi: motor ayarindaki wallet_start (pano ile ayni kaynak); okunamazsa None."""
    try:
        v = TS.motor_ayari(cfg.config_dir or None).get("wallet_start")
    except (OSError, ValueError, TypeError):
        return None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _kasa_toplam_satiri(cfg: TelegramConfig, st: Mapping[str, Any]) -> str | None:
    """'Kasa 915,50 $ · toplam −84,50 $' (toplam = kasa - baslangic; baslangic okunamazsa bu parca yazilmaz)."""
    eq = st.get("equity")
    if not _num_ok(eq):
        return None
    start = _baslangic_kasasi(cfg)
    return f"Kasa {TS.sayi(eq)} $" + (f" · toplam {TS.isaretli(eq - start)} $" if start is not None else "")


def _acik_satiri(st: Mapping[str, Any]) -> str:
    n = len(st.get("open_positions") or [])
    if not n:
        return "Açık işlem yok."
    u = st.get("unrealized_pnl_usd")
    return f"Açık: {n} işlem" + (f" · anlık {TS.isaretli(u)} $" if _num_ok(u) else "")


def _zarar_doldu(cfg: TelegramConfig, st: Mapping[str, Any]) -> bool:
    eq, dse = st.get("equity"), st.get("day_start_equity")
    if not (_num_ok(eq) and _num_ok(dse) and dse > 0):
        return False
    return max(0.0, dse - eq) >= TS.limit_orani(cfg.config_dir, st.get("mode")) * dse


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




def _ml1_veri(cfg: TelegramConfig, now: datetime) -> tuple[dict | None, Any]:
    """ML1 ozeti (pano ile ayni `ml1_gorunum.ml1_ozet`) ve motor ayarindaki `ml1.aktif`. Defter okunamazsa (None, aktif)."""
    from . import ledger as L  # noqa: PLC0415
    try:
        aktif = (TS.motor_ayari(cfg.config_dir or None).get("ml1") or {}).get("aktif")
    except (OSError, ValueError, TypeError, AttributeError):
        aktif = None
    if not cfg.ledger_path or not Path(cfg.ledger_path).exists():
        return None, aktif
    try:
        led = L.open_ledger(cfg.ledger_path, "learner", create=False, read_only=True, migrate=False)
        try:
            dec = led.list_decisions()
            closed = led.list_closed_trades(None, None, L.Ledger.LIST_CLOSED_MAX)
            acik = led.list_open_trades()
        finally:
            led.close()
    except Exception as e:  # noqa: BLE001
        log.warning("ML1 verisi okunamadı: %s", type(e).__name__)
        return None, aktif
    return MG.ml1_ozet(dec, closed, acik, now), aktif


def _ml1_satirlari(oz: dict | None, aktif: Any, *, hafta: bool = False) -> list[str]:
    """Gunluk ozet (hafta=False) ve haftalik ozet (hafta=True) ML1 satirlari; sayilar pano ile ayni."""
    if aktif is not True:
        return ["ML1 kapalı."]
    if oz is None:
        return []
    e = oz["eleme"]["7g" if hafta else "bugun"]
    z7 = oz["zd_ozet_7g"]
    og = (oz.get("ogrenme") or {}).get("7g" if hafta else "bugun") or {}
    if not e["puanlanan"] and og.get("aday"):
        ilk = (f"ML1 öğrenme aşamasında{'' if hafta else ' (bugün)'}: {TS.sayi(og['aday'], 0)} aday süzülmeden geçti, "
               f"{og['islem']}{TS.iyelik_belirtme(og['islem'])} işleme çevirdi")
    elif not e["puanlanan"]:
        ilk = "ML1: puanlanacak aday çıkmadı." if hafta else "ML1 bugün: puanlanacak aday çıkmadı."
    elif hafta:
        ilk = (f"ML1: {TS.sayi(e['puanlanan'], 0)} aday puanladı, {TS.sayi(e['islem'], 0)}{TS.iyelik_belirtme(e['islem'])} "
               f"işleme çevirdi (%{TS.sayi(e['islem'] / e['puanlanan'] * 100, 0)})")
    else:
        ilk = f"ML1 bugün: {TS.sayi(e['puanlanan'], 0)} aday puanladı, {e['islem']}{TS.iyelik_belirtme(e['islem'])} işleme çevirdi"
    if hafta:
        k, d = MG.ozet_satirlari({"zd_ozet": z7})
        return [ilk, k, d]
    if z7["kanitli"]["n"] + z7["kanitsiz"]["n"] == 0:
        return [ilk]
    return [ilk, "ML1 işlemleri (7 gün): "
            f"4s+1g {z7['kanitli']['n']} işlem {MG.r_metni(z7['kanitli']['net_r'])} · "
            f"15dk+1s {z7['kanitsiz']['n']} işlem {MG.r_metni(z7['kanitsiz']['net_r'])}"]


def ml1_metni(cfg: TelegramConfig, now: datetime) -> str:
    """/ml1 (ve /kurulumlar): en cok 6 satir; sayilar panodaki ML1 sekmesiyle ayni."""
    oz, aktif = _ml1_veri(cfg, now)
    if oz is None:
        raise SectionError("defter_yok")
    e = oz["eleme"]
    ogr = (oz.get("ogrenme") or {}).get("7g") or {}
    esik = TS.sayi(oz["esik"], 2) if oz["esik"] is not None else ("öğrenme aşaması" if ogr.get("aday") else "okunamadı")
    k, d = MG.ozet_satirlari(oz)
    return TS.etiketle("\n".join([
        f"ML1{'' if aktif is True else ' (kapalı)'} · eşik {esik}",
        f"Bugün: {TS.sayi(e['bugun']['puanlanan'], 0)} aday, {TS.sayi(e['bugun']['gecen'], 0)} geçti, {e['bugun']['islem']} işlem",
        f"7 gün: {TS.sayi(e['7g']['puanlanan'], 0)} aday, {TS.sayi(e['7g']['gecen'], 0)} geçti, {e['7g']['islem']} işlem",
        k, d, MG.sinav_satiri()][:TS.MAX_SATIR]))


def build_report(cfg: TelegramConfig, now: datetime, day: str, sections: Mapping[str, Callable[[], str]] | None = None
                 ) -> str:
    """Günlük özet (en çok 10 satır, sade Türkçe). `sections` yalnız 'Duraklatma' için okunur; diğer bölümler panelde."""
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
    baslik = f"Günlük özet · {_gun_tr(day)}" + (" · gerçek para" if mod == KIP_TR["live"] else "")
    if stale:                                                    # tek emoji ilk satirda: ozet basligi emojisiz
        out += [f"🔴 Bot yanıt vermiyor (son sinyal {int(age // 60)} dk önce)", baslik]
    else:
        out.append(f"🌙 {baslik}")
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
    if st is not None:
        if (k := _kasa_toplam_satiri(cfg, st)):
            out.append(k)
        out.append(_acik_satiri(st))
        doldu = _zarar_doldu(cfg, st)
    oz, aktif = _ml1_veri(cfg, now)
    out += _ml1_satirlari(oz, aktif)
    if st is not None and _num_ok(dse) and dse > 0 and _num_ok(eq):
        kayip, lim = max(0.0, dse - eq), TS.limit_orani(cfg.config_dir, st.get("mode")) * dse
        out.append(f"Günlük zarar sınırı: {TS.sayi(kayip, 0)} $ / {TS.sayi(lim, 0)} $")
    d = _durum_satiri(st, pause_text, doldu)
    if d and not stale:
        out.append(d)
    if cfg.health_state:
        try:
            ov = json.loads(Path(cfg.health_state).read_text(encoding="utf-8")).get("last_overall")
            if isinstance(ov, str) and ov != "OK":
                out.append("Dikkat: bir sistem kontrolü sorunlu; panoya bak.")
        except Exception as e:  # noqa: BLE001
            log.warning("rapor: sağlık durumu okunamadı: %s", type(e).__name__)
    if problems:
        out.append("Bazı bilgiler okunamadı.")
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
    names = {"haftalik_ozet": "haftalık özet", "lesson": "ders", "haber_kolu": "haber kolu",
             "yorumcu": "yorumcu"}
    parts = [f"{names.get(k, k)} {v.used_usd:.2f}$/{v.cap_usd:.2f}$ ({v.state})" for k, v in sv.items()]
    out = f"ay {st.month_used_usd:.2f}$/{st.monthly_cap_usd:.2f}$ ({st.month_state}); bugün: " + ", ".join(parts)
    if not st.prices_verified:
        out += "; fiyatlar doğrulanmadı"
    return out


def rapor_duraklatma(pauses: Mapping[str, Any]) -> str:
    """Yalnız duraklatılmış botlar için satır; hiç duraklatma yoksa boş."""
    return "\n".join(pause_lines(pauses, sadece_tutulan=True))


def default_sections(cfg: TelegramConfig, now: datetime, day: str, pauses: Mapping[str, Any] | None = None,
                     ladders: Mapping[str, LadderFiles] | None = None) -> dict[str, Callable[[], str]]:
    """Gunluk ozetin okudugu bolumler: yalniz duraklatma (ve varsa risk kademesi); gerisi `build_report` icinde / panelde."""
    out: dict[str, Callable[[], str]] = {}
    if pauses:                                                   # 11 §9.5: bot basina duraklatma satiri
        out["Duraklatma"] = lambda: rapor_duraklatma(pauses)
    if ladders:                                                  # 12 §9: bot basina tek satir
        out["Risk kademesi"] = lambda: "\n".join(
            "📶 " + ladder_line(b, ladder_view(lf, now)) for b, lf in ladders.items())
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
# Haftalik ozet (ayri mesaj; pazar gunu bir kez)
# ---------------------------------------------------------------------------
def haftalik_metni(cfg: TelegramConfig, now: datetime) -> str:
    """Son 7 gunun ozeti (defter + ML1; sayilar panodaki ML1 sekmesiyle ayni). En cok 10 satir."""
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
    try:
        st = json.loads(Path(cfg.status_path).read_text(encoding="utf-8"))
        if (k := _kasa_toplam_satiri(cfg, st)):
            lines.append(k)
    except Exception:  # noqa: BLE001
        pass
    oz, aktif = _ml1_veri(cfg, now)
    lines += _ml1_satirlari(oz, aktif, hafta=True)
    if closed:
        en = max(closed, key=lambda t: t.realized_pnl or 0.0)
        kt = min(closed, key=lambda t: t.realized_pnl or 0.0)
        s = f"En iyi: {TS.coin(en.pair)} {TS.isaretli(en.realized_pnl or 0.0)} $"
        if (kt.realized_pnl or 0.0) < 0:
            s += f" · En kötü: {TS.coin(kt.pair)} {TS.isaretli(kt.realized_pnl or 0.0)} $"
        lines.append(s)
    return TS.etiketle("\n".join(lines[:TS.MAX_SATIR_OZET]))


HAFTALIK_TELEGRAM = True                        # pazar gunu, gunluk ozetin ardindan ayri mesaj (ML1 satirlariyla)


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


SAATLIK_ISLEM_MESAJI = 4          # saatte en cok bu kadar tekil islem mesaji; fazlasi saat sonunda tek ozet


def _kol_haritasi(path: str) -> dict:
    """trade_id -> okunur kol adi ('Trend geri çekilmesi · 4 saat'); ledger salt okunur. arm_id yoksa setup@trigger_tf; okunamazsa bos."""
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
    """Saatlik sinir: ilk 4 mesaj sessiz gider; sonrakiler `delta` ile ozete eklenir."""
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
    Ilk calismada mevcut islemler 'bildirilmis' sayilir. Saatte en cok 4 tekil islem mesaji; ayni dakikadaki acilislar tek
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
        kararlar = {d.id: (d.trigger_tf, MG.skor(d)) for d in led.list_decisions(since_ts=now - timedelta(days=3))}
    finally:
        led.close()
    kollar = _kol_haritasi(cfg.ledger_path)

    def zd_puan(t) -> tuple[str, float | None]:
        """Zaman dilimi ve ML1 puani: kararin kaydindan; karar 3 gunden eskiyse zaman dilimi kol haritasindan (puan yok)."""
        tf, puan = kararlar.get(t.decision_id, (None, None))
        return tf or str(kollar.get(t.trade_id) or "").partition(" · ")[2], puan

    kol = lambda t: TS.kurulum_adi(t.setup)  # noqa: E731
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
        zd, puan = zd_puan(t)
        yeni_acilan.setdefault(t.entry_ts.strftime("%Y-%m-%dT%H:%M"), []).append(
            (t, (kol(t), t.pair, t.side, t.entry_price, (t.qty or 0.0) * (t.entry_price or 0.0), t.planned_stop, zd, puan,
                 t.planned_risk)))
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
        zd, _puan = zd_puan(t)
        gitti = _saat_gonder(kayit, now, TS.islem_kapandi(kol(t), t.pair, t.side, pnl, (t.qty or 0.0) * (t.entry_price or 0.0),
                                                          t.exit_reason, r=t.r_multiple, zd=zd,
                                                          sure=TS.sure_metni(t.entry_ts, t.exit_ts), setup=t.setup,
                                                          hedef=t.planned_target),
                             notifier, f"islem-kapat:{t.trade_id}", {"kapanan": 1, "net": pnl})
        if gitti:
            gonderildi_yaz(cfg.var_dir, now, "kapandi", t, pnl)
        sent += gitti
    try:
        atomic_write_json(imp, {"acilan": sorted(acilan)[-500:], "kapanan": sorted(kapanan)[-500:]})
    except Exception:  # noqa: BLE001
        pass
    return sent + zarar_tick(cfg, notifier, now)


def dayaniklilik_tick(cfg: TelegramConfig, notifier: "TelegramNotifier", now: datetime) -> int:
    """Motor status.json `dayaniklilik` blogundan GECIS bildirimleri: sembol TRADING disi (acik pozisyonsuz WARN / pozisyonlu CRIT; geri donunce INFO). Onceki durum
    `alarm_kaydi.json` durum('dayaniklilik') icinde; ilk okumada mevcut durum bildirilir (tek sefer)."""
    try:
        blk = json.loads(Path(cfg.status_path).read_text(encoding="utf-8")).get("dayaniklilik")
    except Exception:  # noqa: BLE001
        return 0
    if not isinstance(blk, dict):
        return 0
    kayit = notifier.kayit
    prev = kayit.durum("dayaniklilik") or {}
    s_now = {str(r.get("cift")): str(r.get("alert") or "WARN") for r in blk.get("sembol") or [] if isinstance(r, dict)}
    s_prev = dict(prev.get("sembol") or {})
    sent = 0

    def send(text: str, sev: str, key: str) -> None:
        nonlocal sent
        sent += int(bool(notifier.send_text(text, sev, key)))

    for c, sev in s_now.items():
        if c not in s_prev:
            send(TS.sembol_disi(c, sev == "CRIT"), sev, f"sembol:{c}:{int(now.timestamp())}")
    for c in s_prev:
        if c not in s_now:
            send(TS.sembol_geri(c), "INFO", f"sembol-geri:{c}:{int(now.timestamp())}")
    if s_now != s_prev:
        kayit.durum_yaz("dayaniklilik", {"sembol": s_now})
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
