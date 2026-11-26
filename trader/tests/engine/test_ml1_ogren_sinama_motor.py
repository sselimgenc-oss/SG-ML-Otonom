"""Paket 2 / B: orneklem-disi sinama motor tarafinda KAPATILAMAZ: `engine.py` kurucuya `sinama` gecirmez, config'ten okunmaz."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ml1"))
pytest.importorskip("pyarrow")

import ml1_motor_destek as T  # noqa: E402


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    d = tmp_path_factory.mktemp("sinama_hist") / "hist"
    T.write_history(d)
    return d


def test_config_sinama_false_olsa_da_motorda_sinama_acik(tmp_path, hist):
    ml1 = {"aktif": True, "paket_yolu": str(tmp_path / "models" / "ml1_package.json"),
           "ogrenme": {"aktif": True, "kuru": False, "min_islem": 6, "min_islem_tf": 0, "esik": 0.50}}
    eng = T.make_engine(tmp_path, hist, ml1)
    assert eng.ogren is not None and eng.ogren.sinama is True
    ml1["ogrenme"]["sinama"] = False                         # bilinmeyen anahtar: config reddeder (okunmaz)
    from trader_engine.config import ConfigError
    with pytest.raises(ConfigError):
        T.make_engine(tmp_path / "b", hist, ml1)
