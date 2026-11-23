"""DD-12 WP-03 uygulayici duman testleri (evren: contract_types, isteğe bagli cift, feed --env). Sahte REST; ag yok."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_engine.clock import SimClock
from trader_engine.exchange.rules import RulesError, extract_all_rules, extract_rules
from trader_engine.marketdata import feed as F
from trader_engine.marketdata.feed import Feed, FeedConfig, RulesFetchError
from trader_engine.marketdata.store import MarketStore

ROOT = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def _sym(name, ctype):
    return {"symbol": name, "status": "TRADING", "contractType": ctype, "filters": [
        {"filterType": "PRICE_FILTER", "tickSize": "0.01"}, {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
        {"filterType": "MIN_NOTIONAL", "notional": "5"}]}


INFO = {"symbols": [_sym("BTCUSDT", "PERPETUAL"), _sym("NVDAUSDT", "TRADIFI_PERPETUAL")]}


class _Rest:
    base_url = "https://fake"

    def __init__(self, info):
        self.info = info

    def exchange_info(self):
        return self.info


def test_extract_rules_contract_types():
    with pytest.raises(RulesError, match="not_trading"):
        extract_rules(INFO, "NVDAUSDT")
    assert extract_rules(INFO, "NVDAUSDT", ("PERPETUAL", "TRADIFI_PERPETUAL")).symbol == "NVDAUSDT"
    assert extract_rules(INFO, "BTCUSDT") == extract_rules(INFO, "BTCUSDT", ("PERPETUAL", "TRADIFI_PERPETUAL"))
    r = extract_all_rules(INFO, ["BTCUSDT", "NVDAUSDT"])
    assert isinstance(r["NVDAUSDT"], RulesError) and not isinstance(r["BTCUSDT"], RulesError)


def _feed(tmp_path, pairs, optional, ctypes, info):
    cfg = FeedConfig(pairs=pairs, db_path=str(tmp_path / "m.sqlite"), lock_path=str(tmp_path / "l"), status_path=str(tmp_path / "s.json"),
                     optional_pairs=optional, contract_types=ctypes, rules_start_backoff_s=())
    return Feed(cfg, _Rest(info), MarketStore(cfg.db_path), SimClock(T0))


def test_optional_pair_rules_failure_not_fatal(tmp_path):
    f = _feed(tmp_path, ("BTC/USDT", "NVDA/USDT"), ("NVDA/USDT",), ("PERPETUAL",), INFO)
    f._refresh_rules(strict=True)          # NVDA reddedilir ama ölümcül değil


def test_required_pair_rules_failure_fatal(tmp_path):
    f = _feed(tmp_path, ("BTC/USDT", "NVDA/USDT"), (), ("PERPETUAL",), INFO)
    with pytest.raises(RulesFetchError) as e:
        f._fetch_rules_at_start()
    assert e.value.exit_code == F.EXIT_RULES


def test_tradifi_accepted_with_list(tmp_path):
    f = _feed(tmp_path, ("BTC/USDT", "NVDA/USDT"), (), ("PERPETUAL", "TRADIFI_PERPETUAL"), INFO)
    f._refresh_rules(strict=True)


def _cfgdir(tmp_path):
    d = tmp_path / "config"
    d.mkdir()
    (d / "engine.base.json").write_text((ROOT / "config/engine.base.json").read_text())
    (d / "engine.paper.json").write_text((ROOT / "config/engine.paper.json").read_text())
    return str(d)


def test_feed_config_env(tmp_path):
    d = _cfgdir(tmp_path)
    base = F.feed_config_from_base(d)
    paper = F.feed_config_from_base(d, "paper")
    assert len(base.pairs) == 10 and base.optional_pairs == () and base.contract_types == ("PERPETUAL",)
    assert len(paper.pairs) == 43 and len(paper.optional_pairs) == 24 and "TRADIFI_PERPETUAL" in paper.contract_types   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    assert paper.db_path == base.db_path


def test_feed_config_missing_env_failclosed(tmp_path):
    d = _cfgdir(tmp_path)
    with pytest.raises(F.FailClosed):
        F.feed_config_from_base(d, "testnet")


def test_feed_no_pandas():
    code = ("import sys; from trader_engine.marketdata import feed as F; "
            "F.feed_config_from_base('config','paper'); "
            "assert not {'pandas','numpy','requests'} & set(sys.modules), sorted({'pandas','numpy','requests'} & set(sys.modules))")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PATH": ""}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
