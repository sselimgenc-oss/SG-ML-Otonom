"""DD-12 WP-11 (Cok kurulumlu strateji altyapisi) bagimsiz sartname testleri.

Kaynak: docs/motor/dd12-capraz-varlik-spec.md §9 WP-11, D-T16, D-T18 (+ D-T13 tarafsizlik).  Gerceklemeye BAKILMADI;
yalniz sartname + HEAD'deki kod/testler.  Sentetik veri; ag yok.

SPEC-AMBIGUOUS (sartnamenin adlandirmadigi yerler; testler esnek kesfeder, bulunamazsa `skip`, sartname acikca
istedigi yerde FAIL eder):
  * Kurulum kesfi (`strategies/arms/__init__`) fonksiyon adi; kurulum modullerinin ic arayuzu.
  * Bilesik stratejide kurulum listesi verme yolu (fabrika `arms=` / `set_arms` / `arms` ozniteligi).
  * 1g bar toplama fonksiyonunun adi (bars.py): ad desenleri `agg|daily|1d|resample` ile kesfedilir.
  * `arm_id` tasiyicisi: `SignalRow.arm_id` (aday satiri) -> defter `decision_events.arm_id`/`trade_entries.arm_id`.
  * `arms` / `arm_max_positions` yapilandirma bicimi (liste/sozluk); birkac biçim denenir.
"""
from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import test_dd12_wp05_spec as W5           # ayni dizin: E (kagit motoru), sentetik gorunum yardimcilari
import test_engine_05_spec as T5
from trader_core import ledger as L
from trader_core import signals as S
from trader_engine import bars as B
from trader_engine.errors import ConfigError
from trader_engine.strategies.base import StrategyContext, StrategyError
from trader_engine.strategies.registry import get_strategy, list_strategies

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "trader_engine"
UTC = timezone.utc
H = timedelta(hours=1)
ALL_TFS = ("15m", "1h", "4h", "1d")
ARM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}@(15m|1h|4h|1d)$")


# ============================================================================================= yardimcilar
def _lab_mod():
    return pytest.importorskip("trader_engine.strategies.lab")


def _arms_mod():
    return pytest.importorskip("trader_engine.strategies.arms")


def _make_lab(arms=None, ml_mode="off"):
    """Bilesik stratejiyi (isteğe bagli kurulum listesiyle) kurar; yol bulunamazsa skip."""
    _lab_mod()
    st = get_strategy("price_action_lab_ml", ml_mode=ml_mode)
    if arms is None:
        return st
    lab = sys.modules["trader_engine.strategies.lab"]
    for n in sorted(dir(lab)):
        f = getattr(lab, n)
        if n.startswith("make") and callable(f) and "arms" in inspect.signature(f).parameters:
            s = f(arms=list(arms))
            if ml_mode != "off" and hasattr(s, "set_ml_mode"):
                s.set_ml_mode(ml_mode)
            return s
    for n in ("set_arms", "with_arms", "configure_arms"):
        if hasattr(st, n):
            r = getattr(st, n)(list(arms))
            return st if r is None else r
    if hasattr(st, "arms"):
        try:
            st.arms = list(arms)
            return st
        except AttributeError:
            pass
    pytest.skip("bilesik strateji kurulum listesi verme yolu bulunamadi (SPEC-AMBIGUOUS)")


def _params(tf):
    p = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    p["trigger_tf"] = tf
    return p


def _synth_minutes(n_days, seed=7, vol=0.0006, start="2026-01-01"):
    N = n_days * 24 * 60
    idx = pd.date_range(start, periods=N, freq="1min", tz="UTC")
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, vol, N) + 0.00001 * np.sin(np.arange(N) / 5000)))
    o = np.concatenate([[c[0]], c[:-1]])
    w = np.abs(rng.normal(0, vol / 2, N))
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + w), "low": np.minimum(o, c) * (1 - w),
                         "close": c, "volume": 1.0}, index=idx)


def _rs(m, rule):
    return m.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})


def _yuvarla(v):
    """Ondalik degerler 10 anlamli basamakla: islemci SIMD farki (AVX512 var/yok) son bitte iz birakir; ozet makineden bagimsiz."""
    return format(v, ".10g") if isinstance(v, float) else str(v)


def _digest(t):
    return hashlib.sha256(pd.util.hash_pandas_object(t.map(_yuvarla), index=True).values.tobytes()).hexdigest()[:16]


def _bars4h_synth(n, start="2026-03-01", seed=3):
    idx = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    rng = np.random.default_rng(seed)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.5, "low": np.minimum(o, c) - 0.5, "close": c,
                         "volume": np.arange(1, n + 1, dtype=float)}, index=idx)


# ============================================================================================= kayit / dosyalar
def test_spec_files_exist():
    for rel in ("strategies/lab.py", "strategies/arms/__init__.py", "strategies/arms/t1.py", "strategies/arms/r1.py"):
        assert (SRC / rel).is_file(), rel


def test_lab_registered_and_paper_allowed():
    _lab_mod()
    assert "price_action_lab_ml" in list_strategies()
    st = get_strategy("price_action_lab_ml", mode="paper")            # paper_allowed
    assert st.info.name == "price_action_lab_ml"
    assert {"T1", "R1"} <= set(st.info.setups)
    # gercek tasarim: motor karar adimi 15 dk (strateji `decision_tf`), param/defter tf'i 1s; kurulum tf'leri lab.tfs()
    assert getattr(st, "decision_tf", None) == "15m"
    st.set_arms([f"{s_}@{tf}" for s_ in ("T1", "R1") for tf in ALL_TFS])   # dort zaman diliminin hepsi kurulabilir
    assert set(ALL_TFS) <= set(st.tfs())


def test_lab_label_and_unchanged_registry_names():
    for n in ("price_action_v1", "price_action_v1_full", "price_action_v1_ml", "price_action_v1_full_ml"):
        assert n in list_strategies()
    st = get_strategy("price_action_lab_ml") if "price_action_lab_ml" in list_strategies() else pytest.skip("lab yok")
    assert st.label().startswith("strategy:price_action_lab_ml@")      # param_versions.reason etiketi


def test_lab_ml_mode_supported():
    _lab_mod()
    for m in ("off", "shadow", "active"):
        get_strategy("price_action_lab_ml", ml_mode=m)                  # set_ml_mode var: StrategyError yok
    with pytest.raises(StrategyError):
        get_strategy("price_action_lab_ml", ml_mode="bogus")


# ============================================================================================= kurulumlar adla bulunur
def _discover():
    am = _arms_mod()
    for n in sorted(dir(am)):
        if n.startswith("_"):
            continue
        f = getattr(am, n)
        if callable(f) and not isinstance(f, type) and re.search(r"discover|find|load|list|registry|available|names", n):
            try:
                r = f()
            except TypeError:
                continue
            if isinstance(r, dict) or isinstance(r, (list, tuple, set, frozenset)):
                return r
    for n in sorted(dir(am)):
        v = getattr(am, n)
        if not n.startswith("_") and isinstance(v, (dict, tuple, list)) and v and re.search(r"ARM|arm", n):
            return v
    pytest.skip("kurulum kesif fonksiyonu bulunamadi (SPEC-AMBIGUOUS)")


def test_arms_discovered_by_name_t1_r1():
    found = _discover()
    names = {str(getattr(k, "name", k)).upper().split("@")[0] for k in (found.keys() if isinstance(found, dict) else found)}
    assert {"T1", "R1"} <= names, names


def test_arms_init_discovers_by_name_not_static_imports():
    src = (SRC / "strategies" / "arms" / "__init__.py").read_text(encoding="utf-8")
    assert re.search(r"pkgutil|importlib|iter_modules|import_module|listdir|glob", src), \
        "kurulumlar adla bulunmali (pkgutil/importlib), sabit ice aktarma degil"
    assert not re.search(r"from\s+\.\s*(t1|r1)\s+import|from\s+\.(t1|r1)\b|import\s+(t1|r1)\b", src), \
        "__init__ kurulum modullerini sabit adla ice aktarmamali"


def test_other_registry_files_do_not_name_arm_modules():
    """'baska WP kayit dosyasina dokunmaz': registry.py kurulum modullerini adla saymaz."""
    reg = (SRC / "strategies" / "registry.py").read_text(encoding="utf-8")
    assert not re.search(r"arms\.(t1|r1|m1|l1|tf1|b1|f1|s1)\b", reg)


# ============================================================================================= bars.py: zaman dilimleri
def test_tf_1d_arithmetic():
    # gercek tasarim: eski tf_delta/floor_tf sozlesmesi degismez; kurulum yolu arm_* ailesi
    assert B.arm_tf_delta("1d") == timedelta(days=1)
    t = datetime(2026, 3, 5, 13, 37, tzinfo=UTC)
    assert B.arm_floor_tf(t, "1d") == datetime(2026, 3, 5, tzinfo=UTC)      # UTC gun siniri
    assert B.arm_is_tf_close(datetime(2026, 3, 5, tzinfo=UTC), "1d")
    assert not B.arm_is_tf_close(datetime(2026, 3, 5, 4, tzinfo=UTC), "1d")


@pytest.mark.parametrize("ts,want", [
    (datetime(2026, 3, 5, 0, 0, tzinfo=UTC), ["15m", "1h", "4h", "1d"]),
    (datetime(2026, 3, 5, 4, 0, tzinfo=UTC), ["15m", "1h", "4h"]),
    (datetime(2026, 3, 5, 5, 0, tzinfo=UTC), ["15m", "1h"]),
    (datetime(2026, 3, 5, 5, 15, tzinfo=UTC), ["15m"]),
    (datetime(2026, 3, 5, 20, 0, tzinfo=UTC), ["15m", "1h", "4h"]),
])
def test_closing_tfs_with_1d(ts, want):
    assert B.arm_closing_tfs(ts, ALL_TFS) == want


def _agg_fn():
    for n in sorted(dir(B)):
        if n.startswith("_"):
            continue
        f = getattr(B, n)
        if callable(f) and not isinstance(f, type) and re.search(r"agg.*(4h|1d|day|daily)|(4h|day|daily).*(to|agg)|to_1d|daily|resample", n, re.I):
            sig = inspect.signature(f)
            req = [p for p in sig.parameters.values() if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            if len(req) == 1:
                return f
    pytest.skip("1g toplama fonksiyonu bulunamadi (SPEC-AMBIGUOUS)")


def test_1d_is_exactly_six_4h_bars():
    f = _agg_fn()
    h4 = _bars4h_synth(12)                                    # 2 tam gun
    d = f(h4)
    assert len(d) == 2
    for i in range(2):
        g = h4.iloc[6 * i:6 * i + 6]
        r = d.iloc[i]
        assert d.index[i] == g.index[0] and d.index[i].hour == 0
        assert r["open"] == g["open"].iloc[0] and r["close"] == g["close"].iloc[-1]
        assert r["high"] == g["high"].max() and r["low"] == g["low"].min()
        assert r["volume"] == pytest.approx(g["volume"].sum())


def test_1d_incomplete_day_not_produced():
    """D-T16: eksik 4s barla 1g bar uretilmez (kismi gun, ortadaki delik)."""
    f = _agg_fn()
    h4 = _bars4h_synth(15)                                    # 2 tam gun + 3 bar (yarim gun)
    assert len(f(h4)) == 2                                    # yarim gun uretilmez (ileriye bakma yok)
    holey = h4.drop(h4.index[8])                              # ikinci gunun ortasinda delik
    d = f(holey.iloc[:12 + 3 - 1])
    assert len(d) == 1 and d.index[0] == h4.index[0]
    unaligned = _bars4h_synth(12).iloc[2:]                    # 08:00 baslangic: ilk gun eksik
    assert len(f(unaligned)) == 1


def test_1d_causal_prefix_independent():
    """Kapanmis gunler sonraki barlardan bagimsiz: ilk N gun, kuyruk eklenince degismez."""
    f = _agg_fn()
    h4 = _bars4h_synth(30)
    a = f(h4.iloc[:18])
    b = f(h4)
    pd.testing.assert_frame_equal(a, b.iloc[:len(a)])


# ============================================================================================= tarafsizlik (D-T13)
GOLD = {("price_action_v1", "1h"): "bfb477801efe0794", ("price_action_v1_full", "1h"): "b0d7aea78d821aad",
        ("price_action_v1_full", "15m"): "e38e9380e8c4f270"}


@pytest.mark.parametrize("name,tf", sorted(GOLD))
def test_neutrality_existing_strategies_compute_bit_identical(name, tf):
    """HEAD (WP-08) davranisinin sentetik veri altin ozeti (HEAD kodundan hesaplandi)."""
    m = _synth_minutes(60)
    bars = {"15m": _rs(m, "15min"), "1h": _rs(m, "1h"), "4h": _rs(m, "4h")}
    st = get_strategy(name)
    D = bars["4h"].index[-1].to_pydatetime() + timedelta(hours=4)
    b = {tf: bars[tf].tail(st.info.window_bars[tf]), "4h": bars["4h"].tail(st.info.window_bars["4h"])}
    t = st.compute(StrategyContext(pair="X", D=D, tf=tf, params=_params(tf), bars=b))
    assert _digest(t) == GOLD[(name, tf)]


def _run_pytest(*targets, timeout=1500):
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", *targets], cwd=str(ROOT), capture_output=True,
                          text=True, timeout=timeout, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})


def test_neutrality_backtest_golden_digest_unchanged():
    """D-T13: `test_t28_backtest_digest_unchanged` aynen gecer (summary/trades sha256 onekleri degismez)."""
    if not (ROOT / "var" / "history").exists():
        pytest.skip("var/history yok (gercek piyasa verisi)")
    r = _run_pytest("tests/engine/test_risk_ladder_impl.py::test_t28_backtest_digest_unchanged")
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def test_neutrality_compat_equity_unchanged():
    r = _run_pytest("tests/engine/test_engine_compat_equity.py")
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]


def test_neutrality_old_strategy_configs_still_load():
    """arms/arm_max_positions yokken (eski yapilandirmalar) hicbir sey degismez: yukleme + varsayilan strateji."""
    from trader_engine.config import load_cli_config
    for env in (None, "testnet"):
        c = load_cli_config(ROOT / "config", "learner", env)
        assert c.strategy in list_strategies()
        assert c.strategy != "price_action_lab_ml"


# ============================================================================================= yapilandirma
def _paper_raw():
    return json.loads((ROOT / "config" / "engine.paper.json").read_text(encoding="utf-8"))


def test_paper_config_uses_lab_with_arms_and_caps():
    raw = _paper_raw()
    assert raw["strategy"] == "price_action_lab_ml"
    arms = raw["arms"]
    names = list(arms.keys()) if isinstance(arms, dict) else list(arms)
    flat = {str(n).upper() for n in names}
    assert any(a.startswith("T1") for a in flat) and any(a.startswith("R1") for a in flat), flat
    cap = raw["arm_max_positions"]
    if isinstance(cap, int):
        assert cap == 6
    else:
        assert isinstance(cap, dict) and cap
        for k, v in cap.items():
            setup = str(k).split("@")[0].upper()
            assert v == (4 if setup in ("M1", "L1") else 6), (k, v)   # 20 Kasim: tavanlar 6 / 4
        assert setup != "C1", k          # CT/ML ayriligi: C1 kolu kaldirildi


def test_paper_config_loads_and_arms_parse():
    from trader_engine.config import load_cli_config
    c = load_cli_config(ROOT / "config", "learner", "paper")
    assert c.strategy == "price_action_lab_ml"
    assert getattr(c, "arms", None)
    assert getattr(c, "arm_max_positions", None) is not None


def test_new_keys_rejected_outside_paper(tmp_path):
    for mode in ("testnet",):        # 23.11 kullanici karari: canli = kagit (canli arms/arm_max_positions kabul eder)
        for key, val in (("arms", ["T1@1h"]), ("arm_max_positions", 4)):
            (tmp_path / mode).mkdir(exist_ok=True)
            with pytest.raises(ConfigError):
                T5.make_cfg(tmp_path / mode, "learner", mode, T5.PAIRS, **{key: val})


def test_arm_config_validation_rejects_garbage(tmp_path):
    for over in ({"arms": ["T1@2h"]}, {"arms": ["nope"]}, {"arm_max_positions": 0}, {"arm_max_positions": -1}):
        d = tmp_path / ("c%d" % abs(hash(json.dumps(over))))
        d.mkdir()
        (d / "veto.json").write_text((ROOT / "config" / "veto.live.json").read_text())
        with pytest.raises(ConfigError):
            W5._cfg(d, T5.PAIRS, strategy="price_action_lab_ml", **over)


# ============================================================================================= D-T18 esdegerlik + D-T16
def _view_at(D, days_back=60, days_fwd=3, seed=11, pairs=("BTC/USDT",)):
    return T5.SynthView(list(pairs), D - timedelta(days=days_back), D + timedelta(days=days_fwd), seed=seed, mode="rw", vol=0.0006)


def _src(view, st):
    from trader_engine.strategy_runner import MultiArmSignalSource, WindowedSignalSource
    cls = MultiArmSignalSource if getattr(st, "decision_tf", None) else WindowedSignalSource   # gercek tasarim: bilesik kaynak
    return cls(view, st, strict=True)


def _key(fr):
    r = fr.last
    if not bool(r.signal):
        return (False,)                                                  # sinyalsiz satirda NaN alanlar karsilastirilmaz
    return (bool(r.signal), r.setup, r.side, round(r.planned_entry, 9), round(r.planned_stop, 9),
            None if r.planned_target is None else round(r.planned_target, 9))


def test_dt18_lab_t1_r1_at_1h_equals_price_action_v1_full():
    """Bilesik strateji yalniz T1@1h + R1@1h ile, ayni veride price_action_v1_full ile ayni girisleri uretir."""
    D0 = datetime(2026, 3, 20, tzinfo=UTC)
    view = _view_at(D0)
    lab = _make_lab(["T1@1h", "R1@1h"])
    full = get_strategy("price_action_v1_full")
    tf = "1h" if "1h" in lab.info.allowed_trigger_tfs else lab.info.allowed_trigger_tfs[0]
    s_lab, s_full = _src(view, lab), _src(view, full)
    n_sig = 0
    D = D0
    for i in range(24 * 12):
        D = D0 + i * H
        a = s_lab.frame("BTC/USDT", D, _params(tf), 1)
        b = s_full.frame("BTC/USDT", D, _params("1h"), 1)
        assert a.status == b.status, D
        if a.status != "ok":
            continue
        ka, kb = _key(a), _key(b)
        assert ka == kb, (D, ka, kb)
        n_sig += int(ka[0])
    assert n_sig > 0, "sentetik veri sinyal uretmedi: test anlamsiz"


def test_dt16_only_closing_tf_arms_run_and_arm_id_shape():
    """Her karar adiminda yalniz O ANDA kapanan zaman diliminin kurulumlari adaylasir; arm_id = <KURULUM>@<tf>."""
    D0 = datetime(2026, 3, 20, tzinfo=UTC)
    view = _view_at(D0, seed=5)
    lab = _make_lab()
    s = _src(view, lab)
    tf = lab.info.allowed_trigger_tfs[0]
    seen = 0
    for i in range(96 * 3):                                   # 15 dk adimlari, 3 gun
        D = D0 + i * timedelta(minutes=15)
        fr = s.frame("BTC/USDT", D, _params(tf), 1)
        if fr.status != "ok" or fr.last is None or not fr.last.signal:
            continue
        arm = getattr(fr.last, "arm_id", None)
        if arm is None:
            pytest.skip("SignalRow.arm_id yok (SPEC-AMBIGUOUS)")
        assert ARM_RE.match(arm), arm
        setup, atf = arm.split("@")
        assert fr.last.setup == setup
        assert atf in B.arm_closing_tfs(D, ALL_TFS), (D, arm)
        seen += 1
    assert seen > 0


# ============================================================================================= nedensellik (ileriye bakma yok)
@pytest.mark.parametrize("D", [datetime(2026, 3, 20, 0, 0, tzinfo=UTC),     # 1g+4s+1s+15dk kapanir
                               datetime(2026, 3, 20, 8, 0, tzinfo=UTC),     # 4s kapanir, 1g degil
                               datetime(2026, 3, 20, 9, 15, tzinfo=UTC)])   # yalniz 15dk
def test_causality_future_bars_do_not_change_frame(D):
    """D'den sonraki (kapanmamis dahil) her mum degistirilse D'deki kare (hepsi: 4s/1g dahil) ayni kalir."""
    lab = _make_lab()
    tf = lab.info.allowed_trigger_tfs[0]
    va = _view_at(D, seed=21)
    vb = _view_at(D, seed=21)
    for p in vb.min:
        df = vb.min[p]
        fut = df.index >= D
        df.loc[fut, ["open", "high", "low", "close"]] = df.loc[fut, ["open", "high", "low", "close"]] * 3.0
    vb._tf.clear()
    fa = _src(va, lab).frame("BTC/USDT", D, _params(tf), 1)
    fb = _src(vb, _make_lab()).frame("BTC/USDT", D, _params(tf), 1)
    assert fa.status == fb.status
    if fa.status == "ok":
        assert (fa.last is None) == (fb.last is None)
        if fa.last is not None:
            assert _key(fa) == _key(fb)
        if fa.table is not None or fb.table is not None:                # bilesik kaynak tablo tutmaz (bellek); varsa ayni olmali
            pd.testing.assert_frame_equal(fa.table, fb.table)
        ea = [(_key(x) if x.last is not None else None) for x in getattr(fa, "extras", ()) or ()]
        eb = [(_key(x) if x.last is not None else None) for x in getattr(fb, "extras", ()) or ()]
        assert ea == eb


def test_causality_unclosed_4h_bar_never_used_for_1d():
    """1g bari yalniz kapanmis 4s barlardan: 4s'nin son (kapanmamis) bari asiri degerde olsa bile D'de gorulmez."""
    f = _agg_fn()
    h4 = _bars4h_synth(18)
    d_before = f(h4.iloc[:12])
    h4b = h4.iloc[:15].copy()
    h4b.iloc[12:, :4] = 1e9                                   # ikinci gunun ilk 3 bari (gun tamamlanmadi)
    d_after = f(h4b)
    pd.testing.assert_frame_equal(d_before, d_after)


# ============================================================================================= motor: arm_id, tavan, 15 dk adim
def _engine_over(pairs, **extra):
    big = {"kripto_buyuk": {"pairs": [p for p in pairs], "max_positions": 12}}
    base = dict(strategy="price_action_lab_ml", clusters=big, max_positions=16, optional_pairs=[], cost_overrides={},
                flat_bar_guard=True)
    base.update(extra)
    return base


def _mk_engine(tmp, pairs, start, caps=2):
    """arms/arm_max_positions bicimi sartnamede acik degil: birkac bicim dene."""
    variants = [{"arm_max_positions": {"T1": caps, "R1": caps}},
                {"arm_max_positions": {"T1@1h": caps, "R1@1h": caps}},
                {"arm_max_positions": caps},
                {"arm_max_positions": {"default": caps}}]
    err = None
    for i, v in enumerate(variants):
        for arms in (["T1@1h", "R1@1h"], {"T1@1h": {}, "R1@1h": {}}):
            d = Path(tmp) / f"v{i}{type(arms).__name__}"
            d.mkdir(parents=True, exist_ok=True)
            try:
                over = _engine_over(pairs, arms=arms, **v)
                e = _E(d, pairs, start, over)
                return e
            except (ConfigError, TypeError, KeyError) as ex:           # bicim reddedildi: siradaki
                err = ex
    pytest.skip(f"arms/arm_max_positions bicimi kabul edilmedi: {err!r}")


class _E(W5.E):
    def __init__(self, tmp, pairs, start, over):
        self.tmp = Path(tmp)
        self.pairs = list(pairs)
        self.clock = T5.SimClock(start)
        (self.tmp).mkdir(parents=True, exist_ok=True)
        (self.tmp / "veto.json").write_text((ROOT / "config" / "veto.live.json").read_text())
        self.cfg = T5.make_cfg(self.tmp, "learner", "paper", self.pairs, **over)
        self.view = T5.SynthView(self.pairs, start - timedelta(days=2), start + timedelta(days=4), clock=self.clock)
        self.eng = W5.build_engine(self.cfg, clock=self.clock, view=self.view)
        self.eng.signals = T5.FakeSignalSource()
        led = self.eng.ledger
        try:
            led.get_active_params()
        except L.LedgerError:
            led.init_params(dataclasses.asdict(S.DEFAULT_SIGNAL_PARAMS), reason=self.eng.strategy.label())
        self.vid = led.get_active_params().version_id
        self.eng.start()


PAIRS5 = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
D_E = datetime(2026, 11, 11, 15, 0, tzinfo=UTC)


def _ledger_rows(e, sql):
    con = sqlite3.connect(f"file:{e.cfg.ledger_path}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _signal_arm(e, D, pair, arm, **kw):
    try:
        e.signal(D, [pair], arm_id=arm, **kw)
    except TypeError:
        pytest.skip("SignalRow.arm_id alani yok (SPEC-AMBIGUOUS)")


def test_engine_writes_arm_id_on_decision_and_entry_rows(tmp_path):
    e = _mk_engine(tmp_path, PAIRS5[:2], D_E - H)
    try:
        D = D_E
        _signal_arm(e, D, "BTC/USDT", "T1@4h")
        e.decide(D)
        e.step(D)
        rows = _ledger_rows(e, "SELECT pair, arm_id, final_action FROM decision_events")
        assert ("BTC/USDT", "T1@4h", "entered") in rows, rows
        ent = _ledger_rows(e, "SELECT arm_id FROM trade_entries")
        assert ent and all(a == "T1@4h" for (a,) in ent), ent
    finally:
        e.close()


def test_engine_arm_id_default_is_setup_at_tf_for_1h(tmp_path):
    e = _mk_engine(tmp_path, PAIRS5[:2], D_E - H)
    try:
        e.signal(D_E, ["ETH/USDT"], setup="T1")                 # arm_id verilmez -> T1@1h
        e.decide(D_E)
        rows = _ledger_rows(e, "SELECT arm_id FROM decision_events WHERE pair='ETH/USDT'")
        assert rows and all(a and ARM_RE.match(a) for (a,) in rows), rows
    finally:
        e.close()


def test_engine_per_arm_cap(tmp_path):
    """Kurulum basina tavan (test: 2): ucuncu T1 girisi reddedilir; baska kurulum etkilenmez."""
    e = _mk_engine(tmp_path, PAIRS5, D_E - H, caps=2)
    try:
        D = D_E
        for p in PAIRS5[:3]:
            _signal_arm(e, D, p, "T1@1h")
        e.decide(D)
        e.step(D)
        opened = [p for p in PAIRS5[:3] if e.state.position_for_pair(p) is not None]
        assert len(opened) == 2, f"tavan 2 iken {len(opened)} T1 acildi"
        third = [p for p in PAIRS5[:3] if p not in opened][0]
        rows = _ledger_rows(e, f"SELECT final_action, skip_reason FROM decision_events WHERE pair='{third}'")
        assert rows and rows[-1][0] == "skipped" and rows[-1][1], rows
    finally:
        e.close()


def test_engine_arm_cap_counts_per_arm_not_global(tmp_path):
    """T1 tavani dolu iken farkli bir kurulumun (R1) adayi hala girer."""
    e = _mk_engine(tmp_path, PAIRS5, D_E - H, caps=2)
    try:
        D = D_E
        for p in PAIRS5[:2]:
            _signal_arm(e, D, p, "T1@1h")
        e.decide(D)
        e.step(D)
        assert sum(e.state.position_for_pair(p) is not None for p in PAIRS5[:2]) == 2
        D2 = D + H
        # kisa yon: ayni-yon risk siniri (iki long) kurulum tavanindan bagimsiz bir red nedenidir; test yalniz kurulum tavanini olcer
        _signal_arm(e, D2, "SOL/USDT", "R1@1h", setup="R1", side="short", planned_stop=102.0, planned_target=96.0,
                    regime="range", rh=104.0, rl=96.0,
                    features={"atr_tf": 1.0, "stop_dist_atr": 2.0, "atr_4h": 2.0, "rh_touches": 2, "rl_touches": 2,
                              "wick_ratio": 0.6, "rr": 2.0, "edge_dist_atr": 0.2})   # defter R1 ozellik sarti
        e.decide(D2)
        e.step(D2)
        assert e.state.position_for_pair("SOL/USDT") is not None, "R1 tavani T1 doluluguyla paylasilmamali"
    finally:
        e.close()


def test_engine_decision_step_every_15_minutes(tmp_path):
    """15 dk karar adimi: motor 15 dakikalik her sinir icin decision_step cagirir (saatlik degil)."""
    e = _mk_engine(tmp_path, PAIRS5[:1], D_E - H)
    try:
        calls = []
        orig = e.eng.signals.frame

        def spy(pair, D, params, vid):
            calls.append(D)
            return orig(pair, D, params, vid)
        e.eng.signals.frame = spy
        start = D_E
        for i in range(1, 5):                                  # 15:15 .. 16:00
            e.set_clock(start + i * timedelta(minutes=15) + timedelta(seconds=5))
            e.eng.advance_to(e.clock.now())
        got = sorted({c for c in calls})
        want = [start + i * timedelta(minutes=15) for i in range(1, 5)]
        assert [g for g in got if g in want] == want, got
    finally:
        e.close()
