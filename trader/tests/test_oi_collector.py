"""ML-G7 OI/long-short toplayici: AGSIZ (urlopen her yerde patlatilir; testler kendi sahte urlopen'ini koyar)."""
from __future__ import annotations

import importlib
import io
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from trader_engine.marketdata import oi_collector as C

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
sys.path.insert(0, str(ROOT / "scripts"))
RUN = importlib.import_module("oi_collect")
sys.path.pop(0)

NOW = 1_794_000_000_000 // C.PERIOD_MS * C.PERIOD_MS          # 2026-11-06 civari (kilitli donemin SONRASI)
assert NOW > C.HOLDOUT_END_MS


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("ag erisimi")
    monkeypatch.setattr(urllib.request, "urlopen", boom)


FIX = {
    "oi": [{"symbol": "BTCUSDT", "sumOpenInterest": "20403.63", "sumOpenInterestValue": "150570784.07", "timestamp": NOW}],
    "gls": [{"symbol": "BTCUSDT", "longShortRatio": "1.8105", "longAccount": "0.6442", "shortAccount": "0.3558", "timestamp": NOW}],
    "tpa": [{"symbol": "BTCUSDT", "longShortRatio": "1.4", "longAccount": "0.5833", "shortAccount": "0.4167", "timestamp": NOW}],
    "tpp": [{"symbol": "BTCUSDT", "longShortRatio": "0.9", "longAccount": "0.4737", "shortAccount": "0.5263", "timestamp": NOW}],
    "taker": [{"buySellRatio": "1.5586", "buyVol": "387.3300", "sellVol": "248.5200", "timestamp": NOW}],
}


@pytest.mark.parametrize("ep", list(FIX))
def test_parse_each_endpoint(ep):
    rows = C.parse_rows(ep, FIX[ep])
    assert len(rows) == 1 and rows[0]["ts"] == NOW
    cols = list(C.ENDPOINTS[ep][1])
    assert all(isinstance(rows[0][c], float) for c in cols)
    assert rows[0][cols[0]] == pytest.approx(float(FIX[ep][0][C.ENDPOINTS[ep][1][cols[0]]]))


def test_parse_skips_bad_rows_and_rejects_non_list():
    rows = C.parse_rows("oi", [{"timestamp": "x"}, {"timestamp": NOW}, {"timestamp": NOW, "sumOpenInterest": "nan"},
                               {"timestamp": NOW, "sumOpenInterest": "5"}])
    assert [r["oi"] for r in rows] == [5.0]
    with pytest.raises(C.CollectorError):
        C.parse_rows("oi", {"code": -1121})


def _db(tmp_path):
    return C.open_db(tmp_path / "m.sqlite")


def test_upsert_idempotent_and_merges_endpoints(tmp_path):
    db = _db(tmp_path)
    C.upsert(db, "BTC/USDT", C.parse_rows("oi", FIX["oi"]), 111)
    C.upsert(db, "BTC/USDT", C.parse_rows("gls", FIX["gls"]), 222)
    C.upsert(db, "BTC/USDT", C.parse_rows("gls", FIX["gls"]), 333)
    C.upsert(db, "BTC/USDT", C.parse_rows("oi", FIX["oi"]), 333)
    rows = db.execute("SELECT pair, ts, oi, gls_ratio, taker_ratio, fetched_at FROM positioning_5m").fetchall()
    assert rows == [("BTC/USDT", NOW, 20403.63, 1.8105, None, 333)]          # tek satir; None eski degeri ezmez
    assert C.last_ts(db, "BTC/USDT", "oi") == NOW and C.last_ts(db, "BTC/USDT", "taker") is None


# 23.11.2026 kullanici karari: kilit ACIK (C.KILIT_ACIK). Kilit mekanizmasi testleri bayragi kapatarak (fixture) eski davranisi sinar.
@pytest.fixture
def kilitli(monkeypatch):
    monkeypatch.setattr(C, "KILIT_ACIK", False)


def test_acik_kilitte_pencere_bolunmez_ve_satir_yazilir(tmp_path):
    H0, H1 = C.HOLDOUT_START_MS, C.HOLDOUT_END_MS
    assert C.KILIT_ACIK is True and not C.in_holdout(H0)
    assert C.clip_windows(H0 - 10 * C.PERIOD_MS, H1 + 10 * C.PERIOD_MS) == [(H0 - 10 * C.PERIOD_MS, H1 + 10 * C.PERIOD_MS)]
    assert C.clip_windows(H0 + 1, H1 - 1) == [(H0 + 1, H1 - 1)]
    db = _db(tmp_path)
    assert C.upsert(db, "BTC/USDT", [{"ts": H0 + C.PERIOD_MS, "oi": 1.0}, {"ts": H1, "oi": 2.0}], 1) == 2


@pytest.mark.usefixtures("kilitli")
def test_holdout_guard_windows_and_upsert(tmp_path):
    H0, H1 = C.HOLDOUT_START_MS, C.HOLDOUT_END_MS
    assert C.clip_windows(H0 - 10 * C.PERIOD_MS, H1 + 10 * C.PERIOD_MS) == [(H0 - 10 * C.PERIOD_MS, H0 - 1), (H1, H1 + 10 * C.PERIOD_MS)]
    assert C.clip_windows(H0 + 1, H1 - 1) == []
    assert C.clip_windows(H1, H1 + 5) == [(H1, H1 + 5)]
    db = _db(tmp_path)
    inside = {"ts": H0 + C.PERIOD_MS, "oi": 1.0}
    edge = {"ts": H1, "oi": 2.0}
    assert C.upsert(db, "BTC/USDT", [inside, {"ts": H1 - 1, "oi": 3.0}, edge], 1) == 1
    assert [r[0] for r in db.execute("SELECT ts FROM positioning_5m")] == [H1]


def _fake_server(calls, rows_by_ts=None):
    """Sahte client: istenen [startTime,endTime] icindeki 5 dk izgarasini limit'e kadar doner."""
    class Fake:
        requests_made = 0

        def get_json(self, path, params):
            self.requests_made += 1
            calls.append((path, dict(params)))
            assert params["period"] == "5m" and params["limit"] == 500
            lo = -(-params["startTime"] // C.PERIOD_MS) * C.PERIOD_MS
            out, t = [], lo
            while t <= params["endTime"] and len(out) < params["limit"]:
                out.append({"timestamp": t, "sumOpenInterest": "1", "sumOpenInterestValue": "2", "longShortRatio": "1",
                            "longAccount": "0.5", "shortAccount": "0.5", "buySellRatio": "1", "buyVol": "1", "sellVol": "1"})
                t += C.PERIOD_MS
            return out
    return Fake()


def test_gap_backfill_paginates_and_is_resumable(tmp_path):
    db = _db(tmp_path)
    calls: list = []
    fake = _fake_server(calls)
    last = NOW - 1200 * C.PERIOD_MS                                    # ~4 gun onceki son satir
    C.upsert(db, "BTC/USDT", [{"ts": last, "oi": 1.0}], 1)
    st = C.collect(db, fake, ["BTC/USDT"], NOW, endpoints=["oi"])
    oi_calls = [p for _, p in calls]
    assert len(oi_calls) == 3                                           # 1201 satir / 500 -> 3 dilim
    assert oi_calls[0]["startTime"] == last and oi_calls[1]["startTime"] == oi_calls[0]["endTime"] + 1
    assert all(p["endTime"] <= NOW for p in oi_calls)
    ts = [r[0] for r in db.execute("SELECT ts FROM positioning_5m ORDER BY ts")]
    assert ts[0] == last and ts[-1] == NOW and len(ts) == 1201 and len(set(ts)) == 1201
    assert all(b - a == C.PERIOD_MS for a, b in zip(ts, ts[1:]))
    # ikinci kosu: yalniz son satirdan (tek dilim), satir sayisi ayni
    calls.clear()
    C.collect(db, _fake_server(calls), ["BTC/USDT"], NOW + C.PERIOD_MS, endpoints=["oi"])
    assert len(calls) == 1 and calls[0][1]["startTime"] == NOW
    assert db.execute("SELECT COUNT(*) FROM positioning_5m").fetchone()[0] == 1202
    assert st.rows == 1201


@pytest.mark.usefixtures("kilitli")
def test_first_run_limited_to_lookback_and_never_requests_holdout(tmp_path):
    db = _db(tmp_path)
    calls: list = []
    now = C.HOLDOUT_END_MS + 3 * 86_400_000                            # kilitli donem 3 gun once bitti; 30 gun geri = kilitli donemin icinde
    C.collect(db, _fake_server(calls), ["ETH/USDT"], now, endpoints=["oi"])
    assert calls and all(p["symbol"] == "ETHUSDT" for _, p in calls)
    for _, p in calls:
        assert not (p["startTime"] < C.HOLDOUT_END_MS and p["endTime"] >= C.HOLDOUT_START_MS), p
    assert min(r[0] for r in db.execute("SELECT ts FROM positioning_5m")) >= C.HOLDOUT_END_MS


def test_budget_and_partial_errors(tmp_path):
    db = _db(tmp_path)
    st = C.collect(db, _fake_server([]), ["BTC/USDT", "ETH/USDT"], NOW, endpoints=["oi", "gls"], max_requests=1)
    assert st.budget_hit
    class Bad:
        requests_made = 0
        def get_json(self, *a):
            raise C.CollectorError("x")
    st = C.collect(_db(tmp_path), Bad(), ["BTC/USDT"], NOW, endpoints=["oi"])
    assert st.errors == 1


def _http_error(code, ra=None):
    h = {"Retry-After": str(ra)} if ra is not None else {}
    return urllib.error.HTTPError("u", code, "m", h, io.BytesIO(b"{}"))


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def test_http_retry_backoff_and_bans(monkeypatch):
    seq = [urllib.error.URLError("down"), _http_error(500), _Resp(b'[{"a":1}]')]
    def fake(req, timeout):
        assert "key" not in req.full_url.lower() and "signature" not in req.full_url.lower()
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    sleeps: list = []
    cl = C.HttpClient(sleep=sleeps.append, min_interval_s=0)
    assert cl.get_json("/p", {"symbol": "X"}) == [{"a": 1}]
    assert sleeps == [1.0, 2.0] and cl.requests_made == 3
    for code, exc in ((451, C.GeoBlockError), (418, C.BanError)):
        monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout, c=code: (_ for _ in ()).throw(_http_error(c)))
        with pytest.raises(exc):
            C.HttpClient(sleep=lambda s: None, min_interval_s=0).get_json("/p", {})
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout: (_ for _ in ()).throw(_http_error(429, 600)))
    with pytest.raises(C.BanError):
        C.HttpClient(sleep=lambda s: None, min_interval_s=0).get_json("/p", {})
    monkeypatch.setattr(urllib.request, "urlopen", lambda r, timeout: (_ for _ in ()).throw(_http_error(400)))
    with pytest.raises(C.CollectorError):
        C.HttpClient(sleep=lambda s: None, min_interval_s=0).get_json("/p", {})


def test_script_main_end_to_end_with_fake_client(tmp_path):
    calls: list = []
    db = tmp_path / "v" / "market.sqlite"
    rc = RUN.main(["--db", str(db), "--pairs", "BTC/USDT"], client=_fake_server(calls), now_ms=NOW)
    assert rc == 0 and len(calls) >= 5
    assert {p for p, _ in calls} == {v[0] for v in C.ENDPOINTS.values()}
    n = sqlite3.connect(db).execute("SELECT COUNT(*) FROM positioning_5m").fetchone()[0]
    assert 8000 < n < 9000          # kilit ACIK (23.11.2026): 30 gunluk geri pencere (~8640 satir) kilitli doneme dusse de tam yazilir
    pairs, mdb = RUN.load_pairs_and_db(ROOT / "config")
    assert len(pairs) == 10 and mdb.endswith("trader/var/market.sqlite")


def test_public_endpoints_only():
    src = (ROOT / "src/trader_engine/marketdata/oi_collector.py").read_text(encoding="utf-8")
    assert all(p.startswith("/futures/data/") for p, _ in C.ENDPOINTS.values())
    assert not re.search(r"signature|X-MBX-APIKEY|api_key|hmac", src, re.I)


# ------------------------------------------------------------------ systemd
def test_units_present_with_slice_and_hardening():
    s = (DEPLOY / "trader-oi.service").read_text(encoding="utf-8")
    t = (DEPLOY / "trader-oi.timer").read_text(encoding="utf-8")
    for k in ("Slice=trader.slice", "Type=oneshot", "User=trader", "NoNewPrivileges=true", "PrivateTmp=true",
              "ProtectSystem=strict", "ProtectHome=read-only", "OnFailure=trader-health-fail@%n.service"):
        assert k in s, k
    assert re.search(r"^MemoryMax=(\d+)M$", s, re.M) and int(re.search(r"^MemoryMax=(\d+)M$", s, re.M).group(1)) <= 128
    assert re.search(r"^ReadWritePaths=/opt/trader/var$", s, re.M)
    assert "/opt/trader/scripts/oi_collect.py" in s and (ROOT / "scripts/oi_collect.py").exists()
    assert "OnCalendar=*:0/5" in t and "WantedBy=timers.target" in t


def test_install_registers_oi_timer():
    i = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-oi.timer" in i
    assert i.index("enable_now trader-oi.timer") > i.index("enable_now trader-feed.service")
    assert "trader-*.timer" in (DEPLOY / "uninstall.sh").read_text(encoding="utf-8")
