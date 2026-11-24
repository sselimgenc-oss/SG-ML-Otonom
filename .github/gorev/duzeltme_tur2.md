Sen kidemli bir Python gelistiricisin. Proje: Binance USDT-M vadeli botu "ML Otonom" (calisma dizini depo koku; kod trader/, testler `cd trader && python -m pytest ...`).
Bu dal (duzeltme-denetim) denetim duzeltmelerini iceriyor. Fable incelemesi: fikirler/duzeltme/2026-11-24-45449006992/inceleme.md; risk kademesi karari:
fikirler/duzeltme/2026-11-24-45449006992/kademe_karar.md; ilk talimat: .github/duzeltme/2_duzelt.md. Once ucunu oku.
GOREV: incelemenin "Birlestirmeden once duzeltilmesi gerekenler" listesindeki 7 maddeyi yap:
1. Kirilan 22 testi (tests/engine/test_canli_cikis_kipleri.py, tests/engine/test_hedef_bekleyen_emir_canli.py) yeni davranisa (risk hep ayardan, %1) gore guncelle; beklenen adetleri
   gercek kosudan al, yanina "24.11 kullanici karari: risk kademesi kaldirildi, risk ayardan" yorumu yaz. Testin amacini (kismi dolum, mutabakat vb.) koru; yalniz adetler degisir.
2. M1 ileriye bakis testi (tam eslesen mum degil sinyal mumu secilir). 3. Kagit tasfiye MMR testi (hisse/emtia sinif MMR'i, kripto eskisi gibi, kapiyla ayni).
4. Kademe icin eksik testler (CLI, kagitta /kademe_devam, saglikta kagit review/floor, paritede capital_floor). 5. Telegram'daki sabit %1 yedegini etkin riske bagla.
6. "Kilit acikken kesim yok" testi (ml_retrain_run ve pa_proposer_build ikisi de). 7. fikirler/duzeltme/2026-11-24-45449006992/duzelt_notu.md'yi gercek ozet tabloyla doldur.
KURALLAR: skip/xfail yok; git komutu yok; ilgisiz degisiklik yok. Ilgili test dosyalarini calistir ve gecir; sonda tam takim (`cd trader && python -m pytest -q -x -p no:cacheprovider`;
uzun surer) calistir, hepsi gecmeli. Son mesajinda kisa Turkce tablo: madde | ne yapildi | test; tam takim sonucu.
