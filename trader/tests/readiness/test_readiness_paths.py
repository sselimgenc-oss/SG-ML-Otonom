"""Hazirlik 3/6/7: yapilandirma anahtarlari, birimler arasi yol tutarliligi (KILL, status, ledger, telegram outbox, yedek),
ikiz ayrimi. Sunucudaki gercek yollar render edilmis env/birimlerden okunur."""
from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path

import pytest

from readiness_support import DEPLOY, ROOT, SERVER_TRADER_DIR as T, install_text, render_env_files, render_units, unit_kv


@pytest.fixture(scope="module")
def envs(tmp_path_factory):
    return render_env_files(tmp_path_factory.mktemp("envs"))


@pytest.fixture(scope="module")
def units(tmp_path_factory):
    return render_units(tmp_path_factory.mktemp("units"))


def _abs(p: str) -> str:
    return p if p.startswith("/") else posixpath.join(T, p)


def _cfg(bot):
    from trader_engine.config import load_engine_config
    return load_engine_config(ROOT / "config/engine.base.json", ROOT / f"config/engine.{bot}.json")


def _rw(units, name):
    return [p for k, v in unit_kv(units[name]) if k == "ReadWritePaths" for p in v.split()]


def _ro(units, name):
    return [p for k, v in unit_kv(units[name]) if k == "ReadOnlyPaths" for p in v.split()]


def _covered(path, allowed):
    return any(path == a.lstrip("-") or path.startswith(a.lstrip("-").rstrip("/") + "/") for a in allowed)


# ------------------------------------------------------------------ yapilandirma anahtarlari
def test_engine_config_loads_and_twin_is_rejected_and_pairs_agree_everywhere():
    from trader_engine.errors import ConfigError
    learner = _cfg("learner")
    assert learner.bot == "learner" and learner.mode == "paper"
    assert len(learner.pairs) == 10
    assert not (ROOT / "config/engine.twin.json").exists()
    with pytest.raises(ConfigError):                                                         # DD-12: ikiz reddedilir
        from trader_engine.config import load_cli_config
        load_cli_config(ROOT / "config", "twin")


def test_other_configs_load():
    from trader_core import budget, lesson
    from trader_panel.data import load_config
    pc = load_config(ROOT / "config/panel.json")
    assert pc.host == "127.0.0.1"
    bc = budget.load_config(ROOT / "config/budget.json")
    assert bc is not None
    lc = lesson.load_config(ROOT / "config/lesson.json", budget_config_path=ROOT / "config/budget.json")
    assert lc.twin_enabled is False


def test_learner_alone_shares_feed_and_twin_not_installed():
    l = _cfg("learner")
    assert l.start_delay_s == 0
    assert l.ledger_path == "var/learner/ledger.sqlite" and l.status_path == "var/learner/status.json"
    eng = (DEPLOY / "trader-engine@.service").read_text(encoding="utf-8")
    assert "--bot %i" in eng and "trader-feed.service" in eng                 # sablon: tek feed'e bagli
    inst = install_text()
    assert "enable_now trader-engine@twin.service" not in inst and "--with-twin" not in inst      # DD-12
    assert inst.index("enable_now trader-feed.service") < inst.index("enable_now trader-engine@learner.service")


def test_sqlite_market_db_opened_read_only_by_engine():
    src = (ROOT / "src/trader_engine/marketdata/sources.py").read_text(encoding="utf-8")
    assert "MarketStore(self.db_path, read_only=True)" in src               # motor feed'in dosyasina yazmaz


# ------------------------------------------------------------------ yol tutarliligi
def test_engine_var_paths_match_health_panel_telegram(envs, units):
    from trader_panel.data import load_config
    l = _cfg("learner")
    var = _abs(l.var_dir)
    h = envs["trader-health.env"]
    assert h["ENGINE_VAR_DIR"] == var == f"{T}/var"
    assert h["MARKET_DB"] == _abs(l.market_db)
    assert h["ENGINE_CONFIG_DIR"] == f"{T}/config"
    pc = load_config(ROOT / "config/panel.json")
    for bot, st, lg in (("learner", pc.status_path, pc.ledger_path),):
        c = _cfg(bot)
        assert st.replace(str(ROOT), T) == _abs(c.status_path), bot
        assert lg.replace(str(ROOT), T) == _abs(c.ledger_path), bot
    import importlib.util
    spec = importlib.util.spec_from_file_location("health_run_mod", ROOT / "scripts/health_run.py")
    hr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hr)
    for bot in ("learner",):
        c = _cfg(bot)
        assert hr.status_path(var, bot) == _abs(c.status_path) and hr.ledger_path(var, bot) == _abs(c.ledger_path)


def test_telegram_engine_status_path_points_to_learner_status(envs):
    """ENGINE_STATUS_PATH bos olursa /durum ve gunluk rapor 'durum okunamadi' der (sessiz bozulma)."""
    assert envs["trader-telegram.env"]["ENGINE_STATUS_PATH"] == _abs(_cfg("learner").status_path)


def test_kill_file_same_path_in_engine_telegram_panel(envs, units):
    from trader_panel.data import load_config
    eng = _abs(_cfg("learner").kill_file)
    assert eng == f"{T}/shared/KILL"
    assert envs["trader-telegram.env"]["KILL_FILE"] == eng
    assert load_config(ROOT / "config/panel.json").kill_file.replace(str(ROOT), T) == eng
    kdir = posixpath.dirname(eng)
    assert _covered(kdir, _rw(units, "trader-engine@.service"))               # motor yazabilir/okur
    assert _covered(kdir, _rw(units, "trader-telegram.service"))              # Telegram /hepsini_kapat yazabilir
    assert _covered(kdir, _ro(units, "trader-panel.service"))                 # panel yalniz okur
    assert not _covered(kdir, _rw(units, "trader-panel.service"))
    assert (DEPLOY / "trader-panel.service").read_text().count("EnvironmentFile") == 1     # yalniz yorumda


def test_telegram_outbox_dir_is_writable_for_every_writer(envs, units):
    out = envs["trader-telegram.env"]["TELEGRAM_VAR_DIR"]
    assert out == f"{T}/var/telegram"
    for u in ("trader-telegram.service", "trader-telegram-report.service", "trader-lesson.service", "trader-health-fail@.service"):
        assert _covered(out, _rw(units, u)), u
    assert re.search(r'install -d -m 2770 -o "\$TRADER_USER" -g "\$TG_GROUP" "\$TRADER_DIR/var/telegram/outbox"', install_text())
    for u in ("trader-telegram.service", "trader-telegram-report.service", "trader-lesson.service", "trader-health-fail@.service"):
        assert "SupplementaryGroups=trader-tg" in units[u], u


def test_backup_paths_and_timer(envs, units):
    h = envs["trader-health.env"]
    assert h["BACKUP_DIR"] == "/var/backups/trader"
    assert _covered(h["BACKUP_DIR"], _rw(units, "trader-backup.service"))
    assert f"{T}/var" in _rw(units, "trader-backup.service")        # OPEN-10: var yazilabilir (WAL -shm); yedek mode=ro URI kullanir
    assert "/var/backups/trader" in install_text() and "EnvironmentFile=/etc/trader-health.env" in units["trader-backup.service"]
    assert "OnCalendar=*-*-* 03:10:00 UTC" in units["trader-backup.timer"]
    assert "ExecStart=" in units["trader-backup.service"] and "health_backup.py" in units["trader-backup.service"]
    assert "enable_now trader-backup.timer" in install_text()


def test_every_timer_has_a_service_and_is_enabled_or_gated(units):
    inst = install_text()
    for name in units:
        if name.endswith(".timer"):
            stem = name[:-6]
            kv = dict(unit_kv(units[name]))
            target = kv.get("Unit", stem + ".service")
            assert target in units, f"{name} -> {target} yok"
            assert (f"enable_now {name}" in inst or (name in ("trader-engine-retry@.timer", "trader-counterfactual@.timer", "trader-exit-counterfactual@.timer", "trader-drift@.timer") and f"enable_now {name.replace('@.', '@learner.')}" in inst)
                    or (name == "trader-engine-env-retry@.timer" and "enable_now trader-engine-env-retry@testnet.timer" in inst and "enable --now trader-engine-env-retry@live.timer" in inst)), f"{name} install.sh'te etkinlestirilmiyor"


# ------------------------------------------------------------------ eski ACIK kusurlar (duzeltildi; regresyon testleri)
def test_OPEN_engine_units_have_no_veto_env():
    """24.11 kullanici karari: AI veto artiklari silindi; hicbir motor birimi veto env dosyasi yuklemez, ornek dosya yok."""
    def files(n):
        return {Path(v.lstrip("-")).name for k, v in unit_kv((DEPLOY / n).read_text(encoding="utf-8")) if k == "EnvironmentFile"}
    for n in ("trader-engine@.service", "trader-engine-testnet.service", "trader-engine-live.service"):
        assert not {f for f in files(n) if "veto" in f}, n
    assert not (DEPLOY / "trader-veto-hmac.env.example").exists() and not (DEPLOY / "trader-veto.service").exists()


def test_OPEN_lesson_and_telegram_ledger_path_is_the_engine_ledger(envs):
    want = _abs(_cfg("learner").ledger_path)
    assert envs["trader-lesson.env"]["LEDGER_PATH"] == want
    assert envs["trader-telegram.env"]["LEDGER_PATH"] == want
    lc = json.loads((ROOT / "config/lesson.json").read_text())
    assert _abs(lc["ledger_path"]) == want


def test_OPEN_lesson_and_telegram_can_create_sqlite_sidecars(units):
    for u in ("trader-lesson.service", "trader-telegram.service"):
        assert any(p.rstrip("/") == f"{T}/user_data" for p in _rw(units, u)), u



def test_OPEN_lesson_config_has_a_notifier():
    assert json.loads((ROOT / "config/lesson.json").read_text())["notifier"] == "telegram"


def test_health_unit_can_notify_telegram_and_write_outbox(envs, units):
    h = units["trader-health.service"]
    kv = unit_kv(h)
    assert ("EnvironmentFile", "-/etc/trader-telegram.env") in kv
    assert "SupplementaryGroups=trader-tg" in h
    assert _covered(envs["trader-telegram.env"]["TELEGRAM_VAR_DIR"], _rw(units, "trader-health.service"))
    assert envs["trader-health.env"]["NOTIFIER"] == "auto"
    assert ("UMask", "0007") in kv                       # outbox dosyalari trader-tg grubuna okunur/yazilir (daemon siler)


def test_health_env_has_bots_and_no_veto_freshness(envs):
    h = envs["trader-health.env"]
    assert h["HEALTH_BOTS"] == "learner"
    assert "VETO_FILE" not in h and "VETO_MAX_AGE_S" not in h              # DD-12 WP-06a: veto belgesi denetimi yok


def test_lesson_and_telegram_sandbox_ledger_access(units):
    for u in ("trader-lesson.service", "trader-telegram.service"):
        assert f"-{T}/var/learner" in _rw(units, u), u
    for u, paths in (("trader-lesson.service", _ro), ("trader-telegram.service", _rw), ("trader-telegram-report.service", _ro)):
        assert f"-{T}/var/twin" not in paths(units, u), u                                 # DD-12: ikiz yollari yok
    assert _covered(f"{T}/var", _rw(units, "trader-backup.service"))                  # OPEN-10


def test_budget_db_precreated_and_no_hmac_generation():
    t = install_text()
    assert re.search(r'install -m 0600 -o "\$TRADER_USER" -g "\$TRADER_USER" /dev/null "\$TRADER_DIR/user_data/budget.sqlite"', t)
    assert "HMAC_NEW" not in t and "TRADER_VETO_HMAC_KEY" not in t


def test_telegram_pause_env_and_unit_match_engine(envs, units, tmp_path):
    e = envs["trader-telegram.env"]
    l = _cfg("learner")
    assert e["PAUSE_FILE"] == _abs(l.pause_file) == f"{T}/shared/PAUSE"
    assert e["ENGINE_VAR_DIR"] == _abs(l.var_dir) == f"{T}/var"
    assert e["PAUSE_BOTS"] == "learner"
    assert any(k == "WorkingDirectory" for k, _ in unit_kv(units["trader-telegram.service"]))
    assert _covered(posixpath.dirname(e["PAUSE_FILE"]), _rw(units, "trader-telegram.service"))
    assert _covered(f"{T}/var/learner", _rw(units, "trader-telegram.service"))
    from readiness_support import render_env_files as rend
    (tmp_path / "nt").mkdir()
    assert rend(tmp_path / "nt")["trader-telegram.env"]["PAUSE_BOTS"] == "learner"
