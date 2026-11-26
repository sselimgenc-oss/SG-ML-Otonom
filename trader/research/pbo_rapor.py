#!/usr/bin/env python3
"""PBO raporu (docs/ml/pbo-holdout-muhur-spec.md bolum 2). Yalniz rapor: karar kapisi degildir, sunucuda calismaz.

  python research/pbo_rapor.py            # docs/ml/pbo-raporu.md + research/holdout/pbo_ozet.json yeniden yazilir (seed sabit)

Aday kumesi: (a) kagit kural ailesi kurulumlari (config/engine.paper.json `arms`) - var/backtests/*/trades.csv defterlerinden
kurulum (T1, R1) basina gunluk R serisi; (b) hafif donanim serileri (research/arm_harness.py -> research/arm_series/*.parquet): defteri olmayan kurulumlarin
(T1/R1 4s+1g, TF1, B1, H2, S1, F1 tum zaman dilimleri, M1@1h egitim-disi donem) holdout oncesi tarihsel barlardan uretilmis gunluk R serileri;
yapilandirma = zaman dilimi x on-kayitli parametre varyanti x maliyet. Defteri/denemesi olmayan aileler raporda "eksik" yazilir; uydurulmaz.
Yalniz 2026-05-01 oncesi veri; her okumada check_holdout cagrilir ve kilitli donemle kesisen satirlar dusurulur.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trader_core.stats import deflated_sharpe, pbo_cscv, return_moments  # noqa: E402
from trader_engine.holdout import HOLDOUT, check_holdout  # noqa: E402

N_SPLITS = 16
MAX_COMB = 2000
SEED = 0
BT_DIR = ROOT / "var" / "backtests"
ARMS_CONFIG = ROOT / "config" / "engine.paper.json"
ARM_DIR = ROOT / "research" / "arm_series"
OUT_MD = ROOT / "docs" / "ml" / "pbo-raporu.md"
OUT_JSON = ROOT / "research" / "holdout" / "pbo_ozet.json"
RULE_WINDOW = (pd.Timestamp("2024-11-01", tz="UTC"), pd.Timestamp("2025-11-01", tz="UTC"))   # IS kosularinin donemi (holdout oncesi)
PBO_LOW = 0.5
ARMS_SEEN: set[str] = set()      # defteri olan kurulum@tf (meta.trigger_tf)


# ------------------------------------------------------------------------------------- saf hesap
def family_stats(M: pd.DataFrame, *, n_trials_total: int | None = None) -> dict:
    """M: gun x yapilandirma getiri tablosu. Sabit (std=0) sutunlar PBO'dan cikar ama deneme sayisinda kalir."""
    n_total = int(n_trials_total if n_trials_total is not None else M.shape[1])
    T = int(M.shape[0])
    out = {"n_yapilandirma": n_total, "T": T}
    keep = (M.std(axis=0, ddof=0) > 0).to_numpy()
    out["n_kullanilan"] = int(keep.sum())
    if keep.sum() < 2 or T < 2 * N_SPLITS:
        out.update(durum="hesaplanamadi", neden=f"kullanilabilir yapilandirma {int(keep.sum())} (en az 2), gun {T} (en az {2 * N_SPLITS})")
        return out
    U = M.loc[:, keep]
    res = pbo_cscv(U.to_numpy(), n_splits=N_SPLITS, max_combinations=MAX_COMB, seed=SEED)
    srs = np.array([float(c.mean() / c.std(ddof=1)) for c in U.to_numpy().T])        # gunluk (donem basina) Sharpe
    best = int(np.argmax(srs))
    sk, ku = return_moments(U.iloc[:, best].to_numpy())
    dsr = deflated_sharpe(float(srs[best]), T, sk, ku, trial_srs=srs, n_trials=n_total)
    out.update(durum="tamam", pbo=float(res.pbo), n_kombinasyon=int(res.n_combinations),
               medyan_oos_goreli_sira=float(np.median(res.oos_rank)), prob_oos_kayip=float(res.prob_oos_loss),
               en_iyi_yapilandirma=str(U.columns[best]), en_iyi_sr_yillik=float(srs[best] * math.sqrt(365)),
               dsr=float(dsr) if np.isfinite(dsr) else None,
               yorum="asiri uyum riski dusuk-orta" if res.pbo < PBO_LOW else "asiri uyum riski yuksek")
    return out


def rule_series(trades: pd.DataFrame, window: tuple[pd.Timestamp, pd.Timestamp]) -> dict[str, pd.Series]:
    """Defter -> {kurulum: gunluk R toplami (cikis gunune gore)}, pencere = [lo, hi); holdout ile kesisirse check_holdout reddeder; pencere tum gunleri kapsar."""
    lo, hi = window
    check_holdout(lo.to_pydatetime(), hi.to_pydatetime())
    t = trades[trades["exit_ts"].notna() & (trades["exit_ts"].astype(str).str.len() > 0)].copy()
    t["x"] = pd.to_datetime(t["exit_ts"], utc=True, format="ISO8601")
    t = t[(t["x"] >= lo) & (t["x"] < hi)]
    days = pd.date_range(lo.floor("D"), (hi - pd.Timedelta(days=1)).floor("D"), freq="D")
    out = {}
    for setup, g in t.groupby("setup"):
        s = g["r_multiple"].groupby(g["x"].dt.floor("D")).sum()
        out[str(setup)] = s.reindex(days, fill_value=0.0)
    return out


def union_matrix(parts: list[pd.DataFrame]) -> pd.DataFrame:
    parts = [p for p in parts if p.shape[1]]
    if not parts:
        return pd.DataFrame()
    idx = parts[0].index
    for p in parts[1:]:
        idx = idx.union(p.index)
    idx = pd.date_range(idx.min(), idx.max(), freq="D")
    return pd.concat([p.reindex(idx, fill_value=0.0) for p in parts], axis=1)


# ------------------------------------------------------------------------------------- veri toplama
def arms_from_config(path: Path = ARMS_CONFIG) -> list[str]:
    return list(json.loads(Path(path).read_text(encoding="utf-8")).get("arms", []))


def load_rule_ledgers(bt_dir: Path = BT_DIR) -> tuple[dict[str, pd.DataFrame], list[dict]]:
    """-> ({kurulum: gun x defter tablosu}, atlananlar). Yalniz RULE_WINDOW ile cakisan ve 'IS' penceresini kapsayan defterler."""
    series: dict[str, dict[str, pd.Series]] = {}
    skipped = []
    for d in sorted(Path(bt_dir).glob("*/")):
        tp, mp = d / "trades.csv", d / "meta.json"
        if not tp.exists() or not mp.exists():
            skipped.append({"kosu": d.name, "neden": "trades.csv/meta.json yok"})
            continue
        meta = json.loads(mp.read_text(encoding="utf-8"))
        per = meta.get("period") or []
        if len(per) != 2:
            skipped.append({"kosu": d.name, "neden": "donem bilgisi yok"})
            continue
        p0, p1 = pd.Timestamp(per[0]), pd.Timestamp(per[1])
        if not (p0 <= RULE_WINDOW[0] and p1 >= RULE_WINDOW[1]):
            skipped.append({"kosu": d.name, "neden": f"donem {p0:%Y-%m-%d}..{p1:%Y-%m-%d} ortak IS penceresini kapsamiyor"})
            continue
        for setup, s in rule_series(pd.read_csv(tp), RULE_WINDOW).items():
            series.setdefault(setup, {})[f"{setup}:{d.name}"] = s
            ARMS_SEEN.add(f"{setup}@{meta.get('trigger_tf', '?')}")
    return {k: pd.DataFrame(v) for k, v in series.items()}, skipped


HARNESS_SEEN: set[str] = set()   # hafif donanim serisi olan kurulum@tf


def load_arm_series(arm_dir: Path) -> tuple[dict[str, pd.DataFrame], dict]:
    """research/arm_series: {kurulum: gun x kolon tablosu}, meta. Okumadan once gun araligi check_holdout'tan gecer."""
    arm_dir = Path(arm_dir)
    mp = arm_dir / "meta.json"
    if not mp.exists():
        return {}, {}
    meta = json.loads(mp.read_text(encoding="utf-8"))
    gp = arm_dir / "grid_declared.json"
    if gp.exists():
        gd = json.loads(gp.read_text(encoding="utf-8"))
        meta["izgara"], meta["izgara_sha256"] = gd["grid"], gd["sha256"]
    out = {}
    for f in sorted(arm_dir.glob("*.parquet")):
        df = pd.read_parquet(f).astype("float64")
        check_holdout(df.index.min().to_pydatetime(), (df.index.max() + pd.Timedelta(days=1)).to_pydatetime())
        out[f.stem] = df
    return out, meta


def build(bt_dir: Path = BT_DIR, arms: list[str] | None = None, arm_dir: Path | None = None) -> dict:
    arms = arms if arms is not None else arms_from_config()
    ARMS_SEEN.clear()
    HARNESS_SEEN.clear()
    rules, skipped = load_rule_ledgers(bt_dir)
    fams: list[dict] = []
    parts_all: list[pd.DataFrame] = []
    for setup in sorted(rules):
        M = rules[setup]
        r = {"aile": f"Kural {setup}", "tur": "kural", "kaynak": f"var/backtests/*/trades.csv ({M.shape[1]} defter, IS 2024-11-01..2025-10-31)"}
        r.update(family_stats(M))
        fams.append(r)
        parts_all.append(M)
    harness_meta: dict = {}
    if arm_dir is not None:
        series, harness_meta = load_arm_series(arm_dir)
        for setup, M in series.items():
            cols = {c: harness_meta.get("kolonlar", {}).get(c, {}) for c in M.columns}
            for c, m in cols.items():
                HARNESS_SEEN.add(f"{m.get('kurulum', setup)}@{m.get('tf', '?')}")
            is_m1 = setup == "M1"
            r = {"aile": "ML M1@1h (egitim-disi)" if is_m1 else f"Kural {setup} (harness)", "tur": "m1" if is_m1 else "kural_harness",
                 "kaynak": f"research/arm_series/{setup}.parquet ({M.shape[1]} kolon: "
                           + ("esik carpani x maliyet" if is_m1 else "tf x parametre varyanti x maliyet") + "; "
                           f"{M.index.min():%Y-%m-%d}..{M.index.max():%Y-%m-%d})"}
            r.update(family_stats(M))
            fams.append(r)
            parts_all.append(M.rename(columns=lambda c, k=setup: f"h:{c}"))
    U = union_matrix(parts_all)
    allr = {"aile": "TUM KUME", "tur": "tum", "kaynak": "yukaridaki tum yapilandirmalar, ortak gun izgarasinda (etkin olmayan gun = 0 R)"}
    allr.update(family_stats(U) if U.shape[1] else {"durum": "eksik", "neden": "veri yok", "n_yapilandirma": 0, "T": 0})
    fams.append(allr)
    excl = harness_meta.get("dislanan", {})
    arm_rows = [{"kurulum": a, "kayit": "var" if a in ARMS_SEEN else ("harness" if a in HARNESS_SEEN else "yok"),
                 **({"neden": excl[a]} if a in excl and a not in ARMS_SEEN and a not in HARNESS_SEEN else {})} for a in arms]
    return {"parametreler": {"n_splits": N_SPLITS, "max_combinations": MAX_COMB, "seed": SEED,
                             "holdout_oncesi_sinir": HOLDOUT[0].strftime("%Y-%m-%d")},
            "aileler": fams, "kurulumlar": arm_rows, "atlanan_defterler": skipped, "harness": harness_meta}


# ------------------------------------------------------------------------------------- cikti
def _f(x, nd=3) -> str:
    return "-" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}".replace(".", ",")


def COSTS_DECLARED(H: dict):
    return [tuple(c) for c in H.get("izgara", {}).get("costs_fee_mult_slip_bp", [])]


def _onceki_karsilastirma(res: dict) -> list[str]:
    """Kapsam genisletmesi oncesi (10 cift) ozetiyle yan yana PBO/DSR; anlik goruntu `research/holdout/pbo_ozet_10cift.json`."""
    snap = OUT_JSON.parent / "pbo_ozet_10cift.json"
    if not snap.exists():
        return []
    old = json.loads(snap.read_text(encoding="utf-8"))
    oa = {f["aile"]: f for f in old["aileler"] if f.get("durum") == "tamam" and f["tur"] in ("kural_harness", "m1", "tum")}
    L = ["", "### Kapsam genisletmesi: onceki (" + f"{len(old['harness']['ciftler'])} cift) ve yeni ({len(res['harness']['ciftler'])} cift) yan yana", "",
         "| Aile | Onceki PBO | Yeni PBO | Onceki DSR | Yeni DSR | Onceki T | Yeni T | Yeni en iyi yapilandirma |", "|---|---|---|---|---|---|---|---|"]
    for f in res["aileler"]:
        o = oa.get(f["aile"])
        if o is None or f.get("durum") != "tamam":
            continue
        L.append(f"| {f['aile']} | {_f(o['pbo'])} | {_f(f['pbo'])} | {_f(o['dsr'])} | {_f(f['dsr'])} | {o['T']} | {f['T']} | `{str(f['en_iyi_yapilandirma']).replace('|', '/')}` |")
    return L


def render_md(res: dict) -> str:
    P = res["parametreler"]
    L = ["# PBO raporu (holdout oncesi, yalniz rapor)", "",
         "Bu rapor **bilgi amaclidir**: karar kapisi degildir, hicbir islemi ya da kurulumu engellemez. Yalniz "
         f"`{P['holdout_oncesi_sinir']}` oncesi veri kullanildi; holdout satirlarina dokunulmadi. Uretim: `python research/pbo_rapor.py` "
         f"(seed {P['seed']}, sabit).", "", "## 1. Tablo", "",
         "| Aile | Yapilandirma (kullanilan) | T (gun) | PBO | Medyan OOS goreli sira | En iyi IS yapilandirma | Yillik SR | DSR | Yorum |",
         "|---|---|---|---|---|---|---|---|---|"]
    for f in res["aileler"]:
        if f.get("durum") == "tamam":
            L.append(f"| {f['aile']} | {f['n_yapilandirma']} ({f['n_kullanilan']}) | {f['T']} | {_f(f['pbo'])} | {_f(f['medyan_oos_goreli_sira'])} | "
                     f"`{str(f['en_iyi_yapilandirma']).replace('|', '/')}` | {_f(f['en_iyi_sr_yillik'], 2)} | {_f(f['dsr'])} | {f['yorum']} |")
        else:
            L.append(f"| {f['aile']} | {f.get('n_yapilandirma', 0)} | {f.get('T', 0)} | - | - | - | - | - | {f.get('durum')}: {f.get('neden', '')} |")
    L += ["", "PBO < 0,5 ise \"asiri uyum riski dusuk-orta\", aksi \"yuksek\" yazilir; esik bilgi amaclidir. DSR, en iyi (tam orneklem Sharpe) "
          "yapilandirma icin, o ailedeki tum yapilandirma sayisiyla (elenenler ve sabit sutunlar dahil) hesaplanir. Yillik SR = gunluk SR x sqrt(365).",
          "", "## 2. Yontem", "",
          f"- `trader_core.stats.pbo_cscv`, `n_splits={P['n_splits']}`, `max_combinations={P['max_combinations']}`, `seed={P['seed']}`, olcut Sharpe; "
          "- Kural ailelerinde yapilandirma = bir deneme kosusundaki kurulumun (T1, R1) gunluk R toplami (cikis gunune gore); kosular maliyet kolu, "
          "dolum modeli ve tetik zaman dilimi bakimindan farklidir. Ortak pencere IS 2024-11-01..2025-10-31 (365 gun, islemsiz gun = 0).",
          "- Hafif donanim aileleri (`Kural X (harness)`, `ML M1@1h (egitim-disi)`): yapilandirma = zaman dilimi x on-kayitli parametre varyanti x maliyet "
          "(bolum 5); gun izgarasi 2021-01-01..holdout oncesi son gun (islemsiz gun = 0 R). Kolonlar yuksek olcude iliskilidir (ayni sinyal akisi, farkli maliyet/parametre); "
          "PBO bu yuzden zaman-dilimi secimine ve parametre komsuluguna duyarlidir. Dusuk PBO SECIM KARARLILIGIDIR (IS kazananin OOS'ta da iyi sirada kalmasi), "
          "kârlilik degildir: harness ailelerinde 15m/1h kolonlari tutarli bicimde en kotu, 4s/1g kolonlari en iyi siradadir; DSR ~0 ve kucuk yillik SR, "
          "hicbir yapilandirmanin deneme sayisi duzeltmesinden sonra pozitif beklenti gostermedigini belirtir (T1 harness istisnasi: DSR 0,76, 4s+1g yalniz 48 kolon).",
          "- Sabit (std = 0) sutunlar CSCV'den cikarilir ama deneme sayisinda kalir.",
          "- Medyan OOS goreli sira: IS'te en iyi yapilandirmanin OOS goreli sirasinin (rank/(N+1)) kombinasyonlar uzerindeki medyani; 0,5 = medyan.",
          "- TUM KUME: ortak gun izgarasi (en erken..en gec gun); bir ailenin etkin olmadigi gunler 0 R'dir. Bu, pencereleri farkli aileleri tek matriste "
          "karistirir; sonuc yalniz kaba bir ust-kume gostergesidir.", "", "## 3. Deneme kaynaklari", "",
          "| Aile | Kaynak |", "|---|---|"]
    L += [f"| {f['aile']} | {f.get('kaynak', '')} |" for f in res["aileler"]]
    L += ["", "Kayit dosyalari (`research/trial_registry.csv`, `research/runs/*.json`) yalniz toplu istatistik tasir "
          "(gunluk getiri serisi yok); gunluk seriler `var/backtests/*/trades.csv` defterlerinden ve "
          "(defteri olmayan kurulumlar icin) `research/arm_harness.py` hafif donanim serilerinden (`research/arm_series/`) uretildi. "
          "Tam motor backtesti (`backtest --env paper`) kosulmadi.", "", "## 4. Eksik kalan aileler", ""]
    miss = [a for a in res["kurulumlar"] if a["kayit"] == "yok"]
    ok = [a["kurulum"] for a in res["kurulumlar"] if a["kayit"] == "var"]
    hs = [a["kurulum"] for a in res["kurulumlar"] if a["kayit"] == "harness"]
    L += [f"- `config/engine.paper.json` `arms` icinde motor defteri olan kurulumlar (kurulum duzeyinde): {', '.join(ok) or '-'}.",
          f"- Hafif donanim serisi olan kurulumlar ({len(hs)}): {', '.join(hs) or '-'}.",
          f"- Seri / defter **olmayan** {len(miss)} kurulum: {', '.join(a['kurulum'] for a in miss) or '-'}. Bunlar icin PBO hesaplanmadi; deneme uydurulmadi."]
    L += [f"  - `{a['kurulum']}`: {a.get('neden', 'deneme kaydi / defter yok')}" for a in miss if a.get("neden")]
    L += [
          "- Defter ailelerinde yalniz `T1` ve `R1` var; `T1` defterlerinin bir kismi (`ml_cand_v1b_native`, `s2_base_v1b`) farkli strateji surumu "
          "(`price_action_v1`) ve 10 ciftlik evrenle kosulmustur."]
    H = res.get("harness") or {}
    if H:
        L += ["", "## 5. Hafif donanim serileri (`research/arm_harness.py`)", "",
              "Amac: tam kagit backtest (~15 sn / 15 dk adim) cok yillik kosuya uygun degil; her kurulumun KENDI `compute()` fonksiyonu holdout oncesi tarihsel "
              "barlarda bir kez cagrilir, adaylar muhafazakar bir bar-yolu simulatoruyle cozulur, gunluk R toplami (cikis gunune gore, cift toplami) yazilir. "
              "Sinyal mantigi yeniden yazilmadi; simulator `trader_core.signals` yardimcilarini (`regime_flip_exit`, `TRAIL_START_R`, `TIME_STOP_BARS`) kullanir, "
              "hedef modu `trader_core.counterfactual.replay` ile (maliyetsiz) ve iz-stop `signals.trail_stop_path` ile testte karsilastirilir.", "",
              f"- Veri: `var/history` feather, okuma aninda `date < {P['holdout_oncesi_sinir']}` suzgeci; gun izgarasi {H['gun_izgarasi'][0]}..{H['gun_izgarasi'][1]}; "
              f"{len(H['ciftler'])} cift ({', '.join(H['ciftler'])}); `var/history` (muhurlu) disindaki ciftler `var/history_pre`den (`research/pbo_veri_indir.py`, data.binance.vision, "
              f"holdout satiri yok). `config/engine.paper.json` icindeki {len(H.get('gecmisi_olmayan_ciftler', []))} cift icin tarihsel mum bulunamadi ve kapsam disidir"
              + (f" ({', '.join(H.get('gecmisi_olmayan_ciftler', []))}; neden: data.binance.vision USDS-M arsivinde sembol yok)." if H.get('gecmisi_olmayan_ciftler') else "."),
              "- Simulator: giris = karar mumunu izleyen mumun acilisi (taraf aleyhine kayma); ayni barda stop ve hedef ikisi de degerse STOP once; acilis stop'u asmissa "
              "dolum acilista; `target` kipi: hedef + 48 mum zaman durdurma; `trail` kipi: 1R'de silahlanan iz-stop (`trail_atr` x ATR), rejim donusu ve iz-stop "
              "capraz cikisi sonraki barin acilisinda; kurulum+cift basina tek pozisyon, ayni-mum yeniden giris yasagi; cozulmemis islemler dusurulur.",
              "- Maliyet: taraf basina taker 5 bp x ucret carpani + kayma (giris = cikis = stop). Fonlama, `cost_overrides`, kapasite/risk tavanlari, dakika "
              "cozunurlugu yok; bu nedenle seri motor defterinin birebir kopyasi degil, ham aday akisinin muhafazakar bir tahminidir.",
              "- Deneme sayisi = her (kurulum, tf, parametre varyanti, maliyet) kolonu; sabit/bos kolonlar dahil DSR'ye girer.", "",
              "### On-kayitli izgara (sonuclara bakilmadan once `research/arm_series/grid_declared.json` olarak yazildi)", "",
              f"sha256: `{H.get('izgara_sha256', '-')}`. Maliyet izgarasi (ucret carpani, kayma bp): "
              + ", ".join(f"({a:g}x, {b:g} bp)" for a, b in COSTS_DECLARED(H)) + ".", "",
              "| Kurulum | Zaman dilimleri | Parametre varyantlari (OAT: varsayilan + dusuk/yuksek) | Kolon sayisi |", "|---|---|---|---|"]
        g = H.get("izgara", {})
        ncol = {}
        for c, m in H.get("kolonlar", {}).items():
            ncol[m["kurulum"]] = ncol.get(m["kurulum"], 0) + 1
        for setup, d in g.get("kurulumlar", {}).items():
            L.append(f"| {setup} | {', '.join(d['tfs'])} | {', '.join(d['parametre_varyantlari'])} | {ncol.get(setup, 0)} |")
        if "M1" in g:
            L.append(f"| M1 | {g['M1']['tf']} | esik carpani {', '.join(f'{x:g}' for x in g['M1']['esik_carpani'])} (paket esigi x carpan) | {ncol.get('M1', 0)} |")
        L += ["", "### Referans: varsayilan varyant, config maliyetiyle (kayma 2/2/5 bp, ucret 1x; deneme sayilmaz)", "",
              "| Kurulum@tf | Islem | Toplam R | Ort. R / islem |", "|---|---|---|---|"]
        for k, v in sorted(H.get("referans_cfg_maliyet", {}).items()):
            L.append(f"| {k.replace('|cfg', '')} | {v['n_islem']} | {_f(v['toplam_r'], 1)} | {_f(v['ort_r_islem'], 3)} |")
        if H.get("m1"):
            m = H["m1"]
            L += ["", "### M1 (egitim-disi donem)", "",
                  f"Gonderilen `M1@1h` paketinin egitim penceresi {m['egitim_penceresi']['start']}..{m['egitim_penceresi']['end']} (egitim satiri `max_rows`=400000 ile "
                  f"yalniz EN SON satirlara kirpilmis); bu pencereden ONCEKI tarihsel veri paketin gormedigi donemdir. Degerlendirme gunleri "
                  f"{m['degerlendirme_gunleri'][0]}..{m['degerlendirme_gunleri'][1]}; son sinyal mumu {m['son_sinyal_mumu']} (egitim baslangicindan "
                  "pencere + ufuk + 2 bar once: etiket/ozellik ortusmesi yok). Paket esigi " + _f(m["esik"], 4) + ". "
                  "Uyari: ozellik/etiket tasarimi (1,5 ATR stop, 3 ATR hedef, 48 bar) ve esik niceligi tum tarihsel veri goruldukten sonra secilmis olabilir; "
                  "bu donem model-uyumu acisindan temizdir, tasarim-secimi acisindan tam bagimsiz sayilmaz."]
        L += _onceki_karsilastirma(res)
        L += ["", "### Disarida birakilanlar", ""]
        L += [f"- `{k}`: {v}" for k, v in sorted(H.get("dislanan", {}).items())]
        L += ["", f"Calisma suresi: toplam {H.get('toplam_sure_sn', '-')} sn (4 cekirdek; kurulum basina: "
              + ", ".join(f"{k} {v} sn" for k, v in H.get("sure_sn", {}).items()) + ")."]
    if res["atlanan_defterler"]:
        L += ["", "Atlanan defterler:"] + [f"- `{s['kosu']}`: {s['neden']}" for s in res["atlanan_defterler"]]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    res = build(arm_dir=ARM_DIR)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(res), encoding="utf-8")
    for f in res["aileler"]:
        print(f"{f['aile']:<12} {f.get('durum'):<12} cfg={f.get('n_yapilandirma')} T={f.get('T')} PBO={_f(f.get('pbo'))} DSR={_f(f.get('dsr'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
