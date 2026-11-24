"""Independent spec tests for DD-12 WP-08 (Ders ikizsiz ve esiksiz).

Written from docs/motor/dd12-capraz-varlik-spec.md (sec. 6, 9 WP-08, 15, D-T10, D-T26 ders) and the owner
decisions at the end of otonom-trading-arastirma/tasarim-kararlari.md.  The implementation was not read.
Names not fixed by the spec are looked up tolerantly (pytest.skip when absent).
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

TRADER = Path(__file__).resolve().parents[2]
LESSON_JSON = TRADER / "config" / "lesson.json"

LZ = pytest.importorskip("trader_core.lesson")
LG = pytest.importorskip("trader_core.ledger")


def _raw():
    return json.loads(LESSON_JSON.read_text(encoding="utf-8"))


def _find(*patterns):
    """First public callable of the lesson module whose name matches any regex."""
    for p in patterns:
        for n in sorted(dir(LZ)):
            if n.startswith("_"):
                continue
            o = getattr(LZ, n)
            if callable(o) and not isinstance(o, type) and re.search(p, n):
                return o
    return None


def _call(fn, *args, **kw):
    sig = inspect.signature(fn)
    kw = {k: v for k, v in kw.items() if k in sig.parameters}
    return fn(*args, **kw)


# ---------------------------------------------------------------- config (sec. 15, owner decisions)
def test_config_no_twin_keys():
    raw = _raw()
    assert not [k for k in raw if k.startswith("twin_")], "config/lesson.json must have no twin_* keys"
    assert "report_show_twin" not in raw
    assert "max_steps_from_twin" not in raw


def test_config_no_shadow_weeks():
    assert _raw().get("shadow_weeks", 0) == 0


def test_config_evidence_thresholds_closed():
    raw = _raw()
    assert "checkpoints" not in raw
    assert "max_user_requests_per_week" not in raw
    # 24.11 kullanici karari: ders esikleri ve geri alma (esiksiz kagit kaldirildi; olu early_* anahtarlari silindi)
    assert raw.get("min_affected") == 8
    assert raw.get("min_distinct_days") == 4
    assert raw.get("min_z") == 1.64
    assert raw.get("min_gap_r") == 0.5
    assert "early_min_n" not in raw and "early_min_days" not in raw
    assert raw.get("max_changes_per_night") == 1


def test_config_new_keys():
    raw = _raw()
    assert raw.get("shrink_n") == 10  # 24.11 kullanici karari: sonumleme 10 (az karar ile yanlis geri alma onlenir)
    assert raw.get("max_steps_from_ref") == 2


def test_config_loads_and_twin_disabled():
    cfg = LZ.load_config(LESSON_JSON)
    assert getattr(cfg, "twin_enabled", False) is False
    assert getattr(cfg, "shadow_weeks", 0) == 0
    assert getattr(cfg, "shrink_n") == 10


def test_config_shrink_zero_accepted(tmp_path):
    raw = _raw()
    raw["shrink_n"] = 0
    p = tmp_path / "lesson.json"
    p.write_text(json.dumps(raw))
    assert LZ.load_config(p).shrink_n == 0


# ---------------------------------------------------------------- LESSON_PARAMS extension
def _wait_param(params):
    c = [p for p in params if re.search(r"wait|bekle|cooldown|after_stop|post_stop|reentry|stop_wait", p)]
    return c[0] if c else None


def test_lesson_params_has_session_off():
    assert "session_off" in LG.LESSON_PARAMS
    assert "session_off" in LZ.LESSON_PARAMS


def test_lesson_params_has_post_stop_wait_0_to_3():
    p = _wait_param(LG.LESSON_PARAMS)
    assert p, f"no post-stop wait param in {LG.LESSON_PARAMS}"
    assert p in LZ.LESSON_PARAMS
    spec = {**LG.PARAM_SPECS, **getattr(LG, "OPTIONAL_PARAM_SPECS", {})}[p]
    lo = spec.get("lo", None)
    hi = spec.get("hi", None)
    choices = spec.get("choices")
    if choices:
        assert set(choices) >= {0, 1, 2, 3} and max(choices) == 3 and min(choices) == 0
    else:
        assert lo == 0 and hi == 3
    b = LG.LESSON_BOUNDS_DEFAULT[p]
    assert tuple(b) == (0, 3)


def test_existing_lesson_params_kept():
    for p in ("vol_ratio_max", "stop_buffer_atr", "trail_atr", "range_target_frac", "rr_min"):
        assert p in LG.LESSON_PARAMS


# ---------------------------------------------------------------- damped mean / effect (sec. 6.1, 6.3)
def test_damped_mean_formula():
    f = _find(r"damp", r"shrunk", r"shrink", r"sonum")
    if f is None:
        pytest.skip("damped-mean helper name not found")
    try:
        v = _call(f, [-1.0], shrink_n=10)
    except TypeError:
        pytest.skip("damped-mean helper signature unknown")
    assert v == pytest.approx(-1.0 / 11.0, abs=1e-6)  # ~ -0.09
    v0 = _call(f, [-1.0, 0.5, 0.5], shrink_n=0)
    assert v0 == pytest.approx(0.0, abs=1e-9)
    v10 = _call(f, [1.0, 2.0, 3.0], shrink_n=10)
    assert v10 == pytest.approx(6.0 / 13.0, abs=1e-6)


def test_effect_formula_added_real_minus_removed_counterfactual():
    f = _find(r"lesson_effect", r"^effect", r"impact", r"etki")
    if f is None:
        pytest.skip("lesson-effect helper name not found")
    try:
        v = _call(f, added=[1.0, -2.0], removed=[-1.0, 0.5])
    except TypeError:
        try:
            v = f([1.0, -2.0], [-1.0, 0.5])
        except TypeError:
            pytest.skip("effect helper signature unknown")
    if isinstance(v, dict):
        v = v.get("effect", v.get("sum", v.get("total")))
    # etki = sum R(added, real) - sum R(removed, counterfactual) = -1 - (-0.5) = -0.5 (undamped)
    assert v == pytest.approx(-0.5, abs=1e-6) or v == pytest.approx(-0.5 / 14.0, abs=1e-6) \
        or v == pytest.approx(-0.5 / 12.0, abs=1e-6)


# ---------------------------------------------------------------- source-level rules
def _src():
    return (TRADER / "src" / "trader_core" / "lesson.py").read_text(encoding="utf-8")


def test_source_has_no_hard_evidence_floors():
    cfg_src = _src()
    # the old validator floors (isint(.. "min_affected", 8) etc.) must be gone
    assert not re.search(r'"min_affected",\s*8\)', cfg_src)
    assert not re.search(r'"min_distinct_days",\s*8\)', cfg_src)
    assert not re.search(r'"shadow_weeks",\s*4', cfg_src)


def test_rollback_constants_in_source():
    s = _src()
    assert re.search(r"-\s*3(\.0)?\b", s), "-3 R single-change rollback threshold expected"
    assert re.search(r"-\s*10(\.0)?\b", s), "-10 R brake threshold expected"


def test_no_twin_dependency_when_twin_absent(tmp_path):
    """Config without any twin_* key loads; twin ledger absence must not raise."""
    raw = _raw()
    for k in list(raw):
        if k.startswith("twin_"):
            raw.pop(k)
    p = tmp_path / "lesson.json"
    p.write_text(json.dumps(raw))
    cfg = LZ.load_config(p)
    assert not getattr(cfg, "twin_enabled", False)
    f = getattr(LZ, "open_twin", None)
    if f is not None:
        try:
            r = f(cfg)
            # ikiz yok: None ya da (None, neden) — model/defter dönmez
            assert r is None or (isinstance(r, tuple) and r[0] is None)
        except TypeError:
            pass
