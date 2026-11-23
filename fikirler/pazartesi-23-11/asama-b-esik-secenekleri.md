# Aşama B — Eşik Seçenekleri (karar için)

Tarih: 23 Kasım 2026 · Durum: yalnız analiz, kod yazılmadı. Eşikler **test başlamadan önce kilitlenecek**; seçim sizde.

## Önce kısa özet

Dört madde için önerim:

| Madde | Önerim | Tek cümle gerekçe |
|---|---|---|
| 1. Aynı yön sınırı | **%6** (aynı yönde en çok 6 pozisyon) | Kapanmış hiçbir kârlı işlemi kesmiyor; 9 short'luk yığılmayı 6'da durduruyor. |
| 2. "Tek bahis" sınırı | **K = 4** (birbirine bağlı en çok 4 pozisyon, yön başına) | Kağıtta +23 $ kazandırırdı; geri testte düşüşü biraz azaltıyor, kârı az kesiyor. |
| 3. Kayıp freni | **5 kayıp üst üste** veya günlük limitin yarısı (**%4**) → risk yarıya | Veri frenin para kazandırmadığını gösteriyor; bu bir sigorta, o yüzden en gevşeğini öneriyorum. |
| 4. Toplam büyüklük tavanı | **3 kat** (tüm pozisyonların toplamı kasanın 3 katını geçmez) | Kağıt zirvesi 3,6 kattı; 3 kat tam o zirveyi keser, normal günlere dokunmaz. |

**En önemli dürüst not:** Elimizdeki veri bu kararları *kanıtlamaya* yetmiyor. 55 kağıt işlem çok az; geri test ise botun yalnız küçük bir parçasını kapsıyor. Aşağıdaki sayılar "yön gösterir", "kesin sonuç" değildir.

## Hangi veriyle baktım

**Kağıt işlemler (55 işlem, 18–23 Kasım):** 47'si kapanmış, 8'i dosya anında açıktı. 55 işlemin 49'u short (kapananların 41'i). Dosya 23 Kasım 10:34'te (TSİ) üretilmiş; o ana kadar kapanan işlemlerin toplamı **+34 $** idi (short'lar +50 $, long'lar −15 $).

Buradaki sorun şu: asıl büyük kayıp **bu dosyadan sonra** yaşandı. Aynı gün akşama doğru kasa günü 1.055 $'dan 962 $'a (yaklaşık **−%8,8**) indirdi. O işlemlerin çoğu 55'lik listede yok. Yani "55 işlemde ne olurdu" sütunu, tam da korunmak istediğimiz kötü saatleri **görmüyor**.

**Geri test:** Tek bir kol (trend geri çekilmesi, 1 saatlik), 10 kripto para, 4.695 işlem, Şubat 2021 – Nisan 2026. Ayrıca son 6 ayı (Kasım 2025 – Nisan 2026, 455 işlem) ayrı gösterdim. Kilitli dönem (1 Mayıs – 1 Kasım 2026) hiç okunmadı.

Geri testin sınırları:
- Bot 32 kol ve 43 araçla çalışıyor; bu test 1 kol ve 10 kripto. Hisse, altın, petrol yok.
- Bu kol tüm dönemde zarar ediyor (−124 R). Zarar eden bir seride "işlem engellemek" kendiliğinden iyi görünür. Bu yüzden son 6 ayı (kârlı dönem, +34 R) da gösterdim: orada engellemenin **bedeli** görülüyor.
- "Düşüş" yalnız kapanan işlemlerden hesaplandı; açık pozisyonların anlık zararı dahil değil.
- `arm_series` dosyaları her kol için yalnız **günlük toplam** tutuyor; hangi coin, hangi yön bilgisi yok. O yüzden yön, bağlılık ve büyüklük maddeleri orada sınanamadı.

**Birim:** "R" = bir işlemde riske edilen para = kasanın %1'i. "−10 R" kabaca "kasanın %10'u" demek.

---

## 1. Aynı yön sınırı

**Ne yapar:** Aynı yöndeki (hepsi short ya da hepsi long) açık pozisyonların toplam riskini sınırlar. Şu an %16 (16 pozisyon). Kağıtta en çok 9 pozisyon aynı anda açıktı, 9'u da short.

| Seçenek | Ne demek (sade) | 55 işlemde ne olurdu | Geri testte ne olurdu | Öneri |
|---|---|---|---|---|
| **%10** (gevşek) | Aynı yönde en çok 10 pozisyon | Hiçbir işlem engellenmezdi (zirve 9'du). Etki: 0 $ | Değişiklik yok (bu testte aynı yönde en çok 8 açılabiliyordu) | |
| **%8** (orta) | Aynı yönde en çok 8 pozisyon | 1 işlem engellenirdi (#79 NVDA short; dosyada açıktı, sonucu bilinmiyor). Kapananlara etki: 0 $ | Değişiklik yok (aynı sebep) | |
| **%6** (sıkı) | Aynı yönde en çok 6 pozisyon | 3 işlem engellenirdi (#39 BNB, #40 HYPE, #79 NVDA). Üçü de dosyada açıktı; ikisi şu an zararda (−5,6 $ ve −8,9 $). Kapanan kârlı hiçbir işlem kesilmezdi | Tüm dönem: 67 işlem engellenir (%1,4); net −124 R → −109 R; en büyük düşüş 351 R → 345 R. Son 6 ay: 13 işlem engellenir; net +33,9 R → +35,5 R; düşüş aynı (30,5 R) | **Önerim** |

Daha sıkısına da baktım: %5 olsaydı kağıtta 9 işlem engellenir, bunların kapanan 5'i toplam **+44 $ kâr** götürürdü. O yüzden %5 ve altını önermiyorum.

**Yön karnesi:** Bu bir sınır değil, bir göstergedir; eşik gerektirmez. Önerim panelde şunu göstermesi: açık long/short sayısı, son 7 günde açılan işlemlerin yön dağılımı, yön başına kâr/zarar. Bugünkü değerler: 55 işlemin 49'u short.

---

## 2. Bağlılık ("tek bahis") sınırı

**Ne yapar:** Birlikte hareket eden araçlar ayrı ayrı sayılmaz, tek bahis sayılır. BTC, ETH ve SOL'da aynı anda short olmak aslında üç kere aynı bahsi oynamaktır.

**Önerdiğim yöntem:**
1. Her araç çifti için son **30 günün 1 saatlik** getirilerine bakılır.
2. Bağlılık **0,7 veya üstüyse** bu ikisi "aynı bahis" sayılır.
3. Yeni bir işlem açılmadan önce: aynı yönde açık olan ve bu adayla bağlı pozisyonlar sayılır. Sayı **K**'ye ulaşmışsa yeni işlem açılmaz.
4. Geçmiş fiyatı olmayan araçlar (hisseler, altın, petrol, bazı coinler) için mevcut sabit gruplar kullanılır; coinler "kripto" grubunda sayılır.

**Ölçtüğüm bağlılık (10 kripto):**
- Uzun dönemde çiftlerin ortancası 0,71; çift-günlerin yaklaşık yarısı (%52) 0,7'nin üstünde.
- Son bir yılda ortanca 0,78; çift-günlerin %69'u 0,7'nin üstünde.
- 1–15 Kasım 2026'da 45 çiftin 36'sı 0,7'nin üstünde (ortanca 0,82). BTC–ETH 0,93.
- Tek ayrık duran **TRX** (diğerleriyle 0,30–0,43). Yani yöntem TRX'i haklı olarak ayrı bahis sayar; sabit grup bunu göremez.

| Seçenek | Ne demek (sade) | 55 işlemde ne olurdu | Geri testte ne olurdu | Öneri |
|---|---|---|---|---|
| **K = 5** (gevşek) | Birbirine bağlı en çok 5 pozisyon, yön başına | 6 işlem engellenirdi (2 kârlı, 4 zararlı). Etki: **+26,5 $** | Tüm dönem: 75 işlem engellenir; net −124 R → −117 R; düşüş 351 → 347 R. Son 6 ay: 20 işlem; net +33,9 → +37,2 R; düşüş 30,5 → 31,1 R | |
| **K = 4** (orta) | En çok 4 | 8 işlem engellenirdi (kapanan 7'si: 3 kârlı, 4 zararlı). Etki: **+23,2 $**; ayrıca şu an zararda olan #40 HYPE açılmazdı | Tüm dönem: 180 işlem; net −124 → −115 R; düşüş 351 → 330 R. Son 6 ay: 44 işlem; net +33,9 → +27,7 R; düşüş 30,5 → 28,7 R | **Önerim** |
| **K = 3** (sıkı) | En çok 3 | 12 işlem engellenirdi (kapanan 10'u: 6 kârlı, 4 zararlı). Etki: **−12,2 $** | Tüm dönem: 407 işlem; net −124 → −115 R; düşüş 351 → 325 R. Son 6 ay: 81 işlem; net +33,9 → **+16,0 R**; düşüş 30,5 → 24,5 R; en kötü hafta −12,1 → −9,2 R | |

K = 2'ye de baktım: kağıtta 20 işlem engellenir ve **−61 $** götürürdü; geri testin son 6 ayında kârın beşte dördü giderdi. Önermiyorum.

**Not:** Kağıt haftası için fiyat verisi yok (elimizdeki mumlar 15 Kasım'da bitiyor) ve hisselerin geçmişi hiç yok. Bu yüzden 55 işlemde sabit gruplarla saydım: tüm coinler tek grup, teknoloji hisseleri tek grup, diğer hisseler, metal, enerji. Geri test sütunu ise gerçek 30 günlük ölçümle yapıldı.

**Neden K = 4:** 23 Kasım sabahı 9 short'un 6'sı kriptoydu; K = 4 bunu 4'te keserdi. K = 3 düşüşü daha çok azaltıyor ama kârlı dönemde kârın yarısını alıyor.

---

## 3. Kayıp freni

**Ne yapar:** Üst üste N işlem zararla kapanırsa **veya** o günün zararı günlük limitin yarısına (%8'in yarısı = **%4**) ulaşırsa, yeni işlemler yarım riskle (%0,5) açılır.

**Frenin kalkması (bunu da kilitlemek gerekir, önerim):** Üst üste kayıp freni, ilk kârlı kapanışta kalkar. Günlük fren, ertesi gün (UTC gün başı) kalkar.

| Seçenek | Ne demek (sade) | 55 işlemde ne olurdu | Geri testte ne olurdu | Öneri |
|---|---|---|---|---|
| **N = 5** (gevşek) | 5 kayıp üst üste → yarım risk | Hiç devreye girmezdi (47 kapanışta 5'li seri yok). Etki: 0 $ | Tüm dönem: işlemlerin %25'i yarım açılır; net −124 → −162 R (**daha kötü**); düşüş 351 → 339 R. Son 6 ay: 69 işlem yarım; net +33,9 → +28,2 R; düşüş aynı | **Önerim** |
| **N = 4** (orta) | 4 kayıp üst üste → yarım risk | 4 işlem yarım açılırdı; kapanan 3'ü de **kârlıydı**. Etki: **−7,4 $** | Tüm dönem: %32'si yarım; net −124 → −161 R; düşüş 351 → 334 R. Son 6 ay: 106 işlem; net +28,3 R; en kötü hafta −12,1 → −10,6 R | |
| **N = 3** (sıkı) | 3 kayıp üst üste → yarım risk | 6 işlem yarım açılırdı (4 kârlı, 2 zararlı). Etki: **−3,0 $** | Tüm dönem: %41'i yarım; net −124 → −164 R; düşüş 351 → 319 R. Son 6 ay: 146 işlem; net +30,5 R; en kötü hafta −12,1 → −9,3 R | |

**Günlük yarı-limit (%4) kısmı:** 55 işlemlik dosyada hiç tetiklenmedi. Ama 23 Kasım'ın devamında gün −%8,8'e indi; fren yaklaşık −42 $'da devreye girer ve sonraki işlemleri yarım açardı. Ne kadar kurtarırdı, hesaplayamıyorum: o işlemler dosyada yok. Geri testte tek başına çok seyrek tetikleniyor (4.695 işlemde 61), etkisi küçük.

**Dürüst sonuç:** Geri testte fren **para kazandırmıyor, kaybettiriyor**. Sebebi şu: kayıp serisinden sonra açılan işlemler ortalamadan kötü değil (ortalama +0,05 R; genel ortalama −0,03 R). Yani "kaybediyorsam devamı da kötü gelir" varsayımı bu veride doğrulanmıyor. Fren, düşüşü yalnız birkaç puan azaltıyor.

Yine de fren onaylandı ve mantıklı bir sigorta: 23 Kasım gibi "her şey birlikte kaybediyor" günlerinde hasarı sınırlar. Bu yüzden **en az bedelli** olanı, N = 5'i öneriyorum. Kağıt botu günde 10'dan fazla işlem açıyor; 5'li seri kötü günde yine hızlı dolar.

---

## 4. Toplam büyüklük (kaldıraç) tavanı

**Ne yapar:** Açık tüm pozisyonların toplam büyüklüğü, kasanın belli bir katını geçemez. Geçecekse yeni işlem açılmaz.

**Kağıtta gerçekte ne oldu:**
- **Zirve: kasanın yaklaşık 3,6 katı** (21 Kasım 01:30, 6 pozisyon, yaklaşık 3.850 $ büyüklük / 1.080 $ kasa).
- 9 short'un açık olduğu an (23 Kasım 07:00): yaklaşık **2,9 kat** (3.020 $ / 1.040 $). "Cüzdanın %92'si kullanımda" bununla uyumlu.
- Olağan saatlerde 2–3 kat arasında gezdi.
- Büyük pozisyonlar hisselerdi: stopları dar olduğu için tek işlem kasanın 1 katına kadar çıkıyor (AAPL, NFLX, JPM, GOOGL her biri 1.050–1.250 $).

Bu büyüklükleri komisyonlardan geri hesapladım; kasayı yalnız kapanan işlemlerle güncelledim. Birkaç puanlık sapma olabilir.

| Seçenek | Ne demek (sade) | 55 işlemde ne olurdu | Geri testte ne olurdu | Öneri |
|---|---|---|---|---|
| **5 kat** (gevşek) | Toplam büyüklük kasanın 5 katını geçmez | Hiç devreye girmezdi (zirve 3,6 kat). 8 kat da aynı: hiç dokunmaz | Tüm dönem: 14 işlem engellenir; net −124 → −120 R; düşüş 351 → 345 R. Son 6 ay: 4 işlem; net +33,9 → +31,7 R | |
| **3 kat** (orta) | Kasanın 3 katını geçmez | 6 işlem engellenirdi (3 kârlı, 3 zararlı). Etki: **−8,2 $** | Tüm dönem: 403 işlem; net −124 → −84 R; düşüş 351 → 316 R. Son 6 ay: 68 işlem; net +33,9 → +30,7 R; düşüş 30,5 → 26,2 R; en kötü hafta −12,1 → −8,3 R | **Önerim** |
| **2,5 kat** (sıkı) | Kasanın 2,5 katını geçmez | 8 işlem engellenirdi (kapanan 6'sı: 2 kârlı, 4 zararlı). Etki: **−3,5 $** | Tüm dönem: 715 işlem; net −124 → −63 R; düşüş 351 → 245 R. Son 6 ay: 107 işlem; net +33,9 → **+9,7 R**; düşüş 30,5 → 29,9 R | |

2 kata da baktım: kağıtta 23 işlem engellenir, **−67 $** götürürdü. Çok sıkı.

**Notlar:**
- Sizin örnek verdiğiniz 5 kat ve 8 kat bugünkü işleyişte hiç devreye girmez; kağıt zirvesi 3,6 kat. Kural koymak istiyorsak anlamlı aralık 2,5–4 kat.
- Geri test %0,5 riskle koşulmuştu; büyüklükleri %1 riske çevirdim (işlem başı 1 kat tavanıyla). Bu bir yaklaşımdır.
- 3 kat, son 6 ayda en iyi dengeyi verdi: kârdan 3 R gidiyor, en kötü hafta 12 R'den 8 R'ye iniyor.

---

## Dört öneri birlikte uygulanırsa

| | Şimdiki | Dört öneri birlikte | Fren hariç üçü |
|---|---|---|---|
| 55 kağıt işlem | +34 $ (kapananlar) | 10 işlem engellenir (kapanan 7'si: 4 kârlı, 3 zararlı); etki **−12 $**. Engellenen 3 açık işlemden biri şu an zararda | aynı (fren hiç tetiklenmedi) |
| Geri test, tüm dönem | net −124 R, düşüş 351 R, en kötü gün −9,2 R, en kötü hafta −17,3 R | net −119 R, düşüş 309 R, en kötü gün −6,9 R, en kötü hafta −13,1 R | net −78 R, düşüş 321 R |
| Geri test, son 6 ay | net +33,9 R, düşüş 30,5 R, en kötü hafta −12,1 R | net **+19,9 R**, düşüş 24,7 R, en kötü hafta −8,2 R | net +32,4 R, düşüş 25,4 R, en kötü hafta −8,3 R |

Okuması: Üç sınır (yön, bağlılık, büyüklük) birlikte kârlı dönemde neredeyse bedelsiz çalışıyor ve en kötü haftayı üçte bir küçültüyor. Kârın düşmesinin asıl kaynağı **fren**.

## Verinin söyleyemediği şeyler

- 55 işlem, 5 gün, tek bir piyasa havası (düşüş, sonra sıçrama). Buradan çıkan dolar rakamları şansa çok açık; 2–3 işlem sonucu tersine çevirir.
- Büyük kayıp saatleri 55'lik dosyada yok.
- Geri test botun 32 kolundan 1'ini, 43 aracından 10'unu kapsıyor. Hisseler için hiç geçmiş veri yok; bağlılık kuralı hisselerde sabit gruplara dayanacak.
- Bir işlem engellenince onun yerine başka bir işlemin açılıp açılmayacağını hesaba katmadım.
- Bu yüzden önerim: eşikleri kilitleyin, ama Aşama B testinde her kuralın "kaç işlemi engelledi, engellenenler ne yapardı" kaydı tutulsun. Karar asıl o kayıtla doğrulanır.

---

## KARAR soruları

**KARAR 1 — Aynı yön sınırı:** %10 mu, %8 mi, %6 mı? (Önerim: **%6**)

**KARAR 2 — Bağlılık sınırı:** Yöntem "30 günlük, 1 saatlik getiri, 0,7 ve üstü aynı bahis; verisi olmayanlarda sabit grup" olarak kabul mü? K = 5 mi, 4 mü, 3 mü? (Önerim: **yöntem kabul, K = 4**)

**KARAR 3 — Kayıp freni:** N = 5 mi, 4 mü, 3 mü? Günlük yarı-limit %4 ve "ilk kârlı kapanışta / ertesi gün kalkar" kuralı kabul mü? (Önerim: **N = 5, %4, kalkış kuralı kabul**)

**KARAR 4 — Toplam büyüklük tavanı:** 5 kat mı, 3 kat mı, 2,5 kat mı? (Önerim: **3 kat**)
