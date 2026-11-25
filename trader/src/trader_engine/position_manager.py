"""Pozisyon yonetimi (04 §5): cikis karari (saf), dolum/cikis uygulamasi, MFE/MAE, ledger yukleri."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

import numpy as np

from trader_core import exit_modes as _xm
from trader_core import ledger as _ledger
from trader_core import risk, signals

from .bars import arm_floor_tf, floor_tf
from .numeric import round_tight
from .state import iso_z
from .types import BrokerEvent, Fill, MinuteBar, Position

EPS = 1e-9
_REASONS = ("stop", "target", "trail_stop", "regime_flip", "time_stop", "manual", "force_exit", "liquidation", "other")


@dataclass(frozen=True)
class ExitContext:
    bar_close_ts: datetime
    highs: np.ndarray
    lows: np.ndarray
    atrs: np.ndarray
    regime_last: str | None
    last_close: float
    n_closed: int
    rule_exit: bool = False       # 24.11: kutuphane kural cikisi (EXIT_RULE) bu kapanista saglandi


@dataclass(frozen=True)
class ExitDecision:
    kind: Literal["none", "exit", "stop_update"]
    reason: str | None = None
    new_stop: float | None = None
    planned_exit: float | None = None


@dataclass(frozen=True)
class ClosedTrade:
    trade_id: int
    exit_ts: datetime
    exit_price: float
    exit_reason: str
    planned_exit: float | None
    fee_exit: float
    funding_paid: float
    max_favorable_price: float | None
    max_adverse_price: float | None
    excursion_tf: str | None
    leg_exit_price: float | None = None        # kismi cikis sonrasi: SON bacagin dolum fiyati (yalniz slippage_exit icin)


_NONE = ExitDecision("none", None, None, None)
_FORCE = ExitDecision("exit", "force_exit", None, None)


def _fin(x) -> bool:
    return x is not None and isinstance(x, (int, float, np.floating, np.integer)) and math.isfinite(float(x))


def exit_mode_of(setup: str | None) -> str | None:
    """Kurulumun cikis kipi (`trail` | `target`) ya da None (bilinmeyen). Kurulum adina degil kipe bakilir (WP-12a)."""
    from .strategies import arms as _arms          # gecikmeli: strategies -> base -> position_manager dongusunu onler
    return _arms.exit_mode(setup)


def trail_stop_value(pos: Position, ctx: ExitContext) -> tuple[float, bool]:
    highs, lows, atrs = ctx.highs, ctx.lows, ctx.atrs
    if exit_mode_of(pos.setup) != "trail" or len(highs) == 0:
        return float(pos.initial_stop), False
    path = signals.trail_stop_path(pos.side, pos.entry_price, pos.initial_stop, highs, lows, atrs, pos.trail_atr)
    stop = float(path.iloc[-1])
    return stop, stop != pos.initial_stop


def evaluate_exit(pos: Position, ctx: ExitContext | None) -> ExitDecision:
    if ctx is None:
        return _FORCE
    mode = exit_mode_of(pos.setup)
    if mode is None:                                # bilinmeyen kurulum: zorla kapat
        return _FORCE
    if (not pos.setup or not _fin(pos.initial_stop) or pos.entry_bar_open is None
            or (mode == "trail" and (not _fin(pos.entry_price) or not _fin(pos.trail_atr)))):
        return _FORCE
    if ctx.n_closed == 0:
        return _NONE
    if mode == "target":                            # R1 yolu: hedef + zaman durdurma (B1, F1 de burada)
        if _fin(pos.planned_target):
            for h, l in zip(ctx.highs, ctx.lows):
                if signals.target_reached(pos.side, pos.planned_target, h, l):
                    return ExitDecision("exit", "target", None, float(pos.planned_target))
        if ctx.rule_exit:                           # 24.11: kutuphane kural cikisi (neden `other`; defter CHECK kisiti)
            return ExitDecision("exit", "other", None, None)
        from .strategies import arms as _arms
        if signals.time_stop_due(ctx.n_closed, _arms.time_stop_of(pos.setup, getattr(pos, "trigger_tf", None))):
            return ExitDecision("exit", "time_stop", None, None)
        return _NONE
    # trail (T1 yolu): rejim cikisi + iz suren stop (TF1, S1, H2 de burada)
    if signals.regime_flip_exit(pos.side, ctx.regime_last):
        return ExitDecision("exit", "regime_flip", None, None)
    stop, armed = trail_stop_value(pos, ctx)
    if armed:
        crossed = stop >= ctx.last_close if pos.side == "long" else stop <= ctx.last_close
        if crossed:
            return ExitDecision("exit", "trail_stop", None, None)
    tighter = stop > pos.current_stop + EPS if pos.side == "long" else stop < pos.current_stop - EPS
    if tighter:
        return ExitDecision("stop_update", None, stop, None)
    return _NONE


# ---------------------------------------------------------------------- cikis kipleri (docs/cikis-kipleri-spec.md)
def apply_exit_modes(pos: Position, ctx: ExitContext | None, dec: ExitDecision, modes) -> ExitDecision:
    """Basa-bas kipi: karar zaten cikis ise dokunmaz; aksi halde en iyi uc `be_trigger_r` R'ye ulastiysa stop girise (+maliyet)
    sikilastirilir (iz suren stopla siki olan kazanir). Kip yoksa/kapaliysa `dec` ayni nesne doner (bayt bayt ayni davranis)."""
    if modes is None or not modes.breakeven or ctx is None or dec.kind == "exit" or ctx.n_closed == 0:
        return dec
    if not (_fin(pos.entry_price) and _fin(pos.initial_stop)):
        return dec
    best = _xm.best_extreme(pos.side, ctx.highs, ctx.lows)
    be = _xm.be_stop(pos.side, float(pos.entry_price), float(pos.initial_stop), best, modes)
    if be is None:
        return dec
    cur = dec.new_stop if (dec.kind == "stop_update" and dec.new_stop is not None) else pos.current_stop
    if _xm.tighter(pos.side, be, cur):
        return ExitDecision("stop_update", None, be, None)
    return dec


def partial_due(pos: Position, ctx: ExitContext | None, modes) -> bool:
    """Kismi kar alma tetigi (bir kez; cagiran `partial:<trade>` durumunu denetler)."""
    if modes is None or not modes.partial or ctx is None or ctx.n_closed == 0:
        return False
    if not (_fin(pos.entry_price) and _fin(pos.initial_stop)):
        return False
    best = _xm.best_extreme(pos.side, ctx.highs, ctx.lows)
    return _xm.partial_due(pos.side, float(pos.entry_price), float(pos.initial_stop), best, modes)


# ---------------------------------------------------------------------- MFE / MAE
def update_excursion(pos: Position, bar: MinuteBar) -> Position:
    mfe, mae = pos.mfe_price, pos.mae_price
    if pos.side == "long":
        mfe = bar.last_h if mfe is None else max(mfe, bar.last_h)
        mae = bar.last_l if mae is None else min(mae, bar.last_l)
    else:
        mfe = bar.last_l if mfe is None else min(mfe, bar.last_l)
        mae = bar.last_h if mae is None else max(mae, bar.last_h)
    return replace(pos, mfe_price=mfe, mae_price=mae)


def apply_entry_fill(pos: Position, fill: Fill, bar: MinuteBar | None, now: datetime) -> Position:
    p = replace(pos, status="open", entry_ts=fill.ts, entry_price=fill.price, qty=fill.qty, fee_entry=fill.fee,
                entry_bar_open=(arm_floor_tf if pos.trigger_tf == "1d" else floor_tf)(fill.ts, pos.trigger_tf), mfe_price=fill.price, mae_price=fill.price)
    if bar is not None:
        p = update_excursion(p, bar)
    return p


def fill_risk_violation(pos: Position, equity_at_decision: float, tick: float | None = None) -> str | None:
    """Dolum sonrasi dogrulama (§5.2). Ihlal kodu ya da None."""
    fill = pos.entry_price
    stop = pos.initial_stop
    if tick:
        stop = round_tight(stop, pos.side, tick)
    if pos.side == "long" and not stop < fill:
        return "stop_wrong_side"
    if pos.side == "short" and not stop > fill:
        return "stop_wrong_side"
    loss = risk.loss_at_stop(pos.qty, fill, stop, risk.LOCKED_CFG)
    if loss > risk.LOCKED_CFG.max_trade_risk * equity_at_decision:
        return "risk_exceeded"
    return None


def apply_funding(pos: Position, event: BrokerEvent) -> Position:
    return replace(pos, funding_paid=pos.funding_paid + event.funding_paid)


def exit_reason_for_stop_fill(pos: Position) -> str:
    return "trail_stop" if pos.current_stop != pos.initial_stop else "stop"


def apply_exit_fill(pos: Position, fill: Fill, bar: MinuteBar | None, now: datetime) -> ClosedTrade:
    r = fill.reason
    planned: float | None = None
    if r == "stop":
        reason, planned = exit_reason_for_stop_fill(pos), pos.current_stop
    elif r == "target":
        reason, planned = "target", pos.planned_target
    elif r == "liquidation":
        reason = "liquidation"
    else:
        reason = pos.exit_reason if pos.exit_reason in _REASONS else "other"
        if reason == "target":
            planned = pos.planned_target
    p = update_excursion(pos, bar) if bar is not None else pos
    entry, ex = pos.entry_price, fill.price
    pts = [x for x in (entry, ex) if x is not None]
    if pos.side == "long":
        mfp = max([p.mfe_price] * (p.mfe_price is not None) + pts)
        mapr = min([p.mae_price] * (p.mae_price is not None) + pts)
    else:
        mfp = min([p.mfe_price] * (p.mfe_price is not None) + pts)
        mapr = max([p.mae_price] * (p.mae_price is not None) + pts)
    tf: str | None = "1m" if (bar is None or bar.step_s == 60) else "15m"
    if not (_fin(mfp) and _fin(mapr) and mfp > 0 and mapr > 0):
        mfp = mapr = tf = None
    return ClosedTrade(trade_id=pos.trade_id, exit_ts=fill.ts, exit_price=fill.price, exit_reason=reason,
                       planned_exit=planned, fee_exit=fill.fee, funding_paid=pos.funding_paid,
                       max_favorable_price=mfp, max_adverse_price=mapr, excursion_tf=tf)


def close_position(pos: Position, closed: ClosedTrade) -> Position:
    return replace(pos, status="closed", closed_ts=closed.exit_ts, exit_reason=closed.exit_reason,
                   mfe_price=closed.max_favorable_price if closed.max_favorable_price is not None else pos.mfe_price,
                   mae_price=closed.max_adverse_price if closed.max_adverse_price is not None else pos.mae_price)


# ---------------------------------------------------------------------- ledger yukleri
# WP-3 (defter-ek-alanlar 3.1/3.4): olcum alanlari. Yalniz kayit; hicbir karar bunlari okumaz.
_EXEC_GROUPS = (("order_ts", "order_ack_ts"), ("order_ref_price", "order_ref_spread", "order_ref_src"),
                ("decision_price",), ("exit_regime",))


def exec_fields(role: str, meta: dict | None, fill: Fill | None, order_row) -> dict:
    """Saf yardimci: dolum icin ham olcum alanlari (datetime'lar ham). `role` 'entry' | 'exit'.
    `meta` bellekteki `exec_meta[client_id]` (yoksa None), `order_row` kalici emir satiri (yoksa None).
    Dinlenen emirle (stop/hedef) ya da likidasyonla gelen cikista hicbir emir-ani alani yoktur."""
    out: dict = {}
    if fill is not None and role == "exit" and fill.reason != "market":
        return out
    ots = (meta or {}).get("order_ts")
    if ots is None and order_row is not None:
        ots = getattr(order_row, "created_ts", None)
    if ots is not None:
        out["order_ts"] = ots
        ack = (meta or {}).get("order_ack_ts")
        if ack is not None:
            out["order_ack_ts"] = ack
    m = meta or {}
    if m.get("order_ref_price") is not None:
        out["order_ref_price"] = m["order_ref_price"]
        out["order_ref_src"] = m.get("order_ref_src", "book")
        if m.get("order_ref_spread") is not None:
            out["order_ref_spread"] = m["order_ref_spread"]
    elif fill is not None and getattr(fill, "ref_price", None) is not None:
        out["order_ref_price"] = fill.ref_price
        out["order_ref_src"] = "sim_open"
    return out


def exec_payload(raw: dict | None) -> tuple[dict, int]:
    """Ham alanlari `clean_exec_fields`'ten gecirir; JSON'a uygun (ISO-Z) yuk ve dusurulen grup sayisi dondurur.
    Hicbir girdide istisna atmaz: hata = bos yuk (olcum NULL)."""
    if not raw:
        return {}, 0
    try:
        clean = _ledger.clean_exec_fields(raw)
        dropped = sum(1 for g in _EXEC_GROUPS
                      if any(raw.get(k) is not None for k in g) and all(clean[k] is None for k in g))
        out = {}
        for k, v in clean.items():
            if v is None:
                continue
            out[k] = iso_z(v) if isinstance(v, datetime) else v
        return out, dropped
    except Exception:  # noqa: BLE001 - olcum kaydi hicbir zaman islemi durdurmaz
        return {}, 1


def build_trade_entry(pos: Position, ex: dict | None = None) -> dict:
    d = {"trade_id": pos.trade_id, "decision_id": pos.decision_id, "entry_ts": iso_z(pos.entry_ts),
         "entry_price": pos.entry_price, "qty": pos.qty, "leverage": pos.leverage, "fee_entry": pos.fee_entry}
    if ex:
        d.update(ex)
    return d


def build_trade_exit(pos: Position, closed: ClosedTrade, excursion_tf: str | None = None,
                     ex: dict | None = None) -> dict:
    mfp, mapr = closed.max_favorable_price, closed.max_adverse_price
    tf = (excursion_tf or closed.excursion_tf) if (mfp is not None and mapr is not None) else None
    if tf is None:
        mfp = mapr = None
    d = {"trade_id": closed.trade_id, "exit_ts": iso_z(closed.exit_ts), "exit_price": closed.exit_price,
         "exit_reason": closed.exit_reason, "planned_exit": closed.planned_exit, "fee_exit": closed.fee_exit,
         "funding_paid": closed.funding_paid, "max_favorable_price": mfp, "max_adverse_price": mapr,
         "excursion_tf": tf}
    if closed.leg_exit_price is not None:
        d["leg_exit_price"] = closed.leg_exit_price
    if ex:
        d.update(ex)
    return d
