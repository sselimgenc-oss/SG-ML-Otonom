# Duzeltme incelemesi

**Sonuc: bu haliyle birlestirilemez.** Tam takimda 22 test kiriliyor ve hepsi 3. maddenin (risk kademesi) dogrudan sonucu. Ayrica 1. ve 10. maddelerin testi yok. Gelistirici notu (`duzelt_notu.md`) bos sayilir: icinde yalniz "Kosular ilerliyor…" yaziyor, ozet tablo ve tam takim sonucu yok.

## Madde tablosu

| # | Durum | Not |
|---|---|---|
| 1 M1 ileriye bakis | eksik | Kod dogru: eslesme yalniz `t0 - tf_delta` (sinyal mumu). Ama zorunlu test eklenmemis; mevcut M1 testlerinde yalniz `KILIT_ACIK=False` yamasi var. |
| 2 M1 kilit kesimi | eksik | Kod dogru: `KILIT_ACIK` iken tarihsel kesim ve kagit pencere sarti atlaniyor; docstring 00:40 UTC, CSV `veri_penceresi` duzeltildi. "Kilit acikken kesilmiyor" davranisini sinayan test yok. Mevcut iki test kilidi kapatarak eski davranisi sinar, o da yalniz `ml_retrain_run` kopyasini yamar (`pa_proposer_build` acik kalir). |
| 3 Risk kademesi | hatali | Cekirdek kod talimata uygun (ayrinti asagida), ama 22 test kiriliyor ve talimattaki testlerin bir kismi yazilmamis. |
| 4 Panel | tamam | Limitler kipin ayar dosyasindan; gunluk zarar = gun basi kasa − simdiki kasa. Kagit ve canli icin test var. Kucuk not: `testnet` kipi kagit dosyasini okur; dosya okunamazsa sessizce `LOCKED_CFG`'ye duser. |
| 5 Gunluk %8 kalir | tamam | Yalniz belge; 19 Kasim kaydinin altina yazilmis, ayar/kod degismemis. |
| 6 Kayip freni | tamam | Yalniz bugunun (UTC) kapanislarina bakiyor; kapi UTC gun basini geciriyor, defterde `exit_ts` alani var. Test saf fonksiyon duzeyinde, yeterli. |
| 7 HB1 kaynak teyidi | tamam | Yayinci = besleme adinin `_` oncesi; uretici ve kol ayni kurali kullaniyor, esitlik testi var. Kural kirilgan: ileride `the_block` / `the_defiant` gibi adlar tek yayinci sayilir. Bugunku listede sorun yok. |
| 8 Haber 120 siniri | tamam | Eskiden yeniye siralaniyor, imlec en eski bekleyenin hemen oncesinde kaliyor; ayni zamanli olaylar yeniden okununca mevcut olaylarla birlesiyor (cift puanlama yok). Test var. |
| 9 Haber partileri | tamam | Basarili partiler yaziliyor, imlec kismi ilerliyor, donus `kismi`. Ilk parti bozuksa hicbir sey yazilmiyor. Iki test var. |
| 10 Kagit tasfiye MMR | eksik | Kod dogru: `mmr_fn` kapiyla ayni kaynagi (`K.sinif_mmr`) kullaniyor, seans maliyeti sarmalayicisi alani koruyor. Hic test eklenmemis. Backtest tek 0,004 oraninda kaliyor (bit-bit ayni kalsin diye; bilincli olmali). |
| 11 Saglik uyarisi | tamam | `ek_uyari_geri_al` + `run_once` baglantisi dogru; saf test ve uctan uca test var. |
| 12 Haftalik ozet | tamam | R bicimleyici; `_fmt_pnl`'in baska kullanimi kalmamis; test guncel. |

**3. madde ayrintisi**

- **Talimata uygun olanlar:** `STEP_RISK_ENABLED=False`, `evaluate` ve `step_config` dallari, kagitta dosya gunlugu + `enforce=True` + motorun yazdigi `initial`, `risk_config`'ten gozlem dalinin kalkmasi, CLI degisiklikleri, belgeler. Kagit ayarinda `ladder_follow` zaten yok.
- **Kirilan testler:** `test_canli_cikis_kipleri.py` (19) ve `test_hedef_bekleyen_emir_canli.py` (3). Bu canli testler K0 (%0,5) ile boyutlanan adetleri bekliyordu (4,8 / 3,3). Artik risk dogrudan ayardan geldigi icin adet 13,4 / 9,0 / 11,9 cikiyor. Iki dosyaya da dokunulmamis.
- **Yazilmamis testler (karar §8):**
  - CLI: kagitta `ladder` devam komutu satir yazar, `capital init` reddedilir, backtest'te yazan komut reddedilir.
  - Kagit botunda `/kademe_devam`.
  - Saglik: kagitta `review` ve `floor` alarmlari (`test_health_ladder_*` hic degismemis).
  - Parite testinde `capital_floor` tutusu hic tetiklenmiyor; dizi yalniz `drawdown_review` ve `capital_latch` uretiyor.
- **Telegram etkin riski her yerde gostermiyor:** durum bayatken `ladder_view` yedegi ve `/kademe_devam` onay metni sabit `RL.STEPS[LIVE_START_STEP]` (%1) yaziyor. Ayari %1 olmayan bir botta (or. testnet %0,5) yanlis sayi gosterir. Karar "etkin riski goster" diyor.

**Kagit = canli:** davranis olarak bozulmuyor; iki ayar dosyasina dokunulmamis, kademe artik iki kipte de zorluyor. Kalan farklar belgelenmis olanlar: kagitta aktarim eslestirmesi yok, `capital init` yok. Bir acik nokta: kagitta `capital deposit/withdraw` artik yazabiliyor ama kagit cuzdani degismiyor; taban ile kasa ayrisabilir, testi de yok.

## Birlestirmeden once duzeltilmesi gerekenler

1. Kirilan 22 testi yeni davranisa gore guncelle (`test_canli_cikis_kipleri.py`, `test_hedef_bekleyen_emir_canli.py`); beklenen adetleri gercek kosudan al ve "24.11 kullanici karari" yorumunu ekle.
2. 1. madde icin test: tam eslesen mum degil, bir onceki (sinyal) mumun secildigini dogrulasin.
3. 10. madde icin test: kagit brokerde hisse/emtia tasfiye fiyati ve tasfiye ucreti sinif MMR'i ile, kripto eskisi gibi; kapiyla ayni deger.
4. 3. madde icin eksik testler: CLI, kagitta `/kademe_devam`, saglikta kagit `review`/`floor`, paritede `capital_floor`.
5. Telegram'daki sabit %1 yedegini etkin riske bagla (durum blogu yoksa kipin ayarindan).
6. 2. madde icin "kilit acikken kesim yok" testi ekle.
7. `duzelt_notu.md`'yi gercek ozet tablo ve tam takim sonucuyla doldur.

## Tam test sonucu (kisa)

- `test_sonucu.txt`: **22 basarisiz, 8403 gecti, 145 atlandi** (55 dk 33 sn). Talimat "hepsi gecmeli" diyor; saglanmiyor.
- Tam takimi yeniden kosmadim. Kademeyle ilgili 11 test dosyasini kostum: 22 basarisiz, 475 gecti, 12 atlandi. Yani 22 hatanin tamami yukaridaki iki dosyada (19 + 3).
- Diff yeni `skip`/`xfail` eklemiyor; 145 atlama onceden var.