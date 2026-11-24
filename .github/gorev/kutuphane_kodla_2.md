Sen kidemli bir Python gelistiricisin. Proje: Binance USDT-M vadeli botu "ML Otonom" (calisma dizini depo koku; kod trader/; testler `cd trader && python -m pytest ...`).
GOREV (adim 2/3): formasyon kutuphanesinin su kismini motora kodla: GF1 (13 grafik formasyonu) + IN1 (17 indikator setupu; gerekli gostergeler: RSI, MACD, Bollinger, Stokastik vb.).
TASARIM (aynen uygula): fikirler/gorev/2026-11-24-45474500845/gorev_sonuc.md. KULLANICI KARARLARI (tasarimdan once gelir): fikirler/gorev/2026-11-24-45474500845/kullanici_kararlari.md
(hepsi ACIK, hepsi TAM BOY, aile 6 / formasyon x ZD 3, stopsuzlara 2 ATR stop, ic cubuk kapanis teyidi, 4 ZD: 15m 1h 4h 1d).
Onceki adimlarda yapilanlar bu dalda; once git log ve mevcut kodu oku, tekrarlama.
KURALLAR: kagit = canli (engine.paper.json ve engine.live.json ayni). Ileriye bakis yok (pivot onay gecikmesi, yalniz kapanmis mum). Her formasyon icin sentetik ornek testi +
ileriye bakis testi. Hash sabitlemeli testleri gercek degerlerden yeniden hesapla, yanina "24.11 kullanici karari: formasyon kutuphanesi" yorumu. skip/xfail yok.
freqtrade/ccxt/python-binance yok, yeni paket yok. git komutu yok. Ilgili testleri calistir; sonunda tam takim (`cd trader && python -m pytest -q -x -p no:cacheprovider`) gecmeli.
Butce siniri var: once en kritik kismi bitir ve testleri gecir; yetismeyen formasyon kalirsa son mesajda listele.
Son mesajinda kisa Turkce tablo: eklenenler | dosyalar | test; eksik kalanlar; tam takim sonucu.
