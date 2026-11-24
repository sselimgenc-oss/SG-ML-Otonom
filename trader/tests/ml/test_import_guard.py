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


def test_engine_and_core_do_not_import_trader_ml():
    for pkg in ("trader_engine", "trader_core"):
        bad = [f for f, i in _scan(pkg).items() if "trader_ml" in i]
        assert not bad, bad


def test_model_evaluator_is_numpy_only():
    """Motor tarafi degerlendirici ve paket okuyucu trader_ml'e bagimli olmaz; yalniz stdlib + numpy."""
    imps = _imports(SRC / "trader_core" / "ml_eval.py")
    assert imps <= {"__future__", "numpy"}, imps
    pkg = _imports(SRC / "trader_core" / "ml_package.py")
    assert pkg <= {"__future__", "hashlib", "json", "re", "dataclasses", "datetime", "pathlib", "numpy"}, pkg


def test_engine_imports_only_core_for_ml():
    """Motor ML icin yalniz trader_core.ml_* kullanir (trader_ml'e hic dokunmaz)."""
    for f, imps in _scan("trader_engine").items():
        assert "trader_ml" not in imps, f


def test_no_ml_training_libraries_anywhere_in_runtime_dependencies():
    d = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = " ".join(d["project"]["dependencies"]).lower()
    opt = " ".join(x for v in d["project"].get("optional-dependencies", {}).values() for x in v).lower()
    for lib in ("lightgbm", "scikit-learn", "sklearn", "scipy"):
        assert lib not in deps and lib not in opt
    assert not (ROOT / "requirements-ml.txt").exists()
    assert not [f for f, i in _scan("trader_ml").items() if i & FORBIDDEN]
