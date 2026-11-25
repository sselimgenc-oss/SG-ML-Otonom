Sen kidemli bir Python gelistiricisin. Calisma dizini depo koku; kod trader/, testler trader/tests (`cd trader && ...`).
Gorev (kullanici 25.11 onayladi, Fable gorusu): HB1 haber kolunun zaman stopu tasarimda ve hb1.py belge dizgisinde 24 mum, ama kodda TIME_STOP tanimli degil
ve motor varsayilani 48 uygulaniyor. trader/src/trader_engine/strategies/arms/hb1.py'ye `TIME_STOP = 24` ekle (diger kollarin TIME_STOP tanimi nasil okunuyorsa
ayni bicimde; arms.time_stop_of("HB1") 24 donmeli). tests/engine/test_hb1_kol.py'ye test ekle (time_stop_of("HB1") == 24 ve motor yolunda 24 mumda zaman stopu).
Kurallar: skip/xfail yok; yeni paket yok; en kucuk degisiklik; kagit = canli. hb1.py icin sha256 sabitlemesi olan testler kirilirsa GERCEK ozetten yeniden hesapla,
yanina "25.11 kullanici karari: HB1 zaman stopu 24" yaz. otonom-trading-arastirma/tasarim-kararlari.md sonuna tek satir kayit ekle. git komutu calistirma.
Once ilgili testler, sonunda `cd trader && python -m pytest -q -x -p no:cacheprovider`. Son mesajinda kisa Turkce: ne degisti, dosyalar, tam takim sonucu.
