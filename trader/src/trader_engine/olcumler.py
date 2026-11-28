"""Olcum kayit defteri (tek modul, tek cikti): "200/300 islemde bakilacak sorular" icin YALNIZ OLCEN kod. Karar vermez (tek istisna: `golge_gercek`
sonucunu ogrenici `agirlik_fn` ile okur ve sanal agirligi yalnizca DUSURUR). Kural dondurma: giris/cikis, tekilleştirme anahtari, model girdileri,
etiket bu modulden etkilenmez.

Cikti yeri TEK: `var/learner/olcum/ozet.json` (+ ham satirlar `satirlar-YYYY-MM.jsonl`, 14 ay). Belge: `docs/inceleme-200.md` (soru, olcum, ne zaman,
onceden yazilmis karar kurali); belge ile `KAYIT` birebir ayni olmak zorunda (`tests/test_olcum_kaydi.py`).
Her olcum `try/except` icindedir: hata motoru dusurmez, `ozet.json`'da o olcumun blogu `durum: "hata"` olur. Saat: yalniz enjekte edilen karar zamani `D`.

Olcum turleri:
  * `islem`: kapanan GERCEK islem basina bir satir (`fn(yon, islem, D) -> dict | None`; None = henuz cozulemedi, saatte bir yeniden denenir; kapanistan
    `VAZGEC_GUN` gun sonra `cozulemedi` yazilir), `ozet_fn(yon, satirlar)` ozet degerlerini uretir.
  * `ozet`: yalniz ozet hesaplar (`fn(yon, D) -> dict`).

Bilinen sinirlama (`iz_kadans`): 1 dk mum deposu 14 gun tutulur; daha uzun suren islemlerde 1 dk veri eksik kalir ve olcum `veri_eksik` yazar (yeniden denenmez).
"""
from __future__ import annotations

import json
import logging
import math
import re
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from trader_core import risk
from trader_core import signals as S

log = logging.getLogger("engine.olcumler")

ISLEM_BUTCE = 8                  # `islem` turu olcum basina adim basina en cok bu kadar islem denenir
VAZGEC_GUN = 35                  # kapanistan bu kadar gun sonra hala cozulemeyen islem `cozulemedi` yazilip birakilir
SATIR_TAVAN = 2000               # bellekte olcum basina tutulan en yeni satir
SAKLA_AY = 14
YENIDEN_DENE = pd.Timedelta(hours=1)
KIYAS_PENCERE = 500              # `golge_gercek` ozeti en yeni bu kadar cozulmus satirdan
_AD_RE = re.compile(r"^[a-z0-9_]+$")


# ----------------------------------------------------------------------------------------------------------- kayit
@dataclass(frozen=True)
class Olcum:
    ad: str
    soru: str
    bakis: str                    # "200" | "300" | "canli"
    tur: str                      # "islem" | "ozet"
    fn: Callable
    ozet_fn: Callable | None = None


KAYIT: dict[str, Olcum] = {}


def olcum(ad: str, *, soru: str, bakis: str, tur: str, ozet_fn: Callable | None = None):
    """Dekorator: olcumu `KAYIT`'a ekler. Ayni ad ikinci kez kaydedilirse ValueError."""
    if not _AD_RE.match(ad):
        raise ValueError(f"gecersiz olcum adi: {ad!r}")
    if bakis not in ("200", "300", "canli") or tur not in ("islem", "ozet"):
        raise ValueError(f"gecersiz bakis/tur: {bakis!r}/{tur!r}")

    def _kaydet(fn: Callable) -> Callable:
        if ad in KAYIT:
            raise ValueError(f"olcum zaten kayitli: {ad}")
        KAYIT[ad] = Olcum(ad, soru, bakis, tur, fn, ozet_fn)
        return fn
    return _kaydet


# ----------------------------------------------------------------------------------------------------------- yardimcilar
def _temiz(v: Any) -> Any:
    """JSON'a yazilabilir hale getirir: NaN/inf -> None, numpy/pandas skalerleri -> python."""
    if isinstance(v, dict):
        return {str(k): _temiz(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_temiz(x) for x in v]
    if isinstance(v, (pd.Timestamp, datetime)):
        return pd.Timestamp(v).isoformat()
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return f if math.isfinite(f) else None
    return v


def _ay(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m")


def _atomik_yaz(path: Path, data: bytes) -> None:
    from .ml1_ogren import _atomik_yaz_bayt
    _atomik_yaz_bayt(path, data)


def _ort(x: list[float]) -> float | None:
    return None if not x else float(sum(x) / len(x))


def _yuvarla(v: float | None, n: int = 6) -> float | None:
    return None if v is None or not math.isfinite(v) else round(float(v), n)


def _ogrenme_cfg(yon) -> Mapping:
    return ((yon.ml1_cfg or {}).get("ogrenme") or {})


# ----------------------------------------------------------------------------------------------------------- yonetici
class OlcumYonetici:
    def __init__(self, dizin, *, now_fn: Callable[[], datetime], ml1_cfg: Mapping | None = None, view=None, ledger=None, ogren=None,
                 maliyet_fn: Callable | None = None, kume_fn: Callable | None = None, trail_atr_fn: Callable[[], float | None] | None = None) -> None:
        self.dir = Path(dizin)
        self.now_fn = now_fn
        self.ml1_cfg: Mapping = ml1_cfg or {}
        self.view, self.ledger, self.ogren = view, ledger, ogren
        self.maliyet_fn, self.kume_fn, self.trail_atr_fn = maliyet_fn, kume_fn, trail_atr_fn
        self._ozet: dict = {"sema": 1, "guncellendi": None, "olcumler": {}}
        self._bitti: dict[str, set[int]] = {}
        self._satir: dict[str, deque] = {}
        self._son_deneme: dict[tuple[str, int], pd.Timestamp] = {}
        self._son_saat: dict[str, pd.Timestamp] = {}
        self._temizlik_gun: str | None = None
        self.hazir = False

    # ------------------------------------------------------------------ dosya
    def _p(self, ad: str) -> Path:
        return self.dir / ad

    def _aylar(self, simdi, n: int) -> list[str]:
        t = pd.Timestamp(simdi)
        return [(t - pd.DateOffset(months=i)).strftime("%Y-%m") for i in range(n)][::-1]

    def baslat(self, simdi: datetime | None = None) -> bool:
        """`ozet.json` ve son 14 ayin satir dosyalarindan bellegi kurar. Firlatmaz. Doner: hazir mi."""
        try:
            simdi = simdi or self.now_fn()
            self._bitti = {ad: set() for ad in KAYIT}
            self._satir = {ad: deque(maxlen=SATIR_TAVAN) for ad in KAYIT}
            try:
                d = json.loads(self._p("ozet.json").read_text(encoding="utf-8"))
                if isinstance(d, dict) and isinstance(d.get("olcumler"), dict):
                    self._ozet = {"sema": 1, "guncellendi": d.get("guncellendi"), "olcumler": d["olcumler"]}
            except (OSError, ValueError):
                pass
            for ay in self._aylar(simdi, SAKLA_AY):
                try:
                    with open(self._p(f"satirlar-{ay}.jsonl"), encoding="utf-8") as f:
                        for ln in f:
                            ln = ln.strip()
                            if not ln:
                                continue
                            try:
                                r = json.loads(ln)
                            except ValueError:
                                continue
                            ad = r.get("olcum")
                            if ad not in self._satir:
                                continue
                            self._satir[ad].append(r)
                            if r.get("trade_id") is not None:
                                self._bitti[ad].add(int(r["trade_id"]))
                except FileNotFoundError:
                    continue
            self.hazir = True
            return True
        except Exception as e:  # noqa: BLE001
            log.error("olcum baslatilamadi: %r", e, exc_info=True)
            return False

    def kaydet(self, ad: str, satir: dict, ts) -> None:
        """Ham olcum satiri ekler (`satirlar-YYYY-MM.jsonl`). `ad` kayitli degilse KeyError."""
        if ad not in KAYIT:
            raise KeyError(ad)
        kayit = _temiz({"olcum": ad, "ts": pd.Timestamp(ts).isoformat(), **satir})
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self._p(f"satirlar-{_ay(ts)}.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, separators=(",", ":"), allow_nan=False) + "\n")
        self._satir.setdefault(ad, deque(maxlen=SATIR_TAVAN)).append(kayit)
        if kayit.get("trade_id") is not None:
            self._bitti.setdefault(ad, set()).add(int(kayit["trade_id"]))

    def say(self, ad: str, anahtar: str, n: int = 1) -> None:
        """Olcume ait kalici sayac (TEK sayac yeri). Bir sonraki `ozet.json` yazimiyla diske gider. Firlatmaz."""
        try:
            sc = self._ozet.setdefault("olcumler", {}).setdefault(ad, {}).setdefault("sayac", {})
            sc[anahtar] = int(sc.get(anahtar, 0)) + int(n)
        except Exception:  # noqa: BLE001
            pass

    def sayac(self, ad: str) -> dict:
        return dict((self._ozet.get("olcumler", {}).get(ad) or {}).get("sayac") or {})

    def deger(self, ad: str) -> dict | None:
        """Olcumun son ozeti (`ozet.json`'daki blok). Karar veren kod yalniz bunu okur."""
        b = self._ozet.get("olcumler", {}).get(ad)
        return b if isinstance(b, dict) and b.get("guncellendi") else None

    def saatlik(self, ad: str, D) -> bool:
        """Pahalı `ozet` olcumleri icin: en cok saatte bir True doner (donerken zamani kaydeder)."""
        t = pd.Timestamp(D)
        son = self._son_saat.get(ad)
        if son is not None and pd.Timestamp(son) <= t < pd.Timestamp(son) + YENIDEN_DENE:
            return False
        self._son_saat[ad] = t
        return True

    # ------------------------------------------------------------------ adim
    def _gercek(self) -> dict[int, dict]:
        return getattr(self.ogren, "gercek", None) or {}

    def _islem_adim(self, o: Olcum, D: datetime) -> bool:
        """Doner: bu adimda bir islemde hata olustu mu."""
        bitti = self._bitti.setdefault(o.ad, set())
        t = pd.Timestamp(D)
        hata = False
        denendi = 0
        for tid, isl in sorted(self._gercek().items(), key=lambda kv: str(kv[1].get("exit_ts"))):
            if denendi >= ISLEM_BUTCE:
                break
            if tid in bitti:
                continue
            son = self._son_deneme.get((o.ad, tid))
            if son is not None and t - son < YENIDEN_DENE:
                continue
            self._son_deneme[(o.ad, tid)] = t
            denendi += 1
            try:
                sonuc = o.fn(self, isl, D)
            except Exception as e:  # noqa: BLE001
                hata = True
                self.say(o.ad, "hata")
                log.warning("olcum %s islem %s hatasi: %r", o.ad, tid, e)
                continue
            if isinstance(sonuc, dict):
                self.kaydet(o.ad, {"trade_id": int(tid), **sonuc}, D)
                self._son_deneme.pop((o.ad, tid), None)
            else:
                try:
                    yas = t - pd.Timestamp(isl.get("exit_ts"))
                except Exception:  # noqa: BLE001
                    yas = pd.Timedelta(0)
                if yas >= pd.Timedelta(days=VAZGEC_GUN):
                    self.kaydet(o.ad, {"trade_id": int(tid), "durum": "cozulemedi"}, D)
                    self._son_deneme.pop((o.ad, tid), None)
        return hata

    def adim(self, D: datetime) -> None:
        """Karar adimi sonunda bir kez. Firlatmaz."""
        if not self.hazir:
            return
        try:
            t = pd.Timestamp(D)
            eski = self._ozet.get("olcumler", {})
            yeni: dict[str, dict] = {}
            for ad, o in KAYIT.items():
                sayac = dict((eski.get(ad) or {}).get("sayac") or {})
                try:
                    hata_var = False
                    if o.tur == "islem":
                        hata_var = self._islem_adim(o, D)
                        satirlar = list(self._satir.get(ad, ()))
                        degerler = o.ozet_fn(self, satirlar) if o.ozet_fn is not None else {}
                        cozulmus = any("durum" not in r for r in satirlar)
                        varsayilan = "ok" if cozulmus else "veri_yok"
                    else:
                        degerler = o.fn(self, D)
                        varsayilan = "ok"
                    degerler = dict(degerler or {})
                    durum = degerler.pop("durum", None) or varsayilan
                    blok = {"durum": "hata" if hata_var else durum, "guncellendi": t.isoformat(), "soru": o.soru, "bakis": o.bakis, "sayac": self.sayac(ad) or sayac, **degerler}
                    if hata_var:
                        blok["hata"] = "islem_hatasi"
                except Exception as e:  # noqa: BLE001
                    self.say(ad, "hata")
                    log.warning("olcum %s hatasi: %r", ad, e)
                    blok = {"durum": "hata", "guncellendi": t.isoformat(), "soru": o.soru, "bakis": o.bakis, "sayac": self.sayac(ad) or sayac,
                            "hata": type(e).__name__}
                yeni[ad] = blok
            self._ozet = {"sema": 1, "guncellendi": t.isoformat(), "olcumler": yeni}
            try:
                _atomik_yaz(self._p("ozet.json"), json.dumps(_temiz(self._ozet), sort_keys=True, indent=1, allow_nan=False).encode("utf-8"))
            except Exception as e:  # noqa: BLE001
                log.error("olcum ozeti yazilamadi: %r", e)
            self._temizle(D)
        except Exception as e:  # noqa: BLE001
            log.error("olcum adimi hatasi: %r", e, exc_info=True)

    def _temizle(self, D) -> None:
        gun = pd.Timestamp(D).strftime("%Y-%m-%d")
        if self._temizlik_gun == gun:
            return
        self._temizlik_gun = gun
        tut = set(self._aylar(D, SAKLA_AY))
        for p in self.dir.glob("satirlar-????-??.jsonl"):
            if p.stem.split("-", 1)[1] not in tut:
                try:
                    p.unlink()
                except OSError:
                    pass


# ----------------------------------------------------------------------------------------------------------- ortak: eski kayit tamamlama
def _tamamla(islem: Mapping, yon) -> dict:
    """Eski alinan kayitlarda (skor/mod/time_stop/trail_atr alanlari yok) eksikleri turetir: mod/time_stop setup'tan, trail_atr = motorun guncel ayari."""
    rec = dict(islem)
    setup = rec.get("setup")
    if rec.get("mod") is None:
        from . import position_manager as PM
        rec["mod"] = PM.exit_mode_of(setup)
    if rec.get("mod") == "target" and rec.get("time_stop") is None:
        from .strategies import arms as AR
        rec["time_stop"] = AR.time_stop_of(setup, rec.get("tf"))
    if rec.get("trail_atr") is None and yon is not None and yon.trail_atr_fn is not None:
        try:
            v = yon.trail_atr_fn()
            rec["trail_atr"] = None if v is None else float(v)
        except Exception:  # noqa: BLE001
            rec["trail_atr"] = None
    rec.setdefault("skor", None)
    return rec


def _gecerli(rec: Mapping) -> bool:
    """Golge/karsi-olgu simulasyonu icin kayit uygun mu (kip, stop/giris referansi, iz kipinde trail_atr)."""
    try:
        if rec.get("mod") not in ("trail", "target"):
            return False
        stop, ref = float(rec["stop"]), float(rec["entry_ref"])
        if not (stop > 0 and ref > 0 and abs(ref - stop) > 0):
            return False
        if rec["mod"] == "trail":
            ta = rec.get("trail_atr")
            return isinstance(ta, (int, float)) and math.isfinite(ta) and ta > 0
        return True
    except (KeyError, TypeError, ValueError):
        return False


# ----------------------------------------------------------------------------------------------------------- P1-a: eksik dakika
@olcum("eksik_dakika_stop", soru="Eksik dakikalar ölçümü bozuyor mu?", bakis="200", tur="ozet")
def _eksik_dakika_stop(yon, D) -> dict:
    sc = yon.sayac("eksik_dakika_stop")
    out = {k: int(sc.get(k, 0)) for k in ("kontrol", "stop", "tasfiye", "veri_yok", "kapanmis", "stop_yok", "hata")}
    n = len(getattr(yon.ogren, "gercek", None) or {})
    out["stop_orani"] = out["stop"] / max(1, n)
    if not any(out[k] for k in ("kontrol", "stop", "tasfiye", "veri_yok", "kapanmis", "stop_yok", "hata")):
        out["durum"] = "veri_yok"
    return out


# ----------------------------------------------------------------------------------------------------------- P1-b: golge-gercek
def _golge_ozet(yon, satirlar: list[dict]) -> dict:
    og = _ogrenme_cfg(yon)
    min_n = int(og.get("kiyas_min_n", 30))
    isaret_min = float(og.get("kiyas_isaret_min", 0.85))
    dr_maks = float(og.get("kiyas_dr_maks", 0.30))
    dusuk = float(og.get("kiyas_dusuk_agirlik", 0.5))
    sanal_agirlik = float(og.get("sanal_agirlik", 1.0))
    coz = [r for r in satirlar if "durum" not in r and r.get("dr") is not None][-KIYAS_PENCERE:]
    n = len(coz)
    mdr = sorted(abs(float(r["dr"])) for r in coz)
    ort_mutlak = _ort(mdr)
    uyum = _ort([1.0 if r.get("y_sanal") == r.get("y_gercek") else 0.0 for r in coz])
    medyan = None if not mdr else float(np.median(mdr))
    ort_dr = _ort([float(r["dr"]) for r in coz])
    bitti = yon._bitti.get("golge_gercek", set())
    bekleyen = sum(1 for tid in (getattr(yon.ogren, "gercek", None) or {}) if tid not in bitti)
    dusur = bool(n >= min_n and ((round(uyum, 9) < isaret_min) or (round(ort_mutlak, 9) > dr_maks)))
    etkin = min(sanal_agirlik, dusuk) if dusur else sanal_agirlik
    return {"n": n, "ort_mutlak_dr": _yuvarla(ort_mutlak), "ort_dr": _yuvarla(ort_dr), "medyan_mutlak_dr": _yuvarla(medyan), "isaret_uyumu": _yuvarla(uyum),
            "bekleyen": bekleyen, "min_n": min_n, "isaret_min": isaret_min, "dr_maks": dr_maks, "agirlik_dusur": dusur, "sanal_agirlik_etkin": float(etkin)}


@olcum("golge_gercek", soru="Sanal (gölge) satırlar gerçek işlemle aynı sonucu veriyor mu?", bakis="200", tur="islem", ozet_fn=_golge_ozet)
def _golge_gercek(yon, islem: dict, D) -> dict | None:
    from . import ml1_sanal as SN
    rec = _tamamla(islem, yon)
    if not _gecerli(rec):
        return {"durum": "uygun_degil"}
    karar = pd.Timestamp(rec["decision_ts"]).to_pydatetime()
    b15, trig, fon = SN.veri_al(yon.view, rec, D, rec["mod"] == "trail")
    res = SN.simule(rec, b15, trig, yon.maliyet_fn(rec["pair"], karar), fon, D)
    if res is None:
        return None
    r_g = float(islem["r_net"])
    return {"k": rec.get("k"), "decision_ts": rec["decision_ts"], "tf": rec["tf"], "arm_id": rec.get("arm_id"), "r_gercek": r_g, "y_gercek": islem.get("y"),
            "neden_gercek": islem.get("exit_reason"), "r_sanal": float(res.r_net), "y_sanal": int(res.y), "neden_sanal": res.exit_reason,
            "kesildi": bool(res.kesildi), "dr": float(res.r_net) - r_g}


# ----------------------------------------------------------------------------------------------------------- P1-c: iz kadansi
_DK = pd.Timedelta(minutes=1)


def kadans_simule(rec: Mapping, b1: pd.DataFrame, trig: pd.DataFrame | None, mal, fonlama, kadans_dk: int) -> dict | None:
    """Karsi-olgu: ayni islem, iz suren stop / zaman cikisi `kadans_dk` dakikada bir (1/5/15) guncellenirse. Saf; `ml1_sanal.simule` ile ayni maliyet/giris/
    ucret/funding formulu. Doner {"r", "neden", "cikis_ts", "kesildi"}; veri bitmis ve ufuk dolmamissa None; 1 dk dizisinde delik varsa {"veri_eksik": True}.
    `b1`: karar D'den itibaren 1 dk `last` mumlari (open/high/low/close; UTC indeks, mum ACILIS zamani); `trig`: iz kipinde tf mumlari (high/low/close/atr_tf/regime)."""
    from . import ml1_sanal as SN
    from trader_core import arm_time as AT
    side = rec["side"]
    long = side == "long"
    sgn = 1.0 if long else -1.0
    D = pd.Timestamp(rec["decision_ts"])
    tfd = pd.Timedelta(AT.arm_tf_delta(rec["tf"]))
    mod, tl = rec["mod"], rec.get("time_stop")
    stop0 = float(rec["stop"])
    tgt = rec.get("target")
    tgt = None if tgt is None or not math.isfinite(float(tgt)) else float(tgt)
    if len(b1) == 0 or b1.index[0] != D:
        return None
    ufuk = pd.Timedelta(days=SN.MAKS_GUN)
    zs_ufuk = mod == "target" and tl is not None and tl * tfd < ufuk
    son = D + (tl * tfd if zs_ufuk else ufuk)
    idx = b1.index
    o, h, lo, c = (b1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    n = len(idx)
    ep = SN._slip(o[0], "buy" if long else "sell", mal.slip_entry_bps)
    risk_u = risk.loss_at_stop(1.0, float(rec["entry_ref"]), stop0, risk.LOCKED_CFG)
    if not risk_u > 0:
        return None
    xs = "sell" if long else "buy"
    R = abs(ep - stop0)
    tf_kapanis_ns = tf_atr = tf_reg = None
    if mod == "trail":
        if trig is None or len(trig) == 0:
            return None
        tf_kapanis_ns = (trig.index + tfd).as_unit("ns").asi8.tolist()
        tf_atr = trig["atr_tf"].to_numpy(float)
        tf_reg = trig["regime"].tolist()
        trail_atr = float(rec["trail_atr"])
    cur = stop0
    hh = -math.inf if long else math.inf
    bekleyen: str | None = None
    cikis: tuple[float, pd.Timestamp, str, bool] | None = None
    for i in range(n):
        b = idx[i]
        if i > 0 and b - idx[i - 1] != _DK:
            return {"veri_eksik": True}
        if bekleyen is not None:                                              # piyasa cikisi: bu mumun acilisi
            cikis = (SN._slip(o[i], xs, mal.slip_exit_bps), b, bekleyen, False)
            break
        if b >= son:
            break
        gap = (o[i] <= cur) if long else (o[i] >= cur)
        if (lo[i] <= cur) if long else (h[i] >= cur):                         # stop once
            base = o[i] if gap else cur
            cikis = (SN._slip(base, xs, mal.slip_stop_bps), b, "trail_stop" if cur != stop0 else "stop", False)
            break
        if mod == "target" and tgt is not None and ((h[i] >= tgt) if long else (lo[i] <= tgt)):
            base = o[i] if ((o[i] >= tgt) if long else (o[i] <= tgt)) else tgt
            base = min(base, h[i]) if long else max(base, lo[i])
            cikis = (SN._slip(base, xs, mal.slip_exit_bps), b, "target", False)
            break
        hh = max(hh, h[i]) if long else min(hh, lo[i])
        t = b + _DK                                                            # bu mumun kapanisi
        grid = (t.value // 60_000_000_000) % int(kadans_dk) == 0
        if mod == "trail":
            kk = bisect_right(tf_kapanis_ns, t.value) - 1                      # t'ye kadar KAPANMIS son tf mumu
            if kk >= 0:
                if tf_kapanis_ns[kk] == t.value and (t - D) % tfd == pd.Timedelta(0) and t > D and S.regime_flip_exit(side, tf_reg[kk]):
                    bekleyen = "regime_flip"                                   # rejim donusu: her kadansta yalniz tf kapanisinda
                elif grid and not np.isnan(tf_atr[kk]) and ((hh >= ep + S.TRAIL_START_R * R - S.EPS) if long else (hh <= ep - S.TRAIL_START_R * R + S.EPS)):
                    aday = hh - trail_atr * tf_atr[kk] if long else hh + trail_atr * tf_atr[kk]
                    if (aday > cur) if long else (aday < cur):
                        cur = aday                                             # yeni stop sonraki dakikadan gecerli
                        if (cur >= c[i]) if long else (cur <= c[i]):
                            bekleyen = "trail_stop"                            # aday kapanisi asti: sonraki dakika acilisinda piyasa cikisi
        elif grid and tl is not None and t - D >= tl * tfd:
            bekleyen = "time_stop"
        if bekleyen is not None and i + 1 >= n:
            return None                                                        # piyasa cikisi sonraki mumun acilisinda: henuz yok
    if cikis is None:
        if not (idx[-1] + _DK >= son):
            return None
        j = max(int((idx < son).sum()) - 1, 0)
        cikis = (SN._slip(c[j], xs, mal.slip_exit_bps), idx[j] + _DK, "kesildi", True)
    xp, xt, why, kes = cikis
    gross = sgn * (xp - ep)
    ucret = (ep + xp) * mal.taker_fee
    fund = 0.0
    for ts, rate, mark in fonlama:
        ts = pd.Timestamp(ts)
        if D < ts <= xt and ts.hour % 8 == 0 and ts.minute == 0:
            m = mark if mark is not None and math.isfinite(mark) and mark > 0 else ep
            p = m * rate
            fund += p if long else -p
    r = (gross - ucret - fund) / risk_u
    if not math.isfinite(r):
        return None
    return {"r": float(r), "neden": why, "cikis_ts": xt, "kesildi": bool(kes)}


def _iz_ozet_grup(rows: list[dict]) -> dict:
    n = len(rows)
    out: dict[str, Any] = {"n": n}
    for k in (1, 5, 15):
        out[f"ort_r_{k}"] = _yuvarla(_ort([float(r[f"r_{k}"]) for r in rows]))
        out[f"kazanma_{k}"] = _yuvarla(_ort([1.0 if float(r[f"r_{k}"]) > 0 else 0.0 for r in rows]))
    for ad, k in (("1_15", 1), ("5_15", 5)):
        d = [float(r[f"r_{k}"]) - float(r["r_15"]) for r in rows]
        out[f"fark_{ad}"] = _yuvarla(_ort(d))
        t = None
        if n >= 2:
            sd = float(np.std(d, ddof=1))
            if sd > 0:
                t = float(np.mean(d)) / (sd / math.sqrt(n))
        out[f"t_{ad}"] = _yuvarla(t)
    out["zaman_farki"] = sum(1 for r in rows if "time_stop" in (r.get("neden_1"), r.get("neden_5"), r.get("neden_15"))
                             and len({r.get("cikis_1"), r.get("cikis_5"), r.get("cikis_15")}) > 1)
    return out


def _iz_ozet(yon, satirlar: list[dict]) -> dict:
    coz = [r for r in satirlar if "durum" not in r and r.get("r_1") is not None]
    out = {"tumu": _iz_ozet_grup(coz), "veri_eksik": sum(1 for r in satirlar if r.get("durum") == "veri_eksik")}
    for m in ("trail", "target"):
        out[m] = _iz_ozet_grup([r for r in coz if r.get("mod") == m])
    return out


@olcum("iz_kadans", soru="İz süren stop ve zaman çıkışı 1/5/15 dk'da mı güncellenmeli?", bakis="300", tur="islem", ozet_fn=_iz_ozet)
def _iz_kadans(yon, islem: dict, D) -> dict | None:
    from . import ml1_sanal as SN
    rec = _tamamla(islem, yon)
    if not _gecerli(rec):
        return {"durum": "uygun_degil"}
    dec = pd.Timestamp(rec["decision_ts"])
    now = pd.Timestamp(D)
    cikis_g = pd.Timestamp(islem["exit_ts"])
    n = int((min(now - dec, pd.Timedelta(days=SN.MAKS_GUN + 1))) / _DK) + 2
    b1 = yon.view.bars(rec["pair"], "1m", now.to_pydatetime(), n)
    b1 = b1[b1.index >= dec]
    if len(b1) == 0 or b1.index[0] != dec:
        return {"durum": "veri_eksik"}
    ic = b1[b1.index < cikis_g]
    if len(ic) and (ic.index[-1] - dec) / _DK + 1 != len(ic):                  # gercek kapanisa dek 1 dk dizisinde delik
        return {"durum": "veri_eksik"}
    if b1.index[-1] + _DK < cikis_g:
        return None                                                            # veri henuz gercek kapanisa ulasmadi
    _, trig, fon = SN.veri_al(yon.view, rec, D, rec["mod"] == "trail")
    mal = yon.maliyet_fn(rec["pair"], dec.to_pydatetime())
    sonuc = {k: kadans_simule(rec, b1, trig, mal, fon, k) for k in (1, 5, 15)}
    if any(s is not None and s.get("veri_eksik") for s in sonuc.values()):
        return {"durum": "veri_eksik"}
    if any(s is None for s in sonuc.values()):
        return None
    out = {"k": rec.get("k"), "tf": rec["tf"], "arm_id": rec.get("arm_id"), "mod": rec["mod"], "r_gercek": float(islem["r_net"])}
    for k, s in sonuc.items():
        out[f"r_{k}"], out[f"neden_{k}"], out[f"cikis_{k}"] = s["r"], s["neden"], s["cikis_ts"]
    return out
