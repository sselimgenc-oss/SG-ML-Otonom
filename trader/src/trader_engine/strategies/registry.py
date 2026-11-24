"""Statik strateji kayit defteri (05 §13.2). Ad yalniz bu sozlukten cozulur; yapilandirma/CLI/ortam/ledger'dan gelen
hicbir dize modul yuklemek icin kullanilmaz."""
from __future__ import annotations

import re
from collections.abc import Mapping

from .base import ParamSpec, Strategy, StrategyError
from .lab import make_lab_ml
from .price_action_v1 import make_v1_full, make_v1b

__all__ = ["StrategyError", "list_strategies", "get_strategy", "parse_label", "make_label"]

_FACTORIES = {
    "price_action_v1": make_v1b,
    "price_action_v1_full": make_v1_full,
    "price_action_lab_ml": make_lab_ml,                    # DD-12 WP-11: cok kurulumlu bilesik strateji (kurulumlar arms/ paketinde)
}
_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")
_LABEL_RE = re.compile(r"strategy:([a-z][a-z0-9_]{0,39})@(\S+)")
DEFAULT_NAME = "price_action_v1"


def list_strategies() -> tuple[str, ...]:
    return tuple(_FACTORIES)


def get_strategy(name: str, *, mode: str | None = None, arms=None) -> Strategy:
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise StrategyError("bad_name", f"gecersiz strateji adi: {name!r}")
    f = _FACTORIES.get(name)
    if f is None:
        raise StrategyError("unknown_strategy", f"bilinmeyen strateji {name!r}; izinli: {list_strategies()}")
    s = f()
    if arms:
        if not hasattr(s, "set_arms"):
            raise StrategyError("arms_not_supported", f"{name} cok kurulumlu degil (arms={list(arms)!r})")
        s.set_arms(arms)
    if mode == "paper" and not s.info.paper_allowed:
        raise StrategyError("paper_not_allowed", f"{name} yalniz backtest/capraz dogrulama icindir")
    return s


def make_label(name: str, version: str) -> str:
    return f"strategy:{name}@{version}"


def parse_label(reason: str | None) -> tuple[str, str | None]:
    """param_versions.reason -> (ad, surum|None). Etiket yoksa eski varsayilan: price_action_v1."""
    m = _LABEL_RE.match(reason or "")
    if m is None:
        return DEFAULT_NAME, None
    return m.group(1), m.group(2)


def check_param_keys(strategy: Strategy, params: Mapping) -> None:
    want = {p.name for p in strategy.info.param_specs}
    if set(params) != want:
        raise StrategyError("ledger_incompatible",
                            f"parametre anahtarlari uyusmuyor: eksik={sorted(want - set(params))} fazla={sorted(set(params) - want)}")
