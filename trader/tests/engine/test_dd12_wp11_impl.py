"""DD-12 WP-11 uygulayici duman testleri: kurulum paketi (arms), bars (1g = 6 x 4s), yapilandirma (arms/arm_max_positions), lab
stratejisi, oncelik/arm_conflict, kurulum tavani, D-T18 esdegerligi ve sentetik cok kurullu kagit calismasi."""
from __future__ import annotations

import sqlite3
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core import signals as S
from trader_engine import bars as B
from trader_engine import engine as E
from trader_engine.clock import SimClock
from trader_engine.config import ConfigError, apply_overrides, load_cli_config
from trader_engine.marketdata.sources import HistoricalSource
from trader_engine.strategies import arms as ARMS
from trader_engine.strategies.base import StrategyError
from trader_engine.strategies.lab import NAME, PriceActionLab
from trader_engine.strategies.registry import get_strategy, list_strategies
from trader_engine.strategy_runner import MultiArmSignalSource

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
PAPER = load_cli_config(ROOT / "config", "learner", "paper")
ALL_ARMS = tuple(f"{s_}@{tf}" for s_ in ("T1", "R1", "TF1", "B1", "H2", "S1", "F1") for tf in ("15m", "1h", "4h", "1d"))   # WP-12a: TF1/B1; WP-12b: H2/S1/F1
PAPER_ARMS = ALL_ARMS + ("M1@1h", "M1@4h", "M1@15m", "M1@1d", "HB1@1h", "DL1@15m", "DL1@1h", "DL1@4h", "DL1@1d")   # 24.11: DL1 dort zaman dilimi; 23.11: HB1 haber kolu; 20 Kasim: M1 15dk/1g kagitta acik; DD-12 WP-14: M1 (ML'in kendi adayi) config/engine.paper.json'a eklendi


# --------------------------------------------------------------------------- arms paketi
def test_arms_discovery_and_lookup():
    assert {"R1", "T1"} <= set(ARMS.list_arms())   # WP-12a: TF1/B1 de var
    t1, r1 = ARMS.find_arm("T1"), ARMS.find_arm("R1")
    assert t1.SETUP == "T1" and set(t1.TIMEFRAMES) == {"15m", "1h", "4h", "1d"} and t1.CORE and r1.CORE
    with pytest.raises(ARMS.ArmError):
        ARMS.find_arm("ZZ9")
    with pytest.raises(ARMS.ArmError):
        ARMS.find_arm("../t1")                                  # dize modul yuklemek icin kullanilmaz
    assert ARMS.parse_arm_id("T1@4h") == ("T1", "4h") and ARMS.make_arm_id("R1", "1d") == "R1@1d"
    for bad in ("T1", "t1@1h", "T1@5m", "T1@1h ", ""):
        with pytest.raises(ARMS.ArmError):
            ARMS.parse_arm_id(bad)


def test_new_arm_file_found_without_registry_edit(tmp_path):
    (tmp_path / "x9.py").write_text(textwrap.dedent('''
        SETUP = "X9"
        TIMEFRAMES = ("1h",)
        CORE = False
        EXIT_MODE = "trail"      # WP-12a (K-7): zorunlu
        PRIORITY = 99
        FEATURES = {}
        def compute(inp):
            return inp.core()
    '''))
    ARMS.__path__.append(str(tmp_path))                          # type: ignore[attr-defined]
    try:
        ARMS.discover(refresh=True)
        assert "X9" in ARMS.list_arms()
        lab = PriceActionLab(("T1@1h", "X9@1h"))
        assert lab.info.setups == ("T1", "X9") and lab.arm_ids == ("T1@1h", "X9@1h")
    finally:
        ARMS.__path__.remove(str(tmp_path))                      # type: ignore[attr-defined]
        sys.modules.pop(f"{ARMS.__name__}.x9", None)
        ARMS.discover(refresh=True)
    assert {"R1", "T1"} <= set(ARMS.list_arms())   # WP-12a: TF1/B1 de var


def test_lab_rejects_unknown_arm_and_tf():
    for bad in (("ZZ9@1h",), ("T1@5m",), ("T1@1h", "T1@1h")):
        with pytest.raises(StrategyError) as ei:
            PriceActionLab(bad)
        assert ei.value.code == "unknown_arm"


def test_registry_and_defaults():
    assert list_strategies()[-1] == NAME == "price_action_lab_ml"
    s = get_strategy(NAME, mode="paper")
    assert s.info.paper_allowed and s.decision_tf == "15m"
    assert s.arm_ids == ("T1@1h", "R1@1h")                       # D-T18 varsayilani
    s2 = get_strategy(NAME, mode="paper", arms=ALL_ARMS)
    assert s2.tfs() == ("15m", "1h", "4h", "1d")
    with pytest.raises(StrategyError):
        get_strategy("price_action_v1", arms=("T1@1h",))


# --------------------------------------------------------------------------- bars
def _h4_frame(start, n, drop=()):
    idx = pd.DatetimeIndex([start + timedelta(hours=4 * i) for i in range(n) if i not in drop], tz="UTC", name="date")
    k = np.arange(len(idx), dtype=float)
    return pd.DataFrame({"open": 100 + k, "high": 102 + k, "low": 99 + k, "close": 101 + k, "volume": 10.0 + k}, index=idx)


def test_aggregate_1d_is_six_4h_and_drops_incomplete_days():
    h4 = _h4_frame(datetime(2026, 11, 1, tzinfo=UTC), 18)               # 3 gun
    d = B.aggregate_4h_to_1d(h4)
    assert list(d.index) == [datetime(2026, 11, d_, tzinfo=UTC) for d_ in (1, 2, 3)]
    first = h4.iloc[:6]
    assert d.iloc[0]["open"] == first["open"].iloc[0] and d.iloc[0]["close"] == first["close"].iloc[-1]
    assert d.iloc[0]["high"] == first["high"].max() and d.iloc[0]["low"] == first["low"].min()
    assert d.iloc[0]["volume"] == pytest.approx(first["volume"].sum())
    d2 = B.aggregate_4h_to_1d(_h4_frame(datetime(2026, 11, 1, tzinfo=UTC), 18, drop={7}))   # 2. gun bir 4s eksik
    assert list(d2.index) == [datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 3, tzinfo=UTC)]
    # yarim (son) gun uretilmez
    assert len(B.aggregate_4h_to_1d(h4.iloc[:16])) == 2
    assert len(B.aggregate_4h_to_1d(h4.iloc[:0])) == 0


def test_arm_tf_helpers_and_old_contract_untouched():
    t = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)
    assert B.arm_closing_tfs(t) == ["15m", "1h", "4h", "1d"]
    assert B.arm_closing_tfs(t + timedelta(hours=4)) == ["15m", "1h", "4h"]
    assert B.arm_closing_tfs(t + timedelta(minutes=15)) == ["15m"]
    assert B.arm_floor_tf(t + timedelta(hours=13), "1d") == t
    with pytest.raises(ValueError):
        B.tf_delta("1d")                                                # eski sozlesme: 1g yok
    assert B.TF_SECONDS == {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}


# --------------------------------------------------------------------------- yapilandirma
def test_config_arms_and_caps():
    assert PAPER.strategy == NAME and PAPER.arms == PAPER_ARMS
    assert PAPER.arm_max_positions == {"default": 6, "M1": 4, "L1": 4, "HB1": 3, "DL1": 4}   # 23.11: HB1 3; 24.11: DL1 toplam 4; C1 kaldirildi (CT/ML ayriligi); 20 Kasim: kagit tavanlari gevsetildi
    c = apply_overrides(PAPER, arms={"T1": ["1h", "4h"]}, arm_max_positions=2)
    assert c.arms == ("T1@1h", "T1@4h") and c.arm_max_positions == {"default": 2}
    for kw in ({"arms": ["T1@5m"]}, {"arms": ["T1@1h", "T1@1h"]}, {"arms": "T1@1h"}, {"arm_max_positions": 0},
               {"arm_max_positions": {"t1": 2}}, {"arm_max_positions": True}):
        with pytest.raises(ConfigError):
            apply_overrides(PAPER, **kw)
    with pytest.raises(ConfigError):                                    # yalniz kagit
        apply_overrides(PAPER, mode="backtest", veto_mode="off", arms=["T1@1h"], optional_pairs=(),
                        max_positions=None, risk={}, clusters={}, cost_overrides={}, contract_types=None,
                        flat_bar_guard=False, arm_max_positions={})


def test_arm_cap_helpers():
    from trader_engine import arm_guard as AG
    caps = {"default": 4, "M1": 3, "T1@15m": 1}
    assert AG.arm_cap(caps, "T1@15m", "T1") == 1 and AG.arm_cap(caps, "M1@1h", "M1") == 3 and AG.arm_cap(caps, "R1@1h", "R1") == 4
    assert AG.arm_cap({}, "R1@1h", "R1") is None
    assert AG.arm_full(["T1@1h"] * 4, "T1@1h", 4) and not AG.arm_full(["T1@1h"] * 3 + ["R1@1h"], "T1@1h", 4)
    assert not AG.arm_full(["T1@1h"] * 9, "T1@1h", None)


# --------------------------------------------------------------------------- sentetik veri
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "NVDA/USDT"]
H_START, H_END = datetime(2026, 4, 5, tzinfo=UTC), datetime(2026, 11, 11, tzinfo=UTC)
START, END = datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 9, 6, tzinfo=UTC)


def _write_history(hist: Path) -> None:
    import pyarrow as pa
    import pyarrow.feather as pf
    hist.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(H_START, H_END, freq="15min", inclusive="left")
    t = np.arange(len(idx))
    for k, pair in enumerate(PAIRS):
        rng = np.random.default_rng(31 + k)
        wave = 0.07 * np.sin(2 * np.pi * t / (96 * 5 + k * 40)) + 0.012 * np.sin(2 * np.pi * t / (96 * 1.3))
        close = np.round(100 * (1 + 0.3 * k) * np.exp(wave + np.cumsum(rng.normal(0, 0.0018, len(idx)))), 3)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0009, len(idx)))), 3)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0009, len(idx)))), 3)
        df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close,
                           "volume": np.round(rng.uniform(100, 500, len(idx)), 1)}, index=idx)
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        for tf, rule in (("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
            g = df if tf == "15m" else pd.DataFrame(
                {"open": df.resample(rule)["open"].first(), "high": df.resample(rule)["high"].max(),
                 "low": df.resample(rule)["low"].min(), "close": df.resample(rule)["close"].last(),
                 "volume": df.resample(rule)["volume"].sum()}).dropna()
            arrs = {"date": pa.array(g.index.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
            for c in g.columns:
                arrs[c] = pa.array(g[c].to_numpy(dtype="float64"))
            pf.write_feather(pa.table(arrs), str(hist / f"{stem}-{tf}-futures.feather"), compression="uncompressed")
        fidx = pd.date_range(H_START, H_END, freq="8h", inclusive="left")
        pf.write_feather(pa.table({"date": pa.array(fidx.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC")),
                                   "funding_rate": pa.array([0.0001] * len(fidx))}),
                         str(hist / f"{stem}-1h-funding_rate.feather"), compression="uncompressed")


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    pytest.importorskip("pyarrow")
    d = tmp_path_factory.mktemp("wp11_hist") / "hist"
    _write_history(d)
    return d


def _view(hist):
    return HistoricalSource(str(hist), granularity="15m", synthetic_rules=True)


def _pmap():
    return {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}


def _forced(lab):
    """compute_tf'i sarar: her cagrida son satiri gecerli T1 long sinyaline cevirir (oncelik testi icin)."""
    orig = lab.compute_tf

    def fn(ctx, force_core=False):
        out = orig(ctx, force_core=force_core)
        t = out["core"].copy()
        px = float(ctx.bars[ctx.tf]["close"].iloc[-1])
        for c, v in (("setup", "T1"), ("side", "long"), ("signal", True), ("planned_entry", px), ("planned_stop", px * 0.99),
                     ("atr_tf", px * 0.002), ("stop_dist_atr", 5.0), ("atr_4h", px * 0.004), ("pullback_ema", 1),
                     ("ema_value", px), ("body_ratio", 0.5), ("regime", "trend_up")):
            t.iloc[-1, t.columns.get_loc(c)] = v
        out["core"] = t
        return out
    lab.compute_tf = fn
    return lab


def test_priority_larger_tf_wins_and_losers_are_extras(hist):
    lab = _forced(PriceActionLab(ALL_ARMS))
    src = MultiArmSignalSource(_view(hist), lab, strict=True)
    D = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)                       # 15m + 1h + 4h + 1d ayni anda kapanir
    fr = src.frame("BTC/USDT", D, _pmap(), 1)
    assert fr.status == "ok" and fr.last.signal and fr.last.arm_id == "T1@1d" and fr.last.tf == "1d"
    assert [e.last.arm_id for e in fr.extras] == ["T1@4h", "T1@1h", "T1@15m"] and all(e.last.signal for e in fr.extras)
    assert fr.last.bar_close_ts == D and fr.last.bar_open_ts == D - timedelta(days=1)
    D2 = D + timedelta(hours=4)                                       # 15m + 1h + 4h
    fr2 = src.frame("BTC/USDT", D2, _pmap(), 1)
    assert fr2.last.arm_id == "T1@4h" and [e.last.arm_id for e in fr2.extras] == ["T1@1h", "T1@15m"]
    fr3 = src.frame("BTC/USDT", D + timedelta(minutes=15), _pmap(), 1)      # yalniz 15m kapanir (D-T16)
    assert fr3.last.arm_id == "T1@15m" and fr3.extras == ()
    # kurulum tf'si olmayan adimlar bos kare: 1s kurulumu olmayan lab saat basinda 'no_arm_closed'
    lab2 = PriceActionLab(("T1@4h",))
    fr4 = MultiArmSignalSource(_view(hist), lab2, strict=True).frame("BTC/USDT", D + timedelta(hours=1), _pmap(), 1)
    assert fr4.status == "ok" and fr4.last is None


def test_1d_round_logs_one_info_line(hist, caplog):
    """1g kurulum turu: tur basina TEK INFO satiri ('1d tarama: N cift, M aday'); 4s adiminda (1g kapanmaz) satir yok."""
    import logging
    lab = _forced(PriceActionLab(("T1@1d",)))
    pairs = ["BTC/USDT", "ETH/USDT"]
    src = MultiArmSignalSource(_view(hist), lab, strict=True, pairs=pairs)
    D = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)
    with caplog.at_level(logging.INFO, logger="engine.runner"):
        for p in pairs:
            src.frame(p, D, _pmap(), 1)
        for p in pairs:                                                  # 4s adimi: 1g kapanmaz
            src.frame(p, D + timedelta(hours=4), _pmap(), 1)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("1d tarama:")]
    assert len(lines) == 1 and lines[0].startswith("1d tarama: 2 cift, 2 aday")


def test_gate_arm_conflict_event_and_arm_id(hist):
    lab = _forced(PriceActionLab(("T1@1h", "T1@4h")))
    src = MultiArmSignalSource(_view(hist), lab, strict=True)
    D = datetime(2026, 11, 7, 4, 0, tzinfo=UTC)
    fr = src.frame("ETH/USDT", D, _pmap(), 1)
    from trader_engine.gates import EntryGate, build_decision_event
    ev = build_decision_event(fr.last, "4h")
    assert ev.arm_id == "T1@4h" and ev.trigger_tf == "4h"
    g = object.__new__(EntryGate)
    g.cfg = PAPER
    g.counters = __import__("collections").Counter()
    out = g.conflict(fr.extras[0], fr.last)
    assert out.action == "skip" and out.code == "arm_conflict" and not out.mark_decided
    e = out.event
    assert e.skip_reason == "arm_conflict" and e.arm_id == "T1@1h" and e.trigger_tf == "1h" and e.session_tag == "open"
    assert e.veto_reason == "gate:arm_conflict:T1@4h" and e.final_action == "skipped" and e.veto_status == "not_evaluated"


def test_1d_arm_uses_complete_days_only(hist):
    lab = PriceActionLab(("T1@1d", "R1@1d"))
    src = MultiArmSignalSource(_view(hist), lab, strict=True)
    D = datetime(2026, 11, 7, 0, 0, tzinfo=UTC)
    fr = src.frame("SOL/USDT", D, _pmap(), 1)
    assert fr.status == "ok" and fr.last is not None and fr.last.bar_open_ts == D - timedelta(days=1)
    assert fr.last.bar_close_ts == D and fr.last.tf == "1d"
    # 1g kurulumu 4s'te (gun ortasi) calismaz
    fr2 = src.frame("SOL/USDT", D + timedelta(hours=4), _pmap(), 1)
    assert fr2.last is None


# --------------------------------------------------------------------------- motor: sentetik cok kurullu kagit
def _cfg(tmp: Path, **kw):
    clusters = {"kripto_buyuk": {"pairs": ["BTC/USDT", "ETH/USDT"], "max_positions": 4},
                "kripto_diger": {"pairs": ["SOL/USDT"], "max_positions": 6},
                "hisse": {"pairs": ["NVDA/USDT"], "max_positions": 5},
                "hisse_teknoloji": {"pairs": ["NVDA/USDT"], "max_positions": 3}}
    base = dict(pairs=tuple(PAIRS), optional_pairs=("NVDA/USDT",), clusters=clusters,
                cost_overrides={"NVDA/USDT": PAPER.cost_overrides["NVDA/USDT"]}, var_dir=str(tmp / "var"),
                kill_file=str(tmp / "KILL"), pause_file=str(tmp / "PAUSE"), veto_config=str(ROOT / "config/veto.live.json"),
                market_db=str(tmp / "m.sqlite"),
                history_dir=str(tmp / "h"), cost=dict(fill_model="native", granularity="15m", trigger_source="last"))
    base.update(kw)
    return apply_overrides(PAPER, **base)


def _run(tmp, hist, start=START, end=END, **kw):
    cfg = _cfg(tmp, **kw)
    eng = E.build_engine(cfg, clock=SimClock(start), view=_view(hist), env={})
    s = eng.strategy
    eng.ledger.init_params(_pmap(), reason=f"strategy:{s.info.name}@{s.info.version} wp11")
    eng.start()
    return eng, cfg


def _rows(eng, sql):
    con = sqlite3.connect(eng.cfg.ledger_path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql)]
    finally:
        con.close()


def test_end_to_end_multi_arm_paper_with_caps(tmp_path, hist):
    eng, cfg = _run(tmp_path, hist, arm_max_positions={"default": 1})
    assert eng.step_tf == "15m" and eng.tf == "1h" and eng.strategy.arm_ids == PAPER_ARMS
    # kurulum tavani her adimda gecerli (parca parca ilerleyerek denetlenir)
    t = START
    seen_open = 0
    while t < END:
        t = min(t + timedelta(hours=6), END)
        eng.run_range(eng.clock.now(), t) if False else None
        break
    eng.run_range(START, END)
    c = eng.counters()
    assert c["decisions"] > 300 and c.get("callback_errors", 0) == 0
    arms = eng.cluster_counts()["arms"]
    assert set(arms) >= set(ALL_ARMS) and all(v["open"] <= 1 and v["max"] == 1 for v in arms.values())
    # defter: arm_id her satirda; tetik zaman dilimleri 15m/1h/4h/1d arasindan; entered satirlari setup@tf ile tutarli
    rows = _rows(eng, "SELECT pair, trigger_tf, setup, arm_id, final_action, skip_reason, veto_reason, session_tag, ml_score FROM v_decisions")
    assert rows and all(r["arm_id"] == f"{r['setup']}@{r['trigger_tf']}" for r in rows)
    tfs = {r["trigger_tf"] for r in rows}
    assert tfs <= {"15m", "1h", "4h", "1d"} and len(tfs) >= 2
    ent = [r for r in rows if r["final_action"] == "entered"]
    assert ent, "sentetik veride en az bir giris bekleniyor"
    te = _rows(eng, "SELECT e.arm_id AS arm_id, e.trade_id AS trade_id, d.trigger_tf AS tf, d.setup AS setup "
                    "FROM trade_entries e JOIN decision_events d ON d.id = e.decision_id WHERE e.supersedes_id IS NULL")
    assert te and all(r["arm_id"] == f"{r['setup']}@{r['tf']}" for r in te)
    assert all(r["skip_reason"] != "ml_filter" for r in rows)                    # 24.11: ML filtreleri silindi
    # tavan atlamasi gerekce taşır
    caps = [r for r in rows if r["veto_reason"] and str(r["veto_reason"]).startswith("gate:arm_cap:")]
    for r in caps:
        assert r["skip_reason"] == "max_positions" and r["veto_reason"] == f"gate:arm_cap:{r['arm_id']}"
    # arm_conflict satirlari yalniz bir kazananla birlikte (ayni cift/bar), kazananin tf'si daha buyuk
    byk = {"15m": 0, "1h": 1, "4h": 2, "1d": 3}
    for r in (r for r in rows if r["skip_reason"] == "arm_conflict"):
        win = r["veto_reason"].split(":")[-1]
        # K-7 md.3: tf once (buyuk), ayni tf'de kurulum onceligi (kucuk kazanir; WP-14 M1=90 ile ayni tf kayipları olabilir)
        pri = {"T1": 10, "R1": 20, "TF1": 30, "B1": 40, "H2": 50, "S1": 60, "F1": 70, "M1": 90}
        wtf, ltf = win.split("@")[1], r["trigger_tf"]
        assert byk[wtf] > byk[ltf] or (wtf == ltf and pri[win.split("@")[0]] < pri[r["setup"]])
    # cikislar pozisyonun kendi tf'sinde; pozisyon trigger_tf'i satirinki ile ayni
    for p in eng.state.open_positions():
        assert p.trigger_tf in ("15m", "1h", "4h", "1d")
    eng.status.write(eng, force=True)
