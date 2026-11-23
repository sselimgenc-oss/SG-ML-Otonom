"""Donmus ortak tipler (02 §4). Yontemsiz dataclass'lar; dogrulama sinirlarda."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

Side = Literal["long", "short"]
OrderSide = Literal["buy", "sell"]
Role = Literal["entry", "stop", "target", "exit"]
Kind = Literal["last", "mark"]
ExitReason = Literal["stop", "target", "trail_stop", "regime_flip", "time_stop", "manual",
                     "force_exit", "liquidation", "other"]

_PAIR_RE = re.compile(r"^[A-Z0-9]{1,20}/[A-Z0-9]{1,20}$")
_TF_SECONDS = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}


def canon_pair(p: str) -> str:
    if not isinstance(p, str):
        raise ValueError(f"pair str olmali: {p!r}")
    s = p.strip().upper().split(":", 1)[0]
    if not _PAIR_RE.match(s):
        raise ValueError(f"gecersiz pair: {p!r}")
    return s


def pair_symbol(pair: str) -> str:
    return canon_pair(pair).replace("/", "")


def pair_stem(pair: str) -> str:
    c = canon_pair(pair)
    return c.replace("/", "_") + "_" + c.split("/")[1]


def order_side_for(side: Side, role: Role) -> OrderSide:
    if side not in ("long", "short"):
        raise ValueError(f"gecersiz side: {side!r}")
    if role == "entry":
        return "buy" if side == "long" else "sell"
    if role in ("stop", "target", "exit"):
        return "sell" if side == "long" else "buy"
    raise ValueError(f"gecersiz role: {role!r}")


def require_utc(dt: datetime, name: str = "ts") -> datetime:
    if not isinstance(dt, datetime):
        raise ValueError(f"{name} datetime olmali: {dt!r}")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{name} tz-aware olmali")
    return dt


@dataclass(frozen=True)
class Bar:
    pair: str
    kind: Kind
    tf: str
    open_ts: datetime
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0

    @property
    def close_ts(self) -> datetime:
        try:
            return self.open_ts + timedelta(seconds=_TF_SECONDS[self.tf])
        except KeyError:
            raise ValueError(f"bilinmeyen tf: {self.tf!r}") from None


@dataclass(frozen=True)
class MinuteBar:
    pair: str
    open_ts: datetime
    step_s: int
    last_o: float
    last_h: float
    last_l: float
    last_c: float
    mark_o: float | None
    mark_h: float | None
    mark_l: float | None
    mark_c: float | None
    volume: float = 0.0

    @property
    def close_ts(self) -> datetime:
        return self.open_ts + timedelta(seconds=self.step_s)


@dataclass(frozen=True)
class FundingPoint:
    pair: str
    ts: datetime
    rate: float
    mark: float | None


@dataclass(frozen=True)
class SymbolRules:
    pair: str
    symbol: str
    tick: float
    step: float
    min_qty: float
    max_qty: float
    min_notional: float


@dataclass(frozen=True)
class OrderRequest:
    client_id: str
    pair: str
    role: Role
    order_side: OrderSide
    qty: float
    trigger_price: float | None
    reduce_only: bool
    leverage: int | None
    working_type: Literal["MARK_PRICE", "CONTRACT_PRICE"] = "MARK_PRICE"
    signal_bar_close_ts: datetime | None = None
    created_ts: datetime | None = None
    partial: bool = False               # cikis kipleri (kismi kar alma): reduceOnly piyasa emri; pozisyonu KAPATMAZ, dolum olayi dogrudan emirden uretilir


@dataclass(frozen=True)
class OrderResult:
    status: Literal["filled", "accepted", "rejected", "unknown"]
    client_id: str
    order_id: str | None = None
    filled_qty: float = 0.0
    avg_price: float | None = None
    fee: float = 0.0
    reason: str | None = None
    ts: datetime | None = None


@dataclass(frozen=True)
class BrokerOrder:
    client_id: str
    pair: str
    role: Role
    order_side: OrderSide
    qty: float
    trigger_price: float | None
    reduce_only: bool
    status: Literal["new", "filled", "canceled", "rejected", "expired"]
    filled_qty: float
    avg_price: float | None
    created_ts: datetime
    updated_ts: datetime


@dataclass(frozen=True)
class Fill:
    client_id: str
    pair: str
    role: Role
    order_side: OrderSide
    qty: float
    price: float
    fee: float
    ts: datetime
    reason: Literal["market", "stop", "target", "liquidation"]
    ref_price: float | None = None      # WP-3 (defter-ek-alanlar 3.1): benzetimde kayma oncesi taban (`bar.last_o`); yoksa None


@dataclass(frozen=True)
class BrokerEvent:
    kind: Literal["fill", "funding", "liquidation", "order_canceled", "order_rejected"]
    ts: datetime
    pair: str
    client_id: str | None = None
    fill: Fill | None = None
    funding_paid: float = 0.0
    rate: float | None = None
    mark: float | None = None
    detail: str | None = None


@dataclass(frozen=True)
class BrokerPosition:
    pair: str
    side: Side
    qty: float
    entry_price: float
    leverage: int
    margin: float
    liq_price: float
    funding_paid: float
    fee_paid_entry: float
    opened_ts: datetime
    mark_price: float | None = None
    unrealized: float = 0.0


@dataclass(frozen=True)
class BrokerAccount:
    wallet: float
    unrealized: float
    equity: float
    used_margin: float
    available: float
    ts: datetime


@dataclass(frozen=True)
class Intent:
    kind: Literal["entry", "exit", "stop_update"]
    bot: str
    pair: str
    side: Side
    signal_bar_close_ts: datetime
    setup: Literal["T1", "R1"] | None
    qty: float | None
    leverage: int | None
    planned_entry: float | None
    stop_price: float | None
    target_price: float | None
    reason: str
    decision_id: int | None = None


@dataclass(frozen=True)
class Position:
    trade_id: int
    bot: str
    pair: str
    side: Side
    setup: Literal["T1", "R1"]
    status: Literal["opening", "open", "closing", "closed"]
    decision_id: int
    signal_bar_close_ts: datetime
    entry_ts: datetime | None
    entry_bar_open: datetime | None
    entry_price: float | None
    qty: float | None
    leverage: int
    initial_stop: float
    current_stop: float
    stop_seq: int
    stop_client_id: str | None
    planned_target: float | None
    trail_atr: float
    param_version_id: int
    trigger_tf: str
    risk_amount: float
    margin: float
    rh: float | None
    rl: float | None
    fee_entry: float
    funding_paid: float
    mfe_price: float | None
    mae_price: float | None
    exit_reason: str | None
    exit_client_id: str | None
    closed_ts: datetime | None
    strategy_name: str = "price_action_v1"      # 05 §13.6: giris aninda donar
    strategy_version: str = "1b.0"
