"""DERİN OKUMA (senin PC'nde, SENIN Console bakiyenle): ML/Algo kitaplarının TAMAMI bölüm bölüm Haiku batch ile okunur.

Kurulum:  pip install pymupdf anthropic   (zaten kurulu)
Anahtar:  ANTHROPIC_API_KEY kalıcı tanımlı (kitap taramasında yaptığın gibi).
Kullanim (her komut ayni klasorde):
  python derin_oku.py parca --klasor "<...>\\Özel - Makine Öğrenmesi 1" --klasor "<...>\\Özel - Algoritmik Trading 1"
                                            # TOKEN YOK: kitaplari ~45k tokenlik parcalara boler -> parcalar.jsonl
  python derin_oku.py tahmin                # para harcamaz: parca sayisi + tahmini maliyet
  python derin_oku.py gonder --onay         # batch gonderir (yarim kalan parcalar atlanir)
  python derin_oku.py durum                 # bitti mi
  python derin_oku.py al                    # sonuc -> derin_kartlar.jsonl + GERCEK maliyet
Ciktiyi (derin_kartlar.jsonl) Claude oturumuna yukle. Kitap metni gonderilmez; yalniz kendi sozlerimizle notlar.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MODEL = "claude-haiku-5-5"
FIYAT_GIRDI, FIYAT_CIKTI = 0.05, 0.25      # $/milyon token, batch, istem <= 100k token
PARCA_KARAKTER = 140_000                   # ~45k token: 100k token ucretinin altinda kalir
MAX_TOKENS = 8000
DURUM = Path("derin_durum.json")

SISTEM = """Sen kıdemli bir kantitatif trading araştırmacısısın. Sana bir kitabın bir BÖLÜMÜ (parçası) verilecek.

BİZİM BOT: Binance USDT-M vadeli, kâğıt (canlı = kâğıtla birebir hazır). 19 kripto (7/24) + 21 ABD hissesi + 4 emtia (seanslı).
8 kural tabanlı price-action stratejisi (trend kırılımı, iki bacaklı geri çekilme, sıkışma kırılımı, kırılım yeniden testi, sahte kırılım
dönüşü, trend geri çekilmesi, aralık kenarı, M1 LLM adayı) x 4 zaman dilimi (15m/1h/4h/1d) = 32 kol. Aday sinyaller kurulum ailesi
başına ridge lojistik regresyonla süzülür (canlı gece süzgeci; etiket: gerçekleşen işlemin R > 0 olması; yalnız alınan işlemlerden öğrenir;
özellikler: ATR oranı, rejim, stop/ATR, R:R, range kenar mesafesi, yön, seans, varlık sınıfı; v2 paketi: hacim, mum şekli, BTC rejimi, fonlama — kapalı).
Gece yeniden eğitim, kurulum ailesi başına en az 10 işlem; gece süzgeci görülmemiş veride sınanmadan devreye girer. Gradient boosting ve üçlü bariyer
etiketi yalnız araştırma tarafındadır (canlı süzgeçte yok). Araştırma tarafı doğrulaması: purge+embargo walk-forward, deflated Sharpe/PBO, deneme kaydı; holdout mühürlü.
Risk: işlem başına %1, açık risk %24, günlük %8, ana paradan %15 kilit.
Az veri: şu an ~55 kâğıt işlem (41'i short — yön yoğunlaşması).

SEÇTİĞİMİZ VE UYGULADIĞIMIZ FİKİRLER (bunları özellikle denetle: kitap ne diyor, biz doğru mu yapıyoruz?):
S1 aynı yön sınırı (en çok 6 aynı yön pozisyon) + yön karnesi
S2 korelasyon grubu: 30 gün 1s getiri korelasyonu >= 0,7 aynı grup; grup başına yön başına en çok 4
S3 kayıp freni: 5 ardışık kayıp ya da günlük %4 → risk yarıya
S4 toplam nominal tavan: kasanın 3 katı
S5 basit rakip kıyası (rastgele giriş, hep short/long, hiç işlem)
S6 gecikme/masraf dayanıklılığı (1-2 mum geç giriş, masraf x1,5-x2)
S7 işlem sırası karıştırma (Monte Carlo) ile en kötü düşüş ve batma olasılığı; en iyi N işlemi çıkar
S8 canlıya geçiş şartları (n>=300, masraf sonrası alt güven sınırı > 0, >=2 rejim, rastgele yüzdelik >= 90)
S9 ML süzgecinde yön özelliğinin ağırlığı denetimi
S10 v2 özellik paketini açıp v1 ile karşılaştırma
S11 LLM haber kolu (başlık → yön/şiddet, saatlik, Haiku)
S12 derin öğrenme kolu (küçük 1D-CNN, 96 saatlik mum, üçlü bariyer etiketi, haftalık eğitim)

YALNIZ şu JSON nesnesini döndür (başka metin yok):
{"bolum_konusu": "bu parçanın konusu (Türkçe, 1 cümle)",
 "ilgili": true|false,
 "yontemler": [ {"baslik": "kısa Türkçe", "ne": "ne işe yarar, 1 cümle",
                 "nasil": "somut adımlar ve SAYISAL ayarlar (pencere, eşik, parametre) — kendi sözlerinle, 1-4 cümle",
                 "tuzaklar": "kitabın uyardığı hatalar/önyargılar", "kanit": "kitap kanıt/deney sunuyor mu, kısaca",
                 "bizimle_ilgisi": ["S1".."S12" ya da "YENI"], "puan": 0-5} ],
 "bizim_uygulamaya_uyari": ["S-numarası: kitaba göre bizim uygulamamızda yanlış/eksik olabilecek somut şey"]}
En çok 6 yöntem. Kitapta olmayanı uydurma. Bölüm alakasızsa ilgili=false, listeler boş. Uzun alıntı yapma."""


def oku(p: Path) -> list[dict]:
    return [json.loads(s) for s in p.read_text(encoding="utf-8").split("\n") if s.strip()]


def durum_oku() -> dict:
    return json.loads(DURUM.read_text(encoding="utf-8")) if DURUM.exists() else {"batchler": [], "gonderilen": []}


def parcala(klasorler: list[Path], cikti: Path) -> int:
    import pymupdf as fitz
    yok = [str(k) for k in klasorler if not k.is_dir()]
    if yok:
        sys.exit("Klasor bulunamadi:\n  " + "\n  ".join(yok))
    pdfler = sorted({p for k in klasorler for p in k.rglob("*") if p.suffix.lower() == ".pdf"})
    print(f"{len(pdfler)} PDF")
    gorulen, n_parca, n_kitap = set(), 0, 0
    with cikti.open("w", encoding="utf-8") as out:
        for i, p in enumerate(pdfler, 1):
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            if h in gorulen:
                continue
            gorulen.add(h)
            try:
                doc = fitz.open(p)
            except Exception:  # noqa: BLE001
                print(f"  acilamadi: {p.name}")
                continue
            try:
                baslik = ((doc.metadata or {}).get("title") or p.stem).strip()
                sayfalar = [(j + 1, doc[j].get_text()) for j in range(doc.page_count)]
            finally:
                doc.close()
            if sum(len(t) for _, t in sayfalar) < 2000:
                print(f"  metin yok (taranmis): {p.name}")
                continue
            n_kitap += 1
            buf, bas = [], None
            def yaz(son):
                nonlocal n_parca, buf, bas
                metin = "".join(buf).strip()
                if metin:
                    pid = f"{h[:40]}_{bas:04d}"
                    out.write(json.dumps({"id": pid, "kitap": baslik, "dosya": p.name, "sayfa": f"{bas}-{son}",
                                          "metin": metin}, ensure_ascii=False) + "\n")
                    n_parca += 1
                buf, bas = [], None
            uzunluk = 0
            for sf, t in sayfalar:
                if bas is None:
                    bas, uzunluk = sf, 0
                buf.append(f"\n[s.{sf}]\n{t}")
                uzunluk += len(t)
                if uzunluk >= PARCA_KARAKTER:
                    yaz(sf)
            if buf:
                yaz(sayfalar[-1][0])
            if i % 10 == 0:
                print(f"  {i}/{len(pdfler)}")
    print(f"Bitti: {n_kitap} kitap -> {n_parca} parca -> {cikti}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("komut", choices=["parca", "tahmin", "gonder", "durum", "al", "iptal"])
    ap.add_argument("--klasor", action="append", type=Path, default=[])
    ap.add_argument("--girdi", type=Path, default=Path("parcalar.jsonl"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--onay", action="store_true")
    a = ap.parse_args()
    if a.komut == "parca":
        return parcala(a.klasor, a.girdi)
    d = durum_oku()

    if a.komut in ("tahmin", "gonder"):
        hepsi = oku(a.girdi)
        sec = [x for x in hepsi if x["id"] not in set(d["gonderilen"])][: a.limit or None]
        tok = sum(len(SISTEM) + len(x["metin"]) for x in sec) / 3.0
        tahmin = tok / 1e6 * FIYAT_GIRDI + len(sec) * 3000 / 1e6 * FIYAT_CIKTI
        print(f"{len(sec)} parca ({len({x['dosya'] for x in sec})} kitap), ~{tok / 1e6:.1f} M girdi token, "
              f"tahmini maliyet ~{tahmin:.2f} $ (ust sinir icin x1.5 dusun)")
        if a.komut == "tahmin":
            return 0
        if not a.onay:
            print("Gondermek icin --onay ekle.")
            return 1
        import anthropic
        from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request
        client = anthropic.Anthropic()
        sistem = [{"type": "text", "text": SISTEM, "cache_control": {"type": "ephemeral"}}]
        for i in range(0, len(sec), 5000):          # batch basina en cok 5000 parca
            dilim = sec[i:i + 5000]
            b = client.messages.batches.create(requests=[
                Request(custom_id=x["id"], params=MessageCreateParamsNonStreaming(
                    model=MODEL, max_tokens=MAX_TOKENS, output_config={"effort": "low"}, system=sistem,
                    messages=[{"role": "user", "content": f"KİTAP: {x['kitap']} (sayfa {x['sayfa']})\n\n{x['metin']}"}]))
                for x in dilim])
            d["batchler"].append(b.id)
            d["gonderilen"] += [x["id"] for x in dilim]
            DURUM.write_text(json.dumps(d, indent=1), encoding="utf-8")
            print(f"Gonderildi: {b.id} ({len(dilim)} parca)")
        print("'durum' ile bak; buyuk batch birkac saat surebilir.")
        return 0

    import anthropic
    client = anthropic.Anthropic()
    if a.komut == "iptal":
        for bid in d["batchler"]:
            if client.messages.batches.retrieve(bid).processing_status == "in_progress":
                client.messages.batches.cancel(bid)
                print(f"{bid}: iptal istendi")
        DURUM.write_text(json.dumps({"batchler": [], "gonderilen": [], "eski": d["batchler"]}, indent=1), encoding="utf-8")
        return 0
    if a.komut == "durum":
        for bid in d["batchler"]:
            b = client.messages.batches.retrieve(bid)
            c = b.request_counts
            print(f"{bid}: {b.processing_status} | bitti {c.succeeded}, hata {c.errored}, suruyor {c.processing}")
        return 0

    bilgi = {x["id"]: x for x in oku(a.girdi)} if a.girdi.exists() else {}
    tin = tout = tcr = n_ok = n_err = 0
    with open("derin_kartlar.jsonl", "w", encoding="utf-8") as out:
        for bid in d["batchler"]:
            if client.messages.batches.retrieve(bid).processing_status != "ended":
                print(f"{bid} henuz bitmedi; atlandi")
                continue
            for r in client.messages.batches.results(bid):
                x = bilgi.get(r.custom_id, {})
                if r.result.type != "succeeded":
                    n_err += 1
                    continue
                m = r.result.message
                tin += m.usage.input_tokens
                tcr += getattr(m.usage, "cache_read_input_tokens", 0) or 0
                tout += m.usage.output_tokens
                metin = next((b.text for b in m.content if b.type == "text"), "")
                bas, son = metin.find("{"), metin.rfind("}")
                try:
                    kart = json.loads(metin[bas:son + 1])
                except ValueError:
                    kart = {"hata": "json_okunamadi", "ham": metin[:1500]}
                kart.update(id=r.custom_id, kitap=x.get("kitap"), dosya=x.get("dosya"), sayfa=x.get("sayfa"))
                out.write(json.dumps(kart, ensure_ascii=False) + "\n")
                n_ok += 1
    gercek = (tin + tcr * 0.1) / 1e6 * FIYAT_GIRDI + tout / 1e6 * FIYAT_CIKTI
    print(f"derin_kartlar.jsonl: {n_ok} parca, {n_err} hata. GERCEK maliyet ~{gercek:.2f} $")
    return 0


if __name__ == "__main__":
    sys.exit(main())
