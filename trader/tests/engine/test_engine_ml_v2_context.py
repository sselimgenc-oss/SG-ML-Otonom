"""ML-G5: motor yolu (WindowedSignalSource, bayrakli) r02/r03 ozelliklerini iki gecisli uretir ve egitim yoluyla ayni puani verir;
bayrak kapaliyken (ml_v2=None / ml_features=v1) davranis degismez; precomputed `model=` gecisi. Yalniz sentetik veri."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core.ml_features import BAR, BTC, ETH
from trader_core.ml_features_v2 import R02_FEATURE_NAMES, R03_FEATURE_NAMES, feature_frame_v2
from trader_core.ml_live_v2 import LiveContextV2, funding_frame_from_points
from trader_core.ml_package import canon, feature_list_hash, load_model_view, sha256_text
from trader_core.signals import DEFAULT_SIGNAL_PARAMS
from trader_engine.config import load_engine_config
from trader_engine.strategies.base import StrategyContext
from trader_engine.strategies.price_action_v1_ml import make_v1b_ml
from trader_engine.strategy_runner import WindowedSignalSource
from trader_engine.types import FundingPoint

UTC = timezone.utc
START = pd.Timestamp("2024-01-01", tz="UTC")
N = 24 * 235
PAIRS_I = [BTC, ETH, "BNB/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT", "ADA/USDT:USDT",
           "TRX/USDT:USDT", "LINK/USDT:USDT", "AVAX/USDT:USDT"]
PAIRS_E = [p.split(":")[0] for p in PAIRS_I]
OHLC = {"open": "first", "high": "max", "low": "min", "close": "last"}
PARAMS = {**{k: getattr(DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}, "trigger_tf": "1h"}


class FakeView:
    def __init__(self, px, fund):
        self.px = {k.split(":")[0]: v for k, v in px.items()}
        self.fund = {k.split(":")[0]: v for k, v in fund.items()}
        self.calls = 0

    def bars(self, pair, tf, until, n=None, kind="last"):
        self.calls += 1
        d = self.px[pair]
        u = pd.Timestamp(until)
        if tf == "1h":
            out = d[d.index + BAR <= u]
        else:
            h = d[["open", "high", "low", "close"]].resample("4h", label="left", closed="left").agg(OHLC).dropna()
            out = h[h.index + pd.Timedelta("4h") <= u]
        return out.iloc[-n:] if n else out

    def contiguous_tail(self, pair, tf, until, max_n=5000):
        return 10 ** 6

    def funding(self, pair, start, end):
        f = self.fund[pair]
        f = f[(f.index >= pd.Timestamp(start)) & (f.index <= pd.Timestamp(end))]
        return [FundingPoint(pair=pair, ts=t.to_pydatetime(), rate=float(r), mark=None) for t, r in zip(f.index, f["funding_rate"])]


def _world():
    rng = np.random.default_rng(23)
    idx = pd.date_range(START, periods=N, freq="1h", tz="UTC")
    common = rng.normal(0, 0.004, N)
    px = {}
    for i, p in enumerate(PAIRS_I):
        c = 100 * (i + 1) * np.exp(np.cumsum(common * (1 + 0.1 * i) + rng.normal(0, 0.006, N)))
        o = np.concatenate([[c[0]], c[:-1]])
        px[p] = pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, N))),
                              "low": np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, N))), "close": c,
                              "volume": rng.uniform(50, 150, N)}, index=idx)
    ft = pd.date_range(START, periods=N // 8, freq="8h", tz="UTC")
    fund = {p: pd.DataFrame({"funding_rate": rng.normal(0.0001, 0.0003, len(ft))}, index=ft) for p in PAIRS_I}
    return px, fund


def _model(names, *, seed=1):
    rng = np.random.default_rng(seed)
    n = len(names)
    body = {"model": {"kind": "logistic", "n_features": n, "coef": list(rng.normal(0, 0.3, n)), "intercept": 0.1,
                      "mean": [0.0] * n, "std": [1.0] * n, "fill": [0.0] * n},
            "calibration": {"a": 1.0, "b": 0.0}, "threshold": 0.5}
    created = datetime(2024, 9, 1, tzinfo=UTC)
    meta = {"version": "t", "created_at": created.isoformat(), "expires_at": (created + timedelta(days=21)).isoformat(),
            "features": list(names), "feature_list_hash": feature_list_hash(names), "model_hash": sha256_text(canon(body)),
            "gate_passed": True, "user_approved": True}
    return load_model_view({"meta": meta, **body}, expected_features=names, ml_mode="shadow", now=created)


@pytest.fixture(scope="module")
def world():
    return _world()


def _candidate_bars(px):
    """Tum tabloda yerel v1b adaylari (egitim tarafi, bagimsiz): {D: [(pair_i, side, entry, stop)]}, en az 2 adayli mumlar once."""
    strat = make_v1b_ml()._inner
    out: dict[pd.Timestamp, list] = {}
    for p in PAIRS_I:
        d = px[p]
        h4 = d[["open", "high", "low", "close"]].resample("4h", label="left", closed="left").agg(OHLC).dropna()
        sig = strat.compute(StrategyContext(pair=p.split(":")[0], D=d.index[-1].to_pydatetime(), tf="1h", params=PARAMS,
                                            bars={"1h": d[["open", "high", "low", "close"]], "4h": h4}, last_exit=None))
        s = sig[sig["signal"].astype(bool) & (sig.index >= START + pd.Timedelta(days=205))]
        for t, r in s.iterrows():
            out.setdefault(t + BAR, []).append((p, r["side"], float(r["planned_entry"]), float(r["planned_stop"])))
    return out


@pytest.fixture(scope="module")
def cand_bars(world):
    return _candidate_bars(world[0])


@pytest.mark.parametrize("recipe,names", [("r02", R02_FEATURE_NAMES), ("r03", R03_FEATURE_NAMES)])
def test_engine_two_pass_score_equals_training_score(world, cand_bars, recipe, names):
    px, fund = world
    multi = sorted(t for t, v in cand_bars.items() if len(v) >= 2)
    assert multi, "sentetik veride >= 2 adayli mum yok"
    D = multi[0]
    expect_cands = cand_bars[D]
    model = _model(names)
    view = FakeView(px, fund)
    strat = make_v1b_ml()
    strat.set_ml_mode("shadow")
    ctx2 = LiveContextV2(recipe, PAIRS_E, lambda p, d, n: view.bars(p, "1h", d, n),
                         lambda p, a, b: funding_frame_from_points(view.funding(p, a, b)))
    src = WindowedSignalSource(view, strat, strict=True, ml_model=model, ml_v2=ctx2, pairs=PAIRS_E)
    frames = {p: src.frame(p, D.to_pydatetime(), PARAMS, 1) for p in PAIRS_E}
    # egitim yolu: bagimsiz aday listesi (tum tablo) -> feature_frame_v2 (tum cerceve) -> ayni model
    cdf = pd.DataFrame([{"ts": D, "pair": p, "side": s, "planned_entry": e, "planned_stop": st} for p, s, e, st in expect_cands])
    X = feature_frame_v2(px, cdf, funding=fund, recipe=recipe)[list(model.features)].to_numpy(float)
    want = {p.split(":")[0]: float(v) for p, v in zip(cdf["pair"], model.score(X))}
    got = {p: fr.last.ml_score for p, fr in frames.items() if fr.last is not None and fr.last.ml_score is not None}
    assert set(got) == set(want) and len(want) >= 2
    for p in want:
        assert got[p] == pytest.approx(want[p], abs=1e-6)               # reasons'taki 6 haneli yuvarlama
    assert src.counters["ml_v2_errors"] == 0 and strat.counters["ml_score_errors"] == 0
    # ikinci gecis: ayni mum sayisi TUM adaylar uzerinden (tek cift icin degil)
    if recipe == "r03":
        assert ctx2.features_for_bar(D.to_pydatetime(), pd.DataFrame(
            [{"pair": p.split(":")[0], "side": s, "planned_entry": e, "planned_stop": st} for p, s, e, st in expect_cands])
        ).rows[expect_cands[0][0].split(":")[0]]["f_same_bar_signals"] == float(len(expect_cands))


_WP11_FIELDS = ("arm_id", "tf", "vol_tahmin", "vol_asim")   # fikir 10 (23.11): oynaklik tahmini alanlari da yeni; # DD-12 WP-11: SignalRow'a eklenen alanlar (tekli stratejide None); eski ozetle karsilastirmada disarida


def _flag_off_digest(mod, px, fund, cand_bars, mode):
    """Bayrak kapali (ml_v2 yok) cikti ozeti: ilk 25 aday mumu x 10 cift; `mod` = strategy_runner modulu (eski/yeni)."""
    import hashlib
    from trader_core.ml_features import FEATURE_NAMES
    view = FakeView(px, fund)
    strat = make_v1b_ml()
    kw = {}
    if mode != "off":
        strat.set_ml_mode(mode)
        kw = {"ml_model": _model(FEATURE_NAMES)}
    src = mod.WindowedSignalSource(view, strat, strict=True, **kw)
    out = []
    for D in sorted(cand_bars)[:25]:
        for p in PAIRS_E:
            fr = src.frame(p, D.to_pydatetime(), PARAMS, 1)
            out.append((p, str(D), fr.status, fr.detail,
                        None if fr.last is None else tuple((k, format(v, ".10g") if isinstance(v, float) else repr(v)) for k, v in sorted(vars(fr.last).items())
                                                              if k not in _WP11_FIELDS)))
    return hashlib.sha256(repr(out).encode()).hexdigest()[:16], sum(1 for o in out if o[4] and dict(o[4]).get("signal") == "True"), view.calls


# Ondaliklar 10 anlamli basamakla ozetlenir (islemci SIMD farki son bitte iz birakir). G5 oncesi (strategy_runner_old, mentor probe_g5.py A) koduyla uretilen ozetler: bayrak kapaliyken cikti BAYT BAYT ayni kalmali.
_FLAG_OFF_GOLDEN = {"off": ("e726dfbacc461156", 29, 500), "shadow": ("152d23fbee71e682", 29, 500)}


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_flag_off_output_identical_to_pre_g5_golden(world, cand_bars, mode):
    """ml_v2 yok => v1 yolu: cikti ve gorunum cagri sayisi G5 oncesi koda esit (golden ozet)."""
    import trader_engine.strategy_runner as mod
    px, fund = world
    assert _flag_off_digest(mod, px, fund, cand_bars, mode) == _FLAG_OFF_GOLDEN[mode]


def test_flag_off_does_not_touch_features(world, cand_bars):
    """ml_v2 yok => v1 yolu (ctx.ml_v2 None); r02 modeli v1 ozellik listesiyle yuklenemez (eski kapi aynen)."""
    px, fund = world
    D = sorted(cand_bars)[0]
    view = FakeView(px, fund)
    strat = make_v1b_ml()
    src = WindowedSignalSource(view, strat, strict=True)
    assert src.ml_v2 is None and not src._v2_active()
    fr = src.frame("BTC/USDT", D.to_pydatetime(), PARAMS, 1)
    assert fr.status == "ok" and src._bar_feats is None
    assert src.ml_status(D.to_pydatetime())["features"] == "v1"
    with pytest.raises(Exception):
        load_model_view({"meta": {}}, expected_features=R02_FEATURE_NAMES, ml_mode="shadow")


def _src(view, recipe, bars_fn=None, funding=True, *, strict=False):
    strat = make_v1b_ml()
    strat.set_ml_mode("shadow")
    names = R02_FEATURE_NAMES if recipe == "r02" else R03_FEATURE_NAMES
    ctx = LiveContextV2(recipe, PAIRS_E, bars_fn or (lambda p, d, n: view.bars(p, "1h", d, n)),
                        (lambda p, a, b: funding_frame_from_points(view.funding(p, a, b))) if funding else None)
    return WindowedSignalSource(view, strat, strict=strict, ml_model=_model(names), ml_v2=ctx, pairs=PAIRS_E), ctx


def _run_bar(src, D):
    return {p: src.frame(p, D.to_pydatetime(), PARAMS, 1) for p in PAIRS_E}


def _unscored(frames):
    return all(fr.last is None or fr.last.ml_score is None for fr in frames.values())


def test_short_history_makes_candidate_unscored_not_crash(world, cand_bars):
    px, fund = world
    D = sorted(t for t, v in cand_bars.items() if len(v) >= 1)[0]
    view = FakeView(px, fund)                                                       # adaylar tam gecmisle bulunur
    src, ctx = _src(view, "r03", lambda p, d, n: view.bars(p, "1h", d, 24 * 150))   # ... ama v2 baglami yalniz 150 gun alir
    frames = _run_bar(src, D)
    assert src._bar_feats.error is not None and "HistoryShort" in src._bar_feats.error
    assert src.counters["ml_v2_errors"] == 1 and _unscored(frames)
    assert any(fr.last is not None and fr.last.signal for fr in frames.values())     # aday var, puansiz kaldi (shadow: gecer)


def _cand_world(world, cand_bars):
    px, fund = world
    D = sorted(t for t, v in cand_bars.items() if len(v) >= 1 and all(c[0] != BTC for c in v))[0]
    return px, fund, D, {c[0] for c in cand_bars[D]}


def test_btc_last_bar_missing_or_hole_makes_candidate_unscored(world, cand_bars):
    """G5 fix 1: BTC son mumu eksik ya da 200g penceresinde delik -> HistoryGap, aday puansiz (sessiz NaN/kayma yok)."""
    px, fund, D, _ = _cand_world(world, cand_bars)
    b = px[BTC]
    for name, bad in (("son mum", b[b.index != D - pd.Timedelta("1h")]),
                      ("delik", b[~((b.index >= D - pd.Timedelta("60h")) & (b.index < D - pd.Timedelta("40h")))])):
        bad_view = FakeView({**px, BTC: bad}, fund)                                  # aday bulma saglikli, yalniz v2 baglami bozuk
        src, ctx = _src(FakeView(px, fund), "r03", lambda p, d, n, v=bad_view: v.bars(p, "1h", d, n))
        frames = _run_bar(src, D)
        assert src._bar_feats.error is not None and "HistoryGap" in src._bar_feats.error, name
        assert _unscored(frames) and src.counters["ml_v2_errors"] == 1


def test_hole_in_non_candidate_pair_is_counted_not_fatal(world, cand_bars):
    px, fund, D, cp = _cand_world(world, cand_bars)
    other = next(p for p in PAIRS_I if p not in cp and p not in (BTC, ETH))
    o = px[other]
    bad = {**px, other: o[~((o.index >= D - pd.Timedelta("100h")) & (o.index < D - pd.Timedelta("90h")))]}
    v = FakeView(bad, fund)
    src, ctx = _src(FakeView(px, fund), "r03", lambda p, d, n: v.bars(p, "1h", d, n))
    _run_bar(src, D)
    assert src._bar_feats.error is None and ctx.counters["ml_v2_ctx_gaps"] == 1 and src.counters["ml_v2_ctx_gaps"] == 1


def test_late_backfill_is_picked_up_by_full_reload(world, cand_bars):
    """G5 fix 2: BTC deligi D-1s'de goruldu, sonra DB'de doldu (24 mumdan eski): sonraki mum tam yeniden yukleme -> taze deger."""
    px, fund, D, cp = _cand_world(world, cand_bars)
    b = px[BTC]
    hole = (b.index >= D - pd.Timedelta("60h")) & (b.index < D - pd.Timedelta("40h"))
    state = {"px": {**px, BTC: b[~hole]}}
    view = FakeView(px, fund)
    ctx = LiveContextV2("r03", PAIRS_E, lambda p, d, n: FakeView(state["px"], fund).bars(p, "1h", d, n), None)
    ctx.refresh((D - pd.Timedelta("1h")).to_pydatetime())
    state["px"] = px                                                                # gec doldurma
    cands = pd.DataFrame([{"pair": p.split(":")[0], "side": s, "planned_entry": e, "planned_stop": st} for p, s, e, st in cand_bars[D]])
    live = ctx.features_for_bar(D.to_pydatetime(), cands)
    fresh = LiveContextV2("r03", PAIRS_E, lambda p, d, n: view.bars(p, "1h", d, n), None).features_for_bar(D.to_pydatetime(), cands)
    assert live.error is None and ctx.counters["ml_v2_full_reloads"] == 1
    for p in live.rows:
        assert live.rows[p] == fresh.rows[p]


def test_full_reload_once_per_utc_day(world, cand_bars):
    """G5 fix 2: delik olmayan eski duzeltme (24 mumdan eski) ayni gun artimli yolda gorulmez, ertesi UTC gunu tam yuklemeyle gorulur."""
    px, fund, D, cp = _cand_world(world, cand_bars)
    D0 = D.floor("1D") + pd.Timedelta("2h")
    state = {"px": px}
    ctx = LiveContextV2("r03", PAIRS_E, lambda p, d, n: FakeView(state["px"], fund).bars(p, "1h", d, n), None)
    ctx.refresh(D0.to_pydatetime())
    old = D0 - pd.Timedelta("100h")
    changed = px[BTC].copy()
    changed.loc[old, "close"] *= 1.5                                                  # eski mum duzeltildi
    state["px"] = {**px, BTC: changed}
    ctx.refresh((D0 + pd.Timedelta("1h")).to_pydatetime())
    assert ctx._held["BTC/USDT"].loc[old, "close"] == px[BTC].loc[old, "close"]       # ayni gun: artimli (belgeli)
    ctx.refresh((D0 + pd.Timedelta("22h")).to_pydatetime())                          # ertesi gun 00:00
    assert ctx._held["BTC/USDT"].loc[old, "close"] == changed.loc[old, "close"]       # tam yukleme


@pytest.mark.parametrize("recipe", ["r02", "r03"])
def test_stale_funding_nan_and_counted(world, cand_bars, recipe):
    """G5 fix 3 (yalniz r02 etkilenir): en yeni olay 9 saatten eski -> NaN + sayac; r03 hic etkilenmez."""
    px, fund, D, cp = _cand_world(world, cand_bars)
    stale = {p: f[f.index < D - pd.Timedelta("5D")] for p, f in fund.items()}
    view = FakeView(px, stale)
    ctx = LiveContextV2(recipe, PAIRS_E, lambda p, d, n: view.bars(p, "1h", d, n),
                        lambda p, a, b: funding_frame_from_points(view.funding(p, a, b)))
    cands = pd.DataFrame([{"pair": p.split(":")[0], "side": s, "planned_entry": e, "planned_stop": st} for p, s, e, st in cand_bars[D]])
    r = ctx.features_for_bar(D.to_pydatetime(), cands)
    assert r.error is None
    if recipe == "r02":
        assert all(np.isnan(v["f_funding_last"]) and np.isnan(v["f_funding_sum3"]) for v in r.rows.values())
        assert ctx.counters["ml_v2_funding_stale"] == len(cands)
    else:
        assert ctx.counters["ml_v2_funding_stale"] == 0


def test_v2_requires_1h_trigger_tf(world, cand_bars):
    """G5 fix 4a: trigger_tf != '1h' -> v2 ozellik hatasi (sayac + durum), puansiz."""
    px, fund = world
    D = sorted(cand_bars)[0]
    src, ctx = _src(FakeView(px, fund), "r03")
    src.frame("BTC/USDT", D.to_pydatetime(), {**PARAMS, "trigger_tf": "4h"}, 1)
    assert src.counters["ml_v2_errors"] == 1 and "1h" in src._bar_feats.error


def test_future_bar_never_held(world, cand_bars):
    """G5 fix 4b: kapanisi D'yi asan mum tutulursa ozellik uretilmez."""
    px, fund = world
    D = sorted(t for t, v in cand_bars.items() if len(v) >= 1)[0]
    view = FakeView(px, fund)
    src, ctx = _src(view, "r03", lambda p, d, n: view.bars(p, "1h", pd.Timestamp(d) + pd.Timedelta("1h"), n))
    _run_bar(src, D)
    assert src._bar_feats.error is not None and src.counters["ml_v2_errors"] == 1
    ctx2 = LiveContextV2("r03", PAIRS_E, lambda p, d, n: view.bars(p, "1h", pd.Timestamp(d) + pd.Timedelta("1h"), n), None)
    ctx2.refresh(D.to_pydatetime())
    with pytest.raises((AssertionError, Exception)):
        ctx2.features_for_bar(D.to_pydatetime(), pd.DataFrame([{"pair": "SOL/USDT", "side": "long", "planned_entry": 1.0, "planned_stop": 0.9}]))


def test_ml_status_exposes_v2_state(world, cand_bars):
    px, fund = world
    D = sorted(t for t, v in cand_bars.items() if len(v) >= 1)[0]
    view = FakeView(px, fund)
    src, ctx = _src(view, "r03", lambda p, d, n: view.bars(p, "1h", d, 24 * 150))
    _run_bar(src, D)
    st = src.ml_status(D.to_pydatetime())
    assert st["features"] == "r03" and st["v2_errors"] == 1 and "HistoryShort" in st["v2_error"]


def test_config_flag_default_off_and_validated(tmp_path):
    import json
    from pathlib import Path
    raw = json.loads((Path(__file__).resolve().parents[2] / "config" / "engine.base.json").read_text())
    raw.setdefault("bot", "learner")

    def load(**kw):
        (tmp_path / "c.json").write_text(json.dumps({**raw, **kw}))
        return load_engine_config(tmp_path / "c.json")
    cfg = load()
    assert cfg.ml_features == "v1" and cfg.ml_mode == "off"
    assert load(ml_features="r02").ml_features == "r02"
    with pytest.raises(Exception):
        load(ml_features="zzz")
