"""Paket 2 / C2 (26.11 sahip karari #8): ML1 `vol_*` ozellikleri olu mumlari (hacim 0, o=h=l=c) disarida birakir.

Olu mumsuz seride (kripto) ozellikler eski surumle bit bit ayni; ozellik tanimi surumu `OZELLIK_SURUM = 2`, kapi kayda `oz` yazar."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trader_core import arm_time as AT
from trader_ml.ml1 import features as F

from ml1_destek import PAIR, TF, sentetik

VOL = ["vol_20", "vol_100", "vol_ratio", "vol_volume_ratio", "vol_range_atr"]


def _olu_ekle(df: pd.DataFrame) -> pd.DataFrame:
    """Her 6 mumun ilk 2'si olu (onceki kapanis, hacim 0)."""
    d = df.copy()
    for i in range(len(d)):
        if i % 6 < 2 and i > 0:
            c = d["close"].iloc[i - 1]
            d.iloc[i, d.columns.get_indexer(["open", "high", "low", "close"])] = c
            d.iloc[i, d.columns.get_loc("volume")] = 0.0
    return d


def _cand(df: pd.DataFrame, bar_ts) -> pd.DataFrame:
    return pd.DataFrame({"pair": PAIR, "tf": TF, "side": "long", "group": "A", "arm_id": "a", "bar_ts": pd.DatetimeIndex(bar_ts),
                         "decision_ts": pd.DatetimeIndex(bar_ts) + pd.Timedelta(hours=4)})


def test_ozellik_surum_2():
    assert F.OZELLIK_SURUM == 2


def test_olu_mumsuz_seride_eski_surumle_birebir(monkeypatch):
    df = sentetik(600)
    assert AT.active_mask(df) is None
    c = _cand(df, df.index[200:260:3])
    yeni = F.bar_features(c, lambda p, t: (df, df))
    monkeypatch.setattr(AT, "strip_dead", lambda x: x)                       # eski davranis: olu mum ayiklama yok
    eski = F.bar_features(c, lambda p, t: (df, df))
    pd.testing.assert_frame_equal(yeni, eski)


def test_olu_mumlu_seride_vol_20_olu_mumlari_silinmis_seriyle_ayni():
    df = _olu_ekle(sentetik(900, seed=3))
    assert AT.active_mask(df) is not None
    dolu = df[AT.active_mask(df)]
    karar = [t for t in dolu.index[200:300:2]]
    a = F.bar_features(_cand(df, karar), lambda p, t: (df, df))
    b = F.bar_features(_cand(dolu, karar), lambda p, t: (dolu, dolu))
    assert a["vol_20"].notna().all()
    for col in ("vol_20", "vol_100", "vol_ratio", "vol_volume_ratio"):
        np.testing.assert_allclose(a[col].to_numpy(float), b[col].to_numpy(float), rtol=1e-12, atol=1e-15, err_msg=col)


def test_olu_mum_vol_tablosuna_girmez_eski_yol_farkli():
    df = _olu_ekle(sentetik(900, seed=3))
    dolu_t = F._vol_table(df[AT.active_mask(df)])
    kar = F._vol_table(df)                                                   # eski yol: olu mumlar dahil
    t = df.index[AT.active_mask(df)][300]
    assert not np.isclose(kar.loc[t, "vol_20"], dolu_t.loc[t, "vol_20"])
    c = _cand(df, [t])
    got = F.bar_features(c, lambda p, t_: (df, df))
    assert got["vol_20"].iloc[0] == pytest.approx(dolu_t.loc[t, "vol_20"], rel=1e-12)
