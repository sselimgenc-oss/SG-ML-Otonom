"""Piyasa verisi olcumu (salt okunur). Bkz. docs/saglik-spec.md Bolum 15.

`market.sqlite` yalnizca `mode=ro` URI ile acilir; `trader_engine` iceri aktarilmaz. Hicbir istisna disari sizmaz:
okunamayan girdi `*_state="unreadable"` ya da `None` olur (health.evaluate bunu fail-closed degerlendirir).
Yalnizca standart kutuphane.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from trader_core.health import MarketProbe

__all__ = ["probe_market", "canon_pair"]

MAX_BYTES = 2_000_000


def canon_pair(p: str) -> str:
    return str(p).strip().upper().split(":", 1)[0]


def _parse_dt(s):
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def _ms(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(n / 1000, tz=timezone.utc) if n > 0 else None


def _read_feed_status(path):
    """-> (state, ts, pairs_from_status)."""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_BYTES + 1)
    except FileNotFoundError:
        return "missing", None, ()
    except OSError:
        return "unreadable", None, ()
    try:
        if len(raw) > MAX_BYTES:
            raise ValueError
        d = json.loads(raw.decode("utf-8"))
        ts = _parse_dt(d.get("ts")) if isinstance(d, dict) else None
        if ts is None:
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return "unreadable", None, ()
    pairs = d.get("pairs")
    pairs = tuple(canon_pair(p) for p in pairs) if isinstance(pairs, list) and all(isinstance(p, str) for p in pairs) else ()
    return "ok", ts, pairs


def _read_engine_counter(status_path, bot):
    try:
        with open(status_path, "rb") as f:
            d = json.loads(f.read(MAX_BYTES).decode("utf-8"))
        v = d["counters"]["rules_missing"]
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError):
        return None
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def probe_market(*, db_path: str, feed_status_path: str, pairs, engine_status_paths: dict | None = None,
                 pair_classes: dict | None = None) -> MarketProbe:
    """pairs: yapilandirilmis ciftler; feed-status.json listesi ile birlesir (tekrarsiz, yapilandirilmis once).
    pair_classes: cift -> varlik sinifi (seans kapaliyken mum beklenmez).
    engine_status_paths: bot -> status.json yolu (rules_missing sayaci icin)."""
    fs_state, fs_ts, fs_pairs = _read_feed_status(feed_status_path)
    plist = tuple(dict.fromkeys([canon_pair(p) for p in (pairs or ())] + list(fs_pairs)))   # yapilandirilmis once, sonra feed'in gercek listesi
    counters = {b: _read_engine_counter(p, b) for b, p in (engine_status_paths or {}).items()}
    base = dict(feed_status_state=fs_state, feed_status_at=fs_ts, pairs=plist, rules_missing=counters,
                pair_classes={canon_pair(k): v for k, v in (pair_classes or {}).items()})
    if not os.path.exists(db_path):
        return MarketProbe(db_state="missing", **base)
    newest, rules_count, fetched = {}, None, None
    try:
        c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        try:
            for p in plist:
                r = c.execute("SELECT MAX(open_ms) FROM bars WHERE kind='last' AND pair=? AND tf='1m'", (p,)).fetchone()
                newest[p] = _ms(r[0]) if r else None
            rules_count = int(c.execute("SELECT COUNT(*) FROM rules").fetchone()[0])
            r = c.execute("SELECT v FROM feed_meta WHERE k='rules_fetched_at'").fetchone()
            fetched = _ms(r[0]) if r else None
        finally:
            c.close()
    except Exception:  # noqa: BLE001 - fail-closed
        return MarketProbe(db_state="unreadable", **base)
    return MarketProbe(db_state="ok", newest_bar_at=newest, rules_count=rules_count, rules_fetched_at=fetched, **base)
