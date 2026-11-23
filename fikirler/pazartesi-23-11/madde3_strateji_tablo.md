# Madde 3: Strateji arşivinden çıkan fikirler

**Kaynaklar (yalnız bunlar):** A/B/C grupları (649 kitap) ve D grubu (2546 kitap). ML/Algo arşivi ve X/PDF fikirleri bu tabloda sayılmadı; onlar Madde 2'de.

**Kısaca:** Binlerce kitap bize yeni bir "sihirli strateji" vermedi. Verdiği şey: aynı birkaç risk ve ölçüm kuralını tekrar tekrar söylüyorlar ve bunların çoğu bizde yarım.

**"Kaç kaynakta" nasıl okunur:** kitap sayısı, yaklaşık üst sınır (etiketleri yardımcı modeller koydu). Çok kitapta geçmesi fikre güveni artırır, önceliği tek başına artırmaz.

**"Bizde var mı"** koda bakılarak dolduruldu.

## A. Açığımızı kapatır (para kaybını önler)

| # | Fikir | Ne işe yarar (1 basit cümle) | Kaç kaynakta | Bizde var mı | Emek | Puan |
|---|---|---|---|---|---|---|
| 1 | Yön karnesi + aynı yön sınırını sıkılaştır | 41/47 short gibi tek yöne yığılmayı görünür kılar ve frenler. | ~115 | Kısmen. Sınır var ama kâğıtta %16; 16 aynı yönlü işleme izin veriyor. | az | 5 |
| 2 | Birlikte hareket eden pozisyonları tek bahis say | Farklı görünen 10 pozisyonun tek büyük bahis olmasını engeller. | ~158 (arşivin en çok tekrar eden fikri) | Kısmen. Sabit grup sınırı var; canlı benzerlik ölçümü yok. | orta | 5 |
| 3 | Kayıp serisinden sonra otomatik fren (3 kayıptan sonra riski yarıya indir) | Kötü günde zararın katlanmasını yavaşlatır. | ~71 | Kısmen. Günlük %8 sınırı ve kötü kolu küçültme var; seri freni yok. | az | 4 (önce geçmiş işlemlerde dene) |
| 4 | Toplam pozisyon büyüklüğü tavanı | Çok sayıda pozisyonun toplamda kasanın kat kat üstüne çıkmasını engeller. | ~23 | Kısmen. İşlem başına tavan var; toplam için tavan bulamadım. | az | 3 |
| 5 | Masraf kapısı: alış-satış farkı açıkken ya da masraf stopa göre büyükken girme | Kazansa bile masrafını çıkarmayacak işlemleri eler. | ~41 | Kısmen. Oran hesaplanıp izleniyor; girişte reddetme yok. | az | 3 |
| 6 | Bilanço ve büyük veri günlerinde işlem yasağı (21 hisse) | Açıklama anındaki zar atışına benzeyen hareketlerden uzak tutar. | ~58 | Yok. Takvim verisi de yok. | orta | 3 |

## B. Kendimizi kandırmayı önler (sadece ölçer, botu değiştirmez)

| # | Fikir | Ne işe yarar (1 basit cümle) | Kaç kaynakta | Bizde var mı | Emek | Puan |
|---|---|---|---|---|---|---|
| 7 | Basit rakiplerle kıyas (rastgele giriş, hep short, al-ve-tut) | Kârın kurallardan mı, düşen piyasada short olmaktan mı geldiğini gösterir. | ~68 | Kısmen. Rastgele giriş aracı yazılmış ama hiçbir rapora bağlı değil. | az | 5 |
| 8 | Gecikme, masraf ve mum saati kaydırma testi | Kârın küçük bir gecikme ya da mumun 15 dk kaymasıyla eriyip erimediğini gösterir. | ~41 | Kısmen. Filtre kapısında masraf stresi var; geç giriş ve kaydırma yok. | az | 4 |
| 9 | Şans ve kuyruk testi (sırayı karıştır, en iyi 1/2/5 işlemi çıkar) | Kârın birkaç şanslı işleme bağlı olup olmadığını gösterir. | ~75 | Kısmen. Yeniden örnekleme yalnız getiri kalitesi için. | az | 4 |
| 10 | Canlıya geçiş için önceden yazılı şartlar + asgari işlem sayısı | Az sayıda şanslı işleme bakıp erken karar vermeyi engeller. | ~43 | Kısmen. Kapı ve güven aralığı var; eşleştirilmiş kıyas yok. | az | 4 |
| 11 | "Komşu ayarlar da iyi mi" + ayarı en kötü döneme göre seç | Çok deneyip şans eseri iyi görüneni seçmeyi önler. | ~77 | Kısmen. Deneme kaydı ve düzeltme var; komşu ayar raporu yok. | az | 3 |
| 12 | Kol karnesi + kayıp kümeleri raporu | Hangi durum, kol ve yönün birlikte kaybettirdiğini haftalık gösterir. | ~100 | Kısmen. Her işleme not yazılıyor, en iyi/en kötü nokta kaydı var; küme sayımı ve düşüş ölçüleri yok. | az | 3 |

## C. Botu geliştirebilir (daha çok kazanç)

| # | Fikir | Ne işe yarar (1 basit cümle) | Kaç kaynakta | Bizde var mı | Emek | Puan |
|---|---|---|---|---|---|---|
| 13 | Hazır duran yeni özellik paketini (v2) aç, eskisiyle yan yana ölç | Hacim, mum şekli, BTC durumu ve piyasa genişliği bilgisini filtreye verir. | ~125 | Kısmen. Kod ve testleri hazır; kâğıt ayarında kapalı. | az | 4 |
| 14 | Göreceli güç (coin BTC'ye, hisse endekse göre güçlü mü) | Piyasa düşerken ayakta kalanda long, zayıfta short seçmeye yardım eder. | ~29 | Yok. | az-orta | 4 |
| 15 | Çıkış denemeleri (zaman stopu süresi, stop sonrası bekleme, rejime göre çıkış) | Aynı girişten daha çok kâr bırakan çıkışı bulur. | ~78 | Kısmen. Zaman stopu (48 mum sabit) ve "başka çıkış olsaydı" ölçümü var; tarama yok. | orta | 3 |

**Tabloya sığmayanlar (hepsi 2-3 puan, tam liste `son_tablo_final.md` içinde):** boyutu oynaklığa göre ayarlama (~81 kitap), kalabalık taraf ve fonlama (~109), önemli seviyelere uzaklık (~60), BTC-ETH ayrışması (~5), seans özellikleri (~125, çok tekrar ediyor ama kanıtı zayıf), hacim profili (~30), yeni kollar (çift işlemi, akıllı para bölgeleri, kârdakine ekleme).

**Bilerek alınmayan kutu (~280 kitap):** Gann, Elliott, Fibonacci zaman sayımı, opsiyon verisi, emir defteri, alternatif grafikler, zarara ekleme. Çoğu kanıtsız, verisi yok ya da risk kurallarımıza aykırı.

## Zaten var — tekrar yapma

Kitapların "ekleyin" dediği ama kodda bulunanlar: kırılım, yeniden test, sahte kırılım, geri çekilme ve aralık kenarı kolları; başa baş stop, kısmi kapama, iz süren stop, zaman stopu; sabit %1 risk, toplam açık risk tavanı, günlük zarar sınırı; zarardaki pozisyona ekleme yok (parite başına tek pozisyon); aynı mumda yeniden giriş engeli; kötü kolu küçültme; borsa ile pozisyon eşitleme. Haber ve duygu verisi 21 Kasım'da sizin kararınızla kaldırıldı.

## İlginç kutusu

| Fikir | Hüküm |
|---|---|
| Mum saatini kaydırma testi | Test edilebilir, ucuz, güçlü. Satır 8'e alındı. |
| Ayarı en kötü döneme göre seçme | Test edilebilir. Satır 11'e alındı. |
| Alakasız bir seriyle sahte sinyal üretip kıyaslama | Test edilebilir, ucuz. Satır 7'ye alındı. |
| Fonlama "taşıma" eğilimi (aşırı pozitif fonlamada short'a eğilim) | Test edilebilir, verisi var. Güçlü trendde fonlama haftalarca aşırı kalır; önce filtre özelliği olarak dene. |
| BTC-ETH ayrışması | Test edilebilir, veri var. Kaynağı kanıt sunmuyor; rastgele girişe karşı ölçülmeden kullanılmaz. |
| Varlığın baskın döngü uzunluğunu ölçme | Matematiği net ama kriptoda kalıcı döngü kanıtı zayıf, serbest ayar çok. Beklet. |
| Zaman yerine olaya göre mum | Test edilebilir; bütün veri hattını değiştirir. Kısa vadeli kollara sakla. |
| Stablecoin arzına göre long/short ağırlığı | Veri almak gerekir; haftalık seri, gözlem az. Düşük öncelik. |

**Batıl ya da sınanamaz diye elenenler:** salınım süresini 1,28 ile çarpma, PHI elipsi ve spirali, Fibonacci zaman bölgeleri, 53 gün ve 212 hafta döngüsü, 3 günlük döngü, "piyasa yapıcının niyeti" ve "stop avı" anlatıları, astroloji ve ay döngüsü, Super Bowl göstergesi.

## Gelecek kısa vadeli kollar için (scalp/day)

Şu an en küçük mumumuz 15 dakika. 1-5 dakikalık kollar kurulurken ilk bakılacaklar:

**Önce kurallar:**
- Masraf kapısı (satır 5) zorunlu; kısa vadede masraf stopun büyük kısmını yer.
- Günlük işlem sayısı tavanı ve kayıp serisi freni (satır 3).
- Büyük veri açıklamasından önce ve sonra birkaç dakika giriş yok (8 kitap).
- İlerlemeyen pozisyonu birkaç dakikada kapatan kısa zaman stopu.

**Sonra denenecek fikirler:**
- Açılış aralığı ve ilk saat aralık oranı (10 kitap); hisse ve emtia için.
- Hacim patlamasından başlatılan ortalama fiyata (sabitlenmiş VWAP) uzaklık (5 kitap).
- Seans açılışında sahte hareket sonrası dönüş; bizdeki sahte kırılım kolunun dakikalık sürümü.
- Emir defteri ve işlem akışı dengesizliği (7 kitap); verisi yok, kartların hepsi 1 puan.
- Zaman yerine olaya göre mum.

**Şimdiden biriktirilmesi gereken veri:** 1 dakikalık mum ve emir defteri kaydı, long/short oranı geçmişi, bilanço ve makro veri takvimi.

## Öneri

1. Önce **1** (yön sınırı) ve **7** (basit rakip kıyası): biri bilinen açığı kapatır, diğeri kârın gerçek olup olmadığını söyler; ikisi de az emek.
2. Sonra **8, 9, 10** ölçümleri (9'un içinde kayıp freni **3** de denenir) ve **13** (hazır paketi açmak): botu riske atmadan dayanıklılığı ve long tarafını ölçer.
3. En son **2** (korelasyon): arşivin en çok desteklenen fikri ama orta emek. Yeni kol ve Gann/Elliott türü fikirler alınmasın; 47 işlemle hiçbiri kanıtlanamaz.
