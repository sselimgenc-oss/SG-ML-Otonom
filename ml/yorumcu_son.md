# Yorumcu raporu 2026-11-24

**SAYI HATASI**: raporda girdi tablolarında bulunmayan sayılar var (1.5). Bu raporu doğrulanmamış sayın.

Yalnız yorum: bu rapor hiçbir ayarı değiştirmez, işlem açıp kapatmaz. Kapanmış işlem n = 65.

## Bulgular

- **Dün (2026-11-23):** 15 işlem kapandı (n=15) ve toplam sonuç -9.96 R oldu. R, bir işlemde göze alınan zarar birimidir. Bu **yetersiz örnek**, bu yüzden kesin sonuç çıkarmıyorum.

- **Genel ölçüm (n=62):** Şart için en az 300 kapanmış işlem gerekiyor, şu an n = 62. Masraf sonrası net = -1.72 R, ortalama = -0.028 R. Güven alt sınırı hesaplanamadı, çünkü gün sayısı 7 < 8. Bu şartların hepsi FAIL. Tabloda "toplam_kapanmis_islem" 65, "n_islem" 62 yazıyor. Bu farkın nedeni tabloda açıklanmamış.

- **Rastgele girişle yarış (n=62):** Bot, girişlerini rastgele girişlerle karşılaştırır. Yüzdelik = 37.6, şart ise en az 90 ve sonuç FAIL. Masraflar 1.5 kat olsa net = -4.93 R. Monte Carlo (işlem sırası karıştırılarak tahmin edilen en kötü düşüş) için p95 = %27.7, sınır %15. İkisi de FAIL.

- **Alınmayan sinyaller:** Bot 3888 kararın 70'inde girdi (entered), 3818'inde girmedi (skipped). En sık ret nedeni risk_denied (n=2485).
  - Alınmayan sinyallerin tablosunda risk_denied için n=1355 ve toplam_pnl_usd -952.14 yazıyor. etiket_rejim için n=72 ve -218.9. Eksi değer, girilmeyen bu sinyallerin zarar edeceğine işaret eder.
  - Haftalık özette en iyi satır stop_width: +78,45 $ (n=201). Yani bu filtreyle girilmeyen sinyaller kazançlı görünüyor. Bu yalnızca 7 günlük bir pencere, bu yüzden kesin sonuç çıkarmıyorum.
  - cluster_cap (n=10) ve veto_blocked (n=3) **yetersiz örnek**.

- **Kollar ve rejimler:** Tüm kollar
