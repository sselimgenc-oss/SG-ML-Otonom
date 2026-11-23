"""Kademeli boyut kucultme (20 Kasim 2026, yalniz kagit): kolun son kapanan islemlerinin net R toplamina gore islem basi
risk carpani. Spec: docs/motor/kademeli-kucultme-spec.md. Saf Python (stdlib); girdi: kolun kapanan islemlerinin net R
degerleri, EN YENIDEN ESKIYE.

Kural (kesin, deterministik), aile ortalamasi YOKSA (ham):
  n >= 10 ve son 10'un toplami < 0  -> 0.3   (asgari boyut; kol ASLA kapatilmaz)
  degilse n >= 5 ve son 5'in toplami < 0 -> 0.5
  degilse 1.0
Buzulme (23.11, fikir 8): `aile_ort` (ayni kurulumun, kolun KENDISI haric diger kollarinin son 90 gundeki karar zamanina kadar
kapanmis islemlerinin ortalama net R'si; holdout disinda) verilirse kolun pencere ortalamasi aileye cekilir:
R_buz = (n*m_kol + K*R_aile)/(n+K), K = K_BUZULME (10), n = penceredeki GERCEK kapanmis islem sayisi (0..pencere; m_kol bu n
islemin ortalamasi, n = 0 ise yalniz aile). Olcut R_buz < 0: 5'lik pencere (n = min(islem, 5), 0 islem dahil) -> 0.5;
10'luk pencere (n = min(islem, 10)) -> 0.3, ama 0.3 yalniz pencere dolu (n >= 10) iken; az veride (n < 10) en kotu 0.5.
Aile ortalamasi yoksa (None) ham kural (toplam < 0, n >= 5 / n >= 10).
Carpan yalniz kucultur (<= 1.0); stop/kaldirac/gunluk limit/kademe (RK-1) anlamina dokunmaz. Geri yukselis otomatiktir:
her karar yeniden hesaplanir; buzulmus ortalama >= 0 olunca (kol toparlayinca ya da aile duzelince) carpan bir ust basamaga
(0.3 -> 0.5 -> 1.0) ya da dogrudan 1.0'a doner."""
from __future__ import annotations

import math
from typing import NamedTuple, Sequence

PENCERE_KISA = 5
PENCERE_UZUN = 10
CARPAN_YARI = 0.5
CARPAN_MIN = 0.3
KAYIT_SAYISI = PENCERE_UZUN
K_BUZULME = 10                 # buzulme gucu: kol ortalamasi n islemle, aile ortalamasi k = 10 "sanal" islemle agirliklanir


class KolKarar(NamedTuple):
    carpan: float
    n: int                      # degerlendirilen kapanmis islem sayisi (en cok 10)
    net_5: float | None         # son 5'in net R toplami (n < 5 ise None)
    net_10: float | None        # son 10'un net R toplami (n < 10 ise None)
    aile: float | None = None   # aile ortalama net R (buzulme kullanildiysa)
    buz_5: float | None = None  # 5'lik pencerenin buzulmus ortalama R'si
    buz_10: float | None = None


def buzulme(n: int, r_kol: float | None, r_aile: float, k: int = K_BUZULME) -> float:
    """R_buzulmus = (n*R_kol + k*R_aile)/(n+k). n = 0 (ya da R_kol yok) => R_aile; n buyudukce kol ortalamasina yaklasir."""
    if n <= 0 or r_kol is None:
        return float(r_aile)
    return (n * float(r_kol) + k * float(r_aile)) / (n + k)


def aile_ortalamasi(kol_sonuclari: "dict[str, Sequence[float]]", haric: str | None = None) -> dict[str, float]:
    """{arm_id: net R listesi} -> {kurulum (arm_id'nin '@' oncesi): tum TF'lerdeki ortalama net R}; `haric` arm_id'si sayilmaz."""
    toplam: dict[str, list[float]] = {}
    for arm, vals in kol_sonuclari.items():
        if haric is not None and arm == haric:
            continue
        toplam.setdefault(str(arm).split("@")[0], []).extend(float(v) for v in vals if v is not None and math.isfinite(float(v)))
    return {a: math.fsum(v) / len(v) for a, v in toplam.items() if v}


def _buz(vals: Sequence[float], pencere: int, aile: float) -> float:
    w = vals[:pencere]
    return buzulme(len(w), math.fsum(w) / len(w) if w else None, aile)


def karar(net_r_yeniden_eskiye: Sequence[float], aile_ort: float | None = None) -> KolKarar:
    vals = [float(v) for v in list(net_r_yeniden_eskiye)[:KAYIT_SAYISI] if v is not None and math.isfinite(float(v))]
    n = len(vals)
    n5 = math.fsum(vals[:PENCERE_KISA]) if n >= PENCERE_KISA else None
    n10 = math.fsum(vals[:PENCERE_UZUN]) if n >= PENCERE_UZUN else None
    if aile_ort is None or not math.isfinite(float(aile_ort)):
        if n10 is not None and n10 < 0:
            c = CARPAN_MIN
        elif n5 is not None and n5 < 0:
            c = CARPAN_YARI
        else:
            c = 1.0
        return KolKarar(c, n, n5, n10)
    b5 = _buz(vals, PENCERE_KISA, float(aile_ort))
    b10 = _buz(vals, PENCERE_UZUN, float(aile_ort))
    if n >= PENCERE_UZUN and b10 < 0:
        c = CARPAN_MIN
    elif b5 < 0:
        c = CARPAN_YARI
    else:
        c = 1.0
    return KolKarar(c, n, n5, n10, float(aile_ort), b5, b10 if n >= PENCERE_UZUN else None)


def ozellikler(k: KolKarar) -> dict:
    """Karar satiri `features` anahtarlari (yalniz kayit)."""
    out: dict = {"kol_boyut_carpani": float(k.carpan), "kol_n": int(k.n)}
    if k.net_5 is not None:
        out["kol_net_r_5"] = round(k.net_5, 6)
    if k.net_10 is not None:
        out["kol_net_r_10"] = round(k.net_10, 6)
    if k.aile is not None:
        out["kol_aile_r"] = round(k.aile, 6)
    if k.buz_5 is not None:
        out["kol_buz_r_5"] = round(k.buz_5, 6)
    if k.buz_10 is not None:
        out["kol_buz_r_10"] = round(k.buz_10, 6)
    return out


def azaltilanlar(kol_sonuclari: "dict[str, Sequence[float]]", buzulmeli: bool = True) -> dict[str, KolKarar]:
    """{arm_id: net R (yeniden eskiye)} -> yalniz carpani < 1.0 olan kollar ({arm_id: KolKarar}); rapor/panel icin."""
    out: dict[str, KolKarar] = {}
    for arm, vals in kol_sonuclari.items():       # NOT: rapor/panel yaklasimi; aile = kolun kendisi haric, verilen listelerin tamami (kapi 90 gunluk pencere kullanir)
        aile = aile_ortalamasi(kol_sonuclari, haric=arm) if buzulmeli else {}
        k = karar(vals, aile.get(str(arm).split("@")[0]))
        if k.carpan < 1.0:
            out[arm] = k
    return out


def satir(azaltilan: "dict[str, KolKarar]", en_cok: int = 4) -> str:
    """Telegram gunluk ozet satiri; azaltilan kol yoksa bos metin."""
    if not azaltilan:
        return ""
    parca = [f"{a} %{round(k.carpan * 100)}" for a, k in sorted(azaltilan.items())]
    ek = f" (+{len(parca) - en_cok})" if len(parca) > en_cok else ""
    return "Boyutu küçültülen kollar (son işlemler zararda): " + ", ".join(parca[:en_cok]) + ek
