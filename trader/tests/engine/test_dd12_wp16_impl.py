"""DD-12 WP-16 uygulayici testleri: aylik kagit evreni (D-T28). Ag yok; yalniz gecici dizinler.

Kapsam: stabil/sarili dislama, emtia sabit, acik pozisyonlu cift korunur, atomik yazma, kuru kosu yazmaz,
kaplama yalniz paper'da, gecersiz kaplama reddedilir.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_core import universe as U
from trader_engine.config import ConfigError, apply_universe_overlay, load_cli_config

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 12, 1, 0, 30, tzinfo=timezone.utc)

_spec = importlib.util.spec_from_file_location("universe_run", ROOT / "scripts" / "universe_run.py")
UR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(UR)

CRYPTO20 = ["BTC/USDT", "ETH/USDT", "XRP/USDT", "BNB/USDT", "SOL/USDT", "DOGE/USDT", "TRX/USDT", "ADA/USDT", "HYPE/USDT",
            "LINK/USDT", "BCH/USDT", "XLM/USDT", "SUI/USDT", "AVAX/USDT", "HBAR/USDT", "LTC/USDT", "TON/USDT",
            "1000SHIB/USDT", "DOT/USDT", "XMR/USDT"]
STOCKS = ["NVDA/USDT", "MSFT/USDT", "AAPL/USDT", "GOOGL/USDT", "AMZN/USDT", "META/USDT", "AVGO/USDT", "TSLA/USDT",
          "BRKB/USDT", "JPM/USDT", "LLY/USDT", "WMT/USDT", "V/USDT", "ORCL/USDT", "XOM/USDT", "NFLX/USDT", "PLTR/USDT",
          "COST/USDT", "AMD/USDT", "HD/USDT"]
COMM = ["XAU/USDT", "XAG/USDT", "BZ/USDT", "COPPER/USDT"]


@pytest.fixture
def env(tmp_path):
    """Gecici config (gercek config kopyasi) + var (market.sqlite, state.sqlite) dizinleri."""
    cfg = tmp_path / "config"
    shutil.copytree(ROOT / "config", cfg)
    var = tmp_path / "var"
    var.mkdir()
    return cfg, var


def _market(var: Path, trading: list[str], volumes: dict[str, float] | None = None) -> None:
    con = sqlite3.connect(var / "market.sqlite")
    con.execute("CREATE TABLE rules(pair TEXT PRIMARY KEY, json TEXT NOT NULL, fetched_ms INTEGER NOT NULL)")
    con.execute("CREATE TABLE bars(kind TEXT, pair TEXT, tf TEXT, open_ms INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL, "
                "written_ms INTEGER)")
    for p in trading:
        con.execute("INSERT INTO rules VALUES (?,?,0)", (p, "{}"))
    for p, vol in (volumes or {}).items():
        for i in range(3):
            con.execute("INSERT INTO bars VALUES ('last',?,'1h',?,1,1,1,?,?,0)", (p, i, 10.0, vol))
    con.commit()
    con.close()


def _state(var: Path, rows: list[tuple[str, str]]) -> None:
    (var / "learner").mkdir(exist_ok=True)
    con = sqlite3.connect(var / "learner" / "state.sqlite")
    con.execute("CREATE TABLE positions(bot TEXT, pair TEXT, status TEXT)")
    con.executemany("INSERT INTO positions VALUES ('learner', ?, ?)", rows)
    con.commit()
    con.close()


def _marketcap(tmp: Path, extra: list[dict]) -> Path:
    items = [{"pair": p, "market_cap": 1000.0 - i} for i, p in enumerate(CRYPTO20)] + extra
    f = tmp / "mcap.json"
    f.write_text(json.dumps({"items": items}), encoding="utf-8")
    return f


def _all_trading(exclude=()):
    return [p for p in CRYPTO20 + STOCKS + COMM if p not in exclude]


# --- saf fonksiyonlar -------------------------------------------------------------------------------------------------

def test_stablecoin_and_wrapped_excluded():
    cands = [{"pair": "USDC/USDT", "score": 9e9, "trading": True},
             {"pair": "WBTC/USDT", "score": 8e9, "trading": True},
             {"pair": "FDUSD/USDT", "score": 7e9, "trading": True},
             {"pair": "BTC/USDT", "score": 1.0, "trading": True}]
    excl = json.loads((ROOT / "config" / "universe.json").read_text(encoding="utf-8"))["exclude_bases"]
    out = U.select_crypto(cands, exclude_bases=excl, n=20)
    assert out == ["BTC/USDT"]


def test_non_trading_crypto_skipped_and_top_n():
    cands = [{"pair": f"C{i}/USDT", "score": float(100 - i), "trading": i != 0} for i in range(30)]
    out = U.select_crypto(cands, exclude_bases=[], n=20)
    assert len(out) == 20 and "C0/USDT" not in out and out[0] == "C1/USDT"


def test_pinned_ml_pairs_kept_within_count():
    cands = [{"pair": f"C{i}/USDT", "score": float(100 - i), "trading": True} for i in range(25)]
    out = U.select_crypto(cands, exclude_bases=[], n=20, pinned=["C24/USDT"])
    assert out[0] == "C24/USDT" and len(out) == 20


def test_select_stocks_uses_backup_when_not_trading():
    ordered = ["A/USDT", "B/USDT", "C/USDT", "D/USDT"]
    assert U.select_stocks(ordered, ["A/USDT", "C/USDT", "D/USDT"], n=2) == ["A/USDT", "C/USDT"]


def test_diff_pairs():
    assert U.diff_pairs(["A/USDT", "B/USDT"], ["B/USDT", "C/USDT"]) == {"added": ["C/USDT"], "removed": ["A/USDT"]}


# --- kuru kosu / evren olusturma --------------------------------------------------------------------------------------

def test_commodities_kept_even_when_not_trading(env, tmp_path):
    cfg, var = env
    _market(var, _all_trading(exclude=["XAU/USDT", "BZ/USDT"]))
    doc, rep = UR.build(cfg, var, _marketcap(tmp_path, []), NOW)
    assert "XAU/USDT" in doc["pairs"] and "BZ/USDT" in doc["pairs"]
    assert "XAU/USDT" in doc["optional_pairs"]
    assert len(doc["pairs"]) == 43   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    assert any("XAU/USDT" in n for n in doc["notes"])


def test_open_position_pair_retained_as_optional(env, tmp_path):
    cfg, var = env
    dropped = "DOT/USDT"
    extra = [{"pair": "NEWC/USDT", "market_cap": 5000.0}]
    _market(var, _all_trading() + ["NEWC/USDT"])
    _state(var, [(dropped, "open"), ("ETH/USDT", "closed")])
    items = [{"pair": p, "market_cap": 1000.0 - i} for i, p in enumerate(CRYPTO20) if p != dropped] + extra
    mc = tmp_path / "mc2.json"
    mc.write_text(json.dumps({"items": items}), encoding="utf-8")
    doc, rep = UR.build(cfg, var, mc, NOW)
    assert dropped in doc["pairs"] and dropped in doc["optional_pairs"]
    assert "NEWC/USDT" in doc["pairs"]
    assert rep["removed"] == []  # DOT korunur; eski listede de vardi
    assert len(doc["pairs"]) == 44  # 43 + korunan acik pozisyon   # 23.11 kullanici karari: TON cikarildi (SETTLING)


def test_closed_position_not_retained(env, tmp_path):
    cfg, var = env
    _market(var, _all_trading())
    _state(var, [("ZZZ/USDT", "closed")])
    doc, _ = UR.build(cfg, var, _marketcap(tmp_path, []), NOW)
    assert "ZZZ/USDT" not in doc["pairs"]


def test_volume_fallback_ranks_by_quote_volume(env):
    cfg, var = env
    vols = {p: float(i) for i, p in enumerate(CRYPTO20)}   # sonradan siralama: son eklenen en yuksek hacim
    _market(var, _all_trading(), vols)
    doc, rep = UR.build(cfg, var, None, NOW)
    assert rep["source"] == "volume_fallback"
    assert "XMR/USDT" in rep["crypto"]   # XMR: en yuksek hacim (19 Kasim: r03 emekli, ml_pairs bos => BTC artik sabit degil)
    assert len(rep["crypto"]) == 20


def test_dry_run_writes_nothing(env, tmp_path, capsys):
    cfg, var = env
    _market(var, _all_trading())
    rc = UR.main(["--config-dir", str(cfg), "--var-dir", str(var), "--marketcap", str(_marketcap(tmp_path, []))], now=NOW)
    assert rc == 0
    assert not (var / "universe").exists()
    assert "KURU KOSU" in capsys.readouterr().out


def test_no_network_calls(env, tmp_path, monkeypatch):
    cfg, var = env
    _market(var, _all_trading())

    def boom(*a, **k):
        raise AssertionError("ag cagrisi yasak")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    assert UR.main(["--config-dir", str(cfg), "--var-dir", str(var), "--marketcap", str(_marketcap(tmp_path, []))],
                   now=NOW) == 0


def test_atomic_write_keeps_old_file_on_failure(env, tmp_path, monkeypatch):
    cfg, var = env
    _market(var, _all_trading())
    target = var / "universe" / "paper_pairs.json"
    target.parent.mkdir(parents=True)
    target.write_text("ESKI", encoding="utf-8")
    import trader_engine.fileio as F

    def fail(src, dst):
        raise OSError("disk dolu (test)")
    monkeypatch.setattr(F.os, "replace", fail)
    with pytest.raises(OSError):
        UR.main(["--apply", "--config-dir", str(cfg), "--var-dir", str(var), "--marketcap", str(_marketcap(tmp_path, []))],
                now=NOW)
    assert target.read_text(encoding="utf-8") == "ESKI"
    assert not [p for p in target.parent.iterdir() if p.name.startswith(".")]


def test_apply_writes_valid_overlay_atomically(env, tmp_path):
    cfg, var = env
    _market(var, _all_trading())
    rc = UR.main(["--apply", "--config-dir", str(cfg), "--var-dir", str(var), "--marketcap", str(_marketcap(tmp_path, []))],
                 now=NOW)
    assert rc == 0
    obj = json.loads((var / "universe" / "paper_pairs.json").read_text(encoding="utf-8"))
    assert U.validate_overlay(obj)["pairs"] == obj["pairs"]
    assert len(obj["pairs"]) == 43 and obj["source"] == "marketcap"   # 23.11 kullanici karari: TON cikarildi (SETTLING)


# --- kaplama (config.py) ----------------------------------------------------------------------------------------------

def _write_overlay(var: Path, pairs, optional, schema=U.SCHEMA):
    (var / "universe").mkdir(parents=True, exist_ok=True)
    (var / "universe" / "paper_pairs.json").write_text(
        json.dumps({"schema": schema, "pairs": pairs, "optional_pairs": optional}), encoding="utf-8")


def test_overlay_applies_in_paper(env):
    cfg, var = env
    pairs = [p if p != "HD/USDT" else "ARM/USDT" for p in json.loads((cfg / "engine.paper.json").read_text())["pairs"]]
    opt = [p if p != "HD/USDT" else "ARM/USDT" for p in json.loads((cfg / "engine.paper.json").read_text())["optional_pairs"]]
    _write_overlay(var, pairs, opt)
    c = load_cli_config(cfg, "learner", "paper")
    assert "ARM/USDT" in c.pairs and "HD/USDT" not in c.pairs
    assert "ARM/USDT" in c.optional_pairs
    assert all("HD/USDT" not in members.pairs for members in c.clusters.values())


def test_overlay_ignored_for_testnet_and_backtest(env):
    cfg, var = env
    _write_overlay(var, ["BTC/USDT"], [])        # gecersiz olsa da okunmamali (yalniz paper)
    raw = {"mode": "testnet", "pairs": ["ETH/USDT"]}
    assert apply_universe_overlay(raw, var / "universe" / "paper_pairs.json") == raw
    raw_bt = {"mode": "backtest", "pairs": ["ETH/USDT"]}
    assert apply_universe_overlay(raw_bt, var / "universe" / "paper_pairs.json") == raw_bt


def test_missing_overlay_keeps_engine_paper_json(env):
    cfg, var = env
    a = load_cli_config(cfg, "learner", "paper")
    b = load_cli_config(ROOT / "config", "learner", "paper")
    assert a.pairs == b.pairs and a.optional_pairs == b.optional_pairs


@pytest.mark.parametrize("bad", [
    "{not json",
    json.dumps({"schema": "x/1", "pairs": ["BTC/USDT"], "optional_pairs": []}),
    json.dumps({"schema": U.SCHEMA, "pairs": ["BTC/USDT", "BTC/USDT"], "optional_pairs": []}),
    json.dumps({"schema": U.SCHEMA, "pairs": ["BTC/USDT"], "optional_pairs": ["ETH/USDT"]}),
    json.dumps({"schema": U.SCHEMA, "pairs": ["btc-usdt"], "optional_pairs": []}),
    json.dumps({"schema": U.SCHEMA, "pairs": [], "optional_pairs": []}),
])
def test_invalid_overlay_rejected(env, bad):
    cfg, var = env
    (var / "universe").mkdir(parents=True)
    (var / "universe" / "paper_pairs.json").write_text(bad, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_cli_config(cfg, "learner", "paper")


def test_validate_overlay_direct():
    with pytest.raises(ValueError):
        U.validate_overlay({"schema": U.SCHEMA, "pairs": ["A/USDT"], "optional_pairs": ["B/USDT"]})
    assert U.validate_overlay({"schema": U.SCHEMA, "pairs": ["A/USDT"], "optional_pairs": []})["pairs"] == ["A/USDT"]
