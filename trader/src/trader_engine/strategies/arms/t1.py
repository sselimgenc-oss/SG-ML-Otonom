"""T1: trend ici geri cekilme (PA-TRD-01/05; mevcut kurulum). Sinyal `trader_core.signals` (donuk) ortak tablosundan T1
satirlari secilerek gelir; yeni mantik yoktur. 4s'de `price_action_v1_4h.py`nin yerel 4s hesabiyla ayni (tetik = 4s bar,
rejim = onceki kapanmis 4s); 1g'de tetik = 4s'den toplanan UTC gunu."""
from __future__ import annotations

from . import ArmInput, mask_to_setups

SETUP = "T1"
TIMEFRAMES = ("1h", "4h", "1d")
CORE = True
EXIT_MODE = "trail"
PRIORITY = 10
FEATURES = {"pullback_ema": "pullback_ema", "ema_value": "ema_value", "body_ratio": "body_ratio"}


def compute(inp: ArmInput):
    return mask_to_setups(inp.core(), (SETUP,))
