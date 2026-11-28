"""P1-b: `golge_gercek` olcumu (gercek islemin golge simulasyonuyla kiyasi) ve esik kurali."""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
pytest.importorskip("pyarrow")

from olcum_destek import D0, Gorunum, islem, sahte_ogren, seri_1dk  # noqa: E402
from trader_engine import ml1_sanal as SN  # noqa: E402
from trader_engine import olcumler as OL  # noqa: E402

MAL = SN.Maliyet()
CFG = {"ogrenme": {"sanal_agirlik": 1.0}}


def _yon(tmp, view, ogren, cfg=CFG):
    y = OL.OlcumYonetici(tmp / "olcum", now_fn=lambda: D0, ml1_cfg=cfg, view=view, ogren=ogren, maliyet_fn=lambda p, t: MAL,
                         trail_atr_fn=lambda: 2.0)
    assert y.baslat(D0)
    return y


def _yukari(n=6 * 60):
    p = [100.0] * 30 + [103.0] * (n - 30)                     # 08:30'dan sonra hedef (102) asilir
    return seri_1dk(p)


def _asagi(n=6 * 60):
    p = [100.0] * 30 + [98.0] * (n - 30)
    return seri_1dk(p)


def _sanal(isl, view, D):
    rec = OL._tamamla(isl, None)
    b15, trig, fon = SN.veri_al(view, rec, D, False)
    return SN.simule(rec, b15, trig, MAL, fon, D)


def test_ayni_yol_dr_sifir(tmp_path):
    view = Gorunum({"BTC/USDT": _yukari()})
    D = D0 + timedelta(hours=6)
    ref = _sanal(islem(), view, D)
    isl = islem(r_net=ref.r_net, y=ref.y, exit_reason=ref.exit_reason)
    s = OL._golge_gercek(_yon(tmp_path, view, sahte_ogren(isl)), isl, D)
    assert s["dr"] == pytest.approx(0.0, abs=1e-9) and s["y_sanal"] == s["y_gercek"] == 1


def test_golge_stop_gercek_kazanmis(tmp_path):
    view = Gorunum({"BTC/USDT": _asagi()})
    isl = islem(r_net=1.0, y=1)
    s = OL._golge_gercek(_yon(tmp_path, view, sahte_ogren(isl)), isl, D0 + timedelta(hours=6))
    assert s["y_sanal"] == 0 and s["y_gercek"] == 1 and s["dr"] < 0 and s["neden_sanal"] == "stop"


def test_veri_yetmiyor_sonra_tek_satir(tmp_path):
    kisa = Gorunum({"BTC/USDT": seri_1dk([100.0] * 10)})
    isl = islem()
    y = _yon(tmp_path, kisa, sahte_ogren(isl))
    D = D0 + timedelta(hours=6)
    assert OL._golge_gercek(y, isl, D) is None
    y.adim(D)
    assert not list((tmp_path / "olcum").glob("satirlar-*.jsonl"))                            # henuz satir yok
    y.view = Gorunum({"BTC/USDT": _yukari()})
    y.adim(D + timedelta(minutes=30))                                                          # 1 saat dolmadi: yeniden denenmez
    assert not list((tmp_path / "olcum").glob("satirlar-*.jsonl"))
    y.adim(D + timedelta(hours=2))
    y.adim(D + timedelta(hours=4))
    satir = [json.loads(x) for f in (tmp_path / "olcum").glob("satirlar-*.jsonl") for x in f.read_text().splitlines()]
    assert [r["olcum"] for r in satir].count("golge_gercek") == 1


def _ozet(satirlar, **cfg):
    y = SimpleYon({"ogrenme": cfg})
    return OL._golge_ozet(y, satirlar)


class SimpleYon:
    def __init__(self, cfg):
        self.ml1_cfg, self.ogren, self._bitti = cfg, sahte_ogren(), {}


def _satirlar(n, uyum, mutlak_dr):
    uyan = round(n * uyum)
    return [{"y_sanal": 1, "y_gercek": 1 if i < uyan else 0, "dr": mutlak_dr * (1 if i % 2 else -1)} for i in range(n)]


def test_esik_kurali():
    assert _ozet(_satirlar(29, 0.1, 1.0))["agirlik_dusur"] is False                            # n < 30
    o = _ozet(_satirlar(30, 0.80, 0.1))
    assert o["agirlik_dusur"] is True and o["sanal_agirlik_etkin"] == 0.5
    assert _ozet(_satirlar(30, 0.90, 0.31))["agirlik_dusur"] is True
    o = _ozet(_satirlar(30, 0.90, 0.29))
    assert o["agirlik_dusur"] is False and o["sanal_agirlik_etkin"] == 1.0
    assert _ozet(_satirlar(40, 0.85, 0.1))["agirlik_dusur"] is False                           # uyum tam esikte
    assert _ozet(_satirlar(40, 0.95, 0.30))["agirlik_dusur"] is False                          # |dr| tam esikte
    assert _ozet(_satirlar(30, 0.1, 1.0), kiyas_min_n=31)["agirlik_dusur"] is False            # ayardan


def test_sanal_agirlik_ayari_dusukse_yukselmez():
    o = _ozet(_satirlar(30, 0.5, 1.0), sanal_agirlik=0.3)
    assert o["agirlik_dusur"] is True and o["sanal_agirlik_etkin"] == 0.3
    assert _ozet(_satirlar(30, 1.0, 0.0), sanal_agirlik=0.3)["sanal_agirlik_etkin"] == 0.3


def test_eski_alinan_kayit_tamamla_ile_cozulur():
    isl = islem(setup="T1")                                    # mod/time_stop/trail_atr/skor alani yok (iz kipi kurulumu)
    rec = OL._tamamla(isl, SimpleYon({}) if False else type("Y", (), {"trail_atr_fn": staticmethod(lambda: 2.5)})())
    assert rec["mod"] == "trail" and rec["trail_atr"] == 2.5 and rec["skor"] is None and OL._gecerli(rec)
    rec = OL._tamamla(islem(setup="R1"), None)
    assert rec["mod"] == "target" and rec["time_stop"] == 48 and OL._gecerli(rec)
    assert not OL._gecerli(OL._tamamla(islem(setup="T1"), None))               # iz kipi ama trail_atr yok
