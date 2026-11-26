"""DD-12 WP-07 (Ikiz kaldirma) bagimsiz spec testleri: docs/motor/dd12-capraz-varlik-spec.md v4, Bolum 9 WP-07, D-T11,
D-T23 (ikiz kismi), D-T13 (testnet/canli birimleri degismedi). Uygulayici testlerine bakilmadan yazildi.
install.sh ASLA calistirilmaz; yalniz statik metin denetimi + saf fonksiyonlar."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

DEPLOY = ROOT / "deploy"
UTC = timezone.utc
NOW = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)
DAY = "2026-11-16"


def _git_show(rel: str) -> bytes:
    r = subprocess.run(["git", "show", f"HEAD:./{rel}"], cwd=ROOT, capture_output=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def _load(name):
    spec = importlib.util.spec_from_file_location(f"wp07_{name}", ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"wp07_{name}"] = m
    spec.loader.exec_module(m)
    return m


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _unit_files():
    return sorted(p for p in DEPLOY.rglob("*") if p.is_file() and (p.suffix in (".service", ".timer", ".conf")
                                                                    or p.name.endswith(".env.example")))


def _active_lines(text: str):
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


# ---------------------------------------------------------------- deploy: birimler
def test_ml_shadow_dropin_silindi():
    assert not (DEPLOY / "trader-engine@learner.service.d" / "ml-shadow.conf").exists()
    assert not list(DEPLOY.rglob("ml-shadow*"))


def test_install_ml_shadow_ve_env_bayragi_kalmadi():
    t = _read(DEPLOY / "install.sh")
    assert "TRADER_ML_SHADOW" not in t
    # drop-in KURAN bir kod yok (yalniz eski kurulumdaki dosyanin temizligi serbest)
    assert not re.search(r"for f in .*service\.d/\*\.conf", t)


def test_hicbir_birim_ikiz_yolu_veya_adi_icermez():
    kotu = []
    for p in _unit_files():
        for ln in _active_lines(_read(p)):
            if re.search(r"twin|ikiz", ln, re.I):
                kotu.append(f"{p.name}: {ln.strip()}")
    assert not kotu, kotu


def test_env_ornekleri_ikizsiz():
    for p in DEPLOY.glob("*.env.example"):
        for ln in _active_lines(_read(p)):
            assert not re.search(r"twin", ln, re.I), (p.name, ln)
    h = _read(DEPLOY / "trader-health.env.example")
    m = re.search(r"^HEALTH_BOTS=(.*)$", h, re.M)
    assert m and m.group(1).strip() == "learner"
    tg = _read(DEPLOY / "trader-telegram.env.example")
    m = re.search(r"^PAUSE_BOTS=(.*)$", tg, re.M)
    assert m and m.group(1).strip() == "learner"
    assert "TWIN_LEDGER_PATH" not in tg and "TWIN_LEDGER_PATH" not in _read(DEPLOY / "trader-lesson.env.example")


def test_engine_birimi_paper_ve_tavanlar():
    t = _read(DEPLOY / "trader-engine@.service")
    assert re.search(r"^ExecStart=.*-m trader_engine run --bot %i --env paper\b", t, re.M)
    assert re.search(r"^ExecStartPre=.*init-ledger --bot %i --env paper\b", t, re.M)
    assert re.search(r"^MemoryHigh=600M$", t, re.M)
    assert re.search(r"^MemoryMax=750M$", t, re.M)
    assert "Slice=trader.slice" in t
    assert "Restart=on-failure" in t and "RestartPreventExitStatus=7 8" in t


def test_feed_birimi_paper_ve_tavanlar():
    t = _read(DEPLOY / "trader-feed.service")
    assert re.search(r"^ExecStart=.*-m trader_engine feed\b.*--env paper\b", t, re.M)
    assert re.search(r"^MemoryHigh=200M$", t, re.M)
    assert re.search(r"^MemoryMax=260M$", t, re.M)
    assert "Slice=trader.slice" in t
    assert "--startup-retry forever" in t


@pytest.mark.parametrize("rel", ["deploy/trader-engine-testnet.service", "deploy/trader-engine-live.service",
                                 "deploy/trader-testnet.env.example", "deploy/trader-live.env.example",
                                 "deploy/trader.slice"])
def test_testnet_canli_slice_birimleri_degismedi(rel):
    want = _git_show(rel)
    if rel in ("deploy/trader-engine-testnet.service", "deploy/trader-engine-live.service"):   # 24.11 kullanici karari: veto ve C1 artiklari silindi
        want = re.sub(rb"(# Veto belgesini[^\n]*\n)?EnvironmentFile=/etc/trader-veto-hmac\.env\n", b"", want)
    assert (ROOT / rel).read_bytes() == want


def test_slice_tavani_aynen():
    t = _read(DEPLOY / "trader.slice")
    assert "MemoryHigh=1100M" in t and "MemoryMax=1300M" in t


def test_ozel_birimler_ikiz_olmadan_ayni_kaldi_veya_temiz():
    # telegram/report birimleri: var/twin ReadOnlyPaths/ReadWritePaths girdisi yok
    for n in ("trader-telegram.service", "trader-telegram-report.service"):
        t = _read(DEPLOY / n)
        for ln in _active_lines(t):
            assert "var/twin" not in ln, (n, ln)


# ---------------------------------------------------------------- deploy: install/uninstall (statik)
def test_install_ikiz_bayraklari_kalkti():
    t = _read(DEPLOY / "install.sh")
    assert not re.search(r"--with-twin\)", t)
    assert not re.search(r"--no-twin\)", t)
    assert "WITH_TWIN" not in t


def test_install_health_bots_learner():
    t = _read(DEPLOY / "install.sh")
    assert "learner,twin" not in t
    assert re.search(r"HEALTH_BOTS", t)
    # PAUSE_BOTS/HEALTH_BOTS degeri yalniz learner
    assert re.search(r'HEALTH_BOTS_VAL="learner"|HEALTH_BOTS=learner\b', t)


def test_install_ikiz_birimlerini_durdurur_ve_devre_disi_birakir():
    t = _read(DEPLOY / "install.sh")
    for unit in ("trader-engine@twin.service", "trader-engine-retry@twin.timer",
                 "trader-counterfactual@twin.timer", "trader-drift@twin.timer"):
        assert unit in t, unit
    # kurulum (enable --now) YOK; durdur + devre disi VAR
    assert not re.search(r"enable_now\s+trader-[\w-]+@twin", t)
    assert re.search(r"disable\s+--now|stop\b.*disable|disable\b.*stop\b", t)


def test_install_var_twin_arsive_tasinir_silinmez():
    t = _read(DEPLOY / "install.sh")
    assert "var/arsiv/twin-" in t
    assert re.search(r"\b(mv|rsync|cp)\b[^\n]*var/twin|\b(mv|rsync|cp)\b[^\n]*\$\{?\w*TWIN\w*", t) or "mv " in t
    for ln in t.splitlines():
        if ln.lstrip().startswith("#"):
            continue
        assert not re.search(r"\brm\b[^\n]*(-\w*r\w*|-\w*f\w*)[^\n]*var/twin", ln), ln
        assert not re.search(r"\brm\b[^\n]*var/twin", ln), ln
        assert not re.search(r"\bfind\b[^\n]*var/twin[^\n]*-delete", ln), ln


def test_uninstall_ikiz_verisini_silmez_ve_ikiz_secenegi_yok():
    t = _read(DEPLOY / "uninstall.sh")
    assert "--with-twin" not in t and "--no-twin" not in t
    for ln in _active_lines(t):
        assert not re.search(r"\brm\b[^\n]*var/twin", ln), ln


@pytest.mark.parametrize("name", ["install.sh", "uninstall.sh"])
def test_bash_sozdizimi(name):
    assert subprocess.run(["bash", "-n", str(DEPLOY / name)], capture_output=True).returncode == 0


def test_install_ikiz_bayragi_reddedilir_hicbir_sey_yapmadan(tmp_path):
    # root degil / COMMIT yok: bayrak ayristirma asamasinda cikis 2 ("Bilinmeyen secenek") beklenir; hicbir degisiklik yok
    r = subprocess.run(["bash", str(DEPLOY / "install.sh"), "--no-twin"], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}, timeout=30)
    assert r.returncode == 2
    assert "Bilinmeyen" in r.stderr


# ---------------------------------------------------------------- konfig
def test_panel_json_ikizsiz():
    raw = json.loads(_read(ROOT / "config/panel.json"))
    assert not [k for k in raw if "twin" in k.lower()]
    assert "twin" not in json.dumps(raw).lower()


# ---------------------------------------------------------------- saglik / yedek / pause / retry
def test_saglik_varsayilan_yalniz_learner():
    from trader_core import health as H
    assert H.DEFAULT_CFG.require_bots == ("learner",)
    hr = _load("health_run")
    assert hr.bots_from_env({}) == ("learner",)
    assert hr.bots_from_env({"HEALTH_BOTS": "learner"}) == ("learner",)
    assert hr.make_cfg({"HEALTH_BOTS": "learner"}).require_bots == ("learner",)


def test_yedek_varsayilan_yalniz_learner():
    hb = _load("health_backup")
    assert tuple(hb.BOTS) == ("learner",)
    assert tuple(hb.bots_from_env({})) == ("learner",)


def test_telegram_pause_varsayilan_yalniz_learner(tmp_path):
    tr = _load("telegram_run")
    pauses = tr.build_pauses({"PAUSE_BOTS": "learner"}, lambda: NOW, root=tmp_path)
    assert set(pauses) == {"learner"}
    assert set(tr.build_pauses({}, lambda: NOW, root=tmp_path)) == {"learner"}


def test_engine_retry_ikiz_birimini_tanimaz():
    er = _load("engine_retry")
    assert not er.UNIT_RE.match("trader-engine@twin.service")
    assert er.UNIT_RE.match("trader-engine@learner.service")
    assert er.UNIT_RE.match("trader-engine-testnet.service")
    assert er.UNIT_RE.match("trader-engine-live.service")


@pytest.mark.parametrize("script", ["drift_run", "counterfactual_run", "report_run"])
def test_betikler_bot_twin_reddeder(script, capsys):
    m = _load(script)
    argv = ["--bot", "twin", "--once"] if script != "report_run" else ["--bot", "twin"]
    with pytest.raises(SystemExit) as e:
        m.main(argv)
    assert e.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


# ---------------------------------------------------------------- telegram (ikiz satiri yok, var/twin yokken cokmez)
def _twin_fixture(tmp_path):
    """var/twin dolu ve TWIN_LEDGER_PATH ona isaret eder: yine de hicbir cikti ikiz satiri uretmemeli."""
    from tests.test_telegram_report import mkledger as mkl, write_status
    mkl(tmp_path / "l.sqlite", "learner", [(True, True), (False, True)])
    (tmp_path / "var" / "twin").mkdir(parents=True)
    try:
        mkl(tmp_path / "var/twin/ledger.sqlite", "twin", [(True, True)])
    except Exception:  # noqa: BLE001 - ikiz bot kodu kaldirilmissa fikstur kurulamaz; sorun degil
        pass
    (tmp_path / "var/twin/drift.json").write_text("{}")
    write_status(tmp_path)


def _cfg(tmp_path, twin_dir: bool):
    from trader_core import telegram as T
    env = {"TELEGRAM_BOT_TOKEN": "1:tok", "TELEGRAM_CHAT_ID": "5", "TELEGRAM_VAR_DIR": str(tmp_path / "tg"),
           "LEDGER_PATH": str(tmp_path / "l.sqlite"), "ENGINE_STATUS_PATH": str(tmp_path / "status.json"),
           "BUDGET_CONFIG_PATH": str(tmp_path / "config/budget.json"),
           "TRADER_DATA_ROOT": str(tmp_path)}
    if twin_dir:
        env["TWIN_LEDGER_PATH"] = str(tmp_path / "var/twin/ledger.sqlite")
    cfg = T.TelegramConfig.from_env(env)
    assert cfg is not None
    return cfg


@pytest.mark.parametrize("twin_dir", [True, False])
def test_telegram_rapor_ikiz_satiri_yok(tmp_path, twin_dir):
    from trader_core import telegram as T
    _twin_fixture(tmp_path)
    if not twin_dir:
        import shutil
        shutil.rmtree(tmp_path / "var/twin")
    cfg = _cfg(tmp_path, twin_dir)
    for out in (T.section_ledger(cfg, DAY), T.rapor_defter(cfg, DAY), T.rapor_davranis(cfg, NOW)):
        low = out.lower()
        assert "ikiz" not in low and "twin" not in low and "👥" not in out, out


def test_telegram_bot_tr_ikizsiz():
    from trader_core import telegram as T
    assert "twin" not in getattr(T, "BOT_TR", {})
    assert "ikiz" not in " ".join(getattr(T, "BOT_TR", {}).values()).lower()


def test_telegram_tam_rapor_ikiz_yok_var_twin_yokken_cokmez(tmp_path):
    from trader_core import telegram as T
    _twin_fixture(tmp_path)
    import shutil
    shutil.rmtree(tmp_path / "var/twin")
    cfg = _cfg(tmp_path, False)
    r = T.build_report(cfg, NOW, DAY)
    text = r if isinstance(r, str) else "\n".join(map(str, r)) if isinstance(r, (list, tuple)) else str(r)
    assert "ikiz" not in text.lower() and "twin" not in text.lower()


# ---------------------------------------------------------------- pano
def _panel_env(tmp_path):
    from panel_support import Env, ROOT as _R  # noqa: F401
    e = Env(tmp_path, twin=False)
    shutil_rm = __import__("shutil").rmtree
    shutil_rm(tmp_path / "var/twin")                    # var/twin hic yok
    raw = json.loads(e.cfg_path.read_text())
    for k in [k for k in raw if "twin" in k]:
        del raw[k]                                      # ikiz anahtarlari olmayan yapilandirma
    e.cfg_path.write_text(json.dumps(raw))
    return e


def test_pano_ikiz_anahtari_olmadan_yuklenir_ve_ikiz_satiri_yok(tmp_path):
    from panel_support import NOW as PNOW
    from trader_panel.data import PanelData, load_config
    e = _panel_env(tmp_path)
    cfg = load_config(e.cfg_path)
    pd = PanelData(cfg, clock=lambda: PNOW)
    st = pd.status()
    assert st["ok"] is True
    assert set(st["bots"]) == {"learner"}
    assert "twin" not in json.dumps(st).lower()
    for bot in ("learner",):
        assert pd.ledger(bot, None)["ok"] is True
        assert pd.curve(bot)["ok"] is True
        assert pd.risk(bot)["ok"] in (True, False)
    # ikiz istegi artik gecerli bir bot degil (hata dondurur ya da firlatir; ikiz verisi asla degil)
    try:
        res = pd.ledger("twin", None)
        assert res.get("ok") is False
    except Exception:  # noqa: BLE001
        pass
    e.close()


def test_pano_modulu_ikiz_sabitleri_yok():
    from trader_panel import data as D
    assert tuple(D.BOTS) == ("learner",)
    for k in ("twin_status_path", "twin_ledger_path"):
        assert k not in D._PATH_KEYS


# ---------------------------------------------------------------- kaynak kodda ikiz kalinti taramasi
_SRC = ["src/trader_core/telegram.py", "src/trader_core/health.py", "src/trader_core/panel_data.py",
        "src/trader_core/live_paths.py", "scripts/telegram_run.py", "scripts/health_run.py", "scripts/report_run.py",
        "scripts/drift_run.py", "scripts/counterfactual_run.py", "scripts/health_backup.py", "scripts/engine_retry.py"]


@pytest.mark.parametrize("rel", _SRC)
def test_kaynakta_ikiz_bot_kalintisi_yok(rel):
    t = _read(ROOT / rel)
    kod = [ln for ln in t.splitlines() if not ln.lstrip().startswith("#")]
    kotu = [ln.strip() for ln in kod if re.search(r"twin_ledger|twin_status|TWIN_LEDGER|ikiz bot",
                                                  ln, re.I)]
    assert not kotu, kotu


def test_panel_paketi_ikizsiz():
    kotu = []
    for p in (ROOT / "src/trader_panel").rglob("*"):
        if p.suffix in (".py", ".js", ".html", ".css"):
            for i, ln in enumerate(_read(p).splitlines(), 1):
                if re.search(r"twin|ikiz", ln, re.I):
                    kotu.append(f"{p.name}:{i}: {ln.strip()}")
    assert not kotu, kotu
