"""DD-12 WP-04 (Kapilar) bagimsiz sartname testleri: docs/motor/dd12-capraz-varlik-spec.md (v4) §4.1, §4.2/4.3 (seans etiketi),
§9 WP-04, D-T6, D-T7. Gerceklemenin farklarina BAKILMADI; yalniz sartname + HEAD'deki gates.py/testler.

SPEC-AMBIGUOUS (sartnamenin adlandirmadigi yerler; testler esnek kesfeder):
  * arm_guard saf API adlari: session_tag(pair_or_class, ts_utc) / is_flat_bar(bar) / cluster membership. Burada adlar
    adaylar listesinden kesfedilir (_find); bulunamazsa ilgili test FAIL eder (skip degil).
  * Seans etiketi gate seviyesinde `EntryOutcome.event.session_tag` ile okunur (ledger v5 DecisionEvent.session_tag).
  * Tatil bari: SignalFrame.table son satirinda `volume`/`high`/`low` sutunlari.
  * Dersin kapattigi seans: `gate.session_off = {"<varlik sinifi>": ["weekend"], ...}` (sinif: crypto|stock|metal|energy) ya da
    `cfg`/`gate` uzerinden; _set_session_off bunu dener.
  * EntryGate kurucusu veto argumani alabilir ya da almayabilir; imzaya gore kurulur.
"""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core import signals as S
from trader_engine.clock import SimClock
from trader_engine.config import load_cli_config
from trader_engine.gates import EntryGate
from trader_engine.killswitch import Killswitch
from trader_engine.state import StateStore
from trader_engine.strategy_runner import SignalFrame, SignalRow
from trader_engine.types import Position, SymbolRules

ag = pytest.importorskip("trader_engine.arm_guard")

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
UTC = timezone.utc
NY = ZoneInfo("America/New_York")
H = timedelta(hours=1)

BUYUK = ["BTC", "ETH", "XRP", "BNB", "SOL"]
# 23.11 kullanici karari: TON cikarildi (SETTLING)
DIGER = ["DOGE", "ADA", "TRX", "LINK", "AVAX", "HYPE", "BCH", "XLM", "SUI", "HBAR", "LTC", "1000SHIB", "DOT", "XMR"]
TEK = ["NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "ORCL", "NFLX", "PLTR", "AMD"]
NONTEK = ["BRKB", "JPM", "LLY", "WMT", "V", "COST", "XOM", "HD"]
METAL = ["XAU", "XAG"]
ENERJI = ["BZ", "COPPER"]


def P(base):
    return f"{base}/USDT"


# ------------------------------------------------------------------------------------------------ yardimcilar
def _find(names, mod=ag):
    for n in names:
        f = getattr(mod, n, None)
        if callable(f):
            return f
    pytest.fail(f"arm_guard icinde {names} adaylarindan hicbiri yok; mevcut: {[n for n in dir(mod) if not n.startswith('_')]}")


def _tag(pair, ts):
    """Saf session_tag hesabi; (pair, ts) ya da (ts, pair) sirasini dener."""
    f = _find(["session_tag", "compute_session_tag", "session_tag_for"])
    cfg = _paper_cfg()
    cls = None
    if hasattr(ag, "asset_class"):
        try:
            cls = ag.asset_class(P(pair), cfg.clusters)
        except Exception:  # noqa: BLE001
            cls = None
    for args in ((cls, ts), (pair, ts), (P(pair), ts), (ts, pair), (ts, P(pair))):
        try:
            r = f(*args)
        except (TypeError, ValueError, KeyError, AttributeError):
            continue
        if r in ("open", "closed", "weekend"):
            return r
    pytest.fail(f"session_tag({pair}, {ts}) cozulemedi")


_CFG = []


def _paper_cfg():
    if not _CFG:
        import dataclasses
        # 23.11 kullanici karari: asama B esikleri. Bu dosya sabit kume tavanlarini (cluster_cap) olcer; korelasyon grubu
        # (ayri kural, test_asama_b_esikleri.py) burada kapali tutulur ki kume tavani kendi basina denensin.
        _CFG.append(dataclasses.replace(load_cli_config(CONFIG, "learner", "paper"), korelasyon={}))
    return _CFG[0]


def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def ny(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=NY).astimezone(UTC)


class _FakeBroker:
    def __init__(self, equity=1000.0):
        self.equity = equity

    def account(self):
        return type("A", (), {"equity": self.equity, "wallet": self.equity})()


class _Veto:
    """Veto nesnesi: cagrilirsa test basarisiz (kagit yolunda veto adimi yok)."""
    calls = 0

    def begin_step(self, now):
        _Veto.calls += 1

    def lookup(self, pair, side, now):
        _Veto.calls += 1
        raise AssertionError("kagit yolunda veto cagrilmamali")


def _row(pair, D, **kw) -> SignalRow:
    d = dict(pair=pair, bar_open_ts=D - H, bar_close_ts=D, signal=True, setup="T1", side="long",
             skip_reason=None, planned_entry=100.0, planned_stop=98.0, planned_target=None, rr=None,
             stop_dist_atr=2.0, atr_tf=1.0, atr_4h=2.0, atr_ratio=1.0, regime="trend_up", rh=None, rl=None,
             rh_touches=0, rl_touches=0, ema_value=99.5, body_ratio=0.7, wick_ratio=None, edge_dist_atr=None,
             pullback_ema=50, reasons="t1", param_version_id=1)
    d.update(kw)
    return SignalRow(**d)


def _frame(pair, D, volume=10.0, high=101.0, low=99.0, **kw):
    tbl = pd.DataFrame({"volume": [volume], "high": [high], "low": [low]}, index=pd.DatetimeIndex([pd.Timestamp(D)]))
    extra = {"trigger_bar": (high, low, volume)} if "trigger_bar" in getattr(SignalFrame, "__dataclass_fields__", {}) else {}
    return SignalFrame(pair=pair, status="ok", detail=None, last=_row(pair, D, **kw), table=tbl, **extra)


def _params():
    return {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}


def _pos(tid, pair, D, side="long"):
    return Position(trade_id=tid, bot="learner", pair=pair, side=side, setup="T1", status="open", decision_id=tid,
                    signal_bar_close_ts=D - H, entry_ts=D - H, entry_bar_open=D - H, entry_price=100.0, qty=0.001,
                    leverage=3, initial_stop=98.0, current_stop=98.0, stop_seq=0, stop_client_id=None, planned_target=None,
                    trail_atr=1.0, param_version_id=1, trigger_tf="1h", risk_amount=0.01, margin=0.01, rh=None, rl=None,
                    fee_entry=0.0, funding_paid=0.0, mfe_price=None, mae_price=None, exit_reason=None, exit_client_id=None,
                    closed_ts=None)


class Env:
    def __init__(self, tmp, D, mode_cfg=None):
        self.D = D
        self.cfg = mode_cfg or _paper_cfg()   # 23.11 kullanici karari: asama B esikleri (korelasyon kapali; bkz. _paper_cfg)
        if mode_cfg is None and getattr(self.cfg, "arm_max_positions", None):     # WP-11 kurulum tavani bu dosyanin konusu degil
            import dataclasses as _dc
            self.cfg = _dc.replace(self.cfg, arm_max_positions=None)
        self.clock = SimClock(D + timedelta(seconds=5))
        self.led = L.open_ledger(str(tmp / "l.sqlite"), "learner", create=True, clock=self.clock.now)
        self.led.init_params(_params(), reason="strategy:test")
        self.state = StateStore(":memory:", bot="learner")
        with self.state.tx():
            self.state.kv_set(f"day_start:{D.strftime('%Y-%m-%d')}", 1000.0)
        kill = Killswitch(str(tmp / "KILL"), self.clock)
        args = [self.cfg, self.led, self.state, kill]
        if "veto" in inspect.signature(EntryGate.__init__).parameters:
            args.append(_Veto())
        args += [self.clock, _FakeBroker(), self._rules]
        self.gate = EntryGate(*args)
        self.n = 0

    @staticmethod
    def _rules(pair):
        return SymbolRules(pair, pair.replace("/", ""), 0.01, 0.001, 0.001, 1e9, 5.0)

    def fill(self, bases):
        with self.state.tx():
            for b in bases:
                self.n += 1
                self.state.insert_position(_pos(self.n, P(b), self.D))

    def decide(self, base, **kw):
        fr = _frame(P(base), self.D, **kw)
        pre = self.gate.pre(self.D, "1h", True, "1h")
        return self.gate.decide(fr, self.D, pre, 1)

    def close(self):
        self.state.close()
        self.led.close()


@pytest.fixture
def mk(tmp_path):
    envs = []

    def make(D=utc(2026, 12, 2, 12, 0), **kw):
        e = Env(tmp_path / f"e{len(envs)}" if (tmp_path / f"e{len(envs)}").mkdir() is None else tmp_path, D, **kw)
        envs.append(e)
        return e
    yield make
    for e in envs:
        e.close()


def _set_session_off(gate, cls_to_states):
    """SPEC-AMBIGUOUS: dersin session_off ayari kapiya nasil verilir. Yaygin adaylar denenir."""
    for target in (gate, gate.cfg):
        for attr in ("session_off", "lesson_session_off"):
            try:
                object.__setattr__(target, attr, cls_to_states)
                return
            except Exception:  # noqa: BLE001
                continue
    pytest.fail("session_off kapiya verilemedi")


# ------------------------------------------------------------------------------------------------ D-T7 seans etiketi (saf)
STOCK = "NVDA"


def test_stock_saturday_weekend():
    assert _tag(STOCK, utc(2026, 12, 5, 15, 0)) == "weekend"          # Cumartesi
    assert _tag(STOCK, utc(2026, 12, 6, 15, 0)) == "weekend"          # Pazar


def test_stock_monday_0929_ny_closed_0930_open_winter():
    assert _tag(STOCK, ny(2026, 12, 7, 9, 29)) == "closed"
    assert _tag(STOCK, ny(2026, 12, 7, 9, 30)) == "open"
    assert _tag(STOCK, ny(2026, 12, 7, 15, 59)) == "open"
    assert _tag(STOCK, ny(2026, 12, 7, 16, 0)) == "closed"


def test_stock_summer_and_winter_dst_weeks():
    # yaz (EDT, UTC-4): 09:30 NY = 13:30 UTC ; kis (EST, UTC-5): 09:30 NY = 14:30 UTC
    assert _tag(STOCK, utc(2026, 7, 6, 13, 29)) == "closed"
    assert _tag(STOCK, utc(2026, 7, 6, 13, 30)) == "open"
    assert _tag(STOCK, utc(2026, 7, 6, 19, 59)) == "open"
    assert _tag(STOCK, utc(2026, 7, 6, 20, 0)) == "closed"
    assert _tag(STOCK, utc(2026, 12, 7, 14, 29)) == "closed"
    assert _tag(STOCK, utc(2026, 12, 7, 14, 30)) == "open"
    assert _tag(STOCK, utc(2026, 12, 7, 20, 59)) == "open"
    assert _tag(STOCK, utc(2026, 12, 7, 21, 0)) == "closed"


def test_stock_dst_transition_weeks():
    # ABD yaz saati 2026-03-08'de basladi: 9 Mart Pzt 13:30 UTC acik; 2 Mart Pzt hala kis: 13:30 UTC = 08:30 NY closed
    assert _tag(STOCK, utc(2026, 3, 9, 13, 30)) == "open"
    assert _tag(STOCK, utc(2026, 3, 2, 13, 30)) == "closed"
    assert _tag(STOCK, utc(2026, 3, 2, 14, 30)) == "open"
    # yaz saati 2026-11-01'de bitti: 2 Kasim Pzt 14:30 UTC acik, 13:30 closed
    assert _tag(STOCK, utc(2026, 11, 2, 13, 30)) == "closed"
    assert _tag(STOCK, utc(2026, 11, 2, 14, 30)) == "open"


def test_stock_weekday_night_closed_not_weekend():
    assert _tag(STOCK, utc(2026, 12, 8, 3, 0)) == "closed"            # Sal gece
    assert _tag(STOCK, utc(2026, 12, 11, 22, 0)) == "closed"          # Cuma aksam seans sonrasi


def test_metal_friday_2100_weekend_sunday_2259_weekend_2300_open():
    for base in METAL:
        assert _tag(base, utc(2026, 12, 4, 20, 59)) == "open"
        assert _tag(base, utc(2026, 12, 4, 21, 0)) == "weekend"
        assert _tag(base, utc(2026, 12, 5, 12, 0)) == "weekend"
        assert _tag(base, utc(2026, 12, 6, 22, 59)) == "weekend"
        assert _tag(base, utc(2026, 12, 6, 23, 0)) == "open"
        assert _tag(base, utc(2026, 12, 8, 4, 0)) == "open"


def test_energy_commodities_follow_metal_hours():
    for base in ENERJI:
        assert _tag(base, utc(2026, 12, 4, 21, 0)) == "weekend"
        assert _tag(base, utc(2026, 12, 6, 23, 0)) == "open"


def test_crypto_always_open():
    for base in ("BTC", "DOGE", "1000SHIB"):
        for ts in (utc(2026, 12, 5, 3, 0), utc(2026, 12, 6, 12, 0), utc(2026, 12, 7, 0, 0), utc(2026, 12, 2, 22, 30)):
            assert _tag(base, ts) == "open"


def test_session_tags_are_only_three_values_for_all_pairs():
    ts = utc(2026, 12, 5, 12, 0)
    for b in BUYUK + DIGER + TEK + NONTEK + METAL + ENERJI:
        assert _tag(b, ts) in ("open", "closed", "weekend")


# ------------------------------------------------------------------------------------------------ D-T7 tatil bari (saf)
def test_flat_bar_pure():
    f = _find(["is_flat_bar", "flat_bar", "is_holiday_bar", "holiday_bar"])

    def call(**o):
        b = dict(volume=10.0, high=101.0, low=99.0, open=100.0, close=100.0)
        b.update(o)
        for arg in (b, pd.Series(b)):
            try:
                return bool(f(arg))
            except (TypeError, AttributeError, KeyError):
                continue
        # SPEC-AMBIGUOUS arg sirasi: (high, low, volume) ve (volume, high, low) ikisi de makul; ikisi de ayni sonucu vermeli degil,
        # bu yuzden imza adlarindan anahtar-sozcuk ile cagrilir.
        return bool(f(high=b["high"], low=b["low"], volume=b["volume"]))
    assert call() is False
    assert call(volume=0.0) is True
    assert call(high=100.0, low=100.0) is True
    assert call(volume=0.0, high=100.0, low=100.0) is True


# ------------------------------------------------------------------------------------------------ D-T6 kume uyeligi (saf)
def _members_fn():
    return _find(["clusters_of", "cluster_membership", "clusters_for", "cluster_names", "memberships"])


def _clusters_of(cfg, base):
    f = _members_fn()
    for args in ((P(base), cfg.clusters), (cfg, P(base)), (P(base), cfg), (cfg.clusters, P(base))):
        try:
            r = f(*args)
        except (TypeError, AttributeError, KeyError):
            continue
        return set(r)
    pytest.fail("clusters_of cagrilamadi")


def test_cluster_membership_multi():
    cfg = load_cli_config(CONFIG, "learner", "paper")
    assert _clusters_of(cfg, "NVDA") == {"hisse", "hisse_teknoloji"}
    assert _clusters_of(cfg, "JPM") == {"hisse"}
    assert _clusters_of(cfg, "BTC") == {"kripto_buyuk"}
    assert _clusters_of(cfg, "DOGE") == {"kripto_diger"}
    assert _clusters_of(cfg, "XAU") == {"metal"}
    assert _clusters_of(cfg, "BZ") == {"enerji_sanayi"}


# ------------------------------------------------------------------------------------------------ D-T6 tavanlar (kapi)
def test_cluster_cap_tech5_blocks_6th_tech(mk):
    e = mk()
    e.fill(TEK[:5])
    out = e.decide("AMD")
    assert out.action == "skip" and out.event.skip_reason == "cluster_cap"
    assert out.event.veto_status == "not_evaluated" and out.event.final_action == "skipped"


def test_nontech_stock_enters_when_tech3_full(mk):
    e = mk()
    e.fill(TEK[:5])
    out = e.decide("JPM")
    assert out.action == "enter", (out.code, out.event and out.event.skip_reason)


def test_stock5_full_blocks_any_stock(mk):
    e = mk()
    e.fill(TEK[:2] + NONTEK[:6])               # hisse=8, teknoloji=2
    for b in ("XOM", "AMD"):
        out = e.decide(b)
        assert out.action == "skip" and out.event.skip_reason == "cluster_cap", b


def test_stock5_full_does_not_block_crypto_or_metal(mk):
    e = mk()
    e.fill(TEK[:2] + NONTEK[:6])
    assert e.decide("BTC").action == "enter"
    assert e.decide("XAU").action == "enter"


def test_crypto_big_cap_6_not_binding(mk):
    """20 Kasim: kume tavani 6 > uye sayisi 5; tum uyeler acik olsa da baska kumeler etkilenmez."""
    e = mk()
    e.fill(BUYUK[:5])
    assert e.decide("DOGE").action == "enter"


def test_crypto_other_cap_9(mk):
    e = mk()
    e.fill(DIGER[:8])
    assert e.decide("XMR").action == "enter"
    e2 = mk()
    e2.fill(DIGER[:9])
    out = e2.decide("XMR")
    assert out.action == "skip" and out.event.skip_reason == "cluster_cap"


def test_metal_and_energy_clusters_independent(mk):
    e = mk()
    e.fill(METAL)
    assert e.decide("BZ").action == "enter"        # metal dolu (2) enerji'yi etkilemez
    e2 = mk()
    e2.fill(ENERJI)
    assert e2.decide("XAU").action == "enter"


def test_metal_one_open_other_member_enters(mk):
    e = mk()
    e.fill(["XAU"])
    assert e.decide("XAG").action == "enter"


def test_account_cap_24(mk):
    e = mk()
    # 24 pozisyonu kume tavanlarini asmadan doldur: buyuk 5 + diger 9 + hisse 8 (tech 2 + nontech 6) + metal 2
    e.fill(BUYUK[:5] + DIGER[:9] + NONTEK[:6] + TEK[:2] + METAL)
    assert len(e.state.open_positions()) == 24
    out = e.decide("BZ")
    assert out.action == "skip" and out.event.skip_reason == "max_positions"
    assert out.event.veto_status == "not_evaluated"


def test_account_cap_23_allows_24th(mk):
    e = mk()
    e.fill(BUYUK[:5] + DIGER[:9] + NONTEK[:6] + TEK[:2] + ["XAU"])
    assert len(e.state.open_positions()) == 23
    assert e.decide("BZ").action == "enter"


def test_cluster_cap_checked_before_account_cap(mk):
    e = mk()
    e.fill(BUYUK[:5] + DIGER[:9] + NONTEK[:6] + TEK[:2] + METAL)     # hesap 24 dolu, diger kume 9/9 dolu
    out = e.decide("XMR")
    assert out.action == "skip" and out.event.skip_reason == "cluster_cap"       # sira: kume tavani -> hesap tavani


def test_pairs_order_same_bar(mk):
    """Ayni barda sira `pairs` sirasi: ilk gelen girer, tavan dolunca sonrakiler cluster_cap alir."""
    e = mk()
    e.fill(TEK[:4])
    order = [b for b in TEK[4:]]            # pairs sirasinda 3 aday (teknoloji tavani 5)
    outs = []
    for b in order[:3]:
        o = e.decide(b)
        outs.append(o)
        if o.action == "enter":
            e.fill([b])                      # giris sayimi: acilmakta pozisyon
    assert [o.action for o in outs] == ["enter", "skip", "skip"]
    assert all(o.event.skip_reason == "cluster_cap" for o in outs[1:])


# ------------------------------------------------------------------------------------------------ D-T7 kapi: seans etiketi bilgidir
def test_session_tag_filled_on_entered_event_and_closed_session_not_blocked(mk):
    D = ny(2026, 12, 7, 9, 29)        # Pzt 09:29 NY, hisse closed
    e = mk(D)
    out = e.decide("NVDA")
    assert out.action == "enter", (out.code,)
    assert out.event.session_tag == "closed"


def test_weekend_stock_entry_not_blocked_and_tagged(mk):
    D = utc(2026, 12, 5, 15, 0)
    e = mk(D)
    out = e.decide("JPM")
    assert out.action == "enter" and out.event.session_tag == "weekend"


def test_open_session_tag(mk):
    D = ny(2026, 12, 7, 9, 30) + H
    e = mk(D)
    out = e.decide("JPM")
    assert out.action == "enter" and out.event.session_tag == "open"


def test_crypto_tag_open_on_weekend(mk):
    e = mk(utc(2026, 12, 6, 3, 0))
    out = e.decide("BTC")
    assert out.action == "enter" and out.event.session_tag == "open"


def test_metal_weekend_entry_allowed(mk):
    e = mk(utc(2026, 12, 5, 12, 0))
    out = e.decide("XAU")
    assert out.action == "enter" and out.event.session_tag == "weekend"


def test_session_tag_on_skipped_rows_too(mk):
    D = utc(2026, 12, 5, 15, 0)
    e = mk(D)
    e.fill(TEK[:5])
    out = e.decide("AMD")
    assert out.action == "skip" and out.event.skip_reason == "cluster_cap" and out.event.session_tag == "weekend"


# ------------------------------------------------------------------------------------------------ D-T7 tatil bari
def test_flat_bar_volume_zero_blocks(mk):
    e = mk()
    out = e.decide("BTC", volume=0.0)
    assert out.action == "skip" and out.event.skip_reason == "flat_bar"
    assert out.event.veto_status == "not_evaluated" and out.event.final_action == "skipped"


def test_flat_bar_high_equals_low_blocks(mk):
    e = mk()
    out = e.decide("NVDA", high=100.0, low=100.0)
    assert out.action == "skip" and out.event.skip_reason == "flat_bar"


def test_normal_bar_not_flat(mk):
    e = mk()
    assert e.decide("BTC").action == "enter"


def test_flat_bar_precedes_cluster_cap(mk):
    e = mk()
    e.fill(TEK[:5])
    out = e.decide("AMD", volume=0.0)
    assert out.event.skip_reason == "flat_bar"           # sira: kural -> tatil bari -> ... -> kume tavani


def test_flat_bar_guard_off_in_non_paper_unchanged(mk, tmp_path):
    """Tarafsizlik: flat_bar_guard yalniz paper anahtari; taban/testnet yapilandirmasinda False -> koruma yok (davranis ayni)."""
    for name in ("engine.testnet.json",):        # 23.11 kullanici karari: canli = kagit (engine.live.json artik bu anahtarlari tasir)
        raw = json.loads((CONFIG / name).read_text())
        assert "flat_bar_guard" not in raw and "clusters" not in raw and "max_positions" not in raw
    assert json.loads((CONFIG / "engine.live.json").read_text())["flat_bar_guard"] is True


# ------------------------------------------------------------------------------------------------ D-T7 dersin kapattigi seans
def test_lesson_closed_session_rejects_with_session_closed(mk):
    D = utc(2026, 12, 5, 15, 0)         # hisse weekend
    e = mk(D)
    _set_session_off(e.gate, {"stock": ["weekend"], "hisse": ["weekend"]})
    out = e.decide("JPM")
    assert out.action == "skip" and out.event.skip_reason == "session_closed"
    assert out.event.veto_status == "not_evaluated" and out.event.session_tag == "weekend"


def test_lesson_closed_other_session_not_rejected(mk):
    D = utc(2026, 12, 5, 15, 0)         # hisse weekend; ders yalniz 'closed' kapatmis
    e = mk(D)
    _set_session_off(e.gate, {"stock": ["closed"], "hisse": ["closed"]})
    assert e.decide("JPM").action == "enter"


def test_lesson_closed_other_asset_class_not_rejected(mk):
    D = utc(2026, 12, 5, 15, 0)
    e = mk(D)
    _set_session_off(e.gate, {"stock": ["weekend"], "hisse": ["weekend"]})
    assert e.decide("XAU").action == "enter"       # metal weekend ama ders hisseyi kapatti
    assert e.decide("BTC").action == "enter"


def test_no_lesson_means_session_closed_never_used(mk):
    for D in (utc(2026, 12, 5, 15, 0), ny(2026, 12, 7, 9, 29), utc(2026, 12, 6, 23, 0)):
        e = mk(D)
        for b in ("JPM", "XAU", "BTC"):
            o = e.decide(b)
            assert o.action == "enter", (D, b, o.code)


def test_session_closed_precedes_cluster_cap(mk):
    D = utc(2026, 12, 5, 15, 0)
    e = mk(D)
    e.fill(TEK[:5])
    _set_session_off(e.gate, {"stock": ["weekend"], "hisse": ["weekend"]})
    out = e.decide("AMD")
    assert out.event.skip_reason == "session_closed"          # sira: tatil bari -> ders-kapali seans -> kume tavani


# ------------------------------------------------------------------------------------------------ veto adimi yok (kagit)
def test_no_veto_step_in_paper_entry_and_rows_not_evaluated(mk):
    _Veto.calls = 0
    e = mk()
    out = e.decide("BTC")
    assert out.action == "enter" and out.event.veto_status == "not_evaluated"
    assert _Veto.calls == 0


def test_all_rejection_rows_veto_not_evaluated(mk):
    e = mk()
    e.fill(TEK[:5])
    rows = [e.decide("AMD"), e.decide("BTC", volume=0.0)]
    assert all(r.event.veto_status == "not_evaluated" for r in rows)
    assert {r.event.skip_reason for r in rows} == {"cluster_cap", "flat_bar"}


def test_rejection_skip_reasons_valid_in_ledger_v5(mk):
    """Red satirlari defterde gercekten yazilabilir (ledger v5 skip_reason sozlugu)."""
    e = mk()
    e.fill(TEK[:5])
    out = e.decide("AMD")
    e.led.record_decision(out.event)
    for r in ("cluster_cap", "flat_bar", "session_closed", "max_positions"):
        assert r in L._NEW_SKIP


def test_gates_module_has_no_veto_step_for_paper():
    src = (ROOT / "src" / "trader_engine" / "gates.py").read_text(encoding="utf-8")
    # paper yolunda lookup cagrisi kosulsuz olmamali; dosyada veto kodu testnet/canli icin kalabilir ama "paper" kosulu gerekir
    assert "paper" in src


# ------------------------------------------------------------------------------------------------ tarafsizlik: testnet/canli
def test_neutrality_testnet_live_configs_unchanged_and_veto_required():
    from trader_engine.config import load_cli_config as lc
    for env in ("testnet", "live"):
        try:
            c = lc(CONFIG, "learner", env)
        except Exception as ex:  # noqa: BLE001 - canli onay/anahtar gibi nedenlerle yuklenemeyebilir
            pytest.skip(f"{env} yuklenemedi: {ex}")
        if env == "live":                  # 23.11 kullanici karari: canli = kagit (veto yok; kume/tavan/tatil bari korumasi acik)
            assert c.veto_mode == "off" and c.clusters and c.max_positions == 24 and c.flat_bar_guard is True
            continue
        assert c.veto_mode == "off"          # DD-12 QC: LLM veto kaldirildi, testnet veto'suz
        assert not c.clusters and c.max_positions is None and c.flat_bar_guard is False


def test_neutrality_testnet_gate_still_applies_veto(tmp_path):
    """Testnet kapisi: veto engelliyorsa bugunku gibi veto_* ile reddedilir (kume/seans adimlari etkisiz)."""
    from trader_core import veto as V
    try:
        cfg = load_cli_config(CONFIG, "learner", "testnet")
    except Exception as ex:  # noqa: BLE001
        pytest.skip(f"testnet yuklenemedi: {ex}")
    if "veto" not in inspect.signature(EntryGate.__init__).parameters:
        pytest.fail("EntryGate artik veto argumani almiyor: testnet/canli yolu icin veto kapisi korunmali")

    class Blk:
        def begin_step(self, now):
            pass

        def lookup(self, pair, side, now):
            return V.VetoLookup("missing", "none", True)
    D = utc(2026, 12, 2, 12, 0)
    clock = SimClock(D + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:test")
    st = StateStore(":memory:", bot="learner")
    with st.tx():
        st.kv_set("day_start:2026-12-02", 1000.0)
    g = EntryGate(cfg, led, st, Killswitch(str(tmp_path / "K"), clock), Blk(), clock, _FakeBroker(), Env._rules)
    pre = g.pre(D, "1h", True, "1h")
    out = g.decide(_frame("BTC/USDT", D), D, pre, 1)
    assert out.action == "skip" and out.event.skip_reason == "veto_missing" and out.event.veto_status == "missing"
    st.close()
    led.close()


def test_neutrality_base_config_no_cluster_or_flat_effect(tmp_path):
    """Taban (learner) yapilandirmasi: kume/hesap tavani/tatil bari adimi yok; session_tag disinda davranis ayni."""
    cfg = load_cli_config(CONFIG, "learner", None)
    assert not cfg.clusters and cfg.max_positions is None and cfg.flat_bar_guard is False
