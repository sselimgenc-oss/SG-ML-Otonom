# Son tablo (FİNAL): 1. tur + 43 ML kitabı + 649 strateji kitabı + 2546 kitaplık D grubu

**Kısaca:** Kitap arşivi bize yeni bir "sihirli strateji" vermedi. Verdiği şey şu: yüzlerce kitap aynı birkaç risk ve doğrulama kuralını tekrar ediyor, ve bunların çoğu bizde ya yarım ya da yazılmış ama çalıştırılmıyor. İlk tur yine "ölç ve sınırı sıkılaştır" işleri; yeni kol yok.

**Ne yapıldı:** D grubunun 2458 güçlü kartı etiketlendi: 1875'i eski temalara oturdu, 163'ü bizde zaten var, 234'ü ilgisiz, 113'ü yeni. Yeni kartlardan çıkan 27 aday tema üst üste biniyordu; **20 ayrı gruba** indi, bunların 4'ü eski temalara katıldı. Toplam: 34 eski + 10 ek (Y1-Y10) + 16 yeni = **60 tema**, aşağıda 30 satırda toplandı.

**"Kaç kitapta" sütunu nasıl okunmalı:** Eski sayı + D grubu. D etiketlerini yardımcı modeller koydu; geniş temalarda (ör. yön dengesi, korelasyon) sayı üst sınırdır, kesin değil. Çok kitapta geçmesi fikre **güveni** artırır, önceliği tek başına artırmaz.

**Koda bakınca çıkan yeni düzeltmeler (bu turda):**
- **Zaman stopu zaten var.** Kartlar "yok" diyordu; pozisyon 48 mum içinde sonuçlanmazsa kapanıyor. Eksik olan yalnız bu sayının denenmesi.
- **Zarardaki pozisyona ekleme zaten imkânsız.** Parite başına tek pozisyon tutuluyor, ekleme kodu yok. 7 kitabın "yasaklayın" dediği şey yapısal olarak yasak.
- **Haber/duygu verisi 21 Kasım'da sizin kararınızla silindi.** 5 kitabın önerdiği "sosyal medya duygusu" teması bu yüzden tabloya alınmadı.
- **Piyasa genişliği özelliği hazır pakette (v2) var**, ama paket kapalı. 7 kitabın önerisi satır 7'yi açınca gelir.
- **Maliyet stres testi kısmen var.** Filtre kapısı komisyonu 2 katına çıkarıp taraf başına 5 baz puan ekleyerek bakıyor. Geç giriş testi yok. (Önceki tabloda "yok" demiştim; düzeltildi.)
- **İşlem başına büyüklük tavanı var (kasanın 1 katı), toplam için ayrı tavan bulamadım.** Kâğıtta 24 pozisyona izin var.

## Sıralı tablo

| # | Fikir | Ne işe yarar (1 cümle) | Tür | Kaç kitapta | Bizde var mı (doğrulanmış) | Emek | Puan 0-5 |
|---|---|---|---|---|---|---|---|
| 1 | Yön karnesi + aynı yön sınırını sıkılaştır | Tek yöne yığılmayı (41/47 short) görünür kılar ve tek hareketle toplu kaybı önler. | risk | ~115 | Kısmen. Sınır var ama kâğıtta %16; %1 riskle 16 aynı yönlü işleme izin veriyor. Yön bazlı durdurma yok. | az | 5 |
| 2 | Basit rakiplerle kıyas (rastgele giriş, hep short, al-ve-tut, alakasız seriyle sahte sinyal) | Kârın kurallardan mı, yoksa düşen piyasada short olmaktan mı geldiğini gösterir. | doğrulama | ~68 | Kısmen. Rastgele giriş aracı yazılmış ama hiçbir rapora bağlı değil; diğer kıyaslar yok. | az | 5 |
| 3 | Birlikte hareket eden pozisyonları tek bahis say | Farklı görünen 10 pozisyonun aslında tek büyük bahis olmasını engeller. | risk | ~162 (arşivin en çok tekrar eden fikri) | Kısmen. Sabit grup sınırları var (ör. büyük kripto 6, hisse 8); canlı benzerlik ölçümü yok. | orta | 5 |
| 4 | Gecikme, maliyet ve mum saati kaydırma testi | Kârın küçük bir gecikme, pahalı işlem ya da mumun 15 dk kayması ile eriyip erimediğini gösterir. | doğrulama | ~41 | Kısmen. Filtre kapısında maliyet stresi var; 1-2 mum geç giriş ve saat kaydırma testi yok. | az | 4 |
| 5 | Şans ve kuyruk testi: işlem sırasını karıştır, en iyi 1/2/5 işlemi çıkar, ani %20-30 şok uygula | Kötü şansta kasanın ne kadar eridiğini ve kârın birkaç şanslı işleme bağlı olup olmadığını gösterir. | doğrulama | ~76 | Kısmen. Yeniden örnekleme yalnız getiri kalitesi için; düşüş dağılımı, "en iyiler çıkınca" ve şok senaryosu yok. | az | 4 |
| 6 | Canlıya geçiş için önceden yazılı sayısal şartlar + asgari işlem sayısı | Az sayıda şanslı işleme bakıp erken karar vermeyi engeller. | doğrulama | ~44 | Kısmen. Kapı ve güven aralığı var; iki varyantı eşleştirip kıyaslayan test yok. | az | 4 |
| 7 | Hazır duran yeni özellik paketini (v2) aç, eskisiyle yan yana ölç | Hacim, mum şekli, BTC durumu, fonlama ve piyasa genişliği bilgisini filtreye verir; long tarafını canlandırabilir. | ML | ~130 | Kısmen. Kod ve testleri hazır; kâğıt ayarında kapalı. | az | 4 |
| 8 | Filtrede "yön" bilgisinin ağırlığını denetle | Filtrenin long'ları sırf long olduğu için eleyip elemediğini ortaya çıkarır. | ML | ~8 | Kısmen. Özellik önemi hesabı var; yön odaklı rapor yok. | az | 4 |
| 9 | Kayıp serisinden sonra otomatik fren (3 kayıp ya da günlük sınırın yarısı → riski yarıya indir) | Kötü günde zararın katlanmasını yavaşlatır. | risk | ~71 | Kısmen. Günlük %8 sınırı ve kötü kolu küçültme var; ardışık kayıp raporda sayılıyor ama fren yok. | az | 4 (önce geçmiş işlemlerde dene) |
| 10 | Göreceli güç (coin BTC'ye, hisse endekse göre güçlü mü) | Piyasa düşerken ayakta kalanda long, zayıfta short seçmeye yardım eder. | ML | ~29 | Yok. | az-orta | 4 |
| 11 | Toplam pozisyon büyüklüğü (kaldıraç) tavanı | Çok sayıda dar stoplu pozisyonun toplamda kasanın kat kat üstüne çıkmasını engeller. | risk | ~23 | Kısmen. İşlem başına tavan var; toplam için tavan bulamadım. | az | 3 |
| 12 | Deneme bütçesi + "komşu ayarlar da iyi mi" + en kötü döneme göre ayar seçimi | Çok deneyip şans eseri iyi görüneni seçmeyi önler. | doğrulama | ~78 | Kısmen. Deneme kaydı ve düzeltme var; üst sınır ve komşu ayar raporu yok. | az | 3 |
| 13 | Maliyet kapısı: fark (spread) açıkken ya da maliyet stop mesafesine göre büyükken girme | Kazansa bile masrafı çıkarmayacak işlemleri eler. | risk | ~41 | Kısmen. Maliyet/risk oranı hesaplanıp izleniyor, fark kaydediliyor; girişte reddetme yok. | az | 3 |
| 14 | Pozisyon boyutunu oynaklığa ve filtre güvenine göre ayarla | Çok oynayan varlığın ve emin olunmayan işlemin kasaya etkisini eşitler. | risk | ~82 | Kısmen. Sabit %1; ölçekleme yok. 47 işlemle erken. | orta | 3 |
| 15 | Kalabalık taraf bilgisi + fonlama "taşıma" eğilimi | Herkes aynı tarafa yığıldığında ters hareket riskini haber verir. | ML | ~109 | Kısmen. Fonlama özelliği ve açık pozisyon toplayıcısı var (kapalı); long/short oranı yok. | orta | 3 |
| 16 | Şok freni + piyasa stres kapıları (sert hareket, stablecoin sapması) | Çöküş günlerinde "ucuz" diye alınıp ezilen işlemleri azaltır. | risk | ~43 | Kısmen. "Volatil" etiketi girişi atlatabiliyor; boyut küçültme ve sapma kapısı yok. | orta | 3 |
| 17 | Kol karnesini genişlet: ortalama kazanç/kayıp, düşüş derinliği-süresi, "kâra geçip başa baş kapanan" oranı | "Çok kazanıyor ama az kazandırıyor" tuzağını ve çıkışın kârı geri verip vermediğini gösterir. | doğrulama | ~90 | Kısmen. En iyi/en kötü nokta, geri verme ve zararda kalma süresi var; güven aralığı ve düşüş ölçüleri yok. | az | 3 |
| 18 | Kayıp kümeleri raporu (hangi durum + kol + yön birlikte kaybettiriyor) | Kayıpların ortak nedenini haftalık olarak önünüze koyar. | doğrulama | ~58 | Kısmen. Her işleme kodla not yazılıyor, aday ders çıkıyor; küme sayımı yok. | az | 3 |
| 19 | Bilanço ve büyük veri günlerinde işlem yasağı (21 hisse) | Açıklama anındaki zar atışına benzeyen hareketlerden uzak tutar. | risk | ~58 | Yok. Takvim verisi de yok. | orta | 3 |
| 20 | Herkesin baktığı seviyelere uzaklık (önceki gün/hafta tepe-dip, yuvarlak sayı) | Kırılım kollarına seviyenin önemli olup olmadığını söyler. | ML | ~61 | Kısmen. v2'de son 20/50 mum tepe-dip var; takvim seviyeleri yok. | orta | 3 |
| 21 | Çıkış denemeleri: zaman stopu süresini tara, stop sonrası bekleme, rejime göre çıkış | Aynı girişten daha çok kâr bırakan çıkışı bulur. | strateji | ~79 | Kısmen. Zaman stopu (48 mum sabit), stop sonrası bekleme ayarı (şu an 0) ve "başka çıkış olsaydı" ölçümü var; tarama yok. | orta | 3 |
| 22 | Öncü-artçı: BTC kırdı, benzeri gecikti; BTC yeni tepe yaptı, ETH yapmadı | Gecikmeli varlıkta fırsat ya da uyumsuzlukta uyarı arar. | ML | ~5 | Yok. | orta | 3 |
| 23 | Düşüşte oynaklığın daha çok arttığını ölçen özellik | Filtreye düşüş ile yükselişin farklı davrandığını öğretir. | ML | ~6 | Yok. | az | 3 |
| 24 | Emir biçimi: piyasa yerine limit emir, büyüklüğe bağlı kayma | Giriş masrafını düşürür; dolmayan emirlerin kaçan kârını ölçer. | risk | ~25 | Yok. Maliyet sabit oranla. | orta | 2 |
| 25 | Makro likidite ve zincir üstü veri (stablecoin arzı, faiz, borsaya giriş) | Piyasaya para girip çıktığını rejim bilgisi olarak verir. | ML | ~14 | Yok. Veri de yok. | orta | 2 |
| 26 | Seans özellikleri (açılış boşluğu, açılış aralığı, vade günü) | Seanslı varlıklarda açılışın yönü ve gücü hakkında bilgi verir. | ML | ~128 | Kısmen. Saat/gün özelliği var; boşluk ve açılış aralığı yok. D'deki 105 kartın hiçbiri 4 puan almadı: çok tekrar ediyor ama kanıtı zayıf. | orta | 2 |
| 27 | Hacim profili ve hacim ağırlıklı ortalama fiyata (VWAP) uzaklık | En çok işlem gören fiyat bölgelerini destek/direnç olarak verir. | ML | ~30 | Yok. | orta | 2 |
| 28 | Ortalamaya dönüş kolunu güçlendir + döngü uzunluğu ölçümü | Yatay piyasada kenardan dönüş işlemlerini inceltir. | strateji | ~74 | Kısmen. Aralık kenarı kolu var; osilatör ve döngü ölçümü yok. | orta | 2 |
| 29 | Yeni kollar: çift işlemi (24 kitap), akıllı para bölgeleri (52), kârdakine ekleme (6), panik düşüş sonrası tepki alımı (4), rejim geçiş olasılığı (5) | Yeni kazanç kaynağı arar. | strateji | ~91 | Yok. Hepsi yeni motor ya da öznel tanım ister; 47 işlemle kanıtlanamaz. | çok | 1-2 |
| 30 | Toplu kutu: Gann/Elliott/Fibonacci zaman sayımı, opsiyon verisi, emir defteri, alternatif grafik, martingale | Çoğu kanıtsız, verisi yok ya da risk kurallarımıza aykırı. | karışık | ~283 | Yok (bilerek). | çok | 0-1 |

**Tabloya girmeyen küçük temalar:** hatalı sıçrama mumu temizliği (11 kitap, az emek, veri hattına not), özellik dilim testi (5), hisse temel değer filtresi (7, veri yok), emtia COT verisi (2, veri yok), günlük işlem sayısı tavanı (3; kısa vadeli kollar bölümünde).

## 25 numaralı tema neydi?

**Evet, çöp kutusu.** Önceki tablonun "ilk tura alınmayanlar" satırı. D grubunda en çok kartı (279 kart, 201 kitap) o aldı, çünkü arşivin büyük kısmı bu türden. İçi: Gann/Elliott/Fibonacci/zaman sayımı ~104 kart, opsiyon ~41, emir defteri ~33, alternatif grafik ve diğerleri ~100. 279 kartın 144'ü 0-1 puan, yalnız 4'ü 4 puan.

İçinde önemli bir şey saklı mı? Baktım, beş şey çıktı, hiçbiri sıralamayı değiştirmiyor:
- **Zarardaki pozisyona ekleme yasağı (~12 kart):** yanlış kutuya düşmüş; bizde zaten yapısal olarak var.
- **"Fibonacci seviyeleri rastgele seviyelerden daha mı çok tepki veriyor" testi (4 puan):** tartışmayı ucuza kapatır; satır 2'nin aracıyla yapılır. Fibonacci kullanmaya karar verilirse önce bu.
- **Trend ve ortalamaya dönüş kollarını aynı kasada çalıştırma (4 puan):** bizde zaten böyle.
- **Zaman yerine olaya göre mum (hacim barı, yön değişimi barı; ~8 kart):** ciddi fikir ama veri hattını değiştirir; kısa vadeli kollar bölümünde.
- **Opsiyon verisinden oynaklık rejimi (~6 kart):** mantıklı ama veri yok.

## İlginç kutusu

52 adet "ilginçlik 5" kartından seçilen 8 fikir:

| Fikir | Hüküm |
|---|---|
| Mum saatini kaydırma testi (1 saatlik mumu 15/30/45 dk kaydırıp tekrar dene) | Test edilebilir, ucuz, güçlü. Satır 4'e alındı. Sonuç kaymaya çok duyarlıysa kol güvenilmez. |
| Ayarı en iyi sonuca göre değil, en kötü döneme göre seç | Test edilebilir. Satır 12'ye alındı. Daha az parlak ama daha dayanıklı ayar verir. |
| Alakasız bir seriyle sahte sinyal üretip kıyasla | Test edilebilir, ucuz. Satır 2'ye alındı. Sahte seri de aynı kârı veriyorsa bizimki şanstır. |
| Fonlama "taşıma" eğilimi (aşırı pozitif fonlamada short'a, negatifte long'a eğilim) | Test edilebilir, verisi bizde var, iki ciddi kaynak. Ama güçlü trendde fonlama haftalarca aşırı kalır; ayrı kol değil, önce filtre özelliği olarak dene (satır 15). |
| BTC-ETH ayrışması (biri yeni tepe yapar, diğeri yapmaz) | Test edilebilir, veri var. Kaynağı (ICT) kanıt sunmuyor; rastgele girişe karşı ölçülmeden kullanılmaz (satır 22). |
| Her varlığın baskın döngü uzunluğunu ölçüp stop ve süreyi ona göre ayarlama | Matematiği net, test edilebilir. Ama kriptoda kalıcı döngü olduğuna dair kanıt zayıf ve serbest ayar çok; kendimizi kandırma riski yüksek. Beklet. |
| Zaman yerine olaya göre mum (fiyat %X dönünce yeni mum) | Test edilebilir ve akademik dayanağı var. Bütün veri hattını değiştirir; kısa vadeli kollar kurulurken denenir. |
| Stablecoin arzı arttıkça yalnız long, daralırken short ağırlığı | Test edilebilir ama veri almak gerekir; haftalık seri olduğu için gözlem az, tesadüfle karışır. Düşük öncelik (satır 25). |

**Aynı listeden elenenler ve nedeni:**
- **Batıl / sayı büyüsü:** salınım süresini 1,28 ile çarpma (2 kart), PHI elipsi ve spirali (2), Fibonacci zaman bölgeleri (2), 53 gün ve 212 hafta döngüsü, 3 günlük Taylor döngüsü. Ortak özellikleri: sayının neden o sayı olduğu açıklanmıyor, kitaplar kanıt vermiyor.
- **Yanlışlanamaz anlatı:** "piyasa yapıcının niyeti", "perakende stoplarının avlanması", "kaybeden nerede diye sor". Sonradan her harekete uydurulabilir; ölçülebilir bir kurala dönmüyor.
- **Veri yok:** emir defteri dengesizliği, işlem akışı, opsiyon gama seviyeleri, merkeziyetsiz borsa likidite aralıkları.
- **Risk kurallarımıza aykırı:** "stop kullanmadan sürekli pozisyon ayarı" (Carver). Ciddi bir yazar ama bizim sabit stop ve %1 risk yapımızla çelişir.
- **Çöküş öncesi log-periyodik imza (Sornette):** bilimsel görünümlü ama çok serbest ayarlı; geçmişe iyi uyar, ileriyi tutturduğu gösterilmemiş.

## Zaten var — tekrar yapma

Kitapların ve kartların "ekleyin" dediği ama kodda bulunan işler:
- Boşluklu ileri-yürüyen test, çapraz doğrulama, deneme sayısına göre düzeltme, aşırı uyum olasılığı raporu, deneme kaydı.
- Filtre olasılığının doğruluk kontrolü; filtre kapısında maliyet stres bacağı.
- Trend kırılımı, sıkışma kırılımı, yeniden test, sahte kırılım dönüşü, geri çekilme, aralık kenarı kolları.
- Üst zaman dilimi yön bilgisi, rejim etiketi; rejim, kol, parite ve yöne göre döküm.
- Başa baş stop, kısmi kapama, iz süren stop, **zaman stopu (48 mum)**, "başka çıkış olsaydı" ölçümü, alınmayan sinyallerin sanal takibi.
- Sabit %1 boyut, toplam açık risk tavanı, günlük zarar sınırı, işlem başına büyüklük tavanı, likidasyon güvenlik payı, acil durdurma.
- **Zarardaki pozisyona ekleme yok** (parite başına tek pozisyon).
- **Aynı mumda yeniden giriş engeli** ve stop sonrası bekleme ayarı (şu an 0).
- Kötü giden kolu küçültme/kaldırma; beklenen-gerçekleşen sapma izleyicisi.
- **Operasyonel güvenlik:** borsa ile pozisyon mutabakatı, eksik stopu hemen kurma, defter-panel-Telegram mutabakatı.
- Her işleme kodla yazılan not ve aday ders; en iyi/en kötü nokta ve geri verilen kâr kaydı.
- **Piyasa genişliği, hacim, mum şekli, BTC durumu, fonlama özellikleri** (v2 paketinde, kapalı).
- **Haber ve duygu verisi:** 21 Kasım'da sizin kararınızla kaldırıldı; yeniden eklemeyin.

## Gelecek kısa vadeli kollar için (scalp/day)

Şu an en küçük mumumuz 15 dakika. Aşağıdakiler bugün tabloda düşük ya da yok, ama 1-5 dakikalık kollar kurulurken ilk bakılacak liste:

**Önce kurallar (kol açılmadan):**
- **Maliyet kapısı (satır 13) zorunlu.** Kısa vadede stop dardır; masraf stopun büyük kısmını yer. "Günlük işlem sayısı × tek işlem masrafı" brüt kârın belli bir payını aşıyorsa kol kapalı kalır.
- **Günlük işlem sayısı tavanı** ve **kayıp serisi freni (satır 9).** Sık işlemde zarar hızlı birikir.
- **Haber penceresi yasağı** (8 kitap): büyük veri açıklamasından önce/sonra birkaç dakika giriş yok.
- **Kısa zaman stopu:** N dakikada ilerlemeyen pozisyonu kapat.
- **Limit emir ve "ters seçim" ölçümü:** hemen dolan ile fiyat karşıya geçince dolan emirleri ayrı ölç (Lebron).

**Sonra denenecek fikirler:**
- **Açılış aralığı ve ilk saat aralık oranı** (10 kitap): günün tepe/dibi ilk dakikalarda oluşuyor mu; ilk saat genişse trend günü mü. Hisse ve emtia için.
- **Sabitlenmiş VWAP** (5 kitap): hacim patlaması ya da bilanço mumundan başlatılan ortalama fiyata uzaklık.
- **Seans açılışında sahte hareket sonrası dönüş** (16 kitap seans temasında): bizdeki sahte kırılım kolunun dakikalık sürümü; rastgele girişe karşı ölçülmeli.
- **Gün tipi sınıflandırma** (trend günü / dar gün) ile kol seçimi.
- **Emir defteri ve işlem akışı dengesizliği** (7 kitap): kısa vadede en mantıklı bilgi kaynağı, ama verisi yok ve kartların hepsi 1 puan (kitaplar kural vermiyor).
- **Zaman yerine olaya göre mum** (hacim barı, yön değişimi barı): sakin saatlerde az, hareketli saatlerde çok mum üretir.

## Edinmemiz gereken veriler

1. **Bilanço ve makro veri takvimi** (21 hisse için bilanço tarihleri; faiz kararı, enflasyon, istihdam). Satır 19 ve kısa vadeli haber yasağı buna bağlı. Küçük ve ucuz.
2. **Long/short hesap oranı ve açık pozisyon geçmişi.** Borsa geçmişi yalnız kısa bir süre geriye veriyor; şimdiden biriktirmeye başlamazsak satır 15 için geçmiş oluşmaz.
3. **1 dakikalık mum + emir defteri / işlem akışı kaydı.** Kısa vadeli kollar planlandığı için bugünden kaydetmeye başlamak gerekir; sonradan geriye dönük toplamak zor ve pahalı.

İkinci derecede: stablecoin arzı ve zincir üstü veri (satır 25), emtia için haftalık COT raporu (ücretsiz).

## Önerilen ilk tur (8 fikir)

**1, 2, 4, 5, 6, 7, 8, 3** sırasıyla; **9 ayrı iş olmadan 5'in içinde denenir.**
- **Önce 1:** bilinen tek somut zayıflık; sınır kodda hazır, sayıyı düşürmek ve yön karnesi eklemek yeter. D grubu bunu ~105 kitapla daha destekledi.
- **Sonra 2, 4, 5, 6:** dört ölçüm. Hiçbiri botun davranışını değiştirmez; "kâr gerçek mi, dayanıklı mı, birkaç şanslı işleme mi bağlı, ne zaman güveneceğiz" sorularını cevaplar. 2'nin aracı yazılmış, bağlamak yeter. 5 çalışırken aynı işlem serisinde kayıp freni (9) de denenir.
- **Sonra 7 ve 8:** hazır paketi açıp eskisiyle kıyaslamak ve filtrenin long'ları neden elediğine bakmak; yeni kod yazmadan long tarafını düzeltebilecek en ucuz iki adım. Paket açılınca 7 kitabın istediği piyasa genişliği de gelir.
- **En son 3:** 162 kitapla arşivin en çok tekrar eden fikri, güven çok yüksek; ama orta emek, ölçümler bitince yapılır.
- **Bu tura alınmayanlar:** yeni kollar (27-29) ve kutu 30. 47 işlemle hiçbirinin işe yaradığı kanıtlanamaz. 10 ve 11 ikinci turun başıdır.
