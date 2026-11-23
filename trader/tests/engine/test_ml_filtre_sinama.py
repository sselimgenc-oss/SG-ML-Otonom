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


def _kotu(n):     # egitim bolumunde x bilgili, sinama bolumunde TERS: suzgec kabul ettiklerinde hepsinden kotu
    out = []
    for i in range(n):
        x = -5.0 if i % 3 == 2 else 5.0
        ters = i >= n * 2 // 3
        out.append(_aday(i, (1.0 if (x > 0) != ters else -1.0), x))
    return out


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
    assert k.izin is True                                               # suzgec KAPALI
    d = json.loads((tmp_path / OF.DURUM_DOSYASI).read_text())["aile:T1"]
    assert d["model"] is False and d["sinama"]["karar"] == "kaldi"
    assert json.loads((tmp_path / "aile_T1.sinama.json").read_text())["karar"] == "kaldi"
    assert k.neden == "sinama_gecmedi"                                   # bozuk/bayat/yok'tan ayirt edilir


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
                   "bars_held,computed_at,version,arm_id) VALUES ('learner',?,'plan','BTC/USDT','long','T1','1h','ml_filter',?,100,99,102,?,?,1,?,?,0,'target',3,?,2,'T1@1h')",
                   (did, _z(T0), _z(T0), _z(end), r, r, _z(NOW)))
    db.commit()
    db.close()


def _led(kararlar, trade_karar):
    trades = [SimpleNamespace(trade_id=100 + d, decision_id=d, r_multiple=1.0, exit_ts=T0 + timedelta(hours=d + 2)) for d in trade_karar]
    return SimpleNamespace(LIST_CLOSED_MAX=1000, list_decisions=lambda: kararlar, list_closed_trades=lambda limit=None: trades)


def test_c_counterfactual_egitime_girer_cift_sayim_kesim_ve_holdout(tmp_path, monkeypatch):
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
    acik = sorted(a.id for a in OF.adaylar_defterden(_led(kararlar, [3]), R.cf_satirlari_oku(cf), NOW))
    assert acik == ["103", "cf1", "cf2", "cf7"]                   # 23.11.2026 kilit ACIK: holdout satiri (7) artik disarida degil
    monkeypatch.setattr(OF, "KILIT_ACIK", False)                  # kilit mekanizmasi kapali bayrakla sinanir
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


def test_c2_counterfactual_egitime_girer_ama_min_islemi_ve_sinamayi_etkilemez(tmp_path):
    kararlar = [_dec(i) for i in range(1, 31)]
    cf = tmp_path / "cf.sqlite"
    _cf_depo(cf, [(i, 1.0 if i % 3 else -1.0, T0 + timedelta(hours=i + 2)) for i in range(1, 31)])
    cfa = OF.adaylar_defterden(_led(kararlar, []), R.cf_satirlari_oku(cf), NOW)
    assert len(cfa) == 30
    r = OF.egit_hepsi(cfa, tmp_path / "m", NOW)                     # yalniz counterfactual: MIN 10 GERCEK islem sayilir
    assert r["aileler"]["T1"]["durum"] == "az_islem" and r["aileler"]["T1"]["n"] == 0 and r["aileler"]["T1"]["n_cf"] == 30
    gercek = _iyi(12)                                               # 12 gercek + 30 cf: MIN gecer; n gercek sayisidir
    r = OF.egit_hepsi(gercek + cfa, tmp_path / "m2", NOW)
    assert r["aileler"]["T1"]["n"] == 12 and r["aileler"]["T1"]["n_cf"] == 30
    sin = r["aileler"]["T1"]["sinama"]
    assert sin["n_sinama"] == 5 and sin["n_egitim_cf"] > 0          # cf egitimde, sinama yalniz gercek


def test_min_10_yalniz_gercek_islem_ve_yeniden_tetigi(tmp_path):
    cf = [dataclasses.replace(a, id="c" + a.id, etiketler=(OF.CF_ETIKET,)) for a in _iyi(40)]
    r = OF.egit_hepsi(_iyi(9) + cf, tmp_path, NOW)
    assert r["aileler"]["T1"]["durum"] == "az_islem" and r["aileler"]["T1"]["n"] == 9
    OF.egit_hepsi(_iyi(30), tmp_path, NOW)
    cf2 = [dataclasses.replace(a, id="d" + a.id, ts=a.ts + timedelta(days=1), etiketler=(OF.CF_ETIKET,)) for a in _iyi(30)]
    r = OF.egit_hepsi(_iyi(30) + cf2, tmp_path, NOW + timedelta(days=1))
    assert r["aileler"]["T1"]["durum"] == "guncel"                  # 30 yeni counterfactual yeniden egitimi tetiklemez


def test_sinanamadi_egitim_az_ve_egitilemedi(tmp_path):
    r = OF.egit_hepsi(_iyi(10), tmp_path, NOW)                      # 10 gercek: sinama 5, egitim 5 < SINAMA_MIN_EGITIM
    s = r["aileler"]["T1"]
    assert s["durum"] == "sinama_sinanamadi" and s["sinama"]["neden"] == "egitim_az"
    assert not (tmp_path / "aile_T1.json").exists()
    assert json.loads((tmp_path / "aile_T1.sinama.json").read_text())["karar"] == "sinanamadi"
    tek = [_aday(i, 1.0, float(i)) for i in range(20)]               # egitimde tek sinif
    r = OF.egit_hepsi(tek, tmp_path / "t", NOW)
    assert r["aileler"]["T1"]["sinama"]["neden"] == "egitilemedi" and r["aileler"]["T1"]["durum"] == "sinama_sinanamadi"


def test_istisna_yolunda_eski_paket_kalkar_isaret_hata_durum_hemen_yazilir(tmp_path, monkeypatch):
    eski = PF.egit("aile:T1", [dataclasses.replace(a, kurulum="aile:T1") for a in _iyi(30)], olusturma=NOW - timedelta(days=1))
    PF.kaydet(eski, tmp_path)
    monkeypatch.setattr(PF, "egit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("patladi")))
    r = OF.egit_hepsi(_iyi(30) + [dataclasses.replace(a, kurulum="R1@1h") for a in _iyi(30)], tmp_path, NOW)
    assert r["aileler"]["T1"]["durum"] == "hata" and r["aileler"]["R1"]["durum"] == "hata"
    assert not (tmp_path / "aile_T1.json").exists()                  # sinanmamis paket "hayir" demez
    assert json.loads((tmp_path / "aile_T1.sinama.json").read_text())["karar"] == "hata"
    assert json.loads((tmp_path / OF.DURUM_DOSYASI).read_text())["aile:T1"]["sinama"]["karar"] == "hata"
    k = OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": -5.0}, NOW)
    assert k.izin is True and k.neden == "hata"                      # hata isareti: canli fail-closed kalir
    assert OF.canlida_engelle(k.neden) is True


def test_sinama_kaydi_olmayan_paket_guncel_sayilmaz(tmp_path):
    OF.egit_hepsi(_iyi(30), tmp_path, NOW)
    dy = tmp_path / OF.DURUM_DOSYASI
    d = json.loads(dy.read_text())
    d["aile:T1"].pop("sinama")                                       # eski surum durum kaydi
    dy.write_text(json.dumps(d))
    r = OF.egit_hepsi(_iyi(30), tmp_path, NOW + timedelta(days=1))
    assert r["aileler"]["T1"]["durum"] == "ok" and r["aileler"]["T1"]["sinama"]["karar"] == "gecti"


def test_hepsini_kabul_eden_suzgec_gecer():
    duz = [_aday(i, 1.0 if i % 2 else -1.0, 1.0) for i in range(30)]   # ozellik sabit: puan ~ taban oran >= esik, hepsi kabul
    sin = OF.aile_sinama(PF, "aile:T1", [dataclasses.replace(a, kurulum="aile:T1") for a in duz], NOW)
    assert sin["n_kabul"] == sin["n_sinama"] and sin["ort_r_kabul"] == sin["ort_r_hepsi"] and sin["karar"] == "gecti"


def test_purge_gercekten_ornek_atar_ve_sonucu_degistirir():
    kimlik = "aile:T1"
    gercek = [dataclasses.replace(a, kurulum=kimlik) for a in _iyi(30)]
    ilk = gercek[-9].ts                                             # sinama diliminin ilk karari
    # karar zamani sinamadan ONCE ama kapanisi SONRA (uzun ufuk) + yaniltici etiket: purge'suz egitimi bozar
    bozucu = [Aday(id=f"c{i}", proje="ML", kurulum=kimlik, enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long",
                   ts=ilk - timedelta(hours=1 + i), alindi=True, r=(-1.0 if i % 2 else 1.0), ozellikler={"x": (5.0 if i % 2 else -5.0)},
                   etiketler=(OF.CF_ETIKET,), cikis={"kapanis": (NOW - timedelta(days=1)).isoformat()}) for i in range(30)]
    sin = OF.aile_sinama(PF, kimlik, gercek + bozucu, NOW)
    assert sin["n_purge"] == 30 and sin["n_egitim"] == 21 and sin["n_egitim_cf"] == 0 and sin["karar"] == "gecti"
    # purge'suz (bozucular egitimde): suzgec bozulur
    purgesiz = PF.egit(kimlik, gercek[:-9] + bozucu, olusturma=NOW)
    kabul = [a.r for a in gercek[-9:] if PF.puan(purgesiz, a.ozellikler) >= purgesiz["esik"]]
    rs = [a.r for a in gercek[-9:]]
    assert len(kabul) < OF.SINAMA_MIN_KABUL or sum(kabul) / len(kabul) < sum(rs) / len(rs)


def test_karisik_ufuk_uzun_ufuklu_ornek_egitimi_silmez():
    kimlik = "aile:T1"
    gercek = [dataclasses.replace(a, kurulum=kimlik) for a in _iyi(30)]
    uzun = Aday(id="uzun", proje="ML", kurulum=kimlik, enstruman="BTC/USDT", varlik_sinifi="kripto", yon="long", ts=T0 - timedelta(hours=1),
                alindi=True, r=1.0, ozellikler={"x": 5.0}, etiketler=(OF.CF_ETIKET,), cikis={"kapanis": (NOW - timedelta(days=1)).isoformat()})
    sin = OF.aile_sinama(PF, kimlik, gercek + [uzun], NOW)
    assert sin["n_sinama"] == 9 and sin["n_purge"] == 1 and sin["n_egitim"] == 21   # yalniz uzun ufuklu ornek atilir, sinama dilimi/egitim bozulmaz


def test_sqlite_hatasi_yalniz_islemlerle_devam(tmp_path):
    bozuk = tmp_path / "cf.sqlite"
    bozuk.write_bytes(b"bu bir sqlite dosyasi degil" * 100)
    assert R.cf_satirlari_oku(bozuk) == []
    assert R.cf_satirlari_oku(tmp_path / "yok.sqlite") == []


# ------------------------------------------------------------------ isaret + canli/kagit parite (23.11 karar a)
def test_isaret_okunur_bozuk_paket_ve_okunamayan_isaret_ayirt_edilir(tmp_path):
    OF.egit_hepsi(_kotu(30), tmp_path, NOW)
    d = OF.FiltreDeposu(tmp_path)
    k = d.karar("T1@1h", {"x": 5.0}, NOW)
    assert k.neden == "sinama_gecmedi" and k.izin is True and OF.canlida_engelle("sinama_gecmedi") is False
    (tmp_path / "aile_T1.sinama.json").write_text("{bozuk")
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": 5.0}, NOW).neden == "hata"          # isaret okunamiyor: canli engel
    (tmp_path / "aile_T1.sinama.json").write_text(json.dumps({"karar": "kaldi"}))
    (tmp_path / "aile_T1.json").write_text("{bozuk")                                           # bozuk PAKET: isaret bakilmaz
    assert OF.FiltreDeposu(tmp_path).karar("T1@1h", {"x": 5.0}, NOW).neden == "filtre_yok"
    assert OF.canlida_engelle("filtre_yok") and OF.canlida_engelle("hata") and not OF.canlida_engelle("ok")


def test_parite_sinama_gecmedi_iki_motorda_serbest_bozuk_paket_canli_engel(tmp_path):
    import test_canli_inceleme_duzeltmeleri as C
    OF.egit_hepsi(_kotu(30), tmp_path / "m", NOW)
    hepsi = []
    for mod in ("paper", "live"):
        (tmp_path / f"g1{mod}").mkdir()
        o, e = C._gate_outcome(tmp_path / f"g1{mod}", mode=mod, filtre=_Sabit(OF.FiltreDeposu(tmp_path / "m")))
        try:
            hepsi.append(o.action)
        finally:
            C._kapat(e)
    assert hepsi == ["enter", "enter"]                                                          # sinama_gecmedi: kagit = canli
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "aile_PA.json").write_text("{bozuk")
    sonuc = {}
    for mod in ("paper", "live"):
        (tmp_path / f"g2{mod}").mkdir()
        o, e = C._gate_outcome(tmp_path / f"g2{mod}", mode=mod, filtre=_Sabit(OF.FiltreDeposu(tmp_path / "b")))
        try:
            sonuc[mod] = o.action
        finally:
            C._kapat(e)
    assert sonuc == {"paper": "enter", "live": "skip"}                                          # bozuk paket: kagit serbest, canli engel


class _Sabit:
    """FiltreDeposu'nu gate'in gorecegi aileye (PA) yonlendirir."""
    def __init__(self, dep):
        self._d = dep

    def karar(self, arm, oz, simdi):
        return self._d.karar("T1@1h" if (self._d.klasor / "aile_T1.sinama.json").exists() else "PA@1h", oz, simdi)


def test_d_az_veri_eskisi_gibi_atlanir(tmp_path):
    r = OF.egit_hepsi(_iyi(9), tmp_path, NOW)
    assert r["aileler"]["T1"]["durum"] == "az_islem" and "sinama" not in r["aileler"]["T1"]
    assert not (tmp_path / "aile_T1.json").exists()
