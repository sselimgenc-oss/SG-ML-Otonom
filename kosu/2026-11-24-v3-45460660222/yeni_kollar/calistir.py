#!/usr/bin/env python3
"""MF1/GF1/IN1 geri testi (YALNIZ ARASTIRMA; motor/ayar degismez). Kullanim (trader/ icinden):
  PYTHONPATH=src:paket python research/yeni_kollar/calistir.py --donem gelistirme --cikti ../sonuc_tur2
Kilitli donem (2025-07-01 ->) yalniz --kilidi-ac ile calisir. Cikti: <dizin>/sonuc.json + ozet.md."""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kol_sinyalleri as KS  # noqa: E402
import metrikler as MT  # noqa: E402
import ozellikler as OZ  # noqa: E402
import simulasyon as SM  # noqa: E402
import veri_yukle as V  # noqa: E402

KILIT_BAS = date(2025, 7, 1)
KOLLAR = ["MF1", "GF1", "IN1"]
# Tur 2: kol -> izinli zaman dilimi (kapatilanlar hesaplanmaz: 15m'ler, MF1 1h, IN1 1d)
IZINLI = {"MF1": ["4h", "1d"], "GF1": ["1h", "4h", "1d"], "IN1": ["1h", "4h"]}
TFLER = ["1h", "4h", "1d"]
TOHUM = 20251124
RASTGELE_N = 200            # gercek islem basina rastgele giris sayisi
ISINMA = 250                # ilk 250 mumda (gercek ve rastgele) giris yok
MIN_RISK = 0.006            # giris acilisinda risk/giris tabani (maliyet teyidi acikken)
Z_MIN_ISLEM = 50
YONLER = {"long": 1, "short": -1}
G = {}          # fork ile isciye paylasilan veri


def _ns(d: date) -> int:
    return int(np.datetime64(d.isoformat(), "ns").astype("int64"))


def satirlar_tablo(rows: list) -> dict:
    if not rows:
        return {k: np.zeros(0) for k in ("R", "tur", "tutma", "cift", "t_giris", "t_cikis", "d", "sa", "ha", "etiket")}
    f = lambda j, dt: np.array([r[j] for r in rows], dtype=dt)  # noqa: E731
    return {"R": f(0, float), "tur": f(1, int), "tutma": f(2, float), "cift": f(3, int), "t_giris": f(4, "int64"), "t_cikis": f(5, "int64"),
            "d": f(6, int), "sa": f(7, float), "ha": f(8, float),
            "etiket": np.array([r[9] if len(r) > 9 else "" for r in rows], dtype=object)}


def islem_dongusu(D, sig, maxm, mal, step, fonh, pi, min_risk=0.0):
    """sig: (t, -yon, yon, stop, hedef, sa, ha[, etiket]) listesi. Zaman sirasi (ayni mumda long once); ayni cift+kol+zd'de acik pozisyon varken
    giris yok (onceki cikis mumu >= karar mumu ise atla). -> satirlar (R, tur, tutma, cift, t_giris, t_cikis, yon, sa, ha, etiket)."""
    sig = sorted(sig, key=lambda x: (x[0], x[1]))
    rows, son = [], -1
    for x in sig:
        a, _, d, st, hd, sa, ha = x[:7]
        if a < son:
            continue
        r = SM.simule(D, a, d, st, hd, maxm, mal, step, fonh, min_risk)
        if r is None:
            continue
        son = r[4]
        rows.append((r[0], r[1], r[2], pi, int(D["t"][r[3]]), int(D["t"][r[4]]), d, sa, ha, x[7] if len(x) > 7 else ""))
    return rows


def rastgele_taban(D, atr, rows, rg, maxm, mal, step, fonh, bas_ns, min_risk):
    """Her gercek islem icin ayni yon + ayni takvim yili + ayni stop/hedef (ATR cinsinden) ile RASTGELE_N rastgele giris.
    Giris adaylari: ilk ISINMA mum sonrasi, veri baslangic kesimi icinde. -> [(yon, n_gecerli, toplam_R, kareler_toplami)] (islem basina)."""
    n = len(D["t"])
    yil = MT.yil_of(D["t"])
    gecerli = np.flatnonzero((atr > 0) & (D["t"] + step >= bas_ns))
    gecerli = gecerli[(gecerli >= ISINMA) & (gecerli <= n - 2)]
    yil_idx = {int(y): gecerli[yil[gecerli] == y] for y in np.unique(yil[gecerli])}
    out = []
    for x in rows:
        d, sa, ha = x[6], x[7], x[8]
        adaylar = yil_idx.get(int(MT.yil_of(np.array([x[4]]))[0]))
        k = 0
        s1 = s2 = 0.0
        if adaylar is not None and len(adaylar):
            for a in rg.choice(adaylar, RASTGELE_N):
                c0, a0 = D["c"][a], atr[a]
                r = SM.simule(D, int(a), d, c0 - d * sa * a0, c0 + d * ha * a0, maxm, mal, step, fonh, min_risk)
                if r is not None:
                    k += 1
                    s1 += r[0]
                    s2 += r[0] * r[0]
        out.append((d, k, s1, s2))
    return out


def isle_cift(arg):
    """Bir cift: tum zaman dilimi x kol x cfg. -> {(kol, tf, cfg): satirlar}, {(kol, tf): rastgele satirlar}."""
    pi, pair = arg
    mal = G["mal"][pair]
    bas_ns = G["bas_ns"]
    sonuc, rastgele = {}, {}
    fon = V.fonlama_dizi(G["fon"].get(pair))
    fonh = SM.fonlama_hazirla(fon)
    for ti, tf in enumerate(G["tfler"]):
        if pair not in G["mum"].get(tf, {}):
            continue
        D = V.dizilere(G["mum"][tf][pair])
        if len(D["t"]) < 300:
            continue
        ust = {tu: V.dizilere(G["mum"][tu][pair]) for tu in OZ.UST[tf] if pair in G["mum"].get(tu, {})}
        step = OZ.TF_NS[tf]
        Fd = {d: OZ.ozellik(D, tf, ust, fon, d) for d in (1, -1)}
        n = len(D["t"])
        for ki, kol in enumerate(G["kollar"]):
            if tf not in IZINLI[kol]:
                continue
            ham_fn, sin_fn = KS.KOLLAR[kol]
            ham = {d: ham_fn(Fd[d]) for d in (1, -1)}
            maxm = KS.MAX_MUM[kol]
            for cad, cfg in KS.cfg_listesi(kol).items():
                sig = []
                mr = MIN_RISK if cfg["maliyet"] else 0.0
                for d in (1, -1):
                    t, s, h, et = sin_fn(Fd[d], ham[d], cfg)
                    keep = (D["t"][t] + step >= bas_ns) & (t >= ISINMA) if len(t) else np.zeros(0, bool)
                    t, s, h, et = t[keep], s[keep], h[keep], et[keep]
                    F = Fd[d]
                    for a, b, c, e in zip(t.tolist(), s.tolist(), h.tolist(), et.tolist()):
                        at = F["atr"][a]
                        cf = F["c"][a]
                        sig.append((a, -d, d, d * b, d * c, (cf - b) / at, (c - cf) / at, e))
                rows = islem_dongusu(D, sig, maxm, mal, step, fonh, pi, mr)
                sonuc[(kol, tf, cad)] = rows
                if cad == "tam" and rows:
                    rg = np.random.default_rng(TOHUM + pi * 1009 + ti * 101 + ki * 11)
                    rastgele[(kol, tf, "tam")] = rastgele_taban(D, Fd[1]["atr"], rows, rg, maxm, mal, step, fonh, bas_ns, mr)
    return sonuc, rastgele


def tablo_yon(T, yon):
    if yon == "hepsi":
        return T
    m = T["d"] == YONLER[yon]
    return {k: v[m] for k, v in T.items()}


def hesapla(sonuc, rastgele, ciftler, tfler, kollar):
    out = {"ana": {}, "ablation": {}, "rastgele": {}}
    saat = {"15m": 0.25, "1h": 1.0, "4h": 4.0, "1d": 24.0}
    for kol in kollar:
        for tf in tfler:
            for cad in KS.cfg_listesi(kol):
                rows = sonuc.get((kol, tf, cad))
                if rows is None:
                    continue
                T = satirlar_tablo(rows)
                for yon in ("long", "short", "hepsi"):
                    m = MT.ozet(tablo_yon(T, yon), saat[tf], ciftler, detay=True)
                    if cad == "tam":
                        out["ana"].setdefault(kol, {}).setdefault(tf, {})[yon] = m
                    out["ablation"].setdefault(kol, {}).setdefault(tf, {}).setdefault(cad, {})[yon] = m
            rr = rastgele.get((kol, tf, "tam"))
            if rr is not None:
                Tg = satirlar_tablo(sonuc[(kol, tf, "tam")])
                Rr = np.array(rr, float).reshape(-1, 4)          # yon, n, toplam, kareler
                for yon in ("long", "short", "hepsi"):
                    a = tablo_yon(Tg, yon)
                    mk = np.ones(len(Rr), bool) if yon == "hepsi" else Rr[:, 0] == YONLER[yon]
                    out["rastgele"].setdefault(kol, {}).setdefault(tf, {})[yon] = rastgele_ozet(a["R"], Rr[mk])
            for yon in ("long", "short", "hepsi"):
                m = out["ana"].get(kol, {}).get(tf, {}).get(yon)
                if m and m["islem"]:
                    E = tablo_yon(satirlar_tablo(sonuc[(kol, tf, "tam")]), yon)
                    m["etiket_dokum"] = {str(e): {"islem": int((E["etiket"] == e).sum()), "ort_net_R": float(E["R"][E["etiket"] == e].mean()),
                                                  "toplam_net_R": float(E["R"][E["etiket"] == e].sum())} for e in sorted(set(E["etiket"].tolist()))}
    return out


def rastgele_ozet(R, Rr):
    """R: gercek islem R'leri; Rr: islem basina (yon, n, toplam, kareler). z = fark / sqrt(se_gercek^2 + se_rastgele^2); N < 50 ise 'yetersiz'.
    Rastgele ortalama = islem basina ortalamalarin ortalamasi (eslestirme korunur). se_rastgele = havuz std / sqrt(gercek islem sayisi) (temkinli)."""
    N = len(R)
    g = {"gercek_islem": int(N), "rastgele_islem": int(Rr[:, 1].sum()) if len(Rr) else 0, "gercek_ort_net_R": None, "rastgele_ort_net_R": None,
         "gercek_std_hata": None, "rastgele_std_hata": None, "fark": None, "z": None, "z_durum": "yetersiz"}
    if N == 0:
        return g
    g["gercek_ort_net_R"] = float(R.mean())
    if N > 1:
        g["gercek_std_hata"] = float(R.std(ddof=1) / np.sqrt(N))
    gecer = Rr[:, 1] > 0
    n_top = Rr[:, 1].sum()
    if not gecer.any() or n_top < 2:
        return g
    g["rastgele_ort_net_R"] = float((Rr[gecer, 2] / Rr[gecer, 1]).mean())
    ort = Rr[:, 2].sum() / n_top
    sd = float(np.sqrt(max(0.0, Rr[:, 3].sum() / n_top - ort * ort)))
    g["rastgele_std_hata"] = sd / float(np.sqrt(N))
    g["fark"] = g["gercek_ort_net_R"] - g["rastgele_ort_net_R"]
    if N >= Z_MIN_ISLEM and g["gercek_std_hata"] is not None:
        payda = float(np.hypot(g["gercek_std_hata"], g["rastgele_std_hata"]))
        if payda > 0:
            g["z"] = g["fark"] / payda
            g["z_durum"] = "ok"
    return g


def f2(x, k=3):
    return "-" if x is None else f"{x:.{k}f}"


def ozet_md(sonuc_json) -> str:
    j = sonuc_json
    s = [f"# Yeni kollar geri test ozeti ({j['meta']['donem']})", "",
         f"- Ciftler: {len(j['meta']['ciftler'])} (veri olan: {len(j['meta']['veri_olan_ciftler'])}); zaman dilimleri: {', '.join(j['meta']['tfler'])}",
         f"- Fonlama verisi olan cift: {j['meta']['fonlama_cift']}/{len(j['meta']['ciftler'])} (olmayanda veto kapali)",
         f"- Kesim (dislayici): {j['meta']['kesim']}; sure: {j['meta']['sure_sn']:.0f} sn", "",
         "R = net R (ucret+kayma+fonlama dusulmus). Yalniz arastirma; canliya baglanmaz.", "", "## Ana sonuc (tam teyit)", "",
         "| kol | tf | yon | islem | kazanma | ort R | toplam R | PF | maks dusus R | ort tutma (mum) | stop/hedef/zaman | rastgele ort R | fark | z |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for kol, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            for yon, m in d2.items():
                rg = j["rastgele"].get(kol, {}).get(tf, {}).get(yon, {})
                if m["islem"] == 0:
                    s.append(f"| {kol} | {tf} | {yon} | 0 | | | | | | | | | | |")
                    continue
                ct = m["cikis_turleri"]
                s.append(f"| {kol} | {tf} | {yon} | {m['islem']} | {f2(m['kazanma_orani'], 2)} | {f2(m['ort_net_R'])} | {f2(m['toplam_net_R'], 1)} | "
                         f"{f2(m['kar_faktoru'], 2)} | {f2(m['en_buyuk_dusus_R'], 1)} | {f2(m['ort_tutma_mum'], 1)} | {ct['stop']}/{ct['hedef']}/{ct['zaman']} | "
                         f"{f2(rg.get('rastgele_ort_net_R'))} | {f2(rg.get('fark'))} | {f2(rg.get('z'), 1) if rg.get('z') is not None else 'yetersiz'} |")
    s += ["", "## Sekil / seviye turune gore dokum (tam teyit, hepsi): tur: islem, ort R, toplam R", ""]
    for kol, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            m = d2.get("hepsi", {})
            if m.get("islem"):
                s.append(f"- {kol} {tf}: " + "; ".join(f"{e}: {v['islem']}, {v['ort_net_R']:.3f}, {v['toplam_net_R']:.1f}" for e, v in m["etiket_dokum"].items()))
    in1 = sum(j["ana"].get("IN1", {}).get(tf, {}).get("hepsi", {}).get("islem", 0) for tf in ("1h", "4h"))
    if "IN1" in j["ana"]:
        s += ["", f"IN1 kapatma kurali: 1h + 4h toplam islem = {in1} -> " + ("< 50: IN1 TUMUYLE KAPANIR (baska gevsetme yok)" if in1 < 50 else ">= 50: devam")]
    s += ["", "## Yil yil toplam R (tam teyit, her iki yon)", ""]
    for kol, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            m = d2.get("hepsi", {})
            if m.get("islem"):
                s.append(f"- {kol} {tf}: " + ", ".join(f"{y}: {v:.1f}" for y, v in m["yillik_toplam_R"].items()))
    s += ["", "## Cift dagilimi (tam teyit, hepsi): en iyi / en kotu 5 (toplam R)", ""]
    for kol, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            m = d2.get("hepsi", {})
            if m.get("islem"):
                e = ", ".join(f"{x['cift']} {x['toplam_R']:.1f}" for x in m["cift_en_iyi5"])
                k = ", ".join(f"{x['cift']} {x['toplam_R']:.1f}" for x in m["cift_en_kotu5"])
                s.append(f"- {kol} {tf}: iyi [{e}]; kotu [{k}]")
    s += ["", "## Teyit acma-kapama (ablation, her iki yon)", "", "| kol | tf | konfig | islem | ort R | toplam R | PF | kazanma |", "|---|---|---|---|---|---|---|---|"]
    for kol, d1 in j["ablation"].items():
        for tf, d2 in d1.items():
            for cad, d3 in d2.items():
                m = d3["hepsi"]
                if m["islem"] == 0:
                    s.append(f"| {kol} | {tf} | {cad} | 0 | | | | |")
                else:
                    s.append(f"| {kol} | {tf} | {cad} | {m['islem']} | {f2(m['ort_net_R'])} | {f2(m['toplam_net_R'], 1)} | {f2(m['kar_faktoru'], 2)} | {f2(m['kazanma_orani'], 2)} |")
    s += ["", "Not: GF1'de 'seviye', MF1'de 'zd'+'hacim', IN1'de 'seviye'+'hacim' teyidi yoktur (uygulanmaz). 'hic_teyit' = yalniz sekil + stop/hedef (rr>=1,5).", ""]
    return "\n".join(s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--donem", choices=["gelistirme", "kilitli"], required=True)
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--kilidi-ac", action="store_true", help="kilitli donemi calistirmak icin zorunlu")
    ap.add_argument("--ciftler", default=None, help="virgullu liste (varsayilan: engine.paper.json pairs)")
    ap.add_argument("--tf", default=",".join(TFLER))
    ap.add_argument("--kol", default=",".join(KOLLAR))
    ap.add_argument("--setuplar", choices=["v3"], default=None,
                    help="v3: setup_secimi.md'deki 12 kitap setupu x 4 ZD (15m,1h,4h,1d); --tf verilmezse tum 4; --kol yok sayilir")
    ap.add_argument("--setup", default=None, help="v3'te virgullu setup kimlikleri (varsayilan: 12'si)")
    ap.add_argument("--bas-ay", default=None, help="veri baslangic ayi (YYYY-MM) - duman kosusu icin")
    ap.add_argument("--kesim", default=None, help="gelistirmede kesim (YYYY-MM-DD, dislayici; <= 2025-07-01)")
    ap.add_argument("--isci", type=int, default=0)
    a = ap.parse_args(argv)
    if a.donem == "kilitli" and not a.kilidi_ac:
        print("HATA: kilitli donem yalniz --kilidi-ac ile calisir", file=sys.stderr)
        return 2
    t0 = time.time()
    if a.setuplar == "v3" and a.tf == ",".join(TFLER):
        a.tf = "15m,1h,4h,1d"
    tfler = [t for t in a.tf.split(",") if t]
    kollar = [k for k in a.kol.split(",") if k]
    mal = V.maliyetler()
    ciftler = [c for c in a.ciftler.split(",")] if a.ciftler else list(mal)
    if a.donem == "gelistirme":
        kesim = date.fromisoformat(a.kesim) if a.kesim else KILIT_BAS
        if kesim > KILIT_BAS:
            print("HATA: gelistirme kesimi 2025-07-01'den sonra olamaz", file=sys.stderr)
            return 2
        bas_ns = 0
    else:
        kesim = datetime.now(timezone.utc).date()
        bas_ns = _ns(KILIT_BAS)
    print(f"donem={a.donem} kesim={kesim} ciftler={len(ciftler)} tf={tfler}", flush=True)
    if a.setuplar == "v3":
        import v3_kos as K3
        kodlar = [x for x in a.setup.split(",") if x] if a.setup else list(K3.SV.SETUPLAR)
        bilinmeyen = [x for x in kodlar if x not in K3.SV.SETUPLAR]
        if bilinmeyen:
            print(f"HATA: bilinmeyen setup {bilinmeyen}", file=sys.stderr)
            return 2
        return K3.kos(a.donem, ciftler, tfler, kodlar, kesim, bas_ns, mal, a.bas_ay, a.isci, a.cikti, t0)
    mum, fon = V.yukle(ciftler, tfler, kesim, a.bas_ay)
    G.update(mal=mal, mum=mum, fon=fon, bas_ns=bas_ns, tfler=tfler, kollar=kollar)
    isler = list(enumerate(ciftler))
    nis = a.isci or min(mp.cpu_count(), 8)
    sonuc, rastgele = {}, {}
    ctx = mp.get_context("fork")
    with ctx.Pool(nis) as pool:
        for k, (s, r) in enumerate(pool.imap_unordered(isle_cift, isler), 1):
            for key, rows in s.items():
                sonuc.setdefault(key, []).extend(rows)
            for key, rows in r.items():
                rastgele.setdefault(key, []).extend(rows)
            print(f"[{k}/{len(isler)}] {time.time() - t0:.0f} sn", flush=True)
    sj = hesapla(sonuc, rastgele, ciftler, tfler, kollar)
    sj["meta"] = {"donem": a.donem, "kesim": kesim.isoformat(), "ciftler": ciftler, "tfler": tfler, "kollar": kollar,
                  "veri_olan_ciftler": sorted({p for tf in mum for p in mum[tf]}), "fonlama_cift": len(fon),
                  "fonlama_olmayan": [p for p in ciftler if p not in fon], "sure_sn": time.time() - t0, "tohum": TOHUM}
    out = Path(a.cikti)
    out.mkdir(parents=True, exist_ok=True)
    (out / "sonuc.json").write_text(json.dumps(sj, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "ozet.md").write_text(ozet_md(sj), encoding="utf-8")
    print(f"bitti: {time.time() - t0:.0f} sn -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
