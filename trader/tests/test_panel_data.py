"""Panel uc noktalari: durum eslemesi, bayatlik, eksik kaynaklar, defter/egri/risk/butce/ders/saglik."""
import dataclasses
import json
from datetime import timedelta

import pytest

from panel_support import DAY, NOW, Env, Running, STD_LEARNER, status_doc, z
from trader_core import panel_data as P
from pathlib import Path

from trader_core.risk import LOCKED_CFG

ROOT_CFG = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    e = Env(tmp_path_factory.mktemp("pd"))
    yield e
    e.close()


@pytest.fixture(scope="module")
def run(env):
    r = Running(env, cache_s=0)
    yield r
    r.stop()


# ---------------- /api/status ----------------
def test_status_fields_one_to_one(run, env):
    raw = json.loads((env.root / "var/learner/status.json").read_text())
    b = run.get("/api/status")["bots"]["learner"]
    assert b["state"] == "live" and b["banner"] is None
    d = b["data"]
    for k in ("mode", "dry_run", "kill", "kill_state", "entries_open", "entries_blocked_reason", "loop_at", "equity",
              "day_start_equity", "wallet", "counters", "param_version_id", "strategy", "trigger_tf", "open_positions"):
        assert d[k] == raw[k], k
    assert d["gate_code"] == raw["gate"]["code"]


@pytest.mark.parametrize("age,stale", [(120, False), (120.5, True), (121, True), (5, False)])
def test_stale_boundary(tmp_path, age, stale):
    e = Env(tmp_path)
    e.write_status("learner", age)
    b = Running(e).get("/api/status")["bots"]["learner"]
    assert (b["state"] == "stale") is stale
    e.close()


def test_stale_banner_and_no_last_known_values(tmp_path):
    e = Env(tmp_path, status_age_s=400)
    r = Running(e)
    j = r.get("/api/status")
    b = j["bots"]["learner"]
    assert b["state"] == "stale" and b["data"] is None
    since = (NOW - timedelta(seconds=400)).astimezone(P.TR).strftime("%Y-%m-%d %H:%M:%S")
    assert b["banner"] == f"BAYAT: {since} TSİ'dan beri"
    body = json.dumps(j)
    assert "1003.5" not in body and "ETH/USDT" not in body           # son bilinen equity/pozisyon canli gibi sizmaz
    assert r.get("/api/risk?bot=learner")["ok"] is False             # canli degerden turetilen risk de yok
    r.stop()
    e.close()


@pytest.mark.parametrize("content,code", [(None, "status_yok"), ("{bozuk", "status_bozuk"), ("[1]", "status_bozuk"),
                                          ('{"equity": 5}', "status_bozuk"), ('{"loop_at": "dun"}', "status_bozuk")])
def test_status_missing_or_corrupt(tmp_path, content, code):
    e = Env(tmp_path)
    p = e.root / "var/learner/status.json"
    if content is None:
        p.unlink()
    else:
        p.write_text(content)
    r = Running(e)
    j = r.get("/api/status")
    b = j["bots"]["learner"]
    assert b["state"] in ("missing", "bad") and b["code"] == code and b["data"] is None
    assert b["banner"].startswith("BAYAT")
    assert "twin" not in j["bots"]                                    # DD-12: ikiz kaldirildi
    r.stop()
    e.close()


def test_kill_file_is_only_read(tmp_path):
    e = Env(tmp_path)
    r = Running(e)
    assert r.get("/api/status")["kill_file_exists"] is False
    (e.root / "shared/KILL").write_text("x")
    assert r.get("/api/status")["kill_file_exists"] is True
    r.stop()
    e.close()


def test_thresholds_come_from_config_not_literals(tmp_path, monkeypatch):
    e = Env(tmp_path, status_age_s=60)
    monkeypatch.setattr(P, "STALE_S", 30)
    r = Running(e, cache_s=0)
    assert r.get("/api/status")["bots"]["learner"]["state"] == "stale"
    monkeypatch.setattr(P, "STALE_S", 120)
    assert r.get("/api/status")["bots"]["learner"]["state"] == "live"
    monkeypatch.setattr(P, "daily_loss_rate", lambda mode="paper": 0.03)   # tek kaynak: Telegram ile ayni yardimci
    row = [x for x in r.get("/api/risk?bot=learner")["rows"] if x["label"] == "Günlük zarar"][0]
    assert row["limit"] == pytest.approx(0.03 * 1000.0)
    s = r.get("/api/ledger?bot=learner")["summary"]
    assert s["daily_limit"] == pytest.approx(30.0)
    r.stop()
    e.close()


# ---------------- /api/ledger, curve, risk, compare ----------------
def test_ledger_day_and_recent(run):
    j = run.get(f"/api/ledger?bot=learner&day={DAY}")
    s = j["summary"]
    assert (s["closed"], s["win"], s["loss"], s["open"]) == (2, 1, 1, 1)
    assert s["daily_limit"] == pytest.approx(P.daily_loss_rate() * 1000.0)
    assert [t["trade_id"] for t in j["closed"]] == [5, 4]                 # cikis zamani yeniden eskiye
    assert j["open"][0]["trade_id"] == 6
    assert j["decisions"]["entered"] == 3 and j["decisions"]["total"] == 3
    allr = run.get("/api/ledger?bot=learner")
    assert [t["trade_id"] for t in allr["closed"]] == [5, 4, 3, 2, 1]
    other = run.get("/api/ledger?bot=learner&day=2026-11-14")
    assert [t["trade_id"] for t in other["closed"]] == [2, 1]


@pytest.mark.parametrize("q", ["bot=x", "", "bot=learner&day=2026-13-40", "bot=learner&day=abc", "bot=learner&day=2026-11-1"])
def test_ledger_bad_params(run, q):
    j = run.get("/api/ledger?" + q)
    assert j["ok"] is False and j["code"] in ("gecersiz_bot", "gecersiz_gun")


def test_curve(run):
    c = run.get("/api/curve?bot=learner")
    assert c["base"] == "equity" and c["start"] == 1000.0 and c["total_closed"] == 5
    pnl = sum(t["realized_pnl"] for t in run.get("/api/ledger?bot=learner")["closed"])
    assert c["points"][-1][1] == pytest.approx(1000.0 + pnl)
    assert c["peak"] >= max(p[1] for p in c["points"]) - 1e-9
    assert c["max_dd_pct"] <= 0 and c["max_dd_abs"] <= 0
    days = {d["day"]: d for d in c["daily"]}
    assert days[DAY]["n"] == 2 and days["2026-11-14"]["n"] == 2 and days["2026-11-15"]["n"] == 1
    assert sum(d["pnl"] for d in c["daily"]) == pytest.approx(pnl)


def test_curve_without_engine_config_falls_back_to_pnl(tmp_path):
    e = Env(tmp_path)
    (e.root / "config/engine.base.json").unlink()
    r = Running(e)
    c = r.get("/api/curve?bot=learner")
    assert c["base"] == "pnl" and c["start"] is None and c["max_dd_pct"] is None and c["peak"] is None
    r.stop()
    e.close()


def test_risk_rows_use_ledger_and_risk_config(run):
    rows = {x["label"]: x for x in run.get("/api/risk?bot=learner")["rows"]}
    assert rows["Toplam açık risk"]["used"] == pytest.approx(13.188)     # acik islemin planned_risk toplami
    cfg = json.loads((ROOT_CFG / "engine.paper.json").read_text())["risk"]        # 24.11: limitler kipin ayar dosyasindan (motorla ayni)
    assert rows["Toplam açık risk"]["limit"] == pytest.approx(cfg["max_open_risk"] * 1003.5)
    assert rows["Long açık risk"]["limit"] == pytest.approx(cfg["max_same_dir_risk"] * 1003.5)
    assert rows["Günlük zarar"]["limit"] == pytest.approx(P.daily_loss_rate() * 1000.0)


@pytest.mark.parametrize("mode", ["paper", "live"])
def test_risk_usage_ayar_dosyasi_ve_gerceklesmemis_zarar(monkeypatch, mode):
    """24.11 denetim: limitler LOCKED_CFG degil ayar dosyasi (%12/%6); gunluk zarar = gun basi kasa - simdiki kasa (acik zarar dahil)."""
    monkeypatch.setattr(P, "ledger_day", lambda path, bot, day: ([], []))
    cfg = json.loads((ROOT_CFG / f"engine.{mode}.json").read_text())["risk"]
    rows = {x["label"]: x for x in P.risk_usage("x", "learner", 970.0, 1000.0, DAY, mode)["rows"]}
    assert rows["Toplam açık risk"]["limit"] == pytest.approx(cfg["max_open_risk"] * 970.0)
    assert rows["Short açık risk"]["limit"] == pytest.approx(cfg["max_same_dir_risk"] * 970.0)
    assert rows["Günlük zarar"]["used"] == pytest.approx(30.0)                    # gerceklesen pnl yok, acik zarar 30
    assert rows["Günlük zarar"]["limit"] == pytest.approx(cfg["daily_max_loss"] * 1000.0)
    assert cfg["max_open_risk"] != LOCKED_CFG.max_open_risk


def test_compare_and_twin_endpoints_removed(run):
    """DD-12: ikiz karsilastirmasi kalkti; bot=twin gecersiz."""
    assert run.req(f"/api/compare?day={DAY}")[0] == 404
    j = run.get("/api/ledger?bot=twin")
    assert j["ok"] is False and j["code"] == "gecersiz_bot"


# ---------------- /api/budget, lesson, health, system ----------------
def test_budget_matches_guard(run, env):
    from trader_core import budget as B
    st = B.BudgetGuard(B.load_config(env.root / "config/budget.json")).status()
    j = run.get("/api/budget")
    assert j["month_used_usd"] == st.month_used_usd and j["monthly_cap_usd"] == st.monthly_cap_usd
    assert j["month_state"] == st.month_state and j["prices_verified"] is st.prices_verified
    for k, v in st.services.items():
        assert (j["services"][k]["used_usd"], j["services"][k]["cap_usd"], j["services"][k]["state"]) == (v.used_usd, v.cap_usd, v.state)


def test_lesson_matches_store(run):
    j = run.get("/api/lesson")
    assert j["open_count"] == 1 and j["open_requests"][0] == {"request_id": "lr-2026-11-16-1", "param": "rr_min",
                                                              "from": 1.5, "to": 1.25, "scope": "global"}
    assert j["shadow"]["end"] == "2026-12-08" and j["shadow"]["day"] == 7 and j["shadow"]["total"] == 28
    assert j["last_run"] == {"day": "2026-11-16", "status": "succeeded", "code": "ok"}


def test_health_and_system(run):
    h = run.get("/api/health")
    assert h["overall"] == "WARN" and h["check_stale"] is False and h["alerts"][0]["code"] == "stale"
    assert h["restart_counts"] == {"engine": 1}
    s = run.get("/api/system")
    assert s["mem_available"] > 0 and s["mem_level"] in ("iyi", "uyari", "kotu")


def test_health_stale_check(tmp_path):
    e = Env(tmp_path)
    st = json.loads((e.root / "state/state.json").read_text())
    st["last_run_at"] = z(NOW - timedelta(hours=3))
    (e.root / "state/state.json").write_text(json.dumps(st))
    r = Running(e)
    assert r.get("/api/health")["check_stale"] is True
    r.stop()
    e.close()


# ---------------- eksik kaynak: yalniz o widget "okunamadi" ----------------
def test_missing_sources_isolated(tmp_path):
    e = Env(tmp_path, learner=False, budget=False, lesson=False, health=False)
    r = Running(e)
    for path, code in (("/api/ledger?bot=learner", "defter_yok"), ("/api/curve?bot=learner", "defter_yok"),
                       ("/api/budget", "yapilandirma_gecersiz"), ("/api/lesson", "depo_yok"), ("/api/health", "state_yok")):
        j = r.get(path)
        assert j["ok"] is False and j["code"] == code, path
    assert r.get("/api/status")["ok"] is True and r.get("/api/system")["ok"] is True
    assert not (e.root / "var/learner/ledger.sqlite").exists()       # okuma dosya olusturmaz
    assert not (e.root / "user_data/lesson.sqlite").exists()
    r.stop()
    e.close()


def test_corrupt_sources_do_not_crash(tmp_path):
    e = Env(tmp_path)
    (e.root / "var/learner/ledger.sqlite").write_bytes(b"garbage" * 200)
    (e.root / "user_data/lesson.sqlite").write_bytes(b"garbage" * 200)
    (e.root / "user_data/budget.sqlite").write_bytes(b"garbage" * 200)
    (e.root / "state/state.json").write_text("{bozuk")
    r = Running(e)
    for p in ("/api/ledger?bot=learner", "/api/curve?bot=learner", "/api/lesson", "/api/budget", "/api/health"):
        j = r.get(p)
        assert j["ok"] is False and j["code"], p
    assert r.get("/healthz")["ok"] is True
    r.stop()
    e.close()
