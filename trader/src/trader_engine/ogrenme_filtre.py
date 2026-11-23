"""ML filtresi (kagit, AKTIF; 19.11 kullanici karari): `ortak_ogrenme.filtre` paketini kagit giris kapisina baglar.

Sinir (kod duzeyinde): filtre yalniz bir YENI girisi atlatabilir (`ml_filter`). Boyut, kaldirac, risk, limit, stop/hedef ve
kapi zincirine dokunamaz; yeni islem actiramaz (kapi: gates.EntryGate.decide, risk kontrolunden ONCE yalniz "hayir" der).
Hata/eksik/bozuk/suresi gecmis paket ya da kurulumun kapanmis islemi < MIN_ISLEM => o kurulum icin filtre YOK, giris serbest
(fail-open; `ml_no_model` YAZILMAZ). `TRADER_OGRENME_FILTRE_KAPALI=1` filtreyi tamamen kapatir. Yalniz kagit; testnet/canli yolu
degismez (orada ML kapisi/gecis kapisi eskisi gibi).

AILE (kurulum ailesi, 20.11): model kol (arm_id = `<kurulum>@<tf>`) basina DEGIL, AILE basina: ayni kurulumun tum zaman dilimleri
(M1@15m, M1@1h, M1@4h, M1@1d -> aile `M1`) tek havuzda. Ailenin TOPLAM kapanmis islemi >= MIN_ISLEM olunca havuzlanmis islemlerle tek model
egitilir ve ailenin HER koluna uygulanir (tek tek kolun 10 islemi gerekmez). Zaman dilimi modelin ozelligidir: `tf_log2_dk`
(log2 dakika) + `tf_15m/tf_1h/tf_4h/tf_1d` (one-hot). T1 ve R1 AYRI ailelerdir (farkli `f_*` ozellik kumeleri; havuzlanmaz).
Paket kimligi `aile:<kurulum>` (dosya `aile_<kurulum>.json`). Eski kol-basina paketler (`<kurulum>@<tf>.json`) kullanilmaz; gece
egitiminde `eski_kol/` alt dizinine tasinir (geri alinabilir, taranmaz). Durum dosyasi anahtarlari da aile bazli (eski kol anahtarlari atilir).

Egitim (gece birimi `scripts/ml_retrain_run.py`, 03:10 UTC): kagit defterinden aile basina, >= MIN_ISLEM kapanmis islemle (kollar toplami);
her YENIDEN_ISLEM yeni kapanan (havuz) islemde ya da paket YENIDEN_GUN gunu astiginda yeniden. Kilitli donem (HOLDOUT) satirlari
egitimden dusurulur. YAYIN ONCESI SINAMA (23.11): egitim sonrasi paket, zaman olarak sonraki %30'luk (en az 5 ornek) dilimde sinanir
(SINAMA_*; `aile_sinama`): suzgecin kabul ettikleri hepsinden iyi ve >= 3 kabul degilse paket YAYINLANMAZ, eski paket de geri cekilir =>
o aile icin suzgec KAPALI (kagit: giris serbest; canlida `ml_mode=active` fail-closed degismez). COUNTERFACTUAL: reddedilen sinyallerin
'alinsaydi' R'si de egitim/sinama ornegi (bkz `adaylar_defterden`). Paketler `<defter dizini>/models/ortak_filtre/aile_<kurulum>.json`.
"""
from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from trader_core.ml_live_v2 import setup_feature_dict

from .holdout import HOLDOUT

log = logging.getLogger("engine.ogrenme_filtre")

MIN_ISLEM = 10             # kurulum basina asgari kapanmis islem (1L3A ile ayni, 2026-11-19)
YENIDEN_ISLEM = 10         # her 10 yeni kapanan islemde yeniden egit
YENIDEN_GUN = 20           # paket omru 21 gun: bir gun erken yenile (bosluk kalmasin)
# Yayin oncesi ileri sinama (23.11 kullanici karari 3 (c)): aile paketi, gorulmemis (zaman olarak SONRAKI) veride sinanmadan yayina girmez.
SINAMA_ORAN = 0.30         # ornekler kapanis zamanina gore siralanir; son %30'u sinama dilimi
SINAMA_MIN_ORNEK = 5       # sinama dilimi en az 5 ornek
SINAMA_MIN_KABUL = 3       # sinama diliminde suzgecin KABUL ettigi en az 3 ornek
ENV_KAPALI = "TRADER_OGRENME_FILTRE_KAPALI"
MODEL_ALT = ("models", "ortak_filtre")
DURUM_DOSYASI = "ogrenme_filtre_durum.json"
AILE_ON_EK = "aile:"
ESKI_ALT = "eski_kol"
TF_DAKIKA = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}   # trader_core.arm_time.ARM_TF_SECONDS / 60


def aile_of(arm: str | None) -> str | None:
    """`M1@15m` -> `M1`. Kurulum/tf eksik (`?`) ya da bicim bozuksa None (o kol icin filtre YOK)."""
    if not arm or "@" not in str(arm):
        return None
    kur, _, tf = str(arm).partition("@")
    if not kur or kur == "?" or tf not in TF_DAKIKA:
        return None
    return kur


def tf_of(arm: str | None) -> str | None:
    if not arm or "@" not in str(arm):
        return None
    tf = str(arm).partition("@")[2]
    return tf if tf in TF_DAKIKA else None


def aile_kimligi(aile: str) -> str:
    return AILE_ON_EK + aile


def tf_ozellikleri(tf: str) -> dict[str, float]:
    """Zaman dilimi ozellikleri (egitim ve giris AYNI islevi kullanir): log2(dakika) + one-hot."""
    d = {"tf_log2_dk": math.log2(TF_DAKIKA[tf])}
    for k in TF_DAKIKA:
        d[f"tf_{k}"] = 1.0 if k == tf else 0.0
    return d


def paket_modulleri():
    """(filtre, kayit) ya da None (paket/numpy yok => filtre YOK)."""
    try:
        from ortak_ogrenme import filtre, kayit
        return filtre, kayit
    except ImportError:
        return None


def model_dizini(ledger_path: str | os.PathLike) -> Path:
    return Path(ledger_path).parent.joinpath(*MODEL_ALT)


def model_dizini_cfg(cfg) -> Path:
    """Giris kapisinin model dizini. Kagit: kendi defterinin yani. Canli (23.11 kullanici karari: canli = kagit): modeli HICBIR sey
    `var-live` altina yazmaz; kagidin dizini (`<var_dir ust dizini>/var/<bot>/models/ortak_filtre`) YALNIZ OKUNUR. Eksik paket => fail-open."""
    if getattr(cfg, "mode", None) == "live":
        return Path(cfg.var_dir).parent.joinpath("var", cfg.bot, *MODEL_ALT)
    return model_dizini(cfg.ledger_path)


def kapali(env: Mapping[str, str] | None = None) -> bool:
    return (os.environ if env is None else env).get(ENV_KAPALI) == "1"


def ozellikler(*, side, regime, atr_ratio, session_tag, pair, planned_entry, planned_stop, planned_target=None,
               rh_touches=0, rl_touches=0, features: Mapping | None = None) -> dict[str, float]:
    """Karar anindaki sayisal ozellikler (egitim ve giris AYNI islevi kullanir). Sonlu olmayanlar atilir (filtre `fill` kullanir)."""
    d = setup_feature_dict(side=side, regime=regime, atr_ratio=atr_ratio, session_tag=session_tag, asset_class=None, pair=pair,
                           planned_entry=planned_entry, planned_stop=planned_stop, planned_target=planned_target,
                           rh_touches=rh_touches, rl_touches=rl_touches, features=features)
    return {k: float(v) for k, v in d.items() if isinstance(v, (int, float)) and math.isfinite(v)}


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class Karar:
    izin: bool
    puan: float | None
    neden: str          # ok | esik_alti | filtre_yok | hata


class FiltreDeposu:
    """Kurulum (arm_id) basina paket onbellegi + puanlama. Her yol hata -> izin True (fail-open)."""

    def __init__(self, klasor: str | os.PathLike, *, kapali_: bool | None = None) -> None:
        self.klasor = Path(klasor)
        self.kapali = kapali() if kapali_ is None else kapali_
        self._mod = None if self.kapali else paket_modulleri()
        self._onbellek: dict[str, tuple[tuple, dict | None]] = {}
        self._uyarilan: set[str] = set()

    @property
    def calisiyor(self) -> bool:
        return self._mod is not None

    def _yol(self, kimlik: str) -> Path:
        return self.klasor / f"{self._mod[0]._guvenli_ad(kimlik)}.json"

    def paket(self, arm: str, simdi: datetime) -> dict | None:
        """Kolun AILE paketi (gecerli: hash + sure + n_egitim >= MIN_ISLEM) ya da None. `arm` = kol kimligi (`M1@15m`)."""
        aile = aile_of(arm)
        return None if aile is None else self._aile_paketi(aile, simdi)

    def _aile_paketi(self, aile: str, simdi: datetime) -> dict | None:
        if self._mod is None:
            return None
        arm = aile_kimligi(aile)
        filtre = self._mod[0]
        try:
            yol = self._yol(arm)
            st = yol.stat()
        except (OSError, ValueError):
            self._onbellek.pop(arm, None)
            return None
        sig = (st.st_mtime_ns, st.st_size)
        ent = self._onbellek.get(arm)
        if ent is None or ent[0] != sig:
            try:
                p = filtre.yukle(yol, sure_kontrol=False)
                if int(p["meta"].get("n_egitim", 0)) < MIN_ISLEM:
                    p = None
            except Exception as e:  # noqa: BLE001 - bozuk paket: filtre YOK
                if arm not in self._uyarilan:
                    self._uyarilan.add(arm)
                    log.warning("ML filtre paketi gecersiz (%s), filtre YOK: %s", arm, e)
                p = None
            ent = (sig, p)
            self._onbellek[arm] = ent
        p = ent[1]
        if p is None:
            return None
        try:
            if _utc(simdi) >= _utc(datetime.fromisoformat(p["meta"]["son_kullanma"])):
                return None                                          # suresi gecmis: filtre YOK
        except Exception:  # noqa: BLE001
            return None
        return p

    def karar(self, arm: str, oz: Mapping[str, float], simdi: datetime) -> Karar:
        """Yalniz bir girisi atlatabilir. Esik alti puan => izin False; baska her durum => izin True."""
        if self._mod is None:
            return Karar(True, None, "filtre_yok")
        try:
            p = self.paket(arm, simdi)
            if p is None:
                return Karar(True, None, "filtre_yok")
            oz = {**oz, **tf_ozellikleri(tf_of(arm))}                # aile modeli: kolun zaman dilimi ozellik olarak eklenir
            puan = float(self._mod[0].puan(p, oz))
            if not math.isfinite(puan) or not 0.0 <= puan <= 1.0:
                return Karar(True, None, "hata")
            return Karar(puan >= float(p["esik"]), puan, "ok" if puan >= float(p["esik"]) else "esik_alti")
        except Exception as e:  # noqa: BLE001 - filtre hatasi asla motoru durdurmaz, girisi engellemez
            log.warning("ML filtre hatasi (%s), giris serbest: %s: %s", arm, type(e).__name__, e)
            return Karar(True, None, "hata")

    def saglik(self, simdi: datetime, aileler) -> tuple[str, str | None, datetime | None]:
        """Canli saglik (status.json ml -> health): (durum, hata, en erken son_kullanma). durum: ok | no_model | expired.
        ok: istenen ailelerden en az biri gecerli ve suresi dolmamis paket tasiyor. Salt okunur."""
        if self._mod is None:
            return "no_model", "ogrenme_filtre paketi yok ya da filtre kapali", None
        if not self.klasor.is_dir():
            return "no_model", f"model dizini yok/okunamiyor: {self.klasor}", None
        exp: list[datetime] = []
        var = False
        for a in sorted(set(aileler)):
            try:
                var = var or self._yol(aile_kimligi(a)).exists()
            except (OSError, ValueError):
                pass
            p = self._aile_paketi(a, simdi)
            if p is not None:
                try:
                    exp.append(_utc(datetime.fromisoformat(p["meta"]["son_kullanma"])))
                except Exception:  # noqa: BLE001
                    pass
        if exp:
            return "ok", None, min(exp)
        if var:
            return "expired", "paketler gecersiz/suresi dolmus/bozuk", None
        return "no_model", "gecerli aile paketi yok", None

    def aktif_kurulumlar(self, simdi: datetime) -> list[str]:
        """Aktif AILE paketlerinin kimlikleri (`aile:M1`...). Eski kol paketleri sayilmaz."""
        if self._mod is None or not self.klasor.is_dir():
            return []
        out = []
        for p in sorted(self.klasor.glob("*.json")):
            if p.name.endswith(".prev.json") or p.name.startswith("."):
                continue
            try:
                arm = json.loads(p.read_text(encoding="utf-8"))["meta"]["kurulum"]
            except Exception:  # noqa: BLE001
                continue
            if not str(arm).startswith(AILE_ON_EK):
                continue
            if self._aile_paketi(str(arm)[len(AILE_ON_EK):], simdi) is not None:
                out.append(str(arm))
        return out

    def aktif_aileler(self, simdi: datetime) -> list[str]:
        return [k[len(AILE_ON_EK):] for k in self.aktif_kurulumlar(simdi)]

    def aktif_kol_sayisi(self, simdi: datetime) -> int:
        """Filtrenin kapsadigi kol sayisi (aktif aile x zaman dilimi)."""
        return len(self.aktif_aileler(simdi)) * len(TF_DAKIKA)


# ---------------------------------------------------------------------------------------------- egitim (gece birimi)
def _kilit_kesisir(ts: datetime, bitis: datetime | None) -> bool:
    b, e = HOLDOUT
    son = ts if bitis is None or bitis < ts else bitis
    return ts < e and son >= b


def _oz_karar(d) -> dict[str, float]:
    return ozellikler(side=d.side, regime=d.regime, atr_ratio=d.atr_ratio, session_tag=d.session_tag, pair=d.pair,
                      planned_entry=d.planned_entry, planned_stop=d.planned_stop, planned_target=d.planned_target,
                      rh_touches=d.rh_touches, rl_touches=d.rl_touches, features=d.features)


def adaylar_defterden(led, cf_satirlari=None, simdi: datetime | None = None) -> list:
    """Kapanmis kagit islemleri (+ varsa counterfactual) -> ortak_ogrenme Aday listesi (alindi=True, r = net R). Kilitle kesisen dusurulur.
    ts = karar mumunun kapanisi; ozellikler = karar anindaki ozellikler (girisle AYNI islev); cikis.kapanis = sonucun kesinlestigi an.

    COUNTERFACTUAL (23.11 kullanici karari 4): `cf_satirlari` (counterfactual.sqlite `cf_outcomes` barrier satirlari: {decision_id, hyp_r_net, window_end_ts: datetime}; okuma
    `scripts/ml_retrain_run.cf_satirlari_oku`, motor core.counterfactual'e bagimli olmasin diye) verilirse suzgecin/kapilarin REDDETTIGI sinyallerin
    'alinsaydi' net R'si (method=barrier, `hyp_r_net`) de egitim ornegi olur; `trader_ml.setup_filter.train.collect_rows` ile ayni kaynak.
    Sizinti onlemi: yalniz karar anindan SONRA kesinlesmis (window_end > karar) ve kesim `simdi`den ONCE kapanmis (window_end <= simdi)
    sonuclar; kilit donemiyle kesisenler dusurulur. Ayni karar iki kez sayilmaz: kapanmis islemi olan karar icin counterfactual atlanir.
    Counterfactual ornekler egitim icin `alindi=True` isaretlenir (paket yalniz alindi orneklerle egitir), `etiketler=("counterfactual",)`."""
    mod = paket_modulleri()
    if mod is None:
        return []
    Aday = mod[1].Aday
    kesim = _utc(simdi or datetime.now(timezone.utc))
    dec = {d.id: d for d in led.list_decisions()}
    out = []
    trade_karar: set[int] = set()
    for t in led.list_closed_trades(limit=led.LIST_CLOSED_MAX):
        trade_karar.add(t.decision_id)
        d = dec.get(t.decision_id)
        if d is None or t.r_multiple is None or not d.arm_id or not math.isfinite(float(t.r_multiple)):
            continue
        ts = _utc(d.bar_close_ts)
        bitis = None if t.exit_ts is None else _utc(t.exit_ts)
        if _kilit_kesisir(ts, bitis):
            continue
        out.append(Aday(id=str(t.trade_id), proje="ML", kurulum=d.arm_id, enstruman=d.pair, varlik_sinifi="kripto",
                        yon=d.side, ts=ts, alindi=True, r=float(t.r_multiple), rejim=d.regime, ozellikler=_oz_karar(d),
                        cikis={"kaynak": "islem", "kapanis": (bitis or ts).isoformat()}))
    if cf_satirlari:
        out.extend(_cf_adaylari(dec, trade_karar, cf_satirlari, kesim, Aday))
    return out


def _cf_adaylari(dec, trade_karar: set, satirlar, kesim: datetime, Aday) -> list:
    out = []
    for r in satirlar:
        did = int(r["decision_id"])
        d = dec.get(did)
        if d is None or did in trade_karar or not d.arm_id:        # alinmis karar: counterfactual SAYILMAZ (cift sayim yok)
            continue
        try:
            r_net = float(r["hyp_r_net"])
            bitis = r["window_end_ts"]
            ts = _utc(d.bar_close_ts)
            bitis = None if bitis is None else _utc(bitis)
        except (TypeError, ValueError, AttributeError):
            continue
        if bitis is None or not math.isfinite(r_net):
            continue
        if bitis <= ts or bitis > kesim or _kilit_kesisir(ts, bitis):   # karardan sonra kesinlesmeli, kesimden once kapanmali, kilit disi
            continue
        out.append(Aday(id=f"cf{did}", proje="ML", kurulum=d.arm_id, enstruman=d.pair, varlik_sinifi="kripto", yon=d.side, ts=ts,
                        alindi=True, r=r_net, rejim=d.regime, ozellikler=_oz_karar(d), etiketler=("counterfactual",),
                        cikis={"kaynak": "counterfactual", "kapanis": bitis.isoformat(), "karar_id": did}))
    return out


def _eski_kol_paketlerini_ayir(klasor: Path) -> int:
    """Eski kol-basina paketleri (`@` iceren ad) `eski_kol/` altina tasir (silmez); taramalar yalniz ust dizine bakar."""
    n = 0
    if not klasor.is_dir():
        return 0
    for p in sorted(klasor.glob("*@*.json")):
        try:
            hedef = klasor / ESKI_ALT
            hedef.mkdir(exist_ok=True)
            os.replace(p, hedef / p.name)
            n += 1
        except OSError as e:
            log.warning("eski kol paketi tasinamadi (%s): %s", p.name, e)
    return n


def aile_adaylari(adaylar) -> dict[str, list]:
    """Kol adaylarini aile bazinda havuzlar: kurulum -> `aile:<kurulum>`, ozelliklere zaman dilimi eklenir. Tanimsiz kol atlanir."""
    import dataclasses
    by: dict[str, list] = {}
    for a in adaylar:
        aile, tf = aile_of(a.kurulum), tf_of(a.kurulum)
        if aile is None or tf is None:
            continue
        by.setdefault(aile, []).append(dataclasses.replace(a, kurulum=aile_kimligi(aile),
                                                           ozellikler={**a.ozellikler, **tf_ozellikleri(tf)},
                                                           cikis={**a.cikis, "kol": a.kurulum}))
    return by


def _kapanis(a) -> datetime:
    try:
        return _utc(datetime.fromisoformat(str(a.cikis["kapanis"])))
    except (KeyError, ValueError, TypeError):
        return _utc(a.ts)


def aile_sinama(filtre, kimlik: str, adaylar, simdi: datetime) -> dict:
    """Yayin oncesi zaman-siralı ileri sinama (deterministik). Ornekler kapanis zamanina gore siralanir; son
    max(SINAMA_MIN_ORNEK, ceil(SINAMA_ORAN*n)) ornek sinama dilimi. PURGE: sinama diliminin ILK kararindan once kapanmamis egitim ornekleri
    atilir (etiketi o anda bilinmiyordu; embargo = etiket ufku). Egitim diliminde egitilir; sinamada suzgecin KABUL ettiklerinin ort. R'si
    > hepsinin ort. R'si VE kabul >= SINAMA_MIN_KABUL ise `gecti`. Egitilemezse (veri/tek sinif) ya da dilim kucukse `sinanamadi`
    (gecmemis sayilir: paket yayinlanmaz). Donus: {karar, n_egitim, n_sinama, n_kabul, ort_r_hepsi, ort_r_kabul, neden}."""
    kilit = [HOLDOUT]
    ornek = [a for a in adaylar if a.kurulum == kimlik and a.alindi and a.r is not None and not filtre._kilitte(_utc(a.ts), kilit)]
    ornek.sort(key=lambda a: (_kapanis(a), _utc(a.ts), str(a.id)))
    n = len(ornek)
    rap = {"karar": "sinanamadi", "n_egitim": 0, "n_sinama": 0, "n_kabul": 0, "ort_r_hepsi": None, "ort_r_kabul": None, "neden": None}
    k = max(SINAMA_MIN_ORNEK, math.ceil(SINAMA_ORAN * n))
    if k >= n:
        rap["neden"] = "ornek_az"
        return rap
    sinama = ornek[-k:]
    ilk = min(_utc(a.ts) for a in sinama)
    egitim = [a for a in ornek[:-k] if _kapanis(a) < ilk]
    rap["n_egitim"], rap["n_sinama"] = len(egitim), len(sinama)
    paket = filtre.egit(kimlik, egitim, olusturma=simdi, kilit=kilit)
    if paket is None:
        rap["neden"] = "egitilemedi"
        return rap
    rs = [float(a.r) for a in sinama]
    kabul = [float(a.r) for a in sinama if filtre.puan(paket, a.ozellikler) >= float(paket["esik"])]
    rap["n_kabul"] = len(kabul)
    rap["ort_r_hepsi"] = sum(rs) / len(rs)
    rap["ort_r_kabul"] = (sum(kabul) / len(kabul)) if kabul else None
    ok = len(kabul) >= SINAMA_MIN_KABUL and rap["ort_r_kabul"] > rap["ort_r_hepsi"]
    rap["karar"] = "gecti" if ok else "kaldi"
    return rap


def egit_hepsi(adaylar, klasor: str | os.PathLike, simdi: datetime, *, durum_yolu: str | os.PathLike | None = None,
               kollar=None) -> dict:
    """AILE basina (kollar toplami >= MIN_ISLEM kapanmis islem) yeniden egitim kurali: son egitimden bu yana >= YENIDEN_ISLEM yeni
    islem ya da >= YENIDEN_GUN gun. Holdout satirlari `adaylar_defterden`de dusuruldu; `egit` kilit aralikla ayrica dusurur.
    Donus: {"durum", "aileler": {aile: {n, kollar:{arm:n}, durum, model_hash?}}, "eski_tasinan"}."""
    mod = paket_modulleri()
    if mod is None:
        return {"durum": "paket_yok"}
    filtre = mod[0]
    simdi = _utc(simdi)
    dy = Path(durum_yolu) if durum_yolu else Path(klasor) / DURUM_DOSYASI
    try:
        durum = json.loads(dy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        durum = {}
    if not isinstance(durum, dict):
        durum = {}
    durum = {k: v for k, v in durum.items() if str(k).startswith(AILE_ON_EK)}   # eski kol anahtarlari atilir
    eski = _eski_kol_paketlerini_ayir(Path(klasor))
    kilit = [HOLDOUT]
    if kollar is not None:                                    # yapilandirmadaki kollar disindaki (kaldirilmis) kol aile/paket uretmez
        izinli = set(kollar)
        adaylar = [a for a in adaylar if a.kurulum in izinli]
    by = aile_adaylari(adaylar)
    rapor: dict[str, dict] = {}
    for aile in sorted(by):
        kimlik = aile_kimligi(aile)
        kollar: dict[str, int] = {}
        for a in by[aile]:
            if a.r is not None:
                kol = a.cikis.get("kol", "?")
                kollar[kol] = kollar.get(kol, 0) + 1
        n = sum(kollar.values())
        son = durum.get(kimlik) if isinstance(durum.get(kimlik), dict) else None
        if n < MIN_ISLEM:
            rapor[aile] = {"n": n, "kollar": kollar, "durum": "az_islem"}
            continue
        if son is not None:
            try:
                gun = (simdi - _utc(datetime.fromisoformat(son["zaman"]))).days
            except Exception:  # noqa: BLE001
                gun = YENIDEN_GUN
            if n - int(son.get("n", 0)) < YENIDEN_ISLEM and gun < YENIDEN_GUN:
                rapor[aile] = {"n": n, "kollar": kollar, "durum": "guncel"}
                continue
        try:
            yol = Path(klasor) / f"{filtre._guvenli_ad(kimlik)}.json"
            sin = aile_sinama(filtre, kimlik, by[aile], simdi)
            log.info("ML filtre sinamasi aile=%s n_egitim=%s n_sinama=%s ort_r_hepsi=%s ort_r_kabul=%s n_kabul=%s karar=%s", aile,
                     sin["n_egitim"], sin["n_sinama"], sin["ort_r_hepsi"], sin["ort_r_kabul"], sin["n_kabul"], sin["karar"])
            if sin["karar"] != "gecti":
                if yol.exists():
                    yol.unlink()                              # sinamayi gecemedi: eski/bayat paket de geri cekilir => filtre KAPALI
                durum[kimlik] = {"zaman": simdi.isoformat(), "n": n, "model": False, "sinama": sin}
                rapor[aile] = {"n": n, "kollar": kollar, "durum": "sinama_" + sin["karar"], "sinama": sin}
                continue
            paket = filtre.egit(kimlik, by[aile], olusturma=simdi, kilit=kilit)   # gecti: TUM veriyle yeniden egit
            if paket is not None:
                filtre.kaydet(paket, klasor)
            elif yol.exists():
                yol.unlink()                                  # tek sinif: eski model de gecersiz => filtre YOK
            durum[kimlik] = {"zaman": simdi.isoformat(), "n": n, "model": paket is not None, "sinama": sin}
            rapor[aile] = {"n": n, "kollar": kollar, "durum": "ok" if paket is not None else "tek_sinif", "sinama": sin}
            if paket is not None:
                rapor[aile]["model_hash"] = paket["meta"]["model_hash"]
        except Exception as e:  # noqa: BLE001 - bir ailenin hatasi digerini ve gece birimini durdurmaz
            log.warning("ML filtre egitimi basarisiz (%s): %s: %s", aile, type(e).__name__, e)
            rapor[aile] = {"n": n, "kollar": kollar, "durum": "hata"}
    try:
        Path(klasor).mkdir(parents=True, exist_ok=True)
        tmp = dy.with_name(f".{dy.name}.tmp")
        tmp.write_text(json.dumps(durum, sort_keys=True), encoding="utf-8")
        os.replace(tmp, dy)
    except OSError as e:
        log.warning("ML filtre durumu yazilamadi: %s", e)
    return {"durum": "ok", "aileler": rapor, "eski_tasinan": eski}
