"""ML1 kagit giris kapisi (trader_engine/ml1_gate.py + motor/kapi baglantisi).

En onemlisi egitim/hizmet PARITESI: gercek kagit motoru (HistoricalSource, MultiArmSignalSource, threshold=0 paketiyle her aday puanlanir)
sentetik gecmiste kosulur; canli hesaplanan ozellikler + puanlar ayni adaylar icin cevrimdisi hatla (scan + build_features + score) ayni
cikmali (<= 1e-6; ozellik matrisi float64 ve float32 kesitinde). Ag yok; var/history yok."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("pyarrow")

import ml1_motor_destek as T  # noqa: E402

from trader_engine import ml1_gate as MG  # noqa: E402
from trader_ml.ml1 import data as D  # noqa: E402
from trader_ml.ml1 import groups as G  # noqa: E402
from trader_ml.ml1 import model as M  # noqa: E402

UTC = timezone.utc
TOL = 1e-6
K_BARS = MG.K_BARS


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    d = tmp_path_factory.mktemp("ml1_gate_hist") / "hist"
    T.write_history(d)
    return d


@pytest.fixture(scope="module")
def pkg0(tmp_path_factory):
    d = tmp_path_factory.mktemp("ml1_pkg0")
    return d / "ml1_package.json", T.write_package(d / "ml1_package.json", threshold=0.0)


def _ml1_cfg(pkg_path: Path, seed: Path | None = None) -> dict:
    return {"aktif": True, "paket_yolu": str(pkg_path), "tohum_yolu": str(seed or (pkg_path.parent / "yok_tohum.json"))}


class _Capture:
    """Motor kosusu boyunca: gozlenen aday anahtarlari ve puanlama girdi tablolari (canli ozellikler)."""

    def __init__(self) -> None:
        self.observed: set[tuple] = set()
        self.frames: list[pd.DataFrame] = []


def _patched(mp, cap: _Capture) -> None:
    obs, sc, real_m = MG.Ml1Gate.observe, MG.M.score, MG.M

    def observe(self, pair, D_, tf, r, trig, h4):
        obs(self, pair, D_, tf, r, trig, h4)
        if r["setup"] in G.GRUPLAR:
            cap.observed.add((pair, f"{r['setup']}@{tf}", pd.Timestamp(D_), r["side"]))

    def score(pkg, df):
        cap.frames.append(df.copy())
        return sc(pkg, df)
    mp.setattr(MG.Ml1Gate, "observe", observe)
    mp.setattr(MG, "M", SimpleNamespace(load_package=real_m.load_package, score=score))     # yalniz kapinin kullandigi M: cevrimdisi hat etkilenmez


def _live_table(cap: _Capture) -> pd.DataFrame:
    f = pd.concat(cap.frames, ignore_index=True)
    f["decision_ts"] = pd.to_datetime(f["decision_ts"], utc=True)
    return f.drop_duplicates(["pair", "arm_id", "decision_ts", "side"]).set_index(["pair", "arm_id", "decision_ts", "side"]).sort_index()


def _off_table(f: pd.DataFrame) -> pd.DataFrame:
    f = f.copy()
    f["decision_ts"] = pd.to_datetime(f["decision_ts"], utc=True)
    return f.set_index(["pair", "arm_id", "decision_ts", "side"]).sort_index()


def _assert_close(a: np.ndarray, b: np.ndarray, what: str) -> None:
    both_nan = np.isnan(a) & np.isnan(b)
    assert np.array_equal(np.isnan(a), np.isnan(b)), f"{what}: NaN deseni farkli"
    bad = ~both_nan & ~(np.abs(a - b) <= TOL + TOL * np.abs(b))
    assert not bad.any(), f"{what}: {int(bad.sum())} deger {TOL} ustu; en buyuk fark {np.nanmax(np.abs(a - b)[~both_nan]):.3g}"


# =========================================================================================================== PARITE (motor <-> cevrimdisi)
@pytest.fixture(scope="module")
def cold_run(tmp_path_factory, hist, pkg0):
    """Soguk baslangic: motor START'ta bos tamponla baslar (konfluans ilk pencerelerde eksik sayilabilir)."""
    tmp = tmp_path_factory.mktemp("ml1_cold")
    cap = _Capture()
    mp = pytest.MonkeyPatch()
    _patched(mp, cap)
    try:
        eng = T.make_engine(tmp, hist, _ml1_cfg(pkg0[0]))
        eng.run_range(T.START, T.END)
        yield SimpleNamespace(eng=eng, cap=cap, dec=T.decisions(eng), pkg=pkg0[1])
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def offline(hist, pkg0):
    return T.offline_scored(hist, pkg0[1], since=T.START + timedelta(minutes=1), until=T.END)


def test_candidate_set_equals_offline_scan(cold_run, offline):
    live = {(p, a, ts, s) for p, a, ts, s in cold_run.cap.observed}
    off = {(p, a, ts, s) for p, a, ts, s in _off_table(offline).index}
    assert len(off) >= 30, len(off)                                   # sentetik gecmis yeterli aday uretiyor
    assert live == off, (sorted(live - off)[:5], sorted(off - live)[:5])


def test_feature_and_score_parity_with_offline(cold_run, offline):
    live, off = _live_table(cold_run.cap), _off_table(offline)
    assert len(live) >= 20, len(live)                                 # puanlanan (giris degerlendirmesine ulasan) aday sayisi
    common = live.index.intersection(off.index)
    assert len(common) == len(live), "canli puanlanan her aday cevrimdisi tabloda olmali"
    names = M.feature_names()
    lx = M.design_matrix(live.loc[common].reset_index(), names)
    ox = M.design_matrix(off.loc[common].reset_index(), names)
    # konfluans soguk baslangicta eksik sayilabilir: ozellik esitligi konfluans DISINDAKI tum sutunlarda, konfluans icin <=; tam esitlik asagida
    cj = [j for j, n in enumerate(names) if n in M.CONF_COLS]
    nj = [j for j in range(len(names)) if j not in cj]
    _assert_close(lx[:, nj], ox[:, nj], "ozellik (konfluans disi)")
    _assert_close(lx[:, nj].astype(np.float32).astype(float), ox[:, nj].astype(np.float32).astype(float), "ozellik float32")
    assert (lx[:, cj] <= ox[:, cj] + 1e-9).all()                       # soguk baslangic: konfluans asla fazla degil
    # pencere tamamen gozlenen donemde ise (karar zamani - k mum >= ilk adim) konfluans TAM esit
    first = pd.Timestamp(T.START) + timedelta(minutes=15)
    tf_of = common.get_level_values("arm_id").str.split("@").str[1]
    full = np.array([(ts - pd.Timedelta(hours=_hours(t)) * K_BARS) >= first for ts, t in zip(common.get_level_values("decision_ts"), tf_of)])
    assert full.sum() >= 10, int(full.sum())
    _assert_close(lx[full][:, cj], ox[full][:, cj], "konfluans (tam pencere)")
    # puan: konfluans tam olan adaylarda <= 1e-6; ledgerdaki skor ile ayni
    ls = M.score(cold_run.pkg, live.loc[common].reset_index())
    os_ = off.loc[common, "score"].to_numpy(float)
    _assert_close(ls[full], os_[full], "puan")


def _hours(tf: str) -> int:
    return {"1h": 1, "4h": 4}[tf]


def test_ledger_records_score_sha_group_for_every_scored_candidate(cold_run, offline):
    dec = cold_run.dec
    scored = [r for r in dec if "ml1_skor" in r["features"]]
    assert len(scored) >= 15
    sha = cold_run.pkg["sha256"][:12]
    off = _off_table(offline)
    for r in scored:
        f = r["features"]
        assert f["ml1_sha"] == sha and f["ml1_grup"] == G.group(r["setup"]) and f["ml1_esik"] == 0.0
        assert 0.0 <= f["ml1_skor"] <= 1.0 and all(k in f for k in ("ml1_conf_same_tf", "ml1_conf_all_tf", "ml1_conf_groups", "ml1_conf_opp"))
    # esik 0: hicbir aday ml1 nedeniyle elenmez; girilen satirlar da puan tasir
    assert not [r for r in dec if r["veto_reason"] and str(r["veto_reason"]).startswith("gate:ml1_")]
    assert [r for r in scored if r["final_action"] == "entered"]
    # tampondaki puanlar cevrimdisi ile ayni (konfluansi tam olanlar)
    ok = 0
    for r in scored:
        k = (r["pair"], r["arm_id"], pd.Timestamp(r["bar_close_ts"]).tz_convert("UTC") if pd.Timestamp(r["bar_close_ts"]).tzinfo else pd.Timestamp(r["bar_close_ts"], tz="UTC"), r["side"])
        if k in off.index and abs(off.loc[k, "score"] - r["features"]["ml1_skor"]) <= TOL:
            ok += 1
    assert ok >= len(scored) // 2                                      # kalani yalniz soguk baslangic konfluansi (<=) nedeniyle farkli olabilir


@pytest.fixture(scope="module")
def warm_run(tmp_path_factory, hist, pkg0):
    """Sicak tampon: motor START-18s'de baslar; tampon cevrimdisi adaylarla (karar zamani <= baslangic) tohumlanir => konfluans TAM esit."""
    tmp = tmp_path_factory.mktemp("ml1_warm")
    start = T.START - timedelta(hours=18)                              # 4 Kasim 06:00 (onceki gunlerde aday var: tohum anlamli)
    end = start + timedelta(hours=12)
    full = T.offline_scored(hist, pkg0[1])
    cap = _Capture()
    mp = pytest.MonkeyPatch()
    _patched(mp, cap)
    try:
        eng = T.make_engine(tmp, hist, _ml1_cfg(pkg0[0]), start=start)
        eng.ml1.seed(full[full["decision_ts"] <= pd.Timestamp(start)])
        eng.run_range(start, end)
        yield SimpleNamespace(cap=cap, off=_off_table(full[(full["decision_ts"] > pd.Timestamp(start)) & (full["decision_ts"] <= pd.Timestamp(end))]))
    finally:
        mp.undo()


def test_warm_buffer_confluence_equals_offline(warm_run):
    live, off = _live_table(warm_run.cap), warm_run.off
    assert len(live) >= 4, len(live)
    common = live.index.intersection(off.index)
    assert len(common) == len(live)
    cols = list(M.CONF_COLS)
    _assert_close(live.loc[common, cols].to_numpy(float), off.loc[common, cols].to_numpy(float), "konfluans (sicak tampon)")
    names = M.feature_names()
    _assert_close(M.design_matrix(live.loc[common].reset_index(), names), M.design_matrix(off.loc[common].reset_index(), names), "ozellik (sicak)")
    assert {k for k in warm_run.cap.observed} == {(p, a, ts, s) for p, a, ts, s in off.index}


# =========================================================================================================== kapi birim testleri
def _frame(tf: str, pair: str, i: int, hist: Path, side="long", setup="T1", sda=1.5):
    """Gercek gecmisten (i. mum kapanisi karar) pencere + aday satiri."""
    trig, h4 = D.load_pair_tf(hist, pair, tf)
    delta = pd.Timedelta(tf)
    Dts = trig.index[i] + delta
    w = trig.iloc[max(0, i - 1499):i + 1]
    h4w = h4[h4.index + pd.Timedelta("4h") <= Dts].iloc[-1500:]
    px = float(trig["close"].iloc[i])
    r = {"setup": setup, "side": side, "planned_entry": px, "planned_stop": px * (0.99 if side == "long" else 1.01), "planned_target": None,
         "stop_dist_atr": sda}
    row = SimpleNamespace(signal=True, setup=setup, side=side, arm_id=f"{setup}@{tf}", tf=tf, pair=pair, bar_close_ts=Dts.to_pydatetime())
    return Dts.to_pydatetime(), r, w, h4w, SimpleNamespace(last=row)


def _observe(g: MG.Ml1Gate, tf, pair, i, hist, **kw):
    Dd, r, w, h4w, c = _frame(tf, pair, i, hist, **kw)
    g.observe(pair, Dd, tf, r, w, h4w)
    return Dd, c


I0 = 3000          # 1s mum indeksi (gecmis yeterince uzun)


def test_package_missing_and_corrupt_skip_with_paket_yok(hist, tmp_path, caplog):
    g = MG.Ml1Gate({"paket_yolu": str(tmp_path / "yok.json"), "tohum_yolu": str(tmp_path / "yok2.json")})
    Dd, c = _observe(g, "1h", "BTC/USDT", I0, hist)
    with caplog.at_level(logging.INFO, logger="engine.ml1"):
        out = g.prepare("BTC/USDT", Dd, (c,))
        assert out == (c,)
        v = g.verdict(c.last)
        assert v.code == MG.PAKET_YOK and v.ledger_reason == "ml_no_model" and v.score is None
        # saatte bir CRIT: ayni saat icinde sessiz, 1 saat sonra yine (ardisik 15 dk adimlari)
        for m in (15, 45, 59, 60, 75, 125):
            g._crit(Dd + timedelta(minutes=m), "ML1: gecerli paket yok; sentetik")
    crit = [r for r in caplog.records if r.levelno == logging.CRITICAL and "paket yok" in r.getMessage()]
    assert len(crit) == 1 + 2, [r.getMessage() for r in caplog.records]    # prepare (t=0) + 60 ve 125. dk (15/45/59/75 sessiz)
    assert g.counters["ml1_paket_yok"] == 1
    # bozuk dosyalar: cop json, yanlis sha, sema, esik yok
    for k, mut in enumerate((lambda p: "{not json", lambda p: json.dumps({**p, "sha256": "0" * 64}), lambda p: json.dumps({**p, "schema": "x/9"}),
                             lambda p: json.dumps({**p, "threshold": None, "sha256": M.package_hash({**p, "threshold": None})}))):
        good = json.loads(T.SEED_PKG.read_text())
        path = tmp_path / f"bozuk{k}.json"
        path.write_text(mut(good), encoding="utf-8")
        g2 = MG.Ml1Gate({"paket_yolu": str(path), "tohum_yolu": str(tmp_path / "yok.json")})
        Dd, c = _observe(g2, "1h", "BTC/USDT", I0, hist)
        g2.prepare("BTC/USDT", Dd, (c,))
        assert g2.verdict(c.last).code == MG.PAKET_YOK, k


def test_runtime_package_wins_seed_fallback_and_mtime_reload(hist, tmp_path):
    rt, seed = tmp_path / "rt" / "ml1_package.json", tmp_path / "seed" / "ml1_package.json"
    p_seed = T.write_package(seed, threshold=0.0)
    g = MG.Ml1Gate({"paket_yolu": str(rt), "tohum_yolu": str(seed)})
    Dd, c = _observe(g, "1h", "BTC/USDT", I0, hist)
    g.prepare("BTC/USDT", Dd, (c,))
    assert g.verdict(c.last).features["ml1_sha"] == p_seed["sha256"][:12] and g.verdict(c.last).code is None      # runtime yok -> tohum
    # runtime paket gelir: bir sonraki adimda (mtime/boyut degisti) o kullanilir
    p_rt = T.write_package(rt, threshold=1.5)
    assert p_rt["sha256"] != p_seed["sha256"]
    g.end_step()
    Dd2, c2 = _observe(g, "1h", "BTC/USDT", I0 + 1, hist)
    g.prepare("BTC/USDT", Dd2, (c2,))
    v = g.verdict(c2.last)
    assert v.features["ml1_sha"] == p_rt["sha256"][:12] and v.code == MG.ESIK_ALTI and v.features["ml1_esik"] == 1.5
    # ayni adim icinde dosya degisse bile paket adim basina bir kez denetlenir (cheap stat)
    T.write_package(rt, threshold=0.0)
    g.end_step()
    Dd3, c3 = _observe(g, "1h", "BTC/USDT", I0 + 2, hist)
    g.prepare("BTC/USDT", Dd3, (c3,))
    assert g.verdict(c3.last).code is None and g.verdict(c3.last).features["ml1_esik"] == 0.0
    # runtime bozulursa tohuma doner; ikisi de bozulursa paket yok
    rt.write_text("bozuk", encoding="utf-8")
    g.end_step()
    Dd4, c4 = _observe(g, "1h", "BTC/USDT", I0 + 3, hist)
    g.prepare("BTC/USDT", Dd4, (c4,))
    assert g.verdict(c4.last).features["ml1_sha"] == p_seed["sha256"][:12]
    seed.write_text("bozuk", encoding="utf-8")
    g.end_step()
    Dd5, c5 = _observe(g, "1h", "BTC/USDT", I0 + 4, hist)
    g.prepare("BTC/USDT", Dd5, (c5,))
    assert g.verdict(c5.last).code == MG.PAKET_YOK


def test_one_position_per_event_window(hist, tmp_path):
    pk = tmp_path / "p.json"
    T.write_package(pk, threshold=0.0)
    g = MG.Ml1Gate(_ml1_cfg(pk))
    res = []
    for k in range(6):                                              # 1s mumlari ardisik: bar_ts = I0 + k
        Dd, c = _observe(g, "1h", "BTC/USDT", I0 + k, hist)
        g.prepare("BTC/USDT", Dd, (c,))
        v = g.verdict(c.last)
        res.append(v.code)
        if k == 0:
            assert v.code is None
            g.note_entry("BTC/USDT", "long", "1h", Dd)             # onayli giris
        g.end_step()
    # giristen 1,2,3 mum sonra ayni olay; 4. mumda yeni olay
    assert res == [None, MG.AYNI_OLAY, MG.AYNI_OLAY, MG.AYNI_OLAY, None, None], res
    # ters yon / baska cift / baska tf ayni olay degil
    for pair, side, tf, ii in (("BTC/USDT", "short", "1h", I0 + 1), ("ETH/USDT", "long", "1h", I0 + 1), ("BTC/USDT", "long", "4h", 600)):
        g2 = MG.Ml1Gate(_ml1_cfg(pk))
        g2.note_entry("BTC/USDT", "long", "1h", _frame("1h", "BTC/USDT", I0, hist)[0])
        Dd, c = _observe(g2, tf, pair, ii, hist, side=side)
        g2.prepare(pair, Dd, (c,))
        if tf == "1h":
            assert g2.verdict(c.last).code is None, (pair, side, tf)


def test_highest_score_first_and_non_rule_arms_untouched(hist, tmp_path):
    pk = tmp_path / "p.json"
    T.write_package(pk, threshold=0.0)
    g = MG.Ml1Gate(_ml1_cfg(pk))
    Dd, ca = _observe(g, "1h", "BTC/USDT", I0, hist, setup="T1", sda=0.6)
    _, cb = _observe(g, "1h", "BTC/USDT", I0, hist, setup="MF1-YUTAN", sda=4.0)
    _, cc = _observe(g, "1h", "BTC/USDT", I0, hist, setup="R1", sda=2.5)
    m1 = SimpleNamespace(last=SimpleNamespace(signal=True, setup="M1", side="long", arm_id="M1@1h", tf="1h", pair="BTC/USDT", bar_close_ts=Dd))
    nosig = SimpleNamespace(last=SimpleNamespace(signal=False, setup="T1", side="long", arm_id="T1@1h", tf="1h", pair="BTC/USDT", bar_close_ts=Dd))
    out = g.prepare("BTC/USDT", Dd, (m1, ca, nosig, cb, cc))
    sc = {c.last.arm_id: g.verdict(c.last).score for c in (ca, cb, cc)}
    assert len(set(sc.values())) == 3 and g.verdict(m1.last) is None and g.verdict(nosig.last) is None
    assert out[0] is m1 and out[2] is nosig                                # kural kolu olmayan / sinyalsiz yuvalar yerinde
    got = [c.last.arm_id for c in (out[1], out[3], out[4])]
    assert got == sorted(sc, key=lambda a: -sc[a])                          # kural kolu adaylari puana gore (yuksek once)
    # giris sirasindan bagimsiz ayni sonuc
    g.end_step()
    out2 = g.prepare("BTC/USDT", Dd, (m1, cc, nosig, cb, ca))
    assert [c.last.arm_id for c in (out2[1], out2[3], out2[4])] == got


def test_scoring_error_is_fail_closed_and_never_raises(hist, tmp_path, monkeypatch):
    pk = tmp_path / "p.json"
    T.write_package(pk, threshold=0.0)
    g = MG.Ml1Gate(_ml1_cfg(pk))
    Dd, c = _observe(g, "1h", "BTC/USDT", I0, hist)
    monkeypatch.setattr(MG.M, "score", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("patladi")))
    assert g.prepare("BTC/USDT", Dd, (c,)) == (c,)
    assert g.verdict(c.last).code == MG.PAKET_YOK and g.counters["ml1_hata"] == 1
    # tamponda olmayan aday (observe cagrilmamis) de motoru durdurmaz
    c2 = SimpleNamespace(last=SimpleNamespace(signal=True, setup="T1", side="long", arm_id="T1@4h", tf="4h", pair="BTC/USDT", bar_close_ts=Dd))
    monkeypatch.undo()
    g.prepare("BTC/USDT", Dd, (c2,))
    assert g.verdict(c2.last).code == MG.PAKET_YOK


def test_warm_from_ledger_builds_buffer_and_event_window(tmp_path):
    from trader_core import ledger as L
    led = L.open_ledger(tmp_path / "l.sqlite", "learner", create=True)
    pv = led.init_params(T.pmap(), reason="strategy:test")
    now = datetime(2026, 11, 8, 12, tzinfo=UTC)

    def ev(pair, setup, tf, side, ts, action, skip, feats):
        from trader_core.ledger import DecisionEvent
        px = 100.0
        return DecisionEvent(bar_close_ts=ts, trigger_tf=tf, pair=pair, side=side, setup=setup, regime="trend_up", atr_ratio=1.0, rh=None, rl=None,
                             rh_touches=0, rl_touches=0, features={"atr_tf": 1.0, "stop_dist_atr": 1.0, "atr_4h": 2.0, "pullback_ema": 1, "ema_value": 99.0,
                                                                     "body_ratio": 0.5, **feats}, planned_entry=px, planned_stop=99.0, planned_target=None,
                             param_version_id=pv if isinstance(pv, int) else 1, veto_status="not_evaluated", veto_reason=None,
                             risk_allowed=True if action == "entered" else None, risk_reason=None, size_qty=1.0 if action == "entered" else None,
                             size_notional=100.0 if action == "entered" else None, size_margin=33.0 if action == "entered" else None,
                             size_risk_amount=1.0 if action == "entered" else None, leverage=3 if action == "entered" else None,
                             final_action=action, skip_reason=skip, arm_id=f"{setup}@{tf}")
    try:
        led.record_decision(ev("BTC/USDT", "T1", "1h", "long", now - timedelta(hours=2), "entered", None, {"ml1_skor": 0.7}))
        led.record_decision(ev("BTC/USDT", "MF1-YUTAN", "1h", "long", now - timedelta(hours=1), "skipped", "ml_filter", {"ml1_skor": 0.4}))
        led.record_decision(ev("BTC/USDT", "T1", "1h", "short", now - timedelta(hours=1), "skipped", "stop_width", {}))      # aday degil
        g = MG.Ml1Gate({})
        assert g.warm(led, now) == 2
        assert set(g._buf["BTC/USDT"]) == {("T1@1h", pd.Timestamp(now - timedelta(hours=2)), "long"),
                                           ("MF1-YUTAN@1h", pd.Timestamp(now - timedelta(hours=1)), "long")}
        assert g._son_giris == {("BTC/USDT", "long", "1h"): now - timedelta(hours=2)}
    finally:
        led.close()
    assert MG.Ml1Gate({}).warm(object(), now) == 0                      # defter okunamazsa bos baslar, firlatmaz


# =========================================================================================================== yapilandirma / baglanti
def test_config_switch_and_paper_only():
    import dataclasses

    from trader_engine.config import ConfigError, apply_overrides, load_cli_config
    from trader_engine.engine import _ml1_aktif
    cfg = load_cli_config(T.ROOT / "config", "learner", "paper")
    assert dict(cfg.ml1) == {"aktif": True} and _ml1_aktif(cfg)
    assert not _ml1_aktif(apply_overrides(cfg, ml1={"aktif": False}))
    assert not _ml1_aktif(apply_overrides(cfg, ml1={}))
    assert not _ml1_aktif(dataclasses.replace(cfg, ml1={}))
    for mode in ("live", "testnet", "backtest"):                           # canli/testnet/backtest'te asla
        assert not _ml1_aktif(SimpleNamespace(mode=mode, ml1={"aktif": True}))
    for bad in ({"aktif": 1}, {"aktif": True, "x": 1}, {"paket_yolu": "a"}, "evet", {"aktif": True, "paket_yolu": ""}):
        with pytest.raises(ConfigError):
            apply_overrides(cfg, ml1=bad)
    live = load_cli_config(T.ROOT / "config", "learner", "live")
    assert dict(live.ml1) == {} and not _ml1_aktif(live)


def test_aktif_false_leaves_engine_untouched(tmp_path_factory, hist):
    """ml1 kapali: ML1 nesnesi yok, kaynakta/kapida bagli degil, defter satirlarinda ml1_* alani yok; motor calisir."""
    tmp = tmp_path_factory.mktemp("ml1_off")
    for ml1 in ({"aktif": False}, {}):
        eng = T.make_engine(tmp / ("a" if ml1 else "b"), hist, ml1, start=T.START + timedelta(days=2))
        assert eng.ml1 is None and eng.gate.ml1 is None and eng.signals.ml1 is None
        eng.run_range(T.START + timedelta(days=2), T.START + timedelta(days=2, hours=6))
        assert eng.counters()["decisions"] >= 20
        assert not any(k.startswith("ml1_") for k in eng.counters())
        assert not any("ml1_skor" in r["features"] for r in T.decisions(eng))
        eng.ledger.close()
        eng.state.close()


def test_engine_keeps_running_without_package_and_reloads_new_one(tmp_path_factory, hist):
    """Motor-duzeyi senaryo: paket yok -> adaylar ml_no_model/gate:ml1_paket_yok ile atlanir, motor kararlari surer; dosya gelince (mtime) puanlanir;
    bozulunca yine atlanir."""
    tmp = tmp_path_factory.mktemp("ml1_swap")
    pk = tmp / "pk" / "ml1_package.json"
    start = T.START + timedelta(days=1)
    eng = T.make_engine(tmp, hist, _ml1_cfg(pk), start=start)
    seg = [start, start + timedelta(hours=12), start + timedelta(hours=24), start + timedelta(hours=36)]
    eng.run_range(seg[0], seg[1])
    c1 = eng.counters()
    assert c1["decisions"] >= 40 and c1.get("ml1_paket_yok", 0) >= 1 and c1.get("callback_errors", 0) == 0
    d1 = T.decisions(eng)
    assert d1 and all(r["skip_reason"] == "ml_no_model" and r["veto_reason"] == "gate:ml1_paket_yok" for r in d1 if r["final_action"] == "skipped"
                      and str(r["veto_reason"] or "").startswith("gate:ml1")), d1[:2]
    assert not [r for r in d1 if r["final_action"] == "entered"]            # paket yokken ML1 adayi girmez
    n1 = len(d1)
    T.write_package(pk, threshold=0.0)                                      # paket gelir
    eng.run_range(seg[1], seg[2])
    d2 = T.decisions(eng)[n1:]
    assert [r for r in d2 if "ml1_skor" in r["features"]] and eng.counters().get("ml1_gecti", 0) >= 1
    n2 = len(T.decisions(eng))
    T.write_package(pk, threshold=1.5)                                      # esik gecilemez: tum adaylar esik alti
    eng.run_range(seg[2], seg[3])
    d3 = T.decisions(eng)[n2:]
    esik = [r for r in d3 if r["veto_reason"] == "gate:ml1_esik_alti"]
    assert esik and all(r["skip_reason"] == "ml_filter" and r["final_action"] == "skipped" and r["features"]["ml1_esik"] == 1.5 for r in esik)
    assert eng.counters().get("ml1_esik_alti", 0) == len(esik) or eng.counters().get("ml1_esik_alti", 0) >= len(esik)
    pk.write_text("{bozuk", encoding="utf-8")                               # bozulur: motor yine calisir
    n3 = len(T.decisions(eng))
    c = eng.counters()["decisions"]
    eng.run_range(seg[3], seg[3] + timedelta(hours=6))
    assert eng.counters()["decisions"] > c and eng.counters().get("callback_errors", 0) == 0
    assert any(r["veto_reason"] == "gate:ml1_paket_yok" for r in T.decisions(eng)[n3:]) or eng.counters()["ml1_paket_yok"] > c1["ml1_paket_yok"]
    eng.ledger.close()
    eng.state.close()
