# Alınmayan sinyal × sonuç raporu — belirtim (19 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


**Yalnız ölçüm/rapor.** Motor, kapılar, kol ayarları, ders ve ML özellikleri değişmez (kol ayarlarına 23.11'e kadar dokunulmaz). Şema `ml.alinmayan_sonuc.v1`; satır biçimi `ml.haber_sonuc.v1` ve CT `ct.rejim_sonuc.v1` ile aynıdır (aynı yardımcılar: `haber_sonuc._satirlar`, `yaz_atomik`). Kod: `src/trader_core/alinmayan_sonuc.py` (saf `topla`/`olustur` + okuyucu). Veri kaynağı `docs/alinmayan-sinyal-spec.md` (gece işi).

## Veri
- Alınmayan adaylar: `var/learner/counterfactual.sqlite` `cf_outcomes` (yöntem `plan`, `version ≥ 2`, `hyp_r_net` dolu = çözüldü). Engel nedeni = satırın `skip_reason` alanı.
- Çözülmedi: defterde `final_action='skipped'` olup çözülmüş `plan` satırı olmayan karar (bekleyen pencere, `data_gap`, `invalid_plan`). Uydurulmaz; neden başına sayı olarak yazılır (`cozulmedi`). Kilitli dönemde (2026-05-01 → 2026-11-01) karar çözülmedi sayılmaz (iş onları hiç okumaz).
- Alınan işlemler (karşılaştırma): kapanan kâğıt işlemleri, `r_multiple` (kapanış zamanına göre dönem).

## Engel nedenleri (kodda geçen gerçek değerler: `ledger._SKIP`)
`max_positions, cluster_cap, flat_bar, arm_conflict, arm_disabled, session_closed, ml_filter, ml_no_model, risk_denied, entry_gate_closed, veto_blocked, veto_missing, veto_stale, stop_width, rr_below_min, order_failed, llm_invalid, other`. Boş kovalar yazılmaz; sözlük dışı değer gelirse alfabetik sona eklenir.

## Birim: R (USD değil) — gerekçe
Alınmayan aday için kâğıt boyutlandırması (miktar, marj, kaldıraç) hiç üretilmez; kasa o andaki kullanılabilir bakiye/açık risk durumuna bağlıdır ve atlanma nedeni çoğu zaman bunun kendisidir (`max_positions`, `risk_denied`). USD'ye çevirmek varsayım uydurmak olurdu. "Alınsaydı" sonucu gece işinde net R olarak hesaplanır (maliyet düşülmüş), alınan işlemlerin `r_multiple`'ı da R'dir; iki taraf aynı birimde karşılaştırılır. Bu yüzden `toplam_pnl` / `ortalama_pnl` alanları bu raporda **R**'dir; dosyada `"birim": "R"`, pano başlığı "Toplam PnL (R) / Ort. PnL (R)".
Not: CT raporlarında aynı alan adları USD'dir; orkestratör yan yana koyarken `birim` alanına bakmalıdır.

## Satır ve dosya
Satır `{etiket, n, kazanan, isabet_yuzde, toplam_pnl, ortalama_pnl}`; kazanan = R > 0. `var/durum/alinmayan_sonuc_v1.json` (atomik): `{sema, uretim, birim:"R", pencere_gun:7, tablolar:{neden:[satırlar]} (son 7 gün, karar zamanına göre), tum_zamanlar:{neden:[...]}, cozulmedi:{tablolar:{neden:n}, tum_zamanlar:{neden:n}}, not}`. Her tablonun son satırı `alınan işlemler` (aynı dönem, karşılaştırma; işlem yoksa yazılmaz).

## Sınırlar
Üst sınır: giriş = planlanan fiyat, sonraki kapılar ve dolum yok sayılır (`alinmayan-sinyal-spec.md` §8); `plan` yöntemi 48 mum ufkunda planlanan stop/hedefi oynatır, alınan işlemin gerçek çıkışı (iz süren stop, zaman çıkışı) farklı olabilir. Örtüşen sinyaller bağımsız sayılır.

## Üretim ve gösterim
- Gece işi `scripts/counterfactual_run.py` (her gece, `--once`; `--dry-run` yazmaz) karşı-olgu depoyu güncelledikten sonra JSON'u yazar; hata yutulur, iş çıkış kodunu etkilemez. Birime `var/durum` yazma yolu eklendi (`trader-counterfactual@.service`). Pano yayın birimi `/opt/trader` salt okunur olduğundan dosyayı orada üretmek mümkün değildir; pano ve `scripts/weekly_summary_run.py` yalnız JSON'u okur.
- Pano Doğrulama sekmesi "Alınmayan sinyal × sonuç (R)" kartı (`/api/alinmayansonuc`, `docs/panel-spec.md` §14.1).
