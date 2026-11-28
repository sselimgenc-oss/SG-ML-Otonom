"""ML1 golge (sanal) ogrenme (27.11 sahip karari): simulasyon + ogrenici birim testleri (sentetik mum, ag yok)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("pyarrow")

from trader_core import ml1_gorunum as MG  # noqa: E402
from trader_core import risk  # noqa: E402
from trader_engine import ml1_ogren as OG  # noqa: E402
from trader_engine import ml1_sanal as SN  # noqa: E402
from trader_engine.config import ConfigError, _build_ml1  # noqa: E402
from trader_ml.ml1 import model as M  # noqa: E402

UTC = timezone.utc
D0 = pd.Timestamp("2026-11-20 08:00", tz="UTC")
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
K = len(M.feature_names())
MAL0 = SN.Maliyet(0.0, 0.0, 0.0, 0.0)
MAL = SN.Maliyet()


def _b15(rows, start=D0):
    idx = pd.DatetimeIndex([start + pd.Timedelta(minutes=15 * i) for i in range(len(rows))])
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"], dtype=float)


def _duz(n, p=100.0):
    return [(p, p + 0.1, p - 0.1, p)] * n


def _rec(**kw):
    d = {"side": "long", "tf": "1h", "mod": "target", "stop": 99.0, "target": 102.0, "entry_ref": 100.0, "decision_ts": D0.isoformat(),
         "time_stop": 48, "trail_atr": 2.0}
    d.update(kw)
    return d


def _sim(rec, rows, mal=MAL, trig=None, simdi=None):
    return SN.simule(rec, _b15(rows), trig, mal, [], simdi or (D0 + pd.Timedelta(days=40)))


def test_long_stop_vurdu_stop_fiyatindan_ve_negatif():
    r = _sim(_rec(), _duz(3) + [(100, 100.2, 98.5, 99.0)] + _duz(2))
    assert r.exit_reason == "stop" and r.y == 0 and -1.1 < r.r_net < -0.9 and not r.kesildi        # stop kaybi + maliyet
    assert r.exit_ts == D0 + pd.Timedelta(minutes=45)


def test_short_stop_vurdu():
    r = _sim(_rec(side="short", stop=101.0, target=98.0), _duz(2) + [(100, 101.5, 99.9, 101.0)])
    assert r.exit_reason == "stop" and r.y == 0 and r.r_net < -0.9


def test_gap_stopta_acilistan_dolar():
    r = _sim(_rec(), _duz(2) + [(98.0, 98.5, 97.0, 97.5)], mal=MAL0)
    assert r.exit_reason == "stop" and r.r_net == pytest.approx(-2.0 / risk.loss_at_stop(1.0, 100.0, 99.0, risk.LOCKED_CFG) * 1.0, rel=1e-6)


def test_hedef_vurdu_long_ve_short_pozitif():
    r = _sim(_rec(), _duz(2) + [(100, 102.5, 99.8, 102.0)])
    assert r.exit_reason == "target" and r.y == 1 and r.r_net > 0
    r = _sim(_rec(side="short", stop=101.0, target=98.0), _duz(2) + [(100, 100.1, 97.5, 98.0)])
    assert r.exit_reason == "target" and r.y == 1


def test_ayni_mumda_stop_ve_hedef_stop_once():
    r = _sim(_rec(), [(100, 102.5, 98.5, 100.0)])
    assert r.exit_reason == "stop" and r.y == 0


def test_maliyet_uygulanir_ve_etiket_isareti():
    rows = _duz(2) + [(100, 102.5, 99.8, 102.0)]
    sifir, tam = _sim(_rec(), rows, mal=MAL0), _sim(_rec(), rows)
    risk_u = risk.loss_at_stop(1.0, 100.0, 99.0, risk.LOCKED_CFG)
    assert sifir.r_net == pytest.approx(2.0 / risk_u, rel=1e-9)                    # maliyetsiz: brut / planli risk
    beklenen = (2.0 - 0.0002 * 100 - 0.0005 * (100 * 1.0002 + 102.0 * 0.9998) - 0.0) / risk_u
    assert tam.r_net < sifir.r_net and tam.r_net == pytest.approx((102.0 * 0.9998 - 100 * 1.0002 - 0.0005 * (100 * 1.0002 + 102.0 * 0.9998)) / risk_u, rel=1e-9)
    assert beklenen > 0
    # kucuk kazanc maliyetle negatife donerse etiket 0
    dar = _sim(_rec(target=100.03), _duz(1) + [(100, 100.05, 99.95, 100.03)])
    assert dar.exit_reason == "target" and dar.r_net < 0 and dar.y == 0


def test_funding_dusulur():
    rec = _rec(stop=50.0, target=500.0, time_stop=9)
    risk_u = risk.loss_at_stop(1.0, 100.0, 50.0, risk.LOCKED_CFG)
    sade = SN.simule(rec, _b15(_duz(37)), None, MAL0, [], D0 + pd.Timedelta(days=1))
    fon = SN.simule(rec, _b15(_duz(37)), None, MAL0, [(D0 + pd.Timedelta(hours=8), 0.001, 100.0)], D0 + pd.Timedelta(days=1))
    assert sade.exit_reason == fon.exit_reason == "time_stop"
    assert sade.r_net - fon.r_net == pytest.approx(0.1 / risk_u, rel=1e-9)                # long 0.001 x 100 oder
    kisa = SN.simule(rec, _b15(_duz(37)), None, MAL0, [(D0 + pd.Timedelta(hours=8), -0.001, 100.0)], D0 + pd.Timedelta(days=1))
    assert kisa.r_net > sade.r_net                                                          # negatif oran: long alir


def test_zaman_stopu_tf_kapanisi_sonraki_acilista():
    r = _sim(_rec(time_stop=2, stop=50.0, target=500.0), _duz(9), mal=MAL0)           # 2 x 1h = 8 x 15 dk; cikis 9. mumun acilisinda
    assert r.exit_reason == "time_stop" and r.exit_ts == D0 + pd.Timedelta(hours=2) and r.kesildi is False
    assert _sim(_rec(time_stop=2, stop=50.0, target=500.0), _duz(8)) is None          # sonraki mum henuz yok: bekler


def test_iz_suren_stop_yolu_ve_tf_kapanisinda_piyasa_cikisi():
    n = 12
    idx = pd.DatetimeIndex([D0 + pd.Timedelta(hours=i) for i in range(n)])
    hi = [100.3, 103.0, 105.0, 105.0, 105.0, 105.0] + [105.0] * 6
    lo = [99.9, 100.0, 103.0, 103.0, 102.0, 99.0] + [99.0] * 6
    cl = [100.0, 102.5, 104.5, 104.0, 101.5, 99.5] + [99.5] * 6
    trig = pd.DataFrame({"high": hi, "low": lo, "close": cl, "atr_tf": 1.0, "regime": "range"}, index=idx)
    # 15 dk izgara: ilk 4 saat sakin, 5. saatin kapanisinda iz stopu (105 - 2*1 = 103) kapanisi (101.5) astigi icin piyasa cikisi
    rows = []
    for i in range(n * 4):
        h = i // 4
        rows.append((cl[h - 1] if h and i % 4 == 0 else cl[h], hi[h] if i % 4 == 1 else cl[h] + 0.05, lo[h] if i % 4 == 2 else cl[h] - 0.05, cl[h]))
    r = SN.simule(_rec(mod="trail", target=None, stop=99.0), _b15(rows), trig, MAL0, [], D0 + pd.Timedelta(days=2))
    assert r is not None and r.exit_reason == "trail_stop" and not r.kesildi
    path = SN.S.trail_stop_path("long", 100.0, 99.0, trig["high"].to_numpy(), trig["low"].to_numpy(), trig["atr_tf"].to_numpy(), 2.0).to_numpy()
    assert path[4] > 99.0 and path[4] >= cl[4]                                      # iz stopu kuruldu ve 5. kapanista asildi
    assert r.r_net > 0 or r.exit_reason == "stop"


def test_ufuk_kesilir_son_fiyattan_ve_etikete_dahil():
    n = 30 * 96 + 4
    idx = pd.DatetimeIndex([D0 + pd.Timedelta(hours=i) for i in range(30 * 24 + 2)])
    trig = pd.DataFrame({"high": 100.1, "low": 99.9, "close": 100.0, "atr_tf": 1.0, "regime": "range"}, index=idx)
    r = SN.simule(_rec(mod="trail", target=None, stop=95.0), _b15(_duz(n)), trig, MAL, [], D0 + pd.Timedelta(days=32))
    assert r is not None and r.exit_reason == "kesildi" and r.kesildi is True and r.y in (0, 1)
    assert r.exit_ts <= D0 + pd.Timedelta(days=30, minutes=15)
    # veri ufka yetmiyorsa ve zaman dolmadiysa bekler
    assert SN.simule(_rec(mod="trail", target=None, stop=95.0), _b15(_duz(200)), trig, MAL, [], D0 + pd.Timedelta(days=10)) is None


def test_ilk_mum_yoksa_bekler():
    assert SN.simule(_rec(), _b15(_duz(3), start=D0 + pd.Timedelta(minutes=15)), None, MAL, [], NOW) is None


# ================================================================================================================ ogrenici
class SahteDefter:
    def __init__(self):
        self.kapanan = []

    def kapat(self, tid, did, pair, side, r, exit_ts):
        self.kapanan.append(SimpleNamespace(trade_id=tid, decision_id=did, pair=pair, side=side, r_multiple=r, exit_ts=exit_ts, exit_reason="stop"))

    def list_closed_trades(self, since=None, until=None, limit=200):
        return [t for t in self.kapanan if (since is None or t.exit_ts >= since) and (until is None or t.exit_ts < until)][:limit]


class SahteView:
    """15 dk sabit seri; `satirlar(pair)` ile yukseltilebilir; hedef yoluna giden fiyat veya duz."""

    def __init__(self, hedef_yukari=True):
        self.yukari = hedef_yukari
        self.cagri = 0

    def bars(self, pair, tf, until, n=None, kind="last"):
        self.cagri += 1
        assert tf == "15m"
        until = pd.Timestamp(until)
        last = until.floor("15min") - pd.Timedelta(minutes=15)
        idx = pd.date_range(end=last, periods=n, freq="15min", tz="UTC") if n else pd.DatetimeIndex([])
        p = np.where(idx >= D0 + pd.Timedelta(minutes=30), 103.0 if self.yukari else 98.0, 100.0)
        return pd.DataFrame({"open": p, "high": p + 0.1, "low": p - 0.1, "close": p, "volume": 1.0}, index=idx)

    def funding(self, pair, a, b):
        return []


def _cfg(view=None, tavan=5000, butce=40):
    return SN.SanalCfg(view=view or SahteView(), maliyet_fn=lambda p, t: MAL, tavan=tavan, butce=butce,
                       kontrol_aralik=pd.Timedelta(0))


def _og(tmp, defter=None, **kw):
    kw.setdefault("sinama", False)
    kw.setdefault("sanal", _cfg())
    og = OG.Ml1Ogrenici(tmp / "og", tmp / "models" / "ml1_package.json", now_fn=lambda: NOW, ledger=defter or SahteDefter(), **kw)
    assert og.baslat(NOW)
    return og


def _aday(arm="T1@1h", side="long", tf="1h", skor=None, pair="BTC/USDT", rng=None):
    rng = rng or np.random.default_rng(0)
    return {"pair": pair, "tf": tf, "setup": arm.split("@")[0], "arm_id": arm, "group": "PULLBACK_1LEG", "side": side, "entry_ref": 100.0, "stop": 99.0,
            "target": 102.0, "stop_dist_atr": 1.0, "oz": 1, "x": [float(v) for v in rng.normal(size=K)], "skor": skor, "mod": "target",
            "time_stop": 48, "trail_atr": 2.0}


def test_olay_basina_bir_sanal_en_yuksek_puanli():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        og = _og(Path(t))
        D = D0.to_pydatetime()
        n = og.sanal_adaylar(D, [_aday("T1@1h", skor=0.4), _aday("TF1@1h", skor=0.7), _aday("H2@1h", skor=0.5), _aday("T1@4h", tf="4h"),
                                 _aday("T1@1h", side="short")])
        assert n == 3                                                                   # (long,1h), (long,4h), (short,1h): her olay icin bir
        assert {r["arm_id"] for r in og.sanal_bekleyen.values() if r["tf"] == "1h" and r["side"] == "long"} == {"TF1@1h"}
        # ayni olayin sonraki adimlari (K mum icinde, zincir) yeni sanal uretmez
        assert og.sanal_adaylar(D + timedelta(hours=1), [_aday("T1@1h")]) == 0
        assert og.sanal_adaylar(D + timedelta(hours=4), [_aday("T1@1h")]) == 0          # zincir bosluk <= K mum: ayni olay
        # K mumdan uzun bosluk: yeni olay
        assert og.sanal_adaylar(D + timedelta(hours=4 + 3 * 1 + 1), [_aday("T1@1h")]) == 1
        assert len(list((Path(t) / "og").glob("sanallar-*.jsonl"))) == 1


def test_alinan_olay_icin_sanal_yok_ve_bekleyen_iptal():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        og = _og(Path(t))
        D = D0.to_pydatetime()
        assert og.sanal_adaylar(D, [_aday()]) == 1
        og.sanal_giris("BTC/USDT", "long", "1h", D + timedelta(hours=1))               # ayni olayda gercek giris: bekleyen iptal
        assert not og.sanal_bekleyen and og.sayac["sanal_iptal_giris"] == 1
        assert og.sanal_adaylar(D + timedelta(hours=2), [_aday()]) == 0                # girisli olay zinciri: sanal yok
        og.sanal_giris("ETH/USDT", "long", "1h", D)                                    # baska cift: etkilenmez
        assert og.sanal_adaylar(D + timedelta(hours=1), [_aday(pair="SOL/USDT")]) == 1


def test_tavan_asilinca_yeni_sanal_alinmaz():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        og = _og(Path(t), sanal=_cfg(tavan=2))
        D = D0.to_pydatetime()
        og.sanal_adaylar(D, [_aday(pair=f"P{i}/USDT") for i in range(5)])
        assert len(og.sanal_bekleyen) == 2 and og.sayac["sanal_tavan"] == 3


def test_coz_etiketler_sayar_ve_defter_tablolarina_girmez(tmp_path):
    defter = SahteDefter()
    og = _og(tmp_path, defter, min_islem=1000)
    og.sanal_adaylar(D0.to_pydatetime(), [_aday(pair="A/USDT"), _aday(pair="B/USDT")])
    assert og.sanal_coz(NOW) == 2
    assert og.n_kapali == 2 and og.n_sanal == 2 and not og.sanal_bekleyen and og.n_tf["1h"] == 2
    assert [bool(s[7]) for s in og._sn] == [True, True] and [s[2] for s in og._sn] == [1.0, 1.0]       # hedef: y=1
    assert defter.kapanan == [] and og.bekleyen == {} and not list((tmp_path / "og").glob("alinanlar-*"))
    d, X = og._tampon()
    assert d["sanal"].tolist() == [True, True] and X.shape == (2, K)
    og.adim(NOW)
    dur = json.loads((tmp_path / "og" / "durum.json").read_text())
    assert (dur["kapali_islem"], dur["gercek"], dur["sanal"], dur["bekleyen_sanal"]) == (2, 0, 2, 0) and dur["sanal_agirlik"] == 1.0
    # kayip yonu: y=0
    og2 = _og(tmp_path / "b", sanal=_cfg(SahteView(hedef_yukari=False)))
    og2.sanal_adaylar(D0.to_pydatetime(), [_aday()])
    og2.sanal_coz(NOW)
    assert og2._sn[0][2] == 0.0 and og2.n_sanal == 1


def test_gercek_arti_sanal_min_islem_ve_paket(tmp_path):
    defter = SahteDefter()
    og = _og(tmp_path, defter, min_islem=6)
    rng = np.random.default_rng(3)
    for i in range(3):                                                                # 3 gercek
        ts = NOW - timedelta(days=4, hours=7 * i)
        og.islem_alindi({"pair": "BTC/USDT", "tf": "1h", "setup": "T1", "arm_id": "T1@1h", "group": "G", "side": "long", "entry_ref": 100.0, "stop": 99.0,
                         "target": None, "stop_dist_atr": 1.0, "decision_ts": ts.isoformat(), "decision_id": 10 + i, "trade_id": 10 + i,
                         "x": [float(v) for v in rng.normal(size=K)]})
        defter.kapat(10 + i, 10 + i, "BTC/USDT", "long", 0.8 if i % 2 else -1.0, NOW - timedelta(hours=1))
    for i in range(3):                                                                # 3 sanal
        og.sanal_adaylar((D0 + timedelta(hours=10 * i)).to_pydatetime(), [_aday(pair=f"S{i}/USDT", rng=rng)])
    pk = tmp_path / "models" / "ml1_package.json"
    og.adim(NOW)
    assert og.n_kapali == 6 and og.n_sanal == 3 and og.n_kapali - og.n_sanal == 3     # gercek + sanal etiketli satirlar min_islem'e sayilir
    assert og.esik_asildi() and (pk.exists() or og.sayac["uydurulamadi"])
    assert og.sanal_bekleyen == {}


def test_yeniden_baslatma_bekleyen_sanallar_kalir_ve_cift_sayim_yok(tmp_path):
    og = _og(tmp_path, min_islem=1000)
    og.sanal_adaylar(D0.to_pydatetime(), [_aday(pair="A/USDT"), _aday(pair="B/USDT")])
    sid_b = next(s for s, r in og.sanal_bekleyen.items() if r["pair"] == "B/USDT")
    og.sanal_bekleyen = {s: r for s, r in og.sanal_bekleyen.items()}
    # yalniz A cozulsun
    og.sanal_bekleyen.pop(sid_b)
    assert og.sanal_coz(NOW) == 1
    og.sanal_bekleyen[sid_b] = {}                                                      # (bellek bozulsa bile dosya esastir)
    og2 = _og(tmp_path, min_islem=1000)
    assert set(og2.sanal_bekleyen) == {sid_b} and og2.n_sanal == 1 and og2.n_kapali == 1 and len(og2._sn) == 1
    assert og2.sanal_adaylar(D0.to_pydatetime(), [_aday(pair="B/USDT")]) == 0          # ayni sid tekrar yazilmaz
    assert og2.sanal_coz(NOW) == 1 and og2.n_sanal == 2
    og3 = _og(tmp_path, min_islem=1000)
    assert og3.n_sanal == 2 and not og3.sanal_bekleyen
    # olay zinciri de geri gelir: ayni olayin yeni adayi sanal uretmez
    assert og3.sanal_adaylar(D0.to_pydatetime() + timedelta(hours=1), [_aday(pair="A/USDT")]) == 0


def test_budce_ve_veri_yoksa_bekler(tmp_path):
    v = SahteView()
    og = _og(tmp_path, sanal=_cfg(v, butce=2))
    og.sanal_adaylar(D0.to_pydatetime(), [_aday(pair=f"P{i}/USDT") for i in range(5)])
    assert og.sanal_coz(NOW) == 2 and len(og.sanal_bekleyen) == 3                     # adim butcesi
    assert og.sanal_coz(NOW) == 2 and og.sanal_coz(NOW) == 1


def test_agirlik_etkisi_ve_sanal_sutunu_yoksa_eski_davranis():
    rng = np.random.default_rng(1)
    n = 60
    y = (rng.random(n) < 0.5).astype(float)
    X = rng.normal(size=(n, K))
    X[:, M.feature_names().index("stop_dist_atr")] += 2 * y
    ts = [pd.Timestamp(NOW) - pd.Timedelta(hours=10 * i) for i in range(n)]
    d = pd.DataFrame({"k": [str(i) for i in range(n)], "decision_ts": pd.to_datetime(ts, utc=True), "y": y, "pair": "BTC/USDT", "side": "long", "tf": "1h"})
    a = OG.uydur(d, X, NOW)
    d2 = d.assign(sanal=False)
    assert np.allclose(OG.uydur(d2, X, NOW)["coef"], a["coef"])
    d3 = d.assign(sanal=np.arange(n) % 2 == 0)
    w1, w0 = OG.uydur(d3, X, NOW, sanal_agirlik=1.0), OG.uydur(d3, X, NOW, sanal_agirlik=0.0)
    assert w1["n_etkin"] > w0["n_etkin"] > 0 and not np.allclose(w1["coef"], w0["coef"])
    assert OG.uydur(d.assign(sanal=True), X, NOW, sanal_agirlik=0.0) is None


def test_sinama_gercek_alt_kume_bilgi_amacli():
    rng = np.random.default_rng(2)
    n = 240
    y = (rng.random(n) < 0.5).astype(float)
    X = rng.normal(size=(n, K))
    X[:, M.feature_names().index("stop_dist_atr")] += 2 * y
    ts = [pd.Timestamp(NOW) - pd.Timedelta(hours=10 * (n - i)) for i in range(n)]
    d = pd.DataFrame({"k": [str(i) for i in range(n)], "decision_ts": pd.to_datetime(ts, utc=True), "y": y, "pair": "BTC/USDT", "side": "long", "tf": "1h",
                      "sanal": np.arange(n) % 4 == 0})
    s = OG.sina(d, X, NOW)
    assert s["gecti"] and s["n_sinama_gercek"] >= 20 and s["gercek"]["n"] == s["n_sinama_gercek"] and s["gercek"]["auc"] is not None
    kucuk = OG.sina(d.assign(sanal=True), X, NOW)
    assert kucuk["n_sinama_gercek"] == 0 and "gercek" not in kucuk


def test_sinama_araligi_basarisiz_denemeden_sonra_100_ek_satir(tmp_path):
    rng = np.random.default_rng(5)
    defter = SahteDefter()
    og = _og(tmp_path, defter, min_islem=100, sinama=True, sanal=None)
    pk = tmp_path / "models" / "ml1_package.json"

    def ekle(i):
        ts = NOW - timedelta(hours=2 + (1000 - i))
        y = int(rng.random() < 0.5)
        og.islem_alindi({"pair": "BTC/USDT", "tf": "1h", "setup": "T1", "arm_id": "T1@1h", "group": "G", "side": "long", "entry_ref": 100.0, "stop": 99.0,
                         "target": None, "stop_dist_atr": 1.0, "decision_ts": ts.isoformat(), "decision_id": 1000 + i, "trade_id": 1000 + i,
                         "x": [float(v) for v in rng.normal(size=K)]})
        defter.kapat(1000 + i, 1000 + i, "BTC/USDT", "long", 0.8 if y else -1.0, NOW - timedelta(hours=1))
    for i in range(100):
        ekle(i)
    og.adim(NOW)
    assert og.n_kapali == 100 and og.sayac["sinama_red"] + og.sayac["yazildi"] == 1
    if og.sayac["yazildi"]:
        pytest.skip("rastgele veri sinamayi gecti (tohum)")
    assert og.sonraki_sinama_n == 200 and og.son_sinama["sonraki_sinama_n"] == 200
    dur = json.loads((tmp_path / "og" / "durum.json").read_text())
    assert dur["sonraki_sinama_n"] == 200 and dur["son_sinama"]["gecti"] is False and dur["sinama_aralik"] == 100
    for i in range(100, 199):                                                         # +99 satir: deneme YOK
        ekle(i)
        og.adim(NOW)
    assert og.n_kapali == 199 and og.sayac["sinama_red"] == 1 and og.sayac["sinama_aralik_bekle"] >= 99
    ekle(199)                                                                          # +100: yeni deneme
    og.adim(NOW)
    assert og.n_kapali == 200 and (og.sayac["sinama_red"] + og.sayac["yazildi"]) == 2
    og2 = _og(tmp_path, defter, min_islem=100, sinama=True, sanal=None)               # yeniden baslatma: esik korunur
    assert og2.sonraki_sinama_n == og.sonraki_sinama_n
    assert not pk.exists() or og.sayac["yazildi"]


def test_ayar_dogrulama_sanal_agirlik_ve_sinama_aralik():
    def b(**og):
        return _build_ml1({"aktif": True, "ogrenme": {"aktif": True, **og}})
    assert b(sanal_agirlik=0)["ogrenme"]["sanal_agirlik"] == 0 and b(sanal_agirlik=0.5, sinama_aralik=100)
    for kotu in ({"sanal_agirlik": -0.1}, {"sanal_agirlik": 1.5}, {"sanal_agirlik": True}, {"sanal_agirlik": "1"}, {"sinama_aralik": 0},
                 {"sinama_aralik": 1.5}, {"sinama_aralik": True}):
        with pytest.raises(ConfigError):
            b(**kotu)


def test_durum_satiri_ana_satir_degismez_sanal_notu_yalniz_panelde():
    ogr = MG.ogr_durumu({"asama": "ogrenme", "kapali_islem": 37, "gercek": 20, "sanal": 17, "min_islem": 200}, 0, {}, False)
    oz = {"ogr": ogr}
    assert MG.durum_satiri(oz) == "ML1 öğrenme aşamasında: 37/200 kapanan işlem; puanlama başlamadı"          # gercek/sanal ana satirda YOK
    assert MG.sanal_notu(oz) == "37 içinde sanal: 17"
    assert MG.sanal_notu({"ogr": MG.ogr_durumu({"kapali_islem": 5, "sanal": 0}, 0, {}, False)}) is None
    assert MG.sanal_notu({"ogr": MG.ogr_durumu(None, 0, {}, False)}) is None
    import inspect
    from trader_core import telegram as TG
    assert "sanal_notu" not in inspect.getsource(TG)                                       # Telegram'a sanal gosterimi yok
