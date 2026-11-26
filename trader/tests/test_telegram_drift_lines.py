"""Sapma izleyicisi (drift.json) artik gunluk Telegram ozetinde yok (26.11 sadelesme); dosya yazimi baska yerde sinanir."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trader_core import telegram as T  # noqa: E402

NOW = datetime(2026, 12, 20, 18, 0, tzinfo=timezone.utc)


def z(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class Cfg:
    def __init__(self, base: Path):
        self.status_path = str(base / "status.json")
        self.ledger_path = str(base / "ledger.sqlite")
        self.health_state = ""
        self.var_dir = str(base)
        self.config_dir = ""


def put(d: Path, age_h=1, lines=("📐 Bot beklendiği gibi davranıyor",), schema="drift/1"):
    d.mkdir(parents=True, exist_ok=True)
    (d / "drift.json").write_text(json.dumps({"schema": schema, "generated_at": z(NOW - timedelta(hours=age_h)),
                                              "report_lines": list(lines)}), encoding="utf-8")


def test_davranis_satirlari_telegramdan_kalkti(tmp_path):
    """26.11 sadelesme: sapma izleyicisi satirlari (drift.json) gunluk ozette/komutlarda yok; dosya yazilmaya devam eder, Telegram okumaz."""
    for ad in ("rapor_davranis", "_davranis_satirlari", "DAVRANIS_YOK", "DAVRANIS_MAX_YAS_S"):
        assert not hasattr(T, ad), ad
    put(tmp_path / "learner", lines=["📐 Bot beklendiği gibi davranıyor (sıklık, maliyet, fonlama normal)"])
    cfg = Cfg(tmp_path / "learner")
    secs = T.default_sections(cfg, NOW, "2026-12-20")
    assert "Davranış" not in secs and secs == {}


def test_gunluk_ozet_drift_dosyasi_olsa_da_sapma_satiri_yok(tmp_path):
    put(tmp_path / "learner", lines=["📐 Bot beklendiği gibi davranıyor"])
    cfg = Cfg(tmp_path / "learner")
    text = T.build_report(cfg, NOW, "2026-12-20", {"Davranış": lambda: "📐 x"})            # bolum verilse bile okunmaz
    assert "Günlük özet" in text and "📐" not in text
    # bolum patlasa bile rapor uretilir
    def boom():
        raise RuntimeError("x")
    assert "Günlük özet" in T.build_report(cfg, NOW, "2026-12-20", {"Duraklatma": boom})
