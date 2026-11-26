# İşlem defteri ve parametre değişiklik günlüğü — arayüz ve kurallar (spesifikasyon v1 + Revizyon 2, 16 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


**Revizyon 2 (mentor incelemesi, ders-spec Revizyon 2 ile birlikte; şema sürüm 1 → 2):** (1) `trade_exits`'e `mfe_r`, `mae_r`, `bars_held`, `excursion_tf` eklendi (3.4, 3.4.1); (2) kanıt sayımı artık parametreye göre **havuzlanır**: ilgili parametrenin kapsamını etkilemeyen sürüm değişiklikleri kanıtı sıfırlamaz (5.4, `pool_version_ids`); (3) `propose_change(..., require_user=True)` ile herhangi bir öneri `needs_user` durumuna alınabilir (5.3 madde 11, 6.2); (4) yeni okuma yöntemleri: `pool_version_ids`, `trades_for_versions`, `aggregate_trades(version_ids=...)` (7.1); (5) `TradeRecord`'a `mfe_r`, `mae_r`, `bars_held` (7.1); (6) `SCHEMA_VERSION = 2` ve göç 1 → 2 (10.1); (7) ikiz defteri ders servisi tarafından **salt okunur** açılabilir (10.2). Mevcut `ledger.py` (şema 1) bu değişiklikler için güncellenmelidir.

**Revizyon 3 (ML-0a, faz planı 19a; `ml-faz-tasarimi.md` §4 ve §10 madde 1b; şema sürüm 2 → 3):** (1) `decision_events.skip_reason` sözlüğüne **`ml_filter`** (ML filtresinin elediği aday; `veto_status='not_evaluated'` ile yazılır) eklendi (3.3); (2) `decision_events`'e **`ml_score`** (REAL NULL, [0,1]; ML kalibre olasılığı) eklendi; `DecisionEvent.ml_score` / `DecisionRecord.ml_score` (6.1, 7.1); (3) `SCHEMA_VERSION = 3` ve göç 2 → 3 (10.3). Ekleyici içerik: yeni sütun NULL; mevcut satır değişmez/silinmez. SQLite bir CHECK'i değiştiremediği için göç `decision_events`'i **yeniden kurar** (10.3); bu bir "ekleme türü" göçtür ama yeniden kurma yordamı kullanır. `ml_score` idempotent karşılaştırmaya dahil **değildir** (3.3).

**Revizyon 4 (WP-3, `defter-ek-alanlar-spec.md`; şema sürüm 3 → 4):** (1) `trade_entries`'e beş, `trade_exits`'e yedi **ekleyici NULL** sütun: emir anı alanları (`order_ts`, `order_ack_ts`, `order_ref_price`, `order_ref_spread`, `order_ref_src`) ve çıkışta `decision_price`, `exit_regime`; `v_trades`/`v_closed_trades` sona on beş sütun alır (mevcut sütunlar aynı sırada); (2) yeni append-only tablolar `shadow_decisions` (+ `v_shadow_decisions`) ve `equity_marks`; gölge satır `decision_events`/`v_decisions`'a girmez; (3) `Ledger.record_shadow`, `record_equity_mark`, `list_shadow`, `list_equity_marks`, `clean_exec_fields`; bu iki yazım `_on_write_failure`, spool ve `_last_write_ok`'a **dokunmaz**; (4) ölçüm alanları idempotans karşılaştırmasına dahil değildir; (5) `SCHEMA_VERSION = 4`, göç 3 → 4 (tablo yeniden kurulmaz, `premigrate-v3` yedeği).

Kaynak kurallar: `otonom-trading-arastirma/mimari-taslak.md` (parça 7, 8, 9), `strateji-v1.md` (Bölüm 4–6: T1/R1, parametreler, ders servisi sınırları), `tasarim-kararlari.md` (15–16 Kasım bölümü: öğrenme ilk günden açık, ≥20–30 işlem kanıtı, değişiklik günlüğü, geri alma). Şekil uyumu: `risk-kilidi-spec.md` (`Decision`, `Candidate`, `SizeResult`) ve `rejim-spec.md` (`RegimeResult`, `Regime`). Bu belge kod ve test içermez; testler bu belgeden yazılır. Sayılar kârlılık kanıtı değildir.

Modül: `src/trader_core/ledger.py`. Yalnızca standart kütüphane (`sqlite3`, `json`, `hashlib`, `dataclasses`, `datetime`, `os`); pandas/numpy ve freqtrade import edilmez. Hata durumunda her zaman kapalı (fail-closed): defter yazılamıyorsa yeni işlem açılmaz.

## 1. Genel ilkeler

- **Bot başına bir veritabanı dosyası.** `bot ∈ {"learner", "twin"}`. Dosya adı çağıranın seçimi (öneri: `user_data/ledger_learner.sqlite`, `ledger_twin.sqlite`). Her satırda `bot` sütunu da bulunur; defter açılırken `meta.bot` ile istenen bot eşleşmezse `LedgerSchemaError`.
- **WAL modu** (`PRAGMA journal_mode=WAL`), `synchronous=FULL` (güç kesintisinde son işlem kaybolmasın; yazma hacmi düşük), `foreign_keys=ON`, `busy_timeout=5000` ms. WAL dosyaları aynı makinede ve yerel dosya sisteminde olmalıdır (docker volume olur; ağ paylaşımı olmaz).
- **Yalnızca ekleme (append-only).** Her tabloda `BEFORE UPDATE` ve `BEFORE DELETE` tetikleyicileri `RAISE(ABORT, 'append-only')` verir. Geçmiş değiştirilmez; düzeltme, `supersedes_id` ile eski satırı işaret eden **yeni bir olaydır**. "Geçerli" satır, zincirin en sonudur (görünümler `v_*`, Bölüm 3.7). Tetikleyiciler güvenlik sınırı değil, kazara değişikliğe karşı korumadır (dosyaya erişen biri tetikleyiciyi düşürebilir; hash zinciri v1'de yok).
- **Sıralama gerçeği satır `id`'sidir** (INTEGER PRIMARY KEY AUTOINCREMENT), saat değil. Saat geriye giderse bile olay sırası bozulmaz.
- **Para birimi:** hepsi quote para (USDT), `REAL`. Sonlu olmayan sayı (NaN/inf), `bool`, `None` (zorunlu alanda), metin → `LedgerValidationError`. Sayı kabulü `risk-kilidi-spec.md` ile aynı (`int`/`float`/`numbers.Real`, `float()` ile dönüştürülür).
- **Yan etkisiz doğrulama:** her yazma fonksiyonu önce girdiyi doğrular; doğrulama hatasında hiçbir şey yazılmaz.

## 2. Hatalar

| Sınıf | Taban | Ne zaman |
|---|---|---|
| `LedgerError` | `Exception` | Tüm defter hatalarının tabanı |
| `LedgerValidationError` | `LedgerError`, `ValueError` | Girdi geçersiz (tür, aralık, biçim, bilinmeyen anahtar) |
| `LedgerConflictError` | `LedgerError` | Aynı doğal anahtarla **farklı içerik** yazma girişimi |
| `LedgerWriteError` | `LedgerError` | Disk dolu, kilit zaman aşımı, salt okunur dosya, I/O hatası; her `sqlite3.Error` bu sınıfa sarılır |
| `LedgerSchemaError` | `LedgerError` | Şema sürümü koddan yeni, bozuk dosya, `bot` uyuşmazlığı, eksik tetikleyici |
| `LedgerStateError` | `LedgerError` | Etkin parametre yok, `init_params` ikinci kez, ikiz botta yasak işlem |

Ders servisinin **politika ret'leri** (sınır dışı, kanıt yetersiz vb.) istisna değil, `ProposalResult`/`ActivationResult` içinde `ok=False` + `code` olarak döner (Bölüm 5). Sistem hataları (`LedgerWriteError` vb.) her zaman istisnadır.

## 3. Şema (sürüm 3; sürüm 1'den göç için 10.1, sürüm 2'den 10.3)

### 3.1 Zaman ve kimlik kuralları (tüm tablolar)

- Zaman damgaları metin: `YYYY-MM-DDTHH:MM:SS.mmmZ`, UTC, sabit genişlik (sözlük sırası = zaman sırası). Python tarafında `datetime` kabul edilir; **tz-naive reddedilir** (`LedgerValidationError`), tz-aware olan UTC'ye çevrilip milisaniyeye **aşağı** yuvarlanarak yazılır.
- `bar_close_ts` mumun **kapanış** zamanıdır (açılış + zaman dilimi). `rejim-spec.md` indeksi mum **açılış** zamanıdır; dönüşüm (açılış + 1s) çağıranın işidir, defter dönüştürmez. Doğrulama: `bar_close_ts` 15 dakikanın tam katı (saniye ve ms = 0) olmalı ve `recorded_at + 5 sn`'den ileri olmamalı.
- `recorded_at`: defterin saati (enjekte edilebilir `clock`, varsayılan `datetime.now(UTC)`). Çağıran vermez.
- `bot`, her tabloda `CHECK (bot IN ('learner','twin'))`.
- Metin alanı üst sınırları: `reason` ≤ 500 karakter; JSON alanları (`features`, `params`, `evidence`, `proposal`) serileştirilmiş ≤ 16 KiB. Aşım → `LedgerValidationError`.
- JSON alanları kanonik biçimde yazılır: `json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)`.

### 3.2 `meta` (tek satırlık yapılandırma; yalnızca `INSERT` ile bir kez)

`key TEXT PRIMARY KEY`, `value TEXT`. Anahtarlar: `bot`, `created_at`, `schema_version`. Güncellenemez (tetikleyici). Şema sürümünün asıl kaynağı `PRAGMA user_version`'dır; `meta.schema_version` aynasıdır, ikisi farklıysa `LedgerSchemaError`.

### 3.3 `decision_events` — her aday sinyal

Aday sinyal = bir kurulumun (T1/R1) tetik koşulunun 1s (veya `trigger_tf=15m` kolunda 15dk) mum kapanışında tuttuğu her durum. Rejim `volatile`/`unclear` iken kurulum tetiklenmez, kayıt yazılmaz. Kurulum içi eleme (stop mesafesi 0,5–2,0 × ATR dışı, `rr_min` altı) **kayıt yazılır** (`skipped`).

| Sütun | Tür | Not |
|---|---|---|
| `id` | INTEGER PK | |
| `bot` | TEXT | |
| `bar_close_ts` | TEXT | tetik mumunun kapanışı, UTC |
| `trigger_tf` | TEXT | `"1h"` veya `"15m"` |
| `pair` | TEXT | normalleştirilmiş: büyük harf, `:USDT` sonrası atılmış (`"ETH/USDT"`), `risk-kilidi-spec.md` ile aynı |
| `side` | TEXT | `"long"`/`"short"` (boşluk kırpılır, küçük harf) |
| `setup` | TEXT | `"T1"` / `"R1"` |
| `regime` | TEXT | `Regime` değeri: `trend_up`, `trend_down`, `range`, `volatile`, `unclear` (kurulum tetiklendiği için pratikte ilk üçü) |
| `atr_ratio` | REAL NULL | `RegimeResult.atr_ratio` |
| `rh`, `rl` | REAL NULL | `RegimeResult.rh/rl`; `regime=range` iken **dolu olmak zorunda**, aksi halde NULL olmak zorunda (CHECK) |
| `rh_touches`, `rl_touches` | INTEGER | `RegimeResult`'tan; range dışında 0 |
| `features` | TEXT (JSON) | Bölüm 3.3.1 |
| `planned_entry`, `planned_stop` | REAL | kural motorunun ürettiği giriş (tetik mumu kapanışı) ve stop |
| `planned_target` | REAL NULL | R1'de dolu, T1'de NULL (sabit hedef yok) |
| `param_version_id` | INTEGER FK | kararı üreten etkin parametre sürümü |
| `veto_status` | TEXT | `allowed`/`blocked`/`missing`/`stale`/`not_evaluated` |
| `veto_reason` | TEXT NULL | `blocked` iken Claude'un gerekçesi; `missing`/`stale` için neden kodu; diğerlerinde NULL olabilir |
| `risk_allowed` | INTEGER NULL | 1/0; risk kilidi değerlendirilmediyse NULL |
| `risk_reason` | TEXT NULL | `Decision.reason` aynen |
| `size_qty`, `size_notional`, `size_margin`, `size_risk_amount` | REAL NULL | `Decision.size` (`SizeResult`); `risk_allowed=1` ise dolu |
| `leverage` | INTEGER NULL | `risk_allowed=1` ise dolu |
| `final_action` | TEXT | `entered` / `skipped` |
| `skip_reason` | TEXT NULL | `skipped` ise zorunlu, kod: `stop_width`, `rr_below_min`, `veto_blocked`, `veto_missing`, `veto_stale`, `risk_denied`, `entry_gate_closed`, `order_failed`, `other`, `ml_filter` (şema 3: ML filtresi adayı eledi ya da `active` modda model yok/süresi dolmuş ⇒ yeni giriş yok; motor 05 §13.4a) |
| `supersedes_id` | INTEGER NULL FK | düzeltme olayı ise eski satır |
| `recorded_at` | TEXT | |
| `ml_score` | REAL NULL | şema 3. ML filtresinin kalibre olasılığı (`price_action_v1_ml`, `shadow` ve `active`); `[0,1]` dışı ⇒ `LedgerValidationError` + `CHECK`. `off` modunda ve ML'siz stratejide NULL. `entered` kararlar da taşıyabilir (gölge/aktif geçişi). Boyutu/kararı etkilemez; gece işi etiketleme ve rapor içindir |

`not_evaluated` bu belgenin eklediği beşinci veto değeridir: kurulum içi eleme (stop genişliği, `rr_min`) veto'dan önce olur; veto'ya hiç sorulmayan adayı `allowed` diye yazmak yanıltıcı olur. İstenen dört değer aynen korunur.

Tutarlılık kuralları (CHECK + yazma doğrulaması): `final_action='entered'` ⇒ `veto_status='allowed'` ve `risk_allowed=1` ve `size_*`/`leverage` dolu ve `skip_reason` NULL. `veto_status ∈ {blocked, missing, stale}` ⇒ `final_action='skipped'` ve `skip_reason` buna uygun (`veto_*`). `risk_allowed=0` ⇒ `skipped`, `skip_reason='risk_denied'`. `veto_status='not_evaluated'` ⇒ `risk_allowed` NULL, `skip_reason ∈ {stop_width, rr_below_min, other, entry_gate_closed, ml_filter}`.

`ml_filter` yalnız `final_action='skipped'` ve `veto_status='not_evaluated'` ile yazılır (veto/risk hiç değerlendirilmedi; ML elemesi kapı zincirinden **önce** olur, `stop_width`/`rr_below_min` gibi). Yazma doğrulaması `ml_filter`'ı `not_evaluated` kümesine (`_NOT_EVAL_SKIP`) ve genel sözlüğe (`_SKIP`) ekler.

Benzersizlik: `UNIQUE (bot, pair, side, setup, trigger_tf, bar_close_ts) WHERE supersedes_id IS NULL`. Aynı mum için aynı içerikle ikinci yazma (freqtrade döngüsü tekrar çalışır) **idempotent**: var olan `id` döner. Farklı içerik → `LedgerConflictError` (düzeltme için `supersedes_id` kullanılır). "Aynı içerik" karşılaştırması `id`, `recorded_at`, `supersedes_id` dışındaki tüm alanlardadır; **istisna:** `ml_score` karşılaştırmaya girmez (motor yeniden oynatmasında `ml_mode` farkı `LedgerConflictError` üretmesin; ilk yazılan kazanır).

#### 3.3.1 `features` anahtarları (zorunlu; fazlası serbest, ders servisi yalnızca bunları bilir)

- Ortak: `atr_1h` (veya `atr_tf`, trigger_tf için ATR14), `stop_dist_atr` (|giriş − stop| / ATR14(tf)), `atr_4h`.
- T1: `pullback_ema` (20/50), `ema_value`, `body_ratio` (gövde/range).
- R1: `wick_ratio` (ilgili fitil/range), `rr` ((hedef − giriş)/(giriş − stop)), `edge_dist_atr` (kenara uzaklık, ATR cinsinden).
Eksik zorunlu anahtar → `LedgerValidationError`. Değerler sonlu sayı.

### 3.4 `trade_entries` ve `trade_exits` — işlemler

İşlem = freqtrade `trade_id` (tam sayı, bot başına tekil). Giriş ve çıkış ayrı olaylardır (`UPDATE` yok).

`trade_entries`:

| Sütun | Tür | Not |
|---|---|---|
| `id` | INTEGER PK | |
| `bot` | TEXT | |
| `trade_id` | INTEGER | freqtrade `trade_id` |
| `decision_id` | INTEGER FK | `final_action='entered'` olan karar; başka karara bağlanamaz (doğrulama) |
| `param_version_id` | INTEGER FK | kararın sürümü ile aynı olmak zorunda (doğrulama) |
| `pair`, `side`, `setup` | TEXT | karardakiyle aynı olmak zorunda (doğrulama) |
| `entry_ts` | TEXT | gerçekleşen dolum zamanı (UTC) |
| `entry_price` | REAL | gerçekleşen ortalama giriş fiyatı |
| `planned_entry`, `planned_stop`, `planned_target` | REAL | karardan kopyalanır (okumayı kolaylaştırır; kopya tutarlılığı doğrulanır) |
| `qty` | REAL | |
| `leverage` | INTEGER | |
| `planned_risk` | REAL | karardaki `size_risk_amount` (komisyon+kayma dahil planlanan zarar); R'nin paydası |
| `fee_entry` | REAL | ≥ 0, quote |
| `slippage_entry` | REAL | göreli, işaretli; aşağıda |
| `supersedes_id` | INTEGER NULL | |
| `recorded_at` | TEXT | |

`UNIQUE (bot, trade_id) WHERE supersedes_id IS NULL`.

`trade_exits`:

| Sütun | Tür | Not |
|---|---|---|
| `id` | INTEGER PK | |
| `bot`, `trade_id` | | `trade_id` için geçerli bir giriş zorunlu |
| `exit_ts` | TEXT | ≥ `entry_ts` |
| `exit_price` | REAL | gerçekleşen ortalama çıkış |
| `exit_reason` | TEXT | `stop`, `target`, `trail_stop`, `regime_flip`, `time_stop`, `manual`, `force_exit`, `liquidation`, `other` |
| `planned_exit` | REAL NULL | `stop`/`trail_stop`/`target` çıkışlarında borsadaki planlanan fiyat; diğerlerinde NULL |
| `fee_exit` | REAL | ≥ 0 |
| `funding_paid` | REAL | **ödenen pozitif, alınan negatif**; işlem süresince toplam |
| `gross_pnl` | REAL | fiyat farkı kârı: long `qty·(exit − entry)`, short `qty·(entry − exit)` |
| `realized_pnl` | REAL | **net** = `gross_pnl − fee_entry − fee_exit − funding_paid` |
| `r_multiple` | REAL | `realized_pnl / planned_risk` |
| `slippage_exit` | REAL NULL | `planned_exit` NULL ise NULL |
| `mfe_r` | REAL NULL | **(şema 2)** işlem süresince azami lehte sapma, R cinsinden, ≥ 0 (3.4.1) |
| `mae_r` | REAL NULL | **(şema 2)** işlem süresince azami aleyhe sapma, R cinsinden, ≥ 0 (3.4.1) |
| `bars_held` | INTEGER NULL | **(şema 2)** işlemde geçen 15 dk'lık mum kapanışı sayısı (3.4.1) |
| `excursion_tf` | TEXT NULL | **(şema 2)** sapmanın hesaplandığı mum dilimi: `1m` / `5m` / `15m` |
| `supersedes_id` | INTEGER NULL | |
| `recorded_at` | TEXT | |

`UNIQUE (bot, trade_id) WHERE supersedes_id IS NULL`. CHECK: `mfe_r`, `mae_r`, `excursion_tf` ya üçü birden NULL ya üçü birden dolu; `mfe_r ≥ 0`, `mae_r ≥ 0`; `bars_held ≥ 0` (NULL olabilir).

**Türetilen alanlar defter tarafından hesaplanır, çağıran vermez** (tutarsızlık imkânsız olsun): `gross_pnl`, `realized_pnl`, `r_multiple`, `slippage_*`. Çağıran ham fiyat, miktar, komisyon, funding verir. `fee_entry` giriş kaydında, `fee_exit`/`funding_paid` çıkış kaydındadır.

#### 3.4.1 MFE / MAE ve `bars_held` (şema 2)

Çıkış kaydında çağıran **ham uç fiyatları** verir (`TradeExit.max_favorable_price`, `max_adverse_price`, `excursion_tf`); defter `mfe_r`, `mae_r`, `bars_held` değerlerini kendisi hesaplar (diğer türetilen alanlarla aynı ilke).

- **Uç fiyatlar (çağıranın işi):** `entry_ts` ile `exit_ts` arasındaki mumlardan alınır. `excursion_tf` ayrıntı varsa `1m`, yoksa `5m`, yoksa `15m`. Dahil mumlar: `[entry_ts, exit_ts]` aralığıyla kesişen tüm mumlar (dolum anını ve çıkış anını içeren mumlar dahil; bunlar dolumdan önceki/çıkıştan sonraki kısmı da kapsayabilir, dilim inceldikçe bu yanlılık küçülür; `15m` diliminde sapma hafifçe abartılır ve bu `excursion_tf` ile kaydedilir). Long: `max_favorable_price` = dahil mumların en yüksek `high`'ı, `max_adverse_price` = en düşük `low`'u. Short: tersi (`max_favorable_price` = en düşük `low`, `max_adverse_price` = en yüksek `high`).
- **Hesap (defter):** `sgn = +1` (long), `−1` (short). `mfe_r = max(0, sgn·(max_favorable_price − entry_price)·qty / planned_risk)`; `mae_r = max(0, sgn·(entry_price − max_adverse_price)·qty / planned_risk)`. Pay brüt fiyat hareketidir (komisyon/funding hariç), payda `r_multiple` ile **aynı** `planned_risk`'tir (R birimi tutarlı; `gross_pnl/planned_risk ≤ mfe_r` karşılaştırılabilir). 6 ondalığa yuvarlanır.
- **`bars_held`** = `entry_ts < c ≤ exit_ts` koşulunu sağlayan 15 dk mum **kapanış** zamanı `c` sayısı = `floor(exit_ts / 15dk) − floor(entry_ts / 15dk)` (UTC epoch dakikası tam bölme). Tetik dilimi 1s olsa da birim sabit 15 dk'dır.
- **Doğrulama (`LedgerValidationError`):** üç uç alan ya birlikte verilir ya birlikte `None` (o zaman `mfe_r/mae_r/bars_held/excursion_tf` NULL kalır; **`bars_held` yine hesaplanır**, bu durumda `excursion_tf` NULL, `bars_held` dolu olabilir: CHECK yalnızca `mfe_r/mae_r/excursion_tf` üçlüsünü bağlar); fiyatlar > 0; long için `max_favorable_price ≥ max(entry_price, exit_price)` ve `max_adverse_price ≤ min(entry_price, exit_price)`, short için tersi. İhlal: kayıt reddedilir (uç fiyat, gerçekleşen fiyatlardan daha ılımlı olamaz).
- **Eksik veri:** mum verisi alınamazsa çağıran `None` verir; işlem yine kaydedilir (`mfe_r` NULL). Ders servisi NULL olanları ilgili kural için dışarıda bırakır (`excluded_missing_excursion`). Şema 1'den göçen eski işlemler NULL kalır (append-only; geriye dönük doldurma yok; 10.1).
- Sonradan düzeltme gerekirse yeni çıkış satırı (`supersedes_id`); eski satır değişmez.

**Kayma işareti:** pozitif = olumsuz (aleyhe). Giriş: long `(entry_price − planned_entry)/planned_entry`, short `(planned_entry − entry_price)/planned_entry`. Çıkış: long `(planned_exit − exit_price)/planned_exit`, short `(exit_price − planned_exit)/planned_exit`. Göreli oran (kesir), yüzde değil.

**R-multiple:** `planned_risk > 0` zorunlu (≤ 0 → `LedgerValidationError`). R, kayıt anındaki `planned_risk`'e göre hesaplanır; sonradan yeniden hesaplanmaz (düzeltme gerekirse yeni çıkış satırı).

Çıkış kaydı, işlem başka bir çıkışla zaten kapalıysa (`supersedes_id` yok) `LedgerConflictError`. Aynı içerikle tekrar yazma idempotent (var olan `id`).

### 3.5 `param_versions` — değişmez anlık görüntüler

| Sütun | Tür | Not |
|---|---|---|
| `id` | INTEGER PK | sürüm numarası (`version_id`), 1'den başlar |
| `bot` | TEXT | |
| `params` | TEXT (JSON) | tam 9 anahtar (Bölüm 5.1) |
| `params_hash` | TEXT | `sha256(kanonik params JSON)` onaltılık küçük harf, 64 karakter |
| `lesson_bounds` | TEXT (JSON) | ders servisinin bu sürümde dokunabileceği 5 parametrenin `[alt, üst]` sınırları |
| `parent_version_id` | INTEGER NULL FK | türetildiği sürüm; `initial` için NULL |
| `author` | TEXT | `initial` / `lesson` / `user` |
| `reason` | TEXT | zorunlu, boş olamaz |
| `evidence` | TEXT (JSON) NULL | `lesson` için zorunlu (Bölüm 5.4); diğerlerinde NULL olabilir |
| `proposal_id` | INTEGER NULL FK | `lesson` sürümü için ilgili öneri |
| `created_at` | TEXT | |

`params_hash` benzersiz **değildir** (aynı parametre farklı `lesson_bounds` ile yeniden oluşturulabilir; ikiz ile öğrenen botun başlangıç hash'inin eşitliği ayrıca doğrulanır). İki bot arasında hash karşılaştırması serbesttir.

### 3.6 `param_activations` — etkin işaretçi olayları

| Sütun | Tür | Not |
|---|---|---|
| `id` | INTEGER PK | etkin sürüm = en yüksek `id`'li satırın `version_id`'si |
| `bot` | TEXT | |
| `version_id` | INTEGER FK | |
| `prev_version_id` | INTEGER NULL | bu olaydan önce etkin olan sürüm; ilk olayda NULL |
| `kind` | TEXT | `initial` / `apply` / `rollback` |
| `actor` | TEXT | `system` (initial), `lesson`, `user` |
| `reason` | TEXT | zorunlu |
| `proposal_id` | INTEGER NULL FK | `apply` ise |
| `activated_at` | TEXT | |

Geri alma = önceki bir sürümü yeniden etkinleştirmek: **yeni sürüm yaratılmaz**, `kind='rollback'` olayı yazılır. İlk satır mutlaka `kind='initial'`; sonrakilerde `initial` yasak.

### 3.7 `lesson_proposals` ve `proposal_status_events`

`lesson_proposals` (değişmez öneri):

| Sütun | Tür | Not |
|---|---|---|
| `id` | INTEGER PK | `proposal_id` |
| `bot` | TEXT | yalnızca `learner` |
| `base_version_id` | INTEGER FK | önerinin dayandığı (öneri anında etkin) sürüm |
| `proposal` | TEXT (JSON) | `{"changes": {"rr_min": 1.25}, "rationale": "..."}` |
| `claimed_evidence` | TEXT (JSON) | ders servisinin beyanı (ör. `{"n_closed": 24}`); **bağlayıcı değil**, defter kendi sayımını yapar |
| `source` | TEXT | ör. `"claude-sonnet-5.5-batch"`; boş olamaz |
| `created_at` | TEXT | |

Öneri satırı değişmezdir; uygulanınca yaratılan sürümle bağ `proposal_status_events.version_id` ve `param_versions.proposal_id` üzerindedir.

`proposal_status_events`:

| Sütun | Tür | Not |
|---|---|---|
| `id` | INTEGER PK | |
| `proposal_id` | INTEGER FK | |
| `status` | TEXT | `proposed` / `applied` / `rejected` / `needs_user` |
| `code` | TEXT | makine kodu (Bölüm 5.3) |
| `reason` | TEXT | insan metni |
| `version_id` | INTEGER NULL FK | `applied` ise yaratılan/etkinleştirilen sürüm |
| `actor` | TEXT | `lesson` / `user` / `system` |
| `recorded_at` | TEXT | |

Geçerli durum = o `proposal_id`'nin en yüksek `id`'li olayı. İzinli geçişler: `∅ → proposed | needs_user | rejected`; `proposed → applied | rejected`; `needs_user → applied | rejected`; `applied` ve `rejected` terminaldir. Diğer geçişler `LedgerStateError`.

### 3.8 Görünümler (salt okunur, `CREATE VIEW`)

- `v_decisions`: `supersedes_id` zincirinin geçerli (kendisini kimse yerine geçirmemiş) kararları.
- `v_trades`: geçerli giriş + geçerli çıkış birleşimi (`LEFT JOIN`; çıkışı yoksa açık işlem), karar ve `regime`, `atr_ratio` ile birleşik; şema 2'den itibaren `mfe_r`, `mae_r`, `bars_held`, `excursion_tf` de dahildir (göçte görünümler yeniden kurulur, 10.1).
- `v_closed_trades`: `v_trades` içinde çıkışı olanlar. **Bütün okuma ve toplulaştırma fonksiyonları yalnızca bu görünümleri kullanır**, ham tabloları değil.
- `v_proposals`: öneri + geçerli durum.

### 3.9 `health_probes`

`id`, `bot`, `probed_at`. Yalnızca `check_writable()` (Bölüm 7.2) ekler; append-only.

## 4. Açma, kapatma, enjekte edilebilirlik

```
open_ledger(path: str | os.PathLike, bot: str, *, create: bool = True,
            read_only: bool = False, migrate: bool | None = None,
            clock: Callable[[], datetime] | None = None,
            min_evidence_trades: int = 20) -> Ledger
class Ledger:
    bot: str
    min_evidence_trades: int
    def close(self) -> None
    def backup(self, dest_path: str | os.PathLike) -> None
```

- `read_only=True`: SQLite URI `file:…?mode=ro` (ders servisinin okuma bağlantısı); tüm yazma fonksiyonları `LedgerStateError`. `create=False` ve dosya yoksa `LedgerSchemaError`.
- `migrate=None` ⇒ `read_only` değilse `True`, değilse `False` (Bölüm 8).
- `min_evidence_trades < 20` → `LedgerValidationError` (alt sınır 20 sabit; yalnızca yukarı yapılandırılabilir). Varsayılan 20.
- `clock` yalnızca test içindir; üretimde verilmez. `Ledger` iş parçacığı başına bağlantı kullanır (`threading.local`); bir `Ledger` nesnesi iş parçacıkları arası paylaşılabilir, bağlantı paylaşılmaz.
- `backup(dest)`: `sqlite3.Connection.backup` ile tutarlı kopya (günlük yedek için; mimari taslak "günlük veritabanı yedeği"). Hedef dosya varsa `LedgerValidationError`.
- Bağlantı açılışında şema denetimi: tüm `BEFORE UPDATE/DELETE` tetikleyicileri mevcut olmalı; eksikse `LedgerSchemaError` (fail-closed).

## 5. Parametre sözlüğü ve doğrulama kuralları

### 5.1 `params` (tam 9 anahtar; eksik/fazla anahtar → `LedgerValidationError`)

| Anahtar | Tür | Tarama aralığı (geçerlilik, uçlar dahil) | Ders servisi | Ders sınırı (varsayılan `lesson_bounds`) | Tek öneride en fazla değişim (`STEP`) | Kanıt kapsamı |
|---|---|---|---|---|---|---|
| `range_width_atr` | float | 3.0 – 6.0 | Hayır | — | — | — |
| `vol_ratio_max` | float | 1.25 – 2.0 | Evet | 1.3 – 1.7 | 0.25 | T1+R1 |
| `edge_zone_atr` | float | 0.15 – 0.50 | Hayır | — | — | — |
| `pullback_ema` | int ∈ {20, 50} | — | Hayır | — | — | — |
| `stop_buffer_atr` | float | 0.1 – 1.0 | Evet | 0.2 – 0.5 | 0.1 | T1+R1 |
| `trail_atr` | float | 2.0 – 4.0 | Evet | 2.5 – 3.5 | 0.5 | T1 |
| `range_target_frac` | float | 0.5 – 1.0 | Evet | 0.6 – 0.9 | 0.125 | R1 |
| `rr_min` | float | 1.0 – 2.0 | Evet | 1.2 – 2.0 | 0.25 | R1 |
| `trigger_tf` | str ∈ {"1h", "15m"} | — | Hayır | — | — | — |

Kaynak: `strateji-v1.md` Bölüm 2 ve 6.1 (ve `rejim-spec.md` `RegimeParams` aralıkları; ikisi eşit olmak zorunda). Modül sabitleri: `PARAM_SPECS` (yukarıdaki tablo), `LESSON_PARAMS = ("vol_ratio_max", "stop_buffer_atr", "trail_atr", "range_target_frac", "rr_min")`, `LESSON_BOUNDS_DEFAULT`, `LESSON_STEP`, `LESSON_MIN_INTERVAL_DAYS = 7`. Float'lar yazılırken `round(x, 6)` ile normalleştirilir; `pullback_ema` tam sayı, `trigger_tf` metin. Aralık karşılaştırması normalleştirilmiş değerle, uçlar dahil.

### 5.2 Sürüm yaratma kuralları

- `author="initial"`: yalnızca defter boşken (`param_activations` yok) ve yalnızca `init_params` ile. Tüm 9 anahtar tarama aralığında. `lesson_bounds` verilmezse varsayılan; verilirse her `[alt, üst]` hem tarama aralığında hem `alt ≤ üst`, hem de **başlangıç değerini içermeli**. (Backtest sonrası sınırların yeniden ortalanması: `strateji-v1.md` 6.1 son maddeler; sınırlar yalnızca `initial` ve `user` sürümlerinde değişebilir.)
- `author="user"`: kullanıcının doğrudan sürümü (Telegram komutu/yeni backtest sonucu). 9 anahtarın hepsi tarama aralığında, istenirse `lesson_bounds` yeniden verilebilir. Kanıt şartı **yok**, `reason` zorunlu. Bu, ders servisinin dokunamadığı parametrelerin (1, 3, 4, `trigger_tf`) değişebildiği tek yoldur.
- `author="lesson"`: yalnızca `apply_proposal` ile (Bölüm 6.3); `params`, ana sürümden yalnızca **tek** `LESSON_PARAMS` anahtarı kadar farklı olabilir; `lesson_bounds` ana sürümden aynen devralınır.
- Yeni `params` etkin sürümle birebir aynı (`params_hash` eşit) ise: `code="no_change"`, sürüm yaratılmaz.

### 5.3 Öneri doğrulama kod listesi (`code`)

Öneri `propose_change` ile yazılırken sırayla denetlenir; ilk ihlal öneriyi `rejected` yapar (öneri yine de **deftere yazılır**, denetim izi için; istisna atılmaz).

| Sıra | Kod | Koşul |
|---|---|---|
| 1 | `twin_forbidden` | bot `twin` (istisna: `LedgerStateError`, öneri yazılmaz) |
| 2 | `stale_base` | `base_version_id` ≠ öneri anındaki etkin sürüm |
| 3 | `empty_changes` | `changes` boş |
| 4 | `multiple_changes` | `changes`'te birden fazla anahtar |
| 5 | `unknown_param` | anahtar 9 anahtardan biri değil |
| 6 | `immutable_param` | anahtar `LESSON_PARAMS` dışında |
| 7 | `bad_value` | tür/biçim geçersiz veya NaN/inf/bool |
| 8 | `out_of_bounds` | yeni değer, **ana sürümün `lesson_bounds`** aralığı dışında (uçlar dahil) |
| 9 | `step_too_large` | `\|yeni − eski\| > STEP[param]` (kayan nokta için `1e-9` toleransı) |
| 10 | `no_change` | yeni değer = eski değer |
| 11 | `needs_user` (durum, ret değil) | `vol_ratio_max` **artırılıyorsa** (gevşetme, `strateji-v1.md` 6.1) **veya** çağıran `require_user=True` verdiyse (ders servisi bunu gölge dönemde her öneri için, ayrıca `stop_buffer_atr` artışı ve diğer kullanıcıya-sorulur sınıflar için verir; ders-spec 8.3). 1–10. kurallardan biri ihlal edilmişse yine `rejected` |

"Bir adım" bu belgede **"tek öneride değişim ≤ tarama adımı"** olarak okunur (tam kat zorunlu değil): `vol_ratio_max` tarama adımı 0.25 iken ders sınırı genişliği 0.4 olduğundan, kat zorunluluğu 1.5 → 1.3'ü bile engellerdi.

`needs_user` durumundaki öneri (kural 11 ister `vol_ratio_max` artışı ister `require_user` yüzünden), kullanıcı `apply_proposal(..., actor="user")` çağırana kadar bekler; `actor="lesson"` ile uygulanamaz (`code="user_approval_required"`). `needs_user` kodu, `require_user` yüzündense `code="user_approval_required"`, `vol_ratio_max` yüzündense `code="needs_user"` yazılır (ikisi birlikteyse `needs_user`). Böylece gölge dönem ve "her zaman kullanıcıya" kuralları, ders servisinde bir hata olsa bile defter düzeyinde zorlanır. Kullanıcı onayı da 2–9. kuralları ve kanıt şartını **yeniden** denetler (kullanıcı onayı sınırları genişletmez; sınır değişikliği `author="user"` sürümüyle yapılır).

### 5.4 Uygulama (apply) kuralları

`apply_proposal` sırayla (ilk ihlal `ok=False` döner; **terminal** işaretli olanlar durumu `rejected` yapar, **geçici** işaretliler durumu değiştirmez ve olay yazmaz):

1. Durum `proposed` veya (`needs_user` ve `actor="user"`); aksi `LedgerStateError`.
2. `base_version_id` hâlâ etkin değil → `stale_base` (terminal `rejected`).
3. 5.3'ün 2–10. kuralları yeniden (etkin sürüm değişmiş olabilir) → ilgili kod (terminal).
4. **Kanıt (havuzlu, Revizyon 2):** defterin kendi sayımı `n_closed` ≥ `min_evidence_trades`. `n_closed` = `v_closed_trades` içinde `param_version_id ∈ POOL(base_version_id, key)` olan ve kapsamı (Bölüm 5.1 "Kanıt kapsamı") parametreye uyan kapanmış işlem sayısı. Kapsam `T1` ise yalnızca `setup='T1'`, `R1` ise yalnızca `R1`, `T1+R1` ise ikisi. Eksikse `insufficient_evidence` (**geçici**: durum `proposed` kalır, olay yazılmaz, ertesi gün tekrar denenir). Beyan edilen `claimed_evidence.n_closed` yok sayılır; fark varsa `evidence` içine `claimed_mismatch: true` yazılır.

   **Havuz tanımı (`POOL`):** `key` önerilen parametre, `S = LESSON_SCOPE[key]` (setup kümesi). Bir parametre `q`, `key`'in kapsamını **etkiler** (`affects(q, key)`) ancak: `q` ders servisine kapalı bir parametre ise (`range_width_atr`, `edge_zone_atr`, `pullback_ema`, `trigger_tf`: giriş kümesini şekillendirirler) **ya da** `LESSON_SCOPE[q] ∩ S ≠ ∅` ise. `POOL(base, key)` = bu botun `param_versions` kayıtlarında, `params[q]` değeri `base` sürümünün `params[q]` değerine **eşit** olan sürümlerin kümesi, **her** `q` için `affects(q, key)` doğruysa (`q = key` dahil; `base` kendisi havuzdadır). Yani yalnızca kapsamı ayrık parametreler (örn. `key = trail_atr` (T1) iken `rr_min` (R1) farkı) farklı olan sürümler **havuzlanır**; kapsamı kesişen herhangi bir parametre farklıysa o sürüm havuz dışıdır. Sonuç: bir R1 parametresinin değişmesi T1 kanıt akışını sıfırlamaz; `T1+R1` parametreleri (`vol_ratio_max`, `stop_buffer_atr`) değiştiğinde her iki kapsam sıfırlanır. `LESSON_SCOPE`/`affects` bir sabit tablodur, veri-bağımlı değildir. Rollback sonrası bir önceki sürüme dönüşte havuz doğal olarak yeniden birleşir (sürüm kimliği aynıdır).
5. **Haftalık sınır:** `actor="lesson"` ise son 7 günde (`activated_at ≥ şimdi − 7 gün`) `kind='apply'` ve `actor='lesson'` olan etkinleştirme varsa `weekly_limit` (**geçici**). Geri almalar ve kullanıcı etkinleştirmeleri sayılmaz. (Kaynak: `mimari-taslak.md` Bölüm 5 "haftada en fazla bir değişiklik".)
6. Hepsi geçerse tek işlemde (`BEGIN IMMEDIATE`): yeni `param_versions` satırı (`author="lesson"` — kullanıcı onaylı olsa da; onaylayan `param_activations.actor`'da yazılır), `param_activations` (`kind="apply"`), `proposal_status_events(applied, version_id=…)`. Üçü birlikte yazılır ya da hiçbiri.

`evidence` (sürüm satırında): `{"n_closed": 23, "scope": "R1", "base_version_id": 1, "pooled_version_ids": [1], "n_by_version": {"1": 23}, "first_exit_ts": "...", "last_exit_ts": "...", "mean_r": 0.31, "sum_r": 7.13, "win_rate": 0.52, "claimed_mismatch": false}`. `n_closed` zorunlu ve `≥ min_evidence_trades`; sayılar defterin kendi hesabıdır.

### 5.5 Geri alma (rollback) kuralları

`rollback(to_version_id=None, *, actor, reason)`: `to_version_id=None` ⇒ `param_activations`'ta mevcut sürümden farklı olan **en son** `version_id` (`prev_version_id` zinciri değil, bir önceki farklı sürüm). Kanıt şartı yok, haftalık sınıra tabi değil, hedef sürüm var olmalı (yoksa `unknown_version`), etkinden farklı olmalı (`already_active`). `actor ∈ {lesson, user}`; `reason` zorunlu. Olay `kind="rollback"`, `proposal_id=NULL`. Geri alınan önerinin durumu `applied` kalır (geçmiş değişmez). `twin` botta yasak.

### 5.6 İkiz botun kuralı

`bot="twin"`: yalnızca `init_params` (öğrenen botun ilk sürümüyle **aynı** `params_hash`; bunu doğrulamak çağıranın/testin işidir) ve okuma/karar/işlem yazımı serbest. `propose_change`, `apply_proposal`, `rollback`, `create_param_version(author="lesson")` → `LedgerStateError`. `author="user"` sürümü ikizde de yasak (dondurulmuş). İkizin parametresi yalnızca defter dosyası elle yeniden kurularak değişir (dışarıda).

## 6. API — yazma

Hepsi `Ledger` yöntemidir. Tüm yazmalar tek `BEGIN IMMEDIATE … COMMIT` işlemidir; başarısızlıkta `ROLLBACK` ve `LedgerWriteError`.

### 6.1 Veri sınıfları (frozen dataclass)

```
@dataclass(frozen=True)
class DecisionEvent:
    bar_close_ts: datetime
    trigger_tf: str                       # "1h" | "15m"
    pair: str
    side: str
    setup: str                            # "T1" | "R1"
    regime: str                           # Regime değeri (str)
    atr_ratio: float | None
    rh: float | None
    rl: float | None
    rh_touches: int
    rl_touches: int
    features: Mapping[str, float | int | str]
    planned_entry: float
    planned_stop: float
    planned_target: float | None
    param_version_id: int
    veto_status: str                      # allowed|blocked|missing|stale|not_evaluated
    veto_reason: str | None
    risk_allowed: bool | None
    risk_reason: str | None
    size_qty: float | None
    size_notional: float | None
    size_margin: float | None
    size_risk_amount: float | None
    leverage: int | None
    final_action: str                     # entered | skipped
    skip_reason: str | None
    supersedes_id: int | None = None
    ml_score: float | None = None         # şema 3; ML filtresi puanı, yoksa None

@dataclass(frozen=True)
class TradeEntry:
    trade_id: int
    decision_id: int
    entry_ts: datetime
    entry_price: float
    qty: float
    leverage: int
    fee_entry: float
    supersedes_id: int | None = None

@dataclass(frozen=True)
class TradeExit:
    trade_id: int
    exit_ts: datetime
    exit_price: float
    exit_reason: str
    planned_exit: float | None
    fee_exit: float
    funding_paid: float
    supersedes_id: int | None = None
    max_favorable_price: float | None = None   # şema 2 (3.4.1); üçlü birlikte verilir ya da birlikte None
    max_adverse_price: float | None = None
    excursion_tf: str | None = None            # "1m" | "5m" | "15m"
```

Kolaylık: `decision_from_results(*, regime_result, risk_decision, ...)` **yok** (defter `rejim`/`risk` modüllerini import etmez; çağıran alanları kendisi aktarır). `RegimeResult.regime.value` metni, `Decision.reason` ve `Decision.size` alanları aynen kopyalanır.

### 6.2 Yazma fonksiyonları

```
Ledger.record_decision(ev: DecisionEvent) -> int
Ledger.record_trade_entry(e: TradeEntry) -> int
Ledger.record_trade_exit(x: TradeExit) -> int
Ledger.init_params(params: Mapping[str, Any], *, reason: str,
                   lesson_bounds: Mapping[str, tuple[float, float]] | None = None) -> int
Ledger.create_user_version(params: Mapping[str, Any], *, reason: str,
                   lesson_bounds: Mapping[str, tuple[float, float]] | None = None) -> int
Ledger.activate_version(version_id: int, *, actor: str, reason: str) -> ActivationResult
Ledger.propose_change(*, base_version_id: int, changes: Mapping[str, Any],
                   rationale: str, claimed_evidence: Mapping[str, Any], source: str,
                   require_user: bool = False) -> ProposalResult      # require_user: 5.3 madde 11
Ledger.apply_proposal(proposal_id: int, *, actor: str, reason: str) -> ActivationResult
Ledger.reject_proposal(proposal_id: int, *, actor: str, reason: str) -> None
Ledger.rollback(to_version_id: int | None = None, *, actor: str, reason: str) -> ActivationResult

@dataclass(frozen=True) class ProposalResult:   ok: bool; proposal_id: int; status: str; code: str; reason: str
@dataclass(frozen=True) class ActivationResult: ok: bool; code: str; reason: str; version_id: int | None; activation_id: int | None; proposal_id: int | None
```

- `record_decision`: doğrulama Bölüm 3.3; dönen değer `id` (idempotent tekrar: mevcut `id`). `param_version_id` var olmalı. `pair`/`side` normalleştirilir (`risk-kilidi-spec.md` kuralı).
- `record_trade_entry`: `decision_id` mevcut, `final_action='entered'`, aynı `bot`; `trade_id` daha önce aynı karara bağlanmış olmalı (farklı kararla çakışma → `LedgerConflictError`). `planned_*`, `pair`, `side`, `setup`, `param_version_id`, `planned_risk` karardan alınır. `planned_risk = size_risk_amount`. `qty > 0`, `entry_price > 0`, `leverage` tam sayı ≥ 1, `fee_entry ≥ 0`.
- `record_trade_exit`: Bölüm 3.4 ve 3.4.1. `exit_price > 0`; `exit_reason` listede; `fee_exit ≥ 0`; `funding_paid` sonlu (negatif olabilir); `mfe_r`, `mae_r`, `bars_held` defter tarafından hesaplanır (3.4.1). Aynı içerikle tekrar yazma idempotenttir (karşılaştırmaya yeni alanlar da girer).
- `init_params`: yalnızca ilk çağrı; ikinci çağrı `LedgerStateError`. Sürüm + `initial` etkinleştirmesi tek işlemde.
- `create_user_version`: sürümü yaratır, **etkinleştirmez**; ayrı `activate_version(actor="user")`. (İki adım: kullanıcı backtest sonucunu görüp onaylar.)
- `activate_version`: yalnızca `author in {initial, user}` sürümleri için (lesson sürümleri yalnızca `apply_proposal` ile etkinleşir; eski lesson sürümüne dönüş `rollback` ile). `kind="apply"`, `actor="user"`.
- `reject_proposal`: `proposed` veya `needs_user` → `rejected` (`code="rejected_by_actor"`).
- Tüm `reason`, `rationale`, `source` boş (kırpılmış) olamaz.

## 7. API — okuma ve sağlık

### 7.1 Okuma (ders servisi ve rapor)

Tüm okumalar tek bir okuma işleminde (WAL anlık görüntüsü) yapılır; bir çağrı içinde tutarlıdır.

```
Ledger.get_active_params() -> ActiveParams
Ledger.get_version(version_id: int) -> ParamVersion
Ledger.list_versions() -> list[ParamVersion]
Ledger.list_activations(limit: int | None = None) -> list[ActivationEvent]   # en yeni önce
Ledger.get_decision(decision_id: int) -> DecisionRecord
Ledger.list_decisions(*, since_ts: datetime | None = None, until_ts: datetime | None = None,
                      setup: str | None = None, final_action: str | None = None,
                      limit: int | None = None) -> list[DecisionRecord]      # bar_close_ts artan
Ledger.get_trade(trade_id: int) -> TradeRecord | None
Ledger.list_open_trades() -> list[TradeRecord]
Ledger.trades_since_version(version_id: int, *, closed_only: bool = True, exact: bool = False,
                      setup: str | None = None) -> list[TradeRecord]
Ledger.aggregate_trades(group_by: Sequence[str], *, version_id: int | None = None,
                      exact_version: bool = True, since_ts: datetime | None = None,
                      until_ts: datetime | None = None,
                      version_ids: Sequence[int] | None = None) -> list[AggregateRow]   # version_ids verilirse version_id/exact_version verilemez
Ledger.count_closed_trades(*, version_id: int, setup: str | None = None) -> int
Ledger.pool_version_ids(base_version_id: int, param: str) -> tuple[int, ...]        # 5.4 havuz tanımı; artan sıralı, base dahil
Ledger.trades_for_versions(version_ids: Sequence[int], *, closed_only: bool = True,
                      setup: str | None = None, until_ts: datetime | None = None) -> list[TradeRecord]   # exit_ts (kapalıysa) artan, eşitlikte trade_id
Ledger.get_proposal(proposal_id: int) -> ProposalRecord
Ledger.list_proposals(*, status: str | None = None, limit: int | None = None) -> list[ProposalRecord]
```

- `ActiveParams` (frozen): `version_id`, `activation_id`, `params: Mapping[str, float|int|str]` (salt okunur kopya), `lesson_bounds`, `params_hash`, `activated_at`. Etkin sürüm yoksa `LedgerStateError`. Strateji bunu **her mum kapanışında bir kez** çağırır; ucuz yoldan `Ledger.active_activation_id() -> int | None` ile değişim denetlenebilir. Değişiklik, mevcut mumun içinde yaşanmaz: karar kaydı, o mumun başında okunan `version_id`'yi taşır.
- `TradeRecord` (frozen): giriş + çıkış + karar alanları düzleştirilmiş (`trade_id`, `pair`, `side`, `setup`, `regime`, `atr_ratio`, `param_version_id`, `entry_ts`, `exit_ts|None`, fiyatlar, `qty`, `leverage`, `fee_entry`, `fee_exit|None`, `funding_paid|None`, `exit_reason|None`, `gross_pnl|None`, `realized_pnl|None`, `r_multiple|None`, `planned_risk`, `slippage_entry`, `slippage_exit|None`, `decision_id`, ve şema 2'den itibaren `mfe_r|None`, `mae_r|None`, `bars_held|None`, `excursion_tf|None`).
- `trades_since_version(X)`: `exact=False` ⇒ girişin `param_activations` olay `id`'si, X'in **en son** etkinleştirme olayının `id`'sinden büyük/eşit olanlar (rollback sonrası X'e dönüşte yalnızca dönüşten sonrası); bu, X'ten sonra gelen sürümler altında açılanları da içerir. `exact=True` ⇒ yalnızca `param_version_id == X`. Bunun için `decision_events` ve `trade_entries` tablolarına `activation_id` sütunu (karar anında etkin `param_activations.id`) eklenir; `record_decision` bunu kendisi okuyup yazar, `DecisionEvent` alanı değildir.
- `pool_version_ids(base, param)`: 5.4'teki `POOL` kümesi; `param` bilinmiyorsa `LedgerValidationError`; `param` `LESSON_PARAMS` dışındaysa da geçerlidir (yalnızca `LESSON_SCOPE` yerine tüm setup kümesi `T1+R1` kabul edilir, yani yalnızca birebir aynı parametreli sürümler). `trades_for_versions` `version_ids` boşsa boş liste döner; var olmayan sürüm `LedgerValidationError`.
- Sıralama: `trade` listeleri `entry_ts` artan, eşitlikte `trade_id` artan (`trades_for_versions` hariç, yukarıda belirtildi).
- `aggregate_trades`: `group_by` ⊆ `{"setup", "regime", "side", "param_version_id", "pair"}`, boş olamaz, tekrarsız; aksi `LedgerValidationError`. Yalnızca kapanmış işlemler, pencere `exit_ts` üzerinden (`since_ts` dahil, `until_ts` hariç). `version_id` verilirse `exact_version` ile Bölüm yukarıdaki iki anlam.

```
@dataclass(frozen=True)
class AggregateRow:
    key: Mapping[str, str | int]   # group_by anahtarları
    n: int
    wins: int                      # realized_pnl > 0
    win_rate: float                # wins / n
    sum_r: float
    mean_r: float
    median_r: float                # Python'da hesaplanır (SQLite'ta medyan yok); çift n'de iki ortanın ortalaması
    sum_pnl: float                 # realized_pnl toplamı
    sum_fees: float                # fee_entry + fee_exit toplamı
    sum_funding: float
    mean_slippage_entry: float
    mean_slippage_exit: float | None   # hiçbir işlemde planlanan çıkış yoksa None
```
Satırlar `key`'in değerlerine göre sıralı (metin artan, sayı artan). `n=0` olan grup satırı üretilmez.

### 7.2 Sağlık ve kapı

```
@dataclass(frozen=True) class Health: ok: bool; code: str; detail: str
Ledger.check_writable() -> Health
Ledger.entries_allowed() -> Health
Ledger.find_orphan_decisions(*, older_than_s: int = 3600) -> list[int]
Ledger.find_unledgered_trades(open_trade_ids: Iterable[int]) -> list[int]
Ledger.drain_spool() -> int
```

- `check_writable()`: `BEGIN IMMEDIATE`, `health_probes`'a bir satır, `COMMIT`; ayrıca dosya sistemi boş alanı ≥ 50 MiB (`os.statvfs`). Başarılıysa `Health(True, "ok", "")` ve `degraded` bayrağı temizlenir (spool boşsa). Hata → `Health(False, kod, ...)`; kod: `disk_low`, `locked`, `io_error`, `read_only`, `schema`.
- `entries_allowed()` (strateji her mumda çağırır, sonuç ≤ 30 sn önbelleğe alınır; `degraded` iken önbellek yoktur ve en çok 30 sn'de bir `check_writable` denenir): `ok=True` ancak şunların **hepsi** doğruysa: bayrak `degraded` değil; spool boş; etkin parametre var; şema sürümü uyumlu; son `check_writable` başarılı (yaşı ≤ 60 sn); `find_unledgered_trades` boş (başlangıçta ve her mumda freqtrade açık işlem kimlikleriyle). Aksi `ok=False` ve kod (`degraded`, `spool_pending`, `no_active_params`, `schema`, `unledgered_trades`).
- `find_orphan_decisions`: `final_action='entered'` olup, `recorded_at`'ı `older_than_s` saniyeden eski ve hiçbir geçerli `trade_entries` satırına bağlı olmayan karar `id`'leri (emir hiç dolmadı). Rapor bunları uyarı yapar; düzeltme `record_decision` ile `supersedes_id`, `final_action='skipped'`, `skip_reason='order_failed'`.
- `find_unledgered_trades`: verilen freqtrade açık işlem kimliklerinden defterde geçerli girişi olmayanlar.

## 8. Fail-closed kuralları

### 8.1 Yeni işlem açma kapısı

Yeni işlem **yalnızca** şu yolla açılır; strateji yapısı:

1. `populate_entry_trend` başında `ledger.entries_allowed()`; `ok=False` ise giriş sinyali üretilmez (kapı kapalı). Bu çağrı ayrıca her kapalı mum için `skip_reason='entry_gate_closed'` karar kaydı **yazmaya çalışır**; yazılamıyorsa yalnızca log (kayıp kabul edilir, kapı zaten kapalı).
2. Kapı açıksa karar `final_action='entered'` ile `record_decision` ile **emir verilmeden önce** yazılır (`confirm_trade_entry` içinde). `LedgerError` veya herhangi bir istisna → `confirm_trade_entry` `False` döner (işlem açılmaz), `degraded=True`, `CRITICAL` log + Telegram uyarısı.
3. `order_filled` (giriş) içinde `record_trade_entry`. Pozisyon artık açık olduğundan burada başarısızlık işlemi **geri alamaz**: kayıt spool'a düşer (8.2), `degraded=True` olur ve kapı kapanır; yeni işlem açılmaz. Açık pozisyon kendi stop'u ile yönetilmeye devam eder.

`degraded` ve spool bayrakları süreç yeniden başlamasında dosyadan yeniden kurulur (spool dosyasının varlığı ve boş olmaması).

### 8.2 Çıkış ve spool

Çıkışlar **asla engellenmez** (riski azaltır). `record_trade_exit` başarısız olursa kayıt, veritabanı dosyasının yanındaki `<db>.spool.jsonl` dosyasına tek satır JSON olarak eklenir (`flush` + `os.fsync`); `degraded=True`. `drain_spool()` satırları sırayla defterde yeniden yazar (idempotentlik sayesinde çift yazma zararsızdır), başarıyla işlenen satırları tutan dosyayı **yeniden yazarak** küçültür (spool, defter değildir; append-only kuralı yalnızca SQLite tablolarına uygulanır), kaç satır işlendiğini döner. Spool'a da yazılamazsa `CRITICAL` log ve kapı kapalı kalır (başka bir şey yapılamaz). `drain_spool` her `entries_allowed` denemesinde ve başlangıçta çağrılır.

### 8.3 Ders servisi tarafı

Ders servisi, defter yazımı başarısız olursa hiçbir parametre uygulamaz; `apply_proposal` işlemi atomiktir (Bölüm 5.4/6). Ders servisinin çökmesi veya defteri okuyamaması botun işlem akışını etkilemez (bot yalnızca etkin sürümü okur).

## 9. Eşzamanlılık

- **Yazar süreçler:** freqtrade (öğrenen veya ikiz, dosyası başına bir süreç) kararları/işlemleri yazar; ders servisi (yalnızca `learner` dosyası) öneri, sürüm, etkinleştirme yazar. Yani öğrenen dosyada **iki yazar süreç** olabilir. SQLite tek yazar kilidiyle serileştirir; `busy_timeout=5000`, yazma `BEGIN IMMEDIATE`. Kilit zaman aşımı → `LedgerWriteError(code="locked")`.
- **Okuyucular** engellenmez (WAL). Ders servisi okurken freqtrade yazmaya devam eder.
- Ders servisi **okuma işlemleri** `read_only=True` bağlantısıyla yapılır; yazma gereken `propose/apply/rollback` ayrı `read_only=False` bağlantısıyla.
- Etkin parametre değişimi (apply/rollback) bota **bir sonraki mum kapanışında** yansır (Bölüm 7.1); açık pozisyonlar açılış parametreleriyle yönetilir (T1 iz süren stop, R1 hedefi vs. giriş anında belirlenir; `trail_atr` gibi çıkış parametresinin açık pozisyonda değişip değişmeyeceği strateji spesifikasyonunun işidir, defter yalnızca `param_version_id`'yi kaydeder).
- Aynı dosyayı iki farklı makineden açma desteklenmez.

## 10. Şema sürümü ve göçler

- `PRAGMA user_version` = şema sürümü (şimdiki: **3**). Modülde `SCHEMA_VERSION = 3` ve sıralı `MIGRATIONS` listesi (`n → n+1`, her biri tek işlemde tablolar + tetikleyiciler + görünümler).
- Açılışta: dosya yeni ve `create=True` ⇒ göçler 0 → 1 → 2 → 3 sırayla kurulur (sonuç sürüm 3). `user_version == SCHEMA_VERSION` ⇒ devam. `user_version > SCHEMA_VERSION` ⇒ `LedgerSchemaError` (eski kod yeni şemaya yazamaz). `user_version < SCHEMA_VERSION` ⇒ `migrate=True` ise önce `backup(<db>.premigrate-v<n>)`, sonra göçler sırayla `BEGIN IMMEDIATE` içinde; her göç sonrası `user_version` güncellenir ve `meta.schema_version` için **yeni** bir `schema_migrations` olayı yazılır; `migrate=False` ise `LedgerSchemaError`. Salt okunur bağlantı hiçbir zaman göç etmez.
- Göçler yalnızca **ekleyicidir** (yeni tablo/sütun/görünüm); mevcut satır silinmez ya da yeniden yazılmaz. Yeni sütunlar `NULL` ya da `DEFAULT` ile eklenir, tetikleyiciler yeniden kurulur.
- Göç sırasında ders servisi aynı dosyayı salt okunur açmış olabilir; WAL buna izin verir. Göç, bot durmuşken yapılması önerilen bir operasyondur (docker compose yeniden başlatma).
- `schema_migrations(id, from_version, to_version, applied_at)` tablosu, append-only.

### 10.1 Göç 1 → 2 (MFE/MAE; Revizyon 2)

Tek `BEGIN IMMEDIATE` işleminde, `migrate=True` ve bot durmuşken (10. bölüm önerisi), önceden `backup(<db>.premigrate-v1)`:

1. `ALTER TABLE trade_exits ADD COLUMN mfe_r REAL`, `... mae_r REAL`, `... bars_held INTEGER`, `... excursion_tf TEXT` (hepsi NULL varsayılan; mevcut satırlara dokunulmaz; append-only tetikleyicileri `ALTER`'dan etkilenmez ama göç sonunda yine yeniden kurulur ve varlıkları doğrulanır). Yeni sütunlar için tutarlılık kontrolü (`mfe_r/mae_r/excursion_tf` üçlüsü; `≥ 0`) yazma yolunda doğrulanır; SQLite `ADD COLUMN` ile eklenen CHECK, tablo bütünü için ek `CREATE TRIGGER trg_trade_exits_excursion_check BEFORE INSERT` ile sağlanır (`RAISE(ABORT, 'excursion_check')`).
2. `DROP VIEW v_closed_trades; DROP VIEW v_trades;` sonra yeni sütunları içeren `v_trades` ve `v_closed_trades` yeniden kurulur (görünümler veri değildir; silinebilir). `v_decisions` ve `v_proposals` değişmez.
3. `PRAGMA user_version = 2`; `meta.schema_version` aynası için yeni bir `schema_migrations(1, 2)` satırı. (`meta` satırı güncellenemez; asıl kaynak `user_version`, 3.2.)
4. Mevcut kapanmış işlemlerin `mfe_r/mae_r/excursion_tf` değerleri NULL kalır; `bars_held` de NULL kalır (append-only: geriye dönük doldurma yok). İsteğe bağlı geriye doldurma yalnızca yeni çıkış satırı (`supersedes_id`) ile olur ve bu sürümün kapsamı dışındadır.
5. Göç sonrası `entries_allowed()` normal; yeni kod şema 1 dosyasını `migrate=False` ile açarsa `LedgerSchemaError` (açıkça göç gerekir). Salt okunur bağlantı göç etmez (10.2).

Geri alma: göç ileri yönlüdür; sorun olursa `premigrate-v1` yedeğine dönülür (eski kod şema 2 dosyasına yazamaz: `user_version > SCHEMA_VERSION`).

### 10.2 İkiz defterini salt okunur açma (ders servisi)

Ders servisi ikiz defterini `open_ledger(twin_path, "twin", create=False, read_only=True, migrate=False)` ile açar; ikiz botun kendisi dosyayı yazan tek süreçtir. Şema uyuşmazlığı (ikiz dosyası hâlâ şema 1, ders servisi kodu şema 2) `LedgerSchemaError` verir: ders servisi bunu "ikiz yok" kabul eder (ders-spec 4.5.5), hata değildir. Bu yüzden her iki bot dosyası aynı kod sürümüyle ve aynı gün göç edilmelidir (operasyon notu). Okuma, WAL anlık görüntüsüyle tutarlıdır; ikiz yazarken bloklanmaz.

### 10.3 Göç 2 → 3 (ML-0a; Revizyon 3)

Tek `BEGIN IMMEDIATE` işleminde, `migrate=True` ve bot durmuşken, önceden `backup(<db>.premigrate-v2)`. SQLite `CHECK`'i değiştiremediğinden (`ALTER TABLE` yok) `decision_events` SQLite'in resmi yeniden-kurma yordamıyla yeniden kurulur; **hiçbir satır değişmez ya da silinmez, `id`'ler korunur**:

1. İşlemin **dışında** `PRAGMA foreign_keys=OFF` (`_FK_OFF_MIGRATIONS`); işlem sonrası `PRAGMA foreign_key_check` (ihlal ⇒ `LedgerSchemaError`) ve `foreign_keys=ON` (hata olsa da geri açılır).
2. `DROP VIEW v_closed_trades, v_trades, v_decisions`.
3. `decision_events_v3` tablosu yeni DDL ile kurulur (`skip_reason` CHECK'ine `ml_filter`; `not_evaluated` CHECK'ine `ml_filter`; yeni `ml_score REAL` + `CHECK (ml_score IS NULL OR ml_score BETWEEN 0 AND 1)`), eski sütunların hepsi `id` dahil kopyalanır (`ml_score` NULL), eski tablo `DROP`, yeni tablo `decision_events` adına `RENAME`, `ux_decision_key` ve `ix_decision_supersedes` yeniden kurulur.
4. Görünümler (`v_decisions`, `v_trades`, `v_closed_trades`) yeniden kurulur; `decision_events` dahil tüm append-only tetikleyiciler düşürülüp yeniden kurulur (`trg_trade_exits_excursion_check` `trade_exits`'te kaldığı için dokunulmaz).
5. `PRAGMA user_version = 3`; `schema_migrations(2, 3)` satırı. Mevcut kararların `ml_score`'u NULL kalır.

Salt okunur bağlantı göç etmez; şema 2 dosyasını `migrate=False` ile açan yeni kod `LedgerSchemaError` alır (10.2'deki aynı-gün göç uyarısı geçerli: ders servisi ve ikiz aynı kod sürümüyle göç etmeli). Geri alma: `premigrate-v2` yedeği (eski kod şema 3 dosyasına yazamaz). Testler: `tests/test_ledger_v3_ml_filter.py`.

## 11. Belirsizlikler ve bu belgedeki çözümleri

| # | Belirsizlik | Çözüm |
|---|---|---|
| 1 | Veto'dan önce elenen aday için veto değeri | Beşinci değer `not_evaluated` |
| 2 | "Bir adım" ve `vol_ratio_max` adımı (0.25) / sınır genişliği (0.4) | Tek öneride değişim ≤ tarama adımı; tam kat zorunlu değil |
| 3 | Kanıt: kaç işlem, hangi işlemler | Defter sayar; ana sürümle açılmış, kapanmış, parametrenin kapsamındaki kurulumlara ait işlemler (`trail_atr` yalnız T1, `range_target_frac`/`rr_min` yalnız R1); kapsamlı sayım, `strateji-v1.md` 3. zayıf nokta (R1 seyrek) nedeniyle R1 değişiklikleri yavaş olabilir |
| 4 | Sınırların yeniden ortalanması | `lesson_bounds` sürüm içinde; yalnızca `initial`/`user` sürümlerinde değişir; tarama aralığı dışına çıkamaz |
| 5 | Büyük değişiklik tanımı | Yalnızca `vol_ratio_max` artırma (gevşetme); başka tanım `strateji-v1.md`'de yok |
| 6 | Kullanıcının doğrudan sürümü kanıt ister mi | İstemez; `author="user"` yolu ve gerekçe zorunlu |
| 7 | `planned_risk` neyi içerir | `risk.py` `size_risk_amount` (komisyon + kayma dahil planlanan zarar); R bu paydayla |
| 8 | `realized_pnl` brüt mü net mi | Net (komisyon ve funding sonrası); brüt ayrı sütun |
| 9 | Kayma işareti | Pozitif = aleyhe, kesir |
| 10 | Çıkışta engel | Çıkışlar hiçbir koşulda engellenmez; yalnızca spool |
| 11 | Mum zaman damgası | Kapanış zamanı; `rejim-spec.md` açılış zamanı kullanır, dönüşüm çağıranın |
| 12 | İkiz | Parametre ve öneri yazımı yasak; yalnızca karar/işlem |
| 13 | 15dk tetik kolu | `trigger_tf` hem karar sütunu hem parametre; ders servisine kapalı |
| 14 | Kanıt sürümler arası sıfırlansın mı (mentor) | Hayır: kapsamı kesişen parametreleri eşit olan sürümler havuzlanır (5.4); yalnızca ilgili kapsamı etkileyen değişiklik sayacı sıfırlar |
| 15 | MFE/MAE ve R | `planned_risk` paydalı brüt sapma; uç fiyatlar çağıranda, hesap defterde (3.4.1); eski işlemler NULL |
| 16 | Gölge dönemde ve `stop_buffer_atr` artışında kullanıcıya sorma | `propose_change(require_user=True)` → `needs_user`; defter düzeyinde `actor="lesson"` ile uygulanamaz |
| 17 | İkiz defteri ders servisine açık mı | Yalnızca salt okunur (10.2); ikizde yazma yasağı (5.6) aynen sürer |

## 12. Elle doğrulanabilir örnekler (test yazarı için)

Aksi belirtilmedikçe `bot="learner"`, saatler UTC.

### 12.1 Kanıt ve kanonik JSON

Başlangıç `params` (varsayılanlar, `strateji-v1.md` 6.1), kanonik metin:

`{"edge_zone_atr":0.25,"pullback_ema":50,"range_target_frac":0.75,"range_width_atr":4.0,"rr_min":1.5,"stop_buffer_atr":0.3,"trail_atr":3.0,"trigger_tf":"1h","vol_ratio_max":1.5}`

`params_hash` = `de6ff80013f1ae38fbe23322363fb0d0d6aa031569ef22ac2e7efd03da1c0514` (SHA-256, UTF-8). Aynı `params`, anahtarlar farklı sırada ve `pullback_ema=50.0` (float) verilse bile aynı hash çıkar (anahtar sırası ve `50.0 → 50` normalleştirmesi). `rr_min=1.25` ile: `dc7f7c8cc75741d8b0673da580efecfcea977006d88b4bed12949ff011d7a3bf`.

`init_params(...)` ⇒ `version_id=1`, `param_activations` tek satır (`id=1`, `kind=initial`, `actor=system`, `prev_version_id=NULL`). `get_active_params().version_id == 1`. İkinci `init_params` → `LedgerStateError`. `params`'a `max_leverage` eklenirse → `LedgerValidationError` (fazla anahtar). `vol_ratio_max=1.2` → `LedgerValidationError` (tarama aralığı 1.25 altı).

### 12.2 Karar kaydı

R1 long, ETH/USDT, tetik mumu 1s kapanışı `2026-12-01T10:00:00.000Z`, `regime=range`, `rh=2100`, `rl=1980`, `rh_touches=2`, `rl_touches=3`, `atr_ratio=1.1`, `planned_entry=2000`, `planned_stop=1960`, `planned_target=2100`, `rr=2.5`, `veto_status=allowed`, `risk_allowed=True`, `risk_reason` boş değil, `size_qty=0.3`, `size_risk_amount=13.188`, `leverage=3`, `final_action=entered`, `param_version_id=1` ⇒ `id=1`.

- Aynı olayı aynen yeniden yaz ⇒ yine `1`. `planned_stop=1961` ile ⇒ `LedgerConflictError`.
- `regime="range"` ama `rh=None` ⇒ `LedgerValidationError`. `regime="trend_up"` ama `rh=2100` ⇒ `LedgerValidationError`.
- `bar_close_ts` `10:07:00` ⇒ `LedgerValidationError` (15 dk katı değil). tz-naive `datetime` ⇒ `LedgerValidationError`.
- `veto_status=blocked`, `final_action=entered` ⇒ `LedgerValidationError`.
- T1 short, aynı mum, farklı çift `"btc/usdt:usdt"` ⇒ `pair` `"BTC/USDT"` saklanır.
- `rr=1.2 < rr_min` elemesi: `veto_status=not_evaluated`, `risk_allowed=None`, `final_action=skipped`, `skip_reason=rr_below_min` ⇒ geçerli.

Düzeltme: `final_action=skipped`, `skip_reason=order_failed`, `supersedes_id=1` ⇒ `id=2`; `v_decisions` yalnızca `id=2`'yi (zincirin sonu) gösterir; `UPDATE decision_events …` ⇒ `sqlite3.IntegrityError` (`append-only`).

### 12.3 İşlem, R ve kayma (kazanan R1 long)

12.2'deki `id=1` kararı için (düzeltme yazılmamış varsay), `trade_id=7`: `entry_ts=2026-12-01T10:00:03Z`, `entry_price=2001`, `qty=0.3`, `leverage=3`, `fee_entry=0.30015` (= 0,3·2001·0,0005).

- `slippage_entry = (2001 − 2000)/2000 = 0.0005`.
- `planned_risk = 13.188` (= 0,3·(40 + 2000·0,001 + 1960·0,001) = 0,3·43,96).

Çıkış: `exit_ts=2026-12-02T09:00:00Z`, `exit_price=2079`, `exit_reason=target`, `planned_exit=2100`, `fee_exit=0.31185` (= 0,3·2079·0,0005), `funding_paid=0.1`.

- `gross_pnl = 0.3·(2079 − 2001) = 23.4`.
- `realized_pnl = 23.4 − 0.30015 − 0.31185 − 0.1 = 22.688`.
- `r_multiple = 22.688 / 13.188 ≈ 1.7204` (4 hane; test `pytest.approx(1.720352, abs=1e-5)`).
- `slippage_exit = (2100 − 2079)/2100 = 0.01`.

**MFE/MAE (şema 2):** aynı işlem için çağıran `max_favorable_price=2085` (işlem süresince en yüksek `high`), `max_adverse_price=1992` (en düşük `low`), `excursion_tf="1m"` verir.

- `mfe_r = 0.3·(2085 − 2001)/13.188 = 25.2/13.188 ≈ 1.9109`.
- `mae_r = 0.3·(2001 − 1992)/13.188 = 2.7/13.188 ≈ 0.2047`.
- `bars_held = floor(exit_ts/15dk) − floor(entry_ts/15dk)`: `2026-12-02T09:00:00Z` ve `2026-12-01T10:00:03Z` → `09:00` ile `10:00` arası 23 sa = **92** mum.
- Doğrulama: `gross_pnl/planned_risk = 23.4/13.188 ≈ 1.7743 ≤ mfe_r (1.9109)` ✓. `max_favorable_price=2050` verilirse (çıkış fiyatı 2079'dan küçük) ⇒ `LedgerValidationError`. `max_favorable_price` verilip `excursion_tf=None` ⇒ `LedgerValidationError`. Üçü de `None` ⇒ kayıt geçerli, `mfe_r=mae_r=None`, `bars_held=92`.
- Short örneği (12.4, `trade_id=8`): `max_favorable_price` = en düşük `low` = 99.2, `max_adverse_price` = en yüksek `high` = 101.0 ⇒ `mfe_r = 10·(100 − 99.2)/12.01 ≈ 0.6661`; `mae_r = 10·(101 − 100)/12.01 ≈ 0.8326`.

`exit_ts` < `entry_ts` ⇒ `LedgerValidationError`. İkinci farklı çıkış (`supersedes_id` yok) ⇒ `LedgerConflictError`; birebir aynısı ⇒ aynı `id`. `planned_exit=None` (`exit_reason=time_stop`) ⇒ `slippage_exit=None`.

### 12.4 Kaybeden işlem (T1 short)

`trade_id=8`: giriş `planned_entry=100`, `planned_stop=101`, `entry_price=100`, `qty=10`, `fee_entry=0.5`, kararın `size_risk_amount=12.01` (= 10·(1 + 0,1 + 0,101)). Çıkış `exit_price=101`, `exit_reason=stop`, `planned_exit=101`, `fee_exit=0.505`, `funding_paid=−0.05` (alındı).

- `gross_pnl = 10·(100 − 101) = −10`.
- `realized_pnl = −10 − 0.5 − 0.505 − (−0.05) = −10.955`.
- `r_multiple = −10.955/12.01 ≈ −0.9122`.
- `slippage_entry = 0`, `slippage_exit = (101 − 101)/101 = 0`.

### 12.5 Toplulaştırma

Kapanmış üç işlem (hepsi `param_version_id=1`): A `T1/trend_up/long`, `r=+2.0`, `realized_pnl=+20`; B `T1/trend_down/short`, `r=−1.0`, `pnl=−10`; C `R1/range/long`, `r=+0.5`, `pnl=+5`.

`aggregate_trades(["setup"])` ⇒ `T1`: `n=2, wins=1, win_rate=0.5, sum_r=1.0, mean_r=0.5, median_r=0.5, sum_pnl=10`; `R1`: `n=1, wins=1, win_rate=1.0, sum_r=0.5, mean_r=0.5, median_r=0.5, sum_pnl=5`. Satır sırası `R1`, `T1` (metin artan). `aggregate_trades(["setup","side"])` ⇒ üç satır. `aggregate_trades([])` ⇒ `LedgerValidationError`. Açık işlem toplulaştırmaya girmez.

`trades_since_version(1, exact=True)` ⇒ A, B, C, `entry_ts` sırasıyla. Sürüm 2 etkinleştirildikten sonra D (sürüm 2 altında) açılırsa: `trades_since_version(1, exact=True)` yalnızca A, B, C; `trades_since_version(1, exact=False)` A, B, C, D; `trades_since_version(2)` yalnızca D.

### 12.6 Öneri doğrulama (`base_version_id=1`, varsayılan `lesson_bounds`)

| Öneri | Sonuç |
|---|---|
| `{"trail_atr": 3.5}` | geçerli (sınır üst ucu dahil, değişim 0.5 ≤ 0.5), `proposed` |
| `{"trail_atr": 4.0}` | `rejected`, `out_of_bounds` (4.0 > 3.5; adım da 1.0 > 0.5 ama 8. kural önce gelir) |
| `{"stop_buffer_atr": 0.5}` | `rejected`, `step_too_large` (0.2 > 0.1; sınır içinde) |
| `{"stop_buffer_atr": 0.4}` | `proposed` |
| `{"rr_min": 1.25}` | `proposed` (aralık 1.2–2.0 içinde, değişim 0.25 ≤ 0.25) |
| `{"vol_ratio_max": 1.3}` | `proposed` (sıkılaştırma, 0.2 ≤ 0.25, sınır alt ucu dahil) |
| `{"vol_ratio_max": 1.7}` | `needs_user` (gevşetme; sınır içinde) |
| `{"vol_ratio_max": 1.75}` | `rejected`, `out_of_bounds` |
| `{"range_width_atr": 3.5}` | `rejected`, `immutable_param` |
| `{"rr_min": 1.25, "trail_atr": 3.5}` | `rejected`, `multiple_changes` |
| `{"max_leverage": 4}` | `rejected`, `unknown_param` |
| `{"rr_min": True}` | `rejected`, `bad_value` |
| `{"rr_min": 1.5}` | `rejected`, `no_change` |
| `base_version_id=3` (etkin 1) | `rejected`, `stale_base` |

Her ret satırı `lesson_proposals`'a yine yazılır (+ `proposal_status_events(rejected)`).

### 12.7 Kanıt eşiği

`{"rr_min": 1.25}` önerisi `proposed`. Sürüm 1 altında kapanmış işlemler: 15 `R1` + 30 `T1`.
- `apply_proposal(actor="lesson")` ⇒ `ok=False, code=insufficient_evidence` (R1 kapsamı: 15 < 20; T1 sayılmaz). Öneri `proposed` kalır, yeni durum olayı **yazılmaz**.
- 4 R1 işlemi daha kapanır (19) ⇒ yine `insufficient_evidence`. 20. kapanışta ⇒ `ok=True`: `param_versions.id=2`, `author=lesson`, `params.rr_min=1.25`, diğer 8 anahtar aynen, `evidence.n_closed=20`, `evidence.scope="R1"`; `param_activations.id=2` (`kind=apply`, `prev_version_id=1`); durum `applied`, `version_id=2`.
- `claimed_evidence={"n_closed": 99}` ile bile 19 işlemde ret (beyan yok sayılır).
- `Ledger(min_evidence_trades=10)` ⇒ `LedgerValidationError`; `=25` geçerli ve R1 için 25 gerekir.
- `{"vol_ratio_max": 1.3}` (kapsam T1+R1): 30 T1 + 15 R1 = 45 ≥ 20 ⇒ kanıt tamam.

**Havuzlu kanıt (Revizyon 2):** sürüm 1 altında 15 R1 + 30 T1 kapanmış; `{"rr_min": 1.25}` 20. R1 kapanışıyla uygulandı (sürüm 2: yalnızca `rr_min` farklı). Sürüm 2 altında 8 T1 kapandı.
- `{"trail_atr": 3.5}` (taban sürüm 2, kapsam T1): `affects(rr_min, trail_atr)` = yanlış (R1 ∩ T1 = ∅) ⇒ `POOL(2, "trail_atr") = [1, 2]` ⇒ `n_closed = 30 + 8 = 38 ≥ 20` ⇒ kanıt tamam (havuzsuz sayım 8 olurdu). `evidence.pooled_version_ids=[1,2]`, `n_by_version={"1":30,"2":8}`.
- `{"rr_min": 1.5}` ya da `range_target_frac` önerisi (taban sürüm 2, kapsam R1): `rr_min` (kendisi) sürüm 1 ile farklı ⇒ `POOL(2, "rr_min") = [2]` ⇒ yalnızca sürüm 2 altındaki R1 işlemleri sayılır (0) ⇒ `insufficient_evidence`.
- `{"vol_ratio_max": 1.3}` (T1+R1, taban 2): `rr_min` kapsamı kesişir ⇒ sürüm 1 havuz dışı ⇒ yalnızca sürüm 2 işlemleri.
- Rollback ile sürüm 1'e dönüldükten sonra `POOL(1, "rr_min") = [1]` (sürüm 2 `rr_min`'i farklı); T1 için `POOL(1, "trail_atr") = [1, 2]`.

### 12.8 Haftalık sınır ve rollback

Sürüm 2, `2026-12-10T12:00:00Z`'de lesson tarafından etkinleştirildi. `2026-12-14`'te yeni, kanıtı yeterli `{"trail_atr": 3.5}` (taban sürüm 2; o sürümle 20 kapanmış T1 işlemi var) ⇒ `weekly_limit` (4 gün < 7), `proposed` kalır. `2026-12-17T12:00:00.000Z` ⇒ uygulanır (tam 7 gün dahil). `actor="user"` ile uygulanırsa haftalık sınır yok.

`rollback(actor="user", reason="...")` etkin sürüm 3 iken: hedef = en son farklı sürüm = 2; yeni `param_activations` satırı `kind=rollback`, `version_id=2`, `prev_version_id=3`; `param_versions` satır sayısı değişmez; sürüm 3'ün önerisi `applied` kalır. `rollback(to_version_id=3)` (etkin) ⇒ `already_active`; `to_version_id=99` ⇒ `unknown_version`. Ardından `rollback()` tekrar ⇒ hedef = 3 (en son farklı sürüm; ileri-geri). `bot="twin"` ⇒ `LedgerStateError`.

### 12.9 Fail-closed

- Veritabanı dosyası salt okunur (`chmod 0444` ve dizin yazılamaz) ⇒ `record_decision` `LedgerWriteError`; strateji `confirm_trade_entry` `False` döner; sonraki `entries_allowed()` ⇒ `ok=False, code=degraded`. Dizin yeniden yazılabilir olunca `check_writable()` ⇒ `ok=True`, ardından `entries_allowed()` ⇒ `ok=True` (spool boşsa).
- Disk boş alanı < 50 MiB (test: `os.statvfs` taklit edilir) ⇒ `check_writable` `ok=False, code=disk_low`.
- Giriş kaydı yazılırken hata ⇒ `<db>.spool.jsonl` bir satır, `entries_allowed` ⇒ `spool_pending`; `drain_spool()` 1 döner, dosya boşalır; `entries_allowed` ⇒ `ok=True`. Aynı satır iki kez drain edilirse defterde tek satır.
- `find_unledgered_trades([7, 8, 9])` defterde yalnızca 7, 8 varsa ⇒ `[9]`; `entries_allowed` ⇒ `unledgered_trades`.
- Karar `entered` yazılmış, 2 saat sonra trade girişi yok ⇒ `find_orphan_decisions(older_than_s=3600)` o `id`'yi döner.

### 12.10 Şema

Yeni dosyada `PRAGMA user_version == 3` (`SCHEMA_VERSION == 3`; göçler 0→1→2→3). Elle `user_version=4` yapılmış dosya, kod `SCHEMA_VERSION=3` ⇒ `LedgerSchemaError`. Elle `user_version=0` ve `migrate=False` ⇒ `LedgerSchemaError`.

**Göç 1 → 2:** sürüm 1 şemalı bir dosya (testte, 0→1 göçüyle kurulup `ALTER`/görünüm değişiklikleri geri alınmadan, ya da saklı v1 fikstürü) bir kapanmış işlemle hazırlanır. `open_ledger(migrate=False)` ⇒ `LedgerSchemaError`; `migrate=True` ⇒ `<db>.premigrate-v1` oluşur, `user_version == 2`, `trade_exits`'te dört yeni sütun var, eski işlemin `mfe_r/mae_r/bars_held/excursion_tf` değerleri NULL, `v_closed_trades` yeni sütunları gösterir, eski `r_multiple` değişmedi, tetikleyiciler yerinde (`UPDATE trade_exits` ⇒ `append-only`), `schema_migrations`'a `(1, 2)` satırı. `read_only=True` ile şema 1 dosyası ⇒ `LedgerSchemaError` (salt okunur göç etmez). İkinci `migrate=True` açılışı yan etkisizdir. `bot="twin"` ile açılan, `meta.bot="learner"` dosya ⇒ `LedgerSchemaError`. Bir tetikleyiciyi düşürülmüş dosya ⇒ açılışta `LedgerSchemaError`. `read_only=True` bağlantıda `record_decision` ⇒ `LedgerStateError`.

## 13. Kapsam dışı (bu sürümde yok)

Hash zinciri / imza; ders servisinin istatistik hesapları (yalnızca ham okuma ve toplulaştırma burada); al-tut/rastgele giriş kontrolleri (`null.py`); DSR; rapor biçimi; freqtrade `Trade` ile otomatik uzlaştırma (yalnızca `find_unledgered_trades` ve `find_orphan_decisions` yardımcıları); haber ve FreqAI alanları; çok bot (ikiden fazla) desteği.

## 14. Netleştirmeler

- Haftalık sınır (5.4/12.8): kural metni `activated_at ≥ şimdi − 7 gün` uygulamayı sayar; tam 7. gün anında (örn. 12-10T12:00:00.000 → 12-17T12:00:00.000) hâlâ engellenir (fail-closed), uygulama 7 günden **sonra** mümkündür; 12.8'deki "tam 7 gün dahil" bu şekilde okunur.
- Yazma hatası sonrası kapı (8.1/12.9): başarısız `record_decision`/`record_trade_entry` `degraded` yapar ve bu an son sağlık denemesi sayılır; `entries_allowed()` en erken 30 sn sonra yeniden `check_writable` dener, o zamana kadar `degraded` döner (kısa süreli kilit/hata kapıyı hemen açmaz).
- Düzeltme kararında (`supersedes_id`) `risk_allowed=1` ise `size_*` ve `leverage` yine dolu olmak zorundadır (3.3 tutarlılık kuralları); `order_failed` düzeltmesi bu alanları korur.
