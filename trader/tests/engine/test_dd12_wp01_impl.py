"""DD-12 WP-01 uygulayici duman testleri (kagit yapilandirmasi + risk parametreleri)."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from trader_core import risk as K
from trader_engine.cli import build_parser
from trader_engine.config import ConfigError, apply_overrides, load_cli_config, load_engine_config

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config"


def _raw(mode="paper", **extra):
    raw = json.loads((CFG / "engine.base.json").read_text())
    raw["bot"] = "learner"
    if mode in ("testnet", "live"):
        raw.update(json.loads((CFG / f"engine.{mode}.json").read_text()))
    raw["mode"] = mode
    if mode == "backtest":
        raw["veto_mode"] = "off"
    raw.update(extra)
    return raw


def _load(tmp_path, raw):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(raw))
    return load_engine_config(p)


def test_paper_config_shape():
    c = load_cli_config(CFG, "learner", "paper")
    assert c.mode == "paper" and c.bot == "learner" and len(c.pairs) == 43   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    assert set(json.loads((CFG / "engine.base.json").read_text())["pairs"]) <= set(c.pairs)
    assert len(c.optional_pairs) == 24 and set(c.optional_pairs) <= set(c.pairs)
    assert c.max_positions == 24 and c.ml_mode == "active" and c.shadow_blocks == ("regime", "r1_disabled", "same_bar_reentry", "tf_15m")
    # 19 Kasim: r03 kagitta emekli (kullanici karari)
    assert c.ml_features == "v1" and c.ml_experimental is False and c.ml_pairs == () and c.ml_model_path is None
    raw_paper = json.loads((CFG / "engine.paper.json").read_text())
    assert not {"ml_pairs", "ml_features", "ml_model_path", "ml_experimental"} & set(raw_paper)
    assert [s.max_positions for s in c.clusters.values()] == [6, 9, 8, 5, 3, 3]
    assert [len(s.pairs) for s in c.clusters.values()] == [5, 14, 20, 12, 2, 2]   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    assert c.flat_bar_guard is True and "TRADIFI_PERPETUAL" in c.contract_types
    assert set(c.cost_overrides) == set(c.optional_pairs)   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    r = c.risk_config
    assert (r.target_trade_risk, r.max_open_risk, r.max_same_dir_risk, r.daily_max_loss) == (0.01, 0.24, 0.16, 0.08)


def test_removed_layers():
    assert not (CFG / "engine.paper-ml.json").exists() and not (CFG / "engine.twin.json").exists()
    with pytest.raises(ConfigError):
        load_engine_config(CFG / "engine.base.json", overlay_path=None) if False else load_cli_config(CFG, "twin")
    with pytest.raises(ConfigError):
        load_cli_config(CFG, "learner", "paper-ml")


def test_cli_env_and_bot_choices():
    ap = build_parser()
    ns = ap.parse_args(["run", "--bot", "learner", "--env", "paper"])
    assert ns.env == "paper"
    for argv in (["run", "--bot", "twin"], ["run", "--bot", "learner", "--env", "paper-ml"]):
        with pytest.raises(SystemExit):
            ap.parse_args(argv)


def test_locked_defaults_bit_identical():
    d = K.RiskConfig()
    assert (d.max_open_risk, d.max_same_dir_risk, d.daily_max_loss, d.target_trade_risk) == (0.06, 0.04, 0.05, 0.014)
    assert type(d) is K.RiskConfig and K.LOCKED_CFG == d
    with pytest.raises(ValueError):
        K.RiskConfig(max_open_risk=0.12)              # kilitli profil gevsemez
    with pytest.raises(ValueError):
        K.paper_config(max_open_risk=0.25)             # kagit ust siniri (0.24) asilmaz
    with pytest.raises(ValueError):
        K.paper_config(max_same_dir_risk=0.17)
    with pytest.raises(ValueError):
        K.paper_config(daily_max_loss=0.09)
    assert K.paper_config(max_open_risk=0.24, max_same_dir_risk=0.16).max_open_risk == 0.24
    with pytest.raises(ValueError):
        K.paper_config(max_trade_risk=0.03)            # yalniz PAPER_KEYS


@pytest.mark.parametrize("mode", ["testnet", "backtest"])      # 23.11 kullanici karari: canli = kagit (canli bu anahtarlari kabul eder)
@pytest.mark.parametrize("key,val", [
    ("risk", {"max_open_risk": 0.12}), ("max_positions", 16), ("flat_bar_guard", True),
    ("contract_types", ["TRADIFI_PERPETUAL"]), ("optional_pairs", ["BTC/USDT"]), ("ml_pairs", ["BTC/USDT"]),
    ("clusters", {"x": {"pairs": ["BTC/USDT"], "max_positions": 1}}),
    ("cost_overrides", {"BTC/USDT": {"open": {"slip_entry_bps": 1.0}}}),
])
def test_new_keys_rejected_outside_paper(tmp_path, mode, key, val):
    _load(tmp_path, _raw(mode))                        # kontrol: anahtarsiz gecerli
    with pytest.raises(ConfigError, match="paper"):
        _load(tmp_path, _raw(mode, **{key: val}))


@pytest.mark.parametrize("key,val", [
    ("optional_pairs", ["NVDA/USDT"]), ("ml_pairs", ["NVDA/USDT"]),
    ("clusters", {"x": {"pairs": ["NVDA/USDT"], "max_positions": 1}}),
    ("cost_overrides", {"NVDA/USDT": {"open": {"slip_entry_bps": 1.0}}}),
    ("max_positions", 0), ("max_positions", True),
    ("risk", {"max_open_risk": 0.25}), ("risk", {"max_same_dir_risk": 0.17}), ("risk", {"daily_max_loss": 0.09}),
    ("risk", {"bogus": 1}), ("risk", {"target_trade_risk": 0.02}), ("target_trade_risk", 0.02),
    ("contract_types", ["SPOT"]), ("flat_bar_guard", "yes"),
])
def test_paper_validation_errors(tmp_path, key, val):
    with pytest.raises(ConfigError):
        _load(tmp_path, _raw("paper", **{key: val}))


def test_testnet_live_risk_unchanged(tmp_path):
    for mode in ("testnet",):        # 23.11 kullanici karari: canli = kagit (canli: LiveRiskConfig, test_canli_kagit_parite.py)
        r = _load(tmp_path, _raw(mode)).risk_config
        assert r == K.tightened(K.LOCKED_CFG, target_trade_risk=0.005) and type(r) is K.RiskConfig
        assert (r.max_open_risk, r.max_same_dir_risk, r.daily_max_loss) == (0.06, 0.04, 0.05)
    # canli: acik `risk` blogu yoksa hala kilitli sinirlar (kagit sinirlari yalniz `risk` blogu ile gelir; ayrinti: test_canli_kagit_parite.py)
    raw = _raw("live")
    raw.pop("risk", None)
    raw["target_trade_risk"] = 0.005
    r = _load(tmp_path, raw).risk_config
    assert r == K.tightened(K.LOCKED_CFG, target_trade_risk=0.005) and type(r) is K.RiskConfig


def test_paper_without_new_keys_is_old_behaviour(tmp_path):
    c = _load(tmp_path, _raw("paper"))
    assert c.risk_config == K.tightened(K.LOCKED_CFG, target_trade_risk=0.005)
    assert c.max_positions is None and c.clusters == {} and c.optional_pairs == () and c.contract_types is None


def test_apply_overrides_roundtrip_and_lock():
    c = load_cli_config(CFG, "learner", "paper")
    assert apply_overrides(c, wallet_start=500.0).risk_config == c.risk_config
    with pytest.raises(ConfigError):
        apply_overrides(c, mode="testnet")


def test_ml_experimental_active_needs_ml_pairs(tmp_path):
    with pytest.raises(ConfigError, match="paper\\+shadow"):
        _load(tmp_path, _raw("paper", ml_mode="active", ml_experimental=True))


def test_dataclass_fields_have_defaults():
    c = load_cli_config(CFG, "learner", None)
    names = {f.name for f in dataclasses.fields(c)}
    assert {"optional_pairs", "ml_pairs", "max_positions", "risk", "clusters", "flat_bar_guard",
            "contract_types", "cost_overrides"} <= names
