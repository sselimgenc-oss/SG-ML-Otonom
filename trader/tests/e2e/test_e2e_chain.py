"""Madde 20 + 19d: uctan uca zincir (sinyal -> veto -> risk -> emir -> defter -> ders), TAMAMEN cevrimdisi.
Sartname: docs/e2e-spec.md. Sentetik 15m/1h/4h + fonlama verisi (tmp, 2025; kilitli donem 2026-05..2026-10 OKUNMAZ);
ag yok, anahtar yok, LLM yok (ders `rule_proxy` kipi, bildirimci LogNotifier)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pa = pytest.importorskip("pyarrow")
import pyarrow.feather as pf  # noqa: E402

from trader_core import ledger as L  # noqa: E402
from trader_core import lesson as LS  # noqa: E402
from trader_core import risk as K  # noqa: E402
from trader_core import signals as S  # noqa: E402
from trader_core import telegram as T  # noqa: E402
from trader_engine.gates import VetoLookup  # noqa: E402
from trader_engine.brokers.paper import PaperBroker, PaperConfig  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.config import apply_overrides, load_engine_config  # noqa: E402
from trader_engine.engine import Engine  # noqa: E402
from trader_engine.killswitch import Killswitch  # noqa: E402
from trader_engine.marketdata.sources import HistoricalSource  # noqa: E402
from trader_engine.state import StateStore  # noqa: E402
from trader_engine.status import StatusWriter  # noqa: E402
from trader_engine.strategies.registry import get_strategy  # noqa: E402
from trader_engine.strategy_runner import WindowedSignalSource  # noqa: E402

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
H_START, H_END = datetime(2025, 1, 1, tzinfo=UTC), datetime(2025, 3, 15, tzinfo=UTC)
START, END = datetime(2025, 3, 1, tzinfo=UTC), datetime(2025, 3, 5, tzinfo=UTC)
BLOCKED_PAIR = "ETH/USDT"
BLOCK_REASON = "e2e_test_block"
LESSON_NOW = datetime(2025, 3, 7, 3, 0, tzinfo=UTC)


# ------------------------------------------------------------------------------------------------ sahte veri (fixture)
def _wf(path: Path, dates: pd.DatetimeIndex, cols: dict) -> None:
    arrs = {"date": pa.array(dates.as_unit("ms").asi8.astype("int64"), type=pa.timestamp("ms", tz="UTC"))}
    for k, v in cols.items():
        arrs[k] = pa.array(np.asarray(v, dtype="float64"))
    pf.write_feather(pa.table(arrs), str(path), compression="uncompressed")


def write_history(hist: Path) -> None:
    """Dalgali + gurultulu sentetik seri (rejim/pullback sinyalleri uretecek kadar yapili); deterministik."""
    hist.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(H_START, H_END, freq="15min", inclusive="left")
    t = np.arange(len(idx))
    for k, pair in enumerate(PAIRS):
        rng = np.random.default_rng(7 + k)
        wave = 0.06 * np.sin(2 * np.pi * t / (96 * 6 + k * 40)) + 0.01 * np.sin(2 * np.pi * t / (96 * 1.3))
        close = np.round(100 * (1 + 0.3 * k) * np.exp(wave + np.cumsum(rng.normal(0, 0.0015, len(idx)))), 3)
        op = np.concatenate([[close[0]], close[:-1]])
        hi = np.round(np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.00075, len(idx)))), 3)
        lo = np.round(np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.00075, len(idx)))), 3)
        df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": close,
                           "volume": np.round(rng.uniform(100, 500, len(idx)), 1)}, index=idx)
        stem = pair.replace("/", "_") + "_" + pair.split("/")[1]
        for tf, rule in (("15m", "15min"), ("1h", "1h"), ("4h", "4h")):
            g = df if tf == "15m" else pd.DataFrame(
                {"open": df.resample(rule)["open"].first(), "high": df.resample(rule)["high"].max(),
                 "low": df.resample(rule)["low"].min(), "close": df.resample(rule)["close"].last(),
                 "volume": df.resample(rule)["volume"].sum()}).dropna()
            _wf(hist / f"{stem}-{tf}-futures.feather", g.index, g.to_dict("list"))
        fidx = pd.date_range(H_START, H_END, freq="8h", inclusive="left")
        _wf(hist / f"{stem}-1h-funding_rate.feather", fidx, {"funding_rate": [0.0001] * len(fidx)})


# ------------------------------------------------------------------------------------------------ sahte veto (sonuc dosyasi)
class StubFileVeto:
    """Kagitta hic sorgulanmamasi gereken veto vekili: sorgulari kaydeder (allow -> allowed; block -> blocked; dosya yok -> missing).
    24.11: trader_core.veto silindi; vekil yalniz `gates.VetoLookup` doner."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.lookups: list[tuple[str, str, str]] = []

    def begin_step(self, now: datetime) -> None:
        return None

    def lookup(self, pair: str, side: str, now: datetime) -> VetoLookup:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lk = VetoLookup("missing", "file_missing", True)
        else:
            d = doc.get(f"{pair}:{side}") or doc.get(f"{pair}:*") or doc.get("*") or {"action": "allow"}
            lk = VetoLookup("allowed", None, False) if d["action"] == "allow" else VetoLookup("blocked", d.get("reason"), True)
        self.lookups.append((pair, side, lk.status))
        return lk


# ------------------------------------------------------------------------------------------------ zincir kurucu
def _params():
    return {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}


class Chain:
    def __init__(self, tmp: Path, hist: Path, *, strategy="price_action_v1", veto_doc=None, kill=False):
        tmp.mkdir(parents=True, exist_ok=True)
        self.tmp = tmp
        cfg = load_engine_config(ROOT / "config" / "engine.base.json", ROOT / "config" / "engine.learner.json")
        kw = dict(mode="paper", pairs=PAIRS, var_dir=str(tmp / "var"), kill_file=str(tmp / "KILL"), strategy=strategy, history_dir=str(hist),
                  cost=dict(fill_model="native", granularity="15m", trigger_source="last"))
        self.cfg = apply_overrides(cfg, **kw)
        self.clock = SimClock(START)
        self.view = HistoricalSource(str(hist), granularity="15m", synthetic_rules=True)
        broker = PaperBroker(PaperConfig(cost=self.cfg.cost, mmr=K.LOCKED_CFG.maint_margin_rate,
                                         wallet_start=self.cfg.wallet_start),
                             self.view.rules, self.view.funding, self.clock)
        for p in (self.cfg.ledger_path, self.cfg.state_path, self.cfg.status_path):
            Path(p).parent.mkdir(parents=True, exist_ok=True)
        self.ledger = L.open_ledger(self.cfg.ledger_path, "learner", create=True, clock=self.clock.now)
        strat = get_strategy(strategy)
        self.ledger.init_params(_params(), reason=f"strategy:{strat.info.name}@{strat.info.version} e2e")
        state = StateStore(self.cfg.state_path, bot="learner", durability="off")
        self.veto_path = tmp / "veto_result.json"
        self.veto_path.write_text(json.dumps(veto_doc or {"*": {"action": "allow"}}))
        self.veto = StubFileVeto(self.veto_path)
        self.kill = Killswitch(self.cfg.kill_file, self.clock)
        if kill:
            self.kill.set("e2e", "test")
        src = WindowedSignalSource(self.view, strat, strict=True)
        self.engine = Engine(self.cfg, clock=self.clock, view=self.view, broker=broker, ledger=self.ledger, state=state,
                             signals=src, strategy=strat, veto=self.veto, kill=self.kill,
                             status=StatusWriter(self.cfg.status_path, self.clock, self.cfg), strict=True)

    def run(self):
        self.engine.start()
        self.engine.run_range(START, END)
        return self

    # -- defter okuma (salt okunur sqlite)
    def q(self, sql, args=()):
        con = sqlite3.connect(self.cfg.ledger_path)
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(sql, args)]
        finally:
            con.close()

    def decisions(self):
        return self.q("SELECT * FROM v_decisions ORDER BY bar_close_ts, pair, side, setup")

    def trades(self):
        return self.q("SELECT * FROM v_trades ORDER BY entry_ts, pair")

    def digest(self, drop=("id", "recorded_at", "ml_score")):
        rows = [{k: v for k, v in r.items() if k not in drop} for r in self.decisions()]
        tr = [{k: v for k, v in r.items() if k not in drop} for r in self.trades()]
        return hashlib.sha256(json.dumps([rows, tr], sort_keys=True, default=str).encode()).hexdigest()


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    d = tmp_path_factory.mktemp("e2e_hist") / "hist"
    write_history(d)
    return d


def _veto_blocking(row) -> dict:
    return {"*": {"action": "allow"}, f"{row['pair']}:{row['side']}": {"action": "block", "reason": BLOCK_REASON}}


@pytest.fixture(scope="module")
def off(tmp_path_factory, hist):
    """Ana zincir kosusu: veto hepsine 'allow'."""
    return Chain(tmp_path_factory.mktemp("off"), hist).run()


@pytest.fixture(scope="module")
def blocked(tmp_path_factory, hist, off):
    """Ayni veri; 'off' kosusunda girilen ILK adayin (cift, yon) veto sonucu 'block'."""
    entered = [r for r in off.decisions() if r["final_action"] == "entered"]
    assert entered, "fixture veri en az bir giris uretmeli"
    c = Chain(tmp_path_factory.mktemp("blocked"), hist, veto_doc=_veto_blocking(entered[0])).run()
    c.target = entered[0]
    return c


@pytest.fixture(scope="module")
def killed(tmp_path_factory, hist):
    return Chain(tmp_path_factory.mktemp("kill"), hist, kill=True).run()


# ------------------------------------------------------------------------------------------------ zincir degismezleri
def _check_decisions(c: Chain):
    dec, trades = c.decisions(), c.trades()
    cnt = c.engine.counters()
    # her degerlendirilen aday icin tam bir karar satiri (alinan + atlanan; aday olmayanlar 'ignore:' sayaci)
    evaluated = cnt.get("enter", 0) + sum(v for k, v in cnt.items() if k.startswith("skip:"))
    assert len(dec) == evaluated and dec, (len(dec), evaluated)
    by_dec = {t["decision_id"]: t for t in trades}
    for r in dec:
        assert r["final_action"] in ("entered", "skipped")
        if r["final_action"] == "entered":
            assert r["skip_reason"] is None and r["veto_status"] == "not_evaluated" and r["risk_allowed"] in (1, True)
            assert r["size_qty"] and r["size_qty"] > 0 and r["leverage"] and r["id"] in by_dec
        else:
            assert r["skip_reason"], r
            assert r["id"] not in by_dec and r["size_qty"] is None
            if r["skip_reason"].startswith("veto_"):
                assert r["veto_status"] == r["skip_reason"][5:] and r["veto_status"] != "allowed"
                assert r["risk_allowed"] is None
            if r["skip_reason"] == "risk_denied":
                assert r["risk_allowed"] in (0, False) and r["risk_reason"]
    assert len(by_dec) == len(trades) == sum(1 for r in dec if r["final_action"] == "entered")


def test_schema_is_v4(off):   # WP-3 (defter-ek-alanlar-spec): sema 3 -> 4
    assert L.SCHEMA_VERSION == 8  # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)
    assert off.q("PRAGMA user_version")[0]["user_version"] == 8
    assert off.decisions() and "ml_score" in off.decisions()[0]          # v3 kolonu


def test_every_candidate_has_consistent_decision_row(off, blocked):
    _check_decisions(off)
    _check_decisions(blocked)


def test_trades_have_entry_exit_fees_and_funding(off):
    trades = off.trades()
    assert trades, "en az bir islem"
    closed = [t for t in trades if t["exit_ts"]]
    assert closed, "en az bir kapanmis islem (giris + cikis satiri)"
    for t in trades:
        assert t["entry_ts"] and t["entry_price"] > 0 and t["qty"] > 0 and t["leverage"] >= 1
        assert t["fee_entry"] is not None and t["fee_entry"] > 0
        assert t["planned_risk"] > 0
    for t in closed:
        assert t["exit_price"] > 0 and t["exit_reason"] and t["exit_ts"] >= t["entry_ts"]
        assert t["fee_exit"] is not None and t["fee_exit"] > 0
        assert t["funding_paid"] is not None and np.isfinite(t["funding_paid"])
        assert t["realized_pnl"] == pytest.approx(
            t["gross_pnl"] - t["fee_entry"] - t["fee_exit"] - t["funding_paid"], abs=1e-6)
        assert t["r_multiple"] == pytest.approx(t["realized_pnl"] / t["planned_risk"], rel=1e-6)
    assert off.engine.summary().trades_opened == len(trades)


def test_risk_sizing_respects_locked_cfg(off):
    for t in off.trades():
        assert t["leverage"] == int(max(1, K.LOCKED_CFG.min_leverage))
        assert t["planned_risk"] <= off.cfg.risk_config.target_trade_risk * off.cfg.wallet_start * 1.5 + 1e-9


def test_killswitch_blocks_new_entries(killed, off):
    assert off.trades()                                           # kontrol: kill'siz ayni veride giris var
    assert Path(killed.cfg.kill_file).exists() and killed.engine.kill.active()
    assert killed.trades() == [] and killed.engine.summary().trades_opened == 0
    dec = killed.decisions()
    assert dec and not [r for r in dec if r["final_action"] == "entered"]
    cand = [r for r in dec if r["skip_reason"] == "entry_gate_closed"]
    assert cand and all(r["veto_reason"] == "gate:kill" for r in cand)     # veto/risk degerlendirilmeden kapi kapali
    _check_decisions(killed)


def test_veto_block_is_ignored_in_paper(blocked, off):
    """DD-12 WP-06a: kagitta veto yok; veto sonucu 'block' olsa da aday girilir, veto hic sorgulanmaz."""
    tgt = blocked.target
    rows = [r for r in blocked.decisions()
            if (r["pair"], r["bar_close_ts"], r["side"]) == (tgt["pair"], tgt["bar_close_ts"], tgt["side"])]
    assert len(rows) == 1
    r = rows[0]
    assert (r["final_action"], r["skip_reason"], r["veto_status"]) == ("entered", None, "not_evaluated")
    assert r["id"] in {t["decision_id"] for t in blocked.trades()}
    assert blocked.veto.lookups == []
    assert blocked.engine.counters().get("skip:veto_blocked", 0) == 0


def test_veto_result_file_missing_does_not_block_in_paper(tmp_path_factory, hist):
    """Eski davranis 'veto yok/eski -> islem yok' kagit yolundan cikti (WP-06a)."""
    c = Chain(tmp_path_factory.mktemp("noveto"), hist)
    c.veto_path.unlink()
    c.run()
    dec = c.decisions()
    assert c.trades() and not any(str(r["skip_reason"]).startswith("veto_") for r in dec)
    assert all(r["veto_status"] == "not_evaluated" for r in dec)


# ------------------------------------------------------------------------------------------------ ders + Telegram raporu
def _lesson_cfg_file(tmp: Path, c: Chain) -> Path:
    raw = json.loads((ROOT / "config" / "lesson.json").read_text())
    raw.update(mode="rule_proxy", twin_enabled=False, notifier=None, ledger_path=c.cfg.ledger_path,
               store_path=str(tmp / "lesson.sqlite"), twin_ledger_path=str(tmp / "no_twin.sqlite"))
    p = tmp / "lesson.json"
    p.write_text(json.dumps(raw))
    return p


def _load_lesson_run():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lesson_run_e2e", ROOT / "scripts" / "lesson_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_lesson_runs_on_produced_ledger_offline(off, tmp_path, capsys):
    LR = _load_lesson_run()
    cfgp = _lesson_cfg_file(tmp_path, off)
    env = {"LEDGER_PATH": off.cfg.ledger_path, "LESSON_STORE_PATH": str(tmp_path / "lesson.sqlite")}
    # LLM istemcisi/bildirimci enjekte: rule_proxy kipinde LLM zaten yok; API anahtari ortamda YOK
    rc = LR.main(["--once", "--config", str(cfgp), "--mode", "rule_proxy", "--allow-log-notifier"],
                 env=env, now_fn=lambda: LESSON_NOW, sleep_fn=lambda s: None)
    out = capsys.readouterr().out
    assert rc == 0, out
    res = json.loads(out.strip().splitlines()[-1])
    assert res["status"] in ("skipped_no_data", "skipped_gate", "no_change", "idle", "needs_user", "applied") and res["run_day"]
    # DD-12 WP-08: esiksiz ders; tiny ledger'da hicbir aday checkpoint'te degil -> skipped_gate/no_candidates
    if res["status"] == "skipped_gate":
        assert res["code"] == "no_candidates"
    con = sqlite3.connect(str(tmp_path / "lesson.sqlite"))
    try:
        runs = con.execute("SELECT run_day FROM lesson_runs").fetchall()
        ev = con.execute("SELECT status FROM lesson_run_events").fetchall()
    finally:
        con.close()
    assert runs and ev, "ders calisma kaydi yazilmali"
    # ders defteri DEGISTIRMEDI: sema hala v3, karar/islem sayilari ayni (az islem -> veri yetersiz)
    assert off.q("PRAGMA user_version")[0]["user_version"] == 8   # DD-12 WP-08: sema 6


def test_telegram_daily_report_renders_from_ledger(off, tmp_path):
    closed = [t for t in off.trades() if t["exit_ts"]]
    assert closed
    exit_tr = datetime.fromisoformat(closed[0]["exit_ts"].replace("Z", "+00:00")) + timedelta(hours=3)
    day = exit_tr.strftime("%Y-%m-%d")
    cfg = T.TelegramConfig("1:tok", 5, str(tmp_path / "tg"), "", str(tmp_path / "status.json"),
                           ledger_path=off.cfg.ledger_path,
                           budget_config=str(tmp_path / "b.json"), lesson_store=str(tmp_path / "l.sqlite"))
    now = datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(hours=18)      # 21:00 TR
    out = T.build_report(cfg, now, day, {"Defter": lambda: T.rapor_defter(cfg, day)})
    n_closed = sum(1 for t in off.trades() if t["exit_ts"]
                   and (datetime.fromisoformat(t["exit_ts"].replace("Z", "+00:00")) + timedelta(hours=3)).strftime("%Y-%m-%d") == day)
    assert f"Bugün {n_closed} işlem kapandı" in out and "kapanan=" not in out      # 20.11: sade günlük özet biçimi
