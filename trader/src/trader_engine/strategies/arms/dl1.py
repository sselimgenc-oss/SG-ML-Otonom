"""DL1: derin ogrenme kolu (ust lig; tasarim fikirler/pazartesi-23-11/ust-lig-tasarim.md bolum 2 ve 6). Aday, `models/dl1/DL1@<tf>.json`
paketindeki kucuk 1D-CNN'in puanindan uretilir (her gece GitHub Actions'ta dort zaman dilimi icin egitilir ve KAPISIZ yayinlanir; motor torch/trader_ml ICE
AKTARMAZ, ileri gecis saf numpy: `trader_engine.dl1_cikarim`). Dort zaman dilimi (24.11 kullanici karari): 15m, 1h, 4h, 1d; her biri kendi paketi.

Paket yok / bozuk / hash tutmuyor -> aday yok (sayac `COUNTERS`); diger kollar ve acik pozisyonlar etkilenmez (M1/HB1 ile ayni ilke).
Kalite kapisi ve 45 gunluk son kullanma ENGELLEMEZ (24.11): kapisiz paket ve eski paket islem yapar; eski paket yalniz uyari sayaci + log uretir.
Kapsam: paketin `kapsam.siniflar` listesindeki 43 enstruman (kripto + hisse + emtia); kapsam disi cift: aday yok.
Giris: yalniz karar barinda (o zaman diliminin son kapanmis mumu) long ve short puanlanir; esik (paket icinde, egitim puanlarinin %98'ligi) ustundeki en
yuksek yon secilir. Stop = giris -/+ 1,5 ATR, hedef = giris +/- 3 ATR (egitim etiketiyle ayni; ATR = son 14 dolu mumun ortalama gercek araligi).
Zaman stopu motorun ortak kuralidir (signals.TIME_STOP_BARS = 48 mum, her zaman diliminde o zaman diliminin mumu) ve egitim etiketi ufku ayni 48'dir; egitim R'si canli cikislari
(basa-bas + kismi kar, bosluk acilis dolumu) taklit eder.
Seansli araclar: bos/eksik mumlar doldurulmaz; pencere dolu mumlardan kurulur ve doluluk orani < %50 ise aday yok (dl1_cikarim.MIN_DOLU_ORAN).
Seans kapaliyken mevcut ortak kapilar gecerlidir (bu dosya yeni kapi eklemez). Cikarim her mumda bir kez (cift, bar zamani, paket hash'i onbellekli)."""
from __future__ import annotations

import logging
import math
from collections import Counter

import numpy as np
import pandas as pd


from ... import dl1_cikarim as DL
from . import ArmInput
from . import _pa as P
from .m1 import empty_output

log = logging.getLogger("trader.dl1")

SETUP = "DL1"
TIMEFRAMES = DL.ZAMAN_DILIMLERI              # ("15m", "1h", "4h", "1d"); her zaman dilimi kendi paketi (DL1@<tf>.json)
CORE = False
ML_SCORED = False
EXIT_MODE = "target"
PRIORITY = 95                            # M1 (90) ve HB1 (92) ile ayni mumda cakisirsa onlar kazanir
FEATURES = {"dl1_body": "body_ratio", "dl1_wick": "wick_ratio", "dl1_rr": "rr"}
RR = DL.HEDEF_ATR / DL.STOP_ATR

COUNTERS: Counter = Counter()
_LOG: dict = {}                          # tf -> son log saati; "eski_uyari" -> {(tf, sha)} uyarisi verilmis paketler
_ONBELLEK: dict = {}                     # (cift, tf, son bar ns, paket sha) -> puan (en fazla ~100 kayit)


def _ns(index: pd.DatetimeIndex) -> np.ndarray:
    ix = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    return ix.as_unit("ns").asi8


def _sayac_logu(D, tf: str) -> None:
    """Sayaclari her zaman diliminde en fazla saatte bir INFO olarak yazar (bar zamani D'ye gore; duvar saati yok)."""
    saat = D.replace(minute=0, second=0, microsecond=0)
    onceki = _LOG.get(tf)
    if onceki != saat:
        if onceki is not None and COUNTERS:
            log.info("DL1 sayaclar: %s", dict(sorted(COUNTERS.items())))
        _LOG[tf] = saat


def _eski_uyari(paket, D, tf: str) -> None:
    """45 gunden yasli paket ENGELLENMEZ (24.11); her cagrida sayac, paket basina bir kez WARNING."""
    if not paket.eski(D):
        return
    COUNTERS["paket_eski_uyari"] += 1
    anahtar = (tf, paket.sha256)
    gorulen = _LOG.setdefault("eski_uyari", set())
    if anahtar not in gorulen:
        gorulen.add(anahtar)
        log.warning("DL1@%s paketi eski (olusturma %s, %d gunden yasli); islem yapmaya devam eder, gece egitimi yenilemedi", tf,
                    paket.olusturma.isoformat(), DL.SON_KULLANMA_GUN)


def compute(inp: ArmInput):
    trig = inp.trig
    _sayac_logu(inp.D, inp.tf)
    paket, neden = DL.paket_yukle(simdi=inp.D, tf=inp.tf)
    if paket is None:                    # yok/bozuk/hash/sema: aday yok; kurulum tablosu hic hesaplanmaz
        COUNTERS["paket_" + str(neden)] += 1
        return empty_output(trig.index)
    _eski_uyari(paket, inp.D, inp.tf)
    if inp.pair not in paket.siniflar:
        COUNTERS["kapsam_disi"] += 1
        return empty_output(trig.index)
    if len(trig) < DL.MIN_BAR:
        COUNTERS["veri_kisa"] += 1
        return empty_output(trig.index)
    ts = _ns(trig.index)
    key = (inp.pair, inp.tf, int(ts[-1]), paket.sha256)
    if key in _ONBELLEK:
        sonuc = _ONBELLEK[key]
    else:
        sonuc = DL.puanla(paket, inp.pair, ts, *(trig[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "volume")))
        if len(_ONBELLEK) > 200:
            _ONBELLEK.clear()
        _ONBELLEK[key] = sonuc
    if sonuc is None:
        COUNTERS["puan_yok"] += 1
        return empty_output(trig.index)
    pl, ps, _vol, atr = sonuc
    best = None
    for side, sc in (("long", pl), ("short", ps)):
        if math.isfinite(sc) and sc >= paket.esik and (best is None or sc > best[1]):
            best = (side, sc)
    if best is None:
        COUNTERS["esik_alti"] += 1
        return empty_output(trig.index)
    core = inp.core()
    if core is None:                     # ortak tablo yok: aday yok
        COUNTERS["core_yok"] += 1
        return empty_output(trig.index)
    p = P.prepare(inp, core)
    tab = P.Table(p.core)
    i = len(p.c) - 1
    if not bool(p.ok[i]):                # son bar gecersiz (sonlu degil / h == l / ATR <= 0): aday yok
        COUNTERS["bar_gecersiz"] += 1
        return tab.frame()
    side, score = best
    s = P.SIGN[side]
    entry = float(p.c[i])
    stop = entry - s * DL.STOP_ATR * atr
    target = entry + s * DL.HEDEF_ATR * atr
    rng = float(p.h[i] - p.l[i])
    body = float(abs(p.c[i] - p.o[i]) / rng)
    wick = float((p.h[i] - max(p.o[i], p.c[i])) / rng) if side == "long" else float((min(p.o[i], p.c[i]) - p.l[i]) / rng)
    COUNTERS["aday"] += 1
    tab.put(i, setup=SETUP, side=side, skip=None, labels=["dl1", f"p={score:.3f}"], entry=entry, stop=stop, target=target,
            rr=RR, sda=DL.STOP_ATR, ema=np.nan, body=body, wick=wick, edge=np.nan, pb=0)
    return tab.frame()
