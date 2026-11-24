"""Saglik: DL1 paket yasi satiri (dl1_paket_age) + toplayici (probe_dl1_paket)."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader_core import health as H

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "engine"))
import dl1_support as S  # noqa: E402


def _ev(probe):
    snap = H.HealthSnapshot(now=NOW, dl1_paket=probe)
    return {r.name: r for r in H.evaluate(snap).results}["dl1_paket_age"]


def _p(yas_gun, kalan_gun):
    return H.Dl1PaketProbe("ok", NOW - timedelta(days=yas_gun), NOW + timedelta(days=kalan_gun))


def test_yok_warn():
    r = _ev(H.Dl1PaketProbe("missing"))
    assert r.status is H.Status.WARN and r.code == "dl1_paket_yok" and "DL1 paketi henuz yok" in r.detail


def test_taze_ok_ve_yas_satiri():
    r = _ev(_p(3, 42))
    assert r.status is H.Status.OK and "3.0 gun" in r.detail


def test_eski_warn_ama_islem_durmaz_yaklasiyor_yok():
    """24.11: son kullanma paketi durdurmaz; 45 gunden yasli -> WARN `dl1_paket_eski` (metin 'islem yapmaya devam'), yaklasirken uyari yok."""
    assert _ev(_p(40, 5)).status is H.Status.OK
    r = _ev(_p(46, -1))
    assert r.status is H.Status.WARN and r.code == "dl1_paket_eski" and "devam" in r.detail and "durdu" not in r.detail
    assert _ev(_p(38, 7.5)).status is H.Status.OK


def test_bozuk_warn_ve_alan_yoksa_denetim_yok():
    assert _ev(H.Dl1PaketProbe("unreadable")).code == "dl1_paket_bozuk"
    assert "dl1_paket_age" not in {r.name for r in H.evaluate(H.HealthSnapshot(now=NOW)).results}


def test_turkce_uyari_metni():
    s, d, a = H._health_tr("dl1_paket_age", "dl1_paket_eski")
    assert "DL1" in s and "DL1" in a


def test_probe_dl1_paket(tmp_path):
    spec = importlib.util.spec_from_file_location("health_run_dl1", ROOT / "scripts" / "health_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    env = {"TRADER_DATA_ROOT": str(tmp_path)}
    assert m.probe_dl1_paket(env).file_state == "missing"
    d = tmp_path / "models" / "dl1"
    d.mkdir(parents=True)
    S.yaz(d / "DL1@1h.json", S.paket_sozlugu(NOW - timedelta(days=2)))
    assert m.probe_dl1_paket(env).file_state == "missing"                       # dort zaman dilimi: biri eksikse eksik
    for tf, yas in (("15m", 1), ("4h", 5), ("1d", 3)):
        S.yaz(d / f"DL1@{tf}.json", S.paket_sozlugu(NOW - timedelta(days=yas), tf=tf))
    p = m.probe_dl1_paket(env)
    assert p.file_state == "ok" and p.created_at == NOW - timedelta(days=5) and p.expires_at == NOW + timedelta(days=40)    # en eski paket
    S.yaz(d / "DL1@4h.json", "{bozuk")
    assert m.probe_dl1_paket(env).file_state == "unreadable"



def test_dl1_kol_ayarda_yoksa_denetim_uretilmez(tmp_path):
    """23.11: DL1@1h ayarda kol degilken 'paket yok' WARN gurultu olur (CI hazirlik tatbikati); yalniz kol ayardayken denetlenir."""
    import json
    spec = importlib.util.spec_from_file_location("health_run_dl1b", ROOT / "scripts" / "health_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    (tmp_path / "engine.paper.json").write_text(json.dumps({"arms": ["T1@1h"]}), encoding="utf-8")
    assert m.dl1_kolda({"ENGINE_CONFIG_DIR": str(tmp_path)}) is False
    (tmp_path / "engine.paper.json").write_text(json.dumps({"arms": ["T1@1h", "DL1@4h"]}), encoding="utf-8")
    assert m.dl1_kolda({"ENGINE_CONFIG_DIR": str(tmp_path)}) is True
    assert m.dl1_kolda({"ENGINE_CONFIG_DIR": str(tmp_path / "yok")}) is True     # okunamazsa temkinli: denetle
