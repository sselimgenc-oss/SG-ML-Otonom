"""trader-feed: REST yoklama ile market.sqlite'i dolduran TEK yazar (01 §5). pandas/numpy/requests import etmez.

Saat yalnizca enjekte edilen Clock'tan okunur; sleep da Clock.sleep. Tasarim yalniz fikir olarak alinmistir; kod kopyalanmamistir.
"""
from __future__ import annotations

import argparse
import dataclasses
import fcntl
import hashlib
import json
import logging
import os
import random
import signal
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from trader_engine.bars import (aggregate_minutes, expected_opens, floor_tf, from_ms, last_closed_open,
                                tf_delta, to_ms)
from trader_engine.clock import Clock
from trader_engine.errors import ClockError, DataError, FailClosed
from trader_engine.exchange.rules import RulesError, extract_all_rules, spec_to_json
from trader_engine.fileio import atomic_write_json, fmt_ts
from trader_engine.marketdata.rest_public import ExchangeBan, ExchangeError, PublicRestClient, rows_to_bars
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar, FundingPoint, MinuteBar, canon_pair, pair_symbol

log = logging.getLogger("engine.feed")

SERIES_TFS = ("1m", "15m", "1h", "4h")
TF_CLOSE_TFS = ("15m", "1h", "4h")
EXIT_BAN = 3
EXIT_STORE = 4
EXIT_RULES = 5          # acilista kurallar (retry sonrasi) alinamadi
EXIT_GEOBLOCK = 6       # HTTP 451: bu makineden Binance vadeli erisimi yok (tekrar denemek anlamsiz)
MAX_CONSEC_BANS = 6
MAX_CONSEC_STORE_FAIL = 3
CLOCK_WARN_MS = 60_000
CLOCK_FATAL_MS = 300_000
RETRY_THROTTLE_MS = 5_000
TF_GIVEUP_MS = 60_000
BAN_MARGIN_S = 5                # her yasak uykusuna eklenen guvenlik payi
BAN_418_DEFAULT_S = 120         # 418 ve Retry-After okunamadi: en az bu kadar uyu
BAN_MAX_WAIT_S = 3600           # yasakta surec ici uyku ust siniri; asilirsa cikis 3 (birim yeniden baslatmaz, alarm)
FUNDING_FIRST_LOOKBACK_MS = 30 * 86_400_000
_DAY_MS = 86_400_000
_FUNDING_GRID_MS = 3_600_000     # funding kaydi kendi saatine yazilir (1s/4s/8s sembol); izgara sabiti saat


def _floor_funding_ms(ms: int) -> int:
    """fundingTime'i saat basina tabana yuvarla (aralik-bagimsiz; 12:00:00.005 -> 12:00): 4s/1s kayitlar 8s izgarasina dusmez."""
    return ms - ms % _FUNDING_GRID_MS


def _next_funding_boundary_ms(now_ms: int) -> int:
    """now_ms'den SONRAKI saat siniri (her saat sorulur: 1s/4s/8s semboller icin kayit saat basinda gelir)."""
    return _floor_funding_ms(now_ms) + _FUNDING_GRID_MS


def _default_backfill() -> Mapping[str, int]:
    return {"1m": 4320, "15m": 5000, "1h": 1500, "4h": 3700}      # 4s: 1g penceresi (WINDOW_ARM["1d"] = 600 gun x 6) icin; yalniz BOS depoda ilk doldurma derinligi


@dataclass(frozen=True)
class FeedConfig:
    pairs: tuple[str, ...]
    db_path: str
    lock_path: str
    status_path: str
    optional_pairs: tuple[str, ...] = ()    # DD-12 §2: kurali/verisi gelmeyen isteğe bagli cift sureci dusurmez
    contract_types: tuple[str, ...] = ("PERPETUAL",)
    grace_s: float = 3.0
    minute_fetch_limit: int = 5
    backfill_bars: Mapping[str, int] = field(default_factory=_default_backfill)
    funding_refresh_s: float = 3600.0      # yedek periyodik cekim
    funding_boundary_delay_s: float = 5.0  # her saat basi + birkac saniye
    rules_refresh_s: float = 3600.0
    retention_1m_days: int = 14
    rules_start_backoff_s: tuple[float, ...] = (5.0, 15.0, 45.0)   # acilis kural cekimi: len+1 deneme, sonra cikis
    # --- DD-1 ---
    startup_retry_forever: bool = False     # True: acilista ag/5xx/bozuk JSON hatasinda suresiz ustel geri cekilme (+jitter)
    startup_backoff_base_s: float = 5.0
    startup_backoff_cap_s: float = 300.0
    heal_page_bars: int = 1000              # calisirken bosluk doldurma: istek basina en fazla bar (agirlik 5)
    heal_min_interval_s: float = 2.0        # iki doldurma istegi arasi en az sure (tum seriler icin ortak)
    heal_weight_ceiling: int = 1200         # kullanilan dakikalik agirlik bunu gecmisken doldurma yapilmaz (limit 2400)
    heal_backoff_base_s: float = 30.0       # basarisiz/ilerlemeyen doldurma icin seri basina ustel bekleme
    heal_backoff_cap_s: float = 600.0       # ilerlemeyen (bos/bozuk veri) doldurma icin
    heal_net_backoff_base_s: float = 10.0   # ag/5xx/bozuk JSON hatasinda doldurma bekleme: 10,20,40,60 (tavan)
    heal_net_backoff_cap_s: float = 60.0
    heal_giveup_strikes: int = 3            # yalniz BASARILI ama ilerlemeyen cevaplar sayilir


class RulesFetchError(FailClosed):
    """Acilista borsa kurallari alinamadi (feed baslamaz; surec sifirdan farkli kodla cikar)."""

    def __init__(self, message: str, *, geoblock: bool = False) -> None:
        super().__init__(message)
        self.geoblock = geoblock

    @property
    def exit_code(self) -> int:
        return EXIT_GEOBLOCK if self.geoblock else EXIT_RULES


GEOBLOCK_MSG = ("HTTP 451: Binance vadeli (fapi) bu makinenin bulundugu konumdan engelli; kurallar alinamaz. "
                "Sunucuyu/bolgeyi degistirmeden feed ve paper baslatilamaz")


@dataclass(frozen=True)
class BackfillReport:
    bars_written: int = 0
    duplicates: int = 0
    conflicts: int = 0
    gaps_marked: int = 0
    errors: int = 0
    skipped_pairs: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedTick:
    now_ms: int
    bars_written: int = 0
    errors: int = 0
    gaps: int = 0
    conflicts: int = 0
    banned: bool = False
    skipped: str | None = None


class RulesSnapshot(dict):
    """{pair: spec_json}; basarisiz ciftler `errors`'ta (pair -> mesaj), `exit_code` 0 | 1."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.errors: dict[str, str] = {}

    @property
    def exit_code(self) -> int:
        return 1 if self.errors else 0


def snapshot_rules(rest: PublicRestClient, pairs: Sequence[str], clock: Clock, *, store: MarketStore | None = None,
                   out_json_path: str | None = None, contract_types: Sequence[str] = ("PERPETUAL",)) -> dict[str, str]:
    """exchangeInfo -> extract_all_rules -> {pair: spec_json}. RulesError veren cift atlanir (sonuc.errors, exit_code=1)."""
    info = rest.exchange_info()
    cpairs = [canon_pair(p) for p in pairs]
    res = extract_all_rules(info, [pair_symbol(p) for p in cpairs], contract_types)
    out = RulesSnapshot()
    now_ms = to_ms(clock.now())
    for p in cpairs:
        r = res[pair_symbol(p)]
        if isinstance(r, RulesError):
            out.errors[p] = str(r)
            log.warning("kural alinamadi %s: %s", p, r)
            continue
        out[p] = spec_to_json(r)
        if store is not None:
            store.put_rules(p, out[p], now_ms)
    if out_json_path is not None:
        atomic_write_json(out_json_path, dict(out))
    return out


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


class Feed:
    def __init__(self, cfg: FeedConfig, rest: PublicRestClient, store: MarketStore, clock: Clock,
                 rng: Callable[[], float] | None = None) -> None:
        self.cfg = cfg
        self._rng = rng or random.random
        self.rest = rest
        self.store = store
        self.clock = clock
        self.pairs = tuple(canon_pair(p) for p in cfg.pairs)
        self.optional = frozenset(canon_pair(p) for p in cfg.optional_pairs)
        self.offset_ms = 0
        self._clock_fatal = False
        self._lock_fd: int | None = None
        self._started = False
        self._c = {"requests": 0, "errors": 0, "gaps": 0, "conflicts": 0, "agg_mismatch": 0, "bans": 0, "bars_written": 0}
        self._last_ok: dict[str, str] = {}
        self._retry_at: dict[tuple, int] = {}
        self._tf_done: dict[tuple[str, str], int] = {}
        self._next_funding_ms = 0
        self._next_rules_ms = 0
        self._next_prune_ms = 0
        self._ban_streak = 0
        self._store_fail_streak = 0
        self._tick_store_err = False
        self._abn_done: dict[tuple, int] = {}
        self._heal_at: dict[tuple, int] = {}
        self._heal_fail: dict[tuple, int] = {}          # basarili ama ilerlemeyen doldurma sayisi
        self._heal_net_at: dict[tuple, int] = {}        # ag-sinifi hata beklemesi (herhangi bir basarili cevapta temizlenir)
        self._heal_net_fail: dict[tuple, int] = {}
        self._next_heal_ms = 0
        self._start_429 = 0

    # ------------------------------------------------------------------ zaman
    def _now_server(self) -> datetime:
        return self.clock.now() + timedelta(milliseconds=self.offset_ms)

    def _measure_offset(self) -> None:
        st = self._rest(self.rest.server_time_ms)
        self.offset_ms = int(st) - to_ms(self.clock.now())
        self.store.meta_set("server_offset_ms", str(self.offset_ms))
        a = abs(self.offset_ms)
        self._clock_fatal = a > CLOCK_FATAL_MS
        if self._clock_fatal:
            log.error("%s", ClockError(f"yerel saat sunucudan {self.offset_ms} ms farkli (> 5 dk): bar yazilmaz"))
        elif a > CLOCK_WARN_MS:
            log.warning("yerel saat sunucudan %d ms farkli; suzgec sunucu saatine gore", self.offset_ms)

    # ------------------------------------------------------------------- REST
    def _rest(self, fn, *a, **k):
        self._c["requests"] += 1
        try:
            r = fn(*a, **k)
            if self._heal_net_at:       # borsa cevap veriyor: ag-sinifi doldurma beklemeleri bosalir (iyilesme gecikmesin)
                self._heal_net_at.clear()
                self._heal_net_fail.clear()
            return r
        except ExchangeBan:
            self._c["bans"] += 1
            raise
        except ExchangeError:
            self._c["errors"] += 1
            raise

    # ------------------------------------------------------------------ acilis
    def start(self) -> None:
        if self._lock_fd is None:
            lock_dir = os.path.dirname(self.cfg.lock_path)
            if lock_dir:
                os.makedirs(lock_dir, exist_ok=True)
            fd = os.open(self.cfg.lock_path, os.O_CREAT | os.O_RDWR, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                raise FailClosed(f"locked: baska bir feed sureci calisiyor ({self.cfg.lock_path})") from None
            self._lock_fd = fd
        self._startup_ban_persisted()
        self._startup_call(self._measure_offset, "saat farki olcumu")
        self.store.meta_set("started_ms", str(to_ms(self.clock.now())))
        self._fetch_rules_at_start()
        self._started = True
        if not self._clock_fatal:
            self.backfill()

    def _startup_ban_persisted(self) -> None:
        """DD-7 §3: kalici/benimsenen ban kaydi varsa ilk istekten ONCE bekle (kalan > BAN_MAX_WAIT_S ise cikis 3)."""
        guard = getattr(self.rest, "ban_guard", None)
        if guard is None:
            return
        rec = guard.active()
        until = getattr(rec, "until_ms", None)
        if rec is None or not isinstance(until, int):
            return
        left = max(1, -(-(until - int(guard.now_ms())) // 1000))
        if left > BAN_MAX_WAIT_S:
            log.critical("ban_persisted: kalan %d sn > ust sinir %d sn; cikiliyor (kod %d)", left, BAN_MAX_WAIT_S, EXIT_BAN)
            raise SystemExit(EXIT_BAN)
        log.critical("ban_persisted: kalici yasak kaydi (http=%s kaynak=%s) kalan %d sn; bekleniyor", getattr(rec, "http", None),
                     getattr(rec, "source", None), left)
        self._c["bans"] += 1
        self.clock.sleep(left + BAN_MARGIN_S)

    def _startup_delay_s(self, n: int) -> float:
        """Acilis geri cekilmesi: base*2**n (tavanli) x [0.5, 1.0) jitter (cok istemcili ayni anda yeniden denemeyi dagitir)."""
        d = min(self.cfg.startup_backoff_cap_s, self.cfg.startup_backoff_base_s * (2 ** min(n, 30)))
        return d * (0.5 + 0.5 * min(max(float(self._rng()), 0.0), 1.0))

    def _ban_wait_s(self, b: ExchangeBan) -> int:
        """Yasakta beklenecek sure; ust sinir (BAN_MAX_WAIT_S) asilirsa uyumadan cikis 3 (yasak uzatilmaz, alarm)."""
        wait = b.retry_after_s if b.retry_after_s is not None else (BAN_418_DEFAULT_S if b.http == 418 else 60)
        if b.http == 418:
            wait = max(wait, BAN_418_DEFAULT_S)
        if wait > BAN_MAX_WAIT_S:
            log.critical("ban/kisit (HTTP %s): Retry-After=%d sn > ust sinir %d sn; cikiliyor (kod %d)", b.http, wait, BAN_MAX_WAIT_S, EXIT_BAN)
            raise SystemExit(EXIT_BAN)
        return wait + BAN_MARGIN_S

    def _startup_wait(self, what: str, n: int, err: Exception) -> None:
        d = self._startup_delay_s(n)
        log.warning("acilista %s basarisiz (deneme %d): %s; %.1f sn sonra tekrar", what, n + 1, err, d)
        self._write_status(to_ms(self._now_server()))
        self.clock.sleep(d)

    def _startup_429(self, what: str, b: ExchangeBan) -> None:
        """Acilista ardisik 429: calisma yolundaki gibi MAX_CONSEC_BANS'te cikis 3 (yasak uzatilmaz, alarm)."""
        self._start_429 += 1
        wait = self._ban_wait_s(b)
        log.warning("acilista 429 (%s): %d sn uyuyor (%d/%d)", what, wait, self._start_429, MAX_CONSEC_BANS)
        if self._start_429 >= MAX_CONSEC_BANS:
            log.critical("acilista %d ardisik 429; cikiliyor (kod %d)", self._start_429, EXIT_BAN)
            raise SystemExit(EXIT_BAN)
        self.clock.sleep(wait)

    def _startup_call(self, fn, what: str):
        """Acilis adimi. startup_retry_forever: ag/5xx/bozuk JSON (ExchangeError) ve 429 suresiz denenir; 418/451 ve ust siniri asan
        Retry-After yukselir (cikis 3/6). Kapaliyken tek deneme (eski davranis)."""
        n = 0
        while True:
            try:
                return fn()
            except ExchangeBan as b:
                if not self.cfg.startup_retry_forever or b.http != 429:
                    raise
                self._startup_429(what, b)
            except ExchangeError as e:
                if not self.cfg.startup_retry_forever:
                    raise
                self._start_429 = 0
                self._startup_wait(what, n, e)
                n += 1

    def _fetch_rules_at_start(self) -> None:
        """Acilis kural cekimi: sinirli geri cekilmeyle yeniden dener; olmazsa RulesFetchError (10/10 ya da hicbiri).
        startup_retry_forever iken ag/borsa hatalari (ExchangeError) deneme hakkini TUKETMEZ (suresiz); eksik cift/bozuk kural
        (DataError/RulesError) yapilandirma hatasidir ve eski sinirli sayiyla biter."""
        waits = tuple(self.cfg.rules_start_backoff_s)
        last = ""
        net_n = 0
        attempt = 0
        while attempt <= len(waits):
            try:
                self._refresh_rules(strict=True)
                return
            except ExchangeBan as e:
                if e.http == 451:
                    raise RulesFetchError(GEOBLOCK_MSG, geoblock=True) from e
                if self.cfg.startup_retry_forever and e.http == 429:
                    self._startup_429("kural cekimi", e)
                    continue
                raise
            except ExchangeError as e:
                if self.cfg.startup_retry_forever:
                    self._start_429 = 0
                    self._startup_wait("kural cekimi", net_n, e)
                    net_n += 1
                    continue
                last = str(e)
                log.warning("acilista kurallar cekilemedi (%d/%d): %s", attempt + 1, len(waits) + 1, e)
            except (DataError, RulesError) as e:
                last = str(e)
                log.warning("acilista kurallar cekilemedi (%d/%d): %s", attempt + 1, len(waits) + 1, e)
            if attempt < len(waits):
                self.clock.sleep(waits[attempt])
            attempt += 1
        raise RulesFetchError(f"acilista borsa kurallari {len(waits) + 1} denemede alinamadi: {last}")

    def close(self) -> None:
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            finally:
                self._lock_fd = None

    # --------------------------------------------------------------- yazma yolu
    def _write(self, pair: str, tf: str, kind: str, rows: Sequence[Sequence], now_ms: int):
        bars, bad = rows_to_bars(pair, kind, tf, rows, now_ms)  # type: ignore[arg-type]
        gaps = 0
        for b in bad:
            self.store.mark_gap(kind, pair, tf, b.open_ms, "abnormal_close", now_ms)
            gaps += 1
            log.warning("anormal satir %s %s %s %d (%s)", pair, tf, kind, b.open_ms, b.reason)
        res = self.store.put_bars(bars, now_ms=now_ms)
        # h<l vb. bozuk mum: store yazmaz; deligi 'abnormal_close' olarak kaydet (sessiz kalmasin, yeniden istek firtinasi olmasin)
        abn = {b.open_ms for b in bad}
        for ib in res.invalid_bars:
            om = to_ms(ib.open_ts)
            abn.add(om)
            self.store.mark_gap(kind, pair, tf, om, "abnormal_close", now_ms)
            gaps += 1
            log.warning("gecersiz mum %s %s %s %d (h/l tutarsiz vb.); abnormal_close", pair, tf, kind, om)
        self._c["gaps"] += gaps + res.conflicts
        self._c["conflicts"] += res.conflicts
        self._c["bars_written"] += res.inserted
        return bars, res, gaps, abn

    def _ok(self, pair: str, tf: str, kind: str, now_ms: int) -> None:
        k = f"{pair}:{tf}:{kind}"
        self._last_ok[k] = fmt_ts(from_ms(now_ms))
        self.store.meta_set(f"last_ok:{k}", str(now_ms))

    # ---------------------------------------------------------------- backfill
    def backfill(self) -> BackfillReport:
        now = self._now_server()
        now_ms = to_ms(now)
        w = d = c = g = e = 0
        skipped: list[str] = []
        for pair in self.pairs:
            sym = pair_symbol(pair)
            got_any = False
            for tf in SERIES_TFS:
                for kind in (("last", "mark") if tf == "1m" else ("last",)):
                    try:
                        r = self._backfill_series(pair, sym, tf, kind, now, now_ms)
                    except ExchangeBan:
                        raise
                    except ExchangeError:
                        e += 1
                        continue
                    except DataError as ex:
                        e += 1
                        self._c["errors"] += 1
                        self._tick_store_err = True
                        log.error("backfill store hatasi: %s", ex)
                        continue
                    except Exception as ex:  # noqa: BLE001
                        e += 1
                        self._c["errors"] += 1
                        log.exception("backfill %s %s %s: %s", pair, tf, kind, ex)
                        continue
                    w, d, c, g = w + r[0], d + r[1], c + r[2], g + r[3]
                    got_any = got_any or r[4]
            if not got_any:
                skipped.append(pair)
                log.warning("backfill: %s icin hic veri yok; atlandi", pair)
        return BackfillReport(w, d, c, g, e, tuple(skipped))

    def _backfill_series(self, pair, sym, tf, kind, now: datetime, now_ms: int):
        derin = None
        tf_ms = int(tf_delta(tf).total_seconds() * 1000)
        last = self.store.last_open_ms(kind, pair, tf)
        end_open = to_ms(floor_tf(now, tf))                  # [.., end_open) kapanmis
        if last is None:
            start_ms = end_open - int(self.cfg.backfill_bars.get(tf, 0)) * tf_ms
            if self.cfg.backfill_bars.get(tf, 0) <= 0:
                return (0, 0, 0, 0, False)
        else:
            start_ms = last + 1
            depth = int(self.cfg.backfill_bars.get(tf, 0))
            if tf == "4h" and depth > 0:
                # derinlesme (bir kez): 1g penceresi 600 gun ister; eski depo 1500 x 4s ile kurulmustu. Depo istenen derinlikten
                # sigsa eski kismi da indir (ayni satirlar yeniden yazilir, idempotent). Isaret: liste tarihi gec olan enstruman her
                # acilista yeniden denemesin.
                mk = f"derin:{pair}:{tf}:{kind}"
                first = self.store.first_open_ms(kind, pair, tf)
                want = end_open - depth * tf_ms
                if first is not None and first > want and self.store.meta_get(mk) != str(depth):
                    start_ms = max(want, 0)
                    derin = mk
            if depth > 0:       # uzun kesintide de sinirli: en fazla backfill_bars kadar geriye
                if start_ms < end_open - depth * tf_ms:
                    log.warning("backfill %s %s %s: %d..%d araligi backfill_bars=%d'den derin; atlandi", pair, tf, kind,
                                start_ms, end_open - depth * tf_ms, depth)
                self._mark_missing(pair, tf, kind, start_ms, end_open - depth * tf_ms, now_ms) \
                    if start_ms < end_open - depth * tf_ms else None
                start_ms = max(start_ms, end_open - depth * tf_ms)
        fn = self.rest.klines_all if kind == "last" else self.rest.mark_price_klines_all
        rows = self._rest(fn, sym, tf, max(start_ms, 0))
        bars, res, gaps, _ = self._write(pair, tf, kind, rows, now_ms)
        if derin is not None:
            self.store.meta_set(derin, str(int(self.cfg.backfill_bars.get(tf, 0))))   # indirme basarili: bir daha deneme
        first = self.store.first_open_ms(kind, pair, tf)
        has = first is not None
        if has:
            lo = max(start_ms, first)
            exp = [to_ms(t) for t in expected_opens(from_ms(lo), from_ms(end_open), tf)]
            if exp:
                have = {b.open_ts for b in self.store.query_range(kind, pair, tf, exp[0], exp[-1] + 1)}
                for om in exp:
                    if from_ms(om) not in have:
                        self.store.mark_gap(kind, pair, tf, om, "missing", now_ms)
                        gaps += 1
                        self._c["gaps"] += 1
            self._ok(pair, tf, kind, now_ms)
        return (res.inserted, res.duplicates_equal, res.conflicts, gaps, has)

    # ----------------------------------------------------------------- run_once
    def run_once(self) -> FeedTick:
        before = dict(self._c)
        now = self._now_server()
        now_ms = to_ms(now)
        self._tick_store_err = False
        banned = False
        skipped = None
        if not self._started:
            skipped = "not_started"
        elif self._clock_fatal:
            skipped = "clock_skew"
        if skipped is None:
            try:
                self._tick(now, now_ms)
                self._ban_streak = 0
            except ExchangeBan as b:
                banned = True
                self._ban_streak += 1
                wait = b.retry_after_s if b.retry_after_s is not None else 60
                log.error("ban/kisit (HTTP %s): %d sn uyuyor (%d/%d)", b.http, wait, self._ban_streak, MAX_CONSEC_BANS)
                self._write_status(now_ms)
                if self._ban_streak >= MAX_CONSEC_BANS:
                    raise SystemExit(EXIT_BAN) from None
                self.clock.sleep(self._ban_wait_s(b))     # ust sinir asilirsa uyumadan cikis 3
        if self._tick_store_err:
            self._store_fail_streak += 1
            if self._store_fail_streak >= MAX_CONSEC_STORE_FAIL:
                self._write_status(now_ms)
                raise SystemExit(EXIT_STORE)
        else:
            self._store_fail_streak = 0
        if not banned:
            self._write_status(now_ms)
        d = {k: self._c[k] - before[k] for k in self._c}
        return FeedTick(now_ms, d["bars_written"], d["errors"], d["gaps"], d["conflicts"], banned, skipped)

    def run_forever(self, *, max_ticks: int | None = None) -> None:
        n = 0
        while max_ticks is None or n < max_ticks:
            self.run_once()
            self.clock.sleep(1.0)
            n += 1

    def _guard(self, what: str, fn, *a):
        """Bir cift/seri hatasi dongu olduruz (ExchangeBan ve SystemExit disinda)."""
        try:
            return fn(*a)
        except ExchangeBan:
            raise
        except ExchangeError as e:
            log.warning("%s: %s", what, e)
        except DataError as e:
            self._c["errors"] += 1
            self._tick_store_err = True
            log.error("%s: store hatasi: %s", what, e)
        except Exception as e:  # noqa: BLE001
            self._c["errors"] += 1
            log.exception("%s: beklenmeyen hata: %s", what, e)
        return None

    def _tick(self, now: datetime, now_ms: int) -> None:
        grace_ms = int(self.cfg.grace_s * 1000)
        m_open = last_closed_open(now, "1m")
        m_close_ms = to_ms(m_open) + 60_000
        self._heal_pass(now, now_ms)
        for pair in self.pairs:
            sym = pair_symbol(pair)
            if now_ms >= m_close_ms + grace_ms:
                for kind in ("last", "mark"):
                    if self._heal_blocks(pair, "1m", kind, now):
                        continue
                    self._guard(f"{pair} 1m {kind}", self._minute, pair, sym, kind, to_ms(m_open), now_ms)
            for tf in TF_CLOSE_TFS:                 # kapanis siniri: floor_tf(now, tf); grace sonrasi (kendini iyilestirir)
                b_ms = to_ms(floor_tf(now, tf))
                if now_ms >= b_ms + grace_ms and not self._heal_blocks(pair, tf, "last", now):
                    self._guard(f"{pair} {tf}", self._tf_close, pair, sym, tf, b_ms, now_ms)
        if now_ms >= self._next_rules_ms:
            self._guard("rules", self._refresh_rules)
            self._next_rules_ms = now_ms + int(self.cfg.rules_refresh_s * 1000)
        if now_ms >= self._next_funding_ms:
            for pair in self.pairs:
                self._guard(f"{pair} funding", self._funding, pair, pair_symbol(pair), now_ms)
            self._next_funding_ms = min(now_ms + int(self.cfg.funding_refresh_s * 1000),
                                        _next_funding_boundary_ms(now_ms) + int(self.cfg.funding_boundary_delay_s * 1000))
            self._guard("offset", self._measure_offset)
        if now_ms >= self._next_prune_ms:
            self._guard("prune", lambda: self.store.prune(now_ms, self.cfg.retention_1m_days))
            self._next_prune_ms = now_ms + 3_600_000

    def _minute(self, pair, sym, kind, m_ms, now_ms) -> None:
        if (self.store.last_open_ms(kind, pair, "1m") or -1) >= m_ms:
            return
        key = (pair, "1m", kind)
        if self._abn_done.get(key, -1) >= m_ms:      # bu dakika bozuk mum olarak kaydedildi: yeniden istek yok
            return
        if now_ms < self._retry_at.get(key, 0):
            return
        fn = self.rest.klines if kind == "last" else self.rest.mark_price_klines
        rows = self._rest(fn, sym, "1m", limit=self.cfg.minute_fetch_limit)
        bars, res, _, abn = self._write(pair, "1m", kind, rows, now_ms)
        if any(to_ms(b.open_ts) >= m_ms for b in res.inserted_bars):
            self._ok(pair, "1m", kind, now_ms)
            self._retry_at.pop(key, None)
        elif m_ms in abn:
            self._abn_done[key] = m_ms
            self._retry_at.pop(key, None)
        else:
            self._retry_at[key] = now_ms + RETRY_THROTTLE_MS

    def _tf_close(self, pair, sym, tf, boundary_ms, now_ms) -> None:
        tf_ms = int(tf_delta(tf).total_seconds() * 1000)
        want = boundary_ms - tf_ms
        key = (pair, tf)
        if self._tf_done.get(key) == boundary_ms:
            return
        if (self.store.last_open_ms("last", pair, tf) or -1) >= want:
            self._tf_done[key] = boundary_ms
            return
        if now_ms < self._retry_at.get((pair, tf, "last"), 0):
            return
        rows = self._rest(self.rest.klines, sym, tf, limit=2)
        bars, res, _, abn = self._write(pair, tf, "last", rows, now_ms)
        for b in res.inserted_bars:
            self._check_aggregate(b, now_ms)
        if any(to_ms(b.open_ts) >= want for b in res.inserted_bars):
            self._tf_done[key] = boundary_ms
            self._retry_at.pop((pair, tf, "last"), None)
            self._ok(pair, tf, "last", now_ms)
        elif want in abn:                # bozuk mum: abnormal_close kaydedildi; bu sinir icin tekrar istek yok
            self._tf_done[key] = boundary_ms
            self._retry_at.pop((pair, tf, "last"), None)
            log.warning("%s %s bari %d bozuk; abnormal_close, yeniden istek yok", pair, tf, want)
        elif now_ms >= boundary_ms + TF_GIVEUP_MS:
            self._tf_done[key] = boundary_ms
            log.warning("%s %s bari %d yayinlanmadi; vazgecildi", pair, tf, want)
        else:
            self._retry_at[(pair, tf, "last")] = now_ms + RETRY_THROTTLE_MS

    # ------------------------------------------- calisirken bosluk doldurma (O12)
    def _heal_need(self, pair, tf, kind, now: datetime):
        """(last, end_open) | None. Normal dakikalik/kapanis cekimi (limit=5 / limit=2) deligi kapatamayacaksa doldurma gerekir."""
        last = self.store.last_open_ms(kind, pair, tf)
        if last is None:            # hic veri yok: ilk doldurma acilista (start) yapilir
            return None
        tf_ms = int(tf_delta(tf).total_seconds() * 1000)
        end_open = to_ms(floor_tf(now, tf))
        cover = max(self.cfg.minute_fetch_limit - 1, 1) if tf == "1m" else 1
        if (end_open - tf_ms - last) // tf_ms <= cover:
            return None
        return last, end_open

    def _heal_blocks(self, pair, tf, kind, now: datetime) -> bool:
        """Doldurma bekleyen seride normal (limit=5/2) cekim ATLANIR: yoksa son N mumu yazip son_acilis'i ilerletir ve eski deligi
        gorunmez yapar. Doldurma 3 kez ilerlemezse (bozuk/bos veri) normal cekim devam eder; delik loglanir."""
        if self._heal_fail.get((pair, tf, kind), 0) >= self.cfg.heal_giveup_strikes:
            return False
        return self._heal_need(pair, tf, kind, now) is not None

    def _heal_pass(self, now: datetime, now_ms: int) -> None:
        """Her tur EN FAZLA bir doldurma istegi (agirlik 5); iki istek arasi >= heal_min_interval_s; kullanilan agirlik
        tavani asarsa bekler; basarisiz/ilerlemeyen seri ustel bekleme alir. Ban gelirse ExchangeBan run_once'a yukselir."""
        if now_ms < self._next_heal_ms:
            return
        try:
            used = int(self.rest.used_weight())
        except Exception:  # noqa: BLE001  (sahte/eksik istemci)
            used = 0
        if used >= self.cfg.heal_weight_ceiling:
            return
        for pair in self.pairs:
            sym = pair_symbol(pair)
            for tf in SERIES_TFS:
                for kind in (("last", "mark") if tf == "1m" else ("last",)):
                    key = (pair, tf, kind)
                    if now_ms < self._heal_at.get(key, 0) or now_ms < self._heal_net_at.get(key, 0):
                        continue
                    need = self._heal_need(pair, tf, kind, now)
                    if need is None:
                        self._heal_fail.pop(key, None)
                        continue
                    self._next_heal_ms = now_ms + int(self.cfg.heal_min_interval_s * 1000)
                    self._guard(f"heal {pair} {tf} {kind}", self._heal_series, pair, sym, tf, kind, need[0], need[1], now_ms)
                    return

    def _mark_missing(self, pair, tf, kind, lo_ms: int, hi_ms: int, now_ms: int) -> int:
        """[lo_ms, hi_ms) icinde depoda olmayan her acilisi 'missing' diye kaydet."""
        exp = [to_ms(t) for t in expected_opens(from_ms(max(lo_ms, 0)), from_ms(max(hi_ms, 0)), tf)]
        if not exp:
            return 0
        have = {to_ms(b.open_ts) for b in self.store.query_range(kind, pair, tf, exp[0], exp[-1] + 1)}
        miss = [om for om in exp if om not in have]
        self.store.mark_gaps(kind, pair, tf, miss, "missing", now_ms)
        self._c["gaps"] += len(miss)
        return len(miss)

    def _heal_series(self, pair, sym, tf, kind, last: int, end_open: int, now_ms: int) -> None:
        tf_ms = int(tf_delta(tf).total_seconds() * 1000)
        key = (pair, tf, kind)
        start_ms = last + 1
        depth = int(self.cfg.backfill_bars.get(tf, 0))
        if depth > 0 and start_ms < end_open - depth * tf_ms:
            log.warning("doldurma %s %s %s: %d..%d araligi backfill_bars=%d'den derin; atlandi", pair, tf, kind,
                        start_ms, end_open - depth * tf_ms, depth)
            skipped_hi = end_open - depth * tf_ms
            n = self._mark_missing(pair, tf, kind, start_ms, skipped_hi, now_ms)     # atlanan arac da kayitli olsun
            log.warning("doldurma %s %s %s: atlanan aralik 'missing' kaydedildi (%d bar)", pair, tf, kind, n)
            start_ms = skipped_hi
        page = max(int(self.cfg.heal_page_bars), 1)
        fn = self.rest.klines if kind == "last" else self.rest.mark_price_klines
        try:
            rows = self._rest(fn, sym, tf, start_ms, None, page)
        except ExchangeBan:
            raise
        except ExchangeError:
            # ag/5xx/bozuk JSON: yalniz bekleme; vazgecme sayacina GIRMEZ (kesinti bitince doldurulacak)
            nf = self._heal_net_fail.get(key, 0)
            self._heal_net_fail[key] = nf + 1
            self._heal_net_at[key] = now_ms + int(min(self.cfg.heal_net_backoff_cap_s,
                                                     self.cfg.heal_net_backoff_base_s * (2 ** min(nf, 20))) * 1000)
            raise
        bars, res, gaps, _ = self._write(pair, tf, kind, rows, now_ms)
        if rows:
            hi = end_open if len(rows) < page else int(rows[-1][0]) + tf_ms      # kapsanan yari-acik aralik
            self._mark_missing(pair, tf, kind, start_ms, hi, now_ms)
        for b in res.inserted_bars:
            if tf != "1m" and kind == "last":
                self._check_aggregate(b, now_ms)
        new_last = self.store.last_open_ms(kind, pair, tf)
        if res.inserted > 0 and new_last is not None and new_last > last:
            self._heal_fail.pop(key, None)
            self._heal_at.pop(key, None)
            log.warning("bosluk dolduruldu %s %s %s: +%d bar (son %d)", pair, tf, kind, res.inserted, new_last)
            if new_last >= end_open - tf_ms:
                self._ok(pair, tf, kind, now_ms)
            return
        # basarili cevap ama ilerleme yok (bos/bozuk veri): sayac + ustel bekleme
        fails = self._heal_fail.get(key, 0) + 1
        self._heal_fail[key] = fails
        self._heal_at[key] = now_ms + int(min(self.cfg.heal_backoff_cap_s, self.cfg.heal_backoff_base_s * (2 ** min(fails - 1, 20))) * 1000)
        if fails == self.cfg.heal_giveup_strikes:
            # normal cekim artik acilacak ve son_acilis'i ileri sicratabilir: DELIGI ONCE KAYDET
            n = self._mark_missing(pair, tf, kind, start_ms, end_open, now_ms)
            log.warning("doldurma vazgecildi %s %s %s: %d..%d araligi doldurulamadi (%d bar 'missing' kaydedildi)",
                        pair, tf, kind, start_ms, end_open, n)

    # -------------------------------------------------------- bar builder (§5.4)
    def _check_aggregate(self, bar: Bar, now_ms: int) -> None:
        s, e = to_ms(bar.open_ts), to_ms(bar.close_ts)
        mins = self.store.query_range("last", bar.pair, "1m", s, e)
        n = (e - s) // 60_000
        if len(mins) < n:
            self.store.mark_gap("last", bar.pair, bar.tf, s, "minute_missing", now_ms)
            self._c["gaps"] += 1
            log.warning("minute_missing %s %s %d (%d/%d dakika)", bar.pair, bar.tf, s, len(mins), n)
            return
        mb = [MinuteBar(m.pair, m.open_ts, 60, m.o, m.h, m.l, m.c, None, None, None, None, m.v) for m in mins]
        agg = aggregate_minutes(mb, bar.tf, "last")
        bad = any(_rel(a, b) > 1e-9 for a, b in ((agg.o, bar.o), (agg.h, bar.h), (agg.l, bar.l), (agg.c, bar.c))) \
            or _rel(agg.v, bar.v) > 1e-6
        if bad:
            self.store.mark_gap("last", bar.pair, bar.tf, s, "agg_mismatch", now_ms)
            self._c["agg_mismatch"] += 1
            self._c["gaps"] += 1
            log.warning("agg_mismatch %s %s %d: 1m toplami REST barindan farkli", bar.pair, bar.tf, s)

    # -------------------------------------------------------- kurallar, funding
    def _refresh_rules(self, *, strict: bool = False) -> None:
        """exchangeInfo -> rules tablosu. Basari `rules_fetched_at`; her deneme `rules_attempt_at`; hata `rules_last_error`
        (feed_meta). strict (acilis): eksik cift de hata sayilir. Saatlik yenilemede hata yalniz WARN (`_guard`)."""
        now_ms = to_ms(self._now_server())
        self.store.meta_set("rules_attempt_at", str(now_ms))
        try:
            res = snapshot_rules(self.rest, self.pairs, self.clock, store=self.store, contract_types=self.cfg.contract_types)
            self._c["requests"] += 1
            if strict:
                for p, m in sorted(res.errors.items()):
                    if p in self.optional:
                        log.warning("isteğe bagli cift kurali yok, atlandi %s: %s", p, m)
                req = {p: m for p, m in res.errors.items() if p not in self.optional}
                if req:
                    raise DataError("kural eksik: " + "; ".join(f"{p}: {m}" for p, m in sorted(req.items())))
        except Exception as e:  # noqa: BLE001
            try:
                self.store.meta_set("rules_last_error", str(e)[:300])
            except Exception:  # noqa: BLE001
                pass
            raise
        self.store.meta_set("rules_fetched_at", str(now_ms))
        self.store.meta_set("rules_last_error", "")

    def _mark_at(self, pair: str, ts_ms: int) -> float | None:
        m0 = ts_ms - ts_ms % 60_000
        r = self.store.query_range("mark", pair, "1m", m0, m0 + 60_000)
        return r[0].o if r else None

    def _funding(self, pair: str, sym: str, now_ms: int) -> None:
        ex = self.store.query_funding(pair, 0, now_ms + _DAY_MS)
        last = to_ms(ex[-1].ts) if ex else now_ms - FUNDING_FIRST_LOOKBACK_MS
        rows = self._rest(self.rest.funding_rates, sym, start_ms=last + 1)
        pts = []
        for x in rows:
            ts = _floor_funding_ms(int(x["fundingTime"]))
            pts.append(FundingPoint(pair, from_ms(ts), float(x["fundingRate"]), self._mark_at(pair, ts)))
        # bos mark'lari doldurmayi dene (son 3 gun)
        have = {p.ts for p in pts}
        for p in self.store.query_funding(pair, now_ms - 3 * _DAY_MS, now_ms):
            if p.mark is None and p.ts not in have:
                mk = self._mark_at(pair, to_ms(p.ts))
                if mk is not None:
                    pts.append(FundingPoint(pair, p.ts, p.rate, mk))
        if pts:
            self.store.put_funding(pts)
        self._ok(pair, "funding", "last", now_ms)

    # ------------------------------------------------------------------- durum
    def stats(self) -> dict:
        d = dict(self._c)
        d["last_ok"] = dict(self._last_ok)
        return d

    def _write_status(self, now_ms: int) -> None:
        try:
            st = {"schema": "engine/feed-status/1", "ts": fmt_ts(from_ms(now_ms)), "server_offset_ms": self.offset_ms,
                  "pairs": list(self.pairs), "counters": {k: v for k, v in self._c.items()},
                  "last_ok": dict(self._last_ok), "clock_skew_fatal": self._clock_fatal}
            atomic_write_json(self.cfg.status_path, st)
            self.store.meta_set("counters", json.dumps(self._c, sort_keys=True))
        except Exception as e:  # noqa: BLE001  (durum yazilamamasi feed'i dusurmez)
            log.warning("durum yazilamadi: %s", e)


# ====================================================================== giris noktalari
RULES_SOURCE_PATH = "/fapi/v1/exchangeInfo"


def _read_base(config_dir: str) -> dict:
    """engine.base.json'dan yalniz feed'in ihtiyaci olan alanlar (EngineConfig/pandas yuklenmez; bot gerekmez)."""
    path = os.path.join(config_dir, "engine.base.json")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        raise FailClosed(f"engine.base.json okunamadi: {path}: {e}") from e
    pairs = raw.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise FailClosed(f"{path}: pairs bos olmayan liste olmali")
    for k in ("var_dir", "market_db", "history_dir"):
        if not isinstance(raw.get(k), str) or not raw[k]:
            raise FailClosed(f"{path}: {k} bos olmayan str olmali")
    return raw


def _read_env_overlay(config_dir: str, env: str) -> dict:
    """`--env`: engine.<env>.json katmanindan feed'in alanlari (ham JSON; EngineConfig/pandas yuklenmez)."""
    path = os.path.join(config_dir, f"engine.{env}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as e:
        raise FailClosed(f"engine.{env}.json okunamadi: {path}: {e}") from e
    if not isinstance(raw, dict):
        raise FailClosed(f"{path}: nesne olmali")
    return raw


def feed_config_from_base(config_dir: str, env: str | None = None) -> FeedConfig:
    raw = _read_base(config_dir)
    optional: tuple[str, ...] = ()
    ctypes: tuple[str, ...] = ("PERPETUAL",)
    if env:
        ov = _read_env_overlay(config_dir, env)
        raw = {**raw, **{k: ov[k] for k in ("pairs", "var_dir", "market_db", "history_dir") if k in ov}}
        for k in ("pairs", "var_dir", "market_db", "history_dir"):
            if k in ov and (not ov[k] or not isinstance(ov[k], (list, str))):
                raise FailClosed(f"engine.{env}.json: {k} gecersiz")
        if "optional_pairs" in ov:
            op = ov["optional_pairs"]
            if not isinstance(op, list) or not all(isinstance(x, str) for x in op):
                raise FailClosed(f"engine.{env}.json: optional_pairs liste olmali")
            optional = tuple(canon_pair(p) for p in op)
            if not set(optional) <= {canon_pair(p) for p in raw["pairs"]}:
                raise FailClosed(f"engine.{env}.json: optional_pairs pairs disinda")
        if "contract_types" in ov:
            ct = ov["contract_types"]
            if not isinstance(ct, list) or not ct or not all(isinstance(x, str) for x in ct):
                raise FailClosed(f"engine.{env}.json: contract_types bos olmayan liste olmali")
            ctypes = tuple(ct)
    var = raw["var_dir"].rstrip("/")
    return FeedConfig(pairs=tuple(canon_pair(p) for p in raw["pairs"]), db_path=raw["market_db"],
                      lock_path=f"{var}/feed.lock", status_path=f"{var}/feed-status.json",
                      optional_pairs=optional, contract_types=ctypes)


def _make_rest(clock: Clock) -> PublicRestClient:
    return PublicRestClient(now_s=lambda: clock.now().timestamp(), sleep=clock.sleep, jitter=random.random)


def _make_guarded_rest(clock: Clock, db_path: str) -> PublicRestClient:
    """DD-7 §3: feed'in kendi kurdugu istemciye ban dosyasi guard'i takilir (`ban_dir_for(db_path)`, istemcinin base_url'i, source="feed")."""
    from trader_core.ban_store import BanGuard, ban_dir_for, ban_path
    rest = _make_rest(clock)
    rest.ban_guard = BanGuard(ban_path(ban_dir_for(db_path), rest.base_url), source="feed",
                              now_ms=lambda: int(clock.now().timestamp() * 1000))
    return rest


def _parse(argv: Sequence[str] | None, prog: str, extra=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog=prog)
    ap.add_argument("--config-dir", default="config")
    if extra:
        extra(ap)
    return ap.parse_args(list(argv) if argv is not None else None)


def _on_term(signum, frame) -> None:
    raise SystemExit(0)


def main(argv: Sequence[str] | None = None, *, rest: PublicRestClient | None = None, clock: Clock | None = None,
         max_ticks: int | None = None) -> int:
    """`trader_engine feed`: kilidi al, kurallari cek (10/10), backfill, sonra run_forever. Donus = cikis kodu."""
    def extra(ap):
        ap.add_argument("--env", default=None, choices=("testnet", "live", "paper"),
                        help="config/engine.<env>.json katmani (pairs, optional_pairs, contract_types); yoksa yalniz engine.base.json")
        ap.add_argument("--startup-retry", choices=("bounded", "forever"), default="bounded",
                        help="forever: acilista ag/5xx/bozuk JSON hatasinda suresiz ustel geri cekilme (418/451 haric)")
    a = _parse(argv, "trader_engine feed", extra)
    from trader_engine.clock import SystemClock
    clock = clock or SystemClock()
    try:
        cfg = feed_config_from_base(a.config_dir, a.env)
    except FailClosed as e:
        log.critical("feed baslamadi: %s", e)
        return EXIT_STORE
    if a.startup_retry == "forever":
        cfg = dataclasses.replace(cfg, startup_retry_forever=True)
    rest = rest or _make_guarded_rest(clock, cfg.db_path)
    try:
        store = MarketStore(cfg.db_path)
    except DataError as e:
        log.critical("feed baslamadi: %s", e)
        return EXIT_STORE
    feed = Feed(cfg, rest, store, clock)
    prev = {}
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            prev[sig] = signal.signal(sig, _on_term)
        except ValueError:      # ana is parcacigi degil (test)
            pass
    try:
        feed.start()
        feed.run_forever(max_ticks=max_ticks)
        return 0
    except RulesFetchError as e:
        log.critical("feed baslamadi: %s", e)
        return e.exit_code
    except ExchangeBan as e:
        log.critical("feed durdu: ban/kisit (HTTP %s): %s", e.http, e)
        return EXIT_GEOBLOCK if e.http == 451 else EXIT_BAN
    except FailClosed as e:
        log.critical("feed baslamadi: %s", e)
        return EXIT_STORE
    except (ExchangeError, DataError, RulesError) as e:     # acilista ag/borsa/veri hatasi (traceback yok)
        log.critical("feed baslamadi: borsa/ag hatasi: %s", type(e).__name__)
        return EXIT_RULES
    except SystemExit as e:
        return int(e.code or 0)
    finally:
        feed.close()
        store.close()
        for sig, h in prev.items():
            signal.signal(sig, h)


def rules_snapshot_main(argv: Sequence[str] | None = None, *, rest: PublicRestClient | None = None,
                        clock: Clock | None = None) -> int:
    """`trader_engine rules-snapshot`: exchangeInfo -> rules.json (+ `rules.json.meta.json`: fetched_at, sha256, kaynak).
    Cikis: 0 tamam, 1 bazi ciftler eksik (dosya yine de yazilir), 5 alinamadi, 6 HTTP 451."""
    def extra(ap):
        ap.add_argument("--out", default=None, help="varsayilan: <history_dir>/rules.json")
    a = _parse(argv, "trader_engine rules-snapshot", extra)
    from trader_engine.clock import SystemClock
    clock = clock or SystemClock()
    try:
        raw = _read_base(a.config_dir)
    except FailClosed as e:
        print(f"rules-snapshot: {e}", file=sys.stderr)
        return EXIT_STORE
    out = a.out or os.path.join(raw["history_dir"], "rules.json")
    pairs = [canon_pair(p) for p in raw["pairs"]]
    rest = rest or _make_guarded_rest(clock, raw["market_db"])
    try:
        res = snapshot_rules(rest, pairs, clock, out_json_path=out)
    except ExchangeBan as e:
        if e.http == 451:
            print(f"rules-snapshot: {GEOBLOCK_MSG}", file=sys.stderr)
            return EXIT_GEOBLOCK
        print(f"rules-snapshot: ban/kisit: {e}", file=sys.stderr)
        return EXIT_RULES
    except (ExchangeError, DataError, RulesError) as e:
        print(f"rules-snapshot: kurallar alinamadi: {e}", file=sys.stderr)
        return EXIT_RULES
    with open(out, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    meta = {"schema": "engine/rules-snapshot/1", "fetched_at": fmt_ts(clock.now()), "sha256": digest,
            "source_url": getattr(rest, "base_url", "") + RULES_SOURCE_PATH, "file": os.path.basename(out),
            "pairs": sorted(res), "errors": dict(res.errors)}
    atomic_write_json(out + ".meta.json", meta)
    print(f"rules-snapshot: {len(res)}/{len(pairs)} cift -> {out} (sha256 {digest[:12]})")
    for p, m in sorted(res.errors.items()):
        print(f"rules-snapshot: EKSIK {p}: {m}", file=sys.stderr)
    return res.exit_code
