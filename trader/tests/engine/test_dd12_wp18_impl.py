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

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
LOCK_START = datetime(2026, 5, 1, tzinfo=UTC)          # holdout kilit baslangici (eski M1 egitim modulu kaldirildi)
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
    """Yumusak tavan toplami feed 200 + ogrenen 600 + testnet 250 = 1050 <= slice MemoryMax (1300)."""
    slice_max = _mem((DEPLOY / "trader.slice").read_text(encoding="utf-8"), "MemoryMax")
    soft = {
        "feed": _mem(_unit("trader-feed.service"), "MemoryHigh"),
        "learner": _mem(_unit("trader-engine@.service"), "MemoryHigh"),
        "testnet": _mem(_unit("trader-engine-testnet.service"), "MemoryHigh"),
    }
    assert soft == {"feed": 200, "learner": 600, "testnet": 250}
    assert sum(soft.values()) == 1050 and sum(soft.values()) <= slice_max == 1300


def test_every_trader_service_is_in_trader_slice():
    missing = [p.name for p in sorted(DEPLOY.glob("trader-*.service"))
               if "Slice=trader.slice" not in p.read_text(encoding="utf-8")
               and p.name != "trader-oto-guncelle.service"]   # kurulum isi: slice disinda, kendi MemoryMax'i ile (birim yorumu)
    assert missing == [], f"trader.slice disinda servis: {missing}"


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
    "src/trader_ml/config.py": "cd015f16fe601e75187f474a1cfbc1639f280692c7278991eae3f7838bc8e4b1",   # 25.11: DL1 kaldirildi (belge dizgisi); 24.11 kullanici karari: ML filtreleri silindi (yalniz kilit + walk-forward sabitleri kaldi)
    "src/trader_core/signals.py": "cd748923487db52ef0c29014c9454cbf97d967a96cc5745167e4417844ff52af",
    "src/trader_core/regime.py": "1c68c7624ad39cc9ef883fd5e2953acc1ed26dfb03513b55e1b19413303d7ecf",
    "src/trader_core/indicators.py": "8ebd05613f4845cb0ed930327adae0363eff43699d9091b373f0dc92af8cb84a",   # 24.11 kullanici karari: formasyon kutuphanesi (GF1/IN1 gostergeleri eklendi; mevcut fonksiyonlar ayni)
    "src/trader_engine/holdout.py": "c03925100fe903bf11bb4fcb692cf27255a138220be552bee9b6ffae28fec475",
    "config/engine.base.json": "26f5664f630f44bf594eb58e4efa881b2e71890ecb6d11ec80ad9fe2b3b8b361",   # 25.11 kullanici karari: denetim kalan maddeler (start_delay_s kalkti); 24.11 kullanici karari: veto ve C1 artiklari silindi;   # 24.11 kullanici karari: ML filtreleri silindi (ml_mode/ml_model_path anahtarlari kalkti)
    "config/engine.learner.json": "30ca2842c40cacafbf6cdd90c9e6f1f54fc62b9a9ec913476d1399ac5352cb12",
    "config/engine.testnet.json": "eff9eb61dcd9018bf86c195a02f7f25f08960473e705cbd114e104c26a956c9c",
    "config/engine.live.json": "05f1bfc2dc8ba2c5705e6fab9b5c40c722bc349c99425c8af9ea313cc20bd59b",   # 25.11: M1 kolu ve kol/aile basina pozisyon tavani kaldirildi (279 kol); HB1 + DL1 kolu kaldirildi; 24.11 kullanici karari: formasyon kutuphanesi birlesik (MF1 48 + GF1 52 + IN1 66 + PA2 29 + PA varyantlari 56 kol; max_positions 36)
    #   # 24.11 kullanici karari: DL1 dort zaman dilimi acik; onceki 24.11 ML filtreleri silindi; onceki 23.11 asama B + uzun_yon + HB1 (canli = kagit)
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


# ---- (d) kurulum, birimler, sunucu belgesi --------------------------------------------------------------------------
DD12_TIMERS = ("trader-weekly-summary.timer", "trader-universe.timer",
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
                   "price_action_lab_ml", "trader-universe", "8787", "--env testnet"):
        assert needle in guide, f"sunucu belgesinde eksik: {needle}"
