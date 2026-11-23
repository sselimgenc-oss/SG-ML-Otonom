"""Risk kademe denetimi calisma zamani sarmalayicisi (docs/motor/12-risk-kademe.md §8): `RiskLadder`.

Motor bu sinifi her karar adiminda ve canli dongude `tick` ile besler; kapi (`gate_code`), etkin risk (`risk_config`) ve
durum (`status`) buradan okunur. Risk sayisi YOKTUR: basamaklar/esikler `trader_core.risk_ladder` kod sabitleridir.
Motor yalniz `step_down`/`review_stop`/`floor_stop`/`peak` satirlari yazar ve duraklatma tutusu KURAR; tutus kaldirmak,
sermaye/devam/yeniden baslatma satiri yazmak yalniz CLI'nin (ve Telegram'in) isidir. Paper kipi GOZLEM'dir (enforce=False).
Sermaye mandali (`capital_latch`): equity <= 0.85 x dep_net -> yeni giris kapanir; TUM kiplerde (paper dahil, enforce'tan bagimsiz)
kurulur, yeniden baslatmada kalir, yalniz kullanici acar; kaldirildiktan sonra esigin ustune cikilip yeniden inilmedikce tekrar kurulmaz.
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from trader_core import risk_ladder as RL
from trader_core.risk import RiskConfig

from .clock import Clock
from .config import EngineConfig
from .errors import ConfigError
from .pause import EntryPause

log = logging.getLogger("engine.ladder")

BY = "engine:rk1"
COUNTERS_EVERY_S = 600.0
GATE_ORDER = ("capital_missing", "ladder_invalid", "equity_unreadable", "capital_mismatch", "capital_unverified")


def _ok_num(x: Any) -> bool:
    return RL.finite_number(x)


class RiskLadder:
    def __init__(self, cfg: EngineConfig, clock: Clock, pause: EntryPause | None, *, log: RL.LadderLog,
                 enforce: bool, follow: RL.LadderLog | None = None,
                 transfers_fn: Callable[[datetime, datetime], list] | None = None,
                 trades_fn: Callable[[datetime], Sequence] | None = None) -> None:
        if enforce and pause is None:
            raise ConfigError("risk kademe zorlamasi icin duraklatma (pause) zorunlu")
        self.cfg = cfg
        self.clock = clock
        self.pause = pause
        self.log = log
        self.enforce = bool(enforce)
        self.follow = follow
        self.transfers_fn = transfers_fn
        self.trades_fn = trades_fn
        self.counters: Counter = Counter()
        self._last_eval: datetime | None = None
        self._st: RL.LadderState | None = None
        self._state_kind = "uninitialized"           # ok | review | floor | uninitialized | invalid
        self._loaded = False
        self._gate: str | None = None
        self._gate_since: datetime | None = None
        self._equity: float | None = None
        self._pend_key: tuple | None = None
        self._pend_n = 0
        self._xfers: list | None = None
        self._xfer_ok_at: datetime | None = None
        self._xfer_checked_at: datetime | None = None
        self._match: RL.MatchResult | None = None
        self._init_mismatch = False
        self._peak_day: str | None = None
        self._would: dict | None = None
        self._retry: tuple[str, dict] | None = None
        self._hold_latch = False                       # RK-1 fix 1: tutus yazilamadi/dogrulanamadi -> ladder_invalid
        self._forced_since: datetime | None = None
        self._mm_latch: dict | None = None             # v1.1 §7: yapiskan capital_mismatch mandali
        self._cnt: dict | None = None
        self._cnt_at: datetime | None = None
        self._follow_state: dict | None = None
        self._follow_cfg: RiskConfig | None = None
        self._latch_init = False                       # capital_latch yeniden silahlanma durumu (yeniden baslatmada denetim gunlugunden)
        self._latch_armed = True
        self._latch_seen = False                       # tutus bu surecte goruldu (kullanici kaldirdi mi ayrimi)
        self._latch_n = 0

    # ================================================================== kapi / etkin risk
    def gate_code(self) -> str | None:
        if not self.enforce:
            return None
        if self._gate in ("capital_missing", "ladder_invalid"):
            return self._gate
        if self._hold_latch or self._stop_retry_pending():
            if self._forced_since is None:
                self._forced_since = self.clock.now()
            return "ladder_invalid"                      # RK-1 fix 1/2: tutus kurulamadi ya da stop satiri yazilamadi
        self._forced_since = None
        return self._gate

    def _stop_retry_pending(self) -> bool:
        return self._retry is not None and self._retry[0] in ("review_stop", "floor_stop")

    @property
    def risk_config(self) -> RiskConfig:
        base = self.cfg.risk_config
        if self.follow is not None:
            if self._follow_cfg is None:
                self._refresh_follow()
            return self._follow_cfg if self._follow_cfg is not None else base
        if not self.enforce:
            return base                                   # gozlem: kagit sonuclari bit-bit ayni
        if not self._loaded:
            self._load()
        if self._st is None:
            return base
        return RL.step_config(base, self._st.step)

    def _refresh_follow(self) -> None:
        base = self.cfg.risk_config
        try:
            fst = self.follow.state() if self.follow is not None else None
            if fst is None:
                raise RL.LadderLogError("izlenen gunluk bos/yok")
            step = fst.step if fst.status == "ok" else min(fst.step, 0)
            self._follow_cfg = RL.step_config(base, step)
            self._follow_state = {"step": step, "ok": True}
        except Exception:  # noqa: BLE001 - izlenen okunamiyor: yapilandirma riski
            self.counters["ladder_follow_unreadable"] += 1
            self._follow_cfg = base
            self._follow_state = {"step": None, "ok": False}

    # ================================================================== durum okuma
    def _load(self) -> list[dict] | None:
        """Gunlugu okur ve katlar; durum etiketini ayarlar. -> satirlar (ok) ya da None (yok/bozuk)."""
        self._loaded = True
        try:
            rows = self.log.rows()
            st = RL.fold(rows)
        except Exception as e:  # noqa: BLE001 - LadderLogError ya da okuma hatasi: fail-closed
            self._st = None
            self._state_kind = "invalid"
            if not isinstance(e, RL.LadderLogError):
                log.error("kademe gunlugu okunamadi: %r", e)
            return None
        self._st = st
        self._state_kind = "uninitialized" if st is None else st.status
        return rows if st is not None else None

    def _set_gate(self, code: str | None, now: datetime) -> None:
        if code != self._gate:
            self._gate = code
            self._gate_since = now if code is not None else None

    def _write(self, kind: str, now: datetime, **fields: Any) -> bool:
        """Satir yazar; yazilamazsa CRITICAL ve (stop/inis icin) sonraki degerlendirmede yeniden denenir."""
        try:
            self.log.append(kind, BY, self._row_at(now), **fields)
            return True
        except Exception as e:  # noqa: BLE001 - satir yazilamasa da tutus kurulur
            log.critical("kademe satiri yazilamadi (%s): %r", kind, e)
            self.counters["ladder_write_errors"] += 1
            if kind != "peak" and not (self._stop_retry_pending() and kind not in ("review_stop", "floor_stop")):
                self._retry = (kind, fields)
            return False

    def _row_at(self, now: datetime) -> datetime:
        """RK-1 fix 2b: motor saati son satirin gerisindeyse satir `at = max(now, son satir at)` ile yazilir."""
        try:
            rows = self.log.rows()
            if rows:
                return max(now, RL.parse_at(rows[-1]["at"]))
        except Exception:  # noqa: BLE001 - okunamazsa now; yazma kendi hatasini verir
            pass
        return now

    # ================================================================== degerlendirme
    def tick(self, now: datetime, equity: float, wallet: float, *, flat: bool = False) -> None:
        """12 §8.2. Hicbir istisna disari sizmaz."""
        try:
            self._tick(now, equity, wallet, flat)
        except Exception as e:  # noqa: BLE001
            self.counters["ladder_errors"] += 1
            log.critical("kademe degerlendirmesi hatasi: %r", e, exc_info=True)
            self._state_kind = "invalid"
            self._set_gate("ladder_invalid", now)

    def _tick(self, now: datetime, equity: float, wallet: float, flat: bool) -> None:
        if self._last_eval is not None and (now - self._last_eval).total_seconds() < RL.EVAL_EVERY_S:
            return                                                                            # 1: kisma
        self._last_eval = now
        if self.follow is not None:
            self._refresh_follow()
        rows = self._load()                                                                   # 2: gunluk
        if self._state_kind == "uninitialized":
            self._pend_key, self._pend_n = None, 0
            self._set_gate("capital_missing", now)
            return
        if self._state_kind == "invalid" or rows is None or self._st is None:
            self._pend_key, self._pend_n = None, 0
            self._set_gate("ladder_invalid", now)
            return
        st = self._st
        self._equity = float(equity) if _ok_num(equity) and equity > 0 else None
        if self.enforce:                                                                      # 3: tutus degismezi
            self._hold_invariant(st)
        if st.status == "floor":
            self._pend_key, self._pend_n = None, 0
            self._set_gate(None, now)
            self._refresh_counters(now, st)
            return
        if self._retry is not None:
            st = self._do_retry(now, st) or st
            rows = self.log.rows() if self._st is not None else rows
            if self._stop_retry_pending():                                                    # RK-1 fix 2a: stop satiri
                self._pend_key, self._pend_n = None, 0                                        # yazilana dek baska
                return                                                                        # eylem/tetik yok (kapi kapali)
        unverified, mismatch = False, False
        if self.enforce and self.transfers_fn is not None:                                    # 4: aktarim (yalniz canli)
            unverified, mismatch = self._transfers(now, rows, wallet, flat)
        if self._equity is None:                                                              # 5: ozsermaye
            self._pend_key, self._pend_n = None, 0
            self._set_gate("equity_unreadable", now)
            return
        if mismatch:                                                                          # 6: uyusmazlik
            self._pend_key, self._pend_n = None, 0
            self._set_gate("capital_mismatch", now)
            return
        self._set_gate("capital_unverified" if unverified else None, now)
        eq = self._equity
        if st.status == "ok":                                                                 # 7: tepe
            st = self._peak(now, st, eq)
        self._capital_latch(now, st, eq)                                                      # 7b: sermaye mandali
        self._trigger(now, st, eq)                                                            # 8: tetik + onay
        self._refresh_counters(now, self._st or st)                                           # 9: sayaclar

    # -- 3 -----------------------------------------------------------------
    def _hold_invariant(self, st: RL.LadderState) -> None:
        if self.pause is None:
            return
        if st.status == "review":
            self._add_hold("drawdown_review", f"base={st.base:.2f} (gunluk: inceleme)")
        elif st.status == "floor":
            self._add_hold("capital_floor", f"dep_net={st.dep_net:.2f} (gunluk: taban)")
        elif self._stop_retry_pending():                  # RK-1 fix 2a: satir yazilamadi, tutus her adimda yeniden kurulur
            kind, f = self._retry  # type: ignore[misc]
            if kind == "review_stop":
                self._add_hold("drawdown_review", f"base={f.get('base', 0):.2f} equity={f.get('equity', 0):.2f} (yeniden)")
            else:
                self._add_hold("capital_floor", f"dep_net={f.get('dep_net', 0):.2f} equity={f.get('equity', 0):.2f} (yeniden)")

    # -- 4 -----------------------------------------------------------------
    def _transfers(self, now: datetime, rows: list, wallet: float, flat: bool) -> tuple[bool, bool]:
        st = self._st
        assert st is not None and self.transfers_fn is not None
        if self._xfer_ok_at is None or (now - self._xfer_ok_at).total_seconds() >= RL.XFER_POLL_S:
            try:
                since = max(st.started_at, now - timedelta(seconds=RL.XFER_WINDOW_S))
                self._xfers = list(self.transfers_fn(since, now))
                self._xfer_ok_at = now
                self._xfer_checked_at = now
            except Exception as e:  # noqa: BLE001 - onceki sonuc korunur
                self.counters["transfer_poll_errors"] += 1
                log.warning("aktarim yoklamasi basarisiz: %r", e)
        unverified = self._xfers is None or self._xfer_ok_at is None or \
            (now - self._xfer_ok_at).total_seconds() > RL.XFER_STALE_S
        if self._xfers is not None:
            self._match = RL.match_transfers(rows, self._xfers, now)
        mismatch = self._mismatch_latched(st, rows, now)
        self._init_mismatch = False
        if not mismatch and flat and RL.init_wallet_mismatch(rows, wallet) and not self._closed_since(st):
            self._init_mismatch = True
            mismatch = True
        return unverified, mismatch

    def _mismatch_latched(self, st: RL.LadderState, rows: list, now: datetime) -> bool:
        """12 §7 (v1.1) yapiskan mandal: uyusmazlik bir kez goruldu mu, sonraki eslesme tam ok VE gunluk basi (seq) degismis
        (operator eylemi) ya da -- YALNIZ gunluk tarafi kalemler icin -- eslesmeyen her kalem GERCEKTEN eslesmis (gec gelen
        aktarim) olmadikca kalkmaz. Borsa tarafi eslesmeyen aktarim mandalda ise yalniz seq degisimi kaldirir (mentor, R1).
        Zaman asimi (pencereden dusme) tek basina mandali kaldirmaz."""
        m = self._match
        if m is not None and not m.ok:
            ex = {str(t.tran_id) for t in m.unmatched_exchange}
            lg = set(m.unmatched_log)
            if self._mm_latch is None:
                self._mm_latch = {"seq": st.seq, "ex": ex, "log": lg}
            else:
                self._mm_latch["ex"] |= ex
                self._mm_latch["log"] |= lg
            return True
        if self._mm_latch is None:
            return False
        if m is None:                                    # yoklama sonucu yok: mandal korunur
            return True
        if st.seq != self._mm_latch["seq"] or self._latched_items_matched(m, rows, now):
            self._mm_latch = None
            return False
        return True

    def _latched_items_matched(self, m: RL.MatchResult, rows: list, now: datetime) -> bool:
        lt = self._mm_latch or {}
        if lt.get("ex"):                                 # mentor: borsa tarafi kalem ancak yeni kayitla (seq degisimi) eslesebilir
            return False
        win = now - timedelta(seconds=RL.XFER_WINDOW_S)
        un_ex = {str(t.tran_id) for t in m.unmatched_exchange}
        in_pool = {str(t.tran_id) for t in (self._xfers or []) if t.ts >= win}
        for tid in lt.get("ex", ()):
            if tid in un_ex or tid not in in_pool:
                return False                             # hala eslesmemis ya da pencereden dusmus (asim)
        log_from = now - timedelta(seconds=RL.XFER_WINDOW_S + RL.XFER_PAIR_S)
        at = {r["seq"]: RL.parse_at(r["at"]) for r in rows}
        for sq in lt.get("log", ()):
            if sq in m.unmatched_log or sq not in at or at[sq] < log_from:
                return False
        return True

    def _closed_since(self, st: RL.LadderState) -> bool:
        if self.trades_fn is None:
            return False
        try:
            return len(self.trades_fn(st.started_at)) > 0
        except Exception as e:  # noqa: BLE001 - belirsiz: denetim atlanir (yalniz gevsetir degil, sikilastirmaz)
            log.warning("kapanmis islem sayisi okunamadi: %r", e)
            return True

    # -- retry -------------------------------------------------------------
    def _do_retry(self, now: datetime, st: RL.LadderState) -> RL.LadderState | None:
        kind, fields = self._retry or (None, None)
        if kind is None:
            return None
        try:
            self.log.append(kind, BY, self._row_at(now), **fields)
        except RL.LadderLogError:
            # RK-1 fix 2b: saat gerisi artik `at` ile cozulur; kalan LadderLogError gercek gecis hatasidir (CLI durumu degistirdi)
            self._retry = None
            log.warning("kademe satiri yeniden denemesi gecersiz, birakildi: %s", kind)
        except Exception as e:  # noqa: BLE001
            log.critical("kademe satiri yeniden yazilamadi (%s): %r", kind, e)
            return None
        else:
            self._retry = None
        self._load()
        return self._st

    # -- 7 -----------------------------------------------------------------
    def _peak(self, now: datetime, st: RL.LadderState, eq: float) -> RL.LadderState:
        day = now.strftime("%Y-%m-%d")
        if self._peak_day == day:
            return st
        if eq > st.peak:
            if not self._write("peak", now, value=eq):
                return st
            self._load()
        self._peak_day = day
        return self._st or st

    # -- 7b ----------------------------------------------------------------
    def _capital_latch(self, now: datetime, st: RL.LadderState, eq: float) -> None:
        """equity <= 0.85 x dep_net -> `capital_latch` tutusu (enforce'tan bagimsiz). Kullanici kaldirdiysa esigin ustune
        cikilmadan yeniden kurulmaz; yeniden baslatmada denetim gunlugunun son capital_latch satiri `remove` ise ve hala esikte
        isek silahsiz baslar. Gunluk satiri yazilmaz (kademe zinciri etkilenmez)."""
        if self.pause is None:
            return
        below = eq <= RL.CAPITAL_LATCH_RATIO * st.dep_net
        try:
            present = any(h.reason == "capital_latch" for h in self.pause.holds())
        except Exception as e:  # noqa: BLE001
            log.error("capital_latch tutusu okunamadi: %r", e)
            return
        if not self._latch_init:
            self._latch_init = True
            last = getattr(self.pause, "last_op", lambda r: None)("capital_latch")
            if below and not present and last == "remove":
                self._latch_armed = False
        if not below:
            self._latch_armed, self._latch_seen, self._latch_n = True, False, 0
            return
        if present:
            self._latch_seen, self._latch_n = True, 0
            return
        if self._latch_seen:                          # kullanici kaldirdi, hala esikte: yeniden kurma
            self._latch_armed, self._latch_seen, self._latch_n = False, False, 0
            return
        if not self._latch_armed:
            return
        self._latch_n += 1
        if self._latch_n < RL.CONFIRM_N:
            return
        if self._add_hold("capital_latch", f"dep_net={st.dep_net:.2f} equity={eq:.2f}"):
            self._latch_seen, self._latch_n = True, 0
            log.critical("sermaye mandali: ozsermaye %.2f <= yatirilan %.2f x %.2f; yeni giris kapali", eq, st.dep_net,
                         RL.CAPITAL_LATCH_RATIO)

    # -- 8 -----------------------------------------------------------------
    def _trigger(self, now: datetime, st: RL.LadderState, eq: float) -> None:
        acts = RL.evaluate(st, eq)
        if not acts:
            self._pend_key, self._pend_n = None, 0
            return
        a = acts[0]
        key = (a.kind, a.trigger)
        self._pend_n = self._pend_n + 1 if key == self._pend_key else 1
        self._pend_key = key
        if self._pend_n < RL.CONFIRM_N:
            return
        self._pend_key, self._pend_n = None, 0
        self._apply(now, st, a, eq)

    def _apply(self, now: datetime, st: RL.LadderState, a: RL.Action, eq: float) -> None:
        if a.kind == "step_down":
            self._write("step_down", now, step=a.step, trigger=a.trigger, equity=eq, peak=st.peak)
            log.warning("kademe indi: %s -> %s (%s, ozsermaye %.2f, tepe %.2f)", RL.STEP_NAMES[st.step],
                        RL.STEP_NAMES[a.step], a.trigger, eq, st.peak)
        elif a.kind == "review_stop":
            self._write("review_stop", now, equity=eq, base=st.base)
            log.critical("-%%20 durma: ozsermaye %.2f <= taban %.2f x %.2f; giris kapali (inceleme)", eq, st.base,
                         RL.STOP_RATIO)
            if self.enforce and self.pause is not None:
                self._add_hold("drawdown_review", f"base={st.base:.2f} equity={eq:.2f}")
        elif a.kind == "floor_stop":
            self._write("floor_stop", now, equity=eq, dep_net=st.dep_net)
            log.critical("son taban: ozsermaye %.2f <= yatirilan %.2f x %.2f; giris kapali", eq, st.dep_net,
                         RL.FLOOR_RATIO)
            if self.enforce and self.pause is not None:
                self._add_hold("capital_floor", f"dep_net={st.dep_net:.2f} equity={eq:.2f}")
        self._would = {"kind": a.kind, "at": RL.fmt_at(now)} if not self.enforce else self._would
        self._load()

    def _add_hold(self, reason: str, note: str) -> bool:
        """Tutusu kurar ve DOGRULAR (RK-1 fix 1). Basarisizlikta bellek ici mandal (ladder_invalid) sonraki basarili
        eklemeye/dogrulamaya kadar kalir."""
        try:
            self.pause.add(reason, BY, note)                     # type: ignore[union-attr]
            present = any(h.reason == reason for h in self.pause.holds())    # type: ignore[union-attr]
        except Exception as e:  # noqa: BLE001
            log.critical("tutus kurulamadi %s: %r", reason, e)
            self.counters["ladder_hold_errors"] += 1
            self._hold_latch = True
            return False
        if not present:
            log.critical("tutus dogrulanamadi %s", reason)
            self.counters["ladder_hold_errors"] += 1
            self._hold_latch = True
            return False
        self._hold_latch = False
        return True

    # -- 9 -----------------------------------------------------------------
    def _refresh_counters(self, now: datetime, st: RL.LadderState) -> None:
        if self.trades_fn is None:
            return
        if self._cnt_at is not None and (now - self._cnt_at).total_seconds() < COUNTERS_EVERY_S:
            return
        try:
            self._cnt = RL.counters(self.trades_fn(st.started_at), st, now)
            self._cnt_at = now
        except Exception as e:  # noqa: BLE001
            self.counters["ladder_counter_errors"] += 1
            log.warning("kademe sayaclari yenilenemedi: %r", e)

    # ================================================================== durum
    def status(self) -> dict:
        """12 §10 `risk_ladder` blogu."""
        if not self._loaded:
            self._load()
        st = self._st
        eq = self._equity
        kind = self._state_kind
        d: dict[str, Any] = {"enforce": self.enforce, "state": kind}
        if st is None:
            d.update({k: None for k in ("step", "step_name", "step_risk", "lowest_step", "step_since", "started_at",
                                        "dep_net", "base", "peak", "dd_base_pct", "dd_peak_pct", "stop_at", "floor_at",
                                        "near", "stopped_at", "last_down_at", "log_seq", "log_hash")})
            d["equity"] = eq
        else:
            d.update({
                "step": st.step, "step_name": RL.STEP_NAMES[st.step], "step_risk": RL.STEPS[st.step],
                "lowest_step": RL.lowest(st.dep_net), "step_since": RL.fmt_at(st.step_since),
                "started_at": RL.fmt_at(st.started_at), "dep_net": st.dep_net, "base": st.base, "peak": st.peak,
                "equity": eq,
                "dd_base_pct": None if eq is None else max(0.0, (st.base - eq) / st.base * 100.0),
                "dd_peak_pct": None if eq is None else max(0.0, (st.peak - eq) / st.peak * 100.0),
                "stop_at": round(RL.STOP_RATIO * st.base, 8), "floor_at": round(RL.FLOOR_RATIO * st.dep_net, 8),
                "near": None if eq is None else eq <= round(RL.NEAR_RATIO * st.base, 8),
                "stopped_at": None if st.stopped_at is None else RL.fmt_at(st.stopped_at),
                "last_down_at": None if st.last_down_at is None else RL.fmt_at(st.last_down_at),
                "log_seq": st.seq, "log_hash": st.head_hash[:8]})
        try:
            d["effective_risk"] = self.risk_config.target_trade_risk
        except Exception:  # noqa: BLE001
            d["effective_risk"] = None
        d["gate_code"] = self.gate_code()
        gc = self.gate_code()
        since = self._gate_since if gc == self._gate else (self._forced_since or self._gate_since)
        d["gate_since"] = None if since is None or gc is None else RL.fmt_at(since)
        if self.transfers_fn is not None:
            d["transfer"] = {"checked_at": None if self._xfer_checked_at is None else RL.fmt_at(self._xfer_checked_at),
                             "ok": None if self._match is None else
                             bool(self._match.ok) and self._mm_latch is None and not self._init_mismatch,
                             "unmatched": 0 if self._match is None else
                             len(self._match.unmatched_exchange) + len(self._match.unmatched_log),
                             "detail": "init_wallet" if self._init_mismatch else None}
        else:
            d["transfer"] = None
        d["pending"] = self._pend_key[0] if (self._pend_key is not None and self._pend_n > 0) else None
        d["would"] = None if self.enforce else self._would
        d["follow"] = self._follow_state if self.follow is not None else None
        d["counters"] = self._cnt
        return d
