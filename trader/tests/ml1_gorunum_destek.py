"""ML1 gorunum testleri icin ortak fikstur: puanli/puansiz kararlar, girilen/atlanan adaylar, kapanan/acik islemler (ag yok)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from panel_support import NOW, PARAMS
from trader_core import ledger as L

UTC = timezone.utc
H = timedelta(hours=1)
BUGUN = datetime(2026, 11, 16, 6, 0, tzinfo=UTC)         # NOW = 16.11 21:00 TSI; TSI gunu 15.11 21:00 UTC'de basladi
ESKI = datetime(2026, 11, 12, 6, 0, tzinfo=UTC)          # 7 gun icinde, bugun degil
COK_ESKI = datetime(2026, 11, 1, 6, 0, tzinfo=UTC)       # 7 gunden eski


def kayit(led: L.Ledger, tid: int, *, bar: datetime, tf: str, setup: str, pair: str, skor: float | None = None, esik: float = 0.6,
          grup: str | None = None, final: str = "entered", skip: str | None = None, veto: str | None = None,
          cikis: tuple[bool, str] | None = None, side: str = "long", ogrenme: bool = False) -> int:
    """Tek karar (+ girildiyse islem). cikis=(kazandi_mi, neden) -> kapanan; None -> acik. Donus: karar id'si."""
    ft: dict = {"atr_1h": 20.0, "stop_dist_atr": 2.0, "atr_4h": 40.0, "wick_ratio": 0.5, "rr": 2.5, "edge_dist_atr": 0.1,
          "pullback_ema": 50, "ema_value": 1990.0, "body_ratio": 0.6}
    if skor is not None:
        ft.update({"ml1_skor": skor, "ml1_esik": esik, "ml1_sha": "abc123def456", "ml1_conf_same_tf": 1})
        if grup:
            ft["ml1_grup"] = grup
    if ogrenme:                                          # 26.11: ogrenme asamasi (paket yok): puansiz gecis, ml1_skor YOK
        ft.update({"ml1_neden": "ogrenme", "ml1_conf_same_tf": 1})
        if grup:
            ft["ml1_grup"] = grup
    girildi = final == "entered"
    kw = dict(veto_status="not_evaluated", risk_allowed=True if girildi else None, risk_reason="ok" if girildi else None,
              size_qty=0.3 if girildi else None, size_notional=600.0 if girildi else None, size_margin=200.0 if girildi else None,
              size_risk_amount=13.188 if girildi else None, leverage=3 if girildi else None)
    if final == "skipped" and skip == "risk_denied":
        kw["risk_allowed"] = False
        kw["risk_reason"] = "limit"
    did = led.record_decision(L.DecisionEvent(
        bar_close_ts=bar, trigger_tf=tf, pair=pair, side=side, setup=setup, regime="range", atr_ratio=1.1, rh=2100.0, rl=1980.0,
        rh_touches=2, rl_touches=3, features=ft, planned_entry=2000.0, planned_stop=1960.0, planned_target=None if setup == "T1" else 2100.0,
        param_version_id=1, veto_reason=veto, final_action=final, skip_reason=skip, **kw))
    if girildi:
        led.record_trade_entry(L.TradeEntry(tid, did, bar + timedelta(seconds=3), 2001.0, 0.3, 3, 0.30015))
        if cikis is not None:
            kazandi, neden = cikis
            led.record_trade_exit(L.TradeExit(tid, bar + H, 2079.0 if kazandi else 1960.0, neden,
                                              None if setup == "T1" else 2100.0, 0.3, 0.1))
    return did


def ml1_defter(path, *, esik: float = 0.6, ek=()):
    """Standart ML1 defteri. Bugun: 8 puanli (5 gecen: 3 girildi + 1 ayni olay + 1 risk + 1 diger...) bkz. yorumlar."""
    led = L.open_ledger(path, "learner", clock=lambda: NOW)
    led.init_params(PARAMS, reason="x")
    e = esik
    # --- bugun (TSI): puanlanan 9, gecen 6, islem 4
    kayit(led, 1, bar=BUGUN, tf="4h", setup="T1", pair="BTC/USDT", skor=0.70, esik=e, grup="PULLBACK_1LEG", cikis=(True, "target"))
    kayit(led, 2, bar=BUGUN + H, tf="4h", setup="T1", pair="ETH/USDT", skor=0.65, esik=e, grup="PULLBACK_1LEG", cikis=(False, "stop"))
    kayit(led, 3, bar=BUGUN + 2 * H, tf="1d", setup="TF1", pair="SOL/USDT", skor=0.62, esik=e, grup="TREND_BREAKOUT", cikis=(True, "target"))
    kayit(led, 4, bar=BUGUN + 3 * H, tf="15m", setup="MF1-YUTAN", pair="XRP/USDT", skor=0.61, esik=e, grup="CANDLE_ENGULF", cikis=(False, "stop"))
    kayit(led, 5, bar=BUGUN + 4 * H, tf="1h", setup="R1", pair="ADA/USDT", skor=0.64, esik=e, grup="RANGE_EDGE")            # acik islem
    kayit(led, 0, bar=BUGUN + 5 * H, tf="4h", setup="T1", pair="DOGE/USDT", skor=0.66, esik=e, grup="PULLBACK_1LEG",
          final="skipped", skip="ml_filter", veto="gate:ml1_ayni_olay")
    kayit(led, 0, bar=BUGUN + 6 * H, tf="4h", setup="T1", pair="LTC/USDT", skor=0.67, esik=e, grup="PULLBACK_1LEG",
          final="skipped", skip="risk_denied")
    kayit(led, 0, bar=BUGUN + 7 * H, tf="1h", setup="R1", pair="AVAX/USDT", skor=0.40, esik=e, grup="RANGE_EDGE",
          final="skipped", skip="ml_filter", veto="gate:ml1_esik_alti")
    kayit(led, 0, bar=BUGUN + 8 * H, tf="15m", setup="R1", pair="LINK/USDT", skor=0.30, esik=e, grup="RANGE_EDGE",
          final="skipped", skip="ml_filter", veto="gate:ml1_esik_alti")
    # --- 7 gun icinde ama bugun degil: puanlanan 2, gecen 1, islem 1 (girildi + kapandi)
    kayit(led, 6, bar=ESKI, tf="1h", setup="S1", pair="BNB/USDT", skor=0.63, esik=e, grup="SQUEEZE_BREAK", cikis=(True, "target"))
    kayit(led, 0, bar=ESKI + H, tf="1h", setup="S1", pair="DOT/USDT", skor=0.20, esik=e, grup="SQUEEZE_BREAK",
          final="skipped", skip="ml_filter", veto="gate:ml1_esik_alti")
    # --- 7 gunden eski: ML1 oncesi (puansiz) kapanan islemler; biri kaldirilan kol (M1)
    kayit(led, 7, bar=COK_ESKI, tf="1h", setup="R1", pair="ATOM/USDT", cikis=(True, "target"))
    kayit(led, 8, bar=COK_ESKI + H, tf="1h", setup="R1", pair="NEAR/USDT", cikis=(False, "stop"))
    kayit(led, 9, bar=COK_ESKI + 2 * H, tf="1h", setup="M1", pair="APT/USDT", cikis=(False, "force_exit"))
    for f in ek:
        f(led)
    led.close()


def ogrenme_defteri(path):
    """Yalniz OGRENME asamasi (puansiz): bugun 4 aday, 3 girildi (2 kapandi, 1 acik) + 1 risk reddi; ML1 oncesi 1 eski islem."""
    led = L.open_ledger(path, "learner", clock=lambda: NOW)
    led.init_params(PARAMS, reason="x")
    kayit(led, 1, bar=BUGUN, tf="4h", setup="T1", pair="BTC/USDT", grup="PULLBACK_1LEG", ogrenme=True, cikis=(True, "target"))
    kayit(led, 2, bar=BUGUN + H, tf="1h", setup="R1", pair="ETH/USDT", grup="RANGE_EDGE", ogrenme=True, cikis=(False, "stop"))
    kayit(led, 3, bar=BUGUN + 2 * H, tf="1d", setup="TF1", pair="SOL/USDT", grup="TREND_BREAKOUT", ogrenme=True)               # acik
    kayit(led, 0, bar=BUGUN + 3 * H, tf="4h", setup="T1", pair="LTC/USDT", grup="PULLBACK_1LEG", ogrenme=True, final="skipped", skip="risk_denied")
    kayit(led, 7, bar=COK_ESKI, tf="1h", setup="R1", pair="ATOM/USDT", cikis=(True, "target"))
    led.close()
