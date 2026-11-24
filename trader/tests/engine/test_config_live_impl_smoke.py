"""WP-B2 gerceklestirme duman testleri (11 §3): kipler, live blogu, LIVE_CONFIRM, keys_missing, cikis kodu 8."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trader_core.risk import LOCKED_CFG
from trader_engine import cli
from trader_engine.config import apply_overrides, load_engine_config, load_keys
from trader_engine.engine import EngineExit
from trader_engine.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config"
LIVE = {"account_tag": "sub-acct-1", "expected_wallet_max": 1500.0}
GOOD = "A" * 32


def _base(**kw):
    if kw.get("mode") in ("testnet", "live"):       # DD-8 yol kurali: testnet/live kagit `var`/`shared/KILL|PAUSE` yollarini kullanamaz
        for k, v in (("var_dir", "var-testnet"), ("kill_file", "shared/testnet/KILL"), ("pause_file", "shared/testnet/PAUSE")):
            kw.setdefault(k, v)
    return apply_overrides(load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json"), **kw)


def test_paper_unchanged():
    c = _base()
    assert c.mode == "paper" and c.live is None and c.leverage == LOCKED_CFG.min_leverage == 3


def test_testnet_overlay_loads():
    c = load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json", overlay_path=CFG / "engine.testnet.json")
    assert c.mode == "testnet" and c.live is not None and c.var_dir == "var-testnet"


def test_live_block_required_and_forbidden():
    for m in ("testnet", "live"):
        with pytest.raises(ConfigError):
            _base(mode=m)
        assert _base(mode=m, live=LIVE).live.account_tag == "sub-acct-1"
    with pytest.raises(ConfigError):
        _base(live=LIVE)
    with pytest.raises(ConfigError):
        _base(mode="testnet", live={**LIVE, "account_tag": "X"})
    with pytest.raises(ConfigError):
        _base(mode="testnet", live={**LIVE, "stop_deadline_s": 16})


def test_leverage_range():
    assert _base(leverage=5).leverage == 5
    for v in (2, 6, True, 3.5):
        with pytest.raises(ConfigError):
            _base(leverage=v)


def test_live_rules():
    with pytest.raises(ConfigError):
        _base(mode="live", bot="twin", live=LIVE)
    with pytest.raises(ConfigError):
        _base(mode="testnet", bot="twin", live=LIVE)
    with pytest.raises(ConfigError):
        _base(mode="testnet", live=LIVE, cost={"trigger_source": "last"})
    with pytest.raises(ConfigError):
        _base(mode="live", live=LIVE, cost={"trigger_source": "last"})


def _write_live(tmp_path, tag="sub-acct-1"):
    p = tmp_path / "live.json"
    p.write_text(json.dumps({"mode": "live", "live": {**LIVE, "account_tag": tag}, "var_dir": "var-live",
                             "kill_file": "shared/live/KILL", "pause_file": "shared/live/PAUSE"}))
    return p


def test_live_confirm(tmp_path):
    p = _write_live(tmp_path)
    args = (CFG / "engine.base.json", CFG / "engine.learner.json")
    assert load_engine_config(*args, overlay_path=p, env={"LIVE_CONFIRM": "sub-acct-1"}).mode == "live"
    for env in ({}, {"LIVE_CONFIRM": "sub-acct-2"}, {"LIVE_CONFIRM": ""}):
        with pytest.raises(ConfigError, match="live_confirm"):
            load_engine_config(*args, overlay_path=p, env=env)


def test_load_keys():
    assert load_keys({"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": "B" * 40}) == (GOOD, "B" * 40)
    for env in ({}, {"BINANCE_API_KEY": GOOD}, {"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": "short"},
                {"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": "B" * 20 + " " + "B" * 20},
                {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": GOOD}):
        with pytest.raises(ConfigError, match="keys_missing"):
            load_keys(env)


def _run(monkeypatch, env, checker=None):
    for k in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "LIVE_CONFIRM"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    a = cli.build_parser().parse_args(["run", "--bot", "learner", "--env", "testnet", "--config-dir", str(CFG)])
    return cli._cmd_run(a, checker=checker)


def test_cli_exit_codes(monkeypatch):
    assert cli.EXIT_PERMISSION == 8
    assert _run(monkeypatch, {}) == cli.EXIT_FAZ_B                      # keys_missing
    keys = {"BINANCE_API_KEY": GOOD, "BINANCE_API_SECRET": GOOD}
    # B4 sonrasi: anahtarlar varken run gercek build_engine'e gider; ag yok -> EngineExit(5)
    import trader_engine.engine as _eng

    def _unreachable(cfg, *a, **k):
        raise EngineExit(5, "exchange_unreachable")
    monkeypatch.setattr(_eng, "build_engine", _unreachable)
    assert _run(monkeypatch, keys) == 5

    def refuse(cfg, k, s):
        raise EngineExit(8, "key_permission:enableWithdrawals")
    assert _run(monkeypatch, keys, checker=refuse) == 8
    seen = []
    assert _run(monkeypatch, keys, checker=lambda c, k, s: seen.append(c.mode)) == cli.EXIT_FAZ_B and seen == ["testnet"]


# ------------------------------------------------------------------ mentor duzeltmeleri F1-F9
def _live_dir(tmp_path):
    import shutil
    d = tmp_path / "cfg"
    shutil.copytree(CFG, d)
    (d / "engine.live.json").write_text(json.dumps(
        {"mode": "live", "var_dir": str(tmp_path / "var-live"), "kill_file": str(tmp_path / "K"),
         "pause_file": str(tmp_path / "P"), "live": LIVE}))
    return d


def test_load_engine_config_no_confirm_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("LIVE_CONFIRM", raising=False)
    d = _live_dir(tmp_path)
    c = load_engine_config(d / "engine.base.json", d / "engine.learner.json", overlay_path=d / "engine.live.json")
    assert c.mode == "live"
    with pytest.raises(ConfigError, match="live_confirm"):
        load_engine_config(d / "engine.base.json", d / "engine.learner.json",
                           overlay_path=d / "engine.live.json", env={})


def test_kill_pause_succeed_under_live_config_without_confirm(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LIVE_CONFIRM", raising=False)
    d = _live_dir(tmp_path)
    cd = ["--config-dir", str(d), "--env", "live"]
    assert cli.main(["kill", *cd, "--by", "t", "--reason", "x"]) == 0
    assert (tmp_path / "K").exists()
    assert cli.main(["kill", *cd, "--clear"]) == 0
    assert cli.main(["pause", "--bot", "learner", *cd, "--by", "ops"]) == 0
    assert cli.main(["pause", "--bot", "learner", *cd, "--list"]) == 0
    assert '"active": true' in capsys.readouterr().out
    assert cli.main(["pause", "--bot", "learner", *cd, "--clear", "--reason", "manual", "--by", "ops"]) == 0


def test_run_live_requires_confirm_exit_2(tmp_path, monkeypatch):
    for k in ("LIVE_CONFIRM",):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BINANCE_API_KEY", GOOD)
    monkeypatch.setenv("BINANCE_API_SECRET", GOOD)
    d = _live_dir(tmp_path)
    called = []
    a = cli.build_parser().parse_args(["run", "--bot", "learner", "--env", "live", "--config-dir", str(d)])
    assert cli._cmd_run(a, checker=lambda c, k, s: called.append(1)) == cli.EXIT_FAZ_B
    assert not called
    monkeypatch.setenv("LIVE_CONFIRM", "sub-acct-1")
    assert cli._cmd_run(a, checker=lambda c, k, s: called.append(1)) == cli.EXIT_FAZ_B and called == [1]


def test_init_ledger_reconcile_live_config_ok_and_config_error_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LIVE_CONFIRM", raising=False)
    d = _live_dir(tmp_path)
    assert cli.main(["reconcile", "--bot", "learner", "--config-dir", str(d), "--env", "live"]) == cli.EXIT_FAZ_B
    assert "faz_b" in capsys.readouterr().err
    assert cli.main(["init-ledger", "--bot", "learner", "--config-dir", str(d), "--env", "live"]) == 0
    (d / "engine.live.json").write_text(json.dumps({"mode": "live"}))      # live blogu yok => ConfigError
    for cmd in ("init-ledger", "reconcile"):
        assert cli.main([cmd, "--bot", "learner", "--config-dir", str(d), "--env", "live"]) == 2


def test_apply_overrides_backtest_paper_drop_live():
    t = load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json", overlay_path=CFG / "engine.testnet.json")
    assert apply_overrides(t, mode="backtest").live is None
    assert apply_overrides(t, mode="paper").live is None
    assert apply_overrides(t, mode="paper").mode == "paper"


def test_backtest_build_config_under_live_bot_file(tmp_path):
    from trader_engine.backtest import BacktestRunner, BacktestSpec
    d = _live_dir(tmp_path)
    raw = json.loads((d / "engine.learner.json").read_text())
    raw.update({"mode": "live", "live": LIVE, "var_dir": "var-live", "kill_file": "shared/live/KILL",
                "pause_file": "shared/live/PAUSE"})
    (d / "engine.learner.json").write_text(json.dumps(raw))
    from datetime import datetime, timezone
    spec = BacktestSpec(id="t", start=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        end=datetime(2025, 1, 2, tzinfo=timezone.utc), config_dir=str(d))
    cfg = BacktestRunner(spec).build_config()
    assert cfg.mode == "backtest" and cfg.live is None


def test_build_engine_refuses_testnet_live_without_broker(tmp_path):
    from trader_engine.engine import build_engine
    # B4 fix 11 (B4-10): kanonik sira once onay (yalniz live), sonra anahtarlar; "faz_b" sarmalayicisi yok, duz keys_missing
    for m in ("testnet", "live"):
        env = {"LIVE_CONFIRM": LIVE["account_tag"]} if m == "live" else {}
        with pytest.raises(ConfigError, match="keys_missing") as ei:
            build_engine(_base(mode=m, live=LIVE, var_dir=str(tmp_path / "v"), kill_file=str(tmp_path / "k"),
                               pause_file=str(tmp_path / "p")), env=env)
        assert "faz_b" not in str(ei.value)
    with pytest.raises(ConfigError, match="live_confirm"):            # onay anahtarlardan ONCE denetlenir
        build_engine(_base(mode="live", live=LIVE, var_dir=str(tmp_path / "v"), kill_file=str(tmp_path / "k"),
                           pause_file=str(tmp_path / "p")), env={})


def test_entry_leverage_wired(tmp_path):
    from trader_engine import gates
    assert gates.entry_leverage(_base()) == 3
    assert gates.entry_leverage(_base(leverage=4)) == 4
    assert gates.entry_leverage() == LOCKED_CFG.min_leverage


def test_engine_start_prepares_with_cfg_leverage(tmp_path):
    import inspect
    from trader_engine import engine as E
    src = inspect.getsource(E.Engine.start)
    assert "entry_leverage(cfg)" in src and "entry_leverage()" not in src
    import trader_engine.gates as G
    assert "entry_leverage(self.cfg)" in inspect.getsource(G.EntryGate)


def test_testnet_config_env_specific_paths():
    c = load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json", overlay_path=CFG / "engine.testnet.json")
    assert c.kill_file == "shared/testnet/KILL" and c.pause_file == "shared/testnet/PAUSE"


def test_gitignore_has_live_vars():
    t = (ROOT / ".gitignore").read_text().split()
    assert "var-testnet/" in t and "var-live/" in t
