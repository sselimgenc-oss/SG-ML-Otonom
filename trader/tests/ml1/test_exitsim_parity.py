"""ML1 izole cikis simulatoru <-> GERCEK motor parite testi (plan bolum 5).

Yontem: sentetik 1 dk yoldan (tests/exit_modes_parity_support: rejim degisen suruklenme; 15m/1h/4h bundan turetilir) GERCEK motor geri testi
(native, 1 dk adim, tetik `last`, `target_mode=resting`, kagit varsayilani cikis kipleri basa-bas + kismi ACIK) kosulur. Karisik kollar:
T1 (iz suren stop) ve R1 (hedef + zaman stopu). Motorun actigi her islem icin ayni aday (planned_entry/stop/target, karar zamani) `exitsim`
ile 15 dk izgarada oynatilir ve motor defteriyle karsilastirilir.
Kapi (exit_counterfactual esikleri): medyan |dR| <= 0,10, ortalama <= 0,05, cikis nedeni uyumu >= %85. Veri sentetik; ag yok; var/history yok."""
from __future__ import annotations

import json
import statistics as stt
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
pytest.importorskip("pyarrow")

import exit_modes_parity_support as P  # noqa: E402

from trader_core import arm_time as AT  # noqa: E402
from trader_core import exit_counterfactual as EC  # noqa: E402
from trader_core import exit_modes as XM  # noqa: E402
from trader_core import signals as S  # noqa: E402
from trader_engine.strategies.price_action_v1 import PriceActionV1  # noqa: E402
from trader_ml.ml1 import costs as C  # noqa: E402
from trader_ml.ml1 import exitsim as X  # noqa: E402

MEDIAN_MAX, MEAN_MAX, REASON_MIN = EC.PARITY_MEDIAN_ABS_R, EC.PARITY_MEAN_ABS_R, EC.PARITY_REASON_MATCH
MODES = {"default": {"breakeven": True, "partial": True}}          # engine.paper.json varsayilani


class MixedNth(P.EveryNth):
    """EveryNth (T1) + her ikinci sinyal R1 (hedef kipi): hedef = giris +/- 3 ATR (stop mesafesi 2 ATR -> 1,5 R) ya da 5 ATR (2,5 R)."""
    EVERY = 5

    def __init__(self) -> None:
        PriceActionV1.__init__(self, name="ml1_nth", version="0.1", setups_enabled=("T1", "R1"), allowed_trigger_tfs=("1h",),
                               block_same_bar_reentry=False, paper_allowed=False)

    def compute(self, ctx):
        df = super().compute(ctx).copy()
        n = len(df)
        sig = df["signal"].to_numpy(dtype=bool)
        order = np.cumsum(sig)
        r1 = sig & (order % 2 == 0)
        c = ctx.bars[ctx.tf]["close"].astype("float64").to_numpy()
        atr = df["atr_tf"].to_numpy(dtype="float64")
        side = df["side"].to_numpy(dtype=object)
        sgn = np.where(side == "long", 1.0, -1.0)
        mult = np.where(order % 4 == 0, 5.0, 3.0)
        df["setup"] = pd.Series(np.where(r1, "R1", np.where(sig, "T1", None)), index=df.index, dtype=object)
        df["planned_target"] = np.where(r1, c + sgn * mult * atr, np.nan)
        return df[S.SIGNAL_COLUMNS]


def _bars(ws: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    import pyarrow.feather as pf

    def rd(tf: str) -> pd.DataFrame:
        t = pf.read_table(str(ws / "hist" / f"BTC_USDT_USDT-{tf}-futures.feather")).to_pandas()
        return t.set_index("date")
    return rd("15m"), rd("1h"), rd("4h")


def _funding(ws: Path) -> pd.DataFrame:
    import pyarrow.feather as pf
    return pf.read_table(str(ws / "hist" / "BTC_USDT_USDT-1h-funding_rate.feather")).to_pandas().set_index("date")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    from trader_engine import backtest as B
    from trader_engine.strategies import registry as REG
    root = tmp_path_factory.mktemp("exitsim_parity")
    tpl, ws = root / "tpl", root / "ws"
    P.make_history(tpl)
    ws.mkdir()
    mp = pytest.MonkeyPatch()
    P.setup_workspace(ws, mp, tpl)
    mp.setitem(REG._FACTORIES, "ml1_nth", lambda: MixedNth())
    try:
        args = ["--id", "ml1", "--period", P.PERIOD, "--tf", "1h", "--fill-model", "native", "--granularity", "1m", "--trigger-source", "last",
                "--synthetic-rules", "--no-record-filtered", "--strategy", "ml1_nth", "--pairs", P.PAIR, "--target-mode", "resting",
                "--exit-modes", json.dumps(MODES)]
        assert int(B.main(["--env", "eski", *args]) or 0) == 0
        run_dir = ws / "var" / "backtests" / "ml1"
        from trader_core import ledger as L
        led = L.open_ledger(run_dir / "ledger.sqlite", "learner", create=False, read_only=True, migrate=False)
        try:
            trades = sorted(led.list_closed_trades(limit=L.Ledger.LIST_CLOSED_MAX), key=lambda t: t.trade_id)
        finally:
            led.close()
        b15, h1, h4 = _bars(ws)
        reg = AT.regime_series(h4, S.DEFAULT_SIGNAL_PARAMS.regime_params())
        core, _, _ = AT.core_signals(h1, reg, S.DEFAULT_SIGNAL_PARAMS)
        tfb = X.prepare_tf(h1, core)
        fund = _funding(ws)
        yield dict(ws=ws, trades=trades, b15=b15, tfb=tfb, fund=fund)
    finally:
        mp.undo()


def _cands(trades, with_qty: bool = False) -> list[dict]:
    out = []
    for t in trades:
        d = dict(decision_ts=pd.Timestamp(t.entry_ts), pair=t.pair, tf="1h", setup=t.setup, side=t.side, entry_ref=t.planned_entry,
                 stop=t.planned_stop, target=t.planned_target, trade_id=t.trade_id)
        if with_qty:
            d["qty"] = t.qty
        out.append(d)
    return out


def _cfg(world, lot: bool = False) -> X.SimConfig:
    base = X.load_sim_config()
    kw = {}
    if lot:
        from trader_engine.marketdata.sources import HistoricalSource
        r = HistoricalSource(world["ws"] / "hist", granularity="1m", synthetic_rules=True).rules(P.PAIR)
        kw["lot_rules"] = (float(r.step), float(r.min_qty), float(r.min_notional))
    return X.SimConfig(cost=base.cost, cfg_modes=XM.build_config(MODES), **kw)


def _stats(world, res, trades):
    d_r = [abs(r["net_R"] - t.r_multiple) for r, t in zip(res, trades)]
    match = [r["exit_reason"] == t.exit_reason for r, t in zip(res, trades)]
    return dict(n=len(trades), median=stt.median(d_r), mean=float(np.mean(d_r)), max=max(d_r), match=sum(match) / len(match))


def test_engine_run_has_both_arm_kinds_and_modes(world):
    tr = world["trades"]
    assert len(tr) >= 40, len(tr)
    assert {t.setup for t in tr} == {"T1", "R1"}
    reasons = {t.exit_reason for t in tr}
    assert {"stop", "trail_stop", "target"} <= reasons, reasons               # iz, hedef ve stop yollari sentetik yolda gorulur
    assert all(t.planned_entry == t.planned_entry and t.planned_stop is not None for t in tr)


def test_decision_ts_equals_entry_fill_ts(world):
    """Motor girisi karar kapanisinin ilk dakikasinda doldurur: giris zamani = 1h sinirinda (karar zamani)."""
    assert all(pd.Timestamp(t.entry_ts) == pd.Timestamp(t.entry_ts).floor("1h") for t in world["trades"])


def test_exitsim_parity_vs_engine(world):
    trades = world["trades"]
    res = X.simulate_rows(_cands(trades), world["b15"], world["tfb"], world["fund"], cfg=_cfg(world))
    assert all(r["status"] == "ok" for r in res), [r["status"] for r in res if r["status"] != "ok"][:3]
    s = _stats(world, res, trades)
    assert s["median"] <= MEDIAN_MAX and s["mean"] <= MEAN_MAX and s["match"] >= REASON_MIN, s


def test_exitsim_parity_with_lot_rounding_is_tight(world):
    """Motorun adet yuvarlamasi (kismi adet) verilince sapma kuculur: medyan <= 0,01 R."""
    trades = world["trades"]
    res = X.simulate_rows(_cands(trades, True), world["b15"], world["tfb"], world["fund"], cfg=_cfg(world, lot=True))
    s = _stats(world, res, trades)
    assert s["median"] <= 0.01 and s["mean"] <= MEAN_MAX and s["match"] >= REASON_MIN, s


def test_parity_by_arm_kind_and_entry_price(world):
    trades = world["trades"]
    res = X.simulate_rows(_cands(trades), world["b15"], world["tfb"], world["fund"], cfg=_cfg(world))
    for kind in ("T1", "R1"):
        idx = [i for i, t in enumerate(trades) if t.setup == kind]
        s = _stats(world, [res[i] for i in idx], [trades[i] for i in idx])
        assert s["n"] >= 10 and s["median"] <= MEDIAN_MAX and s["match"] >= REASON_MIN, (kind, s)
    ent = [abs(r["entry_px"] - t.entry_price) / t.entry_price for r, t in zip(res, trades)]
    assert max(ent) < 1e-4                                                      # giris dolumu (acilis + 2 bps kayma) ayni


def test_r_unit_equals_ledger_planned_risk_per_qty(world):
    trades = world["trades"]
    res = X.simulate_rows(_cands(trades), world["b15"], world["tfb"], world["fund"], cfg=_cfg(world))
    for r, t in zip(res, trades):
        assert r["r_unit"] * t.qty == pytest.approx(t.planned_risk, rel=1e-6)
