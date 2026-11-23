"""Sağlık uyarıları sade Türkçe: ham kontrol adı/kodu kullanıcıya gitmez; parmak izi ve `code` değişmez."""
import re
from datetime import datetime, timedelta, timezone

from trader_core import health as H
from trader_core.health import Status

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def _rep(*rs):
    return H.HealthReport(NOW, tuple(rs), Status.CRIT, False)


def _veto_crit():
    return H.CheckResult("veto_file_age", Status.CRIT, "veto_missing", "veto belgesi yok/bayat: girisler kapali")


def _confirmed(rep):
    """CRIT (acil olmayan) uyarı ardışık doğrulama ister: iki tur."""
    a, st = H.plan_alerts(rep, None, NOW)
    assert a == []
    return H.plan_alerts(rep, st, NOW + timedelta(minutes=5))


def test_veto_crit_alert_text():
    a, st = _confirmed(_rep(_veto_crit()))
    assert len(a) == 1
    al = a[0]
    assert al.title == "🚨 Sorun: Veto (yapay zekâ filtresi) güncel değil — yeni işlemler bekletiliyor"
    assert "veto_file_age" not in al.title + al.body and "veto_missing" not in al.title + al.body
    assert al.code == "veto_missing" and al.fingerprint == "veto_file_age|veto_missing" and al.level is Status.CRIT
    assert len(al.title) <= 80 and len(al.body) <= 500


def test_veto_recovery_text():
    _, st = _confirmed(_rep(_veto_crit()))
    ok = H.HealthReport(NOW + timedelta(minutes=5), (), Status.OK, True)
    a, _ = H.plan_alerts(ok, st, NOW + timedelta(minutes=5))
    assert len(a) == 1 and a[0].level is Status.OK
    assert a[0].title == "✅ Düzeldi: Veto (yapay zekâ filtresi) yeniden güncel"
    assert "veto_missing" not in a[0].title + a[0].body and "yeniden saglikli" not in a[0].body
    assert a[0].code == "veto_missing" and a[0].fingerprint == "veto_file_age|veto_missing"


def test_warn_alert_prefix_and_unknown_check_is_generic():
    w = H.CheckResult("disk_free", Status.WARN, "disk_low", "x")
    a, _ = _confirmed(_rep(w))
    assert a and a[0].title.startswith("⚠️ Dikkat: ")
    u = H.CheckResult("yeni_bilinmeyen", Status.CRIT, "disk_low", "ayrıntı")      # disk_low acil kod: hemen uyarır
    _, st0 = H.plan_alerts(_rep(u), None, NOW)
    a, _ = H.plan_alerts(_rep(u), st0, NOW + timedelta(minutes=5))            # kirmizi cift dogrulama: 2. tur
    assert a[0].title == "🚨 Sorun: Bir sistem kontrolü sorunlu"
    assert "yeni_bilinmeyen" not in a[0].title + a[0].body and "disk_low" not in a[0].title + a[0].body


def test_every_known_check_has_short_turkish_text():
    for base, (sorun, duzeldi, anlam) in H._HEALTH_TR.items():
        for mark in ("🚨 Sorun: ", "⚠️ Dikkat: ", "✅ Düzeldi: "):
            txt = mark + (duzeldi if "Düzeldi" in mark else sorun)
            assert len(txt) <= 80, (base, len(txt))
        assert not re.search(r"[a-z]+_[a-z_]+", sorun + duzeldi + anlam), base          # ham kod/ad yok
    # health.py'deki her kontrol adı sözlükte (":bot" eki hariç)
    src = open(H.__file__, encoding="utf-8").read()
    names = set(re.findall(r'name = f?"([a-z0-9_]+)', src)) | {"disk_free", "memory", "swap", "backup_age",
                                                             "veto_file_age", "budget_status"}
    assert names <= set(H._HEALTH_TR), names - set(H._HEALTH_TR)
