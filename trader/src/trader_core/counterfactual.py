"""Alinmayan sinyallerin varsayimsal sonucu (plan 25a; docs/alinmayan-sinyal-spec.md).

Atlanan her karar (`final_action='skipped'`, her `skip_reason`), karar mumunun kapanisindan sonraki 1 saatlik mumlarda
yeniden oynatilir: (a) `barrier` = uclu bariyer (-1R stop, +2R hedef,
72 mum zaman), (b) `plan` = defterdeki planned_stop/planned_target, 48 mumluk ufukta. Sonuc `counterfactual.sqlite`'e
(var/<bot>/, bu isin TEK yazari) yazilir. Defter ve market.sqlite yalnizca `mode=ro` acilir. WP-13: kurulum zaman dilimleri (15dk/1s/4s/1g; 1g = 6 x 4s), kayma seansa gore (cost_overrides; yoksa taban 5 bp).
Bagimlilik: trader_core.arm_time (saf, stdlib; eskiden trader_engine.bars/arm_guard). trader_engine / trader_ml / pandas ice aktarilmaz.

Sizinti kurali: bir karar ancak ufku (72 mum) TAMAMEN dolduktan ve pencere mumlari kapanis sonrasi yazilmis, eksiksiz
bulunduktan sonra hesaplanir; erken bariyer vurusu bile beklenir. Bir kez yazilan satir degismez (idempotent).
"""
from __future__ import annotations

import math
import os
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from trader_core import arm_time as AT

__all__ = ["VERSION", "HORIZON_BARS", "PLAN_HORIZON_BARS", "TARGET_R", "FEE_RATE", "SLIPPAGE_RATE", "replay", "cost_in_r", "CounterfactualStore",
           "run_once", "summary", "outcomes", "RunResult", "CounterfactualError",
           "run_shadow", "shadow_outcomes", "ShadowRunResult",
           "ARM_TF_MS", "BASE_SLIP", "arm_rows", "arm_candidates", "arm_scorecard", "arm_virtual_bankroll"]

VERSION = 2                          # 2: plan ufku 48 mum; target yanlis tarafta -> invalid_plan
# --- etiket sabitleri (kilit bayragi trader_engine.holdout / trader_ml.config kopyalariyla testle esit); etiket degisirse VERSION artar
HORIZON_BARS = 72
PLAN_HORIZON_BARS = 48                # `plan` yontemi: planlanan stop/hedef icin ders kaniti ufku (<= HORIZON_BARS)
TARGET_R = 2.0
FEE_RATE = 0.0005                     # taraf basina
SLIPPAGE_RATE = 0.0005                # taraf basina
# 23.11.2026 kullanici karari: kilit ACIK (trader_engine.holdout.KILIT_ACIK'in kopyasi; esitlik testle denetlenir)
KILIT_ACIK = True
HOLDOUT_START = datetime(2026, 5, 1, tzinfo=timezone.utc)
HOLDOUT_END = datetime(2026, 11, 1, tzinfo=timezone.utc)
GAP_GRACE = timedelta(hours=24)       # ufuk dolduktan sonra bu kadar bekleyip hala eksik mum varsa 'data_gap' yazilir
BAR_MS = 3_600_000
METHODS = ("barrier", "plan")
MARKET_SCHEMA_VERSION = 1             # trader_engine.marketdata.store.SCHEMA_VERSION'in kopyasi (salt okunur dogrulama)
STORE_SCHEMA_VERSION = 2              # 2: cf_outcomes += arm_id, session_tag, asset_class (WP-13); 1 -> 2 kolon ekleme
ARM_TF_MS = {tf: int(AT.arm_tf_delta(tf).total_seconds() * 1000) for tf in AT.ARM_TFS}   # 15m, 1h, 4h, 1d
DAY_MS = ARM_TF_MS["1d"]
H4_MS = ARM_TF_MS["4h"]
# Taban kayma (oran, taraf basina): kripto ve `cost_overrides`'ta olmayan cift/seans. 5 bp = SLIPPAGE_RATE (legacy taban).
BASE_SLIP = (SLIPPAGE_RATE, SLIPPAGE_RATE, SLIPPAGE_RATE)            # (giris, cikis, stop)


class CounterfactualError(Exception):
    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.code = code


def cost_in_r(entry: float, stop: float, fee_rate: float = FEE_RATE, slippage_rate: float = SLIPPAGE_RATE) -> float:
    return 2.0 * (fee_rate + slippage_rate) * entry / abs(entry - stop)


# ------------------------------------------------------------------------------------------------ saf hesap
def replay(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], side: str, entry: float, stop: float,
           target: float | None, *, horizon: int = HORIZON_BARS, fee_rate: float = FEE_RATE,
           slippage_rate: float = SLIPPAGE_RATE) -> dict | None:
    """Tek yonlu bariyer taramasi. `target=None` -> hedef yok (yalniz stop/zaman). Ayni mumda iki bariyer de degerse STOP
    once sayilir. Pencere `horizon` mumdan kisaysa ve bariyer degmediyse None (cozulmemis). Doner: {outcome (1 hedef,
    0 stop/zaman), exit_reason, r_gross, r_net, cost_r, bars_held}. R = |entry-stop|."""
    rr = abs(entry - stop)
    sgn = 1.0 if side == "long" else -1.0
    cost = 2.0 * (fee_rate + slippage_rate) * entry / rr
    n = min(len(highs), horizon)
    i_stop = i_up = None
    for i in range(n):
        h, l = highs[i], lows[i]
        if i_stop is None and ((l <= stop) if side == "long" else (h >= stop)):
            i_stop = i
        if target is not None and i_up is None and ((h >= target) if side == "long" else (l <= target)):
            i_up = i
        if i_stop is not None and i_up is not None:
            break
    t_r = abs(target - entry) / rr if target is not None else 0.0
    if i_stop is not None and (i_up is None or i_stop <= i_up):
        out, why, g, j = 0, "stop", -1.0, i_stop
    elif i_up is not None:
        out, why, g, j = 1, "target", t_r, i_up
    elif n == horizon:
        out, why, g, j = 0, "time", sgn * (closes[horizon - 1] - entry) / rr, horizon - 1
    else:
        return None
    return {"outcome": out, "exit_reason": why, "r_gross": g, "r_net": g - cost, "cost_r": cost, "bars_held": j + 1}


# ------------------------------------------------------------------------------------------------ depo
_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cf_outcomes (
  bot TEXT NOT NULL CHECK (bot IN ('learner','twin')),
  decision_id INTEGER NOT NULL,
  method TEXT NOT NULL CHECK (method IN ('barrier','plan')),
  pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT, trigger_tf TEXT,
  skip_reason TEXT NOT NULL,
  decision_ts TEXT NOT NULL,
  planned_entry REAL NOT NULL, planned_stop REAL NOT NULL, planned_target REAL,
  window_start_ts TEXT NOT NULL, window_end_ts TEXT NOT NULL,
  hyp_outcome INTEGER CHECK (hyp_outcome IS NULL OR hyp_outcome IN (0,1)),
  hyp_r_gross REAL, hyp_r_net REAL, cost_r REAL,
  exit_reason TEXT NOT NULL CHECK (exit_reason IN ('target','stop','time','data_gap','invalid_plan')),
  bars_held INTEGER,
  computed_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  arm_id TEXT, session_tag TEXT, asset_class TEXT,
  PRIMARY KEY (bot, decision_id, method));
CREATE INDEX IF NOT EXISTS ix_cf_ts ON cf_outcomes (bot, decision_ts);
CREATE TABLE IF NOT EXISTS cf_shadow_outcomes (
  bot TEXT NOT NULL CHECK (bot IN ('learner','twin')),
  shadow_id INTEGER NOT NULL,
  method TEXT NOT NULL CHECK (method IN ('barrier','plan')),
  pair TEXT NOT NULL, side TEXT NOT NULL, setup TEXT, trigger_tf TEXT,
  block TEXT NOT NULL,
  decision_ts TEXT NOT NULL,
  planned_entry REAL NOT NULL, planned_stop REAL NOT NULL, planned_target REAL,
  window_start_ts TEXT NOT NULL, window_end_ts TEXT NOT NULL,
  hyp_outcome INTEGER CHECK (hyp_outcome IS NULL OR hyp_outcome IN (0,1)),
  hyp_r_gross REAL, hyp_r_net REAL, cost_r REAL,
  exit_reason TEXT NOT NULL CHECK (exit_reason IN ('target','stop','time','data_gap','invalid_plan')),
  bars_held INTEGER,
  computed_at TEXT NOT NULL,
  version INTEGER NOT NULL,
  PRIMARY KEY (bot, shadow_id, method));
CREATE INDEX IF NOT EXISTS ix_cfs_ts ON cf_shadow_outcomes (bot, decision_ts);
"""             # WP-3 (defter-ek-alanlar 7): golge satirlar AYRI tabloda; `cf_outcomes` golge icermez; depo user_version 1 kalir


def _fmt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise CounterfactualError("saat dilimi olmayan zaman", "bad_time")
    return dt.astimezone(timezone.utc)


class CounterfactualStore:
    """counterfactual.sqlite. Tek yazar: bu is. journal_mode=DELETE (WAL yok): salt okunur okuyucular (rapor, pano, ML derlemi)
    -shm yazmadan acar. `read_only=True` -> mode=ro URI, yazma yok."""

    def __init__(self, path, *, read_only: bool = False):
        self.path = os.fspath(path)
        self.read_only = read_only
        try:
            if read_only:
                if not os.path.exists(self.path):
                    raise CounterfactualError("depo yok", "store_missing")
                self._db = sqlite3.connect("file:" + quote(os.path.abspath(self.path)) + "?mode=ro", uri=True,
                                           timeout=5.0, isolation_level=None)
                self._db.execute("PRAGMA busy_timeout=5000")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver not in (1, STORE_SCHEMA_VERSION):
                    raise CounterfactualError(f"depo sema surumu {ver}", "store_schema")
            else:
                self._db = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
                self._db.execute("PRAGMA busy_timeout=5000")
                self._db.execute("PRAGMA journal_mode=DELETE")
                self._db.execute("PRAGMA synchronous=FULL")
                ver = self._db.execute("PRAGMA user_version").fetchone()[0]
                if ver not in (0, 1, STORE_SCHEMA_VERSION):
                    raise CounterfactualError(f"depo sema surumu {ver}, beklenen {STORE_SCHEMA_VERSION}", "store_schema")
                self._db.executescript(_DDL)
                self._ensure_arm_columns()
                self._db.execute(f"PRAGMA user_version={STORE_SCHEMA_VERSION}")
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo acilamadi: {type(e).__name__}", "store_io") from e
        self._db.row_factory = sqlite3.Row

    def _ensure_arm_columns(self) -> None:
        """Sema 1 -> 2 gocu: eksik kurulum kolonlarini ekler (idempotent; veri silinmez)."""
        have = {r[1] for r in self._db.execute("PRAGMA table_info(cf_outcomes)").fetchall()}
        for col in ("arm_id", "session_tag", "asset_class"):
            if col not in have:
                self._db.execute(f"ALTER TABLE cf_outcomes ADD COLUMN {col} TEXT")

    def close(self) -> None:
        try:
            self._db.close()
        except sqlite3.Error:  # pragma: no cover
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def done_ids(self, bot: str) -> set[int]:
        """Her iki yontemi de yazilmis kararlar."""
        rows = self._db.execute("SELECT decision_id FROM cf_outcomes WHERE bot=? GROUP BY decision_id HAVING COUNT(*)=?",
                                (bot, len(METHODS))).fetchall()
        return {r[0] for r in rows}

    def done_shadow_ids(self, bot: str) -> set[int]:
        try:
            rows = self._db.execute("SELECT shadow_id FROM cf_shadow_outcomes WHERE bot=? GROUP BY shadow_id "
                                    "HAVING COUNT(*)=?", (bot, len(METHODS))).fetchall()
        except sqlite3.Error:
            return set()                                           # tablo yok (salt okunur eski depo)
        return {r[0] for r in rows}

    def insert_shadow(self, rows: Iterable[Mapping]) -> int:
        """Idempotent: ayni (bot, shadow_id, method) varsa dokunmaz. Doner: yeni eklenen satir sayisi."""
        if self.read_only:
            raise CounterfactualError("depo salt okunur", "read_only")
        cols = ("bot", "shadow_id", "method", "pair", "side", "setup", "trigger_tf", "block", "decision_ts",
                "planned_entry", "planned_stop", "planned_target", "window_start_ts", "window_end_ts", "hyp_outcome",
                "hyp_r_gross", "hyp_r_net", "cost_r", "exit_reason", "bars_held", "computed_at", "version")
        sql = (f"INSERT INTO cf_shadow_outcomes ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
               "ON CONFLICT (bot, shadow_id, method) DO NOTHING")
        n = 0
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for r in rows:
                    n += self._db.execute(sql, [r[c] for c in cols]).rowcount
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo yazma hatasi: {type(e).__name__}", "store_io") from e
        return n

    def insert(self, rows: Iterable[Mapping]) -> int:
        """Idempotent: ayni (bot, decision_id, method) varsa dokunmaz. Doner: yeni eklenen satir sayisi."""
        if self.read_only:
            raise CounterfactualError("depo salt okunur", "read_only")
        cols = ("bot", "decision_id", "method", "pair", "side", "setup", "trigger_tf", "skip_reason", "decision_ts",
                "planned_entry", "planned_stop", "planned_target", "window_start_ts", "window_end_ts", "hyp_outcome",
                "hyp_r_gross", "hyp_r_net", "cost_r", "exit_reason", "bars_held", "computed_at", "version",
                "arm_id", "session_tag", "asset_class")
        sql = (f"INSERT INTO cf_outcomes ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
               "ON CONFLICT (bot, decision_id, method) DO NOTHING")
        n = 0
        try:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for r in rows:
                    n += self._db.execute(sql, [r.get(c) for c in cols]).rowcount
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo yazma hatasi: {type(e).__name__}", "store_io") from e
        return n


# ------------------------------------------------------------------------------------------------ piyasa (salt okunur)
class _Market:
    def __init__(self, path):
        if not os.path.exists(path):
            raise CounterfactualError("market.sqlite yok", "market_missing")
        try:
            self._db = sqlite3.connect("file:" + quote(os.path.abspath(path)) + "?mode=ro", uri=True, timeout=5.0,
                                       isolation_level=None)
            self._db.execute("PRAGMA busy_timeout=5000")
            ver = self._db.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error as e:
            raise CounterfactualError(f"market.sqlite acilamadi: {type(e).__name__}", "market_unreadable") from e
        if ver != MARKET_SCHEMA_VERSION:
            self._db.close()
            raise CounterfactualError(f"market.sqlite user_version={ver}", "market_schema")

    def close(self):
        self._db.close()

    def window(self, pair: str, start_ms: int, n: int, tf: str = "1h") -> list[tuple]:
        """[start, start+n*tf) araligindaki `tf` 'last' mumlari; yalniz kapanistan SONRA yazilmis olanlar. `1d` 4s'lerden
        kurulur: yalniz TAM 6 x 4s barli UTC gunu (motor kurali; eksik gun atlanir -> cagiran veri bosluğu sayar)."""
        if tf == "1d":
            return self._window_1d(pair, start_ms, n)
        tf_ms = ARM_TF_MS[tf]
        try:
            return self._db.execute(
                "SELECT open_ms,h,l,c FROM bars WHERE kind='last' AND pair=? AND tf=? AND open_ms>=? AND open_ms<? "
                "AND written_ms>=open_ms+? ORDER BY open_ms", (pair, tf, start_ms, start_ms + n * tf_ms, tf_ms)).fetchall()
        except sqlite3.Error as e:
            raise CounterfactualError(f"market okuma hatasi: {type(e).__name__}", "market_unreadable") from e

    def _window_1d(self, pair: str, start_ms: int, n: int) -> list[tuple]:
        try:
            rows = self._db.execute(
                "SELECT open_ms,h,l,c,written_ms FROM bars WHERE kind='last' AND pair=? AND tf='4h' AND open_ms>=? AND open_ms<? "
                "ORDER BY open_ms", (pair, start_ms, start_ms + n * DAY_MS)).fetchall()
        except sqlite3.Error as e:
            raise CounterfactualError(f"market okuma hatasi: {type(e).__name__}", "market_unreadable") from e
        days: dict[int, list[tuple]] = {}
        for o, h, l, c, w in rows:
            if w < o + H4_MS:                                  # kapanistan once yazilmis: yok say
                continue
            days.setdefault(o - o % DAY_MS, []).append((o, h, l, c))
        out = []
        for day in sorted(days):
            bs = sorted(days[day])
            if [b[0] for b in bs] != [day + k * H4_MS for k in range(6)]:
                continue                                       # eksik 4s: gun bari yok
            out.append((day, max(b[1] for b in bs), min(b[2] for b in bs), bs[-1][3]))
        return out


# ------------------------------------------------------------------------------------------------ is
@dataclass
class RunResult:
    scanned: int = 0          # taranan atlanmis karar
    already: int = 0          # zaten hesaplanmis
    computed: int = 0         # bu kosuda yazilan karar
    gap: int = 0              # bunlardan 'data_gap'
    pending: int = 0          # ufuk dolmadi / pencere eksik (bekliyor)
    holdout_skipped: int = 0
    rows_written: int = 0


def _ceil_hour_ms(dt: datetime) -> int:
    ms = int(dt.timestamp() * 1000)
    return -(-ms // BAR_MS) * BAR_MS


def _ceil_ms(dt: datetime, tf_ms: int) -> int:
    ms = int(dt.timestamp() * 1000)
    return -(-ms // tf_ms) * tf_ms


def _session_slip(cost_table, pair: str, session: str | None) -> tuple[float, float, float]:
    """Seansa gore kayma (oran): (giris, cikis, stop). `cost_overrides` bps degerleri; yoksa taban (BASE_SLIP)."""
    row = ((cost_table or {}).get(pair) or {}).get(session or "open")
    if not row:
        return BASE_SLIP
    return (float(row.get("slip_entry_bps", 0.0)) * 1e-4, float(row.get("slip_exit_bps", 0.0)) * 1e-4,
            float(row.get("slip_stop_bps", 0.0)) * 1e-4)


def _priced(res, e: float, s: float, slip: tuple[float, float, float], fee_rate: float = FEE_RATE) -> dict | None:
    """Brut R sonucuna maliyeti ekler: cost_R = giris * (2 fee + s_giris + s_cikis|stop) / |giris - stop|.
    Taban (5 bp) ile eski `cost_in_r` ayni sonucu verir."""
    if res is None:
        return None
    s_in, s_out, s_stop = slip
    s_x = s_stop if res["exit_reason"] == "stop" else s_out
    cost = e * (2.0 * fee_rate + s_in + s_x) / abs(e - s)
    return {**res, "r_net": res["r_gross"] - cost, "cost_r": cost}


def _rows_for(bot, d, method, res, start, end, now, why_override=None, meta=None) -> dict:
    base = {"bot": bot, "decision_id": d.id, "method": method, "pair": d.pair, "side": d.side, "setup": d.setup,
            "trigger_tf": d.trigger_tf, "skip_reason": d.skip_reason, "decision_ts": _fmt(d.bar_close_ts),
            "planned_entry": d.planned_entry, "planned_stop": d.planned_stop, "planned_target": d.planned_target,
            "window_start_ts": _fmt(start), "window_end_ts": _fmt(end), "computed_at": _fmt(now), "version": VERSION,
            "arm_id": None, "session_tag": None, "asset_class": None, **(meta or {})}
    if res is None:
        base.update(hyp_outcome=None, hyp_r_gross=None, hyp_r_net=None, cost_r=None, bars_held=None,
                    exit_reason=why_override or "data_gap")
    else:
        base.update(hyp_outcome=res["outcome"], hyp_r_gross=res["r_gross"], hyp_r_net=res["r_net"], cost_r=res["cost_r"],
                    bars_held=res["bars_held"], exit_reason=res["exit_reason"])
    return base


def run_once(*, bot: str, decisions: Sequence, market_path, store: CounterfactualStore, now: datetime,
             horizon: int = HORIZON_BARS, dry_run: bool = False, cost_table: Mapping | None = None,
             asset_class_of=None) -> RunResult:
    """`decisions`: atlanmis DecisionRecord benzeri nesneler (id, pair, side, setup, trigger_tf, bar_close_ts, planned_*,
    skip_reason, final_action; ops. arm_id, session_tag). `now` enjekte edilir (test/lookahead). Ufku dolmamis karar HIC
    islenmez. `cost_table`: `cost_overrides` ({cift: {seans: {slip_*_bps}}}); `asset_class_of(pair)` -> kripto|hisse|emtia
    (yoksa hepsi kripto). Her satir `arm_id`, `session_tag`, `asset_class` tasir."""
    now = _utc(now)
    res = RunResult()
    done = store.done_ids(bot)
    mk = _Market(market_path)
    cls_of = asset_class_of or (lambda pair: AT.CLASS_CRYPTO)
    try:
        batch: list[dict] = []
        for d in decisions:
            if d.final_action != "skipped" or not d.skip_reason:
                continue
            res.scanned += 1
            if d.id in done:
                res.already += 1
                continue
            tf = d.trigger_tf
            cls = cls_of(d.pair)
            bar_close = _utc(d.bar_close_ts)
            sess = getattr(d, "session_tag", None) or AT.session_tag(cls, bar_close)
            meta = {"arm_id": getattr(d, "arm_id", None) or AT.arm_id_of(d.setup, tf), "session_tag": sess,
                    "asset_class": cls}
            if tf not in ARM_TF_MS:                               # bilinmeyen kurulum zaman dilimi: hesap yok
                start = end = bar_close
                for m in METHODS:
                    batch.append(_rows_for(bot, d, m, None, start, end, now, "invalid_plan", meta))
                res.computed += 1
                continue
            tf_ms = ARM_TF_MS[tf]
            start_ms = _ceil_ms(bar_close, tf_ms)
            start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
            end = start + timedelta(milliseconds=horizon * tf_ms)
            if not KILIT_ACIK and start < HOLDOUT_END and end > HOLDOUT_START:           # kilitli donem (kilit kapaliyken): okunmaz
                res.holdout_skipped += 1
                continue
            if now < end:                                              # ufuk dolmadi: sizinti yok, bekle
                res.pending += 1
                continue
            e, s, tg = d.planned_entry, d.planned_stop, d.planned_target
            ok_plan = all(isinstance(x, (int, float)) and math.isfinite(x) for x in (e, s)) and e > 0 and e != s \
                and d.side in ("long", "short") and ((s < e) if d.side == "long" else (s > e))
            if not ok_plan:
                for m in METHODS:
                    batch.append(_rows_for(bot, d, m, None, start, end, now, "invalid_plan", meta))
                res.computed += 1
                continue
            bars = mk.window(d.pair, start_ms, horizon, tf)
            expect = [start_ms + k * tf_ms for k in range(horizon)]
            if [b[0] for b in bars] != expect:
                if now >= end + GAP_GRACE:                             # veri bosluğu kalici sayilir
                    for m in METHODS:
                        batch.append(_rows_for(bot, d, m, None, start, end, now, "data_gap", meta))
                    res.computed += 1
                    res.gap += 1
                else:
                    res.pending += 1
                continue
            hi, lo, cl = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars]
            slip = _session_slip(cost_table, d.pair, sess)
            sgn = 1.0 if d.side == "long" else -1.0
            up = e + sgn * TARGET_R * abs(e - s)
            plan_tg = tg if tg is not None and math.isfinite(tg) else None
            r_bar = _priced(replay(hi, lo, cl, d.side, e, s, up, horizon=horizon, fee_rate=0.0, slippage_rate=0.0),
                            e, s, slip)
            batch.append(_rows_for(bot, d, "barrier", r_bar, start, end, now, meta=meta))
            if tg is not None and plan_tg is None:                     # hedef sonlu degil -> gecersiz plan
                batch.append(_rows_for(bot, d, "plan", None, start, end, now, "invalid_plan", meta))
            elif plan_tg is not None and not ((plan_tg > e) if d.side == "long" else (plan_tg < e)):
                batch.append(_rows_for(bot, d, "plan", None, start, end, now, "invalid_plan", meta))   # hedef kar tarafinda degil
            else:
                r_plan = _priced(replay(hi, lo, cl, d.side, e, s, plan_tg, horizon=min(horizon, PLAN_HORIZON_BARS),
                                        fee_rate=0.0, slippage_rate=0.0), e, s, slip)
                batch.append(_rows_for(bot, d, "plan", r_plan, start, end, now, meta=meta))
            res.computed += 1
        if batch and not dry_run:
            res.rows_written = store.insert(batch)
    finally:
        mk.close()
    return res


# ------------------------------------------------------------------------------------------------ okuma (rapor / ders)
def summary(path, bot: str, *, now: datetime, days: int = 7, method: str = "barrier") -> dict:
    """Son `days` gunde (karar zamanina gore) hesaplanmis sonuclar: {"n", "mean_r_net", "by_reason": {skip_reason: {"n",
    "mean_r_net"}}}. Veri bosluklu/gecersiz satirlar (r_net NULL) sayima girmez. Salt okunur; depo yoksa CounterfactualError."""
    if method not in METHODS:
        raise CounterfactualError("gecersiz yontem", "bad_method")
    since = _fmt(_utc(now) - timedelta(days=days))
    with CounterfactualStore(path, read_only=True) as st:
        try:
            rows = st._db.execute(
                "SELECT skip_reason, COUNT(*) n, AVG(hyp_r_net) m FROM cf_outcomes WHERE bot=? AND method=? "
                "AND hyp_r_net IS NOT NULL AND decision_ts>=? GROUP BY skip_reason ORDER BY skip_reason",
                (bot, method, since)).fetchall()
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    n = sum(r["n"] for r in rows)
    mean = sum(r["n"] * r["m"] for r in rows) / n if n else None
    return {"n": n, "mean_r_net": mean, "by_reason": {r["skip_reason"]: {"n": r["n"], "mean_r_net": r["m"]} for r in rows}}


def outcomes(path, bot: str, *, now: datetime, days: int = 28, method: str = "barrier") -> list[dict]:
    """Ham satirlar (karar zamani `[now-days, now)`, hesaplanmis r_net, deterministik sira). YALNIZ `now`
    itibariyla bilinen sonuclar: `window_end_ts <= now`. `plan` yalnizca version>=2 (48 mumluk ufuk). Alanlar: skip_reason,
    decision_ts, hyp_r_net, side, setup, trigger_tf, planned_entry/stop/target. Salt okunur; depo yoksa CounterfactualError."""
    if method not in METHODS:
        raise CounterfactualError("gecersiz yontem", "bad_method")
    since, until = _fmt(_utc(now) - timedelta(days=days)), _fmt(_utc(now))
    minv = 2 if method == "plan" else 1
    with CounterfactualStore(path, read_only=True) as st:
        try:
            rows = st._db.execute(
                "SELECT skip_reason, decision_ts, hyp_r_net, side, setup, trigger_tf, planned_entry, planned_stop, "
                "planned_target FROM cf_outcomes WHERE bot=? AND method=? AND version>=? "
                "AND hyp_r_net IS NOT NULL AND decision_ts>=? AND decision_ts<? AND window_end_ts<=? "
                "ORDER BY decision_ts, decision_id", (bot, method, minv, since, until, until)).fetchall()
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    return [dict(r) for r in rows]


# ------------------------------------------------------------------------------------------------ WP-3: golge adaylar (7)
@dataclass
class ShadowRunResult:
    shadow_scanned: int = 0
    shadow_computed: int = 0
    shadow_pending: int = 0
    shadow_rows_written: int = 0
    shadow_holdout_skipped: int = 0


def _shadow_rows_for(bot, d, method, res, start, end, now, why_override=None) -> dict:
    base = {"bot": bot, "shadow_id": d.id, "method": method, "pair": d.pair, "side": d.side, "setup": d.setup,
            "trigger_tf": d.trigger_tf, "block": d.block, "decision_ts": _fmt(d.bar_close_ts),
            "planned_entry": d.planned_entry, "planned_stop": d.planned_stop, "planned_target": d.planned_target,
            "window_start_ts": _fmt(start), "window_end_ts": _fmt(end), "computed_at": _fmt(now), "version": VERSION}
    if res is None:
        base.update(hyp_outcome=None, hyp_r_gross=None, hyp_r_net=None, cost_r=None, bars_held=None,
                    exit_reason=why_override or "data_gap")
    else:
        base.update(hyp_outcome=res["outcome"], hyp_r_gross=res["r_gross"], hyp_r_net=res["r_net"], cost_r=res["cost_r"],
                    bars_held=res["bars_held"], exit_reason=res["exit_reason"])
    return base


def run_shadow(*, bot: str, shadows: Sequence, market_path, store: CounterfactualStore, now: datetime,
               horizon: int = HORIZON_BARS, dry_run: bool = False) -> ShadowRunResult:
    """Golge satirlarin (`ledger.ShadowRecord` benzeri: id, pair, side, setup, trigger_tf, bar_close_ts, planned_*, block)
    karsi-olgusu: hesap `run_once` ile AYNIDIR (barrier 72 + plan 48 mum, ufuk dolmadan hesap yok, `data_gap`, kilitli donemle
    kesisen pencere okunmaz). `tf_15m` satirlari 1 saatlik izgarada oynatilir (yaklasik). Sonuc `cf_shadow_outcomes`'a
    yazilir; `cf_outcomes`'a DOKUNULMAZ."""
    now = _utc(now)
    res = ShadowRunResult()
    done = store.done_shadow_ids(bot)
    mk = _Market(market_path)
    try:
        batch: list[dict] = []
        for d in shadows:
            res.shadow_scanned += 1
            if d.id in done:
                continue
            start_ms = _ceil_hour_ms(_utc(d.bar_close_ts))
            start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
            end = start + timedelta(milliseconds=horizon * BAR_MS)
            if not KILIT_ACIK and start < HOLDOUT_END and end > HOLDOUT_START:
                res.shadow_holdout_skipped += 1
                continue
            if now < end:
                res.shadow_pending += 1
                continue
            e, s_, tg = d.planned_entry, d.planned_stop, d.planned_target
            ok_plan = all(isinstance(x, (int, float)) and math.isfinite(x) for x in (e, s_)) and e > 0 and e != s_ \
                and d.side in ("long", "short") and ((s_ < e) if d.side == "long" else (s_ > e))
            if not ok_plan:
                for m in METHODS:
                    batch.append(_shadow_rows_for(bot, d, m, None, start, end, now, "invalid_plan"))
                res.shadow_computed += 1
                continue
            bars = mk.window(d.pair, start_ms, horizon)
            expect = [start_ms + k * BAR_MS for k in range(horizon)]
            if [b[0] for b in bars] != expect:
                if now >= end + GAP_GRACE:
                    for m in METHODS:
                        batch.append(_shadow_rows_for(bot, d, m, None, start, end, now, "data_gap"))
                    res.shadow_computed += 1
                else:
                    res.shadow_pending += 1
                continue
            hi, lo, cl = [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars]
            sgn = 1.0 if d.side == "long" else -1.0
            up = e + sgn * TARGET_R * abs(e - s_)
            plan_tg = tg if tg is not None and math.isfinite(tg) else None
            batch.append(_shadow_rows_for(bot, d, "barrier", replay(hi, lo, cl, d.side, e, s_, up, horizon=horizon),
                                          start, end, now))
            if tg is not None and plan_tg is None:
                batch.append(_shadow_rows_for(bot, d, "plan", None, start, end, now, "invalid_plan"))
            elif plan_tg is not None and not ((plan_tg > e) if d.side == "long" else (plan_tg < e)):
                batch.append(_shadow_rows_for(bot, d, "plan", None, start, end, now, "invalid_plan"))
            else:
                r_plan = replay(hi, lo, cl, d.side, e, s_, plan_tg, horizon=min(horizon, PLAN_HORIZON_BARS))
                batch.append(_shadow_rows_for(bot, d, "plan", r_plan, start, end, now))
            res.shadow_computed += 1
        if batch and not dry_run:
            res.shadow_rows_written = store.insert_shadow(batch)
    finally:
        mk.close()
    return res


def shadow_outcomes(path, bot: str, *, now: datetime, days: int | None = None, method: str = "barrier") -> list[dict]:
    """Golge adaylarin hesaplanmis satirlari (salt okunur; ayri islev: `outcomes()`/`summary()` golge DONDURMEZ).
    YALNIZ `now` itibariyla bilinen sonuclar (`window_end_ts <= now`); `days=None` -> hepsi. Tablo yoksa bos liste."""
    if method not in METHODS:
        raise CounterfactualError("gecersiz yontem", "bad_method")
    until = _fmt(_utc(now))
    where, args = ["bot=?", "method=?", "hyp_r_net IS NOT NULL", "window_end_ts<=?"], [bot, method, until]
    if days is not None:
        where.append("decision_ts>=?")
        args.append(_fmt(_utc(now) - timedelta(days=days)))
    with CounterfactualStore(path, read_only=True) as st:
        try:
            rows = st._db.execute(
                "SELECT shadow_id, block, pair, side, setup, trigger_tf, decision_ts, hyp_outcome, hyp_r_net, "
                "exit_reason, planned_entry, planned_stop, planned_target FROM cf_shadow_outcomes WHERE "
                + " AND ".join(where) + " ORDER BY decision_ts, shadow_id", args).fetchall()
        except sqlite3.Error:
            return []                                              # tablo yok (gece isi henuz golge yazmadi)
    return [dict(r) for r in rows]


# ------------------------------------------------------------------------------------------------ WP-13: kurulum karnesi
def arm_rows(path, bot: str, *, method: str | None = None) -> list[dict]:
    """Hesaplanmis karsi-olgu satirlari (kurulum bazinda; `arm_id` yoksa setup@trigger_tf). Salt okunur; depo yoksa [].
    `method=None` (24.11): karar basina `plan` satiri varsa o, yoksa `barrier` (ders sistemindeki eski kuralla ayni);
    belirli yontem verilirse yalniz o."""
    if method is not None and method not in METHODS:
        raise CounterfactualError("gecersiz yontem", "bad_method")
    if not os.path.exists(os.fspath(path)):
        return []
    with CounterfactualStore(path, read_only=True) as st:
        try:
            # sema 1 depo (gece isi henuz gocurmedi): kurulum kolonlari yok -> NULL kabul edilir (salt okunur, goc yok)
            have = {r[1] for r in st._db.execute("PRAGMA table_info(cf_outcomes)").fetchall()}
            arm = "arm_id" if "arm_id" in have else "NULL"
            acl = "asset_class" if "asset_class" in have else "NULL"
            ses = "session_tag" if "session_tag" in have else "NULL"
            rows = st._db.execute(
                f"SELECT decision_id, COALESCE({arm}, setup || '@' || trigger_tf) AS arm_id, "
                f"COALESCE({acl}, 'kripto') AS asset_class, {ses} AS session_tag, skip_reason, decision_ts, hyp_r_net, method "
                "FROM cf_outcomes WHERE bot=? AND hyp_r_net IS NOT NULL "
                "AND ((method='plan' AND version>=2) OR (method='barrier' AND version>=1)) "
                "ORDER BY decision_ts, decision_id", (bot,)).fetchall()
        except sqlite3.Error as e:
            raise CounterfactualError(f"depo okuma hatasi: {type(e).__name__}", "store_io") from e
    out: dict[int, dict] = {}
    for r in rows:
        d = dict(r)
        m = d.pop("method")
        if method is not None and m != method:
            continue
        cur = out.get(d["decision_id"])
        if cur is None or (m == "plan" and cur["_m"] != "plan"):
            out[d["decision_id"]] = {**d, "_m": m}
    res = [{k: v for k, v in d.items() if k != "_m"} for d in out.values()]
    res.sort(key=lambda d: (d["decision_ts"], d["decision_id"]))
    return res


ARM_DEDUP_MUM = 48            # 24.11: ayni kol + parite + yon icin bu kadar mumluk pencerede yalniz ilk aday sayilir
_TF_DK = {"s": 1 / 60, "m": 1, "h": 60, "d": 1440, "w": 10080}


def _tf_dakika(tf: str) -> float:
    try:
        return float(tf[:-1]) * _TF_DK[tf[-1]]
    except (KeyError, ValueError, IndexError):
        return 60.0


def arm_candidates(*, decisions, trades, cf_rows, asset_class_of) -> list[dict]:
    """Kurulum adaylari (alinan + alinmayan) tek biçimde: {arm_id, asset_class, taken, ts, r, decision_id}.
    `r`: alinan icin gercek kapanmis islem R'si (`r_multiple`), alinmayan icin "alinsaydi" R'si (`hyp_r_net`); sonuc
    yoksa None (cozulmemis aday). Yalniz `entered` ve gerekceli `skipped` kararlar aday sayilir.
    Tekillestirme (24.11): ayni kol + parite + yon icin `ARM_DEDUP_MUM` (48) mumluk pencerede yalniz ILK aday sayilir
    (pencere ilk adayin zamanindan baslar, sonraki pencere ilk disarida kalan adayla acilir)."""
    r_taken = {t.decision_id: t.r_multiple for t in trades if t.r_multiple is not None}
    r_cf = {row["decision_id"]: row["hyp_r_net"] for row in cf_rows}
    out: list[dict] = []
    ilk: dict[tuple, datetime] = {}                            # (kol, parite, yon) -> pencereyi acan ilk adayin zamani
    for d in sorted(decisions, key=lambda x: (x.bar_close_ts, x.id)):
        if d.final_action == "entered":
            taken, r = True, r_taken.get(d.id)
        elif d.final_action == "skipped" and d.skip_reason:
            taken, r = False, r_cf.get(d.id)
        else:
            continue
        arm = getattr(d, "arm_id", None) or AT.arm_id_of(d.setup, d.trigger_tf)
        ts = _utc(d.bar_close_ts)
        key = (arm, d.pair, getattr(d, "side", None))
        pencere = timedelta(minutes=ARM_DEDUP_MUM * _tf_dakika(arm.partition("@")[2]))
        if key in ilk and ts - ilk[key] < pencere:             # tekilleştirme: ayni sinyal art arda mumlarda cift sayilmaz
            continue
        ilk[key] = ts
        out.append({"arm_id": arm, "asset_class": asset_class_of(d.pair), "taken": taken,
                    "ts": ts, "r": None if r is None else float(r), "decision_id": d.id})
    return out


def _mean_or_none(vals) -> float | None:
    v = [x for x in vals if x is not None]
    return math.fsum(v) / len(v) if v else None


def _arm_block(cs: list[dict]) -> dict:
    return {"candidates": len(cs), "taken": sum(1 for c in cs if c["taken"]),
            "resolved": sum(1 for c in cs if c["r"] is not None),
            "mean_r_taken": _mean_or_none(c["r"] for c in cs if c["taken"]),
            "mean_r_taken_cf": _mean_or_none(c["r"] for c in cs)}


def arm_virtual_bankroll(candidates, *, start: float = 1000.0, risk: float = 0.01, arms=()) -> dict:
    """Kurulum basina sanal kasa (yalniz rapor): arm_id -> {"taken": seri, "cf": seri}.
    `taken`: yalniz alinan ve sonucu olan adaylar; `cf`: sonucu olan tum adaylar (alinan + alinmayan 'alinsaydi').
    Seri ts'ye gore artan (esitlikte girdi sirasi), her adimda eq = eq * (1 + risk * r), eq 0'in altina inmez.
    Seri: {n, equity, return_pct, max_dd_pct} (equity/return_pct 2 ondalik; max_dd_pct pozitif, 2 ondalik).
    `arms`: aday olmayan kurulumlar da (n=0) yer alir."""
    if not start > 0 or not risk > 0:
        raise ValueError("start ve risk pozitif olmali")
    groups: dict[str, list[dict]] = {}
    for c in candidates:
        groups.setdefault(c["arm_id"], []).append(c)

    def _series(cs: list[dict]) -> dict:
        ordered = sorted(cs, key=lambda c: c["ts"])          # sorted kararlidir: esitlikte girdi sirasi korunur
        eq, peak, worst = float(start), float(start), 0.0
        for c in ordered:
            eq = max(0.0, eq * (1.0 + risk * float(c["r"])))
            peak = max(peak, eq)
            if peak > 0:
                worst = max(worst, (peak - eq) / peak * 100.0)
        equity = round(eq, 2)
        return {"n": len(ordered), "equity": equity,
                "return_pct": round((equity / start - 1.0) * 100.0, 2),
                "max_dd_pct": round(worst, 2)}

    out: dict[str, dict] = {}
    for arm in dict.fromkeys([*arms, *groups]):
        cs = groups.get(arm, [])
        out[arm] = {"taken": _series([c for c in cs if c["taken"] is True and c["r"] is not None]),
                    "cf": _series([c for c in cs if c["r"] is not None])}
    return out


def arm_scorecard(candidates, *, arms=(), closed=None) -> dict:
    """Kurulum karnesi: arm_id -> {candidates, taken, resolved, mean_r_taken (yalniz alinan), mean_r_taken_cf (alinan +
    alinmayan 'alinsaydi'), by_class: {kripto|hisse|emtia: ayni alanlar}, state: open|closed, kasa: arm_virtual_bankroll
    degeri (start=1000, risk=0.01: {taken, cf})}. `arms`: yapilandirilmis
    kurulumlar (aday yoksa da satiri vardir). `closed`: kapali kurulum kimlikleri (arms_off)."""
    closed = set(closed or ())
    groups: dict[str, list[dict]] = {}
    for c in candidates:
        groups.setdefault(c["arm_id"], []).append(c)
    bankroll = arm_virtual_bankroll(candidates, arms=arms)
    out: dict[str, dict] = {}
    for arm in dict.fromkeys([*arms, *groups]):
        cs = groups.get(arm, [])
        block = _arm_block(cs)
        block["by_class"] = {cls: _arm_block([c for c in cs if c["asset_class"] == cls])
                             for cls in sorted({c["asset_class"] for c in cs})}
        block["state"] = "closed" if arm in closed else "open"
        block["kasa"] = bankroll[arm]
        out[arm] = block
    return out
