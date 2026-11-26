> **[24 Kasım 2026 — kod SİLİNDİ]** Kullanıcı kararıyla üç ML giriş filtresinin (v1 = r01, v2 = r02/r03, kurulum filtresi) kodu, testleri ve `ml_mode`/`ml_model_path`/`ml_features`/`ml_experimental`/`ml_pairs` yapılandırma anahtarları kod tabanından kaldırıldı. Bu belge yalnız geçmiş kaydıdır; geri açmak için kod yeniden yazılmalıdır (git geçmişi: silme işleminden önceki commit).
> **[24 Kasım 2026 — kullanıcı kararı: KAPALI]** Kâğıt ve canlıda `ml_mode: "off"`; gece eğitimi yapılmaz. Aşağıdaki metin geri açılış için kayıttır (bazı ayrıntılar eski: kod aile bazlı çalışır, eğitim 03:10 UTC).

# ML filtresi kâğıtta aktif (19.11 kullanıcı kararı)

**Karar:** `config/engine.paper.json` `ml_mode: "active"`. Kâğıt giriş kapısı (`gates.EntryGate.decide`, yalnız `mode=paper`), kurulum (arm_id, örn. `T1@1h`) için geçerli bir paket varsa girişi puanlar; puan `esik` altındaysa girişi `ml_filter` nedeniyle atlar. Karar satırı `final_action=skipped, skip_reason=ml_filter, ml_score=<puan>` olarak deftere yazılır; karşı-olgu kaydı mevcut atlama yolundan oluşur (alınmayan sinyal).

**Sınır:** Filtre yalnız bir YENİ girişe "hayır" diyebilir. Kapı, risk kontrolünden (`risk.check_entry`) ÖNCE yalnız atlar; boyut, kaldıraç, stop/hedef, günlük %5, kaldıraç 3-5x, küme/pozisyon tavanları ve risk kademesi filtreden etkilenmez. Yeni işlem açtıramaz.

**Serbest (filtre yok) durumları** (`ml_no_model` YAZILMAZ; yalnız log/özet): paket yok; hash/sürüm bozuk; `son_kullanma` geçmiş (21 gün); `n_egitim < 10`; `ortak_ogrenme` ya da numpy yüklenemedi; puanlama istisnası; `TRADER_OGRENME_FILTRE_KAPALI=1`. Filtre hatası motoru durdurmaz.

**Bileşenler:**
- `src/trader_engine/ogrenme_filtre.py`: `FiltreDeposu` (paket önbelleği, `karar`), `ozellikler` (giriş ve eğitim aynı işlev: `trader_core.ml_live_v2.setup_feature_dict`), `adaylar_defterden`, `egit_hepsi`.
- Paket: `paket/ortak_ogrenme/filtre.py` (1.2.1; değiştirilmez). Dosya: `<defter dizini>/models/ortak_filtre/<arm>.json` (+ `.prev.json`).
- Eğitim: gece birimi `scripts/ml_retrain_run.py` (00:40 UTC), kurulum başına ≥10 kapanmış işlem; son eğitimden ≥10 yeni kapanan işlem ya da ≥20 gün geçtiyse yeniden eğitim (1L3A ile aynı eşikler). Satır = defterdeki kapanmış kâğıt işlemi; holdout (2026-05-01..2026-11-01) ile kesişen satır eğitimden düşer (`kilit_dusen`).
- Motor ortamı: `deploy/trader-engine@.service` PYTHONPATH `paket` dizinini içerir.
- Görünürlük: `status.json` `ml_filtre` {aktif_kurulum, atladi, gecti}; günlük özet `ogrenme.filtre_aktif` ve not "ML filtresi: N kurulumda aktif, bugün K giriş atlandı".

**Eski yol:** `ml_model_path` boş + `ml_pairs` yoksa eski tek-model (r03) yolu kapalı kalır (sağlık alarmı üretmez); ML etkinliği kurulum filtresindedir. Canlı/testnet yolu değişmedi.

**İlk etki:** bir kurulum ≥10 kapanmış işleme ulaştıktan sonraki ilk gece eğitiminde (00:40 UTC) paket oluşur; motor dosyayı bir sonraki girişte okur. Mevcut ML kurulum süzgeci (`trader_ml.setup_filter`, `var/learner/models/setup_filter`) gece eğitimine devam eder; motor tarafından tüketilmez.


## Bilinen riskler (26.11 sahip kararları, Paket 2)

- **Seçilim yanlılığı (karar #11):** model yalnız kendi geçirdiği işlemleri görür; rastgele geçiş payı bilerek yoktur.
- **Örneklem-dışı sınama (karar #1):** her yayın denemesinde (ilk paket ve sonraki güncellemeler) en yeni %20'lik (en az 40) dilimde sınanır; eğitim/sınama zaman sıralıdır, aynı olaydaki eğitim satırları ambargolanır. Geçme: iki sınıf var, `ll_model < ll_taban`, `AUC > 0.5`. Geçemezse paket YAZILMAZ, etkin paket aynen kalır, öğrenme sürer. **Zayıflık:** 40 işlemlik sınama zayıf bir testtir; hiç bilgi taşımayan (rastgele etiketli, 96 özellikli) bir model n=240'ta ölçülen ~%16, n=400'de ~%6 oranında şans eseri geçer (300 tohum taraması). Amaç "açıkça kötü modeli" durdurmaktır; `GERI_IZLE_MIN` geri dönüş denetimi aynen kalır.
- **Özellik tanımı sürümü (karar #8, 26.11):** `vol_*` özellikleri ölü mumlar (hacim 0, o=h=l=c) dışarıda bırakılarak hesaplanır (`OZELLIK_SURUM = 2`); önceki işlemler eski tanımla kaydedilmiştir ve atılmaz; `durum.json` `oz_karisik` oranı gösterir.
- **Kapı arızası (karar #10):** ML1 açıkken kapı/öğrenici kurulamazsa (`ml1_kapi_yok`) ya da öğrenici yokken paket bozuksa (`ml1_paket_bozuk`) yeni işlem AÇILMAZ; açık işlemler/çıkışlar yönetilmeye devam eder. Paket dosyası hiç yoksa (öğrenme aşaması) engel yoktur.
- **Parametre defteri (karar #9, yalnız kâğıt):** defter okunamazsa çıkışlar kv'deki son bilinen sürümle sürer; girişler kapalı kalır (`params_unavailable`).
- **Sahip adımları (P7-02 / P7-09):** güncelleme dalı koruması ve pano parolası canlıya geçişe ertelendi (bu pakette uygulanmadı).
