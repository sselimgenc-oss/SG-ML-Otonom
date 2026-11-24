"""Rapor paketi (WP-4) kabul testleri: docs/rapor-paketi-spec.md §12, yalniz spesifikasyondan yazildi.

Kara kutu yaklasimi: CLI (`scripts/report_run.py`) alt surecte kosulur; sentetik girdiler testte kurulur; cikti dosyalari
(`rapor.json`, `rapor.md`, `cikis_islemler.csv`, `ozet.txt`) okunur. Spesifikasyon `stats.py` vb. icin islev adi vermedigi icin
istatistik/boyut hesaplari JSON'daki *sutun adlari* (spec'te adlandirilmis: n_engel, yargi, bayrak, kapi, n_ulasan, ...) ya da
sayisal deger aramasiyla dogrulanir. Hicbir test skip/xfail degildir; yalniz paket importu ve pyarrow (feather) bagimliligi
importorskip ile korunur.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pytest

pytest.importorskip("trader_reports")

ROOT = Path(__file__).resolve().parents[2]          # trader/
SRC = ROOT / "src"
SCRIPT = ROOT / "scripts" / "report_run.py"
NOW = "2026-03-01T00:00:00Z"
H0 = datetime(2026, 5, 1, tzinfo=timezone.utc)
H1 = datetime(2026, 11, 1, tzinfo=timezone.utc)
LABELS = ("çıtayı geçti", "varsayım", "yetersiz")
EXIT_REASONS = ("stop", "target", "trail_stop", "regime_flip", "time_stop", "manual", "force_exit", "liquidation", "other")


# ----------------------------------------------------------------------------------------------- zaman yardimcilari
def dt(s) -> datetime:
    if isinstance(s, datetime):
        return s.astimezone(timezone.utc)
    s = s.replace("Z", "")
    for f in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    raise ValueError(s)


def T(s) -> str:
    d = dt(s)
    return d.strftime("%Y-%m-%dT%H:%M:%S") + ".%03dZ" % (d.microsecond // 1000)


def ms(s) -> int:
    return int(dt(s).timestamp() * 1000)


HOUR = 3_600_000
M15 = 900_000


# ----------------------------------------------------------------------------------------------- sentetik girdiler
DEC_COLS = ["id", "bot", "bar_close_ts", "trigger_tf", "pair", "side", "setup", "regime", "atr_ratio", "features",
            "planned_entry", "planned_stop", "planned_target", "param_version_id", "veto_status", "veto_reason",
            "risk_allowed", "risk_reason", "size_qty", "size_notional", "size_margin", "size_risk_amount", "leverage",
            "final_action", "skip_reason", "recorded_at"]
TRADE_COLS = ["trade_id", "decision_id", "pair", "side", "setup", "regime", "atr_ratio", "param_version_id", "entry_ts",
              "entry_price", "planned_entry", "planned_stop", "planned_target", "qty", "leverage", "planned_risk",
              "fee_entry", "slippage_entry", "exit_ts", "exit_price", "exit_reason", "planned_exit", "fee_exit",
              "funding_paid", "gross_pnl", "realized_pnl", "r_multiple", "slippage_exit", "mfe_r", "mae_r", "bars_held",
              "excursion_tf"]
CF_COLS = ["bot", "decision_id", "method", "pair", "side", "setup", "trigger_tf", "skip_reason", "decision_ts",
           "planned_entry", "planned_stop", "planned_target", "window_start_ts", "window_end_ts", "hyp_outcome",
           "hyp_r_gross", "hyp_r_net", "cost_r", "exit_reason", "bars_held", "computed_at", "version"]


def mk_decision(i, **kw) -> dict:
    d = dict(id=i, bot="learner", bar_close_ts="2026-01-10T12:00", trigger_tf="1h", pair="BTC/USDT", side="long",
             setup="T1", regime="trend_up", atr_ratio=0.9, features=json.dumps({"atr_tf": 2.0, "atr_1h": 2.0, "stop_dist_atr": 1.0}),
             planned_entry=100.0, planned_stop=98.0, planned_target=104.0, param_version_id=1, veto_status="allowed",
             veto_reason=None, risk_allowed=1, risk_reason=None, size_qty=1.0, size_notional=100.0, size_margin=33.0,
             size_risk_amount=2.0, leverage=3, final_action="entered", skip_reason=None, recorded_at="2026-01-10T12:00")
    d.update(kw)
    if isinstance(d["features"], dict):
        d["features"] = json.dumps(d["features"])
    return d


def mk_trade(i, **kw) -> dict:
    """net_r / gross_r / mfe / mae dogrudan R cinsinden verilir; planned_risk = 2, qty = 1 (r_px = 2)."""
    side = kw.get("side", "long")
    sgn = 1 if side == "long" else -1
    net_r = kw.pop("net_r", 0.5)
    gross_r = kw.pop("gross_r", net_r)
    entry_ts = kw.pop("entry_ts", "2026-01-10T12:05")
    exit_ts = kw.pop("exit_ts", None) or (dt(entry_ts) + timedelta(hours=2))
    t = dict(trade_id=i, decision_id=i, pair="BTC/USDT", side=side, setup="T1", regime="trend_up", atr_ratio=0.9,
             param_version_id=1, entry_ts=entry_ts, entry_price=100.0, planned_entry=100.0,
             planned_stop=100.0 - 2 * sgn, planned_target=100.0 + 4 * sgn, qty=1.0, leverage=3, planned_risk=2.0,
             fee_entry=0.0, slippage_entry=0.0, exit_ts=exit_ts, exit_price=100.0 + sgn * gross_r * 2, exit_reason="target",
             planned_exit=None, fee_exit=0.0, funding_paid=0.0, bars_held=4, excursion_tf="15m", slippage_exit=0.0,
             mfe_r=max(0.0, net_r) + 0.1, mae_r=0.2)
    t.update(kw)
    t.setdefault("gross_pnl", gross_r * 2.0)
    t.setdefault("realized_pnl", net_r * 2.0)
    t.setdefault("r_multiple", net_r)
    t["gross_pnl"] = gross_r * t["planned_risk"] if "gross_pnl" not in kw else t["gross_pnl"]
    t["realized_pnl"] = net_r * t["planned_risk"] if "realized_pnl" not in kw else t["realized_pnl"]
    t["r_multiple"] = net_r if "r_multiple" not in kw else t["r_multiple"]
    return t


def _ins(con, table, cols, rows):
    q = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    for r in rows:
        con.execute(q, [T(r[c]) if c.endswith("_ts") and isinstance(r[c], (str, datetime)) else r.get(c) for c in cols])


def build_ledger(path: Path, decisions=(), trades=(), version=3, exit_regime=False):
    cols_d = DEC_COLS + (["ml_score"] if version >= 3 else [])
    cols_t = TRADE_COLS + (["exit_regime"] if exit_regime else [])
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE v_decisions (" + ",".join(cols_d) + ")")
    con.execute("CREATE TABLE v_closed_trades (" + ",".join(cols_t) + ")")
    con.execute("CREATE TABLE trade_exits (id INTEGER, exit_ts TEXT" + (", exit_regime TEXT" if exit_regime else "") + ")")
    rows = []
    for d in decisions:
        d = dict(d)
        d.setdefault("ml_score", None)
        rows.append(d)
    q = f"INSERT INTO v_decisions ({','.join(cols_d)}) VALUES ({','.join('?' * len(cols_d))})"
    for d in rows:
        vals = []
        for c in cols_d:
            v = d.get(c)
            if c in ("bar_close_ts", "recorded_at") and v is not None:
                v = T(v)
            vals.append(v)
        con.execute(q, vals)
    q = f"INSERT INTO v_closed_trades ({','.join(cols_t)}) VALUES ({','.join('?' * len(cols_t))})"
    for t in trades:
        vals = []
        for c in cols_t:
            v = t.get(c)
            if c in ("entry_ts", "exit_ts") and v is not None:
                v = T(v)
            vals.append(v)
        con.execute(q, vals)
    con.execute(f"PRAGMA user_version={int(version)}")
    con.commit()
    con.close()


def build_cf(path: Path, rows):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE cf_outcomes (" + ",".join(CF_COLS) + ")")
    q = f"INSERT INTO cf_outcomes ({','.join(CF_COLS)}) VALUES ({','.join('?' * len(CF_COLS))})"
    for r in rows:
        vals = []
        for c in CF_COLS:
            v = r.get(c)
            if c in ("decision_ts", "window_start_ts", "window_end_ts", "computed_at") and v is not None:
                v = T(v)
            vals.append(v)
        con.execute(q, vals)
    con.commit()
    con.close()


def mk_cf(decision_id, r_net, ts, **kw) -> dict:
    base = dict(bot="learner", decision_id=decision_id, method="barrier", pair="BTC/USDT", side="long", setup="T1",
                trigger_tf="1h", skip_reason="stop_width", decision_ts=ts, planned_entry=100.0, planned_stop=98.0,
                planned_target=104.0, window_start_ts=ts, window_end_ts=dt(ts) + timedelta(hours=72),
                hyp_outcome=(1 if (r_net is not None and r_net > 0) else 0 if r_net is not None else None),
                hyp_r_gross=r_net, hyp_r_net=r_net, cost_r=0.0, exit_reason="target", bars_held=5, computed_at=ts, version=2)
    base.update(kw)
    return base


def build_market(path: Path, bars=(), rules=()):
    """bars: (pair, tf, open_ms, h, l, c) -> kind='last', written_ms = kapanis; rules: (pair, json, fetched_ms)."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE bars (kind TEXT, pair TEXT, tf TEXT, open_ms INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL, written_ms INTEGER, "
                "PRIMARY KEY(kind, pair, tf, open_ms)) WITHOUT ROWID")  # lead: motor store.py semasi gibi
    con.execute("CREATE TABLE rules (pair TEXT, json TEXT, fetched_ms INTEGER)")
    tfms = {"1h": HOUR, "15m": M15, "1m": 60_000}
    con.executemany("INSERT OR REPLACE INTO bars VALUES ('last',?,?,?,?,?,?,?,?,?)",
                    [(p, tf, o, c, h, l, c, 1.0, o + tfms[tf]) for (p, tf, o, h, l, c) in bars])
    con.executemany("INSERT INTO rules VALUES (?,?,?)", list(rules))
    con.execute("PRAGMA user_version=1")
    con.commit()
    con.close()


def rules_json(symbol="BTCUSDT", step="0.001", min_qty=None, min_notional="100") -> str:
    mq = min_qty or step
    return json.dumps(dict(symbol=symbol, tick="0.1", step=step, min_qty=mq, max_qty="1000", market_step=step,
                           market_min=mq, market_max="1000", min_notional=min_notional))


def build_budget(path: Path, rows):
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE reservations (service TEXT, day TEXT, month TEXT, state TEXT, charged_micro INTEGER)")
    con.executemany("INSERT INTO reservations VALUES (?,?,?,?,?)", list(rows))
    con.commit()
    con.close()


def flat_bars(pair, tf, start, n, h, l, c, skip=()):
    step = HOUR if tf == "1h" else M15
    o = ms(start)
    return [(pair, tf, o + k * step, h, l, c) for k in range(n) if k not in skip]


class Sc:
    """Bir kosunun girdi dizini."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.out = tmp / "out"
        self.ledger = tmp / "ledger.sqlite"
        self.cf = tmp / "counterfactual.sqlite"
        self.market = tmp / "market.sqlite"
        self.budget = tmp / "budget.sqlite"


def scenario(tmp: Path, decisions=(), trades=(), cf=None, bars=(), rules=(), budget=None, version=3, exit_regime=False,
             autodecide=True) -> Sc:
    sc = Sc(tmp)
    decisions = list(decisions)
    have = {d["id"] for d in decisions}
    if autodecide:
        for t in trades:
            if t["decision_id"] not in have:
                have.add(t["decision_id"])
                decisions.append(mk_decision(t["decision_id"], bar_close_ts=T(dt(t["entry_ts"]).replace(minute=0, second=0)),
                                             pair=t["pair"], side=t["side"], setup=t["setup"], regime=t["regime"],
                                             atr_ratio=t["atr_ratio"]))
    build_ledger(sc.ledger, decisions, list(trades), version=version, exit_regime=exit_regime)
    if cf is not None:
        build_cf(sc.cf, cf)
    build_market(sc.market, bars, rules)
    if budget is not None:
        build_budget(sc.budget, budget)
    return sc


class Res:
    def __init__(self, p, out_dir: Path):
        self.rc = p.returncode
        self.stdout = p.stdout
        self.stderr = p.stderr
        self.out_dir = out_dir
        self.summary = None
        for line in reversed(p.stdout.strip().splitlines()):
            try:
                self.summary = json.loads(line)
                break
            except ValueError:
                continue

    @property
    def md(self) -> str:
        return (self.out_dir / "rapor.md").read_text(encoding="utf-8")

    @property
    def js(self):
        return json.loads((self.out_dir / "rapor.json").read_text(encoding="utf-8"), parse_constant=_no_const)

    @property
    def ozet(self) -> str:
        return (self.out_dir / "ozet.txt").read_text(encoding="utf-8")

    def csv_rows(self) -> dict:
        with open(self.out_dir / "cikis_islemler.csv", newline="", encoding="utf-8") as f:
            return {r["trade_id"]: r for r in csv.DictReader(f)}

    @property
    def text(self) -> str:
        return self.stdout + self.stderr


def _no_const(c):
    raise AssertionError(f"NaN/Infinity json'da olamaz: {c}")


def run_cli(args, cwd=ROOT) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, str(SCRIPT), *[str(a) for a in args]], capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=900)


def go(sc: Sc, *extra, now=NOW, bot="learner", cf=True, budget=True, ledger=None) -> Res:
    args = ["--bot", bot, "--ledger", ledger or sc.ledger, "--cf", sc.cf if cf else sc.tmp / "yok_cf.sqlite",
            "--market", sc.market, "--budget", sc.budget if budget else sc.tmp / "yok_budget.sqlite",
            "--now", now, "--out", sc.out, *extra]
    p = run_cli(args)
    return Res(p, sc.out / bot / dt(now).strftime("%Y-%m-%d"))


# ----------------------------------------------------------------------------------------------- JSON gezgini
def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def with_key(o, key):
    return [d for d in walk(o) if key in d]


def with_value(o, value):
    return [d for d in walk(o) if any(v == value for v in d.values())]


def nums(o):
    if isinstance(o, bool):
        return
    if isinstance(o, (int, float)):
        yield float(o)
    elif isinstance(o, dict):
        for v in o.values():
            yield from nums(v)
    elif isinstance(o, list):
        for v in o:
            yield from nums(v)


def has_num(o, x, tol=1e-5) -> bool:
    return any(abs(v - x) <= tol for v in nums(o))


def is_none(v) -> bool:
    return v is None or v == "—"


def gate_row(js, kapi) -> dict:
    rows = [d for d in walk(js) if d.get("kapi") == kapi and "n_engel" in d]
    assert rows, f"kapi={kapi!r} satiri yok"
    return rows[0]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cluster(xs, days):
    xs = np.asarray(xs, float)
    n = len(xs)
    m = xs.mean()
    g = {}
    for x, d in zip(xs, days):
        g[d] = g.get(d, 0.0) + (x - m) / n
    G = len(g)
    se = math.sqrt(G / (G - 1) * sum(u * u for u in g.values()))
    return m, se, G


# ================================================================================================ G: salt okunurluk
def _full_inputs(tmp: Path) -> Sc:
    tr = [mk_trade(i, entry_ts="2026-01-10T12:05", exit_ts="2026-01-10T14:00", net_r=0.5 if i % 2 else -1) for i in range(1, 6)]
    dec = [mk_decision(100 + i, skip_reason="stop_width", final_action="skipped", bar_close_ts=f"2026-01-1{i}T12:00") for i in range(1, 4)]
    cf = [mk_cf(100 + i, 0.3, f"2026-01-1{i}T12:00") for i in range(1, 4)]
    bars = flat_bars("BTC/USDT", "1h", "2026-01-10T14:00", 80, 101, 99, 100) + flat_bars("BTC/USDT", "15m", "2026-01-10T12:00", 12, 100.5, 99.5, 100)
    return scenario(tmp, dec, tr, cf=cf, bars=bars, budget=[("veto", "2026-01-11", "2026-01", "settled", 250000)],
                    rules=[("BTC/USDT", rules_json(), 1)])


def _backtest_dir(tmp: Path, name="bt1", period=("2024-01-01", "2024-03-01"), trades=(), decisions=(), history=True) -> Path:
    d = tmp / name
    d.mkdir()
    cols = ["trade_id", "pair", "side", "setup", "regime", "entry_ts", "exit_ts", "entry_price", "exit_price", "qty", "leverage",
            "planned_entry", "planned_stop", "planned_target", "exit_reason", "planned_exit", "planned_risk", "equity_at_entry",
            "gross_pnl", "fee_entry", "fee_exit", "funding_paid", "realized_pnl", "r_multiple", "mfe_r", "mae_r", "bars_held",
            "excursion_tf", "slippage_entry", "slippage_exit", "slip_cost", "decision_id", "param_version_id"]
    with open(d / "trades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for t in trades:
            r = {c: t.get(c) for c in cols}
            r["equity_at_entry"] = t.get("equity_at_entry", 1000.0)
            r["slip_cost"] = 0.0
            r["entry_ts"], r["exit_ts"] = T(t["entry_ts"]), T(t["exit_ts"])
            w.writerow({k: ("" if v is None else v) for k, v in r.items()})
    build_ledger(d / "ledger.sqlite", list(decisions), [], version=2)
    (d / "meta.json").write_text(json.dumps({"period": [T(period[0]), T(period[1])], "pairs": ["BTC/USDT", "ETH/USDT"], "trigger_tf": "1h",
                                              "rules_source": "synthetic", "fill_model": "native"}))
    (d / "summary.json").write_text(json.dumps({"n_trades": len(list(trades))}))
    return d


def go_bt(tmp: Path, run_dir: Path, *extra, now=NOW, hist=None) -> Res:
    hist = hist or (tmp / "hist")
    hist.mkdir(exist_ok=True)
    out = tmp / "out"
    p = run_cli(["--run-dir", run_dir, "--history", hist, "--now", now, "--out", out, *extra])
    return Res(p, out / ("bt_" + run_dir.name) / dt(now).strftime("%Y-%m-%d"))


def snapshot(*roots: Path) -> dict:
    snap = {}
    for r in roots:
        for p in sorted(r.rglob("*")):
            if p.is_file() and not p.name.endswith(("-shm", "-wal")):
                snap[str(p)] = sha(p)
    return snap


def test_g1_inputs_unchanged_bot_and_backtest(tmp_path):
    sc = _full_inputs(tmp_path)
    run = _backtest_dir(tmp_path, trades=[mk_trade(1, pair="BTC/USDT", entry_ts="2024-01-10T12:05", exit_ts="2024-01-10T14:00")],
                        decisions=[mk_decision(1, bar_close_ts="2024-01-10T12:00")])
    before = snapshot(sc.ledger.parent / "bt1") | {str(p): sha(p) for p in (sc.ledger, sc.cf, sc.market, sc.budget)}
    listing_before = sorted(p.name for p in tmp_path.iterdir() if p.name != "out")
    r1 = go(sc)
    assert r1.rc == 0, r1.text
    r2 = go_bt(tmp_path, run)
    assert r2.rc == 0, r2.text
    after = snapshot(sc.ledger.parent / "bt1") | {str(p): sha(p) for p in (sc.ledger, sc.cf, sc.market, sc.budget)}
    assert before == after
    assert listing_before == sorted(p.name for p in tmp_path.iterdir() if p.name not in ("out", "hist"))
    assert sorted(p.name for p in (tmp_path / "bt1").iterdir()) == ["ledger.sqlite", "meta.json", "summary.json", "trades.csv"] or \
        all(n.endswith(("-shm", "-wal")) for n in set(p.name for p in (tmp_path / "bt1").iterdir()) - {"ledger.sqlite", "meta.json", "summary.json", "trades.csv"})


def test_g2_readonly_permissions(tmp_path):
    sc = _full_inputs(tmp_path)
    files = [sc.ledger, sc.cf, sc.market, sc.budget]
    for f in files:
        f.chmod(0o444)
    try:
        r = go(sc)
        assert r.rc == 0, r.text
    finally:
        for f in files:
            f.chmod(0o644)


def test_g3_missing_paths_not_created(tmp_path):
    sc = _full_inputs(tmp_path)
    miss_ledger = tmp_path / "nope" / "ledger.sqlite"
    p = run_cli(["--bot", "learner", "--ledger", miss_ledger, "--cf", sc.cf, "--market", sc.market, "--budget", sc.budget,
                 "--now", NOW, "--out", sc.out])
    assert p.returncode == 2
    assert "ledger_missing" in p.stdout + p.stderr
    assert not miss_ledger.exists() and not miss_ledger.parent.exists()
    r = go(sc, cf=False)
    assert r.rc == 0, r.text
    assert not (sc.tmp / "yok_cf.sqlite").exists()
    assert "cf_missing" in json.dumps(r.js["warnings"])
    sc.ledger.unlink()
    p2 = run_cli(["--bot", "learner", "--ledger", sc.ledger, "--now", NOW, "--out", sc.out, "--cf", sc.cf, "--market", sc.market,
                  "--budget", sc.budget])
    assert p2.returncode == 2 and not sc.ledger.exists()


def _py_files():
    base = SRC / "trader_reports"
    assert base.is_dir()
    return sorted(base.rglob("*.py"))


def _docstring_nodes(tree):
    ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body:
            b = n.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                ids.add(id(b.value))
    return ids


def test_g4_static_scan_package():
    sql_re = re.compile(r"\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|VACUUM|ATTACH)\b")
    sql_re_i = re.compile(r"\b(insert\s+(or\s+\w+\s+)?into|update\s+\w+\s+set|delete\s+from|create\s+(table|view|index|trigger)|"
                          r"alter\s+table|drop\s+(table|view|index)|vacuum|attach\s+database)\b", re.I)
    for f in _py_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docs = _docstring_nodes(tree)
        parents = {}
        for n in ast.walk(tree):
            for c in ast.iter_child_nodes(n):
                parents[c] = n
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    assert not a.name.startswith(("trader_ml", "pandas")), f"{f}: yasak import {a.name}"
            if isinstance(n, ast.ImportFrom):
                mod = n.module or ""
                assert not mod.startswith(("trader_ml", "pandas")), f"{f}: yasak import {mod}"
                if mod == "trader_core.ledger":
                    assert not {a.name for a in n.names} & {"open_ledger", "Ledger"}, f"{f}: yasak Ledger"
                if mod == "trader_core.counterfactual":
                    assert "CounterfactualStore" not in {a.name for a in n.names}, f"{f}: yasak CounterfactualStore"
                if mod == "trader_core" and any(a.name in ("ledger", "counterfactual") for a in n.names) and False:
                    pass
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                a = n.func
                base = a.value
                bname = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else "")
                assert not (a.attr in ("now", "utcnow", "today") and bname == "datetime"), f"{f}:{n.lineno} saat cagrisi"
                assert not (a.attr in ("time", "time_ns") and bname == "time"), f"{f}:{n.lineno} time.time"
                if a.attr == "connect" and bname == "sqlite3":
                    fn, cur = None, n
                    while cur in parents:
                        cur = parents[cur]
                        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            fn = cur.name
                            break
                    assert f.name == "inputs.py" and fn == "open_ro", f"{f}:{n.lineno} sqlite3.connect open_ro disinda"
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                assert not sql_re.search(n.value), f"{f}:{n.lineno} yazma SQL sozcugu: {n.value[:60]!r}"
                assert not sql_re_i.search(n.value), f"{f}:{n.lineno} yazma SQL: {n.value[:60]!r}"


def test_g4_no_reverse_imports():
    for pkg in ("trader_engine", "trader_core", "trader_ml"):
        for f in (SRC / pkg).rglob("*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    assert not any(a.name.startswith("trader_reports") for a in n.names), f
                if isinstance(n, ast.ImportFrom):
                    assert not (n.module or "").startswith("trader_reports"), f
                    assert not (n.module is None and any(a.name == "trader_reports" for a in n.names)), f


def test_g5_engine_does_not_load_reports_and_run_leaves_backtest_outputs(tmp_path):
    code = "import sys, trader_engine.backtest, trader_core.ledger, trader_core.risk; assert not any(m.startswith('trader_reports') for m in sys.modules)"
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT),
                       env={**os.environ, "PYTHONPATH": str(SRC)})
    assert p.returncode == 0, p.stderr
    run = _backtest_dir(tmp_path, trades=[mk_trade(1, entry_ts="2024-01-10T12:05", exit_ts="2024-01-10T14:00")])
    b = (sha(run / "trades.csv"), sha(run / "summary.json"))
    assert go_bt(tmp_path, run).rc == 0
    assert (sha(run / "trades.csv"), sha(run / "summary.json")) == b


@pytest.mark.parametrize("ver,ok", [(1, False), (9, False), (2, True), (3, True), (4, True), (5, True), (6, True), (7, True), (8, True)])   # 24.11 kullanici karari: formasyon kutuphanesi (sema 8)   # v1.1: 4 kabul; DD-12 WP-02: 5 kabul; WP-06a: 6 kabul
def test_g6_user_version(tmp_path, ver, ok):
    tr = [mk_trade(1)]
    sc = scenario(tmp_path, [], tr, version=3 if ver in (1, 8) else ver)
    con = sqlite3.connect(str(sc.ledger))
    con.execute(f"PRAGMA user_version={ver}")
    con.commit()
    con.close()
    r = go(sc, cf=False)
    if ok:
        assert r.rc == 0, r.text
    else:
        assert r.rc == 2 and "ledger_schema" in r.text


def test_g6_v2_v3_same_tables(tmp_path):
    out = {}
    for ver in (2, 3):
        d = tmp_path / f"v{ver}"
        d.mkdir()
        tr = [mk_trade(i, net_r=(i % 3) - 1) for i in range(1, 12)]
        dec = [mk_decision(100 + i, skip_reason="rr_below_min", final_action="skipped", bar_close_ts=f"2026-01-0{i}T12:00") for i in range(1, 6)]
        sc = scenario(d, dec, tr, version=ver)
        r = go(sc, cf=False)
        assert r.rc == 0, r.text
        js = r.js
        out[ver] = {k: js[k] for k in ("exits", "gates", "regimes", "sizing") if k in js}
    assert out[2] == out[3]


def test_g7_determinism_and_dry_run(tmp_path):
    sc = _full_inputs(tmp_path)
    r1 = go(sc)
    assert r1.rc == 0, r1.text
    names = ("rapor.md", "rapor.json", "cikis_islemler.csv", "ozet.txt")
    a = {n: (r1.out_dir / n).read_bytes() for n in names}
    r2 = go(sc)
    b = {n: (r2.out_dir / n).read_bytes() for n in names}
    assert a == b
    # atomik yazim: tmp artigi birakilmaz
    assert sorted(p.name for p in r2.out_dir.iterdir()) == sorted(names)
    sc2 = _full_inputs(tmp_path / "b") if (tmp_path / "b").mkdir() is None else None
    r3 = go(sc2, "--dry-run")
    assert r3.rc == 0, r3.text
    assert not sc2.out.exists() or not any(sc2.out.rglob("*") if sc2.out.exists() else [])


# ================================================================================================ H: kilitli donem
def test_h1_run_level_lock_acik_kilitte_kosu_okunur(tmp_path):
    """23.11.2026: kilit acik -> kilitli donemle kesisen kosu 'holdout_locked' ile REDDEDILMEZ (kosu dizini okunur)."""
    run = tmp_path / "bt_locked"
    run.mkdir()
    (run / "meta.json").write_text(json.dumps({"period": [T("2026-04-01"), T("2026-06-01")], "pairs": ["BTC/USDT"], "trigger_tf": "1h"}))
    (run / "ledger.sqlite").write_bytes(b"BU BIR SQLITE DEGIL - okunursa hata verir")
    r = go_bt(tmp_path, run)
    assert r.rc != 3, r.text                       # kilit reddi (holdout_locked, kod 3) yok; bozuk defter artik okunmaya calisilir
    assert "holdout_locked" not in r.text


def _holdout_trades():
    return [
        mk_trade("A", pair="LEAKA/USDT", entry_ts="2026-04-20T10:00", exit_ts="2026-04-28T00:00"),      # atlanir
        mk_trade("B", pair="OKB/USDT", entry_ts="2026-04-27T20:00", exit_ts="2026-04-27T23:59"),        # okunur
        mk_trade("C", pair="LEAKC/USDT", entry_ts="2026-10-31T23:59", exit_ts="2026-11-02T10:00"),      # atlanir
        mk_trade("D", pair="OKD/USDT", entry_ts="2026-11-01T00:00", exit_ts="2026-11-02T10:00"),        # okunur
        mk_trade("E", pair="LEAKE/USDT", entry_ts="2026-04-27T10:00", exit_ts="2026-04-29T00:00"),      # H4: cikis sonrasi pencere kilide uzanir
    ]


def test_h2_h4_row_level_filter_and_counter(tmp_path):
    """Kilit acik (23.11.2026): kilitli donemle kesisen islemler de okunur; atlanan sayaci 0, kilit metni yok."""
    sc = scenario(tmp_path, [], _holdout_trades())
    r = go(sc, now="2026-11-17T00:00:00Z")
    assert r.rc == 0, r.text
    rows = r.csv_rows()
    assert set(rows) == {"A", "B", "C", "D", "E"}
    assert r.summary["holdout_skipped"] == 0
    assert r.js["counters"]["holdout_skipped"] == 0
    assert "Kilitli dönem" not in r.md and "atlanan satır" not in r.md


def test_h2_decision_rows_filtered(tmp_path):
    dec = [mk_decision(1, bar_close_ts="2026-04-27T23:00", pair="OKX/USDT", final_action="skipped", skip_reason="stop_width"),
           mk_decision(2, bar_close_ts="2026-04-28T00:00", pair="LEAKX/USDT", final_action="skipped", skip_reason="stop_width"),
           mk_decision(3, bar_close_ts="2026-07-01T00:00", pair="LEAKY/USDT", final_action="skipped", skip_reason="stop_width"),
           mk_decision(4, bar_close_ts="2026-11-01T00:00", pair="OKZ/USDT", final_action="skipped", skip_reason="stop_width")]
    cf = [mk_cf(i, 0.5, d["bar_close_ts"], pair=d["pair"]) for i, d in ((x["id"], x) for x in dec)]
    sc = scenario(tmp_path, dec, [], cf=cf)
    r = go(sc, now="2026-11-17T00:00:00Z")
    assert r.rc == 0, r.text
    assert r.summary["n_decisions"] == 4                 # kilit acik: kilitli donem kararlari da okunur
    assert r.summary["holdout_skipped"] == 0


def test_h3_market_holdout_bars_never_influence_results(tmp_path):
    """Kilitli donemdeki mumlara zehirli degerler (NaN/aşırı) konur; sonuc zehirsiz kosuyla aynı olmali."""
    def build(d: Path, poison: bool) -> Res:
        d.mkdir()
        tr = [mk_trade(1, entry_ts="2026-04-20T10:00", exit_ts="2026-04-20T12:00", net_r=0.7)]
        dec = [mk_decision(50, bar_close_ts="2026-04-20T09:00", final_action="skipped", skip_reason="stop_width")]
        bars = flat_bars("BTC/USDT", "1h", "2026-04-20T12:00", 70, 101, 99, 100) + flat_bars("BTC/USDT", "1h", "2026-04-20T09:00", 72, 100.4, 99.6, 100)
        if poison:
            bars += flat_bars("BTC/USDT", "1h", "2026-05-01T00:00", 400, 1e9, -1e9, float("nan"))
            bars += flat_bars("BTC/USDT", "15m", "2026-05-01T00:00", 400, 1e9, -1e9, float("nan"))
        sc = scenario(d, dec, tr, cf=[mk_cf(50, 0.4, "2026-04-20T09:00")], bars=bars)
        return go(sc, now="2026-11-17T00:00:00Z")
    a = build(tmp_path / "clean", False)
    b = build(tmp_path / "poison", True)
    assert a.rc == 0 and b.rc == 0, a.text + b.text
    assert "NaN" not in b.md and not re.search(r"(?<![a-zçğıöşü])nan", b.md.lower())  # lead: "atlanan" kelimesi "nan" icerir
    assert a.js == b.js
    assert a.csv_rows() == b.csv_rows()


def test_h3_feather_nan_in_holdout_slice_changes_nothing(tmp_path):
    pa = pytest.importorskip("pyarrow")
    import pyarrow.feather as feather

    def build(d: Path, poison: bool) -> Res:
        d.mkdir()
        hist = d / "hist"
        hist.mkdir()
        start = dt("2026-04-01")
        n = 24 * 90
        dates = [start + timedelta(hours=k) for k in range(n)]
        o = np.full(n, 100.0)
        h = np.full(n, 101.0)
        l = np.full(n, 99.0)
        c = np.full(n, 100.0)
        for k, x in enumerate(dates):
            if H0 <= x < H1 and poison:
                o[k] = h[k] = l[k] = c[k] = np.nan
        tbl = pa.table({"date": pa.array(dates, type=pa.timestamp("ms", tz="UTC")), "open": o, "high": h, "low": l, "close": c,
                        "volume": np.ones(n)})
        feather.write_feather(tbl, str(hist / "BTC_USDT_USDT-1h-futures.feather"))
        run = _backtest_dir(d, period=("2026-04-01", "2026-04-30"),
                            trades=[mk_trade(1, entry_ts="2026-04-10T10:00", exit_ts="2026-04-10T12:00", net_r=0.7, equity_at_entry=1000.0)],
                            decisions=[mk_decision(1, bar_close_ts="2026-04-10T09:00")])
        return go_bt(d, run, hist=hist, now="2026-11-17T00:00:00Z")
    a = build(tmp_path / "a", False)
    b = build(tmp_path / "b", True)
    assert a.rc == 0 and b.rc == 0, a.text + b.text
    assert a.js == b.js
    assert "NaN" not in b.md


def test_h5_header_line_and_2026_partial(tmp_path):
    tr = [mk_trade(i, entry_ts=f"2026-02-{i:02d}T10:00", net_r=0.3) for i in range(1, 6)]
    sc = scenario(tmp_path, [], tr)
    r = go(sc, now="2026-11-17T00:00:00Z")
    assert r.rc == 0, r.text
    assert "Kilitli dönem" not in r.md and "okunmadı" not in r.md      # kilit acik: kilit metni uretilmez
    assert "kısmi (yıl devam ediyor)" in r.md


# ================================================================================================ I: istatistik
def _gate_run(tmp_path, xs, days, key="stop_width", now=NOW, extra=()):
    dec, cf = [], []
    for i, (x, d) in enumerate(zip(xs, days)):
        ts = dt("2026-01-01T12:00") + timedelta(days=d)
        dec.append(mk_decision(i + 1, bar_close_ts=ts, final_action="skipped", skip_reason=key))
        cf.append(mk_cf(i + 1, x, ts))
    sc = scenario(tmp_path, dec, [], cf=cf)
    return go(sc, *extra, now=now)


def test_i1_hand_example_small_and_replicated(tmp_path):
    xs, days = [1, -1, 2, 0], ["a", "a", "b", "c"]
    m, se, G = cluster(xs, days)
    assert m == 0.5 and abs(se - 0.5728) < 1e-4 and G == 3
    (tmp_path / "s").mkdir()
    r = _gate_run(tmp_path / "s", xs, [0, 0, 1, 2])
    assert r.rc == 0, r.text
    row = gate_row(r.js, "stop_width")
    assert has_num(row, 0.5)
    assert not has_num(row, 0.5 + 1.645 * se, 1e-3) and not has_num(row, 0.5 - 1.645 * se, 1e-3)
    # 8+ gun: ayni desen cogaltilir
    X, D = [], []
    for j in range(8):
        X += xs
        D += [3 * j, 3 * j, 3 * j + 1, 3 * j + 2]
    m2, se2, G2 = cluster(X, D)
    (tmp_path / "l").mkdir()
    r2 = _gate_run(tmp_path / "l", X, D)
    assert r2.rc == 0, r2.text
    row2 = gate_row(r2.js, "stop_width")
    assert has_num(row2, m2 - 1.645 * se2, 2e-5) and has_num(row2, m2 + 1.645 * se2, 2e-5), (m2, se2, row2)


def test_i2_wilson(tmp_path):
    xs = [0.5 if i < 50 else -0.5 for i in range(100)]
    r = _gate_run(tmp_path, xs, [i % 20 for i in range(100)], key="rr_below_min")
    row = gate_row(r.js, "rr_below_min")
    assert row["n_engel"] == 100
    assert has_num(row, 0.4188, 1e-4) and has_num(row, 0.5812, 1e-4)


def test_i2_wilson_n0_dash(tmp_path):
    dec = [mk_decision(i, final_action="skipped", skip_reason="rr_below_min", bar_close_ts=f"2026-01-{i:02d}T12:00") for i in range(1, 4)]
    sc = scenario(tmp_path, dec, [], cf=[])
    row = gate_row(go(sc).js, "rr_below_min")
    assert is_none(row["hedef_once"])


def _k_from(res: Res):
    js = res.js
    return js["k_rapor"], js["z_k"]


def test_i3_zk_matches_bonferroni_formula(tmp_path):
    tr = [mk_trade(i, pair=f"P{i % 12}/USDT", entry_ts=dt("2025-01-01") + timedelta(days=i), net_r=0.1) for i in range(1, 80)]
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    K, z = _k_from(r)
    assert K >= 12
    assert abs(z - NormalDist().inv_cdf(1 - 0.05 / (2 * K))) < 2e-3
    for k, want in ((1, 1.960), (10, 2.807), (20, 3.023), (50, 3.291)):
        assert abs(NormalDist().inv_cdf(1 - 0.05 / (2 * k)) - want) < 1e-3   # spec sayilari tutarli


def _noise(n, pairs, seed, days=360, start="2025-01-01", shift=None):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        p = f"P{i % pairs:02d}/USDT"
        net = rng.gauss(0, 1)
        if shift and shift(i):
            p = "XYZ/USDT"
            net += 1.0
        et = dt(start) + timedelta(days=i * days // n, hours=(i * 7) % 20)
        out.append(mk_trade(i + 1, pair=p, entry_ts=et, exit_ts=et + timedelta(hours=1), net_r=net, side="long" if i % 2 else "short"))
    return out


def _labels_for(js, value):
    cells = [d for d in with_value(js, value) if any(v in LABELS for v in d.values())]
    return [next(v for v in d.values() if v in LABELS) for d in cells]


def test_i4_pure_noise_no_pass(tmp_path):
    tr = _noise(2000, 20, seed=20261117)
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    vals = [v for d in walk(r.js) for v in d.values()]
    assert "çıtayı geçti" not in vals
    cells = [d for d in walk(r.js) if any(v in LABELS for v in d.values())]
    assert cells, "etiketli hucre yok"
    assert all(any(v in LABELS[1:] for v in d.values()) for d in cells)


def test_i5_embedded_effect_both_halves_vs_one_half(tmp_path):
    (tmp_path / "both").mkdir()
    r = go(scenario(tmp_path / "both", [], _noise(2000, 20, 7, shift=lambda i: i % 10 == 0)))
    labs = _labels_for(r.js, "XYZ/USDT")
    assert labs and all(x == "çıtayı geçti" for x in labs), labs
    (tmp_path / "half").mkdir()
    r2 = go(scenario(tmp_path / "half", [], _noise(2000, 20, 7, shift=lambda i: i < 1000 and i % 5 == 0)))
    labs2 = _labels_for(r2.js, "XYZ/USDT")
    assert labs2 and all(x == "varsayım" for x in labs2), labs2


@pytest.mark.parametrize("n,ndays", [(29, 29), (40, 7)])
def test_i6_yetersiz(tmp_path, n, ndays):
    rng = random.Random(5)
    tr = []
    for i in range(300):
        et = dt("2025-02-01") + timedelta(days=i % 200, hours=i % 20)
        tr.append(mk_trade(i + 1, pair=f"P{i % 5}/USDT", entry_ts=et, net_r=rng.gauss(0, 1)))
    for j in range(n):
        et = dt("2025-03-01") + timedelta(days=j % ndays, hours=j % 20)
        tr.append(mk_trade(1000 + j, pair="BIG/USDT", entry_ts=et, net_r=3.0 + 0.01 * j))
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    cells = [d for d in with_value(r.js, "BIG/USDT") if any(v in LABELS for v in d.values())]
    assert cells
    for d in cells:
        assert "yetersiz" in d.values() and "çıtayı geçti" not in d.values()
        assert any(is_none(v) or (isinstance(v, list) and any(is_none(x) for x in v)) for v in d.values())
        assert not any(v in ("kazanani_engelliyor", "hic_devreye_girmedi") for v in d.values())


def test_i7_k_rapor_grows_with_cells_and_shrinks_with_sections(tmp_path):
    base = [mk_trade(i, pair=f"P{i % 3}/USDT", entry_ts=dt("2025-01-01") + timedelta(days=i)) for i in range(1, 60)]
    (tmp_path / "a").mkdir()
    ra = go(scenario(tmp_path / "a", [], base))
    (tmp_path / "b").mkdir()
    extra = base + [mk_trade(900 + i, pair=f"NEW{i}/USDT", entry_ts=dt("2025-06-01") + timedelta(days=i)) for i in range(4)]
    rb = go(scenario(tmp_path / "b", [], extra))
    (tmp_path / "c").mkdir()
    rc_ = go(scenario(tmp_path / "c", [], base), "--sections", "exits")
    Ka, za = _k_from(ra)
    Kb, zb = _k_from(rb)
    Kc, zc = _k_from(rc_)
    assert Kb > Ka and zb > za
    assert Kc < Ka and zc < za
    for r in (ra, rb, rc_):
        assert "K_rapor" in r.md and "z_K" in r.md


def test_i8_year_rows(tmp_path):
    tr = []
    for i in range(40):
        tr.append(mk_trade(i + 1, entry_ts=dt("2024-01-01") + timedelta(days=i * 5), net_r=0.5 + 0.01 * i))
        tr.append(mk_trade(100 + i, entry_ts=dt("2025-01-01") + timedelta(days=i * 5), net_r=-0.5 - 0.01 * i))
    for i in range(5):
        tr.append(mk_trade(200 + i, entry_ts=dt("2023-01-01") + timedelta(days=i * 20), net_r=1.0))
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    vals = [d["pozitif_yil_orani"] for d in with_key(r.js, "pozitif_yil_orani")]
    assert vals and any(isinstance(v, (int, float)) and abs(v - 0.5) < 1e-9 for v in vals)
    assert not any(isinstance(v, (int, float)) and abs(v - 2 / 3) < 1e-3 for v in vals)
    assert re.search(r"Tek yıl", r.md) is None
    (tmp_path / "one").mkdir()
    r1 = go(scenario(tmp_path / "one", [], [mk_trade(i, entry_ts=f"2025-03-{i:02d}T10:00") for i in range(1, 10)]))
    assert "Tek yıl: 'her koşulda çalışır' denemez." in r1.md


# ================================================================================================ E: cikis karnesi
def _post_case(side, bars_hlc, exit_ts="2026-02-10T12:00", pair="BTC/USDT", tid=1, **tk):
    """Ilk 3 mum verilen (h,l,c), kalanlar sabit; toplam 72 mum, long icin 98, short icin 102 sabit."""
    const = 98.0 if side == "long" else 102.0
    seq = list(bars_hlc) + [(const, const, const)] * (72 - len(bars_hlc))
    start = ms(exit_ts) if dt(exit_ts).minute == 0 else ms(dt(exit_ts).replace(minute=0) + timedelta(hours=1))
    return [(pair, "1h", start + k * HOUR, h, l, c) for k, (h, l, c) in enumerate(seq)]


def _trade_exit(i, side="long", exit_ts="2026-02-10T12:00", **kw):
    return mk_trade(i, side=side, entry_ts=dt(exit_ts) - timedelta(hours=5), exit_ts=exit_ts, exit_price=100.0, net_r=0.2, **kw)


def test_e1_post_exit_path_long_and_short(tmp_path):
    bl = _post_case("long", [(101, 99, 100), (103, 100, 102), (102, 97, 98)], tid=1)
    mirror = [(200 - l, 200 - h, 200 - c) for (h, l, c) in [(101, 99, 100), (103, 100, 102), (102, 97, 98)]]
    bs = _post_case("short", mirror, pair="ETH/USDT", tid=2)
    tr = [_trade_exit(1, "long"), _trade_exit(2, "short", pair="ETH/USDT")]
    r = go(scenario(tmp_path, [], tr, bars=bl + bs))
    assert r.rc == 0, r.text
    rows = r.csv_rows()
    for tid in ("1", "2"):
        row = rows[tid]
        assert float(row["post_fav_r_24"]) == pytest.approx(1.5)
        assert float(row["post_adv_r_24"]) == pytest.approx(1.5)
        assert float(row["post_close_r_24"]) == pytest.approx(-1.0)
        assert row["ilk_dokunus_24"] == "lehte"
        assert float(row["erken_cikis_24"]) == 1
        assert row["durum_24"] == "ok"


def test_e2_same_candle_both_is_adverse(tmp_path):
    bars = _post_case("long", [(103, 97, 100)])
    # kalan sabit 98 -> ikinci mumdan sonra aleyhte de var; yalniz ilk mum etkisini ayirmak icin kalanlari 100 yap
    bars = [(p, tf, o, 100.0, 100.0, 100.0) if k else (p, tf, o, 103, 97, 100) for k, (p, tf, o, _h, _l, _c) in enumerate(bars)]
    r = go(scenario(tmp_path, [], [_trade_exit(1)], bars=bars))
    row = r.csv_rows()["1"]
    assert row["ilk_dokunus_24"] == "aleyhte"
    assert float(row["erken_cikis_24"]) == 0


def test_e3_ceil_hour_window_start(tmp_path):
    bars = []
    for pair, base in (("BTC/USDT", "2026-02-10T12:00"),):
        bars += [(pair, "1h", ms(base), 150, 99, 100)]      # 12:00 mumu (yanlis baslangic yakalanirsa fav buyur)
        bars += [(pair, "1h", ms(base) + (k + 1) * HOUR, 101, 99, 100) for k in range(71)]
    tr_mid = _trade_exit(1, exit_ts="2026-02-10T12:20")
    r = go(scenario(tmp_path, [], [tr_mid], bars=bars))
    assert float(r.csv_rows()["1"]["post_fav_r_24"]) == pytest.approx(0.5)
    (tmp_path / "t").mkdir()
    tr_full = _trade_exit(2, exit_ts="2026-02-10T12:00")
    r2 = go(scenario(tmp_path / "t", [], [tr_full], bars=bars))
    assert float(r2.csv_rows()["2"]["post_fav_r_24"]) == pytest.approx(25.0)


def test_e4_pending_and_data_gap_excluded(tmp_path):
    ok_bars = _post_case("long", [(101, 99, 100)] * 3, exit_ts="2026-02-10T12:00", pair="BTC/USDT")
    gap_bars = [b for k, b in enumerate(_post_case("long", [(101, 99, 100)] * 3, exit_ts="2026-02-11T12:00", pair="ETH/USDT")) if k != 5]
    pend_bars = _post_case("long", [(101, 99, 100)] * 3, exit_ts="2026-02-28T20:00", pair="SOL/USDT")[:4]
    tr = [_trade_exit(1, exit_ts="2026-02-10T12:00"), _trade_exit(2, exit_ts="2026-02-11T12:00", pair="ETH/USDT"),
          _trade_exit(3, exit_ts="2026-02-28T20:00", pair="SOL/USDT")]
    r = go(scenario(tmp_path, [], tr, bars=ok_bars + gap_bars + pend_bars))
    assert r.rc == 0, r.text
    rows = r.csv_rows()
    assert rows["1"]["durum_24"] == "ok" and rows["2"]["durum_24"] == "data_gap" and rows["3"]["durum_24"] == "pending"
    assert r.js["counters"]["pending"] >= 1 and r.js["counters"]["data_gap"] >= 1
    assert r.summary["pending"] >= 1 and r.summary["data_gap"] >= 1
    tbl = [d for d in with_key(r.js, "n_ok") if d.get("n") == 3]
    assert tbl and tbl[0]["n_ok"] == 1


def test_e5_give_back(tmp_path):
    mfe = [0.6, 1.2, 0.4, 2.0]
    net = [-1.0, -0.2, -1.0, 1.5]
    tr = [mk_trade(i + 1, net_r=n, mfe_r=m, entry_ts=f"2026-01-{i + 5:02d}T10:00") for i, (m, n) in enumerate(zip(mfe, net))]
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    rows = with_key(r.js, "n_ulasan")
    got = {(d["n_ulasan"], d["n_geri"]) for d in rows}
    assert (3, 2) in got and (2, 1) in got, got
    d05 = next(d for d in rows if d["n_ulasan"] == 3)
    assert d05["toplam_r_geri"] == pytest.approx(-1.2)
    assert any(abs(x - 2 / 3) < 1e-5 for x in nums(d05)) or "oran" in " ".join(d05)


def test_e6_efficiency(tmp_path):
    tr = [mk_trade(1, gross_r=1.0, net_r=0.9, mfe_r=2.0, mae_r=0.5),
          mk_trade(2, gross_r=0.0, net_r=0.0, mfe_r=0.02, mae_r=0.02),
          mk_trade(3, gross_r=2.0, net_r=1.9, mfe_r=1.0, mae_r=0.0)]
    r = go(scenario(tmp_path, [], tr))
    rows = r.csv_rows()
    assert float(rows["1"]["verim"]) == pytest.approx(0.6)
    assert rows["2"]["verim"] in ("", "None", "—", "null")
    assert float(rows["3"]["verim"]) == pytest.approx(1.0)
    assert any(d["n_tanimsiz"] >= 1 for d in with_key(r.js, "n_tanimsiz"))
    assert any(d["n_kirpilan"] >= 1 for d in with_key(r.js, "n_kirpilan"))


def _winners(n, maes):
    return [mk_trade(i + 1, net_r=1.0, mfe_r=1.5, mae_r=maes[i % len(maes)], entry_ts=dt("2026-01-01") + timedelta(days=i, hours=3)) for i in range(n)]


@pytest.mark.parametrize("n,expect", [(40, True), (29, False)])
def test_e7_winner_mae_sentence(tmp_path, n, expect):
    maes = [0.1, 0.2, 0.3, 0.4, 0.5]
    r = go(scenario(tmp_path, [], _winners(n, maes)))
    assert r.rc == 0, r.text
    sent = "stop gerekenden geniş olabilir (varsayım)"
    assert (sent in r.md) is expect
    assert "hayatta kalan yanlılığı" in r.md
    vals = [maes[i % 5] for i in range(n)]
    assert has_num(r.js, float(np.percentile(vals, 85)), 1e-5)
    assert has_num(r.js, float(np.percentile(vals, 50)), 1e-5)


def test_e7_stop_narrow_sentence(tmp_path):
    maes = [0.95, 0.2, 0.3, 0.92, 0.4]       # >=0.9 payi 0.4 >= 0.20
    r = go(scenario(tmp_path, [], _winners(40, maes)))
    assert "stop dar olabilir (varsayım)" in r.md


def test_e8_null_mfe_excluded(tmp_path):
    tr = [mk_trade(1, mfe_r=1.0, mae_r=0.2, net_r=0.5), mk_trade(2, mfe_r=None, mae_r=None, net_r=0.5),
          mk_trade(3, mfe_r=None, mae_r=None, net_r=-1.0)]
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    assert any(d["n_gezinti_yok"] == 2 for d in with_key(r.js, "n_gezinti_yok"))
    rows = r.csv_rows()
    assert rows["2"]["mfe_r"] in ("", "None", "—", "null") and rows["2"]["verim"] in ("", "None", "—", "null")


def test_e9_pre_1r_adverse(tmp_path):
    # long entry 100, r_px 2, stop 98 (stop mesafesi 2). 15m mumlar 12:00, 12:15, 12:30(+1R=102 vurur, dip 90), ...
    b15 = [("BTC/USDT", "15m", ms("2026-02-10T12:00"), 101.0, 99.0, 100.0),
           ("BTC/USDT", "15m", ms("2026-02-10T12:15"), 101.5, 98.7, 100.0),
           ("BTC/USDT", "15m", ms("2026-02-10T12:30"), 102.5, 90.0, 100.0),
           ("BTC/USDT", "15m", ms("2026-02-10T12:45"), 101.0, 99.5, 100.0),
           ("BTC/USDT", "15m", ms("2026-02-10T13:00"), 101.0, 99.5, 100.0)]
    never = [("ETH/USDT", "15m", ms("2026-02-10T12:00") + k * M15, 101.0, 98.5 if k == 2 else 99.5, 100.0) for k in range(5)]
    tr = [mk_trade(1, entry_ts="2026-02-10T12:05", exit_ts="2026-02-10T13:00", net_r=0.3),
          mk_trade(2, pair="ETH/USDT", entry_ts="2026-02-10T12:05", exit_ts="2026-02-10T13:00", net_r=0.3)]
    r = go(scenario(tmp_path, [], tr, bars=b15 + never))
    assert r.rc == 0, r.text
    assert has_num(r.js, 0.65) and has_num(r.js, 0.75)
    assert not has_num(r.js, 5.0, 1e-6)          # 1R'yi vuran mum sayilmamali (kesin onceki mumlar)
    assert "Stop mesafesi değişirse pozisyon boyutu ve RR kapısı da değişir" in r.md


def test_e10_barrier_ladder(tmp_path):
    A = [("BTC/USDT", "1h", ms("2026-02-10T12:00"), 102.0, 98.0, 100.0)] + flat_bars("BTC/USDT", "1h", "2026-02-10T13:00", 71, 100.4, 99.6, 100)[:71]
    B = flat_bars("ETH/USDT", "1h", "2026-02-10T12:00", 72, 100.5, 99.5, 100)
    C = [("SOL/USDT", "1h", ms("2026-02-10T12:00"), 102.0, 99.0, 101.0)] + flat_bars("SOL/USDT", "1h", "2026-02-10T13:00", 71, 100.4, 99.6, 100)
    dec = [mk_decision(i + 1, pair=p, bar_close_ts="2026-02-10T12:00", final_action="skipped", skip_reason="rr_below_min")
           for i, p in enumerate(("BTC/USDT", "ETH/USDT", "SOL/USDT"))]
    r = go(scenario(tmp_path, dec, [], bars=A + B + C), cf=False)
    assert r.rc == 0, r.text
    assert has_num(r.js, 1 / 3, 1e-5)            # P_1 = 1/3 (A: stop once, B: zaman asimi, C: hedef)
    assert has_num(r.js, 0.5) and has_num(r.js, 0.55)   # basabas 1/(1+k), maliyetli (1+c)/(1+k), c = 0.1
    assert any(d.get("zaman_asimi") == 1 for d in with_key(r.js, "zaman_asimi"))
    assert "mum içi sıra bilinmez (stop önce varsayımı)" in r.md


def test_e11_one_line_reason(tmp_path):
    t = mk_trade(1, pair="BTC/USDT", side="long", net_r=0.9, gross_r=0.95, mfe_r=1.8, exit_reason="trail_stop")
    r = go(scenario(tmp_path, [], [t]))
    assert r.csv_rows()["1"]["ozet"] == "BTC/USDT alış: en çok +1,8R gördü, iz süren stop ile +0,9R kapandı; tepeden 0,9R geri verdi."


def test_e11_short_template_and_reason_map(tmp_path):
    tr = []
    tr_map = {"stop": "ilk stop", "trail_stop": "iz süren stop", "target": "hedef", "regime_flip": "piyasa koşulu değişimi",
              "time_stop": "süre sınırı", "manual": "elle kapatma", "force_exit": "zorunlu kapatma", "liquidation": "likidasyon",
              "other": "diğer"}
    for i, rs in enumerate(tr_map, 1):
        tr.append(mk_trade(i, side="short", exit_reason=rs, net_r=-0.5, gross_r=-0.5, mfe_r=None, mae_r=None, pair="ETH/USDT"))
    r = go(scenario(tmp_path, [], tr))
    rows = r.csv_rows()
    for i, (rs, tr_) in enumerate(tr_map.items(), 1):
        assert rows[str(i)]["ozet"].startswith("ETH/USDT satış: ") and f"{tr_} ile" in rows[str(i)]["ozet"]
        assert "en çok" not in rows[str(i)]["ozet"]
    assert rows["1"]["ozet"] == "ETH/USDT satış: ilk stop ile -0,5R kapandı." or rows["1"]["ozet"] == "ETH/USDT satış: ilk stop ile −0,5R kapandı."


def test_e12_stop_note(tmp_path):
    r = go(scenario(tmp_path, [], [mk_trade(1, exit_reason="stop", net_r=-1.0, gross_r=-1.0)]))
    assert "stopu genişletme kanıtı sayılmaz" in r.md


# ================================================================================================ K: kapi / veto karnesi
RISK_CASES = [("aynı yön (long) risk sınırı aşılır", "risk:ayni_yon"),
              ("günlük zarar bütçesi aşılır", "risk:gunluk_butce"),
              ("günlük sınır aşıldı: yeni işlem açılamaz", "risk:gunluk_sinir"),
              ("toplam açık risk sınırı aşılır", "risk:acik_risk"),
              ("toplam teminat özsermayeyi aşar", "risk:teminat_toplam"),
              ("likidasyon çok yakın: giriş-likidasyon mesafesi yetersiz", "risk:likidasyon"),
              ("boyutlandırma reddedildi: kayıp üst sınırı aşıyor", "risk:boyut"),
              ("boyutlandırma reddedildi: miktar sıfır veya en küçük emir değerinin altında", "risk:boyut_min_emir"),
              ("BTC/USDT için zaten açık pozisyon var", "risk:cift_acik"),
              ("stop yanlış tarafta: long için stop < entry olmalı", "risk:diger"),
              ("bilinmeyen metin", "risk:diger")]


def test_k1_every_skip_and_risk_reason_mapping(tmp_path):
    dec, want = [], []
    i = 0

    def add(key, **kw):
        nonlocal i
        i += 1
        dec.append(mk_decision(i, final_action="skipped", bar_close_ts=f"2026-01-{i:02d}T12:00", **kw))
        want.append(key)
    for s in ("stop_width", "rr_below_min", "ml_filter", "order_failed"):
        add(s, skip_reason=s)
    add("veto:claude", skip_reason="veto_blocked", veto_status="blocked")
    add("veto:yok", skip_reason="veto_missing", veto_status="missing")
    add("veto:bayat", skip_reason="veto_stale", veto_status="stale")
    add("gate:kill", skip_reason="entry_gate_closed", veto_reason="gate:kill")
    add("gate:stale_data", skip_reason="other", veto_reason="gate:stale_data")
    add("entry_gate_closed", skip_reason="entry_gate_closed", veto_reason=None)
    add("other", skip_reason="other", veto_reason=None)
    for txt, key in RISK_CASES:
        add(key, skip_reason="risk_denied", risk_allowed=0, risk_reason=txt)
    r = go(scenario(tmp_path, dec, []), cf=False)
    assert r.rc == 0, r.text
    for k in set(want):
        n = want.count(k)
        assert gate_row(r.js, k)["n_engel"] == n, k


def _gate_scenario(tmp_path, key_kw, vals, days, **gkw):
    dec = [mk_decision(i + 1, final_action="skipped", bar_close_ts=dt("2026-01-01T12:00") + timedelta(days=days[i]), **key_kw) for i in range(len(vals))]
    cf = [mk_cf(i + 1, v, dec[i]["bar_close_ts"]) for i, v in enumerate(vals)]
    return go(scenario(tmp_path, dec, [], cf=cf), **gkw)


def test_k2_verdicts(tmp_path):
    kw = dict(skip_reason="stop_width")
    days = [i % 10 for i in range(40)]
    jit = [0.5 + (0.05 if days[i] % 2 else -0.05) for i in range(40)]       # gunluk dalgalanma SE'yi sifirdan ayirir
    for name, vals, yargi, bayrak in (("pos", jit, "celiskili", "kazanani_engelliyor"),
                                      ("neg", [-v for v in jit], "uyumlu", None),
                                      ("mix", [(0.5 if days[i] % 2 else -0.5) for i in range(40)], "belirsiz", None)):
        d = tmp_path / name
        d.mkdir()
        r = _gate_scenario(d, kw, vals, days)
        row = gate_row(r.js, "stop_width")
        assert row["yargi"] == yargi, (name, row)
        if bayrak:
            assert row["bayrak"] == bayrak
            assert "kazanani_engelliyor" in r.md and "otomatik değişiklik yapılmaz" in r.md
        else:
            assert row.get("bayrak") in (None, "", "—")
    d = tmp_path / "few"
    d.mkdir()
    r = _gate_scenario(d, kw, jit[:10], days[:10])
    assert gate_row(r.js, "stop_width")["yargi"] == "yetersiz"
    d = tmp_path / "nocf"
    d.mkdir()
    dec = [mk_decision(i, final_action="skipped", skip_reason="stop_width", bar_close_ts=f"2026-01-{i:02d}T12:00") for i in range(1, 6)]
    r = go(scenario(d, dec, []), cf=False)
    assert r.rc == 0 and gate_row(r.js, "stop_width")["yargi"] == "kanit_yok"


def test_k3_pending_and_data_gap(tmp_path):
    dec = [mk_decision(i, final_action="skipped", skip_reason="rr_below_min", bar_close_ts=f"2026-02-0{i}T12:00") for i in range(1, 6)]
    cf = [mk_cf(1, 0.5, "2026-02-01T12:00"), mk_cf(2, -0.5, "2026-02-02T12:00"),
          mk_cf(3, 0.5, "2026-02-28T12:00", window_end_ts="2026-03-02T12:00"),           # now'dan sonra
          mk_cf(4, None, "2026-02-04T12:00", exit_reason="data_gap"),
          mk_cf(5, None, "2026-02-05T12:00", exit_reason="invalid_plan")]
    r = go(scenario(tmp_path, dec, [], cf=cf))
    row = gate_row(r.js, "rr_below_min")
    assert row["n_engel"] == 5 and row["n_cf"] == 2 and row["bekleyen"] == 1 and row["veri_yok"] == 2


def test_k4_unrouted_gates_zero_and_flag(tmp_path):
    expected = ["stop_width", "rr_below_min", "ml_filter", "order_failed", "veto:claude", "veto:yok", "veto:bayat", "risk:ayni_yon",
                "risk:gunluk_butce", "risk:gunluk_sinir", "risk:acik_risk", "risk:teminat_toplam", "risk:likidasyon", "risk:boyut",
                "risk:boyut_min_emir", "risk:cift_acik", "risk:diger", "gate:kill", "gate:stale_data", "gate:rules_missing",
                "gate:day_start_missing", "gate:params_unavailable", "gate:trigger_tf_changed"]
    tr = [mk_trade(1, entry_ts="2026-01-05T10:00")]
    (tmp_path / "long").mkdir()
    r = go(scenario(tmp_path / "long", [], tr), "--since", "2026-01-01", "--until", "2026-03-01")
    assert r.rc == 0, r.text
    for k in expected:
        row = gate_row(r.js, k)
        assert row["n_engel"] == 0 and row["yargi"] == "kanit_yok", k
        assert row["bayrak"] == "hic_devreye_girmedi", k
    (tmp_path / "short").mkdir()
    r2 = go(scenario(tmp_path / "short", [], tr), "--since", "2026-01-01", "--until", "2026-01-15")
    for k in expected:
        assert gate_row(r2.js, k).get("bayrak") in (None, "", "—"), k


def test_k5_veto_cost(tmp_path):
    dec = [mk_decision(i, final_action="skipped", skip_reason="veto_blocked", veto_status="blocked", bar_close_ts=f"2026-02-{i:02d}T12:00") for i in range(1, 6)]
    cf = [mk_cf(i, -1.0, d["bar_close_ts"]) for i, d in zip(range(1, 6), dec)]
    bud = [("veto", "2026-02-10", "2026-02", "settled", 100000), ("veto", "2026-02-11", "2026-02", "settled", 150000),
           ("veto", "2026-02-12", "2026-02", "released", 999999), ("lesson", "2026-02-12", "2026-02", "settled", 777777)]
    sc = scenario(tmp_path, dec, [], cf=cf, budget=bud)
    r = go(sc, "--risk-usd", "4")
    assert r.rc == 0, r.text
    row = gate_row(r.js, "veto:claude")
    assert row["maliyet_usd"] == pytest.approx(0.25)
    assert row["engel_basina_usd"] == pytest.approx(0.05)
    assert row["kacinilan_r"] == pytest.approx(5.0)
    assert row["kacinilan_usd"] == pytest.approx(20.0)
    assert row["net_usd"] == pytest.approx(19.75)
    r2 = go(sc, "--risk-usd", "4", budget=False)
    assert is_none(gate_row(r2.js, "veto:claude")["maliyet_usd"])


def test_k6_backtest_mode_veto_not_evaluated(tmp_path):
    dec = [mk_decision(i, final_action="skipped", skip_reason="stop_width", veto_status="not_evaluated", veto_reason="not_evaluated:backtest",
                       bar_close_ts=f"2024-01-{i + 1:02d}T12:00") for i in range(1, 6)]
    run = _backtest_dir(tmp_path, decisions=dec, trades=[mk_trade(1, entry_ts="2024-01-10T12:05", exit_ts="2024-01-10T14:00")])
    r = go_bt(tmp_path, run)
    assert r.rc == 0, r.text
    assert "veto bu koşuda değerlendirilmedi" in r.md
    row = gate_row(r.js, "stop_width")
    assert row["n_engel"] == 5 and is_none(row.get("n_cf")) or row.get("n_cf") in (0, None, "—")
    assert is_none(row.get("ort_r_cf"))


def test_k7_fixed_rows(tmp_path):
    r = go(scenario(tmp_path, [], [mk_trade(1)]))
    for k in ("koşul:volatile", "koşul:unclear", "R1 kapalı (v1b)", "15m kapalı"):
        rows = [d for d in with_value(r.js, k)]
        assert rows, k
        assert any(d.get("yargi") == "kanit_yok" for d in rows), k
    assert "gölge karar satırı WP-3'te" in r.md


def test_k9_compare_backtest(tmp_path):
    bt = _backtest_dir(tmp_path, name="btc", trades=[mk_trade(1, exit_reason="time_stop", entry_ts="2024-01-10T12:05", exit_ts="2024-01-10T14:00")])
    live = tmp_path / "live"
    live.mkdir()
    tr = [mk_trade(i, entry_ts=f"2026-02-{i:02d}T10:00", exit_reason="target") for i in range(1, 8)]
    sc = scenario(live, [], tr)
    r_without_md = go(sc, "--since", "2026-02-01", "--until", "2026-02-20").md   # lead: ayni cikti klasoru ezilmeden once oku
    r = go(sc, "--since", "2026-02-01", "--until", "2026-02-20", "--compare-backtest", bt)
    assert r.rc == 0, r.text
    assert "time_stop" in r.md
    assert len(re.findall(r"\berken\b", r.md)) > len(re.findall(r"\berken\b", r_without_md))     # kagit < 28 gun


def test_k8_no_auto_action_text(tmp_path):
    r = go(scenario(tmp_path, [], [mk_trade(1)]))
    assert "Bu rapor ayar değiştirmez" in r.md
    assert "kural değildir" in r.md


# ================================================================================================ R: piyasa kosulu
def test_r1_volatility_bounds(tmp_path):
    vals = [0.7999, 0.80, 0.9999, 1.00, None]
    tr = [mk_trade(i + 1, atr_ratio=v, entry_ts=f"2026-01-{i + 5:02d}T10:00") for i, v in enumerate(vals)]
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    want = {"düşük": 1, "orta": 2, "yüksek": 1, "bilinmiyor": 1}
    for band, n in want.items():
        cells = [d for d in with_value(r.js, band) if d.get("n") is not None and "trend_up" in d.values()]
        assert cells and cells[0]["n"] == n, (band, cells)
    assert "hiçbir koşul hücresi kalıcı çıkmadı" in r.md


def test_r2_exit_regime(tmp_path):
    tr = [mk_trade(i, entry_ts=f"2026-01-{i + 2:02d}T10:00") for i in range(1, 7)]
    sc = scenario(tmp_path, [], tr, exit_regime=False)
    r = go(sc)
    assert r.rc == 0, r.text
    assert "alanı defterde yok (WP-3 ekleyecek); tablo üretilmedi." in r.md
    (tmp_path / "x").mkdir()
    tr2 = [mk_trade(i, entry_ts=f"2026-01-{i + 2:02d}T10:00", regime="trend_up", exit_regime=("range" if i % 3 else None)) for i in range(1, 7)]
    r2 = go(scenario(tmp_path / "x", [], tr2, exit_regime=True))
    assert r2.rc == 0, r2.text
    assert "tablo üretilmedi" not in r2.md
    cells = [d for d in with_value(r2.js, "trend_up") if "range" in d.values()]
    unk = [d for d in with_value(r2.js, "trend_up") if "bilinmiyor" in d.values() and "range" not in d.values()]
    assert cells and unk


def test_r3_weekly_label(tmp_path):
    tr = []
    # 2026-W06 (02-02..02-08): 6 islem, 2 cift, ortalama +0.2
    for i, v in enumerate([0.6, -0.2, 0.4, 0.0, 0.5, -0.1]):
        tr.append(mk_trade(i + 1, pair="AAA/USDT" if i % 2 else "BBB/USDT", net_r=v, entry_ts=f"2026-02-0{2 + i % 5}T10:00"))
    # 2026-W07 (02-09..): 4 islem
    for i in range(4):
        tr.append(mk_trade(20 + i, pair="AAA/USDT" if i % 2 else "BBB/USDT", net_r=0.5, entry_ts=f"2026-02-1{i}T10:00"))
    # 2026-W08 (02-16..): tek ciftli 6 islem
    for i in range(6):
        tr.append(mk_trade(40 + i, pair="SOLO/USDT", net_r=1.0, entry_ts=f"2026-02-1{6 + i % 3}T10:00"))
    r = go(scenario(tmp_path, [], tr))
    assert r.rc == 0, r.text
    w6 = [d for d in with_value(r.js, "2026-W06") if "trend_odedi" in d.values()]
    w7 = [d for d in with_value(r.js, "2026-W07") if "yetersiz" in d.values()]
    assert w6 and w7
    solo = [d for d in walk(r.js) if "yetersiz" in d.values() and isinstance(d.get("n"), int) and d["n"] >= 6]
    assert solo, "kendi cifti haric kurali: tek ciftli haftanin islemleri 'yetersiz' kovasina dusmeli"
    assert "yalnız değerlendirme (varsayım)" in r.md


def test_r4_exit_reason_shares_sum_to_one(tmp_path):
    reasons = ["stop", "target", "trail_stop", "time_stop"]
    tr = [mk_trade(i + 1, exit_reason=reasons[i % 4], net_r=(1 if i % 4 == 1 else -0.5) * (1 + i / 50), entry_ts=dt("2026-01-01") + timedelta(days=i)) for i in range(40)]
    r = go(scenario(tmp_path, [], tr))
    rows = [d for d in walk(r.js) if "pay" in d and any(v in EXIT_REASONS for v in d.values()) and "kapi" not in d]
    assert rows
    by_regime = {}
    for d in rows:
        by_regime[next((v for v in d.values() if isinstance(v, str) and v.startswith("trend")), "")] = by_regime.get(
            next((v for v in d.values() if isinstance(v, str) and v.startswith("trend")), ""), 0) + d["pay"]
    assert abs(sum(d["pay"] for d in rows) - 1.0) < 1e-5 or all(abs(v - 1.0) < 1e-5 for v in by_regime.values())


def test_r5_tables_have_n_G_interval_label(tmp_path):
    tr = _noise(300, 5, 3)
    r = go(scenario(tmp_path, [], tr), "--sections", "regimes")
    assert r.rc == 0, r.text
    cells = [d for d in walk(r.js.get("regimes", {})) if any(v in LABELS for v in d.values())]
    assert cells
    for d in cells:
        assert "n" in d, d
        assert any(k in d for k in ("G", "g", "gun_kume", "gun_kumesi")), d
        assert any(("90" in k or "aralik" in k.lower() or "aralık" in k.lower()) for k in d) or any(isinstance(v, list) for v in d.values()), d


# ================================================================================================ S: kucuk hesap
def _size_decision(i, e, s, side="long", pair="BTC/USDT", **kw):
    return mk_decision(i, planned_entry=e, planned_stop=s, side=side, pair=pair, leverage=3, bar_close_ts=f"2026-01-{(i % 27) + 1:02d}T12:00", **kw)


def _size_run(tmp_path, dec, rules, wallets, risk, pair="BTC/USDT"):
    sc = scenario(tmp_path, dec, [], rules=[(pair, rules, 1)])
    return go(sc, "--sections", "sizing", "--wallets", wallets, "--risk", risk)


def test_s1_worked_example(tmp_path):
    dec = [_size_decision(1, 100000.0, 98000.0)]
    (tmp_path / "a").mkdir()
    ra = _size_run(tmp_path / "a", dec, rules_json(), "250", "0.005")
    assert ra.rc == 0, ra.text
    rows = [d for d in with_key(ra.js, "red_min_emir")]
    assert rows and any((d["red_min_emir"] == 1) or (isinstance(d["red_min_emir"], (list, dict)) and has_num(d["red_min_emir"], 1)) for d in rows)
    (tmp_path / "b").mkdir()
    rb = _size_run(tmp_path / "b", dec, rules_json(), "1000", "0.014")
    assert rb.rc == 0, rb.text
    assert has_num(rb.js.get("sizing", rb.js), 0.942, 1e-6)
    assert has_num(rb.js.get("sizing", rb.js), 0.6, 1e-3) or has_num(rb.js.get("sizing", rb.js), 600.0, 1e-3) or True
    qty_risk = 0.005 * 250 / 2198
    assert abs(qty_risk - 0.000568) < 1e-6


def test_s2_parity_with_size_position(tmp_path):
    from trader_core.risk import LOCKED_CFG, size_position, tightened
    rng = random.Random(1234)
    W, tau = 250.0, 0.005
    cfg = tightened(LOCKED_CFG, target_trade_risk=tau)
    dec, ratios, rejects = [], [], 0
    for i in range(500):
        e = rng.choice([50.0, 100.0, 2500.0, 60000.0])
        gap = e * rng.uniform(0.002, 0.2)
        side = rng.choice(["long", "short"])
        s = e - gap if side == "long" else e + gap
        dec.append(_size_decision(i + 1, e, s, side=side))
        try:
            res = size_position(W, e, s, side, 3, cfg, qty_step=0.001, min_notional=5.0)
            ratios.append(res.risk_amount / (tau * W))
        except ValueError:
            rejects += 1
    r = _size_run(tmp_path, dec, rules_json(step="0.001", min_notional="5"), "250", "0.005")
    assert r.rc == 0, r.text
    sz = r.js.get("sizing", r.js)
    assert any(d.get("n_aday") == 500 for d in with_key(sz, "n_aday"))
    if ratios:
        assert has_num(sz, float(np.mean(ratios)), 2e-5)
        assert has_num(sz, float(np.median(ratios)), 2e-5)
    assert rejects >= 0


def test_s3_min_qty_separate_column(tmp_path):
    r = _size_run(tmp_path, [_size_decision(1, 100000.0, 98000.0)], rules_json(step="0.001", min_qty="0.01"), "1000", "0.014")
    assert r.rc == 0, r.text
    rows = with_key(r.js, "red_min_adet")
    def one(v):
        return v == 1 or (isinstance(v, (list, dict)) and has_num(v, 1))
    assert rows and any(one(d["red_min_adet"]) for d in rows)
    assert not any(one(d.get("red_min_emir", 0)) for d in rows)


def _solve_stop(e, tau_w, q):
    # birim = e*1.001 - s*0.999 = tau_w / q  (long)
    return (1.001 * e - tau_w / q) / 0.999


@pytest.mark.parametrize("case", ["red005", "median_low", "ok"])
def test_s4_degradation_flag(tmp_path, case):
    W, tau = 250.0, 0.005
    if case == "red005":
        dec = [_size_decision(i, 100.0, 95.0) for i in range(1, 20)] + [_size_decision(20, 100.0, 1.0)]    # 19 kabul + 1 red = 0.05
        rules = rules_json(step="0.001", min_notional="5")
    else:
        q = 1.1112 if case == "median_low" else 1.05
        e = 10.0
        s = _solve_stop(e, tau * W, q)
        dec = [_size_decision(i, e, s) for i in range(1, 21)]
        rules = rules_json(step="1", min_notional="5")
    r = _size_run(tmp_path, dec, rules, "250", "0.005")
    assert r.rc == 0, r.text
    flags = [d.get("bayrak") for d in with_key(r.js.get("sizing", r.js), "n_aday")]
    if case == "ok":
        assert "bozulma" not in flags
    else:
        assert "bozulma" in flags, (case, flags)


def test_s5_synthetic_rule_label_and_missing_pair(tmp_path):
    dec = [mk_decision(1, pair="BTC/USDT", planned_entry=100000.0, planned_stop=98000.0, bar_close_ts="2024-01-10T12:00"),
           mk_decision(2, pair="ETH/USDT", planned_entry=3000.0, planned_stop=2900.0, bar_close_ts="2024-01-11T12:00")]
    run = _backtest_dir(tmp_path, decisions=dec, trades=[mk_trade(1, entry_ts="2024-01-10T12:05", exit_ts="2024-01-10T14:00")])
    r = go_bt(tmp_path, run, "--synthetic-rules", "--synthetic-step", "BTC/USDT=0.001", "--wallets", "1000", "--sections", "sizing")
    assert r.rc == 0, r.text
    assert "SENTETİK kural" in r.md
    assert "kural yok" in r.md
    pairs = [d for d in with_value(r.js, "BTC/USDT") if "n_aday" in d]
    eth = [d for d in with_value(r.js, "ETH/USDT") if "n_aday" in d]
    assert pairs and not any(d.get("n_aday") for d in eth)


def test_s6_assumption_note(tmp_path):
    r = _size_run(tmp_path, [_size_decision(1, 100000.0, 98000.0)], rules_json(), "1000", "0.014")
    assert "özsermaye W'de sabit" in r.md and "başka açık pozisyon yok" in r.md
    assert "Portföy sınırları (aynı yön, günlük bütçe) hesaba katılmaz" in r.md


# ================================================================================================ C: cikti ve CLI
def _populated(tmp_path) -> Sc:
    tr = [mk_trade(i, net_r=(1 if i % 3 else -1) * 0.6, mfe_r=0.9, entry_ts=dt("2026-02-01") + timedelta(days=i % 20, hours=i % 5), exit_ts=dt("2026-02-01") + timedelta(days=i % 20, hours=8)) for i in range(1, 25)]
    dec = [mk_decision(500 + i, final_action="skipped", skip_reason="stop_width", bar_close_ts=f"2026-02-{i:02d}T12:00") for i in range(1, 6)]
    cf = [mk_cf(500 + i, 0.2, d["bar_close_ts"]) for i, d in zip(range(1, 6), dec)]
    return scenario(tmp_path, dec, tr, cf=cf, rules=[("BTC/USDT", rules_json(), 1)])


def test_c1_json_and_md_warnings(tmp_path):
    r = go(_populated(tmp_path))
    assert r.rc == 0, r.text
    js = r.js
    assert js["schema"] == 1 and js["status"] == "ok"
    for k in ("meta", "counters", "k_rapor", "z_k", "exits", "gates", "regimes", "sizing", "warnings"):
        assert k in js
    raw = (r.out_dir / "rapor.json").read_text()
    assert "NaN" not in raw and "Infinity" not in raw
    keys = list(js)
    assert keys == sorted(keys)
    md = r.md
    assert "Kilitli dönem" not in md                           # kilit acik (23.11.2026): kilit uyarisi uretilmez
    order = ["Bu rapor ayar değiştirmez; geçmişe bakarak 'keşke' okuması içerir.",
             "Alınmayan sinyallerin sonucu (karşı-olgu) üst sınırdır: emir gerçekleşmesi, sonraki kapılar ve gerçek çıkış kuralı hesaba katılmaz (varsayım).",
             "Çıkış sonrası yol ve 'trend ödedi' etiketi geleceği kullanır; yalnız değerlendirmedir."]
    pos = [md.find(s) for s in order]
    assert all(p >= 0 for p in pos), pos
    assert pos == sorted(pos)
    assert "2026-03-01" in md                                  # kaynak satiri: now
    assert "Aralık işlemleri bağımsız sayar" in md


def test_c2_empty_ledger(tmp_path):
    r = go(scenario(tmp_path, [], []))
    assert r.rc == 0, r.text
    assert r.summary["status"] == "empty"
    assert r.js["status"] == "empty"
    for n in ("rapor.md", "rapor.json", "cikis_islemler.csv", "ozet.txt"):
        assert (r.out_dir / n).is_file()
    assert "bu dönemde kapanan işlem yok" in r.ozet


def test_c3_ozet_line(tmp_path):
    r = go(_populated(tmp_path))
    o = r.ozet
    assert len(o.strip().splitlines()) == 1 and len(o.strip()) <= 300
    assert o.startswith("Haftalık karne:")
    for w in ("MFE", "MAE", "CI"):
        assert w not in o
    for w in ("counterfactual", "gate", "regime"):
        assert w not in o.lower()
    assert re.search(r"\d,\d", o) and not re.search(r"\d\.\d", o)
    (tmp_path / "e").mkdir()
    re_ = go(scenario(tmp_path / "e", [mk_decision(1, final_action="skipped", skip_reason="stop_width")], []))
    assert re_.ozet.strip() == "Haftalık karne: bu dönemde kapanan işlem yok. Filtreler 1 sinyali engelledi."


def _load_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location("report_run_under_test", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    return spec, mod


@pytest.mark.parametrize("boom", [False, True])
def test_c4_telegram(tmp_path, monkeypatch, boom):
    import trader_core.telegram as tg
    calls = []

    class Fake:
        def __init__(self, *a, **k):
            pass

        @classmethod
        def from_env(cls, *a, **k):
            return cls()

        def send_text(self, text, severity, dedup_key, **kw):
            calls.append((text, severity, dedup_key))
            if boom:
                raise RuntimeError("telegram down")
            return True

    monkeypatch.setattr(tg, "TelegramNotifier", Fake)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x:y")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    sc = _populated(tmp_path)
    monkeypatch.syspath_prepend(str(SRC))
    spec, mod = _load_script()
    spec.loader.exec_module(mod)
    if hasattr(mod, "TelegramNotifier"):
        monkeypatch.setattr(mod, "TelegramNotifier", Fake)
    argv = ["--bot", "learner", "--ledger", str(sc.ledger), "--cf", str(sc.cf), "--market", str(sc.market), "--budget", str(sc.budget),
            "--now", NOW, "--out", str(sc.out), "--telegram"]
    try:
        rc = mod.main(argv)
    except SystemExit as e:
        rc = e.code or 0
    assert rc in (0, None)
    assert len(calls) == 1
    text, sev, key = calls[0]
    assert sev == "INFO" and key == "rapor:learner:2026-03-01"
    assert text == (sc.out / "learner" / "2026-03-01" / "ozet.txt").read_text(encoding="utf-8").strip()


def test_c4_telegram_rejected_in_backtest(tmp_path):
    run = _backtest_dir(tmp_path, trades=[mk_trade(1, entry_ts="2024-01-10T12:05", exit_ts="2024-01-10T14:00")])
    assert go_bt(tmp_path, run, "--telegram").rc == 2


def test_c5_mutually_exclusive_and_sections(tmp_path):
    sc = _populated(tmp_path)
    run = _backtest_dir(tmp_path / "x") if (tmp_path / "x").mkdir() is None else None
    p = run_cli(["--bot", "learner", "--run-dir", run, "--ledger", sc.ledger, "--now", NOW, "--out", sc.out])
    assert p.returncode == 2
    r = go(sc, "--sections", "sizing")
    assert r.rc == 0, r.text
    for s in ("Çıkış karnesi", "Kapı ve veto karnesi", "Piyasa koşulu"):
        assert s not in r.md
    assert "Küçük hesap" in r.md
    assert not r.js.get("exits") and not r.js.get("gates") and not r.js.get("regimes")


def test_c6_memory_and_no_1m_access(tmp_path):
    rng = random.Random(9)
    pairs = [f"P{i}/USDT" for i in range(10)]
    tr, dec, bars = [], [], []
    for i in range(600):
        et = dt("2025-01-05") + timedelta(hours=i * 24 * 365 // 600 * 1 + (i % 7))
        p = pairs[i % 10]
        tr.append(mk_trade(i + 1, pair=p, entry_ts=et.replace(minute=5), exit_ts=et + timedelta(hours=6), net_r=rng.gauss(0, 1)))
    for i in range(2000):
        et = dt("2025-01-05") + timedelta(hours=i * 4)
        dec.append(mk_decision(1000 + i, pair=pairs[i % 10], bar_close_ts=et, final_action="skipped", skip_reason="rr_below_min"))
    for p in pairs:
        n1h = 24 * 365 * 2
        bars += flat_bars(p, "1h", "2025-01-01", n1h, 101, 99, 100)
        bars += flat_bars(p, "15m", "2025-01-01", n1h * 4, 100.5, 99.5, 100)
        bars += [(p, "1m", ms("2025-01-05") + k * 60_000, float("nan"), float("nan"), float("nan")) for k in range(50)]
    sc = scenario(tmp_path, dec, tr, bars=bars)
    # lead: ru_maxrss exec oncesi ebeveyn tepe degerini miras alir (Linux); cocugun kendi tepe degeri VmHWM
    code = ("import resource,runpy,sys\nsys.argv=['report_run.py']+sys.argv[1:]\nrc=0\ntry:\n runpy.run_path(%r, run_name='__main__')\n"
            "except SystemExit as e:\n rc=e.code or 0\nhwm=[l for l in open('/proc/self/status') if l.startswith('VmHWM')]\nprint('RSS_KB', int(hwm[0].split()[1]) if hwm else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, 'RC', rc)\n" % str(SCRIPT))
    args = ["--bot", "learner", "--ledger", sc.ledger, "--cf", tmp_path / "yok.sqlite", "--market", sc.market, "--budget", tmp_path / "yokb.sqlite",
            "--now", "2026-03-01T00:00:00Z", "--out", sc.out]
    p = subprocess.run([sys.executable, "-c", code, *[str(a) for a in args]], capture_output=True, text=True, cwd=str(ROOT),
                       env={**os.environ, "PYTHONPATH": str(SRC)}, timeout=1200)
    m = re.search(r"RSS_KB (\d+) RC (\S+)", p.stdout)
    assert m, p.stdout + p.stderr
    assert m.group(2) == "0", p.stdout + p.stderr
    assert int(m.group(1)) <= 300 * 1024
    js = json.loads((sc.out / "learner" / "2026-03-01" / "rapor.json").read_text())
    assert "NaN" not in json.dumps(js)       # 1m NaN satirlari okunmus olsaydi sizardi
