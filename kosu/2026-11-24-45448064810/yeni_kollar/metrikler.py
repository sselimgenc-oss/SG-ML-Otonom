"""Metrikler: islem tablosundan (dict of numpy) ozet."""
from __future__ import annotations

import numpy as np

TUR = ["stop", "hedef", "zaman"]


def yil_of(ns):
    return (np.asarray(ns, dtype="int64").astype("datetime64[ns]").astype("datetime64[Y]").astype(int) + 1970)


def ozet(T: dict, saat_mum: float, cift_adlari: list[str], detay: bool = True) -> dict:
    """T: R, tur, tutma, cift (idx), t_giris (ns), t_cikis (ns). saat_mum: mum suresi saat."""
    R = np.asarray(T["R"], float)
    n = len(R)
    if n == 0:
        return {"islem": 0}
    poz, neg = R[R > 0].sum(), -R[R < 0].sum()
    sira = np.argsort(np.asarray(T["t_cikis"]), kind="stable")
    cum = np.cumsum(R[sira])
    dusus = float((np.maximum.accumulate(np.r_[0.0, cum])[1:] - cum).max())
    out = {"islem": int(n), "kazanma_orani": float((R > 0).mean()), "ort_net_R": float(R.mean()), "toplam_net_R": float(R.sum()),
           "kar_faktoru": float(poz / neg) if neg > 0 else None, "en_buyuk_dusus_R": dusus,
           "ort_tutma_mum": float(np.mean(T["tutma"])), "ort_tutma_saat": float(np.mean(T["tutma"]) * saat_mum),
           "cikis_turleri": {TUR[k]: int((np.asarray(T["tur"]) == k).sum()) for k in range(3)}}
    yil = yil_of(T["t_giris"])
    out["yillik_toplam_R"] = {str(y): float(R[yil == y].sum()) for y in sorted(set(yil.tolist()))}
    if detay:
        ci = np.asarray(T["cift"])
        tab = sorted(((float(R[ci == k].sum()), cift_adlari[k], int((ci == k).sum())) for k in set(ci.tolist())), reverse=True)
        fmt = lambda x: {"cift": x[1], "toplam_R": x[0], "islem": x[2]}  # noqa: E731
        out["cift_en_iyi5"] = [fmt(x) for x in tab[:5]]
        out["cift_en_kotu5"] = [fmt(x) for x in tab[::-1][:5]]
        out["cift_sayisi"] = len(tab)
    return out
