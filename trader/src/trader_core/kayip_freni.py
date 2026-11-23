"""Kayip freni (23.11 kullanici karari: asama B esikleri). Saf Python, durum dosyasi YOK: durum deftere (kapanan islemler) ve
state'teki gun basi kasaya bakilarak her seferinde TURETILIR; yeniden baslatmada kendiliginden ayni sonuc.

Tetik (biri yeter):
  - ardisik: son `ardisik` kapanan islemin hepsi zararda (realized_pnl < 0; elle kapanis `manual` sayilmaz).
    Ilk kazancli (ya da basa-bas) kapanista kalkar (seri bozulur) VE yeni UTC gununde kalkar (yalniz bugun kapananlar sayilir).
  - gunluk: bugunku zarar (gun basi kasa - kasa) / gun basi kasa >= gunluk_oran. UTC gun basinda (yeni gun_basi kasasi) kalkar.
Etki: islem basi hedef risk `carpan` ile carpilir (0.01 -> 0.005). YALNIZ KUCULTUR: etkin hedef = min(kademe/kol hedefi, taban hedef x carpan).
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FrenKarari:
    aktif: bool
    neden: str | None          # "ardisik" | "gunluk" | None
    carpan: float              # 1.0 = fren yok
    ardisik_kayip: int         # sayilan ardisik kayip (kayit icin)


YOK = FrenKarari(False, None, 1.0, 0)


def _fin(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x))


def ardisik_kayip(kapananlar_yeniden_eskiye: Sequence, ust: int) -> int:
    """Sondan baslayarak ust uste zararli kapanis sayisi (en cok `ust`). Elle kapanis atlanir; ilk KAZANCLI kapanis seriyi keser; basa-bas (pnl == 0) notr."""
    n = 0
    for t in kapananlar_yeniden_eskiye:
        if getattr(t, "exit_reason", None) == "manual":
            continue
        pnl = getattr(t, "realized_pnl", None)
        if _fin(pnl) and float(pnl) == 0.0:      # basa-bas: notr (ne seriyi keser ne sayilir)
            continue
        if not _fin(pnl) or float(pnl) > 0.0:
            break
        n += 1
        if n >= ust:
            break
    return n


def _son_kazanc(kapananlar_yeniden_eskiye: Sequence) -> bool:
    """En yeni anlamli (elle olmayan, pnl != 0) kapanis kazancli mi? (gunluk freni kaldirir; basa-bas notr)"""
    for t in kapananlar_yeniden_eskiye:
        if getattr(t, "exit_reason", None) == "manual":
            continue
        pnl = getattr(t, "realized_pnl", None)
        if _fin(pnl) and float(pnl) != 0.0:
            return float(pnl) > 0.0
    return False


def karar(cfg: Mapping | None, kapananlar_yeniden_eskiye: Sequence, equity: float, gun_basi_kasa: float, gun_basi=None) -> FrenKarari:
    """cfg = {ardisik, gunluk_oran, carpan} (bos/None = kapali). Hata durumunda cagiran fren uygulamaz (kucultme zaten sigorta)."""
    if not cfg:
        return YOK
    if gun_basi is not None:        # seri gece yarisini asmaz: yalniz bugunku (UTC) kapanislar
        kapananlar_yeniden_eskiye = [t for t in kapananlar_yeniden_eskiye
                                     if getattr(t, "exit_ts", None) is not None and t.exit_ts >= gun_basi]
    n = ardisik_kayip(kapananlar_yeniden_eskiye, int(cfg["ardisik"]))
    carpan = float(cfg["carpan"])
    if n >= int(cfg["ardisik"]):
        return FrenKarari(True, "ardisik", carpan, n)
    if _son_kazanc(kapananlar_yeniden_eskiye):          # gunluk fren de ilk kazancli kapanista kalkar
        return FrenKarari(False, None, 1.0, n)
    if _fin(equity) and _fin(gun_basi_kasa) and float(gun_basi_kasa) > 0:
        zarar = (float(gun_basi_kasa) - float(equity)) / float(gun_basi_kasa)
        if zarar >= float(cfg["gunluk_oran"]):
            return FrenKarari(True, "gunluk", carpan, n)
    return FrenKarari(False, None, 1.0, n)


def goreli_carpan(fren: FrenKarari, taban_hedef: float, etkin_hedef: float) -> float:
    """Frenin `check_entry_scaled` icin goreli carpani: min(1, taban_hedef*carpan / etkin_hedef). Etkin hedef (kademe/mandal) zaten
    daha dusukse 1.0 (fren onu ARTIRMAZ). Fren yoksa 1.0."""
    if not fren.aktif or not etkin_hedef > 0:
        return 1.0
    return min(1.0, float(taban_hedef) * fren.carpan / float(etkin_hedef))
