HB1 zaman stopu artık 24 mum. Tam takım geçti: 8700 geçti, 145 atlandı (benim eklediğim atlama yok), hata yok; süre 47 dk.

- **Kod:** `hb1.py` içine `TIME_STOP = 24` eklendi. `arms.time_stop_of("HB1")` 24 dönüyor, motor varsayılanı olan 48 artık HB1'e uygulanmıyor.
- **Test:** `test_hb1_kol.py` içine `test_hb1_zaman_stopu_24_mum` eklendi. Motor yolunda 23 kapanmış mumda çıkış yok, 24'te `time_stop` çıkışı var.
- **Kayıt:** `tasarim-kararlari.md` sonuna tek satırlık 25.11 kullanıcı kararı eklendi.
- **sha256:** `hb1.py` için sha256 sabitlemesi olan bir test bulamadım, bu yüzden özet yeniden hesaplamadım.

Dosyalar:
- `trader/src/trader_engine/strategies/arms/hb1.py`
- `trader/tests/engine/test_hb1_kol.py`
- `otonom-trading-arastirma/tasarim-kararlari.md`