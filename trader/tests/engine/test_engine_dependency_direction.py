"""08 §4.7: bağımlılık yönü (trader_core -> trader_engine yok; motor içi izinli kenarlar)."""
from __future__ import annotations

import ast
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = "src/trader_engine"
CORE = "src/trader_core"
CORE_ALLOWED = {"risk", "signals", "regime", "indicators", "ledger", "veto", "config_loader", "ml_package",
                "risk_ladder", "ban_store", "proc_guard", "universe", "arm_time", "pa_features", "exit_modes", "etiket_kurallari", "giris_izi", "kayip_freni"}   # 24.11 kullanici karari: formasyon_on_deger (saf, stdlib) yalniz gates.py
#   # 23.11 kullanici karari: asama B esikleri (kayip_freni: saf, stdlib; yalniz gates.py)   # M1 (DD-12 WP-14): pa_features (numpy-only) canli ozellik tanimi; trader_ml.pa_proposer.features geri-export eder   # DD-12 WP-13: arm_time (saf, stdlib) kurulum zaman dilimi/seans; bars.py ve arm_guard.py yeniden kullanir   # DD-12 WP-16: universe (saf, stdlib) yalniz config.py kagit kaplamasi   # DD-9: proc_guard (yalniz stdlib/ctypes; cli._cmd_run testnet/live)   # cikis kipleri (1b): exit_modes (saf, stdlib) basa-bas/kismi kar hesabi; motor (config.py, position_manager.py, engine.py) ve karsi-olgu oynatimi AYNI islevleri cagirir   # kademeli kucultme: kol_kucultme (saf, stdlib) yalniz gates.py; # haber etiketi: haber (saf, stdlib) yalniz kayit; gates.py/engine.py okur   # DD-7: yalniz stdlib'li ban dosyasi (ban_store); 12 (RK-1): kademe sabitleri/katlama; yalniz ladder.py (ve cli.py) kullanir
CORE_NAME_ALLOWED = {"config_loader": {"deep_merge"}}
LEAVES = {"types", "errors", "numeric", "clock", "bars", "fileio", "config", "holdout"}
# ALLOWED_EDGES: yaprak modüller yalnız birbirini içe aktarabilir (stdlib + izinli trader_core hariç).
ALLOWED_EDGES = {m: set(LEAVES) for m in LEAVES}
HIGH = {"engine", "gates", "strategy_runner"}
FORBIDDEN_EDGES = {   # grup -> yasak hedefler
    "marketdata": HIGH | {"state", "order_manager", "position_manager"},
    "brokers": HIGH | {"state", "order_manager", "position_manager"},
    "position_manager": HIGH, "order_manager": HIGH, "state": HIGH,
}


def _py(base: Path):
    for d, dirs, files in os.walk(base):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in sorted(files):
            if f.endswith(".py"):
                yield Path(d) / f


def _modname(base: Path, p: Path) -> str:
    rel = p.relative_to(base).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1] or ["__init__"]
    return ".".join(parts)


def _engine_edges(tree, cur: str) -> tuple[set[str], list[tuple[str, str]]]:
    """-> (trader_engine hedef modülleri (üst bileşen adı), [(trader_core modül, ad|'')])"""
    eng, core = set(), []
    pkg = cur.split(".")[:-1] if not cur.endswith("__init__") else cur.split(".")[:-1]
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                parts = a.name.split(".")
                if parts[0] == "trader_engine" and len(parts) > 1:
                    eng.add(".".join(parts[1:]))
                elif parts[0] == "trader_core":
                    core.append((parts[1] if len(parts) > 1 else "", ""))
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = pkg[:len(pkg) - (n.level - 1)] if n.level > 1 else pkg
                mod = ".".join(base + (n.module.split(".") if n.module else []))
                if n.module:
                    eng.add(mod)
                else:
                    eng.update(".".join(base + [a.name]) for a in n.names)
            else:
                parts = (n.module or "").split(".")
                if parts[0] == "trader_engine":
                    if len(parts) > 1:
                        eng.add(".".join(parts[1:]))
                    else:
                        eng.update(a.name for a in n.names)
                elif parts[0] == "trader_core":
                    if len(parts) > 1:
                        core += [(parts[1], a.name) for a in n.names]
                    else:
                        core += [(a.name, "") for a in n.names]
    return eng, core


def _imports_engine(tree) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name.split(".")[0] == "trader_engine" for a in n.names):
            return True
        if isinstance(n, ast.ImportFrom) and n.level == 0 and (n.module or "").split(".")[0] == "trader_engine":
            return True
    return False


def scan_direction(root: Path) -> list[str]:
    v = []
    cbase = Path(root) / CORE
    if cbase.exists():
        for p in _py(cbase):
            if _imports_engine(ast.parse(p.read_text(encoding="utf-8"))):
                v.append(f"{p.relative_to(root)}: trader_core imports trader_engine")
    ebase = Path(root) / ENGINE
    if not ebase.exists():
        return v
    for p in _py(ebase):
        cur = _modname(ebase, p)
        top = cur.split(".")[0]
        eng, core = _engine_edges(ast.parse(p.read_text(encoding="utf-8")), cur)
        targets = {t.split(".")[0] for t in eng} - {"trader_engine"}
        rel = str(p.relative_to(root))
        for m, name in core:
            if m not in CORE_ALLOWED:
                v.append(f"{rel}: trader_core.{m} not allowed")
            elif m in CORE_NAME_ALLOWED and name not in CORE_NAME_ALLOWED[m]:
                v.append(f"{rel}: trader_core.{m}.{name} not allowed")
            if name.startswith("_") or m.startswith("_"):
                v.append(f"{rel}: private trader_core name {m}.{name}")
        if cur in LEAVES:
            bad = targets - ALLOWED_EDGES[cur] - {cur}
            if bad:
                v.append(f"{rel}: leaf imports {sorted(bad)}")
        grp = top if top in FORBIDDEN_EDGES else None
        if grp:
            bad = targets & FORBIDDEN_EDGES[grp] - {cur}
            if bad:
                v.append(f"{rel}: {grp} must not import {sorted(bad)}")
    return v


def test_real_tree_direction():
    assert scan_direction(REPO) == []


def _w(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_scanner_boundaries(tmp_path):
    clean = tmp_path / "clean"
    _w(clean, f"{ENGINE}/types.py", "from trader_engine.errors import X\nimport json\n")
    _w(clean, f"{ENGINE}/config.py", "from trader_core.config_loader import deep_merge\nfrom .types import T\n")
    _w(clean, f"{ENGINE}/gates.py", "from trader_core import risk\nfrom trader_core.ledger import record\nfrom trader_engine.state import S\n")
    _w(clean, f"{ENGINE}/marketdata/feed.py", "from trader_engine.bars import tf_delta\nfrom ..types import Bar\n")
    _w(clean, f"{CORE}/risk.py", "import json\n")
    assert scan_direction(clean) == []
    cases = {
        f"{CORE}/x.py": "import trader_engine\n",
        f"{CORE}/y.py": "from trader_engine.types import Bar\n",
        f"{ENGINE}/a.py": "from trader_core.health import x\n",
        f"{ENGINE}/b.py": "from trader_core.budget import x\n",
        f"{ENGINE}/c.py": "from trader_core.ledger import _EXIT_REASONS\n",
        f"{ENGINE}/d.py": "from trader_core.config_loader import load_all\n",
        f"{ENGINE}/types.py": "from trader_engine.state import S\n",
        f"{ENGINE}/marketdata/feed.py": "from trader_engine.engine import Engine\n",
        f"{ENGINE}/brokers/paper.py": "from trader_engine import gates\n",
        f"{ENGINE}/state.py": "from trader_engine.strategy_runner import R\n",
        f"{ENGINE}/order_manager.py": "from .engine import E\n",
        f"{ENGINE}/bars.py": "from .marketdata.feed import F\n",
    }
    for i, (rel, code) in enumerate(cases.items()):
        root = tmp_path / f"bad{i}"
        _w(root, rel, code)
        assert scan_direction(root), (rel, code)
