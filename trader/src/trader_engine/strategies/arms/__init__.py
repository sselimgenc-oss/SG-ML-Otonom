"""DD-12 WP-11: kurulum (arm) paketi. Her kurulum bu klasorde TEK dosyadir (`t1.py`, `r1.py`; sonra `tf1.py`, `b1.py`,
`f1.py`, `s1.py`, `m1.py` ...) ve baska hicbir kayit dosyasina dokunulmaz: `find_arm(ad)` kurulumu paket klasorunu tarayarak
bulur. Yapilandirma/CLI/ortamdan gelen dize modul yuklemek icin KULLANILMAZ (registry.py kurali): yalniz bu paketin kendi
dosyalari kesfedilir (`pkgutil`), gelen ad bu kesfedilmis sozlukte aranir.

Kurulum dosyasi sozlesmesi (modul seviyesi):
  SETUP: str                   kurulum kodu (`T1`, `R1` ...; buyuk harf/rakam, 2-8)
  TIMEFRAMES: tuple[str, ...]  desteklenen zaman dilimleri (alt kume: 15m, 1h, 4h, 1d)
  CORE: bool                   True: sinyali `signals.compute_signals` ortak tablosundan satir secerek verir (T1/R1); lab bu
                               kurulumlarin tablosunu zaman dilimi basina TEK hesapla toplu uretir
  compute(inp: ArmInput) -> DataFrame   SIGNAL_COLUMNS sutunlu, `inp.trig.index` indeksli tablo; kurulumun olmayan satirlarinda signal=False
  EXIT_MODE: str               "trail" (iz suren stop + rejim cikisi; T1 yolu) | "target" (hedef + zaman durdurma; R1 yolu);
                               position_manager cikisi bu kipe gore secer (kurulum adina gore degil) (DD-12 WP-12a, K-7 madde 1)
  FEATURES: dict[str, str]     defter ozellik anahtari -> tasiyici sutun (CARRIERS); en fazla 6; gates._features okur (WP-12a, K-7 madde 2)
  PRIORITY: int                ayni zaman dilimindeki cakismada kucuk olan kazanir (T1 10, R1 20, TF1 30, B1 40, H2 50, S1 60, F1 70; M1 90)
Kurulum kimligi `arm_id = <KURULUM>@<zaman dilimi>`."""
from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import ModuleType

import pandas as pd

from ...bars import ARM_TFS

_SETUP_RE = re.compile(r"[A-Z][A-Z0-9]{1,7}")
EXIT_MODES = ("trail", "target")
# tasiyici sutunlar (SIGNAL_COLUMNS icinde, sayisal ya da tamsayi); ortak anahtarlar (atr_tf, stop_dist_atr, atr_4h,
# rh_touches, rl_touches) gates'te her zaman yazilir ve burada tasiyici olamaz (rejim anlami tasir)
CARRIERS = ("ema_value", "body_ratio", "wick_ratio", "edge_dist_atr", "rr", "pullback_ema")
_RESERVED_FEATURE_KEYS = ("atr_tf", "stop_dist_atr", "atr_4h", "rh_touches", "rl_touches")
MAX_FEATURES = 6
_ARM_ID_RE = re.compile(r"([A-Z][A-Z0-9]{1,7})@(15m|1h|4h|1d)")
_OFF_PREFIX = "lab:arm_off|"


class ArmError(ValueError):
    """Bilinmeyen kurulum / gecersiz kimlik / desteklenmeyen zaman dilimi."""


@dataclass
class ArmInput:
    pair: str
    tf: str
    D: datetime
    trig: pd.DataFrame                     # tf OHLCV (kapanmis barlar; son bar = D - tf)
    h4: pd.DataFrame                       # 4s OHLCV (rejim kaynagi)
    params: object                         # SignalParams
    core_fn: Callable[[], pd.DataFrame]    # ortak compute_signals tablosu (lazy; lab zaman dilimi basina bir kez hesaplar)

    def core(self) -> pd.DataFrame:
        return self.core_fn()


def mask_to_setups(core: pd.DataFrame, setups: Sequence[str]) -> pd.DataFrame:
    """Ortak tablodaki `setups` disi kurulum satirlarini adaylikdan cikarir (signal=False, skip_reason=None). Girdiyi degistirmez."""
    off = core["setup"].notna() & ~core["setup"].isin(list(setups))
    if not bool(off.any()):
        return core
    out = core.copy()
    out.loc[off, "signal"] = False
    out.loc[off, "skip_reason"] = None
    out.loc[off, "reasons"] = _OFF_PREFIX + out.loc[off, "reasons"].astype(str)
    return out


def make_arm_id(setup: str, tf: str) -> str:
    return f"{setup}@{tf}"


def parse_arm_id(arm_id: str) -> tuple[str, str]:
    m = _ARM_ID_RE.fullmatch(arm_id) if isinstance(arm_id, str) else None
    if m is None:
        raise ArmError(f"gecersiz arm_id: {arm_id!r} (bicim <KURULUM>@<15m|1h|4h|1d>)")
    return m.group(1), m.group(2)


_CACHE: dict[str, ModuleType] | None = None


def discover(refresh: bool = False) -> dict[str, ModuleType]:
    """Paket klasorundeki kurulum dosyalari: {SETUP: modul}. `_` ile baslayan dosyalar yok sayilir."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE
    found: dict[str, ModuleType] = {}
    for info in pkgutil.iter_modules(__path__):                # type: ignore[name-defined]  # noqa: F821
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        setup = getattr(mod, "SETUP", None)
        if not isinstance(setup, str) or not _SETUP_RE.fullmatch(setup):
            raise ArmError(f"{info.name}.py: SETUP gecersiz: {setup!r}")
        tfs = getattr(mod, "TIMEFRAMES", None)
        if not tfs or any(t not in ARM_TFS for t in tfs) or not callable(getattr(mod, "compute", None)):
            raise ArmError(f"{info.name}.py: TIMEFRAMES/compute sozlesmeye uymuyor")
        validate_arm(mod, info.name)
        if setup in found:
            raise ArmError(f"yinelenen kurulum kodu: {setup}")
        found[setup] = mod
    _CACHE = found
    return found


def validate_arm(mod: ModuleType, name: str = "?") -> None:
    """WP-12a sozlesme alanlari: EXIT_MODE (zorunlu, ONC-3), PRIORITY (tamsayi), FEATURES (<= 6, tasiyici sutun)."""
    mode = getattr(mod, "EXIT_MODE", None)
    if mode not in EXIT_MODES:
        raise ArmError(f"{name}.py: EXIT_MODE gecersiz: {mode!r} (trail | target)")
    prio = getattr(mod, "PRIORITY", None)
    if not isinstance(prio, int) or isinstance(prio, bool):
        raise ArmError(f"{name}.py: PRIORITY tamsayi olmali: {prio!r}")
    feats = getattr(mod, "FEATURES", None)
    if not isinstance(feats, dict) or len(feats) > MAX_FEATURES:
        raise ArmError(f"{name}.py: FEATURES sozluk olmali (en fazla {MAX_FEATURES})")
    for k, v in feats.items():
        if not isinstance(k, str) or not k or k in _RESERVED_FEATURE_KEYS:
            raise ArmError(f"{name}.py: FEATURES anahtari gecersiz: {k!r}")
        if v not in CARRIERS:
            raise ArmError(f"{name}.py: FEATURES tasiyicisi gecersiz: {v!r} (bilinenler: {CARRIERS})")


def exit_mode(setup: str) -> str | None:
    """Kurulumun cikis kipi; bilinmeyen kurulum None (position_manager: force_exit)."""
    mod = discover().get(setup) if isinstance(setup, str) else None
    return None if mod is None else mod.EXIT_MODE


def features_of(setup: str) -> dict[str, str]:
    """Kurulumun defter ozellik eslemesi {defter_anahtari: tasiyici}; bilinmeyen kurulum: {}."""
    mod = discover().get(setup) if isinstance(setup, str) else None
    return {} if mod is None else dict(mod.FEATURES)


def priority_of(setup: str | None) -> int:
    """Siralama onceligi (kucuk once); bilinmeyen/None kurulum en sona."""
    mod = discover().get(setup) if isinstance(setup, str) else None
    return 1000 if mod is None else int(mod.PRIORITY)


def find_arm(setup: str) -> ModuleType:
    """Kurulumu ad (kod) ile bulur; yoksa ArmError."""
    mods = discover()
    if not isinstance(setup, str) or setup not in mods:
        raise ArmError(f"bilinmeyen kurulum {setup!r}; bulunanlar: {sorted(mods)}")
    return mods[setup]


def list_arms() -> tuple[str, ...]:
    return tuple(sorted(discover()))
