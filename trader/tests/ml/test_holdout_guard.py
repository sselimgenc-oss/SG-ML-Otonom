"""Kilitli donem (2026-05 -> 2026-10): 23.11.2026 kullanici karariyla kilit ACIK (config.KILIT_ACIK). Acikken egitim kodu bu donemi
okuyabilir; bayrak kapatilirsa (monkeypatch) eski koruma aynen geri gelir."""
import pandas as pd
import pytest

from trader_ml import config as C
from trader_ml import fixture, guards, pipeline
from trader_ml.features import feature_frame
from trader_ml.guards import HoldoutViolation, assert_pre_holdout, clip_to_train_window
from trader_ml.labels import label_candidates
from trader_ml.schema import validate_candidates
from trader_ml.walkforward import make_folds

HOLDOUT_T = pd.Timestamp("2026-05-01", tz="UTC")


@pytest.fixture
def kilitli(monkeypatch):
    monkeypatch.setattr(guards, "KILIT_ACIK", False)


def test_kilit_bayragi_acik_ve_kesim_veri_sonu():
    assert C.KILIT_ACIK is True
    assert C.EGITIM_KESIMI == C.HOLDOUT_END


def test_acik_kilitte_assert_pre_holdout_hata_vermez():
    assert_pre_holdout(pd.to_datetime(["2026-04-30 23:00"], utc=True))
    assert_pre_holdout(pd.to_datetime(["2026-05-01 00:00"], utc=True))
    assert_pre_holdout(pd.DatetimeIndex(["2026-07-01"]))
    df = pd.DataFrame({"x": [1, 2], "ts": pd.to_datetime(["2026-04-30", "2026-07-01"], utc=True)})
    assert len(clip_to_train_window(df, "ts")) == 2


def test_acik_kilitte_fixture_kilitli_doneme_uzanir(candles):
    assert max(d.index.max() for d in candles.values()) >= HOLDOUT_T


def test_acik_kilitte_mum_ve_aday_tablosu_kabul(candles, table):
    feature_frame(candles["BTC/USDT:USDT"])
    bad = table.copy()
    bad.loc[bad.index[-1], "ts"] = pd.Timestamp("2026-06-01", tz="UTC")
    validate_candidates(bad)
    make_folds(bad)


def test_kapali_kilitte_eski_koruma(kilitli, candles, table):
    assert_pre_holdout(pd.to_datetime(["2026-04-30 23:00"], utc=True))
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.to_datetime(["2026-05-01 00:00"], utc=True))
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.DatetimeIndex(["2026-07-01"]))        # naif -> UTC kabul
    df = pd.DataFrame({"x": [1, 2], "ts": pd.to_datetime(["2026-04-30", "2026-07-01"], utc=True)})
    assert len(clip_to_train_window(df, "ts")) == 1
    c = candles["BTC/USDT:USDT"]
    bad = pd.concat([c, c.iloc[-5:].set_axis(pd.date_range("2026-11-01", periods=5, freq="1h", tz="UTC"))])
    with pytest.raises(HoldoutViolation):
        label_candidates(bad, pd.DataFrame({"ts": [], "side": [], "planned_entry": [], "planned_stop": [],
                                            "planned_target": []}))
    bad2 = table.copy()
    bad2.loc[bad2.index[-1], "ts"] = pd.Timestamp("2026-06-01", tz="UTC")
    with pytest.raises(HoldoutViolation):
        validate_candidates(bad2)
    with pytest.raises(HoldoutViolation):
        make_folds(bad2)


def test_acik_kilitte_fold_kesimi_veri_sonu(table):
    for f in make_folds(table):
        assert f["test_end"] <= C.EGITIM_KESIMI
