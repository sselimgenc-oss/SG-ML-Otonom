"""Adim 1 (senin PC'nde, SENIN Console bakiyenle): kitap_on.jsonl -> Claude Message Batches (Haiku 5.5, %50 indirimli) -> kartlar.jsonl

Kurulum:  pip install anthropic
Anahtar:  Console'da ayri bir "kitap-tarama" anahtari ac (harcama tavani 10 $). Anahtari SOHBETE YAZMA; yalniz ortam degiskeni:
            PowerShell:  $env:ANTHROPIC_API_KEY = "..."      (yalniz o pencere icin gecerli)
Kullanim:
  python kart_batch.py tahmin  --limit 50          # para harcamaz: kac kitap, tahmini maliyet
  python kart_batch.py gonder  --limit 50 --onay   # pilot: ilk 50 kitap (ML/Algo klasorleri once)
  python kart_batch.py durum                        # batch bitti mi (cogu 1 saat icinde)
  python kart_batch.py al                           # sonuclar -> kartlar.jsonl + GERCEK maliyet
  python kart_batch.py iptal                        # bitmemis batchi durdur + kaydi temizle (yeniden gondermek icin)
  python kart_batch.py gonder --onay                # pilot iyiyse: kalanlarin hepsi (daha once gonderilenler atlanir)

Ciktiyi (kartlar.jsonl) Claude oturumuna yukle; kitap metni degil, yalniz kendi sozlerimizle kartlar.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODEL = "claude-haiku-5-5"
FIYAT_GIRDI, FIYAT_CIKTI = 0.05, 0.25      # $ / milyon token, batch (%50 indirimli), istem <= 100k token
MAX_TOKENS = 6000                          # dusunme de buna dahil
DURUM = Path("batch_durum.json")

SISTEM = """Sen bir algoritmik trading arastirmacisisin. Sana bir kitabin icindekiler bolumu ve ilk sayfalari verilecek.
Bizim bot: Binance USDT-M vadeli; 19 kripto (7/24) + 21 ABD hissesi + 4 emtia (seansli). 8 kural tabanli price-action stratejisi
(trend kirilimi, iki bacakli geri cekilme, sikisma kirilimi, kirilim yeniden testi, sahte kirilim donusu, trend geri cekilmesi,
range kenari, ML adayi) x 4 zaman dilimi (15m/1h/4h/1d). Aday sinyaller (canli gece suzgeci) ridge lojistik regresyonla filtrelenir
(etiket: gerceklesen islemin R > 0 olmasi; gradient boosting/uclu bariyer yalniz arastirma tarafinda; ozellikler: ATR orani, rejim, stop/ATR, R:R, range kenar mesafeleri, yon, seans, varlik sinifi).
Risk: islem basina %1, gunluk %8, basa bas stop + kismi kapama. Maliyet (komisyon+kayma+fonlama) dahil walk-forward test.
Bilinen zayiflik: yon yogunlasmasi (cogu short), meta-label / pozisyon boyutlama / portfoy-korelasyon farkindaligi yok.

YALNIZ su JSON nesnesini dondur (baska metin yok):
{"konu": "kitabin konusu (Turkce, 1 cumle)",
 "tur": "ml_yontem" | "strateji" | "risk" | "dogrulama" | "genel" | "alakasiz",
 "kitap_puani": 0-5 (bizim bota faydasi),
 "okunacak_bolumler": ["en faydali bolum basliklari, en cok 5"],
 "fikirler": [ {"baslik": "kisa Turkce", "tur": "strateji|ml_yontem|ozellik|risk|dogrulama",
               "kural": "test edilebilir kural/yontem, 1-2 cumle, KENDI SOZLERINLE",
               "veri": "gereken veri", "zaman_dilimi": "...",
               "kripto_7_24": "anlamli mi, neden", "maliyet_sonrasi": "evet|belirsiz|hayir + neden",
               "zaten_var": "evet|kismen|hayir", "puan": 0-5} ]}
En cok 6 fikir. Kati ol: bos vaatler, kanitsiz iddialar dusuk puan. Kitapta olmayani uydurma. Alakasizsa fikirler bos liste."""

GENIS_EK = """

GENIS MOD (kullanici istegi): Bu kitaplar scalp/day trade ve 'ilginc/alisilmadik' klasorlerinden. Hicbir seyi atlama.
- Kisa zaman dilimi (1m-5m, gun ici) fikirleri DUSUK PUANLAMA: ileride acilacak kisa vadeli kollar icin degerlendir; zaman_dilimi alanina yaz.
- Alisilmadik, sezgiye ters, yaratici fikirleri ozellikle yakala; her fikre ek alan ekle: "ilginclik": 0-5 (ne kadar ozgun/beyin yakici).
- puan yine bizim bota faydadir; ilginclik ayri olcudur. Genis modda en cok 8 fikir."""


def oku(p: Path) -> list[dict]:
    return [json.loads(s) for s in p.read_text(encoding="utf-8").split("\n") if s.strip()]   # splitlines \u2028 vb. ile boler


def secim(kitaplar: list[dict], limit: int | None, gonderilen: set[str]) -> list[dict]:
    def onem(k):   # ML/Algo klasorleri ve anahtar kelime yogunlugu once
        a = k.get("anahtar", {})
        return (-(a.get("ml", 0) + a.get("strateji", 0) + a.get("risk", 0) + a.get("dogrulama", 0)), k["sha256"])
    kalan = [k for k in sorted(kitaplar, key=onem) if k["sha256"] not in gonderilen]
    return kalan[:limit] if limit else kalan


def icerik(k: dict) -> str:
    return (f"BASLIK: {k.get('baslik')}\nYAZAR: {k.get('yazar')}\nSAYFA: {k.get('sayfa')}\n\n"
            f"ICINDEKILER:\n{k.get('icindekiler') or '(yok)'}\n\nILK SAYFALAR:\n{k.get('ilk_sayfalar', '')}")


def durum_oku() -> dict:
    return json.loads(DURUM.read_text(encoding="utf-8")) if DURUM.exists() else {"batchler": [], "gonderilen": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("komut", choices=["tahmin", "gonder", "durum", "al", "iptal"])
    ap.add_argument("--girdi", type=Path, default=Path("kitap_on.jsonl"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--onay", action="store_true", help="gonder icin zorunlu (para harcar)")
    ap.add_argument("--genis", action="store_true", help="scalp/day/ilginc: kisa vade cezasi yok, ilginclik puani")
    a = ap.parse_args()
    d = durum_oku()
    sistem = SISTEM + (GENIS_EK if a.genis else "")

    if a.komut in ("tahmin", "gonder"):
        sec = secim(oku(a.girdi), a.limit, set(d["gonderilen"]))
        tok = sum(len(sistem) + len(icerik(k)) for k in sec) / 3.0          # kaba: ~3 karakter/token
        tahmin = tok / 1e6 * FIYAT_GIRDI + len(sec) * 2500 / 1e6 * FIYAT_CIKTI
        print(f"{len(sec)} kitap, ~{tok / 1e6:.2f} M girdi token, tahmini maliyet ~{tahmin:.2f} $ (ust sinir icin x1.5 dusun)")
        if a.komut == "tahmin":
            return 0
        if not a.onay:
            print("Gondermek icin --onay ekle.")
            return 1
        import anthropic
        from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
        from anthropic.types.messages.batch_create_params import Request
        client = anthropic.Anthropic()
        b = client.messages.batches.create(requests=[
            Request(custom_id=k["sha256"][:64], params=MessageCreateParamsNonStreaming(
                model=MODEL, max_tokens=MAX_TOKENS, output_config={"effort": "low"}, system=sistem,
                messages=[{"role": "user", "content": icerik(k)}]))
            for k in sec])
        d["batchler"].append(b.id)
        d["gonderilen"] += [k["sha256"] for k in sec]
        DURUM.write_text(json.dumps(d, indent=1), encoding="utf-8")
        print(f"Gonderildi: {b.id} ({len(sec)} kitap). 'durum' ile bak; cogu 1 saat icinde biter.")
        return 0

    import anthropic
    client = anthropic.Anthropic()
    if a.komut == "iptal":   # bitmemis batchleri durdurur, kaydi temizler (yeniden gonderim icin). Bitmis istekler zaten ucretlenmistir.
        for bid in d["batchler"]:
            b = client.messages.batches.retrieve(bid)
            if b.processing_status == "in_progress":
                client.messages.batches.cancel(bid)
                print(f"{bid}: iptal istendi")
            else:
                print(f"{bid}: {b.processing_status} (iptal gerekmedi)")
        DURUM.write_text(json.dumps({"batchler": [], "gonderilen": [], "eski": d["batchler"]}, indent=1), encoding="utf-8")
        print("Kayit temizlendi; simdi 'gonder --genis --onay' ile yeniden gonderebilirsin.")
        return 0
    if a.komut == "durum":
        for bid in d["batchler"]:
            b = client.messages.batches.retrieve(bid)
            c = b.request_counts
            print(f"{bid}: {b.processing_status} | bitti {c.succeeded}, hata {c.errored}, suruyor {c.processing}")
        return 0

    # al
    adlar = {k["sha256"][:64]: k for k in oku(a.girdi)} if a.girdi.exists() else {}
    tin = tout = n_ok = n_err = 0
    with open("kartlar.jsonl", "w", encoding="utf-8") as out:
        for bid in d["batchler"]:
            if client.messages.batches.retrieve(bid).processing_status != "ended":
                print(f"{bid} henuz bitmedi; atlandi")
                continue
            for r in client.messages.batches.results(bid):
                k = adlar.get(r.custom_id, {})
                if r.result.type != "succeeded":
                    n_err += 1
                    continue
                m = r.result.message
                tin += m.usage.input_tokens
                tout += m.usage.output_tokens
                metin = next((b.text for b in m.content if b.type == "text"), "")
                bas, son = metin.find("{"), metin.rfind("}")
                try:
                    kart = json.loads(metin[bas:son + 1])
                except ValueError:
                    kart = {"ham": metin[:2000], "hata": "json_okunamadi"}
                kart.update(baslik_dosya=k.get("baslik"), dosya=k.get("dosya"), klasor=k.get("klasor"), sha256=r.custom_id)
                out.write(json.dumps(kart, ensure_ascii=False) + "\n")
                n_ok += 1
    gercek = tin / 1e6 * FIYAT_GIRDI + tout / 1e6 * FIYAT_CIKTI
    print(f"kartlar.jsonl: {n_ok} kart, {n_err} hata. Token: girdi {tin}, cikti {tout}. GERCEK maliyet ~{gercek:.3f} $")
    return 0


if __name__ == "__main__":
    sys.exit(main())
