"""Backtester (06 §3): AYNI Engine + HistoricalSource + SimClock + PaperBroker. Ayri strateji/dolum/cikis kodu yoktur.
`python -m trader_engine backtest --id ID --period IS|WF|YYYYMMDD-YYYYMMDD ...` (bkz. docs/motor/06-backtester.md)."""
from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import logging
import math
import random
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from trader_core import ledger as L
from trader_core import risk as K
from trader_core.signals import DEFAULT_SIGNAL_PARAMS

from . import metrics as M
from .bars import floor_tf, is_tf_close, tf_delta
from .brokers.paper import PaperBroker, PaperConfig
from .clock import SimClock
from .config import EngineConfig, _read as _read_cfg, _validate as _validate_cfg, apply_overrides, load_engine_config
from .engine import ENGINE_VERSION, Engine, signal_source_class
from .errors import ConfigError, DataError, EngineError
from .gates import NoVeto
from .holdout import HOLDOUT, BacktestArgError, check_holdout  # noqa: F401  (yeniden disa aktarim)
from .killswitch import Killswitch
from .numeric import round_nearest
from .marketdata.sources import HistoricalSource, StoreSource
from .precomputed import GuardedView, LedgerReplayVeto, LookaheadError, PrecomputedSignalSource
from .state import StateStore
from .strategies.base import StrategyError
from .strategies.registry import get_strategy, make_label
from .strategy_runner import WindowedSignalSource
from .types import canon_pair

log = logging.getLogger("backtest")

ROOT = Path(__file__).resolve().parents[2]
PERIODS = {"IS": "20241101-20251101", "WF": "20251101-20260501"}
BASE_FEE = 0.0005

EXIT_OK, EXIT_ARG, EXIT_LOOKAHEAD, EXIT_DATA, EXIT_TRUNCATE, EXIT_EQUALITY = 0, 2, 3, 4, 5, 6


class TruncateError(EngineError):
    pass


class EqualityError(EngineError):
    pass


# --------------------------------------------------------------------------------------------- yardimcilar
def _ymd(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise BacktestArgError("bad_period", f"gecersiz tarih: {s!r}") from e


def parse_period(period: str) -> tuple[datetime, datetime]:
    """IS | WF | YYYYMMDD-YYYYMMDD -> [start, end). HOLDOUT ile kesisen donem reddedilir (anahtar yoktur)."""
    tr = PERIODS.get(period, period)
    try:
        a, b = tr.split("-")
    except ValueError as e:
        raise BacktestArgError("bad_period", f"gecersiz donem: {period!r}") from e
    start, end = _ymd(a), _ymd(b)
    if end <= start:
        raise BacktestArgError("bad_period", "end <= start")
    check_holdout(start, end)
    return start, end


def parse_end_prime(txt: str) -> datetime:
    """END': YYYYMMDDTHH | YYYYMMDDTHHMMSS | YYYYMMDDHH | ISO-8601 (`Z`/`+00:00`, bosluklu). UTC."""
    t = txt.strip()
    for fmt in ("%Y%m%dT%H", "%Y%m%dT%H%M%S", "%Y%m%d%H", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(t, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError as e:
        raise BacktestArgError("bad_truncate", f"--truncate-check END' cozulemedi: {txt!r}") from e
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


def fee_eff(fee_mult: float, slip_bps: float) -> float:
    return round(BASE_FEE * fee_mult + slip_bps / 1e4, 8)


def git_commit() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        d = subprocess.run(["git", "status", "--porcelain", "--", "src", "config"], cwd=ROOT, capture_output=True,
                           text=True).stdout.strip()
        return (c or "unknown") + ("+dirty" if d else "")
    except Exception:  # noqa: BLE001
        return "unknown"


def iso_z(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def build_cost(fill_model: str, fee_mult: float, slip_bps: float | None, granularity: str | None,
               trigger_source: str | None = None) -> dict:
    if fill_model == "legacy_compat":
        if granularity not in (None, "15m"):
            raise BacktestArgError("bad_args", "legacy_compat: granularity 15m zorunlu")
        fe = fee_eff(fee_mult, slip_bps or 0.0)
        return dict(fill_model="legacy_compat", taker_fee=fe, slip_entry_bps=0.0, slip_exit_bps=0.0, slip_stop_bps=0.0,
                    trigger_source="last", granularity="15m")
    gran = granularity or "1m"
    ts = trigger_source or ("mark" if gran == "1m" else "last")
    if gran == "15m" and ts != "last":
        raise BacktestArgError("bad_args", "granularity=15m: trigger_source=last zorunlu")
    cost = dict(fill_model="native", taker_fee=round(BASE_FEE * fee_mult, 8), trigger_source=ts, granularity=gran)
    if slip_bps is not None:
        cost.update(slip_entry_bps=float(slip_bps), slip_exit_bps=float(slip_bps), slip_stop_bps=2.5 * float(slip_bps))
    else:
        cost.update(slip_entry_bps=2.0, slip_exit_bps=2.0, slip_stop_bps=5.0)
    return cost


def _resolve(p: str | Path) -> Path:
    """Goreli yollar cwd'ye gore (yapilandirma `config/engine.base.json` ve `var/` cwd'dedir)."""
    return Path(p)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (datetime, pd.Timestamp)):
        return o.isoformat()
    return str(o)


# --------------------------------------------------------------------------------------------- belirtim / sonuc
@dataclass
class BacktestSpec:
    id: str
    start: datetime
    end: datetime
    period: str = ""
    strategy: str = "price_action_v1"
    tf: str = "1h"
    fill_model: str = "native"
    fee_mult: float = 1.0
    slip_bps: float | None = None
    params: dict = field(default_factory=dict)
    granularity: str | None = None
    trigger_source: str | None = None
    source: str = "history"
    market_db: str | None = None
    history_dir: str | None = None
    synthetic_rules: bool = False
    veto: str = "none"
    record_filtered: bool = True
    skip_flat: bool = True
    paranoid: int | None = None
    seed: int = 17
    truncate_check: datetime | None = None
    from_paper_ledger: str | None = None
    out_root: str | None = None
    config_dir: str = "config"
    pairs: tuple[str, ...] | None = None
    target_trade_risk: float | None = None      # None -> kilitli hedef risk (LOCKED_CFG); verilirse yalniz daha SIKI (<=) deger
    record_shadow: bool = False                 # WP-3 5.1: --record-shadow (tf_15m geri testte DESTEKLENMEZ)
    env: str | None = None                      # tutarlilik raporu: "paper" -> kagit katmani (arms/kume/maliyet) + cok kurullu kaynak; None = eski yol
    wallet_start: float | None = None           # yalniz env ile: ozsermaye baslangici (kagit defterinden turetilir)
    flags: dict = field(default_factory=dict)
    exit_modes: dict | None = None              # cikis kipleri (basa-bas/kismi; docs/cikis-kipleri-spec.md); None = kapali (eski davranis bayt bayt ayni)
    target_mode: str | None = None              # 24.11: "resting" (hedef bekleyen emir; kagit/canli ile ayni) | "bar_close"; None = yapilandirma degeri (--env paper: "resting")


@dataclass
class BacktestResult:
    out_dir: Path
    summary: dict
    meta: dict
    trades: pd.DataFrame
    open_at_end: list
    snapshot: list | None = None
    signals: object = None


class _CompatEntryView:
    """legacy_compat (dondurulmus referans davranisi): giris kapisinin gordugu hesap ve pozisyon durumu.
    (1) Cikislar bir mumda giristen ONCE islenir: bu karar adiminda cikis emri verilmis (`closing`) ve stopu D adimi
        barinda tetiklenecek pozisyonlar kapali sayilir ve gerceklesmis kabul edilir (tek-adimlik ileri bakis:
        yalniz uyum kipi, `peek_uses`a sayilir).
    Ozsermaye tanimi degismez (motor: cuzdan + mark gerceklesmemis; referans: cuzdan + 1h kapanis farki
    capraz dogrulamada `equity_coupling` olarak raporlanir). Paper/native'de kullanilmaz."""

    def __init__(self, state, raw_view, clock, counter) -> None:
        self._s = state
        self._v = raw_view
        self._clock = clock
        self._counter = counter
        self._memo: tuple | None = None

    # -- serbest kalan pozisyonlar: {trade_id: cikis fiyati tahmini}
    def _freed(self) -> dict:
        D = self._clock.now()
        if self._memo is not None and self._memo[0] == D:
            return self._memo[1]
        out: dict = {}
        step = timedelta(seconds=self._v.step_seconds())
        for p in self._s.open_positions():
            if p.status not in ("open", "closing") or p.entry_price is None:
                continue
            try:
                st = next(iter(self._v.minute_steps([p.pair], D, D + step)), None)
            except DataError:
                st = None
            if st is None or p.pair not in st.bars:
                if p.status == "closing":
                    out[p.trade_id] = None
                continue
            b = st.bars[p.pair]
            self._counter[0] += 1
            long = p.side == "long"
            hit = (b.last_l <= p.current_stop) if long else (b.last_h >= p.current_stop)
            if p.status == "closing":
                out[p.trade_id] = b.last_o
            elif hit:
                gap = (b.last_o <= p.current_stop) if long else (b.last_o >= p.current_stop)
                out[p.trade_id] = b.last_o if gap else p.current_stop
        self._memo = (D, out)
        return out

    # -- durum gorunumu
    def open_positions(self):
        fr = self._freed()
        return [p for p in self._s.open_positions() if p.trade_id not in fr]

    def __getattr__(self, name):
        return getattr(self._s, name)


def _trunc_step(x: float, step: float) -> float:
    """Adima asagi kesme, Decimal(repr) uzerinden (referans davranisi: asagi kesme; kayan nokta gurultusu korunur)."""
    d, q = Decimal(repr(float(x))), Decimal(repr(float(step)))
    return float((d / q).to_integral_value(rounding=ROUND_DOWN) * q)


class _CompatBrokerView:
    """legacy_compat: giris kapisinin gordugu hesap. Ayni adimda cikacak (`_CompatEntryView._freed`) pozisyonlarin
    gerceklesmis K/Z'si (cikis fiyati tahmini, giris-ayi tick'ine en yakin yuvarlama, cikis komisyonu dahil) boyutlandirmadan
    ONCE ozsermayeye yansir (referans davranisi: cikislar giristen once islenir). Paper/native'de kullanilmaz."""

    def __init__(self, broker, entry_view, tick_fn, fee) -> None:
        self._b = broker
        self._ev = entry_view
        self._tick_fn = tick_fn
        self._fee = fee

    def account(self):
        acct = self._b.account()
        freed = self._ev._freed()
        if not freed:
            return acct
        bp = {x.pair: x for x in self._b.positions()}
        adj = 0.0
        for p in self._ev._s.open_positions():
            px = freed.get(p.trade_id)
            q = bp.get(p.pair)
            if px is None or q is None or p.entry_price is None:
                continue
            fp = round_nearest(px, self._tick_fn(p.pair, q.opened_ts)) if self._tick_fn is not None else px
            sign = 1.0 if p.side == "long" else -1.0
            adj += q.qty * (fp - q.entry_price) * sign - q.qty * fp * self._fee - q.unrealized
        return dataclasses.replace(acct, equity=acct.equity + adj)

    def __getattr__(self, name):
        return getattr(self._b, name)


class _CoarsePaperBroker(PaperBroker):
    """legacy_compat (kaba 15 dk adim): PaperBroker ayni dolum/tetik kodu; yalniz adim ici `last_mark` zamanlamasi.
    Dolum asamasinda (adim acilisi) mark = adim ACILISI (koruyucu stop bu mark'a gore kurulur), tetik asamasindan sonra
    adim KAPANISI. Boylece 15 dk barin kapanisi stopu asmis olsa bile giris sonrasi stop kurulur ve ayni adimda tetiklenir
    (referans davranisi: giris mumunda stop kontrolu); aksi halde `would_trigger` -> `stop_failed` giris kilidi olusurdu.
    Native 1 dk kipte kullanilmaz."""

    def _fill_entry(self, o, bar, rules) -> None:
        """Referans stake->miktar kesmesi (yalniz legacy_compat): `stake = qty*ref/lev` (karar marjini),
        `amount = trunc((stake/fill)*lev, adim)` (Decimal(repr) kesme: 0.92 -> 0.9199999999999999 -> 0.91).
        Ref = adim acilisi (`entry_ref`), fill = tick'e yuvarlanmis acilis."""
        lev = o.leverage if o.leverage is not None else self._lev.get(o.pair)
        if lev and o.qty > 0 and rules.step:
            fp = self._slipped(bar.last_o, o.order_side, 0.0, rules.tick, o.pair, bar.open_ts)
            if fp > 0:
                margin = (o.qty * bar.last_o) / lev
                o.qty = _trunc_step((margin / fp) * lev, rules.step)
        super()._fill_entry(o, bar, rules)

    def advance(self, bars, phase):
        super().advance(bars, phase)
        for pair, b in bars.items():
            self._last_mark[pair] = b.last_o if phase == "fills" else (b.mark_c if b.mark_c is not None else b.last_c)


# --------------------------------------------------------------------------------------------- BacktestRunner
class BacktestRunner:
    def __init__(self, spec: BacktestSpec) -> None:
        self.spec = spec

    # -- yapilandirma
    def build_config(self, out_dir: Path | None = None) -> EngineConfig:
        s = self.spec
        d = _resolve(s.config_dir)
        if s.env:
            return self._build_env_config(d, out_dir)
        bot = d / "engine.learner.json"
        if bot.exists():
            cfg = load_engine_config(d / "engine.base.json", bot)
        else:                                            # yalniz taban dosya: bot=learner (backtest tek deftere yazar)
            raw = dict(_read_cfg(d / "engine.base.json"))
            raw.setdefault("bot", "learner")
            cfg = _validate_cfg(raw)
        cost = build_cost(s.fill_model, s.fee_mult, s.slip_bps, s.granularity, s.trigger_source)
        # backtest/capraz dogrulama kilitli hedef riskle kosar (taban yapilandirmadaki paper degeri 0.005 sonuclari kaydirmasin)
        kw = dict(mode="backtest", bot="learner", strategy=s.strategy, cost=cost,
                  target_trade_risk=(K.LOCKED_CFG.target_trade_risk if s.target_trade_risk is None else s.target_trade_risk),
                  record_filtered_candidates=bool(s.record_filtered),
                  shadow_blocks=(("regime", "r1_disabled", "same_bar_reentry") if s.record_shadow else ()))
        if s.pairs:
            kw["pairs"] = tuple(canon_pair(p) for p in s.pairs)
        if s.market_db:
            kw["market_db"] = s.market_db
        if s.history_dir:
            kw["history_dir"] = s.history_dir
        if s.exit_modes is not None:
            kw["exit_modes"] = s.exit_modes
        if s.target_mode is not None:
            kw["target_mode"] = s.target_mode
        return apply_overrides(cfg, **kw)

    def _build_env_config(self, d: Path, out_dir: Path | None) -> EngineConfig:
        """`--env paper`: kagit motorunun yapilandirmasi (base + learner + engine.<env>.json katmani; `load_cli_config` ile ayni) KIPI DAHIL
        aynen yuklenir (mode="paper": kume/arm/risk/maliyet kapilari kagitla ayni kod yolu). Yalniz yollar cikti dizinine tasinir ki
        kagit var dizinine/KILL/PAUSE dosyalarina HICBIR sey yazilmasin/okunmasin. Holdout kilidi `run_once`ta ayrica denetlenir.
        ML1 paket yolu cikti dizinine tasinir, ogrenme kuru: geri test kagit paketini OKUMAZ/YAZMAZ; kapi geri testte ogrenme asamasindadir
        (herkes gecer)."""
        from .config import load_cli_config
        s = self.spec
        cfg = load_cli_config(d, "learner", s.env)
        kw: dict = {"mtm_marks": False}
        if s.target_trade_risk is not None:
            kw["target_trade_risk"] = s.target_trade_risk
        if s.wallet_start is not None:
            kw["wallet_start"] = float(s.wallet_start)
        if s.market_db:
            kw["market_db"] = s.market_db
        if s.history_dir:
            kw["history_dir"] = s.history_dir
        if s.pairs:
            kw["pairs"] = tuple(canon_pair(p) for p in s.pairs)
        if s.exit_modes is not None:
            kw["exit_modes"] = s.exit_modes
        if s.target_mode is not None:
            kw["target_mode"] = s.target_mode
        if out_dir is not None:
            o = str(Path(out_dir).resolve())
            kw.update(var_dir=o, kill_file=f"{o}/KILL.never", pause_file=f"{o}/PAUSE.never")
        ml1 = dict(cfg.ml1 or {})
        if ml1.get("aktif"):
            og = dict(ml1.get("ogrenme") or {})
            if out_dir is not None:
                ml1["paket_yolu"] = str(Path(out_dir).resolve() / "models" / "ml1" / "ml1_package.json")
                if og:
                    og["kuru"] = True
            else:
                ml1["paket_yolu"] = str(Path(tempfile.gettempdir()) / "trader-bt-ml1-yok" / "ml1_package.json")   # var olmayan yol; kimse yazmaz
                if og:
                    og["aktif"] = False                                  # ogrenici hic kurulmaz; gunlukleri kagit var dizinine dusemez
            if og:
                ml1["ogrenme"] = og
            kw["ml1"] = ml1
        return apply_overrides(cfg, **kw)

    def build_view(self, cfg: EngineConfig):
        s = self.spec
        if s.source == "store":
            return StoreSource(_resolve(cfg.market_db))
        return HistoricalSource(_resolve(cfg.history_dir), granularity=cfg.cost.granularity,
                                synthetic_rules=s.synthetic_rules)

    def _check_data(self, view, cfg: EngineConfig, end: datetime, tf: str) -> None:
        """Veri bitisi `end`'den once ise sessiz kisaltma yok: DataError (06 §10)."""
        step = timedelta(seconds=view.step_seconds())
        for p in cfg.pairs:
            rng = view.data_range(p, tf)
            if rng is None and cfg.mode == "paper" and p in cfg.optional_pairs:
                continue                                  # --env paper: istege bagli cift (hisse/emtia) verisiz kalabilir (kagitla ayni)
            if rng is None:
                raise DataError(f"{p} {tf}: veri yok")
            if rng[1] < end - tf_delta(tf):
                raise DataError(f"{p} {tf}: veri {rng[1]:%Y-%m-%d %H:%M}'de bitiyor, end={end:%Y-%m-%d %H:%M}")
            r4 = view.data_range(p, "4h")
            if r4 is None or r4[1] + tf_delta("4h") < floor_tf(end, "4h"):
                raise DataError(f"{p} 4h: veri end'den once bitiyor")
            lm = view.last_closed_minute(p)
            if lm is None or lm < end - step:
                raise DataError(f"{p}: adim verisi {lm}'de bitiyor, end={end}")

    # -- tek calisma
    def run_once(self, out_dir: Path, *, end: datetime | None = None, snapshot_at: datetime | None = None,
                 paranoid: bool = False) -> BacktestResult:
        s = self.spec
        t0 = time.perf_counter()
        end = end or s.end
        out_dir.mkdir(parents=True, exist_ok=True)
        led_path = out_dir / "ledger.sqlite"
        if led_path.exists():
            raise BacktestArgError("output_exists", f"{led_path} zaten var")
        envm = bool(s.env)
        if envm:
            if s.paranoid is not None or s.truncate_check is not None or s.fill_model != "native" or s.fee_mult != 1.0 \
                    or s.slip_bps is not None or s.record_shadow or s.veto != "none":
                raise BacktestArgError("bad_args", "--env: paranoid/truncate-check/legacy_compat/fee-mult/slip-bps/record-shadow/veto desteklenmez (eski yol icin `--env eski`)")
            check_holdout(s.start, end)          # mode="paper" ile kosuldugu icin motorun kendi kilidi (run_range) devre disi: burada zorunlu
        cfg = self.build_config(out_dir if envm else None)
        if envm:
            strategy = get_strategy(cfg.strategy, mode=cfg.mode, arms=cfg.arms or None)   # build_engine ile ayni
        else:
            strategy = get_strategy(s.strategy, mode="backtest")
        if s.fill_model == "legacy_compat" and s.strategy != "price_action_v1_full":
            log.warning("uyum kipi: capraz dogrulama yalniz price_action_v1_full ile anlamlidir")
        tf = s.tf
        clock = SimClock(s.start)
        raw = self.build_view(cfg)
        view = GuardedView(raw, clock, fill_model=cfg.cost.fill_model)
        self._check_data(raw, cfg, end, tf)
        # parametreler (ledger'a yazilir; strateji dogrular)
        params = {k: getattr(DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
        for k, v in s.params.items():
            if k not in params:
                raise BacktestArgError("bad_params", f"bilinmeyen parametre: {k}")
            params[k] = v
        params["trigger_tf"] = tf
        try:
            strategy.validate_params(params)
        except (ValueError, StrategyError) as e:
            raise BacktestArgError("bad_params", str(e)) from e
        label = make_label(strategy.info.name, strategy.info.version)
        ledger = L.open_ledger(str(led_path), cfg.bot, create=True, clock=clock.now)
        try:
            version_id = ledger.init_params(params, reason=f"{label} backtest")
        except L.LedgerError as e:
            ledger.close()
            raise BacktestArgError("bad_params", f"ledger parametre: {e}") from e
        if envm:                                            # kagitla ayni kaynak (bilesik strateji -> MultiArmSignalSource; strict=False)
            signals = signal_source_class(strategy)(view, strategy, strict=False)
        else:
            signals = PrecomputedSignalSource(raw, strategy, pairs=cfg.pairs, tf=tf, params=params, version_id=version_id,
                                              end=end, strict=True)
        paranoid_report = None
        if paranoid and s.paranoid is not None:
            paranoid_report = self.paranoid_check(raw, strategy, signals, cfg, params, version_id, end, out_dir)
        state = StateStore(":memory:", bot=cfg.bot, durability="off", lock=False)
        broker_cls = _CoarsePaperBroker if cfg.cost.fill_model == "legacy_compat" else PaperBroker
        tick_fn = None
        if cfg.cost.fill_model == "legacy_compat" and hasattr(raw, "tick_at"):
            raw.main_tf = tf                                # referans: tarihsel tick ana zaman dilimi mumlarindan
            tick_fn = view.tick_at
        pcfg = PaperConfig(cost=cfg.cost, mmr=K.LOCKED_CFG.maint_margin_rate, wallet_start=cfg.wallet_start)
        if envm and cfg.cost_overrides:                     # kagit: cift/seans kaymasi (build_engine ile ayni)
            from .engine import session_cost_broker
            broker = session_cost_broker(cfg, pcfg, view.rules, view.funding, clock)
        else:
            broker = broker_cls(pcfg, view.rules, view.funding, clock, tick_fn=tick_fn)
        if s.veto.startswith("ledger:"):
            veto = LedgerReplayVeto(_resolve(s.veto[len("ledger:"):]))
        else:
            veto = NoVeto()
        kill = Killswitch(str(out_dir / "KILL.never"), clock)
        entry_ref = None
        if cfg.cost.fill_model == "legacy_compat":
            def entry_ref(pair, D, row, _v=view):          # noqa: E306  (referans: sonraki adim acilisi)
                return _v.open_at(pair, D)
        if envm:
            from .pause import EntryPause
            pause = EntryPause(str(out_dir / "PAUSE.never"), clock, audit_path=str(out_dir / "pause_audit.jsonl"), bot=cfg.bot)
        else:
            pause = None
        eng = Engine(cfg, clock=clock, view=view, broker=broker, ledger=ledger, state=state, signals=signals,
                     strategy=strategy, veto=veto, kill=kill, status=None, entry_ref_fn=entry_ref, strict=not envm,
                     tick_fn=tick_fn, pause=pause)
        view_peek = [0]
        if cfg.cost.fill_model == "legacy_compat":
            eng.gate.state = _CompatEntryView(state, raw, clock, view_peek)
            eng.gate.broker = _CompatBrokerView(broker, eng.gate.state, tick_fn, cfg.cost.taker_fee)
        snap: list | None = None
        if snapshot_at is not None:
            orig = eng.decision_step
            holder: dict = {}

            def wrapped(D, _o=orig):
                _o(D)
                if D == snapshot_at:
                    holder["snap"] = [dict(pair=p.pair, side=p.side, status=p.status, entry_price=p.entry_price,
                                           qty=p.qty, initial_stop=p.initial_stop, current_stop=p.current_stop)
                                      for p in state.open_positions()]
            eng.decision_step = wrapped                     # type: ignore[method-assign]
        try:
            eng.start()
            summary = eng.run_range(s.start, end, active_only=s.skip_flat)
            eng.state.drain_outbox(ledger)
        finally:
            pass
        if snapshot_at is not None:
            snap = holder.get("snap")
        eq = {}
        trades = M.read_ledger_trades(led_path)
        for tid in trades["trade_id"]:
            v = state.kv_get(f"eq:{int(tid)}")
            if v is not None:
                eq[int(tid)] = float(v)
        open_pos = [dict(trade_id=p.trade_id, pair=p.pair, side=p.side, setup=p.setup, status=p.status,
                         entry_ts=iso_z(p.entry_ts) if p.entry_ts else None, entry_price=p.entry_price, qty=p.qty,
                         initial_stop=p.initial_stop, current_stop=p.current_stop) for p in state.open_positions()]
        tdf = M.enrich_trades(trades, eq)
        mtm_rows = list(eng.mtm.rows)
        ledger.close()
        state.close()
        dur = time.perf_counter() - t0
        counters = dict(summary.counters)
        coarse = cfg.cost.granularity == "15m"
        rules_source = "synthetic" if getattr(raw, "synthetic_rules", False) else ("store" if s.source == "store" else "snapshot")
        dr = {}
        for p in cfg.pairs:
            r = raw.data_range(p, tf)
            dr[p] = [iso_z(r[0]), iso_z(r[1])] if r else None
        meta = dict(
            id=s.id, flags=s.flags, git_commit=git_commit(), strategy=strategy.info.name,
            strategy_version=strategy.info.version, strategy_label=label, fill_model=cfg.cost.fill_model,
            granularity=cfg.cost.granularity, trigger_source=cfg.cost.trigger_source, trigger_tf=tf,
            rules_source=rules_source, coarse=coarse, peek_uses=view.peek_uses + view_peek[0], data_range=dr,
            engine_version=ENGINE_VERSION, param_version_id=version_id, duration_s=round(dur, 2),
            period=[iso_z(s.start), iso_z(end)], cost=dataclasses.asdict(cfg.cost), pairs=list(cfg.pairs),
            veto=s.veto, record_filtered=bool(s.record_filtered), skip_flat=bool(s.skip_flat),
            compat_label=("uyum calismasi, yerel sonuc degildir" if cfg.cost.fill_model == "legacy_compat" else None),
            paranoid=paranoid_report, no_paper_record=getattr(veto, "no_paper_record", [])[:200])
        if (s.flags or {}).get("eski_yol"):                 # `--env eski`: kagitla ayni DEGIL (damga + stderr uyarisi)
            meta["kagit_paritesi"] = False
            print("UYARI: --env eski: 5 ciftli taban yolu; sonuclar kagit botla ayni DEGIL (kagit_paritesi=false)", file=sys.stderr)
        if cfg.target_mode != "bar_close":                  # 24.11: eski yolda meta bayt bayt ayni
            meta["target_mode"] = cfg.target_mode
        if cfg.exit_modes:                                  # kip kapaliyken meta bayt bayt ayni
            meta["exit_modes"] = {k: {kk: vv for kk, vv in v.items() if vv is not None} for k, v in cfg.exit_modes.items()}
        slip = (s.slip_bps or 0.0) if cfg.cost.fill_model == "legacy_compat" else None
        met = M.compute_metrics(tdf, wallet_start=cfg.wallet_start, slip_bps=slip, fill_model=cfg.cost.fill_model,
                                period=(f"{s.start:%Y-%m-%d %H:%M:%S}", f"{end:%Y-%m-%d %H:%M:%S}"),
                                engine=dict(fill_model=cfg.cost.fill_model, granularity=cfg.cost.granularity, coarse=coarse,
                                            rules_source=rules_source, counters=counters))
        summ = dict(met)
        summ.update(id=s.id, strategy=strategy.info.name, strategy_version=strategy.info.version,
                    fee_eff=cfg.cost.taker_fee, n_open_at_end=len(open_pos), steps=summary.steps,
                    decisions=summary.decisions)
        tdf.to_csv(out_dir / "trades.csv", index=False)
        (out_dir / "summary.json").write_text(json.dumps(summ, indent=1, default=_json_default))
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, default=_json_default))
        (out_dir / "open_at_end.json").write_text(json.dumps(open_pos, indent=1, default=_json_default))
        if not envm:
            self._write_mtm(out_dir, mtm_rows, trades, met, cfg.wallet_start, s.start)
        return BacktestResult(out_dir=out_dir, summary=summ, meta=meta, trades=tdf, open_at_end=open_pos, snapshot=snap,
                              signals=signals)

    @staticmethod
    def _write_mtm(out_dir: Path, rows: list, trades: pd.DataFrame, met: dict, wallet_start: float,
                   start: datetime) -> None:
        """WP-3 6.4: YENI dosyalar (`equity_mtm.csv`, `mtm.json`); trades.csv/summary.json/open_at_end.json degismez."""
        with open(out_dir / "equity_mtm.csv", "w", encoding="utf-8", newline="") as f:
            f.write("ts,wallet,equity,equity_low,n_open\n")
            for ts, w, e, lo, n in rows:
                f.write(f"{iso_z(ts)},{w!r},{e!r},{lo!r},{int(n)}\n")
        eqs = [r[2] for r in rows]
        lows = [r[3] for r in rows]
        st = M.drawdown_stats(eqs, lows, wallet_start)
        loc = M.drawdown_locations(eqs, lows, wallet_start)

        def ts_at(curve_idx: int) -> str:
            return iso_z(start) if curve_idx <= 0 else iso_z(rows[curve_idx - 1][0])

        def ts_low(i: int) -> str:
            return iso_z(rows[i][0])

        closed = trades[trades["exit_ts"].notna()].sort_values(["exit_ts", "trade_id"]) if len(trades) else trades
        pnl = [float(x) for x in closed["realized_pnl"]] if len(closed) else []
        out = dict(schema="mtm/1", wallet_start=float(wallet_start), n_rows=len(rows),
                   max_dd_realized_pct=float(met.get("max_dd_pct", 0.0)), max_dd_realized_abs=float(met.get("max_dd_abs", 0.0)),
                   max_dd_mtm_pct=st["max_dd_mtm_pct"], max_dd_mtm_abs=st["max_dd_mtm_abs"],
                   max_dd_mtm_low_pct=st["max_dd_mtm_low_pct"], max_dd_mtm_low_abs=st["max_dd_mtm_low_abs"],
                   peak_ts=ts_at(loc["peak_idx"]) if rows else None,
                   trough_ts=ts_at(loc["trough_idx"]) if rows else None,
                   low_peak_ts=ts_at(loc["low_peak_idx"]) if rows else None,
                   low_trough_ts=ts_low(loc["low_trough_idx"]) if rows else None,
                   max_underwater_steps=st["max_underwater_steps"], max_consecutive_losses=M.max_consecutive_losses(pnl))
        (out_dir / "mtm.json").write_text(json.dumps(out, indent=1, default=_json_default))

    # -- --paranoid
    DISCRETE = ("signal", "setup", "side", "skip_reason", "regime", "rh_touches", "rl_touches")
    CONT = ("planned_entry", "planned_stop", "planned_target", "rr", "stop_dist_atr", "atr_tf", "atr_4h", "atr_ratio",
            "rh", "rl", "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr")

    def paranoid_check(self, raw, strategy, pre: PrecomputedSignalSource, cfg: EngineConfig, params: dict,
                       version_id: int, end: datetime, out_dir: Path) -> dict:
        """D orneklemi (tetik tf kapanislari, STARTUP sonrasi); Windowed (D'ye kesilmis) ile Precomputed karsilastirilir."""
        n = int(self.spec.paranoid or 200)
        tf = self.spec.tf
        info = strategy.info
        rng = random.Random(self.spec.seed)
        cand: dict[str, list[datetime]] = {}
        for p in cfg.pairs:
            tbl = pre._t.get(p)                                                        # noqa: SLF001
            if tbl is None:
                continue
            ds = [datetime.fromtimestamp(int(m) / 1000, tz=timezone.utc) + tf_delta(tf) for m in tbl.ms]
            ds = [d for d in ds if self.spec.start < d <= end and d >= ds[0] + tf_delta(tf) * info.warmup_bars[tf]]
            cand[p] = ds
        per = max(1, n // max(1, len(cand)))
        samples: list[tuple[datetime, str]] = []
        for p, ds in cand.items():
            k = min(per, len(ds))
            samples += [(d, p) for d in rng.sample(ds, k)] if k else []
        samples.sort()
        clock = SimClock(samples[0][0] if samples else self.spec.start)
        gv = GuardedView(raw, clock)
        win = WindowedSignalSource(gv, strategy, strict=True)
        diffs: list[dict] = []
        for D, p in samples:
            clock.set_time(D)
            fw = win.frame(p, D, params, version_id)
            fp = pre.frame(p, D, params, version_id)
            if fw.status != fp.status:
                diffs.append(dict(pair=p, D=iso_z(D), col="status", windowed=fw.status, precomputed=fp.status))
                continue
            if fw.status != "ok":
                continue
            a, b = fw.last, fp.last
            for c in self.DISCRETE:
                x, y = getattr(a, c), getattr(b, c)
                if x != y:
                    diffs.append(dict(pair=p, D=iso_z(D), col=c, windowed=x, precomputed=y))
            for c in self.CONT:
                x, y = getattr(a, c), getattr(b, c)
                if x is None or y is None or (isinstance(x, float) and math.isnan(x)) or (isinstance(y, float) and math.isnan(y)):
                    if not ((x is None or (isinstance(x, float) and math.isnan(x)))
                            and (y is None or (isinstance(y, float) and math.isnan(y)))):
                        diffs.append(dict(pair=p, D=iso_z(D), col=c, windowed=x, precomputed=y))
                    continue
                if abs(x - y) > 1e-9 * max(1.0, abs(x)):
                    diffs.append(dict(pair=p, D=iso_z(D), col=c, windowed=x, precomputed=y))
        rep = dict(n_samples=len(samples), n_diffs=len(diffs), seed=self.spec.seed)
        if diffs:
            (out_dir / "paranoid_diff.json").write_text(json.dumps(diffs[:500], indent=1, default=_json_default))
            raise LookaheadError(f"paranoid: {len(diffs)} fark (bkz. paranoid_diff.json)")
        return rep

    # -- --truncate-check
    def truncate_check(self, main: BacktestResult, end_prime: datetime) -> dict:
        s = self.spec
        if not (s.start < end_prime < s.end) or not is_tf_close(end_prime, s.tf):
            raise BacktestArgError("bad_truncate", "END' start..end arasinda bir tetik tf kapanisi olmali")
        out_b = main.out_dir / "truncate_check" / "B"
        if out_b.exists():
            raise BacktestArgError("output_exists", str(out_b))
        b = self.run_once(out_b, end=end_prime)
        diffs = compare_truncated(main, b, end_prime) + compare_tables(main.signals, b.signals, end_prime, s.tf)
        rep = dict(end_prime=iso_z(end_prime), n_diffs=len(diffs), n_trades_a=len(main.trades), n_trades_b=len(b.trades))
        (main.out_dir / "truncate_report.json").write_text(json.dumps(rep, indent=1))
        if diffs:
            pd.DataFrame(diffs).to_csv(main.out_dir / "truncate_diff.csv", index=False)
            raise TruncateError(f"truncate-check: {len(diffs)} fark")
        return rep


_DEC_COLS_DROP = ("id", "recorded_at", "supersedes_id")


def _decisions(path: Path) -> pd.DataFrame:
    import sqlite3
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        d = pd.read_sql("SELECT * FROM v_decisions", c)
    finally:
        c.close()
    return d.drop(columns=list(_DEC_COLS_DROP), errors="ignore")


def _close(x, y, rel=1e-12) -> bool:
    if x is None or y is None or (isinstance(x, float) and math.isnan(x)) or (isinstance(y, float) and math.isnan(y)):
        return (x is None or (isinstance(x, float) and math.isnan(x))) and (y is None or (isinstance(y, float) and math.isnan(y)))
    if isinstance(x, (int, float, np.integer, np.floating)) and isinstance(y, (int, float, np.integer, np.floating)):
        return abs(float(x) - float(y)) <= rel * max(1.0, abs(float(x)))
    return x == y


def compare_truncated(a: BacktestResult, b: BacktestResult, end_prime: datetime) -> list[dict]:
    """06 §6 kabul kosullari. `END'` ile ayni anda olan olaylar (adim END'te baslar) B'de islenmemistir: kesin esitlik
    `ts < END'` olaylari icindir; `entry_ts < END' <= exit_ts` olanlar B'de acik olmalidir."""
    diffs: list[dict] = []
    e = iso_z(end_prime)
    da, db = _decisions(a.out_dir / "ledger.sqlite"), _decisions(b.out_dir / "ledger.sqlite")
    da = da[da["bar_close_ts"] <= e]
    key = ["pair", "side", "setup", "trigger_tf", "bar_close_ts"]
    da, db = da.sort_values(key).reset_index(drop=True), db.sort_values(key).reset_index(drop=True)
    ka, kb = set(map(tuple, da[key].values)), set(map(tuple, db[key].values))
    for k in sorted(ka - kb):
        diffs.append(dict(kind="decision_only_in_A", key=str(k)))
    for k in sorted(kb - ka):
        diffs.append(dict(kind="decision_only_in_B", key=str(k)))
    m = da.merge(db, on=key, suffixes=("_a", "_b"))
    for c in [c for c in da.columns if c not in key]:
        for i, r in m.iterrows():
            if not _close(r[c + "_a"], r[c + "_b"]):
                diffs.append(dict(kind="decision_field", key=str(tuple(r[k] for k in key)), col=c,
                                  a=r[c + "_a"], b=r[c + "_b"]))
    ta, tb = a.trades, b.trades
    tk = ["pair", "side", "entry_ts"]
    done_a = ta[(ta["exit_ts"].notna()) & (ta["exit_ts"] < e)]
    bm = tb.set_index(tk)
    for _, r in done_a.iterrows():
        k = (r["pair"], r["side"], r["entry_ts"])
        if k not in bm.index:
            diffs.append(dict(kind="trade_missing_in_B", key=str(k)))
            continue
        rb = bm.loc[k]
        for c in ta.columns:
            if c in tk:
                continue
            if not _close(r[c], rb[c]):
                diffs.append(dict(kind="trade_field", key=str(k), col=c, a=r[c], b=rb[c]))
    ob = {(p["pair"], p["side"]): p for p in b.open_at_end}
    for p in (a.snapshot or []):
        q = ob.get((p["pair"], p["side"]))
        if q is None:
            diffs.append(dict(kind="open_missing_in_B", key=f"{p['pair']} {p['side']}"))
            continue
        for c in ("entry_price", "qty", "initial_stop", "current_stop"):
            if not _close(p[c], q[c]):
                diffs.append(dict(kind="open_field", key=f"{p['pair']} {p['side']}", col=c, a=p[c], b=q[c]))
    return diffs


def compare_tables(sa: PrecomputedSignalSource, sb: PrecomputedSignalSource, end_prime: datetime, tf: str) -> list[dict]:
    """Motor duzeyi ek denetim: END' ye kadar kapanmis tum barlar icin sinyal tablolari A ve B'de ayni olmali."""
    diffs: list[dict] = []
    for pair in sorted(set(sa._t) & set(sb._t)):                                   # noqa: SLF001
        ta, tb = sa.frame_table(pair, end_prime), sb.frame_table(pair, end_prime)
        if ta is None or tb is None:
            continue
        if len(ta) != len(tb):
            diffs.append(dict(kind="table_len", key=pair, a=len(ta), b=len(tb)))
            continue
        for c in ta.columns:
            x, y = ta[c].to_numpy(), tb[c].to_numpy()
            if x.dtype.kind in "fc":
                bad = ~(np.isclose(x.astype(float), y.astype(float), rtol=1e-12, atol=1e-12, equal_nan=True))
            else:
                bad = np.array([not (u == v or (u is None and v is None) or (isinstance(u, float) and isinstance(v, float)
                                                                           and math.isnan(u) and math.isnan(v)))
                                for u, v in zip(x, y)], dtype=bool)
            for i in np.flatnonzero(bad)[:5]:
                diffs.append(dict(kind="signal_table", key=f"{pair} {ta.index[i].isoformat()}", col=c, a=x[i], b=y[i]))
    return diffs


# --------------------------------------------------------------------------------------------- paper <-> backtest esitligi
EQ_FIELDS = ("entry_price", "qty", "exit_ts", "exit_price", "exit_reason", "fee_entry", "fee_exit", "funding_paid",
             "realized_pnl")


def equality_report(paper_ledger: Path, bt_trades: pd.DataFrame, no_paper_record: list) -> dict:
    """06 §8: anahtar (pair, side, entry_ts); alanlar 1e-9 goreli."""
    import sqlite3
    c = sqlite3.connect(f"file:{paper_ledger}?mode=ro", uri=True)
    try:
        pt = pd.read_sql("SELECT * FROM v_trades", c)
        pdc = pd.read_sql("SELECT pair, side, bar_close_ts, final_action, skip_reason, veto_reason FROM v_decisions", c)
    finally:
        c.close()
    k = ["pair", "side", "entry_ts"]
    P = {tuple(r[k]): r for _, r in pt.iterrows()}
    B = {tuple(r[k]): r for _, r in bt_trades.iterrows()}
    diffs, ok = [], 0
    npr = {(x[0], x[1], x[2]) for x in no_paper_record}
    for key in sorted(set(P) | set(B)):
        if key in P and key in B:
            bad = [f for f in EQ_FIELDS if not _close(P[key][f], B[key][f], 1e-9)]
            if bad:
                diffs.append(dict(key=str(key), cls="unexplained", fields=bad))
            else:
                ok += 1
        elif key in B:
            cls = "unexplained"
            if (key[0], key[1], key[2]) in npr:
                cls = "no_paper_record"
            else:
                m = pdc[(pdc["pair"] == key[0]) & (pdc["side"] == key[1]) & (pdc["bar_close_ts"] == key[2])]
                if len(m) and (m["skip_reason"].isin(["entry_gate_closed", "other"])).any():
                    cls = "paper_gap"
            diffs.append(dict(key=str(key), cls=cls, side="backtest_only"))
        else:
            diffs.append(dict(key=str(key), cls="unexplained", side="paper_only"))
    unexplained = [d for d in diffs if d["cls"] == "unexplained"]
    return dict(n_paper=len(P), n_backtest=len(B), n_equal=ok, n_diffs=len(diffs), n_unexplained=len(unexplained),
                diffs=diffs[:200], equal=(len(unexplained) == 0))


# --------------------------------------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="trader_engine backtest")
    ap.add_argument("--id", required=True)
    ap.add_argument("--period", default=None, help="IS | WF | YYYYMMDD-YYYYMMDD")
    ap.add_argument("--start", default=None, help="YYYYMMDD (period yerine; HOLDOUT yine reddedilir)")
    ap.add_argument("--end", default=None, help="YYYYMMDD")
    ap.add_argument("--strategy", default="price_action_v1", help="yalniz --env eski")
    ap.add_argument("--tf", default="1h", choices=["1h", "15m"], help="yalniz --env eski")
    ap.add_argument("--fill-model", default="native", choices=["native", "legacy_compat"])
    ap.add_argument("--fee-mult", type=float, default=1.0)
    ap.add_argument("--slip-bps", type=float, default=None)
    ap.add_argument("--params", default="")
    ap.add_argument("--granularity", default=None, choices=["1m", "15m"])
    ap.add_argument("--trigger-source", default=None, choices=["last", "mark"], help="native: varsayilan 1m->mark, 15m->last")
    ap.add_argument("--source", default="history", choices=["history", "store"])
    ap.add_argument("--market-db", default=None)
    ap.add_argument("--history-dir", default=None)
    ap.add_argument("--synthetic-rules", action="store_true")
    ap.add_argument("--target-trade-risk", type=float, default=None,
                    help="yalniz --env eski: varsayilan kilitli hedef risk (0.014); verilirse (0, 0.014] icinde, orn. kagit 0.005")
    ap.add_argument("--veto", default="none")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--record-filtered", dest="record_filtered", action="store_true", default=True)
    g.add_argument("--no-record-filtered", dest="record_filtered", action="store_false")
    ap.add_argument("--no-skip-flat", action="store_true")
    ap.add_argument("--record-shadow", action="store_true",
                    help="WP-3: golge karar satirlari (regime, r1_disabled, same_bar_reentry); tf_15m geri testte yok")
    ap.add_argument("--paranoid", nargs="?", const=200, type=int, default=None)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--truncate-check", default=None, help="END' (YYYYMMDDTHH)")
    ap.add_argument("--from-paper-ledger", default=None)
    ap.add_argument("--env", default="paper", choices=["paper", "eski"],
                    help="varsayilan paper = kagit botla ayni yapilandirma (config/engine.paper.json: arms/kume/maliyet + cok kurullu sinyal kaynagi); "
                         "eski = 5 ciftli taban yolu (yalniz capraz dogrulama/arastirma)")
    ap.add_argument("--wallet-start", type=float, default=None, help="yalniz --env ile: baslangic ozsermayesi")
    ap.add_argument("--out-root", default=None, help="varsayilan: <var_dir>/backtests")
    ap.add_argument("--config-dir", default="config")
    ap.add_argument("--pairs", default=None, help="virgullu kanonik ciftler (BTC/USDT,ETH/USDT)")
    ap.add_argument("--exit-modes", default=None,
                    help='cikis kipleri JSON: {"default":{"breakeven":true,"partial":{"trigger_r":1.5,"frac":0.5}}}; verilmezse kapali')
    ap.add_argument("--target-mode", default=None, choices=["bar_close", "resting"],
                    help="24.11: hedef bekleyen emir (resting; basa-bas/kismi 15 dk adiminda) ya da eski bar_close; verilmezse yapilandirma degeri")
    return ap


def spec_from_args(a: argparse.Namespace, argv: list[str]) -> BacktestSpec:
    if a.period:
        start, end = parse_period(a.period)
        period = a.period
    elif a.start and a.end:
        start, end = _ymd(a.start), _ymd(a.end)
        check_holdout(start, end)
        period = f"{a.start}-{a.end}"
    else:
        raise BacktestArgError("bad_period", "--period ya da --start/--end gerekli")
    try:
        params = json.loads(a.params) if a.params else {}
    except json.JSONDecodeError as e:
        raise BacktestArgError("bad_params", f"--params JSON degil: {e}") from e
    if a.fill_model == "legacy_compat" and a.granularity not in (None, "15m"):
        raise BacktestArgError("bad_args", "legacy_compat: --granularity 15m zorunlu")
    trunc = parse_end_prime(a.truncate_check) if a.truncate_check else None
    try:
        exit_modes = json.loads(a.exit_modes) if getattr(a, "exit_modes", None) else None
    except json.JSONDecodeError as e:
        raise BacktestArgError("bad_args", f"--exit-modes JSON degil: {e}") from e
    eski = a.env == "eski"                           # P6-03 (Paket 2 / E): varsayilan kagit ortami; eski taban yol ACIKCA istenir
    env = None if eski else a.env
    if a.wallet_start is not None and not env:
        raise BacktestArgError("bad_args", "--wallet-start yalniz --env paper ile (eski yolda yok)")
    return BacktestSpec(
        id=a.id, start=start, end=end, period=period, strategy=a.strategy, tf=a.tf, fill_model=a.fill_model,
        fee_mult=a.fee_mult, slip_bps=a.slip_bps, params=params, granularity=a.granularity, trigger_source=a.trigger_source, source=a.source,
        market_db=a.market_db, history_dir=a.history_dir, synthetic_rules=a.synthetic_rules, veto=a.veto,
        record_filtered=a.record_filtered, skip_flat=not a.no_skip_flat, paranoid=a.paranoid, seed=a.seed,
        truncate_check=trunc, from_paper_ledger=a.from_paper_ledger, out_root=a.out_root, config_dir=a.config_dir,
        pairs=tuple(x.strip() for x in a.pairs.split(",")) if a.pairs else None,
        target_trade_risk=a.target_trade_risk, record_shadow=bool(a.record_shadow),
        env=env, wallet_start=a.wallet_start, flags=dict(argv=list(argv), **({"eski_yol": True} if eski else {})), exit_modes=exit_modes,
        target_mode=getattr(a, "target_mode", None))


def run_spec(spec: BacktestSpec) -> BacktestResult:
    """Programatik giris (research/run_bt_engine.py): hata siniflarini yayar."""
    runner = BacktestRunner(spec)
    root = spec.out_root or f"{runner.build_config().var_dir}/backtests"
    out = _resolve(root) / spec.id
    if out.exists():
        raise BacktestArgError("output_exists", f"{out} zaten var")
    res = runner.run_once(out, paranoid=spec.paranoid is not None, snapshot_at=spec.truncate_check)
    if spec.truncate_check is not None:
        res.meta["truncate_check"] = runner.truncate_check(res, spec.truncate_check)
        (out / "meta.json").write_text(json.dumps(res.meta, indent=1, default=_json_default))
    if spec.from_paper_ledger:
        rep = equality_report(_resolve(spec.from_paper_ledger), res.trades,
                              [tuple(x) for x in res.meta.get("no_paper_record", [])])
        (out / "equality_report.json").write_text(json.dumps(rep, indent=1, default=_json_default))
        if not rep["equal"]:
            raise EqualityError(f"paper esitligi: {rep['n_unexplained']} aciklanamayan fark")
    return res


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--":                     # `trader_engine backtest -- --id ...` (REMAINDER)
        argv = argv[1:]
    ap = build_parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 0) if e.code in (0, None) else EXIT_ARG
    try:
        spec = spec_from_args(a, argv)
        res = run_spec(spec)
    except BacktestArgError as e:
        print(f"{e.code}: {e}", file=sys.stderr)
        return EXIT_ARG
    except (ConfigError, StrategyError) as e:
        print(f"hata: {e}", file=sys.stderr)
        return EXIT_ARG
    except LookaheadError as e:
        print(f"lookahead: {e}", file=sys.stderr)
        return EXIT_LOOKAHEAD
    except DataError as e:
        print(f"veri hatasi: {e}", file=sys.stderr)
        return EXIT_DATA
    except TruncateError as e:
        print(f"truncate_check: {e}", file=sys.stderr)
        return EXIT_TRUNCATE
    except EqualityError as e:
        print(f"esitlik: {e}", file=sys.stderr)
        return EXIT_EQUALITY
    s = res.summary
    print(f"[{spec.id}] n={s.get('n_trades')} expR={s.get('expectancy_R')} PF={s.get('profit_factor')} "
          f"DD={s.get('max_dd_pct')} sure={res.meta['duration_s']}s", flush=True)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
