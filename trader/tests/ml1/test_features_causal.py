"""Ozellikler nedensel: veri/aday kesilince (decision_ts <= X) onceki satirlarin ozellikleri DEGISMEZ; konfluans yalniz <= D sayar."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_ml.ml1 import features as F

from ml1_destek import PAIR, TF


def _cand(rows):
    df = pd.DataFrame(rows, columns=["decision_ts", "pair", "tf", "side", "group", "arm_id"])
    df["decision_ts"] = pd.to_datetime(df["decision_ts"], utc=True)
    return df


def test_konfluans_yalniz_D_ve_oncesini_sayar():
    # 1h; k=3: pencere [D-3h, D]
    c = _cand([("2024-01-01 10:00", "P", "1h", "long", "A", "a1"), ("2024-01-01 09:00", "P", "1h", "long", "B", "b1"),
               ("2024-01-01 08:00", "P", "1h", "long", "C", "c1"), ("2024-01-01 06:00", "P", "1h", "long", "D", "d1"),   # pencere disi
               ("2024-01-01 11:00", "P", "1h", "long", "E", "e1"),                                                     # gelecek (D=10:00 icin)
               ("2024-01-01 10:00", "P", "1h", "short", "A", "s1"), ("2024-01-01 10:00", "Q", "1h", "long", "A", "q1")])
    f = F.confluence(c, k=3)
    r = f.loc[0]                                             # D = 10:00 long: 09:00, 08:00 (6:00 pencere disi, 11:00 gelecek)
    assert r["conf_same_tf"] == 2 and r["conf_all_tf"] == 2 and r["conf_groups"] == 2
    assert r["conf_opp"] == 1                                # ayni anda short
    assert f.loc[3, "conf_all_tf"] == 0                      # 06:00: oncesinde kimse yok (gelecek sayilmaz)
    assert f.loc[4, "conf_all_tf"] == 3                      # 11:00: 10:00, 09:00, 08:00
    assert f.loc[6, "conf_all_tf"] == 0                      # baska cift sayilmaz


def test_konfluans_tf_arasi_zaman_damgasina_gore():
    c = _cand([("2024-01-01 12:00", "P", "4h", "long", "A", "a@4h"), ("2024-01-01 12:00", "P", "1h", "long", "B", "b@1h"),
               ("2024-01-01 06:00", "P", "1h", "long", "C", "c@1h")])
    f = F.confluence(c, k=3)                                 # 4h satiri icin pencere 12 saat: 1h adaylari da sayilir
    assert f.loc[0, "conf_same_tf"] == 0 and f.loc[0, "conf_all_tf"] == 2
    assert f.loc[1, "conf_same_tf"] == 0 and f.loc[1, "conf_all_tf"] == 1     # 1h satiri: 3 saat penceresinde yalniz 12:00 4h


def test_konfluans_kesme_degismezligi(scanned):
    X = scanned["decision_ts"].iloc[len(scanned) // 2]
    tam = F.confluence(scanned.assign(pair=PAIR), 3)
    kes = scanned[scanned["decision_ts"] <= X]
    kesik = F.confluence(kes, 3)
    pd.testing.assert_frame_equal(tam.loc[kes.index], kesik)


def test_olay_agirligi():
    c = _cand([("2024-01-01 01:00", "P", "1h", "long", "A", "a"), ("2024-01-01 02:00", "P", "1h", "long", "B", "b"),
               ("2024-01-01 03:00", "P", "1h", "long", "C", "c"), ("2024-01-01 12:00", "P", "1h", "long", "A", "a"),
               ("2024-01-01 02:00", "P", "1h", "short", "A", "a")])
    e = F.events(c, k=3)
    assert e["event_id"].nunique() == 3
    assert list(np.round(e["event_weight"], 6)) == [round(1 / 3, 6)] * 3 + [1.0, 1.0]
    assert abs(e["event_weight"].sum() - 3) < 1e-9           # olay basina toplam agirlik 1


def test_mum_ozellikleri_kesme_degismezligi(scanned, bars4h):
    from trader_core.arm_time import arm_tf_delta
    X = bars4h.index[1100]
    ornek = scanned[scanned["decision_ts"] <= X].sample(40, random_state=2)
    assert len(ornek) == 40

    def lookup_full(pair, tf):
        return bars4h, bars4h

    def lookup_kesik(pair, tf):
        kes = bars4h[bars4h.index + arm_tf_delta(TF) <= X]                  # karar anina kadar KAPANMIS mumlar
        return kes, kes

    a = F.bar_features(ornek.assign(pair=PAIR), lookup_full)
    b = F.bar_features(ornek.assign(pair=PAIR), lookup_kesik)
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-12)
    assert a["pa_ret_1"].notna().any() and a["reg_atr_pct"].notna().all() and a["vol_ratio"].notna().any()


def test_build_features_sutunlari(scanned, bars4h):
    out = F.build_features(scanned.head(30).assign(pair=PAIR), lambda p, t: (bars4h, bars4h))
    assert {"conf_same_tf", "conf_all_tf", "conf_groups", "conf_opp", "event_id", "event_weight", "pa_body", "reg_atr_ratio",
            "vol_20", "hour_utc"} <= set(out.columns)
    assert len(out) == 30
