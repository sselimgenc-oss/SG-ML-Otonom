"""DD-12 WP-17 uygulayici duman testleri: ogrenme gorunumu (kurulum karnesi, ders, ML, seans/varlik kirilimi, acik
pozisyon, haftalik ozet, harcama), Telegram bolumleri ve /kurulumlar, /ders komutlari, pano uc noktasi ve sekme."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import counterfactual as CF
from trader_core import panel_data as PD
from trader_core import telegram as T
from trader_panel import data as PDATA
from trader_panel import server as SRV

UTC = timezone.utc
NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "trader_panel" / "static"


# ---- sahte defter ------------------------------------------------------------------------------------------------
def _dec(i, *, arm, pair="BTC/USDT", final="skipped", skip=None, session="open", ml=None, tf="1h", setup=None):
    return SimpleNamespace(id=i, pair=pair, setup=setup or arm.split("@")[0], trigger_tf=tf, arm_id=arm,
                           bar_close_ts=datetime(2026, 11, 18, 10, tzinfo=UTC), final_action=final, skip_reason=skip,
                           session_tag=session, ml_score=ml)


class FakeLedger:
    def __init__(self, decisions, trades=(), open_trades=(), acts=()):
        self._d, self._t, self._o, self._a = list(decisions), list(trades), list(open_trades), list(acts)

    def list_decisions(self, **kw):
        return self._d

    def list_closed_trades(self, **kw):
        return self._t

    def list_open_trades(self):
        return self._o

    def list_activations(self, limit=None):
        return self._a if limit is None else self._a[:limit]

    def get_active_params(self):                      # brake_active yalniz list_activations kullanir
        raise AssertionError("kullanilmamali")

    def close(self):
        pass


def _act(kind, actor, reason, at=NOW):
    return SimpleNamespace(kind=kind, actor=actor, reason=reason, activated_at=at, version_id=1, prev_version_id=None,
                           bot="learner", id=1, proposal_id=None)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Kurulum karnesi, ders, ML, seans ve acik pozisyon senaryosu; yollar tmp, defter sahte."""
    led_path = tmp_path / "var" / "ledger.sqlite"
    led_path.parent.mkdir(parents=True)
    led_path.write_bytes(b"")                         # varlik kontrolu icin; okuma sahte defterden
    (led_path.parent / "counterfactual.sqlite").write_bytes(b"")
    (led_path.parent / "arms_off.json").write_text(json.dumps(
        {"schema": 1, "arms": {"M1@1h": {"state": "closed", "n": 3, "mean_r": -0.4}}}), encoding="utf-8")
    wk = led_path.parent / "weekly_summaries"
    wk.mkdir()
    (wk / "2026-W46.md").write_text("# eski\neski ozet\n", encoding="utf-8")
    (wk / "2026-W47.md").write_text("# Haftalik ozet\nBu hafta iki kurulum calisti.\n", encoding="utf-8")
    paper = tmp_path / "engine.paper.json"
    paper.write_text(json.dumps({"arms": ["T1@1h", "M1@1h", "F1@1h"],
                                 "clusters": {"kripto_buyuk": {"pairs": ["BTC/USDT", "ETH/USDT"]},
                                              "hisse": {"pairs": ["NVDA/USDT"]},
                                              "metal": {"pairs": ["XAU/USDT"]}}}), encoding="utf-8")
    decisions = [
        _dec(1, arm="T1@1h", final="entered", session="open"),                           # alindi, kazanc
        _dec(2, arm="T1@1h", pair="NVDA/USDT", skip="ml_filter", session="closed", ml=0.2),  # ML eledi
        _dec(3, arm="M1@1h", pair="XAU/USDT", final="entered", session="open", ml=0.8, setup="M1"),
        _dec(4, arm="T1@1h", skip="stop_width", session="open"),                          # alinmadi
        _dec(5, arm="M1@1h", pair="ETH/USDT", final="entered", session="open", setup="M1"),  # acik
    ]
    trades = [SimpleNamespace(decision_id=1, r_multiple=1.0), SimpleNamespace(decision_id=3, r_multiple=-0.5)]
    open_trades = [SimpleNamespace(decision_id=5, pair="ETH/USDT")]
    acts = [_act("rollback", "lesson", "lesson_brake: referans sürüme dönüldü"), _act("apply", "lesson", "ders")]
    fake = FakeLedger(decisions, trades, open_trades, acts)
    monkeypatch.setattr(PD, "open_ledger_ro", lambda path, bot: fake)
    cf_rows = [{"decision_id": 2, "hyp_r_net": -1.0}, {"decision_id": 4, "hyp_r_net": 0.5}]
    monkeypatch.setattr(CF, "arm_rows", lambda path, bot, **kw: cf_rows)
    monkeypatch.setattr(PD, "PAPER_CONFIG", paper)
    return SimpleNamespace(ledger=str(led_path), budget=str(tmp_path / "config" / "budget.json"), tmp=tmp_path)


# ---- zaman damgasi (motor ve pano ms'li yazar) ------------------------------------------------------------------
def test_parse_ts_z_accepts_fractional_utc_and_rejects_naive_or_offset():
    assert T.parse_ts_z("2026-12-01T10:00:00Z") == datetime(2026, 12, 1, 10, tzinfo=UTC)
    assert T.parse_ts_z("2026-12-01T10:00:00.000Z") == datetime(2026, 12, 1, 10, tzinfo=UTC)
    assert T.parse_ts_z("2026-12-01T10:00:00.250Z").microsecond == 250_000
    for bad in ("2026-12-01T10:00:00", "2026-12-01T10:00:00+03:00", "2026-12-01T10:00:00.000+00:00", None):
        with pytest.raises(ValueError):
            T.parse_ts_z(bad)


# ---- ogrenme gorunumu -------------------------------------------------------------------------------------------
def test_learning_view_scorecard_lesson_m1_sessions_open(world):
    lv = PD.learning_view(world.ledger, world.budget, NOW)
    arms = {r["arm"]: r for r in lv["scorecard"]}
    t1, m1, f1 = arms["T1@1h"], arms["M1@1h"], arms["F1@1h"]
    assert (t1["candidates"], t1["taken"], t1["mean_r_taken"]) == (3, 1, 1.0)
    assert t1["mean_r_taken_cf"] == pytest.approx((1.0 - 1.0 + 0.5) / 3)     # alinan + alinmayan (alinsaydi)
    assert (m1["candidates"], m1["taken"], m1["mean_r_taken"], m1["state"]) == (2, 2, -0.5, "closed")
    assert (f1["candidates"], f1["state"]) == (0, "open")                     # yapilandirilmis, adayi yok
    assert lv["lesson"]["applied"] == 1 and lv["lesson"]["rollbacks"] == 0
    assert lv["lesson"]["brake_active"] is True and lv["lesson"]["brake_events"] == 1
    assert lv["lesson"]["closed_arms"] == ["M1@1h"]
    assert "ml" not in lv                                                      # 24.11: ML filtre sayilari (elenen/gecen/etki) silindi
    assert (lv["m1"]["candidates"], lv["m1"]["taken"]) == (2, 2)
    assert lv["sessions"]["open"]["kripto"]["taken"] == 2
    assert lv["sessions"]["open"]["emtia"]["mean_r_taken"] == -0.5
    assert lv["sessions"]["closed"]["hisse"]["taken"] == 0
    assert lv["open"] == {"total": 1, "by_arm": {"M1@1h": 1}, "by_cluster": {"kripto_buyuk": 1}}
    assert lv["weekly_summary"]["week"] == "2026-W47"
    assert "Bu hafta iki kurulum" in lv["weekly_summary"]["text"]
    assert lv["budget"]["code"]                                                 # yapilandirma yok: kod, cokme yok


def test_learning_view_missing_ledger_keeps_budget_and_weekly(tmp_path):
    lv = PD.learning_view(str(tmp_path / "yok.sqlite"), "", NOW)           # defter yok: bolum kodu, cokme yok
    assert lv["ledger_error"] == "defter_yok" and lv["scorecard"] == []
    assert lv["weekly_summary"] is None and lv["budget"] == {"code": "yapilandirma_yok"}


# ---- Telegram: bolumler ve komutlar -----------------------------------------------------------------------------
def _cfg(world):
    return T.TelegramConfig(token="1:tok", chat_id=7, var_dir=str(world.tmp / "tg"),
                            status_path=str(world.tmp / "status.json"), ledger_path=world.ledger,
                            budget_config=world.budget)


def test_daily_sections_show_learning_and_scorecard(world):
    cfg = _cfg(world)
    ogr = T.rapor_ogrenme(cfg, NOW)
    assert "Ders: uygulanan 1 · geri alınan 0 · −10 R freni AKTİF" in ogr
    assert "elenen" not in ogr and "M1: aday 2, giriş 2" in ogr
    assert "Haftalık özet (2026-W47)" in ogr
    karne = T.rapor_kurulum_karnesi(cfg, NOW)
    assert "T1@1h: aday 3 · alınan 1" in karne and "M1@1h: aday 2 · alınan 2" in karne and "KAPALI" in karne
    assert "F1@1h" not in karne                                                 # adayi olmayan kurulum satiri yok
    out = T.build_report(cfg, NOW, "2026-11-19", {"Öğrenme": lambda: ogr, "Kurulum karnesi": lambda: karne})
    assert "📚" not in out and "🧪" not in out and len(out.splitlines()) <= 12     # gunluk ozet kisa; bolumler komutlarda
    assert ogr.index("📚 Ders") < ogr.index("Haftalık özet")
    for banned in ("ikiz", "twin", "veto"):
        assert banned not in (ogr + karne).lower()


def test_kurulumlar_and_ders_commands_reply_through_dispatch(world):
    cfg = _cfg(world)
    sent: list[str] = []

    class Client:
        def send_message(self, chat_id, text, disable_notification=False):
            sent.append(text)
            return {"ok": True}

    d = T.TelegramDaemon(cfg, Client(), now_fn=lambda: NOW, runner=lambda *a: (0, "{}"), sleep=lambda s: None)
    assert "/kurulumlar" in T.HELP and "/ders" in T.HELP
    assert d._dispatch_text("/kurulumlar", "x") == "ok"
    assert sent[-1].startswith("🧪 Kurulum karnesi") and "T1@1h: aday 3" in sent[-1]
    assert d._dispatch_text("/ders", "x") == "ok"
    assert "Uygulanan değişiklik: 1" in sent[-1] and "AKTİF" in sent[-1]
    assert "M1@1h" in sent[-1]                                                  # kapali kurulum
    assert "/rapor" in T.HELP


def test_commands_report_unreadable_data_in_one_line(tmp_path):
    cfg = T.TelegramConfig(token="1:tok", chat_id=7, var_dir=str(tmp_path / "tg"), ledger_path="")
    sent: list[str] = []

    class Client:
        def send_message(self, chat_id, text, disable_notification=False):
            sent.append(text)
            return {"ok": True}

    d = T.TelegramDaemon(cfg, Client(), now_fn=lambda: NOW, runner=lambda *a: (0, "{}"), sleep=lambda s: None)
    assert d._dispatch_text("/kurulumlar", "x") == "unreadable"
    assert sent == ["okunamadı: defter_yok"]                                     # komutta kod; günlük raporda yok


def test_veto_labels_remain_for_historical_reasons_only():
    assert T.ATLAMA_TR["veto_missing"] == "veto hazır değildi"                  # eski defter satirlari icin ceviri


# ---- pano: uc nokta, sekme, statik dosyalar ----------------------------------------------------------------------
def test_panel_endpoint_and_tab(world, tmp_path):
    cfg = PDATA.PanelConfig({"ledger_path": world.ledger, "budget_config": world.budget,
                             "status_path": str(tmp_path / "status.json")}, tmp_path)
    data = PDATA.PanelData(cfg, clock=lambda: NOW)
    v = data.learning()
    assert v["ok"] is True and v["scorecard"] and v["lesson"]["brake_active"] is True
    assert "/api/learning" in SRV.build_api(data)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    # 20.11 yeni pano (6 sekme): ders + ML ogrenme sekmesinde, saglik teknik sekmesinde; veri /api/pano'dan
    assert 'id="sek-ogrenme"' in html and 'id="sek-teknik"' in html
    js = (STATIC / "panel.js").read_text(encoding="utf-8")
    assert "['ogrenme', 'ÖĞRENME']" in js and "/api/pano" in js
    assert ".innerHTML" not in js and "insertAdjacentHTML" not in js           # yalniz textContent ile basilir
