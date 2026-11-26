"""Tablo deposu: artimli ekleme == tam yeniden kurulum; arms_hash degisince yeniden kurulum; bos cikis alanlari; cikis kancasi."""
from __future__ import annotations

import importlib.util

import pandas as pd
import pytest

from trader_engine.marketdata.sources import pair_stem
from trader_ml.ml1 import build as B
from trader_ml.ml1 import data as D
from trader_ml.ml1 import scan as SC
from trader_ml.ml1 import table as T

from ml1_destek import PAIR, STARTUP, sentetik

TF = "4h"
KW = dict(startup=STARTUP, min_contig=5, warmup_bars=900, warmup_days=150)       # kucuk sentetik seri icin


@pytest.fixture()
def hist(tmp_path):
    b = sentetik(n=1500)
    d = b.reset_index().rename(columns={"index": "date"})
    d["date"] = d["date"].astype("datetime64[ms, UTC]")
    h = tmp_path / "hist"
    h.mkdir()
    d.to_feather(h / f"{pair_stem(PAIR)}-4h-futures.feather")
    return h


def _build(root, hist, until, **kw):
    tbl = T.CandidateTable(root)
    B.build(tbl, hist, [PAIR], [TF], until=pd.Timestamp(until).to_pydatetime(), log=lambda *_: None,
            **{**KW, **kw})
    return tbl


def test_artimli_ekleme_tam_kurulumla_ayni(tmp_path, hist):
    son = sentetik(n=1500).index[-1] + pd.Timedelta("4h")
    ara = sentetik(n=1500).index[1100] + pd.Timedelta("4h")
    inc = _build(tmp_path / "inc", hist, ara)
    n1 = len(inc.read())
    assert inc.last_scanned(PAIR, TF) == ara and n1 > 50
    inc = _build(tmp_path / "inc", hist, son)
    assert inc.last_scanned(PAIR, TF) == son
    tam = _build(tmp_path / "tam", hist, son)
    a, b = inc.read(), tam.read()
    assert len(a) == len(b) > n1
    assert T.stable_equal(a, b)
    # ayni veriyle tekrar calistirmak satir eklemez
    assert len(_build(tmp_path / "inc", hist, son).read()) == len(a)
    # yeni satirlar yalniz son taramadan sonraki mumlardan
    assert (a["decision_ts"] > ara).sum() == len(a) - n1


def test_hash_degisince_yeniden_kurulur(tmp_path, hist, monkeypatch):
    son = sentetik(n=1500).index[-1] + pd.Timedelta("4h")
    tbl = _build(tmp_path / "t", hist, son)
    ref = tbl.read()
    # bir ay dosyasini boz: hash ayniyken tablo onarilmaz
    f = tbl.files()[0]
    f.unlink()
    assert len(_build(tmp_path / "t", hist, son).read()) < len(ref)
    # hash degisince TUM tablo silinip bastan kurulur -> referansla ayni
    monkeypatch.setattr(SC, "arms_hash", lambda arm_ids=None: "baska-hash")
    yeni = _build(tmp_path / "t", hist, son)
    assert yeni.manifest()["arms_hash"] == "baska-hash"
    assert T.stable_equal(yeni.read(), ref)


def test_gercek_hash_kol_kaynagina_duyarli(monkeypatch):
    h1 = SC.arms_hash()
    assert h1 == SC.arms_hash() and len(h1) == 64
    assert SC.arms_hash(["T1@1h"]) != h1                                   # kol listesi hash'e girer


def test_cikis_alanlari_bos_ve_guncellenebilir(tmp_path, hist, monkeypatch):
    son = sentetik(n=1500).index[-1] + pd.Timedelta("4h")
    tbl = _build(tmp_path / "t", hist, son)
    df = tbl.read()
    assert set(T.EXIT_COLUMNS) <= set(df.columns)
    assert df["exit_ts"].isna().all() and df["r_net"].isna().all() and df["exit_reason"].isna().all()
    assert len(tbl.read(only_pending_exit=True)) == len(df)
    # 26.11 sahip karari: cikis simulatoru kaldirildi; cikis sutunlari sema uyumu icin kalir ve her zaman null yazilir
    assert importlib.util.find_spec("trader_ml.ml1.exitsim") is None and importlib.util.find_spec("trader_ml.ml1.costs") is None
    assert not hasattr(B, "simulate_pending") and not hasattr(B, "exit_module") and not hasattr(B, "exit_hash")
    assert not hasattr(D, "load_15m")
    assert len(tbl.read(only_pending_exit=True)) == len(df)
    assert df[list(T.EXIT_COLUMNS)].isna().all().all()


def test_ay_bolumleri_ve_okuma_suzgeci(tmp_path, hist):
    son = sentetik(n=1500).index[-1] + pd.Timedelta("4h")
    tbl = _build(tmp_path / "t", hist, son)
    fs = tbl.files()
    assert len(fs) > 3 and all(f.parent.name == f"tf={TF}" and f.name.startswith("month=") for f in fs)
    df = tbl.read()
    assert len(tbl.read(pairs=["BASKA/USDT"])) == 0
    kes = pd.Timestamp("2022-07-01", tz="UTC")
    assert (tbl.read(since=kes)["decision_ts"] >= kes).all() and len(tbl.read(until=kes)) + len(tbl.read(since=kes)) == len(df)
