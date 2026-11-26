"""Hazirlik 1: install.sh'in render sed'i sonrasi her birimin ExecStart/EnvironmentFile/WorkingDirectory/ReadWritePaths yolu
sunucuda GERCEKTEN var olacak mi? (render()'i gercekten calistirir; ag/systemd yok.)"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from readiness_support import (DEPLOY, ROOT, SERVER_TRADER_DIR as T, created_dirs, install_text, render_units, unit_kv,
                               with_ancestors)

VENV_PY = f"{T}/.venv/bin/python"
ROOT_LIB = "/usr/local/lib/trader-root"          # DD-9 §4.1: root birimleri kodu root sahipli kopyadan calistirir
ROOT_PY = f"{ROOT_LIB}/venv/bin/python"


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    return render_units(tmp_path_factory.mktemp("units"))


def _repo(p: str) -> Path:
    assert p == T or p.startswith(T + "/"), p
    return ROOT / p[len(T):].lstrip("/")


def test_no_placeholder_left_after_render(rendered):
    assert len(rendered) == len(list(DEPLOY.glob("trader-*.service"))) + len(list(DEPLOY.glob("trader-*.timer")))
    for name, txt in rendered.items():
        assert "/opt/trader" not in txt, name
        assert "/home/trader/trader" not in txt, name           # eski 'trader/trader' yazimi
        assert "/usr/bin/python3" not in txt, name              # sistem python'u degil, venv python'u
        assert "ccxt" not in txt and "freqtrade" not in txt, name


def test_exec_lines_resolve_to_real_module_script_subcommand(rendered):
    from trader_engine import cli
    subcmds = set(cli.build_parser()._subparsers._group_actions[0].choices)
    seen = {"module": 0, "script": 0}
    for name, txt in rendered.items():
        if not name.endswith(".service"):
            continue
        for k, v in unit_kv(txt):
            if k not in ("ExecStart", "ExecStartPre"):
                continue
            toks = shlex.split(v.lstrip("-"))
            exe = toks[0]
            assert exe in ("/bin/sh", "/bin/bash", VENV_PY, ROOT_PY), f"{name}: beklenmeyen calistirilabilir {exe}"
            if exe == ROOT_PY:
                script = next(t for t in toks[1:] if t.startswith(f"{ROOT_LIB}/current/"))
                assert (ROOT / script[len(f"{ROOT_LIB}/current/"):]).is_file(), f"{name}: betik yok {script}"
                seen["script"] += 1
            elif exe == VENV_PY:
                if "-m" in toks:
                    mod = toks[toks.index("-m") + 1]
                    assert (ROOT / "src" / mod).is_dir(), f"{name}: modul yok {mod}"
                    assert (ROOT / "src" / mod / "__main__.py").exists(), f"{name}: {mod}/__main__.py yok"
                    if mod == "trader_engine":
                        assert toks[toks.index("-m") + 2] in subcmds, f"{name}: alt komut yok"
                    seen["module"] += 1
                else:
                    script = next(t for t in toks[1:] if t.startswith(T))
                    assert _repo(script).is_file(), f"{name}: betik yok {script}"
                    seen["script"] += 1
            elif exe == "/bin/bash" and toks[1].startswith(f"{ROOT_LIB}/current/"):   # root sahipli surum agaci
                assert (ROOT / toks[1][len(f"{ROOT_LIB}/current/"):]).is_file(), f"{name}: betik yok {toks[1]}"
                seen["script"] += 1
            elif exe == "/bin/bash":
                assert _repo(toks[1]).is_file(), f"{name}: betik yok {toks[1]}"
                seen["script"] += 1
            # tum yol argumanlari (--config ... gibi) gercek dosya mi
            for t in toks[1:]:
                if t.startswith(T + "/") and not t.startswith(T + "/.venv"):
                    assert _repo(t).exists(), f"{name}: yol yok {t}"
    assert seen["module"] >= 4 and seen["script"] >= 8, seen


def test_working_directory_and_pythonpath_point_to_repo(rendered):
    for name, txt in rendered.items():
        kv = dict(unit_kv(txt))
        if "WorkingDirectory" in kv:
            assert kv["WorkingDirectory"] == T, name
        for k, v in unit_kv(txt):
            if k == "Environment" and v.startswith("PYTHONPATH="):
                assert v in (f"PYTHONPATH={T}/src", f"PYTHONPATH={T}/src:{T}/paket"), name      # 19.11: motor ortak paketi de okur


def test_module_units_have_workingdirectory_and_pythonpath(rendered):
    """`python -m trader_*` birimleri PYTHONPATH + goreli `--config-dir config` icin WorkingDirectory ister; -I'li betikler kendi sys.path'ini kurar."""
    for name, txt in rendered.items():
        for k, v in unit_kv(txt):
            if k in ("ExecStart", "ExecStartPre") and " -m trader_" in v:
                kv = dict(unit_kv(txt))
                assert kv.get("WorkingDirectory") == T and any(
                    kk == "Environment" and vv.startswith("PYTHONPATH=") for kk, vv in unit_kv(txt)), name


def test_environment_files_are_created_by_install(rendered):
    t = install_text()
    created = set(re.findall(r'copy_env "[^"]+"\s+(/etc/trader-[\w-]+\.env)', t))
    assert len(created) == 6, created            # WP-B8: + /etc/trader-testnet.env; DD-9: + /etc/trader-live.env; DD-12 WP-06a: - trader-veto.env
    assert "/etc/trader-live.env" in created
    assert "/etc/trader-testnet.env" in created
    assert "/etc/trader-veto-hmac.env" not in created           # 24.11: AI veto artiklari silindi
    for name, txt in rendered.items():
        for k, v in unit_kv(txt):
            if k == "EnvironmentFile":
                optional = v.startswith("-")
                assert v.lstrip("-") in created, f"{name}: {v} install.sh tarafindan olusturulmuyor"
                _ = optional


def test_namespace_paths_exist_after_install(rendered):
    """ReadWritePaths/ReadOnlyPaths'ta '-' onekisiz yol sunucuda yoksa birim 226/NAMESPACE ile baslamaz.
    Yollar: install.sh'in `install -d` dizinleri + depodaki izlenen yollar + birimin kendi StateDirectory'si."""
    have = with_ancestors(created_dirs())
    for name, txt in rendered.items():
        kv = unit_kv(txt)
        state = {f"/var/lib/{v}" for k, v in kv if k == "StateDirectory"}
        for k, v in kv:
            if k not in ("ReadWritePaths", "ReadOnlyPaths"):
                continue
            for p in v.split():
                if p.startswith("-"):
                    continue
                ok = p in have or p in state or (p.startswith(T + "/") and _repo(p).exists())
                assert ok, f"{name}: {k}={p} sunucuda olusturulmuyor (ilk calistirmada namespace hatasi) -> basina '-' koyun ya da install.sh olustursun"


def test_install_pre_creates_what_strict_units_need():
    d = created_dirs()
    for p in ("var", "shared", "user_data", "var/telegram", "var/telegram/outbox"):
        assert f"{T}/{p}" in d, p
    assert "/var/backups/trader" in d
    assert f"{T}/user_data/budget.sqlite" not in d          # dosya (install -d degil): ayrica 0600 trader sahipli olusturulur


def test_restart_semantics_match_exit_codes():
    """Birim RestartPreventExitStatus degerleri kodun cikis kodlariyla birebir (motor 7, feed 6)."""
    from trader_engine.engine import EXIT_STARTUP_GATE
    from trader_engine.marketdata import feed as F
    eng = dict(unit_kv((DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")))
    fd = dict(unit_kv((DEPLOY / "trader-feed.service").read_text(encoding="utf-8")))
    assert eng["RestartPreventExitStatus"].split() == [str(EXIT_STARTUP_GATE), "8"] == ["7", "8"]     # DD-8: 8 = kalici ret (damga vb.)
    assert fd["RestartPreventExitStatus"].split() == [str(F.EXIT_BAN), str(F.EXIT_GEOBLOCK)] == ["3", "6"]
    for u in ("trader-engine@.service", "trader-feed.service", "trader-telegram.service",
              "trader-health.service", "trader-backup.service", "trader-telegram-report.service",
              "trader-counterfactual@.service", "trader-exit-counterfactual@.service"):
        assert "OnFailure=trader-health-fail@%n.service" in (DEPLOY / u).read_text(encoding="utf-8"), u


def test_slice_rendered_and_every_service_references_it(rendered):
    # trader.slice 'trader-*' glob'una girmez: install.sh onu ayrica render() ile kurar
    assert "trader.slice" not in rendered
    assert "render \"$REL_DIR/deploy/trader.slice\"" in install_text()
    for name, txt in rendered.items():
        if name == "trader-oto-guncelle.service":         # kurulum isi: bilincli olarak slice disinda, kendi tavani var
            assert ("MemoryMax", "800M") in unit_kv(txt), name
        elif name.endswith(".service"):
            assert ("Slice", "trader.slice") in unit_kv(txt), name
