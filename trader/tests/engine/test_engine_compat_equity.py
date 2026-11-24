"""06 mentor karari (17 Kasim) adim 1-2: legacy_compat'a ozgu duzeltmeler; native/paper defteri bayt bayt ayni kalir."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pa = pytest.importorskip("pyarrow")

from tests.engine.test_engine_06_impl_smoke import PAIRS, _bt, _tpl, _wf, ws  # noqa: E402,F401

NATIVE = ["--period", "20250301-20250303", "--tf", "1h", "--fill-model", "native", "--granularity", "1m",
          "--trigger-source", "last", "--synthetic-rules", "--no-record-filtered", "--strategy", "fake_clean"]
# HEAD (legacy_compat degisikliginden once) kodla uretilen native trades.csv + ledger ozeti SHA-256'si
NATIVE_GOLDEN = "a2967c4d007d48e7e5460fdf4bd7d0b4bec805b64c9db44ea151ccffe95ff159"   # 24.11 kullanici karari: giris sirasi adil (buyuk tf once + donen ofset) -> karar/islem siralamasi degisti


def _add_1m(hist: Path) -> None:
    """15m barlardan sentetik 1m (dogrusal yol + 15 dk icinde belirli fitil); yalniz native testi icin."""
    for pair in PAIRS:
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        t = pd.read_feather(hist / f"{stem}-15m-futures.feather")
        t = t[(t["date"] >= "2025-02-27") & (t["date"] < "2025-03-04")].reset_index(drop=True)
        rows = []
        for r in t.itertuples():
            base = pd.Timestamp(r.date)
            path = np.linspace(r.open, r.close, 16)
            for k in range(15):
                o, c = path[k], path[k + 1]
                h, l = max(o, c), min(o, c)
                if k == 3:
                    h = max(h, r.high)
                if k == 9:
                    l = min(l, r.low)
                rows.append((base + pd.Timedelta(minutes=k), o, h, l, c, r.volume / 15))
        m = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        _wf(hist / f"{stem}-1m-futures.feather", pd.DatetimeIndex(m["date"]),
            {c: m[c].to_numpy() for c in ("open", "high", "low", "close", "volume")})


# WP-3 (sema 4) v_trades'e yalniz olcum sutunlari ekledi; altin ozet sema-3 sutunlari uzerinden kalir (lead: yeni
# sutunlarla ozet degisti, eski sutunlarla birebir ayni oldugu dogrulandi).
_WP3_COLS = frozenset({"entry_order_ts", "entry_order_ack_ts", "entry_ref_price", "entry_ref_spread", "entry_ref_src",
                       "slip_exec_entry", "exit_order_ts", "exit_order_ack_ts", "exit_ref_price", "exit_ref_spread",
                       "exit_ref_src", "slip_exec_exit", "exit_decision_price", "slip_decision_exit", "exit_regime"})


# DD-12 WP-02 (sema 5) goruntulere yalniz yeni sutunlar ekledi; altin ozet eski sutunlar uzerinden kalir.
_WP5_COLS = frozenset({"arm_id", "session_tag", "lesson_ids", "source"})


def _digest(out: Path) -> str:
    import sqlite3
    h = hashlib.sha256()
    h.update((out / "trades.csv").read_bytes())
    con = sqlite3.connect(f"file:{out / 'ledger.sqlite'}?mode=ro", uri=True)
    for tbl in ("v_decisions", "v_trades"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({tbl})")]
        keep = [c for c in cols if c not in ("id", "recorded_at", "ml_score") and c not in _WP3_COLS and c not in _WP5_COLS]
        for row in con.execute(f"SELECT {','.join(keep)} FROM {tbl} ORDER BY 1,2,3"):
            h.update(repr(row).encode())
    con.close()
    return h.hexdigest()


def test_native_ledger_hash_unchanged_by_compat_work(ws):
    _add_1m(ws / "hist")
    assert _bt("--id", "n1", *NATIVE) == 0
    out = ws / "var/backtests/n1"
    assert len(pd.read_csv(out / "trades.csv")) > 0
    assert _digest(out) == NATIVE_GOLDEN


# ------------------------------------------------------------------ adim 2: stake -> miktar kesmesi
def test_trunc_step_keeps_float_noise_like_freqtrade():
    from trader_engine.backtest import _trunc_step
    assert _trunc_step(0.9199999999999999, 0.01) == 0.91     # BNB 2025-11-01 02:00: karar 0.92, referans dolum 0.91
    assert _trunc_step(0.92, 0.01) == 0.92
    assert _trunc_step(4058.5999999999995, 0.1) == 4058.5
    assert _trunc_step(0.0099, 0.001) == 0.009
    margin = 0.92 * 1085.26 / 3.0
    assert _trunc_step((margin / 1085.26) * 3.0, 0.01) in (0.91, 0.92)        # yalniz kayan nokta kosuluna bagli, adimdan buyuk sapma yok


# ------------------------------------------------------------------ adim 1: cikis -> ozsermaye -> giris boyutu
def test_compat_broker_view_realizes_freed_positions_before_sizing():
    from types import SimpleNamespace as NS
    from trader_engine.backtest import _CompatBrokerView
    from trader_engine.types import BrokerAccount
    from datetime import datetime, timezone
    now = datetime(2025, 3, 1, tzinfo=timezone.utc)
    acct = BrokerAccount(wallet=1000.0, unrealized=-5.0, equity=995.0, used_margin=0.0, available=1000.0, ts=now)
    bp = NS(pair="SOL/USDT", qty=10.0, entry_price=100.0, unrealized=-5.0, opened_ts=now)
    broker = NS(account=lambda: acct, positions=lambda: [bp])
    pos = NS(trade_id=1, pair="SOL/USDT", side="long", entry_price=100.0)
    ev = NS(_freed=lambda: {1: 99.0}, _s=NS(open_positions=lambda: [pos]))
    v = _CompatBrokerView(broker, ev, lambda pair, ts: 0.01, 0.0005)
    # gerceklesen: 10*(99-100) - 10*99*0.0005 = -10.495 ; mark'taki -5 yerine
    assert v.account().equity == pytest.approx(995.0 + (-10.495 + 5.0))
    ev2 = NS(_freed=lambda: {}, _s=ev._s)
    assert _CompatBrokerView(broker, ev2, None, 0.0005).account() is acct
