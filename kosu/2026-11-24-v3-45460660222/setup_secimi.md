# Kitaplarda en cok kullanilan setuplar

443 kuralın hepsi okundu; gruplama ve sayım elle yapıldı, bu yüzden sayılar ±1 oynayabilir. Her kural tek gruba yazıldı. Yalnız filtre, hedef, çıkış veya para yönetimi tarif eden kurallar setup sayılmadı. Tek kitapta geçen göstergeler (Alligator, %R, PMax, SSL, MIDAS, Elliott, harmonik) tabloya alınmadı.

## Grup sayimi

| kategori | setup | kural | kitap | ort netlik |
|---|---|---|---|---|
| formasyon | Yatay direnç/destek (aralık, dikdörtgen) kırılımı | 17 | 11 | 2.65 |
| formasyon | Üçgen kırılımı (yükselen/alçalan/simetrik) | 20 | 10 | 2.70 |
| mum | İç çubuk / harami | 13 | 9 | 3.15 |
| mum | Pin bar (çekiç / kayan yıldız) | 26 | 9 | 2.88 |
| formasyon | İkili/üçlü dip-tepe boyun kırılımı | 16 | 8 | 3.25 |
| mum | Yutan mum | 16 | 8 | 3.19 |
| formasyon | OBO / TOBO boyun kırılımı | 12 | 8 | 3.00 |
| formasyon | Bayrak / flama kırılımı | 16 | 8 | 2.88 |
| indikator | RSI 30/70 aşırı bölge | 14 | 7 | 3.36 |
| formasyon | Aralık/kanal sınırından dönüş | 8 | 7 | 2.75 |
| indikator | Hızlı/yavaş MA kesişimi | 7 | 6 | 3.86 |
| indikator | Fiyatın MA'yı kapanışla kesmesi | 7 | 5 | 2.86 |
| indikator | Bollinger bant dönüşü (ortalamaya dönüş) | 7 | 5 | 2.86 |
| indikator | VWAP kesişimi / VWAP tarafı | 15 | 5 | 2.67 |
| formasyon | Kırılım sonrası geri test (retest) | 9 | 5 | 2.67 |
| indikator | RSI/osilatör uyumsuzluğu | 9 | 5 | 2.44 |
| formasyon | Kama kırılımı | 7 | 5 | 2.29 |
| indikator | MACD sinyal kesişimi | 6 | 4 | 3.00 |
| indikator | Fibonacci geri çekilme girişi | 5 | 4 | 2.80 |
| formasyon | Trend çizgisi dönüş/kırılım | 5 | 4 | 2.60 |
| indikator | MA'ya geri çekilme | 4 | 4 | 2.25 |
| formasyon | Açılış boşluğu (gap) | 5 | 4 | 2.20 |
| indikator | Hacim klimaksı / hacim-fiyat uyumsuzluğu | 12 | 4 | 2.00 |
| mum | Sabah / akşam yıldızı | 7 | 3 | 4.00 |
| mum | Delici / kara bulut | 4 | 3 | 4.00 |
| mum | Ters çekiç / asılı adam | 4 | 3 | 3.75 |
| indikator | Stokastik (%K/%D, 20/80) | 5 | 3 | 3.60 |
| formasyon | Açılış aralığı kırılımı | 4 | 3 | 3.00 |
| formasyon | Sahte kırılım (boğa/ayı tuzağı) | 4 | 3 | 2.75 |
| indikator | RSI(2) kısa vadeli | 4 | 2 | 4.25 |
| mum | Üç asker / üç karga | 2 | 2 | 3.50 |
| indikator | Ichimoku (Kumo, Tenkan-Kijun) | 19 | 2 | 3.42 |
| formasyon | Kupa-kulp | 3 | 2 | 3.00 |
| mum | Doji | 5 | 2 | 2.60 |

Seçimi etkileyen sınır durumları:
- **Formasyon, 8 kitapta üçlü eşitlik:** İkili dip, OBO ve bayrak 8'er kitapta. Netlik sırasıyla ikili dip ve OBO girdi, bayrak 5. kaldı. Bu sonuç tek bir kuralın sınıflamasına bağlı: Al Brooks'un "çift dipli boğa bayrağı" kuralını ikili dibe yazdım. Bayrağa yazılırsa ikili dip 7 kitaba düşer ve bayrak girer.
- **İndikatör, 5 kitapta eşitlik:** Bollinger ve fiyat-MA kesişimi aynı netlikle (2.86) 3. ve 4. oldu; VWAP (2.67) ve uyumsuzluk (2.44) dışarıda kaldı. MACD 4 kitapta kaldı, seçilmedi.
- **Mum, 4. sıra:** Yıldız ve delici/kara bulut 3 kitap ve 4.00 netlikle eşit; kural sayısı fazla olduğu için yıldızı aldım.

## Secilen 12 setup

Ortak tanımlar:
- Bütün koşullar kapanmış mumda değerlendirilir. "Kapanışta giriş", sinyal mumunun kapanış fiyatıdır.
- **Pivot:** Pivot tepe, yüksek fiyatı solundaki 10 ve sağındaki 2 mumun hepsinden büyük olan mumdur (Young Ho Seo). Pivot dip aynasıdır. Bir pivot ancak kendisinden 2 mum sonra, o mum kapandığında kullanılabilir; daha erken kullanmak ileriye bakmaktır.
- **R:** Giriş ile stop arasındaki mesafe.
- **Zaman stopu:** Kitapta yoksa 48 mum.
- **Short:** Aksi yazılmadıkça long'un aynası.
- **Hedef:** Mum setuplarında kitapların çoğu hedef vermiyor. Sayı veren tek ortak kural 1:2 risk/ödül (Burns, Homma, Bhandari); 2R buradan geliyor.

### MUM_PINBAR
- **Giriş (long):** Alt gölge en az gövdenin 2 katı, üst gölge mum aralığının %10'undan küçük, kapanış aralığın üst yarısında. Mumun dibi son 10 mumun en düşüğü olmalı (öncesinde düşüş şartı; James'in 10 günlük dip koşulu). Pin bar kapanışında gir.
- **Stop:** Pin barın fitil ucunun hemen ötesi (long'da dibin altı).
- **Hedef:** 2R.
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok. Kitaplar "destek seviyesinde" diyor ama sayısal tanım vermiyor; 10 mumluk dip koşulu bunun kitaptaki tek sayısal karşılığı. Trend konusunda kitaplar ikiye bölünüyor (trend yönünde / düşüş sonrası dönüş), ortak MA filtresi yok.
- **Dayanak:** Homma, Burns, Karahan, James, Pring (Mum Çubukları), Burns-Matov, Wise, Bhandari, Profit King.

### MUM_IC_CUBUK
- **Giriş:** İç mumun en yükseği ana mumun en yükseğinin altında, en düşüğü ana mumun en düşüğünün üstünde. İç mum kapanınca ana mumun en yükseğine alış-stop, en düşüğüne satış-stop emri konur. İlk dolan işlem olur, diğeri iptal edilir. Emirler sonraki 2 mum geçerli (Hill).
- **Stop:** Ana mumun karşı ucu.
- **Hedef:** 2R.
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok. Teo trend yönünde devam, NCFM ve Wise trende karşı dönüş diyor; ortak filtre çıkmıyor.
- **Dayanak:** Graham, Hill, Burns, Homma, Brooks, Hunter, Teo, Wise, NCFM.

### MUM_YUTAN
- **Giriş (long):** Önceki mum düşüş mumu. Şimdiki mum yükseliş mumu ve gövdesi öncekinin gövdesini tamamen kapsıyor (açılış ≤ önceki kapanış, kapanış ≥ önceki açılış). Önceki mumun dibi son 5 mumun en düşüğü (James'in 5 günlük uç koşulu; "trend sonunda" şartının sayısal hali). Yutan mumun kapanışında gir.
- **Stop:** Yutan mumun dibinin hemen altı (Karahan).
- **Hedef:** 2R. Bu grupta dayanağı zayıf; kitapların çoğu hedef vermiyor.
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok (seviye şartı sayısal değil).
- **Dayanak:** Karahan, Price Action Kalıpları (16 s.), Burns, James, Homma, Bhandari, Wise, Christensen.

### MUM_YILDIZ
- **Giriş (sabah yıldızı, long):** Üç mum.
  1. Büyük düşüş mumu (kapanış açılışın en az %1.5 altında), dibi son 2 mumun en düşüğü.
  2. Küçük gövdeli mum (gövde en fazla %0.3), gövdesi 1. mumun kapanışının üstüne taşmıyor.
  3. Yükseliş mumu, kapanışı 1. mumun gövde ortasının üstünde.
  
  3. mumun kapanışında gir.
- **Stop:** Girişin %3 altı (James).
- **Hedef:** Girişin %9 üstü (James).
- **Zaman stopu:** 20 mum (James).
- **Filtre:** Yok.
- **Uyarı:** %1.5 / %0.3 / %3 / %9 değerleri James'in günlük hisse testinden. Kısa zaman diliminde bu eşiklerle sinyal çok az çıkar; ölçekleme kitaplarda yok, karar size ait. James akşam yıldızında farklı değer kullanıyor (%6 stop, %2 hedef); short için ayna yerine bunu da deneyebilirsiniz.
- **Dayanak:** James, Wise, NCFM.

### FOR_YATAY_KIRILIM
- **Giriş (long):** Direnç, birbirine en fazla %3 yakın en az 2 onaylı pivot tepedir; seviye bunların en yükseği. Mum bu seviyenin üstünde kapanınca gir.
- **Stop:** Kırılan seviyenin altı. Tampon için kitaplarda sayı yok; kırılım mumunun dibi daha aşağıdaysa o kullanılır (Norman).
- **Hedef:** Aralık yüksekliği (direnç eksi pivot tepeler arasındaki en düşük dip) kırılım seviyesine eklenir (Lambert).
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok. Hacim artışını 11 kitaptan 3'ü şart koşuyor (Pistolese, Graham, Mohanty) ve eşik vermiyor; çoğunluk olmadığı için eklenmedi.
- **Uyarı:** %3 toleransı Ankya'nın günlük grafikteki ikili dip değerinden alındı.
- **Dayanak:** Norman, Pistolese, Graham, Lambert, Seo, Mohanty (Hacim), Damir, Rudd, Burns, Teo, Hill.

### FOR_UCGEN
- **Giriş:**
  - Yükselen üçgen (long): En az 2 pivot tepe yaklaşık aynı seviyede (%3 içinde) ve aralarında en az 2 yükselen pivot dip. Yatay direncin üstünde kapanışta gir.
  - Alçalan üçgen (short): Aynası.
  - Simetrik üçgen: Son 2 pivot tepe düşüyor, son 2 pivot dip yükseliyor. Çizgiler bu pivotlardan geçirilip ileri uzatılır; hangi çizginin dışında kapanış olursa o yönde gir.
- **Stop:** Kırılımdan önceki son onaylı pivot dibin altı (short'ta pivot tepenin üstü).
- **Hedef:** Üçgenin en geniş yeri (ilk pivot tepe eksi ilk pivot dip) kırılım noktasından kırılım yönünde eklenir.
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok. Hacim (3 kitap) ve önceki trend (4 kitap) 10 kitapta çoğunluk değil.
- **Dayanak:** Trading Strategy Guides (Sniper), Salvon, Ankya, Forex GDP, Persic, Petruci, Trading Technicals, Swanson, Collins, Seo.

### FOR_IKILI_DIP
- **Giriş (long):** İki onaylı pivot dip; ikincisi birincinin %3 yakınında, aralarında 5–25 mum (Alfa Crypto). Boyun, iki dip arasındaki en yüksek fiyat. Boynun üstünde kapanışta gir.
- **Stop:** İki dibin en düşüğünün altı.
- **Hedef:** Boyun eksi dip mesafesi boyna eklenir (Salvon). Alternatif: Alfa Crypto'nun 1.4R'si (tek kitap, 4 kural).
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok. Önceki düşüş trendi 3 kitapta, hacim 3 kitapta, RSI<30 ve EMA200 yalnız Alfa Crypto'da geçiyor.
- **Dayanak:** Ankya, Alfa Crypto, Pistolese, Salvon, Petruci, Trading Technicals, Khan, Brooks.

### FOR_OBO
- **Giriş (OBO, short):** Üç onaylı pivot tepe; ortadaki (baş) ikisinden yüksek, omuzlar arası fark en fazla %3. Boyun, tepeler arasındaki iki pivot dipten geçen ve ileri uzatılan çizgi. Boynun altında kapanışta gir. TOBO long aynasıdır.
- **Stop:** Baş seviyesinin ötesi (Salvon, Alfa Crypto). Alternatif: boyun + 1 ATR (Alfa Crypto).
- **Hedef:** Baş–boyun mesafesi kırılım noktasından eklenir (Khan, Salvon).
- **Zaman stopu:** 48 mum.
- **Filtre:** Önceki trend şartı var; 8 kitabın 6'sı istiyor. Sayısal hali Salvon'dan: sol omuzdan önceki hareket, baş–boyun mesafesinin en az 2 katı olmalı.
- **Uyarı:** Omuz eşitliği için kitaplarda sayı yok; %3, Ankya'nın ikili dip toleransından alındı.
- **Dayanak:** Ankya, Alfa Crypto, Pistolese, Salvon, Petruci, Khan, Trading Technicals, Tyler Aaron.

### IND_RSI_3070
- **Giriş (long):** RSI(14) kapanışta 30'un altına indiği ilk mumda gir. Short: 70'in üstüne çıktığı ilk mum. Yedi kitabın beşi "30 altındayken al" diyor; yalnız Pring ve Pansheriya 30'u geri yukarı kesmeyi bekliyor.
- **Stop:** Son dibin altı (Graham, Pansheriya). Pencere kitaplarda yok; giriş mumu dahil son 10 mumun en düşüğü benim varsayımım.
- **Hedef / çıkış:** RSI 70'in üstüne çıkınca kapat (short'ta 30'un altı). Alternatif: RSI 50 (Pring, SmartMoney).
- **Zaman stopu:** 48 mum.
- **Filtre:** Long yalnız SMA50 > SMA200 iken, short yalnız SMA50 < SMA200 iken. Yedi kitabın dördü trend yönü şartı koşuyor (Pring, SmartMoney, Khan, Aaron); sayısal tanım SmartMoney'den.
- **Dayanak:** Pring (Momentum), Pansheriya, Tyler Aaron, Graham, Dagade, Khan, SmartMoney.

### IND_MA_KESISIM
- **Giriş:** SMA50, SMA200'ü kapanışta yukarı kesince long, aşağı kesince short. En sık geçen çift 50/200 (Bunjira, Khan); diğerleri EMA 4/9 (Dagade), VWMA 10/21 (Al ve Sat) ve 10/50 (Pansheriya).
- **Stop:** Yok. Hiçbir kitap seviye vermiyor.
- **Hedef / çıkış:** Ters kesişimde kapat ve ters yöne geç.
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok.
- **Uyarı:** 48 mumluk zaman stopu 50/200 gibi yavaş bir trend takip kuralını erken keser; kitaplardaki çıkış yalnız ters kesişim. Motor stop zorunlu tutuyorsa, o stop kitaplardan gelmeyecek.
- **Dayanak:** Dagade, Bunjira, Khan, Pistolese, Seo, Al ve Sat Sinyalleri.

### IND_BOLL_DONUS
- **Giriş (long):** Bollinger (20, 2). Mumun en düşüğü alt banda değer veya altına inerse o mumun kapanışında gir. Short: en yüksek üst banda değerse. Sapma bütün kitaplarda 2; periyot kitaplarda 5, 12 ve 20 olarak dağınık, 20'yi seçtim.
- **Stop:** Alt bandın altı (Bunjira). Sayı yok; dokunan mumun dibini kullanıyorum.
- **Hedef:** Orta bant (20 SMA), her mumda güncel değerle (Bunjira, Dagade). Alternatif: karşı bant (Harnett).
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok.
- **Not:** SmartMoney ve Heitkoetter bandı ters yönde, kırılım teyidi olarak kullanıyor; bu gruba alınmadılar.
- **Dayanak:** Bunjira, Dagade, Harnett, Seo, Pansheriya.

### IND_FIYAT_MA
- **Giriş:** Kapanış SMA50'nin altından üstüne geçtiği mumda long; üstünden altına geçtiği mumda short. 50, en sık geçen periyot (Johnson'da iki kural); diğerleri 500 EMA (Al ve Sat) ve 8/9 (Kewltech).
- **Stop / çıkış:** Kapanış MA'nın karşı tarafına geçince kapat (Pistolese, Johnson). Ayrı sabit stop yok.
- **Hedef:** Yok.
- **Zaman stopu:** 48 mum.
- **Filtre:** Yok. Hacim artışı 5 kitaptan 2'sinde (Pistolese, Johnson) eşiksiz geçiyor.
- **Dayanak:** Johnson, Pistolese, Graham, Kewltech, Al ve Sat Sinyalleri.