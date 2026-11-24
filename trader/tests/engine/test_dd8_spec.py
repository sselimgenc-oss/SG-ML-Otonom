"""DD-8 (canli baslangic guvenligi) bagimsiz sartname testleri: docs/dd8-canli-baslangic-spec.md (v1, 18 Kasim 2026).

Bagimsiz test ajani; yalniz sartnameden (cikis kodlari, hata kodlari, sayac/kv adlari, islev imzalari), COMMITTED koddan (HEAD) ve
mevcut test duzeneklerinden (fake_exchange, test_engine_live_spec.LiveEnv, test_live_broker_impl_smoke.build) yazildi.
Gerceklemenin (src/ calisma agaci) taslak farklarina BAKILMADI. Gercek ag/saat yok: sahte borsa (FakeExchange, HTTP duzeyi) + SimClock.
"Istek sayisi" daima sahte borsanin `requests` kayit listesinden olculur.

Adlandirma: test_<bolum>_<no>_...  (s0 = sartname §0 acilis sirasi/cikis kodlari; o4/o8/o6/d7/d2/e1/e2/e4 = sartname maddeleri).
Yeni modulleri (`trader_engine.stamp`, `Ledger.get_meta/set_meta_once`, `config.load_cli_config/absolutize_paths`, ...) testler FONKSIYON
ICINDE iceri alir: gerceklenmemisse yalniz o test basarisiz olur, toplama hatasi olmaz.

`# SPEC-AMBIGUOUS:` ile isaretli yerler sartnamenin adlandirmadigi noktalardaki tahminlerdir.
"""
from __future__ import annotations

import argparse
import ast
import dataclasses
import fcntl
import importlib
import importlib.util
import json
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import pytest

import test_engine_live_spec as T
from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from test_live_broker_impl_smoke import build as lb_build
from trader_core import ledger as L
from trader_core import risk_ladder as RL
from trader_engine import cli
from trader_engine import engine as E
from trader_engine.brokers.binance_futures import LiveBroker
from trader_engine.clock import SimClock
from trader_engine.config import load_engine_config
from trader_engine.errors import ConfigError, EngineExit, StateError
from trader_engine.exchange.binance_rest import ExchangeAuth, ExchangeReject, ExchangeUncertain, SignedRestClient
from trader_engine.marketdata.rest_public import ExchangeBan
from trader_engine.order_manager import make_client_id
from trader_engine.pause import EntryPause
from trader_engine.state import StateStore
from trader_engine.types import OrderRequest

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
XRP, SYM = T.XRP, T.SYM
TAG = T.TAG                                   # "sub-acct"
T0 = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
WALLET_MAX = 1000.0
PERM_FIELDS = (("enableReading", True), ("enableFutures", True), ("enableWithdrawals", False),
               ("enableInternalTransfer", False), ("permitsUniversalTransfer", False), ("ipRestrict", True))
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}


# ====================================================================================== kucuk yardimcilar
def _now_ms(clock):
    return lambda: int(clock.now().timestamp() * 1000)


def want_stamp(mode="testnet", tag=TAG) -> str:
    return f"{mode}:{tag}"


def make_cfg(tmp, mode="testnet", tag=TAG, wallet_max=WALLET_MAX, var=None, **over):
    """mode testnet/live yapilandirmasi; var_dir sartname §2.1'e uygun (`var-<mode>`)."""
    Path(tmp).mkdir(parents=True, exist_ok=True)
    return T.make_live_cfg(Path(tmp), mode=mode, var_dir=str(var or Path(tmp) / f"var-{mode}"),
                           live_over={"account_tag": tag, "expected_wallet_max": wallet_max}, **over)


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def kv_get(path, key):
    """State kv (json kodlu) degeri; dosya/anahtar yoksa None."""
    try:
        con = _ro(path)
        try:
            r = con.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return None if r is None else json.loads(r[0])


def kv_keys(path) -> set[str]:
    try:
        con = _ro(path)
        try:
            return {r[0] for r in con.execute("SELECT k FROM kv")}
        finally:
            con.close()
    except sqlite3.Error:
        return set()


def meta_get(path, key):
    try:
        con = _ro(path)
        try:
            r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    return None if r is None else r[0]


def count_rows(path, table) -> int:
    con = _ro(path)
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def seed_state(path, kv: dict | None = None):
    """Gercek StateStore ile (bakir) state kurar; `kv` ek anahtarlar. Dosya kapatilir (kilit birakilir)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    st = StateStore(str(path), bot="learner")
    try:
        if kv:
            with st.tx():
                for k, v in kv.items():
                    st.kv_set(k, v)
    finally:
        st.close()


def seed_ledger(path, *, stamp: str | None = None, rows: str | None = None):
    """Gercek defter. rows: None (yalniz sema + parametre) | "decision" (bir karar satiri) | "open" (acik islem) | "closed"
    (yalniz kapanmis islem). Damga ham INSERT ile (`meta` yalniz-ekleme: INSERT serbest; get_meta/set_meta_once'a baglanmaz)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if rows in ("open", "closed"):
        from panel_support import day_specs, mkledger
        mkledger(str(path), "learner", day_specs(datetime(2026, 11, 14, tzinfo=UTC), [(True, rows == "closed")]))
    else:
        lg = L.open_ledger(str(path), "learner", create=True, clock=lambda: T0)
        try:
            if rows == "decision":
                from test_ledger_impl_smoke import r1
                lg.init_params(PARAMS, reason="strategy:price_action_v1@1b.0")
                lg.record_decision(r1())
        finally:
            lg.close()
    if stamp is not None:
        con = sqlite3.connect(str(path))
        try:
            con.execute("INSERT INTO meta (key, value) VALUES ('account_stamp', ?)", (stamp,))
            con.commit()
        finally:
            con.close()


def wipe_state(path):
    for ext in ("", "-wal", "-shm"):
        Path(str(path) + ext).unlink(missing_ok=True)


def file_bytes(*paths):
    return {str(p): (Path(p).read_bytes() if Path(p).exists() else None) for p in paths}


def is_entry_post(m, p, q):
    return m == "POST" and p == "/fapi/v1/order" and q.get("reduceOnly") != "true"


def requests_of(ex, method=None, part=None):
    return [(m, p, q) for m, p, q in ex.requests if (method is None or m == method) and (part is None or part in p)]


ACCOUNT_SETUP_PATHS = ("/fapi/v1/marginType", "/fapi/v1/leverage", "/fapi/v1/positionSide/dual", "/fapi/v1/multiAssetsMargin")


def setup_posts(ex):
    return [(m, p) for m, p, _ in ex.requests if m == "POST" and p in ACCOUNT_SETUP_PATHS]


# ====================================================================================== build_engine yolu (gercek REST istemcisi, sahte borsa)
class _Sess:
    """FakeExchange oturumu sarmalayici: olay siralamasi icin ilk HTTP istegini kaydeder."""

    def __init__(self, ex, events):
        self.ex, self.events = ex, events

    def request(self, method, url, headers=None, timeout=None):
        self.events.append(("http", urlparse(url).path))
        return self.ex.request(method, url, headers=headers, timeout=timeout)


def patch_rest(mp, ex, events=None):
    """`_build_live_broker`in kurdugu SignedRestClient'a sahte oturum enjekte eder (ag yok)."""
    import trader_engine.exchange.binance_rest as R
    orig = getattr(R.SignedRestClient, "_dd8_orig", R.SignedRestClient)      # ic ice yamalarda en alttaki gercek sinif
    sess = _Sess(ex, events if events is not None else [])

    def factory(*a, **k):
        k["session"] = sess
        return orig(*a, **k)

    factory._dd8_orig = orig
    mp.setattr(R, "SignedRestClient", factory)
    return sess


def patch_order_spies(mp, events):
    """D7-4: state kilidi (flock LOCK_EX|LOCK_NB) ve damga dogrulamasi olay listesine yazilir."""
    real = fcntl.flock

    def spy(fd, op):
        if op & fcntl.LOCK_NB and op & fcntl.LOCK_EX:
            events.append(("flock",))
        return real(fd, op)

    mp.setattr(fcntl, "flock", spy)
    import trader_engine.stamp as S
    orig = S.verify_or_init_stamp

    def wrap(*a, **k):
        events.append(("stamp",))
        return orig(*a, **k)

    mp.setattr(S, "verify_or_init_stamp", wrap)
    mp.setattr(E, "verify_or_init_stamp", wrap, raising=False)


class Boot:
    """`build_engine` + `Engine.start` yolu (testnet/live): gercek SignedRestClient (oturum = FakeExchange), gercek
    StateStore/Ledger, enjekte edilmis piyasa gorunumu. `ex`/`clock` verilirse ayni borsada yeniden baslatma."""

    def __init__(self, tmp, mp, *, mode="testnet", tag=TAG, wallet=None, wallet_max=WALLET_MAX, var=None, ex=None,
                 clock=None, cfg=None, env_extra=None, **cfg_over):
        self.tmp = Path(tmp)
        self.clock = clock or SimClock(T.BOOT)
        self.ex = ex or FakeExchange(_now_ms(self.clock))
        if wallet is not None:
            self.ex.wallet = Decimal(str(wallet))
        self.events: list = []
        self.cfg = cfg or make_cfg(self.tmp, mode, tag, wallet_max, var, **cfg_over)
        self.mode = self.cfg.mode
        self.env = {"BINANCE_API_KEY": KEY, "BINANCE_API_SECRET": SECRET}
        if self.mode == "live":
            self.env["LIVE_CONFIRM"] = self.cfg.live.account_tag
        self.env.update(env_extra or {})
        self.view = T.FeedView(self.cfg.pairs, T.DEC - timedelta(days=3), T.DEC + timedelta(days=4), mode="flat", base=2.0,
                               clock=self.clock)
        patch_rest(mp, self.ex, self.events)
        self.eng = None

    def build(self):
        self.eng = E.build_engine(self.cfg, clock=self.clock, view=self.view, env=self.env)
        return self.eng

    def boot(self):
        self.build()
        self.eng.start()
        return self.eng

    def close(self):
        if self.eng is not None:
            for x in (self.eng.state, self.eng.ledger):
                try:
                    x.close()
                except Exception:  # noqa: BLE001
                    pass
            self.eng = None

    @property
    def state_path(self):
        return self.cfg.state_path

    @property
    def ledger_path(self):
        return self.cfg.ledger_path


@pytest.fixture
def boots(monkeypatch):
    made: list[Boot] = []

    def mk(tmp, **kw):
        b = Boot(tmp, monkeypatch, **kw)
        made.append(b)
        return b

    yield mk
    for b in made:
        b.close()


def boot_expect_exit(b: Boot, code: int, msg: str | None = None):
    with pytest.raises(EngineExit) as ei:
        b.build()
        b.eng.start()
    assert ei.value.code == code, str(ei.value)
    if msg is not None:
        assert msg in str(ei.value), str(ei.value)
    return ei.value


# ====================================================================================== giris akisi duzenegi (O4 / D2)
class DEnv:
    """LiveEnv'in (test_engine_live_spec) kardesi: testnet/live kipi, gercek LiveBroker + EntryPause + zorlamali kademe
    (`E._build_ladder`; build_engine'in testnet/live kablolamasi). `ex`/`clock` verilirse ayni borsada "yeniden baslatma"."""

    def __init__(self, tmp, *, mode="testnet", wallet=None, wallet_max=WALLET_MAX, ex=None, clock=None, pairs=(XRP,)):
        self.tmp, self.mode = Path(tmp), mode
        self.clock = clock or SimClock(T.BOOT)
        self.ex = ex or FakeExchange(_now_ms(self.clock))
        if wallet is not None:
            self.ex.wallet = Decimal(str(wallet))
        self.cfg = make_cfg(self.tmp, mode, wallet_max=wallet_max, pairs=pairs)
        rest = SignedRestClient(env=mode, api_key=KEY, api_secret=SECRET, session=self.ex.session, now_ms=_now_ms(self.clock),
                                sleep=self.clock.sleep, conditional_mode=self.cfg.live.conditional_mode)
        self.broker = LiveBroker(self.cfg.live, mode, self.cfg.leverage, list(pairs), rest, self.clock,
                                 self.cfg.cost.taker_fee, environ={})
        for p in (self.cfg.ledger_path, self.cfg.state_path):
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        self.state = StateStore(self.cfg.state_path, bot="learner")
        real = L.open_ledger(self.cfg.ledger_path, "learner", create=True, clock=self.clock.now)
        try:
            real.get_active_params()
        except L.LedgerError:
            import dataclasses as dc

            from trader_core import signals
            real.init_params(dc.asdict(signals.DEFAULT_SIGNAL_PARAMS), reason="strategy:fake_strategy@0.1")
        self.real_ledger = real
        self.ledger = T.LedgerProxy(real)
        self.version_id = real.get_active_params().version_id
        self.pause = EntryPause(f"{self.cfg.pause_file}.learner", self.clock, audit_path=self.cfg.path("pause_audit.jsonl"),
                                bot="learner")
        lad_log = RL.LadderLog(self.cfg.path("risk_ladder.jsonl"))
        if lad_log.state() is None:                     # sermaye kaydi (yoksa kademe zorlamasi `capital_missing` ile girisi kapatir)
            lad_log.append("initial", "test", self.clock.now(), amount=float(self.ex.wallet))
        self.ladder = E._build_ladder(self.cfg, self.clock, self.pause, self.broker, self.ledger)
        self.strategy = T.FakeStrategy()
        self.view = T.FeedView(self.cfg.pairs, T.DEC - timedelta(days=3), T.DEC + timedelta(days=4), mode="flat", base=2.0,
                               clock=self.clock)
        self.src = T.XrpSignals()
        from trader_engine.killswitch import Killswitch
        self.kill = Killswitch(self.cfg.kill_file, self.clock)
        self.engine = E.Engine(self.cfg, clock=self.clock, view=self.view, broker=self.broker, ledger=self.ledger,
                               state=self.state, signals=self.src, strategy=self.strategy, veto=T.FakeVeto(), kill=self.kill,
                               status=None, pause=self.pause, ladder=self.ladder)

    def boot(self):
        self.broker.startup_check()
        self.engine.start()
        return self

    def close(self):
        for f in (self.state.close, self.real_ledger.close):
            try:
                f()
            except Exception:  # noqa: BLE001
                pass

    # -- surucu (LiveEnv ile ayni)
    def signal(self, D=T.DEC, **kw):
        d = dict(entry=2.0, stop=1.9, atr_tf=0.05, atr_4h=0.1, stop_dist_atr=2.0)
        d.update(kw)
        self.src.frames[(XRP, D)] = T.make_frame(XRP, D, version=self.version_id, **d)

    def decide(self, D=T.DEC):
        t = D + timedelta(seconds=5)
        if t > self.clock.now():
            self.clock.set_time(t)
        self.engine.decision_step(D)

    def enter(self, D=T.DEC, **kw):
        self.signal(D, **kw)
        self.decide(D)
        return self.pos()

    def tick(self, dt=6.0):
        self.clock.advance(dt)
        self.engine.live_tick(self.clock.now())

    def pos(self):
        return self.state.position_for_pair(XRP)

    def stops(self):
        return [a for a in self.ex.algos.values() if a["algoStatus"] == "NEW"]

    def entry_posts(self):
        return [r for r in self.ex.requests if is_entry_post(*r)]

    def hold(self, reason="wallet_above_expected"):
        return [h for h in self.pause.holds() if h.reason == reason]


@pytest.fixture
def denv_factory():
    made: list[DEnv] = []

    def mk(tmp, **kw):
        e = DEnv(tmp, **kw)
        made.append(e)
        return e

    yield mk
    for e in made:
        e.close()


def strip_stop_and_restart(denv_factory, tmp, *, mode, high_wallet):
    """Ilk motor pozisyon acar; stop elle silinir; borsa bakiyesi yukseltilir; AYNI borsada yeniden baslatma (stopsuz acik pozisyon)."""
    e1 = denv_factory(tmp, mode=mode, wallet=100).boot()
    pos = e1.enter()
    assert pos is not None and pos.status == "open", pos
    T._strip_stop(e1, pos)
    assert e1.stops() == []
    e1.close()
    e1.ex.wallet = Decimal(str(high_wallet))
    return pos, e1.ex, e1.clock


# ====================================================================================== CLI yapilandirma agaci
def make_tree(tmp, env="testnet", *, tag="testnet-sub", absolute=True, overlay_over=None, base_over=None, cname="config"):
    """<tmp>/root/<cname>/{engine.base,engine.learner,engine.<env>}.json. absolute=True: var/kill/pause/market mutlak (tmp icinde);
    False: gercek `config/` dosyalarindaki goreli degerler (E1; 24.11: veto_config silindi)."""
    root = Path(tmp) / "root"
    cdir = root / cname
    cdir.mkdir(parents=True, exist_ok=True)
    base = json.loads((ROOT / "config" / "engine.base.json").read_text())
    if absolute:
        base["var_dir"] = str(root / "var")
        base["market_db"] = str(root / "var" / "market.sqlite")      # `run` yolunda StoreSource bos da olsa acilabilir bir market.sqlite ister
        base["history_dir"] = str(root / "hist")
        base["kill_file"] = str(root / "shared" / "KILL")
        from trader_engine.marketdata.store import MarketStore
        Path(base["market_db"]).parent.mkdir(parents=True, exist_ok=True)
        MarketStore(base["market_db"]).close()
    base.update(base_over or {})
    (cdir / "engine.base.json").write_text(json.dumps(base))
    shutil.copy(ROOT / "config" / "engine.learner.json", cdir / "engine.learner.json")
    ov = json.loads((ROOT / "config" / "engine.testnet.json").read_text())
    ov["live"]["account_tag"] = tag
    if env == "live":
        ov["mode"] = "live"
        ov["var_dir"] = "var-live"
        ov["kill_file"] = "shared/live/KILL"
        ov["pause_file"] = "shared/live/PAUSE"
        ov["live"]["expected_wallet_max"] = 350.0
    if absolute:
        ov["var_dir"] = str(root / ov["var_dir"])
        ov["kill_file"] = str(root / ov["kill_file"])
        ov["pause_file"] = str(root / ov["pause_file"])
    ov.update(overlay_over or {})
    (cdir / f"engine.{env}.json").write_text(json.dumps(ov))
    return cdir, root


def cli_cfg(cdir, env="testnet"):
    """Ham (mutlaklastirilmamis) yapilandirma; env=None: kagit."""
    d = Path(cdir)
    return load_engine_config(d / "engine.base.json", d / "engine.learner.json",
                              overlay_path=(d / f"engine.{env}.json") if env else None)


# ====================================================================================== §0 acilis sirasi / cikis kodlari
def test_s0_01_steps_1_2_config_and_key_failures_exit_2_with_zero_http(tmp_path, monkeypatch):
    """§0 tablo 1-2: yapilandirma (var_dir kurali), anahtarlar, LIVE_CONFIRM -> cikis 2; borsaya SIFIR istek."""
    ex = FakeExchange(lambda: 1_800_000_000_000)
    patch_rest(monkeypatch, ex)
    monkeypatch.chdir(tmp_path)
    for k in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "LIVE_CONFIRM"):
        monkeypatch.delenv(k, raising=False)
    # (1) var_dir son bileseni `var` (testnet)
    cdir, _ = make_tree(tmp_path / "a", "testnet", overlay_over={"var_dir": str(tmp_path / "a" / "x" / "var")})
    monkeypatch.setenv("BINANCE_API_KEY", KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET)
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]) == 2
    # (2) anahtar yok
    cdir, _ = make_tree(tmp_path / "b", "testnet")
    monkeypatch.delenv("BINANCE_API_KEY")
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]) == 2
    # (3) live: LIVE_CONFIRM yok / yanlis
    cdir, _ = make_tree(tmp_path / "c", "live", tag="live-sub")
    monkeypatch.setenv("BINANCE_API_KEY", KEY)
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "live"]) == 2
    monkeypatch.setenv("LIVE_CONFIRM", "yanlis")
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "live"]) == 2
    assert ex.requests == []


def test_s0_02_steps_3_4_state_lock_exits_3_and_stamp_reject_exits_8_with_zero_http(tmp_path, monkeypatch):
    ex = FakeExchange(lambda: 1_800_000_000_000)
    patch_rest(monkeypatch, ex)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET)
    cdir, root = make_tree(tmp_path, "testnet")
    cfg = cli_cfg(cdir)
    Path(cfg.state_path).parent.mkdir(parents=True, exist_ok=True)
    # adim 3: kilit baskasinda -> cikis 3
    fd = os.open(cfg.state_path + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]) == 3
    finally:
        os.close(fd)
    # adim 4: yabanci damga -> cikis 8
    seed_state(cfg.state_path, {"account_stamp": "live:baska-hesap"})
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]) == 8
    assert ex.requests == []


def test_s0_03_first_http_request_is_startup_check_time_sync(tmp_path, boots):
    """§0 tablo 5: ilk HTTP istegi `startup_check` icinde (`GET /fapi/v1/time`); 1-4. adimlar ag kullanmaz."""
    b = boots(tmp_path)
    b.build()
    assert b.ex.requests, "startup_check HTTP istegi yapmadi"
    assert b.ex.requests[0][:2] == ("GET", "/fapi/v1/time")


def test_s0_04_exit_code_contract_and_new_reject_codes_are_wired_to_cli(tmp_path):
    """Cikis kodlari degismez: 2 yapilandirma, 3 motor/kilit, 5 ulasilamaz, 7 acilis kapisi, 8 kalici ret; yeni 8 kodlari stamp modulunde."""
    assert cli.EXIT_FAZ_B == 2 and cli.EXIT_REPEATED == 3 and cli.EXIT_PERMISSION == 8
    assert E.EXIT_STARTUP_GATE == 7
    src = (SRC / "trader_engine" / "stamp.py").read_text(encoding="utf-8")
    for code in ("state_stamp_mismatch", "ledger_stamp_mismatch", "state_stamp_missing", "ledger_stamp_missing", "state_missing"):
        assert code in src, code


# ====================================================================================== O4: cuzdan tavani asimi
def _crit_logs(caplog, word):
    return [r for r in caplog.records if r.levelno == logging.CRITICAL and word in r.getMessage()]


@pytest.mark.parametrize("mode", ["live"])
def test_o4_01_wallet_above_max_boot_completes_protects_stopless_position_and_pauses(tmp_path, denv_factory, caplog, mode):
    pos, ex, clock = strip_stop_and_restart(denv_factory, tmp_path, mode=mode, high_wallet=WALLET_MAX + 0.01)
    assert not [a for a in ex.algos.values() if a["algoStatus"] == "NEW"]
    n_stop_posts = ex.count("/fapi/v1/algoOrder", "POST")
    e2 = denv_factory(tmp_path, mode=mode, ex=ex, clock=clock)
    seen = []
    orig = e2.broker.place_stop
    e2.broker.place_stop = lambda req: (seen.append(bool(e2.hold())), orig(req))[1]      # protect_first'ten ONCE tutus olmali
    with caplog.at_level(logging.WARNING):
        e2.boot()                                                       # istisnasiz tamamlanir
    assert "wallet_above_expected" in e2.broker.startup_findings
    assert ex.count("/fapi/v1/algoOrder", "POST") > n_stop_posts, "stopsuz pozisyon icin stop emri gonderilmedi"
    assert len(e2.stops()) == 1 and e2.pos().status == "open"
    holds = e2.hold()
    assert len(holds) == 1 and holds[0].by == "engine:wallet_cap"
    assert "wallet=" in holds[0].note and "max=" in holds[0].note
    assert seen and seen[0] is True, "pause.add, protect_first'ten once yapilmali"
    assert _crit_logs(caplog, "wallet_above_expected"), "CRITICAL gunluk (wallet_above_expected) yok"
    from trader_engine import pause as P
    assert "wallet_above_expected" in P.REASONS


def test_o4_02_entry_signal_under_cap_hold_sends_no_entry_order(tmp_path, denv_factory):
    ctl = denv_factory(tmp_path / "ctl", mode="live", wallet=WALLET_MAX - 1).boot()        # kontrol: tavan altinda giris gider
    assert ctl.enter() is not None and len(ctl.entry_posts()) == 1
    e = denv_factory(tmp_path / "hi", mode="live", wallet=WALLET_MAX + 0.01).boot()
    assert e.hold()
    e.enter()
    assert e.entry_posts() == [], "tutus varken giris emri gonderildi"
    assert e.pos() is None
    assert e.pause.code() == "paused"
    assert e.engine._live_gate_code(None, False) == e.pause.code()


@pytest.mark.parametrize("mode", ["live", "testnet"])
@pytest.mark.parametrize("wallet", [WALLET_MAX, WALLET_MAX - 0.01])
def test_o4_03_wallet_equal_or_below_max_no_finding_no_hold(tmp_path, denv_factory, mode, wallet):
    e = denv_factory(tmp_path, mode=mode, wallet=wallet).boot()
    assert "wallet_above_expected" not in e.broker.startup_findings
    assert e.hold() == [] and not e.pause.active()


@pytest.mark.parametrize("env", ["live", "testnet"])
@pytest.mark.parametrize("case", ["missing", "abc", "nan"])
def test_o4_04_unreadable_wallet_exits_8_wallet_unreadable(env, case):
    body = {"canTrade": True, "totalUnrealizedProfit": "0", "totalMarginBalance": "100", "totalInitialMargin": "0",
            "availableBalance": "100"}
    if case != "missing":
        body["totalWalletBalance"] = case

    def pre(ex):
        ex.inject("/fapi/v2/account", FakeResp(200, body))
    with pytest.raises(EngineExit) as ei:
        lb_build(env=env, pre=pre)
    assert ei.value.code == 8 and "wallet_unreadable" in str(ei.value)


def test_o4_05_testnet_wallet_above_max_same_outcome_as_live(tmp_path, denv_factory):
    pos, ex, clock = strip_stop_and_restart(denv_factory, tmp_path, mode="testnet", high_wallet=WALLET_MAX + 0.01)
    e2 = denv_factory(tmp_path, mode="testnet", ex=ex, clock=clock).boot()
    assert "wallet_above_expected" in e2.broker.startup_findings
    assert len(e2.hold()) == 1 and e2.hold()[0].by == "engine:wallet_cap"
    assert len(e2.stops()) == 1


def test_o4_06_running_wallet_cap_check_adds_hold_without_extra_account_request(tmp_path, denv_factory):
    n_acct = {}
    for tag, bump in (("base", False), ("bump", True)):
        e = denv_factory(tmp_path / tag, mode="testnet", wallet=100).boot()
        assert e.hold() == [] and "wallet_above_expected" not in e.broker.startup_findings
        if bump:
            e.ex.wallet = Decimal(str(WALLET_MAX + 0.5))                 # acilistan sonra borsa bakiyesi tavani asar
        e.clock.advance(5)                                               # hesap onbellegi (2 sn) dolsun
        n0 = e.ex.count("/fapi/v2/account")
        for _ in range(3):
            e.tick(6)
        n_acct[tag] = e.ex.count("/fapi/v2/account") - n0
        assert bool(e.hold()) is bump, (tag, e.pause.holds())
        if bump:
            assert e.hold()[0].by == "engine:wallet_cap"
    assert n_acct["bump"] == n_acct["base"], f"denetim ek account istegi yapti: {n_acct}"


def test_o4_07_hold_is_sticky_cleared_only_by_cli_and_readded_while_above(tmp_path, denv_factory, monkeypatch):
    e = denv_factory(tmp_path, mode="testnet", wallet=100).boot()
    e.ex.wallet = Decimal(str(WALLET_MAX + 0.5))
    for _ in range(2):
        e.tick(6)
    assert e.hold()
    e.ex.wallet = Decimal("100")                                         # bakiye tavanin altina iner
    for _ in range(4):
        e.tick(6)
    assert e.hold(), "bakiye dusunce tutus kendiliginden kalkti"
    monkeypatch.setattr(cli, "_load_cfg", lambda a: e.cfg)
    argv = ["pause", "--bot", "learner", "--clear", "--reason", "wallet_above_expected", "--by", "x"]
    assert cli.main(argv) == 0
    assert e.hold() == []
    for _ in range(2):
        e.tick(6)
    assert e.hold() == [], "bakiye altinda iken tutus yeniden eklendi"
    # bakiye hala ustte iken temizlenirse sonraki denetimde yeniden eklenir
    e.ex.wallet = Decimal(str(WALLET_MAX + 0.5))
    e.tick(6)
    assert e.hold()
    assert cli.main(argv) == 0 and e.hold() == []
    for _ in range(2):
        e.tick(6)
    assert e.hold(), "bakiye hala ustteyken temizlenen tutus yeniden eklenmedi"


def test_o4_08_pause_add_failing_still_boots_protects_and_blocks_entries_in_memory(tmp_path, denv_factory):
    # (a) acilis: add her cagrida False; start() tamamlanir, protect_first calisir
    pos, ex, clock = strip_stop_and_restart(denv_factory, tmp_path / "a", mode="testnet", high_wallet=WALLET_MAX + 0.01)
    e2 = denv_factory(tmp_path / "a", mode="testnet", ex=ex, clock=clock)
    calls = []
    e2.pause.add = lambda *a, **k: calls.append(a) or False
    e2.boot()
    assert calls, "pause.add denenmedi"
    assert len(e2.stops()) == 1, "protect_first calismadi"
    assert not e2.hold() and not e2.pause.active()                       # tutus dosyada yok
    # (b) giris sinyali: bellek kilidi -> giris emri gonderilmez; her donguda add yeniden denenir
    e3 = denv_factory(tmp_path / "b", mode="testnet", wallet=WALLET_MAX + 0.01)
    c3 = []
    e3.pause.add = lambda *a, **k: c3.append(a) or False
    e3.boot()
    n0 = len(c3)
    e3.enter()
    assert e3.entry_posts() == [] and e3.pos() is None
    e3.tick(6)
    assert len(c3) > n0, "add her donguda yeniden denenmeli"
    e3.enter(D=T.DEC + timedelta(hours=1))
    assert e3.entry_posts() == []


def test_o4_09_telegram_reason_dictionary_covers_every_pause_reason():
    from trader_core import telegram as TG
    from trader_engine import pause as P
    assert "wallet_above_expected" in P.REASONS
    missing = [r for r in P.REASONS if r not in TG.NEDEN_TR]
    assert not missing, f"Turkce metin eksik: {missing}"
    assert TG.NEDEN_TR["wallet_above_expected"] == "hesap bakiyesi izin verilen tavanı aştı (yalnız sunucuda açılır)"


def test_o4_10_paper_has_no_wallet_cap_behavior(tmp_path):
    import test_engine_05_spec as E5
    e = E5.Env(tmp_path, mode="paper", pairs=(E5.BTC,), wallet=5_000_000.0)
    try:
        e.start()
        e.engine._ladder_step(e.clock.now() + timedelta(minutes=1))
        assert e.engine.pause.holds() == ()
        assert not hasattr(e.broker, "startup_findings") or "wallet_above_expected" not in e.broker.startup_findings
    finally:
        e.close()
    _golden_when_enabled()


def _golden_when_enabled():
    """Altin 3 ciftli geri test bit-ozdesligi (tests/test_wp3_golden.py; ~8-15 dk, yerel gecmis veri ister): WP3_GOLDEN=1 ile."""
    if os.environ.get("WP3_GOLDEN") != "1":
        return
    import subprocess
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", str(ROOT / "tests" / "test_wp3_golden.py")],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=7200)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


# ====================================================================================== O8: damga, var_dir kurali, state_missing
# -- §2.1 yapilandirma kurallari
@pytest.mark.parametrize("mode", ["testnet", "live"])
@pytest.mark.parametrize("var", ["var", "./var", "var/", "/x/y/var"])
def test_o8_01_var_dir_with_last_component_var_rejected_in_live_modes(tmp_path, mode, var):
    with pytest.raises(ConfigError, match="var_dir"):
        T.make_live_cfg(tmp_path, mode=mode, var_dir=var)


@pytest.mark.parametrize("mode,var", [("testnet", "var-testnet"), ("live", "/x/var-live"), ("testnet", "/x/var-live"),
                                      ("paper", "var"), ("paper", "./var")])
def test_o8_01b_var_dir_accepted_cases(tmp_path, mode, var):
    over = {"live": None} if mode == "paper" else {}
    cfg = T.make_live_cfg(tmp_path, mode=mode, var_dir=var, **over)
    assert cfg.mode == mode


@pytest.mark.parametrize("mode", ["testnet", "live"])
@pytest.mark.parametrize("field,val", [("kill_file", "shared/KILL"), ("kill_file", "/opt/trader/shared/KILL"),
                                       ("pause_file", "shared/PAUSE"), ("pause_file", "/opt/trader/shared/PAUSE")])
def test_o8_02_shared_paper_kill_and_pause_paths_rejected_in_live_modes(tmp_path, mode, field, val):
    with pytest.raises(ConfigError):
        T.make_live_cfg(tmp_path, mode=mode, var_dir=str(tmp_path / f"var-{mode}"), **{field: val})


@pytest.mark.parametrize("mode", ["testnet", "live"])
def test_o8_02b_env_specific_kill_pause_paths_accepted(tmp_path, mode):
    cfg = T.make_live_cfg(tmp_path, mode=mode, var_dir=str(tmp_path / f"var-{mode}"),
                          kill_file=f"shared/{mode}/KILL", pause_file=f"shared/{mode}/PAUSE")
    assert cfg.kill_file.endswith(f"shared/{mode}/KILL")


def test_o8_02c_paper_keeps_shared_paths(tmp_path):
    cfg = T.make_live_cfg(tmp_path, mode="paper", live=None, var_dir="var", kill_file="shared/KILL", pause_file="shared/PAUSE")
    assert cfg.kill_file == "shared/KILL" and cfg.pause_file == "shared/PAUSE"


# -- §2.2 damga
def test_o8_03_first_boot_writes_stamps_state_first_then_ledger_second_boot_unchanged(tmp_path, boots, monkeypatch):
    b = boots(tmp_path)
    ledger_stamp_calls = []
    orig = L.Ledger.set_meta_once

    def spy(self, key, value):
        ledger_stamp_calls.append((key, kv_get(b.state_path, "account_stamp")))     # defter damgasi yazilirken state damgasi kalici mi
        return orig(self, key, value)
    monkeypatch.setattr(L.Ledger, "set_meta_once", spy)
    b.boot()
    want = want_stamp("testnet")
    assert kv_get(b.state_path, "account_stamp") == want
    assert meta_get(b.ledger_path, "account_stamp") == want
    assert ("account_stamp", want) in ledger_stamp_calls, "yazim sirasi: once state, sonra defter"
    b.close()
    b2 = boots(tmp_path, ex=b.ex, clock=b.clock)
    b2.boot()                                                           # ikinci acilis surer
    assert kv_get(b2.state_path, "account_stamp") == want and meta_get(b2.ledger_path, "account_stamp") == want


def test_o8_04_paper_dir_copied_to_live_var_dir_exit_8_state_stamp_mismatch_files_untouched(tmp_path, boots):
    import test_engine_05_spec as E5
    (tmp_path / "paper").mkdir()
    pe = E5.Env(tmp_path / "paper", mode="paper", pairs=(E5.BTC,))
    try:
        pe.start()
        pe.open_pos(E5.BTC)                                             # kagit motoru gercekten calisti (karar + islem + broker_snapshot)
    finally:
        pe.close()
    assert count_rows(pe.cfg.ledger_path, "decision_events") >= 1
    b = boots(tmp_path / "live", mode="live", tag="live-sub")
    for src, dst in ((pe.cfg.state_path, b.state_path), (pe.cfg.ledger_path, b.ledger_path)):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    before = file_bytes(b.state_path, b.ledger_path)
    boot_expect_exit(b, 8, "state_stamp_mismatch")
    assert b.ex.requests == []
    assert file_bytes(b.state_path, b.ledger_path) == before, "damga yazildi / dosya degisti"


def test_o8_05_testnet_stamped_dir_opened_as_live_or_other_tag_exit_8_zero_http(tmp_path, boots):
    shared = tmp_path / "var-shared"
    b1 = boots(tmp_path, mode="testnet", var=shared)
    b1.boot()
    assert kv_get(b1.state_path, "account_stamp") == want_stamp("testnet")
    b1.close()
    b2 = boots(tmp_path, mode="live", tag="live-sub", var=shared)
    boot_expect_exit(b2, 8, "state_stamp_mismatch")
    assert b2.ex.requests == []
    b3 = boots(tmp_path, mode="testnet", tag="baska-alt-hesap", var=shared)
    boot_expect_exit(b3, 8, "state_stamp_mismatch")
    assert b3.ex.requests == []
    assert kv_get(b1.state_path, "account_stamp") == want_stamp("testnet")


@pytest.mark.parametrize("how", ["delete", "truncate"])
def test_o8_06_stamped_live_dir_with_open_trade_state_file_lost_exit_8_state_missing(tmp_path, boots, how):
    cfg = make_cfg(tmp_path, "live", "live-sub")
    seed_state(cfg.state_path, {"account_stamp": want_stamp("live", "live-sub")})
    seed_ledger(cfg.ledger_path, stamp=want_stamp("live", "live-sub"), rows="open")
    wipe_state(cfg.state_path)
    if how == "truncate":
        Path(cfg.state_path).write_bytes(b"")
    b = boots(tmp_path, mode="live", tag="live-sub")
    boot_expect_exit(b, 8, "state_missing")
    assert b.ex.requests == []
    assert "account_stamp" not in kv_keys(b.state_path), "yeni olusan state damga icermemeli"


@pytest.mark.parametrize("rows", ["closed", None])
def test_o8_07_state_lost_with_closed_only_or_empty_stamped_ledger_still_state_missing(tmp_path, boots, rows):
    cfg = make_cfg(tmp_path, "live", "live-sub")
    if rows is None:                                                    # ilk acilistan hemen sonra state silindi
        b0 = boots(tmp_path / "first", mode="live", tag="live-sub", var=cfg.var_dir)
        b0.boot()
        b0.close()
        assert meta_get(cfg.ledger_path, "account_stamp") == want_stamp("live", "live-sub")
        assert count_rows(cfg.ledger_path, "decision_events") == 0 and count_rows(cfg.ledger_path, "trade_entries") == 0
    else:
        seed_state(cfg.state_path, {"account_stamp": want_stamp("live", "live-sub")})
        seed_ledger(cfg.ledger_path, stamp=want_stamp("live", "live-sub"), rows=rows)
    wipe_state(cfg.state_path)
    b = boots(tmp_path, mode="live", tag="live-sub")
    boot_expect_exit(b, 8, "state_missing")
    assert b.ex.requests == []


def test_o8_08_unstamped_filled_ledger_with_empty_state_is_state_missing_nonvirgin_state_is_stamp_missing(tmp_path, boots):
    a = boots(tmp_path / "a")
    seed_ledger(a.ledger_path, rows="decision")
    boot_expect_exit(a, 8, "state_missing")
    assert a.ex.requests == []
    # damgasiz, bakir olmayan (initialized_at dolu) ama kagit izi (broker_snapshot) tasimayan state
    b = boots(tmp_path / "b")
    seed_state(b.state_path, {"initialized_at": "2026-12-01T00:00:00Z"})
    assert "broker_snapshot" not in kv_keys(b.state_path) and "account_stamp" not in kv_keys(b.state_path)
    boot_expect_exit(b, 8, "state_stamp_missing")
    assert b.ex.requests == []


def test_o8_09_half_done_first_boot_stamps_ledger_when_empty_but_rejects_filled_ledger(tmp_path, boots):
    want = want_stamp("testnet")
    a = boots(tmp_path / "a")
    seed_state(a.state_path, {"account_stamp": want})
    seed_ledger(a.ledger_path)                                          # damgasiz, bos defter
    a.boot()                                                            # surer
    assert meta_get(a.ledger_path, "account_stamp") == want
    a.close()
    b = boots(tmp_path / "b")
    seed_state(b.state_path, {"account_stamp": want})
    seed_ledger(b.ledger_path, rows="decision")                         # damgasiz, dolu defter
    boot_expect_exit(b, 8, "ledger_stamp_missing")
    assert b.ex.requests == []
    assert meta_get(b.ledger_path, "account_stamp") is None


def test_o8_10_state_stamp_ok_ledger_other_stamp_is_ledger_stamp_mismatch(tmp_path, boots):
    b = boots(tmp_path)
    seed_state(b.state_path, {"account_stamp": want_stamp("testnet")})
    seed_ledger(b.ledger_path, stamp="live:baska-hesap")
    boot_expect_exit(b, 8, "ledger_stamp_mismatch")
    assert b.ex.requests == []


def _paper_engine_pieces(tmp, clock):
    import test_engine_05_spec as E5
    Path(tmp).mkdir(parents=True, exist_ok=True)
    cfg = E5.make_cfg(Path(tmp), "learner", "paper", (E5.BTC,), 1000.0)
    view = E5.SynthView((E5.BTC,), T.BOOT - timedelta(days=1), T.BOOT + timedelta(days=1), clock=None)
    return cfg, view


def test_o8_11_paper_engine_rejects_foreign_stamps_but_never_writes_any(tmp_path):
    clock = SimClock(T.BOOT)
    # (a) damgali state -> state_stamp_mismatch
    cfg, view = _paper_engine_pieces(tmp_path / "a", clock)
    seed_state(cfg.state_path, {"account_stamp": "live:baska"})
    with pytest.raises(EngineExit) as ei:
        E.build_engine(cfg, clock=clock, view=view, env={})
    assert ei.value.code == 8 and "state_stamp_mismatch" in str(ei.value)
    # (b) damgali defter + damgasiz state -> ledger_stamp_mismatch
    cfg, view = _paper_engine_pieces(tmp_path / "b", clock)
    seed_ledger(cfg.ledger_path, stamp="live:baska")
    with pytest.raises(EngineExit) as ei:
        E.build_engine(cfg, clock=clock, view=view, env={})
    assert ei.value.code == 8 and "ledger_stamp_mismatch" in str(ei.value)
    # (c) temiz kagit dizini: acilis oncesi/sonrasi damga yok
    cfg, view = _paper_engine_pieces(tmp_path / "c", clock)
    assert "account_stamp" not in kv_keys(cfg.state_path)
    eng = E.build_engine(cfg, clock=clock, view=view, env={})
    try:
        eng.start()
        assert "account_stamp" not in kv_keys(cfg.state_path)
        assert meta_get(cfg.ledger_path, "account_stamp") is None
        assert kv_get(cfg.state_path, "broker_snapshot") is not None     # kagit motoru kosuyor (sanity)
    finally:
        eng.state.close()
        eng.ledger.close()
    assert "account_stamp" not in kv_keys(cfg.state_path) and meta_get(cfg.ledger_path, "account_stamp") is None


def test_o8_12_init_ledger_refuses_foreign_stamp_writes_nothing_and_never_stamps(tmp_path, monkeypatch):
    cdir, root = make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    tcfg, pcfg = cli_cfg(cdir, "testnet"), cli_cfg(cdir, None)
    seed_ledger(tcfg.ledger_path, stamp="live:baska-hesap")
    n0 = count_rows(tcfg.ledger_path, "param_versions")
    assert cli.main(["init-ledger", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]) == 8
    assert count_rows(tcfg.ledger_path, "param_versions") == n0
    seed_ledger(pcfg.ledger_path, stamp="testnet:testnet-sub")            # kagit init-ledger: var olan her damga yabanci
    m0 = count_rows(pcfg.ledger_path, "param_versions")
    assert cli.main(["init-ledger", "--bot", "learner", "--config-dir", str(cdir)]) == 8
    assert count_rows(pcfg.ledger_path, "param_versions") == m0
    # init-ledger damga yazmaz
    Path(tcfg.ledger_path).unlink()
    for ext in ("-wal", "-shm"):
        Path(tcfg.ledger_path + ext).unlink(missing_ok=True)
    assert cli.main(["init-ledger", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]) == 0
    assert meta_get(tcfg.ledger_path, "account_stamp") is None


def test_o8_13_state_store_ledger_path_parameter_replaces_sibling_lookup(tmp_path):
    other = tmp_path / "other" / "ledger.sqlite"
    seed_ledger(other, rows="decision")
    sp = tmp_path / "s" / "state.sqlite"
    sp.parent.mkdir()
    sp.write_bytes(b"")
    with pytest.raises(StateError):
        StateStore(str(sp), bot="learner", ledger_path=str(other))
    # ledger_path=None: kardes dizindeki dolu defter artik denetlenmez
    seed_ledger(sp.parent / "ledger.sqlite", rows="decision")
    sp.write_bytes(b"")
    StateStore(str(sp), bot="learner", ledger_path=None).close()
    assert "ledger.sqlite" not in (SRC / "trader_engine" / "state.py").read_text(encoding="utf-8")


def test_o8_14_ledger_set_meta_once_semantics(tmp_path):
    lg = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=lambda: T0)
    try:
        assert lg.get_meta("account_stamp") is None
        lg.set_meta_once("account_stamp", "testnet:a")
        assert lg.get_meta("account_stamp") == "testnet:a"
        lg.set_meta_once("account_stamp", "testnet:a")                    # ayni deger: sessiz
        with pytest.raises(L.LedgerError):
            lg.set_meta_once("account_stamp", "live:b")
        assert lg.get_meta("account_stamp") == "testnet:a"
        assert meta_get(str(tmp_path / "l.sqlite"), "account_stamp") == "testnet:a"
        assert count_rows(str(tmp_path / "l.sqlite"), "meta") == len({r[0] for r in
                                                                       _ro(str(tmp_path / "l.sqlite")).execute("SELECT key FROM meta")})
    finally:
        lg.close()


def test_o8_15_backtest_never_imports_or_calls_stamp_golden_unchanged(tmp_path, monkeypatch):
    import trader_engine.stamp as S
    calls = []
    monkeypatch.setattr(S, "verify_or_init_stamp", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(E, "verify_or_init_stamp", lambda *a, **k: calls.append(a), raising=False)
    import test_engine_05_spec as E5
    cfg = E5.make_cfg(tmp_path, "learner", "backtest", (E5.BTC,), 1000.0)
    view = E5.SynthView((E5.BTC,), T.BOOT - timedelta(days=1), T.BOOT + timedelta(days=1), clock=None)
    eng = E.build_engine(cfg, clock=SimClock(T.BOOT), view=view, env={})
    eng.state.close()
    eng.ledger.close()
    assert calls == [], "backtest yolunda damga denetimi cagrildi"
    bt = (SRC / "trader_engine" / "backtest.py").read_text(encoding="utf-8")
    assert not any(w in bt for w in ("account_stamp", "verify_or_init_stamp", ".stamp import", "import stamp")), \
        "backtest.py damga modulunu iceri aliyor/cagiriyor"
    assert not Path(cfg.state_path).exists() or "account_stamp" not in kv_keys(cfg.state_path)
    _golden_when_enabled()


# ====================================================================================== O6: anahtar izin denetimi (beyan yolu kaldirildi)
TODAY = "2026-12-28"                    # test_live_broker_impl_smoke.T0 gunu: eski beyan "bugun" gecerliydi
_UNSET = object()


def perm_outcome(*, env="live", environ=None, restr=None, api=_UNSET, exc=None):
    """LiveBroker.startup_check'i calistirir. restr: sahte borsanin apiRestrictions govdesi; api: istemci yontemini dogrudan
    degistirir (govde turu denemeleri); exc: istemci istisnasi. -> ((kod, ileti) | None, broker, borsa, gecen sure)."""
    b, ex, clock = lb_build(env=env, startup=False, environ=environ)
    if restr is not None:
        ex.restrictions = restr
    if exc is not None:
        def boom():
            raise exc
        b._rest.api_restrictions = boom
    elif api is not _UNSET:
        b._rest.api_restrictions = lambda: api
    t0 = clock.now()
    try:
        b.startup_check()
        out = None
    except EngineExit as e:
        out = (e.code, str(e))
    return out, b, ex, clock.now() - t0


def _inv(field):
    want = dict(PERM_FIELDS)[field]
    r = {f: w for f, w in PERM_FIELDS}
    r[field] = not want
    return r


def _full_ok():
    return {f: w for f, w in PERM_FIELDS}


def _drop(field):
    r = _full_ok()
    del r[field]
    return r


def _txt(field):
    r = _full_ok()
    r[field] = "true"
    return r


UNVERIFIABLE_APIS = {"empty_list": [], "none": None, "missing_field": _drop("ipRestrict"), "text_true": _txt("enableReading")}
EXC_CASES = {
    "uncertain": (dict(exc=ExchangeUncertain("x")), 5, "exchange_unreachable"),
    "reject_1021": (dict(exc=ExchangeReject("x", code=-1021, http=400)), 5, "exchange_unreachable"),
    "auth": (dict(exc=ExchangeAuth("x", code=-2015, http=401)), 8, "auth_failed"),
    "ban_451": (dict(exc=ExchangeBan("x", http=451)), 8, "region_blocked"),
    "ban_403": (dict(exc=ExchangeBan("x", http=403)), 8, "region_blocked"),
    "ban_429": (dict(exc=ExchangeBan("x", http=429, retry_after_s=7)), 5, "exchange_unreachable"),
    "reject_2015": (dict(exc=ExchangeReject("x", code=-2015, http=400)), 8, "key_permission_unverifiable"),
    "runtime": (dict(exc=RuntimeError("x")), 8, "key_permission_unverifiable"),
}


def _expect(out, code, msg):
    assert out is not None, "startup_check gecti (beklenen: ret)"
    assert out[0] == code and msg in out[1], out


def test_o6_01_all_six_fields_correct_passes_to_account_step():
    out, b, ex, _ = perm_outcome(restr=_full_ok())
    assert out is None
    assert ex.count("apiRestrictions") == 1 and ex.count("/fapi/v2/account") >= 1


@pytest.mark.parametrize("field", [f for f, _ in PERM_FIELDS])
def test_o6_02_each_field_inverted_exits_8_key_permission_field(field):
    out, *_ = perm_outcome(restr=_inv(field))
    _expect(out, 8, f"key_permission:{field}")


def test_o6_02b_violation_has_priority_over_missing_fields_and_first_in_required_order():
    out, *_ = perm_outcome(api={"enableWithdrawals": True})                 # diger alanlar eksik
    _expect(out, 8, "key_permission:enableWithdrawals")
    r = _full_ok()
    r["ipRestrict"], r["enableWithdrawals"], r["enableFutures"] = False, True, False
    out, *_ = perm_outcome(api=r)                                           # birden cok ihlal: _REQUIRED_PERMS sirasindaki ilki
    _expect(out, 8, "key_permission:enableFutures")


@pytest.mark.parametrize("case", list(UNVERIFIABLE_APIS))
def test_o6_03_unreadable_response_exits_8_unverifiable(case):
    out, *_ = perm_outcome(api=UNVERIFIABLE_APIS[case])
    _expect(out, 8, "key_permission_unverifiable")


def _all_cases():
    cases = {f"unverifiable_{k}": (dict(api=v), 8, "key_permission_unverifiable") for k, v in UNVERIFIABLE_APIS.items()}
    cases["withdrawals_true"] = (dict(restr=_inv("enableWithdrawals")), 8, "key_permission:enableWithdrawals")
    cases["withdrawals_true_others_missing"] = (dict(api={"enableWithdrawals": True}), 8, "key_permission:enableWithdrawals")
    cases.update({f"exc_{k}": v for k, v in EXC_CASES.items()})
    return cases


@pytest.mark.parametrize("case", list(_all_cases()))
def test_o6_04_attestation_env_never_changes_the_outcome(case, caplog):
    kw, code, msg = _all_cases()[case]
    plain, *_ = perm_outcome(**kw)
    with caplog.at_level(logging.WARNING):
        attested, *_ = perm_outcome(environ={"LIVE_PERMISSION_ATTESTED": TODAY}, **kw)
    _expect(plain, code, msg)
    assert attested == plain, "beyan sonucu degistirdi"


def test_o6_04b_attestation_only_logs_a_warning_when_all_fields_ok(caplog):
    with caplog.at_level(logging.WARNING):
        out, *_ = perm_outcome(restr=_full_ok(), environ={"LIVE_PERMISSION_ATTESTED": TODAY})
    assert out is None
    assert [r for r in caplog.records if r.levelno == logging.WARNING and "LIVE_PERMISSION_ATTESTED" in r.getMessage()]
    assert not [r for r in caplog.records if r.levelno >= logging.CRITICAL and "LIVE_PERMISSION_ATTESTED" in r.getMessage()]


def test_o6_05_uncertain_exits_5_ban_429_sleeps_clock_7s_region_ban_exits_8():
    for k in ("uncertain", "reject_1021"):
        out, *_ = perm_outcome(**EXC_CASES[k][0])
        _expect(out, 5, "exchange_unreachable")
    out, b, ex, dt = perm_outcome(**EXC_CASES["ban_429"][0])
    _expect(out, 5, "exchange_unreachable")
    assert dt == timedelta(seconds=7), dt
    for k in ("ban_451", "ban_403"):
        out, *_ = perm_outcome(**EXC_CASES[k][0])
        _expect(out, 8, "region_blocked")


def test_o6_06_permanent_reject_runtimeerror_auth_mapping():
    out, *_ = perm_outcome(**EXC_CASES["reject_2015"][0])
    _expect(out, 8, "key_permission_unverifiable")
    out, *_ = perm_outcome(**EXC_CASES["reject_1021"][0])
    _expect(out, 5, "exchange_unreachable")
    out, *_ = perm_outcome(**EXC_CASES["auth"][0])
    _expect(out, 8, "auth_failed")
    out, *_ = perm_outcome(**EXC_CASES["runtime"][0])
    _expect(out, 8, "key_permission_unverifiable")


_LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log"}
_ATT = "LIVE_PERMISSION_ATTESTED"


def _attested_violations(path: Path) -> list[str]:
    """`LIVE_PERMISSION_ATTESTED` yalniz uyari gunlugu baglaminda gecer: degeri bir karsilastirmaya/ayristirmaya girmez."""
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    parent = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n):
            parent[c] = n
    bad: list[str] = []

    def is_log_call(n):
        return isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _LOG_METHODS

    def enclosing_fn(n):
        while n in parent:
            n = parent[n]
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return n
        return tree

    def use_ok(n):
        """Bir degerin (n) kullanimi yalniz gunluk argumani ya da dogruluk testi mi?"""
        p = parent.get(n)
        if is_log_call(p):
            return True
        if isinstance(p, ast.JoinedStr) or isinstance(p, ast.FormattedValue):
            return use_ok(p)
        if isinstance(p, (ast.If, ast.IfExp)) and p.test is n:
            return True
        if isinstance(p, ast.UnaryOp) and isinstance(p.op, ast.Not):
            return use_ok(p)
        if isinstance(p, ast.BoolOp):
            return use_ok(p)
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "bool":
            return use_ok(p)
        return False

    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and n.value == _ATT):
            continue
        p = parent.get(n)
        if isinstance(p, ast.Expr):                                  # belge dizgisi
            continue
        if is_log_call(p):                                           # log.warning("LIVE_PERMISSION_ATTESTED ...") (dizgi)
            continue
        top = n
        if isinstance(p, ast.Call) and isinstance(p.func, ast.Attribute) and p.func.attr in ("get", "getenv", "pop"):
            top = p
        elif isinstance(p, ast.Subscript):
            top = p
        elif isinstance(p, ast.Compare) and isinstance(p.ops[0], ast.In) and p.left is n:
            continue                                                 # varlik testi ("X" in environ): deger okunmaz
        else:
            bad.append(f"{path.name}:{n.lineno}: beklenmeyen baglam {type(p).__name__}")
            continue
        q = parent.get(top)
        if isinstance(q, ast.Assign):
            names = [t.id for t in q.targets if isinstance(t, ast.Name)]
            for u in ast.walk(enclosing_fn(top)):
                if isinstance(u, ast.Name) and u.id in names and isinstance(u.ctx, ast.Load) and not use_ok(u):
                    bad.append(f"{path.name}:{u.lineno}: beyan degeri gunluk disinda kullaniliyor ({u.id})")
        elif not use_ok(top):
            bad.append(f"{path.name}:{top.lineno}: beyan degeri gunluk disinda kullaniliyor")
    return bad


def test_o6_07_attested_variable_only_appears_in_warning_log_context():
    files = [p for p in SRC.rglob("*.py") if _ATT in p.read_text(encoding="utf-8")]
    bad = [v for p in files for v in _attested_violations(p)]
    assert not bad, bad


def test_o6_07b_smoke_live_imports_the_single_permission_tuple():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import smoke_live as M
        from trader_engine.brokers import binance_futures as BF
        assert M._REQUIRED_PERMS is BF._REQUIRED_PERMS
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    text = (ROOT / "scripts" / "smoke_live.py").read_text(encoding="utf-8")
    assert "_REQUIRED_PERMS = (" not in text, "smoke_live kendi izin demetini tutuyor"


def test_o6_08_testnet_never_calls_api_restrictions():
    b, ex, _ = lb_build(env="testnet")
    assert ex.count("apiRestrictions") == 0


@pytest.mark.parametrize("case", ["withdrawals_true", "unverifiable_empty_list", "exc_auth", "exc_ban_451", "exc_reject_2015"])
def test_o6_09_permission_refusal_sends_no_account_setting_posts(case):
    kw, code, msg = _all_cases()[case]
    out, b, ex, _ = perm_outcome(**kw)
    _expect(out, code, msg)
    assert setup_posts(ex) == [], setup_posts(ex)


# ====================================================================================== D7: state kilidi hesaba dokunmadan once
def test_d7_01_state_lock_held_elsewhere_build_engine_raises_state_error_zero_http(tmp_path, boots):
    b = boots(tmp_path)
    Path(b.state_path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(b.state_path + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with pytest.raises(StateError):
            b.build()
    finally:
        os.close(fd)
    assert b.ex.requests == [], f"kilit alinamadi ama borsaya istek gitti: {b.ex.requests[:3]}"


def test_d7_02_second_process_exits_3_with_zero_http_first_engine_loop_keeps_running(tmp_path, boots, monkeypatch):
    cdir, root = make_tree(tmp_path, "testnet", overlay_over={"pairs": ["XRP/USDT"]})
    cfg = cli_cfg(cdir)
    b1 = boots(tmp_path, cfg=cfg)
    b1.boot()
    st0 = Path(cfg.status_path).read_bytes() if Path(cfg.status_path).exists() else b""
    ex2 = FakeExchange(lambda: 1_800_000_000_000)
    patch_rest(monkeypatch, ex2)                                        # ikinci surecin REST'i ayri sahte borsaya gider
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BINANCE_API_KEY", KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET)
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]) == 3
    assert ex2.requests == [], "ikinci surec kilide takilmadan borsaya dokundu"
    b1.clock.advance(60)
    b1.eng.live_tick(b1.clock.now())                                    # birinci motor dongusu surer
    assert Path(cfg.status_path).exists() and Path(cfg.status_path).read_bytes() != st0


def test_d7_03_startup_check_exit_8_releases_the_state_lock(tmp_path, boots):
    b = boots(tmp_path)
    b.ex.can_trade = False
    boot_expect_exit(b, 8, "account_cannot_trade")
    Path(b.state_path).parent.mkdir(parents=True, exist_ok=True)
    st = StateStore(b.state_path, bot="learner")                        # kilit sizmamis
    st.close()


def test_d7_04_call_order_flock_then_stamp_then_first_http(tmp_path, boots, monkeypatch):
    b = boots(tmp_path)
    patch_order_spies(monkeypatch, b.events)
    b.build()
    kinds = [e[0] for e in b.events]
    assert "flock" in kinds and "stamp" in kinds and "http" in kinds, kinds
    assert kinds.index("flock") < kinds.index("stamp") < kinds.index("http"), kinds


class SpyBroker:
    """Enjekte edilen broker'in yontem cagrilarini olay listesine yazar (ozellikler gecirilir)."""

    def __init__(self, inner, events):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_events", events)

    def __getattr__(self, name):
        v = getattr(self._inner, name)
        if callable(v):
            def call(*a, **k):
                self._events.append(("broker", name))
                return v(*a, **k)
            return call
        return v


def test_d7_04b_injected_broker_untouched_until_lock_and_stamp_done(tmp_path, monkeypatch):
    clock = SimClock(T.BOOT)
    ex = FakeExchange(_now_ms(clock))
    events: list = []
    cfg = make_cfg(tmp_path)
    rest = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=_Sess(ex, events), now_ms=_now_ms(clock),
                            sleep=clock.sleep, conditional_mode=cfg.live.conditional_mode)
    inner = LiveBroker(cfg.live, "testnet", cfg.leverage, list(cfg.pairs), rest, clock, cfg.cost.taker_fee, environ={})
    view = T.FeedView(cfg.pairs, T.DEC - timedelta(days=3), T.DEC + timedelta(days=4), mode="flat", base=2.0, clock=clock)
    patch_order_spies(monkeypatch, events)
    eng = E.build_engine(cfg, clock=clock, view=view, broker=SpyBroker(inner, events), env={})
    try:
        kinds = [e[0] for e in events]
        assert "flock" in kinds and "stamp" in kinds, kinds
        first_touch = min([i for i, k in enumerate(kinds) if k in ("broker", "http")], default=len(kinds))
        assert kinds.index("flock") < kinds.index("stamp") < first_touch, kinds
    finally:
        eng.state.close()
        eng.ledger.close()


def test_d7_05_paper_build_order_ledger_then_state_unchanged_no_stamp_files(tmp_path, monkeypatch):
    import trader_engine.state as ST
    events: list = []
    real_open = L.open_ledger
    monkeypatch.setattr(L, "open_ledger", lambda *a, **k: (events.append("ledger"), real_open(*a, **k))[1])
    real_cls = ST.StateStore

    class SpyState(real_cls):
        def __init__(self, *a, **k):
            events.append("state")
            super().__init__(*a, **k)
    monkeypatch.setattr(ST, "StateStore", SpyState)
    monkeypatch.setattr(E, "StateStore", SpyState, raising=False)
    clock = SimClock(T.BOOT)
    cfg, view = _paper_engine_pieces(tmp_path, clock)
    eng = E.build_engine(cfg, clock=clock, view=view, env={})
    eng.state.close()
    eng.ledger.close()
    assert events[:2] == ["ledger", "state"], events
    assert "account_stamp" not in kv_keys(cfg.state_path) and meta_get(cfg.ledger_path, "account_stamp") is None
    _golden_when_enabled()


# ====================================================================================== D2: giris oncesi hesap modu dogrulamasi
def d2_env(tmp, denv_factory, **kw):
    """Hazirlanmis duz cift (XRP): acilis tamam, pozisyon yok. Giris emri dogrudan `broker.market_order` ile denenir."""
    return denv_factory(tmp, **kw).boot()


def entry_req(seq=0, qty=10.0, pair=XRP):
    return T_req("entry", qty, seq=seq, pair=pair)


def T_req(role, qty, trigger=None, seq=0, pair=XRP):
    cid = make_client_id("learner", role, pair, "long", T.DEC, seq)
    return OrderRequest(client_id=cid, pair=pair, role=role, order_side="buy" if role == "entry" else "sell", qty=qty,
                        trigger_price=trigger, reduce_only=role != "entry", leverage=3 if role == "entry" else None,
                        created_ts=T.DEC)


def order_posts(ex):
    return ex.count("/fapi/v1/order", "POST")


def pr_symbol_reads(ex, symbol=SYM):
    return [r for r in ex.requests if r[0] == "GET" and r[1] == "/fapi/v2/positionRisk" and r[2].get("symbol") == symbol]


@pytest.mark.parametrize("drift", ["leverage", "margin"])
def test_d2_01_02_mode_drift_blocks_entry_counts_and_logs_critical(tmp_path, denv_factory, caplog, drift):
    e = d2_env(tmp_path, denv_factory)
    if drift == "leverage":
        e.ex.lev[SYM] = e.cfg.leverage + 1
    else:
        e.ex.margin_type[SYM] = "cross"
    n0 = order_posts(e.ex)
    with caplog.at_level(logging.WARNING):
        r = e.broker.market_order(entry_req())
    assert r.status == "rejected" and r.reason == "not_prepared", r
    assert order_posts(e.ex) == n0, "sapma varken giris emri gonderildi"
    assert e.broker.counters()["account_mode_drift"] == 1
    assert [x for x in caplog.records if x.levelno == logging.CRITICAL and f"account_mode_drift:{XRP}" in x.getMessage()]
    assert "account_mode_drift" in e.broker.health() and e.broker.health()["account_mode_drift"] == 1


def test_d2_03_correct_values_entry_sent_after_exactly_one_fresh_position_risk_read(tmp_path, denv_factory):
    e = d2_env(tmp_path, denv_factory)
    n_reads, n_posts = len(pr_symbol_reads(e.ex)), order_posts(e.ex)
    i0 = len(e.ex.requests)
    r = e.broker.market_order(entry_req())
    assert r.status == "filled", r
    assert len(pr_symbol_reads(e.ex)) - n_reads == 1, "giris basina tam 1 ek positionRisk(symbol) okumasi olmali"
    seq = [(m, p) for m, p, q in e.ex.requests[i0:] if (m == "GET" and p == "/fapi/v2/positionRisk") or (m == "POST" and p == "/fapi/v1/order")]
    assert seq.index(("GET", "/fapi/v2/positionRisk")) < seq.index(("POST", "/fapi/v1/order"))
    assert order_posts(e.ex) - n_posts == 1
    assert e.broker.counters()["account_mode_drift"] == 0 and e.broker.counters()["account_mode_unverified"] == 0


@pytest.mark.parametrize("case", ["uncertain", "ban_429", "empty_list", "leverage_missing"])
def test_d2_04_unverifiable_read_blocks_entry_counts_unverified(tmp_path, denv_factory, case):
    e = d2_env(tmp_path, denv_factory)
    n0 = order_posts(e.ex)
    if case == "uncertain":
        for _ in range(6):                                              # istemci yeniden denemelerini de tuket
            e.ex.inject("/fapi/v2/positionRisk", FakeResp(503, {"code": -1001, "msg": "x"}))
    elif case == "ban_429":
        for _ in range(6):
            e.ex.inject("/fapi/v2/positionRisk", FakeResp(429, {"code": -1003, "msg": "rate"}, {"Retry-After": "7"}))
    elif case == "empty_list":
        e.ex.inject("/fapi/v2/positionRisk", FakeResp(200, []))
    else:
        row = e.ex._pr(SYM)
        del row["leverage"]
        e.ex.inject("/fapi/v2/positionRisk", FakeResp(200, [row]))
    r = e.broker.market_order(entry_req())
    assert r.status == "rejected" and r.reason == "not_prepared", r
    assert order_posts(e.ex) == n0
    assert e.broker.counters()["account_mode_unverified"] == 1, e.broker.counters()
    if case == "ban_429":
        assert e.broker.last_ban is not None and e.broker.counters()["exchange_bans"] >= 1, "ban penceresi kaydi yok"


def test_d2_05_exit_and_stop_paths_never_read_or_blocked_while_drift_persists(tmp_path, denv_factory):
    e = denv_factory(tmp_path).boot()
    pos = e.enter()
    assert pos is not None and pos.status == "open"
    e.ex.lev[SYM] = e.cfg.leverage + 1                                   # sapma suruyor
    e.ex.margin_type[SYM] = "cross"
    n_reads = len(pr_symbol_reads(e.ex))
    qty = float(e.ex.pos[SYM]["amt"])
    stop = e.broker.place_stop(T_req("stop", qty, 1.95, seq=7))          # stop yenileme (yeni kimlik)
    assert stop.status == "accepted", stop
    ex_r = e.broker.market_order(T_req("exit", qty, seq=8))
    assert ex_r.status in ("accepted", "filled"), ex_r
    assert len(pr_symbol_reads(e.ex)) == n_reads, "cikis/stop yolu ek positionRisk(symbol) okumasi yapti"
    assert e.broker.counters()["account_mode_drift"] == 0 and e.broker.counters()["account_mode_unverified"] == 0
    assert e.ex.pos[SYM]["amt"] == 0


def test_d2_06_drift_corrected_next_entry_passes_without_restart(tmp_path, denv_factory):
    e = d2_env(tmp_path, denv_factory)
    e.ex.lev[SYM] = e.cfg.leverage + 1
    assert e.broker.market_order(entry_req(seq=0)).reason == "not_prepared"
    e.ex.lev[SYM] = e.cfg.leverage
    r = e.broker.market_order(entry_req(seq=1))
    assert r.status == "filled", r
    assert e.broker.counters()["account_mode_drift"] == 1


def test_d2_07_cache_trap_change_after_last_sync_still_detected(tmp_path, denv_factory):
    e = d2_env(tmp_path, denv_factory)
    e.broker.poll(e.clock.now())                                         # _sync: dogru degerler okunur
    assert e.broker.market_order(entry_req(seq=0)).status == "filled"
    e.ex.external_close(SYM)
    e.broker.poll(e.clock.now())
    e.ex.lev[SYM] = e.cfg.leverage + 5                                   # _sync'ten SONRA borsada degisir; araya _sync girmez
    n0 = order_posts(e.ex)
    r = e.broker.market_order(entry_req(seq=2))
    assert r.status == "rejected" and r.reason == "not_prepared" and order_posts(e.ex) == n0
    assert e.broker.counters()["account_mode_drift"] == 1


def test_d2_08_engine_level_not_prepared_closes_opening_position_no_stop_failed_keeps_running(tmp_path, denv_factory):
    e = denv_factory(tmp_path).boot()
    e.ex.lev[SYM] = e.cfg.leverage + 1
    e.enter()
    assert e.pos() is None, "reddedilen girisin `opening` pozisyonu kapanmadi"
    assert e.entry_posts() == []
    assert not e.engine.state.block_has("stop_failed") and "stop_failed" not in e.state.block_reasons()
    assert e.state.open_positions() == []
    e.tick(6)
    e.tick(6)                                                            # motor calismayi surdurur
    e.ex.lev[SYM] = e.cfg.leverage                                       # sapma duzelince sonraki bar girisi gecer
    e.enter(D=T.DEC + timedelta(hours=1))
    assert e.pos() is not None and e.pos().status == "open"


def test_d2_09_no_margin_or_leverage_post_while_running(tmp_path, denv_factory):
    e = d2_env(tmp_path, denv_factory)
    n0 = len(setup_posts(e.ex))
    e.ex.lev[SYM] = e.cfg.leverage + 1                                   # sapma: motor DUZELTMEYE calismaz
    for i in range(3):
        e.broker.market_order(entry_req(seq=i))
        e.tick(6)
    e.ex.lev[SYM] = e.cfg.leverage
    e.enter()
    for _ in range(3):
        e.tick(6)
    assert len(setup_posts(e.ex)) == n0, [x for x in setup_posts(e.ex)][n0:]


# ====================================================================================== E1 / E2: mutlak yollar, tek yukleyici
def test_e1_01_load_cli_config_absolute_paths_paper_var_dir_raw(tmp_path):
    from trader_engine.config import load_cli_config
    cdir, root = make_tree(tmp_path, "testnet", absolute=False)
    r = str(root.resolve())
    c = load_cli_config(str(cdir), env="testnet")
    assert c.kill_file == f"{r}/shared/testnet/KILL" and c.pause_file == f"{r}/shared/testnet/PAUSE"
    assert c.var_dir == f"{r}/var-testnet"
    p = load_cli_config(str(cdir))
    raw = cli_cfg(cdir, None)
    assert p.kill_file == f"{r}/shared/KILL" and p.pause_file == f"{r}/shared/PAUSE"
    assert os.path.isabs(p.kill_file) and os.path.isabs(p.pause_file)
    assert p.var_dir == "var" and p.market_db == raw.market_db and p.history_dir == raw.history_dir, \
        "paper: var_dir/market_db/history_dir oldugu gibi kalmali"
    assert raw.kill_file == "shared/KILL" and raw.pause_file == "shared/PAUSE"       # saf yukleyici ham degeri dondurur


def test_e1_01b_already_absolute_fields_unchanged_and_absolutize_paths_signature(tmp_path):
    from trader_engine.config import absolutize_paths, load_cli_config
    cdir, root = make_tree(tmp_path, "testnet", absolute=True)
    raw = cli_cfg(cdir, "testnet")
    c = load_cli_config(str(cdir), env="testnet")
    assert (c.kill_file, c.pause_file, c.var_dir) == (raw.kill_file, raw.pause_file, raw.var_dir)
    cdir2, root2 = make_tree(tmp_path / "x", "testnet", absolute=False)
    c2 = absolutize_paths(cli_cfg(cdir2, "testnet"), cdir2 / "engine.base.json")
    assert c2.kill_file == f"{root2.resolve()}/shared/testnet/KILL" and c2.var_dir == f"{root2.resolve()}/var-testnet"


def test_e1_02_pause_from_another_cwd_writes_next_to_config_not_cwd(tmp_path, monkeypatch):
    cdir, root = make_tree(tmp_path, "testnet", absolute=False)
    other = tmp_path / "baska"
    other.mkdir()
    monkeypatch.chdir(other)
    r = root.resolve()
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(cdir), "--reason", "manual", "--by", "x"]) == 0
    assert (r / "shared" / "PAUSE.learner").exists()
    assert not (other / "shared").exists()
    assert cli.main(["pause", "--bot", "learner", "--config-dir", str(cdir), "--clear", "--reason", "manual", "--by", "x"]) == 0
    assert not (r / "shared" / "PAUSE.learner").exists()


def test_e1_03_env_testnet_pause_and_capital_list_from_another_cwd_create_nothing_in_cwd(tmp_path, monkeypatch, capsys):
    cdir, root = make_tree(tmp_path, "testnet", absolute=False)
    other = tmp_path / "baska"
    other.mkdir()
    monkeypatch.chdir(other)
    r = root.resolve()
    argv = ["--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"]
    assert cli.main(["pause", *argv, "--reason", "manual", "--by", "x"]) == 0
    assert (r / "shared" / "testnet" / "PAUSE.learner").exists()
    assert (r / "var-testnet" / "learner" / "pause_audit.jsonl").exists()
    capsys.readouterr()
    assert cli.main(["pause", *argv, "--list"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert os.path.isabs(out["pause_file"]) and out["pause_file"].startswith(str(r / "shared" / "testnet" / "PAUSE"))
    cli.main(["capital", "list", *argv])
    assert list(other.iterdir()) == [], f"calisma dizininde dosya olustu: {list(other.iterdir())}"


def test_e1_04_engine_entry_pause_path_equals_cli_path_from_two_cwds(tmp_path, boots, monkeypatch):
    cdir, root = make_tree(tmp_path, "testnet", absolute=False, overlay_over={"pairs": ["XRP/USDT"]})
    ns = argparse.Namespace(config_dir=str(cdir), bot="learner", env="testnet")
    a, b = tmp_path / "cwd_a", tmp_path / "cwd_b"
    a.mkdir()
    b.mkdir()
    monkeypatch.chdir(a)
    cfg_a = cli._load_cfg(ns)
    bt = boots(tmp_path, cfg=cfg_a)
    eng = bt.build()
    engine_path = eng.pause.path
    monkeypatch.chdir(b)
    cli_path = cli._ladder_pause(cli._load_cfg(ns)).path
    assert engine_path == cli_path and os.path.isabs(cli_path), (engine_path, cli_path)
    assert engine_path == f"{root.resolve()}/shared/testnet/PAUSE.learner"


def test_e1_04b_cli_run_logs_absolute_pause_path(tmp_path, monkeypatch, caplog):
    cdir, root = make_tree(tmp_path, "testnet", absolute=False, overlay_over={"pairs": ["XRP/USDT"]})
    cfg = cli.__dict__["_load_cfg"](argparse.Namespace(config_dir=str(cdir), bot="learner", env="testnet"))
    Path(cfg.state_path).parent.mkdir(parents=True, exist_ok=True)
    patch_rest(monkeypatch, FakeExchange(lambda: 1_800_000_000_000))
    monkeypatch.setenv("BINANCE_API_KEY", KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET)
    monkeypatch.chdir(tmp_path)
    fd = os.open(cfg.state_path + ".lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with caplog.at_level(logging.INFO):
            cli.main(["run", "--bot", "learner", "--config-dir", str(cdir), "--env", "testnet"])
    finally:
        os.close(fd)
    assert any(f"{root.resolve()}/shared/testnet/PAUSE.learner" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("mode", ["testnet", "live"])
@pytest.mark.parametrize("field,val", [("pause_file", "shared/{m}/PAUSE"), ("kill_file", "shared/{m}/KILL"), ("var_dir", "var-{m}")])
def test_e1_05_build_engine_live_modes_refuse_relative_paths(tmp_path, boots, monkeypatch, mode, field, val):
    monkeypatch.chdir(tmp_path)
    kw = {"kill_file": str(tmp_path / mode / "KILL"), "pause_file": str(tmp_path / mode / "PAUSE")}
    var = str(tmp_path / f"var-{mode}")
    if field == "var_dir":
        var = val.format(m=mode)
    else:
        kw[field] = val.format(m=mode)
    cfg = make_cfg(tmp_path, mode, var=var, **kw)
    b = boots(tmp_path, cfg=cfg)
    with pytest.raises(ConfigError, match=f"relative_path:{field}"):
        b.build()
    assert b.ex.requests == []


def test_e1_06_config_dir_not_named_config_uses_itself_as_root(tmp_path):
    from trader_engine.config import load_cli_config
    cdir, root = make_tree(tmp_path, "testnet", absolute=False, cname="cfgx")
    c = load_cli_config(str(cdir), env="testnet")
    r = str(cdir.resolve())
    assert c.kill_file == f"{r}/shared/testnet/KILL" and c.pause_file == f"{r}/shared/testnet/PAUSE"
    assert c.var_dir == f"{r}/var-testnet"


def _scripts_on_path():
    p = str(ROOT / "scripts")
    if p not in sys.path:
        sys.path.insert(0, p)


def test_e2_01_smoke_scripts_use_the_single_cli_loader():
    for n in ("smoke_live.py", "smoke_testnet.py"):
        text = (ROOT / "scripts" / n).read_text(encoding="utf-8")
        assert "load_engine_config(" not in text, n
        assert "load_cli_config(" in text, n
    stray = [p.name for p in (ROOT / "scripts").glob("*.py")
             if "load_engine_config(" in p.read_text(encoding="utf-8")
             and any(w in p.read_text(encoding="utf-8") for w in ("kill_file", "pause_file"))]
    assert not stray, f"kill/pause okuyup load_engine_config kullanan betikler: {stray}"


def _two_positions(ex):
    for sym, qty in (("XRPUSDT", "10"), ("DOGEUSDT", "40")):
        ex.fill_market(sym, "BUY", qty)
        ex._new_cond(sym, "SELL", "STOP_MARKET", Decimal(qty), Decimal("1.0"), "MARK_PRICE", f"trTx-engine-{sym}")


def test_e2_02_smoke_t15_kill_goes_to_config_root_kill_file_from_another_cwd(tmp_path, monkeypatch):
    _scripts_on_path()
    import smoke_testnet as M
    cdir, root = make_tree(tmp_path, "testnet", absolute=False)
    other = tmp_path / "baska"
    other.mkdir()
    monkeypatch.chdir(other)
    clock = SimClock(datetime(2026, 12, 28, 9, 0, tzinfo=UTC))
    ex = FakeExchange(_now_ms(clock))
    kill_path = root.resolve() / "shared" / "testnet" / "KILL"
    seen = []
    real_main = cli.main

    def rec(args):
        rc = real_main(args)                                             # gercek CLI, baska calisma dizininden
        if args[0] == "kill" and "--clear" not in args:
            seen.append((rc, kill_path.exists()))
            for s in list(ex.pos):                                       # motorun KILL tepkisi
                ex.external_close(s)
            for a in ex.algos.values():
                a["algoStatus"] = "CANCELED"
        return rc
    monkeypatch.setattr(M, "_cli", rec)
    out: list = []
    env = {"BINANCE_API_KEY": KEY, "BINANCE_API_SECRET": SECRET}
    M.main(["--config-dir", str(cdir), "--out-root", str(tmp_path / "out"), "--ack-no-withdraw", "--env", "testnet", "--step", "t15"],
           environ=env, rest_factory=lambda **k: SignedRestClient(session=ex.session, **k), clock=clock,
           input_fn=lambda *_: _two_positions(ex) or "", say=out.append)
    assert seen, "\n".join(out)
    assert seen[0] == (0, True), f"KILL <kok>/shared/testnet/KILL'e yazilmadi: {seen} {out}"
    assert not (other / "shared").exists()


def _guard_cfg(tmp, mode, tag=TAG, **repl):
    cfg = make_cfg(tmp, mode, tag)
    return dataclasses.replace(cfg, **repl) if repl else cfg


def test_e2_03_guard_config_ignores_testnet_in_root_dir_name_and_rejects_paper_paths(tmp_path):
    _scripts_on_path()
    import smoke_testnet_lib as SL
    root = tmp_path / "testnet-x"
    ok = _guard_cfg(root, "testnet", kill_file=str(root / "shared" / "testnet" / "KILL"),
                    pause_file=str(root / "shared" / "testnet" / "PAUSE"))
    SL.guard_config(ok)                                                  # gecmeli
    for repl in ({"kill_file": str(root / "shared" / "KILL")}, {"pause_file": str(root / "shared" / "PAUSE")}):
        cfg = _guard_cfg(root, "testnet", **{"kill_file": str(root / "shared" / "testnet" / "KILL"),
                                             "pause_file": str(root / "shared" / "testnet" / "PAUSE"), **repl})
        with pytest.raises(SL.SafetyError):
            SL.guard_config(cfg)
    bad_var = _guard_cfg(root, "testnet", var_dir=str(root / "var"), kill_file=str(root / "shared" / "testnet" / "KILL"),
                         pause_file=str(root / "shared" / "testnet" / "PAUSE"))
    with pytest.raises(SL.SafetyError):
        SL.guard_config(bad_var)


def test_e2_03b_live_guard_config_same_rule_last_two_components_only(tmp_path):
    _scripts_on_path()
    import smoke_live as SLV
    import smoke_testnet_lib as SL
    root = tmp_path / "testnet-x"
    env = {"LIVE_CONFIRM": "live-sub"}
    ok = _guard_cfg(root, "live", "live-sub", kill_file=str(root / "shared" / "live" / "KILL"),
                    pause_file=str(root / "shared" / "live" / "PAUSE"))
    SLV.guard_config(ok, env)                                            # kok dizin adinda `testnet` gecmesi yanlis ret vermez
    bad = _guard_cfg(root, "live", "live-sub", kill_file=str(root / "shared" / "testnet" / "KILL"),
                     pause_file=str(root / "shared" / "live" / "PAUSE"))
    with pytest.raises(SL.SafetyError):
        SLV.guard_config(bad, env)


# ====================================================================================== E4: <ledger>.spool.corrupt.jsonl yedek + saglik alarmi
def _load_script(name):
    spec = importlib.util.spec_from_file_location(name + "_dd8", ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(ROOT / "scripts"))
    spec.loader.exec_module(m)
    return m


BK_NOW = datetime(2026, 12, 5, 3, 0, tzinfo=UTC)


def _backup_env(tmp):
    var = Path(tmp) / "var"
    seed_ledger(var / "learner" / "ledger.sqlite")
    seed_state(var / "learner" / "state.sqlite")
    return var, Path(tmp) / "bk"


def _run_backup(tmp, var):
    B = _load_script("health_backup")
    return B, B.run_backup(str(Path(tmp) / "bk"), str(var), 14, now=BK_NOW, free_bytes=lambda: 10 ** 12, bots=("learner",))


def test_e4_01_corrupt_spool_is_copied_byte_identical_and_recorded_in_manifest(tmp_path):
    var, bk = _backup_env(tmp_path)
    src = var / "learner" / "ledger.sqlite.spool.corrupt.jsonl"
    src.write_bytes(b'{"row":"torn","why":"JSONDecodeError"}\n{"row":"x","why":"JSONDecodeError"}\n')
    B, (code, m) = _run_backup(tmp_path, var)
    day = bk / "2026-12-05"
    assert code == 0 and m["ok"] is True, m
    out = day / "ledger_learner.sqlite.spool.corrupt.jsonl"
    assert out.read_bytes() == src.read_bytes()
    assert m["files"]["ledger_learner.sqlite"]["spool_corrupt_bytes"] == src.stat().st_size
    assert json.loads((day / "MANIFEST.json").read_text())["files"]["ledger_learner.sqlite"]["spool_corrupt_bytes"] == src.stat().st_size
    assert "spool_corrupt_bytes" not in m["files"]["state_learner.sqlite"]


@pytest.mark.parametrize("kind", ["absent", "empty"])
def test_e4_02_no_or_empty_corrupt_file_no_copy_no_field_backup_ok(tmp_path, kind):
    var, bk = _backup_env(tmp_path)
    if kind == "empty":
        (var / "learner" / "ledger.sqlite.spool.corrupt.jsonl").write_bytes(b"")
    B, (code, m) = _run_backup(tmp_path, var)
    assert code == 0 and m["ok"] is True
    assert not (bk / "2026-12-05" / "ledger_learner.sqlite.spool.corrupt.jsonl").exists()
    assert "spool_corrupt_bytes" not in m["files"]["ledger_learner.sqlite"]


def test_e4_02b_copy_failure_marks_entry_failed_and_backup_failed(tmp_path, monkeypatch):
    var, bk = _backup_env(tmp_path)
    (var / "learner" / "ledger.sqlite.spool.corrupt.jsonl").write_bytes(b"x\n")
    B = _load_script("health_backup")
    real = shutil.copyfile

    def boom(src, dst, *a, **k):
        if "spool.corrupt" in str(src) or "spool.corrupt" in str(dst):
            raise OSError("disk dolu")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(B.shutil, "copyfile", boom)
    code, m = B.run_backup(str(bk), str(var), 14, now=BK_NOW, free_bytes=lambda: 10 ** 12, bots=("learner",))
    assert code != 0 and m["ok"] is False
    assert m["files"]["ledger_learner.sqlite"]["ok"] is False


def _hsnap(probe, *, warm=False):
    from trader_core import health as H
    NOW = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
    api = {"learner": H.ApiProbe(ping_ok=True, last_process_at=NOW - timedelta(seconds=30),
                                 last_candle_open=datetime(2026, 11, 16, 12, 0, tzinfo=UTC), open_trade_ids=(), dry_run=True)}
    kw = {}
    if warm:
        kw["containers"] = {"trader-learner": H.ContainerProbe(state="running", restart_count=0,
                                                               started_at=NOW - timedelta(seconds=60), oom_killed=False)}
    return H.HealthSnapshot(now=NOW, timeframe_s=3600, api=api, ledger={"learner": probe}, **kw)


def _eval(probe, **kw):
    from trader_core import health as H
    cfg = dataclasses.replace(H.DEFAULT_CFG, require_bots=("learner",))
    return H.evaluate(_hsnap(probe, **kw), cfg)


def _good_probe(**kw):
    from trader_core import health as H
    base = dict(last_write_at=datetime(2026, 11, 16, 12, 0, 2, tzinfo=UTC), spool_lines=0, unledgered_ids=(), orphan_ids=(),
                schema_ok=True, has_active_params=True)
    base.update(kw)
    return H.LedgerProbe(**base)


def _one(rep, name):
    got = [r for r in rep.results if r.name == name]
    assert len(got) == 1, [r.name for r in rep.results]
    return got[0]


@pytest.mark.parametrize("warm", [False, True])
def test_e4_03_spool_corrupt_check_crit_ok_unknown(warm):
    from trader_core import health as H
    r = _one(_eval(_good_probe(spool_corrupt_lines=3), warm=warm), "spool_corrupt:learner")
    assert r.status == H.Status.CRIT and r.code == "spool_corrupt" and r.value == 3, "isinma CRIT'i yumusatmamali"
    assert _eval(_good_probe(spool_corrupt_lines=3), warm=warm).overall == H.Status.CRIT
    r0 = _one(_eval(_good_probe(spool_corrupt_lines=0), warm=warm), "spool_corrupt:learner")
    assert r0.status == H.Status.OK
    rn = _one(_eval(_good_probe(spool_corrupt_lines=None), warm=warm), "spool_corrupt:learner")
    assert rn.status == H.Status.UNKNOWN and rn.code == "spool_corrupt_unreadable"


def test_e4_04_spool_pending_does_not_mask_spool_corrupt():
    rep = _eval(_good_probe(spool_lines=5, spool_corrupt_lines=1))
    g, c = _one(rep, "ledger_gate:learner"), _one(rep, "spool_corrupt:learner")
    assert g.code == "spool_pending" and c.code == "spool_corrupt"


def test_e4_05_immediate_code_first_sight_alert_and_recovery_message():
    from trader_core import health as H
    assert "spool_corrupt" in H.IMMEDIATE_CODES
    t0 = datetime(2026, 11, 16, 12, 30, tzinfo=UTC)
    bad = H.HealthReport(t0, (H.CheckResult("spool_corrupt:learner", H.Status.CRIT, "spool_corrupt", "3 satir", 3.0),),
                         H.Status.CRIT, False)
    first, st0 = H.plan_alerts(bad, None, t0)
    assert not first                                  # kirmizi cift dogrulama: ilk tur sari
    t0 = t0 + timedelta(minutes=5)
    alerts, st = H.plan_alerts(bad, st0, t0)
    got = [a for a in alerts if a.code == "spool_corrupt"]
    assert got and got[0].level == H.Status.CRIT, alerts
    assert "Deftere yazılamayan bozuk kayıt var" in got[0].title
    t1 = t0 + timedelta(minutes=10)
    ok = H.HealthReport(t1, (H.CheckResult("spool_corrupt:learner", H.Status.OK, "ok", "0 satir", 0.0),), H.Status.OK, True)
    alerts2, _ = H.plan_alerts(ok, st, t1)
    rec = [a for a in alerts2 if a.code == "spool_corrupt"]
    assert rec and rec[0].level == H.Status.OK and "Bozuk kayıt dosyası temizlendi" in rec[0].title, alerts2


def test_e4_06_probe_ledger_counts_corrupt_lines_zero_when_absent_none_when_unreadable(tmp_path):
    R = _load_script("health_run")
    db = tmp_path / "ledger.sqlite"
    seed_ledger(db)
    cor = Path(str(db) + ".spool.corrupt.jsonl")
    assert R.probe_ledger(str(db), "learner", ()).spool_corrupt_lines == 0
    cor.write_text('{"a":1}\n{"b":2}\n')
    assert R.probe_ledger(str(db), "learner", ()).spool_corrupt_lines == 2
    cor.unlink()
    cor.mkdir()                                                          # dosya yerinde dizin: okunamaz
    assert R.probe_ledger(str(db), "learner", ()).spool_corrupt_lines is None


def test_e4_06b_probe_ledger_fills_corrupt_count_even_when_ledger_cannot_be_opened(tmp_path):
    R = _load_script("health_run")
    db = tmp_path / "yok.sqlite"
    Path(str(db) + ".spool.corrupt.jsonl").write_text("a\nb\n")
    assert R.probe_ledger(str(db), "learner", ()).spool_corrupt_lines == 2


def test_e4_07_quarantined_spool_row_makes_next_health_run_crit_spool_corrupt(tmp_path):
    from trader_core import health as H
    R = _load_script("health_run")
    db = tmp_path / "ledger.sqlite"
    lg = L.open_ledger(str(db), "learner", create=True, clock=lambda: T0)
    try:
        lg.init_params(PARAMS, reason="strategy:price_action_v1@1b.0")
        Path(lg._spool_path()).write_text('{"type":"entry","trade_id":9,"decision_id":')     # yarim yazim
        lg.drain_spool()
        assert Path(lg._corrupt_path()).exists()
    finally:
        lg.close()
    probe = R.probe_ledger(str(db), "learner", ())
    assert probe.spool_lines == 0 and probe.spool_corrupt_lines == 1
    r = _one(_eval(probe), "spool_corrupt:learner")
    assert r.status == H.Status.CRIT and r.code == "spool_corrupt"


def test_e4_08_positional_six_argument_ledger_probe_still_works():
    from trader_core import health as H
    p = H.LedgerProbe(datetime(2026, 11, 16, tzinfo=UTC), 0, (), (), True, True)
    assert p.spool_corrupt_lines is None
    last = dataclasses.fields(H.LedgerProbe)[-1]
    assert last.name == "spool_corrupt_lines" and last.default is None
