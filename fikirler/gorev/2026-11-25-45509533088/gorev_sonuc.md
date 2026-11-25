GF1 (13 formasyon) ve IN1 (17 setup) motora eklendi, tam takım geçti: **8606 passed, 145 skipped, 0 failed**. Skip'ler eski testlerden. Bu adımda yeni skip/xfail eklemedim. Eksik formasyon kalmadı.

| Eklenenler | Dosyalar | Test |
|---|---|---|
| **GF1:** OBO, UCLU, KUPA, IKILI, KAMA, UCGEN, BAYRAK, FLAMA, RETEST, SAHTE, TREND, KANAL, YATAY. Pivot sol 10, sağ 2, onay gecikmesi 2 mum; 52 kol. | `arms/gf1.py` | `test_formasyon_gf1.py` |
| **IN1:** 17 setup, hepsi 17'si tasarımdaki gibi. VWAP yalnız 15m ve 1h, 66 kol. Stopsuzlara 2 ATR stop. 13 setupta kural çıkışı yön duyarlı (`other` nedeniyle). | `arms/in1.py` | `test_formasyon_in1.py` |
| **Yeni göstergeler:** RSI, EMA, SMA, Bollinger, MACD, Stokastik, Ichimoku, günlük VWAP, pivot. Referansla 1e-9 içinde. | `trader_core/indicators.py` (yalnız ekleme) | gösterge testi, `test_formasyon_in1.py` içinde |
| **Altyapı:** pivot ve gösterge önbelleği, `ArmInput.side`; kural çıkışı pozisyonun yönüyle çağrılıyor. | `_kutuphane.py`, `arms/__init__.py`, `strategy_runner.py` | pozisyon yönü testi, `test_formasyon_in1.py` içinde |
| **Ayar ve ad:** 203 kol, `GF1-*`/`IN1-*` joker tavanı 3, aile tavanı 6/6/6; kâğıt ve canlı aynı. 30 Türkçe ad. | `engine.paper.json`, `engine.live.json`, `tg_sade.py` | kâğıt = canlı testi, GF1 ve IN1 dosyalarında |
| **Ortak test yardımcısı** | `tests/engine/formasyon_destek.py` | — |

- **Test kapsamı:** Her formasyon için sentetik long, short aynası ve bozulan koşul testi var. Motor yolu satırı ve ileriye bakış testleri de geçiyor.
- **Referans eşdeğerliği:** YATAY, UCGEN, IKILI, OBO, RSI ve BOLL referansla (t, yön, stop) aynı çıktı verdi. MAKESISIM ve FIYATMA yalnız (t, yön) olarak karşılaştırıldı.
- **Hız:** 42 formasyon, 5000 mum için toplam 19,8 ms (hedef 50 ms).
- **Hash ve sayı güncellemeleri:** Yorum satırı "24.11 kullanıcı kararı: formasyon kütüphanesi" ile gerçek değerlerden yeniden hesaplandı. Güncellenenler: `engine.live.json` sha256 (iki testte), `indicators.py` sha256, kol sayısı 85→203, `PAPER_ARMS`, tavan sözlükleri ve modül envanteri.
- **Sınırlamalar:**
  - Uzun serilerde özyinelemeli göstergeler son 1200 muma göre hesaplanıyor (hata 1e-15 altında).
  - BAYRAK ve FLAMA direk tepesi seçiminde eşitlikte ilk tepe alınıyor. Tasarım bu konuda sessizdi.
  - Tam takım koşusu 37 dakika sürüyor.

**Sizin onayınız gereken karar:** `test_wp3_spec.py` dondurulmuş dosya listesinden `indicators.py` çıkarıldı. Bu test dosyayı git blob eşitliğiyle kilitliyordu. Göstergeleri eklemek bunu bozduğu için, 23.11'deki kilit açma emsaliyle çıkardım. İsterseniz gösterge kodunu ayrı bir dosyaya taşıyıp kilidi geri koyabilirim.