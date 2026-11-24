# Price action karşılaştırması

Kurallar ve kod okunarak yazıldı; hiçbir test ya da kod çalıştırılmadı. Yedi kolun kapsamadığı beş setup grubu çıktı; bunlardan yedi yeni formasyon tanımladım (yeni aile PA2, 26 kol). Bunların hiçbiri geçmiş veride test edilmedi ve eşiklerin çoğunu kitap sayı vermediği için ben doldurdum.

- **Kaynak:** `kurallar_pa.jsonl` (18 kitap, 98 kural; netlik ≥ 3 olan 51) ve `kurallar.jsonl` içinden PA niteliğindeki, netliği ≥ 3 olan yaklaşık 135 kural. İkinci dosyayı anahtar sözcükle süzdüm.
- **Gruplama elle yapıldı:** sayılar ±1-2 oynayabilir. "+N" genel dosyadan gelen ek kuralı gösterir; orada kitap sayısını çıkarmadım.
- **Kütüphane durumu:** 42 formasyonluk tasarım (`gorev_sonuc.md`) bulundu, ama bu dalda henüz kodlanmamış (`mf1.py`, `gf1.py`, `in1.py`, `_kutuphane.py` yok). Yeni formasyonlar o altyapıya bağlıdır.

## Grup tablosu

| # | Setup grubu | PA kural / kitap | Mevcut 7 kol | Kütüphane (42) |
|---|---|---|---|---|
| 1 | Trendde ortalamaya geri çekilme, devam | 3 / 2 (+3) | T1 aynı; H2 kısmen | IN1-MAGERI aynı |
| 2 | Yatay piyasa kenarından dönüş | 3 / 2 (+4) | R1 aynı | GF1-KANAL aynı |
| 3 | Seviye ya da momentum kırılımı | 5 / 3 (+8) | TF1 aynı | GF1-YATAY, IN1-HACIM aynı |
| 4 | Kırılım + yeniden test, rol değişimi | 9 / 6 (+7) | B1 aynı | GF1-RETEST aynı |
| 5 | Sahte kırılım, likidite süpürmesi | 6 / 3 (+4) | F1 aynı; tek mumluk süpürme kısmen | GF1-SAHTE aynı; MF1-ICSAHTE, MF1-DISBAR kısmen |
| 6 | Sıkışma, iç çubuk kırılımı | 4 / 3 (+5) | S1 aynı | MF1-ICCUBUK aynı |
| 7 | Klasik formasyonlar (üçgen, omuz-baş, ikili, fincan, bayrak) | 10 / 5 (+40) | Yok (S1 bayrağı kısmen) | GF1 aynı |
| 8 | Trend çizgisi kırılımı | 2 / 1 (+2) | Yok | GF1-TREND kısmen (yalnız düşen kanal) |
| 9 | Fibonacci geri çekilme | 2 / 2 (+2) | T1, H2 kısmen | IN1-FIBO aynı (%78,6 girişi yok) |
| 10 | Hareketli ortalama yönü ve kesişimi (PA değil) | 7 / 4 | Yok (T1 ve TF1 süzgeç olarak kullanıyor) | IN1-FIYATMA, HIZLIMA, MAKESISIM aynı |
| 11 | Seviyede mum onayı (pin bar, yutan) | 2 / 2 (+12) | R1 kısmen (yalnız range kenarı) | MF1-PINBAR, MF1-YUTAN kısmen (seviye şartı yok) |
| 12 | **Arz/talep bölgesine ilk dönüş** | 16 / 8 (+3) | **Hiçbirinde yok** | Yok (tasarımda "mekanik tanımı yok" diye dışarıda) |
| 13 | **Trend yapısı değişimi** (düşük tepe kırılır, yüksek dip oluşur) | 10 / 6 | **Hiçbirinde yok** | Yok (GF1-TREND ve IKILI yalnız komşu) |
| 14 | **Açılı trend çizgisinden tepki** | 5 / 1 (+3) | **Hiçbirinde yok** | Yok (KANAL yatay, TREND kırılım) |
| 15 | **Önceki gün/hafta tepe-dip seviyesi** | 2 / 1 (+2) | **Hiçbirinde yok** (F1 son 40 mumun dibine bakar) | Yok ("seans gerektiriyor" diye dışarıda) |
| 16 | **Gün içi aşırı uzama, ATR tükenmesi** | 1 / 1 | **Hiçbirinde yok** | Yok |
| 17 | **Seviyede sönen momentum** (küçülen mumlar + dönüş) | 2 / 1 (+2) | **Hiçbirinde yok** | Yok |
| 18 | Üst ZD hizası, test sayısı, seans, haber (süzgeç) | 8 / 5 | Giriş değil; rejim ve B1 dokunma sayısı kısmen | Yok (kütüphane süzgeç eklemiyor) |
| 19 | Risk ve çıkış yönetimi | 11 / 5 | Giriş değil; motorda kısmi kâr, başabaş ve iz süren stop var | — |
| 20 | Açılış boşluğu, açılış aralığı | 0 (+6) | Yok | Yok; kripto 7/24, boşluk oluşmaz |

Netliği 2 ve altında olan 47 PA kuralı da gruplara sayıldı; tanımlarda yalnız netliği ≥ 3 olanlara dayandım.

## Yeni PA formasyonları (uygulayıcı için kesin)

**Aile önerisi: yeni aile `PA2`, GF1'e eklenmesin.**
- GF1'in 13 formasyonu yalnız pivot geometrisi kırılımıdır. Bu yedisi bölge, yapı durumu ve UTC dönem seviyesi ister; ortak hazırlığı farklıdır.
- GF1'e girerlerse aynı aile tavanını (4) paylaşır ve grafik formasyonlarıyla yer için yarışırlar.
- Öğrenme iki seçenekte de formasyon x ZD bazındadır; fark yalnız tavan ve rapor gruplamasındadır.
- Dosya `arms/pa2.py`, `SETUP = "PA2"`, kimlik `PA2-BOLGE@1h`. Kimlik kalıbı tasarımdaki genişletilmiş kalıba uyar.
- Öncelik tabanı 250 (GF1 200 ile MF1 300 arası). Aile içi sıra: YAPIDON 1, BOLGE 2, CIZGI 3, YAPIKIR 4, ONCEKI 5, SONUM 6, TUKENME 7.
- Tavan önerisi: `"PA2-*": 2` ve aile tavanı 4.
- Hepsi açık başlar; ön değer yoktur, tam boyutla başlarlar. Kol sayısı 6 x 4 + 2 = 26.

**Ortak kurallar:** kütüphanenin ortak kuralları aynen geçerlidir.
- Karar son kapanmış mumda (`t`) verilir, `planned_entry = c[t]`, short long'un aynasıdır.
- Pivot sol 10, sağ 2 ve indeksi ≤ `t-2`. ATR(14) kullanılır.
- Stop mesafesi < %0,6 ise `stop_width`, hedef yanlış taraftaysa `other`.
- Zaman stopu yazmıyorsa 48 mum. `EXIT_MODE = "target"`, kendi süzgeci yok.

| Kod | Giriş (long) | Stop | Hedef | Zaman stopu | İleriye bakış |
|---|---|---|---|---|---|
| **BOLGE** | Aşağıdaki talep bölgesine ilk dönüşte onay mumu | `min(alt, min l[i..t])` | Kaçıştan ilk temasa kadarki en yüksek tepe | 48 | Kaçış mumu ≤ `t-3`; bölge yalnız kapanmış mumlardan |
| **YAPIKIR** | Düşüş yapısında son düşük tepenin üstünde ilk kapanış | T2'den `t`'ye en düşük dip | 2R | 48 | Pivotlar ≤ `t-2` |
| **YAPIDON** | YAPIKIR'dan sonra yüksek dip, ardından kırılım zirvesinin üstünde kapanış | Geri çekilme dibi `Q` | 2R | 48 | Pencereler `t-1`'de biter |
| **CIZGI** | Yükselen dip çizgisine üçüncü temas ve yukarı kapanış | `min(l[t], çizgi(t))` | D2'den beri en yüksek tepe | 48 | Çizgi yalnız onaylı iki pivottan; `t`'ye uzatma geçmiş veriyle |
| **ONCEKI** | Önceki gün ya da hafta dibini delip üstünde kapanış | `l[t]` | Aynı dönemin tepesi | 48 | Yalnız BİTMİŞ UTC günü/haftası |
| **SONUM** | Destekte üç küçülen düşüş mumu + dönüş mumu | `min(l[t], l[t-1])` | 2R | 48 | Pivot dip ≤ `t-2` |
| **TUKENME** | Gün içi aralık 2 günlük ATR'yi aşmış, dipten dönüş | Günün dibi | Gün aralığının ortası | 24 | Günlük ATR yalnız bitmiş günlerden |

**BOLGE (grup 12)**
- Taban: 2-6 ardışık mum; her birinin aralığı ≤ 1,0 ATR, kümenin toplam aralığı ≤ 1,5 ATR.
- Kaçış mumu (tabandan hemen sonra): `c > o`, gövde ≥ 0,6 x aralık, aralık ≥ 1,5 ATR, `c >` taban tepesi.
- Bölge: `alt` = tabanın en düşüğü, `üst` = taban gövdelerinin en yükseği.
- Geçerlilik: kaçıştan sonra fiyat `üst + 2 ATR`'ye ulaşmış; o günden `i-1`'e kadar hiçbir mum `üst`'e değmemiş (ilk test); bölge yaşı ≤ 100 mum. Birden çok bölge varsa en yenisi.
- Tetik: `i` = ilk temas mumu (`l ≤ üst`), `t ∈ {i .. i+3}`; `i..t` arasında `alt` altında kapanış yok; `c[t] > o[t]`, `c[t-1] < o[t-1]`, `c[t] ≥ o[t-1]`. Temastan sonraki ilk böyle mum.

**YAPIKIR (grup 13)**
- T1, T2 = son iki onaylı pivot tepe; D1, D2 = son iki pivot dip. Düşüş yapısı: `h[T2] < h[T1]` ve `l[D2] < l[D1]`.
- Tetik: T2'den `t-1`'e kadar `h[T2]` üstünde kapanış yok; `c[t] > h[T2] + 0,5 ATR`; `c > o`.
- 0,5 ATR, kitabın "50 pip" eşiğinin karşılığıdır.

**YAPIDON (grup 13)**
- `b` = son 30 mum içindeki YAPIKIR kırılım mumu; `P` = T2'den `b`'ye en düşük dip; `Hb` = `b..t-1` arası en yüksek tepe; `Q` = `b+1..t-1` arası en düşük dip.
- Koşul: `Q > P` (yüksek dip) ve `Hb − Q ≥ 1 ATR`.
- Tetik: `c[t] > Hb`, `c > o`; `b`'den sonraki ilk böyle mum.
- YAPIKIR pozisyonu açıksa çift başına tek pozisyon kuralı ikinciyi zaten engeller.

**CIZGI (grup 14)**
- D1 (eski), D2 (yeni) onaylı pivot dip; `l[D2] > l[D1]`; aralarında ≥ 10 mum. Çizgi bu iki dipten geçer.
- Geçerlilik: D1'den `t-1`'e çizgi altında kapanış yok; D2'den beri en yüksek tepe ≥ `çizgi(t) + 2 ATR`; `t − D1 ≤ 100`; eğim ≤ 0,25 ATR/mum (kitabın "45 dereceden dik çizgi geçersiz" kuralının karşılığı).
- Tetik: `l[t] ≤ çizgi(t) + 0,25 ATR`, `c[t] > çizgi(t)`, `c > o`; D2'den sonraki ilk böyle mum.

**ONCEKI (grup 15)**
- Seviye `S`: 15m ve 1h'de önceki UTC gününün dibi ve önceki UTC haftasının dibi (hafta Pazartesi 00:00 UTC başlar). 4h ve 1d'de yalnız hafta dibi.
- Tetik: `l[t] ≤ S`, `c[t] > S`, `c > o`; içinde bulunulan dönemde `S` altında kapanış olmamış; dönemde seviye başına tek sinyal.
- Aynı mumda iki seviye tutarsa hafta seviyesi kullanılır; hangisi olduğu etikete yazılır.

**SONUM (grup 17)**
- `t-3, t-2, t-1` düşüş mumu; aralıkları sırayla küçülüyor; her birinin dibi öncekinden düşük.
- `min(l[t], l[t-1])` bir onaylı pivot dibin ± 0,5 ATR içinde.
- Tetik: `c[t] > o[t]` ve `c[t] > h[t-1]`.

**TUKENME (grup 16)** — yalnız 15m ve 1h
- Gün aralığı = UTC günü başından `t`'ye (en yüksek − en düşük) ≥ 2 x günlük ATR(14).
- Günün dibi `t` ya da `t-1`'de yapılmış; `c[t] > o[t]`, `c[t] > h[t-1]`. Günde yön başına tek sinyal.
- Tek kitaba dayanır, kitap stop ve hedef vermez; en zayıf adaydır.

**Kod açılmayanlar**
- Emir bloğuna dönüş (akıllı para kitabı, tek kural): BOLGE ve YAPIDON ile aynı fikir, giriş yeri farklı.
- "Dirençte üçüncü vuruş + iç çubuk" (tek kural): CIZGI'nin aynası zaten kapsar.
- Arz/talep bölgesine bekleyen emirle giriş: motorda bekleyen giriş emri yok (tasarımdaki tespit); BOLGE kapanış teyidiyle girer.

**Testler:** kütüphanedeki kalıp aynen uygulanır.
- Her formasyon için sentetik long, short aynası ve bozulmuş koşul testi.
- İleriye bakış testi: `t` sonrası mumlar değişince karar değişmez; 500 ve 5000 mumluk pencere aynı sonucu verir.
- ONCEKI ve TUKENME için ek test: gün/hafta sınırında bitmemiş dönem kullanılmıyor.

## Mevcut kollara varyant önerileri

Bunlar öneridir, karar sizindir. `signals.py` donuk olduğu için T1 ve R1 varyantları ancak ayrı kol olarak eklenebilir.

| Kol | Kitabın önerdiği, kolda olmayan | Kaynak (kural / kitap) | Nasıl eklenir |
|---|---|---|---|
| B1 | Yeniden test gelmezse seviyenin tamamen dışında kapanan ikinci mumda giriş | 1 kural, netlik 4 | B1'e ikinci giriş yolu; ayrı etiketle, bot ayrı öğrensin |
| B1 | Kırılımdan önce seviye ne kadar çok test edildiyse o kadar iyi (3-4 red) | 4 / 3 | Koşul değil; dokunma sayısı özellik olarak deftere yazılsın (şimdi yalnız ≥ 2 eşiği var) |
| F1 | Süpürmenin en az bir mesafe aşması şartı (kitapta 35-50 pip) | 3 / 2 | F1 bugün yalnız üst sınır koyuyor (≤ 1,5 ATR); alt eşik 0,1 ATR. Alt eşiği 0,3-0,5 ATR deneyen varyant |
| F1 | Tek mumluk süpürme: önceki mumun dibini alıp yukarı kapanan mum, bölge içinde | 2 / 1, netlik 4 | Ayrı kol gerekmez; MF1-DISBAR ve ICSAHTE büyük ölçüde karşılıyor. Karar: yeterli mi |
| T1 | Geri çekilmede %61,8-%78,6 derinlik ve 1:3 hedef | 2 / 2 | T1'e dokunulmaz; IN1-FIBO'ya derin giriş varyantı (stop bacak başı) |
| T1, H2 | Çıkış: stop her kapanışta önceki mumun dibine taşınır | 1 kural, netlik 4 | Yeni iz sürme kipi; şimdiki iz süren stop ATR tabanlı |
| TF1, S1 | Yalnız üst ZD dürtü yönündeki kırılımlar (4s yön, alt ZD formasyon) | 3 / 3 | TF1 zaten rejim istiyor; S1'de yalnız özellik olarak yazılsın |
| R1 | Kenarda fitil yerine iç çubuk kırılımı ya da yutan ile onay | 3 / 2 | R1 donuk; kütüphanede "range kenarında" şartlı ayrı formasyon olarak |
| Tümü | Bölge ya da seviye üst ZD seviyesiyle çakışıyorsa geçerli | 4 / 3 | Süzgeç olarak değil özellik olarak; PA2-BOLGE ve ONCEKI'ye "üst ZD seviyesine uzaklık" sütunu |
| Tümü | %50'yi 1R'de kapat, kalanı iz sür; yakın tepe kırılınca stop başabaşa | 2 / 2, netlik 4 | Motorda kısmi kâr ve başabaş kipleri var; hangi kollarda açık olduğuna bakmadım |

## Uyarılar

- **Tasarımdaki iki dışlamayı tersine çevirdim.** Tasarım arz/talep bölgelerini "mekanik tanımı yok", önceki gün seviyelerini "seans gerektiriyor" diye dışarıda bırakmıştı. Bölgeye mekanik tanım yazdım; gün ve haftayı UTC'ye göre aldım (`tasarim_v2.md` de böyle tanımlıyor). İstemezseniz BOLGE ve ONCEKI çıkar.
- **Benim doldurduğum sayılar:** BOLGE'nin taban ve kaçış ölçüleri, YAPIKIR'daki 0,5 ATR, CIZGI'deki eğim ve 0,25 ATR temas payı, SONUM'daki 0,5 ATR, TUKENME'nin stop, hedef ve 24 mumu.
- **Kitapta stop ya da hedef olmayanlar:** YAPIKIR, YAPIDON ve SONUM için kitap hedef vermiyor, 2R koydum. ONCEKI ve CIZGI'de stop benim seçimim.
- **Örtüşme:** YAPIKIR, GF1-TREND ve GF1-IKILI ile sık sık aynı mumda tetikler; GF1 önceliklidir, YAPIKIR çoğu zaman `arm_conflict` yazılır. ONCEKI ile F1, seviye son 40 mumun dibiyle aynıysa çakışır; F1 önceliklidir.
- **Tavan:** PA2 aile tavanı 4 olursa kütüphane en çok 16 pozisyon tutar, mevcut kollara 24'ten 8 yer kalır (tasarımda 12 kalıyordu). Alternatif: PA2 tavanı 2 ya da kütüphane toplamına ortak sınır. Karar sizin.
- **Alınsaydı hesabı:** TUKENME'nin 24 mumluk zaman stopu, tasarımda YILDIZ için yazılan aynı sınıra takılır; alınsaydı R'si yaklaşık olur.
- **Veri penceresi:** 15m için 5000 mum (yaklaşık 52 gün) ve 1h için 1500 mum, hafta seviyesi ve günlük ATR için yeterli. Günlük ATR'nin 15m mumlarından toplanması yeni yardımcı ister; ısınma dolmadan aday çıkmamalı.
- **Sayım ve dosyalar:** kol sayısı testleri 203 → 229 olur (tasarımdaki 37 + 166 varsayımıyla). Türkçe adlar, panel grubu ve ayar üreticisi PA2'yi de kapsamalı.
- **Kaynak kalitesi:** kurallar PDF'lerden otomatik çıkarılmış; çoğunda giriş mumu, stop ya da hedef "belirtilmemiş". Kitapların çoğu forex ve hisse üzerine; kripto vadelide davranış farklı olabilir.