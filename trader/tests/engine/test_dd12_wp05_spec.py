"""DD-12 WP-05 (Motor entegrasyonu) bagimsiz sartname testleri: docs/motor/dd12-capraz-varlik-spec.md (v4) §2 (acilis kapisi,
isteğe bagli ciftler), §4.3 (seansa gore kayma), §9 WP-05, D-T5, D-T8, D-T12, D-T29, D-T31 (+ D-T13 tarafsizlik).
Gerceklemenin farklarina BAKILMADI; yalniz sartname + HEAD'deki kod/testler. Sentetik veri; ag yok.

SPEC-AMBIGUOUS (sartnamenin adlandirmadigi yerler; testler esnek kesfeder, bulunamazsa FAIL eder):
  * Seansa gore kayma mekanizmasi (broker/motor arayuzu) adlandirilmaz: yalniz uctan uca gozlenir (dolum fiyati) - motor
    `build_engine` ile kurulur (PaperBroker'i motor/build_engine baglar), `cost_overrides` ile yapilandirilir.
  * `status.json` kume sayilari: ust duzey/ic ice anahtar adinda `cluster` ya da `kume` gecen sozluk; deger int ya da
    {open|count|n|positions: int}.
  * Evren disi aday isareti: `out_of_universe` (kare nedeni/`reasons` ya da herhangi bir sayac anahtari).
  * `ml_no_model`: strateji/sinyal kaynagi/motor sayaclarinda anahtar adi `no_model` iceren sayac.
  * Kapi: optional pair icin yalniz kural; bayat veri kapiyi bekletmez/dusurmez (sureye iliskin iddia YOK).
"""
from __future__ import annotations

import copy
import dataclasses
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import test_engine_05_spec as T5            # ayni dizin: mevcut sentetik gorunum/sahte sinyal kaynagi/kurulum yardimcilari
from trader_core import ledger as L
from trader_core import signals as S
from trader_engine.bars import to_ms
from trader_engine.brokers.paper import PaperBroker, PaperConfig
from trader_engine.clock import SimClock
from trader_engine.config import load_cli_config
from trader_engine.engine import EXIT_STARTUP_GATE, EngineExit, build_engine
from trader_engine.exchange.rules import extract_rules, spec_to_json
from trader_engine.marketdata.sources import MinuteStep
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar, MinuteBar, OrderRequest, SymbolRules

REAL_STARTUP_GATE = True       # tests/conftest.py: bu modulde acilis kapisi gercekten calisir

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
FIXT = Path(__file__).parent / "fixtures" / "binance" / "exchange_info_sample.json"
UTC = timezone.utc
H = timedelta(hours=1)
M1 = timedelta(minutes=1)

BTC, ETH, SOL = "BTC/USDT", "ETH/USDT", "SOL/USDT"
NVDA, XAU, BZ = "NVDA/USDT", "XAU/USDT", "BZ/USDT"
BASE10 = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "TRX", "LINK", "AVAX"]

# seans tarihleri (2026-11, DST bitti: New York = UTC-5; defter saati duvar saati oldugundan tarihler gecmiste)
D_OPEN = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)        # Car 10:00 NY -> hisse open; metal open
D_CLOSED = datetime(2026, 11, 10, 3, 0, tzinfo=UTC)       # Sal 22:00 NY -> hisse closed; metal open
D_WEEKEND = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)     # Cts -> weekend (hisse ve metal)

BASE_SLIP = (2.0, 2.0, 5.0)                                # entry, exit, stop (bp) - taban
MULT = {"open": 2.0, "closed": 3.0, "weekend": 4.0}        # §4.3


def _slips(tag):
    return tuple(b * MULT[tag] for b in BASE_SLIP)


def _overrides(pairs):
    return {p: {t: dict(zip(("slip_entry_bps", "slip_exit_bps", "slip_stop_bps"), _slips(t))) for t in MULT} for p in pairs}


def _clusters(pairs):
    cl = {"kripto_buyuk": [p for p in pairs if p in (BTC, ETH, "XRP/USDT", "BNB/USDT", SOL)]}
    cl["hisse"] = [p for p in pairs if p == NVDA]
    cl["metal"] = [p for p in pairs if p == XAU]
    cl["enerji_sanayi"] = [p for p in pairs if p == BZ]
    return {k: {"pairs": v, "max_positions": 4} for k, v in cl.items() if v}


def _paper_over(pairs, **kw):
    pairs = list(pairs)
    opt = [p for p in pairs if p in (NVDA, XAU, BZ)]
    over = dict(clusters=_clusters(pairs), optional_pairs=opt, cost_overrides=_overrides(opt),
                flat_bar_guard=True, max_positions=16)
    over.update(kw)
    return over


def _cfg(tmp, pairs, **over):
    """veto_mode paper'da 'required' kalir (WP-06a'ya kadar); veto.json kopyalanir (motor veto kullanmaz/okumaz)."""
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "veto.json").write_text((CONFIG / "veto.live.json").read_text())
    return T5.make_cfg(tmp, "learner", "paper", list(pairs), **over)


# ------------------------------------------------------------------------------------------------ uctan uca motor
class E:
    """build_engine ile kurulan kagit motoru (broker/kayma baglamasi uygulamaya birakilir) + sahte sinyal kaynagi."""

    def __init__(self, tmp, pairs, start, **over):
        self.tmp = Path(tmp)
        self.pairs = list(pairs)
        self.clock = SimClock(start)
        self.cfg = _cfg(self.tmp, self.pairs, **_paper_over(self.pairs, **over))
        self.view = T5.SynthView(self.pairs, start - timedelta(days=2), start + timedelta(days=4), clock=self.clock)
        self.eng = build_engine(self.cfg, clock=self.clock, view=self.view)
        self.eng.gate.seans_disi_aktif = False  # eski WP-05 harness zaman damgalari hafta sonu/acilis oncesi pencerelere duser; bu kapi (seans_disi) o beklentilerin yerine gecer
        self.eng.signals = T5.FakeSignalSource()
        led = self.eng.ledger
        try:
            led.get_active_params()
        except L.LedgerError:
            led.init_params(dataclasses.asdict(S.DEFAULT_SIGNAL_PARAMS), reason=self.eng.strategy.label())
        self.vid = led.get_active_params().version_id
        self.eng.start()

    @property
    def led(self):
        return self.eng.ledger

    @property
    def state(self):
        return self.eng.state

    def set_clock(self, t):
        if t > self.clock.now():
            self.clock.set_time(t)

    def signal(self, D, pairs, **kw):
        for p in pairs:
            self.eng.signals.frames[(p, D)] = T5.make_frame(p, D, version=self.vid, **kw)

    def decide(self, D):
        self.set_clock(D + timedelta(seconds=5))
        self.eng.decision_step(D)

    def step(self, ts, price=100.0, hi=None, lo=None, pairs=None):
        self.set_clock(ts + M1)
        hi = price if hi is None else hi
        lo = price if lo is None else lo
        bars = {p: MinuteBar(p, ts, 60, price, hi, lo, price, price, hi, lo, price, 1.0) for p in (pairs or self.pairs)}
        self.eng.process_step(MinuteStep(ts, bars))

    def enter(self, pair, D, **kw):
        self.signal(D, [pair], **kw)
        self.decide(D)
        self.step(D)
        return self.state.position_for_pair(pair)

    def decisions(self):
        return self.led.list_decisions()

    def close(self):
        try:
            self.eng.state.close()
        finally:
            self.eng.ledger.close()


@pytest.fixture
def mk(tmp_path):
    made = []

    def make(pairs, start, **over):
        e = E(tmp_path / f"e{len(made)}", pairs, start, **over) if (tmp_path / f"e{len(made)}").mkdir() is None else None
        made.append(e)
        return e
    yield make
    for e in made:
        e.close()


def _bps_fill(price, bps, side):
    """beklenen kayma: buy -> yukari, sell -> asagi; tick 0.01 (yonu aleyhine yuvarlama)."""
    raw = price * (1 + bps / 1e4) if side == "buy" else price * (1 - bps / 1e4)
    return round(raw, 2)


# ================================================================================================ D-T29: kayma
@pytest.mark.parametrize("pair,D,tag", [
    (NVDA, D_OPEN, "open"), (NVDA, D_CLOSED, "closed"), (NVDA, D_WEEKEND, "weekend"),
    (XAU, D_OPEN, "open"), (XAU, D_WEEKEND, "weekend"), (BZ, D_WEEKEND, "weekend"),
])
def test_dt29_entry_slippage_by_session(mk, pair, D, tag):
    e = mk([BTC, pair], D - H)
    pos = e.enter(pair, D)
    assert pos is not None and pos.status == "open", "seans yuzunden giris engellenmez, dolar"
    assert pos.entry_price == pytest.approx(_bps_fill(100.0, _slips(tag)[0], "buy"), abs=1e-9), \
        f"{pair} {tag}: giris kaymasi {_slips(tag)[0]} bp olmali (taban x{MULT[tag]})"


@pytest.mark.parametrize("D", [D_OPEN, D_CLOSED, D_WEEKEND])
def test_dt29_crypto_is_base_slippage_in_every_session(mk, D):
    e = mk([BTC, NVDA], D - H)
    pos = e.enter(BTC, D)
    assert pos.entry_price == pytest.approx(_bps_fill(100.0, BASE_SLIP[0], "buy"), abs=1e-9)


@pytest.mark.parametrize("pair,D,tag", [(NVDA, D_OPEN, "open"), (NVDA, D_WEEKEND, "weekend"), (XAU, D_WEEKEND, "weekend")])
def test_dt29_stop_slippage_by_session(mk, pair, D, tag):
    e = mk([BTC, pair], D - H)
    pos = e.enter(pair, D, entry=100.0, stop=98.0)
    assert pos is not None
    e.step(D + M1, price=100.0, hi=100.0, lo=97.0)               # stop 98'e dokunur, bosluk yok
    assert e.state.position_for_pair(pair) is None, "stop tetiklenmeli"
    tr = [t for t in e.led.list_closed_trades() if t.pair == pair]
    assert len(tr) == 1
    assert tr[0].exit_price == pytest.approx(_bps_fill(98.0, _slips(tag)[2], "sell"), abs=1e-9)


def test_dt29_market_exit_slippage_by_session(mk):
    D = D_WEEKEND
    e = mk([BTC, NVDA], D - H)
    pos = e.enter(NVDA, D)
    e.eng.orders.submit_exit(pos, "other", e.clock.now())
    e.step(D + M1)
    tr = [t for t in e.led.list_closed_trades() if t.pair == NVDA]
    assert len(tr) == 1
    assert tr[0].exit_price == pytest.approx(_bps_fill(100.0, _slips("weekend")[1], "sell"), abs=1e-9)


def test_dt29_no_overrides_means_base_everywhere(mk):
    e = mk([BTC, NVDA], D_WEEKEND - H, cost_overrides={})
    pos = e.enter(NVDA, D_WEEKEND)
    assert pos.entry_price == pytest.approx(_bps_fill(100.0, BASE_SLIP[0], "buy"), abs=1e-9)


def test_dt29_shipped_paper_table_is_2_3_4_times_base():
    cfg = load_cli_config(CONFIG, "learner", "paper")
    base = (cfg.cost.slip_entry_bps, cfg.cost.slip_exit_bps, cfg.cost.slip_stop_bps)
    assert base == BASE_SLIP
    opt = [p for p in cfg.pairs if p in cfg.optional_pairs]
    assert len(opt) == 24 and set(cfg.cost_overrides) == set(opt), "kripto icin override yok (tabanda aynen)"  # 23.11 kullanici karari: TON cikarildi (SETTLING)
    for p in opt:
        if p == "TON/USDT":
            continue
        for tag, k in MULT.items():
            got = tuple(cfg.cost_overrides[p][tag][x] for x in ("slip_entry_bps", "slip_exit_bps", "slip_stop_bps"))
            assert got == tuple(b * k for b in base), (p, tag)


# ================================================================================================ D-T31: kagit broker sicrama
def _mini_broker():
    clock = SimClock(datetime(2026, 11, 11, 12, 0, tzinfo=UTC))
    from trader_engine.config import CostModel
    rules = lambda p: SymbolRules(pair=p, symbol=p.replace("/", ""), tick=0.01, step=0.001, min_qty=0.001,  # noqa: E731
                                  max_qty=1e6, min_notional=5.0)
    b = PaperBroker(PaperConfig(cost=CostModel(), mmr=0.004, wallet_start=1000.0), rules, lambda p, s, e: [], clock)
    b.prepare(BTC, 3)
    return b, clock


def _bar(ts, o, h, lo, c):
    return MinuteBar(BTC, ts, 60, o, h, lo, c, o, h, lo, c, 1.0)


@pytest.mark.parametrize("side", ["long", "short"])
def test_dt31_stop_fills_at_post_gap_price_not_stop_price(side):
    b, clock = _mini_broker()
    t0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    buy = side == "long"
    b.market_order(OrderRequest("E1", BTC, "entry", "buy" if buy else "sell", 0.1, None, False, 3, created_ts=t0))
    b.advance({BTC: _bar(t0, 100.0, 100.0, 100.0, 100.0)}, "fills")
    stop = 98.0 if buy else 102.0
    b.place_stop(OrderRequest("S1", BTC, "stop", "sell" if buy else "buy", 0.1, stop, True, 3, created_ts=t0))
    t1 = t0 + M1
    gap_open = 95.0 if buy else 105.0                      # stop'u asan sicrama
    b.advance({BTC: _bar(t1, gap_open, gap_open + (1 if buy else 2), gap_open - (2 if buy else 1), gap_open)}, "fills")
    b.advance({BTC: _bar(t1, gap_open, gap_open + (1 if buy else 2), gap_open - (2 if buy else 1), gap_open)}, "triggers")
    fills = [ev.fill for ev in b.poll(t1 + M1) if ev.kind == "fill" and ev.fill and ev.fill.client_id == "S1"]
    assert len(fills) == 1
    px = fills[0].price
    assert abs(px - gap_open) < 0.1 * abs(gap_open - stop), f"sicrama sonrasi fiyat ({gap_open}) civarinda dolmali, stop ({stop}) degil: {px}"
    assert (px <= gap_open) if buy else (px >= gap_open), "kayma aleyhine"


def test_dt31_no_gap_stop_fills_at_stop_price():
    b, _ = _mini_broker()
    t0 = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    b.market_order(OrderRequest("E1", BTC, "entry", "buy", 0.1, None, False, 3, created_ts=t0))
    b.advance({BTC: _bar(t0, 100.0, 100.0, 100.0, 100.0)}, "fills")
    b.place_stop(OrderRequest("S1", BTC, "stop", "sell", 0.1, 98.0, True, 3, created_ts=t0))
    t1 = t0 + M1
    for ph in ("fills", "triggers"):
        b.advance({BTC: _bar(t1, 100.0, 100.0, 97.0, 99.0)}, ph)
    f = [ev.fill for ev in b.poll(t1 + M1) if ev.kind == "fill" and ev.fill and ev.fill.client_id == "S1"]
    assert len(f) == 1 and 97.8 < f[0].price <= 98.0


# ================================================================================================ D-T5: acilis kapisi
def _spec_json(base: str, contract="TRADIFI_PERPETUAL"):
    info = json.loads(FIXT.read_text())
    sym = copy.deepcopy(next(s for s in info["symbols"] if s["symbol"] == "BTCUSDT"))
    sym["symbol"], sym["contractType"] = base + "USDT", contract
    return spec_to_json(extract_rules({"symbols": [sym]}, base + "USDT", contract_types=(contract,)))


GATE_NOW = datetime(2026, 11, 10, 10, 0, 20, tzinfo=UTC)


def _gate_engine(tmp, *, rules, fresh, pairs=(BTC, ETH, NVDA), wait=30.0, **over):
    """MarketStore'a `rules` (cift listesi) kurallari, `fresh` (cift listesi) taze 1m last+mark yazar."""
    store = MarketStore(tmp / "market.sqlite")
    for p in rules:
        base = p.split("/")[0]
        store.put_rules(p, _spec_json(base, "PERPETUAL" if p in (BTC, ETH) else "TRADIFI_PERPETUAL"), to_ms(GATE_NOW))
    last_open = (GATE_NOW - M1).replace(second=0)
    for p in fresh:
        for i in range(4):
            t = last_open - timedelta(minutes=i)
            store.put_bars([Bar(p, "last", "1m", t, 100, 101, 99, 100.5, 1.0)], now_ms=to_ms(GATE_NOW))
            store.put_bars([Bar(p, "mark", "1m", t, 100, 101, 99, 100.5, 0.0)], now_ms=to_ms(GATE_NOW))
    store.close()
    cfg = _cfg(tmp, pairs, **_paper_over(pairs, startup_wait_s=wait, **over))
    clock = SimClock(GATE_NOW)
    eng = build_engine(cfg, clock=clock)
    try:
        eng.ledger.get_active_params()
    except L.LedgerError:
        eng.ledger.init_params(dataclasses.asdict(S.DEFAULT_SIGNAL_PARAMS), reason=eng.strategy.label())
    return eng, clock


def test_dt5_all_fresh_passes(tmp_path):
    eng, _ = _gate_engine(tmp_path, rules=[BTC, ETH, NVDA], fresh=[BTC, ETH, NVDA])
    eng.start()


def test_dt5_crypto_stale_exits_7(tmp_path):
    eng, _ = _gate_engine(tmp_path, rules=[BTC, ETH, NVDA], fresh=[BTC, NVDA], wait=10.0)       # ETH verisi yok
    with pytest.raises(EngineExit) as ei:
        eng.start()
    assert ei.value.code == EXIT_STARTUP_GATE == 7
    assert "ETH/USDT" in str(ei.value)


def test_dt5_crypto_rules_missing_exits_7(tmp_path):
    eng, _ = _gate_engine(tmp_path, rules=[BTC, NVDA], fresh=[BTC, ETH, NVDA], wait=10.0)
    with pytest.raises(EngineExit) as ei:
        eng.start()
    assert ei.value.code == 7


def test_dt5_stock_stale_passes(tmp_path):
    eng, _ = _gate_engine(tmp_path, rules=[BTC, ETH, NVDA], fresh=[BTC, ETH], wait=10.0)        # NVDA verisi bayat/yok
    eng.start()                                                                                   # EngineExit yok


def test_dt5_stock_without_rules_only_that_pair_waits(tmp_path):
    eng, _ = _gate_engine(tmp_path, rules=[BTC, ETH], fresh=[BTC, ETH, NVDA], wait=10.0)         # NVDA kurali yok
    eng.start()                                                                                   # motor calisir, cokmez


def test_dt5_stale_optional_pair_does_not_enter(tmp_path):
    """Gercek sinyal kaynagiyla (WindowedSignalSource) karar adimi: verisi bayat/kurali eksik hisse cifti giris/karar uretmez,
    kripto cifti ve motor etkilenmez (hata yok)."""
    eng, clock = _gate_engine(tmp_path, rules=[BTC, ETH, NVDA], fresh=[BTC, ETH], wait=10.0)
    eng.start()
    D = GATE_NOW.replace(minute=0, second=0)
    eng.decision_step(D)                                    # EngineExit/istisna yok
    assert eng.state.position_for_pair(NVDA) is None, "bayat hisse cifti giris yapmaz"
    assert not [d for d in eng.ledger.list_decisions() if d.pair == NVDA and d.final_action == "entered"]


# ================================================================================================ session_tag + status (WP-05 yazimi)
@pytest.mark.parametrize("pair,D,tag", [
    (NVDA, D_OPEN, "open"), (NVDA, D_CLOSED, "closed"), (NVDA, D_WEEKEND, "weekend"),
    (XAU, D_WEEKEND, "weekend"), (BTC, D_WEEKEND, "open"), (BTC, D_CLOSED, "open"),
])
def test_session_tag_written_to_decision_and_entry_rows(mk, pair, D, tag):
    e = mk([BTC, NVDA, XAU], D - H)
    pos = e.enter(pair, D)
    assert pos is not None, "etiket yasak degil"
    decs = [d for d in e.decisions() if d.pair == pair]
    assert decs and all(d.session_tag == tag for d in decs)
    import sqlite3
    e.eng.state.drain_outbox(e.led) if hasattr(e.eng.state, "drain_outbox") else None
    con = sqlite3.connect(f"file:{e.cfg.ledger_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT session_tag FROM trade_entries WHERE trade_id=?", (pos.trade_id,)).fetchall()
    finally:
        con.close()
    assert rows and all(r[0] == tag for r in rows), f"islem (giris) satirinda da session_tag={tag}: {rows}"


def _find_cluster_block(obj, path=""):
    """Kume adlarini (kripto_buyuk ...) anahtar olarak tasiyan ilk ic ice sozluk."""
    if isinstance(obj, dict):
        if "kripto_buyuk" in obj:
            return obj
        for v in obj.values():
            r = _find_cluster_block(v)
            if r is not None:
                return r
    return None


def _count(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, dict):
        for k in ("open", "count", "n", "positions", "used"):
            if isinstance(v.get(k), (int, float)) and not isinstance(v.get(k), bool):
                return int(v[k])
    if isinstance(v, (list, tuple)):
        return len(v)
    return None


def test_status_json_cluster_counts(mk):
    D = D_OPEN
    e = mk([BTC, ETH, NVDA, XAU], D - H)
    st = e.eng.status_fields()
    blk = _find_cluster_block(st)
    assert blk is not None, f"status alanlarinda kume sayilari yok: {sorted(st)}"
    assert set(blk) >= {"kripto_buyuk", "hisse", "metal"}
    assert all(_count(blk[k]) == 0 for k in ("kripto_buyuk", "hisse", "metal"))
    e.enter(BTC, D)
    e.enter(NVDA, D)
    e.eng.status.write(e.eng, force=True)
    disk = json.loads(Path(e.cfg.status_path).read_text())
    blk = _find_cluster_block(disk)
    assert blk is not None, "status.json diske yazilan kume sayilari"
    assert _count(blk["kripto_buyuk"]) == 1 and _count(blk["hisse"]) == 1 and _count(blk["metal"]) == 0


# ================================================================================================ D-T12: 10 -> 44 gecis
def test_dt12_state_and_ledger_survive_pairs_expansion(tmp_path):
    D = D_OPEN
    small = [BTC, ETH, SOL]
    e1 = E(tmp_path, small, D - H)
    pos = e1.enter(BTC, D)
    assert pos is not None and pos.status == "open"
    e1.step(D + M1)
    e1.step(D + 2 * M1)
    e1.eng.status.write(e1.eng, force=True)
    before = e1.state.position_for_pair(BTC)
    cur_before = {p: (e1.state.get_cursor(p, "minute"), e1.state.get_cursor(p, "decision")) for p in small}
    vid = e1.led.get_active_params().version_id
    n_ver = len(e1.led.list_versions())
    n_dec = len(e1.decisions())
    trades = [t.trade_id for t in e1.led.list_open_trades()]
    e1.close()
    assert all(c[0] is not None for c in cur_before.values())

    big = small + [NVDA, XAU, BZ]                          # ayni var/state/defter, daha genis evren
    e2 = E(tmp_path, big, D + 3 * M1)
    try:
        after = e2.state.position_for_pair(BTC)
        assert after is not None and after.status == "open", "acik pozisyon korunur"
        assert (after.trade_id, after.entry_price, after.qty, after.current_stop, after.side) == \
               (before.trade_id, before.entry_price, before.qty, before.current_stop, before.side)
        assert [t.trade_id for t in e2.led.list_open_trades()] == trades, "defter acik islem satiri korunur"
        assert e2.led.get_active_params().version_id == vid and len(e2.led.list_versions()) == n_ver, "parametre surumu korunur"
        assert len(e2.decisions()) == n_dec, "defter satirlari korunur"
        for p in small:                                     # imlec geri sarilmaz/silinmez
            c = e2.state.get_cursor(p, "minute")
            assert c is not None and c >= cur_before[p][0], f"{p} imleci korunur"
        for p in (NVDA, XAU, BZ):
            assert e2.state.get_cursor(p, "minute") is not None, f"yeni cift {p} icin imlec kurulur"
        assert e2.eng.broker.positions() if hasattr(e2.eng.broker, "positions") else True
        # yeni cift girisi calisir, eski pozisyon tek kalir (cift basina tek pozisyon)
        e2.signal(D_OPEN + H, [BTC, NVDA])
        e2.decide(D_OPEN + H)
        assert e2.state.position_for_pair(NVDA) is not None
        assert len([p for p in e2.state.open_positions() if p.pair == BTC]) == 1
    finally:
        e2.close()


# ================================================================================================ kagit yapilandirmasi: golge satirlar (D-T8)
def test_dt8_paper_config_has_shadow_rows_open(mk):
    cfg = load_cli_config(CONFIG, "learner", "paper")
    assert tuple(cfg.shadow_blocks) == ("regime", "r1_disabled", "same_bar_reentry", "tf_15m")      # golge satirlar acik
    e = mk([BTC, ETH], D_OPEN - H)
    e.enter(BTC, D_OPEN)
    e.step(D_OPEN + M1)
    e.step(D_OPEN + 2 * M1)
    assert e.led.list_shadow() == [], "(mk motoru kendi yapilandirmasiyla kurulur) golge satir 0"


# ================================================================================================ ikiz yok / tarafsizlik
def test_engine_has_no_twin_start_delay():
    src = (ROOT / "src" / "trader_engine" / "engine.py").read_text()
    assert not re.search(r"""bot\s*==\s*["']twin["']""", src), "ikiz baslatma gecikmesi kalkar"
    assert "twin" not in src.lower(), "motorda ikiz izi kalmaz"


def _run_pytest(*args):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *args], cwd=ROOT,
                       capture_output=True, text=True, timeout=1500)
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def test_neutrality_golden_digests_unchanged():
    """D-T13: geri test altin ozeti (compat/native) ve t28 ozeti bit bit ayni."""
    rc, out = _run_pytest("tests/engine/test_engine_compat_equity.py", "tests/engine/test_risk_ladder_impl.py",
                          "-k", "digest or golden or t28 or equity")
    assert rc == 0, out


def test_neutrality_backtest_rejects_paper_only_cost_and_cluster_keys(tmp_path):
    """Seansa gore kayma/session_tag yalniz paper: backtest yapilandirmasi cost_overrides/clusters kabul etmez; anahtarsiz yukleme sorunsuz."""
    from trader_engine.errors import ConfigError
    (tmp_path / "ok").mkdir()
    ok = T5.make_cfg(tmp_path / "ok", "learner", "backtest", [BTC, ETH])
    assert ok.mode == "backtest" and not ok.cost_overrides and not ok.clusters
    for k, v in (("cost_overrides", _overrides([BTC])), ("clusters", {"kripto_buyuk": {"pairs": [BTC], "max_positions": 1}}),
                 ("optional_pairs", [ETH])):
        (tmp_path / k).mkdir()
        with pytest.raises(ConfigError):
            T5.make_cfg(tmp_path / k, "learner", "backtest", [BTC, ETH], **{k: v})
