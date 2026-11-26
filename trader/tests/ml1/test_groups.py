"""Fikir gruplari: config'teki TUM kural kollari kapsanir (162), 18 grup, 55 kurulum, M1/DL1/HB1 haric."""
from __future__ import annotations

import json
from collections import Counter

from evren_destek import GRUP_SAYISI, KALDIRILAN_KURULUM, KOL_SAYISI, KURULUM_SAYISI
from trader_engine.strategies import arms as A
from trader_ml.ml1 import groups as G


def test_tum_kural_kollari_kapsanir():
    ids = G.rule_arm_ids()
    assert len(ids) == len(set(ids)) == 162
    assert all(G.family(a) not in ("M1", "DL1", "HB1") for a in ids)
    eksik = sorted({G.split_arm_id(a)[0] for a in ids} - set(G.GRUPLAR))
    assert not eksik, eksik
    for a in ids:
        assert G.group(a) in G.GRUP_ADLARI


def test_config_disi_kural_kolu_yok_ve_discover_ile_ayni_kume():
    """26.11: 16 kurulum config'ten ve gruplardan cikarildi; modulleri yerinde kalir => discover() = gruplar + kaldirilanlar."""
    kurulumlar = {s for s in A.discover() if G.family(s) not in G.DISLANAN_AILELER}
    assert kurulumlar == set(G.GRUPLAR) | set(KALDIRILAN_KURULUM) and not (set(G.GRUPLAR) & set(KALDIRILAN_KURULUM))
    assert {G.split_arm_id(a)[0] for a in G.rule_arm_ids()} == set(G.GRUPLAR)


def test_onsekiz_grup_55_kurulum():
    assert len(G.GRUP_ADLARI) == GRUP_SAYISI == 18 and len(set(G.GRUP_ADLARI)) == 18
    assert "CANDLE_STAR3" not in G.GRUP_ADLARI and "EXHAUSTION" not in G.GRUP_ADLARI   # tum uyeleri kaldirildi: grup da yok
    assert len(G.GRUPLAR) == KURULUM_SAYISI == 55
    assert all(n > 0 for n in Counter(G.GRUPLAR.values()).values())
    assert set(G.GRUPLAR.values()) == set(G.GRUP_ADLARI)


def test_family_ve_group_yardimcilari():
    assert G.family("MF1-YUTAN@1h") == "MF1" and G.family("T1@4h") == "T1" and G.family("IN1-RSI") == "IN1"
    assert G.group("IN1-RSI@1h") == "OSC_REVERSAL" and G.group("T1@1d") == "PULLBACK_1LEG" and G.group("PA2-FVG") == "SD_ZONE"
    assert G.split_arm_id("GF1-KANAL@4h") == ("GF1-KANAL", "4h")


def test_config_kol_sayilari():
    cfg = json.loads(G.CONFIG_YOLU.read_text(encoding="utf-8"))
    assert all(not a.endswith("@15m") for a in cfg["arms"])           # 26.11: giris zaman dilimleri 1h/4h/1d
    assert len(cfg["arms"]) == len(G.rule_arm_ids()) == KOL_SAYISI        # M1 x4 25.11de kaldirildi: ayardaki tum kollar kural kolu
