# Yorumcu raporu 2026-11-26

Yalnız yorum: bu rapor hiçbir ayarı değiştirmez, işlem açıp kapatmaz. Kapanmış işlem n = 110.

## Bulgular

- **Genel tablo olumsuz (n=110).** Kapanmış 110 işlemde masraf sonrası net = -15.06 R, ortalama = -0.137 R, güven alt sınırı = -0.478. R, bir işlemde riske edilen tutarın katıdır. Güven alt sınırı, gerçek ortalamanın bundan kötü çıkma ihtimalinin düşük olduğu en kötü makul değerdir. Masraf x1.5 senaryosunda net = -20.82 R. İlgili kontrollerin hepsi FAIL.

- **Giriş kalitesi rastgeleden iyi görünmüyor (n=110).** Rastgele giriş yüzdeliği 38.4. Bu, botun girişlerinin rastgele girişlerle karşılaştırıldığında kaçıncı sırada olduğunu gösterir. Kontrolün eşiği 90 ve sonuç FAIL. Monte Carlo (işlem sırasını karıştırarak yapılan deneme) %95 en kötü düşüş p95 = %36.0 çıktı (n=110). Kontrolün sınırı %15 ve sonuç FAIL.

- **Zarar neredeyse tamamen düşen piyasada (trend_down, n=91).** Bu rejimde güven alt sınırı = -0.557. Diğer rejimlerde range n=3, trend_up n=9, unclear n=7 işlem var, hepsi yetersiz örnek, kesin sonuç çıkarılamaz. Hiçbir rejim pozitif çıkmadı.

- **Alınmayan sinyaller çoğunlukla zararlıydı.**
  - risk_denied: n
