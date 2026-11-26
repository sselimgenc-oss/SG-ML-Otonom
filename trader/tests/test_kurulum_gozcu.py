"""Kurulum gozcusu (scripts/kurulum_gozcu.py) + saglik kurulum-sonrasi sessizlik (scripts/health_run.py) testleri.

Ag/systemd yok: systemctl, geri alma komutu ve Telegram gonderimi enjekte edilir; durum dosyalari tmp_path'te."""
from __future__ import annotations

import dataclasses
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import health_run as HR  # noqa: E402
import kurulum_gozcu as KG  # noqa: E402
from trader_core import health as H  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 11, 20, 7, 33, 0, tzinfo=UTC)          # kurulum anı (10:33 TSI)
NEW, OLD = "b" * 40, "a" * 40


class World:
    def __init__(self, tmp: Path, *, tur="oto", onceki=OLD, release=NEW):
        self.tmp = tmp
        self.state = tmp / "state"
        self.state.mkdir(parents=True)
        self.var = tmp / "var"
        (self.var / "learner").mkdir(parents=True)
        self.release = tmp / "trader-release"
        self.release.write_text(f"COMMIT={release}\n", encoding="utf-8")
        self.health = tmp / "health.json"
        (self.state / "kurulum.json").write_text(
            json.dumps({"at": T0.strftime("%Y-%m-%dT%H:%M:%SZ"), "commit": NEW, "onceki": onceki, "tur": tur}), encoding="utf-8")
        self.units: dict[str, str] = {}          # "is-active trader-engine@learner.service" -> "active"
        self.active = True
        self.restarts = "0"
        self.live = False
        self.rollbacks: list[list[str]] = []
        self.rollback_rc = 0
        self.messages: list[str] = []
        self.env = {"OTO_STATE_DIR": str(self.state), "OTO_RELEASE_FILE": str(self.release), "HEALTH_STATE_FILE": str(self.health),
                    "ENGINE_VAR_DIR": str(self.var), "GOZCU_GERI_AL": "/x/trader-geri-al"}
        self.status(fresh_at=T0)

    # --- sahte sistem
    def sysctl(self, *args):
        if args[0] == "is-active":
            if "live" in args[-1]:
                return "active" if self.live else "inactive"
            return "active" if self.active else "inactive"
        if args[0] == "is-enabled":
            return "enabled" if (self.live and "live" in args[-1]) else "disabled"
        if args[0] == "show":
            return self.restarts
        return ""

    def status(self, fresh_at: datetime) -> None:
        (self.var / "learner" / "status.json").write_text(json.dumps(
            {"schema": HR.STATUS_SCHEMA, "bot": "learner", "loop_at": fresh_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
             "gate": {"code": "ok"}, "open_positions": []}), encoding="utf-8")

    def health_red(self, code, name="x", consecutive=2, level="CRIT"):
        fps = {f"{name}|{code}": {"first_seen": "z", "consecutive": consecutive, "last_alert_at": None, "alerted": False, "level": level}}
        self.health.write_text(json.dumps({"schema": 1, "fingerprints": fps}), encoding="utf-8")

    def tick(self, minutes: float) -> str:
        now = T0 + timedelta(minutes=minutes)
        self.status(fresh_at=now - timedelta(seconds=20)) if self.fresh else None
        return KG.tick(self.env, now, sysctl=self.sysctl, runner=self._run, send=self.messages.append)

    fresh = True

    def _run(self, cmd):
        self.rollbacks.append(cmd)
        return self.rollback_rc


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_saglikli_kurulumda_hicbir_sey_olmaz_20_dk_sessiz(w):
    outs = [w.tick(m) for m in (1, 5, 7, 9, 20, 21, 30, 59)]
    assert outs[0] == "isinma" and set(outs[1:]) <= {"saglikli"}
    assert w.rollbacks == [] and w.messages == []                          # sorun yok: mesaj YOK


def test_servis_calismiyorsa_2_ust_uste_turda_geri_alir_tek_komut(w):
    w.active = False
    assert w.tick(5) == "sorun_dogrulaniyor" and w.rollbacks == []          # tek tur: henuz degil (cift dogrulama)
    assert w.tick(7) == "geri_alindi"
    assert len(w.rollbacks) == 1 and w.rollbacks[0][:2] == ["/x/trader-geri-al", "--otomatik"]
    assert "motor servisi çalışmıyor" in w.rollbacks[0][-1]
    assert w.tick(9) == "geri_alindi" and len(w.rollbacks) == 1               # tekrar geri alinmaz
    assert w.messages == []                                                 # mesaji trader-geri-al yollar (tek mesaj)


def test_gecici_tek_tur_sorun_geri_alma_uretmez(w):
    w.active = False
    assert w.tick(5) == "sorun_dogrulaniyor"
    w.active = True
    assert w.tick(7) == "saglikli"
    w.active = False
    assert w.tick(9) == "sorun_dogrulaniyor"                                 # sayac sifirlanmisti
    assert w.rollbacks == []


def test_motor_durum_dosyasi_bayatsa_geri_alir(w):
    w.fresh = False
    w.status(fresh_at=T0)                                                   # 10 dk once yazilmis
    w.tick(10)
    assert w.tick(12) == "geri_alindi" and "durum dosyası" in w.rollbacks[0][-1]


def test_motor_durum_dosyasi_taze_ise_sorun_yok(w):
    assert w.tick(10) == "saglikli" and w.tick(12) == "saglikli"


def test_tekrarlayan_yeniden_baslama_geri_alir(w):
    w.restarts = "3"
    w.tick(6)
    assert w.tick(8) == "geri_alindi" and "yeniden başladı" in w.rollbacks[0][-1]


def test_saglikta_olumcul_kirmizi_geri_alir_olumcul_olmayan_almaz(w):
    w.health_red("backup_stale", name="backup_age")                        # olumcul degil
    assert w.tick(6) == "saglikli" and w.tick(8) == "saglikli" and w.rollbacks == []
    w.health_red("oom_killed", name="container_restarts:trader-learner")    # olumcul
    w.tick(10)
    assert w.tick(12) == "geri_alindi" and len(w.rollbacks) == 1
    w.health_red("oom_killed", name="c", consecutive=1)                      # tek tur (sari): sayilmaz


def test_tek_turluk_saglik_kirmizisi_sayilmaz(tmp_path):
    w = World(tmp_path)
    w.health_red("oom_killed", name="c", consecutive=1)
    assert w.tick(6) == "saglikli" and w.tick(8) == "saglikli" and w.rollbacks == []


def test_oz_kontrol_20_dk_sorun_varsa_tek_mesaj_yoksa_sessiz(w):
    w.health_red("backup_stale", name="backup_age")                        # olumcul degil -> geri alma yok, oz-kontrol uyarir
    assert w.tick(19) == "saglikli" and w.messages == []
    assert w.tick(20) == "oz_kontrol_sorun"
    assert len(w.messages) == 1 and "20 dk sonra" in w.messages[0] and "Yedek" in w.messages[0]
    w.tick(22)
    w.tick(40)
    assert len(w.messages) == 1                                              # bir kez


def test_oz_kontrol_izleme_sorun_gorurken_ikinci_mesaj_gondermez(w):
    w.health_red("backup_stale", name="backup_age")
    w.active = False
    w.tick(18)
    assert w.tick(20) == "geri_alindi"                                       # geri alma mesaji trader-geri-al'dan
    assert w.messages == []


def test_geri_alma_basarisizsa_sonraki_turda_yeniden_dener(w):
    w.active = False
    w.rollback_rc = 1
    w.tick(5)
    assert w.tick(7) == "geri_alma_basarisiz"
    w.rollback_rc = 0
    assert w.tick(9) == "geri_alindi" and len(w.rollbacks) == 2


@pytest.mark.parametrize("minutes", [61, 90, 600])
def test_60_dk_sonra_izleme_biter(w, minutes):
    w.active = False
    assert w.tick(minutes) == "pencere_disi" and w.rollbacks == []


def test_atlanan_durumlar(tmp_path):
    w = World(tmp_path / "1", tur="geri-al")
    w.active = False
    assert w.tick(10) == "geri_al_kurulumu" and w.rollbacks == []            # geri alma kurulumu izlenmez: dongu yok
    w = World(tmp_path / "2", release=OLD)
    assert w.tick(10) == "kurulum_tamamlanmadi" and w.rollbacks == []        # kurulum yarida kalmis/baska surum
    w = World(tmp_path / "3")
    w.live = True
    w.active = False
    assert w.tick(10) == "canli_birim" and w.rollbacks == []                 # canliya hic dokunulmaz
    w = World(tmp_path / "4", onceki=NEW)
    w.active = False
    w.tick(10)
    assert w.tick(12) == "geri_alinamaz" and w.rollbacks == []               # ayni surum yeniden kuruldu: geri alinacak yok
    w = World(tmp_path / "5", onceki="")
    w.active = False
    w.tick(10)
    assert w.tick(12) == "geri_alinamaz"
    (w.state / "kurulum.json").unlink()
    assert w.tick(14) == "isaret_yok"


def test_yeni_kurulum_sayaclari_sifirlar(w):
    w.active = False
    w.tick(5)
    gs = json.loads((w.state / "gozcu.json").read_text())
    assert gs["fails"] == 1
    other = "c" * 40
    (w.state / "kurulum.json").write_text(json.dumps({"at": T0.strftime("%Y-%m-%dT%H:%M:%SZ"), "commit": other, "onceki": NEW,
                                                      "tur": "oto"}), encoding="utf-8")
    w.release.write_text(f"COMMIT={other}\n", encoding="utf-8")
    w.tick(5)
    assert json.loads((w.state / "gozcu.json").read_text())["commit"] == other
    assert json.loads((w.state / "gozcu.json").read_text())["fails"] == 1 and w.rollbacks == []


def test_telegram_gonderimi_token_maskelenir_ve_anahtarsiz_sessiz(tmp_path):
    env = {"OTO_TELEGRAM_ENV": str(tmp_path / "yok.env")}
    assert KG.tg_send(env, "x") is False
    assert "<maskeli>" in KG.mask("bot123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abc")
    assert "sk-ant-<maskeli>" in KG.mask("sk-ant-api03-SECRET")


def test_gozcu_birimi_ve_zamanlayici():
    d = ROOT / "deploy"
    s = (d / "trader-kurulum-gozcu.service").read_text(encoding="utf-8")
    t = (d / "trader-kurulum-gozcu.timer").read_text(encoding="utf-8")
    assert "User=root" in s and "Type=oneshot" in s and "kurulum_gozcu.py" in s and "-I" in s
    assert "Slice=trader.slice" in s and "MemoryMax=100M" in s          # hafif olcum birimi trader.slice icinde (WP-18 kurali)
    assert "OnUnitActiveSec=2min" in t and "Persistent=false" in t


# ----------------------------------------------------------------------------- saglik: kurulum sonrasi 15 dk sessizlik
def _snap(**over):
    base = dict(now=T0, timeframe_s=3600,
                api={"learner": H.ApiProbe(ping_ok=True, last_process_at=T0, last_candle_open=T0.replace(minute=0), open_trade_ids=(),
                                           dry_run=True)},
                ledger={"learner": H.LedgerProbe(last_write_at=T0, spool_lines=0, unledgered_ids=(), schema_ok=True,
                                                 has_active_params=True, spool_corrupt_lines=0)},
                disk_free_bytes=20 * 2**30, disk_total_bytes=100 * 2**30, 
                containers={"trader-learner": H.ContainerProbe(state="running", restart_count=1, started_at=T0 - timedelta(days=2),
                                                              oom_killed=False)},
                prev_restart_counts={"trader-learner": 1}, last_backup_at=T0 - timedelta(hours=2))
    base.update(over)
    return H.HealthSnapshot(**base)


def _taze(sn, n):
    """Motor dongusu her turda tazelenir (yalniz 'dongu bayat' senaryosu bayat kalir)."""
    api = {b: p if p.last_process_at < T0 - timedelta(minutes=30) else dataclasses.replace(p, last_process_at=n)
           for b, p in sn.api.items()}
    return dataclasses.replace(sn, now=n, api=api)


def _run_turns(tmp_path, turns, marker_at=T0):
    """turns: [(dakika_sonra, snapshot)]. Doner: [(dakika, [uyari kodlari])]."""
    (tmp_path / "kurulum.json").write_text(json.dumps({"at": marker_at.strftime("%Y-%m-%dT%H:%M:%SZ")}), encoding="utf-8")
    env = {"INSTALL_MARKER": str(tmp_path / "kurulum.json")}
    sp, out = tmp_path / "state.json", []
    for minute, snapshot in turns:
        now = T0 + timedelta(minutes=minute)
        notifier = H.NullNotifier()
        HR.run_once(env, now=now, state_path=sp, notifier=notifier, sender=HR.NoHeartbeat(),
                    snapshot_fn=lambda e, s, n, sn=snapshot: _taze(sn, n))
        out.append((minute, [(a.code, a.level.value) for a in notifier.sent]))
    return out


def test_saglik_kurulumdan_sonra_15_dk_yalniz_olumcul_sonra_tek_ozet(tmp_path):
    down = {"learner": dataclasses.replace(_snap().api["learner"], last_process_at=T0 - timedelta(hours=1))}   # stale_loop: olumcul
    soft = _snap(disk_free_bytes=int(0.5 * 2**30))                             # disk_low: olumcul degil
    both = _snap(api=down, disk_free_bytes=int(0.5 * 2**30))
    out = dict(_run_turns(tmp_path, [(1, both), (6, both), (11, both), (16, both), (21, both)]))
    assert out[1] == []                                                        # cift dogrulama: ilk tur sari
    assert out[6] == [("stale_loop", "CRIT")]                             # olumcul: sessizlikte gecer, disk_low tutulur
    assert out[11] == []
    codes16 = [c for c, _ in out[16]]                                          # pencere bitti (T0+15): tutulanlar ozetle gelir
    assert "quiet_summary" in codes16 and codes16.count("quiet_summary") == 1 and "disk_low" in codes16
    assert all(c != "quiet_summary" for c, _ in out[21])                       # ozet bir kez
    # yalniz olumcul olmayan sorun: pencere boyunca HIC mesaj yok
    sub_dir = tmp_path / "x"
    sub_dir.mkdir()
    out2 = dict(_run_turns(sub_dir, [(1, soft), (6, soft), (11, soft)]))
    assert all(v == [] for v in out2.values()), out2


def test_marker_yoksa_ya_da_eski_ise_sessizlik_uygulanmaz(tmp_path):
    soft = _snap(disk_free_bytes=int(0.5 * 2**30))
    eski = T0 - timedelta(hours=3)
    out = dict(_run_turns(tmp_path, [(1, soft), (6, soft)], marker_at=eski))
    assert out[1] == [] and [c for c, _ in out[6]] == ["disk_low"]            # sessizlik yok; yalniz cift dogrulama
    assert HR.install_quiet_until({"INSTALL_MARKER": str(tmp_path / "yok.json")}, T0) is None
    (tmp_path / "bozuk.json").write_text("{x", encoding="utf-8")
    assert HR.install_quiet_until({"INSTALL_MARKER": str(tmp_path / "bozuk.json")}, T0) is None


def test_varsayilan_calistirici_geri_almayi_gecici_birimde_calistirir(monkeypatch):
    calls = []

    class R:
        returncode = 0

    monkeypatch.setattr(KG.shutil, "which", lambda n: "/usr/bin/systemd-run")
    monkeypatch.setattr(KG.subprocess, "run", lambda cmd, **k: calls.append(cmd) or R())
    assert KG.default_runner(["/usr/local/sbin/trader-geri-al", "--otomatik", "--neden", "x"]) == 0
    c = calls[0]
    assert c[0] == "systemd-run" and "--wait" in c and "MemoryMax=800M" in c and c[-4:] == [
        "/usr/local/sbin/trader-geri-al", "--otomatik", "--neden", "x"]
    monkeypatch.setattr(KG.shutil, "which", lambda n: None)
    KG.default_runner(["a"])
    assert calls[1] == ["a"]
