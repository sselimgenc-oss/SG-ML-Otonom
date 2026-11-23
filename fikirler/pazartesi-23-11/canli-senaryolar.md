# Canlı işlem senaryoları — 2000 $ ile ilk 1 hafta, 2 hafta, 1 ay

Tarih: 23.11.2026. Bu belge öneri içermez; yalnızca "ne olabilir"i anlatır.
Rakamlar bir tahmindir, söz değildir. Dayandığı veri çok küçüktür (aşağıda "Rakamlar nereden geldi").

## 1. Kullanılan ayarlar (canlı = kağıt)

| Ayar | Değer | 2000 $ için anlamı |
|---|---|---|
| İşlem başına risk | %1 | Bir işlem zararla kapanırsa yaklaşık 20 $ gider |
| Açık toplam risk | en çok %24 | Aynı anda açık işlemlerin toplam riski en çok ~480 $ |
| Aynı yönde işlem | en çok 6 | |
| Benzer coin grubu | yön başına en çok 4 | |
| Zarar freni | 5 zarar üst üste veya günde −%4 | Risk yarıya iner (işlem başı ~10 $) |
| Toplam pozisyon büyüklüğü | kasanın en çok 3 katı | En çok ~6000 $ |
| Günlük zarar sınırı | %8 | Gün içinde ~160 $ zarar → o gün yeni işlem açılmaz |
| Sermaye kilidi | sermayenin %85'i | Kasa 1700 $'a inerse yeni giriş durur; siz açana kadar kapalı kalır. Açık işlemler devam eder |
| Araçlar | 43 | 19 kripto (7/24), 21 ABD hissesi, 4 emtia (15.09.2026'dan beri yalnız hafta içi) |
| Kollar | 32 kol + yapay zekâ filtresi | Canlıda model paketi olmayan kol hiç işlem açmaz |

## 2. Rakamlar nereden geldi

- Kağıt hesapta 5 günde 55 işlem açıldı (günde ~10), 47'si kapandı. Kapananların toplamı 1000 $'lık kağıt kasada +34 $; açık 8 işlem o anda −13 $'daydı.
- İşlem başına ortalama: +0,07 R (R = bir işlemde göze alınan risk; canlıda 20 $). Kazanan oranı %47. Tek işlemin oynaklığı ~1,3 R.
- 47 işlem çok azdır: ortalamanın belirsizliği ±0,19 R. Yani bu veri "sistem kazandırıyor" ile "sistem kazandırmıyor"u birbirinden ayıramaz.
- Canlıda maliyet kağıttan kötüdür. İşlem başına 0,05–0,1 R ek kayma varsayıldı (ortası 0,075 R). Bu, kağıtta görülen +0,07 R'yi neredeyse tam olarak siler.
- Kıyas: eski geriye dönük test (tek kol, 10 kripto, 4695 işlem, 01.05.2026 öncesi) işlem başına −0,03 R veriyor. "Sıfır civarı" varsayımıyla uyumlu.
- Yöntem: kağıt işlemleri rastgele yeniden çekilerek 20.000 kez 1 hafta / 2 hafta / 1 ay oynatıldı. Günde ~10 işlem, zarar freni, günlük %8 sınırı ve 1700 $ kilidi hesaba katıldı. Kilit bir kez kapanırsa dönem sonuna kadar kapalı kaldığı varsayıldı.

Üç varsayım:

- **A — Kağıttaki gibi:** işlem başına +0,07 R, ek kayma yok.
- **B — Sıfır avantaj:** masraflardan sonra işlem başına 0 R. Kağıt sonucu + canlı kayması da buraya denk geliyor.
- **C — Hafif eksi:** işlem başına −0,10 R.

## 3. Para tablosu (dönem sonu kasa, $)

P10 = 10 denemenin 1'i bundan kötü. P50 = orta. P90 = 10 denemenin 1'i bundan iyi.

| Dönem | Varsayım | P10 | P50 | P90 | Kilit (1700 $) olasılığı |
|---|---|---|---|---|---|
| 1 hafta | A | 1797 | 2093 | 2459 | %6 |
| 1 hafta | B | 1698 | 1993 | 2331 | %12 |
| 1 hafta | C | 1690 | 1869 | 2191 | %26 |
| 2 hafta | A | 1697 | 2191 | 2748 | %14 |
| 2 hafta | B | 1690 | 1982 | 2488 | %28 |
| 2 hafta | C | 1685 | 1699 | 2185 | %56 |
| 1 ay | A | 1693 | 2416 | 3406 | %22 |
| 1 ay | B | 1687 | 1844 | 2752 | %47 |
| 1 ay | C | 1683 | 1694 | 2021 | %82 |

Okuma notları:

- Alt uçtaki rakamların 1680–1700 $'da yığılması kilit yüzündendir: kasa 1700'e inince yeni giriş durur, kayıp orada kesilir.
- Günde 10 işlem, ayda ~300 işlem demektir. Avantaj sıfır olsa bile bu kadar işlemin doğal dalgası ±400–500 $'dır. Bu yüzden B varsayımında bile ay içinde kilide değme ihtimali yarıya yakındır.
- Dönem içinde zirveden en derin düşüş (bir ayda, B): tipik ~410 $, 10'da 1 ihtimalle ~640 $ (zirve 2000'in üstündeyse).
- Günlük %8 sınırına en az bir kez takılma: haftada ~%5, ayda ~%14 (B).
- Canlıda işlem sayısı günde 10'dan az olursa (bkz. teknik bölüm) hem kazanç hem kayıp dalgası daralır, her şey daha yavaş ilerler.

## 4. Senaryolar

Olasılıklar kabadır: A, B, C varsayımlarına eşit ağırlık verilerek hesaplandı. Parantez içinde A / B / C ayrı ayrı.

### 4.1 İlk 1 hafta

| Senaryo | Kasa | Olasılık |
|---|---|---|
| İYİ | 2100 $ ve üstü (çoğunlukla 2100–2450) | ~%33 (49 / 33 / 17) |
| ORTA | 1900–2100 $ | ~%30 |
| KÖTÜ | 1900 $ ve altı, veya kilit (1680–1700) | ~%37 (21 / 34 / 55) |

**İYİ — teknik:** 50–70 işlem açılır. Telegram'a açılış/kapanış mesajları düzenli gelir. Zarar freni birkaç kez devreye girip çıkar, günlük sınır hiç dolmaz. Borsadaki zarar-kes emirleri yerinde durur. Bir haftalık kazanç, sistemin iyi olduğunu kanıtlamaz; şansla da aynı sonuç çıkar.

**ORTA — teknik:** Kasa 2000 $ çevresinde gidip gelir. Bir-iki gün −60…−100 $ ile, bir-iki gün aynı büyüklükte artıyla kapanır. Fren birkaç kez riski yarıya indirir. Komisyon ve fonlama haftada ~100 $ civarı tutar (kaymayla ~200 $); kasa yerinde sayıyorsa asıl gideren budur.

**KÖTÜ — teknik:** Arka arkaya zararlar gelir, fren neredeyse sürekli açık kalır (işlem başı ~10 $). Bir gün −160 $ ile günlük sınır dolar, o gün yeni işlem açılmaz. Kasa 1700 $'a değerse kilit kapanır: yeni giriş durur, açık işlemler kendi zarar-kes/hedefleriyle kapanana kadar sürer, Telegram'a uyarı düşer. Kilidi yalnız siz açabilirsiniz.

### 4.2 İlk 2 hafta

| Senaryo | Kasa | Olasılık |
|---|---|---|
| İYİ | 2150 $ ve üstü (çoğunlukla 2150–2750) | ~%33 (54 / 33 / 12) |
| ORTA | 1850–2150 $ | ~%26 |
| KÖTÜ | 1850 $ ve altı, veya kilit | ~%41 (19 / 37 / 66) |

**İYİ — teknik:** 100–140 işlem. Arada 150–300 $'lık geri çekilmeler yine görülür; iyi senaryo düz bir çizgi değildir. Risk kasayla birlikte büyür (2400 $'da işlem başı ~24 $).

**ORTA — teknik:** İlk kez bir hafta sonu ve bir hafta içi tam yaşanmıştır: emtialar hafta sonu kapalı kalır, hisseler seans dışında boşlukla açılabilir. Sistem en az bir kez yeniden başlamış, açık işlemleri borsadan okuyup kaldığı yerden devam etmiştir.

**KÖTÜ — teknik:** Kilit bu dönemde çok daha olasıdır (B'de %28, C'de %56). Kilit kapandıktan sonra sistem çalışır ama işlem açmaz; ekranda ve Telegram'da "kilitli" görünür. Kilit kapanırken açık işlemler varsa kasa 1700'ün biraz altına (1600–1700) inebilir.

### 4.3 İlk 1 ay

| Senaryo | Kasa | Olasılık |
|---|---|---|
| İYİ | 2200 $ ve üstü (B'de 2750'ye, A'da 3400'e kadar) | ~%34 (63 / 32 / 6) |
| ORTA | 1800–2200 $ | ~%14 |
| KÖTÜ | 1800 $ ve altı, veya kilit (1680–1700) | ~%52 (23 / 49 / 84) |

**İYİ — teknik:** ~300 işlem. Yolda 400 $ civarı bir geri çekilme normaldir. Bu kadar işlemle canlı sonuç kağıtla ilk kez anlamlı biçimde kıyaslanabilir hale gelir.

**ORTA — teknik:** Bir ay sonunda kasanın 2000 $ çevresinde kalması en az görülen sonuçtur: ya yukarı kaçar ya kilide iner. Ortada kalındıysa işlem sayısı beklenenden az olmuş olabilir.

**KÖTÜ — teknik:** En sık biçimi kilittir. Kayıp ~300–320 $'da durur (−%15…−%16). Kilit açılmadıkça sistem bekler. Kilidi açıp devam etmek ayrı bir karardır; açılırsa aynı olasılıklar yeni kasa üzerinden yeniden başlar.

## 5. Canlıya özgü teknik durumlar

- **Başlangıç adımı (sermaye tanımı / K2):** Canlı ilk açılışta sermayeyi (2000 $) kaydeder; %85 kilidi bu rakama göre hesaplanır. Bu adım tamamlanmadan giriş açılmaz. İlk saatlerde "hiç işlem yok" görülmesi bundan olabilir.
- **Yapay zekâ filtresi kapalı-güvenli çalışır:** Canlıda model paketi olmayan veya paketi yüklenemeyen kol hiç işlem açmaz (kağıtta açıyordu). Sonuç: canlıda işlem sayısı kağıttan az çıkabilir; bazı kollar hiç görünmeyebilir.
- **Çıkış biçimleri farklı:** Başa-baş'a çekme ve kısmi kâr alma canlıda henüz yok ("faz 2"). Canlıda işlem ya zarar-kes'te ya hedefte/izleyen stopta kapanır. Kağıtta küçük kârla veya sıfırda kapanan bazı işlemler canlıda tam zarar ya da tam kâr olarak biter; tek tek sonuçlar kağıtla birebir örtüşmez, dalga biraz büyür.
- **Hisse/emtia reddi:** Türkiye'de yerleşik hesapta borsa ABD hissesi ve emtia sözleşmelerini reddedebilir. Olursa 43 aracın 25'i devre dışı kalır, yalnız 19 kripto işlem görür: işlem sayısı düşer, işlemler birbirine daha çok benzer (kripto birlikte hareket eder), Telegram/kayıtlarda ret mesajları birikir.
- **Hafta sonu emtia:** 4 emtia yalnız hafta içi işlem görür. Cuma'dan açık kalan emtia işlemi Pazartesi boşlukla açılabilir; hafta sonu fiyatı gelmez, ekranda "fiyat bekleniyor" yazar.
- **Borsadaki zarar-kes emirleri:** Zarar-kes borsanın kendisinde durur; sistem kapalıyken de çalışır. Hızlı piyasada emir daha kötü fiyattan dolabilir (20 $ yerine 22–30 $ zarar).
- **Hisselerde boşluk:** Hisse fiyatı seans dışında/haber üzerine zarar-kes'in ötesine sıçrayabilir; o işlemde zarar 1 R yerine 2–5 R (40–100 $) olabilir.
- **API / yasak / yeniden başlama:** Borsa bağlantısı kopabilir, istek sınırı aşılırsa geçici yasak gelebilir. Sistem yeniden başlayınca açık işlemleri ve kaçırdığı kapanışları borsadan okuyup defterini günceller; arada kaçan sinyaller sonradan açılmaz. Bu sürede yeni giriş olmaz, açık işlemler borsadaki emirlerle korunur.
- **Telegram:** Açılış, kapanış, fren, günlük sınır, kilit ve hata mesajları gelir. Mesaj gelmemesi işlemin olmadığı anlamına gelmeyebilir (Telegram gecikmesi/kesintisi); doğrusu borsa hesabı ve paneldir.
- **Maliyet:** Komisyon + fonlama kağıtta işlem başına ~0,08 R idi; canlıda kayma eklenir. Ayda ~300 işlemde toplam masraf kabaca 450–900 $ eder (kazanan işlemlerden karşılanır veya kasadan gider).

## 6. Uç olaylar (seyrek ama mümkün)

| Olay | Ne olur | Para etkisi |
|---|---|---|
| Ani çöküş / sıçrama, aynı yönde 6 işlem açıkken | Hepsi birlikte zarar-kes olur, kayma büyür | −120…−200 $ tek seferde; günlük sınır ve belki kilit aynı anda dolar |
| Tüm açık riskin aynı anda vurulması | Sınırın izin verdiği en kötü durum | ~−480 $ (%24) + kayma; kasa bir anda 1500 $ civarına iner, kilit kapanır |
| Hisse/emtiada büyük boşluk (bilanço, hafta sonu haberi) | Zarar-kes atlanır | İşlem başına 40–100 $, uçta daha fazla |
| Borsa arızası / bakım | Emir verilemez, işlem kapatılamaz | Belirsiz; borsadaki stoplar da gecikebilir |
| Sistem uzun süre kapalı kalır | Yeni giriş yok; açık işlemler borsadaki emirlerle kalır | Genelde sınırlı; izleyen stop güncellenmez |
| API anahtarı iptali / hesap kısıtı | Sistem işlem açamaz, kapatamaz | Açık işlemler borsadaki emirlerle biter |
| Fonlama oranı sıçraması | Açık işlemi taşımak pahalanır | İşlem başına birkaç dolar |
| Borsa veya sabit coin (USDT) sorunu | Kasa borsada durduğu için kasanın tamamı etkilenebilir | Hesaptaki sınırların hiçbiri bunu kapsamaz |
| Olağanüstü iyi seri | Arka arkaya büyük kazançlar | A varsayımında ayda 3400 $ üstü: ~10'da 1 |

## 7. Bu belgenin sınırları

- 47 kapanmış kağıt işlem, 5 gün, tek bir piyasa havası. Gerçek dağılım daha geniş olabilir.
- Canlı çıkış biçimleri kağıttan farklı olduğu için işlem başı sonuçlar birebir taşınmaz.
- Hisse/emtia reddi ve model paketi eksikleri işlem sayısını değiştirir; tablo günde ~10 işlem varsayar.
- Geriye dönük testin 01.05.2026 sonrası (ayrılmış dönem) hiç okunmadı.
