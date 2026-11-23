"""Pano (panel) gorunum verisi: yalniz GOSTERIM, salt okunur. Risk/motor hesabina dokunmaz.

Panelin yeni yapisi (OZET, ACIK, KAPANAN, K/Z, OGRENME, TEKNIK) icin sade Turkce, zaten bicimlenmis alanlar uretir:
kol adi `tg_sade.kol_adi` (Telegram ile ayni), coin "SOL", yon long/short, saatler TSI, ham kod yok.
Gunluk zarar siniri tek kaynaktan: `panel_data.daily_loss_rate()` (sabit sayi yok).
Olculemeyen sayi uydurulmaz: {"olculemedi": "Henüz ölçülemedi (N işlem, en az M gerek)"}; bos kart hic uretilmez (None).
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import ledger as L
from . import panel_data as P
from . import tg_sade as TS

TR = P.TR
MIN_ORAN = 5            # kazanma orani / ort. kazanc-kayip icin asgari kapanan islem
MIN_ETKI = 10           # ders / ML katkisi icin asgari sonuclu karar
MIN_ISABET = 10         # ML isabeti icin asgari sonuclu tahmin

REJIM_TR = {"range": "yatay piyasa", "trend": "trend", "trending": "trend", "ranging": "yatay piyasa"}
# giris kapisi / duraklatma kodu -> kisa sade neden (ham kod gosterilmez)
NEDEN_KISA = {
    "user_cmd": "elle durdurdun", "manual": "elle durduruldu", "kill": "acil durdurma", "paused": "duraklatıldı",
    "drawdown_review": "risk incelemesi bekliyor", "capital_floor": "sermaye tabanı", "capital_latch": "ana para kilidi", "capital_missing": "sermaye kaydı yok",
    "ladder_invalid": "risk kaydı bozuk", "unknown_position": "tanınmayan pozisyon", "late_fill": "geç gelen emir",
    "exchange_ban": "borsa engeli", "exchange_auth": "borsa erişimi sorunlu", "exchange_unreachable": "borsaya ulaşılamıyor",
    "exchange_rate_limited": "borsa istek sınırı", "stale_data": "piyasa verisi eski", "day_start_missing": "gün başı bakiyesi yok",
    "clock_skew": "saat kayması", "order_unknown": "belirsiz emir", "exit_unknown": "belirsiz kapanış",
    "reconcile": "borsayla kayıtlar uyuşmuyor", "degraded": "kayıt sorunu", "equity_unreadable": "bakiye okunamadı",
    "ml_expired": "model süresi doldu", "ml_no_model": "model yok", "daily_loss": "günlük zarar limiti doldu",
    "korelasyon_grubu": "aynı yön grubu dolu", "toplam_buyukluk": "toplam büyüklük tavanı", "kayip_freni": "kayıp freni (yarım risk)",
}
GENEL_NEDEN = "güvenlik kuralı devrede"
SAGLIK_TR = {"OK": "Sağlam", "WARN": "Dikkat", "CRIT": "Sorun var", "UNKNOWN": "Bilinmiyor", "SKIPPED": "Atlandı"}


# ----------------------------------------------------------------------------- bicim yardimcilari (veri katmani)
def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def tr_sayi(x: float, nd: int = 2) -> str:
    """1428.4 -> '1.428,40' (Turkce bicim; isaret yok)."""
    return f"{abs(float(x)):,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tsi_kisa(dt: datetime | None) -> str:
    """'19.11 21:05' (TSI, yil yok, UTC yok)."""
    return "—" if dt is None else dt.astimezone(TR).strftime("%d.%m %H:%M")


def tsi_gun(dt: datetime | None) -> str:
    return "—" if dt is None else dt.astimezone(TR).strftime("%d.%m")


def sure_metni(a: datetime | None, b: datetime | None) -> str:
    if a is None or b is None:
        return "—"
    m = max(int((b - a).total_seconds() // 60), 0)
    if m < 60:
        return f"{m} dk"
    if m < 1440:
        return f"{m // 60}s {m % 60}dk" if m % 60 else f"{m // 60}s"
    return f"{m // 1440}g {(m % 1440) // 60}s"


def neden_sade(kod: Any) -> str:
    k = str(kod or "")
    if k.startswith("ml_"):
        return NEDEN_KISA.get(k, "yapay zekâ filtresi hazır değil")
    return NEDEN_KISA.get(k, GENEL_NEDEN)


def olculemedi(n: int, en_az: int, birim: str = "işlem") -> dict:
    return {"olculemedi": f"Henüz ölçülemedi ({n} {birim}, en az {en_az} gerek)"}


def gun_basi(now: datetime, geri: int = 0) -> datetime:
    """TSI gunu baslangici (UTC olarak), `geri` gun oncesi. Yalniz gosterim araligi."""
    d0 = now.astimezone(TR).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=geri)
    return d0.astimezone(P.UTC)


PERIODS = ("bugun", "7g", "30g", "tumu")


def period_bounds(period: str, now: datetime) -> tuple[datetime | None, datetime | None]:
    if period == "bugun":
        return gun_basi(now), gun_basi(now, -1)
    if period == "7g":
        return gun_basi(now, 6), None
    if period == "30g":
        return gun_basi(now, 29), None
    return None, None


# ----------------------------------------------------------------------------- defter baglami
class Ctx:
    """Tek defter okumasi: kapanan/acik islemler, kararlar, kol eslemesi."""

    def __init__(self, path: str, bot: str = "learner"):
        led = P.open_ledger_ro(path, bot)
        try:
            self.closed: list[L.TradeRecord] = led.list_closed_trades(None, None, P.CLOSED_MAX)
            self.open: list[L.TradeRecord] = led.list_open_trades()
            self.decisions: list[L.DecisionRecord] = led.list_decisions()
        except P.SectionError:
            raise
        except Exception as e:  # noqa: BLE001
            raise P.SectionError(type(e).__name__) from None
        finally:
            led.close()
        self.dec = {d.id: d for d in self.decisions}

    def kol(self, t: L.TradeRecord) -> str:
        d = self.dec.get(t.decision_id)
        if d is not None:
            return TS.kol_adi(getattr(d, "arm_id", None) or d.setup, d.trigger_tf)
        return TS.kol_adi(t.setup)


def _px(x: Any) -> float | None:
    v = _f(x)
    return v


def closed_row(t: L.TradeRecord, ctx: Ctx) -> dict:
    d = ctx.dec.get(t.decision_id)
    notional = (t.entry_price or 0) * (t.qty or 0)
    pnl = t.realized_pnl or 0.0
    return {"id": t.trade_id, "coin": TS.coin(t.pair), "yon": TS.yon(t.side), "kol": ctx.kol(t),
            "kapanis": tsi_kisa(t.exit_ts), "acilis": tsi_kisa(t.entry_ts),
            "kz": pnl, "kz_yuzde": (pnl / notional * 100.0) if notional else None,
            "neden": (lambda x: {"i": "İ"}.get(x[:1], x[:1].upper()) + x[1:])(TS.kapanis_neden(t.exit_reason, pnl)),
            "giris": _px(t.entry_price), "cikis": _px(t.exit_price), "sure": sure_metni(t.entry_ts, t.exit_ts),
            "komisyon": (t.fee_entry or 0.0) + (t.fee_exit or 0.0), "fonlama": t.funding_paid or 0.0,
            "buyukluk": notional, "kaldirac": t.leverage,
            "marj": (notional / t.leverage) if (notional and t.leverage) else None,
            "kapanis_ts": t.exit_ts.timestamp() if t.exit_ts else None, "acilis_ts": t.entry_ts.timestamp() if t.entry_ts else None,
            "ders": bool(d is not None and d.lesson_ids)}


def closed_view(path: str, bot: str, period: str, now: datetime, limit: int = 200) -> dict:
    if period not in PERIODS:
        raise P.SectionError("gecersiz_donem")
    ctx = Ctx(path, bot)
    a, b = period_bounds(period, now)
    sel = [t for t in ctx.closed if t.exit_ts is not None and (a is None or t.exit_ts >= a) and (b is None or t.exit_ts < b)]
    n = len(sel)
    wins = sum(1 for t in sel if (t.realized_pnl or 0) > 0)
    net = math.fsum(t.realized_pnl or 0.0 for t in sel)
    return {"period": period, "n": n, "kazanan_yuzde": (wins / n * 100.0) if n else None, "net": net,
            "rows": [closed_row(t, ctx) for t in sel[:limit]], "daha_fazla": max(n - limit, 0)}


# ----------------------------------------------------------------------------- acik islemler
def open_view(ctx: Ctx, status: Mapping | None, now: datetime) -> dict:
    """status: read_status() `data` (canliysa) ya da None. Motor durumu fiyat/K-Z verir; defter kol/kaldirac/aciklama verir."""
    live = {p.get("trade_id"): p for p in ((status or {}).get("open_positions") or []) if isinstance(p, Mapping)}
    rows = []
    for t in ctx.open:
        p = live.get(t.trade_id) or {}
        d = ctx.dec.get(t.decision_id)
        notional = _f(p.get("notional_usd"))
        if notional is None:
            notional = (t.entry_price or 0) * (t.qty or 0)
        reg = REJIM_TR.get(str(getattr(d, "regime", "") or t.regime or ""))
        kol = ctx.kol(t)
        rows.append({"id": t.trade_id, "coin": TS.coin(t.pair), "yon": TS.yon(t.side), "kol": kol, "giris": _px(t.entry_price),
                     "simdi": _f(p.get("mark")), "kz": _f(p.get("unrealized_pnl_usd")),
                     "fiyat_bekleniyor": status is not None and _f(p.get("mark")) is None,   # piyasa kapali / veri yok: K/Z sayisi yerine metin
                     "kz_yuzde": _f(p.get("unrealized_pct")), "sure": sure_metni(t.entry_ts, now),
                     "stop": _f(p.get("stop")) if p.get("stop") is not None else _px(t.planned_stop),
                     "hedef": _px(t.planned_target), "buyukluk": notional, "kaldirac": t.leverage,
                     "acilis": tsi_kisa(t.entry_ts), "acilis_ts": t.entry_ts.timestamp() if t.entry_ts else None,
                     "neden": f"{TS.kurulum_adi(t.setup)} sinyali" + (f", {reg}" if reg else ""),
                     "_marj": (notional / t.leverage) if (notional and t.leverage) else None})
    kz = [r["kz"] for r in rows if r["kz"] is not None]
    eq = _f((status or {}).get("equity"))
    marj = math.fsum(r["_marj"] for r in rows if r["_marj"] is not None)
    en_iyi = max((r for r in rows if r["kz"] is not None), key=lambda r: r["kz"], default=None)
    en_kotu = min((r for r in rows if r["kz"] is not None), key=lambda r: r["kz"], default=None)
    for r in rows:
        r.pop("_marj", None)
    return {"n": len(rows), "kz": math.fsum(kz) if kz else None,
            "kasa_yuzde": (marj / eq * 100.0) if (eq and eq > 0 and rows) else None,
            "en_iyi": {"coin": en_iyi["coin"], "kz": en_iyi["kz"]} if en_iyi else None,
            "en_kotu": {"coin": en_kotu["coin"], "kz": en_kotu["kz"]} if en_kotu and en_kotu is not en_iyi else None,
            "rows": rows}


# ----------------------------------------------------------------------------- serit
def _yas_metni(age_s: float | None) -> str:
    if age_s is None:
        return ""
    m = int(age_s // 60)
    return f"{m} dk önce" if m < 120 else f"{m // 60} sa önce"


def risk_durumu(status: Mapping | None, state: str, kill_file: bool | None, pnl_bugun: float, age_s: float | None = None) -> dict:
    """Tek Turkce risk durumu. renk: yesil Guvenli / sari Limite yakin (>=%70) / kirmizi Durdu: neden / gri Bilinmiyor
    (durum bilgisi eski ya da kasa/gun basi bakiyesi okunamadi: limit ve kalan gosterilmez, eski sayi canli gibi sunulmaz).
    Limit tek kaynaktan: panel_data.daily_loss_rate(mode) x gun basi equity."""
    d = status or {}
    rate = P.daily_loss_rate(d.get("mode") or "paper")
    dse = _f(d.get("day_start_equity"))
    eq = _f(d.get("equity"))
    limit = rate * dse if dse and dse > 0 else None
    kullanilan = max(0.0, -pnl_bugun)
    kalan = max(limit - kullanilan, 0.0) if limit is not None else None
    oran = (kullanilan / limit) if limit else None
    alt = f"günlük limite kalan {tr_sayi(kalan)} $" if kalan is not None else "günlük limite kalan —"
    out = {"limit": limit, "limit_orani": rate, "kullanilan": kullanilan, "kalan": kalan, "oran": oran}
    if kill_file or d.get("kill"):
        return {**out, "renk": "kirmizi", "metin": "Durdu: acil durdurma", "alt": alt}
    if state != "live":
        why = "durum bilgisi eski" if state == "stale" else "durum bilgisi okunamıyor"
        yas = _yas_metni(age_s) if state == "stale" else ""
        return {**out, "limit": None, "kalan": None, "oran": None, "renk": "gri", "metin": f"Bilinmiyor ({why})",
                "alt": "günlük limite kalan —" + (f" · son durum {yas}" if yas else "")}
    if eq is None or dse is None or dse <= 0:
        return {**out, "limit": None, "kalan": None, "oran": None, "renk": "gri",
                "metin": "Bilinmiyor (kasa ya da gün başı bakiyesi okunamadı)", "alt": "günlük limite kalan —"}
    if oran is not None and oran >= 1.0:
        return {**out, "renk": "kirmizi", "metin": "Durdu: günlük zarar limiti doldu", "alt": alt}
    if d.get("entries_open") is False:
        kod = d.get("entries_blocked_reason") or d.get("gate_code")
        neden = neden_sade(kod) if kod not in (None, "ok") else "yeni işlemler kapalı"
        return {**out, "renk": "kirmizi", "metin": f"Durdu: {neden}", "alt": alt}
    if oran is not None and oran >= 0.70:
        return {**out, "renk": "sari", "metin": "Limite yakın", "alt": alt}
    return {**out, "renk": "yesil", "metin": "Güvenli", "alt": alt}


def kz_donem(trades: list, a: datetime | None, b: datetime | None = None) -> float:
    return math.fsum(t.realized_pnl or 0.0 for t in trades
                     if t.exit_ts is not None and (a is None or t.exit_ts >= a) and (b is None or t.exit_ts < b))


def serit_view(ctx: Ctx, status: Mapping | None, state: str, kill_file: bool | None, start: float | None, now: datetime,
               curve: Mapping | None, age_s: float | None = None) -> dict:
    d = status or {}
    eq = _f(d.get("equity"))
    pnl_bugun = kz_donem(ctx.closed, gun_basi(now), gun_basi(now, -1))
    toplam = (eq - start) if (eq is not None and start) else None       # TOPLAM K/Z = kasa - baslangic (acik K/Z dahil)
    dse = _f(d.get("day_start_equity")) or start
    acik_n = len(d.get("open_positions") or []) if state == "live" else len(ctx.open)
    unreal = _f(d.get("unrealized_pnl_usd")) if state == "live" else None
    # zirveden dusus: kapanan islem egrisinin zirvesi (+ canli equity)
    dd = dd_pct = None
    if curve and curve.get("points"):
        last = curve["points"][-1]
        cur = eq if eq is not None else last[1]
        peak = max(_f(curve.get("peak")) or cur, cur) if curve.get("base") == "equity" else None
        if peak:
            dd, dd_pct = cur - peak, (cur / peak - 1.0) * 100.0
        else:
            dd = last[2]
    elif eq is not None and start:
        dd, dd_pct = min(eq - start, 0.0), min((eq / start - 1.0) * 100.0, 0.0)
    return {"kasa": eq, "baslangic": start,
            "bugun": pnl_bugun, "bugun_yuzde": (pnl_bugun / dse * 100.0) if dse else None,
            "toplam": toplam, "toplam_yuzde": (toplam / start * 100.0) if (start and toplam is not None) else None,
            "acik": acik_n, "acik_kz": unreal, "dusus": dd, "dusus_yuzde": dd_pct,
            "durum_yasi_s": age_s, "risk": risk_durumu(d if state == "live" else None, state, kill_file, pnl_bugun, age_s)}


# ----------------------------------------------------------------------------- K/Z
def kz_view(ctx: Ctx, start: float | None, now: datetime, curve: Mapping | None, arms: list[str]) -> dict:
    cl = [t for t in ctx.closed if t.exit_ts is not None]
    d30 = gun_basi(now, 29)
    donemler = {}
    for ad, a in (("bugun", gun_basi(now)), ("7g", gun_basi(now, 6)), ("30g", d30), ("tumu", None)):
        v = kz_donem(cl, a, gun_basi(now, -1) if ad == "bugun" else None)
        donemler[ad] = {"kz": v, "yuzde": (v / start * 100.0) if start else None}
    egri = []
    if curve and curve.get("points"):
        egri = [[tsi_gun(P.parse_z(p[0])), p[1]] for p in curve["points"] if (P.parse_z(p[0]) or now) >= d30]
    wins = [t.realized_pnl for t in cl if (t.realized_pnl or 0) > 0]
    loss = [t.realized_pnl for t in cl if (t.realized_pnl or 0) <= 0]
    if len(cl) >= MIN_ORAN:
        oran = {"kazanma_yuzde": len(wins) / len(cl) * 100.0, "n": len(cl),
                "ort_kazanc": math.fsum(wins) / len(wins) if wins else None,
                "ort_kayip": math.fsum(loss) / len(loss) if loss else None}
    else:
        oran = olculemedi(len(cl), MIN_ORAN)
    by: dict[str, list[float]] = {}
    for t in cl:
        by.setdefault(ctx.kol(t), []).append(t.realized_pnl or 0.0)
    ad_sira = [TS.kol_adi(a) for a in arms]
    adlar = [k for k in ad_sira if k in by] + sorted(k for k in by if k not in ad_sira)    # yalniz islemi olan kollar
    kol = [{"kol": k, "n": len(by[k]), "kz": math.fsum(by[k])} for k in adlar]

    def maliyet(a):
        sel = [t for t in cl if a is None or t.exit_ts >= a]
        return {"komisyon": math.fsum((t.fee_entry or 0.0) + (t.fee_exit or 0.0) for t in sel),
                "fonlama": math.fsum(t.funding_paid or 0.0 for t in sel)}
    return {"donemler": donemler, "egri": egri if len(egri) >= 2 else None, "oran": oran if cl else None, "kol": kol if cl else [],
            "masraf": {"30g": maliyet(d30), "tumu": maliyet(None)} if cl else None}


# ----------------------------------------------------------------------------- ogrenme (ders + ML)
MIN_KOL_ISLEM = 10      # motorun ogrenme_filtre.MIN_ISLEM ile ayni; esitligi tests/test_panel_pano.py denetler (core -> engine bagimliligi yok)


# ----- ortak durum sozlugu (OZET / OGRENME / Telegram ayni metni kullanir)
DURUM_ETKILIYOR = "Açık, işlemleri etkiliyor"
DURUM_MODEL_BEKLENIYOR = "Açık, model bekleniyor"
DURUM_KAPALI = "Kapalı"


def durum_veri_birikiyor(x: int, y: int | None = None) -> str:
    return f"Açık, veri birikiyor ({x}/{y})" if y else "Açık, veri birikiyor"


def ogrenme_durumu(calisiyor: bool, etkili: bool, x: int = 0, y: int | None = None, model_bekliyor: bool = False,
                   kol: tuple[int, int] | None = None) -> tuple[str, str]:
    """(metin, renk): kapali = gri; etkiliyor = yesil; veri birikiyor / model bekleniyor = sari (kirmizi degil)."""
    if not calisiyor:
        return DURUM_KAPALI, "gri"
    if etkili:
        return DURUM_ETKILIYOR + (f" · {kol[0]}/{kol[1]} kol" if kol else ""), "yesil"
    if model_bekliyor:
        return DURUM_MODEL_BEKLENIYOR, "sari"
    return durum_veri_birikiyor(x, y), "sari"


def min_kol_islem() -> int:
    """Kol basina ML filtresi icin asgari kapanmis islem (motor sabitiyle esit; testle sabitlenir)."""
    return MIN_KOL_ISLEM


def katki_olculemedi(n: int) -> dict:
    """Katki icin kendi sayisi: sonucu belli karar sayisi (onay/ret sayisindan farkli olabilir)."""
    return {"olculemedi": f"Henüz ölçülemedi (sonucu belli {n} karar, en az {MIN_ETKI})"}


def _usd_per_r(trades: list) -> float | None:
    v = [t.planned_risk for t in trades if t.planned_risk]
    return math.fsum(v) / len(v) if v else None


_BIRIM = {"stop_buffer_atr": "ATR", "trail_atr": "ATR", "range_width_atr": "ATR", "edge_zone_atr": "ATR",
          "rr_min": "R", "vol_ratio_max": "kat", "pullback_ema": "bar", "post_stop_wait": "bar"}


def _deger(v: Any) -> str:
    return tr_sayi(v, 2).rstrip("0").rstrip(",") if isinstance(v, float) else str(v)


def _param_farki(old: Mapping | None, new: Mapping | None) -> str:
    """Iki param surumu farki -> tek sade cumle (LLM metni degil)."""
    if not isinstance(new, Mapping):
        return "Bir ayar güncellendi"
    old = old if isinstance(old, Mapping) else {}
    parts = []
    for k in sorted(new):
        if k in old and old[k] != new[k] and not isinstance(new[k], (dict, list)):
            birim = _BIRIM.get(k)
            parts.append(f"{TS.PARAM_AD.get(k, k)} {_deger(old[k])} → {_deger(new[k])}" + (f" {birim}" if birim else ""))
    return ", ".join(parts[:2]) if parts else "Bir ayar güncellendi"


def ders_view(path: str, ctx: Ctx, now: datetime, status_live: bool) -> dict | None:
    from . import lesson as LS  # noqa: PLC0415
    led = P.open_ledger_ro(path, "learner")
    try:
        acts = [a for a in led.list_activations(200) if a.actor == "lesson"]
        brake = bool(LS.brake_active(led))
        try:
            eff = LS.evaluate_brake(led, LS.load_config(), now).effect
        except Exception:  # noqa: BLE001
            eff = None
        satirlar = []
        for a in acts[:5]:
            try:
                new = led.get_version(a.version_id).params
                old = led.get_version(a.prev_version_id).params if a.prev_version_id else None
            except Exception:  # noqa: BLE001
                new = old = None
            ne = _param_farki(old, new)
            satirlar.append({"tarih": tsi_gun(a.activated_at), "metin": ("Geri alındı: " if a.kind == "rollback" else "") + ne,
                             "geri": a.kind == "rollback"})
    finally:
        led.close()
    uygulanan = [a for a in acts if a.kind == "apply"]
    d7 = now - timedelta(days=7)
    degisen = sum(1 for d in ctx.decisions if d.final_action == "entered" and d.lesson_ids and d.bar_close_ts >= d7)
    sonra = (sum(1 for d in ctx.decisions if d.final_action == "entered" and d.bar_close_ts >= uygulanan[0].activated_at)
             if uygulanan else 0)
    if brake:
        durum, renk = "Kapalı (ders freni devrede)", "gri"
    elif uygulanan and degisen > 0:
        durum, renk = ogrenme_durumu(True, True)
    elif uygulanan:
        durum, renk = ogrenme_durumu(True, False, min(eff.n if eff is not None else 0, MIN_ETKI), MIN_ETKI)
    else:
        durum, renk = ogrenme_durumu(bool(status_live), False, min(eff.n if eff is not None else 0, MIN_ETKI), MIN_ETKI)
    son = next((s for s in satirlar if not s["geri"]), satirlar[0] if satirlar else None)
    if eff is not None and eff.n >= MIN_ETKI:
        r2usd = _usd_per_r(ctx.closed)
        katki = ({"usd": eff.damped * r2usd, "yaklasik": True, "n": eff.n} if r2usd else katki_olculemedi(eff.n))
    else:
        katki = katki_olculemedi(eff.n if eff is not None else 0)
    return {"durum": durum, "renk": renk, "son": son, "degisen_7g": degisen, "katki": katki,
            "son5": satirlar if len(satirlar) > 1 else []}           # tek ders: "Son dersler" listesi tekrar olur


def _ml_paketleri(ledger_path: str, now: datetime) -> tuple[int, int, datetime | None, set]:
    """(gecerli paket sayisi, toplam egitim ornegi, son egitim zamani) — `<defter dizini>/models/ortak_filtre/*.json` meta."""
    klasor = Path(ledger_path).parent / "models" / "ortak_filtre"
    n_paket = n_ornek = 0
    son: datetime | None = None
    kur: set = set()
    if not klasor.is_dir():
        return 0, 0, None, kur
    for p in sorted(klasor.glob("*.json")):
        if p.name.endswith(".prev.json") or p.name.startswith("."):
            continue
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))["meta"]
            sk = P.parse_z(str(meta.get("son_kullanma")))
            if sk is not None and sk <= now:
                continue
            n_paket += 1
            kur.add(str(meta.get("kurulum")))
            n_ornek += int(meta.get("n_egitim") or 0)
            ol = P.parse_z(str(meta.get("olusturma") or meta.get("created_at") or ""))
            if ol is None:
                ol = datetime.fromtimestamp(p.stat().st_mtime, tz=P.UTC)
            son = ol if son is None or ol > son else son
        except Exception:  # noqa: BLE001
            continue
    return n_paket, n_ornek, son, kur


def ml_view(path: str, ctx: Ctx, now: datetime, ml_filtre: Mapping | None) -> dict | None:
    from . import counterfactual as CF  # noqa: PLC0415
    cf_path = Path(path).parent / "counterfactual.sqlite"
    try:
        cf_rows = CF.arm_rows(cf_path, "learner") if cf_path.exists() else []
    except Exception:  # noqa: BLE001
        cf_rows = []
    r_taken = {t.decision_id: t.r_multiple for t in ctx.closed if t.r_multiple is not None}
    r_cf = {row["decision_id"]: row["hyp_r_net"] for row in cf_rows}
    pnl_of = {t.decision_id: t.realized_pnl for t in ctx.closed}
    skorlu = [d for d in ctx.decisions if d.ml_score is not None or d.skip_reason == "ml_filter"]
    n_paket, n_ornek, son_egitim, paket_kur = _ml_paketleri(path, now)
    if isinstance(ml_filtre, Mapping):
        acik = bool(ml_filtre.get("calisiyor"))          # kapali YALNIZ filtre gercekten calismiyorsa
        kolsay = int(ml_filtre.get("aktif_kurulum") or 0)
    else:
        acik, kolsay = n_paket > 0, n_paket
    arm_of = lambda d: getattr(d, "arm_id", None) or f"{d.setup}@{d.trigger_tf}"  # noqa: E731
    en_az = min_kol_islem()
    cfg_kollar = list(P.paper_maps()[0])
    tum = cfg_kollar or sorted({arm_of(d) for d in ctx.decisions if d.final_action == "entered"})    # payda: kagit ayarindaki kol listesi
    kapali = {}
    for t in ctx.closed:
        dd = ctx.dec.get(t.decision_id)
        if dd is not None:
            kapali[arm_of(dd)] = kapali.get(arm_of(dd), 0) + 1
    kapsam = None
    if acik and tum:
        aktif = [a for a in tum if a in paket_kur] if paket_kur else []
        kalan = [a for a in tum if a not in aktif]
        kismen = sorted(((a, kapali.get(a, 0)) for a in kalan if kapali.get(a, 0) > 0), key=lambda x: -x[1])
        kapsam = {"aktif": len(aktif), "toplam": len(tum), "en_az": en_az,
                  "eksik": [{"kol": TS.kol_adi(a), "n": n, "en_az": en_az} for a, n in kismen[:6]],
                  "eksik_fazla": max(len(kismen) - 6, 0), "bos": sum(1 for a in kalan if kapali.get(a, 0) == 0)}
        en_cok = max(kapali.values(), default=0)
        durum, renk = ogrenme_durumu(True, bool(aktif), min(en_cok, en_az), en_az, model_bekliyor=en_cok >= en_az,
                                     kol=(len(aktif), len(tum)))
    else:
        en_cok = max(kapali.values(), default=0)
        durum, renk = ogrenme_durumu(acik, kolsay > 0, min(en_cok, en_az), en_az, model_bekliyor=en_cok >= en_az)

    def sonuc_r(d):
        return r_taken.get(d.id) if d.final_action == "entered" else r_cf.get(d.id)
    # isabet: gecirdi & kazandi ya da eledi & kaybederdi
    sonuclu = sorted((d for d in skorlu if sonuc_r(d) is not None), key=lambda d: d.bar_close_ts)[-20:]
    if len(sonuclu) >= MIN_ISABET:
        tutan = sum(1 for d in sonuclu if (sonuc_r(d) > 0) == (d.skip_reason != "ml_filter"))
        isabet = {"tutan": tutan, "n": len(sonuclu)}
    else:
        isabet = olculemedi(len(sonuclu), MIN_ISABET, "tahmin")
    d7 = now - timedelta(days=7)
    son7 = [d for d in skorlu if d.bar_close_ts >= d7]
    onay = sum(1 for d in son7 if d.final_action == "entered")
    ret = sum(1 for d in son7 if d.skip_reason == "ml_filter")
    d30 = now - timedelta(days=30)
    elenen = [sonuc_r(d) for d in skorlu if d.skip_reason == "ml_filter" and d.bar_close_ts >= d30 and sonuc_r(d) is not None]
    r2usd = _usd_per_r([t for t in ctx.closed if t.exit_ts and t.exit_ts >= d30] or ctx.closed)
    if len(elenen) >= MIN_ETKI and r2usd:
        katki = {"usd": -math.fsum(float(r) for r in elenen) * r2usd, "yaklasik": True, "n": len(elenen)}
    else:
        katki = katki_olculemedi(len(elenen))
    son5 = []
    for d in sorted(skorlu, key=lambda d: d.bar_close_ts, reverse=True)[:5]:
        alindi = d.final_action == "entered"
        r = sonuc_r(d)
        pn = None
        if alindi:
            pn = pnl_of.get(d.id)
            sonuc = "" if pn is not None else "açık"
        else:
            sonuc = "alsaydı kazanırdı" if (r is not None and r > 0) else ("alsaydı kaybederdi" if r is not None else "sonuç bekleniyor")
        son5.append({"coin": TS.coin(d.pair), "tarih": tsi_kisa(d.bar_close_ts), "karar": "Aldı" if alindi else "Almadı",
                     "puan": d.ml_score, "sonuc": sonuc, "kz": pn})
    return {"durum": durum, "renk": renk, "kapsam": kapsam, "isabet": isabet, "onay_7g": onay, "ret_7g": ret, "katki": katki,
            "egitim": ({"tarih": tsi_gun(son_egitim), "ornek": n_ornek} if son_egitim else None), "son5": son5}


def kucultme_view(ledger_path: str, bot: str) -> dict | None:
    """OGRENME sekmesi 'Kademeli kucultme' karti (docs/motor/kademeli-kucultme-spec.md): boyutu kucultulen kollar
    (carpan, son 5/10 net R). Kucultulen kol yoksa ya da okunamazsa None (kart gizlenir)."""
    from . import kol_kucultme as KK  # noqa: PLC0415
    led = P.open_ledger_ro(ledger_path, bot)
    try:
        az = KK.azaltilanlar(led.arm_results_all(KK.KAYIT_SAYISI))
    finally:
        led.close()
    if not az:
        return None
    return {"kollar": [{"kol": a, "carpan": k.carpan, "n": k.n, "net_5": k.net_5, "net_10": k.net_10}
                       for a, k in sorted(az.items())]}


# ----------------------------------------------------------------------------- teknik
def _testnet_alarmi(a: Mapping) -> bool:
    """Testnet golge botuna ait kontrol (ad ':<bot>' ekinde 'testnet'): kagit botu etkilemez; yalniz TEKNIK'te gri bilgi."""
    return "testnet" in str(a.get("name") or "").partition(":")[2].lower()


def _testnet_cumlesi(a: Mapping) -> str:
    if str(a.get("code") or "").removesuffix("_warmup") == "capital_missing":
        return "Testnet botu: sermaye kaydı girilmemiş (gerçek paraya geçişte yapılacak)"
    s, _ = TS.saglik_cumlesi(a.get("name"), a.get("code"))
    return "Testnet botu: " + s[:1].lower() + s[1:]


def _saglik_cumleleri(alerts: list) -> tuple[list[str], list[str]]:
    """Sorunlu saglik kontrolleri -> (sade cumleler, 'Senden' eylemleri). Telegram'a gitmeyen kontroller de adiyla gorunur
    (WARN/CRIT hicbir kontrol panelde adsiz kalmaz); tek sozluk: tg_sade.saglik_cumlesi. OK/SKIPPED duzeyli kayitlar atlanir."""
    out: list[str] = []
    senden: list[str] = []
    for a in alerts:
        if str(a.get("level") or "").upper() in ("OK", "SKIPPED", "INFO") or _testnet_alarmi(a):
            continue
        s, yap = TS.saglik_cumlesi(a.get("name"), a.get("code"))
        if s not in out:
            out.append(s)
        if yap and yap not in senden:
            senden.append(yap)
    return out[:8], senden[:3]


def mutabakat_view(path: str) -> dict | None:
    """`var/durum/mutabakat_v1.json` -> {"son": "20.11 04:40" (TSI), "islem": N, "uyusmazlik": N}; yok/bozuk/yanlis sema -> None (satir gizlenir)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("sema") != "ml.mutabakat.v1":
        return None
    made = P.parse_z(d.get("uretim"))
    n, u = d.get("islem_sayisi"), d.get("uyusmazlik_sayisi")
    if made is None or not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (n, u)):
        return None
    return {"son": tsi_kisa(made), "islem": n, "uyusmazlik": u}


def teknik_view(*, health: Mapping | None, risk_rows: list | None, budget: Mapping | None, tut: Mapping | None,
                pbo: Mapping | None, ctx: Ctx | None, ml_filtre: Mapping | None, ders: Mapping | None,
                mutabakat: Mapping | None = None, dayaniklilik: Mapping | None = None) -> dict:
    out: dict[str, Any] = {}
    if isinstance(dayaniklilik, Mapping):
        kar = [f"{r.get('birim')}: art arda kod hatası, yeni işlem açmıyor (açık pozisyonlar sürüyor)"
               for r in dayaniklilik.get("karantina") or [] if isinstance(r, Mapping) and r.get("durum") == "aktif"]
        sem = [f"{r.get('cift')}: borsada işlem dışı, yeni giriş yok" + (" (açık pozisyon var)" if r.get("open") else "")
               for r in dayaniklilik.get("sembol") or [] if isinstance(r, Mapping)]
        if kar or sem:
            out["dayaniklilik"] = {"karantina": kar, "sembol": sem}
    if mutabakat:
        out["mutabakat"] = dict(mutabakat)
    if health:
        ov = str(health.get("overall") or "UNKNOWN")
        alerts = health.get("alerts") or []
        uy, senden = _saglik_cumleleri(alerts)
        diger = []
        for a in alerts:
            if isinstance(a, Mapping) and str(a.get("level") or "").upper() not in ("OK", "SKIPPED", "INFO") and _testnet_alarmi(a):
                c = _testnet_cumlesi(a)
                if c not in diger:
                    diger.append(c)
        if diger and ov in ("WARN", "CRIT"):          # genel durum yalniz testnet'ten geliyorsa kagit botu sorunsuz sayilir
            lv = {str(a.get("level") or "").upper() for a in alerts if isinstance(a, Mapping) and not _testnet_alarmi(a)}
            ov = "CRIT" if "CRIT" in lv else ("WARN" if "WARN" in lv else ("UNKNOWN" if "UNKNOWN" in lv else "OK"))
        if ov in ("WARN", "CRIT", "UNKNOWN") and not uy:      # sorun var ama adi okunamadi: yine de gorunur (adsiz ama dürüst)
            uy = [TS.SAGLIK_BILINMEYEN]
        out["saglik"] = {"durum": SAGLIK_TR.get(ov, "Bilinmiyor"), "renk": {"OK": "yesil", "WARN": "sari", "CRIT": "kirmizi"}.get(ov, "sari"),
                         "uyarilar": uy, "senden": senden, "kontrol_bayat": bool(health.get("check_stale")),
                         "diger_botlar": diger[:4]}
    if risk_rows:
        out["limitler"] = [{"ad": r["label"], "kullanilan": r["used"], "limit": r["limit"], "yuzde": r["pct"]} for r in risk_rows]
    kap = []
    if isinstance(ml_filtre, Mapping):
        kap.append({"ad": "Yapay zekâ filtresi", "ok": bool(ml_filtre.get("calisiyor")),
                    "not": f"{int(ml_filtre.get('aktif_kurulum') or 0)} kolda aktif"})
    if ders:
        kap.append({"ad": "Ders freni", "ok": "freni" not in str(ders.get("durum")), "not": str(ders.get("durum"))})
    if kap:
        out["kapilar"] = kap
    if budget:
        sv = budget.get("services") or {}
        out["model"] = [{"ad": "Yapay zekâ", "cagri_bugun": sum(int(v.get("calls_today") or 0) for v in sv.values()),
                         "maliyet_ay": budget.get("month_used_usd")}] if sv else None
        out["butce"] = {"kullanilan": budget.get("month_used_usd"), "tavan": budget.get("monthly_cap_usd")}
    if ctx is not None:
        out["kayitlar"] = {"kapanan": len(ctx.closed), "acik": len(ctx.open), "karar": len(ctx.decisions)}
    dog = {}
    if tut and tut.get("var"):
        ks = [k for k in tut.get("kurulumlar") or [] if k.get("eslesme_orani") is not None]
        if ks:
            dog["eslesme"] = math.fsum(k["eslesme_orani"] for k in ks) / len(ks)
        dog["uyari"] = bool(tut.get("uyari"))
    if pbo and (pbo.get("pbo") or {}).get("var"):
        fam = pbo["pbo"].get("aileler") or []
        vals = [a["pbo"] for a in fam if a.get("pbo") is not None]
        if vals:
            dog["pbo"] = max(vals)
    if dog:
        out["dogrulama"] = dog
    return out


def _ilk_sorun(saglik: Mapping) -> str:
    uy = saglik.get("uyarilar") or []
    return (str(uy[0]) + (f" (+{len(uy) - 1} uyarı daha)" if len(uy) > 1 else "")) if uy else "ayrıntı TEKNİK sekmesinde"


def _problem(saglik: Mapping | None, state: str, risk: Mapping, budget: Mapping | None) -> dict:
    sebepler = []
    if state != "live":
        sebepler.append("Bot yanıt vermiyor")
    if saglik and saglik.get("renk") == "kirmizi":
        sebepler.append("Sağlık kontrolü sorun bildiriyor: " + _ilk_sorun(saglik))
    if saglik and saglik.get("kontrol_bayat"):
        sebepler.append("Sağlık kontrolü güncel değil")
    if budget and str(budget.get("month_state") or "") in ("exhausted", "blocked"):
        sebepler.append("Yapay zekâ bütçesi doldu")
    if sebepler:
        return {"renk": "kirmizi", "metin": "; ".join(sebepler[:2])}
    if saglik and saglik.get("renk") == "sari":
        return {"renk": "sari", "metin": "Sağlık uyarısı: " + _ilk_sorun(saglik)}
    return {"renk": "yesil", "metin": "Sistem sağlıklı"}


def kismi_durum(ders: Mapping | None, ml: Mapping | None) -> list[str]:
    """Sistem calisiyor ama tam degil: sade cumleler (bos = her sey tam)."""
    out = []
    if ders and ders.get("renk") == "kirmizi":
        out.append("ders işlemleri etkilemiyor")
    if ml and ml.get("kapsam") and ml["kapsam"]["aktif"] < ml["kapsam"]["toplam"]:
        k = ml["kapsam"]
        if k["aktif"] == 0 and ml.get("durum"):
            out.append(f"Makine öğrenmesi: {ml['durum']}")
            return out
        out.append(f"ML {k['aktif']}/{k['toplam']} kolda çalışıyor, diğerlerinde yeterli işlem yok (en az {k['en_az']})")
    return out


def saglik_yapmali(saglik: Mapping | None) -> str | None:
    """Saglik WARN/CRIT ise 'Ne yapmaliyim?' cumlesi (kullanici eylemi gerekiyorsa o, degilse 'bir sey gerekmiyor'); yoksa None."""
    if not saglik or saglik.get("renk") not in ("sari", "kirmizi") or not saglik.get("uyarilar"):
        return None
    uy = [str(u).rstrip(".") for u in saglik["uyarilar"][:2]]
    sorun = "; ".join(uy) + (f" (+{len(saglik['uyarilar']) - 2} uyarı daha)" if len(saglik["uyarilar"]) > 2 else "")
    if saglik.get("senden"):
        return f"Sağlık uyarısı: {sorun}. " + " ".join(saglik["senden"][:2])
    return f"Bir şey yapmanız gerekmiyor; sağlık uyarısı inceleniyor: {sorun}."


def _ne_yapmali_temel(state: str, risk: Mapping, acik_n: int, kismi: list[str] | None = None) -> str:
    if state != "live":
        return "Bot yanıt vermiyor; otomatik yeniden başlatma deneniyor. Uzun sürerse bana haber ver."
    if risk["renk"] == "kirmizi":
        return "Yeni işlemler kapalı; açık işlemler stoplarla izleniyor. Şimdilik yapılacak bir şey yok."
    if risk["renk"] == "sari":
        return "Günlük zarar limitine yaklaşıldı; limit dolarsa yeni işlem durur. Yapılacak bir şey yok."
    if kismi:
        return "Bir şey yapmanız gerekmiyor; " + "; ".join(kismi) + "."
    if acik_n:
        return f"Bir şey yapmanız gerekmiyor; bot çalışıyor, {acik_n} açık işlem izleniyor."
    return "Bir şey yapmanız gerekmiyor; bot çalışıyor, uygun fırsat bekleniyor."


def ne_yapmali(state: str, risk: Mapping, acik_n: int, kismi: list[str] | None = None, saglik: Mapping | None = None) -> str:
    """Her durumda saglik WARN/CRIT'i anar (bot/risk durumu once gelir, saglik cumlesi arkasina eklenir)."""
    t = _ne_yapmali_temel(state, risk, acik_n, kismi)
    sy = saglik_yapmali(saglik)
    if not sy:
        return t
    if state == "live" and risk["renk"] == "yesil":
        return sy + (" Ayrıca: " + "; ".join(kismi) + "." if kismi else "")      # genel "bir sey gerekmiyor" cümlesinin yerine
    return t + " " + sy
