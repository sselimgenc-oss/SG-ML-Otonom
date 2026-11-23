"""PriceActionLab (DD-12 WP-11; `price_action_lab_ml`): cok kurulumlu (arm) bilesik strateji.

Kurulum = `strategies/arms/<kod>.py` dosyasi; kimlik `arm_id = <KURULUM>@<zaman dilimi>` (15m / 1h / 4h / 1d). Yapilandirma
`arms` listesi hangi kurulumun hangi zaman diliminde calisacagini soyler; kurulumlar paket klasorunden adla bulunur
(`arms.find_arm`), bu dosyada ya da kayit defterinde degisiklik gerekmez.

Karar adimi 15 dakikadir (`decision_tf`); her adimda YALNIZ kapanan zaman dilimlerinin kurulumlari hesaplanir (D-T16).
1g bar = UTC gununun 6 x 4s'i (bars.aggregate_4h_to_1d). Ortak `compute_signals` tablosu zaman dilimi basina bir kez hesaplanir
ve T1/R1 gibi CORE kurulumlar bu tablodan satir secer. ML (r03, `ml_pairs`) yalniz 1s CORE adaylarina uygulanir
(`PriceActionV1Ml` sarmalayicisi; D-T18: yalniz T1@1h + R1@1h ile `price_action_v1_full_ml` ile ayni cikti); diger zaman
dilimleri/kurulumlar puansiz gecer (WP-10'a kadar). Strateji yalniz aday uretir: boyut, emir, defter, kapi onun isi degildir."""
from __future__ import annotations

import dataclasses
import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime

import pandas as pd

from trader_core import signals as S

from .. import arm_guard as AG
from ..bars import (ARM_TFS, MIN_CONTIG_ARM, STARTUP_BARS_ARM, WINDOW_ARM, arm_tf_delta)
from .arms import ArmError, ArmInput, find_arm, make_arm_id, mask_to_setups, parse_arm_id
from .base import ExitPolicy, StrategyContext, StrategyError, StrategyInfo
from .price_action_v1 import _REENTRY_BLOCK, _param_specs
from .price_action_v1_ml import PriceActionV1Ml

log = logging.getLogger("engine.strategy.lab")

NAME = "price_action_lab_ml"
VERSION = "1.0-lab1"
DECISION_TF = "15m"
DEFAULT_ARMS = ("T1@1h", "R1@1h")            # D-T18: price_action_v1_full ile esdeger varsayilan
CORE_KEY = "core"                             # CORE kurulumlarin birlesik tablosunun anahtari (digerleri kurulum kodu)


class _CoreInner:
    """`PriceActionV1Ml` sarmalayicisinin ictigi strateji (PriceActionV1 benzeri): 1s CORE kurulumlarinin birlesik tablosu."""

    def __init__(self, lab: "PriceActionLab") -> None:
        self.lab = lab
        self.counters = lab.counters

    @property
    def info(self) -> StrategyInfo:
        return self.lab.info

    @property
    def setups_enabled(self) -> tuple[str, ...]:
        return self.lab.info.setups

    def validate_params(self, m: Mapping) -> Mapping:
        return self.lab.validate_params(m)

    def exit_policy(self) -> ExitPolicy | None:
        return None

    def compute(self, ctx: StrategyContext) -> pd.DataFrame:
        return self.lab.core_group_table(ctx)

    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        return self.lab.reentry_filter(row, ctx)


class PriceActionLab:
    decision_tf = DECISION_TF                                   # motor karar adimi (15 dk); strateji bilgisi, motor okur
    accepted_prev_strategies = ("price_action_v1", "price_action_v1_full_ml", "price_action_v1_ml", "price_action_v1_full")   # acik pozisyonla etiket gecisine izin

    def __init__(self, arms: Sequence[str] = DEFAULT_ARMS, *, block_same_bar_reentry: bool = True) -> None:
        self.counters: Counter = Counter()
        self.block_same_bar_reentry = bool(block_same_bar_reentry)
        self._enabled: dict[str, list] = {}
        self._arm_ids: tuple[str, ...] = ()
        self._core_key: tuple | None = None
        self._core_val: pd.DataFrame | None = None
        self._core_c: tuple[pd.DataFrame, pd.DataFrame] | None = None     # (dolu satirlarin tablosu, dolu tetik) - olu mum yoksa ikisi de tam
        self._reg_cache: dict[str, tuple] = {}                  # cift -> (son 4s acilis, rejim parametreleri, uzunluk, rejim tablosu); tek giris/cift
        self.info = self._make_info(())
        self._inner = _CoreInner(self)
        self._ml = PriceActionV1Ml(self._inner, name=NAME, version=VERSION, fail_open=True)
        self._ml.ml_block = False                           # 19 Kasim (sahip karari): kagitta ML hicbir adayi elemez, yalniz puanlar
        self.set_arms(arms)

    # ------------------------------------------------------------------ kurulum kumesi
    def _make_info(self, setups: tuple[str, ...]) -> StrategyInfo:
        return StrategyInfo(
            name=NAME, version=VERSION, setups=setups, timeframes=("trigger", "4h"), allowed_trigger_tfs=("1h",),
            warmup_bars={"1h": STARTUP_BARS_ARM["1h"], "15m": STARTUP_BARS_ARM["15m"], "4h": STARTUP_BARS_ARM["4h"]},
            window_bars={"1h": WINDOW_ARM["1h"], "15m": WINDOW_ARM["15m"], "4h": WINDOW_ARM["4h"]},
            min_contiguous=dict(MIN_CONTIG_ARM), param_specs=_param_specs(), paper_allowed=True)

    def set_arms(self, arm_ids: Sequence[str]) -> None:
        """arm_id listesini (sirali) yukler; bilinmeyen kurulum/zaman dilimi StrategyError('unknown_arm')."""
        enabled: dict[str, list] = {tf: [] for tf in ARM_TFS}
        setups: list[str] = []
        ids: list[str] = []
        for aid in arm_ids:
            try:
                setup, tf = parse_arm_id(aid)
                mod = find_arm(setup)
            except ArmError as e:
                raise StrategyError("unknown_arm", str(e)) from e
            if tf not in mod.TIMEFRAMES:
                raise StrategyError("unknown_arm", f"{setup} {tf} zaman diliminde desteklenmiyor ({mod.TIMEFRAMES})")
            if make_arm_id(setup, tf) in ids:
                raise StrategyError("unknown_arm", f"yinelenen kurulum: {aid}")
            enabled[tf].append(mod)
            ids.append(make_arm_id(setup, tf))
            if setup not in setups:
                setups.append(setup)
        self._enabled = enabled
        self._arm_ids = tuple(ids)
        self.info = self._make_info(tuple(setups))
        if hasattr(self, "_ml"):
            self._ml.info = dataclasses.replace(self.info)

    @property
    def arm_ids(self) -> tuple[str, ...]:
        return self._arm_ids

    def arms_at(self, tf: str) -> list:
        return self._enabled.get(tf, [])

    def tfs(self) -> tuple[str, ...]:
        return tuple(tf for tf in ARM_TFS if self._enabled.get(tf))

    def label(self) -> str:
        return f"strategy:{self.info.name}@{self.info.version}"

    # ------------------------------------------------------------------ ML (yalniz 1s CORE adaylari)
    @property
    def ml_mode(self) -> str:
        return self._ml.ml_mode

    def set_ml_mode(self, mode: str) -> None:
        self._ml.set_ml_mode(mode)

    @property
    def ml_universe(self):
        return self._ml.ml_universe

    def set_ml_universe(self, pairs) -> None:
        self._ml.set_ml_universe(pairs)

    @property
    def fail_open(self) -> bool:
        return self._ml.fail_open

    @fail_open.setter
    def fail_open(self, v: bool) -> None:
        self._ml.fail_open = bool(v)

    def native_candidate(self, ctx: StrategyContext) -> dict | None:
        """ML-G5 birinci gecis: 1s CORE kurulumlarinin ML'siz adayi (ctx.tf == '1h')."""
        return self._ml.native_candidate(ctx)

    # ------------------------------------------------------------------ protokol
    def validate_params(self, m: Mapping) -> Mapping:
        p = S.SignalParams.from_mapping(m)
        if p.trigger_tf not in self.info.allowed_trigger_tfs:
            raise ValueError(f"trigger_tf {p.trigger_tf!r} bu strateji icin izinli degil: {self.info.allowed_trigger_tfs}")
        return m

    def exit_policy(self) -> ExitPolicy | None:
        return None

    def compute(self, ctx: StrategyContext) -> pd.DataFrame:
        """Protokol uyumu: ctx.tf'nin CORE tablosu (1s: ML etiketli). Bilesik hesap `compute_tf` ile yapilir."""
        return self._ml.compute(ctx) if ctx.tf == "1h" else self.core_group_table(ctx)

    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        return self._ml.post_filter(row, ctx) if ctx.tf == "1h" else self.reentry_filter(row, ctx)

    # ------------------------------------------------------------------ hesap
    def _regime(self, pair: str, h4: pd.DataFrame, params: S.SignalParams) -> pd.DataFrame:
        rp = params.regime_params()
        last = h4.index[-1] if len(h4) else None
        hit = self._reg_cache.get(pair)
        if hit is not None and hit[0] == last and hit[1] == rp and hit[2] == len(h4):
            return hit[3]
        reg = AG.regime_series(h4, rp)                          # olu 4s mumlar (hisse/emtia hafta sonu) rejim girdisinden cikar; kriptoda eski yol
        self._reg_cache[pair] = (last, rp, len(h4), reg)
        return reg

    def _core(self, ctx: StrategyContext) -> pd.DataFrame:
        """Ortak compute_signals tablosu (cift, D, tf basina bir kez; yalniz son anahtar tutulur - bellek siniri)."""
        key = (ctx.pair, ctx.D, ctx.tf)
        if self._core_key == key and self._core_val is not None:
            return self._core_val
        params = S.SignalParams.from_mapping(ctx.params)
        trig = ctx.bars[ctx.tf]
        h4 = ctx.bars["4h"]
        reg = self._regime(ctx.pair, h4, params)
        # olu (hacim 0, o=h=l=c) mumlar gosterge girdisinden cikarilir; `core` tam izgarada, `core_c` yalniz dolu satirlarda (kurulumlar icin)
        core, core_c, trig_c = AG.core_signals(trig, reg, params)
        self._core_key, self._core_val, self._core_c = key, core, (core_c, trig_c)
        return core

    def _core_compact(self, ctx: StrategyContext) -> pd.DataFrame:
        """Kurulumlarin gordugu ortak tablo: olu mum yoksa `_core` ile ayni; varsa yalniz dolu satirlar (kurulum girdisi `trig_c`)."""
        self._core(ctx)
        return self._core_c[0]                                  # type: ignore[index]

    def core_group_table(self, ctx: StrategyContext) -> pd.DataFrame:
        setups = tuple(m.SETUP for m in self.arms_at(ctx.tf) if getattr(m, "CORE", False))
        return mask_to_setups(self._core(ctx), setups)

    def compute_tf(self, ctx: StrategyContext, *, force_core: bool = False, skip=(), on_error=None,
                   on_ok=None) -> dict[str, pd.DataFrame]:
        """ctx.tf kapandi: {anahtar: aday tablosu}. `core` = CORE kurulumlarin birlesik tablosu (1s'de ML puani dahil);
        digerleri kurulum koduyla. `force_core`: acik pozisyonun cikis baglami icin tablo gerekir (kurulum olmasa da).
        Karantina kancalari (arm_quarantine.py): `skip` anahtarlar hesaplanmaz (acik pozisyon icin zorunlu `core` HARIC: tablo
        yine hesaplanir, aday uretimini cagiran keser); `on_error(key, exc)` yalniz strateji kod hatasinda (errors.is_strategy_error)
        cagrilir ve anahtar atlanir, diger hatalar yukselir; `on_ok(key)` basarili hesapta. Kanca yoksa eski davranis."""
        from ..errors import is_strategy_error
        out: dict[str, pd.DataFrame] = {}
        arms = self.arms_at(ctx.tf)

        def run(key: str, fn) -> None:
            try:
                out[key] = fn()
            except Exception as e:  # noqa: BLE001
                if on_error is None or not is_strategy_error(e):
                    raise
                on_error(key, e)
                return
            if on_ok is not None:
                on_ok(key)

        if (force_core or any(getattr(m, "CORE", False) for m in arms)) and (CORE_KEY not in skip or force_core):
            run(CORE_KEY, lambda: self.compute(ctx))
        setups = [m for m in arms if not getattr(m, "CORE", False) and m.SETUP not in skip]
        if not setups:                                           # kurulum yoksa barlara dokunma (eski davranis)
            return out
        full = ctx.bars[ctx.tf]
        keep = AG.active_mask(full)                              # None: olu mum yok (kripto) -> eski yol, kurulum girdisi/ciktisi degismez
        trig_a = full if keep is None else full[keep]
        for m in setups:
            inp = ArmInput(pair=ctx.pair, tf=ctx.tf, D=ctx.D, trig=trig_a, h4=ctx.bars["4h"],
                           params=S.SignalParams.from_mapping(ctx.params), core_fn=lambda c=ctx: self._core_compact(c))
            if keep is None:
                run(m.SETUP, lambda m=m, inp=inp: m.compute(inp))
            else:
                # kurulum yalniz dolu mumlarda calisir, tablo tam izgaraya genisler (olu satirlarda aday yok: karar mumu oluysa
                # son satir aday degildir; yalniz-son-bar kurulumlarinin (M1/DL1/HB1) bayat dolu bardaki adayi gecmis satirda kalir)
                run(m.SETUP, lambda m=m, inp=inp: AG.expand_rows(m.compute(inp), full.index, keep, AG.CARRY_SIGNAL))
        return out

    def filter_row(self, key: str, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        """Son satir sonrasi suzgeci: CORE 1s'de ML + ayni-mum yasagi; digerlerinde yalniz ayni-mum yasagi."""
        if key == CORE_KEY:
            return self.post_filter(row, ctx)
        return self.reentry_filter(row, ctx)

    def reentry_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        """Aynı mum yasagi (spec 3): kurulumun KENDI zaman dilimiyle; stop/trail_stop cikisindan sonra ayni barda yeniden giris yok."""
        if not (self.block_same_bar_reentry and ctx.last_exit is not None and bool(row["signal"])):
            return row
        ts, reason = ctx.last_exit
        bar_open = ctx.D - arm_tf_delta(ctx.tf)
        if reason in _REENTRY_BLOCK and bar_open <= ts < ctx.D:
            r = row.copy()
            r["signal"] = False
            r["skip_reason"] = None
            r["reasons"] = "v1b:same_bar_reentry|" + str(row["reasons"])
            self.counters["shadow_reentry"] += 1
            return r
        return row


def make_lab_ml() -> PriceActionLab:
    return PriceActionLab(DEFAULT_ARMS)
