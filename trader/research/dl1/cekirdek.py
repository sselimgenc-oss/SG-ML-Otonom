"""DL1 egitim cekirdegi (numpy + pandas; torch YOK): veri -> ornek tablosu, etiket, walk-forward (trader_ml.walkforward purge + embargo),
olcekleyici, puanlama (motorla ayni numpy ileri gecis), yayin kapisi, paket kurulumu. Torch yalniz `egit.py`de (trainer arayuzu).

Tasarim: fikirler/pazartesi-23-11/ust-lig-tasarim.md bolum 2 ve 6 + kullanici karari (43 enstruman, havuz modeli, varlik sinifi kanali).
Kanal hesabi ve ileri gecis motorun `trader_engine.dl1_cikarim` modulunden gelir (egitim = canli; tek kod).

Ornek = (cift, dolu mum i): karar zamani D = mum acilisi + 1 saat. Seansli araclarda bos/eksik mumlar yok sayilir, seri dolu mumlardan kurulur
(bosluk doldurulmaz); 96 dolu mumluk pencerenin takvim doluluk orani >= MIN_DOLU_ORAN. Etiket (M1 ile ayni bariyer, ufuk 24): long/short ayri
"hedef (3 ATR) stoptan (1,5 ATR) once, takvimde 24 saat icinde"; ayni barda ikisi de vurulursa stop; zaman asimi son mumun kapanisi.
Net R = brut R - masraf; masraf = 2 * (FEE + SLIPPAGE) * giris / (1,5 ATR) (trader_ml.config sabitleri; tur basina)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
import sys  # noqa: E402

if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trader_engine import dl1_cikarim as DL  # noqa: E402
from trader_ml.config import FEE_RATE, KILIT_ACIK, SLIPPAGE_RATE  # noqa: E402
from trader_ml.walkforward import make_folds  # noqa: E402

TOHUM = 20261123
H_NS = 3_600_000_000_000
BAR = pd.Timedelta(hours=1)
# yurume (walk-forward): kayan dilimler, genisleyen egitim
TRAIN_BARS = 365 * 24
TEST_BARS = 120 * 24
STEP_BARS = 120 * 24
MIN_TEST_BARS = 30 * 24
EGIT_TAVAN_FOLD = 120_000          # dilim basina egitim ornegi ust siniri (tohumlu rastgele alt kume)
EGIT_TAVAN_SON = 300_000           # nihai model
ESIK_YUZDELIK = 98.0               # esik = egitim puanlarinin %98'ligi (long+short birlikte)
ESIK_ORNEK = 100_000               # esik/olcek icin puanlanan egitim ornegi ust siniri
KAPI_MIN_POZ_DILIM = 0.60
KAPI_MIN_ADAY = 30                 # tum dilimlerde toplam en az bu kadar aday (aksi: kapi gecmez; anlamsiz ortalama)
PARITE_TOL = 1e-5
# yayin karari (gunluk egitim; kullanici karari 23.11): yeni paket yalniz kapiyi gecer VE mevcuttan belirgin iyiyse yayinlanir
SON_DILIM_GUN = 14                 # ayni son degerlendirme dilimi (kesimden geriye, takvim gunu); iki model ayni veride
ESIK_IYILESME = 0.05               # yeni - mevcut ort. R (en ust %2 adaylar, masraf sonrasi) en az bu kadar yuksek olmali
YENILEME_KALAN_GUN = 7             # mevcut paketin son kullanmasina bundan az kaldiysa: kapiyi gecen yeni paket iyilesme aranmadan yayinlanir
KARS_MIN_ADAY = 20                 # yeni modelin son dilimde en az bu kadar adayi olmali (aksi: karsilastirma anlamsiz -> yayin yok)
MASRAF_TUR = 2.0 * (FEE_RATE + SLIPPAGE_RATE)   # gidis-donus (fraksiyon)


def sinif_haritasi(config: Path | None = None, universe: Path | None = None) -> dict[str, int]:
    """engine.paper.json pairs (43) -> SINIFLAR indeksi (universe.json: hisse = stocks_ordered, emtia = commodities, kalan kripto)."""
    config = config or ROOT / "config" / "engine.paper.json"
    universe = universe or ROOT / "config" / "universe.json"
    pairs = json.loads(Path(config).read_text())["pairs"]
    u = json.loads(Path(universe).read_text())
    hisse, emtia = set(u["stocks_ordered"]), set(u["commodities"])
    return {p: (1 if p in hisse else 2 if p in emtia else 0) for p in pairs}


# ------------------------------------------------------------------------------------------- veri
@dataclass
class Veri:
    X: np.ndarray            # (N, 11) float32 kanal satirlari (cift basina dolu mumlar, birlestirilmis)
    g: np.ndarray            # (S,) ornegin X satiri (pencere X[g-95 .. g])
    ts: np.ndarray           # (S,) karar zamani D (ns, UTC)
    bitis: np.ndarray        # (S,) etiket bitisi (ns): D + 24 saat
    y: np.ndarray            # (S, 2) uint8: [long, short] hedef once
    r: np.ndarray            # (S, 2) float32: masraf SONRASI R
    vol: np.ndarray          # (S,) float32: sonraki 4 mumun ort. (h-l)/ATR (ikincil bas)
    cift: np.ndarray         # (S,) int16 cift indeksi
    sinif: np.ndarray        # (S,) int8 varlik sinifi
    ciftler: list[str]
    siniflar: dict[str, int]


def etiketle(ts, o, h, l, c, atr):
    """Dolu mum serisi icin (gecerli, y[n,2], rbrut[n,2], vol[n]); gecerli = ufuk tamamen gozlendi ve atr > 0."""
    n = len(c)
    ufuk_ns = DL.UFUK * H_NS
    ok = np.isfinite(atr) & (atr > 0) & (ts + ufuk_ns <= ts[-1] if n else np.zeros(0, bool))
    y = np.zeros((n, 2), dtype=np.uint8)
    rb = np.zeros((n, 2), dtype=np.float64)
    rr = DL.HEDEF_ATR / DL.STOP_ATR
    sa = np.where(ok, atr, 1.0)
    for k, s in enumerate((1.0, -1.0)):
        stop = c - s * DL.STOP_ATR * sa
        tgt = c + s * DL.HEDEF_ATR * sa
        cozuldu = np.zeros(n, dtype=bool)
        son = c.copy()
        rk = np.zeros(n)
        yk = np.zeros(n, dtype=np.uint8)
        for j in range(1, DL.UFUK + 1):
            m = n - j
            if m <= 0:
                break
            ic = (ts[j:] - ts[:m]) <= ufuk_ns            # bar i+j ufuk icinde mi
            act = ic & ~cozuldu[:m]
            hj, lj, cj = h[j:], l[j:], c[j:]
            hit_stop = (lj <= stop[:m]) if s > 0 else (hj >= stop[:m])
            hit_tgt = (hj >= tgt[:m]) if s > 0 else (lj <= tgt[:m])
            st = act & hit_stop
            tg = act & hit_tgt & ~hit_stop
            rk[:m][st] = -1.0
            rk[:m][tg] = rr
            yk[:m][tg] = 1
            cozuldu[:m] |= st | tg
            gun = ic & ~cozuldu[:m]
            son[:m][gun] = cj[gun]
        zaman = ~cozuldu
        rk[zaman] = s * (son[zaman] - c[zaman]) / (DL.STOP_ATR * sa[zaman])
        rb[:, k] = rk
        y[:, k] = yk
    vol = np.full(n, np.nan)
    if n > 4:
        rng = (h - l) / sa
        v4 = np.lib.stride_tricks.sliding_window_view(rng[1:], 4).mean(axis=1)      # i icin rng[i+1..i+4]
        vol[:len(v4)] = np.minimum(v4, 10.0)
    ok &= np.isfinite(vol)
    return ok, y, rb, vol


def cift_ornekleri(df: pd.DataFrame, sinif: int):
    """Bir cift DataFrame'i (date, open..volume; tz-aware UTC) -> (kanal X (m,11), ornek tablosu dict) ya da None."""
    d = df.sort_values("date").drop_duplicates("date")
    ts = d["date"].dt.tz_convert("UTC").dt.as_unit("ns").astype("int64").to_numpy()
    ts, o, h, l, c, v = DL.kompakt(ts, *(d[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "volume")))
    if len(c) < DL.MIN_BAR + DL.UFUK + 5:
        return None
    X = DL.kanallar(o, h, l, c, v, sinif)
    atr = DL.atr_serisi(h, l, c)
    fin = np.isfinite(X).all(axis=1)
    cs = np.r_[0, np.cumsum(fin)]
    n = len(c)
    pen_ok = np.zeros(n, dtype=bool)
    pen_ok[DL.PENCERE - 1:] = (cs[DL.PENCERE:] - cs[:n - DL.PENCERE + 1]) == DL.PENCERE
    dolu_ok = DL.pencere_doluluk_ok(ts)
    lab_ok, y, rb, vol = etiketle(ts, o, h, l, c, atr)
    ok = pen_ok & dolu_ok & lab_ok
    idx = np.flatnonzero(ok)
    if not idx.size:
        return None
    masraf = MASRAF_TUR * c[idx] / (DL.STOP_ATR * atr[idx])
    tab = dict(i=idx, ts=ts[idx] + H_NS, y=y[idx], r=(rb[idx] - masraf[:, None]).astype(np.float32), vol=vol[idx].astype(np.float32))
    return X.astype(np.float32), tab


def veri_kur(seriler: dict[str, pd.DataFrame], siniflar: dict[str, int]) -> Veri:
    Xs, gs, tss, ys, rs, vs, cs_, ss = [], [], [], [], [], [], [], []
    ciftler, off = [], 0
    for pair in sorted(seriler):
        got = cift_ornekleri(seriler[pair], siniflar[pair])
        if got is None:
            continue
        X, t = got
        ci = len(ciftler)
        ciftler.append(pair)
        Xs.append(X)
        gs.append(t["i"] + off)
        tss.append(t["ts"]); ys.append(t["y"]); rs.append(t["r"]); vs.append(t["vol"])
        cs_.append(np.full(len(t["i"]), ci, dtype=np.int16)); ss.append(np.full(len(t["i"]), siniflar[pair], dtype=np.int8))
        off += len(X)
    if not Xs:
        raise ValueError("hic ornek yok")
    ts = np.concatenate(tss)
    sira = np.argsort(ts, kind="stable")                  # zamana gore sirali tablo (make_folds konumsal indeks)
    f = lambda a: np.concatenate(a)[sira]  # noqa: E731
    return Veri(X=np.concatenate(Xs), g=f(gs), ts=ts[sira], bitis=ts[sira] + DL.UFUK * H_NS, y=f(ys), r=f(rs), vol=f(vs),
                cift=f(cs_), sinif=f(ss), ciftler=ciftler, siniflar={p: siniflar[p] for p in ciftler})


# ------------------------------------------------------------------------------------------- olcek / pencere / puan
def olcekleyici(v: Veri, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Yalniz `rows` (egitim) orneklerinin son-mum kanal degerlerinden; sinif kanallari 0/1 sabit."""
    x = v.X[v.g[rows]][:, :DL.N_FIYAT].astype(np.float64)
    ort = np.zeros(DL.N_KANAL)
    std = np.ones(DL.N_KANAL)
    ort[:DL.N_FIYAT] = x.mean(axis=0)
    std[:DL.N_FIYAT] = np.maximum(x.std(axis=0), 1e-8)
    return ort, std


def olcekli_x(v: Veri, ort, std) -> np.ndarray:
    z = (v.X.astype(np.float64) - ort) / std
    z[:, :DL.N_FIYAT] = np.clip(z[:, :DL.N_FIYAT], -DL.KIRP, DL.KIRP)
    return z.astype(np.float32)


def pencereler(xs: np.ndarray, g: np.ndarray) -> np.ndarray:
    return xs[g[:, None] + np.arange(-(DL.PENCERE - 1), 1)]


def puanlar(v: Veri, rows: np.ndarray, agirlik, ort, std, xs: np.ndarray | None = None, parti: int = 4096) -> np.ndarray:
    """(len(rows), 2) [p_long, p_short]; motorla ayni numpy ileri gecis."""
    xs = olcekli_x(v, ort, std) if xs is None else xs
    out = np.empty((len(rows), 2))
    for a in range(0, len(rows), parti):
        r = rows[a:a + parti]
        out[a:a + len(r)] = DL.sigmoid(DL.ileri(agirlik, pencereler(xs, v.g[r]))[:, :2])
    return out


def alt_kume(rows: np.ndarray, tavan: int, tohum: int) -> np.ndarray:
    if len(rows) <= tavan:
        return rows
    return np.sort(np.random.default_rng(tohum).choice(rows, tavan, replace=False))


# ------------------------------------------------------------------------------------------- walk-forward + kapi
def tablo(v: Veri) -> pd.DataFrame:
    return pd.DataFrame({"ts": pd.to_datetime(v.ts, utc=True), "label_end_ts": pd.to_datetime(v.bitis, utc=True)})


def foldlar(v: Veri, kesim: pd.Timestamp) -> list[dict]:
    tb = tablo(v)
    start = tb["ts"].min().floor("D")
    return make_folds(tb, train_bars=TRAIN_BARS, test_bars=TEST_BARS, step_bars=STEP_BARS, min_test_bars=MIN_TEST_BARS,
                      start=start, end=kesim)


def _ozet(r: np.ndarray) -> dict:
    return {"n": int(len(r)), "ort_r": float(r.mean()) if len(r) else None}


def dilim_degerlendir(v: Veri, fold: dict, agirlik, ort, std, tohum: int = TOHUM) -> dict:
    """Bir dilim: esik = egitim puanlarinin %98'ligi; test adaylari (puan >= esik, her iki yon) masraf sonrasi R."""
    xs = olcekli_x(v, ort, std)
    tr = alt_kume(fold["train_rows"], ESIK_ORNEK, tohum + fold["fold"])
    esik = float(np.percentile(puanlar(v, tr, agirlik, ort, std, xs).ravel(), ESIK_YUZDELIK))
    te = fold["test_rows"]
    p = puanlar(v, te, agirlik, ort, std, xs)
    m = p >= esik
    r = v.r[te][m]
    sn = np.broadcast_to(v.sinif[te][:, None], m.shape)[m]
    return {"fold": fold["fold"], "test_basi": str(fold["test_start"]), "test_sonu": str(fold["test_end"]), "esik": esik,
            "n_test": int(len(te)), **_ozet(r), "sinif": {DL.SINIFLAR[k]: _ozet(r[sn == k]) for k in range(len(DL.SINIFLAR))},
            "_r": r, "_sn": sn}


def kapi(dilimler: list[dict]) -> dict:
    """Yayin kapisi (toplam uzerinden): toplam ort. R > 0 VE dilimlerin >= %60'i pozitif (adaysiz dilim pozitif sayilmaz) VE >= KAPI_MIN_ADAY aday.
    Sinif bazli satirlar yalniz raporlanir (kapiyi belirlemez)."""
    r = np.concatenate([d["_r"] for d in dilimler]) if dilimler else np.zeros(0)
    sn = np.concatenate([d["_sn"] for d in dilimler]) if dilimler else np.zeros(0, dtype=int)
    poz = sum(1 for d in dilimler if d["n"] > 0 and d["ort_r"] > 0)
    oran = poz / len(dilimler) if dilimler else 0.0
    ort = float(r.mean()) if len(r) else None
    siniflar = {}
    for k, ad in enumerate(DL.SINIFLAR):
        dk = [d["sinif"][ad] for d in dilimler]
        siniflar[ad] = {"n": int(sum(x["n"] for x in dk)), "ort_r": float(r[sn == k].mean()) if (sn == k).any() else None,
                        "poz_dilim": int(sum(1 for x in dk if x["n"] > 0 and x["ort_r"] > 0)),
                        "aday_dilim": int(sum(1 for x in dk if x["n"] > 0))}
    return {"gecti": bool(ort is not None and ort > 0 and oran >= KAPI_MIN_POZ_DILIM and len(r) >= KAPI_MIN_ADAY),
            "toplam_ort_r": ort, "toplam_aday": int(len(r)), "dilim_sayisi": len(dilimler), "pozitif_dilim": int(poz),
            "pozitif_oran": oran, "siniflar": siniflar,
            "kosullar": {"ort_r_pozitif": bool(ort is not None and ort > 0), "pozitif_oran_min": KAPI_MIN_POZ_DILIM,
                         "min_aday": KAPI_MIN_ADAY}}


def yuru(v: Veri, trainer, kesim: pd.Timestamp, tohum: int = TOHUM, log=print) -> list[dict]:
    """trainer(v, rows, ort, std, tohum) -> agirlik (numpy sozlugu). Dilim basina: egit (yalniz egitim dilimi + yalniz oradan olcek), test."""
    out = []
    for f in foldlar(v, kesim):
        tr = f["train_rows"]
        if len(tr) < 1000 or len(f["test_rows"]) == 0:
            continue
        sub = alt_kume(tr, EGIT_TAVAN_FOLD, tohum + f["fold"])
        ort, std = olcekleyici(v, sub)
        ag = trainer(v, sub, ort, std, tohum + f["fold"])
        d = dilim_degerlendir(v, {**f, "train_rows": sub}, ag, ort, std, tohum)
        log(f"dilim {d['fold']}: n_test={d['n_test']} aday={d['n']} ort_R={d['ort_r']}")
        out.append(d)
    return out


def temiz(dilimler: list[dict]) -> list[dict]:
    return [{k: x for k, x in d.items() if not k.startswith("_")} for d in dilimler]


# ------------------------------------------------------------------------------------------- paket
def paket_kur(agirlik, ort, std, esik: float, siniflar: dict[str, int], kapi_sonuc: dict, olusturma, metrikler: dict) -> dict:
    from datetime import timedelta
    p = {"schema": DL.SEMA, "arm_id": DL.ARM_ID, "pencere": DL.PENCERE, "kanallar": list(DL.KANALLAR), "ufuk": DL.UFUK,
         "etiket": {"stop_atr": DL.STOP_ATR, "hedef_atr": DL.HEDEF_ATR},
         "olusturma": olusturma.isoformat(), "son_kullanma": (olusturma + timedelta(days=DL.SON_KULLANMA_GUN)).isoformat(),
         "esik": float(esik), "olcekleyici": {"ort": [float(x) for x in ort], "std": [float(x) for x in std]},
         "kapsam": {"siniflar": dict(sorted(siniflar.items())), "sinif_adlari": list(DL.SINIFLAR)},
         "kapi": {"gecti": bool(kapi_sonuc["gecti"]), "toplam_ort_r": kapi_sonuc["toplam_ort_r"],
                  "pozitif_oran": kapi_sonuc["pozitif_oran"]},
         "agirliklar": DL.agirlik_paketle(agirlik), "metrikler": metrikler}
    p["sha256"] = DL.paket_ozeti(p)
    return p


def paket_yaz(paket: dict, yol: Path) -> bool:
    """Atomik yazar; icerik (sha dahil) ayniysa dokunmaz. True = yazildi."""
    yol = Path(yol)
    yeni = DL.kanonik(paket) + "\n"
    if yol.exists() and yol.read_text(encoding="utf-8") == yeni:
        return False
    yol.parent.mkdir(parents=True, exist_ok=True)
    tmp = yol.with_suffix(".tmp")
    tmp.write_text(yeni, encoding="utf-8")
    tmp.replace(yol)
    return True


def ilk_ag(tohum: int) -> dict[str, np.ndarray]:
    """He-baslatmali rastgele agirliklar (numpy; test/duman icin)."""
    rg = np.random.default_rng(tohum)
    out = {}
    for ad, sek in DL.agirlik_sekilleri().items():
        out[ad] = rg.normal(0, np.sqrt(2.0 / max(int(np.prod(sek[1:])), 1)), sek) if ad.endswith(".w") else np.zeros(sek)
    return out


# ------------------------------------------------------------------------------------------- yayin karari (gunluk)
def son_dilim(v: Veri, kesim: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    """(egitim satirlari, degerlendirme satirlari): degerlendirme = karar zamani >= kesim - SON_DILIM_GUN gun; egitim = etiketi dilim basindan
    EMBARGO_BARS (24) saat once bitmis ornekler (ileriye bakma yok; purge etiket bitisiyle)."""
    bas = (kesim - pd.Timedelta(days=SON_DILIM_GUN)).value
    ev = np.flatnonzero(v.ts >= bas)
    tr = np.flatnonzero(v.bitis < bas - 24 * H_NS)
    return tr, ev


def aday_r(v: Veri, rows: np.ndarray, agirlik, ort, std, esik: float) -> dict:
    """rows uzerinde puan >= esik (her iki yon) adaylarinin masraf sonrasi ort. R'si."""
    p = puanlar(v, rows, agirlik, ort, std)
    r = v.r[rows][p >= esik]
    return {"n": int(len(r)), "ort_r": float(r.mean()) if len(r) else None, "esik": float(esik)}


def yayin_karari(kapi_gecti: bool, mevcut: str, kalan_gun: float | None, r_mevcut: dict | None, r_yeni: dict | None) -> dict:
    """Saf karar. mevcut: "yok" (yok/bozuk/eski/gecersiz) | "gecerli". r_*: {"n", "ort_r"} (son dilim). Doner {"yayinla", "neden", ...}.
    Sira: kapi gecmediyse yayin yok; mevcut yok -> yayin; kalan < 7 gun -> yayin (iyilesme aranmaz); aksi: yeni - mevcut >= ESIK_IYILESME."""
    d = {"yayinla": False, "neden": "", "esik_iyilesme": ESIK_IYILESME, "son_dilim_gun": SON_DILIM_GUN, "yenileme_kalan_gun": YENILEME_KALAN_GUN,
         "mevcut": r_mevcut, "yeni": r_yeni, "kalan_gun": kalan_gun}
    if not kapi_gecti:
        d["neden"] = "kapi_gecmedi"
    elif mevcut != "gecerli":
        d.update(yayinla=True, neden="mevcut_yok")
    elif kalan_gun is not None and kalan_gun < YENILEME_KALAN_GUN:
        d.update(yayinla=True, neden="mevcut_suresi_yakin")
    elif r_yeni is None or r_yeni["n"] < KARS_MIN_ADAY or r_yeni["ort_r"] is None:
        d["neden"] = "yetersiz_aday"
    elif r_mevcut is None or r_mevcut["n"] == 0 or r_mevcut["ort_r"] is None:
        d.update(yayinla=True, neden="mevcut_aday_uretmedi")
    elif r_yeni["ort_r"] - r_mevcut["ort_r"] >= ESIK_IYILESME - 1e-12:
        d.update(yayinla=True, neden="iyilesme")
    else:
        d["neden"] = "iyilesme_yok"
    return d


def mevcut_durum(yol: Path, simdi) -> tuple[str, "DL.Paket | None", float | None]:
    """Depodaki paket: ("gecerli", paket, kalan_gun) ya da ("yok", None, None) (yok/bozuk/hash/kapi/eski hepsi 'yok' sayilir)."""
    p, _neden = DL.paket_yukle(yol, simdi)
    if p is None:
        return "yok", None, None
    return "gecerli", p, (p.son_kullanma - simdi).total_seconds() / 86400.0
