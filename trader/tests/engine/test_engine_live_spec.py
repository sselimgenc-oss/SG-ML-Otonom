"""WP-B4 (11-canli-broker.md §6, §10, §13 satir B4 + "B4/B5 icin notlar" + mentor kosullari) motor canli yolu sartname testleri.

Bagimsiz test ajani; yalniz sartnameden, committed koddan (HEAD) ve dondurulmus `fake_exchange.py` / `binance_futures.py` /
`binance_rest.py` yuzeyinden yazildi. Gerceklemenin (engine.py / order_manager.py / cli.py) taslak farklarina BAKILMADI.
Gercek ag/saat yok: `FakeExchange` (HTTP duzeyi, SimClock). Testler gerceklemeden once basarisiz olabilir.

Duzenek: gercek `SignedRestClient` -> `Wire` (HTTP sarmalayici: sira/tx/kayit denetimi, hata/cokme enjeksiyonu) -> `FakeExchange`;
gercek `LiveBroker` (cagri kaydeden `ProbeLive` alt sinifi); gercek `StateStore`/`Ledger` (tmp); gercek `Engine` (mode="testnet").
Cokme = `Crash(BaseException)` (motorun `except Exception` korumalarindan gecer); yeniden baslatma = ayni state/borsa/saat uzerinde
yeni `LiveEnv` (bos bellekli yeni LiveBroker + yeni Engine).

`# SPEC-AMBIGUOUS:` ile isaretli yerler sartnamenin adlandirmadigi noktalardaki tahminlerdir (ozet: dosya sonundaki liste).
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import numpy as np
import pytest

from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from test_engine_05_spec import (BTC, CallLogBroker, Env, FakeSignalSource, FakeStrategy, FakeVeto, LedgerProxy, ROOT,
                                 SynthView, make_cfg, make_frame)
from trader_core import ledger as L
from trader_core import signals
from trader_engine.brokers.binance_futures import LiveBroker
from trader_engine.clock import SimClock
from trader_engine.config import load_engine_config
from trader_engine.engine import Engine, build_engine
from trader_engine.errors import BrokerUncertain, ConfigError
from trader_engine.exchange.binance_rest import SignedRestClient
from trader_engine.killswitch import Killswitch
from trader_engine.order_manager import make_client_id
from trader_engine.position_manager import ExitContext
from trader_engine.state import StateStore, parse_iso_z
from trader_engine.types import BrokerEvent, Fill, OrderResult

UTC = timezone.utc
XRP = "XRP/USDT"
SYM = "XRPUSDT"
H = timedelta(hours=1)
DEC = datetime(2026, 12, 28, 10, 0, tzinfo=UTC)          # sinyal/karar bari kapanisi
BOOT = DEC - timedelta(minutes=10)                        # motorun acildigi an
TAG = "sub-acct"
LEV_DEFAULT = 3


class Crash(BaseException):
    """Surec olumu benzetimi: `except Exception` korumalarindan gecer."""


def cid_of(role: str, side="long", seq=0, D=DEC, pair=XRP, bot="learner") -> str:
    return make_client_id(bot, role, pair, side, D, seq)


def role_of(cid: str | None) -> str | None:
    return cid[3] if cid and len(cid) > 3 else None            # "trL" + rol harfi (e/s/t/x)


# ====================================================================================== HTTP sarmalayici
@dataclasses.dataclass
class Rec:
    method: str
    path: str
    q: dict
    t: datetime
    in_tx: bool | None
    cid_committed: bool | None = None
    pos_statuses: tuple = ()
    resp: object = None

    @property
    def cid(self):
        return self.q.get("newClientOrderId") or self.q.get("clientAlgoId") or self.q.get("origClientOrderId") \
            or self.q.get("origClientAlgoId")

    @property
    def role(self):
        return role_of(self.cid)


ORDER_PATHS = ("/fapi/v1/order", "/fapi/v1/algoOrder")


def is_order_write(r: Rec) -> bool:
    return r.method in ("POST", "DELETE") and r.path in ORDER_PATHS


def entry_post(r: Rec) -> bool:
    return r.method == "POST" and r.path == "/fapi/v1/order" and r.role == "e"


def exit_post(r: Rec) -> bool:
    return r.method == "POST" and r.path == "/fapi/v1/order" and r.role == "x"


def stop_post(r: Rec) -> bool:
    return r.method == "POST" and r.path == "/fapi/v1/algoOrder"


def stop_delete(r: Rec) -> bool:
    return r.method == "DELETE" and r.path == "/fapi/v1/algoOrder"


def raising(exc):
    def f(rec, resp=None):                 # before(rec) ve after(rec, resp) kancalari icin
        raise exc
    return f


class Wire:
    """SignedRestClient `session=`: her istegi kaydeder, tx/kalicilik durumunu o anda olcer, kancalarla hata enjekte eder."""

    def __init__(self, ex: FakeExchange, clock: SimClock):
        self.ex, self.clock = ex, clock
        self.log: list[Rec] = []
        self.hooks: list[list] = []
        self.in_tx = lambda: None
        self.db_path: str | None = None

    def on(self, match, *, before=None, after=None, once=True):
        self.hooks.append([match, before, after, once, 0])

    def _db(self, sql, args=()):
        if not self.db_path or not Path(self.db_path).exists():
            return []
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.Error:
            return []
        finally:
            con.close()

    def request(self, method, url, headers=None, timeout=None):
        u = urlparse(url)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        rec = Rec(method, u.path, q, self.clock.now(), self.in_tx())
        if is_order_write(rec) and rec.cid:
            rec.cid_committed = bool(self._db("SELECT 1 FROM orders WHERE client_id=?", (rec.cid,)))
            rec.pos_statuses = tuple(r[0] for r in self._db("SELECT status FROM positions"))
        self.log.append(rec)
        afters = []
        for h in self.hooks:
            match, before, after, once, n = h
            if (once and n > 0) or not match(rec):
                continue
            if before is not None:
                h[4] += 1
                r = before(rec)
                if r is not None:
                    rec.resp = r
                    return r
            if after is not None:
                h[4] += 1
                afters.append(after)
        resp = self.ex.request(method, url, headers=headers, timeout=timeout)
        rec.resp = resp
        for a in afters:
            a(rec, resp)
        return resp

    def writes(self, pred=None):
        return [r for r in self.log if is_order_write(r) and (pred is None or pred(r))]


# ====================================================================================== canli LiveBroker kaydedici
class ProbeLive(LiveBroker):
    """Cagrilari (ad, zaman, argumanlar, in_tx) kaydeder; `hooks[ad]` siradaki kancayi tuketir: None = gec, callable(call, *a)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.calls: list[tuple] = []
        self.hooks: dict[str, list] = {}
        self.probe_clock = None
        self.probe_tx = lambda: None

    def _w(self, name, fn, *a, **k):
        self.calls.append((name, self.probe_clock.now(), a, self.probe_tx()))
        q = self.hooks.get(name)
        if q:
            act = q.pop(0)
            if act is not None:
                return act(lambda: fn(*a, **k), *a)
        return fn(*a, **k)

    def market_order(self, req):
        return self._w("market_order", super().market_order, req)

    def place_stop(self, req):
        return self._w("place_stop", super().place_stop, req)

    def cancel(self, pair, client_id):
        return self._w("cancel", super().cancel, pair, client_id)

    def query(self, pair, client_id):
        return self._w("query", super().query, pair, client_id)

    def poll(self, now):
        return self._w("poll", super().poll, now)

    def prepare(self, pair, leverage):
        return self._w("prepare", super().prepare, pair, leverage)

    def register_position(self, pair, opened_ts, client_ids=()):
        return self._w("register_position", super().register_position, pair, opened_ts, client_ids)

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


# ====================================================================================== sahte gorunum / yapilandirma
class FeedView(SynthView):
    """`dead=True` iken besleme yok: dakika/mum verisi gelmez (KILL testi: beslemesiz `live_tick`)."""
    dead = False

    def minute_steps(self, pairs, start, end):
        return iter(()) if self.dead else super().minute_steps(pairs, start, end)

    def last_closed_minute(self, pair):
        return None if self.dead else super().last_closed_minute(pair)

    def data_range(self, pair, tf):
        return None if self.dead else super().data_range(pair, tf)


def make_live_cfg(tmp: Path, *, mode="testnet", leverage=None, live_over=None, pairs=(XRP,), **over):
    raw = json.loads((ROOT / "config" / "engine.base.json").read_text())
    live = {"account_tag": TAG, "expected_wallet_max": 1000.0, "conditional_mode": "algo", "recv_window_ms": 5000,
            "poll_open_s": 5.0, "poll_flat_s": 30.0, "stop_deadline_s": 10.0, "entry_resolve_window_s": 60.0,
            "max_attempts": 1}
    live.update(live_over or {})
    raw.update(pairs=list(pairs), wallet_start=100.0, mode=mode, var_dir=str(tmp / ("var-live" if mode == "live" else "var-testnet")),   # DD-8: testnet/live var_dir son bileseni `var` olamaz
               market_db=str(tmp / "market.sqlite"), history_dir=str(tmp / "hist"), kill_file=str(tmp / "KILL"),
               pause_file=str(tmp / "PAUSE"), live=live, target_trade_risk=0.014)
    if leverage is not None:
        raw["leverage"] = leverage
    raw.update(over)
    b = tmp / "base.json"
    b.write_text(json.dumps(raw))
    o = tmp / "learner.json"
    o.write_text(json.dumps({"bot": "learner"}))
    return load_engine_config(b, o)


def sql(path, q, args=()):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute(q, args).fetchall()
    finally:
        con.close()


def trail_ctx(D, high=2.1, atr=0.02, last_close=2.08):
    """XRP olcegi: giris 2.0, ilk stop 1.9 (R=0.1). iz suren stop = 2.1 - 3*0.02 = 2.04 (> 1.9; kapanis altinda degil)."""
    return ExitContext(bar_close_ts=D, highs=np.array([high]), lows=np.array([2.0]), atrs=np.array([atr]),
                       regime_last="trend_up", last_close=last_close, n_closed=1)


class XrpSignals(FakeSignalSource):
    """Varsayilan cikis baglami XRP olcegine (giris 2.0, stop 1.9) uygun: iz suren stop sikilasmaz, cikis yok.
    (05'in benign_ctx'i 100 olcegindedir; yeniden baslatmada tekrar oynatilan bar onu 97.5 iz stopuna cevirirdi.)"""

    def exit_context(self, pair, pos, D):
        c = self.ctx.get((pair, D))
        return c if c is not None else ExitContext(bar_close_ts=D, highs=np.array([2.02]), lows=np.array([1.98]),
                                                   atrs=np.array([0.02]), regime_last="trend_up", last_close=2.0, n_closed=1)


class LiveEnv:
    """Canli motor duzenegi. `ex`/`clock` verilirse ayni borsada ve ayni state dosyasinda "yeniden baslatma"dir."""

    def __init__(self, tmp, *, ex=None, clock=None, leverage=None, live_over=None, dead=False, **cfg_over):
        self.tmp = Path(tmp)
        self.clock = clock or SimClock(BOOT)
        now_ms = lambda: int(self.clock.now().timestamp() * 1000)    # noqa: E731
        self.ex = ex or FakeExchange(now_ms)
        self.cfg = make_live_cfg(self.tmp, leverage=leverage, live_over=live_over, **cfg_over)
        self.wire = Wire(self.ex, self.clock)
        rest = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=self.wire, now_ms=now_ms,
                                sleep=self.clock.sleep, conditional_mode=self.cfg.live.conditional_mode)
        self.broker = ProbeLive(self.cfg.live, "testnet", self.cfg.leverage, list(self.cfg.pairs), rest, self.clock,
                                self.cfg.cost.taker_fee, environ={})
        self.broker.probe_clock = self.clock
        for p in (self.cfg.ledger_path, self.cfg.state_path):
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        self.state = StateStore(self.cfg.state_path, bot="learner")
        self.broker.probe_tx = self.state.in_tx
        self.wire.in_tx = self.state.in_tx
        self.wire.db_path = self.cfg.state_path
        real = L.open_ledger(self.cfg.ledger_path, "learner", create=True, clock=self.clock.now)
        try:
            real.get_active_params()
        except L.LedgerError:
            real.init_params(dataclasses.asdict(signals.DEFAULT_SIGNAL_PARAMS), reason="strategy:fake_strategy@0.1")
        self.real_ledger = real
        self.ledger = LedgerProxy(real)
        self.version_id = real.get_active_params().version_id
        self.strategy = FakeStrategy()
        self.view = FeedView(self.cfg.pairs, DEC - timedelta(days=3), DEC + timedelta(days=4), mode="flat", base=2.0,
                             clock=self.clock)
        self.view.dead = dead
        self.src = XrpSignals()
        self.kill = Killswitch(self.cfg.kill_file, self.clock)
        # SPEC-AMBIGUOUS: canli Engine'in elle kurulumu: Engine(...) kurucusu mevcut imzayla (broker=LiveBroker, orders=None ->
        # motor kendi OrderManager'ini canli ayarlarla kurar: max_attempts=cfg.live.max_attempts, stop_deadline_s). status=None.
        self.engine = Engine(self.cfg, clock=self.clock, view=self.view, broker=self.broker, ledger=self.ledger,
                             state=self.state, signals=self.src, strategy=self.strategy, veto=FakeVeto(), kill=self.kill,
                             status=None)

    # -- yasam
    def boot(self):
        # SPEC-AMBIGUOUS: startup_check'i build/cli yolu cagirir; burada elle (idempotent varsayilir), sonra engine.start()
        # (protect_first + acilis kapisi + tam mutabakat, §6.2).
        self.broker.startup_check()
        self.engine.start()
        return self

    def hard_close(self):
        for f in (self.state.close, self.real_ledger.close):
            try:
                f()
            except Exception:  # noqa: BLE001
                pass

    def close(self):
        self.hard_close()

    # -- surucu
    def signal(self, D=DEC, **kw):
        d = dict(entry=2.0, stop=1.9, atr_tf=0.05, atr_4h=0.1, stop_dist_atr=2.0)
        d.update(kw)
        self.src.frames[(XRP, D)] = make_frame(XRP, D, version=self.version_id, **d)

    def decide(self, D=DEC):
        t = D + timedelta(seconds=5)
        if t > self.clock.now():
            self.clock.set_time(t)
        self.engine.decision_step(D)

    def enter(self, D=DEC, **kw):
        self.signal(D, **kw)
        self.decide(D)
        return self.pos()

    def tick(self, dt=6.0):
        self.clock.advance(dt)
        self.engine.live_tick(self.clock.now())

    def tick_at(self, t: datetime):
        if t > self.clock.now():
            self.clock.set_time(t)
        self.engine.live_tick(self.clock.now())

    # -- gozlem
    def pos(self):
        return self.state.position_for_pair(XRP)

    def stops(self):
        return [a for a in self.ex.algos.values() if a["algoStatus"] == "NEW"]

    def ex_qty(self) -> Decimal:
        p = self.ex.pos.get(SYM)
        return p["amt"] if p else Decimal(0)

    def posted(self, role=None, method="POST", path=None):
        return [(m, p, q) for m, p, q in self.ex.requests
                if m == method and (path is None or p == path) and p in ORDER_PATHS
                and (role is None or role_of(q.get("newClientOrderId") or q.get("clientAlgoId")) == role)]

    def order_status(self, cid):
        r = self.state.get_order(cid)
        return None if r is None else r.status

    def kv(self, k):
        return self.state.kv_get(k)


@pytest.fixture
def env(tmp_path):
    e = LiveEnv(tmp_path).boot()
    yield e
    e.close()


def restart(old: LiveEnv, **kw) -> LiveEnv:
    old.hard_close()
    return LiveEnv(old.tmp, ex=old.ex, clock=old.clock, **kw).boot()


# ============================================================================================ 1. tx cit testi
def test_live_spec_no_outer_tx_and_post_outside_tx_fence(env):
    pos = env.enter()
    assert pos is not None and pos.status == "open"
    writes = env.wire.writes()
    assert writes, "emir yazimi gozlenmedi"
    # dis tx yok: hicbir emir POST/DELETE'i tx icinde degil; kimligi POST'tan once KALICI (commit edilmis) satirda
    assert all(w.in_tx is False for w in writes), [(w.method, w.path, w.role) for w in writes if w.in_tx]
    assert all(w.cid_committed for w in writes), [(w.method, w.path, w.role) for w in writes if not w.cid_committed]
    # giris POST'u: G1 (pozisyon `opening` + emir satiri) POST'tan once commit edilmis
    e = [w for w in writes if entry_post(w)]
    assert len(e) == 1 and "opening" in e[0].pos_statuses
    # stop POST'u: G2 (pozisyon `open`) commit edilmis
    s = [w for w in writes if stop_post(w)]
    assert len(s) == 1 and "open" in s[0].pos_statuses
    # broker duzeyinde de: market_order/place_stop/cancel/query/poll cagrisi tx icinde degil
    assert env.broker.calls and all(c[3] is False for c in env.broker.calls), \
        [(c[0], c[3]) for c in env.broker.calls if c[3]]


def test_live_spec_live_path_never_calls_simulator_methods(env):
    # §6.1: advance/snapshot/restore yalniz is_simulated iken; LiveBroker'da yoktur -> cagrilsa AttributeError olurdu
    assert LiveBroker.is_simulated is False
    for name in ("advance", "snapshot", "restore"):
        assert not hasattr(LiveBroker, name)
    env.enter()
    env.tick(6)
    env.tick(6)
    assert env.engine.counters().get("callback_errors", 0) == 0


def test_live_spec_paper_keeps_outer_tx_and_simulator_calls(tmp_path):
    """Paper degismez: PaperBroker emir cagrisi dis tx icinde; advance cagrilir."""

    class TxProbe(CallLogBroker):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.tx_seen: list[bool] = []
            self.state = None

        def market_order(self, req):
            self.tx_seen.append(self.state.in_tx())
            return super().market_order(req)

    pe = Env(tmp_path, pairs=(BTC,), broker_cls=TxProbe)
    try:
        pe.broker.state = pe.state
        pe.start()
        pe.open_pos(BTC)
        assert pe.broker.tx_seen and all(pe.broker.tx_seen)
        assert pe.broker.counts["advance"] >= 1
        assert pe.engine.is_paper is True
    finally:
        pe.close()


# ============================================================================================ 2. giris -> stop
def test_live_spec_entry_then_stop_in_same_call(env):
    pos = env.enter()                        # TEK decision_step cagrisi: tick/dongu beklenmez
    assert pos.status == "open" and pos.qty == pytest.approx(float(env.ex_qty())) and env.ex_qty() > 0
    assert pos.entry_price == pytest.approx(2.0)
    st = env.stops()
    assert len(st) == 1
    a = st[0]
    assert a["type"] == "STOP_MARKET" and a["side"] == "SELL" and a.get("reduce", True) is True
    assert a["workingType"] == "MARK_PRICE" and a["qty"] == env.ex_qty() and a["triggerPrice"] == Decimal("1.9")
    assert pos.stop_client_id == a["cid"] and env.order_status(pos.stop_client_id) == "accepted"
    w = env.wire.writes()
    assert [x.role for x in w][:2] == ["e", "s"]
    assert (w[1].t - w[0].t).total_seconds() <= 1.0          # ayni cagri zinciri
    # B4 notu: giris dolumunda register_position (yetkili acilis zamani + kimlikler)
    assert env.broker.named("register_position"), "register_position cagrilmadi"


def test_live_spec_stop_trigger_closes_position_via_live_tick(env):
    pos = env.enter()
    env.ex.set_mark(SYM, "1.85")             # stop borsada tetiklendi
    env.tick(6)
    env.tick(6)
    cur = env.state.get_position(pos.trade_id)
    assert cur.status == "closed" and cur.exit_reason == "stop"
    assert env.ex_qty() == 0
    assert env.engine.counters()["trades_closed"] == 1


# ============================================================================================ 3. stop suresi siniri
def _strip_stop(env: LiveEnv, pos):
    for a in env.ex.algos.values():
        a["algoStatus"] = "CANCELED"
    with env.state.tx():
        env.state.update_position(pos.trade_id, stop_client_id=None)
        env.state.update_order(pos.stop_client_id, status="canceled")


def _as_dt(v):
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, UTC)
    return parse_iso_z(v) if str(v).endswith("Z") else datetime.fromisoformat(v)


@pytest.mark.parametrize("gap,closed", [
    (9, False),
    # SPEC-AMBIGUOUS: tam 10 sn: sartname "sure stop_deadline_s'i ASARSA kapatilir" (§6.5) -> 10.0'da henuz kapatilmaz.
    (10, False),
    (11, True)])
def test_live_spec_naked_guard_deadline_boundaries(tmp_path, gap, closed):
    # SPEC-AMBIGUOUS: mutabakat (L5 yeniden stop) araya girmesin diye reconcile_open_s buyuk; stop POST'lari bekcinin
    # penceresinde basarisiz (zaman asimi) tutulur. naked_since baslangici kv `naked:<tid>` degerinden okunur.
    e = LiveEnv(tmp_path, reconcile_open_s=100000.0, reconcile_flat_s=100000.0).boot()
    try:
        pos = e.enter()
        _strip_stop(e, pos)
        e.wire.on(stop_post, before=raising(ConnectionError("zaman asimi")), once=False)
        e.tick(6)                                            # bekci: stopsuz pozisyonu gordu, naked_since yazildi
        v = e.kv(f"naked:{pos.trade_id}")
        assert v is not None, "naked_since (kv naked:<tid>) yazilmadi"
        t_n = _as_dt(v)
        n_exit0 = len(e.posted("x"))
        e.tick_at(t_n + timedelta(seconds=gap))
        assert (len(e.posted("x")) > n_exit0) is closed
        if closed:
            sent = e.posted("x")[-1]
            assert sent[2].get("reduceOnly") in ("true", True)
            assert e.ex_qty() == 0
            e.tick(6)
            assert e.state.get_position(pos.trade_id).status == "closed"
        else:
            assert e.ex_qty() > 0
    finally:
        e.close()


@pytest.mark.parametrize("elapsed,retry", [(4.9, True), (5.1, False)])
def test_live_spec_stop_retry_only_within_deadline_minus_post_budget(tmp_path, elapsed, retry):
    """§6.4 madde 3: ikinci deneme yalniz `now - t_fill <= stop_deadline_s - 5`; aksi hâlde reduceOnly cikis + stop_failed."""
    e = LiveEnv(tmp_path).boot()
    try:
        def first_fails(call, req):
            e.clock.advance(elapsed)             # ilk stop POST'u bu kadar surdu
            return OrderResult("rejected", req.client_id, reason="filter:-1111")

        e.broker.hooks["place_stop"] = [first_fails]
        pos = e.enter()
        stops = e.broker.named("place_stop")
        if retry:
            assert len(stops) == 2 and stops[1][2][0].client_id == cid_of("stop", seq=1)
            assert pos.status == "open" and len(e.stops()) == 1 and e.stops()[0]["cid"] == cid_of("stop", seq=1)
            assert not e.posted("x")
        else:
            assert len(stops) == 1
            assert len(e.posted("x")) == 1 and e.ex_qty() == 0
            assert e.kv("entries_blocked_reason") == "stop_failed"
    finally:
        e.close()


# ============================================================================================ 4. risk ihlali
def test_live_spec_fill_risk_violation_places_stop_first_then_exit(env):
    env.ex.set_mark(SYM, "2.08")             # karar 2.0'da verildi; dolum 2.08 -> stop mesafesi buyudu -> ihlal
    env.signal(DEC)
    env.decide()
    w = env.wire.writes()
    roles = [x.role for x in w]
    assert "s" in roles and "x" in roles, roles
    assert roles.index("s") < roles.index("x"), f"once stop sonra cikis olmali: {roles}"
    env.tick(6)
    env.tick(6)
    p = env.state.get_position(1)
    assert p.status == "closed" and p.exit_reason == "other"
    assert env.ex_qty() == 0
    assert env.engine.counters()["fill_risk_violation"] >= 1


# ============================================================================================ 5. stop reddi / belirsiz
@pytest.mark.parametrize("reason", ["exchange_-1021", "exchange_status:REJECTED", "exchange_status:EXPIRED",
                                    "exchange_status:CANCELED"])
def test_live_spec_stop_reject_takes_new_id_path_without_query(tmp_path, reason):
    e = LiveEnv(tmp_path).boot()
    try:
        e.broker.hooks["place_stop"] = [lambda call, req: OrderResult("rejected", req.client_id, reason=reason)]
        pos = e.enter()
        stops = e.broker.named("place_stop")
        assert len(stops) == 2
        assert stops[0][2][0].client_id == cid_of("stop", seq=0) and stops[1][2][0].client_id == cid_of("stop", seq=1)
        assert e.broker.named("query") == [], "kesin ret sorgu yoluna girmemeli (F2: yeni kimlik)"
        assert pos.status == "open" and [a["cid"] for a in e.stops()] == [cid_of("stop", seq=1)]
        assert not e.posted("x")
    finally:
        e.close()


def test_live_spec_stop_post_uncertain_but_delivered_is_adopted_by_query(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        def deliver_then_lose(call, req):
            call()
            raise BrokerUncertain("yanit kayboldu")

        e.broker.hooks["place_stop"] = [deliver_then_lose]
        pos = e.enter()
        assert [c for c in e.broker.named("query") if c[2][1] == cid_of("stop", seq=0)], "kimlikle sorgu yapilmadi (F3)"
        assert len(e.stops()) == 1 and len(e.posted("s")) == 1
        assert pos.stop_client_id == cid_of("stop", seq=0) and pos.status == "open"
        assert not e.posted("x")
    finally:
        e.close()


def test_live_spec_stop_post_uncertain_not_delivered_new_seq_after_two_empty_queries(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.wire.on(stop_post, before=raising(ConnectionError("gitmedi")))
        pos = e.enter()
        qs = [c for c in e.broker.named("query") if c[2][1] == cid_of("stop", seq=0)]
        assert len(qs) >= 2, "iki sorgu bekleniyordu (F3)"
        assert [a["cid"] for a in e.stops()] == [cid_of("stop", seq=1)]
        assert pos.status == "open" and not e.posted("x")
    finally:
        e.close()


# ============================================================================================ 6. belirsiz giris penceresi
def test_live_spec_uncertain_entry_window_blocks_then_closes_unopened(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.wire.on(entry_post, before=raising(TimeoutError("gitmedi")))
        e.signal(DEC)
        e.decide()
        pos = e.pos()
        ecid = cid_of("entry")
        assert pos.status == "opening" and e.order_status(ecid) == "unknown"
        assert e.kv("entries_blocked_reason") == "order_unknown"
        entry_attempts = [r for r in e.wire.log if entry_post(r)]
        assert len(entry_attempts) == 1, "kor yeniden gonderim yok (max_attempts=1)"
        t0 = e.state.get_order(ecid).created_ts
        for dt in (16, 32, 48):                       # pencere icinde: her turda kimlikle yeniden sorgu, hâlâ belirsiz
            e.tick_at(t0 + timedelta(seconds=dt))
        e.tick_at(t0 + timedelta(seconds=59))
        assert e.pos().status == "opening" and e.order_status(ecid) == "unknown"
        e.tick_at(t0 + timedelta(seconds=80))         # pencere (60 sn) doldu, emir yok, borsada pozisyon yok
        assert e.state.get_position(pos.trade_id).status == "closed"
        assert e.order_status(ecid) == "failed"
        assert e.ex_qty() == 0 and len([r for r in e.wire.log if entry_post(r)]) == 1
    finally:
        e.close()


def test_live_spec_uncertain_entry_delivered_but_response_lost_is_adopted(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        e.wire.on(entry_post, after=lambda rec, resp: (_ for _ in ()).throw(TimeoutError("yanit kayboldu")))
        e.signal(DEC)
        e.decide()
        e.tick(6)
        pos = e.pos()
        assert pos.status == "open" and pos.qty == pytest.approx(float(e.ex_qty()))
        assert len(e.posted("e")) == 1 and len([r for r in e.wire.log if entry_post(r)]) == 1
        assert len(e.stops()) == 1 and not e.posted("x")
    finally:
        e.close()


# ============================================================================================ 7. cokme noktalari
def _db_pos(e_or_cfg):
    return sql(e_or_cfg.cfg.state_path, "SELECT status, entry_price, qty FROM positions")


def _assert_protected(e: LiveEnv, n_stops=1):
    st = e.stops()
    assert len(st) == n_stops, st
    return st


def test_live_spec_crash_before_entry_post_never_resends_blindly(tmp_path):
    """r1/F5: POST oncesi cokme. Kayit (opening + emir satiri) kalicidir; borsa duz; yeniden baslatmada kor gonderim YOK;
    pencere sonunda pozisyon kapatilir."""
    e = LiveEnv(tmp_path).boot()
    e.wire.on(entry_post, before=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    assert [r[0] for r in _db_pos(e)] == ["opening"]
    assert sql(e.cfg.state_path, "SELECT count(*) FROM orders WHERE role='entry'")[0][0] == 1
    n_before = len(e.ex.requests)
    e2 = restart(e)
    try:
        assert e2.ex_qty() == 0
        t0 = e2.clock.now()
        for dt in (16, 32, 48, 64, 80, 96):
            e2.tick_at(t0 + timedelta(seconds=dt))
        assert e2.ex_qty() == 0
        assert not [1 for m, p, q in e2.ex.requests[n_before:] if m == "POST" and role_of(q.get("newClientOrderId")) == "e"]
        assert e2.state.get_position(1).status == "closed"
        assert e2.order_status(cid_of("entry")) in ("failed", "rejected", "canceled")
    finally:
        e2.close()


def test_live_spec_crash_between_intent_and_order_row_closes_unopened_on_restart(tmp_path):
    """§6.4 madde 6: `opening` + hic emir satiri yok (G1 ile POST arasi cokme), borsa duz -> acilista `_close_unopened`."""
    e = LiveEnv(tmp_path).boot()
    e.wire.on(entry_post, before=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    e.hard_close()
    con = sqlite3.connect(e.cfg.state_path)
    con.execute("DELETE FROM orders")
    con.commit()
    con.close()
    e2 = LiveEnv(e.tmp, ex=e.ex, clock=e.clock).boot()
    try:
        e2.tick(6)
        assert e2.state.get_position(1).status == "closed" and e2.ex_qty() == 0
        assert not e2.posted("e")
    finally:
        e2.close()


def test_live_spec_crash_after_entry_post_restart_installs_stop_at_initial_stop(tmp_path):
    """r2/F4: giris POST'u borsada doldu, surec yanit islenmeden oldu. Yeniden baslatma: emir sorgusu -> dolum benimsenir -> stop."""
    e = LiveEnv(tmp_path).boot()
    e.wire.on(entry_post, after=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    assert e.ex_qty() > 0 and not e.stops()
    assert [r[0] for r in _db_pos(e)] == ["opening"]
    n_entry = len(e.posted("e"))
    e2 = restart(e)                       # SPEC-AMBIGUOUS: protect_first start() icinde, acilis kapisindan once kosar
    try:
        e2.tick(6)
        pos = e2.state.get_position(1)
        assert pos.status == "open" and pos.qty == pytest.approx(float(e2.ex_qty())) and pos.entry_price == pytest.approx(2.0)
        st = _assert_protected(e2)
        assert st[0]["triggerPrice"] == Decimal("1.9") and st[0]["qty"] == e2.ex_qty()
        assert pos.stop_client_id == st[0]["cid"] and e2.order_status(pos.stop_client_id) == "accepted"
        assert len(e2.posted("e")) == n_entry == 1, "giris yeniden gonderilmemeli"
        assert not e2.posted("x")
    finally:
        e2.close()


def test_live_spec_crash_after_fill_before_stop_restart_protects(tmp_path):
    """r4/r5: dolum islendi (G2 commit), stop POST'una gitmeden cokme."""
    e = LiveEnv(tmp_path).boot()
    e.wire.on(stop_post, before=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    st_rows = _db_pos(e)
    assert st_rows[0][0] == "open" and st_rows[0][1] == pytest.approx(2.0)      # G2 kalici
    assert e.ex_qty() > 0 and not e.stops()
    e2 = restart(e)
    try:
        e2.tick(6)
        pos = e2.state.get_position(1)
        st = _assert_protected(e2)
        assert pos.status == "open" and st[0]["triggerPrice"] == Decimal("1.9") and st[0]["qty"] == e2.ex_qty()
        assert pos.stop_client_id == st[0]["cid"]
        assert not e2.posted("x")
    finally:
        e2.close()


def test_live_spec_crash_after_stop_post_before_state_adopts_not_duplicates(tmp_path):
    e = LiveEnv(tmp_path).boot()
    e.wire.on(stop_post, after=raising(Crash()))
    e.signal(DEC)
    with pytest.raises(Crash):
        e.decide()
    assert len(e.stops()) == 1
    e2 = restart(e)
    try:
        e2.tick(6)
        e2.tick(16)
        st = _assert_protected(e2, 1)               # ikinci stop kurulmamali (ya da L7 tek'e indirmeli)
        pos = e2.state.get_position(1)
        assert pos.status == "open" and pos.stop_client_id == st[0]["cid"]
        assert e2.order_status(pos.stop_client_id) == "accepted"
    finally:
        e2.close()


def _trailing_setup(tmp_path):
    e = LiveEnv(tmp_path).boot()
    pos = e.enter()
    assert pos.status == "open" and [a["triggerPrice"] for a in e.stops()] == [Decimal("1.9")]
    D2 = DEC + H
    e.src.ctx[(XRP, D2)] = trail_ctx(D2)
    e.ex.set_mark(SYM, "2.1")             # yeni uzun stop 2.04 < mark: would_trigger olmasin (1.9 stopu da tetiklenmez)
    return e, pos, D2


def test_live_spec_trailing_replace_places_new_before_cancelling_old(tmp_path):
    e, pos, D2 = _trailing_setup(tmp_path)
    try:
        e.decide(D2)
        w = [x for x in e.wire.writes() if x.role == "s"]
        kinds = [(x.method, x.cid) for x in w]
        new_cid = cid_of("stop", seq=1)
        assert kinds == [("POST", cid_of("stop", seq=0)), ("POST", new_cid), ("DELETE", cid_of("stop", seq=0))], kinds
        st = e.stops()
        assert len(st) == 1 and st[0]["cid"] == new_cid and st[0]["triggerPrice"] == Decimal("2.04")
        cur = e.state.get_position(pos.trade_id)
        assert cur.stop_client_id == new_cid and cur.current_stop == pytest.approx(2.04)
    finally:
        e.close()


def test_live_spec_crash_mid_trailing_before_new_stop_keeps_old_stop(tmp_path):
    e, pos, D2 = _trailing_setup(tmp_path)
    e.wire.on(stop_post, before=raising(Crash()))
    with pytest.raises(Crash):
        e.decide(D2)
    assert [a["triggerPrice"] for a in e.stops()] == [Decimal("1.9")]            # asla cplak degil
    e2 = restart(e)
    try:
        e2.tick(6)
        st = _assert_protected(e2)
        assert st[0]["triggerPrice"] == Decimal("1.9") and e2.state.get_position(pos.trade_id).status == "open"
    finally:
        e2.close()


def test_live_spec_crash_mid_trailing_new_accepted_old_not_cancelled_l7(tmp_path):
    """r7/r9/F12: yeni stop kabul edildi, eski iptal edilmeden cokme -> iki stop; mutabakat L7: en siki kalir, state ona esitlenir."""
    e, pos, D2 = _trailing_setup(tmp_path)
    e.wire.on(stop_delete, before=raising(Crash()))
    with pytest.raises(Crash):
        e.decide(D2)
    assert sorted(a["triggerPrice"] for a in e.stops()) == [Decimal("1.9"), Decimal("2.04")]
    e2 = restart(e)
    try:
        e2.tick(6)
        e2.tick(16)
        st = _assert_protected(e2)
        assert st[0]["triggerPrice"] == Decimal("2.04")
        cur = e2.state.get_position(pos.trade_id)
        assert cur.status == "open" and cur.stop_client_id == st[0]["cid"] and cur.current_stop == pytest.approx(2.04)
    finally:
        e2.close()


def test_live_spec_crash_mid_trailing_new_posted_state_not_updated_l7(tmp_path):
    """Yeni stop borsada, state henuz guncellenmedi (yanit isleme oncesi cokme): yine iki stop -> L7 en sikiyi tutar."""
    e, pos, D2 = _trailing_setup(tmp_path)
    def crash_on_second_stop_post(rec):
        return stop_post(rec) and rec.cid != cid_of("stop", seq=0)

    e.wire.on(crash_on_second_stop_post, after=raising(Crash()))
    with pytest.raises(Crash):
        e.decide(D2)
    assert len(e.stops()) == 2
    e2 = restart(e)
    try:
        e2.tick(6)
        e2.tick(16)
        st = _assert_protected(e2)
        assert st[0]["triggerPrice"] == Decimal("2.04")
        cur = e2.state.get_position(pos.trade_id)
        assert cur.stop_client_id == st[0]["cid"]
    finally:
        e2.close()


# ============================================================================================ 8. KILL beslemesiz
def test_live_spec_kill_runs_in_live_tick_without_feed(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        e.view.dead = True                            # besleme durdu (F20): dakika/mum verisi yok
        Path(e.cfg.kill_file).parent.mkdir(parents=True, exist_ok=True)
        Path(e.cfg.kill_file).write_text("{}")
        e.tick(6)
        e.tick(6)
        xs = e.posted("x")
        assert len(xs) == 1 and xs[0][2].get("reduceOnly") in ("true", True)
        assert e.ex_qty() == 0
        cur = e.state.get_position(pos.trade_id)
        assert cur.status == "closed" and cur.exit_reason == "force_exit"
        # stop iptal EDILMEZ, cikis dolunca iptal edilir (r3)
        reqs = [(m, p) for m, p, q in e.ex.requests if p in ORDER_PATHS and m in ("POST", "DELETE")]
        kinds = [(m, role_of(q.get("newClientOrderId") or q.get("clientAlgoId")))
                 for m, p, q in e.ex.requests if p in ORDER_PATHS and m in ("POST", "DELETE")]
        i_exit = kinds.index(("POST", "x"))
        dels = [i for i, k in enumerate(kinds) if k == ("DELETE", "s")]
        assert not dels or min(dels) > i_exit, kinds
        assert not e.stops()
        assert reqs
    finally:
        e.close()


# ============================================================================================ 9. yalniz son karar bari
def test_live_spec_only_last_decision_bar_is_acted_on(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        D1, D2, D3 = DEC + H, DEC + 2 * H, DEC + 3 * H
        # SPEC-AMBIGUOUS: imlecler elle: son karar = DEC, son dakika = DEC - 1 dk (kacan barlar: D1, D2; en son kapanmis: D3)
        with e.state.tx():
            e.state.set_cursor(XRP, "minute", DEC - timedelta(minutes=1))
            e.state.set_cursor(XRP, "decision", DEC)
        for D in (D1, D2, D3):
            e.signal(D)
        e.clock.set_time(D3 + timedelta(seconds=5))
        e.engine.live_tick(e.clock.now())
        called = [c for c in e.src.calls if c[0] == XRP]
        assert (XRP, D1) not in called and (XRP, D2) not in called, called
        assert (XRP, D3) in called
        pos = e.pos()
        assert pos is not None and pos.signal_bar_close_ts == D3
        assert len(e.posted("e")) == 1
        assert e.engine.counters()["skipped_decisions"] >= 2
        assert e.state.get_cursor(XRP, "decision") == D3
    finally:
        e.close()


# ============================================================================================ 10. cift dolum / beklenmeyen dolum
def test_live_spec_duplicate_exit_fill_is_ignored(env):
    pos = env.enter()
    env.ex.set_mark(SYM, "1.85")
    env.clock.advance(6)
    evs = [x for x in env.broker.poll(env.clock.now()) if x.kind in ("fill", "liquidation")]
    assert evs and evs[0].fill.role != "entry"      # LiveBroker stop dolumu icin role="stop" uretir
    now = env.clock.now()
    env.engine._handle_events(evs, None, now)                 # §6.3: step=None kabul edilir
    assert env.state.get_position(pos.trade_id).status == "closed"
    c0 = env.engine.counters()
    env.engine._handle_events(evs, None, now)                 # ayni olay ikinci kez
    c1 = env.engine.counters()
    assert c1["trades_closed"] == c0["trades_closed"] == 1
    assert c1.get("duplicate_fill_ignored", 0) == c0.get("duplicate_fill_ignored", 0) + 1
    assert c1.get("unexpected_fills", 0) == c0.get("unexpected_fills", 0)
    assert env.state.get_position(pos.trade_id).status == "closed"


def test_live_spec_fill_for_pair_without_state_position_is_tolerated(env):
    now = env.clock.now()
    f = Fill(client_id=cid_of("entry"), pair=XRP, role="entry", order_side="buy", qty=1.0, price=2.0, fee=0.0, ts=now,
             reason="market")
    ev = BrokerEvent(kind="fill", ts=now, pair=XRP, client_id=f.client_id, fill=f)
    env.engine._handle_events([ev], None, now)                # yeniden baslatma/gec dolum: cokme yok
    assert env.pos() is None


# ============================================================================================ 11. ban -> last_ban cizelgesi
def test_live_spec_exchange_ban_reject_schedules_next_attempt_from_retry_after(tmp_path):
    e = LiveEnv(tmp_path).boot()
    try:
        pos = e.enter()
        Path(e.cfg.kill_file).write_text("{}")
        e.wire.on(exit_post, before=lambda rec: FakeResp(429, {"code": -1003, "msg": "Too many requests"},
                                                         {"Retry-After": "30"}))
        e.tick(6)                                                  # cikis POST'u 429 alir (pencere acildi)
        T = e.clock.now()
        e.tick(6)                                                  # simdi gonderim oncesi ban -> `exchange_ban` reddi
        assert e.broker.last_ban is not None
        n_calls = len([c for c in e.broker.named("market_order") if c[2][0].role == "exit"])
        for dt in (12, 18, 24):                                    # pencere icinde motor broker'a TEKRAR GITMEMELI
            e.tick_at(T + timedelta(seconds=dt))
        assert len([c for c in e.broker.named("market_order") if c[2][0].role == "exit"]) == n_calls, \
            "ban penceresinde cikis tekrar denendi (retry_after_s'ten cizelgelenmeli)"
        assert e.ex_qty() > 0 and len(e.posted("x")) == 0
        e.tick_at(T + timedelta(seconds=40))                       # pencere bitti: yeni kimlikle yeniden dene
        e.tick(6)
        assert e.ex_qty() == 0
        assert e.state.get_position(pos.trade_id).status == "closed"
    finally:
        e.close()


# ============================================================================================ 12. kaldirac 4 uctan uca
def test_live_spec_leverage_four_end_to_end(tmp_path):
    e = LiveEnv(tmp_path, leverage=4).boot()
    try:
        assert e.cfg.leverage == 4
        # borsa tarafi: acilis hazirligi izole + kaldirac 4
        assert e.ex.margin_type[SYM] == "isolated" and e.ex.lev[SYM] == 4
        pos = e.enter()
        assert pos is not None and pos.status == "open", "prepare(pair, 4) reddedilmemeli"
        assert pos.leverage == 4
        assert pos.margin == pytest.approx(pos.qty * pos.entry_price / 4, rel=1e-6)    # margin = notional / 4
        # niyet: prepare 4 ile cagrildi
        assert all(c[2][1] == 4 for c in e.broker.named("prepare") if c[2][0] == XRP)
        lev_posts = [q for m, p, q in e.ex.requests if p == "/fapi/v1/leverage" and m == "POST"]
        assert lev_posts and all(q["leverage"] == "4" for q in lev_posts)
        assert e.ex.lev[SYM] == 4
    finally:
        e.close()


# ============================================================================================ 13. LIVE_CONFIRM
def _live_cfg_env(tmp_path, confirm):
    cfg = make_live_cfg(Path(tmp_path), mode="live")
    env = {"BINANCE_API_KEY": "k" * 40, "BINANCE_API_SECRET": "s" * 40}
    if confirm is not None:
        env["LIVE_CONFIRM"] = confirm
    return cfg, env


def _injected(tmp_path, cfg):
    clock = SimClock(BOOT)
    ex = FakeExchange(lambda: int(clock.now().timestamp() * 1000))
    rest = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=ex.session,
                            now_ms=lambda: int(clock.now().timestamp() * 1000), sleep=clock.sleep)
    b = LiveBroker(cfg.live, "testnet", cfg.leverage, list(cfg.pairs), rest, clock, 0.0005, environ={})
    view = FeedView(cfg.pairs, DEC - timedelta(days=3), DEC + timedelta(days=4), mode="flat", base=2.0, clock=clock)
    return clock, b, view


@pytest.mark.parametrize("confirm", [None, "yanlis-hesap", ""])
def test_live_spec_build_engine_live_requires_live_confirm_real_path(tmp_path, confirm):
    cfg, env = _live_cfg_env(tmp_path, confirm)
    # SPEC-AMBIGUOUS: gercek canli yol = broker verilmeden build_engine (anahtarlar env'de); LIVE_CONFIRM agdan ONCE denetlenir
    # (ag yok; denetim sonradan olsaydi baska bir hata/ag denemesi olurdu).
    clock = SimClock(BOOT)
    view = FeedView(cfg.pairs, DEC - timedelta(days=3), DEC + timedelta(days=4), mode="flat", base=2.0, clock=clock)
    with pytest.raises(ConfigError, match="live_confirm"):
        build_engine(cfg, clock=clock, view=view, env=env)


def test_live_spec_build_engine_live_confirm_also_checked_with_injected_broker(tmp_path):
    cfg, env = _live_cfg_env(tmp_path, "yanlis")
    clock, b, view = _injected(tmp_path, cfg)
    with pytest.raises(ConfigError, match="live_confirm"):
        build_engine(cfg, clock=clock, view=view, broker=b, env=env)


def test_live_spec_build_engine_live_with_matching_confirm_builds(tmp_path):
    cfg, env = _live_cfg_env(tmp_path, TAG)
    clock, b, view = _injected(tmp_path, cfg)
    eng = build_engine(cfg, clock=clock, view=view, broker=b, env=env)
    try:
        assert eng.broker is b and eng.cfg.mode == "live"
    finally:
        eng.state.close()
        eng.ledger.close()


def test_live_spec_build_engine_testnet_and_paper_need_no_live_confirm(tmp_path):
    cfg = make_live_cfg(Path(tmp_path), mode="testnet")
    clock, b, view = _injected(tmp_path, cfg)
    eng = build_engine(cfg, clock=clock, view=view, broker=b, env={})
    try:
        assert eng.broker is b
    finally:
        eng.state.close()
        eng.ledger.close()
    (tmp_path / "p").mkdir()
    pcfg = make_cfg(tmp_path / "p", "learner", "paper", (BTC,), 1000.0)
    peng = build_engine(pcfg, clock=SimClock(BOOT), view=SynthView((BTC,), BOOT - timedelta(days=1), BOOT + timedelta(days=1),
                                                                     clock=None), env={})
    try:
        assert peng.is_paper is True
    finally:
        peng.state.close()
        peng.ledger.close()


# SPEC-AMBIGUOUS ozeti (rapor):
#  1. Canli Engine kurulumu: Engine(cfg, ..., broker=ProbeLive, orders=None, status=None); motor OrderManager'i canli ayarlarla
#     (max_attempts, stop_deadline_s) kendisi kurar varsayildi. startup_check testte elle cagrildi; protect_first start() icinde.
#  2. Canli dongu girisi: `engine.live_tick(now)`; karar bari elle `engine.decision_step(D)`; olay isleme `engine._handle_events`.
#  3. Bekci: kv `naked:<tid>` degeri (ISO-Z ya da epoch) naked_since; tam 10.0 sn'de kapatilmaz ("asarsa"); mutabakat araya
#     girmesin diye reconcile_open_s buyutuldu.
#  4. Ban: ilk 429 (Retry-After 30) emir icin `rate_limited` ret + pencere; ikinci deneme gonderim oncesi `exchange_ban`;
#     B4 sonraki cikis denemesini pencere bitene kadar broker'a gondermez (sayac `market_order` cagrilari).
#  5. Sayac adlari: skipped_decisions, duplicate_fill_ignored, fill_risk_violation, unexpected_fills, trades_closed.
#  6. Imlec ile "yalniz son karar bari": imlecler elle (dakika = DEC-1dk, karar = DEC); counters()["skipped_decisions"] >= 2.
#  7. Belirsiz giris penceresinde son durum: emir `failed`, pozisyon `closed`; ara durum `unknown`/`opening`/order_unknown.
#  8. KILL kaldirilmis pozisyon cikis nedeni "force_exit", risk ihlali "other", stop tetik "stop".
#  9. LIVE_CONFIRM: build_engine (broker verilsin ya da verilmesin) mode=live iken ag/ayar kurulumundan once ConfigError("live_confirm").
