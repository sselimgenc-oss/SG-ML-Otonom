"""Risk kilidi: saf Python (stdlib) risk kuralları. Bkz. docs/risk-kilidi-spec.md (v2).

Sabitler `RiskConfig` varsayılanlarındadır; bot `LOCKED_CFG` kullanır. `HARD_LIMITS`
bu sınırlardan daha gevşek bir yapılandırma oluşturulmasını engeller.
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field, fields, replace
from decimal import Decimal

_SIDES = ("long", "short")

# Kilitli üst/alt sınırlar. *_min anahtarları alt sınırdır.
HARD_LIMITS = {
    "max_trade_risk": 0.02,
    "target_trade_risk": 0.014,
    "daily_max_loss": 0.05,
    "max_open_risk": 0.06,
    "max_same_dir_risk": 0.04,
    "max_leverage": 5,
    "min_leverage": 1,
    "max_notional_ratio": 1.0,
    # Alt sınırlar: maliyet ve güvenlik varsayımları gevşetilemez.
    "min_fee_rate": 0.0005,
    "min_slippage_rate": 0.0005,
    "min_maint_margin_rate": 0.004,
    "min_liq_safety_factor": 1.5,
}

# DD-12 §4.1: YALNIZ kağıt katmanı (mode="paper") için ayrı üst sınırlar. Testnet/canlı/geri test `HARD_LIMITS` kullanır;
# `RiskConfig` alanları ve HARD_LIMITS değişmez; kağıt sınırları yalnız `PaperRiskConfig` alt sınıfındadır.
PAPER_LIMITS = {**HARD_LIMITS,
                "target_trade_risk": 0.014,   # işlem başı risk kağıtta %1 (<= kilitli hedef); gevşemez
                "daily_max_loss": 0.08,
                "max_open_risk": 0.24,   # 20 Kasim 2026: kullanici onayli kagit gevsetmesi (0.12 -> 0.24)
                "max_same_dir_risk": 0.16}


def _num(x, name: str = "değer") -> float:
    """int/float/numbers.Real -> float; bool, None, metin, NaN, inf geçersiz."""
    if isinstance(x, bool) or not isinstance(x, numbers.Real):
        raise ValueError(f"{name} sayı olmalı")
    v = float(x)
    if not math.isfinite(v):
        raise ValueError(f"{name} sonlu olmalı")
    return v


def _whole(x, name: str) -> int:
    v = _num(x, name)
    if v != int(v):
        raise ValueError(f"{name} tam sayı olmalı")
    return int(v)


def _norm_side(side) -> str:
    if not isinstance(side, str):
        raise ValueError("yön metin olmalı")
    s = side.strip().lower()
    if s not in _SIDES:
        raise ValueError("yön 'long' veya 'short' olmalı")
    return s


def _norm_pair(pair) -> str:
    if not isinstance(pair, str):
        raise ValueError("çift metin olmalı")
    p = pair.strip().upper().split(":", 1)[0].strip()
    if not p:
        raise ValueError("çift boş olamaz")
    return p


@dataclass(frozen=True)
class RiskConfig:
    max_trade_risk: float = 0.02
    target_trade_risk: float = 0.014
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0005
    daily_max_loss: float = 0.05
    max_open_risk: float = 0.06
    max_same_dir_risk: float = 0.04
    min_leverage: int = 3
    max_leverage: int = 5
    maint_margin_rate: float = 0.004
    liq_safety_factor: float = 1.5
    max_notional_ratio: float = 1.0

    _LIMITS = HARD_LIMITS   # sınıf özniteliği (alan değil): `PaperRiskConfig` kağıt sınırlarını taşır
    # Adım 10 biçimi (sınıf özniteliği, alan değil: asdict/baseline dökümleri değişmez). True (kilitli/testnet/canlı):
    # loss_today + açık risk + yeni risk <= daily_max_loss*day_start. `PaperRiskConfig` False: yalnız bugünkü zarar.
    _DAILY_INCLUDES_OPEN_RISK = True

    def __post_init__(self) -> None:
        limits = self._LIMITS
        pos = ("max_trade_risk", "target_trade_risk", "daily_max_loss", "max_open_risk",
               "max_same_dir_risk", "liq_safety_factor", "max_notional_ratio")
        nonneg = ("fee_rate", "slippage_rate", "maint_margin_rate")
        for n in pos + nonneg:
            v = _num(getattr(self, n), n)
            if n in pos and v <= 0:
                raise ValueError(f"{n} > 0 olmalı")
            if n in nonneg and v < 0:
                raise ValueError(f"{n} negatif olamaz")
            object.__setattr__(self, n, v)
        for n in ("min_leverage", "max_leverage"):
            object.__setattr__(self, n, _whole(getattr(self, n), n))
        if self.target_trade_risk > self.max_trade_risk:
            raise ValueError("target_trade_risk, max_trade_risk değerini aşamaz")
        if self.min_leverage < 1 or self.min_leverage > self.max_leverage:
            raise ValueError("kaldıraç aralığı geçersiz")
        if self.maint_margin_rate >= 1:
            raise ValueError("maint_margin_rate < 1 olmalı")
        for n in ("max_trade_risk", "target_trade_risk", "daily_max_loss", "max_open_risk",
                  "max_same_dir_risk", "max_leverage", "max_notional_ratio"):
            if getattr(self, n) > limits[n]:
                raise ValueError(f"{n} kilitli üst sınırı aşıyor ({limits[n]})")
        if self.min_leverage < limits["min_leverage"]:
            raise ValueError("min_leverage kilitli alt sınırın altında")
        for n in ("fee_rate", "slippage_rate", "maint_margin_rate", "liq_safety_factor"):
            if getattr(self, n) < limits["min_" + n]:
                raise ValueError(f"{n} kilitli alt sınırın altında ({limits['min_' + n]})")


LOCKED_CFG = RiskConfig()


@dataclass(frozen=True)
class PaperRiskConfig(RiskConfig):
    """DD-12 §4.1: yalnız kağıt katmanı; alanlar RiskConfig ile aynı, üst sınırlar PAPER_LIMITS."""
    _LIMITS = PAPER_LIMITS
    # Karar A (21 Kasim 2026): kağıtta günlük limit yalnız bugünkü zarara (gerçekleşen+gerçekleşmemiş = day_start-equity)
    # bakar; loss_today >= daily_max_loss*day_start ise yeni giriş yok. Açık riski max_open_risk/max_same_dir_risk sınırlar.
    _DAILY_INCLUDES_OPEN_RISK = False

# DD-12 §4.1: kağıt parametreleri. Yalnız `paper_config` (trader_engine.config, mode="paper") üretir.
PAPER_KEYS = ("target_trade_risk", "max_open_risk", "max_same_dir_risk", "daily_max_loss")


def paper_config(**kw: float) -> RiskConfig:
    """Kağıt katmanı RiskConfig'i: LOCKED_CFG'den yalnız `PAPER_KEYS` ayarlanabilir; her biri PAPER_LIMITS'i aşamaz
    (aşarsa ValueError). Verilmeyen anahtar kilitli değerde kalır; `PaperRiskConfig` döner."""
    unknown = set(kw) - set(PAPER_KEYS)
    if unknown:
        raise ValueError(f"paper_config bilinmeyen anahtar: {sorted(unknown)}")
    d = {f.name: getattr(LOCKED_CFG, f.name) for f in fields(LOCKED_CFG)}
    d.update(kw)
    return PaperRiskConfig(**d)


def tightened(base: RiskConfig, *, target_trade_risk: float) -> RiskConfig:
    """`base`in yalniz `target_trade_risk` değeri daha SIKI (<= base, > 0) bir kopyası. Gevşek/geçersiz değer
    ValueError (kilit asla gevşetilemez; RiskConfig HARD_LIMITS ayrıca denetler)."""
    v = _num(target_trade_risk, "target_trade_risk")
    if v <= 0 or v > base.target_trade_risk:
        raise ValueError(f"target_trade_risk (0, {base.target_trade_risk}] içinde olmalı: {v!r}")
    return replace(base, target_trade_risk=v)


@dataclass(frozen=True)
class SizeResult:
    qty: float
    notional: float
    margin: float
    risk_amount: float


@dataclass(frozen=True)
class OpenPosition:
    pair: str
    side: str
    risk_amount: float
    margin: float


@dataclass(frozen=True)
class AccountState:
    equity: float
    day_start_equity: float
    open_positions: list = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    pair: str
    side: str
    entry: float
    stop: float
    leverage: float
    qty_step: float | None = None
    min_notional: float = 0.0


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    size: SizeResult | None = None


def liquidation_price(entry: float, side: str, leverage: float, mmr: float) -> float:
    """İzole teminat likidasyon fiyatı yaklaşığı."""
    side = _norm_side(side)
    entry, leverage, mmr = _num(entry, "entry"), _num(leverage, "leverage"), _num(mmr, "mmr")
    if leverage <= 0:
        raise ValueError("kaldıraç pozitif olmalı")
    if side == "long":
        return entry * (1 - 1 / leverage + mmr)
    return entry * (1 + 1 / leverage - mmr)


def loss_at_stop(qty: float, entry: float, stop: float, cfg: RiskConfig) -> float:
    """Stop'ta gerçekleşen kayıp, her iki taraf komisyon+kayma dahil."""
    cost = cfg.fee_rate + cfg.slippage_rate
    return qty * abs(entry - stop) + qty * entry * cost + qty * stop * cost


def _floor_to_step(qty: float, step: float) -> float:
    """Kayan nokta hatasına karşı güvenli aşağı yuvarlama; sonuç asla qty'yi aşmaz."""
    d = Decimal(repr(qty))
    s = Decimal(repr(step))
    out = float((d // s) * s)
    while out > qty:
        out = math.nextafter(out, 0.0)
    return out


def size_position(equity: float, entry: float, stop: float, side: str,
                  leverage: float, cfg: RiskConfig = LOCKED_CFG,
                  qty_step: float | None = None, min_notional: float = 0.0) -> SizeResult:
    """loss_at_stop(qty) = target_trade_risk*equity denklemini çözer; notional ve adım sınırlı."""
    side = _norm_side(side)
    equity, entry, stop = _num(equity, "equity"), _num(entry, "entry"), _num(stop, "stop")
    leverage = _num(leverage, "leverage")
    min_notional = _num(min_notional, "min_notional")
    if qty_step is not None:
        qty_step = _num(qty_step, "qty_step")
        if qty_step <= 0:
            raise ValueError("qty_step > 0 olmalı")
    if equity <= 0 or entry <= 0 or stop <= 0 or leverage <= 0 or min_notional < 0:
        raise ValueError("equity, fiyat ve kaldıraç pozitif olmalı")
    if entry == stop:
        raise ValueError("stop mesafesi sıfır")
    per_qty = loss_at_stop(1.0, entry, stop, cfg)
    if not per_qty > 0:
        raise ValueError("birim kayıp hesaplanamadı")
    limit = cfg.target_trade_risk * equity
    qty_risk = limit / per_qty
    if loss_at_stop(qty_risk, entry, stop, cfg) > limit:  # savunma amaçlı
        qty_risk = math.nextafter(qty_risk, 0.0)
    notional_cap = cfg.max_notional_ratio * equity
    qty_cap = notional_cap / entry
    while qty_cap * entry > notional_cap:
        qty_cap = math.nextafter(qty_cap, 0.0)
    qty = min(qty_risk, qty_cap)
    if qty_step is not None:
        qty = _floor_to_step(qty, qty_step)
    if not qty > 0 or qty * entry < min_notional:
        raise ValueError("miktar sıfır veya en küçük emir değerinin altında")
    risk = loss_at_stop(qty, entry, stop, cfg)
    if risk > cfg.max_trade_risk * equity:
        raise ValueError("işlem riski üst sınırı aşıyor")
    notional = qty * entry
    margin = notional / leverage
    if margin > equity:
        raise ValueError("gereken teminat özsermayeyi aşıyor")
    return SizeResult(qty=qty, notional=notional, margin=margin, risk_amount=risk)


def _deny(reason: str) -> Decision:
    return Decision(False, reason, None)


def _check_entry(state: AccountState, cand: Candidate, cfg: RiskConfig) -> Decision:
    # 1. Girdi geçerliliği
    try:
        equity = _num(state.equity, "equity")
        day_start = _num(state.day_start_equity, "day_start_equity")
        entry = _num(cand.entry, "entry")
        stop = _num(cand.stop, "stop")
        lev_raw = _num(cand.leverage, "leverage")
        side = _norm_side(cand.side)
        pair = _norm_pair(cand.pair)
        qty_step = None if cand.qty_step is None else _num(cand.qty_step, "qty_step")
        min_notional = _num(cand.min_notional, "min_notional")
        if qty_step is not None and qty_step <= 0:
            raise ValueError("qty_step > 0 olmalı")
        if min_notional < 0:
            raise ValueError("min_notional negatif olamaz")
        if equity <= 0 or day_start <= 0:
            raise ValueError("equity > 0 olmalı")
        if entry <= 0 or stop <= 0:
            raise ValueError("fiyat > 0 olmalı")
        positions = state.open_positions
        if not isinstance(positions, (list, tuple)):
            raise ValueError("open_positions liste olmalı")
        opens = []
        for p in positions:
            if not isinstance(p, OpenPosition):
                raise ValueError("açık pozisyon geçersiz")
            ra = _num(p.risk_amount, "risk_amount")
            mg = _num(p.margin, "margin")
            if ra < 0 or mg < 0:
                raise ValueError("açık pozisyon negatif değer içeriyor")
            opens.append((_norm_pair(p.pair), _norm_side(p.side), ra, mg))
    except ValueError as exc:
        return _deny(f"geçersiz girdi: {exc}")
    # 2. Stop tarafı
    if side == "long" and stop >= entry:
        return _deny("stop yanlış tarafta: long için stop < entry olmalı")
    if side == "short" and stop <= entry:
        return _deny("stop yanlış tarafta: short için stop > entry olmalı")
    # 3. Kaldıraç
    if lev_raw != int(lev_raw) or lev_raw < cfg.min_leverage or lev_raw > cfg.max_leverage:
        return _deny(f"kaldıraç aralık dışı: {cfg.min_leverage}-{cfg.max_leverage} tam sayı olmalı")
    lev = int(lev_raw)
    # 4. Günlük zarar zaten dolmuş mu
    if (equity - day_start) / day_start <= -cfg.daily_max_loss:
        return _deny("günlük sınır aşıldı: yeni işlem açılamaz")
    # 5. Aynı çift
    if any(op[0] == pair for op in opens):
        return _deny(f"{pair} için zaten açık pozisyon var")
    # 6. Boyut
    try:
        size = size_position(equity, entry, stop, side, lev, cfg, qty_step, min_notional)
    except ValueError as exc:
        return _deny(f"boyutlandırma reddedildi: {exc}")
    # 6b. Savunma: boyut sonucunu yeniden doğrula (bozuk sonuca asla güvenme)
    try:
        s_qty = _num(size.qty, "qty")
        s_notional = _num(size.notional, "notional")
        s_margin = _num(size.margin, "margin")
        s_risk = _num(size.risk_amount, "risk_amount")
    except (ValueError, TypeError, AttributeError) as exc:
        return _deny(f"boyutlandırma reddedildi: geçersiz sonuç ({exc})")
    if (s_qty <= 0 or s_notional <= 0 or s_margin < 0 or s_risk < 0
            or s_risk > cfg.max_trade_risk * equity
            or s_notional > cfg.max_notional_ratio * equity
            or s_margin > equity):
        return _deny("boyutlandırma reddedildi: sonuç sınır dışında")
    # 7. Likidasyon güvenliği
    liq = liquidation_price(entry, side, lev, cfg.maint_margin_rate)
    if abs(entry - liq) < cfg.liq_safety_factor * abs(entry - stop):
        return _deny("likidasyon çok yakın: giriş-likidasyon mesafesi yetersiz")
    # 8. Toplam açık risk
    total_open = sum(op[2] for op in opens)
    if total_open + size.risk_amount > cfg.max_open_risk * equity:
        return _deny("toplam açık risk sınırı aşılır")
    # 9. Aynı yön riski
    same = sum(op[2] for op in opens if op[1] == side)
    if same + size.risk_amount > cfg.max_same_dir_risk * equity:
        return _deny(f"aynı yön ({side}) risk sınırı aşılır")
    # 10. Günlük bütçe
    loss_today = max(0.0, day_start - equity)
    if cfg._DAILY_INCLUDES_OPEN_RISK:
        if loss_today + total_open + size.risk_amount > cfg.daily_max_loss * day_start:
            return _deny("günlük zarar bütçesi aşılır")
    elif loss_today >= cfg.daily_max_loss * day_start:   # kağıt: %8 bugün kaybedildi -> yeni giriş yok
        return _deny("günlük zarar bütçesi aşılır")
    # 11. Teminat toplamı
    if sum(op[3] for op in opens) + size.margin > equity:
        return _deny("toplam teminat özsermayeyi aşar")
    # 12.
    return Decision(True, "izin verildi", size)


def check_entry(state: AccountState, cand: Candidate, cfg: RiskConfig = LOCKED_CFG) -> Decision:
    """Giriş kurallarını sırayla uygular; beklenmeyen hatada kapalı (fail-closed)."""
    try:
        return _check_entry(state, cand, cfg)
    except Exception as exc:  # noqa: BLE001
        return Decision(False, f"iç hata: {exc!r}", None)


def check_entry_scaled(state: AccountState, cand: Candidate, cfg: RiskConfig, mult: float) -> Decision:
    """`check_entry`, hedef işlem riski `mult` (0, 1] ile ÇARPILMIŞ kopya üzerinde (yalnız küçültür; sınırlar ve diğer alanlar aynı).
    Kademeli boyut küçültme (docs/motor/kademeli-kucultme-spec.md) kullanır; mult > 1 ya da <= 0 ValueError."""
    m = _num(mult, "mult")
    if not 0 < m <= 1:
        raise ValueError(f"mult (0, 1] içinde olmalı: {m!r}")
    return check_entry(state, cand, tightened(cfg, target_trade_risk=cfg.target_trade_risk * m))
