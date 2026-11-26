"""Panel: Tutarlilik ve PBO/Holdout bolumleri (salt okunur; eksik/bozuk/bayat dosya paneli bozmaz)."""
import json
from datetime import timedelta

import pytest

from panel_support import NOW, Env, z
from trader_panel import snapshot as SN
from trader_panel.data import PanelData, load_config


def tut_doc(age_days=1.0, **kw):
    d = {"sema": "ml.tutarlilik.v1", "uretim": z(NOW - timedelta(days=age_days)),
         "donem": {"bas": "2026-11-09T00:00:00Z", "bit": "2026-11-16T00:00:00Z"},
         "kurulumlar": [{"ad": "PA1", "kagit_islem": 8, "bt_islem": 9, "eslesme_orani": 0.88, "yalniz_kagit": 1,
                         "yalniz_bt": 0, "giris_kayma_bps_ort": 4.5, "cikis_kayma_bps_ort": 2.0, "kagit_R": 3.2,
                         "bt_R": 2.5, "kagit_pnl": 10.0, "bt_pnl": 8.0, "nedenler": {}},
                        {"ad": "M1", "eslesme_orani": 1.0, "kagit_R": float("nan")}],
         "uyari": True, "uyari_nedenleri": ["PA1: eslesme < 90%"], "not": None}
    d.update(kw)
    return d


@pytest.fixture()
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    e.close()


def pd_(env):
    return PanelData(load_config(env.cfg_path), clock=lambda: NOW)


def put(env, rel, obj, raw=None):
    p = env.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw if raw is not None else json.dumps(obj))


def test_tutarlilik_ok(env):
    put(env, "var/durum/tutarlilik_v1.json", tut_doc())
    r = pd_(env).tutarlilik()
    assert r["ok"] and r["var"] and r["uyari"] is True
    pa1, m1 = r["kurulumlar"]
    assert pa1["eslesme_orani"] == 0.88 and pa1["giris_kayma_bps_ort"] == 4.5 and pa1["uyari"] == ["PA1: eslesme < 90%"]
    assert m1["kagit_R"] is None and m1["uyari"] == []          # NaN -> None (JSON gecerli kalir)
    json.dumps(r, allow_nan=False)
    assert r["donem"]["bit"].startswith("2026-11-16")


@pytest.mark.parametrize("raw,neden", [(None, "dosya_yok"), ("{bozuk", "bozuk"), ("[1]", "bozuk"),
                                       (json.dumps({"sema": "x"}), "sema_yanlis"),
                                       (json.dumps(tut_doc(age_days=9)), "bayat"),
                                       (json.dumps(tut_doc(uretim="dun")), "uretim_yok")])
def test_tutarlilik_missing_corrupt_stale_is_rapor_yok(env, raw, neden):
    if raw is not None:
        put(env, "var/durum/tutarlilik_v1.json", None, raw)
    r = pd_(env).tutarlilik()
    assert r["ok"] is True and r["var"] is False and r["neden"] == neden


def test_tutarlilik_structure_garbage_tolerated(env):
    put(env, "var/durum/tutarlilik_v1.json", tut_doc(kurulumlar="x", uyari_nedenleri=5, donem=3))
    r = pd_(env).tutarlilik()
    assert r["ok"] and r["var"] and r["kurulumlar"] == [] and r["uyari_nedenleri"] == []


def test_pbo_and_muhur(env):
    put(env, "research/holdout/pbo_ozet.json", {"parametreler": {"holdout_oncesi_sinir": "2026-05-01"}, "aileler": [
        {"aile": "Kural T1", "tur": "kural", "pbo": 0.25, "dsr": 0.31, "n_yapilandirma": 7, "T": 365,
         "durum": "tamam", "yorum": "dusuk"}, "x"]})
    put(env, "research/holdout/muhur.json", {"muhur_tarihi": "2026-11-19T15:08:49Z", "dosya_sayisi": 80,
                                              "dosyalar": [{"sha256": "a" * 64}], "birlesik_sha256": "ab" * 32, "acildi": False})
    r = pd_(env).pbo()
    assert r["ok"] and r["pbo"]["var"] and len(r["pbo"]["aileler"]) == 1
    a = r["pbo"]["aileler"][0]
    assert (a["pbo"], a["dsr"], a["n_yapilandirma"], a["T"]) == (0.25, 0.31, 7, 365)
    m = r["muhur"]
    assert m["acildi"] is False and m["dosya_sayisi"] == 80 and m["hash12"] == "ab" * 6
    assert "dosyalar" not in json.dumps(r) and "a" * 20 not in json.dumps(r)


def test_pbo_missing_and_corrupt_never_breaks(env):
    r = pd_(env).pbo()
    assert r["ok"] and r["pbo"] == {"var": False, "neden": "dosya_yok"} and r["muhur"]["var"] is False
    put(env, "research/holdout/pbo_ozet.json", None, "{{")
    put(env, "research/holdout/muhur.json", None, "[]")
    r = pd_(env).pbo()
    assert r["ok"] and r["pbo"]["neden"] == "bozuk" and r["muhur"]["neden"] == "bozuk"


def test_snapshot_includes_sections_and_survives_missing(env):
    html = SN.render(pd_(env))
    assert html
    data = SN.collect(pd_(env))      # 9b-01: panel.js okumayan uclar gomulmez
    assert "/api/tutarlilik" not in data and "/api/pbo" not in data
