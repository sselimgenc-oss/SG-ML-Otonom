"""HB1 haber kolu (ust lig): sinyal dosyasi -> aday; yok/bozuk/bayat/sizinti -> aday yok; parite; kol tavani."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core import haber_sinyal as HS
from trader_core.signals import SIGNAL_COLUMNS
from trader_engine.strategies.arms import ArmInput, discover, exit_mode, find_arm
import trader_engine.strategies.arms.hb1 as HB1

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc
D = datetime(2026, 11, 24, 13, 0, tzinfo=UTC)          # karar zamani = son 1s mumun kapanisi
H = 3_600_000


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _belge(uretim, ens, **kw):
    b = {"schema": HS.SEMA, "uretim_ms": _ms(uretim), "gecerlilik_sonu_ms": _ms(uretim) + 3 * H, "enstrumanlar": ens}
    b.update(kw)
    return b


GUCLU = {"puan": 1.2, "kaynak_sayisi": 2, "teyit_kaynak": 2, "max_siddet": 2, "oge_sayisi": 2, "olay_kimligi": 7}


@pytest.fixture
def sinyal(tmp_path, monkeypatch):
    yol = tmp_path / "haber_sinyal.json"
    monkeypatch.setattr(HB1, "SINYAL_YOLU", yol)
    HB1.COUNTERS.clear()
    HB1._ONBELLEK.update(key=None, belge=None, neden=None)

    def yaz(belge):
        yol.write_text(belge if isinstance(belge, str) else json.dumps(belge), encoding="utf-8")
        HB1._ONBELLEK.update(key=None)
        return yol
    yaz.yol = yol
    return yaz


def _inp(pair="BTC/USDT", yon_yukari=True, n=80, D_=D):
    idx = pd.DatetimeIndex([D_ - timedelta(hours=n - k) for k in range(n)])
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 0.5, n))
    o = np.r_[c[0], c[:-1]]
    c[-1] = o[-1] + (0.8 if yon_yukari else -0.8)
    h = np.maximum(o, c) + 0.4
    lo = np.minimum(o, c) - 0.4
    trig = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)

    def core():
        t = pd.DataFrame(index=idx, columns=SIGNAL_COLUMNS)
        t["regime"] = "none"
        t["signal"] = False
        t["pullback_ema"] = 0
        return t
    return ArmInput(pair=pair, tf="1h", D=D_, trig=trig, h4=trig, params=None, core_fn=core)


def _son(out):
    return out.iloc[-1]


def test_kontrat_ve_kimlik():
    m = discover(refresh=True)["HB1"]
    assert m.TIMEFRAMES == ("1h",) and m.EXIT_MODE == "target" and exit_mode("HB1") == "target" and find_arm("HB1") is m
    assert m.ESIK_PUAN == 0.6 and m.MIN_KAYNAK == 2 and m.SIDDET_YETERLI == 3 and m.SIZINTI_MARJ_S == 60


def test_taze_guclu_sinyal_ve_mum_long_aday(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": GUCLU}))
    out = HB1.compute(_inp())
    r = _son(out)
    assert bool(r["signal"]) and r["setup"] == "HB1" and r["side"] == "long"
    assert r["planned_stop"] < r["planned_entry"] < r["planned_target"]
    atr_stop = r["planned_entry"] - r["planned_stop"]
    assert (r["planned_target"] - r["planned_entry"]) == pytest.approx(2 * atr_stop)   # stop 1,5 ATR, hedef 3 ATR
    assert r["rr"] == pytest.approx(2.0) and not out.iloc[:-1]["signal"].any()


def test_negatif_puan_ve_dusen_mum_short_aday(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"ETH/USDT": {"puan": -1.0, "kaynak_sayisi": 1, "teyit_kaynak": 1, "max_siddet": 3, "oge_sayisi": 1, "olay_kimligi": 9}}))
    r = _son(HB1.compute(_inp("ETH/USDT", yon_yukari=False)))
    assert bool(r["signal"]) and r["side"] == "short" and r["planned_target"] < r["planned_entry"] < r["planned_stop"]


@pytest.mark.parametrize("satir", [
    {"puan": 0.59, "kaynak_sayisi": 3, "teyit_kaynak": 3, "max_siddet": 3, "oge_sayisi": 3, "olay_kimligi": 7},     # esik alti
    {"puan": 1.5, "kaynak_sayisi": 1, "teyit_kaynak": 1, "max_siddet": 2, "oge_sayisi": 1, "olay_kimligi": 7},      # tek kaynak, siddet < 3
])
def test_zayif_ya_da_tek_kaynak_aday_yok(sinyal, satir):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": satir}))
    assert not _son(HB1.compute(_inp()))["signal"]


def test_mum_ters_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": GUCLU}))            # long sinyali, mum asagi kapanmis
    assert not _son(HB1.compute(_inp(yon_yukari=False)))["signal"]
    assert HB1.COUNTERS["mum_ters"] == 1


def test_enstruman_dosyada_yok_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"ETH/USDT": GUCLU}))
    assert not _son(HB1.compute(_inp("BTC/USDT")))["signal"]


def test_bayat_dosya_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(hours=3, minutes=1), {"BTC/USDT": GUCLU}))
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["bayat"] == 1


def test_gecerlilik_alani_uzatilsa_da_uretim_arti_3_saat_tavan(sinyal):
    sinyal(_belge(D - timedelta(hours=4), {"BTC/USDT": GUCLU}, gecerlilik_sonu_ms=_ms(D) + 10 * H))
    assert not _son(HB1.compute(_inp()))["signal"]


def test_sizinti_mum_kapanisi_uretimden_once_ya_da_60sn_icinde(sinyal):
    for fark in (timedelta(minutes=-5), timedelta(seconds=-30), timedelta(0), timedelta(seconds=-60)):   # uretim = D - fark
        sinyal(_belge(D - fark, {"BTC/USDT": GUCLU}))
        assert not _son(HB1.compute(_inp()))["signal"], fark
    sinyal(_belge(D - timedelta(seconds=61), {"BTC/USDT": GUCLU}))
    assert bool(_son(HB1.compute(_inp()))["signal"])
    assert HB1.COUNTERS["sizinti"] == 4


@pytest.mark.parametrize("icerik", [None, "{bozuk json", "[]", json.dumps({"schema": "x/9", "uretim_ms": 1}),
                                    json.dumps({"schema": HS.SEMA, "uretim_ms": "a", "gecerlilik_sonu_ms": 2, "enstrumanlar": {}}),
                                    json.dumps({"schema": HS.SEMA, "uretim_ms": 1, "gecerlilik_sonu_ms": 2, "enstrumanlar": []})])
def test_yok_bozuk_sema_disi_dosya_aday_yok_istisna_yok(sinyal, icerik):
    if icerik is not None:
        sinyal(icerik)
    out = HB1.compute(_inp())
    assert list(out.columns) == SIGNAL_COLUMNS and len(out) == 80 and not out["signal"].any()
    assert sum(HB1.COUNTERS.values()) == 1


def test_bozuk_satir_aday_yok(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": {"puan": "yuksek", "kaynak_sayisi": 2, "max_siddet": 3}}))
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["satir_bozuk"] == 1


def test_hb1_sinyal_sozlesmesi_uretici_ile_ayni():
    """Motor trader_core.haber_sinyal'i ice aktarmaz; sabitler elle kopyalandi, burada esitlik sinanir."""
    from trader_core import haber_sinyal as HS
    from trader_engine.strategies.arms import hb1
    assert (hb1.HS_SEMA, hb1.HS_GECERLILIK_SAAT, hb1.HS_PUAN_SINIR, hb1.HS_H_MS, hb1.HS_CIKTI_DOSYASI) == \
        (HS.SEMA, HS.GECERLILIK_SAAT, HS.PUAN_SINIR, HS.H_MS, HS.CIKTI_DOSYASI)


# ============================================================ 23.11 inceleme duzeltmeleri
def _s(puan=1.2, k=2, sid=2, teyit=None, kimlik=7, **kw):
    r = {"puan": puan, "kaynak_sayisi": k, "teyit_kaynak": k if teyit is None else teyit, "max_siddet": sid, "oge_sayisi": 2, "olay_kimligi": kimlik}
    r.update(kw)
    return r


def test_sozlesme_sabitleri_yeniden_sonumleme_dahil_uretici_ile_ayni():
    from trader_core import haber_sinyal as HS_
    assert HB1.HS_SEMA == HS_.SEMA == "haber_sinyal/2"
    assert (HB1.HS_PENCERE_SAAT, HB1.HS_YARI_OMUR_SAAT) == (HS_.PENCERE_SAAT, HS_.YARI_OMUR_SAAT)


def test_teyit_bir_olumlu_bir_etkisiz_farkli_kaynak_giris_yok(sinyal):
    """Gercek uretici ciktisi: olumlu(a) + etkisiz(b): kaynak_sayisi 2 ama teyit 1 -> siddet < 3 iken giris yok."""
    def ev(yon, sid, kay, n=0):
        return {"baslik": f"h{kay}{n}", "alim": _ms(D - timedelta(minutes=70)), "kaynaklar": [kay], "semboller": ["BTC/USDT"], "yon": yon,
                "siddet": sid, "guven": 1.0, "ufuk_saat": 24}
    uret = _ms(D - timedelta(minutes=50))
    belge = HS.sinyal_belgesi([ev(1, 2, "a"), ev(1, 2, "a", 1), ev(0, 0, "b")], uret)
    assert belge["enstrumanlar"]["BTC/USDT"]["kaynak_sayisi"] == 2 and belge["enstrumanlar"]["BTC/USDT"]["teyit_kaynak"] == 1
    sinyal(belge)
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["tek_kaynak"] == 1
    # siddet 3 ise tek yonlu kaynak yeter; iki yonlu kaynak da yeter
    sinyal(HS.sinyal_belgesi([ev(1, 3, "a"), ev(0, 0, "b")], uret))
    assert bool(_son(HB1.compute(_inp()))["signal"])
    sinyal(HS.sinyal_belgesi([ev(1, 2, "a"), ev(1, 2, "b")], uret))
    assert bool(_son(HB1.compute(_inp()))["signal"])


def test_kol_teyit_kaynak_alanini_kullanir_kaynak_sayisini_degil(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": _s(k=2, teyit=1, sid=2)}))
    assert not _son(HB1.compute(_inp()))["signal"]
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": _s(k=2, teyit=2, sid=2)}))
    assert bool(_son(HB1.compute(_inp()))["signal"])


def test_yeniden_sonumleme_ufku_asan_olay_karar_aninda_dusurulur(sinyal):
    """Uretimde (D-50dk) taze olan, ufku 1 saat olan olay D'de 70 dk yasinda: puan 0 -> aday yok (dosya puani eski kalsa da)."""
    olay = {"baslik": "x", "alim": _ms(D - timedelta(minutes=70)), "kaynaklar": ["a", "b"], "semboller": ["BTC/USDT"], "yon": 1, "siddet": 3,
            "guven": 1.0, "ufuk_saat": 1.0}
    belge = HS.sinyal_belgesi([olay], _ms(D - timedelta(minutes=50)))
    assert belge["enstrumanlar"]["BTC/USDT"]["puan"] > 0.6
    sinyal(belge)
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["esik_alti"] == 1


def test_yeniden_sonumleme_puan_karar_zamaninda_hesaplanir():
    olay = {"alim_ms": _ms(D) - 2 * H, "yon": 1, "siddet": 3, "guven": 1.0, "ufuk_saat": 24, "kaynaklar": ["a"], "kimlik": 5}
    s = _s(puan=1.0, olaylar=[olay])
    assert HB1.yeniden_sonumle(s, _ms(D))["puan"] == pytest.approx(0.5)          # 2 saat = yari omur
    assert HB1.yeniden_sonumle(s, _ms(D) + 4 * H)["puan"] == pytest.approx(0.125)  # 6 saat sinirinda hala canli
    assert HB1.yeniden_sonumle(s, _ms(D) + 5 * H)["puan"] == 0.0 and HB1.yeniden_sonumle(s, _ms(D) + 5 * H)["olay_kimligi"] == 0


def test_olaysiz_dosyada_sinyal_yasi_90_dk_siniri(sinyal):
    assert HB1.MAX_SINYAL_YASI_DK == 90
    sinyal(_belge(D - timedelta(minutes=91), {"BTC/USDT": _s()}))
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["eski_sinyal"] == 1
    sinyal(_belge(D - timedelta(minutes=90), {"BTC/USDT": _s()}))                 # tam sinirda hala gecerli
    assert bool(_son(HB1.compute(_inp()))["signal"])
    sinyal(_belge(D - timedelta(minutes=52), {"BTC/USDT": _s()}))                 # normal akis
    assert bool(_son(HB1.compute(_inp()))["signal"])


def test_olay_kimligi_ml_ozelligine_yazilmaz(sinyal):
    """Olay kimligi edge_dist_atr tasiyicisina yazilmaz (suzgec ozelligi bozulmasin)."""
    assert "hb1_olay" not in HB1.FEATURES and "edge_dist_atr" not in HB1.FEATURES.values()
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": _s(kimlik=3_000_000_001)}))
    r = _son(HB1.compute(_inp()))
    assert bool(r["signal"]) and np.isnan(r["edge_dist_atr"])


def test_kapi_duzeyi_hb1_tavani_3_dorduncu_aday_reddedilir():
    import json as _j
    from trader_engine import arm_guard as AG
    caps = _j.loads((ROOT / "config" / "engine.paper.json").read_text())["arm_max_positions"]
    assert AG.arm_cap(caps, "HB1@1h", "HB1") == 3 and AG.arm_cap(caps, "M1@1h", "M1") == 4
    assert not AG.arm_full(["HB1@1h"] * 2, "HB1@1h", 3)
    assert AG.arm_full(["HB1@1h"] * 3, "HB1@1h", 3)                                 # 4. aday: kapi dolu
    assert not AG.arm_full(["HB1@1h"] * 3 + ["M1@1h"], "M1@1h", 4)                    # tavan kola ozel, paylasilmaz


def test_motor_hb1_dorduncu_giris_reddedilir(tmp_path):
    import test_dd12_wp11_spec as W
    pairs = W.PAIRS5
    over = W._engine_over(pairs, arms=["HB1@1h"], arm_max_positions={"HB1": 3})
    e = W._E(tmp_path, pairs, W.D_E - timedelta(hours=1), over)
    try:
        for p, yon in zip(pairs[:4], ("long", "short", "long", "short")):      # ayni-yon risk siniri tavani degil, HB1 tavani olculur
            kw = {} if yon == "long" else {"side": "short", "planned_stop": 102.0, "regime": "trend_down"}
            W._signal_arm(e, W.D_E, p, "HB1@1h", setup="HB1", wick_ratio=0.2, rr=2.0, edge_dist_atr=12345.0, **kw)
        e.decide(W.D_E)
        e.step(W.D_E)
        acik = [p for p in pairs[:4] if e.state.position_for_pair(p) is not None]
        assert len(acik) == 3, acik
        dorduncu = [p for p in pairs[:4] if p not in acik][0]
        rows = W._ledger_rows(e, f"SELECT final_action, skip_reason, veto_reason FROM decision_events WHERE pair='{dorduncu}'")
        assert rows[-1][0] == "skipped" and rows[-1][1] == "max_positions" and "arm_cap:HB1@1h" in rows[-1][2], rows
    finally:
        e.close()


def test_uretici_ciktisi_kolda_uctan_uca(sinyal):
    """Gercek sinyal_belgesi cikti dosyaya yazilir, kol compute'u bunu okur: iki farkli kaynak, ayni yon."""
    def ev(kay, dk):
        return {"baslik": f"BTC rallies {kay}", "alim": _ms(D - timedelta(minutes=dk)), "kaynaklar": [kay], "semboller": ["BTC/USDT"],
                "yon": 1, "siddet": 2, "guven": 0.9, "ufuk_saat": 12}
    belge = HS.sinyal_belgesi([ev("a", 80), ev("b", 60)], _ms(D - timedelta(minutes=52)))
    sinyal(belge)
    r = _son(HB1.compute(_inp()))
    assert bool(r["signal"]) and r["side"] == "long"
    assert np.isnan(r["edge_dist_atr"])                    # olay kimligi ML ozelligine yazilmaz
    assert HB1.COUNTERS["aday"] == 1


def test_varsayilan_sinyal_yolu_ureticinin_varsayilan_yoluyla_ayni(monkeypatch):
    """Kol SINYAL_YOLU (repo koku/var/learner/sinyal/<dosya>), uretici kos(var_dir=<repo>/var) ile ayni goreli yolu yazar."""
    import importlib
    monkeypatch.delenv("TRADER_HABER_SINYAL", raising=False)
    m = importlib.reload(HB1)
    try:
        rel = m.SINYAL_YOLU.relative_to(m._REPO_ROOT / "var")
        assert rel == Path("learner") / "sinyal" / HS.CIKTI_DOSYASI
        # ureticinin varsayilan yolu: betik --var-dir varsayilani = <trader>/var; kos() cikti = var_dir/learner/sinyal/CIKTI_DOSYASI
        assert m._REPO_ROOT / "var" == ROOT / "var"
        assert 'default=ROOT / "var"' in (ROOT / "scripts" / "haber_sinyal_run.py").read_text()
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            HS._yaz(Path(td) / "learner" / "sinyal" / HS.CIKTI_DOSYASI, {})
            assert (Path(td) / rel).exists()
    finally:
        importlib.reload(HB1)


def test_sizinti_siniri_tam_esitlik_ve_bir_ms_otesi(sinyal):
    uret = D - timedelta(seconds=HB1.SIZINTI_MARJ_S)                       # D == uretim + 60 sn: sizinti (D_ms <= ...)
    sinyal(_belge(uret, {"BTC/USDT": _s()}))
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["sizinti"] == 1
    sinyal(_belge(uret - timedelta(milliseconds=1), {"BTC/USDT": _s()}))   # 1 ms otesi: gecer
    assert bool(_son(HB1.compute(_inp()))["signal"])


@pytest.mark.parametrize("deger", ["NaN", "Infinity", "-Infinity"])
def test_nan_inf_puan_reddedilir(sinyal, deger):
    ham = json.dumps(_belge(D - timedelta(minutes=50), {"BTC/USDT": _s()})).replace('"puan": 1.2', f'"puan": {deger}')
    assert deger in ham
    sinyal(ham)
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["satir_bozuk"] == 1


def test_eski_sema_v1_reddedilir(sinyal):
    sinyal(_belge(D - timedelta(minutes=50), {"BTC/USDT": GUCLU}, schema="haber_sinyal/1"))
    assert not _son(HB1.compute(_inp()))["signal"] and HB1.COUNTERS["sema"] == 1


def test_bozuk_dosya_digeri_yalitimi_gercek(sinyal):
    """Gercek yalitim: HB1 bozuk dosyada bos doner VE ortak/diger kolun sayaclari ve onbellegi etkilenmez; M1 kendi sinyal kaynagini kullanir."""
    import trader_engine.strategies.arms.m1 as M1
    sinyal("{bozuk")
    m1_once = dict(getattr(M1, "COUNTERS", {}))
    out = HB1.compute(_inp())
    assert not out["signal"].any() and HB1.COUNTERS["bozuk"] == 1
    assert dict(getattr(M1, "COUNTERS", {})) == m1_once                    # HB1 hatasi M1 sayaclarina yansimaz
    assert not hasattr(M1, "SINYAL_YOLU") and getattr(M1, "_ONBELLEK", None) is not HB1._ONBELLEK
    # tersi: M1 calisir ve HB1 durumu degismez
    M1.compute(_inp())
    assert HB1.COUNTERS["bozuk"] == 1 and sum(HB1.COUNTERS.values()) == 1
