"""24.11 kullanici karari: formasyon kutuphanesi ortak altyapisi (kurulum dosyasi DEGIL; `_` onekli, `discover` yok sayar).

Kutuphane dosyasi (`mf1.py`) `SETUP` (aile), `PRIORITY` (taban), `TIMEFRAMES` ve `FORMASYONLAR = {kod: Formasyon}` verir;
`discover` her formasyonu sanal kurulum (`MF1-YUTAN`) olarak kaydeder: tavan, karantina, kol kucultme, `arm_conflict`,
alinsaydi ve ogrenme kayitlari boylece formasyon x zaman dilimi bazinda calisir.

Kurallar: karar yalniz kapanmis son mumda (`t`); `planned_entry = c[t]`; short, long'un fiyat aynasi (o,h,l,c -> -o,-l,-h,-c);
ayni mumda iki yon cikarsa aday yok. Kitap kurallari sabittir: hicbir ders parametresi (`inp.params.*`) okunmaz.
Dedektorler yalniz `t` ve oncesini okur (ileriye bakis yok). Stop mesafesi girisin %0,6'sindan kucukse ya da yanlis taraftaysa
`stop_width`; hedef yanlis taraftaysa `rr_below_min` (sema yalniz bu iki elenme nedenini kabul eder)."""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from types import SimpleNamespace
from typing import Callable

import numpy as np

from trader_core import indicators as I

from . import ArmInput
from . import _pa as P

ATR_LEN = 14
MIN_MUM = 40                       # isinma: bu kadar mum yoksa aday yok, hata yok
MIN_STOP_ORAN = 0.006
PIV_SOL, PIV_SAG = 10, 2           # pivot: sol 10, sag 2, kesin esitsizlik; ancak indeksi <= t-2 olan pivot kullanilir
IND_PENCERE = 1200                 # uzun serilerde ozyinelemeli gostergeler son bu kadar mumdan hesaplanir (hata < 1e-15)
KUTUPHANE_FEATURES = {"body_ratio": "body_ratio", "wick_ratio": "wick_ratio", "rr": "rr", "f_seviye": "ema_value",
                      "f_olcu_atr": "edge_dist_atr", "f_yas": "pullback_ema"}


@dataclass(frozen=True)
class Formasyon:
    kod: str
    ad: str
    sira: int
    tfs: tuple[str, ...]
    zaman_stopu: int
    bul: Callable                  # bul(g: Gorunum) -> None | dict(stop, hedef, seviye, olcu, yas, etiket)
    cikis: Callable | None = None  # cikis(inp: ArmInput) -> bool | None (kural cikisi)
    kip: str = "target"            # cikis kipi: "target" (hedef + zaman stopu) | "trail" (iz suren stop; hedef yok; ana kol trail ise)


class Gorunum:
    """Long uzayinda (short icin aynalanmis) `t` anindaki goruntu. Dizilerin tamami verilir ama dedektor YALNIZ `<= t` okur."""
    __slots__ = ("o", "h", "l", "c", "atr", "t", "v", "yon", "ham", "gun", "onb")

    def __init__(self, o, h, l, c, atr, t: int, v=None, yon: str = "long", ham=None, gun=None) -> None:
        self.o, self.h, self.l, self.c, self.atr, self.t = o, h, l, c, atr, t
        self.v, self.yon, self.ham = v, yon, ham          # hacim (aynalanmaz), yon, ortak ham (ana kol / rejim erisimi)
        self.gun = gun                          # UTC gun numarasi (VWAP demiri)
        self.onb: dict = {}                     # tembel onbellek: gosterge / pivot dizileri (tum dizi uzerinde, nedensel)

    def trend_ok(self) -> bool:
        """`t` anindaki 4s rejimi bu yonun trendi mi (core tablosu; long trend_up, short trend_down)."""
        return self.ham is not None and self.ham.rejim_t() == ("trend_up" if self.yon == "long" else "trend_down")

    def ana(self, modul):
        """Ana kolun (T1/R1/TF1/B1/H2/S1/F1) `t` mumundaki ayni yonlu, sinyal=True satiri g-uzayinda: dict(stop, hedef, satir) ya
        da None. Ana kol hesabi cift x ZD x D basina bir kez (onbellek); ana kolun davranisi degismez."""
        return self.ham.ana_satir(modul, self.yon) if self.ham is not None else None

    def once(self, anahtar, fn):
        """`fn()` sonucunu bu gorunumde bir kez hesaplar (gosterge dizileri nedensel: t anindaki deger yalniz <= t verisinden)."""
        r = self.onb.get(anahtar)
        if r is None:
            r = self.onb[anahtar] = fn()
        return r

    def pivotlar(self, t: int | None = None):
        """(tepe_idx, dip_idx): `t` aninda ONAYLI pivotlar (indeks <= t-2; sol 10, sag 2, kesin). Pivot i, i+2 kapanisinda bilinir."""
        t = self.t if t is None else t
        pt, pd_ = self.once("pivot", lambda: (np.flatnonzero(I.pivot_tepe(self.h, PIV_SOL, PIV_SAG)),
                                                np.flatnonzero(I.pivot_dip(self.l, PIV_SOL, PIV_SAG))))
        k = t - PIV_SAG
        return pt[:np.searchsorted(pt, k, side="right")], pd_[:np.searchsorted(pd_, k, side="right")]

    def dip(self, n: int, k: int = 0) -> float:
        """l[t-k-n+1 .. t-k] en kucugu (pencere `t-k` dahil)."""
        e = self.t - k
        return float(self.l[e - n + 1:e + 1].min())


class _Ham:
    __slots__ = ("o", "h", "l", "c", "atr", "ok", "gor", "bos", "v", "inp", "_reg", "_ana", "oz", "gun")

    def __init__(self, trig, inp=None) -> None:
        self.inp = inp
        self._reg = None
        self._ana: dict = {}
        self.oz: dict = {}                   # varyantlarin paylastigi ara hesaplar (EMA, ham tarama ...)
        self.o = trig["open"].to_numpy(dtype=float)
        self.h = trig["high"].to_numpy(dtype=float)
        self.l = trig["low"].to_numpy(dtype=float)
        self.c = trig["close"].to_numpy(dtype=float)
        self.atr = I.atr(trig[["high", "low", "close"]], ATR_LEN).to_numpy(dtype=float)
        self.v = trig["volume"].to_numpy(dtype=float) if "volume" in trig.columns else np.ones(len(self.c))
        ix = trig.index
        try:
            ix = ix.tz_convert("UTC").tz_localize(None) if getattr(ix, "tz", None) is not None else ix
            self.gun = ix.to_numpy().astype("datetime64[D]").astype(np.int64)      # UTC gun numarasi (VWAP demiri)
        except Exception:  # noqa: BLE001 - zaman indeksi degilse VWAP aday uretmez
            self.gun = None
        t = len(self.c) - 1
        with np.errstate(invalid="ignore"):
            self.ok = bool(t >= MIN_MUM and np.isfinite([self.o[t], self.h[t], self.l[t], self.c[t], self.atr[t]]).all()
                           and self.h[t] - self.l[t] > 0 and self.atr[t] > 0)
        self.gor: dict[str, Gorunum] = {}
        self.bos = None                      # aday yokken tum formasyonlarin paylastigi bos tablo

    def gorunum(self, side: str) -> Gorunum:
        g = self.gor.get(side)
        if g is None:
            t = len(self.c) - 1
            if side == "long":
                g = Gorunum(self.o, self.h, self.l, self.c, self.atr, t, self.v, side, self, self.gun)
            else:
                g = Gorunum(-self.o, -self.l, -self.h, -self.c, self.atr, t, self.v, side, self, self.gun)
            self.gor[side] = g
        return g

    def rejim_t(self):
        """Son mumun 4s rejimi (core tablosundan; ortak tabloyla ayni nedensel deger). Core yoksa None."""
        if self._reg is None:
            try:
                self._reg = str(self.inp.core()["regime"].iloc[-1])
            except Exception:  # noqa: BLE001
                self._reg = ""
        return self._reg or None

    def ana_satir(self, modul, yon: str):
        """Ana kolun son mum satiri (`modul.compute(inp)`; ayni yonde ve signal=True ise): g-uzayinda dict ya da None."""
        key = modul.SETUP
        if key not in self._ana:
            fr = modul.compute(self.inp)
            self._ana[key] = fr.iloc[-1]
        row = self._ana[key]
        if row["setup"] != key or row["side"] != yon or not bool(row["signal"]):
            return None
        sg = P.SIGN[yon]
        tgt = row["planned_target"]
        return {"stop": sg * float(row["planned_stop"]), "hedef": None if not np.isfinite(tgt) else sg * float(tgt),
                "satir": row}


_ONBELLEK: dict = {}                         # anahtar -> _Ham; en cok _ONBELLEK_MAX giris (en eski atilir)
_ONBELLEK_MAX = 96                           # PA varyantlari: ayni cift x ZD x D icin 100+ kol ham ve ana kol hesabini paylasir


def ortak(inp: ArmInput) -> _Ham:
    """Gosterge hazirligi cift x ZD x D basina BIR kez (onbellek; anahtar cift, ZD, D, uzunluk, son indeks)."""
    trig = inp.trig
    key = (inp.pair, inp.tf, inp.D, len(trig), trig.index[-1] if len(trig) else None)
    ham = _ONBELLEK.get(key)
    if ham is not None:
        return ham
    ham = _Ham(trig, inp)
    _ONBELLEK[key] = ham
    while len(_ONBELLEK) > _ONBELLEK_MAX:
        _ONBELLEK.pop(next(iter(_ONBELLEK)))
    return ham


def hesapla(aile: str, formasyonlar: dict, kod: str, inp: ArmInput):
    """`kod` formasyonunun aday tablosu (SIGNAL_COLUMNS). Aday yoksa onbellekteki ortak bos tablo doner (kopya yok)."""
    f = formasyonlar[kod]
    setup = f"{aile}-{kod}"
    ham = ortak(inp)
    core = inp.core()
    if not ham.ok:
        return _bos(ham, core)
    t = len(ham.c) - 1
    bulgu: dict[str, dict] = {}
    for side in P.SIDES:
        r = f.bul(ham.gorunum(side))
        if r is not None:
            bulgu[side] = r
    if not bulgu:
        return _bos(ham, core)
    tab = P.Table(core)
    if len(bulgu) == 2:
        tab.both(t, setup)
        return tab.frame()
    side, r = next(iter(bulgu.items()))
    g = ham.gorunum(side)
    s = P.SIGN[side]
    entry = float(g.c[t])
    stop = float(r["stop"])
    risk = entry - stop
    hedef = r.get("hedef")
    trail = f.kip == "trail"                 # iz suren stop kipi: hedef yok (ana kolun TF1/H2/S1/T1 yolu)
    hedef = None if trail else (entry + 2.0 * risk if hedef is None else float(hedef))
    skip = None
    if not (risk > 0) or risk < MIN_STOP_ORAN * abs(entry):
        skip = "stop_width"
    elif not trail and not (hedef > entry):
        skip = "rr_below_min"
    rng = float(g.h[t] - g.l[t])
    body = abs(float(g.c[t] - g.o[t])) / rng
    wick = (float(min(g.o[t], g.c[t]) - g.l[t])) / rng
    atr = float(ham.atr[t])
    rr = np.nan if trail else ((hedef - entry) / risk if risk > 0 else np.nan)
    tab.put(t, setup=setup, side=side, skip=skip, labels=[str(r.get("etiket", kod.lower()))], entry=s * entry, stop=s * stop,
            target=None if trail else s * hedef, rr=rr, sda=risk / atr, ema=s * float(r.get("seviye", stop)), body=body, wick=wick,
            edge=float(r.get("olcu", abs(risk))) / atr, pb=int(r.get("yas", 0)))
    return tab.frame()


def _bos(ham: _Ham, core):
    if ham.bos is None:
        ham.bos = P.Table(core).frame()
    return ham.bos


def sanal_kurulumlar(mod) -> dict[str, SimpleNamespace]:
    """Kutuphane modulunden {AILE-FORMASYON: sanal kurulum modulu} (SETUP, TIMEFRAMES, CORE, EXIT_MODE, FEATURES, PRIORITY,
    TIME_STOP, EXIT_RULE, compute)."""
    out: dict[str, SimpleNamespace] = {}
    for kod, f in mod.FORMASYONLAR.items():
        setup = f"{mod.SETUP}-{kod}"
        feats = {k: v for k, v in KUTUPHANE_FEATURES.items() if not (f.kip == "trail" and k == "rr")}
        out[setup] = SimpleNamespace(
            SETUP=setup, TIMEFRAMES=tuple(f.tfs), CORE=False, EXIT_MODE=f.kip, FEATURES=feats,
            PRIORITY=int(mod.PRIORITY) + int(f.sira), TIME_STOP=int(f.zaman_stopu), EXIT_RULE=f.cikis,
            compute=partial(hesapla, mod.SETUP, mod.FORMASYONLAR, kod), FORMASYON=f, AILE=mod.SETUP)
    return out
