import csv, json, os, re, sys, time
import pymupdf, anthropic
kok, csvyol = sys.argv[1], sys.argv[2]
N_KONU, PARCA, AZAMI_SAYFA = 15, 25, 300
MODEL = "claude-haiku-5-5"
SORU = """Asagidaki metin bir trading kitabinin {s1}-{s2}. sayfalari. Konu: {konu}.
Gorevin: metinde anlatilan, BILGISAYARLA TEST EDILEBILIR islem kurallarini cikar (mum formasyonu, grafik formasyonu ya da indikatorle giris).
Her kural icin kendi sozlerinle (alinti yapma) yaz: ad, tur (mum/formasyon/indikator), yon (long/short/ikisi),
giris (net kosul: hangi mum/formasyon/indikator degeri, hangi kapanista), stop, hedef/cikis, filtre (trend, hacim vb.),
zaman_dilimi (kitap ne diyor), iddia (kitapta basari orani/getiri varsa), sayfa, netlik (1-5: 5 = koda dokulebilir kadar net).
Muglak, yoruma dayali, sayiya dokulemeyen anlatimlari ALMA. Kural yoksa bos liste dondur.
YALNIZ JSON yaz: {{"kurallar": [{{"ad": "", "tur": "", "yon": "", "giris": "", "stop": "", "hedef": "", "filtre": "", "zaman_dilimi": "", "iddia": "", "sayfa": 0, "netlik": 0}}]}}

METIN:
{metin}"""
satir = list(csv.DictReader(open(csvyol, encoding="utf-8-sig")))
secili, gor = [], set()
for konu in ("mum", "formasyon", "indikator"):
    for r in [x for x in satir if x["konu"] == konu][:N_KONU]:
        if r["dosya"] in gor or r["taranmis_ocrsiz"] == "True":
            continue
        gor.add(r["dosya"]); secili.append(r)
print(len(secili), "kitap secildi")
istek, harita = [], {}
for i, r in enumerate(secili):
    yol = os.path.join(kok, r["klasor"], r["dosya"])
    try:
        doc = pymupdf.open(yol)
    except Exception as e:
        print("acilamadi:", r["dosya"], e); continue
    n = min(doc.page_count, AZAMI_SAYFA)
    for s in range(0, n, PARCA):
        metin = "\n".join(f"[s.{p+1}] " + doc[p].get_text() for p in range(s, min(s + PARCA, n)))
        if len(metin.strip()) < 500:
            continue
        cid = f"k{i:03d}_s{s+1:04d}"
        harita[cid] = {"kitap": r["dosya"], "konu": r["konu"], "s1": s + 1}
        istek.append({"custom_id": cid, "params": {"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user",
                      "content": SORU.format(s1=s + 1, s2=min(s + PARCA, n), konu=r["konu"], metin=metin[:90000])}]}})
    doc.close()
print(len(istek), "parca gonderilecek")
c = anthropic.Anthropic()
b = c.messages.batches.create(requests=istek)
print("batch:", b.id)
json.dump({"batch": b.id, "harita": harita}, open("kural_batch.json", "w", encoding="utf-8"))
while True:
    b = c.messages.batches.retrieve(b.id)
    print(time.strftime("%H:%M"), b.processing_status, b.request_counts)
    if b.processing_status == "ended":
        break
    time.sleep(60)
n_ok = 0
with open("kurallar.jsonl", "w", encoding="utf-8") as f:
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
print("Bitti:", n_ok, "kural -> kurallar.jsonl")
