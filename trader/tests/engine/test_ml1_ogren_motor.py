"""ML1 aninda ogrenme: motor butunlesik testleri (sentetik gecmis, SimClock; ag yok) ve ic-motor maliyet olcumu."""
from __future__ import annotations

import json
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml1"))
pytest.importorskip("pyarrow")

import ml1_motor_destek as T  # noqa: E402

from trader_engine import ml1_ogren as OG  # noqa: E402
from trader_ml.ml1 import model as M  # noqa: E402

UTC = timezone.utc


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    d = tmp_path_factory.mktemp("ogren_hist") / "hist"
    T.write_history(d)
    return d


def _cfg(tmp: Path, kuru: bool = False, aktif: bool = True, thr: float = 0.0) -> dict:
    tohum = tmp / "tohum" / "ml1_package.json"
    T.write_package(tohum, threshold=thr)
    d = {"aktif": True, "paket_yolu": str(tmp / "models" / "ml1_package.json"), "tohum_yolu": str(tohum)}
    if aktif is not None:
        d["ogrenme"] = {"aktif": aktif, "kuru": kuru}
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


def test_ogren_motor_aday_sonuc_guncelleme_ve_yeni_sha(kosu):
    eng, tmp = kosu
    cand = [r for r in _dosyalar(eng, "adaylar") if "x" in r]
    sonuc = [r for r in _dosyalar(eng, "sonuclar") if "y" in r]
    assert len(cand) >= 30 and len(sonuc) >= 10, (len(cand), len(sonuc))
    assert all(len(r["x"]) == 66 for r in cand[:5])
    upd = _satirlar(_ogren_dir(eng) / "guncellemeler.jsonl")
    yazildi = [u for u in upd if u.get("sonuc") == "yazildi"]
    assert yazildi, upd[-3:]
    dur = json.loads((_ogren_dir(eng) / "durum.json").read_text())
    assert dur["surum"] == len(yazildi) and dur["bugun"]["sonuc"] >= 0 and dur["kuru"] is False
    # kapi yeni paketle puanlar: karar satirlarinda taban sha'dan farkli ml1_sha gorulur; ogrenilen paket gecerli
    dec = T.decisions(eng)
    shas = {r["features"]["ml1_sha"] for r in dec if "ml1_skor" in r["features"]}
    taban = M.load_package(tmp / "tohum" / "ml1_package.json")[0]
    assert len(shas) >= 2 and taban["sha256"][:12] in shas
    etkin, why = M.load_package(tmp / "models" / "ml1_package.json")
    assert why is None and etkin["threshold"] == taban["threshold"] and etkin["online"]["taban_sha"] == taban["sha256"]
    assert (tmp / "models" / "ml1_package.son_iyi.json").exists()


def test_ogren_motor_alinan_islem_isaretli_ve_sonuc_ayni_dosyada(kosu):
    eng, _ = kosu
    alinan = {r["k"] for r in _dosyalar(eng, "adaylar") if r.get("alindi")}
    assert alinan
    sonuc = [r for r in _dosyalar(eng, "sonuclar") if "y" in r]
    assert any(r["alindi"] for r in sonuc)


def test_ogren_motor_yeniden_baslatma_cift_sayim_yok(kosu, hist):
    eng, tmp = kosu
    n_sonuc = len([r for r in _dosyalar(eng, "sonuclar") if "y" in r])
    pend = set(eng.ogren.cands)
    og2 = OG.Ml1Ogrenici(_ogren_dir(eng), eng.ml1._paths[0], eng.ml1._paths[1], view=eng.view, now_fn=eng.clock.now, kapi=None)
    assert og2.baslat(T.END)
    assert set(og2.cands) == pend and len(og2._sn) == len(eng.ogren._sn) <= n_sonuc
    assert not (og2.kapali & set(og2.cands))


def test_ogren_motor_kapali_ve_paper_disi_dosya_yazmaz(tmp_path, hist):
    eng = T.make_engine(tmp_path, hist, _cfg(tmp_path, aktif=False))
    eng.run_range(T.START, T.START + timedelta(hours=8))
    assert eng.ogren is None and not _ogren_dir(eng).exists()
    eng2 = T.make_engine(tmp_path / "b", hist, _cfg(tmp_path / "b", aktif=None))
    eng2.run_range(T.START, T.START + timedelta(hours=8))
    assert eng2.ogren is None and not _ogren_dir(eng2).exists()
    assert eng.ml1.counters.get("ml1_ogren_log_hata", 0) == 0


def test_ogren_motor_kuru_calisir_paketi_yazmaz(tmp_path, hist):
    eng = T.make_engine(tmp_path, hist, _cfg(tmp_path, kuru=True))
    eng.run_range(T.START, T.START + timedelta(days=2))
    upd = _satirlar(_ogren_dir(eng) / "guncellemeler.jsonl")
    assert upd and {u["sonuc"] for u in upd} <= {"kuru"} | {u["sonuc"] for u in upd if u["sonuc"].startswith("reddedildi")}
    assert any(u["sonuc"] == "kuru" for u in upd)
    assert not (tmp_path / "models" / "ml1_package.json").exists()


def test_ogren_motor_ogrenici_istisnasi_motoru_durdurmaz(tmp_path, hist, monkeypatch):
    eng = T.make_engine(tmp_path, hist, _cfg(tmp_path))
    def boom(*a, **k):
        raise RuntimeError("test")
    monkeypatch.setattr(eng.ogren, "adim", boom)
    eng.run_range(T.START, T.START + timedelta(hours=6))
    assert eng._rec["ml1_ogren"]["hata"] > 0


def test_ogren_motor_kapi_gunlugu_yazilamazsa_karar_degismez(tmp_path, hist):
    a = T.make_engine(tmp_path / "a", hist, _cfg(tmp_path / "a", aktif=False))
    a.run_range(T.START, T.START + timedelta(days=1))
    b = T.make_engine(tmp_path / "b", hist, _cfg(tmp_path / "b"))
    d = _ogren_dir(b)
    import shutil
    shutil.rmtree(d)
    d.write_text("dosya, dizin degil")                          # dizin acilamaz: yazim hatasi
    b.ogren.hazir = False                                          # adim/durum yazimi kapali; yalniz kapinin aday kaydi denenir
    b.run_range(T.START, T.START + timedelta(days=1))
    assert b.ml1.counters["ml1_ogren_log_hata"] > 0
    ka = [(r["pair"], r["arm_id"], r["final_action"]) for r in T.decisions(a)]
    kb = [(r["pair"], r["arm_id"], r["final_action"]) for r in T.decisions(b)]
    assert ka == kb


def test_ogren_motor_butce_asilinca_kalan_ciftler_sonraki_adima(tmp_path, hist):
    eng = T.make_engine(tmp_path, hist, _cfg(tmp_path))
    eng.run_range(T.START, T.START + timedelta(days=1))
    og = eng.ogren
    og.butce_s = 0.0                                               # SimClock ilerlemez: 0 sn butce = hemen kes
    c0 = og.sayac["budget_skips"]
    og.coz(T.START + timedelta(days=1, hours=1))
    assert og.sayac["budget_skips"] > c0 or not og.cands


def test_ogren_motor_olculu_maliyet_30_gun_birikim(tmp_path, hist, capsys):
    """Ic-motor maliyet olcumu: 3 cift, 30 gunluk tum-bekleyen birikim tek adimda cozulur (en kotu durum); sonra kararli durum."""
    from trader_ml.ml1 import scan as SC, data as D
    tohum = tmp_path / "tohum.json"
    T.write_package(tohum, threshold=0.0)
    end = datetime(2026, 11, 11, tzinfo=UTC)
    og = OG.Ml1Ogrenici(tmp_path / "og", tmp_path / "pkg.json", tohum, view=_view(hist), now_fn=lambda: datetime.now(UTC), butce_s=1e9)
    assert og.baslat(end)
    recs = []
    for pair in T.PAIRS:
        for tf in ("15m", "1h", "4h", "1d"):
            trig, h4 = D.load_pair_tf(hist, pair, tf)
            ids = [a.split("@")[0] + "@" + tf for a in T.ARMS if a.endswith("@1h")]
            c = SC.scan_pair_tf(pair, tf, trig, h4, ids)
            c = c[(c["decision_ts"] >= pd.Timestamp(end - timedelta(days=30))) & (c["decision_ts"] <= pd.Timestamp(end - timedelta(hours=1)))]
            for r in c.to_dict("records"):
                ts = pd.Timestamp(r["decision_ts"])
                recs.append({"k": f"{pair}|{r['arm_id']}|{r['side']}|{ts.isoformat()}", "decision_ts": ts.isoformat(), "pair": pair, "tf": tf,
                             "setup": r["setup"], "arm_id": r["arm_id"], "group": r["group"], "side": r["side"], "entry_ref": float(r["entry_ref"]),
                             "stop": float(r["stop"]), "target": None if not np.isfinite(r["target"]) else float(r["target"]),
                             "stop_dist_atr": float(r["stop_dist_atr"]), "x": [float(v) for v in np.random.default_rng(1).normal(size=66)],
                             "skor": 0.6, "sha": "x", "kod": None})
    og.kaydet(recs)
    og.butce_s = OG.COZ_BUTCE_S                                    # gercek 5 sn butce
    n0 = len(og.cands)
    import resource
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tracemalloc.start()
    sureler = []
    skip_prev = -1
    for i in range(12):                                            # 30 gunluk tum-bekleyen birikim: butceli adimlarla erir
        t0 = time.perf_counter()
        og.adim(end + timedelta(minutes=15 * i), ())
        sureler.append(time.perf_counter() - t0)
        if i >= 1 and og.sayac["budget_skips"] == skip_prev and len(og.cands) <= 10:
            break
        skip_prev = og.sayac["budget_skips"]
    peak_py = tracemalloc.get_traced_memory()[1] / 1e6
    tracemalloc.stop()
    rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t1 = time.perf_counter()                                       # kararli durum: sadece kalan acik adaylar
    og.adim(end + timedelta(hours=6), ())
    kararli = time.perf_counter() - t1
    msg = (f"OLCUM 3 cift x 4 tf, 30 gun birikim: adaylar={n0} cozulen={len(og._sn)} bekleyen_sonra={len(og.cands)} adim_sayisi={len(sureler)} "
           f"adim_s={[round(x, 2) for x in sureler]} kararli_adim_s={kararli:.2f} py_tepe_MB={peak_py:.1f} rss_artis_MB={(rss1 - rss0) / 1024:.1f} "
           f"budget_skips={og.sayac['budget_skips']} hata={og.sayac['hata']}")
    print(msg)
    (tmp_path.parent / "ogren_olcum.txt").write_text(msg)
    assert og.sayac["hata"] == 0 and len(og._sn) > 0.9 * n0
    assert max(sureler) <= 7.5, msg                                # butce 5 sn + tek cift/tf isinmasi payi (yuklu CI makinesinde 2,5 sn); gercek K3 olcumu kuru kosuda
    assert kararli <= 1.0 and peak_py <= 60.0, msg


def _view(hist):
    from trader_engine.marketdata.sources import HistoricalSource
    return HistoricalSource(str(hist), granularity="15m", synthetic_rules=True)
