"""Giris duraklatma (11 §9): "girisleri durdur, pozisyonlari koru". Kalici dosya, nedenli tutuslar.

Degismezler: dosya varligi = etkin (bozuk icerik de etkin, fail-closed); motor yalniz `add` cagirir, `remove` cli.py ve
Telegram /devam yolundadir (AST koruma testi); `add` idempotenttir ve ilk kokeni korur; her add/remove `flock` altinda ve denetim
gunlugune yazilir. Zamani `Clock` verir.
"""
from __future__ import annotations

import fcntl
import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .clock import Clock
from .fileio import atomic_write_json, fmt_ts

log = logging.getLogger(__name__)

SCHEMA = "pause/1"
REASONS = ("user_cmd", "drawdown_review", "capital_floor", "unknown_position", "late_fill", "exchange_ban", "exchange_auth",
           "manual", "stop_failed_repeat", "wallet_above_expected", "capital_latch")      # DD-8 O4: wallet_above_expected (cuzdan tavani asildi; yalniz sunucuda CLI ile kalkar). 12: capital_floor (son taban); DD-6: stop_failed_repeat (24 sa'te 2. stop_failed) - ikisi de yalniz sunucuda CLI ile kalkar
UNREADABLE = "unreadable"
AUDIT_NAME = "pause_audit.jsonl"


def last_audit_op(audit_path: str, reason: str) -> str | None:
    """Denetim gunlugunda `reason` icin SON satirin islemi ("add" | "remove" | "rearm" = mandal yeniden silahlandi); yok/okunamaz -> None (yeniden baslatma kararlari)."""
    last = None
    try:
        with open(audit_path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("reason") == reason and d.get("op") in ("add", "remove", "rearm"):
                    last = d["op"]
    except OSError:
        return None
    return last


@dataclass(frozen=True)
class PauseHold:
    reason: str
    by: str
    at: str | None
    note: str


def _unreadable(raw: str) -> tuple[PauseHold, ...]:
    return (PauseHold(UNREADABLE, "system", None, raw[:200]),)


def _parse(raw: str) -> tuple[PauseHold, ...] | None:
    """Gecerli semada tutuslar; aksi halde None."""
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("schema") != SCHEMA or not isinstance(d.get("holds"), list) or not d["holds"]:
        return None
    out = []
    for h in d["holds"]:
        if (not isinstance(h, dict) or not isinstance(h.get("reason"), str) or not isinstance(h.get("by"), str)
                or not isinstance(h.get("note", ""), str) or not (h.get("at") is None or isinstance(h.get("at"), str))):
            return None
        out.append(PauseHold(h["reason"], h["by"], h.get("at"), h.get("note", "")))
    return tuple(out)


class EntryPause:
    def __init__(self, path: str, clock: Clock, audit_path: str | None = None, bot: str | None = None) -> None:
        self.path = str(path)
        self.clock = clock
        self.audit_path = str(audit_path) if audit_path else str(Path(self.path).parent / AUDIT_NAME)
        self.bot = bot if bot is not None else (Path(self.path).name.rpartition(".")[2] or "")

    # ------------------------------------------------------------------ okuma
    def active(self) -> bool:
        try:
            os.stat(self.path)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        return True

    def _raw(self) -> str | None:
        try:
            return Path(self.path).read_bytes().decode("utf-8", errors="replace")
        except FileNotFoundError:
            return None
        except OSError as e:
            return f"unreadable: {type(e).__name__}"

    def holds(self) -> tuple[PauseHold, ...]:
        raw = self._raw()
        if raw is None:
            return ()
        return _parse(raw) or _unreadable(raw)

    def last_op(self, reason: str) -> str | None:
        return last_audit_op(self.audit_path, reason)

    def mark_rearm(self, reason: str, by: str) -> None:
        """Mandalin yeniden silahlandigini denetim gunlugune yazar (op "rearm"); tutus dosyasina dokunmaz. Hata yukseltmez."""
        self._check(reason)
        with self._locked():
            self._safe_audit("rearm", reason, by, "")

    def code(self) -> str | None:
        if not self.active():
            return None
        reasons = {h.reason for h in self.holds()}
        if "capital_floor" in reasons:                      # 12 §2: capital_floor -> drawdown_review -> paused
            return "capital_floor"
        return "drawdown_review" if "drawdown_review" in reasons else "paused"

    # ------------------------------------------------------------------ yazma
    @contextmanager
    def _locked(self) -> Iterator[None]:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with open(f"{self.path}.lock", "a+") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lk.fileno(), fcntl.LOCK_UN)

    def _audit(self, op: str, reason: str, by: str, note: str) -> None:
        row = {"at": fmt_ts(self.clock.now()), "op": op, "reason": reason, "by": by, "note": note}
        p = Path(self.audit_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _safe_audit(self, op: str, reason: str, by: str, note: str) -> None:
        """Durum yazildiktan sonra denetim hatasi islemi geri almaz ve yukseltmez (cagiran sessiz kalmasin diye CRITICAL)."""
        try:
            self._audit(op, reason, by, note)
        except Exception as e:  # noqa: BLE001
            log.critical("pause denetim gunlugu yazilamadi (durum degisti): op=%s reason=%s by=%s path=%s err=%s",
                         op, reason, by, self.audit_path, type(e).__name__)

    def _write(self, holds: list[PauseHold]) -> None:
        atomic_write_json(self.path, {"schema": SCHEMA, "bot": self.bot, "holds": [
            {"reason": h.reason, "by": h.by, "at": h.at, "note": h.note} for h in holds]})

    @staticmethod
    def _check(reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"reason gecersiz: {reason!r} (izinli: {REASONS})")

    def add(self, reason: str, by: str, note: str = "") -> bool:
        """Ayni nedenli tutus varsa DEGISTIRMEZ (ilk at/by korunur) -> False. Bozuk dosyaya dokunulmaz (zaten etkin)."""
        self._check(reason)
        with self._locked():
            raw = self._raw()
            cur: list[PauseHold] = []
            if raw is not None:
                parsed = _parse(raw)
                if parsed is None:
                    return False
                cur = list(parsed)
            if any(h.reason == reason for h in cur):
                return False
            cur.append(PauseHold(reason, by, fmt_ts(self.clock.now()), note))
            self._write(cur)
            self._safe_audit("add", reason, by, note)
            return True

    def remove(self, reason: str, by: str) -> bool:
        """Yalniz cli.py / Telegram cagirir (motor degil). Son tutus kalkinca dosya silinir; "unreadable" kalkmaz."""
        if reason != UNREADABLE:
            self._check(reason)
        with self._locked():
            raw = self._raw()
            if raw is None:
                return False
            cur = _parse(raw)
            if cur is None or not any(h.reason == reason for h in cur):
                return False
            left = [h for h in cur if h.reason != reason]
            if left:
                self._write(left)
            else:
                os.unlink(self.path)
            self._safe_audit("remove", reason, by, "")
            return True
