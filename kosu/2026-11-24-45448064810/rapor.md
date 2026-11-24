# Yeni kollar geri test raporu

## Kisa sonuc

- **Hiçbir kol "kağıda al" kararını hak etmiyor.** Sağlam kazanç gösteren hücre yok.
- **IN1 1h tek umut veren hücre.** Kilitli dönemde masraf sonrası +0,112 R (41 işlem) ve kuralınızın üç şartını kâğıt üzerinde geçiyor. Ama geliştirmede sonuç fiilen sıfırdı (+0,002 R) ve 2026'da ekside (-11,3 R). Kararım: bekle.
- **MF1 (mum) işe yaramıyor.** 4h'de her dönemde ekside. 1d'de sıfıra yakın ama ekside ve rastgele girişten iyi değil.
- **GF1 (grafik formasyonu) işe yaramıyor.** Kilitli dönemde üç zaman diliminde de ekside. Tur 1'deki 4h artısı az işlemden doğan bir yanılsamaydı.
- **15m'de üç kol da tur 1'de kapandı.** Masraf tek başına kazancı yiyor.

## Kol x zaman dilimi

R = işlem başına ortalama net sonuç (ücret, kayma ve fonlama düşülmüş). Parantez içi işlem sayısıdır.

| Kol | ZD | Tur1 ort R | Tur2 ort R | Kilitli ort R | Kilitli işlem | Karar |
|---|---|---|---|---|---|---|
| MF1 | 15m | -0,249 (577) | kapatıldı | ölçülmedi | – | Kapat |
| MF1 | 1h | -0,195 (1135) | kapatıldı | ölçülmedi | – | Kapat |
| MF1 | 4h | -0,109 (430) | -0,056 (3300) | -0,112 | 1714 | Kapat |
| MF1 | 1d | -0,169 (43) | -0,017 (459) | -0,026 | 193 | Kapat |
| GF1 | 15m | -0,278 (145) | kapatıldı | ölçülmedi | – | Kapat |
| GF1 | 1h | -0,160 (144) | -0,117 (1032) | -0,153 | 433 | Kapat |
| GF1 | 4h | +0,139 (35) | -0,006 (258) | -0,243 | 121 | Kapat |
| GF1 | 1d | +0,073 (10) | -0,110 (56) | -0,557 | 30 | Kapat |
| IN1 | 15m | işlem yok | kapatıldı | ölçülmedi | – | Kapat |
| IN1 | 1h | -1,161 (1) | +0,002 (47) | +0,112 | 41 | Bekle |
| IN1 | 4h | -1,022 (1) | -0,033 (80) | +0,035 | 28 | Bekle |
| IN1 | 1d | işlem yok | kapatıldı | ölçülmedi | – | Kapat |

Karar gerekçeleri:

- **IN1 1h:** Bekle dememin üç nedeni var.
  - Geliştirmedeki +0,002 R bir kazanç değil, sıfırdır; "aynı yön" şartı ancak kâğıt üzerinde sağlanıyor.
  - Kilitli dönemin artısı 2025'ten geliyor (+15,9 R); 2026 ekside (-11,3 R).
  - En büyük düşüş 14,0 R, toplam kazanç ise yalnız 4,6 R.
- **IN1 4h:** Kilitli dönemde 28 işlem var, eşik 30. Geliştirmede yön eksiydi. Şartlar sağlanmıyor.
- **MF1 1d:** Zarar küçük ama iki dönemde de eksi (toplam 652 işlem) ve rastgele girişten iyi değil.

## Ne degisti ve ise yaradi mi

| Değişiklik | Sonuç | İşe yaradı mı |
|---|---|---|
| 15m, MF1 1h ve IN1 1d kapatıldı | Zarar eden hücreler ölçümden çıktı | Evet, doğru temizlik |
| GF1 stop tanımı düzeltildi | İkili dip artık işlem açıyor; işlem sayısı 1h'de 144'ten 1032'ye çıktı | Hata düzeldi, kazanç gelmedi |
| IN1 gevşetildi (seviye ve hacim şartı kalktı) | İşlem 2'den 127'ye çıktı | Evet, kol artık ölçülebiliyor |
| MF1'den hacim ve üst ZD şartı atıldı | 4h'de zarar -0,109'dan -0,056'ya indi, kilitli dönemde -0,112'ye geri döndü | Hayır, iyileşme kalıcı değil |
| MF1 seviye ve hedef düzeltildi | 1d'de zarar -0,169'dan -0,017'ye indi | Kısmen; zarar azaldı ama kazanca dönmedi |
| Rastgele kıyas güçlendirildi (işlem başına 200 çekiliş) | "Rastgeleden iyi mi" sorusu artık güvenilir | Evet; cevap her hücrede "hayır" ya da "yetersiz" |

Tur 2 kolları kazandırır hale getirmedi, ama ölçümü dürüstleştirdi. GF1 4h bunun en açık örneği: 35 işlemde +0,139 R görünüyordu, 258 işlemde sıfıra indi, kilitli dönemde -0,243 R oldu.

## Kalan zaaflar

- **MF1'in mum şekillerinde kazanç yok.** Hiç şartsız hali de şartlı hali de ekside. Seviye şartı işlemi yarıya indiriyor ama sonucu değiştirmiyor.
- **GF1 rastgele girişten kötü.** Kilitli 4h'de rastgele giriş +0,079 R verirken GF1 -0,243 R verdi.
- **IN1'in sonucu tek bir şarta bağlı.** Üst zaman dilimi şartı kapatılınca kilitli 1h -0,167 R'ye düşüyor (430 işlem). Bu şart iki dönemde de aynı yönde yardım ediyor, bu olumlu; ama kol onsuz zarar ediyor.
- **IN1 çok az işlem üretiyor.** 43 çiftte yaklaşık 17 ayda 1h'de 41, 4h'de 28 işlem var. Karar vermek uzun sürer.
- **Alt kırılımlar tutmuyor.** MF1 1d'nin VWAP seviyesi geliştirmede +0,107 R idi, kilitli dönemde -0,021 R oldu. Bu tür alt dilimlerden kol kurtarılmamalı.
- **Mevcut kollarla çakışma ölçülmedi.** Tur 1 analizi GF1'in B1, S1 ve TF1 ile, MF1 ve IN1'in F1 ile örtüştüğünü yazmıştı. Ek katkı hiç test edilmedi.

## Dürüst uyarilar

- **Örneklem:** IN1'in iki hücresinde de işlem 50'nin altında; rastgele kıyas "yetersiz" çıkıyor. +0,112 R şans eseri olabilir.
- **Aşırı uyum:** Tur 2 kuralları tur 1 sonuçlarına bakılarak yazıldı; geliştirme rakamları bu yüzden iyimserdir. Kilitli dönem tek temiz sınavdır ve bir kez kullanıldı. Yeni bir düzeltme yapılırsa bu dönem artık "bakılmamış" sayılmaz.
- **Evren farkı:** Geliştirme 19 kripto çiftiyle yapıldı. Kilitli dönemde 43 çift var; hisse ve emtia ilk kez burada girdi. İki dönem birebir kıyaslanamaz.
- **Tek-işlem kuralı ve öncelik:** Bu test her kolu tek başına, her sinyali ayrı işlem sayarak ölçtü. Kâğıtta aynı çiftte tek işlem açılır ve öncelikli kollar sinyali önce alır. Yeni kolun gerçek işlem sayısı daha düşük, sonucu farklı olur.
- **Motorun tam simülasyonu değil:** Pozisyon büyüklüğü, portföy sınırları, emir gecikmesi ve kollar arası etkileşim yok. Rakamlar yalnız "sinyalde kazanç var mı" sorusunu yanıtlar.
- **Benim sınırım:** Yalnız özet dosyalarını okudum. Kodu denetlemedim, testleri yeniden çalıştırmadım. Kod denetimi tur 1 analizine dayanıyor.

## Maliyet

| Adım | Tutar ($) |
|---|---|
| 1. Kodlama | 1,62 |
| 2. Tur 1 analizi | 1,65 |
| 3. Tur 2 düzeltme | 0,98 |
| **Toplam (maliyet.txt)** | **4,25** |

Bu rapor adımı `maliyet.txt` içinde yok; yaklaşık 0,3 $ tuttu. Onunla birlikte toplam yaklaşık 4,55 $.