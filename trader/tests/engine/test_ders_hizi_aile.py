"""24.11 kullanici karari: ders hizi / aile destegi (kol aç/kapa dersinde aile ortalamasi, alinsaydi temizligi, kartlar)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader_core import counterfactual as CF  # noqa: E402
from trader_core import lesson as LS  # noqa: E402
from trader_core import panel_pano as PP  # noqa: E402
import counterfactual_run as CR  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 20, tzinfo=UTC)


def c(hours, r, taken=True):
    return (T0 + timedelta(hours=hours), r, taken)


# ---- madde 1: aile yokken eski sonuc birebir -------------------------------------------------------------------------
@pytest.mark.parametrize("cands", [
    [], [c(0, -1.0)], [c(0, -1.0), c(30, -2.0, False)], [c(0, 1.0), c(25, 1.0), c(50, 1.0)],
    [c(i * 24, -0.5, i % 2 == 0) for i in range(6)],
])
@pytest.mark.parametrize("shrink", [0, 10])
def test_aile_yokken_eski_sonuc_birebir(cands, shrink):
    eski = LS.arm_lifecycle_step(None, cands, NOW, shrink_n=shrink)
    assert LS.arm_lifecycle_step(None, cands, NOW, shrink_n=shrink, aile_ort=None) == eski
    assert LS.arm_lifecycle_step(None, cands, NOW, shrink_n=shrink, aile_ort=0.0, cf_weight=1.0) [0]["state"] == eski[0]["state"]


def test_aile_karar_olcutu_formulu():
    # m = (toplam_kol + 10 * aile_ort) / (n_kol + 10): 3 gun x -0.3 = -0.9; aile -0.2 -> (-0.9 - 2.0)/13 = -0.2231
    cs = [c(0, -0.3), c(24, -0.3), c(48, -0.3)]
    st, ev = LS.arm_lifecycle_step(None, cs, NOW, shrink_n=10, aile_ort=-0.2)
    assert ev == "closed" and st["mean_r"] == pytest.approx(-2.9 / 13, abs=1e-4)
    # ayni kol ailesiz: -0.9/13 = -0.069 > -0.15 -> acik kalir
    assert LS.arm_lifecycle_step(None, cs, NOW, shrink_n=10)[1] is None


def test_yalniz_aile_verisiyle_kapanmaz():
    ailede = -1.0                                                  # cok kotu aile
    # kolun kendi adayi yok / 2 aday / 3 aday ama tek gun -> kapanmaz
    for cs in ([], [c(0, 0.0), c(1, 0.0)], [c(0, 0.0), c(1, 0.0), c(2, 0.0)]):
        st, ev = LS.arm_lifecycle_step(None, cs, NOW, shrink_n=10, aile_ort=ailede)
        assert ev is None and st["state"] == "open"
    # 3 aday, 3 ayri gun -> ozkanit yeterli, aile ile kapanir
    st, ev = LS.arm_lifecycle_step(None, [c(0, 0.0), c(24, 0.0), c(48, 0.0)], NOW, shrink_n=10, aile_ort=ailede)
    assert ev == "closed"


def test_geri_alma_siniri_degismez():
    prev = {"state": "closed", "epoch_start": NOW.isoformat(), "closed_at": NOW.isoformat()}
    post = [(NOW + timedelta(hours=k), 1.0, False) for k in (1, 2, 3)]
    st, ev = LS.arm_lifecycle_step(prev, post, NOW + timedelta(days=1))
    assert ev == "rolled_back"
    assert LS.arm_lifecycle_step.__kwdefaults__["rollback_r"] == 3.0


def test_alinmayan_aday_yarim_agirlik():
    # 2 alinan -1 + 2 alinmayan -1 (agirlik .5): toplam -3, n_w = 3 -> shrink 0: -1.0; agirliksiz de -1.0, ama n'li karisim fark eder
    cs = [c(0, -1.0), c(24, -1.0), c(48, 0.2, False), c(72, 0.2, False)]
    w, _ = LS.arm_lifecycle_step(None, cs, NOW, shrink_n=10, cf_weight=0.5)
    u, _ = LS.arm_lifecycle_step(None, cs, NOW, shrink_n=10, cf_weight=1.0)
    assert w["mean_r"] == pytest.approx((-2.0 + 0.2) / 13, abs=1e-4)
    assert u["mean_r"] == pytest.approx((-2.0 + 0.4) / 14, abs=1e-4)


def test_aile_ort_yardimcisi():
    cands = [{"arm_id": "R1@4h", "r": -1.0, "taken": True}, {"arm_id": "R1@4h", "r": -1.0, "taken": False},
             {"arm_id": "R1@1h", "r": -5.0, "taken": True}, {"arm_id": "T1@4h", "r": -9.0, "taken": True},
             {"arm_id": "R1@4h", "r": None, "taken": True}]
    # R1@1h icin aile: R1@4h -> -1 + .5*-1 = -1.5, n=1.5 -> -1.5/(1.5+10)
    assert CR._aile_ort(cands, "R1@1h", 10) == pytest.approx(-1.5 / 11.5)
    assert CR._aile_ort(cands, "T1@4h", 10) is None                # ailesi yok -> bugunku davranis


# ---- madde 3: alinsaydi temizligi ------------------------------------------------------------------------------------
def dec(i, ts, *, final="skipped", pair="ETH/USDT", side="long", tf="1h", arm="R1@1h"):
    return SimpleNamespace(id=i, pair=pair, side=side, setup="R1", trigger_tf=tf, bar_close_ts=ts, arm_id=arm,
                           skip_reason="entry_gate_closed" if final == "skipped" else None, final_action=final)


def test_tekillestirme_48_mum():
    ds = [dec(1, T0), dec(2, T0 + timedelta(hours=1)), dec(3, T0 + timedelta(hours=47)),
          dec(4, T0 + timedelta(hours=48)),                         # 48 mum sonra: yeni pencere
          dec(5, T0 + timedelta(hours=1), pair="BTC/USDT"),         # baska parite: ayri
          dec(6, T0 + timedelta(hours=1), side="short"),            # baska yon: ayri
          dec(7, T0 + timedelta(hours=1), arm="R1@4h", tf="4h")]    # baska kol: ayri
    cf = [{"decision_id": i, "hyp_r_net": 1.0} for i in range(1, 8)]
    out = CF.arm_candidates(decisions=ds, trades=[], cf_rows=cf, asset_class_of=lambda p: "kripto")
    assert sorted(x["decision_id"] for x in out) == [1, 4, 5, 6, 7]


def test_tekillestirme_4h_pencere_zd_ile_olceklenir():
    ds = [dec(1, T0, arm="R1@4h", tf="4h"), dec(2, T0 + timedelta(hours=100), arm="R1@4h", tf="4h"),
          dec(3, T0 + timedelta(hours=192), arm="R1@4h", tf="4h")]    # 48 x 4h = 192 sa
    out = CF.arm_candidates(decisions=ds, trades=[], cf_rows=[], asset_class_of=lambda p: "kripto")
    assert [x["decision_id"] for x in out] == [1, 3]


def _cf_depo(tmp_path, rows):
    st = CF.CounterfactualStore(tmp_path / "cf.sqlite")
    for did, method, r, ver in rows:
        st._db.execute(
            "INSERT INTO cf_outcomes (bot, decision_id, method, pair, side, setup, trigger_tf, skip_reason, decision_ts, "
            "planned_entry, planned_stop, window_start_ts, window_end_ts, hyp_r_net, exit_reason, computed_at, version, "
            "arm_id, asset_class) VALUES ('learner', ?, ?, 'ETH/USDT', 'long', 'R1', '1h', 'x', '2026-11-01T00:00:00Z', 100, 99, "
            "'2026-11-01T00:00:00Z', '2026-11-02T00:00:00Z', ?, 'stop', '2026-11-02T00:00:00Z', ?, 'R1@1h', 'kripto')",
            (did, method, r, ver))
    st._db.commit()
    st.close()
    return tmp_path / "cf.sqlite"


def test_arm_rows_plan_once_sonra_barrier(tmp_path):
    try:
        p = _cf_depo(tmp_path, [(1, "barrier", -1.0, 1), (1, "plan", 2.0, 2), (2, "barrier", 0.5, 1)])
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"cf_outcomes test satiri yazilamadi (sema degismis olabilir): {e}")
    r = {x["decision_id"]: x["hyp_r_net"] for x in CF.arm_rows(p, "learner")}
    assert r == {1: 2.0, 2: 0.5}                                   # 1 icin plan, 2 icin barrier
    assert {x["decision_id"]: x["hyp_r_net"] for x in CF.arm_rows(p, "learner", method="barrier")} == {1: -1.0, 2: 0.5}


# ---- madde 4/6: esikler ve geri alma degismedi --------------------------------------------------------------------------
def test_lesson_json_esikleri_degismedi():
    """24.11 kullanici karari: ders hizi / aile destegi - ders esikleri (lesson.json) AYNEN kalir."""
    doc = json.loads((Path(__file__).resolve().parents[2] / "config" / "lesson.json").read_text(encoding="utf-8"))
    assert (doc["min_affected"], doc["min_gap_r"], doc["min_z"], doc["min_distinct_days"]) == (8, 0.5, 1.64, 4)
    assert (doc["shrink_n"], doc["rollback_effect_r"], doc["brake_effect_r"]) == (10, 3.0, 10.0)
    assert (LS.ARM_CLOSE_R, LS.ARM_REOPEN_R) == (-0.15, 0.05)


# ---- madde 5: kartlar ---------------------------------------------------------------------------------------------------
def test_kol_dersleri_arms_off(tmp_path):
    LS.write_arms_state(tmp_path / "arms_off.json", {
        "R1@1h": {"state": "closed", "epoch_start": "2026-11-10T10:00:00+00:00", "closed_at": "2026-11-10T10:00:00+00:00",
                  "n": 4, "mean_r": -0.2, "last_event": "closed"},
        "T1@4h": {"state": "open", "epoch_start": "2026-11-15T10:00:00+00:00", "closed_at": None, "n": 2, "mean_r": 0.1,
                  "last_event": "reopened"},
        "M1@1h": {"state": "open", "epoch_start": None, "closed_at": None, "n": 0, "mean_r": None, "last_event": None}}, NOW)
    r = PP.kol_dersleri(str(tmp_path / "l.sqlite"))
    assert [(x["kol"], x["olay"]) for x in r] == [("T1@4h", "reopened"), ("R1@1h", "closed")]
    assert PP.kol_dersleri(str(tmp_path / "yok" / "l.sqlite")) == []


def _cp(stream, c_, mid, n_a, n_b, g, passed=False):
    return LS.CheckpointResult(stream, "rr_min", c_, "2026-11-20", "h", passed, "2026-11-27",
                               {mid: {"passed": passed, "fail_reasons": [], "stats": {"n_a": n_a, "n_b": n_b, "g": g}}})


def test_ders_ilerleme_en_yakin_aday():
    cfg = LS.load_config()
    assert LS.lesson_progress([], cfg) is None
    cps = [_cp("s1", 10, "rr_min:down", 1, 9, 1), _cp("s1", 20, "rr_min:down", 5, 9, 3),      # s1: son nokta 5/8, 3/4
           _cp("s2", 20, "vol_ratio_max:up", 2, 8, 2)]
    r = LS.lesson_progress(cps, cfg)
    assert (r["akis"], r["n"], r["n_hedef"], r["gun"], r["gun_hedef"]) == ("s1", 5, 8, 3, 4)


def test_kucultme_karti_aile_nedeni_ve_sifir_islemli_kol(tmp_path):
    from panel_support import mkledger
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    mkledger(str(tmp_path / "l.sqlite"), "learner", [(False, True, t0 + timedelta(hours=2 * i)) for i in range(5)])
    v = PP.kucultme_view(str(tmp_path / "l.sqlite"), "learner", arms=["R1@1h", "R1@4h", "T1@1h"], now=NOW)
    by = {r["kol"]: r for r in v["kollar"]}
    assert set(by) == {"R1@1h", "R1@4h"}                           # T1@1h ailesiz/islemsiz: kucultulmez
    assert by["R1@1h"]["aile"] is None and by["R1@1h"]["aile_nedeni"] is False and by["R1@1h"]["n"] == 5
    z = by["R1@4h"]                                                # hic islemi yok, aile (R1@1h) ekside
    assert z["n"] == 0 and z["aile"] < 0 and z["aile_nedeni"] is True and z["carpan"] == 0.5
    # motorla ayni pencere: aile 90 gunden eskiyse karta girmez
    v2 = PP.kucultme_view(str(tmp_path / "l.sqlite"), "learner", arms=["R1@4h"], now=NOW + timedelta(days=120))
    assert v2 is None or "R1@4h" not in {r["kol"] for r in v2["kollar"]}
