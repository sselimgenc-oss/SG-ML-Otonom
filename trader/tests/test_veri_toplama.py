"""Veri toplama (haber + piyasa pozisyonu): YALNIZ KAYIT. Cozucu, tekillestirme, yalniz-ekleme ve 'karar girdisi degil' korumasi (docs/veri-toplama-spec.md)."""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from trader_core import veri_haber as H
from trader_engine.marketdata import oi_collector as C
from trader_engine.marketdata import veri_piyasa as V

ROOT = Path(__file__).resolve().parent.parent
SIMDI = int(datetime(2026, 11, 23, 12, 0, tzinfo=UTC).timestamp() * 1000)
FNG = {"data": [{"value": "25", "value_classification": "Extreme Fear", "timestamp": "1763769600"},
                {"value": "31", "value_classification": "Fear", "timestamp": "1763683200"},
                {"value": "999", "value_classification": "x", "timestamp": "1"}]}


def _rss(*oge) -> bytes:
    g = "".join(f"<item><title>{b}</title><link>{l}</link><pubDate>{t}</pubDate>" + (f"<description>{d}</description>" if d else "") + "</item>"
                for b, l, t, d in oge)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{g}</channel></rss>'.encode()


PUB = "Mon, 23 Nov 2026 10:00:00 +0000"
RSS = _rss(("Bitcoin surges", "https://x/a", PUB, "<p>Ozet &amp; <b>yazi</b></p>"), ("ETH news", "https://x/b", "bozuk tarih", ""), ("", "https://x/c", PUB, ""))


def _betik(ad):
    s = importlib.util.spec_from_file_location(ad, ROOT / "scripts" / f"{ad}.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


# ---------------------------------------------------------------- haber
def test_rss_ham_alanlar_ve_fng_cozumu():
    r = H.rss_coz(RSS, "cd", SIMDI)
    assert len(r) == 2                                              # bos baslik atilir
    assert r[0] == {"ts": SIMDI - 2 * 3600_000, "alim": SIMDI, "kaynak": "cd", "baslik": "Bitcoin surges", "baglanti": "https://x/a", "ozet": "Ozet & yazi"}
    assert r[1]["ts"] == SIMDI and "ozet" not in r[1]              # tarih bozuk -> alim zamani
    assert not any(k in r[0] for k in ("ton", "etiket", "duygu"))   # yalniz ham alanlar
    f = H.duygu_coz(FNG, SIMDI)
    assert [x["deger"] for x in f] == [31, 25] and f[1]["sinif"] == "Extreme Fear" and f[1]["ts"] == 1763769600_000
    assert H.duygu_coz({"bozuk": 1}, SIMDI) == [] and H.duygu_coz(None, SIMDI) == []
    assert H.rss_coz(b"<rss><item>", "x", SIMDI) == []
    assert H.rss_coz(b'<!DOCTYPE x [<!ENTITY a "b">]><rss/>', "x", SIMDI) == []


def test_haber_tekillestirme_ve_yalniz_ekleme(tmp_path):
    d = tmp_path / "haber"
    o = H.topla(d, SIMDI, lambda u: FNG, lambda u: RSS, kaynaklar={"cd": "https://a"})
    assert o == {"haber": 2, "fng": 2, "hata": 0}
    ilk = (d / "haber.jsonl").read_bytes(), (d / "fng.jsonl").read_bytes()
    o2 = H.topla(d, SIMDI + 3600_000, lambda u: FNG, lambda u: RSS, kaynaklar={"cd": "https://a"})
    assert o2 == {"haber": 0, "fng": 0, "hata": 0}                 # ayni ogeler tekrar yazilmaz
    assert (d / "haber.jsonl").read_bytes() == ilk[0] and (d / "fng.jsonl").read_bytes() == ilk[1]
    yeni = _rss(("Bitcoin surges", "https://x/a", PUB, ""), ("Yeni haber", "https://x/n", PUB, ""))
    H.topla(d, SIMDI + 7200_000, lambda u: FNG, lambda u: yeni, kaynaklar={"cd": "https://a", "ct": "https://b"})
    b = (d / "haber.jsonl").read_bytes()
    assert b.startswith(ilk[0])                                    # onceki bayt dizisi AYNEN korunur; yalniz sona eklendi
    satirlar = [json.loads(s) for s in b.decode().splitlines()]
    assert sum(1 for s in satirlar if s["kaynak"] == "ct") == 2 and len(satirlar) == 5     # ayni oge farkli kaynakta ayri; ayni kaynakta tek


def test_kaynak_hatasi_yutulur_digerleri_surer(tmp_path):
    def gm(u):
        if "bad" in u:
            raise OSError("ag")
        return RSS

    o = H.topla(tmp_path, SIMDI, lambda u: (_ for _ in ()).throw(OSError("x")), gm, kaynaklar={"bad": "https://bad", "ok": "https://ok"})
    assert o["haber"] == 2 and o["hata"] == 2 and not (tmp_path / "fng.jsonl").exists()


def test_haber_betigi_cikis_kodu(tmp_path):
    m = _betik("haber_run")
    assert m.kos(tmp_path / "veri" / "haber", SIMDI, lambda u: FNG, lambda u: RSS) == 0
    assert (tmp_path / "veri" / "haber" / "haber.jsonl").exists()


# ---------------------------------------------------------------- piyasa
H1 = 3_600_000
T0 = SIMDI - SIMDI % H1


def _hist(ts_list, a="longShortRatio"):
    return [{"symbol": "BTCUSDT", "timestamp": t, a: "1.5", "longAccount": "0.6", "shortAccount": "0.4",
             "sumOpenInterest": "10.5", "sumOpenInterestValue": "1000", "buySellRatio": "1.1", "buyVol": "5", "sellVol": "4"} for t in ts_list]


class FakeClient:
    def __init__(self):
        self.calls, self.requests_made, self.last_used_weight = [], 0, None

    def get_json(self, path, params):
        self.calls.append((path, dict(params)))
        self.requests_made += 1
        if path == "/fapi/v1/fundingRate":
            return [{"symbol": "BTCUSDT", "fundingTime": T0 - 8 * H1, "fundingRate": "0.0001", "markPrice": "100"}]
        lo, hi = params["startTime"], params["endTime"]
        return _hist([t for t in range(T0 - 40 * 24 * H1, T0 + H1 + 1, H1) if lo <= t <= hi][:params["limit"]])


def test_piyasa_cozucu():
    r = V.parse_hist("oi", _hist([T0]))
    assert r == [{"ts": T0, "oi": 10.5, "oi_value": 1000.0}]
    assert V.parse_hist("taker", _hist([T0]))[0] == {"ts": T0, "ratio": 1.1, "buy": 5.0, "sell": 4.0}
    assert V.parse_hist("gls", [{"timestamp": "x"}, {"timestamp": T0}]) == []
    assert V.parse_funding([{"fundingTime": 5, "fundingRate": "-0.0002", "markPrice": "9"}, {"fundingTime": 6}]) == [{"ts": 5, "rate": -0.0002, "mark": 9.0}]
    with pytest.raises(C.CollectorError):
        V.parse_hist("oi", {"code": -1})


def test_piyasa_geri_doldurma_tekillestirme_yalniz_ekleme(tmp_path):
    kok = tmp_path / "piyasa"
    cl = FakeClient()
    st = V.collect(kok, cl, ["BTC/USDT"], SIMDI)
    assert st.errors == 0 and st.rows > 0
    paths = {c[0] for c in cl.calls}
    assert paths == {"/futures/data/openInterestHist", "/futures/data/globalLongShortAccountRatio",
                     "/futures/data/topLongShortPositionRatio", "/futures/data/takerlongshortRatio", "/fapi/v1/fundingRate"}
    assert all(c[1]["period"] == "1h" for c in cl.calls if c[0].startswith("/futures/data"))
    dosya = kok / "oi" / "BTCUSDT.jsonl"
    satirlar = [json.loads(s) for s in dosya.read_text().splitlines()]
    ts = [s["ts"] for s in satirlar]
    assert ts == sorted(set(ts))                                   # tekil, artan
    assert max(ts) <= SIMDI - H1                                   # kapanmamis saat yok
    assert not any(C.in_holdout(t) for t in ts)                    # kilitli donem yazilmaz
    assert min(ts) >= SIMDI - C.LOOKBACK_MS
    assert json.loads((kok / "funding" / "BTCUSDT.jsonl").read_text().splitlines()[0]) == {"mark": 100.0, "rate": 0.0001, "ts": T0 - 8 * H1}
    onceki = {p: p.read_bytes() for p in kok.rglob("*.jsonl")}
    cl2 = FakeClient()
    st2 = V.collect(kok, cl2, ["BTC/USDT"], SIMDI)                 # ikinci tur: yeni veri yok
    assert st2.rows == 0 and {p: p.read_bytes() for p in kok.rglob("*.jsonl")} == onceki
    assert all(c[1]["startTime"] > min(ts) + 24 * H1 for c in cl2.calls)       # yalniz son satirdan sonrasi istenir (geri doldurma yok)
    st3 = V.collect(kok, FakeClient(), ["BTC/USDT"], SIMDI + 2 * H1)           # 2 saat sonra: yalniz sona eklenir
    assert st3.rows > 0
    yeni = dosya.read_bytes()
    assert yeni.startswith(onceki[dosya]) and len(yeni) > len(onceki[dosya])


def test_ekle_yalniz_sona_ve_yarim_satir(tmp_path):
    p = tmp_path / "x" / "BTCUSDT.jsonl"
    assert V.ekle(p, [{"ts": 2, "a": 1}, {"ts": 1, "a": 1}, {"ts": 2, "a": 9}]) == 2          # siralanir, ayni ts tek
    assert V.ekle(p, [{"ts": 1, "a": 5}, {"ts": 2, "a": 5}]) == 0                              # eski/ayni ts: yok sayilir, degistirilmez
    govde = p.read_bytes()
    p.write_bytes(govde + b'{"ts":3,"a"')                                                      # guc kesintisi: yarim satir
    assert V.son_ts(p) == 2
    assert V.ekle(p, [{"ts": 4, "a": 1}]) == 1
    assert p.read_bytes().startswith(govde + b'{"ts":3,"a"\n')


def test_piyasa_ban_durumunda_istek_yok(tmp_path, monkeypatch):
    m = _betik("piyasa_veri_run")
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "engine.base.json").write_text(json.dumps({"pairs": ["BTC/USDT"], "market_db": "var/market.sqlite"}))
    (cfg / "engine.paper.json").write_text(json.dumps({"pairs": ["BTC/USDT", "NVDA/USDT"], "optional_pairs": ["NVDA/USDT"]}))
    assert m.kripto_ciftleri(cfg)[0] == ["BTC/USDT"]
    cl = FakeClient()
    assert m.main(["--config-dir", str(cfg), "--var-dir", str(tmp_path / "var")], client=cl, now_ms=SIMDI) == 0
    assert (tmp_path / "var" / "veri" / "piyasa" / "oi" / "BTCUSDT.jsonl").exists()


def test_gercek_yapilandirmada_19_kripto_cifti():
    m = _betik("piyasa_veri_run")
    pairs, _ = m.kripto_ciftleri(ROOT / "config")
    assert len(pairs) == 19 and "BTC/USDT" in pairs and "NVDA/USDT" not in pairs


# ---------------------------------------------------------------- koruma: karar girdisi degil
_YASAK = re.compile(r"var/veri|veri_haber|veri_piyasa|haber\.jsonl|fng\.jsonl|\"veri\"\s*/\s*\"(haber|piyasa)\"|'veri'\s*,\s*'(haber|piyasa)'")
_IZINLI = {"trader_engine/marketdata/veri_piyasa.py"}        # yazan toplayici (kendisi)


def test_motor_veri_dizinlerini_okumaz_ve_toplayicilari_almaz():
    src = ROOT / "src"
    bulunan = []
    for p in (src / "trader_engine").rglob("*.py"):
        rel = p.relative_to(src).as_posix()
        if rel in _IZINLI:
            continue
        t = p.read_text(encoding="utf-8")
        if _YASAK.search(t):
            bulunan.append(rel)
    assert bulunan == [], f"motor modulu veri toplama ciktisina bakiyor: {bulunan}"
    # toplayici modulu motorun baska hicbir parcasindan, ML'den ya da cekirdekten ice alinmaz
    for kok in ("trader_engine", "trader_core", "trader_ml", "trader_panel"):
        for p in (src / kok).rglob("*.py"):
            if p.relative_to(src).as_posix() in _IZINLI | {"trader_core/veri_haber.py"}:
                continue
            t = p.read_text(encoding="utf-8")
            assert not re.search(r"\bveri_haber\b|\bveri_piyasa\b|marketdata\.veri|import veri_", t), p.name


def test_oi_toplayicisi_ve_veri_piyasa_ayri():
    assert "veri_piyasa" not in (ROOT / "src/trader_engine/marketdata/oi_collector.py").read_text(encoding="utf-8")
