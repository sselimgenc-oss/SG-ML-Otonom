"""Salt okunur okuyucular: defter, trades.csv, karsi-olgu deposu, mumlar, borsa kurallari, butce.
Tum SQLite acilislari `open_ro` uzerinden gecer (mode=ro + query_only). Kilitli donem satirlari SQL'de elenir."""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from . import guard
from .guard import BacktestArgError

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS = timedelta(milliseconds=1)
TF_MS = {"15m": 900_000, "1h": 3_600_000}
LOW_TS, HIGH_TS = "0000", "9999"


FALLBACK_LOG: list = []   # immutable acilis kullanilan dosyalar (rapor uyarisi icin)


class ReportError(Exception):
    def __init__(self, code: str, msg: str = "") -> None:
        super().__init__(msg or code)
        self.code = code


# --------------------------------------------------------------------------- zaman yardimcilari
def iso_ms(s: str) -> int:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (d - EPOCH) // _MS



def dt_ms(d: datetime) -> int:
    return (d.astimezone(timezone.utc) - EPOCH) // _MS


def ms_dt(ms: int) -> datetime:
    return EPOCH + timedelta(milliseconds=ms)


def ceil_hour(ms: int) -> int:
    return -(-ms // 3_600_000) * 3_600_000


def floor_to(ms: int, tf_ms: int) -> int:
    return (ms // tf_ms) * tf_ms


# --------------------------------------------------------------------------- sqlite
def open_ro(path, missing_code: str = "ledger_missing") -> sqlite3.Connection:
    """Tek SQLite acilis yardimcisi. Dosya yoksa olusturulmaz (`missing_code`)."""
    p = Path(path)
    if not p.is_absolute():
        p = Path(os.path.abspath(p))
    if not p.is_file():
        raise ReportError(missing_code, f"dosya yok: {p}")
    last = None
    wal = Path(str(p) + "-wal")
    wal_busy = wal.is_file() and wal.stat().st_size > 0
    for uri_extra in ("", "&immutable=1"):   # ikincisi yalniz salt okunur dizinde ve bos/yok -wal ile
        if uri_extra and wal_busy:
            break
        uri = "file:" + quote(str(p)) + "?mode=ro" + uri_extra
        for attempt in range(2):
            try:
                conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute("PRAGMA query_only=ON")
                conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
                if uri_extra:
                    FALLBACK_LOG.append(p.name)
                return conn
            except sqlite3.OperationalError as e:
                last = e
                if "locked" in str(e).lower() and attempt == 0:
                    continue
                break
        if last is None or not any(m in str(last).lower() for m in ("unable to open", "readonly database")):
            break
    raise ReportError(missing_code.replace("_missing", "_unreadable"), f"{p}: {last}")


def run_query(conn: sqlite3.Connection, sql: str, params=()):
    """Sorgu basina ayri ortuk islem; kilit hatasinda bir kez yeniden dene. Imlecle akitilir."""
    for attempt in range(2):
        try:
            cur = conn.execute(sql, params)
            return cur
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt == 0:
                continue
            raise ReportError("ledger_unreadable", str(e)) from e
    raise ReportError("ledger_unreadable")


def _dicts(cur):
    names = [c[0] for c in cur.description]
    for row in cur:
        yield dict(zip(names, row))


def user_version(conn) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def check_ledger_schema(conn) -> int:
    uv = user_version(conn)
    if uv not in (2, 3, 4, 5, 6, 7, 8):   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
        raise ReportError("ledger_schema", f"defter sema surumu {uv}; 2..8 bekleniyor")
    return uv


def has_view(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','table') AND name = ?", (name,)).fetchone() is not None


def has_column(conn, table: str, col: str) -> bool:
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})"))


# --------------------------------------------------------------------------- veri
def _atr_of(features_json) -> tuple[float | None, float | None]:
    """features JSON'undan yalniz atr (atr_tf, yoksa atr_1h) ve stop_dist_atr tutulur."""
    if not features_json:
        return None, None
    try:
        f = json.loads(features_json)
    except (TypeError, ValueError):
        return None, None
    a = f.get("atr_tf")
    if a is None:
        a = f.get("atr_1h")
    s = f.get("stop_dist_atr")
    return (float(a) if isinstance(a, (int, float)) else None, float(s) if isinstance(s, (int, float)) else None)


def _bound(ts: str | None, default: str) -> str:
    return ts if ts else default


def load_decisions(conn, since: str | None, until: str | None) -> tuple[list[dict], int]:
    """Donemdeki yerine gecilmemis kararlar; kilitli donem satirlari SQL'de elenir. (satirlar, atlanan atlanmis-karar sayisi; girilen kararlar kendi islemiyle birlikte sayilir)."""
    sel = ("SELECT id, bar_close_ts, trigger_tf, pair, side, setup, regime, atr_ratio, features, planned_entry, planned_stop, "
           "veto_status, veto_reason, risk_reason, leverage, final_action, skip_reason FROM v_decisions ")
    p = {"since": _bound(since, LOW_TS), "until": _bound(until, HIGH_TS), **guard.PARAMS}
    per = "bar_close_ts >= :since AND bar_close_ts < :until"
    lock = guard.ts_lock_sql("bar_close_ts")
    # kilitli donemle kesisen bir islemin giris karari de okunmaz (islem satiri atlandigi icin)
    tlock = ("id NOT IN (SELECT t.decision_id FROM v_closed_trades t WHERE t.decision_id IS NOT NULL AND "
             + guard.TRADE_LOCK_SQL + ")")
    out = []
    for r in _dicts(run_query(conn, sel + f"WHERE {per} AND NOT {lock} AND {tlock} ORDER BY id", p)):
        r["atr"], r["stop_dist_atr"] = _atr_of(r.pop("features"))
        r["gun"] = r["bar_close_ts"][:10]
        out.append(r)
    n_skip = run_query(conn, f"SELECT COUNT(*) FROM v_decisions WHERE {per} AND {lock} AND final_action = 'skipped'", p).fetchone()[0]
    return out, int(n_skip)


def load_shadow(conn, since: str | None, until: str | None) -> list[dict] | None:
    """WP-3 8-2: golge karar satirlari (`v_shadow_decisions`; sema 4). Gorunum yoksa None (sema < 4). Kilitli donem
    korumasi gölge satir okumasina da uygulanir (SQL'de elenir). Satirlar karar paydasina GIRMEZ."""
    if not has_view(conn, "v_shadow_decisions"):
        return None
    p = {"since": _bound(since, LOW_TS), "until": _bound(until, HIGH_TS), **guard.PARAMS}
    per = "bar_close_ts >= :since AND bar_close_ts < :until"
    lock = guard.ts_lock_sql("bar_close_ts")
    sql = ("SELECT id, block, bar_close_ts, pair, side, setup, trigger_tf, pos_open FROM v_shadow_decisions "
           f"WHERE {per} AND NOT {lock} ORDER BY id")
    return [r for r in _dicts(run_query(conn, sql, p))]


def load_cf_shadow(path, bot: str, now_iso: str, since, until, shadow_ids: set | None) -> dict | None:
    """Golge adaylarin karsi-olgusu (`cf_shadow_outcomes`). Depo yoksa/okunamazsa None; tablo henuz yoksa {}.
    Yalniz window_end_ts <= now; kilitli donem korumasi decision_ts'te. Sonuc: {shadow_id: {'barrier'|'plan': satir|None}}."""
    p = Path(path)
    if not p.is_file():
        return None
    conn = open_ro(p, "cf_missing")
    try:
        if not has_view(conn, "cf_shadow_outcomes"):
            return {}
        try:
            q = {"bot": bot, "now": now_iso, "since": _bound(since, LOW_TS), "until": _bound(until, HIGH_TS), **guard.PARAMS}
            per = "decision_ts >= :since AND decision_ts < :until AND bot = :bot"
            lock = guard.ts_lock_sql("decision_ts")
            sql = ("SELECT shadow_id, method, version, exit_reason, hyp_outcome, hyp_r_net, hyp_r_gross, decision_ts, "
                   "window_start_ts, window_end_ts, planned_entry, planned_stop, pair, side FROM cf_shadow_outcomes "
                   f"WHERE {per} AND window_end_ts <= :now AND NOT {lock} ORDER BY shadow_id, method")
            cf: dict = {}
            for r in _dicts(run_query(conn, sql, q)):
                if shadow_ids is not None and r["shadow_id"] not in shadow_ids:
                    continue
                if r["method"] == "plan" and (r["version"] or 0) < 2:
                    continue
                cf.setdefault(r["shadow_id"], {"barrier": None, "plan": None})[r["method"]] = r
            return cf
        except ReportError:
            return None
    finally:
        conn.close()


_TRADE_COLS = ("trade_id", "decision_id", "pair", "side", "setup", "regime", "atr_ratio", "entry_ts", "exit_ts", "entry_price",
               "exit_price", "qty", "leverage", "planned_entry", "planned_stop", "planned_target", "exit_reason", "planned_risk",
               "gross_pnl", "realized_pnl", "r_multiple", "mfe_r", "mae_r", "bars_held", "excursion_tf")


def _finish_trade(t: dict) -> dict:
    pr = t["planned_risk"]
    t["net_r"] = t["r_multiple"]
    t["gross_r"] = (t["gross_pnl"] / pr) if pr else None
    t["r_px"] = (pr / t["qty"]) if (pr and t.get("qty")) else None
    t["gun"] = t["entry_ts"][:10]
    if t.get("bar_close_ts") is None:
        t["bar_close_ts"] = t["entry_ts"]
    return t


def load_trades_ledger(conn, since, until, with_exit_regime: bool) -> tuple[list[dict], int]:
    """v_closed_trades (yalniz gorunumler). Girdi karari bilgisi (atr, bar_close_ts) v_decisions'tan, kilit disi satirlar icin."""
    p = {"since": _bound(since, LOW_TS), "until": _bound(until, HIGH_TS), **guard.PARAMS}
    vcols = {r[1] for r in conn.execute("PRAGMA table_info(v_closed_trades)")}
    sel = ", ".join(f"t.{c}" for c in _TRADE_COLS)
    xr = ""
    if with_exit_regime and "exit_regime" in vcols:
        xr = ", t.exit_regime AS exit_regime"
    sql = (f"SELECT {sel}{xr} FROM v_closed_trades t "
           f"WHERE t.exit_ts >= :since AND t.exit_ts < :until AND NOT {guard.TRADE_LOCK_SQL} ORDER BY t.exit_ts, t.trade_id")
    out = [r for r in _dicts(run_query(conn, sql, p))]
    info = _decision_info(conn, [r["decision_id"] for r in out if r.get("decision_id") is not None])
    for r in out:
        d = info.get(r["decision_id"])
        r["atr"] = d[1] if d else None
        r["bar_close_ts"] = d[0] if d else None
        _finish_trade(r)
    cnt = (f"SELECT COUNT(*) FROM v_closed_trades t WHERE t.exit_ts >= :since AND t.exit_ts < :until AND {guard.TRADE_LOCK_SQL}")
    return out, int(run_query(conn, cnt, p).fetchone()[0])


def _decision_info(conn, ids) -> dict:
    """{karar_id: (bar_close_ts, atr)}; kilitli donem satirlari SQL'de elenir (sabit sinirlar guard'dan)."""
    res: dict = {}
    ids = sorted(set(ids))
    lock = f"(bar_close_ts < '{guard.H1_ISO}' AND bar_close_ts >= '{guard.H0_PAD_ISO}')"
    for k in range(0, len(ids), 500):
        chunk = ids[k:k + 500]
        q = "SELECT id, bar_close_ts, features FROM v_decisions WHERE id IN (" + ",".join("?" * len(chunk)) + f") AND NOT {lock}"
        for i, ts, f in run_query(conn, q, chunk):
            res[i] = (ts, _atr_of(f)[0])
    return res


def _f(s):
    if s is None or s == "":
        return None
    return float(s)


def load_trades_csv(path, since, until, dec_by_id: dict) -> tuple[list[dict], int]:
    """trades.csv: kilitli donem satirlari ayristirmanin ilk isinde elenir (baska alan okunmaz)."""
    p = Path(path)
    if not p.is_file():
        raise ReportError("trades_missing", f"trades.csv yok: {p}")
    lo, hi = _bound(since, LOW_TS), _bound(until, HIGH_TS)
    out, skipped = [], 0
    with open(p, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            en, ex = row.get("entry_ts") or "", row.get("exit_ts") or ""
            if not ex or not (lo <= ex < hi):
                continue
            if guard.trade_locked(en, ex):
                skipped += 1
                continue
            t = {c: row.get(c) for c in _TRADE_COLS if c in row}
            for c in ("entry_price", "exit_price", "qty", "planned_entry", "planned_stop", "planned_target", "planned_risk",
                      "gross_pnl", "realized_pnl", "r_multiple", "mfe_r", "mae_r", "bars_held"):
                t[c] = _f(t.get(c))
            t["trade_id"] = int(t["trade_id"])
            did = row.get("decision_id")
            t["decision_id"] = int(did) if did not in (None, "") else None
            t["leverage"] = _f(t.get("leverage"))
            t["equity_at_entry"] = _f(row.get("equity_at_entry"))
            d = dec_by_id.get(t["decision_id"])
            t["atr_ratio"] = d["atr_ratio"] if d else None
            t["atr"] = d["atr"] if d else None
            t["bar_close_ts"] = d["bar_close_ts"] if d else None
            if t["r_multiple"] is None or not t["planned_risk"]:
                continue
            out.append(_finish_trade(t))
    out.sort(key=lambda t: (t["exit_ts"], t["trade_id"]))
    return out, skipped


def load_cf(path, bot: str, now_iso: str, since, until, decision_ids: set | None) -> tuple[dict | None, int, str | None]:
    """Karsi-olgu deposu. (cf, atlanan, uyari). cf: {decision_id: {'barrier': satir|None, 'plan': satir|None}}.
    Yalniz window_end_ts <= now satirlari okunur."""
    p = Path(path)
    if not p.is_file():
        return None, 0, "cf_missing"
    conn = open_ro(p, "cf_missing")
    try:
        try:
            q = {"bot": bot, "now": now_iso, "since": _bound(since, LOW_TS), "until": _bound(until, HIGH_TS), **guard.PARAMS}
            per = "decision_ts >= :since AND decision_ts < :until AND bot = :bot"
            lock = guard.ts_lock_sql("decision_ts")
            sql = ("SELECT decision_id, method, version, exit_reason, hyp_outcome, hyp_r_net, hyp_r_gross, decision_ts, "
                   "window_start_ts, window_end_ts, planned_entry, planned_stop, pair, side FROM cf_outcomes "
                   f"WHERE {per} AND window_end_ts <= :now AND NOT {lock} ORDER BY decision_id, method")
            cf: dict = {}
            for r in _dicts(run_query(conn, sql, q)):
                if decision_ids is not None and r["decision_id"] not in decision_ids:
                    continue
                if r["method"] == "plan" and (r["version"] or 0) < 2:
                    continue
                cf.setdefault(r["decision_id"], {"barrier": None, "plan": None})[r["method"]] = r
            n_skip = run_query(conn, f"SELECT COUNT(*) FROM cf_outcomes WHERE {per} AND {lock}", q).fetchone()[0]
        except ReportError:
            return None, 0, "cf_unreadable"
        return cf, int(n_skip), None
    finally:
        conn.close()


def veto_cost_usd(path, since: str | None, until: str | None):
    """Veto maliyeti (USD). Dosya yoksa None."""
    p = Path(path)
    if not p.is_file():
        return None
    conn = open_ro(p, "budget_missing")
    try:
        lo = (since or "")[:10] or "0000-00-00"
        hi = (until or "")[:10] or "9999-99-99"
        row = conn.execute("SELECT COALESCE(SUM(charged_micro), 0) FROM reservations WHERE service = 'veto' "
                           "AND state = 'settled' AND day >= ? AND day <= ?", (lo, hi)).fetchone()
        return float(row[0]) / 1e6
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()


# --------------------------------------------------------------------------- mumlar
class BarReader:
    """window(pair, tf, start_ms, n) -> [(open_ms, h, l, c)]. Her cagri I/O'dan ONCE kilitli donem korumasindan gecer
    (kesisme => BacktestArgError, okuma yapilmaz). Yalniz 1h ve 15m."""
    source = "?"

    def window(self, pair: str, tf: str, start_ms: int, n: int):
        if tf not in TF_MS:
            raise ReportError("bars_tf", f"yalniz 1h/15m okunur: {tf}")
        guard.check_window(start_ms, n, TF_MS[tf])
        return self._read(pair, tf, start_ms, n)

    def _read(self, pair, tf, start_ms, n):  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:
        return None


class SqliteBars(BarReader):
    def __init__(self, path) -> None:
        self.conn = open_ro(path, "market_missing")
        uv = user_version(self.conn)
        if uv != 1:
            raise ReportError("market_schema", f"market.sqlite sema surumu {uv}; 1 bekleniyor")
        self.source = "market.sqlite"

    def _read(self, pair, tf, start_ms, n):
        ms = TF_MS[tf]
        cur = self.conn.execute(
            "SELECT open_ms, h, l, c FROM bars WHERE kind = 'last' AND pair = ? AND tf = ? AND open_ms >= ? AND open_ms < ? "
            "AND written_ms >= open_ms + ? ORDER BY open_ms", (pair, tf, start_ms, start_ms + n * ms, ms))
        return [(int(a), float(h), float(l), float(c)) for a, h, l, c in cur]

    def close(self) -> None:
        self.conn.close()

    def rules(self) -> dict:
        try:
            return {p: j for p, j in self.conn.execute("SELECT pair, json FROM rules")}
        except sqlite3.OperationalError:
            return {}


class FeatherBars(BarReader):
    """<PAIR>_USDT_USDT-<tf>-futures.feather; memory_map. Yalniz `date` sutunu konum bulmak icin taranir."""

    def __init__(self, directory) -> None:
        self.dir = Path(directory)
        if not self.dir.is_dir():
            raise ReportError("history_missing", f"gecmis dizini yok: {self.dir}")
        self._cache: dict = {}
        self.source = f"feather:{self.dir.name}"

    def _file(self, pair, tf):
        base = pair.replace("/", "_")
        return self.dir / f"{base}_USDT-{tf}-futures.feather"

    def _load(self, pair, tf):
        key = (pair, tf)
        if key not in self._cache:
            path = self._file(pair, tf)
            if not path.is_file():
                self._cache[key] = None
            else:
                import pyarrow as pa
                import pyarrow.feather as feather
                pa.set_cpu_count(1)
                pa.set_io_thread_count(1)
                tbl = feather.read_table(str(path), columns=["date", "high", "low", "close"], memory_map=True)
                ms = tbl.column("date").cast(pa.timestamp("ms", tz="UTC")).cast(pa.int64()).to_numpy()
                self._cache[key] = (tbl, ms)
                if len(self._cache) > 4:     # bellek tavani: en eski dosyayi birak
                    self._cache.pop(next(iter(self._cache)))
        return self._cache[key]

    def _read(self, pair, tf, start_ms, n):
        import numpy as np
        ent = self._load(pair, tf)
        if ent is None:
            return []
        tbl, ms = ent
        ms_len = TF_MS[tf]
        i = int(np.searchsorted(ms, start_ms, "left"))
        j = int(np.searchsorted(ms, start_ms + n * ms_len, "left"))
        if j <= i:
            return []
        sl = tbl.slice(i, j - i)
        h = sl.column("high").to_numpy(zero_copy_only=False)
        l = sl.column("low").to_numpy(zero_copy_only=False)
        c = sl.column("close").to_numpy(zero_copy_only=False)
        return [(int(ms[i + k]), float(h[k]), float(l[k]), float(c[k])) for k in range(j - i)]


def get_window(reader: BarReader | None, pair: str, tf: str, start_ms: int, n: int):
    """(durum, satirlar): 'ok' | 'holdout_skipped' | 'data_gap'. Eksik/kismi pencere kullanilmaz."""
    if reader is None or n <= 0:
        return "data_gap", None
    try:
        rows = reader.window(pair, tf, start_ms, n)
    except BacktestArgError:
        return "holdout_skipped", None
    step = TF_MS[tf]
    if len(rows) != n or any(r[0] != start_ms + k * step for k, r in enumerate(rows)):
        return "data_gap", None
    for r in rows:
        if not (r[1] == r[1] and r[2] == r[2] and r[3] == r[3]):  # NaN
            return "data_gap", None
    return "ok", rows


# --------------------------------------------------------------------------- borsa kurallari
Rules = namedtuple("Rules", "step min_qty min_notional source")
SYNTH_MIN_NOTIONAL = {"BTC/USDT": 100.0, "ETH/USDT": 20.0}
SYNTH_LABEL = "SENTETİK kural"


def _norm_pair(p: str) -> str:
    p = p.strip().upper()
    if "/" not in p and "_" in p:
        a, b = p.split("_", 1)
        p = f"{a}/{b.split('_')[0]}"
    return p


def parse_synth_steps(items) -> dict:
    out = {}
    for it in items or ():
        if "=" not in it:
            raise ReportError("arg_error", f"--synthetic-step PAIR=DEGER bekleniyor: {it}")
        k, v = it.split("=", 1)
        try:
            out[_norm_pair(k)] = float(v)
            if not out[_norm_pair(k)] > 0:
                raise ValueError("pozitif olmali")
        except ValueError as e:
            raise ReportError("arg_error", f"--synthetic-step sayi degil: {it}") from e
    return out


def load_rules(pairs, sqlite_rules: dict | None, history_dir, synthetic: bool, synth_steps: dict) -> dict:
    """{pair: Rules | None}. Oncelik: market.sqlite -> <history>/rules.json -> --synthetic-rules (acikca)."""
    from trader_engine.exchange.rules import spec_from_json, to_symbol_rules
    out: dict = {}
    jfile = None
    if history_dir:
        jp = Path(history_dir) / "rules.json"
        if jp.is_file():
            try:
                jfile = json.loads(jp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                jfile = None

    def conv(pair, raw, src):
        try:
            sr = to_symbol_rules(pair, spec_from_json(raw if isinstance(raw, str) else json.dumps(raw)))
            return Rules(sr.step, sr.min_qty, sr.min_notional, src)
        except Exception:  # noqa: BLE001 bozuk kural => bu kaynak yok sayilir
            return None

    for pair in pairs:
        r = None
        if sqlite_rules and pair in sqlite_rules:
            r = conv(pair, sqlite_rules[pair], "market.sqlite")
        if r is None and isinstance(jfile, dict) and pair in jfile:
            r = conv(pair, jfile[pair], "rules.json")
        if r is None and synthetic and pair in synth_steps:
            st = synth_steps[pair]
            r = Rules(st, st, SYNTH_MIN_NOTIONAL.get(pair, 5.0), SYNTH_LABEL)
        out[pair] = r
    return out


def iso_week(ts: str) -> str:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def utc_dt(ts: str) -> datetime:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
