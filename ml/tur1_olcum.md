# Tur 1 ölçüm raporu
Üretim: 2026-11-27T05:10:38Z · kapanmış işlem n = 3 · yalnız ölçüm, bot değişmez.
**yetersiz örnek (n < 30): aşağıdaki sayılar yalnız bilgidir, sonuç çıkarılamaz.**

## 1. Basit rakip kıyası
- Bizim: n=3, toplam -1,65 R, ort -0,549 R/işlem
- Rastgele giriş (n=3, 500 sim.): ort toplam +0,50 R; bizim yüzdelik **26.0**, p=0.741 (yetersiz örnek)
  - Yan yana, eski sabit masrafla (k2: 2/5/5 bp): ort toplam +0,50 R, bizim yüzdelik 26.0, p=0.741
  - Masraf: kâğıt modeli (config kayma/komisyon); fonlama rakipte yok (k2 taşımaz), yani rakip bizden biraz ucuz.
- Al-tut (gerçek, long, eşit ağırlık, 3/3 enstrüman, 2026-11-26 → 2026-11-27, masrafsız): ort getiri %+0,9; bizim net/kasa başlangıcı %-1,2 (farklı risk büyüklüğü, doğrudan kıyas değil)
- Hep long (aynı giriş zamanları, tahmin): toplam +1,00 R, ort +0,333 R
- Hep short (aynı giriş zamanları, tahmin): toplam -1,65 R, ort -0,549 R
- Hiçbir şey yapmamak: 0 R

## 2. Gecikme / masraf dayanıklılığı
- Gerçek net: -1,65 R (n=3)
- Giriş 1_mum gecikmeli: n=3, net -1,67 R, kalan oran —; durum {'ok': 3}
- Giriş 2_mum gecikmeli: n=3, net -1,80 R, kalan oran —; durum {'ok': 2, 'kacirildi': 1}
- Masraf x1.5: net -1,81 R, kalan oran —
- Masraf x2.0: net -1,97 R, kalan oran —

## 3. Şans / kuyruk
- n=3 (yetersiz örnek), 10000 karıştırma
- Maks düşüş p5/p50/p95: %1.2 / %1.4 / %1.4; batış olasılığı (kasa <= %85): %0.00
- Blok örnekleme (ortalama blok 1.0 işlem, 10000 çekim, n=3) maks düşüş p5/p50/p95: %0.6 / %1.4 / %2.3; batış olasılığı: %0.00 (kayıp kümelenmesini korur; karıştırmayla yan yana)
- En iyi 1 işlem çıkarılırsa net: -1,92 R
- En iyi 2 işlem çıkarılırsa net: -0,96 R
- En iyi 5 işlem çıkarılırsa net: — R

## 4. Canlıya geçiş şartları (yetersiz örnek)
- **FAIL** En az 300 kapanmış işlem — n = 3
- **FAIL** Masraf sonrası net > 0 ve güven alt sınırı > 0 — net = -1.65 R; ort = -0.549 R; alt sınır = hesaplanamadı (gün sayısı 1 < 8)
- **FAIL** En az 2 rejimde pozitif (rejim başına >= 30 işlem ve gün kümeli güven alt sınırı > 0) — 0 rejim pozitif []; rejim n: trend_down=3; alt sınır: 
- **FAIL** Rastgele giriş yüzdeliği >= 90 — yüzdelik = 26.0
- **FAIL** Masraf x1.5 altında net > 0 — net = -1.81 R
- **PASS** Monte Carlo %95 maks düşüş <= %15 (sermaye mandalı oranından türetilir: 1 - 0.85; karıştırma ve blok örneklemenin kötüsü) — p95 = %2.3 (n=3)
- **BİLGİ** Çoklu deneme: deflated Sharpe ve PBO (BİLGİ, geçme şartı değil) — DSR = 0.06 (kol sayısı 3); hesaplanamadı (1 gün < 32); n=3

## 5. Yön denetimi (yetersiz örnek)
- short: n=3, net -1,65 R

## 6. Kayıp kümeleri (yetersiz örnek)
- 2 kayıp / 3 işlem, 2 küme
- T1@1h · trend_down · short · kripto · 20-24 UTC: 1 kayıp, -0,96 R (az örnek)
- T1-GERI3@1h · trend_down · short · kripto · 20-24 UTC: 1 kayıp, -0,96 R (az örnek)

## 7. Başlangıç noktasına göre en kötü düşüş (n=3) (yetersiz örnek)
- Her işlemden başlasaydık (3 başlangıç): en kötü düşüş %1,4 (başlangıç: işlem 4, 2026-11-26); medyan %1,4; en iyi %0,6; ilk işlemden başlayan %1,4

## 8. Kazanç/kayıp koşu testi (n=3) (yetersiz örnek)
- yetersiz örnek: n=3 (en az 30); test yapılmadı

## 9. Zaman dilimi × masraf (n=3) (yetersiz örnek)
- 1h: n=3, brüt -1,32 R, masraf -0,32 R, net -1,65 R, masraf/brüt — (yetersiz örnek)

## 10. Giriş/çıkış verimliliği (n=3, MFE/MAE olan 3) (yetersiz örnek)
- Çıkış verimi %37,8 (n=3); giriş verimi %35,4 (n=3); ort geri verme +0,76 R; kazananlarda gerçekleşen/işlem içi en iyi %65,5 (n=1)

## 11. Düşüşten toparlanma süresi (n=3) (yetersiz örnek)
- En uzun düşüş: 2 işlem, 0.2 gün (hâlâ sürüyor)
- Şu an: zirvenin altında, 2 işlem, 0.2 gündür
