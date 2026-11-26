"""26.11 sahip karari: ML1 guven bandina gore islem basi risk (yalniz kagit). Ogrenme asamasi/kapali = sabit %1; ust sinirlar degismez."""
from __future__ import annotations

import pytest
from test_engine_05_spec import BTC, ETH, Env, FakeSignalSource, T0

from trader_core import risk as K
from trader_engine import config as C
from trader_engine import gates as G
from trader_engine.ml1_gate import Verdict

BANT = {"aktif": True, "bantlar": [[0.50, 0.005], [0.60, 0.010], [0.70, 0.015]], "tavan": 0.015}


@pytest.fixture(autouse=True)
def _ml1_kaynagi(monkeypatch):
    monkeypatch.setattr(FakeSignalSource, "ml1", None, raising=False)


class _Stub:
    def __init__(self, feats):
        self.feats = feats

    def verdict(self, row):
        return Verdict(None, self.feats.get("ml1_skor"), dict(self.feats))


def _env(tmp_path, bant, feats):
    ml1 = {"aktif": True}
    if bant is not None:
        ml1["risk_bantlari"] = bant
    e = Env(tmp_path, ml1=ml1, target_trade_risk=0.01)
    e.start()
    e.engine.ml1 = None                                   # gercek kapi yerine sabit karar
    e.engine.gate.ml1 = _Stub(feats)
    return e


def _risk_orani(e):
    e.signal(T0, (BTC,))
    e.decide(T0)
    d = [x for x in e.decisions() if x.pair == BTC][-1]
    assert d.final_action == "entered"
    return d.size_risk_amount / e.cfg.wallet_start, d


@pytest.mark.parametrize("p,beklenen", [(0.55, 0.005), (0.65, 0.010), (0.80, 0.015), (0.50, 0.005), (0.70, 0.015)])
def test_bant_riski(tmp_path, p, beklenen):
    e = _env(tmp_path, BANT, {"ml1_skor": p, "ml1_esik": 0.5})
    try:
        r, d = _risk_orani(e)
        assert r == pytest.approx(beklenen, rel=1e-3) and r <= beklenen
        assert d.features["ml1_risk"] == beklenen
    finally:
        e.close()


def test_ogrenme_asamasi_sabit_yuzde_bir(tmp_path):
    e = _env(tmp_path, BANT, {"ml1_neden": "ogrenme"})
    try:
        r, d = _risk_orani(e)
        assert r == pytest.approx(0.01, rel=1e-3)
        assert "ml1_risk" not in d.features
    finally:
        e.close()


def test_pasif_bayrak_ve_blok_yok_sabit(tmp_path):
    for i, bant in enumerate(({**BANT, "aktif": False}, None)):
        (tmp_path / str(i)).mkdir()
        e = _env(tmp_path / str(i), bant, {"ml1_skor": 0.9, "ml1_esik": 0.5})
        try:
            r, d = _risk_orani(e)
            assert r == pytest.approx(0.01, rel=1e-3)
            assert "ml1_risk" not in d.features
        finally:
            e.close()


def test_bant_orani_saf_fonksiyon():
    f = G.ml1_risk_orani
    assert f(None, 0.9) is None and f({}, 0.9) is None
    assert f({"risk_bantlari": BANT}, None) is None
    assert f({"risk_bantlari": BANT}, 0.49) is None
    assert f({"risk_bantlari": BANT}, 0.5999) == 0.005
    assert f({"risk_bantlari": BANT}, 0.6) == 0.010
    assert f({"risk_bantlari": BANT}, 0.99) == 0.015
    assert f({"risk_bantlari": {**BANT, "tavan": 0.012}}, 0.99) == 0.012


def _acik(n, risk, side="long"):
    return [K.OpenPosition(f"P{i}/USDT", side, risk, 10.0) for i in range(n)]


def test_ayni_yon_tavani_bagli_kalir():
    cfg = K.PaperRiskConfig(target_trade_risk=0.01, max_open_risk=0.12, max_same_dir_risk=0.06, daily_max_loss=0.08)
    eq = 1000.0

    def kac(oran):
        acik, n = [], 0
        while n < 30:
            c = K.Candidate("X/USDT", "long", 100.0, 98.0, 3, 0.001, 0.0, oran)
            d = K.check_entry(K.AccountState(eq, eq, acik), c, cfg)
            if not d.allowed:
                assert "aynı yön" in d.reason
                return n
            acik = acik + [K.OpenPosition(f"P{n}/USDT", "long", d.size.risk_amount, d.size.margin)]
            n += 1
        return n

    sabit = kac(None)
    assert sabit == kac(0.01) and sabit >= 5            # %1: 6% tavana ~6 islemde ulasilir (sayi kayan nokta payina bagli)
    assert kac(0.015) <= 4 < sabit                      # %1,5: tavana daha once ulasilir; 5. islem asla
    assert kac(0.005) > sabit


def test_trade_risk_dogrulama():
    cfg = K.PaperRiskConfig(target_trade_risk=0.01)
    for bad in (0.0, -0.01, 0.03, float("nan"), True):
        with pytest.raises(ValueError):
            K.size_position(1000.0, 100.0, 98.0, "long", 3, cfg, trade_risk=bad)


def _ml1(b):
    return C._build_ml1({"aktif": True, "risk_bantlari": b})


def test_config_gecerli_ve_gonderilen_dosya():
    assert _ml1(BANT)["risk_bantlari"] == BANT
    import json
    from pathlib import Path
    raw = json.loads((Path(__file__).resolve().parents[2] / "config" / "engine.paper.json").read_text())
    assert raw["ml1"]["risk_bantlari"] == BANT
    live = json.loads((Path(__file__).resolve().parents[2] / "config" / "engine.live.json").read_text())
    assert "risk_bantlari" not in (live.get("ml1") or {})


@pytest.mark.parametrize("b", [
    {**BANT, "bantlar": [[0.60, 0.01], [0.50, 0.005]]},         # sirasiz
    {**BANT, "bantlar": [[0.50, 0.005], [0.50, 0.010]]},        # yinelenen esik
    {**BANT, "bantlar": [[0.50, 0.0]]},                          # risk 0
    {**BANT, "bantlar": [[0.50, 0.02]]},                         # risk > tavan
    {**BANT, "bantlar": []},
    {**BANT, "bantlar": [[1.0, 0.01]]},                          # esik disi
    {**BANT, "bantlar": [[0.5]]},
    {**BANT, "tavan": 0.03},
    {**BANT, "tavan": 0},
    {**BANT, "aktif": "evet"},
    {"aktif": True, "bantlar": BANT["bantlar"]},                 # tavan eksik
    {**BANT, "ekstra": 1},
])
def test_config_gecersiz(b):
    with pytest.raises(C.ConfigError):
        _ml1(b)
