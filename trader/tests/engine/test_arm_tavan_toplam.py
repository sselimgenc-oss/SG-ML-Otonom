"""Arm tavani kapsami: zaman dilimsiz kurulum anahtari (`M1`: 4) TUM zaman dilimlerinin toplamidir; `default` ve `X@tf`
anahtarlari kurulum x zaman dilimi basinadir."""
from __future__ import annotations

import json
from datetime import timedelta

from trader_engine import arm_guard as AG

import test_dd12_wp11_spec as W
from test_dd12_wp11_spec import ROOT

TFS = ("15m", "1h", "4h", "1d")


def _dolu(held, aid, caps):
    setup = aid.split("@")[0]
    return AG.arm_full(held, aid, AG.arm_cap(caps, aid, setup), AG.arm_cap_is_setup_total(caps, aid, setup))


def test_m1_toplam_4_tum_zaman_dilimlerinde():
    caps = {"default": 6, "M1": 4, "L1": 4}
    held = ["M1@15m", "M1@1h", "M1@4h"]
    assert not _dolu(held, "M1@1d", caps)                         # 3 acik: dorduncu girer
    held.append("M1@1d")
    for tf in TFS:                                                # 4 acik (4 farkli tf): hicbir tf'te yeni M1 girmez
        assert _dolu(held, f"M1@{tf}", caps), tf
    assert not _dolu(held, "L1@1h", caps)                         # baska kurulum etkilenmez


def test_m1_toplam_tek_tfde_de_4():
    caps = {"default": 6, "M1": 4}
    assert not _dolu(["M1@1h"] * 3, "M1@1h", caps) and _dolu(["M1@1h"] * 4, "M1@1h", caps)
    assert _dolu(["M1@1h"] * 4, "M1@15m", caps)                   # eskiden 15m ayri sayilirdi


def test_varsayilan_6_kurulum_x_tf_basina():
    caps = {"default": 6, "M1": 4}
    t15, t1h = ["T1@15m"] * 6, ["T1@1h"] * 6
    assert not _dolu(t15[:5], "T1@15m", caps)
    assert _dolu(t15, "T1@15m", caps)
    assert not _dolu(t15, "T1@1h", caps)                          # T1@15m 6 iken T1@1h hala girer
    assert not _dolu(t15 + t1h[:5], "T1@1h", caps)
    assert _dolu(t15 + t1h, "T1@1h", caps) and _dolu(t15 + t1h, "T1@15m", caps)   # ikisi birden 6+6 acik


def test_acik_arm_anahtari_tf_basina_kalir():
    caps = {"default": 6, "M1": 4, "M1@1h": 2}
    assert _dolu(["M1@1h"] * 2, "M1@1h", caps)
    assert not _dolu(["M1@1h"] * 2, "M1@4h", caps)                # M1@4h kurulum anahtarina (toplam 4) duser
    assert not AG.arm_cap_is_setup_total(caps, "M1@1h", "M1")
    assert AG.arm_cap_is_setup_total(caps, "M1@4h", "M1")


def test_tavan_yoksa_dolu_degil():
    assert not AG.arm_full(["M1@1h"] * 9, "M1@1h", None, True)
    assert not AG.arm_cap_is_setup_total({}, "M1@1h", "M1")


def test_yapilandirma_degerleri_beklenen():
    for ad in ("engine.paper.json", "engine.live.json"):          # paper ve live ayni tavanlar
        caps = json.loads((ROOT / "config" / ad).read_text())["arm_max_positions"]
        assert caps == {"default": 6, "M1": 4, "MF1-*": 3, **{f"{a}-*": 3 for a in ("T1", "R1", "TF1", "B1", "H2", "S1", "F1")}, "GF1-*": 3, "IN1-*": 3, "PA2-*": 3}, ad  # 24.11 kullanici karari: formasyon kutuphanesi (MF1-* 3)


def test_motor_m1_toplam_tavani_farkli_tflerde(tmp_path):
    pairs = W.PAIRS5
    over = W._engine_over(pairs, arms=["M1@1h", "M1@4h"], arm_max_positions={"M1": 2})
    e = W._E(tmp_path, pairs, W.D_E - timedelta(hours=1), over)
    try:
        D = W.D_E
        yonler = (("long", "M1@1h"), ("short", "M1@4h"), ("long", "M1@1h"), ("short", "M1@4h"))
        for p, (yon, arm) in zip(pairs[:4], yonler):
            kw = {} if yon == "long" else {"side": "short", "planned_stop": 102.0, "regime": "trend_down"}
            W._signal_arm(e, D, p, arm, setup="M1", **kw)
        e.decide(D)
        e.step(D)
        acik = [p for p in pairs[:4] if e.state.position_for_pair(p) is not None]
        assert len(acik) == 2, acik                                # per-tf sayilsaydi 4 acilirdi
        red = [p for p in pairs[:4] if p not in acik][0]
        rows = W._ledger_rows(e, f"SELECT final_action, skip_reason, veto_reason FROM decision_events WHERE pair='{red}'")
        assert rows[-1][0] == "skipped" and rows[-1][1] == "max_positions" and "arm_cap:M1@" in rows[-1][2], rows
    finally:
        e.close()
