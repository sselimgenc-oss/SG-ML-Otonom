"""Panel: cikis kaniti (haber/duygu paneli SILINDI) (salt okunur; kaynak yok/bozuk/bayat paneli bozmaz). Sentetik veri, kilitli donem disinda."""
import json
import sqlite3
from datetime import timedelta

import pytest

from panel_support import NOW, Env, Running, z
from trader_core import exit_counterfactual as X
from trader_core import panel_data as P
from trader_panel import snapshot as SN
from trader_panel.data import PanelData, load_config


@pytest.fixture()
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.close()


def pd_(env):
    return PanelData(load_config(env.cfg_path), clock=lambda: NOW)


def mk_store(path, outcomes=(), modes=()):
    """Gercek DDL ile bos depo, sonra sentetik satirlar (kapanmis; pencere NOW'dan once)."""
    st = X.ExitCfStore(str(path))
    st.close()
    db = sqlite3.connect(str(path))
    ent = z(NOW - timedelta(days=10))
    wend = z(NOW - timedelta(days=9))
    for tid, setup, role, val, net in outcomes:
        db.execute("INSERT INTO ecf_outcomes (bot,source,run_id,trade_id,pair,side,setup,entry_ts,param,value,role,exit_reason_sim,net_r,"
                   "censored,window_end_ts,computed_at,version,registry_id) VALUES ('learner','paper','',?,'ETH/USDT','long',?,?,"
                   "'trail_atr',?,?,'stop',?,0,?,?,1,'exitcf-v1')", (tid, setup, ent, val, role, net, wend, z(NOW - timedelta(hours=3))))
    for tid, setup, variant, net in modes:
        db.execute("INSERT INTO ecf_modes (bot,source,run_id,trade_id,pair,side,setup,entry_ts,trail_atr,variant,exit_reason_sim,net_r,"
                   "censored,window_end_ts,computed_at,version,registry_id) VALUES ('learner','paper','',?,'ETH/USDT','long',?,?,3.0,?,"
                   "'stop',?,0,?,?,1,'exitcf-v2')", (tid, setup, ent, variant, net, wend, z(NOW - timedelta(hours=2))))
    db.commit()
    db.close()


def put(env, rel, text):
    p = env.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)



def test_exitcf_ok_per_setup(env):
    mk_store(env.root / "var/learner/exit_counterfactual.sqlite",
             outcomes=[(1, "T1", "base", 3.0, 1.0), (1, "T1", "up", 3.25, 1.5), (1, "T1", "down", 2.75, 0.5),
                       (2, "T1", "base", 3.0, -1.0), (2, "T1", "up", 3.25, -0.5),
                       (3, "R1", "base", 3.0, 0.2), (3, "R1", "up", 3.25, 0.1)],
             modes=[(1, "T1", "off", 1.0), (1, "T1", "breakeven", 2.2), (1, "T1", "partial", 0.9),
                    (2, "T1", "off", -1.0), (2, "T1", "breakeven", 0.0)])
    r = pd_(env).ciktikaniti()
    assert r["ok"] and r["var"]
    t1 = next(k for k in r["kurulumlar"] if k["kurulum"] == "T1")
    assert t1["islem"] == 2
    assert t1["trail_yukari"] == {"n": 2, "delta_r": 1.0} and t1["trail_asagi"] == {"n": 1, "delta_r": -0.5}
    assert t1["basabas"] == {"n": 2, "delta_r": 2.2} and t1["kismi"] == {"n": 1, "delta_r": -0.1}
    r1 = next(k for k in r["kurulumlar"] if k["kurulum"] == "R1")
    assert r1["basabas"]["n"] == 0 and r1["basabas"]["delta_r"] is None
    assert r["son_kosu_v1"] and r["son_kosu_v2"] and "bekleyen" not in r
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize("make,neden", [(None, "dosya_yok"), ("garbage", "bozuk"), ("empty", "kayit_yok")])
def test_exitcf_missing_corrupt_empty(env, make, neden):
    p = env.root / "var/learner/exit_counterfactual.sqlite"
    if make == "garbage":
        p.write_bytes(b"bu bir sqlite degil" * 50)
    elif make == "empty":
        mk_store(p)
    r = pd_(env).ciktikaniti()
    assert r["ok"] is True and r["var"] is False and r["neden"] == neden


def test_exitcf_old_store_without_modes_table(env):
    p = env.root / "var/learner/exit_counterfactual.sqlite"
    db = sqlite3.connect(str(p))
    db.execute("CREATE TABLE meta (key TEXT)")
    db.commit()
    db.close()
    r = pd_(env).ciktikaniti()
    assert r["ok"] and r["var"] is False and r["neden"] == "kayit_yok"


def test_views_never_raise_on_bad_input():
    assert P.exitcf_view("", NOW)["var"] is False
    assert not hasattr(P, "haber_view") and not hasattr(P, "haber_sonuc_view")


def test_server_endpoints_and_snapshot(env):
    mk_store(env.root / "var/learner/exit_counterfactual.sqlite", modes=[(1, "T1", "off", 1.0), (1, "T1", "partial", 2.0)])
    run = Running(env)
    try:
        assert run.get("/api/ciktikaniti")["var"] is True
    finally:
        run.stop()
    html = SN.render(pd_(env))
    assert "/api/haber" not in html
    data = SN.collect(pd_(env))
    assert "/api/ciktikaniti" not in data      # 9b-01: panel.js okumaz; anlik goruntuye gomulmez
    assert "/api/haber" not in data and "/api/habersonuc" not in data


def test_snapshot_and_server_with_empty_sources(env):
    data = SN.collect(pd_(env))
    assert "/api/ciktikaniti" not in data and "/api/pbo" not in data
    run = Running(env)
    try:
        assert run.get("/api/ciktikaniti")["neden"] == "dosya_yok"
    finally:
        run.stop()


@pytest.fixture(autouse=True)
def _kanit_surumu_eski_yol(monkeypatch):
    """Bu dosya eski (MODES_VERSION=2) kanit satirlariyla calisir; 24.11 surum secimi (target_mode) ayri testlerde
    (tests/engine/test_hedef_bekleyen_emir_cf_parite.py) denenir: burada okuyucu MAX(version)'a duser."""
    from trader_core import exit_counterfactual as _ecf
    monkeypatch.setattr(_ecf, "modes_version_from_config", lambda *a, **k: None)
