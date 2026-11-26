"""ML1: tabloyu kurma/uzatma orkestrasyonu (tarama + depo). Cikis sutunlari (table.EXIT_COLUMNS) sema uyumu icin kalir ve hep null yazilir;
uretimde cikis simulatoru yoktur (26.11 sahip karari: olu kod temizligi). CLI: research/ml1/build_table.py."""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from trader_core import arm_time as AT

from . import data as D
from . import scan as SC
from . import table as T


def build_pair_tf(tbl: T.CandidateTable, hist_dir, pair: str, tf: str, *, since: pd.Timestamp | None = None,
                  until: datetime | None = None, force: bool = False, **scan_kw) -> dict:
    """Bir cift x tf: yeni mumlari tara (artimli) ve diske ekle. `since`: yalniz ilk kurulumda alt sinir (decision_ts >= since).
    Doner istatistik sozlugu."""
    got = D.load_pair_tf(hist_dir, pair, tf, until)
    if got is None:
        return {"pair": pair, "tf": tf, "status": "no_data", "new": 0}
    trig, h4 = got
    delta = AT.arm_tf_delta(tf)
    end_ts = trig.index[-1] + delta
    if force:
        tbl.drop_pair_tf(pair, tf)
    last = tbl.last_scanned(pair, tf)
    after = last
    if after is None and since is not None:
        after = pd.Timestamp(since) - pd.Timedelta(1, "ns")
    if last is not None and end_ts <= last:
        n_new = 0
    else:
        df = SC.scan_pair_tf(pair, tf, trig, h4, after=after, **scan_kw)
        n_new = tbl.append(pair, tf, df, end_ts)
    return {"pair": pair, "tf": tf, "status": "ok", "new": n_new, "last_scanned_ts": str(end_ts)}


def build(tbl: T.CandidateTable, hist_dir, pairs: list[str], tfs: list[str], *, since=None, until=None, force=False,
          log=print, **scan_kw) -> list[dict]:
    """Hash kontrolu (degisirse TUM tablo silinir) + her cift x tf icin artimli tarama."""
    changed = tbl.ensure_hash(SC.arms_hash())
    if changed:
        log("arms_hash degisti: tablo yeniden kuruluyor")
    out = []
    for pair in pairs:
        for tf in tfs:
            r = build_pair_tf(tbl, hist_dir, pair, tf, since=since, until=until, force=force, **scan_kw)
            log(f"{pair} {tf}: {r}")
            out.append(r)
    return out
