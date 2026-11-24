# Derin denetim raporu

## Ozet

- 130 aday bulgu: **96 dogru**, **14 kismen**, **11 yanlis**, **9 kullanici karari / bilincli tasarim** (hata sayilmadi).
- Tekrarlar birlesince 41 ayri sorun kaliyor.
- Dogru sayilanlarin yaklasik 25'i dusuk onemli belge / olu kod maddesi. Bunlari satir satir okumadim, yalniz kanit tutarliligina baktim (Notlar'da listeli).
- Hicbir test calistirilmadi; tum sonuclar statik okumaya dayanir.

En onemli 5 madde:

1. Kagit risk kademesi yalniz gozlem, canli zorlayici: kagit sonuclari canliyi temsil etmiyor.
2. M1 egitiminde kagit kayitlari sinyal mumundan bir sonraki muma esleniyor (ileriye bakis).
3. M1 gece egitimi kilit acikken hala 2026-05..10 verisini atiyor; M1@1d kagit satirlari aylarca egitime girmez.
4. Kurulum yarida kalirsa kod yeni surume gecmis olur, ama surum dosyasi ve Telegram mesaji "eski surum" der.
5. Haber kolunda bir parti bozulursa odenmis sonuclar atilir, ayni basliklar her saat yeniden odenir.

## Dogrulanan sorunlar

| # | Onem | Alan | Dosya:satir | Sorun | Ne yapilmali |
|---|------|------|-------------|-------|--------------|
| 1 | Yuksek | risk | `src/trader_engine/engine.py:2656-2663`, `ladder.py:85-108` | Kagitta kademe `enforce=False`: kapi kapatmaz, riski dusurmez. Canlida `enforce=True`. `engine.paper.json`'da `ladder_follow` yok. | Kagitta da kademeyi zorla ya da farki acik istisna olarak yaz ve parite testine ekle. |
| 2 | Yuksek | m1 | `research/pa_proposer_build.py:75` | `idx.get(t0, …)` once tam eslesme arar. `bar_close_ts` = karar ani, bar dizisi acilis zamanli. Secilen mum sinyalden sonraki mumdur; ozellikler gelecegi gorur. | Yalniz `t0 - tf_delta` ile esle; tam eslesmeyi kaldir. Test ekle. |
| 3 | Orta | m1 | `scripts/ml_retrain_run.py:89`, `research/pa_proposer_build.py:79` | Kilit acik olmasina ragmen gecmis `LOCK_START`'ta kesiliyor. Kagit satiri, 64 mumluk penceresi 2026-11-01'den once baslarsa atiliyor (1d icin 64 gun). | Iki kesimi `KILIT_ACIK` bayragina bagla. Docstring ve CSV etiketini duzelt. |
| 4 | Orta | sunucu | `deploy/install.sh:245-246, 275, 713`; `deploy/oto_guncelle.sh:228` | `current` baglantisi ve depo yeni commit'e gectikten sonra hata olursa geri alma yok (`trap` yok). `/etc/trader-release` eski kalir, mesaj "bot eski surumle calisiyor" der. | Hata tuzagi ekle: baglantiyi ve depoyu eski commit'e dondur ya da mesaji gercek duruma gore yaz. |
| 5 | Orta | hb1 | `src/trader_core/haber_sinyal.py:356-379` | Sonraki partide sema hatasi, API hatasi ya da butce reddi olursa onceki partilerin odenmis sonucu atilir, `son_alim` ilerlemez. Ayni basliklar tekrar odenir. | Basarili partileri yaz ve imleci ilerlet; yalniz bozuk partiyi yeniden dene. |
| 6 | Orta | ayar | `src/trader_engine/config.py:670` | Aylik evren kaplamasi yalniz `mode == "paper"` iken uygulanir. Canli evren statik kalir; parite testi bu anahtarlari muaf tutuyor. | Canliya da uygula ya da kullaniciya acik istisna olarak onaylat. |
| 7 | Orta | giris | `src/trader_engine/strategy_runner.py:481-482` | Bir adimda tum kurulumlar karantinadaysa `cands` ve `bad` bos kalir; `next(iter(bad.values()))` `StopIteration` atar. | Bos `bad` icin "aday yok" cercevesi dondur; test ekle. |
| 8 | Orta | alinsaydi | `src/trader_core/counterfactual.py:35, 49` | Kripto taban kaymasi 5/5/5 bp. Motorun kagit tabani 2/2/5 bp (`engine.base.json:7-8`); cikis karsi-olgusu da 2/5 kullanir. Bunu yakalayan test yok. | Tabani motor ayarindan oku; esitlik testi ekle. |
| 9 | Orta | telegram | `src/trader_core/telegram.py:2403` | Imlec en buyuk 500 kimligi tutar. 500 yeni islemden sonra hala acik olan eski pozisyon imlecten duser ve her turda yeniden "acildi" bildirilir. | Acik islem kimliklerini her zaman imlecte tut. |
| 10 | Orta | sunucu | `src/trader_core/tg_sade.py:457-466` | `OnFailure` alarmi yalniz engine/feed/backup icin metin uretir. Saglik, ders, egitim, telegram birimleri cokerse mesaj gitmez. | Diger birimler icin genel bir "birim basarisiz" metni ekle. |
| 11 | Orta | sunucu | `deploy/install.sh:644-646`, `scripts/health_run.py:98-101, 536-537` | Kurulum "HEARTBEAT_URL bos ise saglik her 5 dk basarisiz olur" der. Kod yalniz uyari yazar, cikis 0. Dis nabiz sessizce kapali kalir. | Metni duzelt ya da bos adresi gercekten hata say. |
| 12 | Orta | kagit | `src/trader_engine/brokers/paper.py:399-427` | Izgara disi (1s/4s) fonlama kaydi eksikse `due` listesine hic girmez. `funding_missing` artmaz, odeme sessizce atlanir. | Ciftin fonlama araligini bil ve eksik saati say. |
| 13 | Orta | risk | `src/trader_engine/gates.py:361`, `src/trader_core/ledger.py:2631-2638` | Kol kucultme elle kapanisi da sayar ve karar zamani kesiti yoktur. Kayip freni ve kademe elle kapanisi atlar. | `exit_reason != manual` ve `exit_ts < D` ekle. |
| 14 | Orta | telegram | `src/trader_core/telegram.py:1671, 2180` | Gunluk rapor yalniz "Duraklatma" bolumunu okur. Butce/Ders/Ogrenme bolumleri kurulur ama cagrilmaz; docstring ve belge tersini soyler. | Bolumleri rapora bagla ya da olu kodu ve belgeyi sil. |
| 15 | Orta | telegram | `src/trader_core/tg_sade.py:24`, `telegram.py:1439` | Sabit ve belge %5 der; gercek sinir ayardan %8 okunur (`daily_max_loss: 0.08`). Sabitler kullanilmiyor. | Sabitleri sil, belgeyi %8'e guncelle. |
| 16 | Orta | belge | `docs/kagit-degerlendirme-plani.md:31` | Kagit ayarini `engine.base.json` sayar. Gercek ayar base + paper: farkli strateji, risk %1, 43 cift. | Belgeyi efektif ayarla guncelle. |
| 17 | Orta | belge | `docs/cikis-kipleri-spec.md:15, 23` | Belge "canlida ConfigError, kip kapali" der. Kod canliya izin verir (`config.py:580`) ve `engine.live.json:11` kipleri acar. | Belgeyi 23.11 kararina gore guncelle. |
| 18 | Orta | belge | `strategies/arms/hb1.py:13` | Docstring zaman stopunu 24 mum der; kod 48 kullanir (`signals.py:31`). | Docstring'i duzelt. |
| 19 | Orta | belge | `docs/sunucu-kurulum.md:131` | Belge guncellemeyi gunde iki sabit pencere anlatir; zamanlayici 5 dakikada bir calisir (`*:0/5`). Davranis kullanici karari; yalniz belge eski. | Belgeyi guncelle. |
| 20 | Orta | ayar | `config/engine.testnet.json` | `target_mode` yok, base'den `bar_close` alir. Kagit ve canli `resting` kullanir; bekleyen hedef emri testnette denenmiyor. | Testnete `"target_mode": "resting"` ekle. |
| 21 | Orta | ders | `src/trader_core/lesson.py:1189-1192` | Gevsetme kurallarinda belgeli `mean_A ≥ 0.30` esigi yok; yalniz `> 0` denetlenir. | Esigi ekle ya da belgeden cikar. |
| 22 | Dusuk | ders | `config/lesson.json:14`, `lesson.py:848` | `max_pair_share: 1.0` cift yogunlugu korumasini fiilen kapatir; belge 0.5 der. | Bilincliyse belgeye yaz, degilse 0.5 yap. |
| 23 | Dusuk | alinsaydi | `counterfactual.py:196-200`, `alinmayan_sonuc.py:176` | `done_ids` surume bakmaz. Eski surum-1 plan satiri varsa yeniden hesaplanmaz ve raporda kalici "cozulmedi" olur. | `done_ids`'e `version >= VERSION` kosulu ekle. |
| 24 | Dusuk | giris | `gates.py:256`, `engine.py:2044` | Bayat veri toleransi 1s uzerinden hesaplanir; karar adimi 15 dk. Tolerans 4 kat genis. | `step_tf` kullan. |
| 25 | Dusuk | giris | `ledger.py:2645` | HB1 olay sorgusunda ust sinir yok (`exit_ts <= D`). Canlida etkisiz, yeniden oynatmada ileriye bakar. | `until=D` ekle. |
| 26 | Dusuk | alinsaydi | `engine.py:2092`, `gates.py:506` | Cift duzeyi redde `arm_conflict` satirindaki "kazanan" aslinda reddedilen adaydir. | Etiketi "engelleyen" yap ya da bos birak. |
| 27 | Dusuk | m1 | `src/trader_core/pa_features.py:47-54` | Short icin `dist_hi/dist_lo` ve fitiller gercek ayna degil. Egitim ve canli ayni fonksiyonu kullandigi icin parite bozulmaz. | Docstring'i duzelt ya da bir sonraki ozellik surumunde aynala. |
| 28 | Dusuk | hb1 | `haber_sinyal.py:350-353` | 120 oge siniri asilinca eski basliklar sessizce atilir; imlec onlari da kapsar. Ilk calismada tum RSS gecmisi "taze" sayilir (alim zamani tasarimi). | Atilan sayisini logla; ilk calismada yayin zamanina bak. |
| 29 | Dusuk | kagit | `paper.py:388-389, 547-548` | `mark_fallbacks` ayni mum icin iki kez artar. | Tek noktada say. |
| 30 | Dusuk | kagit | `paper.py:494, 602` | Tasfiye dolumu tick'e yuvarlanmaz; belge "her dolum tick katidir" der. | Yuvarla ya da belgeye istisna yaz. |
| 31 | Dusuk | canli | `order_manager.py:678-684` | Kabul edilmis giris sorguda "yok" donerse hemen `failed`; "bilinmeyen" yolu pencereyi bekler. | Ayni bekleme penceresini uygula. |
| 32 | Dusuk | canli | `reconcile_live.py:195-200` | Pozisyon varken yalniz izlenen ciftlerin emirleri okunur. Baska ciftteki yetim emir, hesap duzlesene kadar gorulmez. | Seyrek araliklarla tam tarama yap. |
| 33 | Dusuk | alinsaydi | `scripts/counterfactual_run.py:53-57` | Kagit ayari okunamazsa yalniz uyari; tum varliklar kripto sayilir, cikis kodu 0. | `EXIT_DEGRADED` dondur. |
| 34 | Dusuk | alinsaydi / m1 | `alinmayan_sonuc.py:198`, `scripts/export_paper_records.py:52` | "Tum zamanlar" ve disa aktarim en yeni 10000 islemle sinirli; uyari yok. | Sinira ulasilinca rapora not yaz. |
| 35 | Dusuk | sunucu | `scripts/health_run.py:835, 933` | 60 sn saglik butcesi hesaplanir ama `collect` icinde hic okunmaz. | Uygula ya da sil. |
| 36 | Dusuk | dl1 | `scripts/health_run.py:829` | DL1 saglik denetimi yalniz `engine.paper.json`'a bakar. | Calisan kipin ayarini oku. |
| 37 | Dusuk | telegram | `scripts/yorumcu_run.py:2, 107` | Docstring "dunun kararlari" der; karar tablosu tum gecmisten gelir. | Tarih filtresi ekle ya da metni duzelt. |
| 38 | Dusuk | ayar | `lesson.py:232`, `telegram.py:264` | Varsayilan defter yolu `user_data/ledger_learner.sqlite`; motor `var/learner/ledger.sqlite` kullanir. Ayar ya da ortam eksikse yanlis dosya okunur. | Varsayilanlari esitle. |
| 39 | Dusuk | olu ayar | `config.py:93, 164, 406`; `engine.py:150`; `lesson.json:41`; `engine.live.json` | Etkisiz ayarlar: `start_delay_s`, `live.max_attempts` (1'e sabit), `notes_model`, `_PAPER_ONLY_KEYS`, canli dosyadaki `cost_overrides`. | Sil ya da "etkisiz" diye belgele. |
| 40 | Dusuk | olu kod | `haber_sinyal.py:36, 251`; `dl1_cikarim.py:54, 319`; `kayip_freni.py:34`; `funding.py:27, 58`; `numeric.py:62`; `s1.py:27`; `paper.py:126`; `telegram.py:1594` | Uretimde cagrilmayan sabit ve fonksiyonlar. Bir kismi yalniz testlerde yasiyor. | Temizle. |
| 41 | Dusuk | test | `tests/test_exit_modes_cf.py:96`; `tests/test_oto_guncelle.py:453` | Biri davranis yerine kaynak metni arar. Digeri kodun okumadigi `OTO_SIMDI_SAAT` degiskenini kullanir. | Davranis testi yaz; olu degiskeni kaldir. |

## Yanlis cikan aday bulgular

| Alan | Iddia | Neden yanlis |
|------|-------|--------------|
| canli | `_retry_failed_exits` canlida cikis sayacini iki kez artirir | Fonksiyon canlida hic cagrilmaz (`order_manager.py:659`). Kagitta da geri alma dali `live_mode` ister. Cift sayim yok. |
| canli / test | Cift sayim testte yakalanmiyor | Cift sayim olmadigi icin gerekce dusuyor. Yalniz "bu yolun testi yok" kismi dogru. |
| m1 / test | `test_dd12_wp10_impl.py` kilit acikken kirilir | Dosya `pytestmark = usefixtures("egitim_kilitli")` kullaniyor (satir 26). |
| m1 / test | `test_dd12_wp14_impl.py` kilit acikken kirilir | Ayni fixture satir 25'te var. |
| cikis / kurulum (2 kez) | Kacan mum telafisi yalniz canlida, kagit atliyor | Kagit kacan karar mumlarini zaten tek tek yeniden oynatir. Atlama yalniz canlida (`engine.py:2218`); telafi bu yuzden canliya ozel. |
| kagit | Dakika isareti ayni dakikada kapanan pozisyonu kacirir | Kapanan pozisyonun zarari cuzdana gerceklesmis olarak girer; stop fiyati zaten en kotu noktadir. |
| cikis | 4s politikasi 1s baglamiyla kip tetikliyor | `PriceActionV1H4` kayit defterinde yok; motor yuklemez. Yalniz `research/s2_run.py:84` kullanir. |
| kurulum | `make_v1b_4h` hicbir yerden cagrilmiyor | Arastirma betigi cagiriyor. "Uretimde kullanilmiyor" kismi dogru. |
| dl1 (2 kez) | Saglik ve motor DL1 paketini farkli dizinden okur | Dagitimda ikisi de `/opt/trader` (`trader-health.service:13`, motor `WorkingDirectory`). Ayrisma kanitlanmadi. |
| dl1 | "En ust %2" ifadesi kodla celisiyor | Yuzde 98'lik esik ayni seyin yaklasik ifadesi; hata degil. |

Kullanici karari ya da belgeli tasarim oldugu icin hata sayilmayanlar:

- **Onaysiz ders:** `ALWAYS_USER` bos, `cf_n` ve kalibrasyon onay nedeni degil, eski testler OBSOLETE (4 bulgu).
- **Gunluk tepe guncellemesi:** T-44'te belgeli.
- **Giris kapi blogu yalniz kagit/canli:** diger kiplerde bu anahtarlar ayarda zaten yasak.
- **Haber tazeliginde alim zamani:** docstring ve test bilincli secim diyor.
- **Gap'te tasfiye fiyati:** kayip teminatla sinirli.
- **Risk blogu bossa siki sinirlar:** guncel dosyalarda blok var, etkisiz.

## Notlar

- **Satir satir okumadigim dusuk onemli maddeler** (kanit tutarli, dogru saydim): `ml_package.py:102`, `walkforward.py`, `kurulum_gozcu.py:243`, `trader-oto-ac`, `seans_takvimi.json` "durum" alani, `budget.json` haber_kolu suresi, `veri_haber.py:29`, `cekirdek.py:480`, `duman.py:47`, `test_engine_mentor_fixes.py:66`, H2 `PB_MIN_BARS`, ve `docs/motor/` altindaki belge farklari (03, 05, 11, 12, dd12-ek-k, oto-guncelleme-spec).
- **`toplam_buyukluk` aday-ozgu mu** (`gates.py:149`): kod ve test tutarli, belge "hesap tavani durulur" diyor. Daha kucuk aday sigabilecegi icin bilincli olabilir; karar kullanicida.
- **H2 EMA korumasi** (`h2.py:79`): NaN karsilastirmasi korumayi atlatir, ama `p.ok[t]` isinmayi zaten eliyor olabilir. Canli pencere 1500 mum; etkisi dusuk.
- **Gevsetme A kumesi** (`lesson.py:1216, 1225`): kod belgedeki tabloyla ayni, celiski belgenin kendi icinde.
- **Islem mesaji spool'a duserse "gonderildi" kaydi yazilmaz** (`telegram.py:2385`): mantik goruluyor, spool yolunu okumadim.
- **Dakika boslugu sayaclari** (`engine.py:2242`) ve **canli ucret tahmini farki** (`binance_futures.py:988`): kucuk fark, tam dogrulanmadi.
- **`RestartSteps`** Ubuntu 22.04'te taninmayabilir; systemd surumu sunucuda kontrol edilmeli.
- **Ders onayinda `LogNotifier`** (`lesson_run.py:82`): dogru, ama "uygulandi" bildirimi zaten Telegram'a gitmiyor (`DERS_SESSIZ`); etkisi yok.

---
Maliyet: tarama 4.50 $, dogrulama 3.27 $ (Agent SDK, promosyon kredisi).
