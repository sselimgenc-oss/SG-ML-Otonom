# Defter ve motor ek alanları: emir anı kaydı, çıkıştaki koşul, gölge karar satırları, anlık değerli düşüş (spesifikasyon v1, 17 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


İş paketi **WP-3** (`otonom-trading-arastirma/tasarim-kararlari.md` 17 Kasım "Repo denetimi onay listesi"). Onay listesi maddeleri: **2** (yalnız kayıt alanları), **7 / A-11** (aday bastıran bloklar için gölge karar satırı), **16** (yalnız `trade_exits.exit_regime`), **18** (C-15, D-12: anlık değerli düşüş). Tek ajan, sırayla (§11), mentor incelemesi zorunlu.

Bu belge kod, test ve commit içermez; testler bu belgeden yazılır (§12). Çelişkide `defter-spec.md` (defter kuralları), `motor/` belgeleri (motor) ve `kagit-degerlendirme-plani.md` (eşikler) geçerlidir; bu belge onlara **ekler**, hiçbir kuralını değiştirmez. Şema **sürüm 3 → 4**.

## 0. Bağlayıcı ilkeler

1. **Yalnız kayıt.** Bu paketteki hiçbir alan, tablo ya da hesap; giriş/çıkış kararını, boyutu, kaldıracı, emir zamanını, kapı zincirini, veto ya da risk sonucunu etkilemez. Motor bu alanları **yazar, okumaz**. Tek istisna §3.5'teki isteğe bağlı fiyat sorgusudur: varsayılan kapalıdır, kağıt ve geri testte kod yolu yoktur.
2. **Geri test çıktısı bayt bayt aynı kalır.** `trades.csv`, `summary.json`, `open_at_end.json` ve `v_decisions` içeriği değişmez; kanıt yöntemi §10. Yeni çıktılar **yeni dosyalara** yazılır (`equity_mtm.csv`, `mtm.json`); `metrics.METRIC_KEYS`, `metrics.TRADES_COLUMNS` ve `engine.counters()` anahtar kümesi **değişmez**.
3. **Kayıt hatası işlem davranışını bozamaz.** Yeni ölçüm alanları geçersizse NULL yazılır, satır yine yazılır (§3.4). Gölge satır ve öz varlık işareti yazımı başarısız olursa yalnız kendi sayacı artar; `Ledger._degraded`, `_last_write_ok`, spool, `entries_allowed()` ve `entries_blocked_reason` **etkilenmez** (§5.5, §6.4).
4. **Kilitli dönem `[2026-05-01, 2026-11-01)` okunmaz.** Geri test zaten reddeder (`holdout.check_holdout`). Ek kurallar: `bar_close_ts`'si kilitli dönemde olan gölge satır yazılmaz; 15 dk gölge hesabı penceresinin tamamı kilitli dönemin dışına çıkana dek çalışmaz (§5.3-4); gölge karşı-olgusu kilitli dönemle kesişen pencereyi atlar (§7).
5. **Dondurulmuş dosyalara dokunulmaz:** `scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `src/trader_ml/{features,features_v2,labels,guards,config}.py`, `src/trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `src/trader_engine/holdout.py`. Bu dosyaların **kamusal işlevleri çağrılabilir** (`signals.evaluate_t1`, `signals.compute_signals`, `regime.classify_series`, `regime.align_to_base`, `indicators.ema`); içerikleri değişmez.
6. **Gölge satır aday değildir.** Ayrı tabloda durur (`shadow_decisions`), `decision_events` / `v_decisions` içine **hiçbir koşulda** girmez. Ders servisi, ML derlemi, sapma izleyicisi ve sağlık bu tabloyu okumaz (§8). **Otomatik devre dışı bırakma ya da gevşetme yoktur**; gölge kanıtı yalnız rapora gider, kural değişikliği ayrı ön kayıt + kullanıcı onayı ister.
7. Şema değişikliği yalnız **ekleyicidir** (yeni sütun NULL varsayılan, yeni tablo, görünümlere sona eklenen sütun). Mevcut hiçbir satır, sütun, CHECK ya da sütun sırası değişmez.

## 1. Kapsam özeti

| Madde | Ne eklenir | Nerede |
|---|---|---|
| 2 | Emir gönderim/yanıt zamanı, emir anı referans fiyatı, piyasa çıkışında karar fiyatı | `trade_entries`, `trade_exits` yeni sütunlar; `v_trades` türetilmiş sütunlar |
| 16 | Çıkış anındaki piyasa koşulu | `trade_exits.exit_regime` |
| 7 / A-11 | Aday üretmeyen yasakların gölge adayları | yeni tablo `shadow_decisions`, görünüm `v_shadow_decisions`; karşı-olgu deposunda `cf_shadow_outcomes` |
| 18 | Açık pozisyonları sayan öz varlık eğrisi ve düşüş | yeni tablo `equity_marks` (kağıt/testnet/canlı); geri testte `equity_mtm.csv` + `mtm.json`; `metrics.py` saf işlevler |

Kapsam dışı: haftalık kayma karşılaştırma raporu ve M2 eşik değişikliği (§13-1), kötü senaryo olasılık tablosu (§13-2), 15 dk gölgenin geri testi (§5.3-4), koşula bağlı her türlü kural.

## 2. Şema sürüm 4

### 2.1 `trade_entries` yeni sütunlar (hepsi NULL olabilir)

| Sütun | Tip | Anlam | NULL ne demek |
|---|---|---|---|
| `order_ts` | TEXT (`YYYY-MM-DDTHH:MM:SS.mmmZ`) | Giriş piyasa emrinin gönderim anı: motor saati, POST'tan hemen önce (`orders.created_ms` ile aynı an) | sürüm 4 öncesi satır, ya da emir satırı bulunamadı (borsadan devralınan giriş) |
| `order_ack_ts` | TEXT | Borsa yanıtının alındığı an, **aynı yerel saat** | benzetimli broker (kağıt, geri test); yeniden başlatma araya girdi; sürüm 4 öncesi |
| `order_ref_price` | REAL, `> 0` | Emir anı referans fiyatı (§3.2) | kaynak yok / sorgu kapalı ya da başarısız / sürüm 4 öncesi |
| `order_ref_spread` | REAL, `≥ 0` | `(ask − bid) / mid`; yalnız `order_ref_src='book'` | `book` dışı her durum |
| `order_ref_src` | TEXT, `'sim_open'` \| `'book'` | Referans fiyatın kaynağı | `order_ref_price` NULL ise NULL |

Tablo düzeyi tutarlılık (yazma yolunda doğrulanır, §3.4; ayrıca sütun CHECK'leri): `order_ref_src IS NULL ⇔ order_ref_price IS NULL`; `order_ref_spread IS NOT NULL ⇒ order_ref_src = 'book'`; `order_ack_ts IS NOT NULL ⇒ order_ts IS NOT NULL AND order_ack_ts ≥ order_ts`.

### 2.2 `trade_exits` yeni sütunlar (hepsi NULL olabilir)

§2.1'deki beş sütunun aynısı (çıkış **piyasa** emri için), artı:

| Sütun | Tip | Anlam | NULL ne demek |
|---|---|---|---|
| `decision_price` | REAL, `> 0` | Çıkış kararının verildiği tetik mumunun son-fiyat kapanışı (`ExitContext.last_close`). Girişteki `planned_entry`'nin çıkıştaki karşılığıdır | karar adımından gelmeyen çıkış (stop/hedef/likidasyon dolumu, KILL, elle, mutabakat, `force_exit`); yeniden başlatma; sürüm 4 öncesi |
| `exit_regime` | TEXT, `trend_up` \| `trend_down` \| `range` \| `volatile` \| `unclear` | Çıkış dolumundan önceki **son karar adımında** o çift için geçerli hizalanmış 4s koşul etiketi (§4) | son karar adımı bayat / çift verisi `ok` değil / yeniden başlatmadan sonra henüz karar adımı olmadı / sürüm 4 öncesi. Rapor NULL'ı `bilinmiyor` basar (`rapor-paketi-spec.md` §8.5) |

Dinlenen emirle (stop, hedef) ya da likidasyonla gelen çıkışta `order_ts`, `order_ack_ts`, `order_ref_*`, `decision_price` **NULL**'dır; bu çıkışların ölçüsü mevcut `planned_exit` / `slippage_exit`'tir ve **değişmez**.

**Değişmeyenler (kesin):** `planned_exit` ve `slippage_exit` piyasa çıkışlarında bugünkü gibi NULL kalır; `slippage_entry` tanımı aynıdır. Aksi `trades.csv`'yi (`slippage_exit`, `planned_exit`, `slip_cost`) ve WP-0 M3 referansını (0,127) değiştirirdi.

### 2.3 Görünümler

`v_trades` ve `v_closed_trades` düşürülüp yeniden kurulur; mevcut sütunlar **aynı sırada** kalır, yeniler `excursion_tf`'ten **sonra**, şu sırayla eklenir:

`entry_order_ts, entry_order_ack_ts, entry_ref_price, entry_ref_spread, entry_ref_src, slip_exec_entry, exit_order_ts, exit_order_ack_ts, exit_ref_price, exit_ref_spread, exit_ref_src, slip_exec_exit, exit_decision_price, slip_decision_exit, exit_regime`

Türetilmiş sütunlar (oran; **artı = aleyhte**, mevcut `slippage_*` ile aynı işaret; payda NULL ise NULL):

| Sütun | long | short |
|---|---|---|
| `slip_exec_entry` | `(entry_price − entry_ref_price) / entry_ref_price` | `(entry_ref_price − entry_price) / entry_ref_price` |
| `slip_exec_exit` | `(exit_ref_price − exit_price) / exit_ref_price` | `(exit_price − exit_ref_price) / exit_ref_price` |
| `slip_decision_exit` | `(exit_decision_price − exit_price) / exit_decision_price` | `(exit_price − exit_decision_price) / exit_decision_price` |

`v_decisions` ve `v_proposals` **dokunulmaz** (düşürülmez, yeniden kurulmaz).

Gecikme sütunu saklanmaz; okuyucu hesaplar: **gönderim→yanıt** = `order_ack_ts − order_ts` (aynı saat, güvenilir); **karar→gönderim** (giriş) = `entry_order_ts − v_decisions.bar_close_ts`; **gönderim→dolum** = `entry_ts − entry_order_ts` (borsa saati ile yerel saat karışır; eksi çıkabilir, yalnız bilgi). Benzetimli brokerda dolum zamanı mum sınırıdır; gecikme ölçüsü anlamsızdır ve rapor edilmez (`entry_ref_src='sim_open'` ile ayırt edilir).

### 2.4 Yeni tablo `shadow_decisions` (append-only)

```
id INTEGER PRIMARY KEY AUTOINCREMENT
bot TEXT NOT NULL CHECK (bot IN ('learner','twin'))
block TEXT NOT NULL CHECK (block IN ('regime_volatile','regime_unclear','r1_disabled','same_bar_reentry','tf_15m'))
bar_close_ts TEXT NOT NULL
trigger_tf TEXT NOT NULL CHECK (trigger_tf IN ('1h','15m'))
pair TEXT NOT NULL
side TEXT NOT NULL CHECK (side IN ('long','short'))
setup TEXT NOT NULL CHECK (setup IN ('T1','R1'))
regime TEXT NOT NULL CHECK (regime IN ('trend_up','trend_down','range','volatile','unclear'))
atr_ratio REAL
rh REAL, rl REAL
features TEXT NOT NULL            -- JSON; decision_events.features ile aynı anahtar kuralı (gates._features), ≤ 16 KiB
planned_entry REAL NOT NULL CHECK (planned_entry > 0)
planned_stop REAL NOT NULL CHECK (planned_stop > 0)
planned_target REAL
param_version_id INTEGER NOT NULL REFERENCES param_versions(id)
strategy TEXT NOT NULL            -- "ad@sürüm", örn. price_action_v1@1b.0
reasons TEXT NOT NULL             -- strateji gerekçe dizgisi, en çok 500 karakter (uzunsa sondan kesilir)
pos_open INTEGER NOT NULL CHECK (pos_open IN (0,1))   -- kayıt anında çiftte kapanmamış pozisyon var mı
gate_code TEXT                    -- o karar adımındaki çift-bağımsız kapı kodu ("ok" ya da kapı kodu); bilinmiyorsa NULL
recorded_at TEXT NOT NULL
CHECK ((side='long' AND planned_stop < planned_entry) OR (side='short' AND planned_stop > planned_entry))
UNIQUE (bot, block, pair, side, setup, trigger_tf, bar_close_ts)
```

Veto, risk, boyut, kaldıraç, `ml_score`, `final_action`, `skip_reason`, `supersedes_id` sütunu **yoktur**: gölge aday bu kapılardan hiç geçmez. Görünüm:

```
CREATE VIEW v_shadow_decisions AS SELECT s.*, 'shadow' AS final_action FROM shadow_decisions s;
```

`final_action='shadow'` sabiti, satırlar başka bir yerde kararlarla birleştirilirse ayırt edilsin diyedir. Değer `decision_events.final_action` CHECK'inde yoktur; oraya yazılamaz.

`block` anlamları:

| `block` | Bastırılan şey | `setup` | `trigger_tf` | `regime` |
|---|---|---|---|---|
| `regime_volatile`, `regime_unclear` | Koşul yasağı: `signals` bu koşullarda aday hesaplamaz | `T1` | `1h` | `volatile` / `unclear` |
| `r1_disabled` | v1b'de kapalı R1 kurulumu | `R1` | `1h` | `range` |
| `same_bar_reentry` | v1b: stop'la kapanan mumda yeniden giriş yasağı | `T1` | `1h` | `trend_up` / `trend_down` |
| `tf_15m` | v1b'de kapalı 15 dk tetik | `T1` ya da `R1` | `15m` | adayın koşulu |

### 2.5 Yeni tablo `equity_marks` (append-only)

```
id INTEGER PRIMARY KEY AUTOINCREMENT
bot TEXT NOT NULL CHECK (bot IN ('learner','twin'))
ts TEXT NOT NULL                  -- karar adımı zamanı D
wallet REAL NOT NULL              -- gerçekleşmiş bakiye
equity REAL NOT NULL              -- D anında wallet + açık pozisyonların gerçekleşmemiş K/Z'si
equity_low REAL NOT NULL          -- önceki işaretten bu yana dakika bazlı en kötü değer; equity_low <= equity
n_open INTEGER NOT NULL CHECK (n_open >= 0)
src TEXT NOT NULL CHECK (src IN ('sim','exchange'))
recorded_at TEXT NOT NULL
CHECK (equity_low <= equity)
UNIQUE (bot, ts)
```

### 2.6 Göç 3 → 4 (`_migration_3_to_4`, `MIGRATIONS` listesine eklenir)

Tek `BEGIN IMMEDIATE` işleminde, `migrate=True`, önceden `backup(<db>.premigrate-v3)` (mevcut mekanizma). Tablo yeniden kurulmaz; `_FK_OFF_MIGRATIONS`'a ekleme **yok**.

1. `ALTER TABLE trade_entries ADD COLUMN` × 5 (§2.1); `ALTER TABLE trade_exits ADD COLUMN` × 7 (§2.2). Hepsi varsayılansız (NULL). Sütun CHECK'leri sütun tanımında verilir (`CHECK (x IS NULL OR …)`).
2. `CREATE TABLE shadow_decisions …`, `CREATE INDEX ix_shadow_ts ON shadow_decisions (bot, bar_close_ts)`, `CREATE VIEW v_shadow_decisions …`.
3. `CREATE TABLE equity_marks …`.
4. `DROP VIEW v_closed_trades; DROP VIEW v_trades;` ardından §2.3 tanımıyla yeniden kurulur.
5. Append-only tetikleyiciler düşürülüp yeniden kurulur; `_APPEND_ONLY_TABLES`'a `shadow_decisions` ve `equity_marks` eklenir (`_EXPECTED_TRIGGERS` kendiliğinden genişler). `trg_trade_exits_excursion_check` dokunulmaz.
6. `PRAGMA user_version = 4`; `schema_migrations(3, 4)` satırı; `SCHEMA_VERSION = 4`.

Mevcut satırların yeni sütunları NULL kalır; geriye dönük doldurma yoktur. Yeni dosya 0 → 1 → 2 → 3 → 4 sırayla kurulur. Geri alma: `premigrate-v3` yedeği.

**Eski okuyucular:**
- Sürüm denetimi yapmayan ham SQL okuyucular (dondurulmuş derlem kodu, `drift_monitor`, `research/` betikleri, `backtest._decisions`, `LedgerReplayVeto`) sürüm 4 dosyasını değişiklik olmadan okur: adlandırdıkları sütunlar yerinde ve aynı sıradadır.
- `Ledger` sınıfıyla açanlar (motor, ders, pano, Telegram raporu, sağlık, karşı-olgu işi) bugünkü kuralla çalışır: sürüm 3 kodu sürüm 4 dosyasını, sürüm 4 kodu `migrate=False` ile sürüm 3 dosyasını reddeder (`defter-spec.md` §10.2). Bu yüzden `learner` ve `twin` defterleri **aynı kurulumda** göç eder; motor yeniden başlayana dek okuyucuların "şema" uyarısı beklenen geçici durumdur.
- `trader_reports.inputs.check_ledger_schema` bugün yalnız `(2, 3)` kabul eder; `(2, 3, 4)` olur (§8).
- Sürüm 2/3 geri test defterleri (`var/backtests/*`, `research/ml/frozen/*`) **göç ettirilmez**, yerinde bırakılır.

## 3. Madde 2 — emir anı kaydı

### 3.1 Değerler ve yakalandıkları yer

| Değer | Yakalama yeri (dosya:işlev) | Not |
|---|---|---|
| `order_ts` | `order_manager.py:OrderManager._submit` — `pending` emir satırını yazan `now` | Aynı değer bellekte `exec_meta[client_id]`'e konur. Bellekte yoksa `state.get_order(client_id).created_ts` kullanılır (kalıcıdır) |
| `order_ack_ts` | `order_manager.py:OrderManager._submit` — `_send` `None` olmayan sonuç döndürünce `clock.now()` | Yalnız `live_mode=True`; benzetimde yazılmaz |
| `order_ref_price` (benzetim) | `brokers/paper.py:PaperBroker._fill_entry`, `_fill_exit` — kayma uygulanmadan önceki taban `bar.last_o` | `types.Fill`'e eklenen `ref_price: float \| None = None` alanıyla taşınır; `order_ref_src='sim_open'` |
| `order_ref_price`, `order_ref_spread` (borsa) | §3.5 fiyat sorgusu | `order_ref_src='book'`; sorgu kapalıysa NULL |
| `decision_price` | `engine.py:Engine._exits` — `dec.kind == "exit"` iken (ve `would_trigger` → `trail_stop` yolunda) `ctx.last_close`, bellekte `trade_id` ile saklanır | `engine.py:Engine._on_exit_fill` yalnız `fill.reason == "market"` ise kullanır; değilse atar |
| Deftere yazım | `engine.py:Engine._on_entry_fill`, `_on_exit_fill` ve `reconcile_live.py`'deki üç `outbox_add` çağrısı | Hepsi tek saf yardımcıyı kullanır: `position_manager.exec_fields(role, meta, fill, order_row)` |

`exec_meta` bellekte tutulur (en çok 256 kayıt, ilk giren ilk çıkar; kullanılınca silinir). Durum deposuna (`state.sqlite`) **yeni sütun, yeni tablo ya da yeni `kv` yazımı eklenmez**; `state` şema sürümü 1 kalır. Yeniden başlatmada bellekteki kayıt kaybolur: `order_ts` emir satırından kurtarılır, diğerleri NULL olur.

`types.Fill.ref_price` varsayılanı `None` olan son alandır. `PaperBroker._ser_event` / `_de_event` alanı taşır; anahtarı olmayan eski anlık görüntü `None` okunur.

### 3.2 Referans fiyatın anlamı

- **Benzetim (`sim_open`):** emrin dolduğu dakikanın açılışı; modelin kayma uyguladığı taban. Bu yüzden `slip_exec_*`, yapılandırılmış kaymayı (giriş 2 bp, piyasa çıkışı 2 bp) tick yuvarlamasıyla birlikte verir; `slippage_entry − slip_exec_entry` ise karar mumu kapanışı ile dolum dakikası açılışı arasındaki kaymadır. Kağıtta bu, motorun öz denetimidir (`kagit-degerlendirme-plani.md` §4.2 son paragraf).
- **Borsa (`book`):** emir gönderilmeden hemen önce okunan en iyi alış/satışın ortası. `slip_exec_*` = yarım makas + piyasa etkisi + sorgu ile dolum arasındaki hareket.
- Model karşılaştırmasının asıl ölçüsü yine **karar fiyatına göre** kaymadır: girişte mevcut `slippage_entry`, piyasa çıkışında yeni `slip_decision_exit`. Bu ikisi kağıt, testnet ve canlıda aynı tanımla dolar ve ek ağ çağrısı gerektirmez.

### 3.3 `Ledger` API eklemeleri

- `TradeEntry` yeni isteğe bağlı alanlar (sona, varsayılan `None`): `order_ts: datetime`, `order_ack_ts: datetime`, `order_ref_price: float`, `order_ref_spread: float`, `order_ref_src: str`.
- `TradeExit` yeni isteğe bağlı alanlar (sona, varsayılan `None`): aynı beşi, artı `decision_price: float`, `exit_regime: str`.
- `TradeRecord` yeni isteğe bağlı alanlar (sona, varsayılan `None`): §2.3'teki on beş görünüm sütunu, aynı adlarla.
- `ledger.clean_exec_fields(d: Mapping) -> dict`: yalnız yukarıdaki yedi anahtarı döndürür; §2.1 kurallarını çiğneyen **grubu** `None` yapar. Gruplar: {`order_ts`, `order_ack_ts`}, {`order_ref_price`, `order_ref_spread`, `order_ref_src`}, {`decision_price`}, {`exit_regime`}. `order_ack_ts < order_ts` ise yalnız `order_ack_ts` düşer. Hiçbir girdide istisna atmaz.
- Eşgüdüm (idempotans) karşılaştırması (`_write_entry` / `_write_exit` içindeki `same`) yeni alanları **içermez**: aynı işlem aynı çekirdek alanlarla yeniden yazılırsa mevcut satırın `id`'si döner, ölçüm alanları ilk yazılan değerde kalır.
- Spool satırları yeni anahtarları taşır; anahtarı olmayan eski spool satırı `None` ile okunur.

### 3.4 Geçersiz ölçüm işlemi durduramaz

Motor yükü kurarken `clean_exec_fields`'ten geçirir; `Ledger` yine sıkı doğrular (`LedgerValidationError`). Böylece ölçüm alanı yüzünden `record_trade_entry` / `record_trade_exit` başarısız olamaz ve `outbox_stuck` girişi kapatamaz. Düşürülen her grup `records.exec.dropped` sayacını artırır (§9.3).

### 3.5 İsteğe bağlı fiyat sorgusu (yalnız testnet/canlı, varsayılan kapalı)

Yapılandırma: `live.order_quote` (bool, varsayılan `false`). Testnet yapılandırmasında `true` yapılır; **canlıda açılması ayrı mentor kararıdır** (testnette en az iki hafta sorunsuz kayıt ve `tasarim-kararlari.md` satırı).

Açıkken:
- Yalnız iki yerde çalışır: `Engine._enter`'ın gönderdiği giriş emri ve `Engine._exits`'in gönderdiği karar adımı çıkışları. KILL, stop bekçisi, `stop_failed` kapanışı, dolum sonrası risk ihlali, mutabakat ve elle çıkışlarda **çalışmaz**. Koruyucu stop emrinden önce hiçbir zaman çalışmaz.
- `GET /fapi/v1/ticker/bookTicker?symbol=…`, **tek deneme**, bağlantı + okuma toplamı en çok **0,5 sn**. Yeniden deneme, uyku, saat eşitleme yok.
- Çağrı öncesi: borsa yasağı/penceresi etkinse ya da kullanılan ağırlık sınırın %80'ini aşmışsa çağrı **hiç yapılmaz**.
- Her hata (zaman aşımı, HTTP, ayrıştırma, `bid ≤ 0`, `ask < bid`) yutulur ⇒ referans NULL, `records.exec.quote_errors += 1`. Hata `entries_blocked_reason`'ı, broker kilitlerini (`exchange_unreachable` vb.), `_note_ban` yolunu ve mevcut hiçbir sayacı **değiştirmez**. Yanıt başlığındaki ağırlık sayaçları normal biçimde okunur.
- Kağıt ve geri testte (`broker.is_simulated`) bu kod yolu çağrılmaz.

Bedeli açıkça: açıkken giriş ve karar adımı çıkış emri en çok 0,5 sn (tipik < 0,2 sn) geç gider. Kararın kendisi, boyutu ve stop'u değişmez.

## 4. Madde 16 — `exit_regime`

- `engine.py:Engine._decision_step`: çerçeveler hesaplandıktan sonra, `fr.status == "ok"` ve `fr.last` dolu olan her çift için bellekte `(D, fr.last.regime)` saklanır. Durumu `ok` olmayan çiftin eski kaydı **güncellenmez**.
- `engine.py:Engine._on_exit_fill` (ve `reconcile_live.py`'deki çıkış yazımı): `exit_regime` = o çiftin saklı etiketi, **ancak** `0 ≤ fill.ts − D ≤ tf_delta(tf) + 120 sn` ise; değilse NULL.
- Yalnız bellekte tutulur; yeniden başlatmadan sonraki ilk karar adımına dek NULL yazılır.
- `regime_flip` çıkışında değer, çıkışı tetikleyen (dönmüş) koşuldur. Giriş koşulu mevcut `v_trades.regime`'dir.
- Geri testte de dolar; `trades.csv`'ye girmez (`TRADES_COLUMNS` değişmez), `ledger.sqlite`'tan okunur.

## 5. Madde 7 / A-11 — gölge karar satırları

### 5.1 Yapılandırma

`shadow_blocks`: `["regime", "r1_disabled", "same_bar_reentry", "tf_15m"]` alt kümesi (liste; varsayılan `[]` = kapalı; `config._OPTIONAL_KEYS`'e eklenir). `regime` iki `block` değerini birlikte açar. `config/engine.base.json` dördünü de açar; `engine.twin.json` `[]` yapar (ikiz botta gölge yok: aynı piyasa, ikinci kopya gereksiz).

Geri test: `BacktestRunner.build_config` `shadow_blocks=()` **zorlar**. Yeni bayrak `--record-shadow` verilirse `("regime", "r1_disabled", "same_bar_reentry")` açılır; `tf_15m` geri testte **desteklenmez**.

### 5.2 Ne zaman çalışır

`engine.py:Engine.decision_step`: `_guard` başarılı döndükten, `_post_commit()` ve `status.write` bittikten **sonra** `Engine._shadow_step(D)` çağrılır. Yani o karar adımının bütün çıkış, giriş, emir, defter ve durum işleri tamamlanmıştır. `_shadow_step`:
- istisna sızdırmaz (her şey yakalanır, `records.shadow.errors` artar);
- `state`, `broker`, `orders`, `gate`, `veto`, `kill`, `pause`, `ladder` üzerinde **hiçbir yazma ya da çağrı** yapmaz; yalnız `state.position_for_pair` (okuma), saklı çerçeveler, `view.bars` (yalnız `tf_15m`) ve `ledger.record_shadow` kullanır;
- zaman bütçesi `shadow_budget_s = 5.0`: çiftler arasında denetlenir, aşılırsa kalan çiftler atlanır (`records.shadow.budget_skips`);
- `self._stop` kuruluysa ya da `shadow_blocks` boşsa hiçbir şey yapmaz.

Saf hesap yeni modüldedir: `src/trader_engine/shadow.py` (saat, ağ, durum yok; `datetime.now()` yok).

### 5.3 Blok başına aday kuralı

Her blok için aday yalnız **doğal olarak geçerli** ise yazılır: stop genişliği (ve R1'de `rr_min`) süzgeçlerinden geçmiş olmalı. Süzgeçte kalan aday gölge satır olmaz.

1. **`r1_disabled`** — kaynak: o çiftin karar mumu satırı (`SignalFrame.last`). Koşul: `signal == False`, `skip_reason is None`, `setup == "R1"`, `side` dolu, `reasons` `v1b:r1_disabled|` ile başlar ve ön ekler atıldıktan sonra `,stop_ok,rr_ok` ile biter. Alanlar satırdan kopyalanır.
2. **`same_bar_reentry`** — aynı kaynak. Koşul: `signal == False`, `skip_reason is None`, `reasons` `v1b:same_bar_reentry|` ile başlar ve ön ek atıldıktan sonra `,stop_ok` ile biter (ML etiketi `ml:p=…|` varsa o da ön ektir).
3. **`regime_volatile` / `regime_unclear`** — kaynak: aynı satır ve çerçeve tablosu. Koşul: `reasons == "regime_blocked"` ve `regime ∈ {volatile, unclear}`. Aday `shadow.regime_candidate(table, params)` ile üretilir:
   - tablonun son `STOP_LOOKBACK` (5) mumunda ve EMA penceresinde geçersiz OHLC varsa ⇒ aday yok;
   - `ema_last = indicators.ema(table["close"], params.pullback_ema)` son değeri; `a = atr_tf` son değeri;
   - `signals.evaluate_t1(side, o, h, l, c, ema_last, recent, a, params)` **iki yön için** çağrılır (`recent` = long için son 5 düşük, short için son 5 yüksek). Tetik koşulları birbirini dışlar (yükselen / düşen gövde); `skip_reason is None` dönen tek aday alınır;
   - `setup='T1'`, `planned_target=NULL`, `rh=rl=NULL`.
   Sınır: bu, "koşul yasağı olmasaydı EMA geri çekilme tetiği ne yapardı" sorusunun cevabıdır; trend yönü bilgisi olmadan iki yöne de bakar. Bu koşullarda R1 adayı tanımsızdır (bant yok), üretilmez.
4. **`tf_15m`** — `shadow.tf15_candidates(view, pair, D, params)`:
   - girdi `view.bars(pair, "15m", D, 5000)` ve `view.bars(pair, "4h", D, 1500)`; ısınma (4800 / 300 mum), son mum açılışı `D − 15 dk` ve kesintisizlik koşulları 1 saatlik yolla aynıdır; sağlanmazsa aday yok;
   - `regime.classify_series` → `regime.align_to_base(…, 4)` → `signals.compute_signals`, etkin parametrelerin `trigger_tf="15m"` kopyasıyla;
   - mum kapanışı `(D − 1 sa, D]` aralığında ve `signal == True` olan satırlar adaydır (saatte en çok 4 mum × çift);
   - **Kilitli dönem bekleme kuralı:** pencerenin ilk mumu `2026-11-01T00:00Z`'den önceyse hesap yapılmaz (`records.shadow.tf15_holdout_wait`). 5000 × 15 dk ≈ 52,1 gün olduğundan ilk satırlar yaklaşık **23 Aralık 2026**'dan sonra gelir. (Diğer üç blok yeni piyasa okuması yapmaz; motorun işlem için zaten hesapladığı çerçeveyi kullanır.)
   - Kesinti sırasında kaçan 15 dk mumları geriye dönük doldurulmaz.
   - Sınır: göstergeler pencere başından özyinelemeli hesaplandığı için değerler, 15 dk tetikle canlı çalışan bir motorunkiyle sayısal olarak çok yakın ama bit düzeyinde aynı olmayabilir. Kanıt yaklaşık sayılır.

Ortak: `bar_close_ts` kilitli dönemdeyse satır yazılmaz. `pos_open` = `state.position_for_pair(pair) is not None`. `gate_code` = o adımın `pre.code` değeri. ML puanı hesaplanmaz.

**Değişmez:** hiçbir gölge satır, aynı `(pair, side, setup, trigger_tf, bar_close_ts)` anahtarlı bir `v_decisions` satırıyla birlikte bulunamaz (koşullar gereği; test §12 S9).

### 5.4 Hacim beklentisi

Dayanak koşuda 18 ayda `same_bar_reentry` 11 kez. Koşul ve R1 gölgeleri günde birkaç satırı, `tf_15m` günde on-yirmi satırı geçmez. Üst sınır varsayımı: günde 60 satır ≈ yılda 22 000 satır ≈ 10 MB.

### 5.5 `Ledger` API

- `ShadowEvent` (frozen dataclass): §2.4 sütunları (`id`, `bot`, `recorded_at` hariç); `features: Mapping`.
- `Ledger.record_shadow(ev) -> int`: doğrular, ekler. Aynı benzersiz anahtar varsa **yeni satır yazmaz, mevcut `id`'yi döndürür** (içerik karşılaştırılmaz; ilk yazılan kalır). `bot='twin'` defterinde de çalışır.
- `Ledger.list_shadow(*, since_ts=None, until_ts=None, block=None, limit=None) -> list[ShadowRecord]` (`bar_close_ts, id` sıralı).
- `record_shadow` ve `record_equity_mark`: `LedgerWriteError` durumunda `_on_write_failure` **çağırmaz**, spool'a yazmaz; başarıda `_last_write_ok`'u **güncellemez**.

## 6. Madde 18 — anlık değerli düşüş

### 6.1 Tanımlar

Dakika adımı `m`'de, durumu `open` ya da `closing` olan ve `entry_price`, `qty` dolu her pozisyon `p` için (`sgn` = long +1, short −1):
- kapanış fiyatı `c_p` = `mark_c`, yoksa `last_c`; ters uç `w_p` = long için `mark_l` (yoksa `last_l`), short için `mark_h` (yoksa `last_h`);
- `u_close = Σ sgn·(c_p − entry)·qty`, `u_worst = Σ sgn·(w_p − entry)·qty`.

`eq_worst(m) = wallet + u_worst`. Bu **temkinli alt sınırdır**: çiftlerin ters uçları aynı anda oluşmamış olabilir.

Karar adımı `D`'de bir işaret üretilir: `wallet` ve `equity` = `broker.account()`'tan; `equity_low = min(equity, önceki işaretten beri görülen eq_worst değerleri)`; `n_open` = açık pozisyon sayısı. `wallet` kaynağı benzetimde her dakika `broker.account().wallet`; borsada son karar adımında okunan değer (ek REST çağrısı yapılmaz; hesap önbelleği kullanılır). Borsada saat içinde kapanan işlemin gerçekleşmiş K/Z'si `equity_low`'a bir sonraki işarette yansır (bilinen sınır).

### 6.2 Yakalama yeri

- `engine.py:Engine._process_step` ve `_process_step_live`: açık pozisyonlar için `update_excursion` döngüsünden sonra `MtmRecorder.on_minute(ts, step.bars, positions, wallet)`.
- `engine.py:Engine.decision_step`: `_shadow_step` ile aynı noktada (`_post_commit` ve durum yazımından sonra) `MtmRecorder.on_decision(D, account, n_open)`.
- Yeni modül `src/trader_engine/mtm.py` (`MtmRecorder`; saf birikim + enjekte edilen yazıcı). Kağıt/testnet/canlı: yazıcı `ledger.record_equity_mark` (karar adımı başına bir satır, günde 24). Geri test: bellekte liste; koşu sonunda dosyaya.
- Yapılandırma `mtm_marks` (bool, varsayılan `true`; `_OPTIONAL_KEYS`).

`MtmRecorder` yalnız okur: `broker.account()` (benzetimde saf), `step.bars`, `state.open_positions()` sonucu. `engine.counters()`'a anahtar eklemez.

### 6.3 `metrics.py` eklemeleri (saf işlevler; mevcutlar değişmez)

`max_drawdown` ve `compute_metrics` **dokunulmaz**. Yeni:

`drawdown_stats(equity, low, start) -> dict` — `equity[i]`, `low[i]` aynı uzunlukta, `start` başlangıç bakiyesi. `curve = [start] + equity`; `peak[k] = max(curve[0..k])`.
- Kapanış bazlı: `dd[k] = peak[k] − curve[k]`; `max_dd_mtm_abs = max(dd)`, `max_dd_mtm_pct = 100·dd[k*]/peak[k*]`.
- Dip bazlı: `ddl[i] = peak[i] − low[i]` (`peak[i]`: `i`. aralık **başlamadan önceki** tepe, yani `curve[0..i]`); `max_dd_mtm_low_abs`, `max_dd_mtm_low_pct = 100·ddl[i*]/peak[i*]`.
- `max_underwater_steps`: `curve[k] < peak[k]` olan en uzun ardışık dizi.
- Boş girdi ya da hiç düşüş yoksa bütün değerler 0.

`max_consecutive_losses(realized_pnl_by_exit_order) -> int`: `< 0` olan en uzun ardışık dizi.

**Örnek (elle doğrulanabilir):** `start=1000`, `equity=[1010, 990, 1005, 1020, 980]`, `low=[1000, 970, 985, 1004, 960]`.
- `curve=[1000,1010,990,1005,1020,980]`, `peak=[1000,1010,1010,1010,1020,1020]`, `dd=[0,0,20,5,0,40]` ⇒ `max_dd_mtm_abs=40`, `max_dd_mtm_pct=40/1020·100=3,9216`.
- `ddl=[1000−1000, 1010−970, 1010−985, 1010−1004, 1020−960]=[0,40,25,6,60]` ⇒ `max_dd_mtm_low_abs=60`, `max_dd_mtm_low_pct=60/1020·100=5,8824`.
- `max_underwater_steps=2` (990, 1005).

### 6.4 Geri test çıktıları (yeni dosyalar)

- `equity_mtm.csv`: `ts,wallet,equity,equity_low,n_open` (karar adımı başına satır; dayanak koşuda 13 104 satır ≈ 1 MB).
- `mtm.json`: `{"schema": "mtm/1", "wallet_start", "n_rows", "max_dd_realized_pct", "max_dd_realized_abs", "max_dd_mtm_pct", "max_dd_mtm_abs", "max_dd_mtm_low_pct", "max_dd_mtm_low_abs", "peak_ts", "trough_ts", "low_peak_ts", "low_trough_ts", "max_underwater_steps", "max_consecutive_losses"}`. `max_dd_realized_*`, `summary.json`'daki `max_dd_pct` / `max_dd_abs` ile aynı sayıdır.

`summary.json`'a anahtar eklenmez. Mevcut hiçbir eşik (`risk-kilidi`, merdiven, WP-0 kuralları) yeni ölçüye bağlanmaz.

`Ledger` API: `EquityMark` (frozen dataclass), `record_equity_mark(m) -> int` (aynı `(bot, ts)` varsa mevcut `id`), `list_equity_marks(*, since_ts=None, until_ts=None)`.

## 7. Gölge adayların karşı-olgusu (tüketici işi, motor işinden sonra)

`rapor-paketi-spec.md` §7.4'ün sütunları dolabilsin diye gece işi (`scripts/counterfactual_run.py`, `trader_core/counterfactual.py`) genişler:

- Defterde `v_shadow_decisions` varsa satırlar okunur (salt okunur; `Ledger.list_shadow`). Yoksa (sürüm < 4) bu adım sessizce atlanır.
- Hesap `alinmayan-sinyal-spec.md` ile **aynıdır** (`replay`, `barrier` 72 mum + `plan` 48 mum, ufuk tamamen dolmadan hesap yok, `data_gap` kuralı, kilitli dönemle kesişen pencere okunmaz). `tf_15m` satırları 1 saatlik ızgarada oynatılır (yaklaşık; aynı belgedeki bilinen sınır).
- Sonuç **ayrı tabloya** yazılır: `cf_shadow_outcomes`, anahtar `(bot, shadow_id, method)`; sütunlar `cf_outcomes` ile aynı, `decision_id` yerine `shadow_id`, `skip_reason` yerine `block`. `CREATE TABLE IF NOT EXISTS`; depo `user_version` **1 kalır**.
- `cf_outcomes` tablosu, `counterfactual.outcomes()` ve `counterfactual.summary()` gölge satır **içermez ve döndürmez**. Gölge okuması ayrı işlevdir: `counterfactual.shadow_outcomes(path, bot, *, now, days=None, method="barrier")`.
- İşin tek satır JSON çıktısına yalnız yeni anahtarlar eklenir (`shadow_scanned`, `shadow_computed`, `shadow_pending`, `shadow_rows_written`, `shadow_holdout_skipped`); mevcut anahtarlar ve çıkış kodları aynıdır.

## 8. Tüketiciler: kim ne yapmalı

Gölge satırlar ayrı tabloda olduğu için aşağıdaki tüketicilerin çoğunda **kod değişikliği yoktur**; her biri için "dokunmuyor" iddiası testle kilitlenir (§12 T grubu).

| Tüketici | Bugün ne okur | Gereken |
|---|---|---|
| Dondurulmuş derlem: `research/ml_build_candidates.py:read_ledger`, `scripts/build_corpus_v2.py` | `v_decisions`, `v_trades` (adlı sütunlar) | **Değişiklik yok, dosyaya dokunulmaz.** Çıktı eşitliği testi T1 |
| `scripts/build_corpus_v2_overlay.py` | aynı | Değişiklik yok |
| Sağlık: `scripts/health_run.py:probe_ledger`, `Ledger.find_orphan_decisions` | `v_decisions` (`entered`), `v_trades`, `_TS_TABLES` | Değişiklik yok. `status.json`'daki yeni `records` anahtarını yok sayar (T4) |
| Yedek: `scripts/health_backup.py` | bütün tablolar (`_max_ids`), tetikleyici sayısı | Değişiklik yok; yeni tablolar kendiliğinden yedeklenir (T5) |
| Sapma izleyicisi: `trader_core/drift_monitor.py` | `v_closed_trades` (`SELECT *`), `v_decisions` | Değişiklik yok; yeni sütunları kullanmaz (T2) |
| Ders servisi: `trader_core/lesson.py` | `Ledger.list_decisions`, işlem okumaları, `counterfactual.outcomes` | Değişiklik yok. `shadow_decisions` ve `cf_shadow_outcomes` **okuyamaz** (T3, durağan test) |
| Karşı-olgu (25a) | `list_decisions(final_action="skipped")` | §7 eki; mevcut sonuçlar aynı (T6) |
| Çıkış karşı-olgusu (WP-5, henüz kod yok) | `v_closed_trades` | Etkilenmez |
| Pano: `trader_core/panel_data.py`; Telegram günlük raporu: `trader_core/telegram.py` | `Ledger` okuma API'si | Değişiklik yok (T2) |
| `precomputed.LedgerReplayVeto`, `backtest._decisions`, `backtest.equality_report`, `research/bt_*.py` | `v_decisions`, `v_trades` | Değişiklik yok |
| Rapor paketi: `trader_reports` | `v_decisions`, `v_closed_trades`, `cf_outcomes` | **Değişir** (aşağıda) |

**Rapor paketinde yapılacaklar** (`rapor-paketi-spec.md`'ye v1.1 olarak işlenir; rapor yine yalnız okur):
1. `inputs.check_ledger_schema`: `(2, 3, 4)`.
2. §7.4 sabit satırları `v_decisions` üzerindeki yüklemler yerine `v_shadow_decisions.block`'tan gelir: `koşul:volatile` ← `regime_volatile`; `koşul:unclear` ← `regime_unclear`; `R1 kapalı (v1b)` ← `r1_disabled`; `15m kapalı` ← `tf_15m`; yeni satır `aynı mumda yeniden giriş` ← `same_bar_reentry`. Karşı-olgu `cf_shadow_outcomes`'tan. `n_engel` = satır sayısı; ek sütun `n_pozisyon_acik` (`pos_open=1`); `pay` sütunu bu tabloda `—` (gölge satırlar karar paydasına **girmez**). Tablo yoksa bugünkü `kanit_yok` + not korunur. Kapı karnesinin 2.1 tablosu, `n_engel_toplam` ve `pay` paydası gölge satırlardan **etkilenmez**.
3. §8.5 `exit_regime` geçiş tablosu `v_closed_trades.exit_regime` var olduğu için kendiliğinden üretilir (kod hazır).
4. Kilitli dönem koruması (`guard.py`) gölge satır okumasına da uygulanır.

## 9. Başarım ve bellek sınırları (2 GB sunucu)

### 9.1 Sınırlar

| Kalem | Sınır |
|---|---|
| Motor süreci kalıcı bellek artışı (gölge + MtM + `exec_meta` açıkken, 10 çift) | ≤ 20 MB |
| `_shadow_step` süresi (10 çift, dört blok açık) | tipik ≤ 2 sn; sert bütçe 5 sn (aşım ⇒ kalan çift atlanır) |
| `_shadow_step` geçici bellek | ≤ 30 MB (çiftler sırayla işlenir, 15 dk tablosu çift bitince bırakılır) |
| `MtmRecorder.on_minute` | dakika adımı başına O(açık pozisyon); ek sorgu, ek REST, ek dosya yazımı yok |
| Karar adımı başına ek defter yazımı | en çok 1 `equity_marks` + o adımın gölge satırları; hepsi karar adımının işlemlerinden **sonra** |
| Geri test süresi (gölge kapalı) | dayanak komutta artış ≤ %2 |
| Geri test belleği | `equity_mtm` listesi ≤ 5 MB (saatlik satır); dakika serisi **tutulmaz** |
| Göç 3 → 4 | tablo yeniden yazılmaz; 100 MB'lık defterde ≤ 5 sn (yedek kopyası hariç) |
| Defter büyümesi | gölge ≤ 10 MB/yıl, `equity_marks` ≤ 1 MB/yıl, yeni sütunlar işlem başına < 200 bayt |
| Gece karşı-olgu işi | mevcut `MemoryMax=128M` içinde kalır |

### 9.2 Yasaklar

- Motor içinde yeni iş parçacığı, yeni süreç, yeni zamanlayıcı yok.
- `shadow.py` ve `mtm.py` modül düzeyinde `pandas` dışında ağır içe aktarma yapmaz; `trader_ml`, `trader_reports`, `requests` içe aktarmaz. `tests/engine/test_engine_import_weight.py`, `test_engine_dependency_direction.py`, `test_engine_clock_discipline.py`, `test_engine_module_inventory.py` geçmeye devam eder (envanter listesine iki modül eklenir).
- Geri testte `tf_15m` yok (15 dk × 5 yıl × 10 çift tablosu çift başına onlarca MB tutar).

### 9.3 Gözlem

`status.json`'a tek yeni üst düzey anahtar: `records = {"shadow": {"rows", "errors", "budget_skips", "tf15_holdout_wait", "last_step_ms"}, "mtm": {"rows", "errors"}, "exec": {"dropped", "quote_errors"}}`. Bu sayaçlar `engine.counters()`'a **girmez** (aksi `summary.json` değişirdi). Hiçbiri alarm üretmez; sağlık kuralı eklenmez.

## 10. "Davranış değişmedi" kanıtı

**Taban commit** = WP-3 kodu başlamadan önceki `HEAD`. **Yeni commit** = WP-3 bitmiş hali. Koşular ayrı çalışma kopyalarında, aynı makinede, aynı veriyle (`var/history`) yapılır.

**K1 — kısa altın koşu (her inceleme turunda; ≈ 15 dk):**
```
python -m trader_engine backtest --id wp3_k1 --period 20250101-20250401 --tf 1h --fill-model native \
  --strategy price_action_v1 --synthetic-rules --target-trade-risk 0.005 \
  --pairs BTC/USDT,SOL/USDT,AVAX/USDT --out-root <geçici>
```
Taban ve yeni commit çıktıları arasında:
1. `trades.csv`, `summary.json`, `open_at_end.json` **sha256 eşit**.
2. `meta.json`, `git_commit` ve `duration_s` dışında eşit.
3. `ledger.sqlite`: `SELECT * FROM v_decisions ORDER BY id` satır satır eşit (bütün sütunlar); `v_trades`'in taban sütunları (`bot` … `excursion_tf`) satır satır eşit; `param_versions`, `param_activations` eşit.
4. Yeni commit çıktısında `shadow_decisions` **boş**; `equity_mtm.csv` ve `mtm.json` var; `mtm.json.max_dd_realized_pct == summary.json.max_dd_pct`.
5. İşlem sayısı ≥ 20 olmalı (değilse pencere aynı yıl içinde genişletilir ve komut belgeye işlenir).

**K2 — gölge açık koşu:** K1 komutu + `--record-shadow`. Madde 1–3 yine geçerli (gölge kayıt işlem çıktısını değiştirmez). `shadow_decisions` satırlarının hepsi §2.4 kısıtlarını ve §5.3 değişmezini sağlar.

**K3 — dayanak koşu (birleştirmeden önce bir kez; ≈ 5 saat, geliştirme makinesinde, sunucuda değil):** `kagit-degerlendirme-plani.md` §1'deki koşu aynı bayraklarla yeniden üretilir (`--period 20241101-20260501 --tf 1h --fill-model native --strategy price_action_v1 --synthetic-rules --target-trade-risk 0.005`, 10 çift). Beklenen: `trades.csv` sha256 `5fd204a0a34be9a2ced0d55a29f6893b1de361d897016062d6d557c2a7b69061`, `summary.json` sha256 `ea2f58ca9a75f77895015978ec2beb8fa3af41924f39daa541531cba5a73228c`.

**Ön koşul:** K3 önce **taban commit**'te koşulur. Taban bu iki özeti üretmiyorsa iş durur, mentora bildirilir (fark WP-3'ten değildir, ama kanıt zemini yoktur). K1/K2 tabanı her zaman aynı gün üretilir.

**K4 — kağıt eşdeğerliği (birim düzeyi):** sahte borsa/saat ile aynı dakika ve karar adımı dizisi, bir kez `shadow_blocks=[]`, `mtm_marks=false`; bir kez hepsi açık çalıştırılır. İki koşuda `state` (pozisyonlar, emirler, `decided`, imleçler), `decision_events`, `trade_entries` / `trade_exits`'in taban sütunları ve brokera giden çağrı dizisi (yöntem, sıra, bağımsız değişkenler) **aynıdır**.

Hiçbir koşu kilitli dönemle kesişmez.

## 11. Uygulama sırası (tek ajan, sırayla; her adım kendi commit'i)

1. **S1 Defter:** şema 4, göç, yeni dataclass alanları, `clean_exec_fields`, `record_shadow`, `record_equity_mark`, okuma API'si, görünümler. `defter-spec.md`'ye Revizyon 4 notu.
2. **S2 Emir anı + `exit_regime`:** `Fill.ref_price`, `exec_meta`, `exec_fields`, `decision_price`, koşul belleği. K1.
3. **S3 MtM:** `mtm.py`, `metrics` işlevleri, geri test dosyaları, `equity_marks`. K1.
4. **S4 Gölge:** `shadow.py`, `_shadow_step`, yapılandırma, `--record-shadow`. K1, K2, K4.
5. **S5 Tüketiciler:** karşı-olgu eki (§7), rapor paketi (§8), `rapor-paketi-spec.md` v1.1.
6. **S6 İsteğe bağlı fiyat sorgusu (§3.5):** en son; testnet duman testiyle.
7. K3, ardından mentor incelemesi ve birleştirme. Kurulum: iki bot durdurulur, kod güncellenir, motorlar başlatılır (defterler kendiliğinden göç eder), okuyucular sonra.

Motor dosyasına dokunan her birleştirme `tasarim-kararlari.md` koşuluna tabidir (§10 dondurma kaydı commit'lendikten sonra, mentor incelemesiyle).

## 12. Kabul testleri (bağımsız test ajanı; kodu okumadan yazılır)

Testler sahte saat ve geçici dosyalarla çalışır; ağ yok. Test verilerinde kilitli döneme düşen tarih kullanılmaz (`tests/engine/test_no_holdout_in_tests.py`).

**D — defter ve göç**
- D1. Yeni dosya: `PRAGMA user_version = 4`; `schema_migrations`'ta `(3, 4)` satırı; `shadow_decisions`, `equity_marks`, `v_shadow_decisions` var.
- D2. Sürüm 3 dosyası (10 karar, 4 giriş, 3 çıkış ile) `migrate=True` açılınca: `<db>.premigrate-v3` oluşur; her tablonun satır sayısı ve mevcut sütun değerleri bayt bayt aynı; yeni sütunların hepsi NULL; `foreign_key_check` boş.
- D3. Sürüm 3 dosyası `read_only=True` ya da `migrate=False` ile ⇒ `LedgerSchemaError`; dosya değişmez.
- D4. `PRAGMA table_info(v_trades)`: ilk sütunlar sürüm 3 görünümüyle **aynı ad ve sırada**, ardından tam olarak §2.3'teki on beş sütun o sırayla. `v_decisions` sütun listesi sürüm 3 ile aynı.
- D5. `shadow_decisions` ve `equity_marks` üzerinde `UPDATE` ve `DELETE` ⇒ `append-only` hatası.
- D6. Yeni alanlar verilmeden yazılan `TradeEntry` / `TradeExit` ⇒ yeni sütunlar NULL; diğer bütün sütunlar sürüm 3 davranışıyla aynı (aynı girdiyle sürüm 3'te üretilmiş beklenen değerlerle karşılaştırılır).
- D7. Tam alanlı `TradeEntry` (`order_ts=T`, `order_ack_ts=T+180 ms`, `order_ref_price=100.0`, `order_ref_spread=0.0002`, `order_ref_src="book"`), long, dolum 100.02 ⇒ `v_trades.slip_exec_entry = 0.0002` (± 1e-12). Aynısı short, dolum 99.98 ⇒ `0.0002`.
- D8. Long çıkış: `order_ref_price=200.0`, `decision_price=200.5`, dolum 199.9 ⇒ `slip_exec_exit = 0.0005`, `slip_decision_exit = 0.6/200.5` (± 1e-12). `planned_exit=None` ⇒ `slippage_exit IS NULL` (değişmedi).
- D9. Doğrulama: `order_ref_price=-1`; `order_ref_src="x"`; `order_ref_price` var `order_ref_src` yok; `order_ref_spread` var `src="sim_open"`; `order_ack_ts < order_ts`; `order_ack_ts` var `order_ts` yok; `exit_regime="sideways"`; `decision_price=0` ⇒ her biri `LedgerValidationError`, satır yazılmaz.
- D10. `clean_exec_fields`: D9'daki her girdide istisna yok; ihlal eden grup `None`, diğer gruplar korunur; temizlenmiş yük deftere yazılabilir. Sayı olmayan, `NaN`, `inf`, tz'siz `datetime` girdileri de `None` olur.
- D11. İdempotans: aynı çekirdek alanlı `TradeEntry` iki kez, ikincisinde farklı `order_ref_price` ⇒ aynı `id` döner, saklı değer ilk yazılandır, istisna yok. Çekirdek alanı farklı ⇒ bugünkü gibi `LedgerConflictError`.
- D12. Spool: yazma hatası benzetilir; spool satırı yeni anahtarları taşır; `drain_spool` sonrası sütunlar dolu. Yeni anahtarları olmayan eski biçimli spool satırı da işlenir (NULL).
- D13. `record_shadow`: geçerli olay yazılır; aynı benzersiz anahtarla ikinci çağrı aynı `id`, satır sayısı 1. Geçersiz `block`, yanlış taraftaki stop, 16 KiB'i aşan `features` ⇒ `LedgerValidationError`.
- D14. `record_shadow` / `record_equity_mark` yazma hatası benzetilir ⇒ çağıran istisna alır, **ama** hemen ardından `entries_allowed().ok` önceki değerindedir, spool dosyası oluşmaz. Başarılı gölge yazımı, bayatlamış `_last_write_ok` yaşını tazelemez (61 sn sonra `entries_allowed` yine `check_writable` çağırır).
- D15. `list_decisions()` ve `SELECT COUNT(*) FROM v_decisions`, 50 gölge satır eklenmeden önce ve sonra aynı sonucu verir. `find_orphan_decisions` sonucu aynıdır.
- D16. `record_equity_mark`: `equity_low > equity` ⇒ `LedgerValidationError`; aynı `(bot, ts)` ikinci kez ⇒ aynı `id`.

**E — emir anı kaydı ve `exit_regime` (motor, sahte broker)**
- E1. Benzetim girişi: karar adımında aday, sonraki dakika açılışı `50000.0`, giriş kayması 2 bp, tick `0.1` ⇒ `entry_ref_price = 50000.0`, `entry_ref_src = 'sim_open'`, `entry_ref_spread IS NULL`, `entry_order_ack_ts IS NULL`, `entry_order_ts` = karar adımı saati; `0.0002 − 1e-12 ≤ slip_exec_entry ≤ 0.0002 + 0.1/50000`.
- E2. Benzetim, karar adımı çıkışı (`time_stop` ya da `regime_flip`): `exit_decision_price` = karar mumunun kapanışı; `exit_ref_src = 'sim_open'`; `slip_exec_exit` çıkış kayması için E1'deki bantta; `slippage_exit IS NULL`.
- E3. Stop dolumuyla çıkış: `exit_order_ts`, `exit_order_ack_ts`, `exit_ref_*`, `exit_decision_price` hepsi NULL; `planned_exit` ve `slippage_exit` sürüm 3 ile aynı değerde.
- E4. Yarış: karar adımı çıkış kararı verdi, ama pozisyon dinlenen stop'la kapandı ⇒ `exit_decision_price IS NULL`. Aynı çiftte sonraki işlemin çıkışına bu eski değer **taşmaz**.
- E5. Yeniden başlatma: giriş emri gönderildikten sonra, dolumdan önce motor yeniden kurulur ⇒ giriş satırı yazılır; `entry_order_ts` emir satırının oluşturulma zamanıdır; `entry_ref_price IS NULL` olabilir; hata yok.
- E6. `exit_regime`: (a) son karar adımında çiftin koşulu `trend_down`, dolum 10 dk sonra ⇒ `trend_down`; (b) son karar adımı `tf + 121 sn`'den eski ⇒ NULL; (c) son karar adımında çiftin çerçevesi `data_gap` ⇒ önceki adımın değeri yaş sınırı içindeyse o, değilse NULL; (d) yeniden başlatmadan sonra, karar adımı olmadan gelen dolum ⇒ NULL.
- E7. `regime_flip` çıkışında `exit_regime`, girişteki `regime`'den farklıdır ve çıkışı tetikleyen koşula eşittir.
- E8. Canlı yol (sahte borsa, `live_mode`): `entry_order_ack_ts ≥ entry_order_ts`; sahte saatle yanıt 180 ms sonra ⇒ fark tam 180 ms.
- E9. Fiyat sorgusu kapalı (`live.order_quote=false`): sahte borsaya `bookTicker` çağrısı **hiç** gitmez; `entry_ref_price IS NULL`.
- E10. Fiyat sorgusu açık: `bid=99.99`, `ask=100.01` ⇒ `entry_ref_price = 100.0`, `entry_ref_spread = 0.0002`, `src='book'`; çağrı piyasa emrinden **önce**, tam bir kez. Koruyucu stop emrinden önce sorgu çağrısı yok.
- E11. Sorgu hatası (zaman aşımı; HTTP 500; `ask < bid`; `bid = 0`): emir yine gönderilir, giriş açılır, stop kurulur; `entry_ref_price IS NULL`; `records.exec.quote_errors` 1 artar; `entries_blocked_reason` boş kalır; `counters()` çıktısı hatasız koşuyla aynıdır.
- E12. KILL çıkışı, stop bekçisi çıkışı ve `stop_failed` kapanışında sorgu çağrısı yok.
- E13. Borsa yasağı penceresi etkinken ya da ağırlık ≥ %80 iken sorgu çağrısı yapılmaz, emir akışı değişmez.
- E14. Sorgu yanıtı 0,5 sn'yi aşacak biçimde geciktirilir ⇒ emir, sahte saate göre en geç 0,5 sn sonra gönderilir.

**S — gölge satırlar**
- S1. `shadow_blocks=[]` ⇒ `record_shadow` hiç çağrılmaz; `view.bars(…, "15m", …)` hiç çağrılmaz.
- S2. `r1_disabled`: karar mumunda `reasons = "v1b:r1_disabled|R1_long:…,stop_ok,rr_ok"`, `setup="R1"`, `side="long"` ⇒ bir satır; `planned_*`, `rh`, `rl`, `regime='range'` satırdakiyle aynı; `block='r1_disabled'`. Aynı satır `…,stop_ok,rr_below_min` ya da `…,stop_width` ile bitiyorsa ⇒ satır yok.
- S3. `same_bar_reentry`: `reasons = "v1b:same_bar_reentry|T1_long:…,stop_ok"` ⇒ bir satır. `ml:p=0.612345|` ön eki de varsa yine bir satır.
- S4. `regime_candidate`: son mum `o=100, h=102, l=99, c=101.5`, EMA son değeri `99.5`, son beş düşük `[99.2, 99.4, 99.1, 99.3, 99.0]`, `atr_tf=2.0`, `stop_buffer_atr=0.3` ⇒ long aday; `planned_entry=101.5`, `planned_stop = 99.0 − 0.3·2.0 = 98.4`; `setup='T1'`, `planned_target IS NULL`. (Gövde oranı `1.5/3 = 0.5`; `signals.BODY_RATIO_MIN` bundan büyükse test verisi `c=101.9` ile kurulur. Stop uzaklığı `signals` sınırları dışındaysa aday yok beklenir; test iki durumu da `signals.evaluate_t1`'in kendi çıktısıyla karşılaştırır.)
- S5. `regime_candidate`, aynı girdide doğrudan `signals.evaluate_t1(side, …)` çağrısının döndürdüğü `entry`, `stop`, `stop_dist_atr` ile **bit düzeyinde** aynıdır (iki yön için).
- S6. `regime ∈ {trend_up, trend_down, range}` ya da `reasons ≠ "regime_blocked"` ⇒ koşul gölgesi yok. Son beş mumdan biri geçersiz OHLC ⇒ aday yok.
- S7. `tf_15m`: sentetik 15 dk + 4 s seride `tf15_candidates` sonucu, aynı pencereyle doğrudan `classify_series → align_to_base → compute_signals` çağrısının `(D − 1 sa, D]` aralığındaki `signal=True` satırlarıyla aynıdır; aralık dışındaki mumlar için satır yok. Isınma yetersizse ya da son mum eksikse boş liste.
- S8. `tf_15m` kilitli dönem bekleme: pencerenin ilk mumu `2026-10-31T23:45Z` ⇒ hesap yok, `tf15_holdout_wait` artar, `compute_signals` çağrılmaz; ilk mum `2026-11-01T00:00Z` ⇒ hesap yapılır. (Bu testte kilitli döneme düşen mum **verisi** üretilmez; yalnız pencere başlangıç zamanı denetlenir.)
- S9. Değişmez: K2 çıktısında ve S2–S7 senaryolarında hiçbir gölge satırın `(pair, side, setup, trigger_tf, bar_close_ts)` anahtarı `v_decisions`'ta yoktur.
- S10. `pos_open`: çiftte açık pozisyon varken üretilen satır `1`, yokken `0`. `gate_code`: kapı kapalıyken (ör. `kill`) kod yazılır ve satır **yine** üretilir.
- S11. Yalıtım: `record_shadow` her çağrıda istisna atacak biçimde sahtelenir ⇒ karar adımı normal tamamlanır, girişler/çıkışlar aynı, `records.shadow.errors` artar, `counters()` çıktısı hatasız koşuyla aynı, `entries_allowed().ok` aynı.
- S12. Sıra: `_shadow_step`, o karar adımının son broker çağrısından, son `state` yazımından ve `status.write`'tan **sonra** çağrılır (çağrı günlüğüyle doğrulanır). `_shadow_step` sırasında broker'a, `state` yazma yöntemlerine ve `orders`'a çağrı yoktur.
- S13. Bütçe: çift başına hesap 2 sn sürecek biçimde sahtelenir, 10 çift ⇒ en çok 3 çift işlenir, `budget_skips = 7`, karar adımı hatasız.
- S14. Geri test: `--record-shadow` olmadan `shadow_decisions` boş; bayrakla `tf_15m` satırı yok.
- S15. İkiz yapılandırması (`engine.twin.json`) yüklendiğinde `shadow_blocks` boştur.
- S16. `v_shadow_decisions` her satırda `final_action = 'shadow'` döndürür; `decision_events`'e `final_action='shadow'` yazma denemesi CHECK hatası verir.

**M — anlık değerli düşüş**
- M1. `drawdown_stats`, §6.3 örneği ⇒ `max_dd_mtm_abs=40`, `max_dd_mtm_pct=3.9216` (± 1e-4), `max_dd_mtm_low_abs=60`, `max_dd_mtm_low_pct=5.8824` (± 1e-4), `max_underwater_steps=2`.
- M2. Boş girdi ⇒ hepsi 0. Tekdüze artan eğri ve `low == equity` ⇒ hepsi 0. `low` yalnız ilk aralıkta `start`'ın altında ⇒ dip bazlı düşüş `start − low[0]`.
- M3. `max_consecutive_losses([5, -1, -2, 3, -1, -1, -1, 0, -4])` ⇒ `3` (0 kayıp değildir).
- M4. Açık pozisyonsuz hesap ⇒ her işarette `equity == wallet == equity_low`, `n_open = 0`.
- M5. Tek long, `entry=100`, `qty=2`, `wallet=1000`; iki dakika: `(mark_l=98, mark_c=99)`, `(mark_l=97, mark_c=101)`; ardından karar adımı ⇒ `equity = 1002`, `equity_low = 1000 + 2·(97−100) = 994`. Short için simetrik (`mark_h` kullanılır). `mark_*` yoksa `last_*`.
- M6. İki pozisyon (bir long, bir short): `equity_low`, iki pozisyonun **kendi** ters uçlarının toplamıdır (§6.1; aynı anda oluşmamış olsalar da).
- M7. Kağıt kipi: N karar adımı ⇒ `equity_marks`'ta N satır, `ts` karar adımı zamanları, `src='sim'`; `equity_low ≤ equity`. `mtm_marks=false` ⇒ satır yok.
- M8. Geri test çıktısı: `equity_mtm.csv` başlığı tam `ts,wallet,equity,equity_low,n_open`; `mtm.json.schema == "mtm/1"`; `max_dd_mtm_low_pct ≥ max_dd_mtm_pct`; `max_dd_realized_pct == summary.json.max_dd_pct`; `mtm.json` değerleri `equity_mtm.csv`'den `drawdown_stats` ile yeniden hesaplanınca aynı.
- M9. `metrics.max_drawdown` ve `compute_metrics`, sabit bir işlem tablosu için sürüm 3'teki çıktıyla **anahtar anahtar** aynıdır; `METRIC_KEYS` ve `TRADES_COLUMNS` demetleri değişmemiştir.
- M10. Yalıtım: `record_equity_mark` istisna atar ⇒ karar adımı normal tamamlanır, `records.mtm.errors` artar, `counters()` aynı.

**K — davranış eşdeğerliği** (§10)
- K1, K2, K4 otomatik testtir (K1/K2 `slow` işaretli; veri yoksa atlanır ve atlandığı raporlanır). K3 elle koşulur, sonucu (iki sha256, commit, süre) inceleme notuna yazılır.
- K5. `engine.counters()` anahtar kümesi, aynı senaryoda taban commit ile aynıdır (yeni anahtar yok).
- K6. `state.sqlite`: `PRAGMA user_version = 1`; tablo ve sütun listesi taban ile aynı; WP-3 `kv` tablosuna yeni anahtar yazmaz.

**T — tüketiciler**
- T1. Dondurulmuş derlem: iki sentetik defter kurulur; ikisi aynı kararlar ve işlemlerle, biri ayrıca 30 gölge satır, dolu ölçüm sütunları ve `equity_marks` içerir. `research/ml_build_candidates.read_ledger` iki defter için **aynı** iki tabloyu döndürür (`DataFrame.equals`). Ayrıca: dondurulmuş dosyaların git blob özetleri taban commit ile aynıdır (durağan test).
- T2. Sapma izleyicisi, pano veri katmanı ve Telegram günlük raporu T1'in iki defterinde aynı çıktıyı üretir.
- T3. Durağan test: `shadow_decisions`, `v_shadow_decisions`, `cf_shadow_outcomes` adları yalnız şu dosyalarda geçer: `trader_core/ledger.py`, `trader_core/counterfactual.py`, `trader_engine/engine.py`, `trader_engine/shadow.py`, `scripts/counterfactual_run.py`, `trader_reports/{inputs,gates}.py`. `trader_core/lesson.py`, `trader_core/drift_monitor.py`, `trader_core/health.py`, `trader_ml/*`, `scripts/build_corpus_v2*.py`, `research/ml_build_candidates.py` içinde **geçmez**.
- T4. Sağlık: `records` anahtarı içeren ve içermeyen `status.json` için aynı bulgular; `records` bozuk tipte (dizi) olsa da sağlık çökmeden çalışır.
- T5. Yedek: sürüm 4 defterin yedeği `ok`; `max_ids` yeni tabloları içerir; tetikleyici sayısı kaynakla eşleşir.
- T6. Karşı-olgu: T1'in iki defterinde `cf_outcomes` içeriği aynı; `outcomes()` ve `summary()` aynı. Gölge satırlı defterde `cf_shadow_outcomes` dolar; aynı fiyat yolunda aynı `(side, entry, stop, target)` için gölge sonucu ile atlanmış karar sonucu sayısal olarak eşittir. Ufku dolmamış gölge satır bekler; penceresi kilitli dönemle kesişen satır atlanır (`shadow_holdout_skipped`). Sürüm 3 defterde iş hatasız çalışır, gölge sayaçları 0.
- T7. Rapor paketi: sürüm 4 defter kabul edilir, sürüm 5 reddedilir. Gölge satır eklemek kapı karnesi 2.1 tablosunu, `n_engel_toplam`'ı ve `pay` değerlerini değiştirmez; 2.4 tablosunda ilgili satırın `n_engel`'i artar. `exit_regime` dolu defterde §8.5 geçiş tablosu üretilir, NULL'lar `bilinmiyor`.

**P — başarım**
- P1. `_shadow_step`, 10 çift, dört blok, 1500 × 1 sa + 5000 × 15 dk sentetik pencere: tek çağrı ≤ 5 sn (geliştirme makinesi); `tracemalloc` tepe artışı ≤ 30 MB.
- P2. `MtmRecorder.on_minute`: 10 açık pozisyonla 100 000 çağrı ≤ 2 sn; nesnenin bellekte tuttuğu satır sayısı karar adımı sayısıyla sınırlı.
- P3. Göç 3 → 4: 200 000 karar + 20 000 işlem içeren sürüm 3 dosyasında ≤ 5 sn (yedek hariç).
- P4. Motor içe aktarma ağırlığı testi (`test_engine_import_weight.py`) geçer.

## 13. Açık noktalar (mentor notu; uygulamayı engellemez)

1. **M2-piyasa çıkışı bugün veri alamıyor.** `kagit-degerlendirme-plani.md` §4.2'deki kural `slippage_exit` okur; piyasa çıkışlarında bu alan NULL'dır ve öyle kalır (§2.2). Doğru girdi yeni `slip_decision_exit`'tir. Planı bu alana bağlamak eşik belgesinde revizyon demektir; kağıt başlamadan önce mentor ayrı bir satırla karara bağlar. Bu paket yalnız alanı sağlar. Haftalık "gerçek kayma / model" karşılaştırma raporu da testnet verisi geldikten sonra ayrı iştir.
2. **Kötü senaryo tablosu** (−%10 / −%15 / −%20 basamaklarına düşme olasılığı) salt okunur rapor işidir (`trader_reports`); girdisi `equity_mtm.csv` ve `equity_marks`'tır. Bu pakette yalnız ölçü ve en uzun kayıp serisi vardır.
3. Koşul gölgesi yalnız T1'i sınar; `volatile` / `unclear` içinde R1 tanımsızdır. Raporda bu not satırın yanında basılır.
4. Gölge kanıtı üst sınırdır: sonraki kapıları (veto, risk, eşzamanlı pozisyon sınırı) ve dolumu yok sayar; `pos_open=1` satırlar gerçekte hiç alınamazdı. Rapor iki sayıyı ayrı gösterir.
5. Fiyat sorgusunun canlıda açılması (§3.5) testnet sonucuna bağlı ayrı mentor kararıdır.
