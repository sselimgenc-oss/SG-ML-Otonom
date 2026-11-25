"""CHECK 1 - canli (paper/live) ile geri test (precomputed) gosterge/sinyal paritesi.

Iki yol (ayni strateji kodu, farkli pencereleme):
  canli      : `StoreSource` (market.sqlite) + `WindowedSignalSource` (tekli, 1s) / `MultiArmSignalSource` (kurulumlar; her karar adiminda
               son WINDOW_ARM mum kesiti, yalniz kapanmis barlar)
  geri test  : `HistoricalSource` (feather) + `PrecomputedSignalSource` (tum gecmis tek hesap) ve kurulum tablolari (`lab.compute_tf`
               tum gecmis uzerinde; `--env paper` geri testi ise zaten `MultiArmSignalSource`un ta kendisini kullanir)
Sentetik, tohumlu, cok enstrumanli: 2 kripto, seansli hisse (barsiz bosluk), seansli hisse (olu mumlu), emtia (hafta sonu olu mumlu);
15m/1s/4s/1g. Uzun (600+ bar ustu, pencereleri asan) ve KISA (isinma siniri) gecmis. Esik: 1e-9 (bagil/mutlak)."""
from __future__ import annotations

import dataclasses
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import gosterge_support as GS
from trader_core import ledger as L
from trader_core import signals as S
from trader_engine.bars import WINDOW_ARM, aggregate_4h_to_1d, arm_tf_delta, to_ms
from trader_engine.marketdata.sources import HistoricalSource, StoreSource
from trader_engine.precomputed import PrecomputedSignalSource
from trader_engine.strategies.base import StrategyContext
from trader_engine.strategies.lab import PriceActionLab
from trader_engine.strategy_runner import MultiArmSignalSource, SignalRow, WindowedSignalSource

UTC = timezone.utc
START = datetime(2026, 1, 5, tzinfo=UTC)          # Pazartesi
FAMILIES = ("T1", "R1", "TF1", "B1", "H2", "S1", "F1", "M1")
TFS = ("15m", "1h", "4h", "1d")
ARMS = [f"{s}@{t}" for s in FAMILIES for t in TFS]
WARM = {"15m": 4800, "1h": 1200, "4h": 300, "1d": 50}      # tetik tf barinda: 4s isinma (300 x 4s) en siki kosul
TOL = 1e-9
CONT = ("planned_entry", "planned_stop", "planned_target", "rr", "stop_dist_atr", "atr_tf", "atr_4h", "atr_ratio", "rh", "rl",
        "ema_value", "body_ratio", "wick_ratio", "edge_dist_atr")
DISC = ("signal", "setup", "side", "skip_reason", "regime", "rh_touches", "rl_touches", "pullback_ema", "reasons")
CRYPTO = ("BTC/USDT", "SOL/USDT")
SESSION_FLAT = ("TSLA/USDT", "XAU/USDT")           # olu mumlu seri (izgara tam)
STOCK_GAP = "NVDA/USDT"                            # seans disi bar YOK (izgara delikli)


def _params() -> dict:
    p = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    p["trigger_tf"] = "1h"
    return p


def _series(days: int, only: tuple[str, ...] | None = None) -> dict[str, pd.DataFrame]:
    n = days * 96
    full = _series_all(days, n)
    return full if only is None else {k: v for k, v in full.items() if k in only}


def _series_all(days: int, n: int) -> dict[str, pd.DataFrame]:
    return {"BTC/USDT": GS.make_15m(1, n, START, 100.0), "SOL/USDT": GS.make_15m(5, n, START, 60.0),
            "TSLA/USDT": GS.make_stock_15m(7, days, START, 200.0, flat=True),
            "XAU/USDT": GS.make_commodity_15m(9, days, START, 2000.0, flat=True),
            STOCK_GAP: GS.make_stock_15m(3, days, START, 150.0, flat=False)}


@pytest.fixture(scope="module")
def uzun(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("uzun"), 330)       # 1g penceresi (250 gun) asilir; 15m/1s/4s pencereleri de asilir


@pytest.fixture(scope="module")
def kisa(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("kisa"), 82)        # isinma siniri: tum pencereler gecmisin tamamini kapsar


@pytest.fixture(scope="module")
def cok_uzun(tmp_path_factory):
    """1g penceresini (600 gun; seansli enstrumanda 600 DOLU gun ~ 840 takvim gunu) asan gecmis: yalniz 1g testleri icin (3 cift)."""
    return _build(tmp_path_factory.mktemp("cok_uzun"), 900, only=("SOL/USDT", "TSLA/USDT", "XAU/USDT"))


def _build(tmp, days, only=None):
    series = _series(days, only)
    end = START + timedelta(days=days)
    GS.write_store(tmp / "market.sqlite", series, end + timedelta(days=1))
    GS.write_feather(tmp / "hist", series)
    return dict(series=series, end=end, days=days, live=StoreSource(tmp / "market.sqlite"), hist=HistoricalSource(tmp / "hist"))


def _close(a, b, tol=TOL) -> bool:
    a = float("nan") if a is None else float(a)
    b = float("nan") if b is None else float(b)
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= tol * max(1.0, abs(b))


def _row_diffs(a: SignalRow, b: SignalRow, tol=TOL, skip=()) -> list[str]:
    out = []
    for c in DISC:
        x, y = getattr(a, c), getattr(b, c)
        if x != y and not (x is None and y is None):
            out.append(f"{c}: {x!r} != {y!r}")
    for c in CONT:
        if c not in skip and not _close(getattr(a, c), getattr(b, c), tol):
            out.append(f"{c}: {getattr(a, c)!r} != {getattr(b, c)!r}")
    return out


# --------------------------------------------------------------------------------------------- 1) tekli 1s: Windowed == Precomputed
def _lab11():
    return PriceActionLab(("T1@1h", "R1@1h"))


def _d_samples(trig_idx: pd.DatetimeIndex, tf_delta: timedelta, cand_pos, warm: int, n_cand=6, n_rand=4, seed=3):
    rng = np.random.default_rng(seed)
    cand = [int(i) for i in cand_pos if i >= warm]
    pick = list(rng.choice(cand, min(n_cand, len(cand)), replace=False)) if cand else []
    pick += [int(i) for i in rng.choice(np.arange(warm, len(trig_idx)), n_rand, replace=False)]
    pick += [len(trig_idx) - 1]
    return sorted({(trig_idx[i] + tf_delta).to_pydatetime() for i in pick})


@pytest.mark.parametrize("hist", ["uzun", "kisa"])
@pytest.mark.parametrize("pair", CRYPTO + SESSION_FLAT)
def test_tekli_1s_windowed_precomputed_ayni_satir(request, hist, pair):
    """Paranoid kontrolunun testi: 1s tekli yol; canli pencere kesiti (D'ye kesilmis) == tum gecmis tablosu. vol_tahmin yalniz canlidadir."""
    h = request.getfixturevalue(hist)
    params = _params()
    pre = PrecomputedSignalSource(h["hist"], _lab11(), pairs=[pair], tf="1h", params=params, version_id=1, end=h["end"], strict=True)
    win = WindowedSignalSource(h["live"], _lab11(), strict=True)
    tbl = pre.frame_table(pair, h["end"])
    ds = _d_samples(tbl.index, timedelta(hours=1), np.flatnonzero(tbl["signal"].to_numpy()), WARM["1h"])
    n_ok = 0
    for D in ds:
        fw, fp = win.frame(pair, D, params, 1), pre.frame(pair, D, params, 1)
        assert fw.status == fp.status, (pair, D, fw.status, fp.status)
        if fw.status == "ok":
            n_ok += 1
            d = _row_diffs(fw.last, fp.last, skip=())
            assert d == [], (pair, D, d)
    assert n_ok >= len(ds) - 1


@pytest.mark.parametrize("pair", CRYPTO + SESSION_FLAT)
def test_isinma_siniri_ayni_bar_ayni_durum(kisa, pair):
    """Kisa gecmis: isinma baslangic dilimi etrafinda iki yol AYNI durumu (no_history -> ok) ve ayni degeri verir."""
    h = kisa
    params = _params()
    pre = PrecomputedSignalSource(h["hist"], _lab11(), pairs=[pair], tf="1h", params=params, version_id=1, end=h["end"], strict=True)
    win = WindowedSignalSource(h["live"], _lab11(), strict=True)
    idx = pre.frame_table(pair, h["end"]).index
    first_ok = None
    for i in range(1100, 1900, 7):
        D = (idx[i] + timedelta(hours=1)).to_pydatetime()
        fw, fp = win.frame(pair, D, params, 1), pre.frame(pair, D, params, 1)
        assert fw.status == fp.status, (i, fw.status, fp.status)
        if fw.status == "ok":
            first_ok = first_ok or i
            assert _row_diffs(fw.last, fp.last) == []
    assert first_ok is not None and first_ok > 1100            # onceki barlar no_history: isinma gercekten sinanmis


def test_delikli_hisse_ayni_veri_bosluk_durumu(uzun):
    """Seans disi barsiz hisse: iki yol da AYNI 'data_gap' verir (delik); sessiz doldurma yok."""
    h = uzun
    params = _params()
    pre = PrecomputedSignalSource(h["hist"], _lab11(), pairs=[STOCK_GAP], tf="1h", params=params, version_id=1, end=h["end"], strict=True)
    win = WindowedSignalSource(h["live"], _lab11(), strict=True)
    idx = pre.frame_table(STOCK_GAP, h["end"]).index
    for i in (1300, 1500, len(idx) - 5):
        D = (idx[i] + timedelta(hours=1)).to_pydatetime()
        fw, fp = win.frame(STOCK_GAP, D, params, 1), pre.frame(STOCK_GAP, D, params, 1)
        assert (fw.status, fw.detail) == (fp.status, fp.detail)
        assert fw.status in ("data_gap", "no_history")


# --------------------------------------------------------------------------------------------- 2) kurulumlar x zaman dilimleri
def _full_tables(view, lab, pair, tf, end):
    h4 = view.bars(pair, "4h", end, None)
    trig = h4 if tf == "4h" else (aggregate_4h_to_1d(h4) if tf == "1d" else view.bars(pair, tf, end, None))
    ctx = StrategyContext(pair=pair, D=end, tf=tf, params=_params(), bars={tf: trig, "4h": h4}, last_exit=None)
    return trig, lab.compute_tf(ctx)


def _live_rows(src, pair, D, params):
    fr = src.frame(pair, D, params, 1)
    rows = {}
    if fr.status == "ok":
        for f in (fr,) + tuple(fr.extras):
            if f.last is not None:
                rows[(f.last.tf, f.last.arm_id or "ctx")] = f.last
    return fr, rows


def _check_pair_tf(h, pair, tf, tol, n_cand=6, n_rand=3):
    end = h["end"]
    params = _params()
    trig, tabs = _full_tables(h["hist"], PriceActionLab(ARMS), pair, tf, end)
    cand = set()
    for k, t in tabs.items():
        cand |= set(np.flatnonzero(t["setup"].notna().to_numpy()).tolist())
    ds = _d_samples(trig.index, arm_tf_delta(tf), sorted(cand), WARM[tf], n_cand, n_rand)
    src = MultiArmSignalSource(h["live"], PriceActionLab(ARMS), strict=True, pairs=[pair])
    n_cmp = 0
    for D in ds:
        i = int(np.searchsorted(trig.index.tz_convert("UTC"), pd.Timestamp(D - arm_tf_delta(tf))))
        fr, rows = _live_rows(src, pair, D, params)
        if fr.status != "ok":
            pytest.fail(f"{pair} {tf} {D}: canli {fr.status} {fr.detail}")
        # M1 yalniz son barda puanlar: tum gecmis tablosunda yalniz son satirda anlamli (D == end)
        for key, t in tabs.items():
            if key == "M1" and D != end:
                continue
            rec = t.iloc[i]
            has = rec["setup"] is not None and pd.notna(rec["setup"])
            lr = rows.get((tf, f"{rec['setup']}@{tf}")) if has else None
            if has:
                assert lr is not None, (pair, tf, D, key, "canli satir yok", rec["signal"], rec["skip_reason"])
                n_cmp += 1
                srow = _to_signal_row(pair, trig.index[i], D, rec)
                assert _row_diffs(lr, srow, tol) == [], (pair, tf, D, key)
            else:
                assert not any(k[1].startswith(f"{key}@") for k in rows if k[0] == tf), (pair, tf, D, key, "canlida fazla aday")
    return n_cmp


def _to_signal_row(pair, open_ts, D, rec):
    from trader_engine.strategy_runner import _to_row
    return _to_row(pair, open_ts.to_pydatetime(), D, rec, 1)


@pytest.mark.parametrize("tf", ("15m", "1h", "4h"))
@pytest.mark.parametrize("pair", CRYPTO + SESSION_FLAT)
def test_kurulumlar_canli_pencere_eq_tum_gecmis_uzun(uzun, pair, tf):
    """8 kurulum ailesi (T1,R1,TF1,B1,H2,S1,F1,M1): canli pencere kesiti == tum gecmis tablosu (1e-9). 15m/1s/4s pencereleri asilir.
    Ayrik alanlar (signal/setup/side/skip_reason/regime/dokunus/neden) her durumda BIREBIR ayni olmak zorunda."""
    _check_pair_tf(uzun, pair, tf, TOL)


@pytest.mark.parametrize("pair", ("SOL/USDT", "TSLA/USDT", "XAU/USDT"))
def test_kurulumlar_canli_pencere_eq_tum_gecmis_1g(cok_uzun, pair):
    """1g: pencere 600 DOLU gun (WINDOW_ARM['1d']); gecmis 900 gun (hisse/emtia: 640-770 dolu gun) pencereyi ASAR. EMA(50) tohum farki
    (1-2/51)^600 ~ 4e-11 => tum alanlarda 1e-9 (eski 250 gun penceresinde ~3e-5 idi; bkz. test_gunluk_ema_tohum_siniri). Tum
    gecmis tablosu ile canli (MultiArmSignalSource) AYNI esik."""
    _check_pair_tf(cok_uzun, pair, "1d", TOL, n_cand=6, n_rand=8)


@pytest.mark.parametrize("tf", TFS)
@pytest.mark.parametrize("pair", CRYPTO + SESSION_FLAT)
def test_kurulumlar_canli_pencere_eq_tum_gecmis_kisa(kisa, pair, tf):
    """Kisa gecmis (82 gun; isinma sinirinda): pencere = tum gecmis -> tum zaman dilimlerinde 1e-9."""
    _check_pair_tf(kisa, pair, tf, TOL, n_cand=4, n_rand=2)


def test_aday_kapsami_her_ailede_en_az_bir_aday(uzun):
    """Testin anlamli olmasi: sentetik veri her kurulum ailesinden aday uretir (T1,R1,TF1,B1,H2,S1,F1 tum gecmis tablolarinda)."""
    seen = set()
    for pair in CRYPTO:
        for tf in ("1h", "15m"):
            _trig, tabs = _full_tables(uzun["hist"], PriceActionLab(ARMS), pair, tf, uzun["end"])
            seen |= {k for k, t in tabs.items() if k != "core" and bool(t["signal"].any())}
            if "core" in tabs:
                seen |= set(tabs["core"].loc[tabs["core"]["signal"], "setup"].dropna())
    assert {"T1", "R1", "TF1", "B1", "H2", "S1", "F1"} <= seen, seen


def test_gunluk_ema_tohum_siniri(cok_uzun):
    """Olculmus tohum etkisi: tum gecmis EMA tohumu pencere EMA'sindan farkli baslar. ESKI 250 gunluk pencerede EMA(50) icin
    (1-2/51)^250 ~ 5e-5 bagil (T1/R1 1g EMA(50) ozelligi ~ 3e-5); YENI 600 gunluk pencerede (1-2/51)^600 ~ 4e-11 < 1e-9. Hesap TF1 1g
    tablosundaki EMA(30)/ATR(14) sutunlari (atr_tf, ema_value) uzerindedir; EMA(50) icin dogrudan `indicators.ema` ile de dogrulanir."""
    pair, tf = "SOL/USDT", "1d"
    trig, tabs = _full_tables(cok_uzun["hist"], PriceActionLab(["TF1@1d"]), pair, tf, cok_uzun["end"])
    h4 = cok_uzun["hist"].bars(pair, "4h", cok_uzun["end"], None)

    def windowed(k):
        ctx = StrategyContext(pair=pair, D=cok_uzun["end"], tf=tf, params=_params(), bars={tf: trig.iloc[-k:], "4h": h4})
        return PriceActionLab(["TF1@1d"]).compute_tf(ctx)["TF1"]
    full = tabs["TF1"]["atr_tf"].to_numpy()[-1]
    d_old = abs(full - windowed(250)["atr_tf"].to_numpy()[-1]) / full
    d_new = abs(full - windowed(int(WINDOW_ARM["1d"]))["atr_tf"].to_numpy()[-1]) / full
    assert d_new < 1e-9 and d_new <= d_old
    from trader_core import indicators as I
    c = trig["close"]
    e_full = float(I.ema(c, 50).iloc[-1])
    e_old = abs(float(I.ema(c.iloc[-250:], 50).iloc[-1]) - e_full) / e_full
    e_new = abs(float(I.ema(c.iloc[-int(WINDOW_ARM["1d"]):], 50).iloc[-1]) - e_full) / e_full
    assert e_old > 1e-8 and e_new < 1e-9, (e_old, e_new)    # eski pencerede fark VAR (esik anlamli), yenide yok


# --------------------------------------------------------------------------------------------- 3) kapanmis bar kesimi (ileri bakma yok)
def test_kapanmis_bar_kesimi_gelecek_bar_etkisiz(uzun, tmp_path):
    """Karar anindan SONRA yazilan barlar canli sonucu degistirmez: D'ye kesilmis magaza ile tam magaza ayni satir/ozellik."""
    pair = "BTC/USDT"
    full = uzun["series"][pair]
    params = _params()
    for off_days in (200, 311):
        D = START + timedelta(days=off_days)                         # 00:00 UTC: 15m/1s/4s/1g hepsi kapanir
        cut = {pair: full[full.index + pd.Timedelta("15min") <= D]}
        db = tmp_path / f"cut{off_days}.sqlite"
        GS.write_store(db, cut, D)
        a = MultiArmSignalSource(StoreSource(db), PriceActionLab(ARMS), strict=True, pairs=[pair])
        b = MultiArmSignalSource(uzun["live"], PriceActionLab(ARMS), strict=True, pairs=[pair])
        fa, ra = _live_rows(a, pair, D, params)
        fb, rb = _live_rows(b, pair, D, params)
        assert fa.status == fb.status == "ok"
        assert set(ra) == set(rb)
        for k in ra:
            assert _row_diffs(ra[k], rb[k]) == [], (off_days, k)
        # tekli 1s: son kapanan bar D - 1s; D'den sonra baslayan bar yok
        wa, wb = WindowedSignalSource(StoreSource(db), _lab11(), strict=True), WindowedSignalSource(uzun["live"], _lab11(), strict=True)
        fa1, fb1 = wa.frame(pair, D, params, 1), wb.frame(pair, D, params, 1)
        assert fa1.status == fb1.status == "ok" and _row_diffs(fa1.last, fb1.last) == []
        assert fa1.last.bar_open_ts == D - timedelta(hours=1) and fa1.last.bar_close_ts == D


# --------------------------------------------------------------------------------------------- 4) 1g toplama (4s -> 1g)
@pytest.mark.parametrize("pair", ("BTC/USDT", "TSLA/USDT", "XAU/USDT"))
def test_1g_toplama_bagimsiz_15m_ile_ayni(uzun, pair):
    """aggregate_4h_to_1d: yalniz TAM 6 x 4s'li UTC gunu; OHLCV bagimsiz 15m -> 1D yeniden ornekleme ile 1e-9 ayni (canli ve geri test okuyucusu)."""
    s15 = uzun["series"][pair]
    ref = GS.resample(s15, "1D")
    cnt = s15.resample("1D")["open"].count()
    ref = ref[cnt.reindex(ref.index) == 96]                          # tam gun (96 x 15m)
    for src in (uzun["live"], uzun["hist"]):
        h4 = src.bars(pair, "4h", uzun["end"], None)
        agg = aggregate_4h_to_1d(h4)
        common = agg.index.intersection(ref.index)
        assert len(common) >= 300
        np.testing.assert_allclose(agg.loc[common, GS.COLS].to_numpy(), ref.loc[common, GS.COLS].to_numpy(), rtol=1e-9, atol=1e-9)
        assert set(agg.index) <= set(ref.index) | set(common)        # eksik/kismi gun 1g bar uretmez
        # D gun ortasinda: acik gun 1g'ye GIRMEZ (kapanis kesimi)
        mid = START + timedelta(days=100, hours=13)
        h4m = src.bars(pair, "4h", mid, None)
        last_day = aggregate_4h_to_1d(h4m).index[-1]
        assert last_day == pd.Timestamp(START + timedelta(days=99))


def test_1g_delikli_hisse_eksik_4s_gunu_uretmez(uzun):
    """Seans disi bar yok: 4s'ler eksik oldugundan hic 1g bar (6 x 4s tam gun) olusmaz -> sessiz doldurma yok."""
    h4 = uzun["hist"].bars(STOCK_GAP, "4h", uzun["end"], None)
    assert len(aggregate_4h_to_1d(h4)) == 0
