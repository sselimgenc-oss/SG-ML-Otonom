"""Adim 0 (TOKEN YOK, yalniz senin PC'nde): PDF arsivinden kitap basina ozet bilgi cikarir.

Kurulum:   pip install pymupdf
Kullanim:  python kitap_on.py --klasor "C:\\Users\\...\\Masaüstü\\pdfler\\Özel - Makine Öğrenmesi 1" --klasor "...\\Özel - Algoritmik Trading 1"
           (--klasor birden cok verilebilir; alt klasorler de taranir)
Cikti:     kitap_on.jsonl  (her satir bir kitap: dosya, sha256, sayfa, baslik, icindekiler, ilk sayfalar metni, anahtar kelime sayilari)
           taranmis_ocr_yok.txt  (metni cikmayan, taranmis PDF'ler: kartlara girmez)

Ayni kitap farkli adla iki kez varsa (ayni sha256) yalniz biri yazilir. PDF'ler hicbir yere gonderilmez.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    sys.exit("pymupdf yok: once  pip install pymupdf")

ILK_SAYFA = 15            # karta giden metin: ilk 15 sayfa (icindekiler + giris genelde burada)
METIN_SINIRI = 40_000     # karakter (kitap basina ~10k token)
SAYIM_SAYFA = 80          # anahtar kelime sayimi icin taranan sayfa
ANAHTAR = {
    "ml": r"machine learning|neural|lstm|transformer|gradient boost|xgboost|random forest|reinforcement|makine ö[gğ]renmesi",
    "strateji": r"strategy|strateji|breakout|momentum|mean reversion|trend follow|swing|scalp",
    "risk": r"position siz|kelly|drawdown|risk management|stop loss|volatility target",
    "dogrulama": r"backtest|walk.forward|overfit|cross.validation|out.of.sample|look.ahead",
    "kripto": r"crypto|bitcoin|kripto|futures|perpetual|funding",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def kitap(p: Path) -> dict | None:
    try:
        doc = fitz.open(p)
    except Exception as e:  # noqa: BLE001
        return {"dosya": str(p), "hata": f"acilamadi: {type(e).__name__}"}
    try:
        meta = doc.metadata or {}
        toc = [f"{'  ' * (lvl - 1)}{baslik} (s.{sf})" for lvl, baslik, sf in doc.get_toc()[:200]]
        ilk = "\n".join(doc[i].get_text() for i in range(min(ILK_SAYFA, doc.page_count)))
        sayim_metin = ilk + "\n".join(doc[i].get_text() for i in range(ILK_SAYFA, min(SAYIM_SAYFA, doc.page_count)))
        return {
            "dosya": str(p),
            "klasor": p.parent.name,
            "sayfa": doc.page_count,
            "baslik": (meta.get("title") or p.stem).strip(),
            "yazar": (meta.get("author") or "").strip(),
            "icindekiler": "\n".join(toc),
            "ilk_sayfalar": ilk[:METIN_SINIRI],
            "anahtar": {k: len(re.findall(v, sayim_metin, re.I)) for k, v in ANAHTAR.items()},
            "taranmis": len(sayim_metin.strip()) < 500,
        }
    finally:
        doc.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--klasor", action="append", required=True, type=Path)
    ap.add_argument("--cikti", type=Path, default=Path("kitap_on.jsonl"))
    a = ap.parse_args()
    yok = [str(k) for k in a.klasor if not k.is_dir()]
    if yok:
        sys.exit("Klasor bulunamadi:\n  " + "\n  ".join(yok) + "\nDosya Gezgini adres cubugundaki yolu tirnak icinde ver.")
    pdfler = sorted({p for k in a.klasor for p in k.rglob("*") if p.suffix.lower() == ".pdf"})
    print(f"{len(pdfler)} PDF bulundu")
    gorulen, n_yaz, taranmis = set(), 0, []
    with a.cikti.open("w", encoding="utf-8") as out:
        for i, p in enumerate(pdfler, 1):
            h = sha256(p)
            if h in gorulen:
                continue
            gorulen.add(h)
            k = kitap(p)
            k["sha256"] = h
            if k.get("hata") or k.get("taranmis"):
                taranmis.append(f"{p}  ({k.get('hata') or 'metin yok - taranmis'})")
                continue
            out.write(json.dumps(k, ensure_ascii=False) + "\n")
            n_yaz += 1
            if i % 50 == 0:
                print(f"  {i}/{len(pdfler)}")
    Path("taranmis_ocr_yok.txt").write_text("\n".join(taranmis), encoding="utf-8")
    print(f"Bitti: {n_yaz} kitap -> {a.cikti}; {len(pdfler) - len(gorulen)} kopya atlandi; {len(taranmis)} taranmis/acilamayan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
