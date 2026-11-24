"""Canli durum yayini (deploy/durum_yayinla.sh): saatlik ozet verisi -> repo dali canli-durum (ml/), yalniz deploy anahtariyla.

Uctan uca: yerel bir bos (bare) depoya gercekten yazilir (DURUM_YEREL=1, anahtarsiz); izin listesi disi dosya yayimlanmaz."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BETIK = ROOT / "deploy" / "durum_yayinla.sh"
DEPLOY = ROOT / "deploy"

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="git/bash yok")


def _trader(tmp: Path) -> Path:
    t = tmp / "trader"
    (t / "var" / "durum").mkdir(parents=True)
    (t / "var" / "learner").mkdir(parents=True)
    (t / "var" / "durum" / "mutabakat_v1.json").write_text('{"sema": "x", "islem_sayisi": 3}\n', encoding="utf-8")
    (t / "var" / "durum" / "strateji-veri-ml.md").write_text("# Strateji\n", encoding="utf-8")
    (t / "var" / "durum" / "baska_dosya.json").write_text("{}\n", encoding="utf-8")            # izin listesinde yok
    (t / "var" / "learner" / "status.json").write_text('{"bot": "learner", "open_positions": []}\n', encoding="utf-8")
    (t / "var" / "learner" / "ledger.sqlite").write_bytes(b"SQLite")                              # defter yayimlanmaz
    (t / "var" / "learner" / "models" / "pa_proposer").mkdir(parents=True)
    (t / "var" / "learner" / "models" / "pa_proposer" / "M1@1h.json").write_text('{"gizli_icerik": 1}', encoding="utf-8")
    (t / "var" / "learner" / "paper_models.csv").write_text("tarih,kol,durum\n2026-11-20,M1@15m,no_model\n", encoding="utf-8")
    return t


def _kos(trader: Path, repo: Path | None, tmp: Path, **ek) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp / "ev"), "TRADER_DIR": str(trader), "TRADER_PY": "/bin/false",
           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    if repo is not None:
        env.update({"DURUM_YEREL": "1", "DURUM_REPO": str(repo)})
    env.update(ek)
    return subprocess.run(["bash", str(BETIK)], env=env, capture_output=True, text=True, timeout=60)


def _bare(tmp: Path) -> Path:
    r = tmp / "uzak.git"
    subprocess.run(["git", "init", "-q", "--bare", str(r)], check=True)
    return r


def _dosyalar(repo: Path) -> list[str]:
    out = subprocess.run(["git", "--git-dir", str(repo), "ls-tree", "-r", "--name-only", "canli-durum"], capture_output=True, text=True, check=True)
    return sorted(out.stdout.split())


def test_anahtar_yoksa_sessizce_atlar(tmp_path):
    r = _kos(_trader(tmp_path), None, tmp_path)
    assert r.returncode == 0 and "deploy anahtari yok" in r.stdout and r.stderr == ""


def test_yalniz_canli_durum_dali(tmp_path):
    r = _kos(_trader(tmp_path), _bare(tmp_path), tmp_path, DURUM_DALI="main")
    assert r.returncode == 1 and "yalniz canli-durum" in r.stderr


def test_ilk_yayin_yetim_dal_izin_listesi_ve_ikinci_yayin(tmp_path):
    trader, repo = _trader(tmp_path), _bare(tmp_path)
    r = _kos(trader, repo, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "yayimlandi" in r.stdout
    assert _dosyalar(repo) == ["ml/durum.json", "ml/model_paketleri.txt", "ml/mutabakat_v1.json",
                               "ml/paper_models_son.csv", "ml/strateji-veri-ml.md", "ml/uretim.txt"]
    pk = subprocess.run(["git", "--git-dir", str(repo), "show", "canli-durum:ml/model_paketleri.txt"], capture_output=True, text=True, check=True)
    assert "pa_proposer/M1@1h.json" in pk.stdout and "gizli_icerik" not in pk.stdout and " UTC " in pk.stdout   # yalniz ad/boyut/zaman
    kok = subprocess.run(["git", "--git-dir", str(repo), "rev-list", "--max-parents=0", "canli-durum"], capture_output=True, text=True, check=True)
    assert len(kok.stdout.split()) == 1                                                            # yetim dal: tek kok
    durum = subprocess.run(["git", "--git-dir", str(repo), "show", "canli-durum:ml/durum.json"], capture_output=True, text=True, check=True)
    assert json.loads(durum.stdout)["bot"] == "learner"
    # ikinci tur: dosya degisti, ayni dala yeni commit (gecmis korunur, zorla itme yok)
    (trader / "var" / "durum" / "mutabakat_v1.json").write_text('{"sema": "x", "islem_sayisi": 4}\n', encoding="utf-8")
    (trader / "var" / "durum" / "strateji-veri-ml.md").unlink()
    r2 = _kos(trader, repo, tmp_path)
    assert r2.returncode == 0, r2.stderr
    n = subprocess.run(["git", "--git-dir", str(repo), "rev-list", "--count", "canli-durum"], capture_output=True, text=True, check=True)
    assert n.stdout.strip() == "2"
    assert "ml/strateji-veri-ml.md" not in _dosyalar(repo)                                         # kaynakta yoksa dalda da yok
    branches = subprocess.run(["git", "--git-dir", str(repo), "branch", "--format=%(refname:short)"], capture_output=True, text=True, check=True)
    assert branches.stdout.split() == ["canli-durum"]                                              # baska dala yazilmaz


def test_sir_kalibi_gorulurse_yayimlamaz(tmp_path):
    trader, repo = _trader(tmp_path), _bare(tmp_path)
    (trader / "var" / "durum" / "mutabakat.md").write_text("TELEGRAM_BOT_TOKEN=123\n", encoding="utf-8")
    r = _kos(trader, repo, tmp_path)
    assert r.returncode == 1 and "sir kalibi" in r.stderr
    assert subprocess.run(["git", "--git-dir", str(repo), "rev-parse", "--verify", "-q", "canli-durum"]).returncode != 0


def test_birim_sandbox_ve_zamanlayici():
    s = (DEPLOY / "trader-durum-yayin.service").read_text(encoding="utf-8")
    for k in ("User=trader", "ProtectSystem=strict", "NoNewPrivileges=true", "PrivateTmp=true", "ReadOnlyPaths=/opt/trader",
              "StateDirectory=trader-durum-yayin", "StateDirectoryMode=0700", "OnFailure=trader-health-fail@%n.service",
              "ExecStart=/bin/bash /opt/trader/deploy/durum_yayinla.sh"):
        assert k in s, k
    assert "\nEnvironmentFile=" not in s                                                             # Telegram/Cloudflare anahtari yuklenmez
    t = (DEPLOY / "trader-durum-yayin.timer").read_text(encoding="utf-8")
    assert "OnCalendar=hourly" in t
    assert "enable_now trader-durum-yayin.timer" in (DEPLOY / "install.sh").read_text(encoding="utf-8")
