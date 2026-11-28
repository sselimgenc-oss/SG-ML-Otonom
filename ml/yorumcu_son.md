# Yorumcu raporu 2026-11-28

Yalnız yorum: bu rapor hiçbir ayarı değiştirmez, işlem açıp kapatmaz. Kapanmış işlem n = 10.

## Bulgular

- **Dün (2026-11-27):** Kapanan işlem n = 9, toplam_R = -0.62. Bu yetersiz örnek, o yüzden kesin sonuç çıkarmıyorum. R, bir işlemde riske edilen miktarı birim alan ölçüdür. Eksi R, o gün toplamda kayıp olduğunu gösterir.

- **Genel tablo:** Toplam kapanmış işlem n = 10, yani yetersiz örnek. Masraf sonrası net = -0.75 R, ort = -0.075 R. Güven alt sınırı hesaplanamadı, çünkü gün sayısı 2 < 8. Masraf x1.5 altında net = -1.11 R. Ölçüm tablosunda 300 işlem şartı var ve şu an n = 10. Monte Carlo (sonuçları rastgele karıştırarak olası en kötü düşüşü tahmin etme) p95 = %6.0 (n=10). Bu da yetersiz örnek.

- **Kararlar:** n_karar = 785. Bunların 17'si "entered" (işleme girildi), 768'i "skipped" (atlandı). En sık red nedenleri stop_width n = 375 (stop mesafesi uygun bulunmadı) ve arm_conflict n = 204 (kollar arası çakışma). Bu sayılar büyük, ama reddedilenlerin sonradan kazandırıp kazandırmayacağını tablo göstermiyor. Arm_conflict kayıp tablosunda her kolda n = 0, yani yetersiz örnek. Kayıp sayısı en yüksek kol H2-MINI@1h (kayip 4). Bunun ardından GF1-UCGEN@1h ve GF1-YATAY@1h gelir (ikisinde kayip 3). Bu kayıpların R değeri ölçülmediği için bir şey söylemiyorum.

- **Rejim ve rastgele giriş:** Rejim n: trend_down = 9, trend_up = 1. Her ikisi de yetersiz örnek. Kayıp kümelerinde çoğunlukla trend_down rejimi ve short yön var, ama her kümede kayip_sayisi 1. Bu bir örüntü sayılmaz. Rastgele girişle karşılaştırmada yüzdelik = 12.4, p = 0.876 (n = 10). Yetersiz örnek, kesin sonuç yok.

- **Koll
