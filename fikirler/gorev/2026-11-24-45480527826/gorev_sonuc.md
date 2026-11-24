# Price action kontrolü

Üç dosyayı satır satır okumadım: 1117 kuralı `ad`/`alt_tur` anahtar kelimeleriyle grupladım, aday setuplardan yaklaşık 50 kuralın tam metnini ve `yorum` alanını okudum. Sayılar bu yüzden yaklaşıktır (≈). Hiçbir kod ya da test çalıştırılmadı.

İlk karşılaştırmanın (Haiku) sonucu depoda yok: `.github/gorev/pa_karsilastir.md` yalnız görev metni. Bu rapor onun yerine de geçer.

Sonuç: mevcut kollarda ve 42 formasyonda olmayan, mekanik kodlanabilen 8 setup çıktı (PA2 ailesi, 29 kol). Kitaplardaki PA setuplarının çoğu zaten B1, F1, R1, T1, S1 ve GF1 içinde var.

## Model karşılaştırması (kaç kural, kaç kullanılabilir)

| | Haiku | Sonnet | Opus |
|---|---|---|---|
| Kural | 98 | 329 | 690 |
| Kitap | 18 | 21 | 32 |
| Netlik ≥ 3 | 51 | 154 | 374 |
| Konu dışı (hisse taraması, boşluk, haber, arbitraj, mevsimsellik) | 1 | ≈47 | ≈78 |
| Yönetim ya da filtre (setup değil) | ≈30 | ≈123 | ≈214 |
| Setup niteliğinde ve netlik ≥ 3 | ≈30 | ≈61 | ≈196 |
| Tekrarlar birleşince (kitap x setup) | ≈25 | ≈35 | ≈104 |
| Sayıyı modelin koyduğunu `yorum`da söyleyen | — | 217 | 591 |

- Üç dosyada toplam 33 ayrı kitap var, 40 değil.
- **Haiku:** az ama temiz. Stop ve hedef çoğu kuralda "belirtilmemiş"; tek başına kodlanamaz.
- **Sonnet:** orta. Bölge çizim algoritması (s146/s147) en net tariflerden biri.
- **Opus:** en geniş kapsam, ama en çok tekrar ve en çok doldurulmuş sayı. Long/short ve aynı kitabın farklı sayfaları ayrı kural yazılmış.

**Yorumla doldurulan sayılar**

- **Kitaba sadık, kullanılabilir**
  - Bölge çizimi (son ters mumun açılışı ile dip arası), tek kullanımlık bölge, 1:3 oran.
  - 2 günlük ATR tükenme eşiği.
  - Zaybaba: stop = giriş − 1 ATR, hedef 2,5R.
  - Üç çizgi vuruşu: etki 3–5 mumda söner.
  - Force Index 3 günlük geri çekilme ve EMA5 zarfı (kitap tam veriyor).
- **Model uydurması ama makul:** aynı sabitler her kitapta tekrar ediyor, yani kitabın değil modelin varsayılanı.
  - 0,1 ATR stop tamponu, 0,3 ATR "yakın", gövde ≥ aralığın %60'ı, "hedef yoksa 2R", fraktal 2–3 mum, 10–20 mumluk pencereler.
  - PA2 tanımlarında bunları kütüphane ortak kurallarıyla değiştirdim (tampon yok, kütüphane pivotu).
- **Sadık değil ya da çelişkili, atıldı**
  - Penguen çizgisi formülü (Opus kendi tanımladı).
  - Ölçülü hareketin bütün eşikleri (o405).
  - Önceki hafta seviyesinde %50 fitil ve rejim şartı (o392; kitap yalnız seviyeyi veriyor).
  - Swing aşım eşiğinin "3 x ATR"ye çevrilmesi (o102; kitap pip veriyor).
  - Haber ±30 dk, 12 mum zaman stopu (s321), yutan mum için en çok 1,5 ATR (o71).
  - Üç çizgi vuruşunda trend filtresi: Opus SMA50, Sonnet SMA20; kitapta ikisi de yok.
- **Kriptoya taşınamayan birimler:** pip, 0,06 $, %7 hedef, "00" yuvarlak sayı, seans saatleri, açılış boşluğu.

## Setup tablosu

H/S/O = Haiku/Sonnet/Opus kural sayısı. "Kitap" = setupun geçtiği ayrı kitap sayısı.

| Setup | Kural (H/S/O) | Kitap | Mevcut 7 kol | 42 formasyon | Karar |
|---|---|---|---|---|---|
| Kırılım + yeniden test, rol değişimi | ≈61 (8/15/38) | 21 | B1 aynı | GF1-RETEST aynı | Var |
| Sahte kırılım, likidite süpürmesi | ≈84 (5/23/56) | 21 | F1 aynı | GF1-SAHTE, MF1-ICSAHTE aynı | Var |
| Arz/talep bölgesine ilk dönüş (taban + kopuş) | ≈124 (9/24/91) | 18 | Yok | Yok (tasarımda "mekanik tanımı yok" diye dışarıda) | **PA2-BOLGE** |
| Emir bloğu, yapı kırılımı sonrası kaynağa dönüş | ≈37 (1/6/30) | 6 | Yok | Yok | **PA2-EMIRBLOK** |
| Fair value gap geri dolumu | ≈14 (0/1/13) | 1 | Yok | Yok | **PA2-FVG** (tek kitap) |
| Önceki gün/hafta tepe-dibi süpürme-dönüş | 8 (2/2/4) | 3–4 | F1 kısmen (seviye kaynağı farklı) | Yok (seans gerekçesiyle dışarıda) | **PA2-ONCEKI** |
| Günlük 2 ATR tükeniş dönüşü | 14 (3/3/8) | 8 (çekirdek 3) | Yok | IN1-BOLL kısmen | **PA2-TUKENIS** |
| Trend çizgisi ya da kanal dibine dokunuş | 26 (3/7/16) | 11 | T1 kısmen (EMA'ya dokunuş) | Yok (GF1-TREND kırılım, GF1-KANAL yatay) | **PA2-TCIZGI** |
| Yatay seviyede pin bar ya da yutan mum | 24 (1/6/17) | 10 | R1 kısmen | MF1-PINBAR/YUTAN kısmen (seviye şartı yok) | **PA2-SEVIYE** |
| Üç çizgi vuruşu | 3 (1/1/1) | 1 | Yok | Yok (MF1-DISBAR yakın) | **PA2-UCVURUS** (tek kitap) |
| Trend içi geri çekilme (EMA, Fibonacci, swing) | ≈41 (6/18/17) | 15 | T1, H2 aynı | IN1-MAGERI, FIBO aynı | Var |
| 3 mumluk geri çekilme + Force Index | 5 (0/3/2) | 1 | T1 kısmen | Yok | T1 varyantı |
| Yatay piyasa kenarı | ≈32 (1/15/16) | 12 | R1 aynı | GF1-KANAL aynı | Var |
| İki başarısız kırılım denemesi | 6 (0/2/4) | 3 | F1 kısmen | GF1-SAHTE kısmen | F1 varyantı |
| Trend yönünde kırılım | ≈34 (9/6/19) | 16 | TF1 aynı | GF1-YATAY, IN1-HACIM aynı | Var |
| Sıkışma, iç mum, konsolidasyon kırılımı | 17 (3/2/12) | 12 | S1 aynı | MF1-ICCUBUK, GF1-FLAMA aynı | Var |
| Trend çizgisi kırılımı | 9 (0/2/7) | 4 | H2 kısmen | GF1-TREND aynı | Var |
| Üçgen, bayrak, kupa, ikili, OBO, ölçülü hareket | 54 (11/9/34) | 15 | S1 kısmen | GF1 aynı | Var |
| Yalın mum (pin, yutan, harami, dış dönüş) | 18 (0/6/12) | 7 | Yok | MF1 aynı | Var |
| MA kesişimi, RSI, stokastik, uyumsuzluk, hacim | 37 (4/12/21) | 12 | Yok | IN1 aynı | Var |
| Önceki mumun dibini alıp ters kapanan tek mum | 4 (2/0/2) | 1 | F1 kısmen | MF1-DISBAR kısmen | Atıldı: bölge şartı olmadan gürültü; bölge şartı BOLGE'de var |
| EMA5 zarfı (H4 GBP) | ≈9 (0/0/9) | 1 | Yok | Yok | Atıldı: bekleyen emir ve sürekli ters dönüş ister; PA değil, indikatör |
| Penguen (2,5 ATR düşüşte takipli alım) | 3 (0/0/3) | 1 | Yok | Yok | Atıldı: formül Opus'un |
| Açılış aralığı, "saat 10 boğaları", PO3, SMT | ≈20 | 2 | Yok | Yok | Atıldı: seans ya da ikinci varlık ister |
| Trend yapısı, S/R tanımı, diğer | ≈56 | — | — | — | Setup değil, tanım |
| Yönetim ve filtre kuralları | ≈367 | 31 | — | — | Bir kısmı varyant tablosunda |
| Konu dışı | ≈126 | 20 | — | — | Atıldı |

## Yeni PA2 formasyonları (uygulayıcı için kesin)

**Aile ve kapasite**

- Aile kodu `PA2`, dosya `arms/pa2.py`, kütüphane yapısı (`FORMASYONLAR`, `_kutuphane.ortak`).
- Kimlik örneği: `PA2-BOLGE@1h`. Toplam 29 kol: 6 formasyon x 4 ZD, ONCEKI 3 ZD, TUKENIS 2 ZD.
- Tavan: `arm_family_max_positions["PA2"] = 6`, `arm_max_positions["PA2-*"] = 3`.
- Hepsi tam boy ve açık başlar; ön değer yok.
- Öncelik tabanı önerim 250 (GF1 200 ile MF1 300 arası).
- Aile içi sıra: EMIRBLOK 1, BOLGE 2, FVG 3, ONCEKI 4, TCIZGI 5, SEVIYE 6, UCVURUS 7, TUKENIS 8.

**Ortak kurallar:** kütüphanedekiyle aynı.

- Karar kapanmış son mumda (`t`); `planned_entry = c[t]`; motor sonraki açılışta girer.
- Short, long'un aynasıdır. Aynı mumda iki yön çıkarsa aday yok.
- ATR = ATR(14). Pivot: sol 10, sağ 2, indeks ≤ `t-2`.
- Tampon yok: stop seviyenin kendisidir. Stop mesafesi girişin %0,6'sından küçükse atla.
- Zaman stopu yazmıyorsa 48 mum.
- "Yedek 2R" = hedef girişe 1R'den yakınsa ya da yanlış taraftaysa hedef 2R olur.
- Kendi rejim ya da hacim filtresi yok.
- Bekleyen emir yok: kitaplardaki limit girişler kapanış teyidine çevrildi (kullanıcı kararı 4 ile aynı yaklaşım).

| Kod | Giriş (long) | Stop | Hedef | ZS | İleriye bakış |
|---|---|---|---|---|---|
| **BOLGE** | Kopuş mumu `k`: `c>o`, gövde ≥ 0,6 x aralık, aralık ≥ 1,0 x ATR[k-1]. Taban: `k-1`'den geriye, gövdesi ≤ 0,5 x aralık olan ardışık 1–5 mum. `ust` = taban gövdelerinin en yükseği, `alt` = taban diplerinin en düşüğü; `ust − alt ≤ 1,5 x ATR[k-1]`; `c[k] >` taban tepesi. İlk dönüş: `k+3 ≤ t ≤ k+50`; `(k, t-1]` içinde `l ≤ ust` yok; `l[t] ≤ ust`, `c[t] > alt`, `c[t] > o[t]` | `alt` | 3R | 48 | Bölge yalnız `≤ k` mumlarından çizilir. İlk temas mumu yeşil kapanmazsa bölge silinir (tek hak) |
| **EMIRBLOK** | Kırılım mumu `k`: `c[k] > max(h[k-20..k-1])`, `c>o`, gövde ≥ 0,6 x aralık. Blok mumu `j`: `k`'den geriye ilk düşüş mumu, `k − j ≤ 3`, gövde[j] > 0,5 x aralık[j] (değilse BOLGE'nin işi). `ust = o[j]`, `alt = min(l[j..k])`; `c[k] − alt ≥ 1,5 x ATR[j]`. İlk dönüş: `k+2 ≤ t ≤ k+50`; `(k, t-1]` içinde `l ≤ ust` yok; `l[t] ≤ ust`, `c[t] > alt`, `c[t] > o[t]` | `alt` | `max(h[k..t-1])`; yedek 2R | 48 | 20 mumluk tepe penceresi `k`'yi içermez. Tek hak |
| **FVG** | Boşluk mumları `g-2, g-1, g`: `l[g] > h[g-2]`; `l[g] − h[g-2] ≥ 0,25 x ATR[g-2]`; orta mum `c>o` ve gövde ≥ 0,6 x aralık. İlk dönüş: `g+1 ≤ t ≤ g+20`; `(g, t-1]` içinde `l ≤ l[g]` yok; `l[t] ≤ l[g]`, `c[t] > h[g-2]`, `c[t] > o[t]` | `min(l[g-2], l[t])` | `max(h[g..t-1])`; yedek 2R | 48 | Boşluk `g` kapanınca kesinleşir. Tek hak |
| **ONCEKI** | Seviye `L`: 15m ve 1h'de önceki tam UTC gününün dibi; 4h'de önceki UTC haftasının dibi (Pzt 00:00). `s` = içinde bulunulan dönemde `l < L` olan ilk mum; `s`'den önce bu dönemde `L` altında kapanış yok. `s ≤ t ≤ s+2`; `c[t] > L`, `c[t] > o[t]`; dönemde ilk böyle mum (dönem ve yön başına tek sinyal) | `min(l[s..t])` | önceki dönemin orta noktası `(H+L)/2`; yedek 2R | 48 | Dönem sınırı mum açılış zamanından. İçinde bulunulan dönem seviye hesabına girmez. 1d ZD yok |
| **TUKENIS** | Yalnız 15m ve 1h. `dATR` = günlük ATR(14), önceki UTC günü kapanışındaki değer. Bugünün (`t` dahil) tepesi `Gh`, dibi `Gl`: `Gh − Gl ≥ 2 x dATR`; günün dibi tepesinden sonra oluşmuş; dip son 4 mum içinde; `c[t] > h[t-1]`; gün içinde ilk böyle mum | `Gl` | `c + 0,5 x dATR` | 15m: 48, 1h: 12 | `dATR` bugünün mumlarını içermez. Günlük mum UTC gününe göre toplanır |
| **TCIZGI** | `D1`, `D2` = onaylı son iki pivot dip, `l[D2] > l[D1]`, `D2 − D1 ≥ 5`, `t − D1 ≤ 100`, `t − D2 ≥ 3`. `cizgi(x)` = iki dipten geçen doğru. `D1..t` arasında çizgi altında kapanış yok. `l[t] ≤ cizgi(t) + 0,25 x ATR`, `c[t] > cizgi(t)`, `c>o`; `D2`'den beri ilk böyle mum | `c − 1,0 x ATR` | 2,5R | 48 | Pivot ≤ `t-2`. Çizgi yalnız onaylı iki dipten uzatılır |
| **SEVIYE** | `D1`, `D2` onaylı son iki pivot dip, `abs(l[D1] − l[D2]) ≤ 0,5 x ATR`, `D2 − D1 ≥ 5`; `S = min`. `D2`'den beri `S` altında kapanış yok; `t ≥ D2+3`. `S − 0,5 x ATR ≤ l[t] ≤ S + 0,3 x ATR`, `c[t] > S`. Mum: MF1-PINBAR'ın gölge/gövde koşulları ya da MF1-YUTAN'ın dört mum koşulu (ikisinde de dip10/dip5 şartı aranmaz). `D2`'den beri ilk böyle mum | `min(l[t], l[t-1])` | `max(h[D1..t-1])`; yedek 2R | 48 | Pivot ≤ `t-2` |
| **UCVURUS** | `t-3, t-2, t-1`: üçü de `c<o`; `l[t-2] < l[t-3]`, `l[t-1] < l[t-2]`; her birinde `(c − l) ≤ 0,25 x (h − l)`. `t`: `o[t] ≤ c[t-1]`, `c[t] > h[t-3]` | `l[t]` | 2R | 5 | Yalnız son 4 kapanmış mum |

**Kaynak ve sadakat notları**

- **BOLGE:** bölge çizimi ve "ilk dönüş, tek hak" kitaplardan (en az 6 arz-talep kitabı); 1:3 oran iki kitaptan. Taban 1–5 mum, gövde oranları, 1,5 ATR genişlik ve 50 mum ömür model/benim seçimim.
- **EMIRBLOK:** "güçlü hareketten önceki son ters mum" ve "ilk dokunuş" kitaptan (ICT, order block, SMC). 1,5 ATR, 3 mum ve 20 mumluk tepe Opus'un. Sonnet ömrü 100 mum demişti; 50 aldım.
- **FVG:** üç mumluk boşluk tanımı kitaptan. Opus asgari boşluğu 0,1 ATR yazmış; 15m gürültüsü için 0,25 yaptım. %50 limit girişi kapanış teyidine çevrildi.
- **ONCEKI:** seviyeler dört kitapta geçiyor; "aşıp geri kapanma", 3 mum penceresi ve orta nokta hedefi Opus'un.
- **TUKENIS:** kitaptan yalnız 2 ATR eşiği geliyor. Tetik ve hedef Opus'un. Opus'un 0,25 ATR stop payı kütüphane kuralı gereği kaldırıldı.
- **TCIZGI:** stop 1 ATR ve hedef 2,5R Zaybaba'dan. Yakınlık 0,25 ATR, kitabın "2–4 kademe"sinin çevirisi.
- **SEVIYE:** "seviyede mum teyidi" on kitapta var; hiçbiri sayı vermiyor. Bütün eşikler seçimdir.
- **UCVURUS:** kitap yalnız yükseliş yönünü anlatıyor; short aynası kütüphane kuralıyla geliyor. Dördüncü mum için Opus "ilk mumun yükseği", Sonnet "açılışı" demiş; sıkı olanı aldım. Trend filtresi konmadı.

**Testler:** kütüphanedeki kalıpla aynı. Her formasyon için long tetikler, short aynası tetikler, bir koşul bozulunca tetiklemez; `t` sonrası mumlar değişince karar değişmez; 500 ve 5000 mumluk pencere aynı adayı verir.

## Mevcut kollara varyant önerileri

Hiçbiri motora eklenmedi; karar sizde.

| Kol | Varyant | Kaynak | Not |
|---|---|---|---|
| T1 | 3 mumluk geri çekilme tetiği: art arda 3 düşen tepe, sonra `c > h[t-1]`; isteğe bağlı Force Index EMA3 ≤ 0 ve EMA13 ≥ 0 | 1 kitap, Sonnet + Opus, netlik 4–5 | Kitap tam veriyor; yalnız tamponlar dolar cinsinden |
| T1 | Geri çekilme derinliği son itkinin %38–62'si (koşul değil, özellik olarak) | 4 kitap | Oranlar kitaplarda farklı (50, 61,8, 78,6) |
| T1 | Geri çekilme eski direnç/destek seviyesine denk gelsin | 3 kitap | Seviye tanımı SEVIYE ile ortak olabilir |
| R1 | Teyit olarak Heikin Ashi renk dönüşü (fitil reddi yerine ya da yanında) | 1 kitap, Sonnet + Opus | |
| R1 | Yön filtresi: long yalnız bandın alt yarısında/üçte birinde | 3 kitap | R1 kenar şartıyla büyük ölçüde zaten sağlanıyor |
| R1 | İlerlemeyen işlemde erken zaman stopu ve kademeli çıkış | 1 kitap | Motorda kısmi çıkış var mı bakmadım |
| R1 | Band dışına %50 sapmaya limit emir | 1 kitap, netlik 4; 4 işlemlik örnek | Bekleyen emir olmadığı için şimdilik uygulanamaz |
| TF1 | Hacim onayı: kırılım mumunun hacmi ≥ 1,5 x 20 mum ortalaması | 4 kitap | IN1-HACIM ile kısmen çakışır |
| TF1 | Uzun üst fitilli kırılım mumunu ele | 1 kitap | Gövde ≥ 0,5 şartı kısmen karşılıyor |
| TF1, H2 | İz süren stop olarak hareketli ortalama ya da önceki mumun dibi | 3 kitap | Çıkış kipi değişir; ders kapsamına dokunur |
| B1 | Retest mumunda pin bar ya da yutan şartı | 3 kitap | Sinyal sayısını azaltır |
| B1 | Karmaşık (çok mumlu, gidip gelen) kırılımda retest alma | 1 kitap, Opus | "Karmaşık" tanımı kitapta sayısız |
| B1 | Seviye yerine bölge (kırılan arz bölgesi talebe döner) | 3 kitap | PA2-BOLGE ile birlikte düşünülmeli |
| H2 | Tetik olarak 3 alçalan tepeden geçen mini çizginin kırılımı | 1 kitap, Opus | Doğrusallık ölçüsü Opus'un |
| H2 | Yarı pozisyonda sabit kâr, kalan iz süren stop | 2 kitap | Kitaptaki %7 hisseye göre; ATR'ye çevrilmeli |
| S1 | Kutuda hacim düşük, kırılımda hacim yüksek şartı | 4 kitap | |
| S1 | Ölçülü hedef: kutu dibi + direk boyu (şimdi hedef yok, iz süren stop) | 2 kitap | GF1-BAYRAK aynı fikri taşıyor |
| F1 | İki başarısız deneme: aynı seviyede ikinci süpürmeden sonra gir | 3 kitap | Şimdiki "t-1 ham adayı yoksa" kuralının tersi |
| F1 | Süpürme mumunda yutan ya da pin bar şartı | 2 kitap | `rej ≥ 0,6` kısmen karşılıyor |
| F1 | Aşım derinliğine göre ayrım: sığ aşım dönüş, derin aşım devam | 1 kitap, üç model | Kitap pip veriyor; F1'in 1,5 ATR sınırı aynı fikrin karşılığı |

## Uyarılar

- **Sayım yöntemi:** tablo sayıları anahtar kelimeyle çıkarıldı, ±%10–20 kayabilir. "Yönetim/filtre" satırı bir miktar fazla sayıyor; "stop avı" gibi adlar oraya düşmüş olabilir.
- **Test edilmedi:** 8 PA2 formasyonunun hiçbiri geçmiş testten geçmedi. Eşiklerin çoğu kitapta yok; model ya da ben doldurdum. Kullanıcı kararı gereği yine de tam boy ve açık başlarlar.
- **Tek kitaba dayananlar:** FVG ve UCVURUS. Önceki turda tek kitap eleme ölçütüydü; isterseniz ikisi çıkarılır, 6 formasyon ve 21 kol kalır.
- **Çakışma:**
  - EMIRBLOK, BOLGE ve FVG çoğu zaman aynı itkiden doğar ve aynı mumda tetikleyebilir; öncelik sırası ve `arm_conflict` çözer.
  - ONCEKI ve SEVIYE, F1 ile aynı mumda çıkabilir; mevcut kol önce gelir.
  - SEVIYE, MF1-PINBAR/YUTAN'ın seviye şartlı alt kümesidir.
- **TUKENIS:**
  - Hedef (0,5 dATR) stop mesafesinden kısa kalabilir, yani R:R 1'in altına düşebilir.
  - Günlük ATR için en az 15 tam gün veri gerekir; 15m penceresinin buna yetip yetmediğini doğrulamadım.
  - Kitap bunu "ortalamaya dönüş" günleri için öneriyor; filtre koymadım.
- **ONCEKI:** UTC gün sınırı kripto için bir tercih; kitaplar seans (Londra/NY) kullanıyor.
- **Tampon:** Opus ve Sonnet hemen her stopa 0,1–0,5 ATR tampon eklemiş. Kütüphane kuralına uyup kaldırdım; stoplar kitap tarifinden biraz daha sık vurulur.
- **Kod adı kalıbı:** `PA2-EMIRBLOK` (8 harf) tasarımdaki kalıba sığıyor. Kalıbın koda işlenip işlenmediğine bakmadım.
- **Kapasite tutarsızlığı:** formasyon kütüphanesi tasarımı 4/2 tavanla yazılmış, kullanıcı kararı 6/3. PA2 için 6/3 yazdım; MF1/GF1/IN1 ayarının da 6/3 olduğunu uygulayıcı doğrulamalı.
- **Varyant tablosu:** öneriler kolların docstring'leriyle karşılaştırıldı. T1 ve R1'in donuk `signals.py` içindeki tüm koşullarını satır satır okumadım.