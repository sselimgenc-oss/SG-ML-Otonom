"""PaperBroker (03 §4): benzetimli borsa. Belirlenimli; rastgelelik, duvar saati, ag yok.

Eksik dakika kurali (P1-a, yalniz kagit motor; olcum `eksik_dakika_stop`): pozisyonun 1 dk mumu gelmeyen dakikada `_triggers_pair` calismaz; motor
(`Engine._gap15_step`) o 15 dk penceresi icin 15 dk `last` mumuyla `gap_stop_kontrol` cagirir (yalniz stop + tasfiye, hedef yok). Sinirlamalar: tetik
kaynagi mark olsa da last mumu kullanilir; pozisyon pencere icinde acildiysa aralik giris oncesini de kapsar (temkinli); dolum zamani kontrol adiminin
son dakikasidir (D - 1 dk), gercek pencere olcum kaydinda durur; aradaki funding odemeleri geri alinmaz."""
from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Literal

from trader_core.risk import liquidation_price

from ..clock import Clock
from ..config import CostModel
from ..errors import BrokerError, BrokerUncertain
from ..funding import due_funding_times, floor_funding_hour, funding_payment
from ..numeric import is_multiple, round_adverse, round_nearest
from ..types import (BrokerAccount, BrokerEvent, BrokerOrder, BrokerPosition, Fill, FundingPoint, MinuteBar,
                     OrderRequest, OrderResult, Role, Side, SymbolRules, require_utc)

_COUNTER_KEYS = ("mark_fallbacks", "minute_gaps", "funding_missing", "rejects", "duplicates", "anomalies")
_SNAP_VERSION = 1


# --------------------------------------------------------------------------- FaultPlan (03 §6)
@dataclass
class FaultRule:
    method: Literal["market_order", "place_stop", "place_target", "cancel", "query"]
    nth: int
    effect: Literal["unknown_executed", "unknown_not_executed", "rejected", "raise_uncertain"]
    reason: str | None = None


@dataclass
class FaultPlan:
    rules: list[FaultRule] = field(default_factory=list)


@dataclass(frozen=True)
class PaperConfig:
    cost: CostModel
    mmr: float
    wallet_start: float = 1000.0
    funding_max_wait_s: float = 900.0   # funding noktasi gelmezse imlec en fazla bu kadar bekler, sonra funding_missing
    mmr_fn: Callable[[str], float] | None = None   # cift -> sinif MMR'i (giris kapisiyla ayni kaynak); None: tek `mmr`


# --------------------------------------------------------------------------- ic kayitlar
@dataclass
class _Pos:
    side: Side
    qty: float
    entry_price: float
    leverage: int
    margin: float
    liq_price: float
    funding_paid: float
    fee_paid_entry: float
    opened_ts: datetime


@dataclass
class _Order:
    client_id: str
    pair: str
    role: Role
    order_side: str
    qty: float
    trigger_price: float | None
    reduce_only: bool
    leverage: int | None
    status: str
    filled_qty: float
    avg_price: float | None
    created_ts: datetime
    updated_ts: datetime
    order_id: str


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    return require_utc(datetime.fromisoformat(s.replace("Z", "+00:00")))


def _sign(side: Side) -> int:
    return 1 if side == "long" else -1


def _finite_pos(x) -> bool:
    return (not isinstance(x, bool)) and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


class PaperBroker:
    is_simulated = True

    def __init__(self, cfg: PaperConfig, rules_fn: Callable[[str], SymbolRules],
                 funding_fn: Callable[[str, datetime, datetime], list[FundingPoint]],
                 clock: Clock, fault_plan: FaultPlan | None = None,
                 tick_fn: Callable[[str, datetime], float] | None = None) -> None:
        self._cfg = cfg
        self._tick_fn = tick_fn            # yalniz legacy_compat: (cift, giris ani) -> aylik tarihsel tick
        self._rules_fn = rules_fn
        self._funding_fn = funding_fn
        self._clock = clock
        self._fault = fault_plan
        self._legacy = cfg.cost.fill_model == "legacy_compat"
        self._init_state()

    def _init_state(self) -> None:
        self._wallet = float(self._cfg.wallet_start)
        self._lev: dict[str, int] = {}
        self._pos: dict[str, _Pos] = {}
        self._orders: dict[str, _Order] = {}
        self._order_seq = 0
        self._events: deque[BrokerEvent] = deque()
        self._last_funding: dict[str, datetime | None] = {}
        self._funding_paid: dict[str, set[datetime]] = {}      # cift -> odenmis funding saatleri (imlec geride tutulunca cift odeme yok)
        self._last_mark: dict[str, float] = {}
        self._last_step_ts: datetime | None = None
        self._ctr: dict[str, int] = {k: 0 for k in _COUNTER_KEYS}
        self._calls: dict[str, int] = {}
        self._live: dict[str, _Order] = {}      # status == "new" emirler (ekleme sirasi = _orders sirasi); sorgular O(canli)
        self._ord_ser: dict[str, dict] = {}     # terminal (status != "new") emirlerin serilestirme onbellegi
        self._ord_idx: dict[str, int] = {}      # emir -> olusturma sirasi (snapshot bolunmus kayitta sira korunur)
        self._ord_n = 0
        self._term_pending: list[str] = []      # terminal olmus ama bolunmus kayda (snapshot_split) yazilmamis emirler

    def _add_order(self, o: _Order) -> None:
        self._orders[o.client_id] = o
        self._live[o.client_id] = o
        self._ord_ser.pop(o.client_id, None)
        self._ord_idx[o.client_id] = self._ord_n
        self._ord_n += 1

    def _new_orders(self) -> list[_Order]:
        """status == "new" emirler, `_orders` ekleme sirasinda (tum emirleri taramadan)."""
        lv = self._live
        for c in [c for c, o in lv.items() if o.status != "new"]:
            del lv[c]
            self._term_pending.append(c)
        return list(lv.values())

    # ------------------------------------------------------------------ basit okumalar
    def counters(self) -> dict:
        return dict(self._ctr)

    def rules(self, pair: str) -> SymbolRules:
        return self._rules_fn(pair)

    def _mark_of(self, pair: str, pos: _Pos) -> float:
        return self._last_mark.get(pair, pos.entry_price)

    def _unreal(self, pair: str, pos: _Pos) -> float:
        return (self._mark_of(pair, pos) - pos.entry_price) * pos.qty * _sign(pos.side)

    def account(self) -> BrokerAccount:
        unreal = sum(self._unreal(p, pos) for p, pos in self._pos.items())
        used = sum(pos.margin for pos in self._pos.values())
        return BrokerAccount(wallet=self._wallet, unrealized=unreal, equity=self._wallet + unreal,
                             used_margin=used, available=self._wallet - used, ts=self._clock.now())

    def positions(self) -> list[BrokerPosition]:
        out = []
        for pair in sorted(self._pos):
            p = self._pos[pair]
            out.append(BrokerPosition(pair=pair, side=p.side, qty=p.qty, entry_price=p.entry_price,
                                      leverage=p.leverage, margin=p.margin, liq_price=p.liq_price,
                                      funding_paid=p.funding_paid, fee_paid_entry=p.fee_paid_entry,
                                      opened_ts=p.opened_ts, mark_price=self._mark_of(pair, p),
                                      unrealized=self._unreal(pair, p)))
        return out

    @staticmethod
    def _to_broker_order(o: _Order) -> BrokerOrder:
        return BrokerOrder(client_id=o.client_id, pair=o.pair, role=o.role, order_side=o.order_side,  # type: ignore[arg-type]
                           qty=o.qty, trigger_price=o.trigger_price, reduce_only=o.reduce_only,
                           status=o.status, filled_qty=o.filled_qty, avg_price=o.avg_price,  # type: ignore[arg-type]
                           created_ts=o.created_ts, updated_ts=o.updated_ts)

    def open_orders(self, pair: str | None = None) -> list[BrokerOrder]:
        return [self._to_broker_order(o) for o in self._new_orders()
                if pair is None or o.pair == pair]

    def prepare(self, pair: str, leverage: int) -> None:
        if isinstance(leverage, bool) or not isinstance(leverage, int) or leverage < 1:
            raise BrokerError(f"kaldirac tam sayi >= 1 olmali: {leverage!r}")
        if pair in self._pos and self._lev.get(pair) != leverage:
            raise BrokerError(f"acik pozisyonda kaldirac degistirilemez: {pair}")
        self._lev[pair] = leverage

    def query(self, pair: str, client_id: str) -> BrokerOrder | None:
        f = self._fault_for("query")
        if f is not None:
            if f.effect in ("unknown_executed", "unknown_not_executed", "raise_uncertain"):
                raise BrokerUncertain(f"query belirsiz: {client_id}")
            raise BrokerError(f.reason or "fault_injected")
        o = self._orders.get(client_id)
        if o is None or o.pair != pair:
            return None
        return self._to_broker_order(o)

    def poll(self, now: datetime) -> list[BrokerEvent]:
        evs = list(self._events)
        self._events.clear()
        evs.sort(key=lambda e: e.ts)   # kararli: ayni ts icinde ekleme (sira numarasi) sirasi
        return evs

    # ------------------------------------------------------------------ hata enjeksiyonu
    def _fault_for(self, method: str) -> FaultRule | None:
        n = self._calls.get(method, 0) + 1
        self._calls[method] = n
        if self._fault is None:
            return None
        for r in self._fault.rules:
            if r.method == method and r.nth == n:
                return r
        return None

    def _reject(self, cid: str, reason: str) -> OrderResult:
        self._ctr["rejects"] += 1
        return OrderResult(status="rejected", client_id=cid, reason=reason, ts=self._clock.now())

    def _with_fault(self, method: str, req: OrderRequest, fn: Callable[[OrderRequest], OrderResult]) -> OrderResult:
        f = self._fault_for(method)
        if f is None:
            return fn(req)
        if f.effect == "raise_uncertain":
            raise BrokerUncertain(f"{method} belirsiz: {req.client_id}")
        if f.effect == "rejected":
            return self._reject(req.client_id, f.reason or "fault_injected")
        if f.effect == "unknown_not_executed":
            return OrderResult(status="unknown", client_id=req.client_id, reason=f.reason, ts=self._clock.now())
        res = fn(req)   # unknown_executed
        if res.status == "accepted":
            return OrderResult(status="unknown", client_id=req.client_id, order_id=res.order_id,
                               reason=f.reason, ts=res.ts)
        return res

    # ------------------------------------------------------------------ emir verme
    def _new_order(self, req: OrderRequest) -> OrderResult:
        self._order_seq += 1
        oid = f"P{self._order_seq}"
        now = self._clock.now()
        self._add_order(_Order(
            client_id=req.client_id, pair=req.pair, role=req.role, order_side=req.order_side, qty=req.qty,
            trigger_price=req.trigger_price, reduce_only=bool(req.reduce_only), leverage=req.leverage,
            status="new", filled_qty=0.0, avg_price=None, created_ts=req.created_ts or now, updated_ts=now,
            order_id=oid))
        return OrderResult(status="accepted", client_id=req.client_id, order_id=oid, ts=now)

    def _dup(self, cid: str) -> OrderResult:
        self._ctr["duplicates"] += 1
        return self._reject(cid, "duplicate_client_id")

    def market_order(self, req: OrderRequest) -> OrderResult:
        return self._with_fault("market_order", req, self._market_order)

    def _market_order(self, req: OrderRequest) -> OrderResult:
        cid = req.client_id
        if cid in self._orders:
            return self._dup(cid)
        if req.role not in ("entry", "exit"):
            return self._reject(cid, "bad_role")
        if req.order_side not in ("buy", "sell"):
            return self._reject(cid, "bad_side")
        if not _finite_pos(req.qty):
            return self._reject(cid, "qty")
        rules = self._rules_fn(req.pair)
        if not is_multiple(req.qty, rules.step):
            return self._reject(cid, "step")
        if req.qty > rules.max_qty:
            return self._reject(cid, "max_qty")
        pos = self._pos.get(req.pair)
        if req.role == "entry":
            lev = self._lev.get(req.pair)
            if lev is None:
                return self._reject(cid, "not_prepared")
            if req.leverage != lev:
                return self._reject(cid, "leverage_mismatch")
            if pos is not None:
                return self._reject(cid, "position_exists")
        else:
            if pos is None:
                return self._reject(cid, "no_position")
            want = "sell" if pos.side == "long" else "buy"
            if req.order_side != want:
                return self._reject(cid, "wrong_side")
            if req.qty > pos.qty:
                return self._reject(cid, "reduce_only_exceeds")
        return self._new_order(req)

    def place_stop(self, req: OrderRequest) -> OrderResult:
        return self._with_fault("place_stop", req, lambda r: self._place_protective(r, "stop"))

    def place_target(self, req: OrderRequest) -> OrderResult:
        return self._with_fault("place_target", req, lambda r: self._place_protective(r, "target"))

    def _place_protective(self, req: OrderRequest, role: str) -> OrderResult:
        cid = req.client_id
        if cid in self._orders:
            return self._dup(cid)
        if req.role != role:
            return self._reject(cid, "bad_role")
        pos = self._pos.get(req.pair)
        if pos is None:
            return self._reject(cid, "no_position")
        if req.reduce_only is not True:
            return self._reject(cid, "not_reduce_only")
        want = "sell" if pos.side == "long" else "buy"
        if req.order_side != want:
            return self._reject(cid, "wrong_side")
        if not _finite_pos(req.qty):
            return self._reject(cid, "qty")
        if req.qty > pos.qty:
            return self._reject(cid, "reduce_only_exceeds")
        trig = req.trigger_price
        if not _finite_pos(trig):
            return self._reject(cid, "trigger_price")
        if not self._legacy and not is_multiple(trig, self._rules_fn(req.pair).tick):
            return self._reject(cid, "tick")
        lm = self._last_mark.get(req.pair)
        if lm is not None:
            if role == "stop":
                bad = trig >= lm if pos.side == "long" else trig <= lm
            else:
                bad = trig <= lm if pos.side == "long" else trig >= lm
            if bad:
                return self._reject(cid, "would_trigger")
        return self._new_order(req)

    def cancel(self, pair: str, client_id: str) -> None:
        f = self._fault_for("cancel")
        if f is not None:
            if f.effect == "unknown_executed":
                self._cancel(pair, client_id)
                raise BrokerUncertain(f"cancel belirsiz: {client_id}")
            if f.effect in ("unknown_not_executed", "raise_uncertain"):
                raise BrokerUncertain(f"cancel belirsiz: {client_id}")
            raise BrokerError(f.reason or "fault_injected")
        self._cancel(pair, client_id)

    def _cancel(self, pair: str, client_id: str) -> None:
        o = self._orders.get(client_id)
        if o is None or o.pair != pair or o.status != "new":
            return
        now = self._clock.now()
        o.status = "canceled"
        o.updated_ts = now
        self._events.append(BrokerEvent(kind="order_canceled", ts=now, pair=pair, client_id=client_id))

    # ------------------------------------------------------------------ adim
    def advance(self, bars: Mapping[str, MinuteBar], phase: Literal["fills", "triggers"]) -> None:
        if phase not in ("fills", "triggers"):
            raise ValueError(f"gecersiz phase: {phase!r}")
        if phase == "fills":
            if bars:
                self._last_step_ts = max(b.open_ts for b in bars.values())
            for pair in sorted(set(self._pos) | {o.pair for o in self._new_orders()}):
                if pair not in bars:
                    self._ctr["minute_gaps"] += 1
            for pair in sorted(bars):
                self._fills_pair(pair, bars[pair])
        else:
            for pair in sorted(bars):
                self._triggers_pair(pair, bars[pair])

    # --- fills
    def _fills_pair(self, pair: str, bar: MinuteBar) -> None:
        self._funding_step(pair, bar)
        orders = [x for x in self._new_orders() if x.pair == pair and x.role in ("entry", "exit")]
        # kural yalniz bekleyen emir varken okunur: kurali olmayan istege bagli cift (or. borsada not_trading) mum tasisa da
        # motoru dusurmez (emir yoksa kurala gerek yok)
        rules = self._rules_fn(pair) if orders else None
        for o in orders:
            if o.role == "entry":
                self._fill_entry(o, bar, rules)
            else:
                self._fill_exit(o, bar, rules)
        if bar.mark_c is not None:
            self._last_mark[pair] = bar.mark_c
        else:
            self._ctr["mark_fallbacks"] += 1
            self._last_mark[pair] = bar.last_c

    def _funding_step(self, pair: str, bar: MinuteBar) -> None:
        ts = bar.open_ts
        pos = self._pos.get(pair)
        last = self._last_funding.get(pair)
        if pos is None or last is None:
            self._last_funding[pair] = ts
            return
        grid = due_funding_times(last, ts)                     # 8s izgara: noktasi eksikse bekle/uyar (eski davranis)
        if not grid and floor_funding_hour(ts) <= last:        # arada saat siniri yok: odenecek funding olamaz
            self._last_funding[pair] = ts
            return
        pts = self._funding_fn(pair, last, ts)
        by_ts: dict[datetime, FundingPoint] = {}
        for p in pts or ():
            by_ts.setdefault(floor_funding_hour(p.ts), p)      # kaydin kendi zamani; ham fundingTime saat basini birkac ms gecebilir
        # Aralik-bagimsiz: izgara disi (4s/1s) kayitlar da (last, ts] icinde kendi zamaninda bir kez odenir
        due = sorted(set(grid) | {t for t in by_ts if last < t <= ts})
        paid = self._funding_paid.setdefault(pair, set())
        todo = []
        hold_at: datetime | None = None                        # son odenen/atlanan nokta; imlec buraya kadar ilerler
        held = False
        for t in due:
            if pos.opened_ts >= t:
                hold_at = t
                continue
            if t in paid:                                      # bu saat zaten odendi (imlec saat basinda bekletilirken yeniden sorgu)
                hold_at = t
                continue
            p = by_ts.get(t)
            if p is None:
                if (ts - t).total_seconds() < self._cfg.funding_max_wait_s:
                    held = True                                # nokta henuz yok: imleci tut (sinirli bekleme)
                    break
                self._ctr["funding_missing"] += 1              # sinir asildi: uyar ve ilerle (sonsuz bloklama yok)
                hold_at = t
                continue
            if p.mark is not None:
                mark = p.mark
            else:
                self._ctr["mark_fallbacks"] += 1
                mark = bar.mark_o if bar.mark_o is not None else bar.last_o
            try:
                pay = funding_payment(pos.side, pos.qty, mark, p.rate)
            except ValueError:
                self._ctr["funding_missing"] += 1
                raise
            todo.append((t, p, mark, pay))
            hold_at = t
        for t, p, mark, pay in todo:
            self._wallet -= pay
            pos.funding_paid += pay
            paid.add(t)
            self._events.append(BrokerEvent(kind="funding", ts=t, pair=pair, funding_paid=pay,
                                            rate=p.rate, mark=mark))
        cur = hold_at if held and hold_at is not None else (last if held else ts)
        h0 = floor_funding_hour(ts)
        if not held and (ts - h0).total_seconds() < self._cfg.funding_max_wait_s:
            # saat basini birkac ms/sn gecen kayit (4s/1s semboller) henuz depoda olmayabilir: imlec saat basinin hemen
            # oncesinde bekler, bekleme siniri dolana dek yeniden sorulur (odenen saatler `paid` ile tekrar odenmez)
            cur = max(last, min(cur, h0 - timedelta(milliseconds=1)))
        self._last_funding[pair] = cur
        for t in [t for t in paid if t < h0 - timedelta(hours=3)]:
            paid.discard(t)
        return

    def _slipped(self, base: float, order_side: str, slip_bps: float, tick: float,
                 pair: str | None = None, opened_ts: datetime | None = None) -> float:
        if self._legacy:
            # referans: tarihsel tick'e en yakin yuvarlama; pozisyonun tick'i GIRIS ayininkidir ve omur boyu sabit
            if self._tick_fn is None or pair is None or opened_ts is None:
                return base
            return round_nearest(base, self._tick_fn(pair, opened_ts))
        d = Decimal(slip_bps) / Decimal(10000)
        f = Decimal(1) + d if order_side == "buy" else Decimal(1) - d
        raw = float(Decimal(repr(float(base))) * f)
        return round_adverse(raw, order_side, tick)   # type: ignore[arg-type]

    def _reject_at_fill(self, o: _Order, ts: datetime, reason: str) -> None:
        o.status = "rejected"
        o.updated_ts = ts
        self._ctr["rejects"] += 1
        self._events.append(BrokerEvent(kind="order_rejected", ts=ts, pair=o.pair, client_id=o.client_id,
                                        detail=reason))

    def _cfg_pair(self, pair: str) -> PaperConfig:
        """Cift icin yapilandirma: `mmr_fn` varsa MMR sinifa gore (giris kapisiyla ayni kaynak), yoksa tek `mmr`."""
        fn = self._cfg.mmr_fn
        return self._cfg if fn is None else replace(self._cfg, mmr=float(fn(pair)))

    def _fill_entry(self, o: _Order, bar: MinuteBar, rules: SymbolRules) -> None:
        ts = bar.open_ts
        cost = self._cfg.cost
        if o.pair in self._pos:
            return self._reject_at_fill(o, ts, "position_exists")
        fp = self._slipped(bar.last_o, o.order_side, cost.slip_entry_bps, rules.tick, o.pair, ts)
        notional = o.qty * fp
        if notional < rules.min_notional:
            return self._reject_at_fill(o, ts, "min_notional")
        lev = o.leverage if o.leverage is not None else self._lev[o.pair]
        margin = notional / lev
        fee = notional * cost.taker_fee
        used = sum(p.margin for p in self._pos.values())
        if margin + fee > self._wallet - used:
            return self._reject_at_fill(o, ts, "insufficient_margin")
        side: Side = "long" if o.order_side == "buy" else "short"
        self._wallet -= fee
        self._pos[o.pair] = _Pos(side=side, qty=o.qty, entry_price=fp, leverage=lev, margin=margin,
                                 liq_price=liquidation_price(fp, side, lev, self._cfg_pair(o.pair).mmr),
                                 funding_paid=0.0, fee_paid_entry=fee, opened_ts=ts)
        last = self._last_funding.get(o.pair)
        self._last_funding[o.pair] = ts if last is None else max(last, ts)
        o.status, o.filled_qty, o.avg_price, o.updated_ts = "filled", o.qty, fp, ts
        self._events.append(BrokerEvent(kind="fill", ts=ts, pair=o.pair, client_id=o.client_id, fill=Fill(
            client_id=o.client_id, pair=o.pair, role=o.role, order_side=o.order_side, qty=o.qty,  # type: ignore[arg-type]
            price=fp, fee=fee, ts=ts, reason="market", ref_price=bar.last_o)))

    def _fill_exit(self, o: _Order, bar: MinuteBar, rules: SymbolRules) -> None:
        ts = bar.open_ts
        pos = self._pos.get(o.pair)
        if pos is None:
            return self._reject_at_fill(o, ts, "no_position")
        qty = min(o.qty, pos.qty)
        fp = self._slipped(bar.last_o, o.order_side, self._cfg.cost.slip_exit_bps, rules.tick, o.pair, pos.opened_ts)
        fee = qty * fp * self._cfg.cost.taker_fee
        self._close(o, pos, qty, fp, fee, ts, "market", "fill", None, ref_price=bar.last_o)

    def _close(self, o: _Order, pos: _Pos, qty: float, price: float, fee: float, ts: datetime,
               reason: str, kind: str, detail: str | None, ref_price: float | None = None) -> None:
        pair = o.pair
        gross = qty * (price - pos.entry_price) * _sign(pos.side)
        self._wallet += gross - fee
        full = qty >= pos.qty
        if full:
            del self._pos[pair]
        else:
            pos.margin = pos.margin * ((pos.qty - qty) / pos.qty)
            pos.qty = pos.qty - qty
        o.status, o.filled_qty, o.avg_price, o.updated_ts = "filled", qty, price, ts
        self._events.append(BrokerEvent(kind=kind, ts=ts, pair=pair, client_id=o.client_id, detail=detail,  # type: ignore[arg-type]
                                        fill=Fill(client_id=o.client_id, pair=pair, role=o.role,
                                                  order_side=o.order_side, qty=qty, price=price, fee=fee,  # type: ignore[arg-type]
                                                  ts=ts, reason=reason, ref_price=ref_price)))  # type: ignore[arg-type]
        if full:
            for x in self._new_orders():
                if x.pair == pair and x.status == "new" and x.reduce_only and x.role in ("stop", "target"):
                    x.status, x.updated_ts = "canceled", ts
                    self._events.append(BrokerEvent(kind="order_canceled", ts=ts, pair=pair,
                                                    client_id=x.client_id))

    # --- triggers
    def _triggers_pair(self, pair: str, bar: MinuteBar) -> None:
        pos = self._pos.get(pair)
        if pos is None:
            return
        stops = [o for o in self._new_orders() if o.pair == pair and o.role == "stop"]
        targets = [o for o in self._new_orders() if o.pair == pair and o.role == "target"]
        use_mark = self._cfg.cost.trigger_source == "mark"
        if use_mark and None not in (bar.mark_o, bar.mark_h, bar.mark_l):
            op, hi, lo = bar.mark_o, bar.mark_h, bar.mark_l
        else:
            if use_mark:
                self._ctr["mark_fallbacks"] += 1
            op, hi, lo = bar.last_o, bar.last_h, bar.last_l
        ts = bar.open_ts
        rules = self._rules_fn(pair)
        cost = self._cfg.cost
        long = pos.side == "long"
        liq = pos.liq_price
        # en siki duran stop: long -> en yuksek, short -> en dusuk
        stop = None
        if stops:
            stop = max(stops, key=lambda x: x.trigger_price) if long else min(stops, key=lambda x: x.trigger_price)  # type: ignore[arg-type,return-value]
        stop_px = stop.trigger_price if stop is not None else None
        liq_gap = op <= liq if long else op >= liq
        liq_touch = lo <= liq if long else hi >= liq
        stop_hit = stop_px is not None and (lo <= stop_px if long else hi >= stop_px)
        if liq_gap:
            return self._liquidate(pair, pos, stops, stop_px, ts)
        if stop_hit:
            beyond = stop_px <= liq if long else stop_px >= liq   # type: ignore[operator]
            if liq_touch and beyond:
                return self._liquidate(pair, pos, stops, stop_px, ts)
            gap = op <= stop_px if long else op >= stop_px   # type: ignore[operator]
            base = bar.last_o if gap else stop_px
            fp = self._slipped(base, stop.order_side, cost.slip_stop_bps, rules.tick, pair, pos.opened_ts)   # type: ignore[union-attr,arg-type]
            qty = min(stop.qty, pos.qty)   # type: ignore[union-attr]
            self._close(stop, pos, qty, fp, qty * fp * cost.taker_fee, ts, "stop", "fill", None)   # type: ignore[arg-type]
            return
        if liq_touch:
            return self._liquidate(pair, pos, stops, stop_px, ts)
        hit = [t for t in targets if (hi >= t.trigger_price if long else lo <= t.trigger_price)]   # type: ignore[operator]
        if hit:
            t = min(hit, key=lambda x: x.trigger_price) if long else max(hit, key=lambda x: x.trigger_price)   # type: ignore[arg-type,return-value]
            gap = op >= t.trigger_price if long else op <= t.trigger_price   # type: ignore[operator]
            base = bar.last_o if gap else t.trigger_price
            # 24.11 (muhafazakar): tetik mark ile ama dolum last fiyat yolunu asamaz: long min(hedef, last_high), short max(hedef, last_low)
            base = min(base, bar.last_h) if long else max(base, bar.last_l)
            fp = self._slipped(base, t.order_side, cost.slip_exit_bps, rules.tick, pair, pos.opened_ts)   # type: ignore[arg-type]
            qty = min(t.qty, pos.qty)
            self._close(t, pos, qty, fp, qty * fp * cost.taker_fee, ts, "target", "fill", None)
        if bar.mark_c is not None:
            self._last_mark[pair] = bar.mark_c

    def stop_fiyati(self, pair: str) -> float | None:
        """Salt okunur: pozisyonun en siki `new` stop emrinin tetik fiyati (long: en yuksek, short: en dusuk); pozisyon/stop yoksa None."""
        pos = self._pos.get(pair)
        if pos is None:
            return None
        stops = [o for o in self._new_orders() if o.pair == pair and o.role == "stop" and o.trigger_price is not None]
        if not stops:
            return None
        s = max(stops, key=lambda x: x.trigger_price) if pos.side == "long" else min(stops, key=lambda x: x.trigger_price)   # type: ignore[arg-type,return-value]
        return float(s.trigger_price)   # type: ignore[arg-type]

    def gap_stop_kontrol(self, pair: str, o: float, h: float, l: float, stop_px: float, *, ts: datetime, acilis_gecerli: bool) -> str | None:
        """Eksik 1 dk mumlar icin temkinli kontrol (yalniz kagit; motor `_gap15_step`): 15 dk `last` mumu (o,h,l) ile YALNIZ stop + tasfiye
        degerlendirilir (hedef DEGIL: eksik veride kazanc yazilmaz). Doner "stop" | "tasfiye" | None. Mantik `_triggers_pair` ile ayni sira."""
        pos = self._pos.get(pair)
        if pos is None:
            return None
        stops = [x for x in self._new_orders() if x.pair == pair and x.role == "stop"]
        if not stops:
            return None
        long = pos.side == "long"
        liq = pos.liq_price
        stop = max(stops, key=lambda x: x.trigger_price) if long else min(stops, key=lambda x: x.trigger_price)   # type: ignore[arg-type,return-value]
        hit = l <= stop_px if long else h >= stop_px
        touch = l <= liq if long else h >= liq
        if acilis_gecerli and (o <= liq if long else o >= liq):
            self._liquidate(pair, pos, stops, stop_px, ts)
            return "tasfiye"
        if hit:
            beyond = stop_px <= liq if long else stop_px >= liq
            if touch and beyond:
                self._liquidate(pair, pos, stops, stop_px, ts)
                return "tasfiye"
            gap = acilis_gecerli and (o <= stop_px if long else o >= stop_px)
            base = o if gap else stop_px
            rules = self._rules_fn(pair)
            fp = self._slipped(base, stop.order_side, self._cfg.cost.slip_stop_bps, rules.tick, pair, pos.opened_ts)
            qty = min(stop.qty, pos.qty)
            self._close(stop, pos, qty, fp, qty * fp * self._cfg.cost.taker_fee, ts, "stop", "fill", None)
            return "stop"
        if touch:
            self._liquidate(pair, pos, stops, stop_px, ts)
            return "tasfiye"
        return None

    def _liquidate(self, pair: str, pos: _Pos, stops: list[_Order], stop_px: float | None, ts: datetime) -> None:
        long = pos.side == "long"
        detail = None
        if stop_px is not None and (stop_px <= pos.liq_price if long else stop_px >= pos.liq_price):
            detail = "liquidation_before_stop"
            self._ctr["anomalies"] += 1
        fee = pos.qty * pos.entry_price * self._cfg_pair(pair).mmr
        cid = f"LIQ-{pair}-{_iso(ts)}"
        o = _Order(client_id=cid, pair=pair, role="exit", order_side="sell" if long else "buy", qty=pos.qty,
                   trigger_price=None, reduce_only=True, leverage=pos.leverage, status="new", filled_qty=0.0,
                   avg_price=None, created_ts=ts, updated_ts=ts, order_id="LIQ")
        self._add_order(o)
        self._close(o, pos, pos.qty, pos.liq_price, fee, ts, "liquidation", "liquidation", detail)

    # ------------------------------------------------------------------ snapshot / restore
    @staticmethod
    def _ser_event(e: BrokerEvent) -> dict:
        f = e.fill
        return {"kind": e.kind, "ts": _iso(e.ts), "pair": e.pair, "client_id": e.client_id,
                "fill": None if f is None else {
                    "client_id": f.client_id, "pair": f.pair, "role": f.role, "order_side": f.order_side,
                    "qty": f.qty, "price": f.price, "fee": f.fee, "ts": _iso(f.ts), "reason": f.reason,
                    "ref_price": f.ref_price},
                "funding_paid": e.funding_paid, "rate": e.rate, "mark": e.mark, "detail": e.detail}

    @staticmethod
    def _de_event(d: dict) -> BrokerEvent:
        f = d["fill"]
        fill = None if f is None else Fill(client_id=f["client_id"], pair=f["pair"], role=f["role"],
                                           order_side=f["order_side"], qty=f["qty"], price=f["price"],
                                           fee=f["fee"], ts=_dt(f["ts"]), reason=f["reason"],
                                           ref_price=f.get("ref_price"))
        return BrokerEvent(kind=d["kind"], ts=_dt(d["ts"]), pair=d["pair"], client_id=d["client_id"], fill=fill,
                           funding_paid=d["funding_paid"], rate=d["rate"], mark=d["mark"], detail=d["detail"])

    def _ser_order(self, c: str, o: _Order) -> dict:
        # Terminal emir (filled/canceled/rejected) bir daha degismez: serilestirme onbellekli.
        d = self._ord_ser.get(c) if o.status != "new" else None
        if d is None:
            d = {"client_id": o.client_id, "pair": o.pair, "role": o.role, "order_side": o.order_side,
                 "qty": o.qty, "trigger_price": o.trigger_price, "reduce_only": o.reduce_only,
                 "leverage": o.leverage, "status": o.status, "filled_qty": o.filled_qty,
                 "avg_price": o.avg_price, "created_ts": _iso(o.created_ts),
                 "updated_ts": _iso(o.updated_ts), "order_id": o.order_id}
            if o.status != "new":
                self._ord_ser[c] = d
        return dict(d)

    def snapshot_split(self) -> tuple[dict, dict[str, dict]]:
        """Bolunmus snapshot: (govde, henuz yazilmamis terminal emirler {cid: {"i": sira, "o": emir}}).

        Govde `snapshot()` ile ayni, ama `orders` yalniz status == "new" emirleri tasir; `order_idx` canli emirlerin
        olusturma sirasini verir. Terminal emirler degismez: bir kez yazilir (cagiran `mark_persisted` der), her adimda
        tum emir gecmisi yeniden serilestirilmez (adim maliyeti O(canli), O(tum emir) degil)."""
        live = self._new_orders()
        snap = self.snapshot(_orders=False)
        snap["orders"] = {o.client_id: self._ser_order(o.client_id, o) for o in live}
        snap["order_idx"] = {o.client_id: self._ord_idx[o.client_id] for o in live}
        done = {c: {"i": self._ord_idx[c], "o": self._ser_order(c, self._orders[c])} for c in self._term_pending}
        return snap, done

    def mark_persisted(self, cids) -> None:
        gone = set(cids)
        self._term_pending = [c for c in self._term_pending if c not in gone]

    def snapshot(self, _orders: bool = True) -> dict:
        return {
            "version": _SNAP_VERSION,
            "wallet": self._wallet,
            "leverage": dict(self._lev),
            "positions": {p: {"side": x.side, "qty": x.qty, "entry_price": x.entry_price, "leverage": x.leverage,
                              "margin": x.margin, "liq_price": x.liq_price, "funding_paid": x.funding_paid,
                              "fee_paid_entry": x.fee_paid_entry, "opened_ts": _iso(x.opened_ts)}
                          for p, x in self._pos.items()},
            "orders": {c: self._ser_order(c, o) for c, o in self._orders.items()} if _orders else {},
            "order_seq": self._order_seq,
            "events": [self._ser_event(e) for e in self._events],
            "last_funding_ts": {p: _iso(t) for p, t in self._last_funding.items()},
            "funding_paid_ts": {p: sorted(_iso(t) for t in v) for p, v in self._funding_paid.items() if v},
            "last_mark": dict(self._last_mark),
            "last_step_ts": _iso(self._last_step_ts),
            "counters": dict(self._ctr),
            "fault_calls": dict(self._calls),
        }

    def restore(self, snap: dict, persisted=frozenset()) -> None:
        try:
            if snap["version"] != _SNAP_VERSION:
                raise BrokerError(f"snapshot surumu desteklenmiyor: {snap['version']!r}")
            wallet = float(snap["wallet"])
            lev = {str(k): int(v) for k, v in snap["leverage"].items()}
            pos = {p: _Pos(side=d["side"], qty=float(d["qty"]), entry_price=float(d["entry_price"]),
                           leverage=int(d["leverage"]), margin=float(d["margin"]), liq_price=float(d["liq_price"]),
                           funding_paid=float(d["funding_paid"]), fee_paid_entry=float(d["fee_paid_entry"]),
                           opened_ts=_dt(d["opened_ts"])) for p, d in snap["positions"].items()}
            orders = {c: _Order(client_id=d["client_id"], pair=d["pair"], role=d["role"],
                                order_side=d["order_side"], qty=float(d["qty"]),
                                trigger_price=d["trigger_price"], reduce_only=bool(d["reduce_only"]),
                                leverage=d["leverage"], status=d["status"], filled_qty=float(d["filled_qty"]),
                                avg_price=d["avg_price"], created_ts=_dt(d["created_ts"]),
                                updated_ts=_dt(d["updated_ts"]), order_id=d["order_id"])
                      for c, d in snap["orders"].items()}
            seq = int(snap["order_seq"])
            oi = snap.get("order_idx")
            if oi is not None:                                   # bolunmus kayit: olusturma sirasini geri kur
                orders = dict(sorted(orders.items(), key=lambda kv: oi[kv[0]]))
            events = deque(self._de_event(d) for d in snap["events"])
            lf = {p: _dt(t) for p, t in snap["last_funding_ts"].items()}
            lm = {p: float(v) for p, v in snap["last_mark"].items()}
            fpaid = {p: {_dt(t) for t in v} for p, v in snap.get("funding_paid_ts", {}).items()}
            lst = _dt(snap["last_step_ts"])
            ctr = {k: int(snap["counters"][k]) for k in _COUNTER_KEYS}
            calls = {str(k): int(v) for k, v in snap["fault_calls"].items()}
        except BrokerError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise BrokerError(f"gecersiz snapshot: {e!r}") from e
        self._wallet, self._lev, self._pos, self._orders, self._order_seq = wallet, lev, pos, orders, seq
        self._events, self._last_funding, self._last_mark = events, lf, lm
        self._funding_paid = fpaid
        self._last_step_ts, self._ctr, self._calls = lst, ctr, calls
        self._live = {c: o for c, o in orders.items() if o.status == "new"}
        self._ord_ser = {}
        self._ord_idx = {c: i for i, c in enumerate(orders)}
        self._ord_n = len(orders)
        self._term_pending = [c for c, o in orders.items() if o.status != "new" and c not in persisted]
