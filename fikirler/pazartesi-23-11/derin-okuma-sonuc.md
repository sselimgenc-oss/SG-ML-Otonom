# Derin okuma sonucu: kitaplar ne diyor, bizim kod ne yapıyor

Tarih: 23 Kasım 2026. Kod değiştirilmedi; bu belge yalnız denetim ve karar içindir.

**Girdi:** 43 kitaptan 163 bölüm kartı (1 satır bozuk, 162 okundu), 852 yöntem, 802 uyarı.
**Yöntem:** Uyarılar S1–S12 başlığı altında aynı şeyi söyleyenler birleştirilerek 43 kümeye indirildi. Her küme için kodun kendisine bakıldı.

**Önemli not:** Uyarıların yaklaşık dörtte biri "kitap bu konuda bir şey söylemiyor" türünden boş satırdı. Kalanların çoğu da sistemi yalnız kısa özetten tanıyan okuyucunun tahminiydi; koda bakınca büyük kısmı yanlış alarm çıktı.

Dosya yolları `trader/` klasörüne göredir.

---

## Bir bakışta

| Durum | Küme sayısı | Ne demek |
|---|---|---|
| Doğru yapıyoruz | 22 | Kitabın istediği şey kodda var |
| Eksik | 11 | Var ama yarım, ya da hiç yok |
| Yanlış | 3 | Kod, söylediğimiz şeyi yapmıyor |
| Ölçülemez / henüz yapılmadı | 7 | Az veriyle sınanamaz ya da kol henüz yazılmadı |

En önemli üç bulgu:

1. **Yön denetimi (S9) canlı süzgeci görmüyor.** Rapor "yön özelliğinin ağırlığı"nı ölçtüğünü söylüyor ama gece eğitilen aile paketlerini okuyamıyor; sonuç hep "paket yok" çıkıyor. Deneme paketiyle doğrulandı.
2. **Gece eğitilen süzgeç hiç sınanmadan devreye giriyor.** 10 işlemle, yaklaşık 25 özellikle eğitiliyor; "görmediği veride işe yarıyor mu" kontrolü yok. Purge/embargo, deflated Sharpe, PBO yalnız araştırma tarafında var, gece yolunda yok.
3. **Şans testi (S7) kayıpların peş peşe gelmesini hesaba katmıyor.** İşlemler tek tek karıştırılıyor; aynı gün birlikte kaybeden işlemler ayrılıyor, en kötü düşüş olduğundan küçük görünüyor.

---

## Düzeltilmesi gerekenler

Emek: küçük = yarım gün, orta = 1–3 gün, büyük = bir hafta ve üstü. "Risk" sütunu motoru bozar mı sorusunun cevabıdır.

| # | Ne | Kitap ne diyor (kaç uyarı / kaç kitap) | Bizde durum (dosya:satır) | Emek | Risk | Öncelik |
|---|---|---|---|---|---|---|
| 1 | **YANLIŞ – S9 yön denetimi kör** | Yön özelliğinin ağırlığı ölçülmeli (27 / 16) | Rapor `f_side_sign` adını ve `meta.features` alanını arıyor (`src/trader_reports/tur1_olcum.py:44`, `:399`). Canlı aile paketinde ad `side_long` (`src/trader_core/ml_live_v2.py:263`), alan `meta.ozellikler` (`paket/ortak_ogrenme/filtre.py:164`). Sonuç: sessizce atlanıyor. | Küçük | Yok (yalnız rapor) | 1 |
| 2 | **EKSİK – gece süzgeci sınanmadan yayına giriyor** | Az veride aşırı uyum; görülmemiş veride doğrulama şart (16 / 13) | Eşik 10 işlem (`src/trader_engine/ogrenme_filtre.py:37`, `:343`), eğitim doğrudan kayda geçiyor (`:355`). Eğitim içi tek geçiş, sınama yok (`paket/ortak_ogrenme/filtre.py:151-158`). Hafifleten: güçlü düzenlileştirme (`:23`) ve eşik taban oranın 0,9 katı (`:25`). | Orta | Düşük (süzgeç yalnız "hayır" der; kapatılırsa giriş serbest) | 1 |
| 3 | **EKSİK – S7 karıştırma seri bağımlılığını yok ediyor** | Blok/yerine koyarak örnekleme; kayıplar kümelenir (27 / 14) | Saf sıra karıştırma (`src/trader_reports/tur1_olcum.py:340`). Hazır araç duruyor ama kullanılmıyor (`src/trader_core/stats/stats.py:727`). | Küçük | Yok (yalnız rapor) | 1 |
| 4 | **YANLIŞ – tanım ile kod uyuşmuyor** | — (bizim bulgu) | Özetlerde "gradient boosting + üçlü bariyer etiketi" yazıyor. Canlı gece süzgeci ridge lojistik (`paket/ortak_ogrenme/filtre.py:1`, `:41`), etiket gerçekleşen işlemin R > 0 olması (`:151`). Gradient boosting ve üçlü bariyer yalnız araştırma tarafında (`src/trader_ml/models.py:97`, `labels.py`). | Küçük (belge düzelt) | Yok | 2 |
| 5 | **YANLIŞ – günlük kollar testten sessizce düşüyor** | — (bizim bulgu) | Zaman dilimi tablosunda `1d` yok (`src/trader_reports/tur1_olcum.py:43`). Günlük kol işlemleri rastgele giriş kıyasına girmiyor ve atlanan sayısına da yazılmıyor (`:184`); gecikme testinde "veri yok" oluyor. 8 kol kıyas dışı. | Küçük | Yok | 2 |
| 6 | **EKSİK – süzgeç yalnız alınan işlemlerden öğreniyor** | Seçim yanlılığı, örnek örtüşmesi (28 / 17) | Yalnız kapanan işlemler eğitime giriyor (`ogrenme_filtre.py:255-275`, `filtre.py:141`). Süzgecin reddettikleri hiç geri gelmiyor. "Alınsaydı ne olurdu" verisi mevcut ve araştırma yolu kullanıyor (`src/trader_ml/setup_filter/train.py:150-158`); gece yolu kullanmıyor. Örnek ağırlığı da yalnız araştırmada (`src/trader_ml/weights.py`). | Orta | Düşük | 2 |
| 7 | **EKSİK – al-tut / piyasa kıyası yok** | Rakip olarak piyasanın kendisi de olmalı (8 / 5) | Rakipler: rastgele giriş, hep long, hep short, hiç işlem (`tur1_olcum.py:257-262`). "Hep long/short" aynı giriş anlarında tahmini (`:237-239`); gerçek al-tut yok. | Küçük | Yok | 2 |
| 8 | **EKSİK – rakip bizimle aynı masrafı ödemiyor** | Kıyas aynı masraf modeliyle (8 / 7) | Rastgele giriş sabit 2/5/5 baz puan ödüyor, fonlama yok (`src/trader_core/stats/k2_simulasyon.py:40-44`, not `tur1_olcum.py:233`). Bizim hisse/emtia kaymamız 4–20 baz puan (`config/engine.paper.json:31`). Hata bizim aleyhimize, yani güvenli tarafta; yine de elma-armut. | Küçük | Yok | 3 |
| 9 | **EKSİK – canlı şartlarında düşüş ve çoklu deneme maddesi yok** | Çoklu deneme düzeltmesi (32 / 21), azami düşüş şartı (5 / 5) | Beş madde var (`tur1_olcum.py:462-476`); deflated Sharpe/PBO araçları mevcut (`stats.py:310`, `:534`) ama listeye bağlı değil. Azami düşüş maddesi yok. | Küçük | Yok | 3 |
| 10 | **EKSİK – "2 rejimde pozitif" şartı zayıf** | Rejim tanımı ve yeterli örnek (39 / 27) | Rejim başına 10 işlem ve toplam > 0 yetiyor (`tur1_olcum.py:30`, `:457`); güven aralığı aranmıyor. 10 işlem şansla pozitif çıkabilir. | Küçük | Yok | 3 |
| 11 | **EKSİK – kayma sabit, oynak günde artmıyor** | Kayma oynaklığa ve seansa bağlı (39 / 24) | Sabit baz puan (`src/trader_engine/brokers/paper.py:440-447`). Seans ayrımı var (açık/kapalı/hafta sonu). Masraf x1,5–x2 testi kısmen karşılıyor. | Orta | Orta (kâğıt sonuçlarını değiştirir) | 3 |
| 12 | **EKSİK – aynı yön sınırı adet değil risk** | — (bizim bulgu) | Belgede "en çok 6 pozisyon"; kodda aynı yön riski kasanın %6'sı (`config/engine.paper.json:15`, `src/trader_core/risk.py:367-369`). Kayıp freni açıkken işlem riski yarıya indiği için 12 pozisyona kadar izin çıkar. Toplam risk aynı kalır; karar gerektirir. | Küçük | Düşük | 3 |
| 13 | **EKSİK – gecikme testi yaklaşık** | Gecikmede stop ve çıkış da yeniden oynatılmalı (85 / 37 gecikme uyarısının bir kısmı) | Yalnız giriş fiyatı kaydırılıyor; stop, boyut, çıkış aynı (`tur1_olcum.py:272-286`). Rapor bunu açıkça yazıyor. | Orta | Yok | 4 |
| 14 | **EKSİK – en kötü senaryo tek yönlü** | Kalın kuyruk (20 / 15) | "En iyi N işlemi çıkar" var (`tur1_olcum.py:352-355`); "en kötü kaybı iki kez yaşa" gibi ters senaryo yok. | Küçük | Yok | 4 |

Not: 13 ve 14, yukarıdaki 11 eksik sayısına dahil değildir; küçük iyileştirmelerdir.

---

## Doğru yaptıklarımız

| Konu | Kitabın istediği (uyarı / kitap) | Kanıt |
|---|---|---|
| S1 yön karnesi rejimle birlikte okunuyor | Yön yoğunluğu rejimden ayrı yorumlanmamalı (42 / 25) | Yön × rejim, × varlık sınıfı, × kol kırılımı: `src/trader_reports/tur1_olcum.py:418-425` |
| S1 bağımsız bahis sayısı | Aynı gün işlemleri bağımsız sayılmamalı (5 / 4) | Gün kümeli güven aralığı: `src/trader_reports/stats.py:40-56` |
| S2 korelasyon zamanla değişir | Sabit pencere krizi kaçırır (17 / 9) | Saatte bir yenilenen 30 günlük kayan pencere: `src/trader_engine/korelasyon_grubu.py:17`, `:52-67` |
| S2 seanslı araçlar | Hisse/emtia ile 7/24 kripto eşzamanlı değil (2 / 2) | Yalnız ardışık saatler arası getiri (`:21-31`); 200'den az ortak getiride sabit kümeye dönüş (`:16`, `:117-118`) |
| S2 gürültü | "30 gözlem az" (5 / 5) – yanlış alarm | Pencere 30 gün × 24 saat ≈ 720 gözlem, en az 200 şart |
| S3 tam durdurma | Yalnız yarıya indirmek yetmez (9 / 8) | Günlük %8'de yeni giriş yok (`src/trader_core/risk.py:333-334`), ayrıca acil durdurma (`src/trader_engine/killswitch.py`) |
| S3 açık zarar sayılıyor | Gerçekleşmemiş kayıp da izlenmeli (1 / 1) | Kasa = cüzdan + açık zarar/kâr: `src/trader_engine/brokers/paper.py:165` |
| S3 frenin kalkma kuralı net | Geri açma kuralı tanımlı olmalı (2 / 2) | İlk kazançta ya da yeni günde kalkar: `src/trader_core/kayip_freni.py:5-8` |
| S3 fren yalnız küçültür | Otomatik uygulanmalı, artırmamalı | `kayip_freni.py:80-85` |
| S4 toplam büyüklük tavanı | Tavan gerçek fiyatla hesaplanmalı | Güncel fiyatla, kasanın 3 katı: `src/trader_engine/gates.py:348-366` |
| S5 rastgele rakip yapıyı koruyor | Aynı sayı, yön, stop, tutma süresi (11 / 10) | `tur1_olcum.py:215-217` |
| S5 istatistik sınama | Tek sayı yetmez, anlamlılık (8 / 7) | p değeri ve çoklu düzeltme: `src/trader_core/stats/k2_simulasyon.py:157`, `:170` |
| S6 gecikme ve masraf testi | 1–2 mum geç, masraf x1,5–x2 (85 / 37) | `tur1_olcum.py:36-37`, `:304-313` |
| S6 araca göre masraf | Her araçta aynı masraf olmaz (6 / 6) | Araç ve seans bazlı kayma: `config/engine.paper.json:31` |
| S6 fonlama masrafa dahil | — | `tur1_olcum.py:168-170` |
| S7 az örnek uyarısı | Küçük örnekte sonuç bilgi amaçlı (11 / 9) | 30'dan az işlemde "yetersiz örnek": `tur1_olcum.py:26`, `:48` |
| S8 işlem sayısı şartı | Yeterli örnek (69 / 36) | En az 300: `tur1_olcum.py:27` |
| S8 güven alt sınırı | Aralık bağımlılığı hesaba katmalı (52 / 32) | Gün kümeli alt sınır: `tur1_olcum.py:454`, `:465` |
| S8 mühürlü dönem | Görülmemiş veri korunmalı (33 / 19) | Yapısal kilit: `src/trader_engine/holdout.py:8-18`; rapor da süzüyor `tur1_olcum.py:91` |
| S8 kademeli canlı geçiş | Kâğıt ile gerçek farklıdır (20 / 13) | Canlı sınırlar ve basamak: `src/trader_core/risk.py:43-47`, `src/trader_core/risk_ladder.py` |
| S9 sınıf dengesi | Kazanan/kaybeden oranı dengesiz (16 / 13) | Eşik taban orana göre: `paket/ortak_ogrenme/filtre.py:157-158` |
| S9 gelecekten bilgi sızması | Özellik karar anında bilinmeli (4 / 4) | Karar anı özellikleri, etiket alanları dışarıda: `src/trader_core/ml_live_v2.py:271-273`, `src/trader_ml/setup_filter/features.py:33-36` |

---

## Ölçülemeyen ya da henüz yapılmamış olanlar

| Konu | Kitap ne diyor | Durum |
|---|---|---|
| S2 eşik 0,7 ve 30 gün | "Keyfi, kitapta yok" (31 / 18) | Kitaplar sayı vermiyor; ~55 işlemle sınanamaz. Kullanıcı kararı olarak kalır. |
| S3 eşikler 5 kayıp / %4 | "Kendi verinle sına" (23 / 15) | Önceden sabitlendi (doğru). Etkisi ancak fren birkaç kez tetiklenince ölçülür. |
| S4 3 kat tavan | Bazı kitaplar çok daha sıkı (8 / 6) | Kitap sayıları hisse için, kaldıraçsız. Karar konusu. |
| S4, S6 piyasa etkisi, kısmi dolum, likidite | (39 / 29) | Kâğıt boyutta anlamsız; canlıda küçük boyutla ölçülür. |
| S10 v2 özellik paketi | Çoklu deneme ve fonlama/hacim zamanlaması (33 / 20) | Paket kapalı, kıyas yapılmadı. Az veriyle sonuç güvenilmez. |
| S11 haber kolu | (9 / 7) | Yalnız veri toplanıyor, karar yoluna girmiyor: `scripts/haber_run.py:2-4`. |
| S12 derin öğrenme kolu | Az veride aşırı uyum (6 / 3) | Kod yok. Kitaplar bu veri miktarında beklemeyi destekliyor. |

---

## Yeni fikirler (en iyi 10)

251 "yeni" etiketli yöntemden seçildi. Elenenler: zaten bizde olanlar (ileri yürüyüş, mühürlü dönem, bar kapanışı bekleme, acil durdurma, kol küçültme/karantina, CUSUM kayma izleme, kalibrasyonun araştırma tarafı), hisse temel analizi, yüksek frekans ve emir defteri yöntemleri.

| # | Fikir | Kaynak (puan, kitap sayısı) | Bize faydası | Emek | Risk | Az veriyle olur mu |
|---|---|---|---|---|---|---|
| 1 | Hangi işlemden başlasaydık en kötü düşüş ne olurdu | 4, 1 kitap | Şans testini tamamlar; canlıya kötü anda başlama riskini gösterir | Küçük | Yok (rapor) | Evet |
| 2 | Kazanç/kayıp sırası rastgele mi (koşu testi) | 3, 2 kitap | Kayıp freninin anlamlı olup olmadığını söyler; kayıplar kümeleniyorsa fren işe yarar | Küçük | Yok (rapor) | Kısmen (30+ işlem) |
| 3 | Zaman dilimi × masraf tablosu | 4, 1 kitap | 15 dakikalık kollarda masrafın kârın ne kadarını yediğini gösterir; 15m zaten gölgede | Küçük | Yok (rapor) | Evet |
| 4 | Giriş/çıkış verimliliği | 4, 1 kitap | Görülen en iyi kârın ne kadarını aldık; "geri verme" ölçümü var (`src/trader_reports/exits.py:126-131`), oran eklenir | Küçük | Yok (rapor) | Evet |
| 5 | Düşüşten toparlanma süresi | 3, 1 kitap | Düşüş derinliği yanında süresi; canlı şartına eklenebilir | Küçük | Yok (rapor) | Evet |
| 6 | Süzgeç puanı kalibrasyon tablosu | 3, 1 kitap | "%60 diyorsa gerçekten %60 mı"; düzeltme 2 ile birlikte | Küçük | Yok (rapor) | Kısmen |
| 7 | Uzun dönem boğa/ayı/yatay yön filtresi | 4 + 3 + 3, 3 kitap | Short yoğunluğuna doğrudan cevap; önce gölge blok olarak ölç | Orta | Düşük (gölgede); açılırsa orta | Evet (gölgede) |
| 8 | Kol karnesini aile ortalamasına çekme (büzülme) | 3 + 3, 2 kitap | 3–5 işlemli kolda şansa göre kol kapatmayı önler | Orta | Düşük | Evet, tam bunun için |
| 9 | Hafta sonu / tatil / büyük haber öncesi planlı küçülme | 4, 1 kitap | Hisse ve emtia kollarında seans dışı boşluk riski; önce yalnız ölç | Orta | Orta (çıkışlara dokunur) | Önce ölçüm |
| 10 | Oynaklık tahmini (kümelenme, asimetri) | 4 + 4 + 4 + 3, 3 kitap | Stop genişliği ve kayma varsayımı için; önce gölge özellik | Orta | Düşük (gölgede) | Kısmen |

Öneri sırası: 1–6 tek bir rapor güncellemesinde birlikte yapılabilir (toplam 1–2 gün, motora dokunmaz). 7 ve 8 ondan sonra.

---

## Kullanıcı kararları

1. **Yön denetimini düzeltelim mi?** (Düzeltme 1) Öneri: evet, hemen. Şu an "yön özelliği baskın mı" sorusunun cevabı yok; short yoğunluğu varken en çok lazım olan ölçüm bu.
2. **Gece süzgeci sınanmadan mı çalışsın?** (Düzeltme 2) Üç seçenek: (a) olduğu gibi kalsın, (b) eşik 10 işlemden 30'a çıksın, (c) önce "tek tek dışarıda bırakarak" sınansın, sınamayı geçemeyen aile için süzgeç kapalı kalsın. Öneri: (c); geçici olarak (b).
3. **Süzgeç reddettiği sinyallerden de öğrensin mi?** (Düzeltme 6) Öneri: evet; veri zaten toplanıyor.
4. **Şans testi blok örneklemeye geçsin mi?** (Düzeltme 3) Öneri: evet, ikisi yan yana raporlansın.
5. **Aynı yön sınırı adet mi, risk mi?** (Düzeltme 12) Şu an risk (%6). Fren açıkken 12 pozisyona izin veriyor. Öneri: risk kalsın, yanına "en çok 6 adet" tavanı eklensin.
6. **Kayıp freni gece yarısını aşsın mı?** Şu an yalnız aynı gün içindeki 5 ardışık kayıp sayılıyor (`src/trader_core/kayip_freni.py:63-65`); gece yarısı sayaç sıfırlanıyor. Az işlemle bir günde 5 kayıp nadir, yani ardışık kol pratikte az tetiklenir. Öneri: son 5 işlem, gün sınırı olmadan; kalkma kuralı aynı.
7. **Canlı şartlarına iki madde eklensin mi?** (Düzeltme 9, 10) Azami düşüş sınırı ve rejim başına en az 30 işlem. Öneri: evet; şartı sıkılaştırır, gevşetmez.
8. **Belgelerdeki "gradient boosting" ifadesi düzeltilsin mi?** (Düzeltme 4) Öneri: evet. Canlı süzgeç ridge lojistik; az veride doğru seçim de bu.
9. **S10, S11, S12 ne zaman?** Öneri: üçü de beklesin. Kitapların ortak görüşü: bu veri miktarında yeni özellik paketi ve derin öğrenme yalnız aşırı uyum üretir. 300 işlem eşiğinden önce açılmasın.
10. **Yeni fikirlerden hangileri?** Öneri: 1–6 (yalnız rapor) hemen; 7 ve 8 gölgede; 9 ve 10 sonraya.
