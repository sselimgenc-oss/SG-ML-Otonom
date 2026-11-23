"""08 §4.3: trader_engine içinde risk sabiti tanımlamak yasak (tek risk seti: trader_core.risk.LOCKED_CFG)."""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE = "src/trader_engine"
RISK_NAME = re.compile(r"max_trade_risk|target_trade_risk|daily_max_loss|max_open_risk|max_same_dir_risk|max_leverage|min_leverage|"
                       r"liq_safety|maint_margin|max_notional|fee_rate|slippage_rate|risk_per_trade|leverage")
RISK_NAME_ALLOW = {("types.py", "leverage"), ("types.py", "qty")}   # yalnız tür açıklaması (değersiz alan); sayısal varsayılan her zaman ihlal (değersiz alan zaten taranmaz)
RISK_FUNCS = {"trader_core.risk.check_entry": ("cfg", 2), "trader_core.risk.size_position": ("cfg", 5),
              "trader_core.risk.loss_at_stop": ("cfg", 3)}
MMR_FUNC = ("trader_core.risk.liquidation_price", "mmr", 3)


def _aliases(tree):
    m = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                m[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            for a in n.names:
                m[a.asname or a.name] = f"{n.module}.{a.name}"
    return m


def _dotted(node, al):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(al.get(node.id, node.id))
        return ".".join(reversed(parts))
    return None


def _is_num(v) -> bool:
    if isinstance(v, ast.UnaryOp) and isinstance(v.op, (ast.USub, ast.UAdd)):
        return _is_num(v.operand)
    if isinstance(v, ast.Call):   # field(default=<num>) / field(default_factory=lambda: <num>)
        return any(k.arg == "default" and _is_num(k.value) for k in v.keywords)
    return isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) and not isinstance(v.value, bool)


def _tname(t):
    if isinstance(t, ast.Name):
        return t.id
    if isinstance(t, ast.Attribute):
        return t.attr
    if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and isinstance(t.slice.value, str):
        return t.slice.value
    return None


def _ends_locked(node) -> bool:
    # `cfg.risk_config` = LOCKED_CFG'nin yalniz target_trade_risk'i daha SIKI kopyasi (config.build_risk_config ->
    # trader_core.risk.tightened; gevsek => ConfigError). Motor RiskConfig kurmaz/replace etmez (asagidaki tarama).
    return ((isinstance(node, ast.Name) and node.id == "LOCKED_CFG") or (isinstance(node, ast.Attribute) and node.attr in ("LOCKED_CFG", "risk_config")))


def _mmr_ok(node) -> bool:
    return isinstance(node, ast.Attribute) and (node.attr == "mmr" or (node.attr == "maint_margin_rate" and _ends_locked(node.value)))


def _arg(call: ast.Call, kw: str, idx: int):
    for k in call.keywords:
        if k.arg == kw:
            return k.value
    return call.args[idx] if len(call.args) > idx else None


def scan_risk(root: Path) -> list[str]:
    v = []
    base = Path(root) / ENGINE
    if base.exists():
        for d, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for f in sorted(files):
                if f.endswith(".py"):
                    v += _scan_file(Path(d) / f, f)
    cfgdir = Path(root) / "config"
    for p in sorted(cfgdir.glob("engine*.json")) if cfgdir.exists() else []:
        def walk(o):
            if isinstance(o, dict):
                for k, x in o.items():
                    if k == "target_trade_risk" and p.name == "engine.base.json":
                        continue      # tek izinli ayar: yalniz LOCKED_CFG'den SIKI olabilir (config.build_risk_config, fail-closed)
                    if p.name in ("engine.paper.json", "engine.live.json") and k in ("target_trade_risk", "risk", "max_open_risk", "max_same_dir_risk", "daily_max_loss"):
                        continue      # DD-12 WP-01 (§4.1): kagit katmani; risk.PAPER_LIMITS icinde (config.build_paper_risk_config, fail-closed)
                        # 23.11 kullanici karari: canli = kagit; engine.live.json ayni anahtarlari risk.LIVE_LIMITS icinde tasir (fail-closed)
                    if RISK_NAME.search(str(k).lower()):
                        v.append(f"{p.name}: key {k}")
                    walk(x)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(json.loads(p.read_text(encoding="utf-8")))
    return v


def _scan_file(path: Path, fname: str) -> list[str]:
    v = []
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    al = _aliases(tree)
    lines = src.splitlines()

    def add(n, why):
        v.append(f"{fname}:{n.lineno}:{lines[n.lineno - 1].strip()[:80]} [{why}]")

    def name_hit(n, name, value):
        if name and RISK_NAME.search(name.lower()) and value is not None and _is_num(value):
            add(n, f"risk constant {name}")

    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                name_hit(n, _tname(t), n.value)
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            name_hit(n, _tname(n.target), n.value)
        elif isinstance(n, ast.Dict):
            for k, val in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    name_hit(k, k.value, val)
        elif isinstance(n, ast.Call):
            for k in n.keywords:
                name_hit(n, k.arg, k.value)
            fn = _dotted(n.func, al) or ""
            if fn.endswith("RiskConfig"):
                add(n, "RiskConfig constructor")
            if fn in ("dataclasses.replace", "replace") and n.args:
                a0 = n.args[0]
                txt = ast.unparse(a0)
                if "LOCKED_CFG" in txt or "RiskConfig" in txt:
                    add(n, "replace(RiskConfig)")
            if fn in RISK_FUNCS:
                kw, idx = RISK_FUNCS[fn]
                a = _arg(n, kw, idx)
                if a is not None and not _ends_locked(a):
                    add(n, f"{fn.split('.')[-1]} cfg must be LOCKED_CFG")
            if fn == MMR_FUNC[0]:
                a = _arg(n, MMR_FUNC[1], MMR_FUNC[2])
                if a is not None and not _mmr_ok(a):
                    add(n, "liquidation_price mmr must be LOCKED_CFG.maint_margin_rate or PaperConfig.mmr")
        if isinstance(n, ast.ImportFrom) and any(a.name == "HARD_LIMITS" for a in n.names):
            add(n, "HARD_LIMITS import")
        if (isinstance(n, ast.Name) and n.id == "HARD_LIMITS") or (isinstance(n, ast.Attribute) and n.attr == "HARD_LIMITS"):
            add(n, "HARD_LIMITS use")
    return v


def test_real_tree_has_no_risk_constants():
    assert scan_risk(REPO) == []


def _w(root, rel, text):
    p = Path(root) / ENGINE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_scanner_boundaries(tmp_path):
    clean = tmp_path / "clean"
    _w(clean, "types.py", "from dataclasses import dataclass\n@dataclass\nclass X:\n    leverage: int | None\n    qty: float = 0.0\n")
    _w(clean, "gates.py", "import trader_core.risk as K\nfrom trader_core.risk import LOCKED_CFG\nlev = LOCKED_CFG.min_leverage\n"
                          "K.check_entry(s, c)\nK.check_entry(s, c, K.LOCKED_CFG)\nK.size_position(1, 2, 3, 'long', 3, cfg=LOCKED_CFG)\n"
                          "K.liquidation_price(1, 'long', 3, LOCKED_CFG.maint_margin_rate)\nK.liquidation_price(1, 'long', 3, mmr=cfg.mmr)\n"
                          "taker_fee = 0.0005\n")
    assert scan_risk(clean) == []
    bad = {
        "gates.py": "max_leverage = 5\n",
        "a.py": "x = {'daily_max_loss': 0.05}\n",
        "b.py": "import trader_core.risk as K\nK.check_entry(s, c, K.RiskConfig(max_trade_risk=0.03))\n",
        "c.py": "import trader_core.risk as K\nK.check_entry(s, c, my_cfg)\n",
        "d.py": "from trader_core.risk import HARD_LIMITS\n",
        "e.py": "import dataclasses\nx = dataclasses.replace(LOCKED_CFG, fee_rate=1)\n",
        "f.py": "import trader_core.risk as K\nK.liquidation_price(1, 'long', 3, 0.005)\n",
        "g.py": "def f(leverage=3): pass\nf(leverage=3)\n",
        "types.py": "from dataclasses import dataclass\n@dataclass\nclass X:\n    leverage: int = 3\n",
    }
    for rel, code in bad.items():
        root = tmp_path / ("bad_" + rel.replace(".", "_"))
        _w(root, rel, code)
        if rel == "g.py":   # yalnız çağrıdaki sayısal anahtar sözcük
            assert scan_risk(root)
            continue
        assert scan_risk(root), rel
    # yapıcı + alan adı = iki ihlal
    root = tmp_path / "two"
    _w(root, "b.py", bad["b.py"])
    assert len(scan_risk(root)) >= 2
    # JSON anahtarı
    root = tmp_path / "json"
    (root / "config").mkdir(parents=True)
    (root / "config" / "engine_x.json").write_text('{"a": {"max_leverage": 3}}')
    assert scan_risk(root)
