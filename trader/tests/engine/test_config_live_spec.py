"""WP-B2 (11-canli-broker.md §3, §13 B2): modes, `live` block, LIVE_CONFIRM, leverage lock, live+twin refusal,
keys_missing, exit code 8, paper config unchanged. Written from the spec only; may fail until impl lands."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from trader_core.risk import LOCKED_CFG
from trader_engine.config import EngineConfig, load_engine_config
from trader_engine.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]
CFG_DIR = ROOT / "config"
LIVE_OK = {"account_tag": "sub-acct-01", "expected_wallet_max": 1500.0}
MIN_LEV, MAX_LEV = LOCKED_CFG.min_leverage, LOCKED_CFG.max_leverage


def _write(tmp_path: Path, over: dict, bot: str = "learner") -> tuple[Path, Path]:
    base = json.loads((CFG_DIR / "engine.base.json").read_text())
    if over.get("mode") in ("testnet", "live"):          # DD-8 yol kurali: testnet/live kagit var_dir/KILL/PAUSE yollarini kullanamaz
        base.update(var_dir="var-testnet", kill_file="shared/testnet/KILL", pause_file="shared/testnet/PAUSE")
    base.update(over)
    b = tmp_path / "engine.base.json"
    b.write_text(json.dumps(base))
    p = tmp_path / f"engine.{bot}.json"
    src = CFG_DIR / f"engine.{bot}.json"
    p.write_text(json.dumps(json.loads(src.read_text()) if src.exists() else {"bot": bot}))   # DD-12: engine.twin.json yok; bot="twin" reddedilmeli
    return b, p


def _load(tmp_path, over, bot="learner", env=None, monkeypatch=None):
    # SPEC-AMBIGUOUS: spec says "ortam degiskeni LIVE_CONFIRM" but not how config reads it. load_engine_config has a
    # reserved `env` kwarg at HEAD; we provide the value BOTH via env= and os.environ so either impl passes.
    b, p = _write(tmp_path, over, bot)
    if monkeypatch is not None:
        monkeypatch.delenv("LIVE_CONFIRM", raising=False)
        if env and "LIVE_CONFIRM" in env:
            monkeypatch.setenv("LIVE_CONFIRM", env["LIVE_CONFIRM"])
    return load_engine_config(b, p, env=env if env is not None else {})


# ---------------- modes accepted ----------------

def test_testnet_mode_accepted(tmp_path):
    cfg = _load(tmp_path, {"mode": "testnet", "live": LIVE_OK})
    assert cfg.mode == "testnet"
    assert cfg.live is not None and cfg.live.account_tag == "sub-acct-01"


def test_testnet_veto_off_accepted(tmp_path):
    """DD-12 (veto kaldirildi): testnet veto_mode='off' ile calisir (veto.json gerekmez)."""
    cfg = _load(tmp_path, {"mode": "testnet", "live": LIVE_OK, "veto_mode": "off"})
    assert cfg.mode == "testnet" and cfg.veto_mode == "off"


def test_live_veto_off_accepted(tmp_path, monkeypatch):
    # 23.11 kullanici karari: canli = kagit (LLM veto yok; veto_mode 'off' canlida gecerli)
    cfg = _load(tmp_path, {"mode": "live", "live": LIVE_OK, "veto_mode": "off"}, env={"LIVE_CONFIRM": "sub-acct-01"},
                monkeypatch=monkeypatch)
    assert cfg.mode == "live" and cfg.veto_mode == "off"


def test_live_mode_accepted_with_matching_confirm(tmp_path, monkeypatch):
    cfg = _load(tmp_path, {"mode": "live", "live": LIVE_OK}, env={"LIVE_CONFIRM": "sub-acct-01"}, monkeypatch=monkeypatch)
    assert cfg.mode == "live" and cfg.bot == "learner"


def test_faz_b_refusal_gone(tmp_path):
    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, {"mode": "bogus", "live": LIVE_OK})
    assert "faz_b" not in str(ei.value)


def test_live_settings_defaults(tmp_path):
    s = _load(tmp_path, {"mode": "testnet", "live": LIVE_OK}).live
    assert (s.conditional_mode, s.recv_window_ms, s.poll_open_s, s.poll_flat_s) == ("algo", 5000, 5.0, 30.0)
    assert (s.stop_deadline_s, s.entry_resolve_window_s, s.max_attempts) == (10.0, 60.0, 1)


# ---------------- live block mandatory / forbidden ----------------

@pytest.mark.parametrize("mode", ["testnet", "live"])
def test_live_block_mandatory(tmp_path, monkeypatch, mode):
    with pytest.raises(ConfigError):
        _load(tmp_path, {"mode": mode}, env={"LIVE_CONFIRM": "sub-acct-01"}, monkeypatch=monkeypatch)


@pytest.mark.parametrize("mode", ["paper", "backtest"])
def test_live_block_refused_in_other_modes(tmp_path, mode):
    over = {"mode": mode, "live": LIVE_OK}
    if mode == "backtest":
        over["veto_mode"] = "off"
    with pytest.raises(ConfigError):
        _load(tmp_path, over)


@pytest.mark.parametrize("bad", [
    {"account_tag": "AB"}, {"account_tag": "x" * 33}, {"account_tag": "Has_Upper"}, {"account_tag": "sp ace"},
    {"expected_wallet_max": 0}, {"expected_wallet_max": -1},
    {"recv_window_ms": 999}, {"recv_window_ms": 10001},
    {"poll_open_s": 0.5}, {"poll_open_s": 16}, {"poll_flat_s": 4}, {"poll_flat_s": 121},
    {"stop_deadline_s": 4}, {"stop_deadline_s": 15.5},   # upper bound 15: cannot be loosened
    {"max_attempts": 0}, {"max_attempts": 3},
])
def test_live_settings_ranges_refused(tmp_path, bad):
    with pytest.raises(ConfigError):
        _load(tmp_path, {"mode": "testnet", "live": {**LIVE_OK, **bad}})


@pytest.mark.parametrize("good", [{"stop_deadline_s": 5}, {"stop_deadline_s": 15}, {"poll_open_s": 1}, {"poll_open_s": 15},
                                  {"poll_flat_s": 5}, {"poll_flat_s": 120}, {"recv_window_ms": 1000},
                                  {"recv_window_ms": 10000}, {"max_attempts": 2}])
def test_live_settings_range_edges_accepted(tmp_path, good):
    assert _load(tmp_path, {"mode": "testnet", "live": {**LIVE_OK, **good}}).live is not None


# ---------------- LIVE_CONFIRM ----------------

@pytest.mark.parametrize("confirm", ["other-acct-1", "SUB-ACCT-01", "sub-acct-01 ", ""])
def test_live_confirm_mismatch_refused(tmp_path, monkeypatch, confirm):
    with pytest.raises(ConfigError) as ei:
        _load(tmp_path, {"mode": "live", "live": LIVE_OK}, env={"LIVE_CONFIRM": confirm}, monkeypatch=monkeypatch)
    assert "live_confirm" in str(ei.value)
    assert confirm not in str(ei.value) or confirm == ""       # value must not be logged/echoed


def test_live_confirm_missing_refused(tmp_path, monkeypatch):
    with pytest.raises(ConfigError, match="live_confirm"):
        _load(tmp_path, {"mode": "live", "live": LIVE_OK}, env={}, monkeypatch=monkeypatch)


def test_live_confirm_not_required_on_testnet(tmp_path, monkeypatch):
    # SPEC-AMBIGUOUS: spec says double confirm is "yalniz mode=live"; assume testnet ignores LIVE_CONFIRM.
    assert _load(tmp_path, {"mode": "testnet", "live": LIVE_OK}, env={}, monkeypatch=monkeypatch).mode == "testnet"


# ---------------- leverage lock range ----------------

def test_leverage_default_is_locked_min(tmp_path):
    assert _load(tmp_path, {}).leverage == MIN_LEV == 3


@pytest.mark.parametrize("lev", range(MIN_LEV, MAX_LEV + 1))
def test_leverage_inside_range_accepted(tmp_path, lev):
    assert _load(tmp_path, {"leverage": lev}).leverage == lev


@pytest.mark.parametrize("lev", [MIN_LEV - 1, 0, -3, MAX_LEV + 1, 125, 3.5, "3", None, True])
def test_leverage_outside_lock_range_refused(tmp_path, lev):
    with pytest.raises(ConfigError):
        _load(tmp_path, {"leverage": lev})


def test_leverage_checked_for_testnet_too(tmp_path):
    with pytest.raises(ConfigError):
        _load(tmp_path, {"mode": "testnet", "live": LIVE_OK, "leverage": MAX_LEV + 1})


# ---------------- live + twin, other live rules ----------------

@pytest.mark.parametrize("mode", ["live"])
def test_live_with_twin_refused(tmp_path, monkeypatch, mode):
    with pytest.raises(ConfigError):
        _load(tmp_path, {"mode": mode, "live": LIVE_OK}, bot="twin", env={"LIVE_CONFIRM": "sub-acct-01"},
              monkeypatch=monkeypatch)


def test_twin_overlay_rejected_everywhere(tmp_path):
    """DD-12: ikiz kaldirildi; engine.twin.json yok ve bot="twin" her kipte ConfigError."""
    assert not (CFG_DIR / "engine.twin.json").exists()
    with pytest.raises(ConfigError):
        _load(tmp_path, {}, bot="twin")


def test_live_veto_required_still_valid(tmp_path, monkeypatch):
    # 23.11 kullanici karari: canli = kagit (veto 'off' artik gecerli; 'required' da gecerli kalir)
    cfg = _load(tmp_path, {"mode": "live", "live": LIVE_OK, "veto_mode": "required"}, env={"LIVE_CONFIRM": "sub-acct-01"},
                monkeypatch=monkeypatch)
    assert cfg.veto_mode == "required"


def test_live_requires_mark_trigger(tmp_path, monkeypatch):
    cost = json.loads((CFG_DIR / "engine.base.json").read_text())["cost"]
    cost["trigger_source"] = "last"
    cost["granularity"] = "15m"          # "last" is only valid with 15m in the existing cost rules
    with pytest.raises(ConfigError):
        _load(tmp_path, {"mode": "live", "live": LIVE_OK, "cost": cost}, env={"LIVE_CONFIRM": "sub-acct-01"},
              monkeypatch=monkeypatch)


def test_unknown_live_key_refused(tmp_path):
    # SPEC-AMBIGUOUS: unknown keys inside `live` assumed refused (existing config style is strict).
    with pytest.raises(ConfigError):
        _load(tmp_path, {"mode": "testnet", "live": {**LIVE_OK, "base_url": "https://fapi.binance.com"}})


def test_base_url_not_configurable():
    # spec: taban adresleri yapilandirmada YOKTUR
    import dataclasses
    from trader_engine.config import LiveSettings
    names = {f.name for f in dataclasses.fields(LiveSettings)} | {f.name for f in dataclasses.fields(EngineConfig)}
    assert not {n for n in names if "url" in n or "base" in n}


# ---------------- keys: load_keys ----------------

def _load_keys():
    # SPEC-AMBIGUOUS: module of `load_keys` not stated in §3.2; look in config and the REST client module.
    for mod in ("trader_engine.config", "trader_engine.exchange.binance_rest"):
        try:
            fn = getattr(importlib.import_module(mod), "load_keys", None)
        except ImportError:
            fn = None
        if fn:
            return fn
    pytest.fail("load_keys not found (config.py / exchange/binance_rest.py)")


K32 = "k" * 32
S40 = "s" * 40


def test_load_keys_ok():
    assert _load_keys()({"BINANCE_API_KEY": K32, "BINANCE_API_SECRET": S40}) == (K32, S40)


@pytest.mark.parametrize("env", [
    {}, {"BINANCE_API_KEY": K32}, {"BINANCE_API_SECRET": S40},
    {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": S40},
    {"BINANCE_API_KEY": K32, "BINANCE_API_SECRET": ""},
    {"BINANCE_API_KEY": "k" * 31, "BINANCE_API_SECRET": S40},       # shorter than 32
    {"BINANCE_API_KEY": K32, "BINANCE_API_SECRET": "s" * 31},
    {"BINANCE_API_KEY": "k" * 16 + " " + "k" * 20, "BINANCE_API_SECRET": S40},  # contains whitespace
    {"BINANCE_API_KEY": K32, "BINANCE_API_SECRET": "s" * 20 + "\n" + "s" * 20},
])
def test_load_keys_missing_or_bad(env):
    with pytest.raises(ConfigError, match="keys_missing") as ei:
        _load_keys()(env)
    msg = str(ei.value)
    for v in env.values():
        if v and len(v) >= 31:
            assert v not in msg                 # no value in message, variable name only


def test_load_keys_boundary_32_ok():
    assert _load_keys()({"BINANCE_API_KEY": "a" * 32, "BINANCE_API_SECRET": "b" * 32}) == ("a" * 32, "b" * 32)


def test_keys_not_in_config_json():
    for f in CFG_DIR.glob("engine*.json"):
        t = f.read_text().upper()
        assert "BINANCE_API" not in t and "SECRET" not in t


# ---------------- exit code 8 ----------------

class _Clock:
    def now(self):
        from datetime import datetime, timezone
        return datetime(2026, 12, 28, 9, 0, tzinfo=timezone.utc)


class _FakeRest:
    """Injectable REST double for startup_check (spec §3.4). Unlisted calls return benign defaults."""

    def __init__(self, restrictions, *, raises=None):
        self._r, self._raises, self.calls = restrictions, raises, []

    def sync_time(self):
        self.calls.append("sync_time")
        return 0

    def health(self):
        return {"clock_offset_ms": 0}

    def api_restrictions(self):
        self.calls.append("api_restrictions")
        if self._raises:
            raise self._raises
        return self._r

    def account(self):
        return {"canTrade": True, "totalWalletBalance": "10", "totalUnrealizedProfit": "0",
                "totalMarginBalance": "10", "totalInitialMargin": "0", "availableBalance": "10"}

    def multi_assets(self):
        return False

    def position_mode(self):
        return False

    def position_risk(self, symbol=None):
        return []

    def open_orders(self, symbol=None):
        return []

    def exchange_info(self):
        return {"symbols": []}

    def __getattr__(self, name):          # any other call: harmless no-op
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: None


GOOD_RESTR = {"enableReading": True, "enableFutures": True, "enableWithdrawals": False,
              "enableInternalTransfer": False, "permitsUniversalTransfer": False, "ipRestrict": True}


def _broker(env, rest, tmp_path):
    from trader_engine.brokers.binance_futures import LiveBroker   # WP-B3 dependency
    cfg = _load(tmp_path, {"mode": env, "live": LIVE_OK}, env={"LIVE_CONFIRM": LIVE_OK["account_tag"]})
    return LiveBroker(cfg.live, env, cfg.leverage, cfg.pairs, rest, _Clock(), cfg.cost.taker_fee)


@pytest.mark.parametrize("field,val", [
    ("enableWithdrawals", True), ("enableInternalTransfer", True), ("permitsUniversalTransfer", True),
    ("ipRestrict", False), ("enableReading", False), ("enableFutures", False),
])
def test_live_startup_permission_failure_exits_8(tmp_path, field, val):
    from trader_engine.engine import EngineExit
    rest = _FakeRest({**GOOD_RESTR, field: val})
    with pytest.raises(EngineExit) as ei:
        _broker("live", rest, tmp_path).startup_check()
    assert ei.value.code == 8
    assert f"key_permission:{field}" in str(ei.value)


def test_live_startup_unverifiable_permissions_exit_8(tmp_path, monkeypatch):
    from trader_engine.engine import EngineExit
    monkeypatch.delenv("LIVE_PERMISSION_ATTESTED", raising=False)
    for rest in (_FakeRest({}), _FakeRest({"unexpected": 1}), _FakeRest(None, raises=RuntimeError("no endpoint"))):
        with pytest.raises(EngineExit) as ei:
            _broker("live", rest, tmp_path).startup_check()
        assert ei.value.code == 8
        assert "key_permission_unverifiable" in str(ei.value)


def test_testnet_skips_permission_check(tmp_path):
    pytest.importorskip("trader_engine.brokers.binance_futures")   # WP-B3 gelene kadar atla (bos gecmesin)
    rest = _FakeRest({**GOOD_RESTR, "enableWithdrawals": True})
    try:
        _broker("testnet", rest, tmp_path).startup_check()
    except Exception as e:           # later steps may fail on the thin fake; only exit-8/permission would be a bug
        assert getattr(e, "code", None) != 8 and "key_permission" not in str(e)
    assert "api_restrictions" not in rest.calls


def test_live_wallet_above_expected_is_a_finding_not_an_exit(tmp_path):
    """DD-8 O4 ile degisti (eski: EngineExit(8, wallet_above_expected)): tavan asimi acilisi DURDURMAZ; bulgu `startup_findings`te,
    motor `start()`ta giris tutusu ekler. Okunamayan bakiye (alan yok) hala cikis 8 `wallet_unreadable`."""
    from trader_engine.engine import EngineExit
    rest = _FakeRest(GOOD_RESTR)
    rest.account = lambda: {"canTrade": True, "totalWalletBalance": str(LIVE_OK["expected_wallet_max"] + 1)}
    b = _broker("live", rest, tmp_path)
    try:
        b.startup_check()
    except EngineExit as e:               # ince sahte: sonraki adimlar (kural/kaldirac) tavandan bagimsiz takilabilir
        assert "wallet_above_expected" not in str(e)
    assert b.startup_findings == ("wallet_above_expected",)
    rest2 = _FakeRest(GOOD_RESTR)
    rest2.account = lambda: {"canTrade": True}
    with pytest.raises(EngineExit) as ei:
        _broker("live", rest2, tmp_path).startup_check()
    assert ei.value.code == 8 and "wallet_unreadable" in str(ei.value)


def test_cli_run_returns_8_on_exchange_exit(tmp_path, monkeypatch, capsys):
    """cli `run` maps EngineExit(8, ...) (raised while building/starting the live engine) to process exit code 8."""
    import trader_engine.cli as cli
    import trader_engine.engine as eng
    monkeypatch.setattr(eng, "build_engine", lambda cfg: (_ for _ in ()).throw(eng.EngineExit(8, "key_permission:ipRestrict")))
    b, p = _write(tmp_path, {"mode": "testnet", "live": LIVE_OK})
    monkeypatch.setenv("BINANCE_API_KEY", K32)          # SPEC-AMBIGUOUS: cli may read keys from os.environ before build
    monkeypatch.setenv("BINANCE_API_SECRET", S40)
    rc = cli.main(["run", "--bot", "learner", "--config-dir", str(tmp_path)])
    assert rc == 8


def test_cli_exit_code_constant_and_legacy_codes():
    import trader_engine.cli as cli
    # SPEC-AMBIGUOUS: constant name for 8 not given; accept any module-level int constant equal to 8.
    assert 8 in {v for k, v in vars(cli).items() if k.startswith("EXIT_") and isinstance(v, int)}
    assert (cli.EXIT_OK, cli.EXIT_FAZ_B, cli.EXIT_REPEATED, cli.EXIT_ENGINE, cli.EXIT_FINDINGS) == (0, 2, 3, 4, 5)


def test_cli_live_confirm_mismatch_exits_2(tmp_path, monkeypatch):
    import trader_engine.cli as cli
    _write(tmp_path, {"mode": "live", "live": LIVE_OK})
    monkeypatch.setenv("LIVE_CONFIRM", "wrong-tag-x")
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(tmp_path)]) == 2


# ---------------- paper config unchanged ----------------

_FROM_JSON = ("wallet_start", "stale_factor", "loop_sleep_s", "bar_wait_s", "minute_wait_s", "reconcile_open_s",
              "reconcile_flat_s", "start_delay_s", "var_dir", "market_db", "history_dir", "veto_config", "kill_file",
              "strategy", "target_trade_risk", "target_mode", "veto_mode",
              "record_filtered_candidates")


@pytest.mark.parametrize("bot,start_delay", [("learner", 0.0)])
def test_paper_config_loads_unchanged(bot, start_delay):
    cfg = load_engine_config(CFG_DIR / "engine.base.json", CFG_DIR / f"engine.{bot}.json")
    raw = json.loads((CFG_DIR / "engine.base.json").read_text())
    assert cfg.mode == "paper" and cfg.bot == bot and cfg.schema == "engine/1"
    for k in _FROM_JSON:
        if k == "start_delay_s":
            assert cfg.start_delay_s == start_delay
        else:
            assert getattr(cfg, k) == raw[k], k
    assert cfg.pairs == tuple(raw["pairs"])
    assert (cfg.cost.fill_model, cfg.cost.taker_fee, cfg.cost.slip_entry_bps, cfg.cost.slip_exit_bps,
            cfg.cost.slip_stop_bps, cfg.cost.trigger_source, cfg.cost.granularity) == ("native", 0.0005, 2.0, 2.0, 5.0, "mark", "1m")
    assert cfg.target_trade_risk == 0.005 and cfg.startup_wait_s == 600.0
    # new fields default so paper behaviour is unchanged
    assert cfg.leverage == 3 and cfg.live is None and cfg.pause_file == "shared/PAUSE"
    assert cfg.risk_config.min_leverage == 3
    assert cfg.ledger_path == f"var/{bot}/ledger.sqlite" and cfg.state_path == f"var/{bot}/state.sqlite"


def test_paper_accepts_veto_off_and_still_refuses_unknown_keys(tmp_path):
    """DD-12 WP-06a: kagitta veto yok -> veto_mode='off' gecerli (testnet/canli icin hala yasak: ayri testler)."""
    assert _load(tmp_path, {"veto_mode": "off"}).veto_mode == "off"
    with pytest.raises(ConfigError):
        _load(tmp_path, {"nonsense_key": 1})


def test_paper_entry_leverage_equals_cfg_leverage():
    # spec §3.1: entry_leverage() (gates) returns cfg.leverage; default 3 => unchanged paper results
    from trader_engine import gates
    cfg = load_engine_config(CFG_DIR / "engine.base.json", CFG_DIR / "engine.learner.json")
    fn = getattr(gates, "entry_leverage", None)
    assert fn is not None
    # SPEC-AMBIGUOUS: spec says entry_leverage() "returns cfg.leverage" without a signature; accept (cfg) or ().
    try:
        got = fn(cfg)
    except TypeError:
        got = fn()
    assert got == cfg.leverage == 3
