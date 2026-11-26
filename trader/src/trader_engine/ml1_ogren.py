"""ML1 aninda ogrenme (yalniz kagit): her sonuclanan adaydan ayni gun guncelleme, bozuk guncellemede son iyi pakete otomatik donus.

Akis (karar adimi sonunda, `_shadow_step` kalibi: durum/broker/emir/kapi uzerinde YAZMA yok, istisna sizmaz, zaman butceli):
  1) kapi, puanladigi her adayi `adaylar-YYYY-MM.jsonl` dosyasina (ham ozellik vektoru x ile) ekler (`kaydet`).
  2) `adim`: sonucu belli olmamis adaylari egitimdeki AYNI cikis simulatoruyle (`exitsim.simulate_rows`) oynatir; sonuc `sonuclar-*.jsonl`.
     Etiket: y = 1 eger net_R > 0 (status ok, censored degil). Alinan islemin gercek defter R'i yalniz kontrol sayisidir.
  3) yeni sonuc varsa: taban paket (tohum) merkezli, yasa gore agirlikli ridge lojistik Newton uydurmasi (`uydur`); denetim (`denetle`);
     atomik yazim (`.tmp` + son_iyi + os.replace). Kapi dosyanin mtime'i degisince paketi zaten yeniden yukler.
  4) her adim: etkin paket bozulduysa / kapi reddettiyse / ilk 40+ adayda gecme orani %0 ya da > %80 ise son iyiye donus + 24 saat duraklatma.
Esik (0,58) tabandan kopyalanir, burada ASLA hesaplanmaz. `ogrenme.kuru=true`: her sey calisir, yalniz etkin paket yazilmaz.
Saat: yalniz enjekte edilen `now_fn` (motor saati). Ag/yeni servis/defter semasi degisikligi yok."""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from trader_core import arm_time as AT
from trader_ml.ml1 import features as F
from trader_ml.ml1 import model as M

log = logging.getLogger("engine.ml1_ogren")

N0 = 5000.0                       # tabanin "kac sonuca bedel" sayilacagi
YARI_OMUR_GUN = 30.0
PENCERE_GUN = 90
MAKS_SATIR = 50_000
Z_KIRP = 5.0
KUTU_COEF, KUTU_B = 0.25, 0.20    # taban etrafinda sert sinir
MAKS_ITER = 25
REF_N, REF_MIN = 2000, 200
COZ_BUTCE_S = 5.0
GERI_IZLE_MIN = 40
DURAKLAT = timedelta(hours=24)
HORIZON_GUN = 30
YAS_KAPAT_GUN = 32                # veri hic gelmeyen aday bu yastan sonra etiketsiz kapatilir
BEKLE_SAAT = 2                    # invalid/no_data/data_gap: bu yastan once yeniden denenir (veri gecikmesi)
SAKLA_AY = 4
_WARM = {"15m": 600, "1h": 600, "4h": 600, "1d": 300}   # tf mum isinmasi (ATR/rejim)
_WARM_4H = 600
M15 = timedelta(minutes=15)
CHUNK = 25                        # cozme butcesinin cift icinde denetlendigi aday blogu


# ----------------------------------------------------------------------------------------------------------- saf matematik
def olay_agirligi(d: pd.DataFrame) -> np.ndarray:
    """e_i = 1 / (tampondaki ayni olaydaki sonuc sayisi): `features.events` ile ayni kural (pair|side|tf, bosluk <= 3 mum)."""
    if len(d) == 0:
        return np.zeros(0)
    ev = F.events(d[["decision_ts", "pair", "side", "tf"]].reset_index(drop=True))
    return ev["event_weight"].to_numpy(float)


def uydur(taban: Mapping, d: pd.DataFrame, X: np.ndarray, simdi: datetime, *, n0: float = N0, yari_omur_gun: float = YARI_OMUR_GUN,
          pencere_gun: float = PENCERE_GUN, maks_satir: int = MAKS_SATIR) -> dict:
    """Taban merkezli ridge lojistik (Newton/IRLS). `d`: sutunlar k, decision_ts (tz), pair, side, tf, y; `X`: d ile ayni sirada ham ozellikler.
    Sonuc kanonik sirada (decision_ts, k) hesaplanir => girdi sirasindan bagimsiz. Doner coef, b, iter, n_etkin, n_sonuc, ..."""
    coef0 = np.asarray(taban["weights"]["coef"], float)
    b0 = float(taban["weights"]["intercept"])
    k = len(coef0)
    beta0 = np.r_[coef0, b0]
    out = {"coef": coef0.copy(), "b": b0, "iter": 0, "n_etkin": 0.0, "n_sonuc": 0}
    if len(d) == 0:
        return out
    simdi_ns = pd.Timestamp(simdi).as_unit("ns").value
    ts = pd.DatetimeIndex(d["decision_ts"]).as_unit("ns").asi8
    yas_gun = (simdi_ns - ts) / 86_400e9
    keep = np.flatnonzero(yas_gun <= pencere_gun)
    if len(keep) == 0:
        return out
    keep = keep[np.lexsort((d["k"].to_numpy()[keep], ts[keep]))]          # kanonik sira
    keep = keep[-int(maks_satir):]
    dd = d.iloc[keep].reset_index(drop=True)
    e = olay_agirligi(dd)
    age = np.maximum(yas_gun[keep], 0.0)
    w = e * np.exp2(-age / float(yari_omur_gun))
    Z = np.clip(M.standardize(np.asarray(X, float)[keep], taban["standardization"]), -Z_KIRP, Z_KIRP)
    A = np.hstack([Z, np.ones((len(Z), 1))])
    y = dd["y"].to_numpy(float)
    tau = 0.25 * float(n0)
    beta = beta0.copy()
    it = 0
    for it in range(1, MAKS_ITER + 1):
        p = M._sigmoid(A @ beta)
        g = A.T @ (w * (p - y)) + tau * (beta - beta0)
        H = (A * (w * p * (1 - p))[:, None]).T @ A + tau * np.eye(k + 1)
        step = np.linalg.solve(H, g)
        beta = beta - step
        if np.max(np.abs(step)) < 1e-7:
            break
    coef = np.clip(beta[:-1], coef0 - KUTU_COEF, coef0 + KUTU_COEF)
    b = float(np.clip(beta[-1], b0 - KUTU_B, b0 + KUTU_B))
    out.update({"coef": coef, "b": b, "iter": it, "n_etkin": float(w.sum()), "n_sonuc": int(len(dd)),
                "max_dcoef": float(np.max(np.abs(coef - coef0))), "db": float(b - b0)})
    return out


def yeni_paket(taban: Mapping, coef, b: float, *, surum: int, n_sonuc: int, n_etkin: float, simdi: datetime) -> dict:
    """Taban paketin kopyasi + yeni agirliklar + `online` blogu; esik/standardizasyon/ozellikler AYNEN tabandan."""
    pkg = copy.deepcopy(dict(taban))
    pkg.pop("sha256", None)
    pkg["weights"] = {"coef": [float(x) for x in coef], "intercept": float(b)}
    pkg["created_at"] = pd.Timestamp(simdi).isoformat()
    pkg["online"] = {"surum": int(surum), "taban_sha": str(taban["sha256"]), "n_sonuc": int(n_sonuc), "n_etkin": round(float(n_etkin), 4),
                     "guncellendi": pd.Timestamp(simdi).isoformat()}
    pkg = M._clean(pkg)
    pkg["sha256"] = M.package_hash(pkg)
    return pkg


def _kanon(o) -> str:
    return json.dumps(o, sort_keys=True, allow_nan=False)


def gecme_orani(pkg: Mapping, Xref: np.ndarray) -> tuple[float, bool]:
    """(puan >= esik orani, hepsi sonlu mu)."""
    Z = M.standardize(np.asarray(Xref, float), pkg["standardization"])
    pr = M._sigmoid(Z @ np.asarray(pkg["weights"]["coef"], float) + float(pkg["weights"]["intercept"]))
    ok = bool(np.all(np.isfinite(pr)))
    if not ok or len(pr) == 0:
        return float("nan"), ok
    return float(np.mean(pr >= float(pkg["threshold"]))), ok


def denetle(taban: Mapping, yeni: Mapping, Xref: np.ndarray | None) -> tuple[str | None, dict]:
    """Yazmadan once denetim (4.1). Doner (red_nedeni | None, olcumler). Hicbir kosulda firlatmaz."""
    info: dict = {}
    try:
        coef = np.asarray(yeni["weights"]["coef"], float)
        b = float(yeni["weights"]["intercept"])
        if not (np.all(np.isfinite(coef)) and np.isfinite(b)):
            return "agirlik_sonlu_degil", info
        c0 = np.asarray(taban["weights"]["coef"], float)
        b0 = float(taban["weights"]["intercept"])
        eps = 1e-9
        if np.any(np.abs(coef - c0) > KUTU_COEF + eps) or abs(b - b0) > KUTU_B + eps:
            return "kutu_disi", info
        why = M.verify_package(dict(yeni))
        if why is not None:
            return f"paket_gecersiz:{why}", info
        for key in ("feature_names", "standardization", "threshold"):
            if _kanon(yeni.get(key)) != _kanon(taban.get(key)):
                return f"degismemesi_gereken:{key}", info
        if Xref is not None and len(Xref) >= REF_MIN:
            rb, ok0 = gecme_orani(taban, Xref)
            rn, ok1 = gecme_orani(yeni, Xref)
            info.update({"gecme_taban": rb, "gecme_yeni": rn})
            if not (ok0 and ok1):
                return "referans_puan_sonlu_degil", info
            hi = 3 * rb if rb > 0 else 0.01
            if rn < rb / 3 - 1e-12 or rn > hi + 1e-12:
                return f"gecme_orani_disi:{rn:.4f}_taban:{rb:.4f}", info
        return None, info
    except Exception as e:  # noqa: BLE001
        return f"denetim_hatasi:{type(e).__name__}", info


def _ozellik_sha(names) -> str:
    return hashlib.sha256(_kanon(list(names)).encode()).hexdigest()[:16]


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


def _nan_none(x) -> list:
    return [None if not np.isfinite(v) else float(v) for v in np.asarray(x, float)]


# ----------------------------------------------------------------------------------------------------------- ogrenici
class Ml1Ogrenici:
    def __init__(self, dizin, paket_yolu, tohum_yolu, *, view=None, now_fn: Callable[[], datetime], ledger=None, kapi=None,
                 n0: float = N0, yari_omur_gun: float = YARI_OMUR_GUN, kuru: bool = False, butce_s: float = COZ_BUTCE_S) -> None:
        self.dir = Path(dizin)
        self.paket_yolu = Path(paket_yolu)
        self.tohum_yolu = Path(tohum_yolu)
        self.son_iyi_yolu = self.paket_yolu.with_name("ml1_package.son_iyi.json")
        self.view, self.now_fn, self.ledger, self.kapi = view, now_fn, ledger, kapi
        self.n0, self.yari_omur, self.kuru, self.butce_s = float(n0), float(yari_omur_gun), bool(kuru), float(butce_s)
        self.sayac: Counter = Counter()
        self.taban: dict | None = None
        self.hazir = False
        self.cands: dict[str, dict] = {}                 # bekleyen adaylar
        self.kapali: set[str] = set()                    # sonuclanmis ya da etiketsiz kapatilmis anahtarlar
        self.alinan: set[str] = set()
        self.bilinen: set[str] = set()
        self._sn: list[tuple] = []                       # (k, ts_ns, y, pair, side, tf, x float32)
        self.ref: deque = deque(maxlen=REF_N)
        self.imlec: dict[str, str] = {}
        self.surum = 0
        self.duraklat_bitis: datetime | None = None
        self.son_guncelleme: str | None = None
        self.son_geri_donus: dict | None = None
        self.bugun: dict = {"tarih": None, "sonuc": 0, "alinan": 0, "alinmayan": 0, "guncelleme": 0, "geri_donus": 0}
        self.uyusma = {"n": 0, "uyusan": 0}
        self.n_etkin = 0.0
        self._yeni_sonuc = 0
        self._yeni_alinan = 0
        self._onceki_acik: set[str] | None = None
        self._izle: dict | None = None
        self._imza: tuple | None = None
        self._sim_cfg = None
        self._tf_cache: dict[tuple, tuple] = {}
        self._rule_cache: dict[tuple, np.ndarray] = {}
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

    def _durum_yaz(self, simdi: datetime) -> None:
        d = {"aktif": True, "kuru": self.kuru, "surum": self.surum, "son_guncelleme": self.son_guncelleme,
             "guncellendi": pd.Timestamp(simdi).isoformat(), "bugun": dict(self.bugun), "n_etkin": round(self.n_etkin, 3),
             "n_tampon": len(self._sn), "bekleyen": len(self.cands), "imlec": dict(self.imlec),
             "duraklat_bitis": None if self.duraklat_bitis is None else self.duraklat_bitis.isoformat(),
             "son_geri_donus": self.son_geri_donus, "ozellik_adlari_sha": _ozellik_sha(self.taban["feature_names"]) if self.taban else None,
             "uyusma": dict(self.uyusma), "sayac": dict(self.sayac)}
        _atomik_yaz_bayt(self._p("durum.json"), json.dumps(d, sort_keys=True, indent=1).encode("utf-8"))

    # ------------------------------------------------------------------ baslangic: dosyalardan kurulum
    def baslat(self, simdi: datetime | None = None) -> bool:
        """Taban paketi yukler, durum/aday/sonuc dosyalarindan bellegi kurar. Firlatmaz. Doner: hazir mi."""
        try:
            simdi = simdi or self.now_fn()
            pkg, why = M.load_package(self.tohum_yolu)
            if pkg is None:
                log.error("ML1 ogrenme: taban paket yuklenemedi (%s): ogrenme kapali", why)
                self.sayac["taban_yok"] += 1
                return False
            self.taban = pkg
            sha = _ozellik_sha(pkg["feature_names"])
            if list(pkg["feature_names"]) != M.feature_names():
                log.error("ML1 ogrenme: taban paket ozellik adlari kodla uyusmuyor: ogrenme kapali")
                self.sayac["ozellik_uyumsuz"] += 1
                return False
            dur = None
            try:
                dur = json.loads(self._p("durum.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            if dur and dur.get("ozellik_adlari_sha") not in (None, sha):
                log.critical("ML1 ogrenme: ozellik adlari sha'si degisti (%s != %s): ogrenme durdu", dur.get("ozellik_adlari_sha"), sha)
                self.sayac["ozellik_uyumsuz"] += 1
                return False
            if dur:
                self.surum = int(dur.get("surum") or 0)
                self.son_guncelleme = dur.get("son_guncelleme")
                self.imlec = dict(dur.get("imlec") or {})
                self.son_geri_donus = dur.get("son_geri_donus")
                self.bugun.update(dur.get("bugun") or {})
                self.uyusma.update(dur.get("uyusma") or {})
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
        out = []
        for i in range(n):
            out.append((t - pd.DateOffset(months=i)).strftime("%Y-%m"))
        return out[::-1]

    def _kur(self, simdi: datetime) -> None:
        sinir_ns = (pd.Timestamp(simdi) - pd.Timedelta(days=PENCERE_GUN)).as_unit("ns").value
        sonuclar = []
        for ay in self._aylar(simdi, SAKLA_AY):
            for r in self._oku(self._p(f"sonuclar-{ay}.jsonl")):
                self.bilinen.add(r["k"])
                self.kapali.add(r["k"])
                if "y" in r and r.get("x") is not None:
                    ts = pd.Timestamp(r["decision_ts"]).as_unit("ns").value
                    if ts >= sinir_ns:
                        sonuclar.append((r["k"], ts, float(r["y"]), r["pair"], r["side"], r["tf"],
                                         np.array([np.nan if v is None else v for v in r["x"]], np.float32)))
        self._sn = sonuclar
        cand_sinir = (pd.Timestamp(simdi) - pd.Timedelta(days=YAS_KAPAT_GUN)).as_unit("ns").value
        for ay in self._aylar(simdi, 2):
            for r in self._oku(self._p(f"adaylar-{ay}.jsonl")):
                if r.get("alindi") and "x" not in r:
                    self.alinan.add(r["k"])
                    continue
                if "x" not in r:
                    continue
                self.bilinen.add(r["k"])
                self.ref.append(np.array([np.nan if v is None else v for v in r["x"]], float))
                if r["k"] not in self.kapali and pd.Timestamp(r["decision_ts"]).as_unit("ns").value >= cand_sinir:
                    self.cands[r["k"]] = r

    # ------------------------------------------------------------------ kapidan gelen adaylar
    def kaydet(self, recs: list[dict]) -> int:
        """Kapinin puanladigi adaylar. Yazim hatasi YUKARI firlar (kapi sayar, karar etkilenmez). Doner: eklenen sayi."""
        yeni = [r for r in recs if r["k"] not in self.bilinen]
        if not yeni:
            return 0
        by_ay: dict[str, list[dict]] = {}
        for r in yeni:
            by_ay.setdefault(_ay(r["decision_ts"]), []).append(r)
        for ay, rs in by_ay.items():
            self._ekle(self._p(f"adaylar-{ay}.jsonl"), rs)
        for r in yeni:
            self.bilinen.add(r["k"])
            self.cands[r["k"]] = r
            self.ref.append(np.array([np.nan if v is None else v for v in r["x"]], float))
        return len(yeni)

    def isaretle_alindi(self, pair: str, arm_id: str, side: str, D: datetime) -> None:
        k = f"{pair}|{arm_id}|{side}|{pd.Timestamp(D).isoformat()}"
        if k in self.alinan:
            return
        self._ekle(self._p(f"adaylar-{_ay(D)}.jsonl"), [{"k": k, "alindi": True}])
        self.alinan.add(k)

    # ------------------------------------------------------------------ cozme
    def _sim_config(self):
        if self._sim_cfg is None:
            from trader_ml.ml1 import exitsim
            self._sim_cfg = exitsim.load_sim_config()
        return self._sim_cfg

    def _gecen_s(self, t0: datetime) -> float:
        return (self.now_fn() - t0).total_seconds()

    def _tf_bars(self, pair: str, tf: str, D: datetime, dmin: pd.Timestamp):
        """(trig, bars_tf(prepare_tf), cache_anahtari) : ilk bekleyen karardan onceki isinmayla pencere."""
        from trader_ml.ml1 import scan as SC
        from trader_ml.ml1 import exitsim as XS
        delta = AT.arm_tf_delta(tf)
        span = int((pd.Timestamp(D) - dmin) / delta) + 2
        if tf == "1d":
            from trader_engine.bars import aggregate_4h_to_1d
            n4 = (span + _WARM["1d"]) * 6 + 6
            h4 = self.view.bars(pair, "4h", D, n4)
            trig = aggregate_4h_to_1d(h4)
        else:
            trig = self.view.bars(pair, tf, D, span + _WARM[tf])
            if tf == "4h":
                h4 = trig
            else:
                n4 = int(len(trig) * delta / timedelta(hours=4)) + _WARM_4H
                h4 = self.view.bars(pair, "4h", D, n4)
        if len(trig) == 0 or len(h4) == 0:
            return None
        key = (pair, tf, trig.index[0], trig.index[-1])
        hit = self._tf_cache.get((pair, tf))
        if hit is not None and hit[0] == key:
            return hit[1], hit[2], key
        bars_tf = XS.prepare_tf(trig, SC.core_table(trig, h4))
        self._tf_cache[(pair, tf)] = (key, trig, bars_tf)
        return trig, bars_tf, key

    def _kural_cikis(self, pair, tf, setup, side, trig, key, d0_ms: int) -> list:
        from trader_ml.ml1 import scan as SC
        rk = key + (setup, side)
        ts = self._rule_cache.get(rk)
        if ts is None:
            ts = SC.rule_exit_close_ms(trig, tf, setup, side)
            self._rule_cache[rk] = ts
        hz = HORIZON_GUN * 86400 * 1000
        return ts[np.searchsorted(ts, d0_ms, "left"):np.searchsorted(ts, d0_ms + hz, "right")].tolist()

    def _coz_cift(self, pair: str, D: datetime, items: list[dict], t0: datetime | None = None) -> int:
        from trader_ml.ml1 import exitsim as XS
        from trader_engine.strategies import arms as A
        Dt = pd.Timestamp(D)
        hazir = [c for c in items if pd.Timestamp(c["decision_ts"]) + M15 <= Dt]
        if not hazir:
            return 0
        dmin = min(pd.Timestamp(c["decision_ts"]) for c in hazir)
        b15 = self.view.bars(pair, "15m", D, int((Dt - dmin) / M15) + 8)
        if len(b15) == 0:
            self.sayac["veri_yok"] += 1
            return self._eski_kapat(hazir, D)
        try:
            fp = self.view.funding(pair, dmin.to_pydatetime(), D)
        except Exception:  # noqa: BLE001 - funding yoksa 0 sayilir (egitim hattiyla ayni)
            fp = []
        fdf = None
        if fp:
            fdf = pd.DataFrame({"funding_rate": [p.rate for p in fp]}, index=pd.DatetimeIndex([pd.Timestamp(p.ts) for p in fp]))
            if any(p.mark is not None for p in fp):
                fdf["mark"] = [np.nan if p.mark is None else p.mark for p in fp]
        tfs: dict[str, tuple] = {}
        rows, srcs = [], []
        for c in hazir:
            tf = c["tf"]
            if tf not in tfs:
                if t0 is not None and tfs and self._gecen_s(t0) >= self.butce_s:     # tf isinmasi da butceli: kalanlar sonraki adimda
                    self.sayac["budget_skips"] += 1
                    tfs[tf] = None
                    continue
                tfs[tf] = self._tf_bars(pair, tf, D, min(pd.Timestamp(x["decision_ts"]) for x in hazir if x["tf"] == tf))
            if tfs[tf] is None:
                continue
            trig, _, key = tfs[tf]
            row = {"decision_ts": pd.Timestamp(c["decision_ts"]), "pair": pair, "tf": tf, "setup": c["setup"], "side": c["side"],
                   "entry_ref": c["entry_ref"], "stop": c["stop"], "arm_id": c["arm_id"],
                   "target": float("nan") if c.get("target") is None else float(c["target"])}
            if A.exit_rule_of(c["setup"]) is not None:
                row["rule_exit_ts"] = self._kural_cikis(pair, tf, c["setup"], c["side"], trig, key,
                                                        int(pd.Timestamp(c["decision_ts"]).timestamp() * 1000))
            rows.append(row)
            srcs.append(c)
        if not rows:
            return 0
        B = XS.Bars15(b15)
        tfb = {tf: XS.TfBars(v[1], tf) for tf, v in tfs.items() if v is not None}
        Fd = XS.Funding(fdf, B)
        cfg = self._sim_config()
        n_yeni = 0
        for i in range(0, len(rows), CHUNK):                      # butce cift icinde de denetlenir (kalanlar sonraki adimda)
            if t0 is not None and i > 0 and self._gecen_s(t0) >= self.butce_s:
                self.sayac["budget_skips"] += 1
                break
            res = XS.simulate_rows(rows[i:i + CHUNK], B, tfb, Fd, cfg=cfg)
            for c, r in zip(srcs[i:i + CHUNK], res):
                n_yeni += self._sonuclandir(c, r, D)
        return n_yeni

    def _eski_kapat(self, items: list[dict], D: datetime) -> int:
        for c in items:
            if (pd.Timestamp(D) - pd.Timestamp(c["decision_ts"])) > pd.Timedelta(days=YAS_KAPAT_GUN):
                self._kapat(c, "veri_yok", D)
        return 0

    def _kapat(self, c: dict, neden: str, D: datetime) -> None:
        self._ekle(self._p(f"sonuclar-{_ay(D)}.jsonl"), [{"k": c["k"], "kapandi": neden}])
        self.kapali.add(c["k"])
        self.cands.pop(c["k"], None)
        self.sayac["kapandi_" + neden] += 1

    def _defter_r(self, c: dict) -> float | None:
        if self.ledger is None:
            return None
        try:
            d0 = pd.Timestamp(c["decision_ts"])
            for t in self.ledger.list_closed_trades(since=d0.to_pydatetime(), limit=200):
                if t.pair == c["pair"] and t.side == c["side"] and t.setup == c["setup"] and t.r_multiple is not None \
                        and d0 <= pd.Timestamp(t.entry_ts) <= d0 + pd.Timedelta(hours=1):
                    return float(t.r_multiple)
        except Exception:  # noqa: BLE001 - kontrol sayisi: en iyi gayret
            self.sayac["defter_r_hata"] += 1
        return None

    def _sonuclandir(self, c: dict, r: Mapping, D: datetime) -> int:
        st = r.get("status")
        if st == "open":
            return 0
        if st == "ok":
            if int(r.get("censored") or 0) == 1 or r.get("exit_reason") == "horizon":
                self._kapat(c, "horizon", D)
                return 0
            rn = r.get("net_R")
            if rn is None or not np.isfinite(rn) or r.get("exit_ts") is None:
                self._kapat(c, "invalid", D)
                return 0
            y = 1 if rn > 0 else 0
            alindi = c["k"] in self.alinan
            dr = self._defter_r(c) if alindi else None
            if dr is not None:
                self.uyusma["n"] += 1
                self.uyusma["uyusan"] += int((dr > 0) == (rn > 0))
            row = {"k": c["k"], "decision_ts": c["decision_ts"], "exit_ts": pd.Timestamp(int(r["exit_ts"]), unit="ms", tz="UTC").isoformat(),
                   "y": y, "r_net": float(rn), "exit_reason": r.get("exit_reason"), "tf": c["tf"], "pair": c["pair"], "side": c["side"],
                   "alindi": alindi, "defter_r": dr, "x": c["x"]}
            self._ekle(self._p(f"sonuclar-{_ay(D)}.jsonl"), [row])
            self.kapali.add(c["k"])
            self.cands.pop(c["k"], None)
            self._sn.append((c["k"], pd.Timestamp(c["decision_ts"]).as_unit("ns").value, float(y), c["pair"], c["side"], c["tf"],
                             np.array([np.nan if v is None else v for v in c["x"]], np.float32)))
            self._yeni_sonuc += 1
            self._yeni_alinan += int(alindi)
            self.bugun["sonuc"] += 1
            self.bugun["alinan" if alindi else "alinmayan"] += 1
            return 1
        # invalid / no_data / data_gap: veri gecikmesine karsi bir sure beklenir
        if (pd.Timestamp(D) - pd.Timestamp(c["decision_ts"])) >= pd.Timedelta(hours=BEKLE_SAAT):
            self._kapat(c, str(st), D)
        return 0

    def coz(self, D: datetime, acik_ciftler=()) -> int:
        """Bekleyen adaylari butceli (5 sn) simule eder. Doner: bu adimdaki yeni sonuc sayisi."""
        acik = set(acik_ciftler)
        kapanan = set() if self._onceki_acik is None else (self._onceki_acik - acik)
        self._onceki_acik = acik
        gruplar: dict[str, list[dict]] = {}
        for c in list(self.cands.values()):
            gruplar.setdefault(c["pair"], []).append(c)
        for k in [k for k in self._tf_cache if k[0] not in gruplar]:
            del self._tf_cache[k]
        sira = sorted(gruplar, key=lambda p: (p not in kapanan, self.imlec.get(p, ""), p))
        t0 = self.now_fn()
        n = 0
        for i, p in enumerate(sira):
            if self._gecen_s(t0) >= self.butce_s:
                self.sayac["budget_skips"] += len(sira) - i
                break
            try:
                n += self._coz_cift(p, D, gruplar[p], t0)
            except Exception as e:  # noqa: BLE001
                self.sayac["hata"] += 1
                log.warning("ML1 ogrenme cozme hatasi (%s): %r", p, e)
            self.imlec[p] = pd.Timestamp(D).isoformat()
        return n

    # ------------------------------------------------------------------ uydurma + yazim
    def _tampon(self) -> tuple[pd.DataFrame, np.ndarray]:
        d = pd.DataFrame({"k": [s[0] for s in self._sn], "decision_ts": pd.to_datetime([s[1] for s in self._sn], unit="ns", utc=True),
                          "y": [s[2] for s in self._sn], "pair": [s[3] for s in self._sn], "side": [s[4] for s in self._sn],
                          "tf": [s[5] for s in self._sn]})
        X = np.vstack([s[6] for s in self._sn]).astype(float) if self._sn else np.zeros((0, len(self.taban["feature_names"])))
        return d, X

    def _etkin_paket(self) -> dict:
        got, _ = M.load_package(self.paket_yolu)
        return got if got is not None else self.taban

    def _tampon_buda(self, simdi: datetime) -> None:
        sinir = (pd.Timestamp(simdi) - pd.Timedelta(days=PENCERE_GUN)).as_unit("ns").value
        self._sn = [s for s in self._sn if s[1] >= sinir]
        if len(self._sn) > MAKS_SATIR:
            self._sn = sorted(self._sn, key=lambda s: (s[1], s[0]))[-MAKS_SATIR:]

    def guncelle(self, D: datetime) -> dict:
        """Bir uydurma + denetim + (kuru degilse) yazim denemesi. Denetim kaydi satirini doner."""
        t0 = self.now_fn()
        self._tampon_buda(D)
        d, X = self._tampon()
        onceki = self._etkin_paket()
        r = uydur(self.taban, d, X, D, n0=self.n0, yari_omur_gun=self.yari_omur)
        self.n_etkin = r["n_etkin"]
        yeni = yeni_paket(self.taban, r["coef"], r["b"], surum=self.surum + 1, n_sonuc=r["n_sonuc"], n_etkin=r["n_etkin"], simdi=D)
        Xref = np.vstack(list(self.ref)) if len(self.ref) else None
        red, olc = denetle(self.taban, yeni, Xref)
        satir = {"ts": pd.Timestamp(D).isoformat(), "surum": self.surum + 1, "onceki_sha": str(onceki["sha256"])[:12],
                 "yeni_sha": str(yeni["sha256"])[:12], "yeni_sonuc": self._yeni_sonuc, "yeni_alinan": self._yeni_alinan,
                 "yeni_alinmayan": self._yeni_sonuc - self._yeni_alinan, "n_sonuc": r["n_sonuc"], "n_etkin": round(r["n_etkin"], 3),
                 "iter": r["iter"], "max_dcoef": r.get("max_dcoef"), "db": r.get("db"),
                 "gecme_taban": olc.get("gecme_taban"), "gecme_yeni": olc.get("gecme_yeni")}
        if Xref is not None and len(Xref) >= REF_MIN:
            try:
                satir["gecme_onceki"] = gecme_orani(onceki, Xref)[0]
            except Exception:  # noqa: BLE001
                pass
        if red is not None:
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
        satir["sure_ms"] = round(self._gecen_s(t0) * 1000.0, 1)
        self._yeni_sonuc = 0
        self._yeni_alinan = 0
        try:
            self._ekle(self._p("guncellemeler.jsonl"), [satir])
        except OSError as e:
            log.error("ML1 denetim kaydi yazilamadi: %r", e)
        return satir

    def _yaz(self, pkg: dict) -> None:
        """4.2: tmp'ye yaz + geri oku/dogrula; etkin paketi son_iyi'ye kopyala; os.replace. Hata = etkin paket degismez."""
        tmp = self.paket_yolu.with_name(self.paket_yolu.name + ".tmp")
        try:
            self.paket_yolu.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(pkg, sort_keys=True, indent=1), encoding="utf-8")
            got, why = M.load_package(tmp)
            if got is None:
                raise ValueError(f"geri okuma dogrulamasi basarisiz: {why}")
            cur, _ = M.load_package(self.paket_yolu)
            src = self.paket_yolu if cur is not None else self.tohum_yolu
            _atomik_yaz_bayt(self.son_iyi_yolu, src.read_bytes())
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
        son, _ = M.load_package(self.son_iyi_yolu)
        try:
            if son is not None:
                _atomik_yaz_bayt(self.paket_yolu, self.son_iyi_yolu.read_bytes())
            else:
                self.paket_yolu.unlink(missing_ok=True)          # kapi tohuma duser
        except OSError as e:
            log.critical("ML1 geri donus yazimi basarisiz: %r", e)
        self._imza = self._dosya_imza()
        self._izle = None
        self.duraklat_bitis = pd.Timestamp(D).to_pydatetime() + DURAKLAT
        self.bugun["geri_donus"] += 1
        self.sayac["geri_donus"] += 1
        self.son_geri_donus = {"ts": pd.Timestamp(D).isoformat(), "neden": neden, "son_iyi": son is not None}
        log.critical("ML1 ogrenme: SON IYI PAKETE DONULDU (%s); ogrenme 24 saat duraklatildi", neden)
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
            oran = ust / (ust + alt)
            if oran == 0 or oran > 0.8:
                return self.geri_don(D, f"gecme_orani:{oran:.2f}")
            self._izle = None

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
        out = {"sonuc": 0, "guncelleme": False}
        if not self.hazir:
            return out
        try:
            gun = pd.Timestamp(D).strftime("%Y-%m-%d")
            if self.bugun.get("tarih") != gun:
                self.bugun = {"tarih": gun, "sonuc": 0, "alinan": 0, "alinmayan": 0, "guncelleme": 0, "geri_donus": 0}
            self.izle(D)
            out["sonuc"] = self.coz(D, acik_ciftler)
            dur = self.duraklat_bitis is not None and pd.Timestamp(D) < pd.Timestamp(self.duraklat_bitis)
            if self._yeni_sonuc > 0 and not dur:
                self.guncelle(D)
                out["guncelleme"] = True
            self.temizle(D)
            self._durum_yaz(D)
        except Exception as e:  # noqa: BLE001
            self.sayac["hata"] += 1
            log.error("ML1 ogrenme adimi hatasi: %r", e, exc_info=True)
        return out
