"""Kademeli boyut kucultme (20 Kasim 2026, yalniz kagit): kolun son kapanan islemlerinin net R toplamina gore islem basi
risk carpani. Spec: docs/motor/kademeli-kucultme-spec.md. Saf Python (stdlib); girdi: kolun kapanan islemlerinin net R
degerleri, EN YENIDEN ESKIYE.

Kural (kesin, deterministik):
  n >= 10 ve son 10'un toplami < 0  -> 0.3   (asgari boyut; kol ASLA kapatilmaz)
  degilse n >= 5 ve son 5'in toplami < 0 -> 0.5
  degilse 1.0
Buzulme (23.11, fikir 8): `aile_ort` (ayni kurulumun TUM TF'lerindeki tum kapanmis islemlerin ortalama net R'si) verilirse
kolun pencere ORTALAMASI aileye cekilir: R_buzulmus = (n*R_kol + k*R_aile)/(n+k), k = K_BUZULME (10), n = pencere (5 / 10).
Esikler ayni (< 0) ama toplam yerine buzulmus ortalama kullanilir; aile ortalamasi yoksa (None) ham toplam kurali.
Carpan yalniz kucultur (<= 1.0); stop/kaldirac/gunluk limit/kademe (RK-1) anlamina dokunmaz. Geri yukselis otomatiktir:
pencere toplami >= 0 olunca carpan bir ust basamaga cikar (0.3 -> 0.5 -> 1.0)."""
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
    buz_5: float | None = None  # son 5'in buzulmus ortalama R'si
    buz_10: float | None = None


def buzulme(n: int, r_kol: float | None, r_aile: float, k: int = K_BUZULME) -> float:
    """R_buzulmus = (n*R_kol + k*R_aile)/(n+k). n = 0 (ya da R_kol yok) => R_aile; n buyudukce kol ortalamasina yaklasir."""
    if n <= 0 or r_kol is None:
        return float(r_aile)
    return (n * float(r_kol) + k * float(r_aile)) / (n + k)


def aile_ortalamasi(kol_sonuclari: "dict[str, Sequence[float]]") -> dict[str, float]:
    """{arm_id: net R listesi} -> {kurulum (arm_id'nin '@' oncesi): tum TF'lerdeki ortalama net R}."""
    toplam: dict[str, list[float]] = {}
    for arm, vals in kol_sonuclari.items():
        toplam.setdefault(str(arm).split("@")[0], []).extend(float(v) for v in vals if v is not None and math.isfinite(float(v)))
    return {a: math.fsum(v) / len(v) for a, v in toplam.items() if v}


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
    b5 = buzulme(PENCERE_KISA, n5 / PENCERE_KISA, aile_ort) if n5 is not None else None
    b10 = buzulme(PENCERE_UZUN, n10 / PENCERE_UZUN, aile_ort) if n10 is not None else None
    if b10 is not None and b10 < 0:
        c = CARPAN_MIN
    elif b5 is not None and b5 < 0:
        c = CARPAN_YARI
    else:
        c = 1.0
    return KolKarar(c, n, n5, n10, float(aile_ort), b5, b10)


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
    aile = aile_ortalamasi(kol_sonuclari) if buzulmeli else {}    # NOT: ham liste ne kadar uzunsa aile ortalamasi o kadar genis (kapi ile ayni: tum zaman)
    for arm, vals in kol_sonuclari.items():
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
