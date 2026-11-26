"""Tutarlilik raporu (Faz 2a): `backtest --env paper` kagit motoruyla AYNI kod yolundan yurur. Cekirdek ozellik: kagit motorunun
sentetik bir pencerede urettigi defter == ayni penceredeki `--env paper` geri testi (anahtar `(pair, side, entry_ts)`, 06 §8 alanlari).
Eski yol (`--env` yok) degismez: bayraksiz ilk kurulum `PrecomputedSignalSource` kullanir (ayri testler)."""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import ledger as L
from trader_core import signals as S
from trader_engine import backtest as BT
from trader_engine import engine as E
from trader_engine.clock import SimClock
from trader_engine.config import apply_overrides, load_cli_config
from trader_engine.holdout import BacktestArgError
from trader_engine.strategy_runner import MultiArmSignalSource, WindowedSignalSource

ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "NVDA/USDT"]
START, END = datetime(2026, 11, 5, tzinfo=UTC), datetime(2026, 11, 6, 12, tzinfo=UTC)
EQ = BT.EQ_FIELDS


S_START, S_END = datetime(2026, 4, 5, tzinfo=UTC), datetime(2026, 11, 6, 14, tzinfo=UTC)      # sentetik magaza kapsami
ARMS = ["T1@1h", "T1@4h", "S1@1h", "R1@1h", "F1@15m", "H2@1h"]


def _write_store(db: Path) -> None:
    """Sentetik market.sqlite (gercek MarketStore): 15m/1h/4h gecmis + son 3 gun 1m last/mark; kural = ornek BTC kurali."""
    import json as _j
    from trader_engine.bars import to_ms
    from trader_engine.exchange.rules import extract_all_rules, spec_to_json
    from trader_engine.marketdata.store import MarketStore
    from trader_engine.types import Bar
    info = _j.loads((Path(__file__).parent / "fixtures" / "binance" / "exchange_info_sample.json").read_text())
    rules = spec_to_json(extract_all_rules(info, ["BTCUSDT"])["BTCUSDT"])
    st = MarketStore(db)
    now_ms = to_ms(S_END)
    idx = pd.date_range(S_START, S_END, freq="15min", inclusive="left")
    n = len(idx)
    t = np.arange(n)
    for k, pair in enumerate(PAIRS):
        st.put_rules(pair, rules, now_ms)
        rng = np.random.default_rng(31 + k)
        wave = 0.07 * np.sin(2 * np.pi * t / (96 * 5 + k * 40)) + 0.012 * np.sin(2 * np.pi * t / (96 * 1.3))
        close = np.round(100 * (1 + 0.3 * k) * np.exp(wave + np.cumsum(rng.normal(0, 0.0018, n))), 3)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.0009, n))), 3)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.0009, n))), 3)
        vol = np.round(rng.uniform(100, 500, n), 1)
        bars = []
        for i in range(n):
            ts = idx[i].to_pydatetime()
            bars.append(Bar(pair, "last", "15m", ts, float(op[i]), float(hi[i]), float(lo[i]), float(close[i]), float(vol[i])))
        for f, tf in ((4, "1h"), (16, "4h")):
            for j in range(0, n - f + 1, f):
                ts = idx[j]
                if (tf == "1h" and ts.minute) or (tf == "4h" and (ts.hour % 4 or ts.minute)):
                    continue
                sl = slice(j, j + f)
                bars.append(Bar(pair, "last", tf, ts.to_pydatetime(), float(op[sl][0]), float(hi[sl].max()), float(lo[sl].min()),
                                float(close[sl][-1]), float(vol[sl].sum())))
        for i in range(n - 3 * 96, n):                       # 1m: 15 dakikalik mumun dogrusal yolu
            for kind in ("last", "mark"):
                for q in range(15):
                    a = op[i] + (close[i] - op[i]) * q / 15
                    b = op[i] + (close[i] - op[i]) * (q + 1) / 15
                    bars.append(Bar(pair, kind, "1m", (idx[i] + timedelta(minutes=q)).to_pydatetime(), float(a), float(max(a, b)),
                                    float(min(a, b)), float(b), float(vol[i] / 15) if kind == "last" else 0.0))
        for c in range(0, len(bars), 20000):
            st.put_bars(bars[c:c + 20000], now_ms=now_ms)
    st.close()


def make_config_dir(dst: Path) -> Path:
    """Gercek `engine.paper.json` katmaninin kucultulmusu (4 cift; arms alt kumesi; ayni cost_overrides/risk/maliyet)."""
    cfgdir = dst / "cfgx"
    cfgdir.mkdir(parents=True)
    for n in ("engine.base.json", "engine.learner.json"):
        shutil.copy(ROOT / "config" / n, cfgdir / n)
    ov = json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))
    ov["pairs"] = list(PAIRS)
    ov["optional_pairs"] = ["NVDA/USDT"]
    ov["arms"] = list(ARMS)
    ov["clusters"] = {"kripto_buyuk": {"pairs": ["BTC/USDT", "ETH/USDT"], "max_positions": 4},
                      "kripto_diger": {"pairs": ["SOL/USDT"], "max_positions": 6},
                      "hisse": {"pairs": ["NVDA/USDT"], "max_positions": 5},
                      "hisse_teknoloji": {"pairs": ["NVDA/USDT"], "max_positions": 3}}
    ov["cost_overrides"] = {"NVDA/USDT": ov["cost_overrides"]["NVDA/USDT"]}
    ov["ml1"] = {"aktif": False}                         # 25.11: bu test ML1 kapisindan bagimsiz (aday/islem ureten kural yolunu sinar); ML1 testleri tests/ml1'de
    (cfgdir / "engine.paper.json").write_text(json.dumps(ov), encoding="utf-8")
    return cfgdir


def run_paper(tmp: Path, cfgdir: Path, db: Path, start=START, end=END):
    """Kagit motoru (build_engine; StoreSource) sentetik pencerede; dondurur: defter yolu."""
    from trader_engine.marketdata.sources import StoreSource
    cfg = load_cli_config(cfgdir, "learner", "paper")
    cfg = apply_overrides(cfg, var_dir=str(tmp / "pvar"), kill_file=str(tmp / "pvar" / "KILL"), pause_file=str(tmp / "pvar" / "PAUSE"),
                          market_db=str(db))
    eng = E.build_engine(cfg, clock=SimClock(start), view=StoreSource(db), env={})
    s = eng.strategy
    params = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    params["trigger_tf"] = "1h"
    eng.ledger.init_params(params, reason=f"strategy:{s.info.name}@{s.info.version} paper")
    eng.start()
    eng.run_range(start, end)
    return Path(cfg.ledger_path)


def trades_of(path: Path) -> dict:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        return {(r["pair"], r["side"], r["entry_ts"]): dict(r) for r in c.execute("SELECT * FROM v_trades")}
    finally:
        c.close()


@pytest.fixture(scope="module")
def paper_and_bt(tmp_path_factory):
    """Kagit motoru + betigin gercek kosucusu (`backtest --env paper`, source=store) AYNI sentetik magazada/pencerede."""
    tmp = tmp_path_factory.mktemp("tut_run")
    db = tmp / "market.sqlite"
    _write_store(db)
    cfgdir = make_config_dir(tmp)
    pl = run_paper(tmp, cfgdir, db)
    import importlib.util
    import sys as _s
    spec_ = importlib.util.spec_from_file_location("tutarlilik_run_e2e", ROOT / "scripts" / "tutarlilik_run.py")
    T = importlib.util.module_from_spec(spec_)
    _s.modules["tutarlilik_run_e2e"] = T
    spec_.loader.exec_module(T)
    seen = {}

    def runner(spec):
        res = BT.run_spec(spec)
        shutil.copy(res.out_dir / "ledger.sqlite", tmp / "bt_ledger.sqlite")      # betik cikti dizinini siler
        seen["spec"], seen["meta"] = spec, res.meta
        return res

    summary, setups = T.run(END, paper_ledger=pl, market_db=db, config_dir=cfgdir, work_root=tmp / "work", runner=runner,
                            window=(START, END))                                  # elle pencere (7 gunluk kagit kosusu pahali)
    return pl, tmp / "bt_ledger.sqlite", summary, seen, T


def test_env_backtest_equals_paper_engine_over_window(paper_and_bt):
    """Cekirdek ozellik: kagit motorunun penceredeki defteri == ayni penceredeki `--env paper` geri testi; alan alan (06 §8, 1e-9)."""
    pl, btl, summary, seen, _T = paper_and_bt
    P, B = trades_of(pl), trades_of(btl)
    assert len(P) >= 3, "sentetik pencerede kagit motoru en az 3 islem uretmeli"
    assert set(P) == set(B), sorted(set(P) ^ set(B))
    for k in P:
        for f in EQ:
            assert BT._close(P[k][f], B[k][f], 1e-9), (k, f, P[k][f], B[k][f])
    assert seen["meta"]["strategy"] == "price_action_lab_ml" and seen["meta"]["pairs"] == PAIRS


def test_script_summary_over_same_window_is_clean(paper_and_bt):
    """Betik ozeti: eslesme %100, aciklanamayan 0, WARN yok; kayma 0; R/PnL farki 0."""
    _pl, _btl, summary, seen, T = paper_and_bt
    assert summary["not"] is None or "pencere basinda" in summary["not"]
    assert summary["kurulumlar"], summary
    for k in summary["kurulumlar"]:
        assert k["eslesme_orani"] == 1.0 and (k["yalniz_kagit"], k["yalniz_bt"]) == (0, 0), k
        assert sum(k["nedenler"].values()) == 0, k
        assert k["kagit_R"] == k["bt_R"] and k["kagit_pnl"] == k["bt_pnl"]
        assert k["giris_kayma_bps_ort"] in (0, 0.0, None)
    assert summary["uyari"] is False
    sp = seen["spec"]
    assert sp.env == "paper" and sp.source == "store" and sp.veto == "none" and sp.fill_model == "native"


def test_env_flag_uses_paper_signal_class_and_paper_overlay():
    from trader_engine.strategies.registry import get_strategy
    lab = get_strategy("price_action_lab_ml", mode="paper")
    assert E.signal_source_class(lab) is MultiArmSignalSource
    assert E.signal_source_class(get_strategy("price_action_v1", mode="paper")) is WindowedSignalSource
    # engine.paper.json katmani: kagit kipinde yuklenir ve arms/kume/maliyet tasir
    cfg = BT.BacktestRunner(BT.BacktestSpec(id="x", start=START, end=END, env="paper",
                                            config_dir=str(ROOT / "config"))).build_config(Path("/nonexistent-out"))
    assert cfg.mode == "paper" and cfg.strategy == "price_action_lab_ml" and "R1@1h" in cfg.arms and cfg.cost_overrides
    assert cfg.var_dir == "/nonexistent-out" and cfg.target_trade_risk == 0.01 and cfg.mtm_marks is False


def test_env_flag_holdout_and_bad_args_rejected(tmp_path, kilitli_motor):      # 23.11.2026: kilit acik; mekanizma kapali bayrakla sinanir
    runner = BT.BacktestRunner(BT.BacktestSpec(id="h", start=datetime(2026, 10, 25, tzinfo=UTC), end=datetime(2026, 11, 3, tzinfo=UTC),
                                               env="paper", config_dir=str(ROOT / "config"), out_root=str(tmp_path)))
    with pytest.raises(BacktestArgError) as e:
        runner.run_once(tmp_path / "o1")
    assert e.value.code == "holdout_locked"
    bad = BT.BacktestSpec(id="b", start=START, end=END, env="paper", config_dir=str(ROOT / "config"), slip_bps=3.0)
    with pytest.raises(BacktestArgError):
        BT.BacktestRunner(bad).run_once(tmp_path / "o2")
    with pytest.raises(BacktestArgError):                          # --wallet-start yalniz --env ile
        BT.spec_from_args(BT.build_parser().parse_args(["--id", "w", "--period", "20241101-20241201", "--wallet-start", "900"]), [])


def test_cli_parser_env_flag_default_off():
    a = BT.build_parser().parse_args(["--id", "z", "--period", "IS"])
    assert a.env is None and a.wallet_start is None
    sp = BT.spec_from_args(a, [])
    assert sp.env is None and sp.wallet_start is None
    a = BT.build_parser().parse_args(["--id", "z", "--period", "IS", "--env", "paper", "--wallet-start", "950"])
    sp = BT.spec_from_args(a, [])
    assert sp.env == "paper" and sp.wallet_start == 950.0
