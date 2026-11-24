"""23.11 kullanici karari: canli = kagit. Canli motor kagitla AYNI ticaret sistemini calistirir (canli cikis kipleri de kagitla ayni: basa-bas stop tasima + kismi kar alma).
Parite (config), canli risk sinirlari, %1 kademe baslangici, genis sozlesme turleri, testnet tarafsizligi."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
import test_engine_live_spec as LS
from trader_core import exit_modes as XM
from trader_core import risk as K
from trader_core import risk_ladder as RL
from trader_engine.config import ConfigError, load_cli_config, load_engine_config
from trader_engine.engine import build_engine

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"

# Canliya ozgu ya da kagit-yalniz evren kaplamasinin (apply_universe_overlay; pairs/optional_pairs/clusters/cost_overrides)
# yonettigi anahtarlar disinda HER anahtar kagitla esit olmali. Izin listesi AYRICA belgelenir:
PARITE_ISTISNA = {
    "mode": "canli kip",
    "var_dir": "canli veri dizini",
    "kill_file": "canli KILL dosyasi",
    "pause_file": "canli PAUSE dosyasi",
    "live": "borsa blogu (yalniz testnet/canli)",
    "bot": "kagit dosyasi bot adini acik yazar; canli bot adini engine.learner.json'dan alir (ayni: learner)",
}


def _j(name):
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


def test_parite_canli_sistem_anahtarlari_kagitla_esit():
    paper, live = _j("engine.paper.json"), _j("engine.live.json")
    farkli = {k for k in set(paper) | set(live) if k not in PARITE_ISTISNA and paper.get(k) != live.get(k)}
    assert farkli == set(), f"canli != kagit: {sorted(farkli)}"
    assert "leverage" not in live


def test_parite_canliya_ozgu_anahtarlar_canlida_kalir():
    live = _j("engine.live.json")
    assert live["mode"] == "live" and live["var_dir"] == "var-live"
    assert live["kill_file"] == "shared/live/KILL" and live["pause_file"] == "shared/live/PAUSE"
    assert live["live"]["expected_wallet_max"] == 2000.0 and live["live"]["account_tag"] == "canli-alt1"


def test_canli_ml_stratejisi_ve_43_cift_yuklenir():
    live, paper = load_cli_config(CONFIG, "learner", "live"), load_cli_config(CONFIG, "learner", "paper")
    assert live.mode == "live" and live.strategy == "price_action_lab_ml"
    assert len(live.pairs) == 43 and "TON/USDT" not in live.pairs and list(live.pairs) == list(paper.pairs)
    assert len(live.optional_pairs) == 24 and set(live.optional_pairs) <= set(live.pairs)   # eski hisse verisi acilisi bloklamaz
    assert live.contract_types == ("PERPETUAL", "TRADIFI_PERPETUAL")
    assert live.max_positions == 24 and live.flat_bar_guard is True
    assert live.arms == paper.arms and live.arm_max_positions == paper.arm_max_positions
    assert live.clusters == paper.clusters and live.cost_overrides == paper.cost_overrides
    assert live.etiket_kurallari == paper.etiket_kurallari
    assert live.exit_modes == paper.exit_modes          # canli kagitla ayni cikis kiplerini kullanir (istisna yok)


def test_canli_risk_sinirlari_024_016_008_hedef_001():
    r = load_cli_config(CONFIG, "learner", "live").risk_config
    assert isinstance(r, K.LiveRiskConfig)
    # 23.11 kullanici karari: asama B esikleri (yapilandirma 0.16 -> 0.06; LIVE_LIMITS tavani 0.16 kalir)
    assert (r.max_open_risk, r.max_same_dir_risk, r.daily_max_loss, r.target_trade_risk) == (0.24, 0.06, 0.08, 0.01)
    assert K.LIVE_LIMITS["max_open_risk"] == 0.24 and K.LIVE_LIMITS["max_same_dir_risk"] == 0.16
    assert K.LIVE_LIMITS["daily_max_loss"] == 0.08
    # canli ust sinirlari asilamaz
    for kw in ({"max_open_risk": 0.25}, {"max_same_dir_risk": 0.17}, {"daily_max_loss": 0.09}):
        with pytest.raises(ValueError):
            K.live_config(**kw)


def test_hard_limits_ve_testnet_degismedi():
    assert (K.HARD_LIMITS["max_open_risk"], K.HARD_LIMITS["max_same_dir_risk"], K.HARD_LIMITS["daily_max_loss"]) == (0.06, 0.04, 0.05)
    assert K.HARD_LIMITS["target_trade_risk"] == 0.014
    assert K.PAPER_LIMITS["max_open_risk"] == 0.24
    with pytest.raises(ValueError):
        K.RiskConfig(max_open_risk=0.24)
    t = load_cli_config(CONFIG, "learner", "testnet").risk_config
    assert type(t) is K.RiskConfig and (t.max_open_risk, t.max_same_dir_risk, t.daily_max_loss) == (0.06, 0.04, 0.05)


def test_canli_gunluk_zarar_kagit_kurali_acik_risk_dahil_degil():
    """Karar A: canli da kagit gibi yalniz bugunku (gerceklesen+gerceklesmemis) zarara bakar; acik risk sayilmaz."""
    live, paper = load_cli_config(CONFIG, "learner", "live").risk_config, load_cli_config(CONFIG, "learner", "paper").risk_config
    locked = K.LOCKED_CFG
    assert live._DAILY_INCLUDES_OPEN_RISK is False and paper._DAILY_INCLUDES_OPEN_RISK is False
    assert locked._DAILY_INCLUDES_OPEN_RISK is True
    cand = K.Candidate("BTC/USDT", "long", 100.0, 99.0, 3.0)
    # gun basi 1000, bugun zarar 0, acik risk 100 (short) + yeni 10 = 110 > 0.08*1000: acik risk sayilsaydi reddedilirdi
    acct = K.AccountState(equity=1000.0, day_start_equity=1000.0,
                          open_positions=[K.OpenPosition("ETH/USDT", "short", 100.0, 100.0)])
    d_live, d_paper = K.check_entry(acct, cand, live), K.check_entry(acct, cand, paper)
    assert d_live.allowed and d_paper.allowed, (d_live.reason, d_paper.reason)
    assert not K.check_entry(acct, cand, locked).allowed
    # bugunku zarar %8'e ulasinca (gerceklesen + gerceklesmemis) yeni giris yok
    acct2 = K.AccountState(equity=920.0, day_start_equity=1000.0, open_positions=[])
    assert not K.check_entry(acct2, cand, live).allowed
    # kademe kopyasi (tightened/replace) canli sinifini ve kuralini korur
    assert isinstance(RL.step_config(live, 1), K.LiveRiskConfig) and RL.step_config(live, 1)._DAILY_INCLUDES_OPEN_RISK is False


def test_testnet_ve_geri_test_kagit_anahtarlarini_reddeder(tmp_path):
    ml = {"strategy": "price_action_lab_ml", "max_positions": 24, "risk": {"max_open_risk": 0.24},
          "clusters": {"k": {"pairs": ["BTC/USDT"], "max_positions": 1}}, "flat_bar_guard": True,
          "contract_types": ["PERPETUAL"], "optional_pairs": ["BTC/USDT"], "etiket_kurallari": {"rejim": {"acik": True}}}
    testnet = _j("engine.testnet.json")
    for k, v in ml.items():
        if k == "strategy":
            continue
        p = tmp_path / f"t_{k}.json"
        p.write_text(json.dumps({**testnet, k: v}))
        with pytest.raises(ConfigError):
            load_engine_config(CONFIG / "engine.base.json", CONFIG / "engine.learner.json", overlay_path=p)
    with pytest.raises(ConfigError):          # testnet: veto off kalir ama exit_modes reddedilir
        p = tmp_path / "t_xm.json"
        p.write_text(json.dumps({**testnet, "exit_modes": {"default": {"breakeven": True}}}))
        load_engine_config(CONFIG / "engine.base.json", CONFIG / "engine.learner.json", overlay_path=p)


# ----------------------------------------------------------------------------------------------- kademe (%1 baslangic)
NOW = RL.parse_at("2026-11-23T10:00:00Z")


def _ladder_log(tmp_path, *, start_step=None, amount=1000.0):
    lg = RL.LadderLog(str(tmp_path / "risk_ladder.jsonl"))
    kw = {} if start_step is None else {"start_step": start_step}
    lg.append("initial", "test", NOW, amount=amount, **kw)
    return lg


def test_canli_kademe_yuzde_bir_baslar_ve_adim_adim_iner(tmp_path):
    base = load_cli_config(CONFIG, "learner", "live").risk_config
    st = _ladder_log(tmp_path, start_step=RL.LIVE_START_STEP).state()
    assert st.step == 2 and RL.STEPS[st.step] == 0.010
    assert RL.step_config(base, st.step).target_trade_risk == 0.01
    # tepeden -%10 -> K1 (0.0075); -%15 -> K0 (0.005); -%20 durma; taban; hepsi degismedi
    a = RL.evaluate(st, 1000.0 * 0.90)
    assert [(x.kind, x.step) for x in a] == [("step_down", 1)]
    a = RL.evaluate(st, 1000.0 * 0.85)
    assert [(x.kind, x.step) for x in a] == [("step_down", 0)]
    assert [x.kind for x in RL.evaluate(st, 1000.0 * 0.80)] == ["review_stop"]
    assert [x.kind for x in RL.evaluate(st, 1000.0 * 0.60)] == ["floor_stop"]
    assert RL.step_config(base, 1).target_trade_risk == 0.0075 and RL.step_config(base, 0).target_trade_risk == 0.005


def test_kademe_varsayilan_baslangic_degismedi_ve_start_step_sinirli(tmp_path):
    (tmp_path / "a").mkdir()
    assert _ladder_log(tmp_path / "a").state().step == RL.START_STEP == 0
    for bad in (3, -1, True, "2", 2.0):
        d = tmp_path / f"b{abs(hash(repr(bad)))}"
        d.mkdir()
        with pytest.raises(RL.LadderLogError):
            _ladder_log(d, start_step=bad)


def test_kademe_dusus_sonrasi_geri_cikis_en_cok_baslangic_basamagina(tmp_path):
    lg = _ladder_log(tmp_path, start_step=2)
    lg.append("step_down", "t", NOW + timedelta(days=1), step=1, trigger="dd_peak_10", equity=900.0, peak=1000.0)
    st = lg.state()
    assert st.step == 1 and st.max_step == 2
    lg.append("step_up", "t", NOW + timedelta(days=100), step=2, decision="kd")        # K1 -> K2 (baslangic basamagi)
    assert lg.state().step == 2
    with pytest.raises(RL.LadderLogError):                                             # K2 -> K3 asla
        lg.append("step_up", "t", NOW + timedelta(days=200), step=3, decision="kd")
    # testnet/kagit gunlugu (start_step yok): tavan hala K0
    (tmp_path / "x").mkdir()
    lg0 = _ladder_log(tmp_path / "x")
    assert lg0.state().max_step == RL.MAX_STEP_APPROVABLE == 0
    assert any("onaylanamaz" in p for p in RL.step_up_problems(lg0.state(), {"step_trades": 99, "step_days": 99, "step_mean_r": 1.0}, NOW))


def test_cli_capital_init_canlida_k2_testnette_k0(tmp_path):
    from trader_engine import cli
    for mode, want in (("live", 2), ("testnet", 0)):
        d = tmp_path / mode
        d.mkdir()
        cfg = LS.make_live_cfg(d, mode=mode)
        log = RL.LadderLog(cfg.path("risk_ladder.jsonl"))
        extra = {"start_step": RL.LIVE_START_STEP} if cfg.mode == "live" else {}
        a = type("A", (), {"by": "t", "note": ""})()
        row, rc = cli._write_row(log, "initial", a, NOW, amount=500.0, **extra)
        assert rc is None and log.state().step == want


# ----------------------------------------------------------------------------------------------- motor kablolamasi
def _live_engine(tmp_path, **over):
    paper = load_cli_config(CONFIG, "learner", "paper")
    base_over = dict(strategy="price_action_lab_ml", target_trade_risk=0.01,
                     risk={"max_open_risk": 0.24, "max_same_dir_risk": 0.16, "daily_max_loss": 0.08},
                     arms=list(paper.arms), arm_max_positions=dict(paper.arm_max_positions), max_positions=24,
                     flat_bar_guard=True, contract_types=["PERPETUAL", "TRADIFI_PERPETUAL"],
                     etiket_kurallari={"rejim": {"acik": True}},
                     exit_modes={"default": {"breakeven": True, "partial": True}})
    base_over.update(over)
    cfg = LS.make_live_cfg(Path(tmp_path), mode="live", **base_over)
    clock, broker, view = LS._injected(tmp_path, cfg)
    env = {"BINANCE_API_KEY": "k" * 40, "BINANCE_API_SECRET": "s" * 40, "LIVE_CONFIRM": LS.TAG}
    return cfg, build_engine(cfg, clock=clock, view=view, broker=broker, env=env)


def test_canli_motor_kagit_yollarini_kurar_ve_exit_modes_uygulanir(tmp_path):
    cfg, eng = _live_engine(tmp_path)
    try:
        assert eng.strategy.info.name == "price_action_lab_ml"
        assert callable(eng.gate.arms_off)
        assert eng.gate.etiket_cfg                                         # rejim etiketi kurali baglandi
        assert eng.cluster_counts() is None or "clusters" in eng.cluster_counts()
        # exit_modes: canlida kagitla ayni cozumlenir (istisna yok)
        pos = type("P", (), {"setup": "T1", "trigger_tf": "1h"})
        m = eng._exit_modes(pos)
        assert cfg.exit_modes and m is not None and m.breakeven and m.partial
        assert m == XM.resolve(load_cli_config(CONFIG, "learner", "paper").exit_modes, "T1", "1h", {})
        assert type(eng.cfg.risk_config).__name__ == "LiveRiskConfig"
    finally:
        eng.state.close()
        eng.ledger.close()


def test_canli_motor_exit_modes_olmadan_kip_yok(tmp_path):
    _, eng = _live_engine(tmp_path, exit_modes={})
    try:
        assert eng._exit_modes(type("P", (), {"setup": "T1", "trigger_tf": "1h"})) is None
    finally:
        eng.state.close()
        eng.ledger.close()


def test_canli_kapi_kagit_kapisini_calistirir_session_tag_dahil():
    src = (ROOT / "src" / "trader_engine" / "gates.py").read_text(encoding="utf-8")
    assert 'self.cfg.mode in ("paper", "live")' in src and 'paper = self.cfg.mode in ("paper", "live")' in src


# ----------------------------------------------------------------------------------------------- broker kural turleri
def test_broker_extract_all_rules_tradifi_perpetual_alir(tmp_path, monkeypatch):
    from trader_engine.brokers import binance_futures as BF
    seen = {}

    def spy(info, symbols, contract_types=("PERPETUAL",)):
        seen["ct"] = tuple(contract_types)
        return {}
    monkeypatch.setattr(BF, "extract_all_rules", spy)
    cfg = LS.make_live_cfg(tmp_path, mode="live", contract_types=["PERPETUAL", "TRADIFI_PERPETUAL"], max_positions=24,
                           risk={"max_open_risk": 0.24}, target_trade_risk=0.01)
    clock, b, _ = LS._injected(tmp_path, cfg)
    b2 = BF.LiveBroker(cfg.live, "live", cfg.leverage, list(cfg.pairs), b._rest, clock, 0.0005, environ={},
                       contract_types=cfg.contract_types)
    b2._apply_rules({})
    assert seen["ct"] == ("PERPETUAL", "TRADIFI_PERPETUAL")
    b._apply_rules({})                                         # varsayilan: yalniz PERPETUAL (testnet degismedi)
    assert seen["ct"] == ("PERPETUAL",)


def test_build_live_broker_contract_types_gecirir():
    src = (ROOT / "src" / "trader_engine" / "engine.py").read_text(encoding="utf-8")
    assert "contract_types=cfg.contract_types" in src


# ----------------------------------------------------------------------------------------------- birim dosyasi
def test_canli_birim_bellek_tavani_kagitla_ayni():
    live = (ROOT / "deploy" / "trader-engine-live.service").read_text(encoding="utf-8")
    paper = (ROOT / "deploy" / "trader-engine@.service").read_text(encoding="utf-8")
    for key in ("MemoryMax", "MemoryHigh"):
        line = next(x for x in paper.splitlines() if x.startswith(key + "="))
        assert line in live.splitlines()
    assert "MemoryMax=750M" in live
