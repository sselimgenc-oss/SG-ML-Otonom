"""Price action kurallari, 2. tur: ayni 40 kitap (pa_adaylar.csv), Sonnet ve Opus ile Batch; muglak anlatimlar da yorumlanip kurala cevrilir."""
import csv, json, re, time
import pymupdf, anthropic

PARCA, AZAMI_SAYFA = 25, 2000
MODELLER = {"sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
SORU = """Asagidaki metin bir trading kitabinin {s1}-{s2}. sayfalari. Konu: PRICE ACTION (fiyat hareketi).
Gorevin: metinde anlatilan price action islem setuplarini BILGISAYARLA TEST EDILEBILIR kurallara cevirmek: destek/direnc tepkisi, trend yapisi,
geri cekilme, kirilim ve yeniden test, sahte kirilim/likidite supurmesi, arz-talep bolgesi, order block, fair value gap, yatay piyasa kenari,
trend cizgisi, Wyckoff spring/upthrust, devam formasyonlari vb.
Kitap kurali sozle/muglak anlatiyorsa ATLAMA: anlatilan fikri en makul sayisal karsiliklarla (or. "guclu mum" -> govde >= aralik x 0,6; "yakin" -> 0,3 ATR)
kesin kurala cevir ve "yorum" alanina hangi sayilari senin sectigini yaz. Yalniz hic islem fikri olmayan (felsefe, psikoloji) metni alma.
Her kural icin kendi sozlerinle (alinti yapma): ad, alt_tur, yon (long/short/ikisi), giris (net kosul, hangi kapanista), stop, hedef/cikis,
filtre, zaman_dilimi, iddia (kitapta basari orani/getiri varsa), sayfa, netlik (1-5: kitabin kendi netligi), yorum (senin doldurdugun sayilar; yoksa bos).
YALNIZ JSON yaz: {{"kurallar": [{{"ad": "", "alt_tur": "", "yon": "", "giris": "", "stop": "", "hedef": "", "filtre": "", "zaman_dilimi": "", "iddia": "", "sayfa": 0, "netlik": 0, "yorum": ""}}]}}

METIN:
{metin}"""

aday = list(csv.DictReader(open("pa_adaylar.csv", encoding="utf-8-sig")))
print(len(aday), "kitap (pa_adaylar.csv)")
parcalar, harita = [], {}
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
        parcalar.append((cid, SORU.format(s1=s + 1, s2=min(s + PARCA, n), metin=metin[:90000])))
    doc.close()
print(len(parcalar), "parca, her model icin ayri batch")
c = anthropic.Anthropic()
batchler = {}
for ad, model in MODELLER.items():
    b = c.messages.batches.create(requests=[{"custom_id": cid, "params": {"model": model, "max_tokens": 8000,
                                   "messages": [{"role": "user", "content": soru}]}} for cid, soru in parcalar])
    batchler[ad] = b.id
    print(ad, "batch:", b.id)
json.dump({"batchler": batchler, "harita": harita}, open("pa2_batch.json", "w", encoding="utf-8"))
bekleyen = dict(batchler)
while bekleyen:
    for ad, bid in list(bekleyen.items()):
        b = c.messages.batches.retrieve(bid)
        print(time.strftime("%H:%M"), ad, b.processing_status, b.request_counts)
        if b.processing_status != "ended":
            continue
        n_ok = 0
        with open(f"kurallar_pa_{ad}.jsonl", "w", encoding="utf-8") as f:
            for s in c.messages.batches.results(bid):
                if s.result.type != "succeeded":
                    continue
                t = "".join(x.text for x in s.result.message.content if x.type == "text")
                m = re.search(r"\{.*\}", t, re.S)
                try:
                    ks = json.loads(m.group(0)).get("kurallar", []) if m else []
                except json.JSONDecodeError:
                    ks = []
                for k in ks:
                    k.update(harita[s.custom_id]); k["model"] = ad
                    f.write(json.dumps(k, ensure_ascii=False) + "\n"); n_ok += 1
        print("Bitti:", ad, n_ok, "kural ->", f"kurallar_pa_{ad}.jsonl")
        del bekleyen[ad]
    if bekleyen:
        time.sleep(60)
