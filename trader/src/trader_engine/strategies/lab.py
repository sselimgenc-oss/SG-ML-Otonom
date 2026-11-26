"""PriceActionLab (DD-12 WP-11; `price_action_lab_ml`): cok kurulumlu (arm) bilesik strateji.

Kurulum = `strategies/arms/<kod>.py` dosyasi; kimlik `arm_id = <KURULUM>@<zaman dilimi>` (15m / 1h / 4h / 1d). Yapilandirma
`arms` listesi hangi kurulumun hangi zaman diliminde calisacagini soyler; kurulumlar paket klasorunden adla bulunur
(`arms.find_arm`), bu dosyada ya da kayit defterinde degisiklik gerekmez.

Karar adimi 15 dakikadir (`decision_tf`); her adimda YALNIZ kapanan zaman dilimlerinin kurulumlari hesaplanir (D-T16).
1g bar = UTC gununun 6 x 4s'i (bars.aggregate_4h_to_1d). Ortak `compute_signals` tablosu zaman dilimi basina bir kez hesaplanir
ve T1/R1 gibi CORE kurulumlar bu tablodan satir secer. Strateji yalniz aday uretir: boyut, emir, defter, kapi onun isi degildir."""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime

import pandas as pd

from trader_core import signals as S

from .. import arm_guard as AG
from ..bars import (ARM_TFS, GIRIS_TFS, MIN_CONTIG_ARM, STARTUP_BARS_ARM, WINDOW_ARM, arm_tf_delta)
from .arms import ArmError, ArmInput, find_arm, make_arm_id, mask_to_setups, parse_arm_id
from .base import ExitPolicy, StrategyContext, StrategyError, StrategyInfo
from .price_action_v1 import _REENTRY_BLOCK, _param_specs

log = logging.getLogger("engine.strategy.lab")

NAME = "price_action_lab_ml"
VERSION = "1.0-lab1"
DECISION_TF = "15m"
DEFAULT_ARMS = ("T1@1h", "R1@1h")            # D-T18: price_action_v1_full ile esdeger varsayilan
CORE_KEY = "core"                             # CORE kurulumlarin birlesik tablosunun anahtari (digerleri kurulum kodu)


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
            if tf not in GIRIS_TFS:
                raise StrategyError("unknown_arm", f"@{tf} arms rejected: 15m giris kolu yok (sahip karari): {aid}")
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

    @property
    def arm_ids(self) -> tuple[str, ...]:
        return self._arm_ids

    def arms_at(self, tf: str) -> list:
        return self._enabled.get(tf, [])

    def tfs(self) -> tuple[str, ...]:
        return tuple(tf for tf in ARM_TFS if self._enabled.get(tf))

    def label(self) -> str:
        return f"strategy:{self.info.name}@{self.info.version}"

    # ------------------------------------------------------------------ protokol
    def validate_params(self, m: Mapping) -> Mapping:
        p = S.SignalParams.from_mapping(m)
        if p.trigger_tf not in self.info.allowed_trigger_tfs:
            raise ValueError(f"trigger_tf {p.trigger_tf!r} bu strateji icin izinli degil: {self.info.allowed_trigger_tfs}")
        return m

    def exit_policy(self) -> ExitPolicy | None:
        return None

    def compute(self, ctx: StrategyContext) -> pd.DataFrame:
        """Protokol uyumu: ctx.tf'nin CORE tablosu. Bilesik hesap `compute_tf` ile yapilir."""
        return self.core_group_table(ctx)

    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series:
        return self.reentry_filter(row, ctx)

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

    def compute_tf(self, ctx: StrategyContext, *, force_core: bool = False, on_error=None) -> dict[str, pd.DataFrame]:
        """ctx.tf kapandi: {anahtar: aday tablosu}. `core` = CORE kurulumlarin birlesik tablosu (1s'de ML puani dahil);
        digerleri kurulum koduyla. `force_core`: acik pozisyonun cikis baglami icin tablo gerekir (kurulum olmasa da).
        Kod hatasi yalitimi: `on_error(key, exc)` yalniz strateji kod hatasinda (errors.is_strategy_error) cagrilir ve o anahtar
        bu tur atlanir (tur dusmez); diger hatalar yukselir. Kanca yoksa eski davranis (hata yukselir)."""
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

        if force_core or any(getattr(m, "CORE", False) for m in arms):
            run(CORE_KEY, lambda: self.compute(ctx))
        setups = [m for m in arms if not getattr(m, "CORE", False)]
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
                # son satir aday degildir; yalniz-son-bar kurulumlarinin bayat dolu bardaki adayi gecmis satirda kalir)
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
