"""Boyut frenleri 3 katman (25.11 sadelestirme 3/4): islem basi risk, gunluk zarar siniri, hesap geneli acik pozisyon/risk
(max_positions + max_open_risk + max_same_dir_risk). Korelasyon grubu, kayip freni, toplam buyukluk tavani, uzun donem yon filtresi ve
kume tavanlari KALDIRILDI; bu dosya kalan ayni yon riski ve kaldirilanlarin gercekten gitmis oldugunu denetler."""
from __future__ import annotations

import dataclasses
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from trader_core import ledger as L  # noqa: E402
from trader_core import risk as K  # noqa: E402
from trader_engine.clock import SimClock  # noqa: E402
from trader_engine.config import ClusterSpec, ConfigError, load_cli_config  # noqa: E402
from trader_engine.gates import EntryGate, NoVeto  # noqa: E402
from trader_engine.killswitch import Killswitch  # noqa: E402
from trader_engine.state import StateStore  # noqa: E402
from trader_engine.strategy_runner import SignalFrame  # noqa: E402
from trader_engine.types import SymbolRules  # noqa: E402

from test_engine_05_impl_smoke import T0, _params, _row  # noqa: E402

UTC = timezone.utc
CONFIG = ROOT / "config"
PAPER = load_cli_config(CONFIG, "learner", "paper")
LIVE = load_cli_config(CONFIG, "learner", "live")
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "DOGE/USDT", "ADA/USDT", "TRX/USDT"]


def _j(name):
    return json.loads((CONFIG / name).read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ yapilandirma
KALDIRILAN = ("korelasyon", "kayip_freni", "toplam_buyukluk_kat", "uzun_yon")


def test_yapilandirma_kalan_esikler_paper_ve_live():
    for name, cfg in (("engine.paper.json", PAPER), ("engine.live.json", LIVE)):
        raw = _j(name)
        assert raw["risk"]["max_same_dir_risk"] == 0.06 and "leverage" not in raw
        assert raw["risk"]["max_open_risk"] == 0.12 and raw["risk"]["daily_max_loss"] == 0.08 and raw["max_positions"] == 14
        assert cfg.risk_config.max_same_dir_risk == 0.06
        assert not set(KALDIRILAN) & set(raw)
        assert all(set(c) == {"pairs"} for c in raw["clusters"].values())
        assert not any(hasattr(cfg, k) for k in KALDIRILAN)
    # tavanlar yeni degerden gevsek (daha dusuk deger izinli)
    assert K.PAPER_LIMITS["max_same_dir_risk"] >= 0.06 and K.LIVE_LIMITS["max_same_dir_risk"] >= 0.06


def test_kaldirilan_anahtarlar_sunucu_kaplamasinda_atilir_ve_bot_acilir(tmp_path, caplog):
    """Sunucuda kalmis eski anahtarlar (korelasyon, kayip_freni, ..., kume max_positions) uyari ile dusurulur; yapilandirma yuklenir."""
    from trader_engine.config import load_engine_config
    ov = tmp_path / "ov.json"
    raw = _j("engine.paper.json")
    raw["korelasyon"] = {"esik": 0.7, "pencere_gun": 30, "yon_basina_max": 4}
    raw["kayip_freni"] = {"ardisik": 5, "gunluk_oran": 0.04, "carpan": 0.5}
    raw["toplam_buyukluk_kat"] = 3
    raw["uzun_yon"] = {"ema": 50, "egim_gun": 10, "min_gun": 60}
    raw["clusters"]["metal"]["max_positions"] = 3
    ov.write_text(json.dumps(raw), encoding="utf-8")
    with caplog.at_level("WARNING", logger="engine.config"):
        cfg = load_engine_config(CONFIG / "engine.base.json", CONFIG / "engine.learner.json", overlay_path=ov)
    assert not any(hasattr(cfg, k) for k in KALDIRILAN)
    assert cfg.clusters["metal"].pairs == tuple(raw["clusters"]["metal"]["pairs"])
    assert sum("kaldirilan yapilandirma anahtari" in r.message for r in caplog.records) >= 5


# ------------------------------------------------------------------------------------------------ kapi donanimi
def _env(tmp_path, cfg, *, equity=1000.0, **over):
    cfg = dataclasses.replace(cfg, **over)
    clock = SimClock(T0 + timedelta(seconds=5))
    led = L.open_ledger(str(tmp_path / "l.sqlite"), "learner", create=True, clock=clock.now)
    led.init_params(_params(), reason="strategy:price_action_v1@1b.0")
    state = StateStore(":memory:", bot="learner")
    with state.tx():
        state.kv_set(f"day_start:{T0:%Y-%m-%d}", 1000.0)
    held: list = []
    state.open_positions = lambda: list(held)                                    # type: ignore[method-assign]
    acct = SimpleNamespace(equity=equity, wallet=equity)
    broker = SimpleNamespace(account=lambda: acct)
    rules = lambda p: SymbolRules(p, p.replace("/", ""), 0.001, 0.001, 0.001, 1e9, 5.0)  # noqa: E731
    g = EntryGate(cfg, led, state, Killswitch(str(tmp_path / "KILL"), clock), NoVeto(), clock, broker, rules)
    return SimpleNamespace(g=g, held=held, led=led, state=state, acct=acct, clock=clock, cfg=cfg)


@pytest.fixture
def mk(tmp_path):
    made = []

    def f(cfg=PAPER, **kw):
        d = tmp_path / f"e{len(made)}"
        d.mkdir()
        e = _env(d, cfg, **kw)
        made.append(e)
        return e
    yield f
    for e in made:
        e.state.close()
        e.led.close()


# yalniz ilgili kuralin denendigi yalin yapilandirma: baska tavan (kume/hesap) araya girmez
BOS = dict(clusters={}, max_positions=None, etiket_kurallari={}, kume_risk={})


def _go(e, pair="BTC/USDT", side="long", D=T0):
    stop = 90.0 if side == "long" else 110.0
    fr = SignalFrame(pair=pair, status="ok", detail=None, last=_row(pair=pair, side=side, planned_stop=stop), table=None,
                     trigger_bar=(110.0, 99.0, 5.0))
    return e.g.decide(fr, D, e.g.pre(D, "1h", True, "1h"), 1)


def _ac(e, out, pair, side="long"):
    """Girilen pozisyonu (gercek boyut) acik listeye ekler."""
    s = out.size
    e.held.append(SimpleNamespace(pair=pair, side=side, risk_amount=s.risk_amount, margin=s.margin, qty=s.qty,
                                  entry_price=100.0, leverage=out.leverage))


# ------------------------------------------------------------------------------------------------ 1) ayni yon 0.06
@pytest.mark.parametrize("cfg", [PAPER, LIVE], ids=["paper", "live"])
def test_ayni_yon_risk_siniri_006_gercek_risk_matematigi(mk, cfg):
    e = mk(cfg, **BOS)
    sonuc = []
    for i, p in enumerate(PAIRS[:7]):
        o = _go(e, p)
        sonuc.append(o)
        if o.action == "enter":
            _ac(e, o, p)
    assert all(o.action == "enter" for o in sonuc[:5])                           # 5. izinli (5 x %1 = %5 <= %6)
    toplam = sum(p.risk_amount for p in e.held)
    assert toplam <= 0.06 * 1000.0 + 1e-9                                        # sinir asla asilmaz
    assert sonuc[6].action == "skip" and sonuc[6].event.skip_reason == "risk_denied"   # 7. engellenir
    assert sonuc[6].event.risk_reason.startswith("aynı yön (long) risk sınırı")
    # ters yon ayri sayilir
    assert _go(e, "ADA/USDT", "short").action == "enter"




# ------------------------------------------------------------------------------------------------ kaldirilan frenler gitmis
def test_kaldirilan_frenler_kodda_yok():
    src = ROOT / "src"
    for f in ("trader_core/kayip_freni.py", "trader_engine/korelasyon_grubu.py", "trader_engine/uzun_yon.py"):
        assert not (src / f).exists()
    gates = (src / "trader_engine" / "gates.py").read_text(encoding="utf-8")
    for z in ("kayip_freni", "korelasyon", "toplam_buyukluk", "uzun_yon", "cluster_cap", "check_entry_scaled"):
        assert z not in gates


def test_gate_uc_katman_kalir(mk):
    """Hesap tavani (max_positions) ve risk sinirlari (K.check_entry) yerinde; kayip serisi/kume doluluk/yon korelasyonu giris engellemez."""
    e = mk(PAPER, **{**BOS, "max_positions": 2})
    o1 = _go(e, "BTC/USDT")
    assert o1.action == "enter"
    _ac(e, o1, "BTC/USDT")
    o2 = _go(e, "ETH/USDT")
    assert o2.action == "enter"
    _ac(e, o2, "ETH/USDT")
    o3 = _go(e, "SOL/USDT")
    assert o3.action == "skip" and o3.event.skip_reason == "max_positions"
