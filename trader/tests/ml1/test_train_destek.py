"""ML1 egitim/degerlendirme testleri icin sentetik aday tablosu (hizli, ag/dosya yok). Test icermez."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trader_ml.ml1 import groups as G


def sentetik_tablo(n: int = 4000, seed: int = 3, sinyal: float = 0.0, p_kazan: float = 0.5, aylar: int = 24) -> pd.DataFrame:
    """n aday, `aylar` ay. conf_all_tf bilgilendirici ozellik: sinyal > 0 ise kazanma olasiligi sigmoid(sinyal * z) (z std. conf_all_tf).
    r_net = +1 / -1 (maliyet dahil sayilir). Olaylar: ayni gun + tf + yon."""
    rng = np.random.default_rng(seed)
    t0 = pd.Timestamp("2022-01-01", tz="UTC")
    sec = rng.integers(0, int(aylar * 30.4 * 86400), n)
    dec = (t0 + pd.to_timedelta(np.sort(sec), unit="s")).floor("1h")
    tf = rng.choice(["1h", "4h"], n)
    side = rng.choice(["long", "short"], n)
    grp = rng.choice(list(G.GRUP_ADLARI[:6]), n)
    conf = rng.poisson(2.0, n).astype(float)
    z = (conf - conf.mean()) / conf.std()
    p = 1 / (1 + np.exp(-sinyal * z)) if sinyal else np.full(n, p_kazan)
    win = rng.random(n) < p
    hold = pd.to_timedelta(rng.integers(1, 48, n), unit="h")
    entry = 100 + rng.normal(0, 1, n)
    df = pd.DataFrame({
        "bar_ts": dec - pd.Timedelta(hours=1), "decision_ts": dec, "pair": "SYN/USDT", "tf": tf, "arm_id": [f"T1@{t}" for t in tf],
        "setup": "T1", "family": "T1", "group": grp, "side": side, "entry_ref": entry, "stop": entry - 1.0,
        "target": np.where(rng.random(n) < 0.7, entry + 1.5, np.nan), "stop_dist_atr": rng.uniform(0.5, 2.0, n),
        "conf_same_tf": 0, "conf_all_tf": conf, "conf_groups": 0, "conf_opp": 0,
        "exit_ts": dec + hold, "status": "ok", "censored": 0, "r_net": np.where(win, 1.0, -1.0)})
    key = df["pair"] + "|" + df["side"] + "|" + df["tf"] + "|" + df["decision_ts"].dt.strftime("%Y-%m-%d")
    size = key.map(key.value_counts())
    df["event_id"], df["event_size"], df["event_weight"] = key, size, 1.0 / size
    return df
