"""Tur 1 olcum raporu: onayli rapor duzeltmeleri ve yeni bolumler (sentetik veriyle)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "paket"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trader_reports import tur1_olcum as T  # noqa: E402
from test_tur1_olcum import H, NOW, T0, iso, market, mk, trades_mix  # noqa: E402


# ---------------------------------------------------------------- Duzeltme 5: gunluk (1d) kollar
GUN = 86_400_000


def market_4h(tmp_path, pair="BTC/USDT", gun=260, eksik_gun=()):
    """Yalniz 4s mumlar (market.sqlite gercekte 1d tutmaz); 1d bu mumlardan kurulur."""
    import sqlite3
    p = tmp_path / "market1d.sqlite"
    c = sqlite3.connect(str(p))
    c.executescript("""CREATE TABLE bars(kind TEXT NOT NULL, pair TEXT NOT NULL, tf TEXT NOT NULL, open_ms INTEGER NOT NULL,
      o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, v REAL NOT NULL DEFAULT 0, written_ms INTEGER NOT NULL,
      PRIMARY KEY(kind,pair,tf,open_ms)) WITHOUT ROWID; PRAGMA user_version=1;""")
    rng = np.random.default_rng(9)
    px, rows = 100.0, []
    for d in range(gun):
        for k in range(6):
            ms = T0 + d * GUN + k * 4 * H
            o, px = px, px * (1 + rng.normal(0, 0.01))
            if d in eksik_gun and k == 3:
                continue
            rows.append(("last", pair, "4h", ms, o, max(o, px) * 1.002, min(o, px) * 0.998, px, 1.0, ms + 5 * H))
    c.executemany("INSERT INTO bars(kind,pair,tf,open_ms,o,h,l,c,v,written_ms) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit(), c.close()
    return p


def mk1d(i, **kw):
    t = mk(i, arm="T1@1d", entry_ms=T0 + (40 + i * 2) * GUN + 3 * H, **kw)
    t["tf"] = "1d"
    t["exit_ts"] = iso(T0 + (40 + i * 2) * GUN + 3 * H + 2 * GUN)
    t["bars_held"] = 2
    return t


def test_gunluk_mum_4s_den_kurulur_eksik_gun_atlanir(tmp_path):
    m = T.MumDeposu(market_4h(tmp_path, eksik_gun=(5,)))
    try:
        assert m.bar("BTC/USDT", "1d", T0 + 4 * GUN) is not None
        assert m.bar("BTC/USDT", "1d", T0 + 5 * GUN) is None            # 6 mumdan biri eksik
        o, h, l, c = m.bar("BTC/USDT", "1d", T0 + 6 * GUN)
        assert h >= max(o, c) and l <= min(o, c)
    finally:
        m.close()


def test_gunluk_kollar_rastgele_giris_ve_gecikmeye_girer(tmp_path):
    ts = [mk1d(i) for i in range(12)] + [mk(100 + i) for i in range(3)]
    m = T.MumDeposu(market_4h(tmp_path))
    try:
        ra = T.rastgele_giris(ts, m, 200, 3)
        dy = T.dayaniklilik(ts, m)
    finally:
        m.close()
    assert ra["durum"] == "ok" and "1d" in ra["kapsanan_tf"] and ra["n"] == 12
    assert ra["atlanan"] == 3 and ra["atlanan_tf"] == {"1h": 3} and ra["atlanan_neden"] == {"mum_yok": 3}   # 1h mumu yok: acikca yazilir
    g = dy["gecikme"]["1_mum"]
    assert g["durum"].get("ok", 0) + g["durum"].get("kacirildi", 0) == 12 and g["veri_yok_tf"] == {"1h": 3}


def test_gunluk_veri_yoksa_acikca_atlanan_sayilir(tmp_path):
    ts = [mk1d(i) for i in range(5)]
    m = T.MumDeposu(market(tmp_path))                                   # yalniz 1h mumu var
    try:
        ra = T.rastgele_giris(ts, m, 200, 3)
        dy = T.dayaniklilik(ts, m)
    finally:
        m.close()
    assert ra["durum"] == "veri_yok" and ra["atlanan"] == 5 and ra["atlanan_tf"] == {"1d": 5}
    assert dy["gecikme"]["1_mum"]["veri_yok_tf"] == {"1d": 5}


# ---------------------------------------------------------------- Duzeltme 3: blok ornekleme
def test_sans_blok_ornekleme_yan_yana_ve_kume_kaybi_daha_kotu():
    # kayiplar uzun seri halinde (seri bagimlilik): blok ornekleme karistirmadan daha kotu dususu gostermeli
    pnl = ([-1.0] * 12 + [1.0] * 12) * 4
    ts = [mk(i, net=v) for i, v in enumerate(pnl)]
    a = T.sans_kuyruk(ts, 1000.0, 5000, 3)
    assert a == T.sans_kuyruk(ts, 1000.0, 5000, 3)
    b = a["blok"]
    assert b["ort_blok_uzunlugu"] > 1.5 and b["ornekleme"] == 5000
    assert b["maks_dusus"]["p50"] > a["maks_dusus"]["p50"]
    assert set(a["maks_dusus"]) == set(b["maks_dusus"]) and 0.0 <= b["batis_olasiligi"] <= 1.0
    assert "Blok örnekleme" in T.render_md(T.rapor(ts, [], None, kasa0=1000.0, now=NOW, runs=5000))


def test_sans_blok_bos_defterde_yok():
    assert "blok" not in T.sans_kuyruk([], 1000.0, 5000)


# ---------------------------------------------------------------- Duzeltme 9, 10: canli sartlari
RK = {"rastgele_giris": {"yuzdelik": 95.0}}


def _iyi(n=330, net=1.0):
    return [mk(i, net=(net + 0.01 * (i % 7)), regime=("range", "trend_up", "volatile")[i % 3], entry_ms=T0 + (40 + i * 24) * H) for i in range(n)]


def test_canli_azami_dusus_maddesi_esik_mandaldan_turer():
    assert T.CANLI_MAKS_DUSUS == pytest.approx(1.0 - T.SERMAYE_MANDALI_ORANI)
    g = _iyi()
    sk = T.sans_kuyruk(g, 1000.0, 5000)
    c = T.canli_sartlari(g, RK, T.dayaniklilik(g, None), sk)
    m = [x for x in c["maddeler"] if "maks düşüş" in x["ad"]][0]
    assert m["sonuc"] == "PASS" and "%15" in m["ad"] and c["hepsi_gecti"]
    kotu = [mk(i, net=(-1.0 if i % 3 else 1.0), regime=("range", "trend_up", "volatile")[i % 3], entry_ms=T0 + (40 + i * 24) * H) for i in range(330)]
    sk2 = T.sans_kuyruk(kotu, 1000.0, 5000)
    c2 = T.canli_sartlari(kotu, RK, T.dayaniklilik(kotu, None), sk2)
    m2 = [x for x in c2["maddeler"] if "maks düşüş" in x["ad"]][0]
    assert m2["sonuc"] == "FAIL" and not c2["hepsi_gecti"]
    # blok orneklemenin p95'i karistirmadan kotuyse o kullanilir
    sans = {"n": 330, "maks_dusus": {"p95": 0.05}, "blok": {"maks_dusus": {"p95": 0.20}}}
    m3 = [x for x in T.canli_sartlari(g, RK, T.dayaniklilik(g, None), sans)["maddeler"] if "maks düşüş" in x["ad"]][0]
    assert m3["sonuc"] == "FAIL" and "%20.0" in m3["deger"]


def test_canli_dsr_pbo_bilgi_satiri_gecmeyi_etkilemez():
    g = _iyi(400)
    for i, t in enumerate(g):
        t["arm"] = ("T1@1h", "R1@1h", "B1@4h")[i % 3]
    c = T.canli_sartlari(g, RK, T.dayaniklilik(g, None), T.sans_kuyruk(g, 1000.0, 5000))
    b = [x for x in c["maddeler"] if x.get("bilgi")]
    assert len(b) == 1 and b[0]["sonuc"] == "BİLGİ" and "DSR" in b[0]["deger"] and "PBO" in b[0]["deger"]
    d = c["dsr_pbo"]
    assert d["dsr"] is not None and 0.0 <= d["dsr"] <= 1.0 and d["pbo"] is not None and 0.0 <= d["pbo"] <= 1.0 and d["kol_sayisi"] == 3
    assert c["hepsi_gecti"]                                     # bilgi satiri sonucu degistirmez
    az = T.canli_sartlari(g[:5], RK, T.dayaniklilik(g[:5], None))["dsr_pbo"]
    assert az["pbo"] is None and "hesaplanamadı" in az["pbo_not"]


def test_rejim_sarti_30_islem_ve_guven_alt_siniri():
    assert T.REJIM_MIN_ISLEM == 30
    # 25 islemlik rejimler (30'dan az) sayilmaz
    az = [mk(i, net=1.0, regime=("range", "trend_up")[i % 2], entry_ms=T0 + (40 + i * 24) * H) for i in range(50)]
    assert T.canli_sartlari(az, RK, T.dayaniklilik(az, None))["maddeler"][2]["sonuc"] == "FAIL"
    # 60 islem/rejim, toplam pozitif ama guven alt siniri 0'in altinda (gurultulu): sayilmaz
    rng = np.random.default_rng(2)
    gur = [mk(i, net=float(rng.normal(0.02, 2.0)), regime=("range", "trend_up")[i % 2], entry_ms=T0 + (40 + i * 24) * H) for i in range(120)]
    c = T.canli_sartlari(gur, RK, T.dayaniklilik(gur, None))["maddeler"][2]
    assert c["sonuc"] == "FAIL" and "alt sınır" in c["deger"]
    # 60 islem/rejim, net pozitif ve tutarli: sayilir
    ok = [mk(i, net=1.0 + 0.01 * (i % 5), regime=("range", "trend_up")[i % 2], entry_ms=T0 + (40 + i * 24) * H) for i in range(120)]
    assert T.canli_sartlari(ok, RK, T.dayaniklilik(ok, None))["maddeler"][2]["sonuc"] == "PASS"


# ---------------------------------------------------------------- Duzeltme 7, 8: al-tut ve rakip masrafi
def _bars(tmp_path, ad, pair_aralik):
    """pair_aralik: {pair: [(baslangic_ms, adet, baslangic_fiyat, saatlik_carpan)]}"""
    import sqlite3
    p = tmp_path / ad
    c = sqlite3.connect(str(p))
    c.executescript("""CREATE TABLE bars(kind TEXT NOT NULL, pair TEXT NOT NULL, tf TEXT NOT NULL, open_ms INTEGER NOT NULL,
      o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, v REAL NOT NULL DEFAULT 0, written_ms INTEGER NOT NULL,
      PRIMARY KEY(kind,pair,tf,open_ms)) WITHOUT ROWID; PRAGMA user_version=1;""")
    rows = []
    for pair, aralik in pair_aralik.items():
        for bas, adet, px, mul in aralik:
            for k in range(adet):
                o, px = px, px * mul
                ms = bas + k * H
                rows.append(("last", pair, "1h", ms, o, max(o, px), min(o, px), px, 1.0, ms + 2 * H))
    c.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit(), c.close()
    return p


def test_al_tut_esit_agirlik_ve_veri_yok(tmp_path):
    m = T.MumDeposu(_bars(tmp_path, "a.sqlite", {"BTC/USDT": [(T0, 300, 100.0, 1.001)], "ETH/USDT": [(T0, 300, 50.0, 0.999)]}))
    ts = [mk(1, pair="BTC/USDT", entry_ms=T0 + 10 * H), mk(2, pair="ETH/USDT", entry_ms=T0 + 20 * H), mk(3, pair="SOL/USDT", entry_ms=T0 + 30 * H)]
    try:
        r = T.al_tut(ts, m, 1000.0)
    finally:
        m.close()
    # donem: T0+10h (ilk giris) -> son cikis T0+33h; bar basi hizasi: [T0+10h, T0+34h) = 24 bar
    assert r["durum"] == "ok" and r["n_enstruman"] == 3 and r["n_veri_var"] == 2 and r["veri_yok_enstruman"] == ["SOL/USDT"]
    assert r["enstruman_getirisi"]["BTC/USDT"] == pytest.approx(1.001 ** 24 - 1, rel=1e-9)
    assert r["enstruman_getirisi"]["ETH/USDT"] == pytest.approx(0.999 ** 24 - 1, rel=1e-9)
    assert r["ort_getiri"] == pytest.approx((r["enstruman_getirisi"]["BTC/USDT"] + r["enstruman_getirisi"]["ETH/USDT"]) / 2)
    assert r["bizim_getiri"] == pytest.approx(sum(t["pnl"] for t in ts) / 1000.0)
    assert T.al_tut(ts, None)["durum"] == "veri_yok" and T.al_tut([], None)["durum"] == "veri_yok"
    md = T.render_md(T.rapor(ts, [], T.MumDeposu(_bars(tmp_path, "b.sqlite", {"BTC/USDT": [(T0, 300, 100.0, 1.001)]})), kasa0=1000.0, now=NOW, b=100, runs=5000))
    assert "Al-tut (gerçek" in md and "veri yok: ETH/USDT" in md


def test_al_tut_kilitli_donemi_okumaz_zincirler(tmp_path):
    from datetime import datetime, timezone
    h0p = T.guard.H0_MS - T.guard.PAD_HOURS * H
    on = h0p - 50 * H
    sonra = T.guard.H1_MS
    p = _bars(tmp_path, "k.sqlite", {"BTC/USDT": [(on, 50, 100.0, 1.01), (sonra, 60, 200.0, 1.01)]})
    a = mk(1, pair="BTC/USDT", entry_ms=on + 2 * H)
    b = mk(2, pair="BTC/USDT", entry_ms=sonra + 50 * H)
    m = T.MumDeposu(p)
    try:
        r = T.al_tut([a, b], m)
    finally:
        m.close()
    assert r["durum"] == "ok" and r["kilitli_aralik_disarida"] is True
    onc = (1.01 ** 50)
    snr = 1.01 ** 60
    # parca 1: [on+2h, h0p) = 48 bar; parca 2: [H1, son cikis+) = 53 bar (60 bar mevcut, cikis sonrasi dahil degil)
    bit = sonra + 50 * H + 3 * H
    n2 = (bit - bit % H + H - sonra) // H
    assert r["enstruman_getirisi"]["BTC/USDT"] == pytest.approx(1.01 ** 48 * 1.01 ** n2 - 1, rel=1e-9)


def test_rastgele_rakip_kagit_masrafi_ve_eski_yan_yana(tmp_path):
    cfg = {"cost_overrides": {"BTC/USDT": {"open": {"slip_entry_bps": 40.0, "slip_exit_bps": 40.0, "slip_stop_bps": 90.0}}},
           "cost": {"taker_fee": 0.001}}
    fn = T.kagit_maliyet_fn(cfg)
    c = fn("BTC/USDT")
    assert c.kayma == pytest.approx(40e-4) and c.stop_kayma == pytest.approx(90e-4) and c.taker == pytest.approx(0.001)
    d = fn("ETH/USDT")                                      # override yok: CostModel varsayilani (2/2/5 bp)
    assert d.kayma == pytest.approx(2e-4) and d.stop_kayma == pytest.approx(5e-4)
    assert T.kagit_maliyet_fn(None) is None
    ts = [mk(i) for i in range(12)]
    m = T.MumDeposu(market(tmp_path))
    try:
        yeni = T.rastgele_giris(ts, m, 200, 7, cfg)
        eski = T.rastgele_giris(ts, m, 200, 7)
    finally:
        m.close()
    assert yeni["masraf_modeli"] == "kagit_config" and eski["masraf_modeli"] == "k2_varsayilan" and eski["eski_masraf"] is None
    assert yeni["eski_masraf"]["rastgele_ort_toplam_r"] == pytest.approx(eski["rastgele_ort_toplam_r"])   # yan yana eski = eski sonuc
    assert yeni["rastgele_ort_toplam_r"] < eski["rastgele_ort_toplam_r"]                                   # pahali masraf rakibi dusurur
    assert "FONLAMA" in yeni["not"]


# ---------------------------------------------------------------- Yeni fikirler 1-6 (ek bolumler)
def _seri(netler, **kw):
    return [mk(i, net=v, entry_ms=T0 + (40 + i * 24) * H, **kw) for i, v in enumerate(netler)]   # pnl = net * 10, kasa0 1000


def test_baslangic_en_kotu_dusus():
    ts = _seri([1, 1, -5, -5, 1, 1])
    r = T.baslangic_en_kotu_dusus(ts, 1000.0)
    # pnl: +10 +10 -50 -50 +10 +10. ilk islemden: tepe 1020, dip 920 -> 100/1020; 3. islemden baslasak: 1000 -> 950 -> 900: %10
    assert r["durum"] == "ok" and r["n"] == 6 and r["baslangic_sayisi"] == 6
    assert r["gercek_ilk_islemden"] == pytest.approx(100.0 / 1020.0)
    assert r["en_kotu"] == pytest.approx(max(100.0 / 1020.0, 0.10)) and r["en_iyi"] == pytest.approx(0.0)
    assert r["en_kotu_baslangic"]["trade_id"] == 2
    assert T.baslangic_en_kotu_dusus([], 1000.0)["durum"] == "veri_yok"


def test_kosu_testi_yetersiz_ve_kumelenme():
    assert T.kosu_testi(_seri([1, -1] * 10))["durum"] == "yetersiz_ornek"            # n=20 < 30
    kume = T.kosu_testi(_seri([1.0] * 20 + [-1.0] * 20))                              # 2 koşu: aşırı kümelenme
    assert kume["durum"] == "ok" and kume["kosu"] == 2 and kume["z"] < -5 and kume["p"] < 0.001 and "kümeleniyor" in kume["yorum"]
    alt = T.kosu_testi(_seri([1.0, -1.0] * 20))                                       # 40 koşu: aşırı dönüşümlü
    assert alt["kosu"] == 40 and alt["z"] > 5
    assert T.kosu_testi(_seri([1.0] * 40))["durum"] == "tek_sinif"
    # el hesabı: n1=n2=20 -> mu = 21, var = 2*400*(800-40)/(1600*39)
    assert kume["beklenen_kosu"] == pytest.approx(21.0)


def test_tf_masraf_tablosu():
    a = [mk(i, net=1.0, cost=0.5) for i in range(3)]                  # brüt 1.5 R, masraf 0.5 R
    b = [dict(mk(10 + i, net=-0.2, cost=0.3), tf="15m") for i in range(2)]   # brüt 0.2, masraf 0.6
    c = [dict(mk(20, net=-1.0, cost=0.2), tf="1d")]                  # brüt -0.8: oran yok
    r = T.tf_masraf_tablosu(a + b + c)
    s = {x["tf"]: x for x in r["satirlar"]}
    assert [x["tf"] for x in r["satirlar"]] == ["15m", "1h", "1d"]
    assert s["1h"]["n"] == 3 and s["1h"]["brut_r"] == pytest.approx(4.5) and s["1h"]["masraf_r"] == pytest.approx(1.5)
    assert s["1h"]["net_r"] == pytest.approx(3.0) and s["1h"]["masraf_brut_orani"] == pytest.approx(1.5 / 4.5)
    assert s["15m"]["masraf_brut_orani"] == pytest.approx(0.6 / 0.2)
    assert s["1d"]["masraf_brut_orani"] is None and s["1d"]["etiket"] == T.YETERSIZ


def test_verimlilik():
    # brüt R = net + cost = 1.1 (cost 0.1); mfe 1.5, mae 0.2 -> cikis (1.1+0.2)/1.7, giris 1.5/1.7
    ts = [mk(1, net=1.0, mfe=1.5), dict(mk(2, net=1.0), mfe_r=None)]
    r = T.verimlilik(ts)
    assert r["n"] == 2 and r["n_mfe_mae_var"] == 1 and r["n_mfe_mae_yok"] == 1
    assert r["cikis_verimi"] == pytest.approx(1.3 / 1.7) and r["giris_verimi"] == pytest.approx(1.5 / 1.7)
    assert r["ort_geri_verme_r"] == pytest.approx(0.4) and r["kazananlarda_gerceklesen_mfe_orani"] == pytest.approx(1.1 / 1.5)
    assert r["etiket"] == T.YETERSIZ


def test_toparlanma():
    # kasa: 1000 -> +10 +10 (zirve 1020, i=1) -> -30 (990) -> +5 (995) -> +5 (1000)  ... hâlâ altında
    ts = _seri([1, 1, -3, 0.5, 0.5])
    r = T.toparlanma(ts, 1000.0)
    assert r["durum"] == "ok" and r["su_an_dususte"] is True and r["simdi"]["islem"] == 3 and r["simdi"]["bitti"] is False
    assert r["en_uzun"]["islem"] == 3 and r["en_uzun"]["bitti"] is False and r["kasa_son"] == pytest.approx(1000.0)
    ts2 = _seri([1, 1, -1, 3])                          # 1020 -> 1010 -> 1040: düşüş 2 işlemde bitti
    r2 = T.toparlanma(ts2, 1000.0)
    assert r2["su_an_dususte"] is False and r2["en_uzun"]["islem"] == 2 and r2["en_uzun"]["bitti"] is True
    assert r2["en_uzun"]["gun"] == pytest.approx(2.0)   # zirve 2. işlemin çıkışı, toparlanma 4. işlemin çıkışı: 2 x 24 saat
    assert T.toparlanma([], 1000.0)["durum"] == "veri_yok"


def test_ek_bolumler_raporda_ve_md(tmp_path):
    d = T.rapor(trades_mix(20), [], None, kasa0=1000.0, now=NOW, runs=5000)
    assert set(d["ek_bolumler"]) == {"baslangic_dusus", "kosu_testi", "tf_masraf", "verimlilik", "toparlanma"}
    json.dumps(d)
    md = T.render_md(d)
    for baslik in ("## 7. Başlangıç noktasına göre", "## 8. Kazanç/kayıp koşu testi", "## 9. Zaman dilimi × masraf",
                   "## 10. Giriş/çıkış verimliliği", "## 11. Düşüşten toparlanma"):
        assert baslik in md
    assert "(n=20" in md and "Süzgeç puanı" not in md
