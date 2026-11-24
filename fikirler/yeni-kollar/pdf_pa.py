"""Price action kurallari: on eleme + Haiku Batch kural cikarma (tek betik; kullanicinin bilgisayarinda; promosyon kredisi).
Kullanim: python pdf_pa.py "<pdfler klasoru>"   Cikti: pa_adaylar.csv, kurallar_pa.jsonl
"""
import csv, json, os, re, sys, time
import pymupdf, anthropic

kok = sys.argv[1]
N_KITAP, PARCA, AZAMI_SAYFA, ON_SAYFA = 40, 25, 2000, 25
MODEL = "claude-haiku-5-5"
PA = ["price action", "fiyat hareketi", "support", "resistance", "destek", "direnc", "direnç", "market structure", "piyasa yapisi",
      "piyasa yapısı", "higher high", "lower low", "swing", "liquidity", "likidite", "stop hunt", "sweep", "supply", "demand",
      "arz", "talep", "order block", "fair value gap", "fvg", "imbalance", "break of structure", "bos", "choch", "smart money",
      "pullback", "geri cekilme", "geri çekilme", "retest", "yeniden test", "range", "yatay", "trend line", "trend cizgisi",
      "trend çizgisi", "false breakout", "sahte kirilim", "sahte kırılım", "wyckoff", "spring", "upthrust", "al brooks", "ict"]
STRATEJI = ["strategy", "strateji", "entry", "giris", "giriş", "stop loss", "take profit", "rule", "kural", "setup", "kurulum",
            "risk reward", "win rate", "backtest"]
SORU = """Asagidaki metin bir trading kitabinin {s1}-{s2}. sayfalari. Konu: PRICE ACTION (fiyat hareketi).
Gorevin: metinde anlatilan, BILGISAYARLA TEST EDILEBILIR price action islem kurallarini cikar: destek/direnc tepkisi, trend yapisi
(yuksek tepe/dip), geri cekilme girisleri, kirilim ve yeniden test, sahte kirilim/likidite supurmesi, arz-talep bolgesi, order block,
fair value gap, yatay piyasa kenari, trend cizgisi, Wyckoff spring/upthrust, kirilim sonrasi devam vb.
Her kural icin kendi sozlerinle (alinti yapma) yaz: ad, alt_tur, yon (long/short/ikisi), giris (net kosul, hangi kapanista),
stop, hedef/cikis, filtre (trend, hacim, zaman), zaman_dilimi, iddia (kitapta basari orani/getiri varsa), sayfa, netlik (1-5: 5 = koda dokulebilir kadar net).
Muglak, yoruma dayali, sayiya dokulemeyen anlatimlari ALMA. Kural yoksa bos liste dondur.
YALNIZ JSON yaz: {{"kurallar": [{{"ad": "", "alt_tur": "", "yon": "", "giris": "", "stop": "", "hedef": "", "filtre": "", "zaman_dilimi": "", "iddia": "", "sayfa": 0, "netlik": 0}}]}}

METIN:
{metin}"""


def say(metin, kel):
    return sum(len(re.findall(r"(?<![a-zçğıöşü])" + re.escape(k) + r"(?![a-zçğıöşü])", metin)) for k in kel)


pdfler = [os.path.join(d, f) for d, _, fs in os.walk(kok) for f in fs if f.lower().endswith(".pdf")]
print(len(pdfler), "PDF bulundu, on eleme basliyor (birkac dakika)")
aday = []
for i, yol in enumerate(pdfler, 1):
    if i % 200 == 0:
        print(f"  {i}/{len(pdfler)}")
    try:
        doc = pymupdf.open(yol)
        metin = " ".join(doc[p].get_text() for p in range(min(ON_SAYFA, doc.page_count))).lower()
        doc.close()
    except Exception:
        continue
    if len(metin.strip()) < 200:
        continue
    ad = os.path.basename(yol).lower()
    k_ad, k_m = say(ad, PA), say(metin, PA)
    if k_ad or k_m >= 15:
        aday.append({"skor": 20 * k_ad + k_m + 0.5 * say(metin, STRATEJI), "yol": yol, "dosya": os.path.basename(yol)})
aday = sorted(aday, key=lambda r: -r["skor"])[:N_KITAP]
with open("pa_adaylar.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["skor", "dosya", "yol"]); w.writeheader(); w.writerows(aday)
print(len(aday), "kitap secildi (pa_adaylar.csv)")

istek, harita = [], {}
for i, r in enumerate(aday):
    try:
        doc = pymupdf.open(r["yol"])
    except Exception as e:
        print("acilamadi:", r["dosya"], e); continue
    n = min(doc.page_count, AZAMI_SAYFA)
    for s in range(0, n, PARCA):
        metin = "\n".join(f"[s.{p+1}] " + doc[p].get_text() for p in range(s, min(s + PARCA, n)))
        if len(metin.strip()) < 500:
            continue
        cid = f"p{i:03d}_s{s+1:04d}"
        harita[cid] = {"kitap": r["dosya"], "konu": "price_action", "s1": s + 1}
        istek.append({"custom_id": cid, "params": {"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user",
                      "content": SORU.format(s1=s + 1, s2=min(s + PARCA, n), metin=metin[:90000])}]}})
    doc.close()
print(len(istek), "parca gonderilecek")
c = anthropic.Anthropic()
b = c.messages.batches.create(requests=istek)
print("batch:", b.id)
json.dump({"batch": b.id, "harita": harita}, open("pa_batch.json", "w", encoding="utf-8"))
while True:
    b = c.messages.batches.retrieve(b.id)
    print(time.strftime("%H:%M"), b.processing_status, b.request_counts)
    if b.processing_status == "ended":
        break
    time.sleep(60)
n_ok = 0
with open("kurallar_pa.jsonl", "w", encoding="utf-8") as f:
    for s in c.messages.batches.results(b.id):
        if s.result.type != "succeeded":
            continue
        t = "".join(x.text for x in s.result.message.content if x.type == "text")
        m = re.search(r"\{.*\}", t, re.S)
        try:
            ks = json.loads(m.group(0)).get("kurallar", []) if m else []
        except json.JSONDecodeError:
            ks = []
        for k in ks:
            k.update(harita[s.custom_id]); f.write(json.dumps(k, ensure_ascii=False) + "\n"); n_ok += 1
print("Bitti:", n_ok, "kural -> kurallar_pa.jsonl")
