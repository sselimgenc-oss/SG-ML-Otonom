"""P1-0: olcum kayit defteri (`trader_engine.olcumler`) ile `docs/inceleme-200.md` birebir; ozet.json; hata yalitimi; tek-seferlik satir."""
from __future__ import annotations

import dataclasses
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "ml1"))
pytest.importorskip("pyarrow")

from olcum_destek import D0, Gorunum, islem, sahte_ogren, seri_1dk  # noqa: E402
from trader_engine import ml1_sanal as SN  # noqa: E402
from trader_engine import olcumler as OL  # noqa: E402

DOC = ROOT / "docs" / "inceleme-200.md"
KIMLIK = re.compile(r"`([a-z0-9_]+)`")


def _satirlar():
    out = []
    for ln in DOC.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("|") or set(ln.replace("|", "").strip()) <= {"-", " "}:
            continue
        h = [c.strip() for c in re.split(r"(?<!\\)\|", ln.strip().strip("|"))]
        if h[0] == "soru":
            assert h == ["soru", "ölçüm", "ne zaman", "karar kuralı (önceden yazıldı)"]
            continue
        out.append(h)
    return out


def test_kayit_ve_belge_birebir():
    satirlar = _satirlar()
    kimlikler = set()
    for soru, olc, zaman, kural in satirlar:
        ids = KIMLIK.findall(olc)
        assert ids, f"satirda olcum kimligi yok: {soru!r}"
        kimlikler |= set(ids)
        assert zaman in ("200", "300", "canlı"), zaman
        assert soru and kural
    assert kimlikler == set(OL.KAYIT)


def test_bakis_belgeyle_ayni():
    zaman = {}
    for _, olc, z, _ in _satirlar():
        for i in KIMLIK.findall(olc):
            zaman.setdefault(i, set()).add("canli" if z == "canlı" else z)
    for ad, o in OL.KAYIT.items():
        assert o.bakis in zaman[ad], ad


def _yon(tmp, ogren=None, view=None):
    y = OL.OlcumYonetici(tmp / "olcum", now_fn=lambda: D0, ml1_cfg={"ogrenme": {}}, view=view, ogren=ogren or sahte_ogren(),
                         maliyet_fn=lambda p, t: SN.Maliyet(), trail_atr_fn=lambda: 2.0)
    assert y.baslat(D0)
    return y


def test_ozet_her_olcumu_icerir(tmp_path):
    y = _yon(tmp_path)
    y.adim(D0)
    oz = json.loads((tmp_path / "olcum" / "ozet.json").read_text())
    assert oz["sema"] == 1 and set(oz["olcumler"]) == set(OL.KAYIT)
    assert {b["durum"] for b in oz["olcumler"].values()} <= {"veri_yok", "ok"}
    assert all(b["soru"] and b["bakis"] for b in oz["olcumler"].values())


def test_olcum_hatasi_motoru_dusurmez(tmp_path, monkeypatch):
    def boom(yon, D):
        raise RuntimeError("patladi")
    monkeypatch.setitem(OL.KAYIT, "eksik_dakika_stop", dataclasses.replace(OL.KAYIT["eksik_dakika_stop"], fn=boom))
    y = _yon(tmp_path)
    y.adim(D0)
    oz = json.loads((tmp_path / "olcum" / "ozet.json").read_text())["olcumler"]
    assert oz["eksik_dakika_stop"]["durum"] == "hata" and oz["eksik_dakika_stop"]["hata"] == "RuntimeError"
    assert oz["golge_gercek"]["durum"] in ("veri_yok", "ok")


def test_ayni_ad_iki_kez_kaydedilemez():
    with pytest.raises(ValueError):
        OL.olcum("eksik_dakika_stop", soru="x", bakis="200", tur="ozet")(lambda y, D: {})


def test_islem_olcumu_bir_kez_yazar(tmp_path):
    view = Gorunum({"BTC/USDT": seri_1dk([100.0] * 30 + [103.0] * 330)})
    isl = islem()
    og = sahte_ogren(isl)
    D = D0 + timedelta(hours=6)
    y = _yon(tmp_path, og, view)

    def satirlar():
        return [json.loads(x) for f in (tmp_path / "olcum").glob("satirlar-*.jsonl") for x in f.read_text().splitlines()
                if json.loads(x)["olcum"] == "golge_gercek"]
    y.adim(D)
    assert len(satirlar()) == 1
    y.adim(D + timedelta(hours=3))
    assert len(satirlar()) == 1
    y2 = _yon(tmp_path, og, view)                                      # yeniden baslatma
    y2.adim(D + timedelta(hours=6))
    assert len(satirlar()) == 1


def test_dagitik_sayac_yok():
    from trader_engine.brokers.paper import PaperBroker
    from trader_engine.engine import _STATUS_COUNTERS
    assert PaperBroker._COUNTER_KEYS if hasattr(PaperBroker, "_COUNTER_KEYS") else True
    from trader_engine.brokers import paper
    assert paper._COUNTER_KEYS == ("mark_fallbacks", "minute_gaps", "funding_missing", "rejects", "duplicates", "anomalies")
    assert _STATUS_COUNTERS == ("callback_errors", "data_gaps", "ledger_errors", "outbox_failed", "unknown_orders", "mark_fallbacks",
                                "minute_gaps", "funding_missing", "exit_data_gap")


def test_cozulemeyen_islem_35_gunde_vazgecilir(tmp_path):
    isl = islem(exit_ts=D0)
    y = _yon(tmp_path, sahte_ogren(isl), Gorunum({"BTC/USDT": seri_1dk([100.0] * 10, start=D0 + timedelta(hours=1))}))   # karar mumu yok

    def golge():
        return [r for r in (json.loads(x) for f in (tmp_path / "olcum").glob("satirlar-*.jsonl") for x in f.read_text().splitlines())
                if r["olcum"] == "golge_gercek"]
    y.adim(D0 + timedelta(days=1))
    assert golge() == []
    y.adim(D0 + timedelta(days=36))
    assert [r.get("durum") for r in golge()] == ["cozulemedi"]
