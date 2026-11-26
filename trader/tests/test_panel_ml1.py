"""Pano ML1 sekmesi, tek TOPLAM K/Z, arms_off.json'a bagimsizlik, yasak soz taramasi (ML1 donemi sadelesmesi)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ml1_gorunum_destek import ml1_defter
from panel_support import NOW, ROOT, Env
from trader_core import panel_pano as PP
from trader_panel import server as SRV
from trader_panel import snapshot as SNAP
from trader_panel.data import PanelData, load_config

STATIC = ROOT / "src/trader_panel/static"


@pytest.fixture()
def ml1_env(tmp_path):
    """Env (bos) + ML1 defteri + canli durum + ayar dosyalari (ml1.aktif, max_positions)."""
    e = Env(tmp_path, learner=False)
    ml1_defter(str(tmp_path / "var/learner/ledger.sqlite"))
    (tmp_path / "config/engine.paper.json").write_text(json.dumps({"ml1": {"aktif": True}, "max_positions": 36}))
    e.write_status("learner", 5, equity=1010.0, day_start_equity=1000.0, unrealized_pnl_usd=3.0,
                   open_positions=[{"trade_id": 5, "pair": "ADA/USDT", "side": "long", "qty": 0.3, "entry_price": 2001.0, "stop": 1960.0,
                                    "mark": 2011.0, "unrealized_pnl_usd": 3.0, "unrealized_pct": 0.5}])
    yield e
    e.close()


def _pano(e):
    return PanelData(load_config(e.cfg_path), clock=lambda: NOW).pano("learner")


def test_pano_govdesinde_ml1_ve_ogrenme_yok(ml1_env):
    p = _pano(ml1_env)
    assert p["ok"] and "ogrenme" not in p
    m = p["ml1"]
    assert m["durum"] == {"metin": "Açık: adayları ML1 seçiyor", "renk": "yesil"} and m["esik"] == 0.6
    assert [r["kod"] for r in m["zd"]] == ["1h", "4h", "1d"] and "sinav" not in m and "zd_ozet" not in m
    assert m["durum_satiri"].startswith("ML1 ") and m["tf_satiri"].startswith("Kapanan işlem: 1s ")
    assert {"eleme", "ogr", "gruplar", "toplam", "eski"} <= set(m)
    assert m["eleme"]["bugun"]["puanlanan"] == 9 and m["gruplar"]["tumu"][-1]["grup"] == "Kaldırılan kollar (eski)"


def test_ml1_kapaliysa_gri_rozet(tmp_path):
    e = Env(tmp_path, learner=False)
    try:
        ml1_defter(str(tmp_path / "var/learner/ledger.sqlite"))
        e.write_status("learner", 5)
        p = _pano(e)                                          # engine.paper.json yok -> ml1.aktif yok
    finally:
        e.close()
    assert p["ml1"]["durum"]["renk"] == "gri" and p["ml1"]["durum"]["metin"].startswith("Kapalı")


def test_arms_off_dosyasi_olsa_da_olmasa_da_cikti_ayni(ml1_env):
    onceki = json.dumps(_pano(ml1_env), sort_keys=True)
    (ml1_env.root / "var/learner/arms_off.json").write_text(
        json.dumps({"arms": {"T1@4h": {"state": "closed"}, "R1@1h": {"state": "closed"}}}), encoding="utf-8")
    assert json.dumps(_pano(ml1_env), sort_keys=True) == onceki


def test_toplam_kz_tek_kaynak_canli(ml1_env):
    p = _pano(ml1_env)
    t = p["kz"]["toplam"]
    assert t["kaynak"] == "kasa" and p["serit"]["toplam"] == t["toplam"] == pytest.approx(1010.0 - 1000.0)
    assert t["kapanan"] + t["acik"] + t["fark"] == pytest.approx(t["toplam"], abs=1e-9)
    assert p["serit"]["toplam_kaynak"] == "kasa" and "tumu" not in p["kz"]["donemler"]


def test_toplam_kz_durum_bayatsa_kapanan_toplami(ml1_env):
    ml1_env.write_status("learner", 3600, equity=1010.0, unrealized_pnl_usd=3.0)
    p = _pano(ml1_env)
    t = p["kz"]["toplam"]
    assert t["kaynak"] == "kapanan" and t["toplam"] == t["kapanan"] == p["serit"]["toplam"] and t["acik"] is None and t["fark"] is None


def test_risk_limitleri_bes_satir_adet_ayardan(ml1_env):
    p = _pano(ml1_env)
    lim = p["teknik"]["limitler"]
    assert [r["ad"] for r in lim] == ["Toplam açık risk", "Long açık risk", "Short açık risk", "Günlük zarar", "Açık pozisyon sayısı"]
    assert lim[-1]["birim"] == "adet" and lim[-1]["limit"] == 36 and lim[-1]["kullanilan"] == 1 and all(r["birim"] == "$" for r in lim[:4])
    (ml1_env.root / "config/engine.paper.json").write_text(json.dumps({"ml1": {"aktif": True}, "max_positions": 12}))
    assert _pano(ml1_env)["teknik"]["limitler"][-1]["limit"] == 12        # sabit sayi yok: ayardan
    (ml1_env.root / "config/engine.paper.json").write_text(json.dumps({"ml1": {"aktif": True}}))
    assert len(_pano(ml1_env)["teknik"]["limitler"]) == 4                  # okunamazsa satir eklenmez


def test_kirmizi_ml1_isiga_nedeni_ekler(ml1_env):
    from datetime import timedelta
    from ml1_gorunum_destek import BUGUN, kayit
    from trader_core import ledger as L
    led = L.open_ledger(str(ml1_env.root / "var/learner/ledger.sqlite"), "learner", clock=lambda: NOW)
    kayit(led, 0, bar=BUGUN + timedelta(hours=9), tf="4h", setup="T1", pair="TRX/USDT", skor=None, final="skipped",
          skip="ml_no_model", veto="gate:ml1_paket_yok")
    led.close()
    p = _pano(ml1_env)
    assert p["ml1"]["durum"]["renk"] == "kirmizi" and "ML1 modeli yüklenemedi" in p["isik"]["metin"] and p["isik"]["renk"] == "kirmizi"


def test_ogrenme_uc_noktasi_yok(ml1_env):
    api = SRV.build_api(PanelData(load_config(ml1_env.cfg_path), clock=lambda: NOW))
    assert "/api/learning" not in api and "/api/pano" in api
    assert not any("learning" in p for p in SNAP._paths())
    assert not hasattr(PanelData, "learning")


def test_pano_dosyalarinda_yasak_sozcuk_yok():
    yasak = ("Ders", "ders", "arms_off", "Karantina", "karantina", "Kademeli küçültme", "M1", "DL1", "HB1", "ogrenme")
    for p in (STATIC / "panel.js", STATIC / "index.html", STATIC / "panel.css", ROOT / "src/trader_core/panel_pano.py"):
        t = p.read_text(encoding="utf-8")
        for w in yasak:
            assert w not in t, (p.name, w)


def test_arayuz_sekmeler_ml1_ve_eski_kartlar_yok():
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    assert "['ml1', 'ML1']" in js and "'ÖĞRENME'" not in js and "Ders kapattı" not in js and "Açık kol" not in js
    ozet = js.split("function tabOzet")[1].split("function isikKart")[0]
    assert "ml1OzetKart" in ozet and "ogrenmeOzetKart" not in js
    for s in ("Aday eleme", "Fikir grubuna göre", "ML1 işlemleri", "Tüm işlemler", "Toplam K/Z nasıl oluşuyor?",
              "Kapanan K/Z", "Bugün kapanan K/Z", "Yapay zekâ yorum harcaması"):
        assert s in js, s
    assert "Kaynağa göre K/Z" not in js and "Model ayrıntısı" not in js
    for s in ("sınavı geçti", "Sınav sonucu", "Sınavı geçen", "kanitli", "kanitsiz", "zd_ozet", "15 dakika", "15dk"):
        assert s not in js, s
    assert "m.durum_satiri" in js and "m.tf_satiri" in js
    assert "sek-ml1" in (STATIC / "index.html").read_text(encoding="utf-8")


def test_kapanan_satirinda_dogru_etiket_ve_ml1_alanlari(ml1_env):
    d = PanelData(load_config(ml1_env.cfg_path), clock=lambda: NOW)
    rows = {r["id"]: r for r in d.kapanan("learner", "tumu")["rows"]}
    assert rows[9]["neden"] == "Kol kaldırıldı" and "kaldırıldı" in rows[9]["neden_aciklama"]      # M1 + force_exit
    assert rows[1]["neden"] == "Kâr al" and rows[1]["ml1_puan"] == pytest.approx(0.70) and rows[1]["zd"] == "4 saat"
    assert rows[2]["neden"] == "Stop" and rows[7]["ml1_puan"] is None
    assert not any(r["neden"] == "Elle" for r in rows.values())
