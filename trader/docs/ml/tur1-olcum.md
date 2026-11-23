# Tur 1 ölçüm raporu (Aşama A)

Yalnız ölçüm: bot, ayar ve motor yapılandırması değişmez. Kâğıt defteri (kapanan işlemler + karar satırları) ve `var/market.sqlite` mumları salt okunur açılır. Kilitli dönem okunmaz (`trader_reports.guard`).

- Betik: `scripts/tur1_olcum_run.py --once`; çekirdek: `src/trader_reports/tur1_olcum.py` (rastgele giriş yapıştırması: `src/trader_core/tur1_rastgele.py`, mevcut `stats/k2_simulasyon.py`).
- Zamanlama: `trader-tur1-olcum.timer`, her gün 05:10 UTC (gece işlerinden sonra). `install.sh` etkinleştirir.
- Çıktı: `var/durum/tur1_olcum_v1.json` + `tur1_olcum.md`; `deploy/durum_yayinla.sh` bunları canlı-durum dalının `ml/` klasörüne yayımlar.
- Bölümler: 1 rakip kıyası (rastgele giriş yüzdeliği, hep long/short, hiçbir şey) · 2 gecikme/masraf dayanıklılığı · 3 şans/kuyruk (10000 karıştırma, batış) · 4 canlıya geçiş şartları (eşikler dosyanın başında) · 5 yön denetimi · 6 kayıp kümeleri.
- Her bölüm n verir; n < 30 iken "yetersiz örnek" der. 15 dk mum-saati kayması saklı veriden tam ölçülemez (sinyali yeniden üretmek gerekir); yalnız giriş gecikmesi vekili verilir.
- Tohum sabittir; aynı veri aynı sonucu verir.
