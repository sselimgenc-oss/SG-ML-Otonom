"""DL1 kolu (ust lig): paket -> aday (dort zaman dilimi: 15m/1h/4h/1d); paket yok/bozuk/hash -> aday yok (sayac); kapisiz ve eski paket ISLEM YAPAR (24.11);
esik; kapsam (43 enstruman); seans bosluklari; sizinti."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from trader_core.signals import SIGNAL_COLUMNS
from trader_engine import dl1_cikarim as DL
from trader_engine.strategies.arms import ArmInput, discover, exit_mode, find_arm, priority_of
import trader_engine.strategies.arms.dl1 as DL1

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dl1_support as S  # noqa: E402

UTC = timezone.utc
D = datetime(2026, 11, 24, 13, 0, tzinfo=UTC)


@pytest.fixture
def paket(tmp_path, monkeypatch):
    yol = tmp_path / "DL1@1h.json"
    monkeypatch.setattr(DL, "PAKET_DIZINI", tmp_path)
    DL._ONBELLEK.clear()
    DL1.COUNTERS.clear()
    DL1._ONBELLEK.clear()
    DL1._LOG.clear()

    def yaz(bl=2.0, bs=-2.0, esik=0.5, olusturma=None, tf="1h", **kw):
        ag = S.sifir_agirlik(bl, bs)
        yol_tf = tmp_path / f"DL1@{tf}.json"
        S.yaz(yol_tf, S.paket_sozlugu(olusturma or D - timedelta(days=1), esik=esik, agirlik=ag, tf=tf, **kw))
        DL._ONBELLEK.clear()
        DL1._ONBELLEK.clear()
        return yol_tf
    yaz.yol = yol
    return yaz


def _inp(pair="BTC/USDT", yukari=True, n=300, D_=D, trig=None, tf="1h"):
    trig = S.seri(D_, n, yukari=yukari, tf=tf) if trig is None else trig
    idx = trig.index

    def core():
        t = pd.DataFrame(index=idx, columns=SIGNAL_COLUMNS)
        t["regime"] = "none"
        t["signal"] = False
        t["pullback_ema"] = 0
        return t
    return ArmInput(pair=pair, tf=tf, D=D_, trig=trig, h4=trig, params=None, core_fn=core)


def _son(out):
    return out.iloc[-1]


def test_kontrat_ve_kimlik():
    m = discover(refresh=True)["DL1"]
    assert m.TIMEFRAMES == ("15m", "1h", "4h", "1d") == DL.ZAMAN_DILIMLERI and m.EXIT_MODE == "target" and exit_mode("DL1") == "target" and find_arm("DL1") is m
    assert m.PRIORITY == 95 and priority_of("DL1") == 95 and priority_of("M1") < priority_of("DL1")


def test_esik_ustu_long_aday(paket):
    paket(bl=2.0, bs=-2.0)
    out = DL1.compute(_inp())
    r = _son(out)
    assert bool(r["signal"]) and r["setup"] == "DL1" and r["side"] == "long"
    assert r["planned_stop"] < r["planned_entry"] < r["planned_target"]
    assert (r["planned_target"] - r["planned_entry"]) == pytest.approx(2 * (r["planned_entry"] - r["planned_stop"]))   # stop 1,5 ATR, hedef 3 ATR
    assert r["rr"] == pytest.approx(2.0) and not out.iloc[:-1]["signal"].any() and DL1.COUNTERS["aday@1h"] == 1


def test_yon_secimi_en_yuksek_puan_short(paket):
    paket(bl=1.0, bs=3.0)
    r = _son(DL1.compute(_inp("NVDA/USDT")))
    assert bool(r["signal"]) and r["side"] == "short" and r["planned_target"] < r["planned_entry"] < r["planned_stop"]


def test_esik_alti_aday_yok(paket):
    paket(bl=-1.0, bs=-1.0, esik=0.9)
    assert not _son(DL1.compute(_inp()))["signal"] and DL1.COUNTERS["esik_alti@1h"] == 1


def test_esik_paketten_gelir(paket):
    paket(bl=0.0, bs=-5.0, esik=0.5)           # p_long = 0,5 >= 0,5
    assert bool(_son(DL1.compute(_inp()))["signal"])
    paket(bl=0.0, bs=-5.0, esik=0.51)
    assert not _son(DL1.compute(_inp()))["signal"]


def test_paket_yok_aday_yok_sayac(paket):
    out = DL1.compute(_inp())
    assert not out["signal"].any() and DL1.COUNTERS["paket_yok@1h"] == 1 and list(out.columns) == list(SIGNAL_COLUMNS)


def test_paket_eski_yine_islem_yapar_uyari_sayaci(paket, caplog):
    """24.11: 45 gunden yasli paket ENGELLENMEZ (aday uretir); yalniz uyari sayaci + paket basina tek WARNING."""
    import logging
    paket(olusturma=D - timedelta(days=200))
    with caplog.at_level(logging.WARNING, logger="trader.dl1"):
        assert bool(_son(DL1.compute(_inp()))["signal"])
        DL1._ONBELLEK.clear()
        assert bool(_son(DL1.compute(_inp()))["signal"])
    assert DL1.COUNTERS["paket_eski_uyari@1h"] == 2 and "paket_eski@1h" not in DL1.COUNTERS and DL1.COUNTERS["aday@1h"] == 2
    assert len([r for r in caplog.records if "paketi eski" in r.message]) == 1


def test_paket_hash_tutmuyor_ve_bozuk_aday_yok(paket):
    yol = paket()
    yol.write_text(yol.read_text().replace('"esik": 0.5', '"esik": 0.4'), encoding="utf-8")
    DL._ONBELLEK.clear()
    assert not _son(DL1.compute(_inp()))["signal"] and DL1.COUNTERS["paket_hash@1h"] == 1
    yol.write_text("{bozuk", encoding="utf-8")
    DL._ONBELLEK.clear()
    assert not _son(DL1.compute(_inp()))["signal"] and DL1.COUNTERS["paket_bozuk@1h"] == 1


def test_kapi_gecmemis_paket_yine_islem_yapar(paket):
    """24.11: kalite kapisi paketi engellemez; `kapi.gecti = False` paket aday uretir."""
    paket(kapi=False)
    assert bool(_son(DL1.compute(_inp()))["signal"]) and DL1.COUNTERS["aday@1h"] == 1 and "paket_kapi@1h" not in DL1.COUNTERS


@pytest.mark.parametrize("tf", DL.ZAMAN_DILIMLERI)
def test_dort_zaman_dilimi_aday(paket, tf):
    """Her zaman diliminde kendi paketinden aday: stop 1,5 ATR, hedef 3 ATR (rr 2), long/short; zaman dilimi paketleri birbirine karismaz."""
    paket(bl=2.0, bs=-2.0, tf=tf)
    r = _son(DL1.compute(_inp(tf=tf)))
    assert bool(r["signal"]) and r["setup"] == "DL1" and r["side"] == "long" and r["rr"] == pytest.approx(2.0)
    assert (r["planned_target"] - r["planned_entry"]) == pytest.approx(2 * (r["planned_entry"] - r["planned_stop"]))
    paket(bl=-2.0, bs=3.0, tf=tf)
    r = _son(DL1.compute(_inp("NVDA/USDT", tf=tf)))
    assert bool(r["signal"]) and r["side"] == "short" and r["planned_target"] < r["planned_entry"] < r["planned_stop"]
    assert DL1.COUNTERS[f"aday@{tf}"] == 2


def test_paket_zaman_dilimine_ozel_diger_tf_paket_yok(paket):
    paket(tf="4h")
    assert bool(_son(DL1.compute(_inp(tf="4h")))["signal"])
    out = DL1.compute(_inp(tf="15m"))
    assert not _son(out)["signal"] and DL1.COUNTERS["paket_yok@15m"] == 1


def test_baska_tf_paketi_yanlis_dosyada_sema_hatasi(paket, tmp_path):
    """DL1@1h.json icerigi DL1@4h dosyasina kopyalansa arm_id uyusmaz -> sema (aday yok)."""
    yol = paket(tf="1h")
    (tmp_path / "DL1@4h.json").write_text(yol.read_text(encoding="utf-8"), encoding="utf-8")
    DL._ONBELLEK.clear()
    assert not _son(DL1.compute(_inp(tf="4h")))["signal"] and DL1.COUNTERS["paket_sema@4h"] == 1


def test_15m_doluluk_orani_mum_biriminde(paket):
    """15m'de her 2. mum dolu (%50) puanlanir, her 4. mum dolu (%25) puanlanmaz: oran takvim saatiyle degil mumla hesaplanir."""
    paket()
    paket(tf="15m")
    t = S.seri(D, 500, tf="15m")
    m = np.zeros(len(t), dtype=bool)
    m[-1::-4] = True
    t.loc[~m, "volume"] = 0.0
    assert not _son(DL1.compute(_inp("XAU/USDT", trig=t, tf="15m")))["signal"]
    DL1._ONBELLEK.clear()
    t3 = S.seri(D, 500, tf="15m")
    m3 = np.zeros(len(t3), dtype=bool)
    m3[-1::-2] = True
    t3.loc[~m3, "volume"] = 0.0
    assert bool(_son(DL1.compute(_inp("XAU/USDT", trig=t3, tf="15m")))["signal"])


def test_kapsam_disi_cift_aday_yok(paket):
    paket()
    assert not _son(DL1.compute(_inp("DOGE/USDT")))["signal"] and DL1.COUNTERS["kapsam_disi@1h"] == 1


def test_paket_hatasi_diger_kollari_etkilemez(paket):
    """DL1 aday uretmediginde digerleri (M1/HB1) ayni modullerden etkilenmez: modul durumu bagimsiz, cikti bos tablo."""
    import trader_engine.strategies.arms.hb1 as HB1
    out = DL1.compute(_inp())
    assert not out["signal"].any() and HB1.SETUP == "HB1"


def test_veri_kisa_aday_yok(paket):
    paket()
    assert not _son(DL1.compute(_inp(n=150)))["signal"] and DL1.COUNTERS["veri_kisa@1h"] == 1


def test_seans_kapali_son_mum_bos_aday_yok_ve_seyrek_pencere(paket):
    paket()
    t = S.seri(D, 500)
    t.iloc[-1, t.columns.get_loc("volume")] = 0.0
    assert not _son(DL1.compute(_inp("NVDA/USDT", trig=t)))["signal"] and DL1.COUNTERS["puan_yok@1h"] == 1
    t2 = S.seri(D, 500)
    m = np.zeros(len(t2), dtype=bool)
    m[-1::-4] = True
    t2.loc[~m, "volume"] = 0.0                                    # her 4. saat dolu: doluluk %25 -> aday yok
    assert not _son(DL1.compute(_inp("XAU/USDT", trig=t2)))["signal"]
    DL1._ONBELLEK.clear()                                         # onbellek anahtari (cift, bar, paket): ayni bar farkli veri yalniz testte
    t3 = S.seri(D, 500)
    m3 = np.zeros(len(t3), dtype=bool)
    m3[-1::-2] = True
    t3.loc[~m3, "volume"] = 0.0                                   # her 2. saat dolu: %50 -> puanlanir
    assert bool(_son(DL1.compute(_inp("XAU/USDT", trig=t3)))["signal"])


def test_cikarim_bar_basina_bir_kez(paket, monkeypatch):
    paket()
    n = {"c": 0}
    gercek = DL.puanla

    def sayac(*a, **k):
        n["c"] += 1
        return gercek(*a, **k)
    monkeypatch.setattr(DL, "puanla", sayac)
    i = _inp()
    DL1.compute(i)
    DL1.compute(i)
    assert n["c"] == 1


def test_sizinti_son_barin_ardindan_veri_yok_puan_gecmise_bagli(paket):
    """Aday yalniz kapanmis barlardan: son bar degisince puan degisir, onceki barlarin degismesi uzak gecmisi etkilemez (kanal nedenselligi dl1 testinde)."""
    rg = np.random.default_rng(4)
    ag = {ad: rg.normal(0, 0.15, sek) for ad, sek in DL.agirlik_sekilleri().items()}
    yol = paket.yol
    S.yaz(yol, S.paket_sozlugu(D - timedelta(days=1), agirlik=ag, esik=0.01))
    DL._ONBELLEK.clear()
    a = DL.paket_yukle(yol, D)[0]
    t = S.seri(D, 400)
    ts = t.index.tz_localize("UTC").as_unit("ns").asi8
    cols = [t[k].to_numpy() for k in ("open", "high", "low", "close", "volume")]
    r_tam = DL.puanla(a, "BTC/USDT", ts, *cols)
    r_gec = DL.puanla(a, "BTC/USDT", ts[:-1], *(x[:-1] for x in cols))
    assert r_tam is not None and r_gec is not None and r_tam[0] != r_gec[0]


def test_core_yok_ve_bar_gecersiz_sayaclari(paket, monkeypatch):
    paket()
    i = _inp()
    i2 = ArmInput(pair=i.pair, tf=i.tf, D=i.D, trig=i.trig, h4=i.h4, params=None, core_fn=lambda: None)
    assert not DL1.compute(i2)["signal"].any() and DL1.COUNTERS["core_yok@1h"] == 1
    gercek = DL1.P.prepare

    def gecersiz(inp, core):
        p = gercek(inp, core)
        return type(p)(**{**p.__dict__, "ok": np.zeros_like(p.ok)})
    monkeypatch.setattr(DL1.P, "prepare", gecersiz)
    assert not _son(DL1.compute(_inp()))["signal"] and DL1.COUNTERS["bar_gecersiz@1h"] == 1


def test_sayac_logu_saatte_en_fazla_bir_bar_zamani_ile(paket, caplog):
    import logging
    paket(bl=-5.0, bs=-5.0)
    DL1._LOG.clear()
    with caplog.at_level(logging.INFO, logger="trader.dl1"):
        for dk in (0, 15, 30, 45):
            DL1.compute(_inp(D_=D + timedelta(minutes=dk), trig=S.seri(D + timedelta(minutes=dk))))
        assert not [r for r in caplog.records if "sayaclar" in r.message]        # ayni saat: log yok
        DL1.compute(_inp(D_=D + timedelta(hours=1), trig=S.seri(D + timedelta(hours=1))))
        assert len([r for r in caplog.records if "sayaclar" in r.message]) == 1  # saat degisti: bir kez
        DL1.compute(_inp(D_=D + timedelta(hours=1, minutes=30), trig=S.seri(D + timedelta(hours=1, minutes=30))))
        assert len([r for r in caplog.records if "sayaclar" in r.message]) == 1


def test_motor_dongusu_ayni_cift_dort_zaman_dilimi_dort_paket(paket):
    """Gercek dongu sekli: ayni cift icin ardisik 15m/1h/4h/1d hesaplari, dort ayri paket; sayaclar zaman dilimi anahtarlidir."""
    for tf in DL.ZAMAN_DILIMLERI:
        paket(tf=tf)
    for _tur in range(2):
        for tf in DL.ZAMAN_DILIMLERI:
            assert bool(_son(DL1.compute(_inp(tf=tf)))["signal"])
    for tf in DL.ZAMAN_DILIMLERI:
        assert DL1.COUNTERS[f"aday@{tf}"] == 2


def test_dort_paket_birlikte_onbellekte_her_dosya_bir_kez_okunur(paket, monkeypatch):
    for tf in DL.ZAMAN_DILIMLERI:
        paket(tf=tf)
    okunan = []
    gercek = DL.Path.read_text

    def sayac(self, *a, **k):
        okunan.append(self.name)
        return gercek(self, *a, **k)
    monkeypatch.setattr(DL.Path, "read_text", sayac)
    for _tur in range(3):
        for tf in DL.ZAMAN_DILIMLERI:
            p, neden = DL.paket_yukle(tf=tf)
            assert p is not None and neden is None
    assert sorted(okunan) == sorted(f"DL1@{tf}.json" for tf in DL.ZAMAN_DILIMLERI)
    assert len(DL._ONBELLEK) == 4
