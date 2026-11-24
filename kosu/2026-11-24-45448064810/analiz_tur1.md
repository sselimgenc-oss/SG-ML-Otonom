# Tur 1 analizi

## Geri test kod denetimi

**Sonuçları geçersiz kılan bir hata bulmadım.** Kodu satır satır okudum; testleri ve geri testi yeniden çalıştırmadım.

Doğru olanlar:
- **İleriye bakış:** Yok. Pivotlar 3 mum gecikmeyle kullanılıyor, üst zaman dilimi yalnız kapanmış mumdan eşleşiyor, önceki gün/hafta biten dönemden geliyor, VWAP ve hacim ortalaması o anki mumu içermiyor.
- **Giriş ve çıkış:** Giriş bir sonraki mumun açılışında, kayma dahil. Aynı mumda stop ve hedef varsa stop sayılıyor. Boşlukta dolum açılıştan yapılıyor.
- **Maliyet:** Her iki bacakta 5 bps ücret, 2 bps giriş/çıkış kayması, 5 bps stop kayması. Hedef dolumuna da kayma yazılmış (temkinli taraf).
- **Fonlama ve R:** Fonlamanın işareti doğru. R, kaymalı giriş ile stop arasındaki mesafeye bölünüyor. Short aynalaması doğru.

Küçük kusurlar (yön değiştirmez, düzeltilmeli):
1. **Fonlama eksik sayılıyor.** Çıkış mumunun içindeki fonlama ödemeleri hesaba girmiyor; 1d'de işlem başına 1-2 ödeme kaçıyor. Etkisi yüzde birkaç R.
2. **Risk tabanı yanlış yerde ölçülüyor.** %0,6 tabanı ve rr sinyal mumunun kapanışında ölçülüyor, R ise sonraki açılıştan hesaplanıyor. Açılış stopa yakın gelirse çok küçük risk ve aşırı R çıkabilir; koruma yok.
3. **Rastgele taban zayıf.** İşlem başına tek çekiliş var, yıl eşleşmesi yok, yalnız rastgele tarafın standart hatası tutuluyor. Az işlemde anlamsız (GF1 1d long: 2 işlem).
4. **Isınma dönemi.** Üst zaman dilimi EMA'sı hazır değilken durum "yatay" sayılıp filtreden geçiyor. Gerçek sinyaller ilk 250 mumda oluşabiliyor, rastgele çekilişler oluşamıyor.
5. **Veri sonu ve boşluklar.** Veri sonunda açık işlem son mumdan kapatılıyor. Tutma süresi içindeki veri boşluğu denetlenmiyor.
6. **Tasarımdan sapmalar.** IN1 yalnız ardışık iki dip pivotunu eşliyor; tasarım "arası 5-40 mum olan iki pivot" diyor. GF1 B girişinde geri test boyuna değil boyun + 0,3 ATR'ye göre ölçülüyor.

Kapsam uyarısı: 43 çiftin yalnız 19'unda veri var, hepsi kripto. Hisse ve emtia çiftleri (NVDA, XAU vb.) hiç test edilmedi; sonuç onlara genellenemez.

## Kol x zaman dilimi tablosu (islem, kazanma %, ort net R, toplam R, rastgele farki, karar)

Rastgele farkı = gerçek ort R − rastgele ort R. z yaklaşıktır: gerçek tarafın sapması kayıtlı olmadığı için rastgele tarafınkine eşit varsaydım.

| Kol | ZD | İşlem | Kazanma % | Ort net R | Toplam R | Rastgele farkı (z) | Yıllar | Karar |
|---|---|---|---|---|---|---|---|---|
| MF1 | 15m | 577 | 35 | -0,249 | -143,7 | -0,11 (-1,5) | 3 yılın 3'ü eksi | Kapat |
| MF1 | 1h | 1135 | 36 | -0,195 | -221,2 | -0,16 (-3,0) | 5 yılın 5'i eksi | Kapat; rastgeleden belirgin kötü |
| MF1 | 4h | 430 | 38 | -0,109 | -46,7 | -0,02 (-0,3) | 5 yılın 4'ü eksi | Kazandırmıyor, rastgeleden farksız; yapısal değişiklikle son bir deneme |
| MF1 | 1d | 43 | 37 | -0,169 | -7,3 | -0,40 (-1,3) | 4 yıl eksi, 1 yıl sıfır | Karar verilemez (< 50); short 20 işlemde -13,1 R |
| GF1 | 15m | 145 | 30 | -0,278 | -40,4 | +0,02 (0,2) | 2023 ve 2024 eksi | Kapat; rastgele giriş de -0,30 R, masraf yiyor |
| GF1 | 1h | 144 | 35 | -0,160 | -23,0 | -0,22 (-1,4) | 5 yılın 4'ü eksi | Kazandırmıyor; mantık düzeltmesinden sonra yeniden ölç |
| GF1 | 4h | 35 | 40 | +0,139 | +4,9 | +0,09 (0,3) | 3 artı, 2 eksi (2024: -7,9) | Karar verilemez (< 50) |
| GF1 | 1d | 10 | 40 | +0,073 | +0,7 | anlamsız | 2022 tek başına +4,0 | Karar verilemez |
| IN1 | 15m | 0 | – | – | – | – | – | Kapat |
| IN1 | 1h | 1 | 0 | -1,161 | -1,2 | anlamsız | – | Karar verilemez; kural neredeyse hiç tetiklenmiyor |
| IN1 | 4h | 1 | 0 | -1,022 | -1,0 | anlamsız | – | Karar verilemez |
| IN1 | 1d | 0 | – | – | – | – | – | Kapat; hiç teyitsiz bile 4,5 yılda 2 işlem |

- **Kazandıran hücre yok.** Yeterli işlemi olan beş hücrenin (MF1 15m/1h/4h, GF1 15m/1h) hepsi masraf sonrası eksi ve hiçbiri rastgeleden iyi değil.
- **Çiftlere dayanma:** Zarar bütün çiftlere yayılmış, birkaç çifte bağlı değil. MF1 1h'de 19 çiftin 16'sı eksi.
- **GF1 4h'nin artısı kırılgan:** 4,9 R'nin 5,9'u tek çiftten (1000SHIB, 5 işlem) geliyor. Kanıt sayılmaz.
- **15m'de masraf yükü:** Rastgele giriş bile -0,14 ile -0,30 R veriyor. Bu stop mesafeleriyle 15m'de masraf başlı başına engel.

## Teyitlerin katkisi

Ölçü: teyit açıkken ort R − yalnız o teyit kapalıyken ort R.

| Teyit | MF1 (15m / 1h / 4h / 1d) | GF1 (15m / 1h / 4h / 1d) | Sonuç |
|---|---|---|---|
| Hacim | -0,10 / -0,04 / -0,03 / -0,08 | -0,09 / +0,03 / -0,03 / -0,21 | MF1'de 4/4 zararlı ve işlemin %70-88'ini siliyor: at. GF1'de 3/4 zararlı ama örnek küçük. |
| Üst ZD yönü | -0,10 / -0,04 / -0,05 / -0,11 | -0,14 / +0,04 / -0,06 / -0,03 | MF1'de 4/4 zararlı: at. GF1'de karışık; 15m'deki sıkı hali (1h + 4h yukarı) belirgin zararlı. |
| Seviye | -0,04 / -0,04 / +0,07 / -0,06 | uygulanmıyor | Tutarlı katkı yok. 1d'de 45 işlemden 43'ünü geçiriyor, yani hiç süzmüyor (mantık kusuru, aşağıda). |
| Fonlama vetosu | +0,01 / 0,00 / +0,02 / +0,03 | -0,02 / +0,01 / +0,07 / 0 | İşlemin %1-6'sını eliyor, etkisi gürültü düzeyinde. Zararsız; risk kuralı olarak kalsın. |
| Maliyet tabanı | +0,11 / +0,01 / 0 / 0 | +0,03 / 0 / 0 / 0 | Gerçek katkı veren tek teyit, o da yalnız 15m'de. 4h ve 1d'de hiç devreye girmiyor. |

- **MF1'de teyitlerin toplamı işe yaramıyor.** Hiç teyitsiz MF1 1h -0,177, 4h -0,102, 1d -0,028; tam teyitli hali üçünde de daha kötü. Şeklin kendisinde kazanç yok.
- **IN1'de teyitler kolu boğuyor.** Hiç teyitsiz 106 / 48 / 21 / 2 işlem var; herhangi bir teyit tek başına kapatılınca bile en çok 3 işlem kalıyor. Hangisinin katkı verdiği ölçülemiyor.

## Zaaflar

1. **GF1'de ikili dip hiçbir zaman işlem açamaz (tasarım hatası).** Stop dibin altında, hedef boyun + formasyon yüksekliği, giriş boyunun üstünde. Bu üçüyle rr en fazla 2 / 1,7 ≈ 1,18 çıkar; rr ≥ 1,5 şartı hepsini eler. TOBO da aynı nedenle çok nadir geçer. GF1 sonuçları fiilen yalnız yükselen üçgeni ölçüyor; işlem sayısının düşüklüğü buradan. Bunu koddan türettim, işlem dökümünden saymadım.
2. **IN1 kendi kendini kilitliyor.** RSI < 35 ve daha düşük dip isterken üst zaman diliminin "aşağı olmamasını" istiyor; bu ikisi nadiren birlikte olur. Üstüne 0,3 ATR içinde seviye, hacim ve ardışık pivot şartı geliyor. 19 çift x 4,5 yılda 2 işlem.
3. **MF1'in mum şekillerinde kazanç yok.** Teyitli ya da teyitsiz, her zaman diliminde eksi; 1h'de rastgeleden belirgin kötü. Hacim şartı geniş, tükenmiş mumları seçip girişi geciktiriyor.
4. **MF1 seviye tanımı gevşek.** 1d'de "önceki gün dibi" formasyonun kendi mumu, yani şart kendiliğinden sağlanıyor. Delme derinliğinde alt sınır yok. Beş ayrı seviye ve sürekli kesilen VWAP ile bir seviyeye denk gelmek neredeyse kesin.
5. **MF1 hedefi zaman stopuyla uyumsuz.** Hedefin üst sınırı yok ama zaman stopu 16 mum. Hedefe varış yalnız %14-21, zaman çıkışı %23-31. Uzak hedefli işlemler "stop ya da süre" bahsine dönüyor.
6. **Mevcut kollarla çakışma.** GF1 B girişi B1 ile (kırılım + geri test), üçgen + daralma S1 ile, GF1 A girişi TF1 ile aynı işi yapıyor. MF1 çekiç ve IN1 düşük dip dönüşü F1 (süpürme + geri alma) ile örtüşüyor. Yeni kol artıya geçse bile mevcut kola göre ek katkı ayrıca gösterilmeli.

## Uygulanacak degisiklikler (numarali, her biri: ne, neden, nasil; uygulayici buna gore kodlayacak)

1. **Kapat: üç kolun 15m'si, MF1 1h, IN1 1d.**
   - Neden: 15m'de rastgele giriş bile -0,14 ile -0,30 R ve kollar bunu aşamıyor. MF1 1h 1135 işlemle 5 yılın 5'inde eksi ve rastgeleden kötü. IN1 1d teyitsiz bile 2 işlem üretiyor.
   - Nasıl: `calistir.py` içinde kol → izinli zaman dilimi tablosu koy: MF1 4h/1d, GF1 1h/4h/1d, IN1 1h/4h. Kapatılanlar hesaplanmasın. `kol_sinyalleri.py` içindeki 15m özel dalları sil.

2. **GF1 stop tanımını düzelt (mantık hatası).**
   - Neden: Mevcut stop/hedef/rr üçlüsü ikili dibi matematiksel olarak imkânsız kılıyor (zaaf 1).
   - Nasıl: Stop = boyun − 1 ATR (giriş mumunun ATR'si). Bu, tasarımdaki "boyun altında kapanış kurulumu iptal eder" kuralıyla ve motordaki TF1 stop kalıbıyla tutarlı. "Risk > 3 ATR ise işlem yok" şartını kaldır. Hedef ve rr ≥ 1,5 aynı kalsın. B girişindeki geri testi boyuna göre ölç: `l[t] <= boyun + 0,3 ATR` yerine `l[t] <= boyun`. Çıktıya şekil türüne göre (ikili dip / TOBO / üçgen) işlem sayısı ve ort R ekle.

3. **IN1'i yapısal olarak gevşet; yine yetmezse kapat.**
   - Neden: Zaaf 2. Teyitlerin katkısı ölçülemiyor ve kod tasarımdan daha dar.
   - Nasıl: İkinci dip pivotunu yalnız bir öncekiyle değil, 5-40 mum gerideki her onaylı dip pivotuyla eşle; koşulu sağlayan en yakın olanı al. Seviye ve hacim teyitlerini IN1'den çıkar. Üst ZD, fonlama vetosu ve maliyet tabanı kalsın. Kapatma kuralını şimdiden yaz: tur 2'de 1h + 4h toplamı 50 işlemin altındaysa IN1 tümüyle kapanır, başka gevşetme yapılmaz.

4. **MF1'den hacim ve üst ZD teyidini at (4h ve 1d).**
   - Neden: İkisi de dört zaman diliminin dördünde ort R'yi kötüleştiriyor ve işlemlerin çoğunu siliyor.
   - Nasıl: `mf1_sinyal` içinde `zd` ve `hacim` koşullarını kaldır, `UYGULANAN["MF1"]` listesinden çıkar. Fonlama, seviye ve maliyet kalsın. Eşik değiştirme yok.

5. **MF1 seviye ve hedef tanımını düzelt.**
   - Neden: Zaaf 4 ve 5.
   - Nasıl (seviye): Seviye, formasyonun ilk mumundan önce bilinen değer olsun: yutan için t−2, çekiç için t−1, yıldız için t−3 anındaki seviye dizisi. 1d'de "önceki gün dibi"ni listeden çıkar; önceki hafta dibi ve kendi pivotu kalsın. Delme için alt sınır koy: dip seviyenin en çok 1 ATR altında. Çıktıya seviye türüne göre döküm ekle.
   - Nasıl (hedef): Hedef = en yakın karşı seviye ile giriş + 3R'den yakın olanı. 3R önceden sabitlenmiş tek değerdir; taranmayacak, sonuca göre değiştirilmeyecek. rr ≥ 1,5 kalsın.

6. **Ölçümü sağlamlaştır (rastgele taban ve simülasyon).**
   - Neden: Kod denetimindeki 1-4. kusurlar. Tur 2'de "rastgeleden iyi mi" sorusu güvenilir yanıtlanmalı.
   - Nasıl (rastgele taban): Her gerçek işlem için aynı çift, aynı yön ve aynı takvim yılından 200 rastgele giriş çek. Gerçek tarafın standart hatasını da kaydet ve z = fark / √(se_gerçek² + se_rastgele²) raporla. 50 işlemin altında z yerine "yetersiz" yaz. Rastgele ve gerçek girişlere aynı ısınma sınırını (ilk 250 mum yok) uygula.
   - Nasıl (üst ZD): EMA'sı hazır olmayan üst zaman dilimini "yatay" değil "geçersiz" say.
   - Nasıl (simülasyon): Fonlamayı çıkış mumunun kapanışına kadar say; stop/hedef çıkışında da mum sonuna kadar saymak temkinli taraftır. Giriş açılışındaki risk %0,6'nın altındaysa işlemi alma. Tutma penceresinde mum boşluğu varsa ya da veri bitmeden zaman stopuna ulaşılamıyorsa işlemi sayma.