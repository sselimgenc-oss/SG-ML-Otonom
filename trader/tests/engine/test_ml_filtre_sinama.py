"""23.11 kullanici kararlari 3 (c) ve 4: gece suzgeci yayin oncesi ileri sinamadan gecer; counterfactual orneklere de girer.
(a) gecen aile yayinlanir; (b) gecemeyen aile yayinlanmaz ve eski paketi geri cekilir; (c) counterfactual egitime girer, cift sayim yok,
kesimden sonra kapananlar ve kilit donemi disarida; (d) <10 ornek eskisi gibi atlanir."""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ortak_ogrenme import filtre as PF
from ortak_ogrenme.kayit import Aday
from trader_core import counterfactual as CF
from trader_engine import ogrenme_filtre as OF

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import ml_retrain_run as R  # noqa: E402

NOW = datetime(2026, 12, 1, 0, 0, 5, tzinfo=timezone.utc)
T0 = datetime(2026, 11, 2, tzinfo=timezone.utc)


def _aday(i, r, x, arm="T1@1h"):
    return Aday(id=f"a{i}", proje="ML", kurulum=arm, enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long",
                ts=T0 + timedelta(hours=2 * i), alindi=True, r=r, ozellikler={"x": x},
                cikis={"kapanis": (T0 + timedelta(hours=2 * i + 1)).isoformat()})


def _iyi(n):      # x etiketi tam ayirir: 2/3 kazanan
    return [_aday(i, -1.0 if i % 3 == 2 else 1.0, -5.0 if i % 3 == 2 else 5.0) for i in range(n)]


def _kotu(n):     # ozellik ile sonuc ilgisiz (sinama diliminde x=+5 olanlar kaybeder): suzgec deger katmaz
    return [_aday(i, 1.0 if i < n * 2 // 3 else -1.0, 5.0 if i % 3 != 2 else -5.0) for i in range(n)]


def test_a_sinamayi_gecen_aile_yayinlanir(tmp_path):
    r = OF.egit_hepsi(_iyi(30), tmp_path, NOW)
    s = r["aileler"]["T1"]
    assert s["durum"] == "ok" and s["sinama"]["karar"] == "gecti"
    assert s["sinama"]["n_sinama"] == 9 and s["sinama"]["n_kabul"] >= OF.SINAMA_MIN_KABUL
    assert s["sinama"]["ort_r_kabul"] > s["sinama"]["ort_r_hepsi"]
    meta = json.loads((tmp_path / "aile_T1.json").read_text())["meta"]
    assert meta["n_egitim"] == 30                                        # gecince TUM veriyle yeniden egitilir
    assert json.loads((tmp_path / OF.DURUM_DOSYASI).read_text())["aile:T1"]["sinama"]["karar"] == "gecti"
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is False


def test_b_sinamayi_gecemeyen_aile_yayinlanmaz_eski_paket_geri_cekilir(tmp_path):
    eski = PF.egit("aile:T1", [dataclasses.replace(a, kurulum="aile:T1") for a in _iyi(30)], olusturma=NOW - timedelta(days=1))
    PF.kaydet(eski, tmp_path)
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW).izin is False   # eski paket calisiyordu
    r = OF.egit_hepsi(_kotu(30), tmp_path, NOW)
    s = r["aileler"]["T1"]
    assert s["durum"] == "sinama_kaldi" and s["sinama"]["karar"] == "kaldi"
    assert not (tmp_path / "aile_T1.json").exists()                      # eski paket geri cekildi
    k = OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "filtre_yok"                    # suzgec KAPALI
    d = json.loads((tmp_path / OF.DURUM_DOSYASI).read_text())["aile:T1"]
    assert d["model"] is False and d["sinama"]["karar"] == "kaldi"


def test_b2_sinama_purge_ve_min_kabul():
    sin = OF.aile_sinama(PF, "aile:T1", [dataclasses.replace(a, kurulum="aile:T1") for a in _iyi(30)], NOW)
    assert sin["karar"] == "gecti" and sin["n_sinama"] == 9
    # purge: egitim ornekleri sinamanin ilk kararindan ONCE kapanmis olmali -> egitim <= 21
    assert sin["n_egitim"] <= 21
    az = OF.aile_sinama(PF, "aile:T1", [dataclasses.replace(a, kurulum="aile:T1") for a in _iyi(10)], NOW)
    assert az["n_sinama"] == OF.SINAMA_MIN_ORNEK                          # en az 5 ornek


# ------------------------------------------------------------------ counterfactual
def _dec(i, arm="T1@1h", gun=2):
    return SimpleNamespace(id=i, arm_id=arm, side="long", regime="trend", atr_ratio=1.0, session_tag="eu", pair="BTC/USDT",
                           planned_entry=100.0, planned_stop=99.0, planned_target=102.0, rh_touches=2, rl_touches=1,
                           features={}, bar_close_ts=T0 + timedelta(hours=i))


def _z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _cf_depo(yol, satirlar):
    with CF.CounterfactualStore(yol) as st:
        pass
    db = sqlite3.connect(yol)
    for did, r, end in satirlar:
        db.execute("INSERT INTO cf_outcomes (bot,decision_id,method,pair,side,setup,trigger_tf,skip_reason,decision_ts,planned_entry,"
                   "planned_stop,planned_target,window_start_ts,window_end_ts,hyp_outcome,hyp_r_gross,hyp_r_net,cost_r,exit_reason,"
                   "bars_held,computed_at,version,arm_id) VALUES ('learner',?,'barrier','BTC/USDT','long','T1','1h','ml_filter',?,100,99,102,?,?,1,?,?,0,'target',3,?,1,'T1@1h')",
                   (did, _z(T0), _z(T0), _z(end), r, r, _z(NOW)))
    db.commit()
    db.close()


def _led(kararlar, trade_karar):
    trades = [SimpleNamespace(trade_id=100 + d, decision_id=d, r_multiple=1.0, exit_ts=T0 + timedelta(hours=d + 2)) for d in trade_karar]
    return SimpleNamespace(LIST_CLOSED_MAX=1000, list_decisions=lambda: kararlar, list_closed_trades=lambda limit=None: trades)


def test_c_counterfactual_egitime_girer_cift_sayim_kesim_ve_holdout(tmp_path):
    kararlar = [_dec(i) for i in range(1, 7)]
    kararlar.append(SimpleNamespace(**{**_dec(7).__dict__, "bar_close_ts": datetime(2026, 6, 1, tzinfo=timezone.utc)}))   # holdout icinde
    cf = tmp_path / "cf.sqlite"
    _cf_depo(cf, [
        (1, 0.5, T0 + timedelta(hours=10)),                       # gecerli
        (2, -1.0, T0 + timedelta(hours=11)),                      # gecerli
        (3, 1.0, T0 + timedelta(hours=12)),                       # decision 3 kapanmis islem de var -> cift sayim YOK
        (4, 1.0, NOW + timedelta(hours=1)),                       # kesimden SONRA kapaniyor -> disarida
        (5, 1.0, T0 + timedelta(hours=5) - timedelta(hours=10)),  # karardan ONCE 'kesinlesmis' -> disarida
        (7, 1.0, datetime(2026, 6, 2, tzinfo=timezone.utc)),      # holdout -> disarida
    ])
    adaylar = OF.adaylar_defterden(_led(kararlar, [3]), R.cf_satirlari_oku(cf), NOW)
    ids = sorted(a.id for a in adaylar)
    assert ids == ["103", "cf1", "cf2"]                           # 3: yalniz islem olarak; 4,5,7 yok
    cfs = [a for a in adaylar if a.id.startswith("cf")]
    assert all(a.etiketler == ("counterfactual",) and a.alindi and a.cikis["kaynak"] == "counterfactual" for a in cfs)
    assert sorted(a.r for a in cfs) == [-1.0, 0.5]
    assert all(datetime.fromisoformat(a.cikis["kapanis"]) <= NOW for a in adaylar)
    # cf yolu yoksa yalniz islemler (eski davranis)
    assert [a.id for a in OF.adaylar_defterden(_led(kararlar, [3]))] == ["103"]
    assert [a.id for a in OF.adaylar_defterden(_led(kararlar, [3]), R.cf_satirlari_oku(tmp_path / "yok.sqlite"), NOW)] == ["103"]


def test_c2_counterfactual_ornekler_modeli_egitir(tmp_path):
    kararlar = [_dec(i) for i in range(1, 31)]
    cf = tmp_path / "cf.sqlite"
    _cf_depo(cf, [(i, 1.0 if i % 3 else -1.0, T0 + timedelta(hours=i + 2)) for i in range(1, 31)])
    adaylar = OF.adaylar_defterden(_led(kararlar, []), R.cf_satirlari_oku(cf), NOW)
    assert len(adaylar) == 30
    r = OF.egit_hepsi(adaylar, tmp_path / "m", NOW)
    assert r["aileler"]["T1"]["n"] == 30                          # yalniz counterfactual ornekler sayildi


def test_d_az_veri_eskisi_gibi_atlanir(tmp_path):
    r = OF.egit_hepsi(_iyi(9), tmp_path, NOW)
    assert r["aileler"]["T1"]["durum"] == "az_islem" and "sinama" not in r["aileler"]["T1"]
    assert not (tmp_path / "aile_T1.json").exists()
