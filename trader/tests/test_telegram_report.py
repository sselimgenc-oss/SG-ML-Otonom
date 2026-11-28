"""Günlük rapor bölümleri (Defter/Bütçe): salt okunur, her biri bağımsız hata verir."""
import json
import shutil

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trader_core import ledger as L
from trader_core import telegram as T

UTC = timezone.utc
ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)      # 21:00 TR
DAY = "2026-11-16"
PARAMS = {"range_width_atr": 4.0, "vol_ratio_max": 1.5, "edge_zone_atr": 0.25, "pullback_ema": 50,
          "stop_buffer_atr": 0.3, "trail_atr": 3.0, "range_target_frac": 0.75, "rr_min": 1.5, "trigger_tf": "1h"}


def limit_orani():
    """Gercek kagit ayari (config/engine.paper.json risk.daily_max_loss); sabit yazilmaz."""
    return float(json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))["risk"]["daily_max_loss"])


def tr_usd(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def mkcfg(tmp_path, **kw):
    d = dict(ledger_path=str(tmp_path / "l.sqlite"),
             budget_config=str(tmp_path / "config" / "budget.json"))
    d.update(kw)
    return T.TelegramConfig("1:tok", 5, str(tmp_path / "tg"), "", str(tmp_path / "status.json"), **d)


def mkledger(path, bot, trades):
    clk = lambda: NOW  # noqa: E731
    led = L.open_ledger(path, bot, clock=clk)
    led.init_params(PARAMS, reason="x")
    for i, (win, closed) in enumerate(trades, start=1):
        bar = datetime(2026, 11, 16, 6 + i, 0, tzinfo=UTC)
        did = led.record_decision(L.DecisionEvent(
            bar_close_ts=bar, trigger_tf="1h", pair="ETH/USDT", side="long", setup="R1", regime="range",
            atr_ratio=1.1, rh=2100.0, rl=1980.0, rh_touches=2, rl_touches=3,
            features={"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5,
                      "edge_dist_atr": 0.1},
            planned_entry=2000.0, planned_stop=1960.0, planned_target=2100.0, param_version_id=1,
            veto_status="allowed", veto_reason=None, risk_allowed=True, risk_reason="ok", size_qty=0.3,
            size_notional=600.0, size_margin=200.0, size_risk_amount=13.188, leverage=3,
            final_action="entered", skip_reason=None))
        led.record_trade_entry(L.TradeEntry(i, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        if closed:
            px = 2079.0 if win else 1960.0
            led.record_trade_exit(L.TradeExit(i, bar + timedelta(hours=1), px, "target" if win else "stop",
                                              2100.0, 0.3, 0.1))
    led.close()


def write_status(tmp_path):
    (tmp_path / "status.json").write_text(json.dumps({"equity": 1000.0, "day_start_equity": 1000.0}))


def test_ledger_normal_day(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [(True, True), (False, True), (True, False)])
    write_status(tmp_path)
    s = T.section_ledger(mkcfg(tmp_path), DAY)
    assert "kapanan=2" in s and "kazanan/kaybeden=1/1" in s and "açık=1" in s
    assert "equity=1000.00" in s and f"bütçe %{limit_orani() * 100:g}={limit_orani() * 1000:.2f}$" in s and "ikiz" not in s


def test_ledger_no_trades(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [])
    s = T.section_ledger(mkcfg(tmp_path), DAY)
    assert "kapanan=0" in s and "PnL=+0.00$" in s and "açık=0" in s


def test_ledger_missing_reported_in_report(tmp_path):
    cfg = mkcfg(tmp_path)
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert out.count("Bazı bilgiler okunamadı") == 1 and out.rstrip().endswith("Bazı bilgiler okunamadı.")
    for ham in ("defter_yok", "depo_yok", "Defter:", "Ders", "SectionError", "yapilandirma", "_"):
        assert ham not in out
    assert not (tmp_path / "l.sqlite").exists()          # okuma yazı oluşturmaz


def _budget(tmp_path, text=None):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "budget.json").write_text(text if text is not None else
        (ROOT / "config" / "budget.json").read_text().replace("user_data/budget.sqlite", str(tmp_path / "b.sqlite")))


def test_budget_ok_and_corrupt(tmp_path):
    cfg = mkcfg(tmp_path)
    _budget(tmp_path)
    from trader_core import budget as B
    B.BudgetGuard(B.load_config(tmp_path / "config" / "budget.json")).authorize("haftalik_ozet", 0.01)   # deposu başlat
    assert (tmp_path / "b.sqlite").exists()
    s = T.section_budget(cfg)
    # 23.11 kullanici karari: ust lig, LLM tavani 20 $
    assert "/20.00$" in s and "/0.25$" in s
    _budget(tmp_path, "{bozuk")
    with pytest.raises(T.SectionError):                      # teknik satir (panel esdegerlik testi): bozuk yapilandirma kodla bildirilir
        T.section_budget(cfg)
    _budget(tmp_path)
    (tmp_path / "b.sqlite").write_bytes(b"garbage" * 100)
    with pytest.raises(T.SectionError):
        T.section_budget(cfg)
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))       # butce satiri gunluk ozette yok (panelde: Yapay zekâ yorum harcaması)
    assert "garbage" not in out and "bütçe" not in out.lower()


def test_rapor_bolumlerinde_ders_yok(tmp_path):
    cfg = mkcfg(tmp_path)
    assert T.default_sections(cfg, NOW, DAY) == {}                 # silinen bolumler yok: yalniz Duraklatma / Risk kademesi (yapilandirilmissa)
    for ad in ("rapor_defter", "rapor_butce", "rapor_ogrenme", "rapor_kurulum_karnesi", "rapor_kacirilan", "rapor_davranis",
               "section_counterfactual", "kurulumlar_metni", "ATLAMA_TR"):
        assert not hasattr(T, ad), ad
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert len(out) <= 3500 and "ders" not in out.lower() and "karne" not in out.lower() and "alınmayan" not in out.lower()
    mkledger(tmp_path / "l.sqlite", "learner", [(True, True)])
    _status(tmp_path)
    for metin in (T.build_report(cfg, NOW, DAY, {"Duraklatma": lambda: "x"}), T.haftalik_metni(cfg, NOW), T.ml1_metni(cfg, NOW)):
        assert "ders" not in metin.lower() and "M1 " not in metin.replace("ML1 ", "")

def _status(tmp_path, now=NOW, **kw):
    d = {"mode": "paper", "kill": False, "kill_state": "flat", "entries_open": True, "equity": 1000.0,
         "day_start_equity": 1000.0, "loop_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "param_version_id": 1,
         "open_positions": [], "gate": {"ok": True, "code": "ok"},
         "counters": {"mark_fallbacks": 11, "steps": 326, "decisions": 5, "skip:veto_missing": 1, "skip:stop_width": 1,
                      "skip:bilinmeyen_kod": 4, "ignore:no_signal": 300}}
    d.update(kw)
    (tmp_path / "status.json").write_text(json.dumps(d))


def _paper_cfg(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [])
    (tmp_path / "tg").mkdir(exist_ok=True)
    return mkcfg(tmp_path)


def test_report_paper_is_plain_turkish(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    lines = out.splitlines()
    assert lines[0] == "[ML] 🌙 Günlük özet · 16 Kasım"
    for want in ("Bugün kapanan işlem yok.", "Kasa 1.000,00 $ · toplam 0,00 $", "Açık işlem yok.", "ML1 öğrenme aşamasında: 0/200 kapanan işlem; puanlama başlamadı",
                 f"Günlük zarar sınırı: 0 $ / {limit_orani() * 1000:.0f} $", "Yeni işlemler açık."):
        assert want in out, want
    assert "Dersler:" not in out and len(lines) <= 10
    for ham in ("{", "Sayaclar", "PermissionError", "depo_yok", "Spool", "bilgiler okunamadı", "bilinmeyen_kod",
                "veto_missing", "kip=", "Bütçe", "Öğrenme", "━", "gün başı", "kullanıldı"):
        assert ham not in out, ham


def test_report_open_positions_and_closed_summary(tmp_path):
    mkledger(tmp_path / "l.sqlite", "learner", [(True, True), (False, True)])
    (tmp_path / "tg").mkdir(exist_ok=True)
    cfg = mkcfg(tmp_path)
    pos = [{"pair": f"P{i}/USDT", "side": "long" if i % 2 else "short", "entry_price": 2000.0 + i, "stop": 1960.0}
           for i in range(8)]
    _status(tmp_path, open_positions=pos)
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert "Açık: 8 işlem" in out and "P0" not in out                      # coin listesi yok: tek satir sayi (+ anlik K/Z varsa)
    assert "Bugün 2 işlem kapandı (1 kâr, 1 zarar)" in out and "USDT" not in out
    assert len(out.splitlines()) <= 10
    _status(tmp_path, open_positions=pos, unrealized_pnl_usd=3.38)
    assert "Açık: 8 işlem · anlık +3,38 $" in T.build_report(cfg, NOW, DAY, {})


def test_report_risk_closed_lines(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path, entries_open=False, entries_blocked_reason="clock_skew")
    out = T.build_report(cfg, NOW, DAY, T.default_sections(cfg, NOW, DAY))
    assert "Yeni işlemler kapalı." in out and "Yeni işlemler açık" not in out and "clock_skew" not in out
    _status(tmp_path, kill=True, entries_open=False)
    assert "Acil durdurma açık" in T.build_report(cfg, NOW, DAY, {})
    _status(tmp_path, entries_open=False, equity=1000.0 - 1.1 * limit_orani() * 1000.0)
    assert "Günlük zarar sınırı doldu: bugün yeni işlem açılmaz." in T.build_report(cfg, NOW, DAY, {})
    _status(tmp_path, entries_open=False, gate={"ok": False, "code": "paused"})
    out = T.build_report(cfg, NOW, DAY, {"Duraklatma": lambda: "ana bot: yeni işlemler duraklatıldı — elle durduruldu"})
    assert "Yeni işlemler duraklatıldı: elle durduruldu." in out and "ana bot" not in out and "/devam" not in out     # V-06: ilk neden, ham kod yok
    _status(tmp_path, entries_open=False, gate={"ok": False, "code": "paused"})
    out = T.build_report(cfg, NOW, DAY, {"Duraklatma": lambda: "ana bot: yeni işlemler duraklatıldı — Ana para kilidi (kasa ana paranın %15 altına indi) (motor tarafından, 16.11 10:00)"})
    assert "Yeni işlemler duraklatıldı: ana para kilidi (kasa ana paranın %15 altına indi). Açmak için /devam yaz." in out
    assert "capital_latch" not in out and "motor tarafından" not in out
    out = T.build_report(cfg, NOW, DAY, {"Duraklatma": lambda: "ana bot: yeni işlemler duraklatıldı — senin /durdur komutun; borsa geçici engel koydu (Telegram'dan, 16.11 10:00)"})
    assert "Yeni işlemler duraklatıldı: senin /durdur komutun. Açmak için /devam yaz." in out and "borsa" not in out
    out = T.build_report(cfg, NOW, DAY, {"Duraklatma": lambda: "ana bot: yeni işlemler duraklatıldı — risk kademesi incelemesi bekliyor (motor tarafından, 16.11 10:00)"})
    assert "Yeni işlemler duraklatıldı: risk kademesi incelemesi bekliyor." in out and "/devam" not in out


def test_report_heartbeat_missing_first_line(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path, now=NOW - timedelta(minutes=7))
    out = T.build_report(cfg, NOW, DAY, {})
    assert out.splitlines()[0] == "[ML] 🔴 Bot yanıt vermiyor (son sinyal 7 dk önce)"
    assert out.splitlines()[1] == "Günlük özet · 16 Kasım"                  # tek emoji: ozet basligi emojisiz
    assert "Yeni işlemler açık" not in out


def test_report_health_line_only_when_not_ok(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)
    hs = tmp_path / "health.json"
    cfg = mkcfg(tmp_path, health_state=str(hs))
    hs.write_text(json.dumps({"last_overall": "OK"}))
    assert "sistem kontrolü" not in T.build_report(cfg, NOW, DAY, {})
    hs.write_text(json.dumps({"last_overall": "CRIT"}))
    r = T.build_report(cfg, NOW, DAY, {})
    assert "Dikkat: bir sistem kontrolü sorunlu; panoya bak." in r and r.count("⚠") == 0           # tek emoji ilk satirda: 🌙
    hs.write_text("{bozuk")
    out = T.build_report(cfg, NOW, DAY, {})
    assert "sistem kontrolü" not in out and "JSONDecodeError" not in out and "bilgiler okunamadı" not in out


def test_report_ignores_failing_sections(tmp_path):
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)

    def boom():
        raise PermissionError("secret path")
    out = T.build_report(cfg, NOW, DAY, {"A": boom, "B": boom, "C": boom})
    assert "PermissionError" not in out and "secret" not in out and "bilgiler okunamadı" not in out


def test_report_sifir_kz_islem_zarar_sayilmaz(tmp_path, monkeypatch):
    """A-13: K/Z tam sifir olan islem 'zarar' degil 'basa bas'; basa bas yoksa o ek hic yazilmaz."""
    from types import SimpleNamespace as NS
    cfg = _paper_cfg(tmp_path)
    _status(tmp_path)
    trades = [NS(realized_pnl=4.0, r_multiple=1.0), NS(realized_pnl=-1.5, r_multiple=-1.0), NS(realized_pnl=0.0, r_multiple=0.0)]
    monkeypatch.setattr(T, "_ledger_day", lambda path, bot, day: (trades, []))
    assert "Bugün 3 işlem kapandı (1 kâr, 1 zarar, 1 başa baş) · +2,50 $" in T.build_report(cfg, NOW, DAY, {})
    monkeypatch.setattr(T, "_ledger_day", lambda path, bot, day: (trades[:2], []))
    assert "Bugün 2 işlem kapandı (1 kâr, 1 zarar) · +2,50 $" in T.build_report(cfg, NOW, DAY, {})
