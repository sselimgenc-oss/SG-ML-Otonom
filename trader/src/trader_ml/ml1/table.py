"""ML1: aday tablosu deposu (parquet; bolum: pair/tf/ay) ve `manifest.json`.

Dizin:  <kok>/candidates/pair=<BTC_USDT>/tf=<1h>/month=<YYYY-MM>.parquet   (ay = decision_ts ayi, UTC)
        <kok>/manifest.json = {"version", "arms_hash", "exit_hash", "pairs": {"BTC/USDT|1h": {"last_scanned_ts", "n_rows"}}}
`last_scanned_ts` = taranan son mumun decision_ts'i (kapanisi); artimli tarama yalniz decision_ts > last_scanned_ts satirlarini ekler
(onceki `WARMUP_BARS` mumdan isinma ile). `arms_hash` degisirse (kol kaynaklari / parametreler) TUM tablo silinip yeniden kurulur.
Cikis alanlari (EXIT_COLUMNS) tarama aninda bostur (null); cikis simulatoru yoktur (26.11 sahip karari); sutunlar sema uyumu icin kalir (`update_exits` yalniz arac).
`only_pending_exit`: exit_ts ve exit_reason bos satirlar (veri sonunda acik kalan satirlar yazilmaz, sonraki turda yeniden simule edilir).
`exit_hash` degisirse yalniz cikis alanlari bosaltilir (adaylar kalir)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from . import scan as SC

VERSION = 1
EXIT_CORE = ["exit_ts", "exit_reason", "exit_price", "r_net", "censored"]
EXIT_EXTRA = ["entry_ts", "entry_px", "status", "gross_R", "fee_R", "funding_R", "mfe_R", "mae_R", "bars_held", "be_moved", "partial_frac"]
EXIT_COLUMNS = EXIT_CORE + EXIT_EXTRA                      # hepsi null yazilir (sema uyumu)
KEY = ["pair", "tf", "arm_id", "bar_ts"]                       # bir aday satirinin kimligi


def pair_dir_name(pair: str) -> str:
    return pair.replace("/", "_")


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Sabit sema: CAND_COLUMNS + EXIT_COLUMNS (+ varsa ek sutunlar), sabit tipler (bolumler arasi uyum)."""
    df = df.copy()
    for c in SC.CAND_COLUMNS:
        if c not in df.columns:
            raise KeyError(f"aday sutunu eksik: {c}")
    for c in EXIT_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    for c in ("bar_ts", "decision_ts", "exit_ts", "entry_ts"):
        df[c] = pd.to_datetime(df[c], utc=True).astype("datetime64[ns, UTC]")
    for c in ("exit_price", "r_net", "entry_px", "gross_R", "fee_R", "funding_R", "mfe_R", "mae_R", "bars_held", "partial_frac"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
    for c in ("censored", "be_moved"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int8")
    for c in ("exit_reason", "status"):
        df[c] = df[c].astype(object).where(df[c].notna(), None)
    for c in ("pair", "tf", "arm_id", "setup", "family", "group", "side", "exit_mode", "regime", "label"):
        df[c] = df[c].astype(object)
    rest = [c for c in df.columns if c not in SC.CAND_COLUMNS and c not in EXIT_COLUMNS]
    return df[SC.CAND_COLUMNS + EXIT_COLUMNS + rest]


class CandidateTable:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.cand = self.root / "candidates"
        self.manifest_path = self.root / "manifest.json"

    # ---------------------------------------------------------------------------------------------- manifest
    def manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {"version": VERSION, "arms_hash": None, "exit_hash": None, "pairs": {}}

    def write_manifest(self, m: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.manifest_path)

    def last_scanned(self, pair: str, tf: str) -> pd.Timestamp | None:
        e = self.manifest()["pairs"].get(f"{pair}|{tf}")
        return None if e is None else pd.Timestamp(e["last_scanned_ts"])

    def ensure_hash(self, arms_hash: str) -> bool:
        """Manifestteki hash farkliysa (ya da surum) TUM adaylari siler. True = silindi (yeniden kurulum)."""
        m = self.manifest()
        if m.get("arms_hash") == arms_hash and m.get("version") == VERSION:
            return False
        had = self.cand.exists() or bool(m["pairs"])
        if self.cand.exists():
            shutil.rmtree(self.cand)
        m = {"version": VERSION, "arms_hash": arms_hash, "exit_hash": None, "pairs": {}}
        self.write_manifest(m)
        return had

    def ensure_exit_hash(self, exit_hash: str | None) -> bool:
        """cikis simulatoru degistiyse cikis alanlarini bosaltir. True = bosaltildi."""
        m = self.manifest()
        if m.get("exit_hash") == exit_hash:
            return False
        m["exit_hash"] = exit_hash
        self.write_manifest(m)
        if self.cand.exists():
            for p in self.cand.rglob("*.parquet"):
                df = pd.read_parquet(p)
                for c in EXIT_COLUMNS:
                    if c in df.columns:
                        df[c] = None
                normalize(df).to_parquet(p, index=False)
            return True
        return False

    # ---------------------------------------------------------------------------------------------- yazma
    def _month_path(self, pair: str, tf: str, month: str) -> Path:
        return self.cand / f"pair={pair_dir_name(pair)}" / f"tf={tf}" / f"month={month}.parquet"

    def append(self, pair: str, tf: str, df: pd.DataFrame, last_scanned_ts: pd.Timestamp) -> int:
        """Yeni aday satirlarini aylara dagitip ekler (var olan ayin satirlari korunur, ayni anahtar yeniden yazilir)."""
        n_new = len(df)
        if n_new:
            df = normalize(df)
            months = df["decision_ts"].dt.strftime("%Y-%m")
            for mo, sub in df.groupby(months, sort=True):
                p = self._month_path(pair, tf, str(mo))
                if p.exists():
                    old = pd.read_parquet(p)
                    sub = pd.concat([old[~old.set_index(KEY).index.isin(sub.set_index(KEY).index)], sub], ignore_index=True)
                p.parent.mkdir(parents=True, exist_ok=True)
                normalize(sub).sort_values(["decision_ts", "arm_id"], kind="stable").to_parquet(p, index=False)
        m = self.manifest()
        e = m["pairs"].setdefault(f"{pair}|{tf}", {"last_scanned_ts": None, "n_rows": 0})
        e["last_scanned_ts"] = pd.Timestamp(last_scanned_ts).isoformat()
        e["n_rows"] = int(e["n_rows"]) + n_new
        self.write_manifest(m)
        return n_new

    def drop_pair_tf(self, pair: str, tf: str) -> None:
        d = self.cand / f"pair={pair_dir_name(pair)}" / f"tf={tf}"
        if d.exists():
            shutil.rmtree(d)
        m = self.manifest()
        m["pairs"].pop(f"{pair}|{tf}", None)
        self.write_manifest(m)

    def update_exits(self, df: pd.DataFrame) -> int:
        """`df`: KEY sutunlari + cikis sutunlari dolu satirlar; ilgili satirlarin cikis alanlari yerinde guncellenir."""
        if len(df) == 0:
            return 0
        df = normalize(df)
        ext = [c for c in df.columns if c in EXIT_COLUMNS or c not in SC.CAND_COLUMNS]
        n = 0
        months = df["decision_ts"].dt.strftime("%Y-%m")
        for (pair, tf, mo), sub in df.groupby([df["pair"], df["tf"], months], sort=False):
            p = self._month_path(pair, tf, str(mo))
            if not p.exists():
                continue
            old = pd.read_parquet(p)
            oi = old.set_index(KEY)
            si = sub.set_index(KEY)
            si = si[~si.index.duplicated(keep="last")]
            hit = oi.index.intersection(si.index)
            for c in ext:
                if c not in oi.columns:
                    oi[c] = pd.NA
                oi.loc[hit, c] = si.loc[hit, c]
            n += len(hit)
            normalize(oi.reset_index()).to_parquet(p, index=False)
        return n

    # ---------------------------------------------------------------------------------------------- okuma
    def files(self, pairs=None, tfs=None) -> list[Path]:
        if not self.cand.exists():
            return []
        pset = None if pairs is None else {pair_dir_name(p) for p in pairs}
        out = []
        for p in sorted(self.cand.rglob("*.parquet")):
            pr, tf = p.parent.parent.name[5:], p.parent.name[3:]
            if (pset is None or pr in pset) and (tfs is None or tf in tfs):
                out.append(p)
        return out

    def read(self, pairs=None, tfs=None, since: pd.Timestamp | None = None, until: pd.Timestamp | None = None,
             only_pending_exit: bool = False) -> pd.DataFrame:
        parts = [pd.read_parquet(p) for p in self.files(pairs, tfs)]
        if not parts:
            return normalize(SC._frame([]))
        df = pd.concat(parts, ignore_index=True)
        if since is not None:
            df = df[df["decision_ts"] >= pd.Timestamp(since)]
        if until is not None:
            df = df[df["decision_ts"] < pd.Timestamp(until)]
        if only_pending_exit:
            df = df[df["exit_ts"].isna() & df["exit_reason"].isna()]         # simule edilmemis (ya da veri sonunda acik kalmis)
        return df.sort_values(["decision_ts", "arm_id", "pair"], kind="stable").reset_index(drop=True)


def stable_equal(a: pd.DataFrame, b: pd.DataFrame, cols: list[str] | None = None, rtol: float = 1e-8) -> bool:
    """Iki tablonun (sirasiz) esitligi; ondalik sutunlarda goreli tolerans (artimli dilimde EMA tohumu ~1e-12 sapar). Test yardimcisi."""
    cols = cols or SC.CAND_COLUMNS
    x = a[cols].sort_values(["decision_ts", "arm_id", "pair"], kind="stable").reset_index(drop=True)
    y = b[cols].sort_values(["decision_ts", "arm_id", "pair"], kind="stable").reset_index(drop=True)
    try:
        pd.testing.assert_frame_equal(x, y, check_exact=False, rtol=rtol, atol=0.0)
    except AssertionError:
        return False
    return True
