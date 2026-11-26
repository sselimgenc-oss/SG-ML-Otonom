"""ML1 sifirdan ogrenme: motor butunlesik testleri (sentetik gecmis, SimClock; ag yok).

Sahip karari (26.11): tohum paket yok; ogrenme asamasinda kapi her adayi gecirir; ogrenici YALNIZ gercekten acilip kapanan kagit
islemlerden ogrenir (trade_id + decision_id ile bagli, etiket = defterdeki net r_multiple > 0)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml1"))
pytest.importorskip("pyarrow")

import ml1_motor_destek as T  # noqa: E402

from trader_engine import ml1_ogren as OG  # noqa: E402
from trader_ml.ml1 import model as M  # noqa: E402

MIN_ISLEM = 6


class _SinamasizOgrenici(OG.Ml1Ogrenici):
    """Bu dosyanin mekanik testleri (min_islem = 6, n < 40) orneklem-disi sinamayi calistiramaz: yalniz test, kurucu anahtariyla kapatir
    (motor `sinama` GECIRMEZ ve config'ten okunmaz: bkz. test_ml1_ogren_sinama_motor.py)."""

    def __init__(self, *a, **kw):
        kw["sinama"] = False
        super().__init__(*a, **kw)


@pytest.fixture(autouse=True, scope="module")
def _sinamasiz_ogrenici():
    mp = pytest.MonkeyPatch()
    mp.setattr(OG, "Ml1Ogrenici", _SinamasizOgrenici)
    yield
    mp.undo()


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    d = tmp_path_factory.mktemp("ogren_hist") / "hist"
    T.write_history(d)
    return d


def _cfg(tmp: Path, kuru: bool = False, aktif: bool | None = True, min_islem: int = MIN_ISLEM) -> dict:
    d = {"aktif": True, "paket_yolu": str(tmp / "models" / "ml1_package.json")}
    if aktif is not None:
        d["ogrenme"] = {"aktif": aktif, "kuru": kuru, "min_islem": min_islem, "min_islem_tf": 0, "esik": 0.50}
    return d


def _ogren_dir(eng) -> Path:
    return Path(eng.cfg.path("ml1_ogren"))


def _satirlar(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def _dosyalar(eng, ad: str) -> list[dict]:
    out = []
    for p in sorted(_ogren_dir(eng).glob(f"{ad}-*.jsonl")):
        out += _satirlar(p)
    return out


@pytest.fixture(scope="module")
def kosu(tmp_path_factory, hist):
    tmp = tmp_path_factory.mktemp("ogren_kosu")
    eng = T.make_engine(tmp, hist, _cfg(tmp))
    eng.run_range(T.START, T.END)
    return eng, tmp


def _defter_kapananlar(eng) -> dict[int, object]:
    return {t.trade_id: t for t in eng.ledger.list_closed_trades(limit=10000)}


def test_motor_ogrenme_asamasi_hepsini_gecirir_alinanlar_gercek_islemle_baglanir(kosu):
    eng, tmp = kosu
    dec = T.decisions(eng)
    # kapi puansiz gecirdi: ogrenme asamasindaki kararlarda ml1_neden=ogrenme, ml1_skor yok, hicbiri ML1 nedeniyle elenmedi
    ogr = [r for r in dec if r["features"].get("ml1_neden") == "ogrenme"]
    assert ogr and all("ml1_skor" not in r["features"] for r in ogr)
    assert [r for r in ogr if r["final_action"] == "entered"]
    assert not [r for r in ogr if str(r["veto_reason"] or "").startswith("gate:ml1_")
                and r["veto_reason"] != "gate:ml1_ayni_olay"]                # yalniz bir-olay-bir-giris kurali ve motorun kendi kapilari
    # alinanlar: HER kayit gercekten acilmis bir islemin (entered karar) vektoru; alinmayan aday dosyada YOK
    alinan = _dosyalar(eng, "alinanlar")
    assert len(alinan) >= MIN_ISLEM, len(alinan)
    entered = {(r["pair"], r["arm_id"], r["side"]) for r in dec if r["final_action"] == "entered"}
    assert len([r for r in dec if r["final_action"] == "entered"]) >= len(alinan)
    tum = {t.trade_id: t for t in eng.ledger.list_closed_trades(limit=10000)} | {t.trade_id: t for t in eng.ledger.list_open_trades()}
    assert len({r["trade_id"] for r in alinan}) == len(alinan)                # her islem bir kez
    for r in alinan:
        assert len(r["x"]) == len(M.feature_names()) and (r["pair"], r["arm_id"], r["side"]) in entered
        t = tum[r["trade_id"]]                                                 # gercek defter islemi
        assert t.decision_id == r["decision_id"] and t.pair == r["pair"] and t.side == r["side"]
        assert eng.ledger.get_decision(t.decision_id).arm_id == r["arm_id"]
    assert not list(_ogren_dir(eng).glob("adaylar-*.jsonl"))                   # puanlanan her adayi saklayan eski dosya yok
    assert not (_ogren_dir(eng) / "durum.json").read_text().count("taban")


def test_motor_etiket_defterdeki_gercek_net_r_ve_ilk_paket_min_islem_sonrasi(kosu):
    eng, tmp = kosu
    sonuc = [r for r in _dosyalar(eng, "sonuclar") if "y" in r]
    assert len(sonuc) >= MIN_ISLEM, len(sonuc)
    kap = _defter_kapananlar(eng)
    for r in sonuc:
        t = kap[r["trade_id"]]
        assert t.decision_id == r["decision_id"] and r["r_net"] == pytest.approx(t.r_multiple) and r["y"] == int(t.r_multiple > 0)
    # ilk paket yalniz min_islem kapanan islemden sonra
    upd = _satirlar(_ogren_dir(eng) / "guncellemeler.jsonl")
    yazildi = [u for u in upd if u.get("sonuc") == "yazildi"]
    assert yazildi, upd[-3:]
    assert all(u["kapali_islem"] >= MIN_ISLEM for u in upd if "kapali_islem" in u) and yazildi[0]["kapali_islem"] >= MIN_ISLEM
    dur = json.loads((_ogren_dir(eng) / "durum.json").read_text())
    assert dur["surum"] == len(yazildi) and dur["asama"] == "suzme" and dur["kapali_islem"] == len(sonuc) and dur["min_islem"] == MIN_ISLEM
    assert dur["kuru"] is False and dur["son_guncelleme"]
    etkin, why = M.load_package(tmp / "models" / "ml1_package.json")
    assert why is None and etkin["threshold"] == 0.50 and etkin["online"]["kaynak"] == "gercek_kagit_islemleri" and "taban_sha" not in etkin["online"]
    # kapi once puansiz (ogrenme), paket yazilinca puanli (suzme) karar verir
    dec = T.decisions(eng)
    assert any("ml1_skor" in r["features"] for r in dec) and any(r["features"].get("ml1_neden") == "ogrenme" for r in dec)
    ilk_skor = min(i for i, r in enumerate(dec) if "ml1_skor" in r["features"])
    assert not any(r["features"].get("ml1_neden") == "ogrenme" for r in dec[ilk_skor:])      # paketten sonra ogrenme asamasi bitti
    assert {r["features"]["ml1_esik"] for r in dec if "ml1_esik" in r["features"]} == {0.50}


def test_motor_yeniden_baslatma_cift_sayim_yok(kosu):
    eng, tmp = kosu
    n_sonuc = len([r for r in _dosyalar(eng, "sonuclar") if "y" in r])
    pend = set(eng.ogren.bekleyen)
    og2 = OG.Ml1Ogrenici(_ogren_dir(eng), eng.ml1._paths[0], now_fn=eng.clock.now, ledger=eng.ledger, min_islem=MIN_ISLEM)
    assert og2.baslat(T.END)
    assert set(og2.bekleyen) == pend and og2.n_kapali == n_sonuc == eng.ogren.n_kapali
    assert not (og2.kapali & set(og2.bekleyen))


def test_motor_kapali_ve_paper_disi_dosya_yazmaz(tmp_path, hist):
    eng = T.make_engine(tmp_path, hist, _cfg(tmp_path, aktif=False))
    eng.run_range(T.START, T.START + timedelta(hours=8))
    assert eng.ogren is None and not _ogren_dir(eng).exists()
    eng2 = T.make_engine(tmp_path / "b", hist, _cfg(tmp_path / "b", aktif=None))
    eng2.run_range(T.START, T.START + timedelta(hours=8))
    assert eng2.ogren is None and not _ogren_dir(eng2).exists()
    assert eng.ml1.counters.get("ml1_ogren_log_hata", 0) == 0


def test_motor_kuru_calisir_paketi_yazmaz(tmp_path, hist):
    eng = T.make_engine(tmp_path, hist, _cfg(tmp_path, kuru=True))
    eng.run_range(T.START, T.END)
    upd = _satirlar(_ogren_dir(eng) / "guncellemeler.jsonl")
    assert any(u["sonuc"] == "kuru" for u in upd)
    assert not (tmp_path / "models" / "ml1_package.json").exists()
    dur = json.loads((_ogren_dir(eng) / "durum.json").read_text())
    assert dur["asama"] == "ogrenme" and dur["kuru"] is True
    assert not [r for r in T.decisions(eng) if "ml1_skor" in r["features"]]     # paket olmadi: hep ogrenme asamasi


def test_motor_ogrenici_istisnasi_motoru_durdurmaz(tmp_path, hist, monkeypatch):
    eng = T.make_engine(tmp_path, hist, _cfg(tmp_path))

    def boom(*a, **k):
        raise RuntimeError("test")
    monkeypatch.setattr(eng.ogren, "adim", boom)
    eng.run_range(T.START, T.START + timedelta(hours=6))
    assert eng._rec["ml1_ogren"]["hata"] > 0


def test_motor_ogrenme_kaydi_yazilamazsa_karar_degismez(tmp_path, hist):
    a = T.make_engine(tmp_path / "a", hist, _cfg(tmp_path / "a", aktif=False))
    a.run_range(T.START, T.START + timedelta(days=1))
    b = T.make_engine(tmp_path / "b", hist, _cfg(tmp_path / "b"))
    d = _ogren_dir(b)
    shutil.rmtree(d, ignore_errors=True)
    d.write_text("dosya, dizin degil")                          # dizin acilamaz: yazim hatasi
    b.ogren.hazir = False                                          # adim/durum yazimi kapali; yalniz kapinin islem kaydi denenir
    b.run_range(T.START, T.START + timedelta(days=1))
    assert b.ml1.counters["ml1_ogren_log_hata"] > 0
    ka = [(r["pair"], r["arm_id"], r["final_action"]) for r in T.decisions(a)]
    kb = [(r["pair"], r["arm_id"], r["final_action"]) for r in T.decisions(b)]
    assert ka == kb
