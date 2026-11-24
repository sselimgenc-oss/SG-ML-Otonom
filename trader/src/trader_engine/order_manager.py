"""Idempotent emir yoneticisi (04 §4): pending-once, belirsizlik yolu, stop degistirme."""
from __future__ import annotations

import hashlib
import logging
import math
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Literal

from .clock import Clock
from .errors import BrokerUncertain, StateError
from .numeric import ceil_step, floor_step, is_multiple, round_tight
from .state import OrderRow, StateStore, iso_z
from .types import (BrokerOrder, Intent, OrderRequest, OrderResult, Position, Role, Side, SymbolRules,
                    order_side_for, require_utc)

log = logging.getLogger(__name__)

_ROLE_LETTER = {"entry": "e", "stop": "s", "target": "t", "exit": "x"}
_BO_STATUS = {"filled": "filled", "new": "accepted", "canceled": "canceled", "rejected": "rejected",
              "expired": "expired"}
_OK = ("accepted", "filled")
EXEC_META_MAX = 256           # WP-3: bellekteki emir-ani kaydi (ilk giren ilk cikar; kullanilinca silinir)
EXIT_RETRY_LIMIT = 3          # kamusal sabit (reconcile_live ve testler ice aktarir)
_EXIT_RETRY_LIMIT = EXIT_RETRY_LIMIT

__all__ = ["EXIT_RETRY_LIMIT", "make_client_id", "OrderRow", "SubmitOutcome", "OrderManager"]


def _cancel_gone(e: Exception) -> bool:
    """Iptal reddi 'emir yok' (-2011 Unknown order / -2013 Order does not exist): emir borsada zaten yok."""
    t = str(e)
    return "code=-2011" in t or "code=-2013" in t


def _cid_is_target(cid: str) -> bool:
    """Istemci kimligi hedef (rol `t`) mi: `tr<L|T>t-<hash>`."""
    return len(cid) > 3 and cid.startswith("tr") and cid[3:4] == "t"


def make_client_id(bot: str, role: Role, pair: str, side: Side, signal_bar_close_ts: datetime, seq: int) -> str:
    if role not in _ROLE_LETTER:
        raise ValueError(f"gecersiz role: {role!r}")
    if side not in ("long", "short"):
        raise ValueError(f"gecersiz side: {side!r}")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
        raise ValueError(f"seq >= 0 tamsayi olmali: {seq!r}")
    require_utc(signal_bar_close_ts, "signal_bar_close_ts")
    letter = _ROLE_LETTER[role]
    raw = f"{bot}|{pair}|{side}|{iso_z(signal_bar_close_ts)}|{letter}|{seq}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]
    return "tr" + ("L" if bot == "learner" else "T") + letter + "-" + h


@dataclass(frozen=True)
class SubmitOutcome:
    ok: bool
    status: Literal["filled", "accepted", "rejected", "failed"]
    order: OrderRow
    result: OrderResult | None
    note: str | None


class OrderManager:
    def __init__(self, bot: str, broker, state: StateStore, clock: Clock,
                 rules_fn: Callable[[str], SymbolRules], unknown_grace_s: float = 2.0, max_attempts: int = 2,
                 live_mode: bool = False, stop_deadline_s: float = 10.0, entry_resolve_window_s: float = 60.0) -> None:
        self.bot = bot
        self.broker = broker
        self.state = state
        self.clock = clock
        self.rules_fn = rules_fn
        self.unknown_grace_s = unknown_grace_s
        self.max_attempts = max(1, int(max_attempts))
        self.tick_fn: Callable[[str, datetime], float] | None = None   # yalniz legacy_compat: giris-ayi tarihsel tick
        # 11 §6 (WP-B4): canli yol. live_mode=False iken davranis bit-bit eskisi gibidir.
        self.live_mode = bool(live_mode)
        self.stop_deadline_s = float(stop_deadline_s)
        self.entry_resolve_window_s = float(entry_resolve_window_s)
        self.on_entry_adopted: Callable[[OrderRow, BrokerOrder], None] | None = None   # sorguyla bulunan giris dolumu
        self.on_ban: Callable[[], None] | None = None                                    # exchange_ban / rate_limited retinden sonra
        # 11 §6.4/§8: canli piyasa cikislari ve giris-penceresi kapanisi motorun kendi yolundan gecer
        self.exit_fn: Callable[[Position, str, datetime], object] | None = None          # Engine._submit_exit
        self.close_unopened_fn: Callable[[Position, datetime], None] | None = None       # Engine._close_unopened
        # WP-3 (defter-ek-alanlar 3.1): yalniz kayit. Durum deposuna YAZILMAZ; yeniden baslatmada kaybolur.
        self.exec_meta: "OrderedDict[str, dict]" = OrderedDict()
        self.quote_fn: Callable[[str], dict | None] | None = None   # 3.5 (Engine._order_quote); varsayilan yok
        self.on_stop_failed: Callable[[int | None], None] | None = None   # DD-6 O3 (Engine._note_stop_failed); kagitta yok

    def note_stop_failed(self, trade_id: int | None) -> None:
        if self.on_stop_failed is not None:
            self.on_stop_failed(trade_id)

    def _eff_qty(self, pos: Position) -> float:
        """Canli: L4 (dis azaltma) sonrasi state qty ORIJINAL kalir; emir miktari min(pos.qty, borsa miktari) (11 §8 L4)."""
        q = pos.qty
        if self.live_mode and q is not None:
            d = self.state.kv_get(f"ext_reduction:{pos.trade_id}")
            if isinstance(d, dict) and d.get("exch_qty"):
                q = min(q, float(d["exch_qty"]))
        return q

    def stop_tick(self, pos: Position) -> float:
        """Stop yuvarlama tick'i: native = borsa kurali; legacy_compat = pozisyonun GIRIS ayinin tarihsel tick'i."""
        if self.tick_fn is not None and pos.entry_ts is not None:
            return self.tick_fn(pos.pair, pos.entry_ts)
        return self.rules_tick(pos.pair)

    def rules_tick(self, pair: str) -> float:
        """DD-2 D9: koruyucu yolda (stop kur/guncelle) tick, `place_stop`in kullandigi SON BILINEN kuraldan okunur: bayat (>6 sa)
        kural `rules()`te DataError atar ama stop yine de kurulabilir; iki yol tutarsiz olmasin. Kagit brokerde `rules_last_known`
        yok: davranis ayni (`rules_fn`)."""
        lk = getattr(self.broker, "rules_last_known", None)
        if lk is not None:
            r = lk(pair)
            if r is not None:
                return r.tick
        return self.rules_fn(pair).tick
    # ------------------------------------------------------------------ yardimcilar
    def _call(self, req: OrderRequest) -> OrderResult:
        if req.role in ("entry", "exit"):
            return self.broker.market_order(req)
        if req.role == "stop":
            return self.broker.place_stop(req)
        return self.broker.place_target(req)

    def _send(self, req: OrderRequest) -> OrderResult | None:
        """POST oncesi commit citi; belirsizlikte None (= unknown)."""
        self.state.barrier(allow_outer=bool(getattr(self.broker, "is_simulated", False)))
        try:
            res = self._call(req)
        except StateError:
            raise
        except BrokerUncertain:
            return None
        except Exception as e:  # noqa: BLE001 - bilinmeyen hata = belirsiz (kor tekrar yok)
            log.warning("broker istisnasi %s: %r", req.client_id, e)
            return None
        if res.status == "unknown":
            return None
        return res

    def _query(self, pair: str, cid: str) -> tuple[bool, BrokerOrder | None]:
        """(sorgu_basarili, emir). Basarisiz sorgu 'emir yok' teyidi degildir."""
        try:
            return True, self.broker.query(pair, cid)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("query hatasi %s: %r", cid, e)
            return False, None

    def _upd(self, cid: str, **f) -> OrderRow:
        with self.state.tx():
            self.state.update_order(cid, updated_ts=self.clock.now(), **f)
        row = self.state.get_order(cid)
        assert row is not None
        return row

    def _pupd(self, trade_id: int, **f) -> None:
        """Pozisyon satiri varsa gunceller (yoksa sessiz)."""
        with self.state.tx():
            if self.state.get_position(trade_id) is not None:
                self.state.update_position(trade_id, **f)

    def _req_from_row(self, row: OrderRow) -> OrderRequest:
        lev = None
        if row.role == "entry" and row.trade_id is not None:
            p = self.state.get_position(row.trade_id)
            lev = p.leverage if p else None
        return OrderRequest(client_id=row.client_id, pair=row.pair, role=row.role, order_side=row.order_side,
                            qty=row.qty, trigger_price=row.trigger_price, reduce_only=row.reduce_only, leverage=lev,
                            signal_bar_close_ts=row.signal_bar_close_ts, created_ts=row.created_ts)

    def _outcome(self, row: OrderRow, result: OrderResult | None, note: str | None) -> SubmitOutcome:
        if row.status in _OK:
            return SubmitOutcome(True, row.status, row, result, note)  # type: ignore[arg-type]
        st = "failed" if row.status in ("failed", "unknown", "pending") else "rejected"
        return SubmitOutcome(False, st, row, result, note)  # type: ignore[arg-type]

    def _apply_result(self, row: OrderRow, res: OrderResult, note: str | None) -> SubmitOutcome:
        if res.status == "filled":
            row = self._upd(row.client_id, status="filled", broker_order_id=res.order_id)
        elif res.status == "accepted":
            row = self._upd(row.client_id, status="accepted", broker_order_id=res.order_id)
        else:  # rejected
            if res.reason == "duplicate_client_id":
                ok, bo = self._query(row.pair, row.client_id)
                if bo is not None:
                    return self._adopt(row, bo, "duplicate_adopted")
            row = self._upd(row.client_id, status="rejected", detail=res.reason)
            if res.reason in ("exchange_ban", "rate_limited") and self.on_ban is not None:
                self.on_ban()
            if note is None and res.reason == "would_trigger":
                note = "would_trigger"
            elif note is None:
                note = res.reason
        return self._outcome(row, res, note)

    def _adopt(self, row: OrderRow, bo: BrokerOrder, note: str) -> SubmitOutcome:
        st = _BO_STATUS.get(bo.status, "accepted")
        px = bo.avg_price
        if (self.live_mode and row.role == "entry" and st == "filled"
                and not (isinstance(px, (int, float)) and math.isfinite(px) and px > 0)):
            st = "accepted"                    # DD-11 D3: fiyatsiz dolum benimsenmez/doldu isaretlenmez; mutabakat (_l3b) cozer
            log.warning("fiyatsiz giris dolumu benimsenmedi (%s): satir accepted kaldi", row.client_id)
            return self._outcome(self._upd(row.client_id, status=st, broker_order_id=row.broker_order_id), None, note)
        partial = (self.live_mode and row.role == "entry" and bo.status != "filled" and bo.filled_qty > 0
                   and bo.status in ("expired", "canceled"))
        if partial:
            st = "filled"
        row = self._upd(row.client_id, status=st, broker_order_id=row.broker_order_id)
        if (self.on_entry_adopted is not None and row.role == "entry"
                and (bo.status == "filled" or partial)):
            self.on_entry_adopted(row, bo)
        return self._outcome(row, None, note)

    # ------------------------------------------------------------------ ortak gonderim
    def _put_meta(self, cid: str, meta: dict) -> None:
        self.exec_meta[cid] = meta
        while len(self.exec_meta) > EXEC_META_MAX:
            self.exec_meta.popitem(last=False)

    def _submit(self, req: OrderRequest, seq: int, trade_id: int | None, quote: bool = False) -> SubmitOutcome:
        cid = req.client_id
        existing = self.state.get_order(cid)
        if existing is not None:
            return self._existing(existing)
        now = self.clock.now()
        row = OrderRow(client_id=cid, pair=req.pair, role=req.role, order_side=req.order_side, qty=req.qty,
                       trigger_price=req.trigger_price, reduce_only=req.reduce_only, status="pending",
                       signal_bar_close_ts=req.signal_bar_close_ts, seq=seq, attempts=0, trade_id=trade_id,
                       broker_order_id=None, detail=None, created_ts=now, updated_ts=now)
        with self.state.tx():
            self.state.insert_order(row)          # POST'tan once commit
        meta = None
        if req.role in ("entry", "exit"):
            meta = {"order_ts": now}
            if quote and self.quote_fn is not None:
                try:
                    q = self.quote_fn(req.pair)                 # 3.5: tek deneme, <= 0.5 sn; hata = None
                except Exception:  # noqa: BLE001 - olcum emri hicbir zaman durdurmaz
                    q = None
                if q:
                    meta.update(q)
            self._put_meta(cid, meta)
        res = self._send(req)
        if res is None:
            return self._unknown_path(row, req)
        if meta is not None and self.live_mode:
            meta["order_ack_ts"] = self.clock.now()
        out = self._apply_result(row, res, None)
        return self._after(out, trade_id)

    def _existing(self, row: OrderRow) -> SubmitOutcome:
        if row.status in ("pending", "unknown"):
            out = self._resolve_row(row)
            return out
        o = self._outcome(row, None, "duplicate_adopted" if row.status in _OK else None)
        return o

    def _unknown_path(self, row: OrderRow, req: OrderRequest) -> SubmitOutcome:
        row = self._upd(row.client_id, status="unknown")
        if self.live_mode:
            return self._unknown_path_live(row, req)
        attempts = row.attempts
        while True:
            ok, bo = self._query(req.pair, req.client_id)
            if not ok:
                self._block("order_unknown")
                return self._outcome(row, None, "query_uncertain")
            if bo is not None:
                return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)
            if attempts >= self.max_attempts - 1:
                return self._fail(row)
            self.clock.sleep(self.unknown_grace_s)
            ok, bo = self._query(req.pair, req.client_id)
            if not ok:
                self._block("order_unknown")
                return self._outcome(row, None, "query_uncertain")
            if bo is not None:
                return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)
            attempts += 1
            row = self._upd(row.client_id, attempts=attempts)
            res = self._send(req)
            if res is not None:
                return self._after(self._apply_result(row, res, "resent_once"), row.trade_id)
            if attempts >= self.max_attempts - 1:
                return self._fail(row)

    def _unknown_path_live(self, row: OrderRow, req: OrderRequest) -> SubmitOutcome:
        """11 §6.4: iki sorgu (arada unknown_grace_s), KOR YENIDEN GONDERIM YOK. Giris: 'emir yok' ise satir `unknown` kalir
        (pencere dolana dek); diger roller: failed."""
        for i in range(2):
            if i:
                self.clock.sleep(self.unknown_grace_s)
            ok, bo = self._query(req.pair, req.client_id)
            if not ok:
                self._block("order_unknown")
                return self._outcome(row, None, "query_uncertain")
            if bo is not None:
                return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)
        if row.role == "entry":
            return self._entry_pending_or_fail(row)
        return self._fail(row)

    def _exchange_has_position(self, pair: str) -> bool:
        try:
            return any(p.pair == pair for p in self.broker.positions())
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001 - okunamadi: pozisyon var sayilir (muhafazakar)
            log.warning("positions okunamadi: %r", e)
            return True

    def _entry_pending_or_fail(self, row: OrderRow) -> SubmitOutcome:
        age = (self.clock.now() - row.created_ts).total_seconds()
        if age >= self.entry_resolve_window_s and not self._exchange_has_position(row.pair):
            return self._fail(row)
        self._block("order_unknown")
        return self._outcome(row, None, "entry_unknown_pending")

    def _fail(self, row: OrderRow) -> SubmitOutcome:
        row = self._upd(row.client_id, status="failed", detail=row.detail or "unknown_unresolved")
        out = self._outcome(row, None, "failed")
        return self._after(out, row.trade_id)

    def _block(self, reason: str) -> None:
        self.state.block_add(reason)          # DD-2 D6: kume; baska nedeni ezmez

    def _after(self, out: SubmitOutcome, trade_id: int | None) -> SubmitOutcome:
        """Rol bazli yan etkiler (basarisizlik ve kabul)."""
        row = out.order
        if row.role == "entry" and out.status == "failed" and row.status == "failed":
            self._entry_failed(row)
        elif row.role == "exit":
            self._exit_effects(row, out)
        return out

    def _entry_failed(self, row: OrderRow) -> None:
        p = self.state.get_position(row.trade_id) if row.trade_id is not None else None
        if p is not None and p.status == "opening" and self.close_unopened_fn is not None:
            self.close_unopened_fn(p, self.clock.now())       # canli: defter duzeltmesi + _entry_events temizligi motorda
            p = None
        with self.state.tx():
            if p is not None and p.status == "opening":
                self.state.update_position(p.trade_id, status="closed", exit_reason="other", closed_ts=self.clock.now())
            self.state.block_add("order_unknown")
        log.error("giris emri basarisiz: %s", row.client_id)

    def _exit_effects(self, row: OrderRow, out: SubmitOutcome) -> None:
        if row.trade_id is None:
            return
        p = self.state.get_position(row.trade_id)
        if p is None or p.status == "closed":
            return
        if self.live_mode and (out.status == "rejected" or (out.status == "failed" and row.status == "failed")):
            # 11 §8 L3c / F16: reddedilen, iptal/suresi dolan (kismi dahil) ya da iki sorguda da bulunamayan cikis:
            # `closing`te beklemez, `open`a doner ve deneme sayilir
            self._revert_exit(row)
            return
        if out.ok or out.status == "failed":
            # kabul: closing; basarisiz: closing kalir, resolve_unresolved yeniden dener
            if p.status != "closing" or p.exit_client_id != row.client_id:
                with self.state.tx():
                    self.state.update_position(p.trade_id, status="closing", exit_client_id=row.client_id)

    def _resolve_row(self, row: OrderRow) -> SubmitOutcome:
        req = self._req_from_row(row)
        if self.live_mode and row.role == "entry":
            return self._resolve_entry_live(row, req)
        out = self._unknown_path(row, req)
        return out

    def _resolve_entry_live(self, row: OrderRow, req: OrderRequest) -> SubmitOutcome:
        """Her tur tek sorgu; bulunursa dolum uygulanir, yoksa pencere dolana ve borsa duzlesene dek `unknown`."""
        if row.status != "unknown":
            row = self._upd(row.client_id, status="unknown")
        ok, bo = self._query(req.pair, req.client_id)
        if not ok:
            self._block("order_unknown")
            return self._outcome(row, None, "query_uncertain")
        if bo is not None:
            return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)
        return self._entry_pending_or_fail(row)

    # ------------------------------------------------------------------ giris / cikis
    def submit_entry(self, intent: Intent, trade_id: int, quote: bool = False) -> SubmitOutcome:
        if intent.kind != "entry":
            raise ValueError("intent.kind 'entry' olmali")
        if intent.qty is None or not intent.qty > 0:
            raise ValueError("qty > 0 olmali")
        rules = self.rules_fn(intent.pair)
        if not is_multiple(intent.qty, rules.step):
            raise ValueError(f"qty adimin kati degil: {intent.qty} / {rules.step}")
        cid = make_client_id(self.bot, "entry", intent.pair, intent.side, intent.signal_bar_close_ts, 0)
        req = OrderRequest(client_id=cid, pair=intent.pair, role="entry",
                           order_side=order_side_for(intent.side, "entry"), qty=intent.qty, trigger_price=None,
                           reduce_only=False, leverage=intent.leverage, signal_bar_close_ts=intent.signal_bar_close_ts,
                           created_ts=self.clock.now())
        if intent.leverage is not None:
            try:
                self.broker.prepare(intent.pair, intent.leverage)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                return self._prepare_failed(req, trade_id, e)
        return self._submit(req, 0, trade_id, quote)

    def _prepare_failed(self, req: OrderRequest, trade_id: int, e: Exception) -> SubmitOutcome:
        now = self.clock.now()
        row = OrderRow(client_id=req.client_id, pair=req.pair, role=req.role, order_side=req.order_side,
                       qty=req.qty, trigger_price=None, reduce_only=False, status="failed",
                       signal_bar_close_ts=req.signal_bar_close_ts, seq=0, attempts=0, trade_id=trade_id,
                       broker_order_id=None, detail=f"prepare_failed:{type(e).__name__}", created_ts=now, updated_ts=now)
        with self.state.tx():
            self.state.insert_order(row)
        return self._after(SubmitOutcome(False, "failed", row, None, "prepare_failed"), trade_id)

    def submit_exit(self, pos: Position, reason: str, at: datetime, quote: bool = False) -> SubmitOutcome:
        if pos.qty is None or not pos.qty > 0:
            raise ValueError("pozisyon qty yok")
        cid = make_client_id(self.bot, "exit", pos.pair, pos.side, at, 0)
        req = OrderRequest(client_id=cid, pair=pos.pair, role="exit", order_side=order_side_for(pos.side, "exit"),
                           qty=self._eff_qty(pos), trigger_price=None, reduce_only=True, leverage=None,
                           signal_bar_close_ts=at, created_ts=self.clock.now())
        self._pupd(pos.trade_id, exit_reason=reason)
        out = self._submit(req, 0, pos.trade_id, quote)
        if out.status == "failed" and out.order.status == "failed":
            self._exit_failed_effects(pos)
        return out

    def market_exit(self, pos: Position, reason: str, at: datetime):
        """Canli: stop/mutabakat yollarindaki piyasa cikislari motorun `_submit_exit`'inden (hemen poll + ban penceresi) gecer."""
        if self.exit_fn is not None:
            return self.exit_fn(pos, reason, at)
        return self.submit_exit(pos, reason, at)

    def _count_exit_failure(self, trade_id: int) -> int:
        """F16: reddedilen / bulunamayan / kismi cikis denemesi sayilir; limite varinca exit_unknown + CRIT."""
        n = int(self.state.kv_get(f"exit_retry:{trade_id}", 0)) + 1
        with self.state.tx():
            self.state.kv_set(f"exit_retry:{trade_id}", n)
        if n >= _EXIT_RETRY_LIMIT:
            p = self.state.get_position(trade_id)
            if p is not None:
                self._exit_failed_effects(p)
        return n

    def _revert_exit(self, row: OrderRow) -> None:
        """`closing` pozisyonu `open`a dondur (cikis satiri sonuclanmadi) ve denemeyi say."""
        if row.trade_id is None:
            return
        p = self.state.get_position(row.trade_id)
        if p is None or p.status == "closed":
            return
        if p.status == "closing" and p.exit_client_id == row.client_id:
            with self.state.tx():
                self.state.update_position(p.trade_id, status="open", exit_client_id=None, exit_reason=None)
        self._count_exit_failure(p.trade_id)

    def _exit_failed_effects(self, pos: Position) -> None:
        n = int(self.state.kv_get(f"exit_retry:{pos.trade_id}", 0))
        if n >= _EXIT_RETRY_LIMIT:
            self.state.block_add("exit_unknown")
            log.critical("cikis emri cozulemedi: trade %s (stop pozisyonu korur)", pos.trade_id)

    # ------------------------------------------------------------------ stop
    def _stop_request(self, pos: Position, price: float, seq: int) -> OrderRequest:
        cid = make_client_id(self.bot, "stop", pos.pair, pos.side, pos.signal_bar_close_ts, seq)
        return OrderRequest(client_id=cid, pair=pos.pair, role="stop", order_side=order_side_for(pos.side, "stop"),
                            qty=self._eff_qty(pos), trigger_price=price, reduce_only=True, leverage=None,
                            signal_bar_close_ts=pos.signal_bar_close_ts, created_ts=self.clock.now())

    def place_initial_stop(self, pos: Position, t_fill: datetime | None = None) -> SubmitOutcome:
        """t_fill verilirse (canli, 11 §6.4 madde 3) stop suresi siniri: ikinci deneme yalniz now - t_fill <= deadline - 5."""
        if pos.qty is None or not pos.qty > 0:
            raise ValueError("pozisyon qty yok")
        tick = self.stop_tick(pos)
        price = round_tight(pos.initial_stop, pos.side, tick)
        out = self._stop_attempt(pos, price, 0)
        if out.ok:
            return out
        if t_fill is not None:
            return self._stop_deadline_path(pos, price, out, t_fill)
        would = out.note == "would_trigger"
        if not would:
            log.warning("ilk stop kurulamadi (%s), bir kez daha deneniyor", out.note)
            out = self._stop_attempt(pos, price, 1)
            if out.ok:
                return out
            would = out.note == "would_trigger"
        log.critical("stop kurulamadi (%s): trade %s kapatiliyor", out.note, pos.trade_id)
        cur = self.state.get_position(pos.trade_id) or pos
        self.market_exit(cur, "other", self.clock.now())
        if not would:      # BT-1: would_trigger piyasa olayi, kilit yazmaz
            self._block("stop_failed")
            self.note_stop_failed(pos.trade_id)
        return SubmitOutcome(False, out.status, out.order, out.result, "would_trigger_closed" if would else "stop_failed_closed")

    def _stop_deadline_path(self, pos: Position, price: float, out: SubmitOutcome, t_fill: datetime) -> SubmitOutcome:
        would = out.note == "would_trigger"
        if not would and (self.clock.now() - t_fill).total_seconds() <= self.stop_deadline_s - 5.0:
            log.warning("ilk stop kurulamadi (%s), yeni kimlikle bir kez daha deneniyor", out.note)
            out = self._stop_attempt(pos, price, 1)
            if out.ok:
                return out
            would = out.note == "would_trigger"
        log.critical("stop kurulamadi (%s): trade %s piyasada kapatiliyor", out.note, pos.trade_id)
        cur = self.state.get_position(pos.trade_id) or pos
        self.market_exit(cur, "other", self.clock.now())
        if not would:
            self._block("stop_failed")
            self.note_stop_failed(pos.trade_id)
        return SubmitOutcome(False, out.status, out.order, out.result, "would_trigger_closed" if would else "stop_failed_closed")

    def _stop_attempt(self, pos: Position, price: float, seq: int) -> SubmitOutcome:
        req = self._stop_request(pos, price, seq)
        if seq != pos.stop_seq or self.state.get_order(req.client_id) is None:
            self._pupd(pos.trade_id, stop_seq=seq)
        out = self._submit(req, seq, pos.trade_id)
        if out.ok:
            self._pupd(pos.trade_id, stop_seq=seq, stop_client_id=req.client_id)
        return out

    def replace_stop(self, pos: Position, new_stop: float) -> SubmitOutcome:
        if pos.qty is None or not pos.qty > 0:
            raise ValueError("pozisyon qty yok")
        tick = self.stop_tick(pos)
        new = round_tight(new_stop, pos.side, tick)
        tighter = new > pos.current_stop if pos.side == "long" else new < pos.current_stop
        if not tighter:
            row = self.state.get_order(pos.stop_client_id) if pos.stop_client_id else None
            if row is None:
                now = self.clock.now()
                row = OrderRow(client_id=pos.stop_client_id or "", pair=pos.pair, role="stop",
                               order_side=order_side_for(pos.side, "stop"), qty=pos.qty,
                               trigger_price=pos.current_stop, reduce_only=True, status="accepted",
                               signal_bar_close_ts=pos.signal_bar_close_ts, seq=pos.stop_seq, attempts=0,
                               trade_id=pos.trade_id, broker_order_id=None, detail=None, created_ts=now, updated_ts=now)
            return SubmitOutcome(True, "accepted", row, None, "not_tighter")
        seq = pos.stop_seq + 1
        req = self._stop_request(pos, new, seq)
        self._pupd(pos.trade_id, stop_seq=seq)     # kimlik POST'tan once kalici
        out = self._submit(req, seq, pos.trade_id)
        if not out.ok:
            if out.note == "would_trigger":
                return out
            log.warning("stop guncellenemedi (%s): eski stop duruyor", out.note)
            return out
        self._pupd(pos.trade_id, current_stop=new, stop_client_id=req.client_id)
        old = pos.stop_client_id
        if old and old != req.client_id:
            try:
                self.broker.cancel(pos.pair, old)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                if _cancel_gone(e):
                    row = self.state.get_order(old)
                    if row is not None and row.status == "accepted":
                        self._upd(old, status="canceled", detail="gone_on_cancel")
                else:
                    log.warning("eski stop iptal edilemedi %s: %r", old, e)
            else:
                if self.live_mode:                  # DD-2 D10: iptal edilen eski stop satiri `accepted` kalmaz (kagit degismez)
                    row = self.state.get_order(old)
                    if row is not None and row.status == "accepted":
                        self._upd(old, status="canceled", detail="replaced_by_tighter_stop")
        return out

    # ------------------------------------------------------------------ hedef (24.11: bekleyen emir)
    def target_price(self, pos: Position) -> float | None:
        """Bekleyen hedef emrinin tetik fiyati: planlanan hedef, tick'e GIRISE dogru (kolay dolum; borsa `round_target_easy` ile ayni):
        long'da asagi, short'ta yukari. Hedef yoksa/sonsuzsa None."""
        t = pos.planned_target
        if t is None or isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not t > 0:
            return None
        tick = self.stop_tick(pos)
        return floor_step(float(t), tick) if pos.side == "long" else ceil_step(float(t), tick)

    def _target_request(self, pos: Position, price: float, seq: int) -> OrderRequest:
        cid = make_client_id(self.bot, "target", pos.pair, pos.side, pos.signal_bar_close_ts, seq)
        return OrderRequest(client_id=cid, pair=pos.pair, role="target", order_side=order_side_for(pos.side, "target"),
                            qty=self._eff_qty(pos), trigger_price=price, reduce_only=True, leverage=None,
                            signal_bar_close_ts=pos.signal_bar_close_ts, created_ts=self.clock.now())

    def next_target_seq(self, pos: Position) -> int:
        seqs = [r.seq for r in self.state.orders_for_trade(pos.trade_id) if r.role == "target"]
        return (max(seqs) + 1) if seqs else 0

    def place_target(self, pos: Position, seq: int | None = None) -> SubmitOutcome | None:
        """Bekleyen hedef emri (reduceOnly; kagit: hedef emri, canli: TAKE_PROFIT_MARKET). Stop gibi satir POST'tan once kalici
        yazilir; kimlik (rol `t`, seq) tekrar gonderimde ayni kalir. Hedef fiyati yoksa None. Basarisizlik pozisyonu KAPATMAZ
        (hedef koruyucu degil; motor `bar_close` yedegine doner)."""
        if pos.qty is None or not pos.qty > 0:
            raise ValueError("pozisyon qty yok")
        price = self.target_price(pos)
        if price is None:
            return None
        seq = self.next_target_seq(pos) if seq is None else seq
        return self._submit(self._target_request(pos, price, seq), seq, pos.trade_id)

    def cancel_target(self, pos: Position, cid: str, why: str) -> bool:
        """Hedef emrini iptal eder; canlida satir `accepted` kalmaz. True: iptal gonderildi."""
        try:
            self.broker.cancel(pos.pair, cid)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            if _cancel_gone(e):
                row = self.state.get_order(cid)
                if row is not None and row.status == "accepted":
                    self._upd(cid, status="canceled", detail="gone_on_cancel")
                return True
            log.warning("hedef iptal edilemedi %s: %r", cid, e)
            return False
        if self.live_mode:
            row = self.state.get_order(cid)
            if row is not None and row.status == "accepted":
                self._upd(cid, status="canceled", detail=why)
        return True

    def cancel_resting(self, pos: Position) -> None:
        cids: list[str] = []
        if pos.stop_client_id:
            cids.append(pos.stop_client_id)
        for r in self.state.orders_for_trade(pos.trade_id):
            if r.role in ("stop", "target") and r.status == "accepted" and r.client_id not in cids:
                cids.append(r.client_id)
        for cid in cids:
            try:
                self.broker.cancel(pos.pair, cid)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                if _cancel_gone(e):                                 # emir borsada yok: satir `accepted` kalmaz
                    row = self.state.get_order(cid)
                    if row is not None and row.status == "accepted":
                        self._upd(cid, status="canceled", detail="gone_on_cancel")
                    continue
                log.warning("iptal basarisiz %s: %r", cid, e)
                continue
            if self.live_mode and _cid_is_target(cid):             # 24.11: kapanista iptal edilen hedef satiri `accepted` kalmaz
                row = self.state.get_order(cid)
                if row is not None and row.status == "accepted":
                    self._upd(cid, status="canceled", detail="position_closed")

    # ------------------------------------------------------------------ cozum
    def resolve_unresolved(self) -> list[SubmitOutcome]:
        outs: list[SubmitOutcome] = []
        for row in self.state.unresolved_orders():
            out = self._resolve_row(row)
            if row.role == "stop" and out.ok and row.trade_id is not None:
                self._adopt_stop(row)
            outs.append(out)
        outs.extend(self._resolve_in_flight_live() if self.live_mode else self._retry_failed_exits())
        return outs

    # 11 §8 L3c: canli `opening`/`closing` pozisyonlarin yolda kalmis piyasa emirleri (her tur, tek sorgu)
    def _resolve_in_flight_live(self) -> list[SubmitOutcome]:
        outs: list[SubmitOutcome] = []
        for p in self.state.open_positions():
            if p.status == "opening":
                for r in self.state.orders_for_trade(p.trade_id):
                    if r.role == "entry" and r.status == "accepted":
                        o = self._requery_entry(r)
                        if o is not None:
                            outs.append(o)
            elif p.status == "closing":
                o = self._resolve_closing(p)
                if o is not None:
                    outs.append(o)
        return outs

    def _requery_entry(self, row: OrderRow) -> SubmitOutcome | None:
        ok, bo = self._query(row.pair, row.client_id)
        if not ok:
            return None                                   # sorgu HATASI: eylem yok
        if bo is None:
            row = self._upd(row.client_id, status="failed", detail="gone_on_query")
            return self._after(self._outcome(row, None, "failed"), row.trade_id)
        if bo.status == "new":
            return None                                   # hala calisiyor: poll'a birak
        return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)

    def _resolve_closing(self, p: Position) -> SubmitOutcome | None:
        """`closing` pozisyon: cikis satiri failed/rejected/canceled/expired ya da yolda kalmis (accepted + terminal/yok) ise `open`a
        doner. Sorgu HATASI eylemsizdir. Dolmus satir poll/L3'e birakilir."""
        row = self.state.get_order(p.exit_client_id) if p.exit_client_id else None
        if row is None:
            with self.state.tx():
                self.state.update_position(p.trade_id, status="open", exit_client_id=None, exit_reason=None)
            self._count_exit_failure(p.trade_id)
            return None
        if row.status in ("pending", "unknown", "filled"):
            return None                                   # pending/unknown: unresolved dongusu; filled: olay/L3
        if row.status in ("rejected", "canceled", "expired"):
            self._revert_exit(row)
            return self._outcome(row, None, "exit_not_filled")
        ok, bo = self._query(row.pair, row.client_id)     # failed | accepted
        if not ok:
            return None
        if bo is None:
            if row.status == "accepted":
                row = self._upd(row.client_id, status="failed", detail="gone_on_query")
            self._revert_exit(row)
            return self._outcome(row, None, "exit_not_found")
        if bo.status == "new":
            if row.status == "failed":
                row = self._upd(row.client_id, status="accepted")
            return None
        if bo.status == "filled" and row.status == "accepted":
            return None                                   # dolum olayi poll'dan / L3'ten gelir
        return self._after(self._adopt(row, bo, "adopted_after_unknown"), row.trade_id)

    def _adopt_stop(self, row: OrderRow) -> None:
        p = self.state.get_position(row.trade_id) if row.trade_id is not None else None
        if p is None or p.status == "closed" or row.trigger_price is None:
            return
        with self.state.tx():
            if p.stop_client_id is None or row.seq >= p.stop_seq:
                tighter = (row.trigger_price > p.current_stop) if p.side == "long" else (row.trigger_price < p.current_stop)
                f: dict = {"stop_client_id": row.client_id, "stop_seq": max(p.stop_seq, row.seq)}
                if row.seq > 0 and tighter:
                    f["current_stop"] = row.trigger_price
                self.state.update_position(p.trade_id, **f)

    def _retry_failed_exits(self) -> list[SubmitOutcome]:
        outs: list[SubmitOutcome] = []
        for p in self.state.open_positions():
            if p.status != "closing" or not p.exit_client_id:
                continue
            row = self.state.get_order(p.exit_client_id)
            if row is None or row.status != "failed":
                continue
            n = int(self.state.kv_get(f"exit_retry:{p.trade_id}", 0))
            if n >= _EXIT_RETRY_LIMIT:
                self._exit_failed_effects(p)
                continue
            with self.state.tx():
                self.state.kv_set(f"exit_retry:{p.trade_id}", n + 1)
            row = self._upd(row.client_id, status="unknown", attempts=0)
            out = self._resolve_row(row)
            if out.status == "failed" and out.order.status == "failed":
                self._exit_failed_effects(self.state.get_position(p.trade_id) or p)
            outs.append(out)
        return outs
