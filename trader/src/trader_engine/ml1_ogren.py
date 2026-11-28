"""ML1 sifirdan ogrenme (yalniz kagit): gercekten acilip kapanan kagit islemlerden VE (27.11 sahip karari, "golge ogrenme") alinmayan adaylardan ogrenir;
alinmayan adayin etiketi AYNI kurallarla simulasyondan gelir (`ml1_sanal.py`; dosya `sanallar-*.jsonl`; defter/islem tablolarina HICBIR ZAMAN girmez).
Tohum paket ve taban model YOKTUR (sahip karari). Egitim satirlarinda `sanal` sutunu; ornek agirligi `sanal_agirlik` (0..1, varsayilan 1).
Bilinen risk (sahip karari #11, 26.11): model yalniz kendi gecirdigi islemleri gorur (secilim yanlilgi); rastgele gecis payi bilerek yok.

Akis (karar adimi sonunda, `_shadow_step` kalibi: durum/broker/emir/kapi uzerinde YAZMA yok, istisna sizmaz):
  1) motor bir islem actiginda (`Engine._enter`) kapi, o adayin ham ozellik vektorunu (x) islem kimligiyle (trade_id + decision_id) birlikte
     `islem_alindi` ile dosyaya ekler (`alinanlar-YYYY-MM.jsonl`). Alinmayan adayin vektoru HICBIR yere yazilmaz.
  2) `adim`: bekleyen alinan islemlerin defterde KAPANIP kapanmadigina bakilir; baglanti kesin: defter islemi trade_id ve decision_id (+ cift/yon)
     ile eslesir (gevsek zaman/kurulum eslesmesi yok). Etiket gercek kapanan islemden: y = 1 eger net r_multiple > 0. Sonuc `sonuclar-*.jsonl`.
  3) kapanan ogrenilmis islem sayisi `ogrenme.min_islem` (ve `min_islem_tf` > 0 ise her zaman diliminde en az o kadar) olana dek paket YOKTUR
     (kapi her adayi gecirir). Ilk esik asildiktan sonra (200'de ilk DENEME; paket yalniz orneklem-disi sinamayi gecerse yayinlanir) yeni kapanan
     islem geldikce (karar adimi basina en cok bir kez) sifir merkezli ridge lojistik yeniden uydurulur (`uydur`: kendi standardizasyonu,
     30 gun yari omur, olay agirligi), `sina` ile en yeni %20'lik dilimde sinanir (log-kayip tabandan iyi + AUC > 0.5; gecemezse paket
     YAZILMAZ, etkin paket aynen kalir, ogrenme surer), denetlenir (`denetle`), atomik yazilir (`.tmp` + son_iyi + os.replace). Kapi dosyanin mtime'i degisince paketi yeniden yukler.
  4) her adim: etkin paket bozulduysa / kapi puanlama hatasi verdiyse / kapi paketi reddettiyse / ilk 40+ puanlanan adayda gecme orani %0 ise
     (her sey reddedilirse yeni islem de ogrenme de durur) onceki OGRENILMIS pakete, o yoksa pakete hic (= ogrenme asamasi, hepsini gecir)
     donulur + 24 saat duraklatma. Hicbir zaman tohum pakete donulmez.
Esik config'ten sabit (`ogrenme.esik`, 0,50). `ogrenme.kuru=true`: her sey calisir, yalniz etkin paket yazilmaz.
Dosyalar: var/learner/ml1_ogren/ (durum.json, alinanlar-*.jsonl, sonuclar-*.jsonl, guncellemeler.jsonl).
Saat: yalniz enjekte edilen `now_fn` (motor saati). Ag/yeni servis/defter semasi degisikligi yok."""
from __future__ import annotations

import copy
import json
import logging
import math
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from trader_ml.ml1 import features as F
from trader_ml.ml1 import model as M

log = logging.getLogger("engine.ml1_ogren")

K_BARS = F.K_BARS
MIN_ISLEM = 200                   # ilk paket DENEMESINDEN once kapanan islem sayisi (config ogrenme.min_islem)
ESIK = 0.50                       # sabit esik (config ogrenme.esik)
YARI_OMUR_GUN = 30.0
PENCERE_GUN = 365
MAKS_SATIR = 50_000
Z_KIRP = 5.0
RIDGE = 50.0                      # sifir merkezli ridge sertligi (agirliklar ortalama 1'e olceklenir; kesisim cezasiz)
GERI_IZLE_MIN = 40
DURAKLAT = timedelta(hours=24)
YAS_KAPAT_GUN = 120               # defterde hic kapanmayan (acilamamis) alinan kayit bu yastan sonra etiketsiz kapatilir
SAKLA_AY = 14
GERCEK_MAKS = 5000                # `Ml1Ogrenici.gercek` bellek siniri (en eskiler atilir)
SINAMA_ORAN = 0.20                # orneklem-disi sinama: en yeni islemlerin orani (zaman sirali, ambargolu)
SINAMA_ARALIK = 100               # basarisiz sinamadan sonra yeni deneme icin gereken ek etiketli satir
SINAMA_GERCEK_MIN = 20            # gercek-satir alt kumesi sinama metrigi icin en az gercek sinama satiri (bilgi amacli)
SINAMA_MIN_N = 40                 # sinama kumesi alt siniri; n // 2'yi asarsa "sinama_yetersiz_veri"


# ----------------------------------------------------------------------------------------------------------- saf matematik
def olay_agirligi(d: pd.DataFrame) -> np.ndarray:
    """Olay agirligi ETIKETLI islemlerden hesaplanir: e_i = 1 / (tampondaki ayni olaydaki sonuc sayisi): `features.events` ile ayni kural (pair|side|tf, bosluk <= 3 mum)."""
    if len(d) == 0:
        return np.zeros(0)
    ev = F.events(d[["decision_ts", "pair", "side", "tf"]].reset_index(drop=True))
    return ev["event_weight"].to_numpy(float)


def uydur(d: pd.DataFrame, X: np.ndarray, simdi: datetime, *, yari_omur_gun: float = YARI_OMUR_GUN, pencere_gun: float = PENCERE_GUN,
          maks_satir: int = MAKS_SATIR, ridge: float = RIDGE, sanal_agirlik: float = 1.0) -> dict | None:
    """Sifir merkezli ridge lojistik (Newton/IRLS), standardizasyon KENDI verisinden. `d`: sutunlar k, decision_ts (tz), pair, side, tf, y;
    `X`: d ile ayni sirada ham ozellikler. Sonuc kanonik sirada (decision_ts, k) hesaplanir => girdi sirasindan bagimsiz.
    Olay agirligi etiketli islemlerden hesaplanir. Pencerede veri yoksa ya da tek sinif varsa None. Doner st (standardizasyon), coef, b, n_etkin, n_sonuc, tarih araligi."""
    if len(d) == 0:
        return None
    simdi_ns = pd.Timestamp(simdi).as_unit("ns").value
    ts = pd.DatetimeIndex(d["decision_ts"]).as_unit("ns").asi8
    yas_gun = (simdi_ns - ts) / 86_400e9
    keep = np.flatnonzero(yas_gun <= pencere_gun)
    if len(keep) == 0:
        return None
    keep = keep[np.lexsort((d["k"].to_numpy()[keep], ts[keep]))]          # kanonik sira
    keep = keep[-int(maks_satir):]
    dd = d.iloc[keep].reset_index(drop=True)
    y = dd["y"].to_numpy(float)
    if len(np.unique(y)) < 2:
        return None
    e = olay_agirligi(dd)
    age = np.maximum(yas_gun[keep], 0.0)
    w = e * np.exp2(-age / float(yari_omur_gun))
    if "sanal" in dd.columns:
        w = w * np.where(dd["sanal"].to_numpy(bool), float(sanal_agirlik), 1.0)
    if not w.sum() > 0:
        return None
    Xk = np.asarray(X, float)[keep]
    st = M.fit_standardizer(Xk)
    Z = np.clip(M.standardize(Xk, st), -Z_KIRP, Z_KIRP)
    coef, b = M.fit_logistic(Z, y, w, float(ridge))
    return {"st": st, "coef": coef, "b": float(b), "n_etkin": float(w.sum()), "n_sonuc": int(len(dd)),
            "bas": dd["decision_ts"].min(), "son": dd["decision_ts"].max()}


def _auc(p: np.ndarray, y: np.ndarray) -> float:
    """Mann-Whitney AUC; esit puanlara ortalama sira. Tek sinifta nan."""
    y = np.asarray(y, float)
    n1 = float((y > 0.5).sum())
    n0 = float(len(y) - n1)
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = pd.Series(np.asarray(p, float)).rank(method="average").to_numpy()
    return float((r[y > 0.5].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0))


def sina(d: pd.DataFrame, X: np.ndarray, simdi: datetime, *, yari_omur_gun: float = YARI_OMUR_GUN, pencere_gun: float = PENCERE_GUN,
         maks_satir: int = MAKS_SATIR, ridge: float = RIDGE, sanal_agirlik: float = 1.0) -> dict:
    """Orneklem-disi sinama (yayin kapisi): satir kumesi/sirasi `uydur` ile AYNI; en yeni `n_h` satir sinama, oncesi egitim (ayni olaydaki egitim
    satirlari ambargo ile atilir). Egitim kumesinden uydurulan model sinamada puanlanir (kapiyla ayni yol, kirpma YOK) ve sabit tabanla
    (egitim taban orani) karsilastirilir. Gecme: iki sinif var, ll_model < ll_taban, auc > 0.5. Firlatmaz."""
    try:
        return _sina(d, X, simdi, yari_omur_gun=yari_omur_gun, pencere_gun=pencere_gun, maks_satir=maks_satir, ridge=ridge, sanal_agirlik=sanal_agirlik)
    except Exception as e:  # noqa: BLE001
        return {"gecti": False, "neden": f"sinama_hatasi:{type(e).__name__}"}


def _sina(d, X, simdi, *, yari_omur_gun, pencere_gun, maks_satir, ridge, sanal_agirlik=1.0) -> dict:
    if len(d) == 0:
        return {"gecti": False, "neden": "sinama_yetersiz_veri"}
    simdi_ns = pd.Timestamp(simdi).as_unit("ns").value
    ts = pd.DatetimeIndex(d["decision_ts"]).as_unit("ns").asi8
    keep = np.flatnonzero((simdi_ns - ts) / 86_400e9 <= pencere_gun)
    keep = keep[np.lexsort((d["k"].to_numpy()[keep], ts[keep]))]
    keep = keep[-int(maks_satir):]
    n = len(keep)
    n_h = max(SINAMA_MIN_N, int(np.ceil(SINAMA_ORAN * n)))
    if n_h > n // 2:
        return {"gecti": False, "neden": "sinama_yetersiz_veri"}
    dd = d.iloc[keep].reset_index(drop=True)
    Xk = np.asarray(X, float)[keep]
    ts_k = ts[keep]
    t_b = ts_k[n - n_h]                                          # sinir: sondan n_h'inci satirin zamani
    h = ts_k >= t_b                                              # ayni damgali satirlar bolunmez
    ev = F.events(dd[["decision_ts", "pair", "side", "tf"]])["event_id"].to_numpy()
    egit = (~h) & ~np.isin(ev, ev[h])                            # ambargo: sinamayla ayni olaydaki egitim satirlari atilir
    sinir_ts = pd.Timestamp(int(t_b), unit="ns", tz="UTC").isoformat()
    out: dict = {"gecti": False, "neden": "", "n_egitim": int(egit.sum()), "n_sinama": int(h.sum()), "sinir_ts": sinir_ts}
    r_e = uydur(dd[egit].reset_index(drop=True), Xk[egit], simdi, yari_omur_gun=yari_omur_gun, pencere_gun=pencere_gun, maks_satir=maks_satir, ridge=ridge,
                sanal_agirlik=sanal_agirlik)
    if r_e is None:
        out["neden"] = "sinama_egitim_uydurulamadi"
        return out
    y_h = dd["y"].to_numpy(float)[h]
    y_e = dd["y"].to_numpy(float)[egit]
    p = M._sigmoid(M.standardize(Xk[h], r_e["st"]) @ r_e["coef"] + r_e["b"])      # kapiyla ayni puanlama yolu: z kirpmasi YOK
    p0 = float(np.clip(y_e.mean(), 1e-6, 1 - 1e-6))
    ll_m = M.log_loss(p, y_h)
    ll_t = M.log_loss(np.full(len(y_h), p0), y_h)
    auc = _auc(p, y_h)
    out.update({"ll_model": round(ll_m, 6), "ll_taban": round(ll_t, 6), "auc": None if not np.isfinite(auc) else round(auc, 6), "taban_oran": round(p0, 6)})
    if "sanal" in dd.columns:                                                  # bilgi amacli: yalniz GERCEK islemlerden olusan alt kumede ayni olcumler
        gh = ~dd["sanal"].to_numpy(bool)[h]
        out["n_sinama_gercek"] = int(gh.sum())
        if gh.sum() >= SINAMA_GERCEK_MIN:
            yg, pg = y_h[gh], p[gh]
            a_g = _auc(pg, yg)
            out["gercek"] = {"n": int(gh.sum()), "ll_model": round(M.log_loss(pg, yg), 6), "ll_taban": round(M.log_loss(np.full(len(yg), p0), yg), 6),
                             "auc": None if not np.isfinite(a_g) else round(a_g, 6)}
    if len(np.unique(y_h)) < 2:
        out["neden"] = "sinama_tek_sinif"
    elif not ll_m < ll_t:
        out["neden"] = "sinama_logloss"
    elif not auc > 0.5:
        out["neden"] = "sinama_auc"
    else:
        out["gecti"], out["neden"] = True, "gecti"
    return out


def yeni_paket(r: Mapping, *, esik: float, surum: int, simdi: datetime, ridge: float = RIDGE, metrics: dict | None = None) -> dict:
    """Uydurma sonucundan imzali paket (`ml1/1` semasi; ozellik adlari kodun `feature_names()`i; esik config'ten)."""
    pkg = M.build_package(M.feature_names(), r["st"], r["coef"], r["b"], float(esik), float(ridge), train_start=r["bas"], train_end=r["son"],
                          n_train=r["n_sonuc"], metrics=metrics, created_at=pd.Timestamp(simdi).to_pydatetime())
    pkg = copy.deepcopy(pkg)
    pkg.pop("sha256", None)
    pkg["online"] = {"surum": int(surum), "n_sonuc": int(r["n_sonuc"]), "n_etkin": round(float(r["n_etkin"]), 4),
                     "guncellendi": pd.Timestamp(simdi).isoformat(), "kaynak": "gercek_kagit_islemleri"}
    pkg = M._clean(pkg)
    pkg["sha256"] = M.package_hash(pkg)
    return pkg


def denetle(yeni: Mapping, esik: float) -> tuple[str | None, dict]:
    """Yazmadan once denetim: sonlu agirlik/standardizasyon, sema + sha, ozellik adlari kodla ayni, esik config'le ayni. Tohumla KARSILASTIRMA yok.
    Doner (red_nedeni | None, olcumler). Hicbir kosulda firlatmaz."""
    info: dict = {}
    try:
        coef = np.asarray(yeni["weights"]["coef"], float)
        b = float(yeni["weights"]["intercept"])
        if not (np.all(np.isfinite(coef)) and np.isfinite(b)):
            return "agirlik_sonlu_degil", info
        for key in ("fill", "mean", "std"):
            if not np.all(np.isfinite(np.asarray(yeni["standardization"][key], float))):
                return f"standardizasyon_sonlu_degil:{key}", info
        why = M.verify_package(dict(yeni))
        if why is not None:
            return f"paket_gecersiz:{why}", info
        if list(yeni["feature_names"]) != M.feature_names():
            return "ozellik_adlari_kodla_uyusmuyor", info
        thr = yeni.get("threshold")
        if isinstance(thr, bool) or not isinstance(thr, (int, float)) or abs(float(thr) - float(esik)) > 1e-12:
            return f"esik_ayarla_uyusmuyor:{thr!r}", info
        return None, info
    except Exception as e:  # noqa: BLE001
        return f"denetim_hatasi:{type(e).__name__}", info


def _atomik_yaz_bayt(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _ay(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m")


def _vek(x) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in x], np.float32)


# ----------------------------------------------------------------------------------------------------------- ogrenici
class Ml1Ogrenici:
    def __init__(self, dizin, paket_yolu, *, now_fn: Callable[[], datetime], ledger=None, kapi=None, min_islem: int = MIN_ISLEM,
                 min_islem_tf: int = 0, esik: float = ESIK, yari_omur_gun: float = YARI_OMUR_GUN, kuru: bool = False,
                 sinama: bool = True, sanal=None, sanal_agirlik: float = 1.0, sinama_aralik: int = SINAMA_ARALIK, agirlik_fn: Callable[[], float] | None = None,
                 kiyas_fn: Callable[[], dict | None] | None = None) -> None:
        self.dir = Path(dizin)
        self.paket_yolu = Path(paket_yolu)
        self.son_iyi_yolu = self.paket_yolu.with_name("ml1_package.son_iyi.json")
        self.now_fn, self.ledger, self.kapi = now_fn, ledger, kapi
        self.min_islem, self.min_islem_tf, self.esik = int(min_islem), int(min_islem_tf), float(esik)
        self.yari_omur, self.kuru = float(yari_omur_gun), bool(kuru)
        self.sinama = bool(sinama)                       # yalniz testler kapatir; motor GECIRMEZ, config'ten okunmaz
        self.son_sinama: dict | None = None
        self.sanal = sanal                               # ml1_sanal.SanalCfg | None (None = golge ogrenme kapali)
        self.sanal_agirlik = float(sanal_agirlik)
        self.agirlik_fn = agirlik_fn                     # olcum (golge_gercek) onerisi: etkin sanal agirlik (yalniz DUSURUR); motor baglar
        self.kiyas_fn = kiyas_fn                         # olcum ozetinin kucuk aynasi (durum.json icin); motor baglar
        self.gercek: dict[int, dict] = {}                # trade_id -> kapanmis+etiketli GERCEK islem (alinan kayit x haric + exit_ts, y, r_net, exit_reason); olcumlerin veri kaynagi
        self.sinama_aralik = int(sinama_aralik)
        self.sonraki_sinama_n: int | None = None         # basarisiz sinamadan sonra: bu kadar etiketli satira ulasilmadan yeni deneme yok
        self.sanal_bekleyen: dict[str, dict] = {}        # sid -> bekleyen sanal aday (x dahil)
        self.sanal_bilinen: set[str] = set()
        self.n_sanal = 0                                 # etiketlenmis sanal satir sayisi (n_kapali'nin icinde)
        self._sanal_son: dict[tuple, tuple] = {}         # (cift, yon, tf) -> (olay zinciri son aday zamani, olayda gercek giris var mi)
        self._sanal_kontrol: dict[str, pd.Timestamp] = {}
        self.sayac: Counter = Counter()
        self.hazir = False
        self.bekleyen: dict[int, dict] = {}              # trade_id -> alinan (henuz kapanmamis) islemin kaydi (x dahil)
        self.kapali: set[int] = set()                    # sonuclanmis ya da etiketsiz kapatilmis trade_id'ler
        self.bilinen: set[int] = set()
        self._sn: list[tuple] = []                       # (k, ts_ns, y, pair, side, tf, x float32, sanal bool); yalniz etiketli
        self.n_kapali = 0                                # kapanan ogrenilmis (etiketli) islem sayisi (kalici; son 14 ayin dosyalarindan)
        self.n_tf: Counter = Counter()
        self.n_oz: Counter = Counter()                   # kapanan ogrenilmis islemler: ozellik tanimi surumu -> sayi (eski kayit atilmaz, oran gorunur)
        self.surum = 0
        self.duraklat_bitis: datetime | None = None
        self.son_guncelleme: str | None = None
        self.son_geri_donus: dict | None = None
        self.bugun: dict = {"tarih": None, "sonuc": 0, "guncelleme": 0, "geri_donus": 0}
        self.n_etkin = 0.0
        self._yeni_sonuc = 0
        self._izle: dict | None = None
        self._imza: tuple | None = None
        self._temizlik_gun: str | None = None

    # ------------------------------------------------------------------ dosya
    def _p(self, ad: str) -> Path:
        return self.dir / ad

    def _ekle(self, yol: Path, satirlar: list[dict]) -> None:
        yol.parent.mkdir(parents=True, exist_ok=True)
        with open(yol, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(s, separators=(",", ":"), allow_nan=False) + "\n" for s in satirlar))

    def _oku(self, yol: Path):
        try:
            with open(yol, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        try:
                            yield json.loads(ln)
                        except ValueError:
                            self.sayac["bozuk_satir"] += 1
        except FileNotFoundError:
            return

    def asama(self) -> str:
        """'suzme': gecerli ogrenilmis paket etkin; 'ogrenme': paket yok (kapi her adayi gecirir)."""
        got, _ = M.load_package(self.paket_yolu)
        return "suzme" if got is not None else "ogrenme"

    def _hiz(self, simdi: datetime) -> tuple[float | None, str | None]:
        from trader_ml.ml1.hiz import hiz_hesapla     # etiketli (gercek+sanal) satirlar; N durum satiriyla ayni (n_kapali)
        try:
            return hiz_hesapla([pd.Timestamp(s[1], unit="ns", tz="UTC") for s in self._sn], self.n_kapali, self.min_islem, simdi)
        except Exception:  # noqa: BLE001
            return None, None

    def etkin_sanal_agirlik(self) -> float:
        """Egitimde kullanilan sanal agirlik: ayar degeri, olcum onerisi (`agirlik_fn`) daha dusukse o. Hicbir zaman ayari YUKSELTMEZ. Firlatmaz."""
        try:
            if self.agirlik_fn is not None:
                v = float(self.agirlik_fn())
                if math.isfinite(v) and 0.0 <= v <= 1.0:
                    return min(self.sanal_agirlik, v)
        except Exception:  # noqa: BLE001
            pass
        return self.sanal_agirlik

    def _kiyas(self) -> dict | None:
        """durum.json icin golge-gercek kiyas aynasi {n, ort_mutlak_dr, isaret_uyumu, agirlik_dusur} ya da None. Firlatmaz."""
        try:
            if self.kiyas_fn is None:
                return None
            k = self.kiyas_fn()
            if not isinstance(k, dict):
                return None
            return {a: k.get(a) for a in ("n", "ort_mutlak_dr", "isaret_uyumu", "agirlik_dusur")}
        except Exception:  # noqa: BLE001
            return None

    def _durum_yaz(self, simdi: datetime) -> None:
        hiz, varis = self._hiz(simdi)
        d = {"aktif": True, "kuru": self.kuru, "asama": self.asama(), "kapali_islem": self.n_kapali, "gercek": self.n_kapali - self.n_sanal, "sanal": self.n_sanal,
             "bekleyen_sanal": len(self.sanal_bekleyen), "sanal_agirlik": self.sanal_agirlik, "sanal_agirlik_etkin": self.etkin_sanal_agirlik(),
             "sanal_kiyas": self._kiyas(), "sinama_aralik": self.sinama_aralik,
             "sonraki_sinama_n": self.sonraki_sinama_n, "min_islem": self.min_islem,
             "min_islem_tf": self.min_islem_tf, "kapali_islem_tf": {tf: int(self.n_tf.get(tf, 0)) for tf in M.TFS}, "oz_karisik": {k: int(v) for k, v in sorted(self.n_oz.items())},
             "esik": self.esik,
             "surum": self.surum, "son_guncelleme": self.son_guncelleme, "guncellendi": pd.Timestamp(simdi).isoformat(),
             "bugun": dict(self.bugun), "n_etkin": round(self.n_etkin, 3), "n_tampon": len(self._sn), "bekleyen": len(self.bekleyen),
             "duraklat_bitis": None if self.duraklat_bitis is None else self.duraklat_bitis.isoformat(),
             "son_geri_donus": self.son_geri_donus, "son_sinama": self.son_sinama, "sayac": dict(self.sayac),
             "gunluk_hiz": hiz, "tahmini_varis": varis}
        _atomik_yaz_bayt(self._p("durum.json"), json.dumps(d, sort_keys=True, indent=1).encode("utf-8"))

    # ------------------------------------------------------------------ baslangic: dosyalardan kurulum
    def baslat(self, simdi: datetime | None = None) -> bool:
        """Durum/alinan/sonuc dosyalarindan bellegi kurar. Firlatmaz. Doner: hazir mi."""
        try:
            simdi = simdi or self.now_fn()
            dur = None
            try:
                dur = json.loads(self._p("durum.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            if dur:
                self.surum = int(dur.get("surum") or 0)
                self.son_guncelleme = dur.get("son_guncelleme")
                self.son_geri_donus = dur.get("son_geri_donus")
                self.son_sinama = dur.get("son_sinama")
                sn = dur.get("sonraki_sinama_n")
                self.sonraki_sinama_n = int(sn) if isinstance(sn, int) and not isinstance(sn, bool) else None
                self.bugun.update(dur.get("bugun") or {})
                db = dur.get("duraklat_bitis")
                self.duraklat_bitis = pd.Timestamp(db).to_pydatetime() if db else None
            self._kur(simdi)
            self.hazir = True
            self._imza = self._dosya_imza()
            self._durum_yaz(simdi)
            return True
        except Exception as e:  # noqa: BLE001
            self.sayac["hata"] += 1
            log.error("ML1 ogrenme baslatilamadi: %r", e, exc_info=True)
            return False

    def _aylar(self, simdi: datetime, n: int) -> list[str]:
        t = pd.Timestamp(simdi)
        return [(t - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(n)][::-1]

    def _kur(self, simdi: datetime) -> None:
        sinir_ns = (pd.Timestamp(simdi) - pd.Timedelta(days=PENCERE_GUN)).as_unit("ns").value
        self._sn, self.n_kapali, self.n_tf, self.n_oz = [], 0, Counter(), Counter()
        self.n_sanal, self.sanal_bekleyen, self.sanal_bilinen, self._sanal_son = 0, {}, set(), {}
        self.gercek = {}
        sonuc_satir: dict[int, dict] = {}
        for ay in self._aylar(simdi, SAKLA_AY):
            for r in self._oku(self._p(f"sonuclar-{ay}.jsonl")):
                tid = int(r["trade_id"])
                self.bilinen.add(tid)
                self.kapali.add(tid)
                if "y" in r and r.get("x") is not None:
                    sonuc_satir[tid] = r
                    self.n_kapali += 1
                    self.n_tf[r["tf"]] += 1
                    self.n_oz[str(int(r.get("oz") or 1))] += 1
                    ts = pd.Timestamp(r["decision_ts"]).as_unit("ns").value
                    if ts >= sinir_ns:
                        self._sn.append((r["k"], ts, float(r["y"]), r["pair"], r["side"], r["tf"], _vek(r["x"]), False))
        for ay in self._aylar(simdi, SAKLA_AY):
            for r in self._oku(self._p(f"alinanlar-{ay}.jsonl")):
                tid = int(r["trade_id"])
                self.bilinen.add(tid)
                if tid not in self.kapali and r.get("x") is not None:
                    self.bekleyen[tid] = r
                sr = sonuc_satir.get(tid)
                if sr is not None:                                  # olcumler icin: alinan kayit + sonuc (eslesen yoksa atlanir)
                    self._gercek_ekle(tid, r, sr)
                self._sanal_olay_isle(r["pair"], r["side"], r["tf"], pd.Timestamp(r["decision_ts"]), True)       # gercek giris: olay zinciri (golge yok)
        if self.sanal is not None:                                  # golge ogrenme kapaliyken sanal dosyalar egitime KATILMAZ
            self._sanal_kur(sinir_ns, simdi)

    def _gercek_ekle(self, tid: int, alinan: Mapping, sonuc: Mapping) -> None:
        self.gercek[tid] = {**{k: v for k, v in alinan.items() if k != "x"}, "exit_ts": sonuc.get("exit_ts"), "y": sonuc.get("y"),
                            "r_net": sonuc.get("r_net"), "exit_reason": sonuc.get("exit_reason")}
        while len(self.gercek) > GERCEK_MAKS:
            self.gercek.pop(next(iter(self.gercek)))

    # ------------------------------------------------------------------ kapidan: gercekten alinan islem
    def islem_alindi(self, r: dict) -> bool:
        """Motor bir islem actiginda (kapi `note_taken`): adayin ozellik vektoru gercek islem kimligiyle saklanir. Yazim hatasi YUKARI firlar
        (kapi sayar, karar etkilenmez). Doner: yeni kayit mi."""
        tid = int(r["trade_id"])
        if tid in self.bilinen:
            return False
        rec = dict(r)
        rec["k"] = f"{rec['pair']}|{rec['arm_id']}|{rec['side']}|{pd.Timestamp(rec['decision_ts']).isoformat()}"
        self._ekle(self._p(f"alinanlar-{_ay(rec['decision_ts'])}.jsonl"), [rec])
        self.bilinen.add(tid)
        self.bekleyen[tid] = rec
        self.sayac["alinan"] += 1
        return True

    # ------------------------------------------------------------------ gercek defter sonucu
    def _kapat(self, rec: dict, neden: str, D: datetime) -> None:
        tid = int(rec["trade_id"])
        self._ekle(self._p(f"sonuclar-{_ay(D)}.jsonl"), [{"trade_id": tid, "kapandi": neden}])
        self.kapali.add(tid)
        self.bekleyen.pop(tid, None)
        self.sayac["kapandi_" + neden] += 1

    def topla(self, D: datetime) -> int:
        """Bekleyen alinan islemlerden defterde KAPANANLARI etiketler (y = net r_multiple > 0). Doner: yeni etiketli sayi."""
        if not self.bekleyen or self.ledger is None:
            return 0
        d0 = min(pd.Timestamp(r["decision_ts"]) for r in self.bekleyen.values())
        try:
            kap = {t.trade_id: t for t in self.ledger.list_closed_trades(since=d0.to_pydatetime(), until=pd.Timestamp(D).to_pydatetime() + timedelta(minutes=1),
                                                                      limit=10000)}
        except Exception as e:  # noqa: BLE001
            self.sayac["defter_hata"] += 1
            log.warning("ML1 ogrenme: defter okunamadi: %r", e)
            return 0
        n = 0
        for tid, r in list(self.bekleyen.items()):
            t = kap.get(tid)
            if t is None:
                if (pd.Timestamp(D) - pd.Timestamp(r["decision_ts"])) > pd.Timedelta(days=YAS_KAPAT_GUN):
                    self._kapat(r, "kapanmadi", D)
                continue
            if t.decision_id != r["decision_id"] or t.pair != r["pair"] or t.side != r["side"]:
                self._kapat(r, "eslesme_hatasi", D)                  # ayni trade_id, farkli karar/cift/yon: ogrenilmez
                continue
            rm = t.r_multiple
            if rm is None or not np.isfinite(rm) or t.exit_ts is None:
                self._kapat(r, "r_yok", D)
                continue
            y = 1 if rm > 0 else 0
            row = {"trade_id": tid, "decision_id": int(r["decision_id"]), "k": r["k"], "decision_ts": r["decision_ts"],
                   "exit_ts": pd.Timestamp(t.exit_ts).isoformat(), "y": y, "r_net": float(rm), "exit_reason": t.exit_reason, "tf": r["tf"],
                   "pair": r["pair"], "side": r["side"], "arm_id": r["arm_id"], "x": r["x"], "oz": int(r.get("oz") or 1)}
            self._ekle(self._p(f"sonuclar-{_ay(D)}.jsonl"), [row])
            self._gercek_ekle(tid, r, row)
            self.kapali.add(tid)
            self.bekleyen.pop(tid, None)
            self._sn.append((r["k"], pd.Timestamp(r["decision_ts"]).as_unit("ns").value, float(y), r["pair"], r["side"], r["tf"], _vek(r["x"]), False))
            self.n_kapali += 1
            self.n_tf[r["tf"]] += 1
            self.n_oz[str(int(r.get("oz") or 1))] += 1
            self._yeni_sonuc += 1
            self.bugun["sonuc"] += 1
            n += 1
        return n

    # ------------------------------------------------------------------ uydurma + yazim
    def _tampon(self) -> tuple[pd.DataFrame, np.ndarray]:
        d = pd.DataFrame({"k": [s[0] for s in self._sn], "decision_ts": pd.to_datetime([s[1] for s in self._sn], unit="ns", utc=True),
                          "y": [s[2] for s in self._sn], "pair": [s[3] for s in self._sn], "side": [s[4] for s in self._sn],
                          "tf": [s[5] for s in self._sn], "sanal": np.array([bool(s[7]) for s in self._sn], bool)})
        X = np.vstack([s[6] for s in self._sn]).astype(float) if self._sn else np.zeros((0, len(M.feature_names())))
        return d, X

    def _tampon_buda(self, simdi: datetime) -> None:
        sinir = (pd.Timestamp(simdi) - pd.Timedelta(days=PENCERE_GUN)).as_unit("ns").value
        self._sn = [s for s in self._sn if s[1] >= sinir]
        if len(self._sn) > MAKS_SATIR:
            self._sn = sorted(self._sn, key=lambda s: (s[1], s[0]))[-MAKS_SATIR:]

    def esik_asildi(self) -> bool:
        """Ilk paket icin yeterli kapanan ogrenilmis islem var mi (toplam >= min_islem; min_islem_tf > 0 ise her zaman diliminde >= min_islem_tf)."""
        if self.n_kapali < self.min_islem:
            return False
        if self.min_islem_tf > 0 and any(self.n_tf.get(tf, 0) < self.min_islem_tf for tf in M.TFS):
            return False
        return True

    def guncelle(self, D: datetime) -> dict | None:
        """Bir uydurma + denetim + (kuru degilse) yazim denemesi. Denetim kaydi satirini doner (esik asilmadiysa None)."""
        if not self.esik_asildi():
            self.sayac["esik_bekle"] += 1
            return None
        t0 = self.now_fn()
        self._tampon_buda(D)
        d, X = self._tampon()
        if self.sonraki_sinama_n is not None and self.n_kapali < self.sonraki_sinama_n:
            self.sayac["sinama_aralik_bekle"] += 1                  # son basarisiz sinamadan beri yeterli yeni etiketli satir yok
            return None
        r = uydur(d, X, D, yari_omur_gun=self.yari_omur, sanal_agirlik=self.etkin_sanal_agirlik())
        if r is None:
            self.sayac["uydurulamadi"] += 1
            self._yeni_sonuc = 0                                 # tek sinif/veri yok: sonraki kapanan islemde yeniden denenir
            return None
        self.n_etkin = r["n_etkin"]
        s = None
        if self.sinama:
            s = sina(d, X, D, yari_omur_gun=self.yari_omur, sanal_agirlik=self.etkin_sanal_agirlik())
            self.son_sinama = {"ts": pd.Timestamp(D).isoformat(), **s}
            self.sonraki_sinama_n = None if s["gecti"] else self.n_kapali + self.sinama_aralik
            if not s["gecti"]:
                self.son_sinama["sonraki_sinama_n"] = self.sonraki_sinama_n
        yeni = yeni_paket(r, esik=self.esik, surum=self.surum + 1, simdi=D, metrics=None if s is None else {"sinama": s})
        red, olc = denetle(yeni, self.esik)
        onceki, _ = M.load_package(self.paket_yolu)
        satir = {"ts": pd.Timestamp(D).isoformat(), "surum": self.surum + 1, "onceki_sha": None if onceki is None else str(onceki["sha256"])[:12],
                 "yeni_sha": str(yeni["sha256"])[:12], "yeni_sonuc": self._yeni_sonuc, "n_sonuc": r["n_sonuc"], "kapali_islem": self.n_kapali,
                 "n_etkin": round(r["n_etkin"], 3), "sanal_agirlik": self.etkin_sanal_agirlik()}
        if s is not None:
            satir["sinama"] = s
        if s is not None and not s["gecti"]:
            # yayin kapisi: etkin paket (varsa) AYNEN kalir, geri donus tetiklenmez, ogrenme surer (sonraki kapanan islemde yeniden denenir)
            satir["sonuc"] = f"reddedildi:{s['neden']}"
            self.sayac["sinama_red"] += 1
            log.warning("ML1 paketi orneklem-disi sinamayi gecemedi: %s", s["neden"])
        elif red is not None:
            satir["sonuc"] = f"reddedildi:{red}"
            self.sayac["reddedildi"] += 1
            log.warning("ML1 guncelleme reddedildi: %s", red)
        elif self.kuru:
            satir["sonuc"] = "kuru"
            self.sayac["kuru"] += 1
        else:
            try:
                self._yaz(yeni)
                self.surum += 1
                self.son_guncelleme = pd.Timestamp(D).isoformat()
                self.bugun["guncelleme"] += 1
                self.sayac["yazildi"] += 1
                satir["sonuc"] = "yazildi"
                c = getattr(self.kapi, "counters", None) or {}
                self._izle = {"sha": yeni["sha256"], "hata0": int(c.get("ml1_hata", 0)),
                              "gecti0": int(c.get("ml1_gecti", 0)) + int(c.get("ml1_ayni_olay", 0)), "alt0": int(c.get("ml1_esik_alti", 0))}
            except Exception as e:  # noqa: BLE001
                satir["sonuc"] = f"reddedildi:yazim_hatasi:{type(e).__name__}"
                self.sayac["yazim_hatasi"] += 1
                log.error("ML1 paket yazimi basarisiz: %r", e)
        satir["sure_ms"] = round((self.now_fn() - t0).total_seconds() * 1000.0, 1)
        self._yeni_sonuc = 0
        try:
            self._ekle(self._p("guncellemeler.jsonl"), [satir])
        except OSError as e:
            log.error("ML1 denetim kaydi yazilamadi: %r", e)
        return satir

    def _yaz(self, pkg: dict) -> None:
        """tmp'ye yaz + geri oku/dogrula; onceki OGRENILMIS etkin paketi son_iyi'ye kopyala (yoksa eski son_iyi silinir); os.replace.
        Hata = etkin paket degismez."""
        tmp = self.paket_yolu.with_name(self.paket_yolu.name + ".tmp")
        try:
            self.paket_yolu.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(pkg, sort_keys=True, indent=1), encoding="utf-8")
            got, why = M.load_package(tmp)
            if got is None:
                raise ValueError(f"geri okuma dogrulamasi basarisiz: {why}")
            cur, _ = M.load_package(self.paket_yolu)
            if cur is not None:
                _atomik_yaz_bayt(self.son_iyi_yolu, self.paket_yolu.read_bytes())
            else:
                self.son_iyi_yolu.unlink(missing_ok=True)        # onceki ogrenilmis paket yok: geri donus = paket yok
            os.replace(tmp, self.paket_yolu)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        self._imza = self._dosya_imza()

    # ------------------------------------------------------------------ izleme + geri donus
    def _dosya_imza(self):
        try:
            st = os.stat(self.paket_yolu)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def geri_don(self, D: datetime, neden: str) -> None:
        """Onceki ogrenilmis pakete, o yoksa pakete hic (= ogrenme asamasi: kapi her adayi gecirir) donulur. ASLA tohum paket yok."""
        son, _ = M.load_package(self.son_iyi_yolu)
        try:
            if son is not None:
                _atomik_yaz_bayt(self.paket_yolu, self.son_iyi_yolu.read_bytes())
            else:
                self.paket_yolu.unlink(missing_ok=True)          # kapi ogrenme asamasina duser
        except OSError as e:
            log.critical("ML1 geri donus yazimi basarisiz: %r", e)
        self._imza = self._dosya_imza()
        self._izle = None
        self.duraklat_bitis = pd.Timestamp(D).to_pydatetime() + DURAKLAT
        self.bugun["geri_donus"] += 1
        self.sayac["geri_donus"] += 1
        self.son_geri_donus = {"ts": pd.Timestamp(D).isoformat(), "neden": neden, "son_iyi": son is not None}
        log.critical("ML1 ogrenme: %s PAKETE DONULDU (%s); ogrenme 24 saat duraklatildi", "ONCEKI" if son is not None else "HICBIR (ogrenme asamasi)", neden)
        try:
            self._ekle(self._p("guncellemeler.jsonl"), [{"ts": pd.Timestamp(D).isoformat(), "sonuc": f"geri_donuldu:{neden}",
                                                         "surum": self.surum, "son_iyi_var": son is not None}])
        except OSError:
            pass

    def izle(self, D: datetime) -> None:
        imza = self._dosya_imza()
        if imza != self._imza:
            self._imza = imza
            if imza is not None:
                got, why = M.load_package(self.paket_yolu)
                if got is None:
                    return self.geri_don(D, f"etkin_paket_gecersiz:{why}"[:120])
        if self._izle is None or self.kapi is None:
            return
        c = getattr(self.kapi, "counters", {})
        if int(c.get("ml1_hata", 0)) > self._izle["hata0"]:
            return self.geri_don(D, "kapi_puanlama_hatasi")
        dur = getattr(self.kapi, "paket_durumu", None)
        if callable(dur):
            guncel, sha = dur()
            if guncel and sha != self._izle["sha"]:
                return self.geri_don(D, "kapi_paketi_reddetti")
        ust = int(c.get("ml1_gecti", 0)) + int(c.get("ml1_ayni_olay", 0)) - self._izle["gecti0"]
        alt = int(c.get("ml1_esik_alti", 0)) - self._izle["alt0"]
        if ust + alt >= GERI_IZLE_MIN:
            if ust == 0:                                         # paket her adayi reddediyor: yeni islem de ogrenme de durur
                return self.geri_don(D, "gecme_orani:0.00")
            self._izle = None

    # ------------------------------------------------------------------ golge (sanal) ogrenme
    @staticmethod
    def _aralik(tf: str) -> pd.Timedelta:
        from trader_core import arm_time as AT
        return pd.Timedelta(K_BARS * AT.arm_tf_delta(tf))

    def _sanal_olay_isle(self, pair: str, side: str, tf: str, ts: pd.Timestamp, giris: bool) -> bool:
        """Olay zinciri (`features.events` kurali: ayni cift|yon|tf, ardisik bosluk <= K mum). Doner: bu aday YENI ve gercek giris icermeyen olayin ilki mi."""
        key = (pair, side, tf)
        eski = self._sanal_son.get(key)
        devam = eski is not None and ts - eski[0] <= self._aralik(tf) and ts >= eski[0]
        girdi = giris or (devam and eski[1])
        self._sanal_son[key] = (max(ts, eski[0]) if devam else ts, bool(girdi))
        return (not devam) and not giris

    def _sanal_kur(self, sinir_ns: int, simdi: datetime) -> None:
        bek: dict[str, dict] = {}
        for ay in self._aylar(simdi, SAKLA_AY):
            for r in self._oku(self._p(f"sanallar-{ay}.jsonl")):
                sid = r.get("sid")
                if not sid:
                    continue
                t = r.get("t")
                if t == "aday":
                    self._sanal_olay_isle(r["pair"], r["side"], r["tf"], pd.Timestamp(r["decision_ts"]), False)
                    if sid not in self.sanal_bilinen:
                        bek[sid] = r
                    self.sanal_bilinen.add(sid)
                elif t == "sonuc":
                    bek.pop(sid, None)
                    self.sanal_bilinen.add(sid)
                    if r.get("x") is not None and "y" in r:
                        self.n_kapali += 1
                        self.n_sanal += 1
                        self.n_tf[r["tf"]] += 1
                        self.n_oz[str(int(r.get("oz") or 1))] += 1
                        ts = pd.Timestamp(r["decision_ts"]).as_unit("ns").value
                        if ts >= sinir_ns:
                            self._sn.append((r["k"], ts, float(r["y"]), r["pair"], r["side"], r["tf"], _vek(r["x"]), True))
                elif t == "iptal":
                    bek.pop(sid, None)
        self.sanal_bekleyen = bek

    def _sanal_yaz(self, ts, satir: dict) -> None:
        self._ekle(self._p(f"sanallar-{_ay(ts)}.jsonl"), [satir])

    def sanal_giris(self, pair: str, side: str, tf: str, D: datetime) -> None:
        """Gercek giris: ayni olaydaki BEKLEYEN sanal adaylar iptal edilir (bir olay = ya gercek islem ya sanal aday); zincir 'girisli' isaretlenir."""
        if self.sanal is None or not self.hazir:
            return
        ts = pd.Timestamp(D)
        self._sanal_olay_isle(pair, side, tf, ts, True)
        for sid, r in list(self.sanal_bekleyen.items()):
            if (r["pair"], r["side"], r["tf"]) == (pair, side, tf) and 0 <= (ts - pd.Timestamp(r["decision_ts"])) / pd.Timedelta(1, "s") <= self._aralik(tf).total_seconds():
                self._sanal_yaz(ts, {"t": "iptal", "sid": sid, "neden": "olayda_gercek_giris"})
                self.sanal_bekleyen.pop(sid, None)
                self.sayac["sanal_iptal_giris"] += 1

    def sanal_adaylar(self, D: datetime, adaylar: list[dict]) -> int:
        """Bu adimda ML1 kapisina ulasip ALINMAYAN uygun adaylar (stop tabani gecmis, sinyal dogru; her biri ozet + x + skor + mod/time_stop/trail_atr).
        Olay basina en cok bir sanal aday: yeni olayda en yuksek puanli (puan yoksa kapi sirasindaki ilk). Doner: yeni kayit sayisi."""
        if self.sanal is None or not self.hazir or not adaylar:
            return 0
        ts = pd.Timestamp(D)
        gr: dict[tuple, list[dict]] = {}
        for a in adaylar:
            gr.setdefault((a["pair"], a["side"], a["tf"]), []).append(a)
        n = 0
        for (pair, side, tf), lst in gr.items():
            if not self._sanal_olay_isle(pair, side, tf, ts, False):
                continue
            en = lst[0]
            for a in lst[1:]:
                if (a.get("skor") is not None) and (en.get("skor") is None or a["skor"] > en["skor"]):
                    en = a
            if len(self.sanal_bekleyen) >= self.sanal.tavan:
                self.sayac["sanal_tavan"] += 1
                continue
            rec = dict(en)
            rec["decision_ts"] = ts.isoformat()
            rec["k"] = f"{pair}|{rec['arm_id']}|{side}|{ts.isoformat()}"
            rec["sid"] = "s|" + rec["k"]
            rec["t"] = "aday"
            if rec["sid"] in self.sanal_bilinen:
                continue
            self._sanal_yaz(ts, rec)
            self.sanal_bilinen.add(rec["sid"])
            self.sanal_bekleyen[rec["sid"]] = rec
            self.sayac["sanal_aday"] += 1
            n += 1
        return n

    def sanal_coz(self, D: datetime) -> int:
        """Bekleyen sanal adaylari simulasyonla etiketler (adim basina en cok `butce` kontrol; her aday en cok `kontrol_aralik`te bir). Doner: yeni etiketli sayi."""
        sc = self.sanal
        if sc is None or not self.hazir or not self.sanal_bekleyen:
            return 0
        from . import ml1_sanal as SN
        now = pd.Timestamp(D)
        sira = sorted(self.sanal_bekleyen, key=lambda k: self._sanal_kontrol.get(k, pd.Timestamp(0, tz="UTC")))
        kontrol, n = 0, 0
        for sid in sira:
            if kontrol >= sc.butce:
                break
            r = self.sanal_bekleyen[sid]
            ts = pd.Timestamp(r["decision_ts"])
            son = self._sanal_kontrol.get(sid)
            if son is not None and now - son < sc.kontrol_aralik:
                continue
            if now <= ts:
                continue
            kontrol += 1
            self._sanal_kontrol[sid] = now
            try:
                b15, trig, fon = SN.veri_al(sc.view, r, now, r["mod"] == "trail")
                res = SN.simule(r, b15, trig, sc.maliyet_fn(r["pair"], ts.to_pydatetime()), fon, now)
            except Exception as e:  # noqa: BLE001
                self.sayac["sanal_hata"] += 1
                log.warning("ML1 sanal simulasyon hatasi %s: %r", sid, e)
                continue
            if res is None:
                if now - ts > pd.Timedelta(days=SN.MAKS_GUN + SN.VERI_YOK_GUN + 1):
                    self._sanal_yaz(now, {"t": "iptal", "sid": sid, "neden": "cozulemedi"})
                    self.sanal_bekleyen.pop(sid, None)
                    self.sayac["sanal_iptal_veri"] += 1
                continue
            row = {"t": "sonuc", "sid": sid, "k": r["k"], "decision_ts": r["decision_ts"], "exit_ts": res.exit_ts.isoformat(), "y": res.y,
                   "r_net": res.r_net, "exit_reason": res.exit_reason, "kesildi": res.kesildi, "tf": r["tf"], "pair": r["pair"], "side": r["side"],
                   "arm_id": r["arm_id"], "x": r["x"], "oz": int(r.get("oz") or 1)}
            self._sanal_yaz(now, row)
            self.sanal_bekleyen.pop(sid, None)
            self._sanal_kontrol.pop(sid, None)
            self._sn.append((r["k"], ts.as_unit("ns").value, float(res.y), r["pair"], r["side"], r["tf"], _vek(r["x"]), True))
            self.n_kapali += 1
            self.n_sanal += 1
            self.n_tf[r["tf"]] += 1
            self.n_oz[str(int(r.get("oz") or 1))] += 1
            self._yeni_sonuc += 1
            self.bugun["sonuc"] += 1
            self.sayac["sanal_sonuc"] += 1
            n += 1
        return n

    # ------------------------------------------------------------------ motor girisi
    def temizle(self, D: datetime) -> None:
        gun = pd.Timestamp(D).strftime("%Y-%m-%d")
        if self._temizlik_gun == gun:
            return
        self._temizlik_gun = gun
        tut = set(self._aylar(D, SAKLA_AY))
        for p in self.dir.glob("*-????-??.jsonl"):
            if p.stem.rsplit("-", 2)[-2] + "-" + p.stem.rsplit("-", 1)[-1] not in tut:
                try:
                    p.unlink()
                except OSError:
                    pass

    def adim(self, D: datetime, acik_ciftler=()) -> dict:
        """Her karar adiminin sonunda. Firlatmaz. Doner: {"sonuc": n, "guncelleme": bool}."""
        out: dict[str, Any] = {"sonuc": 0, "guncelleme": False}
        if not self.hazir:
            return out
        try:
            gun = pd.Timestamp(D).strftime("%Y-%m-%d")
            if self.bugun.get("tarih") != gun:
                self.bugun = {"tarih": gun, "sonuc": 0, "guncelleme": 0, "geri_donus": 0}
            self.izle(D)
            out["sonuc"] = self.topla(D)
            out["sanal"] = self.sanal_coz(D)
            dur = self.duraklat_bitis is not None and pd.Timestamp(D) < pd.Timestamp(self.duraklat_bitis)
            if self._yeni_sonuc > 0 and not dur:
                out["guncelleme"] = self.guncelle(D) is not None
            self.temizle(D)
            self._durum_yaz(D)
        except Exception as e:  # noqa: BLE001
            self.sayac["hata"] += 1
            log.error("ML1 ogrenme adimi hatasi: %r", e, exc_info=True)
        return out
