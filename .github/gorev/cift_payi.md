Sen kidemli bir kantitatif gelistiricisin. Calisma dizini depo koku; kod trader/, testler trader/tests (`cd trader && ...`).
Kullanici (25.11): "Fable ne diyorsa onu yap." KARARI SEN VER ve uygula.
Konu: denetim raporu fikirler/denetim/rapor-2026-11-24.md madde 18: trader/config/lesson.json `max_pair_share=1.0`; trader/src/trader_core/lesson.py ~848 cift payi korumasi
bu degerle hic tetiklenmiyor; belge 0,5 diyor. Oku: lesson.py ilgili kisim, lesson.json, ilgili belge (grep max_pair_share), ders esikleri (8 islem / 4 gun, aile destegi),
evren 43 cift, 288 kol (kol = formasyon x ZD). Ders bir kolun parametresini degistirir; kanitin cogu tek ciftten gelirse yaniltici olabilir.
Karar: deger ne olmali (1.0 kalsin / 0.5 / baska)? Kucuk kollarda (az islem) korumanin dersleri gereksiz engellememesine dikkat et.
Uygula: lesson.json degeri ve/veya belge duzeltmesi; davranis degisirse test ekle/guncelle. sha256 sabitlemesi kirilirsa GERCEK ozetten yeniden hesapla,
yanina "25.11 kullanici karari: cift payi (Fable)" yaz. otonom-trading-arastirma/tasarim-kararlari.md sonuna tek satir kayit. skip/xfail yok, yeni paket yok, git komutu yok.
Once ilgili testler, sonunda `cd trader && python -m pytest -q -x -p no:cacheprovider`.
Son mesajinda YALNIZ sade Turkce, kisa: # Cift payi / ## Karar (tek cumle + deger) / ## Gerekce (3-5 madde) / ## Degisenler / ## Tam takim sonucu
