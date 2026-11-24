# Kitap setuplari geri test raporu

## Kisa sonuc (3-5 madde)

- **Kod temiz.** İleriye bakış, maliyet veya R hesabı hatası bulmadım. Testleri çalıştırmadım (yalnız okuma) ve maliyet tablosundaki sayıları tek tek doğrulamadım.
- **48 hücrenin (12 setup x 4 ZD) çoğu zarar ediyor.** İki dönemde de artıda kalan yalnız 5 hücre var; hiçbiri güçlü bir kanıt değil.
- **Seçimler:** MF1 = `MUM_YILDIZ` (15m), GF1 = `FOR_YATAY_KIRILIM` (1d), IN1 = `IND_FIYAT_MA` (1d + 4h).
- **En zayıf seçim MF1.** Kuralınıza göre `MUM_YILDIZ` 15m kazanıyor, ama az işleme dayanıyor ve long/short sonucu iki dönem arasında ters dönüyor. Yedek aday `MUM_YUTAN` 1d.
- **15m, 1h ve Bollinger her yerde zarar.** 15m'de tek istisna seçilen `MUM_YILDIZ`.

## Setup x ZD tablosu (Setup | Kol | ZD | Gelistirme ort R (islem) | Kilitli ort R (islem) | Rastgeleden iyi mi)

Long ve short birlikte, net R (ücret, kayma ve fonlama düşülmüş). "Belirsiz" = iki dönemde de rastgeleden iyi ama fark istatistiksel olarak küçük. `IND_` satırlarında rastgele kıyas yaklaşıktır.

| Setup | Kol | ZD | Geliştirme ort R (işlem) | Kilitli ort R (işlem) | Rastgeleden iyi mi |
|---|---|---|---|---|---|
| MUM_PINBAR | MF1 | 15m | -0.165 (9877) | -0.235 (5951) | Hayır |
| MUM_PINBAR | MF1 | 1h | -0.183 (9949) | -0.153 (3505) | Hayır |
| MUM_PINBAR | MF1 | 4h | -0.114 (2670) | -0.299 (1178) | Hayır |
| MUM_PINBAR | MF1 | 1d | +0.009 (413) | -0.409 (112) | Hayır |
| MUM_IC_CUBUK | MF1 | 15m | -0.153 (45403) | -0.181 (30536) | Belirsiz |
| MUM_IC_CUBUK | MF1 | 1h | -0.119 (35550) | -0.138 (14557) | Hayır |
| MUM_IC_CUBUK | MF1 | 4h | -0.048 (9740) | -0.092 (4670) | Belirsiz |
| MUM_IC_CUBUK | MF1 | 1d | +0.027 (1418) | -0.095 (573) | Hayır |
| MUM_YUTAN | MF1 | 15m | -0.167 (21957) | -0.206 (14231) | Hayır |
| MUM_YUTAN | MF1 | 1h | -0.121 (21164) | -0.166 (8434) | Hayır |
| MUM_YUTAN | MF1 | 4h | -0.026 (6107) | -0.065 (2870) | Belirsiz |
| MUM_YUTAN | MF1 | 1d | +0.017 (961) | +0.065 (387) | Belirsiz |
| **MUM_YILDIZ** | MF1 | **15m** | **+0.193 (128)** | **+0.200 (46)** | Belirsiz (işlem az) |
| MUM_YILDIZ | MF1 | 1h | -0.002 (405) | -0.103 (93) | Hayır |
| MUM_YILDIZ | MF1 | 4h | +0.048 (305) | -0.177 (110) | Hayır |
| MUM_YILDIZ | MF1 | 1d | -0.227 (56) | -0.640 (39) | Hayır |
| FOR_YATAY_KIRILIM | GF1 | 15m | -0.168 (24311) | -0.196 (16899) | Hayır |
| FOR_YATAY_KIRILIM | GF1 | 1h | -0.115 (16654) | -0.153 (7650) | Hayır |
| FOR_YATAY_KIRILIM | GF1 | 4h | -0.015 (3499) | -0.093 (2117) | Hayır |
| **FOR_YATAY_KIRILIM** | GF1 | **1d** | **+0.147 (301)** | **+0.234 (145)** | Belirsiz |
| FOR_UCGEN | GF1 | 15m | -0.133 (9401) | -0.142 (6585) | Hayır |
| FOR_UCGEN | GF1 | 1h | -0.023 (4486) | -0.017 (2065) | Belirsiz |
| FOR_UCGEN | GF1 | 4h | +0.068 (1233) | -0.004 (583) | Belirsiz |
| FOR_UCGEN | GF1 | 1d | -0.084 (194) | +0.298 (71) | Hayır |
| FOR_IKILI_DIP | GF1 | 15m | -0.098 (25187) | -0.121 (20440) | Hayır |
| FOR_IKILI_DIP | GF1 | 1h | -0.052 (10229) | -0.082 (5767) | Hayır |
| FOR_IKILI_DIP | GF1 | 4h | -0.011 (1893) | -0.020 (1177) | Hayır |
| FOR_IKILI_DIP | GF1 | 1d | -0.049 (163) | -0.045 (72) | Hayır |
| FOR_OBO | GF1 | 15m | -0.188 (250) | -0.161 (217) | Hayır |
| FOR_OBO | GF1 | 1h | +0.024 (88) | -0.210 (59) | Hayır |
| FOR_OBO | GF1 | 4h | -0.129 (13) | +0.402 (10) | İşlem yetersiz |
| FOR_OBO | GF1 | 1d | -0.468 (2) | +0.304 (2) | İşlem yetersiz |
| IND_RSI_3070 | IN1 | 15m | -0.126 (1782) | -0.192 (904) | Belirsiz |
| IND_RSI_3070 | IN1 | 1h | -0.214 (2641) | -0.140 (868) | Hayır |
| IND_RSI_3070 | IN1 | 4h | -0.080 (1204) | -0.243 (417) | Hayır |
| IND_RSI_3070 | IN1 | 1d | +0.324 (232) | -0.400 (105) | Hayır |
| IND_MA_KESISIM | IN1 | 15m | -0.107 (9927) | -0.359 (9252) | Belirsiz |
| IND_MA_KESISIM | IN1 | 1h | +0.119 (4240) | -0.075 (2202) | Belirsiz |
| IND_MA_KESISIM | IN1 | 4h | +0.194 (979) | -0.189 (532) | Hayır |
| IND_MA_KESISIM | IN1 | 1d | +0.047 (152) | +0.184 (55) | Hayır |
| IND_BOLL_DONUS | IN1 | 15m | -0.173 (59761) | -0.213 (32878) | Hayır |
| IND_BOLL_DONUS | IN1 | 1h | -0.186 (73965) | -0.195 (24717) | Hayır |
| IND_BOLL_DONUS | IN1 | 4h | -0.170 (26033) | -0.172 (10719) | Hayır |
| IND_BOLL_DONUS | IN1 | 1d | -0.129 (4213) | -0.160 (1745) | Hayır |
| IND_FIYAT_MA | IN1 | 15m | -0.176 (125809) | -0.441 (114536) | Hayır |
| IND_FIYAT_MA | IN1 | 1h | -0.043 (51725) | -0.136 (25642) | Belirsiz |
| **IND_FIYAT_MA** | IN1 | **4h** | **+0.048 (11838)** | **+0.007 (5752)** | Evet (yaklaşık kıyas) |
| **IND_FIYAT_MA** | IN1 | **1d** | **+0.173 (1623)** | **+0.145 (620)** | Belirsiz |

## Her kol icin secim (Kol | Secilen setup | Zaman dilimleri | Neden | Beklenti: kazandirir / sifir civari / zarar ama ogrenme icin)

| Kol | Seçilen setup | Zaman dilimleri | Neden | Beklenti |
|---|---|---|---|---|
| MF1 | MUM_YILDIZ | 15m | Mum kolunda iki dönemde de en yüksek ortalama (+0.19 / +0.20). İşlem 128 ve 46, ikisi de 30'un üstünde. 15m şartı sağlanıyor. Diğer ZD'ler eksi, alınmadı. | **Sıfır civarı.** Kanıt zayıf. Ayda yaklaşık 3 işlem; öğrenme yavaş olur. |
| GF1 | FOR_YATAY_KIRILIM | 1d | Formasyon kolunda iki dönemde de artıda olan tek hücre (+0.15 / +0.23). Geliştirmede her yıl artı. 4h iki dönemde de eksi, alınmadı. | **Kazandırır (temkinli).** Ayda yaklaşık 9 işlem. |
| IN1 | IND_FIYAT_MA | 1d ve 4h | İki ZD de iki dönemde artı. 1d: +0.17 / +0.15. 4h: +0.05 / +0.01. | **1d: kazandırır (temkinli). 4h: sıfır civarı.** Ayda yaklaşık 37 (1d) ve 340 (4h) işlem. |

Hiçbir kolda "zarar bekleniyor" demem gerekmedi. Ama üçünde de kazanç garantisi yok; bkz. uyarılar.

## Motora ekleme icin kesin kural (secilen 3 setupun giris/stop/hedef/zaman stopu; uygulayici aynen kodlayacak)

**Ortak kurallar (üçü için)**
- Karar yalnız kapanmış mumda verilir. Giriş bir sonraki mumun açılışındadır.
- Çiftin ilk 250 mumunda giriş yok.
- Aynı çift + setup + ZD'de açık pozisyon varken yeni giriş yok.
- Aynı mumda hem stop hem hedef görülürse stop sayılır.
- Açılış stopun ya da hedefin ötesindeyse dolum açılış fiyatındandır.
- Zaman stopu giriş mumunu 1. mum sayar; N. mumun kapanışında çıkılır.
- Short, long'un tam aynasıdır.
- Kendi filtremiz yok (üst ZD, hacim, fonlama vetosu yok). Testte de yoktu.

**MF1 — MUM_YILDIZ, 15m**

| | Long (sabah yıldızı) | Short (akşam yıldızı) |
|---|---|---|
| 1. mum (t-2) | Kapanış ≤ açılış x 0.985. Dibi ≤ bir önceki mumun (t-3) dibi. | Kapanış ≥ açılış x 1.015. Tepesi ≥ bir önceki mumun tepesi. |
| 2. mum (t-1) | Gövde ≤ açılışın %0.3'ü. Gövdenin üst ucu ≤ 1. mumun kapanışı. | Gövde ≤ açılışın %0.3'ü. Gövdenin alt ucu ≥ 1. mumun kapanışı. |
| 3. mum (t) | Kapanış > açılış. Kapanış > 1. mumun gövde ortası, yani (açılış + kapanış) / 2. | Kapanış < açılış. Kapanış < 1. mumun gövde ortası. |
| Giriş | t+1 açılışı | t+1 açılışı |
| Stop | 3. mum kapanışı x 0.97 | 3. mum kapanışı x 1.03 |
| Hedef | 3. mum kapanışı x 1.09 | 3. mum kapanışı x 0.91 |
| Zaman stopu | 20 mum (5 saat) | 20 mum |

- Giriş açılışı stopun ya da hedefin yanlış tarafındaysa işlem yok.

**GF1 — FOR_YATAY_KIRILIM, 1d**
- **Pivot tepe:** Mumun en yükseği, solundaki 10 ve sağındaki 2 mumun hepsinden kesin büyük. Pivot ancak 2 mum sonra, o mum kapanınca kullanılır.
- **Direnç:** Art arda gelen iki pivot tepe (T1, T2). Aralarındaki fark, küçük olanın en fazla %3'ü. Seviye L = ikisinin büyüğü.
- **Tazelik:** T1'den sonraki mumdan T2'nin onay mumunun öncesine kadar hiçbir kapanış L'nin üstünde olmamalı.
- **Geçerlilik:** T2'nin onay mumundan (T2 + 2) başlar. Yeni bir pivot tepe onaylanınca biter.
- **Giriş (long):** Bu pencerede L'nin üstündeki ilk kapanış. Bir sonraki açılışta gir. Aynı seviyeden yalnız bir işlem.
- **Stop:** L ile kırılım mumunun dibinden düşük olanı. Tampon yok.
- **Hedef:** L + (L − T1 ile T2 arasındaki en düşük dip, uçlar dahil).
- **Zaman stopu:** 48 mum.
- **Atla:** Stop mesafesi girişin %0.6'sından küçükse, ya da açılış stopun altında veya hedefin üstündeyse.
- **Short:** Aynısı pivot diplerle (iki yakın dip, altında kapanış).

**IN1 — IND_FIYAT_MA, 1d ve 4h**
- **Gösterge:** Kapanışların 50 mumluk basit ortalaması (SMA50).
- **Giriş (long):** Bu mumun kapanışı > SMA50 ve önceki mumun kapanışı ≤ önceki SMA50. Bir sonraki açılışta gir.
- **Giriş (short):** Bu mumun kapanışı < SMA50 ve önceki mumun kapanışı ≥ önceki SMA50.
- **Çıkış:** Long'da bir mum SMA50'nin altında kapanırsa bir sonraki açılışta çık (short'ta üstünde). Giriş mumunun kapanışından itibaren bakılır.
- **Ters işlem:** Çıkışla aynı açılışta ters yöne giriş serbest.
- **Sabit stop:** Yok. **Hedef:** Yok.
- **Zaman stopu:** 48 mum. Sonrasında yeni giriş ancak yeni bir kesişimle.
- **Pozisyon boyu (1R):** Sinyal mumundaki 2 x ATR(14), Wilder yöntemi. %0.6 taban kuralı uygulanmaz.
- **Motor stop zorunlu tutuyorsa:** Bu test edilmedi. Eklenecek her stop sonucu değiştirir; karar sizde.

## Dürüst uyarilar

- **MF1 seçimi kuralı harfiyen sağlıyor ama güvenim düşük.**
  - Long geliştirmede +0.46, kilitlide −0.03. Short geliştirmede −0.14, kilitlide +0.43. Yön ters dönüyor; bu şans işaretidir.
  - Aynı setup 1h, 4h ve 1d'de zararda.
  - Eşikler (%1.5 düşüş mumu, %3 stop, %9 hedef) günlük hisse içindir. 15m'de yalnız sert çöküş anlarında tetiklenir.
  - İşlemlerin çoğu (kilitlide 46'nın 25'i) zaman stopuyla kapanıyor.
  - Yedek aday `MUM_YUTAN` 1d (+0.02 / +0.07, 961 ve 387 işlem): beklenti sıfır civarı ama daha tutarlı ve ayda yaklaşık 23 işlem veriyor.
- **48 hücreden seçim yapıldı.** Bu kadar denemede birkaç hücre şansla iyi görünür. Seçilenlerin hiçbiri rastgele girişi net biçimde yenmiyor.
- **Kilitli dönem yarı temiz.** Bu seçimden sonra artık temiz değil. Gerçek sınav kağıt işlemleri olacak.
- **IND_FIYAT_MA'da stop yok.** Kötü bir açılış boşluğunda kayıp 1R'yi çok aşabilir. Kazanma oranı yalnız %19; kazanç az sayıda büyük trendden geliyor ve uzun kayıp serileri olağan.
- **IND_FIYAT_MA yıllara göre dengesiz.** 1d geliştirmede 2022 yılı −52R, 2025'in ilk yarısı −19R. 4h kilitlide 2026 yılı −59R.
- **IND_FIYAT_MA 4h'de en kötü çiftler hisseler.** Kilitlide AAPL −36R, GOOGL −28R, JPM −26R.
- **IND kolunda rastgele kıyas yaklaşık.** Rastgele taraf 48 mum bekliyor, gerçek işlem ortalama 13 mumda çıkıyor. Tablodaki "Evet"e fazla güvenmeyin.
- **İki dönem aynı çiftleri içermiyor.** Geliştirmede yalnız 19 çift (kripto) var; kilitlide 43. Günlükte kilitlide de 22 çift işlem verdi; hisse ve emtia günlükte neredeyse hiç sınanmadı.
- **İşlemler birbirinden bağımsız değil.** Kripto çiftleri birlikte hareket eder; gerçek kanıt işlem sayısının gösterdiğinden azdır.
- **Kitabın sayı vermediği yerler kodlayıcı tarafından dolduruldu.** Örnekler: tampon yok, %3 yakınlık, pivot 10/2, kırılım penceresi. Bunlar sonucu etkiler ve onayınızı bekliyor.
- **Yön ayrımı önermiyorum.** Bazı hücrelerde tek yön daha iyi görünüyor ama dönemler arasında tutarlı değil.

## Maliyet

| Adım | Model | Tutar |
|---|---|---|
| 1. Setup seçimi | claude-fable-5-2 | 3.21 |
| 2. Kodlama | claude-sonnet-5-5 | 1.77 |
| 3. Bu rapor | claude-fable-5-2 | yaklaşık 1.5 |
| **Toplam** | | **yaklaşık 6.5** |

İlk iki satır `maliyet.txt`'den; dosyada birim yazmıyor, dolar varsayıyorum. Bu adımın bütçesi 4 dolardı.