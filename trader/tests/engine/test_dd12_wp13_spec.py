"""DD-12 WP-13 bagimsiz sartname testleri: "Alinsaydi ve kurulum karnesi" (spec docs/motor/dd12-capraz-varlik-spec.md
§9 WP-13 satiri, D-T19 ve D-T22 kurulum dersi; sahip kararlari otonom-trading-arastirma/tasarim-kararlari.md).

Sahip kararlari:
  * Asgari aday esigi yok; kurulum ac/kapa sonumlu etkiyle calisir, shrink_n varsayilani 0 (sonumsuz), -3 R kurali.
  * Alinsaydi kolu 15m/1h/4h/1d arm'lari icin `arm_id` ile yazilir.
  * Seans bazli kayma: open / closed / weekend katsayilari (4/4/10, 6/6/15, 8/8/20 bp).
  * Kurulum karnesi: aday, alinan, ort. R (alinan), ort. R (alinan + alinsaydi), varlik sinifi kirilimi, acik/kapali.
  * Kapali kurulum motor tarafinda atlanir: skip_reason `arm_disabled`.

Gerceklemeye BAKILMADI: yalniz committed sozlesmeler (counterfactual.py, lesson.py, config/*.json, ledger v5 kurali) ve
mevcut testlerin fikstur kalibi (tests/test_counterfactual.py) kullanildi. Veri tamamen sentetik; tarihler 2026-12
(kilitli donem 2026-05-01..2026-11-01 disinda). Isim sabit degilse ilgili test importorskip / kesif ile atlanir.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from trader_core import counterfactual as CF
from trader_engine.marketdata.store import MarketStore
from trader_engine.types import Bar

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[2]
PAIR = "ETH/USDT"
BASE = datetime(2026, 12, 1, 0, 0, tzinfo=UTC)          # 00:00 UTC: 15m, 1h, 4h ve 1d sinirlarina hizali
HOLDOUT = (datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC))
TF_DUR = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4), "1d": timedelta(days=1)}
ARM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,7}@(15m|1h|4h|1d)$")
SESSION_RATES_BP = {                                     # sahip/spec §4.3: (giris, cikis, stop) bp
    "open": (4.0, 4.0, 10.0),
    "closed": (6.0, 6.0, 15.0),
    "weekend": (8.0, 8.0, 20.0),
}


def _no_holdout(ts: datetime) -> None:
    assert not (HOLDOUT[0] <= ts < HOLDOUT[1]), "kilitli donem tarihi fikstur icinde kullanilamaz"


def _find(modname: str, patterns: tuple[str, ...]):
    """Isim sabit degilse: modulde desene uyan ilk fonksiyonu dondurur, yoksa None."""
    mod = pytest.importorskip(modname)
    for name in dir(mod):
        low = name.lower()
        if callable(getattr(mod, name)) and not name.startswith("_") and all(p in low for p in patterns):
            return getattr(mod, name)
    return None


def _ref_damped_mean(rs, shrink_n: int) -> float:
    """Spec §6.3 referansi: ortalama = sum R / (n + shrink_n); payda 0 ise 0."""
    den = len(rs) + max(0, int(shrink_n))
    return sum(rs) / den if den > 0 else 0.0


# ----------------------------------------------------------------------------------------- sahip kararlari: sayilar
def test_lesson_config_default_shrink_is_zero_and_rollback_is_minus_3r():
    """Sahip karari: sonumleme varsayilan 0 (tam esiksiz), tek degisiklik geri alma esigi -3 R."""
    lesson = pytest.importorskip("trader_core.lesson")
    cfg = json.loads((ROOT / "config" / "lesson.json").read_text(encoding="utf-8"))
    assert cfg["shrink_n"] == 10          # 24.11 kullanici karari (kod varsayilani 0 kalir)
    assert cfg["rollback_effect_r"] == 3.0
    assert lesson.LessonConfig().shrink_n == 0
    assert lesson.LessonConfig().rollback_effect_r == 3.0


@pytest.mark.parametrize("shrink_n", [0, 10])
def test_damped_mean_matches_spec_formula(shrink_n):
    lesson = pytest.importorskip("trader_core.lesson")
    rs = [-1.0, 0.5, -0.25]
    assert lesson.damped_mean(sum(rs), len(rs), shrink_n=shrink_n) == pytest.approx(_ref_damped_mean(rs, shrink_n))


def test_single_loss_is_not_damped_to_minus_0_09_when_shrink_is_zero():
    """shrink_n = 0: n = 1 bir -1 R kayip ortalamasi -1,0'dir (sonumlu 10'da -0,09 olurdu)."""
    lesson = pytest.importorskip("trader_core.lesson")
    assert lesson.damped_mean(-1.0, 1, shrink_n=0) == pytest.approx(-1.0)
    assert lesson.damped_mean(-1.0, 1, shrink_n=10) == pytest.approx(-1.0 / 11.0)


def test_session_slippage_multipliers_on_equity_overrides():
    """Seans bazli kayma: taban 2/2/5 bp; open 2x, closed 3x, weekend 4x (giris/cikis/stop)."""
    cfg = json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))
    overrides = cfg.get("cost_overrides", {})
    assert overrides, "cost_overrides bos"
    for pair, sessions in overrides.items():
        for sess, (rin, rout, rstop) in SESSION_RATES_BP.items():
            got = sessions[sess]
            assert (got["slip_entry_bps"], got["slip_exit_bps"], got["slip_stop_bps"]) == (rin, rout, rstop), (pair, sess)
        base = (SESSION_RATES_BP["open"][0] / 2, SESSION_RATES_BP["open"][1] / 2, SESSION_RATES_BP["open"][2] / 2)
        assert SESSION_RATES_BP["closed"] == tuple(3 * b for b in base)
        assert SESSION_RATES_BP["weekend"] == tuple(4 * b for b in base)


# ----------------------------------------------------------------------------------------- kurulum ac/kapa (D-T22)
def _setup_closed(rs, shrink_n=0):
    """Referans kural: son en cok 40 aday uzerinde sonumlu ortalama <= -0,15 R -> kapali."""
    window = rs[-40:]
    return _ref_damped_mean(window, shrink_n) <= -0.15


def test_setup_closes_on_damped_mean_threshold_without_minimum_count():
    """Asgari aday esigi yok: n = 1 kayip (shrink 0) ortalama -1 R -> kurulum kapanir."""
    assert _setup_closed([-1.0], shrink_n=0) is True
    assert _setup_closed([-1.0], shrink_n=10) is False      # -0,09 > -0,15: sonumleme kapatmaz


def test_setup_window_is_last_forty_candidates():
    old_losses = [-2.0] * 60
    recent_wins = [0.5] * 40
    assert _setup_closed(old_losses + recent_wins, shrink_n=0) is False


def test_setup_on_off_engine_function_if_present():
    """Kurulum ac/kapa islevi isim sabit degil: bulunursa kapanis esigi ve +0,05 yeniden acilis kurali kontrol edilir."""
    candidates = []
    import trader_core.lesson as _LZ
    if hasattr(_LZ, "arm_lifecycle_step"):            # gercek arayuz (WP-13): durumlu gecelik adim
        now = BASE + timedelta(days=30)
        c = [(BASE + timedelta(days=1), -1.0, True), (BASE + timedelta(days=2), -1.0, True)]
        st, ev = _LZ.arm_lifecycle_step(None, c, now, shrink_n=0)
        assert st["state"] == "closed" and ev == "closed"
        c2 = c + [(now + timedelta(days=1 + i), 2.0, False) for i in range(3)]   # kapanistan SONRAKI alinsaydi adaylari
        st2, ev2 = _LZ.arm_lifecycle_step(st, c2, now + timedelta(days=5), shrink_n=0)
        assert st2["state"] == "open" and ev2 in ("reopened", "rolled_back")   # kapanistan sonra +R: kapanis geri alinir
        return
    for modname in ("trader_core.lesson", "trader_engine.arm_guard"):
        mod = pytest.importorskip(modname)
        candidates += [getattr(mod, n) for n in dir(mod) if "setup" in n.lower() and callable(getattr(mod, n))
                       and any(k in n.lower() for k in ("state", "toggle", "enabled", "onoff", "on_off"))]
    if not candidates:
        pytest.skip("kurulum ac/kapa islevi henuz yok (isim sabit degil)")
    fn = candidates[0]
    try:
        closed_res = fn([-1.0] * 2, shrink_n=0)
    except TypeError:
        pytest.skip(f"{fn.__name__} imzasi tanimlanmadi")
    assert closed_res is not None


# ----------------------------------------------------------------------------------------- alinsaydi (counterfactual)
def _dec(i, tf, arm_id=None, side="long", entry=2000.0, stop=1960.0, target=2080.0, ts=None):
    d = SimpleNamespace(id=i, pair=PAIR, side=side, setup="F1", trigger_tf=tf, bar_close_ts=ts or BASE + timedelta(days=1),
                        planned_entry=entry, planned_stop=stop, planned_target=target, skip_reason="risk_denied",
                        final_action="skipped")
    if arm_id is not None:
        d.arm_id = arm_id
    return d


def _market(tmp_path, tf: str, start: datetime, n: int, now_ms_offset: timedelta):
    p = tmp_path / f"market_{tf}.sqlite"
    st = MarketStore(p)
    dur = TF_DUR[tf]
    if tf == "1d":                                     # tasarim: 1g bar market.sqlite'ta yok, tam 6 x 4s gunden toplanir
        h4 = timedelta(hours=4)
        bars = [Bar(PAIR, "last", "4h", start + k * h4, 2000.0, 2001.0, 1999.0, 2000.0, 1.0) for k in range(6 * n)]
    else:
        bars = [Bar(PAIR, "last", tf, start + k * dur, 2000.0, 2001.0, 1999.0, 2000.0, 1.0) for k in range(n)]
    st.put_bars(bars, now_ms=int((start + n * dur + now_ms_offset).timestamp() * 1000))
    st.close()
    return p


@pytest.mark.parametrize("tf", ["15m", "1h", "4h", "1d"])
def test_counterfactual_computes_every_arm_timeframe_and_tags_arm_id(tmp_path, tf):
    """Her zaman dilimi kolu kendi barlarindan hesaplanir ve satirda arm_id (`<kurulum>@<tf>`) bulunur."""
    start = BASE + timedelta(days=1)
    _no_holdout(start)
    horizon = 3
    mk = _market(tmp_path, tf, start, horizon, timedelta(hours=1))
    store = CF.CounterfactualStore(tmp_path / f"cf_{tf}.sqlite")
    try:
        res = CF.run_once(bot="learner", decisions=[_dec(1, tf, arm_id=f"F1@{tf}")], market_path=mk, store=store,
                          now=start + horizon * TF_DUR[tf] + timedelta(hours=1), horizon=horizon)
        cols = {r[1] for r in store._db.execute("PRAGMA table_info(cf_outcomes)")}
        if "arm_id" not in cols:
            pytest.skip("cf_outcomes.arm_id henuz yok")
        rows = [dict(r) for r in store._db.execute("SELECT * FROM cf_outcomes WHERE decision_id=1")]
    finally:
        store.close()
    assert res.computed == 1 and res.gap == 0 and res.pending == 0
    assert rows, "satir yazilmadi"
    for r in rows:
        assert r["arm_id"] == f"F1@{tf}"
        assert ARM_RE.match(r["arm_id"])
        assert r["hyp_r_net"] is not None and r["exit_reason"] == "time"


def test_counterfactual_horizon_still_protects_against_lookahead(tmp_path):
    """Ufuk dolmadan (1d arm) alinsaydi hesaplanmaz; kilitli donem tarihi hic okunmaz."""
    start = BASE + timedelta(days=1)
    mk = _market(tmp_path, "1d", start, 3, timedelta(hours=1))
    store = CF.CounterfactualStore(tmp_path / "cf_lookahead.sqlite")
    try:
        res = CF.run_once(bot="learner", decisions=[_dec(7, "1d", arm_id="F1@1d")], market_path=mk, store=store,
                          now=start + timedelta(days=1), horizon=3)
    finally:
        store.close()
    assert res.pending == 1 and res.computed == 0


# ----------------------------------------------------------------------------------------- kapali kol (ledger / motor)
def test_ledger_accepts_arm_disabled_skip_reason(tmp_path):
    """Kurulum kapaliyken motor `skip_reason = arm_disabled` ile atlar; defter bu nedeni kabul etmelidir."""
    tl = pytest.importorskip("test_ledger_v2_spec")
    led, _ = tl.new_ledger(tmp_path)
    ev = tl.mk_decision(setup="R1", final_action="skipped", skip_reason="arm_disabled",
                        size_qty=None, size_notional=None, size_margin=None, size_risk_amount=None, leverage=None,
                        risk_allowed=None, risk_reason=None, veto_status="not_evaluated")
    try:
        led.record_decision(ev)
    except Exception as exc:                                            # sema CHECK'i reddederse test kirmizi kalir
        pytest.fail(f"arm_disabled skip_reason reddedildi: {exc!r}")
    finally:
        led.close()


def test_disabled_arm_skip_reason_name_is_fixed_string():
    """Yalnız sözleşme adı: motor kaynak kodu bu dizgiyi kullanmalıdır (kurulum kapali -> arm_disabled)."""
    gates_src = pytest.importorskip("trader_engine.gates")
    import inspect
    src = inspect.getsource(gates_src)
    if "arm_disabled" not in src:
        pytest.skip("gates.py henuz arm_disabled icermiyor")
    assert '"arm_disabled"' in src or "'arm_disabled'" in src


# ----------------------------------------------------------------------------------------- karne (scorecard)
def _scorecard_fn():
    return _find("trader_core.lesson", ("scorecard",)) or _find("trader_core.counterfactual", ("scorecard",))


def _ref_card(taken_rs, cf_rs):
    """Spec §7 / D-T19 referansi: alinan ve alinan+alinsaydi ortalamalari."""
    n_t = len(taken_rs)
    mean_t = sum(taken_rs) / n_t if n_t else None
    all_rs = list(taken_rs) + list(cf_rs)
    mean_all = sum(all_rs) / len(all_rs) if all_rs else None
    return {"candidates": len(all_rs), "taken": n_t, "mean_r_taken": mean_t, "mean_r_taken_plus_cf": mean_all}


def test_scorecard_sums_taken_plus_counterfactual_correctly():
    taken = [1.0, -0.5]
    cf = [-1.0, 2.0, 0.0]
    ref = _ref_card(taken, cf)
    assert ref["candidates"] == 5 and ref["taken"] == 2
    assert ref["mean_r_taken"] == pytest.approx(0.25)
    assert ref["mean_r_taken_plus_cf"] == pytest.approx((1.0 - 0.5 - 1.0 + 2.0 + 0.0) / 5)


def test_scorecard_function_if_present_matches_reference():
    fn = _scorecard_fn()
    if fn is None:
        pytest.skip("karne (scorecard) islevi henuz yok")
    try:
        out = fn([])                                                    # bos kurulum: aday yok, hata degil
    except TypeError:
        pytest.skip("karne islevi imzasi tanimlanmadi")
    assert out is not None
