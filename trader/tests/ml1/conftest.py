"""ML1 test duzenegi: sentetik 4s seri ve tek seferlik tarama (oturum kapsamli)."""
from __future__ import annotations

import pandas as pd
import pytest

from ml1_destek import PAIR, STARTUP, TF, sentetik
from trader_ml.ml1 import scan as SC


@pytest.fixture(scope="session")
def bars4h() -> pd.DataFrame:
    return sentetik()


@pytest.fixture(scope="session")
def scanned(bars4h) -> pd.DataFrame:
    df = SC.scan_pair_tf(PAIR, TF, bars4h, bars4h, startup=STARTUP, min_contig=5)
    assert df.attrs["n_err"] == 0
    return df
