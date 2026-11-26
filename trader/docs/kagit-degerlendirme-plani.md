# Kağıt / testnet değerlendirme planı ve günlük sapma izleyicisi eşikleri (ön kayıt v1, 17 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. Kâğıt bot tek ve düzdür (ikiz/gölge/deney botu yok), 44 enstrüman, tüm aileler, ML ve ders ilk işlemden etkin, risk %1/16 pozisyon (20 Kasım: 24 pozisyon, toplam açık risk %24, aynı yön %16). Bu planın ikiz kıyası, gölge ve canlıya geçiş (CANLI-K1 vb.) ölçütleri **[ASKIDA — kullanıcı yeniden belirleyecek]**; yalnız kâğıt izleme/raporlama kısımları geçerlidir.

**Yazan:** mentor · **Durum:** ön kayıt. Kağıt işlem (30 Kasım 2026) başlamadan yazıldı; kağıt başladıktan sonra bu belgedeki hiçbir sayı, formül ya da kural sonuca bakılarak değiştirilmez. Değişiklik gerekiyorsa §9'daki yol izlenir.

**Kaynak:** `otonom-trading-arastirma/repo-denetim-onay-listesi.md` madde 1 ve 3 (denetim kimlikleri D-07, B-09, D-01, D-04, B-14, D-12, B-26); `tasarim-kararlari.md` 17 Kasım kayıtları.

## 0. Bu belge ne değildir

- **Proje durdurma ölçütü değildir.** Kullanıcı kararı (17 Kasım): "strateji işe yaramıyor" türü bir durdurma ölçütü konmaz. Buradaki hiçbir sonuç projeyi, botu ya da ML çalışmasını durdurmaz.
- **Para korumasına dokunmaz.** RK-1 (yatırılana göre −%20 duruş, %60 taban), günlük −%5 sınırı, risk kilidi ve KILL aynen çalışır; bu belge onlara eşik eklemez, onlardan eşik almaz.
- **Hiçbir şeyi otomatik değiştirmez.** İzleyici yalnız uyarır: emir vermez, duraklatmaz, ayar değiştirmez, yeniden eğitim başlatmaz.
- **Kağıttan canlıya geçişi kâra bağlamaz.** Geçişi yalnız teknik hata geciktirir (mevcut karar). Buradaki kâr/zarar satırları bilgi içindir.

## 1. Dayanak koşu (referans) ve kilitli dönem

Bütün beklenti değerleri **tek bir dondurulmuş, kilitli dönem öncesi** geri testten gelir:

| Alan | Değer |
|---|---|
| Dizin | `trader/research/ml/frozen/backtest_run_ml_cand_v1b_native33/` (`summary.json`, `meta.json`, `trades.csv`) |
| Strateji / dolum | `price_action_v1@1b.0`, `fill_model=native`, tetik `1h`, `trigger_source=mark`, 1 dk çözünürlük |
| Dönem | 2024-11-01 → 2026-05-01 (bitiş hariç); ilk işlem 2024-12-21 (ısınma) |
| Risk / maliyet | `target_trade_risk=0.005`; komisyon 5 bp/taraf; kayma giriş 2, piyasa çıkışı 2, stop 5 bp (`meta.json` `cost`) |
| Çiftler | kağıt botla aynı 10 çift |
| Veto | **yok** (`veto: none`); kağıtta veto zorunlu. Bu fark §4.1 ve §4.4'te hesaba katıldı |
| `trades.csv` sha256 | `5fd204a0a34be9a2ced0d55a29f6893b1de361d897016062d6d557c2a7b69061` |
| `summary.json` sha256 | `ea2f58ca9a75f77895015978ec2beb8fa3af41924f39daa541531cba5a73228c` |

Kağıt bot yapılandırması (`trader/config/engine.base.json`) risk, maliyet, çift ve strateji bakımından bu koşuyla aynıdır.

**Kilitli dönem kuralı:** kilitli dönem (2026-05-01 → 2026-11-01) bu belge için hiç okunmadı ve okunmaz. Referans değerleri yalnız kilitli dönem öncesi koşulardan gelir. İzleyici kodu referansı bu belgedeki sabitlerden alır; kilitli dönemle kesişen bir geri test çalıştırmaz (`trader_engine/holdout.py` zaten reddeder). Kağıt dönemi kilitli dönemden sonradır (2026-11-30+), çakışma yoktur.

Referans özetleri (1234 kapanmış işlem; aşağıdaki eşiklerin hepsi bunlardan türetildi):

| Ölçü | Değer |
|---|---|
| Açılan işlem / gün (ilk işlemden sonra, 496 gün) | 2,49 (günlerin %19'unda sıfır) |
| 14 günlük işlem sayısı: en az / %1 / ortanca / %99 / en çok | 18 / 21 / 34 / 54 / 58 |
| 30 günlük işlem sayısı: en az / ortanca / en çok | 49 / 75 / 102 |
| İki giriş arası en uzun boşluk | 96 saat |
| İşlem başı net R: ortalama / standart sapma / ortanca | +0,076 / 1,975 / −0,94 |
| Kazanç oranı; stop / takip stopu payı | %32,7; %50,3 / %49,5 |
| Toplam R'nin kaynağı | en iyi %5 işlem +412 R, tamamı +94 R (kâr az sayıda büyük işlemden) |
| Maliyet (komisyon + kayma) / planlanan risk, işlem başı ortalama | 0,127 R (komisyon 0,073 + kayma 0,054); 50 işlemlik ortalamanın en yükseği 0,174 |
| Ölçülen kayma: giriş / stop / takip stopu (ortalama) | 2,24 / 5,03 / 5,44 bp |
| Fonlama / planlanan risk, işlem başı ortalama | +0,0028 R (50 işlemlik ortalama aralığı −0,007 … +0,013) |
| Ortalama elde tutma | 0,67 gün |

Not: beklenen kenar (+0,076 R) işlem başı maliyetten (0,127 R) küçüktür. Bu yüzden asıl erken uyarılar sıklık, maliyet ve fonlamadır; kâr/zarar kuralı düşük güçlüdür (§4.4).

## 2. Değerlendirme penceresi

**Pencere** = aynı bot, aynı kip ve aynı kurallarla açılmış işlemler kümesi. Anahtar: (`bot`, `mode`, `strategy.name@version`, `param_version_id`, `ml.mode`).

**Pencere sıfırlama kuralı.** Aşağıdakilerden biri olduğunda eski pencere kapanır (dondurulur, silinmez) ve yeni pencere **sıfır işlemle** başlar:

1. Yeni bir parametre etkinleştirmesi (`param_activations` satırı; `kind` `apply` ya da `rollback`). Ders servisinin ya da kullanıcının her ayar değişikliği buna dahildir; hangi parametre olduğuna bakılmaz (mekanik kural, yorum yok).
2. Strateji sürümü değişikliği (`status.json` `strategy.version`).
3. ML kipinin `active` olması ya da `active`ten çıkması; `active` iken model paketinin değişmesi (`status.json` `ml.mode`, `ml.model_id`). `off` ↔ `shadow` geçişi pencereyi sıfırlamaz (kararları etkilemez).
4. Veto kipi, maliyet ayarı, çift listesi ya da `target_trade_risk` değişikliği (motor yapılandırması).
5. Kip değişimi: kağıt, testnet ve canlı ayrı pencerelerdir (ayrı defterler); birbirine eklenmez.

Bir işlem, **açıldığı** andaki pencereye aittir (`trade_entries.param_version_id`); pencere kapandıktan sonra kapanan işlem eski pencerenin sayımına girer.

**Birleşik görünüm:** raporlar bütün pencerelerin toplamını da gösterebilir, ama "birleşik, yalnız bilgi" etiketiyle; kontrol noktası kararları birleşik görünümden verilmez.

Sonuç (bilinçli): referans hızla (günde ~2,5 aday, veto sonrası daha az) bir pencerenin 100 işleme ulaşması en az 6–7 hafta sürer; her ayar değişikliği sayacı sıfırlar. Kararlar yavaş verilir. Ders servisinin sık değişiklik yapması pencerelerin hiç olgunlaşmamasına yol açarsa bu, 2. kontrol noktası raporunda mentor tarafından ayrıca bildirilir (kural değişikliği §9 yoluyla).

## 3. Kontrol noktaları ve karar kuralları

### 3.1 Kontrol noktaları

Pencere başına **kapanmış işlem sayısı** ile tanımlıdır; takvim günü ile değil.

| KN | Kapanmış işlem | Ne yapılır |
|---|---|---|
| KN-0 | 30 | Yalnız teknik uygunluk: sıklık, maliyet, fonlama, çıkış nedeni dağılımı. Kâr/zarar hakkında yargı **yazılmaz** |
| KN-1 | 100 | İlk tam rapor (§3.2'deki bütün ölçüler) |
| KN-2 | 150 | Aynı rapor |
| KN-3 | 200 | Aynı rapor; pencere için son planlı karar noktası |

Kontrol noktası raporu, pencerenin **ilk N** kapanmış işlemi üzerinden hesaplanır (çıkış zamanına, eşitlikte `trade_id`'ye göre sıralı); N'den sonraki işlemler o rapora girmez. Kontrol noktaları arasında günlük rapor yalnız ilerlemeyi gösterir ("sıradaki kontrol noktasına 37 işlem kaldı"); günlük hüküm verilmez.

200'den sonra pencere sürüyorsa her +100 işlemde aynı rapor tekrarlanır (300, 400, …).

### 3.2 Ölçüler

**Birincil (ön kayıtlı, hüküm bunlara dayanır):**

1. İşlem başı net R ortalaması ve %90 aralığı. Aralık: durağan bootstrap (`trader_core.stats.stationary_bootstrap`, `n_boot=10000`, `seed=20261117`, blok uzunluğu otomatik, yüzdelik yöntem).
2. İşlem sıklığı: pencere boyunca veto öncesi aday sayısı / gün (§4.1 tanımı) ve referansa oranı.
3. İşlem başı maliyet: (komisyon + kayma) / planlanan risk ortalaması (§4.2 M3).

**İkincil (yalnız betimleyici):** fonlama / risk; kazanç oranı; çıkış nedeni payları; ortanca R; en büyük düşüş; veto geçiş oranı (giren / veto öncesi aday); en uzun kayıp serisi.

**Alt grup kuralı:** kurulum, yön, rejim, çift ya da saat dökümleri yalnız grup başına **en az 30** kapanmış işlem varsa sayı olarak yazılır; altındaysa "yetersiz veri". Alt grup bulguları hüküm üretmez, yalnız varsayım olarak §6 defterine yazılabilir.

### 3.3 Kontrol noktası hükmü

Her kontrol noktasında tek satır hüküm:

| Hüküm | Koşul |
|---|---|
| **UYUMLU** | Sıklık, maliyet ve fonlama kurallarının hiçbiri `UYARI` düzeyinde değil; kâr/zarar bandı ve CUSUM `UYARI` vermedi |
| **İNCELE** | Yukarıdakilerden en az biri `UYARI` verdi. Mentor nedeni yazılı açıklar (veri hatası mı, motor/geri test ayrışması mı, piyasa koşulu mu). Bot çalışmaya devam eder |
| **YETERSİZ VERİ** | Bir ölçü hesaplanamadı ya da girdi eksik/sonlu değil. Eksik girdi hiçbir zaman "iyi" sayılmaz |

`İNCELE` hükmü bir **inceleme** başlatır, bir **eylem** değil. Olası sonuçlar: hata düzeltmesi (motor/veri), referansın benzer olmayanla kıyaslandığının tespiti (belgeye not), ya da "açıklanamadı, izlemeye devam". Stratejiyi ya da projeyi durdurmak bu belgenin çıktısı değildir.

### 3.4 Aday değişiklikler için kurallar ("emekli et, yeniden ayarlama")

Kağıt döneminde sınanan her aday (ders servisinin uyguladığı ayar, ikiz botun fikri, ileride gölge kurallar) için:

1. **Ölçüt önce yazılır.** Aday devreye girmeden önce hangi ölçüyle, hangi kontrol noktasında, hangi eşikle değerlendirileceği kayıtlıdır (ders servisi için `ders-spec.md` kuralları; diğerleri için §6 defteri ya da deneme defteri).
2. **Emekli et, yeniden ayarlama.** Kontrol noktasında ölçütünü tutturamayan aday geri alınır ve **aynı veride** yeni bir değerle yeniden denenmez. Aynı fikrin başka bir değeri yeni bir adaydır: yeni kayıt, yeni pencere, sıfırdan sayım.
3. **Her giriş/çıkış değişikliği yeni pencere açar** (§2). Eski pencerenin işlemleri yeni adayın lehine ya da aleyhine sayılmaz.
4. **Geriye dönük ölçüt yok.** Sonuç görüldükten sonra eklenen ölçü, eşik ya da alt grup yalnız "sonradan bakış" etiketiyle raporlanır ve hüküm üretmez.
5. **Erken bakış hüküm değildir.** Kontrol noktasından önce görülen ara sonuçla aday ne kabul ne emekli edilir (para koruma kuralları ve teknik hata hariç).

Taban strateji (v1b) bir "aday" değildir; onun için hüküm §3.3'tür ve emeklilik kuralı uygulanmaz (durdurma ölçütü yok).

## 4. Günlük sapma izleyicisi: sabit eşikler (madde 3, WP-2)

Günde bir kez (Türkiye saatiyle günlük rapordan önce), bot ve kip başına, salt okunur çalışır. Düzeyler:

| Düzey | Anlamı | Ne olur |
|---|---|---|
| `OK` | Beklenen aralıkta | Günlük raporda tek özet satır |
| `IZLE` | Olağan aralığın kenarında | Yalnız günlük raporda satır; anlık mesaj yok |
| `UYARI` | Referansta hiç görülmemiş ölçüde sapma | Günlük rapor satırı + sağlık kontrolünde `WARN`; anlık Telegram mesajı sağlık uyarı yolundan gider (`saglik-spec.md` §16.6; tekrar bastırma oradaki kurallarla). İzleyici kendisi mesaj göndermez |
| `YETERSIZ` | Asgari örnek yok ya da girdi okunamadı | Günlük raporda "henüz yeterli veri yok"; alarm değil |

`UYARI` üstü düzey **yoktur**: izleyici hiçbir zaman `CRIT` üretmez, nabzı kesmez, botu durdurmaz.

Eşitlik iyi tarafa düşer: "≤ eşik" tetiklemez, "> eşik" tetikler (alt sınırlar için tersi: "≥ eşik" tetiklemez).

### 4.0 Girdiler (bugün var olan alanlar)

| Girdi | Kaynak |
|---|---|
| Kapanmış işlemler | `<var>/<bot>/ledger.sqlite`, görünüm `v_closed_trades`: `trade_id`, `entry_ts`, `exit_ts`, `exit_reason`, `qty`, `entry_price`, `exit_price`, `planned_entry`, `planned_exit`, `planned_risk`, `fee_entry`, `fee_exit`, `funding_paid` (artı = ödenen), `slippage_entry`, `slippage_exit` (oran; artı = aleyhte), `r_multiple`, `param_version_id` |
| Kararlar | aynı defter, `v_decisions`: `bar_close_ts`, `final_action`, `skip_reason`, `veto_status`, `param_version_id` |
| Ayar değişiklikleri | `param_activations`: `activated_at`, `kind`, `version_id` |
| Motor durumu | `<var>/<bot>/status.json` (`engine-status/1`): `mode`, `strategy`, `param_version_id`, `ml`, `counters.funding_missing`, `started_at` |
| Referans | Bu belgedeki sabitler (§1, §4.4 tablosu). İstenirse `trades.csv` sha256 ile doğrulanır; izleyici referansı yeniden hesaplamaz |

Defter salt okunur açılır (`file:...?mode=ro`). Kip başına ayrı defter vardır (testnet: `var-testnet`). `r_multiple`, `planned_risk` ≤ 0 ya da sonlu olmayan satır hiçbir hesaba girmez ve sayısı raporda "atlanan satır" olarak yazılır; atlanan satır > 0 ise ilgili kural en iyi `IZLE` olabilir (sessiz temizlik yok).

### 4.1 İşlem sıklığı (asıl kural; erken güç verir)

**Tanım.** Veto öncesi aday `A` = `v_decisions` içinde `final_action='entered'` olan **ya da** `final_action='skipped'` ve `skip_reason ∈ {veto_blocked, veto_missing, veto_stale, entry_gate_closed, order_failed, ml_filter}` olan satırlar. (`stop_width`, `rr_below_min`, `risk_denied`, `other` sayılmaz: bunlar geri testte de girişe dönmez.) Zaman damgası `bar_close_ts`.

Neden bu tanım: referans koşuda veto yoktu; kağıtta veto adayların bir kısmını eler. Benzeri benzerle kıyaslamak için sayım vetodan **önce** yapılır. Bilinen küçük yanlılık: veto bir adayı eleyince o çiftte pozisyon açılmaz, sonraki sinyaller de aday olur; bu `A`'yı referansa göre biraz yukarı iter. Eşikler bunu kaldıracak kadar geniştir.

Referans hız λ₀ = 2,49 aday/gün.

| Kural | Hesap | `IZLE` | `UYARI` | Asgari koşul |
|---|---|---|---|---|
| S1 sessizlik | `now` − en son `A` satırının `bar_close_ts` (saat); hiç `A` satırı yoksa defterdeki ilk karar satırının `bar_close_ts`'i esas alınır | > 96 | > 120 | defterde en az 1 karar satırı (yoksa `YETERSIZ`) |
| S2 14 gün | `A14` = son 14×24 saatteki `A` sayısı (beklenen 34,9) | ≤ 20 ya da ≥ 55 | ≤ 15 ya da ≥ 62 | defterdeki ilk karar satırı en az 14 gün önce |
| S3 30 gün | `A30` = son 30×24 saatteki `A` sayısı (beklenen 74,7) | ≤ 51 ya da ≥ 99 | ≤ 44 ya da ≥ 108 | ilk karar satırı en az 30 gün önce |

Eşiklerin kaynağı: `IZLE` ≈ referansın %1 / %99 yuvarlanan değerleri; `UYARI` referansta 16 ayda hiç görülmemiş değerlerin dışı (14 gün: 18–58; 30 gün: 49–102) artı pay.

**Ayar değişikliği notu:** pencere içindeki sürede (son 14 / 30 gün) `initial` dışında bir parametre etkinleştirmesi varsa S2/S3'ün `UYARI`sı `IZLE`ye indirilir ve satıra "ayar değişti, kıyas yaklaşık" yazılır (referans yalnız taban ayarlar içindir). S1 indirilmez.

**Kesinti notu:** izleyici motorun kapalı kaldığı süreyi düzeltmez. Motor kapalıysa bunu sağlık kontrolleri bildirir; S1–S3 alarm metni "bot bu sürede kapalı ya da duraklatılmış olabilir" hatırlatmasını içerir.

Ek bilgi satırı (eşiksiz): veto geçiş oranı = son 14 gündeki `entered` / `A14`.

### 4.2 Gerçekleşen maliyet ↔ model maliyeti (asıl kural)

Bütün ortalamalar **en yeni** işlemlerden geriye doğru alınır (çıkış zamanına göre).

| Kural | Hesap | `IZLE` | `UYARI` | Asgari örnek |
|---|---|---|---|---|
| M1 komisyon oranı | son 20 kapanmış işlemde `fee_entry/(qty·entry_price)` ve `fee_exit/(qty·exit_price)` değerlerinin ortalaması, bp (model 5,00) | > 5,25 ya da < 4,75 | > 5,50 ya da < 4,50 | 10 işlem |
| M2-giriş kayması | son 50 girişin `slippage_entry`×10⁴ ortalaması (model b = 2,2 bp) | > 4,3 | > 6,4 | 10 dolum |
| M2-stop kayması | `exit_reason ∈ {stop, trail_stop, liquidation}` olan son 50 çıkışın `slippage_exit`×10⁴ ortalaması (b = 5,2 bp) | > 8,8 | > 12,4 | 10 dolum |
| M2-piyasa çıkışı | diğer çıkış nedenlerinde son 50 çıkış (b = 2,0 bp) | > 4,0 | > 6,0 | 10 dolum |
| M3 toplam maliyet / risk | son 50 kapanmış işlemde `(fee_entry + fee_exit + kayma_tutarı) / planned_risk` ortalaması; `kayma_tutarı = qty·planned_entry·slippage_entry + qty·P·slippage_exit`, `P = planned_exit` yoksa `exit_price`; boş kayma 0 sayılır (`metrics.enrich_trades` ile aynı). Referans 0,127 | > 0,18 | > 0,21 | 20 işlem |

M2 eşik formülü: `IZLE` > 1,5·b + 1 bp; `UYARI` > 2·b + 2 bp. `slippage_exit` boş olan çıkış M2'ye girmez.

**Kağıt kipinde** dolumlar benzetimdir; M1–M3 gerçek borsa maliyetini ölçmez. Kağıtta bu kurallar **motor öz denetimi** olarak çalışır ve ek olarak şu iki alt sınır geçerlidir (referansın 50 işlemlik aralıkları: giriş 1,91–2,54; stop/takip 4,73–6,61): giriş ortalaması < 1,5 bp ya da stop ortalaması < 4,5 bp ise `UYARI` ("benzetim modelden az maliyet yazıyor"). Alarm metninde "kağıt: benzetim tutarlılığı" ibaresi bulunur. Gerçek maliyet karşılaştırması testnet ve canlıda anlam kazanır (madde 2, WP-3 kayıt alanları).

### 4.3 Fonlama

| Kural | Hesap | `IZLE` | `UYARI` | Asgari örnek |
|---|---|---|---|---|
| F1 fonlama / risk | son 50 kapanmış işlemde `funding_paid / planned_risk` ortalaması (referans +0,0028; 50'lik aralık −0,007 … +0,013) | > 0,020 ya da < −0,020 | > 0,030 | 20 işlem |
| F2 fonlama verisi | `status.json` `counters.funding_missing` | — | > 0 | — |

Bilgi satırı (eşiksiz): fonlama yoğunluğu = Σ`funding_paid` / Σ(`qty·entry_price`·elde tutma günü) ×10⁴, bp/gün (referans 0,63; uzun 1,18, kısa 0,19).

F1 `UYARI`nın anlamı: fonlama tek başına beklenen kenarın (0,076 R) yaklaşık %40'ını yiyor.

### 4.4 Kâr/zarar bandı (düşük güçlü; yalnız bilgi ağırlıklı)

Pencerenin ilk işleminden başlayarak kümülatif net R, `C(n) = Σ r_multiple` (n = pencere içi kapanmış işlem sayısı).

Bant, referans R dizisinin durağan bootstrap'inden gelir (`stationary_bootstrap_indices`, 20 000 yol, ortalama blok 8,8 işlem, `numpy.random.default_rng(20261117)`). **Bağlayıcı olan aşağıdaki tablodur**; yöntem yalnız belgelemedir, izleyici bootstrap koşmaz.

| n | %2,5 | %10 | ortanca | %90 | sıfırın altında kalma olasılığı |
|---|---|---|---|---|---|
| 20 | −14,5 | −11,1 | −1,1 | +16,9 | %54 |
| 30 | −18,7 | −14,1 | −0,8 | +22,0 | %52 |
| 40 | −22,4 | −16,4 | −0,1 | +25,9 | %50 |
| 50 | −25,6 | −18,2 | +0,5 | +29,5 | %49 |
| 75 | −32,1 | −22,0 | +1,9 | +37,6 | %46 |
| 100 | −37,0 | −24,9 | +4,0 | +43,7 | %44 |
| 125 | −41,4 | −27,4 | +6,0 | +50,5 | %42 |
| 150 | −45,4 | −29,1 | +7,3 | +56,3 | %41 |
| 175 | −48,4 | −30,9 | +9,3 | +60,9 | %39 |
| 200 | −51,6 | −32,3 | +11,2 | +66,3 | %38 |
| 250 | −57,7 | −34,4 | +15,3 | +75,7 | %36 |
| 300 | −61,0 | −36,2 | +19,1 | +85,4 | %34 |

Ara n değerleri için komşu iki satır arasında doğrusal ara değer. n < 20: `YETERSIZ`. n > 300: son satır kullanılmaz; mentor tabloyu aynı yöntem ve tohumla uzatır (mevcut satırlar değişmez).

| Kural | `IZLE` | `UYARI` |
|---|---|---|
| P1 | `C(n)` < %10 sütunu | `C(n)` < %2,5 sütunu |

Üst taraf için kural yoktur (beklenenden iyi sonuç alarm değildir; raporda %90 sütunuyla birlikte gösterilir).

**Düşük güç notu (her K/Z satırında gösterilir):** referansın kendisi 200 işlemde %38 olasılıkla sıfırın altındadır; yani 200 işlem sonra zararda olmak tek başına bir şey söylemez. Referans kenarı (+0,076 R, standart sapma 1,975) ile şansı beceriden %95 güvenle ayırmak için yaklaşık 2 700 işlem (üç yıla yakın) gerekir. Kâr az sayıda büyük işlemden geldiği için normal dağılım varsayan bant kullanılmaz.

**Sahibe güven satırı** (günlük / haftalık rapor, sabit eşikler; pencere içi kapanmış işlem n):

| n | Satır |
|---|---|
| < 100 | "Henüz çok az işlem var (n): sonuç şans mı beceri mi ayırt edilemez." |
| 100–299 | "Erken gösterge (n işlem): yön hakkında fikir verir, kanıt değildir." |
| ≥ 300 | "n işlem birikti: hâlâ kesin kanıt değil; sıklık ve maliyet uyumu daha güvenilir göstergedir." |

Bant benzer olmayanı kıyaslar: referansta veto yok, kağıtta var. Veto kötü işlemleri eliyorsa kağıt bandın üstünde, iyi işlemleri eliyorsa altında kalır; bu yüzden P1 `UYARI`sı §3.3'te tek başına "strateji bozuldu" diye okunmaz.

### 4.5 Tek yönlü CUSUM (yalnız aşağı kol, kırpılmış R)

Amaç: küçük ama kalıcı kötüleşmeyi sabit pencere karşılaştırmasından erken yakalamak.

Pencere içinde **her** yeni kapanan işlem, çıkış sırasıyla (eşitlikte `trade_id`) bir kez işlenir; izleyici birden çok gün kaçırdıysa aradaki bütün işlemler sırayla beslenir (yalnız sonuncusu değil).

```
x_i = min(max(r_multiple_i, −1,5), +3,0)          # kırpma: üst kuyruk gürültüsünü keser (referansta işlemlerin %5,8'i > 3R)
z_i = (x_i − μ₀) / σ₀            μ₀ = −0,111   σ₀ = 1,224   (referansın kırpılmış R ortalaması ve standart sapması)
S_0 = 0
S_i = max(0, S_{i−1} − z_i − k)                    k = 0,5
```

| Kural | `IZLE` | `UYARI` |
|---|---|---|
| C1 | `S_i` ≥ 3,0 | `S_i` ≥ 4,0 |

- `UYARI` verildiğinde `S` sıfırlanır ve sonraki 30 kapanmış işlem boyunca C1 yeni `UYARI` üretmez (`IZLE` gösterilir); yorgunluk önlemi.
- Yeni pencere açıldığında `S = 0` (§2).
- Asgari örnek: pencere içinde 20 kapanmış işlem; altında düzey `YETERSIZ` olarak bildirilir. `S` yine de pencerenin **ilk** işleminden itibaren hesaplanır (ilk 20 işlem atılmaz); 20. işlemde `S` eşiğin üstündeyse düzey o an verilir.
- Durum (`S`, son işlenen `trade_id`, soğuma sayacı, pencere anahtarı) izleyicinin kendi durum dosyasında tutulur; dosya yoksa defterden baştan hesaplanır (belirleyici).

Ölçülen özellikler (referans üzerinde aynı bootstrap ile; bilgi içindir): h = 4,0 için hiçbir şey değişmemişken 200 işlem içinde yanlış alarm olasılığı ≈ %2; işlem başı −0,30 R kalıcı kötüleşme 200 işlem içinde ≈ %98 yakalanır (ortanca 45 işlem); −0,15 R ≈ %55; kenarın tamamen kaybı (−0,075 R) ≈ %20. Yani CUSUM büyük bozulmaları yakalar, kenarın sessizce sıfıra inmesini yakalamaz; bunu baştan kabul ediyoruz. h = 3,0 için yanlış alarm ≈ %14 (bu yüzden yalnız `IZLE`).

Sezgi: bir stop (−1 R) `S`'yi 0,23 artırır; `UYARI` kabaca "arada kazanan olmadan 18 stop" ya da eşdeğeri demektir.

**İkinci aşama (v1'de yok):** aynı sürümün kendi eski kağıt işlemlerini taban alan CUSUM (D-04) bir pencerede en az 50 referans + 30 yeni işlem ister. KN-1 raporunda mentor ekleyip eklememeye karar verir; eklenirse bu belgeye yeni sürüm olarak yazılır.

### 4.6 İzleyicinin çıktısı

`<var>/<bot>/drift.json` (atomik yazım; şema `drift/1`): `generated_at`, `bot`, `mode`, `window` (anahtar + başlangıç + n), `rules` (kural kimliği → `{level, value, threshold, n, note}`), `overall` (en ağır düzey), `skipped_rows`, `next_checkpoint` (`{n, remaining}`), `plan_version` (`"kdp-v1"`). Günlük rapor ve sağlık kancası yalnız bu dosyayı okur.

Günlük rapor satırları sade Türkçedir; kural kimliği, ham kod ya da İngilizce alan adı kullanıcıya gösterilmez. Örnekler:

- `📐 Bot beklendiği gibi davranıyor (sıklık, maliyet, fonlama normal) · sıradaki değerlendirmeye 37 işlem kaldı`
- `📐 İşlem sıklığı beklenenden düşük: son 14 günde 14 fırsat (beklenen yaklaşık 35). Bot durdurulmadı; inceleme gerekir.`
- `📐 Kâr/zarar: 62 işlemde −9,4 R (olağan aralık −20 … +33). Henüz çok az işlem var: sonuç şans mı beceri mi ayırt edilemez.`

## 5. Uyarı sonrası ne yapılır

1. `UYARI` geldiğinde bot çalışmaya devam eder. Kimse ayar değiştirmez.
2. Mentor en geç sonraki kontrol noktası raporunda nedeni yazar. Sıra: (a) veri/kayıt hatası mı (atlanan satır, eksik fonlama, saat), (b) motor ↔ geri test ayrışması mı (madde 9 karşılaştırması, WP-6), (c) kıyas benzer olmayanla mı (veto, ayar değişikliği, kesinti), (d) piyasa koşulu.
3. Düzeltme gerekiyorsa bu bir **hata düzeltmesidir** (motor/veri) ya da kayıtlı bir aday değişikliktir (§3.4). Uyarı tek başına ayar değişikliği gerekçesi değildir; otomatik yeniden eğitim ya da otomatik gevşetme yoktur.

## 6. Gözlemsel sorular defteri (B-09)

ML tarifi de strateji denemesi de olmayan gözlemsel sorular (ör. çıkış karnesi bulguları, kapı karnesi, alt grup varsayımları) için tek kayıt yeri: `trader/research/gozlem_defteri.csv` (deneme defterlerinin yanında; WP-4 oluşturur).

Sütunlar: `id`, `registered_at`, `soru`, `olcu` (tam formül ya da rapor alanı), `esik`, `min_n`, `min_gun`, `pencere_kurali`, `durum` (`acik` | `GECTI` | `KALDI` | `emekli`), `karar_tarihi`, `not`.

Kurallar:

1. Satır, ilgili veriye bakılmadan **önce** eklenir; eşik ve asgari n sonradan değiştirilmez (değişiklik = yeni satır, eskisi `emekli`).
2. Aynı anda en çok **8** açık satır. Dokuzuncu için önce biri karara bağlanır ya da emekli edilir. Toplam açılmış satır sayısı her raporda yazılır (balık avı sayacı).
3. Hüküm saf bir işlevle üretilir: `GECTI` / `KALDI` / `YETERSIZ`. Eksik ya da sonlu olmayan girdi her zaman `YETERSIZ`.
4. Bir soru karar verilebilir hale geldiği ilk gün günlük raporda bir satır çıkar ("X sorusu için yeterli veri birikti: sonuç …").
5. `GECTI` hükmü bir **kanıttır**, ayar değişikliği değildir; değişiklik ayrı onay ve gerekiyorsa ön kayıt ister.

## 7. Raporlama

- **Günlük (Telegram):** izleyici özeti (§4.6), sıradaki kontrol noktasına kalan işlem, güven satırı (§4.4).
- **Kontrol noktası raporu:** `trader/docs/kagit/kn-<bot>-<kip>-<pencere>-<n>.md`; §3.2 ölçüleri, §3.3 hükmü, uyarı geçmişi, açık gözlem soruları. Rapor yazıldıktan sonra değiştirilmez; düzeltme ek notla yapılır.
- **Haftalık:** birleşik görünüm (yalnız bilgi) ve pencere geçmişi (hangi değişiklik hangi gün pencereyi sıfırladı).

## 8. Uygulayıcı için kabul testleri (WP-2)

Testler sentetik defter ve sabit `now` ile yazılır; gerçek veri gerekmez.

1. **S2 sınırları:** 14 günde 21 aday → `OK`; 20 → `IZLE`; 16 → `IZLE`; 15 → `UYARI`; 54 → `OK`; 55 → `IZLE`; 62 → `UYARI`.
2. **S2 ısınma:** ilk karar satırı 13 gün önce → `YETERSIZ` (aday sayısı ne olursa olsun).
3. **Aday tanımı:** `skip_reason='stop_width'` satırları sayılmaz; `veto_blocked`, `entry_gate_closed` sayılır.
4. **S1:** son aday 96 saat önce → `OK`; 97 saat → `IZLE`; 121 saat → `UYARI`.
5. **Ayar değişikliği indirimi:** son 14 günde `apply` türü etkinleştirme varken S2 `UYARI` koşulu → `IZLE` ve not dolu; S1 indirilmez.
6. **M1:** 20 işlemde ortalama 5,00 bp → `OK`; 5,30 → `IZLE`; 5,60 → `UYARI`; 9 işlem → `YETERSIZ`.
7. **M2:** giriş ortalaması 4,3 → `OK`; 4,4 → `IZLE`; 6,5 → `UYARI`; kağıt kipinde giriş ortalaması 1,4 → `UYARI`; `slippage_exit` boş satırlar ortalamaya girmez.
8. **M3:** elle hesaplanmış 20 işlemlik örnekte formül sonucu ±1e-9 tutar; 0,18 → `OK`; 0,19 → `IZLE`; 0,22 → `UYARI`.
9. **F1/F2:** ortalama 0,020 → `OK`; 0,021 → `IZLE`; 0,031 → `UYARI`; −0,05 → `IZLE` (alt tarafta `UYARI` yok); `funding_missing=1` → F2 `UYARI`.
10. **P1 ara değer:** n = 60 için %2,5 sınırı −28,2 (−25,6 ile −32,1 arası doğrusal); `C(60) = −28,0` → `IZLE` (−19,72'nin altında), `C(60) = −28,3` → `UYARI`; n = 19 → `YETERSIZ`; n = 301 → `YETERSIZ` + "tablo uzatılmalı" notu.
11. **CUSUM formülü:** pencerenin başından art arda −1,0 R işlemler: her biri `S`'yi 0,2263 artırır (±1e-3). 13. işlemde `S` = 2,94 → `YETERSIZ` (n < 20); 14–17. işlemlerde `S` ≥ 3,0 ama n < 20 → yine `YETERSIZ`; 18. işlemde `S` = 4,07 ama n < 20 → `YETERSIZ`; 20. işlemde `S` = 4,53 → `UYARI`, ardından `S = 0` ve sonraki 30 işlemde `UYARI` yok. Ayrı örnek: önce 20 adet +0,5 R işlem (`S` = 0 kalır), sonra art arda −1,0 R: 14. kayıpta `S` = 3,17 → `IZLE`, 18. kayıpta `S` = 4,07 → `UYARI`. +10 R işlem `x = 3,0` olarak kırpılır ve `S`'yi 0'a çeker.
12. **CUSUM kaçırılan günler:** iki çalıştırma arasında 5 işlem kapandıysa beşi de sırayla işlenir; sonuç, her işlemden sonra çalıştırılmış olmakla aynıdır.
13. **Pencere sıfırlama:** yeni `param_activations` satırından sonra açılan işlemler yeni pencerede sayılır; `C(n)` ve `S` sıfırdan başlar; eski pencerenin açık işlemi kapandığında eski pencereye yazılır.
14. **Bozuk satır:** `planned_risk = 0` olan satır atlanır, `skipped_rows = 1`, ilgili kural en iyi `IZLE`.
15. **Salt okunurluk:** çalıştırma öncesi ve sonrası defter dosyasının sha256'sı aynıdır; izleyici KILL/PAUSE dosyası, emir ya da parametre yazmaz.
16. **Düzey tavanı:** hangi girdi verilirse verilsin çıktı düzeyi `OK`, `IZLE`, `UYARI`, `YETERSIZ` dışında bir değer almaz.
17. **Kilitli dönem:** izleyici kodu geri test çalıştırmaz ve `var/history` altından kilitli dönem mumlarını okumaz (içe aktarma / dosya erişimi testi).
18. **Rapor dili:** günlük rapor satırlarında kural kimliği (`S2`, `M3` …), İngilizce alan adı ya da ham kod geçmez; her K/Z satırında güven satırı bulunur.

## 9. Bu belgenin değişmesi

- Kağıt başlamadan önce: mentor serbestçe düzeltir (şu an).
- Kağıt başladıktan sonra: eşik, formül ya da kural değişikliği yalnız (a) belgelenmiş bir hesap/kod hatası için ya da (b) kontrol noktası raporunda gerekçelendirilmiş yeni sürüm (`kdp-v2`) olarak yapılır; `tasarim-kararlari.md`'ye kayıt düşülür, eski sürümün ürettiği uyarılar silinmez, yeni sürüm yalnız ileriye uygulanır. Sonuca bakıp eşik gevşetmek yasaktır.
- Referans koşu değişirse (ör. taban strateji değişti) bütün §1 ve §4 sabitleri aynı yöntemle, yalnız kilitli dönem öncesi veriden yeniden üretilir ve yeni sürüm olarak yazılır.
