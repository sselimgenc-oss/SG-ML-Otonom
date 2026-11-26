"""26.11 sahip karari: evren 14 cift SABIT (hicbir sey otomatik degistiremez), giris zaman dilimleri 1h/4h/1d, 16 kurulum kaldirildi.
15m KARAR/CIKIS kadansi olarak KALIR (yalniz 15m giris kollari ve tf_15m golge blogu config'ten gitti)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from evren_destek import EVREN, GIRIS_TFS, GRUP_SAYISI, KALDIRILAN_KURULUM, KOL_SAYISI, KURULUM_SAYISI
from trader_engine import config as C
from trader_engine.config import SHADOW_BLOCK_KEYS, ConfigError, load_cli_config
from trader_engine.strategies import arms as ARMS

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"


def _raw(ad: str) -> dict:
    return json.loads((CONFIG / ad).read_text(encoding="utf-8"))


@pytest.mark.parametrize("ad", ["engine.paper.json", "engine.live.json"])
def test_tam_14_cift_kume_ve_maliyet(ad):
    raw = _raw(ad)
    assert sorted(raw["pairs"]) == sorted(EVREN) and len(raw["pairs"]) == len(set(raw["pairs"])) == 14
    assert set(raw["optional_pairs"]) == {p for p in EVREN if p.split("/")[0] not in ("BTC", "ETH", "SOL", "XRP", "TRX")}
    assert len(raw["optional_pairs"]) == 9 and set(raw["optional_pairs"]) <= set(raw["pairs"])
    cl = {k: v["pairs"] for k, v in raw["clusters"].items()}
    assert cl == {"kripto_buyuk": ["BTC/USDT", "ETH/USDT", "XRP/USDT", "SOL/USDT"], "kripto_diger": ["TRX/USDT"],
                  "hisse": [p for p in EVREN[:7]], "metal": ["XAU/USDT"], "enerji_sanayi": ["BZ/USDT"]}
    assert all(v and set(v) <= set(raw["pairs"]) for v in cl.values())             # bos olmayan alt kume
    assert set(raw["cost_overrides"]) == set(raw["optional_pairs"])                  # kripto icin override yok; kalanlar budandi


@pytest.mark.parametrize("ad", ["engine.paper.json", "engine.live.json"])
def test_162_kol_15m_yok_16_kurulum_yok_55_kurulum(ad):
    arms = _raw(ad)["arms"]
    assert len(arms) == len(set(arms)) == KOL_SAYISI == 162
    setups, tfs = {a.partition("@")[0] for a in arms}, {a.partition("@")[2] for a in arms}
    assert tfs == set(GIRIS_TFS) and not any(a.endswith("@15m") for a in arms)
    assert len(setups) == KURULUM_SAYISI == 55 and not (setups & KALDIRILAN_KURULUM)
    assert not (set(ARMS.discover()) & KALDIRILAN_KURULUM)                        # Paket 3: config'te degil, kayitta da yok
    assert set(ARMS.list_arms()) == {a.split('@')[0] for a in arms} and len(ARMS.discover()) == 55   # kayit == config (kagit ve canli)
    assert "H2-YARI" not in _raw(ad)["exit_modes"] and set(_raw(ad)["exit_modes"]) == {"default"}


def test_yuklenen_yapilandirma_ve_parite_paper_live():
    p, l = load_cli_config(CONFIG, "learner", "paper"), load_cli_config(CONFIG, "learner", "live")
    assert len(p.pairs) == 14 and set(p.pairs) == set(EVREN) and len(p.arms) == 162 and not any(a.endswith("@15m") for a in p.arms)
    assert p.pairs == l.pairs and p.arms == l.arms and p.optional_pairs == l.optional_pairs and p.clusters == l.clusters
    assert p.cost_overrides == l.cost_overrides and p.exit_modes == l.exit_modes and p.shadow_blocks == l.shadow_blocks


def test_golge_blogu_tf_15m_kalkti_ama_anahtar_ve_defter_kisiti_kalir():
    for ad in ("engine.base.json", "engine.paper.json", "engine.live.json"):
        assert _raw(ad)["shadow_blocks"] == ["regime", "r1_disabled", "same_bar_reentry"]
    assert "tf_15m" in SHADOW_BLOCK_KEYS                                              # eski satirlar/CHECK icin anahtar yerinde
    from trader_core import ledger as L
    assert "tf_15m" in L._SHADOW_BLOCKS


def test_taban_5_kripto_ve_evren_dosyasi_hizali():
    assert _raw("engine.base.json")["pairs"] == ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "TRX/USDT"]
    u = _raw("universe.json")
    assert u["n_crypto"] == 5 and u["n_stocks"] == 7 and u["commodities"] == ["XAU/USDT", "BZ/USDT"]
    assert u["stocks_ordered"] == list(EVREN[:7])


def test_15m_karar_kadansi_kalir():
    from trader_core import arm_time as AT
    from trader_ml.ml1 import data as D
    assert AT.ARM_TFS == ("15m", "1h", "4h", "1d") and D.TFS == ("15m", "1h", "4h", "1d")


def test_kaplama_dosyasi_pairs_degistiremez(tmp_path):
    """Eski `var/universe/paper_pairs.json` kaplamasi (ya da bozuk hali) var olsa da paper/live evreni DEGISMEZ."""
    cfg = tmp_path / "config"
    shutil.copytree(CONFIG, cfg)
    base = load_cli_config(cfg, "learner", "paper")
    (tmp_path / "var" / "universe").mkdir(parents=True)
    ov = tmp_path / "var" / "universe" / "paper_pairs.json"
    ov.write_text(json.dumps({"schema": "universe/1", "pairs": ["BTC/USDT", "DOGE/USDT"], "optional_pairs": ["DOGE/USDT"]}), encoding="utf-8")
    for ic in (ov.read_text(), "{bozuk"):
        ov.write_text(ic, encoding="utf-8")
        for env in ("paper", "live"):
            c = load_cli_config(cfg, "learner", env)
            assert c.pairs == base.pairs and "DOGE/USDT" not in c.pairs and len(c.pairs) == 14 and c.optional_pairs == base.optional_pairs
    assert not hasattr(C, "apply_universe_overlay")


def test_ml1_ogrenme_blogu_paper_sifirdan():
    p, l = _raw("engine.paper.json"), _raw("engine.live.json")
    assert p["ml1"] == {"aktif": True, "ogrenme": {"aktif": True, "kuru": False, "min_islem": 200, "min_islem_tf": 0, "esik": 0.50}}
    assert "ml1" not in l                                                              # ML1 yalniz paper
    assert not (ROOT / "models" / "ml1" / "ml1_package.json").exists()                 # tohum paket depoda yok
    assert "tohum_yolu" not in C._ML1_KEYS


def test_gruplar_ml1_gorunum_kopyasi_ayni():
    from trader_core import ml1_gorunum as MG
    from trader_ml.ml1 import groups as G
    assert MG.GRUP_KURULUM == G._GRUP_KURULUM and len(G.GRUP_ADLARI) == GRUP_SAYISI == 18
    assert len(G.GRUPLAR) == KURULUM_SAYISI == 55 and not (set(G.GRUPLAR) & KALDIRILAN_KURULUM)


def test_15m_giris_kolu_reddedilir_karar_kadansi_kalir():
    """Paket 3 (P1-02): 15m yalniz karar/cikis kadansi; 15m GIRIS kolu config'te ve lab'da reddedilir; hicbir kurulum 15m'i desteklemez."""
    from trader_engine import bars
    from trader_engine.strategies.base import StrategyError
    from trader_engine.strategies.lab import PriceActionLab
    assert bars.GIRIS_TFS == ("1h", "4h", "1d") and "15m" in bars.ARM_TFS
    with pytest.raises(ConfigError, match="15m giris kolu yok"):
        C._build_arms(["T1@15m"])
    assert C._build_arms(["T1@1h", "R1@4h"]) == ("T1@1h", "R1@4h")
    with pytest.raises(StrategyError, match="15m"):
        PriceActionLab(arms=("T1@15m",))
    for ad, mod in ARMS.discover().items():
        assert "15m" not in mod.TIMEFRAMES, ad


def test_cikis_simulatoru_ve_olu_paket_kodu_yok():
    import importlib.util
    import trader_core.ml_package as mp
    for ad in ("trader_ml.ml1.exitsim", "trader_ml.ml1.costs", "trader_core.ml_eval"):
        assert importlib.util.find_spec(ad) is None, ad
    assert not any(hasattr(mp, ad) for ad in ("PackageSet", "view_from_package", "load_package", "MlModelView"))
    assert hasattr(mp, "canon") and hasattr(mp, "sha256_text")
