# Tur 1 ölçüm raporu
Üretim: 2026-11-28T05:10:52Z · kapanmış işlem n = 10 · yalnız ölçüm, bot değişmez.
**yetersiz örnek (n < 30): aşağıdaki sayılar yalnız bilgidir, sonuç çıkarılamaz.**

## 1. Basit rakip kıyası
- Bizim: n=10, toplam -0,75 R, ort -0,075 R/işlem
- Rastgele giriş (n=10, 500 sim.): ort toplam +6,06 R; bizim yüzdelik **12.4**, p=0.876 (yetersiz örnek)
  - Yan yana, eski sabit masrafla (k2: 2/5/5 bp): ort toplam +6,10 R, bizim yüzdelik 12.4, p=0.876
  - Masraf: kâğıt modeli (config kayma/komisyon); fonlama rakipte yok (k2 taşımaz), yani rakip bizden biraz ucuz.
- Al-tut (gerçek, long, eşit ağırlık, 6/6 enstrüman, 2026-11-26 → 2026-11-28, masrafsız): ort getiri %-1,0; bizim net/kasa başlangıcı %-0,4 (farklı risk büyüklüğü, doğrudan kıyas değil)
- Hep long (aynı giriş zamanları, tahmin): toplam -1,29 R, ort -0,129 R
- Hep short (aynı giriş zamanları, tahmin): toplam +1,18 R, ort +0,118 R
- Hiçbir şey yapmamak: 0 R

## 2. Gecikme / masraf dayanıklılığı
- Gerçek net: -0,75 R (n=10)
- Giriş 1_mum gecikmeli: n=10, net +0,66 R, kalan oran —; durum {'ok': 10}
- Giriş 2_mum gecikmeli: n=10, net +1,33 R, kalan oran —; durum {'ok': 6, 'kacirildi': 4}
- Masraf x1.5: net -1,11 R, kalan oran —
- Masraf x2.0: net -1,48 R, kalan oran —

## 3. Şans / kuyruk
- n=10 (yetersiz örnek), 10000 karıştırma
- Maks düşüş p5/p50/p95: %1.8 / %2.7 / %4.2; batış olasılığı (kasa <= %85): %0.00
- Blok örnekleme (ortalama blok 1.0 işlem, 10000 çekim, n=10) maks düşüş p5/p50/p95: %1.0 / %2.8 / %6.0; batış olasılığı: %0.00 (kayıp kümelenmesini korur; karıştırmayla yan yana)
- En iyi 1 işlem çıkarılırsa net: -2,37 R
- En iyi 2 işlem çıkarılırsa net: -3,96 R
- En iyi 5 işlem çıkarılırsa net: -4,91 R

## 4. Canlıya geçiş şartları (yetersiz örnek)
- **FAIL** En az 300 kapanmış işlem — n = 10
- **FAIL** Masraf sonrası net > 0 ve güven alt sınırı > 0 — net = -0.75 R; ort = -0.075 R; alt sınır = hesaplanamadı (gün sayısı 2 < 8)
- **FAIL** En az 2 rejimde pozitif (rejim başına >= 30 işlem ve gün kümeli güven alt sınırı > 0) — 0 rejim pozitif []; rejim n: trend_down=9, trend_up=1; alt sınır: 
- **FAIL** Rastgele giriş yüzdeliği >= 90 — yüzdelik = 12.4
- **FAIL** Masraf x1.5 altında net > 0 — net = -1.11 R
- **PASS** Monte Carlo %95 maks düşüş <= %15 (sermaye mandalı oranından türetilir: 1 - 0.85; karıştırma ve blok örneklemenin kötüsü) — p95 = %6.0 (n=10)
- **BİLGİ** Çoklu deneme: deflated Sharpe ve PBO (BİLGİ, geçme şartı değil) — DSR = 0.00 (kol sayısı 8); hesaplanamadı (2 gün < 32); n=10

## 5. Yön denetimi (yetersiz örnek)
- long: n=1, net -1,04 R
- short: n=9, net +0,29 R

## 6. Kayıp kümeleri (yetersiz örnek)
- 6 kayıp / 10 işlem, 6 küme
- IN1-RSI2@1h · trend_up · long · kripto · 12-16 UTC: 1 kayıp, -1,04 R (az örnek)
- T1@4h · trend_down · short · kripto · 00-04 UTC: 1 kayıp, -0,98 R (az örnek)
- PA2-ONCEKI@1h · trend_down · short · kripto · 04-08 UTC: 1 kayıp, -0,97 R (az örnek)
- T1@1h · trend_down · short · kripto · 20-24 UTC: 1 kayıp, -0,96 R (az örnek)
- T1-GERI3@1h · trend_down · short · kripto · 20-24 UTC: 1 kayıp, -0,96 R (az örnek)

## 7. Başlangıç noktasına göre en kötü düşüş (n=10) (yetersiz örnek)
- Her işlemden başlasaydık (10 başlangıç): en kötü düşüş %3,4 (başlangıç: işlem 4, 2026-11-26); medyan %1,2; en iyi %0,1; ilk işlemden başlayan %3,4

## 8. Kazanç/kayıp koşu testi (n=10) (yetersiz örnek)
- yetersiz örnek: n=10 (en az 30); test yapılmadı

## 9. Zaman dilimi × masraf (n=10) (yetersiz örnek)
- 1h: n=7, brüt +0,18 R, masraf -0,61 R, net -0,44 R, masraf/brüt %348 (yetersiz örnek)
- 4h: n=3, brüt -0,19 R, masraf -0,12 R, net -0,31 R, masraf/brüt — (yetersiz örnek)

## 10. Giriş/çıkış verimliliği (n=10, MFE/MAE olan 10) (yetersiz örnek)
- Çıkış verimi %46,4 (n=10); giriş verimi %38,7 (n=10); ort geri verme +0,61 R; kazananlarda gerçekleşen/işlem içi en iyi %84,8 (n=4)

## 11. Düşüşten toparlanma süresi (n=10) (yetersiz örnek)
- En uzun düşüş: 7 işlem, 0.7 gün
- Şu an: zirvenin altında, 2 işlem, 0.3 gündür
