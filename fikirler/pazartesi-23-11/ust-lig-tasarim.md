# Üst lig hattı: tasarım (23 Kasım 2026)

Durum: tasarım; kod yazılmadı. Kullanıcı kararı 23.11: üç parçalı "üst lig" hattı kurulacak. Kâğıtta her şey açık ve işlem etkili; canlı her an geçilebilecek biçimde kâğıtla aynı (gölge yok, terfi bayrağı yok). Kilitli dönem (2026-05-01 → 2026-11-01) hiçbir aşamada okunmaz. (Tasarım: Fable; belge kaydı ana oturum.)

## 0. Bir bakışta

| Parça | Ne yapar | İşlem yetkisi | Aylık LLM maliyeti | Emek |
|---|---|---|---|---|
| Haber kolu `HB1@1h` | Haberi okuyup enstrüman başına yön/şiddet verir, kol buna göre işlem açar | Var (kâğıt + canlı yapılandırması) | ~1-2 $ | 6-8 gün |
| Derin öğrenme kolu `DL1@1h` | Fiyat mumlarından önümüzdeki saatlerin yönünü tahmin eder | Var (kâğıt + canlı yapılandırması) | 0 $ | 10-14 gün |
| YZ yorumcu | Her gün sade Türkçe rapor yazar | YOK | ~2-3 $ | 3-4 gün |
| Ortak altyapı | Bütçe payları, belge/test güncellemesi, karne bölümü | — | — | 2 gün |

Ortak kurallar:
- Yeni kollar mevcut 32 kol gibi eklenir: `src/trader_engine/strategies/arms/` altına `hb1.py`, `dl1.py`; `engine.paper.json` ve `engine.live.json` `arms` listesine aynı anda. Parite testi (`test_canli_kagit_parite.py`) aynen geçer. Kol sayısı 32 → 34; 32'yi sabit yazan test/panel metinleri güncellenir.
- Risk: adaylar aynı kapıdan geçer (işlem başına %1, küme tavanları, açık risk 0,24, aynı yön 0,16, günlük 0,08, sermaye kilidi, aynı mum yasağı, çift başına tek pozisyon, ML aile süzgeci). `arm_max_positions`: `HB1: 3`, `DL1: 4`.
- Karne: defter `arm_id` bazında; `tur1_olcum` raporuna ve günlük Telegram'a "Üst lig" bölümü, iki kol 32 kolun toplamına karışmadan ayrı satırda.
- Canlı hazır oluş: kolun girdisi (sinyal dosyası, model paketi) yok/bayat/bozuksa o kol aday üretmez (yalnız girişler durur); diğer kollar ve açık pozisyon çıkışları etkilenmez (M1 kolunun bugünkü davranışı).

## 1. Haber kolu (`HB1@1h`)

**Sade özet:** Saatte bir, yeni haber başlıklarını küçük bir yapay zekâ modeli okur ve her kripto para için "olumlu / olumsuz / etkisiz, ne kadar güçlü" der. Güçlü ve taze bir sinyal varsa ve fiyat da aynı yöne kapanmışsa kol işlem açar. Haber yoksa ya da model yanıt vermezse kol o saat bir şey yapmaz.

- **Veri:** `var/veri/haber/haber.jsonl` (CoinDesk, Cointelegraph, Decrypt, Bitcoin Magazine) + `fng.jsonl`. Toplama 23.11'de başladı; geçmiş yok. Kaynaklar yalnız kripto (KARAR-2). Motor ham haberi okumaz; ayrı iş `var/learner/sinyal/haber_sinyal.json` üretir, kol yalnız bunu okur; `veri-toplama-spec` ve `test_veri_toplama.py` buna göre güncellenir (KARAR-8).
- **Model:** Claude Haiku 5.5 eşzamanlı (batch gecikmesi saatlik sinyale uymaz), düşük çaba, yapılandırılmış çıktı: sembol (evren enum'u), yön (−1/0/+1), şiddet (0-3), güven, ufuk. Şemaya uymayan yanıt atılır. F&G yalnız bağlam.
- **Nerede:** `scripts/haber_sinyal_run.py`, `trader-haber-sinyal.timer` (saatlik, toplayıcıdan sonra), motor dışında `MemoryMax=150M`. `budget.py` yeni pay `haber_kolu`, ayrı anahtar `ANTHROPIC_API_KEY_HABER`. Canlı aynı sinyal dosyasını salt okur (tek çağrı iki motora).
- **Giriş kuralı:** son 6 saat sönümlü birleşik puan; |puan| ≥ eşik VE (≥2 kaynak ya da şiddet 3) VE son 1s mum sinyal yönünde kapanmış. Stop 1,5 ATR, hedef 3 ATR, zaman stopu 24 mum (M1 sabitleri).
- **Sızıntı:** yayın saati değil alım saati; sinyal yalnız üretimden sonra kapanan mumda (`mum_kapanisi > uretim + 60 sn`). Geri test yok, yalnız ileri ölçüm.
- **Canlı:** API hatası/bütçe bitti → dosya yenilenmez, 3 saat geçerlilik dolunca kol aday üretmez. Sağlıkta "haber sinyali yaşı" satırı.
- **Başarı (önceden yazılı, tut/kaldır):** asgari 60 işlem. TUT: ort. R ≥ +0,05 VE rastgele giriş yüzdeliği ≥ 70. KALDIR: 60 işlemde ort. R ≤ −0,15, ya da 100 işlemde < 0, ya da herhangi anda toplam ≤ −15 R.
- **Maliyet:** ~1-2 $/ay (Sonnet ile ~12-15 $). **Emek:** 6-8 gün.
- **Riskler:** haber fiyata çoktan girmiş olabilir; başlıklar güvenilmez girdi (katı şema + doğrulama + 3 pozisyon tavanı); aynı haber 4 kaynakta (tek olay say); yalnız kripto.

## 2. Derin öğrenme kolu (`DL1@1h`)

**Sade özet:** Küçük bir sinir ağı son birkaç günün mumlarına bakıp "fiyat önce 3 birim yukarı mı gider, önce 1,5 birim aşağı mı" sorusuna olasılık verir; yüksekse kol işlem açar. Model başka makinede eğitilir, sunucuya yalnız küçük ağırlık dosyası gider. Dürüst beklenti: yalnız mumla derin öğrenme çoğu zaman mevcut modeli geçmez; bu bir denemedir, kaldırma eşikleri baştan yazılı.

- **Veri:** `var/history/*.feather`. Uyarı: bulut kopyasında yalnız 10 kripto var; 43 enstrümanın geçmişi sunucuda doğrulanmalı. Eğitim 2026-05-01 öncesinde biter (+ 2026-11-01 sonrası); 6 aylık boşluk = rejim kayması riski.
- **Model:** küçük 1D-CNN/TCN (~30-50 bin parametre), son 96 saat × ~8 kanal, tüm enstrümanlar tek havuz. Çıktı: long/short "hedef stoptan önce" olasılığı (M1 etiketi) + ikincil 4 saatlik oynaklık başı. ONNX yok (bağımlılık kilidi, motor torch alamaz); eğitim PyTorch dışarıda, ağırlık JSON/npz paketi, sunucuda saf numpy ileri geçiş (sha256 + son kullanma).
- **Nerede:** eğitim GitHub Action aylık (KARAR-4), çıkarım sunucuda kol içinde (< 10 MB).
- **Doğrulama:** `trader_ml/walkforward.py` (purge = ufuk, embargo), `assert_pre_holdout`; ölçekleme yalnız eğitim diliminden; aynı saat tüm enstrümanlar aynı dilimde. Yayın kapısı: en üst %2 puanlı adaylarda masraf sonrası ort. R > 0 ve dilimlerin ≥ %60'ı pozitif; numpy-PyTorch farkı < 1e-5.
- **Giriş:** eşik = eğitim puanlarının %98'liği; stop/hedef/zaman etiketle aynı; M1 ile çakışmada `PRIORITY = 95`.
- **Canlı:** paket depoda (`models/dl1/DL1@1h.json`), otomatik güncellemeyle iner; son kullanma 45 gün; yok/eski/hash tutmuyor → kol aday üretmez. Sağlıkta paket yaşı.
- **Başarı:** asgari 100 işlem. TUT: ort. R ≥ +0,05 VE rastgele yüzdelik ≥ 70 VE M1@1h'den kötü değil. KALDIR: 100'de ort. R < 0, 60'ta ≤ −0,15, ya da toplam ≤ −15 R.
- **Maliyet:** 0 $ LLM. **Emek:** 10-14 gün.

## 3. YZ yorumcu

**Sade özet:** Her sabah bir yapay zekâ analisti dünün işlemlerini, kararları ve ölçüm raporunu okur; "hangi kol hangi durumda kaybediyor, ne denenebilir" diye sade Türkçe bir sayfa yazar. Hiçbir ayarı değiştiremez, işlem açıp kapatamaz.

- **Veri:** kâğıt defteri (salt okunur), `tur1_olcum`, haftalık özet, dersler. Sayılar kodla hesaplanır, model yalnız yorumlar. Kilit dönemi okunmaz.
- **Model:** Claude Sonnet 5.5 batch (mevcut `lesson.AnthropicBatchClient` + `budget`).
- **Nerede:** `scripts/yorumcu_run.py`, 05:40 UTC; çıktı `var/durum/yorumcu/GG.md` + Telegram özeti. Yalnız kendi dizinine yazar; motor okumaz (kaynak tarama testi).
- **Başarı:** 4 hafta: rapordaki sayılar tabloyla birebir mi; kullanıcı haftada ≥1 öneriyi değerli buldu mu.
- **Maliyet:** ~2-3 $/ay. **Emek:** 3-4 gün. Önlem: her bulguda n; en çok 3 öneri.

## 4. Yapım sırası
0. Ortak altyapı (2 gün) → 1. YZ yorumcu (3-4 gün) → 2. Haber kolu (6-8 gün; önce 1 haftalık haber elle gözden geçirilir) → 3. DL kolu (10-14 gün; önce 43 enstrüman geçmişi doğrulanır) → 4. (isteğe bağlı) DL puanı süzgeç özelliği. Toplam ~21-28 iş günü.

## 5. Kullanıcı kararları
- KARAR-1: Aylık LLM tavanı. Bugün 10 $. Öneri: 20 $.
- KARAR-2: Haber kolu kapsamı. Öneri: önce 19 kripto.
- KARAR-3: Haber modeli. Öneri: Haiku 5.5 (Sonnet ~12-15 $/ay).
- KARAR-4: DL eğitim yeri. Öneri: GitHub Action aylık (repo public iken ücretsiz).
- KARAR-5: DL hedefi. Öneri: yön + ikincil oynaklık.
- KARAR-6: DL puanı süzgece özellik. Öneri: şimdi hayır; kol 100 işlemi görünce.
- KARAR-7: Kaldırma eşikleri. Öneri: aynen onay.
- KARAR-8: Haber verisi sinyal dosyası üzerinden karar girdisi olabilsin. Öneri: evet.
- KARAR-9: Kodda olmayan `L1` LLM aday kolu. Öneri: açılmasın, yerini HB1 alsın.

## 6. KULLANICI KARARLARI (23.11, verildi)
- KARAR-1: aylık LLM tavanı **20 $**.
- KARAR-2: haber kolu **kripto + hisse + emtia**; hisse/emtia için haber kaynakları eklenecek (ek iş).
- KARAR-3: haber modeli **Haiku 5.5**.
- KARAR-4: DL eğitimi **haftada bir, GitHub Actions** (repo gizli olursa dakika maliyeti yeniden değerlendirilir).
- KARAR-5…9: Fable önerileri aynen kabul (yön + oynaklık; süzgeç özelliği 100 işlemden sonra; kaldırma eşikleri aynen; haber sinyal dosyası karar girdisi olabilir; L1 açılmaz, yerini HB1 alır).
