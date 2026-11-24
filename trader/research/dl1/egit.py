#!/usr/bin/env python3
"""DL1 gece egitimi, tek zaman dilimi (15m | 1h | 4h | 1d; YALNIZ GitHub Actions; PyTorch yalniz burada; motor/trader requirements kilidi torch'a bagli DEGIL).

  python research/dl1/egit.py --tf 1h --kesim 2026-11-23 --cikti models/dl1 --rapor var/dl1_rapor

Akis: Vision indir (43 enstruman, kesim oncesi) -> ornek tablosu -> walk-forward (purge/embargo; olcek yalniz egitim diliminden;
ayni mumda tum enstrumanlar ayni dilimde) -> kalite kapisi METRIGI (toplam: en ust %2 puanli adaylarda masraf sonrasi ort. R > 0 VE dilimlerin >= %60'i pozitif;
sinif bazinda satirlar yalniz rapor) -> nihai model (tum veri) -> numpy-PyTorch parite (< 1e-5) -> paket `DL1@<tf>.json`.
24.11 kullanici karari: kapi YAYINI ENGELLEMEZ (rapor/ozet bilgisi); mevcut paketle iyilesme karsilastirmasi yok; her gece en yeni model yayinlanir.
Paket YALNIZ parite basarisizsa yazilmaz (butunluk). Rapor (json + md) `dl1_rapor_<tf>.*`. Cikis kodu: 0 paket yazildi (ya da icerik ayni), 2 hata
(parite basarisizligi dahil). `PAKET_YAZILDI=1|0` GITHUB_OUTPUT'a yazilir."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cekirdek as C  # noqa: E402
import veri as V  # noqa: E402
from trader_engine import dl1_cikarim as DL  # noqa: E402


def torch_model(agirlik=None, dtype=None):
    import torch
    import torch.nn as nn

    class Ag(nn.Module):
        def __init__(self):
            super().__init__()
            self.c1 = nn.Conv1d(DL.N_KANAL, 32, 5)
            self.c2 = nn.Conv1d(32, 48, 5, stride=2)
            self.c3 = nn.Conv1d(48, 64, 5, stride=2)
            self.d1 = nn.Linear(128, 64)
            self.head = nn.Linear(64, 3)

        def forward(self, x):                       # x (B, T, C)
            x = x.transpose(1, 2)
            x = torch.relu(self.c3(torch.relu(self.c2(torch.relu(self.c1(x))))))
            z = torch.cat([x.mean(dim=2), x.amax(dim=2)], dim=1)
            return self.head(torch.relu(self.d1(z)))

    m = Ag()
    if agirlik is not None:
        sd = {}
        for ad in ("c1", "c2", "c3", "d1", "head"):
            sd[ad + ".weight"] = torch.tensor(agirlik[ad + ".w"], dtype=torch.float64)
            sd[ad + ".bias"] = torch.tensor(agirlik[ad + ".b"], dtype=torch.float64)
        m = m.double()
        m.load_state_dict(sd)
    if dtype is not None:
        m = m.to(dtype)
    return m


def agirlik_cikar(m) -> dict[str, np.ndarray]:
    sd = {k: v.detach().cpu().double().numpy() for k, v in m.state_dict().items()}
    return {ad + ".w": sd[ad + ".weight"] for ad in ("c1", "c2", "c3", "d1", "head")} | \
           {ad + ".b": sd[ad + ".bias"] for ad in ("c1", "c2", "c3", "d1", "head")}


def torch_trainer(epoch: int = 4, parti: int = 512, lr: float = 2e-3, vol_agirlik: float = 0.1, evre_log=None):
    import torch
    import torch.nn.functional as Fn

    def trainer(v: C.Veri, rows: np.ndarray, ort, std, tohum: int):
        torch.manual_seed(tohum)
        torch.set_num_threads(max(1, os.cpu_count() or 1))
        xs = C.olcekli_x(v, ort, std)
        m = torch_model().float()
        opt = torch.optim.AdamW(m.parameters(), lr=lr, weight_decay=1e-4)
        y = torch.tensor(v.y[rows].astype(np.float32))
        vol = torch.tensor(v.vol[rows].astype(np.float32))
        g = v.g[rows]
        rg = np.random.default_rng(tohum)
        for e in range(epoch):
            for gr in opt.param_groups:
                gr["lr"] = lr * (0.5 if e >= epoch // 2 else 1.0)
            perm = rg.permutation(len(rows))
            tot = 0.0
            for a in range(0, len(perm), parti):
                b = perm[a:a + parti]
                x = torch.from_numpy(C.pencereler(xs, g[b]))
                z = m(x)
                loss = Fn.binary_cross_entropy_with_logits(z[:, :2], y[b]) + vol_agirlik * Fn.smooth_l1_loss(z[:, 2], vol[b])
                opt.zero_grad()
                loss.backward()
                opt.step()
                tot += float(loss) * len(b)
            if evre_log:
                evre_log(f"  epoch {e + 1}/{epoch} kayip={tot / len(perm):.4f}")
        return agirlik_cikar(m)

    return trainer


def parite(v: C.Veri, paket_agirlik: dict, ort, std, n: int = 2000, tohum: int = C.TOHUM) -> dict:
    """Paketteki (yuvarlanmis) agirliklarla torch (float64) ve numpy ileri gecis farki; olasiliklar ve oynaklik cikisi icin en buyuk mutlak fark."""
    import torch
    rows = np.sort(np.random.default_rng(tohum).choice(len(v.g), min(n, len(v.g)), replace=False))
    xs = C.olcekli_x(v, ort, std)
    w = C.pencereler(xs, v.g[rows]).astype(np.float64)
    zn = DL.ileri(paket_agirlik, w)
    m = torch_model(paket_agirlik)
    with torch.no_grad():
        zt = m(torch.from_numpy(w)).numpy()
    return {"n": int(len(rows)), "max_fark_olasilik": float(np.abs(DL.sigmoid(zn[:, :2]) - DL.sigmoid(zt[:, :2])).max()),
            "max_fark_logit": float(np.abs(zn - zt).max())}


def rapor_yaz(rapor: dict, dizin: Path) -> None:
    dizin.mkdir(parents=True, exist_ok=True)
    tf = rapor.get("tf", "1h")
    (dizin / f"dl1_rapor_{tf}.json").write_text(json.dumps(rapor, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    k = rapor.get("kapi", {})
    s = [f"# DL1@{tf} egitim raporu ({rapor['kesim']})", "", f"- Kapi (YALNIZ BILGI; yayini engellemez): **{'GECTI' if k.get('gecti') else 'GECMEDI'}**; toplam ort. R = {k.get('toplam_ort_r')}, "
         f"aday = {k.get('toplam_aday')}, pozitif dilim = {k.get('pozitif_dilim')}/{k.get('dilim_sayisi')} ({k.get('pozitif_oran')})",
         f"- Karar: **{'YAYINLA' if (rapor.get('karar') or {}).get('yayinla') else 'YAYIN YOK'}** ({(rapor.get('karar') or {}).get('neden')})",
         f"- Kapida korunan siniflar (bilgi): {k.get('korunan')}; kapida dusen (bilgi; kapsamdan cikarilmaz): {k.get('dusen')}",
         f"- Parite: {rapor.get('parite')}", f"- Paket yazildi: {rapor.get('paket_yazildi')}", "", "| sinif | aday | ort. R | pozitif dilim / adayli dilim |", "|---|---|---|---|"]
    for ad, x in (k.get("siniflar") or {}).items():
        s.append(f"| {ad} | {x['n']} | {x['ort_r']} | {x['poz_dilim']}/{x['aday_dilim']} |")
    (dizin / f"dl1_rapor_{tf}.md").write_text("\n".join(s) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--tf", choices=list(C.AYARLAR), default="1h", help="egitilecek zaman dilimi (varsayilan 1h)")
    ap.add_argument("--kesim", default=datetime.now(timezone.utc).date().isoformat(), help="YYYY-MM-DD (dislayici; varsayilan bugun UTC)")
    ap.add_argument("--bas-ay", default=None, help="YYYY-MM (varsayilan: zaman dilimine gore cekirdek.AYARLAR)")
    ap.add_argument("--ham", type=Path, default=C.ROOT / "var" / "vision_raw")
    ap.add_argument("--cikti", type=Path, default=C.ROOT / "models" / "dl1")
    ap.add_argument("--rapor", type=Path, default=C.ROOT / "var" / "dl1_rapor")
    ap.add_argument("--epoch", type=int, default=4)
    ap.add_argument("--epoch-son", type=int, default=6)
    args = ap.parse_args(argv)
    if not C.KILIT_ACIK:
        print("HATA: kilit kapali; DL1 egitimi calismaz", file=sys.stderr)
        return 2
    tf = args.tf
    ayar = C.AYARLAR[tf]
    kesim_d = date.fromisoformat(args.kesim)
    kesim = pd.Timestamp(kesim_d, tz="UTC")
    siniflar = C.sinif_haritasi()
    seriler = V.indir(list(siniflar), args.bas_ay or ayar.bas_ay, kesim_d, args.ham, tf=tf)
    v = C.veri_kur(seriler, {p: siniflar[p] for p in seriler}, C.maliyet_tablosu(), C.cikis_kipleri(tf=tf), bar_ns=ayar.bar_ns)
    print(f"tf={tf} ornek={len(v.g)} cift={len(v.ciftler)}")
    dil = C.yuru(v, torch_trainer(args.epoch, evre_log=print), kesim, ayar=ayar)
    k = C.kapi(dil)
    parite_hata = False
    rapor = {"tf": tf, "kesim": args.kesim, "ornek": int(len(v.g)), "ciftler": v.ciftler, "kapi": k, "dilimler": C.temiz(dil), "paket_yazildi": False}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    hedef = args.cikti / f"{DL.arm_id(tf)}.json"
    karar = C.yayin_karari(k)                       # 24.11: kapi engellemez; her gece en yeni model yayinlanir
    rapor["karar"] = karar
    rapor["parite"] = None
    if karar["yayinla"]:
        rows = C.alt_kume(np.arange(len(v.g)), C.EGIT_TAVAN_SON, C.TOHUM)
        ort, std = C.olcekleyici(v, rows)
        ag = torch_trainer(args.epoch_son, evre_log=print)(v, rows, ort, std, C.TOHUM)
        pk = DL.agirlik_ac(DL.agirlik_paketle(ag))                    # yuvarlanmis, gemiyi terk edecek agirliklar
        tr = C.alt_kume(rows, C.ESIK_ORNEK, C.TOHUM)
        esik = float(np.percentile(C.puanlar(v, tr, pk, ort, std).ravel(), C.ESIK_YUZDELIK))
        par = parite(v, pk, ort, std)
        rapor["parite"] = par
        if par["max_fark_olasilik"] < C.PARITE_TOL:
            met = {"tf": tf, "kesim": args.kesim, "ornek": int(len(v.g)), "dilimler": len(dil), "kapi": {x: k[x] for x in ("toplam_ort_r", "toplam_aday", "pozitif_oran", "siniflar")},
                   "parite": par, "parametre": DL.parametre_sayisi(), "ciftler": len(v.ciftler), "karar": karar}
            rapor["paket_yazildi"] = C.paket_yaz(C.paket_kur(pk, ort, std, esik, v.siniflar, k, now, met, tf), hedef)
        else:
            parite_hata = True
    rapor_yaz(rapor, args.rapor)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"paket_yazildi={'1' if rapor['paket_yazildi'] else '0'}\n")
    print(f"tf={tf} kapi gecti={rapor['kapi']['gecti']} (bilgi) paket_yazildi={rapor['paket_yazildi']}")
    if parite_hata:
        print("HATA: numpy-PyTorch parite basarisiz; paket yazilmadi", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
