"""25.11 denetim #16: ortak ayar dosyasi yerine esitlik testi. Kagit ve canli ayar dosyalarinda kol/kume/risk/cikis/masraf/tavan
bloklari birebir ayni olmali ("kagit = canli")."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONFIG = Path(__file__).resolve().parents[2] / "config"
ORTAK = ("arms", "arm_max_positions", "arm_family_max_positions", "clusters", "risk", "exit_modes", "cost_overrides", "max_positions")


def _oku(ad):
    return json.loads((CONFIG / ad).read_text(encoding="utf-8"))


@pytest.mark.parametrize("anahtar", ORTAK)
def test_kagit_ve_canli_ortak_blok_birebir_ayni(anahtar):
    p, c = _oku("engine.paper.json"), _oku("engine.live.json")
    assert anahtar in p and anahtar in c, anahtar
    assert p[anahtar] == c[anahtar], anahtar
