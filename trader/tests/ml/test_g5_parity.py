"""ML-G5: egitim yolu (feature_frame_v2, TUM cerceve) == motor yolu (LiveContextV2: mum mum, yalniz motorun elindeki pencere), 1e-9.
r02 ve r03; 4s ve 1g sinirlari dahil; yalniz sentetik veri (2024 zaman damgalari)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader_core.ml_features import BAR, BTC, ETH
from trader_core.ml_features_v2 import R02_FEATURE_NAMES, R03_FEATURE_NAMES, feature_frame_v2
from trader_core.ml_live_v2 import MIN_1H_BARS, WINDOW_1H_V2, HistoryShort, LiveContextV2, funding_frame_from_points
from trader_ml.features_v2 import feature_frame_v2 as guarded_v2
from trader_ml.guards import HoldoutViolation

PAIRS = [BTC, ETH, "BNB/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT", "ADA/USDT:USDT",
         "TRX/USDT:USDT", "LINK/USDT:USDT", "AVAX/USDT:USDT"]
START = pd.Timestamp("2024-01-01", tz="UTC")
N = 24 * 240                      # 240 gun: pencere (5000 mum) tum gecmisten KISA => pencere etkisi de sinanir


def _eng(p: str) -> str:
    return p.split(":")[0]


@pytest.fixture(scope="module")
def world():
    rng = np.random.default_rng(11)
    idx = pd.date_range(START, periods=N, freq="1h", tz="UTC")
    common = rng.normal(0, 0.004, N)
    px = {}
    for i, p in enumerate(PAIRS):
        r = common * (1 + 0.1 * i) + rng.normal(0.00001 * i, 0.006, N)
        c = 100 * (i + 1) * np.exp(np.cumsum(r))
        o = np.concatenate([[c[0]], c[:-1]])
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.003, N)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.003, N)))
        px[p] = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": rng.uniform(50, 150, N)}, index=idx)
    ft = pd.date_range(START, periods=N // 8, freq="8h", tz="UTC")
    fund = {p: pd.DataFrame({"funding_rate": rng.normal(0.0001, 0.0003, len(ft))}, index=ft) for p in PAIRS}
    return px, fund


def _cands(px, positions, rng_seed=5):
    """positions: sinyal mumu satir konumlari; her konumda 1-3 ayri cift, yonler karisik."""
    rng = np.random.default_rng(rng_seed)
    rows = []
    for k in positions:
        for p in rng.choice(PAIRS, size=int(rng.integers(1, 4)), replace=False):
            side = "long" if rng.random() < 0.5 else "short"
            e = float(px[p]["close"].iloc[k])
            rows.append({"ts": START + (k + 1) * BAR, "pair": p, "side": side, "planned_entry": e,
                         "planned_stop": e * (0.985 if side == "long" else 1.015)})
    return pd.DataFrame(rows)


def _fns(px, fund):
    def bars_fn(p, D, n):
        d = px[p if ":" in p else p + ":USDT"]
        return d[d.index + BAR <= pd.Timestamp(D)].iloc[-n:]

    def funding_fn(p, a, b):
        f = fund[p if ":" in p else p + ":USDT"]
        f = f[(f.index >= pd.Timestamp(a)) & (f.index <= pd.Timestamp(b))]
        return f
    return bars_fn, funding_fn


def _engine_path(px, fund, cands, recipe):
    """Mum mum (artimli): her ayri ts icin yalniz o ts'nin yerel adaylari + motorun elindeki pencere."""
    bars_fn, funding_fn = _fns(px, fund)
    ctx = LiveContextV2(recipe, [_eng(p) for p in PAIRS], bars_fn, funding_fn)
    names = R02_FEATURE_NAMES if recipe == "r02" else R03_FEATURE_NAMES
    out = pd.DataFrame(index=cands.index, columns=names, dtype=float)
    for ts, g in cands.groupby("ts", sort=True):
        c = g.assign(pair=g["pair"].map(_eng))
        bf = ctx.features_for_bar(ts.to_pydatetime(), c[["pair", "side", "planned_entry", "planned_stop"]])
        assert bf.error is None
        for i, (ix, row) in enumerate(c.iterrows()):
            out.loc[ix] = [bf.rows[row["pair"]][n] for n in names]
    assert ctx.held_rows() <= len(PAIRS) * WINDOW_1H_V2
    return out


def _positions():
    # 4s ve 1g sinirlari: kapanis saati 00:00 (1g), 04/08/12:00 (4s), diger saatler; hepsi >= 200 gun sonra
    base = 24 * 205
    day_close = [base + 24 * d - 1 for d in range(0, 6)]                  # ts = 00:00
    h4_close = [base + 24 * 7 + 3, base + 24 * 7 + 7, base + 24 * 7 + 11, base + 24 * 8 + 15]
    other = [base + 24 * 9 + 5, base + 24 * 9 + 6, base + 24 * 10 + 20, N - 1]
    return sorted(set(day_close + h4_close + other))


@pytest.mark.parametrize("recipe", ["r02", "r03"])
def test_training_path_equals_engine_path_1e9(world, recipe):
    px, fund = world
    cands = _cands(px, _positions())
    assert ((cands["ts"].dt.hour % 24 == 0)).any() and (cands["ts"].dt.hour % 4 == 0).any() and (cands["ts"].dt.hour % 4 != 0).any()
    assert cands.groupby("ts").size().max() >= 2                          # ayni mumda birden cok aday (iki gecis)
    train = feature_frame_v2(px, cands, funding=fund, recipe=recipe)
    live = _engine_path(px, fund, cands, recipe)
    assert list(train.columns) == list(live.columns)
    a, b = train.to_numpy(float), live.to_numpy(float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    assert np.isfinite(a).sum() > a.size * 0.8                            # anlamsiz (hep NaN) karsilastirma degil
    np.testing.assert_allclose(b, a, rtol=0, atol=1e-9, equal_nan=True)


@pytest.mark.parametrize("recipe", ["r02", "r03"])
def test_consecutive_bars_incremental_cache_matches(world, recipe):
    """Ardisik 30 saat (1g sinirini kapsar), her saat adaylar var: artimli onbellek tam yuklemeyle ayni sonucu verir."""
    px, fund = world
    start = 24 * 215 - 12
    cands = _cands(px, range(start, start + 30), rng_seed=7)
    train = feature_frame_v2(px, cands, funding=fund, recipe=recipe)
    live = _engine_path(px, fund, cands, recipe)
    np.testing.assert_allclose(live.to_numpy(float), train.to_numpy(float), rtol=0, atol=1e-9, equal_nan=True)


def test_same_bar_count_is_over_all_native_candidates_of_the_bar(world):
    px, fund = world
    k = 24 * 210 + 7
    cands = _cands(px, [k])
    bars_fn, funding_fn = _fns(px, fund)
    ctx = LiveContextV2("r03", [_eng(p) for p in PAIRS], bars_fn, funding_fn)
    c = cands.assign(pair=cands["pair"].map(_eng))
    bf = ctx.features_for_bar((START + (k + 1) * BAR).to_pydatetime(), c[["pair", "side", "planned_entry", "planned_stop"]])
    assert {r["f_same_bar_signals"] for r in bf.rows.values()} == {float(len(cands))}


def test_short_history_is_refused(world):
    px, fund = world
    bars_fn, funding_fn = _fns(px, fund)
    ctx = LiveContextV2("r03", [_eng(p) for p in PAIRS], bars_fn, funding_fn)
    k = 24 * 100
    c = _cands(px, [k]); c = c.assign(pair=c["pair"].map(_eng))
    with pytest.raises(HistoryShort):
        ctx.features_for_bar((START + (k + 1) * BAR).to_pydatetime(), c[["pair", "side", "planned_entry", "planned_stop"]])
    assert MIN_1H_BARS == 4800 and WINDOW_1H_V2 >= MIN_1H_BARS


def test_funding_points_rounded_to_hour():
    from types import SimpleNamespace as NS
    f = funding_frame_from_points([NS(ts=pd.Timestamp("2024-01-01 08:00:00.123", tz="UTC").to_pydatetime(), rate=0.0001)])
    assert f.index[0] == pd.Timestamp("2024-01-01 08:00", tz="UTC") and f["funding_rate"].iloc[0] == 0.0001


def test_guarded_wrapper_equals_core_and_blocks_holdout(world, monkeypatch):
    from trader_ml import guards as _G
    monkeypatch.setattr(_G, "KILIT_ACIK", False)      # 23.11.2026: kilit acik; koruma mekanizmasi kapali bayrakla sinanir
    px, fund = world
    cands = _cands(px, [24 * 210])
    a = guarded_v2(px, cands, funding=fund, recipe="r03")
    b = feature_frame_v2(px, cands, funding=fund, recipe="r03")
    pd.testing.assert_frame_equal(a, b, check_exact=True)
    late = {p: d.copy() for p, d in px.items()}
    late[ETH].index = late[ETH].index + pd.Timedelta(days=800)        # >= 2026-05-01
    with pytest.raises(HoldoutViolation):
        guarded_v2(late, cands, funding=fund, recipe="r03")
    lf = {p: d.copy() for p, d in fund.items()}
    lf[BTC].index = lf[BTC].index + pd.Timedelta(days=800)
    with pytest.raises(HoldoutViolation):
        guarded_v2(px, cands, funding=lf, recipe="r03")


# ---------------------------------------------------------------- G5 fix 3: bayat fonlama (NaN + sayac), egitim == canli
def test_stale_funding_rule_boundary_9h():
    """Tek olay E: ts - E <= 9s -> deger; > 9s -> NaN (f_funding_last ve f_funding_sum3), sayac = NaN'a dusen aday."""
    from trader_core.ml_features_v2 import FUNDING_MAX_AGE
    assert FUNDING_MAX_AGE == pd.Timedelta(hours=9)
    px = {p: pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0},
                          index=pd.date_range(START, periods=24 * 210, freq="1h", tz="UTC")) for p in PAIRS}
    e = START + pd.Timedelta(days=205)
    fund = {BTC: pd.DataFrame({"funding_rate": [0.001]}, index=[e])}
    rows = [{"ts": e + pd.Timedelta(hours=h), "pair": BTC, "side": "long", "planned_entry": 1.0, "planned_stop": 0.9} for h in (1, 8, 9, 10, 20)]
    ff = feature_frame_v2(px, pd.DataFrame(rows), funding=fund, recipe="r02")
    last = ff["f_funding_last"].to_numpy(float)
    assert list(np.isnan(last)) == [False, False, False, True, True]
    assert list(np.isnan(ff["f_funding_sum3"].to_numpy(float))) == [False, False, False, True, True]
    assert ff.attrs["funding_stale"] == 2
    assert feature_frame_v2(px, pd.DataFrame(rows), funding=None, recipe="r02").attrs["funding_stale"] == 0


def test_stale_funding_training_equals_engine_and_counted(world):
    px, fund = world
    cut = START + pd.Timedelta(hours=24 * 210)
    fund = {p: f[f.index < cut] for p, f in fund.items()}                      # beslemesi kesilen fonlama
    k0 = 24 * 210
    cands = _cands(px, range(k0 - 6, k0 + 30), rng_seed=9)
    train = feature_frame_v2(px, cands, funding=fund, recipe="r02")
    bars_fn, funding_fn = _fns(px, fund)
    ctx = LiveContextV2("r02", [_eng(p) for p in PAIRS], bars_fn, funding_fn)
    live = pd.DataFrame(index=cands.index, columns=R02_FEATURE_NAMES, dtype=float)
    for ts, g in cands.groupby("ts", sort=True):
        c = g.assign(pair=g["pair"].map(_eng))
        bf = ctx.features_for_bar(ts.to_pydatetime(), c[["pair", "side", "planned_entry", "planned_stop"]])
        for ix, row in c.iterrows():
            live.loc[ix] = [bf.rows[row["pair"]][n] for n in R02_FEATURE_NAMES]
    a, b = train.to_numpy(float), live.to_numpy(float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    np.testing.assert_allclose(b, a, rtol=0, atol=1e-9, equal_nan=True)
    f_nan = train["f_funding_last"].isna().to_numpy()
    assert f_nan.any() and (~f_nan).any()                                        # hem taze hem bayat satirlar sinandi
    assert train.attrs["funding_stale"] == int(f_nan.sum()) == ctx.counters["ml_v2_funding_stale"]
