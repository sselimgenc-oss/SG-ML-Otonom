"""v3 kosusu: 12 kitap setupu x 4 zaman dilimi (15m,1h,4h,1d) x yon (long/short/hepsi). calistir.py --setuplar v3 ile cagrilir.
Evren: engine.paper.json'daki TUM ciftler (maliyet tablosu ayni liste); arsivde gecmisi kisa olan cifte veri oldugu kadar bakilir (raporda yazar).
Mevcut kurallar aynen: karar t kapanisi, giris t+1 acilisi, ayni mumda stop+hedef -> stop, bosluk dolumu, masraf, fonlama, mum boslugu.
Ust ZD kullanilmaz (setuplarda ust zd sarti yok; kendi teyidi eklenmez) -> yalniz istenen zaman dilimleri yuklenir."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import metrikler as MT  # noqa: E402
import setuplar_v3 as SV  # noqa: E402
import simulasyon as SM  # noqa: E402
import simulasyon_v3 as S3  # noqa: E402
import veri_yukle as V  # noqa: E402

TFLER_V3 = ["15m", "1h", "4h", "1d"]
TOHUM = 20251124
RASTGELE_N = 200            # setup x cift x zd x yon grubu basina rastgele giris cekilisi
ISINMA = 250
MIN_RISK = 0.006
Z_MIN_ISLEM = 50
TF_NS = V.TF_NS
SAAT = {"15m": 0.25, "1h": 1.0, "4h": 4.0, "1d": 24.0}
YONLER = {"long": 1, "short": -1}
G = {}


def islem_dongusu_v3(D, sig, maxm, mal, step, fonh, pi, min_risk, sayac):
    """sig: (t, d, sp, sa, ha, etiket). Ayni cift+setup+zd'de acik pozisyon varken giris yok (son_karar_min). IC_CUBUK: ayni t'deki iki yonlu
    emir OCO (ilk dolan; ayni mumda ikisi de tetiklenirse aciliste daha yakin olan; sonra stop onceligi)."""
    gruplar = {}
    for x in sig:
        gruplar.setdefault(x[0], []).append(x)
    rows, son = [], -1
    for t in sorted(gruplar):
        if t < son:
            sayac["acik_atlanan"] += len(gruplar[t])
            continue
        adaylar = []
        for x in gruplar[t]:
            _, d, sp, sa, ha, et = x
            if "emir" in sp:
                r = S3.emir_dolum(D, t, d, sp["emir"], sp["pencere"], step)
                if r is not None:
                    adaylar.append((r[0], abs(r[1] - D["o"][r[0]]), x, r[1]))
            else:
                e = t + 1
                if e < len(D["t"]) and D["t"][e] - D["t"][t] == step:
                    adaylar.append((e, 0.0, x, D["o"][e]))
        if not adaylar:
            sayac["sim_yok"] += len(gruplar[t])
            continue
        e, _, x, fill = min(adaylar, key=lambda z: (z[0], z[1]))
        _, d, sp, sa, ha, et = x
        r = S3.simule_v3(D, e, fill, d, sp, maxm, mal, step, fonh, min_risk if sp.get("stop") is not None else 0.0)
        if r is None:
            sayac["sim_yok"] += 1
            continue
        son = r[6]
        rows.append((r[0], r[1], r[2], pi, int(D["t"][r[3]]), int(D["t"][r[4]]), d, sa, ha, et))
    return rows


def rastgele_grup(D, atr, rows, d, rg, maxm, mal, step, fonh, bas_ns, min_risk):
    """Yon d'deki gercek islemlerden yerine koyarak RASTGELE_N islem sec (ayni yil, ayni yon, ayni stop/hedef ATR mesafesi; stop yoksa 2 ATR R birimi,
    hedef yoksa yok; sinyal cikislari/dinamik hedef yok, zaman stopu ayni) ve rastgele girisle simule et. -> (n_gercek, k, toplam, kareler)."""
    n = len(D["t"])
    yil = MT.yil_of(D["t"])
    gec = np.flatnonzero((atr > 0) & (D["t"] + step >= bas_ns))
    gec = gec[(gec >= ISINMA) & (gec <= n - 2)]
    yil_idx = {int(y): gec[yil[gec] == y] for y in np.unique(yil[gec])}
    sub = [x for x in rows if x[6] == d]
    k = 0
    s1 = s2 = 0.0
    if not sub:
        return (0, 0, 0.0, 0.0)
    for j in rg.integers(0, len(sub), RASTGELE_N):
        x = sub[j]
        sa, ha = x[7], x[8]
        ad = yil_idx.get(int(MT.yil_of(np.array([x[4]]))[0]))
        if ad is None or not len(ad):
            continue
        a = int(rg.choice(ad))
        c0, a0 = D["c"][a], atr[a]
        sp = {}
        if np.isfinite(sa) and sa > 0:
            sp["stop"] = c0 - d * sa * a0
        else:
            sp["rbirim"] = 2 * a0
        if np.isfinite(ha) and ha > 0:
            sp["hedef"] = c0 + d * ha * a0
        r = S3.simule_v3(D, a + 1, D["o"][a + 1], d, sp, maxm, mal, step, fonh, min_risk if "stop" in sp else 0.0)
        if r is not None:
            k += 1
            s1 += r[0]
            s2 += r[0] * r[0]
    return (len(sub), k, s1, s2)


def isle_cift(arg):
    pi, pair = arg
    mal = G["mal"][pair]
    bas_ns = G["bas_ns"]
    fonh = SM.fonlama_hazirla(V.fonlama_dizi(G["fon"].get(pair)))
    sonuc, rastgele, sayaclar, kapsam = {}, {}, {}, {}
    for ti, tf in enumerate(G["tfler"]):
        if pair not in G["mum"].get(tf, {}):
            continue
        D = V.dizilere(G["mum"][tf][pair])
        n = len(D["t"])
        kapsam[tf] = {"mum": int(n), "ilk": str(np.datetime64(int(D["t"][0]), "ns"))[:10] if n else None,
                      "son": str(np.datetime64(int(D["t"][-1]), "ns"))[:10] if n else None}
        if n < 300:
            continue
        step = TF_NS[tf]
        Fd = {d: SV.ozellik(D, d) for d in (1, -1)}
        for ki, kod in enumerate(G["setuplar"]):
            maxm = SV.SETUPLAR[kod][1]
            sig = SV.gercek_sinyaller(kod, Fd)
            sig = [x for x in sig if x[0] >= ISINMA and D["t"][x[0]] + step >= bas_ns]
            sayac = {"sinyal_long": sum(1 for x in sig if x[1] == 1), "sinyal_short": sum(1 for x in sig if x[1] == -1), "acik_atlanan": 0, "sim_yok": 0}
            rows = islem_dongusu_v3(D, sig, maxm, mal, step, fonh, pi, MIN_RISK, sayac)
            sonuc[(kod, tf)] = rows
            sayaclar[(kod, tf)] = sayac
            rg = np.random.default_rng(TOHUM + pi * 1009 + ti * 101 + ki * 11)
            rastgele[(kod, tf)] = [(d,) + rastgele_grup(D, Fd[1]["atr"], rows, d, rg, maxm, mal, step, fonh, bas_ns, MIN_RISK) for d in (1, -1)]
    return pi, sonuc, rastgele, sayaclar, kapsam


# ----------------------------------------------------------------------------------------------- ozet
def rastgele_ozet(R, rr):
    """R: gercek R'ler. rr: (n_gercek, k, toplam, kareler) gruplari. Rastgele ortalama = gruplarin ortalamalari, gercek islem sayisiyla agirlikli
    (gercek ile ayni ciftlere/yonlere dagilim). z = fark / hypot(se_gercek, se_rastgele); N < 50 ise 'yetersiz'."""
    N = len(R)
    g = {"gercek_islem": int(N), "rastgele_islem": int(sum(x[1] for x in rr)), "gercek_ort_net_R": None, "rastgele_ort_net_R": None,
         "gercek_std_hata": None, "rastgele_std_hata": None, "fark": None, "z": None, "z_durum": "yetersiz"}
    if N == 0:
        return g
    g["gercek_ort_net_R"] = float(R.mean())
    if N > 1:
        g["gercek_std_hata"] = float(R.std(ddof=1) / np.sqrt(N))
    ok = [x for x in rr if x[1] > 0 and x[0] > 0]
    if not ok:
        return g
    w = np.array([x[0] for x in ok], float)
    m = np.array([x[2] / x[1] for x in ok])
    m2 = np.array([x[3] / x[1] for x in ok])
    ort = float((w * m).sum() / w.sum())
    sd = float(np.sqrt(max(0.0, (w * m2).sum() / w.sum() - ort * ort)))
    g["rastgele_ort_net_R"] = ort
    g["rastgele_std_hata"] = sd / float(np.sqrt(N))
    g["fark"] = g["gercek_ort_net_R"] - ort
    if N >= Z_MIN_ISLEM and g["gercek_std_hata"] is not None:
        payda = float(np.hypot(g["gercek_std_hata"], g["rastgele_std_hata"]))
        if payda > 0:
            g["z"] = g["fark"] / payda
            g["z_durum"] = "ok"
    return g


def hesapla(sonuc, rastgele, sayaclar, ciftler, tfler, setuplar):
    import calistir as CA
    out = {"ana": {}, "rastgele": {}, "sayac": {}}
    for kod in setuplar:
        for tf in tfler:
            rows = sonuc.get((kod, tf))
            if rows is None:
                continue
            T = CA.satirlar_tablo(rows)
            sy = sayaclar.get((kod, tf), {})
            out["sayac"].setdefault(kod, {})[tf] = sy
            rr_all = rastgele.get((kod, tf), [])
            for yon in ("long", "short", "hepsi"):
                Ty = CA.tablo_yon(T, yon)
                m = MT.ozet(Ty, SAAT[tf], ciftler, detay=True)
                if m["islem"]:
                    m["cikis_turleri"]["sinyal"] = int((np.asarray(Ty["tur"]) == 3).sum())
                    m["etiket_dokum"] = {str(e): {"islem": int((Ty["etiket"] == e).sum()), "ort_net_R": float(Ty["R"][Ty["etiket"] == e].mean()),
                                                  "toplam_net_R": float(Ty["R"][Ty["etiket"] == e].sum())} for e in sorted(set(Ty["etiket"].tolist()))}
                if yon == "hepsi":
                    m["sinyal"] = sy.get("sinyal_long", 0) + sy.get("sinyal_short", 0)
                elif yon == "long":
                    m["sinyal"] = sy.get("sinyal_long", 0)
                else:
                    m["sinyal"] = sy.get("sinyal_short", 0)
                out["ana"].setdefault(kod, {}).setdefault(tf, {})[yon] = m
                rr = [x[1:] for x in rr_all if yon == "hepsi" or x[0] == YONLER[yon]]
                out["rastgele"].setdefault(kod, {}).setdefault(tf, {})[yon] = rastgele_ozet(Ty["R"], rr)
    return out


def f2(x, k=3):
    return "-" if x is None else f"{x:.{k}f}"


def ozet_md(j) -> str:
    me = j["meta"]
    s = [f"# v3 kitap setuplari geri test ozeti ({me['donem']})", "",
         f"- Ciftler: {len(me['ciftler'])} (engine.paper.json); veri olan: {len(me['veri_olan_ciftler'])}; zaman dilimleri: {', '.join(me['tfler'])}",
         f"- Fonlama verisi olan cift: {me['fonlama_cift']}/{len(me['ciftler'])} (fonlama maliyeti islenir; veto YOK)",
         f"- Kesim (dislayici): {me['kesim']}; sure: {me['sure_sn']:.0f} sn",
         f"- Rastgele kiyas: setup x cift x zd x yon grubu basina {RASTGELE_N} cekilis (ayni yil/yon/stop-hedef ATR mesafesi), gercek islem sayisiyla agirlikli.",
         "- R = net R (ucret+kayma+fonlama dusulmus). Stopu olmayan IND_MA_KESISIM / IND_FIYAT_MA'da R birimi 2 ATR(14). Yalniz arastirma.", "",
         "## Ana sonuc", "",
         "| setup | kat | tf | yon | sinyal | islem | kazanma | ort R | toplam R | PF | maks dusus R | stop/hedef/zaman/sinyal | rastgele ort R | fark | z |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for kod, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            for yon, m in d2.items():
                rg = j["rastgele"][kod][tf][yon]
                if m["islem"] == 0:
                    s.append(f"| {kod} | {SV.kategori(kod)} | {tf} | {yon} | {m['sinyal']} | 0 | | | | | | | | | |")
                    continue
                ct = m["cikis_turleri"]
                s.append(f"| {kod} | {SV.kategori(kod)} | {tf} | {yon} | {m['sinyal']} | {m['islem']} | {f2(100 * m['kazanma_orani'], 1)}% | {f2(m['ort_net_R'])} | "
                         f"{f2(m['toplam_net_R'], 1)} | {f2(m['kar_faktoru'], 2)} | {f2(m['en_buyuk_dusus_R'], 1)} | {ct['stop']}/{ct['hedef']}/{ct['zaman']}/{ct['sinyal']} | "
                         f"{f2(rg.get('rastgele_ort_net_R'))} | {f2(rg.get('fark'))} | {f2(rg.get('z'), 1) if rg.get('z') is not None else 'yetersiz'} |")
    s += ["", "sinyal = kapanis kararinda uretilen aday sayisi; islem = acik pozisyon/MIN_RISK/bosluk/veri-sonu elemelerinden sonra simule edilen.", "",
          "## Alt tur dokumu (hepsi): tur: islem, ort R, toplam R", ""]
    for kod, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            m = d2["hepsi"]
            if m["islem"]:
                s.append(f"- {kod} {tf}: " + "; ".join(f"{e}: {v['islem']}, {v['ort_net_R']:.3f}, {v['toplam_net_R']:.1f}" for e, v in m["etiket_dokum"].items()))
    s += ["", "## Yil yil toplam R (hepsi)", ""]
    for kod, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            m = d2["hepsi"]
            if m["islem"]:
                s.append(f"- {kod} {tf}: " + ", ".join(f"{y}: {v:.1f}" for y, v in m["yillik_toplam_R"].items()))
    s += ["", "## Cift dagilimi (hepsi): en iyi / en kotu 5 (toplam R) ve islem veren cift sayisi", ""]
    for kod, d1 in j["ana"].items():
        for tf, d2 in d1.items():
            m = d2["hepsi"]
            if m["islem"]:
                e = ", ".join(f"{x['cift']} {x['toplam_R']:.1f}" for x in m["cift_en_iyi5"])
                k = ", ".join(f"{x['cift']} {x['toplam_R']:.1f}" for x in m["cift_en_kotu5"])
                s.append(f"- {kod} {tf} ({m['cift_sayisi']} cift): iyi [{e}]; kotu [{k}]")
    s += ["", "## Veri kapsami (cift x zd: mum sayisi, ilk tarih). Kisa gecmisli ya da arsivde olmayan ciftler", ""]
    kisa = []
    for p in me["ciftler"]:
        kp = me["kapsam"].get(p, {})
        for tf in me["tfler"]:
            k = kp.get(tf)
            if k is None:
                kisa.append(f"- {p} {tf}: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)")
            elif k["ilk"] and k["ilk"] > me["tam_gecmis_esigi"][tf]:
                kisa.append(f"- {p} {tf}: {k['mum']} mum, {k['ilk']} -> {k['son']} (kisa gecmis)")
    s += kisa or ["- (hepsi tam)"]
    s.append("")
    return "\n".join(s)


def kos(donem, ciftler, tfler, setuplar, kesim, bas_ns, mal, bas_ay, isci, cikti, t0):
    """Veri yukle -> cift basina is (fork havuzu) -> hesapla -> sonuc.json + ozet.md. Donus 0."""
    import json
    import multiprocessing as mp
    import time
    mum, fon = {}, {}
    for tf in tfler:                                       # ust ZD gerekmez: yalniz istenen zaman dilimleri
        mum[tf] = V.DV.indir(ciftler, bas_ay or V.BAS_AY[tf], kesim, V.HAM_DIR, tf=tf, log=print)
    fon = V.fonlama_indir(ciftler, bas_ay or "2021-01", kesim, log=print)
    G.update(mal=mal, mum=mum, fon=fon, bas_ns=bas_ns, tfler=tfler, setuplar=setuplar)
    nis = isci or min(mp.cpu_count(), 8)
    sonuc, rastgele, sayaclar, kapsam = {}, {}, {}, {}
    with mp.get_context("fork").Pool(nis) as pool:
        for k, (pi, s, r, sy, kp) in enumerate(pool.imap_unordered(isle_cift, list(enumerate(ciftler))), 1):
            for key, rows in s.items():
                sonuc.setdefault(key, []).extend(rows)
            for key, rows in r.items():
                rastgele.setdefault(key, []).extend(rows)
            for key, v in sy.items():
                a = sayaclar.setdefault(key, {x: 0 for x in v})
                for x in v:
                    a[x] += v[x]
            kapsam[ciftler[pi]] = kp
            print(f"[{k}/{len(ciftler)}] {ciftler[pi]} {time.time() - t0:.0f} sn", flush=True)
    sj = hesapla(sonuc, rastgele, sayaclar, ciftler, tfler, setuplar)
    sj["meta"] = {"donem": donem, "kesim": kesim.isoformat(), "ciftler": ciftler, "tfler": tfler, "setuplar": setuplar,
                  "kategori": {k: SV.kategori(k) for k in setuplar},
                  "veri_olan_ciftler": sorted({p for tf in mum for p in mum[tf]}), "fonlama_cift": len(fon),
                  "fonlama_olmayan": [p for p in ciftler if p not in fon], "kapsam": kapsam,
                  "tam_gecmis_esigi": {tf: (bas_ay or V.BAS_AY[tf]) + "-15" for tf in tfler},
                  "sure_sn": time.time() - t0, "tohum": TOHUM, "rastgele_n": RASTGELE_N}
    sj["meta"]["tam_gecmis_esigi"] = {tf: v[:7] + "-15" for tf, v in sj["meta"]["tam_gecmis_esigi"].items()}
    out = Path(cikti)
    out.mkdir(parents=True, exist_ok=True)
    (out / "sonuc.json").write_text(json.dumps(sj, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "ozet.md").write_text(ozet_md(sj), encoding="utf-8")
    print(f"bitti: {time.time() - t0:.0f} sn -> {out}", flush=True)
    return 0
