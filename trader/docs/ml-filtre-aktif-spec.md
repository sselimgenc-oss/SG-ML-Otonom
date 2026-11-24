> **[24 Kasım 2026 — kullanıcı kararı: KAPALI]** Kâğıt ve canlıda `ml_mode: "off"`; gece eğitimi yapılmaz. Aşağıdaki metin geri açılış için kayıttır (bazı ayrıntılar eski: kod aile bazlı çalışır, eğitim 03:10 UTC).

# ML filtresi kâğıtta aktif (19.11 kullanıcı kararı)

**Karar:** `config/engine.paper.json` `ml_mode: "active"`. Kâğıt giriş kapısı (`gates.EntryGate.decide`, yalnız `mode=paper`), kurulum (arm_id, örn. `T1@1h`) için geçerli bir paket varsa girişi puanlar; puan `esik` altındaysa girişi `ml_filter` nedeniyle atlar. Karar satırı `final_action=skipped, skip_reason=ml_filter, ml_score=<puan>` olarak deftere yazılır; karşı-olgu kaydı mevcut atlama yolundan oluşur (alınmayan sinyal).

**Sınır:** Filtre yalnız bir YENİ girişe "hayır" diyebilir. Kapı, risk kontrolünden (`risk.check_entry`) ÖNCE yalnız atlar; boyut, kaldıraç, stop/hedef, günlük %5, kaldıraç 3-5x, küme/pozisyon tavanları ve risk kademesi filtreden etkilenmez. Yeni işlem açtıramaz.

**Serbest (filtre yok) durumları** (`ml_no_model` YAZILMAZ; yalnız log/özet): paket yok; hash/sürüm bozuk; `son_kullanma` geçmiş (21 gün); `n_egitim < 10`; `ortak_ogrenme` ya da numpy yüklenemedi; puanlama istisnası; `TRADER_OGRENME_FILTRE_KAPALI=1`. Filtre hatası motoru durdurmaz.

**Bileşenler:**
- `src/trader_engine/ogrenme_filtre.py`: `FiltreDeposu` (paket önbelleği, `karar`), `ozellikler` (giriş ve eğitim aynı işlev: `trader_core.ml_live_v2.setup_feature_dict`), `adaylar_defterden`, `egit_hepsi`.
- Paket: `paket/ortak_ogrenme/filtre.py` (1.2.1; değiştirilmez). Dosya: `<defter dizini>/models/ortak_filtre/<arm>.json` (+ `.prev.json`).
- Eğitim: gece birimi `scripts/ml_retrain_run.py` (03:40 UTC), kurulum başına ≥10 kapanmış işlem; son eğitimden ≥10 yeni kapanan işlem ya da ≥20 gün geçtiyse yeniden eğitim (1L3A ile aynı eşikler). Satır = defterdeki kapanmış kâğıt işlemi; holdout (2026-05-01..2026-11-01) ile kesişen satır eğitimden düşer (`kilit_dusen`).
- Motor ortamı: `deploy/trader-engine@.service` PYTHONPATH `paket` dizinini içerir.
- Görünürlük: `status.json` `ml_filtre` {aktif_kurulum, atladi, gecti}; günlük özet `ogrenme.filtre_aktif` ve not "ML filtresi: N kurulumda aktif, bugün K giriş atlandı".

**Eski yol:** `ml_model_path` boş + `ml_pairs` yoksa eski tek-model (r03) yolu kapalı kalır (sağlık alarmı üretmez); ML etkinliği kurulum filtresindedir. Canlı/testnet yolu değişmedi.

**İlk etki:** bir kurulum ≥10 kapanmış işleme ulaştıktan sonraki ilk gece eğitiminde (03:40 UTC) paket oluşur; motor dosyayı bir sonraki girişte okur. Mevcut ML kurulum süzgeci (`trader_ml.setup_filter`, `var/learner/models/setup_filter`) gece eğitimine devam eder; motor tarafından tüketilmez.
