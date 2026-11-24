"""ML-G5: r02/r03 v2 ozelliklerinin MOTOR (canli/paper) tarafi -- egitimle AYNI kod (`ml_features_v2.feature_frame_v2`).

Saf: dosya/ag/saat yok. Motor `bars_fn` / `funding_fn` verir; bu sinif yalniz motorun ELINDE tuttugu mumlari (cift basina
son WINDOW_1H_V2 kapanmis 1s mum) `feature_frame_v2`ye verir. Egitim yolu tum gecmisi verir; esitlik (1e-9) testle sabitlenir
(`tests/ml/test_g5_parity.py`). Bayrak: motor yapilandirmasi `ml_features` (varsayilan "v1" = hicbir sey degismez).

Bellek maliyeti (belgeli): 10 cift x 5000 mum x 5 sutun x 8 bayt ~ 2 MB (+ ayni boyutta gecici kopyalar; her aday mumunda
`feature_frame_v2` pencere uzerinde ~birkac yuz ms). 200 gunluk 1g baglam icin 4800 1s mum gerekir (24 x 200); 5000 = pay.

Iki gecisli ayni-mum sayimi: `features_for_bar` TUM yerel adaylari (10 cift, iki yon, alinmis/alinmamis) bir kerede alir;
`f_same_bar_signals` bu listedeki ayni-ts aday sayisidir (feature_frame_v2 icinde cands.groupby(ts)).

G5 mentor duzeltmeleri: (1) `check_history` BTC/ETH/aday ciftleri icin 200 gunluk pencerede delik YOK ve son tutulan mum D-1s olmali
(aksi HistoryGap < HistoryShort -> aday puansiz); diger ciftlerde (genislik/siralama) delik `ml_v2_ctx_gaps` sayacina yazilir;
(2) artimli onbellek gec doldurulan mumlari gormez: gecmis kontrolu basarisizsa TAM yeniden yukleme, ayrica UTC gunde bir kez tam
yukleme; (3) BAYAT FONLAMA (yalniz r02): ts'den onceki en yeni olay 9 saatten eskiyse f_funding_* NaN + `ml_v2_funding_stale`
sayaci -- ayni kural egitimdeki feature_frame_v2'de (bkz. onun docstring'i); (4b) features_for_bar: tutulan en son mum + 1s <= D.

Kapsam disi (mentor 3.2.1-1: r02 tam olarak R02_FEATURE_NAMES): acik aday sayisi, son cikistan bu yana mum sayisi, f_eth_vol_1d
ozellik listesine EKLENMEZ."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from collections import Counter
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .arm_time import strip_dead
from .ml_features import BAR, BTC, ETH
from .ml_features_v2 import LOOKBACK_1D_DAYS, R02_FEATURE_NAMES, R03_FEATURE_NAMES, RECIPES, feature_frame_v2

__all__ = ["SETUP_BASE_FEATURES", "setup_feature_dict", "setup_feature_vector", "guess_asset_class", "WINDOW_1H_V2", "MIN_1H_BARS", "RECIPE_NAMES", "LiveContextV2", "BarFeatures", "HistoryShort", "HistoryGap", "internal_key"]

MIN_1H_BARS = 24 * LOOKBACK_1D_DAYS      # 4800: 200 gunluk 1g baglam
WINDOW_1H_V2 = 5000                      # motorun cift basina tuttugu 1s mum (4800 + ~8 gun pay)
FUNDING_LOOKBACK = timedelta(days=10)    # son fonlama olayi icin geri bakis (8s aralik; bosluklara dayanikli)
RECIPE_NAMES = {"r02": tuple(R02_FEATURE_NAMES), "r03": tuple(R03_FEATURE_NAMES)}


class HistoryShort(RuntimeError):
    """Motorun elindeki 1s gecmis 200 gunluk baglam icin yetmiyor (canli ozellikler egitimdekilerle ayni olmazdi)."""


class HistoryGap(HistoryShort):
    """Elde tutulan 1s gecmiste delik var ya da son mum D-1s degil (egitimdeki tam pencereyle ayni olmazdi)."""


def internal_key(pair: str) -> str:
    """Motor 'SOL/USDT' -> egitim 'SOL/USDT:USDT'."""
    s = pair.strip().upper()
    return s if ":" in s else s + ":USDT"


@dataclass(frozen=True)
class BarFeatures:
    """Bir karar mumu icin hesaplanmis ozellikler: rows[motor_cifti] = {ozellik: deger}; hata varsa error dolu."""
    D: datetime
    recipe: str
    rows: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    error: str | None = None


BarsFn = Callable[[str, datetime, int], pd.DataFrame]          # (motor cifti, D, n) -> 1s OHLCV (indeks = acilis, UTC)
FundingFn = Callable[[str, datetime, datetime], "pd.DataFrame | None"]   # (cift, bas, bit) -> indeks=olay zamani, 'funding_rate'


class LiveContextV2:
    def __init__(self, recipe: str, pairs: Sequence[str], bars_fn: BarsFn, funding_fn: FundingFn | None = None,
                 *, window: int = WINDOW_1H_V2) -> None:
        if recipe not in RECIPES:
            raise ValueError(f"recipe {RECIPES} icinde olmali: {recipe!r}")
        if window < MIN_1H_BARS:
            raise ValueError(f"window >= {MIN_1H_BARS} olmali")
        self.recipe = recipe
        self.names = RECIPE_NAMES[recipe]
        self.pairs = list(pairs)
        self._key = {p: internal_key(p) for p in self.pairs}
        if BTC not in self._key.values() or ETH not in self._key.values():
            raise ValueError("pairs BTC ve ETH icermeli")
        self.bars_fn, self.funding_fn, self.window = bars_fn, funding_fn, int(window)
        self._held: dict[str, pd.DataFrame] = {}
        self._full_day: pd.Timestamp | None = None     # son tam yuklemenin UTC gunu (gunde bir kez tam yukleme)
        self.counters: Counter = Counter()             # ml_v2_ctx_gaps, ml_v2_funding_stale, ml_v2_full_reloads

    # ------------------------------------------------------------------ bellek
    def held_rows(self) -> int:
        return sum(len(d) for d in self._held.values())

    def memory_bytes(self) -> int:
        return int(sum(d.memory_usage(deep=False).sum() for d in self._held.values()))

    # ------------------------------------------------------------------ mum penceresi (artimli)
    def _norm(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        if df.index.tz is None:
            df = df.tz_localize("UTC")
        return df.sort_index()

    def refresh(self, D: datetime, *, force_full: bool = False) -> None:
        """Her cift icin D'ye kadar KAPANMIS son `window` 1s mum. Ilk cagri tam yukler (baslangic yuklemesi);
        sonrakiler yalniz yeni mumlari (+24 mum ust uste binme: dolan/duzelen mumlar) ceker. Tam yukleme: ilk cagri, `force_full`
        (gecmis kontrolu basarisiz) ve UTC gunde bir kez (24 mumdan eski gec doldurmalar artimli yolda gorulmez)."""
        D = pd.Timestamp(D).tz_convert("UTC") if pd.Timestamp(D).tzinfo else pd.Timestamp(D, tz="UTC")
        day = D.floor("1D")
        if force_full or self._full_day is None or day != self._full_day:
            self._held = {}
            self._full_day = day
            if force_full:
                self.counters["ml_v2_full_reloads"] += 1
        for p in self.pairs:
            held = self._held.get(p)
            full = held is None or len(held) == 0
            if not full:
                last_close = held.index[-1] + BAR
                k = int((D - last_close) / BAR)
                if D < last_close or k >= self.window // 2:
                    full = True
                    held = None
            if full:
                new = self._norm(self.bars_fn(p, D.to_pydatetime(), self.window))
                self._held[p] = new.iloc[-self.window:]
            else:
                tail = self._norm(self.bars_fn(p, D.to_pydatetime(), k + 24))
                m = pd.concat([held[~held.index.isin(tail.index)], tail]).sort_index()
                self._held[p] = m.iloc[-self.window:]

    def _problems(self, D: datetime, pairs: Sequence[str]) -> tuple[list[str], list[str]]:
        """(siki, gevsek) sorun listeleri. Siki = BTC, ETH ve aday ciftleri (HistoryShort/HistoryGap); gevsek = diger ciftler
        (genislik/siralama girdisi; yalniz sayilir). Kural: ilk mum <= floor(D,1g)-199g, SON tutulan mum == D-1s, ve
        [floor(D,1g)-199g, D) araliginda delik yok (ardisik fark 1s)."""
        Dt = pd.Timestamp(D).tz_convert("UTC") if pd.Timestamp(D).tzinfo else pd.Timestamp(D, tz="UTC")
        need_from = Dt.floor("1D") - pd.Timedelta(days=LOOKBACK_1D_DAYS - 1)
        strict = {BTC, ETH, *(self._key[x] for x in pairs)}
        hard: list[str] = []
        soft: list[str] = []
        for raw, key in self._key.items():
            h = self._held.get(raw)
            out = hard if key in strict else soft
            if h is None or len(h) == 0:
                out.append(f"{raw}: 1s gecmis yok; >= {MIN_1H_BARS} mum gerekli")
                continue
            if h.index[0] > need_from:
                out.append(f"HistoryShort {raw}: 1s gecmis {need_from} oncesine uzanmiyor (ilk mum: {h.index[0]}); >= {MIN_1H_BARS} mum gerekli")
                continue
            if h.index[-1] != Dt - BAR:
                out.append(f"HistoryGap {raw}: son tutulan mum {h.index[-1]} != D-1s ({Dt - BAR})")
                continue
            w = h.index[h.index >= need_from]
            if len(w) > 1 and not bool(((w[1:] - w[:-1]) == BAR).all()):
                out.append(f"HistoryGap {raw}: [{need_from}, {Dt}) aralaginda 1s mum deligi var")
        return hard, soft

    def check_history(self, D: datetime, pairs: Sequence[str]) -> None:
        """BTC/ETH ve verilen ciftler icin [floor(D,1g)-199g, D) mumlarinin ELDE, SON mumun D-1s ve araliksiz oldugunu dogrular
        (aksi HistoryShort/HistoryGap). Diger ciftlerdeki sorunlar `ml_v2_ctx_gaps` sayacina yazilir (hata degil)."""
        hard, soft = self._problems(D, pairs)
        self.counters["ml_v2_ctx_gaps"] += len(soft)
        if hard:
            cls = HistoryShort if any(x.startswith("HistoryShort") or ": 1s gecmis yok" in x for x in hard) else HistoryGap
            raise cls("; ".join(hard))

    # ------------------------------------------------------------------ fonlama
    def _funding(self, D: datetime) -> dict[str, pd.DataFrame] | None:
        if self.funding_fn is None:
            return None
        out = {}
        for p in self.pairs:
            f = self.funding_fn(p, D - FUNDING_LOOKBACK, D)
            if f is not None and len(f):
                out[self._key[p]] = f
        return out

    # ------------------------------------------------------------------ ozellikler
    def features_for_bar(self, D: datetime, cands: pd.DataFrame) -> BarFeatures:
        """cands: motor cifti `pair`, `side`, `planned_entry`, `planned_stop` (HEPSI yerel adaylar; ikinci gecis).
        Bos cands -> bos rows (hesap yok)."""
        D = pd.Timestamp(D).tz_convert("UTC") if pd.Timestamp(D).tzinfo else pd.Timestamp(D, tz="UTC")
        if len(cands) == 0:
            return BarFeatures(D=D.to_pydatetime(), recipe=self.recipe)
        self.refresh(D.to_pydatetime())
        if self._problems(D.to_pydatetime(), list(cands["pair"]))[0]:       # gec doldurma/delik olabilir: tam yeniden yukleme, sonra bir kez daha
            self.refresh(D.to_pydatetime(), force_full=True)
        self.check_history(D.to_pydatetime(), list(cands["pair"]))
        for p, h in self._held.items():                                      # nedensellik: kapanisi D'yi asan mum tutulmaz
            if len(h) and h.index[-1] + BAR > D:
                raise AssertionError(f"{p}: tutulan son mum {h.index[-1]} + 1s > D={D}")
        # seansli enstruman: olu (hacim 0, o=h=l=c) 1s mumlar ozellik girdisinden cikar (v1 ile ayni, price_action_v1_ml); kriptoda ayni nesne.
        # Tutulan pencere (_held) ham kalir: delik/gecmis denetimleri takvim izgarasinda calisir.
        frames = {self._key[p]: strip_dead(d) for p, d in self._held.items() if len(d)}
        c = pd.DataFrame({
            "ts": [D] * len(cands), "pair": [self._key[p] for p in cands["pair"]], "side": cands["side"].to_numpy(),
            "planned_entry": cands["planned_entry"].to_numpy(float), "planned_stop": cands["planned_stop"].to_numpy(float)})
        ff = feature_frame_v2(frames, c, funding=self._funding(D.to_pydatetime()), recipe=self.recipe)
        self.counters["ml_v2_funding_stale"] += int(ff.attrs.get("funding_stale", 0))
        rows = {}
        for i, p in enumerate(cands["pair"]):
            rows[p] = {n: float(ff[n].iloc[i]) for n in self.names}
        return BarFeatures(D=D.to_pydatetime(), recipe=self.recipe, rows=rows)


def funding_frame_from_points(points) -> pd.DataFrame | None:
    """Motor FundingPoint listesi -> feature_frame_v2 girdisi (olay zamani en yakin saate yuvarlanir; G3 ile ayni)."""
    if not points:
        return None
    idx = pd.DatetimeIndex([pd.Timestamp(p.ts).tz_convert("UTC") if pd.Timestamp(p.ts).tzinfo else pd.Timestamp(p.ts, tz="UTC")
                            for p in points]).round("1h")
    return pd.DataFrame({"funding_rate": np.array([float(p.rate) for p in points])}, index=idx)


# ---------------------------------------------------------------------------------------------------------------------
# DD-12 WP-10: kurulum (arm_id) bazli suzgec ozellikleri. EGITIM VE MOTOR AYNI FONKSIYONU kullanir (parite). Yalniz KARAR ANINDA
# bilinenler; islem sonrasi not etiketleri / sonuc yok. trader_core ML kutuphanesi ice aktarmaz (yalniz stdlib).
# ---------------------------------------------------------------------------------------------------------------------
_REGIMES = ("trend_up", "trend_down", "range", "volatile", "unclear")
_SESSIONS = ("open", "closed", "weekend")
_CLASSES = ("kripto", "hisse", "emtia")
_COMMODITY_BASES = frozenset({"XAU", "XAG", "XPT", "XPD", "WTI", "BRENT", "CL", "NG", "HG", "OIL", "GOLD", "SILVER", "COPPER", "NATGAS"})
SETUP_BASE_FEATURES = tuple(
    ["atr_ratio", "stop_dist_pct", "rr_plan", "rh_touches", "rl_touches", "side_long"]
    + [f"regime_{r}" for r in _REGIMES] + [f"sess_{s}" for s in _SESSIONS] + [f"cls_{c}" for c in _CLASSES])


def guess_asset_class(pair: str) -> str:
    """Motor `arm_guard.asset_class(pair, clusters)` verebiliyorsa o kullanilir; bu yalniz kume bilgisi olmayan egitim yolu icin yedek."""
    s = str(pair).upper()
    base = s.split("/")[0].split(":")[0]
    if base in _COMMODITY_BASES:
        return "emtia"
    if "USDT" in s or "USDC" in s or "BUSD" in s:
        return "kripto"
    return "hisse"


def _fnum(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v if np.isfinite(v) else float("nan")


_DUYGU_HABER_ON = ("duygu", "haber", "fng", "fear", "greed", "etiket_atlardi")      # 21 Kasim 2026 karari: duygu/haber hicbir ML ozelligi degil


def _etiket_alani(k) -> bool:
    k = str(k).lower()
    return any(k == a or k.startswith(a + "_") for a in _DUYGU_HABER_ON)


def setup_feature_dict(*, side: str, regime: str, atr_ratio, session_tag, asset_class: str | None, pair: str | None = None,
                       planned_entry, planned_stop, planned_target=None, rh_touches=0, rl_touches=0,
                       lesson_ids: Sequence[str] | None = None, features: Mapping | None = None) -> dict[str, float]:
    """Bir aday icin ozellik sozlugu: sabit taban + `f_<anahtar>` (kararin sayisal `features` alanlari) + `ders:<kimlik>` (0/1).
    Eksik/bilinmeyen -> NaN (taban) ya da 0 (kategori ve ders). `session_tag` None -> hicbir sess_* yanmaz."""
    e, st = _fnum(planned_entry), _fnum(planned_stop)
    risk = abs(e - st)
    tgt = _fnum(planned_target)
    cls = asset_class or (guess_asset_class(pair) if pair else None)
    d: dict[str, float] = {
        "atr_ratio": _fnum(atr_ratio),
        "stop_dist_pct": risk / e if e > 0 and np.isfinite(risk) else float("nan"),
        "rr_plan": abs(tgt - e) / risk if risk > 0 and np.isfinite(tgt) else float("nan"),
        "rh_touches": _fnum(rh_touches), "rl_touches": _fnum(rl_touches),
        "side_long": 1.0 if str(side).lower() == "long" else 0.0}
    for r in _REGIMES:
        d[f"regime_{r}"] = 1.0 if regime == r else 0.0
    for s in _SESSIONS:
        d[f"sess_{s}"] = 1.0 if session_tag == s else 0.0
    for c in _CLASSES:
        d[f"cls_{c}"] = 1.0 if cls == c else 0.0
    for k, v in (features or {}).items():
        if isinstance(v, bool) or not isinstance(v, (int, float)) or str(k).startswith("ct_") or _etiket_alani(k):
            continue                    # eski kayitlardaki ct_* ve duygu/haber (Fear&Greed, haber tonu) alanlari ozellik olmaz (eski paket eksik ozelligi doldurur)
        d[f"f_{k}"] = _fnum(v)
    for lid in (lesson_ids or ()):
        d[f"ders:{lid}"] = 1.0
    return d


def setup_feature_vector(names: Sequence[str], fdict: Mapping[str, float]) -> np.ndarray:
    """Paket ozellik sirasina gore vektor. Eksik `ders:*` -> 0 (ders eslesmedi); diger eksikler NaN (modelin `fill` degeri)."""
    out = np.empty(len(names), dtype=np.float64)
    for i, n in enumerate(names):
        v = fdict.get(n)
        out[i] = (0.0 if n.startswith("ders:") else float("nan")) if v is None else v
    return out
