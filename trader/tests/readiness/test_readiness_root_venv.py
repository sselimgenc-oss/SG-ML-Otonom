"""Sunucu-benzeri ice aktarma testi: root sanal ortaminda (/usr/local/lib/trader-root/venv; yalniz requirements-root.lock paketleri)
calisan birimlerin betikleri, AST ile bulunan TUM ice aktarmalariyla (fonksiyon ici/try dahil; TYPE_CHECKING haric, depo kodu icinde
ozyinelemeli) yalniz stdlib + kilit dosyasi paketleri + depo kodu ile yuklenebilmeli. Kapsam: betigin KENDI fonksiyon ici ice aktarmalari takip edilir; diger depo modullerinde yalniz modul duzeyi
ice aktarmalar (fonksiyon ici tembel numpy/anthropic ice aktarmalari o fonksiyon cagrilmadikca calismaz). Gercek olay: health_run fonksiyon ici
ice aktarma ile numpy'a uzandi, sunucuda 5 dakikada bir ModuleNotFoundError verdi."""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from readiness_support import DEPLOY, ROOT

ROOT_PY = "/usr/local/lib/trader-root/venv/bin/python"
SRC, SCRIPTS = ROOT / "src", ROOT / "scripts"


def root_scripts() -> list[str]:
    out = set()
    for unit in sorted(DEPLOY.glob("*.service")):
        for line in unit.read_text(encoding="utf-8").splitlines():
            if line.startswith("ExecStart=") and ROOT_PY in line:
                m = re.search(r"/current/scripts/(\w+\.py)", line)
                if m:
                    out.add(m.group(1))
    return sorted(out)


def allowed_third_party() -> set[str]:
    names = set()
    for line in (DEPLOY / "requirements-root.lock").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9_.-]+)==", line)
        if m:
            names.add(m.group(1).lower().replace("-", "_"))
    return names


def _repo_file(dotted: str) -> Path | None:
    """Noktali ad -> depo dosyasi (paket ise __init__.py); depo kodu degilse None."""
    parts = dotted.split(".")
    for base in (SRC, SCRIPTS):
        p = base.joinpath(*parts)
        if (p / "__init__.py").is_file():
            return p / "__init__.py"
        if p.with_suffix(".py").is_file():
            return p.with_suffix(".py")
    return None


def _dotted_of(path: Path) -> str:
    base = SRC if SRC in path.parents else SCRIPTS
    parts = list(path.relative_to(base).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


class _Collect(ast.NodeVisitor):
    def __init__(self, pkg: str, ic_dahil: bool):
        self.pkg, self.names, self.ic_dahil = pkg, set(), ic_dahil   # ic_dahil: fonksiyon ici ice aktarmalar da (yalniz betigin kendisi)

    def visit_FunctionDef(self, node):
        if self.ic_dahil:
            self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node):
        t = node.test
        if (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"):
            for n in node.orelse:
                self.visit(n)
            return
        self.generic_visit(node)

    def visit_Import(self, node):
        self.names.update(a.name for a in node.names)

    def visit_ImportFrom(self, node):
        if node.level:
            base = self.pkg.split(".")
            base = base[:len(base) - (node.level - 1)] if node.level > 1 else base
            mod = ".".join(base + ([node.module] if node.module else []))
        else:
            mod = node.module or ""
        if mod:
            self.names.add(mod)
        for a in node.names:
            if a.name != "*" and mod and _repo_file(f"{mod}.{a.name}"):
                self.names.add(f"{mod}.{a.name}")


def closure(script: str) -> tuple[set[str], set[str], dict[str, str]]:
    """(depo modulleri, dis modul adlari, modul -> ilk iceri alan). Ust paketlerin __init__ dosyalari da dahil."""
    repo, external, todo, via = set(), set(), [SCRIPTS / script], {}
    seen: set[Path] = set()
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        dotted = _dotted_of(f)
        pkg = dotted if f.name == "__init__.py" else dotted.rpartition(".")[0]
        c = _Collect(pkg, f.parent == SCRIPTS)
        c.visit(ast.parse(f.read_text(encoding="utf-8")))
        for name in sorted(c.names):
            via.setdefault(name, dotted)
            target = _repo_file(name)
            if target is None:
                external.add(name)
                continue
            parts = name.split(".")
            for i in range(1, len(parts) + 1):        # ust paketler (calistirilan __init__ dosyalari)
                pf = _repo_file(".".join(parts[:i]))
                if pf:
                    via.setdefault(".".join(parts[:i]), dotted)
                    todo.append(pf)
        if f.parent != SCRIPTS:
            repo.add(dotted)
    return repo, external, via


CHILD = textwrap.dedent("""
    import sys, json, importlib, runpy
    cfg = json.loads(sys.argv[1])
    sys.path[:0] = [cfg["src"], cfg["scripts"]]
    allowed = set(cfg["allowed"]) | set(sys.stdlib_module_names) | set(cfg["repo_top"])

    class Blok:
        def find_spec(self, name, path=None, target=None):
            if "." not in name and name not in allowed and not name.startswith("_sysconfigdata"):
                raise ModuleNotFoundError("No module named %r (root venv'de yok)" % name, name=name)
            return None
    sys.meta_path.insert(0, Blok())
    bad = []
    runpy.run_path(cfg["script_path"], run_name="root_venv_test")      # betigin modul duzeyi ice aktarmalari
    for m in cfg["modules"]:
        try:
            importlib.import_module(m)
        except Exception as e:
            if type(e).__name__ == "ZoneInfoNotFoundError":     # tzdata yok (ortam); modul sorunu degil
                continue
            bad.append([m, type(e).__name__ + ": " + str(e)])
    print(json.dumps(bad))
""")


def run_child(script_path: Path, repo: set[str], external: set[str]) -> list:
    repo_top = {p.name for p in SRC.iterdir() if p.is_dir()} | {p.stem for p in SCRIPTS.glob("*.py")}
    cfg = {"src": str(SRC), "scripts": str(SCRIPTS), "allowed": sorted(allowed_third_party()), "repo_top": sorted(repo_top),
           "script_path": str(script_path), "modules": sorted(repo) + sorted(external)}
    r = subprocess.run([sys.executable, "-I", "-c", CHILD, json.dumps(cfg)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return [[script_path.name, (r.stderr.strip().splitlines() or ["?"])[-1]]]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_root_scripts_discovered():
    s = root_scripts()
    assert s and "health_run.py" in s, s


def test_root_scripts_import_with_root_venv_packages_only():
    problems = []
    for script in root_scripts():
        repo, external, via = closure(script)
        for mod, err in run_child(SCRIPTS / script, repo, external):
            problems.append(f"{script}: {mod} (iceri alan: {via.get(mod)}): {err}")
    assert not problems, "root venv'de yuklenemeyen ice aktarmalar:\n" + "\n".join(problems)
