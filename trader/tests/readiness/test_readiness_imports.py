"""Hazirlik 2: install.sh'in kurdugu paket kumesi (requests pandas numpy pyarrow anthropic + gecisli bagimliliklari) her birim giris
noktasini calistirmaya yeter mi? Her giris noktasi AYRI `python -I` surecinde ice aktarilir; yuklenen ucuncu parti moduller
bildirilen bagimlilik kapanisinin disina cikarsa (ya da ML/gelistirme paketi yuklenirse) test kirilir."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import textwrap

import pytest

from readiness_support import ROOT, install_text

# giris noktasi -> (betik/modul, ek tembel ice aktarmalar: calisma sirasinda fonksiyon icinde yuklenenler)
ENTRIES = {
    "engine": ("module:trader_engine.cli", ["trader_engine.engine", "trader_engine.strategies.registry", "trader_core.ledger",
                                            "trader_core.signals", "trader_core.regime", "trader_engine.brokers", "requests"]),
    "feed": ("module:trader_engine.marketdata.feed", ["trader_engine.marketdata.rest_public", "requests"]),
    "panel": ("module:trader_panel.__main__", ["trader_panel.server", "trader_panel.data", "trader_panel.snapshot"]),
    "health": ("script:scripts/health_run.py", ["trader_core.ledger", "trader_core.market_probe", "trader_core.telegram",
                                                "health_backup", "requests"]),
    "lesson": ("script:scripts/lesson_run.py", ["trader_core.lesson", "trader_core.budget", "anthropic"]),
    "telegram": ("script:scripts/telegram_run.py", ["trader_core.telegram", "requests"]),
    "telegram-report": ("script:scripts/telegram_run.py", ["trader_core.telegram"]),
    "counterfactual": ("script:scripts/counterfactual_run.py", ["trader_core.counterfactual", "trader_core.ledger"]),
    "exit-counterfactual": ("script:scripts/exit_counterfactual_run.py", ["trader_core.exit_counterfactual", "trader_core.ledger", "trader_core.signals",
                                                                         "trader_core.regime", "trader_engine.holdout"]),
    "backup": ("script:scripts/health_backup.py", []),
    "mutabakat": ("script:scripts/mutabakat_run.py", ["trader_core.mutabakat", "trader_core.ledger", "trader_core.panel_pano",
                                                       "trader_panel.data", "trader_core.telegram"]),
    "strateji-veri": ("script:scripts/strateji_veri_run.py", ["trader_core.strateji_veri", "trader_core.ledger", "trader_core.telegram",
                                                              "trader_panel.data", "requests"]),
    "tutarlilik": ("script:scripts/tutarlilik_run.py", ["trader_engine.backtest", "trader_engine.config", "trader_engine.holdout",
                                                         "trader_engine.marketdata.store", "trader_core.ledger"]),
}
FORBIDDEN = ["scipy", "sklearn", "lightgbm", "yaml", "pytest", "matplotlib", "joblib", "numba", "websockets", "ccxt",
             "freqtrade", "trader_ml", "torch"]

PROBE = textwrap.dedent("""
    import sys, json, runpy, importlib
    from importlib import metadata
    sys.path.insert(0, {src!r})                   # PYTHONPATH=<repo>/src (birimler: Environment=PYTHONPATH / betik sys.path.insert)
    kind, target = {entry!r}.split(":", 1)
    if kind == "module":
        importlib.import_module(target)
    else:
        sys.path.insert(0, {scripts!r})
        runpy.run_path({root!r} + "/" + target, run_name="not_main")
    for m in {lazy!r}:
        importlib.import_module(m)
    # ---- bildirilen bagimlilik kapanisi (install.sh paketleri + gecisli Requires-Dist; 'extra' kosullulari atlanir)
    seen, todo = set(), set({declared!r})
    while todo:
        d = todo.pop()
        key = d.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        try:
            reqs = metadata.requires(d) or []
        except metadata.PackageNotFoundError:
            continue
        for r in reqs:
            if "extra ==" in r:
                continue
            name = r.split(";")[0].strip()
            name = name.split("[")[0]
            for ch in "<>=!~ (":
                name = name.split(ch)[0]
            todo.add(name)
    allowed = set()
    for top, dists in metadata.packages_distributions().items():
        if any(x.lower().replace("_", "-") in seen for x in dists):
            allowed.add(top)
    std = set(sys.stdlib_module_names)
    third = sorted({{n.split(".")[0] for n in sys.modules}} - std - {{"__main__", "__mp_main__", "cython_runtime", "sitecustomize", "usercustomize"}})
    local = ("trader_core", "trader_engine", "trader_panel", "trader_ml", "health_backup", "health_run")
    extra = [n for n in third if n not in allowed and not n.startswith("_") and n not in local]
    print(json.dumps({{"third": third, "outside_declared": extra, "ml_loaded": [n for n in {forbidden!r} if n in sys.modules]}}))
""")


def _declared() -> list[str]:
    t = install_text()
    code = re.sub(r"#.*", "", t)
    assert re.search(r'pip install[^\n]*\\\n\s*--require-hashes -r "\$TRADER_DIR/requirements\.lock"', code), \
        "install.sh requirements.lock'u --require-hashes ile kurmuyor"
    lock = (ROOT / "requirements.lock").read_text()
    m = re.search(r"^# Dogrudan:\s*(.+)$", lock, re.M)
    assert m, "requirements.lock 'Dogrudan' basligi yok"
    return m.group(1).split()


def test_install_declares_expected_runtime_packages():
    d = _declared()
    assert set(d) == {"requests", "pandas", "numpy", "pyarrow", "anthropic"}, d
    txt = install_text()
    assert "requirements-ml" not in re.sub(r"#.*", "", txt)             # ML kumesi (requirements-ml.txt) 24.11 kullanici karariyla silindi; sunucuya kurulmaz


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_entrypoint_imports_only_declared_packages(name):
    entry, lazy = ENTRIES[name]
    code = PROBE.format(src=str(ROOT / "src"), scripts=str(ROOT / "scripts"), root=str(ROOT), entry=entry, lazy=lazy,
                        declared=_declared(), forbidden=FORBIDDEN)
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd="/", timeout=120)
    assert r.returncode == 0, (name, r.stderr[-800:])
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert not out["ml_loaded"], f"{name}: ML/gelistirme paketi yuklendi: {out['ml_loaded']}"
    assert not out["outside_declared"], f"{name}: install.sh'in kurmadigi paket(ler) ice aktarildi: {out['outside_declared']}"
