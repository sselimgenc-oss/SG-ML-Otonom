"""Canli mutabakat (11 §8, WP-B5): LiveReconciler + protect_first. Borsa gercegi ile state/defter karsilastirilir.

Degismezler: okumalardan biri basarisizsa tur HICBIR eylem yapmadan biter (`exchange_unreachable`); bilinmeyen pozisyona
KILL disinda dokunulmaz (alarm + yapiskan duraklatma); eksik stop hemen kurulur; yeni stop asla iptal edilmez (r8);
`EntryPause` tutuslari yalniz EKLENIR (`remove` bu modulde yok). `protect_first` piyasa verisi istemez (kurallar brokerdan).
B4 sozlesmesi: `run`/`protect_first` canlida dis tx ICINDE cagrilmaz; `run`'dan once `broker.poll(now)` cagrilir.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Callable, Mapping

from .clock import Clock
from .errors import DataError, StateError
from .killswitch import Killswitch
from .numeric import round_tight
from .order_manager import EXIT_RETRY_LIMIT
from .pause import EntryPause
from .position_manager import (apply_entry_fill, apply_exit_fill, apply_funding, build_trade_entry,
                               build_trade_exit, close_position, exec_fields, exec_payload, fill_risk_violation)
from .reconcile import _AUTO_CLEAR, Reconciler, ReconcileReport, apply_block_set
from .state import iso_z, parse_iso_z
from .types import BrokerEvent, BrokerOrder, BrokerPosition, Fill, OrderRequest, Position, order_side_for, pair_symbol

log = logging.getLogger("engine.reconcile_live")

LATE_FILL_WINDOW = timedelta(hours=24)
EXIT_UNRESOLVED_CRIT_S = 600.0
ENTRY_DRIFT = 0.001
_BLOCK_ORDER = ("reconcile_unknown_position", "reconcile_state_orphan", "reconcile_foreign_order",
                "reconcile_account_mode_drift", "reconcile_ledger_orphan", "stop_failed", "exit_unknown")
_LIVE_AUTO = _AUTO_CLEAR + ("reconcile_",)


class _ReadFailed(Exception):
    pass


def exchange_qty_override(state, trade_id: int) -> float | None:
    """L4 sonrasi borsadaki gercek (kucuk) miktar; state `qty` ORIJINAL giris miktari kalir. B4 stop/cikis emri miktarini
    `min(pos.qty, override)` ile kurmali (yoksa reduceOnly miktari asar). None = dis azaltma yok."""
    d = state.kv_get(f"ext_reduction:{trade_id}")
    return float(d["exch_qty"]) if isinstance(d, dict) and d.get("exch_qty") else None


def kill_close_client_id(bot: str, symbol: str, kill_at: str) -> str:
    h = hashlib.sha1(f"{bot}|kill|{symbol}|{kill_at}".encode("utf-8")).hexdigest()[:24]
    return "tr" + ("L" if bot == "learner" else "T") + "x-" + h


class LiveReconciler(Reconciler):
    def __init__(self, cfg, broker, state, ledger, orders, clock: Clock, kill: Killswitch, pause: EntryPause,
                 handle_events: Callable[[list[BrokerEvent], datetime], None] | None = None,
                 close_unopened: Callable[[Position, datetime], None] | None = None,
                 margin_types: Callable[[], Mapping[str, str]] | None = None) -> None:
        super().__init__(cfg, broker, state, ledger, orders, clock)
        self.kill = kill
        self.pause = pause
        self._handle = handle_events or self._default_handle_events
        self._close_unopened_cb = close_unopened or self._default_close_unopened
        self._margin_types = margin_types or getattr(broker, "margin_types", None)
        self.counters: Counter = Counter()

    # ================================================================== genel
    def protect_first(self) -> ReconcileReport:
        """Acilis (veri kapisindan ONCE, piyasa verisi istemez): L1, L2a/L2 bulgusu, adopt, L5 + register_position."""
        now = self.clock.now()
        acts: list[str] = []
        finds: list[str] = []
        reasons: list[str] = []
        self._l1(acts)                                    # once coz (11 §8 L1 HER ZAMAN), sonra oku
        ctx = self._read(now, full_scan=False)
        if ctx is None:
            return self._unreachable(acts)
        bpos, oo = ctx
        fatal = False
        for pair in sorted(bpos):
            sp = self._state_pos(pair)
            if sp is None or (sp.status != "opening" and sp.side != bpos[pair].side):
                if self._late_fill(pair, bpos[pair], now, acts, finds):
                    continue
                fatal |= self._unknown(pair, bpos[pair], now, acts, finds, reasons, kill_close=False)
        for pair in sorted(bpos):
            sp = self._state_pos(pair)
            if sp is None or (sp.status != "opening" and sp.side != bpos[pair].side):
                continue
            if sp.status == "opening":
                kind, sp = self._adopt_opening(sp, bpos[pair], now, acts, finds, oo.get(pair, []))
                if kind == "unknown":
                    fatal |= self._unknown(pair, bpos[pair], now, acts, finds, reasons, kill_close=False)
                if sp is None:
                    continue
            self._register(sp, bpos[pair], oo.get(pair, []))
            self._stops(sp, bpos[pair], oo.get(pair, []), now, acts, finds, reasons, protect_only=True)
        self._exit_unknown_hold(reasons)
        self._apply_blocks(reasons, acts)
        return ReconcileReport(ok=not finds, fatal=fatal, actions=tuple(acts), findings=tuple(finds))

    def _l1(self, acts: list[str]) -> None:
        """L1: HER tur kosulsuz (11 §8): pending/unknown satirlar + yolda kalmis giris/cikis (L3c) cozulur; borsa okumasindan ONCE."""
        had = bool(self.state.unresolved_orders())
        self.orders.resolve_unresolved()
        if had:
            acts.append("resolve_unresolved")

    def run(self, now: datetime) -> ReconcileReport:
        acts: list[str] = []
        finds: list[str] = []
        reasons: list[str] = []
        self._l1(acts)                                    # once coz, sonra oku (anlik goruntu bayatlamaz)
        ctx = self._read(now, full_scan=None)
        if ctx is None:
            return self._unreachable(acts)
        bpos, oo = ctx
        fatal = False
        spos = {p.pair: p for p in self.state.open_positions()}
        margins = self._margins()
        unresolved_l3: set[str] = set()
        # L3 / L3b: state'te var, borsada yok
        for pair, sp in sorted(spos.items()):
            if pair in bpos:
                continue
            if sp.status in ("open", "closing"):
                if not self._l3(sp, now, acts, finds, reasons):
                    unresolved_l3.add(pair)
            elif sp.status == "opening":
                self._l3b(sp, now, acts, finds, reasons)
        # L2 / adopt / L4-L7, L10
        for pair, bp in sorted(bpos.items()):
            sp = self._state_pos(pair)
            if sp is None or (sp.status != "opening" and sp.side != bp.side):
                if self._late_fill(pair, bp, now, acts, finds):
                    continue
                fatal |= self._unknown(pair, bp, now, acts, finds, reasons, kill_close=True)
                continue
            if sp.status == "opening":
                kind, sp = self._adopt_opening(sp, bp, now, acts, finds, oo.get(pair, []))
                if kind == "unknown":
                    fatal |= self._unknown(pair, bp, now, acts, finds, reasons, kill_close=True)
                if sp is None:
                    continue
            self._register(sp, bp, oo.get(pair, []))
            step = self._rules(pair)[1]
            excess = sp.qty is not None and bp.qty - sp.qty >= step / 2
            pk = self.state.kv_get(f"partial:{sp.trade_id}")
            pq = float(pk.get("qty", 0.0) or 0.0) if isinstance(pk, dict) else 0.0
            if excess and pq > 0 and pk.get("state") == "done" and abs((bp.qty - sp.qty) - pq) < step / 2:
                self.counters["partial_exch_lag_suspect"] += 1       # state kismiyi dusmus, borsa henuz eski adet (positionRisk gecikmesi?)
                log.warning("mutabakat: kismi %s sonrasi borsa adedi eski gorunuyor (state %s borsa %s): gecikme suphesi; "
                            "davranis degismedi", sp.trade_id, sp.qty, bp.qty)
            if excess:
                fatal |= self._unknown(pair, bp, now, acts, finds, reasons, kill_close=True, excess=bp.qty - sp.qty,
                                       known=sp)
            elif sp.qty is not None and sp.qty - bp.qty >= step / 2:
                if pq > 0 and pk.get("state") == "pending" and abs((sp.qty - bp.qty) - pq) < step / 2:
                    self.counters["partial_pending_expected"] += 1   # bekleyen kismi emir borsada doldu: dis azaltma DEGIL
                    log.warning("mutabakat: bekleyen kismi emir trade %s dolmus gorunuyor (state %s borsa %s): ext_reduction yok; "
                                "motor emri kimlikle cozer", sp.trade_id, sp.qty, bp.qty)
                else:
                    self._l4(sp, bp, now, acts, finds)
            else:
                self._clear_reduction(sp)
            self._stops(sp, bp, oo.get(pair, []), now, acts, finds, reasons, protect_only=False, skip_requantity=excess)
            self._targets(sp, bp, oo.get(pair, []), now, acts, finds, skip_requantity=excess)    # 24.11: bekleyen hedef (stoptan SONRA, koruyucu degil)
            self._l10(sp, bp, margins, finds, reasons)
            self._price_drift(sp, bp, finds)
        # L8 yetim / L9 yabanci
        self._orphans(bpos, oo, unresolved_l3, acts, finds)
        if self._flat:                                    # duz kip: sembolsuz tam tarama (yabanci emirler burada bulunur)
            self._foreign(finds, reasons)
        self._ledger_checks(acts, finds, reasons)
        self._exit_unknown_hold(reasons)
        self._apply_blocks(reasons, acts)
        return ReconcileReport(ok=not finds, fatal=fatal, actions=tuple(acts), findings=tuple(finds))

    # ================================================================== okuma
    def _unreachable(self, acts=()) -> ReconcileReport:
        return ReconcileReport(ok=False, fatal=False, actions=tuple(acts), findings=("exchange_unreachable",))

    def _read(self, now: datetime, full_scan: bool | None):
        """(borsa_pozisyonlari, {pair: [acik emirler]}) ya da None (herhangi okuma basarisiz: hicbir eylem yok)."""
        try:
            bpos = {p.pair: p for p in self.broker.positions()}
            spairs = {p.pair for p in self.state.open_positions()}
            watch = sorted(set(bpos) | spairs)
            flat = not bpos and not spairs
            oo: dict[str, list[BrokerOrder]] = {}
            if full_scan or (full_scan is None and flat):
                for o in self.broker.open_orders():
                    oo.setdefault(o.pair, []).append(o)
            else:
                for pair in watch:
                    oo[pair] = list(self.broker.open_orders(pair))
            self._flat = flat
            return bpos, oo
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001 - eksik veriyle karar verilmez
            log.warning("mutabakat: okuma basarisiz (%r); tur eylemsiz", e)
            return None

    def _margins(self) -> Mapping[str, str]:
        if self._margin_types is None:
            return {}
        try:
            return self._margin_types()
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("marginType okunamadi: %r", e)
            return {}

    def _state_pos(self, pair: str) -> Position | None:
        for p in self.state.open_positions():
            if p.pair == pair:
                return p
        return None

    def _rules(self, pair: str) -> tuple[float, float]:
        """(tick, step): once broker (piyasa verisi gerekmez), yoksa OrderManager.rules_fn."""
        try:
            r = self.broker.rules(pair)
        except (DataError, KeyError):
            r = self.orders.rules_fn(pair)
        return r.tick, r.step

    # ================================================================== L2 / L2a
    def _unknown(self, pair, bp: BrokerPosition, now, acts, finds, reasons, *, kill_close: bool,
                 excess: float | None = None, known: Position | None = None) -> bool:
        finds.append(f"unknown_position:{pair}")
        reasons.append("reconcile_unknown_position")
        log.critical("mutabakat: borsada state'te olmayan/uyumsuz pozisyon %s (%s %.8g)", pair, bp.side, bp.qty)
        self.counters["unknown_position"] += 1
        self.pause.add("unknown_position", by="engine:reconcile", note=f"{pair} {bp.side} {bp.qty}")
        if kill_close and self.kill.active():
            self._kill_close(pair, bp, excess, now, acts)
        return True

    def _kill_mtime_at(self) -> str | None:
        try:
            return "mtime:%d" % os.stat(self.kill.path).st_mtime_ns
        except OSError:
            return None

    def _kill_close(self, pair: str, bp: BrokerPosition, excess: float | None, now: datetime, acts: list[str]) -> None:
        step = self._rules(pair)[1]
        qty = self._floor(bp.qty if excess is None else excess, step)          # adima asagi
        if not qty > 0:
            return
        info = self.kill.info() or {}
        at = info.get("at")
        if not isinstance(at, str) or not at:
            at = self._kill_mtime_at()                 # operatorun bos `touch KILL`i: mtime, etkinlestirme basina sabit
        if not at:
            log.critical("mutabakat: KILL kapanisi reddedildi (%s): kill dosyasi okunamiyor, kimlik uretilemez", pair)
            acts.append(f"kill_close_refused:{pair}")
            self.counters["kill_close_refused"] += 1
            return
        cid = kill_close_client_id(self.cfg.bot, pair_symbol(pair), at)
        if self.state.get_order(cid) is not None:
            # KILL etkinlestirmesi basina TEK deneme (kimlik kill.at'ten): pozisyon duruyorsa her turda CRIT
            log.critical("mutabakat: KILL kapanisi sonuclanmadi, %s hala acik (emir %s)", pair, cid)
            acts.append(f"kill_close_pending:{pair}")
            self.counters["kill_close_pending"] += 1
            return
        req = OrderRequest(client_id=cid, pair=pair, role="exit", order_side=order_side_for(bp.side, "exit"), qty=qty,
                           trigger_price=None, reduce_only=True, leverage=None, signal_bar_close_ts=now, created_ts=now)
        out = self.orders._submit(req, 0, None)       # noqa: SLF001
        acts.append(f"kill_closed_unknown:{pair}" if out.ok else f"kill_close_failed:{pair}")

    def _late_fill(self, pair: str, bp: BrokerPosition, now: datetime, acts, finds) -> bool:
        """L2a: son 24 saatte `failed`/`unknown` giris emrimiz var ve query `filled` diyor -> satir yeniden acilir."""
        step = self._rules(pair)[1]
        cands = []
        for p in self.state.closed_positions_since(now - LATE_FILL_WINDOW):
            if p.pair != pair or p.side != bp.side:
                continue
            for r in self.state.orders_for_trade(p.trade_id):
                if r.role == "entry" and r.status in ("failed", "unknown"):
                    cands.append((p, r))
        unverified = False
        for p, r in sorted(cands, key=lambda x: x[1].created_ts, reverse=True):
            try:
                bo = self.broker.query(pair, r.client_id)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("L2a sorgu basarisiz %s: %r", r.client_id, e)
                unverified = True
                continue
            if bo is None or bo.status != "filled":
                continue
            if bp.qty - (bo.filled_qty or bp.qty) >= step / 2:
                continue                                      # borsada fazladan miktar var: L2
            cur = self.state.get_position(p.trade_id) or p
            price = bo.avg_price if (bo.avg_price and bo.avg_price > 0) else bp.entry_price
            if not (isinstance(price, (int, float)) and math.isfinite(price) and price > 0):      # DD-11 Z-3
                log.warning("mutabakat: gec dolum fiyati gecersiz (%s %s); kuyruklama yok", pair, r.client_id)
                self.counters["bad_fill_price"] += 1
                continue
            fee = bp.qty * price * float(self.cfg.cost.taker_fee)
            fill = Fill(client_id=r.client_id, pair=pair, role="entry", order_side=r.order_side, qty=bp.qty, price=price,
                        fee=fee, ts=bo.updated_ts or now, reason="market")
            with self.state.tx():
                newp = replace(apply_entry_fill(cur, fill, None, now), status="open", exit_reason=None, closed_ts=None,
                               exit_client_id=None)
                self._persist(cur, newp)
                self.state.update_order(r.client_id, status="filled", updated_ts=now)
                self.state.outbox_add("entry", cur.trade_id,
                                      build_trade_entry(newp, exec_payload(exec_fields("entry", None, fill, r))[0]))
                self.state.kv_set(f"entry_fee_estimated:{cur.trade_id}", True)
            log.critical("mutabakat: GEC DOLUM %s trade %s yeniden acildi", pair, cur.trade_id)
            self.counters["late_fill"] += 1
            self.pause.add("late_fill", by="engine:reconcile", note=f"{pair} trade {cur.trade_id}")
            finds.append(f"late_fill:{pair}")
            acts.append(f"late_fill_reopened:{cur.trade_id}")
            pos = self.state.get_position(cur.trade_id)
            self._register(pos, bp, [])
            self._stops(pos, bp, [], now, acts, finds, [], protect_only=True)
            return True
        if unverified:
            # sorgu verisi eksik: tutus/KILL kapanisi YOK; sonraki turda yeniden denenir (11 §8 L2a)
            finds.append(f"late_fill_unverified:{pair}")
            self.counters["late_fill_unverified"] += 1
            return True
        return False

    # ================================================================== opening -> open benimseme (L2b; F4/F5/F6)
    def _adopt_opening(self, sp: Position, bp: BrokerPosition, now, acts, finds, orders_open):
        """(kind, pozisyon). Kanit sarti (11 §8 L2b): giris emri satiri VAR + `query(cid)` terminal ve filled_qty > 0 + yon
        eslesir + bp.qty <= filled_qty + step/2. Satir yok / "emir yok" / terminal-dolumsuz / yon uyusmaz => ("unknown", None):
        L2 (dokunulmaz, tutus). Sorgu HATASI => `opening_unverified` bulgusu, eylem yok. Emir hala `new` => poll'a birakilir.
        kind: "adopted" (pozisyon doner) | "skip" | "unknown"."""
        rows = [r for r in self.state.orders_for_trade(sp.trade_id) if r.role == "entry"]
        row = rows[-1] if rows else None
        if row is None or sp.side != bp.side or row.order_side != order_side_for(bp.side, "entry"):
            return "unknown", None
        try:
            bo = self.broker.query(sp.pair, row.client_id)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("L2b sorgu basarisiz %s: %r", row.client_id, e)
            finds.append(f"opening_unverified:{sp.trade_id}")
            self.counters["opening_unverified"] += 1
            return "skip", None
        if bo is None:
            return "unknown", None
        if bo.status == "new":
            return "skip", None
        filled = float(bo.filled_qty or 0.0)
        step = self._rules(sp.pair)[1]
        if not filled > 0 or bp.qty > filled + step / 2:
            return "unknown", None
        price = bo.avg_price if (bo.avg_price and bo.avg_price > 0) else bp.entry_price
        if not (isinstance(price, (int, float)) and math.isfinite(price) and price > 0):          # DD-11 Z-3
            log.warning("mutabakat: benimseme fiyati gecersiz (%s %s); benimseme yok", sp.pair, row.client_id)
            self.counters["bad_fill_price"] += 1
            return "unknown", None
        ts = bo.updated_ts if bo.updated_ts and bo.updated_ts <= now else now
        fee = filled * price * float(self.cfg.cost.taker_fee)
        fill = Fill(client_id=row.client_id, pair=sp.pair, role="entry", order_side=row.order_side,
                    qty=filled, price=price, fee=fee, ts=ts, reason="market")
        with self.state.tx():
            newp = apply_entry_fill(sp, fill, None, now)
            self._persist(sp, newp)
            if row.status != "filled":
                self.state.update_order(row.client_id, status="filled", updated_ts=now)
            self.state.outbox_add("entry", sp.trade_id,
                                  build_trade_entry(newp, exec_payload(exec_fields("entry", None, fill, row))[0]))
            self.state.kv_set(f"entry_fee_estimated:{sp.trade_id}", True)
        self.counters["opening_adopted"] += 1
        acts.append(f"opening_adopted:{sp.trade_id}")
        log.warning("mutabakat: opening pozisyon sorguyla dogrulandi, dolum benimsendi (trade %s qty %s)", sp.trade_id, filled)
        cur = self.state.get_position(sp.trade_id)
        eq = self.state.kv_get(f"eq:{sp.trade_id}")
        if cur is not None and eq:
            viol = fill_risk_violation(cur, float(eq), self._rules(sp.pair)[0])
            if viol:
                self.counters["fill_risk_violation"] += 1
                finds.append(f"fill_risk_violation:{sp.trade_id}")
                log.critical("benimsenen dolumda risk ihlali (%s) trade %s: once stop, sonra cikis", viol, sp.trade_id)
                self._register(cur, bp, orders_open)
                self._stops(cur, bp, orders_open, now, acts, finds, [], protect_only=True)
                again = self.state.get_position(sp.trade_id)
                if again is not None and again.status == "open":
                    self.orders.market_exit(replace(again, qty=bp.qty), "other", now)
                return "skip", None
        return "adopted", cur

    # ================================================================== L3 / L3b
    def _hint_ids(self, sp: Position) -> list[str]:
        ids: list[str] = []
        for c in (sp.stop_client_id, sp.exit_client_id):
            if c and c not in ids:
                ids.append(c)
        for r in reversed(self.state.orders_for_trade(sp.trade_id)):
            if r.role in ("stop", "exit", "target") and r.client_id not in ids:       # 24.11: bekleyen hedef emri de kapanis atfinda aday
                ids.append(r.client_id)
        return ids

    def _l3(self, sp: Position, now, acts, finds, reasons) -> bool:
        """True: cikis turetildi/isleme verildi."""
        self._register_partial(sp)                         # duz pozisyon yolu: kismi bacak kapanis olayindan dislanir (cift sayim yok)
        try:
            evs = self.broker.closing_events(sp.pair, sp.entry_ts or sp.signal_bar_close_ts, self._hint_ids(sp))
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("closing_events basarisiz %s: %r", sp.pair, e)
            evs = []
        if evs:
            self._handle(list(evs), now)
            if self.state.kv_get(f"exit_unresolved_since:{sp.trade_id}") is not None:
                with self.state.tx():
                    self.state.kv_set(f"exit_unresolved_since:{sp.trade_id}", None)
            acts.append(f"exit_derived:{sp.trade_id}")
            return True
        key = f"exit_unresolved_since:{sp.trade_id}"
        since = self.state.kv_get(key)
        if since is None:
            with self.state.tx():
                self.state.kv_set(key, iso_z(now))
            since_dt = now
        else:
            since_dt = parse_iso_z(since)
        finds.append(f"exit_unresolved:{sp.trade_id}")
        reasons.append("reconcile_state_orphan")
        if (now - since_dt).total_seconds() > EXIT_UNRESOLVED_CRIT_S:
            log.critical("mutabakat: cikis 10 dk'dan uzun suredir turetilemiyor trade %s", sp.trade_id)
        return False

    def _l3b(self, sp: Position, now, acts, finds, reasons) -> None:
        win = float(getattr(getattr(self.cfg, "live", None), "entry_resolve_window_s", 60.0) or 60.0)
        rows = [r for r in self.state.orders_for_trade(sp.trade_id) if r.role == "entry"]
        acc = [r for r in rows if r.status == "accepted"]
        if acc:
            # DD-11 D3: pencere dolunca `accepted` satiri sorgulanir; dolu ise _l3b_filled, fiyat bilinmiyorsa bulgu + duraklatma
            t0a = max([r.created_ts for r in rows], default=sp.signal_bar_close_ts)
            if (now - t0a).total_seconds() < win:
                return
            try:
                bo = self.broker.query(sp.pair, acc[-1].client_id)
            except StateError:
                raise
            except Exception:  # noqa: BLE001
                return
            if bo is None or bo.status != "filled":
                return
            px = bo.avg_price
            if not (isinstance(px, (int, float)) and math.isfinite(px) and px > 0):
                finds.append(f"opening_unpriced:{sp.trade_id}")
                self.counters["opening_unpriced"] += 1
                self.pause.add("unknown_position", by="engine:reconcile", note=f"opening_unpriced {sp.pair} trade {sp.trade_id}")
                return
            self._l3b_filled(sp, acc[-1], rows, now, win, acts, finds, reasons)
            return
        filled = [r for r in rows if r.status == "filled"]
        if filled:
            self._l3b_filled(sp, filled[-1], rows, now, win, acts, finds, reasons)
            return
        t0 = max([r.created_ts for r in rows], default=sp.signal_bar_close_ts)
        if (now - t0).total_seconds() < win:
            return
        for r in rows:
            if r.status in ("pending", "unknown"):
                try:
                    if self.broker.query(sp.pair, r.client_id) is not None:
                        return                                # emir var: L1/poll cozer
                except StateError:
                    raise
                except Exception:  # noqa: BLE001
                    return
                with self.state.tx():
                    self.state.update_order(r.client_id, status="failed", detail="unopened_window", updated_ts=now)
        self._close_unopened_cb(sp, now)
        acts.append(f"close_unopened:{sp.trade_id}")

    def _l3b_filled(self, sp: Position, row, rows, now, win: float, acts, finds, reasons) -> None:
        """Fix 4: giris satiri `filled` ama pozisyon `opening` ve borsa duz (benimseme satiri guncelledi, `on_entry_adopted`
        cagrilmadan cokus + dis kapanis). Pencereden sonra dolum sorgudan uygulanir; pozisyon `open` olunca L3 kapatir."""
        t0 = max([r.created_ts for r in rows], default=sp.signal_bar_close_ts)
        cb = getattr(self.orders, "on_entry_adopted", None)
        if (now - t0).total_seconds() < win or cb is None:
            return
        try:
            bo = self.broker.query(sp.pair, row.client_id)
        except StateError:
            raise
        except Exception:  # noqa: BLE001
            return                                        # okunamadi: tahmin yok, sonraki tur
        if bo is None or bo.status != "filled":
            return
        px = bo.avg_price
        if not (isinstance(px, (int, float)) and math.isfinite(px) and px > 0):     # DD-11 D3: fiyatsiz dolum uygulanmaz
            finds.append(f"opening_unpriced:{sp.trade_id}")
            self.counters["opening_unpriced"] += 1
            self.pause.add("unknown_position", by="engine:reconcile", note=f"opening_unpriced {sp.pair} trade {sp.trade_id}")
            return
        cb(row, bo)
        acts.append(f"entry_fill_applied:{sp.trade_id}")
        cur = self.state.get_position(sp.trade_id)
        if cur is not None and cur.status in ("open", "closing"):
            self._l3(cur, now, acts, finds, reasons)

    # ================================================================== L4
    def _l4(self, sp: Position, bp: BrokerPosition, now, acts, finds) -> None:
        """Dis azaltma/ADL/kismi cikis: state `qty` ORIJINAL kalir (cikis olayi tum azaltmalari kapsar); borsa miktari ve
        tahmini gerceklesen kar-zarar kv'ye yazilir; stop yeni miktarla L6'da yeniden kurulur."""
        prev = self.state.kv_get(f"ext_reduction:{sp.trade_id}")
        if not (isinstance(prev, dict) and abs(float(prev.get("exch_qty", -1)) - bp.qty) < 1e-12):
            dq = sp.qty - bp.qty
            mark = bp.mark_price or bp.entry_price
            sign = 1.0 if sp.side == "long" else -1.0
            rec = {"orig_qty": sp.qty, "exch_qty": bp.qty, "reduced_qty": dq, "at": iso_z(now),
                   "est_realized_pnl": sign * (mark - (sp.entry_price or bp.entry_price)) * dq, "pnl_is_estimate": True}
            with self.state.tx():
                self.state.kv_set(f"ext_reduction:{sp.trade_id}", rec)
            log.critical("mutabakat: dis azaltma trade %s (state qty %s -> borsa %s); qty korunuyor, stop yeni miktarla",
                         sp.trade_id, sp.qty, bp.qty)
            self.counters["qty_reduced_external"] += 1

    def _clear_reduction(self, sp: Position) -> None:
        if self.state.kv_get(f"ext_reduction:{sp.trade_id}") is not None:
            with self.state.tx():
                self.state.kv_set(f"ext_reduction:{sp.trade_id}", None)

    # ================================================================== stop yonetimi (L5, L6, L7, L8b)
    def _stops(self, sp: Position, bp: BrokerPosition, orders_open: list[BrokerOrder], now, acts, finds, reasons,
               *, protect_only: bool, skip_requantity: bool = False) -> None:
        if sp.status not in ("open", "closing"):
            return
        tick, step = self._rules(sp.pair)
        tracked = [o for o in orders_open if o.role == "stop" and o.pair == sp.pair
                   and self._row_trade(o.client_id) == sp.trade_id]
        untracked = [o for o in orders_open if o.role == "stop" and o.pair == sp.pair
                     and not self.state.get_order(o.client_id)]
        qty = self._floor(bp.qty, step)                 # borsa miktari adimin tam kati olmali (asagi)
        if skip_requantity and sp.qty is not None:
            qty = self._floor(min(bp.qty, sp.qty), step)  # fazla miktar (L2): stop YALNIZ bizim (state) miktarimiz icin
        if not tracked:
            ok = self._reinstall(sp, qty, tick, now, acts, finds, reasons, why="missing")
            if ok:
                self.counters["stops_reinstalled"] += 1
                finds.append(f"no_stop:{sp.trade_id}")
            self._cancel_untracked(untracked, acts, finds, keep_if=not ok)
            return
        self._cancel_untracked(untracked, acts, finds)
        if protect_only:
            return
        # L7: en siki kalir
        long_ = sp.side == "long"
        key = (lambda o: o.trigger_price or 0.0) if long_ else (lambda o: -(o.trigger_price or 0.0))
        kept = max(tracked, key=key)
        for o in tracked:
            if o is not kept:
                self._cancel(sp.pair, o.client_id, acts, f"dup_stop_canceled:{o.client_id}")
                finds.append(f"dup_stop:{sp.trade_id}")
        cur = self.state.get_position(sp.trade_id) or sp
        need_new = False
        trig = kept.trigger_price or cur.current_stop
        if abs(trig - cur.current_stop) >= tick / 2:
            tighter = trig > cur.current_stop if long_ else trig < cur.current_stop
            if tighter:
                row = self.state.get_order(kept.client_id)
                with self.state.tx():
                    self.state.update_position(cur.trade_id, current_stop=trig, stop_client_id=kept.client_id,
                                               stop_seq=max(cur.stop_seq, row.seq if row else 0))
                acts.append(f"state_stop_tightened:{cur.trade_id}")
            else:
                need_new = True
                finds.append(f"stop_looser:{cur.trade_id}")
        elif cur.stop_client_id != kept.client_id:
            row = self.state.get_order(kept.client_id)
            with self.state.tx():
                self.state.update_position(cur.trade_id, stop_client_id=kept.client_id,
                                           stop_seq=max(cur.stop_seq, row.seq if row else 0))
        if (not skip_requantity and abs(kept.qty - bp.qty) >= step / 2):
            need_new = True
            finds.append(f"stop_qty_mismatch:{cur.trade_id}")
        if need_new:
            cur = self.state.get_position(sp.trade_id) or cur
            if self._reinstall(cur, qty, tick, now, acts, finds, reasons, why="requantity", replace_ids=[kept.client_id]):
                acts.append(f"stop_requantified:{cur.trade_id}")

    def _targets(self, sp: Position, bp: BrokerPosition, orders_open: list[BrokerOrder], now, acts, finds,
                 *, skip_requantity: bool = False) -> None:
        """24.11 (target_mode=resting): bekleyen hedef emri mutabakati. Hedef KORUYUCU DEGILDIR: eksik/uyumsuz hedef yeniden kurulur
        ama basarisizlik pozisyonu kapatmaz (motor kendi tf kapanisinda `bar_close` yedegiyle hedefi denetler). Kurallar: orders
        tablosunda olmayan bizim onekli hedef iptal; bir pozisyonda tek hedef (fazlasi iptal); hedef yok ya da adedi borsa
        adediyle uyumsuz -> yeni seq ile kur, eskisini kurulduktan sonra iptal et. Durum `target:<trade_id>` anahtarinda."""
        from .position_manager import exit_mode_of
        cur = self.state.get_position(sp.trade_id) or sp
        if cur.status != "open" or getattr(self.cfg, "target_mode", "bar_close") != "resting":
            return
        if exit_mode_of(cur.setup) != "target" or not (isinstance(cur.planned_target, (int, float)) and cur.planned_target > 0):
            return
        tick, step = self._rules(cur.pair)
        mine = [o for o in orders_open if o.role == "target" and o.pair == cur.pair]
        untracked = [o for o in mine if not self.state.get_order(o.client_id)]
        tracked = [o for o in mine if self._row_trade(o.client_id) == cur.trade_id]
        for o in untracked:
            finds.append(f"untracked_target:{o.client_id}")
            self._cancel(o.pair, o.client_id, acts, f"untracked_target_canceled:{o.client_id}")
        qty = self._floor(bp.qty, step)
        if skip_requantity and cur.qty is not None:
            qty = self._floor(min(bp.qty, cur.qty), step)
        tk = self.state.kv_get(f"target:{cur.trade_id}")
        tk = tk if isinstance(tk, dict) else None
        state = None if tk is None else tk.get("state")
        if not tracked:
            if state == "failed":
                return                                     # kurulamamisti: bar_close yedegi calisir; her turda denemeyiz
            if state == "active":
                finds.append(f"no_target:{cur.trade_id}")  # borsada kayip (iptal/suresi doldu): yeniden kur
            self._reinstall_target(cur, qty, now, acts, finds, why="missing", replace_ids=())
            return
        kept = max(tracked, key=lambda o: (self.state.get_order(o.client_id).seq if self.state.get_order(o.client_id) else -1))
        for o in tracked:
            if o is not kept:
                self._cancel(cur.pair, o.client_id, acts, f"dup_target_canceled:{o.client_id}")
                finds.append(f"dup_target:{cur.trade_id}")
        row = self.state.get_order(kept.client_id)
        if tk is None or state != "active" or tk.get("cid") != kept.client_id:
            with self.state.tx():
                self.state.kv_set(f"target:{cur.trade_id}", {"state": "active", "cid": kept.client_id,
                                                             "seq": row.seq if row else 0, "why": "adopted_by_reconcile"})
            acts.append(f"target_adopted:{cur.trade_id}")
        if not skip_requantity and abs(kept.qty - bp.qty) >= step / 2:
            finds.append(f"target_qty_mismatch:{cur.trade_id}")
            self._reinstall_target(cur, qty, now, acts, finds, why="requantity", replace_ids=(kept.client_id,))

    def _reinstall_target(self, sp: Position, qty: float, now, acts, finds, *, why: str, replace_ids) -> bool:
        """Yeni seq ile hedef kur (borsa adedi); eskiler yenisi KABUL EDILDIKTEN sonra iptal. Basarisizsa eskiler kalir, piyasa cikisi YOK."""
        if not qty > 0:
            return False
        om = self.orders
        seq = om.next_target_seq(sp)
        try:
            out = om.place_target(replace(sp, qty=qty), seq)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("mutabakat: hedef kurulamadi trade %s (%s): %r", sp.trade_id, why, e)
            return False
        if out is None or not out.ok:
            log.warning("mutabakat: hedef yeniden kurulamadi trade %s (%s): %s", sp.trade_id, why, None if out is None else out.note)
            self.counters["target_reinstall_failed"] += 1
            return False
        with self.state.tx():
            self.state.kv_set(f"target:{sp.trade_id}", {"state": "active", "cid": out.order.client_id, "seq": out.order.seq,
                                                        "why": f"reconcile_{why}"})
        acts.append(f"target_installed:{sp.trade_id}")
        self.counters["targets_reinstalled"] += 1
        for cid in replace_ids:
            if cid != out.order.client_id:
                self._cancel(sp.pair, cid, acts, f"old_target_canceled:{cid}")
        reg = getattr(self.broker, "register_position", None)
        if reg is not None and sp.entry_ts is not None:
            try:
                reg(sp.pair, sp.entry_ts, [r.client_id for r in self.state.orders_for_trade(sp.trade_id)])
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("register_position basarisiz %s: %r", sp.pair, e)
        return True

    def _row_trade(self, cid: str):
        r = self.state.get_order(cid)
        return None if r is None else r.trade_id

    @staticmethod
    def _floor(qty: float, step: float) -> float:
        return round(int(qty / step + 1e-9) * step, 12) if step > 0 else qty

    def _next_seq(self, sp: Position) -> int:
        seqs = [sp.stop_seq] + [r.seq for r in self.state.orders_for_trade(sp.trade_id) if r.role == "stop"]
        return max(seqs) + 1

    def _reinstall(self, sp: Position, qty: float, tick: float, now, acts, finds, reasons, *, why: str,
                   replace_ids: list[str] = ()) -> bool:
        """Yeni stop (yeni seq, `current_stop`, siki yuvarlama, borsa miktari). Basarisizsa eskiler KALIR; eski ancak yeni
        kabul edildikten sonra iptal edilir ve yeni stop hicbir kosulda iptal edilmez (r8). Eksik stop'ta ikinci deneme
        de olmazsa piyasada kapatilir."""
        om = self.orders
        price = round_tight(sp.current_stop, sp.side, tick)
        last = None
        for attempt in range(2):
            seq = self._next_seq(sp)
            with self.state.tx():
                self.state.update_position(sp.trade_id, stop_seq=seq)
            req = om._stop_request(replace(sp, qty=qty), price, seq)      # noqa: SLF001
            out = om._submit(req, seq, sp.trade_id)                         # noqa: SLF001
            last = out
            if out.ok:
                with self.state.tx():
                    self.state.update_position(sp.trade_id, stop_client_id=req.client_id)
                acts.append(f"stop_installed:{sp.trade_id}")
                for cid in replace_ids:
                    if cid != req.client_id:
                        self._cancel(sp.pair, cid, acts, f"old_stop_canceled:{cid}")
                return True
            sp = self.state.get_position(sp.trade_id) or sp
            if out.note == "would_trigger":
                break
        if why == "missing" or (last is not None and last.note == "would_trigger"):
            log.critical("mutabakat: stop kurulamadi (%s), trade %s piyasada kapatiliyor", last.note if last else None,
                         sp.trade_id)
            cur = self.state.get_position(sp.trade_id) or sp
            if cur.status in ("open", "closing"):
                self.orders.market_exit(replace(cur, qty=qty), "force_exit", now)
            if last is None or last.note != "would_trigger":
                reasons.append("stop_failed")
                self._block("stop_failed")
                self.orders.note_stop_failed(sp.trade_id)
            acts.append(f"stop_failed_closed:{sp.trade_id}")
        else:
            log.warning("mutabakat: stop yeniden kurulamadi (%s); eski stop duruyor", last.note if last else None)
        return False

    def _cancel(self, pair: str, cid: str, acts: list[str], tag: str) -> None:
        try:
            self.broker.cancel(pair, cid)
            acts.append(tag)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("iptal basarisiz %s: %r", cid, e)

    def _cancel_untracked(self, untracked: list[BrokerOrder], acts, finds, keep_if: bool = False) -> None:
        if keep_if:
            return                          # tek koruma bu olabilir: yenisi kurulana kadar dokunma
        for o in untracked:
            log.critical("mutabakat: orders tablosunda olmayan bizim onekli emir %s iptal ediliyor", o.client_id)
            finds.append(f"untracked_order:{o.client_id}")
            self._cancel(o.pair, o.client_id, acts, f"untracked_canceled:{o.client_id}")

    # ================================================================== L8 / L9 / L10
    def _orphans(self, bpos, oo, skip: set[str], acts, finds) -> None:
        for pair, orders_ in sorted(oo.items()):
            if pair in bpos or pair in skip:
                continue
            for o in orders_:
                if not o.reduce_only:
                    continue
                finds.append(f"orphan_order:{o.client_id}")
                self._cancel(pair, o.client_id, acts, f"orphan_canceled:{o.client_id}")
                if not self.state.get_order(o.client_id):
                    log.critical("mutabakat: orders tablosunda olmayan yetim emir %s", o.client_id)

    def _foreign(self, finds, reasons) -> None:
        try:
            rows = self.broker.foreign_open_orders()
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("foreign_open_orders okunamadi: %r", e)
            return
        for r in rows:
            finds.append(f"foreign_order:{r.get('symbol')}")
            reasons.append("reconcile_foreign_order")
            log.critical("mutabakat: yabanci acik emir %s (dokunulmadi)", r.get("symbol"))

    def _l10(self, sp: Position, bp: BrokerPosition, margins: Mapping[str, str], finds, reasons) -> None:
        mt = margins.get(bp.pair)
        if (mt is not None and str(mt).lower() != "isolated") or bp.leverage != self.cfg.leverage:
            finds.append(f"account_mode_drift:{bp.pair}")
            reasons.append("reconcile_account_mode_drift")
            log.critical("mutabakat: hesap modu sapmasi %s (margin=%s leverage=%s)", bp.pair, mt, bp.leverage)

    def _price_drift(self, sp: Position, bp: BrokerPosition, finds) -> None:
        if sp.entry_price and abs(bp.entry_price - sp.entry_price) / sp.entry_price > ENTRY_DRIFT:
            log.warning("mutabakat: entry_price_drift %s state=%s borsa=%s", sp.pair, sp.entry_price, bp.entry_price)
            self.counters["entry_price_drift"] += 1          # uyari + sayac; bulgu degil (11 §8 tolerans)

    def _register(self, sp: Position, bp: BrokerPosition, orders_open: list[BrokerOrder]) -> None:
        reg = getattr(self.broker, "register_position", None)
        if reg is None:
            return
        ids = self._hint_ids(sp) + [o.client_id for o in orders_open if o.client_id not in self._hint_ids(sp)]
        try:
            reg(sp.pair, sp.entry_ts or bp.opened_ts, ids)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("register_position basarisiz %s: %r", sp.pair, e)
        self._register_partial(sp)

    def _register_partial(self, sp: Position) -> None:
        """Cikis kipleri: kismi bacak kimligi brokera bildirilir (pozisyon borsada olsun olmasin; yeniden baslatma). Bu emrin
        islemleri son kapanis olayindan dislanir; defter kismi bacagi tek kez karma fiyata katar."""
        rp = getattr(self.broker, "register_partial", None)
        pk = self.state.kv_get(f"partial:{sp.trade_id}")
        if not (callable(rp) and isinstance(pk, dict) and pk.get("cid") and pk.get("state") in ("pending", "done")):
            return
        try:
            rp(sp.pair, str(pk["cid"]))
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("register_partial basarisiz %s: %r", sp.pair, e)

    # ================================================================== L11 + blokaj
    def _exit_unknown_hold(self, reasons: list[str]) -> None:
        """F16: cikis denemeleri `EXIT_RETRY_LIMIT`'e vardiysa ve pozisyon hala duruyorsa `exit_unknown` mandali, otomatik
        temizlemeyle titrememeli: pozisyon kapanana dek korunur."""
        for p in self.state.open_positions():
            if p.status in ("open", "closing") and int(self.state.kv_get(f"exit_retry:{p.trade_id}", 0) or 0) >= EXIT_RETRY_LIMIT:
                reasons.append("exit_unknown")
                return

    def _ledger_checks(self, acts, finds, reasons) -> None:
        pending = self.state.outbox_pending()
        if pending:
            acts.append("drain_outbox")
            res = self.state.drain_outbox(self.ledger)
            if res.failed:
                finds.append("outbox_pending")
            pending = self.state.outbox_pending()
        pend_ids = {r.trade_id for r in pending}
        try:
            live_ps = [p for p in self.state.open_positions() if p.status in ("open", "closing")]
            state_ids = {p.trade_id for p in live_ps}
            for t in self.ledger.list_open_trades():
                tid = t.trade_id if hasattr(t, "trade_id") else t.id
                if tid not in state_ids and tid not in pend_ids:
                    finds.append(f"ledger_orphan:{tid}")
                    reasons.append("reconcile_ledger_orphan")
                    log.warning("mutabakat: defterde acik, state'te olmayan islem %s", tid)
            self.ledger.find_unledgered_trades([p.trade_id for p in live_ps if p.entry_price is not None])
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("mutabakat: defter denetimi basarisiz: %s", e)
            finds.append(f"ledger_check_failed:{type(e).__name__}")

    def _apply_blocks(self, reasons: list[str], acts: list[str]) -> None:
        reasons[:] = list(dict.fromkeys(reasons))
        reasons.sort(key=lambda r: _BLOCK_ORDER.index(r) if r in _BLOCK_ORDER else len(_BLOCK_ORDER))
        apply_block_set(self.state, reasons, acts)           # DD-2 D6: kume; kagit mutabakatla ayni kural

    # ================================================================== varsayilan olay isleyici (B4 kendi `_handle_events`ini verir)
    def _persist(self, old: Position, new: Position) -> None:
        from dataclasses import fields
        diff = {f.name: getattr(new, f.name) for f in fields(Position)
                if f.name != "trade_id" and getattr(new, f.name) != getattr(old, f.name)}
        if diff:
            self.state.update_position(old.trade_id, **diff)

    def _default_handle_events(self, evs: list[BrokerEvent], now: datetime) -> None:
        for e in evs:
            pos = self.state.position_for_pair(e.pair)
            if e.kind in ("fill", "liquidation") and e.fill is not None and e.fill.role != "entry":
                if pos is None or pos.status == "opening" or pos.entry_price is None:
                    self.counters["unexpected_fills"] += 1
                    continue
                with self.state.tx():
                    closed = apply_exit_fill(pos, e.fill, None, now)
                    self._persist(pos, close_position(pos, closed))
                    row = self.state.get_order(e.fill.client_id)
                    self.state.outbox_add("exit", pos.trade_id, build_trade_exit(
                        pos, closed, ex=exec_payload(exec_fields("exit", None, e.fill, row))[0]))
                    if row is not None and row.status not in ("filled", "rejected", "canceled", "failed"):
                        self.state.update_order(row.client_id, status="filled", updated_ts=now)
                self.orders.cancel_resting(pos)
            elif e.kind == "funding" and pos is not None and pos.status in ("open", "closing"):
                with self.state.tx():
                    self._persist(pos, apply_funding(pos, e))

    def _default_close_unopened(self, pos: Position, now: datetime) -> None:
        with self.state.tx():
            self.state.update_position(pos.trade_id, status="closed", exit_reason="other", closed_ts=now)
