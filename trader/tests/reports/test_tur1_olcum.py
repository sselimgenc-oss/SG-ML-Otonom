"""Tur 1 olcum raporu: her bolum sentetik defterle; kilitli donem korumasi; determinizm; betik/zamanlayici baglantisi."""
from __future__ import annotations

import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from trader_reports import tur1_olcum as T  # noqa: E402

H = 3_600_000
NOW = datetime(2026, 11, 23, 5, 10, tzinfo=timezone.utc)
T0 = int(datetime(2026, 11, 2, tzinfo=timezone.utc).timestamp() * 1000)   # kilitli donemin SONRASI


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def mk(i, *, side="long", net=1.0, regime="range", arm="T1@1h", asset="kripto", entry_ms=None, cost=0.1, mfe=1.5, pair="BTC/USDT"):
    em = entry_ms if entry_ms is not None else T0 + (40 + i * 5) * H
    s = 1 if side == "long" else -1
    risk = 10.0
    return {"trade_id": i, "pair": pair, "side": side, "arm": arm, "tf": "1h", "regime": regime, "asset": asset,
            "entry_ts": iso(em), "exit_ts": iso(em + 3 * H), "entry_price": 100.0, "exit_price": 100.0 + s * net,
            "qty": 1.0, "planned_entry": 100.0, "planned_stop": 100.0 - s * 10.0, "planned_risk": risk,
            "gross_pnl": (net + cost) * risk, "pnl": net * risk, "net_r": net, "mfe_r": mfe, "mae_r": 0.2, "bars_held": 3}


def market(tmp_path, pairs=("BTC/USDT",), n=2200, drift=0.0):
    p = tmp_path / "market.sqlite"
    c = sqlite3.connect(str(p))
    c.executescript("""CREATE TABLE bars(kind TEXT NOT NULL, pair TEXT NOT NULL, tf TEXT NOT NULL, open_ms INTEGER NOT NULL,
      o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, v REAL NOT NULL DEFAULT 0, written_ms INTEGER NOT NULL,
      PRIMARY KEY(kind,pair,tf,open_ms)) WITHOUT ROWID; PRAGMA user_version=1;""")
    rng = np.random.default_rng(5)
    px = 100.0
    rows = []
    for pair in pairs:
        px = 100.0
        for k in range(n):
            o = px
            px = px * (1 + drift + rng.normal(0, 0.004))
            ms = T0 + k * H
            rows.append(("last", pair, "1h", ms, o, max(o, px) * 1.001, min(o, px) * 0.999, px, 1.0, ms + 2 * H))
    c.executemany("INSERT INTO bars(kind,pair,tf,open_ms,o,h,l,c,v,written_ms) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()
    return p


def trades_mix(n=40):
    return [mk(i, side="long" if i % 2 else "short", net=(0.8 if i % 3 else -1.0), regime=("range" if i % 4 else "trend_up"),
               arm=("T1@1h" if i % 2 else "R1@1h")) for i in range(n)]


# ---------------------------------------------------------------- bolum 1
def test_rakip_kiyasi_rastgele_ve_sabit_yon(tmp_path):
    ts = trades_mix(30)
    m = T.MumDeposu(market(tmp_path))
    try:
        r = T.rakip_kiyasi(ts, m, b=300)
    finally:
        m.close()
    ra = r["rastgele_giris"]
    assert ra["durum"] == "ok" and ra["n"] > 0 and 0.0 <= ra["yuzdelik"] <= 100.0 and ra["simulasyon_sayisi"] >= 300
    assert r["hicbir_sey"]["toplam"] == 0.0 and r["n"] == 30 and r["etiket"] is None
    # hep long: long islemler kendi net'i; short islemler ters (mfe>=1 -> -1R)
    longs = [t["net_r"] for t in ts if t["side"] == "long"]
    assert r["hep_long"]["n"] == 30 and r["hep_long"]["toplam"] == pytest.approx(sum(longs) + sum(-1.1 for t in ts if t["side"] == "short"))
    assert r["hep_short"]["n"] == 30


def test_rakip_kiyasi_az_islem_yetersiz_ve_mum_yok():
    r = T.rakip_kiyasi([mk(1), mk(2)], None)
    assert r["etiket"] == T.YETERSIZ and r["rastgele_giris"]["durum"] == "veri_yok"


def test_rastgele_giris_belirleyici(tmp_path):
    ts = trades_mix(12)
    p = market(tmp_path)
    a, b = T.MumDeposu(p), T.MumDeposu(p)
    try:
        x, y = T.rastgele_giris(ts, a, 200, 7), T.rastgele_giris(ts, b, 200, 7)
    finally:
        a.close(), b.close()
    assert x["yuzdelik"] == y["yuzdelik"] and x["rastgele_p50"] == y["rastgele_p50"]


# ---------------------------------------------------------------- bolum 2
def test_masraf_carpani_ve_kalan_oran():
    ts = [mk(i, net=1.0, cost=0.2) for i in range(5)]
    d = T.dayaniklilik(ts, None)
    assert d["masraf"]["x1.5"]["toplam"] == pytest.approx(5 * (1.0 - 0.5 * 0.2))
    assert d["masraf"]["x2.0"]["toplam"] == pytest.approx(5 * (1.0 - 0.2))
    assert d["masraf"]["x2.0"]["kalan_oran"] == pytest.approx(0.8)
    assert d["gecikme"]["1_mum"]["n"] == 0 and d["gecikme"]["1_mum"]["durum"]["veri_yok"] == 5


def test_gecikme_fiyatlama_ve_kacirilan(tmp_path):
    m = T.MumDeposu(market(tmp_path, drift=0.0))
    try:
        t = mk(1, entry_ms=T0 + 100 * H)
        o0, o1 = m.bar("BTC/USDT", "1h", T0 + 100 * H)[0], m.bar("BTC/USDT", "1h", T0 + 101 * H)[0]
        r, d = T.gecikmeli_r(t, m, "1h", 1)
        assert d == "ok"
        assert r == pytest.approx(t["net_r"] + (100.0 - 100.0 * o1 / o0) * 1.0 / 10.0)
        t2 = dict(t, exit_ts=iso(T0 + 101 * H))            # cikis gecikmis girisle ayni anda: islem kacirildi
        assert T.gecikmeli_r(t2, m, "1h", 1) == (0.0, "kacirildi")
        assert T.gecikmeli_r(dict(t, entry_ts=iso(T0 - 9 * H)), m, "1h", 1)[1] == "veri_yok"
    finally:
        m.close()


def test_saat_kaymasi_acikca_olculemedi():
    d = T.dayaniklilik([mk(1)], None)["saat_kaymasi_15dk"]
    assert d["tam_olculebildi"] is False and "YAPILAMAZ" in d["aciklama"]


# ---------------------------------------------------------------- bolum 3
def test_sans_kuyruk_belirleyici_ve_batis():
    ts = [mk(i, net=(-1.0 if i % 2 else 1.0)) for i in range(20)]
    a, b = T.sans_kuyruk(ts, 1000.0, 5000, 3), T.sans_kuyruk(ts, 1000.0, 5000, 3)
    assert a == b and a["karistirma"] == 5000 and a["etiket"] == T.YETERSIZ
    assert a["batis_olasiligi"] == 0.0 and a["maks_dusus"]["p95"] >= a["maks_dusus"]["p50"]
    kayip = [mk(i, net=-1.0) for i in range(30)]               # -10$ x 30 = -300$ -> kasa 700 < 850 -> batis kesin
    assert T.sans_kuyruk(kayip, 1000.0, 5000)["batis_olasiligi"] == 1.0


def test_en_iyi_cikar():
    ts = [mk(i, net=v) for i, v in enumerate([5.0, 3.0, 1.0, 1.0, 1.0, 1.0, -1.0])]
    s = T.sans_kuyruk(ts, 1000.0, 5000)["en_iyi_cikar"]
    assert s["1"]["net_r"] == pytest.approx(6.0) and s["2"]["net_r"] == pytest.approx(3.0) and s["5"]["net_r"] == pytest.approx(0.0)
    assert T.sans_kuyruk(ts[:3], 1000.0, 5000)["en_iyi_cikar"]["5"]["net_r"] is None


# ---------------------------------------------------------------- bolum 4
def test_canli_sartlari_az_islemde_fail_ve_gecen_durum():
    ts = trades_mix(40)
    rk = {"rastgele_giris": {"yuzdelik": 95.0}}
    dy = T.dayaniklilik(ts, None)
    c = T.canli_sartlari(ts, rk, dy)
    assert [m["sonuc"] for m in c["maddeler"]][0] == "FAIL" and not c["hepsi_gecti"] and c["uyari"]
    assert c["maddeler"][3]["sonuc"] == "PASS" and "95.0" in c["maddeler"][3]["deger"]
    g = [mk(i, net=(1.0 + 0.01 * (i % 7)), regime=("range", "trend_up", "volatile")[i % 3],
            entry_ms=T0 + (40 + i * 24) * H) for i in range(330)]
    c2 = T.canli_sartlari(g, rk, T.dayaniklilik(g, None))
    assert c2["hepsi_gecti"], c2["maddeler"]
    c3 = T.canli_sartlari(g, {"rastgele_giris": {"yuzdelik": 80.0}}, T.dayaniklilik(g, None))
    assert not c3["hepsi_gecti"] and c3["maddeler"][3]["sonuc"] == "FAIL"
    assert T.canli_sartlari(g, {}, T.dayaniklilik(g, None))["maddeler"][3]["sonuc"] == "FAIL"


def test_canli_sarti_tek_rejim_ve_masraf():
    g = [mk(i, net=0.05, cost=0.5, regime="range", entry_ms=T0 + (40 + i * 24) * H) for i in range(310)]
    c = T.canli_sartlari(g, {"rastgele_giris": {"yuzdelik": 99.0}}, T.dayaniklilik(g, None))
    s = {m["ad"][:12]: m["sonuc"] for m in c["maddeler"]}
    assert c["maddeler"][2]["sonuc"] == "FAIL" and c["maddeler"][4]["sonuc"] == "FAIL"   # 1 rejim; x1.5 masrafta net < 0


# ---------------------------------------------------------------- bolum 5
def test_yon_denetimi_ve_ml_filtre(tmp_path):
    ts = trades_mix(20)
    dec = [{"id": i, "side": "long", "skip_reason": "ml_filter", "final_action": "skipped", "bar_close_ts": iso(T0 + 50 * H)} for i in range(3)]
    dec += [{"id": 10 + i, "side": "long", "skip_reason": None, "final_action": "entered", "bar_close_ts": iso(T0 + 50 * H)} for i in range(1)]
    dec += [{"id": 20, "side": "short", "skip_reason": "stop_width", "final_action": "skipped", "bar_close_ts": iso(T0 + 50 * H)}]
    md = tmp_path / "models"
    md.mkdir()
    feats = ["f_a", T.SIDE_FEATURE, "f_b"]
    (md / "x.json").write_text(json.dumps({"meta": {"features": feats}, "model": {"kind": "logistic", "coef": [1.0, -3.0, 0.0]}}))
    (md / "y.json").write_text(json.dumps({"meta": {"features": ["f_a"]}, "model": {"kind": "logistic", "coef": [1.0]}}))
    d = T.yon_denetimi(ts, dec, md)
    assert {r["anahtar"] for r in d["yon"]} == {"long", "short"} and sum(r["n"] for r in d["yon"]) == 20
    assert d["ml_filtre"]["long"]["red_orani"] == pytest.approx(0.75) and d["ml_filtre"]["short"]["ml_reddi"] == 0
    assert d["ml_filtre"]["long"]["etiket"] == T.YETERSIZ
    p = {x["paket"]: x for x in d["yon_ozelligi"]["paketler"]}
    assert p["x.json"]["onem_payi"] == pytest.approx(0.75) and p["x.json"]["sira"] == 1
    assert p["y.json"]["durum"] == "ozellik_listede_yok"
    assert T.yon_ozelligi_onemi(None)["durum"] == "paket_dizini_yok"


def test_lgbm_onemi():
    tree = {"tree_structure": {"split_feature": 1, "split_gain": 4.0, "left_child": {"leaf_value": 0.1},
                               "right_child": {"split_feature": 0, "split_gain": 1.0, "left_child": {"leaf_value": 0}, "right_child": {"leaf_value": 1}}}}
    assert T._lgbm_onem({"tree_info": [tree]}, 1, 2) == (0.5, 0.8)


# ---------------------------------------------------------------- bolum 6
def test_kayip_kumeleri():
    ts = [mk(i, net=-1.0, arm="A@1h", regime="range", side="long", entry_ms=T0 + 40 * H) for i in range(4)]
    ts += [mk(10, net=-5.0, arm="B@1h", regime="volatile", side="short", asset="hisse")]
    ts += [mk(11, net=2.0, arm="A@1h", regime="range", side="long")]
    k = T.kayip_kumeleri(ts)
    assert k["n_kayip"] == 5 and k["kume_sayisi"] >= 2
    assert k["sayiya_gore"][0]["kol"] == "A@1h" and k["sayiya_gore"][0]["kayip_sayisi"] == 4 and k["sayiya_gore"][0]["not"] is None
    assert k["kayba_gore"][0]["kol"] == "B@1h" and k["kayba_gore"][0]["not"] == "az örnek"
    assert k["etiket"] == T.YETERSIZ


# ---------------------------------------------------------------- kilitli donem
@pytest.mark.usefixtures("kilitli_donem")
def test_kilitli_donem_islemleri_atilir_ve_mum_okunmaz(tmp_path):
    kilitli = mk(1, entry_ms=int(datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp() * 1000))
    sonra = mk(2)
    ok, _, n = T.holdout_filtrele([kilitli, sonra], [])
    assert [t["trade_id"] for t in ok] == [2] and n == 1
    _, dok, _ = T.holdout_filtrele([], [{"bar_close_ts": iso(int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1000))},
                                        {"bar_close_ts": iso(T0)}])
    assert len(dok) == 1
    p = tmp_path / "m.sqlite"
    c = sqlite3.connect(str(p))
    c.executescript("CREATE TABLE bars(kind TEXT,pair TEXT,tf TEXT,open_ms INTEGER,o REAL,h REAL,l REAL,c REAL,v REAL,written_ms INTEGER); PRAGMA user_version=1;")
    jun = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
    c.execute("INSERT INTO bars VALUES ('last','BTC/USDT','1h',?,1,1,1,1,1,?)", (jun, jun + 2 * H))
    c.commit(), c.close()
    m = T.MumDeposu(p)
    try:
        assert m.bar("BTC/USDT", "1h", jun) is None and m.frame("BTC/USDT", "1h", jun - 5 * H, jun + 5 * H) is None
        assert T.rastgele_giris([kilitli], m, 50)["durum"] == "veri_yok"
    finally:
        m.close()
    r = T.rapor([kilitli], [], None, kasa0=1000.0, now=NOW, runs=5000)
    assert r["n_islem"] == 0 and r["kilitli_donem_atilan_islem"] == 1


def test_modul_holdout_tarihini_dogrudan_okumaz():
    src = (ROOT / "src" / "trader_reports" / "tur1_olcum.py").read_text(encoding="utf-8")
    assert "sqlite3.connect" not in src and "2026-05-01" not in src and "HOLDOUT" not in src.replace("(HOLDOUT)", "")
    assert "guard.check_window" in src and "guard.trade_locked" in src


# ---------------------------------------------------------------- tum akis, betik, zamanlama
def test_rapor_butunu_ve_md(tmp_path):
    m = T.MumDeposu(market(tmp_path))
    try:
        d = T.rapor(trades_mix(20), [], m, kasa0=1000.0, now=NOW, b=200, runs=5000)
        d2 = T.rapor(trades_mix(20), [], m, kasa0=1000.0, now=NOW, b=200, runs=5000)
    finally:
        m.close()
    assert d == d2 and d["sema"] == T.SCHEMA and set(d["bolumler"]) == {"rakip_kiyasi", "dayaniklilik", "sans_kuyruk", "canli_sartlari", "yon_denetimi", "kayip_kumeleri"}
    json.dumps(d)
    md = T.render_md(d)
    assert "yetersiz örnek" in md and "FAIL" in md and "tam ölçülemedi" in md


def test_betik_ve_zamanlayici_kablolari():
    dep = ROOT / "deploy"
    assert "tur1_olcum_v1.json" in (dep / "durum_yayinla.sh").read_text(encoding="utf-8")
    assert "enable_now trader-tur1-olcum.timer" in (dep / "install.sh").read_text(encoding="utf-8")
    assert "tur1_olcum_run.py --once" in (dep / "trader-tur1-olcum.service").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 05:10:00 UTC" in (dep / "trader-tur1-olcum.timer").read_text(encoding="utf-8")


def test_betik_defter_yoksa_temiz(tmp_path):
    import tur1_olcum_run as R
    (tmp_path / "config").mkdir()
    for f in ("panel.json",):
        (tmp_path / "config" / f).write_text(json.dumps({"ledger_path": str(tmp_path / "yok.sqlite")}))
    try:
        rc = R.main(["--once"], env={"TRADER_DATA_ROOT": str(tmp_path)}, now_fn=lambda: NOW)
    except Exception as e:  # noqa: BLE001  (panel yapilandirmasi eksik anahtar isterse: betik bu testte yalniz import edilebilir olmali)
        pytest.skip(f"panel yapilandirma sarmalayicisi: {type(e).__name__}") if False else None
        raise
    assert rc == 0


def test_ust_lig_karnesi_kol_yoksa_ve_varsa():
    d = T.ust_lig([])
    assert d["HB1"]["durum"] == "kol henüz yok" and d["DL1"]["n"] == 0
    full = T.rapor(trades_mix(20), [], None, kasa0=1000.0, now=NOW, b=50, runs=5000)
    assert full["ust_lig"]["HB1"]["durum"] == "kol henüz yok"
    md = T.render_md(full)
    assert "## Üst lig" in md and "HB1: kol henüz yok" in md and "DL1: kol henüz yok" in md
    tr = [{"arm": "HB1@1h", "net_r": 0.5}, {"arm": "HB1@1h", "net_r": -0.25}, {"arm": "M1@1h", "net_r": 9.0}]
    d2 = T.ust_lig(tr)
    assert d2["HB1"]["n"] == 2 and d2["HB1"]["toplam"] == 0.25 and d2["HB1"]["etiket"] == T.YETERSIZ and d2["DL1"]["durum"] == "kol henüz yok"
