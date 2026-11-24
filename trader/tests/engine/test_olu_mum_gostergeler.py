"""CHECK 2 - seansli enstrumanlarda (hisse/emtia perp) olu mumlar (hacim 0, o=h=l=c; hafta sonu/tatil/seans disi).

Bulgu (duzeltme oncesi): bu mumlar market.sqlite'a yazilir (`MarketStore._validate` hacim >= 0 kabul eder, h==l gecerlidir) ve gosterge girdisine
AYNEN girerdi: dogru aralik 0 -> Wilder ATR her olu mumda (13/14) ile carpilir (65 saatlik hafta sonu: x0,0083), EMA'lar tekrarlanan kapanisa yaklasir
(EMA20 == EMA50 -> rejim kaybolur), oynaklik tahmini ve korelasyon sifir getiriyle bozulur. Duzeltme TEK yerde (`arm_guard.active_mask`/
`expand_rows`/`regime_series`/`core_signals`/`tail_active`): olu mumlar gosterge girdisinden cikar, sonuc tam izgaraya genisler; kriptoda (olu mum yok)
eski yol AYNEN. Bu testler: ATR/EMA/rejim/stop mesafesi (pazartesi ilk karar), uzun yon, korelasyon, oynaklik tahmini, DL1, kripto etkilenmez."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

import gosterge_support as GS
from trader_core import indicators as I
from trader_core import ledger as L
from trader_core import regime as R
from trader_core import signals as S
from trader_engine import arm_guard as AG
from trader_engine import dl1_cikarim as DL
from trader_engine import korelasyon_grubu as KG
from trader_engine import strategy_runner as SR
from trader_engine import uzun_yon as UY
from trader_engine.bars import arm_tf_delta
from trader_engine.marketdata.sources import StoreSource
from trader_engine.strategies.base import StrategyContext, validate_table
from trader_engine.strategies.lab import PriceActionLab
from trader_engine.strategies.price_action_v1 import make_v1_full

UTC = timezone.utc
START = datetime(2026, 1, 5, tzinfo=UTC)           # Pazartesi
TOL = 1e-9
ARMS = [f"{s}@{t}" for s in ("T1", "R1", "TF1", "B1", "H2", "S1", "F1") for t in ("1h", "4h")]
DAYS = 200


def _params() -> dict:
    p = {k: getattr(S.DEFAULT_SIGNAL_PARAMS, k) for k in L.PARAM_KEYS}
    p["trigger_tf"] = "1h"
    return p


@pytest.fixture(scope="module")
def stock():
    """Ayni fiyat yolu: olu mumlu (izgara tam) ve olu mumsuz (seans disi bar yok)."""
    fl = GS.make_stock_15m(3, DAYS, START, 150.0, flat=True)
    nf = GS.make_stock_15m(3, DAYS, START, 150.0, flat=False)
    return dict(flat15=fl, clean15=nf, flat={tf: g for tf, g in GS.tf_frames(fl).items()}, clean={tf: g for tf, g in GS.tf_frames(nf).items()})


def _first_monday_bars(g: pd.DataFrame, n: int = 3) -> list[int]:
    vol, idx = g["volume"].to_numpy(), g.index
    return [i for i in range(1, len(g)) if vol[i] > 0 and vol[i - 1] == 0 and idx[i].day_of_week == 0][-n:]


# --------------------------------------------------------------------------------------------- maske / genisletme birimleri
def test_flat_mask_tanimi_ve_kripto_etkilenmez():
    df = pd.DataFrame({"open": [10, 10, 10, 10, 10.0], "high": [10, 10, 11, 10, np.nan], "low": [10, 10, 9, 9, np.nan],
                       "close": [10, 10, 10, 10, 10.0], "volume": [0, 5, 0, 0, np.nan]})
    # olu: hacim 0 VE h==l; (hacim>0, h==l) gercek islem; (hacim 0, h>l) tutarsiz veri: cikarilmaz; NaN: cikarilmaz
    assert AG.flat_mask(df).tolist() == [True, False, False, False, False]
    assert AG.active_mask(df).tolist() == [False, True, True, True, True]
    assert AG.flat_mask(df[["close"]]) is None and AG.active_mask(df[["open", "high", "low", "close"]]) is None
    crypto = GS.make_15m(1, 2000, START)
    assert AG.active_mask(crypto) is None                         # kripto: olu mum yok -> eski yol
    assert AG.tail_active(crypto, 500).equals(crypto.iloc[-500:])


def test_expand_rows_tasima_ve_varsayilanlar():
    full = pd.date_range(START, periods=6, freq="1h", tz="UTC")
    keep = np.array([False, True, False, False, True, False])
    ix = full[keep]
    c = pd.DataFrame({"atr_tf": [1.0, 2.0], "regime": pd.Series(["trend_up", "range"], index=ix, dtype=object),
                      "rh_touches": np.array([3, 4], dtype="int64"), "signal": [True, False],
                      "side": pd.Series(["long", None], index=ix, dtype=object), "planned_entry": [5.0, np.nan],
                      "reasons": pd.Series(["a", "b"], index=ix, dtype=object)}, index=ix)
    out = AG.expand_rows(c, full, keep, AG.CARRY_SIGNAL)
    assert list(out.index) == list(full)
    assert out["atr_tf"].tolist()[2:4] == [1.0, 1.0] and out["atr_tf"].tolist()[5] == 2.0 and math.isnan(out["atr_tf"].iloc[0])
    assert out["regime"].tolist() == ["unclear", "trend_up", "trend_up", "trend_up", "range", "range"]
    assert out["rh_touches"].tolist() == [0, 3, 3, 3, 4, 4] and out["rh_touches"].dtype == np.int64
    assert out["signal"].tolist() == [False, True, False, False, False, False]          # olu satirda aday yok
    assert out["side"].tolist() == [None, "long", None, None, None, None] and out["side"].dtype == object
    assert out["reasons"].tolist() == ["", "a", "", "", "b", ""]
    assert out["planned_entry"].iloc[1] == 5.0 and math.isnan(out["planned_entry"].iloc[2])


def test_kripto_yolu_bayt_bayt_ayni():
    """Olu mum yok: lab.compute/compute_tf ve PriceActionV1.compute eski dogrudan hesapla (classify+align+compute_signals) AYNI (assert_frame_equal)."""
    df15 = GS.make_15m(11, 96 * 120, START, 100.0)
    h1, h4 = GS.resample(df15, "1h"), GS.resample(df15, "4h")
    params = _params()
    sp = S.SignalParams.from_mapping(params)
    ref = S.compute_signals(h1[["open", "high", "low", "close"]],
                            R.align_to_base(R.classify_series(h4[["open", "high", "low", "close"]], sp.regime_params()), h1.index, 4), sp)
    D = (h1.index[-1] + timedelta(hours=1)).to_pydatetime()
    ctx = StrategyContext(pair="BTC/USDT", D=D, tf="1h", params=params, bars={"1h": h1, "4h": h4})
    lab = PriceActionLab(ARMS)
    pd.testing.assert_frame_equal(lab.compute_tf(ctx)["core"], ref)
    pd.testing.assert_frame_equal(make_v1_full().compute(ctx), ref)
    pd.testing.assert_frame_equal(PriceActionLab(ARMS).compute(ctx), ref)


# --------------------------------------------------------------------------------------------- ATR / EMA / rejim / stop mesafesi (pazartesi ilk karar)
@pytest.mark.parametrize("tf", ["1h", "4h"])
def test_pazartesi_ilk_karar_atr_ve_stop_mesafesi(stock, tf):
    """Hafta sonu olu mumlari eklenmis seri == eklenmemis seri: ATR ve stop mesafesi (1,5 ATR; M1/DL1/giris stop kurali) AYNI (1e-9).
    Duzeltme oncesi hesap (olu mumlar girdide) ATR'yi 5-10 kat kucultur => stop 5-10 kat dar => pozisyon 5-10 kat buyuk."""
    fl, nf, h4f = stock["flat"][tf], stock["clean"][tf], stock["flat"]["4h"]
    params = _params()
    firsts = _first_monday_bars(fl)
    assert len(firsts) == 3
    for i in firsts:
        D = (fl.index[i] + arm_tf_delta(tf)).to_pydatetime()
        gf = fl.iloc[:i + 1]
        h4_cut = h4f[h4f.index + pd.Timedelta("4h") <= D]
        out = PriceActionLab(ARMS).compute_tf(StrategyContext(pair="NVDA/USDT", D=D, tf=tf, params=params, bars={tf: gf, "4h": h4_cut}))
        core = out["core"]
        for t in out.values():
            validate_table(t, PriceActionLab(ARMS).info, gf.index)
        fixed_atr = float(core["atr_tf"].iloc[-1])
        clean_atr = float(I.atr(nf.loc[:fl.index[i]][["high", "low", "close"]], 14).iloc[-1])      # olu mum hic yok (referans)
        legacy_atr = float(I.atr(gf[["high", "low", "close"]], 14).iloc[-1])                      # eski davranis: olu mumlar girdide
        assert abs(fixed_atr - clean_atr) <= TOL * max(1.0, clean_atr), (fixed_atr, clean_atr)
        assert legacy_atr / clean_atr < 0.3, (legacy_atr, clean_atr)                              # kirlenme gercek ve buyuk
        stop_fixed, stop_clean, stop_legacy = 1.5 * fixed_atr, 1.5 * clean_atr, 1.5 * legacy_atr
        assert stop_fixed == pytest.approx(stop_clean, rel=TOL)
        assert stop_clean / stop_legacy > 3.0                                                      # pozisyon boyutu ~ 1 / stop mesafesi
        # ATR(4s) (rejim) ve atr_ratio duzeltmeden sonra makul (eski: ratio ~0,4); rejim son dolu 4s'ten tasinir ('unclear'e dusmez)
        assert float(core["atr_ratio"].iloc[-1]) > 0.6
        reg4 = AG.regime_series(h4_cut, S.SignalParams.from_mapping(params).regime_params())
        assert core["regime"].iloc[-1] == reg4["regime"].iloc[-1] != "unclear"


def test_olu_mumlu_seri_ile_mumsuz_seri_tum_dolu_barlarda_ayni_atr(stock):
    """Tum dolu 1s barlarda atr_tf ve (sonlu oldugu yerde) atr_4h / atr_ratio: olu mumlu == olu mumsuz; aday satirlari (rejim ayni ise) ayni."""
    params = _params()
    D = (stock["flat"]["1h"].index[-1] + timedelta(hours=1)).to_pydatetime()
    def run(frames):
        ctx = StrategyContext(pair="NVDA/USDT", D=D, tf="1h", params=params, bars={"1h": frames["1h"], "4h": frames["4h"]})
        return PriceActionLab(ARMS).compute_tf(ctx)
    of, oc = run(stock["flat"]), run(stock["clean"])
    flat_1h = stock["flat"]["1h"]
    act = flat_1h.index[~((flat_1h["volume"] == 0) & (flat_1h["high"] == flat_1h["low"]))]
    assert len(act) == len(stock["clean"]["1h"])                  # ayni dolu bar kumesi
    for key in of:
        tf_, tc_ = of[key].loc[act], oc[key]
        assert np.allclose(tf_["atr_tf"].to_numpy(), tc_["atr_tf"].to_numpy(), rtol=TOL, atol=0, equal_nan=True), key
        m = np.isfinite(tc_["atr_4h"].to_numpy())
        assert m.sum() > 100 and np.allclose(tf_["atr_4h"].to_numpy()[m], tc_["atr_4h"].to_numpy()[m], rtol=TOL, atol=0)
        same_reg = (tf_["regime"].to_numpy() == tc_["regime"].to_numpy())
        both = same_reg & tf_["setup"].notna().to_numpy() & tc_["setup"].notna().to_numpy()
        for c in ("signal", "setup", "side", "skip_reason"):
            assert (tf_[c].to_numpy()[both] == tc_[c].to_numpy()[both]).all(), (key, c)
        for c in ("planned_entry", "planned_stop", "planned_target", "stop_dist_atr"):
            assert np.allclose(tf_[c].to_numpy(dtype=float)[both], tc_[c].to_numpy(dtype=float)[both], rtol=TOL, atol=0, equal_nan=True), (key, c)


def test_olu_mumlar_adayi_yok_ve_son_satir_tasinir(stock):
    """Karar mumu olu ise (hafta sonu): son satir aday degildir; baglam (ATR/rejim) son dolu satirdan tasinir; tablo tam izgarada."""
    params = _params()
    g, h4 = stock["flat"]["1h"], stock["flat"]["4h"]
    i = _first_monday_bars(g)[-1] - 5                            # cuma/cumartesi: olu bar
    assert g["volume"].iloc[i] == 0
    D = (g.index[i] + timedelta(hours=1)).to_pydatetime()
    gf, h4c = g.iloc[:i + 1], h4[h4.index + pd.Timedelta("4h") <= D]
    out = PriceActionLab(ARMS).compute_tf(StrategyContext(pair="NVDA/USDT", D=D, tf="1h", params=params, bars={"1h": gf, "4h": h4c}))
    for k, t in out.items():
        validate_table(t, PriceActionLab(ARMS).info, gf.index)
        assert not bool(t["signal"].iloc[-1]) and pd.isna(t["setup"].iloc[-1])
    core = out["core"]
    last_active = int(np.flatnonzero(AG.active_mask(gf))[-1])
    assert core["atr_tf"].iloc[-1] == core["atr_tf"].iloc[last_active] > 0
    assert core["regime"].iloc[-1] == core["regime"].iloc[last_active]


# --------------------------------------------------------------------------------------------- canli yol (StoreSource + MultiArmSignalSource)
def test_canli_yol_hafta_sonu_olu_mumlu_depo_pazartesi_atr(stock, tmp_path):
    """market.sqlite'a olu mumlarla yazilmis hisse: canli kaynak pazartesi ilk dolu 1s barinda ATR = mumsuz referans; eski kirli deger >3x kucuk."""
    pair = "NVDA/USDT"
    db = tmp_path / "market.sqlite"
    GS.write_store(db, {pair: stock["flat15"]}, START + timedelta(days=DAYS + 1))
    st = StoreSource(db)
    # depoda olu mumlar gercekten var (hacim 0, o=h=l=c)
    raw = st.bars(pair, "1h", START + timedelta(days=DAYS), 4000)
    assert int(((raw["volume"] == 0) & (raw["high"] == raw["low"])).sum()) > 500
    g = stock["flat"]["1h"]
    i = _first_monday_bars(g)[-1]
    D = (g.index[i] + timedelta(hours=1)).to_pydatetime()
    src = SR.MultiArmSignalSource(st, PriceActionLab(ARMS), strict=True, pairs=[pair])
    fr = src.frame(pair, D, _params(), 1)
    assert fr.status == "ok", (fr.status, fr.detail)
    live_atr = fr.last.atr_tf
    clean = stock["clean"]["1h"].loc[:g.index[i]]
    clean_atr = float(I.atr(clean[["high", "low", "close"]], 14).iloc[-1])
    legacy_atr = float(I.atr(g.iloc[:i + 1][["high", "low", "close"]], 14).iloc[-1])
    # canli pencere: son n DOLU bar (olu mum orani yuksek: pencere genisler) -> mumsuz tum-gecmis referansa 1e-9
    assert abs(live_atr - clean_atr) <= TOL * max(1.0, clean_atr)
    assert legacy_atr < 0.3 * clean_atr


def test_pencere_dolu_bar_sayar_kripto_degismez(stock, tmp_path):
    pair, crypto = "NVDA/USDT", "BTC/USDT"
    db = tmp_path / "market.sqlite"
    GS.write_store(db, {pair: stock["flat15"], crypto: GS.make_15m(1, 96 * DAYS, START)}, START + timedelta(days=DAYS + 1))
    st = StoreSource(db)
    D = START + timedelta(days=DAYS)
    n = 400
    w = SR._bars_window(st, pair, "1h", D, n)
    assert int(AG.active_mask(w).sum()) == n and len(w) > n * 2          # son 400 DOLU bar (+ aralarindaki olu mumlar)
    assert not bool(((w["volume"] == 0) & (w["high"] == w["low"])).iloc[0])   # pencere dolu barla baslar
    c = SR._bars_window(st, crypto, "1h", D, n)
    assert c.equals(st.bars(crypto, "1h", D, n)) and len(c) == n          # kripto: birebir view.bars(n)


# --------------------------------------------------------------------------------------------- uzun yon / korelasyon / oynaklik / DL1
def test_uzun_yon_hafta_sonu_gunleri_gunluk_seriye_girmez(stock):
    now = (stock["flat"]["4h"].index[-1] + timedelta(hours=4)).to_pydatetime()
    kf = UY.gunluk_kapanislar(stock["flat"]["4h"], now)
    kc = UY.gunluk_kapanislar(stock["clean"]["4h"], now)
    assert kf == kc and len(kf) > 100
    legacy = [k for _g, _t, k in _legacy_gunluk(stock["flat"]["4h"], now)]
    assert len(legacy) > len(kf)                                        # eski: cumartesi/pazar kopya kapanislar da gun sayilirdi
    cfg = {"ema": 50, "egim_gun": 10, "min_gun": 60}
    rf = UY.UzunYon(cfg, lambda p, tf, until, n: stock["flat"]["4h"][stock["flat"]["4h"].index + pd.Timedelta("4h") <= until].iloc[-n:]).rejim("X", now)
    rc = UY.UzunYon(cfg, lambda p, tf, until, n: stock["clean"]["4h"][stock["clean"]["4h"].index + pd.Timedelta("4h") <= until].iloc[-n:]).rejim("X", now)
    assert rf == rc


def _legacy_gunluk(df, now):
    c = df["close"].astype("float64")
    c = c[~c.index.duplicated(keep="last")].sort_index()
    c = c[c.index + timedelta(hours=4) <= now]
    c = c[c.index.normalize() < pd.Timestamp(now).normalize()]
    return [(g, grp.index[-1], float(grp.iloc[-1])) for g, grp in c.groupby(c.index.normalize())]


def test_korelasyon_getirileri_olu_mumlardan_etkilenmez(stock):
    f1, c1 = stock["flat"]["1h"], stock["clean"]["1h"]
    rf, rc = KG.getiriler(f1), KG.getiriler(c1)
    pd.testing.assert_series_equal(rf, rc, rtol=TOL)
    assert len(rc) < len(f1) * 0.3
    # eski: olu mumlar sifir getiri uretirdi
    cl = f1["close"].astype("float64")
    prev = cl.copy(); prev.index = prev.index + timedelta(hours=1)
    old = (cl / prev.reindex(cl.index) - 1.0).dropna()
    assert int((old == 0.0).sum()) > 3000
    # kripto ile korelasyon: olu mumlu == olu mumsuz (hisse-kripto korelasyonu sifirlarla seyrelmez)
    crypto = GS.resample(GS.make_15m(1, 96 * DAYS, START, 100.0), "1h")
    def mat(stock_df):
        frames = {"A": stock_df, "B": crypto}
        g = KG.KorelasyonGruplari(lambda p, tf, now, n: frames[p], ["A", "B"], {}, 0.7, 150, min_ortak=100)
        return g.korelasyon("A", "B", START + timedelta(days=DAYS))
    cf, cc = mat(f1), mat(c1)
    assert cf is not None and cc is not None and cf == pytest.approx(cc, abs=1e-12)


def test_oynaklik_tahmini_olu_mumlardan_etkilenmez(stock):
    fl, nf = stock["flat"]["1h"], stock["clean"]["1h"]
    i = _first_monday_bars(fl)[-1]
    gf, gn = fl.iloc[:i + 1], nf.loc[:fl.index[i]]
    atr = float(I.atr(gn[["high", "low", "close"]], 14).iloc[-1])
    vf = SR._vol("T1", "long", gf, atr, "1h")
    vc = SR._vol("T1", "long", gn, atr, "1h")
    assert vf and vf == vc
    from trader_engine.vol_tahmin import vol_ozellikleri
    old = vol_ozellikleri(gf["close"].to_numpy(dtype=float), atr, "1h")      # eski: olu mumlar sifir getiri
    assert old["vol_tahmin"] != pytest.approx(vf["vol_tahmin"], rel=1e-3)


def test_dl1_olu_mumlari_atlar(stock):
    """dl1_cikarim zaten olu mumlari atliyor (dolu_maske = hacim > 0 ve h > l; egitim ve canli ayni kural) - dogrulama."""
    g = stock["flat"]["1h"]
    ts = g.index.tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]").astype("int64")
    o, h, l, c, v = (g[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "volume"))
    ts_k, o_k, h_k, l_k, c_k, v_k = DL.kompakt(ts, o, h, l, c, v)
    n_clean = len(stock["clean"]["1h"])
    assert len(c_k) == n_clean and (v_k > 0).all() and (h_k > l_k).all()
    # son bar olu ise puan yok
    m = DL.dolu_maske(h[-1:], l[-1:], v[-1:])
    assert bool(m[0]) == bool(v[-1] > 0 and h[-1] > l[-1])
    # olu mumlar sifir ATR eklemez: dolu mumlardan hesaplanan ATR == olu mumsuz seri ATR
    assert DL.atr_son(h_k, l_k, c_k) == pytest.approx(DL.atr_son(stock["clean"]["1h"]["high"].to_numpy(), stock["clean"]["1h"]["low"].to_numpy(),
                                                              stock["clean"]["1h"]["close"].to_numpy()), rel=TOL)


# --------------------------------------------------------------------------------------------- _bars_window: verimli okuma, ayni sonuc, acik eksik-dolu davranisi
def _bars_window_ref(view, pair, tf, D, n):
    """Eski (2-3 kez yeniden okuyan) uygulama: sonuc referansi."""
    df = view.bars(pair, tf, D, n)
    m = n
    for _ in range(3):
        keep = AG.active_mask(df)
        if keep is None or len(df) < m:
            break
        got = int(keep.sum())
        if got >= n or m >= n * 8:
            break
        m = min(n * 8, int(math.ceil(n * len(df) / max(got, 1))) + 32)
        df = view.bars(pair, tf, D, m)
    return AG.tail_active(df, n)


class _CountView:
    def __init__(self, v):
        self.v, self.calls, self.rows = v, 0, 0

    def bars(self, pair, tf, until, n=None, kind="last"):
        df = self.v.bars(pair, tf, until, n, kind)
        self.calls += 1
        self.rows += len(df)
        return df


@pytest.fixture()
def clean_hint():
    SR._LIVE_FRAC.clear()
    yield
    SR._LIVE_FRAC.clear()


@pytest.mark.parametrize("tf,n", [("1h", 400), ("1h", 900), ("15m", 1200), ("4h", 150)])
def test_bars_window_ayni_sonuc_daha_az_okuma(stock, tmp_path, clean_hint, tf, n):
    """Yeni `_bars_window` == eski uygulama (assert_frame_equal) hem soguk (ipucu yok) hem sicak (onceki orandan boyutlu ilk okuma);
    okunan satir toplami eskisinden fazla degil, sicakta tek okuma; kripto: tek okuma, birebir view.bars(n)."""
    pair, crypto = "NVDA/USDT", "BTC/USDT"
    db = tmp_path / "market.sqlite"
    GS.write_store(db, {pair: stock["flat15"], crypto: GS.make_15m(1, 96 * DAYS, START)}, START + timedelta(days=DAYS + 1))
    st = StoreSource(db)
    D = START + timedelta(days=DAYS)
    old = _CountView(st)
    ref = _bars_window_ref(old, pair, tf, D, n)
    cold = _CountView(st)
    pd.testing.assert_frame_equal(SR._bars_window(cold, pair, tf, D, n), ref)
    warm = _CountView(st)
    pd.testing.assert_frame_equal(SR._bars_window(warm, pair, tf, D, n), ref)
    assert int(AG.active_mask(ref).sum()) == n
    assert cold.calls <= min(2, old.calls) and cold.rows <= old.rows * 1.15
    assert warm.calls == 1 and warm.rows < old.rows           # sicak: tek okuma, eskiden 2-3 okuma
    crypto_view = _CountView(st)
    c = SR._bars_window(crypto_view, crypto, tf, D, n)
    assert c.equals(st.bars(crypto, tf, D, n)) and crypto_view.calls == 1 and crypto_view.rows == n


def test_bars_window_eksik_dolu_bar_acik_ve_eski_ile_ayni(tmp_path, clean_hint):
    """Gecmis biterse ya da eski gecmis cok daha oluyse (tavan n*8) pencere n'den AZ dolu bar tutar: bilincli (hata/bloklama yok), eski
    uygulamayla ayni. Burada: ilk 2000 saat dolu, sonraki 5000 saat TAMAMEN olu, son 30 saat dolu; n=100 -> yalniz 30 dolu bar (tavan 800 satir)."""
    base = GS.make_15m(4, 96 * 320, START, 50.0)
    n15 = len(base)
    live_tail, dead_mid = 30 * 4, 5000 * 4
    v = base.copy()
    lo, hi = n15 - live_tail - dead_mid, n15 - live_tail
    last_c = float(v["close"].iloc[lo - 1])
    for col in ("open", "high", "low", "close"):
        v.iloc[lo:hi, v.columns.get_loc(col)] = last_c
    v.iloc[lo:hi, v.columns.get_loc("volume")] = 0.0
    pair = "SPY/USDT"
    db = tmp_path / "m.sqlite"
    end = v.index[-1] + pd.Timedelta("15min")
    GS.write_store(db, {pair: v}, end + timedelta(days=1))
    st = StoreSource(db)
    D = end.to_pydatetime()
    n = 100
    got = SR._bars_window(st, pair, "1h", D, n)
    ref = _bars_window_ref(st, pair, "1h", D, n)
    live = int(AG.active_mask(got).sum())
    assert live < n and live == 30 == int(AG.active_mask(ref).sum()) and len(got) <= n * 8    # ayni dolu barlar (olu dolgu boyu: tek yeniden okuma <= eski tavan)
    lg, lr = got[AG.active_mask(got)], ref[AG.active_mask(ref)]
    pd.testing.assert_frame_equal(lg, lr)
    # gecmis biterse: istenen n depodaki tum dolu bardan buyuk -> hepsi, hata yok
    SR._LIVE_FRAC.clear()
    big = SR._bars_window(st, pair, "1h", D, 100000)
    assert int(AG.active_mask(big).sum()) == int(AG.active_mask(st.bars(pair, "1h", D, None)).sum())


def test_bars_1d_pencere_600_gun_ayni_sonuc_ve_zarif_dusus(stock, tmp_path, clean_hint):
    """1g yolu: 4s'ten toplanir, pencere 4s penceresinden (1500 x 4s) bagimsiz. Kripto: son 600 gun == tum gecmisin kuyrugu; hisse: 600 DOLU gun
    (olu hafta sonu gunleri girmez); gecmis daha kisaysa (200 gun) var olan kullanilir (hata/bloklama yok)."""
    from trader_engine.bars import WINDOW_ARM, aggregate_4h_to_1d
    n = int(WINDOW_ARM["1d"])
    assert n >= 600
    days = 700
    crypto, pair = "BTC/USDT", "NVDA/USDT"
    fl = GS.make_stock_15m(3, days, START, 150.0, flat=True)
    db = tmp_path / "m.sqlite"
    GS.write_store(db, {crypto: GS.make_15m(1, 96 * days, START), pair: fl}, START + timedelta(days=days + 1))
    st = StoreSource(db)
    D = START + timedelta(days=days)
    c = SR._bars_1d(st, crypto, D, n)
    full = aggregate_4h_to_1d(st.bars(crypto, "4h", D, None))
    pd.testing.assert_frame_equal(c, full.iloc[-n:])
    assert len(c) == n
    s = SR._bars_1d(st, pair, D, n)
    live = int(AG.active_mask(s).sum())
    assert live <= n and live > 400                           # 700 gunde ~500 dolu gun var: tumu (depo bitti), hata yok
    pd.testing.assert_frame_equal(s, AG.tail_active(aggregate_4h_to_1d(st.bars(pair, "4h", D, None)), n))
    short = tmp_path / "s.sqlite"
    GS.write_store(short, {crypto: GS.make_15m(1, 96 * 200, START)}, START + timedelta(days=201))
    s2 = SR._bars_1d(StoreSource(short), crypto, START + timedelta(days=200), n)
    assert 150 <= len(s2) < n                                 # elde olan kullanilir


# --------------------------------------------------------------------------------------------- A1-A3: tutarli cagiranlar
def _h1_h4_rows(h1, h4, volume=True):
    def rows(g):
        return [(int(ts.value // 1_000_000), *map(float, r)) for ts, r in zip(g.index, g[["open", "high", "low", "close"] + (["volume"] if volume else [])].to_numpy())]
    return rows(h1), rows(h4)


def test_exit_counterfactual_prepare_h1_kripto_ayni_hisse_motorla_ayni(stock):
    """A1: kripto (olu mum yok): eski dogrudan hesapla ayni (hacimli ya da hacimsiz satir); seansli: ATR/rejim motorun core_signals ciktisiyla ayni."""
    from trader_core import exit_counterfactual as EC
    sp = S.DEFAULT_SIGNAL_PARAMS
    df15 = GS.make_15m(11, 96 * 120, START, 100.0)
    h1, h4 = GS.resample(df15, "1h"), GS.resample(df15, "4h")
    cols = ["open", "high", "low", "close"]
    ref = S.compute_signals(h1[cols], R.align_to_base(R.classify_series(h4[cols], sp.regime_params()), h1.index, 4), sp)
    for vol in (True, False):
        r1, r4 = _h1_h4_rows(h1, h4, vol)
        ser = EC.prepare_h1(r1, r4)
        np.testing.assert_array_equal(ser.atr, ref["atr_tf"].to_numpy())
        assert ser.regime == ref["regime"].tolist()
    f1, f4 = stock["flat"]["1h"], stock["flat"]["4h"]
    assert AG.active_mask(f1) is not None
    r1, r4 = _h1_h4_rows(f1, f4)
    ser = EC.prepare_h1(r1, r4)
    reg = AG.regime_series(f4, sp.regime_params())
    eng, _, _ = AG.core_signals(f1, reg, sp)
    np.testing.assert_array_equal(ser.atr, eng["atr_tf"].to_numpy())
    assert ser.regime == eng["regime"].tolist()
    r1n, r4n = _h1_h4_rows(f1, f4, volume=False)               # hacimsiz satir: eski yol (olu mum ayirt edilemez)
    legacy = EC.prepare_h1(r1n, r4n)
    live = AG.active_mask(f1)
    a, b = np.asarray(ser.atr)[live], np.asarray(legacy.atr)[live]
    assert np.nanmean(np.abs(a - b) / a) > 1e-3               # eski yol seansli enstrumanda gercekten farkli (anlamli test)


def test_ml_v2_ozellikleri_olu_mumlari_cikarir_kripto_ayni():
    """A2: canli ML v2 baglami (LiveContextV2.features_for_bar) olu 1s mumlari ozellik girdisinden cikarir (v1 ile ayni; `ml_features_v2` dondurulmus
    dosya, ayiklama cagirandadir). Seansli cift: sonuc == onceden ayiklanmis girdiyle `feature_frame_v2`; ayiklamasiz yol FARKLI. Kripto: ayni nesne
    (strip_dead) => ayiklamasiz yolla birebir. Tutulan pencere ham kalir (delik denetimi takvim izgarasinda)."""
    from trader_core import ml_live_v2 as LV
    from trader_core.arm_time import strip_dead
    from trader_core.ml_features_v2 import feature_frame_v2
    days = 220
    n = 96 * days
    raw = {"BTC/USDT": GS.resample(GS.make_15m(1, n, START, 100.0), "1h"), "ETH/USDT": GS.resample(GS.make_15m(2, n, START, 50.0), "1h"),
           "SOL/USDT": GS.resample(GS.make_15m(5, n, START, 60.0), "1h"), "NVDA/USDT": GS.resample(GS.make_stock_15m(3, days, START, 150.0, flat=True), "1h")}
    assert strip_dead(raw["BTC/USDT"]) is raw["BTC/USDT"]
    D = pd.Timestamp(START + timedelta(days=213, hours=17))                   # persembe 17:00 UTC: son bar (16:00) seansta -> dolu
    assert AG.active_mask(raw["NVDA/USDT"]) is not None and bool(AG.active_mask(raw["NVDA/USDT"])[raw["NVDA/USDT"].index.get_loc(D - pd.Timedelta("1h"))])

    def bars_fn(p, d, k):
        g = raw[p]
        return g[g.index + pd.Timedelta("1h") <= pd.Timestamp(d)].tail(k)
    ctx = LV.LiveContextV2("r02", list(raw), bars_fn)
    cands = pd.DataFrame([{"pair": "NVDA/USDT", "side": "long", "planned_entry": 150.0, "planned_stop": 148.0},
                          {"pair": "SOL/USDT", "side": "short", "planned_entry": 60.0, "planned_stop": 61.0}])
    bf = ctx.features_for_bar(D.to_pydatetime(), cands)
    assert any(AG.active_mask(h) is not None for h in ctx._held.values())     # tutulan pencere ham (olu mumlar duruyor)
    frames = {LV.internal_key(p): ctx._held[p] for p in raw}
    c = pd.DataFrame({"ts": [D] * 2, "pair": [LV.internal_key(p) for p in cands["pair"]], "side": cands["side"].to_numpy(),
                      "planned_entry": cands["planned_entry"].to_numpy(float), "planned_stop": cands["planned_stop"].to_numpy(float)})
    pre = {k: (d[AG.active_mask(d)] if AG.active_mask(d) is not None else d) for k, d in frames.items()}
    exp = feature_frame_v2(pre, c, recipe="r02")
    legacy = feature_frame_v2(frames, c, recipe="r02")
    for i, p in enumerate(cands["pair"]):
        got = np.array([bf.rows[p][k] for k in ctx.names])
        np.testing.assert_array_equal(got, exp.iloc[i][list(ctx.names)].to_numpy(float))
    nv = np.array([bf.rows["NVDA/USDT"][k] for k in ctx.names])
    assert not np.allclose(nv, legacy.iloc[0][list(ctx.names)].to_numpy(float), equal_nan=True)       # ayiklamasiz yol seansli ciftte farkli
    sol = np.array([bf.rows["SOL/USDT"][k] for k in ctx.names])
    ok = np.isfinite(sol) & np.isfinite(legacy.iloc[1][list(ctx.names)].to_numpy(float))
    assert ok.any()


def test_price_action_v1_4h_kripto_ayni_hisse_olu_mumsuz(stock):
    """A3: v1_4h tetik 4s: kripto eski dogrudan hesapla AYNI; seansli: 4s olu mumlar gosterge girdisinden cikar (v1 ile ayni desen)."""
    from trader_engine.strategies.price_action_v1_4h import PriceActionV1H4
    params = _params()
    sp = S.SignalParams.from_mapping(params)
    cols = ["open", "high", "low", "close"]

    def legacy_core(h4):
        reg = R.classify_series(h4[cols], sp.regime_params())
        return S.compute_signals(h4[cols], R.align_to_base(reg, h4.index, 4), sp)
    df15 = GS.make_15m(11, 96 * 120, START, 100.0)
    h1, h4 = GS.resample(df15, "1h"), GS.resample(df15, "4h")
    D = (h1.index[-1] + timedelta(hours=1)).to_pydatetime()
    strat = PriceActionV1H4()
    out = strat.compute(StrategyContext(pair="BTC/USDT", D=D, tf="1h", params=params, bars={"1h": h1, "4h": h4}))
    # eski cikti: ayni sonradan-isleme ile (compute icindeki 4s -> 1s kopyalama); tek fark kaynagi yalniz 4s cekirdek => cekirdege AYNI
    sig4 = legacy_core(h4)
    pd.testing.assert_frame_equal(AG.core_signals(h4, AG.regime_series(h4, sp.regime_params()), sp)[0], sig4)
    assert list(out.columns) == list(S.SIGNAL_COLUMNS) and len(out) == len(h1)
    f1, f4 = stock["flat"]["1h"], stock["flat"]["4h"]
    assert AG.active_mask(f4) is not None
    Ds = (f1.index[-1] + timedelta(hours=1)).to_pydatetime()
    o2 = strat.compute(StrategyContext(pair="NVDA/USDT", D=Ds, tf="1h", params=params, bars={"1h": f1, "4h": f4}))
    keep = AG.active_mask(f4)
    clean_core = legacy_core(f4[keep])
    full, _, _ = AG.core_signals(f4, AG.regime_series(f4, sp.regime_params()), sp)
    np.testing.assert_allclose(full["atr_tf"].to_numpy()[keep], clean_core["atr_tf"].to_numpy(), rtol=1e-12, equal_nan=True)   # ATR: yalniz dolu mumlardan
    assert len(o2) == len(f1)
