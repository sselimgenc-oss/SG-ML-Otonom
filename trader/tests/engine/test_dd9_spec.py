"""DD-9 (canli paket ve kurulum sertlestirme) bagimsiz sartname testleri: docs/dd9-canli-paket-spec.md (v1, 18 Kasim 2026).

Bagimsiz test ajani; yalniz sartnameden (dosya/ortam/anahtar/hata kodu/cikis kodu/islev imzasi adlari), COMMITTED koddan (HEAD) ve
mevcut test duzeneklerinden (test_dd8_spec, test_telegram_spec, test_wp_b8, readiness_support yontemleri) yazildi. Gerceklemenin
(src/, scripts/, deploy/ calisma agaci) taslak farklarina BAKILMADI. Gercek ag/saat/systemctl/sudo yok: deploy testleri yalniz
dosya ayrisitirir, birimleri `render()` ile uretir ve install.sh islevlerini tmp dizinlerde calistirir.

Dosya yeri: sartname §10 "Test dosyalari" iki dosya (tests/engine/test_dd9_spec.py + tests/test_dd9_deploy_spec.py) der; istek
uzerine TUM sartname testleri bu TEK dosyadadir. Adlandirma: test_<bolum>_<no>_...  (D1-1 -> test_d1_01_...).

Yeni modulleri (`trader_core.live_paths`, `proc_guard`, `scripts/live_preflight.py`, `ledger.peek_meta`, ...) testler FONKSIYON ICINDE
iceri alir: gerceklenmemisse yalniz o test basarisiz olur, toplama hatasi olmaz.

`# SPEC-AMBIGUOUS:` ile isaretli yerler sartnamenin adlandirmadigi noktalardaki tahminlerdir (ozet: dosya sonundaki liste).
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import logging
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import textwrap
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import test_dd8_spec as D8
from fake_exchange import KEY, SECRET, FakeExchange, FakeResp
from test_dd8_spec import denv_factory, boots  # noqa: F401  (fikstur)

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
DEPLOY = ROOT / "deploy"
CONFIG = ROOT / "config"
for _p in (str(SRC), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

SERVER_TRADER_DIR = "/home/trader/SG-Github-AB-proje/trader"      # render testi yalniz metin uretir; bu yol gercekte yoktur
ROOT_DIR = "/usr/local/lib/trader-root"
NOW = datetime(2026, 12, 20, 12, 0, tzinfo=UTC)
LIVE_TAG = "canli-alt1"
HEX40 = "0123456789abcdef0123456789abcdef01234567"


# ====================================================================================== ortak yardimcilar
def load_script(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_dd9s", SCRIPTS / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def z(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def read(p) -> str:
    return Path(p).read_text(encoding="utf-8")


def noncomment(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def parse_unit(text: str) -> list[tuple[str, str, str]]:
    """Birim dosyasi -> [(bolum, anahtar, deger)] (yorum/bos satirsiz, dosya sirasiyla)."""
    sec, out = "", []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(("#", ";")):
            continue
        if s.startswith("[") and s.endswith("]"):
            sec = s[1:-1]
            continue
        if "=" in s:
            k, _, v = s.partition("=")
            out.append((sec, k.strip(), v.strip()))
    return out


def unit_get(text: str, key: str) -> list[str]:
    return [v for _s, k, v in parse_unit(text) if k == key]


def install_text() -> str:
    return read(DEPLOY / "install.sh")


def extract_fn(text: str, name: str) -> str:
    """install.sh'teki `name() {` islevini (tek satirlik ya da `^}` ile biten) aynen dondurur."""
    m = re.search(rf"^{re.escape(name)}\(\)\s*\{{.*$", text, re.M)
    assert m, f"install.sh icinde {name}() bulunamadi"
    first = m.group(0)
    if first.rstrip().endswith("}"):
        return first
    end = re.compile(r"^\}", re.M).search(text, m.end())
    assert end, f"{name}() kapanisi bulunamadi"
    return text[m.start():end.end()]


def has_fn(text: str, name: str) -> bool:
    return re.search(rf"^{re.escape(name)}\(\)\s*\{{", text, re.M) is not None


def bash(script: str, *, env: dict | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.pop("COMMIT", None)
    e.update(env or {})
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=e, timeout=timeout)


def render_units(out_dir: Path, trader_dir: str = SERVER_TRADER_DIR) -> dict[str, str]:
    """install.sh'in GERCEK `render()` islevini calistirip tum trader-*.service/.timer birimlerini out_dir'e yazar."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fn = extract_fn(install_text(), "render")
    script = (f"set -euo pipefail\nTRADER_DIR={shlex_q(trader_dir)}\n{fn}\n"
              f"for f in {shlex_q(str(DEPLOY))}/trader-*.service {shlex_q(str(DEPLOY))}/trader-*.timer; do\n"
              f"  render \"$f\" {shlex_q(str(out_dir))}/\"$(basename \"$f\")\"\ndone\n")
    r = bash(script)
    assert r.returncode == 0, r.stderr
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(out_dir.iterdir())}


def shlex_q(s: str) -> str:
    import shlex
    return shlex.quote(s)


def copy_config(root: Path, cname: str = "config") -> Path:
    cdir = root / cname
    shutil.copytree(CONFIG, cdir)
    return cdir


def stdlib_only(path: Path) -> list[str]:
    """Dosyadaki (islev ici dahil) tum ice aktarmalar stdlib mi? Degilse ihlal listesi."""
    bad = []
    for n in ast.walk(ast.parse(read(path))):
        if isinstance(n, ast.Import):
            mods = [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                bad.append(f"goreli ice aktarma: {n.module}")
                continue
            mods = [n.module or ""]
        else:
            continue
        for m in mods:
            if m.split(".")[0] not in sys.stdlib_module_names:
                bad.append(m)
    return bad


def patch_proc_guard(mp, ret=True, counter: list | None = None):
    """`trader_core.proc_guard.set_nondumpable`i yamar (gercek prctl test surecini etkilemesin). Modul yoksa yamasiz gecer."""
    try:
        import trader_core.proc_guard as PG
    except ImportError:
        return None

    def fake():
        if counter is not None:
            counter.append(1)
        return ret
    mp.setattr(PG, "set_nondumpable", fake)
    return PG


# ====================================================================================== K: config/engine.live.json
def load_live(cdir=None):
    from trader_engine.config import load_cli_config
    return load_cli_config(str(cdir or CONFIG), "learner", env="live")


def test_k_01_live_layer_loads_with_fixed_contract_values():
    from trader_core.risk import LOCKED_CFG
    cfg = load_live()
    r = str(ROOT)
    assert cfg.mode == "live"
    assert cfg.var_dir == f"{r}/var-live"
    assert cfg.kill_file == f"{r}/shared/live/KILL"
    assert cfg.pause_file == f"{r}/shared/live/PAUSE"
    assert cfg.live.account_tag == "canli-alt1"
    assert cfg.live.expected_wallet_max == 2000.0   # 23.11 kullanici karari (d): 1500 -> 2000
    assert cfg.live.max_attempts == 1
    assert cfg.leverage == LOCKED_CFG.min_leverage
    assert cfg.cost.trigger_source == "mark"


def test_k_02_live_json_exact_key_sets():
    live = json.loads(read(CONFIG / "engine.live.json"))
    testnet = json.loads(read(CONFIG / "engine.testnet.json"))
    # 23.11 kullanici karari: canli = kagit (kagit sistem anahtarlari eklendi; ayrinti: test_canli_kagit_parite.py)
    assert set(live) == {"mode", "var_dir", "kill_file", "pause_file", "live", "pairs", "optional_pairs", "strategy", "arms",
                         "shadow_blocks", "exit_modes", "max_positions", "target_trade_risk", "risk",
                         "clusters", "etiket_kurallari", "flat_bar_guard", "contract_types", "cost_overrides",
                         "target_mode"}   # 24.11 kullanici karari: hedef bekleyen emir (kagitla ayni "resting")
    assert set(live["live"]) == set(testnet["live"])


def test_k_03_live_block_differs_from_testnet_only_in_tag_and_wallet_max():
    live = json.loads(read(CONFIG / "engine.live.json"))["live"]
    testnet = json.loads(read(CONFIG / "engine.testnet.json"))["live"]
    diff = {k for k in set(live) | set(testnet) if live.get(k) != testnet.get(k)}
    assert diff == {"account_tag", "expected_wallet_max"}


def test_k_04_twin_cannot_use_live_layer():
    from trader_engine.config import load_cli_config
    from trader_engine.errors import ConfigError
    with pytest.raises(ConfigError):
        load_cli_config(str(CONFIG), "twin", env="live")


def test_k_05_build_engine_live_requires_confirm_then_keys_with_zero_http(monkeypatch):
    from trader_engine import engine as E
    from trader_engine.errors import ConfigError
    ex = FakeExchange(lambda: 1_800_000_000_000)
    D8.patch_rest(monkeypatch, ex)
    cfg = load_live()
    with pytest.raises(ConfigError) as ei:
        E.build_engine(cfg, env={})
    assert "live_confirm" in str(ei.value)
    with pytest.raises(ConfigError) as ei:
        E.build_engine(cfg, env={"LIVE_CONFIRM": "canli-alt1"})
    assert str(ei.value).startswith("keys_missing")
    assert ex.requests == []


def test_k_06_paper_load_is_unaffected_by_live_file_presence(tmp_path):
    from trader_engine.config import load_cli_config
    a = copy_config(tmp_path / "a")
    b = copy_config(tmp_path / "b")
    (b / "engine.live.json").unlink(missing_ok=True)
    ca = dataclasses.asdict(load_cli_config(str(a), "learner"))
    cb = dataclasses.asdict(load_cli_config(str(b), "learner"))
    sa = json.dumps(ca, sort_keys=True, default=str).replace(str(tmp_path / "a"), "@ROOT@")
    sb = json.dumps(cb, sort_keys=True, default=str).replace(str(tmp_path / "b"), "@ROOT@")
    assert sa == sb
    assert ca["mode"] == "paper"


# ====================================================================================== U: --ensure-ledger (U-1..U-4)
def _cli_run(cdir, env, extra=()):
    from trader_engine import cli
    return cli.main(["run", "--bot", "learner", "--env", env, "--config-dir", str(cdir), *extra])


@pytest.fixture
def run_env(monkeypatch):
    """cli.run icin: anahtarlar, sahte borsa, build_engine yerine sayac, sinyal isleyicisi/proc_guard etkisiz."""
    from trader_engine import cli
    from trader_engine import engine as E
    ex = FakeExchange(lambda: 1_800_000_000_000)
    D8.patch_rest(monkeypatch, ex)
    monkeypatch.setenv("BINANCE_API_KEY", KEY)
    monkeypatch.setenv("BINANCE_API_SECRET", SECRET)
    monkeypatch.delenv("LIVE_CONFIRM", raising=False)
    monkeypatch.setattr(cli.signal, "signal", lambda *a, **k: None)
    calls: list = []

    class Eng:
        def run_forever(self):
            return None

        def stop(self):
            return None

    def fake_build(cfg, **kw):
        calls.append(cfg)
        return Eng()
    monkeypatch.setattr(E, "build_engine", fake_build)
    patch_proc_guard(monkeypatch, True)
    return types.SimpleNamespace(ex=ex, build_calls=calls)


def test_u_01_ensure_ledger_foreign_stamp_exits_8_without_build_or_http(tmp_path, monkeypatch, run_env):
    cdir, _ = D8.make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    cfg = D8.cli_cfg(cdir, "testnet")
    D8.seed_ledger(cfg.ledger_path, stamp="live:x")
    n0 = D8.count_rows(cfg.ledger_path, "param_versions")
    assert _cli_run(cdir, "testnet", ["--ensure-ledger"]) == 8
    assert run_env.build_calls == []
    assert run_env.ex.requests == []
    assert D8.count_rows(cfg.ledger_path, "param_versions") == n0


def test_u_02_ensure_ledger_creates_ledger_once_and_is_idempotent(tmp_path, monkeypatch, run_env):
    from trader_core import ledger as L
    cdir, _ = D8.make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    cfg = D8.cli_cfg(cdir, "testnet")
    assert not Path(cfg.ledger_path).exists()
    assert _cli_run(cdir, "testnet", ["--ensure-ledger"]) == 0
    assert len(run_env.build_calls) == 1
    led = L.open_ledger(cfg.ledger_path, "learner", create=False, read_only=True)
    try:
        led.get_active_params()                     # etkin parametre var (istisna yok)
    finally:
        led.close()
    n1 = D8.count_rows(cfg.ledger_path, "param_versions")
    assert n1 >= 1
    assert _cli_run(cdir, "testnet", ["--ensure-ledger"]) == 0
    assert len(run_env.build_calls) == 2
    assert D8.count_rows(cfg.ledger_path, "param_versions") == n1


def test_u_03_without_flag_run_does_not_do_init_ledger_work(tmp_path, monkeypatch, run_env):
    cdir, _ = D8.make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    cfg = D8.cli_cfg(cdir, "testnet")
    assert _cli_run(cdir, "testnet") == 0
    assert len(run_env.build_calls) == 1
    assert not Path(cfg.ledger_path).exists(), "bayraksiz run init-ledger isi yapti"


def test_u_04_missing_keys_with_ensure_ledger_exit_2_and_no_ledger_file(tmp_path, monkeypatch, run_env):
    cdir, _ = D8.make_tree(tmp_path, "testnet")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BINANCE_API_KEY")
    monkeypatch.delenv("BINANCE_API_SECRET")
    cfg = D8.cli_cfg(cdir, "testnet")
    assert _cli_run(cdir, "testnet", ["--ensure-ledger"]) == 2
    assert not Path(cfg.ledger_path).exists(), "anahtar denetiminden once defter olusturuldu"
    assert run_env.build_calls == [] and run_env.ex.requests == []


# ====================================================================================== U: birimler (U-5..U-11)
LIVE_UNIT, TESTNET_UNIT = DEPLOY / "trader-engine-live.service", DEPLOY / "trader-engine-testnet.service"
DIFF_KEYS = {"Description", "ConditionPathExists", "ExecStart", "ReadWritePaths", "MemoryHigh", "MemoryMax", "OOMScoreAdjust", "Nice"}
HARDENING = [("ProtectProc", "invisible"), ("ProtectKernelTunables", "true"), ("ProtectKernelModules", "true"),
             ("ProtectControlGroups", "true"), ("RestrictSUIDSGID", "true"), ("LockPersonality", "true"),
             ("RestrictNamespaces", "true"), ("CapabilityBoundingSet", ""),
             ("RestrictAddressFamilies", "AF_INET AF_INET6 AF_UNIX")]


def _parity_rows(path: Path):
    rows, seen_envfile = [], False
    for sec, k, v in parse_unit(read(path)):
        if k == "EnvironmentFile" and not seen_envfile:
            seen_envfile = True                          # ilk EnvironmentFile (anahtar dosyasi) farkli olabilir
            continue
        if k in DIFF_KEYS:
            continue
        rows.append((sec, k, v))
    return rows


def test_u_05_live_and_testnet_units_are_identical_except_difference_keys():
    assert LIVE_UNIT.exists(), "deploy/trader-engine-live.service yok"
    assert _parity_rows(LIVE_UNIT) == _parity_rows(TESTNET_UNIT)


@pytest.mark.parametrize("unit,env", [(LIVE_UNIT, "live"), (TESTNET_UNIT, "testnet")])
def test_u_06_unit_restart_and_hardening_contract(unit, env):
    text = read(unit)
    assert "init-ledger" not in noncomment(text)             # SPEC-AMBIGUOUS: yalniz yorum disi satirlar
    exec_start = unit_get(text, "ExecStart")
    assert len(exec_start) == 1 and exec_start[0].endswith("--ensure-ledger")
    assert exec_start[0] == f"/usr/bin/python3 -m trader_engine run --bot learner --env {env} --config-dir config --ensure-ledger"
    assert unit_get(text, "StartLimitIntervalSec") == ["0"]
    assert unit_get(text, "StartLimitBurst") == []
    assert unit_get(text, "RestartPreventExitStatus") == ["2 7 8"]
    assert unit_get(text, "Restart") == ["on-failure"]
    assert (unit_get(text, "RestartSec"), unit_get(text, "RestartSteps"), unit_get(text, "RestartMaxDelaySec")) == (["5"], ["5"], ["120"])
    rows = {(k, v) for _s, k, v in parse_unit(text)}
    for kv in HARDENING:
        assert kv in rows, kv
    for k in ("OnFailure",):
        assert unit_get(text, k) == ["trader-health-fail@%n.service"]
    assert ("Service", "Slice", "trader.slice") in parse_unit(text)
    assert unit_get(text, "User") == ["trader"] and unit_get(text, "Group") == ["trader"]
    assert unit_get(text, "Type") == ["simple"]
    assert "Conflicts" not in {k for _s, k, _v in parse_unit(text)}
    assert unit_get(text, "ConditionPathExists") == [f"/etc/trader-{env}.env"]
    assert unit_get(text, "EnvironmentFile")[0] == f"/etc/trader-{env}.env"
    assert "/etc/trader-veto-hmac.env" not in unit_get(text, "EnvironmentFile")      # 24.11: AI veto artiklari silindi


def test_u_06b_unit_difference_rows_per_spec_table():
    live, tn = read(LIVE_UNIT), read(TESTNET_UNIT)
    assert "CANLI" in unit_get(live, "Description")[0]
    assert (unit_get(tn, "MemoryHigh"), unit_get(tn, "MemoryMax"), unit_get(tn, "Nice"), unit_get(tn, "OOMScoreAdjust")) == (["250M"], ["320M"], ["10"], [])
    assert (unit_get(live, "MemoryHigh"), unit_get(live, "MemoryMax"), unit_get(live, "Nice"), unit_get(live, "OOMScoreAdjust")) == (["600M"], ["750M"], ["5"], ["-300"])   # 23.11 kullanici karari: canli = kagit (kagit motoruyla ayni bellek tavani)
    assert unit_get(live, "ReadWritePaths") == ["/opt/trader/var /opt/trader/var-live /opt/trader/shared /opt/trader/user_data"]
    assert unit_get(tn, "ReadWritePaths") == ["/opt/trader/var /opt/trader/var-testnet /opt/trader/shared /opt/trader/user_data"]
    # ExecStartPre: yalniz market.sqlite bekleme satiri
    for t in (live, tn):
        pre = unit_get(t, "ExecStartPre")
        assert len(pre) == 1 and "market.sqlite" in pre[0]


def test_u_07_units_never_mix_testnet_and_live_key_files():
    live, tn = read(LIVE_UNIT), read(TESTNET_UNIT)
    assert "trader-testnet.env" not in live and "--env testnet" not in live
    assert "trader-live.env" not in tn and "LIVE_CONFIRM" not in tn and "--env live" not in tn
    for p in DEPLOY.glob("*.service"):
        assert "BINANCE_API_KEY=" not in noncomment(read(p)), p.name
        assert "BINANCE_API_SECRET=" not in noncomment(read(p)), p.name


def test_u_08_render_resolves_paths_for_both_units(tmp_path):
    rendered = render_units(tmp_path / "u")
    for name, env in (("trader-engine-live.service", "live"), ("trader-engine-testnet.service", "testnet")):
        txt = rendered[name]
        assert "/opt/trader" not in txt and "/usr/bin/python3" not in txt, name
        exe = unit_get(txt, "ExecStart")[0]
        assert f"{SERVER_TRADER_DIR}/.venv/bin/python -m trader_engine run --bot learner --env {env}" in exe


def _git_base(rel: str) -> str | None:
    for rev in ("0f2ef52", "HEAD"):
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:./{rel}"], capture_output=True)
        if r.returncode == 0:
            return r.stdout.decode("utf-8")
    return None


def test_u_09_paper_engine_unit_differs_from_base_commit_only_by_dd12_changes():
    """DD-12 WP-07: kagit motor birimi yalniz `--env paper` ve bellek tavanlari (600M/750M) ile tabandan ayrilir (yorum satirlari haric)."""
    base = _git_base("deploy/trader-engine@.service")
    if base is None:
        pytest.skip("git/taban commit yok")
    want = (base.replace("--bot %i --config-dir config", "--bot %i --env paper --config-dir config")
            .replace("MemoryHigh=280M", "MemoryHigh=600M").replace("MemoryMax=350M", "MemoryMax=750M")
            .replace("EnvironmentFile=/etc/trader-veto-hmac.env\n", "")      # DD-12 WP-06a: kagitta veto yok
            .replace("PYTHONPATH=/opt/trader/src\n", "PYTHONPATH=/opt/trader/src:/opt/trader/paket\n"))      # 19.11: ML filtresi ortak paketi
    strip = lambda t: [ln for ln in t.splitlines() if not ln.lstrip().startswith("#")]  # noqa: E731
    assert strip((DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")) == strip(want)


class _Ctl:
    def __init__(self, active="failed", exit_=7):
        self.active, self.exit_, self.calls = active, exit_, []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[0] == "show":
            return 0, f"ActiveState={self.active}\nExecMainStatus={self.exit_}\nResult=exit-code\n"
        return 0, ""

    @property
    def restarts(self):
        return [c for c in self.calls if c[0] == "restart"]


def _retry_env(tmp_path, monkeypatch):
    """Besleme saglikli (gercek simdiki zamana gore; main() saati enjekte etmez)."""
    now = datetime.now(UTC)
    pairs = ["BTC/USDT", "ETH/USDT"]
    var = tmp_path / "var"
    var.mkdir(parents=True, exist_ok=True)
    (var / "feed-status.json").write_text(json.dumps({"ts": (now - timedelta(seconds=30)).isoformat(), "pairs": pairs}))
    c = sqlite3.connect(var / "market.sqlite")
    c.execute("CREATE TABLE bars(kind TEXT, pair TEXT, tf TEXT, open_ms INTEGER)")
    c.execute("CREATE TABLE rules(pair TEXT)")
    c.execute("CREATE TABLE feed_meta(k TEXT, v TEXT)")
    for p in pairs:
        c.execute("INSERT INTO bars VALUES('last',?,'1m',?)", (p, int((now - timedelta(seconds=30)).timestamp() * 1000)))
        c.execute("INSERT INTO rules VALUES(?)", (p,))
    c.commit()
    c.close()
    for k, v in {"ENGINE_VAR_DIR": str(var), "MARKET_DB": str(var / "market.sqlite"), "MARKET_PAIRS": ",".join(pairs),
                 "STATE_DIR": str(tmp_path / "state"), "NOTIFIER": "log"}.items():
        monkeypatch.setenv(k, v)


def test_u_10_engine_retry_unit_option(tmp_path, monkeypatch):
    R = load_script("engine_retry")
    # exit 7 + besleme saglikli -> canli birim bir kez yeniden baslatilir
    _retry_env(tmp_path / "a", monkeypatch)
    ctl = _Ctl("failed", 7)
    assert R.main(["--bot", "learner", "--unit", "trader-engine-live.service"], ctl=ctl) == 0
    assert [c for c in ctl.restarts] == [["restart", "trader-engine-live.service"]]
    assert all("trader-engine-live.service" in " ".join(c) for c in ctl.calls if c[0] in ("show", "restart", "reset-failed"))
    # exit 8 -> yeniden baslatma yok
    _retry_env(tmp_path / "b", monkeypatch)
    ctl = _Ctl("failed", 8)
    R.main(["--bot", "learner", "--unit", "trader-engine-live.service"], ctl=ctl)
    assert ctl.restarts == []
    # bilinmeyen birim -> donus 1, ctl hic cagrilmaz
    _retry_env(tmp_path / "c", monkeypatch)
    ctl = _Ctl("failed", 7)
    assert R.main(["--bot", "learner", "--unit", "foo.service"], ctl=ctl) == 1
    assert ctl.calls == []
    # --unit verilmezse tabanla ayni cagrilar
    _retry_env(tmp_path / "d", monkeypatch)
    ctl = _Ctl("failed", 7)
    assert R.main(["--bot", "learner"], ctl=ctl) == 0
    assert [c[0] for c in ctl.calls] == ["show", "reset-failed", "restart"]
    assert ctl.calls[0][1] == "trader-engine@learner.service"
    assert ctl.restarts == [["restart", "trader-engine@learner.service"]]


@pytest.mark.parametrize("unit", ["trader-engine-testnet.service", "trader-engine@learner.service"])
def test_u_10b_engine_retry_accepts_whitelisted_units(tmp_path, monkeypatch, unit):
    R = load_script("engine_retry")
    _retry_env(tmp_path, monkeypatch)
    ctl = _Ctl("failed", 7)
    assert R.main(["--bot", "learner", "--unit", unit], ctl=ctl) == 0
    assert ctl.restarts == [["restart", unit]]


def test_u_11_env_retry_template_exec_start_uses_instance_unit():
    svc = DEPLOY / "trader-engine-env-retry@.service"
    assert svc.exists() and (DEPLOY / "trader-engine-env-retry@.timer").exists()
    exe = unit_get(read(svc), "ExecStart")[0]
    assert "--unit trader-engine-%i.service" in exe and "--bot learner" in exe


# ====================================================================================== E: env dosyalari (O13)
def _env_step_region(text: str) -> str:
    start = text.index("copy_env() {")
    last = max(m.start() for m in re.finditer(r"^copy_env\s+\"", text, re.M))
    nxt = re.compile(r"^# ---- ", re.M).search(text, last)
    return text[start:nxt.start() if nxt else len(text)]


def run_env_step(tmp: Path, *, with_twin: int = 1, pre: dict[str, tuple[str, int]] | None = None) -> dict[str, dict[str, str]]:
    """install.sh'in env-ornek kopyalama + harden + yol adimlarini (sahip/chown etkisiz) tmp dizinde calistirir.
    pre: {dosya_adi: (icerik, kip)} onceden var olan dosyalar. Doner: {ad: {ANAHTAR: deger}}."""
    t = install_text()
    snippet = _env_step_region(t)
    # harden_env_file islevi bolge disindaysa (ornegin ayarlar blogunda) ayrica ekle
    prelude_fns = ""
    if not has_fn(snippet, "harden_env_file") and has_fn(t, "harden_env_file"):
        prelude_fns = extract_fn(t, "harden_env_file")
    snippet = re.sub(r"/etc/(trader-[\w.*-]+)", lambda m: f"{tmp}/{m.group(1)}", snippet)
    snippet = re.sub(r"\$\{?\w+\}?(?:/[^\"\s]*?)?/deploy/", f"{DEPLOY}/", snippet)
    tmp.mkdir(parents=True, exist_ok=True)
    for name, (content, mode) in (pre or {}).items():
        (tmp / name).write_text(content)
        os.chmod(tmp / name, mode)
    script = (
        "set -eo pipefail\n"
        f"TRADER_DIR={shlex_q(SERVER_TRADER_DIR)}\nTRADER_USER=trader\nTG_GROUP=trader-tg\nWITH_TWIN={with_twin}\nLIVE=0\n"
        f"REPO_DIR=/nonexistent/repo\nROOT_DIR={shlex_q(str(tmp / 'rootdir'))}\nCOMMIT={HEX40}\nHOME_DIR=/nonexistent/home\n"
        "chown() { :; }\n"
        "install() { local a=(); while [ $# -gt 0 ]; do case \"$1\" in -o|-g) shift 2;; *) a+=(\"$1\"); shift;; esac; done; command install \"${a[@]}\"; }\n"
        "fail() { echo \"HATA: $*\" >&2; exit 1; }\n"
        f"{prelude_fns}\n{snippet}\n")
    r = bash(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out: dict[str, dict[str, str]] = {}
    for p in sorted(tmp.glob("trader-*.env")):
        kv = {}
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln and not ln.startswith("#") and "=" in ln:
                k, _, v = ln.partition("=")
                kv[k] = v
        out[p.name] = kv
    return out


def test_e_01_live_env_example_has_exactly_three_empty_lines():
    p = DEPLOY / "trader-live.env.example"
    assert p.exists()
    kv = dict(ln.split("=", 1) for ln in read(p).splitlines() if ln.strip() and not ln.lstrip().startswith("#"))
    assert kv == {"BINANCE_API_KEY": "", "BINANCE_API_SECRET": "", "LIVE_CONFIRM": ""}
    assert len([ln for ln in read(p).splitlines() if ln.strip() and not ln.lstrip().startswith("#")]) == 3


def test_e_02_install_env_permissions_text():
    t = install_text()
    assert "0640" not in t and "usermod -aG" not in t
    calls = [ln for ln in t.splitlines() if re.match(r"^\s*copy_env\s+\"", ln)]
    assert calls
    for ln in calls:
        assert '"root:root"' in ln and "0600" in ln, ln
    assert any("/etc/trader-live.env" in ln for ln in calls), "/etc/trader-live.env icin copy_env yok"


def test_e_03_every_env_file_ends_0600_and_existing_0640_file_is_hardened_byte_identical(tmp_path):
    content = "ANTHROPIC_API_KEY_VETO=SIZMA-xyz\n"
    out = run_env_step(tmp_path, pre={"trader-veto.env": (content, 0o640)})
    assert "trader-live.env" in out, "canli env ornekten olusturulmadi"
    files = sorted(tmp_path.glob("trader-*.env"))
    assert len(files) >= 7      # 24.11: veto-hmac env artik olusturulmaz (pre'daki trader-veto.env dahil)
    for p in files:
        assert stat.S_IMODE(p.stat().st_mode) == 0o600, p.name
    assert (tmp_path / "trader-veto.env").read_bytes() == content.encode()


def test_e_04_harden_env_file_plain_file_and_symlink(tmp_path):
    t = install_text()
    fn = extract_fn(t, "harden_env_file")
    pre = ("set -euo pipefail\nchown() { :; }\n" + extract_fn(t, "fail") + "\n" + fn + "\n")
    plain = tmp_path / "trader-x.env"
    plain.write_text("A=1\n")
    os.chmod(plain, 0o640)
    r = bash(pre + f"harden_env_file {shlex_q(str(plain))}\n")
    assert r.returncode == 0, r.stderr
    assert stat.S_IMODE(plain.stat().st_mode) == 0o600
    target = tmp_path / "hedef.env"
    target.write_text("S=1\n")
    os.chmod(target, 0o640)
    link = tmp_path / "trader-link.env"
    link.symlink_to(target)
    r = bash(pre + f"harden_env_file {shlex_q(str(link))}\n")
    assert r.returncode != 0
    assert stat.S_IMODE(target.stat().st_mode) == 0o640, "sembolik bagin hedefinin kipi degisti"


def test_e_05_trader_removed_from_tg_group_under_membership_check():
    t = install_text()
    lines = t.splitlines()
    pat = re.compile(r"gpasswd\s+-d\s+(\"?\$\{?TRADER_USER\}?\"?|\"?trader\"?)\s+(\"?\$\{?TG_GROUP\}?\"?|\"?trader-tg\"?)")
    idx = [i for i, ln in enumerate(lines) if pat.search(ln)]
    assert idx, "gpasswd -d trader trader-tg yok"
    i = idx[0]
    window = "\n".join(lines[max(0, i - 3):i + 1])
    assert re.search(r"id -nG|id -Gn|groups|getent|grep -q|\bif\b|&&", window), "uyelik denetimi kosulu yok"
    assert "groupdel" not in t


def test_e_06_telegram_group_bridge_units_keep_supplementary_group():
    for name in ("trader-telegram.service", "trader-health.service", "trader-health-fail@.service",
                 "trader-telegram-report.service", "trader-engine-env-retry@.service"):
        assert "SupplementaryGroups=trader-tg" in read(DEPLOY / name), name


def test_e_07_uninstall_purge_lists_the_four_new_paths():
    t = read(DEPLOY / "uninstall.sh")
    for p in ("/etc/trader-live.env", "/etc/trader-release", "/usr/local/lib/trader-root"):
        assert p in t, p


# ====================================================================================== R: root kopyasi, veto kullanicisi, proc_guard
ROOT_UNITS = ("trader-health.service", "trader-backup.service", "trader-engine-retry@.service", "trader-engine-env-retry@.service")


def test_r_01_four_root_units_run_from_root_tree(tmp_path):
    rendered = render_units(tmp_path / "u")
    for name in ROOT_UNITS:
        raw = read(DEPLOY / name)
        assert unit_get(raw, "User") == ["root"], name
        exe = unit_get(raw, "ExecStart")[0]
        assert exe.startswith(f"{ROOT_DIR}/venv/bin/python -I {ROOT_DIR}/current/scripts/"), name
        for bad in ("/opt/trader/scripts", "/opt/trader/src", "/usr/bin/python3", ".venv"):
            assert bad not in raw, f"{name}: {bad}"
        assert "Environment=TRADER_DATA_ROOT=/opt/trader" in raw.splitlines(), name
        rexe = unit_get(rendered[name], "ExecStart")[0]
        assert rexe.startswith(f"{ROOT_DIR}/"), name
        assert f"Environment=TRADER_DATA_ROOT={SERVER_TRADER_DIR}" in rendered[name].splitlines(), name


def test_r_02_only_the_four_units_run_as_root_and_veto_unit_is_gone():
    roots = {p.name for p in DEPLOY.glob("*.service") if unit_get(read(p), "User") == ["root"]}
    # + kullanici onayli otomatik guncelleme (docs/motor/oto-guncelleme-spec.md): yalniz root sahipli surum agacindan calisir
    # + kurulum gozcusu (kurulumdan sonra oz-kontrol/izleme/otomatik geri alma): root sahipli surum agacindan calisir
    assert roots == set(ROOT_UNITS) | {"trader-oto-guncelle.service", "trader-kurulum-gozcu.service"}
    assert unit_get(read(DEPLOY / "trader-kurulum-gozcu.service"), "ExecStart") == [
        f"{ROOT_DIR}/venv/bin/python -I {ROOT_DIR}/current/scripts/kurulum_gozcu.py"]
    assert unit_get(read(DEPLOY / "trader-oto-guncelle.service"), "ExecStart") == [
        f"/bin/bash {ROOT_DIR}/current/deploy/oto_guncelle.sh"]
    assert not (DEPLOY / "trader-veto.service").exists()           # DD-12 WP-06a: veto birimi kaldirildi


def _lock_blocks(path: Path) -> dict[str, list[str]]:
    """requirements kilidi -> {paket: [satirlar]} (yorum/bos disi, 'via' yorumlari disarida)."""
    blocks, cur = {}, None
    for ln in read(path).splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)==", ln)
        if m:
            cur = m.group(1)
            blocks[cur] = []
        blocks[cur].append(ln)
    return blocks


def test_r_03_root_lock_is_verbatim_subset_of_main_lock():
    sub = DEPLOY / "requirements-root.lock"
    assert sub.exists()
    main = read(ROOT / "requirements.lock").splitlines()
    sub_lines = [ln for ln in read(sub).splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    for ln in sub_lines:
        assert ln in main, f"ana kilitte yok: {ln}"
    blocks = _lock_blocks(sub)
    assert set(blocks) == {"requests", "certifi", "charset-normalizer", "idna", "urllib3"}
    main_blocks = _lock_blocks(ROOT / "requirements.lock")
    for pkg, lines in blocks.items():
        h = [ln for ln in lines if "--hash=" in ln]
        mh = [ln for ln in main_blocks[pkg] if "--hash=" in ln]
        assert len(h) == len(mh) >= 1, pkg


def test_r_04_root_scripts_import_closure_excludes_heavy_packages():
    code = ("import sys, json\n"
            f"sys.path[:0] = [{str(SRC)!r}, {str(SCRIPTS)!r}]\n"
            "import health_run, health_backup, engine_retry\n"
            "import trader_core.telegram, trader_core.live_paths\n"
            "print(json.dumps(sorted(m for m in sys.modules if m.split('.')[0] in ('pandas','numpy','pyarrow','anthropic'))))\n")
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == []


def test_r_05_install_sh_uses_root_owned_release_tree_text():
    t = install_text()
    assert "git archive" in t and ROOT_DIR in t
    lines = t.splitlines()
    for ln in lines:
        if ln.lstrip().startswith("#"):
            continue
        if re.search(r"\bgit\b", ln) and re.search(r"\$\{?REPO_DIR\}?", ln):
            assert "as_trader" in ln and ln.index("as_trader") < re.search(r"\bgit\b", ln).start(), f"root git: {ln.strip()}"
    m = re.search(r"exec bash\s+(\S+)", t)
    assert m, "exec bash yok"
    assert "TRADER_DIR" not in m.group(1), m.group(1)
    assert "ROOT_DIR" in m.group(1) or "trader-root" in m.group(1) or "RELEASE" in m.group(1).upper(), m.group(1)
    assert not re.search(r"\$\{?TRADER_DIR\}?\"?/deploy/trader-", t), "sablon/ornekler hala trader sahipli depodan okunuyor"
    assert "$TRADER_DIR/deploy/install.sh" not in t


def test_r_06_install_chowns_user_data_to_trader():
    t = install_text().replace("\\\n", " ")
    lines = [ln for ln in t.splitlines() if "chown" in ln and "-hR" in ln.replace("-R -h", "-hR").replace("-Rh", "-hR")]
    assert lines, "chown -hR yok"
    joined = "\n".join(lines)
    assert "shared/veto" not in joined and "user_data" in joined
    assert re.search(r"trader:trader|\$\{?TRADER_USER\}?:\$\{?TRADER_USER\}?", joined)


def test_r_07_trader_data_root_resolves_data_paths_only_when_absolute():
    tgm = importlib.import_module("trader_core.telegram")
    R = load_script("health_run")
    assert str(R.data_root({"TRADER_DATA_ROOT": "/x"})) == "/x"
    assert R.data_root({"TRADER_DATA_ROOT": "x"}) == R.data_root({})
    tg_env = {"TELEGRAM_BOT_TOKEN": "123456:SIZMA", "TELEGRAM_CHAT_ID": "42"}
    base_var = tgm.TelegramConfig.from_env(dict(tg_env)).var_dir
    assert tgm.TelegramConfig.from_env({**tg_env, "TRADER_DATA_ROOT": "/x"}).var_dir == "/x/var/telegram"
    assert tgm.TelegramConfig.from_env({**tg_env, "TRADER_DATA_ROOT": "x"}).var_dir == base_var
    assert base_var == str(ROOT / "var" / "telegram")


def test_r_08_proc_guard_makes_process_nondumpable_and_environ_owned_by_root():
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux degil")
    code = ("import sys, os, json\n"
            f"sys.path.insert(0, {str(SRC)!r})\n"
            "from trader_core import proc_guard as P\n"
            "a = P.set_nondumpable()\n"
            "b = P.is_dumpable()\n"
            "uid = os.stat('/proc/self/environ').st_uid\n"
            "try:\n"
            "    open('/proc/self/environ', 'rb').close(); readable = True\n"
            "except PermissionError:\n"
            "    readable = False\n"
            "print(json.dumps([a, b, uid, readable, os.geteuid()]))\n")
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    a, b, uid, readable, euid = json.loads(r.stdout)
    assert a is True and b is False
    assert uid == 0
    # Korumanin asil beklentisi: dokulemez surecte /proc/self/environ yalniz root'a acik (DAC: root okuyabilir,
    # diger kullanicilar -- kendisi dahil -- okuyamaz). Root olmayan CI kosucusunda PermissionError beklenen davranis.
    assert readable is (euid == 0)


def _live_cli_setup(tmp_path, monkeypatch, run_env, env_name, tag="canli-x"):
    cdir, _ = D8.make_tree(tmp_path, env_name, tag=tag)
    monkeypatch.chdir(tmp_path)
    if env_name == "live":
        monkeypatch.setenv("LIVE_CONFIRM", tag)
    return cdir


def test_r_09_run_calls_proc_guard_only_for_testnet_and_live(tmp_path, monkeypatch, run_env, caplog):
    # live: False -> cikis 2, build_engine cagrilmaz
    calls: list = []
    patch_proc_guard(monkeypatch, False, calls)
    cdir = _live_cli_setup(tmp_path / "l", monkeypatch, run_env, "live")
    assert _cli_run(cdir, "live") == 2
    assert calls and run_env.build_calls == []
    # testnet: False -> WARNING, acilis surer
    calls.clear()
    cdir = _live_cli_setup(tmp_path / "t", monkeypatch, run_env, "testnet", tag="testnet-sub")
    with caplog.at_level(logging.WARNING):
        assert _cli_run(cdir, "testnet") == 0
    assert calls and len(run_env.build_calls) == 1
    kw = ("proc_guard", "dump", "environ", "ortam")
    assert [r for r in caplog.records if r.levelno == logging.WARNING and any(k in r.getMessage().lower() for k in kw)], "WARNING yok"
    # paper: hic cagrilmaz
    calls.clear()
    from trader_engine import cli
    cdir, _ = D8.make_tree(tmp_path / "p", "testnet")
    assert cli.main(["run", "--bot", "learner", "--config-dir", str(cdir)]) == 0
    assert calls == []


def _no_http_main_args(name, tmp_path):
    return ["daemon"], {"env": {}}


@pytest.mark.parametrize("name", ["telegram_run"])     # 24.11: veto_run silindi; 25.11: lesson_run silindi
def test_r_10_script_mains_call_set_nondumpable_exactly_once(tmp_path, monkeypatch, name):
    mod = load_script(name)
    argv, kw = _no_http_main_args(name, tmp_path)
    results = []
    for ret in (True, False):
        calls: list = []
        PG = patch_proc_guard(monkeypatch, ret, calls)
        assert PG is not None, "trader_core.proc_guard yok"
        rc = mod.main(argv, **kw)
        assert len(calls) == 1, f"{name}: set_nondumpable {len(calls)} kez cagrildi"
        results.append(rc)
    assert results[0] == results[1], "False donusu sonucu degistirdi"


def test_r_11_proc_guard_imports_only_stdlib():
    assert stdlib_only(SRC / "trader_core" / "proc_guard.py") == []


# ====================================================================================== C: COMMIT sabitleme, --live (O15)
def run_fns(names, body, *, env=None, fail_stub=True):
    t = install_text()
    fns = "\n".join(extract_fn(t, n) for n in names)
    stub = "fail() { echo \"FAIL:$*\" >&2; exit 1; }\n" if fail_stub else ""
    return bash("set -euo pipefail\n" + stub + fns + "\n" + body, env=env)


def _rcs(names, fn, values, extra_env=None):
    """fn'i her deger icin cagirir; {deger: cikis_kodu} doner."""
    body = ("for v in \"$@\"; do rc=0; " + fn + " \"$v\" >/dev/null 2>&1 || rc=$?; printf '%s\\t%s\\n' \"$v\" \"$rc\"; done\n")
    t = install_text()
    fns = "\n".join(extract_fn(t, n) for n in names)
    script = "set -euo pipefail\nfail() { echo FAIL >&2; exit 1; }\n" + fns + "\n" + body
    r = subprocess.run(["bash", "-c", script, "x", *values], capture_output=True, text=True, env={**os.environ, **(extra_env or {})}, timeout=60)
    assert r.returncode == 0, r.stderr
    out = {}
    for ln in r.stdout.splitlines():
        v, _, rc = ln.rpartition("\t")
        out[v] = int(rc)
    return out


def test_c_01_valid_commit_accepts_only_40_lowercase_hex():
    good = [HEX40, "a" * 40, "0" * 40]
    bad = [HEX40[:39], HEX40 + "a", HEX40.upper(), "main", "canli-20261230", "", "g" * 40, " " + HEX40]
    res = _rcs(["valid_commit"], "valid_commit", good + bad)
    for v in good:
        assert res[v] == 0, v
    for v in bad:
        assert res[v] == 1, repr(v)


def _resolve(tmp_path, *, env_commit=None, file_commit=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    rf = tmp_path / "trader-release"
    if file_commit is not None:
        rf.write_text(f"COMMIT={file_commit}\n")
    env = {k: v for k, v in os.environ.items() if k != "COMMIT"}
    if env_commit is not None:
        env["COMMIT"] = env_commit
    t = install_text()
    fns = "\n".join(extract_fn(t, n) for n in ("valid_commit", "resolve_commit"))
    script = (f"set -euo pipefail\nfail() {{ echo FAIL >&2; exit 1; }}\nRELEASE_FILE={shlex_q(str(rf))}\n{fns}\n"
              "rc=0; out=$(resolve_commit) || rc=$?; printf '%s|%s' \"$rc\" \"$out\"\n")
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    rc, _, out = r.stdout.partition("|")
    return int(rc), out.strip()


def test_c_02_resolve_commit_precedence_env_then_file_then_fail(tmp_path):
    a, b = "a" * 40, "b" * 40
    assert _resolve(tmp_path / "1", env_commit=a, file_commit=b) == (0, a)
    assert _resolve(tmp_path / "2", file_commit=b) == (0, b)
    assert _resolve(tmp_path / "3")[0] == 1
    assert _resolve(tmp_path / "4", env_commit="main", file_commit=b)[0] == 1          # gecersiz ortam degeri dosyaya dusmez


def test_c_03_is_live_tag_pattern():
    good = ["canli-20261230", "canli-20261230-2", "canli-20261230-17"]
    bad = ["canli-2026", "live-20261230", "canli-20261230-", "xcanli-20261230", "canli-20261230x", "canli-202612300", ""]
    res = _rcs(["is_live_tag"], "is_live_tag", good + bad)
    for v in good:
        assert res[v] == 0, v
    for v in bad:
        assert res[v] == 1, repr(v)


def _set_kv(path: Path, name: str, value: str):
    r = run_fns(["set_kv"], f"set_kv {shlex_q(str(path))} {shlex_q(name)} {shlex_q(value)}\n")
    assert r.returncode == 0, r.stderr


def test_c_04_set_kv_replaces_appends_and_is_idempotent(tmp_path):
    f = tmp_path / "x.env"
    f.write_bytes(b"A=eski\nB=2\n# yorum\nC=3\n")
    _set_kv(f, "A", "/x/var-live")
    assert f.read_bytes() == b"A=/x/var-live\nB=2\n# yorum\nC=3\n"
    _set_kv(f, "D", "4")
    assert f.read_bytes() == b"A=/x/var-live\nB=2\n# yorum\nC=3\nD=4\n"
    _set_kv(f, "A", "/x/var-live")
    _set_kv(f, "D", "4")
    assert f.read_bytes() == b"A=/x/var-live\nB=2\n# yorum\nC=3\nD=4\n"           # idempotent, tek satir
    g = tmp_path / "y.env"
    g.write_bytes(b"A=1\nB=2")                                                      # son satir sonu yok
    _set_kv(g, "C", "3")
    assert g.read_bytes() == b"A=1\nB=2\nC=3\n"
    h = tmp_path / "z.env"
    h.write_bytes(b"A=1\n")
    _set_kv(h, "A", "")
    assert h.read_bytes() == b"A=\n"


def test_c_05_install_text_checkout_and_release_pin():
    t = install_text()
    assert "merge --ff-only" not in t
    assert "checkout --quiet --detach" in t
    assert "merge-base --is-ancestor" in t
    assert "/etc/trader-release" in t and re.search(r"COMMIT=(%s|\$)", t)


def test_c_06_live_flag_parsing_and_default_off_text():
    t = install_text()
    assert "--live" in t and "--no-live" in t
    lines = t.splitlines()
    # render dongusu: canli birim LIVE kosuluna bagli atlanir
    r_i = next(i for i, ln in enumerate(lines) if re.search(r"\brender\s+\"\$f\"", ln))
    start = max(i for i in range(r_i + 1) if re.match(r"^\s*for\s+f\s+in\b", lines[i]))
    loop = "\n".join(lines[start:r_i + 3])
    assert "trader-engine-live.service" in loop and re.search(r"\bLIVE\b", loop), loop
    assert "enable_now trader-engine-live.service" not in t
    assert not re.search(r"enable\s+--now\s+trader-engine-live", t)
    code = [(i, ln) for i, ln in enumerate(lines) if not ln.lstrip().startswith("#")]
    en = [i for i, ln in code if "systemctl enable trader-engine-live.service" in ln]
    assert en, "systemctl enable trader-engine-live.service yok"
    pre = [i for i, ln in code if "live_preflight" in ln]
    assert pre and min(pre) < en[0], "enable, live_preflight cagrisindan once"
    stack = []
    for i in range(en[0]):
        s = lines[i]
        if s.lstrip().startswith("#"):
            continue
        if re.match(r"^\s*if\b", s):
            stack.append(s)
        if re.match(r"^\s*fi\b", s) and stack:
            stack.pop()
    assert any(re.search(r"\bLIVE\b", s) for s in stack), "enable LIVE kosulu disinda"


def _live_if_blocks(text: str) -> list[str]:
    lines, blocks, i = text.splitlines(), [], 0
    while i < len(lines):
        if re.match(r"^if\b", lines[i]) and re.search(r"\$\{?LIVE\}?", lines[i]):
            depth, j = 0, i
            while j < len(lines):
                s = lines[j]
                if re.match(r"^\s*if\b", s):
                    depth += 1
                depth -= len(re.findall(r"(?:^|;)\s*fi\b", s))
                if depth <= 0:
                    break
                j += 1
            blocks.append("\n".join(lines[i:j + 1]))
            i = j + 1
        else:
            i += 1
    return blocks


def _git(*args, cwd=None):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def run_live_gate(tmp: Path, *, live=1, key="K" * 40, secret="S" * 40, confirm=LIVE_TAG, tags=("canli-20261230",),
                  pause_rc=0, preflight_rc=0):
    """install.sh'in `LIVE` kosullu ust duzey `if` bloklarini (on kosullar + kurulum) stub'lanmis systemctl/as_trader ile tmp
    dizinde calistirir. Etiket sorgusu GERCEK git ile, tmp'deki gercek depolara (root klonu `$ROOT_DIR/repo.git` + `$REPO_DIR`) karsi
    calisir. Doner: (cikis, kayit metni, islem)."""
    if os.geteuid() != 0:
        pytest.skip("root:root sahiplik denetimi taklit edilemiyor (root degil)")
    t = install_text()
    blocks = _live_if_blocks(t)
    assert blocks, "install.sh'te LIVE kosullu blok yok"
    etc, root_dir, trader = tmp / "etc", tmp / "rootdir", tmp / "trader"
    work = tmp / "work"
    work.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", str(work))
    _git("commit", "-q", "--allow-empty", "-m", "x", cwd=str(work))
    sha = _git("rev-parse", "HEAD", cwd=str(work))
    for tg in tags:
        _git("tag", tg, sha, cwd=str(work))
    root_dir.mkdir(parents=True, exist_ok=True)
    _git("clone", "-q", "--bare", str(work), str(root_dir / "repo.git"))
    _git("clone", "-q", str(work), str(tmp / "repo"))
    for d in (etc, root_dir / "venv" / "bin", root_dir / "current" / "scripts", root_dir / "releases" / sha / "scripts",
              trader / ".venv" / "bin", trader / "config", tmp / "units"):
        d.mkdir(parents=True, exist_ok=True)
    stub_py = root_dir / "venv" / "bin" / "python"
    stub_py.write_text("#!/bin/bash\necho \"preflight $*\" >> \"$LOG\"\ncase \"$*\" in *live_preflight*) exit \"${PREFLIGHT_RC:-0}\";; esac\nexit 0\n")
    os.chmod(stub_py, 0o755)
    (trader / ".venv" / "bin" / "python").write_text("#!/bin/bash\nexit 0\n")
    os.chmod(trader / ".venv" / "bin" / "python", 0o755)
    live_env = etc / "trader-live.env"
    live_env.write_text(f"BINANCE_API_KEY={key}\nBINANCE_API_SECRET={secret}\nLIVE_CONFIRM={confirm}\n")
    os.chmod(live_env, 0o600)
    os.chown(live_env, 0, 0)
    for n in ("trader-telegram.env", "trader-health.env", "trader-lesson.env"):
        (etc / n).write_text("KILL_FILE=\nLIVE_BOTS=\n")
        os.chmod(etc / n, 0o600)
    stubbed = {"as_trader", "enable_now", "fail", "say", "render", "systemctl", "install", "runuser"}
    fn_names = [n for n in re.findall(r"^(\w+)\(\)\s*\{", t, re.M) if n not in stubbed]
    fns = "\n".join(extract_fn(t, n) for n in fn_names)
    # Mentor F5 (DD-9 incelemesi): --live, onceki --live'siz kurulumun /etc/trader-release dosyasini sart kosar; harness onu tohumlar
    release_file = etc / "trader-release"
    release_file.write_text(f"COMMIT={sha}\n")
    log = tmp / "log"
    log.write_text("")
    body = "\n".join(blocks)
    script = (
        "set -eo pipefail\n"
        f"export LOG={shlex_q(str(log))} PAUSE_RC={pause_rc} PREFLIGHT_RC={preflight_rc} HOME={shlex_q(str(tmp))} "
        "GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null\n"
        f"LIVE={live}\nTRADER_DIR={shlex_q(str(trader))}\nREPO_DIR={shlex_q(str(tmp / 'repo'))}\nROOT_DIR={shlex_q(str(root_dir))}\n"
        f"COMMIT={sha}\nRELEASE_DIR=\"$ROOT_DIR/releases/$COMMIT\"\nREL_DIR=\"$RELEASE_DIR\"\nTRADER_USER=trader\nTG_GROUP=trader-tg\n"
        f"UNIT_DIR={shlex_q(str(tmp / 'units'))}\nWITH_TWIN=1\nCODE_CHANGED=1\nBRANCH=master\nMISSING=()\nACTIVE_ENGINES=\n"
        "NO_LIVE=0\nLIVE_FLAG=0\n"
        "RELEASE_FILE=/etc/trader-release\n"   # harness /etc/ onekini tmp etc'ye esler
        # SPEC-AMBIGUOUS: kok klonu/surum dizini degisken adlari sartnamede yalniz ROOT_DIR olarak sabit; yaygin takma adlar da tanimlanir
        "for _v in ROOT_REPO ROOT_REPO_DIR ROOT_GIT ROOT_GIT_DIR ROOT_CLONE ROOT_CLONE_DIR BARE_REPO BARE_DIR REPO_BARE; do "
        "printf -v \"$_v\" '%s' \"$ROOT_DIR/repo.git\"; done\n"
        "RELEASES_DIR=\"$ROOT_DIR/releases\"; RELEASE_PATH=\"$RELEASE_DIR\"; REL=\"$RELEASE_DIR\"; NEW_RELEASE=\"$RELEASE_DIR\"; CURRENT_LINK=\"$ROOT_DIR/current\"\n"
        "fail() { echo \"FAIL $*\" >> \"$LOG\"; exit 1; }\n"
        "say() { :; }\n"
        "as_trader() { echo \"as_trader $*\" >> \"$LOG\"; case \"$*\" in *trader_engine*pause*) return \"$PAUSE_RC\";; esac; \"$@\"; }\n"
        "runuser() { shift 3; as_trader \"$@\"; }\n"
        "systemctl() { echo \"systemctl $*\" >> \"$LOG\"; return 0; }\n"
        "enable_now() { echo \"enable_now $*\" >> \"$LOG\"; }\n"
        "render() { echo \"render $1 $2\" >> \"$LOG\"; }\n"
        "install() { echo \"install $*\" >> \"$LOG\"; }\n"
        f"{fns}\n{body}\n")
    script = re.sub(r"/etc/(trader-[\w.-]+)", lambda m: f"{etc}/{m.group(1)}", script)
    script = script.replace("/etc/systemd/system", str(tmp / "units"))
    r = bash(script)
    return r.returncode, log.read_text(), r


def test_c_07_live_gate_executes_preconditions_and_never_starts_live_unit(tmp_path):
    # (a) canli env'de uc alandan biri bos -> fail, birim/env degismeden
    for i, kw in enumerate(({"key": ""}, {"secret": ""}, {"confirm": ""})):
        rc, log, r = run_live_gate(tmp_path / f"a{i}", **kw)
        assert rc != 0 and "FAIL" in log, (kw, r.stderr, log)
        assert "enable trader-engine-live.service" not in log and "render " not in log
    # (b) etiket yok / kalip disi etiket -> fail
    for i, tags in enumerate(((), ("canli-2026", "live-20261230"))):
        rc, log, r = run_live_gate(tmp_path / f"b{i}", tags=tags)
        assert rc != 0 and "FAIL" in log, (tags, r.stderr, log)
        assert "enable trader-engine-live.service" not in log
    # (c) hepsi dolu, etiket var, on denetim 0 -> enable var; canli birim icin start/--now yok
    rc, log, r = run_live_gate(tmp_path / "c")
    assert rc == 0, r.stderr + log
    lines = log.splitlines()
    assert "systemctl enable trader-engine-live.service" in [ln.strip().split(" >")[0] for ln in lines] or \
        any(re.match(r"^systemctl enable trader-engine-live\.service\b", ln) for ln in lines), log
    for ln in lines:
        if "trader-engine-live.service" in ln:
            assert "--now" not in ln and " start" not in ln, ln
    # on denetim ve motorun kendi dogrulayicisi basarisizsa canli birim etkinlesmez
    rc, log, _ = run_live_gate(tmp_path / "c2", preflight_rc=1)
    assert rc != 0 and "enable trader-engine-live.service" not in log
    rc, log, _ = run_live_gate(tmp_path / "c3", pause_rc=1)
    assert rc != 0 and "enable trader-engine-live.service" not in log
    # LIVE=0 -> kayitta canli birim hic yok
    rc, log, r = run_live_gate(tmp_path / "d", live=0)
    assert rc == 0, r.stderr
    assert "trader-engine-live" not in log


def test_c_08_live_and_no_live_together_is_a_usage_error(tmp_path):
    t = install_text()
    m = re.search(r"^# ---- 0\.", t, re.M)
    assert m, "install.sh '# ---- 0.' basligi yok (arguman ayristirma blogu ayrilamadi)"
    head = t[:m.start()]
    pre = "id() { echo 0; }\ngit() { return 0; }\nrunuser() { return 0; }\n"

    def run(*args):
        e = {**os.environ, "COMMIT": HEX40, "RELEASE_FILE": str(tmp_path / "yok")}
        return subprocess.run(["bash", "-c", pre + head, "install.sh", *args], capture_output=True, text=True, env=e, timeout=30,
                              cwd=str(tmp_path)).returncode
    assert run("--live", "--no-live") == 2
    assert run("--no-live", "--live") == 2
    assert run("--bogus") == 2
    assert run("--live") == 0 and run("--no-live") == 0


def created_dirs() -> set[str]:
    """install.sh'in `install -d` ile olusturdugu dizinler (sunucudaki yollar)."""
    import shlex
    t = install_text().replace("\\\n", " ")
    subs = {"${TRADER_DIR}": SERVER_TRADER_DIR, "$TRADER_DIR": SERVER_TRADER_DIR, "${HOME_DIR}": "/home/trader", "$HOME_DIR": "/home/trader"}
    dirs: set[str] = set()
    for ln in t.splitlines():
        s = ln.strip()
        if "install -d" not in s:
            continue
        toks = shlex.split(s.split("install -d", 1)[1], comments=True)
        i = 0
        while i < len(toks):
            tk = toks[i]
            if tk in ("-m", "-o", "-g"):
                i += 2
                continue
            for k, v in subs.items():
                tk = tk.replace(k, v)
            if tk.startswith("/"):
                dirs.add(tk.rstrip("/"))
            i += 1
    return dirs


def test_c_09_install_creates_live_dirs_every_run():
    d = created_dirs()
    assert f"{SERVER_TRADER_DIR}/var-live" in d
    assert f"{SERVER_TRADER_DIR}/shared/live" in d
    assert f"{SERVER_TRADER_DIR}/var-testnet" in d          # mevcut dizin korunur


# ====================================================================================== Y: canli yollari
def live_fields(root: Path) -> dict[str, str]:
    """§6.4: install.sh --live'in Telegram env dosyasina yazdigi alanlar (kok = root)."""
    r = str(root)
    return {"KILL_FILE": f"{r}/shared/live/KILL", "ENGINE_STATUS_PATH": f"{r}/var-live/learner/status.json",
            "LEDGER_PATH": f"{r}/var-live/learner/ledger.sqlite", "LIVE_BOTS": "learner", "LIVE_VAR_DIR": f"{r}/var-live",
            "LIVE_PAUSE_FILE": f"{r}/shared/live/PAUSE", "LADDER_BOTS": "learner", "ENGINE_CONFIG_DIR": f"{r}/config"}


def live_root(tmp: Path) -> tuple[Path, Path]:
    root = tmp / "root"
    return root, copy_config(root)


def test_y_01_validate_live_env_rules():
    from trader_core import live_paths as LP
    LP.validate_live_env({})
    LP.validate_live_env({"LIVE_BOTS": ""})
    ok = {"LIVE_BOTS": "learner", "LIVE_VAR_DIR": "/k/var-live", "LIVE_PAUSE_FILE": "/k/shared/live/PAUSE"}
    LP.validate_live_env(ok)

    def code(**over):
        env = {**ok, **over}
        env = {k: v for k, v in env.items() if v is not None}
        with pytest.raises(LP.LivePathError) as ei:
            LP.validate_live_env(env)
        return ei.value.code
    assert code(LIVE_BOTS="twin") == "live_bots_invalid"
    assert code(LIVE_BOTS="learner,twin") == "live_bots_invalid"
    assert code(LIVE_VAR_DIR=None) == "live_var_dir_missing"
    assert code(LIVE_VAR_DIR="") == "live_var_dir_missing"
    assert code(LIVE_VAR_DIR="var-live") == "live_var_dir_relative"
    assert code(LIVE_VAR_DIR="/k/var") == "live_var_dir_paper"
    assert code(LIVE_PAUSE_FILE=None) == "live_pause_missing"
    assert code(LIVE_PAUSE_FILE="") == "live_pause_missing"
    assert code(LIVE_PAUSE_FILE="shared/live/PAUSE") == "live_pause_relative"
    assert code(LIVE_PAUSE_FILE="/k/shared/PAUSE") == "live_pause_paper"


def test_y_02_bot_var_dir_and_pause_base_pick_live_only_for_live_bots():
    from trader_core import live_paths as LP
    env = {"LIVE_BOTS": "learner", "LIVE_VAR_DIR": "/k/var-live", "LIVE_PAUSE_FILE": "/k/shared/live/PAUSE"}
    assert LP.bot_var_dir(env, "learner", "/k/var") == "/k/var-live"
    assert LP.bot_var_dir(env, "twin", "/k/var") == "/k/var"
    assert LP.bot_pause_base(env, "learner", "/k/shared/PAUSE") == "/k/shared/live/PAUSE"
    assert LP.bot_pause_base(env, "twin", "/k/shared/PAUSE") == "/k/shared/PAUSE"
    for e in ({}, {"LIVE_BOTS": ""}):
        assert LP.bot_var_dir(e, "learner", "/k/var") == "/k/var"
        assert LP.bot_pause_base(e, "learner", "/k/shared/PAUSE") == "/k/shared/PAUSE"
    bad = {"LIVE_BOTS": "learner", "LIVE_VAR_DIR": "/k/var", "LIVE_PAUSE_FILE": "/k/shared/live/PAUSE"}
    with pytest.raises(LP.LivePathError):
        LP.bot_var_dir(bad, "learner", "/k/var")
    with pytest.raises(LP.LivePathError):
        LP.bot_pause_base({**bad, "LIVE_VAR_DIR": "/k/var-live", "LIVE_PAUSE_FILE": "/k/shared/PAUSE"}, "learner", "/k/shared/PAUSE")


def test_y_03_expected_from_config_matches_cli_loader(tmp_path):
    from trader_core import live_paths as LP
    from trader_engine.config import load_cli_config
    root, cdir = live_root(tmp_path)
    exp = LP.expected_from_config(str(cdir))
    cfg = load_cli_config(str(cdir), "learner", env="live")
    assert exp["var_dir"] == cfg.var_dir and exp["kill_file"] == cfg.kill_file and exp["pause_file"] == cfg.pause_file
    assert exp["account_tag"] == cfg.live.account_tag == "canli-alt1"
    # dizin adi `config` degilse kok dizinin kendisidir
    root2 = tmp_path / "r2"
    cx = copy_config(root2, "cfgx")
    exp2 = LP.expected_from_config(str(cx))
    assert exp2["var_dir"] == f"{cx}/var-live" and exp2["kill_file"] == f"{cx}/shared/live/KILL" and exp2["pause_file"] == f"{cx}/shared/live/PAUSE"
    assert exp2["var_dir"] == load_cli_config(str(cx), "learner", env="live").var_dir
    empty = tmp_path / "bos"
    empty.mkdir()
    with pytest.raises(LP.LivePathError) as ei:
        LP.expected_from_config(str(empty))
    assert ei.value.code == "live_config_missing"


def test_y_04_check_against_config_reports_exactly_the_broken_field(tmp_path):
    from trader_core import live_paths as LP
    root, cdir = live_root(tmp_path)
    r = str(root)
    good = live_fields(root)
    assert tuple(LP.check_against_config(good, str(cdir))) == ()
    cases = {
        "LIVE_VAR_DIR": (f"{r}/var-baska", "var_dir_mismatch"),
        "LIVE_PAUSE_FILE": (f"{r}/shared/live2/PAUSE", "pause_file_mismatch"),
        "KILL_FILE": (f"{r}/shared/KILL", "kill_file_mismatch"),
        "ENGINE_STATUS_PATH": (f"{r}/var/learner/status.json", "status_path_mismatch"),
        "LEDGER_PATH": (f"{r}/var/learner/ledger.sqlite", "ledger_path_mismatch"),
        "LADDER_BOTS": ("", "ladder_bots_mismatch"),
    }
    for key, (val, code) in cases.items():
        assert tuple(LP.check_against_config({**good, key: val}, str(cdir))) == (code,), key
    no_kill = {k: v for k, v in good.items() if k != "KILL_FILE"}
    assert "kill_file_mismatch" not in LP.check_against_config(no_kill, str(cdir))
    assert tuple(LP.check_against_config({**good, "LIVE_BOTS": ""}, str(cdir))) == ()
    assert tuple(LP.check_against_config({}, str(cdir))) == ()


def test_y_05_telegram_builders_route_live_bot_to_live_paths(tmp_path):
    TR = load_script("telegram_run")
    root, _ = live_root(tmp_path)
    f = live_fields(root)
    env = {**f, "PAUSE_BOTS": "learner,twin", "PAUSE_FILE": f"{root}/shared/PAUSE", "ENGINE_VAR_DIR": f"{root}/var"}
    clock = lambda: NOW  # noqa: E731
    pauses = TR.build_pauses(env, clock)
    assert pauses["learner"].path == f"{f['LIVE_PAUSE_FILE']}.learner"
    assert pauses["learner"].audit_path == f"{f['LIVE_VAR_DIR']}/learner/pause_audit.jsonl"
    assert pauses["twin"].path == f"{root}/shared/PAUSE.twin"
    assert pauses["twin"].audit_path == f"{root}/var/twin/pause_audit.jsonl"
    ladders = TR.build_ladders(env, clock)
    assert ladders["learner"].log.path == f"{f['LIVE_VAR_DIR']}/learner/risk_ladder.jsonl"
    assert ladders["learner"].status_path == f"{f['LIVE_VAR_DIR']}/learner/status.json"
    # LIVE_BOTS bos -> taban davranisi
    legacy = {k: v for k, v in env.items() if not k.startswith("LIVE_")}
    legacy["LADDER_BOTS"] = "learner"
    p0 = TR.build_pauses(legacy, clock)
    assert p0["learner"].path == f"{root}/shared/PAUSE.learner" and p0["learner"].audit_path == f"{root}/var/learner/pause_audit.jsonl"
    assert TR.build_ladders(legacy, clock)["learner"].log.path == f"{root}/var/learner/risk_ladder.jsonl"


TG_TOKEN = "123456:SIZMA-TOKEN-abcdefghij"


def _tg_main_env(tmp_path, root, **over):
    env = {"TELEGRAM_BOT_TOKEN": TG_TOKEN, "TELEGRAM_CHAT_ID": "424242", "TELEGRAM_VAR_DIR": str(tmp_path / "tgvar"),
           "PAUSE_FILE": f"{root}/shared/PAUSE", "ENGINE_VAR_DIR": f"{root}/var", **live_fields(root)}
    env.update(over)
    return env


class _TgSpy:
    def __init__(self, monkeypatch):
        from trader_core import telegram as tgm
        self.created: list[dict] = []
        spy = self
        base = tgm.TelegramDaemon

        class Spy(base):
            def __init__(self, *a, **k):
                spy.created.append(dict(k))
                super().__init__(*a, **k)

            def run_forever(self, stop=None):
                return None
        monkeypatch.setattr(tgm, "TelegramDaemon", Spy)
        self.http: list = []

    def http_post(self, url, json=None, timeout=None, **kw):
        self.http.append(url)
        return 200, {"ok": True, "result": []}


def test_y_06_telegram_daemon_refuses_inconsistent_live_paths(tmp_path, monkeypatch, capsys):
    TR = load_script("telegram_run")
    root, _ = live_root(tmp_path)
    spy = _TgSpy(monkeypatch)
    bad = _tg_main_env(tmp_path, root, KILL_FILE=f"{root}/shared/KILL")
    rc = TR.main(["daemon"], env=bad, http_post=spy.http_post, now_fn=lambda: NOW, sleep=lambda s: None, stop=lambda: True)
    err = capsys.readouterr().err
    assert rc == TR.EXIT_CONFIG
    assert spy.created == [] and spy.http == []
    assert "kill_file_mismatch" in err and TG_TOKEN not in err and "SIZMA-TOKEN" not in err
    # tutarli env -> daemon kurulur
    good = _tg_main_env(tmp_path, root)
    rc = TR.main(["daemon"], env=good, http_post=spy.http_post, now_fn=lambda: NOW, sleep=lambda s: None, stop=lambda: True)
    assert rc == TR.EXIT_OK and len(spy.created) == 1
    # LIVE_BOTS yok -> taban (kagit) davranisi
    legacy = {k: v for k, v in good.items() if not k.startswith("LIVE_")}
    legacy.update(KILL_FILE=f"{root}/shared/KILL", LADDER_BOTS="", ENGINE_STATUS_PATH=f"{root}/var/learner/status.json")
    rc = TR.main(["daemon"], env=legacy, http_post=spy.http_post, now_fn=lambda: NOW, sleep=lambda s: None, stop=lambda: True)
    assert rc == TR.EXIT_OK and len(spy.created) == 2


def _status_doc(bot, mode, now, exchange=None, **kw):
    d = {"schema": "engine-status/1", "bot": bot, "mode": mode, "loop_at": z(now - timedelta(seconds=5)),
         "started_at": z(now - timedelta(hours=1)), "last_candle_open": z(now - timedelta(minutes=10)), "trigger_tf": "1h",
         "gate": {"ok": True, "code": "ok"}, "kill": False, "open_positions": [], "open_trade_ids": [], "dry_run": mode != "live",
         "counters": {"ledger_errors": 0}}
    if exchange is not None:
        d["exchange"] = exchange
    d.update(kw)
    return d


def put_status(var: Path, bot: str, doc: dict):
    p = var / bot / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc))


def health_env(tmp_path, root, **over):
    env = {"ENGINE_VAR_DIR": f"{root}/var", "BACKUP_DIR": str(tmp_path / "bk"), "HEALTH_BOTS": "learner,twin",
           "PAUSE_FILE": f"{root}/shared/PAUSE", "STATE_DIR": str(tmp_path / "state"), "ENGINE_CONFIG_DIR": f"{root}/config",
           "LIVE_BOTS": "learner", "LIVE_VAR_DIR": f"{root}/var-live", "LIVE_PAUSE_FILE": f"{root}/shared/live/PAUSE"}
    env.update(over)
    return {k: v for k, v in env.items() if v is not None}


def test_y_07_health_collect_reads_live_bot_from_live_paths(tmp_path):
    R = load_script("health_run")
    root, _ = live_root(tmp_path)
    ex = {"reachable": True, "last_sync": z(NOW), "naked": []}
    put_status(root / "var-live", "learner", _status_doc("learner", "live", NOW, ex))
    put_status(root / "var", "twin", _status_doc("twin", "paper", NOW))
    snap = R.collect(health_env(tmp_path, root), {}, NOW)
    assert snap.api["learner"].mode == "live"
    assert snap.api["twin"].mode == "paper"


def test_y_08_health_collect_with_invalid_live_env_does_not_crash(tmp_path):
    R = load_script("health_run")
    root, _ = live_root(tmp_path)
    snap = R.collect(health_env(tmp_path, root, LIVE_VAR_DIR=None), {}, NOW)
    a = snap.api["learner"]
    assert a.expect_exchange is True and a.ping_ok is None
    assert tuple(snap.live_path_issues) == ("live_var_dir_missing",)


def _seed_pair(base: Path, bot: str):
    from trader_core import ledger as L
    from trader_engine.state import StateStore
    base.mkdir(parents=True, exist_ok=True)
    L.open_ledger(str(base / "ledger.sqlite"), bot, create=True).close()
    StateStore(str(base / "state.sqlite"), bot=bot).close()


BK_NOW = datetime(2026, 12, 5, 3, 0, tzinfo=UTC)


def test_y_09_backup_covers_live_dir_and_skips_archived_paper_job(tmp_path):
    B = load_script("health_backup")
    var, var_live = tmp_path / "var", tmp_path / "var-live"
    for bot in ("learner", "twin"):
        _seed_pair(var / bot, bot)
    _seed_pair(var_live / "learner", "learner")
    code, m = B.run_backup(str(tmp_path / "bk1"), str(var), 14, now=BK_NOW, free_bytes=lambda: 10 ** 12,
                           bots=("learner", "twin"), bot_dirs={"learner": str(var_live)})
    assert code == 0 and m["ok"] is True, m
    assert set(m["files"]) == {"ledger_learner.sqlite", "state_learner.sqlite", "ledger_twin.sqlite", "state_twin.sqlite",
                               "ledger_learner@live.sqlite", "state_learner@live.sqlite"}
    assert all(v["ok"] for v in m["files"].values())
    # kagit learner defteri yok (arsivlenmis) -> kagit anahtarlari yok, yedek yine ok
    (var / "learner" / "ledger.sqlite").unlink()
    code, m = B.run_backup(str(tmp_path / "bk2"), str(var), 14, now=BK_NOW, free_bytes=lambda: 10 ** 12,
                           bots=("learner", "twin"), bot_dirs={"learner": str(var_live)})
    assert code == 0 and m["ok"] is True, m
    assert "ledger_learner.sqlite" not in m["files"] and "state_learner.sqlite" not in m["files"]
    assert "ledger_learner@live.sqlite" in m["files"] and "ledger_twin.sqlite" in m["files"]
    # bot_dirs=None -> tabanla ayni anahtarlar
    _seed_pair(var / "learner", "learner")
    code, m = B.run_backup(str(tmp_path / "bk3"), str(var), 14, now=BK_NOW, free_bytes=lambda: 10 ** 12, bots=("learner", "twin"),
                           bot_dirs=None)
    assert set(m["files"]) == {"ledger_learner.sqlite", "state_learner.sqlite", "ledger_twin.sqlite", "state_twin.sqlite"}


def test_y_10_backup_main_with_invalid_live_env_fails_live_jobs_only(tmp_path, monkeypatch):
    B = load_script("health_backup")
    var = tmp_path / "var"
    for bot in ("learner", "twin"):
        _seed_pair(var / bot, bot)
    for k, v in {"BACKUP_DIR": str(tmp_path / "bk"), "ENGINE_VAR_DIR": str(var), "HEALTH_BOTS": "learner,twin",
                 "LIVE_BOTS": "learner"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LIVE_VAR_DIR", raising=False)
    monkeypatch.delenv("LIVE_PAUSE_FILE", raising=False)
    assert B.main() == B.EXIT_FAILED
    manifests = list((tmp_path / "bk").glob("*/MANIFEST.json"))
    assert manifests
    files = json.loads(manifests[0].read_text())["files"]
    live = {k: v for k, v in files.items() if "@live" in k}
    assert live and all(v["ok"] is False for v in live.values())
    assert all("live_env_invalid" in json.dumps(v) for v in live.values())
    for k in ("ledger_twin.sqlite", "state_twin.sqlite"):
        assert files[k]["ok"] is True


def _write_env(path: Path, kv: dict, mode=0o600):
    path.write_text("# yorum\n" + "".join(f"{k}={v}\n" for k, v in kv.items()))
    os.chmod(path, mode)


def build_preflight_tree(tmp: Path):
    """Tutarli on denetim duzenegi: etc dizini + tmp config. Sizma testi icin tum degerler SIZMA- ile baslar."""
    root, cdir = live_root(tmp)
    tag = "SIZMA-etiket-alt1"
    lj = json.loads(read(cdir / "engine.live.json"))
    lj["live"]["account_tag"] = tag
    (cdir / "engine.live.json").write_text(json.dumps(lj))
    etc = tmp / "etc"
    etc.mkdir()
    sec = {"key": "SIZMA-LIVEKEY-" + "a" * 32, "secret": "SIZMA-LIVESECRET-" + "b" * 32, "tkey": "SIZMA-TESTNETKEY-" + "c" * 32,
           "tsecret": "SIZMA-TESTNETSEC-" + "d" * 32, "tag": tag, "token": TG_TOKEN}
    _write_env(etc / "trader-live.env", {"BINANCE_API_KEY": sec["key"], "BINANCE_API_SECRET": sec["secret"], "LIVE_CONFIRM": tag})
    _write_env(etc / "trader-testnet.env", {"BINANCE_API_KEY": sec["tkey"], "BINANCE_API_SECRET": sec["tsecret"]})
    f = live_fields(root)
    _write_env(etc / "trader-telegram.env", {"TELEGRAM_BOT_TOKEN": sec["token"], "TELEGRAM_CHAT_ID": "424242", **f})
    _write_env(etc / "trader-health.env", {"HEARTBEAT_URL": "https://example.invalid/x", "LIVE_BOTS": "learner",
                                           "LIVE_VAR_DIR": f["LIVE_VAR_DIR"], "LIVE_PAUSE_FILE": f["LIVE_PAUSE_FILE"]})
    _write_env(etc / "trader-lesson.env", {"LEDGER_PATH": f["LEDGER_PATH"]})
    (etc / "trader-release").write_text(f"COMMIT={HEX40}\n")
    os.chmod(etc / "trader-release", 0o644)
    return etc, cdir, sec, root


def _preflight(capsys, etc, cdir, **kw):
    import importlib
    P = importlib.import_module("live_preflight")
    rc = P.main(["--skip-owner"], etc_dir=str(etc), config_dir=str(cdir), id_groups=kw.pop("id_groups", ("trader",)))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _verdicts(out: str) -> dict[str, str]:
    d = {}
    for ln in out.splitlines():
        m = re.match(r"^(OK|FAIL) (\w+)$", ln.strip())
        assert m, f"beklenmeyen cikti satiri: {ln!r}"
        d[m.group(2)] = m.group(1)
    return d


def test_y_11_live_preflight_consistent_then_each_break_fails_its_check(tmp_path, capsys):
    etc, cdir, sec, root = build_preflight_tree(tmp_path)
    rc, out, err = _preflight(capsys, etc, cdir)
    v = _verdicts(out)
    assert rc == 0 and v and set(v.values()) == {"OK"}, out
    assert {"env_perms", "live_env_complete", "live_confirm_matches", "keys_not_testnet", "telegram_paths", "health_paths",
            "ortak_env_paths", "trader_not_in_tg", "release_pinned"} <= set(v)
    secrets = [sec["key"], sec["secret"], sec["tkey"], sec["tsecret"], sec["tag"], sec["token"]]

    def check(name, mutate, **kw):
        etc2, cdir2, sec2, root2 = build_preflight_tree(tmp_path / f"m_{name}")
        mutate(etc2, sec2, root2)
        rc2, out2, err2 = _preflight(capsys, etc2, cdir2, **kw)
        assert rc2 == 1, (name, out2)
        assert _verdicts(out2).get(name) == "FAIL", (name, out2)
        for s in secrets:
            assert s not in out2 and s not in err2, f"{name}: gizli deger sizdi"

    def perms(etc2, *_):
        os.chmod(etc2 / "trader-health.env", 0o640)

    def confirm(etc2, sec2, *_):
        _write_env(etc2 / "trader-live.env", {"BINANCE_API_KEY": sec2["key"], "BINANCE_API_SECRET": sec2["secret"],
                                              "LIVE_CONFIRM": "SIZMA-baska-etiket"})

    def same_key(etc2, sec2, *_):
        _write_env(etc2 / "trader-testnet.env", {"BINANCE_API_KEY": sec2["key"], "BINANCE_API_SECRET": sec2["tsecret"]})

    def tg_kill(etc2, sec2, root2):
        _write_env(etc2 / "trader-telegram.env", {"TELEGRAM_BOT_TOKEN": sec2["token"], "TELEGRAM_CHAT_ID": "424242",
                                                  **{**live_fields(root2), "KILL_FILE": f"{root2}/shared/KILL"}})

    def health_var(etc2, sec2, root2):
        _write_env(etc2 / "trader-health.env", {"LIVE_BOTS": "learner", "LIVE_VAR_DIR": f"{root2}/var-baska",
                                                "LIVE_PAUSE_FILE": live_fields(root2)["LIVE_PAUSE_FILE"]})

    def no_release(etc2, *_):
        (etc2 / "trader-release").unlink()

    def short_key(etc2, sec2, *_):
        _write_env(etc2 / "trader-live.env", {"BINANCE_API_KEY": "SIZMA-kisa", "BINANCE_API_SECRET": sec2["secret"],
                                              "LIVE_CONFIRM": sec2["tag"]})
    check("env_perms", perms)
    check("live_confirm_matches", confirm)
    check("keys_not_testnet", same_key)
    check("telegram_paths", tg_kill)
    check("health_paths", health_var)
    check("release_pinned", no_release)
    check("live_env_complete", short_key)
    check("trader_not_in_tg", lambda *_: None, id_groups=("trader", "trader-tg"))


def test_y_12_canli_duman_wrapper_static_checks():
    p = DEPLOY / "canli_duman.sh"
    assert p.exists()
    assert subprocess.run(["bash", "-n", str(p)], capture_output=True).returncode == 0
    t = read(p)
    for needle in ("systemd-run", "User=trader", "EnvironmentFile=/etc/trader-live.env", "smoke_live.py --env live"):
        assert needle in t, needle
    code = noncomment(t)
    assert "set -x" not in code and "cat /etc/trader-live.env" not in code
    assert not re.search(r"(^|[;&|\s])source\s", code, re.M)
    assert not re.search(r"(^|[;&|\s])\.\s+/etc/", code, re.M)


def test_y_13_env_examples_carry_empty_live_fields_and_non_live_install_leaves_them_empty(tmp_path):
    for n in ("trader-telegram.env.example", "trader-health.env.example"):
        kv = dict(ln.split("=", 1) for ln in read(DEPLOY / n).splitlines() if ln.strip() and not ln.lstrip().startswith("#") and "=" in ln)
        for k in ("LIVE_BOTS", "LIVE_VAR_DIR", "LIVE_PAUSE_FILE"):
            assert kv.get(k) == "", (n, k)
    out = run_env_step(tmp_path / "e")
    for n in ("trader-telegram.env", "trader-health.env"):
        for k in ("LIVE_BOTS", "LIVE_VAR_DIR", "LIVE_PAUSE_FILE"):
            assert out[n].get(k) == "", (n, k)
    assert "CANLIYA CIKISTA ENGINE_VAR_DIR" not in read(DEPLOY / "trader-health.env.example")


def test_y_14_live_paths_imports_only_stdlib():
    assert stdlib_only(SRC / "trader_core" / "live_paths.py") == []


def run_pytest(*args: str, timeout: int = 1800) -> None:
    """Mevcut testlerin DEGISMEDEN gectigini dogrular (yeni surec; ayni yorumlayici)."""
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *args],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1500:]


# ====================================================================================== T: /devam her kipte (O7)
def make_tg(tmp_path, **daemon_kw):
    import test_telegram_spec as TS
    from trader_core import telegram as tgm
    from trader_engine.clock import SimClock
    from trader_engine.killswitch import Killswitch
    tmp_path.mkdir(parents=True, exist_ok=True)
    e = types.SimpleNamespace(TS=TS)
    e.tmp, e.fake, e.clk, e.sleeps = tmp_path, TS.FakeTelegram(), TS.Clk(), []
    e.kill_file, e.status_path = str(tmp_path / "KILL"), str(tmp_path / "status.json")
    e.cfg = tgm.TelegramConfig(token=TS.TOKEN, chat_id=TS.CID, var_dir=str(tmp_path / "var"), kill_file=e.kill_file,
                               status_path=e.status_path,
                               health_state=str(tmp_path / "health.json"))
    (tmp_path / "var").mkdir()
    e.client = tgm.TelegramClient(TS.TOKEN, http_post=e.fake.post, sleep=e.sleeps.append)
    e.ks = Killswitch(e.kill_file, SimClock(TS.T0))
    e.d = tgm.TelegramDaemon(e.cfg, e.client, now_fn=e.clk, sleep=e.sleeps.append, random_code=lambda: "4821",
                             killswitch=TS._ks_for(e.cfg, e.clk), **daemon_kw)
    e.clk.advance(2)
    e.send = lambda text, uid=None, **kw: e.d.process_updates([TS.msg(uid or TS._next(), text, kw.pop("date", e.clk()), **kw)])
    e.active = lambda: Path(e.kill_file).exists()
    return e


def tg_status(e, mode="paper", kill_state="flat", *, drop=()):
    e.TS.write_status(e.status_path, mode=mode, kill_state=kill_state)
    if drop:
        d = json.loads(Path(e.status_path).read_text())
        for k in drop:
            d.pop(k, None)
        Path(e.status_path).write_text(json.dumps(d))


def tg_devam(e):
    e.send("/devam")
    e.send("4821")


def test_t_01_paper_devam_requires_flat_state(tmp_path):
    e = make_tg(tmp_path / "x")
    tg_status(e, "paper", "exiting")
    e.TS.set_kill(e, by="me", reason="manual")
    tg_devam(e)
    assert e.active() and "kapanis" in e.fake.alltext().lower().replace("ı", "i")
    for i, (ks, drop) in enumerate(((None, ()), ("flat", ("kill_state",)), ("none", ()))):
        e = make_tg(tmp_path / f"y{i}")
        tg_status(e, "paper", ks, drop=drop)
        e.TS.set_kill(e, by="me", reason="manual")
        assert "flat" in (e.d._devam_refusal() or "")
        tg_devam(e)
        assert e.active(), f"kill_state={ks!r} drop={drop}: KILL kalkti"
        assert e.TS.code_of(e.fake.alltext()) is None


def test_t_02_paper_flat_devam_sends_code_and_clears_kill_on_confirm(tmp_path):
    e = make_tg(tmp_path)
    tg_status(e, "paper", "flat")
    e.TS.set_kill(e, by="me", reason="manual")
    e.send("/devam")
    assert e.active() and e.TS.code_of(e.fake.alltext()) == "4821"
    e.send("4821")
    assert not e.active()


def test_t_03_live_devam_origin_and_flat_rules(tmp_path):
    e = make_tg(tmp_path / "a")
    tg_status(e, "live", "flat")
    e.TS.set_kill(e, by="telegram:482", reason="user_cmd")
    tg_devam(e)
    assert not e.active()
    e = make_tg(tmp_path / "b")
    tg_status(e, "live", "exiting")
    e.TS.set_kill(e, by="telegram:482", reason="user_cmd")
    tg_devam(e)
    assert e.active()
    e = make_tg(tmp_path / "c")
    tg_status(e, "live", "flat")
    e.TS.set_kill(e, by="cli", reason="manual")
    tg_devam(e)
    assert e.active()


def test_t_04_expect_status_mode_blocks_wrong_or_missing_mode(tmp_path):
    e = make_tg(tmp_path / "a", expect_status_mode="live")
    tg_status(e, "paper", "flat")
    e.TS.set_kill(e, by="telegram:482", reason="user_cmd")
    assert "beklenen kipte" in (e.d._devam_refusal() or "")
    tg_devam(e)
    assert e.active()
    e = make_tg(tmp_path / "b", expect_status_mode="live")
    tg_status(e, "live", "flat", drop=("mode",))
    e.TS.set_kill(e, by="telegram:482", reason="user_cmd")
    tg_devam(e)
    assert e.active()
    e = make_tg(tmp_path / "c", expect_status_mode="live")                 # dogru kip -> gecer
    tg_status(e, "live", "flat")
    e.TS.set_kill(e, by="telegram:482", reason="user_cmd")
    tg_devam(e)
    assert not e.active()
    e = make_tg(tmp_path / "d", expect_status_mode=None)                   # None -> bu denetim yapilmaz
    tg_status(e, "paper", "flat")
    e.TS.set_kill(e, by="me", reason="manual")
    assert e.d._devam_refusal() is None
    tg_devam(e)
    assert not e.active()


def test_t_05_confirmation_rechecks_preconditions(tmp_path):
    e = make_tg(tmp_path)
    tg_status(e, "paper", "flat")
    e.TS.set_kill(e, by="me", reason="manual")
    e.send("/devam")
    assert e.TS.code_of(e.fake.alltext()) == "4821"
    tg_status(e, "paper", "exiting")
    e.send("4821")
    assert e.active()


def test_t_06_daemon_built_with_expect_status_mode_live_only_for_live_bots(tmp_path, monkeypatch):
    TR = load_script("telegram_run")
    root, _ = live_root(tmp_path)
    spy = _TgSpy(monkeypatch)
    good = _tg_main_env(tmp_path, root)
    assert TR.main(["daemon"], env=good, http_post=spy.http_post, now_fn=lambda: NOW, sleep=lambda s: None, stop=lambda: True) == TR.EXIT_OK
    assert spy.created[-1].get("expect_status_mode") == "live"
    legacy = {k: v for k, v in good.items() if not k.startswith("LIVE_")}
    legacy.update(KILL_FILE=f"{root}/shared/KILL", LADDER_BOTS="", ENGINE_STATUS_PATH=f"{root}/var/learner/status.json")
    assert TR.main(["daemon"], env=legacy, http_post=spy.http_post, now_fn=lambda: NOW, sleep=lambda s: None, stop=lambda: True) == TR.EXIT_OK
    assert spy.created[-1].get("expect_status_mode") is None


def test_t_07_existing_telegram_suites_still_pass_with_flat_fixtures():
    """Duzenek 'kill_state=flat' ile guncellenir, kural gevsetilmez: mevcut Telegram test dosyalari degismeden/guncel gecer."""
    run_pytest("tests/test_telegram_spec.py", "tests/test_telegram_pause_spec.py", "tests/test_telegram_ladder_spec.py",
               "tests/test_telegram_impl_smoke.py", "tests/test_telegram_pause_impl_smoke.py")


# ====================================================================================== H: saglik
def _snap_h(api, **kw):
    from trader_core import health as H
    return H.HealthSnapshot(now=NOW, timeframe_s=3600, api=api, ledger={}, disk_free_bytes=50 * H.GIB, 
                            last_backup_at=NOW - timedelta(hours=1), **kw)


def _probe_h(**kw):
    from trader_core import health as H
    base = dict(ping_ok=True, last_process_at=NOW, last_candle_open=NOW, open_trade_ids=(), dry_run=False, gate_code="ok", kill=False,
                ledger_errors=0, unprotected_ids=(), mode="live", has_exchange=True, exchange_reachable=True, exchange_last_sync=NOW,
                naked=())
    base.update(kw)
    return H.ApiProbe(**base)


def _eval_h(api, cfg=None, **kw):
    from trader_core import health as H
    cfg = cfg or H.HealthConfig(require_bots=("learner",), multiple_threshold=50)
    rep = H.evaluate(_snap_h(api, **kw), cfg)
    return rep, {r.name: r for r in rep.results}


def test_h_01_broker_counts_ban_sourced_unverified_separately(tmp_path, denv_factory):
    for case, want in (("ban_429", (1, 1)), ("uncertain", (1, 0))):
        e = D8.d2_env(tmp_path / case, denv_factory)
        for _ in range(6):
            if case == "ban_429":
                e.ex.inject("/fapi/v2/positionRisk", FakeResp(429, {"code": -1003, "msg": "rate"}, {"Retry-After": "7"}))
            else:
                e.ex.inject("/fapi/v2/positionRisk", FakeResp(503, {"code": -1001, "msg": "x"}))
        r = e.broker.market_order(D8.entry_req())
        assert r.status == "rejected" and r.reason == "not_prepared", r
        c = e.broker.counters()
        assert (c["account_mode_unverified"], c["account_mode_unverified_ban"]) == want, (case, c)
        h = e.broker.health()
        assert {"account_mode_drift", "account_mode_unverified", "account_mode_unverified_ban"} <= set(h)
        assert h["account_mode_unverified_ban"] == want[1]
    # sapma sayaci ban sayacini artirmaz
    e = D8.d2_env(tmp_path / "drift", denv_factory)
    e.ex.lev[D8.SYM] = e.cfg.leverage + 1
    e.broker.market_order(D8.entry_req())
    assert e.broker.counters()["account_mode_drift"] == 1 and e.broker.counters()["account_mode_unverified_ban"] == 0


def _status_build(mode, exchange=None):
    from trader_engine.status import StatusWriter
    f = {"tf": "1h", "param_version_id": 1, "strategy_name": "s", "strategy_version": "1", "entries_blocked_reason": None,
         "gate_code": "ok", "entries_open": True, "kill": False, "kill_state": None, "wallet": 1000.0, "equity": 1000.0,
         "day_start_equity": 1000.0, "open_positions": [], "counters": {}, "last_minute_ts": None,
         "last_decision_close": None, "last_candle_open": None, "ml": None, "pause": None}
    if exchange is not None:
        f["exchange"] = exchange
    cfg = types.SimpleNamespace(bot="learner", mode=mode, loop_sleep_s=5.0)
    eng = types.SimpleNamespace(status_fields=lambda: f, broker=types.SimpleNamespace(last_ban=None))
    return StatusWriter("x", types.SimpleNamespace(now=lambda: NOW), cfg).build(eng)


def test_h_02_status_exchange_block_carries_account_mode_ints():
    ex = {"reachable": True, "naked": [], "account_mode_drift": 1, "account_mode_unverified": 3, "account_mode_unverified_ban": 2}
    for mode in ("testnet", "live"):
        d = _status_build(mode, ex)
        assert d["exchange"]["account_mode"] == {"drift": 1, "unverified": 3, "unverified_ban": 2}
        json.dumps(d)
    d = _status_build("live", {"reachable": True, "naked": [], "account_mode_drift": "x"})
    assert d["exchange"]["account_mode"] == {"drift": None, "unverified": None, "unverified_ban": None}
    paper = _status_build("paper")
    assert "exchange" not in paper
    assert set(paper) == {k for k in paper}                   # kagit durum dosyasi anahtar kumesi (blok yok)


def _status_file(tmp_path, account_mode, mode="live"):
    ex = {"reachable": True, "last_sync": z(NOW), "naked": []}
    if account_mode is not None:
        ex["account_mode"] = account_mode
    doc = _status_doc("learner", mode, NOW, ex)
    p = tmp_path / "learner" / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc))
    return p


def test_h_03_probe_status_maps_account_mode_block(tmp_path):
    R = load_script("health_run")
    p = _status_file(tmp_path / "a", {"drift": 2, "unverified": 5, "unverified_ban": 3})
    a = R.probe_status(str(p), "learner", NOW)[0]
    assert (a.acct_drift, a.acct_unverified) == (2, 2)
    p = _status_file(tmp_path / "b", {"drift": 0, "unverified": 1, "unverified_ban": 4})
    assert R.probe_status(str(p), "learner", NOW)[0].acct_unverified == 0
    p = _status_file(tmp_path / "c", None)
    a = R.probe_status(str(p), "learner", NOW)[0]
    assert a.acct_drift is None and a.acct_unverified is None


def test_h_04_account_mode_check_priority_and_restart_handling():
    from trader_core import health as H
    prev = {"learner": (0, 0)}

    def res(drift, unv, prev_am=prev, mode="live"):
        _, r = _eval_h({"learner": _probe_h(acct_drift=drift, acct_unverified=unv, mode=mode)}, prev_account_mode=prev_am)
        return r.get("account_mode:learner")
    r = res(1, 0)
    assert r.status is H.Status.CRIT and r.code == "account_mode_drift"
    r = res(0, 1)
    assert r.status is H.Status.WARN and r.code == "account_mode_unverified"
    assert res(0, 0).status is H.Status.OK
    r = res(None, 0)
    assert r.status is H.Status.UNKNOWN and r.code == "account_mode_unknown"
    assert res(4, 7, prev_am=None).status is H.Status.OK                        # onceki yok -> artis 0
    assert res(4, 7, prev_am={}).status is H.Status.OK
    r = res(1, 0, prev_am={"learner": (5, 9)})                                  # yeniden baslama: simdiki < onceki -> simdiki
    assert r.status is H.Status.CRIT and r.code == "account_mode_drift"
    assert res(0, 0, mode="paper") is None or "account_mode:learner" not in _eval_h(
        {"learner": _probe_h(mode="paper", has_exchange=False, acct_drift=3, acct_unverified=3)}, prev_account_mode=prev)[1]


def test_h_05_ban_sourced_unverified_increase_is_ok(tmp_path):
    from trader_core import health as H
    R = load_script("health_run")
    p = _status_file(tmp_path, {"drift": 0, "unverified": 4, "unverified_ban": 4})
    api = R.probe_status(str(p), "learner", NOW)[0]
    _, r = _eval_h({"learner": api}, prev_account_mode={"learner": (0, 0)})
    assert r["account_mode:learner"].status is H.Status.OK


def test_h_06_account_mode_alerts_immediate_and_texts():
    from trader_core import health as H
    assert "account_mode_drift" in H.IMMEDIATE_CODES and "account_mode_unverified" in H.IMMEDIATE_WARN_CODES
    cfg = H.HealthConfig(require_bots=("learner",), multiple_threshold=50)
    for (drift, unv), code, level in (((1, 0), "account_mode_drift", H.Status.CRIT), ((0, 1), "account_mode_unverified", H.Status.WARN)):
        rep, _ = _eval_h({"learner": _probe_h(acct_drift=drift, acct_unverified=unv)}, cfg, prev_account_mode={"learner": (0, 0)})
        alerts, st = H.plan_alerts(rep, H.empty_state(), NOW, cfg)
        assert any(a.code == code and a.level is level for a in alerts), (code, [a.code for a in alerts])
        # sonraki kosu: artis 0 -> duzelme iletisi
        rep2, _ = _eval_h({"learner": _probe_h(acct_drift=drift, acct_unverified=unv)}, cfg, prev_account_mode={"learner": (drift, unv)})
        alerts2, _ = H.plan_alerts(rep2, st, NOW + timedelta(minutes=5), cfg)
        assert any(a.code == code and a.level is H.Status.OK for a in alerts2), (code, [(a.code, a.level) for a in alerts2])
    s, d, _ = H._health_tr("account_mode:learner", "account_mode_drift")
    assert s == "Hesap ayarı değişmiş, yeni işlem açılmadı" and d == "Hesap ayarı yeniden doğru"
    s, d, _ = H._health_tr("account_mode:learner", "account_mode_unverified")
    assert s == "Hesap ayarı doğrulanamadı, bir giriş atlandı" and d == "Hesap ayarı yeniden doğrulanıyor"


def test_h_07_run_once_twice_raises_unverified_alert_and_stores_account_mode(tmp_path, monkeypatch):
    from trader_core import health as H
    R = load_script("health_run")
    root, _ = live_root(tmp_path)
    cfg50 = dataclasses.replace(H.DEFAULT_CFG, multiple_threshold=50)
    orig_plan = H.plan_alerts
    monkeypatch.setattr(H, "plan_alerts", lambda report, state, now, cfg=None, **kw: orig_plan(report, state, now, cfg50, **kw))
    env = health_env(tmp_path, root, HEALTH_BOTS="learner", LIVE_BOTS=None, LIVE_VAR_DIR=None, LIVE_PAUSE_FILE=None,
                     ENGINE_CONFIG_DIR=None, HEARTBEAT_URL=None)
    var = root / "var"
    state_path = tmp_path / "state" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    class Hb:
        def ok(self, report):
            return True

        def fail(self, report):
            return True

    def run(now, drift, unv):
        ex = {"reachable": True, "last_sync": z(now), "naked": [], "account_mode": {"drift": drift, "unverified": unv, "unverified_ban": 0}}
        put_status(var, "learner", _status_doc("learner", "testnet", now, ex))
        notifier = H.NullNotifier()
        R.run_once(env, now=now, state_path=str(state_path), notifier=notifier, sender=Hb())
        return notifier.sent
    run(NOW, 0, 0)
    sent = run(NOW + timedelta(minutes=5), 0, 2)
    assert any(a.code == "account_mode_unverified" for a in sent), [(a.code, a.fingerprint) for a in sent]
    st = json.loads(state_path.read_text())
    assert list(st["account_mode"]["learner"]) == [0, 2]


def test_h_08_exchange_ban_is_crit_with_expected_exchange_even_without_status_file():
    from trader_core import health as H
    ban = H.BanProbe(host="fapi.example.test", until=NOW + timedelta(minutes=30), http=418, source="feed")
    rep, r = _eval_h({"learner": H.ApiProbe(expect_exchange=True)}, bans=(ban,))
    assert r["exchange_ban"].status is H.Status.CRIT and r["exchange_ban"].code == "exchange_ban_open_positions"
    rep, r = _eval_h({"learner": H.ApiProbe(expect_exchange=False)}, bans=(ban,))
    assert r["exchange_ban"].status is H.Status.WARN and r["exchange_ban"].code == "exchange_ban"


def test_h_09_expect_exchange_produces_naked_and_reachable_checks_unknown():
    from trader_core import health as H
    _, r = _eval_h({"learner": H.ApiProbe(expect_exchange=True)})
    assert r["naked_position:learner"].status is H.Status.UNKNOWN
    assert r["exchange_reachable:learner"].status is H.Status.UNKNOWN
    _, r = _eval_h({"learner": H.ApiProbe(expect_exchange=False)})
    assert "naked_position:learner" not in r and "exchange_reachable:learner" not in r


def test_h_10_collect_sets_expect_exchange_for_live_bots_and_shadow(tmp_path):
    R = load_script("health_run")
    root, _ = live_root(tmp_path)
    shadow = root / "var-testnet"
    shadow.mkdir(parents=True)
    env = health_env(tmp_path, root, HEALTH_SHADOW_VAR_DIR=str(shadow))
    snap = R.collect(env, {}, NOW)
    assert snap.api["learner@testnet"].expect_exchange is True
    assert snap.api["learner"].expect_exchange is True and snap.api["twin"].expect_exchange is False
    paper = R.collect(health_env(tmp_path, root, LIVE_BOTS=None, LIVE_VAR_DIR=None, LIVE_PAUSE_FILE=None), {}, NOW)
    assert paper.api["learner"].expect_exchange is False and paper.api["twin"].expect_exchange is False


def test_h_11_live_paths_check_only_when_live_bots_configured():
    from trader_core import health as H
    _, r = _eval_h({"learner": _probe_h()}, live_path_issues=None)
    assert "live_paths" not in r
    _, r = _eval_h({"learner": _probe_h()}, live_path_issues=())
    assert r["live_paths"].status is H.Status.OK
    cfg = H.HealthConfig(require_bots=("learner",), multiple_threshold=50)
    rep, r = _eval_h({"learner": _probe_h()}, cfg, live_path_issues=("kill_file_mismatch",))
    assert r["live_paths"].status is H.Status.CRIT and r["live_paths"].code == "live_paths_mismatch"
    assert "kill_file_mismatch" in r["live_paths"].detail
    assert "live_paths_mismatch" in H.IMMEDIATE_CODES
    alerts, _ = H.plan_alerts(rep, H.empty_state(), NOW, cfg)
    assert any(a.code == "live_paths_mismatch" for a in alerts)
    s, d, _ = H._health_tr("live_paths", "live_paths_mismatch")
    assert s == "Canlı bot ayar yolları tutarsız" and d == "Canlı bot ayar yolları düzeldi"


def test_h_12_collect_flags_live_bot_whose_status_mode_is_not_live(tmp_path):
    R = load_script("health_run")
    root, _ = live_root(tmp_path)
    put_status(root / "var-live", "learner", _status_doc("learner", "paper", NOW))
    snap = R.collect(health_env(tmp_path, root), {}, NOW)
    assert "status_mode_mismatch:learner" in tuple(snap.live_path_issues or ())


def test_h_14_existing_constructors_keep_working():
    from trader_core import health as H
    a = H.ApiProbe(True, NOW, NOW, (), True, "ok", False, 0, (), "live", True, True, NOW, ())
    assert a.acct_drift is None and a.acct_unverified is None and a.expect_exchange is False
    assert H.ApiProbe().expect_exchange is False
    s = H.HealthSnapshot(now=NOW)
    assert s.prev_account_mode is None and s.live_path_issues is None
    H.HealthSnapshot(now=NOW, timeframe_s=3600, api={"learner": a}, ledger={})


# ====================================================================================== D: devralinan kucukler
FAPI = "ban.fapi.example.test.json"


def test_d1_01_write_ban_fsyncs_the_directory(tmp_path, monkeypatch):
    from trader_core import ban_store as B
    real, recs = os.fsync, []

    def spy(fd):
        recs.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return real(fd)
    monkeypatch.setattr(os, "fsync", spy)
    now_ms = 1_800_000_000_000
    assert B.write_ban(str(tmp_path / FAPI), until_ms=now_ms + 120_000, http=418, source="feed", now_ms=now_ms) is True
    assert len(recs) >= 2 and any(recs), f"dizin fsync yok: {recs}"


def test_d1_02_directory_fsync_failure_is_logged_not_raised(tmp_path, monkeypatch, caplog):
    from trader_core import ban_store as B
    real = os.fsync

    def spy(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(5, "EIO")
        return real(fd)
    monkeypatch.setattr(os, "fsync", spy)
    now_ms = 1_800_000_000_000
    path = str(tmp_path / FAPI)
    with caplog.at_level(logging.WARNING):
        assert B.write_ban(path, until_ms=now_ms + 120_000, http=418, source="feed", now_ms=now_ms) is True
    assert [r for r in caplog.records if r.levelno == logging.WARNING]
    rec = B.read_ban(path, now_ms)
    assert rec is not None and rec.until_ms == now_ms + 120_000
    monkeypatch.undo()
    run_pytest("tests/engine/test_dd7_spec.py", "-k", "test_p_")


def _backup_fixture(tmp_path):
    var = tmp_path / "var"
    _seed_pair(var / "learner", "learner")
    return var


@pytest.mark.parametrize("suffix", [".spool.corrupt.jsonl", ".spool.jsonl"])
def test_d2_01_unreadable_spool_size_fails_the_ledger_entry(tmp_path, monkeypatch, suffix):
    B = load_script("health_backup")
    var = _backup_fixture(tmp_path)
    (var / "learner" / ("ledger.sqlite" + suffix)).write_bytes(b'{"row":"x"}\n')
    real = os.path.getsize

    def getsize(p):
        if str(p).endswith(suffix):
            raise PermissionError(13, "izin yok")
        return real(p)
    monkeypatch.setattr(os.path, "getsize", getsize)
    code, m = B.run_backup(str(tmp_path / "bk"), str(var), 14, now=BK_NOW, free_bytes=lambda: 10 ** 12, bots=("learner",))
    assert code == B.EXIT_FAILED and m["ok"] is False
    assert m["files"]["ledger_learner.sqlite"]["ok"] is False
    monkeypatch.undo()
    # dosya yok -> DD-8 E4-2 aynen (basarili)
    (var / "learner" / ("ledger.sqlite" + suffix)).unlink()
    code, m = B.run_backup(str(tmp_path / "bk2"), str(var), 14, now=BK_NOW, free_bytes=lambda: 10 ** 12, bots=("learner",))
    assert code == 0 and m["ok"] is True


def test_d3_01_repo_live_layer_passes_guard_config():
    import smoke_live as SLV
    SLV.guard_config(load_live(), {"LIVE_CONFIRM": "canli-alt1"})


def test_d3_02_guard_config_is_positive_match_on_live_paths(tmp_path):
    import smoke_live as SLV
    import smoke_testnet_lib as SL
    cfg = load_live()
    env = {"LIVE_CONFIRM": "canli-alt1"}
    bads = [{"var_dir": "/x/var-canli"}, {"kill_file": "/x/shared/KILL"}, {"kill_file": "/x/live/KILL"},
            {"pause_file": "/x/shared/testnet/PAUSE"}, {"var_dir": "/x/var-live/var"}, {"pause_file": "/x/var-live/PAUSE"}]
    for repl in bads:
        with pytest.raises(SL.SafetyError):
            SLV.guard_config(dataclasses.replace(cfg, **repl), env)
    SLV.guard_config(dataclasses.replace(cfg, var_dir="/x/var-live", kill_file="/x/shared/live/KILL", pause_file="/x/shared/live/PAUSE"), env)


def _make_v3(path, stamp=None):
    from trader_core import ledger as L
    now_s = "2026-12-01T10:00:00.000Z"
    c = sqlite3.connect(str(path), isolation_level=None)
    for n in range(3):
        c.executescript("BEGIN IMMEDIATE;\n" + L.MIGRATIONS[n]("learner", now_s)
                        + f"INSERT INTO schema_migrations (from_version,to_version,applied_at) VALUES ({n},{n + 1},'{now_s}');\n"
                        + f"PRAGMA user_version={n + 1};\nCOMMIT;")
    c.execute("PRAGMA journal_mode=WAL")                 # uretimdeki defterler WAL kipinde (acmak ana dosyayi degistirmez)
    if stamp is not None:
        c.execute("INSERT INTO meta (key, value) VALUES ('account_stamp', ?)", (stamp,))
    c.close()


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _uv(path) -> int:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return c.execute("PRAGMA user_version").fetchone()[0]
    finally:
        c.close()


def test_d4_01_foreign_stamp_old_schema_ledger_is_not_migrated(tmp_path, boots):
    b = boots(tmp_path)
    Path(b.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    _make_v3(b.ledger_path, stamp="live:baska")
    sha0 = _sha(b.ledger_path)
    D8.boot_expect_exit(b, 8, "ledger_stamp_mismatch")
    assert _sha(b.ledger_path) == sha0 and _uv(b.ledger_path) == 3
    assert not [p for p in Path(b.ledger_path).parent.iterdir() if "premigrate" in p.name]
    assert b.ex.requests == []


def test_d4_02_unstamped_old_schema_ledger_is_rejected_not_migrated(tmp_path, boots):
    b = boots(tmp_path)
    Path(b.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    _make_v3(b.ledger_path)
    sha0 = _sha(b.ledger_path)
    D8.boot_expect_exit(b, 8, "ledger_stamp_missing")
    assert _sha(b.ledger_path) == sha0 and _uv(b.ledger_path) == 3
    assert not [p for p in Path(b.ledger_path).parent.iterdir() if "premigrate" in p.name]


def test_d4_03_matching_stamp_old_schema_ledger_migrates_and_boot_continues(tmp_path, boots):
    from trader_core import ledger as L
    b = boots(tmp_path)
    Path(b.ledger_path).parent.mkdir(parents=True, exist_ok=True)
    want = D8.want_stamp()
    _make_v3(b.ledger_path, stamp=want)
    D8.seed_state(b.state_path, {"account_stamp": want})
    b.build()
    assert _uv(b.ledger_path) == L.SCHEMA_VERSION
    assert [p for p in Path(b.ledger_path).parent.iterdir() if "premigrate" in p.name], "premigrate yedegi yok"


def test_d4_04_peek_meta_is_read_only_and_total(tmp_path):
    from trader_core import ledger as L
    assert L.peek_meta(str(tmp_path / "yok.sqlite"), "account_stamp") is None
    zero = tmp_path / "zero.sqlite"
    zero.write_bytes(b"")
    assert L.peek_meta(str(zero), "account_stamp") is None and zero.stat().st_size == 0
    nometa = tmp_path / "nometa.sqlite"
    c = sqlite3.connect(nometa)
    c.execute("CREATE TABLE t(x)")
    c.commit()
    c.close()
    sha = _sha(nometa)
    assert L.peek_meta(str(nometa), "account_stamp") is None and _sha(nometa) == sha
    v3 = tmp_path / "v3.sqlite"
    _make_v3(v3, stamp="live:x")
    sha = _sha(v3)
    assert L.peek_meta(str(v3), "account_stamp") == "live:x"
    assert L.peek_meta(str(v3), "yok_anahtar") is None
    assert _sha(v3) == sha and _uv(v3) == 3 and not list(tmp_path.glob("*premigrate*"))
    bad = tmp_path / "bad.sqlite"
    bad.write_bytes(b"bu bir sqlite dosyasi degil " * 20)
    sha = _sha(bad)
    with pytest.raises(L.LedgerError):
        L.peek_meta(str(bad), "account_stamp")
    assert _sha(bad) == sha


def test_d4_05_paper_engine_never_calls_peek_meta_and_golden_backtest_unchanged(tmp_path, monkeypatch):
    from trader_core import ledger as L
    from trader_engine import engine as E
    from trader_engine.clock import SimClock
    calls: list = []
    real = L.peek_meta
    monkeypatch.setattr(L, "peek_meta", lambda *a, **k: calls.append(a) or real(*a, **k))
    monkeypatch.setattr(E, "peek_meta", lambda *a, **k: calls.append(a) or real(*a, **k), raising=False)
    clock = SimClock(D8.T.BOOT)
    cfg, view = D8._paper_engine_pieces(tmp_path, clock)
    eng = E.build_engine(cfg, clock=clock, view=view, env={})
    try:
        eng.start()
    finally:
        eng.state.close()
        eng.ledger.close()
    assert calls == []
    monkeypatch.undo()
    run_pytest("tests/test_wp3_golden.py")


# ====================================================================================== belirsizlikler (SPEC-AMBIGUOUS ozeti)
# 1. Dosya yeri: §10 iki dosya der (tests/engine/test_dd9_spec.py + tests/test_dd9_deploy_spec.py); istek uzerine hepsi burada.
# 2. U-6 "init-ledger dizgisi yok": yalniz yorum disi satirlar denetlendi (yorumda anilmasi serbest). U-7 metin tamamina bakar.
# 3. U-5: ilk EnvironmentFile ve DIFF_KEYS disindaki TUM satirlar (Documentation= dahil) esit olmali; tablo Documentation'i anmiyor.
# 4. C-7: install.sh ic yapisi (blok sinirlari, degisken adlari: ROOT_DIR/RELEASE_DIR, root venv yolu `$ROOT_DIR/venv/bin/python`)
#    adlandirilmadigi icin `LIVE` kosullu ust duzey `if` bloklari stub'lanmis systemctl/git/as_trader ile calistirilir; etiket
#    sorgusu icin `git tag|for-each-ref|describe|show-ref|--points-at|--contains` herhangi biri kabul edilir.
# 5. E-3: env adimi bolgesi `copy_env() {` ile son `copy_env "` cagrisindan sonraki ilk `# ---- ` basligina kadar alinir.
# 6. H-13: LIVE_BOTS'un `evaluate`e nasil ulastigi adlandirilmamis; collect + make_cfg + evaluate uctan uca denendi.
# 7. Y-11 ortak_env_paths: ortak env tek basina LIVE_BOTS tasimadigindan bozulma senaryosu yok (yalniz OK yolu denendi).
# 8. T-7 (duzenek guncellemesi) dogrudan ifade edilemez; mevcut Telegram test paketlerinin gecmesi aranir.
# 9. R-9: testnet'te proc_guard basarisizlik WARNING'inin metni adlandirilmamis; anahtar sozcuk (proc_guard/dump/environ/ortam) aranir.
