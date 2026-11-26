"""Mounted research statistics (PSR/DSR, PBO/CSCV, Holm, stationary bootstrap, purged/CPCV splits).

Adapted from Aurum v2 (MIT); see THIRD_PARTY_NOTICES.md. numpy/pandas only. Not wired into any
decision path: used for research cross-checks and the ML phase.
"""
from . import splits, stats
from .splits import *  # noqa: F401,F403
from .stats import *  # noqa: F401,F403

__all__ = list(stats.__all__) + list(splits.__all__)
