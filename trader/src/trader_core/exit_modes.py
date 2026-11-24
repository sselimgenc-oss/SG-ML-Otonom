"""Cikis kipleri (docs/cikis-kipleri-spec.md): basa-bas (breakeven) ve kismi kar alma (partial take-profit).

Saf hesap (stdlib): motor (`trader_engine.position_manager` / `engine`) ve karsi-olgu oynatimi (`exit_counterfactual`) AYNI
islevleri cagirir (kagit = geri test = oynatim; tek kaynak). pandas/numpy yok. Varsayilan KAPALI: kip verilmedikce hicbir
yerde davranis degismez.

Kurallar (1 R = |giris - ilk stop|; en iyi uc = kapanmis mumlarin en yuksek high / en dusuk low'u):
  * basa-bas: en iyi uc >= giris +/- `be_trigger_r` R olunca stop girise +/- `be_offset_bps` (maliyet payi) cekilir.
    Yalniz sikilasir (iz suren stopla `max`/`min`); gevsemez.
  * kismi: en iyi uc >= giris +/- `pt_trigger_r` R olunca bir kez pozisyonun `pt_frac` kadari piyasada kapanir;
    kalan iz suren stop (ve varsa basa-bas) ile surer.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PARAM_BREAKEVEN = "exit_breakeven"      # defter istege bagli parametresi (0/1); ders yolu bunu acar
PARAM_PARTIAL = "exit_partial"
MODE_PARAMS = (PARAM_BREAKEVEN, PARAM_PARTIAL)

BE_TRIGGER_R = 1.0                      # varsayilan: +1 R'de stop girise
BE_OFFSET_BPS = 15.0                    # giris + ~15 bps: gidis-donus taker (2x5 bps) + stop kaymasi (5 bps) payi
PT_TRIGGER_R = 1.5                      # varsayilan: +1,5 R'de
PT_FRAC = 0.5                           # pozisyonun %50'si
TRIGGER_R_BOUNDS = (0.5, 5.0)
OFFSET_BPS_BOUNDS = (0.0, 100.0)
FRAC_BOUNDS = (0.1, 0.9)
EPS = 1e-9


class ExitModeError(ValueError):
    pass


@dataclass(frozen=True)
class ExitModes:
    """Bir kurulum icin etkin cikis kipleri; ikisi de None ise kip yok."""
    be_trigger_r: float | None = None
    be_offset_bps: float = BE_OFFSET_BPS
    pt_trigger_r: float | None = None
    pt_frac: float = PT_FRAC

    @property
    def breakeven(self) -> bool:
        return self.be_trigger_r is not None

    @property
    def partial(self) -> bool:
        return self.pt_trigger_r is not None

    @property
    def any(self) -> bool:
        return self.breakeven or self.partial


def _num(name: str, v, bounds: tuple[float, float]) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ExitModeError(f"{name} sonlu sayi olmali: {v!r}")
    if not bounds[0] <= v <= bounds[1]:
        raise ExitModeError(f"{name} aralik disi {bounds}: {v!r}")
    return float(v)


def parse_section(name: str, v) -> dict | None:
    """Yapilandirma bolumu: false/None -> kapali; true -> varsayilanlar; sozluk -> {trigger_r, offset_bps | frac}."""
    if v is None or v is False:
        return None
    if v is True:
        v = {}
    if not isinstance(v, Mapping):
        raise ExitModeError(f"exit_modes.{name} bool ya da sozluk olmali: {v!r}")
    allowed = {"trigger_r", "offset_bps"} if name == "breakeven" else {"trigger_r", "frac"}
    bad = sorted(set(v) - allowed)
    if bad:
        raise ExitModeError(f"exit_modes.{name} bilinmeyen anahtar: {bad}")
    if name == "breakeven":
        return {"trigger_r": _num("trigger_r", v.get("trigger_r", BE_TRIGGER_R), TRIGGER_R_BOUNDS),
                "offset_bps": _num("offset_bps", v.get("offset_bps", BE_OFFSET_BPS), OFFSET_BPS_BOUNDS)}
    return {"trigger_r": _num("trigger_r", v.get("trigger_r", PT_TRIGGER_R), TRIGGER_R_BOUNDS),
            "frac": _num("frac", v.get("frac", PT_FRAC), FRAC_BOUNDS)}


def make(be=None, pt=None) -> ExitModes | None:
    """`be`/`pt`: parse_section ciktisi (ya da None). Ikisi de yoksa None."""
    if be is None and pt is None:
        return None
    return ExitModes(be_trigger_r=None if be is None else be["trigger_r"],
                     be_offset_bps=BE_OFFSET_BPS if be is None else be["offset_bps"],
                     pt_trigger_r=None if pt is None else pt["trigger_r"],
                     pt_frac=PT_FRAC if pt is None else pt["frac"])


def from_flags(be: bool, pt: bool) -> ExitModes | None:
    """Ders yolu (defter istege bagli parametreleri 0/1): varsayilan sayilarla."""
    return make(parse_section("breakeven", True) if be else None, parse_section("partial", True) if pt else None)


def build_config(raw) -> dict[str, dict]:
    """`exit_modes` yapilandirmasi -> {anahtar: {"breakeven": dict|None, "partial": dict|None}}. Anahtar: "default", kurulum
    kodu ("T1") ya da arm kimligi ("T1@1h"). Bos/None -> {} (kip yok)."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, Mapping):
        raise ExitModeError("exit_modes sozluk olmali")
    out: dict[str, dict] = {}
    for k, sec in raw.items():
        if not isinstance(k, str) or not (k == "default" or _valid_key(k)):
            raise ExitModeError(f"exit_modes anahtari gecersiz: {k!r}")
        if not isinstance(sec, Mapping) or not set(sec) <= {"breakeven", "partial"}:
            raise ExitModeError(f"exit_modes.{k} {{breakeven, partial}} olmali")
        out[k] = {"breakeven": parse_section("breakeven", sec.get("breakeven")),
                  "partial": parse_section("partial", sec.get("partial"))}
    return out


def _valid_key(k: str) -> bool:
    return re.fullmatch(r"[A-Z][A-Z0-9]{1,7}(-[A-Z0-9]{2,10})?(@(15m|1h|4h|1d))?", k) is not None


def resolve(cfg_modes: Mapping[str, Mapping] | None, setup: str, trigger_tf: str | None,
            lesson_flags: Mapping[str, int] | None = None) -> ExitModes | None:
    """Pozisyonun kipleri: en dar yapilandirma anahtari kazanir (arm kimligi > kurulum > default); ders bayraklari (etkin
    defter parametreleri) yalniz yapilandirmada o kip KAPALI/yoksa ve kurulum T1 ise ek olarak acar. Hicbiri yoksa None."""
    be = pt = None
    if cfg_modes:
        arm = f"{setup}@{trigger_tf}" if trigger_tf else None
        for key in (arm, setup, "default"):
            sec = cfg_modes.get(key) if key else None
            if sec is not None:
                be, pt = sec.get("breakeven"), sec.get("partial")
                break
    if lesson_flags and setup == "T1":
        if be is None and int(lesson_flags.get(PARAM_BREAKEVEN, 0) or 0) == 1:
            be = parse_section("breakeven", True)
        if pt is None and int(lesson_flags.get(PARAM_PARTIAL, 0) or 0) == 1:
            pt = parse_section("partial", True)
    return make(be, pt)


# ---------------------------------------------------------------------------------------------- hesap
def _best(side: str, highs: Sequence[float], lows: Sequence[float]) -> float | None:
    vals = [float(h) for h in highs if h is not None and not math.isnan(float(h))] if side == "long" else \
           [float(x) for x in lows if x is not None and not math.isnan(float(x))]
    if not vals:
        return None
    return max(vals) if side == "long" else min(vals)


def reached_r(side: str, entry: float, initial_stop: float, best: float | None, trigger_r: float) -> bool:
    """En iyi uc `trigger_r` R'ye ulasti mi (EPS payi `signals.trail_stop_path` ile ayni sinirda)."""
    if best is None:
        return False
    r = abs(entry - initial_stop)
    if not r > 0:
        return False
    return (best >= entry + trigger_r * r - EPS) if side == "long" else (best <= entry - trigger_r * r + EPS)


def be_level(side: str, entry: float, offset_bps: float) -> float:
    f = offset_bps / 10000.0
    return entry * (1.0 + f) if side == "long" else entry * (1.0 - f)


def be_stop(side: str, entry: float, initial_stop: float, best: float | None, modes: ExitModes | None) -> float | None:
    """Basa-bas stop seviyesi (ulasildiysa) ya da None."""
    if modes is None or not modes.breakeven:
        return None
    if reached_r(side, entry, initial_stop, best, modes.be_trigger_r):
        return be_level(side, entry, modes.be_offset_bps)
    return None


def tighter(side: str, new: float, cur: float) -> bool:
    return new > cur + EPS if side == "long" else new < cur - EPS


def merge_stop(side: str, trail: float, be: float | None) -> float:
    """Iz suren stop ile basa-bas stopun siki olani."""
    if be is None:
        return trail
    return max(trail, be) if side == "long" else min(trail, be)


def partial_due(side: str, entry: float, initial_stop: float, best: float | None, modes: ExitModes | None) -> bool:
    if modes is None or not modes.partial:
        return False
    return reached_r(side, entry, initial_stop, best, modes.pt_trigger_r)


def best_extreme(side: str, highs: Sequence[float], lows: Sequence[float]) -> float | None:
    return _best(side, highs, lows)


def partial_qty(qty: float, frac: float, step: float, min_qty: float, min_notional: float, price: float) -> float | None:
    """Kismi kapanis adedi (adim tabanina yuvarlanir). Kapanan ya da kalan parca min adet/min notional altindaysa None
    (kismi atlanir, pozisyon tek parca surer)."""
    if not (qty > 0 and step > 0):
        return None
    q = math.floor(qty * frac / step + 1e-9) * step
    q = round(q, 12)
    rest = round(qty - q, 12)
    if q < min_qty - 1e-12 or rest < min_qty - 1e-12 or q <= 0:
        return None
    if price is not None and price > 0 and (q * price < min_notional or rest * price < min_notional):
        return None
    return q


def blend_exit(q1: float, p1: float, q2: float, p2: float) -> float:
    """Iki parcali cikisin adet agirlikli ortalama fiyati (defter tek cikis satiri: brut PnL tam eslesir)."""
    return (q1 * p1 + q2 * p2) / (q1 + q2)
