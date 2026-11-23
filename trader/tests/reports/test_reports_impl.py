"""Rapor paketi (WP-4) uygulama testleri: istatistik, hesaplar, kilitli donem, salt okunurluk, CLI."""
from __future__ import annotations

import ast
import hashlib
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from trader_core.risk import LOCKED_CFG, size_position  # noqa: E402
from trader_reports import exits as EX, gates as GA, inputs as I, sizing as SZ, stats as ST  # noqa: E402
import report_run  # noqa: E402

PKG = ROOT / "src" / "trader_reports"
NOW = "2026-11-17T00:00:00Z"


# --------------------------------------------------------------------------- yardimcilar
def make_ledger(path, version=3, decisions=(), trades=()):
    c = sqlite3.connect(str(path))
    ml = ", ml_score REAL" if version >= 3 else ""
    c.executescript(f"""
    CREATE TABLE decision_events (id INTEGER PRIMARY KEY, bot TEXT, bar_close_ts TEXT, trigger_tf TEXT, pair TEXT, side TEXT,
      setup TEXT, regime TEXT, atr_ratio REAL, features TEXT, planned_entry REAL, planned_stop REAL, planned_target REAL,
      veto_status TEXT, veto_reason TEXT, risk_reason TEXT, leverage INTEGER, final_action TEXT, skip_reason TEXT,
      supersedes_id INTEGER{ml});
    CREATE TABLE trade_entries (id INTEGER PRIMARY KEY, trade_id INTEGER, decision_id INTEGER, pair TEXT, side TEXT, setup TEXT,
      entry_ts TEXT, entry_price REAL, planned_entry REAL, planned_stop REAL, planned_target REAL, qty REAL, leverage INTEGER,
      planned_risk REAL);
    CREATE TABLE trade_exits (id INTEGER PRIMARY KEY, trade_id INTEGER, exit_ts TEXT, exit_price REAL, exit_reason TEXT,
      gross_pnl REAL, realized_pnl REAL, r_multiple REAL, mfe_r REAL, mae_r REAL, bars_held INTEGER, excursion_tf TEXT);
    CREATE VIEW v_decisions AS SELECT * FROM decision_events;
    CREATE VIEW v_closed_trades AS SELECT e.trade_id, e.decision_id, e.pair, e.side, e.setup, d.regime, d.atr_ratio, e.entry_ts,
      e.entry_price, e.planned_entry, e.planned_stop, e.planned_target, e.qty, e.leverage, e.planned_risk, x.id AS exit_id,
      x.exit_ts, x.exit_price, x.exit_reason, x.gross_pnl, x.realized_pnl, x.r_multiple, x.mfe_r, x.mae_r, x.bars_held,
      x.excursion_tf FROM trade_entries e JOIN decision_events d ON d.id = e.decision_id JOIN trade_exits x ON x.trade_id = e.trade_id;
    """)
    for i, d in enumerate(decisions, 1):
        c.execute("INSERT INTO decision_events (id, bar_close_ts, trigger_tf, pair, side, setup, regime, atr_ratio, features, "
                  "planned_entry, planned_stop, veto_status, veto_reason, risk_reason, leverage, final_action, skip_reason) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (i, d["ts"], "1h", d.get("pair", "BTC/USDT"), d.get("side", "long"), "T1", d.get("regime", "trend_up"),
                   d.get("atr_ratio", 1.0), '{"atr_tf": 2.0}', 100.0, 98.0, "allowed", d.get("veto_reason"), d.get("risk_reason"),
                   3, d.get("final_action", "skipped"), d.get("skip_reason", "stop_width")))
    for i, t in enumerate(trades, 1):
        c.execute("INSERT INTO decision_events (id, bar_close_ts, trigger_tf, pair, side, setup, regime, features, planned_entry, "
                  "planned_stop, veto_status, final_action) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (1000 + i, t["entry"], "1h", "BTC/USDT", "long", "T1", "trend_up", "{}", 100.0, 98.0, "allowed", "entered"))
        c.execute("INSERT INTO trade_entries (trade_id, decision_id, pair, side, setup, entry_ts, entry_price, planned_entry, "
                  "planned_stop, qty, leverage, planned_risk) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (i, 1000 + i, "BTC/USDT", "long", "T1", t["entry"], 100.0, 100.0, 98.0, 1.0, 3, 2.0))
        c.execute("INSERT INTO trade_exits (trade_id, exit_ts, exit_price, exit_reason, gross_pnl, realized_pnl, r_multiple, mfe_r, "
                  "mae_r, bars_held, excursion_tf) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (i, t["exit"], 101.0, t.get("reason", "stop"), 1.0, 0.9, t.get("r", 0.45), 1.0, 0.2, 3, "15m"))
    c.execute(f"PRAGMA user_version={version}")
    c.commit()
    c.close()


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_cli(args, capsys):
    rc = report_run.main(args)
    out = capsys.readouterr().out.strip().splitlines()
    return rc, (json.loads(out[-1]) if out else {})


# --------------------------------------------------------------------------- istatistik
def test_cluster_mean_hand_calc():
    r = ST.cluster_mean([1, -1, 2, 0], ["a", "a", "b", "c"])
    assert r["m"] == 0.5 and r["lo"] is None
    assert r["se"] == pytest.approx((1.5 * (0.0625 + 0.140625 + 0.015625)) ** 0.5)
    r2 = ST.cluster_mean([1, -1, 2, 0] * 8, [f"{k}{i}" for i in range(8) for k in "abc"] [:0] or [f"{g}{i}" for i in range(8) for g in "abcd"])
    assert r2["G"] == 32


def test_wilson_and_zk():
    w = ST.wilson(50, 100)
    assert w["lo"] == pytest.approx(0.4188, abs=1e-4) and w["hi"] == pytest.approx(0.5812, abs=1e-4)
    assert ST.wilson(0, 0)["p"] is None
    for k, z in ((1, 1.960), (10, 2.807), (20, 3.023), (50, 3.291)):
        assert ST.z_k(k) == pytest.approx(z, abs=1e-3)


def test_subtable_labels():
    rnd = random.Random(1)
    cells = []
    for c in range(20):
        its = [(rnd.gauss(0, 1), f"2025-01-{(i % 28) + 1:02d}", f"2025-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T{i % 24:02d}") for i in range(100)]
        cells.append((f"c{c}", its, {}))
    t = ST.SubTable("x", "x", "r", cells)
    d = t.finalize(ST.z_k(20), 20)
    assert all(r["etiket"] != "çıtayı geçti" for r in d["rows"])
    small = ST.SubTable("y", "y", "r", [("a", cells[0][1][:29], {}), ("b", cells[1][1], {})]).finalize(2.0, 2)
    assert small["rows"][0]["etiket"] == "yetersiz" and small["rows"][0]["aralik"] is None


def test_subtable_embedded_effect_both_halves():
    rnd = random.Random(2)
    def items(shift, n):
        return [(rnd.gauss(shift, 1), f"d{i % 40}", f"2025-{(i * 12) // n + 1:02d}-{(i % 27) + 1:02d}") for i in range(n)]
    t = ST.SubTable("z", "z", "r", [("a", items(1.5, 200), {}), ("b", items(0, 200), {})]).finalize(ST.z_k(2), 2)
    assert t["rows"][0]["etiket"] == "çıtayı geçti"


def test_year_rows():
    its = [(1.0, f"d{i}", f"2024-03-{i % 28 + 1:02d}") for i in range(40)] + [(-1.0, f"e{i}", f"2025-03-{i % 28 + 1:02d}") for i in range(40)]
    r = ST.year_rows(its)
    assert r["pozitif_yil_orani"] == 0.5 and "not" not in r


# --------------------------------------------------------------------------- cikis
class FakeReader(I.BarReader):
    def __init__(self, bars):
        self.bars = bars

    def _read(self, pair, tf, start_ms, n):
        return self.bars[:n]


def _bars(start, specs, n=72):
    rows = [(start + k * 3_600_000, h, l, c) for k, (h, l, c) in enumerate(specs)]
    while len(rows) < n:
        rows.append((start + len(rows) * 3_600_000, 98.0, 98.0, 98.0))
    return rows


def test_post_path_long_example():
    t = {"pair": "BTC/USDT", "side": "long", "exit_ts": "2025-01-01T12:00:00.000Z", "exit_price": 100.0, "r_px": 2.0}
    start = I.iso_ms(t["exit_ts"])
    rd = FakeReader(_bars(start, [(101, 99, 100), (103, 100, 102), (102, 97, 98)]))
    r = EX.post_path(t, rd, I.iso_ms("2025-02-01T00:00:00.000Z"), 24)
    assert (r["fav"], r["adv"], r["close"], r["touch"], r["erken"]) == (1.5, 1.5, -1.0, "lehte", 1)
    both = FakeReader(_bars(start, [(102, 98, 100)]))
    assert EX.post_path(t, both, I.iso_ms("2025-02-01T00:00:00.000Z"), 24)["touch"] == "aleyhte"
    assert EX.post_path(t, rd, start + 3600_000, 24)["durum"] == "pending"
    gap = FakeReader(_bars(start, [(101, 99, 100)])[:10])
    assert EX.post_path(t, gap, I.iso_ms("2025-02-01T00:00:00.000Z"), 24)["durum"] == "data_gap"


def test_post_path_ceil_hour():
    assert I.ceil_hour(I.iso_ms("2025-01-01T12:20:00.000Z")) == I.iso_ms("2025-01-01T13:00:00.000Z")
    assert I.ceil_hour(I.iso_ms("2025-01-01T12:00:00.000Z")) == I.iso_ms("2025-01-01T12:00:00.000Z")


def test_pre1r():
    rows = [(0, 100.5, 99.0, 100), (1, 101, 98.5, 100), (2, 103, 99.9, 102)]
    adv, reached = EX.pre1r(rows, 1, 100.0, 2.0)
    assert reached and adv == pytest.approx(0.75)
    adv, reached = EX.pre1r(rows[:2], 1, 100.0, 2.0)
    assert not reached and adv == pytest.approx(0.75)


def test_reason_line_example():
    t = {"pair": "BTC/USDT", "side": "long", "exit_reason": "trail_stop", "mfe_r": 1.8, "net_r": 0.9, "gross_r": 0.95}
    assert EX.reason_line(t) == "BTC/USDT alış: en çok +1,8R gördü, iz süren stop ile +0,9R kapandı; tepeden 0,9R geri verdi."
    t["mfe_r"] = None
    assert EX.reason_line(t) == "BTC/USDT alış: iz süren stop ile +0,9R kapandı."


# --------------------------------------------------------------------------- kapilar
def test_risk_class_and_keys():
    assert GA.risk_class("aynı yön (long) risk sınırı aşılır") == "ayni_yon"
    assert GA.risk_class("boyutlandırma reddedildi: miktar sıfır veya en küçük emir değerinin altında") == "boyut_min_emir"
    assert GA.risk_class("boyutlandırma reddedildi: x") == "boyut"
    assert GA.risk_class("BTC/USDT için zaten açık pozisyon var") == "cift_acik"
    assert GA.risk_class("bilinmeyen") == "diger"
    d = {"final_action": "skipped", "skip_reason": "entry_gate_closed", "veto_reason": "gate:kill"}
    assert GA.gate_key(d) == "gate:kill"
    assert GA.gate_key({"final_action": "skipped", "skip_reason": "veto_blocked"}) == "veto:claude"


def _cf(vals):
    return {i + 1: {"barrier": {"hyp_r_net": v, "hyp_outcome": 1 if v > 0 else 0, "decision_ts": f"2025-01-{i % 10 + 1:02d}T00:00:00.000Z",
                                "exit_reason": "target"}, "plan": None} for i, v in enumerate(vals)}


def test_yargi():
    ids = list(range(1, 41))
    assert GA._stats(ids, 40, _cf([0.5] * 40), 40, 30)[0]["yargi"] == "celiskili"
    assert GA._stats(ids, 40, _cf([-0.5] * 40), 40, 30)[0]["yargi"] == "uyumlu"
    assert GA._stats(ids[:10], 10, _cf([0.5] * 10), 10, 30)[0]["yargi"] == "yetersiz"
    assert GA._stats(ids, 40, None, 40, 30)[0]["yargi"] == "kanit_yok"
    row = GA._stats([], 0, _cf([]), 40, 30)[0]
    assert row["bayrak"] == "hic_devreye_girmedi"
    assert GA._stats([], 0, _cf([]), 40, 10)[0]["bayrak"] == ""


# --------------------------------------------------------------------------- boyut
def test_sizing_example():
    r = I.Rules(0.001, 0.001, 100.0, "t")
    a = SZ.size_one(100000, 98000, 250, 0.005, 3, r)
    assert a["birim"] == pytest.approx(2198) and a["sonuc"] == "red_min_emir"
    b = SZ.size_one(100000, 98000, 1000, 0.014, 3, r)
    assert b["sonuc"] == "kabul" and b["qty"] == pytest.approx(0.006) and b["risk"] == pytest.approx(13.188)
    assert b["risk_orani"] == pytest.approx(0.942)


def test_sizing_parity():
    rnd = random.Random(7)
    from trader_core.risk import tightened
    for _ in range(500):
        e = rnd.uniform(1, 5000)
        s = e * rnd.uniform(0.93, 0.995)
        W, tau, lev = rnd.choice((250, 300, 1000)), rnd.choice((0.005, 0.014)), rnd.choice((3, 4, 5))
        step = rnd.choice((0.001, 0.01, 0.1, 1.0))
        r = I.Rules(step, step, 5.0, "t")
        mine = SZ.size_one(e, s, W, tau, lev, r)
        cfg = tightened(LOCKED_CFG, target_trade_risk=tau)
        try:
            ref = size_position(W, e, s, "long", lev, cfg, qty_step=step, min_notional=5.0)
        except ValueError:
            assert mine["sonuc"] in ("red_min_emir", "red_teminat")
            continue
        assert mine["sonuc"] in ("kabul", "red_min_adet")
        assert mine["qty"] == pytest.approx(ref.qty, rel=1e-12) and mine["risk"] == pytest.approx(ref.risk_amount, rel=1e-12)


def test_sizing_bozulma_flag():
    mk = lambda ro, sonuc="kabul": {"sonuc": sonuc, "risk_orani": ro, "adim_kaybi": 0.0, "tavan_bagli": False}
    assert SZ._agg([mk(1.0)] * 19 + [mk(1.0, "red_min_emir")], ["d"] * 20)["bayrak"] == "bozulma"
    assert SZ._agg([mk(0.8999)] * 20, ["d"] * 20)["bayrak"] == "bozulma"
    assert SZ._agg([mk(0.90)] * 20, ["d"] * 20)["bayrak"] == ""


# --------------------------------------------------------------------------- CLI / kilit / salt okunur
def _trade_set():
    return [{"entry": "2026-04-20T00:00:00.000Z", "exit": "2026-04-27T23:59:00.000Z"},   # okunur
            {"entry": "2026-04-20T00:00:00.000Z", "exit": "2026-04-28T00:00:00.000Z"},   # atlanir
            {"entry": "2026-10-31T23:59:00.000Z", "exit": "2026-11-02T00:00:00.000Z"},   # atlanir
            {"entry": "2026-11-01T00:00:00.000Z", "exit": "2026-11-02T00:00:00.000Z"}]   # okunur


@pytest.mark.parametrize("ver", [2, 3])
@pytest.mark.usefixtures("kilitli_donem")
def test_cli_holdout_rows_and_readonly(tmp_path, capsys, ver):
    led = tmp_path / "ledger.sqlite"
    make_ledger(led, ver, trades=_trade_set())
    before = sha(led)
    out = tmp_path / "out"
    rc, j = run_cli(["--bot", "learner", "--ledger", str(led), "--cf", str(tmp_path / "nocf.sqlite"), "--market",
                     str(tmp_path / "nomarket.sqlite"), "--budget", str(tmp_path / "nob.sqlite"), "--now", NOW, "--out", str(out)], capsys)
    assert rc == 0 and j["n_trades"] == 2
    assert j["holdout_skipped"] >= 2
    assert sha(led) == before
    assert not (tmp_path / "nocf.sqlite").exists() and not (tmp_path / "nomarket.sqlite").exists()
    d = Path(j["out_dir"])
    assert {p.name for p in d.iterdir()} == {"rapor.md", "rapor.json", "cikis_islemler.csv", "ozet.txt"}
    md = (d / "rapor.md").read_text(encoding="utf-8")
    assert "Kilitli dönem 2026-05-01..2026-11-01 okunmadı; atlanan satır:" in md
    rj = json.loads((d / "rapor.json").read_text(encoding="utf-8"))
    assert rj["schema"] == 1 and rj["counters"]["holdout_skipped_trades"] == 2
    ozet = (d / "ozet.txt").read_text(encoding="utf-8")
    assert len(ozet.strip().splitlines()) == 1 and len(ozet.strip()) <= 300
    for w in ("MFE", "MAE", "CI", "counterfactual", "gate", "regime"):
        assert w not in ozet
    # determinizm
    first = {p.name: p.read_bytes() for p in d.iterdir()}
    rc, j2 = run_cli(["--bot", "learner", "--ledger", str(led), "--cf", str(tmp_path / "nocf.sqlite"), "--market",
                      str(tmp_path / "nomarket.sqlite"), "--now", NOW, "--out", str(out)], capsys)
    assert {p.name: p.read_bytes() for p in d.iterdir()} == first


def test_cli_errors_and_empty(tmp_path, capsys):
    rc, j = run_cli(["--bot", "learner", "--ledger", str(tmp_path / "yok.sqlite"), "--now", NOW, "--out", str(tmp_path / "o")], capsys)
    assert rc == 2 and j["code"] == "ledger_missing" and not (tmp_path / "yok.sqlite").exists()
    for v in (1, 8):   # sema 7 (DD-12 WP-06a) artik kabul; reddedilen ilk yeni surum 7
        led = tmp_path / f"l{v}.sqlite"
        make_ledger(led, v)
        rc, j = run_cli(["--bot", "learner", "--ledger", str(led), "--now", NOW, "--out", str(tmp_path / "o")], capsys)
        assert rc == 2 and j["code"] == "ledger_schema"
    led = tmp_path / "e.sqlite"
    make_ledger(led, 3)
    rc, j = run_cli(["--bot", "learner", "--ledger", str(led), "--cf", str(tmp_path / "c"), "--now", NOW, "--out", str(tmp_path / "o2"),
                     "--dry-run"], capsys)
    assert rc == 0 and j["status"] == "empty" and not (tmp_path / "o2").exists()
    rc, j = run_cli(["--bot", "learner", "--run-dir", "x", "--now", NOW], capsys)
    assert rc == 2
    rc, j = run_cli(["--run-dir", "x", "--telegram", "--now", NOW], capsys)
    assert rc == 2


@pytest.mark.usefixtures("kilitli_donem")
def test_cli_holdout_run_locked(tmp_path, capsys):
    run = tmp_path / "run"
    run.mkdir()
    (run / "meta.json").write_text(json.dumps({"id": "r1", "period": ["2026-03-01T00:00:00.000Z", "2026-06-01T00:00:00.000Z"]}))
    rc, j = run_cli(["--run-dir", str(run), "--now", NOW, "--out", str(tmp_path / "o")], capsys)
    assert rc == 3 and j["status"] == "holdout_locked"
    assert json.loads(next((tmp_path / "o").rglob("rapor.json")).read_text()) == {"status": "holdout_locked"}


def test_telegram_injected(tmp_path, capsys):
    led = tmp_path / "l.sqlite"
    make_ledger(led, 3, trades=[{"entry": "2025-01-01T00:00:00.000Z", "exit": "2025-01-02T00:00:00.000Z"}])
    calls = []

    class N:
        def send_text(self, text, severity, dedup_key, **kw):
            calls.append((text, severity, dedup_key))
            raise RuntimeError("boom")
    rc = report_run.main(["--bot", "learner", "--ledger", str(led), "--cf", str(tmp_path / "c"), "--now", NOW,
                          "--out", str(tmp_path / "o"), "--telegram"], notifier=N())
    assert rc == 0 and len(calls) == 1 and calls[0][1] == "INFO" and calls[0][2] == "rapor:learner:2026-11-17"


# --------------------------------------------------------------------------- statik tarama
def test_static_rules():
    banned = re.compile(r"insert|update|delete|create|alter|drop|vacuum|attach|pandas|trader_ml|datetime\.now|utcnow|time\.time", re.I)
    for p in PKG.rglob("*.py"):
        txt = p.read_text(encoding="utf-8")
        assert not banned.search(txt), (p.name, banned.search(txt).group(0))
        tree = ast.parse(txt)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "connect" and p.name != "inputs.py":
                raise AssertionError(f"sqlite connect {p.name}")
    for base in ("trader_engine", "trader_core", "trader_ml"):
        for p in (ROOT / "src" / base).rglob("*.py"):
            assert "trader_reports" not in p.read_text(encoding="utf-8"), p


# --------------------------------------------------------------------------- mentor duzeltmeleri
def _run_dir(tmp_path, period, name="run"):
    run = tmp_path / name
    run.mkdir()
    meta = {"id": name} if period == "MISSING" else {"id": name, "period": period}
    (run / "meta.json").write_text(json.dumps(meta))
    return run


@pytest.mark.parametrize("period", ["MISSING", None, ["2025-01-01T00:00:00.000Z"], ["x", "y"], "ab", [1, 2, 3]])
def test_meta_period_fail_closed(tmp_path, capsys, period):
    run = _run_dir(tmp_path, period)
    rc, j = run_cli(["--run-dir", str(run), "--now", NOW, "--out", str(tmp_path / "o")], capsys)
    assert rc == 2 and j["code"] == "meta_period"


@pytest.mark.usefixtures("kilitli_donem")
def test_compare_backtest_holdout_skipped(tmp_path, capsys):
    led = tmp_path / "l.sqlite"
    make_ledger(led, 3, trades=[{"entry": "2025-01-01T00:00:00.000Z", "exit": "2025-01-02T00:00:00.000Z"}])
    cmp_dir = _run_dir(tmp_path, ["2026-03-01T00:00:00.000Z", "2026-06-01T00:00:00.000Z"], "cmp")
    (cmp_dir / "ledger.sqlite").write_bytes(b"okunursa hata verir")
    rc, j = run_cli(["--bot", "learner", "--ledger", str(led), "--cf", str(tmp_path / "c"), "--now", NOW,
                     "--out", str(tmp_path / "o"), "--compare-backtest", str(cmp_dir)], capsys)
    assert rc == 0
    rj = json.loads((Path(j["out_dir"]) / "rapor.json").read_text(encoding="utf-8"))
    assert "compare_holdout_locked" in rj["warnings"] and "compare" not in rj["gates"]


@pytest.mark.skipif(hasattr(__import__("os"), "geteuid") and __import__("os").geteuid() == 0, reason="root salt okunur dizini aşar")
def test_readonly_dirs_immutable_fallback(tmp_path, capsys):
    import os
    d = tmp_path / "ro"
    d.mkdir()
    led = d / "ledger.sqlite"
    make_ledger(led, 3, trades=[{"entry": "2025-01-01T00:00:00.000Z", "exit": "2025-01-02T00:00:00.000Z"}])
    c = sqlite3.connect(str(led))
    c.execute("PRAGMA journal_mode=WAL")
    c.close()
    for p in d.glob("*-wal"):
        if p.stat().st_size == 0:
            p.unlink()
    os.chmod(d, 0o555)
    try:
        rc, j = run_cli(["--bot", "learner", "--ledger", str(led), "--cf", str(tmp_path / "c"), "--now", NOW,
                         "--out", str(tmp_path / "o")], capsys)
        assert rc == 0
        rj = json.loads((Path(j["out_dir"]) / "rapor.json").read_text(encoding="utf-8"))
        assert any(w.startswith("immutable_fallback:") for w in rj["warnings"])
    finally:
        os.chmod(d, 0o755)


def test_wal_nonempty_blocks_immutable(tmp_path, monkeypatch):
    p = tmp_path / "x.sqlite"
    make_ledger(p, 3)
    (tmp_path / "x.sqlite-wal").write_bytes(b"x")
    real = sqlite3.connect

    def fail_ro(target, *a, **k):
        if "immutable" in target:
            raise AssertionError("immutable denenmemeli")
        raise sqlite3.OperationalError("unable to open database file")
    monkeypatch.setattr(I.sqlite3, "connect", fail_ro)
    with pytest.raises(I.ReportError) as e:
        I.open_ro(p, "ledger_missing")
    assert e.value.code == "ledger_unreadable"
    monkeypatch.setattr(I.sqlite3, "connect", real)


def test_risk_usd_from_config_only(tmp_path, capsys):
    led = tmp_path / "l.sqlite"
    make_ledger(led, 3, decisions=[{"ts": "2025-01-0%dT00:00:00.000Z" % i, "skip_reason": "veto_blocked"} for i in range(1, 4)])
    cfgp = tmp_path / "engine.base.json"
    cfgp.write_text(json.dumps({"target_trade_risk": 0.01, "wallet_start": 500.0, "mode": "paper"}))
    for extra in ([], ["--risk", "0.002"]):
        rc, j = run_cli(["--bot", "learner", "--ledger", str(led), "--cf", str(tmp_path / "c"), "--now", NOW, "--config", str(cfgp),
                         "--out", str(tmp_path / "o"), *extra], capsys)
        assert rc == 0


@pytest.mark.parametrize("extra", [["--risk", "0"], ["--synthetic-step", "BTC/USDT=0"]])
def test_zero_args_exit_2(tmp_path, capsys, extra):
    run = _run_dir(tmp_path, ["2025-01-01T00:00:00.000Z", "2025-02-01T00:00:00.000Z"])
    rc, j = run_cli(["--run-dir", str(run), "--now", NOW, "--out", str(tmp_path / "o"), *extra], capsys)
    assert rc == 2 and j["code"] == "arg_error"


def test_tr_copies_parity_with_telegram():
    from trader_core import telegram as T
    for x in (0.0, 1.5, -3.0, 1234.5, 0.85, -0.04):
        for d in (0, 1, 2):
            assert ST.tr_sayi(x, d) == T.tr_sayi(x, d)
            assert ST.tr_isaretli(x, d) == T.tr_isaretli(x, d)
            assert ST.tr_yuzde(x, d) == T.tr_yuzde(x, d)


def test_tr_gate_names_and_fixed_rows_flag():
    for k in GA.EXPECTED:
        n = GA.tr_name(k)
        assert n and not re.search(r"[a-z]_[a-z]|gate|veto:", n), (k, n)
    out = GA.build([], [], _cf([]), mode_backtest=False, period_days=60, veto_cost=None, risk_usd=5.0, cf_warning=None)
    fixed = next(b for b in out["blocks"] if isinstance(b, dict) and b.get("id") == "aday_uretmeyen")
    assert all(r["bayrak"] == "" for r in fixed["rows"])


def test_sizing_yetersiz_note():
    mk = {"sonuc": "kabul", "risk_orani": 1.0, "adim_kaybi": 0.0, "tavan_bagli": False}
    assert SZ._agg([mk] * 5, ["d"] * 5)["bayrak_not"] == "(yetersiz)"
