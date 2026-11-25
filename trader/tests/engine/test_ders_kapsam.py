"""24.11 kullanici karari (ders esikleri ve geri alma), madde 4: ders kanit/etki kapsami = parametreyi motorda OKUYAN her kurulum.
Harita TEK yerde (`ledger.LESSON_SCOPE`); bu test motor kaynagini tarar ve yeni bir kurulum bir ders parametresini okuyup
haritada listelenmediyse BASARISIZ olur. Motor davranisina dokunulmaz (yalniz okunur)."""
import re
from pathlib import Path

import pytest

from trader_core import ledger as L

ROOT = Path(__file__).resolve().parents[2]
ARMS = ROOT / "src" / "trader_engine" / "strategies" / "arms"
SIGNALS = (ROOT / "src" / "trader_core" / "signals.py").read_text(encoding="utf-8")
CORE_PARAMS = ("vol_ratio_max", "stop_buffer_atr", "trail_atr", "range_target_frac", "rr_min")


def _arms() -> dict[str, str]:
    out = {}
    for f in sorted(ARMS.glob("*.py")):
        if f.name.startswith("_"):
            continue
        src = f.read_text(encoding="utf-8")
        m = re.search(r'^SETUP\s*=\s*"([A-Z][A-Z0-9]{1,7})"', src, re.M)
        if m and "FORMASYONLAR" not in src:      # 24.11 kullanici karari: kutuphane/varyant dosyalari (b1v.py SETUP="B1") ana kolun kaynagini ezmez
            out[m.group(1)] = src
    return out


def _mode(src: str) -> str | None:
    m = re.search(r'^EXIT_MODE\s*=\s*"(trail|target)"', src, re.M)
    return m.group(1) if m else None


# ortak tablo (signals.py) okumalari: T1 (iz suren, ters donus/geri cekilme) ve R1 (aralik) dallari
_CORE_READS = {"T1": {"stop_buffer_atr"}, "R1": {"stop_buffer_atr", "range_target_frac", "rr_min"}}


def derived_reads() -> dict[str, set[str]]:
    """{kurulum: okudugu ders parametreleri} -- kaynak kodundan."""
    out: dict[str, set[str]] = {}
    for setup, src in _arms().items():
        r = {p for p in CORE_PARAMS if re.search(rf"\bparams\.{p}\b", src)}
        if re.search(r"\bp\.regime\b", src):
            r.add("vol_ratio_max")                    # ortak tablonun rejimi vol_ratio_max ile hesaplanir
        if _mode(src) == "trail":
            r.add("trail_atr")                        # engine `trail_atr`i iz suren stoplu pozisyona yazar/okur
        out[setup] = r
    for setup in ("T1", "R1"):
        out.setdefault(setup, set())
        out[setup] |= _CORE_READS[setup] | {"vol_ratio_max"}
    return out


def test_core_reads_still_hold_in_signals_source():
    # T1/R1 okumalari signals.py'de gercekten var (tablo el ile; kaynak degisirse bu test haber verir)
    for p in ("stop_buffer_atr", "range_target_frac", "rr_min"):
        assert f"params.{p}" in SIGNALS
    assert "vol_ratio_max" in SIGNALS


def test_arm_discovery_finds_known_setups():
    assert {"T1", "R1", "B1", "F1", "H2", "S1", "TF1", "M1"} <= set(_arms())


# Acik istisna: B1 rr_min'i okur ama okuma ETKISIZDIR (sabit RR 2.0; rr_min siniri 2.0'in altinda) => kapsamda degil.
INERT_READS = {("B1", "rr_min")}


@pytest.mark.parametrize("param", CORE_PARAMS)
def test_scope_equals_setups_that_read_the_param(param):
    reads = {s for s, ps in derived_reads().items() if param in ps and (s, param) not in INERT_READS}
    assert set(L.LESSON_SCOPE[param]) == reads, (param, sorted(reads), L.LESSON_SCOPE[param])


def test_new_setup_reading_a_param_without_being_listed_fails():
    """Sozlesme: kaynaktan turetilen her (kurulum, parametre) haritada listeli olmali."""
    missing = [(s, p) for s, ps in derived_reads().items() for p in ps
               if p in L.LESSON_PARAMS and s not in L.LESSON_SCOPE[p] and (s, p) not in INERT_READS]
    assert not missing, f"haritada (ledger.LESSON_SCOPE) listelenmemis okumalar: {missing}"


def test_detector_catches_an_unlisted_reader():
    """Tespit mekanizmasi sahte bir kurulumu yakalar (testin kendisinin calistigini kanitlar)."""
    fake = 'SETUP = "ZZ9"\nEXIT_MODE = "trail"\nx = inp.params.rr_min\n'
    assert re.search(r"\bparams\.rr_min\b", fake) and _mode(fake) == "trail"
    assert "ZZ9" not in L.LESSON_SCOPE["rr_min"] and "ZZ9" not in L.LESSON_SCOPE["trail_atr"]


def test_inert_b1_rr_read_is_really_inert():
    b1 = _arms()["B1"]
    assert re.search(r"^TARGET_R\s*=\s*2\.0", b1, re.M) and L.LESSON_BOUNDS_DEFAULT["rr_min"][1] <= 2.0 + 1e-9
    assert "B1" not in L.LESSON_SCOPE["rr_min"]


def test_unread_params_are_not_in_lesson_menu():
    """session_off / post_stop_wait: motor defter parametresini okumaz (gates.py yalniz gate.session_off sozlugu) => lesson=False."""
    from trader_core import lesson as LS
    for p in ("session_off", "post_stop_wait"):
        assert p not in LS.LESSON_PARAMS
    eng = ROOT / "src" / "trader_engine"
    for f in eng.rglob("*.py"):
        assert "post_stop_wait" not in f.read_text(encoding="utf-8"), f
        assert '"session_off"' not in f.read_text(encoding="utf-8") or f.name == "gates.py", f


def test_exit_modes_are_t1():
    assert L.LESSON_SCOPE["exit_breakeven"] == ("T1",) and L.LESSON_SCOPE["exit_partial"] == ("T1",)
    assert 'setup == "T1"' in (ROOT / "src" / "trader_core" / "exit_modes.py").read_text(encoding="utf-8")


def test_every_lesson_param_has_nonempty_scope_of_known_setups():
    known = set(_arms())
    for p in L.LESSON_PARAMS:
        if p in ("session_off", "post_stop_wait"):
            continue                                                       # menude degil; kapsam bilgi amacli
        sc = L.LESSON_SCOPE[p]
        assert sc and set(sc) <= known, p
