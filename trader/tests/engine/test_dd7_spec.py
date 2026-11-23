"""DD-7 (yasak/ban kaliciligi) bagimsiz sartname testleri: docs/dd7-ban-kalicilik-spec.md (v1, 18 Kasim 2026).

Bagimsiz test ajani; yalniz sartnameden (dosya/alan/sabit/sayac/cikis kodu/hata kodu/islev imzasi adlari), COMMITTED koddan (HEAD) ve
mevcut test duzeneklerinden (fake_exchange, test_dd8_spec.Boot/DEnv, test_live_broker_impl_smoke.build, test_engine_01_spec.make_env,
test_oi_collector, test_health_spec) yazildi. Gerceklemenin (src/ calisma agaci) taslak farklarina BAKILMADI.
Gercek ag/saat yok: sahte borsa (FakeExchange, HTTP duzeyi), sahte oturum, SimClock/enjekte `now_ms`+`sleep`.
"Istek sayisi" daima sahte borsanin `requests` kayit listesinden (ya da sahte oturumun/istemcinin cagri sayacindan) olculur.

Adlandirma: test_<bolum>_<no>_...  (p = ban_store, m = imzali istemci+motor acilisi, f = feed, t = OI toplayici,
g = agirlik esiginde giris reddi, s = saglik alarmi). Numara sartnamedeki "P-3" -> test_p_03_...

Yeni modulleri (`trader_core.ban_store`, `H.BanProbe`, ...) testler FONKSIYON ICINDE iceri alir: gerceklenmemisse yalniz o test
basarisiz olur, toplama hatasi olmaz.

`# SPEC-AMBIGUOUS:` ile isaretli yerler sartnamenin adlandirmadigi noktalardaki tahminlerdir.
"""
from __future__ import annotations

import dataclasses
import http.client
import importlib
import io
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import test_dd8_spec as D8
import test_engine_live_spec as TL
from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from test_engine_01_spec import BTC, T_START, Resp, dt, make_env  # noqa: F401
from test_live_broker_impl_smoke import XRP, build as lb_build
from test_live_broker_impl_smoke import req as lb_req
from trader_core import health as H
from trader_engine.bars import to_ms
from trader_engine.clock import SimClock
from trader_engine.exchange.binance_rest import BASES, SignedRestClient
from trader_engine.marketdata import feed as F
from trader_engine.marketdata import oi_collector as C
from trader_engine.marketdata.feed import Feed, FeedConfig
from trader_engine.marketdata.rest_public import ExchangeBan, PublicRestClient
from trader_engine.marketdata.store import MarketStore

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
SYM = "XRPUSDT"
FAPI = "https://fapi.binance.com"
HOST = "fapi.binance.com"
TESTNET_HOST = "testnet.binancefuture.com"
NOW = 1_800_000_000_000                       # tam saniye; ban_store testlerinin sahte "simdi"si (ms)
NOW_S = NOW // 1000


# ====================================================================================== ortak yardimcilar
def bs():
    """`trader_core.ban_store` (yeni modul): her testte tembel icerik aktarma."""
    return importlib.import_module("trader_core.ban_store")


def good_rec(**over) -> dict:
    d = {"v": 1, "host": HOST, "until_ms": NOW + 120_000, "http": 418, "source": "feed", "written_ms": NOW}
    d.update(over)
    return d


def put_text(path, text: str, mtime_ms: int | None = None) -> str:
    Path(path).write_text(text, encoding="utf-8")
    if mtime_ms is not None:
        os.utime(path, (mtime_ms / 1000, mtime_ms / 1000))
    return str(path)


def put_json(path, obj, mtime_ms: int | None = None) -> str:
    return put_text(path, json.dumps(obj), mtime_ms)


def load_json(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def ms_of(clock) -> int:
    return int(clock.now().timestamp() * 1000)


def spy_sleep(monkeypatch, clock, hook=None):
    """`clock.sleep`i sarmalar: (saniye, hook()) kaydi tutar, sonra gercekten (SimClock) ilerletir."""
    log: list = []
    orig = clock.sleep

    def sleep(s):
        log.append((s, hook() if hook else None))
        return orig(s)

    monkeypatch.setattr(clock, "sleep", sleep)
    return log


def run_pytest(*files: str, timeout: int = 1800) -> None:
    """Mevcut test dosyalarinin DEGISMEDEN gectigini dogrular (yeni surec; ayni yorumlayici)."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *[str(ROOT / f) for f in files]],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1500:]


# ====================================================================================== P: ban dosyasi (trader_core.ban_store)
def test_p_01_write_then_read_roundtrip_and_expiry_keeps_file(tmp_path):
    B = bs()
    path = B.ban_path(str(tmp_path), FAPI)
    assert B.write_ban(path, until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW) is True
    d = load_json(path)
    assert set(d) == {"v", "host", "until_ms", "http", "source", "written_ms"}, d
    assert d == {"v": 1, "host": HOST, "until_ms": NOW + 120_000, "http": 418, "source": "feed", "written_ms": NOW}
    rec = B.read_ban(path, NOW)
    assert rec is not None
    assert (rec.until_ms, rec.http, rec.source, rec.corrupt) == (NOW + 120_000, 418, "feed", False)
    assert rec.host == HOST and rec.written_ms == NOW
    assert B.read_ban(path, NOW + 121_000) is None
    assert Path(path).exists()


def test_p_02_shorter_than_10s_not_written_exactly_10s_written(tmp_path):
    B = bs()
    assert B.PERSIST_MIN_S == 10
    p9 = B.ban_path(str(tmp_path / "a"), FAPI)
    (tmp_path / "a").mkdir()
    assert B.write_ban(p9, until_ms=NOW + 9_000, http=418, source="feed", now_ms=NOW) is True
    assert not Path(p9).exists()
    p10 = B.ban_path(str(tmp_path), FAPI)
    assert B.write_ban(p10, until_ms=NOW + 10_000, http=418, source="feed", now_ms=NOW) is True
    assert Path(p10).exists()


def test_p_03_window_never_shortened_but_longer_overwrites(tmp_path):
    B = bs()
    path = B.ban_path(str(tmp_path), FAPI)
    assert B.write_ban(path, until_ms=NOW + 600_000, http=418, source="feed", now_ms=NOW)
    before = Path(path).read_bytes()
    assert B.write_ban(path, until_ms=NOW + 60_000, http=429, source="oi", now_ms=NOW) is True
    assert Path(path).read_bytes() == before, "kisa pencere mevcut uzun pencereyi kisaltti/degistirdi"
    assert B.write_ban(path, until_ms=NOW + 900_000, http=429, source="oi", now_ms=NOW) is True
    d = load_json(path)
    assert (d["until_ms"], d["http"], d["source"]) == (NOW + 900_000, 429, "oi")


@pytest.mark.parametrize("case", ["brace", "list", "until_str", "until_bool", "v2", "other_host", "future_written"])
def test_p_04_corrupt_content_holds_15_minutes_from_mtime(tmp_path, caplog, case):
    B = bs()
    assert B.CORRUPT_HOLD_S == 900
    path = tmp_path / f"ban.{HOST}.json"
    content = {
        "brace": "{", "list": "[]",
        "until_str": json.dumps(good_rec(until_ms="x")),
        "until_bool": json.dumps(good_rec(until_ms=True)),
        "v2": json.dumps(good_rec(v=2)),
        "other_host": json.dumps(good_rec(host="other.example.com")),
        "future_written": json.dumps(good_rec(written_ms=NOW + 300_000)),
    }[case]
    put_text(path, content, NOW)
    with caplog.at_level(logging.WARNING):
        rec = B.read_ban(str(path), NOW)
    assert rec is not None and rec.corrupt is True, case
    assert rec.http is None and rec.until_ms == NOW + 900_000 and rec.host == HOST
    assert any(r.levelno == logging.WARNING for r in caplog.records), "bozuk dosya icin WARNING yok"
    put_text(path, content, NOW - 901_000)                       # mtime = now - 901 s: yasak varsayimi bitti
    assert B.read_ban(str(path), NOW) is None
    assert path.read_text(encoding="utf-8") == content, "read_ban dosyayi degistirdi"


def test_p_05_window_capped_at_three_days_from_written(tmp_path):
    B = bs()
    assert B.MAX_HORIZON_S == 259_200
    path = put_json(tmp_path / f"ban.{HOST}.json", good_rec(until_ms=NOW + 10 * 86_400_000, written_ms=NOW))
    rec = B.read_ban(path, NOW)
    assert rec is not None and rec.until_ms == NOW + 259_200_000 and rec.corrupt is False


def test_p_06_unopenable_path_and_missing_dir_never_raise(tmp_path, caplog):
    B = bs()
    d = tmp_path / f"ban.{HOST}.json"
    d.mkdir()                                                    # yol bir dizin: acilamaz
    with caplog.at_level(logging.ERROR):
        assert B.read_ban(str(d), NOW) is None
    assert any(r.levelno >= logging.ERROR for r in caplog.records), "izin/acilamama icin ERROR yok"
    missing = str(tmp_path / "yok" / f"ban.{HOST}.json")
    assert B.write_ban(missing, until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW) is False
    assert not (tmp_path / "yok").exists(), "olmayan dizin olusturuldu"


def test_p_07_corrupt_existing_file_is_replaced_by_valid_record(tmp_path):
    B = bs()
    path = tmp_path / f"ban.{HOST}.json"
    put_text(path, "{", NOW)
    assert B.read_ban(str(path), NOW).corrupt is True
    assert B.write_ban(str(path), until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW) is True
    rec = B.read_ban(str(path), NOW)
    assert rec is not None and rec.corrupt is False and rec.until_ms == NOW + 120_000 and rec.http == 418
    assert load_json(path)["v"] == 1


def test_p_08_path_helpers():
    B = bs()
    assert B.ban_path("/x/var", "https://FAPI.binance.com") == f"/x/var/ban.{HOST}.json"
    assert B.ban_path("/x/var", "https://testnet.binancefuture.com") == f"/x/var/ban.{TESTNET_HOST}.json"
    d = B.ban_dir_for("var/market.sqlite")
    assert os.path.isabs(d) and d.endswith("var") and d == os.path.dirname(os.path.abspath("var/market.sqlite"))


def test_p_09_banguard_refresh_interval_and_own_note_visible_immediately(tmp_path):
    B = bs()
    assert B.REFRESH_MIN_S == 1.0
    path = B.ban_path(str(tmp_path), FAPI)
    t = [NOW]
    g1 = B.BanGuard(path, "engine:learner", lambda: t[0])
    g2 = B.BanGuard(path, "feed", lambda: t[0])
    assert g1.path == path and g1.active() is None
    assert g2.note(NOW + 120_000, 418) is True
    own = g2.active()
    assert own is not None and own.until_ms == NOW + 120_000 and own.http == 418, "note eden guard kaydi hemen gormeli"
    t[0] = NOW + 500
    assert g1.active() is None, "0,5 s icinde yeniden okunmamali (onbellek)"
    t[0] = NOW + 1_000
    rec = g1.active()
    assert rec is not None and rec.until_ms == NOW + 120_000 and rec.source == "feed"


def test_p_10_all_three_processes_resolve_the_same_ban_dir(monkeypatch):
    B = bs()
    from trader_engine.config import load_cli_config
    from trader_engine.marketdata.feed import feed_config_from_base
    monkeypatch.chdir(ROOT)
    cfgdir = ROOT / "config"
    oi = _oi_run()
    a = os.path.realpath(B.ban_dir_for(feed_config_from_base(str(cfgdir)).db_path))
    b = os.path.realpath(B.ban_dir_for(oi.load_pairs_and_db(cfgdir)[1]))
    c = os.path.realpath(B.ban_dir_for(load_cli_config(str(cfgdir), env="testnet").market_db))
    assert a == b == c, (a, b, c)
    assert a == os.path.realpath(ROOT / "var")


def test_p_11_module_is_stdlib_only(tmp_path):
    """`requests` ve `trader_engine` hic iceri alinamaz (zehirli sys.modules) ve tum API yine calisir."""
    script = f"""
import sys, os, tempfile
sys.modules['requests'] = None
sys.modules['trader_engine'] = None
import trader_core.ban_store as B
d = tempfile.mkdtemp()
p = B.ban_path(d, 'https://fapi.binance.com')
now = 1_800_000_000_000
t = [now]
assert B.write_ban(p, until_ms=now + 120_000, http=418, source='feed', now_ms=now) is True
assert B.read_ban(p, now).until_ms == now + 120_000
g = B.BanGuard(p, 'oi', lambda: t[0])
assert g.active() is not None and g.note(now + 300_000, 429) is True
bad = [m for m in sys.modules if m.split('.')[0] in ('requests', 'trader_engine') and sys.modules[m] is not None]
assert not bad, bad
print('OK')
"""
    r = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(ROOT / 'src')!r})\n" + script],
                       cwd=str(tmp_path), capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, r.stdout + r.stderr


# ====================================================================================== M: imzali istemci + motor acilisi
T0 = datetime(2026, 12, 28, 9, 0, tzinfo=UTC)


class REnv:
    """Gercek SignedRestClient + sahte borsa (HTTP duzeyi) + BanGuard (`ban_dir` icinde, host dosyasi)."""

    def __init__(self, tmp, *, env="testnet", ban_dir=None, source="engine:learner", guard=True, seed=None):
        B = bs()
        self.clock = SimClock(T0)
        self.now = lambda: ms_of(self.clock)
        self.ex = FakeExchange(self.now)
        self.dir = Path(ban_dir if ban_dir is not None else tmp)
        self.path = B.ban_path(str(self.dir), BASES[env])
        if seed is not None:
            seed(self)
        self.guard = B.BanGuard(self.path, source, self.now) if guard else None
        kw = {"ban_guard": self.guard} if guard else {}
        self.sleeps: list = []
        self.rest = SignedRestClient(env=env, api_key=KEY, api_secret=SECRET, session=self.ex.session, now_ms=self.now,
                                     sleep=self._sleep, **kw)

    def _sleep(self, s):
        self.sleeps.append(s)
        self.clock.sleep(s)

    def get(self, **kw):
        return self.rest.request("GET", "/fapi/v2/account", None, kind="read", **kw)


def test_m_01_ban_responses_are_persisted_with_source_and_window(tmp_path):
    cases = [("418", FakeResp(418, {"code": -1003, "msg": "banned"}, {"Retry-After": "120"}), 418, 120_000),
             ("429", FakeResp(429, {"code": -1003, "msg": "too many"}, {"Retry-After": "60"}), 429, 60_000),
             ("403", FakeResp(403, {"msg": "forbidden"}, {}), 403, 300_000)]
    for name, resp, http, win in cases:
        (tmp_path / name).mkdir()
        e = REnv(tmp_path / name)
        e.ex.inject("/fapi/v2/account", resp)
        t0 = e.now()
        with pytest.raises(ExchangeBan) as ei:
            e.get()
        assert ei.value.http == http, name
        d = load_json(e.path)
        assert d["until_ms"] == t0 + win and d["http"] == http and d["source"] == "engine:learner", (name, d)
        assert d["host"] == TESTNET_HOST


def test_m_02_short_429_retry_after_inline_wait_and_no_file(tmp_path):
    e = REnv(tmp_path)
    e.ex.inject("/fapi/v2/account", FakeResp(429, {"code": -1003, "msg": "x"}, {"Retry-After": "2"}))
    out = e.get()
    assert isinstance(out, dict) and "totalWalletBalance" in out
    assert e.sleeps == [2] and e.ex.count("/fapi/v2/account") == 2, "bugunku satir ici bekleme + yeniden deneme degisti"
    assert not Path(e.path).exists(), "kalan 2 sn < 10 sn: dosya yazilmamali"


def test_m_03_451_is_not_a_window_and_writes_no_file(tmp_path):
    e = REnv(tmp_path)
    e.ex.inject("/fapi/v2/account", FakeResp(451, {"msg": "region"}, {}))
    with pytest.raises(ExchangeBan) as ei:
        e.get()
    assert ei.value.http == 451
    assert not Path(e.path).exists()


def test_m_04_new_client_seeds_window_from_file_and_sends_nothing(tmp_path):
    B = bs()

    def seed(e):
        assert B.write_ban(e.path, until_ms=e.now() + 120_000, http=418, source="feed", now_ms=e.now())

    e = REnv(tmp_path, seed=seed)
    until = e.now() + 120_000
    assert e.rest.health()["ban_until_ms"] == until
    assert e.rest.counters["ban_file_seeded"] == 1
    calls = [
        lambda: e.rest.request("GET", "/fapi/v2/account", None, kind="read"),
        lambda: e.rest.request("GET", "/fapi/v2/account", None, kind="read", protective=True),
        lambda: e.rest.request("DELETE", "/fapi/v1/order", {"symbol": SYM, "origClientOrderId": "x"}, kind="cancel"),
        lambda: e.rest.request("POST", "/fapi/v1/leverage", {"symbol": SYM, "leverage": 3}, kind="setup"),
        lambda: e.rest.request("POST", "/fapi/v1/order", {"symbol": SYM, "side": "SELL", "type": "MARKET", "quantity": "1",
                                                          "reduceOnly": "true", "newClientOrderId": "c1"}, kind="order",
                               protective=True),
        lambda: e.rest.request("POST", "/fapi/v1/order", {"symbol": SYM, "side": "BUY", "type": "MARKET", "quantity": "1",
                                                          "newClientOrderId": "c2"}, kind="order"),
        lambda: e.rest.sync_time(),
    ]
    for i, c in enumerate(calls):
        with pytest.raises(ExchangeBan) as ei:
            c()
        assert ei.value.http == 418, i
    assert e.ex.requests == [], "yasak penceresinde sahte borsaya istek gitti"


def test_m_05_startup_exits_5_exchange_ban_persisted_zero_http_sleep_capped(tmp_path, monkeypatch, boots):
    B = bs()
    for rem_s, want_sleep, sub in ((120, 122, "a"), (1000, 300, "b")):
        b = boots(tmp_path / sub)
        now = ms_of(b.clock)
        path = B.ban_path(B.ban_dir_for(b.cfg.market_db), BASES["testnet"])
        assert B.write_ban(path, until_ms=now + rem_s * 1000, http=418, source="feed", now_ms=now)
        sleeps = spy_sleep(monkeypatch, b.clock)
        D8.boot_expect_exit(b, 5, "exchange_ban_persisted")
        assert b.ex.requests == [], f"{rem_s}: /fapi/v1/time dahil hicbir istek gitmemeli"
        assert [s for s, _ in sleeps] == [want_sleep], sleeps


@pytest.mark.parametrize("case", ["http403", "corrupt"])
def test_m_06_startup_exit_code_is_5_for_403_and_corrupt_records_too(tmp_path, monkeypatch, boots, case):
    B = bs()
    b = boots(tmp_path)
    now = ms_of(b.clock)
    path = B.ban_path(B.ban_dir_for(b.cfg.market_db), BASES["testnet"])
    if case == "http403":
        assert B.write_ban(path, until_ms=now + 120_000, http=403, source="feed", now_ms=now)
    else:
        put_text(path, "{", now)                                 # bozuk, taze: yasak varsayilir
    sleeps = spy_sleep(monkeypatch, b.clock)
    D8.boot_expect_exit(b, 5, "exchange_ban_persisted")
    assert b.ex.requests == []
    assert len(sleeps) == 1 and sleeps[0][0] > 0


def test_m_07_expired_record_boot_completes_and_file_is_kept(tmp_path, boots):
    B = bs()
    b = boots(tmp_path)
    now = ms_of(b.clock)
    path = B.ban_path(B.ban_dir_for(b.cfg.market_db), BASES["testnet"])
    put_json(path, good_rec(host=TESTNET_HOST, until_ms=now - 10_000, written_ms=now - 130_000))
    before = Path(path).read_bytes()
    b.boot()                                                    # EngineExit yok: acilis tamam
    assert b.ex.requests and b.ex.requests[0][:2] == ("GET", "/fapi/v1/time")
    assert Path(path).exists() and Path(path).read_bytes() == before, "suresi dolan kayit silindi/degisti"


def test_m_08_foreign_stamp_beats_future_ban_record_exit_8_zero_http(tmp_path, monkeypatch, boots):
    B = bs()
    b = boots(tmp_path)
    D8.seed_state(b.state_path, {"account_stamp": "live:baska-hesap"})
    now = ms_of(b.clock)
    path = B.ban_path(B.ban_dir_for(b.cfg.market_db), BASES["testnet"])
    assert B.write_ban(path, until_ms=now + 120_000, http=418, source="feed", now_ms=now)
    sleeps = spy_sleep(monkeypatch, b.clock)
    D8.boot_expect_exit(b, 8, "state_stamp_mismatch")
    assert b.ex.requests == [] and sleeps == [], "damga ban denetiminden ONCE gelmeli (uyku yok)"


@pytest.fixture
def boots(monkeypatch):
    made: list = []

    def mk(tmp, **kw):
        b = D8.Boot(tmp, monkeypatch, **kw)
        made.append(b)
        return b

    yield mk
    for b in made:
        b.close()


@pytest.fixture
def denv_factory():
    made: list = []

    def mk(tmp, **kw):
        e = D8.DEnv(tmp, **kw)
        made.append(e)
        return e

    yield mk
    for e in made:
        e.close()


def _guarded_denv(tmp, monkeypatch, denv_factory, **kw):
    """DEnv'in `SignedRestClient(...)` cagrisina motorun kurulum kablolamasini (host dosyasi, source engine:learner) ekler."""
    B = bs()
    orig = D8.SignedRestClient

    def factory(*a, **k):
        k["ban_guard"] = B.BanGuard(B.ban_path(str(tmp), BASES[k["env"]]), source="engine:learner", now_ms=k["now_ms"])
        return orig(*a, **k)

    monkeypatch.setattr(D8, "SignedRestClient", factory)
    return denv_factory(tmp, **kw)


@pytest.mark.parametrize("http", [418, 429])
def test_m_09_running_engine_adopts_other_process_ban_and_sends_nothing(tmp_path, monkeypatch, denv_factory, http):
    B = bs()
    tmp = tmp_path / str(http)
    e = _guarded_denv(tmp, monkeypatch, denv_factory, mode="testnet", wallet=100).boot()
    pos = e.enter()
    assert pos is not None and pos.status == "open", pos
    from trader_engine.status import StatusWriter, _ms_to_z
    e.engine.status = StatusWriter(e.cfg.status_path, e.clock, e.cfg)
    path = B.ban_path(str(tmp), BASES["testnet"])
    now = ms_of(e.clock)
    until = now + 120_000
    assert B.BanGuard(path, "feed", lambda: now).note(until, http) is True
    n0 = len(e.ex.requests)
    for _ in range(3):                                           # pencere (120 sn) icinde: 3 x 6 sn
        e.tick(6.0)
        assert e.clock.now().timestamp() * 1000 < until
        assert len(e.ex.requests) == n0, f"yasak penceresinde sahte borsaya istek gitti: {e.ex.requests[n0:][:3]}"
    reasons = [h.reason for h in e.pause.holds()]
    if http == 418:
        assert "exchange_ban" in reasons, reasons
    else:
        assert "exchange_ban" not in reasons, reasons
        assert e.state.block_has("exchange_rate_limited"), "429: giris engeli exchange_rate_limited olmali"
    assert e.broker.health()["ban_until_ms"] == until, "broker/istemci benimsenen pencereyi gostermiyor"
    # SPEC-AMBIGUOUS: HEAD'de ban sirasinda status_fields hesap okuyamayip status.json yazimi basarisiz olur ("status.json yazilamadi");
    # sartname yine de status.json.exchange.ban_until_ms'in benimsenen degeri gostermesini ister -> gerceklemenin bunu saglamasi beklenir.
    assert Path(e.cfg.status_path).exists(), "ban sirasinda status.json yazilamadi (status_fields hesap okuyamiyor)"
    st = load_json(e.cfg.status_path)["exchange"]
    # SPEC-AMBIGUOUS: sartname `status.json.exchange.ban_until_ms` der; HEAD status.json `ban_until` (ISO Z) yazar. Ikisi de kabul.
    assert st.get("ban_until_ms") == until or st.get("ban_until") == _ms_to_z(until), st


def test_m_10_unwritable_ban_dir_keeps_memory_window_and_counts_failure(tmp_path, caplog):
    nodir = tmp_path / "yok-dizin"                               # olusturulmaz -> write_ban False
    e = REnv(tmp_path, ban_dir=nodir)
    e.ex.inject("/fapi/v2/account", FakeResp(418, {"code": -1003, "msg": "banned"}, {"Retry-After": "120"}))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ExchangeBan) as ei:
            e.get()
    assert ei.value.http == 418
    assert e.rest.counters["ban_persist_failed"] == 1
    assert any(r.levelno >= logging.ERROR for r in caplog.records), "yazma hatasi icin ERROR yok"
    n = len(e.ex.requests)
    with pytest.raises(ExchangeBan):
        e.get()
    assert len(e.ex.requests) == n, "bellekteki pencere etkin degil: istek gitti"
    assert not nodir.exists()


def test_m_11_without_guard_existing_binance_rest_spec_passes_unchanged():
    run_pytest("tests/engine/test_binance_rest_spec.py")
    clock = SimClock(T0)
    ex = FakeExchange(lambda: ms_of(clock))
    r = SignedRestClient(env="testnet", api_key=KEY, api_secret=SECRET, session=ex.session, now_ms=lambda: ms_of(clock),
                         sleep=clock.sleep)
    ex.inject("/fapi/v2/account", FakeResp(418, {"code": -1003, "msg": "b"}, {"Retry-After": "120"}))
    with pytest.raises(ExchangeBan):
        r.request("GET", "/fapi/v2/account", None, kind="read")
    assert "ban_file_seeded" not in r.counters and "ban_persist_failed" not in r.counters


def test_m_12_paper_never_builds_guard_nor_touches_ban_dir(tmp_path, monkeypatch):
    B = bs()
    clock = SimClock(TL.BOOT)
    cfg, view = D8._paper_engine_pieces(tmp_path, clock)
    now = ms_of(clock)
    for base in (FAPI, "https://testnet.binancefuture.com"):    # dizinde gelecekte ban kayitlari olsa da
        assert B.write_ban(B.ban_path(str(tmp_path), base), until_ms=now + 3_600_000, http=418, source="feed", now_ms=now)
    ban_dir = Path(B.ban_dir_for(cfg.market_db))
    snap0 = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in ban_dir.glob("ban.*")}
    assert len(snap0) >= 2
    touched: list = []
    orig_read, orig_write, orig_init = B.read_ban, B.write_ban, B.BanGuard.__init__
    monkeypatch.setattr(B, "read_ban", lambda *a, **k: (touched.append("read_ban"), orig_read(*a, **k))[1])
    monkeypatch.setattr(B, "write_ban", lambda *a, **k: (touched.append("write_ban"), orig_write(*a, **k))[1])
    monkeypatch.setattr(B.BanGuard, "__init__", lambda self, *a, **k: (touched.append("BanGuard"), orig_init(self, *a, **k))[1])
    from trader_engine import engine as E
    eng = E.build_engine(cfg, clock=clock, view=view, env={})
    try:
        eng.start()
    finally:
        eng.state.close()
        eng.ledger.close()
    assert touched == [], f"paper kipi ban_store'a dokundu: {touched}"
    snap1 = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in ban_dir.glob("ban.*")}
    assert snap1 == snap0, "paper kipi ban dizininde dosya olusturdu/degistirdi (kilit dosyasi dahil)"
    D8._golden_when_enabled()                                    # altin geri test bit-ozdesligi: WP3_GOLDEN=1 ile (~8-15 dk)


# ====================================================================================== F: feed
class FEnv:
    """Feed + sahte Binance oturumu + BanGuard(source="feed"); db/ban dizini `tmp`."""

    def __init__(self, tmp, start=T_START, *, guard=True, pairs=(BTC,), max_attempts=2):
        B = bs()
        self.clock = SimClock(start)
        from test_engine_01_spec import FakeBinance
        self.srv = FakeBinance(self.clock)
        self.now = lambda: to_ms(self.clock.now())
        self.path = B.ban_path(str(tmp), FAPI)
        self.guard = B.BanGuard(self.path, "feed", self.now) if guard else None
        kw = {"ban_guard": self.guard} if guard else {}
        self.rest = PublicRestClient(session=self.srv, now_s=lambda: self.clock.now().timestamp(), sleep=self.clock.sleep,
                                     max_attempts=max_attempts, **kw)
        self.db = str(Path(tmp) / "market.sqlite")
        self.store = MarketStore(self.db)
        self.cfg = FeedConfig(pairs=tuple(pairs), db_path=self.db, lock_path=str(Path(tmp) / "market.lock"),
                              status_path=str(Path(tmp) / "status.json"), backfill_bars={"1m": 120, "15m": 8, "1h": 6, "4h": 4})
        self.feed = Feed(self.cfg, self.rest, self.store, self.clock)

    def other_note(self, until_ms, http, source="engine:learner"):
        B = bs()
        return B.BanGuard(self.path, source, self.now).note(until_ms, http)


def test_f_01_start_sleeps_before_first_request_when_ban_file_present(tmp_path, monkeypatch):
    B = bs()
    e = FEnv(tmp_path)
    now = e.now()
    assert B.write_ban(e.path, until_ms=now + 120_000, http=418, source="engine:learner", now_ms=now)
    sleeps = spy_sleep(monkeypatch, e.clock, hook=lambda: len(e.srv.calls))
    e.feed.start()
    assert sleeps and sleeps[0] == (125, 0), f"ilk uyku 125 sn ve istekten once olmali: {sleeps[:2]}"
    assert e.feed._started and e.srv.calls, "uyku sonrasi olagan acilis tamamlanmadi"
    assert e.feed.stats()["bans"] == 1
    assert F.BAN_MARGIN_S == 5 and F.BAN_MAX_WAIT_S == 3600


def test_f_02_start_exits_3_without_sleep_when_remaining_over_cap_and_main_returns_3(tmp_path, monkeypatch):
    B = bs()
    e = FEnv(tmp_path)
    now = e.now()
    assert B.write_ban(e.path, until_ms=now + 3_601_000, http=418, source="engine:learner", now_ms=now)
    sleeps = spy_sleep(monkeypatch, e.clock)
    with pytest.raises(SystemExit) as ei:
        e.feed.start()
    assert ei.value.code == 3 == F.EXIT_BAN
    assert e.srv.calls == [] and sleeps == []
    # main(...) donusu 3
    from test_feed_entrypoints import T0 as FT0, _cfg_dir, _Session
    (tmp_path / "m").mkdir()
    d = _cfg_dir(tmp_path / "m")
    var = tmp_path / "m" / "var"
    var.mkdir(parents=True)
    clock = SimClock(FT0)
    nowm = lambda: to_ms(clock.now())  # noqa: E731
    path = B.ban_path(str(var), FAPI)
    assert B.write_ban(path, until_ms=nowm() + 3_601_000, http=418, source="engine:learner", now_ms=nowm())
    sess = _Session(to_ms(FT0))
    rest = PublicRestClient(session=sess, now_s=lambda: clock.now().timestamp(), sleep=clock.sleep, max_attempts=2,
                            ban_guard=B.BanGuard(path, "feed", nowm))
    rc = F.main(["--config-dir", str(d)], rest=rest, clock=clock, max_ticks=1)
    assert rc == 3 and sess.paths == []


def test_f_03_running_418_and_429_are_persisted_with_feed_source(tmp_path):
    (tmp_path / "a").mkdir()
    e = FEnv(tmp_path / "a")
    e.feed.start()
    seen: list = []

    def inj418(path, p):
        if "klines" in path.lower():
            seen.append(e.now())
            return Resp(418, {}, {"Retry-After": "300"})
        return None

    e.srv.inject.append(inj418)
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e.feed.run_once()
    d = load_json(e.path)
    assert d["http"] == 418 and d["source"] == "feed" and d["until_ms"] == seen[0] + 300_000, (d, seen[:1])
    # 429 + Retry-After 30 (ayri dizin/ortam)
    (tmp_path / "b").mkdir()
    e2 = FEnv(tmp_path / "b")
    e2.feed.start()
    seen2: list = []
    fired = [False]

    def inj429(path, p):
        if "klines" in path.lower() and not fired[0]:
            fired[0] = True
            seen2.append(e2.now())
            return Resp(429, {}, {"Retry-After": "30"})
        return None

    e2.srv.inject.append(inj429)
    e2.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    e2.feed.run_once()
    d2 = load_json(e2.path)
    assert d2["http"] == 429 and d2["source"] == "feed" and d2["until_ms"] == seen2[0] + 30_000, (d2, seen2[:1])


def test_f_04_running_feed_adopts_other_source_window_sends_nothing_and_sleeps(tmp_path):
    e = FEnv(tmp_path)
    e.feed.start()
    e.clock.set_time(dt(2026, 12, 1, 9, 0, 3))
    assert e.other_note(e.now() + 60_000, 429) is True
    e.clock.advance(1.0)
    n0 = len(e.srv.calls)
    t0 = e.clock.now()
    tick = e.feed.run_once()
    assert len(e.srv.calls) == n0, "baska surecin yasagi sirasinda feed HTTP istegi atti"
    assert tick.banned is True
    assert (e.clock.now() - t0).total_seconds() >= 59, "uyku kalan sureden kisa"


def test_f_05_corrupt_fresh_file_reads_as_418_zero_requests(tmp_path):
    e = FEnv(tmp_path)
    put_text(e.path, "{", e.now())
    with pytest.raises(ExchangeBan) as ei:
        e.rest.get("/fapi/v1/time")
    assert ei.value.http == 418
    assert e.srv.calls == []


def test_f_06_without_guard_existing_feed_tests_pass_unchanged(tmp_path):
    run_pytest("tests/engine/test_engine_rest_public_spec.py", "tests/engine/test_dd1_feed_impl.py")
    e = FEnv(tmp_path, guard=False)
    assert getattr(e.rest, "ban_guard", None) is None
    e.feed.start()
    assert e.feed._started


# ====================================================================================== T: OI toplayici
NOW_OI = (C.HOLDOUT_END_MS + 7 * 86_400_000) // C.PERIOD_MS * C.PERIOD_MS


def _oi_run():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        return importlib.import_module("oi_collect")
    finally:
        sys.path.pop(0)


class _HResp(io.BytesIO):
    """urlopen yaniti: baglam yoneticisi + baslik (HTTPMessage; getheader/info destekli)."""

    def __init__(self, body: bytes, headers: dict | None = None):
        super().__init__(body)
        m = http.client.HTTPMessage()
        for k, v in (headers or {}).items():
            m[k] = v
        self.headers = m
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def info(self):
        return self.headers


def _http_err(code, ra=None):
    h = http.client.HTTPMessage()
    if ra is not None:
        h["Retry-After"] = str(ra)
    return urllib.error.HTTPError("u", code, "m", h, io.BytesIO(b"{}"))


def patch_urlopen(monkeypatch, seq, clock_box=None):
    """`urlopen` sirasi: her cagri bir ogeyi tuketir (istisna -> firlatir). Cagri sayaci ve cagri anindaki sahte saat doner."""
    log: list = []

    def fake(req, timeout=None):
        log.append(clock_box[0] if clock_box else None)
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return log


def oi_client(tmp, source="oi", t=None, **kw):
    B = bs()
    t = t if t is not None else [NOW]
    path = B.ban_path(str(tmp), C.BASE_URL)
    g = B.BanGuard(path, source, lambda: t[0])
    cl = C.HttpClient(ban_guard=g, now_ms=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + int(s * 1000)),
                      min_interval_s=0, **kw)
    return cl, g, path, t


def _fake_server(calls=None, *, stop_after=None, weight=None):
    class Fake:
        requests_made = 0
        last_used_weight = None

        def get_json(self, path, params):
            self.requests_made += 1
            if calls is not None:
                calls.append((path, dict(params)))
            if stop_after is not None and self.requests_made >= stop_after:
                self.last_used_weight = weight
            lo = -(-params["startTime"] // C.PERIOD_MS) * C.PERIOD_MS
            out, t = [], lo
            while t <= params["endTime"] and len(out) < params["limit"]:
                out.append({"timestamp": t, "sumOpenInterest": "1", "sumOpenInterestValue": "2", "longShortRatio": "1",
                            "longAccount": "0.5", "shortAccount": "0.5", "buySellRatio": "1", "buyVol": "1", "sellVol": "1"})
                t += C.PERIOD_MS
            return out
    return Fake()


def test_t_01_main_skips_all_http_and_returns_ok_when_ban_file_active(tmp_path, caplog):
    B = bs()
    RUN = _oi_run()
    now = int(time.time() * 1000)                               # SPEC-AMBIGUOUS: enjekte now_ms ile gercek saat ayni kayitta uyumlu olsun
    db = tmp_path / "v" / "market.sqlite"
    db.parent.mkdir()
    path = B.ban_path(str(db.parent), C.BASE_URL)
    assert B.write_ban(path, until_ms=now + 120_000, http=418, source="feed", now_ms=now)
    fake = _fake_server()
    calls: list = []
    fake.get_json = lambda *a, **k: calls.append(a)             # cagrilirsa kayit
    with caplog.at_level(logging.WARNING):
        rc = RUN.main(["--db", str(db), "--pairs", "BTC/USDT"], client=fake, now_ms=now)
    assert rc == 0 == RUN.EXIT_OK and calls == []
    assert any("event=ban_skip" in r.getMessage() and HOST in r.getMessage() for r in caplog.records), "ban_skip uyarisi yok"
    # --ban-dir ile gecersiz kilma: ban baska dizinde
    other = tmp_path / "other"
    other.mkdir()
    assert B.write_ban(B.ban_path(str(other), C.BASE_URL), until_ms=now + 120_000, http=418, source="feed", now_ms=now)
    db2 = tmp_path / "w" / "market.sqlite"
    rc = RUN.main(["--db", str(db2), "--ban-dir", str(other), "--pairs", "BTC/USDT"], client=fake, now_ms=now)
    assert rc == 0 and calls == []


def test_t_02_httpclient_with_active_record_raises_ban_error_without_urlopen(tmp_path, monkeypatch):
    B = bs()
    cl, g, path, t = oi_client(tmp_path)
    assert B.write_ban(path, until_ms=NOW + 120_000, http=418, source="feed", now_ms=NOW)
    log = patch_urlopen(monkeypatch, [])
    with pytest.raises(C.BanError):
        cl.get_json("/futures/data/openInterestHist", {"symbol": "BTCUSDT"})
    assert log == [] and cl.requests_made == 0


def test_t_03_418_is_persisted_default_120s_and_main_returns_exit_ban(tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    cl, g, path, t = oi_client(tmp_path / "a")
    patch_urlopen(monkeypatch, [_http_err(418, 300)])
    with pytest.raises(C.BanError):
        cl.get_json("/p", {})
    d = load_json(path)
    assert d["http"] == 418 and d["until_ms"] == NOW + 300_000 and d["source"] == "oi", d
    (tmp_path / "b").mkdir()
    cl2, g2, path2, t2 = oi_client(tmp_path / "b")
    patch_urlopen(monkeypatch, [_http_err(418)])
    with pytest.raises(C.BanError):
        cl2.get_json("/p", {})
    assert load_json(path2)["until_ms"] == NOW + 120_000, "Retry-After yoksa 120 sn"
    # main: koşu icinde alinan yasak -> EXIT_BAN, dosyada source "oi"
    RUN = _oi_run()
    patch_urlopen(monkeypatch, [_http_err(418, 300)] * 8)
    db = tmp_path / "c" / "market.sqlite"
    rc = RUN.main(["--db", str(db), "--pairs", "BTC/USDT"], now_ms=NOW_OI)
    assert rc == RUN.EXIT_BAN == 3
    d3 = load_json(bs().ban_path(str(db.parent), C.BASE_URL))
    assert d3["source"] == "oi" and d3["http"] == 418
    assert abs((d3["until_ms"] - d3["written_ms"]) - 300_000) <= 2_000, d3   # SPEC-AMBIGUOUS: now_ms enjekte/gercek saat karisimi


def test_t_04_429_is_persisted_and_existing_retry_logic_continues(tmp_path, monkeypatch):
    cl, g, path, t = oi_client(tmp_path)
    box = t
    log = patch_urlopen(monkeypatch, [_http_err(429, 30), _HResp(b"[]")], clock_box=box)
    assert cl.get_json("/p", {}) == []                           # mevcut mantik: 30 sn bekle (sahte saat ilerler), yeniden dene
    d = load_json(path)
    assert d["http"] == 429 and d["until_ms"] == log[0] + 30_000 and d["source"] == "oi", (d, log)
    assert len(log) == 2


def test_t_05_used_weight_header_is_tracked_and_missing_header_keeps_value(tmp_path, monkeypatch):
    cl, g, path, t = oi_client(tmp_path)
    assert cl.last_used_weight is None
    patch_urlopen(monkeypatch, [_HResp(b'[{"a":1}]', {"X-MBX-USED-WEIGHT-1M": "1234"}), _HResp(b"[]", {}),
                                _HResp(b"[]", {"X-MBX-USED-WEIGHT-1M": "abc"})])
    cl.get_json("/p", {})
    assert cl.last_used_weight == 1234
    cl.get_json("/p", {})
    assert cl.last_used_weight == 1234, "basliksiz yanit degeri degistirdi"
    cl.get_json("/p", {})
    assert cl.last_used_weight == 1234, "bozuk baslik degeri degistirdi"


def test_t_06_weight_ceiling_stops_run_cleanly_and_1199_does_not(tmp_path, caplog):
    assert C.OI_WEIGHT_CEILING == 1200
    db = C.open_db(tmp_path / "m.sqlite")
    fake = _fake_server(stop_after=3, weight=1200)
    st = C.collect(db, fake, ["BTC/USDT", "ETH/USDT"], NOW_OI)
    assert fake.requests_made == 3 and st.requests == 3, st
    assert st.budget_hit is True and st.weight_stop is True and st.errors == 0
    assert st.rows == 0 and db.execute("SELECT COUNT(*) FROM positioning_5m").fetchone()[0] == 0, \
        "yarim kalan pencerenin satirlari yazildi"
    db.close()
    db2 = C.open_db(tmp_path / "m2.sqlite")
    ok = _fake_server(stop_after=3, weight=1199)
    st2 = C.collect(db2, ok, ["BTC/USDT"], NOW_OI)
    assert ok.requests_made > 3 and not st2.weight_stop and not st2.budget_hit and st2.errors == 0
    db2.close()
    # main: durdurma hata degildir (donus 0) ve kapanis gunlugu agirlik bilgisini tasir
    RUN = _oi_run()
    with caplog.at_level(logging.INFO):
        rc = RUN.main(["--db", str(tmp_path / "x" / "market.sqlite"), "--pairs", "BTC/USDT"],
                      client=_fake_server(stop_after=3, weight=1200), now_ms=NOW_OI)
    assert rc == 0
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "used_weight=1200" in msgs and "weight_stop=True" in msgs, msgs[-400:]


def test_t_07_client_without_last_used_weight_attribute_is_unaffected(tmp_path):
    class Bare:                                                  # last_used_weight / ban_guard ozniteligi YOK
        requests_made = 0

        def get_json(self, path, params):
            self.requests_made += 1
            lo = -(-params["startTime"] // C.PERIOD_MS) * C.PERIOD_MS
            return [{"timestamp": lo, "sumOpenInterest": "1", "sumOpenInterestValue": "2", "longShortRatio": "1",
                     "longAccount": "0.5", "shortAccount": "0.5", "buySellRatio": "1", "buyVol": "1", "sellVol": "1"}]
    db = C.open_db(tmp_path / "m.sqlite")
    st = C.collect(db, Bare(), ["BTC/USDT"], NOW_OI)
    assert st.weight_stop is False and st.requests > 3 and st.errors == 0
    db.close()
    run_pytest("tests/test_oi_collector.py")


def test_t_08_holdout_windows_and_requests_unchanged(tmp_path, monkeypatch):
    # 23.11.2026 kullanici karari: kilit ACIK; mekanizma bayrak kapatilarak (eski davranis) sinanir, acik davranis asagida
    assert C.KILIT_ACIK is True and C.clip_windows(1, 99) == [(1, 99)] and not C.in_holdout(C.HOLDOUT_START_MS)
    monkeypatch.setattr(C, "KILIT_ACIK", False)
    H0, H1 = C.HOLDOUT_START_MS, C.HOLDOUT_END_MS
    assert (H0, H1) == (1777593600000, 1793491200000) or H0 < H1
    P = C.PERIOD_MS
    assert C.clip_windows(H0 - 10 * P, H1 + 10 * P) == [(H0 - 10 * P, H0 - 1), (H1, H1 + 10 * P)]
    assert C.clip_windows(H0 + 1, H1 - 1) == []
    assert C.clip_windows(H1, H1 + 5) == [(H1, H1 + 5)]
    assert C.in_holdout(H0) and C.in_holdout(H1 - 1) and not C.in_holdout(H1) and not C.in_holdout(H0 - 1)
    db = C.open_db(tmp_path / "m.sqlite")
    calls: list = []
    C.collect(db, _fake_server(calls), ["ETH/USDT"], H1 + 3 * 86_400_000, endpoints=["oi"])
    assert calls
    for _, p in calls:
        assert not (p["startTime"] < H1 and p["endTime"] >= H0), p
    # ban guard'li HttpClient de kilitli doneme yeni istek eklemez (yalniz ban/agirlik kisitlamasi eklenir)
    db.close()


# ====================================================================================== G: agirlik esiginde giris reddi
def weight_hdr(ex, box):
    """Sahte borsanin her yanitinin `X-MBX-USED-WEIGHT-1M` basligini `box[0]` yapar (HTTP duzeyi; istek kaydi korunur)."""
    orig = ex.request

    def request(method, url, headers=None, timeout=None):
        r = orig(method, url, headers=headers, timeout=timeout)
        r.headers["X-MBX-USED-WEIGHT-1M"] = str(box[0])
        return r

    ex.request = request


def prime(b, box, w):
    """Borsa `w` agirlik basligi dondurmus gibi istemci durumunu kur (korumali saat esitleme istegi)."""
    box[0] = w
    b._rest.sync_time()
    assert b._rest.health()["used_weight"] == w


def _prepared(env):
    b, ex, clock = lb_build(env=env)
    box = [10]
    weight_hdr(ex, box)
    b.prepare(XRP, 3)
    return b, ex, clock, box


def test_g_01_entry_rejected_weight_high_with_zero_requests(tmp_path):
    b, ex, clock, box = _prepared("live")
    prime(b, box, 1200)
    n0 = len(ex.requests)
    r = b.market_order(lb_req("entry", 10.0))
    assert r.status == "rejected" and r.reason == "weight_high", r
    assert len(ex.requests) == n0, f"hicbir istek gitmemeli: {ex.requests[n0:]}"
    c = b.counters()
    assert c["entry_weight_rejects"] == 1 and c.get("account_mode_unverified", 0) == 0
    assert tuple(b.entries_blocked_reasons) == ()


def test_g_02_below_threshold_entry_is_normal(tmp_path):
    b, ex, clock, box = _prepared("live")
    prime(b, box, 1199)
    pr0, post0 = ex.count("/fapi/v2/positionRisk", "GET"), ex.count("/fapi/v1/order", "POST")
    r = b.market_order(lb_req("entry", 10.0))
    assert r.status == "filled", r
    assert ex.count("/fapi/v2/positionRisk", "GET") == pr0 + 1, "DD-8 D2 okumasi yapilmadi"
    assert ex.count("/fapi/v1/order", "POST") == post0 + 1
    assert b.counters().get("entry_weight_rejects", 0) == 0


def test_g_03_exit_and_stop_still_sent_at_1200(tmp_path):
    b, ex, clock, box = _prepared("live")
    assert b.market_order(lb_req("entry", 10.0)).status == "filled"
    prime(b, box, 1200)
    stops0, orders0 = ex.count("/fapi/v1/algoOrder", "POST"), ex.count("/fapi/v1/order", "POST")
    s = b.place_stop(lb_req("stop", 10.0, 1.9))
    assert s.status == "accepted", s
    x = b.market_order(lb_req("exit", 10.0))
    assert x.status != "rejected", x
    assert ex.count("/fapi/v1/algoOrder", "POST") == stops0 + 1
    assert ex.count("/fapi/v1/order", "POST") == orders0 + 1, "reduceOnly piyasa cikisi gonderilmedi"
    assert b.counters().get("entry_weight_rejects", 0) == 0


def test_g_04_testnet_skips_the_weight_check(tmp_path):
    b, ex, clock, box = _prepared("testnet")
    prime_w = 1500
    box[0] = prime_w
    b._rest.sync_time()
    post0 = ex.count("/fapi/v1/order", "POST")
    r = b.market_order(lb_req("entry", 10.0))
    assert r.status == "filled", r
    assert ex.count("/fapi/v1/order", "POST") == post0 + 1
    assert b.counters().get("entry_weight_rejects", 0) == 0


def test_g_05_stale_weight_header_older_than_60s_entry_is_normal(tmp_path):
    b, ex, clock, box = _prepared("live")
    prime(b, box, 1200)
    clock.advance(61)
    assert b._rest.health()["used_weight"] == 0, "60 sn'den eski olcum 0 sayilmali"
    r = b.market_order(lb_req("entry", 10.0))
    assert r.status == "filled", r
    assert b.counters().get("entry_weight_rejects", 0) == 0


def test_g_06_engine_level_signal_gives_rejected_order_row_weight_high(tmp_path, denv_factory):
    e = denv_factory(tmp_path, mode="live", wallet=100).boot()
    # Karar anina normal agirlikla gel (kademe/okuma yoklamalari bu anda yapilsin); agirlik ancak SONRA 1200 olur.
    # SPEC-AMBIGUOUS: agirlik >= 1200 iken istemci istemci duzeyinde okumalari reddeder; kademe sermaye yoklamasi o anda
    # gerekirse karar `capital_unverified` ile atlanir (G-6'nin "giris emri satiri" onkosulu: yoklamalar onceden taze olmali).
    e.clock.set_time(TL.DEC + timedelta(seconds=5))
    e.engine.live_tick(e.clock.now())
    box = [10]
    weight_hdr(e.ex, box)
    prime(e.broker, box, 1200)
    post0 = e.ex.count("/fapi/v1/order", "POST")
    e.signal()
    e.decide()
    con = sqlite3.connect(f"file:{e.cfg.state_path}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT status, detail FROM orders WHERE role='entry'").fetchall()
    finally:
        con.close()
    assert rows == [("rejected", "weight_high")], rows
    assert e.pos() is None
    assert e.entry_posts() == [] and e.ex.count("/fapi/v1/order", "POST") == post0, "giris POST'u gitti"
    assert list(e.pause.holds()) == [], "duraklatma tutusu eklenmemeli"


# ====================================================================================== S: saglik alarmi
NOWH = datetime(2026, 11, 16, 12, 30, 0, tzinfo=UTC)
GIB, MIB = 1 << 30, 1 << 20
BOTS = ("learner", "twin")


def _hat(hh, mm=0, ss=0):
    return datetime(2026, 11, 16, hh, mm, ss, tzinfo=UTC)


def good_api(**kw):
    base = dict(ping_ok=True, last_process_at=NOWH - timedelta(seconds=30), last_candle_open=_hat(12, 0, 0), open_trade_ids=(),
                dry_run=True)
    base.update(kw)
    return H.ApiProbe(**base)


def good_ledger():
    return H.LedgerProbe(last_write_at=_hat(12, 0, 2), spool_lines=0, unledgered_ids=(), orphan_ids=(), schema_ok=True,
                         has_active_params=True, spool_corrupt_lines=0)


def good_container():
    return H.ContainerProbe(state="running", restart_count=4, started_at=NOWH - timedelta(days=2), oom_killed=False)


def hsnap(**over):
    base = dict(now=NOWH, timeframe_s=3600, api={b: good_api() for b in BOTS}, ledger={b: good_ledger() for b in BOTS},
                disk_free_bytes=20 * GIB, disk_total_bytes=100 * GIB, mem_available_bytes=900 * MIB,
                swap_total_bytes=2048 * MIB, swap_used_bytes=int(0.10 * 2048 * MIB),
                containers={f"trader-{b}": good_container() for b in BOTS}, prev_restart_counts={f"trader-{b}": 4 for b in BOTS},
                veto_file_mtime=None, budget_state=None, last_backup_at=_hat(3, 10))
    base.update(over)
    return H.HealthSnapshot(**base)


def live_api(**kw):
    """Borsa blogu olan (has_exchange=True) yoklama; diger canli denetimleri sessiz tutar."""
    return good_api(has_exchange=True, exchange_reachable=True, exchange_last_sync=NOWH, naked=(), **kw)


def ban(until_delta_s=120, host=HOST, http=418, source="feed", corrupt=False):
    until = None if corrupt else NOWH + timedelta(seconds=until_delta_s)
    return H.BanProbe(host, until, None if corrupt else http, None if corrupt else source, corrupt)


def ban_result(snap):
    rep = H.evaluate(snap)
    rs = [r for r in rep.results if r.name == "exchange_ban"]
    return rep, (rs[0] if rs else None)


def test_s_01_active_ban_with_open_position_is_crit_open_positions(tmp_path):
    snap = hsnap(bans=(ban(),), api={"learner": live_api(open_trade_ids=(7,)), "twin": good_api()})
    rep, r = ban_result(snap)
    assert r is not None and r.status is H.Status.CRIT and r.code == "exchange_ban_open_positions", r
    assert rep.overall is H.Status.CRIT
    assert r.value == pytest.approx(120, abs=1)                  # SPEC-AMBIGUOUS: "deger = kalan sn (en uzun)"


def test_s_02_open_position_unknown_counts_as_open_and_no_exchange_probe_is_warn():
    _, r = ban_result(hsnap(bans=(ban(),), api={"learner": live_api(open_trade_ids=()), "twin": good_api()}))
    assert (r.status, r.code) == (H.Status.WARN, "exchange_ban")
    _, r = ban_result(hsnap(bans=(ban(),), api={"learner": live_api(open_trade_ids=None), "twin": good_api()}))
    assert (r.status, r.code) == (H.Status.CRIT, "exchange_ban_open_positions"), "bilinmiyor = var say"
    # has_exchange=True yoklama hic yok (kagit botlar acik islem tasisa da): WARN
    _, r = ban_result(hsnap(bans=(ban(),), api={b: good_api(open_trade_ids=(7,)) for b in BOTS}))
    assert (r.status, r.code) == (H.Status.WARN, "exchange_ban")


def test_s_03_expired_empty_and_unprobed_bans():
    api = {"learner": live_api(open_trade_ids=(7,)), "twin": good_api()}
    _, r = ban_result(hsnap(bans=(ban(until_delta_s=-1),), api=api))
    assert r is not None and r.status is H.Status.OK
    _, r = ban_result(hsnap(bans=(), api=api))
    assert r is not None and r.status is H.Status.OK
    rep, r = ban_result(hsnap(bans=None, api=api))
    assert r is None and all(not x.name.startswith("exchange_ban") for x in rep.results), "bans=None: denetim uretilmemeli"


def test_s_04_corrupt_only_is_warn_file_corrupt_and_active_record_wins():
    api = {"learner": live_api(open_trade_ids=()), "twin": good_api()}
    _, r = ban_result(hsnap(bans=(ban(corrupt=True),), api=api))
    assert (r.status, r.code) == (H.Status.WARN, "exchange_ban_file_corrupt")
    _, r = ban_result(hsnap(bans=(ban(corrupt=True), ban()), api=api))
    assert (r.status, r.code) == (H.Status.WARN, "exchange_ban"), "etkin kayit kodu oncelikli olmali"
    api_pos = {"learner": live_api(open_trade_ids=(7,)), "twin": good_api()}
    _, r = ban_result(hsnap(bans=(ban(corrupt=True), ban()), api=api_pos))
    assert (r.status, r.code) == (H.Status.CRIT, "exchange_ban_open_positions")


def test_s_05_plan_alerts_first_run_alerts_and_recovery_after_expiry():
    api_pos = {"learner": live_api(open_trade_ids=(7,)), "twin": good_api()}
    api_none = {"learner": live_api(open_trade_ids=()), "twin": good_api()}
    for api, code, level in ((api_pos, "exchange_ban_open_positions", H.Status.CRIT), (api_none, "exchange_ban", H.Status.WARN)):
        _, r = ban_result(hsnap(bans=(ban(),), api=api))
        assert r.code == code
        rep = H.HealthReport(NOWH, (r,), r.status, False)
        alerts, st = H.plan_alerts(rep, None, NOWH)
        assert len(alerts) == 1 and alerts[0].code == code and alerts[0].level is level, (code, alerts)
        # kayit suresi doldu: sonraki kosuda duzelme iletisi
        later = NOWH + timedelta(minutes=5)
        _, ok = ban_result(hsnap(now=later, bans=(ban(until_delta_s=-400),), api=api))
        assert ok.status is H.Status.OK
        rep2 = H.HealthReport(later, (ok,), H.Status.OK, True)
        a2, _ = H.plan_alerts(rep2, st, later)
        assert len(a2) == 1 and a2[0].level is H.Status.OK, (code, a2)
        assert "Borsa engeli kalktı" in a2[0].title, a2[0].title


def test_s_06_crit_text_mentions_manual_close_host_and_texts_exist_for_all_codes():
    api_pos = {"learner": live_api(open_trade_ids=(7,)), "twin": good_api()}
    _, r = ban_result(hsnap(bans=(ban(until_delta_s=600),), api=api_pos))
    alerts, _ = H.plan_alerts(H.HealthReport(NOWH, (r,), r.status, False), None, NOWH)
    a = alerts[0]
    assert "Borsa geçici engel koydu, açık pozisyon var" in a.title, a.title
    assert "elle kapatın" in a.body, a.body
    assert "Bot engel bitene kadar emir gönderemez. Borsadaki zarar-kes emirleri yerinde durur. Gerekirse pozisyonu Binance " \
           "uygulamasından elle kapatın." in a.body, a.body
    assert HOST in a.title + a.body, "host adi iletide yok"          # SPEC-AMBIGUOUS: host/kalan dk "gövde"de aranir
    assert "10" in a.body, "kalan dakika (10) iletide yok"
    for code in ("exchange_ban_open_positions", "exchange_ban", "exchange_ban_file_corrupt"):
        assert H._health_tr("exchange_ban", code) != H._HEALTH_TR_GENERIC, code
    assert "Borsa engeli kalktı" in H._health_tr("exchange_ban", "exchange_ban")[1]


def _hrun():
    import importlib.util
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("health_run", ROOT / "scripts" / "health_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_s_07_probe_bans_reads_files_marks_corrupt_ignores_lock_and_tmp(tmp_path):
    R = _hrun()
    now = int(time.time() * 1000)
    d = tmp_path / "var"
    d.mkdir()
    until = now + 120_000
    put_json(d / f"ban.{HOST}.json", good_rec(until_ms=until, written_ms=now))
    put_text(d / "ban.bozuk.example.com.json", "{")
    put_text(d / f"ban.{HOST}.json.lock", "")
    put_text(d / f"ban.{HOST}.json.tmp", "{}")
    put_text(d / f".ban.{HOST}.json.abc123", "{}")
    rows = R.probe_bans(str(d))
    assert isinstance(rows, tuple) and len(rows) == 2, rows
    by = {r.host: r for r in rows}
    ok, bad = by[HOST], by["bozuk.example.com"]
    assert ok.corrupt is False and ok.http == 418 and ok.source == "feed"
    assert ok.until == datetime.fromtimestamp(until / 1000, tz=UTC)
    assert bad.corrupt is True and bad.until is None
    assert R.probe_bans(str(tmp_path / "yok")) == ()


def test_s_08_existing_healthsnapshot_constructors_unchanged():
    s = H.HealthSnapshot(NOWH)
    assert s.bans is None
    s2 = H.HealthSnapshot(NOWH, 3600, {"learner": good_api()}, {"learner": good_ledger()})   # konumsal kurucu
    assert s2.timeframe_s == 3600 and s2.bans is None
    f = dataclasses.fields(H.HealthSnapshot)
    names = [x.name for x in f]
    b = f[names.index("bans")]
    assert b.default is None, "bans varsayilan None"
    assert names[names.index("bans") + 1:] == ["prev_account_mode", "live_path_issues", "haber_sinyal"], "DD-9: yalniz bu alanlar bans'tan sonra eklenir (23.11: haber_sinyal)"
    rep = H.evaluate(hsnap())
    assert all(r.name != "exchange_ban" for r in rep.results)
    bp = H.BanProbe("h", None, None, None)
    assert bp.corrupt is False
