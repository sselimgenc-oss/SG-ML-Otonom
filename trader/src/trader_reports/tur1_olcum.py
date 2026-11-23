"""Tur 1 / Asama A olcum raporu (`tur1_olcum`): YALNIZ OLCUM, botu degistirmez, karar yoluna bagli degildir.

Kagit defteri (kapanan islemler + karar satirlari) ve market.sqlite mumlari uzerinden alti bolum:
  1 basit rakip kiyasi   2 gecikme/masraf dayanikliligi   3 sans/kuyruk testi
  4 canliya gecis sartlari   5 yon denetimi   6 kayip kumeleri
Kilitli donem (HOLDOUT) okunmaz: islemler `guard.trade_locked` ile elenir, mum okumalari `guard.check_window` gecidinden gecer.
Az islemde hicbir bolum kesinlik taklit etmez: her bolum n verir ve `yetersiz ornek` bayragi tasir. Tohumlar sabittir.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import guard, inputs as I
from .guard import BacktestArgError
from .stats import MIN_G, cluster_mean

SCHEMA = "ml.tur1_olcum.v1"

# ----------------------------------------------------------------------------- SABITLER (duz Turkce)
YETERSIZ_N = 30              # Bir bolumde bu sayidan az islem varsa sonuc "yetersiz ornek"tir; sayilar yalniz bilgidir.
CANLI_MIN_ISLEM = 300        # Canliya gecis sarti 1: en az bu kadar kapanmis islem.
CANLI_GUVEN_ALT_SINIR = 0.0  # Sart 2: islem basina net R ortalamasinin guven alt siniri bunun USTUNDE olmali.
CANLI_MIN_REJIM = 2          # Sart 3: en az bu kadar farkli rejimde toplam net pozitif olmali.
REJIM_MIN_ISLEM = 10         # Bir rejimin "sayilmasi" icin o rejimde en az bu kadar islem gerekir.
CANLI_MIN_RASTGELE_YUZDELIK = 90.0   # Sart 4: sonucumuz rastgele giris dagiliminin en az bu yuzdeligine ulasmali.
CANLI_MASRAF_CARPANI = 1.5   # Sart 5: masraflar bu carpanla buyutulunca da net > 0 kalmali.
SERMAYE_MANDALI_ORANI = 0.85  # Kasa baslangicin bu oraninin altina inerse sermaye mandali kapanir (batis).
KARISTIRMA_SAYISI = 10000    # Islem sirasi karistirma sayisi (en az 5000).
RASTGELE_B = 2000            # Rastgele giris simulasyon sayisi (ilk asama k2'de 500; p kucukse 5000'e cikar).
GECIKME_BARLARI = (1, 2)     # Girisi kendi zaman diliminin kac mum geciktirecegiz.
MASRAF_CARPANLARI = (1.5, 2.0)
EN_IYI_CIKAR = (1, 2, 5)
KUME_ILK_N = 10              # Kayip kumeleri: listelenecek kume sayisi.
KUME_MIN_ISLEM = 3           # Bir kumede bundan az kayip varsa "az ornek" notu.
SEED = 20261123              # Tum rastgelelik bu tohumdan turetilir.

TF_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}   # 1d: market.sqlite 4s mumlarından kurulur (tam 6 mumlu UTC günü)
SIDE_FEATURE = "f_side_sign"                      # araştırma paketi: meta.features içinde
SIDE_FEATURES = ("f_side_sign", "side_long")      # canlı aile paketi: meta.ozellikler içinde "side_long"
FEATURE_KEYS = ("features", "ozellikler")         # paket şeması: araştırma = features, canlı aile (ortak_ogrenme) = ozellikler
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
            "bar_close_ts": b, "final_action": g("final_action"), "skip_reason": g("skip_reason"), "ml_score": _f(g("ml_score"))}


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


def rastgele_giris(trades, mumlar: MumDeposu | None, b: int = RASTGELE_B, seed: int = SEED) -> dict:
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
    k = RG.k2_toplam({key: (v[0], v[1]) for key, v in gr.items()}, gercek, b, seed, guard.H1_MS)
    sim = k["sim"]
    yuzdelik = 100.0 * float((np.sum(sim < gercek) + 0.5 * np.sum(sim == gercek)) / sim.size)
    return {"durum": "ok", "n": n, "atlanan": atlanan, "atlanan_neden": at["neden"], "atlanan_tf": at["tf"],
            "kapsanan_tf": sorted({k[1] for k in gr}), "simulasyon_sayisi": int(sim.size), "bizim_toplam_r": gercek,
            "bizim_ort_r": gercek / n, "rastgele_ort_toplam_r": float(sim.mean()), "rastgele_ort_r": float(sim.mean() / n),
            "rastgele_p5": float(np.percentile(sim, 5)), "rastgele_p50": float(np.percentile(sim, 50)),
            "rastgele_p95": float(np.percentile(sim, 95)), "yuzdelik": yuzdelik, "p": k["p"], "asama": k["asama"],
            "not": "Rastgele giriş k2 varsayılan masrafıyla (kayma 2bp, stop kayması 5bp, taker 5bp) fiyatlanır; bizimki gerçek masraflıdır.",
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


def rakip_kiyasi(trades, mumlar, b: int = RASTGELE_B, seed: int = SEED) -> dict:
    rs = [t["net_r"] for t in trades]
    return {"n": len(trades), "etiket": etiket(len(trades)), "bizim": ozet(rs),
            "rastgele_giris": rastgele_giris(trades, mumlar, b, seed),
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


def ml_filtre_yon(decisions) -> dict:
    out = {}
    for side in ("long", "short"):
        ds = [d for d in decisions if d["side"] == side]
        red = sum(1 for d in ds if d["skip_reason"] == "ml_filter")
        gir = sum(1 for d in ds if d["final_action"] == "entered")
        n = red + gir
        out[side] = {"ml_reddi": red, "girildi": gir, "n": n, "red_orani": (red / n) if n else None, "etiket": etiket(n)}
    return out


def _lgbm_onem(model: dict, idx: int, nf: int) -> tuple[float, float]:
    cnt, gain = np.zeros(nf), np.zeros(nf)
    for tr in model.get("tree_info", []):
        st = [tr["tree_structure"]]
        while st:
            nd = st.pop()
            if "split_feature" in nd:
                cnt[nd["split_feature"]] += 1
                gain[nd["split_feature"]] += float(nd.get("split_gain", 0.0))
                st += [nd["left_child"], nd["right_child"]]
    return (float(cnt[idx] / cnt.sum()) if cnt.sum() else 0.0, float(gain[idx] / gain.sum()) if gain.sum() else 0.0)


def yon_ozelligi_onemi(models_dir) -> dict:
    """Model paketleri yön özelliğinin önemini açığa çıkarıyorsa raporlar. İki şema desteklenir: araştırma paketi
    (`meta.features`, `f_side_sign`) ve canlı aile paketi (`meta.ozellikler`, `side_long`; `paket/ortak_ogrenme/filtre.py`).
    Lojistik -> |katsayı| payı (katsayılar standartlaştırılmış özellik üzerinedir, iki şemada da öyle saklanır);
    lgbm -> bölme sayısı/kazanç payı. Okunamayan paket atlanmaz: `okunamadi` satırı olarak yazılır. Eski kol paketleri
    (`eski_kol/` klasörü, canlıda kullanılmaz) taranmaz."""
    p = Path(models_dir) if models_dir else None
    if p is None or not p.is_dir():
        return {"durum": "paket_dizini_yok", "paketler": []}
    rows = []
    for f in sorted(p.rglob("*.json")):
        if "eski_kol" in f.parts:
            continue
        try:
            pkg = json.loads(f.read_text(encoding="utf-8"))
            meta, m = pkg["meta"], pkg["model"]
            sema = next(k for k in FEATURE_KEYS if isinstance(meta.get(k), list))
            feats = list(meta[sema])
        except (OSError, ValueError, KeyError, TypeError, StopIteration, AttributeError):
            continue
        ad = next((a for a in SIDE_FEATURES if a in feats), None)
        if ad is None:
            rows.append({"paket": f.name, "durum": "ozellik_listede_yok", "sema": sema})
            continue
        i = feats.index(ad)
        if m.get("kind") == "logistic":
            try:
                c = np.abs(np.asarray(m["coef"], float))
                if len(c) != len(feats):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                rows.append({"paket": f.name, "durum": "katsayi_bozuk", "sema": sema})
                continue
            rows.append({"paket": f.name, "tur": "logistic", "sema": sema, "ozellik": ad,
                         "onem_payi": float(c[i] / c.sum()) if c.sum() else 0.0,
                         "katsayi": float(m["coef"][i]), "sira": int(1 + (c > c[i]).sum()), "ozellik_sayisi": len(feats)})
        elif m.get("kind") == "lgbm":
            sc, kz = _lgbm_onem(m, i, len(feats))
            rows.append({"paket": f.name, "tur": "lgbm", "sema": sema, "ozellik": ad, "bolme_payi": sc, "kazanc_payi": kz,
                         "ozellik_sayisi": len(feats)})
        else:
            rows.append({"paket": f.name, "durum": "bilinmeyen_tur", "sema": sema})
    return {"durum": "ok" if rows else "paket_yok", "paketler": rows}


def yon_denetimi(trades, decisions, models_dir=None) -> dict:
    return {"n": len(trades), "etiket": etiket(len(trades)),
            "yon": _kirilim(trades, lambda t: t["side"]),
            "yon_rejim": _kirilim(trades, lambda t: (t["side"], t["regime"])),
            "yon_varlik_sinifi": _kirilim(trades, lambda t: (t["side"], t["asset"])),
            "yon_kol": _kirilim(trades, lambda t: (t["side"], t["arm"])),
            "ml_filtre": ml_filtre_yon(decisions), "yon_ozelligi": yon_ozelligi_onemi(models_dir)}


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
def canli_sartlari(trades, rakip: dict, dayan: dict) -> dict:
    n = len(trades)
    rs = [t["net_r"] for t in trades]
    toplam_net = toplam(rs)
    c = cluster_mean(rs, [t["entry_ts"][:10] for t in trades]) if n else {"m": None, "lo": None, "G": 0}
    rej: dict = defaultdict(list)
    for t in trades:
        rej[t["regime"]].append(t["net_r"])
    pozitif = sorted(r for r, v in rej.items() if len(v) >= REJIM_MIN_ISLEM and toplam(v) > 0)
    yz = rakip.get("rastgele_giris", {}).get("yuzdelik")
    m15 = dayan["masraf"].get(f"x{CANLI_MASRAF_CARPANI}", {})
    m15t = m15.get("toplam")
    maddeler = [
        {"ad": f"En az {CANLI_MIN_ISLEM} kapanmış işlem", "gecti": n >= CANLI_MIN_ISLEM, "deger": f"n = {n}"},
        {"ad": "Masraf sonrası net > 0 ve güven alt sınırı > 0",
         "gecti": bool(toplam_net > 0 and c["lo"] is not None and c["lo"] > CANLI_GUVEN_ALT_SINIR),
         "deger": f"net = {toplam_net:+.2f} R; ort = {(c['m'] if c['m'] is not None else float('nan')):+.3f} R; alt sınır = "
                  + (f"{c['lo']:+.3f}" if c["lo"] is not None else f"hesaplanamadı (gün sayısı {c.get('G', 0)} < {MIN_G})")},
        {"ad": f"En az {CANLI_MIN_REJIM} rejimde pozitif (rejim başına >= {REJIM_MIN_ISLEM} işlem)",
         "gecti": len(pozitif) >= CANLI_MIN_REJIM,
         "deger": f"{len(pozitif)} rejim pozitif {pozitif}; rejim n: " + ", ".join(f"{r}={len(v)}" for r, v in sorted(rej.items()))},
        {"ad": f"Rastgele giriş yüzdeliği >= {CANLI_MIN_RASTGELE_YUZDELIK:g}",
         "gecti": bool(yz is not None and yz >= CANLI_MIN_RASTGELE_YUZDELIK),
         "deger": f"yüzdelik = {yz:.1f}" if yz is not None else "ölçülemedi (mum verisi yok)"},
        {"ad": f"Masraf x{CANLI_MASRAF_CARPANI} altında net > 0", "gecti": bool(m15t is not None and m15t > 0),
         "deger": f"net = {m15t:+.2f} R" if m15t is not None else "ölçülemedi"},
    ]
    for m in maddeler:
        m["sonuc"] = "PASS" if m["gecti"] else "FAIL"
    return {"n": n, "etiket": etiket(n), "maddeler": maddeler, "hepsi_gecti": all(m["gecti"] for m in maddeler),
            "uyari": "Bu liste karar vermez; yalnız ölçer. Örnek küçükken PASS bile kanıt sayılmaz." if n < CANLI_MIN_ISLEM else None}


# ----------------------------------------------------------------------------- ana akis
def rapor(trades_raw, decisions_raw, mumlar, *, kasa0: float, now: datetime, models_dir=None, b: int = RASTGELE_B,
          runs: int = KARISTIRMA_SAYISI, seed: int = SEED) -> dict:
    trades, decisions, kilit = holdout_filtrele(trades_raw, decisions_raw)
    rakip = rakip_kiyasi(trades, mumlar, b, seed)
    dayan = dayaniklilik(trades, mumlar)
    return {"sema": SCHEMA, "uretim": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "n_islem": len(trades),
            "kilitli_donem_atilan_islem": kilit, "tohum": seed,
            "bolumler": {"rakip_kiyasi": rakip, "dayaniklilik": dayan,
                         "sans_kuyruk": sans_kuyruk(trades, kasa0, runs, seed),
                         "canli_sartlari": canli_sartlari(trades, rakip, dayan),
                         "yon_denetimi": yon_denetimi(trades, decisions, models_dir),
                         "kayip_kumeleri": kayip_kumeleri(trades)}}


def _sozluk(d):
    return ", ".join(f"{k}={v}" for k, v in sorted((d or {}).items())) or "yok"


def _r(x, nd=2):
    return "—" if x is None else f"{x:+.{nd}f}".replace(".", ",")


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
    for k, v in sk["en_iyi_cikar"].items():
        L.append(f"- En iyi {k} işlem çıkarılırsa net: {_r(v['net_r'])} R")
    L += ["", "## 4. Canlıya geçiş şartları" + (f" ({YETERSIZ})" if B["canli_sartlari"]["etiket"] else "")]
    for m in B["canli_sartlari"]["maddeler"]:
        L.append(f"- **{m['sonuc']}** {m['ad']} — {m['deger']}")
    yd = B["yon_denetimi"]
    L += ["", "## 5. Yön denetimi" + (f" ({YETERSIZ})" if yd["etiket"] else "")]
    for r in yd["yon"]:
        L.append(f"- {r['anahtar']}: n={r['n']}, net {_r(r['toplam'])} R")
    for s, v in yd["ml_filtre"].items():
        L.append(f"- ML filtre {s}: ret {v['ml_reddi']} / girildi {v['girildi']}, ret oranı {_r(v['red_orani'], 2)}")
    yo = yd["yon_ozelligi"]
    L.append(f"- Yön özelliği (f_side_sign / side_long) önemi: {yo['durum']}; " + ("; ".join(f"{p['paket']}: {p.get('onem_payi', p.get('kazanc_payi', p.get('durum')))}" for p in yo["paketler"][:5]) or "paket yok"))
    kk = B["kayip_kumeleri"]
    L += ["", "## 6. Kayıp kümeleri" + (f" ({YETERSIZ})" if kk["etiket"] else ""), f"- {kk['n_kayip']} kayıp / {kk['n_islem']} işlem, {kk['kume_sayisi']} küme"]
    for r in kk["sayiya_gore"][:5]:
        L.append(f"- {r['kol']} · {r['rejim']} · {r['yon']} · {r['varlik_sinifi']} · {r['saat']}: {r['kayip_sayisi']} kayıp, {_r(r['toplam_kayip_r'])} R"
                 + (f" ({r['not']})" if r["not"] else ""))
    return "\n".join(L) + "\n"
