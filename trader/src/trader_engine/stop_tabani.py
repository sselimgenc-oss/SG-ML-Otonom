"""27.11 sahip karari: STOP TABANI (tek kural, tum kurulumlar). Giris kararinda (EntryGate.stop_tabani_uygula, boyuttan ve ML1
puanlamasindan ONCE) uygulanir; kagit/canli/geri test ayni yol. Saf hesap (G/C yok).

  c_rt     = 2 x (fee_rate + slippage_rate)   (boyutlamayla ayni maliyet: risk_config; `cost_overrides`'li cift/seans icin kayma =
             max(slippage_rate, (slip_entry_bps + slip_stop_bps) / 2 / 1e4): giris + stop cikisi kaymasi)
  taban    = max(atr_kat x ATR_tf, c_rt / maliyet_payi x giris)        (mesafe, fiyat birimi)
  d        = |giris - planli_stop|   (dogal mesafe)
  d >= taban                      : degismez
  genislet_esik x taban <= d < taban : stop AYNI tarafta tam taban mesafesine GENISLETILIR (hedef fiyati ayni; risk % ayni, boyut kuculur);
                                    hedefli kurulumda rr yeniden hesaplanir: rr < rr_min (yoksa 1.0) => `rr_below_min`
  d < genislet_esik x taban       : `stop_width`
Kurulumun ust siniri (cekirdek 2.0 ATR, TF1/S1 3.0, B1/H2 2.5, F1 2.0; kutuphane: yok) KORUNUR: genisletilmis mesafe bu siniri asarsa `stop_width`."""
from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from typing import Any

EPS = 1e-9
_REL = 1e-12
RR_MIN_VARSAYILAN = 1.0
RR_MIN_PARAMLI = ("R1", "B1", "F1")       # arm kendi `rr_min` parametresini kullanan kurulumlar (signals.SignalParams.rr_min)
_MAX_ATR: dict[str, float] | None = None


def max_atr_of(setup: str | None) -> float | None:
    """Kurulumun bugunku stop ust siniri (ATR kati); kutuphane/varyant kurulumlarinda ust sinir yok (None)."""
    global _MAX_ATR
    if _MAX_ATR is None:
        from trader_core import signals as S
        from .strategies.arms import b1, f1, h2, s1, tf1
        _MAX_ATR = {"T1": S.STOP_DIST_MAX_ATR, "R1": S.STOP_DIST_MAX_ATR, "TF1": tf1.SDA_MAX, "B1": b1.SDA_MAX,
                    "H2": h2.SDA_MAX, "S1": s1.SDA_MAX, "F1": f1.SDA_MAX}
    return _MAX_ATR.get(setup or "")


def rr_min_of(setup: str | None, params: Mapping[str, Any] | None) -> float:
    if setup in RR_MIN_PARAMLI and params is not None:
        v = params.get("rr_min")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0:
            return float(v)
    return RR_MIN_VARSAYILAN


def rt_maliyet(risk_cfg, cost, cost_overrides: Mapping | None, pair: str, tag: str | None) -> float:
    """Gidis-donus maliyet ORANI c_rt = 2 x (fee_rate + slippage_rate). `cost_overrides[cift][seans]` varsa kayma, giris+stop
    kaymasinin ortalamasi (bps) ile en az `slippage_rate`; eksik anahtar `cost`'tan (CostModel) gelir."""
    slip = float(risk_cfg.slippage_rate)
    ov = (cost_overrides or {}).get(pair)
    sl = ov.get(tag) if (ov and tag) else None
    if sl:
        e = float(sl.get("slip_entry_bps", cost.slip_entry_bps))
        s = float(sl.get("slip_stop_bps", cost.slip_stop_bps))
        slip = max(slip, (e + s) / 2.0 / 1e4)
    return 2.0 * (float(risk_cfg.fee_rate) + slip)


def taban_orani(c_rt: float, entry: float, atr: float | None, cfg: Mapping[str, Any]) -> tuple[float, float]:
    """(taban mesafesi fiyat biriminde, taban yuzdesi giris'e gore)."""
    d = float(cfg["maliyet_payi"])
    cost_d = c_rt / d * entry
    atr_d = float(cfg["atr_kat"]) * atr if (atr is not None and math.isfinite(atr) and atr > 0) else 0.0
    f = max(atr_d, cost_d)
    return f, f / entry


def uygula(row, cfg: Mapping[str, Any], c_rt: float, rr_min: float, max_atr: float | None):
    """`row` (SignalRow, signal=True) icin kurali uygular -> (yeni_satir, kod). kod None = giris surer (degismez/genisletildi);
    "stop_width"/"rr_below_min" = elendi (signal=False, skip_reason). Yeni satir `stop_dogal` ve `stop_genisletildi` tasir."""
    e, s = float(row.planned_entry), float(row.planned_stop)
    atr = row.atr_tf
    d = abs(e - s)
    floor_d, _ = taban_orani(c_rt, e, atr, cfg)
    base = dataclasses.replace(row, stop_dogal=s, stop_genisletildi=False)
    if d >= floor_d * (1.0 - _REL):
        return base, None
    if d < float(cfg["genislet_esik"]) * floor_d:
        return _ele(base, "stop_width", "stop_tabani_dar"), "stop_width"
    new_s = e - floor_d if row.side == "long" else e + floor_d
    if not new_s > 0 or (max_atr is not None and atr and atr > 0 and floor_d > max_atr * atr + EPS):
        return _ele(base, "stop_width", "stop_tabani_ust_sinir"), "stop_width"
    t = row.planned_target
    rr = row.rr
    if t is not None and math.isfinite(t):                    # hedefli kurulum: hedef fiyati ayni, rr yeniden
        rr = abs(float(t) - e) / floor_d
        if rr < rr_min - EPS:
            return _ele(dataclasses.replace(base, rr=rr), "rr_below_min", "stop_tabani_rr"), "rr_below_min"
    sda = floor_d / atr if (atr and atr > 0) else row.stop_dist_atr
    return dataclasses.replace(base, planned_stop=new_s, stop_dist_atr=sda, rr=rr, stop_genisletildi=True,
                               reasons=(row.reasons + ",stop_tabani_genisletildi")), None


def _ele(row, kod: str, neden: str):
    return dataclasses.replace(row, signal=False, skip_reason=kod, reasons=(row.reasons + "," + neden))
