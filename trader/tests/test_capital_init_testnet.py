"""Testnet sermaye kaydi: `capital init-from-exchange` (yalniz testnet, bos gunluk, borsadan okunan bakiye)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from trader_core import risk_ladder as RL
from trader_engine import cli

ROOT = Path(__file__).resolve().parent.parent
INSTALL = (ROOT / "deploy" / "install.sh").read_text(encoding="utf-8")


@pytest.fixture
def proj(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(env, fetch, capsys):
    a = cli.argparse.Namespace(cmd="capital", cap_cmd="init-from-exchange", bot="learner", config_dir="config",
                               env=env, by="kurulum.testnet", note="")
    rc = cli._cmd_capital_from_exchange(a, fetch=fetch)
    return rc, capsys.readouterr()


def _journal(proj):
    return proj / "var-testnet" / "learner" / "risk_ladder.jsonl"


@pytest.mark.parametrize("env", ["live", "paper", None])
def test_env_guard(proj, capsys, env):
    called = []
    rc, out = _run(env, lambda: called.append(1) or 100.0, capsys)
    assert rc != 0 and not called
    assert not _journal(proj).exists()


def test_success_writes_valid_initial(proj, capsys):
    rc, _ = _run("testnet", lambda: 4321.5, capsys)
    assert rc == 0
    rows = RL.LadderLog(str(_journal(proj))).rows()
    assert len(rows) == 1 and rows[0]["kind"] == "initial" and rows[0]["amount"] == 4321.5
    assert "testnet bakiye" in rows[0]["note"]
    st = RL.fold(rows)
    assert st.status == "ok" and st.dep_net == 4321.5


def test_idempotent_existing_journal_untouched(proj, capsys):
    _run("testnet", lambda: 1000.0, capsys)
    before = _journal(proj).read_bytes()
    called = []
    rc, _ = _run("testnet", lambda: called.append(1) or 9999.0, capsys)
    assert rc == 0 and not called and _journal(proj).read_bytes() == before


@pytest.mark.parametrize("bad", ["boom", 0.0, -5.0, float("nan"), float("inf")])
def test_read_failure_or_bad_value_writes_nothing(proj, capsys, bad):
    def fetch():
        if bad == "boom":
            raise ValueError("testnet bakiyesi okunamadi: X")
        return cli._validate_balance(bad) if hasattr(cli, "_validate_balance") else _bad(bad)
    rc, out = _run("testnet", fetch, capsys)
    assert rc != 0 and "hicbir sey yazilmadi" in out.err
    assert not _journal(proj).exists() or _journal(proj).read_bytes() == b""


def _bad(v):
    raise ValueError("testnet bakiyesi pozitif sonlu degil")


@pytest.mark.parametrize("raw,ok", [("123.4", True), ("0", False), ("-1", False), ("nan", False), ("x", False), (None, False)])
def test_balance_reader_validates(monkeypatch, raw, ok):
    from trader_engine.exchange import binance_rest

    class FakeRest:
        def __init__(self, **kw):
            assert kw["env"] == "testnet"

        def sync_time(self):
            return 0

        def account(self):
            return {"totalWalletBalance": raw}
    monkeypatch.setattr(binance_rest, "SignedRestClient", FakeRest)
    monkeypatch.setenv("BINANCE_API_KEY", "a" * 40)
    monkeypatch.setenv("BINANCE_API_SECRET", "b" * 40)
    if ok:
        assert cli._testnet_wallet_balance() == 123.4
    else:
        with pytest.raises(ValueError):
            cli._testnet_wallet_balance()


def test_balance_reader_missing_keys(monkeypatch):
    monkeypatch.delenv("BINANCE_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
    with pytest.raises(ValueError):
        cli._testnet_wallet_balance()


def test_install_step_testnet_only_and_conditional():
    hits = [m.start() for m in re.finditer(r"python3 -m trader_engine capital init-from-exchange", INSTALL)]
    hits = [h for h in hits if "runuser" in INSTALL[INSTALL.rfind("\n", 0, h):h]]     # yalniz calistirilan satir
    assert len(hits) == 1
    t = INSTALL.index("if has_value /etc/trader-testnet.env BINANCE_API_KEY")
    e = INSTALL.index("else echo \"Bilgi: testnet kapali")
    assert t < hits[0] < e                                  # anahtar kosulunun icinde
    line = INSTALL[INSTALL.rfind("\n", 0, hits[0]):INSTALL.index("\n", hits[0])]
    assert "--env testnet" in line and "--env live" not in line and "--env paper" not in line
    assert "capital init-from-exchange" in line and "--by kurulum.testnet" in line
    assert hits[0] < INSTALL.index("enable_now trader-engine-testnet.service")   # motor acilmadan once
    assert "YAPILACAKLAR" in INSTALL and "TESTNET_CAPITAL_WARN" in INSTALL


def test_install_bash_syntax():
    assert subprocess.run(["bash", "-n", str(ROOT / "deploy" / "install.sh")]).returncode == 0
