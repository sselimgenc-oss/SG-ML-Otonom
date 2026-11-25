"""DD-12 WP-01 bagimsiz sartname testleri: docs/motor/dd12-capraz-varlik-spec.md (v4) §2, §4.1, §9 (WP-01), §12, §15.

Kapsam: D-T1, D-T2, D-T13 (WP-01 kismi: tarafsizlik), D-T30. Yalniz sartnameden ve onceden var olan koddan (config yukleyici,
risk kilidi, cli) yazildi; gerceklemenin farklarina BAKILMADI.

Taban (onceki davranis): HEAD 0fc8b5c'nin `src/` agaci `git archive` ile gecici dizine acilir ve alt surecte calistirilir;
"onceki EngineConfig ile esit" ve "risk sabitleri bit bit ayni" bununla olculur.

SPEC-AMBIGUOUS notlari (sartnamenin adlandirmadigi yerler):
  * `clusters` JSON bicimi: kume adi -> liste | {pairs/members/symbols: [...], max/cap/limit: n}. Normalize edilir.
  * `risk` blogu anahtar adlari: RiskConfig alan adlari varsayilir (max_open_risk, max_same_dir_risk, daily_max_loss,
    target_trade_risk); degerler EngineConfig.risk_config uzerinden okunur.
  * Cift adlari: taban varlik kodu ("NVDA", "1000SHIB") ile eslesir; tam sembol bicimi (NVDA/USDT) sartnamede yok.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from trader_core import risk
from trader_core.risk import (HARD_LIMITS, LOCKED_CFG, AccountState, Candidate, OpenPosition, check_entry)
from trader_engine import cli
from trader_engine.config import load_cli_config, load_engine_config
from trader_engine.errors import ConfigError

ROOT = Path(__file__).resolve().parents[2]          # .../trader
CONFIG = ROOT / "config"
BASELINE_COMMIT = "0fc8b5c"

BASE10 = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "TRX", "LINK", "AVAX"]
# 22 Kasim: testnet/canli kendi "pairs" listesini tasir (kripto; TradFi ertelendi). Sayilar TEK yerden: bu sabitler.
KRIPTO20 = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA", "TRX", "LINK", "AVAX", "HYPE", "BCH", "XLM", "SUI", "HBAR", "LTC",
            "TON", "1000SHIB", "DOT", "XMR"]
ENV_PAIRS = {"testnet": [f"{b}/USDT" for b in KRIPTO20], "live": [f"{b}/USDT" for b in KRIPTO20 if b != "TON"]}   # TON canlida yok
ENV_PAIRS_LINE = {k: ('  "pairs": [' + ", ".join(f'"{x}"' for x in v) + '],\n').encode() for k, v in ENV_PAIRS.items()}
BUYUK = {"BTC", "ETH", "XRP", "BNB", "SOL"}
TEKNOLOJI = {"NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "ORCL", "NFLX", "PLTR", "AMD"}
METAL = {"XAU", "XAG"}
ENERJI = {"BZ", "COPPER"}
STOCKS20 = {"NVDA", "MSFT", "AAPL", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRKB", "JPM", "LLY", "WMT", "V", "ORCL",
            "XOM", "NFLX", "PLTR", "COST", "AMD", "HD"}
COMMODITY4 = METAL | ENERJI
CAPS = {"kripto_buyuk": 6, "kripto_diger": 9, "hisse": 8, "hisse_teknoloji": 5, "metal": 3, "enerji_sanayi": 3}   # 20 Kasim: kagit tavanlari gevsetildi

PINNED_SHA = {
    "engine.base.json": "2ccdf97d21842f2dc54f682e66d65762f7957a7615befd932fbad8c68f49325e",   # 24.11 kullanici karari: veto ve C1 artiklari silindi (veto_mode/veto_config kalkti);   # WP-06a: yalniz veto_config yolu; 24.11 kullanici karari: ML filtreleri silindi (ml_mode/ml_model_path kalkti)
    "engine.learner.json": "30ca2842c40cacafbf6cdd90c9e6f1f54fc62b9a9ec913476d1399ac5352cb12",
    "engine.testnet.json": "eff9eb61dcd9018bf86c195a02f7f25f08960473e705cbd114e104c26a956c9c",   # 24.11 kullanici karari: veto ve C1 artiklari silindi
    "engine.live.json": "b7e6ca631e84e688115b7561db28cb275b9db7fef1713739e64ebe3c604e0bcd",   # 24.11 kullanici karari: formasyon kutuphanesi birlesik (MF1 48 + GF1 52 + IN1 66 + PA2 29 + PA varyantlari 56 kol; max_positions 36)
    #   # 24.11 kullanici karari: veto ve C1 artiklari silindi (veto_mode, arm_max_positions L1 kalkti);   # 24.11 kullanici karari: DL1 dort zaman dilimi acik; onceki 24.11 ML filtreleri silindi
}
# 23.11 kullanici karari: canli = kagit. engine.live.json'a eklenen kagit sistem anahtarlari (+ pairs yerine kagit evreni).
LIVE_PAPER_SYSTEM_KEYS = {"pairs", "optional_pairs", "strategy", "arms", "arm_max_positions", "shadow_blocks",
                          "exit_modes", "max_positions", "target_trade_risk", "risk", "clusters", "etiket_kurallari",
                          "flat_bar_guard", "contract_types", "cost_overrides",
                          "korelasyon", "kayip_freni", "toplam_buyukluk_kat",   # 23.11 kullanici karari: asama B esikleri
                          "uzun_yon",   # 23.11 kullanici karari: fikir 7 uzun donem yon kapisi
                          "arm_family_max_positions",   # 24.11 kullanici karari: formasyon kutuphanesi (aile tavani)
                          "target_mode"}   # 24.11 kullanici karari: hedef bekleyen emir (kagitla ayni "resting"; taban dosya "bar_close" kalir)
VETO_KEYS_REMOVED = {"veto_mode", "veto_config"}   # 24.11 kullanici karari: veto ve C1 artiklari silindi
ML_KEYS_REMOVED = {"ml_mode", "ml_model_path", "ml_features", "ml_experimental", "ml_pairs"}   # 24.11 kullanici karari: ML filtreleri silindi
UNIT_SHA = {
    "trader-engine-testnet.service": "2fa9d51bb0301cadc3339cbbaf9dc1b61dbbbdd3f52b79531fdbb3dd0d587413",   # 24.11 kullanici karari: veto ve C1 artiklari silindi (EnvironmentFile veto-hmac satiri kalkti)
    "trader-engine-live.service": "7cf61d50e932b92905d37910f7fdf59177bcd77ac3fabd05abca703f2c3068a1",   # 24.11 kullanici karari: veto ve C1 artiklari silindi (EnvironmentFile veto-hmac satiri kalkti);   # 23.11 kullanici karari: canli = kagit (MemoryMax 750M, MemoryHigh 600M)
}


# --------------------------------------------------------------------------- yardimcilar
def _base(pair: str) -> str:
    return pair.split("/")[0].split(":")[0].upper()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git_show(path: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), "show", f"{BASELINE_COMMIT}:./{path}"],
                          check=True, capture_output=True).stdout


def _paper():
    return load_cli_config(CONFIG, "learner", "paper")


def _paper_raw() -> dict:
    return json.loads((CONFIG / "engine.paper.json").read_text(encoding="utf-8"))


def _norm_clusters(obj) -> dict[str, tuple[set[str], int | None]]:
    """-> {ad: ({taban varlik kodlari}, tavan)}"""
    def one(v):
        if isinstance(v, dict):
            members = next((v[k] for k in ("pairs", "members", "symbols", "instruments") if k in v), None)
            cap = next((v[k] for k in ("max", "cap", "limit", "max_positions", "max_open") if k in v), None)
            return {_base(p) for p in (members or [])}, cap
        if hasattr(v, "__dataclass_fields__"):
            return one(dataclasses.asdict(v))
        return {_base(p) for p in v}, None
    if isinstance(obj, dict):
        return {k: one(v) for k, v in obj.items()}
    out = {}
    for item in obj:                                  # liste bicimi: ad iceren nesneler
        d = dataclasses.asdict(item) if hasattr(item, "__dataclass_fields__") else item
        out[d.get("name")] = one(d)
    return out


def _clusters_of(cfg):
    obj = getattr(cfg, "clusters", None)
    if obj is None:
        obj = _paper_raw()["clusters"]
    return _norm_clusters(obj)


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    """HEAD 0fc8b5c kaynak agaci + onun yukledigi configlerin dokumu."""
    d = tmp_path_factory.mktemp("baseline")
    # src VE config birlikte: eski yukleyici eski config ile calisir (testnet DD-12 veto kaldirma)
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", BASELINE_COMMIT, "src", "config"], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(d)], input=tar, check=True)
    script = textwrap.dedent("""
        import dataclasses, json, sys
        from trader_engine.config import load_cli_config
        from trader_core.risk import LOCKED_CFG, HARD_LIMITS
        out = {"locked": dataclasses.asdict(LOCKED_CFG), "hard": HARD_LIMITS, "cfg": {}}
        for env in (None, "testnet", "live"):
            c = load_cli_config(sys.argv[1], "learner", env)
            out["cfg"][str(env)] = {"cfg": dataclasses.asdict(c), "risk": dataclasses.asdict(c.risk_config)}
        print(json.dumps(out, default=str, sort_keys=True))
    """)
    env = dict(os.environ, PYTHONPATH=str(d / "src"))
    r = subprocess.run([sys.executable, "-c", script, str(d / "config")], check=True, capture_output=True, text=True, env=env)
    return json.loads(r.stdout.replace(str(d), str(ROOT)))     # goreli yollar arsivde farkli koke cozulur: ayni repo koküne esle


def _cur_dump(envname):
    c = load_cli_config(CONFIG, "learner", envname)
    return json.loads(json.dumps({"cfg": dataclasses.asdict(c), "risk": dataclasses.asdict(c.risk_config)},
                                 default=str, sort_keys=True))


# --------------------------------------------------------------------------- D-T1
@pytest.mark.parametrize("envname", [None, "testnet", "live"])
def test_dt1_katmansiz_yukleme_onceki_engineconfig_ile_esit(baseline, envname):
    """D-T1: katmansiz (learner), testnet, live: onceki alanlar bit bit ayni; yeni alanlar bu yollarda onceki
    davranisi degistirmez (risk_config dahil)."""
    cur = _cur_dump(envname)
    old = baseline["cfg"][str(envname)]
    for k, v in old["cfg"].items():
        if k in ML_KEYS_REMOVED:                           # 24.11 kullanici karari: ML filtreleri silindi; ML anahtarlari EngineConfig'ten kalkti
            assert k not in cur["cfg"], k
            continue
        if envname == "live" and k in LIVE_PAPER_SYSTEM_KEYS:   # 23.11 kullanici karari: canli = kagit (parite testi: test_canli_kagit_parite.py)
            continue
        if k in VETO_KEYS_REMOVED:                         # 24.11 kullanici karari: veto ve C1 artiklari silindi; anahtarlar EngineConfig'ten kalkti
            assert k not in cur["cfg"], k
            continue
        if k == "pairs" and envname in ENV_PAIRS:           # 22.11: tek beklenen fark: kendi pairs listesi (kripto)
            assert len(v) == 10 and cur["cfg"][k] == ENV_PAIRS[envname]
            continue
        if k == "live" and envname == "live":               # 23.11 kullanici karari (d): canli kasa tavani 1500 -> 2000; baska fark yok
            assert v["expected_wallet_max"] == 1500.0 and cur["cfg"][k] == {**v, "expected_wallet_max": 2000.0}
            continue
        assert cur["cfg"][k] == v, f"{envname}: alan {k} degisti"
    if envname == "live":      # 23.11 kullanici karari: canli = kagit (LIVE_LIMITS 0.24/0.16/0.08, hedef %1)
        assert (cur["risk"]["max_open_risk"], cur["risk"]["max_same_dir_risk"], cur["risk"]["daily_max_loss"],
                cur["risk"]["target_trade_risk"]) == (0.12, 0.06, 0.08, 0.01)   # 23.11 kullanici karari: asama B esikleri
        return
    if envname == "paper":     # 23.11 kullanici karari: asama B esikleri (max_same_dir_risk 0.16 -> 0.06)
        assert cur["risk"] == {**old["risk"], "max_same_dir_risk": 0.06}
        return
    assert cur["risk"] == old["risk"]


def test_dt1_katmansiz_yukleme_hala_10_cift_ve_paper_degil_katman():
    cfg = load_cli_config(CONFIG, "learner", None)
    assert len(cfg.pairs) == 10 and cfg.bot == "learner" and cfg.mode == "paper"
    assert cfg.shadow_blocks == ("regime", "r1_disabled", "same_bar_reentry", "tf_15m")


@pytest.mark.parametrize("name", sorted(PINNED_SHA))
def test_dt1_dt13_config_dosyalari_degismedi(name):
    """engine.base/learner/testnet/live: sabit karma ve HEAD ile ayni bayt."""
    p = CONFIG / name
    assert _sha(p) == PINNED_SHA[name]
    head = _git_show(f"config/{name}")
    if name == "engine.base.json":      # DD-12 WP-06a: config/veto.json -> config/veto.live.json (testnet/canli veto yapilandirmasi); baska fark yok
        head = head.replace(b'  "veto_mode": "required",\n', b"", 1).replace(b'"veto_config": "config/veto.json", "kill_file"', b'"kill_file"', 1)   # 24.11 kullanici karari: veto ve C1 artiklari silindi
        head = head.replace(b'  "ml_mode": "off",\n  "ml_model_path": null,\n', b"", 1)      # 24.11 kullanici karari: ML filtreleri silindi
    if name in ("engine.testnet.json", "engine.live.json"):   # 22.11: kendi "pairs" satiri (kill_file'dan once); baska fark yok
        env = name.split(".")[1]
        head = head.replace(b'  "kill_file"', ENV_PAIRS_LINE[env] + b'  "kill_file"', 1)
    if name == "engine.live.json":      # 23.11 kullanici karari (d): canli kasa tavani 1500 -> 2000
        head = head.replace(b'"expected_wallet_max": 1500.0', b'"expected_wallet_max": 2000.0', 1)
        # 23.11 kullanici karari: canli = kagit. Dosya artik kagit sistem anahtarlarini da tasir; yalniz canliya ozgu anahtarlar
        # (kip, var_dir, kill/pause, live blogu) HEAD ile ayni kalir. Sistem anahtarlari parite testiyle (kagitla esit) korunur.
        cur, old = json.loads(p.read_bytes()), json.loads(head)
        for k in ("mode", "var_dir", "kill_file", "pause_file", "live"):
            assert cur[k] == old[k], k
        assert set(cur) - set(old) <= LIVE_PAPER_SYSTEM_KEYS
        return
    assert p.read_bytes() == head


@pytest.mark.parametrize("name", sorted(UNIT_SHA))
def test_dt13_testnet_canli_birim_dosyalari_degismedi(name):
    assert _sha(ROOT / "deploy" / name) == UNIT_SHA[name]


def test_dt1_bot_twin_reddedilir(tmp_path):
    bot = tmp_path / "twin.json"
    bot.write_text('{"bot": "twin"}')
    with pytest.raises(ConfigError):
        load_engine_config(CONFIG / "engine.base.json", bot)
    with pytest.raises(ConfigError):
        load_engine_config(CONFIG / "engine.base.json", CONFIG / "engine.learner.json", overlay_path=bot)
    # paper katmaniyla da
    with pytest.raises(ConfigError):
        load_engine_config(CONFIG / "engine.base.json", CONFIG / "engine.learner.json",
                           overlay_path=_write(tmp_path, "tw2.json", {**_paper_raw(), "bot": "twin"}))


def test_dt1_cli_bot_twin_kalkti():
    ap = cli.build_parser()
    with pytest.raises(SystemExit):
        ap.parse_args(["run", "--bot", "twin", "--env", "paper"])
    with pytest.raises(SystemExit):
        ap.parse_args(["run", "--bot", "twin"])


def test_dt1_eski_katman_dosyalari_silindi():
    assert not (CONFIG / "engine.twin.json").exists()
    assert not (CONFIG / "engine.paper-ml.json").exists()


# --------------------------------------------------------------------------- D-T2 (paper)
def test_dt2_paper_44_cift_taban_10_ust_kumesi():
    cfg = _paper()
    assert cfg.mode == "paper" and cfg.bot == "learner"
    assert len(cfg.pairs) == 43 and len(set(cfg.pairs)) == 43   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    bases = [_base(p) for p in cfg.pairs]
    base10 = load_cli_config(CONFIG, "learner", None).pairs
    assert set(base10) <= set(cfg.pairs)
    assert set(BASE10) <= set(bases)
    assert STOCKS20 <= set(bases) and COMMODITY4 <= set(bases)
    assert len(set(bases) - STOCKS20 - COMMODITY4) == 19          # 19 kripto   # 23.11 kullanici karari: TON cikarildi (SETTLING)


def test_dt2_paper_golgeli_24_pozisyon():
    cfg = _paper()
    assert cfg.shadow_blocks == ("regime", "r1_disabled", "same_bar_reentry", "tf_15m")      # 19.11 (kagitta her sey acik): golge karar satirlari acik (karar yolunu etkilemez)
    ob = cfg.exit_modes["default"]["breakeven"]["offset_bps"]
    assert cfg.exit_modes == {"default": {"breakeven": {"trigger_r": 1.0, "offset_bps": ob}, "partial": {"trigger_r": 1.5, "frac": 0.5}},
                              "H2-YARI": {"breakeven": {"trigger_r": 1.0, "offset_bps": ob},
                                          "partial": {"trigger_r": 2.0, "frac": 0.5}}}   # 24.11 kullanici karari: PA varyantlari (H2-YARI kismi 2 R)      # 19.11: cikis kipleri kagitta ACIK (spec varsayilanlari)
    assert cfg.max_positions == 24
    assert cfg.target_trade_risk == 0.01                           # islem basi %1


def test_dt2_ml_anahtarlari_silindi(tmp_path):
    # 24.11 kullanici karari: ML filtreleri (v1, v2, kurulum filtresi) silindi; ML yapilandirma anahtarlari artik bilinmeyen anahtardir
    cfg = _paper()
    assert not any(hasattr(cfg, k) for k in ML_KEYS_REMOVED)
    assert not ML_KEYS_REMOVED & set(_paper_raw())
    for k in sorted(ML_KEYS_REMOVED):
        with pytest.raises(ConfigError):
            _load_overlay(_write(tmp_path, f"{k}.json", {**_paper_raw(), k: "off" if k == "ml_mode" else None}))


def test_dt2_paper_optional_pairs_hisse_emtia_24():
    cfg = _paper()
    # 19 Kasim: TON vadelisi Binance'te not_trading; zorunlu olunca besleme acilmiyordu => istege bagli
    assert len(cfg.optional_pairs) == 24   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    assert {_base(p) for p in cfg.optional_pairs} == STOCKS20 | COMMODITY4
    assert set(cfg.optional_pairs) <= set(cfg.pairs)


def test_dt2_paper_kumeler_ve_tavanlar_4_6_5_3_2_2():
    cfg = _paper()
    cl = _clusters_of(cfg)
    assert set(cl) == set(CAPS)
    for name, cap in CAPS.items():
        assert cl[name][1] == cap, name
    assert cl["kripto_buyuk"][0] == BUYUK
    assert cl["hisse_teknoloji"][0] == TEKNOLOJI
    assert cl["metal"][0] == METAL and cl["enerji_sanayi"][0] == ENERJI
    assert cl["hisse"][0] == STOCKS20 and len(cl["hisse"][0]) == 20
    assert len(cl["kripto_diger"][0]) == 14 and not (cl["kripto_diger"][0] & BUYUK)   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    assert not (cl["kripto_diger"][0] & (STOCKS20 | COMMODITY4))
    assert TEKNOLOJI <= cl["hisse"][0]                              # cok uyelik: teknoloji ayni zamanda hisse
    pair_bases = {_base(p) for p in cfg.pairs}
    for name, (members, _) in cl.items():
        assert members <= pair_bases, name


def test_dt2_paper_kume_seans_sutunu_yok_ve_veto_kavrami_yok():
    raw = _paper_raw()
    assert "veto_exempt_pairs" not in raw and "veto_path" not in raw
    assert "session" not in json.dumps(raw["clusters"]).lower()


def test_dt2_paper_flat_bar_ve_contract_types():
    cfg = _paper()
    assert getattr(cfg, "flat_bar_guard") in (True, {"enabled": True}) or bool(cfg.flat_bar_guard)
    ct = tuple(cfg.contract_types)
    assert "PERPETUAL" in ct and "TRADIFI_PERPETUAL" in ct
    assert hasattr(cfg, "cost_overrides")


def test_dt2_paper_yeni_anahtar_ham_json_listesi():
    raw = _paper_raw()
    for k in ("pairs", "optional_pairs", "strategy", "shadow_blocks", "max_positions", "risk", "clusters",
              "flat_bar_guard", "contract_types", "cost_overrides"):
        assert k in raw, k
    assert not ML_KEYS_REMOVED & set(raw)
    assert raw["shadow_blocks"] == ["regime", "r1_disabled", "same_bar_reentry", "tf_15m"] and raw["max_positions"] == 24


# --------------------------------------------------------------------------- D-T2 (yalniz --env paper)
def test_dt2_paper_katmani_yalniz_env_paper_ile_uygulanir():
    plain = load_cli_config(CONFIG, "learner", None)
    paper = load_cli_config(CONFIG, "learner", "paper")
    assert len(plain.pairs) == 10 and len(paper.pairs) == 43   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    assert plain.shadow_blocks != () and paper.shadow_blocks == plain.shadow_blocks      # 19.11: kagitta golge satirlar acik
    assert plain.exit_modes == {} and paper.exit_modes != {}
    for env in ("testnet", "live"):
        c = load_cli_config(CONFIG, "learner", env)
        if env == "live":       # 23.11 kullanici karari: canli = kagit (paper'in 43 cifti, ML aktif, kumeler/tavanlar)
            assert c.mode == "live" and list(c.pairs) == list(paper.pairs) and len(c.pairs) == 43
            assert c.max_positions == paper.max_positions
            continue
        assert c.mode == env and list(c.pairs) == ENV_PAIRS[env]
        assert getattr(c, "max_positions", None) in (None, 0, 1)   # yeni alan varsayilan (kapali) kalir


def test_dt2_cli_env_paper_kabul_ve_yukler():
    ap = cli.build_parser()
    a = ap.parse_args(["run", "--bot", "learner", "--env", "paper", "--config-dir", str(CONFIG)])
    assert a.env == "paper"
    cfg = cli._load_cfg(a)
    assert cfg.mode == "paper" and len(cfg.pairs) == 43   # 23.11 kullanici karari: TON cikarildi (SETTLING)
    b = ap.parse_args(["run", "--bot", "learner", "--config-dir", str(CONFIG)])
    assert b.env is None and len(cli._load_cfg(b).pairs) == 10


def test_dt2_env_paper_diger_alt_komutlarda_da_kabul():
    ap = cli.build_parser()
    for argv in (["kill", "--env", "paper"], ["pause", "--bot", "learner", "--env", "paper"],
                 ["init-ledger", "--bot", "learner", "--env", "paper"]):
        assert ap.parse_args(argv).env == "paper"


# --------------------------------------------------------------------------- D-T2 (hata dallari)
def _write(tmp: Path, name: str, obj) -> Path:
    p = tmp / name
    p.write_text(json.dumps(obj))
    return p


def _load_overlay(overlay: Path):
    return load_engine_config(CONFIG / "engine.base.json", CONFIG / "engine.learner.json", overlay_path=overlay)


def _inject_cluster_pair(raw: dict, pair: str):
    cl = raw["clusters"]
    first = next(iter(cl.values())) if isinstance(cl, dict) else cl[0]
    if isinstance(first, list):
        first.append(pair)
        return
    for k in ("pairs", "members", "symbols", "instruments"):
        if k in first:
            first[k].append(pair)
            return
    raise AssertionError("kume bicimi taninmadi")


def test_dt2_paper_kopyasi_kontrol_yuklenir(tmp_path):
    cfg = _load_overlay(_write(tmp_path, "ok.json", _paper_raw()))
    assert len(cfg.pairs) == 43   # 23.11 kullanici karari: TON cikarildi (SETTLING)


@pytest.mark.parametrize("which", ["cluster", "optional_pairs"])
def test_dt2_pairs_disi_cift_hata(tmp_path, which):
    raw = copy.deepcopy(_paper_raw())
    ghost = "ZZZZ/USDT"
    if which == "cluster":
        _inject_cluster_pair(raw, ghost)
    else:
        base = raw.get(which, ["BTC/USDT"])
        raw[which] = list(base) + [ghost]
    with pytest.raises(ConfigError):
        _load_overlay(_write(tmp_path, "bad.json", raw))


NEW_KEYS = {
    "max_positions": 16,
    "optional_pairs": ["ETH/USDT"],
    "clusters": {"k": {"pairs": ["BTC/USDT"], "max": 1}},
    "risk": {"max_open_risk": 0.12, "max_same_dir_risk": 0.08, "daily_max_loss": 0.08},
    "contract_types": ["PERPETUAL"],
    "flat_bar_guard": True,
}


@pytest.mark.parametrize("env", ["testnet", "backtest"])        # 23.11 kullanici karari: canli = kagit (canli bu anahtarlari kabul eder)
@pytest.mark.parametrize("key", sorted(NEW_KEYS))
def test_dt2_dt30_yeni_anahtarlar_testnet_canli_geri_testte_configerror(tmp_path, env, key):
    if env == "backtest":
        layer = {"mode": "backtest"}
    else:
        layer = json.loads((CONFIG / f"engine.{env}.json").read_text())
    _load_overlay(_write(tmp_path, "ctl.json", layer))              # kontrol: anahtarsiz yuklenir
    with pytest.raises(ConfigError):
        _load_overlay(_write(tmp_path, "bad.json", {**layer, key: NEW_KEYS[key]}))


@pytest.mark.parametrize("env", ["testnet", "backtest"])        # 23.11 kullanici karari: canli = kagit
def test_dt30_risk_anahtarlari_tek_tek_testnet_canli_geri_testte_configerror(tmp_path, env):
    layer = ({"mode": "backtest"} if env == "backtest"
             else json.loads((CONFIG / f"engine.{env}.json").read_text()))
    for k, v in (("max_open_risk", 0.12), ("max_same_dir_risk", 0.08), ("daily_max_loss", 0.08)):
        with pytest.raises(ConfigError):
            _load_overlay(_write(tmp_path, f"b_{k}.json", {**layer, "risk": {k: v}}))


# --------------------------------------------------------------------------- D-T30 / D-T13 risk
def test_dt30_paper_risk_yuzdeleri():
    cfg = _paper()
    rc = cfg.risk_config
    assert rc.target_trade_risk == pytest.approx(0.01)
    assert rc.max_open_risk == pytest.approx(0.12)
    assert rc.max_same_dir_risk == pytest.approx(0.06)   # 23.11 kullanici karari: asama B esikleri
    assert rc.daily_max_loss == pytest.approx(0.08)
    assert rc.max_trade_risk >= rc.target_trade_risk


def _state(equity=1000.0, day_start=1000.0, opens=()):
    return AccountState(equity=equity, day_start_equity=day_start, open_positions=list(opens))


def _cand(pair="ETH/USDT:USDT", side="long"):
    stop = 98.0 if side == "long" else 102.0
    return Candidate(pair=pair, side=side, entry=100.0, stop=stop, leverage=3)


def test_dt30_paper_davranis_toplam_ve_ayni_yon_ve_gunluk():
    rc = _paper().risk_config
    pos = lambda p, s, r: OpenPosition(pair=p, side=s, risk_amount=r, margin=0.0)
    # toplam acik 60 (30 long + 30 short) + yeni ~10: paper izinli, kilitli (%5 gunluk/%6 toplam) reddeder
    st = _state(opens=[pos("BTC/USDT:USDT", "long", 30.0), pos("SOL/USDT:USDT", "short", 30.0)])
    assert check_entry(st, _cand(), rc).allowed
    assert not check_entry(st, _cand(), LOCKED_CFG).allowed
    # ayni yon (Karar A, 21.11): gunluk butce artik acik riski saymaz; long 45 + ~10 izinli, long 55 + ~10 > %6 (60) -> ret
    # 23.11 kullanici karari: asama B esikleri (max_same_dir_risk 0.16 -> 0.06)
    st2 = _state(opens=[pos("BTC/USDT:USDT", "long", 45.0)])
    assert check_entry(st2, _cand(), rc).allowed
    assert not check_entry(_state(opens=[pos("BTC/USDT:USDT", "long", 55.0)]), _cand(), rc).allowed
    # gunluk zarar %6: paper'da kural 4 tetiklenmez (limit %8); 60+10... yalniz gunluk butce: 60 + 0 + 10 <= 80 izinli
    st3 = _state(equity=940.0, day_start=1000.0)
    assert check_entry(st3, _cand(), rc).allowed
    assert not check_entry(st3, _cand(), LOCKED_CFG).allowed
    # gunluk zarar %8.1 -> paper'da da reddedilir
    assert not check_entry(_state(equity=919.0, day_start=1000.0), _cand(), rc).allowed


def test_dt13_risk_varsayilan_sabitleri_bit_bit_ayni(baseline):
    assert json.loads(json.dumps(dataclasses.asdict(LOCKED_CFG))) == baseline["locked"]
    assert HARD_LIMITS == baseline["hard"]
    d = dataclasses.asdict(risk.RiskConfig())
    assert d["max_open_risk"] == 0.06 and d["max_same_dir_risk"] == 0.04 and d["daily_max_loss"] == 0.05
    assert d["max_trade_risk"] == 0.02 and d["target_trade_risk"] == 0.014


@pytest.mark.parametrize("env", ["testnet"])      # 23.11 kullanici karari: canli = kagit (canli limitleri: test_canli_kagit_parite.py)
def test_dt13_testnet_canli_risk_limitleri_degismedi(env):
    rc = load_cli_config(CONFIG, "learner", env).risk_config
    assert (rc.max_open_risk, rc.max_same_dir_risk, rc.daily_max_loss) == (0.06, 0.04, 0.05)
    assert rc.target_trade_risk == 0.005                           # taban config degeri


def test_dt13_katmansiz_risk_config_degismedi(baseline):
    rc = load_cli_config(CONFIG, "learner", None).risk_config
    assert dataclasses.asdict(rc) == baseline["cfg"]["None"]["risk"]
    assert (rc.max_open_risk, rc.max_same_dir_risk, rc.daily_max_loss) == (0.06, 0.04, 0.05)


def test_dt13_paper_layer_diger_ortamlari_kirletmez():
    """paper'dan sonra yuklenen testnet/live/katmansiz risk ve cift sayilari ayni (modul-duzeyi durum sizmaz)."""
    _paper()
    assert len(load_cli_config(CONFIG, "learner", None).pairs) == 10
    assert load_cli_config(CONFIG, "learner", "testnet").risk_config.max_open_risk == 0.06
    assert load_cli_config(CONFIG, "learner", "live").risk_config.max_open_risk == 0.12   # 23.11 kullanici karari: canli = kagit
    assert LOCKED_CFG.max_open_risk == 0.06
