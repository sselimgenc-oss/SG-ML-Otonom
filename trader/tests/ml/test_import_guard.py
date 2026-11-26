"""trader_engine ve trader_core lightgbm/sklearn/scipy ice aktarmaz; motor yoluna ML kutuphanesi girmez."""
import ast
import tomllib
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
ROOT = SRC.parent
FORBIDDEN = {"lightgbm", "sklearn", "scipy", "xgboost", "catboost", "torch"}


def _imports(py: Path) -> set[str]:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            out.add(n.module.split(".")[0])
    return out


def _scan(pkg: str) -> dict[str, set[str]]:
    return {str(p.relative_to(SRC)): _imports(p) for p in (SRC / pkg).rglob("*.py")}


def test_engine_and_core_never_import_ml_libs():
    for pkg in ("trader_engine", "trader_core"):
        files = _scan(pkg)
        assert files, pkg
        bad = {f: i & FORBIDDEN for f, i in files.items() if i & FORBIDDEN}
        assert not bad, bad


# 25.11 ML1 kagit kapisi: motorun trader_ml'e TEK izinli kopru (yalniz trader_ml.ml1 ozellik/model islevleri; egitim kodu cevrimdisidir)
ML1_KOPRU = "trader_engine/ml1_gate.py"
ML1_KOPRULER = (ML1_KOPRU, "trader_engine/ml1_ogren.py")    # ogrenici de yalniz trader_ml.ml1.* (model/features/groups) kullanir


def _ml1_only(py: Path) -> bool:
    tree = ast.parse(py.read_text(encoding="utf-8"))
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module and n.module.split(".")[0] == "trader_ml"]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names if a.name.split(".")[0] == "trader_ml"]
    return bool(mods) and all(m == "trader_ml.ml1" or m.startswith("trader_ml.ml1.") for m in mods)


def test_engine_and_core_do_not_import_trader_ml():
    for pkg in ("trader_engine", "trader_core"):
        bad = [f for f, i in _scan(pkg).items() if "trader_ml" in i and f not in ML1_KOPRULER]
        assert not bad, bad
    for k in ML1_KOPRULER:
        assert _ml1_only(SRC / k)                                      # kopruler yalniz trader_ml.ml1.* ice aktarir


def test_ml_package_is_minimal_stdlib_only():
    """26.11 sahip karari (olu kod): ml_eval.py ve PackageSet/tohum zinciri kaldirildi; ml_package yalniz canon/sha256_text, stdlib."""
    assert not (SRC / "trader_core" / "ml_eval.py").exists()
    pkg = _imports(SRC / "trader_core" / "ml_package.py")
    assert pkg <= {"__future__", "hashlib", "json"}, pkg
    import trader_core.ml_package as mp
    for ad in ("PackageSet", "view_from_package", "load_package"):
        assert not hasattr(mp, ad), ad


def test_engine_imports_only_core_for_ml():
    """Motor ML icin yalniz trader_core.ml_* kullanir (trader_ml'e hic dokunmaz)."""
    for f, imps in _scan("trader_engine").items():
        assert "trader_ml" not in imps or f in ML1_KOPRULER, f


def test_no_ml_training_libraries_anywhere_in_runtime_dependencies():
    d = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = " ".join(d["project"]["dependencies"]).lower()
    opt = " ".join(x for v in d["project"].get("optional-dependencies", {}).values() for x in v).lower()
    for lib in ("lightgbm", "scikit-learn", "sklearn", "scipy"):
        assert lib not in deps and lib not in opt
    assert not (ROOT / "requirements-ml.txt").exists()
    assert not [f for f, i in _scan("trader_ml").items() if i & FORBIDDEN]
