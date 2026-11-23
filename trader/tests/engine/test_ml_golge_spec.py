"""ML golge deneyi (docs/ml/ml-golge-deney-spec.md) bagimsiz testleri: G-T1..G-T6 + G-5 tarafsizlik.

Uygulama koduna/uygulayici testine bakilmadan, yalniz belirtimden yazildi."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

from trader_core.ml_features import FEATURE_NAMES
from trader_core.ml_live_v2 import RECIPE_NAMES
from trader_core.ml_package import (MODEL_EXPIRY_DAYS, PackageError, canon, feature_list_hash, load_model_view,
                                    load_package, sha256_text)
from trader_engine.config import ConfigError, load_engine_config
from trader_engine.strategies.price_action_v1_ml import load_engine_model

ROOT = Path(__file__).resolve().parents[2]
CFG = ROOT / "config"
UTC = timezone.utc
NOW = datetime(2026, 3, 5, tzinfo=UTC)
R03_SRC = ROOT / "research" / "ml" / "r03" / "model_candidate.json"
R03_DST = ROOT / "models" / "ml1-r03.json"
# 19 Kasim: r03 kagitta emekli (kullanici karari). r03 kod yolu hala test edilir: eski paper ML anahtarlari gecici katmanda.
R03_ML_PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "ADA/USDT", "TRX/USDT",
                "LINK/USDT", "AVAX/USDT"]
R03_PAPER_KEYS = {"ml_mode": "active", "ml_pairs": R03_ML_PAIRS, "ml_features": "r03",
                  "ml_model_path": "models/ml1-r03.json", "ml_experimental": True}


# ------------------------------------------------------------------------------------------------ yardimcilar
def make_pkg(*, gate=False, threshold=None, created=None, features=None, intercept=0.0, coef_atr=0.0, approved=True):
    names = list(features or FEATURE_NAMES)
    n = len(names)
    coef = [0.0] * n
    if "f_atr_ratio" in names:
        coef[names.index("f_atr_ratio")] = coef_atr
    model = {"kind": "logistic", "n_features": n, "coef": coef, "intercept": intercept,
             "mean": [0.0] * n, "std": [1.0] * n, "fill": [0.0] * n}
    body = {"model": model, "calibration": {"a": 1.0, "b": 0.0}, "threshold": threshold}
    created = created or datetime(2026, 3, 1, tzinfo=UTC)
    meta = {"version": "test", "created_at": created.isoformat(),
            "expires_at": (created + timedelta(days=MODEL_EXPIRY_DAYS)).isoformat(),
            "features": names, "feature_list_hash": feature_list_hash(names), "model_hash": sha256_text(canon(body)),
            "gate_passed": gate}
    if approved:
        meta["user_approved"] = True
    return {"meta": meta, **body}


def _load(pkg, **kw):
    kw.setdefault("ml_mode", "shadow")
    kw.setdefault("now", NOW)
    return load_model_view(pkg, expected_features=FEATURE_NAMES, **kw)


def _cfg_file(tmp_path, *, mode="paper", ml_mode="shadow", exp=True, extra=None, name="c.json"):
    """base + learner (+ testnet/live katmani) birlestirilmis tek dosya; `exp` None ise anahtar yazilmaz."""
    raw = json.loads((CFG / "engine.base.json").read_text())
    raw.update(json.loads((CFG / "engine.learner.json").read_text()))
    if mode in ("testnet", "live"):
        raw.update(json.loads((CFG / f"engine.{mode}.json").read_text()))
    raw["mode"] = mode
    raw.update({"ml_mode": ml_mode, "ml_model_path": "models/ml1-r03.json", "ml_features": "r03"})
    if mode == "backtest":
        raw["veto_mode"] = "off"
    if exp is None:
        raw.pop("ml_experimental", None)
    else:
        raw["ml_experimental"] = exp
    raw.update(extra or {})
    p = tmp_path / name
    p.write_text(json.dumps(raw))
    return p


# ------------------------------------------------------------------------------------------------ G-T1
class TestG1Config:
    def test_default_is_false_and_key_optional(self, tmp_path):
        cfg = load_engine_config(_cfg_file(tmp_path, exp=None, ml_mode="off"))
        assert cfg.ml_experimental is False

    def test_paper_shadow_true_loads(self, tmp_path):
        cfg = load_engine_config(_cfg_file(tmp_path, mode="paper", ml_mode="shadow", exp=True))
        assert cfg.ml_experimental is True and cfg.ml_mode == "shadow" and cfg.mode == "paper"

    @pytest.mark.parametrize("mode,ml_mode", [("paper", "off"), ("paper", "active"), ("testnet", "shadow"),
                                              ("live", "shadow"), ("backtest", "shadow"), ("testnet", "off"),
                                              ("live", "active")])
    def test_true_elsewhere_is_config_error(self, tmp_path, mode, ml_mode):
        # kontrol: bayrak olmadan ayni yapilandirma gecerli (hata gercekten bayraktan geliyor)
        load_engine_config(_cfg_file(tmp_path, mode=mode, ml_mode=ml_mode, exp=False, name="ok.json"))
        with pytest.raises(ConfigError, match="ml_experimental"):
            load_engine_config(_cfg_file(tmp_path, mode=mode, ml_mode=ml_mode, exp=True, name="bad.json"))

    @pytest.mark.parametrize("val", ["true", 1, 0, "yes", [True], {}])
    def test_non_bool_is_config_error(self, tmp_path, val):
        with pytest.raises(ConfigError):
            load_engine_config(_cfg_file(tmp_path, exp=val))

    def test_apply_overrides_enforces_lock(self, tmp_path):
        from trader_engine.config import apply_overrides
        cfg = load_engine_config(_cfg_file(tmp_path, exp=True))
        with pytest.raises(ConfigError, match="ml_experimental"):
            apply_overrides(cfg, ml_mode="active")
        assert apply_overrides(cfg, ml_experimental=False, ml_mode="off").ml_experimental is False


# ------------------------------------------------------------------------------------------------ G-T2
class TestG2Loading:
    def test_gate_failed_rejected_without_experimental(self):
        for pkg in (make_pkg(gate=False, threshold=0.5), make_pkg(gate=True, threshold=None)):
            with pytest.raises(PackageError):
                _load(pkg)
            with pytest.raises(PackageError):
                _load(pkg, experimental=False)
        v, err = load_engine_model(None, "shadow", NOW)           # yol yok davranisi degismez
        assert v is None and err

    def test_gate_failed_loads_with_experimental_shadow(self):
        v = _load(make_pkg(gate=False, threshold=0.37), experimental=True)
        assert v.experimental is True and v.threshold == pytest.approx(0.37)
        assert float(v.score(np.zeros((1, len(FEATURE_NAMES))))[0]) == pytest.approx(0.5)

    def test_null_threshold_defaults_to_half(self):
        v = _load(make_pkg(gate=False, threshold=None), experimental=True)
        assert v.experimental is True and v.threshold == 0.5

    def test_default_view_not_experimental(self):
        v = _load(make_pkg(gate=True, threshold=0.4))
        assert v.experimental is False
        assert _load(make_pkg(gate=True, threshold=0.4), experimental=False).experimental is False

    def test_experimental_with_gated_package_still_loads(self):
        v = _load(make_pkg(gate=True, threshold=0.4), experimental=True)
        assert v.experimental is True and v.threshold == pytest.approx(0.4)

    def test_load_package_require_gate_false_skips_gate(self):
        assert load_package(make_pkg(gate=False, threshold=None), now=NOW, require_gate=False)

    def test_engine_loader_from_file(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text(json.dumps(make_pkg(gate=False, threshold=None)))
        v, err = load_engine_model(str(p), "shadow", NOW, experimental=True)
        assert err is None and v is not None and v.experimental is True
        v, err = load_engine_model(str(p), "shadow", NOW)
        assert v is None and err                                   # mevcut ret
        v, err = load_engine_model(str(p), "shadow", NOW, experimental=False)
        assert v is None and err

    def test_real_r03_candidate_loads_experimental(self):
        v = load_model_view(R03_SRC, expected_features=RECIPE_NAMES["r03"], ml_mode="shadow",
                            now=datetime(2026, 11, 20, tzinfo=UTC), experimental=True)
        assert v.experimental is True and v.features == tuple(RECIPE_NAMES["r03"]) and v.threshold == 0.5
        with pytest.raises(PackageError):                          # kapi yine de calisir (gate_passed false)
            load_model_view(R03_SRC, expected_features=RECIPE_NAMES["r03"], ml_mode="shadow",
                            now=datetime(2026, 11, 20, tzinfo=UTC))

    def test_feature_list_mismatch_still_rejected(self):
        with pytest.raises(PackageError):
            load_model_view(make_pkg(), expected_features=["x"], ml_mode="shadow", now=NOW, experimental=True)


# ------------------------------------------------------------------------------------------------ G-T3
class TestG3ActiveForbidden:
    def test_view_loader_value_error(self):
        with pytest.raises(ValueError):
            _load(make_pkg(gate=True, threshold=0.5), ml_mode="active", experimental=True)
        with pytest.raises(ValueError):
            _load(make_pkg(gate=False, threshold=None), ml_mode="active", experimental=True)

    @pytest.mark.parametrize("mode", ["off", "active"])
    def test_other_modes_rejected(self, mode):
        with pytest.raises(ValueError):
            _load(make_pkg(), ml_mode=mode, experimental=True)

    def test_engine_loader_never_returns_a_view(self, tmp_path):
        p = tmp_path / "m.json"
        p.write_text(json.dumps(make_pkg(gate=True, threshold=0.5)))
        try:
            v, err = load_engine_model(str(p), "active", NOW, experimental=True)
        except ValueError:
            return
        assert v is None and err                                   # yakalanip hata kodu olarak donerse de kabul


# ------------------------------------------------------------------------------------------------ G-T4
class TestG4HashAndExpiry:
    def test_tampered_model_body(self):
        pkg = make_pkg()
        pkg["model"]["intercept"] = 0.25
        with pytest.raises(PackageError, match="hash"):
            _load(pkg, experimental=True)

    def test_tampered_threshold(self):
        pkg = make_pkg(threshold=0.5)
        pkg["threshold"] = 0.1
        with pytest.raises(PackageError, match="hash"):
            _load(pkg, experimental=True)

    def test_bad_feature_list_hash(self):
        pkg = make_pkg()
        pkg["meta"]["feature_list_hash"] = "0" * 64
        with pytest.raises(PackageError, match="hash"):
            _load(pkg, experimental=True)

    def test_bad_model_hash(self):
        pkg = make_pkg()
        pkg["meta"]["model_hash"] = "0" * 64
        with pytest.raises(PackageError, match="hash"):
            _load(pkg, experimental=True)

    def test_expired_21_days(self):
        pkg = make_pkg(created=datetime(2026, 2, 1, tzinfo=UTC))
        with pytest.raises(PackageError, match="suresi"):
            _load(pkg, experimental=True)
        gated = make_pkg(gate=True, threshold=0.5, created=datetime(2026, 2, 1, tzinfo=UTC))
        with pytest.raises(PackageError, match="suresi"):
            _load(gated, experimental=False)

    def test_extended_expires_at_cannot_dodge(self):
        pkg = make_pkg(created=datetime(2026, 2, 1, tzinfo=UTC))
        pkg["meta"]["expires_at"] = datetime(2027, 1, 1, tzinfo=UTC).isoformat()
        with pytest.raises(PackageError, match="suresi"):
            _load(pkg, experimental=True)

    def test_not_expired_boundary_loads(self):
        v = _load(make_pkg(created=datetime(2026, 3, 1, tzinfo=UTC)), experimental=True, now=datetime(2026, 3, 21, tzinfo=UTC))
        assert v.experimental is True

    def test_engine_loader_returns_error_for_bad_packages(self, tmp_path):
        bad = make_pkg()
        bad["model"]["intercept"] = 1.0
        old = make_pkg(created=datetime(2026, 2, 1, tzinfo=UTC))
        for i, pkg in enumerate((bad, old)):
            p = tmp_path / f"m{i}.json"
            p.write_text(json.dumps(pkg))
            v, err = load_engine_model(str(p), "shadow", NOW, experimental=True)
            assert v is None and err


# ------------------------------------------------------------------------------------------------ G-T5
class TestG5Configs:
    """Spec duzeltme notu (18 Kasim 2026): engine.learner.json == {"bot":"learner"}; ML anahtarlari engine.paper.json'da (DD-12)."""

    def test_learner_config_unchanged(self):
        assert json.loads((CFG / "engine.learner.json").read_text()) == {"bot": "learner"}
        cfg = load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json")
        assert cfg.ml_mode == "off" and cfg.ml_experimental is False and cfg.ml_model_path is None

    def test_paper_ml_config(self, tmp_path):
        """DD-12 r03 paper katmani (eski anahtarlar gecici katmanda); dosya engine.paper-ml.json silindi."""
        assert not (CFG / "engine.paper-ml.json").exists()
        raw = json.loads(_r03_paper_overlay(tmp_path).read_text())
        assert raw["strategy"] == "price_action_lab_ml" and raw["ml_mode"] == "active" and raw["ml_experimental"] is True
        assert raw["ml_model_path"] == "models/ml1-r03.json" and raw["ml_features"] == "r03"
        cfg = load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json",
                                 overlay_path=_r03_paper_overlay(tmp_path))
        assert (cfg.mode, cfg.bot, cfg.strategy, cfg.ml_mode, cfg.ml_experimental, cfg.ml_features) == \
               ("paper", "learner", "price_action_lab_ml", "active", True, "r03")
        assert cfg.ml_model_path == "models/ml1-r03.json"

    def test_paper_ml_loads_via_cli_loader(self, tmp_path):
        import shutil
        from trader_engine.config import load_cli_config
        d = tmp_path / "config"                          # 19 Kasim: gercek paper dosyasi degil, eski anahtarli kopya
        shutil.copytree(CFG, d)
        (d / "engine.paper.json").write_text(json.dumps({**json.loads((CFG / "engine.paper.json").read_text()), **R03_PAPER_KEYS}))
        cfg = load_cli_config(d, "learner", "paper")
        assert cfg.mode == "paper" and cfg.ml_mode == "active" and cfg.ml_experimental is True and cfg.bot == "learner"

    def test_paper_ml_features_match_r03_package(self, tmp_path):
        key = json.loads(_r03_paper_overlay(tmp_path).read_text())["ml_features"]
        assert key in RECIPE_NAMES
        meta = json.loads(R03_SRC.read_text())["meta"]
        assert list(RECIPE_NAMES[key]) == meta["features"]

    @pytest.mark.parametrize("name", ["base", "learner", "testnet", "live"])
    def test_other_configs_have_no_experimental(self, name):
        assert "ml_experimental" not in json.loads((CFG / f"engine.{name}.json").read_text())

    def test_base_ml_off_and_twin_removed(self):
        assert json.loads((CFG / "engine.base.json").read_text())["ml_mode"] == "off"
        assert not (CFG / "engine.twin.json").exists()
        from trader_engine.config import load_cli_config
        with pytest.raises(ConfigError):
            load_cli_config(CFG, "twin")

    @pytest.mark.parametrize("env", ["testnet", "live"])
    def test_learner_testnet_live_stay_ml_free(self, env):
        cfg = load_engine_config(CFG / "engine.base.json", CFG / "engine.learner.json", overlay_path=CFG / f"engine.{env}.json")
        # 23.11 kullanici karari: canli = kagit (canlida ML aktif; deneysel paket/model yolu yine yok)
        assert cfg.mode == env and cfg.ml_mode == ("active" if env == "live" else "off")
        assert cfg.ml_experimental is False and cfg.ml_model_path is None
        with pytest.raises(ConfigError, match="ml_experimental"):       # paper katmani testnet/live ustune bindirilemez
            _stack(env)


def _r03_paper_overlay(tmp_path, name="paper_r03.json"):
    """19 Kasim: r03 kagit katmani kaldirildi; eski paper ML anahtarlari gecici dosyada yeniden kurulur."""
    raw = json.loads((CFG / "engine.paper.json").read_text())
    raw.update(R03_PAPER_KEYS)
    p = tmp_path / name
    p.write_text(json.dumps(raw))
    return p


def _stack(env):
    import tempfile
    d = Path(tempfile.mkdtemp())
    raw = json.loads((CFG / "engine.base.json").read_text())
    for n in ("learner", env):
        raw.update(json.loads((CFG / f"engine.{n}.json").read_text()))
    paper = json.loads((CFG / "engine.paper.json").read_text())             # strategy paper'dan; ML anahtarlari eski r03 seti
    raw.update({"strategy": paper["strategy"], **R03_PAPER_KEYS})          # ML anahtarlari testnet/live uzerine binsin
    (d / "x.json").write_text(json.dumps(raw))
    return load_engine_config(d / "x.json")


# ------------------------------------------------------------------------------------------------ G-T6
class TestG6ModelCopy:
    def test_model_copy_is_byte_identical(self):
        assert R03_DST.is_file(), "models/ml1-r03.json yok"
        assert R03_DST.read_bytes() == R03_SRC.read_bytes()

    def test_model_copy_loads_experimental_only(self):
        kw = dict(expected_features=RECIPE_NAMES["r03"], ml_mode="shadow", now=datetime(2026, 11, 20, tzinfo=UTC))
        assert load_model_view(R03_DST, experimental=True, **kw).experimental is True
        with pytest.raises(PackageError):
            load_model_view(R03_DST, **kw)


# ------------------------------------------------------------------------------------------------ G-5 tarafsizlik
def _helpers():
    """Mevcut ml_filter testinin gercek-veri yardimcilarini yeniden kullanir (tests/ paket degil: yoldan yukle)."""
    name = "_ml_filter_helpers_for_golge"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("test_engine_ml_filter.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_H = _helpers()


@pytest.mark.skipif(not _H.DATA.exists(), reason="var/history yok")
class TestNeutrality:
    @pytest.fixture(scope="class")
    @classmethod
    def runs(cls, tmp_path_factory):
        h = _H
        orig = h.apply_overrides

        def _ao(cfg, **kw):
            # learner yapilandirmasi artik experimental=true (paper+shadow); geri test kipine gecerken G-1 kilidi icin kapat
            if kw.get("mode") == "backtest":
                kw = {"ml_experimental": False, "ml_mode": "off", **kw}
            return orig(cfg, **kw)

        h.apply_overrides = _ao
        try:
            v1 = h._run(tmp_path_factory.mktemp("g_v1"), "price_action_v1", end=h.END_SHORT)
            view = _load(make_pkg(gate=False, threshold=None, intercept=-1.0, coef_atr=1.0), experimental=True)
            assert view.experimental is True
            exp = h._run(tmp_path_factory.mktemp("g_exp"), "price_action_v1_ml", end=h.END_SHORT, ml_mode="shadow", model=view)
        finally:
            h.apply_overrides = orig
        return v1, exp

    def test_experimental_shadow_decisions_equal_v1b(self, runs):
        v1, exp = runs
        d1, t1, _ = _H._rows(v1[0])
        de, te, raw = _H._rows(exp[0])
        assert len(d1) >= 5 and t1
        assert d1 == de and t1 == te
        entered = [r for r in raw if r["final_action"] == "entered"]
        assert entered and all(r["ml_score"] is not None and 0 <= r["ml_score"] <= 1 for r in entered)
        assert not any(r["skip_reason"] == "ml_filter" for r in raw)     # hicbir aday elenmez


def test_experimental_marker_in_load_log(tmp_path, caplog):
    """Belirtim G-2: log satirlarinda `ml_exp=1` gorunur (defter bu etiketi saklamaz: gerekce satiri defterde yok)."""
    import logging
    p = tmp_path / "m.json"
    p.write_text(json.dumps(make_pkg(gate=False, threshold=None)))
    with caplog.at_level(logging.INFO):
        v, err = load_engine_model(str(p), "shadow", NOW, experimental=True)
    assert v is not None and any("ml_exp=1" in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.INFO):
        load_engine_model(str(p), "shadow", NOW)
    assert not any("ml_exp=1" in r.getMessage() for r in caplog.records)
