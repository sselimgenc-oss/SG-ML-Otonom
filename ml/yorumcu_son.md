# Yorumcu raporu 2026-11-27

Yalnız yorum: bu rapor hiçbir ayarı değiştirmez, işlem açıp kapatmaz. Kapanmış işlem n = 3.

## Bulgular

- **Dün (2026-11-26):** Kapanan işlem yok (n = 0), toplam_R 0.0. Yetersiz örnek, bu günden sonuç çıkarılamaz.
- **Kararlar:** Bot toplam 332 karar verdi (n = 332). 6 kararda işleme girdi, 326 kararda atladı. En sık red nedenleri:
  - stop_width: 169
  - arm_conflict: 77
  - session_closed: 58
  - etiket_rejim: 17
  - rr_below_min: 5

  Burada "kol", tek bir strateji demek. arm_conflict, kolların birbiriyle çakışması demek. En çok atlama stop_width kuralından geldi.
- **Kollar:** Üç kolun her birinde yalnızca 1 işlem var (n = 1), hepsi yetersiz örnek, kesin sonuç yok.
  - IN1-RSI2@1h: toplam_R 0.27 (yetersiz örnek, n=1)
  - T1-GERI3@1h: toplam_R -0.96 (yetersiz örnek, n=1)
  - T1@1h: toplam_R -0.96 (yetersiz örnek, n=1)

  Son iki kolun kaybı aynı yönde (short), aynı rejimde (trend_down) ve aynı saat diliminde (20-24 UTC). Her biri n = 1 olduğu için yetersiz örnek, bir örüntü demek için erken.
- **arm_conflict kayıpları:** Tabloda en çok kayıp IN1-HIZLIMA@1h (9) ve IN1-VWAP@1h (9) kollarında görünüyor. Bu kolların n değeri 0, yani yetersiz örnek. R değerleri hesaplanamamış, kesin sonuç çıkarılamaz.
- **Ölçüm tablosu:** Kapanmış işlem sayısı n = 3, yetersiz örnek.
  - Masraf sonrası net -1.65 R, ortalama -0.549 R.
  - Güven alt sınırı hesaplanamadı, çünkü gün sayısı 1 (en az 8 gerekiyor).
  - Rastgele girişe göre yüzdelik 26.0 (n = 3). Yani rastgele girişlerin çoğu bu sonuçtan daha iyi çıkmış, ama 3 işlemle bu bir şey kanıtlamaz.
  - Monte Carlo (karışık işlem sıralarıyla yapılan deneme) p95 düşüş %2.3 (n = 3).

  Veri çok az olduğu için bu sayılar güvenilir bir yön göstermiyor.

## Öneriler

Veri genel olarak yetersiz. Aşağıdaki iki öneri yalnızca izleme amaçlıdır, hiçbir ayar değişikliği içermez.

- **Öneri 1:** Kolların hakkında hüküm vermeden önce her kolda en az 30 işlem birikmesini bekle (yetersiz_ornek_esigi_n = 30). Nasıl ölçülür: Her gün "kollar" tablosunda n alanına bak. Bir kolun etiketi "yetersiz örnek"ten çıktığında o kolun ort_R ve kazanma_orani_yuzde değerlerini değerlendir.
- **
