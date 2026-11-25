Sen kidemli bir Python gelistiricisin. Proje: Binance USDT-M vadeli islem botu "ML Otonom" (calisma dizini depo koku; kod trader/, testler trader/tests; testleri `cd trader && ...` ile calistir).
Derin denetim raporu: fikirler/denetim/rapor-2026-11-24.md ("Dogrulanan sorunlar" tablosu). 1-8, 10-12 ve 21 numarali maddeler ZATEN duzeltildi; dokunma.
Kullanici 25.11'de kalan maddelerin duzeltilmesini onayladi. Ayrica asagidaki EK maddeyi yap.

KURALLAR:
- Kagit = canli: trader/config/engine.paper.json ve engine.live.json ayni davranmali. Risk ayarlarina (max_open_risk, max_same_dir_risk, daily_max_loss, max_positions, tavanlar) DOKUNMA.
- Her davranis duzeltmesi icin en az bir test ekle ya da guncelle. skip/xfail YOK. freqtrade/ccxt/python-binance YOK. Yeni paket YOK.
- En kucuk degisiklik; ilgisiz yeniden duzenleme yok. Kod yorumlari kisa Turkce, ASCII.
- Ozet (sha256) sabitlemesi olan testler (or. tests/engine/test_dd12_wp01_spec.py, test_dd12_wp18_impl.py, test_wp3_spec.py) degisen dosyalar icin kirilir: GERCEK ozetten yeniden hesapla, yanina "25.11 kullanici karari: denetim kalan maddeler" yaz.
- Yeni motor modulu eklersen tests/engine/test_engine_module_inventory.py listesine ekle.
- git komutu CALISTIRMA.
- Butce sinirli: once yuksek etkili maddeler. Sira: EK, 9, 29, 30, 13, 19, 20, 26, 27, 24, 33, 36, 12-disi Orta maddeler, sonra Dusuk temizlikler (olu kod/eski belge).

ATLA (yalniz raporla, kod degistirme):
- #16 (ortak ayar dosyasi): buyuk yeniden duzenleme. Yerine YALNIZ bir test ekle: kagit ve canli ayar dosyalarinda arms, arm_max_positions, arm_family_max_positions, clusters, risk, exit_modes, cost_overrides, max_positions birebir ayni.
- #18 (max_pair_share degeri): kullanici karari; dokunma, raporda "karar bekliyor" yaz.
- #28 ve #46 (canli emir/mutabakat davranisi): davranis degistirme; #46 icin yalnizca mevcut davranisi belgeleyen test yazilabiliyorsa yaz.
- Notlar bolumundeki emin olunamayan maddeler.

EK (zorunlu, ilk yap): aile tavani giris kapisinda uctan uca test. Ayni ailede (or. MF1) `arm_family_max_positions` kadar (6) acik pozisyon varken ayni aileden 7. aday reddedilir (skip nedeni kayitli), ayni anda baska aileden (or. GF1) aday kabul edilir. Gercek giris kapisi / motor yolu uzerinden (saf yardimci degil). Kagit ve canli ayar degerleriyle.

Bitince: otonom-trading-arastirma/tasarim-kararlari.md sonuna "25.11 denetim kalan maddeler" kaydi (her madde tek satir).
Testler: once ilgili dosyalar, sonunda `cd trader && python -m pytest -q -x -p no:cacheprovider` (tam takim). Hepsi gecmeli.
Son mesajinda YALNIZ sade Turkce tablo: # | ne degisti | dosyalar | test. Altina: atlananlar ve nedeni; butce yuzunden kalanlar; tam takim sonucu.
