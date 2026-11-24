# Tur 1 ölçüm raporu
Üretim: 2026-11-24T05:10:39Z · kapanmış işlem n = 62 · yalnız ölçüm, bot değişmez.

## 1. Basit rakip kıyası
- Bizim: n=62, toplam -1,72 R, ort -0,028 R/işlem
- Rastgele giriş (n=62, 500 sim.): ort toplam +5,82 R; bizim yüzdelik **37.6**, p=0.625
  - Yan yana, eski sabit masrafla (k2: 2/5/5 bp): ort toplam +7,85 R, bizim yüzdelik 33.0, p=0.671
  - Masraf: kâğıt modeli (config kayma/komisyon); fonlama rakipte yok (k2 taşımaz), yani rakip bizden biraz ucuz.
- Al-tut (gerçek, long, eşit ağırlık, 29/29 enstrüman, 2026-11-18 → 2026-11-24, masrafsız): ort getiri %-3,7; bizim net/kasa başlangıcı %-1,9 (farklı risk büyüklüğü, doğrudan kıyas değil)
- Hep long (aynı giriş zamanları, tahmin): toplam -8,34 R, ort -0,135 R
- Hep short (aynı giriş zamanları, tahmin): toplam -1,62 R, ort -0,026 R
- Hiçbir şey yapmamak: 0 R

## 2. Gecikme / masraf dayanıklılığı
- Gerçek net: -1,72 R (n=62)
- Giriş 1_mum gecikmeli: n=61, net -2,19 R, kalan oran —; durum {'ok': 58, 'kacirildi': 3, 'veri_yok': 1}; veri yok (zaman dilimi): 1d=1
- Giriş 2_mum gecikmeli: n=61, net -2,95 R, kalan oran —; durum {'ok': 57, 'kacirildi': 4, 'veri_yok': 1}; veri yok (zaman dilimi): 1d=1
- Masraf x1.5: net -4,93 R, kalan oran —
- Masraf x2.0: net -8,14 R, kalan oran —
- 15 dk mum saati kayması: **tam ölçülemedi** (sinyali yeniden üretmek gerekir). Vekil: giriş 15 dk gecikmeli n=62, net -3,72 R

## 3. Şans / kuyruk
- n=62, 10000 karıştırma
- Maks düşüş p5/p50/p95: %6.1 / %9.1 / %13.5; batış olasılığı (kasa <= %85): %0.26
- Blok örnekleme (ortalama blok 5.9 işlem, 10000 çekim, n=62) maks düşüş p5/p50/p95: %5.2 / %13.5 / %27.7; batış olasılığı: %30.48 (kayıp kümelenmesini korur; karıştırmayla yan yana)
- En iyi 1 işlem çıkarılırsa net: -5,95 R
- En iyi 2 işlem çıkarılırsa net: -8,66 R
- En iyi 5 işlem çıkarılırsa net: -15,45 R

## 4. Canlıya geçiş şartları
- **FAIL** En az 300 kapanmış işlem — n = 62
- **FAIL** Masraf sonrası net > 0 ve güven alt sınırı > 0 — net = -1.72 R; ort = -0.028 R; alt sınır = hesaplanamadı (gün sayısı 7 < 8)
- **FAIL** En az 2 rejimde pozitif (rejim başına >= 30 işlem ve gün kümeli güven alt sınırı > 0) — 0 rejim pozitif []; rejim n: range=3, trend_down=54, trend_up=3, unclear=2; alt sınır: trend_down=hesaplanamadı
- **FAIL** Rastgele giriş yüzdeliği >= 90 — yüzdelik = 37.6
- **FAIL** Masraf x1.5 altında net > 0 — net = -4.93 R
- **FAIL** Monte Carlo %95 maks düşüş <= %15 (sermaye mandalı oranından türetilir: 1 - 0.85; karıştırma ve blok örneklemenin kötüsü) — p95 = %27.7 (n=62)
- **BİLGİ** Çoklu deneme: deflated Sharpe ve PBO (BİLGİ, geçme şartı değil) — DSR = 0.00 (kol sayısı 15); hesaplanamadı (7 gün < 32); n=62

## 5. Yön denetimi
- long: n=7, net -1,46 R
- short: n=55, net -0,26 R
- ML filtre long: ret 3 / girildi 8, ret oranı +0,27
- ML filtre short: ret 56 / girildi 61, ret oranı +0,48
- Yön özelliği (f_side_sign / side_long) önemi: ok; M1@15m.json: ozellik_listede_yok; M1@15m.prev.json: ozellik_listede_yok; M1@1d.json: ozellik_listede_yok; M1@1d.prev.json: ozellik_listede_yok; M1@1h.json: ozellik_listede_yok

## 6. Kayıp kümeleri
- 35 kayıp / 62 işlem, 28 küme
- F1@15m · trend_down · short · kripto · 08-12 UTC: 2 kayıp, -2,14 R (az örnek)
- T1@1h · trend_down · short · kripto · 00-04 UTC: 2 kayıp, -2,05 R (az örnek)
- S1@15m · trend_down · short · kripto · 08-12 UTC: 2 kayıp, -2,00 R (az örnek)
- M1@1h · trend_down · short · kripto · 08-12 UTC: 2 kayıp, -1,98 R (az örnek)
- S1@15m · trend_up · long · kripto · 08-12 UTC: 2 kayıp, -1,50 R (az örnek)

## Üst lig (HB1, DL1; 32 kolun dışında ayrı karne)
- HB1: kol henüz yok
- DL1: kol henüz yok

## 7. Başlangıç noktasına göre en kötü düşüş (n=62)
- Her işlemden başlasaydık (62 başlangıç): en kötü düşüş %18,9 (başlangıç: işlem 54, 2026-11-21); medyan %15,9; en iyi %0,0; ilk işlemden başlayan %16,3

## 8. Kazanç/kayıp koşu testi (n=62)
- Kazanç 27 / kayıp 35; koşu 25 (beklenen 31.5), z=-1.69, p=0.091: kümeleniyor (kosu az)

## 9. Zaman dilimi × masraf (n=62)
- 15m: n=38, brüt +3,60 R, masraf -5,01 R, net -1,41 R, masraf/brüt %139
- 1h: n=20, brüt +2,02 R, masraf -1,29 R, net +0,74 R, masraf/brüt %64 (yetersiz örnek)
- 4h: n=3, brüt +0,05 R, masraf -0,10 R, net -0,04 R, masraf/brüt %186 (yetersiz örnek)
- 1d: n=1, brüt -0,97 R, masraf -0,03 R, net -1,00 R, masraf/brüt — (yetersiz örnek)

## 10. Giriş/çıkış verimliliği (n=62, MFE/MAE olan 62)
- Çıkış verimi %31,7 (n=62); giriş verimi %52,5 (n=62); ort geri verme +1,28 R; kazananlarda gerçekleşen/işlem içi en iyi %48,1 (n=30)

## 11. Düşüşten toparlanma süresi (n=62)
- En uzun düşüş: 36 işlem, 2.7 gün (hâlâ sürüyor)
- Şu an: zirvenin altında, 36 işlem, 2.7 gündür

## 12. Süzgeç puanı kalibrasyonu (n=0 puanlı / 62 işlem) (yetersiz örnek)
- veri yok (puanlı işlem yok)
