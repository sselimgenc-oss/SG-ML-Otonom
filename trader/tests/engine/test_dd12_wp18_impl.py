"""DD-12 WP-18 uygulayici testler: bellek butcesi (D-T14), olcum betigi esikleri (D-T20), yasak ice aktarma ve dondurulmus
dosyalar (D-T24), M1 gece egitimi (WP-18 b), evrenden cikmis ciftler (WP-18 c), kurulum ve sunucu belgesi (WP-18 d)."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import universe as U
from trader_engine.config import load_engine_config
from trader_ml.pa_proposer.train import LOCK_END, LOCK_START

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
SCRIPTS = ROOT / "scripts"
DEPLOY = ROOT / "deploy"
sys.path.insert(0, str(SCRIPTS))

from test_dd12_wp04_impl import env, _go  # noqa: E402,F401  (paper kapi fixture'i; WP-13 ile ayni)


def _unit(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def _mem(text: str, key: str) -> int | None:
    m = re.search(rf"^{key}=(\d+)M\s*$", text, re.M)
    return int(m.group(1)) if m else None


# ---- D-T14: bellek butcesi ----------------------------------------------------------------------------------------
def test_soft_cap_sum_fits_slice_hard_cap():
    """Yumusak tavan toplami feed 200 + ogrenen 600 + testnet 250 + egitim 250 = 1300 <= slice MemoryMax (1300)."""
    slice_max = _mem((DEPLOY / "trader.slice").read_text(encoding="utf-8"), "MemoryMax")
    soft = {
        "feed": _mem(_unit("trader-feed.service"), "MemoryHigh"),
        "learner": _mem(_unit("trader-engine@.service"), "MemoryHigh"),
        "testnet": _mem(_unit("trader-engine-testnet.service"), "MemoryHigh"),
        "ml_retrain": _mem(_unit("trader-ml-retrain.service"), "MemoryHigh"),
    }
    assert soft == {"feed": 200, "learner": 600, "testnet": 250, "ml_retrain": 250}
    assert sum(soft.values()) == 1300 and sum(soft.values()) <= slice_max == 1300


def test_every_trader_service_is_in_trader_slice():
    missing = [p.name for p in sorted(DEPLOY.glob("trader-*.service"))
               if "Slice=trader.slice" not in p.read_text(encoding="utf-8")
               and p.name != "trader-oto-guncelle.service"]   # kurulum isi: slice disinda, kendi MemoryMax'i ile (birim yorumu)
    assert missing == [], f"trader.slice disinda servis: {missing}"


def test_ml_retrain_unit_limits_and_command():
    txt = _unit("trader-ml-retrain.service")
    assert _mem(txt, "MemoryHigh") == 250 and _mem(txt, "MemoryMax") == 350       # WP-18 olcumu: tepe ~263 MB
    assert "Slice=trader.slice" in txt and "ml_retrain_run.py --once" in txt and "TimeoutStartSec=900" in txt
    assert "OnFailure=trader-health-fail@%n.service" in txt


def test_slice_hard_cap_is_unchanged():
    assert "MemoryMax=1300M" in (DEPLOY / "trader.slice").read_text(encoding="utf-8")


# ---- D-T20: olcum betigi esikleri ---------------------------------------------------------------------------------
def test_probe_budget_verdict_flags():
    from capacity_probe import budget_verdict, ENGINE_RSS_THRESHOLD_MB, STEP_THRESHOLD_S
    assert (ENGINE_RSS_THRESHOLD_MB, STEP_THRESHOLD_S) == (550.0, 120.0)        # spec §8 / D-T20
    ok = budget_verdict({"rss_peak_mb": 160.0, "per_step_s": {"15m": {"max": 12.0}, "1s": {"max": 16.0},
                                                             "4s": {"max": None}, "1g": {"max": 25.0}}})
    assert ok["rss_over"] is False and ok["hourly_over"] is False and ok["step_max_over"] is False
    bad = budget_verdict({"rss_peak_mb": 600.0, "per_step_s": {"15m": {"max": 1.0}, "1s": {"max": 130.0},
                                                              "4s": {"max": None}, "1g": {"max": None}}})
    assert bad["rss_over"] is True and bad["hourly_over"] is True and bad["step_max_over"] is True


def test_probe_hourly_only_checked_on_hour_steps():
    from capacity_probe import budget_verdict
    v = budget_verdict({"rss_peak_mb": 1.0, "per_step_s": {"15m": {"max": 500.0}, "1s": {"max": None}}})
    assert v["hourly_over"] is False and v["step_max_over"] is True             # 15dk adimi 120 sn asabilir; saat basi degil


def test_probe_step_categories():
    from capacity_probe import _category
    assert [_category(datetime(2026, 4, 30, h, m, tzinfo=UTC)) for h, m in ((0, 0), (4, 0), (5, 0), (5, 15))] == \
        ["1g", "4s", "1s", "15m"]


def test_probe_window_is_pre_lock_and_production_sized():
    import capacity_probe as C
    assert C.END < LOCK_START                                                  # sentetik kural kilit oncesi 1s bar ister
    assert C.BAR_WINDOWS == {"15m": 5000, "1h": 1500, "4h": 1500}


# ---- D-T24: yasak ice aktarma ve dondurulmus dosyalar -----------------------------------------------------------
FORBIDDEN = re.compile(r"^\s*(import|from)\s+(freqtrade|ccxt|binance)\b", re.M)


def test_no_forbidden_imports_in_new_code():
    hits = []
    for base in (ROOT / "src", ROOT / "scripts", ROOT / "research", ROOT / "tests"):
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if FORBIDDEN.search(p.read_text(encoding="utf-8", errors="ignore")):
                hits.append(str(p.relative_to(ROOT)))
    assert hits == [], f"yasak ice aktarma: {hits}"


FROZEN_SHA256 = {
    "src/trader_ml/guards.py": "3aa38a4c9ac1d4484c854c9566dd19c99c5a5bceb0b0addc3161b420c41bfb32",   # 24.11 kullanici karari: ML filtreleri silindi (kullanilmayan clip_to_train_window kalkti)
    "src/trader_ml/config.py": "bcd786bfa6ae7c116813c00c0fe9cc881f79727ce1d32d25701be0d3b3c27fc5",   # 24.11 kullanici karari: ML filtreleri silindi (yalniz kilit + walk-forward sabitleri kaldi)
    "src/trader_core/signals.py": "cd748923487db52ef0c29014c9454cbf97d967a96cc5745167e4417844ff52af",
    "src/trader_core/regime.py": "1c68c7624ad39cc9ef883fd5e2953acc1ed26dfb03513b55e1b19413303d7ecf",
    "src/trader_core/indicators.py": "aa4c6e4c5b19ad26eb6ee0be5f604f439a09310f931fd6ba3d7d475b533a4e4c",
    "src/trader_engine/holdout.py": "c03925100fe903bf11bb4fcb692cf27255a138220be552bee9b6ffae28fec475",
    "config/engine.base.json": "2ccdf97d21842f2dc54f682e66d65762f7957a7615befd932fbad8c68f49325e",   # 24.11 kullanici karari: veto ve C1 artiklari silindi;   # 24.11 kullanici karari: ML filtreleri silindi (ml_mode/ml_model_path anahtarlari kalkti)
    "config/engine.learner.json": "30ca2842c40cacafbf6cdd90c9e6f1f54fc62b9a9ec913476d1399ac5352cb12",
    "config/engine.testnet.json": "eff9eb61dcd9018bf86c195a02f7f25f08960473e705cbd114e104c26a956c9c",
    "config/engine.live.json": "d4f9489fa6373879342e72f812f384847c3654351bebe7e369ea0b464e8ad951",   # 24.11 kullanici karari: DL1 dort zaman dilimi acik; onceki 24.11 ML filtreleri silindi; onceki 23.11 asama B + uzun_yon + HB1 (canli = kagit)
    "src/trader_engine/order_manager.py": "7bd0ff0ca3173c7e8baf0ab05dde04a8b1c472d4510c4922d142220d4ae02538",   # 24.11 kullanici kararlari: hedef emir + risk 0.12/DL1 4 + veto/C1 silme (birlesik pin)
    "research/s2_run.py": "66710418f9be36225b757f9d4a1158b1e9093db5f7df131572c639e3958b21a7",
}


@pytest.mark.parametrize("rel", sorted(FROZEN_SHA256))
def test_frozen_files_unchanged(rel):
    digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    assert digest == FROZEN_SHA256[rel], f"dondurulmus dosya degisti: {rel}"


# ---- (c) evrenden cikmis (retired) ciftler --------------------------------------------------------------------------
def _paper_overlay(retired=()):
    import json as _j
    paper = _j.loads((ROOT / "config/engine.paper.json").read_text(encoding="utf-8"))
    return {"schema": U.SCHEMA, "generated_at": "2026-11-01T00:30:00Z", "source": "test",
            "pairs": paper["pairs"], "optional_pairs": paper["optional_pairs"], "retired_pairs": list(retired), "notes": []}


def test_overlay_retired_pairs_validated():
    ov = U.validate_overlay(_paper_overlay(retired=["XAU/USDT"]))
    assert ov["retired_pairs"] == ["XAU/USDT"]
    with pytest.raises(ValueError, match="pairs disinda"):
        U.validate_overlay(_paper_overlay(retired=["ZZZ/USDT"]))
    with pytest.raises(ValueError, match="yinelenen"):
        U.validate_overlay(_paper_overlay(retired=["XAU/USDT", "XAU/USDT"]))
    doc = dict(_paper_overlay(), retired_pairs=None)
    with pytest.raises(ValueError):
        U.validate_overlay(doc)
    old = _paper_overlay()
    old.pop("retired_pairs")
    assert U.validate_overlay(old)["retired_pairs"] == []                     # eski kaplama: anahtar yok = bos


def test_overlay_document_carries_retired():
    doc = U.overlay_document(["BTC/USDT", "XAU/USDT"], ["XAU/USDT"], generated_at="2026-11-01T00:30:00Z", source="t",
                             retired=["XAU/USDT"])
    assert doc["retired_pairs"] == ["XAU/USDT"] and U.validate_overlay(doc)["retired_pairs"] == ["XAU/USDT"]


def test_config_loader_reads_retired_from_overlay(tmp_path):
    f = tmp_path / "paper_pairs.json"
    f.write_text(json.dumps(_paper_overlay(retired=["XAU/USDT"])), encoding="utf-8")
    cfg = load_engine_config(ROOT / "config/engine.base.json", ROOT / "config/engine.learner.json",
                             overlay_path=ROOT / "config/engine.paper.json", universe_path=f)
    assert cfg.retired_pairs == ("XAU/USDT",) and "XAU/USDT" in cfg.pairs     # evrende kalir, yeni giris kapali
    plain = load_engine_config(ROOT / "config/engine.base.json", ROOT / "config/engine.learner.json",
                               overlay_path=ROOT / "config/engine.paper.json")
    assert plain.retired_pairs == ()


def test_gate_skips_new_entry_on_retired_pair(env):
    env.g.cfg = dataclasses.replace(env.g.cfg, retired_pairs=("BTC/USDT",))
    out = _go(env)
    assert out.action == "skip" and out.code == "arm_disabled"
    assert out.event.skip_reason == "arm_disabled"
    assert out.event.veto_reason == "gate:universe_retired:BTC/USDT"
    assert _go(env, "ETH/USDT").action == "enter"                              # kalan ciftler etkilenmez


def test_skip_reason_has_no_new_ledger_value():
    """Defter CHECK'i 'universe_retired' kabul etmez; neden `veto_reason` ile kaydedilir (belgelenmis karar)."""
    from trader_core import ledger as L
    assert "universe_retired" not in L._NEW_SKIP and "arm_disabled" in L._NEW_SKIP


# ---- (b) M1 gece egitimi -------------------------------------------------------------------------------------------
def _write_1h(hist: Path, base: str, start: datetime, n: int, seed: int) -> None:
    import numpy as np
    import pyarrow as pa
    import pyarrow.feather as pf
    rng = np.random.default_rng(seed)
    idx = [start + timedelta(hours=k) for k in range(n)]
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    op = np.concatenate([[close[0]], close[:-1]])
    hi = np.maximum(op, close) + np.abs(rng.normal(0, 0.2, n))
    lo = np.minimum(op, close) - np.abs(rng.normal(0, 0.2, n))
    tbl = pa.table({"date": pa.array([t for t in idx], type=pa.timestamp("ms", tz="UTC")),
                    "open": op, "high": hi, "low": lo, "close": close, "volume": np.ones(n)})
    pf.write_feather(tbl, str(hist / f"{base}_USDT_USDT-1h-futures.feather"), compression="uncompressed")


class _StubLedger:
    LIST_CLOSED_MAX = 10

    def list_closed_trades(self, limit=10):
        return []

    def list_decisions(self):
        return []


@pytest.fixture()
def hist_dir(tmp_path):
    h = tmp_path / "history"
    h.mkdir()
    start = datetime(2025, 6, 1, tzinfo=UTC)                                     # kilit (2026-05-01..11-01) dahil bars
    for k, base in enumerate(("BTC", "ETH")):
        _write_1h(h, base, start, 24 * 420, seed=7 + k)                          # ~14 ay
    return h


def test_m1_history_tail_excludes_lock_window(hist_dir):
    import ml_retrain_run as R
    bars = R._load_bars(str(hist_dir), "BTC", "1h")
    rows = R._hist_tail(bars, "BTC/USDT", cap=400, cutoff=LOCK_START)
    assert rows and len(rows) <= 400
    assert max(r["ts_end"] for r in rows) < LOCK_START                          # etiket ufku da kilit oncesinde
    assert all(not (r["ts"] < LOCK_END and r["ts_end"] >= LOCK_START) for r in rows)


def test_m1_nightly_writes_package_and_csv_row(hist_dir, tmp_path):
    import ml_retrain_run as R
    now = datetime(2026, 11, 19, 3, 10, tzinfo=UTC)
    csv_rows: list = []
    out = R.m1_nightly(_StubLedger(), None, history_dir=str(hist_dir), tfs=["1h"], models_dir=str(tmp_path / "m1"),
                       now=now, max_rows=400, csv_rows=csv_rows)
    assert out["1h"]["status"] == "ok" and out["1h"]["lock_dropped"] == 0
    assert (tmp_path / "m1" / "M1@1h.json").exists()
    pkg = json.loads((tmp_path / "m1" / "M1@1h.json").read_text(encoding="utf-8"))
    assert pkg["meta"]["arm_id"] == "M1@1h" and pkg["meta"]["paper_only"] is True
    assert len(csv_rows) == 1 and csv_rows[0][1] == "nightly_m1" and "lock_dropped=0" in csv_rows[0][3]


@pytest.mark.usefixtures("egitim_kilitli")
def test_paper_records_in_lock_window_are_dropped():
    import export_paper_records as EPR
    rows = [
        {"bar_close_ts": "2026-06-01T00:00:00+00:00", "outcome_ts": "2026-06-02T00:00:00+00:00", "r": 1.0},   # kilit ici
        {"bar_close_ts": "2026-02-01T00:00:00+00:00", "outcome_ts": "2026-02-02T00:00:00+00:00", "r": -1.0},  # kilit oncesi
        {"bar_close_ts": None, "outcome_ts": None, "r": 0.5},                                                  # dogrulanamaz
    ]
    kept, dropped = EPR.drop_locked_rows(rows)
    assert len(kept) == 1 and dropped == 2 and kept[0]["r"] == -1.0


def test_m1_nightly_hatasinda_cikis_3_ve_csv_yazilir(tmp_path, monkeypatch):
    """M1 hatasi paper_models.csv dosyasini yine olusturur; cikis 3 (saglik gorunurlugu)."""
    import ml_retrain_run as R
    from trader_core import ledger as L
    monkeypatch.setattr(R, "m1_nightly", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("m1 boom")))
    monkeypatch.setattr(L, "open_ledger", lambda *a, **k: SimpleNamespace(close=lambda: None))
    rc = R.main(["--once", "--ledger", str(tmp_path / "x.sqlite"),
                 "--m1-models-dir", str(tmp_path / "m1"), "--paper-models-csv", str(tmp_path / "p.csv")],
                now_fn=lambda: datetime(2026, 11, 19, tzinfo=UTC))
    assert rc == 3
    assert (tmp_path / "p.csv").read_text(encoding="utf-8").splitlines() == ["ad,sinif,tarif,veri_penceresi,commit,sha256,tarih"]


# ---- (d) kurulum, birimler, sunucu belgesi --------------------------------------------------------------------------
DD12_TIMERS = ("trader-notes.timer", "trader-weekly-summary.timer", "trader-ml-retrain.timer", "trader-universe.timer",
               "trader-counterfactual@learner.timer", "trader-exit-counterfactual@learner.timer")


def test_install_enables_dd12_timers():
    txt = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for t in DD12_TIMERS:
        assert re.search(rf"enable_now\s+{re.escape(t)}", txt), f"install.sh etkinlestirmiyor: {t}"


def test_install_removes_veto_and_twin_units():
    txt = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    assert "trader-veto.timer trader-veto.service" in txt and "trader-engine@twin.service" in txt
    assert not any(re.search(r"enable_now\s+\S*(veto|twin)", line) for line in txt.splitlines())
    assert not list(DEPLOY.glob("trader-veto.*")) and not list(DEPLOY.glob("*twin*"))


def test_dd12_timer_units_exist_in_deploy():
    txt = (DEPLOY / "install.sh").read_text(encoding="utf-8")
    for t in DD12_TIMERS:
        assert (DEPLOY / t.replace("@learner", "@")).exists() or (DEPLOY / t).exists()


def test_owner_guide_covers_steps():
    guide = (ROOT / "docs/motor/dd12-sunucu-adimlari.md").read_text(encoding="utf-8")
    for needle in ("COMMIT=", "install.sh", "outbox-quarantine", "--dry-run", "--apply", "init-ledger", "strategy_update",
                   "price_action_lab_ml", "trader-ml-retrain", "trader-universe", "8787", "--env testnet"):
        assert needle in guide, f"sunucu belgesinde eksik: {needle}"
