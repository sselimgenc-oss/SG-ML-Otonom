"""DD-12 WP-16 uygulayici testleri: aylik kagit evreni (D-T28). Ag yok; yalniz gecici dizinler.

Kapsam: stabil/sarili dislama, emtia sabit, acik pozisyonlu cift korunur, kuru kosu yazmaz.
SAHIP KARARI (evren 14 cift SABIT): `--apply` reddedilir, var/universe/paper_pairs.json motor yapilandirmasini DEGISTIREMEZ.
Kuru kosu raporu (bilgi amacli) eski 20 kripto + 20 hisse varsayimiyla test edilir: fixture kendi universe.json'ini yazar.
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
from trader_engine.config import load_cli_config

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
    u = json.loads((cfg / "universe.json").read_text(encoding="utf-8"))      # kuru kosu raporu testleri: eski genis evren varsayimi
    u.update(n_crypto=20, n_stocks=20, commodities=COMM, stocks_ordered=STOCKS)
    (cfg / "universe.json").write_text(json.dumps(u), encoding="utf-8")
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
    assert "XMR/USDT" in rep["crypto"]   # XMR: en yuksek hacim (BTC artik sabit degil)
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


def test_apply_refused_and_writes_nothing(env, tmp_path, capsys):
    cfg, var = env
    _market(var, _all_trading())
    rc = UR.main(["--apply", "--config-dir", str(cfg), "--var-dir", str(var), "--marketcap", str(_marketcap(tmp_path, []))],
                 now=NOW)
    assert rc == 1
    assert "reddedildi" in capsys.readouterr().err
    assert not (var / "universe").exists()


# --- kaplama dosyasi motor yapilandirmasini degistiremez --------------------------------------------------------------

def _write_overlay(var: Path, pairs, optional, schema=U.SCHEMA):
    (var / "universe").mkdir(parents=True, exist_ok=True)
    (var / "universe" / "paper_pairs.json").write_text(
        json.dumps({"schema": schema, "pairs": pairs, "optional_pairs": optional}), encoding="utf-8")


def test_overlay_file_cannot_change_pairs(env):
    cfg, var = env
    base = load_cli_config(cfg, "learner", "paper")
    _write_overlay(var, ["BTC/USDT", "ARM/USDT"], ["ARM/USDT"])
    c = load_cli_config(cfg, "learner", "paper")
    assert c.pairs == base.pairs and c.optional_pairs == base.optional_pairs and "ARM/USDT" not in c.pairs
    assert c.clusters == base.clusters and c.cost_overrides == base.cost_overrides
    (var / "universe" / "paper_pairs.json").write_text("{bozuk json", encoding="utf-8")      # bozuk dosya bile okunmaz
    assert load_cli_config(cfg, "learner", "paper").pairs == base.pairs


def test_load_cli_config_has_no_universe_parameter():
    import inspect
    from trader_engine import config as C
    assert not hasattr(C, "apply_universe_overlay") and not hasattr(C, "UNIVERSE_FILE")
    assert "universe_path" not in inspect.signature(C.load_engine_config).parameters


def test_validate_overlay_direct():
    with pytest.raises(ValueError):
        U.validate_overlay({"schema": U.SCHEMA, "pairs": ["A/USDT"], "optional_pairs": ["B/USDT"]})
    assert U.validate_overlay({"schema": U.SCHEMA, "pairs": ["A/USDT"], "optional_pairs": []})["pairs"] == ["A/USDT"]
