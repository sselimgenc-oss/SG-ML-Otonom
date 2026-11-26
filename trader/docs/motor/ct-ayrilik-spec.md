# CT/ML ayrılığı — C1 kolunun ve tüm CT bağlantısının kaldırılması (20 Kasım 2026)

**Kullanıcı kararı (kesin):** ML ve CT tamamen ayrıdır. CT'den gelen hiçbir şey ML'i (karar, özellik, etiket, rapor, panel) etkilemez.
Eski belgeler `docs/motor/c1-ct-kadro-spec.md` (C1 kolu) ve CT bölümleri **kaldırılmıştır**; bu belge tek kayıttır.

## 1. Kaldırılanlar (kod)
- C1 kolu: `strategies/arms/c1.py`, `config/engine.paper.json` `arms` içinde `C1@1h`, `C1@4h`, `arm_max_positions` içinde `"C1"`.
  Başka hiçbir risk sayısı değişmedi (max_positions 24, açık risk 0,24, aynı yön 0,16, kümeler, günlük 0,08, kaldıraç, sert limitler).
- CT okuma: `scripts/ct_kadro_cek.py`, `deploy/trader-ct-kadro.service|.timer`, `trader_core/ct_kadro.py`, motorun CT okuyucusu.
- Kapı: `_ct_blok`/`_ct_yon` ve `features.ct_*` (ct_long, ct_short, ct_baskinlik, ct_net_yon, ct_yon, ct_yas_dk, ct_durum) artık yazılmaz.
- ML: `f_ct_trader_sayisi` ve her `f_ct_*` özelliği kaldırıldı; `ml_live_v2.setup_feature_dict` eski kayıtlardaki `ct_*` alanlarını
  özellik yapmaz (eğitim de puanlama da aynı fonksiyon). Eski model paketi `f_ct_*` bekliyorsa eksik özellik NaN olur, modelin `fill`
  değeri doldurur; **giriş engellenmez**.
- Etiket kuralı "kalabalık yönü" tamamen kaldırıldı (kod, config bloğu, gate'teki C1 istisnası). `rejim` kuralı aynen (`duygu` kuralı 21 Kasım'da ayrıca silindi; bkz. `docs/etiket-kurallari-spec.md`).
  `etiket_kalabalik` kodu yalnız defter şeması ve eski karar satırlarının okunur adı için kalır (şema CHECK'i değişmez).
- Sağlık: `ct_kadro_bayat` uyarısı. Telegram: "Kadro uzlaşısı" adı. Strateji verisi: "CT bilgisi" bölümü. Tutarlılık: C1 için `veri` özel durumu.
- `drift_monitor` içindeki `C1` bir **kural kimliğidir** (CUSUM; "C1" = 5. kural) ve bu kolla ilgisizdir; dokunulmadı.

## 2. Açık C1 pozisyonlarının zorla kapatılması
`Engine.start()` içinde, mutabakattan sonra tek seferlik ve idempotent adım `_kaldirilan_kollari_kapat` (`KALDIRILAN_KOLLAR = ("C1",)`):
- Kurulumu `C1` olan **açık** (`open`) pozisyonlar stop/hedef beklenmeden piyasadan kapatılır; normal `_submit_exit` yolu kullanılır
  (kâğıtta kâğıt broker piyasa çıkışı; testnet/canlıda yalnız reduce-only çıkış, ban penceresi ve poll dahil). Gerçekleşen K/Z, komisyon,
  kayma her zamanki gibi yazılır. Çıkış nedeni defterin kabul ettiği `force_exit`; günlükte `kol_kaldirildi`.
- İkinci çalışma: pozisyon `closing`/kapalı olduğundan hiçbir şey yapılmaz. Çıkış gönderilemezse veya pozisyon henüz `opening` ise
  **CRIT** günlük + sayaç (`kaldirilan_kol_hata`, `kaldirilan_kol_bekliyor`); sessiz bırakılmaz, sonraki başlangıçta yeniden denenir.
- Yeni C1 girişi zaten mümkün değildir (kol yok).

## 3. Kurulum (install.sh)
`trader-ct-kadro.timer/.service` sunucuda durdurulur, devre dışı bırakılır ve birim dosyaları silinir (her kurulumda, idempotent).
`var/c1_temizle.done` yoksa `scripts/c1_temizle.py` bir kez çalışır; işaret yalnız dosya adımları hatasız bitince yazılır.

## 4. Veri temizliği (scripts/c1_temizle.py) — dosya düzeyi
Silinen/ayıklanan: `var/ct/`; `…/models/ortak_filtre/aile_C1.json` ve `eski_kol/` altındaki C1 dosyaları; `paper_models.csv` C1 satırları;
`arms_off.json` C1 anahtarları; `var/durum/etiket_kurallari_v1.json` içinden `etiket_kalabalik`; sağlık durum dosyasından `ct_kadro|bayat`.
Yeniden üretilebilir çıktılar (özet, strateji verisi, mutabakat) bölüm 5'teki göçle birlikte silinir ve C1'siz yeniden üretilir.

## 5. Defter/state göçü ve kasa (UYGULANDI: `trader_core/kol_kaldirma.py`, `scripts/c1_goc.py`, `trader-c1-goc.service`)
Kullanıcı onayıyla C1 geçmişi defterden silinir ve kasa "C1 hiç olmamış gibi" yeniden hesaplanır (nötr taşıma kaydı YOK).
**Mekanizma:** defterin kendi göç deseni (`ledger._run_migrations`: tek işlem, tetikleyicileri bırak, değiştir, hepsini yeniden kur).
Şema sürümü değişmez (veri göçü). `ledger.py`/`state.py` ve donmuş dosyalara dokunulmadı.
1. **Önkoşul (reddet, hiçbir şey değişmez; çıkış 3):** motor çalışıyor (`systemctl is-active`); `state.positions` ya da defterde kapanmamış
   C1 işlemi; defterde bekleyen C1 outbox satırı. Açık C1 pozisyonu varsa install motoru yeni kodla başlatır, motor açılışta C1'i piyasadan
   kapatır (bölüm 2); install `state.sqlite`'ı ~15 dk'ya kadar yoklar, kapanınca motoru durdurup göçü yeniden dener; olmazsa göç sonraki
   kurulumda (ya da elle `systemctl start trader-c1-goc`) tekrarlanır. İşaret yazılmadığı için tekrar güvenlidir.
2. **Yedek:** `var/yedek/c1-goc-<zaman>/` altına `ledger.sqlite`, `state.sqlite` (sqlite backup API), `counterfactual.sqlite`,
   `exit_counterfactual.sqlite`, Telegram işlem kayıtları ve türetilmiş durum çıktıları. Kullanıcı arşiv istemediği için başarıda
   (ve geri yüklemeden sonra) yedek **silinir**.
3. **Defter (tek işlem):** tetikleyiciler bırakılır; `trade_exits`, `trade_notes`, `trade_entries`, `decision_events`, `shadow_decisions`
   içinden C1 satırları silinir; `equity_marks` geçmişi C1 etkisi çıkarılarak düzeltilir (wallet/equity/equity_low −= kayma,
   `n_open` −= açık C1 sayısı); tüm tetikleyiciler (`_EXPECTED_TRIGGERS`: yalnızca-ekleme + excursion) yeniden kurulur; `meta`'ya
   `kol_kaldirildi:C1` damgası eklenir; `foreign_key_check` temiz olmalı.
4. **State (tek işlem):** C1 `positions`, `orders`, `ledger_outbox`, işlem-bazlı `kv` anahtarları (`gecikme:`, `eq:`, `partial:`, `naked:`,
   `ext_reduction:`, `exit_retry:`, `exit_unresolved_since:`, `entry_fee_estimated:`) ve `broker_order:<cid>` silinir.
   **Kasa:** `broker_snapshot.wallet := wallet − Σ C1 realized_pnl` (realized = brüt − giriş/çıkış komisyonu − fonlama; C1 işlemleri
   kapalıyken cüzdana tam bu net etkisi yansımıştır). `day_start:<gün>` değerleri aynı kayma ile (gün 00:00 UTC itibarıyla) düzeltilir.
   Paper risk kademesi bellekte tutulur (günlük dosyası yok, tepe özsermaye açılışta yeniden kurulur) ve kol küçültme çarpanı defterden
   türetilir: ikisi de motor yeniden başlayınca C1'siz yeniden oluşur.
5. **Yan dosyalar:** `counterfactual.sqlite`/`exit_counterfactual.sqlite` C1 satırları; `islem_gonderildi.jsonl`/`islem_imleci.json`
   C1 işlem numaraları; türetilmiş çıktılar (`mutabakat*`, `tutarlilik_v1.json`) silinir ve yeniden üretilir.
6. **Doğrulama (hepsi geçmeli):** `Ledger._verify` (motorun açılışta yaptığı) + tüm tetikleyiciler mevcut + davranış sınaması
   (UPDATE `append-only` ile reddedilmeli) + `integrity_check` + `foreign_key_check` + C1 satırı kalmadı + state'te C1 kalmadı +
   **kasa kalanı değişmedi**: `kalan = kasa + açık işlemlerin giriş komisyonu/fonlaması − başlangıç − Σ kapanan net K/Z` göç öncesi ve
   sonrası aynı (sıfırsa `kasa = başlangıç + Σ net K/Z (C1 hariç)`; `mutabakat.kontrol_kasa` aynı formülü kullanır) ve yeni kasa
   `eski kasa − Σ C1 net K/Z`'ye eşit.
7. **Sonuç:** başarılıysa yedek silinir, `var/durum/c1_goc_raporu.json` (`eski_kasa`, `yeni_kasa`, `silinen_kayit`, `tetikler_dogrulandi`,
   `zaman`) yazılır (`durum_yayinla.sh` izin listesinde: `canli-durum` dalında görünür), `var/c1_goc.done` işareti yazılır ve tek satır
   Telegram mesajı gider ("Kasa: eski → yeni"). **Herhangi bir adım başarısızsa** yedekten geri yüklenir, işaret yazılmaz, CRIT günlük +
   Telegram "CRIT" mesajı, çıkış 1; yarım göç kalmaz.
**Bilinen sınır:** C1 pozisyonu açıkken alınmış geçmiş `equity_marks`/`day_start` değerlerindeki C1 *gerçekleşmemiş* K/Z'si geçmiş
fiyatlar olmadan geri alınamaz; bu satırlar yalnız gerçekleşen kısım kadar düzeltilir (güncel kasa ve defter toplamları etkilenmez).
Yedeğin kendisi (göç sırasında) C1 içerir; başarıda silinir.

## 6. Mühür / eşdeğerlik
Holdout mührü (`research/holdout/muhur.json`) yalnız `var/history` holdout dilimi baytlarının özetidir; C1 veri içermez (C1 19 Kasım 2026'da
başladı, holdout 2026-05-01..2026-11-01). Mühür/özetler değişmedi. `research/holdout/pbo_ozet*.json`, `research/arm_series/meta.json`
ve `docs/ml/pbo-raporu.md` içindeki "C1 için seri yok" dışlama notları kaldırıldı (mühür girdisi değildir).
