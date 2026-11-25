"""Tam tarih taramasindaki satir i = canli yol (yalniz i'ye kadar prefix + mod.compute son satir). Ileriye bakis testi."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_ml.ml1 import scan as SC

from ml1_destek import PAIR, TF

BASE = ("T1", "R1", "TF1", "B1", "H2", "S1", "F1")
FORM = ("MF1", "GF1", "IN1", "PA2")


def _eq(p: dict, r: pd.Series) -> bool:
    return (p is not None and p["side"] == r["side"] and np.isclose(p["entry"], r["entry_ref"], rtol=1e-9)
            and np.isclose(p["stop"], r["stop"], rtol=1e-9) and np.isclose(p["target"], r["target"], rtol=1e-9, equal_nan=True))


def _ornek(scanned: pd.DataFrame, aileler, n: int) -> pd.DataFrame:
    sub = scanned[scanned["family"].isin(aileler) | scanned["arm_id"].str.split("@").str[0].isin(aileler)]
    assert len(sub) >= n, (len(sub), aileler)
    return sub.sample(n, random_state=3)


def test_taban_kol_satiri_prefix_ile_ayni(scanned, bars4h):
    # taban kollar (`setup` tireli degil): her bir kolun varsa bir satiri + rastgele ornek
    taban = scanned[~scanned["setup"].str.contains("-")]
    assert len(taban) > 0
    ornek = taban.groupby("setup").head(2).head(10)
    for _, r in ornek.iterrows():
        i = bars4h.index.get_loc(r["bar_ts"])
        assert _eq(SC.prefix_recompute(PAIR, TF, bars4h, bars4h, r["arm_id"], i), r), r["arm_id"]


def test_formasyon_kollari_prefix_ile_ayni(scanned, bars4h):
    # her formasyon ailesinden (MF1/GF1/IN1/PA2) ve PA varyantlarindan satirlar; uzun seride (i > 1200) IND_PENCERE penceresi de devrede
    parcalar = []
    for fam in ("MF1", "GF1", "IN1", "PA2", "T1", "H2", "TF1", "B1", "R1", "F1", "S1"):
        s = scanned[(scanned["family"] == fam) & scanned["setup"].str.contains("-")]
        if len(s):
            parcalar.append(s.sample(min(3, len(s)), random_state=5))
    ornek = pd.concat(parcalar)
    assert ornek["family"].nunique() >= 4
    assert (ornek["bar_ts"] > bars4h.index[1250]).any()          # pencere devrede olan bolge de var
    for _, r in ornek.iterrows():
        i = bars4h.index.get_loc(r["bar_ts"])
        assert _eq(SC.prefix_recompute(PAIR, TF, bars4h, bars4h, r["arm_id"], i), r), (r["arm_id"], r["bar_ts"])


def test_negatif_barlarda_canli_yol_da_aday_vermez(scanned, bars4h):
    var = set(zip(scanned["arm_id"], scanned["bar_ts"]))
    rng = np.random.default_rng(1)
    for arm in ("IN1-RSI@4h", "MF1-YUTAN@4h", "GF1-YATAY@4h", "T1@4h"):
        for i in rng.choice(np.arange(200, len(bars4h)), 6, replace=False):
            p = SC.prefix_recompute(PAIR, TF, bars4h, bars4h, arm, int(i))
            assert (p is not None) == ((arm, bars4h.index[int(i)]) in var), (arm, bars4h.index[int(i)])


def test_satir_alanlari(scanned):
    assert set(SC.CAND_COLUMNS) <= set(scanned.columns)
    assert (scanned["decision_ts"] - scanned["bar_ts"] == pd.Timedelta("4h")).all()
    assert scanned["side"].isin(["long", "short"]).all()
    long = scanned["side"] == "long"
    assert (scanned.loc[long, "stop"] < scanned.loc[long, "entry_ref"]).all()
    assert (scanned.loc[~long, "stop"] > scanned.loc[~long, "entry_ref"]).all()
    assert scanned["exit_mode"].isin(["trail", "target"]).all()
    assert (scanned.loc[scanned["exit_mode"] == "trail", "target"].isna()).all()
    assert scanned["family"].nunique() >= 5


def test_kural_cikisi_zamanlari_canli_kuralla_ayni(bars4h):
    # IN1 EXIT_RULE: tum seri uzerinden hesaplanan kapanis zamanlari == prefix ile canli kural (iki yon, dogru ve yanlis ornekler)
    delta = pd.Timedelta("4h")
    rng = np.random.default_rng(4)
    for setup in ("IN1-RSI", "IN1-MACD", "IN1-BOLL", "IN1-TK", "IN1-VWAP"):
        for side in ("long", "short"):
            ms = set(SC.rule_exit_close_ms(bars4h, TF, setup, side).tolist())
            for i in rng.choice(np.arange(300, len(bars4h)), 8, replace=False):
                kapanis = int((bars4h.index[int(i)] + delta).timestamp() * 1000)
                assert (kapanis in ms) == SC.prefix_rule_exit(PAIR, TF, bars4h, bars4h, setup, side, int(i)), (setup, side, int(i))


def test_after_ns_ile_ms_indeksli_seri(bars4h):
    # feather tarihi ms birimli; build.py `since - 1ns` (ns) verir: birim uyusmazligi ValueError vermemeli
    ms = bars4h.copy()
    ms.index = ms.index.as_unit("ms")
    after = ms.index[800] + pd.Timedelta("4h") - pd.Timedelta(1, "ns")
    df = SC.scan_pair_tf(PAIR, TF, ms, ms, after=after)
    assert len(df) == 0 or (df["decision_ts"] >= ms.index[800] + pd.Timedelta("4h")).all()
