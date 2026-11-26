"""Yayin birimi (User=trader, ReadOnlyPaths=/opt/trader) okumalari: butce depo `mode=ro`, health state.json okunabilir.
Root altinda chmod/salt okunur baglama uygulanamaz; kod yolu (URI mode=ro, yazma yok) dogrulanir."""
from __future__ import annotations

import os
import stat
import sys
import sqlite3

import pytest

from panel_support import Env
from readiness_support import ROOT

sys.path.insert(0, str(ROOT / "scripts"))


def test_budget_guard_read_only_never_writes(tmp_path, monkeypatch):
    from trader_core import budget as B
    env = Env(tmp_path, learner=False, health=False)
    cfg = B.load_config(env.root / "config/budget.json")
    db = env.root / "user_data/budget.sqlite"
    before = db.read_bytes()
    real = sqlite3.connect
    seen = []

    def spy(target, *a, **k):
        seen.append(str(target))
        return real(target, *a, **k)
    monkeypatch.setattr(sqlite3, "connect", spy)
    g = B.BudgetGuard(cfg, read_only=True)
    st = g.status()
    assert st.store_ok and st.config_ok
    assert seen and all(t.startswith("file:") and t.endswith("?mode=ro") for t in seen), seen
    assert db.read_bytes() == before                        # last_ts / pragma yazimi yok
    with pytest.raises(B._StoreFail):
        g._run(lambda c, n: None, write=True)               # yazma yolu kapali


def test_budget_ro_missing_store_is_unavailable_not_created(tmp_path):
    from trader_core import budget as B
    env = Env(tmp_path, learner=False, health=False)
    cfg = B.load_config(env.root / "config/budget.json")
    db = env.root / "user_data/budget.sqlite"
    db.unlink()
    st = B.BudgetGuard(cfg, read_only=True).status()
    assert not st.store_ok and not db.exists()


def test_panel_budget_view_uses_read_only_guard(tmp_path, monkeypatch):
    from trader_core import budget as B, panel_data as P
    env = Env(tmp_path, learner=False, health=False)
    kinds = []
    orig = B.BudgetGuard.__init__

    def init(self, *a, **k):
        kinds.append(k.get("read_only"))
        orig(self, *a, **k)
    monkeypatch.setattr(B.BudgetGuard, "__init__", init)
    out = P.budget_view(str(env.root / "config/budget.json"))
    assert kinds == [True] and "services" in out


def test_health_state_world_readable_after_save(tmp_path):
    import health_run as R
    old = os.umask(0o007)                                   # trader-health.service: UMask=0007
    try:
        p = tmp_path / "state.json"
        R.save_state(str(p), {"a": 1})
    finally:
        os.umask(old)
    assert stat.S_IMODE(p.stat().st_mode) & 0o004           # User=trader (grup/sahip degil) okuyabilmeli


def test_health_unit_state_dir_mode_explicit():
    from readiness_support import DEPLOY
    t = (DEPLOY / "trader-health.service").read_text(encoding="utf-8")
    assert "StateDirectoryMode=0755" in t
