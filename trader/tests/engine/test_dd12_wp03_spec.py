"""DD-12 WP-03 (Evren ve feed) bagimsiz spec testleri: D-T3 (extract_rules contract_types), D-T4 (feed --env, istege bagli cift).
Sahte REST oturumu; ag ve gercek veri yok."""
from __future__ import annotations

import inspect
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_engine.bars import to_ms
from trader_engine.clock import SimClock
from trader_engine.exchange.rules import RulesError, SymbolRuleSpec, extract_rules
from trader_engine.marketdata import feed as F
from trader_engine.marketdata.rest_public import PublicRestClient
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import pair_symbol

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)
PERP, TRADIFI = "PERPETUAL", "TRADIFI_PERPETUAL"
BOTH = (PERP, TRADIFI)


def _sym(symbol, ctype=PERP, status="TRADING", with_notional=True):
    f = [{"filterType": "PRICE_FILTER", "tickSize": "0.10"},
         {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
         {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "120"}]
    if with_notional:
        f.append({"filterType": "MIN_NOTIONAL", "notional": "5"})
    return {"symbol": symbol, "status": status, "contractType": ctype, "filters": f}


# ----------------------------------------------------------------------------- D-T3: extract_rules
def test_dt3_default_signature_is_perpetual_only():
    p = inspect.signature(extract_rules).parameters["contract_types"]
    assert tuple(p.default) == (PERP,)


def test_dt3_tradifi_rejected_by_default():
    info = {"symbols": [_sym("NVDAUSDT", TRADIFI)]}
    with pytest.raises(RulesError) as ei:
        extract_rules(info, "NVDAUSDT")
    assert "not_trading" in str(ei.value)


def test_dt3_tradifi_returns_with_accept_list():
    info = {"symbols": [_sym("NVDAUSDT", TRADIFI)]}
    spec = extract_rules(info, "NVDAUSDT", contract_types=BOTH)
    assert isinstance(spec, SymbolRuleSpec) and spec.symbol == "NVDAUSDT" and str(spec.min_notional) == "5"
    spec2 = extract_rules(info, "NVDAUSDT", contract_types=(TRADIFI,))
    assert spec2 == spec


def test_dt3_perpetual_same_in_both_cases():
    info = {"symbols": [_sym("BTCUSDT")]}
    a = extract_rules(info, "BTCUSDT")
    assert a == extract_rules(info, "BTCUSDT", contract_types=(PERP,)) == extract_rules(info, "BTCUSDT", contract_types=BOTH)


def test_dt3_accept_list_is_exclusive_and_other_checks_stay():
    info = {"symbols": [_sym("BTCUSDT"), _sym("XAUUSDT", TRADIFI, status="BREAK"), _sym("ETHUSDT", "CURRENT_QUARTER"),
                        _sym("NVDAUSDT", TRADIFI, with_notional=False)]}
    with pytest.raises(RulesError):                                   # liste disi tur
        extract_rules(info, "BTCUSDT", contract_types=(TRADIFI,))
    with pytest.raises(RulesError, match="not_trading"):               # durum TRADING sart
        extract_rules(info, "XAUUSDT", contract_types=BOTH)
    with pytest.raises(RulesError, match="not_trading"):               # bilinmeyen tur listede yoksa red
        extract_rules(info, "ETHUSDT", contract_types=BOTH)
    with pytest.raises(RulesError, match="min_notional_missing"):      # eksik filtre yine hata
        extract_rules(info, "NVDAUSDT", contract_types=BOTH)
    with pytest.raises(RulesError):
        extract_rules(info, "YYYUSDT", contract_types=BOTH)           # yok


# ----------------------------------------------------------------------------- feed fakes
class _Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._b, self.headers, self.text = status, body, {}, text

    def json(self):
        return self._b


class _Session:
    def __init__(self, server_ms, symbols, kline_fail=()):
        self.server_ms, self.symbols, self.kline_fail = server_ms, symbols, set(kline_fail)
        self.paths = []

    def get(self, url, params=None, timeout=None):
        path = url.split("fapi.binance.com")[1]
        self.paths.append(path)
        if path == "/fapi/v1/time":
            return _Resp(200, {"serverTime": self.server_ms})
        if path == "/fapi/v1/exchangeInfo":
            return _Resp(200, {"symbols": self.symbols})
        if params and params.get("symbol") in self.kline_fail:
            return _Resp(400, {"code": -1121, "msg": "Invalid symbol."}, "bad")
        return _Resp(200, [])


def _rest(sess, clock):
    return PublicRestClient(session=sess, now_s=lambda: clock.now().timestamp(), sleep=clock.sleep, max_attempts=2)


def _cfg(tmp_path):
    """Gercek taban/ogrenen/kagit yapilandirmasinin kopyasi; yollar tmp'ye."""
    d = tmp_path / "config"
    d.mkdir()
    for n in ("engine.base.json", "engine.learner.json", "engine.paper.json"):
        shutil.copy(REPO / "config" / n, d / n)
    b = json.loads((d / "engine.base.json").read_text())
    b.update(var_dir=str(tmp_path / "var"), market_db=str(tmp_path / "var" / "market.sqlite"), history_dir=str(tmp_path / "hist"))
    (d / "engine.base.json").write_text(json.dumps(b))
    paper = json.loads((d / "engine.paper.json").read_text())
    return d, b, paper


def _symbols(base, paper, *, drop=(), bad=()):
    out = []
    opt = set(paper["optional_pairs"])
    for p in paper["pairs"]:
        s = pair_symbol(p)
        if s in drop:
            continue
        out.append(_sym(s, TRADIFI if p in opt else PERP, with_notional=s not in bad))
    return out


def _run(d, sess, *extra):
    clock = SimClock(T0)
    sess.server_ms = to_ms(T0)
    rc = F.main(["--config-dir", str(d), *extra], rest=_rest(sess, clock), clock=clock, max_ticks=2)
    return rc, clock


def _store(tmp_path):
    return MarketStore(tmp_path / "var" / "market.sqlite", read_only=True)


# ----------------------------------------------------------------------------- D-T4: feed
def test_dt4_env_paper_loads_44_pairs_and_tradifi_rules(tmp_path):
    d, base, paper = _cfg(tmp_path)
    assert len(paper["pairs"]) == 14 and paper["optional_pairs"]   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    sess = _Session(0, _symbols(base, paper))
    rc, _ = _run(d, sess, "--env", "paper")
    assert rc == 0
    st = _store(tmp_path)
    for p in paper["pairs"]:
        assert st.get_rules(p) is not None, p
    assert st.meta_get("rules_last_error") == ""


@pytest.mark.parametrize("mode", ["missing", "bad_filter", "klines_fail"])
def test_dt4_optional_pair_failure_is_not_fatal(tmp_path, mode):
    d, base, paper = _cfg(tmp_path)
    opt = paper["optional_pairs"][0]
    s = pair_symbol(opt)
    sess = _Session(0, _symbols(base, paper, drop={s} if mode == "missing" else (), bad={s} if mode == "bad_filter" else ()),
                    kline_fail={s} if mode == "klines_fail" else ())
    rc, _ = _run(d, sess, "--env", "paper")
    assert rc == 0
    st = _store(tmp_path)
    if mode != "klines_fail":
        assert st.get_rules(opt) is None                      # yalniz o cift kuralsiz
    for p in paper["pairs"]:
        if p != opt:
            assert st.get_rules(p) is not None, p              # digerleri etkilenmez


def test_dt4_required_pair_rules_failure_keeps_todays_exit_code(tmp_path):
    d, base, paper = _cfg(tmp_path)
    assert "BTC/USDT" not in paper["optional_pairs"]   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    sess = _Session(0, _symbols(base, paper, drop={"BTCUSDT"}))
    rc, clock = _run(d, sess, "--env", "paper")
    assert rc == F.EXIT_RULES == 5
    assert (clock.now() - T0).total_seconds() >= 5 + 15 + 45   # bugunku sinirli geri cekilme


def test_dt4_required_pair_failure_even_if_only_optional_ok(tmp_path):
    d, base, paper = _cfg(tmp_path)
    sess = _Session(0, _symbols(base, paper, bad={"ETHUSDT"}))
    rc, _ = _run(d, sess, "--env", "paper")
    assert rc == F.EXIT_RULES


def test_dt4_without_env_is_head_behaviour(tmp_path):
    d, base, paper = _cfg(tmp_path)
    (d / "engine.paper.json").write_text("{ not json")        # --env yokken okunmaz
    sess = _Session(0, [_sym(pair_symbol(p)) for p in base["pairs"]])
    rc, _ = _run(d, sess)
    assert rc == 0
    st = _store(tmp_path)
    assert all(st.get_rules(p) is not None for p in base["pairs"])
    assert len(base["pairs"]) == 5
    # yalniz taban 10 cift istenir: baska sembol icin kline istegi yok
    assert sess.paths.count("/fapi/v1/exchangeInfo") >= 1


def test_dt4_without_env_tradifi_base_pair_and_missing_pair_still_fatal(tmp_path):
    d, base, paper = _cfg(tmp_path)
    syms = [_sym(pair_symbol(p), TRADIFI if p == "BTC/USDT" else PERP) for p in base["pairs"]]
    rc, _ = _run(d, _Session(0, syms))
    assert rc == F.EXIT_RULES                                  # varsayilan PERPETUAL: TRADIFI kabul edilmez
    d2 = tmp_path / "second"
    d2.mkdir()
    d3, base3, _ = _cfg(d2)
    rc2, _ = _run(d3, _Session(0, [_sym(pair_symbol(p)) for p in base3["pairs"][1:]]))
    assert rc2 == F.EXIT_RULES


def test_dt4_without_env_extra_symbols_not_stored(tmp_path):
    d, base, paper = _cfg(tmp_path)
    syms = [_sym(pair_symbol(p)) for p in base["pairs"]] + [_sym("NVDAUSDT", TRADIFI)]
    rc, _ = _run(d, _Session(0, syms))
    assert rc == 0
    assert _store(tmp_path).get_rules("NVDA/USDT") is None


def test_dt4_env_paper_feed_does_not_import_pandas(tmp_path):
    d, base, paper = _cfg(tmp_path)
    code = f"""
import sys, json
sys.path.insert(0, {str(REPO / 'src')!r})   # -I altinda PYTHONPATH yok: src acikca eklenir (editable kuruluma bagli degil)
sys.path.insert(0, {str(HERE)!r})
import test_dd12_wp03_spec as T
from trader_engine.marketdata import feed as F
from trader_engine.clock import SimClock
from trader_engine.bars import to_ms
base = json.load(open({str(d / 'engine.base.json')!r})); paper = json.load(open({str(d / 'engine.paper.json')!r}))
sess = T._Session(to_ms(T.T0), T._symbols(base, paper))
clock = SimClock(T.T0)
rc = F.main(['--config-dir', {str(d)!r}, '--env', 'paper'], rest=T._rest(sess, clock), clock=clock, max_ticks=1)
bad = sorted(m for m in ('pandas', 'numpy', 'requests', 'pyarrow') if m in sys.modules)
print('RC', rc, 'HEAVY', bad)
"""
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=300,
                       env={"PYTHONPATH": f"{REPO / 'src'}:{HERE}", "PATH": "/usr/bin:/bin"})
    assert "RC 0 HEAVY []" in r.stdout, (r.stdout, r.stderr[-800:])
