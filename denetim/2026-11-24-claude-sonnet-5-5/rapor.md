# Derin denetim raporu

## Özet

- 141 aday bulgu vardı. Yaklaşık 100'ü doğru, 20'si kısmen doğru, 21'i yanlış ya da hata değil çıktı; sayılar yaklaşıktır.
- Tekrarlar birleşince 46 ayrı sorun kaldı. Bunlardan 13 madde yalnız okuyarak kesinleşemedi, Notlar'da duruyor.
- Hiçbir şey çalıştırılmadı; doğrulama yalnız kod okumayla yapıldı.

En önemli 5 madde:

1. **M1 gece eğitimi:** kilit açık olduğu halde 2026-05-01 sonrası tarihsel veri ve kâğıt satırları eğitime girmiyor.
2. **Risk kademesi:** kâğıtta yalnız gözlem, canlıda zorunlu; canlıda risk %0,5'e iner ve -%20 durması çalışır, kâğıtta hiçbiri olmaz.
3. **Panel risk limitleri:** panel kilitli varsayılanı (%6 / %4) gösteriyor, motor ayardaki %12 / %6 ile çalışıyor.
4. **Günlük kayıp sınırı:** karar kaydı %5 diyor, ayar dosyaları ve kod %8 kullanıyor.
5. **Günlük kayıp freni:** son kapanış kazançlıysa (dünkü bile olsa) fren hiç devreye girmiyor.

## Doğrulanan sorunlar

| # | Önem | Alan | Dosya:satır | Sorun | Ne yapılmalı |
|---|---|---|---|---|---|
| 1 | Yüksek | M1 | `scripts/ml_retrain_run.py:89`, `research/pa_proposer_build.py:79` | Tarihsel veri koşulsuz `LOCK_START`'ta kesiliyor. Kâğıt satırı da penceresi `LOCK_END` öncesine değerse atılıyor. `KILIT_ACIK` bu iki kesime bağlı değil. | İki kesimi `KILIT_ACIK`'a bağla. CSV'deki `veri_penceresi` alanını da düzelt. |
| 2 | Yüksek | Risk | `src/trader_engine/ladder.py:107,204`, `engine.py:2660` | Kademe kâğıtta `enforce=False`. Risk düşürme, -%20 durması, taban durması ve aktarım eşleştirmesi yalnız canlıda çalışıyor. "Canlı = kâğıt" kararıyla çelişiyor. | Kâğıtta da uygula ya da farkı açık bir kullanıcı kararıyla kayda geçir. |
| 3 | Yüksek | Panel | `src/trader_core/panel_data.py:262` | Limitler `LOCKED_CFG`'den (0,06 / 0,04) geliyor. Günlük zarar yalnız kapanmış işlemlerden hesaplanıyor; motor ve Telegram gerçekleşmemiş zararı da sayıyor. | Limitleri kipin ayar dosyasından oku. Günlük zararı `gün başı − kasa` ile hesapla. |
| 4 | Yüksek | Risk / belge | `tasarim-kararlari.md:178`, `config/engine.paper.json:14`, `risk.py:36` | 19 Kasım kaydı "günlük %8 → %5, aynı yön %8" diyor. Ayar %8 ve %6 kullanıyor. Sonradan geri alan bir karar bulamadım. | Hangisinin geçerli olduğunu netleştir. Ayarı ya da karar kaydını düzelt. |
| 5 | Orta | Risk | `src/trader_core/kayip_freni.py:102` | `_son_kazanc` gün sınırına bakmıyor. Son anlamlı kapanış kazançlıysa günlük fren, zarar eşiği aşılsa da açılmıyor. Belge yalnız "gün başında kalkar" diyor. | Kazanç denetimini bugünkü kapanışlarla sınırla ya da belgeyi düzelt. |
| 6 | Orta | Haber | `src/trader_core/haber_sinyal.py:356-377` | Çok partili turda sonraki parti hata verirse önceki partilerin ücretli sonuçları atılıyor. Aynı başlıklar sonraki turda yeniden ücretlenir. | Başarılı partileri yaz, `son_alim`'i kısmi ilerlet. |
| 7 | Orta | Haber | `src/trader_core/haber_sinyal.py:350-353` | 120 öğe sınırını aşan olaylar düşüyor ama `son_alim` tüm ham satırlara göre ilerliyor. Düşen başlıklar bir daha puanlanmaz. | `son_alim`'i yalnız işlenenlere göre ilerlet ya da kalanları sonraki tura bırak. |
| 8 | Orta | Haber | `strategies/arms/hb1.py:175`, `veri_haber.py:31-46` | "En az 2 kaynak" teyidi aynı yayıncının ayrı beslemelerini (4 `cnbc_*`, 2 `marketwatch_*`) ayrı kaynak sayıyor. | Teyitte yayıncı adına göre tekilleştir. |
| 9 | Orta | Haber | `strategies/arms/hb1.py:171` | 90 dakikalık `eski_sinyal` koruması ölü. Üretici her satıra `olaylar` yazdığı için dal hiç çalışmıyor. | Yaş sınırını `olaylar` olsa da uygula ya da sabiti ve belgeyi kaldır. |
| 10 | Orta | Sağlık | `scripts/health_run.py:634-657,1005`, `health.py:1509` | Ek uyarılar (disk, M1 paketi, tutarlılık) gönderilemezse durum geri alınmıyor. Yeni uyarı 6 saat gecikir, "Düzeldi" mesajı kaybolur. | Başarısız gönderimde `ek_uyarilar` durumunu da geri al. |
| 11 | Orta | Telegram | `scripts/weekly_summary_run.py:161` | "Alınmayan sinyal" satırı R değerini `$` olarak yazıyor. Alt satır aynı alanı R diye yazıyor. | R biçimleyici kullan. |
| 12 | Orta | Kâğıt | `engine.py:2745`, `brokers/paper.py:494` | Kâğıt tasfiye fiyatı tüm sınıflarda MMR 0,004 ile hesaplanıyor. Giriş kapısı hisse/emtia için %2 kullanıyor. 3x kaldıraçta fark yaklaşık 1,6 puan. | Kâğıt brokere sınıf MMR'ını geçir. |
| 13 | Orta | Ayar | `config.py:406`, `engine.py:150`, `engine.live.json:530` | `live.max_attempts` doğrulanıyor ama etkisiz; canlıda 1'e sabit. REST istemcisi kendi varsayılanı 4 ile kuruluyor. | Ayarı kaldır ya da gerçekten bağla. |
| 14 | Orta | Çıkış / belge | `docs/cikis-kipleri-spec.md:16,23`, `engine.py:1825` | Belge çıkış kiplerinin canlıda reddedildiğini söylüyor. Kod ve `engine.live.json` canlıda uyguluyor. | Belgeyi güncelle. |
| 15 | Orta | Kâğıt = canlı | `counterfactual_run.py:50`, `exit_counterfactual.py:84`, `research/dl1/cekirdek.py:111`, `haber_sinyal.py:113`, `health_run.py:824` | Karşı-olgu, çıkış kanıtı sürümü, DL1 eğitimi, haber evreni ve DL1 sağlık denetimi yalnız `engine.paper.json` okuyor. Canlı ayar ayrışırsa bunlar yanlış kalır. | Aktif kipin dosyasını oku ya da iki dosyanın eşitliğini testle zorla. |
| 16 | Orta | Ayar | `config/engine.live.json`, `config.py:670` | Canlı ve kâğıt blokları (kollar, kümeler, risk, masraf) elle kopyalanmış. Aylık evren kaplaması yalnız kâğıtta uygulanıyor. | Ortak blokları tek dosyaya al. Evren kaplamasının canlıya geçip geçmeyeceğine karar ver. |
| 17 | Orta | Geri test | `backtest.py:332` | Geri test yalnız taban + learner ayarını yüklüyor: `bar_close`, eski strateji, kol/küme/fren yok. Sonuç kâğıt davranışını ölçmüyor (`--env paper` yolu hariç). | Varsayılanı kâğıt ortamı yap ya da farkı çıktıda belirt. |
| 18 | Orta | Ders | `config/lesson.json:14`, `lesson.py:848` | `max_pair_share=1.0` olduğu için çift payı koruması hiç tetiklenmiyor. Belge 0,5 diyor. | Değeri bilinçli seç; belgeyi ya da ayarı düzelt. |
| 19 | Orta | Ders | `config/lesson.json:44`, `lesson.py:4879` | `exit_cf_reject_cooldown_days=0` bugün etkisiz. `paper_auto` kapatılırsa 28 günlük bekleme sessizce 0 olur. | Ayarı 28 yap ya da kaldır. |
| 20 | Orta | DL1 | `dl1_cikarim.py:254-285`, `strategies/arms/dl1.py:119` | Paketteki ufuk, stop/hedef ATR çarpanı ve zaman dilimi yüklemede doğrulanmıyor. Farklı etiketle eğitilmiş paket sessizce kabul edilir. | Bu alanları sabitlerle karşılaştır, uyuşmazsa paketi reddet. |
| 21 | Orta | M1 / belge | `scripts/ml_retrain_run.py:2,11` | Docstring "03:10 UTC" diyor, zamanlayıcı 00:40. "Kilit dönemi eğitime girmez" metni kilit kararıyla çelişiyor. | Belgeyi #1 ile birlikte düzelt. |
| 22 | Orta | Telegram | `telegram.py:2180,1654`, `weekly_summary_run.py:5` | `default_sections` bölümlerinden yalnız "Duraklatma" okunuyor. Diğer bölüm üreticileri, `haftalik_gonder` (bayrak False) ve `section_ledger` üretimde ölü. Docstring tersini söylüyor. | Ölü bölümleri ve testlerini kaldır ya da belgeyi düzelt. |
| 23 | Orta | Telegram | `telegram.py:1439`, `tg_sade.py:24` | `GUNLUK_ZARAR_ORANI` ve `LIMIT_ORANI` (0,05) hiç okunmuyor. Gerçek oran ayardan 0,08 geliyor; yorumlar yanıltıcı. | Sabitleri sil. |
| 24 | Orta | Yorumcu | `trader_reports/yorumcu.py:64` | "Dün" tablosu UTC gününe göre. Günlük rapor ve panel İstanbul gününe göre. | Aynı gün sınırını kullan. |
| 25 | Orta | Ayar | `config.py:93`, `engine.base.json` | `start_delay_s` zorunlu ama motor kullanmıyor. Belge ikiz için bekleme anlatıyor; ikiz kaldırıldı. | Ayarı ve belge satırını kaldır. |
| 26 | Orta | Giriş | `gates.py:148-165` | Hesap düzeyi red, Türkçe metinde alt dize aranarak anlaşılıyor. Metin değişirse sınıflama sessizce bozulur. `buyukluk_okunamadi` hesap düzeyi bir hata ama adaya özgü sayılıyor. | Yapısal kod alanı ekle. `buyukluk_okunamadi`'yı listeden çıkar. |
| 27 | Düşük | Giriş | `engine.py:2092` | Çift düzeyi redde kalan adaylara "kazanan" olarak ilk aday yazılıyor. Yalnız kayıt yanlış. | Reddedilen adayı geçir. |
| 28 | Düşük | Canlı | `reconcile_live.py:176` | Yabancı emir taraması yalnız borsa ve state tamamen düzken yapılıyor. | Pozisyon varken de aralıklı tam tarama yap. |
| 29 | Düşük | Canlı | `binance_futures.py:527` | Marjin/kaldıraç doğrulamasında `ok` her satırda eziliyor; son satır belirliyor. | Satırları `and` ile birleştir. |
| 30 | Düşük | Canlı | `binance_futures.py:1480,1514` | `_delivered` ve `_delivered_funding` kümeleri hiç temizlenmiyor. Yavaş bellek büyümesi. | Pozisyon kapanınca temizle. |
| 31 | Düşük | Çıkış | `position_manager.py:182` | Başa-baş stop vuruşu `trail_stop` yazılıyor. Belgeli tercih, ama R1 gibi hedef kollarında istatistiği bulandırır. | Ayırt edici alan ekle (isteğe bağlı). |
| 32 | Düşük | Karşı-olgu | `counterfactual.py:3,522`, `alinmayan_sonuc.py:98` | Modül başlığı "1 saatlik mum" diyor, kod kurulum zaman dilimini kullanıyor. `run_shadow` "aynı hesap" diyor ama sabit 5 bp kullanıyor ve üretimde çağıranı yok. Alınan / alınmayan satırları farklı zaman eksenine göre pencereleniyor. | Belgeleri düzelt. `run_shadow`'u kaldır ya da bağla. |
| 33 | Düşük | Karşı-olgu | `counterfactual.py:83` | Stop vuruşu hep -1R; açılış boşluğu sayılmıyor. Çıkış karşı-olgusu boşlukta açılış fiyatını kullanıyor. | Boşlukta açılış fiyatını kullan. |
| 34 | Düşük | Ders | `lesson.py:5172,4848,3222,239` | `_apply_more` (gece sınırı 1), gölge dönem (`shadow_weeks=0`) ve `evaluate_monitor`'ın ikiz parametreleri ölü. Dataclass yorumları ve spec tablosu (2.0 / 8 / 0.5) gerçek değerlerle uyuşmuyor. | Ölü yolları sil, belgeyi güncelle. |
| 35 | Düşük | DL1 | `dl1_cikarim.py:4,145,319`, `cekirdek.py:43,126`, `gunluk_kontrol.py:22` | Eski docstring'ler (8 kanal, tek paket, "D + 24 saat"). `paket_yasi_gun`, `PAKET_YOLU`, `BAR` kullanılmıyor. Yedek koşu, kapısı boş kalmış paketi "yenilendi" sayıyor. | Belgeleri düzelt, ölü kodu sil. Yedek denetimde kapı alanına da bak. |
| 36 | Düşük | Sağlık | `scripts/health_run.py:800-822` | DL1 denetimi ilk bozuk pakette dönüyor. Hangi zaman diliminin sorunlu olduğu mesajda yok. | Tüm dilimleri tara, adını yaz. |
| 37 | Düşük | M1 | `trader_ml/walkforward.py`, `guards.py:19`, `package.py:26`, `ml_package.py:103,114` | `make_folds` ve walk-forward sabitleri üretimde kullanılmıyor. Kilit korumaları hep erken dönüyor. `threshold_quantile` elle 0,98 yazılmış. `user_approved` okunmuyor; `paper_only` yorumu eski. | Temizle. Meta değerini `THRESHOLD_Q`'dan al. |
| 38 | Düşük | Kâğıt | `paper.py:45,431,587`, `funding.py:27,58` | `funding_max_wait_s` ayardan beslenmiyor. `accrue` ve `floor_funding_time` üretimde çağrılmıyor. `last_mark` iki kez yazılıyor. Funding yedek mark'ı o anki mumun açılışı. | Ölü kodu sil ya da broker bunları kullansın. |
| 39 | Düşük | Kurulum | `b1.py:348`, `signals.py:125,275` | B1'de `rr_below_min` dalı ulaşılamaz (RR sabit 2.0, `rr_min` en çok 2.0). `pick_candidate` T1 > R1 önceliği ulaşılamaz. `from_mapping`'de iki dal aynı. | Temizle. |
| 40 | Düşük | Belge | `docs/strateji-spec.md:204`, `arm_guard.py:2`, `veri_haber.py:29`, `weekly_summary_run.py:13`, `config.py:590` | Çıkış nedenleri "yalnız T1 / R1" diye anlatılıyor; kod tüm iz ve hedef kollarına uyguluyor. "Seans yüzünden giriş engellenmez" eski. "21 hisse" yanlış (20). "Aylık tavan 20 $" yanlış (pay 2 $). "Yalnız paper" hata mesajı eski. | Metinleri güncelle. |
| 41 | Düşük | Ayar | `config.py:164`, `config_loader.py:29`, `exit_counterfactual.py:44,64,66,696`, `exit_modes.py:54`, `kayip_freni.py:34` | Ölü kod: `_PAPER_ONLY_KEYS`, `validate`/`load_config`, `SIM_REASONS`, `TRAIL_BOUND_NOTE`, kopya `CF_EXIT_BLOCK_DAYS`, `_funding_fn`'in `now_ms`'i, `ExitModes.any`, `ardisik_kayip`. | Sil. |
| 42 | Düşük | Sunucu | `health_run.py:31,36,89`, `kurulum_gozcu.py:48,237`, `health_backup.py:108`, `deploy/trader-health.service:4,31` | 60 sn bütçesi uygulanmıyor (`deadline` okunmuyor). `BOTS` ve `_iso` ölü. Başarısız geri alma her 2 dakikada üst sınırsız yeniden deneniyor. Birimde eski docker bağımlılığı ve eski yol var. | Temizle. Geri almaya deneme sınırı koy. |
| 43 | Düşük | Risk | `risk_ladder.py:22`, `risk.py:403`, `kol_kucultme.py:106`, `uzun_yon` ayarı, `gates.py:415,546` | K3/K4 basamakları ulaşılamaz. Adım 10'un kâğıt dalı adım 4'ün tekrarı. Panel kol çarpanı kapıdan farklı veriyle hesaplanıyor. `min_gun=60` etkisiz. Takvim ve `arms_off` her adayda diskten okunuyor. | Düşük öncelikli temizlik. |
| 44 | Düşük | Telegram | `tg_sade.py:88`, `yorumcu.py:253`, `yorumcu_run.py:174` | Yasak kelime denetimi yalnız testlerde çalışıyor. `telegram_ozeti` çağrılmıyor. Geçici API hatası da günün dosyasını yazıyor; aynı gün yeniden deneme yalnız `--force` ile olur. | Geçici hatada dosya yazma. Ölü kodu sil. |
| 45 | Düşük | Haber | `haber_sinyal.py:207`, `hb1.py` | Üretici ve HB1 aynı alım zamanlı olaylarda farklı sıralama anahtarı kullanıyor. Yalnız yedek `olay_kimligi` yolunu etkiler. | Tek anahtar kullan. |
| 46 | Düşük | Canlı | `brokers/binance_futures.py:58` | Algo durumu `TRIGGERED` "filled" olarak eşleniyor. Dolum miktarı 0 gelebilir. Etkisini doğrulayamadım. | `TRIGGERED`'ı dolum miktarı gelene kadar "new" say ya da testle kanıtla. |

## Yanlış çıkan aday bulgular

| Alan | İddia | Neden yanlış |
|---|---|---|
| Kâğıt | Tasfiye boşluğunda kapanış iyimser (`paper.py:563`) | İzole teminatta kayıp teminatla sınırlı. Tasfiye fiyatından kapatmak doğru. |
| Kâğıt | Tasfiye ücreti giriş fiyatından, bakiye tabanı yok | Ücret kalan bakım teminatına denk. Toplam kayıp teminata eşit çıkıyor. |
| DL1 | Kısmi kârın ek komisyonu düşülmüyor | Kısmi çıkış çıkışı ikiye böler. Toplam çıkış nominali aynı, tek tur masraf yeterli. |
| M1 | `paper_only` paket canlıda yükleniyor | Kalite kapısız yayın ve "canlı = kâğıt" kullanıcı kararı. Yalnız yorum eski (#37). |
| Ders | `paper_auto=false` iken yollar ayrışıyor (yüksek) | Onaysız ders kullanıcı kararı. Tek ayar dosyası var, bugün ayrışma yok. Tuzak #19'da. |
| Ders | `calibration: null` karar vermiyor | Bilinçli (WP-08: kalibrasyon yalnız bilgi). |
| Ders | `exit_breakeven` / `exit_partial` yalnız T1 | Belge de T1 diyor; tutarlı. |
| Risk | `_DAILY_INCLUDES_OPEN_RISK` kâğıtta bütçeyi yok ediyor | Belgeli tercih. Açık riski `max_open_risk` sınırlıyor. |
| Risk / giriş | Testnet kâğıt kapılarını görmüyor (2 bulgu) | Bilinçli. Karar "canlı = kâğıt"; testnet kilitli limitlerle kalıyor. |
| Giriş | `etiket_rejim` çift düzeyi sayılıyor | Kod yorumunda açıkça seçilmiş tasarım. |
| Çıkış | İz süren stop kapanışa bakıyor, çift çıkış üretebilir | Ajan da "hata değil" diyor. Davranış kâğıtta ve canlıda aynı. |
| Çıkış | Taban `bar_close`, testnet farklı davranır | Testnet zaten kasıtlı farklı. Geri test kısmı #17'de. |
| Kâğıt | `cost_overrides` canlıda etkisiz | Canlıda dolum gerçek; kayma benzetimi beklenmez. Blok rapor için okunuyor. |
| Canlı | `order_quote` kâğıtta yok | Kâğıtta emir defteri sorgusu olamaz. Karar yoluna girmiyor. |
| Canlı | "Testleri okumadım" bulgusu | Bulgu değil. |
| Ayar | `max_positions: 24` ile küme tavanları yineleniyor | İçeriksiz. Farklı katman tavanları, çelişki yok. |
| M1 | Tarihsel ve kâğıt etiketleri karışıyor | Spec 5.3 ikisini aynı hedef sayıyor. |
| M1 | `FEATURES` haritası ilgisiz | Yalnız defter bilgisi. |
| Haber | Tatil penceresi emtia için 1 saat erken | Takvim notunda "temkinli" diye belgeli. |
| Giriş | `tasfiye_okunamadi` hesap düzeyi olmalı | Hesap adayın giriş/stop değerinden yapılıyor; adaya özgü sayılması makul. |
| Risk | Adım 4 ve adım 10 kayan noktada tutarsız | İki koşul matematiksel olarak aynı. Yalnız tekrar var (#43). |

## Notlar (emin olunamayanlar)

- **#4 günlük sınır:** 19 Kasım sonrası %8'e dönen bir karar başka bir belgede olabilir. Yalnız `tasarim-kararlari.md` tarandı.
- **`_select` yön çıkarımı (`binance_futures.py:1530`):** `known` yokken yön son işlemden çıkarılıyor. Kapanıştan sonra aynı pencerede yeni giriş varsa yön ters çıkabilir. Pratikte oluşup oluşmadığını göremedim.
- **`_orphans` ve `opening` durumu (`reconcile_live.py:794`):** `opening` çiftleri atlama listesinde değil. O anda `reduce_only` emir bulunup bulunmayacağını doğrulayamadım.
- **Kaybolan bekleyen hedef (`engine.py:1654`):** durum `active` kalırsa bar kapanışı yedeği çalışmaz. Mutabakatın `_targets` adımı düzeltiyor görünüyor; uçtan uca izlemedim.
- **DL1 sağlık yolu:** sağlık veri kökünden, motor kod kökünden okuyor. Sunucuda ikisi `/opt/trader` gibi görünüyor; kurulum betiğiyle kesinleştirmedim.
- **Kör kalma geri alımı (`lesson.py:4539`):** yalnız son etkinleştirme dersin `apply`'ı ise çalışıyor. Diğer durumların istenen davranış olup olmadığı belirsiz.
- **Gözcü ve çıkış kodu 7 (`kurulum_gozcu.py:142`):** kapıdan bilerek duran motor "çalışmıyor" sayılıp geri alma tetikleyebilir. Kod yolu uyuyor; çıkış 7'nin tam anlamını okumadım.
- **Haber bütçe yeniden denemesi:** `budget.json` `retry` bloğunun haber kolunda kullanılmadığı iddiası için `budget.py` açılmadı.
- **Örneklem içi eşik (M1 ve DL1):** eşik eğitim puanlarının %98'liği. Tasarım tercihi sayılabilir; canlı tetik oranı beklenenden düşük çıkabilir.
- **`toplam_buyukluk_kat: 3`:** kaldıraç 3 ve teminat tavanı yüzünden çoğu durumda bağlayıcı değil. Mark sapmasında devreye girer.
- **Açılmadan bırakılanlar:** `uzun_yon` önbellek koşulu, `_pa.prepare`'daki iki ATR tanımı, haber isteminin kısa kodları, `_parse_dt` farkı, `trigger_tf`'nin ders menüsünde etkisiz olması.
- **Eşik aralıkları ve kaldıraç:** `PAPER_LIMITS` / `LIVE_LIMITS` üst sınırları (0,24 / 0,16) ayardan gevşek, kaldıraç her yerde 3. İkisi de doğru; hata değil, bilgi.
- **Kısmen doğrulanan iki madde:** #32'deki `LIST_CLOSED_MAX` kesmesi ve `arm_conflict` raporunda `arm_id` yedeği olmaması kodda var, etkisi küçük.

---
Maliyet: tarama 4.63 $, dogrulama 3.26 $ (Agent SDK, promosyon kredisi).
