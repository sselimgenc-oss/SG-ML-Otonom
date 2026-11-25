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
KUTUPHANE_FEATURES = {"body_ratio": "body_ratio", "wick_ratio": "wick_ratio", "rr": "rr", "f_seviye": "ema_value",
                      "f_olcu_atr": "edge_dist_atr", "f_yas": "pullback_ema"}


@dataclass(frozen=True)
class Formasyon:
    kod: str
    ad: str
    sira: int
    tfs: tuple[str, ...]
    zaman_stopu: "int | dict"      # mum sayisi; ya da {"15m": 48, "1h": 12} (ZD basina; PA2-TUKENIS)
    bul: Callable                  # bul(g: Gorunum) -> None | dict(stop, hedef, seviye, olcu, yas, etiket)
    cikis: Callable | None = None  # cikis(inp: ArmInput) -> bool | None (kural cikisi)


class Gorunum:
    """Long uzayinda (short icin aynalanmis) `t` anindaki goruntu. Dizilerin tamami verilir ama dedektor YALNIZ `<= t` okur."""
    __slots__ = ("o", "h", "l", "c", "atr", "t", "sec", "onb")

    def __init__(self, o, h, l, c, atr, t: int, sec=None) -> None:
        self.o, self.h, self.l, self.c, self.atr, self.t = o, h, l, c, atr, t
        self.sec = sec                 # mum acilis zamani (UTC saniye, int64); PA2 zaman tabanli dedektorler (yalniz <= t okunur)
        self.onb: dict = {}            # dedektorler arasi paylasilan hesap onbellegi (pivotlar ...)

    def dip(self, n: int, k: int = 0) -> float:
        """l[t-k-n+1 .. t-k] en kucugu (pencere `t-k` dahil)."""
        e = self.t - k
        return float(self.l[e - n + 1:e + 1].min())


class _Ham:
    __slots__ = ("o", "h", "l", "c", "atr", "ok", "gor", "bos", "sec")

    def __init__(self, trig) -> None:
        self.o = trig["open"].to_numpy(dtype=float)
        self.h = trig["high"].to_numpy(dtype=float)
        self.l = trig["low"].to_numpy(dtype=float)
        self.c = trig["close"].to_numpy(dtype=float)
        self.atr = I.atr(trig[["high", "low", "close"]], ATR_LEN).to_numpy(dtype=float)
        ix = trig.index
        try:
            ix = ix.tz_convert(None) if getattr(ix, "tz", None) is not None else ix
            self.sec = ix.to_numpy().astype("datetime64[s]").astype("int64")
        except (TypeError, ValueError, AttributeError):
            self.sec = None
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
                g = Gorunum(self.o, self.h, self.l, self.c, self.atr, t, self.sec)
            else:
                g = Gorunum(-self.o, -self.l, -self.h, -self.c, self.atr, t, self.sec)
            self.gor[side] = g
        return g


_ONBELLEK: list = [None, None]               # [anahtar, _Ham]; tek girisli (cift x ZD x D)


def ortak(inp: ArmInput) -> _Ham:
    """Gosterge hazirligi cift x ZD x D basina BIR kez (tek girisli onbellek; anahtar cift, ZD, D, uzunluk, son indeks)."""
    trig = inp.trig
    key = (inp.pair, inp.tf, inp.D, len(trig), trig.index[-1] if len(trig) else None)
    if _ONBELLEK[0] == key and _ONBELLEK[1] is not None:
        return _ONBELLEK[1]
    ham = _Ham(trig)
    _ONBELLEK[0], _ONBELLEK[1] = key, ham
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
    hedef = entry + 2.0 * risk if hedef is None else float(hedef)
    skip = None
    if not (risk > 0) or risk < MIN_STOP_ORAN * abs(entry):
        skip = "stop_width"
    elif not (hedef > entry):
        skip = "rr_below_min"
    rng = float(g.h[t] - g.l[t])
    body = abs(float(g.c[t] - g.o[t])) / rng
    wick = (float(min(g.o[t], g.c[t]) - g.l[t])) / rng
    atr = float(ham.atr[t])
    rr = (hedef - entry) / risk if risk > 0 else np.nan
    tab.put(t, setup=setup, side=side, skip=skip, labels=[str(r.get("etiket", kod.lower()))], entry=s * entry, stop=s * stop,
            target=s * hedef, rr=rr, sda=risk / atr, ema=s * float(r.get("seviye", stop)), body=body, wick=wick,
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
        out[setup] = SimpleNamespace(
            SETUP=setup, TIMEFRAMES=tuple(f.tfs), CORE=False, EXIT_MODE="target", FEATURES=dict(KUTUPHANE_FEATURES),
            PRIORITY=int(mod.PRIORITY) + int(f.sira), TIME_STOP=(dict(f.zaman_stopu) if isinstance(f.zaman_stopu, dict) else int(f.zaman_stopu)), EXIT_RULE=f.cikis,
            compute=partial(hesapla, mod.SETUP, mod.FORMASYONLAR, kod), FORMASYON=f, AILE=mod.SETUP)
    return out
