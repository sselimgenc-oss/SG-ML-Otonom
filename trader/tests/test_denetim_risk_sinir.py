"""Denetim (20.11) mutasyon sagkalanlari: risk.check_entry / size_position / paper_config / tightened sinir (esitlik) testleri.
Tam gosterilebilir (ikili) sayilar kullanilir; her sinir icin hem tam esitlik (izinli) hem hemen disi (red)."""
from __future__ import annotations

import pytest

from trader_core import risk
from trader_core.risk import (AccountState, Candidate, OpenPosition, RiskConfig, SizeResult, check_entry, paper_config,
                              size_position, tightened)

EQ = 1024.0
CFG = paper_config(max_open_risk=0.0625, max_same_dir_risk=0.03125, daily_max_loss=0.0625)      # 64 / 32 / 64
CFG_DAILY = paper_config(max_open_risk=0.109375, max_same_dir_risk=0.0625, daily_max_loss=0.0625)  # 112 / 64 / 64
CAND = Candidate(pair="BTC/USDT", side="long", entry=100.0, stop=96.0, leverage=5)
R_NEW = 16.0                                              # yeni islemin riski (<= max_trade_risk*EQ = 20.48)


@pytest.fixture
def sabit_boyut(monkeypatch):
    monkeypatch.setattr(risk, "size_position", lambda *a, **k: SizeResult(qty=4.0, notional=400.0, margin=80.0,
                                                                         risk_amount=R_NEW))


def _op(pair, side, risk_amount, margin=1.0):
    return OpenPosition(pair=pair, side=side, risk_amount=risk_amount, margin=margin)


def _dec(opens, cfg=CFG, cand=CAND, equity=EQ, day_start=EQ):
    return check_entry(AccountState(equity=equity, day_start_equity=day_start, open_positions=opens), cand, cfg)


def test_total_open_risk_equality_allowed_just_over_denied(sabit_boyut):
    assert _dec([_op("ETH/USDT", "short", 24.0), _op("SOL/USDT", "short", 24.0)]).allowed           # 48 + 16 == 64
    d = _dec([_op("ETH/USDT", "short", 24.0), _op("SOL/USDT", "short", 24.0625)])
    assert not d.allowed and "toplam açık risk" in d.reason


def test_same_direction_risk_equality_allowed_just_over_denied(sabit_boyut):
    assert _dec([_op("ETH/USDT", "long", 16.0)]).allowed                                            # 16 + 16 == 32
    d = _dec([_op("ETH/USDT", "long", 16.0625)])
    assert not d.allowed and "aynı yön" in d.reason


LOCKED = risk.LOCKED_CFG          # kilitli (canli/testnet) gunluk butce: bugunku kayip + acik risk + yeni risk <= 0.05*1024 = 51.2


def test_daily_budget_equality_allowed_just_over_denied(sabit_boyut):
    assert _dec([_op("ETH/USDT", "short", 24.0), _op("SOL/USDT", "long", 11.2)], cfg=LOCKED).allowed   # 35.2 + 16 == 51.2
    d = _dec([_op("ETH/USDT", "short", 24.0), _op("SOL/USDT", "long", 11.2625)], cfg=LOCKED)
    assert not d.allowed and "günlük zarar bütçesi" in d.reason


def test_daily_budget_counts_realized_loss(sabit_boyut):
    # gerceklesen zarar 16 (equity 1008): 16 + 19.2 + 16 == 51.2 izinli; biraz fazlasi red
    assert _dec([_op("ETH/USDT", "short", 19.2)], cfg=LOCKED, equity=1008.0).allowed
    assert not _dec([_op("ETH/USDT", "short", 19.25)], cfg=LOCKED, equity=1008.0).allowed


def test_daily_loss_already_hit_equality_denied(sabit_boyut):
    d = _dec([], cfg=CFG_DAILY, equity=960.0)                  # (960-1024)/1024 == -0.0625 == -daily_max_loss
    assert not d.allowed and "günlük sınır aşıldı" in d.reason
    assert "günlük sınır aşıldı" not in _dec([], cfg=CFG_DAILY, equity=960.5).reason      # sinirin hemen icinde: bu kapi acik


def test_total_margin_equality_allowed_just_over_denied(sabit_boyut):
    assert _dec([_op("ETH/USDT", "short", 1.0, margin=944.0)]).allowed                              # 944 + 80 == 1024
    d = _dec([_op("ETH/USDT", "short", 1.0, margin=944.0625)])
    assert not d.allowed and "teminat" in d.reason


def test_liquidation_distance_equality_allowed_just_inside_denied(sabit_boyut, monkeypatch):
    # |giris - likidasyon| == 1.5 * |giris - stop| : 6 == 1.5 * 4
    monkeypatch.setattr(risk, "liquidation_price", lambda *a, **k: 94.0)
    assert _dec([]).allowed
    monkeypatch.setattr(risk, "liquidation_price", lambda *a, **k: 94.25)                           # 5.75 < 6
    d = _dec([])
    assert not d.allowed and "likidasyon" in d.reason
    monkeypatch.setattr(risk, "liquidation_price", lambda *a, **k: 93.75)                           # 6.25 > 6
    assert _dec([]).allowed


def test_min_notional_equality_allowed_just_over_denied():
    ok = size_position(1000.0, 100.0, 99.0, "long", 5, risk.LOCKED_CFG, 1.0, 1000.0)               # qty 10 * 100 == 1000
    assert ok.qty == 10.0 and ok.notional == 1000.0
    with pytest.raises(ValueError, match="en küçük emir"):
        size_position(1000.0, 100.0, 99.0, "long", 5, risk.LOCKED_CFG, 1.0, 1000.0625)
    cand = Candidate(pair="BTC/USDT", side="long", entry=100.0, stop=99.0, leverage=5, qty_step=1.0, min_notional=1000.0)
    assert check_entry(AccountState(1000.0, 1000.0, []), cand).allowed
    cand2 = Candidate(pair="BTC/USDT", side="long", entry=100.0, stop=99.0, leverage=5, qty_step=1.0, min_notional=1000.0625)
    assert not check_entry(AccountState(1000.0, 1000.0, []), cand2).allowed


def test_margin_equals_equity_allowed_above_denied():
    cfg1 = RiskConfig(min_leverage=1)
    r = size_position(1000.0, 100.0, 99.0, "long", 1, cfg1)                                         # notional == equity, lev 1
    assert r.margin == 1000.0
    cand = Candidate(pair="BTC/USDT", side="long", entry=100.0, stop=99.0, leverage=1)
    assert check_entry(AccountState(1000.0, 1000.0, []), cand, cfg1).allowed
    with pytest.raises(ValueError, match="teminat"):
        size_position(1000.0, 100.0, 99.0, "long", 0.5, cfg1)                                       # margin 2000 > 1000


# ---- paper_config / tightened / pozitif alan
def test_paper_config_rejects_unknown_key_with_valueerror():
    with pytest.raises(ValueError, match="bilinmeyen"):
        paper_config(max_trade_risk=0.01)
    with pytest.raises(ValueError, match="bilinmeyen"):
        paper_config(target_trade_risk=0.01, nope=1)
    assert paper_config(target_trade_risk=0.01).target_trade_risk == 0.01


def test_tightened_rejects_loosening_and_nonpositive_accepts_equal_and_tighter():
    base = risk.LOCKED_CFG
    for bad in (base.target_trade_risk * 1.0001, 0.02, 0.0, -0.001):
        with pytest.raises(ValueError):
            tightened(base, target_trade_risk=bad)
    assert tightened(base, target_trade_risk=base.target_trade_risk).target_trade_risk == base.target_trade_risk
    assert tightened(base, target_trade_risk=0.01).target_trade_risk == 0.01


@pytest.mark.parametrize("alan", ["max_trade_risk", "target_trade_risk", "daily_max_loss", "max_open_risk",
                                  "max_same_dir_risk", "max_notional_ratio", "liq_safety_factor"])
def test_positive_only_fields_reject_zero(alan):
    with pytest.raises(ValueError, match="> 0"):
        RiskConfig(**{alan: 0})


# --- Karar A (21.11): kagitta gunluk limit yalniz bugunku zarar; canli/testnet/kilitli degismez ---
def test_paper_open_risk_beyond_8pct_allowed_up_to_24pct_no_loss(sabit_boyut):
    cfg = paper_config(max_open_risk=0.24, max_same_dir_risk=0.16, daily_max_loss=0.08)
    opens = [_op("ETH/USDT", "short", 80.0), _op("SOL/USDT", "short", 80.0), _op("XRP/USDT", "short", 60.0)]  # 220 + 16 < 245.76
    assert _dec(opens, cfg=cfg).allowed                                   # acik risk 21.5% > %8, bugun zarar yok
    assert not _dec(opens + [_op("ADA/USDT", "short", 20.0)], cfg=cfg).allowed   # 240 + 16 > 245.76 -> max_open_risk


def test_paper_denies_after_8pct_loss_today(sabit_boyut):
    cfg = paper_config(max_open_risk=0.24, max_same_dir_risk=0.16, daily_max_loss=0.08)
    assert not _dec([], cfg=cfg, equity=920.0, day_start=1000.0).allowed     # tam %8 kayip -> yeni giris yok
    assert _dec([], cfg=cfg, equity=921.0, day_start=1000.0).allowed          # %7.9 kayip: izinli (acik risk bugete sayilmaz)
    # adim 10 tek basina (adim 4'u gecen): kayip %7.9 + acik risk 100 (%10) + yeni -> yine izinli
    assert _dec([_op("ETH/USDT", "short", 100.0)], cfg=cfg, equity=921.0, day_start=1000.0).allowed


def test_paper_unrealized_loss_counts_as_today_loss(sabit_boyut):
    cfg = paper_config(max_open_risk=0.24, max_same_dir_risk=0.16, daily_max_loss=0.08)
    assert not _dec([_op("ETH/USDT", "short", 8.0)], cfg=cfg, equity=EQ, day_start=EQ / 0.9).allowed   # equity dususu = %10 > %8


def test_live_testnet_locked_daily_budget_unchanged(sabit_boyut):
    """Kilitli (canli/testnet) kural AYNEN: bugunku kayip + acik risk + yeni risk <= %5; PaperRiskConfig'e ozgu degisiklik sizmaz."""
    assert risk.RiskConfig._DAILY_INCLUDES_OPEN_RISK is True and risk.PaperRiskConfig._DAILY_INCLUDES_OPEN_RISK is False
    assert risk.LOCKED_CFG._DAILY_INCLUDES_OPEN_RISK is True
    # 0.05*1024 = 51.2: acik 36 + yeni 16 = 52 > 51.2 -> red (kagitta ayni durum izinli olurdu)
    d = _dec([_op("ETH/USDT", "short", 36.0)], cfg=risk.LOCKED_CFG)
    assert not d.allowed and "günlük zarar bütçesi" in d.reason
    assert _dec([_op("ETH/USDT", "short", 35.0)], cfg=risk.LOCKED_CFG).allowed                         # 51 <= 51.2
    assert not _dec([], cfg=risk.LOCKED_CFG, equity=EQ, day_start=EQ + 40.0).allowed                    # 40 + 16 > 51.2
    import dataclasses
    assert "daily_budget_includes_open_risk" not in {f.name for f in dataclasses.fields(risk.LOCKED_CFG)}
