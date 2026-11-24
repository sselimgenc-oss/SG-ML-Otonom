Sen kidemli bir Python gelistiricisin. Proje: Binance USDT-M vadeli botu "ML Otonom" (calisma dizini depo koku; kod trader/; testler `cd trader && python -m pytest ...`).
GOREV (adim 4/4): fikirler/gorev/2026-11-24-45480527826/gorev_sonuc.md icindeki "Mevcut kollara varyant onerileri" tablosundaki varyantlari ekle. KULLANICI KARARI (24.11): EKLE.
YONTEM: mevcut 7 kolun (T1 R1 TF1 B1 H2 S1 F1) ASIL davranisini DEGISTIRME. Her varyant ayri kimlikli yeni kurulum olur (or. "TF1-HACIM@1h", "F1-IKINCI@4h"),
formasyon kutuphanesiyle ayni yapida (onceki adimlarda kuruldu; once git log ve kodu oku): hepsi ACIK, TAM BOY, ailesi kendi ana kolu, kapasite aile 6 / varyant x ZD 3,
4 ZD (15m 1h 4h 1d), ogrenme varyant x ZD bazinda. Oncelik: ana kolun hemen arkasi.
Uygulanamayanlari (bekleyen limit emir gerektiren R1 %50 sapma; kitapta sayisiz "karmasik kirilim"; motorda yoksa kismi cikis) EKLEME, son mesajda neden ile listele.
"Ozellik olarak" denenler (T1 geri cekilme derinligi) icin kosul ekleme; yalniz deftere ozellik olarak yaz (FEATURES siniri varsa atla ve belirt).
KURALLAR: kagit = canli; ileriye bakis yok; her varyanta sentetik + ileriye bakis testi; hash sabitlemeli testleri gercek degerlerden yeniden hesapla
("24.11 kullanici karari: PA varyantlari"); skip/xfail yok; git komutu yok. Ilgili testleri ve sonunda tam takimi (`cd trader && python -m pytest -q -x -p no:cacheprovider`) gecir.
Son mesajinda kisa Turkce tablo: varyant | kimlik | eklendi/eklenmedi (neden) | test; tam takim sonucu.
