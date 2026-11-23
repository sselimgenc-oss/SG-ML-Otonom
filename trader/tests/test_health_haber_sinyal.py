"""Saglik: 'haber sinyali yasi' (haber_sinyal_age) kontrolu + toplayici (probe_haber_sinyal)."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import health as H

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def _ev(probe, **kw):
    snap = H.HealthSnapshot(now=NOW, haber_sinyal=probe, **kw)
    return {r.name: r for r in H.evaluate(snap).results}["haber_sinyal_age"]


def _p(age_s, valid_s=3 * 3600, **kw):
    t = NOW - timedelta(seconds=age_s)
    return H.HaberSinyalProbe("ok", t, t + timedelta(seconds=valid_s), True, **kw)


def test_taze_ok():
    r = _ev(_p(600))
    assert r.status is H.Status.OK and r.code == "ok"


def test_bayat_warn():
    r = _ev(_p(3 * 3600 + 5))
    assert r.status is H.Status.WARN and r.code == "haber_sinyal_bayat"


def test_bozuk_warn():
    assert _ev(H.HaberSinyalProbe("unreadable", job_installed=True)).status is H.Status.WARN


def test_dosya_yok_is_kurulu_degil_info():
    r = _ev(H.HaberSinyalProbe("missing", job_installed=False, job_since=NOW - timedelta(days=9)))
    assert r.status is H.Status.OK and r.code == "haber_sinyal_info" and r.detail.startswith("INFO")


def test_dosya_yok_ilk_saatlerde_info():
    r = _ev(H.HaberSinyalProbe("missing", job_installed=True, job_since=NOW - timedelta(hours=1, minutes=59)))
    assert r.status is H.Status.OK and r.code == "haber_sinyal_info"
    # ana kurulum zamani (installed_at) eski olsa bile haber isinin kendi ilk zamani esas
    r = _ev(H.HaberSinyalProbe("missing", job_installed=True, job_since=NOW - timedelta(minutes=30)), installed_at=NOW - timedelta(days=30))
    assert r.status is H.Status.OK and r.code == "haber_sinyal_info"


def test_dosya_yok_is_kurulu_ve_eski_warn():
    r = _ev(H.HaberSinyalProbe("missing", job_installed=True, job_since=NOW - timedelta(hours=2, minutes=1)))
    assert r.status is H.Status.WARN and r.code == "haber_sinyal_yok"
    r = _ev(H.HaberSinyalProbe("missing", job_installed=True))                  # ilk zaman bilinmiyor: INFO'ya siginilmaz
    assert r.status is H.Status.WARN and r.code == "haber_sinyal_yok"


def test_anahtar_yok_warn_ve_bayat_ek_bilgi():
    r = _ev(H.HaberSinyalProbe("missing", job_installed=True, job_status="anahtar_yok", job_since=NOW - timedelta(minutes=10)))
    assert r.status is H.Status.WARN and r.code == "haber_anahtar_yok" and "haber anahtari yok, haber kolu sinyal goremiyor" in r.detail
    assert _ev(_p(600, job_status="anahtar_yok")).code == "haber_anahtar_yok"
    r = _ev(_p(3 * 3600 + 5, job_status="api_hata"))
    assert r.code == "haber_sinyal_bayat" and "api_hata" in r.detail
    assert _ev(_p(600, job_status="api_hata")).status is H.Status.OK              # dosya taze: yalniz yas olculur


def test_probe_yoksa_kontrol_uretilmez():
    names = {r.name for r in H.evaluate(H.HealthSnapshot(now=NOW)).results}
    assert "haber_sinyal_age" not in names


def _run_mod():
    spec = importlib.util.spec_from_file_location("health_run_hs", ROOT / "scripts" / "health_run.py")
    sys.path.insert(0, str(ROOT / "scripts"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_toplayici(tmp_path):
    m = _run_mod()
    d = tmp_path / "learner" / "sinyal"
    assert m.probe_haber_sinyal(str(tmp_path), str(tmp_path / "yok.timer")).file_state == "missing"
    d.mkdir(parents=True)
    (d / "haber_sinyal.json").write_text("{bozuk")
    assert m.probe_haber_sinyal(str(tmp_path), str(tmp_path / "yok.timer")).file_state == "unreadable"
    up = int(NOW.timestamp() * 1000)
    (d / "haber_sinyal.json").write_text(json.dumps({"schema": "haber_sinyal/2", "uretim_ms": up, "gecerlilik_sonu_ms": up + 99 * 3600_000,
                                                     "enstrumanlar": {}}))
    (d / "haber_sinyal_durum.json").write_text("{}")
    p = m.probe_haber_sinyal(str(tmp_path), str(tmp_path / "yok.timer"))
    assert p.file_state == "ok" and p.job_installed and p.produced_at == NOW and p.valid_until == NOW + timedelta(hours=3)
    assert p.job_status is None and p.job_since is not None            # durum dosyasi mtime'a duser
    ilk = int((NOW - timedelta(hours=5)).timestamp() * 1000)
    (d / "haber_sinyal_durum.json").write_text(json.dumps({"son_alim": 0, "olaylar": [], "calisma": {"durum": "anahtar_yok", "zaman_ms": up, "ilk_ms": ilk}}))
    p = m.probe_haber_sinyal(str(tmp_path), str(tmp_path / "yok.timer"))
    assert p.job_status == "anahtar_yok" and p.job_since == NOW - timedelta(hours=5)


def test_toplayici_unit_dosyasi_kurulu_sayilir_ve_mtime(tmp_path):
    import os
    m = _run_mod()
    unit = tmp_path / "trader-haber-sinyal.timer"
    unit.write_text("[Timer]")
    t = (NOW - timedelta(hours=7)).timestamp()
    os.utime(unit, (t, t))
    p = m.probe_haber_sinyal(str(tmp_path), str(unit))                  # durum dosyasi yok, sinyal yok
    assert p.file_state == "missing" and p.job_installed and p.job_since == NOW - timedelta(hours=7) and p.job_status is None
    assert _ev(p).code == "haber_sinyal_yok"
    assert not m.probe_haber_sinyal(str(tmp_path), str(tmp_path / "yok.timer")).job_installed


def test_turkce_uyari_metni():
    s, d, a = H._health_tr("haber_sinyal_age", "haber_sinyal_bayat")
    assert "Haber sinyali" in s and "HB1" in a
