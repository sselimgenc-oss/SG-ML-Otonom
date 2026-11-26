#!/usr/bin/env python3
"""Varlik sinifi (kripto / hisse / emtia) bazinda PBO + Deflated Sharpe dokumu. Yalniz olcum; karar kapisi degildir.

  python research/pbo_sinif.py   # research/holdout/pbo_sinif_ozet.json + docs/ml/pbo-raporu.md "Varlik sinifi dokumu" bolumu (seed sabit)

Kurulumlar: T1, R1 (arm_harness 4s+1g izgarasi, on-kayitli; cift basina yeniden kosulur, sinifa toplanir). Kol / agirlik / config / motor degismez.
Sinif kaynagi: config/engine.paper.json `clusters` (kripto_buyuk+kripto_diger = kripto 20, hisse = 20, metal+enerji_sanayi = emtia 4).

ON-YAZILI KURAL (sonuclar gorulmeden once yazildi; sonradan secilmez):
  * Aktif pencere = sinifin herhangi bir yapilandirmasinda ilk sifirdan farkli R'li gunden 2026-04-30'a (dahil). T = pencere gun sayisi.
    Pencere oncesi (sinifin verisi/islemi olmayan) sifir gunler T'ye ve CSCV'ye GIRMEZ.
  * T >= 128 -> n_splits 16 (pbo_rapor ile ayni); 64 <= T < 128 -> n_splits 8; T < 64 -> "hesaplanmadi" (PBO/DSR yazilmaz).
  * Sabit (std=0) sutunlar CSCV'den cikar ama DSR deneme sayisinda kalir; kullanilabilir yapilandirma < 2 ise hesaplanmadi.
  * max_combinations 2000, seed 0, olcut Sharpe; DSR en iyi tam-pencere Sharpe'li yapilandirma icin, sinifin TUM yapilandirma sayisiyla.
Holdout (2026-05-01..) okunmaz: arm_harness okuma aninda suzer; her okuma check_holdout'tan gecer.
"""
from __future__ import annotations

import importlib.util
import json
import math
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trader_core.stats import deflated_sharpe, pbo_cscv, return_moments  # noqa: E402
from trader_engine.holdout import HOLDOUT, check_holdout  # noqa: E402

import arm_harness as H  # noqa: E402

_spec = importlib.util.spec_from_file_location("pbo_rapor", Path(__file__).resolve().parent / "pbo_rapor.py")
PR = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PR)

SEED = 0
MAX_COMB = 2000
SETUPS = ("T1", "R1")
CLASSES = ("kripto", "hisse", "emtia")
CONFIG = ROOT / "config" / "engine.paper.json"
ARM_DIR = ROOT / "research" / "arm_series"
OUT_JSON = ROOT / "research" / "holdout" / "pbo_sinif_ozet.json"
OUT_MD = ROOT / "docs" / "ml" / "pbo-raporu.md"
SECTION = "## Varlik sinifi dokumu — 23.11 degerlendirmesi icin"
CLUSTER_CLASS = {"kripto_buyuk": "kripto", "kripto_diger": "kripto", "hisse": "hisse", "metal": "emtia", "enerji_sanayi": "emtia"}   # hisse_teknoloji kumesi 26.11 sahip karariyla silindi
RULE_TEXT = ("T >= 128 gun -> n_splits 16; 64 <= T < 128 -> n_splits 8; T < 64 -> hesaplanmadi. T = sinifin ilk sifirdan farkli R'li gunu..2026-04-30; "
             "pencere oncesi sifir gunler dahil degil.")


def n_splits_for(T: int) -> int | None:
    return 16 if T >= 128 else (8 if T >= 64 else None)


def pair_classes(config_path: Path = CONFIG) -> dict[str, str]:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for name, c in cfg["clusters"].items():
        k = CLUSTER_CLASS.get(name)
        if k is None:
            continue
        for p in c["pairs"]:
            if out.setdefault(p, k) != k:
                raise ValueError(f"cift birden cok sinifta: {p}")
    missing = [p for p in cfg["pairs"] if p not in out]
    if missing:
        raise ValueError(f"siniflandirilamayan ciftler: {missing}")
    return out


# ------------------------------------------------------------------------------------- saf hesap
def class_stats(M: pd.DataFrame, end: pd.Timestamp, ntrades: dict[str, int] | None = None) -> dict:
    """M: gun x yapilandirma (sinifa toplanmis). Aktif pencere kirpilir; kural modul basligindadir."""
    n_total = int(M.shape[1])
    out: dict = {"n_yapilandirma": n_total}
    nz = np.flatnonzero((M.to_numpy() != 0).any(axis=1)) if n_total else np.array([], dtype=int)
    if len(nz) == 0:
        out.update(T=0, durum="hesaplanmadi", neden="hic islem yok")
        return out
    first = M.index[nz[0]]
    W = M.loc[first:end]
    T = int(W.shape[0])
    out.update(T=T, pencere=[str(first.date()), str(end.date())])
    ns = n_splits_for(T)
    keep = (W.std(axis=0, ddof=0) > 0).to_numpy()
    out["n_kullanilan"] = int(keep.sum())
    if ns is None or keep.sum() < 2:
        out.update(durum="hesaplanmadi", neden=(f"T={T} < 64 (kural)" if ns is None else f"kullanilabilir yapilandirma {int(keep.sum())} < 2"))
        return out
    U = W.loc[:, keep]
    res = pbo_cscv(U.to_numpy(), n_splits=ns, max_combinations=MAX_COMB, seed=SEED)
    srs = np.array([float(c.mean() / c.std(ddof=1)) for c in U.to_numpy().T])
    best = int(np.argmax(srs))
    sk, ku = return_moments(U.iloc[:, best].to_numpy())
    dsr = deflated_sharpe(float(srs[best]), T, sk, ku, trial_srs=srs, n_trials=n_total)
    name = str(U.columns[best])
    out.update(durum="tamam", n_splits=ns, pbo=float(res.pbo), n_kombinasyon=int(res.n_combinations),
               medyan_oos_goreli_sira=float(np.median(res.oos_rank)), prob_oos_kayip=float(res.prob_oos_loss),
               en_iyi_yapilandirma=name, en_iyi_sr_yillik=float(srs[best] * math.sqrt(365)),
               en_iyi_islem=(ntrades or {}).get(name), dsr=float(dsr) if np.isfinite(dsr) else None,
               yorum="asiri uyum riski dusuk-orta" if res.pbo < PR.PBO_LOW else "asiri uyum riski yuksek")
    return out


# ------------------------------------------------------------------------------------- veri
def harness_by_class(setup_list, pairs_cls: dict[str, str], history_dir: Path = H.HISTORY, workers: int = 4):
    """-> {(kurulum, sinif): (gun x kolon DataFrame, {kolon: islem})}, toplam DataFrame sozlugu (tutarlilik)."""
    days = H.day_grid()
    pairs, missing = H.available_pairs(history_dir, list(pairs_cls))
    out, whole = {}, {}
    with mp.get_context("fork").Pool(workers) as pool:
        for setup in setup_list:
            parts = pool.map(H.run_pair, [(setup, p, str(history_dir)) for p in pairs])
            whole[setup] = H._merge(parts, days)[0]
            for cls in CLASSES:
                sel = [pp for pp, p in zip(parts, pairs) if pairs_cls[p] == cls]
                df, ntr = H._merge(sel, days) if sel else (pd.DataFrame(index=days), {})
                keep = [c for c in df.columns if not c.startswith("REF|")]
                out[(setup, cls)] = (df[keep], {k: v for k, v in ntr.items() if k in keep}, [p for p in pairs if pairs_cls[p] == cls])
    return out, whole, pairs, missing


def build(workers: int = 4) -> dict:
    pcls = pair_classes()
    end = (pd.Timestamp(HOLDOUT[0]) - pd.Timedelta(days=1)).floor("D")
    check_holdout(H.GRID_START.to_pydatetime(), (end + pd.Timedelta(days=1)).to_pydatetime())
    rows = []
    hc, whole, pairs, missing = harness_by_class(SETUPS, pcls, workers=workers)
    cons = {}
    for setup in SETUPS:      # tutarlilik: siniflarin toplami = research/arm_series/{setup}.parquet (float32 toleransi)
        ref = pd.read_parquet(ARM_DIR / f"{setup}.parquet").astype("float64")
        ssum = sum(hc[(setup, c)][0] for c in CLASSES).reindex(columns=ref.columns, fill_value=0.0)
        cons[setup] = {"maks_mutlak_fark": float(np.nanmax(np.abs(ssum.to_numpy() - np.nan_to_num(ref.to_numpy())))), "kolon_sayisi_esit": list(ssum.columns) == list(ref.columns)}
    for setup in SETUPS:
        for c in CLASSES:
            M, ntr, cp = hc[(setup, c)]
            r = {"kurulum": setup, "sinif": c, "kaynak": "arm_harness 4s+1g (kolon = tf x parametre varyanti x maliyet)",
                 "cift_sayisi": len(cp), "veri_olan_cift": len(cp), "ciftler": cp}
            r.update(class_stats(M, end, ntr))
            rows.append(r)
    ledger = {}
    ozet = ROOT / "research" / "holdout" / "pbo_ozet.json"
    if ozet.exists():
        for f in json.loads(ozet.read_text(encoding="utf-8"))["aileler"]:
            if f["aile"] in ("Kural T1", "Kural R1"):
                ledger[f["aile"]] = {k: f.get(k) for k in ("n_yapilandirma", "T", "pbo", "dsr", "medyan_oos_goreli_sira")}
    return {"parametreler": {"seed": SEED, "max_combinations": MAX_COMB, "kural": RULE_TEXT, "holdout_oncesi_sinir": HOLDOUT[0].strftime("%Y-%m-%d"),
                             "izgara_sha256": H.grid_sha()},
            "siniflar": {c: [p for p in pcls if pcls[p] == c] for c in CLASSES}, "sinif_kaynagi": "config/engine.paper.json clusters",
            "gecmisi_olmayan_ciftler": missing, "satirlar": rows, "tutarlilik_arm_series": cons,
            "defter_sinif_ustu_onceki_sonuc": ledger}


# ------------------------------------------------------------------------------------- cikti
def _f(x, nd=3) -> str:
    return PR._f(x, nd)


def render_section(res: dict) -> str:
    P = res["parametreler"]
    L = [SECTION, "",
         "Yalniz olcum: kol ayari, agirlik, config ve motor degismedi; karar kapisi degildir. Uretim: `python research/pbo_sinif.py` (`pbo_rapor.py` dosyayi bastan yazar; bu komut ondan SONRA kosulur) "
         f"(seed {P['seed']}, tek komut; holdout {P['holdout_oncesi_sinir']} oncesi). Kural ve sinif tablosu asagida; hepsi sonuc gorulmeden once betiğe yazildi.", "",
         "**Ne olduklari.** `T1` / `R1`: kagit kural ailesi kurulumlari (trend / aralik).", "",
         "**Sinif kaynagi** (`config/engine.paper.json` `clusters`): "
         + "; ".join(f"{c} {len(res['siniflar'][c])} cift ({', '.join(p.split('/')[0] for p in res['siniflar'][c])})" for c in CLASSES) + ".",
         f"Tarihsel mumu olmayan {len(res['gecmisi_olmayan_ciftler'])} hisse cifti kapsam disi: {', '.join(p.split('/')[0] for p in res['gecmisi_olmayan_ciftler'])}.", "",
         f"**Onceden yazili kural.** {P['kural']} Sabit sutunlar CSCV'den cikar, deneme sayisinda kalir; max_combinations {P['max_combinations']}, olcut Sharpe, "
         "DSR en iyi tam-pencere Sharpe'li yapilandirma icin sinifin tum yapilandirma sayisiyla. Pencere kirpmasi nedeniyle kripto T'si, mevcut §1 tablosundaki "
         "(2021-01-01..) T'den kisa olabilir; mevcut tablodaki aile-ustu degerlerle birebir karsilastirilmaz.", "",
         "| Kurulum | Sinif | Cift (verisi olan) | Yapilandirma (kullanilan) | T (gun) | n_splits | PBO | Medyan OOS goreli sira | En iyi IS yapilandirma (islem) | Yillik SR | DSR | Not |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res["satirlar"]:
        if r.get("durum") == "tamam":
            isl = "" if r.get("en_iyi_islem") is None else f" ({r['en_iyi_islem']})"
            L.append(f"| {r['kurulum']} | {r['sinif']} | {r['cift_sayisi']} | {r['n_yapilandirma']} ({r['n_kullanilan']}) | {r['T']} | {r['n_splits']} | {_f(r['pbo'])} | "
                     f"{_f(r['medyan_oos_goreli_sira'])} | `{r['en_iyi_yapilandirma'].replace('|', '/')}`{isl} | "
                     f"{_f(r['en_iyi_sr_yillik'], 2)} | {_f(r['dsr'])} | {r['yorum']} |")
        else:
            L.append(f"| {r['kurulum']} | {r['sinif']} | {r.get('cift_sayisi', 0)} | {r.get('n_yapilandirma', 0)} | {r.get('T', 0)} | - | - | - | - | - | - | {r.get('durum')}: {r.get('neden', '')} |")
    L += ["", "PBO < 0,5 ise \"dusuk-orta\", aksi \"yuksek\" yazilir (bilgi amacli). Dusuk PBO secim kararliligidir, karlilik degildir; DSR ~0 deneme sayisi duzeltmesinden "
          "sonra pozitif beklenti gorunmedigini belirtir. Hisse/emtia kolonlari ayni sinyal akisinin maliyet/parametre kopyalari oldugundan yuksek olcude iliskilidir "
          "ve sinif basina islem sayisi azdir (kisa pencere): PBO/DSR bu siniflarda dusuk gucle okunmali, kesin hukum degil.", "",
          "**Tutarlilik:** siniflarin toplami `research/arm_series/{T1,R1}.parquet` ile "
          + ", ".join(f"{k}: maks fark {v['maks_mutlak_fark']:.2e}" for k, v in res["tutarlilik_arm_series"].items()) + " (float32 yuvarlamasi).", ""]
    return "\n".join(L) + "\n"


def write_md(section: str, path: Path = OUT_MD) -> None:
    txt = Path(path).read_text(encoding="utf-8")
    i = txt.find(SECTION)
    if i >= 0:
        txt = txt[:i].rstrip("\n") + "\n"
    Path(path).write_text(txt.rstrip("\n") + "\n\n" + section, encoding="utf-8")


def main(argv=None) -> int:
    res = build()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_md(render_section(res))
    for r in res["satirlar"]:
        print(f"{r['kurulum']:<7}{r['sinif']:<7} {r.get('durum'):<12} cfg={r.get('n_yapilandirma')} T={r.get('T')} PBO={_f(r.get('pbo'))} DSR={_f(r.get('dsr'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
