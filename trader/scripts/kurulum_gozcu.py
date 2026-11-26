#!/usr/bin/env python3
"""Kurulum gozcusu (root; trader-kurulum-gozcu.timer 2 dk'da bir calistirir; daemon degildir).

install.sh kod degistiren her kurulumdan once `kurulum.json` yazar: {"at","commit","onceki","tur"}.
Bu betik o isarete bakar ve yalniz kurulumdan sonraki 60 dk boyunca is yapar:

- IZLEME (60 dk): esik asilirsa (motor servisi etkin degil / motor durum dosyasi bayat / tekrarlayan coksme-yeniden baslama /
  saglikte olumcul kirmizi) UST USTE 2 gozcu turunda gorulurse `trader-geri-al --otomatik` calisir: onceki surum kurulur, bozuk
  commit gecmise "basarisiz" yazilir (oto_guncelle bir daha denemez), tek Telegram mesaji gider. Ilk GRACE_MIN dakika (motor
  yeniden basliyor) sayilmaz. Canli birim varsa ya da kurulum turu `geri-al` ise dokunulmaz.
- OZ-KONTROL (20. dk, bir kez): sorun varsa TEK mesaj; sorun yoksa HICBIR sey gonderilmez.

Hicbir sey acmaz/kapatmaz/islem yapmaz; risk ayarlarina dokunmaz. Cikis kodu her zaman 0 (zamanlayici zinciri sessiz kalir).
Ortam degiskenleri yalniz testler icindir: OTO_STATE_DIR OTO_RELEASE_FILE OTO_TELEGRAM_ENV HEALTH_STATE_FILE GOZCU_GERI_AL
GOZCU_ENGINE_UNITS GOZCU_CANLI_UNITS ENGINE_VAR_DIR HEALTH_BOTS.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

from trader_core import health as H  # noqa: E402

log = logging.getLogger("trader.kurulum_gozcu")

IZLEME_DK = 60            # kurulumdan sonra izleme suresi
OZ_KONTROL_DK = 20        # oz-kontrol zamani (yalniz sorunda mesaj)
GRACE_MIN = 4             # ilk dakikalar: motor yeniden basliyor, sayilmaz
ART_ARDA_TUR = 2          # geri alma icin ust uste basarisiz gozcu turu
STATUS_BAYAT_S = 300      # motor durum dosyasi (loop_at) bu kadar eskiyse sorun (saglik loop_crit_s ile ayni)
YENIDEN_BASLAMA_ESIK = 3  # systemd NRestarts bu degere ulasirsa sorun
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def read_json(path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def write_json(path, obj) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def release_commit(path) -> str:
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.startswith("COMMIT="):
                return line[7:].strip()
    except OSError:
        pass
    return ""


def mask(text: str) -> str:
    text = re.sub(r"bot[0-9]+:[A-Za-z0-9_-]+", "bot<maskeli>", text)
    text = re.sub(r"[0-9]{8,10}:[A-Za-z0-9_-]{30,}", "<maskeli>", text)
    return re.sub(r"sk-ant-[A-Za-z0-9_-]+", "sk-ant-<maskeli>", text)


def _env_value(path, key) -> str:
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def tg_send(env: dict, text: str) -> bool:
    """Dogrudan Telegram (token yalniz bellekte; komut satirinda/gunlukte yok). Hata -> False, betigi dusurmez."""
    path = env.get("OTO_TELEGRAM_ENV", "/etc/trader-telegram.env")
    tok, chat = _env_value(path, "TELEGRAM_BOT_TOKEN"), _env_value(path, "TELEGRAM_CHAT_ID")
    if not tok or not chat:
        log.warning("Telegram anahtari yok; yalniz gunluk: %s", mask(text))
        return False
    base = env.get("GOZCU_TG_BASE", "https://api.telegram.org")
    data = urllib.parse.urlencode({"chat_id": chat, "text": mask(text)}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{base}/bot{tok}/sendMessage", data=data), timeout=20):
            return True
    except Exception:  # noqa: BLE001
        log.warning("Telegram gonderilemedi")
        return False


# --------------------------------------------------------------------------- olcumler
def _systemctl(*args: str) -> str:
    try:
        r = subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=20, check=False)
        return (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def canli_birim_var(env: dict, sysctl=_systemctl) -> bool:
    for u in (env.get("GOZCU_CANLI_UNITS") or "trader-engine-live.service").split():
        if sysctl("is-enabled", u) == "enabled" or sysctl("is-active", u) == "active":
            return True
    return False


def motor_sorunlari(env: dict, now: datetime, sysctl=_systemctl) -> list[tuple[str, str]]:
    """Motor birimi/durum dosyasi sorunlari: [(kod, aciklama)]. Bos liste = saglikli."""
    out: list[tuple[str, str]] = []
    units = (env.get("GOZCU_ENGINE_UNITS") or "trader-engine@learner.service").split()
    for u in units:
        if sysctl("is-active", u) != "active":
            out.append(("servis_etkin_degil", "motor servisi çalışmıyor"))
        else:
            n = sysctl("show", "-p", "NRestarts", "--value", u)
            if n.isdigit() and int(n) >= YENIDEN_BASLAMA_ESIK:
                out.append(("tekrarlayan_yeniden_baslama", f"motor {n} kez yeniden başladı"))
    var_dir = (env.get("ENGINE_VAR_DIR") or "").strip()
    if var_dir:
        import health_run as HR
        for bot in HR.bots_from_env(env):
            probe, _ = HR.probe_status(HR.status_path(HR._bot_var(env, bot, var_dir), bot), bot, now)
            if probe.ping_ok is False and (probe.last_process_at is None or (now - probe.last_process_at).total_seconds() > STATUS_BAYAT_S):
                out.append(("durum_bayat", "motor durum dosyası güncellenmiyor"))
                break
    return out


def saglik_kirmizilari(env: dict, *, yalniz_olumcul: bool) -> list[tuple[str, str]]:
    """Saglik state.json: ust uste >= 2 tur kirmizi olan kontroller (olumcul kodlar ya da hepsi)."""
    st = read_json(env.get("HEALTH_STATE_FILE", "/var/lib/trader-health/state.json")) or {}
    fps = st.get("fingerprints") if isinstance(st.get("fingerprints"), dict) else {}
    out = []
    for fp, ent in fps.items():
        if not isinstance(ent, dict) or ent.get("level") not in ("CRIT", "UNKNOWN"):
            continue
        try:
            if int(ent.get("consecutive", 0)) < H.RED_CONFIRM_RUNS:
                continue
        except (TypeError, ValueError):
            continue
        name, _, code = fp.partition("|")
        if yalniz_olumcul and code not in H.FATAL_CODES:
            continue
        sorun = H._health_tr(name, code)[0]
        out.append((code, sorun))
    return out


def default_runner(cmd: list[str]) -> int:
    """Geri alma komutunu systemd'nin GECICI biriminde (trader.slice DISINDA, kendi bellek tavani) calistirir ve cikis kodunu bekler;
    systemd-run yoksa dogrudan calistirir."""
    if shutil.which("systemd-run"):
        cmd = ["systemd-run", "--wait", "--collect", "--quiet", "--unit=trader-geri-al-oto", "-p", "MemoryMax=800M", "-p", "Nice=10", *cmd]
    try:
        return subprocess.run(cmd, check=False, timeout=2400).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


# --------------------------------------------------------------------------- ana akis
def tick(env: dict, now: datetime, *, sysctl=_systemctl, runner=None, send=None) -> str:
    """Tek tur. Doner: yapilan islemin kisa adi (testler/gunluk icin)."""
    state_dir = env.get("OTO_STATE_DIR", "/var/lib/trader-oto-guncelle")
    marker = read_json(os.path.join(state_dir, "kurulum.json"))
    if not marker:
        return "isaret_yok"
    at, commit = _parse(marker.get("at")), str(marker.get("commit") or "")
    if at is None or not SHA_RE.match(commit):
        return "isaret_gecersiz"
    age_min = (now - at).total_seconds() / 60.0
    if age_min < 0 or age_min > IZLEME_DK:
        return "pencere_disi"
    if release_commit(env.get("OTO_RELEASE_FILE", "/etc/trader-release")) != commit:
        return "kurulum_tamamlanmadi"
    if marker.get("tur") == "geri-al":
        return "geri_al_kurulumu"
    gpath = os.path.join(state_dir, "gozcu.json")
    gs = read_json(gpath) or {}
    if gs.get("commit") != commit:
        gs = {"commit": commit, "fails": 0, "rolled_back": False, "selfcheck_done": False}
    if gs.get("rolled_back"):
        return "geri_alindi"
    if canli_birim_var(env, sysctl):
        return "canli_birim"
    send = send or (lambda text: tg_send(env, text))
    runner = runner or default_runner
    if age_min < GRACE_MIN:
        write_json(gpath, gs)
        return "isinma"

    sorunlar = motor_sorunlari(env, now, sysctl) + saglik_kirmizilari(env, yalniz_olumcul=True)
    gs["fails"] = gs.get("fails", 0) + 1 if sorunlar else 0
    action = "saglikli"
    onceki = str(marker.get("onceki") or "")
    if sorunlar and gs["fails"] >= ART_ARDA_TUR:
        nedenler = "; ".join(dict.fromkeys(t for _c, t in sorunlar))
        if not SHA_RE.match(onceki) or onceki == commit:
            action = "geri_alinamaz"        # onceki surum yok / ayni surum yeniden kuruldu: geri alinacak bir sey yok
        else:
            geri_al = env.get("GOZCU_GERI_AL", "/usr/local/sbin/trader-geri-al")
            rc = runner([geri_al, "--otomatik", "--neden", nedenler])
            if rc == 0:
                gs["rolled_back"] = True
                action = "geri_alindi"
            else:
                action = "geri_alma_basarisiz"   # sonraki turda yeniden denenir (geri-al kendi basarisizlik mesajini yollar)
    elif sorunlar:
        action = "sorun_dogrulaniyor"

    # oz-kontrol: 20. dakikadan sonra bir kez; yalniz sorunda TEK mesaj. Izleme zaten sorun goruyorsa (fails > 0) bekler:
    # geri alma karari mesajini kendisi yollar, ayni sorun icin iki mesaj gitmez.
    if age_min >= OZ_KONTROL_DK and not gs.get("selfcheck_done") and not gs.get("rolled_back"):
        if gs["fails"] == 0:
            tum = saglik_kirmizilari(env, yalniz_olumcul=False)
            if tum:
                basliklar = "; ".join(dict.fromkeys(t for _c, t in tum[:5]))
                send(f"[ML] ⚠️ Güncellemeden 20 dk sonraki kontrolde sorun var: {basliklar}.\n"
                     "Senden: geri almak için orkestratöre \"ML geri al\" yaz.")
                action = "oz_kontrol_sorun"
            gs["selfcheck_done"] = True
    elif gs.get("rolled_back"):
        gs["selfcheck_done"] = True
    write_json(gpath, gs)
    return action


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        env = dict(os.environ)
        print(tick(env, datetime.now(timezone.utc)))
    except Exception:  # noqa: BLE001
        log.exception("kurulum gozcusu beklenmedik hata (yoksayildi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
