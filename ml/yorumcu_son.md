# Yorumcu raporu 2026-11-25

Yalnız yorum: bu rapor hiçbir ayarı değiştirmez, işlem açıp kapatmaz. Kapanmış işlem n = 83.

## Bulgular

- **Dün:** Kapanan işlem n=25, toplam_R -1.58. Bu **yetersiz örnek**, bu yüzden kesin sonuç çıkarmıyorum. (R, bir işlemde riske edilen miktarın katı olarak kazanç ya da kayıptır.)

- **Genel tablo kötü:** Toplam kapanmış işlem n=83, net -6.03 R, ortalama -0.073 R. Masraflar 1.5 katına çıkarsa net -10.79 R olur (n=83). Güven alt sınırı hesaplanamadı, çünkü gün sayısı 7 ve en az 8 gerekiyor.

- **Giriş kalitesi ölçümleri:** Botun girişleri rastgele girişlerle karşılaştırıldı. Yüzdelik 47.8 çıktı (n=83), hedef en az 90'dı. Bu, girişlerin rastgele girişten belirgin biçimde iyi olmadığını gösteriyor. Monte Carlo (işlemleri binlerce kez karıştırıp en kötü düşüşü tahmin eden yöntem) p95 maksimum düşüş %31.2 çıktı (n=83), sınır %15'ti. Bu kontrollerin ikisi de FAIL.

- **Rejim dağılımı:** İşlemlerin çoğu düşen piyasada: trend_down n=69. Diğerleri range n=3, trend_up n=7, unclear n=4, hepsi **yetersiz örnek**. En büyük kayıp kümelerinin hepsi trend_down ve short yönlü. Örneğin F1@15m, 08-12 UTC: kayip_sayisi 3, toplam -3.3726027869252952 R. Her kümede kayıp sayısı 30'un altında olduğu için bunlar **yetersiz örnek**, kesin sonuç çıkarılamaz. Tüm kollar da (T1@15m n=10, toplam_R 8.13 dahil) **yetersiz örnek**.

- **Alın
