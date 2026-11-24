"""Ders servisi x cikis kipleri kaniti (docs/cikis-kipleri-spec.md 7; docs/ders-spec.md Revizyon 7).

`exit:breakeven` / `exit:partial`: `trail_atr:up` kalibi (kanit-yalniz girdi): kanit yoksa girdi yok ve her sey bit duzeyinde eski;
`eligible` yalniz hukum `supports_change`; asla otomatik; daima kullaniciya sorulur; ret sonrasi 28 gun. Fikstur: test_lesson_exit_cf."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from test_lesson_exit_cf import (AS_OF, CUR_BLOCK, UTC, block_start, cfg_of, cfpath, seed, snapshot_for)  # noqa: F401
from test_lesson_spec import RUN_DAY, env, rr_env  # noqa: F401

from trader_core import exit_counterfactual as EC
from trader_core import exit_modes as XM
from trader_core import lesson as LS

COST = {"taker_fee": 0.0, "slip_exit_bps": 0.0, "slip_stop_bps": 0.0}


def mrow(tid, entry, variant, net, *, source="paper", censored=0, fired=False):
    from exit_cf_support import trade
    tr = trade(trade_id=tid, entry_ts=entry, exit_ts=entry + timedelta(days=2), source=source, actual_net_r=None)
    rr = EC.ReplayResult("ok", "trail_stop", EC.to_ms(entry) + 3_600_000, 100.0, 1, 1.0, censored=censored)
    if fired:
        rr.partial_ms, rr.partial_price, rr.partial_frac = EC.to_ms(entry) + 1_800_000, 102.0, 0.5
    return EC._mrow(tr, "learner", variant, 3.0, entry + timedelta(days=4), "last", COST, EC.to_ms(entry),
                    EC.to_ms(entry + timedelta(days=4)), {"gross_r": net, "fee_r": 0.0, "funding_r": 0.0, "net_r": net},
                    "trail_stop", rr)


def seed_modes(path, *, gain_be=0.3, gain_pt=-0.3, noise=0.05, blocks=range(CUR_BLOCK - 8, CUR_BLOCK), per_block=5):
    rows = []
    i = 0
    for b in blocks:
        for k in range(per_block):
            i += 1
            e = block_start(b) + timedelta(days=k, hours=12)
            base = 0.1 * ((i % 5) - 2)
            wob = noise * ((i % 7) - 3)
            rows.append(mrow(i, e, "off", base))
            rows.append(mrow(i, e, "breakeven", base + gain_be + wob))
            rows.append(mrow(i, e, "partial", base + gain_pt - wob, fired=True))
    with EC.ExitCfStore(path) as st:
        st.insert_modes(rows)
    return path


# ---------------------------------------------------------------------------------------------- kanit yok => bit duzeyinde eski
def test_no_mode_evidence_is_bit_identical(rr_env, cfpath):
    cfg = cfg_of(rr_env)
    seed(cfpath)                                                                   # yalniz v1 kaniti
    a = snapshot_for(rr_env, cfg)
    assert a.cf_exit is not None and "modes" not in a.cf_exit
    assert a.entry("exit:breakeven") is None and a.entry("exit:partial") is None
    assert not any(k.startswith("cfx.exit_") for k in a.facts)
    assert "cfx_mode" not in LS.render_prompt(a, cfg).user
    assert LS.exit_modes_cf_line(a.cf_exit) is None
    # v1 depo + bos ecf_modes tablosu (gece isi calisti, satir yok) ayni
    with EC.ExitCfStore(cfpath) as st:
        st.insert_modes([])
    assert snapshot_for(rr_env, cfg).stats_hash == a.stats_hash


def test_modes_only_evidence_without_trail_rows(rr_env, cfpath):
    seed_modes(cfpath)
    snap = snapshot_for(rr_env, cfg_of(rr_env))
    assert snap.cf_exit["by_alt"] == {} and snap.cf_exit["modes"]["by_mode"]["breakeven"]["n"] == 40
    assert snap.entry("trail_atr:up") is None
    assert LS.exit_cf_line(snap.cf_exit) == "Çıkış denemesi: henüz hesaplanmadı"


# ---------------------------------------------------------------------------------------------- menu girdileri
def test_supported_mode_entries_shape_and_route(rr_env, cfpath):
    seed(cfpath)                                                                   # parite (v1) tamam
    seed_modes(cfpath)
    cfg = cfg_of(rr_env)
    snap = snapshot_for(rr_env, cfg)
    be, pt = snap.entry("exit:breakeven"), snap.entry("exit:partial")
    assert be.param == "exit_breakeven" and pt.param == "exit_partial"
    assert (be.evidence_class, be.semantics, be.eligible, be.auto_capable, be.always_user) == ("exit_cf_only", "reshape", True, False, True)
    assert (be.from_value, be.to_value, be.direction, be.scope, be.checkpoint_c) == (0.0, 1.0, "up", "T1", None)
    assert be.stream == "exit_breakeven|exit_cf" and be.extra["cf_exit_n"] == 40 and be.extra["cf_exit_support"] == 1
    assert be.extra["cf_exit_n_eff"] == 20.0
    assert pt.eligible is False and "exit_cf_against_change" in pt.fail_reasons and pt.extra["cf_exit_support"] == 0   # kismi olumsuz
    assert snap.cf_exit["modes"]["by_mode"]["partial"]["fired_share"] == 1.0
    assert snap.facts["cfx.exit_breakeven.on.n"] == 40 and snap.facts["menu.exit:breakeven.cf_exit_n"] == 40
    for m in snap.menu:
        if m.menu_id.startswith("exit:"):
            assert not m.auto_capable
    assert all(k in snap.facts for k in LS._required_cites(be))
    # tur gidis-donus
    back = LS.Snapshot.from_dict(json.loads(json.dumps(snap.to_dict())))
    assert back.cf_exit == snap.cf_exit and back.core_dict() == snap.core_dict()
    # yonlendirme: daima kullaniciya sor
    d = LS.ProposalDraft("change", "exit:breakeven", "exit_breakeven", be.to_value, "r", (), "low", "llm")
    r = LS.classify_route(snap, d, cfg)
    assert (r.klass, r.reason_code) == ("ask_user", "counterfactual_exit_support")
    # istem + satir
    user = LS.render_prompt(snap, cfg).user
    assert "cfx_mode mode=breakeven n=40" in user and "verdict=supports_change" in user and "weight=0.5" in user
    assert LS.SYSTEM_PROMPT.count("cfx_mode") == 0
    line = LS.exit_modes_cf_line(snap.cf_exit)
    assert line.startswith("Çıkış kipleri denemesi (son 120 gün, varsayımsal; gerçek dolum yok): başa-baş stopu (n=40)")
    assert "kısmi kâr alma (n=40)" in line and line.endswith("kipi açmak için sana sorulur") and "\n" not in line


def test_degraded_parity_blocks_mode_support(rr_env, cfpath):
    seed(cfpath, parity=0.5)
    seed_modes(cfpath)
    snap = snapshot_for(rr_env, cfg_of(rr_env))
    be = snap.entry("exit:breakeven")
    assert be.eligible is False and "exit_cf_degraded" in be.fail_reasons and be.extra["cf_exit_support"] == 0


def test_insufficient_data_means_not_eligible(rr_env, cfpath):
    seed(cfpath)
    seed_modes(cfpath, blocks=range(CUR_BLOCK - 3, CUR_BLOCK))
    be = snapshot_for(rr_env, cfg_of(rr_env)).entry("exit:breakeven")
    assert be.eligible is False and any(f.startswith("exit_cf_insufficient") for f in be.fail_reasons)


def test_entry_absent_when_mode_already_on(rr_env, cfpath):
    seed(cfpath)
    seed_modes(cfpath)
    cfg = cfg_of(rr_env)
    snap = snapshot_for(rr_env, cfg)
    cf = snap.cf_exit
    out = LS._exit_mode_entries(cf, {"exit_breakeven": 1.0, "exit_partial": 0.0}, {}, None, None, cfg, AS_OF)
    assert [m.menu_id for m in out] == ["exit:partial"]                               # acik kip icin girdi yok


def test_blacklist_blocks_and_cooldown_override_covers_modes(rr_env, cfpath):
    seed(cfpath)
    seed_modes(cfpath)
    snap = LS.build_snapshot(rr_env.ro(), cfg_of(rr_env), RUN_DAY, blacklist={("exit_breakeven", "up"): LS.fmt_ts(AS_OF + timedelta(days=5))})
    be = snap.entry("exit:breakeven")
    assert be.eligible is False and "blacklisted" in be.fail_reasons
    import inspect
    assert "CF_MODE_PARAM" in inspect.getsource(LS.LessonService._blacklist_with_cooldown)       # ret sonrasi 28 gun (modlar dahil)


def test_modes_missing_table_in_v1_store_is_none(rr_env, cfpath):
    seed(cfpath)
    import sqlite3
    c = sqlite3.connect(cfpath)
    c.execute("DROP TABLE ecf_modes")
    c.commit()
    c.close()
    snap = snapshot_for(rr_env, cfg_of(rr_env))
    assert snap.cf_exit is not None and "modes" not in snap.cf_exit


def test_apply_path_opens_mode_through_ledger_param(tmp_path):
    """Kullanici onayi sonrasi uygulama yolu (mevcut ders yolu): defter istege bagli parametresi 0 -> 1 (yeni surum); onaysiz
    (`needs_user`) uygulanmaz; eski surum parametreleri/ozeti degismez; motor bayragi etkin surumden okunur."""
    from datetime import datetime, timezone

    from exit_cf_support import PARAMS, mk_t1_ledger
    from trader_core import ledger as L
    path = tmp_path / "l.sqlite"
    base = datetime(2025, 1, 2, tzinfo=timezone.utc)
    mk_t1_ledger(path, [(base + timedelta(hours=i), base + timedelta(days=1, hours=i), 105.0, "trail_stop", "1h")
                        for i in range(3)])
    led = L.open_ledger(str(path), "learner", clock=lambda: datetime(2025, 6, 1, tzinfo=timezone.utc), min_evidence_trades=0, paper_lesson=True)
    try:
        v0 = led.get_active_params()
        assert "exit_breakeven" not in v0.params                                   # eski surum: yokluk = varsayilan 0
        assert L.PARAM_DEFAULTS["exit_breakeven"] == 0 and L.LESSON_STEP["exit_partial"] == 1
        assert L.LESSON_SCOPE["exit_breakeven"] == ("T1",) and tuple(L.LESSON_BOUNDS_DEFAULT["exit_partial"]) == (0, 1)
        pr = led.propose_change(base_version_id=v0.version_id, changes={"exit_breakeven": 1}, rationale="kanit: n=40",
                                claimed_evidence={"n_closed": 3}, source="lesson", require_user=True)
        assert pr.status == "needs_user"
        denied = led.apply_proposal(pr.proposal_id, actor="lesson", reason="otomatik")
        assert denied.ok is False and denied.code == "user_approval_required"       # asla otomatik
        ok = led.apply_proposal(pr.proposal_id, actor="user", reason="kullanici onayi")
        assert ok.ok is True
        v1 = led.get_active_params()
        assert v1.params["exit_breakeven"] == 1 and "exit_partial" not in v1.params
        assert {k: v for k, v in v1.params.items() if k != "exit_breakeven"} == dict(v0.params)
        assert v1.params["trail_atr"] == PARAMS["trail_atr"]
        # ikinci kip, bagimsiz
        pr2 = led.propose_change(base_version_id=v1.version_id, changes={"exit_partial": 1}, rationale="kanit: n=40",
                                 claimed_evidence={"n_closed": 3}, source="lesson", require_user=True)
        assert led.apply_proposal(pr2.proposal_id, actor="user", reason="kullanici onayi").ok
        flags = {k: int(v) for k, v in led.get_active_params().params.items() if k in XM.MODE_PARAMS}
        assert flags == {"exit_breakeven": 1, "exit_partial": 1}
        assert XM.resolve({}, "T1", "1h", flags).partial and XM.resolve({}, "T1", "1h", flags).breakeven
        # sinir disi / adim buyuk
        bad = led.propose_change(base_version_id=led.get_active_params().version_id, changes={"exit_partial": 2},
                                 rationale="x", claimed_evidence={}, source="lesson")
        assert bad.status == "rejected"
    finally:
        led.close()


def test_telegram_param_names_cover_mode_params():
    from trader_core import telegram as TG
    assert "başa-baş" in TG.PARAM_TR["exit_breakeven"] and "kısmi" in TG.PARAM_TR["exit_partial"]
    import inspect
    assert "exit_modes_cf_line" in inspect.getsource(TG.section_lesson)                # "Ders" bolumune ek satir


@pytest.fixture(autouse=True)
def _kanit_surumu_eski_yol(monkeypatch):
    """Bu dosya eski (MODES_VERSION=2) kanit satirlariyla calisir; 24.11 surum secimi (target_mode) ayri testlerde
    (tests/engine/test_hedef_bekleyen_emir_cf_parite.py) denenir: burada okuyucu MAX(version)'a duser."""
    from trader_core import exit_counterfactual as _ecf
    monkeypatch.setattr(_ecf, "modes_version_from_config", lambda *a, **k: None)
