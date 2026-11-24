"""Kilitli donem (2026-05 -> 2026-10): 23.11.2026 kullanici karariyla kilit ACIK (config.KILIT_ACIK). Acikken egitim kodu bu donemi
okuyabilir; bayrak kapatilirsa (monkeypatch) eski koruma aynen geri gelir."""
import pandas as pd
import pytest

from trader_ml import config as C
from trader_ml import guards
from trader_ml.guards import HoldoutViolation, assert_pre_holdout
from trader_ml.walkforward import make_folds


@pytest.fixture
def kilitli(monkeypatch):
    monkeypatch.setattr(guards, "KILIT_ACIK", False)


def _tablo(son: str) -> pd.DataFrame:
    """Walk-forward bolmesi icin kucuk aday tablosu: ts (kapanis) ve label_end_ts, veri baslangicindan `son`a saatlik."""
    ts = pd.date_range(C.DATA_START + C.BAR, pd.Timestamp(son, tz="UTC"), freq="1h")
    return pd.DataFrame({"ts": ts, "label_end_ts": ts + C.HORIZON_BARS * C.BAR})


def test_kilit_bayragi_acik_ve_kesim_veri_sonu():
    assert C.KILIT_ACIK is True
    assert C.EGITIM_KESIMI == C.HOLDOUT_END


def test_acik_kilitte_assert_pre_holdout_hata_vermez():
    assert_pre_holdout(pd.to_datetime(["2026-04-30 23:00"], utc=True))
    assert_pre_holdout(pd.to_datetime(["2026-05-01 00:00"], utc=True))
    assert_pre_holdout(pd.DatetimeIndex(["2026-07-01"]))


def test_acik_kilitte_fold_tablosu_kilitli_doneme_uzansa_da_kabul():
    make_folds(_tablo("2026-06-01"))


def test_kapali_kilitte_eski_koruma(kilitli):
    assert_pre_holdout(pd.to_datetime(["2026-04-30 23:00"], utc=True))
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.to_datetime(["2026-05-01 00:00"], utc=True))
    with pytest.raises(HoldoutViolation):
        assert_pre_holdout(pd.DatetimeIndex(["2026-07-01"]))        # naif -> UTC kabul
    with pytest.raises(HoldoutViolation):
        make_folds(_tablo("2026-06-01"))


def test_acik_kilitte_fold_kesimi_veri_sonu():
    for f in make_folds(_tablo("2026-10-31")):
        assert f["test_end"] <= C.EGITIM_KESIMI
