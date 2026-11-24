"""Denetim duzeltmesi (20.11): M1 gece egitiminde bir zaman diliminin hatasi digerlerini durdurmaz; hata `status=error`
olarak cikti ve CSV'ye yazilir; genel cikis kodu yine 3 (saglik gorunurlugu)."""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "scripts", ROOT / "research", ROOT / "paket", ROOT / "src"):
    sys.path.insert(0, str(_p))
import export_paper_records as EPR  # noqa: E402
import ml_retrain_run as R  # noqa: E402
import pa_proposer_build as PB  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 11, 20, tzinfo=UTC)


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr(EPR, "export", lambda led, cf: ([], None))
    monkeypatch.setattr(PB, "_paper_rows", lambda recs, bars, tf, d: ([], {}))
    cagri: list = []

    def sahte(rows, *, arm_id, created_at=None, max_rows=0):
        cagri.append(arm_id)
        if arm_id == "M1@4h":
            raise ValueError("4h patladi")
        return None
    monkeypatch.setattr(R.TR, "train_tf", sahte)
    return cagri


def test_bir_tf_hatasi_digerlerini_durdurmaz(tmp_path, monkeypatch):
    cagri = _patch(monkeypatch, tmp_path)
    rows: list = []
    out = R.m1_nightly(None, None, history_dir=str(tmp_path), tfs=("1h", "4h", "15m", "1d"),
                       models_dir=str(tmp_path / "m"), now=NOW, csv_rows=rows)
    assert cagri == ["M1@1h", "M1@4h", "M1@15m", "M1@1d"]
    assert out["4h"]["status"] == "error" and "ValueError" in out["4h"]["reason"] and "4h patladi" in out["4h"]["reason"]
    assert [out[t]["status"] for t in ("1h", "15m", "1d")] == ["no_model"] * 3
    by = {r[0]: r for r in rows}
    assert len(rows) == 4 and "status=error" in by["m1_nightly_4h_2026-11-20"][3]
    assert "status=no_model" in by["m1_nightly_1d_2026-11-20"][3]


def test_main_cikis_kodu_tf_hatasinda_3_ve_digerleri_yazilir(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    from trader_core import ledger as L
    monkeypatch.setattr(L, "open_ledger", lambda *a, **k: SimpleNamespace(close=lambda: None))
    rc = R.main(["--once", "--ledger", str(tmp_path / "x.sqlite"),
                 "--m1-models-dir", str(tmp_path / "m1"), "--paper-models-csv", str(tmp_path / "p.csv"),
                 "--history-dir", str(tmp_path / "h"), "--m1-tfs", "1h,4h,1d"], now_fn=lambda: NOW)
    assert rc == 3
    names = [r[0] for r in csv.reader(open(tmp_path / "p.csv", encoding="utf-8"))][1:]
    assert len(names) == 3
    assert {"m1_nightly_1h_2026-11-20", "m1_nightly_4h_2026-11-20", "m1_nightly_1d_2026-11-20"} <= set(names)


def test_tum_tf_saglamsa_cikis_0(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    from trader_core import ledger as L
    monkeypatch.setattr(L, "open_ledger", lambda *a, **k: SimpleNamespace(close=lambda: None))
    rc = R.main(["--once", "--ledger", str(tmp_path / "x.sqlite"),
                 "--m1-models-dir", str(tmp_path / "m1"), "--paper-models-csv", str(tmp_path / "p.csv"),
                 "--history-dir", str(tmp_path / "h"), "--m1-tfs", "1h,1d"], now_fn=lambda: NOW)
    assert rc == 0
