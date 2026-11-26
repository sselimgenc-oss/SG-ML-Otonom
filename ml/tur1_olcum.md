# Tur 1 ölçüm raporu
Üretim: 2026-11-26T05:11:01Z · kapanmış işlem n = 110 · yalnız ölçüm, bot değişmez.

## 1. Basit rakip kıyası
- Bizim: n=110, toplam -15,06 R, ort -0,137 R/işlem
- Rastgele giriş (n=110, 500 sim.): ort toplam -8,79 R; bizim yüzdelik **38.4**, p=0.617
  - Yan yana, eski sabit masrafla (k2: 2/5/5 bp): ort toplam -3,82 R, bizim yüzdelik 33.2, p=0.669
  - Masraf: kâğıt modeli (config kayma/komisyon); fonlama rakipte yok (k2 taşımaz), yani rakip bizden biraz ucuz.
- Al-tut (gerçek, long, eşit ağırlık, 35/35 enstrüman, 2026-11-18 → 2026-11-26, masrafsız): ort getiri %-3,1; bizim net/kasa başlangıcı %-8,9 (farklı risk büyüklüğü, doğrudan kıyas değil)
- Hep long (aynı giriş zamanları, tahmin): toplam -1,27 R, ort -0,012 R
- Hep short (aynı giriş zamanları, tahmin): toplam -14,87 R, ort -0,135 R
- Hiçbir şey yapmamak: 0 R

## 2. Gecikme / masraf dayanıklılığı
- Gerçek net: -15,06 R (n=110)
- Giriş 1_mum gecikmeli: n=110, net -12,71 R, kalan oran —; durum {'ok': 100, 'kacirildi': 10}
- Giriş 2_mum gecikmeli: n=110, net -12,06 R, kalan oran —; durum {'kacirildi': 14, 'ok': 96}
- Masraf x1.5: net -20,82 R, kalan oran —
- Masraf x2.0: net -26,58 R, kalan oran —
- 15 dk mum saati kayması: **tam ölçülemedi** (sinyali yeniden üretmek gerekir). Vekil: giriş 15 dk gecikmeli n=110, net -15,59 R

## 3. Şans / kuyruk
- n=110, 10000 karıştırma
- Maks düşüş p5/p50/p95: %10.3 / %14.0 / %19.0; batış olasılığı (kasa <= %85): %12.79
- Blok örnekleme (ortalama blok 6.9 işlem, 10000 çekim, n=110) maks düşüş p5/p50/p95: %7.8 / %18.4 / %36.0; batış olasılığı: %51.19 (kayıp kümelenmesini korur; karıştırmayla yan yana)
- En iyi 1 işlem çıkarılırsa net: -19,29 R
- En iyi 2 işlem çıkarılırsa net: -22,00 R
- En iyi 5 işlem çıkarılırsa net: -28,96 R

## 4. Canlıya geçiş şartları
- **FAIL** En az 300 kapanmış işlem — n = 110
- **FAIL** Masraf sonrası net > 0 ve güven alt sınırı > 0 — net = -15.06 R; ort = -0.137 R; alt sınır = -0.478
- **FAIL** En az 2 rejimde pozitif (rejim başına >= 30 işlem ve gün kümeli güven alt sınırı > 0) — 0 rejim pozitif []; rejim n: range=3, trend_down=91, trend_up=9, unclear=7; alt sınır: trend_down=-0.557
- **FAIL** Rastgele giriş yüzdeliği >= 90 — yüzdelik = 38.4
- **FAIL** Masraf x1.5 altında net > 0 — net = -20.82 R
- **FAIL** Monte Carlo %95 maks düşüş <= %15 (sermaye mandalı oranından türetilir: 1 - 0.85; karıştırma ve blok örneklemenin kötüsü) — p95 = %36.0 (n=110)
- **BİLGİ** Çoklu deneme: deflated Sharpe ve PBO (BİLGİ, geçme şartı değil) — DSR = 0.00 (kol sayısı 23); hesaplanamadı (9 gün < 32); n=110

## 5. Yön denetimi
- long: n=16, net -1,95 R
- short: n=94, net -13,11 R

## 6. Kayıp kümeleri
- 67 kayıp / 110 işlem, 49 küme
- IN1-RSI2@15m · trend_down · short · kripto · 16-20 UTC: 6 kayıp, -4,91 R
- F1@15m · trend_down · short · kripto · 08-12 UTC: 3 kayıp, -3,37 R
- M1@15m · trend_down · short · kripto · 20-24 UTC: 3 kayıp, -2,43 R
- H2@15m · trend_down · short · kripto · 00-04 UTC: 2 kayıp, -2,13 R (az örnek)
- T1@1h · trend_down · short · kripto · 00-04 UTC: 2 kayıp, -2,05 R (az örnek)

## 7. Başlangıç noktasına göre en kötü düşüş (n=110)
- Her işlemden başlasaydık (110 başlangıç): en kötü düşüş %24,9 (başlangıç: işlem 54, 2026-11-21); medyan %7,4; en iyi %0,4; ilk işlemden başlayan %21,5

## 8. Kazanç/kayıp koşu testi (n=110)
- Kazanç 43 / kayıp 67; koşu 42 (beklenen 53.4), z=-2.29, p=0.022: kümeleniyor (kosu az)

## 9. Zaman dilimi × masraf (n=110)
- 15m: n=77, brüt -2,07 R, masraf -9,60 R, net -11,66 R, masraf/brüt —
- 1h: n=27, brüt +1,50 R, masraf -1,74 R, net -0,25 R, masraf/brüt %116 (yetersiz örnek)
- 4h: n=5, brüt -1,99 R, masraf -0,16 R, net -2,15 R, masraf/brüt — (yetersiz örnek)
- 1d: n=1, brüt -0,97 R, masraf -0,03 R, net -1,00 R, masraf/brüt — (yetersiz örnek)

## 10. Giriş/çıkış verimliliği (n=110, MFE/MAE olan 110)
- Çıkış verimi %30,3 (n=110); giriş verimi %48,0 (n=110); ort geri verme +1,17 R; kazananlarda gerçekleşen/işlem içi en iyi %53,1 (n=47)

## 11. Düşüşten toparlanma süresi (n=110)
- En uzun düşüş: 84 işlem, 4.6 gün (hâlâ sürüyor)
- Şu an: zirvenin altında, 84 işlem, 4.6 gündür
