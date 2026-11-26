"""ML1 gorunum verisi (pano ML1 sekmesi, Telegram gunluk/haftalik ozet ve /ml1 AYNI sayilari kullanir). Yalniz stdlib, salt okunur.

`trader_core` `trader_ml`'i ice aktarmaz: kurulum -> fikir grubu eslemesi `trader_ml/ml1/groups.py::_GRUP_KURULUM`dan KOPYALANIR
(`GRUP_KURULUM`); ikisinin birebir ayni oldugu testle sinanir. Veri yeni tablo/sutun istemez: ML1'in her adaya verdigi puan karar
kaydinin `features` alaninda (`ml1_skor`, `ml1_esik`, `ml1_grup`), red nedeni `veto_reason`, girilen aday `final_action == "entered"`.
Esik koda yazilmaz: kaydin kendi `ml1_esik` degeri okunur. Tek tarihli sabit: `SINAV` (sinav sonucu).
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from . import tg_sade as TS

TR = timezone(timedelta(hours=3))

# kurulum -> fikir grubu (trader_ml/ml1/groups.py::_GRUP_KURULUM ile birebir ayni olmali; testle sinanir)
GRUP_KURULUM: dict[str, tuple[str, ...]] = {
    "PULLBACK_1LEG": ("T1", "T1-GERI3", "T1-SEVIYE", "IN1-MAGERI", "IN1-FIBO"),
    "PULLBACK_2LEG": ("H2", "H2-MINI"),
    "TREND_BREAKOUT": ("TF1", "IN1-HACIM"),
    "RANGE_EDGE": ("R1", "GF1-YATAY"),
    "LEVEL_RETEST": ("B1", "B1-BOLGE", "GF1-RETEST"),
    "FALSE_BREAK": ("F1", "GF1-SAHTE", "MF1-ICSAHTE"),
    "SQUEEZE_BREAK": ("S1", "S1-OLCULU"),
    "CHART_CONT": ("GF1-UCGEN", "GF1-FLAMA", "GF1-BAYRAK"),
    "CHART_REVERSAL": ("GF1-IKILI", "GF1-UCLU", "GF1-OBO", "GF1-KUPA", "GF1-KAMA"),
    "CHANNEL_TLINE": ("GF1-KANAL", "GF1-TREND", "PA2-TCIZGI"),
    "CANDLE_PIN": ("MF1-PINBAR", "MF1-CIMBIZ"),
    "CANDLE_ENGULF": ("MF1-YUTAN", "MF1-DELICI", "MF1-DISBAR"),
    "CANDLE_INSIDE": ("MF1-HARAMI", "MF1-ICCUBUK"),
    "OSC_REVERSAL": ("IN1-RSI", "IN1-RSI2", "IN1-RSIDONUS", "IN1-STOK", "IN1-UYUMSUZ"),
    "MA_CROSS": ("IN1-MAKESISIM", "IN1-HIZLIMA", "IN1-TK", "IN1-MACD"),
    "MA_TREND_FLIP": ("IN1-FIYATMA", "IN1-KUMO"),
    "BAND_VWAP": ("IN1-BOLL", "IN1-BOLLKIR", "IN1-VWAP"),
    "SD_ZONE": ("PA2-BOLGE", "PA2-EMIRBLOK", "PA2-FVG", "PA2-ONCEKI"),
}
GRUP_AD: dict[str, str] = {
    "PULLBACK_1LEG": "Tek bacaklı geri çekilme", "PULLBACK_2LEG": "İki bacaklı geri çekilme", "TREND_BREAKOUT": "Trend kırılımı",
    "RANGE_EDGE": "Yatay piyasa kenarı", "LEVEL_RETEST": "Seviye yeniden testi", "FALSE_BREAK": "Sahte kırılım",
    "SQUEEZE_BREAK": "Sıkışma kırılımı", "CHART_CONT": "Grafik: devam formasyonu", "CHART_REVERSAL": "Grafik: dönüş formasyonu",
    "CHANNEL_TLINE": "Kanal / trend çizgisi", "CANDLE_PIN": "Mum: pin bar ailesi", "CANDLE_ENGULF": "Mum: yutan ailesi",
    "CANDLE_INSIDE": "Mum: iç çubuk ailesi",
    "OSC_REVERSAL": "Gösterge: aşırı satımdan dönüş", "MA_CROSS": "Gösterge: ortalama kesişimi",
    "MA_TREND_FLIP": "Gösterge: trend dönüşü", "BAND_VWAP": "Gösterge: bant / VWAP", "SD_ZONE": "Arz-talep bölgesi",
}
_SETUP_GRUP: dict[str, str] = {s: g for g, ss in GRUP_KURULUM.items() for s in ss}
ESKI_GRUP_AD = "Kaldırılan kollar (eski)"
DIGER_AD = "Diğer"

# sinav sonucu (26.11): tek yer; yeni sinavda yalniz burasi guncellenir. Baska sinav sayisi uydurulmaz.
SINAV = {"tarih": "2026-11-26", "esik_notu": True,
         "satirlar": (("4 saat + 1 gün", 0.110, "kazanıyor"), ("1 saat", 0.0, "başa baş"), ("15 dakika", -0.043, "kaybediyor"))}
_SINAV_RENK = {"kazanıyor": "yesil", "başa baş": "gri", "kaybediyor": "kirmizi"}

ZD_SIRA = ("15m", "1h", "4h", "1d")            # ekranda: once kanitli olanlar (JS), veri sirasi sabit
KANITLI_ZD = ("4h", "1d")
LIMIT_NEDENLERI = ("risk_denied", "max_positions", "entry_gate_closed")
AYNI_OLAY = "ml1_ayni_olay"
PAKET_YOK = "ml1_paket_yok"
OGRENME = "ogrenme"                            # features.ml1_neden: ogrenme asamasi (paket yok; aday puansiz gecer; ml1_skor yok)


# ----------------------------------------------------------------------------- adlar
def grup_kodu(setup: Any) -> str | None:
    """'T1@4h' / 'MF1-YUTAN' -> fikir grubu kodu; esleme yoksa (M1, DL1, HB1, C1 ve bilinmeyenler) None."""
    return _SETUP_GRUP.get(str(setup or "").partition("@")[0])


def grup_adi(kod: Any) -> str:
    """Grup kodu -> Turkce ad; bilinmeyen kod 'Diğer' (ham kod asla ekrana cikmaz)."""
    return GRUP_AD.get(str(kod or ""), DIGER_AD)


# ----------------------------------------------------------------------------- yardimcilar
def _f(x: Any) -> float | None:
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _gun_basi(now: datetime, geri: int = 0) -> datetime:
    """TSI gunu baslangici (UTC), `geri` gun oncesi."""
    d0 = now.astimezone(TR).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=geri)
    return d0.astimezone(timezone.utc)


def _feat(d: Any, key: str) -> Any:
    ft = getattr(d, "features", None)
    return ft.get(key) if isinstance(ft, Mapping) else None


def skor(d: Any) -> float | None:
    """Kararin ML1 puani (sonlu sayi degilse None: puanlanmamis)."""
    return _f(_feat(d, "ml1_skor"))


def ogrenme_mi(d: Any) -> bool:
    """Kayit ogrenme asamasinda (puansiz) ML1 kapisindan gecmis mi (`features.ml1_neden == "ogrenme"`)."""
    return _feat(d, "ml1_neden") == OGRENME


def ml1_mi(d: Any) -> bool:
    """ML1 kapisindan gecen kayit: puanli (suzme asamasi) YA DA ogrenme asamasi. Islem sayimlari bununla ayrilir (eski kol kaydi degil)."""
    return d is not None and (skor(d) is not None or ogrenme_mi(d))


def _nedenler(d: Any) -> set[str]:
    """Kararin red nedenleri (veto_reason ve skip_reason; 'gate:' oneki atilir)."""
    return {str(x).removeprefix("gate:") for x in (getattr(d, "veto_reason", None), getattr(d, "skip_reason", None)) if x}


def _istatistik(rows: Sequence[Any]) -> dict:
    """rows: kapanan islemler. n, kazanma (%), net_r, ort_r, kz. n == 0 -> sayilar None."""
    n = len(rows)
    if not n:
        return {"n": 0, "kazanma": None, "net_r": None, "ort_r": None, "kz": None}
    wins = sum(1 for t in rows if (t.realized_pnl or 0.0) > 0)
    net_r = math.fsum(r for r in (_f(t.r_multiple) for t in rows) if r is not None)
    return {"n": n, "kazanma": round(wins / n * 100.0, 1), "net_r": round(net_r, 4), "ort_r": round(net_r / n, 4),
            "kz": round(math.fsum(t.realized_pnl or 0.0 for t in rows), 4)}


def _toplam(rows: Sequence[Any]) -> dict:
    n = len(rows)
    return {"n": n, "net_r": round(math.fsum(r for r in (_f(t.r_multiple) for t in rows) if r is not None), 4),
            "kz": round(math.fsum(t.realized_pnl or 0.0 for t in rows), 4)}


def _tf_of(t: Any, d: Any) -> str:
    tf = str(getattr(d, "trigger_tf", "") or "")
    return tf or str(getattr(t, "setup", "") or "").partition("@")[2]


# ----------------------------------------------------------------------------- ozet
def ml1_ozet(decisions: Sequence[Any], closed: Sequence[Any], open_: Sequence[Any], now: datetime) -> dict:
    """Saf ozet: esik (kayittan), eleme (bugun / 7g), zaman dilimi tablosu, kanitli/kanitsiz toplamlari, ML1 toplami, ML1 oncesi islemler."""
    dec = {d.id: d for d in decisions}
    puanli = [d for d in decisions if skor(d) is not None]
    son = max(puanli, key=lambda d: d.bar_close_ts, default=None)
    esik = _f(_feat(son, "ml1_esik")) if son is not None else None

    def eleme(a: datetime) -> dict:
        sel = [d for d in puanli if d.bar_close_ts >= a]
        gecen = [d for d in sel if (e := _f(_feat(d, "ml1_esik"))) is not None and skor(d) >= e]
        islem = [d for d in sel if d.final_action == "entered"]
        alinmayan = {"ayni_olay": 0, "limit": 0, "diger": 0}
        for d in gecen:
            if d.final_action == "entered":
                continue
            r = _nedenler(d)
            alinmayan["ayni_olay" if AYNI_OLAY in r else ("limit" if r & set(LIMIT_NEDENLERI) else "diger")] += 1
        return {"puanlanan": len(sel), "gecen": len(gecen), "islem": len(islem),
                "gecme_yuzde": round(len(gecen) / len(sel) * 100.0, 1) if sel else None, "alinmayan": alinmayan}

    ml1_islem, eski = [], []
    for t in closed:
        if t.exit_ts is None:
            continue
        d = dec.get(t.decision_id)
        (ml1_islem if ml1_mi(d) else eski).append(t)
    acik_tf: dict[str, int] = {}
    for t in open_:
        d = dec.get(t.decision_id)
        if ml1_mi(d):
            tf = _tf_of(t, d)
            acik_tf[tf] = acik_tf.get(tf, 0) + 1
    zd = []
    for kod in ZD_SIRA:
        sel = [t for t in ml1_islem if _tf_of(t, dec.get(t.decision_id)) == kod]
        zd.append({"kod": kod, "ad": TS.zd_adi(kod), "kanitli": kod in KANITLI_ZD, **_istatistik(sel), "acik": acik_tf.get(kod, 0)})

    def ayri(rows: Sequence[Any]) -> dict:
        """kanitli (4s + 1g) / kanitsiz (15dk + 1s) toplamlari."""
        out = {}
        for k, kod in (("kanitli", KANITLI_ZD), ("kanitsiz", tuple(z for z in ZD_SIRA if z not in KANITLI_ZD))):
            sel = [t for t in rows if _tf_of(t, dec.get(t.decision_id)) in kod]
            out[k] = _toplam(sel)
        return out
    ozet = ayri(ml1_islem)
    ilk7 = _gun_basi(now, 6)

    def ogrenme(a: datetime) -> dict:
        """Ogrenme asamasinda (puansiz) kapidan gecen adaylar ve bunlardan acilan islemler."""
        sel = [d for d in decisions if ogrenme_mi(d) and d.bar_close_ts >= a]
        return {"aday": len(sel), "islem": sum(1 for d in sel if d.final_action == "entered")}
    tum = _istatistik(ml1_islem)
    return {"esik": esik, "ogrenme": {"bugun": ogrenme(_gun_basi(now)), "7g": ogrenme(ilk7)},
            "eleme": {"bugun": eleme(_gun_basi(now)), "7g": eleme(_gun_basi(now, 6))},
            "zd": zd, "zd_ozet": ozet, "zd_ozet_7g": ayri([t for t in ml1_islem if t.exit_ts >= ilk7]),
            "toplam": {k: tum[k] for k in ("n", "kazanma", "net_r", "kz")},
            "eski": {"n": len(eski), "kz": round(math.fsum(t.realized_pnl or 0.0 for t in eski), 4)} if eski else None}


# ----------------------------------------------------------------------------- fikir grubu tablosu
def _grup_adi_islem(t: Any, d: Any, *, eski_ayri: bool) -> str:
    kod = _feat(d, "ml1_grup") if d is not None else None
    kod = str(kod) if kod else grup_kodu(getattr(t, "setup", None))
    if kod is None:
        return ESKI_GRUP_AD if eski_ayri else DIGER_AD
    return grup_adi(kod)


def _grup_satirlari(pairs: Sequence[tuple[Any, Any]], *, eski_ayri: bool) -> list[dict]:
    by: dict[str, list[tuple[Any, Any]]] = {}
    for t, d in pairs:
        by.setdefault(_grup_adi_islem(t, d, eski_ayri=eski_ayri), []).append((t, d))
    out = []
    for ad, items in by.items():
        kol: dict[tuple[str, str], list[Any]] = {}
        for t, d in items:
            kol.setdefault((TS.kurulum_adi(getattr(t, "setup", None)), TS.zd_adi(_tf_of(t, d))), []).append(t)
        kollar = []
        for (kad, zf), ts in kol.items():
            st = _istatistik(ts)
            kollar.append({"kol": kad, "zd": zf, **{k: st[k] for k in ("n", "kazanma", "net_r", "kz")}})
        kollar.sort(key=lambda r: (-(r["net_r"] or 0.0), r["kol"], r["zd"]))
        st = _istatistik([t for t, _ in items])
        out.append({"grup": ad, **{k: st[k] for k in ("n", "kazanma", "net_r", "kz")}, "kollar": kollar})
    out.sort(key=lambda r: (r["grup"] == ESKI_GRUP_AD, -(r["net_r"] or 0.0), r["grup"]))
    return out


def gruplar(decisions: Sequence[Any], closed: Sequence[Any]) -> dict:
    """{"ml1": ML1'in aldigi islemler, "tumu": tum kapanan islemler}; yalniz islemi olan gruplar/kollar. 'Kaldirilan kollar (eski)'
    yalniz `tumu` icinde ve en sonda."""
    dec = {d.id: d for d in decisions}
    kap = [(t, dec.get(t.decision_id)) for t in closed if t.exit_ts is not None]
    ml1 = [(t, d) for t, d in kap if ml1_mi(d)]
    return {"ml1": _grup_satirlari(ml1, eski_ayri=False), "tumu": _grup_satirlari(kap, eski_ayri=True)}


# ----------------------------------------------------------------------------- durum rozeti ve sinav
def durum(decisions: Sequence[Any], now: datetime, aktif: Any) -> dict:
    """Ilk eslesen: ayarda kapali -> gri; son 24 saatte paket yok -> kirmizi; puanlanan var -> yesil; yoksa sari."""
    if aktif is not True:
        return {"metin": "Kapalı: adayları ML1 seçmiyor", "renk": "gri"}
    son24 = [d for d in decisions if d.bar_close_ts >= now - timedelta(hours=24)]
    if any(PAKET_YOK in _nedenler(d) for d in son24):
        return {"metin": "Sorun: ML1 modeli yüklenemedi; kural adayları atlanıyor", "renk": "kirmizi"}
    if any(skor(d) is not None for d in son24):
        return {"metin": "Açık: adayları ML1 seçiyor", "renk": "yesil"}
    if any(ogrenme_mi(d) for d in son24):
        return {"metin": "Öğrenme aşaması: model henüz yok, adaylar süzülmeden alınıyor", "renk": "sari"}
    return {"metin": "Açık: son 24 saatte puanlanacak aday çıkmadı", "renk": "sari"}


def sinav() -> dict:
    y, m, d = (int(x) for x in str(SINAV["tarih"]).split("-"))
    return {"tarih": f"{d:02d}.{m:02d}",
            "satirlar": [{"ad": ad, "ort_r": r, "sonuc": s, "renk": _SINAV_RENK.get(s, "gri")} for ad, r, s in SINAV["satirlar"]]}


# ----------------------------------------------------------------------------- Telegram metinleri (pano ile ayni sayilar)
def r_metni(x: Any) -> str:
    v = _f(x)
    return "—" if v is None else f"{TS.isaretli(v)} R"


def sinav_satiri() -> str:
    """'Sınav (26.11): 4s+1g +0,11 R · 1s ≈ 0 · 15dk −0,04 R' (/ml1)."""
    kisa = {"4 saat + 1 gün": "4s+1g", "1 saat": "1s", "15 dakika": "15dk"}
    sv = sinav()
    parcalar = [f"{kisa.get(r['ad'], r['ad'])} " + ("≈ 0" if abs(r["ort_r"]) < 0.005 else f"{TS.isaretli(r['ort_r'])} R")
                for r in sv["satirlar"]]
    return f"Sınav ({sv['tarih']}): " + " · ".join(parcalar)


def usd_metni(x: Any) -> str:
    v = _f(x)
    return "—" if v is None else f"{TS.isaretli(v)} $"


def ozet_satirlari(oz: Mapping, *, uzun: bool = True) -> tuple[str, str]:
    """('Sınavı geçen kısım (4s+1g): 6 işlem · +1,80 R · +14,10 $', 'Diğer (15dk+1s): ...') (Telegram haftalik ozet ve /ml1)."""
    out = []
    for ad, k in (("Sınavı geçen kısım (4s+1g)", "kanitli"), ("Diğer (15dk+1s)", "kanitsiz")):
        z = oz["zd_ozet"][k]
        out.append(f"{ad}: {z['n']} işlem · {r_metni(z['net_r'])}" + (f" · {usd_metni(z['kz'])}" if uzun else ""))
    return out[0], out[1]
