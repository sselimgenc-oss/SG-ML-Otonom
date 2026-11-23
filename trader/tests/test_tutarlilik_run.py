"""Tutarlilik raporu betigi (scripts/tutarlilik_run.py; Faz 2a): donem, kilit kesme, parametre kesimi, olculer, fark nedenleri, WARN
esikleri, TIKANDI, atomik cikti, saglik WARN ve haftalik ozet satiri. Sentetik veri (tmp_path); gercek veri/ag yok."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
sys.path.insert(0, str(ROOT / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


T = _load("tutarlilik_run")
NOW = datetime(2026, 11, 23, 0, 30, tzinfo=UTC)          # pazartesi
START, END = datetime(2026, 11, 16, tzinfo=UTC), datetime(2026, 11, 23, tzinfo=UTC)


def z(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def tr(pair="BTC/USDT", side="long", setup="T1", day=1, hour=10, ep=100.0, xh=6, xp=102.0, r=1.0, pnl=2.0, qty=1.0, **kw):
    e = START + timedelta(days=day, hours=hour)
    x = (e + timedelta(hours=xh)) if xh is not None else None
    d = dict(pair=pair, side=side, setup=setup, entry_ts=z(e), entry_price=ep, qty=qty, exit_ts=z(x) if x else None,
             exit_price=xp if x else None, exit_reason="stop" if x else None, fee_entry=0.1, fee_exit=0.1, funding_paid=0.0,
             realized_pnl=pnl if x else None, r_multiple=r if x else None, gross_pnl=None)
    d.update(kw)
    return d


def df(*rows):
    return pd.DataFrame(list(rows))


def cmp_(p, b, **kw):
    return T.compare(df(*p), df(*b), START, END, **kw)


def one(res, ad):
    return next(s for s in res["kurulumlar"] if s["ad"] == ad)


# ---------------------------------------------------------------------------------------------- donem
def test_week_window_is_last_seven_full_utc_days():
    assert T.week_window(NOW) == (START, END)
    assert T.week_window(datetime(2026, 11, 25, 13, 0, tzinfo=UTC)) == (START, END)       # hafta ici: o haftanin pazartesisi
    assert T.week_window(datetime(2026, 11, 22, 23, 59, tzinfo=UTC)) == (datetime(2026, 11, 9, tzinfo=UTC), START)


# ---------------------------------------------------------------------------------------------- olculer
def test_identical_trades_match_fully_and_zero_slip():
    r = cmp_([tr(), tr("ETH/USDT", day=2)], [tr(), tr("ETH/USDT", day=2)])
    s = one(r, "T1")
    assert (s["kagit_islem"], s["bt_islem"], s["eslesen"], s["yalniz_kagit"], s["yalniz_bt"]) == (2, 2, 2, 0, 0)
    assert s["eslesme_orani"] == 1.0 and s["giris_kayma_bps_ort"] == 0 and s["cikis_kayma_bps_ort"] == 0
    assert s["kagit_R"] == s["bt_R"] == 2.0 and s["kagit_kazanma"] == s["bt_kazanma"] == 1.0
    assert sum(s["nedenler"].values()) == 0 and T.warn_reasons([s]) == []


def test_match_ratio_formula_and_signal_counts():
    p = [tr(day=1), tr(day=2), tr(day=3)]                       # 3 kagit
    b = [tr(day=1), tr(day=2), tr(day=4)]                       # 2 ortak, 1 yalniz GT; 1 yalniz kagit
    s = one(cmp_(p, b), "T1")
    assert (s["eslesen"], s["yalniz_kagit"], s["yalniz_bt"]) == (2, 1, 1) and s["eslesme_orani"] == 0.5


def test_slippage_sign_positive_against_paper():
    # long: kagit girisi daha PAHALI (+), cikisi daha UCUZ (+); short tersi
    s = one(cmp_([tr(ep=100.10, xp=101.90)], [tr(ep=100.0, xp=102.0)]), "T1")
    assert s["giris_kayma_bps_ort"] == pytest.approx(10.0, abs=0.01) and s["cikis_kayma_bps_ort"] == pytest.approx(
        (102.0 - 101.9) / 102.0 * 1e4, abs=0.01)
    s = one(cmp_([tr(side="short", ep=99.9, xp=102.1)], [tr(side="short", ep=100.0, xp=102.0)]), "T1")
    assert s["giris_kayma_bps_ort"] == pytest.approx(10.0, abs=0.01) and s["cikis_kayma_bps_ort"] > 0
    # kagit lehine -> negatif
    s = one(cmp_([tr(ep=99.9)], [tr(ep=100.0)]), "T1")
    assert s["giris_kayma_bps_ort"] < 0
    assert s["giris_kayma_bps_en_kotu"] < 0


def test_trades_closing_after_window_end_are_open_for_both():
    late = dict(day=6, hour=22, xh=8)                           # cikis pencere sonundan sonra
    s = one(cmp_([tr(**late)], [tr(**late, xp=None) if False else tr(day=6, hour=22, xh=None)]), "T1")
    assert s["kagit_islem"] == 1 and s["kagit_kazanma"] is None and s["kagit_R"] == 0 and s["eslesen"] == 1
    assert s["nedenler"]["aciklanamayan"] == 0


# ---------------------------------------------------------------------------------------------- nedenler
def test_cause_cost_only_differs_in_fees():
    s = one(cmp_([tr(fee_exit=0.5, pnl=1.6)], [tr()]), "T1")
    assert s["nedenler"]["maliyet"] == 1 and s["nedenler"]["aciklanamayan"] == 0


def test_cause_delay_exit_later_and_entry_later():
    p = tr(xh=8, xp=102.0)
    b = tr(xh=6)
    s = one(cmp_([p], [b]), "T1")
    assert s["nedenler"]["gecikme"] == 1
    # giris: kagit-yalniz giris geri test-yalniz girisinden sonraki barda
    s = one(cmp_([tr(hour=11)], [tr(hour=10)]), "T1")
    assert s["nedenler"]["gecikme"] == 1
    assert s["nedenler"]["aciklanamayan"] == 0 and (s["yalniz_kagit"], s["yalniz_bt"]) == (1, 1)


def test_cause_paper_gap_and_no_paper_record():
    b = tr(day=2, hour=4)
    dec = pd.DataFrame([dict(pair="BTC/USDT", side="long", bar_close_ts=b["entry_ts"], final_action="skipped",
                             skip_reason="entry_gate_closed", veto_reason=None),
                        dict(pair="ETH/USDT", side="long", bar_close_ts=z(START + timedelta(days=1)), final_action="skipped",
                             skip_reason="no_signal", veto_reason=None)])
    s = one(cmp_([], [b], decisions=dec), "T1")
    assert s["nedenler"]["paper_gap"] == 1
    b2 = tr(day=3, hour=5)                                      # o barda hicbir karar kaydi yok: motor kapaliydi
    s = one(cmp_([], [b2], decisions=dec), "T1")
    assert s["nedenler"]["no_paper_record"] == 1


def test_cause_data_and_conflict_via_gaps():
    gaps = {"x": ["missing"]}
    fn = lambda pair, t0, t1: gaps["x"]  # noqa: E731
    s = one(cmp_([tr(ep=100.5)], [tr()], gaps_fn=fn), "T1")
    assert s["nedenler"]["veri"] == 1
    gaps["x"] = ["conflict", "missing"]
    s = one(cmp_([tr(ep=100.5)], [tr()], gaps_fn=fn), "T1")
    assert s["nedenler"]["data_conflict"] == 1


def test_cause_no_external_feed_special_case_anymore():
    """CT/ML ayriligi: kagit-yalniz kurulum ozel `veri` nedeni yoktur; eslesmeyen kagit islemi veri bosluguna bakilarak aciklanir."""
    import tutarlilik_run as T
    assert not hasattr(T, "EXTERNAL_FEED_SETUPS")
    s = one(cmp_([tr(setup="T1")], []), "T1")
    assert s["nedenler"]["veri"] == 0 and s["nedenler"]["aciklanamayan"] == 1


def test_cause_unexplained_price_diff_and_unmatched():
    s = one(cmp_([tr(ep=100.5, xp=103.0)], [tr()]), "T1")
    assert s["nedenler"]["aciklanamayan"] == 1
    s = one(cmp_([tr(pair="SOL/USDT")], []), "T1")
    assert s["nedenler"]["aciklanamayan"] == 1


# ---------------------------------------------------------------------------------------------- WARN
def _many(n, **kw):
    return [tr(day=1 + i % 5, hour=i, **kw) for i in range(n)]


def test_warn_requires_min_five_trades():
    p = _many(4, ep=100.5)
    b = _many(4)
    assert T.warn_reasons(cmp_(p, b)["kurulumlar"]) == []            # 4 islem: aciklanamayan olsa da uyari yok
    p, b = _many(5, ep=100.5), _many(5)
    assert any("aciklanamayan" in w for w in T.warn_reasons(cmp_(p, b)["kurulumlar"]))


def test_warn_match_ratio_below_90():
    p = _many(10)
    b = _many(9)                                                # 9 ortak, 1 yalniz kagit -> %90 (esik ALTI degil)
    assert not any("eslesme" in w for w in T.warn_reasons(cmp_(p, b, gaps_fn=lambda *a: ["missing"])["kurulumlar"]))
    b = _many(8)
    ws = T.warn_reasons(cmp_(p, b, gaps_fn=lambda *a: ["missing"])["kurulumlar"])
    assert any("eslesme" in w for w in ws)


def test_warn_r_difference_threshold_max_one_or_20pct():
    p, b = _many(5, r=1.0), _many(5, r=1.0)
    s = cmp_(p, b)["kurulumlar"]
    s[0]["bt_R"] = s[0]["kagit_R"] - 1.2                       # |dR|=1.2 > max(1.0, 0.2*5=1.0)
    assert any("R farki" in w for w in T.warn_reasons(s))
    s[0]["bt_R"] = s[0]["kagit_R"] - 0.9
    assert not any("R farki" in w for w in T.warn_reasons(s))
    s[0]["kagit_mutlak_R"] = 100.0                              # %20 = 20R: 1.2 R esigi asmaz
    s[0]["bt_R"] = s[0]["kagit_R"] - 1.2
    assert not any("R farki" in w for w in T.warn_reasons(s))


def test_warn_mean_entry_slip_over_10bps():
    p, b = _many(5, ep=100.2), _many(5)                          # 20 bps
    ws = T.warn_reasons(cmp_(p, b, gaps_fn=lambda *a: None)["kurulumlar"])
    assert any("giris kaymasi" in w for w in ws)


# ---------------------------------------------------------------------------------------------- aktivasyon kesimi
def test_activation_cut_moves_start_and_reports():
    acts = [dict(id=1, version_id=1, kind="initial", at=pd.Timestamp(START - timedelta(days=30)), params={"trail_atr": 3.0, "trigger_tf": "1h"}),
            dict(id=2, version_id=2, kind="apply", at=pd.Timestamp(START + timedelta(days=3, hours=5)),
                 params={"trail_atr": 3.5, "trigger_tf": "1h", "bogus": 1})]
    st, params, note = T.apply_activation_cut(START, END, acts)
    assert st == START + timedelta(days=3, hours=5) and "param_activation_changed" in note
    assert params == {"trail_atr": 3.5}
    st, params, note = T.apply_activation_cut(START, END, acts[:1])
    assert st == START and note is None and params == {"trail_atr": 3.0}


# ---------------------------------------------------------------------------------------------- uc uca (sahte kosucu)
def _mk_ledger(path: Path, trades: list[dict], acts=()):
    c = sqlite3.connect(path)
    cols = ["pair", "side", "setup", "entry_ts", "entry_price", "qty", "exit_ts", "exit_price", "exit_reason", "fee_entry",
            "fee_exit", "funding_paid", "realized_pnl", "r_multiple", "gross_pnl"]
    c.execute(f"CREATE TABLE v_trades ({', '.join(cols)})")
    for t in trades:
        c.execute(f"INSERT INTO v_trades VALUES ({','.join('?' * len(cols))})", [t.get(k) for k in cols])
    c.execute("CREATE TABLE v_decisions (pair, side, bar_close_ts, final_action, skip_reason, veto_reason)")
    c.execute("CREATE TABLE param_versions (id INTEGER PRIMARY KEY, params TEXT)")
    c.execute("CREATE TABLE param_activations (id INTEGER PRIMARY KEY, version_id INTEGER, kind TEXT, activated_at TEXT)")
    for i, (at, kind, params) in enumerate(acts, 1):
        c.execute("INSERT INTO param_versions VALUES (?, ?)", (i, json.dumps(params)))
        c.execute("INSERT INTO param_activations VALUES (?, ?, ?, ?)", (i, i, kind, at))
    c.commit()
    c.close()


def _fake_runner(bt_trades, seen=None):
    def runner(spec):
        if seen is not None:
            seen.append(spec)
        out = Path(spec.out_root) / spec.id
        out.mkdir(parents=True)
        _mk_ledger(out / "ledger.sqlite", bt_trades)
        return SimpleNamespace(out_dir=out)
    return runner


def _run_main(tmp_path, runner, now=NOW, paper=None, acts=()):
    root = tmp_path / "data"
    (root / "var" / "learner").mkdir(parents=True)
    _mk_ledger(root / "var" / "learner" / "ledger.sqlite", paper if paper is not None else [tr(), tr("ETH/USDT", day=2)], acts)
    rc = T.main(["--once", "--data-root", str(root), "--config-dir", str(ROOT / "config"),
                 "--market-db", str(root / "var" / "market.sqlite")], now_fn=lambda: now, runner=runner)
    assert rc == 0
    return root, json.loads((root / "var" / "durum" / "tutarlilik_v1.json").read_text(encoding="utf-8"))


def test_main_end_to_end_writes_md_and_json_schema(tmp_path):
    seen = []
    root, doc = _run_main(tmp_path, _fake_runner([tr(), tr("ETH/USDT", day=2)], seen))
    assert doc["sema"] == "ml.tutarlilik.v1" and doc["donem"] == {"bas": "2026-11-16T00:00:00Z", "bit": "2026-11-23T00:00:00Z"}
    assert doc["uyari"] is False and doc["uyari_nedenleri"] == [] and doc["not"] is None
    k = doc["kurulumlar"][0]
    for f in ("ad", "kagit_islem", "bt_islem", "eslesme_orani", "yalniz_kagit", "yalniz_bt", "giris_kayma_bps_ort", "cikis_kayma_bps_ort",
              "kagit_R", "bt_R", "kagit_pnl", "bt_pnl", "kagit_kazanma", "bt_kazanma", "nedenler"):
        assert f in k, f
    assert set(k["nedenler"]) == set(T.CAUSES)
    md = (root / "var" / "rapor" / "tutarlilik" / "2026-11-23.md").read_text(encoding="utf-8")
    assert "Kurulum basina" in md and "| T1 |" in md and "yalniz bilgi" in md.lower()
    s = seen[0]
    assert s.env == "paper" and s.source == "store" and s.start == START and s.end == END and s.veto == "none"
    assert not list((root / "var" / "rapor" / "tutarlilik").glob(".work/*"))      # gecici cikti temizlendi
    assert not list((root / "var" / "durum").glob("*.tmp"))


def test_main_warns_on_unexplained_and_ignores_below_min_trades(tmp_path):
    paper = _many(6, ep=100.5)
    bt = _many(6)
    _, doc = _run_main(tmp_path, _fake_runner(bt), paper=paper)
    assert doc["uyari"] is True and any("aciklanamayan" in w for w in doc["uyari_nedenleri"])


def test_main_tikandi_when_backtest_fails_never_silent_substitution(tmp_path):
    def boom(spec):
        raise RuntimeError("cok kurullu strateji desteklenmiyor")
    _, doc = _run_main(tmp_path, boom)
    assert doc["kurulumlar"] == [] and doc["uyari"] is False and doc["not"].startswith("TIKANDI")


def test_main_param_activation_cut_passes_params_and_reports(tmp_path):
    seen = []
    cut = z(START + timedelta(days=3))
    acts = [(z(START - timedelta(days=9)), "initial", {"trail_atr": 3.0, "trigger_tf": "1h"}),
            (cut, "apply", {"trail_atr": 3.5, "trigger_tf": "1h"})]
    _, doc = _run_main(tmp_path, _fake_runner([], seen), paper=[], acts=acts)
    assert seen[0].start == START + timedelta(days=3) and seen[0].params == {"trail_atr": 3.5}
    assert "param_activation_changed" in doc["not"] and doc["donem"]["bas"].startswith("2026-11-19")


def test_acik_kilitte_pencere_kesilmez(tmp_path):
    """23.11.2026 kullanici karari: kilit ACIK -> kilitli doneme dusen hafta penceresi kesilmez, calistirilir."""
    now = datetime(2026, 11, 2, 0, 30, tzinfo=UTC)
    seen = []
    _, doc = _run_main(tmp_path, _fake_runner([], seen), now=now, paper=[])
    assert seen and seen[0].start < datetime(2026, 11, 1, tzinfo=UTC)
    assert "kesildi" not in (doc.get("not") or "")


def test_holdout_part_of_window_is_truncated_and_never_read(tmp_path, kilitli_motor):      # kilit kapali bayragiyla (eski davranis)
    now = datetime(2026, 11, 2, 0, 30, tzinfo=UTC)                 # pencere 26 Ekim .. 2 Kasim -> 1 Kasim'a kesilir
    seen = []
    _, doc = _run_main(tmp_path, _fake_runner([], seen), now=now, paper=[])
    assert seen[0].start == datetime(2026, 11, 1, tzinfo=UTC) and seen[0].end == datetime(2026, 11, 2, tzinfo=UTC)
    assert "kesildi" in doc["not"]
    now = datetime(2026, 10, 26, 0, 30, tzinfo=UTC)                # tamamen kilitli: calistirilmaz
    seen2 = []
    _, doc = _run_main(tmp_path / "b", _fake_runner([], seen2), now=now, paper=[])
    assert seen2 == [] and doc["kurulumlar"] == [] and "kilitli" in doc["not"]


def test_missing_paper_ledger_is_note_not_crash(tmp_path):
    rc = T.main(["--once", "--data-root", str(tmp_path), "--config-dir", str(ROOT / "config")], now_fn=lambda: NOW,
                runner=lambda s: None)
    doc = json.loads((tmp_path / "var" / "durum" / "tutarlilik_v1.json").read_text(encoding="utf-8"))
    assert rc == 0 and doc["not"] == "kagit defteri yok" and doc["kurulumlar"] == []


def test_atomic_write_replaces_and_leaves_no_tmp(tmp_path):
    p = tmp_path / "a" / "x.json"
    T.write_atomic(p, "1")
    T.write_atomic(p, "2")
    assert p.read_text() == "2" and [x.name for x in p.parent.iterdir()] == ["x.json"]


# ---------------------------------------------------------------------------------------------- saglik + haftalik ozet
def test_health_warns_tutarlilik_sapma_only_when_flag_true(tmp_path):
    HR = _load("health_run")
    d = tmp_path / "durum"
    d.mkdir()
    assert HR.tutarlilik_alerts({}, NOW, durum_dir=str(d)) == []                     # dosya yok
    (d / "tutarlilik_v1.json").write_text("{bozuk", encoding="utf-8")
    assert HR.tutarlilik_alerts({}, NOW, durum_dir=str(d)) == []
    (d / "tutarlilik_v1.json").write_text(json.dumps({"uyari": False, "uyari_nedenleri": []}), encoding="utf-8")
    assert HR.tutarlilik_alerts({}, NOW, durum_dir=str(d)) == []
    (d / "tutarlilik_v1.json").write_text(json.dumps({"uyari": True, "uyari_nedenleri": ["T1: aciklanamayan=2"],
                                                      "donem": {"bas": "2026-11-16T00:00:00Z", "bit": "2026-11-23T00:00:00Z"}}), encoding="utf-8")
    al = HR.tutarlilik_alerts({}, NOW, durum_dir=str(d))
    assert len(al) == 1 and al[0].code == "tutarlilik_sapma" and al[0].level == HR.H.Status.WARN and "aciklanamayan=2" in al[0].body
    assert HR.tutarlilik_alerts({"TRADER_DATA_ROOT": str(tmp_path)}, NOW) == []     # veri kokunden: var/durum yok


def test_weekly_summary_line_cases(tmp_path):
    W = _load("weekly_summary_run")
    p = tmp_path / "t.json"
    assert W.tutarlilik_satiri({}, NOW, durum_path=p) == "Tutarlılık: rapor yok"
    doc = {"uretim": "2026-11-23T00:31:00Z", "uyari": False, "not": None,
           "kurulumlar": [{"eslesen": 24, "yalniz_kagit": 1, "yalniz_bt": 0, "kagit_R": 5.0, "bt_R": 4.6}]}
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert W.tutarlilik_satiri({}, NOW, durum_path=p) == "Tutarlılık: eşleşme %96, ΣR farkı +0,4R; uyarı yok"
    doc["uyari"] = True
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert "uyarı: tutarlilik_sapma" in W.tutarlilik_satiri({}, NOW, durum_path=p)
    assert W.tutarlilik_satiri({}, NOW + timedelta(days=9), durum_path=p) == "Tutarlılık: rapor yok"     # 8 gunden eski
    p.write_text("{", encoding="utf-8")
    assert W.tutarlilik_satiri({}, NOW, durum_path=p) == "Tutarlılık: rapor yok"
    doc.update(kurulumlar=[], **{"not": "TIKANDI: x"})
    p.write_text(json.dumps(doc), encoding="utf-8")
    assert W.tutarlilik_satiri({}, NOW, durum_path=p) == "Tutarlılık: TIKANDI: x"


def test_manual_window_args_and_validation(tmp_path):
    seen = []
    root = tmp_path / "data"
    (root / "var" / "learner").mkdir(parents=True)
    _mk_ledger(root / "var" / "learner" / "ledger.sqlite", [])
    base = ["--once", "--data-root", str(root), "--config-dir", str(ROOT / "config")]
    rc = T.main(base + ["--start", "2026-11-10", "--end", "2026-11-12T06:00:00Z"], now_fn=lambda: NOW, runner=_fake_runner([], seen))
    assert rc == 0 and seen[0].start == datetime(2026, 11, 10, tzinfo=UTC) and seen[0].end == datetime(2026, 11, 12, 6, tzinfo=UTC)
    assert T.main(base + ["--start", "2026-11-10"], now_fn=lambda: NOW) == 1                       # tek basina --start
    assert T.main(base + ["--start", "2026-11-12", "--end", "2026-11-10"], now_fn=lambda: NOW) == 1
    # kilitli doneme dusen elle pencere de kesilir/reddedilir (kilit elle pencerede de gecerli)
    seen2 = []
    rc = T.main(base + ["--start", "2026-11-01", "--end", "2026-11-03"], now_fn=lambda: NOW, runner=_fake_runner([], seen2))
    assert rc == 0 and seen2[0].start == datetime(2026, 11, 1, tzinfo=UTC)
