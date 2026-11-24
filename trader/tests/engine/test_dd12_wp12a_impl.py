"""DD-12 WP-12a uygulayici duman testleri: TF1 ve B1 kurulumlari + K-7 sozlesme duzeltmeleri (EXIT_MODE, FEATURES,
PRIORITY). Ag yok; yalniz sentetik seriler. Bagimsiz spec testleri test_dd12_wp12a_spec.py'dadir (ayri yazar)."""
from __future__ import annotations

import dataclasses
import importlib
import types
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core import signals as S
from trader_engine import gates as G
from trader_engine import position_manager as PM
from trader_engine import strategy_runner as SR
from trader_engine.strategies import arms as A
from trader_engine.strategies.arms import ArmInput
from trader_engine.strategies.arms import _pa as P
from trader_engine.strategies.arms import b1, tf1
from trader_engine.strategies.base import StrategyError, StrategyInfo, validate_table
from trader_engine.types import Position

UTC = timezone.utc
OHLC = ["open", "high", "low", "close"]


# ----------------------------------------------------------------------------------------------- yardimcilar
def _regime_frame(idx, labels) -> pd.DataFrame:
    return pd.DataFrame({"regime": list(labels), "rh": np.nan, "rl": np.nan, "rh_touches": 0, "rl_touches": 0,
                         "atr": 1.0, "atr_ratio": 1.0}, index=idx)          # 4s ATR (sonlu; gercek rejimde de sonlu)


def _inp(trig: pd.DataFrame, labels, tf: str = "1h") -> ArmInput:
    params = S.SignalParams()
    core = S.compute_signals(trig[OHLC], _regime_frame(trig.index, labels), params)
    return ArmInput(pair="T/X", tf=tf, D=trig.index[-1].to_pydatetime(), trig=trig, h4=trig, params=params,
                    core_fn=lambda: core)


def _bars(rows, start="2026-01-01") -> pd.DataFrame:
    o, h, l, c = (np.asarray(x, dtype=float) for x in zip(*rows))
    idx = pd.date_range(start, periods=len(rows), freq="h")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=idx)


def _random_bars(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = 100 + np.cumsum(rng.normal(0.03, 0.6, n))
    o = np.r_[closes[0], closes[:-1]] + rng.normal(0, 0.2, n)
    hi = np.maximum(o, closes) + np.abs(rng.normal(0.3, 0.2, n))
    lo = np.minimum(o, closes) - np.abs(rng.normal(0.3, 0.2, n))
    idx = pd.date_range("2026-02-01", periods=n, freq="h")
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": closes, "volume": 1.0}, index=idx)


def _random_regimes(n: int, seed: int) -> list[str]:
    rng = np.random.default_rng(seed + 1000)
    return list(rng.choice(["trend_up", "trend_down", "range", "unclear"], size=n))


def _b1_scenario() -> pd.DataFrame:
    """Seviye 101: iki ayrik dokunus; 41. bar kirilim; 44. bar retest (dipte 100,8); 45. bar yukari kapanis."""
    rows = []
    for k in range(70):
        if k <= 36 and k % 2 == 0:
            rows.append((100.5, 101.0, 99.0, 100.5))
        elif k <= 40:
            rows.append((100.5, 100.0, 99.0, 100.2))
        elif k == 41:
            rows.append((101.0, 102.7, 100.9, 102.5))
        elif k == 42:
            rows.append((102.5, 102.9, 101.5, 102.0))
        elif k == 43:
            rows.append((102.0, 102.4, 101.2, 101.8))
        elif k == 44:
            rows.append((101.8, 101.9, 100.8, 101.2))
        elif k == 45:
            rows.append((101.0, 101.9, 100.9, 101.6))
        elif k == 46:
            rows.append((101.6, 102.0, 101.4, 101.9))
        else:
            rows.append((101.9, 102.1, 101.6, 101.9))
    return _bars(rows)


def _tf1_scenario() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    closes = list(100 + np.cumsum(rng.normal(0.02, 0.15, 150)))
    closes += [closes[-1] + 0.1, closes[-1] + 0.2, closes[-1] + 0.3, closes[-1] + 1.0]   # govde esigi disinda
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.3, "low": np.minimum(o, c) - 0.3, "close": c,
                         "volume": 1.0}, index=idx)


def _pos(setup: str, side: str = "long", **kw) -> Position:
    base = dict(trade_id=1, bot="paper", pair="T/X", side=side, setup=setup, status="open", decision_id=1,
                signal_bar_close_ts=datetime(2026, 1, 1, tzinfo=UTC), entry_ts=datetime(2026, 1, 1, tzinfo=UTC),
                entry_bar_open=datetime(2026, 1, 1, tzinfo=UTC), entry_price=100.0, qty=1.0, leverage=3,
                initial_stop=98.0, current_stop=98.0, stop_seq=0, stop_client_id=None, planned_target=None,
                trail_atr=3.0, param_version_id=1, trigger_tf="1h", risk_amount=2.0, margin=10.0, rh=None, rl=None,
                fee_entry=0.0, funding_paid=0.0, mfe_price=None, mae_price=None, exit_reason=None,
                exit_client_id=None, closed_ts=None)
    base.update(kw)
    return Position(**base)


def _ctx(highs, lows, atrs, regime="trend_up", last_close=100.0, n_closed=None) -> PM.ExitContext:
    h = np.asarray(highs, float)
    return PM.ExitContext(bar_close_ts=datetime(2026, 1, 1, tzinfo=UTC), highs=h, lows=np.asarray(lows, float),
                          atrs=np.asarray(atrs, float), regime_last=regime, last_close=last_close,
                          n_closed=len(h) if n_closed is None else n_closed)


INFO = StrategyInfo("t", "1", ("T1", "R1", "TF1", "B1"), ("1h",), ("1h",), {}, {}, {}, (), True)


# ----------------------------------------------------------------------------------------------- sozlesme
def test_discovery_finds_new_setups_and_contract_fields():
    mods = A.discover()
    assert {"T1", "R1", "TF1", "B1"} <= set(mods)
    assert A.exit_mode("T1") == "trail" and A.exit_mode("R1") == "target"
    assert A.exit_mode("TF1") == "trail" and A.exit_mode("B1") == "target"
    assert A.exit_mode("ZZ") is None
    for name in ("TF1", "B1"):
        m = mods[name]
        assert m.CORE is False
        assert tuple(m.TIMEFRAMES) == ("15m", "1h", "4h", "1d")
        assert 1 <= len(m.FEATURES) <= 6
        assert set(m.FEATURES.values()) <= set(A.CARRIERS)


def test_priority_order_within_timeframe():
    order = ["T1", "R1", "TF1", "B1"]
    prios = [A.priority_of(s) for s in order]
    assert prios == sorted(prios) and len(set(prios)) == len(prios)
    assert A.priority_of(None) == 1000                                          # bilinmeyen/None en sona


def test_features_maps_are_bounded_and_use_carriers_only():
    assert A.features_of("TF1") == {"brk_dist_atr": "edge_dist_atr", "ema_value": "ema_value", "body_ratio": "body_ratio",
                                    "ext_atr": "wick_ratio", "brk_n": "pullback_ema"}
    assert len(A.features_of("B1")) == 6
    assert A.features_of("T1") == {"pullback_ema": "pullback_ema", "ema_value": "ema_value", "body_ratio": "body_ratio"}


@pytest.mark.parametrize("attrs", [
    {"EXIT_MODE": "bogus", "PRIORITY": 1, "FEATURES": {}},
    {"EXIT_MODE": "trail", "PRIORITY": "x", "FEATURES": {}},
    {"EXIT_MODE": "trail", "PRIORITY": 1, "FEATURES": {"a": "rh"}},
    {"EXIT_MODE": "trail", "PRIORITY": 1, "FEATURES": {"atr_tf": "ema_value"}},
    {"EXIT_MODE": "trail", "PRIORITY": 1, "FEATURES": {f"k{i}": "rr" for i in range(7)}},
])
def test_invalid_arm_contract_is_rejected_at_load(attrs):
    mod = types.ModuleType("x")
    for k, v in attrs.items():
        setattr(mod, k, v)
    with pytest.raises(A.ArmError):
        A.validate_arm(mod, "x")


def test_missing_exit_mode_is_rejected_at_load():
    mod = types.ModuleType("noexit")
    mod.PRIORITY, mod.FEATURES = 1, {}
    with pytest.raises(A.ArmError):
        A.validate_arm(mod, "noexit")


def test_arm_id_parsing_accepts_new_setups_and_lab_accepts_them():
    lab = importlib.import_module("trader_engine.strategies.lab")
    lab.PriceActionLab(arms=("TF1@1h", "B1@4h", "B1@1d", "T1@1h", "R1@1h"))
    with pytest.raises(StrategyError):
        lab.PriceActionLab(arms=("TF1@5m",))


# ----------------------------------------------------------------------------------------------- cikis
def test_evaluate_exit_t1_r1_paths_unchanged_shapes():
    # T1 (trail): 1R ilerlemeden sonra iz suren stop kurulur; geri gitmez
    p = _pos("T1", "long", entry_price=100.0, initial_stop=98.0, current_stop=98.0, trail_atr=3.0)
    d = PM.evaluate_exit(p, _ctx([101.0, 106.0], [100.0, 104.0], [2.0, 2.0], last_close=105.0))
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(106.0 - 3 * 2.0)
    # R1 (target): hedef degince cikis
    r = _pos("R1", "long", planned_target=104.0, entry_price=100.0, initial_stop=98.0, current_stop=98.0)
    assert PM.evaluate_exit(r, _ctx([103.0, 105.0], [101.0, 102.0], [2.0, 2.0])).reason == "target"


def test_evaluate_exit_tf1_trails_and_b1_targets():
    tf = _pos("TF1", "long", entry_price=100.0, initial_stop=98.0, current_stop=98.0, trail_atr=3.0)
    d = PM.evaluate_exit(tf, _ctx([101.0, 106.0], [100.0, 104.0], [2.0, 2.0], last_close=105.0))
    assert d.kind == "stop_update" and d.new_stop == pytest.approx(106.0 - 6.0)          # iz suren stop devreye girer
    assert PM.evaluate_exit(tf, _ctx([101.0], [99.0], [2.0], regime="trend_down")).reason == "regime_flip"
    b = _pos("B1", "long", planned_target=104.0, entry_price=100.0, initial_stop=98.0, current_stop=98.0,
             trail_atr=0.0)
    assert PM.evaluate_exit(b, _ctx([103.0, 105.0], [101.0, 102.0], [2.0, 2.0])).reason == "target"  # hedef denetlenir
    assert PM.evaluate_exit(b, _ctx([101.0] * 48, [99.5] * 48, [2.0] * 48)).reason == "time_stop"
    # trail_stop_value: B1 (target) iz suren stop kurmaz
    assert PM.trail_stop_value(b, _ctx([106.0], [104.0], [2.0]))[1] is False


def test_unknown_setup_is_force_exit():
    assert PM.evaluate_exit(_pos("ZZ"), _ctx([101.0], [99.0], [2.0])).reason == "force_exit"


# ----------------------------------------------------------------------------------------------- TF1 / B1 sinyal
def test_tf1_long_breakout_plan_values_and_validity():
    trig = _tf1_scenario()
    out = tf1.compute(_inp(trig, ["trend_up"] * len(trig)))
    validate_table(out, INFO, trig.index)
    row = out.iloc[-1]
    assert bool(row["signal"]) and row["setup"] == "TF1" and row["side"] == "long"
    hc = trig["close"].iloc[-51:-1].max()
    atr = float(P.prepare(_inp(trig, ["trend_up"] * len(trig))).atr[-1])
    assert row["planned_stop"] == pytest.approx(hc - atr, rel=1e-9)            # stop = HC - 1 ATR
    assert np.isnan(row["planned_target"])                                     # hedef yok
    assert row["pullback_ema"] == 50 and row["reasons"].startswith("TF1_long:trend_up")


def test_tf1_no_candidate_when_not_trend_or_warmup_or_volatile():
    trig = _tf1_scenario()
    for labels in (["range"] * len(trig), ["volatile"] * len(trig)):
        out = tf1.compute(_inp(trig, labels))
        assert not out["setup"].notna().any()
    short = trig.iloc[:119]                                                    # len < LOOKBACK (120)
    assert not tf1.compute(_inp(short, ["trend_up"] * len(short)))["setup"].notna().any()


def test_b1_retest_signal_matches_spec_arithmetic_and_single_signal_per_breakout():
    trig = _b1_scenario()
    out = b1.compute(_inp(trig, ["trend_up"] * len(trig)))
    validate_table(out, INFO, trig.index)
    sig = out[out["setup"].notna()]
    assert list(sig.index) == [trig.index[45]]                                 # yalniz bir sinyal (kirilim basina tek)
    r = sig.iloc[0]
    assert r["side"] == "long" and bool(r["signal"]) and r["skip_reason"] is None
    assert r["planned_entry"] == pytest.approx(101.6)
    assert r["ema_value"] == pytest.approx(101.0)                              # seviye L
    assert r["pullback_ema"] == 4                                              # bars_since_brk = t - i0
    assert r["rr"] == pytest.approx(2.0)
    entry, stop = r["planned_entry"], r["planned_stop"]
    assert r["planned_target"] == pytest.approx(entry + 2.0 * (entry - stop))  # hedef = c + 2R
    assert stop == pytest.approx(100.8 - 0.3 * float(P.prepare(_inp(trig, ["trend_up"] * len(trig))).atr[45]))


def test_b1_breakout_without_retest_gives_no_candidate():
    base = _b1_scenario()
    rows = [(r.open, r.high, r.low, r.close) for r in base.itertuples(index=False)]
    for k in range(42, len(rows)):                                              # seviyeye hic dokunmadan yukari gidis
        rows[k] = (102.2, 102.9, 102.0, 102.5)
    out = b1.compute(_inp(_bars(rows), ["trend_up"] * len(rows)))
    assert not out["setup"].notna().any()


def test_b1_volatile_regime_gives_no_candidate():
    trig = _b1_scenario()
    assert not b1.compute(_inp(trig, ["volatile"] * len(trig)))["setup"].notna().any()


# ----------------------------------------------------------------------------------------------- nedensellik / simetri
@pytest.mark.parametrize("mod,labels_kind", [(tf1, "trend"), (b1, "mixed")])
def test_causality_prefix_equals_full_row(mod, labels_kind):
    """Kesme testi (K-ORT-1): compute(trig[:k+1]) son satiri == compute(trig)'in k. satiri (tum sutunlar)."""
    n = 260
    trig = _random_bars(n, seed=11)
    labels = ["trend_up"] * n if labels_kind == "trend" else _random_regimes(n, seed=11)
    full = mod.compute(_inp(trig, labels))
    assert full["setup"].notna().any(), "sinyal yok: nedensellik testi bos kalir"
    for k in range(120, n, 7):
        pref = mod.compute(_inp(trig.iloc[:k + 1], labels[:k + 1]))
        assert pref.iloc[-1].equals(full.iloc[k]), k


@pytest.mark.parametrize("mod", [tf1, b1])
def test_future_poison_does_not_change_past_rows(mod):
    n = 240
    trig = _random_bars(n, seed=5)
    labels = _random_regimes(n, seed=5)
    base = mod.compute(_inp(trig, labels))
    assert base["setup"].notna().any(), "sinyal yok: gelecek zehiri testi bos kalir"
    t = 150
    poisoned = trig.copy()
    poisoned.iloc[t + 1:, :4] = 1e6
    got = mod.compute(_inp(poisoned, labels))
    assert base.iloc[:t + 1].equals(got.iloc[:t + 1])


@pytest.mark.parametrize("mod", [tf1, b1])
def test_deterministic_and_input_not_mutated(mod):
    trig = _random_bars(200, seed=2)
    labels = _random_regimes(200, seed=2)
    before = trig.copy()
    inp = _inp(trig, labels)
    a = mod.compute(inp)
    b = mod.compute(inp)
    assert a.equals(b)
    assert trig.equals(before)


def test_tf1_short_is_price_mirror_of_long():
    """Ayna testi (K-ORT-4): short, long'un fiyat aynasi (p -> C - p) olarak ayni barlarda sinyal verir."""
    trig = _tf1_scenario()
    n = len(trig)
    C = 400.0
    mirror = trig.copy()
    mirror["open"] = C - trig["open"]
    mirror["high"] = C - trig["low"]
    mirror["low"] = C - trig["high"]
    mirror["close"] = C - trig["close"]
    long_m = tf1.compute(_inp(trig, ["trend_up"] * n))                  # long: gercek seri
    short = tf1.compute(_inp(mirror, ["trend_down"] * n))              # short: ayna seri (dususte)
    s_rows = short[short["setup"].notna()]
    l_rows = long_m[long_m["setup"].notna()]
    assert list(s_rows.index) == list(l_rows.index) and len(s_rows) > 0
    for i in s_rows.index:
        assert s_rows.loc[i, "side"] == "short" and l_rows.loc[i, "side"] == "long"
        assert s_rows.loc[i, "planned_stop"] == pytest.approx(C - l_rows.loc[i, "planned_stop"])
        assert s_rows.loc[i, "planned_entry"] == pytest.approx(C - l_rows.loc[i, "planned_entry"])
        assert bool(s_rows.loc[i, "signal"]) == bool(l_rows.loc[i, "signal"])


# ----------------------------------------------------------------------------------------------- ozellik / defter
def _row_from(df: pd.DataFrame, i: int, setup_tf: str):
    r = df.iloc[i].copy()
    return SR._to_row("T/X", df.index[i].to_pydatetime(), df.index[i].to_pydatetime(), r, 1)


def test_gates_features_t1_r1_legacy_keys_and_order():
    trig = _tf1_scenario()
    base = tf1.compute(_inp(trig, ["trend_up"] * len(trig)))
    row = _row_from(base, len(base) - 1, "1h")
    row = dataclasses.replace(row, setup="T1", planned_target=None)
    feats = G._features(row)
    # T1 defter anahtarlari eskiyle ayni sirada: ortak uc, T1 uclusu, rh/rl dokunma sayilari
    assert list(feats) == ["atr_tf", "stop_dist_atr", "atr_4h", "pullback_ema", "ema_value", "body_ratio",
                           "rh_touches", "rl_touches"]
    assert isinstance(feats["pullback_ema"], int) and isinstance(feats["rh_touches"], int)


def test_gates_features_tf1_and_b1_use_arm_mapping_and_ledger_accepts():
    t = _tf1_scenario()
    tf_out = tf1.compute(_inp(t, ["trend_up"] * len(t)))
    row = _row_from(tf_out, len(tf_out) - 1, "1h")
    feats = G._features(row)
    assert set(feats) >= {"atr_tf", "stop_dist_atr", "atr_4h", "brk_dist_atr", "ema_value", "body_ratio", "ext_atr",
                          "brk_n", "rh_touches", "rl_touches"}
    assert isinstance(feats["brk_n"], int) and feats["brk_n"] == 50
    assert not any(k in feats for k in ("rr", "level", "rh", "rl"))
    stored = L.Ledger._prep_features(feats, "TF1")
    assert "brk_n" in stored

    b = _b1_scenario()
    b_out = b1.compute(_inp(b, ["trend_up"] * len(b)))
    brow = _row_from(b_out, 45, "1h")
    bfeats = G._features(brow)
    assert {"level", "brk_dist_atr", "retest_depth_atr", "body_ratio", "bars_since_brk", "rr"} <= set(bfeats)
    assert bfeats["bars_since_brk"] == 4 and bfeats["rr"] == pytest.approx(2.0)
    L.Ledger._prep_features(bfeats, "B1")


def test_strategy_runner_sorts_by_setup_priority_within_timeframe():
    """Ayni zaman diliminde T1 TF1'in onunde (K-7 madde 3). Kaynak denetimi: siralama anahtari kurulum onceligini okur."""
    import inspect
    src = inspect.getsource(SR.MultiArmSignalSource._build_multi)
    assert "priority_of(c[2].setup)" in src
    assert A.priority_of("T1") < A.priority_of("TF1") < A.priority_of("B1")


@pytest.mark.parametrize("tf", ["15m", "1h", "4h", "1d"])
@pytest.mark.parametrize("mod", [tf1, b1])
def test_all_timeframes_validate_and_warmup_is_quiet(mod, tf):
    trig = _random_bars(400, seed=21)
    labels = ["trend_up"] * 400
    out = mod.compute(_inp(trig, labels, tf=tf))
    validate_table(out, INFO, trig.index)
    assert set(out.columns) == set(S.SIGNAL_COLUMNS)
    short = trig.iloc[:mod.LOOKBACK[tf] - 1]
    assert not mod.compute(_inp(short, ["trend_up"] * len(short), tf=tf))["setup"].notna().any()


def test_b1_both_sides_same_bar_yields_no_candidate():
    """K-0 'Cift yon': ayni barda iki yonun kosulu -> aday yok (reasons '<kod>:both_sides')."""
    trig = _b1_scenario()
    labels = ["range"] * len(trig)                              # range: iki yon de izinli
    out = b1.compute(_inp(trig, labels))
    both = out["reasons"].astype(str).str.endswith(":both_sides")
    assert not (both & out["setup"].notna()).any()
