"""Strateji verisi raporu (beyin firtinasi icin): saf yardimcilar; YALNIZ OKUR, hesap uretir, markdown uretir.

Kaynak: kagit defteri (kapanan/acik islemler + `decision_events`), motor kagit yapilandirmasi (kollar), sunucudaki tutarlilik raporu
(`var/durum/tutarlilik_v1.json`) ve depoda yayimlanmis kagit-geri test bandi (docs/kagit-degerlendirme-plani.md §4.4). YENI geri
test hesaplanmaz. KILITLI DONEM (2026-05-01 -> 2026-11-01) kayitlari bu modulde de ayrica ayiklanir (kilit_disi).
Her sayi yaninda veri zamani (TSI) bulunur. Yorum/oneri yok: yalniz kisa yanit ve tablo.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from . import tg_sade as TS

TR = timezone(timedelta(hours=3))     # Europe/Istanbul (DST yok)
# trader_engine.holdout.HOLDOUT ile AYNI (katman geregi kopya; testte esitligi denetlenir)
KILIT_ACIK = True      # trader_engine.holdout.KILIT_ACIK kopyasi (23.11.2026 kullanici karari; parite testi)
KILIT = (datetime(2026, 5, 1, tzinfo=timezone.utc), datetime(2026, 11, 1, tzinfo=timezone.utc))
BASLIK = "Strateji verisi (beyin fırtınası için)"
DOSYA_ADI = "strateji-veri-ml.md"
REJIMLER = ("trend_up", "trend_down", "range", "unclear", "volatile")
HEDEFLER = (30, 100, 300)

# skip_reason -> grup (filtre / rejim / veri / esik / risk-limit)
SKIP_GRUP = {
    "ml_filter": "filtre", "ml_no_model": "filtre", "etiket_rejim": "rejim", "etiket_duygu": "filtre", "etiket_kalabalik": "filtre",
    "flat_bar": "veri", "arm_disabled": "filtre", "session_closed": "filtre", "llm_invalid": "veri", "entry_gate_closed": "veri",
    "order_failed": "veri", "other": "veri", "veto_blocked": "filtre", "veto_missing": "veri", "veto_stale": "veri",
    "stop_width": "eşik", "rr_below_min": "eşik",
    "risk_denied": "risk/limit", "max_positions": "risk/limit", "cluster_cap": "risk/limit", "arm_conflict": "risk/limit",
}

# docs/kagit-degerlendirme-plani.md §4.4 (referans R dizisinin durağan bootstrap'i; BAĞLAYICI tablo): n -> (%2,5, %10, ortanca, %90)
BANT_KAYNAK = "docs/kagit-degerlendirme-plani.md §4.4 (kümülatif net R, referans bootstrap bandı)"
BANT = {20: (-14.5, -11.1, -1.1, 16.9), 30: (-18.7, -14.1, -0.8, 22.0), 40: (-22.4, -16.4, -0.1, 25.9),
        50: (-25.6, -18.2, 0.5, 29.5), 75: (-32.1, -22.0, 1.9, 37.6), 100: (-37.0, -24.9, 4.0, 43.7),
        125: (-41.4, -27.4, 6.0, 50.5), 150: (-45.4, -29.1, 7.3, 56.3), 175: (-48.4, -30.9, 9.3, 60.9),
        200: (-51.6, -32.3, 11.2, 66.3), 250: (-57.7, -34.4, 15.3, 75.7), 300: (-61.0, -36.2, 19.1, 85.4)}


# ------------------------------------------------------------------------------------------------ zaman / bicim
def utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def kilit_disi(ts: datetime | None) -> bool:
    """True: zaman kilitli donemin (2026-05-01 <= t < 2026-11-01) DISINDA (kilit acikken zamani olan her kayit; KILIT_ACIK). Zamani olmayan kayit okunmaz sayilir (False)."""
    t = utc(ts)
    return t is not None and (KILIT_ACIK or not (KILIT[0] <= t < KILIT[1]))


def tsi(dt: datetime | None) -> str:
    t = utc(dt)
    return "yok" if t is None else t.astimezone(TR).strftime("%d.%m.%Y %H:%M") + " TSİ"


def veri(dt: datetime | None) -> str:
    return f"veri: {tsi(dt)}"


def para(x: float | None, nd: int = 2) -> str:
    if x is None:
        return "-"
    return ("-" if float(x) < 0 and round(abs(float(x)), nd) > 0 else "") + "$" + TS.sayi(x, nd)


def isp(x: float | None, nd: int = 2) -> str:
    """Isaretli para: +$1,20 / -$3,00."""
    if x is None:
        return "-"
    return ("-" if float(x) < 0 and round(abs(float(x)), nd) > 0 else "+") + "$" + TS.sayi(x, nd)


def rr(x: float | None, nd: int = 2) -> str:
    if x is None:
        return "-"
    return ("-" if float(x) < 0 and round(abs(float(x)), nd) > 0 else "+") + TS.sayi(x, nd) + " R"


def yuzde(x: float | None, nd: int = 1) -> str:
    return "-" if x is None else "%" + TS.sayi(100.0 * x, nd)


def tablo(baslik: Sequence[str], satirlar: Iterable[Sequence[Any]]) -> list[str]:
    out = ["| " + " | ".join(baslik) + " |", "|" + "|".join("---" for _ in baslik) + "|"]
    for s in satirlar:
        out.append("| " + " | ".join(str(c).replace("|", "/") for c in s) + " |")
    return out


# ------------------------------------------------------------------------------------------------ adaptorler
def kol_id(setup: Any, tf: Any, arm_id: Any = None) -> str:
    """Kol kimligi: arm_id ya da setup@trigger_tf ('T1@1h')."""
    a = str(arm_id or "").strip()
    if a:
        return a
    s = str(setup or "?")
    return s if "@" in s or not tf else f"{s}@{tf}"


def islem_satirlari(kapali: Iterable[Any], acik: Iterable[Any], kararlar_by_id: Mapping[int, Any]) -> list[dict]:
    """Defter TradeRecord'larindan duz satirlar (kilitli donemde giris/cikis yapanlar atilir). `kapali` bool ve ts alanlari dahil."""
    out: list[dict] = []
    for closed, lst in ((True, kapali), (False, acik)):
        for t in lst:
            if not kilit_disi(t.entry_ts) or (closed and not kilit_disi(t.exit_ts)):
                continue
            d = kararlar_by_id.get(t.decision_id)
            tf = getattr(d, "trigger_tf", None)
            arm = kol_id(t.setup, tf, getattr(d, "arm_id", None))
            slip = 0.0
            if t.slippage_entry is not None:
                slip += float(t.slippage_entry) * float(t.planned_entry) * float(t.qty)
            if closed and t.slippage_exit is not None and t.planned_exit is not None:
                slip += float(t.slippage_exit) * float(t.planned_exit) * float(t.qty)
            out.append({"id": t.trade_id, "arm": arm, "side": str(t.side), "regime": str(t.regime or "?"), "kapali": closed,
                        "giris": utc(t.entry_ts), "cikis": utc(t.exit_ts) if closed else None,
                        "net": float(t.realized_pnl) if closed else None, "brut": float(t.gross_pnl) if closed else None,
                        "r": float(t.r_multiple) if closed else None,
                        "komisyon": float(t.fee_entry or 0.0) + (float(t.fee_exit or 0.0) if closed else 0.0),
                        "fonlama": float(t.funding_paid or 0.0) if closed else 0.0, "kayma": slip})
    return out


def _sda(feats: Any) -> float | None:
    try:
        v = float(feats["stop_dist_atr"])
    except (TypeError, KeyError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def karar_satirlari(kararlar: Iterable[Any]) -> list[dict]:
    out = []
    for d in kararlar:
        if not kilit_disi(d.bar_close_ts):
            continue
        out.append({"arm": kol_id(d.setup, d.trigger_tf, getattr(d, "arm_id", None)), "side": str(d.side), "regime": str(d.regime),
                    "girdi": d.final_action == "entered", "skip": d.skip_reason, "ts": utc(d.bar_close_ts),
                    "risk": getattr(d, "risk_reason", None), "veto": getattr(d, "veto_reason", None),
                    "sda": _sda(getattr(d, "features", None))})
    return out


def _son(ts: Iterable[datetime | None]) -> datetime | None:
    v = [t for t in ts if t is not None]
    return max(v) if v else None


def _kz(t: Mapping) -> float:
    return float(t["net"])


# ------------------------------------------------------------------------------------------------ bolumler
def ortak1(kap: Sequence[Mapping]) -> dict:
    n = len(kap)
    kaz = [t for t in kap if t["net"] > 0]
    kay = [t for t in kap if t["net"] <= 0]

    def ort(xs, k):
        return sum(x[k] for x in xs) / len(xs) if xs else None
    return {"veri": _son(t["cikis"] for t in kap), "n": n, "net": sum(_kz(t) for t in kap), "kazanan": len(kaz),
            "oran": (len(kaz) / n) if n else None, "ort_kazanc_r": ort(kaz, "r"), "ort_kayip_r": ort(kay, "r"),
            "ort_kazanc_usd": ort(kaz, "net"), "ort_kayip_usd": ort(kay, "net"), "toplam_r": sum(t["r"] for t in kap)}


def ortak2(kap: Sequence[Mapping]) -> dict:
    s = sorted(kap, key=lambda t: (-t["net"], t["id"]))
    net = sum(_kz(t) for t in s)
    n = len(s)

    def pay(k):
        return (sum(t["net"] for t in s[:k]) / net) if n >= k and net > 0 else None
    d = {"veri": _son(t["cikis"] for t in kap), "n": n, "net": net, "pay1": pay(1), "pay2": pay(2),
         "top1": s[0]["net"] if n else None, "top2": sum(t["net"] for t in s[:2]) if n >= 2 else None,
         "en_iyi3_cikar": None, "en_kotu3_cikar": None, "ikisi_cikar": None}
    if n >= 4:
        d["en_iyi3_cikar"] = net - sum(t["net"] for t in s[:3])
        d["en_kotu3_cikar"] = net - sum(t["net"] for t in s[-3:])
    if n >= 7:
        d["ikisi_cikar"] = net - sum(t["net"] for t in s[:3]) - sum(t["net"] for t in s[-3:])
    return d


def ortak3(kap: Sequence[Mapping]) -> dict:
    brut_kar = sum(t["brut"] for t in kap if t["brut"] > 0)
    brut = sum(t["brut"] for t in kap)
    kom, fon, kay = (sum(t[k] for t in kap) for k in ("komisyon", "fonlama", "kayma"))

    def o(x, b):
        return (x / b) if b > 0 else None
    return {"veri": _son(t["cikis"] for t in kap), "brut_kar": brut_kar, "brut": brut, "komisyon": kom, "fonlama": fon, "kayma": kay,
            "kom_fon_oran": o(kom + fon, brut_kar), "toplam_oran": o(kom + fon + kay, brut_kar), "net": sum(_kz(t) for t in kap)}


def ortak6(kap: Sequence[Mapping]) -> list[dict]:
    g: dict[str, list] = defaultdict(list)
    for t in kap:
        g[t["regime"]].append(t)
    sira = list(REJIMLER) + sorted(r for r in g if r not in REJIMLER)
    out = []
    for r in sira:
        xs = g.get(r, [])
        out.append({"rejim": r, "n": len(xs), "net": sum(t["net"] for t in xs), "oran": (sum(1 for t in xs if t["net"] > 0) / len(xs)) if xs else None,
                    "veri": _son(t["cikis"] for t in xs)})
    return out


def ortak7(kap: Sequence[Mapping], tum: Sequence[Mapping], baslangic: datetime | None, kesit: datetime | None,
           kollar: Sequence[str]) -> dict:
    """Hiz = kapanan / gun (ilk girisden veri kesitine). Ulasma: kalan / hiz. Kol medyani: kapanan islemi olan kollarin kol-basi hizlarinin medyani."""
    gun = ((kesit - baslangic).total_seconds() / 86400.0) if (kesit and baslangic) else 0.0
    n = len(kap)
    hiz = (n / gun) if gun > 0 else None
    per = Counter(t["arm"] for t in kap)
    hizlar = [c / gun for c in per.values()] if gun > 0 else []
    med_var = statistics.median(hizlar) if hizlar else None
    tum_hiz = sorted([per.get(a, 0) / gun for a in kollar] + [c / gun for a, c in per.items() if a not in kollar]) if gun > 0 else []
    med_tum = statistics.median(tum_hiz) if tum_hiz else None
    satir = []
    for h in HEDEFLER:
        def eta(kalan, v):
            if kalan <= 0:
                return "ulaşıldı"
            if not v:
                return "hesaplanamaz (hız 0)"
            d = kalan / v
            return f"{TS.sayi(d, 0)} gün ({TS.sayi(d / 7, 1)} hafta)"
        satir.append({"hedef": h, "genel": eta(h - n, hiz),
                      "kol_medyan_var": eta(h - 0, med_var),            # kol-basi: medyan kolun kendi hizi ile 0'dan hedefe
                      "kol_medyan_tum": eta(h, med_tum),
                      "kol_ulasan": sum(1 for c in per.values() if c >= h)})
    return {"veri": kesit, "baslangic": baslangic, "gun": gun, "n": n, "hiz": hiz, "med_var": med_var, "med_tum": med_tum,
            "kol_sayisi_islemli": len(per), "kol_sayisi_yapilandirma": len(kollar), "satirlar": satir}


# risk.py `_deny` metni (onek) -> limit adi (rapor etiketi)
RISK_LIMIT = (("toplam açık risk", "max_open_risk"), ("aynı yön", "max_same_dir_risk"), ("günlük zarar bütçesi", "daily_max_loss"),
              ("günlük sınır aşıldı", "daily_limit"), ("toplam teminat", "margin_total"), ("likidasyon çok yakın", "liquidation"),
              ("boyutlandırma reddedildi", "sizing"), ("zaten açık pozisyon", "pair_already_open"), ("kaldıraç aralık", "leverage_range"),
              ("stop yanlış tarafta", "stop_side"), ("geçersiz girdi", "invalid_input"),
              ("korelasyon grubu sınırı", "korelasyon_grubu"), ("toplam büyüklük tavanı", "toplam_buyukluk"),
              ("kayıp freni okunamadı", "fren_okunamadi"), ("toplam büyüklük okunamadı", "buyukluk_okunamadi"))
PENCERE_SAAT = 12


def risk_limiti(reason: Any) -> str:
    r = str(reason or "").strip()
    for pre, ad in RISK_LIMIT:
        if r.startswith(pre) or (pre == "zaten açık pozisyon" and pre in r):
            return ad
    return "diğer" if r else "?"


def _kol_taniyor(kazanan: str, kollar: Sequence[str] | None) -> bool:
    """Kazanan, yapilandirilmis kollardan biri (ya da kurulum adi) mi? `kollar` None => filtre yok. Kaldirilan kollar raporda gorunmez."""
    if kollar is None:
        return True
    return kazanan in kollar or any(k.partition("@")[0] == kazanan for k in kollar)


def skip_detay(d: Mapping, kollar: Sequence[str] | None = None) -> tuple[str, str | None]:
    """(skip_reason, ayrinti): risk_denied -> risk limiti adi; max_positions -> arm_max_positions|max_positions; cluster_cap -> kume;
    arm_conflict -> kazanan kol (veto_reason `gate:arm_conflict:<kazanan>`); digerleri ayrintisiz."""
    sk = d.get("skip") or "?"
    veto = str(d.get("veto") or "")
    if sk == "risk_denied":
        return sk, risk_limiti(d.get("risk"))
    if sk == "max_positions":
        return sk, "arm_max_positions" if veto.startswith("gate:arm_cap:") else "max_positions"
    if sk == "cluster_cap":
        return sk, veto.split(":", 2)[2] if veto.count(":") >= 2 else "cluster"
    if sk == "arm_conflict":
        if veto.count(":") >= 2:
            kazanan = veto.split(":", 2)[2]
            return sk, (kazanan if _kol_taniyor(kazanan, kollar) else None)     # kaldirilan kol: sayi kalir, ad gosterilmez
        return sk, "kazanan kayıtlı değil"
    return sk, None


def _pencere(arm: str, kararlar: Sequence[Mapping], kollar: Sequence[str] | None = None) -> dict:
    skip: Counter = Counter()
    det: dict[str, Counter] = defaultdict(Counter)
    aday = girdi = 0
    for d in kararlar:
        if d["arm"] != arm:
            continue
        aday += 1
        if d["girdi"]:
            girdi += 1
            continue
        sk, ay = skip_detay(d, kollar)
        skip[sk] += 1
        if ay:
            det[sk][ay] += 1
    return {"aday": aday, "girdi": girdi, "skip": skip, "detay": det}


def ml8(kollar: Sequence[str], tum: Sequence[Mapping], kararlar: Sequence[Mapping], kesit: datetime | None = None) -> dict:
    islem = Counter(t["arm"] for t in tum)
    girdi = Counter(d["arm"] for d in kararlar if d["girdi"])
    karar_n = Counter(d["arm"] for d in kararlar)
    acan = [a for a in kollar if islem.get(a, 0) > 0 or girdi.get(a, 0) > 0]
    acmayan = [a for a in kollar if a not in acan]
    skip: dict[str, Counter] = defaultdict(Counter)
    for d in kararlar:
        if d["arm"] in acmayan and not d["girdi"]:
            skip[d["arm"]][d["skip"] or "?"] += 1
    kes = kesit or _son(d["ts"] for d in kararlar)
    son = [d for d in kararlar if kes and d["ts"] >= kes - timedelta(hours=PENCERE_SAAT)]
    kol_detay = [{"arm": a, "tum": _pencere(a, kararlar, kollar), "son": _pencere(a, son, kollar)} for a in kollar]
    return {"veri": _son(d["ts"] for d in kararlar), "toplam": len(kollar), "acan": acan, "acmayan": acmayan, "kes": kes,
            "kol_detay": kol_detay, "aday_yok_tum": [r["arm"] for r in kol_detay if r["tum"]["aday"] == 0],
            "aday_yok_son": [r["arm"] for r in kol_detay if r["son"]["aday"] == 0 and r["tum"]["aday"] > 0],
            "yapilandirma_disi": sorted(a for a in islem if a not in kollar),
            "satirlar": [{"arm": a, "aday": karar_n.get(a, 0), "skip": skip.get(a, Counter()),
                          "son": _son(d["ts"] for d in kararlar if d["arm"] == a)} for a in acmayan]}


def stop_genislik(kollar: Sequence[str], kararlar: Sequence[Mapping], kesit: datetime | None = None) -> list[dict]:
    """Yalniz olcum: kol basina `stop_width` skip'leri (son PENCERE_SAAT saat / tum kayit): dar (stop/ATR < bant alti) ve genis
    (> bant ustu) sayisi ile reddedilen adaylarin medyan stop/ATR'si. Red tarafi kayitli degil; `features.stop_dist_atr`
    bant sinirlariyla (signals.STOP_DIST_MIN_ATR/MAX_ATR) karsilastirilarak turetilir. Davranis degismez."""
    from .signals import STOP_DIST_MAX_ATR, STOP_DIST_MIN_ATR
    kes = kesit or _son(d["ts"] for d in kararlar)
    out = []
    for a in kollar:
        sw = [d for d in kararlar if d["arm"] == a and d["skip"] == "stop_width"]
        row = {"arm": a, "bant": (STOP_DIST_MIN_ATR, STOP_DIST_MAX_ATR)}
        for ad, rows in (("tum", sw), ("son", [d for d in sw if kes and d["ts"] >= kes - timedelta(hours=PENCERE_SAAT)])):
            v = [d.get("sda") for d in rows if d.get("sda") is not None]
            dar = [x for x in v if x < STOP_DIST_MIN_ATR]
            gen = [x for x in v if x > STOP_DIST_MAX_ATR]
            row[ad] = {"n": len(rows), "dar": len(dar), "genis": len(gen), "belirsiz": len(rows) - len(dar) - len(gen),
                       "medyan": statistics.median(v) if v else None}
        out.append(row)
    return out


def ml10(kollar: Sequence[str], kap: Sequence[Mapping]) -> list[dict]:
    g: dict[str, list] = defaultdict(list)
    for t in kap:
        g[t["arm"]].append(t)
    out = []
    for a in list(kollar) + sorted(x for x in g if x not in kollar):
        xs = g.get(a, [])
        net = sum(t["net"] for t in xs)
        out.append({"arm": a, "n": len(xs), "net": net, "r": sum(t["r"] for t in xs),
                    "oran": (sum(1 for t in xs if t["net"] > 0) / len(xs)) if xs else None,
                    "zarar": bool(xs) and net < 0, "veri": _son(t["cikis"] for t in xs)})
    out.sort(key=lambda r: (r["n"] == 0, r["net"], r["arm"]))
    return out


def yon_ozet(kap: Sequence[Mapping], kararlar: Sequence[Mapping]) -> dict:
    def blok(xs):
        return {"n": len(xs), "net": sum(t["net"] for t in xs), "oran": (sum(1 for t in xs if t["net"] > 0) / len(xs)) if xs else None,
                "r": sum(t["r"] for t in xs), "veri": _son(t["cikis"] for t in xs)}
    genel = {s: blok([t for t in kap if t["side"] == s]) for s in ("long", "short")}
    rej = {}
    for r in list(REJIMLER) + sorted({t["regime"] for t in kap} - set(REJIMLER)):
        rej[r] = {s: blok([t for t in kap if t["side"] == s and t["regime"] == r]) for s in ("long", "short")}
    return {"genel": genel, "rejim": rej, "veri": _son(t["cikis"] for t in kap)}


def guncel_rejim(kararlar: Sequence[Mapping]) -> tuple[str | None, datetime | None, int]:
    """Son karar zamanindan geriye 24 saatteki en sik rejim (esitlikte REJIMLER sirasi). (rejim, son karar zamani, ornek sayisi)."""
    if not kararlar:
        return None, None, 0
    son = max(d["ts"] for d in kararlar)
    c = Counter(d["regime"] for d in kararlar if d["ts"] > son - timedelta(hours=24))
    sira = {r: i for i, r in enumerate(REJIMLER)}
    r = sorted(c, key=lambda k: (-c[k], sira.get(k, 99), k))[0]
    return r, son, sum(c.values())


def ml11(kararlar: Sequence[Mapping], kollar: Sequence[str]) -> dict:
    rejim, son, n24 = guncel_rejim(kararlar)
    longs = [d for d in kararlar if d["side"] == "long"]
    kaps = sorted({d["arm"] for d in longs}, key=lambda a: (kollar.index(a) if a in kollar else 999, a))
    satir = []
    for a in kaps:
        la = [d for d in longs if d["arm"] == a]
        lr = [d for d in la if d["regime"] == rejim]
        satir.append({"arm": a, "aday": len(lr), "alinan": sum(1 for d in lr if d["girdi"]),
                      "aday_toplam": len(la), "alinan_toplam": sum(1 for d in la if d["girdi"]), "son": _son(d["ts"] for d in la)})
    return {"rejim": rejim, "veri": son, "n24": n24, "satirlar": satir,
            "aday": sum(r["aday"] for r in satir), "alinan": sum(r["alinan"] for r in satir)}


def bant_satiri(n: int, toplam_r: float) -> dict:
    """Yayimlanmis kumulatif-R bandi: n < 20 yetersiz; n > 300 yok; aradeger dogrusal. Donus: konum etiketi."""
    if n < 20:
        return {"durum": "yetersiz", "etiket": f"n={n} < 20: band için yetersiz"}
    if n > 300:
        return {"durum": "yok", "etiket": "n > 300: yayımlanmış band yok"}
    ks = sorted(BANT)
    alt = max(k for k in ks if k <= n)
    ust = min(k for k in ks if k >= n)
    w = 0.0 if ust == alt else (n - alt) / (ust - alt)
    b = tuple(BANT[alt][i] + w * (BANT[ust][i] - BANT[alt][i]) for i in range(4))
    if toplam_r < b[0]:
        k = "%2,5 altında"
    elif toplam_r < b[1]:
        k = "%2,5-%10 arası"
    elif toplam_r <= b[3]:
        k = "%10-%90 arası (bant içinde)"
    else:
        k = "%90 üstünde"
    return {"durum": "var", "n": n, "bant": b, "etiket": k}


def ml12(kap: Sequence[Mapping], tutarlilik: Mapping | None, tut_veri: datetime | None) -> dict:
    top_r = sum(t["r"] for t in kap)
    kur = []
    for k in (tutarlilik or {}).get("kurulumlar") or []:
        try:
            kn, bn = int(k.get("kagit_islem") or 0), int(k.get("bt_islem") or 0)
            kr, br = float(k.get("kagit_R")), float(k.get("bt_R"))
        except (TypeError, ValueError):
            continue
        kur.append({"ad": str(k.get("ad")), "kagit_n": kn, "bt_n": bn, "kagit_rt": (kr / kn) if kn else None,
                    "bt_rt": (br / bn) if bn else None, "eslesme": k.get("eslesme_orani")})
    return {"genel": bant_satiri(len(kap), top_r), "toplam_r": top_r, "n": len(kap), "veri": _son(t["cikis"] for t in kap),
            "tutarlilik": kur, "tutarlilik_donem": (tutarlilik or {}).get("donem"), "tut_veri": tut_veri,
            "tut_uyari": (tutarlilik or {}).get("uyari"), "tut_not": (tutarlilik or {}).get("not")}


def mekanizmalar(kollar: Sequence[str], arms_off: Mapping[str, Mapping] | None, fren: bool | None,
                 kapali_kolu_zarar: Sequence[str]) -> list[dict]:
    """Kaybeden kollar icin mevcut mekanizmalar (kod/yapilandirmadan) ve tetiklenip tetiklenmedigi (okunabilen durum dosyasindan)."""
    kapali = sorted(a for a, s in (arms_off or {}).items() if str(s.get("state")) == "closed")
    return [
        {"ad": "Ders: kol kapatma (arms_off)", "var": "var", "etki": "yalnız karne/rapor bilgisi; giriş ENGELLENMEZ (sahip kararı, 19 Kasım; gates.py `arm_would_close` sayacı)",
         "tetik": ("tetiklendi: " + ", ".join(kapali)) if kapali else "tetiklenmedi (arms_off kaydı yok/boş)"},
        {"ad": "Ders: 10 R freni (lesson_brake)", "var": "var", "etki": "ders ayarlarını referansa döndürür, otomatik uygulamayı durdurur; kolu kapatmaz",
         "tetik": "tetiklendi" if fren else ("tetiklenmedi" if fren is not None else "durum okunamadı")},
        {"ad": "Kol başına açık pozisyon tavanı (arm_max_positions) ve küme/hesap tavanı", "var": "var",
         "etki": "kayıptan bağımsız konum sınırı; zarardaki kolu özel olarak ayırmaz", "tetik": "kayıp temelli tetik değil"},
        {"ad": "Risk kademe denetimi (risk_ladder, hesap düzeyi küçültme)", "var": "var (hesap düzeyi; kol düzeyi değil)",
         "etki": "tepe-denge düşüşünde hedef işlem riskini kademeli düşürür / durdurur; motor zorunlu yalnız canlı modda",
         "tetik": "kâğıt ayarında LADDER_BOTS boş; kâğıtta kademe izlenmez"},
        {"ad": "Kol bazında otomatik karantina / boyut küçültme", "var": "yok",
         "etki": f"zararda kol: {', '.join(kapali_kolu_zarar) if kapali_kolu_zarar else 'yok'}; bu kolları kendiliğinden kısan kural yok", "tetik": "-"},
    ]


# ------------------------------------------------------------------------------------------------ rapor
def hesapla(*, kollar: Sequence[str], islemler: Sequence[Mapping], kararlar: Sequence[Mapping], simdi: datetime,
            tutarlilik: Mapping | None = None, tut_veri: datetime | None = None, arms_off: Mapping | None = None,
            fren: bool | None = None, atlanan: int = 0) -> dict:
    kap = [t for t in islemler if t["kapali"]]
    baslangic = min([t["giris"] for t in islemler] + [d["ts"] for d in kararlar], default=None)
    kesit = _son([t["cikis"] for t in kap] + [t["giris"] for t in islemler] + [d["ts"] for d in kararlar])
    o10 = ml10(kollar, kap)
    return {"simdi": simdi, "baslangic": baslangic, "kesit": kesit, "kap_n": len(kap), "acik_n": len(islemler) - len(kap),
            "karar_n": len(kararlar), "atlanan_kilit": atlanan, "kollar": list(kollar),
            "o1": ortak1(kap), "o2": ortak2(kap), "o3": ortak3(kap), "o6": ortak6(kap),
            "o7": ortak7(kap, islemler, baslangic, kesit, kollar), "m8": ml8(kollar, islemler, kararlar, kesit),
            "sw": stop_genislik(kollar, kararlar, kesit), "m10": o10,
            "mek": mekanizmalar(kollar, arms_off, fren, [r["arm"] for r in o10 if r["zarar"]]),
            "yon": yon_ozet(kap, kararlar), "m11": ml11(kararlar, kollar), "m12": ml12(kap, tutarlilik, tut_veri)}


def markdown(d: Mapping) -> str:
    L: list[str] = []
    a = L.append
    o1, o2, o3, o7, m8, m11, m12, yon = d["o1"], d["o2"], d["o3"], d["o7"], d["m8"], d["m11"], d["m12"], d["yon"]
    a(f"# [ML] {BASLIK}")
    a("")
    a(f"Üretim: {tsi(d['simdi'])} · Kâğıt başlangıcı (ilk kayıt): {tsi(d['baslangic'])} · Veri kesiti: {tsi(d['kesit'])}")
    a(f"Kapanan işlem: {d['kap_n']} · Açık işlem: {d['acik_n']} · Karar kaydı: {d['karar_n']} · Yapılandırılmış kol: {len(d['kollar'])}")
    a("Kapsam: yalnız kâğıt defteri (salt okunur). Kilitli dönem (01.05.2026-01.11.2026) kayıtları okunmadı/ayıklandı "
      f"(ayıklanan kayıt: {d['atlanan_kilit']}). Yeni geri test hesaplanmadı. Yorum/öneri yok.")
    a("")
    a("## Ortak 1 — Kâğıt başlangıcından beri sonuç")
    a("")
    L += tablo(["Ölçü", "Değer", "Veri"], [
        ["Net K/Z", isp(o1["net"]), veri(o1["veri"])], ["İşlem sayısı (kapanan)", o1["n"], veri(o1["veri"])],
        ["Kazanma oranı (net > 0)", yuzde(o1["oran"]), veri(o1["veri"])],
        ["Ort. kazanç", f"{rr(o1['ort_kazanc_r'])} / {isp(o1['ort_kazanc_usd'])}", veri(o1["veri"])],
        ["Ort. kayıp", f"{rr(o1['ort_kayip_r'])} / {isp(o1['ort_kayip_usd'])}", veri(o1["veri"])],
        ["Toplam R", rr(o1["toplam_r"]), veri(o1["veri"])]])
    a("")
    a("## Ortak 2 — K/Z yoğunlaşması")
    a("")
    L += tablo(["Ölçü", "Değer", "Veri"], [
        ["En iyi 1 işlemin net içindeki payı", yuzde(o2["pay1"]) + (f" ({isp(o2['top1'])})" if o2["top1"] is not None else ""), veri(o2["veri"])],
        ["En iyi 2 işlemin net içindeki payı", yuzde(o2["pay2"]) + (f" ({isp(o2['top2'])})" if o2["top2"] is not None else ""), veri(o2["veri"])],
        ["En iyi 3 çıkarılınca net", isp(o2["en_iyi3_cikar"]), veri(o2["veri"])],
        ["En kötü 3 çıkarılınca net", isp(o2["en_kotu3_cikar"]), veri(o2["veri"])],
        ["En iyi 3 + en kötü 3 çıkarılınca net", isp(o2["ikisi_cikar"]), veri(o2["veri"])]])
    a("")
    a("Pay: net > 0 iken hesaplanır; yetersiz işlemde (en iyi/kötü 3 için < 4, ikisi birden < 7) '-'.")
    a("")
    a("## Ortak 3 — Maliyetler")
    a("")
    L += tablo(["Kalem", "Tutar", "Brüt kâra oranı", "Veri"], [
        ["Brüt kâr (yalnız brüt > 0 olan işlemlerin toplamı)", para(o3["brut_kar"]), "-", veri(o3["veri"])],
        ["Toplam brüt K/Z (tüm işlemler)", isp(o3["brut"]), "-", veri(o3["veri"])],
        ["Komisyon", para(o3["komisyon"]), yuzde(o3["komisyon"] / o3["brut_kar"] if o3["brut_kar"] > 0 else None), veri(o3["veri"])],
        ["Fonlama (ödenen)", isp(o3["fonlama"]), yuzde(o3["fonlama"] / o3["brut_kar"] if o3["brut_kar"] > 0 else None), veri(o3["veri"])],
        ["Komisyon + fonlama", para(o3["komisyon"] + o3["fonlama"]), yuzde(o3["kom_fon_oran"]), veri(o3["veri"])],
        ["Kayma (giriş+çıkış, planlanana göre; brüte ZATEN işlenmiştir)", isp(o3["kayma"]), yuzde(o3["kayma"] / o3["brut_kar"] if o3["brut_kar"] > 0 else None), veri(o3["veri"])],
        ["Komisyon + fonlama + kayma", para(o3["komisyon"] + o3["fonlama"] + o3["kayma"]), yuzde(o3["toplam_oran"]), veri(o3["veri"])]])
    a("")
    a("Net K/Z = brüt - komisyon - fonlama (kayma fiyatlara işlendiğinden ayrıca düşülmez).")
    a("")
    a("## Ortak 6 — Girişteki piyasa rejimine göre sonuç")
    a("")
    L += tablo(["Rejim", "İşlem", "Net K/Z", "Kazanma", "Veri"],
               [[r["rejim"], r["n"], isp(r["net"]) if r["n"] else "-", yuzde(r["oran"]), veri(r["veri"]) if r["n"] else "veri: işlem yok"] for r in d["o6"]])
    a("")
    a("## Ortak 7 — 30 / 100 / 300 kapanan işleme ulaşma süresi")
    a("")
    hz = "-" if o7["hiz"] is None else f"{TS.sayi(o7['hiz'], 2)} işlem/gün"
    mv = "-" if o7["med_var"] is None else f"{TS.sayi(o7['med_var'], 3)} işlem/gün"
    mt = "-" if o7["med_tum"] is None else f"{TS.sayi(o7['med_tum'], 3)} işlem/gün"
    a(f"Süre: {TS.sayi(o7['gun'], 1)} gün ({tsi(o7['baslangic'])} → {tsi(o7['veri'])}); kapanan {o7['n']}; genel hız {hz}; "
      f"kol medyan hızı: işlemi olan {o7['kol_sayisi_islemli']} kol {mv}, tüm {o7['kol_sayisi_yapilandirma']} yapılandırılmış kol {mt} ({veri(o7['veri'])}).")
    a("")
    L += tablo(["Hedef", "Genel (güncel hızla)", "Kol medyanı (işlemi olan kollar)", "Kol medyanı (tüm kollar)", "Hedefe ulaşan kol", "Veri"],
               [[s["hedef"], s["genel"], s["kol_medyan_var"], s["kol_medyan_tum"], s["kol_ulasan"], veri(o7["veri"])] for s in o7["satirlar"]])
    a("")
    a("## ML 8 — Yapılandırılmış kollar: işlem açan / açmayan")
    a("")
    a(f"Yapılandırılmış kol: {m8['toplam']} · ≥1 işlem açan: {len(m8['acan'])} · hiç açmayan: {len(m8['acmayan'])} ({veri(m8['veri'])})")
    if m8["yapilandirma_disi"]:
        a(f"Yapılandırma dışı kolda işlem: {', '.join(m8['yapilandirma_disi'])}")
    a("")
    if m8["acmayan"]:
        satir = []
        for s in m8["satirlar"]:
            top = ", ".join(f"{k}={v}" for k, v in s["skip"].most_common(5)) or "-"
            grup = Counter()
            for k, v in s["skip"].items():
                grup[SKIP_GRUP.get(k, "diğer")] += v
            gs = ", ".join(f"{k}={v}" for k, v in grup.most_common()) or "-"
            satir.append([s["arm"], s["aday"] if s["aday"] else "0 (aday üretmedi)", top, gs, veri(s["son"]) if s["aday"] else veri(m8["veri"])])
        L += tablo(["Kol", "Aday (karar kaydı)", "En sık skip_reason", "Grup (filtre/rejim/veri/eşik/risk-limit)", "Veri"], satir)
        a("")
    a("Açan kollar: " + (", ".join(m8["acan"]) or "yok"))
    a("")
    a(f"### Kol bazında neden işlem açmıyor (tüm kayıt / son {PENCERE_SAAT} saat)")
    a("")
    a(f"Pencere: «tüm kayıt» = kilitli dönem dışındaki tüm karar satırları; «son {PENCERE_SAAT} saat» = veri kesitinden ({tsi(m8['kes'])}) geriye {PENCERE_SAAT} saat. "
      "Kâğıt risk limitleri kayıt süresince gevşetilmiş olabilir; eski `risk_denied` sayıları o günkü limitlere aittir, güncel durumu "
      f"«son {PENCERE_SAAT} saat» sütunları gösterir. Risk reddi `risk_reason` metninden limit adına çevrilir (max_open_risk, max_same_dir_risk, daily_max_loss ...).")
    a("")

    def hucre(w: Mapping) -> str:
        parcalar = []
        for k, v in w["skip"].most_common():
            ay = w["detay"].get(k)
            if ay:
                parcalar.append(f"{k}={v} ({', '.join(f'{x}={y}' for x, y in ay.most_common())})")
            else:
                parcalar.append(f"{k}={v}")
        return "; ".join(parcalar) or "-"

    L += tablo(["Kol", "Aday (tüm)", "Girdi (tüm)", "Skip (tüm)", f"Aday ({PENCERE_SAAT}s)", f"Girdi ({PENCERE_SAAT}s)", f"Skip ({PENCERE_SAAT}s)", "Veri"],
               [[r["arm"], r["tum"]["aday"], r["tum"]["girdi"], hucre(r["tum"]), r["son"]["aday"], r["son"]["girdi"], hucre(r["son"]), veri(m8["kes"])]
                for r in m8["kol_detay"]])
    a("")
    a("Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta " + (", ".join(m8["aday_yok_tum"]) or "yok")
      + f" · yalnız son {PENCERE_SAAT} saatte " + (", ".join(m8["aday_yok_son"]) or "yok") + ".")
    a("")
    a("Aday = `decision_events` satırı. Golge kararlar (shadow) ve hiç kayda girmeyen sinyaller bu sayıya girmez.")
    a("")
    a(f"### stop_width skip'leri: dar / geniş (son {PENCERE_SAAT} saat / tüm kayıt)")
    a("")
    bant = d["sw"][0]["bant"] if d.get("sw") else (None, None)
    a(f"İzinli bant: stop/ATR {bant[0]} – {bant[1]} (signals.STOP_DIST_MIN_ATR / STOP_DIST_MAX_ATR). Yalnız ölçüm; davranış değişmez. "
      "Dar/geniş ayrımı kayıtlı `features.stop_dist_atr` değerinin banta göre karşılaştırılmasından türetilir; medyan = reddedilen adayların medyan stop/ATR'si.")
    a("")

    def sw_hucre(w: Mapping) -> str:
        if not w["n"]:
            return "-"
        med = f"{w['medyan']:.2f}" if w["medyan"] is not None else "?"
        return f"dar={w['dar']}, geniş={w['genis']}" + (f", ?={w['belirsiz']}" if w["belirsiz"] else "") + f" · medyan {med}"

    L += tablo(["Kol", f"Son {PENCERE_SAAT}s", "Tüm kayıt", "Veri"],
               [[r["arm"], sw_hucre(r["son"]), sw_hucre(r["tum"]), veri(m8["kes"])] for r in d["sw"]])
    a("")
    a("## ML 10 — Kol bazında sanal K/Z")
    a("")
    L += tablo(["Kol", "İşlem", "Net $", "R toplamı", "Kazanma", "Durum", "Veri"],
               [[r["arm"], r["n"], isp(r["net"]) if r["n"] else "-", rr(r["r"]) if r["n"] else "-", yuzde(r["oran"]),
                 "ZARARDA" if r["zarar"] else ("-" if not r["n"] else "kârda/başa baş"), veri(r["veri"]) if r["n"] else "veri: işlem yok"] for r in d["m10"]])
    a("")
    a("Zarardaki kollara karşı mevcut mekanizmalar (kod/yapılandırma; tetik durumu okunabilen durum dosyasından):")
    a("")
    L += tablo(["Mekanizma", "Var mı", "Etki", "Tetiklendi mi", "Veri"],
               [[m["ad"], m["var"], m["etki"], m["tetik"], f"okuma: {tsi(d['simdi'])}"] for m in d["mek"]])
    a("")
    a("## ML 11 — Long/short dağılımı")
    a("")
    sat = []
    for s in ("long", "short"):
        b = yon["genel"][s]
        sat.append([s, b["n"], isp(b["net"]) if b["n"] else "-", yuzde(b["oran"]), rr(b["r"]) if b["n"] else "-", veri(b["veri"]) if b["n"] else "veri: işlem yok"])
    L += tablo(["Yön", "İşlem", "Net $", "Kazanma", "R", "Veri"], sat)
    a("")
    L += tablo(["Rejim", "Long (n / net $ / kazanma)", "Short (n / net $ / kazanma)", "Veri"],
               [[r, " / ".join([str(v["long"]["n"]), isp(v["long"]["net"]) if v["long"]["n"] else "-", yuzde(v["long"]["oran"])]),
                 " / ".join([str(v["short"]["n"]), isp(v["short"]["net"]) if v["short"]["n"] else "-", yuzde(v["short"]["oran"])]),
                 veri(_son([v["long"]["veri"], v["short"]["veri"]])) if (v["long"]["n"] or v["short"]["n"]) else "veri: işlem yok"]
                for r, v in yon["rejim"].items()])
    a("")
    a(f"Güncel rejim (son karar zamanından geriye 24 saatte en sık rejim; {m11['n24']} karar): {m11['rejim'] or 'veri yok'} ({veri(m11['veri'])})")
    a(f"Long-yetkin kollar (kayıtta ≥1 long adayı olanlar) bu rejimde: aday {m11['aday']} · alınan {m11['alinan']}")
    a("")
    if m11["satirlar"]:
        L += tablo(["Kol", "Long aday (güncel rejim)", "Alınan (güncel rejim)", "Long aday (tüm kayıt)", "Alınan (tüm kayıt)", "Veri"],
                   [[s["arm"], s["aday"], s["alinan"], s["aday_toplam"], s["alinan_toplam"], veri(s["son"])] for s in m11["satirlar"]])
        a("")
    a("## ML 12 — Kâğıt / geri test tutarlılığı")
    a("")
    g = m12["genel"]
    if g["durum"] == "var":
        b = g["bant"]
        bs = f"%2,5={b[0]:+.1f} · %10={b[1]:+.1f} · ortanca={b[2]:+.1f} · %90={b[3]:+.1f}".replace(".", ",")
        a(f"Toplam kâğıt R (n={g['n']}): {rr(m12['toplam_r'])} ({veri(m12['veri'])}). Yayımlanmış bant (n={g['n']} için aradeğer): "
          f"{bs}. Konum: {g['etiket']}. Kaynak: {BANT_KAYNAK}.")
    else:
        a(f"Toplam kâğıt R (n={m12['n']}): {rr(m12['toplam_r'])} ({veri(m12['veri'])}). Bant: {g['etiket']}. Kaynak: {BANT_KAYNAK}.")
    a("")
    if m12["tutarlilik"]:
        dn = m12["tutarlilik_donem"] or {}
        a(f"Sunucu tutarlılık raporu (kâğıt ↔ geri test, aynı dönem {dn.get('bas', '?')} → {dn.get('bit', '?')}; uyarı: {m12['tut_uyari']}; {veri(m12['tut_veri'])}). "
          "Arm başına yayımlanmış R/işlem bandı yoktur; kurulum (setup) düzeyi yan yana:")
        a("")
        L += tablo(["Kurulum", "Kâğıt işlem", "Kâğıt R/işlem", "Geri test işlem", "Geri test R/işlem", "Eşleşme", "Veri"],
                   [[k["ad"], k["kagit_n"], rr(k["kagit_rt"]), k["bt_n"], rr(k["bt_rt"]), yuzde(k["eslesme"]) if isinstance(k["eslesme"], (int, float)) else "-",
                     veri(m12["tut_veri"])] for k in m12["tutarlilik"]])
    else:
        a("Arm/kurulum bazında kâğıt R/işlem ↔ geri test bandı: veri yok (tutarlılık raporu yok ya da boş"
          + (f"; not: {m12['tut_not']}" if m12.get("tut_not") else "") + "; repoda arm bazında R/işlem bandı yayımlanmamış).")
    a("")
    return "\n".join(L).rstrip() + "\n"


def tutarlilik_oku(yol) -> tuple[dict | None, datetime | None]:
    """var/durum/tutarlilik_v1.json (+ dosya zamani = veri zamani: `uretim` alani, yoksa None)."""
    from pathlib import Path  # noqa: PLC0415
    try:
        doc = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(doc, dict):
        return None, None
    try:
        t = datetime.strptime(str(doc.get("uretim")), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        t = None
    return doc, t


def json_oku(yol) -> dict | None:
    from pathlib import Path  # noqa: PLC0415
    try:
        d = json.loads(Path(yol).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None

