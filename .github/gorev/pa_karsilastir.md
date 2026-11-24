Sen kidemli bir kantitatif arastirmaci ve yazilim mimarisin. Yalniz okuyabilirsin. Proje: Binance USDT-M vadeli botu "ML Otonom" (kod trader/; kagit = canli).
KULLANICI ISTEGI: mevcut 7 price action kolunun (T1 R1 TF1 B1 H2 S1 F1; trader/src/trader_engine/strategies/arms/ ve trader_core/signals.py) KAPSAMADIGI, kitaplarda
gecen price action setuplarini bul ve bota ekle.
KAYNAK: fikirler/yeni-kollar/kurallar_pa.jsonl (18 kitap, 98 kural; netlik >= 3 olan ~51'i kodlanabilir). Ayrica fikirler/yeni-kollar/kurallar.jsonl icindeki
price action niteligindeki kurallar (destek-direnc, trend yapisi, seviye reddi; mum/formasyon etiketli olsa da).
Formasyon kutuphanesi tasarimi (MF1/GF1/IN1; 42 formasyon): fikirler/gorev/2026-11-24-45474500845/gorev_sonuc.md (bu dalda yoksa `onceki/` disinda; Glob ile ara;
bulamazsan yalniz kurallarla calis ve belirt).
GOREV:
1. Her PA kuralini grupla (setup). Her grup icin: kural/kitap sayisi; mevcut 7 koldan hangisiyle ayni / kismen ayni / HICBIRINDE YOK; kutuphanedeki 42 formasyondan biriyle ayni mi.
2. "Hicbirinde yok" olanlardan mekanik olarak kodlanabilenleri yeni PA formasyonu olarak tanimla: kod adi, giris, stop, hedef, zaman stopu, ileriye bakis kurali.
   Kutuphane yapisina uygun yaz (yeni aile PA2 mi, yoksa GF1'e mi girer: onerini gerekcele). Kullanici karari: hepsi ACIK baslar, bot formasyon x ZD bazinda ogrenir.
3. Mevcut 7 kolda kitaplarin onerdigi ama kolda eksik bir varyant varsa (or. T1'e farkli giris) ayri tablo; bunlari motora ekleme onerisi olarak yaz, kullanici karar verir.
Son mesajinda YALNIZ Markdown, sade Turkce: # Price action karsilastirmasi / ## Grup tablosu / ## Yeni PA formasyonlari (uygulayici icin kesin) / ## Mevcut kollara varyant onerileri / ## Uyarilar
