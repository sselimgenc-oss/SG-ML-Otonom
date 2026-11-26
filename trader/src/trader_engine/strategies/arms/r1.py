"""R1: yatay piyasa kenari (PA-YTY-02; mevcut kurulum). Sinyal `trader_core.signals` (donuk) ortak tablosundan R1 satirlari
secilerek gelir; yeni mantik yoktur."""
from __future__ import annotations

from . import ArmInput, mask_to_setups

SETUP = "R1"
TIMEFRAMES = ("1h", "4h", "1d")
CORE = True
EXIT_MODE = "target"
PRIORITY = 20
FEATURES = {"wick_ratio": "wick_ratio", "rr": "rr", "edge_dist_atr": "edge_dist_atr"}


def compute(inp: ArmInput):
    return mask_to_setups(inp.core(), (SETUP,))
