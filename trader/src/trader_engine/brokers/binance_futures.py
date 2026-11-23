"""LiveBroker (11 §5): Binance USDⓈ-M vadeli (testnet/live) icin Broker protokolu gerceklemesi. REST yoklama; ag yalniz enjekte
edilen SignedRestClient uzerinden. Risk sayisi yoktur. SimBroker yontemleri (advance/snapshot/restore) YOKTUR.

Karar notlari (sartname bosluklari):
  * Reddler `code` ile eslenir, asla `http` ile (200+govdede hata kodu http=200 kalir); yalniz code=None iken (429 / order_rate_cap)
    `msg`/`http` bakilir.
  * ExchangeBan (gonderim oncesi) = emir KESINLIKLE gonderilmedi: market/stop -> rejected(reason="exchange_ban"), `last_ban`
    (http, retry_after_s) doldurulur; iptal/sorgu -> BrokerUncertain; okuma -> BrokerError.
  * -1021 reddi: kesin "islenmedi"; reason="exchange_-1021" (bilinen kod: sayac `clock_rejects`, giris engeli YOK).
  * Sorgularda attempts=1 (durdurma suresi siniri); istemci `protective`/`attempts` anahtar sozcuklerini desteklemiyorsa gecilmez.
  * Cikis nedeni: userTrades satirinda kimlik yoksa sirayla bellekteki/ogrenilen emir kimlikleri (her open_orders()/query()
    sonucundan ogrenilir), `client_ids` ipuclari ve kayitli/son iptal edilen stoplar (stop sorgusu actualOrderId/orderId), sonra
    GET /fapi/v1/order?orderId (yalniz -2013 = "yok"; baska her hata yeniden dene) ve /fapi/v1/forceOrders (likidasyon/ADL)
    ile cozulur; cozulemezse `foreign_close`; baglanti hatasinda bos doner.
  * Giris engelleri (`entries_blocked_reason`) yapiskan bir kume: hicbir neden digerini ezmez; yalniz `exchange_unreachable`
    bir sonraki basarili esitlemede kalkar.
"""
from __future__ import annotations

import inspect
import logging
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from ..clock import Clock
from ..config import LiveSettings
from ..errors import BrokerError, BrokerUncertain, DataError, EngineExit
from ..exchange.binance_rest import ExchangeAuth, ExchangeReject, ExchangeUncertain, fmt_num
from ..exchange.rules import (RulesError, SymbolRuleSpec, extract_all_rules, round_stop_tight, round_target_easy,
                              to_symbol_rules)
from ..marketdata.rest_public import ExchangeBan, ExchangeError
from ..numeric import is_multiple
from ..types import (BrokerAccount, BrokerEvent, BrokerOrder, BrokerPosition, Fill, OrderRequest, OrderResult, Role,
                     SymbolRules)

log = logging.getLogger("engine.live_broker")

D = Decimal
UTC = timezone.utc
RULES_REFRESH_S = 3600.0
CLOCK_SYNC_S = 1800.0          # DD-2 D5: periyodik saat esitleme (11-canli-broker §3: acilista, 30 dakikada bir ve her -1021'de)
RULES_MAX_AGE_S = 6 * 3600.0
ACCOUNT_CACHE_S = 2.0
FILL_WAIT_S = 3.0
FILL_POLL_S = 0.3
FUNDING_GIVEUP_S = 60.0
FEE_DRIFT_REL = 0.01
OURS = ("trL", "trT")
_ROLE_BY_LETTER: dict[str, Role] = {"e": "entry", "s": "stop", "t": "target", "x": "exit"}
_FILTER_CODES = {-1111, -1013, -4003, -4005, -4131}
_KNOWN_REASON = {-2021: "would_trigger", -4116: "duplicate_client_id", -2019: "insufficient_margin",
                 -4164: "min_notional", -2022: "reduce_only_exceeds"}
_STATUS_MAP = {"NEW": "new", "PARTIALLY_FILLED": "new", "TRIGGERING": "new", "FILLED": "filled", "TRIGGERED": "filled",
               "FINISHED": "filled", "CANCELED": "canceled", "REJECTED": "rejected", "EXPIRED": "expired"}
_REQUIRED_PERMS = (("enableReading", True), ("enableFutures", True), ("enableWithdrawals", False),
                   ("enableInternalTransfer", False), ("permitsUniversalTransfer", False), ("ipRestrict", True))
_COUNTERS = ("fee_rate_fallback", "unknown_reject_codes", "fee_drift", "fee_asset_unexpected", "rules_missing",
             "rules_refresh_failed", "prepare_failed", "funding_unresolved", "foreign_close", "clock_rejects",
             "working_type_mismatch", "sync_failures", "exchange_bans", "rules_drift", "working_type_unverified",
             "stop_response_mismatch", "exchange_auth", "close_unresolved", "malformed_trades",
             "account_mode_drift", "account_mode_unverified", "entry_weight_rejects", "account_mode_unverified_ban",
             "zero_fill_pending", "zero_fill_unresolved", "optional_position_risk_failed", "partial_exit_events", "partial_fee_estimated")
_BLOCK_PRIORITY = ("exchange_auth", "exchange_unknown_code", "working_type_unverified", "exchange_unreachable")
STARTUP_BAN_SLEEP_MAX_S = 300.0
STARTUP_RULES_TRIES = 2
POS_SINCE_MARGIN = timedelta(seconds=2)
PENDING_NF_TRIES = 3           # bekleyen piyasa emri: ust uste "yok" (-2013) sayisi ...
PENDING_NF_SPAN_S = 10.0       # ... ve ilk "yok"tan bu yana gecen sure dolmadan dusurulmez
FORCE_ORDERS_MAX_AGE = timedelta(days=7)   # forceOrders startTime en fazla 7 gun geriye
FEE_FALLBACK_CTR = "fee_rate_fallback"     # sayac anahtari (risk sabiti degil)
assert _COUNTERS[0] == FEE_FALLBACK_CTR
CLOSE_FAST_TRIES = 3
CLOSE_GIVEUP_S = 60.0
STOP_KEEP = 3                  # pair basina iptal edilmis son stop kimligi sayisi (gec tetiklenme atfi icin)
_STOP_OK = {"NEW", "PARTIALLY_FILLED", "TRIGGERING", "TRIGGERED", "FINISHED", "FILLED"}
_STOP_DEAD = {"REJECTED", "EXPIRED", "CANCELED"}


def _d(x: Any) -> Decimal:
    try:
        v = D(str(x))
    except (InvalidOperation, ValueError):
        return D(0)
    return v if v.is_finite() else D(0)


def _fl(x: Any, default: float = 0.0) -> float:
    try:
        v = float(str(x))
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _ts(ms: Any, default: datetime) -> datetime:
    try:
        v = int(float(str(ms)))
    except (TypeError, ValueError):
        return default
    if v <= 0:
        return default
    return datetime.fromtimestamp(v / 1000.0, tz=UTC)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _finite_pos(x: Any) -> bool:
    return (not isinstance(x, bool)) and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def _strict_float(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(str(x))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _cid_role(cid: str | None) -> Role | None:
    if cid and len(cid) >= 4 and cid.startswith(OURS):
        return _ROLE_BY_LETTER.get(cid[3])
    return None


def _num(x: Decimal) -> str:
    return fmt_num(x)


@dataclass
class _RuleEntry:
    spec: SymbolRuleSpec
    rules: SymbolRules
    ts: datetime


@dataclass
class _Pending:
    pair: str
    role: Role
    side: str
    partial: bool = False      # cikis kipleri: kismi kar alma emri (pozisyonu kapatmaz; dolum dogrudan emirden)


@dataclass
class _Rejected:
    code: int | None


class _Retry(Exception):
    """closing_events: sinif/okuma belirsiz; bos don, sonraki turda yeniden dene."""


class LiveBroker:
    is_simulated = False

    def __init__(self, live: LiveSettings, env: Literal["testnet", "live"], leverage: int, pairs: Sequence[str],
                 rest: Any, clock: Clock, taker_fee_fallback: float, environ: Mapping[str, str] | None = None,
                 contract_types: Sequence[str] | None = None, optional_pairs: Sequence[str] = ()) -> None:
        self._live, self._env, self._lev = live, env, int(leverage)
        self._optional = frozenset(optional_pairs)       # 23.11: hisse/emtia; baslangic position_risk reddi acilisi DURDURMAZ
        self._contract_types = tuple(contract_types) if contract_types else ("PERPETUAL",)   # 23.11: canli = kagit (cfg.contract_types)
        self._environ: Mapping[str, str] = os.environ if environ is None else environ
        self._pairs = tuple(pairs)
        self._sym = {p: p.replace("/", "") for p in self._pairs}
        self._pair_of = {s: p for p, s in self._sym.items()}
        self._rest, self._clock = rest, clock
        self._fee_fallback = float(taker_fee_fallback)
        self._taker: dict[str, float] = {}
        self._ctr: dict[str, int] = {k: 0 for k in _COUNTERS}
        self._sig_cache: dict[tuple[str, str], bool] = {}
        self._rules: dict[str, _RuleEntry] = {}
        self._rules_at: datetime | None = None
        self._prepared: set[str] = set()
        self._acct: tuple[datetime, BrokerAccount] | None = None
        self._seq = 0
        self._queue: list[tuple[datetime, int, BrokerEvent]] = []
        self._pending_market: dict[str, _Pending] = {}
        self._zero_fill: dict[str, tuple[datetime, int]] = {}      # DD-11 D1: cid -> (ilk sifir-dolum zamani, deneme sayisi)
        self._zero_fill_last: dict[str, datetime] = {}            # cid -> son userTrades sorgusu
        self._pending_nf: dict[str, tuple[datetime, int]] = {}   # cid -> (ilk "yok" zamani, ust uste sayi)
        self._margin_types: dict[str, str] = {}          # son positionRisk okumasindan pair -> isolated|cross
        self._pending_close: dict[str, datetime] = {}
        self._pc_first: dict[str, datetime] = {}         # cozulmemis kapanis: ilk deneme zamani / deneme sayisi / sonraki deneme
        self._pc_tries: dict[str, int] = {}
        self._pc_next: dict[str, datetime] = {}
        self._hints: dict[str, tuple[str, ...]] = {}     # register_position ile verilen kimlikler
        self._registered: set[str] = set()
        self._cancelled: dict[str, list[str]] = {}       # pair -> son iptal edilen koruyucu kimlikleri
        self._rules_dirty = False
        self._ban_until: datetime | None = None
        self._open_pairs: set[str] = set()
        self._last_pos: dict[str, Decimal] = {}          # son bilinen imzali miktar (kapanista okunur)
        self._pos_since: dict[str, datetime] = {}
        self._last_mark: dict[str, float] = {}
        self._order_ids: dict[str, tuple[str, str]] = {}  # borsa orderId -> (kendi client id'miz, pair)
        self._stops: dict[str, str] = {}                 # kendi stop/hedef client id -> pair
        self._exit_cids: dict[str, str] = {}
        self._entry_fee: dict[str, float] = {}
        self._delivered: set[Any] = set()
        self._partial_cids: dict[str, set[str]] = {}     # pair -> kismi kar alma emri kimlikleri (kapanis olayindan DISLANIR)
        self._partial_oids: dict[str, set[str]] = {}     # pair -> bu kimliklerin borsa orderId'leri (cozumlenmis)
        self._delivered_funding: set[Any] = set()
        self._funding_wait: dict[str, datetime] = {}
        self._last_sync: datetime | None = None
        self._last_clock_sync: datetime | None = None
        self._last_ok: datetime | None = None
        self._fails = 0
        self._reachable = True
        self._naked: list[Any] = []
        self.findings: list[str] = []
        self._startup_findings: list[str] = []          # DD-8 O4: acilisi durdurmayan bulgular (ornek: wallet_above_expected)
        self.startup_wallet: float | None = None        # acilista okunan totalWalletBalance (yalniz bildirim notu icin)
        self._blocks: set[str] = set()
        self.last_ban: tuple[int | None, int | None] | None = None

    @property
    def startup_findings(self) -> tuple[str, ...]:
        """DD-8 O4: acilis denetiminin acilisi DURDURMAYAN bulgulari (salt okunur). Motor `start()`ta tutusa cevirir."""
        return tuple(self._startup_findings)

    # ------------------------------------------------------------------ giris engelleri (yapiskan kume)
    @property
    def entries_blocked_reasons(self) -> tuple[str, ...]:
        known = [r for r in _BLOCK_PRIORITY if r in self._blocks]
        return tuple(known + sorted(self._blocks - set(known)))

    @property
    def entries_blocked_reason(self) -> str | None:
        rs = self.entries_blocked_reasons
        return rs[0] if rs else None

    def _block(self, reason: str) -> None:
        self._blocks.add(reason)

    def register_position(self, pair: str, opened_ts: datetime, client_ids: Sequence[str] = ()) -> None:
        """B5 protect_first / B4 giris dolumu: pozisyonun yetkili acilis zamani ve kimlikleri (funding penceresi, cikis atfi)."""
        for c in [c for c, i in self._pending_market.items() if i.pair == pair and i.role == "entry"]:
            del self._pending_market[c]                     # DD-11 D2: benimsenen pair'in bekleyen giris kayitlari (hayalet izleme yok)
            self._pending_nf.pop(c, None)
            self._zero_fill.pop(c, None)
            self._zero_fill_last.pop(c, None)
        self._open_pairs.add(pair)
        self._registered.add(pair)
        self._pos_since[pair] = opened_ts
        self._hints[pair] = tuple(c for c in client_ids if c)
        for c in client_ids:
            role = _cid_role(c)
            if role in ("stop", "target"):
                self._remember_stop(c, pair)
            elif role == "exit":
                self._exit_cids[c] = pair

    # ------------------------------------------------------------------ yardimcilar
    def counters(self) -> dict:
        return dict(self._ctr)

    def set_naked(self, rows: list[Any]) -> None:
        self._naked = list(rows)

    def _now(self) -> datetime:
        return self._clock.now()

    def _supports(self, name: str, kw: str) -> bool:
        key = (name, kw)
        v = self._sig_cache.get(key)
        if v is None:
            try:
                ps = inspect.signature(getattr(self._rest, name)).parameters
                v = kw in ps or any(p.kind is inspect.Parameter.VAR_KEYWORD for p in ps.values())
            except (TypeError, ValueError):
                v = False
            self._sig_cache[key] = v
        return v

    def _rc(self, name: str, *args: Any, protective: bool | None = None, attempts: int | None = None) -> Any:
        kw: dict[str, Any] = {}
        if protective is not None and self._supports(name, "protective"):
            kw["protective"] = protective
        if attempts is not None and self._supports(name, "attempts"):
            kw["attempts"] = attempts
        return getattr(self._rest, name)(*args, **kw)

    def _note_ban(self, e: ExchangeBan) -> None:
        now = self._now()
        ra = getattr(e, "retry_after_s", None)
        self.last_ban = (getattr(e, "http", None), ra)
        if self._ban_until is None or now >= self._ban_until:       # ban basina bir kez (pencere icindeki yerel retler sayilmaz)
            self._ctr["exchange_bans"] += 1
            self._ban_until = now + timedelta(seconds=float(ra) if ra else 1.0)

    def _note_429_reject(self) -> None:
        """Emir yolundaki 429 (rate_limited reti): pencere REST istemcisinde acildi; motor `last_ban`dan gorsun (F8)."""
        ra: int | None = None
        try:
            h = self._rest.health()
            left = (int(h.get("ban_until_ms", 0)) - int(self._rest.now_ms())) / 1000.0
            ra = max(1, int(-(-left // 1)))
        except Exception:  # noqa: BLE001
            ra = None
        self.last_ban = (429, ra)

    def _read(self, name: str, *args: Any, protective: bool | None = None) -> Any:
        try:
            return self._rc(name, *args, protective=protective)
        except ExchangeBan as e:
            self._note_ban(e)
            raise BrokerError(f"{name}: exchange_ban retry_after={e.retry_after_s}") from None
        except ExchangeError as e:
            raise BrokerError(f"{name}: {type(e).__name__}") from None

    def _push(self, ev: BrokerEvent) -> None:
        self._seq += 1
        self._queue.append((ev.ts, self._seq, ev))

    def _rej(self, cid: str, reason: str) -> OrderResult:
        return OrderResult(status="rejected", client_id=cid, reason=reason, ts=self._now())

    def _taker_rate(self, pair: str) -> float:
        return self._taker.get(pair, self._fee_fallback)

    def _pair(self, symbol: str) -> str:
        p = self._pair_of.get(symbol)
        if p:
            return p
        for q in ("USDT", "USDC", "BUSD"):
            if symbol.endswith(q) and len(symbol) > len(q):
                return f"{symbol[:-len(q)]}/{q}"
        return symbol

    def _symbol(self, pair: str) -> str:
        return self._sym.get(pair) or pair.replace("/", "")

    # ------------------------------------------------------------------ kurallar (§5.2)
    def refresh_rules(self) -> bool:
        try:
            info = self._rc("exchange_info")
        except ExchangeBan as e:
            self._note_ban(e)
            self._ctr["rules_refresh_failed"] += 1
            return False
        except ExchangeError as e:
            self._ctr["rules_refresh_failed"] += 1
            log.warning("exchangeInfo yenilenemedi: %s", type(e).__name__)
            return False
        self._apply_rules(info)
        return True

    def _apply_rules(self, info: Any) -> None:
        now = self._now()
        res = extract_all_rules(info if isinstance(info, dict) else {}, [self._sym[p] for p in self._pairs],
                                self._contract_types)
        for p in self._pairs:
            r = res.get(self._sym[p])
            if isinstance(r, SymbolRuleSpec):
                self._rules[p] = _RuleEntry(r, to_symbol_rules(p, r), now)
            else:
                self._ctr["rules_missing"] += 1
                log.warning("kural yok/bozuk %s: %s", p, r)
        self._rules_at = now
        self._rules_dirty = False

    def check_rules_drift(self, feed_rules: Mapping[str, SymbolRules]) -> list[str]:
        out = []
        for p, fr in feed_rules.items():
            e = self._rules.get(p)
            if e is None:
                continue
            r = e.rules
            if (r.tick, r.step, r.min_notional) != (fr.tick, fr.step, fr.min_notional):
                self._ctr["rules_drift"] += 1
                out.append(f"rules_drift:{p}")
                log.warning("rules_drift:%s", p)
        return out

    def rules(self, pair: str) -> SymbolRules:
        e = self._rules.get(pair)
        if e is None:
            raise DataError(f"rules_missing:{pair}")
        if (self._now() - e.ts).total_seconds() > RULES_MAX_AGE_S:
            raise DataError(f"rules_stale:{pair}")
        return e.rules

    def rules_last_known(self, pair: str) -> SymbolRules | None:
        """DD-2 D9: yas denetimsiz son bilinen kural (koruyucu yol); yoksa None."""
        e = self._rules.get(pair)
        return None if e is None else e.rules

    def _entry_any(self, pair: str) -> _RuleEntry | None:
        return self._rules.get(pair)          # cikis/stop: son bilinen kural (bayat olsa da)

    # ------------------------------------------------------------------ acilis denetimi (§3.4)
    def _startup_ban(self, e: ExchangeBan) -> None:
        if getattr(e, "http", None) in (451, 403):
            raise EngineExit(8, "region_blocked") from e
        wait = min(max(float(getattr(e, "retry_after_s", None) or 0.0), 0.0), STARTUP_BAN_SLEEP_MAX_S)
        log.critical("acilista ban http=%s retry_after=%s: %.0f sn beklenip cikilacak (kod 5)", getattr(e, "http", None),
                     getattr(e, "retry_after_s", None), wait)
        if wait > 0:
            self._clock.sleep(wait)
        raise EngineExit(5, "exchange_unreachable") from e

    def _startup_call(self, fn, *args: Any, soft_reject: bool = False) -> Any:
        """soft_reject: -1021 disindaki ExchangeReject -> `_Rejected(code)` doner (cift basina adimlar)."""
        try:
            return fn(*args)
        except ExchangeAuth as e:
            raise EngineExit(8, "auth_failed") from e
        except ExchangeBan as e:
            self._startup_ban(e)
        except ExchangeUncertain as e:
            raise EngineExit(5, "exchange_unreachable") from e
        except ExchangeReject as e:
            if e.code == -1021:                                  # saat yeniden esitlenemedi: ag sorunu, kurulum hatasi degil
                raise EngineExit(5, "exchange_unreachable") from e
            if soft_reject:
                return _Rejected(e.code)
            raise EngineExit(8, f"startup_reject:{e.code}") from e

    def _startup_ban_persisted(self) -> None:
        """DD-7 §2: kalıcı/benimsenen ban penceresi sürerken HİÇ istek atılmaz; bekle ve çıkış 5 (kayıttaki http ne olursa olsun)."""
        try:                                           # gercek istemci hep tamsayi doner; sahte istemcide okunamayan deger = pencere yok
            until = int(self._rest.health().get("ban_until_ms") or 0)
            now_ms = int(self._rest.now_ms())
        except (TypeError, ValueError, AttributeError, KeyError):
            return
        if until <= now_ms:
            return
        left = (until - now_ms) / 1000.0
        wait = min(left + 2.0, STARTUP_BAN_SLEEP_MAX_S)
        log.critical("exchange_ban_persisted: host=%s kalan=%.0f sn; %.0f sn beklenip cikilacak (kod 5)",
                     getattr(self._rest, "_base", self._env), left, wait)
        self._clock.sleep(wait)
        raise EngineExit(5, "exchange_ban_persisted")

    def startup_check(self) -> None:
        live = self._env == "live"
        self._startup_ban_persisted()                  # DD-7: saat eşitlemesinden ÖNCE; istek 0
        # 1) saat
        for i in range(3):
            try:
                self._rest.sync_time()
                break
            except ExchangeUncertain:
                if i == 2:
                    raise EngineExit(5, "exchange_unreachable") from None
                self._clock.sleep(float(2 ** i))
            except ExchangeAuth as e:
                raise EngineExit(8, "auth_failed") from e
            except ExchangeBan as e:
                self._startup_ban(e)
            except ExchangeReject as e:
                if e.code == -1021:
                    raise EngineExit(5, "exchange_unreachable") from e
                raise EngineExit(8, f"startup_reject:{e.code}") from e
        # 2) anahtar izinleri (yalniz live)
        if live:
            self._check_permissions()
        else:
            log.info("testnet: api_restrictions denetimi atlandi")
        # 3) hesap
        acct = self._startup_call(self._rest.account)
        if not isinstance(acct, dict) or acct.get("canTrade") is not True:
            raise EngineExit(8, "account_cannot_trade")
        # DD-8 O4: cuzdan tavani testnet'te de denetlenir; ASIM acilisi durdurmaz (bulgu: motor girisi tutusla kapatir,
        # protect_first yine calisir). Okunamayan bakiye (yok/sayi degil/sonlu degil) fail-closed: kod 8.
        self._startup_findings = []
        self.startup_wallet = None
        wallet = _strict_float(acct.get("totalWalletBalance"))
        if wallet is None:
            raise EngineExit(8, "wallet_unreadable")
        self.startup_wallet = wallet
        if wallet > float(self._live.expected_wallet_max):             # kati '>' (esitlik asim degildir)
            self._startup_findings.append("wallet_above_expected")
            log.critical("wallet_above_expected: wallet=%s max=%s (acilis surer, girisler kapatilacak)", wallet,
                         self._live.expected_wallet_max)
        # 4) coklu varlik
        rows = self._startup_call(self._rest.position_risk) or []
        has_pos = any(_d(r.get("positionAmt")) != 0 for r in rows if isinstance(r, dict))
        if self._startup_call(self._rest.multi_assets):
            if has_pos:
                raise EngineExit(8, "multi_asset_mode")
            self._startup_call(self._rest.set_single_asset)
        # 5) pozisyon kipi
        if self._startup_call(self._rest.position_mode):
            orders = (self._startup_call(self._rest.open_orders) or []) + (self._startup_call(self._rest.open_conditionals) or [])
            if has_pos or orders:
                raise EngineExit(8, "hedge_mode_with_positions")
            self._startup_call(self._rest.set_one_way)
        # 6) cift basina marjin/kaldirac: ExchangeReject (-4048/-4047/-4161 ...) cifti hazirlanmamis birakir, acilis surer
        self._prepared.clear()
        held_pairs: set[str] = set()
        for p in self._pairs:
            s = self._sym[p]
            rejected: list[Any] = []
            for fn, args in ((self._rest.set_isolated, (s,)), (self._rest.set_leverage, (s, self._lev))):
                r0 = self._startup_call(fn, *args, soft_reject=True)
                if isinstance(r0, _Rejected):
                    rejected.append(r0.code)
            ok = False
            held = False
            pr = self._startup_call(self._rest.position_risk, s, soft_reject=(p in self._optional))
            if isinstance(pr, _Rejected):
                # Istege bagli (TradFi) cift: -1121/bolge kisiti gibi ret acilisi (kod 8 = kalici kapali) durdurmaz; cift hazirlanmamis
                # (giris yok). Acik pozisyon HESAP GENELI okumadan (adim 4) bilinir: varsa ASLA sessizce atlanmaz (held + CRITICAL;
                # protect_first/mutabakat yonetir). Cekirdek ciftler eskisi gibi fail-closed.
                self._ctr["optional_position_risk_failed"] += 1
                held_all = any(isinstance(r, dict) and r.get("symbol") == s and _d(r.get("positionAmt")) != 0 for r in rows)
                if held_all:
                    held_pairs.add(p)
                self._ctr["prepare_failed"] += 1
                log.log(logging.CRITICAL if held_all else logging.ERROR,
                        "optional_position_risk_failed:%s kod=%s held=%s (cift hazirlanmadi, giris yok)", p, pr.code, held_all)
                continue
            for r in pr or []:
                if isinstance(r, dict) and r.get("symbol") == s:
                    held = _d(r.get("positionAmt")) != 0
                    self._last_mark[p] = _fl(r.get("markPrice"), self._last_mark.get(p, 0.0)) or self._last_mark.get(p, 0.0)
                    ok = str(r.get("marginType", "")).lower() == "isolated" and int(_fl(r.get("leverage"))) == self._lev
            if held:
                held_pairs.add(p)
            if ok:
                self._prepared.add(p)
            else:
                self._ctr["prepare_failed"] += 1
                log.log(logging.CRITICAL if held else logging.ERROR,
                        "prepare_failed:%s (marjin/kaldirac dogrulanamadi; ret=%s held=%s)", p, rejected, held)
        # 7) kurallar: okunamazsa kod 5 (yeniden baslatilir); eksik cift + tutulan pozisyon = CRITICAL
        info = None
        for i in range(STARTUP_RULES_TRIES):
            try:
                info = self._rc("exchange_info")
                break
            except ExchangeBan as e:
                self._startup_ban(e)
            except ExchangeError:
                if i == STARTUP_RULES_TRIES - 1:
                    raise EngineExit(5, "exchange_unreachable") from None
                self._clock.sleep(float(2 ** (i + 1)))
        self._apply_rules(info)
        for p in self._pairs:
            if p not in self._rules:
                log.log(logging.CRITICAL if p in held_pairs else logging.ERROR,
                        "rules_missing:%s%s", p, " (POZISYON VAR: stop kurulamaz)" if p in held_pairs else "")
        # 8) komisyon orani
        for p in self._pairs:
            rate = None
            try:
                r = self._rest.commission_rate(self._sym[p])
                if isinstance(r, dict) and r.get("takerCommissionRate") is not None:
                    rate = float(str(r["takerCommissionRate"]))
            except (ExchangeError, ValueError):
                rate = None
            if rate is None or not math.isfinite(rate) or rate < 0:
                self._ctr[FEE_FALLBACK_CTR] += 1
                log.warning("fee_rate_fallback:%s", p)
            else:
                self._taker[p] = rate
        self._last_ok = self._now()
        self._rules_at = self._rules_at or self._now()

    def _check_permissions(self) -> None:
        """DD-8 O6: sonuc YALNIZ `apiRestrictions` yanitina baglidir; beyan yolu (LIVE_PERMISSION_ATTESTED) YOK.
        Okunamayan her durum ya yeniden denenir (kod 5) ya da kalici reddedilir (kod 8); gecis yalniz alti alan dogruysa."""
        if self._environ.get("LIVE_PERMISSION_ATTESTED"):
            log.warning("LIVE_PERMISSION_ATTESTED artik gecerli degil: izin denetimini etkilemez (yok sayildi)")
        try:
            r = self._rest.api_restrictions()
        except EngineExit:
            raise
        except ExchangeAuth as e:
            raise EngineExit(8, "auth_failed") from e
        except ExchangeBan as e:
            self._startup_ban(e)                 # 451/403 -> region_blocked (8); diger ban -> en cok 300 sn bekle, kod 5
            raise EngineExit(5, "exchange_unreachable") from e
        except ExchangeUncertain as e:
            raise EngineExit(5, "exchange_unreachable") from e
        except ExchangeReject as e:
            if e.code == -1021:
                raise EngineExit(5, "exchange_unreachable") from e
            raise EngineExit(8, "key_permission_unverifiable") from e
        except Exception as e:  # noqa: BLE001 - fail-closed
            raise EngineExit(8, "key_permission_unverifiable") from e
        if isinstance(r, dict):
            for field, want in _REQUIRED_PERMS:                    # ihlal onceligi: eksik alan olsa da ihlal once raporlanir
                if isinstance(r.get(field), bool) and r[field] is not want:
                    raise EngineExit(8, f"key_permission:{field}")
            if all(isinstance(r.get(f), bool) for f, _ in _REQUIRED_PERMS):
                return
        raise EngineExit(8, "key_permission_unverifiable")

    # ------------------------------------------------------------------ okumalar
    def account(self) -> BrokerAccount:
        now = self._now()
        if self._acct is not None and (now - self._acct[0]).total_seconds() < ACCOUNT_CACHE_S:
            return self._acct[1]
        a = self._read("account")
        acc = BrokerAccount(wallet=_fl(a.get("totalWalletBalance")), unrealized=_fl(a.get("totalUnrealizedProfit")),
                            equity=_fl(a.get("totalMarginBalance")), used_margin=_fl(a.get("totalInitialMargin")),
                            available=_fl(a.get("availableBalance")), ts=now)
        self._acct = (now, acc)
        return acc

    def account_cached(self) -> BrokerAccount | None:
        """WP-3: son okunan hesap, YASINA BAKMADAN; yoksa None. Ag cagrisi YAPMAZ (yalniz kayit olan MtM isareti kesintide
        yeniden denemeli REST cagrisini tetikleyemez)."""
        return None if self._acct is None else self._acct[1]

    def transfers(self, since: datetime, until: datetime) -> list:
        """12 §7 [V-8]: `GET /fapi/v1/income?incomeType=TRANSFER` (sembolsuz): vadeli cuzdana giren (+) / cikan (-) aktarimlar,
        `tranId` ile tekillestirilir. Okuma hatasi istisna olarak yukselir (cagiran fail-closed)."""
        from trader_core.risk_ladder import Transfer
        rows = self._read("income", None, "TRANSFER", _ms(since), _ms(until))
        out: dict[str, Transfer] = {}
        for r in rows or []:
            if not isinstance(r, Mapping):
                raise BrokerError("transfers: gecersiz satir (nesne degil)")   # RK-1 fix 3: atlama yok, fail-closed
            amt = _strict_float(r.get("income"))
            t_ms = _strict_float(r.get("time"))
            tid = str(r["tranId"]) if r.get("tranId") not in (None, "") else f"t{r.get('time')}:{r.get('income')}"
            if amt is None or t_ms is None:
                raise BrokerError("transfers: ayristirilamayan aktarim satiri")   # cagiran onceki sonucu korur
            out[tid] = Transfer(ts=_ts(t_ms, until), amount=amt, tran_id=tid, asset=str(r.get("asset") or ""))
        return sorted(out.values(), key=lambda x: (x.ts, x.tran_id))

    def _note_positions(self, rows: list[dict], now: datetime, track: bool = False) -> dict[str, dict]:
        """track=True yalniz `_sync`ten: orada gorulen acik pozisyon izlenir. Saf okumalar (positions()) izleme baslatmaz;
        kayit icin register_position() ya da `_sync` gerekir (acilis zamani yetkili olsun)."""
        cur: dict[str, dict] = {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            pair = self._pair(str(r.get("symbol", "")))
            mt = str(r.get("marginType", "")).lower()
            if mt in ("isolated", "cross"):
                self._margin_types[pair] = mt
            m = _fl(r.get("markPrice"))
            if m > 0:
                self._last_mark[pair] = m
            amt = _d(r.get("positionAmt"))
            if amt != 0:
                cur[pair] = r
                if track and pair not in self._open_pairs:
                    self._open_pairs.add(pair)
                    self._pos_since.setdefault(pair, min(now, _ts(r.get("updateTime"), now)) - POS_SINCE_MARGIN)
                self._last_pos[pair] = amt                 # son bilinen miktar (cikis tamamlanma alt siniri); izleme ayri
            elif pair not in self._open_pairs:
                self._last_pos.pop(pair, None)
        return cur

    def margin_types(self) -> dict[str, str]:
        """Son positionRisk okumasindan {pair: "isolated"|"cross"} (marginType alani; okunmayan cift yok). Ag cagrisi yapmaz."""
        return dict(self._margin_types)

    def positions(self) -> list[BrokerPosition]:
        now = self._now()
        rows = self._read("position_risk", protective=True)
        cur = self._note_positions(rows, now, track=False)
        out = []
        for pair in sorted(cur):
            r = cur[pair]
            amt = _d(r.get("positionAmt"))
            out.append(BrokerPosition(
                pair=pair, side="long" if amt > 0 else "short", qty=float(abs(amt)), entry_price=_fl(r.get("entryPrice")),
                leverage=int(_fl(r.get("leverage"), 0)), margin=_fl(r.get("isolatedMargin")),
                liq_price=_fl(r.get("liquidationPrice")), funding_paid=0.0, fee_paid_entry=0.0,
                opened_ts=_ts(r.get("updateTime"), now), mark_price=_fl(r.get("markPrice")) or None,
                unrealized=_fl(r.get("unRealizedProfit"))))
        return out

    def _to_order(self, r: dict, now: datetime) -> BrokerOrder:
        cid = str(r.get("clientAlgoId") or r.get("clientOrderId") or "")
        role = _cid_role(cid) or "exit"
        self._learn(r, self._pair(str(r.get("symbol", ""))))
        raw = str(r.get("algoStatus") or r.get("status") or "").upper()
        status = _STATUS_MAP.get(raw)
        if status is None:
            raise BrokerUncertain(f"bilinmeyen durum {raw!r}: {cid}")
        qty = _fl(r.get("quantity", r.get("origQty")))
        trig = _fl(r.get("triggerPrice", r.get("stopPrice")))
        executed = _fl(r.get("executedQty", r.get("actualQty")), 0.0)          # yalniz borsanin bildirdigi dolum; yoksa 0
        avg = _fl(r.get("avgPrice"))
        created = _ts(r.get("time", r.get("createTime", r.get("bookTime"))), now)
        return BrokerOrder(client_id=cid, pair=self._pair(str(r.get("symbol", ""))), role=role,
                           order_side="buy" if str(r.get("side", "")).upper() == "BUY" else "sell", qty=qty,
                           trigger_price=trig if trig > 0 else None, reduce_only=bool(r.get("reduceOnly", False)),
                           status=status, filled_qty=executed, avg_price=avg if avg > 0 else None,
                           created_ts=created, updated_ts=_ts(r.get("updateTime"), created))

    def _remember_stop(self, cid: str, pair: str) -> None:
        self._stops.pop(cid, None)
        self._stops[cid] = pair                                   # en yeni sonda

    def _learn(self, r: Mapping[str, Any], pair: str) -> None:
        """Her open_orders()/query()/aday sorgusu sonucundan kendi kimliklerimizi ogren (yeniden baslatma sonrasi atif)."""
        cid = str(r.get("clientAlgoId") or r.get("clientOrderId") or "")
        role = _cid_role(cid)
        if role is None:
            return
        if role in ("stop", "target"):
            self._remember_stop(cid, pair)
        elif role == "exit":
            self._exit_cids[cid] = pair
        for k in ("orderId", "actualOrderId"):
            v = r.get(k)
            if v not in (None, "", 0, "0"):
                self._order_ids[str(v)] = (cid, pair)

    def _open_rows(self, pair: str | None) -> list[dict]:
        sym = self._symbol(pair) if pair else None
        rows = list(self._read("open_orders", sym, protective=True) or []) + \
            list(self._read("open_conditionals", sym, protective=True) or [])
        seen, out = set(), []
        for r in rows:
            cid = str(r.get("clientAlgoId") or r.get("clientOrderId") or "")
            if sym is not None and r.get("symbol") != sym:
                continue
            if (cid, r.get("symbol")) in seen:
                continue
            seen.add((cid, r.get("symbol")))
            out.append(r)
        return out

    def open_orders(self, pair: str | None = None) -> list[BrokerOrder]:
        now = self._now()
        out = []
        for r in self._open_rows(pair):
            cid = str(r.get("clientAlgoId") or r.get("clientOrderId") or "")
            if _cid_role(cid) is not None:
                out.append(self._to_order(r, now))
        return out

    def foreign_open_orders(self) -> list[dict]:
        return [r for r in self._open_rows(None)
                if _cid_role(str(r.get("clientAlgoId") or r.get("clientOrderId") or "")) is None]

    def book_ticker(self, pair: str) -> tuple[float, float] | None:
        """WP-3 (3.5): (bid, ask) ya da None (yasak penceresi / agirlik >= %80: cagri HIC yapilmaz). Hatalar disari
        sizar (motor yutar); `_rc`/`_note_ban` yolundan gecmez: mevcut sayac ve kilitler degismez."""
        h = self._rest.health()
        if int(h.get("ban_until_ms") or 0) > int(self._rest.now_ms()):
            return None
        lim = float(getattr(self._rest, "weight_soft", 1200))
        if float(h.get("used_weight") or 0) >= 0.8 * lim:
            return None
        r = self._rest.book_ticker(self._symbol(pair))
        return float(r["bidPrice"]), float(r["askPrice"])

    def prepare(self, pair: str, leverage: int) -> None:
        if pair in self._prepared and leverage == self._lev:
            return
        raise BrokerError(f"prepare_failed:{pair} (startup_check gecmedi ya da kaldirac {leverage} != {self._lev})")

    def health(self) -> dict:
        try:
            h = dict(self._rest.health())
        except Exception:  # noqa: BLE001
            h = {}
        h.update(self._ctr)
        h["reachable"] = self._reachable
        h["last_sync_ts"] = None if self._last_ok is None else self._last_ok.isoformat().replace("+00:00", "Z")
        h["naked"] = list(self._naked)
        h["entries_blocked_reasons"] = list(self.entries_blocked_reasons)
        return h

    # ------------------------------------------------------------------ emir dogrulama / gonderim
    def _map_reject(self, cid: str, e: ExchangeReject, protective: bool = False) -> OrderResult:
        code = e.code
        if code is None:
            if e.msg == "order_rate_cap" or "order_rate_cap" in str(e):
                return self._rej(cid, "order_rate_cap")
            if e.http == 429 or e.msg == "rate_limited":
                self._note_429_reject()
                return self._rej(cid, "rate_limited")
            return self._unknown(cid, "none")
        if code in _KNOWN_REASON:
            return self._rej(cid, _KNOWN_REASON[code])
        if code in _FILTER_CODES:
            if protective:
                self._rules_dirty = True               # koruyucu yol: satir ici yenileme (yeniden denemeli) yok; sonraki _sync yeniler
            else:
                self.refresh_rules()
            return self._rej(cid, f"filter:{code}")
        if code == -1021:
            self._ctr["clock_rejects"] += 1
            return self._rej(cid, "exchange_-1021")
        return self._unknown(cid, str(code))

    def _unknown(self, cid: str, code: str) -> OrderResult:
        self._ctr["unknown_reject_codes"] += 1
        self._block("exchange_unknown_code")
        log.critical("taninmayan borsa ret kodu %s (%s)", code, cid)
        return self._rej(cid, f"exchange_{code}")

    def _common_checks(self, req: OrderRequest, roles: tuple[str, ...], allow_stale: bool) -> tuple[str | None, _RuleEntry | None]:
        if req.role not in roles:
            return "bad_role", None
        if req.order_side not in ("buy", "sell"):
            return "bad_side", None
        if not _finite_pos(req.qty):
            return "qty", None
        e = self._entry_any(req.pair)
        if e is None:
            self._rules_dirty = True
            if req.pair in self._open_pairs:
                log.critical("rules_missing:%s pozisyon varken (%s)", req.pair, req.role)
            return "rules_missing", None
        if not allow_stale:
            try:
                self.rules(req.pair)
            except DataError:
                return "rules_stale", None
        if not is_multiple(req.qty, e.rules.step):
            return "step", e
        if req.qty > e.rules.max_qty:
            return "max_qty", e
        if req.role == "entry" and req.qty < e.rules.min_qty:
            return "min_qty", e                            # DD-2 D4/D5: yerel `market_min` denetimi; yalniz giris (koruyucu stop/cikis degil)
        return None, e

    def _qty_str(self, qty: float, e: _RuleEntry | None) -> str:
        if e is None:                                     # kural yok (yalniz reduceOnly cikis): miktar verildigi gibi
            return _num(D(repr(float(qty))))
        step = e.spec.market_step
        return _num((D(repr(float(qty))) / step).to_integral_value() * step)

    def _absorb_errors(self, cid: str, fn, protective: bool = False) -> Any:
        """Emir POST'u: Reject -> OrderResult, Ban -> rejected(exchange_ban), Auth -> rejected(exchange_auth),
        Uncertain -> BrokerUncertain."""
        try:
            return fn()
        except ExchangeReject as e:
            return self._map_reject(cid, e, protective)
        except ExchangeBan as e:
            self._note_ban(e)
            return self._rej(cid, "exchange_ban")
        except ExchangeAuth:
            self._ctr["exchange_auth"] += 1
            self._block("exchange_auth")
            log.critical("exchange_auth: emir reddedildi (%s)", cid)
            return self._rej(cid, "exchange_auth")
        except ExchangeUncertain as e:
            raise BrokerUncertain(f"emir belirsiz: {cid}") from e

    def _weight_high(self) -> bool:
        """DD-7 §5: kullanılan IP ağırlığı `weight_soft` ve üstü mü. Yasak penceresi etkinse False (ban yolu önce gelir).
        Fail-closed: health() istisna verir ya da used_weight sayı değilse True."""
        try:
            h = self._rest.health()
            if int(h.get("ban_until_ms") or 0) > int(self._rest.now_ms()):
                return False
            w = h.get("used_weight")
            if isinstance(w, bool) or not isinstance(w, (int, float)) or w != w:
                return True
            return float(w) >= float(getattr(self._rest, "weight_soft", 1200))
        except Exception:  # noqa: BLE001
            return True

    def _verify_account_mode(self, pair: str, symbol: str) -> bool:
        """DD-8 D2: giris oncesi TAZE `positionRisk(symbol)`: satir var + marginType isolated + leverage == cfg.leverage.
        Uyusmazlik -> `account_mode_drift`; okunamayan her sey -> `account_mode_unverified` (ikisinde de emir gitmez, False).
        `_prepared` ve hesap ayarlari DEGISMEZ (motor kendiliginden set_isolated/set_leverage gondermez)."""
        try:
            rows = self._rc("position_risk", symbol)
        except ExchangeBan as e:
            self._note_ban(e)
            self._ctr["account_mode_unverified_ban"] += 1     # DD-9 §8.1: yasak kaynakli dogrulanamama (saglik alarmindan dusulur)
            return self._unverified(pair, f"ban http={getattr(e, 'http', None)}")
        except ExchangeAuth:
            self._ctr["exchange_auth"] += 1
            self._block("exchange_auth")
            log.critical("exchange_auth: giris oncesi hesap modu okumasi reddedildi (%s)", pair)
            return self._unverified(pair, "auth")
        except Exception as e:  # noqa: BLE001 - fail-closed (her ExchangeError dahil)
            return self._unverified(pair, type(e).__name__)
        mine = [r for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict) and r.get("symbol") == symbol]
        if not mine:
            return self._unverified(pair, "no_row")
        for r in mine:
            margin, lev_raw = r.get("marginType"), _strict_float(r.get("leverage"))
            if not isinstance(margin, str) or not margin or lev_raw is None:
                return self._unverified(pair, "missing_field")
            lev = int(lev_raw) if float(lev_raw).is_integer() else None
            if margin.lower() != "isolated" or lev != self._lev:
                self._ctr["account_mode_drift"] += 1
                log.critical("account_mode_drift:%s margin=%s leverage=%s", pair, margin, r.get("leverage"))
                return False
        return True

    def _unverified(self, pair: str, why: str) -> bool:
        self._ctr["account_mode_unverified"] += 1
        log.error("account_mode_unverified:%s (%s): giris gonderilmedi", pair, why)
        return False

    def market_order(self, req: OrderRequest) -> OrderResult:
        cid = req.client_id
        why, e = self._common_checks(req, ("entry", "exit"), allow_stale=req.role == "exit")
        if why == "rules_missing" and req.role == "exit":
            why, e = None, None                          # reduceOnly cikis kural eksikligiyle YEREL olarak engellenmez
        if why is None and e is not None:
            if req.role == "entry":
                if req.pair not in self._prepared:
                    why = "not_prepared"
                elif req.leverage != self._lev:
                    why = "leverage_mismatch"
                else:
                    ref = self._last_mark.get(req.pair)
                    if ref and req.qty * ref < e.rules.min_notional:
                        why = "min_notional"
        if why is not None:
            return self._rej(cid, why)
        symbol, side = self._symbol(req.pair), "BUY" if req.order_side == "buy" else "SELL"
        reduce_only = req.role == "exit"
        if req.role == "entry" and self._env != "testnet" and self._weight_high():       # DD-7 §5: D2 okumasından ÖNCE, istek 0
            self._ctr["entry_weight_rejects"] += 1
            log.warning("weight_high:%s: kullanilan agirlik esikte; giris gonderilmedi", req.pair)
            return self._rej(cid, "weight_high")
        if req.role == "entry" and not self._verify_account_mode(req.pair, symbol):     # DD-8 D2: emir POST'undan hemen once
            return self._rej(cid, "not_prepared")
        out = self._absorb_errors(cid, lambda: self._rest.new_market(symbol, side, self._qty_str(req.qty, e), cid, reduce_only),
                                  protective=reduce_only)
        if isinstance(out, OrderResult):
            return out
        body = out if isinstance(out, dict) else {}
        oid = body.get("orderId")
        if oid is not None:
            self._order_ids[str(oid)] = (cid, req.pair)
        if req.role == "exit":
            self._exit_cids[cid] = req.pair
        body = self._wait_fill(symbol, cid, body)
        info = _Pending(req.pair, req.role, req.order_side, bool(req.partial and req.role == "exit"))
        if info.partial:
            self.register_partial(req.pair, cid, None if oid is None else str(oid))
        outcome, qty, avg, fee = self._settle(info, cid, body)
        oid_s = None if oid is None else str(oid)
        if outcome == "filled" and req.role == "entry":
            return OrderResult("filled", cid, oid_s, qty, avg, fee, None, self._now())
        if outcome == "pending":
            self._pending_market[cid] = info
        if outcome == "rejected":
            return self._rej(cid, "exchange_rejected")
        return OrderResult("accepted", cid, oid_s, 0.0, None, 0.0, None, self._now())

    def _wait_fill(self, symbol: str, cid: str, body: dict) -> dict:
        waited = 0.0
        while str(body.get("status", "")).upper() in ("NEW", "PARTIALLY_FILLED") and waited < FILL_WAIT_S - 1e-9:
            self._clock.sleep(FILL_POLL_S)
            waited += FILL_POLL_S
            try:
                q = self._rc("query_order", symbol, cid, protective=True, attempts=1)
            except ExchangeError:
                break
            if isinstance(q, dict):
                body = q
        return body

    def _settle(self, info: _Pending, cid: str, body: dict) -> tuple[str, float, float | None, float]:
        """Piyasa emri son durumu (§5.3). -> (sonuc, doldurulan, ort. fiyat, fee); olaylari kuyruga yazar."""
        pair, status = info.pair, str(body.get("status", "")).upper()
        ex = _d(body.get("executedQty"))
        now = self._now()
        if status in ("NEW", "PARTIALLY_FILLED") or status not in ("FILLED", "EXPIRED", "CANCELED", "REJECTED"):
            return "pending", 0.0, None, 0.0
        if status == "REJECTED":
            return "rejected", 0.0, None, 0.0
        entry = info.role == "entry"
        if status == "FILLED" or (ex > 0 and entry):
            avg = _fl(body.get("avgPrice"))
            if entry:
                if ex <= 0:                                     # DD-11 Z-1: FILLED ama miktar 0 -> dolum yok, pending
                    return self._zero_fill_wait(pair, cid, "executedQty<=0")
                if not (math.isfinite(avg) and avg > 0):
                    px = self._recover_entry_price(pair, cid, body, ex)
                    if px is None:
                        return self._zero_fill_wait(pair, cid, "avgPrice bilinmiyor")
                    avg = px
                self._zero_fill.pop(cid, None)
                self._zero_fill_last.pop(cid, None)
                cum = _d(body.get("cumQuote")) or ex * D(repr(avg))
                fee = float(cum) * self._taker_rate(pair)
                ts = _ts(body.get("updateTime"), now)
                sign = D(1) if info.side == "buy" else D(-1)
                self._open_pairs.add(pair)
                self._last_pos[pair] = sign * ex
                self._pos_since[pair] = now - POS_SINCE_MARGIN
                self._entry_fee[pair] = fee
                self._push(BrokerEvent("fill", ts, pair, cid, Fill(cid, pair, "entry", info.side, float(ex), avg, fee, ts, "market")))  # type: ignore[arg-type]
                return "filled", float(ex), avg, fee
            if info.partial and self._settle_partial(info, cid, body, ex, avg, now):
                return "filled", float(ex), avg, 0.0
            self._pending_close[pair] = self._pos_since.get(pair) or now - timedelta(days=1)
            self._try_close(pair, rereads=0)
            return "filled", float(ex), avg, 0.0
        if ex > 0:                                              # cikis kismi
            self._push(BrokerEvent("order_rejected", now, pair, cid, detail=f"partial_exit:{_num(ex)}"))
            return "partial_exit", float(ex), None, 0.0
        self._push(BrokerEvent("order_rejected", now, pair, cid, detail="expired_unfilled"))
        return "expired_unfilled", 0.0, None, 0.0

    def register_partial(self, pair: str, cid: str, oid: str | None = None) -> None:
        """Cikis kipleri: kismi kar alma emri kimligi (motor acilista/yeniden baslatmada da bildirir). Bu emrin islemleri son
        kapanis olayindan dislanir (kismi bacak motorda ayri dolum olarak islenir; defter karma fiyati kendisi hesaplar)."""
        if not cid:
            return
        self._partial_cids.setdefault(pair, set()).add(cid)
        if oid:
            self._partial_oids.setdefault(pair, set()).add(str(oid))

    def _partial_oid_set(self, pair: str) -> set[str]:
        """Kismi emirlerin orderId'leri; bilinmeyen kimlikler (yeniden baslatma) sorgulanir. Sorgulanamazsa _Retry."""
        out = set(self._partial_oids.get(pair, ()))
        known_cids = {c for o, (c, p) in self._order_ids.items() if p == pair}
        for cid in sorted(self._partial_cids.get(pair, ())):
            hit = next((o for o, (c, p) in self._order_ids.items() if c == cid and p == pair), None)
            if hit is not None:
                out.add(hit)
                continue
            if cid in known_cids:
                continue
            try:
                r = self._rc("query_order", self._symbol(pair), cid, protective=True, attempts=1)
            except ExchangeReject:
                continue                                        # emir yok (kesin): dislanacak islem de yok
            except ExchangeError:
                raise _Retry() from None
            if isinstance(r, dict) and r.get("orderId") is not None:
                out.add(str(r["orderId"]))
                self._partial_oids.setdefault(pair, set()).add(str(r["orderId"]))
        return out

    def _settle_partial(self, info: _Pending, cid: str, body: dict, ex: Decimal, avg: float, now: datetime) -> bool:
        """Kismi kar alma emrinin dolumu: pozisyon acik kalir (kapanis cozumu YOK); dolum olayi dogrudan emirden uretilir ve son
        bilinen miktar dusurulur. False: emir aslinda tum pozisyonu kapatti / veri eksik -> normal kapanis yolu."""
        pair = info.pair
        known = self._last_pos.get(pair)
        spec = (self._rules.get(pair).spec if pair in self._rules else None)       # type: ignore[union-attr]
        eps = (spec.market_step / 2) if spec is not None else D("1e-9")
        if known is None or known == 0 or ex <= 0 or ex >= abs(known) - eps:
            return False
        if not (math.isfinite(avg) and avg > 0):
            cum = _d(body.get("cumQuote"))
            avg = float(cum / ex) if cum > 0 else float("nan")
            if not (math.isfinite(avg) and avg > 0):
                return False
        ts = _ts(body.get("updateTime"), now)
        fee = self._order_commission(pair, body, ex, avg)
        sign = 1 if known > 0 else -1
        self._last_pos[pair] = known - D(sign) * ex
        self._ctr["partial_exit_events"] += 1
        self._push(BrokerEvent("fill", ts, pair, cid, Fill(cid, pair, "exit", info.side, float(ex), avg, fee, ts, "market")))  # type: ignore[arg-type]
        return True

    def _order_commission(self, pair: str, body: dict, ex: Decimal, avg: float) -> float:
        """Emrin gercek komisyonu (userTrades, USDT); okunamazsa/USDT degilse taker orani tahmini (sayac)."""
        oid = body.get("orderId")
        if oid is not None:
            since = _ts(body.get("time", body.get("updateTime")), self._now()) - timedelta(minutes=5)
            try:
                trades = self._rc("user_trades", self._symbol(pair), _ms(since))
            except ExchangeError:
                trades = None
            rows = [t for t in (trades or []) if isinstance(t, dict) and str(t.get("orderId")) == str(oid)]
            if rows and all(str(t.get("commissionAsset", "USDT")) == "USDT" for t in rows):
                return float(sum((_d(t.get("commission")) for t in rows), D(0)))
        self._ctr["partial_fee_estimated"] += 1
        return float(ex) * avg * self._taker_rate(pair)

    def _zero_fill_wait(self, pair: str, cid: str, why: str) -> tuple[str, float, float | None, float]:
        """DD-11 D1: sifir/bilinmeyen dolum bekleme sayaci. >=3 deneme VE >=30 sn sonra emri birakir (order_rejected YOK:
        gercek pozisyon var olabilir); bulgu + CRITICAL + giris engeli. Aksi halde "pending"."""
        now = self._now()
        first, n = self._zero_fill.get(cid, (now, 0))
        n += 1
        self._zero_fill[cid] = (first, n)
        self._ctr["zero_fill_pending"] += 1
        if n >= 3 and (now - first).total_seconds() >= 30.0:
            self._zero_fill.pop(cid, None)
            self._zero_fill_last.pop(cid, None)
            self._ctr["zero_fill_unresolved"] += 1
            self.findings.append(f"zero_fill_unresolved:{cid}")
            self._block("zero_fill_unresolved")
            log.critical("zero_fill_unresolved:%s %s (%s); emir birakildi, giris engellendi, mutabakat cozecek", pair, cid, why)
            return "zero_fill_unresolved", 0.0, None, 0.0
        log.warning("zero_fill_pending:%s %s %s; emir pending (deneme %d)", pair, cid, why, n)
        return "pending", 0.0, None, 0.0

    def _recover_entry_price(self, pair: str, cid: str, body: dict, ex: Decimal) -> float | None:
        """DD-11 Z-1: avgPrice<=0 iken fiyat = cumQuote/executedQty, o da yoksa emrin userTrades VWAP'i; yoksa None."""
        cum = _d(body.get("cumQuote"))
        if ex > 0 and cum > 0:
            v = float(cum / ex)
            if math.isfinite(v) and v > 0:
                return v
        oid = body.get("orderId")
        if oid is None:
            oid = next((k for k, (c, _p) in self._order_ids.items() if c == cid), None)
        if oid is None:
            return None
        now = self._now()
        last = self._zero_fill_last.get(cid)
        if last is not None and (now - last).total_seconds() < float(self._live.poll_open_s):
            return None                                     # DD-11 D1: userTrades en fazla poll_open_s'de bir
        self._zero_fill_last[cid] = now
        since = _ts(body.get("time", body.get("updateTime")), now) - timedelta(minutes=5)
        try:
            trades = self._rc("user_trades", self._symbol(pair), _ms(since))
        except ExchangeBan as e:
            self._note_ban(e)
            return None
        except ExchangeError:
            return None
        q_sum, n_sum = D(0), D(0)
        for t in trades or []:
            if not isinstance(t, dict) or str(t.get("orderId")) != str(oid):
                continue
            q, pr = _d(t.get("qty")), _d(t.get("price"))
            if q > 0 and pr > 0:
                q_sum += q
                n_sum += q * pr
        if q_sum <= 0:
            return None
        v = float(n_sum / q_sum)
        return v if math.isfinite(v) and v > 0 else None

    def _protective(self, req: OrderRequest, kind: str) -> OrderResult:
        cid = req.client_id
        role = "stop" if kind == "STOP_MARKET" else "target"
        if req.role != role:
            return self._rej(cid, "bad_role")
        if req.reduce_only is not True:
            return self._rej(cid, "not_reduce_only")
        if req.working_type != "MARK_PRICE":
            return self._rej(cid, "bad_working_type")
        why, e = self._common_checks(req, (role,), allow_stale=True)
        if why is not None:
            return self._rej(cid, why)
        assert e is not None
        if not _finite_pos(req.trigger_price):
            return self._rej(cid, "trigger_price")
        direction = 1 if req.order_side == "sell" else -1          # sell = uzun pozisyonu korur
        trig = D(repr(float(req.trigger_price)))                    # type: ignore[arg-type]
        trig = round_stop_tight(trig, direction, e.spec) if role == "stop" else round_target_easy(trig, direction, e.spec)
        if trig <= 0:
            return self._rej(cid, "trigger_price")
        symbol, side = self._symbol(req.pair), "BUY" if req.order_side == "buy" else "SELL"
        out = self._absorb_errors(cid, lambda: self._rest.new_conditional(symbol, kind, side, self._qty_str(req.qty, e), _num(trig),
                                                                          cid, "MARK_PRICE"), protective=True)
        if isinstance(out, OrderResult):
            return out
        body = dict(out) if isinstance(out, dict) else {}
        requeried = False

        def requery() -> None:
            """Eksik/anlasilmaz yanit alanlari icin TEK sorgu (attempts=1); sonucu govdeye doldurur."""
            nonlocal requeried
            if requeried:
                return
            requeried = True
            try:
                q = self._rc("query_conditional", symbol, cid, protective=True, attempts=1)
            except ExchangeError:
                return
            if isinstance(q, dict):
                for k, v in q.items():
                    if body.get(k) in (None, ""):
                        body[k] = v

        def status() -> str:
            return str(body.get("algoStatus") or body.get("status") or "").upper()

        if status() not in _STOP_OK | _STOP_DEAD:
            requery()
        st = status()
        if st in _STOP_DEAD:                                    # kesin: kurulmadi (F2 yolu)
            return self._rej(cid, f"exchange_status:{st}")
        if st not in _STOP_OK:
            raise BrokerUncertain(f"koruyucu emir yaniti anlasilmaz ({cid}): durum={st!r}")
        echo_cid = body.get("clientAlgoId", body.get("clientOrderId"))
        bad = None
        if echo_cid is not None and str(echo_cid) != cid:
            bad = "client_id"
        elif "reduceOnly" in body and body["reduceOnly"] is not True:
            bad = "reduceOnly"
        elif body.get("closePosition") is True:
            bad = "closePosition"
        wt = body.get("workingType")
        if bad is None and wt is None:
            requery()
            wt = body.get("workingType")
            if "reduceOnly" in body and body["reduceOnly"] is not True:
                bad = "reduceOnly"
        if bad is not None or (wt is not None and wt != "MARK_PRICE"):
            if bad is not None:
                self._ctr["stop_response_mismatch"] += 1
                log.critical("koruyucu emir yaniti uyusmazligi %s: %s", cid, bad)
            else:
                self._ctr["working_type_mismatch"] += 1
                log.critical("workingType uyusmazligi %s: %s", cid, wt)
            try:
                self._rest.cancel_conditional(symbol, cid)
            except ExchangeError:
                log.critical("uyusmayan koruyucu emir iptal edilemedi: %s", cid)
                self.findings.append(f"uncancelled_protective:{cid}")
            return self._rej(cid, "working_type_mismatch" if bad is None else f"response_mismatch:{bad}")
        if wt is None:                                          # dogrulanamadi: kabul et, ama giris kapat (yapiskan)
            self._ctr["working_type_unverified"] += 1
            self._block("working_type_unverified")
            log.critical("workingType dogrulanamadi %s: yanit ve sorgu alani vermedi", cid)
        self._remember_stop(cid, req.pair)
        oid = body.get("algoId", body.get("orderId"))
        return OrderResult("accepted", cid, None if oid is None else str(oid), 0.0, None, 0.0, None, self._now())

    def place_stop(self, req: OrderRequest) -> OrderResult:
        return self._protective(req, "STOP_MARKET")

    def place_target(self, req: OrderRequest) -> OrderResult:
        return self._protective(req, "TAKE_PROFIT_MARKET")

    def cancel(self, pair: str, client_id: str) -> None:
        sym = self._symbol(pair)
        try:
            if _cid_role(client_id) in ("stop", "target"):
                self._rest.cancel_conditional(sym, client_id)
                if self._stops.pop(client_id, None) is not None:           # yalniz son birkac iptal gec tetiklenme atfi icin tutulur
                    lst = self._cancelled.setdefault(pair, [])
                    lst.append(client_id)
                    del lst[:-STOP_KEEP]
            else:
                self._rest.cancel_order(sym, client_id)
        except ExchangeBan as e:
            self._note_ban(e)
            raise BrokerUncertain(f"iptal gonderilmedi (ban): {client_id}") from None
        except ExchangeUncertain as e:
            raise BrokerUncertain(f"iptal belirsiz: {client_id}") from e
        except ExchangeAuth as e:
            raise BrokerError("exchange_auth") from e
        except ExchangeReject as e:
            raise BrokerError(f"iptal reddedildi code={e.code}") from None

    def query(self, pair: str, client_id: str) -> BrokerOrder | None:
        sym = self._symbol(pair)
        try:
            if _cid_role(client_id) in ("stop", "target"):
                r = self._rc("query_conditional", sym, client_id, protective=True, attempts=1)
            else:
                r = self._rc("query_order", sym, client_id, protective=True, attempts=1)
        except ExchangeBan as e:
            self._note_ban(e)
            raise BrokerUncertain(f"sorgu gonderilmedi (ban): {client_id}") from None
        except ExchangeUncertain as e:
            raise BrokerUncertain(f"sorgu belirsiz: {client_id}") from e
        except (ExchangeAuth, ExchangeReject) as e:
            raise BrokerError(f"sorgu hatasi: {type(e).__name__}") from None
        if r is None:
            return None
        return self._to_order(r, self._now())

    # ------------------------------------------------------------------ poll / _sync (§7)
    def poll(self, now: datetime) -> list[BrokerEvent]:
        try:
            self._sync(now)
        except Exception:  # noqa: BLE001  (poll asla patlamaz; olay kaybi yok: kuyruk korunur)
            log.exception("sync hatasi")
        self._queue.sort(key=lambda t: (t[0], t[1]))
        evs = [t[2] for t in self._queue]
        self._queue.clear()
        self._maybe_sync_clock(now, evs)
        return evs

    def _maybe_sync_clock(self, now: datetime, evs: list) -> None:
        """DD-2 D5: 30 dakikada bir saat esitleme. Koruyucu yolu geciktirmez: yalniz bu turda olay (dolum vb.) YOKKEN, bekleyen
        kapanis/stopsuz pozisyon YOKKEN, tek deneme ve kisa zaman asimiyla (order_timeout_s). Ban penceresi burada degil
        `_send` icinde uygulanir (ban varken istek gitmez). Hata sessizce yutulur (bir sonraki 30 dk)."""
        if self._last_clock_sync is None:
            self._last_clock_sync = now
            return
        if (now - self._last_clock_sync).total_seconds() < CLOCK_SYNC_S:
            return
        if evs or self._pending_market or self._pending_close or self._naked:
            return
        fn = getattr(self._rest, "sync_time_once", None)
        if fn is None:
            return
        self._last_clock_sync = now
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.warning("periyodik saat esitleme basarisiz: %s", type(e).__name__)

    def _sync(self, now: datetime) -> None:
        if self._rules_dirty or (self._rules_at is not None and (now - self._rules_at).total_seconds() >= RULES_REFRESH_S):
            self.refresh_rules()
            self._rules_at = now                # basarisizsa da saatte bir dene (yaslanma ts'ten hesaplanir)
            self._rules_dirty = False
        self._poll_pending()                    # bekleyen piyasa emirleri HER turda sorgulanir (giris hala NEW olabilir)
        watching = bool(self._open_pairs or self._pending_market or self._pending_close)
        interval = self._live.poll_open_s if watching else self._live.poll_flat_s
        if self._last_sync is not None and (now - self._last_sync).total_seconds() < interval:
            self._retry_closings(now)
            return
        try:
            rows = self._rc("position_risk")
        except ExchangeBan as e:
            self._note_ban(e)
            self._reachable = False             # ban penceresi boyunca ulasilamaz (giris engeli kurulmaz: ban ayri sayilir)
            return
        except ExchangeAuth:
            self._last_sync = now
            self._ctr["exchange_auth"] += 1
            self._block("exchange_auth")
            log.critical("exchange_auth: runtime yetki hatasi (_sync)")
            return
        except ExchangeError:
            self._last_sync = now
            self._ctr["sync_failures"] += 1
            self._fails += 1
            self._reachable = False
            if self._fails >= 3:
                self._block("exchange_unreachable")
            return
        self._last_sync = now
        self._fails, self._reachable, self._last_ok = 0, True, now
        self._blocks.discard("exchange_unreachable")        # yalniz bu neden ilk basarili esitlemede kalkar
        before = set(self._open_pairs)
        cur = self._note_positions(rows or [], now, track=True)
        for pair in before - set(cur):
            self._open_pairs.discard(pair)
            self._pending_close.setdefault(pair, self._pos_since.get(pair) or now - timedelta(days=1))
        for pair in list(self._pending_close):
            if pair in cur:
                self._clear_pending_close(pair)      # hala pozisyon var (kismi cikis / yeniden giris)
        self._retry_closings(now)

    def _poll_pending(self) -> None:
        for cid, info in list(self._pending_market.items()):
            try:
                q = self._rc("query_order", self._symbol(info.pair), cid, protective=True, attempts=1)
            except ExchangeBan as e:
                self._note_ban(e)
                continue
            except ExchangeError:
                continue
            if q is None:                                    # POST kabul etmisti; tek -2013 yetmez (gecikmeli gorunurluk)
                now = self._now()
                first, n = self._pending_nf.get(cid, (now, 0))
                n += 1
                self._pending_nf[cid] = (first, n)
                if n >= PENDING_NF_TRIES and (now - first).total_seconds() >= PENDING_NF_SPAN_S:
                    del self._pending_market[cid]
                    del self._pending_nf[cid]
                    self.findings.append(f"pending_order_not_found:{cid}")
                    self._push(BrokerEvent("order_rejected", now, info.pair, cid, detail="pending_not_found"))
                    log.critical("bekleyen emir bulunamadi: %s", cid)
                continue
            self._pending_nf.pop(cid, None)
            outcome, *_ = self._settle(info, cid, q)
            if outcome != "pending":
                del self._pending_market[cid]
                self._pending_nf.pop(cid, None)

    def _clear_pending_close(self, pair: str) -> None:
        for d in (self._pending_close, self._pc_first, self._pc_tries, self._pc_next):
            d.pop(pair, None)

    def _retry_closings(self, now: datetime) -> None:
        for pair in list(self._pending_close):
            nxt = self._pc_next.get(pair)
            if nxt is not None and now < nxt:
                continue                                      # ilk birkac denemeden sonra poll_open_s'de bir
            self._try_close(pair, rereads=0)

    def _try_close(self, pair: str, rereads: int) -> None:
        since = self._pending_close.get(pair)
        if since is None:
            return
        evs = self._closing(pair, since, self._hints.get(pair, ()), rereads)
        if evs:
            self._clear_pending_close(pair)
            for e in evs:
                self._push(e)
            return
        now = self._now()
        first = self._pc_first.setdefault(pair, now)
        n = self._pc_tries[pair] = self._pc_tries.get(pair, 0) + 1
        if n >= CLOSE_FAST_TRIES:
            self._pc_next[pair] = now + timedelta(seconds=float(self._live.poll_open_s))
        if (now - first).total_seconds() >= CLOSE_GIVEUP_S and f"close_unresolved:{pair}" not in self.findings:
            self._ctr["close_unresolved"] += 1
            self.findings.append(f"close_unresolved:{pair}")
            log.critical("close_unresolved:%s (%.0f sn'dir cikis islemleri cozulemiyor)", pair, (now - first).total_seconds())

    # ------------------------------------------------------------------ cikis olaylari (§5.5)
    def closing_events(self, pair: str, since: datetime, client_ids: Sequence[str] = ()) -> list[BrokerEvent]:
        return self._closing(pair, since, tuple(client_ids), 3)

    def _finish(self, pair: str) -> None:
        self._open_pairs.discard(pair)
        self._last_pos.pop(pair, None)
        self._pos_since.pop(pair, None)
        self._clear_pending_close(pair)
        self._funding_wait.pop(pair, None)
        self._entry_fee.pop(pair, None)
        self._hints.pop(pair, None)
        self._registered.discard(pair)
        self._partial_cids.pop(pair, None)
        self._partial_oids.pop(pair, None)
        self._cancelled.pop(pair, None)
        for d in (self._stops, self._exit_cids):
            for c in [c for c, p in d.items() if p == pair]:
                del d[c]
        for o in [o for o, (_, p) in self._order_ids.items() if p == pair]:
            del self._order_ids[o]

    def _closing(self, pair: str, since: datetime, hints: Sequence[str], rereads: int) -> list[BrokerEvent]:
        try:
            return self._closing_inner(pair, since, hints, rereads)
        except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError) as e:      # bozuk islem satiri: yeniden dene
            self._ctr["malformed_trades"] += 1
            log.error("closing %s: bozuk islem/gelir satiri (%s); bos donuluyor", pair, type(e).__name__)
            return []

    def _closing_inner(self, pair: str, since: datetime, hints: Sequence[str], rereads: int) -> list[BrokerEvent]:
        symbol, now = self._symbol(pair), self._now()
        spec = (self._rules.get(pair).spec if pair in self._rules else None)       # type: ignore[union-attr]
        eps = (spec.market_step / 2) if spec is not None else D("1e-9")
        known = self._last_pos.get(pair)
        sel = None
        for i in range(rereads + 1):
            try:
                trades = self._rc("user_trades", symbol, _ms(since) - 1000)
            except ExchangeError:
                return []
            try:
                skip = self._partial_oid_set(pair) if self._partial_cids.get(pair) else frozenset()
            except _Retry:
                return []
            sel = self._select(trades or [], known, eps, skip)
            if sel is not None:
                break
            if i < rereads:
                self._clock.sleep(1.0)
        if sel is None:
            return []
        reduces, entries, d_sign = sel                       # reduces: en yeni basta
        if reduces[0]["id"] in self._delivered:
            return []
        final = reduces[0]
        try:
            kind, cid, detail = self._classify(symbol, pair, final, hints, since)
        except _Retry:
            return []
        # funding (§5.5 madde 4)
        qty = sum((_d(t["qty"]) for t in reduces), D(0))
        vw = sum((_d(t["qty"]) * _d(t["price"]) for t in reduces), D(0)) / qty
        ts = max(_ts(t["time"], now) for t in reduces)
        fund: list[BrokerEvent] = []
        try:
            inc = self._rc("income", symbol, "FUNDING_FEE", _ms(since), _ms(ts) + 5000) or []
            self._funding_wait.pop(pair, None)
            new_keys = []
            for r in sorted(inc, key=lambda x: int(_fl(x.get("time")))):
                key = (symbol, str(r["tranId"])) if r.get("tranId") else (symbol, r.get("time"), str(r.get("income")))
                if key in self._delivered_funding:
                    continue
                new_keys.append(key)
                fts = min(_ts(r.get("time"), ts), ts)
                fund.append(BrokerEvent("funding", fts, pair, funding_paid=-_fl(r.get("income"))))
            self._delivered_funding.update(new_keys)
        except ExchangeError:
            w = self._funding_wait.setdefault(pair, now)
            if (now - w).total_seconds() < FUNDING_GIVEUP_S:
                return []
            self._funding_wait.pop(pair, None)
            self._ctr["funding_unresolved"] += 1
            self.findings.append(f"funding_unresolved:{pair}")
            log.critical("funding_unresolved:%s (cikis funding_paid=0 ile)", pair)
        # komisyon
        non_usdt = any(str(t.get("commissionAsset", "USDT")) != "USDT" for t in reduces)
        if non_usdt:
            fee = float(qty * vw) * self._taker_rate(pair)
            self._ctr["fee_asset_unexpected"] += 1
            log.critical("fee_asset_unexpected:%s", pair)
        else:
            fee = float(sum((_d(t.get("commission")) for t in reduces), D(0)))
        est = self._entry_fee.get(pair)
        if est and entries and all(str(t.get("commissionAsset", "USDT")) == "USDT" for t in entries):
            act = float(sum((_d(t.get("commission")) for t in entries), D(0)))
            if act > 0 and abs(act - est) / act > FEE_DRIFT_REL:
                self._ctr["fee_drift"] += 1
                log.warning("fee_drift:%s tahmin=%s gercek=%s", pair, est, act)
        side = "sell" if d_sign > 0 else "buy"
        if kind == "liquidation":
            role, reason, ekind = "exit", "liquidation", "liquidation"
        elif kind == "stop":
            role, reason, ekind = "stop", "stop", "fill"
        elif kind == "target":
            role, reason, ekind = "target", "target", "fill"
        else:
            role, reason, ekind = "exit", "market", "fill"
        fill = Fill(cid, pair, role, side, float(qty), float(vw), fee, ts, reason)       # type: ignore[arg-type]
        for t in reduces:
            self._delivered.add(t["id"])
        self._finish(pair)
        return fund + [BrokerEvent(ekind, ts, pair, cid, fill, detail=detail)]            # type: ignore[arg-type]

    def _select(self, trades: list[dict], known: Decimal | None, eps: Decimal, skip_oids: Sequence[str] | frozenset = frozenset()):
        """Son kapanisin azaltan islemleri (en yeni basta), girisleri, yon. Eksikse None.

        Tek mod: sondan basa yuru; pozisyon sifirdan baslayana (girisler == azaltmalar) dek TUM azaltan islemler (stop + dis
        azaltmalar) kapanisa dahildir. Son bilinen miktar (`known`) yalniz tamamlanma alt siniridir: azaltmalar toplami bunun
        altindaysa eksik veri sayilir (None). Giris penceredeyse `known` kapanisi KISITLAMAZ (araya giren azaltma kaybolmaz)."""
        rows = sorted((t for t in trades if isinstance(t, dict)), key=lambda t: (int(_fl(t.get("time"))), int(_fl(t.get("id")))))
        if not rows:
            return None

        def sg(t: dict) -> int:
            return 1 if str(t.get("side", "")).upper() == "BUY" else -1
        d_sign = (1 if known > 0 else -1) if (known is not None and known != 0) else -sg(rows[-1])
        reduces: list[dict] = []
        entries: list[dict] = []
        r_sum, e_sum, r_all = D(0), D(0), D(0)
        balanced = False
        for t in reversed(rows):
            q = _d(t.get("qty"))
            if sg(t) == -d_sign:
                r_all += q
                if str(t.get("orderId")) in skip_oids:
                    continue                                   # kismi kar alma bacagi: ayri dolum olarak teslim edildi; girisleri tuketir
                reduces.append(t)
                r_sum += q
            else:
                if r_all == 0:
                    continue                                   # kapanistan SONRA gelen (yeni) giris: bu kapanisin parcasi degil
                entries.append(t)
                e_sum += q
                if e_sum >= r_all - eps:
                    balanced = True
                    break
        if not reduces:
            return None
        if balanced and e_sum > r_all + eps:
            return None                                        # girisler azaltmalardan fazla: kapanis tam gorunmuyor
        if known is not None and known != 0 and r_sum < abs(known) - eps:
            return None                                        # son bilinen miktar kadar azaltma yok: eksik
        if not balanced:
            if known is None or known == 0:
                return None                                    # giris gorunmuyor ve alt sinir yok: dogrulanamaz
            # giris pencere disinda: azaltmalari bilinen miktarda kes (eski kapanislari karistirma)
            acc, kept = D(0), []
            for t in reduces:
                if acc >= abs(known) - eps:
                    break
                kept.append(t)
                acc += _d(t.get("qty"))
            reduces = kept
        return reduces, entries, d_sign

    def _classify(self, symbol: str, pair: str, t: dict, hints: Sequence[str], since: datetime) -> tuple[str, str, str | None]:
        oid = str(t.get("orderId", ""))
        cid = None
        for k in ("clientOrderId", "clientId", "origClientOrderId", "newClientOrderId"):
            if t.get(k):
                cid = str(t[k])
                break
        if cid is None:
            hit = self._order_ids.get(oid)
            cid = hit[0] if hit else None
        if cid is None:
            cands = [c for c in hints if c] + list(reversed([c for c, p in self._stops.items() if p == pair])) + \
                    list(reversed(self._cancelled.get(pair, []))) + \
                    list(reversed([c for c, p in self._exit_cids.items() if p == pair]))
            for c in dict.fromkeys(cands):
                try:
                    if _cid_role(c) in ("stop", "target"):
                        r = self._rc("query_conditional", symbol, c, protective=True, attempts=1)
                    else:
                        r = self._rc("query_order", symbol, c, protective=True, attempts=1)
                except ExchangeReject:
                    continue                                    # bu aday sorgulanamadi (kesin ret): atla
                except ExchangeError:
                    raise _Retry() from None                    # belirsiz / ban / yetki: yeniden dene
                if isinstance(r, dict) and oid in (str(r.get("actualOrderId")), str(r.get("orderId"))):
                    cid = c
                    self._learn(r, pair)
                    break
        if cid is None and oid and getattr(self._rest, "query_order_by_id", None) is not None:
            try:
                r = self._rc("query_order_by_id", symbol, oid, protective=True, attempts=1)
            except ExchangeError:
                raise _Retry() from None                        # yalniz -2013 (wrapper None doner) "yok" sayilir; digerleri yeniden dene
            if isinstance(r, dict) and r.get("clientOrderId"):
                cid = str(r["clientOrderId"])
                self._learn(r, pair)
        if cid is not None:
            if cid.startswith(("autoclose-", "adl_autoclose")):
                return "liquidation", cid, None
            role = _cid_role(cid)
            if role == "stop":
                return "stop", cid, None
            if role == "target":
                return "target", cid, None
            if role == "exit":
                return "market", cid, None
        # yabanci ilan etmeden once: likidasyon/ADL emri mi? (forceOrders; sorgulanamayan likidasyon emri icin tek yol)
        if oid and getattr(self._rest, "force_orders", None) is not None:
            for typ in ("LIQUIDATION", "ADL"):
                start = max(_ms(since) - 1000, _ms(self._now() - FORCE_ORDERS_MAX_AGE) + 60_000)   # borsa siniri 7 gun
                try:
                    rows = self._rc("force_orders", symbol, start, typ, protective=True, attempts=1)
                except ExchangeReject:
                    f = f"force_orders_rejected:{pair}:{oid}"
                    if f not in self.findings:
                        self.findings.append(f)
                    continue                                    # kesin ret: bulgu ile devam (yabanci ilanina gidebilir)
                except ExchangeError:
                    raise _Retry() from None
                for fr in rows or []:
                    if isinstance(fr, dict) and str(fr.get("orderId")) == oid:
                        return "liquidation", str(fr.get("clientOrderId") or f"autoclose-{oid}"), None
        self._ctr["foreign_close"] += 1
        log.critical("foreign_close %s order=%s", pair, oid)
        return "market", cid or f"foreign-{oid}", "foreign_close"
