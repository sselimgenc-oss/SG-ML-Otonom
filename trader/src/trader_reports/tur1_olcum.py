"""Tur 1 / Asama A olcum raporu (`tur1_olcum`): YALNIZ OLCUM, botu degistirmez, karar yoluna bagli degildir.

Kagit defteri (kapanan islemler + karar satirlari) ve market.sqlite mumlari uzerinden alti bolum:
  1 basit rakip kiyasi   2 gecikme/masraf dayanikliligi   3 sans/kuyruk testi
  4 canliya gecis sartlari   5 yon denetimi   6 kayip kumeleri
Kilitli donem (HOLDOUT) okunmaz: islemler `guard.trade_locked` ile elenir, mum okumalari `guard.check_window` gecidinden gecer.
Az islemde hicbir bolum kesinlik taklit etmez: her bolum n verir ve `yetersiz ornek` bayragi tasir. Tohumlar sabittir.
"""
from __future__ import annotations

import math
import warnings
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

from . import guard, inputs as I
from .guard import BacktestArgError
from .stats import MIN_G, cluster_mean, merge

SCHEMA = "ml.tur1_olcum.v1"

# ----------------------------------------------------------------------------- SABITLER (duz Turkce)
YETERSIZ_N = 30              # Bir bolumde bu sayidan az islem varsa sonuc "yetersiz ornek"tir; sayilar yalniz bilgidir.
CANLI_MIN_ISLEM = 300        # Canliya gecis sarti 1: en az bu kadar kapanmis islem.
CANLI_GUVEN_ALT_SINIR = 0.0  # Sart 2: islem basina net R ortalamasinin guven alt siniri bunun USTUNDE olmali.
CANLI_MIN_REJIM = 2          # Sart 3: en az bu kadar farkli rejimde toplam net pozitif olmali.
REJIM_MIN_ISLEM = 30         # Bir rejimin "sayilmasi" icin o rejimde en az bu kadar islem gerekir (eskiden 10; 23.11 karari: 30) ve gun kumeli guven alt siniri > 0 olmali.
CANLI_MIN_RASTGELE_YUZDELIK = 90.0   # Sart 4: sonucumuz rastgele giris dagiliminin en az bu yuzdeligine ulasmali.
CANLI_MASRAF_CARPANI = 1.5   # Sart 5: masraflar bu carpanla buyutulunca da net > 0 kalmali.
SERMAYE_MANDALI_ORANI = 0.85  # Kasa baslangicin bu oraninin altina inerse sermaye mandali kapanir (batis).
CANLI_MAKS_DUSUS = 1.0 - SERMAYE_MANDALI_ORANI   # Sart 6: Monte Carlo %95 maks dusus bundan (= %15, yani mandal siniri) kotu olmamali. Yeni sayi degil: mandaldan turetilir.
PBO_BOLUM = 16               # DSR/PBO bilgi satiri: PBO icin gun serisi bu kadar (cift) parcaya bolunur; en az 2 x bu kadar gun gerekir.
KARISTIRMA_SAYISI = 10000    # Islem sirasi karistirma sayisi (en az 5000).
RASTGELE_B = 2000            # Rastgele giris simulasyon sayisi (ilk asama k2'de 500; p kucukse 5000'e cikar).
GECIKME_BARLARI = (1, 2)     # Girisi kendi zaman diliminin kac mum geciktirecegiz.
MASRAF_CARPANLARI = (1.5, 2.0)
EN_IYI_CIKAR = (1, 2, 5)
KUME_ILK_N = 10              # Kayip kumeleri: listelenecek kume sayisi.
KUME_MIN_ISLEM = 3           # Bir kumede bundan az kayip varsa "az ornek" notu.
SEED = 20261123              # Tum rastgelelik bu tohumdan turetilir.

TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}   # 1d: market.sqlite 4s mumlarından kurulur (tam 6 mumlu UTC günü)
YETERSIZ = "yetersiz örnek"


def etiket(n: int) -> str | None:
    return YETERSIZ if n < YETERSIZ_N else None


def _f(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else float(x)


# ----------------------------------------------------------------------------- girdi: kayit -> sade sozluk
def tf_of(arm_id: str | None, trigger_tf: str | None) -> str:
    if trigger_tf:
        return trigger_tf
    if arm_id and "@" in arm_id:
        return arm_id.rsplit("@", 1)[1]
    return "1h"


def trade_dict(t, dec, asset_of) -> dict:
    """TradeRecord (ya da ayni alanlara sahip nesne/sozluk) + karar satiri -> sade sozluk. Zamanlar ISO metin."""
    g = (lambda k: t.get(k)) if isinstance(t, dict) else (lambda k: getattr(t, k, None))
    dg = (lambda k: None) if dec is None else ((lambda k: dec.get(k)) if isinstance(dec, dict) else (lambda k: getattr(dec, k, None)))

    def ts(v):
        return v if isinstance(v, str) else v.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    arm = dg("arm_id") or (f"{g('setup')}@{dg('trigger_tf') or '1h'}")
    pr = _f(g("planned_risk"))
    return {"trade_id": g("trade_id"), "pair": g("pair"), "side": g("side"), "arm": arm, "tf": tf_of(arm, dg("trigger_tf")),
            "regime": g("regime"), "asset": asset_of(g("pair")), "entry_ts": ts(g("entry_ts")), "exit_ts": ts(g("exit_ts")),
            "entry_price": _f(g("entry_price")), "exit_price": _f(g("exit_price")), "qty": _f(g("qty")),
            "planned_entry": _f(g("planned_entry")), "planned_stop": _f(g("planned_stop")), "planned_risk": pr,
            "gross_pnl": _f(g("gross_pnl")), "pnl": _f(g("realized_pnl")), "net_r": _f(g("r_multiple")),
            "mfe_r": _f(g("mfe_r")), "mae_r": _f(g("mae_r")), "bars_held": g("bars_held")}


def decision_dict(d, asset_of) -> dict:
    g = (lambda k: d.get(k)) if isinstance(d, dict) else (lambda k: getattr(d, k, None))
    b = g("bar_close_ts")
    b = b if isinstance(b, str) else b.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    arm = g("arm_id") or f"{g('setup')}@{g('trigger_tf') or '1h'}"
    return {"id": g("id"), "pair": g("pair"), "side": g("side"), "arm": arm, "regime": g("regime"), "asset": asset_of(g("pair")),
            "bar_close_ts": b, "final_action": g("final_action"), "skip_reason": g("skip_reason")}


def holdout_filtrele(trades: list[dict], decisions: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Kilitli donemle (72 saat pay dahil) kesisen islem/kararlari atar; atilan islem sayisini da doner. Ayrica bozuk satirlari eler."""
    ok = [t for t in trades if t.get("net_r") is not None and t.get("planned_risk")
          and not guard.trade_locked(t["entry_ts"], t["exit_ts"])]
    kilit = sum(1 for t in trades if guard.trade_locked(t["entry_ts"], t["exit_ts"]))
    dok = [d for d in decisions if not guard.ts_locked(d["bar_close_ts"])]
    return ok, dok, kilit


# ----------------------------------------------------------------------------- mumlar (yalniz guard gecidiyle)
def _ms(ts: str) -> int:
    return I.iso_ms(ts)


class MumDeposu:
    """market.sqlite 'last' mumlari. Her okuma `guard.check_window` gecidinden gecer; kilitli donemle kesisen okuma YAPILMAZ (None/bos)."""

    def __init__(self, path) -> None:
        self.conn = I.open_ro(path, "market_missing")
        uv = I.user_version(self.conn)
        if uv != 1:
            raise I.ReportError("market_schema", f"market.sqlite sema surumu {uv}; 1 bekleniyor")
        self._cache: dict = {}

    def close(self) -> None:
        self.conn.close()

    def _rows(self, pair, tf, start_ms, n):
        ms = TF_MS.get(tf)
        if ms is None or n <= 0:
            return None
        try:
            guard.check_window(start_ms, n, ms)
        except BacktestArgError:
            return None
        if tf == "1d":
            return self._rows_1d(pair, start_ms, n)
        cur = self.conn.execute(
            "SELECT open_ms, o, h, l, c FROM bars WHERE kind='last' AND pair=? AND tf=? AND open_ms>=? AND open_ms<? "
            "AND written_ms >= open_ms + ? ORDER BY open_ms", (pair, tf, start_ms, start_ms + n * ms, ms))
        return cur.fetchall()

    def _rows_1d(self, pair, start_ms, n):
        """Günlük mumlar 4s'lerden kurulur: yalnız TAM 6 x 4s mumlu UTC günü (motor/`counterfactual` kuralıyla aynı); eksik gün yok sayılır."""
        h4, gun = TF_MS["4h"], TF_MS["1d"]
        rows = self.conn.execute(
            "SELECT open_ms, o, h, l, c, written_ms FROM bars WHERE kind='last' AND pair=? AND tf='4h' AND open_ms>=? AND open_ms<? "
            "ORDER BY open_ms", (pair, start_ms, start_ms + n * gun)).fetchall()
        gunler: dict = defaultdict(list)
        for r in rows:
            if r[5] >= r[0] + h4:
                gunler[r[0] - r[0] % gun].append(r)
        out = []
        for g in sorted(gunler):
            bs = gunler[g]
            if [b[0] for b in bs] != [g + k * h4 for k in range(6)]:
                continue
            out.append((g, bs[0][1], max(b[2] for b in bs), min(b[3] for b in bs), bs[-1][4]))
        return out

    def bar(self, pair: str, tf: str, open_ms: int):
        """(o, h, l, c) ya da None (yok/kilitli/bilinmeyen tf)."""
        key = (pair, tf, open_ms)
        if key not in self._cache:
            r = self._rows(pair, tf, open_ms, 1)
            self._cache[key] = tuple(r[0][1:]) if r else None
        return self._cache[key]

    def frame(self, pair: str, tf: str, lo_ms: int, hi_ms: int) -> dict | None:
        """{'ms','open','high','low','close'} numpy dizileri (kilitli donemle kesisirse ya da veri yoksa None)."""
        ms = TF_MS.get(tf)
        if ms is None:
            return None
        lo = lo_ms - lo_ms % ms
        r = self._rows(pair, tf, lo, max(0, (hi_ms - lo) // ms))
        if not r:
            return None
        a = np.array(r, dtype=float)
        return {"ms": a[:, 0].astype(np.int64), "open": a[:, 1], "high": a[:, 2], "low": a[:, 3], "close": a[:, 4]}


# ----------------------------------------------------------------------------- ortak olcumler
def toplam(xs) -> float:
    return math.fsum(xs)


def ozet(xs, days=None) -> dict:
    """n, toplam, ortalama (+ gun kumelenmis %90 aralik; G<8 ise aralik YOK)."""
    n = len(xs)
    out = {"n": n, "toplam": toplam(xs) if n else 0.0, "ort": (toplam(xs) / n) if n else None, "alt": None, "ust": None,
           "etiket": etiket(n)}
    if n and days is not None:
        c = cluster_mean(list(xs), list(days))
        out["alt"], out["ust"], out["G"] = c["lo"], c["hi"], c["G"]
    return out


def cost_r(t: dict) -> float:
    """Islemin toplam masrafi (komisyon + fonlama + kayma etkisi) R cinsinden = brut - net."""
    return (t["gross_pnl"] - t["pnl"]) / t["planned_risk"]


def sig(t: dict) -> int:
    return 1 if t["side"] == "long" else -1


# ----------------------------------------------------------------------------- 1) basit rakip kiyasi
def _kurulum_islemleri(trades, mumlar: MumDeposu):
    """k2 icin islem satirlari: {(pair, tf, parca): (mum, [(giris_ms, yon, stop_carpan, tutma)], [trade])}. Kilitli donemin iki yaninda
    ayri parca ('once' < kilit payi <= 'sonra'): simulasyon mumlari kilitli donemi asla icermez."""
    from trader_core import tur1_rastgele as RG
    gruplar: dict = defaultdict(list)
    for t in trades:
        if t["tf"] not in TF_MS:
            at(t, "tf_bilinmiyor")
            continue
        if not t.get("planned_entry") or not t.get("planned_stop"):
            at(t, "plan_yok")
            continue
        parca = "once" if t["entry_ts"] < guard.H0_PAD_ISO else "sonra"
        gruplar[(t["pair"], t["tf"], parca)].append(t)
    sonuc = {}
    neden: dict = defaultdict(int)          # atlanma nedeni -> sayı
    atlanan_tf: dict = defaultdict(int)     # zaman dilimi -> atlanan işlem sayısı (sessiz düşme yok)

    def at(t, ne):
        neden[ne] += 1
        atlanan_tf[t.get("tf") or "?"] += 1
    for (pair, tf, parca), ts in gruplar.items():
        ms = TF_MS[tf]
        giris = [_ms(t["entry_ts"]) - _ms(t["entry_ts"]) % ms for t in ts]
        lo, hi = min(giris) - 200 * ms, max(giris) + 400 * ms
        if parca == "once":
            hi = min(hi, guard.H0_MS - guard.PAD_HOURS * 3_600_000)
        else:
            lo = max(lo, guard.H1_MS)
        mum = mumlar.frame(pair, tf, lo, hi)
        if mum is None or len(mum["ms"]) < 30:
            for t in ts:
                at(t, "mum_yok")
            continue
        atr_ = RG.atr_onceki(mum, giris)
        sat, tr = [], []
        for t, g, a in zip(ts, giris, atr_):
            if not (a == a and a > 0):
                at(t, "atr_yok")
                continue
            tutma = int(t["bars_held"]) if t.get("bars_held") else max(1, round((_ms(t["exit_ts"]) - _ms(t["entry_ts"])) / ms))
            sat.append((g, sig(t), abs(t["planned_entry"] - t["planned_stop"]) / a, max(1, tutma)))
            tr.append(t)
        if sat:
            sonuc[(pair, tf, parca)] = (mum, sat, tr)
    return sonuc, {"toplam": sum(neden.values()), "neden": dict(neden), "tf": dict(atlanan_tf)}


def kagit_maliyet_fn(cfg: dict | None):
    """Kâğıt masraf modelinden (`config/engine.paper.json`: `cost` + `cost_overrides`, `trader_engine.config.CostModel` varsayılanları)
    çift -> K2Maliyet. Hisse/emtia için 'open' seans kayması. FONLAMA YOK: k2 simülasyonu fonlama taşımaz (rapor notu). cfg None -> None."""
    if not isinstance(cfg, dict):
        return None
    from trader_core.stats.k2_simulasyon import K2Maliyet
    from trader_engine.config import CostModel
    d = CostModel()
    c = cfg.get("cost") if isinstance(cfg.get("cost"), dict) else {}
    ov = cfg.get("cost_overrides") if isinstance(cfg.get("cost_overrides"), dict) else {}
    taker = float(c.get("taker_fee", d.taker_fee))
    base = {k: float(c.get(k, getattr(d, k))) for k in ("slip_entry_bps", "slip_exit_bps", "slip_stop_bps")}

    def fn(pair: str):
        o = ((ov.get(pair) or {}).get("open")) or {}
        v = {k: float(o.get(k, base[k])) for k in base}
        return K2Maliyet(kayma=(v["slip_entry_bps"] + v["slip_exit_bps"]) / 2e4, stop_kayma=v["slip_stop_bps"] / 1e4, taker=taker)
    return fn


def rastgele_giris(trades, mumlar: MumDeposu | None, b: int = RASTGELE_B, seed: int = SEED, maliyet_cfg: dict | None = None) -> dict:
    """Mevcut k2 simulasyonu (`trader_core.stats.k2_simulasyon`): ayni sayi, yon, stop/ATR kati ve tutma suresi; giris ayni takvim
    ceyreginde rastgele. Rakip dagilim 'toplam R'; bizimki ayni islem alt kumesinin gercek toplam net R'si."""
    from trader_core import tur1_rastgele as RG
    if mumlar is None or not trades:
        return {"durum": "veri_yok", "n": 0, "etiket": YETERSIZ}
    gr, at = _kurulum_islemleri(trades, mumlar)
    atlanan = at["toplam"]
    n = sum(len(v[1]) for v in gr.values())
    if not n:
        return {"durum": "veri_yok", "n": 0, "atlanan": atlanan, "atlanan_neden": at["neden"], "atlanan_tf": at["tf"], "etiket": YETERSIZ}
    gercek = toplam(t["net_r"] for v in gr.values() for t in v[2])
    gk = {key: (v[0], v[1]) for key, v in gr.items()}
    mf = kagit_maliyet_fn(maliyet_cfg)
    k = RG.k2_toplam(gk, gercek, b, seed, guard.H1_MS, mf)
    sim = k["sim"]
    yuzdelik = 100.0 * float((np.sum(sim < gercek) + 0.5 * np.sum(sim == gercek)) / sim.size)
    eski = None
    if mf is not None:                       # yan yana: eski sabit k2 masrafı (2/5/5 bp, fonlamasız)
        ke = RG.k2_toplam(gk, gercek, b, seed, guard.H1_MS)
        se = ke["sim"]
        eski = {"rastgele_ort_toplam_r": float(se.mean()), "yuzdelik": 100.0 * float((np.sum(se < gercek) + 0.5 * np.sum(se == gercek)) / se.size),
                "p": ke["p"], "masraf": "k2 varsayılanı: kayma 2bp, stop kayması 5bp, taker 5bp"}
    return {"durum": "ok", "n": n, "atlanan": atlanan, "atlanan_neden": at["neden"], "atlanan_tf": at["tf"],
            "kapsanan_tf": sorted({k[1] for k in gr}), "simulasyon_sayisi": int(sim.size), "bizim_toplam_r": gercek,
            "bizim_ort_r": gercek / n, "rastgele_ort_toplam_r": float(sim.mean()), "rastgele_ort_r": float(sim.mean() / n),
            "rastgele_p5": float(np.percentile(sim, 5)), "rastgele_p50": float(np.percentile(sim, 50)),
            "rastgele_p95": float(np.percentile(sim, 95)), "yuzdelik": yuzdelik, "p": k["p"], "asama": k["asama"],
            "masraf_modeli": "kagit_config" if mf is not None else "k2_varsayilan", "eski_masraf": eski,
            "not": ("Rastgele giriş kâğıt masraf modeliyle (config kayma/komisyon; hisse/emtia 'open' seans kayması) fiyatlanır; FONLAMA dahil değildir "
                    "(k2 simülasyonu taşımaz), yani rakip bizden biraz ucuza çıkar. Eski sabit masrafla sonuç yan yanadır."
                    if mf is not None else
                    "Rastgele giriş k2 varsayılan masrafıyla (kayma 2bp, stop kayması 5bp, taker 5bp) fiyatlanır; bizimki gerçek masraflıdır."),
            "etiket": etiket(n)}


def sabit_yon(trades, yon: int) -> dict:
    """Ayni giris zamanlari, hep long (+1) ya da hep short (-1). Bizimle ayni yon: kendi net R'miz. Ters yon: brut hareket
    ters cevrilir, stop 1R'de; kendi MFE'miz >= 1R ise ters yon stop olurdu (-1R). Masraf ayni. Tahmindir (stop/hedef yeniden oynatilmaz)."""
    xs, tahmin = [], 0
    for t in trades:
        if sig(t) == yon:
            xs.append(t["net_r"])
            continue
        brut = t["gross_pnl"] / t["planned_risk"]
        ters = -brut
        if t.get("mfe_r") is not None and t["mfe_r"] >= 1.0:
            ters = -1.0
        elif t.get("mfe_r") is None:
            tahmin += 1
        xs.append(ters - cost_r(t))
    d = ozet(xs)
    d["mfe_yok_sayisi"] = tahmin
    return d


def al_tut(trades, mumlar: MumDeposu | None, kasa0: float | None = None) -> dict:
    """Gerçek al-tut: işlem yapılan her enstrüman için aynı dönem (ilk giriş -> son çıkış), 1s mumlarla, long, EŞİT ağırlık; masrafsız.
    Kilitli dönem okunmaz: dönem kilitli aralığı kesiyorsa iki parça ayrı okunur ve zincirlenir (kilitli aralık dışarıda bırakılır).
    Mum verisi olmayan enstrüman sayılır ('veri yok'). Bizimki: toplam net USD / başlangıç kasası (kasa0 verilmişse)."""
    out = {"n": len(trades), "etiket": etiket(len(trades))}
    if mumlar is None or not trades:
        return {**out, "durum": "veri_yok"}
    tf, ms = "1h", TF_MS["1h"]
    bas = min(_ms(t["entry_ts"]) for t in trades)
    bit = max(_ms(t["exit_ts"]) for t in trades)
    bas, bit = bas - bas % ms, bit - bit % ms + ms
    h0 = guard.H0_MS - guard.PAD_HOURS * 3_600_000
    parcalar = [(bas, bit)]
    if bas < h0 < bit:                                  # kilitli aralıkla kesişen dönem: iki parça
        parcalar = [(bas, h0), (max(guard.H1_MS, bas), bit)]
    elif guard.H0_MS - 1 <= bas < guard.H1_MS:
        parcalar = [(guard.H1_MS, bit)]
    getiri, yok = {}, []
    for pair in sorted({t["pair"] for t in trades}):
        g, ok = 1.0, True
        for lo, hi in parcalar:
            if hi <= lo:
                continue
            f = mumlar.frame(pair, tf, lo, hi)
            if f is None or len(f["ms"]) < 2:
                ok = False
                break
            g *= f["close"][-1] / f["open"][0]
        if ok:
            getiri[pair] = g - 1.0
        else:
            yok.append(pair)
    merge(out, {"n_enstruman": len(getiri) + len(yok), "n_veri_var": len(getiri), "veri_yok_enstruman": yok,
                "donem": [iso_ms(bas), iso_ms(bit)], "kilitli_aralik_disarida": len(parcalar) > 1})
    if not getiri:
        return {**out, "durum": "veri_yok"}
    merge(out, {"durum": "ok", "ort_getiri": float(np.mean(list(getiri.values()))), "enstruman_getirisi": getiri,
                "masraf": "yok (al-tut masrafsız; bizimki masraflı)"})
    if kasa0:
        out["bizim_getiri"] = toplam(t["pnl"] for t in trades) / kasa0
    return out


def iso_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rakip_kiyasi(trades, mumlar, b: int = RASTGELE_B, seed: int = SEED, maliyet_cfg: dict | None = None, kasa0: float | None = None) -> dict:
    rs = [t["net_r"] for t in trades]
    return {"n": len(trades), "etiket": etiket(len(trades)), "bizim": ozet(rs),
            "rastgele_giris": rastgele_giris(trades, mumlar, b, seed, maliyet_cfg), "al_tut": al_tut(trades, mumlar, kasa0),
            "hep_long": sabit_yon(trades, +1), "hep_short": sabit_yon(trades, -1),
            "hicbir_sey": {"n": len(trades), "toplam": 0.0, "ort": 0.0}}


# ----------------------------------------------------------------------------- 2) gecikme / masraf dayanikliligi
def _bar_ms(t, tf):
    ms = TF_MS[tf]
    e = _ms(t["entry_ts"])
    return e - e % ms, ms


def gecikmeli_r(t: dict, mumlar: MumDeposu | None, tf: str, k: int) -> tuple[float | None, str]:
    """Girisi `tf` mumunda k adim geciktir: yeni giris = giris * o[k]/o[0] (ayni baslangic mumu ve gecikmis mum acilislari).
    Stop, boyut ve cikis ayni kalir (varsayim). Yeni giris stopun yanlis tarafinda ya da cikistan sonra ise islem 'kacirildi' (R=0)."""
    if mumlar is None or tf not in TF_MS:
        return None, "veri_yok"
    b0, ms = _bar_ms(t, tf)
    m0, mk = mumlar.bar(t["pair"], tf, b0), mumlar.bar(t["pair"], tf, b0 + k * ms)
    if not m0 or not mk or not m0[0]:
        return None, "veri_yok"
    yeni = t["entry_price"] * mk[0] / m0[0]
    s = sig(t)
    if _ms(t["exit_ts"]) <= b0 + k * ms or (yeni - t["planned_stop"]) * s <= 0:
        return 0.0, "kacirildi"
    return t["net_r"] + s * (t["entry_price"] - yeni) * t["qty"] / t["planned_risk"], "ok"


def _senaryo(trades, fn) -> dict:
    xs, durum, yok_tf = [], defaultdict(int), defaultdict(int)
    baz = []
    for t in trades:
        r, d = fn(t)
        durum[d] += 1
        if d == "veri_yok":
            yok_tf[t.get("tf") or "?"] += 1
        if r is not None:
            xs.append(r)
            baz.append(t["net_r"])
    o = ozet(xs)
    o["durum"] = dict(durum)
    o["veri_yok_tf"] = dict(yok_tf)          # sessiz düşme yok: hangi zaman diliminde kaç işlem için mum verisi yok
    o["ayni_islemlerde_gercek_net"] = toplam(baz)
    o["kalan_oran"] = (o["toplam"] / toplam(baz)) if baz and toplam(baz) > 0 else None
    return o


def dayaniklilik(trades, mumlar) -> dict:
    base = toplam(t["net_r"] for t in trades)
    out = {"n": len(trades), "etiket": etiket(len(trades)), "gercek_net_r": base, "gecikme": {}, "masraf": {}}
    for k in GECIKME_BARLARI:
        out["gecikme"][f"{k}_mum"] = _senaryo(trades, lambda t, k=k: gecikmeli_r(t, mumlar, t["tf"], k))
    for m in MASRAF_CARPANLARI:
        o = ozet([t["net_r"] - (m - 1.0) * cost_r(t) for t in trades])
        o["kalan_oran"] = (o["toplam"] / base) if base > 0 else None
        out["masraf"][f"x{m}"] = o
    # 15 dakikalik mum saati kaymasi
    out["saat_kaymasi_15dk"] = {
        "tam_olculebildi": False,
        "aciklama": ("Gerçek 15 dk mum-saati kayması sinyali yeniden üretmeyi gerektirir (göstergeler kaymış mumlarda yeniden "
                     "hesaplanır); saklı veriden (defter + market.sqlite) YAPILAMAZ. Aşağıdaki yalnız yaklaşık vekildir: giriş 15 dk "
                     "gecikir (15dk mumlarla), sinyal/stop/çıkış aynı kalır."),
        "yaklasik_giris_15dk_gecikme": _senaryo(trades, lambda t: gecikmeli_r(t, mumlar, "15m", 1))}
    return out


# ----------------------------------------------------------------------------- 3) sans / kuyruk
def _blok_ornekleme(pnl, kasa0: float, runs: int, seed: int, egri) -> dict:
    """Durağan blok örnekleme (`trader_core.stats.stats`, Politis-Romano): işlem sırası bloklar halinde çekilir, kayıpların peş peşe
    gelmesi (kümelenme) korunur. Saf karıştırma bunu yok eder ve en kötü düşüşü olduğundan küçük gösterebilir. Ortalama blok uzunluğu
    aracın varsayılanıdır (Politis-White otomatik seçim; seri bağımlılık yoksa 1'e iner). Karıştırmayla yan yana raporlanır."""
    from trader_core.stats import stats as S
    n = len(pnl)
    mb = float(min(max(S.optimal_block_length(pnl)["stationary"], 1.0), n))
    rng = np.random.default_rng(seed + 1)
    dds, batan, left = [], 0, runs
    while left > 0:
        m = min(left, max(1, 2_000_000 // n))
        e, dd = egri(pnl[S.stationary_bootstrap_indices(n, m, mb, rng)])
        dds.append(dd)
        batan += int(((np.minimum(e.min(axis=1), kasa0)) < SERMAYE_MANDALI_ORANI * kasa0).sum())
        left -= m
    dd = np.concatenate(dds)
    return {"ort_blok_uzunlugu": mb, "ornekleme": runs, "maks_dusus": {f"p{q}": float(np.percentile(dd, q)) for q in (5, 50, 95, 99)},
            "batis_olasiligi": batan / runs}


def sans_kuyruk(trades, kasa0: float, runs: int = KARISTIRMA_SAYISI, seed: int = SEED) -> dict:
    n = len(trades)
    pnl = np.array([t["pnl"] for t in sorted(trades, key=lambda t: (t["exit_ts"], t["trade_id"]))], float)
    out = {"n": n, "etiket": etiket(n), "kasa_baslangic": kasa0, "karistirma": runs}

    def egri(p):
        e = kasa0 + np.cumsum(p, axis=-1)
        pk = np.maximum.accumulate(np.concatenate([np.full(e.shape[:-1] + (1,), kasa0), e], axis=-1), axis=-1)[..., 1:]
        return e, ((pk - e) / pk).max(axis=-1)
    if n:
        e, dd = egri(pnl)
        out["gercek_sira"] = {"maks_dusus": float(dd), "min_kasa_orani": float(min(e.min(), kasa0) / kasa0)}
        rng = np.random.default_rng(seed)
        dds, batan, left = [], 0, runs
        while left > 0:
            m = min(left, max(1, 2_000_000 // n))
            idx = np.argsort(rng.random((m, n)), axis=1)
            e, dd = egri(pnl[idx])
            dds.append(dd)
            batan += int(((np.minimum(e.min(axis=1), kasa0)) < SERMAYE_MANDALI_ORANI * kasa0).sum())
            left -= m
        dd = np.concatenate(dds)
        out["maks_dusus"] = {f"p{q}": float(np.percentile(dd, q)) for q in (5, 50, 95, 99)}
        out["batis_olasiligi"] = batan / runs
        out["batis_tanimi"] = f"kasa <= {SERMAYE_MANDALI_ORANI:.0%} x baslangic (sermaye mandali) en az bir an"
        out["blok"] = _blok_ornekleme(pnl, kasa0, runs, seed, egri)
    rs = sorted((t["net_r"] for t in trades), reverse=True)
    pn = sorted((t["pnl"] for t in trades), reverse=True)
    out["en_iyi_cikar"] = {str(k): {"net_r": toplam(rs[k:]) if n > k else None, "net_usd": toplam(pn[k:]) if n > k else None}
                           for k in EN_IYI_CIKAR}
    out["toplam_net_r"], out["toplam_net_usd"] = toplam(rs), toplam(pn)
    return out


# ----------------------------------------------------------------------------- 5) yon denetimi
def _kirilim(trades, keyf) -> list[dict]:
    g: dict = defaultdict(list)
    for t in trades:
        g[keyf(t)].append(t["net_r"])
    return [{"anahtar": list(k) if isinstance(k, tuple) else k, **ozet(v)} for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))]


def yon_denetimi(trades) -> dict:
    return {"n": len(trades), "etiket": etiket(len(trades)),
            "yon": _kirilim(trades, lambda t: t["side"]),
            "yon_rejim": _kirilim(trades, lambda t: (t["side"], t["regime"])),
            "yon_varlik_sinifi": _kirilim(trades, lambda t: (t["side"], t["asset"])),
            "yon_kol": _kirilim(trades, lambda t: (t["side"], t["arm"]))}


# ----------------------------------------------------------------------------- 6) kayip kumeleri
def saat_dilimi(ts: str) -> str:
    h = int(ts[11:13]) // 4 * 4
    return f"{h:02d}-{h + 4:02d} UTC"


def kayip_kumeleri(trades, ilk: int = KUME_ILK_N) -> dict:
    anahtar = lambda t: (t["arm"], t["regime"], t["side"], t["asset"], saat_dilimi(t["entry_ts"]))  # noqa: E731
    tum, kay = defaultdict(int), defaultdict(list)
    for t in trades:
        tum[anahtar(t)] += 1
        if t["net_r"] < 0:
            kay[anahtar(t)].append(t["net_r"])
    rows = [{"kol": k[0], "rejim": k[1], "yon": k[2], "varlik_sinifi": k[3], "saat": k[4], "kayip_sayisi": len(v),
             "toplam_islem": tum[k], "toplam_kayip_r": toplam(v), "not": "az örnek" if len(v) < KUME_MIN_ISLEM else None}
            for k, v in kay.items()]
    nk = sum(len(v) for v in kay.values())
    return {"n_islem": len(trades), "n_kayip": nk, "kume_sayisi": len(rows), "etiket": etiket(len(trades)),
            "sayiya_gore": sorted(rows, key=lambda r: (-r["kayip_sayisi"], r["toplam_kayip_r"], str(r["kol"])))[:ilk],
            "kayba_gore": sorted(rows, key=lambda r: (r["toplam_kayip_r"], -r["kayip_sayisi"], str(r["kol"])))[:ilk]}


# ----------------------------------------------------------------------------- 4) canliya gecis sartlari
def dsr_pbo(trades) -> dict:
    """BİLGİ (karar vermez): deflated Sharpe (işlem başına net R; deneme sayısı = işlem yapan kol sayısı, deneme Sharpe dağılımı kol
    başına) ve PBO (gün x kol net R matrisi, CSCV). Az veride ikisi de belirsizdir; hesaplanamayanın nedeni yazılır."""
    from trader_core.stats import stats as S
    rs = np.array([t["net_r"] for t in trades], float)
    out = {"n": len(rs), "etiket": etiket(len(rs)), "dsr": None, "pbo": None}
    if len(rs) < 3 or not rs.std() > 0:
        out["dsr_not"] = "hesaplanamadı (en az 3 işlem ve sıfırdan farklı dağılım gerekir)"
    else:
        kol: dict = defaultdict(list)
        for t in trades:
            kol[t["arm"]].append(t["net_r"])
        srs = [float(np.mean(v) / np.std(v, ddof=1)) for v in kol.values() if len(v) >= 2 and np.std(v, ddof=1) > 0]
        sk, ku = S.return_moments(rs)
        sr = float(rs.mean() / rs.std(ddof=1))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)       # çok küçük/dejenere örnekte basıklık uyarısı: bilgi satırı, gürültü yok
            dsr = float(S.deflated_sharpe(sr, len(rs), sk, ku, trial_srs=srs if len(srs) > 1 else None, n_trials=max(1, len(kol))))
        merge(out, {"kol_sayisi": len(kol), "deneme_sharpe_sayisi": len(srs), "sr_islem_basina": sr, "dsr": dsr})
    gunler = sorted({t["entry_ts"][:10] for t in trades})
    kollar = sorted({t["arm"] for t in trades})
    if gunler and len(kollar) >= 2:
        d0, d1 = datetime.fromisoformat(gunler[0]).date(), datetime.fromisoformat(gunler[-1]).date()
        nd = (d1 - d0).days + 1
        if nd >= 2 * PBO_BOLUM:
            m = np.zeros((nd, len(kollar)))
            for t in trades:
                m[(datetime.fromisoformat(t["entry_ts"][:10]).date() - d0).days, kollar.index(t["arm"])] += t["net_r"]
            r = S.pbo_cscv(m, n_splits=PBO_BOLUM, max_combinations=2000, seed=SEED)
            out["pbo"], out["pbo_gun"], out["pbo_kol"] = float(r.pbo), nd, len(kollar)
        else:
            out["pbo_not"] = f"hesaplanamadı ({nd} gün < {2 * PBO_BOLUM})"
    else:
        out["pbo_not"] = "hesaplanamadı (en az 2 kol gerekir)"
    return out


def canli_sartlari(trades, rakip: dict, dayan: dict, sans: dict | None = None) -> dict:
    n = len(trades)
    rs = [t["net_r"] for t in trades]
    toplam_net = toplam(rs)
    c = cluster_mean(rs, [t["entry_ts"][:10] for t in trades]) if n else {"m": None, "lo": None, "G": 0}
    rej: dict = defaultdict(list)
    for t in trades:
        rej[t["regime"]].append(t["net_r"])
    rej_gun: dict = defaultdict(list)
    for t in trades:
        rej_gun[t["regime"]].append(t["entry_ts"][:10])
    rej_lo = {r: cluster_mean(v, rej_gun[r])["lo"] for r, v in rej.items() if len(v) >= REJIM_MIN_ISLEM}
    pozitif = sorted(r for r, lo in rej_lo.items() if lo is not None and lo > CANLI_GUVEN_ALT_SINIR and toplam(rej[r]) > 0)
    yz = rakip.get("rastgele_giris", {}).get("yuzdelik")
    m15 = dayan["masraf"].get(f"x{CANLI_MASRAF_CARPANI}", {})
    m15t = m15.get("toplam")
    maddeler = [
        {"ad": f"En az {CANLI_MIN_ISLEM} kapanmış işlem", "gecti": n >= CANLI_MIN_ISLEM, "deger": f"n = {n}"},
        {"ad": "Masraf sonrası net > 0 ve güven alt sınırı > 0",
         "gecti": bool(toplam_net > 0 and c["lo"] is not None and c["lo"] > CANLI_GUVEN_ALT_SINIR),
         "deger": f"net = {toplam_net:+.2f} R; ort = {(c['m'] if c['m'] is not None else float('nan')):+.3f} R; alt sınır = "
                  + (f"{c['lo']:+.3f}" if c["lo"] is not None else f"hesaplanamadı (gün sayısı {c.get('G', 0)} < {MIN_G})")},
        {"ad": f"En az {CANLI_MIN_REJIM} rejimde pozitif (rejim başına >= {REJIM_MIN_ISLEM} işlem ve gün kümeli güven alt sınırı > 0)",
         "gecti": len(pozitif) >= CANLI_MIN_REJIM,
         "deger": f"{len(pozitif)} rejim pozitif {pozitif}; rejim n: " + ", ".join(f"{r}={len(v)}" for r, v in sorted(rej.items()))
                  + "; alt sınır: " + ", ".join(f"{r}={lo:+.3f}" if lo is not None else f"{r}=hesaplanamadı" for r, lo in sorted(rej_lo.items()))},
        {"ad": f"Rastgele giriş yüzdeliği >= {CANLI_MIN_RASTGELE_YUZDELIK:g}",
         "gecti": bool(yz is not None and yz >= CANLI_MIN_RASTGELE_YUZDELIK),
         "deger": f"yüzdelik = {yz:.1f}" if yz is not None else "ölçülemedi (mum verisi yok)"},
        {"ad": f"Masraf x{CANLI_MASRAF_CARPANI} altında net > 0", "gecti": bool(m15t is not None and m15t > 0),
         "deger": f"net = {m15t:+.2f} R" if m15t is not None else "ölçülemedi"},
    ]
    if sans is not None:                          # sans verilmezse (eski çağrı) bu madde yok
        dds = [v["maks_dusus"]["p95"] for v in (sans, sans.get("blok") or {}) if v.get("maks_dusus")]
        kotu = max(dds) if dds else None
        maddeler.append({"ad": f"Monte Carlo %95 maks düşüş <= %{CANLI_MAKS_DUSUS * 100:.0f} (sermaye mandalı oranından türetilir: 1 - {SERMAYE_MANDALI_ORANI:g}; "
                               "karıştırma ve blok örneklemenin kötüsü)",
                         "gecti": bool(kotu is not None and kotu <= CANLI_MAKS_DUSUS),
                         "deger": (f"p95 = %{kotu * 100:.1f} (n={sans['n']})" if kotu is not None else "ölçülemedi (işlem yok)")})
    bilgi = dsr_pbo(trades)
    for m in maddeler:
        m["sonuc"] = "PASS" if m["gecti"] else "FAIL"
    dsr_s = (f"DSR = {bilgi['dsr']:.2f} (kol sayısı {bilgi.get('kol_sayisi')})" if bilgi["dsr"] is not None else bilgi.get("dsr_not", "DSR yok"))
    pbo_s = (f"PBO = {bilgi['pbo']:.2f} ({bilgi['pbo_gun']} gün x {bilgi['pbo_kol']} kol)" if bilgi["pbo"] is not None else bilgi.get("pbo_not", "PBO yok"))
    maddeler.append({"ad": "Çoklu deneme: deflated Sharpe ve PBO (BİLGİ, geçme şartı değil)", "gecti": True, "bilgi": True,
                     "sonuc": "BİLGİ", "deger": f"{dsr_s}; {pbo_s}; n={bilgi['n']}"})
    return {"n": n, "etiket": etiket(n), "maddeler": maddeler, "dsr_pbo": bilgi,
            "hepsi_gecti": all(m["gecti"] for m in maddeler if not m.get("bilgi")),
            "uyari": "Bu liste karar vermez; yalnız ölçer. Örnek küçükken PASS bile kanıt sayılmaz." if n < CANLI_MIN_ISLEM else None}


# ----------------------------------------------------------------------------- ek bolumler (7-12): yalniz olcum
def _sirali(trades):
    return sorted(trades, key=lambda t: (t["exit_ts"], t["trade_id"]))


def _dusus(pnl, kasa0: float) -> float:
    """Kasa kasa0'dan baslayarak pnl dizisini uygular; en buyuk tepe-dip dusus orani (sans_kuyruk ile ayni tanim)."""
    e = kasa0 + np.cumsum(np.asarray(pnl, float))
    pk = np.maximum.accumulate(np.concatenate([[kasa0], e]))[1:]
    return float(((pk - e) / pk).max()) if len(e) else 0.0


def baslangic_en_kotu_dusus(trades, kasa0: float) -> dict:
    """Fikir 1: eğriyi her işlemden başlatırız ('o işlemden canlıya başlasaydık'); her başlangıç için en kötü düşüş. Kasa her başlangıçta kasa0."""
    ts = _sirali(trades)
    n = len(ts)
    out = {"n": n, "etiket": etiket(n)}
    if not n:
        return {**out, "durum": "veri_yok"}
    pnl = np.array([t["pnl"] for t in ts], float)
    dd = np.array([_dusus(pnl[i:], kasa0) for i in range(n)])
    w = int(dd.argmax())
    return {**out, "durum": "ok", "en_kotu": float(dd[w]), "en_kotu_baslangic": {"trade_id": ts[w]["trade_id"], "zaman": ts[w]["entry_ts"]},
            "medyan": float(np.median(dd)), "en_iyi": float(dd.min()), "gercek_ilk_islemden": float(dd[0]), "baslangic_sayisi": n}


def kosu_testi(trades) -> dict:
    """Fikir 2: Wald-Wolfowitz koşu testi (kazanç = net R > 0, aksi kayıp; çıkış sırasıyla). Koşu sayısı beklenenden azsa kazanç/kayıplar
    kümeleniyor (z < 0). n < YETERSIZ_N ise sonuç verilmez."""
    ts = _sirali(trades)
    n = len(ts)
    out = {"n": n, "etiket": etiket(n)}
    seq = [t["net_r"] > 0 for t in ts]
    n1, n2 = sum(seq), n - sum(seq)
    merge(out, {"kazanc": n1, "kayip": n2})
    if n < YETERSIZ_N:
        return {**out, "durum": "yetersiz_ornek"}
    if n1 == 0 or n2 == 0:
        return {**out, "durum": "tek_sinif"}
    kosu = 1 + sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    mu = 2.0 * n1 * n2 / n + 1.0
    var = 2.0 * n1 * n2 * (2.0 * n1 * n2 - n) / (n * n * (n - 1.0))
    z = (kosu - mu) / math.sqrt(var) if var > 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return {**out, "durum": "ok", "kosu": kosu, "beklenen_kosu": mu, "z": z, "p": p,
            "yorum": "kümeleniyor (kosu az)" if z < 0 else "dönüşümlü (koşu çok)"}


def tf_masraf_tablosu(trades) -> dict:
    """Fikir 3: zaman dilimi x masraf: brüt R, masraf R, net R, masrafın brüte oranı (brüt <= 0 ise oran yok)."""
    g: dict = defaultdict(list)
    for t in trades:
        g[t["tf"]].append(t)
    sira = {"15m": 0, "1h": 1, "4h": 2, "1d": 3}
    rows = []
    for tf, ts in sorted(g.items(), key=lambda kv: (sira.get(kv[0], 9), kv[0])):
        brut = toplam(t["gross_pnl"] / t["planned_risk"] for t in ts)
        mas = toplam(cost_r(t) for t in ts)
        rows.append({"tf": tf, "n": len(ts), "brut_r": brut, "masraf_r": mas, "net_r": toplam(t["net_r"] for t in ts),
                     "masraf_brut_orani": (mas / brut) if brut > 0 else None, "etiket": etiket(len(ts))})
    return {"n": len(trades), "etiket": etiket(len(trades)), "satirlar": rows}


def verimlilik(trades) -> dict:
    """Fikir 4: giriş/çıkış verimi (`exits.py` ile aynı tanım): çıkış = (brüt R + MAE) / (MFE + MAE), 0-1'e kırpılır (payda < 0,05 tanımsız);
    giriş = MFE / (MFE + MAE) (girişten sonra görülen toplam yolun ne kadarı lehimizeydi); geri verme = MFE - brüt R. MFE/MAE yoksa işlem dışarıda."""
    cik, gir, geri, kaz = [], [], [], []
    for t in trades:
        mfe, mae = t.get("mfe_r"), t.get("mae_r")
        if mfe is None or mae is None:
            continue
        g = t["gross_pnl"] / t["planned_risk"]
        den = mfe + mae
        if den >= 0.05:
            cik.append(min(1.0, max(0.0, (g + mae) / den)))
            gir.append(min(1.0, max(0.0, mfe / den)))
        geri.append(mfe - g)
        if g > 0 and mfe > 0:
            kaz.append(min(1.0, g / mfe))
    n_var = sum(1 for t in trades if t.get("mfe_r") is not None and t.get("mae_r") is not None)
    ort = lambda xs: (toplam(xs) / len(xs)) if xs else None   # noqa: E731
    return {"n": len(trades), "n_mfe_mae_var": n_var, "n_mfe_mae_yok": len(trades) - n_var, "etiket": etiket(n_var),
            "cikis_verimi": ort(cik), "cikis_verimi_n": len(cik), "giris_verimi": ort(gir), "giris_verimi_n": len(gir),
            "ort_geri_verme_r": ort(geri), "kazananlarda_gerceklesen_mfe_orani": ort(kaz), "kazanan_n": len(kaz)}


def toparlanma(trades, kasa0: float) -> dict:
    """Fikir 5: düşüşten toparlanma süresi. Kasa eğrisi (çıkış sırasıyla) önceki zirveyi yeniden geçene kadar geçen süre; en uzun ve şu anki
    (şu an zirvenin altındaysa o zirveden beri). Süre hem işlem sayısı hem takvim günü."""
    ts = _sirali(trades)
    n = len(ts)
    out = {"n": n, "etiket": etiket(n)}
    if not n:
        return {**out, "durum": "veri_yok"}

    def gun(a, b):
        return (datetime.fromisoformat(b[:19]) - datetime.fromisoformat(a[:19])).total_seconds() / 86400.0
    eq, zirve, z_i, z_ts = kasa0, kasa0, -1, ts[0]["entry_ts"]
    en_uzun = {"islem": 0, "gun": 0.0, "bitti": True}
    for i, t in enumerate(ts):
        eq += t["pnl"]
        if eq >= zirve:                                  # yeni zirve: önceki düşüş (varsa) bitti
            uz = {"islem": i - z_i, "gun": gun(z_ts, t["exit_ts"]), "bitti": True}
            if i - z_i > 1 and uz["gun"] > en_uzun["gun"]:
                en_uzun = uz
            zirve, z_i, z_ts = eq, i, t["exit_ts"]
    simdi = {"islem": n - 1 - z_i, "gun": gun(z_ts, ts[-1]["exit_ts"]), "bitti": False} if eq < zirve else {"islem": 0, "gun": 0.0, "bitti": True}
    if not simdi["bitti"] and simdi["gun"] > en_uzun["gun"]:
        en_uzun = dict(simdi)
    return {**out, "durum": "ok", "en_uzun": en_uzun, "simdi": simdi, "su_an_dususte": eq < zirve,
            "kasa_son": eq, "kasa_zirve": zirve}


def ek_bolumler(trades, kasa0: float) -> dict:
    return {"baslangic_dusus": baslangic_en_kotu_dusus(trades, kasa0), "kosu_testi": kosu_testi(trades),
            "tf_masraf": tf_masraf_tablosu(trades), "verimlilik": verimlilik(trades), "toparlanma": toparlanma(trades, kasa0)}


# ----------------------------------------------------------------------------- ana akis
def rapor(trades_raw, decisions_raw, mumlar, *, kasa0: float, now: datetime, b: int = RASTGELE_B,
          runs: int = KARISTIRMA_SAYISI, seed: int = SEED, maliyet_cfg: dict | None = None) -> dict:
    trades, decisions, kilit = holdout_filtrele(trades_raw, decisions_raw)
    rakip = rakip_kiyasi(trades, mumlar, b, seed, maliyet_cfg, kasa0)
    dayan = dayaniklilik(trades, mumlar)
    sans = sans_kuyruk(trades, kasa0, runs, seed)
    return {"sema": SCHEMA, "uretim": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "n_islem": len(trades),
            "kilitli_donem_atilan_islem": kilit, "tohum": seed,
            "bolumler": {"rakip_kiyasi": rakip, "dayaniklilik": dayan,
                         "sans_kuyruk": sans,
                         "canli_sartlari": canli_sartlari(trades, rakip, dayan, sans),
                         "yon_denetimi": yon_denetimi(trades),
                         "kayip_kumeleri": kayip_kumeleri(trades)},
            "ek_bolumler": ek_bolumler(trades, kasa0)}


def _sozluk(d):
    return ", ".join(f"{k}={v}" for k, v in sorted((d or {}).items())) or "yok"


def _r(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}".replace(".", ",")


def _yz(x, nd=1):
    return "—" if x is None else f"%{x * 100:.{nd}f}".replace(".", ",")


def _render_ek(E) -> list[str]:
    if not E:
        return []
    L = []
    b = E["baslangic_dusus"]
    L += ["", f"## 7. Başlangıç noktasına göre en kötü düşüş (n={b['n']})" + (f" ({YETERSIZ})" if b["etiket"] else "")]
    if b["durum"] == "ok":
        L.append(f"- Her işlemden başlasaydık ({b['baslangic_sayisi']} başlangıç): en kötü düşüş {_yz(b['en_kotu'])} (başlangıç: işlem {b['en_kotu_baslangic']['trade_id']}, "
                 f"{b['en_kotu_baslangic']['zaman'][:10]}); medyan {_yz(b['medyan'])}; en iyi {_yz(b['en_iyi'])}; ilk işlemden başlayan {_yz(b['gercek_ilk_islemden'])}")
    else:
        L.append("- veri yok")
    k = E["kosu_testi"]
    L += ["", f"## 8. Kazanç/kayıp koşu testi (n={k['n']})" + (f" ({YETERSIZ})" if k["etiket"] else "")]
    if k["durum"] == "ok":
        L.append(f"- Kazanç {k['kazanc']} / kayıp {k['kayip']}; koşu {k['kosu']} (beklenen {k['beklenen_kosu']:.1f}), z={k['z']:+.2f}, p={k['p']:.3f}: {k['yorum']}")
    else:
        L.append(f"- {YETERSIZ if k['durum'] == 'yetersiz_ornek' else 'tek sınıf (hepsi kazanç ya da hepsi kayıp)'}: n={k['n']} (en az {YETERSIZ_N}); test yapılmadı")
    m = E["tf_masraf"]
    L += ["", f"## 9. Zaman dilimi × masraf (n={m['n']})" + (f" ({YETERSIZ})" if m["etiket"] else "")]
    for r in m["satirlar"]:
        L.append(f"- {r['tf']}: n={r['n']}, brüt {_r(r['brut_r'])} R, masraf {_r(-r['masraf_r'])} R, net {_r(r['net_r'])} R, masraf/brüt "
                 + ("—" if r["masraf_brut_orani"] is None else f"%{r['masraf_brut_orani'] * 100:.0f}") + (f" ({YETERSIZ})" if r["etiket"] else ""))
    v = E["verimlilik"]
    L += ["", f"## 10. Giriş/çıkış verimliliği (n={v['n']}, MFE/MAE olan {v['n_mfe_mae_var']})" + (f" ({YETERSIZ})" if v["etiket"] else "")]
    L.append(f"- Çıkış verimi {_yz(v['cikis_verimi'])} (n={v['cikis_verimi_n']}); giriş verimi {_yz(v['giris_verimi'])} (n={v['giris_verimi_n']}); "
             f"ort geri verme {_r(v['ort_geri_verme_r'])} R; kazananlarda gerçekleşen/işlem içi en iyi {_yz(v['kazananlarda_gerceklesen_mfe_orani'])} (n={v['kazanan_n']})")
    t = E["toparlanma"]
    L += ["", f"## 11. Düşüşten toparlanma süresi (n={t['n']})" + (f" ({YETERSIZ})" if t["etiket"] else "")]
    if t["durum"] == "ok":
        L.append(f"- En uzun düşüş: {t['en_uzun']['islem']} işlem, {t['en_uzun']['gun']:.1f} gün" + ("" if t["en_uzun"]["bitti"] else " (hâlâ sürüyor)"))
        L.append(f"- Şu an: " + (f"zirvenin altında, {t['simdi']['islem']} işlem, {t['simdi']['gun']:.1f} gündür" if t["su_an_dususte"] else "zirvede"))
    else:
        L.append("- veri yok")
    return L


def render_md(d: dict) -> str:
    B = d["bolumler"]
    L = [f"# Tur 1 ölçüm raporu", f"Üretim: {d['uretim']} · kapanmış işlem n = {d['n_islem']} · yalnız ölçüm, bot değişmez."]
    if d["n_islem"] < YETERSIZ_N:
        L.append(f"**{YETERSIZ} (n < {YETERSIZ_N}): aşağıdaki sayılar yalnız bilgidir, sonuç çıkarılamaz.**")
    rk = B["rakip_kiyasi"]
    L += ["", "## 1. Basit rakip kıyası", f"- Bizim: n={rk['bizim']['n']}, toplam {_r(rk['bizim']['toplam'])} R, ort {_r(rk['bizim']['ort'], 3)} R/işlem"]
    ra = rk["rastgele_giris"]
    if ra.get("durum") == "ok":
        L.append(f"- Rastgele giriş (n={ra['n']}, {ra['simulasyon_sayisi']} sim.): ort toplam {_r(ra['rastgele_ort_toplam_r'])} R; "
                 f"bizim yüzdelik **{ra['yuzdelik']:.1f}**, p={ra['p']:.3f}" + (f" ({YETERSIZ})" if ra.get("etiket") else ""))
    else:
        L.append("- Rastgele giriş: ölçülemedi (mum verisi yok)")
    if ra.get("atlanan"):
        L.append(f"  - Kıyas dışı kalan işlem: {ra['atlanan']} (neden: {_sozluk(ra.get('atlanan_neden'))}; zaman dilimi: {_sozluk(ra.get('atlanan_tf'))})")
    if ra.get("eski_masraf"):
        e = ra["eski_masraf"]
        L.append(f"  - Yan yana, eski sabit masrafla (k2: 2/5/5 bp): ort toplam {_r(e['rastgele_ort_toplam_r'])} R, bizim yüzdelik {e['yuzdelik']:.1f}, p={e['p']:.3f}")
    if ra.get("masraf_modeli") == "kagit_config":
        L.append("  - Masraf: kâğıt modeli (config kayma/komisyon); fonlama rakipte yok (k2 taşımaz), yani rakip bizden biraz ucuz.")
    at_ = rk.get("al_tut", {})
    if at_.get("durum") == "ok":
        L.append(f"- Al-tut (gerçek, long, eşit ağırlık, {at_['n_veri_var']}/{at_['n_enstruman']} enstrüman, {at_['donem'][0][:10]} → {at_['donem'][1][:10]}, masrafsız): "
                 f"ort getiri %{at_['ort_getiri']*100:+.1f}".replace(".", ",")
                 + (f"; bizim net/kasa başlangıcı %{at_['bizim_getiri']*100:+.1f} (farklı risk büyüklüğü, doğrudan kıyas değil)".replace(".", ",") if "bizim_getiri" in at_ else "")
                 + (f"; veri yok: {', '.join(at_['veri_yok_enstruman'])}" if at_["veri_yok_enstruman"] else "")
                 + (" (kilitli aralık dışarıda bırakıldı)" if at_["kilitli_aralik_disarida"] else ""))
    else:
        L.append("- Al-tut (gerçek): veri yok")
    for ad, k in (("Hep long", "hep_long"), ("Hep short", "hep_short")):
        L.append(f"- {ad} (aynı giriş zamanları, tahmin): toplam {_r(rk[k]['toplam'])} R, ort {_r(rk[k]['ort'], 3)} R")
    L.append("- Hiçbir şey yapmamak: 0 R")
    dy = B["dayaniklilik"]
    L += ["", "## 2. Gecikme / masraf dayanıklılığı", f"- Gerçek net: {_r(dy['gercek_net_r'])} R (n={dy['n']})"]
    for k, v in dy["gecikme"].items():
        L.append(f"- Giriş {k} gecikmeli: n={v['n']}, net {_r(v['toplam'])} R, kalan oran {_r(v['kalan_oran'], 2)}; durum {v['durum']}"
                 + (f"; veri yok (zaman dilimi): {_sozluk(v['veri_yok_tf'])}" if v.get("veri_yok_tf") else ""))
    for k, v in dy["masraf"].items():
        L.append(f"- Masraf {k}: net {_r(v['toplam'])} R, kalan oran {_r(v['kalan_oran'], 2)}")
    L.append(f"- 15 dk mum saati kayması: **tam ölçülemedi** (sinyali yeniden üretmek gerekir). Vekil: giriş 15 dk gecikmeli n="
             f"{dy['saat_kaymasi_15dk']['yaklasik_giris_15dk_gecikme']['n']}, net {_r(dy['saat_kaymasi_15dk']['yaklasik_giris_15dk_gecikme']['toplam'])} R")
    sk = B["sans_kuyruk"]
    L += ["", "## 3. Şans / kuyruk", f"- n={sk['n']}" + (f" ({YETERSIZ})" if sk["etiket"] else "") + f", {sk['karistirma']} karıştırma"]
    if "maks_dusus" in sk:
        L.append(f"- Maks düşüş p5/p50/p95: %{sk['maks_dusus']['p5']*100:.1f} / %{sk['maks_dusus']['p50']*100:.1f} / %{sk['maks_dusus']['p95']*100:.1f}; "
                 f"batış olasılığı (kasa <= %{SERMAYE_MANDALI_ORANI*100:.0f}): %{sk['batis_olasiligi']*100:.2f}")
    if "blok" in sk:
        b = sk["blok"]
        L.append(f"- Blok örnekleme (ortalama blok {b['ort_blok_uzunlugu']:.1f} işlem, {b['ornekleme']} çekim, n={sk['n']}) maks düşüş p5/p50/p95: "
                 f"%{b['maks_dusus']['p5']*100:.1f} / %{b['maks_dusus']['p50']*100:.1f} / %{b['maks_dusus']['p95']*100:.1f}; "
                 f"batış olasılığı: %{b['batis_olasiligi']*100:.2f} (kayıp kümelenmesini korur; karıştırmayla yan yana)")
    for k, v in sk["en_iyi_cikar"].items():
        L.append(f"- En iyi {k} işlem çıkarılırsa net: {_r(v['net_r'])} R")
    L += ["", "## 4. Canlıya geçiş şartları" + (f" ({YETERSIZ})" if B["canli_sartlari"]["etiket"] else "")]
    for m in B["canli_sartlari"]["maddeler"]:
        L.append(f"- **{m['sonuc']}** {m['ad']} — {m['deger']}")
    yd = B["yon_denetimi"]
    L += ["", "## 5. Yön denetimi" + (f" ({YETERSIZ})" if yd["etiket"] else "")]
    for r in yd["yon"]:
        L.append(f"- {r['anahtar']}: n={r['n']}, net {_r(r['toplam'])} R")
    kk = B["kayip_kumeleri"]
    L += ["", "## 6. Kayıp kümeleri" + (f" ({YETERSIZ})" if kk["etiket"] else ""), f"- {kk['n_kayip']} kayıp / {kk['n_islem']} işlem, {kk['kume_sayisi']} küme"]
    for r in kk["sayiya_gore"][:5]:
        L.append(f"- {r['kol']} · {r['rejim']} · {r['yon']} · {r['varlik_sinifi']} · {r['saat']}: {r['kayip_sayisi']} kayıp, {_r(r['toplam_kayip_r'])} R"
                 + (f" ({r['not']})" if r["not"] else ""))
    L += _render_ek(d.get("ek_bolumler"))
    return "\n".join(L) + "\n"
