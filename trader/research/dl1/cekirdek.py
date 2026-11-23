"""DL1 egitim cekirdegi (numpy + pandas; torch YOK): veri -> ornek tablosu, etiket, walk-forward (trader_ml.walkforward purge + embargo),
olcekleyici, puanlama (motorla ayni numpy ileri gecis), yayin kapisi, paket kurulumu. Torch yalniz `egit.py`de (trainer arayuzu).

Tasarim: fikirler/pazartesi-23-11/ust-lig-tasarim.md bolum 2 ve 6 + kullanici karari (43 enstruman, havuz modeli, varlik sinifi kanali).
Kanal hesabi ve ileri gecis motorun `trader_engine.dl1_cikarim` modulunden gelir (egitim = canli; tek kod).

Ornek = (cift, dolu mum i): karar zamani D = mum acilisi + 1 saat. Seansli araclarda bos/eksik mumlar yok sayilir, seri dolu mumlardan kurulur
(bosluk doldurulmaz); 96 dolu mumluk pencerenin takvim doluluk orani >= MIN_DOLU_ORAN. Etiket (M1 ile ayni bariyer, ufuk 24): long/short ayri
"hedef (3 ATR) stoptan (1,5 ATR) once, takvimde 24 saat icinde"; ayni barda ikisi de vurulursa stop; zaman asimi son mumun kapanisi.
R = CANLI CIKIS SIMULASYONU (`simule_cikis`): stop 1,5 ATR (bosluk: stop asilirsa acilista dolum), hedef 3 ATR, 48 mum zaman stopu ve motorun
`exit_modes` ayari (engine.paper.json "exit_modes" -> trader_core.exit_modes.resolve, position_manager ile ayni islevler/parametreler: basa-bas + kismi kar).
Net R = R - masraf: giris * (2 taker + kayma_giris + kayma_cikis|stop) / (1,5 ATR); komisyon ve kayma enstruman bazinda (engine.base.json cost +
engine.paper.json cost_overrides, "open" seans). Fonlama DAHIL DEGIL (Vision fundingRate indirilmiyor; sonraki is). Sinif etiketi y (hedef stoptan once)
ayri tutulur (basa-bas/kismi y'yi degistirmez).
Aday secimi (kapi ve yayin karsilastirmasi): cift basina 48 mumluk ufukta EN FAZLA bir aday (zamanda ilk, o barda en iyi yon); ust uste binen adaylar sayilmaz."""
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

from trader_core import exit_modes as XM  # noqa: E402
from trader_engine import dl1_cikarim as DL  # noqa: E402
from trader_ml.config import HORIZON_BARS, KILIT_ACIK  # noqa: E402
from trader_ml.walkforward import make_folds  # noqa: E402

assert HORIZON_BARS >= DL.UFUK + 24, "purge (HORIZON_BARS) >= etiket ufku + 24 olmali"

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
KAPI_MIN_ADAY = 30                 # korunan siniflarda tum dilimlerde toplam en az bu kadar aday (aksi: kapi gecmez; anlamsiz ortalama)
KAPI_MIN_SINIF_ADAY = 30           # sinif kapsamda kalmak icin: n >= 30 VE ort. R > 0 (aksi sinif kapsamdan cikar: kol o sinifta islem acmaz)
PARITE_TOL = 1e-5
# yayin karari (gunluk egitim; kullanici karari 23.11): yeni paket yalniz kapiyi gecer VE mevcuttan belirgin iyiyse yayinlanir
# Karsilastirma YALNIZ mevcut paketin olusturmasindan SONRAKI gunlerde (iki model icin de kesin orneklem disi). Mevcut paket yok/gecersiz ya da
# son kullanmasina < YENILEME_KALAN_GUN kaldiysa kapiyi gecen yeni paket karsilastirmasiz yayinlanir.
KARS_MIN_GUN = 14                  # mevcut paketin olusturmasindan bu kadar gun gecmeden iyilesme yayini yok
ESIK_IYILESME = 0.05               # yeni - mevcut ort. R >= max(ESIK_IYILESME, fark standart hatasi)
YENILEME_KALAN_GUN = 7
KARS_MIN_ADAY = 30                 # her iki modelin de son dilimde en az bu kadar (secilmis) adayi olmali
VARSAYILAN_MALIYET = (0.0005, 2e-4, 2e-4, 5e-4)    # taker, kayma giris, cikis, stop (oran); engine.base.json cost ile ayni


def sinif_haritasi(config: Path | None = None, universe: Path | None = None) -> dict[str, int]:
    """engine.paper.json pairs (43) -> SINIFLAR indeksi (universe.json: hisse = stocks_ordered, emtia = commodities, kalan kripto)."""
    config = config or ROOT / "config" / "engine.paper.json"
    universe = universe or ROOT / "config" / "universe.json"
    pairs = json.loads(Path(config).read_text())["pairs"]
    u = json.loads(Path(universe).read_text())
    hisse, emtia = set(u["stocks_ordered"]), set(u["commodities"])
    return {p: (1 if p in hisse else 2 if p in emtia else 0) for p in pairs}


def _json(p: Path) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def maliyet_tablosu(base: Path | None = None, paper: Path | None = None) -> dict[str, tuple[float, float, float, float]]:
    """cift -> (taker, kayma_giris, kayma_cikis, kayma_stop) oran. engine.base.json `cost` + engine.paper.json `cost_overrides[cift]["open"]`."""
    base = _json(base or ROOT / "config" / "engine.base.json")
    paper = _json(paper or ROOT / "config" / "engine.paper.json")
    c = base.get("cost", {})
    taker = float(c.get("taker_fee", VARSAYILAN_MALIYET[0]))
    d = {k: float(c.get(k, v * 1e4)) for k, v in (("slip_entry_bps", VARSAYILAN_MALIYET[1]), ("slip_exit_bps", VARSAYILAN_MALIYET[2]),
                                                  ("slip_stop_bps", VARSAYILAN_MALIYET[3]))}
    out = {}
    for pair in paper["pairs"]:
        o = ((paper.get("cost_overrides") or {}).get(pair) or {}).get("open") or {}
        v = {k: float(o.get(k, d[k])) for k in d}
        out[pair] = (taker, v["slip_entry_bps"] / 1e4, v["slip_exit_bps"] / 1e4, v["slip_stop_bps"] / 1e4)
    return out


def cikis_kipleri(paper: Path | None = None):
    """Motorun DL1 icin cozdugu cikis kipleri (position_manager ile ayni: exit_modes.resolve(config, "DL1", "1h")); config'te yoksa None."""
    cfg = XM.build_config(_json(paper or ROOT / "config" / "engine.paper.json").get("exit_modes"))
    return XM.resolve(cfg, DL.ARM_ID.split("@")[0], "1h")


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


def simule_cikis(ts, o, h, l, c, atr, modes, mal=VARSAYILAN_MALIYET) -> np.ndarray:
    """(n, 2) masraf SONRASI R [long, short]: canli cikisin bar bar simulasyonu. Giris = karar barinin kapanisi; R birimi = 1,5 ATR.
    Her kapanmis bar j (<= UFUK, takvimde <= 48 saat): once stop (ayni barda hem stop hem hedef: stop; bosluk: stop asilirsa ACILISTA dolum),
    sonra hedef (tam 3 ATR = +2 R); bar kapandiktan sonra en iyi uc guncellenir: basa-bas (stop girise + offset, sonraki bardan gecerli) ve
    kismi kar (bar kapanisinda `frac`, bir kez). Ufuk sonunda kalan, son barin kapanisinda zaman stopuyla cikar. `modes`: ExitModes | None."""
    taker, s_in, s_out, s_stop = mal
    n = len(c)
    ufuk_ns = DL.UFUK * H_NS
    ok = np.isfinite(atr) & (atr > 0)
    sa = np.where(ok, atr, 1.0)
    risk = DL.STOP_ATR * sa
    rr = DL.HEDEF_ATR / DL.STOP_ATR
    out = np.zeros((n, 2))
    for k, s in enumerate((1.0, -1.0)):
        stop = c - s * risk
        tgt = c + s * DL.HEDEF_ATR * sa
        best = c.copy()
        done = np.zeros(n, dtype=bool)
        pdone = np.zeros(n, dtype=bool)
        rtot = np.zeros(n)
        rem = np.ones(n)
        kind = np.zeros(n, dtype=np.int8)           # 0 zaman, 1 stop, 2 hedef
        son = c.copy()
        for j in range(1, DL.UFUK + 1):
            m = n - j
            if m <= 0:
                break
            ic = (ts[j:] - ts[:m]) <= ufuk_ns
            act = ic & ~done[:m]
            oj, hj, lj, cj = o[j:], h[j:], l[j:], c[j:]
            st = stop[:m]
            if s > 0:
                hs, ht, px = lj <= st, hj >= tgt[:m], np.minimum(st, oj)
            else:
                hs, ht, px = hj >= st, lj <= tgt[:m], np.maximum(st, oj)
            es = act & hs
            et = act & ht & ~hs
            rtot[:m] += np.where(es, rem[:m] * s * (px - c[:m]) / risk[:m], 0.0) + np.where(et, rem[:m] * rr, 0.0)
            kind[:m][es] = 1
            kind[:m][et] = 2
            done[:m] |= es | et
            live = ic & ~done[:m]
            best[:m] = np.where(live, np.maximum(best[:m], hj) if s > 0 else np.minimum(best[:m], lj), best[:m])
            if modes is not None and modes.breakeven:
                hit = best[:m] >= c[:m] + modes.be_trigger_r * risk[:m] - XM.EPS if s > 0 else best[:m] <= c[:m] - modes.be_trigger_r * risk[:m] + XM.EPS
                lvl = c[:m] * (1.0 + s * modes.be_offset_bps / 1e4)
                tight = np.maximum(st, lvl) if s > 0 else np.minimum(st, lvl)
                stop[:m] = np.where(live & hit, tight, st)
            if modes is not None and modes.partial:
                hit = best[:m] >= c[:m] + modes.pt_trigger_r * risk[:m] - XM.EPS if s > 0 else best[:m] <= c[:m] - modes.pt_trigger_r * risk[:m] + XM.EPS
                due = live & hit & ~pdone[:m]
                rtot[:m] += np.where(due, modes.pt_frac * s * (cj - c[:m]) / risk[:m], 0.0)
                rem[:m] = np.where(due, 1.0 - modes.pt_frac, rem[:m])
                pdone[:m] |= due
            son[:m] = np.where(live, cj, son[:m])
        zaman = ~done
        rtot[zaman] += rem[zaman] * s * (son[zaman] - c[zaman]) / risk[zaman]
        cikis_kayma = np.where(kind == 1, s_stop, s_out)
        out[:, k] = rtot - c * (2.0 * taker + s_in + cikis_kayma) / risk
    return out


def cift_ornekleri(df: pd.DataFrame, sinif: int, mal=VARSAYILAN_MALIYET, modes=None):
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
    rnet = simule_cikis(ts, o, h, l, c, atr, modes, mal)
    tab = dict(i=idx, ts=ts[idx] + H_NS, y=y[idx], r=rnet[idx].astype(np.float32), vol=vol[idx].astype(np.float32))
    return X.astype(np.float32), tab


def veri_kur(seriler: dict[str, pd.DataFrame], siniflar: dict[str, int], maliyet: dict | None = None, modes=None) -> Veri:
    Xs, gs, tss, ys, rs, vs, cs_, ss = [], [], [], [], [], [], [], []
    ciftler, off = [], 0
    for pair in sorted(seriler):
        got = cift_ornekleri(seriler[pair], siniflar[pair], (maliyet or {}).get(pair, VARSAYILAN_MALIYET), modes)
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


def aday_sec(v: Veri, rows: np.ndarray, p: np.ndarray, esik: float) -> tuple[np.ndarray, np.ndarray]:
    """(satir konumlari, yon indeksi): puan >= esik adaylari; cift basina UFUK (48 mum = 48 saat) icinde en fazla bir aday: zamanda ilk,
    o barda en yuksek puanli yon. Ust uste binen (secilen adayin ufku icindeki) adaylar atilir."""
    yon = p.argmax(axis=1)
    sk = p.max(axis=1)
    aday = np.flatnonzero(sk >= esik)
    if not aday.size:
        return aday, yon[aday]
    ts, ci = v.ts[rows][aday], v.cift[rows][aday]
    aday = aday[np.lexsort((ts, ci))]
    ts, ci = v.ts[rows][aday], v.cift[rows][aday]
    sec, son_c, bitis = [], -1, 0
    for k in range(len(aday)):
        if ci[k] != son_c:
            son_c, bitis = ci[k], -1
        if ts[k] >= bitis:
            sec.append(k)
            bitis = ts[k] + DL.UFUK * H_NS
    aday = aday[np.array(sec, dtype=np.int64)]
    return aday, yon[aday]


def dilim_degerlendir(v: Veri, fold: dict, agirlik, ort, std, tohum: int = TOHUM) -> dict:
    """Bir dilim: esik = egitim puanlarinin %98'ligi; test adaylari (puan >= esik, cift basina ufukta bir, en iyi yon) masraf sonrasi R."""
    xs = olcekli_x(v, ort, std)
    tr = alt_kume(fold["train_rows"], ESIK_ORNEK, tohum + fold["fold"])
    esik = float(np.percentile(puanlar(v, tr, agirlik, ort, std, xs).ravel(), ESIK_YUZDELIK))
    te = fold["test_rows"]
    p = puanlar(v, te, agirlik, ort, std, xs)
    pos, yon = aday_sec(v, te, p, esik)
    r = v.r[te][pos, yon]
    sn = v.sinif[te][pos]
    return {"fold": fold["fold"], "test_basi": str(fold["test_start"]), "test_sonu": str(fold["test_end"]), "esik": esik,
            "n_test": int(len(te)), **_ozet(r), "sinif": {DL.SINIFLAR[k]: _ozet(r[sn == k]) for k in range(len(DL.SINIFLAR))},
            "_r": r, "_sn": sn}


def kapi(dilimler: list[dict]) -> dict:
    """Yayin kapisi. 1) Sinif eleme: tum dilimlerde sinifin secilmis aday sayisi >= KAPI_MIN_SINIF_ADAY VE ort. R > 0 degilse sinif KAPSAMDAN cikar
    (n < 30 ya da ort. R <= 0; kol o sinifta islem acmaz). 2) Kalan siniflar uzerinden toplam: ort. R > 0 VE dilimlerin >= %60'i pozitif
    (kalan siniflarda adaysiz dilim pozitif sayilmaz) VE >= KAPI_MIN_ADAY aday. Kalan sinif yoksa kapi gecmez."""
    r = np.concatenate([d["_r"] for d in dilimler]) if dilimler else np.zeros(0)
    sn = np.concatenate([d["_sn"] for d in dilimler]) if dilimler else np.zeros(0, dtype=int)
    siniflar, korunan, dusen = {}, [], {}
    for k, ad in enumerate(DL.SINIFLAR):
        m = sn == k
        n_k = int(m.sum())
        ort_k = float(r[m].mean()) if n_k else None
        dk = [d["sinif"][ad] for d in dilimler]
        siniflar[ad] = {"n": n_k, "ort_r": ort_k, "poz_dilim": int(sum(1 for x in dk if x["n"] > 0 and x["ort_r"] > 0)),
                        "aday_dilim": int(sum(1 for x in dk if x["n"] > 0))}
        if n_k >= KAPI_MIN_SINIF_ADAY and ort_k is not None and ort_k > 0:
            korunan.append(k)
        else:
            dusen[ad] = "aday_az" if n_k < KAPI_MIN_SINIF_ADAY else "ort_r_pozitif_degil"
    keep = np.isin(sn, korunan)
    rk = r[keep]
    poz = 0
    for d in dilimler:
        mk = np.isin(d["_sn"], korunan)
        if mk.any() and float(d["_r"][mk].mean()) > 0:
            poz += 1
    oran = poz / len(dilimler) if dilimler else 0.0
    ort = float(rk.mean()) if len(rk) else None
    return {"gecti": bool(korunan and ort is not None and ort > 0 and oran >= KAPI_MIN_POZ_DILIM and len(rk) >= KAPI_MIN_ADAY),
            "toplam_ort_r": ort, "toplam_aday": int(len(rk)), "dilim_sayisi": len(dilimler), "pozitif_dilim": int(poz),
            "pozitif_oran": oran, "siniflar": siniflar, "korunan_idx": korunan, "korunan": [DL.SINIFLAR[k] for k in korunan], "dusen": dusen,
            "tum_siniflar_toplam": {"n": int(len(r)), "ort_r": float(r.mean()) if len(r) else None},
            "kosullar": {"ort_r_pozitif": bool(ort is not None and ort > 0), "pozitif_oran_min": KAPI_MIN_POZ_DILIM,
                         "min_aday": KAPI_MIN_ADAY, "min_sinif_aday": KAPI_MIN_SINIF_ADAY}}


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
         "kapsam": {"siniflar": dict(sorted((p_, i) for p_, i in siniflar.items() if i in kapi_sonuc.get("korunan_idx", range(len(DL.SINIFLAR))))),
                    "sinif_adlari": list(DL.SINIFLAR)},       # yalniz kapiyi gecen siniflar: kol digerlerinde aday uretmez
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
def son_dilim(v: Veri, olusturma: pd.Timestamp) -> tuple[np.ndarray, np.ndarray]:
    """(egitim satirlari, degerlendirme satirlari): degerlendirme = karar zamani >= mevcut paketin olusturmasi (iki model icin kesin orneklem disi:
    mevcut paket olusturmadan sonraki veriyi gormedi; yeni model dilimden once biten etiketlerle egitilir, 24 saat embargo)."""
    bas = pd.Timestamp(olusturma).tz_convert("UTC").value
    return np.flatnonzero(v.bitis < bas - 24 * H_NS), np.flatnonzero(v.ts >= bas)


def aday_r(v: Veri, rows: np.ndarray, agirlik, ort, std, esik: float, ciftler: set | None = None) -> dict:
    """rows uzerinde secilmis adaylarin (cift basina ufukta bir, en iyi yon) masraf sonrasi ort. R'si, std'si. `ciftler`: yalniz bu ciftler."""
    if ciftler is not None:
        iz = {i for i, p_ in enumerate(v.ciftler) if p_ in ciftler}
        rows = rows[np.isin(v.cift[rows], list(iz))]
    p = puanlar(v, rows, agirlik, ort, std)
    pos, yon = aday_sec(v, rows, p, esik)
    r = v.r[rows][pos, yon]
    return {"n": int(len(r)), "ort_r": float(r.mean()) if len(r) else None, "std": float(r.std(ddof=1)) if len(r) > 1 else None, "esik": float(esik)}


def _se(x: dict) -> float:
    return float(x["std"]) / np.sqrt(x["n"]) if x.get("std") is not None and x["n"] > 0 else 0.0


def yayin_karari(kapi_gecti: bool, mevcut: str, kalan_gun: float | None, gecen_gun: float | None, r_mevcut: dict | None, r_yeni: dict | None) -> dict:
    """Saf karar. mevcut: "yok" (yok/bozuk/eski/gecersiz) | "gecerli". gecen_gun: mevcut paketin olusturmasindan beri gun. r_*: {"n","ort_r","std"}.
    Sira: kapi gecmediyse yayin yok; mevcut yok -> yayin; kalan < 7 gun -> yayin (iyilesme aranmaz); gecen < 14 gun -> yayin yok (erken);
    her iki modelde n >= 30 degilse yok; yeni - mevcut >= max(0,05, fark standart hatasi) ise yayin."""
    d = {"yayinla": False, "neden": "", "esik_iyilesme": ESIK_IYILESME, "kars_min_gun": KARS_MIN_GUN, "yenileme_kalan_gun": YENILEME_KALAN_GUN,
         "mevcut": r_mevcut, "yeni": r_yeni, "kalan_gun": kalan_gun, "gecen_gun": gecen_gun}
    if not kapi_gecti:
        d["neden"] = "kapi_gecmedi"
    elif mevcut != "gecerli":
        d.update(yayinla=True, neden="mevcut_yok")
    elif kalan_gun is not None and kalan_gun < YENILEME_KALAN_GUN:
        d.update(yayinla=True, neden="mevcut_suresi_yakin")
    elif gecen_gun is None or gecen_gun < KARS_MIN_GUN:
        d["neden"] = "karsilastirma_erken"
    elif any(x is None or x["n"] < KARS_MIN_ADAY or x["ort_r"] is None for x in (r_mevcut, r_yeni)):
        d["neden"] = "yetersiz_aday"
    else:
        fark = r_yeni["ort_r"] - r_mevcut["ort_r"]
        gerek = max(ESIK_IYILESME, float(np.hypot(_se(r_yeni), _se(r_mevcut))))
        d.update(fark=fark, gerekli_fark=gerek)
        if fark >= gerek - 1e-12:
            d.update(yayinla=True, neden="iyilesme")
        else:
            d["neden"] = "iyilesme_yok"
    return d


def mevcut_durum(yol: Path, simdi) -> tuple[str, "DL.Paket | None", float | None]:
    """Depodaki paket: ("gecerli", paket, kalan_gun) ya da ("yok", None, None) (yok/bozuk/hash/kapi/eski/erken hepsi 'yok' sayilir)."""
    p, _neden = DL.paket_yukle(yol, simdi)
    if p is None:
        return "yok", None, None
    return "gecerli", p, (p.son_kullanma - simdi).total_seconds() / 86400.0


