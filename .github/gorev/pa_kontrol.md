Sen kidemli bir kantitatif arastirmaci ve yazilim mimarisin. Yalniz okuyabilirsin. Proje: Binance USDT-M vadeli botu "ML Otonom" (kod trader/; kagit = canli).
Ayni 40 price action kitabindan uc model kural cikardi: fikirler/yeni-kollar/kurallar_pa.jsonl (Haiku, 98, yalniz net olanlar), kurallar_pa_sonnet.jsonl ve
kurallar_pa_opus.jsonl (muglak anlatimlar da "yorum" alaninda sayiya cevrildi). Bunlar BUYUK dosyalar: Grep ile "ad"/"alt_tur" alanlarini tarayip grupla, hepsini satir satir okuma.
Ilk karsilastirma (Haiku kurallariyla, varsa): fikirler/gorev/ altinda pa_karsilastir sonucu (Glob ile bul). Formasyon kutuphanesi tasarimi (42 formasyon) ve kullanici kararlari:
fikirler/gorev/2026-11-24-45474500845/gorev_sonuc.md ve kullanici_kararlari.md. Mevcut 7 PA kolu: trader/src/trader_engine/strategies/arms/ (T1 R1 TF1 B1 H2 S1 F1).
GOREV (kontrol + birlestirme):
1. Uc modelin kurallarini setup olarak grupla; her setup icin kac model ve kac kitapta gectigi. Opus/Sonnet'in "yorum"la uydurdugu sayilari ayikla: kitap fikrine sadik mi, makul mu.
   Hatali/uydurma/tekrar kurallari at.
2. Her setup: mevcut 7 kolla ayni / kismen / yok; 42 formasyonla ayni / yok.
3. "Yok" olanlardan mekanik kodlanabilenleri yeni PA formasyonu olarak kesin tanimla (kod adi, giris, stop, hedef, zaman stopu, ileriye bakis kurali). Aile: PA2 (yeni) — kapasite
   kullanici kararindaki gibi aile 6 / formasyon x ZD 3, hepsi tam boy ve ACIK, stopsuzsa 2 ATR stop.
4. Mevcut 7 kola kitaplardan varyant onerileri (kullanici karar verecek), ayri tablo.
Son mesajinda YALNIZ Markdown, sade Turkce: # Price action kontrolu / ## Model karsilastirmasi (kac kural, kac kullanilabilir) / ## Setup tablosu / ## Yeni PA2 formasyonlari (uygulayici icin kesin) / ## Mevcut kollara varyant onerileri / ## Uyarilar
