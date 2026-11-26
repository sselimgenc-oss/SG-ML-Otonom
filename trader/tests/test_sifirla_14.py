"""deploy/sifirla_14.sh: sahte systemctl/id/install ile senaryolar (ag yok, systemd yok, root yok).
P7-03 (calisan oneshot), P7-04 (durdurma hatasinda silmeden cik), P7-05 (canli/testnet), P7-07 (yarida kalma), P7-06 (metin)."""
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "sifirla_14.sh"

SYSTEMCTL = textwrap.dedent("""\
    #!/bin/bash
    echo "$*" >> "$SC_LOG"
    case "$1" in
      list-units) if [[ "$*" == *trader-engine-live* ]]; then cat "$SC_LIVE"; else cat "$SC_LIST"; fi ;;
      stop) exit "${SC_STOP_RC:-0}" ;;
      is-active) echo "${SC_ACTIVE:-inactive}"; [ "${SC_ACTIVE:-inactive}" = inactive ] ;;
      *) exit 0 ;;
    esac
    """)


class Rig:
    def __init__(self, tmp: Path, liste="trader-tutarlilik.service loaded activating start\n", canli=""):
        self.tmp = tmp
        (tmp / "deploy").mkdir()
        shutil.copy(SCRIPT, tmp / "deploy" / "sifirla_14.sh")
        (tmp / "config").mkdir()
        shutil.copy(ROOT / "config" / "engine.paper.json", tmp / "config" / "engine.paper.json")
        for d in ("var/learner", "var/telegram/outbox", "var/durum", "var/rapor"):
            (tmp / d).mkdir(parents=True)
        (tmp / "var/learner/x").write_text("x")
        (tmp / "var/market.sqlite").write_text("m")
        (tmp / "var/telegram/offset.json").write_text("{}")
        gun = tmp / "bk" / "2026-01-01"
        gun.mkdir(parents=True)
        for n in ("ledger_learner.sqlite", "ledger_live@live.sqlite", "MANIFEST.json"):
            (gun / n).write_text("b")
        bin_ = tmp / "bin"
        bin_.mkdir()
        for n, body in (("systemctl", SYSTEMCTL), ("id", "#!/bin/bash\necho 0\n"), ("install", "#!/bin/bash\nexit 0\n")):
            (bin_ / n).write_text(body)
            (bin_ / n).chmod(0o755)
        (tmp / "list.txt").write_text(liste)
        (tmp / "live.txt").write_text(canli)
        self.log = tmp / "sc.log"
        self.log.write_text("")

    def run(self, **env):
        e = dict(os.environ, PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}", SC_LOG=str(self.log), SC_LIST=str(self.tmp / "list.txt"),
                 SC_LIVE=str(self.tmp / "live.txt"), SIFIRLA_KAYIT=str(self.tmp / "kayit.txt"), SIFIRLA_SAGLIK=str(self.tmp / "saglik.json"),
                 SIFIRLA_YEDEK=str(self.tmp / "bk"), **env)
        return subprocess.run(["bash", str(self.tmp / "deploy" / "sifirla_14.sh"), "--evet"], capture_output=True, text=True, env=e)

    def calls(self):
        return self.log.read_text().splitlines()

    def dosyalar_duruyor(self):
        return (self.tmp / "var/learner/x").exists() and (self.tmp / "var/market.sqlite").exists()


def test_calisan_oneshot_durdurulur_ve_temiz_senaryoda_yalniz_kagit_yedegi_silinir(tmp_path):
    r = Rig(tmp_path)
    p = r.run()
    assert p.returncode == 0, p.stdout + p.stderr
    assert "stop trader-tutarlilik.service" in r.calls()                         # (a) activating birim de durdurulur
    assert not (tmp_path / "var/learner/x").exists() and not (tmp_path / "var/market.sqlite").exists()
    gun = tmp_path / "bk" / "2026-01-01"                                         # (e)
    assert (gun / "ledger_live@live.sqlite").exists() and (gun / "MANIFEST.json").exists()
    assert not (gun / "ledger_learner.sqlite").exists()


def test_durdurma_hatasi_silmeden_cikar_ve_birimleri_geri_baslatir(tmp_path):
    r = Rig(tmp_path)
    p = r.run(SC_STOP_RC="1")
    assert p.returncode != 0
    assert r.dosyalar_duruyor() and (tmp_path / "bk/2026-01-01/ledger_learner.sqlite").exists()     # (b)
    assert "hicbir sey silinmedi" in p.stdout
    assert "start trader-tutarlilik.service" in r.calls()


def test_stop_basarili_ama_birim_hala_activating_ise_silmez(tmp_path):
    r = Rig(tmp_path)
    p = r.run(SC_ACTIVE="activating")
    assert p.returncode != 0 and "DURMADI: trader-tutarlilik.service (activating)" in p.stdout     # (c)
    assert r.dosyalar_duruyor() and "hicbir sey silinmedi" in p.stdout
    assert "start trader-tutarlilik.service" in r.calls()


def test_canli_motor_aktifse_reddeder(tmp_path):
    r = Rig(tmp_path, canli="trader-engine-live.service loaded active running\n")
    p = r.run()
    assert p.returncode != 0 and "trader-engine-live.service" in p.stdout                        # (d)
    assert not any(c.startswith("stop") for c in r.calls())
    assert r.dosyalar_duruyor()


def test_silinecekler_blogu_gercegi_soyler():
    t = SCRIPT.read_text(encoding="utf-8")
    blok = t[t.index('echo "Silinecekler'):t.index('if [ "${1:-}"')]
    assert "audit.jsonl" in blok and "rules.json" in blok and "saglik durumu" in blok
