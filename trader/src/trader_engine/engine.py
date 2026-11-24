"""Engine (05 §5): paper, backtest ve (Faz B) canli icin ayni dongu. Fark yalniz Broker/MarketView/Clock/SignalSource
enjeksiyonudur. Sira her karar adiminda: parametre yenile -> cikislar -> stop guncelle -> girisler. Risk sayisi yoktur."""
from __future__ import annotations

import logging
import math
import os
from collections import Counter, OrderedDict
from contextlib import nullcontext
from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from trader_core import exit_modes as XM
from trader_core import ledger as L
from trader_core import risk as K
from trader_core.signals import SignalParams

from .bars import arm_floor_tf, arm_is_tf_close, arm_tf_delta, floor_tf, is_tf_close, tf_delta
from .brokers.base import Broker
from .clock import Clock
from .config import EngineConfig
from .arm_guard import asset_class, load_arms_off, session_tag
from .errors import ClockError, ConfigError, DataError, EngineExit, FailClosed, StateError
from .holdout import check_holdout
from .gates import EntryGate, EntryOutcome, NoVeto, VetoSource, _tf_of, entry_leverage
from .gates import aday_ozgu_red as AG_ADAY_OZGU
from .killswitch import Killswitch
from .pause import EntryPause
from . import shadow as SH
from .marketdata.sources import MarketView, MinuteStep
from .mtm import MtmRecorder
from .numeric import round_tight
from .order_manager import EXIT_RETRY_LIMIT, OrderManager, SubmitOutcome, make_client_id
from .position_manager import (ExitContext, ExitDecision, apply_entry_fill, apply_exit_fill, apply_exit_modes, apply_funding,
                               build_trade_entry, build_trade_exit, close_position, evaluate_exit, exec_fields, exec_payload,
                               exit_mode_of, fill_risk_violation, partial_due, update_excursion)
from .reconcile import Reconciler, ReconcileReport
from .state import OrderRow, StateStore, iso_z
from .status import StatusWriter
from .strategies.base import Strategy, StrategyError
from .strategies.registry import check_param_keys, get_strategy, make_label, parse_label
from .arm_quarantine import ArmQuarantine, KV_KEY as QUARANTINE_KV, take_release_request
from .tur_koruyucu import TurKoruyucu
from .strategy_runner import MultiArmSignalSource, SignalFrame, SignalSource, WindowedSignalSource
from .types import BrokerEvent, Fill, Intent, OrderRequest, Position, order_side_for

log = logging.getLogger("engine")
PARTIAL_RETRY_MAX = 5                                           # gecici retlerde kismi emir yeniden deneme ust siniri (bar basina bir)
_PARTIAL_TRANSIENT = ("exchange_ban", "rate_limited", "order_rate_cap", "exchange_-1021", "exchange_auth", "weight_high",
                      "rules_stale", "rules_missing")           # emir borsada YOK; kalici ret (miktar/min notional/kural) degil

ENGINE_VERSION = "05.1"
KALDIRILAN_KOLLAR = ("C1",)          # CT/C1 ayriligi: kullanici karariyla kaldirilan kurulumlar (acik pozisyonlari baslangicta kapatilir)
_REASONS = ("stop", "target", "trail_stop", "regime_flip", "time_stop", "manual", "force_exit", "liquidation", "other")
_STATUS_COUNTERS = ("callback_errors", "data_gaps", "ledger_errors", "outbox_failed", "unknown_orders", "mark_fallbacks",
                    "minute_gaps", "funding_missing", "exit_data_gap")
STARTUP_MAX_AGE_S = 300          # acilis kapisi: son kapanmis 1m (last+mark) en fazla bu kadar eski olabilir
EXIT_STARTUP_GATE = 7
# DD-6 (O1): canli `advance_to` veri hatasi dayanikliligi. Hata = cikis degil: ussel geri cekilme, N ardisik hatada girisler kapanir.
ADVANCE_BACKOFF_BASE_S = 2.0
ADVANCE_BACKOFF_CAP_S = 30.0
ADVANCE_ERRORS_ENTRIES_OFF = 5
# DD-6 (D11): karar adimi hata verirse ayni barin yazilim cikislari icin sinirli yeniden deneme (canli yol)
DECISION_EXIT_RETRIES = 3
DECISION_EXIT_RETRY_BASE_S = 5.0
# DD-6 (O3): 24 saatte ikinci (ayri pozisyonda) stop_failed -> kalici duraklatma
STOP_FAILED_REPEAT_WINDOW_S = 86_400.0
_GATE_QUOTE_MAX_AGE_S = 5.0   # D17 sorgusunun `order_quote` icin yeniden kullanilabilecegi en gec yas (ayni giris denemesi)
# DD-6 (D17): yalniz testnet; testnet fiyati planned_entry'den bu orandan fazla saparsa giris atlanir
TESTNET_PRICE_DIVERGENCE_MAX = 0.005
# DD-6 (D1): `opening` + borsada pozisyon gorulurse protect_first en sik bu aralikla
OPENING_PROTECT_MIN_GAP_S = 5.0
PAPER_SYSTEM_MODES = ("paper", "live")           # 23.11 kullanici karari: canli = kagit (ayni strateji/kapi/kume/risk sistemi)
FEED_MODES = ("paper", "testnet", "live")        # 11 §6.1: "feed'li canli dongu" (benzetimli broker ayrimi: is_paper)
_BROKER_REASONS = ("exchange_auth", "exchange_unknown_code", "working_type_unverified", "exchange_unreachable",
                   "exchange_rate_limited")
SHADOW_BUDGET_S = 5.0            # WP-3 5.2: `_shadow_step` zaman butcesi (ciftler arasinda denetlenir)
_EXEC_MEM_MAX = 256              # WP-3: bellekteki `decision_price` kayitlari


def _pos_finite(x) -> bool:
    """DD-11: sayi, sonlu ve > 0 (bool/None/str degil)."""
    return (not isinstance(x, bool)) and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


@dataclass(frozen=True)
class RecoveryReport:
    replayed_minutes: int
    replayed_decisions: int
    unresolved_orders: int
    reconcile: ReconcileReport


@dataclass(frozen=True)
class RunSummary:
    steps: int
    decisions: int
    trades_opened: int
    trades_closed: int
    open_at_end: tuple[int, ...]
    counters: dict


_TF_RANK = {"15m": 1, "1h": 2, "4h": 3, "1d": 4}      # giris sirasi: buyuk zaman dilimi once
_TF_SECS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


class Engine:
    def __init__(self, cfg: EngineConfig, *, clock: Clock, view: MarketView, broker: Broker, ledger: L.Ledger,
                 state: StateStore, signals: SignalSource, strategy: Strategy, veto: VetoSource, kill: Killswitch,
                 status: StatusWriter | None, orders: OrderManager | None = None, entry_ref_fn=None,
                 strict: bool = False, tick_fn=None, pause: EntryPause | None = None, reconciler=None,
                 ladder=None) -> None:
        if cfg.mode == "live" and ladder is None:
            raise ConfigError("mode='live': risk kademe denetimi (ladder) olmadan motor kurulamaz (12 §8.1)")
        self.cfg = cfg
        self.ladder = ladder
        self.clock = clock
        self.view = view
        self.broker = broker
        self.ledger = ledger
        self.state = state
        self.signals = signals
        self.strategy = strategy
        self.veto = veto
        self.kill = kill
        self._wallet_lock = False                      # DD-8 O4: tutus dosyaya yazilamadiysa bellek kilidi (surec omru boyunca)
        if pause is None and cfg.mode == "paper":
            # F10: goreli yol cwd'ye bagli kalmasin (systemd WorkingDirectory'ye guvenilmez): mutlak yola cevrilir (yalniz paper)
            pause = EntryPause(os.path.abspath(f"{cfg.pause_file}.{cfg.bot}"), clock,
                               audit_path=os.path.abspath(cfg.path("pause_audit.jsonl")), bot=cfg.bot)
        elif pause is None and cfg.mode in ("testnet", "live"):
            for fld in ("pause_file", "var_dir"):      # DD-8 E1: canlida goreli yol = acilmaz
                if not os.path.isabs(getattr(cfg, fld)):
                    raise ConfigError(f"relative_path:{fld}")
            pause = EntryPause(f"{cfg.pause_file}.{cfg.bot}", clock, audit_path=cfg.path("pause_audit.jsonl"), bot=cfg.bot)
        self.pause = pause
        self.status = status
        self.strict = strict
        rules_fn = broker.rules
        live = cfg.live
        self.orders = orders or OrderManager(cfg.bot, broker, state, clock, rules_fn)
        if not getattr(broker, "is_simulated", False):
            # 11 §6: canli yol (OrderManager bayraklari; kagit/backtest'te dokunulmaz)
            self.orders.live_mode = True
            self.orders.max_attempts = 1                    # DD-2 D10: canli yolda kor yeniden gonderim yok (ayar olu: 1'e sabit)
            if live is not None:
                self.orders.stop_deadline_s = float(live.stop_deadline_s)
                self.orders.entry_resolve_window_s = float(live.entry_resolve_window_s)
            self.orders.on_entry_adopted = self._on_adopted_entry
            self.orders.on_ban = self._note_ban
            self.orders.exit_fn = self._submit_exit                 # 11 §6.4/§8: piyasa cikislari tek yoldan (poll + ban penceresi)
            self.orders.close_unopened_fn = self._close_unopened    # giris penceresi kapanisi: defter duzeltmesi + _entry_events
        if tick_fn is not None:
            self.orders.tick_fn = tick_fn                    # legacy_compat: giris-ayi tarihsel tick
        self.gate = EntryGate(cfg, ledger, state, kill, veto, clock, broker, rules_fn, entry_ref_fn, pause, ladder)
        self.gate.symbol_blocked = lambda p: self.sembol_izleyici is not None and self.sembol_izleyici.is_blocked(p)   # 4f
        if cfg.mode in PAPER_SYSTEM_MODES:       # DD-12 WP-13: ders kapattigi kurulumlar (salt okunur dosya; yoksa hepsi acik); 23.11 kullanici karari: canli = kagit
            _arms_path = Path(cfg.ledger_path).parent / "arms_off.json"
            self.gate.arms_off = lambda: load_arms_off(_arms_path)
            if self.gate.korelasyon is not None:                        # 23.11 asama B: korelasyon matrisi market.sqlite barlarindan (saatte bir)
                self.gate.korelasyon.bars_fn = lambda p, tf, until, n: self.view.bars(p, tf, until, n)
            if self.gate.uzun_yon is not None:                          # fikir 7: 1d rejimi market.sqlite 4h barlarindan
                self.gate.uzun_yon.bars_fn = lambda p, tf, until, n: self.view.bars(p, tf, until, n)
            if cfg.etiket_kurallari:                                    # rejim etiketi kurali (sabit; girisi yalniz atlatabilir; docs/etiket-kurallari-spec.md)
                self.gate.etiket_cfg = cfg.etiket_kurallari
        self.reconciler = reconciler if reconciler is not None else self._make_reconciler()
        if getattr(signals, "last_exit_fn", False) is None:
            signals.last_exit_fn = self._last_exit            # type: ignore[attr-defined]
        self._c: Counter = Counter()
        self.tf: str = strategy.info.allowed_trigger_tfs[0]
        # DD-12 WP-11: bilesik strateji (price_action_lab_ml) karar adimini kendisi belirler (15 dk); `self.tf` parametre/ledger
        # zaman dilimi olarak kalir (1s). Tekli stratejilerde step_tf == tf: davranis bit bit ayni.
        self.step_tf: str = getattr(strategy, "decision_tf", None) or self.tf
        self._multi_tf: bool = self.step_tf != self.tf
        if self._multi_tf and getattr(signals, "position_fn", False) is None:
            signals.position_fn = self._position_for_arms       # type: ignore[attr-defined]
        self._params_map: dict | None = None
        self._exit_seen: dict[int, datetime] = {}                 # canli telafi: trade_id -> en son degerlendirilen TF siniri (bellek)
        self._mode_flags: dict[str, int] = {}                  # etkin defter surumunun cikis kipi bayraklari (exit_breakeven/exit_partial)
        self._act_id: int | None = None
        self._version_id = 0
        self._params_ok = False
        self._active_tf: str | None = None
        self._consec_errors = 0
        self._consec: dict[str, int] = {}                       # canli: adim etiketi basina ardisik hata (merdiven)
        self._ban_seen: tuple | None = None                     # son islenen broker.last_ban belirteci
        self._stop = False
        self._last_now: datetime | None = None
        self._last_minute: datetime | None = None
        self._last_marks: dict[str, tuple[float, datetime]] = {}   # pair -> (son kapanmis 1m last_c, bar kapanis ts); yalniz status.json icin
        self._last_decision: datetime | None = None
        self._last_candle_open: datetime | None = None
        self._last_pre = None
        self._adv_errors = 0                                   # DD-6 O1
        self._adv_next_try: datetime | None = None
        self._exit_retry: dict | None = None                   # DD-6 D11
        self._last_opening_protect: datetime | None = None     # DD-6 D1
        self._last_reconcile: datetime | None = None
        self._entry_events: dict[int, object] = {}
        self._started = False
        self.quarantine: ArmQuarantine | None = getattr(signals, "quarantine", None)   # 4b: kurulum kod hatasi karantinasi
        self.sembol_izleyici = None                             # 4f: sembol_izleme.SembolIzleyici (cli kurar); None = kapali
        self._tur_koruyucu = TurKoruyucu(self)                  # 4c
        self._ban_until: datetime | None = None
        self._exit_throttle: dict[int, datetime] = {}
        self._naked_rows: list[dict] = []
        self._in_drain = 0
        # WP-3 (defter-ek-alanlar): YALNIZ KAYIT. Bu durum bellekte tutulur, durum deposuna YAZILMAZ ve hicbir karari etkilemez.
        self._dec_ts: "OrderedDict[int, tuple[str, datetime]]" = OrderedDict()   # trade_id -> (cikis client_id, karar mumu kapanis zamani)
        self._dec_price: "OrderedDict[int, tuple[str, float]]" = OrderedDict()   # trade_id -> (cikis client_id, karar mumu kapanisi)
        self._regime_mem: dict[str, tuple[datetime, str]] = {}                   # cift -> (karar adimi D, hizali 4s kosul etiketi)
        self._gate_quote: tuple[str, datetime, dict | None] | None = None        # D17 sorgusu (cift, ts, sonuc) - tek GET paylasimi
        self._shadow_ctx: tuple | None = None                                    # (D, frames, params) son karar adimi
        self._rec = {"shadow": {"rows": 0, "errors": 0, "budget_skips": 0, "tf15_holdout_wait": 0, "last_step_ms": 0.0},
                     "mtm": {"rows": 0, "errors": 0}, "exec": {"dropped": 0, "quote_errors": 0}}
        simulated = bool(getattr(broker, "is_simulated", False))
        self.mtm = MtmRecorder(None if cfg.mode == "backtest" else self._write_equity_mark,
                               src="sim" if simulated else "exchange", keep=cfg.mode == "backtest",
                               enabled=bool(cfg.mtm_marks))
        if not simulated and live is not None and live.order_quote:
            self.orders.quote_fn = self._order_quote
        if not simulated:
            self.orders.on_stop_failed = self._note_stop_failed     # DD-6 O3

    def _make_reconciler(self):
        if self.is_paper:
            return Reconciler(self.cfg, self.broker, self.state, self.ledger, self.orders, self.clock)
        try:
            from .reconcile_live import LiveReconciler
        except ImportError:
            log.warning("reconcile_live yok: canli mutabakat kagit alt kumesiyle (B5 bekleniyor)")
            return Reconciler(self.cfg, self.broker, self.state, self.ledger, self.orders, self.clock)
        return LiveReconciler(self.cfg, self.broker, self.state, self.ledger, self.orders, self.clock, self.kill,
                              self.pause, handle_events=lambda evs, now: self._handle_events(evs, None, now),
                              close_unopened=self._close_unopened)

    # ================================================================== yardimcilar
    def _set_clock(self, t: datetime) -> None:
        if hasattr(self.clock, "set_time") and t > self.clock.now():
            self.clock.set_time(t)                              # type: ignore[attr-defined]

    def _persist(self, old: Position, new: Position) -> None:
        diff = {f.name: getattr(new, f.name) for f in fields(Position)
                if f.name != "trade_id" and getattr(new, f.name) != getattr(old, f.name)}
        if diff:
            with self.state.tx():
                self.state.update_position(old.trade_id, **diff)

    def _mark_order(self, cid: str | None, status: str, detail: str | None = None) -> None:
        if not cid:
            return
        row = self.state.get_order(cid)
        if row is None or row.status in ("filled", "rejected", "canceled", "failed"):
            return
        f = {"status": status, "updated_ts": self.clock.now()}
        if detail:
            f["detail"] = detail
        with self.state.tx():
            self.state.update_order(cid, **f)

    def _block(self, reason: str) -> None:
        self.state.block_add(reason)          # DD-2 D6: kume; baska nedeni ezmez

    def _note_stop_failed(self, trade_id: int | None = None) -> None:
        """DD-6 O3: `stop_failed` olaylarini (pozisyon basina bir) 24 saat boyunca sayar; ikincisinde kalici duraklatma
        `stop_failed_repeat` (yalniz sunucuda CLI ile kalkar). Yalniz testnet/canli; kagit ve geri test degismez."""
        if self.is_paper or self.cfg.mode not in ("testnet", "live"):
            return
        try:
            now = self.clock.now()
            raw = self.state.kv_get("stop_failed_log") or {}
            keep: dict[str, str] = {}
            from .state import parse_iso_z
            for k, v in dict(raw).items():
                try:
                    if (now - parse_iso_z(v)).total_seconds() <= STOP_FAILED_REPEAT_WINDOW_S:
                        keep[str(k)] = v
                except (ValueError, TypeError):
                    continue
            keep.setdefault(str(trade_id) if trade_id is not None else f"?{iso_z(now)}", iso_z(now))
            with self.state.tx():
                self.state.kv_set("stop_failed_log", keep)
            if len(keep) >= 2 and self.pause is not None:
                log.critical("24 saatte %d stop_failed (%s): girisler kalici duraklatildi (stop_failed_repeat)",
                             len(keep), sorted(keep))
                self.pause.add("stop_failed_repeat", by="engine:stop_failed",
                               note=f"{len(keep)} stop_failed / 24h: trade {','.join(sorted(keep))}")
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001 - sayac hatasi korumayi geciktirmez
            log.error("stop_failed sayaci hatasi: %r", e)

    def _position_for_arms(self, pair: str):
        p = self.state.position_for_pair(pair)
        return None if p is None else (p.trigger_tf, p.entry_bar_open)

    def _last_exit(self, pair: str, D: datetime, tf: str | None = None):
        since = D - (arm_tf_delta(tf) if tf else tf_delta(self.tf))
        best = None
        for p in self.state.closed_positions_since(since):
            if p.pair == pair and p.closed_ts is not None and p.exit_reason and (best is None or p.closed_ts >= best[0]):
                best = (p.closed_ts, p.exit_reason)
        return best

    @property
    def is_paper(self) -> bool:
        return bool(getattr(self.broker, "is_simulated", False))

    def _outer_tx(self):
        """11 §6.1: benzetimli brokerda tek dis tx aynen; canlida YOK (her yazma grubu kendi tx'i)."""
        return self.state.tx() if self.is_paper else nullcontext()

    # ================================================================== gozlem
    def counters(self) -> dict:
        out = {k: 0 for k in _STATUS_COUNTERS}
        out.update(self._c)
        for src in (self.gate.counters, getattr(self.signals, "counters", None),
                    getattr(self.strategy, "counters", None)):
            if src:
                for k, v in src.items():
                    out[k] = out.get(k, 0) + v
        bc = getattr(self.broker, "counters", None)
        if callable(bc):
            for k, v in bc().items():
                out[k] = out.get(k, 0) + v
        try:
            out["unknown_orders"] = len(self.state.unresolved_orders())
        except StateError:
            pass
        return out

    def _live_gate_code(self, blocked, killed: bool) -> str:
        """Anlik kapi durumu (cift-bagimsiz kapilar; bayatlik karar adimina ozgudur)."""
        if self._params_ok is False and self._started:      # 11 §9.3: ilk kapi
            return "params_unavailable"
        try:
            h = self.ledger.entries_allowed()
            if not h.ok:
                return h.code
        except Exception:  # noqa: BLE001
            return "degraded"
        if blocked:
            return str(blocked)
        if killed:
            return "kill"
        if self.pause is not None and self.pause.active():
            return self.pause.code() or "paused"
        if getattr(self, "_wallet_lock", False):             # DD-8 O4: tutus dosyaya yazilamadi -> bellek kilidi
            return "paused"
        if self.ladder is not None:                          # 12 §8.3: duraklatmadan sonra
            gc = self.ladder.gate_code()
            if gc:
                return gc
        return "ok"

    def kill_state(self) -> str | None:
        if not self.kill.active():
            return None
        return "flat" if not self.state.open_positions() else "exiting"

    def _open_extra(self) -> dict:
        """Mutabakat icin acik pozisyon basina kasaya yansiyan ama defterde henuz olmayan kalemler (yalniz kagit): giris komisyonu,
        odenen fonlama (broker cuzdanindan duser, defter kapanista yazar), kismi cikisin brut K/Z'si ve komisyonu."""
        if not self.is_paper:
            return {}
        out: dict = {}
        try:
            bp = {b.pair: b for b in self.broker.positions()}
            for p in self.state.open_positions():
                if p.status not in ("open", "closing"):
                    continue
                b = bp.get(p.pair)
                d = {"fee_paid_entry": float(b.fee_paid_entry) if b is not None else float(p.fee_entry or 0.0),
                     "funding_paid": float(b.funding_paid) if b is not None else float(p.funding_paid or 0.0),
                     "partial_realized_usd": 0.0, "partial_fee_usd": 0.0}
                pk = self.state.kv_get(f"partial:{p.trade_id}")
                if isinstance(pk, dict) and pk.get("state") == "done":
                    sgn = 1.0 if p.side == "long" else -1.0
                    d["partial_realized_usd"] = sgn * (float(pk["price"]) - float(p.entry_price)) * float(pk["qty"])
                    d["partial_fee_usd"] = float(pk.get("fee") or 0.0)
                out[p.trade_id] = d
        except Exception as e:  # noqa: BLE001 - status yazimi bozulmaz; alanlar yoksa mutabakat 'atlandi' der
            log.warning("status: acik pozisyon ek alanlari okunamadi (%s)", type(e).__name__)
            return {}
        return out

    def status_fields(self) -> dict:
        now = self.clock.now()
        acct, stale = None, False
        try:
            acct = self.broker.account()
            self._last_acct = acct
        except Exception as e:  # noqa: BLE001  DD-7: yasak/ag hatasinda status.json yine yazilir; bayat bakiye taze gibi YAYINLANMAZ
            if self.is_paper:
                raise
            stale = True
            log.warning("status: hesap okunamadi (%s); wallet/equity None, account_stale", type(e).__name__)
        ds = self.state.kv_get("day_start:" + now.strftime("%Y-%m-%d"))
        blocked = self.state.kv_get("entries_blocked_reason")
        killed = self.kill.active()
        code = self._live_gate_code(blocked, killed)
        cand = self._last_candle_open
        if cand is None:
            try:
                rng = self.view.data_range(self.cfg.pairs[0], self.tf)
                cand = rng[1] if rng else None
            except Exception:  # noqa: BLE001
                cand = None
        return {
            "tf": self.tf, "param_version_id": self._version_id, "strategy_name": self.strategy.info.name,
            "strategy_version": self.strategy.info.version, "entries_blocked_reason": blocked, "gate_code": code,
            "entries_blocked_reasons": self.state.block_reasons(),          # DD-2: eklemeli; eski alan degismedi
            "entries_open": code == "ok",
            "kill": killed, "kill_state": self.kill_state(), "wallet": acct.wallet if acct else None,
            "equity": acct.equity if acct else None, "account_stale": stale,
            **self._stale_extra(stale),
            "day_start_equity": ds if ds is not None else (acct.equity if acct else None), "open_positions": self.state.open_positions(),
            "counters": {"rules_missing": 0, "data_stale": 0, **self.counters()}, "last_minute_ts": self._last_minute,
            "last_decision_close": self._last_decision, "last_candle_open": cand,
            "etiket_kurallari": self._etiket_status(),
            "cluster_counts": self.cluster_counts(),
            "last_marks": dict(self._last_marks),
            "open_extra": self._open_extra(),
            "records": self.records_block(),
            "pause": self._pause_status(),
            "risk_ladder": self._ladder_status(),
            "dayaniklilik": self._dayaniklilik_status(),
            **({} if self.is_paper else {"exchange": self._exchange_status()}),
        }

    def _stale_extra(self, stale: bool) -> dict:
        last = getattr(self, "_last_acct", None)
        if not stale or last is None:
            return {}
        return {"equity_last": last.equity, "account_at": last.ts}

    def _exchange_status(self) -> dict:
        h = {}
        try:
            h = dict(self.broker.health())
        except Exception:  # noqa: BLE001
            pass
        h["naked"] = list(self._naked_rows)
        return h

    def _pause_status(self) -> dict | None:
        if self.pause is None:
            return None
        return {"active": self.pause.active(), "holds": [asdict(h) for h in self.pause.holds()]}

    def _ladder_status(self) -> dict | None:
        if self.ladder is None:
            return None
        try:
            return self.ladder.status()
        except Exception as e:  # noqa: BLE001 - blok yazimi bozmaz
            log.warning("risk_ladder durum blogu uretilemedi: %r", e)
            return None

    def _wallet_cap_hold(self, note: str) -> None:
        """DD-8 O4: `wallet_above_expected` giris tutusu (`add` idempotent; ilk koken korunur). Tutus dosyaya yazilamazsa
        (add False doner ve tutus dosyada yok) surec acik kalir ama bellek kilidi tutulur: hicbir giris emri gonderilmez;
        her denetimde `add` yeniden denenir. Yalniz testnet/live (paper/backtest'te cagrilmaz)."""
        added = False
        held = False
        if self.pause is not None:
            try:
                added = bool(self.pause.add("wallet_above_expected", by="engine:wallet_cap", note=note))
            except Exception as e:  # noqa: BLE001
                log.error("pause.add basarisiz: %r", e)
            try:
                held = any(h.reason == "wallet_above_expected" for h in self.pause.holds())
            except Exception:  # noqa: BLE001
                held = False
        if added:
            log.critical("wallet_above_expected: girisler kapatildi (%s)", note)
        if not held and not self._wallet_lock:
            self._wallet_lock = True
            self.gate.memory_lock = "paused"
            log.critical("wallet_above_expected: tutus dosyaya yazilamadi; surec omru boyunca giris kilidi bellekte (%s)", note)

    def _wallet_cap_step(self, wallet: float) -> None:
        """DD-8 O4 (calisirken): motorun zaten okudugu hesap degeri (ek REST cagrisi YOK) sonlu ve > tavan ise tutus eklenir.
        Sonlu olmayan deger bu denetimde yok sayilir. Bellek kilidi varken `add` her turda yeniden denenir."""
        live = self.cfg.live
        if live is None or self.cfg.mode not in ("testnet", "live"):
            return
        over = math.isfinite(wallet) and wallet > float(live.expected_wallet_max)
        if over or self._wallet_lock:
            note = f"wallet={wallet} max={live.expected_wallet_max}"
            if over:
                self._wallet_cap_hold(note)
            elif self.pause is not None:
                try:
                    self.pause.add("wallet_above_expected", by="engine:wallet_cap", note="mem_lock_retry " + note)
                except Exception as e:  # noqa: BLE001
                    log.error("pause.add basarisiz: %r", e)

    def _ladder_step(self, now: datetime) -> None:
        """12 §8.2: kademe degerlendirmesi (kisma ladder icinde). Ozsermaye okunamazsa NaN verilir (kapi: equity_unreadable);
        hicbir istisna disari sizmaz. DD-8 O4: ayni hesap okumasi cuzdan tavani denetimine de beslenir (testnet/live)."""
        if self.ladder is None and self.cfg.mode not in ("testnet", "live"):
            return
        try:
            try:
                acct = self.broker.account()
                equity, wallet = float(acct.equity), float(acct.wallet)
            except Exception as e:  # noqa: BLE001
                log.warning("kademe icin hesap okunamadi: %r", e)
                equity = wallet = float("nan")
            try:
                self._wallet_cap_step(wallet)
            except Exception as e:  # noqa: BLE001
                log.critical("cuzdan tavani denetimi hatasi: %r", e)
            if self.ladder is None:
                return
            try:
                flat = not self.state.open_positions() and not self.state.unresolved_orders()
            except Exception:  # noqa: BLE001
                flat = False
            self.ladder.tick(now, equity, wallet, flat=flat)
        except Exception as e:  # noqa: BLE001
            self._c["ladder_errors"] += 1
            log.critical("kademe adimi hatasi: %r", e)

    def _etiket_status(self) -> dict | None:
        """status.json `etiket_kurallari`: sabit kural icin atlama ve veri-yok sayaclari. Yalniz kagit + yapilandirilmissa."""
        if not getattr(self.gate, "etiket_cfg", None):
            return None
        try:
            from trader_core import etiket_kurallari as EK
            c = self.gate.counters
            kur = {k: {"atladi": int(c.get("etiket_atladi:" + k, 0)), "veri_yok": int(c.get("etiket_veri_yok:" + k, 0))}
                   for k in EK.KURALLAR if EK.kural_acik_config(self.gate.etiket_cfg, k)}
            return {"kurallar": kur}
        except Exception:  # noqa: BLE001
            return None

    def cluster_counts(self) -> dict | None:
        """status.json `clusters` (DD-12 §4.1): kume basina acik + acilmakta pozisyon sayisi ve tavan; hesap geneli. Yalniz kagit."""
        if self.cfg.mode not in PAPER_SYSTEM_MODES or not self.cfg.clusters:
            return None
        held = [p.pair for p in self.state.open_positions()]
        out = {name: {"open": sum(1 for h in held if h in spec.pairs), "max": spec.max_positions}
               for name, spec in self.cfg.clusters.items()}
        res = {"account": {"open": len(held), "max": self.cfg.max_positions}, "clusters": out,
               "optional_waiting": int(self._c.get("optional_waiting", 0))}
        if self.cfg.arms or self.cfg.arm_max_positions:            # WP-11: kurulum basina acik pozisyon ve tavan
            from . import arm_guard as AG
            held_arms = [AG.arm_id_of(p.setup, p.trigger_tf) for p in self.state.open_positions()]
            ids = list(self.cfg.arms) or list(getattr(self.strategy, "arm_ids", ()))
            ids += [a for a in dict.fromkeys(held_arms) if a not in ids]
            def _arm_row(a: str) -> dict:
                setup = a.split("@")[0]
                tot = AG.arm_cap_is_setup_total(self.cfg.arm_max_positions, a, setup)
                n_open = (sum(1 for h in held_arms if h.split("@")[0] == setup) if tot
                          else sum(1 for h in held_arms if h == a))       # `M1: 4` gibi anahtar: acik sayisi kurulum toplami
                return {"open": n_open, "max": AG.arm_cap(self.cfg.arm_max_positions, a, setup),
                        "scope": "setup_total" if tot else "arm"}
            res["arms"] = {a: _arm_row(a) for a in ids}
        return res

    def summary(self) -> RunSummary:
        c = self.counters()
        return RunSummary(steps=c.get("steps", 0), decisions=c.get("decisions", 0),
                          trades_opened=c.get("trades_opened", 0), trades_closed=c.get("trades_closed", 0),
                          open_at_end=tuple(p.trade_id for p in self.state.open_positions()), counters=c)

    def stop(self) -> None:
        self._stop = True

    # ================================================================== WP-3: kayit yardimcilari (yalniz kayit)
    def records_block(self) -> dict:
        """status.json `records` (9.3): bu sayaclar `counters()`'a GIRMEZ; alarm uretmez."""
        r = self._rec
        return {"shadow": dict(r["shadow"]),
                "mtm": {"rows": int(self.mtm.rows_written), "errors": int(self.mtm.errors)},
                "exec": dict(r["exec"])}

    def _write_equity_mark(self, ts, wallet, equity, low, n_open, src) -> None:
        self.ledger.record_equity_mark(L.EquityMark(ts=ts, wallet=wallet, equity=equity, equity_low=low,
                                                    n_open=n_open, src=src))

    def _exec_payload(self, role: str, fill, extra: dict | None = None) -> dict:
        """Dolum icin olcum alanlari (temiz, JSON'a uygun). Hicbir hata disari sizmaz: hata = bos yuk (NULL)."""
        try:
            cid = fill.client_id
            meta = self.orders.exec_meta.pop(cid, None) if cid else None
            row = self.state.get_order(cid) if cid else None
            raw = exec_fields(role, meta, fill, row)
            if extra:
                raw.update({k: v for k, v in extra.items() if v is not None})
            out, dropped = exec_payload(raw)
            if dropped:
                self._rec["exec"]["dropped"] += dropped
            return out
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            self._rec["exec"]["dropped"] += 1
            log.warning("olcum alanlari uretilemedi: %r", e)
            return {}

    def _latency_sn(self, since) -> float | None:
        """Kagit: enjekte saatle simdi - `since` (sn, >= 0). Bilinmeyen/bozuk zaman = None (alan yazilmaz). Yalniz kayit."""
        try:
            if not self.is_paper or not isinstance(since, datetime):
                return None
            v = (self.clock.now() - since).total_seconds()
            return round(max(0.0, float(v)), 3) if math.isfinite(v) else None
        except Exception:  # noqa: BLE001 - olcum kaydi hicbir zaman islemi durdurmaz
            return None

    def _store_latency(self, trade_id: int, key: str, value: float | None) -> None:
        """Gecikmeyi motor durumundaki `gecikme:<trade_id>` kv satirina birlestirir (defter semasi degismez; ledger'a giden yuke girmez).
        Cagiran `state.tx()` icinde olmalidir."""
        if value is None:
            return
        cur = self.state.kv_get(f"gecikme:{trade_id}")
        d = dict(cur) if isinstance(cur, dict) else {}
        d[key] = value
        self.state.kv_set(f"gecikme:{trade_id}", d)

    def _remember_dec_price(self, pos: Position, D: datetime, price) -> None:
        try:
            self._dec_ts[pos.trade_id] = (make_client_id(self.cfg.bot, "exit", pos.pair, pos.side, D, 0), D)
            while len(self._dec_ts) > _EXEC_MEM_MAX:
                self._dec_ts.popitem(last=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            if price is None or not float(price) > 0:
                return
            cid = make_client_id(self.cfg.bot, "exit", pos.pair, pos.side, D, 0)
            self._dec_price[pos.trade_id] = (cid, float(price))
            while len(self._dec_price) > _EXEC_MEM_MAX:
                self._dec_price.popitem(last=False)
        except Exception:  # noqa: BLE001
            return

    def _exit_regime_for(self, pair: str, fill_ts: datetime) -> str | None:
        """4: son karar adimindaki hizalanmis 4s etiketi; yas siniri 0 <= fill.ts - D <= tf + 120 sn, aksi NULL."""
        m = self._regime_mem.get(pair)
        if m is None:
            return None
        D, label = m
        age = (fill_ts - D).total_seconds()
        if 0 <= age <= tf_delta(self.tf).total_seconds() + 120:
            return label
        return None

    def _order_quote(self, pair: str) -> dict | None:
        """3.5: emir oncesi `bookTicker` (yalniz testnet/canli, `live.order_quote=true`). Tek deneme, <= 0,5 sn.
        Yasak penceresi/agirlik >= %80 iken cagri yapilmaz (broker None doner). Her hata yutulur.
        Ayni giris denemesinde D17 kapisi sorguyu zaten yaptiysa o sonuc (hata dahil) bir kez yeniden kullanilir:
        giris basina en cok BIR bookTicker GET'i."""
        gq = self._gate_quote
        if gq is not None:
            self._gate_quote = None
            g_pair, g_ts, g_q = gq
            if g_pair == pair and 0.0 <= (self.clock.now() - g_ts).total_seconds() <= _GATE_QUOTE_MAX_AGE_S:
                return g_q
        try:
            if self._ban_until is not None and self.clock.now() < self._ban_until:
                return None
            fn = getattr(self.broker, "book_ticker", None)
            if not callable(fn):
                return None
            res = fn(pair)
            if res is None:
                return None
            bid, ask = float(res[0]), float(res[1])
            if not (bid > 0 and ask >= bid and ask == ask and bid == bid and ask != float("inf")):
                raise ValueError("gecersiz bookTicker")
            mid = (bid + ask) / 2.0
            return {"order_ref_price": mid, "order_ref_spread": (ask - bid) / mid, "order_ref_src": "book"}
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            self._rec["exec"]["quote_errors"] += 1
            log.warning("bookTicker sorgusu basarisiz (%s): %r", pair, e)
            return None

    # ================================================================== gun basi
    def ensure_day_start(self, ts: datetime) -> None:
        day = ts.strftime("%Y-%m-%d")
        pre = None
        if not self.is_paper and self.state.kv_get("day_start_date") != day:
            pre = self.broker.account().equity                 # canli: ag okumasi tx disinda
        with self.state.tx():
            cur = self.state.kv_get("day_start_date")
            if cur == day:
                return
            fresh = cur is None
            self.state.kv_set("day_start:" + day, pre if pre is not None else self.broker.account().equity)
            self.state.kv_set("day_start_date", day)
            self.state.block_remove("day_start_missing")
            if not fresh and ts.replace(hour=0, minute=0, second=0, microsecond=0) != ts:
                self.state.block_add("day_start_missing")
                log.critical("gun basi anlik goruntusu kayip (%s): girisler kapali", day)

    # ================================================================== parametreler
    def _refresh_params(self) -> None:
        try:
            ap = self.ledger.get_active_params()
            if self._params_map is None or ap.activation_id != self._act_id:
                m = dict(ap.params)
                flags = {k: int(m.pop(k)) for k in XM.MODE_PARAMS if k in m}     # cikis kipi bayraklari strateji parametresi degildir
                self.strategy.validate_params(m)
                self._mode_flags = flags
                self._params_map = m
                self._act_id = ap.activation_id
                log.info("parametre surumu %s etkin", ap.version_id)
            self._version_id = ap.version_id
            self._active_tf = str(ap.params["trigger_tf"])
            self._params_ok = True
        except Exception as e:  # noqa: BLE001 - fail-closed
            self._params_ok = False
            log.critical("etkin parametre kullanilamiyor (%s); girisler kapali (params_unavailable)", e)

    def _frame_params(self):
        m = dict(self._params_map) if self._params_map is not None else {
            p.name: p.default for p in self.strategy.info.param_specs}
        if m.get("trigger_tf") != self.tf:
            m["trigger_tf"] = self.tf
        try:
            return SignalParams.from_mapping(m)
        except Exception:  # noqa: BLE001
            return m

    # ================================================================== baslatma
    # ---------------------------------------------------------------- acilis kapisi (yalniz paper)
    def check_inputs(self) -> tuple[list[str], list[str]]:
        """(kurali eksik/bozuk ciftler, 1m last+mark verisi bayat/eksik ciftler). Kapi ve canli sayaclar kullanir."""
        now = self.clock.now()
        missing: list[str] = []
        for p in self.cfg.pairs:
            try:
                self.view.rules(p)
            except Exception:  # noqa: BLE001 - DataError/RulesError/baska: kural yok sayilir
                missing.append(p)
        fresh_last: dict[str, datetime] = {}
        fresh_mark: dict[str, datetime] = {}
        try:
            a = floor_tf(now - timedelta(seconds=STARTUP_MAX_AGE_S + 120), "1m")
            for st in self.view.minute_steps(self.cfg.pairs, a, now):
                for p, b in st.bars.items():
                    fresh_last[p] = max(fresh_last.get(p, b.open_ts), b.open_ts)
                    if b.mark_c is not None:
                        fresh_mark[p] = max(fresh_mark.get(p, b.open_ts), b.open_ts)
        except Exception as e:  # noqa: BLE001
            log.error("veri taze mi kontrolu okunamadi: %r", e)
        limit = timedelta(seconds=STARTUP_MAX_AGE_S)
        stale = [p for p in self.cfg.pairs
                 if not (p in fresh_last and p in fresh_mark
                         and now - (fresh_last[p] + timedelta(seconds=60)) <= limit
                         and now - (fresh_mark[p] + timedelta(seconds=60)) <= limit)]
        self._c["rules_missing"], self._c["data_stale"] = len(missing), len(stale)
        return missing, stale

    def _required_pairs(self) -> list[str]:
        """DD-12 §2: `optional_pairs` (hisse/emtia) disindaki ciftler. Isteğe bagli cift kurali/verisi eksik ya da bayat olsa da
        kapiyi ve dakika/karar adimlarini BEKLETMEZ (yalniz o cift giris yapmaz). Hepsi istege bagliysa hepsi sayilir; testnet/canli/
        geri testte `optional_pairs` bostur => tum ciftler (davranis ayni)."""
        opt = set(self.cfg.optional_pairs)
        req = [p for p in self.cfg.pairs if p not in opt]
        return req or list(self.cfg.pairs)

    def _startup_gate(self) -> None:
        """Zorunlu ciftlerde (kripto) kural + taze 1m last/mark yoksa sinirli bekler, sonra EngineExit(7); isteğe bagli
        (hisse/emtia) ciftlerdeki eksik/bayat durum yalniz uyari + sayac (`optional_waiting`) olur."""
        waited = 0.0
        step = max(1.0, min(15.0, self.cfg.loop_sleep_s * (1 if not self.is_paper else 3)))   # DD-6: canlida kapi beklerken KILL/bekci sik calissin
        while True:
            missing, stale = self.check_inputs()
            req = set(self._required_pairs())
            opt_wait = sorted((set(missing) | set(stale)) - req)
            self._c["optional_waiting"] = len(opt_wait)
            missing = [p for p in missing if p in req]
            stale = [p for p in stale if p in req]
            if not missing and not stale:
                if opt_wait:
                    log.warning("acilis kapisi: isteğe bagli cift(ler) bekliyor (giris yok, motor calisir): %s", opt_wait)
                log.info("acilis kapisi tamam: %d/%d zorunlu cift kural+taze veri", len(req), len(self.cfg.pairs))
                return
            if waited >= self.cfg.startup_wait_s:
                msg = (f"acilis kapisi: {self.cfg.startup_wait_s:.0f} sn sonra hazir degil; "
                       f"kural eksik={missing or '-'} veri bayat={stale or '-'}; motor baslamiyor (feed calisiyor mu?)")
                log.critical("%s", msg)
                raise EngineExit(EXIT_STARTUP_GATE, msg)
            if waited == 0.0:
                log.warning("acilis kapisi bekliyor: kural eksik=%s veri bayat=%s", missing or "-", stale or "-")
            if not self.is_paper:
                self._gate_wait_protect()                         # DD-6 O1: beklerken KILL + stop bekcisi calisir
            self.clock.sleep(step)
            waited += step

    def _gate_wait_protect(self) -> None:
        """DD-6 O1: canli acilis kapisi beklerken KILL (acik pozisyon piyasada kapanir), olaylar ve stop bekcisi calisir.
        Hicbiri kapi bekleyisini bozmaz (hata sayilir, `_guard` 10 ardisik hatada EngineExit(3))."""
        now = self.clock.now()
        self._set_clock(now)
        self._guard("kill", lambda: self._kill_step(now))
        self._guard("events", lambda: self._drain_events())
        self._post_commit()
        self._guard("watchdog", lambda: self._stop_watchdog(self.clock.now()))

    def protect_first(self):
        """11 §6.2 adim 2: veri kapisindan ONCE, piyasa verisi gerektirmez (yalniz canli). Stopsuz pozisyonu korur."""
        if self.is_paper:
            return None
        pf = getattr(self.reconciler, "protect_first", None)
        if pf is None:
            self.orders.resolve_unresolved()
            rep = None
        else:
            rep = pf()
        self._recover_orphan_opening()
        self._mirror_broker_blocks()
        return rep

    def _recover_orphan_opening(self) -> None:
        """G1 ile emir satiri arasinda cokme (11 §6.4 madde 6): `opening` + emir satiri yok + borsada pozisyon yok => kapat."""
        for p in self.state.open_positions():
            if p.status != "opening" or self.state.orders_for_trade(p.trade_id):
                continue
            if not self.orders._exchange_has_position(p.pair):   # noqa: SLF001
                self._close_unopened(p, self.clock.now())

    def start(self) -> RecoveryReport:
        cfg = self.cfg
        live_loop = not self.is_paper and cfg.mode in FEED_MODES
        if live_loop:
            self._clear_broker_latches()
        if cfg.mode in ("testnet", "live") and not self.is_paper:
            if not self.state.integrity_check():
                raise StateError("state integrity_check basarisiz")
            if "wallet_above_expected" in tuple(getattr(self.broker, "startup_findings", ()) or ()):   # DD-8 O4
                w = getattr(self.broker, "startup_wallet", None)
                lim = cfg.live.expected_wallet_max if cfg.live is not None else None
                self._wallet_cap_hold(f"wallet={w} max={lim}")       # protect_first'ten ONCE; cikis/stop/KILL/mutabakat etkilenmez
            self.protect_first()
        if cfg.mode == "paper" or (live_loop and cfg.mode in ("testnet", "live")):
            self._startup_gate()                                  # 11 §6.2: canlida protect_first'ten SONRA, ayni 10/10 kapisi
        if not self.state.integrity_check():
            raise StateError("state integrity_check basarisiz")
        now = self.clock.now()
        with self.state.tx():
            if self.state.kv_get("initialized_at") in (None, "unset"):
                self.state.kv_set("initialized_at", iso_z(now))
            self.state.kv_set("engine_version", ENGINE_VERSION)
        try:
            self.ledger.drain_spool()
        except Exception as e:  # noqa: BLE001
            log.error("spool bosaltilamadi: %s", e)
        self.state.drain_outbox(self.ledger)
        if self.is_paper:
            self._reconcile_orphan_decisions()
        self._refresh_params()
        self._init_tf_and_strategy()
        if self.quarantine is not None:
            self.quarantine.load(self.state.kv_get(QUARANTINE_KV))
        if self.is_paper:
            snap = self.state.kv_get("broker_snapshot")
            if snap:
                self._restore_broker(snap)
            else:
                with self.state.tx():
                    self._save_broker()
        lev = entry_leverage(cfg)
        for pair in cfg.pairs:
            try:
                self.broker.prepare(pair, lev)
            except Exception as e:  # noqa: BLE001
                log.error("prepare %s: %s", pair, e)
        self.orders.resolve_unresolved()
        rep = self._reconcile(now)
        if rep.fatal:
            log.critical("baslangic mutabakati ölümcül: girisler kapali; cikislar calisir")
        self._started = True
        self._kaldirilan_kollari_kapat(now)                       # CT/C1 ayriligi: kaldirilan kolun acik pozisyonlari piyasadan kapanir
        mins, decs = 0, 0
        if cfg.mode == "paper":
            self._adopt_new_pairs()
        if cfg.mode in FEED_MODES and self._init_cursors():
            c0 = self._c["decisions"]
            mins = self.advance_to(self.clock.now())
            decs = self._c["decisions"] - c0
        return RecoveryReport(replayed_minutes=mins, replayed_decisions=decs,
                              unresolved_orders=len(self.state.unresolved_orders()), reconcile=rep)

    def _kaldirilan_kollari_kapat(self, now: datetime) -> int:
        """Tek seferlik, idempotent adim (baslangicta): `KALDIRILAN_KOLLAR` kurulumlarinin ACIK pozisyonlarini piyasa fiyatindan kapatir
        (stop/hedef beklenmez; kapanis normal yoldan: gerceklesen K/Z, komisyon ve kayma her zamanki gibi; neden `force_exit`, gunluge
        `kol_kaldirildi`). Kalan acik pozisyon yoksa hicbir sey yapmaz (ikinci calisma no-op). Kagit: `submit_exit` (karsi tarafta
        kagit broker); testnet/canli: yalniz normal reduce-only cikis yolu (`_submit_exit`: ban penceresi + poll). Cikis gonderilemezse
        CRIT gunluk + sayac; sessiz birakilmaz (sonraki baslangicta yeniden denenir). Doner: gonderilen cikis sayisi."""
        sent = 0
        for p in self.state.open_positions():
            if p.setup not in KALDIRILAN_KOLLAR:
                continue
            if p.status == "closing":
                continue                                          # cikis zaten yolda (onceki baslangic): yeniden gonderilmez
            if p.status != "open" or not p.qty:
                self._c["kaldirilan_kol_bekliyor"] += 1
                log.critical("kol_kaldirildi: trade %s (%s) durum=%s; acik degil, bu baslangicta kapatilamadi", p.trade_id, p.setup, p.status)
                continue
            try:
                out = self._submit_exit(p, "force_exit", now)
            except (StateError, EngineExit):
                raise
            except Exception as e:  # noqa: BLE001
                out = None
                log.critical("kol_kaldirildi: trade %s (%s) cikisi basarisiz: %r", p.trade_id, p.setup, e)
            if out is None or getattr(out, "status", "") == "failed":
                self._c["kaldirilan_kol_hata"] += 1
                log.critical("kol_kaldirildi: trade %s (%s) cikisi gonderilemedi; pozisyon acik kaldi", p.trade_id, p.setup)
                continue
            sent += 1
            self._c["kaldirilan_kol_kapatildi"] += 1
            log.warning("kol_kaldirildi: trade %s (%s) piyasadan kapatiliyor", p.trade_id, p.setup)
        return sent

    def _init_tf_and_strategy(self) -> None:
        info = self.strategy.info
        kv_tf = self.state.kv_get("trigger_tf")
        want = self._active_tf if (self._params_ok and self._active_tf in ("1h", "15m", "4h")) else info.allowed_trigger_tfs[0]
        has_open = bool(self.state.open_positions())
        tf = kv_tf if (kv_tf and has_open) else want
        if kv_tf and kv_tf != want and has_open:
            log.critical("trigger_tf degisti (%s -> %s) acik pozisyon varken: girisler kapali", kv_tf, want)
        self.tf = tf
        with self.state.tx():
            self.state.kv_set("trigger_tf", tf)
        # strateji degisikligi / ledger uyumu (§13.2, §13.6)
        label = make_label(info.name, info.version)
        prev = self.state.kv_get("strategy")
        accepted = tuple(getattr(self.strategy, "accepted_prev_strategies", ()))     # WP-11: onceki kagit stratejisinden gecis
        if prev and prev != label and self.state.open_positions() and parse_label(prev)[0] not in accepted:
            raise StrategyError("strategy_change_with_open_positions", f"{prev} -> {label}")
        with self.state.tx():
            self.state.kv_set("strategy", label)
        if self._params_ok:
            check_param_keys(self.strategy, self._params_map or {})
            try:
                reason = self.ledger.get_version(self._version_id).reason
            except Exception:  # noqa: BLE001
                reason = None
            name, ver = parse_label(reason)
            if name != info.name:
                raise StrategyError("strategy_mismatch", f"ledger etiketi {name}, calisan {info.name}")
            if ver is not None and ver != info.version:
                log.critical("strateji surumu uyusmuyor (ledger %s, calisan %s): girisler kapali", ver, info.version)
                self._block("strategy_mismatch")

    def _reconcile(self, now: datetime) -> ReconcileReport:
        self._last_reconcile = now
        rep = self.reconciler.run(now)
        self._c["reconciles"] += 1
        if not self.is_paper:
            self._after_live_reconcile(rep)
        return rep

    def _adopt_new_pairs(self) -> None:
        """DD-12 D-T12 (10 -> 44 gecis): yapilandirmaya sonradan eklenen cifte (imleci yok) mevcut imlecin en gerisi verilir; boylece
        imlec sifirlanmaz/ileri atlanmaz, acik pozisyon ve defter ayni kalir. Hicbir cift imleci yoksa (ilk kurulum) dokunmaz."""
        for kind in ("minute", "decision"):
            cur = {p: self.state.get_cursor(p, kind) for p in self.cfg.pairs}
            have = [c for c in cur.values() if c is not None]
            if not have or len(have) == len(cur):
                continue
            base = min(have)
            with self.state.tx():
                for p, c in cur.items():
                    if c is None:
                        self.state.set_cursor(p, kind, base)
            log.info("yeni cift imleci %s: %s", kind, [p for p, c in cur.items() if c is None])

    def _init_cursors(self) -> bool:
        """True: imlec var (oynatma). Ilk kurulumda son kapanmis dakikaya ayarlanir, gecmis oynatilmaz."""
        cur = self._cursor("minute")
        if cur is not None:
            return True
        lasts = []
        for p in self._required_pairs():                          # istege bagli cift imleci geri cekmez / bekletmez (DD-12 §2)
            lm = self.view.last_closed_minute(p)
            if lm is None:
                return False
            lasts.append(lm)
        last = min(lasts)
        D = floor_tf(last + timedelta(seconds=self.view.step_seconds()), self.step_tf)
        with self.state.tx():
            for p in self.cfg.pairs:
                self.state.set_cursor(p, "minute", last)
                self.state.set_cursor(p, "decision", D)
        return False

    def _cursor(self, kind: str) -> datetime | None:
        cs = [self.state.get_cursor(p, kind) for p in self.cfg.pairs]
        if any(c is None for c in cs):
            return None
        return min(cs)

    # ================================================================== hata yonetimi
    def _guard(self, label: str, fn) -> bool:
        try:
            fn()
        except (StateError, EngineExit):
            raise
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self._after_failure(label, e)
            return False
        self._consec_errors = 0
        self._consec[label] = 0
        return True

    _BO = "broker_order:"

    def _save_broker(self) -> None:
        """Kagit broker snapshot'i kv'ye yaz. Terminal (degismez) emirler emir basina bir kez ayri satira yazilir;
        ana `broker_snapshot` yalniz canli emirleri tasir (adim maliyeti emir gecmisiyle buyumez)."""
        if not hasattr(self.broker, "snapshot_split"):                  # test/yedek brokerlari: eski tek-blob yolu
            self.state.kv_set("broker_snapshot", self.broker.snapshot())   # type: ignore[attr-defined]
            return
        snap, done = self.broker.snapshot_split()   # type: ignore[attr-defined]
        for cid, row in done.items():
            self.state.kv_set(self._BO + cid, row)
        self.state.kv_set("broker_snapshot", snap)
        if done:
            self.broker.mark_persisted(done)   # type: ignore[attr-defined]

    def _restore_broker(self, snap: dict) -> None:
        """`_save_broker` kaydini (govde + terminal emir satirlari) birlestirip broker'a geri yukle."""
        if not hasattr(self.broker, "snapshot_split"):
            self.broker.restore(snap)   # type: ignore[attr-defined]
            return
        rows = self.state.kv_prefix(self._BO)
        if "order_idx" in snap:
            orders = {r["o"]["client_id"]: r["o"] for r in rows.values()}
            idx = {r["o"]["client_id"]: r["i"] for r in rows.values()}
            snap = dict(snap)
            snap["orders"] = {**orders, **snap["orders"]}
            snap["order_idx"] = {**idx, **snap["order_idx"]}
        self.broker.restore(snap, persisted=frozenset(r["o"]["client_id"] for r in rows.values()))   # type: ignore[attr-defined]

    def _after_failure(self, label: str, e: Exception) -> None:
        self._c["callback_errors"] += 1
        if self.is_paper:
            self._consec_errors += 1                          # kagit/backtest: eski davranis (herhangi bir basari sifirlar)
        else:
            # canli: basarili bir alt adim baska adimin hata sayacini sifirlayamaz (etiket basina sayac)
            self._consec[label] = self._consec.get(label, 0) + 1
            self._consec_errors = max(self._consec.values())
        log.critical("%s adimi basarisiz (%d. ardisik): %r", label, self._consec_errors, e, exc_info=True)
        if self.is_paper:
            snap = self.state.kv_get("broker_snapshot")
            if snap:
                try:
                    self._restore_broker(snap)
                except Exception as re_:  # noqa: BLE001
                    log.critical("broker geri yuklenemedi: %r", re_)
        if self._consec_errors >= 10:
            raise EngineExit(3, "10 ardisik hata")
        if self._consec_errors >= 3:
            self._block("engine_errors")

    # ================================================================== dakika adimi
    def process_step(self, step) -> None:
        if self._guard("minute", lambda: self._process_step(step)):
            self._post_commit()

    def _post_commit(self) -> None:
        try:
            res = self.state.drain_outbox(self.ledger)
            self._outbox_health(res)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            self._c["ledger_errors"] += 1
            log.error("outbox bosaltilamadi: %r", e)

    def _outbox_health(self, res) -> None:
        """Defter outbox'inda takili/gecersiz satir: say ve girisleri kapat (cozulene kadar; islem kapansa da kapali)."""
        if res.failed > 0:
            self._c["outbox_failed"] += 1
            log.error("outbox takili: %d satir yazilamadi (%s)", res.failed, res.first_error)
            self._block("outbox_stuck")
        else:
            self.state.block_remove("outbox_stuck")

    def _process_step(self, step) -> None:
        ts = step.ts
        end = ts + timedelta(seconds=self.view.step_seconds())
        self._set_clock(end)
        if not self.is_paper:
            self._process_step_live(step, ts)
            return
        with self.state.tx():
            self.ensure_day_start(ts)
            self.broker.advance(step.bars, "fills")             # type: ignore[attr-defined]
            self._handle_events(self.broker.poll(end), step, end)
            self.broker.advance(step.bars, "triggers")          # type: ignore[attr-defined]
            self._handle_events(self.broker.poll(end), step, end)
            self._kill_step(end)                                # kill emri bu adimda verilir, sonraki adimda dolar
            opens = self.state.open_positions()
            for p in opens:
                bar = step.bars.get(p.pair)
                if bar is not None and p.status in ("open", "closing"):
                    self._persist(p, update_excursion(p, bar))
            self._mtm_minute(ts, step, opens)                   # WP-3 madde 18: yalniz kayit
            for pair in self.cfg.pairs:
                c = self.state.get_cursor(pair, "minute")
                if c is None or ts > c:
                    self.state.set_cursor(pair, "minute", ts)
            self._save_broker()
        self._last_minute = ts
        self._remember_marks(step)
        self._c["steps"] += 1

    def _process_step_live(self, step, ts: datetime) -> None:
        """Canli dakika adimi (11 §6.2 madde 4): yalniz gun basi, MFE/MAE ve imlec. Olay/KILL live_tick'te."""
        self.ensure_day_start(ts)
        opens = self.state.open_positions()
        for p in opens:
            bar = step.bars.get(p.pair)
            if bar is not None and p.status in ("open", "closing"):
                self._persist(p, update_excursion(p, bar))
        self._mtm_minute(ts, step, opens)                       # WP-3 madde 18: yalniz kayit
        with self.state.tx():
            for pair in self.cfg.pairs:
                c = self.state.get_cursor(pair, "minute")
                if c is None or ts > c:
                    self.state.set_cursor(pair, "minute", ts)
        self._last_minute = ts
        self._remember_marks(step)
        self._c["steps"] += 1

    def _remember_marks(self, step) -> None:
        """status.json acik K/Z: islenen son kapanmis 1m last_c (bellekte zaten var; yeni istek yok). Hicbir istisna sizmaz."""
        try:
            for pair, bar in step.bars.items():
                c = getattr(bar, "last_c", None)
                if c is not None:
                    self._last_marks[pair] = (float(c), bar.close_ts)
        except Exception:  # noqa: BLE001
            pass

    def _mtm_minute(self, ts: datetime, step, opens) -> None:
        """6.2: dakika adiminda ters-uc (temkinli) gerceklesmemis K/Z birikimi. Hicbir istisna sizmaz."""
        if not self.mtm.enabled or not opens:
            return
        try:
            wallet = float(self.broker.account().wallet) if self.is_paper else None   # canli: onbellek (ek REST yok)
            self.mtm.on_minute(ts, step.bars, opens, wallet)
        except Exception as e:  # noqa: BLE001
            self.mtm.errors += 1
            log.warning("mtm dakika isareti hatasi: %r", e)

    def _kill_step(self, now: datetime) -> None:
        if self.kill.active():
            if self.state.kv_get("kill_seen_at") is None:
                with self.state.tx():
                    self.state.kv_set("kill_seen_at", iso_z(now))
                log.critical("KILL etkin: girisler kapali, acik pozisyonlar kapatiliyor")
            first_err: Exception | None = None
            for p in self.state.open_positions():
                if p.status == "open" and p.qty:
                    try:
                        self._submit_exit(p, "force_exit", now)
                    except (StateError, EngineExit):
                        raise
                    except Exception as e:  # noqa: BLE001
                        if self.is_paper or self.strict:
                            raise                              # kagit: dis tx geri alinir; strict: hata gizlenmez (eski davranis)
                        # DD-2 O9 (yalniz canli): bir pozisyonun cikis hatasi sonrakileri o turda engellemez; say, kaydet,
                        # devam et. Ilk hata dongu sonunda YENIDEN FIRLATILIR: `_guard("kill")` sayar (CRIT/engine_errors/exit)
                        self._c["kill_exit_errors"] += 1
                        log.error("KILL cikisi trade %s: %r (kalan pozisyonlara devam)", p.trade_id, e)
                        if first_err is None:
                            first_err = e
            if first_err is not None:
                raise first_err
        elif self.state.kv_get("kill_seen_at") is not None:
            with self.state.tx():
                self.state.kv_set("kill_seen_at", None)
            log.warning("KILL kalkti: girisler bir sonraki karar adiminda yeniden acilir")

    def _submit_exit(self, pos: Position, reason: str, at: datetime, quote: bool = False):
        """Piyasa cikisi; canlida hemen poll (11 §5.3 not 2) ve olaylari isle."""
        if not self.is_paper and self._ban_until is not None and self.clock.now() < self._ban_until:
            self._c["ban_skipped_exits"] += 1          # pencere icinde gonderim zaten reddedilir; yeni kimlik/satir uretme
            return None
        if not self.is_paper and self.cfg.live is not None:
            # Fix 5: deneme limiti doldu (exit_unknown) -> KILL/watchdog her dakika degil `reconcile_open_s`te BIR gonderim
            n = int(self.state.kv_get(f"exit_retry:{pos.trade_id}", 0) or 0)
            if n >= EXIT_RETRY_LIMIT:
                now = self.clock.now()
                last = self._exit_throttle.get(pos.trade_id)
                if last is not None and (now - last).total_seconds() < float(self.cfg.reconcile_open_s):
                    self._c["exit_throttled"] += 1
                    return None
                self._exit_throttle[pos.trade_id] = now
        out = (self.orders.submit_exit(pos, reason, at, True) if (quote and self.orders.quote_fn is not None)
               else self.orders.submit_exit(pos, reason, at))
        if not self.is_paper:
            self._register(pos.trade_id)
            self._drain_events()
        return out

    def _drain_events(self) -> None:
        now = self.clock.now()
        self._handle_events(self.broker.poll(now), None, now)

    # ------------------------------------------------------------------ broker olaylari
    def _handle_events(self, evs, step, now: datetime) -> None:
        for e in evs:
            if e.kind in ("fill", "liquidation") and e.fill is not None:
                if e.fill.role == "entry":
                    self._on_entry_fill(e, step, now)
                else:
                    self._on_exit_fill(e, step, now)
            elif e.kind == "funding":
                p = self.state.position_for_pair(e.pair)
                if p is not None and p.status in ("open", "closing"):
                    self._persist(p, apply_funding(p, e))   # _persist kendi tx'ini acar
            elif e.kind == "order_rejected":
                self._on_rejected(e, now)
            elif e.kind == "order_canceled":
                self._mark_order(e.client_id, "canceled")

    def _on_entry_fill(self, e, step, now: datetime) -> None:
        fill = e.fill
        pos = self.state.position_for_pair(e.pair)
        if pos is None or pos.status != "opening":
            self._c["unexpected_fills"] += 1
            log.critical("beklenmeyen giris dolumu %s", e.pair)
            return
        if not (_pos_finite(getattr(fill, "price", None)) and _pos_finite(getattr(fill, "qty", None))):   # DD-11 Z-2
            self._c["bad_fill"] += 1
            log.critical("bad_fill %s: gecersiz giris dolumu (price=%r qty=%r); pozisyon opening'de birakildi, outbox yok",
                         e.pair, getattr(fill, "price", None), getattr(fill, "qty", None))
            return
        t_fill = self.clock.now()
        lat_in = self._latency_sn(pos.signal_bar_close_ts)      # yalniz kayit: dolum duvar saati - karar mumu kapanisi
        newp = apply_entry_fill(pos, fill, step.bars.get(e.pair) if step is not None else None, now)
        xp = self._exec_payload("entry", fill)                  # WP-3: yalniz kayit (emir ani alanlari)
        with self.state.tx():                                   # G2: pozisyon open + emir filled + outbox
            self._persist(pos, newp)
            self._mark_order(fill.client_id, "filled")
            self.state.outbox_add("entry", pos.trade_id, build_trade_entry(newp, xp))
            self._store_latency(pos.trade_id, "dolum_gecikme_sn", lat_in)
        self._c["trades_opened"] += 1
        eq = self.state.kv_get(f"eq:{pos.trade_id}")
        tick = self.orders.stop_tick(newp)
        viol = fill_risk_violation(newp, float(eq), tick) if eq else None
        cur = self.state.get_position(pos.trade_id) or newp
        live = not self.is_paper
        if live:
            self._register(pos.trade_id)
        if viol:
            log.critical("dolum sonrasi risk ihlali (%s) trade %s: cikis", viol, pos.trade_id)
            self._c["fill_risk_violation"] += 1
            if live:
                # 11 §6.4 madde 4: once stop, sonra cikis (stopsuz `closing` pozisyon kalmaz)
                self.orders.place_initial_stop(cur, t_fill)
                self._register(pos.trade_id)
                cur = self.state.get_position(pos.trade_id) or cur
                if cur.status == "open":
                    self._submit_exit(cur, "other", now)
            else:
                self.orders.submit_exit(cur, "other", now)
        elif live:
            self.orders.place_initial_stop(cur, t_fill)
            self._register(pos.trade_id)
            self._place_resting_target(pos.trade_id)            # 24.11: stop kuruldu; hedef bekleyen emir (basarisizlik pozisyonu kapatmaz)
        else:
            self.orders.place_initial_stop(cur)
            self._place_resting_target(pos.trade_id)

    def _on_exit_fill(self, e, step, now: datetime) -> None:
        fill = e.fill
        pos = self.state.position_for_pair(e.pair)
        if self._duplicate_exit(fill):
            self._c["duplicate_fill_ignored"] += 1
            return
        if pos is None or pos.status == "opening" or pos.entry_price is None:
            self._c["unexpected_fills"] += 1
            log.critical("beklenmeyen cikis dolumu %s", e.pair)
            return
        pk = self.state.kv_get(f"partial:{pos.trade_id}")
        if (not self.is_paper and isinstance(pk, dict) and pk.get("state") == "pending" and pk.get("cid")
                and fill.client_id != pk.get("cid")):
            self._partial_recover(pos, closing=True)            # kapanistan ONCE: belirsiz kismi bacak cozulur (dolduysa kaydedilir)
            pos = self.state.get_position(pos.trade_id) or pos
            pk = self.state.kv_get(f"partial:{pos.trade_id}")
            if isinstance(pk, dict) and pk.get("state") == "pending":
                self._c["partial_unresolved_at_close"] += 1
                log.critical("kapanista kismi bacak cozulemedi trade %s (cid %s): defter kismi bacagi icermeyebilir",
                             pos.trade_id, pk.get("cid"))
        if isinstance(pk, dict) and self._partial_fill(pos, fill, pk):
            return                                              # kismi kar alma dolumu: pozisyon acik kalir
        closed = apply_exit_fill(pos, fill, step.bars.get(e.pair) if step is not None else None, now)
        if isinstance(pk, dict):
            closed = self._blend_closed(pos, closed)
        if e.detail == "foreign_close":                          # 11 §5.5 madde 3: bizim olmayan kapanis
            closed = replace(closed, exit_reason="manual")
            log.critical("yabanci kapanis %s trade %s: exit_reason=manual", e.pair, pos.trade_id)
        newp = close_position(pos, closed)
        dp = self._dec_price.pop(pos.trade_id, None)            # WP-3: yalniz kayit; yalniz KARARIN verdigi piyasa cikisi icin
        extra = {"exit_regime": self._exit_regime_for(pos.pair, fill.ts)}
        if dp is not None and fill.reason == "market" and dp[0] == fill.client_id:
            extra["decision_price"] = dp[1]
        xp = self._exec_payload("exit", fill, extra)
        dts = self._dec_ts.pop(pos.trade_id, None)               # yalniz KARARIN verdigi piyasa cikisi: dolum - karar mumu kapanisi
        lat_out = self._latency_sn(dts[1]) if (dts is not None and fill.reason == "market" and dts[0] == fill.client_id) else None
        with self.state.tx():                                   # G3
            self._persist(pos, newp)
            self._store_latency(pos.trade_id, "cikis_gecikme_sn", lat_out)
            self.state.outbox_add("exit", pos.trade_id, build_trade_exit(pos, closed, ex=xp))
            self._mark_order(fill.client_id, "filled")
        self._c["trades_closed"] += 1
        if fill.reason == "target":
            self._c["target_fills"] += 1                        # 24.11: bekleyen hedef emri doldu
        if not self.is_paper and self.state.kv_get(f"naked:{pos.trade_id}") is not None:
            with self.state.tx():
                self.state.kv_set(f"naked:{pos.trade_id}", None)
        self.orders.cancel_resting(pos)

    def _duplicate_exit(self, fill) -> bool:
        """11 §6.6: ayni kapanis iki kez teslim edilirse (emir satiri filled, sahibi pozisyon closed) sessizce yok say."""
        row = self.state.get_order(fill.client_id) if fill.client_id else None
        if row is None or row.trade_id is None or row.status != "filled":
            return False
        pk = self.state.kv_get(f"partial:{row.trade_id}")
        if isinstance(pk, dict) and pk.get("state") == "done" and pk.get("cid") == fill.client_id:
            return True                                         # kismi cikis dolumunun ikinci teslimi: tam kapanis DEGIL
        owner = self.state.get_position(row.trade_id)
        return owner is not None and owner.status == "closed"

    def _on_rejected(self, e, now: datetime) -> None:
        row = self.state.get_order(e.client_id) if e.client_id else None
        if row is None:
            return
        self._mark_order(e.client_id, "rejected", e.detail)
        pos = self.state.get_position(row.trade_id) if row.trade_id is not None else None
        if pos is None:
            return
        if row.role == "entry" and pos.status == "opening":
            self._close_unopened(pos, now)
        elif row.role == "exit" and pos.status == "closing" and pos.exit_client_id == row.client_id:
            with self.state.tx():
                self.state.update_position(pos.trade_id, status="open", exit_client_id=None, exit_reason=None)
            if not self.is_paper:
                self.orders._count_exit_failure(pos.trade_id)       # noqa: SLF001  F16: reddedilen cikis de sayilir
        elif row.role == "stop" and pos.status == "open":
            log.critical("stop reddedildi trade %s (%s): mutabakat yeniden kuracak", pos.trade_id, e.detail)
            self._block("stop_failed")
            if "would_trigger" not in str(e.detail or ""):      # would_trigger = stop kurulamadi degil, fiyat gecmis: sayilmaz
                self._note_stop_failed(pos.trade_id)

    def _close_unopened(self, pos: Position, now: datetime) -> None:
        with self.state.tx():
            self.state.update_position(pos.trade_id, status="closed", exit_reason="other", closed_ts=now)
        ev = self._entry_events.pop(pos.trade_id, None)
        if ev is not None:
            try:
                self.ledger.record_decision(replace(ev, final_action="skipped", skip_reason="order_failed",
                                                    supersedes_id=pos.decision_id))
            except Exception as err:  # noqa: BLE001 - best-effort
                self._c["ledger_errors"] += 1
                log.error("order_failed duzeltmesi yazilamadi: %r", err)

    def _reconcile_orphan_decisions(self) -> int:
        """Yeniden baslatma artigi: 'entered' karari yazildi ama islem satiri hic yazilmadi (cokme/yeniden baslatma G1 ile dolum arasinda)
        ve hicbir canli kayit (pozisyon, outbox) buna bagli degil => karar `skipped/order_failed` olarak duzeltilir (supersedes_id; mevcut
        defter API'si). Ticareti etkilemez; hata yutulur."""
        n = 0
        try:
            ids = self.ledger.find_orphan_decisions(older_than_s=3600)
            if not ids:
                return 0
            canli = self.state.decision_ids_in_flight()
            from trader_core.ledger import DecisionEvent  # noqa: PLC0415
            names = {f.name for f in fields(DecisionEvent)}
            for did in ids:
                if did in canli:
                    continue
                rec = self.ledger.get_decision(did)
                kw = {k: getattr(rec, k) for k in names if hasattr(rec, k)}
                kw.update(final_action="skipped", skip_reason="order_failed", supersedes_id=did)
                self.ledger.record_decision(DecisionEvent(**kw))
                n += 1
        except Exception as e:  # noqa: BLE001 - best-effort; saglik uyarisi kalir
            log.error("sahipsiz karar duzeltmesi yapilamadi: %r", e)
        if n:
            log.warning("yeniden baslatma artigi %d giris karari 'order_failed' olarak duzeltildi", n)
        return n

    # ================================================================== karar adimi
    def decision_step(self, D: datetime) -> None:
        self._exit_retry = None                                 # DD-6 D11: yeni karar adimi eski bekleyen denemeyi gecersiz kilar
        ok = self._guard("decision", lambda: self._decision_step(D))
        self._karantina_kaydet()                                # 4b: tx geri alinsa bile karantina kaydi kalici
        if not ok:
            if not self.is_paper and self.cfg.mode in ("testnet", "live"):
                self._schedule_exit_retry(D)
        else:
            self._post_commit()
            if self.status is not None:
                self.status.write(self, force=True)
            self._mtm_decision(D)                               # WP-3: karar adiminin butun isleri bittikten SONRA
            self._shadow_step(D)

    # ------------------------------------------------------------------ DD-6 D11: ayni bar icin yazilim cikislari yeniden denemesi
    def _schedule_exit_retry(self, D: datetime) -> None:
        self._exit_retry = {"D": D, "n": 0, "next": self.clock.now() + timedelta(seconds=DECISION_EXIT_RETRY_BASE_S)}
        self._c["decision_failures"] += 1
        log.critical("karar adimi basarisiz (bar %s): yazilim cikislari %d kez yeniden denenecek", D, DECISION_EXIT_RETRIES)

    def _retry_exits(self, now: datetime) -> None:
        r = self._exit_retry
        if r is None or now < r["next"]:
            return
        r["n"] += 1
        D = r["D"]
        try:
            self._set_clock(now)
            params = self._frame_params()
            frames = {pair: self.signals.frame(pair, D, params, self._version_id) for pair in self.cfg.pairs}
            with self._outer_tx():
                self._exits(D, frames)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            self._c["exit_retry_errors"] += 1
            if r["n"] >= DECISION_EXIT_RETRIES:
                self._exit_retry = None
                log.critical("bar %s yazilim cikis denemesi %d kez basarisiz: vazgecildi (borsa stopu koruyor): %r",
                             D, r["n"], e)
                return
            r["next"] = now + timedelta(seconds=DECISION_EXIT_RETRY_BASE_S * (2 ** r["n"]))
            log.error("bar %s yazilim cikis denemesi %d basarisiz: %r", D, r["n"], e)
            return
        self._exit_retry = None
        self._c["exit_retry_ok"] += 1
        log.warning("bar %s yazilim cikislari %d. denemede degerlendirildi", D, r["n"])

    def _decision_step(self, D: datetime) -> None:
        self._shadow_ctx = None
        self._set_clock(D)
        now = self.clock.now()
        with self._outer_tx():
            self.ensure_day_start(D)
            self._kill_step(now)
            self._ladder_step(now)                                  # 12 §8.2 (a): kapilardan once
            if self.cfg.mode in FEED_MODES:
                self._reconcile(now)
            self._refresh_params()
            self.veto.begin_step(now)
            params = self._frame_params()
            frames: dict[str, SignalFrame] = {}
            for pair in self.cfg.pairs:
                fr = self.signals.frame(pair, D, params, self._version_id)
                frames[pair] = fr
                if fr.status == "data_gap":
                    self._c["data_gaps"] += 1
                if fr.status == "ok" and fr.last is not None:
                    c = fr.last.bar_open_ts
                    if self._last_candle_open is None or c > self._last_candle_open:
                        self._last_candle_open = c
                    self._regime_mem[pair] = (D, fr.last.regime)          # WP-3 madde 16: yalniz kayit
            self._exits(D, frames)
            self._entries(D, frames)
            with self.state.tx():                                   # G4: imecler
                for pair in self.cfg.pairs:
                    c = self.state.get_cursor(pair, "decision")
                    if c is None or D > c:
                        self.state.set_cursor(pair, "decision", D)
                if self.is_paper:
                    self._save_broker()
        self._shadow_ctx = (D, frames, params)
        self._last_decision = D
        self._c["decisions"] += 1

    # ------------------------------------------------------------------ WP-3: karar adimi sonrasi kayitlar (yalniz kayit)
    def _mtm_decision(self, D: datetime) -> None:
        """6.2: karar adimi basina bir oz varlik isareti; butun is bittikten sonra. Hicbir istisna sizmaz."""
        if not self.mtm.enabled:
            return
        try:
            if self.is_paper:
                acct = self.broker.account()                       # benzetim: saf
            else:                                                  # canli: yalniz onbellek, ag cagrisi yok
                fn = getattr(self.broker, "account_cached", None)
                acct = fn() if callable(fn) else None
                if acct is None:
                    return                                         # isaret atlanir; hata degil
            n_open = sum(1 for p in self.state.open_positions() if p.status in ("open", "closing"))
            self.mtm.on_decision(D, acct, n_open)
        except Exception as e:  # noqa: BLE001
            self.mtm.errors += 1
            log.warning("mtm karar isareti hatasi: %r", e)

    def _shadow_table(self, pair: str, D: datetime, fr: SignalFrame):
        t = fr.table
        if t is None:
            ft = getattr(self.signals, "frame_table", None)          # geri test: onceden hesaplanmis tablo
            t = ft(pair, D) if callable(ft) else None
        return None if t is None else t.iloc[-SH.N4H:]

    def _shadow_step(self, D: datetime) -> None:
        """5.2: golge karar satirlari. `state`/`broker`/`orders`/`gate`/`veto`/`kill`/`pause`/`ladder` uzerinde YAZMA ya da
        cagri yok (yalniz `state.position_for_pair` okuma); istisna sizmaz; butce `SHADOW_BUDGET_S`."""
        ctx, self._shadow_ctx = self._shadow_ctx, None
        keys = set(self.cfg.shadow_blocks or ())
        if not keys or self._stop or ctx is None or ctx[0] != D:
            return
        rec = self._rec["shadow"]
        t0 = self.clock.now()
        try:
            _, frames, params = ctx
            sp = params if isinstance(params, SignalParams) else None
            blocks = {b for k in keys for b in SH.BLOCK_OF_KEY.get(k, ())}
            code = getattr(self._last_pre, "code", None)
            pairs = list(self.cfg.pairs)
            if pairs:                                              # butce kuyrugu hep ayni ciftlere dusmesin: baslangic zamanla doner
                k = int(D.timestamp() // 3600) % len(pairs)
                pairs = pairs[k:] + pairs[:k]
            for i, pair in enumerate(pairs):
                if (self.clock.now() - t0).total_seconds() >= SHADOW_BUDGET_S:
                    rec["budget_skips"] += len(pairs) - i
                    break
                try:
                    self._shadow_pair(pair, D, frames.get(pair), sp, blocks, code)
                except Exception as e:  # noqa: BLE001
                    rec["errors"] += 1
                    log.warning("golge adimi hatasi (%s): %r", pair, e)
        except Exception as e:  # noqa: BLE001
            rec["errors"] += 1
            log.warning("golge adimi hatasi: %r", e)
        finally:
            try:
                rec["last_step_ms"] = round((self.clock.now() - t0).total_seconds() * 1000.0, 1)
            except Exception:  # noqa: BLE001
                pass

    def _shadow_pair(self, pair: str, D: datetime, fr, sp, blocks: set, gate_code: str | None) -> None:
        rec = self._rec["shadow"]
        cands: list = []
        tf = self.tf
        if fr is not None and fr.status == "ok" and fr.last is not None:
            rb = blocks & {"r1_disabled", "same_bar_reentry"}
            if rb:
                cands += SH.row_candidates(fr.last, rb, trigger_tf=tf)
            gb = blocks & {"regime_volatile", "regime_unclear"}
            if gb and sp is not None and fr.last.reasons == "regime_blocked":
                cands += SH.regime_cands(fr.last, self._shadow_table(pair, D, fr), sp, gb, trigger_tf=tf)
        if "tf_15m" in blocks and sp is not None and tf == "1h":
            cands += SH.tf15_candidates(self.view, pair, D, sp, counters=rec)
        if not cands:
            return
        info = self.strategy.info
        strat = f"{info.name}@{info.version}"
        pos_open = self.state.position_for_pair(pair) is not None
        for c in cands:
            if SH.in_holdout(c.bar_close_ts):
                continue
            try:
                self.ledger.record_shadow(L.ShadowEvent(
                    block=c.block, bar_close_ts=c.bar_close_ts, trigger_tf=c.trigger_tf, pair=c.pair, side=c.side,
                    setup=c.setup, regime=c.regime, atr_ratio=c.atr_ratio, rh=c.rh, rl=c.rl,
                    features=c.features, planned_entry=c.planned_entry, planned_stop=c.planned_stop,
                    planned_target=c.planned_target, param_version_id=self._version_id, strategy=strat,
                    reasons=c.reasons[:L.MAX_REASON], pos_open=pos_open, gate_code=gate_code))
                rec["rows"] += 1
            except Exception as e:  # noqa: BLE001 - golge yazimi hicbir seyi etkilemez
                rec["errors"] += 1
                log.warning("golge satiri yazilamadi (%s %s): %r", pair, c.block, e)

    # ------------------------------------------------------------------ cikislar (kapisiz)
    def _catchup_boundary(self, pos: Position, D: datetime) -> datetime | None:
        """Canli telafi: pozisyonun TF'sinin D'den onceki son kapanis siniri B; yalniz canli (gercek broker), giristen SONRA ve daha once
        degerlendirilmediyse. Aksi None. (Bellek: yeniden baslatmada ilk adimda bir kez telafi edilir.)"""
        if self.is_paper or self.cfg.mode != "live":
            return None
        B = arm_floor_tf(D, pos.trigger_tf)
        if B >= D or B <= pos.signal_bar_close_ts:
            return None
        last = self._exit_seen.get(pos.trade_id)
        return B if (last is None or B > last) else None

    def _vet(self, pos: Position, dec):
        if dec.kind == "exit" and dec.reason not in _REASONS:
            log.critical("gecersiz cikis nedeni %r (trade %s): force_exit", dec.reason, pos.trade_id)
            return replace(dec, reason="force_exit")
        if dec.kind == "stop_update":
            ns = dec.new_stop
            ok = ns is not None and ((ns > pos.current_stop) if pos.side == "long" else (ns < pos.current_stop))
            if not ok:
                self._c["exit_policy_loosen"] += 1
                return replace(dec, kind="none")
        return dec

    def _exits(self, D: datetime, frames: Mapping[str, SignalFrame]) -> None:
        policy = self.strategy.exit_policy()
        opens = self.state.open_positions()
        seen = self._exit_seen
        resting = self.cfg.target_mode == "resting"
        for k in [k for k in seen if k not in {p.trade_id for p in opens}]:
            seen.pop(k, None)
        for pos in opens:
            if pos.status != "open":
                continue
            Dx = D
            if self._multi_tf and not arm_is_tf_close(D, pos.trigger_tf):
                if resting:
                    # 24.11 kullanici karari: basa-bas tasima ve kismi kar alma 15 dk karar adimi basina degerlendirilir (kendi tf
                    # kapanisini beklemez). Iz suren stop, zaman durdurma, rejim cikisi yine yalniz kendi tf kapanisinda.
                    self._modes_step_guarded(pos, D)
                    pos = self.state.get_position(pos.trade_id)
                    if pos is None or pos.status != "open":
                        continue                                # basa-bas would_trigger / kismi sonrasi pozisyon kapandi: bu adimda iz/catchup yok
                # WP-11: cikis yalniz pozisyonun KENDI zaman dilimi kapaninca degerlendirilir. 23.11 (canli): kacirilan sinir icin
                # telafi: canlida kacan karar barlari yeniden oynatilmaz, bu yuzden o TF kapanisi hic gelmezse pozisyon yalniz borsa
                # stopuyla kalirdi. Son kapanmis TF barinin siniri (D'den onceki) daha once degerlendirilmediyse simdi degerlendirilir.
                Dx = self._catchup_boundary(pos, D)
                if Dx is None:
                    continue
                self._c["exit_catchup"] += 1
                fr = self.signals.frame(pos.pair, Dx, self._frame_params(), self._version_id)   # cikis baglami Dx icin kurulur (giris YOK)
            else:
                fr = frames.get(pos.pair)
            if fr is None or fr.status != "ok":
                self._c["exit_data_gap"] += 1
                continue
            seen[pos.trade_id] = Dx
            try:
                if not self.is_paper:
                    self._partial_recover(pos)              # canli: belirsiz/yarim kalmis kismi emri cozumle (yeniden baslatma dahil)
                    pos = self.state.get_position(pos.trade_id) or pos
                ctx = self.signals.exit_context(pos.pair, pos, Dx)
                if self._multi_tf and ctx is None:              # baglam yok (kendi tf verisi bosluklu): zorla cikis DEGIL, atla
                    self._c["exit_data_gap"] += 1
                    continue
                pos_eval = pos
                if resting and self._target_active(pos.trade_id):
                    pos_eval = replace(pos, planned_target=None)    # hedef bekleyen emirde: bar kapanisinda hedef kontrolu YOK (zaman durdurma kalir)
                dec = policy.evaluate(pos_eval, ctx) if policy is not None else evaluate_exit(pos_eval, ctx)
                modes = self._exit_modes(pos)
                if resting:
                    if modes is not None and dec.kind != "exit":
                        # basa-bas + kismi: ayni 15 dk yolu (mfe/mae); iz suren stop karari bunlardan SONRA, tazelenen stopa gore
                        self._modes_step(pos, Dx)
                        pos = self.state.get_position(pos.trade_id) or pos
                        if pos.status != "open":
                            continue
                    if dec.kind == "stop_update" and dec.new_stop is not None:
                        tighter = (dec.new_stop > pos.current_stop) if pos.side == "long" else (dec.new_stop < pos.current_stop)
                        if not tighter:
                            dec = ExitDecision("none")      # basa-bas stopu iz suren stoptan sikiydi: gevsetme sayilmaz
                elif modes is not None:                         # cikis kipleri: kapaliyken bu dal hic calismaz (bayt bayt ayni)
                    dec = apply_exit_modes(pos, ctx, dec, modes)
                dec = self._vet(pos, dec)
                if dec.kind == "exit":
                    self._remember_dec_price(pos, Dx, getattr(ctx, "last_close", None))
                    self._submit_exit(pos, dec.reason, Dx, quote=True)
                elif dec.kind == "stop_update":
                    self._apply_stop_update(pos, dec.new_stop, Dx, getattr(ctx, "last_close", None), modes)
                if not resting and modes is not None and modes.partial and dec.kind != "exit":
                    cur = self.state.get_position(pos.trade_id)
                    if cur is not None and cur.status == "open":
                        self._maybe_partial(cur, ctx, modes, Dx)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                if self.strict:
                    raise
                self._c["callback_errors"] += 1
                log.critical("cikis degerlendirmesi hatasi trade %s: %r", pos.trade_id, e, exc_info=True)

    def _apply_stop_update(self, pos: Position, new_stop: float, D: datetime, last_close, modes) -> None:
        """Stop sikilastirma karari uygulamasi (iz suren stop ve basa-bas ortak): borsa/kagit stopu degistirilir; yeni stop
        zaten asilmissa (would_trigger) piyasa cikisi."""
        out = self.orders.replace_stop(pos, new_stop)
        if out.note == "would_trigger":
            cur = self.state.get_position(pos.trade_id) or pos
            if cur.status == "open":
                self._remember_dec_price(cur, D, last_close)
                self._submit_exit(cur, "trail_stop", D, quote=True)
        elif out.ok and not self.is_paper:
            self._register(pos.trade_id)
        elif not out.ok and modes is not None and not self.is_paper:
            self._c["exit_mode_stop_replace_failed"] += 1       # canli: eski stop DURUR (yeni once kurulur); sonraki adimda yeniden denenir
            log.warning("cikis kipi stop tasima basarisiz trade %s (%s): eski stop korur", pos.trade_id, out.note)

    # ------------------------------------------------------------------ 24.11: 15 dk adiminda basa-bas + kismi (target_mode=resting)
    def _modes_ctx(self, pos: Position, D: datetime) -> ExitContext | None:
        """Kendi tf kapanisini beklemeyen cikis kipi baglami: en iyi/en kotu uc motorun dakika dakika tuttugu `mfe_price`/`mae_price`
        (giris dolumundan bu adima kadar 1 dk `last` high/low; kagit = canli); son fiyat = son kapanmis 1 dk kapanisi. Tek eleman dizi:
        `exit_modes` islevleri yalniz en iyi uca bakar."""
        mfe, mae = pos.mfe_price, pos.mae_price
        if not (_pos_finite(mfe) and _pos_finite(mae)) or not _pos_finite(pos.entry_price):
            return None
        lm = self._last_marks.get(pos.pair)
        last = float(lm[0]) if lm is not None and _pos_finite(lm[0]) else float(pos.entry_price)
        hi, lo = (float(mfe), float(mae)) if pos.side == "long" else (float(mae), float(mfe))
        return ExitContext(bar_close_ts=D, highs=np.array([hi], dtype=float), lows=np.array([lo], dtype=float),
                           atrs=np.array([], dtype=float), regime_last=None, last_close=last, n_closed=1)

    def _modes_step_guarded(self, pos: Position, D: datetime) -> None:
        try:
            self._modes_step(pos, D)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self._c["callback_errors"] += 1
            log.critical("15 dk cikis kipi hatasi trade %s: %r", pos.trade_id, e, exc_info=True)

    def _modes_step(self, pos: Position, D: datetime) -> None:
        """Basa-bas stop tasima (once) + kismi kar alma (sonra); kagit/canli/geri test AYNI yol. Kip yoksa hicbir sey yapmaz."""
        modes = self._exit_modes(pos)
        if modes is None or pos.status != "open" or not pos.qty:
            return
        if not self.is_paper:
            self._partial_recover(pos)
            pos = self.state.get_position(pos.trade_id) or pos
            if pos.status != "open":
                return
        ctx = self._modes_ctx(pos, D)
        if ctx is None:
            return
        if modes.breakeven:
            dec = self._vet(pos, apply_exit_modes(pos, ctx, ExitDecision("none"), modes))
            if dec.kind == "stop_update" and dec.new_stop is not None:
                self._c["be_moves_15m"] += 1
                self._apply_stop_update(pos, dec.new_stop, D, ctx.last_close, modes)
        if modes.partial:
            cur = self.state.get_position(pos.trade_id)
            if cur is not None and cur.status == "open":
                self._maybe_partial(cur, ctx, modes, D)

    # ------------------------------------------------------------------ 24.11: bekleyen hedef emri (target_mode=resting)
    def _target_wanted(self, pos: Position) -> bool:
        return (self.cfg.target_mode == "resting" and exit_mode_of(pos.setup) == "target" and _pos_finite(pos.planned_target))

    def _target_state(self, trade_id: int) -> dict | None:
        v = self.state.kv_get(f"target:{trade_id}")
        return v if isinstance(v, dict) else None

    def _target_active(self, trade_id: int) -> bool:
        v = self._target_state(trade_id)
        return v is not None and v.get("state") == "active"

    def _place_resting_target(self, trade_id: int) -> None:
        """Giris + ilk stop sonrasi: planlanan hedefi bekleyen (reduceOnly) emir olarak kur. Hedef koruyucu degildir: red/belirsizlik
        pozisyonu KAPATMAZ; durum `failed` olur ve hedef eski yolla (kendi tf kapanisinda piyasa cikisi) denetlenir."""
        pos = self.state.get_position(trade_id)
        if pos is None or pos.status != "open" or not self._target_wanted(pos):
            return
        try:
            out = self.orders.place_target(pos)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            if self.strict:
                raise
            self._c["target_place_errors"] += 1
            log.error("hedef emri kurulamadi trade %s: %r", trade_id, e)
            return
        if out is None:
            return
        if not out.ok and out.note == "would_trigger":
            # 24.11: fiyat hedefi zaten asmis: bekleyen emir semantigi = hemen tetiklenir => piyasada `target` cikisi (kagit = canli)
            with self.state.tx():
                self.state.kv_set(f"target:{trade_id}", {"state": "hit", "cid": out.order.client_id, "seq": out.order.seq,
                                                         "why": "would_trigger", "n": 0})
            self._c["target_instant_exit"] += 1
            cur = self.state.get_position(trade_id)
            if cur is not None and cur.status == "open":
                log.warning("hedef girisle ayni anda asilmis trade %s: piyasada target cikisi", trade_id)
                self._submit_exit(cur, "target", self.clock.now())
            return
        st = {"state": "active" if out.ok else "failed", "cid": out.order.client_id, "seq": out.order.seq,
              "why": out.note, "n": 0 if out.ok else 1}          # n: basarisiz deneme sayisi (mutabakat sinirli yeniden dener)
        with self.state.tx():
            self.state.kv_set(f"target:{trade_id}", st)
        self._c["target_placed" if out.ok else "target_place_failed"] += 1
        if not out.ok:
            log.warning("hedef emri kurulamadi trade %s (%s): bar_close yedegi", trade_id, out.note)
        if not self.is_paper:
            self._register(trade_id)

    def _resize_target(self, pos: Position) -> None:
        """Kismi cikis sonrasi: hedef kalan adede gore yeniden kurulur (yeni seq), eskisi iptal. Kurulamazsa eskisi durur
        (kagit: min(hedef adedi, pozisyon) dolar; canli: mutabakat adet farkini giderir)."""
        tk = self._target_state(pos.trade_id)
        if tk is None or tk.get("state") != "active" or pos.status != "open":
            return
        old = str(tk.get("cid") or "")
        out = self.orders.place_target(pos)
        if out is None or not out.ok:
            self._c["target_resize_failed"] += 1
            log.warning("kismi sonrasi hedef kalan adede kurulamadi trade %s (%s): eski hedef durur; mutabakat duzeltir",
                        pos.trade_id, None if out is None else out.note)
            return
        with self.state.tx():
            self.state.kv_set(f"target:{pos.trade_id}", {"state": "active", "cid": out.order.client_id,
                                                         "seq": out.order.seq, "why": "resized"})
        self._c["target_resized"] += 1
        if old and old != out.order.client_id:
            self.orders.cancel_target(pos, old, "replaced_by_partial_resize")
        if not self.is_paper:
            self._register(pos.trade_id)

    # ------------------------------------------------------------------ cikis kipleri (basa-bas / kismi kar alma)
    def _exit_modes(self, pos: Position):
        """Pozisyonun cikis kipleri (yapilandirma + ders bayraklari; docs/cikis-kipleri-spec.md). Kip yoksa None."""
        if not (self.is_paper or self.cfg.mode == "live") or (not self.cfg.exit_modes and not self._mode_flags):
            return None                                         # kipler kagit/geri test ve CANLI (23.11: canli = kagit); testnet: kapali
        return XM.resolve(self.cfg.exit_modes, pos.setup, pos.trigger_tf, self._mode_flags)

    def _maybe_partial(self, pos: Position, ctx, modes, D: datetime) -> None:
        """Kismi kar alma: tetik gerceklesince BIR kez pozisyonun `pt_frac` kadari piyasada kapanir (kagit ve canli ayni kural;
        canlida reduceOnly piyasa emri). Durum `partial:<trade_id>` anahtarinda (pending | done | skipped); emir kimligi
        gonderimden ONCE kalici yazilir, yeniden baslatmada anahtar bos degilse ikinci kismi emir ASLA gonderilmez."""
        prev = self.state.kv_get(f"partial:{pos.trade_id}")
        n_try = 0
        if prev is not None:
            if not (isinstance(prev, dict) and prev.get("state") == "retry"):
                return
            if prev.get("d") == iso_z(D):
                return                                          # ayni barda yeniden deneme yok (kimlik ayni)
            n_try = int(prev.get("n", 0))
            if n_try >= PARTIAL_RETRY_MAX:
                with self.state.tx():
                    self.state.kv_set(f"partial:{pos.trade_id}", {"state": "skipped", "why": "retry_exhausted"})
                self._c["partial_skipped"] += 1
                return
        if not partial_due(pos, ctx, modes):
            return
        rules = self.broker.rules(pos.pair)
        q = XM.partial_qty(float(pos.qty), modes.pt_frac, rules.step, rules.min_qty, rules.min_notional,
                           float(getattr(ctx, "last_close", 0.0) or 0.0))
        if q is not None:
            q = round(round(q / rules.step) * rules.step, 12)       # emirle ayni adim (market_step); kv adedi gonderilenle ayni
        if q is None:
            with self.state.tx():
                self.state.kv_set(f"partial:{pos.trade_id}", {"state": "skipped", "why": "min_qty"})
            self._c["partial_skipped"] += 1
            return
        cid = make_client_id(self.cfg.bot, "exit", pos.pair, pos.side, D, 1)
        req = OrderRequest(client_id=cid, pair=pos.pair, role="exit", order_side=order_side_for(pos.side, "exit"), qty=q,
                           trigger_price=None, reduce_only=True, leverage=None, signal_bar_close_ts=D,
                           created_ts=self.clock.now(), partial=True)
        with self.state.tx():
            self.state.kv_set(f"partial:{pos.trade_id}", {"state": "pending", "cid": cid, "qty": q, "n": n_try})
        out = self._submit_partial_order(pos, req)         # emir `orders` tablosuna yazilir (normal cikislarla ayni yol)
        if not self.is_paper:
            self._register(pos.trade_id)
            self._drain_events()                           # canli: dolum olayi hemen islenir (pozisyon qty + stop kalan adede gore)
        if out.order.status == "rejected":
            why = str(out.order.detail or "")
            if not self.is_paper and why.startswith(_PARTIAL_TRANSIENT):
                with self.state.tx():                       # gecici ret (emir borsada YOK): sonraki barda yeniden dene
                    self.state.kv_set(f"partial:{pos.trade_id}", {"state": "retry", "n": n_try + 1, "d": iso_z(D), "why": why})
                self._c["partial_retry_transient"] += 1
                return
            with self.state.tx():
                self.state.kv_set(f"partial:{pos.trade_id}", {"state": "skipped", "why": f"rejected:{out.order.detail}"})
            self._c["partial_skipped"] += 1
        else:
            self._c["partial_submitted"] += 1

    def _submit_partial_order(self, pos: Position, req: OrderRequest):
        """Kismi kar alma emri (yalniz benzetimli broker): emir satiri `orders`a yazilir (POST'tan once commit), sonuc
        normal cikislarla ayni `_apply_result` yoluyla uygulanir; normal cikisin aksine pozisyon `closing`e GECMEZ."""
        now = self.clock.now()
        row = OrderRow(client_id=req.client_id, pair=req.pair, role=req.role, order_side=req.order_side, qty=req.qty,
                       trigger_price=None, reduce_only=req.reduce_only, status="pending",
                       signal_bar_close_ts=req.signal_bar_close_ts, seq=0, attempts=0, trade_id=pos.trade_id,
                       broker_order_id=None, detail=None, created_ts=now, updated_ts=now)
        with self.state.tx():
            self.state.insert_order(row)
        self.orders._put_meta(req.client_id, {"order_ts": now})        # noqa: SLF001
        if self.is_paper:
            res = self.broker.market_order(req)
            return self.orders._apply_result(row, res, None)          # noqa: SLF001
        try:                                                           # canli: POST'tan once kimlik kalici; kor yeniden gonderim YOK
            res = self.broker.market_order(req)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001 - belirsiz: emir borsada olabilir
            log.warning("kismi emir belirsiz %s: %r", req.client_id, e)
            res = None
        if res is None or res.status == "unknown":
            row = self.orders._upd(req.client_id, status="accepted", detail="partial_unverified")    # noqa: SLF001
            return SubmitOutcome(False, "failed", row, None, "partial_unverified")   # `_partial_recover` sorgular
        return self.orders._apply_result(row, res, None)              # noqa: SLF001

    def _partial_recover(self, pos: Position, *, closing: bool = False) -> None:
        """Canli: `partial:<id>` pending ve dolum olayi gelmediyse (belirsiz POST, yeniden baslatma) emri kimlikle sorgula.
        Dolduysa dolum uydurulur (`_partial_fill`: adet/stop/durum); dolmadiysa atlandi isaretlenir. Ikinci emir GONDERILMEZ."""
        pk = self.state.kv_get(f"partial:{pos.trade_id}")
        if not (isinstance(pk, dict) and pk.get("state") == "pending" and pk.get("cid")):
            return
        cid = str(pk["cid"])
        try:
            bo = self.broker.query(pos.pair, cid)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            self._c["partial_recover_query_failed"] += 1
            log.warning("kismi emir sorgulanamadi %s: %r", cid, e)
            return
        if bo is None:
            key = f"partial_nf:{pos.trade_id}"
            n = int(self.state.kv_get(key, 0) or 0) + 1
            with self.state.tx():
                self.state.kv_set(key, n)
                if n >= 2:
                    self.state.kv_set(f"partial:{pos.trade_id}", {"state": "skipped", "why": "not_found", "cid": cid})
            if n >= 2:
                self._c["partial_skipped"] += 1
                self._mark_order(cid, "failed", "gone_on_query")
            return
        if bo.status == "new":
            return
        if bo.filled_qty and bo.filled_qty > 0 and bo.avg_price and bo.avg_price > 0:
            fee = float(bo.filled_qty) * float(bo.avg_price) * self.cfg.cost.taker_fee      # gercek komisyon bilinmiyor: tahmin
            self._c["partial_fee_estimated"] += 1
            fill = Fill(client_id=cid, pair=pos.pair, role="exit", order_side=bo.order_side, qty=float(bo.filled_qty),
                        price=float(bo.avg_price), fee=fee, ts=bo.updated_ts or self.clock.now(), reason="market")
            if self._partial_fill(pos, fill, pk, resize=not closing):
                self._c["partial_recovered"] += 1
                return
        with self.state.tx():
            self.state.kv_set(f"partial:{pos.trade_id}", {"state": "skipped", "why": f"query:{bo.status}", "cid": cid})
        self._c["partial_skipped"] += 1
        self._mark_order(cid, "canceled" if bo.status != "rejected" else "rejected", f"partial_{bo.status}")

    def _partial_fill(self, pos: Position, fill, pk: dict, *, resize: bool = True) -> bool:
        """Kismi cikis dolumu: pozisyon acik kalir (adet/marjin azalir), dolum `partial:<id>`'e yazilir, stop kalan adede
        gore yeniden kurulur. Defter tek cikis satiri yazar (kapanista karma fiyat; bkz. `_blend_closed`)."""
        if pk.get("state") != "pending" or fill.client_id != pk.get("cid"):
            return False
        rest = float(pos.qty) - float(fill.qty)
        if not rest > 0:
            return False                                         # tam kapanis: normal yol
        with self.state.tx():
            self.state.kv_set(f"partial:{pos.trade_id}", {"state": "done", "cid": pk.get("cid"), "qty": float(fill.qty),
                                                          "price": float(fill.price), "fee": float(fill.fee),
                                                          "ts": iso_z(fill.ts)})
            self.state.update_position(pos.trade_id, qty=rest,
                                       margin=float(pos.margin) * rest / float(pos.qty))
            self._mark_order(fill.client_id, "filled")           # `_duplicate_exit` ikinci teslimi gorur
        self._c["partial_fills"] += 1
        cur = self.state.get_position(pos.trade_id)
        if resize and cur is not None and cur.status == "open":
            self._resize_stop(cur)
            self._resize_target(self.state.get_position(pos.trade_id) or cur)       # 24.11: bekleyen hedef de kalan adede
        return True

    def _resize_stop(self, pos: Position) -> None:
        """Kalan adede gore yeni stop (ayni fiyat, yeni seq); eskisi iptal. would_trigger/red: eski stop durur (paperda
        min(stop.qty, pos.qty) dolar) ve mutabakat adet farkini giderir."""
        om = self.orders
        price = round_tight(pos.current_stop, pos.side, om.stop_tick(pos))
        seq = pos.stop_seq + 1
        old = pos.stop_client_id
        om._pupd(pos.trade_id, stop_seq=seq)                      # noqa: SLF001
        out = om._submit(om._stop_request(pos, price, seq), seq, pos.trade_id)   # noqa: SLF001
        if not out.ok:
            self._c["partial_stop_resize_failed"] += 1
            log.warning("kismi sonrasi stop kalan adede kurulamadi trade %s (%s): eski stop durur; mutabakat duzeltir",
                        pos.trade_id, out.note)
            return
        om._pupd(pos.trade_id, stop_client_id=out.order.client_id)   # noqa: SLF001
        if old and old != out.order.client_id:
            try:
                self.broker.cancel(pos.pair, old)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("eski stop iptal edilemedi %s: %r", old, e)
            else:
                if not self.is_paper:                              # canli: iptal edilen eski stop satiri `accepted` kalmaz
                    r_old = self.state.get_order(old)
                    if r_old is not None and r_old.status == "accepted":
                        om._upd(old, status="canceled", detail="replaced_by_partial_resize")   # noqa: SLF001

    def _blend_closed(self, pos: Position, closed):
        """Kismi cikis yapilmis pozisyonun kapanisi: defter TEK cikis satiri tutar; cikis fiyati iki parcanin adet agirlikli
        ortalamasi, cikis ucreti toplam (brut PnL = tam adet * (karma - giris) birebir). Kismi yoksa `closed` aynen doner."""
        pk = self.state.kv_get(f"partial:{pos.trade_id}")
        if not (isinstance(pk, dict) and pk.get("state") == "done"):
            return closed
        px = XM.blend_exit(float(pk["qty"]), float(pk["price"]), float(pos.qty), float(closed.exit_price))
        return replace(closed, exit_price=px, fee_exit=float(closed.fee_exit) + float(pk["fee"]),
                       leg_exit_price=float(closed.exit_price))   # kayma: son bacak dolumu / planlanan cikis (karma degil)

    # ------------------------------------------------------------------ girisler (kapili)
    def _entry_order(self, D: datetime, frames: Mapping[str, SignalFrame]) -> list[str]:
        """Giris adaylarinin sirasi (kagit/canli/geri test ayni yol): once buyuk zaman dilimi (1d > 4h > 1h > 15m; adayi olmayan
        sona), esitlikte yapilandirma sirasi DONEN bir baslangic ofsetiyle. Ofset her grup icin KENDI zaman diliminden
        turetilir: `(D // tf_saniye) % n` (buyuk tf adaylari yalniz kendi sinirlarinda gorundugunden, 15 dk ofseti n ile ortak
        boleni olan sayilarda donusu durdururdu). Adayi olmayanlar 15 dk ofsetini kullanir. Yalniz `D`'ye bagli: ayni zaman
        damgasi ayni sirayi verir. Boyut tavanlari dolarken hep BTC/ETH onde gitmez. Cift ici sira degismez."""
        pairs = list(self.cfg.pairs)
        n = len(pairs)
        if n <= 1:
            return pairs
        epoch = int(D.timestamp())
        idx = {p: i for i, p in enumerate(pairs)}

        def tf_of(pair: str) -> str | None:
            fr = frames.get(pair)
            row = None if fr is None else fr.last
            if row is None or not row.signal:          # sinyali olmayan cift: en sonda (-1)
                return None
            try:
                return _tf_of(row)
            except Exception:  # noqa: BLE001 - tf cozulemezse en dusuk aday sirasi
                return ""

        tfs = {p: tf_of(p) for p in pairs}

        def key(p: str):
            tf = tfs[p]
            rank = -1 if tf is None else _TF_RANK.get(tf, 0)
            secs = _TF_SECS.get(tf or "", 900)
            return (-rank, (idx[p] - (epoch // secs) % n) % n)
        return sorted(pairs, key=key)

    def _entries(self, D: datetime, frames: Mapping[str, SignalFrame]) -> None:
        pre = self.gate.pre(D, self.tf, self._params_ok, self._active_tf or self.tf)
        self._last_pre = pre
        attempted = False
        for pair in self._entry_order(D, frames):
            try:
                attempted = self._pair_entries(pair, D, frames[pair], pre, attempted) or attempted
                pre = self._last_pre if self._last_pre is not None else pre
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001 - cift-bazli hata: giris yok
                if self.strict:
                    raise
                self._c["callback_errors"] += 1
                log.critical("giris degerlendirmesi hatasi %s: %r", pair, e, exc_info=True)

    def _pair_entries(self, pair: str, D: datetime, fr: SignalFrame, pre, attempted: bool) -> bool:
        """Bir ciftin adaylari (buyuk tf once, sonra oncelik; `fr` kazanan, `fr.extras` digerleri). 24.11: kazanan sonraki bir
        kontrolde (uzun_yon, kurulum tavani, risk/boyut ...) reddedilirse siradaki aday ayni adimda denenir; biri girince ya da
        aday kalmayinca durur (cift basina en cok BIR islem). Reddedilen adaylar gercek red nedeniyle yazilir (`mark_decided`
        yalniz hicbiri girmediyse, ilk redle, bir kez); hic denenmemis / yalniz onceliginde kaybeden sinyal adaylari
        `arm_conflict` yazilir. Kagit/canli/geri test ayni yol. Doner: giris denemesi yapildi mi."""
        tried = False
        entered = None          # girisi yapilan aday satiri
        first_skip: EntryOutcome | None = None
        cands = (fr, *fr.extras)
        try:
            for k, c in enumerate(cands):
                if attempted or not self.is_paper:
                    # DD-6 O3: kapi (blokaj nedeni, KILL, duraklatma, kademe) her girisden once yeniden okunur; bir onceki giris
                    # `stop_failed` yazdiysa kalan ciftler `gate:<neden>` ile atlanir. Kagit/geri test: yalniz giris denemesinden sonra.
                    pre = self.gate.pre(D, self.tf, self._params_ok, self._active_tf or self.tf)
                    self._last_pre = pre
                out = self.gate.decide(c, D, pre, self._version_id)
                if out.action == "enter" and self.cfg.mode == "testnet" and not self.is_paper:
                    out = self._testnet_price_gate(pair, D, c, out)
                if out.action != "enter":
                    self._gate_quote = None
                if out.action == "enter":
                    tried = True
                    entered = c.last
                    self._enter(pair, D, c, out)
                    self._kalan_adaylar(pair, D, cands[k + 1:], entered, pre)     # onceliginde kaybedenler: arm_conflict
                    break
                if out.action == "skip":
                    self._record_skip(pair, D, out, mark=False)   # isaret en sonda: sonraki aday `already_decided` gormesin
                    if first_skip is None:
                        first_skip = out
                    if not AG_ADAY_OZGU(out):                       # cift/hesap duzeyi red: durulur, kalanlar arm_conflict
                        self._kalan_adaylar(pair, D, cands[k + 1:], fr.last, pre)
                        break
                    continue
                break                                              # ignore (position_exists / already_decided / ...): satir yazilmaz
        finally:
            if entered is None and first_skip is not None and first_skip.mark_decided:
                try:
                    with self.state.tx():
                        self.state.mark_decided(pair, D, "skipped:" + first_skip.code)
                except StateError:
                    raise
                except Exception as e:  # noqa: BLE001 - isaret hatasi baska bir istisnayi ortmesin
                    log.error("karar isareti yazilamadi %s: %r", pair, e)
        return tried

    def _kalan_adaylar(self, pair: str, D: datetime, rest, winner, pre) -> None:
        """Siralamada kazananin/redin ARKASINDAki adaylar: sinyal ise `arm_conflict`, elenmis (filtre) ise kendi nedeniyle."""
        for c in rest:
            self._extra_candidate(pair, D, c, winner, pre)

    def _extra_candidate(self, pair: str, D: datetime, ex: SignalFrame, winner, pre) -> None:
        """D-T16: kazanan (buyuk zaman dilimi) disindaki sinyal adaylari `arm_conflict` olarak yazilir; elenmis (filtre) adaylar
        kendi atlama nedenleriyle (kapi `decide` yolu). Kaybedenler hicbir zaman giris yapmaz."""
        if ex.last is None:
            return
        if ex.last.signal:
            if winner is not None and winner.signal:
                self._record_skip(pair, D, self.gate.conflict(ex, winner))
            return
        out = self.gate.decide(ex, D, pre, self._version_id)
        if out.action == "skip":
            self._record_skip(pair, D, out)

    def _testnet_price_gate(self, pair: str, D: datetime, fr: SignalFrame, out: EntryOutcome) -> EntryOutcome:
        """DD-6 D17 (11-canli-broker §11): yalniz testnet. Testnet fiyati (bookTicker orta) `planned_entry`den %0,5'ten fazla
        saparsa giris `testnet_price_divergence` ile atlanir. Fiyat okunamazsa (yasak penceresi/agirlik/hata) sapma
        olculemez: giris ENGELLENMEZ (fail-open; `testnet_price_unchecked` sayaci + uyari) - kapi sartnamede yalniz sapmayi atlar."""
        row = fr.last
        q = self._order_quote(pair)
        self._gate_quote = (pair, self.clock.now(), q)     # ayni girisin `order_quote` yolu yeniden kullanir (tek GET)
        ref = None if q is None else float(q["order_ref_price"])
        pe = float(row.planned_entry) if row.planned_entry else 0.0
        if ref is None or not pe > 0:
            self._c["testnet_price_unchecked"] += 1
            return out
        if abs(ref - pe) / pe <= TESTNET_PRICE_DIVERGENCE_MAX:
            return out
        code = "testnet_price_divergence"
        self._c[code] += 1
        log.warning("testnet giris atlandi %s: %s (planned_entry=%s testnet=%s)", pair, code, row.planned_entry, ref)
        self.gate.counters["enter"] -= 1
        return self.gate._skip(row, _tf_of(row), code, skip_reason="entry_gate_closed",      # noqa: SLF001
                               veto_reason="gate:" + code)

    def _record_skip(self, pair: str, D: datetime, out: EntryOutcome, mark: bool = True) -> None:
        try:
            self.ledger.record_decision(out.event)
        except Exception as e:  # noqa: BLE001 - skip kayitlari best-effort
            self._c["ledger_errors"] += 1
            log.error("skip karari yazilamadi (%s %s): %r", pair, out.code, e)
        if mark and out.mark_decided:
            with self.state.tx():
                self.state.mark_decided(pair, D, "skipped:" + out.code)

    def _enter(self, pair: str, D: datetime, fr: SignalFrame, out: EntryOutcome) -> None:
        row = fr.last
        try:
            did = self.ledger.record_decision(out.event)
        except Exception as e:  # noqa: BLE001 - zorunlu kayit: yoksa giris yok
            self._c["ledger_errors"] += 1
            log.critical("entered karari yazilamadi (%s): %r; giris yok", pair, e)
            return
        size = out.size
        equity = float(self.broker.account().equity)
        with self.state.tx():                                   # G1: giris niyeti (POST'tan once commit)
            tid = self.state.next_trade_id()
            info = self.strategy.info
            trail = float((self._params_map or {}).get("trail_atr", 0.0))
            pos = Position(
                trade_id=tid, bot=self.cfg.bot, pair=pair, side=row.side, setup=row.setup, status="opening",
                decision_id=did, signal_bar_close_ts=row.bar_close_ts, entry_ts=None, entry_bar_open=None,
                entry_price=None, qty=None, leverage=out.leverage, initial_stop=row.planned_stop,
                current_stop=row.planned_stop, stop_seq=0, stop_client_id=None, planned_target=row.planned_target,
                trail_atr=trail, param_version_id=row.param_version_id, trigger_tf=row.tf or self.tf,
                risk_amount=size.risk_amount, margin=size.margin, rh=row.rh, rl=row.rl, fee_entry=0.0,
                funding_paid=0.0, mfe_price=None, mae_price=None, exit_reason=None, exit_client_id=None,
                closed_ts=None, strategy_name=info.name, strategy_version=info.version)
            self.state.insert_position(pos)
            self.state.mark_decided(pair, D, "entered")
            self.state.kv_set(f"eq:{tid}", equity)
        self._entry_events[tid] = out.event
        intent = Intent(kind="entry", bot=self.cfg.bot, pair=pair, side=row.side, signal_bar_close_ts=row.bar_close_ts,
                        setup=row.setup, qty=size.qty, leverage=out.leverage, planned_entry=row.planned_entry,
                        stop_price=row.planned_stop, target_price=row.planned_target, reason="entry", decision_id=did)
        res = (self.orders.submit_entry(intent, tid, quote=True) if self.orders.quote_fn is not None
               else self.orders.submit_entry(intent, tid))
        if not self.is_paper:
            self._drain_events()                                # 11 §6.4: dolum ayni cagri zincirinde -> stop
            if res.status == "failed" and res.order.status == "unknown":
                return                                          # belirsiz giris: satir/pozisyon pencere boyunca kalir
        if res.status not in ("filled", "accepted"):
            cur = self.state.get_position(tid)
            if cur is not None and cur.status == "opening":
                self._close_unopened(cur, self.clock.now())
            elif cur is not None:
                self._entry_events.pop(tid, None)

    # ================================================================== canli dongu
    def advance_to(self, now: datetime) -> int:
        if self._last_now is not None and now < self._last_now:
            self._block("clock_skew")
            raise ClockError(f"saat geri gitti: {now} < {self._last_now}")
        self._last_now = now
        self.state.block_remove("clock_skew")
        step_s = self.view.step_seconds()
        n = 0
        while not self._stop:
            cur = self._cursor("minute")
            if cur is None:
                if not self._init_cursors():
                    return n
                cur = self._cursor("minute")
            nxt = cur + timedelta(seconds=step_s)
            if is_tf_close(nxt, self.step_tf):
                ld = self._cursor("decision")
                if ld is None or ld < nxt:
                    if not self.is_paper and nxt < floor_tf(now, self.step_tf):
                        # 11 §6.2 madde 4: kacan karar barlari yeniden oynatilmaz; yalniz en son kapanmis bar degerlendirilir
                        self._c["skipped_decisions"] += 1
                        with self.state.tx():
                            for p in self.cfg.pairs:
                                c = self.state.get_cursor(p, "decision")
                                if c is None or nxt > c:
                                    self.state.set_cursor(p, "decision", nxt)
                    else:
                        if not self._decision_ready(nxt, now):
                            return n
                        self.decision_step(nxt)
            end = nxt + timedelta(seconds=step_s)
            if now < end:
                return n
            steps = list(self.view.minute_steps(self.cfg.pairs, nxt, end))
            have = steps[0].bars if steps else {}
            if any(p not in have for p in self._required_pairs()):
                if now < end + timedelta(seconds=self.cfg.minute_wait_s):
                    return n
                if not have:
                    latest = [self.view.last_closed_minute(p) for p in self._required_pairs()]
                    if not any(t is not None and t > nxt for t in latest):
                        return n                                  # veri bayat: dakika ilerlemez
            self.process_step(steps[0] if steps else MinuteStep(nxt, {}))
            n += 1
        return n

    def _decision_ready(self, D: datetime, now: datetime) -> bool:
        if now < D:
            return False
        if now >= D + timedelta(seconds=self.cfg.bar_wait_s):
            return True
        for p in self._required_pairs():
            rng = self.view.data_range(p, self.step_tf)
            if rng is None or rng[1] < D - tf_delta(self.step_tf):
                return False
        return True

    def run_forever(self) -> None:
        self.start()
        try:
            while not self._stop:
                self._tur_koruyucu.calistir(self._loop_turn)        # 4c: gecici hatada sinirsiz bekleme, kagitta tur-bellek geri yukleme
        finally:
            self.shutdown("stop")

    def _loop_turn(self) -> None:
        now = self.clock.now()
        if not self.is_paper and self.cfg.mode in ("testnet", "live"):
            self.live_tick(now)
            self.clock.sleep(self.cfg.loop_sleep_s)
            return
        try:
            self.advance_to(now)
        except ClockError as e:
            log.critical("%s", e)
        self._periodic_reconcile(now)
        self._periodic_input_check(now)
        if self.status is not None:
            self.status.write(self)
        self.clock.sleep(self.cfg.loop_sleep_s)

    # ------------------------------------------------------------------ 4b / 4f: karantina ve sembol izleyici
    def _karantina_kaydet(self) -> None:
        q = self.quarantine
        if q is None or not q.dirty:
            return
        try:
            with self.state.tx():
                self.state.kv_set(QUARANTINE_KV, q.dump() or None)
            q.dirty = False
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("karantina kaydi yazilamadi: %r", e)

    def _dayaniklilik_tick(self, now: datetime) -> None:
        """Dakikada bir: karantina kaldirma istegi + saatlik sembol kontrolu. Hicbir istisna sizmaz."""
        try:
            q = self.quarantine
            if q is not None:
                req = take_release_request(os.path.dirname(self.cfg.path("x")))
                if req:
                    rel = q.release(req)
                    log.warning("karantina kaldirma istegi (%s): %s", req, rel or "eslesen yok")
                self._karantina_kaydet()
            iz = self.sembol_izleyici
            if iz is not None:
                iz.check(now)
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("dayaniklilik kontrolu hatasi: %r", e)

    def _dayaniklilik_status(self) -> dict:
        q, iz = self.quarantine, self.sembol_izleyici
        return {"karantina": q.status() if q is not None else [],
                "sembol": iz.status() if iz is not None else [],
                "tur_hatalari": {"toplam": self._tur_koruyucu.total, "son": self._tur_koruyucu.last_error}}

    def _periodic_input_check(self, now: datetime) -> None:
        """Calisirken kural/veri sayaclarini (`rules_missing`, `data_stale`) dakikada bir tazeler; karar vermez."""
        if self.cfg.mode not in ("paper", "testnet", "live"):
            return
        last = getattr(self, "_last_input_check", None)
        if last is not None and (now - last).total_seconds() < 60:
            return
        self._last_input_check = now
        self._dayaniklilik_tick(now)
        try:
            self.check_inputs()
        except Exception as e:  # noqa: BLE001
            log.error("girdi kontrolu hatasi: %r", e)

    def _periodic_reconcile(self, now: datetime) -> None:
        every = self.cfg.reconcile_open_s if self.state.open_positions() else self.cfg.reconcile_flat_s
        if self._last_reconcile is None or (now - self._last_reconcile).total_seconds() >= every:
            try:
                with self._outer_tx():
                    self._reconcile(now)
            except StateError:
                raise
            except Exception as e:  # noqa: BLE001
                log.error("mutabakat hatasi: %r", e)

    def shutdown(self, reason: str) -> None:
        log.info("kapaniyor: %s", reason)
        if self.status is not None:
            self.status.write(self, force=True, stopped=True)


    # ================================================================== canli yol (11 §6)
    def live_tick(self, now: datetime) -> None:
        """Her dongude, veri akisindan bagimsiz: KILL -> olaylar -> stop bekcisi -> mutabakat -> advance_to -> status."""
        self._set_clock(now)
        self._guard("kill", lambda: self._kill_step(now))
        self._guard("events", lambda: self._drain_events())
        self._post_commit()
        self._guard("ladder", lambda: self._ladder_step(now))     # 12 §8.2 (b): olaylardan sonra, mutabakattan once
        self._guard("watchdog", lambda: self._stop_watchdog(self.clock.now()))
        self._guard("bans", self._sync_bans)
        self._mirror_broker_blocks()
        self._periodic_input_check(now)                        # 11 §6.3: kural/veri sayaclari dakikada bir
        every = self.cfg.reconcile_open_s if self.state.open_positions() or self.state.unresolved_orders() \
            else self.cfg.reconcile_flat_s
        if self._last_reconcile is None or (now - self._last_reconcile).total_seconds() >= every:
            self._guard("reconcile", lambda: self._reconcile(now))
        self._guard("exit_retry", lambda: self._retry_exits(now))
        if self._adv_next_try is None or now >= self._adv_next_try:
            try:
                self.advance_to(now)
                self._adv_errors = 0
                self._adv_next_try = None
            except ClockError as e:
                log.critical("%s", e)
            except DataError as e:
                self._advance_failed(e, now)
        if self.status is not None:
            self.status.write(self)

    def _advance_failed(self, e: Exception, now: datetime) -> None:
        """DD-6 O1: gecici veri hatasi motoru oldurmez. Say, ussel geri cekil, N ardisik hatada girisleri kapat (engine_errors)."""
        self._adv_errors += 1
        self._c["advance_errors"] += 1
        delay = min(ADVANCE_BACKOFF_CAP_S, ADVANCE_BACKOFF_BASE_S * (2 ** (self._adv_errors - 1)))
        self._adv_next_try = now + timedelta(seconds=delay)
        log.error("advance_to veri hatasi (%d. ardisik, %.0f sn sonra yeniden): %r", self._adv_errors, delay, e)
        if self._adv_errors >= ADVANCE_ERRORS_ENTRIES_OFF and not self.state.block_has("engine_errors"):
            log.critical("%d ardisik veri hatasi: girisler kapatildi (engine_errors); KILL/bekci/mutabakat surer", self._adv_errors)
            self._block("engine_errors")

    def _stop_watchdog(self, now: datetime) -> None:
        """11 §6.5: borsada kabul edilmis stopu olmayan open/closing pozisyon stop_deadline_s'i (>) asarsa reduceOnly piyasa."""
        deadline = float(self.cfg.live.stop_deadline_s) if self.cfg.live is not None else 10.0
        rows: list[dict] = []
        for p in self.state.open_positions():
            if p.status not in ("open", "closing"):
                continue
            row = self.state.get_order(p.stop_client_id) if p.stop_client_id else None
            if row is not None and row.status == "accepted":
                if self.state.kv_get(f"naked:{p.trade_id}") is not None:
                    with self.state.tx():
                        self.state.kv_set(f"naked:{p.trade_id}", None)
                continue
            since_s = self.state.kv_get(f"naked:{p.trade_id}")
            if since_s is None:
                with self.state.tx():
                    self.state.kv_set(f"naked:{p.trade_id}", iso_z(now))
                since = now
            else:
                from .state import parse_iso_z
                since = parse_iso_z(since_s)
            secs = (now - since).total_seconds()
            rows.append({"trade_id": p.trade_id, "pair": p.pair, "seconds": secs})
            if secs > deadline:
                self._c["naked_closes"] += 1
                log.critical("stopsuz pozisyon %.1f sn (trade %s): piyasada kapatiliyor", secs, p.trade_id)
                if p.status == "open" and p.qty:
                    self._block("stop_failed")
                    self._submit_exit(p, "other", now)
                    self._note_stop_failed(p.trade_id)
        self._naked_rows = rows
        sn = getattr(self.broker, "set_naked", None)
        if callable(sn):
            sn(list(rows))
        self._opening_watch(now)                               # DD-6 D1: korumali pozisyonlardan SONRA (stop asla gecikmez)

    def _opening_watch(self, now: datetime) -> None:
        """DD-6 D1: `opening` pozisyonun cifti `broker.positions()` icinde gorunuyorsa (belirsiz giris sonradan doldu) mutabakati
        beklemeden `protect_first` (adopt + stop). En sik `OPENING_PROTECT_MIN_GAP_S` araliklarla; hata bekciyi bozmaz."""
        opening = [p for p in self.state.open_positions() if p.status == "opening"]
        if not opening:
            return
        last = self._last_opening_protect
        if last is not None and (now - last).total_seconds() < OPENING_PROTECT_MIN_GAP_S:
            return
        self._last_opening_protect = now                       # deneme aninda yazilir (isabet olmasa da REST okumasi kisitlanir)
        try:
            self.orders.resolve_unresolved()                   # 11 §8 L1: once coz, sonra oku
            held = {bp.pair for bp in self.broker.positions()}
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("opening bekcisi: pozisyonlar okunamadi: %r", e)
            return
        hit = [p for p in opening if p.pair in held]
        if not hit:
            return
        self._c["opening_protect"] += 1
        log.critical("opening pozisyon borsada dolu gorundu (%s): protect_first hemen", [p.pair for p in hit])
        self.protect_first()

    def _register(self, trade_id: int) -> None:
        """LiveBroker.register_position: yetkili acilis zamani + pozisyona ait kimlikler (best-effort)."""
        reg = getattr(self.broker, "register_position", None)
        if not callable(reg):
            return
        try:
            p = self.state.get_position(trade_id)
            if p is None or p.entry_ts is None or p.status == "closed":
                return
            cids = [r.client_id for r in self.state.orders_for_trade(trade_id)]
            reg(p.pair, p.entry_ts, tuple(cids))
            rp = getattr(self.broker, "register_partial", None)       # kismi bacak kapanis olayindan dislanir (yeniden baslatmada da)
            pk = self.state.kv_get(f"partial:{trade_id}")
            if callable(rp) and isinstance(pk, dict) and pk.get("cid") and pk.get("state") in ("pending", "done"):
                rp(p.pair, str(pk["cid"]))
        except StateError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("register_position basarisiz: %r", e)

    def _on_adopted_entry(self, row, bo) -> None:
        """Sorguyla (belirsizlik/yeniden baslatma sonrasi) bulunan dolu giris: dolum olayi uydur -> G2 + stop."""
        pos = self.state.get_position(row.trade_id) if row.trade_id is not None else None
        if pos is None or pos.status != "opening":
            return
        qty = bo.filled_qty if bo.filled_qty and bo.filled_qty > 0 else row.qty
        price = bo.avg_price
        if not _pos_finite(price):
            try:
                price = next((bp.entry_price for bp in self.broker.positions() if bp.pair == row.pair), None)
            except Exception:  # noqa: BLE001
                price = None
        if not _pos_finite(price) or not _pos_finite(qty):      # DD-11 Z-3
            self._c["bad_fill"] += 1
            log.critical("bulunan giris dolumunun fiyati yok (%s): mutabakat cozecek", row.client_id)
            return
        now = self.clock.now()
        fee = float(qty) * float(price) * self.cfg.cost.taker_fee
        fill = Fill(client_id=row.client_id, pair=row.pair, role="entry", order_side=row.order_side, qty=float(qty),
                    price=float(price), fee=fee, ts=bo.updated_ts or now, reason="market")
        with self.state.tx():
            self.state.kv_set(f"entry_fee_estimated:{row.trade_id}", True)      # ucret tahmini (gercek komisyon bilinmiyor)
        self._on_entry_fill(BrokerEvent("fill", fill.ts, row.pair, row.client_id, fill), None, now)

    def _ban_token(self) -> tuple:
        lb = getattr(self.broker, "last_ban", None)
        bans = 0
        bc = getattr(self.broker, "counters", None)
        if callable(bc):
            try:
                bans = int(bc().get("exchange_bans", 0))
            except Exception:  # noqa: BLE001
                bans = 0
        return (lb, bans)

    def _note_ban(self) -> None:
        """exchange_ban / rate_limited reti hemen sonrasi (emir yolu)."""
        self._apply_ban()
        self._ban_seen = self._ban_token()

    def _sync_bans(self) -> None:
        """11 §10 F8-F11: ban HER yolda (okuma dahil) gorulur: her live_tick'te broker.last_ban son gorulenle karsilastirilir."""
        tok = self._ban_token()
        if tok == self._ban_seen:
            return
        self._ban_seen = tok
        if tok[0] is not None or tok[1]:
            self._apply_ban()

    def _apply_ban(self) -> None:
        """broker.last_ban'dan (http, retry_after_s) zamanla: 429 -> engel + pencere; 418/403/451 -> exchange_ban tutusu."""
        now = self.clock.now()
        lb = getattr(self.broker, "last_ban", None)
        http, ra = (lb if lb else (None, None))
        until = now + timedelta(seconds=float(ra if ra else 1.0))
        if self._ban_until is None or until > self._ban_until:
            self._ban_until = until
        self._c["exchange_ban_rejects"] += 1
        if http == 429:
            self._block("exchange_rate_limited")
        elif http in (418, 403, 451) and self.pause is not None:
            try:
                self.pause.add("exchange_ban", by="engine:orders", note=f"http={http} retry_after={ra}")
            except Exception as e:  # noqa: BLE001
                log.error("pause.add basarisiz: %r", e)

    def _clear_broker_latches(self) -> None:
        """Temiz yeniden baslatma: brokerin bellek-ici yapiskan nedenleri sifirlanir; kv'ye yansiyanlar da (11 §5)."""
        for r in _BROKER_REASONS:
            self.state.block_remove(r)

    def _mirror_broker_blocks(self) -> None:
        """Brokerin giris engeli (exchange_auth, ...) kapi icin kv'ye yansitilir (baska nedeni ezmez). exchange_auth ayrica
        yapiskan duraklatma tutusu olarak EKLENIR (11 §10 F9; kaldirma yalniz cli)."""
        brs = tuple(getattr(self.broker, "entries_blocked_reasons", ()) or ())
        if "exchange_auth" in brs and self.pause is not None:
            try:
                self.pause.add("exchange_auth", by="engine:broker", note="broker exchange_auth")
            except Exception as e:  # noqa: BLE001
                log.error("pause.add basarisiz: %r", e)
        if not brs:
            br = getattr(self.broker, "entries_blocked_reason", None)
            brs = (br,) if br else ()
        for r in brs:                                      # kumenin TUM uyeleri (yalniz oncelikli degil)
            self._block(str(r))

    def _after_live_reconcile(self, rep) -> None:
        """B4'un kendi exchange_unreachable mandali: yalniz temiz mutabakattan sonra, broker kendininkini kaldirdiysa temizlenir."""
        reasons = tuple(getattr(self.broker, "entries_blocked_reasons", ()) or ())
        if "exchange_unreachable" in reasons or "exchange_unreachable" in getattr(rep, "findings", ()):
            self._block("exchange_unreachable")
            return
        # tur okumalarini tamamladi (temiz mutabakat = okumalar bitti; bulgu varligi temizlemeyi engellemez, 11 §8)
        self.state.block_remove("exchange_unreachable")
        if self._ban_until is None or self.clock.now() >= self._ban_until:
            self.state.block_remove("exchange_rate_limited")
        self._mirror_broker_blocks()

    # ================================================================== backtest surucusu
    def run_range(self, start: datetime, end: datetime, *, active_only: bool = True) -> RunSummary:
        if self.cfg.mode == "backtest":
            check_holdout(start, end)      # kilitli donem: hicbir bar okunmadan once reddedilir
        tf = self.step_tf
        step_s = self.view.step_seconds()
        D = floor_tf(start, tf)
        if D <= start:
            D += tf_delta(tf)
        cur = start
        while D <= end:
            self._run_steps(cur, D, active_only)
            cur = D
            self._set_clock(D)
            self.decision_step(D)
            D += tf_delta(tf)
        if end > cur:
            self._run_steps(cur, end, active_only)
        if self.cfg.mode not in FEED_MODES:
            self._guard("reconcile", lambda: self._reconcile_tx(end))
        return self.summary()

    def _reconcile_tx(self, now: datetime) -> None:
        with self.state.tx():
            self._reconcile(now)

    def _run_steps(self, a: datetime, b: datetime, active_only: bool) -> None:
        if active_only:
            pairs = sorted({p.pair for p in self.state.open_positions()})
        else:
            pairs = list(self.cfg.pairs)
        if not pairs or b <= a:
            return
        for step in self.view.minute_steps(pairs, a, b):
            self.process_step(step)


# ====================================================================== insa
def _build_live_broker(cfg: EngineConfig, clock: Clock | None, env: Mapping[str, str]):
    """11 §6.2 adim 1: load_keys -> SignedRestClient -> LiveBroker -> startup_check (EngineExit 8/5)."""
    from .brokers.binance_futures import LiveBroker
    from .clock import SystemClock
    from .config import check_live_confirm, load_keys
    from .exchange.binance_rest import SignedRestClient
    if cfg.live is None:
        raise ConfigError("live blogu yok")
    check_live_confirm(cfg, env)                     # kanonik sira: once onay, sonra anahtarlar (11 §3)
    key, secret = load_keys(env)                     # ConfigError("keys_missing: ...") aynen
    clk = clock or SystemClock()
    from trader_core.ban_store import BanGuard, ban_dir_for, ban_path
    from .exchange.binance_rest import BASES
    now_ms = lambda: int(clk.now().timestamp() * 1000)    # noqa: E731  (istemciyle aynı saat)
    guard = BanGuard(ban_path(ban_dir_for(cfg.market_db), BASES[cfg.mode]), source=f"engine:{cfg.bot}", now_ms=now_ms)   # DD-7 §2
    rest = SignedRestClient(env=cfg.mode, api_key=key, api_secret=secret,
                            now_ms=now_ms, sleep=clk.sleep,
                            recv_window_ms=cfg.live.recv_window_ms, conditional_mode=cfg.live.conditional_mode,
                            ban_guard=guard)
    broker = LiveBroker(cfg.live, cfg.mode, cfg.leverage, cfg.pairs, rest, clk, cfg.cost.taker_fee, environ=env,
                        contract_types=cfg.contract_types, optional_pairs=cfg.optional_pairs)
    broker.startup_check()
    return broker


def _check_rules_drift(broker, view, cfg: EngineConfig) -> None:
    chk = getattr(broker, "check_rules_drift", None)
    if cfg.mode != "live" or not callable(chk):
        return
    try:
        feed = {p: view.rules(p) for p in cfg.pairs}
        for d in chk(feed):
            log.warning("%s", d)
    except Exception as e:  # noqa: BLE001
        log.warning("kural karsilastirmasi yapilamadi: %r", e)


def _build_ladder(cfg: EngineConfig, clock: Clock, pause: EntryPause, broker, led):
    """12 §8.1: backtest -> yok; paper/testnet/live -> zorlama (dosya gunlugu). 24.11: kagit canli gibi; kagitta gunluk yoksa motor
    `initial` (wallet_start) yazar; canlida `broker.transfers` ile aktarim eslestirme (kagitta aktarim yok = tek fark)."""
    if cfg.mode == "backtest":
        return None
    from trader_core import risk_ladder as RL

    from .ladder import RiskLadder

    def trades_fn(since):
        return led.list_closed_trades(since=since, limit=L.Ledger.LIST_CLOSED_MAX)

    lg = RL.LadderLog(cfg.path("risk_ladder.jsonl"))
    if cfg.mode == "paper":
        try:
            bos = not lg.rows()
        except Exception as e:  # noqa: BLE001 - bozuk gunluk: dokunulmaz, kapi ladder_invalid verir
            log.error("kagit kademe gunlugu okunamadi: %r", e)
            bos = False
        if bos:
            lg.append("initial", "engine:paper", clock.now(), amount=float(cfg.wallet_start), start_step=RL.LIVE_START_STEP)
    xfer = getattr(broker, "transfers", None) if cfg.mode == "live" else None
    return RiskLadder(cfg, clock, pause, log=lg, enforce=True,
                      transfers_fn=xfer if callable(xfer) else None, trades_fn=trades_fn)


def _require_live_paths(cfg: EngineConfig) -> None:
    """DD-8 (E1/O8, acilis sirasi 1. adim): testnet/live'da `kill_file`, `pause_file`, `var_dir` mutlak olmali (`relative_path:<alan>`)
    ve paylasimli kagit yollari olamaz (`check_shared_paths`; EngineConfig elle degistirilmis olsa da burada yeniden denetlenir)."""
    from .config import check_shared_paths
    for fld in ("kill_file", "pause_file", "var_dir"):
        if not os.path.isabs(getattr(cfg, fld)):
            raise ConfigError(f"relative_path:{fld}")
    check_shared_paths(cfg.mode, cfg.var_dir, cfg.kill_file, cfg.pause_file)


def signal_source_class(strategy):
    """Kagit sinyal kaynagi sinifi (tek yer): bilesik strateji (`decision_tf` var; WP-11) -> `MultiArmSignalSource`, aksi
    halde `WindowedSignalSource`. `build_engine` ve geri testin `--env paper` yolu (tutarlilik raporu) ayni secimi kullanir."""
    return MultiArmSignalSource if getattr(strategy, "decision_tf", None) else WindowedSignalSource


def build_engine(cfg: EngineConfig, *, clock: Clock | None = None, view: MarketView | None = None,
                 broker: Broker | None = None, env: Mapping[str, str] | None = None) -> Engine:
    """Zorunlu acilis sirasi (testnet/live; DD-8 §0): 1 yapilandirma (yollar) -> 2 LIVE_CONFIRM + anahtarlar -> 3 state kilidi
    -> 4 damga dogrulamasi -> 5 `startup_check` (ilk HTTP istegi) -> (Engine.start: 6 tavan tutusu, protect_first, kapi).
    Adim 1-4'te borsaya HIC istek gitmez; enjekte `broker`in hicbir yontemi de 3-4'ten once cagrilmaz."""
    from .brokers.paper import PaperBroker, PaperConfig
    from .clock import SystemClock
    from .marketdata.sources import StoreSource

    env = os.environ if env is None else env
    live_mode = cfg.mode in ("testnet", "live")
    if live_mode:
        _require_live_paths(cfg)                     # 1
    if cfg.mode == "live":
        from .config import check_live_confirm
        check_live_confirm(cfg, env)                 # 2: ag oncesi cift onay (11 §3.1)
    if live_mode and broker is None:
        from .config import load_keys
        load_keys(env)                               # ConfigError("keys_missing: ...") aynen (11 §3.2)
    strategy = get_strategy(cfg.strategy, mode=cfg.mode, arms=cfg.arms or None)
    clock = clock or SystemClock()
    view = view or StoreSource(cfg.market_db)
    if live_mode:
        for p in (cfg.ledger_path, cfg.state_path, cfg.status_path, cfg.kill_file, f"{cfg.pause_file}.{cfg.bot}"):
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        # 3: state kilidi (StateError -> cikis 3). `ledger_path` verilmez: testnet/live'de 0 bayt/eksik state'i DAMGA KARAR TABLOSU
        # yakalar (4. satir: state_missing, cikis 8); StateStore'un 0 bayt denetimi (StateError -> 3) yalniz paper icindir.
        state = StateStore(cfg.state_path, bot=cfg.bot)
        led = None
        try:
            # DD-9 §9.4: damga, sema gocunden ONCE (yabanci eski-sema defter goc ettirilip yedeklenmesin; dosyaya dokunulmaz)
            from .stamp import want_stamp
            want = want_stamp(cfg)
            from .stamp import _read_state
            ss = _read_state(state)                     # DD-8 karar tablosu 1. satir (state damgasi) defterden ONCE
            if ss is not None and ss != want:
                raise EngineExit(8, "state_stamp_mismatch")
            try:
                lp = L.peek_meta(cfg.ledger_path, "account_stamp")
            except L.LedgerError as e:
                log.critical("defter damgasi okunamadi: %r", e)
                raise EngineExit(8, "ledger_stamp_mismatch") from e
            if lp is not None and lp != want:
                raise EngineExit(8, "ledger_stamp_mismatch")
            try:
                led = L.open_ledger(cfg.ledger_path, cfg.bot, create=True, migrate=(lp == want), clock=clock.now)
            except L.LedgerSchemaError as e:
                if lp == want:
                    raise
                log.critical("eski sema damgasiz defter: goc yapilmadi: %r", e)
                raise EngineExit(8, "ledger_stamp_missing") from e
            from .stamp import verify_or_init_stamp
            verify_or_init_stamp(cfg, state, led)                                         # 4: damga (EngineExit 8)
            live_broker_new = broker is None
            if broker is None:
                broker = _build_live_broker(cfg, clock, env)                              # 5: startup_check (EngineExit 8/5)
            return _assemble_engine(cfg, clock, view, broker, led, state, strategy, env, live_broker_new)
        except BaseException:
            state.close()                                                                 # kilit sizmasin (flock birakilir)
            if led is not None:
                led.close()
            raise
    if broker is None:
        mmr_fn = None
        if cfg.mode == "paper":                                                           # kapiyla ayni kaynak: sinif MMR'i (gates._tasfiye_mesafesi_karari)
            from . import arm_guard as _AG
            mmr_fn = lambda p: K.sinif_mmr(_AG.asset_class(p, cfg.clusters), cfg.risk_config.maint_margin_rate)  # noqa: E731
        pcfg = PaperConfig(cost=cfg.cost, mmr=K.LOCKED_CFG.maint_margin_rate, wallet_start=cfg.wallet_start, mmr_fn=mmr_fn)
        if cfg.mode == "paper" and cfg.cost_overrides:
            broker = session_cost_broker(cfg, pcfg, view.rules, view.funding, clock)       # DD-12 §4.3: seansa gore kayma
        else:
            broker = PaperBroker(pcfg, view.rules, view.funding, clock)
    for p in (cfg.ledger_path, cfg.state_path, cfg.status_path, cfg.kill_file, f"{cfg.pause_file}.{cfg.bot}"):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
    led = L.open_ledger(cfg.ledger_path, cfg.bot, create=True, clock=(None if cfg.mode == "paper" else clock.now))
    state = StateStore(cfg.state_path, bot=cfg.bot, ledger_path=cfg.ledger_path)
    if cfg.mode == "paper":
        from .stamp import verify_or_init_stamp     # paper: yalniz OKUR (yabanci damga = kod 8); backtest: hic cagrilmaz
        try:
            verify_or_init_stamp(cfg, state, led)
        except BaseException:
            state.close()
            led.close()
            raise
    return _assemble_engine(cfg, clock, view, broker, led, state, strategy, env, False)


def _assemble_engine(cfg: EngineConfig, clock: Clock, view: MarketView, broker: Broker, led: L.Ledger, state: StateStore,
                     strategy, env: Mapping[str, str], live_broker_new: bool) -> Engine:
    vsrc: VetoSource = NoVeto()
    kill = Killswitch(cfg.kill_file, clock)
    pause = EntryPause(f"{cfg.pause_file}.{cfg.bot}", clock, audit_path=cfg.path("pause_audit.jsonl"), bot=cfg.bot)
    status = StatusWriter(cfg.status_path, clock, cfg)
    ladder = _build_ladder(cfg, clock, pause, broker, led)
    sig_cls = signal_source_class(strategy)
    extra = {"quarantine": ArmQuarantine(now_fn=clock.now)} if sig_cls is MultiArmSignalSource else {}
    signals = sig_cls(view, strategy, strict=False, **extra)
    if live_broker_new:
        _check_rules_drift(broker, view, cfg)
    return Engine(cfg, clock=clock, view=view, broker=broker, ledger=led, state=state, signals=signals,
                  strategy=strategy, veto=vsrc, kill=kill, status=status, pause=pause, ladder=ladder)


# ====================================================================== DD-12 §4.3: seansa gore kayma (yalniz kagit)
def session_cost(cfg: EngineConfig, base, pair: str, ts: datetime):
    """`cost_overrides[cift][seans]` (varsa) ile temel CostModel'in kayma alanlarini ezer; yoksa (kripto, eksik cift/seans) temel
    maliyetin kendisini dondurur. Seans, dolum mumunun acilis zamanindan ve cift sinifindan (kume adlari) bulunur."""
    ov = cfg.cost_overrides.get(pair)
    if not ov:
        return base
    tag = session_tag(asset_class(pair, cfg.clusters), ts)
    slips = ov.get(tag)
    return replace(base, **slips) if slips else base


def session_cost_broker(cfg: EngineConfig, pcfg, rules_fn, funding_fn, clock):
    """`PaperBroker` + dolum anina (mum acilisi) gore cift/seans kaymasi. Brokerin kendisi degismez: her mum/cift icin `_cfg.cost`
    gecici olarak seans maliyetiyle degistirilir (is parcacigi yok; try/finally ile geri alinir)."""
    from .brokers.paper import PaperBroker

    class _SessionPaperBroker(PaperBroker):
        def __init__(self, *a, **k) -> None:
            super().__init__(*a, **k)
            self._base_pcfg = self._cfg

        def _with_session(self, pair, bar, fn):
            cost = session_cost(cfg, self._base_pcfg.cost, pair, bar.open_ts)
            if cost is self._base_pcfg.cost:
                return fn(pair, bar)
            self._cfg = replace(self._base_pcfg, cost=cost)
            try:
                return fn(pair, bar)
            finally:
                self._cfg = self._base_pcfg

        def _fills_pair(self, pair, bar):
            return self._with_session(pair, bar, super()._fills_pair)

        def _triggers_pair(self, pair, bar):
            return self._with_session(pair, bar, super()._triggers_pair)

    return _SessionPaperBroker(pcfg, rules_fn, funding_fn, clock)
