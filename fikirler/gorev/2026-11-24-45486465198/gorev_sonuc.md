# Ders neden öğrenmiyor

## Neden
- **Sorun kol × ZD dağılımı değil.** Parametre dersi kanıtı zaten havuzdan alıyor: o ayarı okuyan tüm kurulumlar, tüm zaman dilimleri birlikte (`ledger.py` `LESSON_SCOPE`, 24.11 kararı).
- **Asıl engel iki grup şartı.** Ders, işlemleri "ayarın etkilediği" ve "etkilemediği" diye ikiye böler ve iki grupta da en az 8 işlem ister (`lesson.py` `_eval_ab`). Üstüne 4 ayrı gün, 0,5 R fark ve z ≥ 1,64 gelir. 23 işlemle bu dolmaz; bazı ayarların kapsamı zaten 1-2 kurulumdur.
- **"0/10" yanıltıcı.** Bu sayı eşiğe yaklaşmayı göstermiyor. Uygulanmış bir dersin etkilediği karar sayısıdır (`panel_pano.py` `MIN_ETKI = 10`). Ders uygulanmadıkça hep 0 kalır.
- **"Alınsaydı" verisi kısmen kullanılıyor:**
  - Parametre dersi adayı seçerken kullanmıyor; yalnız kapanmış işlemlere bakıyor. Alınsaydı sonucu orada sadece ek bilgi.
  - Kol aç/kapa dersi kullanıyor (`counterfactual_run._arm_lesson`): her kol × ZD için alınan ve alınmayan adayları birlikte sayıyor. Ama her kol tek başına ve 10 sanal işlemle sönümleniyor; aile verisi yok.
  - Bu kol kapatmaları Ders kartında hiç görünmüyor; kart yalnız parametre değişikliklerini sayıyor.
- **166+ kolda asıl yavaşlayacak olan kol aç/kapa dersidir**, çünkü kol başına aday sayısı çok düşecek.

## Seçenekler
Hız ve risk sütunları kod okumasına dayalı tahminimdir; ölçülmedi.

| Seçenek | Hız kazancı | Aşırı uyum riski |
|---|---|---|
| (a) Alınsaydı verisini parametre dersine eklemek | Yüksek (veri 3-10 kat artabilir) | Yüksek: sanal dolum, aynı sinyalin art arda mumlarda çift sayılması (kodda tekilleştirme yok), elenen sinyaller rastgele değil |
| (b) Eşik düşürmek | Hemen | En yüksek: 166 kolda şans eseri "ders" çıkar |
| (c) Havuzlama: kolu ailesine (aynı formasyon, diğer ZD'ler) çekmek | Orta-yüksek; kol sayısı arttıkça artar | Düşük: kol kimliği korunur, aile yalnız başlangıç tahmini olur |
| (d) Kartı düzeltmek (gerçek ilerleme + kol dersleri) | Hız yok, görünürlük var | Yok |

## Önerim
**(c) + (d), alınsaydı verisini temizleyerek. Eşikler düşürülmesin.**

Kol aç/kapa dersi aile ortalamasıyla desteklensin. Bu, küçültmede zaten çalışan yöntemin aynısı. Her formasyon yine kendi kimliğiyle karar alır; verisi azken ailesine yaslanır, verisi çoğaldıkça kendi sonucuna döner. Parametre dersine dokunulmasın: zaten havuzlu, eksik olan sadece zaman.

## Uygulama talimatı
1. **Aile desteği** (`lesson.arm_lifecycle_step` ve `scripts/counterfactual_run._arm_lesson`):
   - Yeni isteğe bağlı girdi `aile_ort`: aynı formasyonun, kolun kendisi hariç diğer ZD'lerdeki çözülmüş adaylarının sönümlü ortalaması, `toplam R / (n_aile + 10)`.
   - Karar ölçütü: `m = (toplam_kol + 10 × aile_ort) / (n_kol + 10)`.
   - Aile verisi yoksa `aile_ort = 0` alınır; bu bugünkü davranışla birebir aynıdır.
   - Kapatma −0,15 ve açma +0,05 eşikleri aynı kalır.
2. **Kapatma için asgari öz kanıt:** kolun kendi çözülmüş adayı en az 3 ve en az 3 ayrı günden olmalı. Yalnız aile yüzünden kol kapanmasın.
3. **Alınsaydı temizliği** (`counterfactual.arm_candidates`):
   - Tekilleştirme: aynı kol + parite + yön için 48 mumluk pencerede yalnız ilk aday sayılır.
   - Alınmayan adayın R'si toplamda ve sayıda 0,5 ağırlıkla girer.
   - `arm_rows` bugün varsayılan `barrier` yöntemini okuyor. `plan` satırı varsa o tercih edilsin (`_cf_r_by_decision` ile aynı kural).
4. **Geri alma kuralına dokunma** (−3 R). Yanlış kapatmanın sigortası odur.
5. **Kart** (`panel_pano.ders_view`):
   - "0/10" yerine en yakın adayın gerçek ilerlemesi yazılsın (örnek: "en yakın aday 5/8 işlem, 3/4 gün").
   - Kol dersleri (`arms_off.json`: kapatılan, yeniden açılan) aynı kartta listelensin.
6. **Testler:**
   - Aile yokken eski sonuçla birebir eşitlik.
   - Tekilleştirme.
   - Yalnız aile verisiyle kapanmama.
   - `lesson.json` eşiklerinin değişmediği.

## Küçültme kartı
**Hata değil, gösterim eksiği.**

- Küçültme iki veriye bakar: kolun son 5 / son 10 kapanmış işlemi ve ailesinin (aynı formasyon, diğer ZD'ler, son 90 gün) ortalaması (`kol_kucultme.karar`, `gates._kol_karari`).
- B1@1h, H2@15m ve M1@1h'nin kendi işlemi 5'ten az, o yüzden "son 5" boş. Ama ailelerinin ortalaması ekside olduğu için boyut %50'ye inmiş. 23.11 kuralı bunu bilerek yapıyor ve 0 işlemli kolu da kapsıyor.
- Kart yalnız "son 5 / son 10" toplamını basıyor (`panel.js` satır 476). Küçültmenin gerçek nedeni olan aile ortalaması karta gönderilmiyor (`kucultme_view`).

Düzeltme: satır "%50 boyut · kendi 2 işlem · aile ort. −0,31 R (aile nedeniyle)" gibi yazılsın (sayılar örnektir).

İki küçük tutarsızlık daha var:
- Kart aileyi tüm geçmişten hesaplıyor, motor son 90 günden. İkisi ileride farklı sonuç gösterebilir.
- Hiç işlemi olmayan ama aile yüzünden küçültülen kollar kartta hiç görünmüyor.

Bilmen gereken bir sonuç: formasyon kütüphanesi gelince, ailesi ekside olan her yeni kol yarım boyutla başlayacak. İstenen davranış buysa sorun yok; değilse ayrıca karar gerekir.