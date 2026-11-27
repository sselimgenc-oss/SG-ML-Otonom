"""Motor yapilandirmasi (02 §8). Risk kaynagi trader_core.risk.LOCKED_CFG; tek ayar `target_trade_risk` yalniz
LOCKED_CFG'den SIKI olabilir (gevsek/gecersiz => ConfigError, fail-closed)."""
from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from trader_core import etiket_kurallari as _EK
from trader_core import exit_modes as _xm
from trader_core.config_loader import deep_merge
from trader_core.risk import LOCKED_CFG, PAPER_KEYS, RiskConfig, live_config, paper_config, tightened

from .bars import GIRIS_TFS
from .errors import ConfigError
from .types import canon_pair

SCHEMA = "engine/1"
TARGET_MODES = ("bar_close", "resting")   # 24.11: "resting" = hedef bekleyen emir; "bar_close" = eski (kendi tf mum kapanisinda piyasa cikisi)


@dataclass(frozen=True)
class CostModel:
    fill_model: Literal["native", "legacy_compat"] = "native"
    taker_fee: float = 0.0005
    slip_entry_bps: float = 2.0
    slip_exit_bps: float = 2.0
    slip_stop_bps: float = 5.0
    trigger_source: Literal["mark", "last"] = "mark"
    granularity: Literal["1m", "15m"] = "1m"


# 5c (1L3A motor/canli/borsa/canli_ayar.py'dan uyarlandi): API anahtar carpisma denetimi (sha256 ozetleri; deger asla yazilmaz).
DIGER_ANAHTAR_ENV = "TRADER_DIGER_ANAHTAR_SHA256"    # "etiket:sha256hex,..." (baska hesap/bot anahtarlarinin ozetleri; deger degil)

_TAG_RE = re.compile(r"[a-z0-9-]{3,32}")
_KEY_VARS = ("BINANCE_API_KEY", "BINANCE_API_SECRET")


@dataclass(frozen=True)
class LiveSettings:
    """11 §3.1: testnet/live ayarlari. Taban adresleri burada YOK (binance_rest.py'de sabit)."""
    account_tag: str
    expected_wallet_max: float
    conditional_mode: Literal["algo", "classic"] = "algo"
    recv_window_ms: int = 5000
    poll_open_s: float = 5.0
    poll_flat_s: float = 30.0
    stop_deadline_s: float = 10.0
    entry_resolve_window_s: float = 60.0
    max_attempts: int = 1
    order_quote: bool = False       # WP-3 (defter-ek-alanlar 3.5): emir ani bookTicker sorgusu; varsayilan KAPALI


SHADOW_BLOCK_KEYS = ("regime", "r1_disabled", "same_bar_reentry", "tf_15m")

# DD-12 WP-01: YALNIZ mode="paper" ile verilebilen yeni anahtarlar (testnet/live/backtest'te varsayilan disi deger => ConfigError).
CONTRACT_TYPES = ("PERPETUAL", "TRADIFI_PERPETUAL")
SESSION_TAGS = ("open", "closed", "weekend")
_SLIP_KEYS = ("slip_entry_bps", "slip_exit_bps", "slip_stop_bps")
_CLUSTER_KEYS = {"pairs"}


@dataclass(frozen=True)
class ClusterSpec:
    """Kume (04 §4.1): yalniz varlik sinifi/seans/maliyet siniflamasi; uyeler `pairs` icinde olmali. 25.11 sadelestirme 3/4: kume basina
    acik pozisyon tavani kaldirildi (eski `max_positions` anahtari yapilandirmadan sessizce dusurulur)."""
    pairs: tuple[str, ...]


@dataclass(frozen=True)
class EngineConfig:
    schema: str
    mode: Literal["paper", "backtest", "testnet", "live"]
    bot: Literal["learner"]
    pairs: tuple[str, ...]
    wallet_start: float
    cost: CostModel
    target_mode: Literal["bar_close", "resting"]   # 24.11: "resting" = hedef bekleyen emir (borsada/kagit brokerde bar ici); "bar_close" eski yol
    record_filtered_candidates: bool
    stale_factor: float
    loop_sleep_s: float
    bar_wait_s: float
    minute_wait_s: float
    reconcile_open_s: float
    reconcile_flat_s: float
    var_dir: str
    market_db: str
    history_dir: str
    kill_file: str
    strategy: str = "price_action_v1"
    target_trade_risk: float = LOCKED_CFG.target_trade_risk
    pause_file: str = "shared/PAUSE"                          # 11 §3.1: gercek yol f"{pause_file}.{bot}"
    startup_wait_s: float = 600.0                             # paper acilis kapisi: kural+taze 1m veri icin azami bekleme
    leverage: int = LOCKED_CFG.min_leverage                   # 11 §3.1: [min_leverage, max_leverage]
    live: LiveSettings | None = None                          # 11 §3.1: testnet/live icin ZORUNLU, digerlerinde yasak
    ladder_follow: str | None = None                          # 12 §8.4: baska botun kademe gunlugunun yolu; yalniz paper
    shadow_blocks: tuple[str, ...] = ()                       # WP-3 5.1: golge karar satiri bloklari; bos = kapali
    mtm_marks: bool = True                                    # WP-3 6.2: oz varlik isaretleri (yalniz kayit)
    # --- DD-12 WP-01 (yalniz mode="paper"; varsayilanlar = onceki davranis) ---
    optional_pairs: tuple[str, ...] = ()                      # hisse/emtia: kural/veri gelmezse yalniz o cift bekler (pairs icinde)
    retired_pairs: tuple[str, ...] = ()                       # DD-12 WP-18: evrenden cikmis, acik pozisyonu tutulan ciftler (pairs icinde); yeni giris YOK
    max_positions: int | None = None                          # hesap geneli eszamanli pozisyon tavani (None = tavan yok)
    risk: Mapping[str, float] = dataclasses.field(default_factory=dict)          # 4.1 paper: target_trade_risk/max_open_risk/max_same_dir_risk/daily_max_loss
    clusters: Mapping[str, ClusterSpec] = dataclasses.field(default_factory=dict)  # 4.1 kume tavanlari (seanssiz), pairs sirasi korunur
    flat_bar_guard: bool = False                              # 4.2: son kapanmis tetik bari volume==0 / high==low => giris yok
    contract_types: tuple[str, ...] | None = None             # exchangeInfo contractType kabul listesi (03); None = PERPETUAL (yalniz paper verebilir)
    cost_overrides: Mapping[str, Mapping[str, Mapping[str, float]]] = dataclasses.field(default_factory=dict)  # cift -> seans -> kayma bps (4.3)
    # --- DD-12 WP-11 (yalniz mode="paper"; varsayilan bos = onceki davranis) ---
    arms: tuple[str, ...] = ()                                # bilesik strateji kurulumlari: arm_id ("T1@1h") listesi; bos = stratejinin varsayilani
    etiket_kurallari: Mapping[str, Any] = dataclasses.field(default_factory=dict)    # 20 Kasim: etiket kurallari (yalniz paper; bos = kapali; docs/etiket-kurallari-spec.md)
    # --- 23.11 kullanici karari: asama B esikleri (yalniz paper/live giris kapisi; bos/None = kapali) ---
    exit_modes: Mapping[str, Mapping] = dataclasses.field(default_factory=dict)      # cikis kipleri (basa-bas / kismi kar); anahtar default|KURULUM|arm_id; bos = kapali (docs/cikis-kipleri-spec.md)
    stop_tabani: Mapping[str, Any] = dataclasses.field(default_factory=dict)         # 27.11 sahip karari: stop tabani (tum kurulumlar; giris karari, boyuttan once); bos/aktif=false = eski davranis
    kume_risk: Mapping[str, Any] = dataclasses.field(default_factory=dict)           # 27.11 kume bazli ayni-yon risk tavani: {"aktif", "kumeler": {ad: {"ciftler", "ayni_yon"}}}; bos/aktif=false = eski davranis
    ml1: Mapping[str, Any] = dataclasses.field(default_factory=dict)                 # 25.11 ML1 (yalniz paper): {"aktif": bool, "paket_yolu"?, "ogrenme"?}; bos/aktif=false = kapali (onceki davranis)

    def _kume_tuple(self) -> tuple:
        kr = self.kume_risk
        if not kr or not kr.get("aktif"):
            return ()
        return tuple((n, tuple(k["ciftler"]), float(k["ayni_yon"])) for n, k in kr["kumeler"].items())

    @functools.cached_property
    def risk_config(self) -> RiskConfig:
        """Boyutlama/kapi icin tek RiskConfig (twin ve learner ayni degeri okur). Nesne tek kez kurulur (12 §8.3:
        K0'da `step_config` ayni nesneyi dondurur)."""
        if self.mode in ("paper", "live") and self.risk:      # 23.11 kullanici karari: canli = kagit (canli: LIVE_LIMITS)
            return build_paper_risk_config(self.target_trade_risk, self.risk, mode=self.mode, kume_risk=self._kume_tuple())
        return build_risk_config(self.target_trade_risk)

    def _bot_path(self, name: str) -> str:
        return f"{self.var_dir.rstrip('/')}/{self.bot}/{name}"

    def path(self, name: str) -> str:
        return self._bot_path(name)

    @property
    def ledger_path(self) -> str:
        return self._bot_path("ledger.sqlite")

    @property
    def state_path(self) -> str:
        return self._bot_path("state.sqlite")

    @property
    def status_path(self) -> str:
        return self._bot_path("status.json")


_COST_KEYS = {f.name for f in dataclasses.fields(CostModel)}
_TOP_KEYS = {f.name for f in dataclasses.fields(EngineConfig)}
_NUM = ("wallet_start", "stale_factor", "loop_sleep_s", "bar_wait_s", "minute_wait_s",
        "reconcile_open_s", "reconcile_flat_s")
_STR = ("var_dir", "market_db", "history_dir", "kill_file")
_OPTIONAL_KEYS = {"strategy", "target_trade_risk", "startup_wait_s", "pause_file",
                  "leverage", "live", "ladder_follow", "shadow_blocks", "mtm_marks",
                  "optional_pairs", "retired_pairs", "max_positions", "risk", "clusters", "flat_bar_guard", "contract_types",
                  "cost_overrides", "arms", "exit_modes", "etiket_kurallari",
                  "ml1", "stop_tabani", "kume_risk"}
_STOP_TABANI_KEYS = {"aktif": bool, "maliyet_payi": (int, float), "genislet_esik": (int, float), "atr_kat": (int, float)}
_ML1_KEYS = {"aktif": bool, "paket_yolu": str, "ogrenme": dict, "risk_bantlari": dict}                     # tohum paket YOK (sifirdan ogrenme)
_OGRENME_KEYS = {"aktif": bool, "kuru": bool, "yari_omur_gun": (int, float), "min_islem": int, "min_islem_tf": int, "esik": (int, float),
                  "sanal_aktif": bool, "sanal_agirlik": (int, float), "sinama_aralik": int}
_RISK_BANT_KEYS = {"aktif": bool, "bantlar": (list, tuple), "tavan": (int, float)}
_RISK_BANT_TAVAN_MAX = 0.02
_PAPER_ONLY_KEYS = ("optional_pairs", "max_positions", "risk", "clusters", "flat_bar_guard", "contract_types",
                    "cost_overrides", "arms")
# 25.11 sadelestirme: ML1 kapisi secer; boyut/giris frenleri 3 katmana indi (islem basi risk, gunluk zarar siniri, hesap geneli acik
# pozisyon/risk). Kol/aile/kume tavanlari, korelasyon grubu, kayip freni, toplam buyukluk tavani, uzun donem yon filtresi kaldirildi.
_KALDIRILAN_ANAHTARLAR = ("arm_max_positions", "arm_family_max_positions", "korelasyon", "kayip_freni", "toplam_buyukluk_kat", "uzun_yon")
_LIVE_KEYS = {f.name for f in dataclasses.fields(LiveSettings)}
_STRATEGY_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")


def _num(name: str, v: Any, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{name} sayi olmali: {v!r}")
    if not math.isfinite(v):
        raise ConfigError(f"{name} sonlu olmali: {v!r}")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ConfigError(f"{name} aralik disi [{lo}, {hi}]: {v!r}")
    return float(v)


def build_risk_config(target_trade_risk: Any) -> RiskConfig:
    """LOCKED_CFG'nin yalniz `target_trade_risk`i daha sikilastirilmis kopyasi. Gevsek (> kilitli hedef), <= 0,
    sonlu olmayan ya da sayi olmayan deger => ConfigError."""
    v = _num("target_trade_risk", target_trade_risk)
    try:
        return tightened(LOCKED_CFG, target_trade_risk=v)
    except ValueError as e:
        raise ConfigError(f"target_trade_risk: {e}") from e


def build_paper_risk_config(target_trade_risk: Any, risk: Mapping[str, Any], mode: str = "paper", kume_risk: tuple = ()) -> RiskConfig:
    """DD-12 §4.1 (mode="paper"; 23.11: canli da, LIVE_LIMITS): `risk` blogundaki anahtarlar PAPER_LIMITS icinde uygulanir. Ust sinirlari asan,
    bilinmeyen, sayi olmayan ya da `target_trade_risk` ile celisen deger => ConfigError (fail-closed)."""
    unknown = set(risk) - set(PAPER_KEYS)
    if unknown:
        raise ConfigError(f"risk bilinmeyen anahtar: {sorted(unknown)} (izinli: {PAPER_KEYS})")
    kw = {k: _num(f"risk.{k}", v) for k, v in risk.items()}
    ttr = _num("target_trade_risk", target_trade_risk)
    if "target_trade_risk" in kw and kw["target_trade_risk"] != ttr:
        raise ConfigError(f"risk.target_trade_risk ({kw['target_trade_risk']}) ile target_trade_risk ({ttr}) celisiyor")
    kw["target_trade_risk"] = ttr
    if kume_risk:
        kw["kume_risk"] = kume_risk
        for kn, _kp, kc in kume_risk:
            if kc > kw.get("max_same_dir_risk", LOCKED_CFG.max_same_dir_risk):
                raise ConfigError(f"kume_risk.{kn}.ayni_yon max_same_dir_risk degerini asamaz")
    try:
        return live_config(**kw) if mode == "live" else paper_config(**kw)
    except ValueError as e:
        raise ConfigError(f"risk: {e}") from e


def _choice(name: str, v: Any, allowed: tuple[str, ...]) -> str:
    if not isinstance(v, str) or v not in allowed:
        raise ConfigError(f"{name} gecersiz: {v!r} (izinli: {allowed})")
    return v


def _build_cost(raw: Any) -> CostModel:
    if not isinstance(raw, Mapping):
        raise ConfigError("cost sozluk olmali")
    unknown = set(raw) - _COST_KEYS
    if unknown:
        raise ConfigError(f"cost bilinmeyen anahtar: {sorted(unknown)}")
    d = CostModel()
    fm = _choice("cost.fill_model", raw.get("fill_model", d.fill_model), ("native", "legacy_compat"))
    ts = _choice("cost.trigger_source", raw.get("trigger_source", d.trigger_source), ("mark", "last"))
    gr = _choice("cost.granularity", raw.get("granularity", d.granularity), ("1m", "15m"))
    cm = CostModel(
        fill_model=fm,  # type: ignore[arg-type]
        taker_fee=_num("cost.taker_fee", raw.get("taker_fee", d.taker_fee), 0, 0.005),
        slip_entry_bps=_num("cost.slip_entry_bps", raw.get("slip_entry_bps", d.slip_entry_bps), 0, 100),
        slip_exit_bps=_num("cost.slip_exit_bps", raw.get("slip_exit_bps", d.slip_exit_bps), 0, 100),
        slip_stop_bps=_num("cost.slip_stop_bps", raw.get("slip_stop_bps", d.slip_stop_bps), 0, 100),
        trigger_source=ts,  # type: ignore[arg-type]
        granularity=gr,  # type: ignore[arg-type]
    )
    if fm == "legacy_compat" and (ts != "last" or gr != "15m"):
        raise ConfigError("legacy_compat: trigger_source=last ve granularity=15m zorunlu")
    if gr == "15m" and ts != "last":
        raise ConfigError("granularity=15m: trigger_source=last zorunlu")
    return cm


def _int(name: str, v: Any, lo: int, hi: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"{name} tam sayi olmali: {v!r}")
    if v < lo or v > hi:
        raise ConfigError(f"{name} aralik disi [{lo}, {hi}]: {v!r}")
    return v


def _bool(name: str, v: Any) -> bool:
    if not isinstance(v, bool):
        raise ConfigError(f"{name} bool olmali: {v!r}")
    return v


def _build_shadow_blocks(v: Any) -> tuple[str, ...]:
    if isinstance(v, (str, bytes)) or not isinstance(v, (list, tuple)):
        raise ConfigError(f"shadow_blocks liste olmali: {v!r}")
    for b in v:
        if not isinstance(b, str) or b not in SHADOW_BLOCK_KEYS:
            raise ConfigError(f"shadow_blocks gecersiz oge {b!r} (izinli: {SHADOW_BLOCK_KEYS})")
    if len(set(v)) != len(v):
        raise ConfigError("shadow_blocks yinelenen oge iceriyor")
    return tuple(v)


def _pair_subset(name: str, v: Any, pairs: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(v, (str, bytes)) or not isinstance(v, (list, tuple)):
        raise ConfigError(f"{name} liste olmali: {v!r}")
    try:
        out = tuple(canon_pair(p) for p in v)
    except (ValueError, TypeError, AttributeError) as e:
        raise ConfigError(f"{name}: {e}") from e
    if len(set(out)) != len(out):
        raise ConfigError(f"{name} yinelenen oge iceriyor")
    outside = [p for p in out if p not in pairs]
    if outside:
        raise ConfigError(f"{name} pairs disinda cift iceriyor: {outside}")
    return out


_ARM_ID_RE = re.compile(r"[A-Z][A-Z0-9]{1,7}(-[A-Z0-9]{2,10})?@(15m|1h|4h|1d)")   # 24.11 kullanici karari: formasyon kutuphanesi (MF1-YUTAN@1h)


def _build_arms(v: Any) -> tuple[str, ...]:
    """`arms`: arm_id listesi (["T1@1h", "R1@4h"]) ya da {kurulum: [zaman dilimleri]} sozlugu. Sira korunur; yinelenen yasak.
    Kurulumun var olup olmadigi strateji kurulurken (arms paketi) denetlenir."""
    if isinstance(v, Mapping):
        v = [f"{k}@{tf}" for k, tfs in v.items()
             for tf in (tfs if isinstance(tfs, (list, tuple)) else [tfs])]
    if isinstance(v, (str, bytes)) or not isinstance(v, (list, tuple)):
        raise ConfigError(f"arms liste ya da sozluk olmali: {v!r}")
    for a in v:
        if not isinstance(a, str) or not _ARM_ID_RE.fullmatch(a):
            raise ConfigError(f"arms gecersiz arm_id {a!r} (bicim <KURULUM>@<1h|4h|1d>)")
        if a.rsplit("@", 1)[1] not in GIRIS_TFS:
            raise ConfigError(f"arms: 15m giris kolu yok (sahip karari): {a!r}")
    if len(set(v)) != len(v):
        raise ConfigError("arms yinelenen oge iceriyor")
    return tuple(v)


def _build_kume_risk(v: Any, pairs: tuple[str, ...]) -> dict[str, Any]:
    """27.11 kume_risk: {"aktif": bool, "kumeler": {ad: {"ciftler": [...], "ayni_yon": 0<oran<=1}}}. Aktifse her cift tam bir kumede."""
    if not v:
        return {}
    if not isinstance(v, Mapping) or set(v) != {"aktif", "kumeler"} or not isinstance(v["aktif"], bool) or not isinstance(v["kumeler"], Mapping):
        raise ConfigError("kume_risk {aktif: bool, kumeler: {...}} olmali")
    out: dict[str, Any] = {}
    seen: set[str] = set()
    for name, spec in v["kumeler"].items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name):
            raise ConfigError(f"kume_risk kume adi gecersiz: {name!r}")
        if not isinstance(spec, Mapping) or set(spec) != {"ciftler", "ayni_yon"}:
            raise ConfigError(f"kume_risk.{name} tam olarak ['ayni_yon', 'ciftler'] icermeli")
        members = _pair_subset(f"kume_risk.{name}.ciftler", spec["ciftler"], pairs)
        if not members:
            raise ConfigError(f"kume_risk.{name}.ciftler bos olamaz")
        dup = seen & set(members)
        if dup:
            raise ConfigError(f"kume_risk: cift birden fazla kumede: {sorted(dup)}")
        seen |= set(members)
        cap = _num(f"kume_risk.{name}.ayni_yon", spec["ayni_yon"])
        if not 0 < cap <= 1:
            raise ConfigError(f"kume_risk.{name}.ayni_yon (0, 1] araliginda olmali")
        out[name] = {"ciftler": list(members), "ayni_yon": cap}
    if v["aktif"] and seen != set(pairs):
        raise ConfigError(f"kume_risk: kumede olmayan cift: {sorted(set(pairs) - seen)}")
    return {"aktif": v["aktif"], "kumeler": out}


def _build_clusters(v: Any, pairs: tuple[str, ...]) -> dict[str, ClusterSpec]:
    if not isinstance(v, Mapping):
        raise ConfigError("clusters sozluk olmali")
    out: dict[str, ClusterSpec] = {}
    for name, spec in v.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name):
            raise ConfigError(f"clusters kume adi gecersiz: {name!r}")
        if isinstance(spec, ClusterSpec):
            spec = {"pairs": list(spec.pairs)}
        if isinstance(spec, Mapping) and "max_positions" in spec:          # eski kume tavani anahtari: kaldirildi, yok sayilir (bot acilisi bozulmasin)
            spec = {k: x for k, x in spec.items() if k != "max_positions"}
        if not isinstance(spec, Mapping) or set(spec) != _CLUSTER_KEYS:
            raise ConfigError(f"clusters.{name} tam olarak {sorted(_CLUSTER_KEYS)} icermeli")
        members = _pair_subset(f"clusters.{name}.pairs", spec["pairs"], pairs)
        if not members:
            raise ConfigError(f"clusters.{name}.pairs bos olamaz")
        out[name] = ClusterSpec(pairs=members)
    return out


def _build_stop_tabani(v: Any) -> dict[str, Any]:
    """27.11 stop tabani blogu: {"aktif": bool, "maliyet_payi": (0,1] (gidis-donus maliyet <= stop mesafesinin bu payi), "genislet_esik": (0,1]
    (dogal mesafe >= esik x taban ise taban mesafesine GENISLET, altinda atla), "atr_kat": (0,5] (taban >= atr_kat x ATR)}. Bos/None = kapali
    (eski davranis). Eksik anahtar varsayilan alir (0.20 / 0.7 / 0.5); 'aktif' zorunlu."""
    if v in (None, {}):
        return {}
    if not isinstance(v, Mapping) or not set(v) <= set(_STOP_TABANI_KEYS) or "aktif" not in v:
        raise ConfigError(f"stop_tabani {sorted(_STOP_TABANI_KEYS)} anahtarlarindan olusmali ('aktif' zorunlu): {v!r}")
    out: dict[str, Any] = {"maliyet_payi": 0.20, "genislet_esik": 0.7, "atr_kat": 0.5}
    for k, x in v.items():
        if k == "aktif":
            if not isinstance(x, bool):
                raise ConfigError(f"stop_tabani.aktif bool olmali: {x!r}")
            out[k] = x
            continue
        hi = 5.0 if k == "atr_kat" else 1.0
        out[k] = _num(f"stop_tabani.{k}", x, 0.0, hi)
        if out[k] <= 0.0:
            raise ConfigError(f"stop_tabani.{k} > 0 olmali: {x!r}")
    return out


def _build_ml1(v: Any) -> dict[str, Any]:
    """25.11 ML1 blogu: {"aktif": bool, "paket_yolu"?: str, "ogrenme"?: {aktif, kuru, yari_omur_gun, min_islem >= 1, min_islem_tf >= 0, esik (0,1)}}; bos/None = kapali. Bilinmeyen anahtar/tur = ConfigError."""
    if v in (None, {}):
        return {}
    if not isinstance(v, Mapping) or not set(v) <= set(_ML1_KEYS) or "aktif" not in v:
        raise ConfigError(f"ml1 {sorted(_ML1_KEYS)} anahtarlarindan olusmali ('aktif' zorunlu): {v!r}")
    for k, x in v.items():
        if k == "ogrenme":
            if not isinstance(x, Mapping) or not set(x) <= set(_OGRENME_KEYS):
                raise ConfigError(f"ml1.ogrenme {sorted(_OGRENME_KEYS)} anahtarlarindan olusmali: {x!r}")
            for kk, xx in x.items():
                if isinstance(xx, bool) != (kk in ("aktif", "kuru", "sanal_aktif")) or not isinstance(xx, _OGRENME_KEYS[kk]):
                    raise ConfigError(f"ml1.ogrenme.{kk} gecersiz: {xx!r}")
                if (kk == "yari_omur_gun" and xx <= 0) or (kk == "min_islem" and xx < 1) or (kk == "min_islem_tf" and xx < 0) \
                        or (kk == "esik" and not 0.0 < xx < 1.0) or (kk == "sanal_agirlik" and not (0.0 <= xx <= 1.0 and math.isfinite(xx))) \
                        or (kk == "sinama_aralik" and xx < 1):
                    raise ConfigError(f"ml1.ogrenme.{kk} aralik disi: {xx!r}")
            continue
        if k == "risk_bantlari":
            _build_risk_bantlari(x)
            continue
        if not isinstance(x, _ML1_KEYS[k]) or (k != "aktif" and not x.strip()):
            raise ConfigError(f"ml1.{k} turu gecersiz: {x!r}")
    return dict(v)


def _build_risk_bantlari(x: Any) -> None:
    """26.11 ML1 guven bandi riski: {"aktif": bool, "bantlar": [[esik, risk], ...], "tavan": float}. Esikler (0,1) ve kesin artan,
    riskler > 0 ve <= tavan, tavan <= 0.02 (max_trade_risk). Gecersiz = ConfigError."""
    if not isinstance(x, Mapping) or not set(x) <= set(_RISK_BANT_KEYS) or not {"aktif", "bantlar", "tavan"} <= set(x):
        raise ConfigError(f"ml1.risk_bantlari {sorted(_RISK_BANT_KEYS)} anahtarlarindan olusmali: {x!r}")
    if not isinstance(x["aktif"], bool):
        raise ConfigError(f"ml1.risk_bantlari.aktif bool olmali: {x['aktif']!r}")
    tavan = x["tavan"]
    if isinstance(tavan, bool) or not isinstance(tavan, (int, float)) or not 0 < tavan <= _RISK_BANT_TAVAN_MAX:
        raise ConfigError(f"ml1.risk_bantlari.tavan (0, {_RISK_BANT_TAVAN_MAX}] icinde olmali: {tavan!r}")
    b = x["bantlar"]
    if not isinstance(b, (list, tuple)) or not b:
        raise ConfigError("ml1.risk_bantlari.bantlar bos olmayan liste olmali")
    onceki = None
    for it in b:
        if not isinstance(it, (list, tuple)) or len(it) != 2 or any(isinstance(z, bool) or not isinstance(z, (int, float)) for z in it):
            raise ConfigError(f"ml1.risk_bantlari.bantlar ogesi [esik, risk] olmali: {it!r}")
        e, r = float(it[0]), float(it[1])
        if not (math.isfinite(e) and math.isfinite(r)) or not 0.0 < e < 1.0:
            raise ConfigError(f"ml1.risk_bantlari esik (0,1) icinde olmali: {it!r}")
        if onceki is not None and e <= onceki:
            raise ConfigError("ml1.risk_bantlari esikleri kesin artan siralanmali")
        if not 0.0 < r <= float(tavan):
            raise ConfigError(f"ml1.risk_bantlari risk (0, tavan] icinde olmali: {it!r}")
        onceki = e


def _build_cost_overrides(v: Any, pairs: tuple[str, ...]) -> dict[str, dict[str, dict[str, float]]]:
    if not isinstance(v, Mapping):
        raise ConfigError("cost_overrides sozluk olmali")
    out: dict[str, dict[str, dict[str, float]]] = {}
    for pair, sess in v.items():
        try:
            cp = canon_pair(pair)
        except (ValueError, TypeError, AttributeError) as e:
            raise ConfigError(f"cost_overrides: {e}") from e
        if cp not in pairs:
            raise ConfigError(f"cost_overrides pairs disinda cift: {cp}")
        if cp in out:
            raise ConfigError(f"cost_overrides yinelenen cift: {cp}")
        if not isinstance(sess, Mapping):
            raise ConfigError(f"cost_overrides.{cp} sozluk olmali")
        d: dict[str, dict[str, float]] = {}
        for tag, slips in sess.items():
            if tag not in SESSION_TAGS:
                raise ConfigError(f"cost_overrides.{cp} seans gecersiz: {tag!r} (izinli: {SESSION_TAGS})")
            if not isinstance(slips, Mapping) or not slips or set(slips) - set(_SLIP_KEYS):
                raise ConfigError(f"cost_overrides.{cp}.{tag} anahtarlari {_SLIP_KEYS} alt kumesi olmali")
            d[tag] = {k: _num(f"cost_overrides.{cp}.{tag}.{k}", x, 0, 100) for k, x in slips.items()}
        out[cp] = d
    return out


def _build_live(raw: Any) -> LiveSettings:
    if isinstance(raw, LiveSettings):
        raw = dataclasses.asdict(raw)
    if not isinstance(raw, Mapping):
        raise ConfigError("live sozluk olmali")
    unknown = set(raw) - _LIVE_KEYS
    if unknown:
        raise ConfigError(f"live bilinmeyen anahtar: {sorted(unknown)}")
    for req in ("account_tag", "expected_wallet_max"):
        if req not in raw:
            raise ConfigError(f"live eksik anahtar: {req}")
    d = LiveSettings(account_tag="x", expected_wallet_max=1.0)
    tag = raw["account_tag"]
    if not isinstance(tag, str) or not _TAG_RE.fullmatch(tag):
        raise ConfigError("live.account_tag ^[a-z0-9-]{3,32}$ olmali")
    wmax = _num("live.expected_wallet_max", raw["expected_wallet_max"])
    if wmax <= 0:
        raise ConfigError("live.expected_wallet_max > 0 olmali")
    cm = _choice("live.conditional_mode", raw.get("conditional_mode", d.conditional_mode), ("algo", "classic"))
    return LiveSettings(
        account_tag=tag, expected_wallet_max=wmax, conditional_mode=cm,  # type: ignore[arg-type]
        recv_window_ms=_int("live.recv_window_ms", raw.get("recv_window_ms", d.recv_window_ms), 1000, 10000),
        poll_open_s=_num("live.poll_open_s", raw.get("poll_open_s", d.poll_open_s), 1, 15),
        poll_flat_s=_num("live.poll_flat_s", raw.get("poll_flat_s", d.poll_flat_s), 5, 120),
        stop_deadline_s=_num("live.stop_deadline_s", raw.get("stop_deadline_s", d.stop_deadline_s), 5, 15),
        entry_resolve_window_s=_num("live.entry_resolve_window_s",
                                    raw.get("entry_resolve_window_s", d.entry_resolve_window_s), 0, 3600),
        max_attempts=_int("live.max_attempts", raw.get("max_attempts", d.max_attempts), 1, 1),   # 25.11: motor canlida 1'e sabit (DD-2 D10); 2 artik reddedilir
        order_quote=_bool("live.order_quote", raw.get("order_quote", d.order_quote)))


def anahtar_ozeti(deger: str) -> str:
    """sha256 hex ozeti (anahtar karsilastirmasi icin; degerin kendisi asla loglanmaz/yazilmaz)."""
    return hashlib.sha256(deger.encode("utf-8")).hexdigest()


def _diger_ozetler(env: Mapping[str, str]) -> dict[str, str]:
    """TRADER_DIGER_ANAHTAR_SHA256='etiket:hex,etiket2:hex' -> {hex: etiket}. Bozuk giris => ConfigError (fail-closed)."""
    ham = env.get(DIGER_ANAHTAR_ENV)
    if ham is None or not ham.strip():
        return {}
    out: dict[str, str] = {}
    for parca in ham.split(","):
        etiket, sep, hx = parca.strip().partition(":")
        hx = hx.strip().lower()
        if not sep or not etiket.strip() or not re.fullmatch(r"[0-9a-f]{64}", hx):
            raise ConfigError(f"{DIGER_ANAHTAR_ENV}: 'etiket:sha256hex' bicimi bozuk")
        out[hx] = etiket.strip()
    return out


def check_key_collision(key: str, secret: str, env: Mapping[str, str]) -> None:
    """5c: bu surecin anahtar/gizli degeri baska hesap/bot anahtarlariyla (testnet<->live<->diger botlar) CAKISAMAZ.
    Karsilastirma sha256 ozetleriyle; mesajda yalniz etiket vardir, anahtar degeri asla. Kume bos ise denetim yoktur (davranis degismez)."""
    diger = _diger_ozetler(env)
    for ad, v in (("BINANCE_API_KEY", key), ("BINANCE_API_SECRET", secret)):
        et = diger.get(anahtar_ozeti(v))
        if et is not None:
            raise ConfigError(f"key_collision: {ad} baska hesapla ({et}) ayni (hesap/anahtar paylasilamaz)")


def load_keys(env: Mapping[str, str]) -> tuple[str, str]:
    """11 §3.2: (BINANCE_API_KEY, BINANCE_API_SECRET). Eksik/bos/bosluklu/<32 karakter => ConfigError('keys_missing').
    Iletide yalniz degisken adi vardir, deger asla."""
    out = []
    for name in _KEY_VARS:
        v = env.get(name)
        if not isinstance(v, str) or len(v) < 32 or any(c.isspace() for c in v):
            raise ConfigError(f"keys_missing: {name}")
        out.append(v)
    check_key_collision(out[0], out[1], env)       # 5c: yalniz ozet karsilastirmasi; deger iletiye yazilmaz
    return out[0], out[1]


def check_live_confirm(cfg: "EngineConfig", env: Mapping[str, str] | None = None) -> None:
    """11 §3.1 cift onay: yalniz mode='live'. LIVE_CONFIRM != live.account_tag => ConfigError('live_confirm')."""
    if cfg.mode != "live":
        return
    env = os.environ if env is None else env
    got = env.get("LIVE_CONFIRM")
    if cfg.live is None or not isinstance(got, str) or got != cfg.live.account_tag:
        raise ConfigError("live_confirm")  # deger iletiye/gunluge yazilmaz


def _tail(path: str, n: int) -> tuple[str, ...]:
    parts = [c for c in os.path.normpath(path).split(os.sep) if c]
    return tuple(parts[-n:])


def check_shared_paths(mode: str, var_dir: str, kill_file: str, pause_file: str) -> None:
    """DD-8 (O8 §2.1): testnet/live, kagit botlarinin `var` dizinini ve paylasimli `shared/KILL`, `shared/PAUSE` dosyalarini
    kullanamaz (yanlis hesapla acilis / kagit bota KILL-PAUSE sizmasi). paper/backtest: uygulanmaz."""
    if mode not in ("testnet", "live"):
        return
    if _tail(var_dir, 1) == ("var",):
        raise ConfigError(f"var_dir kagit dizini ('var') olamaz (mode={mode}): {var_dir!r}")
    if _tail(kill_file, 2) == ("shared", "KILL"):
        raise ConfigError(f"kill_file kagit botlarinin dosyasi (shared/KILL) olamaz (mode={mode}): {kill_file!r}")
    if _tail(pause_file, 2) == ("shared", "PAUSE"):
        raise ConfigError(f"pause_file kagit botlarinin dosyasi (shared/PAUSE) olamaz (mode={mode}): {pause_file!r}")


def _validate(raw: Mapping[str, Any]) -> EngineConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError("yapilandirma sozluk olmali")
    unknown = set(raw) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"bilinmeyen anahtar: {sorted(unknown)}")
    missing = _TOP_KEYS - _OPTIONAL_KEYS - set(raw)
    if missing:
        raise ConfigError(f"eksik anahtar: {sorted(missing)}")
    if raw["schema"] != SCHEMA:
        raise ConfigError(f"schema {SCHEMA!r} olmali: {raw['schema']!r}")
    mode = raw["mode"]
    _choice("mode", mode, ("paper", "backtest", "testnet", "live"))
    bot = _choice("bot", raw["bot"], ("learner",))      # DD-12: ikiz kaldirildi; "twin" => ConfigError
    pairs_raw = raw["pairs"]
    if isinstance(pairs_raw, (str, bytes)) or not isinstance(pairs_raw, (list, tuple)) or not pairs_raw:
        raise ConfigError("pairs bos olmayan liste olmali")
    try:
        pairs = tuple(canon_pair(p) for p in pairs_raw)
    except ValueError as e:
        raise ConfigError(f"pairs: {e}") from e
    if len(set(pairs)) != len(pairs):
        raise ConfigError("pairs yinelenen oge iceriyor")
    nums = {n: _num(n, raw[n]) for n in _NUM}
    if nums["wallet_start"] <= 0:
        raise ConfigError("wallet_start > 0 olmali")
    if not 1.0 <= nums["stale_factor"] <= 3.0:
        raise ConfigError("stale_factor [1, 3] araliginda olmali")
    for n in _NUM[2:]:
        if nums[n] < 0:
            raise ConfigError(f"{n} >= 0 olmali")
    target_mode = _choice("target_mode", raw["target_mode"], TARGET_MODES)   # 24.11 kullanici karari: hedef bekleyen emir ("resting")
    if not isinstance(raw["record_filtered_candidates"], bool):
        raise ConfigError("record_filtered_candidates bool olmali")
    for n in _STR:
        if not isinstance(raw[n], str) or not raw[n]:
            raise ConfigError(f"{n} bos olmayan str olmali")
    strategy = raw.get("strategy", "price_action_v1")
    if not isinstance(strategy, str) or not _STRATEGY_RE.fullmatch(strategy):
        raise ConfigError(f"strategy gecersiz (^[a-z][a-z0-9_]{{0,39}}$): {strategy!r}")
    pause_file = raw.get("pause_file", "shared/PAUSE")
    if not isinstance(pause_file, str) or not pause_file:
        raise ConfigError("pause_file bos olmayan str olmali")
    startup_wait = _num("startup_wait_s", raw.get("startup_wait_s", 600.0), 0.0, 86_400.0)
    lev = _int("leverage", raw.get("leverage", LOCKED_CFG.min_leverage),
               LOCKED_CFG.min_leverage, LOCKED_CFG.max_leverage)
    ladder_follow = raw.get("ladder_follow")
    if ladder_follow is not None:
        if not isinstance(ladder_follow, str) or not ladder_follow:
            raise ConfigError("ladder_follow bos olmayan str ya da null olmali")
        if mode != "paper":
            raise ConfigError(f"ladder_follow yalniz mode='paper' ile verilebilir (mode={mode!r})")
    shadow_blocks = _build_shadow_blocks(raw.get("shadow_blocks", ()))
    mtm_marks = _bool("mtm_marks", raw.get("mtm_marks", True))
    # --- DD-12 WP-01 yeni anahtarlar: yalniz paper ---
    pairs_set = pairs
    optional_pairs = _pair_subset("optional_pairs", raw.get("optional_pairs", ()), pairs_set)
    retired_pairs = _pair_subset("retired_pairs", raw.get("retired_pairs", ()), pairs_set)
    max_positions = raw.get("max_positions")
    if max_positions is not None:
        max_positions = _int("max_positions", max_positions, 1, 1000)
    risk_raw = raw.get("risk", {})
    if not isinstance(risk_raw, Mapping):
        raise ConfigError("risk sozluk olmali")
    risk_raw = dict(risk_raw)
    flat_bar_guard = _bool("flat_bar_guard", raw.get("flat_bar_guard", False))
    ct_raw = raw.get("contract_types")
    contract_types = None
    if ct_raw is not None:
        if isinstance(ct_raw, (str, bytes)) or not isinstance(ct_raw, (list, tuple)) or not ct_raw:
            raise ConfigError(f"contract_types bos olmayan liste olmali: {ct_raw!r}")
        for c in ct_raw:
            if not isinstance(c, str) or c not in CONTRACT_TYPES:
                raise ConfigError(f"contract_types gecersiz oge {c!r} (izinli: {CONTRACT_TYPES})")
        if len(set(ct_raw)) != len(ct_raw):
            raise ConfigError("contract_types yinelenen oge iceriyor")
        contract_types = tuple(ct_raw)
    clusters = _build_clusters(raw.get("clusters", {}), pairs_set)
    kume_risk = _build_kume_risk(raw.get("kume_risk"), pairs_set)
    cost_overrides = _build_cost_overrides(raw.get("cost_overrides", {}), pairs_set)
    arms = _build_arms(raw.get("arms", ()))
    try:
        exit_modes = _xm.build_config(raw.get("exit_modes", {}))
    except _xm.ExitModeError as e:
        raise ConfigError(str(e)) from e
    etiket_raw = raw.get("etiket_kurallari")
    if etiket_raw and mode not in ("paper", "live"):          # 23.11 kullanici karari: canli = kagit
        raise ConfigError(f"etiket_kurallari yalniz mode='paper'|'live' ile verilebilir (mode={mode!r})")
    try:
        etiket_kurallari = _EK.build_config(etiket_raw)
    except _EK.EtiketConfigHatasi as e:
        raise ConfigError(str(e)) from e
    ml1 = _build_ml1(raw.get("ml1"))
    stop_tabani = _build_stop_tabani(raw.get("stop_tabani"))
    if mode not in ("paper", "backtest", "live") and exit_modes:   # 23.11 kullanici karari: canli = kagit (canli motor da uygular)
        raise ConfigError(f"exit_modes yalniz mode='paper'/'backtest'/'live' ile verilebilir (mode={mode!r})")
    if mode not in ("paper", "live"):                         # 23.11 kullanici karari: canli = kagit
        given = {"optional_pairs": optional_pairs, "max_positions": max_positions, "risk": risk_raw,
                 "clusters": clusters, "flat_bar_guard": flat_bar_guard, "cost_overrides": cost_overrides,
                 "contract_types": contract_types, "arms": arms, "ml1": ml1, "kume_risk": kume_risk}
        bad = sorted(k for k, x in given.items() if x not in ((), {}, None, False))
        if bad:
            raise ConfigError(f"{bad} yalniz mode='paper' ile verilebilir (mode={mode!r})")
    live_raw = raw.get("live")
    if mode in ("testnet", "live"):
        if live_raw is None:
            raise ConfigError(f"live blogu mode={mode} icin zorunlu")
        live = _build_live(live_raw)
    else:
        if live_raw is not None:
            raise ConfigError(f"live blogu mode={mode} ile verilemez")
        live = None
    ttr = raw.get("target_trade_risk", risk_raw.get("target_trade_risk", LOCKED_CFG.target_trade_risk))
    if risk_raw:
        build_paper_risk_config(ttr, risk_raw, mode=mode)    # mode == 'paper'|'live' (digerleri yukarida reddedildi)
    else:
        build_risk_config(ttr)
    cost = raw["cost"] if isinstance(raw["cost"], CostModel) else None
    cost = _build_cost(dataclasses.asdict(cost) if cost else raw["cost"])
    if mode in ("testnet", "live"):
        if bot != "learner":
            raise ConfigError(f"mode={mode!r} yalniz bot='learner' ile gecerli")
        if cost.trigger_source != "mark":
            raise ConfigError(f"mode={mode!r}: cost.trigger_source='mark' zorunlu")
    if mode in ("testnet", "live"):
        check_shared_paths(mode, raw["var_dir"], raw["kill_file"], pause_file)
    return EngineConfig(
        schema=SCHEMA, mode=mode, bot=bot, pairs=pairs,  # type: ignore[arg-type]
        wallet_start=nums["wallet_start"], cost=cost, target_mode=target_mode,  # type: ignore[arg-type]
        record_filtered_candidates=raw["record_filtered_candidates"],
        stale_factor=nums["stale_factor"], loop_sleep_s=nums["loop_sleep_s"],
        bar_wait_s=nums["bar_wait_s"], minute_wait_s=nums["minute_wait_s"],
        reconcile_open_s=nums["reconcile_open_s"], reconcile_flat_s=nums["reconcile_flat_s"],
        strategy=strategy,
        target_trade_risk=float(ttr),
        startup_wait_s=startup_wait, pause_file=pause_file, leverage=lev, live=live, ladder_follow=ladder_follow,
        shadow_blocks=shadow_blocks, mtm_marks=mtm_marks,
        optional_pairs=optional_pairs, retired_pairs=retired_pairs, max_positions=max_positions,
        risk=risk_raw, clusters=clusters,
        flat_bar_guard=flat_bar_guard, contract_types=contract_types, cost_overrides=cost_overrides,
        arms=arms, exit_modes=exit_modes, etiket_kurallari=etiket_kurallari,
        ml1=ml1, stop_tabani=stop_tabani, kume_risk=kume_risk,
        **{n: raw[n] for n in _STR},
    )


def _read(path: Any) -> dict[str, Any]:
    try:
        with open(Path(path), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise ConfigError(f"yapilandirma okunamadi: {path}: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"yapilandirma nesne olmali: {path}")
    return data


def absolutize_paths(cfg: EngineConfig, base_path: Any) -> EngineConfig:
    """DD-2 (D7) + DD-8 (E1): goreli `kill_file` ve `pause_file` (her kipte) ile, testnet/live'da ayrica `var_dir`, yapilandirma
    dizinine gore mutlak yola cevrilir; boylece `trader_engine kill|pause|...` baska bir dizinden calistirilsa da motorun
    izledigi dosyalara yazar. Dizin `config/` ise kok onun ustudur (`<kok>/shared/KILL`), degilse dizinin kendisidir. Zaten mutlak
    alan degismez. paper/backtest'te `var_dir`, `market_db`, `history_dir` OLDUGU GIBI kalir.
    `load_engine_config` ham degeri aynen dondurur ("paper config loads unchanged" sozlesmesi)."""
    cdir = Path(base_path).resolve().parent
    root = cdir.parent if cdir.name == "config" else cdir
    names = ["kill_file", "pause_file"] + (["var_dir"] if cfg.mode in ("testnet", "live") else [])
    kw = {n: str(root / getattr(cfg, n)) for n in names if not os.path.isabs(getattr(cfg, n))}
    return dataclasses.replace(cfg, **kw) if kw else cfg


def absolutize_kill_file(cfg: EngineConfig, base_path: Any) -> EngineConfig:
    """Geriye uyum adi (DD-2); `absolutize_paths`a yonlenir."""
    return absolutize_paths(cfg, base_path)


def load_engine_config(base_path: Any, bot_path: Any = None, *,
                       env: Mapping[str, str] | None = None, overlay_path: Any = None) -> EngineConfig:
    """base (+ bot) (+ overlay) JSON birlestirir ve dogrular. LIVE_CONFIRM (11 §3.1) burada YALNIZ `env=` acikca
    verildiyse denetlenir; kosu yolu (cli run / build_engine) check_live_confirm'i kendisi cagirir
    (kill/pause/init-ledger/reconcile/backtest live yapilandirmada LIVE_CONFIRM istemez).
    Evren (pairs/optional_pairs) YALNIZ bu JSON dosyalarindan gelir: otomatik evren kaplamasi YOKTUR (sahip karari: 14 cift sabit)."""
    merged = _read(base_path)
    if bot_path is not None:
        merged = deep_merge(merged, _read(bot_path))
    if overlay_path is not None:
        merged = deep_merge(merged, _read(overlay_path))
    for k in _KALDIRILAN_ANAHTARLAR:                  # eski sunucu kaplamasi kalmis olabilir: bot acilisi bozulmasin (yok sayilir)
        if merged.pop(k, None) is not None:
            logging.getLogger("engine.config").warning("kaldirilan yapilandirma anahtari yok sayildi: %s", k)
    if isinstance(merged.get("clusters"), dict):        # eski kume basina tavan (max_positions) kaldirildi: sunucu kaplamasinda kalmis olabilir
        for cname, cspec in merged["clusters"].items():
            if isinstance(cspec, dict) and cspec.pop("max_positions", None) is not None:
                logging.getLogger("engine.config").warning("kaldirilan yapilandirma anahtari yok sayildi: clusters.%s.max_positions", cname)
    cfg = _validate(merged)
    if env is not None:
        check_live_confirm(cfg, env)
    return cfg


def apply_overrides(cfg: EngineConfig, **kw: Any) -> EngineConfig:
    if "cost" in kw and isinstance(kw["cost"], Mapping):
        if not set(kw["cost"]) <= _COST_KEYS:
            raise ConfigError("cost bilinmeyen anahtar")
        kw["cost"] = dataclasses.replace(cfg.cost, **kw["cost"])
    unknown = set(kw) - _TOP_KEYS
    if unknown:
        raise ConfigError(f"bilinmeyen anahtar: {sorted(unknown)}")
    if kw.get("mode") in ("backtest", "paper") and "live" not in kw:
        kw["live"] = None                        # testnet/live yapilandirmasindan backtest/paper'a gecis live blogunu birakir
    d = {f.name: getattr(cfg, f.name) for f in dataclasses.fields(cfg)}
    d.update(kw)
    return _validate(d)


def load_cli_config(config_dir: Any, bot: str = "learner", env: str | None = None, *,
                    overlay_path: Any = None) -> EngineConfig:
    """DD-8 (E2): komut satiri ve duman betiklerinin TEK yukleyicisi = `load_engine_config(base, bot, overlay)` +
    `absolutize_paths`. Betikler `load_engine_config`i dogrudan cagirmaz (mutlaklastirma atlanmasin). `overlay_path` (yalniz
    `smoke_live --live-overlay`) verilirse `engine.<env>.json` yerine o katman kullanilir."""
    d = Path(config_dir)
    overlay = overlay_path if overlay_path is not None else (d / f"engine.{env}.json" if env else None)
    cfg = load_engine_config(d / "engine.base.json", d / f"engine.{bot}.json", overlay_path=overlay)
    return absolutize_paths(cfg, d / "engine.base.json")
