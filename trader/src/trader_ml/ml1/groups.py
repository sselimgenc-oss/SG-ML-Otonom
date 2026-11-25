"""ML1: kurulum (setup) -> fikir grubu eslemesi (plan bolum 6: 71 kurulum, 20 grup) ve kural kolu listesi.

`family` ve `tf` ayri sutunlar olarak tutulur; grup yalniz fikir (ornek: PULLBACK_1LEG) sinifidir.
M1 (ML kolu), DL1 ve HB1 kural kolu degildir: aday tablosuna girmez."""
from __future__ import annotations

import json
from pathlib import Path

# grup -> kurulumlar (kurulum = SETUP; formasyon kollari `AILE-KOD`)
_GRUP_KURULUM: dict[str, tuple[str, ...]] = {
    "PULLBACK_1LEG": ("T1", "T1-GERI3", "T1-SEVIYE", "IN1-MAGERI", "IN1-FIBO"),
    "PULLBACK_2LEG": ("H2", "H2-MINI", "H2-YARI"),
    "TREND_BREAKOUT": ("TF1", "TF1-FITIL", "TF1-HACIM", "IN1-HACIM", "MF1-MARUBOZU"),
    "RANGE_EDGE": ("R1", "R1-ALT", "R1-ERKEN", "R1-HA", "GF1-YATAY"),
    "LEVEL_RETEST": ("B1", "B1-BOLGE", "B1-MUM", "GF1-RETEST"),
    "FALSE_BREAK": ("F1", "F1-IKINCI", "GF1-SAHTE", "MF1-ICSAHTE"),
    "SQUEEZE_BREAK": ("S1", "S1-HACIM", "S1-OLCULU"),
    "CHART_CONT": ("GF1-UCGEN", "GF1-FLAMA", "GF1-BAYRAK"),
    "CHART_REVERSAL": ("GF1-IKILI", "GF1-UCLU", "GF1-OBO", "GF1-KUPA", "GF1-KAMA"),
    "CHANNEL_TLINE": ("GF1-KANAL", "GF1-TREND", "PA2-TCIZGI"),
    "CANDLE_PIN": ("MF1-PINBAR", "MF1-TERSCEKIC", "MF1-CIMBIZ"),
    "CANDLE_ENGULF": ("MF1-YUTAN", "MF1-DELICI", "MF1-DISBAR"),
    "CANDLE_STAR3": ("MF1-YILDIZ", "MF1-UCASKER"),
    "CANDLE_INSIDE": ("MF1-HARAMI", "MF1-ICCUBUK"),
    "OSC_REVERSAL": ("IN1-RSI", "IN1-RSI2", "IN1-RSIDONUS", "IN1-STOK", "IN1-UYUMSUZ"),
    "MA_CROSS": ("IN1-MAKESISIM", "IN1-HIZLIMA", "IN1-TK", "IN1-MACD"),
    "MA_TREND_FLIP": ("IN1-FIYATMA", "IN1-KUMO"),
    "BAND_VWAP": ("IN1-BOLL", "IN1-BOLLKIR", "IN1-VWAP"),
    "SD_ZONE": ("PA2-BOLGE", "PA2-EMIRBLOK", "PA2-FVG", "PA2-SEVIYE", "PA2-ONCEKI"),
    "EXHAUSTION": ("PA2-TUKENIS", "PA2-UCVURUS"),
}
GRUP_ADLARI: tuple[str, ...] = tuple(_GRUP_KURULUM)
GRUPLAR: dict[str, str] = {s: g for g, ss in _GRUP_KURULUM.items() for s in ss}      # setup -> grup
DISLANAN_AILELER = ("M1", "DL1", "HB1")                                                # kural kolu degil
CONFIG_YOLU = Path(__file__).resolve().parents[3] / "config" / "engine.paper.json"


def split_arm_id(arm_id: str) -> tuple[str, str]:
    """`IN1-RSI@1h` -> (`IN1-RSI`, `1h`)."""
    setup, _, tf = arm_id.partition("@")
    return setup, tf


def family(arm_id_or_setup: str) -> str:
    """`MF1-YUTAN@1h` -> `MF1`; `T1@4h` -> `T1`."""
    return split_arm_id(arm_id_or_setup)[0].split("-")[0]


def group(arm_id_or_setup: str) -> str:
    """Fikir grubu; bilinmeyen kurulum KeyError (sessiz varsayilan yok)."""
    return GRUPLAR[split_arm_id(arm_id_or_setup)[0]]


def rule_arm_ids(config_path: str | Path | None = None) -> list[str]:
    """config/engine.paper.json `arms` icinden kural kollari (M1/DL1/HB1 haric), config sirasiyla."""
    cfg = json.loads(Path(config_path or CONFIG_YOLU).read_text(encoding="utf-8"))
    return [a for a in cfg["arms"] if family(a) not in DISLANAN_AILELER]
