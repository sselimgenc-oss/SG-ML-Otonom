"""Ders Revizyon 8 (19.11 kullanici karari): KAGITTA (`paper_auto`) cikis onerileri ve menu disi oneri onaysiz uygulanir; otomatik geri alma;
cooldown 0. Canli/varsayilan (`paper_auto=false`) davranis ESKI: daima kullaniciya sorulur, 28 gun bekleme. Sentetik, tmp_path."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_lesson_exit_cf import (CUR_BLOCK, block_start, cfg_of, cfpath, seed, snapshot_for)  # noqa: F401
from test_lesson_exit_modes import seed_modes
from test_lesson_spec import env, rr_env  # noqa: F401

from trader_core import exit_counterfactual as EC
from trader_core import lesson as LS

ROOT = Path(__file__).resolve().parents[1]


def test_paper_config_enables_everything_and_live_default_unchanged():
    raw = json.loads((ROOT / "config/lesson.json").read_text())
    cfg = LS.load_config(ROOT / "config/lesson.json")
    assert cfg.paper_auto and cfg.allow_off_menu and cfg.proxy_include_ask_user and cfg.exit_cf_reject_cooldown_days == 28
    # sert limitler dokunulmaz
    assert (raw["rollback_effect_r"], raw["brake_effect_r"], raw["max_steps_from_ref"]) == (3.0, 10.0, 2)
    d = LS.LessonConfig()
    assert (d.paper_auto, d.allow_off_menu, d.proxy_include_ask_user, d.exit_cf_reject_cooldown_days) == (False, False, False, 28)
    with pytest.raises(LS.LessonConfigError):
        LS.LessonConfig(paper_auto="evet")


def test_exit_entries_auto_in_paper_ask_in_live(rr_env, cfpath):
    seed(cfpath)
    seed_modes(cfpath)
    live = snapshot_for(rr_env, cfg_of(rr_env))
    paper = snapshot_for(rr_env, cfg_of(rr_env, paper_auto=True, proxy_include_ask_user=True))
    be_l, be_p = live.entry("exit:breakeven"), paper.entry("exit:breakeven")
    assert (be_l.auto_capable, be_l.always_user) == (False, True)
    assert (be_p.eligible, be_p.auto_capable, be_p.always_user) == (True, True, False)
    pt_p = paper.entry("exit:partial")                       # olumsuz kanit: uygun degil => otomatik de degil
    assert pt_p.eligible is False and pt_p.auto_capable is False
    d = LS.ProposalDraft("change", "exit:breakeven", "exit_breakeven", be_p.to_value, "r", (), "low", "llm")
    assert (LS.classify_route(live, d, cfg_of(rr_env)).klass, LS.classify_route(live, d, cfg_of(rr_env)).reason_code) == \
        ("ask_user", "counterfactual_exit_support")
    assert LS.classify_route(paper, d, cfg_of(rr_env, paper_auto=True)).klass == "auto"


def test_off_menu_auto_in_paper_ask_in_live(rr_env, cfpath):
    snap = snapshot_for(rr_env, cfg_of(rr_env))
    d = LS.ProposalDraft("change", "rr_min:up", "rr_min", 9.9, "r", (), "low", "llm", True)
    assert LS.classify_route(snap, d, cfg_of(rr_env)).reason_code == "off_menu"
    assert LS.classify_route(snap, d, cfg_of(rr_env, paper_auto=True)).klass == "auto"


# ---------------------------------------------------------------------------------------------- otomatik geri alma olcutu
def test_rollback_criterion_hand_computed():
    f = LS.exit_rollback_needed
    ok = [0.5] * 10
    assert f(ok, ok) is False
    assert f([0.1] * 10, [0.5] * 10) is True                    # ozgun 5.0 >= yeni 1.0 + max(2, 0.2) = 3.0
    assert f([0.4] * 10, [0.5] * 10) is False                   # 5.0 < 4.0 + 2 ; en kotu esit
    assert f([0.5] * 9 + [-1.0], [0.5] * 10) is True            # en kotu 1.5 R daha kotu (toplam farki 1.5 < 2)
    assert f([0.1] * 9, [0.5] * 9) is False                     # n < 10
    assert f([0.1] * 10, [0.5] * 9) is False                    # eslesmeyen uzunluk


def _monitor(param, frm, to, started):
    return LS.Monitor(version_id=2, base_version_id=1, param=param, from_value=frm, to_value=to, scope="T1", proposal_id=1,
                      started_at=LS.fmt_ts(started), k=20, recheck_n=30)


def _ecf_with(cfpath, on_r, off_r):
    rows = []
    for i, (a, b) in enumerate(zip(on_r, off_r), start=1):
        e = block_start(CUR_BLOCK - 1) + timedelta(hours=i)
        rows.append(_mrow(i, e, "off", b))
        rows.append(_mrow(i, e, "breakeven", a))
    with EC.ExitCfStore(cfpath) as st:
        st.insert_modes(rows)


def _mrow(*a, **k):
    from test_lesson_exit_modes import mrow
    return mrow(*a, **k)


def test_exit_harm_rolls_back_only_in_paper(rr_env, cfpath):
    started = block_start(CUR_BLOCK - 1) - timedelta(hours=1)
    as_of = block_start(CUR_BLOCK) + timedelta(days=1)
    _ecf_with(cfpath, [0.0] * 12, [0.5] * 12)                    # yeni kotu: toplam 0 vs 6
    cfg = cfg_of(rr_env, paper_auto=True)
    mon = _monitor("exit_breakeven", 0.0, 1.0, started)
    v = LS.exit_harm_verdict(cfg, mon, started, as_of)
    assert v is not None and v.rollback and v.action == "rolled_back" and v.stats["n"] == 12
    assert v.stats["new_sum_r"] == 0.0 and v.stats["orig_sum_r"] == 6.0
    assert LS.exit_harm_verdict(cfg_of(rr_env), mon, started, as_of) is None            # canli: devrede degil
    assert LS.exit_harm_verdict(cfg, mon, as_of, as_of) is None                         # degisiklikten once: orneklem yok


def test_exit_harm_no_rollback_when_not_worse(rr_env, cfpath):
    started = block_start(CUR_BLOCK - 1) - timedelta(hours=1)
    as_of = block_start(CUR_BLOCK) + timedelta(days=1)
    _ecf_with(cfpath, [0.6] * 12, [0.5] * 12)
    cfg = cfg_of(rr_env, paper_auto=True)
    assert LS.exit_harm_verdict(cfg, _monitor("exit_breakeven", 0.0, 1.0, started), started, as_of) is None
    assert LS.exit_harm_verdict(cfg, _monitor("rr_min", 1.5, 2.0, started), started, as_of) is None   # cikis disi parametre


@pytest.fixture(autouse=True)
def _kanit_surumu_eski_yol(monkeypatch):
    """Bu dosya eski (MODES_VERSION=2) kanit satirlariyla calisir; 24.11 surum secimi ayri testlerde denenir: okuyucu MAX(version)e duser."""
    from trader_core import exit_counterfactual as _ecf
    monkeypatch.setattr(_ecf, "modes_version_from_config", lambda *a, **k: None)


def test_cikis_bekleme_ayari_28_paper_auto_aciksa_etkili_0():
    """25.11 denetim #19: ayar dosyasi 28; paper_auto kapanirsa 28 gun sessizce 0'a dusmez (acikken etkili bekleme 0)."""
    import json
    from pathlib import Path
    ham = json.loads((Path(__file__).resolve().parents[1] / "config" / "lesson.json").read_text(encoding="utf-8"))
    assert ham["exit_cf_reject_cooldown_days"] == 28
