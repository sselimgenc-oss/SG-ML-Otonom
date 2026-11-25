# HB1 zaman dilimi

## Karar
HB1 şimdilik yalnız 1s kalsın; 4s ve 1g hiç açılmasın, 15d ise ancak HB1@1h 60 işlemlik ölçümünü tamamladıktan sonra ve aşağıdaki değişikliklerle yeniden değerlendirilsin.

## Gerekçe

Ortak zemin (koddan okundu, çalıştırılmadı):
- **Üretim:** sinyal saatte bir, :08'de yazılır; ham haber de saatlik toplanır.
- **Geçerlilik ve pencere:** dosya 3 sa geçerli; puan 6 sa pencerede 2 sa yarı ömürle karar anında yeniden sönümlenir. Tek olay en çok 1,0 puan verir, yani 0,6 eşiğini en fazla ~1,5 sa geçer.
- **Sızıntı:** her ZD'de aynı kural korur (mum kapanışı > üretim + 60 sn); ZD açmak sızıntı yaratmaz.
- **Tekrar tetiklenme:** "aynı haberle yeniden giriş yok" kontrolü defteri kol kimliğiyle (`HB1@1h`) sorgular, yani ZD'ler birbirinin işlemini görmez.
- **Zaman stopu:** kodda HB1 için `TIME_STOP` yok, varsayılan 48 mum uygulanır. Tasarım ve `hb1.py` açıklaması 24 mum diyor; bu bugün 1s'te de bir uyumsuzluk.
- **Öğrenme:** geri test yok, yalnız ileri ölçüm; tut/kaldır eşiği 60 işlem. `HB1: 3` tavanı tüm ZD'lerin toplamıdır, yani yeni ZD işlem eklemez, aynı 3 yeri böler.

| ZD | aç/açma | neden |
|---|---|---|
| 15d | açma (şimdilik) | Tek gerçek fayda: giriş :15'te olur, sinyal yaşı ~52 dk'dan ~7 dk'ya iner. Zararı: aynı sinyal 3 saatte 12 mumda sınanır ve stop sonrası aynı haberle 1s'ten yeniden girilebilir. Stop 1,5 × 15d ATR haber oynaklığında gürültüye takılır, komisyon R'ye oranla büyür, mum yönü teyidi zayıflar. Çift başına tek pozisyon yüzünden 15d önce girer ve HB1@1h'yi aç bırakır; 60 işlemlik ölçüm bozulur. |
| 1s | açık kalsın | Üretim sıklığıyla aynı ritim: her sinyal dosyası tam bir kez, bir sonraki saat kapanışında sınanır. Tekilleştirme ve tavanlar buna göre yazılmış ve testli. Tüm öğrenme verisi tek kolda toplanır. |
| 4s | açma | 4s kapanışı her zaman bir 1s kapanışıyla çakışır; yeni bilgi getirmez, 1s'in aldığı sinyallerin kabaca dörtte birini aynı anda görür. Kapanıştan ~1,5 sa önceki haberler dışında hepsi eşik altına sönmüş olur. Zaman stopu 48 × 4s = 8 gün, haberin 6 sa ömrüyle ilgisiz. Çok az işlem üretir, öğrenme verisi yetmez. |
| 1g | açma | Günde tek kapanış (00:00 UTC); yalnız ~22:30–00:00 haberleri girebilir. Zaman stopu 48 gün. Yılda bir avuç işlem, öğrenilemez; haber kolu olmaktan çıkar. |

Aile desteği gerekçesi de zayıf: 4s ve 1g neredeyse hiç işlem üretmeyeceği için HB1@1h'ye destek veremez. 15d ise aynı haberlerin aynısını işler, bağımsız kanıt değildir.

## Yapılacaklar

Şimdi ZD açmak için: yok.

Bundan bağımsız, küçük (~0,5 gün): HB1'in zaman stopunu netleştir. Ya `hb1.py`'ye `TIME_STOP = 24` ekle ya da açıklamayı ve tasarımı 48'e düzelt; testle sabitle.

15d ileride açılırsa (tahmini 2-3 gün, testler dahil):
- **Tekilleştirme:** `gates._hb1_olay_karari` defteri kol kimliği yerine kurulum (HB1, tüm ZD'ler) bazında sorgulasın; bekleyen çıkış kontrolü zaten çift bazında.
- **Geçerlilik:** 15d için sinyal yaşı tavanı ~30 dk olsun (yalnız :15 ve :30 kapanışları); 3 sa dosya tavanı 1s için kalsın.
- **Stop/hedef:** 15d ATR yerine 1s ATR ile 1,5 / 3 hesaplansın (`h4`/üst ZD verisinden), yoksa gürültü stopu.
- **Zaman stopu:** `TIME_STOP = {"15m": 24, "1h": 24}` (15d'de 6 sa = haber penceresi).
- **Yapılandırma:** `TIMEFRAMES`, `engine.paper.json` ve `engine.live.json` `arms` listesine `HB1@15m`; `HB1: 3` tavanı toplam olarak kalsın.
- **Ölçüm:** `HB1@15m` için ayrı 60 işlemlik tut/kaldır eşiği; `test_hb1_kol.py` içindeki `TIMEFRAMES == ("1h",)` ve tavan testleri güncellensin, ZD'ler arası aynı-olay testi eklensin.