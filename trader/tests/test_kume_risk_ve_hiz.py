"""27.11 sahip karari: (1) kume bazli ayni-yon acik risk tavani; (2) ML1 'Hiz' satiri (hesap + metin)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from trader_core import ml1_gorunum as MG
from trader_core import risk as K
from trader_ml.ml1.hiz import hiz_hesapla
from trader_engine.config import ConfigError, load_cli_config

CONFIG = Path(__file__).resolve().parents[1] / "config"
EQ = 10_000.0
KRIPTO = tuple(f"{x}/USDT" for x in "BTC ETH SOL XRP TRX".split())
HISSE = tuple(f"{x}/USDT" for x in "AAPL MSFT NVDA GOOGL AMZN META TSLA".split())
KUME = (("kripto", KRIPTO, 0.03), ("hisse", HISSE, 0.03), ("emtia", ("XAU/USDT", "BZ/USDT"), 0.02))


def _cfg(kume=KUME):
    return K.paper_config(max_open_risk=0.12, max_same_dir_risk=0.06, kume_risk=kume)


def _op(pair, side="long", r=0.01):
    return K.OpenPosition(pair, side, r * EQ, 1000.0)


def _dec(opens, pair, side="long", r=0.01, cfg=None):
    st = K.AccountState(EQ, EQ, list(opens))
    ent, stop = (100.0, 95.0) if side == "long" else (100.0, 105.0)
    return K.check_entry(st, K.Candidate(pair, side, ent, stop, 3, risk_override=r), cfg or _cfg())


def test_kripto_ucuncu_izinli_dorduncu_red():
    ac = [_op("BTC/USDT"), _op("ETH/USDT")]
    assert _dec(ac, "SOL/USDT").allowed
    d = _dec(ac + [_op("SOL/USDT")], "XRP/USDT")
    assert not d.allowed and d.reason.startswith("aynı yön") and "kripto" in d.reason


def test_hisse_ayni_kural():
    ac = [_op("AAPL/USDT"), _op("MSFT/USDT")]
    assert _dec(ac, "NVDA/USDT").allowed
    assert not _dec(ac + [_op("NVDA/USDT")], "TSLA/USDT").allowed


def test_emtia_iki_yuzde():
    assert _dec([_op("XAU/USDT")], "BZ/USDT").allowed
    d = _dec([_op("XAU/USDT")], "BZ/USDT", r=0.015)
    assert not d.allowed and "emtia" in d.reason


def test_ters_yon_ve_baska_kume_sayilmaz():
    ac = [_op("BTC/USDT", "short"), _op("ETH/USDT", "short"), _op("SOL/USDT", "short")]
    assert _dec(ac, "XRP/USDT", "long").allowed                       # ters yon sayilmaz
    kr = [_op(p) for p in KRIPTO[:3]]
    assert _dec(kr, "AAPL/USDT").allowed                              # baska kume sayilmaz


def test_kapali_eski_davranis_ve_global_tavanlar():
    kr = [_op(p) for p in KRIPTO[:3]]
    assert _dec(kr, "XRP/USDT", cfg=_cfg(())).allowed                 # kume_risk bos: eski davranis
    ac = [_op(p) for p in ("BTC/USDT", "ETH/USDT", "SOL/USDT", "AAPL/USDT", "MSFT/USDT")]   # 5% long
    d = _dec(ac + [_op("NVDA/USDT")], "XAU/USDT")                      # 6% + 1% > global 6%
    assert not d.allowed and "aynı yön (long) risk" in d.reason
    sh = [_op(p, "short", 0.02) for p in ("AAPL/USDT", "MSFT/USDT", "BTC/USDT")]   # 6% short + 5% long = 11%
    d = _dec(ac + sh, "XAU/USDT", "short", r=0.015)
    assert not d.allowed and "toplam açık risk" in d.reason


def test_gercek_boyut_riski_kullanilir():
    # acik risk 2.9%: 1% aday (gercek size.risk_amount) kume tavanini asar
    ac = [_op("BTC/USDT", r=0.015), _op("ETH/USDT", r=0.014)]
    assert not _dec(ac, "SOL/USDT").allowed



def test_ayar_yuklenir_ve_risk_config_kume_tasir():
    cfg = load_cli_config(CONFIG, "learner", "paper")
    rc = cfg.risk_config
    assert {n: c for n, _p, c in rc.kume_risk} == {"kripto": 0.03, "hisse": 0.03, "emtia": 0.02}
    assert load_cli_config(CONFIG, "learner", "live").risk_config.kume_risk == rc.kume_risk


@pytest.mark.parametrize("mod", [
    lambda k: k["kumeler"]["kripto"].update(ayni_yon=0.07),                  # > max_same_dir_risk
    lambda k: k["kumeler"]["kripto"].update(ayni_yon=0),
    lambda k: k["kumeler"]["emtia"].update(ciftler=["XAU/USDT"]),            # BZ kumede degil
    lambda k: k["kumeler"]["emtia"].update(ciftler=["XAU/USDT", "BZ/USDT", "BTC/USDT"]),   # cift iki kumede
    lambda k: k["kumeler"]["emtia"].update(ciftler=["XAU/USDT", "BZ/USDT", "YOK/USDT"]),   # config disi cift
])
def test_ayar_dogrulama(mod):
    from trader_engine import config as C
    cfg = load_cli_config(CONFIG, "learner", "paper")
    kr = json.loads(json.dumps(dict(cfg.kume_risk)))
    mod(kr)
    with pytest.raises(ConfigError):
        C.apply_overrides(cfg, kume_risk=kr).risk_config


def test_paper_live_kume_esit():
    assert json.loads((CONFIG / "engine.paper.json").read_text())["kume_risk"] == json.loads((CONFIG / "engine.live.json").read_text())["kume_risk"]


# ---------------------------------------------------------------- Hiz
NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def test_hiz_hesabi():
    z = [NOW - timedelta(days=d, hours=1) for d in (0.5, 1, 2, 3, 4, 5, 6, 6.5, 10)]    # 9 satir, 8 tanesi son 7 gunde
    h, v = hiz_hesapla(z, 20, 200, NOW)
    assert h == round(8 / 7, 2)
    assert v == (NOW + timedelta(days=180 / h)).strftime("%Y-%m-%d")


def test_hiz_olculemedi():
    assert hiz_hesapla([], 0, 200, NOW) == (None, None)
    assert hiz_hesapla([NOW - timedelta(hours=5)], 1, 200, NOW) == (None, None)          # < 1 gun veri
    assert hiz_hesapla([NOW - timedelta(days=30)], 1, 200, NOW) == (None, None)          # hiz 0
    assert MG.hiz_satiri({"ogr": {}}) == "Hız: henüz ölçülemedi"


def test_hiz_metni():
    oz = {"ogr": {"gunluk_hiz": 4.5, "tahmini_varis": "2026-12-14", "min_islem": 200}}
    assert MG.hiz_satiri(oz) == "Hız: son 7 günde günde ortalama 4,5 etiketli işlem · 200'e tahmini varış: 14.12"
    o = MG.ogr_durumu({"gunluk_hiz": 2, "tahmini_varis": "2026-12-01"}, 0, {}, False)
    assert o["gunluk_hiz"] == 2.0 and o["tahmini_varis"] == "2026-12-01"
