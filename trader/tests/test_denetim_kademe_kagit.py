"""24.11 denetim (kullanici karari: risk kademesi kaldirildi, risk ayardan): kagit botunda Telegram /kademe_devam, etkin risk
yedegi (durum blogu yokken kipin ayari), saglikta kagit `review`/`floor` alarmlari."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from test_health_ladder_impl import NOW, api, block, check, expect
from test_telegram_ladder_impl import T0, Rig

from trader_core import telegram as T
from trader_core.health import Status


# ------------------------------------------------------------------------------------------ Telegram
def _paper_rig(tmp_path, risk):
    r = Rig(tmp_path)
    r.write_status()
    d = json.loads(r.status_path.read_text())
    d["mode"] = "paper"
    r.status_path.write_text(json.dumps(d))
    lf = r.d.ladders["learner"]
    r.d.ladders["learner"] = T.LadderFiles(lf.log, lf.status_path, lf.pause, risk)
    return r


def test_kagit_botunda_kademe_devam_iki_adim_calisir(tmp_path):
    r = _paper_rig(tmp_path, 0.01)
    t = r.say("/kademe_devam")
    assert "risk %1,00 (sabit)" in t and "0427" in t
    t = r.say("0427")
    assert r.log.rows()[-1]["kind"] == "review_resume" and not r.pause.active() and "girişler açık" in t


def test_etkin_risk_yedegi_kipin_ayarindan_durum_bayatken(tmp_path):
    r = _paper_rig(tmp_path, 0.005)                       # ayari %1 olmayan bot (orn. testnet %0,5)
    r.write_status(age=121)                               # durum bayat: blok kullanilamaz
    assert "risk %0,50 (sabit)" in r.say("/kademe")
    t = r.say("/kademe_devam")                            # onay metni de ayni etkin riski yazar
    assert t is None or "%1,00" not in t
    r.write_status()
    t = r.say("/kademe_devam")
    assert "risk %0,50 (sabit)" in t and "%1,00" not in t


def test_etkin_risk_durum_blogu_varsa_bloktan(tmp_path):
    r = _paper_rig(tmp_path, 0.005)
    r.write_status(effective_risk=0.0075)
    assert "risk %0,75 (sabit)" in r.say("/kademe")


def test_ayar_yoksa_yedek_canli_baslangic_basamagi(tmp_path):
    r = _paper_rig(tmp_path, None)
    r.write_status(age=121)
    assert "risk %1,00 (sabit)" in r.say("/kademe")


def test_build_ladders_riski_kipin_ayar_dosyasindan_okur(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    try:
        import telegram_run as TR
    finally:
        sys.path.pop(0)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "engine.paper.json").write_text(json.dumps({"risk": {"target_trade_risk": 0.005}}))
    (tmp_path / "config" / "engine.live.json").write_text(json.dumps({"target_trade_risk": 0.01}))
    assert TR._mode_risk(tmp_path, {}, "learner") == 0.005                     # kagit: engine.paper.json
    assert TR._mode_risk(tmp_path, {"LIVE_BOTS": "learner"}, "learner") == 0.01   # canli: engine.live.json
    assert TR._mode_risk(tmp_path / "yok", {}, "learner") is None             # dosya yok: yedek devreye girer
    lad = TR.build_ladders({"LADDER_BOTS": "learner", "ENGINE_VAR_DIR": "var", "PAUSE_FILE": "shared/PAUSE"}, lambda: T0, tmp_path)
    assert lad["learner"].risk == 0.005
    # gercek ayar dosyalari: ikisi de %1
    real = TR.build_ladders({"LADDER_BOTS": "learner"}, lambda: T0, Path(TR.__file__).resolve().parents[1])
    assert real["learner"].risk == 0.01


# ------------------------------------------------------------------------------------------ saglik
def test_saglik_kagitta_review_crit():
    r = expect(api(block(state="review", equity=790.0), mode="paper"), Status.CRIT, "drawdown_review")
    assert "taban 1000.00" in r.detail and "/kademe_devam" in r.detail


def test_saglik_kagitta_floor_crit():
    r = expect(api(block(state="floor", equity=590.0), mode="paper"), Status.CRIT, "capital_floor")
    assert "590.00" in r.detail and "/hepsini_kapat" in r.detail


def test_saglik_kagitta_blok_yoksa_denetim_eklenmez():
    r, _ = check(api(None, "paper"))
    assert r is None
