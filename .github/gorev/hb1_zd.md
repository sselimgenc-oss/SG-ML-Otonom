Sen kidemli bir kantitatif gelistiricisin. Yalniz okuyabilirsin. Calisma dizini depo koku. Proje: Binance USDT-M vadeli islem botu (kagit; kagit = canli).
Soru (kullanici soruyor): Haber kolu HB1 yalniz 1s zaman diliminde calisiyor (trader/src/trader_engine/strategies/arms/hb1.py TIMEFRAMES = ("1h",)).
Bu karar kullanicidan degil, 23.11 tasarimindan geldi (fikirler/pazartesi-23-11/ust-lig-tasarim.md bolum 1). Diger kollar 15m/1h/4h/1d'de.
Oku: hb1.py, trader/src/trader_core/haber_sinyal.py, trader/scripts/haber_sinyal_run.py, ilgili zamanlayici (trader/deploy/*haber*), ust-lig-tasarim.md bolum 1,
tests/engine/test_hb1_kol.py. Ogrenme formasyon x ZD bazinda (kol kimligi HB1@1h); aile destegi ayni kurulumun diger ZD'lerinden gelir.
Karar ver: HB1 yalniz 1s mi kalsin, yoksa 15m / 4h / 1d de acilsin mi? Her ZD icin: sinyal uretim sikligi (saatlik), gecerlilik (3 sa), 6 sa pencere,
ayni sinyalin tekrar tetiklenmesi, sizinti, ogrenme verisi ve beklenen fayda/zarar. Acilacaksa gereken degisiklikler (tekillestirme, gecerlilik, stop/hedef/zaman stopu) ve tahmini is buyuklugu.
Son mesajinda YALNIZ Markdown, sade Turkce, kisa: # HB1 zaman dilimi / ## Karar (tek cumle) / ## Gerekce (ZD basina tablo: ZD | ac/acma | neden) / ## Yapilacaklar (acilacaksa; yoksa "yok")
