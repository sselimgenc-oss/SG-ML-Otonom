"""state.sqlite: motorun tek yerel durumu (04 §3). Tek yazar (flock), tx() disinda yazma yok."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

from trader_core.ledger import LedgerError, TradeEntry, TradeExit, clean_exec_fields

from .bars import from_ms, to_ms
from .errors import StateError
from .types import Position, require_utc

SCHEMA_VERSION = 1

# --- giris engeli nedenleri KUMESI (DD-2 / D6 = dunku O6) ---
# Eskiden tek `entries_blocked_reason` degerini her yazan eziyordu (`engine_errors` -> `stop_failed` -> mutabakatla temizlendi).
#   * `entries_blocked_reasons` (kv, JSON liste): yapiskan kume; `block_add` digerini ezmez, `block_remove` yalniz o nedeni kaldirir.
#   * `entries_blocked_reason` (kv, metin): kumenin ONCELIKLI uyesi; kapi, status.json, panel ve Telegram bunu okur (geriye uyum).
# Elle kalkan nedenler hicbir otomatik yolla temizlenmez; yalniz `trader_engine unblock` kaldirir (kayit birakarak).
# Kume ile metin uyusmuyorsa (eski state / dis yazim) metin deger esas alinir.
BLOCK_KV_SET = "entries_blocked_reasons"
BLOCK_KV_PRIMARY = "entries_blocked_reason"
MANUAL_CLEAR_REASONS: tuple[str, ...] = ("engine_errors", "strategy_mismatch")
_BLOCK_PRIORITY: tuple[str, ...] = MANUAL_CLEAR_REASONS + (
    "reconcile_unknown_position", "reconcile_state_orphan", "reconcile_foreign_order",
    "reconcile_account_mode_drift", "reconcile_ledger_orphan", "stop_failed", "exit_unknown")


def block_primary(reasons: list[str]) -> str | None:
    """Kapida gorunen neden: once elle kalkanlar, sonra sabit oncelik, sonra eklenme sirasi."""
    if not reasons:
        return None
    return min(reasons, key=lambda r: (_BLOCK_PRIORITY.index(r) if r in _BLOCK_PRIORITY else len(_BLOCK_PRIORITY),
                                       reasons.index(r)))

_SCHEMA = """
CREATE TABLE positions(
  trade_id INTEGER PRIMARY KEY, bot TEXT NOT NULL, pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN('opening','open','closing','closed')),
  decision_id INTEGER NOT NULL, signal_bar_close_ms INTEGER NOT NULL,
  entry_ms INTEGER, entry_bar_open_ms INTEGER, entry_price REAL, qty REAL, leverage INTEGER NOT NULL,
  initial_stop REAL NOT NULL, current_stop REAL NOT NULL, stop_seq INTEGER NOT NULL DEFAULT 0, stop_client_id TEXT,
  planned_target REAL, trail_atr REAL NOT NULL, param_version_id INTEGER NOT NULL, trigger_tf TEXT NOT NULL,
  risk_amount REAL NOT NULL, margin REAL NOT NULL, rh REAL, rl REAL,
  fee_entry REAL NOT NULL DEFAULT 0, funding_paid REAL NOT NULL DEFAULT 0,
  mfe_price REAL, mae_price REAL, exit_reason TEXT, exit_client_id TEXT, closed_ms INTEGER,
  strategy_name TEXT NOT NULL DEFAULT 'price_action_v1', strategy_version TEXT NOT NULL DEFAULT '1b.0');
CREATE UNIQUE INDEX ux_pos_pair_live ON positions(pair) WHERE status != 'closed';
CREATE TABLE orders(
  client_id TEXT PRIMARY KEY, pair TEXT NOT NULL, role TEXT NOT NULL, order_side TEXT NOT NULL, qty REAL NOT NULL,
  trigger_price REAL, reduce_only INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN('pending','accepted','filled','rejected','unknown','failed','canceled','expired')),
  signal_bar_close_ms INTEGER NOT NULL, seq INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
  trade_id INTEGER, broker_order_id TEXT, detail TEXT, created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL);
CREATE TABLE decided(pair TEXT NOT NULL, bar_close_ms INTEGER NOT NULL, outcome TEXT NOT NULL, PRIMARY KEY(pair, bar_close_ms)) WITHOUT ROWID;
CREATE TABLE cursors(pair TEXT NOT NULL, kind TEXT NOT NULL, ts_ms INTEGER NOT NULL, PRIMARY KEY(pair, kind)) WITHOUT ROWID;
CREATE TABLE kv(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE ledger_outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, trade_id INTEGER NOT NULL,
  payload TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0, created_ms INTEGER NOT NULL);
"""

# Position alani -> (sutun, zaman mi)
_POS_COLS: dict[str, tuple[str, bool]] = {
    "trade_id": ("trade_id", False), "bot": ("bot", False), "pair": ("pair", False), "side": ("side", False),
    "setup": ("setup", False), "status": ("status", False), "decision_id": ("decision_id", False),
    "signal_bar_close_ts": ("signal_bar_close_ms", True), "entry_ts": ("entry_ms", True),
    "entry_bar_open": ("entry_bar_open_ms", True), "entry_price": ("entry_price", False), "qty": ("qty", False),
    "leverage": ("leverage", False), "initial_stop": ("initial_stop", False), "current_stop": ("current_stop", False),
    "stop_seq": ("stop_seq", False), "stop_client_id": ("stop_client_id", False),
    "planned_target": ("planned_target", False), "trail_atr": ("trail_atr", False),
    "param_version_id": ("param_version_id", False), "trigger_tf": ("trigger_tf", False),
    "risk_amount": ("risk_amount", False), "margin": ("margin", False), "rh": ("rh", False), "rl": ("rl", False),
    "fee_entry": ("fee_entry", False), "funding_paid": ("funding_paid", False), "mfe_price": ("mfe_price", False),
    "mae_price": ("mae_price", False), "exit_reason": ("exit_reason", False),
    "exit_client_id": ("exit_client_id", False), "closed_ts": ("closed_ms", True),
    "strategy_name": ("strategy_name", False), "strategy_version": ("strategy_version", False),
}
_ORD_COLS: dict[str, tuple[str, bool]] = {
    "client_id": ("client_id", False), "pair": ("pair", False), "role": ("role", False),
    "order_side": ("order_side", False), "qty": ("qty", False), "trigger_price": ("trigger_price", False),
    "reduce_only": ("reduce_only", False), "status": ("status", False),
    "signal_bar_close_ts": ("signal_bar_close_ms", True), "seq": ("seq", False), "attempts": ("attempts", False),
    "trade_id": ("trade_id", False), "broker_order_id": ("broker_order_id", False), "detail": ("detail", False),
    "created_ts": ("created_ms", True), "updated_ts": ("updated_ms", True),
}


def iso_z(ts: datetime) -> str:
    """UTC 'YYYY-MM-DDTHH:MM:SSZ' (saniye alti varsa mikrosaniye eklenir)."""
    require_utc(ts)
    u = ts.astimezone(timezone.utc)
    if u.microsecond:
        return u.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    return u.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_z(s: str) -> datetime:
    if not isinstance(s, str) or not s.endswith("Z"):
        raise ValueError(f"ISO-Z metin olmali: {s!r}")
    return datetime.fromisoformat(s[:-1] + "+00:00").astimezone(timezone.utc)


@dataclass(frozen=True)
class OrderRow:
    client_id: str
    pair: str
    role: str
    order_side: str
    qty: float
    trigger_price: float | None
    reduce_only: bool
    status: str
    signal_bar_close_ts: datetime
    seq: int
    attempts: int
    trade_id: int | None
    broker_order_id: str | None
    detail: str | None
    created_ts: datetime
    updated_ts: datetime


@dataclass(frozen=True)
class OutboxRow:
    id: int
    kind: str
    trade_id: int
    payload: dict
    done: bool
    created_ts: datetime


@dataclass(frozen=True)
class DrainResult:
    written: int
    failed: int
    first_error: str | None


def _enc(v: Any, is_ts: bool) -> Any:
    if v is None:
        return None
    if is_ts:
        return to_ms(v)
    if isinstance(v, bool):
        return int(v)
    return v


def _row_to_position(r: sqlite3.Row) -> Position:
    kw = {}
    for attr, (col, is_ts) in _POS_COLS.items():
        v = r[col]
        kw[attr] = from_ms(v) if (is_ts and v is not None) else v
    return Position(**kw)


def _row_to_order(r: sqlite3.Row) -> OrderRow:
    kw = {}
    for attr, (col, is_ts) in _ORD_COLS.items():
        v = r[col]
        if is_ts:
            v = from_ms(v)
        elif attr == "reduce_only":
            v = bool(v)
        kw[attr] = v
    return OrderRow(**kw)


def _ledger_has_history(path: str) -> bool:
    """Defter islem/karar satiri iceriyor mu (salt okunur; okunamazsa False: defter kendi hatasini verir). Ilk kurulumda
    yaratilip coken bos defter `dolu` sayilmaz."""
    try:
        if os.path.getsize(path) == 0:
            return False
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            for t in ("trade_entries", "decision_events"):
                if con.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() is not None:
                    return True
            return False
        finally:
            con.close()
    except (OSError, sqlite3.Error):
        return False


ledger_has_history = _ledger_has_history      # DD-8: damga denetimi ayni olcutu kullanir (tek islev)


class StateStore:
    def __init__(self, path: str, *, bot: str, durability: str = "full", lock: bool = True,
                 ledger_path: str | None = None) -> None:
        if durability not in ("full", "off"):
            raise ValueError(f"durability full|off olmali: {durability!r}")
        self.path = str(path)
        self.bot = bot
        self.durability = durability
        self._depth = 0
        self._closed = False
        self._lock_fd: int | None = None
        memory = self.path == ":memory:"
        existed = (not memory) and os.path.exists(self.path) and os.path.getsize(self.path) > 0
        if not memory and not existed and os.path.exists(self.path):
            # DD-2 D9: 0 baytlik state yeni durum sayilmaz, defter (`ledger_path`) doluysa (kayip/bozulma belirtisi) sessiz
            # kalinmaz. DD-8 (E3): defter yolu cagiran tarafindan verilir (sabit kardes yol yok); None => denetim yapilmaz.
            led = ledger_path
            if led is not None and _ledger_has_history(led):
                raise StateError(f"state dosyasi 0 bayt ama defter dolu ({led}): sessizce yeni durum acilmaz; "
                                 "yedekten donun ya da bilincli olarak 0 baytlik dosyayi silin")
        if lock and not memory:
            self._acquire_lock()
        try:
            self._con = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
            self._con.row_factory = sqlite3.Row
            self._open(existed)
        except StateError:
            self._release()
            raise
        except sqlite3.Error as e:
            self._release()
            raise StateError(f"state acilamadi: {e}") from e

    # --- aci/kapa
    def _acquire_lock(self) -> None:
        import fcntl
        try:
            fd = os.open(self.path + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
        except OSError as e:
            raise StateError(f"kilit dosyasi acilamadi: {e}") from e
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            raise StateError(f"state kilitli (baska motor calisiyor): {self.path}") from e
        self._lock_fd = fd

    def _release(self) -> None:
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)  # kapatma flock'u birakir
            except OSError:
                pass
            self._lock_fd = None

    def _open(self, existed: bool) -> None:
        c = self._con
        if self.durability == "full":
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")
        else:
            c.execute("PRAGMA journal_mode=MEMORY")
            c.execute("PRAGMA synchronous=OFF")
        uv = c.execute("PRAGMA user_version").fetchone()[0]
        has_tables = c.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] > 0
        if has_tables or uv != 0:
            if uv != SCHEMA_VERSION:
                raise StateError(f"state user_version={uv}, beklenen {SCHEMA_VERSION} (goc yok)")
            if not self.integrity_check():
                raise StateError("state integrity_check basarisiz")
            return
        if existed:  # dolu ama tanimsiz dosya
            raise StateError("state dosyasi taninmiyor")
        c.execute("BEGIN IMMEDIATE")
        try:
            for stmt in _SCHEMA.split(";\n"):
                if stmt.strip():
                    c.execute(stmt)
            c.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            c.execute("INSERT INTO kv(k, v) VALUES('initialized_at', ?)", (json.dumps("unset"),))
            c.execute("INSERT INTO kv(k, v) VALUES('bot', ?)", (json.dumps(self.bot),))
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._con.in_transaction:
                self._con.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        try:
            self._con.close()
        finally:
            self._release()

    def integrity_check(self) -> bool:
        try:
            rows = self._con.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.Error:
            return False
        return len(rows) == 1 and rows[0][0] == "ok"

    # --- islem
    def in_tx(self) -> bool:
        return self._depth > 0

    @contextmanager
    def tx(self) -> Iterator[None]:
        if self._closed:
            raise StateError("state kapali")
        if self._depth > 0:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        try:
            self._con.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as e:
            raise StateError(f"BEGIN basarisiz: {e}") from e
        self._depth = 1
        try:
            yield
        except BaseException:
            self._depth = 0
            try:
                self._con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        self._depth = 0
        try:
            self._con.execute("COMMIT")
        except sqlite3.Error as e:
            try:
                self._con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise StateError(f"COMMIT basarisiz: {e}") from e

    def barrier(self, *, allow_outer: bool) -> None:
        if self._depth == 0:
            return
        if not allow_outer:
            raise StateError("POST oncesi commit citi: dis tx icinde gercek broker emri yasak")

    def _w(self) -> None:
        if self._closed:
            raise StateError("state kapali")
        if self._depth == 0:
            raise StateError("yazma tx() disinda")

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        try:
            return self._con.execute(sql, args)
        except sqlite3.Error as e:
            raise StateError(f"sqlite hatasi: {e}") from e

    # --- pozisyonlar
    def next_trade_id(self) -> int:
        self._w()
        cur = self.kv_get("next_trade_id", 1)
        self.kv_set("next_trade_id", int(cur) + 1)
        return int(cur)

    def insert_position(self, p: Position) -> None:
        self._w()
        cols = [c for c, _ in _POS_COLS.values()]
        vals = tuple(_enc(getattr(p, a), t) for a, (_, t) in _POS_COLS.items())
        self._exec(f"INSERT INTO positions({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)

    def update_position(self, trade_id: int, **flds: Any) -> None:
        self._w()
        if not flds:
            return
        sets, vals = [], []
        for k, v in flds.items():
            if k not in _POS_COLS or k == "trade_id":
                raise ValueError(f"bilinmeyen/degistirilemez Position alani: {k!r}")
            col, is_ts = _POS_COLS[k]
            sets.append(f"{col}=?")
            vals.append(_enc(v, is_ts))
        cur = self._exec(f"UPDATE positions SET {','.join(sets)} WHERE trade_id=?", tuple(vals) + (trade_id,))
        if cur.rowcount != 1:
            raise StateError(f"pozisyon yok: {trade_id}")

    def get_position(self, trade_id: int) -> Position | None:
        r = self._exec("SELECT * FROM positions WHERE trade_id=?", (trade_id,)).fetchone()
        return _row_to_position(r) if r else None

    def position_for_pair(self, pair: str) -> Position | None:
        r = self._exec("SELECT * FROM positions WHERE pair=? AND status != 'closed'", (pair,)).fetchone()
        return _row_to_position(r) if r else None

    def open_positions(self) -> list[Position]:
        rs = self._exec("SELECT * FROM positions WHERE status IN ('opening','open','closing') ORDER BY trade_id").fetchall()
        return [_row_to_position(r) for r in rs]

    def decision_ids_in_flight(self) -> set[int]:
        """Karari hala canli bir kayda bagli olanlar: kapanmamis/dolmus pozisyon ya da teslim bekleyen outbox girisi."""
        ids = {int(r[0]) for r in self._exec(
            "SELECT decision_id FROM positions WHERE (status != 'closed' OR entry_price IS NOT NULL) AND decision_id IS NOT NULL")}
        for row in self.outbox_pending():
            if row.payload.get("decision_id") is not None:
                ids.add(int(row.payload["decision_id"]))
        return ids

    def closed_positions_since(self, since: datetime) -> list[Position]:
        rs = self._exec("SELECT * FROM positions WHERE status='closed' AND closed_ms >= ? ORDER BY closed_ms, trade_id",
                        (to_ms(since),)).fetchall()
        return [_row_to_position(r) for r in rs]

    # --- emirler
    def insert_order(self, o: OrderRow) -> None:
        self._w()
        cols = [c for c, _ in _ORD_COLS.values()]
        vals = tuple(_enc(getattr(o, a), t) for a, (_, t) in _ORD_COLS.items())
        self._exec(f"INSERT INTO orders({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)

    def update_order(self, client_id: str, **flds: Any) -> None:
        self._w()
        if not flds:
            return
        sets, vals = [], []
        for k, v in flds.items():
            if k not in _ORD_COLS or k == "client_id":
                raise ValueError(f"bilinmeyen/degistirilemez OrderRow alani: {k!r}")
            col, is_ts = _ORD_COLS[k]
            sets.append(f"{col}=?")
            vals.append(_enc(v, is_ts))
        cur = self._exec(f"UPDATE orders SET {','.join(sets)} WHERE client_id=?", tuple(vals) + (client_id,))
        if cur.rowcount != 1:
            raise StateError(f"emir yok: {client_id}")

    def get_order(self, client_id: str) -> OrderRow | None:
        r = self._exec("SELECT * FROM orders WHERE client_id=?", (client_id,)).fetchone()
        return _row_to_order(r) if r else None

    def orders_for_trade(self, trade_id: int) -> list[OrderRow]:
        rs = self._exec("SELECT * FROM orders WHERE trade_id=? ORDER BY created_ms, rowid", (trade_id,)).fetchall()
        return [_row_to_order(r) for r in rs]

    def unresolved_orders(self) -> list[OrderRow]:
        rs = self._exec("SELECT * FROM orders WHERE status IN ('pending','unknown') ORDER BY created_ms, rowid").fetchall()
        return [_row_to_order(r) for r in rs]

    # --- mum basina tek karar
    def mark_decided(self, pair: str, bar_close_ts: datetime, outcome: str) -> bool:
        self._w()
        cur = self._exec("INSERT OR IGNORE INTO decided(pair, bar_close_ms, outcome) VALUES(?,?,?)",
                         (pair, to_ms(bar_close_ts), outcome))
        return cur.rowcount == 1

    def is_decided(self, pair: str, bar_close_ts: datetime) -> bool:
        r = self._exec("SELECT 1 FROM decided WHERE pair=? AND bar_close_ms=?", (pair, to_ms(bar_close_ts))).fetchone()
        return r is not None

    # --- imecler
    def get_cursor(self, pair: str, kind: Literal["minute", "decision"]) -> datetime | None:
        r = self._exec("SELECT ts_ms FROM cursors WHERE pair=? AND kind=?", (pair, kind)).fetchone()
        return from_ms(r[0]) if r else None

    def set_cursor(self, pair: str, kind: str, ts: datetime) -> None:
        self._w()
        if kind not in ("minute", "decision"):
            raise ValueError(f"gecersiz imec turu: {kind!r}")
        ms = to_ms(ts)
        r = self._exec("SELECT ts_ms FROM cursors WHERE pair=? AND kind=?", (pair, kind)).fetchone()
        if r is not None and ms < r[0]:
            raise StateError(f"imec geri gitmez: {pair}/{kind} {ts} < {from_ms(r[0])}")
        self._exec("INSERT OR REPLACE INTO cursors(pair, kind, ts_ms) VALUES(?,?,?)", (pair, kind, ms))

    # --- DD-8 (O8): damga denetimi icin salt okunur sorgular
    def is_virgin(self) -> bool:
        """Bakir state: `positions` ve `orders` bos, kv `initialized_at` yok/"unset", kv `broker_snapshot` yok."""
        if self._exec("SELECT 1 FROM positions LIMIT 1").fetchone() is not None:
            return False
        if self._exec("SELECT 1 FROM orders LIMIT 1").fetchone() is not None:
            return False
        if self.kv_get("initialized_at") not in (None, "unset"):
            return False
        return self.kv_get("broker_snapshot") is None

    def has_paper_trace(self) -> bool:
        """Kagit izi: kv `broker_snapshot` var (yalniz kagit motoru yazar)."""
        return self.kv_get("broker_snapshot") is not None

    # --- genel
    def kv_get(self, k: str, default: Any = None) -> Any:
        r = self._exec("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else default

    def kv_prefix(self, prefix: str) -> dict[str, Any]:
        """`prefix` ile baslayan tum kv satirlari {anahtar: deger} (anahtar siralidir)."""
        rows = self._exec("SELECT k, v FROM kv WHERE substr(k, 1, ?) = ? ORDER BY k", (len(prefix), prefix)).fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    def kv_set(self, k: str, v: Any) -> None:
        self._w()
        if v is None:
            self._exec("DELETE FROM kv WHERE k=?", (k,))
            return
        try:
            s = json.dumps(v, sort_keys=True)
        except (TypeError, ValueError) as e:
            raise ValueError(f"kv degeri JSON olmali: {e}") from e
        self._exec("INSERT OR REPLACE INTO kv(k, v) VALUES(?,?)", (k, s))

    # --- giris engeli kumesi
    def block_reasons(self) -> list[str]:
        p = self.kv_get(BLOCK_KV_PRIMARY)
        s = self.kv_get(BLOCK_KV_SET)
        if isinstance(s, list) and all(isinstance(r, str) for r in s) and p == block_primary(s):
            return list(s)
        # eski state / dis yazim: metin deger esas. Not: `_BLOCK_PRIORITY` degisirse kayitli primary ile turetilen primary
        # uyusmaz; bu durumda da kume tek elemana (primary) dusurulur => uyum icin oncelik listesi degisince kume bir sonraki
        # yazimda yeniden kurulur; yalnizca ikincil uyeler kaybolabilir (oncelik degisikligi bunu goz onunde tutmali).
        return [str(p)] if p else []

    def _block_write(self, rs: list[str]) -> None:
        with self.tx():
            self.kv_set(BLOCK_KV_SET, rs or None)
            self.kv_set(BLOCK_KV_PRIMARY, block_primary(rs))

    def block_add(self, reason: str) -> bool:
        """Nedeni kumeye ekler (digerlerini ezmez). Degisiklik olduysa True."""
        rs = self.block_reasons()
        if reason in rs:
            if self.kv_get(BLOCK_KV_SET) is None:      # eski state: kume kaydini kur
                self._block_write(rs)
            return False
        self._block_write(rs + [reason])
        return True

    def block_remove(self, reason: str) -> bool:
        """Yalniz bu nedeni kaldirir; kumede yoksa dokunmaz (False)."""
        rs = self.block_reasons()
        if reason not in rs:
            return False
        self._block_write([r for r in rs if r != reason])
        return True

    def block_has(self, reason: str) -> bool:
        return reason in self.block_reasons()

    # --- ledger kuyrugu
    def outbox_add(self, kind: Literal["entry", "exit"], trade_id: int, payload: dict) -> int:
        self._w()
        if kind not in ("entry", "exit"):
            raise ValueError(f"gecersiz outbox turu: {kind!r}")
        ts = payload.get("entry_ts" if kind == "entry" else "exit_ts")
        ms = to_ms(parse_iso_z(ts)) if isinstance(ts, str) else 0
        cur = self._exec("INSERT INTO ledger_outbox(kind, trade_id, payload, done, created_ms) VALUES(?,?,?,0,?)",
                         (kind, trade_id, json.dumps(payload, sort_keys=True), ms))
        return int(cur.lastrowid)

    def outbox_pending(self) -> list[OutboxRow]:
        rs = self._exec("SELECT * FROM ledger_outbox WHERE done=0 ORDER BY id").fetchall()
        return [OutboxRow(id=r["id"], kind=r["kind"], trade_id=r["trade_id"], payload=json.loads(r["payload"]),
                          done=bool(r["done"]), created_ts=from_ms(r["created_ms"])) for r in rs]

    def outbox_done(self, outbox_id: int) -> None:
        self._w()
        self._exec("UPDATE ledger_outbox SET done=1 WHERE id=?", (outbox_id,))

    def outbox_quarantine(self, items: list[tuple[int, str]], now: datetime) -> int:
        """DD-11 Z-4: teslim edilemeyen (defter dogrulama hatasi veren) satirlari `ledger_outbox_quarantine`a tasir (gerekce +
        zaman damgasi), `ledger_outbox`tan siler. Tek tx. Tablo tembel olusturulur (sema surumune dokunmaz)."""
        n = 0
        with self.tx():
            self._exec("CREATE TABLE IF NOT EXISTS ledger_outbox_quarantine(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, "
                       "trade_id INTEGER NOT NULL, payload TEXT NOT NULL, created_ms INTEGER NOT NULL, "
                       "reason TEXT NOT NULL, quarantined_ms INTEGER NOT NULL)")
            for oid, reason in items:
                r = self._exec("SELECT * FROM ledger_outbox WHERE id=? AND done=0", (oid,)).fetchone()
                if r is None:
                    continue
                self._exec("INSERT INTO ledger_outbox_quarantine(id, kind, trade_id, payload, created_ms, reason, quarantined_ms) "
                           "VALUES(?,?,?,?,?,?,?)",
                           (r["id"], r["kind"], r["trade_id"], r["payload"], r["created_ms"], reason, to_ms(now)))
                self._exec("DELETE FROM ledger_outbox WHERE id=?", (oid,))
                n += 1
        return n

    def drain_outbox(self, ledger) -> DrainResult:
        rows = self.outbox_pending()
        written = 0
        for i, row in enumerate(rows):
            try:
                _write_ledger(ledger, row)
            except LedgerError as e:
                return DrainResult(written=written, failed=len(rows) - i, first_error=str(e) or type(e).__name__)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001 - beklenmeyen bicim hatasi sureci dusurmez; satir takili sayilir, girisler kapanir
                return DrainResult(written=written, failed=len(rows) - i, first_error=f"{type(e).__name__}: {e}")
            with self.tx():
                self.outbox_done(row.id)
            written += 1
        return DrainResult(written=written, failed=0, first_error=None)


def _write_ledger(ledger, row: OutboxRow) -> None:
    p = dict(row.payload)
    if row.kind == "entry":
        p["entry_ts"] = parse_iso_z(p["entry_ts"])
        _parse_exec_ts(p)
        p.update(clean_exec_fields(p))
        ledger.record_trade_entry(TradeEntry(**_only(TradeEntry, p)))
    else:
        p["exit_ts"] = parse_iso_z(p["exit_ts"])
        _parse_exec_ts(p)
        p.update(clean_exec_fields(p))
        ledger.record_trade_exit(TradeExit(**_only(TradeExit, p)))


def _parse_exec_ts(p: dict) -> None:
    """WP-3: emir-ani zaman alanlari (varsa) ISO-Z'den datetime'a; bozuksa NULL (olcum yazimi dusurmez)."""
    for k in ("order_ts", "order_ack_ts"):
        v = p.get(k)
        if v is None:
            continue
        try:
            p[k] = parse_iso_z(v)
        except Exception:  # noqa: BLE001
            p[k] = None


def _only(cls, p: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in p.items() if k in names}
