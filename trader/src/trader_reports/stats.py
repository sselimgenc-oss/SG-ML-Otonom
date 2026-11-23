"""Istatistik (gun-kumelenmis ortalama/aralik, Wilson, cokluk citasi, yari uyumu, yil satirlari) ve Turkce bicimleyiciler."""
from __future__ import annotations

import math
from statistics import NormalDist

from trader_engine.holdout import KILIT_ACIK

Z90 = 1.645
MIN_N = 30
MIN_G = 8
WILSON_NOTE = ("Aralık işlemleri bağımsız sayar; aynı gün açılan işlemler birlikte hareket ettiği için gerçek belirsizlik "
               "daha geniştir (varsayım).")
SUBGROUP_NOTE = ("`varsayım` = tesadüften ayırt edilemedi. `çıtayı geçti` de kural değildir; değişiklik ön kayıt ve onay ister.")
DASH = "—"


# --------------------------------------------------------------------------- bicimleyiciler (telegram ile ayni cikti)
def tr_sayi(x: float, ondalik: int = 2) -> str:
    return f"{x:,.{ondalik}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tr_isaretli(x: float, ondalik: int = 2) -> str:
    return ("+" if x >= 0 else "−") + tr_sayi(abs(x), ondalik)


def tr_yuzde(oran: float, ondalik: int = 2) -> str:
    return ("+" if oran >= 0 else "−") + "%" + tr_sayi(abs(oran) * 100, ondalik)


# --------------------------------------------------------------------------- temel
def merge(dst: dict, src: dict) -> dict:
    for k, v in src.items():
        dst[k] = v
    return dst


def mean(v) -> float:
    return math.fsum(v) / len(v)


def cluster_mean(xs, days) -> dict:
    """CR1: m, SE, G, n. SE None => tanimsiz (G < 2)."""
    n = len(xs)
    if n == 0:
        return {"n": 0, "G": 0, "m": None, "se": None, "lo": None, "hi": None}
    m = mean(xs)
    u: dict[str, float] = {}
    for x, g in zip(xs, days):
        u[g] = u.get(g, 0.0) + (x - m) / n
    G = len(u)
    se = None
    if G >= 2:
        se = math.sqrt(G / (G - 1) * math.fsum(v * v for v in u.values()))
    lo = hi = None
    if se is not None and G >= MIN_G and se >= 1e-12:
        lo, hi = m - Z90 * se, m + Z90 * se
    return {"n": n, "G": G, "m": m, "se": se, "lo": lo, "hi": hi}


def cluster_diff(a_x, a_d, b_x, b_d) -> dict:
    """d = m_B - m_A; z = d/SE (G < 8 ya da SE < 1e-12 => z None)."""
    na, nb = len(a_x), len(b_x)
    if na < 1 or nb < 1:
        return {"d": None, "se": None, "z": None, "G": 0}
    ma, mb = mean(a_x), mean(b_x)
    d = mb - ma
    u: dict[str, float] = {}
    for x, g in zip(b_x, b_d):
        u[g] = u.get(g, 0.0) + (x - mb) / nb
    for x, g in zip(a_x, a_d):
        u[g] = u.get(g, 0.0) - (x - ma) / na
    G = len(u)
    if G < 2:
        return {"d": d, "se": None, "z": None, "G": G}
    se = math.sqrt(G / (G - 1) * math.fsum(v * v for v in u.values()))
    z = d / se if (G >= MIN_G and se >= 1e-12) else None
    return {"d": d, "se": se, "z": z, "G": G}


def wilson(k: int, n: int) -> dict:
    if n <= 0:
        return {"n": 0, "k": 0, "p": None, "lo": None, "hi": None}
    p = k / n
    z = Z90
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return {"n": n, "k": k, "p": p, "lo": max(0.0, centre - half), "hi": min(1.0, centre + half)}


def z_k(K: int) -> float | None:
    if K < 1:
        return None
    return NormalDist().inv_cdf(1 - 0.05 / (2 * K))


def pctl(values, qs):
    """numpy.percentile varsayilani (dogrusal ara deger)."""
    import numpy as np
    if len(values) == 0:
        return [None] * len(qs)
    return [float(x) for x in np.percentile(np.asarray(values, dtype=float), list(qs))]


def label_basic(n: int, G: int) -> str:
    return "yetersiz" if (n < MIN_N or G < MIN_G) else "varsayım"


def sign(x: float) -> int:
    return (x > 0) - (x < 0)


# --------------------------------------------------------------------------- alt grup tablosu
class SubTable:
    """Ayni orneklemi hucrelere bolen dokum. cells: [(etiket, [(x, gun, ts), ...], ekstra_sozluk)].
    K_tablo = n>=1 hucre sayisi; etiketler K_rapor bilinince `finalize` ile atanir."""

    def __init__(self, tid: str, title: str, measure: str, cells, extra_cols=(), notes=(), section: str = "", post=None):
        self.tid, self.title, self.measure = tid, title, measure
        self.cells = [(str(lbl), list(items), dict(extra or {})) for lbl, items, extra in cells]
        self.extra_cols = list(extra_cols)
        self.notes = list(notes)
        self.section = section
        self.post = post

    @property
    def k_table(self) -> int:
        return sum(1 for _, it, _ in self.cells if len(it) >= 1)

    def finalize(self, zk: float | None, k_rapor: int) -> dict:
        all_items = [i for _, it, _ in self.cells for i in it]
        halves = _halves(all_items)
        rows = []
        single = self.k_table <= 1
        for lbl, items, extra in self.cells:
            xs = [i[0] for i in items]
            ds = [i[1] for i in items]
            cm = cluster_mean(xs, ds)
            n, G = cm["n"], cm["G"]
            row = {"hucre": lbl, "n": n, "G": G, "ort": cm["m"], "aralik": ([cm["lo"], cm["hi"]] if cm["lo"] is not None else None)}
            z = None
            if n < MIN_N or G < MIN_G:
                et = "yetersiz"
                row["aralik"] = None
            elif single or len(all_items) == n:
                et = "varsayım"
            else:
                ids = {id(i) for i in items}
                rest = [i for i in all_items if id(i) not in ids]
                cd = cluster_diff([i[0] for i in rest], [i[1] for i in rest], xs, ds)
                z = cd["z"]
                et = "varsayım"
                if z is not None and zk is not None and abs(z) >= zk and _half_agree(items, rest, halves):
                    et = "çıtayı geçti"
            row["z"] = z
            row["etiket"] = et
            merge(row, extra)
            if self.post is not None:
                self.post(row)
            rows.append(row)
        return {"id": self.tid, "title": self.title, "measure": self.measure, "k_table": self.k_table, "k_rapor": k_rapor,
                "z_k": zk, "columns": ["hucre", "n", "G", "ort", "aralik", "z", "etiket"] + self.extra_cols,
                "rows": rows, "notes": [SUBGROUP_NOTE] + self.notes, "section": self.section}


def _halves(items):
    """Medyan zaman damgasi (alt medyan); ts <= medyan => ilk yari (esitlikte ilk yari)."""
    if not items:
        return None
    ts = sorted(i[2] for i in items)
    return ts[(len(ts) - 1) // 2]


def _half_agree(cell, rest, med) -> bool:
    ds = []
    for first in (True, False):
        b = [i[0] for i in cell if (i[2] <= med) == first]
        a = [i[0] for i in rest if (i[2] <= med) == first]
        if len(b) < 10 or not a:
            return False
        ds.append(sign(mean(b) - mean(a)))
    return ds[0] == ds[1] != 0


def finalize_tables(tables: list[SubTable]) -> tuple[list[dict], int, float | None]:
    k_rapor = sum(t.k_table for t in tables)
    zk = z_k(k_rapor)
    return [t.finalize(zk, k_rapor) for t in tables], k_rapor, zk


# --------------------------------------------------------------------------- yil satirlari
def year_rows(items) -> dict:
    """items: [(x, gun, ts_iso)]. Takvim yili = ts'nin ilk 4 hanesi."""
    by: dict[str, list] = {}
    for it in items:
        by.setdefault(it[2][:4], []).append(it)
    rows = []
    for y in sorted(by):
        xs = [i[0] for i in by[y]]
        ds = [i[1] for i in by[y]]
        cm = cluster_mean(xs, ds)
        row = {"yil": y, "n": cm["n"], "G": cm["G"], "ort": cm["m"], "aralik": ([cm["lo"], cm["hi"]] if cm["lo"] is not None else None),
               "toplam": math.fsum(xs),
               "etiket": label_basic(cm["n"], cm["G"])}
        if y == "2026":
            row["not"] = "kısmi (yıl devam ediyor)" if KILIT_ACIK else "kısmi (kilitli dönem hariç)"
        rows.append(row)
    ok = [r for r in rows if r["etiket"] != "yetersiz"]
    pos = None if not ok else sum(1 for r in ok if r["ort"] > 0) / len(ok)
    out = {"rows": rows, "pozitif_yil_orani": pos}
    if len(by) == 1:
        out["not"] = "Tek yıl: 'her koşulda çalışır' denemez."
    return out
