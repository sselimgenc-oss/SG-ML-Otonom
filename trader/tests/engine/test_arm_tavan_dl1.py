"""DL1: yapilandirmada `DL1: 4` = dort zaman dilimindeki TOPLAM (paper = live)."""
from __future__ import annotations

import json

from test_arm_tavan_toplam import ROOT, TFS, _dolu


def test_dl1_toplam_4_tum_zaman_dilimlerinde():
    for ad in ("engine.paper.json", "engine.live.json"):
        caps = json.loads((ROOT / "config" / ad).read_text())["arm_max_positions"]
        assert caps["DL1"] == 4, ad
        assert caps["default"] == 6, ad
    caps = {"default": 6, "DL1": 4}
    held = ["DL1@15m", "DL1@1h", "DL1@4h"]
    assert not _dolu(held, "DL1@1d", caps)
    held.append("DL1@1d")
    assert all(_dolu(held, f"DL1@{tf}", caps) for tf in TFS)
