"""ML1 maliyet modeli: motorun kagit maliyetinin (tek kaynak: config) izole cikis simulatoru icin ince katmani.

Kaynaklar (motorla AYNI):
  * `config/engine.base.json` `cost` -> `trader_engine.config.CostModel` (`_build_cost`): taker ucreti (taraf basina),
    giris/cikis/stop kaymasi (bps). Varsayilan: 5 bps ucret, 2/2/5 bps kayma.
  * `config/engine.paper.json` `cost_overrides[cift][seans]` kayma ezmeleri (hisse/emtia perp'leri). Seans
    `arm_time.session_tag(varlik_sinifi, dolum_mumu_acilisi)`; sinif kume adlarindan (`arm_guard.asset_class` ile ayni kural:
    `hisse` kumesi -> hisse, `metal`/`enerji_sanayi` -> emtia, aksi kripto). Kayma DOLUM ANINA gore secilir (giris ve cikis
    farkli seansta olabilir): motordaki `session_cost` ile ayni.
  * R birimi: `risk.loss_at_stop` (ledger `planned_risk` = `size.risk_amount`; `r_multiple = realized / planned_risk`).
    Birim adet icin R_unit = |e-s| + (e+s)*(fee_rate+slippage_rate); kilitli risk yapilandirmasinda 0,0005+0,0005 = 0,001
    (taker ucreti/kayma `cost`tan DEGIL, `risk.LOCKED_CFG`ten: motorun planlanan riski boyle hesaplar).

`trader_ml/config.py`de maliyet sabiti yoktur; bu modul yapilandirma dosyalarini okur.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from trader_core import risk as _risk
from trader_core.arm_time import CLASS_COMMODITY, CLASS_CRYPTO, CLASS_EQUITY, session_tag
from trader_engine.arm_guard import COMMODITY_CLUSTERS, EQUITY_CLUSTER
from trader_engine.config import CostModel, _build_cost, _build_cost_overrides

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"     # trader/config


@dataclass(frozen=True)
class Slips:
    """Tek dolum icin kayma (bps): giris, cikis (piyasa + hedef), stop."""
    entry_bps: float
    exit_bps: float
    stop_bps: float


@dataclass(frozen=True)
class CostConfig:
    """Yuklenmis maliyet yapilandirmasi (degismez)."""
    taker_fee: float
    base: Slips
    overrides: Mapping[str, Mapping[str, Slips]] = field(default_factory=dict)     # cift -> seans -> Slips (yalniz ezilen alanlar dolu)
    classes: Mapping[str, str] = field(default_factory=dict)                       # cift -> varlik sinifi (yoksa kripto)
    risk_cost_rate: float = _risk.LOCKED_CFG.fee_rate + _risk.LOCKED_CFG.slippage_rate

    def slips(self, pair: str | None, ts_ms: int) -> Slips:
        """`ts_ms`: dolum mumunun acilisi (epoch ms). Ezme yoksa temel kayma (hizli yol: kripto)."""
        ov = self.overrides.get(pair) if pair else None
        if not ov:
            return self.base
        tag = session_tag(self.classes.get(pair, CLASS_CRYPTO), datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc))
        s = ov.get(tag)
        return s if s is not None else self.base

    def r_unit(self, entry_ref: float, stop: float) -> float:
        """Birim adet icin planlanan risk (= ledger `planned_risk` / adet). `risk.loss_at_stop(1, e, s, cfg)` ile ayni formul."""
        return abs(entry_ref - stop) + (entry_ref + stop) * self.risk_cost_rate


def _asset_classes(clusters: Mapping | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, spec in (clusters or {}).items():
        pairs = spec.get("pairs", ()) if isinstance(spec, Mapping) else ()
        cls = CLASS_EQUITY if name == EQUITY_CLUSTER else (CLASS_COMMODITY if name in COMMODITY_CLUSTERS else None)
        if cls is None:
            continue
        for p in pairs:
            out.setdefault(p, cls)           # arm_guard.asset_class: ilk eslesen kume kazanir (hisse/emtia kumeleri ayri cift kumeleri)
    return out


def load_cost_config(config_dir: str | Path | None = None, bot_file: str | None = "engine.paper.json") -> CostConfig:
    """`engine.base.json` + (varsa) `bot_file` katmani. `bot_file=None` -> yalniz taban (cost_overrides yok)."""
    d = Path(config_dir) if config_dir is not None else CONFIG_DIR
    base = json.loads((d / "engine.base.json").read_text(encoding="utf-8"))
    cm: CostModel = _build_cost(base.get("cost", {}))
    over: dict[str, dict[str, Slips]] = {}
    classes: dict[str, str] = {}
    if bot_file:
        bot = json.loads((d / bot_file).read_text(encoding="utf-8"))
        if isinstance(bot.get("cost"), Mapping):
            cm = _build_cost({**base.get("cost", {}), **bot["cost"]})
        pairs = tuple(bot.get("pairs") or ())
        raw = _build_cost_overrides(bot.get("cost_overrides") or {}, pairs)
        for pair, sess in raw.items():
            over[pair] = {tag: Slips(float(s.get("slip_entry_bps", cm.slip_entry_bps)),
                                     float(s.get("slip_exit_bps", cm.slip_exit_bps)),
                                     float(s.get("slip_stop_bps", cm.slip_stop_bps))) for tag, s in sess.items()}
        classes = _asset_classes(bot.get("clusters"))
    return CostConfig(taker_fee=cm.taker_fee, base=Slips(cm.slip_entry_bps, cm.slip_exit_bps, cm.slip_stop_bps),
                      overrides=over, classes=classes)


# ---------------------------------------------------------------------------------------------- fiyat yardimcilari
def slipped(price: float, order_side: str, bps: float) -> float:
    """PaperBroker._slipped (tick yuvarlamasi OLMADAN): alis fiyati arttirir, satis azaltir."""
    f = bps / 10000.0
    return price * (1.0 + f) if order_side == "buy" else price * (1.0 - f)


def entry_fill(side: str, open_px: float, slip_bps: float) -> float:
    """Giris dolumu: long alir, short satar."""
    return slipped(open_px, "buy" if side == "long" else "sell", slip_bps)


def exit_fill(side: str, base_px: float, slip_bps: float) -> float:
    """Cikis dolumu (piyasa/hedef/stop): long satar, short alir."""
    return slipped(base_px, "sell" if side == "long" else "buy", slip_bps)


def fee(qty: float, price: float, taker_fee: float) -> float:
    """Dolum ucreti (para): adet x fiyat x taker."""
    return qty * price * taker_fee
