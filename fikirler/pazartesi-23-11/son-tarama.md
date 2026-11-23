# Son tarama: "Bir şey kaçırdık mı?"

Tarih: 23.11.2026. Kod değişmedi; bu yalnız okuma ve karar notu.

**Nasıl tarandı:** Strateji arşivindeki 3.195 kitap kartının 12.729 fikri anahtar kelimeyle tarandı. Puanı 3 ve üstü olan 1.547 strateji/özellik fikri temalara ayrıldı; hiçbir temaya girmeyen 505 başlık tek tek okundu. Puanı 3'ün altındaki kartlar yalnız kelime taramasıyla görüldü. ML tarafında 43 + 163 kart ve 35 X/PDF kartı başlık düzeyinde okundu. Yardımcı model (Haiku) kullanılamadı, çünkü bu oturumda alt ajan aracı yoktu; tarama doğrudan yapıldı.

**"Kaç kitapta":** fikrin başlıkta geçtiği kitap sayısı, yaklaşık. Parantez içi, açık kural veren kitaplardır (kart no).

**† işareti:** önceki tabloda adı geçmiş ama işe dönmemiş ve "bekleyen" listesine de girmemiş fikir.

## 1. Sonuç

- **Strateji arşivi (Grup 2):** Büyük bir şey kaçmamış, ama bir strateji türü eksik: aşırı uçta ortalamaya dönüş. Onun dışında kalanlar küçük giriş filtreleri, hisse seansı fikirleri ve iki çıkış kuralı.
- **ML/Algo arşivi (Grup 1):** Yeni yöntem yok. Kaçanlar beş küçük ölçüm ve veri temizliği işi; hiçbiri modeli değiştirmiyor.

## 2. Gözden kaçan

### Grup 2 — Strateji

**A. Ortalamaya dönüş (bizde bu türde kol yok; R1 yalnız aralık kenarına bakıyor)**

| Fikir | Ne yapar | Kaç kitapta | Veriyle test edilir mi | Emek | Puan |
|---|---|---|---|---|---|
| Aşırı uçta dönüş kolu (2 günlük RSI ya da Bollinger %b), yalnız uzun trend yönünde | Yükselen trendde 2-4 gün üst üste sert düşeni alır, toparlanınca çıkar. | ~28 (kural veren 3: A72, A264, D1271) | Evet, 1g ve 4s. Kanıt: Connors, 2001-2012 hisse, masrafsız; bizde yeniden ölçülmeli. | orta | 4 |
| Tasfiye dalgası sonrası dönüş | Açık pozisyon sert düşer, mum ve hacim çok büyürse ters yönde kısa işlem dener. | ~15 (D818, D506, D1959, A158) | Evet. Tasfiye verisi yok, açık pozisyon düşüşü vekil olur. Olay sayısı az. | orta | 3 |
| Tek büyük mumdan sonra dönüş ölçümü | 3 ATR'den büyük düşüşten sonraki N mumun getirisini ölçer; önce rapor, sonra kol. | ~17 (D506, D614, D2087) | Evet. | az | 3 |
| Kısa vadeli sıralı ters dönüş | Son haftanın en çok düşenini alır, en çok çıkanını satar. | ~4 (A340, A192) | Evet. Kriptoda kanıt karışık, devir yüksek. | orta | 2 |

**B. Seans ve zaman (hisse ve emtia için)**

| Fikir | Ne yapar | Kaç kitapta | Veriyle test edilir mi | Emek | Puan |
|---|---|---|---|---|---|
| Açılış aralığı kırılımı † | New York açılışının ilk 15-30 dakikasının tepe/dibini kırınca o yönde girer. | ~35 (B60, D926, D807) | 15 dk ile kaba; doğrusu 5 dk (1 dk verimiz var). | orta | 3 |
| Açılış boşluğu: devam mı, kapanma mı † | Boşluk 1 ATR'den büyükse ilk 30 dakikaya göre devam ya da kapanma yönünde işlem açar. | ~97 başlıkta boşluk var (kural veren 9: A104, D568, D1615, D2490, D1290, C127) | Evet, 20 hisse + 4 emtia. Seans açılış/kapanış fiyatı gerekir. | orta | 3 |
| Saat bloğu karnesi ve seans özelliği † | Kazancı Asya/Avrupa/ABD saatine göre ayırır; kötü bloğu görünür kılar. | ~19 (D2054, D2477, D403) | Evet, mevcut işlem kayıtlarıyla. | az | 3 |
| Günlük aralık tüketimi | Gün ortalama aralığının %80'ini yaptıysa yeni trend girişini eler. | ~8 (D2065, D2434, D325) | Evet. | az | 3 |
| Gece ve gündüz getirisini ayırma | Hissede kazancın gece mi gündüz mü geldiğini ölçer; gece tutma kararına girer. | ~7 (B52, D1809) | Evet. | az | 2 |

**C. Giriş filtreleri ve özellikler**

| Fikir | Ne yapar | Kaç kitapta | Veriyle test edilir mi | Emek | Puan |
|---|---|---|---|---|---|
| Kovalama filtresi | Fiyat ortalamadan çok ATR uzaklaşmışsa ya da hareket ivmelenip hacim patlamışsa trend girişini eler. | ~52 (D334, D645, D787, D2398, A192) | Evet. Kanıt zayıf ama mekanizma net. | az | 3 |
| Aralık içi konum | Long'u yalnız aralığın alt yarısında, short'u üst yarısında kabul eder; ortadan girmez. | ~21 (D131 puan 4, A149, D153, D358, C71) | Evet. | az | 3 |
| Yeni zirvede short, yeni dipte long kapısı | Son N mumun zirvesi yeni kırılmışken short açmayı engeller ya da ayrı ölçer. | ~9 (C24 puan 4, D997, D2460) | Evet. Short yığılmasına doğrudan dokunur. | az | 3 |
| Seviyenin kaç kez denendiği | Dokunuş sayısını B1, R1 ve F1 adaylarına bilgi olarak verir. | ~36 (C59, B43, D1287, D1555, D2345) | Evet. | az-orta | 3 |
| Short'a ayrı, daha sıkı kapı | Short için ek şart ister (örn. BTC ya da endeks de düşüyor olsun). | ~8 (A84, D2017, C17, B52) | Evet. Uzun vadeli yön filtremizle kısmen örtüşür. | az | 3 |
| Alıcı tarafın hacim payı | Mumdaki hacmin ne kadarının piyasa alımı olduğunu özellik yapar. | ~4 (C113, D1205) | Evet; Binance mum verisinde hazır alan, ama çekip saklamak gerekir. | az | 3 |
| Hacim patlamasından başlatılan ortalama fiyata uzaklık † | Büyük hacimli mumdan beri ödenen ortalama fiyatın neresinde olduğumuzu söyler. | ~6 (D263 puan 4, D846, A319) | Evet. | orta | 3 |
| Bağımsız teyit sayısı | Bir adayda kaç ayrı onay olduğunu sayıp filtreye verir. | ~34 (A224, A233, D1381, D2071) | Evet. | az | 2 |
| Fiyat-osilatör uyumsuzluğu | Fiyat yeni tepe yapıp RSI/MACD yapmıyorsa dönüş uyarısı sayar. | ~175 (hiçbiri sayı vermiyor) | Evet. Çok tekrar ediyor, kanıtı zayıf; yalnız özellik olarak. | orta | 2 |
| Yükselişin yolu | Aynı getiride adım adım yükseleni, tek sıçrayışla yükselenden güçlü sayar. | 2 (A231) | Evet. | az | 2 |
| Tek günlük aşırı sıçrama cezası | Son ayda çok büyük tek gün yapmış varlığı long için zayıf sayar. | 1 (A340) | Evet. | az | 2 |

**D. Çıkış kuralları**

| Fikir | Ne yapar | Kaç kitapta | Veriyle test edilir mi | Emek | Puan |
|---|---|---|---|---|---|
| Kırılım ilerlemiyorsa erken çık † | Girişten birkaç mum sonra fiyat yol almadıysa 48 mumu beklemeden kapatır. | ~6 (D1029 puan 4, D2195, D1271) | Evet, "başka çıkış olsaydı" aracıyla. | az | 3 |
| Aşırı büyük mumda kârı al | Trend yönünde olağandışı büyük mum gelince kalan pozisyonu kapatır. | ~5 (A215, D1260) | Evet. | az | 3 |
| İlk bacak kadar hedef | Hedefi ilk hareketin boyuna eşitler. | ~10 (C47, C119) | Evet; bacak tespiti gerekir. | orta | 2 |

**E. Risk ve emir**

| Fikir | Ne yapar | Kaç kitapta | Veriyle test edilir mi | Emek | Puan |
|---|---|---|---|---|---|
| Toplu şok senaryosu ve tasfiye mesafesi | "Her şey aynı anda %X ters giderse ne kaybederiz" hesabı; tasfiye fiyatı stopa fazla yakınsa küçültür. | ~26 (D2206, A178, D1055; X5) | Evet, yalnız hesap. | az | 3 |
| Aylık zarar tavanı | Ay içi kayıp %6'yı geçince o ay yeni giriş açmaz. | ~3 (D2200, D2341) | Evet. | az | 2 |
| Girişte limit emir | Piyasa emri yerine limit koyup masrafı düşürür. | ~8 (D1312, D2360, D118) | Kısmen: 1 dk mumla dolum varsayılır, emir defteri yok. | orta | 2 |

### Grup 1 — ML/Algo

| Fikir | Ne yapar | Kaç kaynakta | Veriyle test edilir mi | Emek | Puan |
|---|---|---|---|---|---|
| Hacmi günün saatine göre normalleştir | Hacim özelliğini "bu saat için normalin kaç katı" diye verir; açılış saatleri yanıltmaz. | 5 (ML9, ML15, ML41, DR157, DR160) | Evet. | az | 3 |
| Seans dışı düz mumları gizle | Hisse/emtia kapalıyken oluşan hareketsiz mumların oynaklık ve göstergeleri bozmasını önler. | 1 (DR23) | Evet; önce bizde sorun var mı bakılır. | az | 3 |
| Benzerliği 4 saat/günlükte ölç | 15 dakikada ölçülen korelasyon olduğundan düşük çıkar; grup sınırı yanlış rahatlar. | 2 (ML9, DR146) | Evet. | az | 3 |
| Öncü gösterge sınaması | Fonlama ya da açık pozisyon fiyatı gerçekten önceden haber veriyor mu, özelliği eklemeden önce test eder. | 1 (DR42) | Evet. | az | 3 |
| Trend mi, dönüş mü testi | Her varlık ve zaman diliminde fiyatın trende mi dönüşe mi yatkın olduğunu ölçer; kol-varlık eşleşmesine yarar. | 1 (DR85) | Evet. | az | 3 |
| Canlı ile test gösterge eşitliği | Göstergelerin başlangıç verisi canlıda ve testte aynı mı kontrol eder. | 1 (DR96) | Evet. | az | 2 |
| Mum aralığından oynaklık ve sıçrama ayrımı | Tepe-dip farkından ikinci bir oynaklık ölçüsü verir, ani sıçramayı ayrı sayar. | 3 (D2097, ML17, DR146) | Evet. | az | 2 |
| Özellik eleme (adım adım ekleme) | İşe yaramayan özellikleri filtreden çıkarır. | 3 (DR36, C131, D335) | Evet; işlem sayısı azken kazancı küçük. | az | 2 |

## 3. Bekleyen (zaten listede, yeni sayılmadı)

- Göreceli güç (BTC'ye/endekse göre) — arşivin en çok tekrar eden "yapılmamış" fikri, ~50 kitap.
- Fonlama taşıma eğilimi; kalabalık taraf ve açık pozisyon-fiyat dörtlüsü.
- BTC-ETH ayrışması; çift işlemi.
- Kazanana ekleme.
- Olaya göre mum; baskın döngü; stablecoin arzı.
- Önceki tablolardan açık kalanlar: oynaklığa ve filtre güvenine göre boyut, hacim profili, önceki hafta/ay seviyeleri, komşu ayar raporu, eşleştirilmiş kıyas, bilanço takvimi.

## 4. Bilerek alınmayan

- **Donchian/Keltner/ATR kanal kırılımı:** ~25 kitapta var ama puanı 3'ü geçen kart yok; TF1 ve S1 aynı işi yapıyor.
- **Yavaş trend (6-12 aylık getiriye göre yön):** ~26 kitap, kanıtı güçlü; ama günlük EMA50 yön filtresi ve günlük TF1 ile büyük ölçüde bizde.
- **Mum kapanış konumu, piyasa genişliği:** v2 özellik paketinde var.
- **Bilanço sonrası sürüklenme, kazanç sürprizi:** bilanço verimiz yok.
- **Makro rejim skoru (dolar endeksi, VIX, faiz), vade farkı, BTC hakimiyeti:** verisi yok.
- **Emtia mevsimselliği, FOMC sonrası işlem:** yılda birkaç gözlem; 4 emtia ile sınanamaz.
- **TD sayımı, "akıllı para" bölgeleri, Gann, Elliott, Fibonacci zamanı, harmonik:** kanıt yok ya da tanım öznel.
- **Emir defteri ve tik fikirleri, opsiyon verisi:** veri yok.
- **Giriş-çıkış eşiğini ayırma (histerezis):** sürekli sinyalli sistemler için; bizim stoplu kollara uymuyor.

## 5. Öneri

İlk üç: (1) aşırı uçta dönüş kolu (2 günlük RSI, trend yönünde, 1g/4s); (2) kovalama + aralık içi konum + yeni zirvede short kapısını mevcut işlem kayıtlarında tek seferde ölçmek; (3) hisseler için açılış aralığı ve boşluk kolunu 1 dk veriyle geçmişte denemek.

## Fable görüşü

Kısaca: çoğu alınmaya değmez. Yılda aile başına birkaç yüz işlemle küçük bir filtrenin faydasını şanstan ayıramayız; her yeni kural da canlıya bir ay kala kırma riski getirir. Bu ay yalnız rapor ve güvenlik işleri alınmalı; yeni kol ve filtreler önce geçmiş veride ölçülmeli.

- **AL:** bu ay yap (motoru değiştirmeyen rapor/kontrol).
- **ÖNCE ÖLÇ:** geçmiş veride ya da mevcut kayıtlarda ölç; geçerse canlıdan sonra kâğıtta aç.
- **ALMA:** şimdilik bırak.

### Strateji

| Fikir | Hüküm | Neden |
|---|---|---|
| Aşırı uçta dönüş kolu (2 günlük RSI) | ÖNCE ÖLÇ | Elimizdeki tek gerçekten yeni tür ve long üretir; ama kanıtı eski ve masrafsız. Geçmişte masraflı test, geçerse canlıdan sonra kâğıtta. |
| Tasfiye dalgası sonrası dönüş | ALMA | Yılda bir avuç olay; kayma tam o anda en yüksek. Ölçecek örnek yok. |
| Tek büyük mumdan sonra dönüş ölçümü | ÖNCE ÖLÇ | Tek rapor; dönüş kolu testiyle aynı işte çıkar. |
| Kısa vadeli sıralı ters dönüş | ALMA | Sık al-sat, masraf kârı yer; bekleyen göreceli güç fikriyle de ters yönde. |
| Açılış aralığı kırılımı | ALMA | 1-5 dk veri hattı ve yeni kol ister; kısa vadede masraf ağır. Canlıdan sonra. |
| Açılış boşluğu | ALMA | 20 hisse, az olay; seans dışı kapısıyla çakışır, sürekli işlem gören sözleşmede boşluk tanımı da bulanık. |
| Saat bloğu karnesi | AL | Yalnız rapor, risksiz; kötü saat varsa görürüz. Özellik olarak eklemek ayrı karar. |
| Günlük aralık tüketimi | ÖNCE ÖLÇ | Kovalama filtresiyle aynı şeyi ölçer; ikisi tek ölçümde, biri seçilir. |
| Gece ve gündüz getirisi | ALMA | Seans dışı kapısı ve planlı küçülme bu riski zaten yönetiyor. |
| Kovalama filtresi | ÖNCE ÖLÇ | Ucuz; mevcut kayıtlarda bakılır. Kural değil, süzgece özellik olarak girmeli. |
| Aralık içi konum | ÖNCE ÖLÇ | Aynı ölçümde çıkar. Kırılım kollarını (TF1, B1) yanlışlıkla kesebilir, aile aile bakılmalı. |
| Yeni zirvede short kapısı | ÖNCE ÖLÇ | Short yığılmasına dokunur ama uzun_yon ile örtüşür ve F1'in zirvedeki short'larını öldürebilir. |
| Seviyenin kaç kez denendiği | ALMA | Seviye bulma koduna dokunur; faydası belirsiz, kırma riski var. |
| Short'a ayrı kapı | ALMA | uzun_yon aynı işi yapıyor; iki kapı üst üste short'u kurutur, veri daha da azalır. |
| Alıcı tarafın hacim payı | ALMA | Veri hattını değiştirip geçmişi yeniden çekmek gerekir; canlıdan sonra. |
| Hacim patlamasından ortalama fiyat | ALMA | Başlangıç mumunu seçmek serbest ayar; az işlemle kendimizi kandırırız. |
| Bağımsız teyit sayısı | ALMA | Süzgeç özellikleri zaten topluyor; aynı bilgiyi iki kez saymak olur. |
| Fiyat-osilatör uyumsuzluğu | ALMA | 175 kitap söylüyor, hiçbiri sayı vermiyor; kodlaması öznel. |
| Yükselişin yolu | ALMA | Sıralama stratejisi içindir; bizde öyle bir kol yok. |
| Tek günlük sıçrama cezası | ALMA | Aynı sebep. |
| Kırılım ilerlemiyorsa erken çık | ÖNCE ÖLÇ | "Başka çıkış olsaydı" aracı hazır; bir akşamlık ölçüm. |
| Aşırı büyük mumda kârı al | ÖNCE ÖLÇ | Aynı araçla; iz süren stop ve kısmi kapama zaten benzerini yapıyor olabilir. |
| İlk bacak kadar hedef | ALMA | Bacak tespiti öznel; hedef kuralımız var. |
| Toplu şok senaryosu ve tasfiye mesafesi | AL | Canlı öncesi güvenlik hesabı; motora dokunmaz, gerçek paradan önce bilinmeli. |
| Aylık zarar tavanı | AL | Birkaç satır; canlının ilk ayları için sigorta. Eşiği kullanıcı seçer. |
| Girişte limit emir | ALMA | Dolmayan emir ve emir yönetimi yeni hata kaynağı; önce canlıda gerçek kayma ölçülsün. |

### ML

| Fikir | Hüküm | Neden |
|---|---|---|
| Hacmi günün saatine göre normalleştir | ÖNCE ÖLÇ | Hisse/emtiada anlamlı; v2 hacim özelliğiyle yan yana denenir, iyiyse onun yerine geçer. |
| Seans dışı düz mumları gizle | AL | Önce kontrol: sorun varsa ATR'yi ve oynaklık tahminini sessizce bozuyor demektir; düzeltmesi küçük. |
| Benzerliği 4 saat/günlükte ölç | AL | Tek ölçüm; grup sınırlarımızın doğru kurulduğunu gösterir ya da çürütür. |
| Öncü gösterge sınaması | ALMA | Gece süzgeci ve ileri test işe yaramayan özelliği zaten eliyor; ikinci sınav fazlalık. |
| Trend mi, dönüş mü testi | ÖNCE ÖLÇ | Tek başına değil; dönüş kolu testinin ilk adımı olarak (hangi varlıkta dönüş var). |
| Canlı ile test gösterge eşitliği | AL | Canlı öncesi doğruluk kontrolü; fark varsa bütün geçmiş sonuçlar şüpheli olur. |
| Mum aralığından oynaklık | ALMA | Oynaklık tahmini (GJR-GARCH) zaten var; ikinci ölçü az şey ekler. |
| Özellik eleme | ALMA | Süzgeç zaten ağırlıkları küçültüyor; az veriyle seçim şansa döner. |

**Sıra:** (1) bu ay, canlıdan önce: düz mum ve gösterge eşitliği kontrolü, şok senaryosu, aylık tavan, saat karnesi, 4s/1g benzerlik ölçümü; (2) boş vakitte tek ölçüm turu: kovalama + aralık konumu + yeni zirve + aralık tüketimi ve iki çıkış kuralı; (3) dönüş kolunun geçmiş testi — geçerse canlıdan sonra kâğıtta. Gerisi beklesin.
