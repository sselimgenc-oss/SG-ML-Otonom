"""25.11 kullanici karari: ders sistemi dondurulur (`dondurulmus`). --once/--resolve servisi hic kurmaz; false iken eski yol."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lesson_run as LR  # noqa: E402

from trader_core import lesson as LS  # noqa: E402

RID = "lr-2026-11-25-1"


class _Kuruldu(Exception):
    pass


def _cfg(tmp_path, dondurulmus):
    p = tmp_path / "lesson.json"
    p.write_text(json.dumps({"ledger_path": str(tmp_path / "l.sqlite"), "store_path": str(tmp_path / "s.sqlite"),
                             "dondurulmus": dondurulmus}), encoding="utf-8")
    return str(p)


def _kurulum_yasak(monkeypatch):
    def _bomba(*a, **k):
        raise AssertionError("LessonService kurulmamaliydi")
    monkeypatch.setattr(LS, "LessonService", _bomba)


def test_repo_config_dondurulmus():
    assert json.loads((ROOT / "config/lesson.json").read_text())["dondurulmus"] is True
    assert LS.load_config(ROOT / "config/lesson.json").dondurulmus is True
    assert LS.LessonConfig().dondurulmus is False
    with pytest.raises(LS.LessonConfigError):
        LS.LessonConfig(dondurulmus="evet")


def test_load_config_okur(tmp_path):
    assert LS.load_config(_cfg(tmp_path, True)).dondurulmus is True
    assert LS.load_config(_cfg(tmp_path, False)).dondurulmus is False


def test_once_dondurulmus_servis_kurmaz(tmp_path, monkeypatch, capsys):
    _kurulum_yasak(monkeypatch)
    assert LR.main(["--once", "--config", _cfg(tmp_path, True)], env={}) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "dondurulmus"


def test_dry_run_dondurulmus_atlanir(tmp_path, monkeypatch, capsys):
    _kurulum_yasak(monkeypatch)
    assert LR.main(["--once", "--dry-run", "--config", _cfg(tmp_path, True)], env={}) == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "dondurulmus"


def test_resolve_dondurulmus_servis_kurmaz(tmp_path, monkeypatch, capsys):
    _kurulum_yasak(monkeypatch)
    assert LR.main(["--resolve", RID, "--approve", "--config", _cfg(tmp_path, True)], env={}) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (out["status"], out["request_id"]) == ("dondurulmus", RID)


def test_once_dondurulmamis_eski_yol(tmp_path, monkeypatch):
    def _sentinel(*a, **k):
        raise _Kuruldu
    monkeypatch.setattr(LS, "LessonService", _sentinel)
    with pytest.raises(_Kuruldu):
        LR.main(["--once", "--allow-log-notifier", "--mode", "rule_proxy", "--config", _cfg(tmp_path, False)], env={})


def test_resolve_dondurulmamis_eski_yol(tmp_path, monkeypatch, capsys):
    kuruldu = []

    def _sentinel(*a, **k):
        kuruldu.append(1)
        raise _Kuruldu
    monkeypatch.setattr(LS, "LessonService", _sentinel)
    LR.main(["--resolve", RID, "--approve", "--config", _cfg(tmp_path, False)], env={})
    assert kuruldu
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["status"] == "error"
