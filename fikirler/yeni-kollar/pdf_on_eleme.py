"""Yeni kollar icin PDF on elemesi (TOKEN YOK, API YOK). Kullanicinin bilgisayarinda calisir.

Uc konu icin aday PDF'leri bulur:
  1 mum       : mum formasyonlari (doji, cekic, yutan, sabah yildizi...)
  2 formasyon : grafik formasyonlari (OBO, TOBO, ucgen, bayrak, flama, kama, ikili tepe...)
  3 indikator : indikatorler (RSI, MACD, Bollinger, hacim, stokastik, ADX...)
Her PDF'in dosya adina ve ilk 25 sayfasina bakar; konu kelimeleri + strateji kelimeleri (giris, stop, kural, backtest) sayilir.
Cikti: pdf_adaylar.csv (konu basina en iyi 40). PDF'ler hicbir yere gonderilmez.

Kullanim: python pdf_on_eleme.py "<pdfler klasoru>"
"""
import csv
import os
import re
import sys

import fitz  # pymupdf

KONULAR = {
    "mum": ["candlestick", "candle", "mum formasyon", "doji", "hammer", "cekic", "çekiç", "engulfing", "yutan", "harami",
            "morning star", "sabah yildizi", "sabah yıldızı", "evening star", "shooting star", "kayan yildiz", "kayan yıldız",
            "pin bar", "pinbar", "marubozu", "japanese", "japon", "hanging man", "asilan adam", "asılan adam", "three white soldiers"],
    "formasyon": ["chart pattern", "formasyon", "head and shoulders", "omuz bas omuz", "omuz baş omuz", "obo", "tobo",
                  "double top", "ikili tepe", "double bottom", "ikili dip", "triangle", "ucgen", "üçgen", "flag", "bayrak",
                  "flama", "pennant", "wedge", "kama", "cup and handle", "fincan", "rectangle", "dikdortgen", "dikdörtgen",
                  "breakout", "kirilim", "kırılım"],
    "indikator": ["rsi", "macd", "bollinger", "stochastic", "stokastik", "moving average", "hareketli ortalama", "volume",
                  "hacim", "obv", "adx", "ichimoku", "vwap", "cci", "williams", "momentum", "indicator", "indikator",
                  "indikatör", "oscillator", "osilator", "osilatör", "divergence", "uyumsuzluk"],
}
STRATEJI = ["strategy", "strateji", "entry", "giris", "giriş", "stop loss", "stop-loss", "take profit", "kar al", "kâr al",
            "rule", "kural", "backtest", "geri test", "win rate", "risk reward", "risk/reward", "trading system", "işlem sistemi"]
SAYFA = 25


def say(metin, kelimeler):
    return sum(len(re.findall(r"(?<![a-zçğıöşü])" + re.escape(k) + r"(?![a-zçğıöşü])", metin)) for k in kelimeler)


def main(kok):
    satirlar = []
    pdfler = [os.path.join(d, f) for d, _, fs in os.walk(kok) for f in fs if f.lower().endswith(".pdf")]
    print(f"{len(pdfler)} PDF bulundu")
    for i, yol in enumerate(pdfler, 1):
        if i % 100 == 0:
            print(f"  {i}/{len(pdfler)}")
        ad = os.path.basename(yol).lower()
        try:
            doc = fitz.open(yol)
            sayfa = doc.page_count
            metin = " ".join(doc[p].get_text() for p in range(min(SAYFA, sayfa))).lower()
            doc.close()
        except Exception:
            continue
        taranmis = len(metin.strip()) < 200
        st = say(metin, STRATEJI)
        for konu, kel in KONULAR.items():
            k_ad = say(ad, kel)
            k_metin = say(metin, kel)
            skor = 20 * k_ad + k_metin + 0.5 * st
            if k_ad or k_metin >= 10:
                satirlar.append({"konu": konu, "skor": round(skor, 1), "ad_eslesme": k_ad, "konu_kelime": k_metin,
                                 "strateji_kelime": st, "sayfa": sayfa, "taranmis_ocrsiz": taranmis,
                                 "dosya": os.path.basename(yol), "klasor": os.path.relpath(os.path.dirname(yol), kok)})
    cikti = []
    for konu in KONULAR:
        cikti += sorted([r for r in satirlar if r["konu"] == konu], key=lambda r: -r["skor"])[:40]
    with open("pdf_adaylar.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(cikti[0].keys()) if cikti else ["konu"])
        w.writeheader()
        w.writerows(cikti)
    for konu in KONULAR:
        print(konu, sum(1 for r in cikti if r["konu"] == konu), "aday")
    print("Bitti: pdf_adaylar.csv")


if __name__ == "__main__":
    main(sys.argv[1])
