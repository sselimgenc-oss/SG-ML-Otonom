"""WP-06b: LLM butce paylasimi (18 Kasim 2026 eki): veto payi yok; haftalik_ozet + lesson."""
import json
from pathlib import Path

import pytest

from trader_core import budget as B

ROOT = Path(__file__).resolve().parents[2]


def _cfg():
    return json.loads((ROOT / "config" / "budget.json").read_text())


def test_services_no_veto():
    assert B.SERVICES == ("haftalik_ozet", "lesson", "haber_kolu", "yorumcu")   # 23.11 ust lig: haber kolu + yorumcu


def test_config_json_no_veto_entries():
    d = _cfg()
    for k in ("daily_cap_usd", "api_key_env", "reservation_ttl_s"):
        assert set(d[k]) == {"haftalik_ozet", "lesson", "haber_kolu", "yorumcu"}
    assert set(d["retry"]["deadline_s"]) == {"haftalik_ozet", "lesson", "haber_kolu", "yorumcu"}
    assert "veto" not in json.dumps(d).lower()
    assert d["monthly_cap_usd"] == 20.0 and d["prepaid_credit_usd"] == 10.0   # 23.11 kullanici karari: aylik tavan 20 $


def test_config_loads_and_caps():
    cfg = B.load_config(ROOT / "config" / "budget.json")
    assert cfg.cap_micro("haftalik_ozet") == 250_000
    assert cfg.cap_micro("lesson") == 100_000


def test_veto_service_rejected_cleanly(tmp_path):
    d = _cfg()
    d["db_path"] = str(tmp_path / "b.sqlite")
    p = tmp_path / "budget.json"
    p.write_text(json.dumps(d))
    g = B.BudgetGuard(B.load_config(p))
    with pytest.raises(ValueError):
        g.authorize("veto", 0.01)
    assert not isinstance(g.authorize("haftalik_ozet", 0.01), B.Denial)


def test_old_veto_config_invalid():
    d = _cfg()
    d["daily_cap_usd"] = {"veto": 0.25, "lesson": 0.10}
    with pytest.raises(B.BudgetConfigError):
        B.BudgetConfig(**d)
