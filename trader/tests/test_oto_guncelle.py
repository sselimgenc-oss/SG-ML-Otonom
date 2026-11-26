"""Sunucu otomatik guncelleme (deploy/oto_guncelle.sh, trader-geri-al, trader-oto-ac) kabuk testleri.

Ag yok: sahte curl ve systemctl PATH'in basina konur; kurulum betigi (install.sh) OTO_INSTALL ile sahte bir betiktir.
Git gercek ama yereldir: bir kaynak (origin) deposu ve root klonu tmp_path altinda kurulur.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
SCRIPT = DEPLOY / "oto_guncelle.sh"
GERI_AL = DEPLOY / "trader-geri-al"
OTO_AC = DEPLOY / "trader-oto-ac"
BRANCH = "claude/charming-hawking-ab5w5q"
TOKEN = "123456789:TESTTOKEN_abcdefghijklmnopqrstuvwxyz0123"   # sahte; yalniz test icin
SK = "sk-ant-api03-SECRETKEYVALUE12345"                         # sahte; yalniz test icin

pytestmark = pytest.mark.skipif(shutil.which("git") is None or shutil.which("bash") is None, reason="git/bash yok")

FAKE_CURL = r'''#!/usr/bin/env bash
# sahte curl (ag yok). Telegram cagrilari (token --config - ile stdin'den gelir) kayda alinir.
# GitHub cagrisi FAKE_RUNS_FILE icerigini basar; FAKE_GH_FAIL doluysa hata verir.
L="$OTO_TEST_LOG"
cfg=""
if [[ " $* " == *" --config - "* ]]; then cfg="$(cat)"; fi
printf '%s\n' "$*" >> "$L/curl_argv.log"
if [[ "$cfg" == *api.telegram.org* ]]; then
  printf '%s\n' "$cfg" >> "$L/curl_cfg.log"
  for a in "$@"; do
    case "$a" in text=*) printf '%s\n---\n' "${a#text=}" >> "$L/telegram.log" ;; esac
  done
  [ -z "${FAKE_TG_FAIL:-}" ] || exit 22
  exit 0
fi
[ -z "$cfg" ] || printf '%s\n' "$cfg" >> "$L/gh_cfg.log"
[ -z "${FAKE_GH_FAIL:-}" ] || exit 22
cat "$FAKE_RUNS_FILE"
'''

FAKE_SYSTEMCTL = r'''#!/usr/bin/env bash
# sahte systemctl: FAKE_UNITS listelenir; FAKE_LIVE icindekiler etkin/calisiyor sayilir.
echo "$*" >> "$OTO_TEST_LOG/systemctl.log"
case "$1" in
  list-unit-files|list-units)
    for u in ${FAKE_UNITS:-}; do echo "$u"; done ;;
  is-enabled|is-active)
    unit="${!#}"
    for u in ${FAKE_LIVE:-}; do [ "$u" = "$unit" ] && exit 0; done
    exit 1 ;;
  *) exit 0 ;;
esac
'''

FAKE_UYKU = r'''#!/usr/bin/env bash
echo "$*" >> "$OTO_TEST_LOG/uyku.log"
'''

FAKE_INSTALL = r'''#!/usr/bin/env bash
# sahte install.sh: COMMIT'i kaydeder, /etc/trader-release yerine OTO_RELEASE_FILE'i yazar (basarili ise).
echo "COMMIT=${COMMIT:-}" >> "$OTO_TEST_LOG/install.log"
echo "TUR=${OTO_KURULUM_TUR:-}" >> "$OTO_TEST_LOG/tur.log"
echo "kurulum ciktisi"
[ -z "${FAKE_INSTALL_OUT_FILE:-}" ] || cat "$FAKE_INSTALL_OUT_FILE"
[ -z "${FAKE_INSTALL_FAIL:-}" ] || exit 3
printf 'COMMIT=%s\n' "$COMMIT" > "$OTO_RELEASE_FILE"
'''

GIT_IDENT = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **GIT_IDENT}
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


class World:
    """Gecici sunucu: sahte komutlar, surum dosyasi, Telegram ortami, origin + root klonu, kurulum betigi."""

    def __init__(self, tmp: Path, commits: int = 3, subjects: list[str] | None = None):
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.log = tmp / "log"
        self.state = tmp / "state"
        self.etc = tmp / "etc"
        for d in (self.bin, self.log, self.state, self.etc):
            d.mkdir(parents=True)
        for name, body in (("curl", FAKE_CURL), ("systemctl", FAKE_SYSTEMCTL), ("sahte-uyku", FAKE_UYKU)):
            p = self.bin / name
            p.write_text(body, encoding="utf-8")
            p.chmod(0o755)
        self.install = tmp / "install.sh"
        self.install.write_text(FAKE_INSTALL, encoding="utf-8")
        self.release = self.etc / "trader-release"
        self.tg_env = self.etc / "trader-telegram.env"
        self.tg_env.write_text(f"TELEGRAM_BOT_TOKEN={TOKEN}\nTELEGRAM_CHAT_ID=4242\n", encoding="utf-8")
        self.runs = tmp / "runs.json"
        self.subjects = subjects
        self.shas = self._make_history(len(subjects) if subjects else commits)
        self.set_green(self.shas[-1])

    # ------------------------------------------------------------------ git: origin + root klonu (yerel)
    def _make_history(self, n: int) -> list[str]:
        work = self.tmp / "work"
        work.mkdir()
        _git(work, "init", "-q")
        _git(work, "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")
        shas = []
        for i in range(n):
            (work / "f.txt").write_text(str(i), encoding="utf-8")
            _git(work, "add", "-A")
            _git(work, "commit", "-q", "-m", self.subjects[i] if self.subjects else f"degisiklik {i}")
            shas.append(_git(work, "rev-parse", "HEAD"))
        origin = self.tmp / "origin.git"
        _git(self.tmp, "init", "-q", "--bare", str(origin))
        _git(work, "push", "-q", str(origin), f"{BRANCH}:{BRANCH}")
        self.root_git = self.tmp / "root.git"
        _git(self.tmp, "init", "-q", "--bare", str(self.root_git))
        _git(self.root_git, "remote", "add", "origin", str(origin))
        return shas

    # ------------------------------------------------------------------ durum yardimcilari
    def set_green(self, sha: str | None) -> None:
        if sha is None:
            self.runs.write_text('{"workflow_runs": []}', encoding="utf-8")
        else:
            self.runs.write_text('{"workflow_runs": [{"head_sha": "%s"}]}' % sha, encoding="utf-8")

    def set_release(self, sha: str) -> None:
        self.release.write_text(f"COMMIT={sha}\n", encoding="utf-8")

    def current(self) -> str:
        return self.release.read_text(encoding="utf-8").split("=", 1)[1].strip()

    def install_calls(self) -> list[str]:
        p = self.log / "install.log"
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    def telegram(self) -> list[str]:
        p = self.log / "telegram.log"
        if not p.exists():
            return []
        return [m for m in p.read_text(encoding="utf-8").split("\n---\n") if m]

    def history(self) -> list[list[str]]:
        p = self.state / "gecmis.tsv"
        return [ln.split("\t") for ln in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def curl_argv(self) -> str:
        p = self.log / "curl_argv.log"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def run(self, script: Path = SCRIPT, *args: str, **extra: str) -> subprocess.CompletedProcess:
        env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.tmp),
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "OTO_STATE_DIR": str(self.state),
            "OTO_RELEASE_FILE": str(self.release),
            "OTO_ROOT_DIR": str(self.tmp / "root-without-key"),   # ssh anahtari yok: root_git duz git calistirir
            "OTO_GIT_DIR": str(self.root_git),
            "OTO_INSTALL": str(self.install),
            "OTO_API_URL": "https://api.github.com/test/runs",
            "OTO_TELEGRAM_ENV": str(self.tg_env),
            "OTO_BRANCH": BRANCH,
            "OTO_TEST_LOG": str(self.log),
            "OTO_ZORLA": "1",          # varsayilan testler sabit pencereyi atlar (pencere testleri OTO_ZORLA="" verir)
            "OTO_SIMDI_DAKIKA": "7",   # mum kapanisi penceresi disi: varsayilan testler beklemez
            "OTO_UYKU": str(self.bin / "sahte-uyku"),
            "FAKE_RUNS_FILE": str(self.runs),
            **GIT_IDENT,
        }
        env.update(extra)
        return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, env=env, timeout=120)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# ----------------------------------------------------------------------------- sozdizim (bash -n)
@pytest.mark.parametrize("path", [SCRIPT, GERI_AL, OTO_AC, DEPLOY / "trader-oto-simdi"], ids=lambda p: p.name)
def test_bash_syntax(path):
    assert subprocess.run(["bash", "-n", str(path)], capture_output=True).returncode == 0


# ----------------------------------------------------------------------------- akis
def test_ayni_surum_islem_yok(world):
    world.set_release(world.shas[2])
    r = world.run()
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [] and world.telegram() == [] and world.history() == []


def test_yeni_yesil_commit_kurulur_ve_telegram_sessiz(world):
    old, new = world.shas[0], world.shas[2]
    world.set_release(old)
    r = world.run()
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [f"COMMIT={new}"]                # install.sh COMMIT ortam degiskeniyle cagrildi
    assert world.current() == new
    rows = world.history()
    assert len(rows) == 1 and rows[0][1:] == [old, new, "basarili"]
    assert world.telegram() == []                                     # basarili kurulumda Telegram'a hicbir sey gitmez
    assert "Bot güncellendi: degisiklik 2" in r.stdout and "guncellendi:" in r.stdout   # yalniz gunluk


def test_token_komut_satirinda_degil_stdinde(world):
    world.set_release(world.shas[0])
    assert world.run().returncode == 0
    assert world.run(GERI_AL).returncode == 0                         # basarili guncelleme sessiz; geri alma mesaji token yolunu dener
    assert TOKEN not in world.curl_argv()                             # ps'te gorunecek argv'de token yok
    cfg = (world.log / "curl_cfg.log").read_text(encoding="utf-8")
    assert TOKEN in cfg and "api.telegram.org/bot" in cfg             # token yalniz --config - (stdin) ile gider


def test_durdur_dosyasi_varsa_islem_yok(world):
    world.set_release(world.shas[0])
    (world.state).mkdir(parents=True, exist_ok=True)
    (world.state / "DURDUR").write_text("", encoding="utf-8")
    r = world.run()
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [] and world.telegram() == []


def test_canli_birim_etkinse_islem_yok_ve_gunde_bir_bildirim(world):
    world.set_release(world.shas[0])
    env = {"FAKE_UNITS": "trader-engine-live.service", "FAKE_LIVE": "trader-engine-live.service"}
    for _ in range(2):
        r = world.run(**env)
        assert r.returncode == 0, r.stderr
    assert world.install_calls() == [] and world.current() == world.shas[0]
    assert world.telegram() == []                                          # canli birim nedeniyle durma: mesaj yok (tekrar eden tur)


def test_canli_birim_yalniz_var_ve_pasifse_engellemez(world):
    world.set_release(world.shas[0])
    r = world.run(FAKE_UNITS="trader-engine-live.service", FAKE_LIVE="")   # dosya var, etkin/calisan degil
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [f"COMMIT={world.shas[2]}"]


def test_kurulum_hatasi_basarisiz_mesaji_ve_tekrar_denememe(world):
    old, new = world.shas[0], world.shas[2]
    world.set_release(old)
    out = world.tmp / "install_out.txt"
    out.write_text(f"hata satiri 1\nbot{TOKEN}\n{TOKEN}\nanahtar {SK}\nson satir\n", encoding="utf-8")
    env = {"FAKE_INSTALL_FAIL": "1", "FAKE_INSTALL_OUT_FILE": str(out)}
    r = world.run(**env)
    assert r.returncode == 1
    assert world.current() == old                                     # surum degismedi
    rows = world.history()
    assert rows[-1][1:] == [old, new, "basarisiz"]
    msgs = world.telegram()
    assert msgs == ["[ML] ⚠️ Güncelleme kurulamadı; bot eski sürümle çalışmaya devam ediyor."]
    assert TOKEN not in msgs[0] and "SECRETKEYVALUE" not in msgs[0]
    # ayni commit bir daha denenmez
    r2 = world.run(**env)
    assert r2.returncode == 0
    assert len(world.install_calls()) == 1


def test_cikti_maskelenir_ve_gunluge_token_sizmaz(world):
    world.set_release(world.shas[0])
    out = world.tmp / "install_out.txt"
    out.write_text(f"bot{TOKEN}\n{TOKEN}\n{SK}\n", encoding="utf-8")
    r = world.run(FAKE_INSTALL_FAIL="1", FAKE_INSTALL_OUT_FILE=str(out))
    text = r.stdout + r.stderr + "\n".join(world.telegram())
    assert TOKEN not in text and "SECRETKEYVALUE" not in text
    assert "<maskeli>" in text and "sk-ant-<maskeli>" in text


def test_eski_commit_kurulmaz(world):
    # yesil commit (shas[0]) mevcut surumun (shas[2]) atasi: geri gitmez
    world.set_release(world.shas[2])
    world.set_green(world.shas[0])
    r = world.run()
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [] and world.current() == world.shas[2] and world.telegram() == []


def test_yesil_kosu_yoksa_islem_yok(world):
    world.set_release(world.shas[0])
    world.set_green(None)
    assert world.run().returncode == 0
    assert world.install_calls() == []


def test_github_erisilemezse_islem_yok(world):
    world.set_release(world.shas[0])
    r = world.run(FAKE_GH_FAIL="1")
    assert r.returncode == 0
    assert world.install_calls() == []
    # istek dogru bicimde yapildi (User-Agent ve yalniz basarili kosular), cevap alinamadi
    assert "User-Agent: trader-oto-guncelle" in world.curl_argv() and "status=success" in world.curl_argv()


def test_cok_degisiklikte_mesaj_uc_satiri_asmaz(tmp_path):
    w = World(tmp_path, commits=18)                                    # 17 degisiklik (c0 haric)
    w.set_release(w.shas[0])
    r = w.run()
    assert r.returncode == 0, r.stderr
    assert w.telegram() == [] and "Bot güncellendi: degisiklik 17 (ve 16 değişiklik daha)" in r.stdout


def test_mesaj_konusu_test_ve_merge_atlanir_onek_temizlenir(tmp_path):
    w = World(tmp_path, subjects=["Temel", "Mutabakat: kasa kontrolü sadeleşti", "Test: kasa testi", "Merge branch 'x'"])
    w.set_release(w.shas[0])
    r = w.run()
    assert r.returncode == 0
    assert w.telegram() == [] and "Bot güncellendi: kasa kontrolü sadeleşti (ve 2 değişiklik daha)" in r.stdout


def test_mesaj_konusu_yalniz_test_varsa_en_yeni_konu_ve_90_karakter(tmp_path):
    w = World(tmp_path, subjects=["Temel", "Test: " + "a" * 120])
    w.set_release(w.shas[0])
    r = w.run()
    assert r.returncode == 0 and w.telegram() == []
    ilk = next(l for l in r.stdout.splitlines() if "Bot güncellendi: " in l).split("Bot güncellendi: ", 1)[1].split(" (ve ")[0].split(" Senden:")[0]
    assert len(ilk) <= 90


def test_geri_al_onceki_surumu_kurar_ve_durdurur(world):
    old, new = world.shas[0], world.shas[2]
    world.set_release(old)
    assert world.run().returncode == 0                                # 1. guncelleme: old -> new
    assert world.current() == new
    r = world.run(GERI_AL)
    assert r.returncode == 0, r.stderr
    assert world.install_calls()[-1] == f"COMMIT={old}"
    assert world.current() == old
    assert (world.state / "DURDUR").exists()
    assert world.history()[-1][1:] == [new, old, "geri_alindi"]
    assert world.telegram() == ["[ML] ⚠️ Son güncelleme geri alındı; bot önceki sürümle çalışıyor."]
    # DURDUR varken yeni yesil commit kurulmaz
    n = len(world.install_calls())
    assert world.run().returncode == 0
    assert len(world.install_calls()) == n


def test_geri_al_gecmis_yoksa_hata(world):
    r = world.run(GERI_AL)
    assert r.returncode == 1
    assert "Geri alinacak surum yok" in r.stderr
    assert world.install_calls() == [] and not (world.state / "DURDUR").exists()


def test_oto_ac_durdurmayi_kaldirir_telegram_sessiz(world):
    world.set_release(world.shas[0])
    (world.state).mkdir(parents=True, exist_ok=True)
    (world.state / "DURDUR").write_text("", encoding="utf-8")
    assert world.run(OTO_AC).returncode == 0
    assert not (world.state / "DURDUR").exists()
    assert world.telegram() == []
    assert world.run().returncode == 0                                # artik guncelleme yapar
    assert world.install_calls() == [f"COMMIT={world.shas[2]}"]


# ----------------------------------------------------------------------------- kurulum sozlesmesi (statik)
def test_install_sh_kurar_ve_etkinlestirir():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "enable_now trader-oto-guncelle.timer" in t
    assert "/var/lib/trader-oto-guncelle" in t and "install -d -m 0700 -o root -g root" in t
    assert 'install -m 0755 -o root -g root "$REL_DIR/deploy/$c" "/usr/local/sbin/$c"' in t
    assert "for c in trader-geri-al trader-oto-ac" in t


def test_birimler_ve_zamanlayici():
    s = (DEPLOY / "trader-oto-guncelle.service").read_text(encoding="utf-8")
    tm = (DEPLOY / "trader-oto-guncelle.timer").read_text(encoding="utf-8")
    assert "User=root" in s and "Type=oneshot" in s
    assert "ExecStart=/bin/bash /usr/local/lib/trader-root/current/deploy/oto_guncelle.sh" in s
    assert "TimeoutStartSec=45min" in s
    # 24.11 kullanici karari: sabit pencere yok; 5 dakikada bir
    assert "OnCalendar=*:0/5" in tm and "RandomizedDelaySec=0" in tm and "Persistent=false" in tm


def test_betiklerde_telegram_token_komut_satirinda_yok():
    for p in (SCRIPT, GERI_AL, OTO_AC):
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
        assert any("--config -" in ln for ln in lines), p.name           # Telegram istegi stdin config ile
        assert not any("curl" in ln and "$tok" in ln for ln in lines), p.name   # token hicbir curl argv'inde yok


def test_mesaj_konusu_sozcuk_sinirinda_kesilir_utf8_guvenli(tmp_path):
    konu = "Kasa mutabakatı şimdi çok daha sade ve anlaşılır oldu, işlem özetleri ğüşiöç ile birlikte kaydedildi ve gönderildi"
    w = World(tmp_path, subjects=["Temel", konu])
    w.set_release(w.shas[0])
    r = w.run()
    assert r.returncode == 0 and w.telegram() == []
    ilk = next(l for l in r.stdout.splitlines() if "Bot güncellendi: " in l).split("Bot güncellendi: ", 1)[1].split(" (ve ")[0].split(" Senden:")[0]
    assert len(ilk) <= 90 and ilk.endswith("…") and "\ufffd" not in ilk
    govde = ilk[:-1]
    assert konu.startswith(govde) and konu[len(govde)] == " "              # sozcuk ortasinda kesilmez
    assert "kaydedil" not in ilk


def test_kisa_konu_kesilmez(tmp_path):
    w = World(tmp_path, subjects=["Temel", "Kısa şık konu"])
    w.set_release(w.shas[0])
    r = w.run()
    assert r.returncode == 0 and w.telegram() == [] and "Bot güncellendi: Kısa şık konu" in r.stdout


# ----------------------------------------------------------------------------- mum kapanisi beklemesi
def _uyku(world):
    p = world.log / "uyku.log"
    return p.read_text(encoding="utf-8").split() if p.exists() else []


@pytest.mark.parametrize("dk,sn,beklenen", [
    ("14", "0", 240), ("29", "30", 210), ("0", "0", 180), ("15", "0", 180), ("1", "0", 120), ("2", "0", 60), ("2", "59", 1), ("44", "10", 230),
])
def test_kapanis_penceresinde_kurulum_ertelenir(world, dk, sn, beklenen):
    world.set_release(world.shas[0])
    r = world.run(OTO_SIMDI_DAKIKA=dk, OTO_SIMDI_SANIYE=sn)
    assert r.returncode == 0, r.stderr
    assert _uyku(world) == [str(beklenen)]
    assert len(world.install_calls()) == 1 and world.current() == world.shas[2]


@pytest.mark.parametrize("dk", ["3", "7", "13", "18", "58", "08"])
def test_kapanis_penceresi_disinda_beklenmez(world, dk):
    world.set_release(world.shas[0])
    r = world.run(OTO_SIMDI_DAKIKA=dk)
    assert r.returncode == 0, r.stderr
    assert _uyku(world) == [] and len(world.install_calls()) == 1


def test_kurulum_gerekmiyorsa_beklenmez(world):
    world.set_release(world.shas[2])
    r = world.run(OTO_SIMDI_DAKIKA="0")
    assert r.returncode == 0 and _uyku(world) == [] and world.install_calls() == []


# ----------------------------------------------------------------------------- sabit pencere yok (24.11): her saatte kurulur
SIMDI = DEPLOY / "trader-oto-simdi"


@pytest.mark.parametrize("sa,dk", [("0", "7"), ("7", "29"), ("12", "7"), ("20", "37"), ("23", "52")])
def test_her_saatte_kurulur(world, sa, dk):
    world.set_release(world.shas[0])
    r = world.run(OTO_ZORLA="", OTO_SIMDI_SAAT=sa, OTO_SIMDI_DAKIKA=dk)
    assert r.returncode == 0, r.stderr
    assert len(world.install_calls()) == 1 and world.current() == world.shas[2]
    assert "penceresi disinda" not in r.stdout


def test_simdi_secenegi_pencereyi_atlar_ama_korumalari_atlamaz(world):
    world.set_release(world.shas[0])
    (world.state).mkdir(parents=True, exist_ok=True)
    (world.state / "DURDUR").write_text("", encoding="utf-8")
    r = world.run(SCRIPT, "--simdi", OTO_ZORLA="", OTO_SIMDI_SAAT="12", OTO_SIMDI_DAKIKA="0")
    assert r.returncode == 0 and world.install_calls() == []             # DURDUR hala gecerli
    (world.state / "DURDUR").unlink()
    r = world.run(SCRIPT, "--simdi", OTO_ZORLA="", OTO_SIMDI_SAAT="12", OTO_SIMDI_DAKIKA="0")
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [f"COMMIT={world.shas[2]}"]          # pencere disinda ama acil kurulum
    canli = World(world.tmp / "canli")
    canli.set_release(canli.shas[0])
    r = canli.run(SCRIPT, "--simdi", OTO_ZORLA="", OTO_SIMDI_SAAT="12", OTO_SIMDI_DAKIKA="0",
                  FAKE_UNITS="trader-engine-live.service", FAKE_LIVE="trader-engine-live.service")
    assert r.returncode == 0 and canli.install_calls() == []             # canli koruma hala gecerli


def test_simdi_komutu_oto_guncelleyi_zorlar(world):
    world.set_release(world.shas[0])
    r = world.run(SIMDI, OTO_ZORLA="", OTO_GUNCELLE=str(SCRIPT), OTO_SIMDI_SAAT="12", OTO_SIMDI_DAKIKA="0")
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [f"COMMIT={world.shas[2]}"]


def test_bilinmeyen_secenek_reddedilir(world):
    r = world.run(SCRIPT, "--bilinmeyen")
    assert r.returncode == 2 and world.install_calls() == []


def test_oto_kurulum_turu_install_e_iletilir(world):
    world.set_release(world.shas[0])
    assert world.run().returncode == 0
    assert (world.log / "tur.log").read_text(encoding="utf-8").split() == ["TUR=oto"]


# ----------------------------------------------------------------------------- otomatik geri alma (trader-geri-al --otomatik)
def _isaret(world, commit, onceki, tur="oto"):
    world.state.mkdir(parents=True, exist_ok=True)
    (world.state / "kurulum.json").write_text(
        '{"at":"2026-11-20T07:33:00Z","commit":"%s","onceki":"%s","tur":"%s"}\n' % (commit, onceki, tur), encoding="utf-8")


def test_geri_al_otomatik_onceki_surumu_kurar_isaretler_durdurmaz(world):
    old, new = world.shas[0], world.shas[2]
    world.set_release(old)
    assert world.run().returncode == 0
    _isaret(world, new, old)
    r = world.run(GERI_AL, "--otomatik", "--neden", "motor servisi çalışmıyor")
    assert r.returncode == 0, r.stderr
    assert world.install_calls()[-1] == f"COMMIT={old}" and world.current() == old
    assert (world.log / "tur.log").read_text(encoding="utf-8").split()[-1] == "TUR=geri-al"
    assert not (world.state / "DURDUR").exists()                           # otomatik geri alma guncellemeyi durdurmaz
    h = world.history()
    assert h[-2][1:] == [old, new, "basarisiz"] and h[-1][1:] == [new, old, "geri_alindi"]
    tg = world.telegram()
    assert len(tg) == 1 and tg[0].startswith("[ML] ⚠️ Güncellemeden sonra sorun görüldü; bot önceki sürüme döndürüldü.\nNeden: motor servisi çalışmıyor.")
    assert tg[0].endswith("Sorunlu sürüm yeniden kurulmayacak.")
    # bozuk commit bir daha denenmez; yesil commit hala o ise oto_guncelle islem yapmaz
    n = len(world.install_calls())
    r = world.run()
    assert r.returncode == 0 and len(world.install_calls()) == n and "tekrar denenmez" in r.stdout
    # daha yeni bir yesil commit gelirse kurulur (DURDUR yok)


def test_geri_al_otomatik_isaretsiz_gecmisten_hedef_bulur(world):
    old, new = world.shas[0], world.shas[2]
    world.set_release(old)
    assert world.run().returncode == 0
    r = world.run(GERI_AL, "--otomatik")
    assert r.returncode == 0, r.stderr
    assert world.current() == old and not (world.state / "DURDUR").exists()


def test_geri_al_otomatik_basarisiz_kurulumda_tek_hata_mesaji(world):
    old, new = world.shas[0], world.shas[2]
    world.set_release(old)
    assert world.run().returncode == 0
    _isaret(world, new, old)
    r = world.run(GERI_AL, "--otomatik", FAKE_INSTALL_FAIL="1")
    assert r.returncode == 1
    assert world.history()[-1][1:] == [new, old, "geri_alma_basarisiz"]
    assert all(row[3] != "basarisiz" for row in world.history())          # surum degismedi: bozuk isaretlenmez
    assert world.telegram() == ["[ML] 🔴 Geri alma yapılamadı; bot mevcut sürümle çalışıyor.\nSenden: bana haber ver."]
    assert not (world.state / "DURDUR").exists()


def test_install_sh_kurulum_isareti_yazar():
    t = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert '"onceki":"%s"' in t and '"tur":"%s"' in t and "OTO_KURULUM_TUR:-elle" in t
    assert t.index("kurulum.json") < t.index("Kod degisti: calisan motorlar yeniden baslatiliyor")   # motorlar yeniden baslamadan ONCE
    assert "enable_now trader-kurulum-gozcu.timer" in t and "trader-oto-simdi" in t


# 23.11 repo gizli: token destegi
GH_TOK = "github_pat_FAKETOKEN0123456789abcdef"


def test_github_token_dosyasi_varsa_bearer_stdinde_argvde_yok(world):
    world.set_release(world.shas[0])
    f = world.tmp / "gh-token"
    f.write_text(f"  {GH_TOK}\n\r\n", encoding="utf-8")
    r = world.run(OTO_GITHUB_TOKEN_FILE=str(f))
    assert r.returncode == 0, r.stderr
    assert world.install_calls() == [f"COMMIT={world.shas[2]}"]
    cfg = (world.log / "gh_cfg.log").read_text(encoding="utf-8")
    assert f'Authorization: Bearer {GH_TOK}"' in cfg                  # bosluk/satir sonu kirpildi
    assert GH_TOK not in world.curl_argv() and GH_TOK not in r.stdout + r.stderr


def test_github_token_dosyasi_yoksa_ya_da_bossa_anonim(world):
    world.set_release(world.shas[0])
    bos = world.tmp / "bos"
    bos.write_text(" \n", encoding="utf-8")
    for tf in (world.tmp / "yok", bos):
        world.set_release(world.shas[0])
        assert world.run(OTO_GITHUB_TOKEN_FILE=str(tf)).returncode == 0
    assert not (world.log / "gh_cfg.log").exists()                    # stdin config yok
    assert "--config" not in "".join(l for l in world.curl_argv().splitlines() if "status=success" in l)
    assert "-H User-Agent: trader-oto-guncelle" in world.curl_argv()


def test_github_reddedilirse_ipucu_gunlukte(world):
    world.set_release(world.shas[0])
    r = world.run(FAKE_GH_FAIL="1", OTO_GITHUB_TOKEN_FILE=str(world.tmp / "yok"))  # dosya yok: anonim
    assert "GitHub'a ulasilamadi" in r.stdout and "repo gizliyse /etc/trader-github-token gerekli" in r.stdout
