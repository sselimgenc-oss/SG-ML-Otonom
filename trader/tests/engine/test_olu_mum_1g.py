"""Paket 2 / C1 (26.11 sahip karari #8): 1g mum olu 4s satirlari ayiklayarak toplanir (`bars.aggregate_4h_to_1d`).

Tamlik kurali AYNI (6 x 4s satirli UTC gunu; olu satirlar da sayilir); OHLC yalniz DOLU 4s satirlardan; hacim tum satirlarin toplami.
Olu mumu olmayan seride (kripto) sonuc eski fonksiyonla bit bit ayni."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from trader_core import arm_time as AT
from trader_engine import bars as B
from trader_engine import strategy_runner as SR

UTC = timezone.utc
COLS = ["open", "high", "low", "close", "volume"]


def _eski(df4h):
    """`aggregate_4h_to_1d`'nin Paket 2 oncesi hali (referans)."""
    day = df4h.index.floor("1D")
    g = df4h.groupby(day, sort=True)
    n = g["open"].count()
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    out = out.loc[n[n == B.BARS_PER_DAY_4H].index][COLS]
    out.index.name = df4h.index.name
    return out


def _seri(gun: int, dolu_baslangic: int = 0, *, olu_fiyat: float = 100.0, tumu_olu: bool = False, seed: int = 1) -> pd.DataFrame:
    """`gun` gunluk 4s seri; her gunun ilk `dolu_baslangic` satiri olu (fiyat `olu_fiyat`, hacim 0), kalani seans barlari (103-106)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-03-02", periods=gun * 6, freq="4h", tz="UTC")
    rows = []
    for i in range(len(idx)):
        if tumu_olu or (i % 6) < dolu_baslangic:
            rows.append((olu_fiyat,) * 4 + (0.0,))
        else:
            o = 103.0 + (i % 6) * 0.5
            rows.append((o, o + 1.0 + rng.random() * 0.5, o - 0.5 - rng.random() * 0.4, o + 0.3, 10.0 + i))
    return pd.DataFrame(rows, columns=COLS, index=idx)


def test_olu_mumsuz_seride_eski_fonksiyonla_ayni():
    rng = np.random.default_rng(3)
    idx = pd.date_range("2026-03-02", periods=60, freq="4h", tz="UTC", name="ts")
    c = 100 + np.cumsum(rng.normal(size=60))
    df = pd.DataFrame({"open": c, "high": c + 1, "low": c - 1, "close": c + 0.2, "volume": rng.random(60) + 1}, index=idx)
    assert AT.active_mask(df) is None
    pd.testing.assert_frame_equal(B.aggregate_4h_to_1d(df), _eski(df))


def test_gunun_ilk_iki_4s_olu_ise_1g_yalniz_dolu_barlardan():
    df = _seri(5, 2)
    out = B.aggregate_4h_to_1d(df)
    assert len(out) == 5
    g0 = df.iloc[:6]
    dolu = g0.iloc[2:]
    assert out.iloc[0]["open"] == dolu.iloc[0]["open"]               # ilk DOLU acilis (olu 100 degil)
    assert out.iloc[0]["low"] >= 103.0 and out.iloc[0]["low"] == dolu["low"].min()
    assert out.iloc[0]["high"] == dolu["high"].max()
    assert out.iloc[0]["close"] == dolu.iloc[-1]["close"]
    assert out.iloc[0]["volume"] == g0["volume"].sum()
    eski = _eski(df)
    assert eski.iloc[0]["low"] == 100.0                              # eski toplayici oluyu karistiriyordu


def test_tumu_olu_gun_olu_1g_bar_ve_active_mask_olu_gorur():
    df = pd.concat([_seri(2, 0), _seri(1, tumu_olu=True).set_axis(pd.date_range("2026-03-04", periods=6, freq="4h", tz="UTC"))])
    out = B.aggregate_4h_to_1d(df)
    assert len(out) == 3
    son = out.iloc[-1]
    assert son["open"] == son["high"] == son["low"] == son["close"] == 100.0 and son["volume"] == 0.0
    m = AT.active_mask(out)
    assert m is not None and list(m) == [True, True, False]
    pd.testing.assert_frame_equal(out.iloc[-1:], _eski(df).iloc[-1:])  # tumu olu gunun ciktisi eskisiyle ayni


def test_5_satirli_gun_bar_uretmez():
    df = _seri(3, 2)
    df = df.drop(df.index[8])                                        # 2. gunden bir satir eksik
    out = B.aggregate_4h_to_1d(df)
    assert list(out.index.strftime("%m-%d")) == ["03-02", "03-04"]


class _GoruntuSahte:
    def __init__(self, df):
        self.df = df

    def bars(self, pair, tf, D, n):
        return self.df[self.df.index < D].iloc[-n:]


def test_cevrimdisi_data_ile_canli_bars_1d_ayni_gunlerde_ayni_ohlc(tmp_path):
    pytest.importorskip("pyarrow")
    df = _seri(40, 2)
    D = datetime(2026, 4, 20, tzinfo=UTC)
    canli = SR._bars_1d(_GoruntuSahte(df), "NVDA/USDT", D, 20)
    ref = B.aggregate_4h_to_1d(df[df.index < D])
    ref = ref[ref["volume"] > 0].iloc[-20:] if len(ref) else ref
    pd.testing.assert_frame_equal(canli[COLS], ref[COLS])
    assert (canli["low"] >= 103.0).all()
    # trader_ml.ml1.data ayni toplayiciyi cagirir
    from trader_ml.ml1 import data as DT
    assert DT.aggregate_4h_to_1d is B.aggregate_4h_to_1d
