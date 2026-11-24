"""`arm_conflict` kayiplari: kurulum x zaman dilimi basina sayi ve "alinsaydi" net R (yalniz bilgi; karar yoluna girmez)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from trader_core import alinmayan_sonuc as AS
from trader_reports import yorumcu as Y

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import weekly_summary_run as W  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def _atl(i, gun, neden, arm):
    return {"id": i, "skip_reason": neden, "ts": NOW - timedelta(days=gun), "arm_id": arm}


def _cf(i, gun, neden, r):
    return {"decision_id": i, "skip_reason": neden, "ts": NOW - timedelta(days=gun), "r": r}


ATL = [_atl(1, 1, "arm_conflict", "T1@1h"), _atl(2, 2, "arm_conflict", "T1@1h"), _atl(3, 3, "arm_conflict", "T1@1h"),
       _atl(4, 1, "arm_conflict", "M1@15m"), _atl(5, 2, "max_positions", "T1@1h"), _atl(6, 30, "arm_conflict", "T1@1h")]
CFR = [_cf(1, 1, "arm_conflict", 1.5), _cf(2, 2, "arm_conflict", -1.0),            # 3 numarali kayip cozulmedi
       _cf(4, 1, "arm_conflict", 0.5), _cf(5, 2, "max_positions", 9.0), _cf(6, 30, "arm_conflict", 2.0)]


def test_kol_basina_kayip_sayisi_ve_net_r():
    d = AS.olustur(CFR, ATL, [], NOW)
    son7 = {r["etiket"]: r for r in d["arm_conflict"]["tablolar"]}
    assert set(son7) == {"T1@1h", "M1@15m"}                                       # max_positions satiri karismaz
    t1 = son7["T1@1h"]
    assert (t1["kayip"], t1["n"], t1["kazanan"], t1["isabet_yuzde"], t1["toplam_pnl"], t1["ortalama_pnl"]) == (3, 2, 1, 50.0, 0.5, 0.25)
    assert son7["M1@15m"]["kayip"] == 1 and son7["M1@15m"]["toplam_pnl"] == 0.5
    tum = {r["etiket"]: r for r in d["arm_conflict"]["tum_zamanlar"]}
    assert tum["T1@1h"]["kayip"] == 4 and tum["T1@1h"]["n"] == 3 and tum["T1@1h"]["toplam_pnl"] == 2.5


def test_cozulmeyen_kol_icin_bos_alanlar_uydurulmaz():
    d = AS.olustur([], [_atl(1, 1, "arm_conflict", "S1@4h")], [], NOW)
    r = d["arm_conflict"]["tablolar"][0]
    assert r["kayip"] == 1 and r["n"] == 0 and r["isabet_yuzde"] is None and r["ortalama_pnl"] is None


def test_mevcut_neden_tablosu_degismez():
    d = AS.olustur(CFR, ATL, [], NOW)
    nedenler = {r["etiket"] for r in d["tablolar"]["neden"]}
    assert {"arm_conflict", "max_positions"} <= nedenler


def test_haftalik_satir_ve_yorumcu_ozeti(tmp_path):
    doc = AS.olustur(CFR, ATL, [], NOW)
    p = tmp_path / "alinmayan_sonuc_v1.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    satir = W.arm_conflict_satiri(None, durum_path=p)
    assert satir and "T1@1h 3 kayıp" in satir and "+0.50R" in satir
    oz = Y.arm_conflict_ozeti(doc)
    assert {r["kol"] for r in oz} == {"T1@1h", "M1@15m"} and oz[0]["kayip"] >= 1


def test_veri_yoksa_satir_yazilmaz(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps(AS.olustur([], [], [], NOW)), encoding="utf-8")
    assert W.arm_conflict_satiri(None, durum_path=p) is None
    assert Y.arm_conflict_ozeti({"sema": "baska"}) is None
    assert W.arm_conflict_satiri(None, durum_path=tmp_path / "yok.json") is None
