"""Piyasa verisi alarmlari (docs/saglik-spec.md Bolum 15): gecici dosya + sqlite fikstürleri, saat enjekte."""
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import health as H
from trader_core.health import Status
from trader_core.market_probe import probe_market

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
PAIRS = ("BTC/USDT", "ETH/USDT")


def _ms(dt):
    return int(dt.timestamp() * 1000)


def z(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_runner():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("health_run_m", ROOT / "scripts" / "health_run.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    finally:
        sys.path.remove(str(ROOT / "scripts"))


R = _load_runner()


def make_world(tmp, *, bar_age=30, feed_age=20, rules=PAIRS, rules_age=3600, rm=0, db=True, feed=True):
    var = tmp / "var"
    var.mkdir()
    if feed:
        (var / "feed-status.json").write_text(json.dumps(
            {"schema": "engine/feed-status/1", "ts": z(NOW - timedelta(seconds=feed_age)), "pairs": list(PAIRS)}))
    if db:
        c = sqlite3.connect(var / "market.sqlite")
        c.executescript("""CREATE TABLE bars(kind TEXT, pair TEXT, tf TEXT, open_ms INTEGER, o REAL, h REAL, l REAL,
            c REAL, v REAL, written_ms INTEGER);
            CREATE TABLE rules(pair TEXT PRIMARY KEY, json TEXT, fetched_ms INTEGER);
            CREATE TABLE feed_meta(k TEXT PRIMARY KEY, v TEXT);""")
        for p in PAIRS:
            c.execute("INSERT INTO bars VALUES('last',?, '1m',?,1,1,1,1,1,0)", (p, _ms(NOW - timedelta(seconds=bar_age))))
            c.execute("INSERT INTO bars VALUES('last',?, '1m',?,1,1,1,1,1,0)", (p, _ms(NOW - timedelta(hours=1))))
        for p in rules:
            c.execute("INSERT INTO rules VALUES(?, '{}', 0)", (p,))
        c.execute("INSERT INTO feed_meta VALUES('rules_fetched_at', ?)", (str(_ms(NOW - timedelta(seconds=rules_age))),))
        c.commit()
        c.close()
    for bot in ("learner", "twin"):
        d = var / bot
        d.mkdir()
        (d / "status.json").write_text(json.dumps({"schema": "engine-status/1", "bot": bot,
                                                   "counters": {"rules_missing": rm}}))
    return var


def snap(var, prev=None):
    m = probe_market(db_path=str(var / "market.sqlite"), feed_status_path=str(var / "feed-status.json"), pairs=PAIRS,
                     engine_status_paths={b: str(var / b / "status.json") for b in ("learner", "twin")})
    return H.HealthSnapshot(now=NOW, market=m)


def results(var, prev=None):
    rep = H.evaluate(snap(var, prev), H.HealthConfig(require_bots=("learner", "twin")))   # DD-12: varsayilan yalniz learner; genel coklu bot denetimi
    return {r.name: r for r in rep.results if r.name in (
        "market_bar_age",)}


def test_happy_path_no_alarm(tmp_path):
    r = results(make_world(tmp_path), prev={"learner": 0, "twin": 0})
    assert len(r) == 1 and all(x.status is Status.OK for x in r.values()), r


def test_disabled_when_market_none():
    rep = H.evaluate(H.HealthSnapshot(now=NOW))
    assert not any(x.name == "market_bar_age" for x in rep.results)


def test_bar_stale_crit(tmp_path):
    x = results(make_world(tmp_path, bar_age=301))["market_bar_age"]
    assert x.status is Status.CRIT and x.code == "market_bars_stale"


def test_bar_missing_for_one_pair_crit(tmp_path):
    var = make_world(tmp_path)
    c = sqlite3.connect(var / "market.sqlite")
    c.execute("DELETE FROM bars WHERE pair='ETH/USDT'")
    c.commit()
    c.close()
    x = results(var)["market_bar_age"]
    assert x.status is Status.CRIT and "ETH/USDT" in x.detail


def test_market_db_missing_crit_clear_message(tmp_path):
    r = results(make_world(tmp_path, db=False))
    for n in ("market_bar_age",):
        assert r[n].status is Status.CRIT and r[n].code == "market_db_missing" and "market.sqlite" in r[n].detail


def test_reader_is_read_only(tmp_path):
    var = make_world(tmp_path)
    before = (var / "market.sqlite").read_bytes()
    snap(var)
    assert (var / "market.sqlite").read_bytes() == before
    assert not list(var.glob("market.sqlite-*"))


def test_loop_lag_already_covered_by_bot_loop_age():
    assert H.DEFAULT_CFG.loop_crit_s == 300 and H.DEFAULT_CFG.market_bar_crit_s == 300


# ---- 44 enstruman: yapilandirilmis (10) U feed-status listesi; seans kapali cift CRIT uretmez
def _world44(tmp, extra, *, cfg_pairs=PAIRS, bar_age=30, stale=()):
    var = make_world(tmp)
    fs = json.loads((var / "feed-status.json").read_text())
    fs["pairs"] = list(PAIRS) + list(extra)
    (var / "feed-status.json").write_text(json.dumps(fs))
    c = sqlite3.connect(var / "market.sqlite")
    for p in extra:
        age = 3600 * 5 if p in stale else bar_age
        c.execute("INSERT INTO bars VALUES('last',?, '1m',?,1,1,1,1,1,0)", (p, _ms(NOW - timedelta(seconds=age))))
    c.commit()
    c.close()
    return var


def test_probe_union_configured_first_deduped(tmp_path):
    var = _world44(tmp_path, ["HYPE/USDT", "btc/usdt:USDT", "NVDA/USDT"])
    m = probe_market(db_path=str(var / "market.sqlite"), feed_status_path=str(var / "feed-status.json"), pairs=PAIRS)
    assert m.pairs == ("BTC/USDT", "ETH/USDT", "HYPE/USDT", "NVDA/USDT")
    assert "HYPE/USDT" in m.newest_bar_at


def _eval(var, m_classes, now):
    m = probe_market(db_path=str(var / "market.sqlite"), feed_status_path=str(var / "feed-status.json"), pairs=PAIRS,
                     pair_classes=m_classes)
    rep = H.evaluate(H.HealthSnapshot(now=now, market=m), H.HealthConfig(require_bots=("learner",)))
    return {r.name: r for r in rep.results}["market_bar_age"]


def test_stale_crypto_outside_base10_is_crit(tmp_path):
    var = _world44(tmp_path, ["HYPE/USDT"], stale=("HYPE/USDT",))
    x = _eval(var, {}, NOW)
    assert x.status is Status.CRIT and "HYPE/USDT" in x.detail


def test_closed_session_stock_and_commodity_no_crit(tmp_path):
    sat = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)   # Cumartesi
    var = _world44(tmp_path, ["NVDA/USDT", "XAU/USDT"], stale=("NVDA/USDT", "XAU/USDT"))
    # kripto ciftlerin mumu taze olmali: make_world mumlari NOW'a gore; saati NOW'da tutup yalniz sinifi sinamak icin
    # seans kontrolu zamana baglidir, bu yuzden tum veriyi cumartesiye kaydir.
    c = sqlite3.connect(var / "market.sqlite")
    c.execute("DELETE FROM bars WHERE pair IN ('BTC/USDT','ETH/USDT')")
    for p in PAIRS:
        c.execute("INSERT INTO bars VALUES('last',?, '1m',?,1,1,1,1,1,0)", (p, _ms(sat - timedelta(seconds=30))))
    c.commit()
    c.close()
    x = _eval(var, {"NVDA/USDT": "hisse", "XAU/USDT": "emtia"}, sat)
    assert x.status is Status.OK, x.detail


def test_open_session_stale_stock_is_crit(tmp_path):
    tue = datetime(2026, 11, 17, 16, 0, tzinfo=timezone.utc)   # Sali 11:00 NY: seans acik
    assert NOW == datetime(2026, 11, 17, 12, 0, tzinfo=timezone.utc)
    var = _world44(tmp_path, ["NVDA/USDT"], stale=("NVDA/USDT",))
    c = sqlite3.connect(var / "market.sqlite")
    c.execute("DELETE FROM bars WHERE pair IN ('BTC/USDT','ETH/USDT')")
    for p in PAIRS:
        c.execute("INSERT INTO bars VALUES('last',?, '1m',?,1,1,1,1,1,0)", (p, _ms(tue - timedelta(seconds=30))))
    c.commit()
    c.close()
    x = _eval(var, {"NVDA/USDT": "hisse"}, tue)
    assert x.status is Status.CRIT and "NVDA/USDT" in x.detail


def test_runner_pair_classes_from_universe(tmp_path):
    cd = tmp_path / "cfg"
    cd.mkdir()
    (cd / "universe.json").write_text(json.dumps({"stocks_ordered": ["NVDA/USDT"], "commodities": ["XAU/USDT"]}))
    assert R.pair_classes({"ENGINE_CONFIG_DIR": str(cd)}) == {"NVDA/USDT": "hisse", "XAU/USDT": "emtia"}
    assert R.pair_classes({"ENGINE_CONFIG_DIR": str(tmp_path / "yok")}) == {}
    assert R.pair_classes({}) == {}
