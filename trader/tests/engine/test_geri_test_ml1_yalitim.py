"""P6-01: geri test (`--env paper`) kagit botun ML1 paketini OKUMAZ/YAZMAZ; paket yolu cikti dizinine tasinir, ogrenme kuru
(out_dir yoksa kapali). Kagit var/runtime dizinindeki paket dosyalari bayt ve mtime olarak degismez."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trader_engine import backtest as BT
from test_tutarlilik_env_backtest import END, START, ROOT, _write_store, make_config_dir

UTC = timezone.utc


def _sig(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns


@pytest.fixture
def rt(tmp_path, monkeypatch):
    d = tmp_path / "rt"
    (d / "ml1").mkdir(parents=True)
    monkeypatch.setenv("TRADER_ML_RUNTIME_DIR", str(d))
    for n in ("ml1_package.json", "ml1_package.son_iyi.json"):
        (d / "ml1" / n).write_bytes(b"NOBETCI-" + n.encode())
    return d


def test_build_config_paket_yolu_cikti_dizinine_ogrenme_kuru(tmp_path, rt):
    spec = BT.BacktestSpec(id="y", start=START, end=END, env="paper", config_dir=str(ROOT / "config"))
    out = tmp_path / "out"
    cfg = BT.BacktestRunner(spec).build_config(out)
    assert cfg.ml1["aktif"] is True
    yol = Path(cfg.ml1["paket_yolu"])
    assert out.resolve() in yol.parents and rt not in yol.parents
    assert cfg.ml1["ogrenme"]["kuru"] is True
    cfg0 = BT.BacktestRunner(spec).build_config(None)
    assert cfg0.ml1["ogrenme"]["aktif"] is False
    assert rt not in Path(cfg0.ml1["paket_yolu"]).parents and not Path(cfg0.ml1["paket_yolu"]).exists()


def test_kisa_calisma_kagit_paketine_dokunmaz(tmp_path, rt, monkeypatch):
    db = tmp_path / "market.sqlite"
    _write_store(db)
    cfgdir = make_config_dir(tmp_path)
    ov = json.loads((cfgdir / "engine.paper.json").read_text())
    ov["ml1"] = {"aktif": True, "ogrenme": {"aktif": True, "kuru": False, "min_islem": 200, "min_islem_tf": 0, "esik": 0.50}}
    (cfgdir / "engine.paper.json").write_text(json.dumps(ov))
    seen = {}

    class Yakala(BT.Engine):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            seen["eng"] = self
    monkeypatch.setattr(BT, "Engine", Yakala)
    before = {p.name: _sig(p) for p in (rt / "ml1").iterdir()}
    spec = BT.BacktestSpec(id="k", start=START, end=datetime(2026, 11, 5, 12, tzinfo=UTC), env="paper", source="store",
                           market_db=str(db), config_dir=str(cfgdir), out_root=str(tmp_path / "bt"))
    out = tmp_path / "bt" / "k"
    BT.BacktestRunner(spec).run_once(out)
    after = {p.name: _sig(p) for p in (rt / "ml1").iterdir()}
    assert after == before                                          # ayni bayt + mtime, yeni dosya yok
    assert sorted(p.name for p in rt.rglob("*") if p.is_file()) == sorted(before)
    eng = seen["eng"]
    assert eng.ml1 is not None and out.resolve() in eng.ml1._paths[0].parents
    assert eng.ogren is not None and eng.ogren.kuru is True


def test_varsayilan_yol_cli_da_ml1_yalitimli(tmp_path, rt):
    """Paket 2 / E: `--env`siz (varsayilan paper) CLI yolu da paketi cikti dizinine tasir, ogrenme kuru."""
    a = BT.build_parser().parse_args(["--id", "y2", "--period", "IS"])
    spec = BT.spec_from_args(a, [])
    assert spec.env == "paper"
    out = tmp_path / "out2"
    cfg = BT.BacktestRunner(spec).build_config(out)
    assert out.resolve() in Path(cfg.ml1["paket_yolu"]).parents and rt not in Path(cfg.ml1["paket_yolu"]).parents
    assert cfg.ml1["ogrenme"]["kuru"] is True
