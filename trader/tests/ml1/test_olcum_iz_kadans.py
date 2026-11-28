"""P1-c: `iz_kadans` karsi-olgusu (iz suren stop / zaman cikisi 1, 5, 15 dk kadansla guncellenirse)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("pyarrow")

from olcum_destek import D0, Gorunum, islem, sahte_ogren, seri_1dk, seri_bos  # noqa: E402
from trader_engine import ml1_sanal as SN  # noqa: E402
from trader_engine import olcumler as OL  # noqa: E402

MAL0 = SN.Maliyet(0.0, 0.0, 0.0, 0.0)


def _rec(**kw):
    d = {"side": "long", "tf": "1h", "mod": "trail", "stop": 99.0, "target": None, "entry_ref": 100.0, "decision_ts": D0.isoformat(),
         "time_stop": None, "trail_atr": 1.0}
    d.update(kw)
    return d


def _trig(rejim="range"):
    idx = pd.date_range(D0 - pd.Timedelta(hours=5), periods=20, freq="1h", tz="UTC")
    return pd.DataFrame({"high": 100.0, "low": 100.0, "close": 100.0, "atr_tf": 1.0, "regime": rejim}, index=idx)


def _hepsi(rec, m1, trig=None):
    trig = _trig() if trig is None and rec["mod"] == "trail" else trig
    return {k: OL.kadans_simule(rec, m1, trig, MAL0, [], k) for k in (1, 5, 15)}


def _yol(*parcalar):
    """[(hedef_fiyat, dakika), ...] dogrusal parcalardan kapanis dizisi."""
    out, cur = [], parcalar[0][0]
    for hedef, n in parcalar[1:]:
        out += list(np.linspace(cur, hedef, n + 1)[1:])
        cur = hedef
    return [parcalar[0][0]] + out


def test_dogrudan_yukselis_sert_donus_sik_guncelleme_erken_sikilastirir():
    # 0..15 dk: 100 -> 103; 16-17: 105 (tepe 15 dk izgarasindan SONRA); 18: sert dusus 100
    kap = _yol((100.0, 0), (103.0, 15)) + [105.0, 105.0, 100.0, 100.0, 100.0, 100.0]
    r = _hepsi(_rec(), seri_1dk(kap))
    assert r[1]["neden"] == "trail_stop" and r[15]["neden"] == "trail_stop"
    assert r[1]["r"] > r[15]["r"] > 1.0


def test_testere_sik_guncelleme_erken_stop_eder():
    kap = [100.0, 100.7, 101.4, 102.0, 100.9] + list(np.linspace(101.0, 106.0, 10)) + list(np.linspace(106.0, 110.0, 12)) + [100.0] * 6
    r = _hepsi(_rec(), seri_1dk(kap))
    assert r[1]["r"] < r[15]["r"]
    assert 0.5 < r[1]["r"] < 1.0 and r[1]["neden"] == "trail_stop"                  # stop ~101,05 (planli risk maliyetli: 1R > 1 fiyat birimi)


def test_iz_esigine_ulasilmiyor_uc_varyant_ayni():
    kap = [100.0, 100.4, 100.1, 100.5, 99.8, 100.2, 99.5] + [98.0] * 20
    r = _hepsi(_rec(), seri_1dk(kap, genislik=0.01))
    assert {x["neden"] for x in r.values()} == {"stop"}
    assert len({round(x["r"], 9) for x in r.values()}) == 1 and r[1]["r"] < 0


def test_hedef_kipi_zaman_stopu_ayni_dakika():
    m1 = seri_1dk([100.0] * 260)
    rec = _rec(mod="target", target=500.0, stop=50.0, time_stop=2)
    r = _hepsi(rec, m1)
    assert {x["neden"] for x in r.values()} == {"time_stop"}
    assert {x["cikis_ts"] for x in r.values()} == {D0 + pd.Timedelta(hours=2)}
    row = {"mod": "target", **{f"r_{k}": x["r"] for k, x in r.items()}, **{f"neden_{k}": x["neden"] for k, x in r.items()},
           **{f"cikis_{k}": x["cikis_ts"] for k, x in r.items()}}
    assert OL._iz_ozet_grup([row])["zaman_farki"] == 0


def test_15dk_varyanti_sanal_simule_ile_ayni_neden():
    for kap, rec in (([100.0] * 260, _rec(mod="target", target=500.0, stop=50.0, time_stop=2)),
                     ([100.0] * 10 + [97.0] * 30, _rec(mod="target", target=500.0, stop=99.0, time_stop=48)),
                     ([100.0] * 10 + [103.0] * 30, _rec(mod="target", target=102.0, stop=99.0, time_stop=48))):
        m1 = seri_1dk(kap)
        k15 = OL.kadans_simule(rec, m1, None, MAL0, [], 15)
        v = Gorunum({"P": m1})
        b15 = v.bars("P", "15m", D0 + pd.Timedelta(days=3))
        ref = SN.simule(rec, b15, None, MAL0, [], D0 + pd.Timedelta(days=40))
        assert k15 is not None and ref is not None and k15["neden"] == ref.exit_reason


def test_delik_veri_eksik(tmp_path):
    m1 = seri_bos(seri_1dk([100.0] * 300), [30, 31])
    isl = islem(setup="R1", exit_ts=D0 + pd.Timedelta(hours=2))
    y = OL.OlcumYonetici(tmp_path / "o", now_fn=lambda: D0, ml1_cfg={}, view=Gorunum({"BTC/USDT": m1}), ogren=sahte_ogren(isl),
                         maliyet_fn=lambda p, t: MAL0, trail_atr_fn=lambda: 1.0)
    assert OL._iz_kadans(y, isl, D0 + pd.Timedelta(hours=6)) == {"durum": "veri_eksik"}
    ilk = seri_bos(seri_1dk([100.0] * 300), [0])                                 # karar mumu yok
    y.view = Gorunum({"BTC/USDT": ilk})
    assert OL._iz_kadans(y, isl, D0 + pd.Timedelta(hours=6)) == {"durum": "veri_eksik"}


def _ayna(df):
    return pd.DataFrame({"open": 200 - df["open"], "high": 200 - df["low"], "low": 200 - df["high"], "close": 200 - df["close"], "volume": 1.0}, index=df.index)


def test_short_simetri():
    for kap in ([100.0, 100.7, 101.4, 102.0, 100.9] + list(np.linspace(101.0, 106.0, 10)) + list(np.linspace(106.0, 110.0, 12)) + [100.0] * 6,
                _yol((100.0, 0), (103.0, 15)) + [105.0, 105.0, 100.0, 100.0, 100.0, 100.0]):
        m1 = seri_1dk(kap)
        uzun = _hepsi(_rec(), m1)
        kisa = _hepsi(_rec(side="short", stop=101.0, entry_ref=100.0), _ayna(m1), trig=_ayna_trig())
        for k in (1, 5, 15):
            assert kisa[k]["r"] == pytest.approx(uzun[k]["r"], rel=5e-3)         # planli risk (ucretli) long/short icin ufak asimetrik and kisa[k]["neden"] == uzun[k]["neden"]


def _ayna_trig():
    t = _trig()
    return pd.DataFrame({"high": 200 - t["low"], "low": 200 - t["high"], "close": 200 - t["close"], "atr_tf": t["atr_tf"], "regime": t["regime"]}, index=t.index)


def test_ozet_eslesik_t_ve_farklar_elle():
    r1, r5, r15 = [1.0, 2.0, 0.0, 3.0], [0.5, 1.0, 0.0, 2.0], [0.0, 1.0, 0.5, 1.0]
    rows = [{"mod": "trail", "r_1": a, "r_5": b, "r_15": c, "neden_1": "x", "neden_5": "x", "neden_15": "x"} for a, b, c in zip(r1, r5, r15)]
    oz = OL._iz_ozet(None, rows + [{"durum": "veri_eksik"}])
    t = oz["tumu"]
    d1 = np.array(r1) - np.array(r15)                                           # [1, 1, -0.5, 2]
    d5 = np.array(r5) - np.array(r15)                                           # [0.5, 0, -0.5, 1]
    assert t["n"] == 4 and oz["veri_eksik"] == 1
    assert t["fark_1_15"] == pytest.approx(d1.mean()) and t["fark_5_15"] == pytest.approx(d5.mean())
    assert t["t_1_15"] == pytest.approx(d1.mean() / (d1.std(ddof=1) / math.sqrt(4)), abs=1e-5)
    assert t["t_5_15"] == pytest.approx(d5.mean() / (d5.std(ddof=1) / math.sqrt(4)), abs=1e-5)
    assert t["ort_r_15"] == pytest.approx(np.mean(r15)) and t["kazanma_1"] == pytest.approx(0.75)
    assert oz["trail"]["n"] == 4 and oz["target"]["n"] == 0 and oz["target"]["t_1_15"] is None
