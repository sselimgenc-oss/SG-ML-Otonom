# X-algo fikirleri: denetim ve nihai seçim

Yalnız öneridir; hiçbir şey uygulanmadı. Kaynak içerik veri olarak okundu.

## Haiku denetimi

- 30 maddeden 20'si kaynağına bakılarak kontrol edildi (A: 9, B: 11). Bakılanlar: TAM belgesi, video_notlari.txt, 3 video karesi, 11 ekran görüntüsü.
- Uydurma yok. 5 kusur bulundu:
  - **Kaynağı aşan yorum (2):** A3, MT5 panelindeki "Slip" sütununu "kopya gecikmesi" diye sundu; kaynakta kopya da süre ölçümü de yok, değerler 0/0. B1'deki "sonraki mum açılışından giriş" kaynakta yazmıyor (yazan: "onay sonrası piyasa fiyatından giriş").
  - **Yanlış kaynak (1):** B4, kama/takoz formasyonunu "likidite süpürme" kanıtı saydı; ikisi ayrı şey, kural tanımı da yok.
  - **Bizim tarafı yanlış okuma (2):** B15 "BIST hisse tokenları" diyor, bizde BIST yok (Binance'teki hisse/emtia tokenları var). A13 (üst zaman dilimi onayı) büyük olasılıkla bizde zaten var: kollar 15dk/1sa/1g çalışıyor, rejim etiketi var.
- Küçük eklemeler (hata sayılmadı): B3'teki "ATR katı" ve B6'daki "son N işlem" Haiku'nun kendi ayrıntısı.
- **Kaçan fikir:** beklenti ile gerçekleşenin ayrı raporlanması (tablo #4). Kaçan ders: iki kaynak sistemin kendi sonuçları da zararda (Quantum v5 kâğıtta 8 işlem, %0 kazanma; TradesSenceAI arşivi −0,10R, panoya çıkan sinyaller −0,43R). Yani buradan strateji değil, ölçüm ve güvenlik fikri alınır.

## Seçilen fikirler

| # | Fikir | Proje | Fayda | Zahmet | Fable görüşü | Kaynak |
|---|---|---|---|---|---|---|
| 1 | Kopyalanan trader'ın giriş fiyatı ile bizim giriş fiyatımız arasındaki fark ve gecikme her işlemde kaydedilsin. | CT | Kopya kârının ne kadarının gecikmeyle eridiğini sayıya döker; trader seçimini de iyileştirir. | Düşük-orta | **Yap.** CT'nin en büyük görünmez maliyeti bu, şu an ölçülmüyor. | Uyarlama: MT5 "Slip" sütunları (17.12.20 (7), kare v2_01) |
| 2 | Kol başına istatistik genişlesin: kazanınca ortalama, kaybedince ortalama, %95 güven aralığı, işlem sayısı, dolmayan sinyal oranı. | ML, CT | "Kazanma oranı yüksek ama ortalama zararda" tuzağını gösterir. | Düşük | **Yap.** Veri zaten elde, yalnız rapor eklenir. | 17.12.18 (3), 17.12.18 (5) |
| 3 | Canlıya geçiş şartı önceden sayıyla yazılsın: en az 300 işlem, maliyet sonrası ortalama > 0, güven aralığının alt ucu > 0, en az 2 rejim, 4–8 hafta kâğıt. | ML, CT | Canlı kararı "iyi görünüyor" hissine değil, önceden yazılmış ölçüte bağlanır. | Düşük | **Yap.** Yalnız canlı kapısıdır, kâğıtta hiçbir şeyi kapatmaz; eşikleri kullanıcı onaylar. | TAM §6 (belge yazarının önerisi, kanıt değil) |
| 4 | Geçmiş test beklentisi ile kâğıtta gerçekleşen sonuç yan yana izlensin, fark büyürse uyarı versin. | ML | Aşırı uydurmayı ve bozulan kolu erken yakalar. | Düşük-orta | **Yap.** Holdout mührünü tamamlar; Haiku kaçırmıştı. | 17.12.18 (3) (arşiv −0,10R, pano −0,43R), TAM §6 madde 6 |
| 5 | Likidasyon fiyatı stop mesafesinin en az 2 katı uzakta kalsın; kalmıyorsa kaldıraç düşsün. | ML, CT | Stop çalışmadan likidasyona düşme riskini kurala bağlar. | Düşük | **Yap.** Tek satırlık kontrol, teminat kontrolünün yanına girer. | 17.12.20 (3) |
| 6 | Geçmiş işlemlerin sırası rastgele karıştırılıp binlerce kez denensin; en kötü düşüş ve batma olasılığı çıksın. | ML, CT | %1 risk ve kasa freni eşiklerinin yeterli olup olmadığını sayıyla gösterir. | Düşük | **Yap.** Tek betik, işlemlere dokunmaz. | TAM §6 madde 4; 17.12.21 (yalnız özellik listesi, sonuç yok) |
| 7 | Bir yönün (long ya da short) son dönem sonucu belirgin bozulursa o yönde yeni giriş dursun, nedeni yazılsın. | ML | Tek yönlü zarar serisini keser. | Orta | **Sonra.** Önce #2 ölçsün; az işlemle karar verirse gürültüye tepki verir. | 17.12.20 (2) |
| 8 | Fiyat giriş seviyesinden fazla uzaklaştıysa işleme girilmesin. | CT, ML | Geç ve kötü fiyatlı girişleri eler. | Düşük-orta | **Sonra.** Eşik #1'in ölçümünden çıkmalı; ölçmeden konursa iyi işlemleri de eler. | 17.12.17, 17.12.18 (1) (yalnız etiket; eşik tanımı yok) |
| 9 | Model, eğitim ve test arasına boşluk bırakılarak birden çok dönemde sınansın (purged walk-forward). | ML | Gece eğitilen M1'de veri sızıntısını ve tek döneme bağımlılığı azaltır. | Orta-yüksek | **Sonra.** Değerli ama holdout mührü var; #3 ve #4'ten sonra. | TAM fikir 11, Ek B.7; kare v1_06 |
| 10 | Hisse tokenlarında bilanço günü öncesi yeni giriş kısıtlansın. | ML | Bilanço boşluğundaki ani kayıp riskini azaltır. | Orta | **Sonra.** Önce geçmişte bilanço günlerinde gerçekten kötü mü, veriyle bakılmalı. | 17.12.18 (6), 17.12.20 (6) (BIST örneği; bize uyarlama) |

## Elenenler

Makro şok uyarısı: kaynak uygulama da "sinyal olarak kullanmayın" diyor. (Kullanıcı isteğiyle yeni formasyon kolları ve long/short oranı / açık pozisyon elenenlerden çıkarıldı; en alttaki "Yeni kollar ve kalabalık göstergeleri" bölümünde ayrı ayrı değerlendirildi.) Üst zaman dilimi onayı, sinyal "neden" listesi, kriter skoru, otomatik teşhis metni, üst şerit göstergeleri, strateji kurucu: büyük olasılıkla bizde var ya da yalnız görünüm. Ardışık kayıp limiti: günlük risk limiti ve kasa freni aynı işi görüyor, az işlemde yanlış alarm verir. Tek tuş acil kapatma: fikir doğru, kâğıtta faydası düşük; canlı hazırlığında ele alınmalı. (Düzeltme: ilk sürümde elenen ML vetosu, veri onarımı ve haftalık seviyeler aşağıdaki tweet bölümünde yeniden değerlendirildi ve yukarı alındı.) Dinamik kaldıraç, mum kapanış kilidi, Kalman filtresi, GPU, olay güdümlü mimari, "veri kaybı sıfır", "555 test": doğrulanamayan ya da tanıtım amaçlı iddialar. Forex/MT5, prop firma, sinyal satışı, yönlendirme linkleri: kapsam dışı.

## X tweet'leri ayrıntılı

Kullanıcının itirazı haklı: ilk elemede iki fikri (ML vetosu, veri onarımı) fazla sert eledim, birini (haftalık seviyeler) "anekdot" diye geçtim. Tweet metinleri resimlerden yeniden okundu (17.12.21, (1), (2), (11), (12)). Aşağıdaki hükümler yukarıdaki tabloya ektir; çeliştiği yerde bu bölüm geçerlidir. "Bizde var mı" yalnız mevcut.md'ye dayanır, koda bakılmadı.

### Tweet 1-2: "Hedge Fund Cockpit" (@soligann)

| İddia / özellik | Bize uyar mı | Bizde var mı | Fable görüşü |
|---|---|---|---|
| **ML sinyal üretmez, teknik sinyali veto eder** (ETH LONG'u "%78 düşüş" deyip reddetti) | ML | Kısmen: M1 kendi adayını öneriyor; price-action kollarının sinyalini süzdüğü yazmıyor | **Yap.** Tweet'lerin en değerli fikri: M1 puanı düşükse kolun sinyali atlansın, atlanan işlemin "girseydik ne olurdu" sonucu da kaydedilsin ki vetonun para kazandırıp kazandırmadığı görülsün. Zahmet orta. "%78" tek anekdot, kanıt değil; kanıtı kendi verimiz verecek. |
| **Kendini onaran veri** (boşlukta eksik mumu REST'ten çekip tamamlar) | ML (CT az) | Belirsiz: "mutabakat" var ama mum boşluğu onarımı yazmıyor | **Yap.** M1 her gece eğitiliyor; eksik mum sessizce modeli ve sinyali bozar. Önce kodda var mı bakılır, yoksa boşluk tespiti + tamamlama eklenir. Zahmet düşük-orta. |
| **WebSocket 5 sn'de yeniden bağlanma, "veri kaybı sıfır"** | ML, CT | Belirsiz (bekçi/öz-denetim var) | **Yap, ama denetim olarak.** Yeniden bağlanmak standarttır; asıl soru kopukken kaçan verinin sonradan tamamlanıp tamamlanmadığı. "Kayıp sıfır" bu olmadan doğru olamaz. CT'de kritik: akış koparken trader pozisyonu kapatırsa bizimki açık kalır; yeniden bağlanınca trader pozisyonlarıyla eşitleme var mı, kontrol edilmeli. |
| **Üst kayan şerit**: canlı PnL, düşüş, ML güven skoru, API limit | ML, CT | Kısmen: web pano var; API limit ve veri gecikmesi yazmıyor | **Kısmen yap.** Kayan şerit ve ML güven skoru süs: yapma. Panoya tek "sağlık satırı" ekle: veri kaç saniye eski, son başarılı döngü ne zaman, API limiti ne durumda. Zahmet düşük. |
| KILL SWITCH (her şeyi kapat ve dur) | ML, CT | Kısmen: bekçi otomatik geri alıyor; elle tek tuş yazmıyor | **Sonra.** Canlıdan önce şart; kâğıtta faydası düşük. |
| Olay güdümlü / asenkron pub-sub mimari | Hayır | Yok | **Yapma.** 15 dk ve üstü mumla çalışan sistemde kazanç yok, baştan yazım riski var. |
| WFO (dönem dönem yeniden ayarlama) | ML | Kısmen: gece eğitim + holdout | **Sonra.** Tablo #9 ile aynı. |

### Tweet 3-4: "Quantbot"

| İddia / özellik | Bize uyar mı | Bizde var mı | Fable görüşü |
|---|---|---|---|
| GPU destekli ML | Hayır | Yok | **Yapma.** Verimiz küçük; hız darboğaz değil. |
| Meta-labeling | ML | Kısmen | **Yap.** Yukarıdaki ML vetosuyla aynı iş. |
| Triple-barrier etiket (önce hedef mi, stop mu, süre mi) | ML | Belirsiz: M1 etiketinin nasıl kurulduğu yazmıyor | **Sonra.** Önce M1 etiketine bakılır; gerçek stop/hedef mantığıyla kurulmuyorsa geçmek değerlidir. |
| Otomatik tarihsel veri toplama | ML | Var (gece eğitim, günde 2 güncelleme) | **Yapma** (zaten var). |
| Purged walk-forward | ML | Kısmen | **Sonra.** Tablo #9. |
| Monte Carlo | ML, CT | Yok | **Yap.** Tablo #6. |
| Sızıntı ve aşırı uydurma kontrolü | ML | Var (holdout mühür) | **Var;** tablo #4 (beklenti-gerçekleşen farkı) bunu güçlendirir. |
| Maliyet dahil geçmiş test | ML, CT | Var (ücret/funding) | **Yapma** (zaten var). |
| Prop firma risk kuralları | Hayır | Günlük/toplam limitler zaten var | **Yapma.** Kapsam dışı. |
| MT5 + Binance bağlantısı | Binance evet, MT5 hayır | Binance var | **Yapma.** |
| 555 otomatik test | ML, CT | Var (öz-denetim) | Sayı bir iddia; fikir bizde var. |
| "Henüz kanıtlanmış avantajım yok" itirafı | ML, CT | Yok (yazılı ölçüt olarak) | **Yap.** Tablo #3: avantaj sayıyla kanıtlanmadan canlıya geçilmez. |

### Tweet 5: Quantbot'a gelen yanıt

| İddia / özellik | Bize uyar mı | Bizde var mı | Fable görüşü |
|---|---|---|---|
| **Pazartesi / haftalık / aylık aralık** (o dönemin en yükseği, en düşüğü, açılışı seviye olarak) | ML | Yok | **Yap, önce seviye olarak.** Mumlardan hesaplanır, ek veri gerekmez: M1'e "fiyat bu seviyelere ne kadar uzak" bilgisi verilir ve kırılım/yeniden test kollarına seviye kaynağı olur. Zahmet düşük. Ayrı kol: **sonra**, kendi verimizde işe yaradığı görülürse. Kaynak yalnız "başarı oranı fena değil" diyor; rakam yok. |
| Hacimli majörler (BTC, ETH, SOL) daha az "saçma" hareket eder | ML, CT | Belirsiz | **Yap, rapor olarak.** Kol istatistiği majör / küçük coin diye ayrılsın (tablo #2'ye ek); fark varsa coin listesi ona göre daraltılır. Zahmet düşük. |
| Altın, gümüş, petrol, US100, EURUSD | ML kısmen | Var (hisse/emtia tokenları); forex yok | **Yapma.** Olan var; forex kapsam dışı. |
| Aralık yoksa günlük-4s arz-talep bölgesinden tepki + karakter değişimi | ML | Kısmen (trend geri çekilmesi, iki bacaklı geri çekilme benzer) | **Sonra.** Bölge öznel çiziliyor; makinenin uygulayacağı net kural yazılabilirse denenir. |
| Kama / takoz formasyonu | ML | Kısmen (sıkışma kırılımı aynı fikre yakın) | **Yapma.** Ayrı kol olarak ek getirisi belirsiz. |
| Botu bağlamak yerine TradingView alarmı / Telegram sinyali | Hayır | Telegram var | **Yapma.** Bizim sistem zaten otonom. |

### Net sonuç

Tweet'lerden 5 kayda değer iş çıkıyor: (1) M1'in price-action sinyalini veto etmesi, (2) mum boşluğu tespiti ve onarımı, (3) haftalık/aylık/Pazartesi seviyeleri, (4) kopukluk sonrası eşitleme denetimi (özellikle CT), (5) panoda veri sağlığı satırı. Yanında majör/küçük coin kırılımı küçük bir rapor ekidir. Hepsi kâğıtta açık ve işleme etkili çalışabilir; hiçbiri gölge kip gerektirmez. Çıkmayan şey hazır bir kârlı strateji: iki tweet sahibi de kârlılık kanıtı göstermiyor, biri bunu açıkça söylüyor.

### Yeni kollar ve kalabalık göstergeleri (elenmedi, ayrı ayrı değerlendirildi)

Bu alt bölüm, yukarıdaki "Elenenler" paragrafının ve Tweet 5 tablosundaki kama/takoz ile arz-talep hükümlerinin yerine geçer. Hepsi ML Otonom içindir. CT'ye kol olarak girmezler: CT kendi sinyalini üretmez, trader kopyalar ve makine öğrenmesi kaldırıldı. Hiçbiri gölge ya da yalnız-kayıt önerilmiyor: her biri kâğıtta açık çalışır, gerçek kâğıt işlemi açar ve mevcut risk limitlerine tabidir.

| Fikir | Nasıl girer | Kâğıtta nasıl sınanır | Riski | Fable görüşü |
|---|---|---|---|---|
| **Aralık kolu** (Pazartesi / haftalık / aylık en yüksek-en düşük) | Yeni kol: rejim "yatay" iken fiyat aralığın kenarına gelip içeri dönerse giriş, stop kenarın ötesi, hedef aralığın ortası ya da karşı kenar. Seviyeler ayrıca M1'e bilgi olarak verilir. | Kâğıtta açık kol; kol istatistiğiyle (ortalama, güven aralığı, işlem sayısı) ölçülür; kol başına öğrenme zaten bunu yapıyor. | Trend başlayınca art arda stop; rejim etiketi yanlışsa zarar birikir. Kırılım kollarıyla ters yönde çakışabilir. | **Yap.** Kuralı en net, verisi hazır, mevcut 4 kolun boş bıraktığı yatay piyasayı dolduruyor. Önce seviyeler, hemen ardından kol. Zahmet orta. |
| **Likidite süpürme** (seviye delinir, mum geri içeride kapanır) | Yeni kol: önceki dip/tepe ya da haftalık seviye fitille delinip mum içeride kapanırsa ters yönde giriş, stop fitilin ötesi. | Kâğıtta açık kol; kol istatistiği. Aralık koluyla aynı seviyeleri kullanır, ayrı etiketle izlenir. | Gerçek kırılımı "sahte" sanıp trende karşı girmek. Kırılım yeniden testi koluyla aynı anda ters sinyal: hangisinin geçerli olacağı önceden yazılmalı. | **Yap, aralık kolundan sonra.** Kaynak kanıtı zayıf (uygulamanın tek piyasadaki kendi beyanı: +0,45R, n=256), ama kural yazılabilir ve ucuz. Zahmet orta. |
| **Arz-talep bölgesi + karakter değişimi** | Yeni kol: günlük/4s'te güçlü hareketin başladığı bölgeye fiyat dönünce, alt zaman diliminde son tepe/dip kırılırsa giriş. | Kâğıtta açık kol; kol istatistiği. Ayarları açmadan önce sabitlenir, sonra oynanmaz. | Bölgenin tanımı çok ayar ister; ayarla oynandıkça aşırı uydurma. İki bacaklı geri çekilme ve trend geri çekilmesiyle büyük ölçüde aynı işlemleri alabilir. | **Sonra.** Fikir değerli ama en zor yazılanı; önce iki kol üstte ölçülsün, mevcut kollarla ne kadar örtüştüğü görülsün. Zahmet yüksek. |
| **Kama / takoz** | Ayrı kol değil: sıkışma kırılımı kolunun alt türü (daralan aralık). Alt tür M1'e bilgi olarak da girer, böylece işleme etkili olur. | Kâğıtta açık; sıkışma kolunun işlemleri "kama" ve "diğer" diye ayrı istatistiklenir. | Eğik çizgiyi makineye tanıtmak hataya açık; kazanç küçük kalabilir. | **Sonra.** Düşük öncelik: sıkışma kolu aynı fikri büyük ölçüde zaten alıyor. Zahmet orta. |
| **Long/short oranı ve açık pozisyon (OI)** | ML: önce M1'e bilgi (model puanını, dolayısıyla işlemleri etkiler). İkinci adım sabit kural: aşırı kalabalık yönde yeni giriş açma. CT: kol/filtre olarak önermiyorum; net yön tavanı zaten var. | Kâğıtta açık: M1 bu bilgiyle eğitilir ve işlem seçer; holdout mührü ve beklenti-gerçekleşen farkı (tablo #4) katkıyı gösterir. | Silinen haber etiketiyle aynı son: gürültü ekleyip modeli bozabilir. Hisse/emtia tokenlarında veri eksik olabilir. Geçmiş veri kaynağı doğrulanmalı (Binance'in günlük arşivinde olduğunu hatırlıyorum, kontrol edilmedi). | **Yap, yalnız M1 bilgisi olarak.** Haberden farkı: sayısal, borsanın kendi verisi, her mumda var. Sabit kural filtresi **sonra**. Zahmet düşük-orta. |

Ortak risk ve sıra: birden çok kol aynı anda açılırsa hangisinin işe yaradığı ayrıştırılamaz ve hepsi aynı risk bütçesini (günlük %8, aynı yön limiti) paylaşır. Önerilen sıra: (1) genişletilmiş kol istatistiği (tablo #2) ve haftalık seviyeler, (2) aralık kolu, (3) likidite süpürme kolu, (4) long/short + OI bilgisi, (5) arz-talep, (6) kama alt türü. Her kol kendi etiketiyle açılır; aynı coinde ters yönlü iki kol sinyali için öncelik kuralı açılmadan önce yazılır. Kârlılık kanıtı kaynaklarda yok; kanıtı kâğıttaki kol istatistiği verecek.

## Pano fikirleri (Fable "yalnız görünüm" diye elemişti; kullanıcı istedi, ayrı liste)

| # | Fikir | Proje | Kaynak |
|---|---|---|---|
| P1 | Sinyal/işlem kartında "neden" listesi: hangi koşullar sağlandı, hangisi eksik, kriter skoru (ör. 9/12) | ML | Ek C, 17.12.17, 17.12.18 (3), 17.12.20 (5) |
| P2 | İşlem açılırken o kurulumun geçmiş karnesi: işlem sayısı, ortalama sonuç, kârla kapanma oranı | ML, CT | Ek C, 17.12.18 (3) |
| P3 | Üst şerit: API limit durumu, veri gecikmesi (ms), anlık K/Z ve düşüş | ML, CT | Ek B, kare v1_01 |
| P4 | Otomatik teşhis kutusu: "düşük başarı / stop hatalı / sinyal zayıf" gibi sade uyarı + önerilen adım | ML | 17.12.21 (6) |
| P5 | Her sayfada görünen acil "hepsini kapat ve dur" düğmesi (canlıda önemli) | ML, CT | kare v1_01, v2_06, 17.12.21 (4)(12) |
| P6 | Kol/yön durduğunda panoda nedeni: "short yönü geçici durdu, sebep: …" | ML | Ek C ("Hedefim" ekranı) |

## Önemli düzeltme (21.11 akşam, ML'den teyit)
ML'de zaten var: **R1 = Yatay piyasa kenarı** (bant kenarından içeri dönüş) → Fable'ın "range kolu" önerisiyle aynı fikir; **F1 = Sahte kırılım dönüşü** (stop süpürüp geri dönme) → "likidite süpürme kolu" ile aynı fikir. Yeni kol açmak yerine bunları güçlendirme (ör. Pazartesi/haftalık/aylık seviyeleri R1/F1'e girdi) değerlendirilmeli. R1 şimdiye kadar hiç işlem açmadı (çoğu risk/teminat reddi). Diğer adlar: T1 trend geri çekilmesi, H2 iki bacaklı geri çekilme, S1 sıkışma kırılımı, B1 kırılım yeniden testi, TF1 trend kırılımı, M1 yapay zekâ adayı.
