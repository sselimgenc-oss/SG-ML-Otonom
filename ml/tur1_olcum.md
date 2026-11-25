# Tur 1 ölçüm raporu
Üretim: 2026-11-25T05:11:00Z · kapanmış işlem n = 83 · yalnız ölçüm, bot değişmez.

## 1. Basit rakip kıyası
- Bizim: n=83, toplam -6,03 R, ort -0,073 R/işlem
- Rastgele giriş (n=83, 500 sim.): ort toplam -5,19 R; bizim yüzdelik **47.8**, p=0.523
  - Yan yana, eski sabit masrafla (k2: 2/5/5 bp): ort toplam -0,77 R, bizim yüzdelik 38.2, p=0.619
  - Masraf: kâğıt modeli (config kayma/komisyon); fonlama rakipte yok (k2 taşımaz), yani rakip bizden biraz ucuz.
- Al-tut (gerçek, long, eşit ağırlık, 32/32 enstrüman, 2026-11-18 → 2026-11-25, masrafsız): ort getiri %-5,3; bizim net/kasa başlangıcı %-4,4 (farklı risk büyüklüğü, doğrudan kıyas değil)
- Hep long (aynı giriş zamanları, tahmin): toplam -7,63 R, ort -0,092 R
- Hep short (aynı giriş zamanları, tahmin): toplam -5,30 R, ort -0,064 R
- Hiçbir şey yapmamak: 0 R

## 2. Gecikme / masraf dayanıklılığı
- Gerçek net: -6,03 R (n=83)
- Giriş 1_mum gecikmeli: n=83, net -5,08 R, kalan oran —; durum {'ok': 77, 'kacirildi': 6}
- Giriş 2_mum gecikmeli: n=82, net -7,72 R, kalan oran —; durum {'ok': 75, 'kacirildi': 7, 'veri_yok': 1}; veri yok (zaman dilimi): 1d=1
- Masraf x1.5: net -10,79 R, kalan oran —
- Masraf x2.0: net -15,56 R, kalan oran —
- 15 dk mum saati kayması: **tam ölçülemedi** (sinyali yeniden üretmek gerekir). Vekil: giriş 15 dk gecikmeli n=83, net -6,75 R

## 3. Şans / kuyruk
- n=83, 10000 karıştırma
- Maks düşüş p5/p50/p95: %7.5 / %10.9 / %15.5; batış olasılığı (kasa <= %85): %2.06
- Blok örnekleme (ortalama blok 6.4 işlem, 10000 çekim, n=83) maks düşüş p5/p50/p95: %6.0 / %15.1 / %31.2; batış olasılığı: %38.54 (kayıp kümelenmesini korur; karıştırmayla yan yana)
- En iyi 1 işlem çıkarılırsa net: -10,26 R
- En iyi 2 işlem çıkarılırsa net: -12,97 R
- En iyi 5 işlem çıkarılırsa net: -19,93 R

## 4. Canlıya geçiş şartları
- **FAIL** En az 300 kapanmış işlem — n = 83
- **FAIL** Masraf sonrası net > 0 ve güven alt sınırı > 0 — net = -6.03 R; ort = -0.073 R; alt sınır = hesaplanamadı (gün sayısı 7 < 8)
- **FAIL** En az 2 rejimde pozitif (rejim başına >= 30 işlem ve gün kümeli güven alt sınırı > 0) — 0 rejim pozitif []; rejim n: range=3, trend_down=69, trend_up=7, unclear=4; alt sınır: trend_down=hesaplanamadı
- **FAIL** Rastgele giriş yüzdeliği >= 90 — yüzdelik = 47.8
- **FAIL** Masraf x1.5 altında net > 0 — net = -10.79 R
- **FAIL** Monte Carlo %95 maks düşüş <= %15 (sermaye mandalı oranından türetilir: 1 - 0.85; karıştırma ve blok örneklemenin kötüsü) — p95 = %31.2 (n=83)
- **BİLGİ** Çoklu deneme: deflated Sharpe ve PBO (BİLGİ, geçme şartı değil) — DSR = 0.00 (kol sayısı 16); hesaplanamadı (7 gün < 32); n=83

## 5. Yön denetimi
- long: n=13, net -2,08 R
- short: n=70, net -3,95 R

## 6. Kayıp kümeleri
- 48 kayıp / 83 işlem, 37 küme
- F1@15m · trend_down · short · kripto · 08-12 UTC: 3 kayıp, -3,37 R
- M1@15m · trend_down · short · kripto · 20-24 UTC: 3 kayıp, -2,43 R
- T1@1h · trend_down · short · kripto · 00-04 UTC: 2 kayıp, -2,05 R (az örnek)
- S1@15m · trend_down · short · kripto · 08-12 UTC: 2 kayıp, -2,00 R (az örnek)
- M1@1h · trend_down · short · kripto · 08-12 UTC: 2 kayıp, -1,98 R (az örnek)

## Üst lig (HB1, DL1; 32 kolun dışında ayrı karne)
- HB1: kol henüz yok
- DL1: kol henüz yok

## 7. Başlangıç noktasına göre en kötü düşüş (n=83)
- Her işlemden başlasaydık (83 başlangıç): en kötü düşüş %21,6 (başlangıç: işlem 54, 2026-11-21); medyan %12,4; en iyi %0,4; ilk işlemden başlayan %18,6

## 8. Kazanç/kayıp koşu testi (n=83)
- Kazanç 35 / kayıp 48; koşu 32 (beklenen 41.5), z=-2.15, p=0.032: kümeleniyor (kosu az)

## 9. Zaman dilimi × masraf (n=83)
- 15m: n=58, brüt +3,45 R, masraf -8,07 R, net -4,62 R, masraf/brüt %234
- 1h: n=20, brüt +2,02 R, masraf -1,29 R, net +0,74 R, masraf/brüt %64 (yetersiz örnek)
- 4h: n=4, brüt -1,00 R, masraf -0,15 R, net -1,14 R, masraf/brüt — (yetersiz örnek)
- 1d: n=1, brüt -0,97 R, masraf -0,03 R, net -1,00 R, masraf/brüt — (yetersiz örnek)

## 10. Giriş/çıkış verimliliği (n=83, MFE/MAE olan 83)
- Çıkış verimi %30,7 (n=83); giriş verimi %51,5 (n=83); ort geri verme +1,24 R; kazananlarda gerçekleşen/işlem içi en iyi %49,5 (n=39)

## 11. Düşüşten toparlanma süresi (n=83)
- En uzun düşüş: 57 işlem, 3.7 gün (hâlâ sürüyor)
- Şu an: zirvenin altında, 57 işlem, 3.7 gündür
