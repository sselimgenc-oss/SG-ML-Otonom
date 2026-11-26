"""Madde 7: kapi ve veto karnesi. Rapor kural degildir: hicbir bayrak otomatik bir degisiklik tetiklemez."""
from __future__ import annotations

import math

from . import inputs as I
from .exits import plain
from .stats import merge, DASH, MIN_G, MIN_N, SubTable, cluster_mean, mean, wilson

SKIP_DIRECT = ("stop_width", "rr_below_min", "ml_filter", "order_failed")
RISK_CLASSES = ("ayni_yon", "gunluk_butce", "gunluk_sinir", "acik_risk", "teminat_toplam", "likidasyon", "boyut",
                "boyut_min_emir", "cift_acik", "diger")
GATE_CODES = ("kill", "stale_data", "rules_missing", "day_start_missing", "params_unavailable", "trigger_tf_changed",
              "ml1_kapi_yok", "ml1_paket_bozuk")
EXPECTED = (list(SKIP_DIRECT) + ["entry_gate_closed", "other", "veto:claude", "veto:yok", "veto:bayat"]
            + [f"risk:{c}" for c in RISK_CLASSES] + [f"gate:{c}" for c in GATE_CODES])
_RISK_PREFIX = (("aynı yön", "ayni_yon"), ("günlük zarar bütçesi", "gunluk_butce"), ("günlük sınır aşıldı", "gunluk_sinir"),
                ("toplam açık risk", "acik_risk"), ("toplam teminat", "teminat_toplam"), ("likidasyon çok yakın", "likidasyon"))
FIXED_ROWS = (("koşul:volatile", lambda d: d["regime"] == "volatile"), ("koşul:unclear", lambda d: d["regime"] == "unclear"),
              ("R1 kapalı (v1b)", lambda d: d["setup"] == "R1"))
# WP-3 8-2 (rapor-paketi-spec v1.1): sabit satirlar `v_shadow_decisions.block`'tan gelir (sema 4); tablo yoksa FIXED_ROWS (kanit_yok).
SHADOW_ROWS = (("koşul:volatile", "regime_volatile"), ("koşul:unclear", "regime_unclear"),
               ("R1 kapalı (v1b)", "r1_disabled"), ("aynı mumda yeniden giriş", "same_bar_reentry"))
SHADOW_NOTES = {"koşul:volatile": "yalnız T1 (bu koşulda R1 tanımsız)", "koşul:unclear": "yalnız T1 (bu koşulda R1 tanımsız)"}
SHADOW_TABLE_NOTE = ("Gölge satırlar karar paydasına girmez (pay —); n_pozisyon_acik gerçekte hiç alınamayacak satırları ayrı "
                     "gösterir: kanıt üst sınırdır.")
CF_NOTE = ("Alınmayan sinyallerin sonucu (karşı-olgu) üst sınırdır: emir gerçekleşmesi, sonraki kapılar ve gerçek çıkış kuralı "
           "hesaba katılmaz (varsayım).")
TAKEN_NOTE = "gerçek çıkışla; karşı-olgu satırlarıyla birebir kıyaslanamaz"
AUTO_NOTE = "Bayrak yalnız bilgidir: otomatik değişiklik yapılmaz; kural değişikliği ön kayıt ve kullanıcı onayı ister."
VETO_COLS = ["maliyet_usd", "engel_basina_usd", "kacinilan_r", "kacinilan_usd", "net_usd"]
SEPARATION_NOTE = "iki taraf farklı çıkış tanımı kullanır (varsayım)"


def risk_class(reason: str | None) -> str:
    r = (reason or "").strip()
    for pre, cls in _RISK_PREFIX:
        if r.startswith(pre):
            return cls
    if r.startswith("boyutlandırma reddedildi"):
        return "boyut_min_emir" if "en küçük emir" in r else "boyut"
    if "zaten açık pozisyon" in r:
        return "cift_acik"
    return "diger"


def gate_key(d: dict) -> str | None:
    """Atlanan karar icin kapi anahtari (§7.1); alinan karar icin None."""
    if d["final_action"] != "skipped":
        return None
    sr = d["skip_reason"]
    if sr in SKIP_DIRECT:
        return sr
    if sr == "veto_blocked":
        return "veto:claude"
    if sr == "veto_missing":
        return "veto:yok"
    if sr == "veto_stale":
        return "veto:bayat"
    if sr in ("entry_gate_closed", "other"):
        vr = d.get("veto_reason") or ""
        return vr if vr.startswith("gate:") else sr
    if sr == "risk_denied":
        return "risk:" + risk_class(d.get("risk_reason"))
    return sr or "other"


def _stats(dids, n_engel: int, cf: dict | None, n_total: int, period_days: float | None) -> dict:
    """Ortak kapi sutunlari; (satir, olcum_ogeleri) dondurur."""
    row = {"n_engel": n_engel, "pay": (n_engel / n_total) if n_total else None}
    items: list = []
    if cf is None:
        merge(row, {"n_cf": None, "ort_r_cf": None, "aralik_cf": None, "hedef_once": None, "hedef_once_aralik": None,
                    "ort_r_plan": None, "bekleyen": None, "veri_yok": None})
    else:
        bar = [cf[i]["barrier"] for i in dids if i in cf and cf[i]["barrier"] is not None]
        ok = [b for b in bar if b["hyp_r_net"] is not None]
        items = [(b["hyp_r_net"], b["decision_ts"][:10], b["decision_ts"]) for b in ok]
        cm = cluster_mean([x[0] for x in items], [x[1] for x in items])
        w = wilson(sum(1 for b in ok if b["hyp_outcome"] == 1), len(ok))
        plan = [cf[i]["plan"]["hyp_r_net"] for i in dids if i in cf and cf[i]["plan"] is not None
                and cf[i]["plan"]["hyp_r_net"] is not None]
        merge(row, {"n_cf": len(ok), "ort_r_cf": cm["m"], "aralik_cf": [cm["lo"], cm["hi"]] if cm["lo"] is not None else None,
                    "hedef_once": w["p"], "hedef_once_aralik": [w["lo"], w["hi"]] if w["p"] is not None else None,
                    "ort_r_plan": mean(plan) if plan else None, "bekleyen": n_engel - len(bar),
                    "veri_yok": sum(1 for b in bar if b["exit_reason"] in ("data_gap", "invalid_plan"))})
    # yargi
    n_cf = row["n_cf"]
    if n_engel == 0 or not n_cf:
        yargi = "kanit_yok"
    else:
        cm = cluster_mean([x[0] for x in items], [x[1] for x in items])
        if cm["n"] < MIN_N or cm["G"] < MIN_G:
            yargi = "yetersiz"
        else:
            lo, hi = cm["lo"], cm["hi"]
            if lo is None:      # SE ~ 0 (ornegin sabit deger): dejenere aralik [m, m]
                lo = hi = cm["m"]
            yargi = "uyumlu" if hi < 0 else ("celiskili" if lo > 0 else "belirsiz")
    row["yargi"] = yargi
    row["bayrak"] = ""
    if yargi == "celiskili":
        row["bayrak"] = "kazanani_engelliyor"
    elif n_engel == 0 and period_days is not None and period_days >= 28:
        row["bayrak"] = "hic_devreye_girmedi"
    return row, items


def build(trades: list[dict], decisions: list[dict], cf: dict | None, *, mode_backtest: bool, period_days: float | None,
          veto_cost, risk_usd: float, cf_warning: str | None, section: str = "gates",
          shadow: list[dict] | None = None, cf_shadow: dict | None = None) -> dict:
    blocks: list = []
    n_total = len(decisions)
    skipped = [d for d in decisions if d["final_action"] == "skipped"]
    by_gate: dict[str, list] = {}
    for d in skipped:
        by_gate.setdefault(gate_key(d), []).append(d["id"])
    keys = list(EXPECTED) + sorted(k for k in by_gate if k not in EXPECTED)
    use_cf = None if mode_backtest else cf

    # ---- 7.3 veto (veto:claude satirina sutun olarak da eklenir)
    veto: dict = {}
    veto_blocks: list = []
    if mode_backtest or (decisions and all((d.get("veto_status") == "not_evaluated" or (d.get("veto_reason") or "").startswith("not_evaluated"))
                                          for d in decisions)):
        veto = {"durum": "degerlendirilmedi"}
        veto_blocks.append({"kind": "text", "text": "2.3 Claude veto satırı: veto bu koşuda değerlendirilmedi."})
    else:
        dids = by_gate.get("veto:claude", [])
        row, items = _stats(dids, len(dids), use_cf, n_total, period_days)
        n_engel = len(dids)
        kac_r = -math.fsum(x[0] for x in items) if items else None
        kac_usd = kac_r * risk_usd if kac_r is not None else None
        p_izin_n = len(trades)
        p_izin = (sum(1 for t in trades if t["r_multiple"] > 0) / p_izin_n) if p_izin_n else None
        p_engel = row["hedef_once"]
        veto = {"n_engel": n_engel, "maliyet_usd": veto_cost, "engel_basina_usd": (veto_cost / n_engel) if (veto_cost is not None and n_engel) else None,
                "kacinilan_r": kac_r, "kacinilan_usd": kac_usd, "risk_usd": (risk_usd if kac_r is not None else None), "risk_usd_etiket": "varsayım",
                "net_usd": (kac_usd - veto_cost) if (kac_usd is not None and veto_cost is not None) else None,
                "p_kazanc_izin": p_izin, "p_kazanc_engel": p_engel,
                "ayirma": (p_izin - p_engel) if (p_izin is not None and p_engel is not None) else None}
        veto_blocks.append(plain("veto_claude", "2.3 Claude veto satırı",
                            ["n_engel", "maliyet_usd", "engel_basina_usd", "kacinilan_r", "kacinilan_usd", "net_usd",
                             "p_kazanc_izin", "p_kazanc_engel", "ayirma"], [veto],
                            [f"risk_usd = {risk_usd:g} (varsayım)", f"ayirma: {SEPARATION_NOTE}"]))

    cells = []
    for k in keys:
        dids = by_gate.get(k, [])
        row, items = _stats(dids, len(dids), use_cf, n_total, period_days)
        ex = {c: row[c] for c in ("n_engel", "pay", "n_cf", "hedef_once", "hedef_once_aralik", "ort_r_plan",
                                  "bekleyen", "veri_yok", "yargi", "bayrak")}
        if k == "veto:claude":
            for c in VETO_COLS:
                ex[c] = veto.get(c)
        cells.append((k, items, ex))

    def post(r):
        r["kapi"] = r["hucre"]
        r["bayrak_not"] = "(varsayım)" if (r["bayrak"] == "kazanani_engelliyor" and r["etiket"] == "varsayım") else ""
    extra = ["kapi", "n_engel", "pay", "n_cf", "hedef_once", "hedef_once_aralik", "ort_r_plan", "bekleyen", "veri_yok", "yargi", "bayrak", "bayrak_not"] + VETO_COLS
    blocks.append(SubTable("kapi_karnesi", "2.1 Kapı karnesi (atlanan kararlar; ölçüt hyp_r_net, ort = ort_r_cf)", "hyp_r_net",
                           cells, extra, [CF_NOTE, AUTO_NOTE], section, post))

    rm = [t["r_multiple"] for t in trades]
    cm = cluster_mean(rm, [t["gun"] for t in trades])
    blocks.append(plain("alinanlar", "2.2 Karşılaştırma: alınanlar", ["hucre", "n", "G", "ort_r", "aralik"],
                        [{"hucre": "alınanlar", "n": cm["n"], "G": cm["G"], "ort_r": cm["m"],
                          "aralik": [cm["lo"], cm["hi"]] if cm["lo"] is not None else None}], [TAKEN_NOTE]))

    blocks.extend(veto_blocks)

    # ---- 7.4 sabit satirlar
    rows = []
    if shadow is None:                                   # sema < 4: gölge tablo yok -> bugunku kanit_yok + not
        for name, pred in FIXED_ROWS:
            dids = [d["id"] for d in decisions if pred(d)]
            row, _ = _stats(dids, len(dids), use_cf, n_total, period_days)
            if not dids:
                row["yargi"] = "kanit_yok"
            r = {"hucre": name, "kapi": name}
            merge(r, {c: row[c] for c in ("n_engel", "pay", "n_cf", "ort_r_cf", "hedef_once", "yargi", "bayrak")})
            if not dids:
                r["bayrak"] = ""
            r["not"] = "" if dids else "gölge karar satırı WP-3'te"
            rows.append(r)
        r5 = {"hucre": "aynı mumda yeniden giriş", "kapi": "aynı mumda yeniden giriş"}
        merge(r5, {"n_engel": 0, "pay": None, "n_cf": None, "ort_r_cf": None, "hedef_once": None, "yargi": "kanit_yok",
                   "bayrak": ""})
        r5["not"] = "gölge karar satırı WP-3'te"
        rows.append(r5)
        blocks.append(plain("aday_uretmeyen", "2.4 Aday üretmeyen yasaklar",
                            ["hucre", "kapi", "n_engel", "pay", "n_cf", "ort_r_cf", "hedef_once", "yargi", "bayrak", "not"],
                            rows, [CF_NOTE]))
    else:
        cfs = None if mode_backtest else cf_shadow
        for name, block in SHADOW_ROWS:
            sids = [s["id"] for s in shadow if s["block"] == block]
            row, _ = _stats(sids, len(sids), cfs, 0, period_days)
            if not sids:
                row["yargi"] = "kanit_yok"
            r = {"hucre": name, "kapi": name}
            merge(r, {c: row[c] for c in ("n_engel", "n_cf", "ort_r_cf", "hedef_once", "yargi", "bayrak")})
            r["pay"] = DASH                              # gölge satırlar karar paydasına girmez
            r["n_pozisyon_acik"] = sum(1 for s in shadow if s["block"] == block and s.get("pos_open"))
            if not sids:
                r["bayrak"] = ""
            r["not"] = SHADOW_NOTES.get(name, "")
            rows.append(r)
        blocks.append(plain("aday_uretmeyen", "2.4 Aday üretmeyen yasaklar",
                            ["hucre", "kapi", "n_engel", "n_pozisyon_acik", "pay", "n_cf", "ort_r_cf", "hedef_once", "yargi",
                             "bayrak", "not"], rows, [CF_NOTE, SHADOW_TABLE_NOTE]))
    counts = {k: len(v) for k, v in by_gate.items()}
    return {"blocks": blocks, "veto": veto, "gate_counts": counts, "n_engel_toplam": len(skipped), "cf_warning": cf_warning}


def compare(live_trades, live_counts: dict, bt_trades, bt_counts: dict, period_days: float | None) -> dict:
    """A-16: backtest'te gorulup canli/kagit defterde hic gorulmeyenler."""
    live_r = {t["exit_reason"] for t in live_trades}
    only_reasons = sorted({t["exit_reason"] for t in bt_trades} - live_r)
    early = period_days is None or period_days < 28
    only_gates = [] if early else sorted(k for k, n in bt_counts.items() if n > 0 and live_counts.get(k, 0) == 0)
    return {"yalniz_backtest_cikis_nedenleri": only_reasons, "yalniz_backtest_kapilari": only_gates,
            "durum": "erken" if early else "degerlendirilebilir", "kagit_donemi_gun": period_days}


_TR_NAMES = {"stop_width": "stop genişliği", "rr_below_min": "kazanç/risk oranı", "ml_filter": "öğrenen filtre",
             "order_failed": "emir hatası", "entry_gate_closed": "giriş kapısı kapalı", "other": "diğer",
             "veto:claude": "veto", "veto:yok": "veto yok", "veto:bayat": "veto bayat",
             "risk:ayni_yon": "aynı yön riski", "risk:gunluk_butce": "günlük zarar bütçesi", "risk:gunluk_sinir": "günlük sınır",
             "risk:acik_risk": "toplam açık risk", "risk:teminat_toplam": "toplam teminat", "risk:likidasyon": "likidasyon yakınlığı",
             "risk:boyut": "boyutlandırma", "risk:boyut_min_emir": "en küçük emir", "risk:cift_acik": "çift zaten açık",
             "risk:diger": "diğer risk", "gate:kill": "acil durdurma", "gate:stale_data": "bayat veri",
             "gate:rules_missing": "borsa kuralı yok", "gate:day_start_missing": "gün başı bakiyesi yok",
             "gate:params_unavailable": "ayarlar okunamadı", "gate:trigger_tf_changed": "zaman dilimi değişti",
             "gate:ml1_kapi_yok": "ML1 kapısı kurulamadı", "gate:ml1_paket_bozuk": "ML1 paketi bozuk"}


def tr_name(key: str) -> str:
    """Telegram satiri icin Turkce kapi adi (Ingilizce anahtar gosterilmez)."""
    if key in _TR_NAMES:
        return _TR_NAMES[key]
    return key.split(":", 1)[-1].replace("_", " ")
