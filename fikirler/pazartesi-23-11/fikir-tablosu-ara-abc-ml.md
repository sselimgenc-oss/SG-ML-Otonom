# Son tablo: 1. tur + 649 strateji kitabı (ABC) + 43 ML kitabı

**Ne yapıldı:** 454 strateji kartı ile 41 ML kartı (toplam 495) tek tek yeniden gruplandı; 38 tema birleştirme ve ayırmalarla **34 temaya** indi. Hiçbir kart atılmadı; her kartın hangi temaya gittiği `tema_esleme_abc_ml.json` dosyasında. "Bizde var mı" sütunu kart yazarlarının iddiasına göre değil, **koda bakılarak** dolduruldu.

**Koddan çıkan üç önemli düzeltme:**
- **Rastgele giriş testi aslında yazılmış.** 1. turda "yok" denmişti. Araç kodda duruyor (`stats/k2_simulasyon.py`, ayrıca `stats/spa.py`) ama hiçbir rapora ya da komuta bağlanmamış; yani hiç çalıştırılmıyor.
- **40 özellikli yeni filtre paketi (v2) hazır ama kapalı.** Hacim, mum şekli, BTC piyasa durumu ve fonlama bilgisi içeriyor, testleri yazılmış. Kâğıt bot ayarında açılmamış, eski paket (v1) çalışıyor. Kitapların "ekleyin" dediği pek çok özellik bu pakette zaten var.
- **Aynı yön sınırı kâğıtta %16.** İşlem başı %1 riskle 16 aynı yönlü işleme izin veriyor; 41/47 short yığılmasını fiilen frenlemiyor (1. turdaki tespit doğrulandı).

## Sıralı tablo

| # | Fikir | Ne işe yarar (1 cümle) | Tür | Kaç kaynakta | Bizde var mı (doğrulanmış) | Emek | Puan 0-5 |
|---|---|---|---|---|---|---|---|
| 1 | Yön karnesi + aynı yön sınırını sıkılaştır (long/short ayrı rapor, kötü giden yönde yeni girişi durdur) | Tek yöne yığılmayı görünür kılar ve tek bir piyasa hareketiyle toplu kaybı önler. | risk | 10 kitap + 1. tur (2) | Kısmen. Sınır kodda var ama %16 ile frenlemiyor; yöne göre rapor var, yön bazlı durdurma yok. | az | 5 |
| 2 | Basit rakiplerle kıyas (rastgele giriş, hep short, al-ve-tut, hiç işlem yapmama) | Kârın kurallarımızdan mı yoksa düşen piyasada short olmaktan mı geldiğini gösterir. | doğrulama | 12 kitap + 1. tur (2) | Kısmen. Rastgele giriş aracı yazılmış ama hiçbir rapora bağlı değil; hep-short ve al-ve-tut kıyası yok. | az | 5 |
| 3 | Birlikte hareket eden pozisyonları tek bahis say (son günlerin fiyat benzerliğine göre sınır; benzerlik artınca yeni girişi kıs) | Görünüşte farklı 10 pozisyonun aslında tek büyük bahis olmasını engeller. | risk | 22 kitap (5'i ML) + 1. tur (2) | Kısmen. Sabit grup sınırı var; canlı benzerlik ölçümü yok. | orta | 5 |
| 4 | Gecikme ve maliyet dayanıklılık testi (1-2 mum geç giriş; komisyon/kaymayı artırıp tekrar) | Kârın küçük bir gecikme ya da biraz pahalı işlemle eriyip erimediğini gösterir. | doğrulama | 9 kitap + 1. tur (2) | Yok. Maliyet sabit oranla dahil; tarama yok. | az | 4 |
| 5 | Hazır duran yeni özellik paketini (v2) aç ve eskisiyle yan yana ölç | Hacim, mum şekli, BTC durumu ve fonlama bilgisini filtreye verir; long tarafını canlandırabilir. | ML | 16 + 14 + 22 kitap (hacim, mum, çapraz piyasa temaları) + 1. tur | Kısmen. Kod ve testleri var; kâğıt ayarında kapalı (v1 çalışıyor). | az | 4 |
| 6 | Filtre kararında "yön" bilgisinin ağırlığını denetle | Filtrenin long'ları sırf long olduğu için eleyip elemediğini ortaya çıkarır. | ML | 1. tur (1) | Kısmen. Özellik önemi hesabı var; yön odaklı rapor yok. | az | 4 |
| 7 | İşlem sırasını karıştırarak en kötü düşüş ve batma olasılığı | Şansın kötü gittiği senaryoda kasanın ne kadar eriyeceğini ve %1 riskin güvenli olup olmadığını gösterir. | doğrulama | 3 kitap + 1. tur (1) | Kısmen. Yeniden örnekleme var ama yalnız getiri kalitesi aralığı için; düşüş/batma dağılımı yok. | az | 4 |
| 8 | Canlıya geçiş için önceden yazılmış sayısal şartlar ve asgari işlem sayısı | Az sayıda şanslı işleme bakıp erken karar vermeyi engeller. | doğrulama | 7 kitap (2'si ML) + 1. tur (1) | Kısmen. Kapı, güven aralığı ve asgari kayıt uzunluğu hesabı var; iki varyantı eşleştirip kıyaslayan test yok. | az | 4 |
| 9 | Göreceli güç özelliği (coin BTC'ye göre, hisse endekse göre güçlü mü zayıf mı) | Genel piyasa düşerken ayakta kalan varlıkta long, zayıf olanda short seçmeye yardım eder. | ML | 6 kitap (+ elenenlerden 2 kart) | Yok. | az-orta | 4 |
| 10 | Kalabalık taraf bilgisi: fonlama aşırılığı, açık pozisyon-fiyat uyumu, long/short hesap oranı | Herkes aynı tarafa yığıldığında ters hareket riskini filtreye haber verir. | ML | 27 kitap + 1. tur (1) | Kısmen. Fonlama özelliği ve açık pozisyon toplayıcısı var (kapalı); long/short oranı yok. | orta | 3 |
| 11 | Pozisyon boyutunu ayarla: oynak varlıkta küçült, sonra filtre güvenine göre yarım ölçek | Çok oynayan varlığın ve emin olunmayan işlemin kasaya etkisini eşitler. | risk | 14 kitap (1'i ML) + 1. tur (2) | Kısmen. Stop mesafesine göre sabit %1 ve toplam açık risk tavanı var; oynaklığa ya da güvene göre ölçek yok. 47 işlemle erken. | orta | 3 |
| 12 | Şok freni: sert hareket döneminde boyutu küçült, aralık kenarı kolunu beklet | Ani çöküş/sıçrama günlerinde "ucuz" diye alınıp ezilen işlemleri azaltır. | risk | 7 kitap (2'si ML) + 1. tur (1) | Kısmen. "Volatil" rejim etiketi ve oynaklık özellikleri var; otomatik fren yok. | orta | 3 |
| 13 | Deneme bütçesi + "plato" kontrolü (en iyi ayarın komşuları da iyi mi) | Çok deneyip şans eseri iyi görüneni seçmeyi önler. | doğrulama | 8 kitap + 1. tur (2) | Kısmen. Deneme kaydı ve düzeltme var; üst sınır kuralı ve komşu ayar raporu yok. | az | 3 |
| 14 | Kol karnesini genişlet (ortalama kazanç/kayıp, güven aralığı, likit/az likit ayrımı) | "Çok kazanıyor ama az kazandırıp çok kaybettiriyor" tuzağını yakalar. | doğrulama | 1. tur (1) + 2 kitap | Kısmen. Kol, rejim, parite, yön dökümü var; güven aralığı ve likidite ayrımı yok. | az | 3 |
| 15 | Bilanço ve büyük veri günlerinde işlem yasağı (21 hisse için) | Açıklama anındaki zar atışına benzeyen sert hareketlerden uzak tutar. | risk | 6 kitap + elenenlerden 4 kart | Yok. Takvim verisi de yok; dışarıdan almak gerekir. | orta | 3 |
| 16 | Alış-satış farkı (spread) kapısı: fark açıkken girme | Gece ve seans dışı sığ piyasada pahalı girişleri engeller (özellikle hisse/emtia). | risk | elenenlerden 2 kart + 9 kitap (maliyet teması) | Yok. Emir anındaki fark kaydediliyor ama buna göre reddetme yok. | az | 3 |
| 17 | Herkesin baktığı seviyelere uzaklık (önceki gün/hafta/ay tepe-dip, pivot, yuvarlak sayı) | Kırılım ve yeniden test kollarına seviyenin "önemli" olup olmadığını söyler. | ML | 15 kitap + 1. tur (1) | Kısmen. v2'de son 20/50 mum tepe-dip uzaklığı ve aralık temas sayısı var; takvim seviyeleri ve pivot yok. | orta | 3 |
| 18 | Çıkış denemeleri: rejime göre çıkış modu, sıkı/geniş stop ikizi, geçmiş geri çekilme yüzdeliğine göre stop | Aynı girişten daha çok kâr bırakan çıkış biçimini bulur. | strateji | 14 kitap (1'i ML) + elenenlerden 1 kart | Kısmen. Başa baş, kısmi kapama, iz süren stop ve "başka çıkış olsaydı" ölçümü var; rejime göre seçim ve yüzdelik stop yok. | orta | 3 |
| 19 | Düşüşte oynaklığın daha çok arttığını ölçen özellik | Filtreye düşüş ile yükselişin farklı davrandığını öğretir. | ML | 1. tur (1) + 2 ML kitabı | Yok. | az | 3 |
| 20 | Seans özellikleri (hisse/emtia): açılış boşluğu yüzdesi, gece-gündüz getirisi, açılış aralığı | Seanslı varlıklarda açılışın yönü ve gücü hakkında bilgi verir. | ML | 35 kitap (3'ü ML) | Kısmen. Saat/gün özellikleri ve seans etiketine göre maliyet var; boşluk ve açılış aralığı yok. | orta | 2 |
| 21 | Hacim profili ve hacim ağırlıklı ortalama fiyata (VWAP) uzaklık | En çok işlem görülen fiyat bölgelerini destek/direnç olarak verir. | ML | 11 kitap | Yok. | orta | 2 |
| 22 | Ortalamaya dönüş kolunu güçlendir (osilatör eşiğini trende göre kaydır, aşırı uzamada bekle) | Yatay piyasada kenardan dönüş işlemlerini inceltir. | strateji | 27 kitap | Kısmen. Aralık kenarı kolu var; osilatör/bant yok. Kartların çoğu düşük puanlı. | orta | 2 |
| 23 | "Akıllı para" bölgeleri (kırılımdan önceki son ters mum, doldurulmamış boşluk) | Fiyatın geri dönüp tepki verebileceği bölgeleri işaretler. | strateji | 10 kitap | Yok. Tanımlar öznel; kanıtı zayıf. | çok | 2 |
| 24 | Çift işlemi / piyasa-nötr (bir coin long, benzeri short) | Piyasa yönünden bağımsız kazanç arar; yön yığılmasına yapısal çare olabilir. | strateji | 10 kitap (2'si ML) | Yok. Yeni bir motor ve iki bacaklı emir ister. | çok | 2 |
| 25 | İlk tura alınmayan toplu kutu: Gann/Elliott/harmonik/zaman sayımı (35 kitap), opsiyon verisi (10), emir defteri (11), Renko vb. alternatif grafik (8), ML yöntem denemeleri: dolar barı, Kalman, desen eşleme (7), psikoloji (7), zarara ekleme/martingale (4) | Çoğu ya kanıtsız, ya bizde verisi yok, ya da risk kurallarımıza aykırı. | karışık | 82 kitap toplam | Yok (bilerek). | çok | 0-1 |

## İlginç kutusu

| Fikir | Hüküm |
|---|---|
| Kapı Bekçisi (zaman+fiyat ölçüsüyle "son tepe denemesi") | Kanıtsız; ölçüm öznel, tek kitap. Beklet. |
| Ertesi gün aşağı boşlukla açılışta alım ("terör boşluğu") | Test edilebilir ama yalnız 21 hisse ve 4 emtiada (kriptoda boşluk yok); kitapta eşik yok, gün içi maliyet yüksek. Düşük öncelik. |
| İnce profil bölgelerinde hızlı geçiş hedefi | Veri/altyapı yok; önce hacim profili (satır 21) gerekir. |
| Osilatörü ters çözüp fiyat hedefi bulma | Test edilebilir, matematiği net; ama osilatörlü kolumuz yok. Satır 22 yapılırsa eklenir. |
| Super Bowl göstergesi | Batıl; yılda tek gözlem, tesadüf ilişkisi. |
| Finansal astroloji ve ay döngüsü | Batıl; kitabın kendisi de kanıt sunmuyor. |
| Fox dalga (5 nokta kuralı) | Kuralı kodlanabilir ama kanıtsız; az örnek + çok serbest ayar = kendimizi kandırma riski. |
| Ritmik ekleme/çıkarma (lehe gittikçe parça parça ekle) | Test edilebilir ("başka çıkış olsaydı" aracıyla); risk sınırlarını zorlar, şimdi değil. |
| Takvim spreadi (yakın-uzak vadeli fark) | Veri yok; yalnız süresiz (perpetual) sözleşme işliyoruz. |
| Günün kesirli dakikalarında dönüş (39. ve 48,75. dakika) | Batıl; ayrıca en küçük mumumuz 15 dakika, ölçemeyiz. |

## Zaten var — tekrar yapma

Kitapların ve kartların "yok/kısmen" dediği ama kodda bulunan işler (yalnız sonuçlarını düzenli okumak yeter):
- Boşluklu ileri-yürüyen test (purge + embargo), çapraz doğrulama bölmeleri.
- Deneme sayısına göre düzeltilmiş başarı ölçüsü, aşırı uyum olasılığı raporu, çoklu test düzeltmesi, deneme kaydı.
- Filtre olasılığının doğruluk (kalibrasyon) kontrolü; filtre puanı-gerçek sonuç sıra uyumu.
- Trend kırılımı, sıkışma kırılımı, kırılım yeniden testi, sahte kırılım dönüşü, iki bacaklı ve trend geri çekilmesi, aralık kenarı kolları (kitapların en çok anlattığı kurulumlar bunlar).
- Üst zaman dilimi yön bilgisi (1s/4s/1g eğim, "4s ile uyumlu mu" özelliği) ve rejim etiketi; rejim, kol, parite ve yöne göre döküm.
- Başa baş stop, kısmi kapama, iz süren stop; "başka çıkış olsaydı" ve reddedilen sinyallerin sanal takibi.
- Stop mesafesine göre sabit %1 boyut, toplam açık risk tavanı ("portföy ısısı"), günlük zarar sınırı, likidasyon güvenlik payı, acil durdurma.
- Kötü giden kolu kademeli küçültme ve kaldırma; beklenen-gerçekleşen sapma izleyicisi.
- Üçlü bariyer etiketi, eksik mum tamamlama, aralık kenarına temas sayısı özelliği.

## Elenen kartlardan örnek kontrol (eşik çok mu sıkı?)

Tam 3 puan aldığı için düşen 704 karttan rastgele 60'ına bakıldı. **9 kart (5 ayrı fikir) tabloya girmeyi hak ediyor**, yani eşik bir miktar sıkı:
- Bilanço/haber penceresinde işlem yasağı: 4 kart (Swing Trading için..., Opsiyon Trading St..., Swing Trading Kura..., 1 Dakikalık Forex...). Satır 15 oldu.
- Spread/likidite kapısı: 2 kart (Robbie Burns Trading Stratejileri; Price Action Tradi...). Satır 16 oldu.
- Olasılık tabanlı (yüzdelik) stop: 1 kart (Kase'in Teknik Analizi). Satır 18'e eklendi.
- Kaç bağımsız seviyenin üst üste geldiğini sayan özellik: 1 kart (En İyi 10 Forex Stratejisi). Satır 17'ye not.
- Short için daha sıkı, long için gevşek şart: 1 kart (Al ve Tut Stratejisini Yenen...). Satır 1'in bir çeşidi.

Kalan 51 kartın çoğu ya tablodaki temaların tekrarı (yön dengesi, korelasyon, göreceli güç, asgari işlem sayısı) ya da bizde zaten olan şeyler; gerisi zayıf. Öneri: eşiği toptan düşürmeyin; yalnız "risk" ve "doğrulama" türündeki 3 puanlık kartları ikinci kez tarayın. Kaçan değerli fikirler hep bu iki türden, basit ve operasyonel kurallar.

## Tema dökümü (34 tema, 495 kart; hiçbiri atılmadı)

Kırılım/sıkışma 6 · Ortalamaya dönüş/osilatör/aşırı uzama 30 · Hacim profili/VWAP 13 · Çıkış yönetimi 17 · Trend/üst zaman dilimi 20 · Yön dengesi 10 · Korelasyon/portföy/kol ağırlığı 25 · Gann/Elliott/harmonik/zaman sayımı 42 · Fonlama/açık pozisyon/duygu 27 · Opsiyon verisi 12 · Sahte kırılım/likidite süpürme 21 · Akıllı para bölgeleri 11 · Seans/açılış/boşluk/takvim 41 · Emir defteri 16 · Çift/arbitraj 11 · Göreceli güç 7 · Çapraz piyasa/risk iştahı 24 · Haber/olay 6 · Martingale (kaçın) 4 · Pozisyon boyutlama 15 · İleri-yürüyen test/plato 9 · Yanlılık ve maliyet gerçekçiliği 9 · Rastgele giriş/basit rakip 15 · Çoklu test düzeltmesi 6 · Batma olasılığı 3 · ML yöntemleri 10 · Destek/direnç/pivot 15 · Hacim özellikleri 20 · Mum kalıpları 14 · Psikoloji 7 · Oynaklık rejimi/şok freni 7 (yeni) · Bozulma alarmı 5 (yeni) · Alternatif grafik 9 (yeni) · İstatistik yeterlilik 8 (yeni).

Gruplamadaki başlıca düzeltmeler: "Kırılım" temasındaki kartların yarısı aslında seans/saat ve zaman sayımı kartıydı; "Çıkış" temasına stop avı kartları, "Sahte kırılım" temasına bootstrap testleri, "Emir defteri" temasına rastgele giriş testi karışmıştı. Açık pozisyon kartları opsiyon temasından ayrılıp fonlama/duygu ile birleşti; fonlama ile duygu, boşluk ile seans ile takvim, Gann ile Elliott, korelasyon ile kol ağırlığı birleştirildi. 41 ML kartının 7'si emir defterine, 5'i korelasyona, kalan 29'u 16 temaya dağıldı.

## Önerilen ilk tur (8 fikir)

**1, 2, 4, 7, 8, 5, 6, 3** sırasıyla.
- Önce 1 (yön sınırı): bilinen tek somut zayıflığımız; sınır kodda hazır, yalnız sayıyı düşürmek ve yön karnesi eklemek gerekiyor.
- Sonra 2, 4, 7, 8 (dört ölçüm): hepsi az emek, hiçbiri botun davranışını değiştirmiyor, yalnız "kâr gerçek mi, dayanıklı mı, ne zaman güveneceğiz" sorularını cevaplıyor. 2 numaranın aracı zaten yazılmış; bağlamak yeter.
- Sonra 5 ve 6 (filtre): hazır paketi açıp eskisiyle kıyaslamak ve filtrenin long'ları neden elediğine bakmak, yeni kod yazmadan long tarafını düzeltebilecek en ucuz iki adım.
- En son 3 (canlı benzerlik sınırı): 22 kitapla en çok tekrar eden ve tek 5 puanlık kartı içeren fikir, ama orta emek; önceki ölçümler bitince yapılmalı.
- Yeni strateji kolları (satır 21-24) ve kutu 25 bu tura alınmadı: 47 işlemle hiçbirinin işe yaradığı kanıtlanamaz.
