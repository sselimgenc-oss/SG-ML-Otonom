Sen kidemli bir Python gelistiricisin. Proje: Binance USDT-M vadeli islem botu "ML Otonom" (calisma dizini depo koku; kod trader/, testler trader/tests; testleri `cd trader && ...` ile calistir).
Derin denetimde dogrulanan sorunlari DUZELT. Kullanici 24.11'de hepsini onayladi.

KURALLAR:
- Kagit = canli: iki ayar dosyasi (trader/config/engine.paper.json, engine.live.json) ayni davranmali.
- Her duzeltme icin en az bir test ekle ya da guncelle. skip/xfail YOK. freqtrade/ccxt/python-binance YOK. Yeni paket YOK.
- Degisiklik en kucuk olsun; ilgisiz yeniden duzenleme yapma. Kod yorumlari kisa Turkce, ASCII.
- Ozet (hash) sabitlemesi olan testler (or. tests/engine/test_dd12_wp01_spec.py, test_dd12_wp18_impl.py, test_risk_ladder_impl.py digest) ayar ya da
  davranis degisince kirilir: bu kullanici karari oldugu icin degerleri GERCEK dosya ozetlerinden/kosudan yeniden hesapla ve yanina
  "24.11 kullanici karari: denetim duzeltmeleri" yorumu yaz.
- otonom-trading-arastirma/tasarim-kararlari.md sonuna "24.11 denetim duzeltmeleri" kaydi ekle (her madde tek satir).
- git komutu CALISTIRMA (commit/push is akisinda yapilir).
- Testleri calistir: once ilgili test dosyalari, sonunda `cd trader && python -m pytest -q -x -p no:cacheprovider` (tam takim, uzun surebilir). Hepsi gecmeli.

DUZELTILECEKLER (dosya:satir yaklasik; once oku, dogrula):
1. M1 egitimi ileriye bakis: trader/research/pa_proposer_build.py ~75 `i = idx.get(t0, idx.get(t0 - tf_delta))`. bar_close_ts motorda karar ani D = son kapanmis
   mumun KAPANIS zamani; mum dosyasi "date" = ACILIS zamani. Tam eslesme sinyalden SONRAKI mumu seciyor. Yalniz t0 - tf_delta ile esle (sinyal mumu), test ekle.
2. M1 kilit kesimi: trader/scripts/ml_retrain_run.py ~89 ve pa_proposer_build.py ~79: tarihsel veri kosulsuz LOCK_START'ta kesiliyor, kagit satiri penceresi LOCK_END
   oncesine degerse atiliyor. trader_ml.config.KILIT_ACIK True iken bu kesimler uygulanmasin. Docstring (03:10 UTC -> zamanlayicidaki gercek saat) ve CSV veri_penceresi alanini duzelt.
3. Risk kademesi: Fable karari kademe_karar.md dosyasinda (depo kokunde). "Uygulama talimati"ni AYNEN uygula.
4. Panel: trader/src/trader_core/panel_data.py ~262 limitler LOCKED_CFG'den (0,06/0,04) geliyor. Kipin ayar dosyasindan oku (motorun kullandigi %12/%6 gibi).
   Gunluk zarari motor/Telegram ile ayni yontemle (gun basi kasa - simdiki kasa, gerceklesmemis dahil) hesapla.
5. Gunluk kayip siniri: KULLANICI KARARI %8 KALIR. Ayar/kod degismez; tasarim-kararlari.md'de 19 Kasim "%8 -> %5" kaydinin altina "24.11 kullanici karari: gunluk %8 kalir" yaz.
6. Gunluk kayip freni: trader/src/trader_core/kayip_freni.py ~102 `_son_kazanc` gun sinirina bakmiyor; yalniz BUGUNUN (sistemin gun siniri) kapanislarina bak. Test ekle (dunku kazanc freni engellemez).
7. HB1 kaynak teyidi: trader/src/trader_engine/strategies/arms/hb1.py ~175 ve trader/src/trader_core/veri_haber.py 31-46: "en az 2 kaynak" ayni yayincinin ayri beslemelerini
   (cnbc_*, marketwatch_* ...) ayri sayiyor. Yayinci adina gore tekillestir.
8. Haber 120 siniri: trader/src/trader_core/haber_sinyal.py ~350: sinirdan dusen olaylar puanlanmadan son_alim ilerliyor. Kalanlar sonraki tura kalsin (son_alim yalniz islenenlere gore ilerlesin).
9. Haber partileri: haber_sinyal.py ~356-377: sonraki parti hata verince onceki odenmis partiler atiliyor. Basarili partileri yaz, imleci kismi ilerlet.
10. Kagit tasfiye MMR: trader/src/trader_engine/engine.py ~2745 ve brokers/paper.py ~494 tum siniflarda 0,004; giris kapisi hisse/emtia icin farkli oran kullaniyor. Kagit brokere sinif MMR'ini gecir (kapiyla ayni kaynak).
11. Saglik uyarisi: trader/scripts/health_run.py ~634-657, 1005: ek uyarilar gonderilemezse durum geri alinmiyor. Basarisiz gonderimde ek_uyarilar durumunu da geri al.
12. Haftalik ozet: trader/scripts/weekly_summary_run.py ~161 "alinmayan sinyal" R degerini $ olarak yaziyor; R bicimleyici kullan.

Son mesajinda kisa Turkce tablo: # | ne degisti | dosyalar | test. Uygulanamayan varsa neden. Tam takim sonucu (gecen/kalan sayisi).
