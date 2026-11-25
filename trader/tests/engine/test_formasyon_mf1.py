"""24.11 kullanici karari: formasyon kutuphanesi, adim 1 (altyapi + MF1 12 mum formasyonu).
Sentetik ornek (long + short aynasi + bozulan kosul), setuplar_v3 esdegerligi (PINBAR/YUTAN/YILDIZ), ileriye bakis,
kimlik/kesif, tavanlar, on deger, cikis (zaman stopu / kural cikisi), kagit = canli."""
from __future__ import annotations

import importlib
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import exit_modes as EM
from trader_core import formasyon_on_deger as FOD
from trader_core import ledger as L
from trader_engine import arm_guard as AG
from trader_engine import config as C
from trader_engine.position_manager import ExitContext, evaluate_exit
from trader_engine.strategies import arms
from trader_engine.strategies.arms import _kutuphane as K
from trader_engine.strategies.arms import m1 as M1MOD
from trader_engine.strategies.arms import mf1

ROOT = Path(__file__).resolve().parents[2]
KODLAR = ("YILDIZ", "UCASKER", "DELICI", "ICSAHTE", "DISBAR", "YUTAN", "HARAMI", "TERSCEKIC", "CIMBIZ", "PINBAR", "ICCUBUK",
          "MARUBOZU")
TFS = ("15m", "1h", "4h", "1d")
KAL = 320.0                      # short aynasi: gercek fiyat = KAL - long fiyati (pozitif kalsin)

# ------------------------------------------------------------------------------------------------ sentetik seri
# Taban: 40 mum dusus (c=200-i, o=c+1, h=o+.4, l=c-.4); sonra formasyon mumlari (o, h, l, c). Beklenen long stop/hedef.
ORNEK = {
    "PINBAR": ([(160.5, 160.9, 157.0, 160.8)], 157.0, None),
    "YUTAN": ([(161.0, 161.2, 159.3, 159.5), (159.4, 161.7, 159.2, 161.5)], 159.2, None),
    "YILDIZ": ([(160.5, 160.6, 157.3, 157.5), (157.4, 157.8, 157.0, 157.5), (157.6, 159.6, 157.5, 159.5)],
               159.5 - 0.03 * 159.5, 159.5 + 0.09 * 159.5),
    "DELICI": ([(161.0, 161.2, 158.3, 158.5), (158.3, 160.4, 158.0, 160.3)], 158.0, None),
    "HARAMI": ([(162.0, 162.2, 158.3, 158.5), (159.0, 160.2, 158.9, 160.0)], 158.3, None),
    "TERSCEKIC": ([(160.4, 164.0, 160.3, 160.6), (160.7, 164.6, 160.6, 164.5)], 160.3, None),
    "UCASKER": ([(159.0, 161.1, 158.9, 161.0), (160.0, 163.1, 159.9, 163.0), (162.0, 165.1, 161.9, 165.0)], 158.9, None),
    "CIMBIZ": ([(161.0, 161.2, 158.0, 159.6), (159.0, 160.7, 158.05, 160.5)], 158.0, None),
    "MARUBOZU": ([(161.0, 165.2, 160.9, 165.0)], 160.9, None),
    "ICSAHTE": ([(161.5, 163.0, 160.0, 162.0), (161.5, 162.5, 160.5, 161.8), (160.2, 161.9, 159.5, 161.7)], 159.5, None),
    "DISBAR": ([(161.0, 161.3, 160.2, 160.5), (160.4, 162.5, 159.8, 162.0)], 159.8, None),
    "ICCUBUK": ([(160.0, 163.0, 159.0, 161.0), (160.5, 162.0, 160.0, 161.0), (161.0, 163.7, 160.8, 163.5)], 159.0, None),
}
BOZAN = (161.0, 161.1, 160.9, 161.0)      # son mumu doji ile degistirmek her formasyonu bozar


def taban(n=40):
    i = np.arange(n)
    c = 200.0 - i
    o = c + 1.0
    return [(float(a), float(a) + 0.4, float(b) - 0.4, float(b)) for a, b in zip(o, c)]


def seri(kod: str, *, short=False, bozuk=False):
    bars = taban() + list(ORNEK[kod][0])
    if bozuk:
        bars[-1] = BOZAN
    arr = np.array(bars, float)                       # (o, h, l, c)
    if short:
        arr = np.column_stack([KAL - arr[:, 0], KAL - arr[:, 2], KAL - arr[:, 1], KAL - arr[:, 3]])
    idx = pd.date_range("2026-01-01", periods=len(arr), freq="1h", tz="UTC")
    return pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3], "volume": 1.0}, index=idx)


def bul(kod, df, side):
    ham = K._Ham(df)
    assert ham.ok
    return mf1.FORMASYONLAR[kod].bul(ham.gorunum(side))


@pytest.mark.parametrize("kod", KODLAR)
def test_sentetik_long_short_ve_bozulan_kosul(kod):
    _, stop, hedef = ORNEK[kod]
    r = bul(kod, seri(kod), "long")
    assert r is not None, kod
    assert r["stop"] == pytest.approx(stop, abs=1e-9)
    if hedef is not None:
        assert r["hedef"] == pytest.approx(hedef, abs=1e-9)
    else:
        assert r["hedef"] is None                                  # 2R (hesapla doldurur)
    assert bul(kod, seri(kod), "short") is None                    # long serisinde short yok
    rs = bul(kod, seri(kod, short=True), "short")
    assert rs is not None, kod
    if kod == "YILDIZ":                                            # yuzde stop |fiyat| ile: aynadaki fiyat uzerinden
        assert -rs["stop"] == pytest.approx((KAL - 159.5) * 1.03, abs=1e-9)
    else:
        assert -rs["stop"] == pytest.approx(-(KAL - stop), abs=1e-9) or rs["stop"] == pytest.approx(-(KAL - stop), abs=1e-9)
    assert bul(kod, seri(kod, short=True), "long") is None
    assert bul(kod, seri(kod, bozuk=True), "long") is None         # kosul bozulunca tetiklemez


def _core_inp(df, pair="BTC/USDT", tf="1h"):
    return arms.ArmInput(pair=pair, tf=tf, D=df.index[-1].to_pydatetime() + timedelta(hours=1), trig=df, h4=None, params=None,
                         core_fn=lambda: M1MOD.empty_output(df.index))


@pytest.mark.parametrize("kod", KODLAR)
def test_motor_yolu_tablo_satiri(kod):
    """compute(): long ve short icin giris = kapanis, stop/hedef gercek fiyat, 2R hedef, kimlik MF1-<KOD>."""
    _, stop, hedef = ORNEK[kod]
    mod = arms.find_arm(f"MF1-{kod}")
    for short in (False, True):
        df = seri(kod, short=short, )
        t = mod.compute(_core_inp(df, pair=f"P{kod}{short}/USDT"))
        row = t.iloc[-1]
        assert row["setup"] == f"MF1-{kod}" and row["side"] == ("short" if short else "long")
        assert row["signal"] is np.True_ or bool(row["signal"])
        s = -1.0 if short else 1.0
        c = float(df["close"].iloc[-1])
        assert row["planned_entry"] == pytest.approx(c)
        sd = abs(c - float(row["planned_stop"]))
        if hedef is None:
            assert float(row["planned_target"]) == pytest.approx(c + s * 2 * sd)
            assert float(row["rr"]) == pytest.approx(2.0)
        assert s * (float(row["planned_target"]) - c) > 0 and s * (c - float(row["planned_stop"])) > 0
        assert t["signal"].iloc[:-1].sum() == 0
    bos = mod.compute(_core_inp(seri(kod, bozuk=True), pair=f"B{kod}/USDT"))
    assert not bool(bos["signal"].iloc[-1]) and bos["setup"].iloc[-1] is None


def test_yildiz_gercek_stop_hedef_yuzde_ve_zaman_stopu():
    df = seri("YILDIZ")
    row = arms.find_arm("MF1-YILDIZ").compute(_core_inp(df, pair="YS/USDT")).iloc[-1]
    c = 159.5
    assert float(row["planned_stop"]) == pytest.approx(c * 0.97) and float(row["planned_target"]) == pytest.approx(c * 1.09)
    assert arms.time_stop_of("MF1-YILDIZ") == 20 and arms.time_stop_of("MF1-YUTAN") == 48 and arms.time_stop_of("T1") == 48


def test_stop_dar_ise_elenir():
    """stop mesafesi girisin %0,6'sindan kucukse stop_width (aday kaydedilir, sinyal degil)."""
    df = seri("MARUBOZU")
    df.iloc[-1] = [161.0, 161.2, 160.9999, 161.1999, 1.0]      # dar govde ama marubozu: aralik < 1.5 ATR -> aday yok
    assert arms.find_arm("MF1-MARUBOZU").compute(_core_inp(df, pair="SW/USDT")).iloc[-1]["setup"] is None
    # PINBAR dar stop: alt golge 0.4 (>= 2 govde), giris 160.8 stop 160.4 -> %0,25
    p = seri("PINBAR")
    p.iloc[-1] = [160.7, 160.82, 160.4, 160.8, 1.0]
    row = arms.find_arm("MF1-PINBAR").compute(_core_inp(p, pair="SW2/USDT")).iloc[-1]
    assert row["setup"] == "MF1-PINBAR" and row["skip_reason"] == "stop_width" and not bool(row["signal"])


# ------------------------------------------------------------------------------------------------ rastgele yuruyus
def rw(n, seed, vol=0.012):
    rng = np.random.default_rng(seed)
    c = 100.0 * np.exp(np.cumsum(rng.normal(0, vol, n)))
    o = np.concatenate(([100.0], c[:-1])) * np.exp(rng.normal(0, vol / 3, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 2, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 2, n)))
    return o, h, l, c


def atr_of(o, h, l, c):
    from trader_core import indicators as I
    df = pd.DataFrame({"high": h, "low": l, "close": c})
    return I.atr(df, 14).to_numpy(dtype=float)


def tara(kod, o, h, l, c, atr, bas=40, son=None):
    """{(t, yon): (stop, hedef)} long uzayinda, iki yon de."""
    n = len(c)
    son = n - 1 if son is None else son
    gl = K.Gorunum(o, h, l, c, atr, 0)
    gs = K.Gorunum(-o, -l, -h, -c, atr, 0)
    f = mf1.FORMASYONLAR[kod].bul
    out = {}
    for t in range(bas, son + 1):
        for yon, g in ((1, gl), (-1, gs)):
            g.t = t
            r = f(g)
            if r is not None:
                out[(t, yon)] = (r["stop"], r["hedef"])
    return out


def _ref():
    d = str(ROOT / "tests" / "fixtures" / "formasyon_ref")
    sys.path.insert(0, d)
    try:
        for m in ("gostergeler", "setuplar_v3"):
            sys.modules.pop(m, None)
        return importlib.import_module("setuplar_v3")
    finally:
        sys.path.remove(d)


def _enjekte_yildiz(o, h, l, c, rng):
    """Rastgele yuruyuse yildiz kaliplari gom (v3 ile karsilastirmada yildiz sinyali bulunsun)."""
    for t in range(60, len(c) - 5, 400):
        b = c[t - 1]
        o[t - 2], c[t - 2] = b * 1.0, b * 0.97
        h[t - 2], l[t - 2] = b * 1.0005, b * 0.9695
        o[t - 1], c[t - 1] = b * 0.9701, b * 0.9702
        h[t - 1], l[t - 1] = b * 0.9712, b * 0.9692
        o[t], c[t] = b * 0.9715, b * 0.9885
        h[t], l[t] = b * 0.9895, b * 0.9710


@pytest.mark.parametrize("kod,v3kod", [("PINBAR", "MUM_PINBAR"), ("YUTAN", "MUM_YUTAN"), ("YILDIZ", "MUM_YILDIZ")])
def test_setuplar_v3_esdegerligi(kod, v3kod):
    """Rastgele yuruyuste her t icin kutuphane sonucu `gercek_sinyaller` ile ayni (t, yon, stop, hedef)."""
    v3 = _ref()
    n = 6000
    o, h, l, c = rw(n, 7, 0.015)
    _enjekte_yildiz(o, h, l, c, None)
    a = atr_of(o, h, l, c)
    v = np.ones(n)
    Fd = {}
    for yon in (1, -1):
        Fd[yon] = v3.ozellik({"t": np.arange(n), "o": o, "h": h, "l": l, "c": c, "v": v}, yon)
    ref = {}
    for t, d, sp, sa, ha, et in v3.gercek_sinyaller(v3kod, Fd):
        if t < 40 or t > n - 2:
            continue
        ref[(t, d)] = (sp["stop"], sp["hedef"])
    lib = tara(kod, o, h, l, c, a, 40, n - 2)
    # kutuphane long uzayinda: short icin fiyat aynasi
    lib_gercek = {k: (k[1] * s, k[1] * hd) for k, (s, hd) in ((k, (v[0], v[1] if v[1] is not None else float("nan"))) for k, v in lib.items())}
    # 2R hedefleri v3'te de ayni formul: kitaptan beklenen (c + 2 (c - l)) -> lib hedefi None (hesapla doldurur): giris/stop ile uret
    def tam(k, st, hd):
        t, d = k
        cc = d * c[t] if d == -1 else c[t]
        if d == -1:
            cc = -c[t]
        return st, (hd if hd is not None and not np.isnan(hd) else cc + 2 * (cc - st))
    lib_n = {}
    for (t, yon), (st, hd) in lib.items():
        cc = c[t] if yon == 1 else -c[t]
        hh = hd if hd is not None else cc + 2 * (cc - st)
        lib_n[(t, yon)] = (yon * st, yon * hh)
    # iki yonlu mumlar ve dar stoplar (motor eler) disarida
    ikili = {t for (t, y) in lib_n if (t, -y) in lib_n}
    f = lambda d: {k: v for k, v in d.items() if k[0] not in ikili}
    assert f(ref).keys() == f(lib_n).keys(), (kod, sorted(set(f(ref)) ^ set(f(lib_n)))[:10])
    for k in f(ref):
        assert f(ref)[k][0] == pytest.approx(f(lib_n)[k][0], rel=1e-9) and f(ref)[k][1] == pytest.approx(f(lib_n)[k][1], rel=1e-9), k
    assert len(f(ref)) >= 5, (kod, len(f(ref)))


def test_ileriye_bakis_ve_pencere_bagimsizligi():
    """t'den sonraki mumlar degisince t'deki karar degismez; 500 ve 5000 mumluk pencere ayni adayi verir (1e-9)."""
    n = 5000
    o, h, l, c = rw(n, 11, 0.01)
    a = atr_of(o, h, l, c)
    toplam = 0
    rng = np.random.default_rng(3)
    for kod in KODLAR:
        tam = tara(kod, o, h, l, c, a, 40, n - 1)
        toplam += len(tam)
        o2, h2, l2, c2 = (x.copy() for x in (o, h, l, c))
        kes = 2500
        for x in (o2, h2, l2, c2):
            x[kes + 1:] = x[kes + 1:] * rng.uniform(0.5, 1.5, n - kes - 1)
        a2 = atr_of(o2, h2, l2, c2)
        deg = tara(kod, o2, h2, l2, c2, a2, 40, kes)
        onc = {k: v for k, v in tam.items() if k[0] <= kes}
        assert deg.keys() == onc.keys(), kod                     # t <= kes kararlari ayni
        for k in onc:
            assert deg[k][0] == pytest.approx(onc[k][0], abs=1e-9)
        # pencere: son 500 mum, t = son mum
        pen = tara(kod, o[-500:], h[-500:], l[-500:], c[-500:], atr_of(o[-500:], h[-500:], l[-500:], c[-500:]), 40, 499)
        for (t, y), v in pen.items():
            gt = t + n - 500
            assert (gt, y) in tam, (kod, gt)
            assert v[0] == pytest.approx(tam[(gt, y)][0], abs=1e-9)
    assert toplam > 50


def test_hiz_5000_mum_12_formasyon():
    o, h, l, c = rw(5000, 5)
    idx = pd.date_range("2026-01-01", periods=5000, freq="1h", tz="UTC")
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1.0}, index=idx)
    inp = _core_inp(df, pair="HIZ/USDT")
    for kod in KODLAR:                                      # isinma
        arms.find_arm(f"MF1-{kod}").compute(inp)
    en_iyi = 1e9
    for r in range(3):
        df2 = df.copy()
        inp2 = _core_inp(df2, pair=f"HIZ{r}/USDT")
        t0 = time.perf_counter()
        for kod in KODLAR:
            arms.find_arm(f"MF1-{kod}").compute(inp2)
        en_iyi = min(en_iyi, time.perf_counter() - t0)
    assert en_iyi < 0.1, en_iyi       # ATR (5000 mum) bir kez + 12 dedektor; ortak onbellek kopya yapmaz


def test_aday_yoksa_ortak_bos_tablo():
    df = seri("YUTAN", bozuk=True)
    inp = _core_inp(df, pair="BOS/USDT")
    a = arms.find_arm("MF1-YUTAN").compute(inp)
    b = arms.find_arm("MF1-PINBAR").compute(inp)
    assert a is b


# ------------------------------------------------------------------------------------------------ kesif ve kimlik
def test_kesif_12_formasyon_sanal_kurulum():
    ls = arms.list_arms()
    assert "MF1" not in ls
    mf = [s for s in ls if s.startswith("MF1-")]
    assert sorted(mf) == sorted(f"MF1-{k}" for k in KODLAR)
    for k in KODLAR:
        m = arms.find_arm(f"MF1-{k}")
        assert m.TIMEFRAMES == TFS and m.CORE is False and m.EXIT_MODE == "target"
        assert set(m.FEATURES) == {"body_ratio", "wick_ratio", "rr", "f_seviye", "f_olcu_atr", "f_yas"}
        assert arms.exit_mode(f"MF1-{k}") == "target" and arms.features_of(f"MF1-{k}") == m.FEATURES
        assert arms.priority_of(f"MF1-{k}") == 300 + mf1.FORMASYONLAR[k].sira
        assert arms.exit_rule_of(f"MF1-{k}") is None
    assert arms.family_of("MF1-YUTAN") == "MF1" and arms.family_of("T1") == "T1"
    assert arms.parse_arm_id("MF1-YUTAN@1h") == ("MF1-YUTAN", "1h")
    assert sorted(mf1.FORMASYONLAR[k].sira for k in KODLAR) == list(range(1, 13))
    # mevcut kollar kutuphaneden once (en buyuk mevcut 95 < 300)
    assert max(arms.priority_of(s) for s in ls if "-" not in s) < 200


def test_kutuphane_ders_parametresi_okumaz():
    for dosya in ("_kutuphane.py", "mf1.py"):
        src = (ROOT / "src" / "trader_engine" / "strategies" / "arms" / dosya).read_text(encoding="utf-8")
        import re
        assert re.search(r"\bparams\.\w", src) is None and "SignalParams" not in src, dosya


def test_tireli_kod_yollari():
    assert L._setup_code("MF1-YUTAN") == "MF1-YUTAN"
    with pytest.raises(L.LedgerValidationError):
        L._setup_code("mf1-yutan")
    cfg = EM.build_config({"MF1-YUTAN@1h": {"breakeven": None, "partial": None}, "MF1-YUTAN": {}})
    assert "MF1-YUTAN@1h" in cfg
    with pytest.raises(EM.ExitModeError):
        EM.build_config({"MF1-@1h": {}})
    assert C._build_arms(["MF1-YUTAN@1h"]) == ("MF1-YUTAN@1h",)
    with pytest.raises(C.ConfigError):
        C._build_arms(["MF1-@1h"])
    assert C._build_arm_caps({"MF1-*": 3, "MF1-YUTAN": 2, "MF1-YUTAN@1h": 1, "default": 6})["MF1-*"] == 3
    with pytest.raises(C.ConfigError):
        C._build_arm_caps({"MF1-": 3})
    assert C._build_arm_family_caps({"MF1": 6}) == {"MF1": 6}
    for kotu in ({"mf1": 6}, {"MF1-YUTAN": 6}, {"MF1": 0}, [6]):
        with pytest.raises(C.ConfigError):
            C._build_arm_family_caps(kotu)


def test_arms_off_ve_karantina_tireli_kimlik(tmp_path):
    p = tmp_path / "arms_off.json"
    p.write_text(json.dumps({"arms": {"MF1-YUTAN@1h": {"state": "closed"}, "T1@1h": {"state": "open"}}}), encoding="utf-8")
    assert AG.load_arms_off(p) == frozenset({"MF1-YUTAN@1h"})
    from trader_engine.arm_quarantine import unit_for
    from trader_engine.strategies.lab import PriceActionLab
    lab = PriceActionLab(("MF1-YUTAN@1h", "MF1-PINBAR@1h"))
    assert unit_for(lab, "1h", "MF1-YUTAN") == ("MF1-YUTAN@1h", ["MF1-YUTAN@1h"])
    assert lab.info.setups == ("MF1-YUTAN", "MF1-PINBAR")


# ------------------------------------------------------------------------------------------------ tavanlar
def test_joker_formasyon_zd_tavani_ve_aile_tavani():
    caps = {"default": 6, "M1": 4, "MF1-*": 3}
    assert AG.arm_cap(caps, "MF1-YUTAN@1h", "MF1-YUTAN") == 3
    assert AG.arm_cap({**caps, "MF1-YUTAN": 2}, "MF1-YUTAN@1h", "MF1-YUTAN") == 2          # kurulum anahtari jokeri gecer
    assert AG.arm_cap({**caps, "MF1-YUTAN@1h": 1}, "MF1-YUTAN@1h", "MF1-YUTAN") == 1
    assert AG.arm_cap(caps, "T1@1h", "T1") == 6 and AG.arm_cap(caps, "M1@1h", "M1") == 4
    held = ["MF1-YUTAN@1h"] * 3
    assert AG.arm_full(held, "MF1-YUTAN@1h", 3)
    assert not AG.arm_full(held, "MF1-YUTAN@4h", 3)                                         # formasyon x ZD bazinda
    assert not AG.arm_full(held, "MF1-PINBAR@1h", 3)
    # aile tavani 6: formasyon ve ZD'lerden bagimsiz toplam
    setups = ["MF1-YUTAN"] * 3 + ["MF1-PINBAR"] * 2 + ["T1"] * 4 + [None]
    fc = {"MF1": 6}
    assert AG.family_count(setups, "MF1") == 5 and AG.family_full(setups, "MF1-DISBAR", fc) is None
    assert AG.family_full(setups + ["MF1-DELICI"], "MF1-DISBAR", fc) == "MF1"
    assert AG.family_full(setups + ["MF1-DELICI"], "T1", fc) is None and AG.family_full([], "MF1-X1", {}) is None


def test_aile_tavani_kapida_siradaki_aday_denenir():
    from trader_engine import gates as G
    from types import SimpleNamespace as NS
    out = NS(code="max_positions", event=NS(veto_reason="gate:arm_cap:MF1"))
    assert G.aday_ozgu_red(out) is True                      # aile tavani adaya ozgu: siradaki aday denenir


# ------------------------------------------------------------------------------------------------ on deger
def test_on_deger_dosyasi_bos_ve_mekanizma(tmp_path):
    """Kullanici karari: dosya bos (hepsi tam boy). Mekanizma: dosya doluysa yalniz kutuphane kolunda aile ortalamasi yerine."""
    assert json.loads((ROOT / "config" / "formasyon_on_deger.json").read_text(encoding="utf-8")) == {}
    assert FOD.yukle() == {} and FOD.r_of("MF1-YUTAN@1h") is None
    p = tmp_path / "od.json"
    p.write_text(json.dumps({"MF1-YUTAN@1h": {"r": -0.2, "n": 100}, "kotu": 1, "MF1-X@1h": {"r": "a"}}), encoding="utf-8")
    assert FOD.r_of("MF1-YUTAN@1h", p) == -0.2 and FOD.r_of("MF1-PINBAR@1h", p) is None and FOD.r_of("MF1-X@1h", p) is None
    assert FOD.yukle(tmp_path / "yok.json") == {}


def _kapi(ledger):
    from trader_engine.gates import EntryGate
    g = EntryGate.__new__(EntryGate)
    g.ledger = ledger
    return g


class _Def:
    def __init__(self, sonuc, aile):
        self.sonuc, self.aile = sonuc, aile

    def arm_recent_results(self, aid, n):
        return list(self.sonuc)

    def arm_family_mean_r(self, aid, D=None):
        return self.aile


def test_on_deger_kol_karari_bagli(tmp_path, monkeypatch):
    p = tmp_path / "od.json"
    p.write_text(json.dumps({"MF1-YUTAN@1h": {"r": -0.3, "n": 100}}), encoding="utf-8")
    monkeypatch.setattr(FOD, "DOSYA", p)
    bos = _kapi(_Def([], None))._kol_karari("MF1-YUTAN@1h")
    ref = _kapi(_Def([], -0.3))._kol_karari("MF1-YUTAN@1h")
    assert bos is not None and ref is not None and bos.carpan == ref.carpan < 1.0         # on deger eksi: kucuk baslar
    assert _kapi(_Def([], None))._kol_karari("MF1-PINBAR@1h").carpan == 1.0                 # on degersiz: tam boy
    assert _kapi(_Def([], 0.5))._kol_karari("MF1-YUTAN@1h").carpan == _kapi(_Def([], 0.5))._kol_karari("MF1-YUTAN@1h").carpan
    gercek = _kapi(_Def([], 0.5))._kol_karari("MF1-YUTAN@1h")                              # gercek aile verisi varsa on deger yok
    assert gercek.carpan == 1.0
    monkeypatch.setattr(FOD, "DOSYA", ROOT / "config" / "formasyon_on_deger.json")
    assert _kapi(_Def([], None))._kol_karari("MF1-YUTAN@1h").carpan == 1.0                 # gercek dosya bos: tam boy


# ------------------------------------------------------------------------------------------------ cikis
def _pos(setup, planned_target=None):
    from trader_engine.types import Position
    T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Position(trade_id=1, bot="learner", pair="BTC/USDT", side="long", setup=setup, status="open", decision_id=1,
                    signal_bar_close_ts=T0, entry_ts=T0, entry_bar_open=T0, entry_price=100.0, qty=1.0, leverage=3,
                    initial_stop=95.0, current_stop=95.0, stop_seq=0, stop_client_id=None, planned_target=planned_target,
                    trail_atr=None, param_version_id=1, trigger_tf="1h", risk_amount=10.0, margin=100.0, rh=None, rl=None,
                    fee_entry=0.0, funding_paid=0.0, mfe_price=100.0, mae_price=100.0, exit_reason=None, exit_client_id=None,
                    closed_ts=None)


def _ctx(n, rule=False, high=101.0):
    return ExitContext(bar_close_ts=datetime(2026, 1, 2, tzinfo=timezone.utc), highs=np.full(n, high), lows=np.full(n, 99.0),
                       atrs=np.full(n, 1.0), regime_last=None, last_close=100.0, n_closed=n, rule_exit=rule)


def test_cikis_zaman_stopu_hedef_ve_kural():
    assert evaluate_exit(_pos("MF1-YILDIZ", 109.0), _ctx(19)).kind == "none"
    d = evaluate_exit(_pos("MF1-YILDIZ", 109.0), _ctx(20))
    assert (d.kind, d.reason) == ("exit", "time_stop")                                   # YILDIZ 20. mumda
    assert evaluate_exit(_pos("MF1-YUTAN", 109.0), _ctx(20)).kind == "none"              # digerleri 48
    assert evaluate_exit(_pos("MF1-YUTAN", 109.0), _ctx(48)).reason == "time_stop"
    assert evaluate_exit(_pos("R1", 109.0), _ctx(47)).kind == "none" and evaluate_exit(_pos("R1", 109.0), _ctx(48)).reason == "time_stop"
    h = evaluate_exit(_pos("MF1-YUTAN", 109.0), _ctx(3, high=110.0))
    assert (h.reason, h.planned_exit) == ("target", 109.0)                                # hedef once
    k = evaluate_exit(_pos("MF1-YUTAN", 109.0), _ctx(3, rule=True))
    assert (k.kind, k.reason) == ("exit", "other")                                        # kural cikisi `other`
    assert evaluate_exit(_pos("R1", 109.0), _ctx(3, rule=False)).kind == "none"


def test_kural_cikisi_calistiricisi_hata_olursa_false(monkeypatch):
    from trader_engine import strategy_runner as SR
    monkeypatch.setattr(SR, "SignalParams", type("SP", (), {"from_mapping": staticmethod(lambda m: m)}))
    from trader_engine.strategy_runner import MultiArmSignalSource
    import dataclasses
    src = MultiArmSignalSource.__new__(MultiArmSignalSource)
    src.strict = False
    from collections import Counter
    src.counters = Counter()
    v = _ctx(3)
    assert src._rule_exit(v, None, "MF1-YUTAN", (None, None), None, {}, v.bar_close_ts) is v          # kural yok: ayni gorunum

    class Sahte:
        pass
    # kurala sahip sanal kurulum: hata olursa False kalir + sayac
    mod = arms.find_arm("MF1-YUTAN")
    orig = getattr(mod, "EXIT_RULE")
    try:
        mod.EXIT_RULE = lambda inp: 1 / 0
        out = src._rule_exit(v, Sahte(), "MF1-YUTAN", (pd.DataFrame(), Sahte()), None, {}, v.bar_close_ts)
        assert out.rule_exit is False and src.counters["exit_rule_error"] == 1
        mod.EXIT_RULE = lambda inp: True
        trig = seri("YUTAN")
        ctx = type("C", (), {"pair": "X/USDT", "tf": "1h"})()
        lab = type("L", (), {"_core_compact": lambda self, c: None})()
        out = src._rule_exit(v, lab, "MF1-YUTAN", (trig, ctx), None, {}, v.bar_close_ts)
        assert out.rule_exit is True and dataclasses.is_dataclass(out)
    finally:
        mod.EXIT_RULE = orig


# ------------------------------------------------------------------------------------------------ kagit = canli
def _cfg(ad):
    return json.loads((ROOT / "config" / ad).read_text(encoding="utf-8"))


def test_kagit_canli_ayni_ve_mf1_48_kimlik():
    p, l = _cfg("engine.paper.json"), _cfg("engine.live.json")
    for k in ("arms", "arm_max_positions", "arm_family_max_positions"):
        assert p[k] == l[k], k
    assert p["arm_family_max_positions"]["MF1"] == p["arm_family_max_positions"]["PA2"] == 6 and p["arm_max_positions"]["MF1-*"] == 3   # 24.11 kullanici karari: formasyon kutuphanesi (PA2 aile 6)
    lib = [a for a in p["arms"] if a.startswith("MF1-")]
    beklenen = [f"{s}@{tf}" for s in sorted(a for a in arms.list_arms() if a.startswith("MF1-")) for tf in TFS]
    assert sorted(lib) == sorted(beklenen) and len(lib) == 48 and len(set(p["arms"])) == len(p["arms"])
    for ad in ("engine.paper.json", "engine.live.json"):
        cfg = C.load_cli_config(ROOT / "config", "learner", ad.split(".")[1])
        assert cfg.arm_family_max_positions["MF1"] == cfg.arm_family_max_positions["PA2"] == 6 and cfg.arm_max_positions["MF1-*"] == 3   # 24.11 kullanici karari: formasyon kutuphanesi
        assert all(a in cfg.arms for a in beklenen)


def test_telegram_adlari_tireli_kod():
    from trader_core import tg_sade
    for k in KODLAR:
        ad = tg_sade.kurulum_adi(f"MF1-{k}@1h")
        assert ad.startswith("Mum: ") and ad != f"MF1-{k}", k
    assert tg_sade.kurulum_adi("MF1-YUTAN") == "Mum: yutan"
    assert "Mum: yutan" in tg_sade.kol_adi("MF1-YUTAN@1h")
