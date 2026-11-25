"""ML1: tabloyu kurma/uzatma orkestrasyonu (tarama + depo + cikis simulatoru kancasi). CLI: research/ml1/build_table.py."""
from __future__ import annotations

import hashlib
import importlib
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from trader_core import arm_time as AT

from . import data as D
from . import scan as SC
from . import table as T

_EXIT_DOSYALARI = ("exitsim.py", "costs.py")


def exit_module():
    """`trader_ml.ml1.exitsim` varsa ve `simulate_rows` iceriyorsa modul, yoksa None (cikis alanlari null kalir)."""
    try:
        mod = importlib.import_module("trader_ml.ml1.exitsim")
    except ImportError:
        return None
    return mod if callable(getattr(mod, "simulate_rows", None)) else None


def exit_hash() -> str | None:
    """Cikis simulatorunun kaynak hash'i (yoksa None). Degisirse cikis alanlari bosaltilip yeniden simule edilir."""
    h, any_ = hashlib.sha256(), False
    for f in _EXIT_DOSYALARI:
        p = Path(__file__).with_name(f)
        if p.exists():
            h.update(f.encode())
            h.update(p.read_bytes())
            any_ = True
    return h.hexdigest() if any_ else None


def simulate_pending(tbl: T.CandidateTable, hist_dir, pair: str, tf: str) -> int:
    """Cikisi bos satirlari `exitsim.simulate_rows` ile simule edip yazar (modul yoksa 0). Veri sonunda acik kalan (status='open')
    satirlar yazilmaz (sonraki turda yeniden simule edilir). Doner: yazilan satir sayisi."""
    mod = exit_module()
    if mod is None:
        return 0
    pend = tbl.read(pairs=[pair], tfs=[tf], only_pending_exit=True)
    if len(pend) == 0:
        return 0
    b15 = D.load_15m(hist_dir, pair)
    got = D.load_pair_tf(hist_dir, pair, tf)
    if b15 is None or got is None:
        return 0
    trig, h4 = got
    bars_tf = mod.prepare_tf(trig, SC.core_table(trig, h4)) if hasattr(mod, "prepare_tf") else trig
    delta_ms = int(AT.arm_tf_delta(tf).total_seconds() * 1000)
    horizon_ms = int(getattr(mod, "HORIZON_DAYS", 30) * 86400 * 1000)
    rule: dict[tuple[str, str], np.ndarray] = {}
    rows = pend[SC.CAND_COLUMNS].to_dict("records")
    for r in rows:
        if r["rule_exit"]:
            k = (r["setup"], r["side"])
            if k not in rule:
                rule[k] = SC.rule_exit_close_ms(trig, tf, *k)
            ts = rule[k]
            d0 = int(pd.Timestamp(r["decision_ts"]).timestamp() * 1000)
            r["rule_exit_ts"] = ts[np.searchsorted(ts, d0, "left"):np.searchsorted(ts, d0 + horizon_ms, "right")].tolist()
    res = mod.simulate_rows(rows, b15, bars_tf, D.load_funding(hist_dir, pair), tf=tf)
    res = mod.to_frame(res) if hasattr(mod, "to_frame") else pd.DataFrame(list(res))
    if len(res) != len(pend):
        raise ValueError(f"simulate_rows satir sayisi uyusmuyor: {len(res)} != {len(pend)}")
    res.index = pend.index
    out = pend.copy()
    ren = {"exit_px": "exit_price", "net_R": "r_net"}
    for c in res.columns:
        c2 = ren.get(c, c)
        if c2 in T.EXIT_COLUMNS:
            out[c2] = res[c]
    out = out[out["status"].ne("open") & out["status"].notna()]
    return tbl.update_exits(out)


def build_pair_tf(tbl: T.CandidateTable, hist_dir, pair: str, tf: str, *, since: pd.Timestamp | None = None,
                  until: datetime | None = None, force: bool = False, simulate: bool = True, **scan_kw) -> dict:
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
    n_exit = simulate_pending(tbl, hist_dir, pair, tf) if simulate else 0
    return {"pair": pair, "tf": tf, "status": "ok", "new": n_new, "exit_updated": n_exit, "last_scanned_ts": str(end_ts)}


def build(tbl: T.CandidateTable, hist_dir, pairs: list[str], tfs: list[str], *, since=None, until=None, force=False,
          simulate: bool = True, log=print, **scan_kw) -> list[dict]:
    """Hash kontrolu (degisirse TUM tablo silinir) + her cift x tf icin artimli tarama."""
    changed = tbl.ensure_hash(SC.arms_hash())
    if changed:
        log("arms_hash degisti: tablo yeniden kuruluyor")
    if simulate:
        if tbl.ensure_exit_hash(exit_hash()):
            log("exit_hash degisti: cikis alanlari bosaltildi")
    out = []
    for pair in pairs:
        for tf in tfs:
            r = build_pair_tf(tbl, hist_dir, pair, tf, since=since, until=until, force=force, simulate=simulate, **scan_kw)
            log(f"{pair} {tf}: {r}")
            out.append(r)
    return out
