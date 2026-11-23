"""ML-G7: acik pozisyon (OI) ve long/short orani toplayici. YALNIZ okuma: Binance USDⓈ-M herkese acik /futures/data/* uclari
(API anahtari yok, imzali uc yok, yalniz GET). Sonuc `var/market.sqlite` icinde YENI tablo `positioning_5m`.

Uclar (period=5m; en fazla ~30 gun geriye; limit<=500):
  openInterestHist               -> oi, oi_value
  globalLongShortAccountRatio    -> gls_ratio, gls_long, gls_short
  topLongShortAccountRatio       -> tpa_ratio, tpa_long, tpa_short
  topLongShortPositionRatio      -> tpp_ratio, tpp_long, tpp_short
  takerlongshortRatio            -> taker_ratio (buySellRatio), taker_buy, taker_sell

`ts` = API'nin `timestamp` alani, AYNEN (UTC ms). Bunun periyot basi mi sonu mu oldugu ayrica dogrulanmadi; ozellik
uretiminde ileriye bakma olmamasi icin tuketici ts'yi "en erken ts + 5 dk'dan sonra bilinir" diye ele almalidir (plan Bolum 3.3-C).

KILITLI DONEM (trader_engine.holdout.HOLDOUT, 2026-05-01..2026-11-01): bu modul o araliga ait ts'yi ne ister ne yazar
(istek pencereleri kilitli donemden once/sonra diye bolunur; gelen satirlar ayrica suzulur).

Tablo tek yazar degildir: feed `bars/funding/...` yazar, bu modul yalniz `positioning_5m` yazar (WAL + busy_timeout). Feed'in
SCHEMA_VERSION/user_version'una DOKUNMAZ. Saat ve uyku enjekte edilir (test icin); gunluge anahtar/baslik yazilmaz.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from trader_core.ban_store import BanGuard
from trader_engine.holdout import HOLDOUT, KILIT_ACIK
from trader_engine.types import pair_symbol

log = logging.getLogger("trader.oi")

BASE_URL = "https://fapi.binance.com"
PERIOD = "5m"
PERIOD_MS = 300_000
PAGE_LIMIT = 500
LOOKBACK_MS = 30 * 86_400_000
LOOKBACK_MARGIN_MS = 2 * 3_600_000          # "30 gun" siniri tam degil; 2 saat iceride kal
HOLDOUT_START_MS = int(HOLDOUT[0].timestamp() * 1000)
HOLDOUT_END_MS = int(HOLDOUT[1].timestamp() * 1000)
USER_AGENT = "trader-oi-collector/1"
OI_WEIGHT_CEILING = 1200                    # DD-7 T: dakikalik IP siniri 2400'un %50'si; kullanilan agirlik buna ulasinca kosu durur
BAN_418_DEFAULT_S = 120.0

# endpoint adi -> (yol, {tablo kolonu: yanit alani}); ilk kolon "anahtar kolon" (son satir ve bosluk tespiti)
ENDPOINTS: dict[str, tuple[str, dict[str, str]]] = {
    "oi": ("/futures/data/openInterestHist", {"oi": "sumOpenInterest", "oi_value": "sumOpenInterestValue"}),
    "gls": ("/futures/data/globalLongShortAccountRatio",
            {"gls_ratio": "longShortRatio", "gls_long": "longAccount", "gls_short": "shortAccount"}),
    "tpa": ("/futures/data/topLongShortAccountRatio",
            {"tpa_ratio": "longShortRatio", "tpa_long": "longAccount", "tpa_short": "shortAccount"}),
    "tpp": ("/futures/data/topLongShortPositionRatio",
            {"tpp_ratio": "longShortRatio", "tpp_long": "longAccount", "tpp_short": "shortAccount"}),
    "taker": ("/futures/data/takerlongshortRatio",
              {"taker_ratio": "buySellRatio", "taker_buy": "buyVol", "taker_sell": "sellVol"}),
}
METRIC_COLS = tuple(c for _, (_, m) in ENDPOINTS.items() for c in m)

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS positioning_5m(
  pair TEXT NOT NULL, ts INTEGER NOT NULL,
  {", ".join(f"{c} REAL" for c in METRIC_COLS)},
  fetched_at INTEGER NOT NULL,
  PRIMARY KEY(pair, ts)) WITHOUT ROWID;
"""


class CollectorError(Exception):
    pass


class BanError(CollectorError):
    """418 / 429 (bekleme tavani asildi): bu kosuyu durdur."""


class WeightStop(Exception):
    """DD-7: kullanilan agirlik tavana ulasti; kosu hatasiz durur (CollectorError DEGIL: hata sayilmaz)."""


class GeoBlockError(CollectorError):
    """451: bu makineden Binance vadeli yok."""


# ------------------------------------------------------------------ holdout
def in_holdout(ts_ms: int) -> bool:
    return (not KILIT_ACIK) and HOLDOUT_START_MS <= ts_ms < HOLDOUT_END_MS


def clip_windows(start_ms: int, end_ms: int) -> list[tuple[int, int]]:
    """[start,end] (ms, kapali) araligini kilitli donemin DISINDAKI parcalara boler (bos olabilir)."""
    out: list[tuple[int, int]] = []
    if start_ms > end_ms:
        return out
    if KILIT_ACIK:                   # 23.11.2026 kullanici karari: kilit acik, pencere bolunmez
        return [(start_ms, end_ms)]
    if start_ms < HOLDOUT_START_MS:
        out.append((start_ms, min(end_ms, HOLDOUT_START_MS - 1)))
    if end_ms >= HOLDOUT_END_MS:
        out.append((max(start_ms, HOLDOUT_END_MS), end_ms))
    return [w for w in out if w[0] <= w[1]]


# ------------------------------------------------------------------ ayristirma
def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def parse_rows(endpoint: str, payload) -> list[dict]:
    """JSON listesi -> [{'ts': int, kolon: float|None, ...}] ; bozuk satirlar atlanir (gunluge sayi yazilir)."""
    cols = ENDPOINTS[endpoint][1]
    if not isinstance(payload, list):
        raise CollectorError(f"{endpoint}: beklenmeyen yanit turu {type(payload).__name__}")
    out, bad = [], 0
    for r in payload:
        try:
            ts = int(r["timestamp"])
        except (KeyError, TypeError, ValueError):
            bad += 1
            continue
        row = {"ts": ts}
        for col, field_ in cols.items():
            row[col] = _num(r.get(field_)) if isinstance(r, dict) else None
        if all(row[c] is None for c in cols):
            bad += 1
            continue
        out.append(row)
    if bad:
        log.warning("event=parse_skipped endpoint=%s bad=%d", endpoint, bad)
    return out


# ------------------------------------------------------------------ depo
def open_db(path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), isolation_level=None, timeout=5.0)
    db.execute("PRAGMA busy_timeout=5000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(_SCHEMA)
    return db


def upsert(db: sqlite3.Connection, pair: str, rows: Iterable[dict], fetched_at_ms: int) -> int:
    """(pair, ts) uzerinde idempotent birlestirme: gelen None eski degeri ezmez. Kilitli donem satirlari ATLANIR."""
    cols = list(METRIC_COLS)
    ins = ", ".join(["pair", "ts", *cols, "fetched_at"])
    ph = ", ".join("?" * (len(cols) + 3))
    sets = ", ".join([f"{c}=COALESCE(excluded.{c}, {c})" for c in cols] + ["fetched_at=excluded.fetched_at"])
    sql = f"INSERT INTO positioning_5m({ins}) VALUES({ph}) ON CONFLICT(pair, ts) DO UPDATE SET {sets}"
    data = [(pair, r["ts"], *[r.get(c) for c in cols], fetched_at_ms) for r in rows if not in_holdout(r["ts"])]
    if not data:
        return 0
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executemany(sql, data)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return len(data)


def last_ts(db: sqlite3.Connection, pair: str, endpoint: str) -> int | None:
    key = next(iter(ENDPOINTS[endpoint][1]))
    r = db.execute(f"SELECT MAX(ts) FROM positioning_5m WHERE pair=? AND {key} IS NOT NULL", (pair,)).fetchone()
    return r[0]


# ------------------------------------------------------------------ HTTP
_wall = time.time      # varsayilan saat kaynagi (sleep=time.sleep varsayilani gibi referans; enjekte edilebilir)


def _sys_now_ms() -> int:
    return int(_wall() * 1000)


def _retry_after_s(headers, default: float) -> float:
    """Retry-After saniye; yok / sayi degil / sonlu degil / negatif ise `default`."""
    try:
        v = float(headers.get("Retry-After")) if headers else default
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) and v >= 0 else default


@dataclass
class HttpClient:
    base_url: str = BASE_URL
    timeout_s: float = 15.0
    max_attempts: int = 4
    backoff_s: float = 1.0
    min_interval_s: float = 0.4          # ~150 istek/dk; borsa siniri 1000/5dk/IP
    max_retry_after_s: float = 120.0
    sleep: Callable[[float], None] = time.sleep
    mono: Callable[[], float] = time.monotonic
    requests_made: int = 0
    _last: float = field(default=-1e9, repr=False)
    ban_guard: BanGuard | None = None          # DD-7: kalici ban dosyasi
    now_ms: Callable[[], int] = _sys_now_ms
    last_used_weight: int | None = None        # son basarili yanitin X-MBX-USED-WEIGHT-1M basligi

    def _note_ban(self, wait_s: float, http: int) -> None:
        g = self.ban_guard
        if g is None:
            return
        try:
            ok = g.note(int(self.now_ms()) + int(wait_s * 1000), http)
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            log.error("event=ban_persist_failed http=%d", http)

    def get_json(self, path: str, params: dict):
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        last_err: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            g = self.ban_guard
            if g is not None:                                  # DD-7: yasak penceresinde istek atilmaz
                rec = g.active()
                if rec is not None:
                    left = max(1, -(-(rec.until_ms - int(self.now_ms())) // 1000))
                    raise BanError(f"kalici yasak penceresi (http={rec.http}, kalan {left} sn); istek gonderilmedi")
            wait = self.min_interval_s - (self.mono() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.mono()
            self.requests_made += 1
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    self._read_weight(getattr(resp, "headers", None))
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                code = e.code
                if code == 451:
                    raise GeoBlockError("HTTP 451 (konum kisiti)") from e
                if code == 418:
                    self._note_ban(_retry_after_s(e.headers, BAN_418_DEFAULT_S), 418)
                    raise BanError("HTTP 418 (IP yasagi)") from e
                if code == 429:
                    try:
                        ra = float(e.headers.get("Retry-After", 60)) if e.headers else 60.0
                    except (TypeError, ValueError):
                        ra = 60.0
                    self._note_ban(ra if ra > 0 else 60.0, 429)
                    if attempt >= self.max_attempts or ra > self.max_retry_after_s:
                        raise BanError(f"HTTP 429 (Retry-After={ra:g}s)") from e
                    log.warning("event=rate_limited path=%s retry_after_s=%g", path, ra)
                    self.sleep(ra)
                    last_err = e
                    continue
                if 400 <= code < 500:
                    raise CollectorError(f"HTTP {code} {path}") from e      # yeniden denemek anlamsiz
                last_err = e
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
                last_err = e
            if attempt < self.max_attempts:
                d = self.backoff_s * 2 ** (attempt - 1)
                log.warning("event=retry path=%s attempt=%d err=%s sleep_s=%g", path, attempt, type(last_err).__name__, d)
                self.sleep(d)
        raise CollectorError(f"{path}: {self.max_attempts} denemede basarisiz ({type(last_err).__name__})")


    def _read_weight(self, headers) -> None:
        """Basarili yanitta X-MBX-USED-WEIGHT-1M tam sayiya cevrilebiliyorsa saklanir; yok/bozuksa deger degismez."""
        if not headers:
            return
        try:
            v = headers.get("X-MBX-USED-WEIGHT-1M")
            if v is None:
                return
            self.last_used_weight = int(str(v).strip())
        except (TypeError, ValueError, AttributeError):
            return


# ------------------------------------------------------------------ toplama
def _weight_hit(client, ceiling: int | None) -> bool:
    w = getattr(client, "last_used_weight", None)
    return ceiling is not None and isinstance(w, int) and not isinstance(w, bool) and w >= ceiling


@dataclass
class Stats:
    rows: int = 0
    requests: int = 0
    errors: int = 0
    budget_hit: bool = False
    weight_stop: bool = False
    per_pair: dict = field(default_factory=dict)


def fetch_window(client: HttpClient, endpoint: str, symbol: str, start_ms: int, end_ms: int, *,
                 weight_ceiling: int | None = None) -> list[dict]:
    """[start,end] araligini limit*5dk'lik dilimlerle ceker (dilim <= limit satir: yanit kirpilmaz, sayfalama varsayimi gerekmez)."""
    path = ENDPOINTS[endpoint][0]
    span = PAGE_LIMIT * PERIOD_MS
    out: list[dict] = []
    cur = start_ms
    while cur <= end_ms:
        if _weight_hit(client, weight_ceiling):            # DD-7: yarim pencere yazilmaz (cagirana WeightStop yukselir)
            raise WeightStop()
        hi = min(end_ms, cur + span - 1)
        payload = client.get_json(path, {"symbol": symbol, "period": PERIOD, "limit": PAGE_LIMIT,
                                         "startTime": cur, "endTime": hi})
        out.extend(r for r in parse_rows(endpoint, payload) if cur <= r["ts"] <= hi and not in_holdout(r["ts"]))
        cur = hi + 1
    return out


def plan_window(last: int | None, now_ms: int) -> tuple[int, int]:
    """Bosluk penceresi: son saklanan satirdan (dahil: son satir yarim olabilir) simdiye; en fazla ~30 gun geriye."""
    floor = now_ms - LOOKBACK_MS + LOOKBACK_MARGIN_MS
    start = floor if last is None else max(last, floor)
    start -= start % PERIOD_MS
    return start, now_ms


def collect(db: sqlite3.Connection, client: HttpClient, pairs: Sequence[str], now_ms: int, *,
            endpoints: Sequence[str] = tuple(ENDPOINTS), max_requests: int = 900,
            weight_ceiling: int = OI_WEIGHT_CEILING) -> Stats:
    st = Stats()
    for pair in pairs:
        symbol = pair_symbol(pair)
        pstat = st.per_pair.setdefault(pair, 0)
        for ep in endpoints:
            if client.requests_made >= max_requests:
                st.budget_hit = True
                break
            if _weight_hit(client, weight_ceiling):
                st.budget_hit = st.weight_stop = True
                break
            start, end = plan_window(last_ts(db, pair, ep), now_ms)
            try:
                for lo, hi in clip_windows(start, end):
                    rows = fetch_window(client, ep, symbol, lo, hi, weight_ceiling=weight_ceiling)
                    n = upsert(db, pair, rows, now_ms)
                    st.rows += n
                    pstat += n
            except WeightStop:
                st.budget_hit = st.weight_stop = True
                log.warning("event=weight_stop pair=%s endpoint=%s used_weight=%s", pair, ep, getattr(client, "last_used_weight", None))
                break
            except (BanError, GeoBlockError):
                st.requests = client.requests_made
                raise
            except CollectorError as e:
                st.errors += 1
                log.error("event=fetch_failed pair=%s endpoint=%s err=%s", pair, ep, e)
        st.per_pair[pair] = pstat
        if st.budget_hit:
            break
    st.requests = client.requests_made
    return st
