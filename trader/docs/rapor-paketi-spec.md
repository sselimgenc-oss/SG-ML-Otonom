# Rapor paketi: çıkış karnesi, kapı/veto karnesi, piyasa koşulu tabloları, "varsayım" etiketi, küçük hesap kontrolü (spesifikasyon v1.1, 17 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. İkiz kıyası ve veto raporları kaldırıldı; gerçek para ile ilgili ölçütler **[ASKIDA — kullanıcı yeniden belirleyecek]**.

İş paketi **WP-4** (`tasarim-kararlari.md` 17 Kasım "Repo denetimi onay listesi"). Onay listesi maddeleri: **4, 7 (yalnız karne), 16 (yalnız tablolar), 17, 19**. Denetim kimlikleri: B-01, B-02 (1. adım), C-01, A-10, B-03, A-09, B-27 · B-07, D-17, A-16 · A-14, D-05, B-18 · A-13 · A-19.

Bu belge kod, test ve commit içermez; testler bu belgeden yazılır (§12). Çelişkide `defter-spec.md`, `alinmayan-sinyal-spec.md`, `motor/06-backtester.md` geçerlidir.

**v1.1 (WP-3 ardılı, `defter-ek-alanlar-spec.md` §8):** (1) defter şema kontrolü `(2, 3, 4)` kabul eder (§2.1, G6); (2) §7.4 sabit satırları `v_shadow_decisions.block`'tan gelir, yeni satır `aynı mumda yeniden giriş`, ek sütun `n_pozisyon_acik`, `pay` bu tabloda `—`; karşı-olgu `cf_shadow_outcomes`'tan; (3) `exit_regime` sütunu sürüm 4'te vardır, §8.5 geçiş tablosu kendiliğinden üretilir (kod değişikliği yok); (4) kilitli dönem koruması gölge satır okumasına da uygulanır (§4). Rapor yine yalnız okur.

## 0. Bağlayıcı ilkeler

1. **Yalnız okur, yalnız rapor yazar.** Paket hiçbir motor/ders/ML davranışını, hiçbir eşiği, hiçbir defter satırını ve hiçbir backtest çıktısını değiştirmez. Yazdığı tek yer `--out` dizinidir (varsayılan `var/reports/`).
2. **Rapor kural değildir.** Hiçbir bayrak (`kazanani_engelliyor`, `bozulma`, `çıtayı geçti` …) otomatik bir değişikliği tetiklemez; otomatik kapı kapatma/gevşetme yoktur. Rapordan türeyen her kural değişikliği ayrı ön kayıt + kullanıcı onayı ister.
3. **Kilitli dönem `[2026-05-01, 2026-11-01)` hiçbir zaman okunmaz** (§4). Geçersiz kılma anahtarı yoktur.
4. **Stop çıkışlarının çıkış sonrası yolu, stopu genişletme kanıtı sayılmaz**; rapor bunu `stop` satırının yanında yazar.
5. **Geleceği kullanan her sütun** (çıkış sonrası yol, haftalık "trend ödedi" etiketi) yalnız değerlendirmedir; canlı girdi olamaz. Paket bu değerleri motorun/dersin okuyabileceği hiçbir yere yazmaz.
6. Her tabloda **n, gün kümesi sayısı (G), %90 aralık ve etiket** (`yetersiz` / `varsayım` / `çıtayı geçti`) görünür (§5).

## 1. Paket düzeni ve bağımlılık kuralları

```
trader/src/trader_reports/
  __init__.py
  inputs.py      # salt okunur okuyucular: defter, trades.csv, karşı-olgu deposu, mumlar, borsa kuralları, bütçe
  guard.py       # kilitli dönem koruması (tek geçit)
  stats.py       # kümelenmiş ortalama/aralık, Wilson, çokluk çıtası, yarı-uyumu, yıl satırları
  exits.py       # madde 4
  gates.py       # madde 7
  regimes.py     # madde 16
  sizing.py      # madde 19
  render.py      # markdown / JSON / CSV / tek satır özet
trader/scripts/report_run.py   # CLI (argparse, saat, dosya yazımı, isteğe bağlı Telegram)
```

`pyproject.toml` değişmez (`packages.find where=["src"]` yeni paketi kendiliğinden bulur; yeni bağımlılık yok).

**İzinli içe aktarmalar:** standart kütüphane, `numpy`; `pyarrow` (yalnız feather okuma, tembel içe aktarma); `trader_engine.holdout` (`HOLDOUT`, `check_holdout`, `BacktestArgError`); `trader_engine.exchange.rules` (`spec_from_json`, `to_symbol_rules`); `trader_core.risk` (`LOCKED_CFG`, `tightened`; `size_position` yalnız parite testinde); `trader_core.telegram` (`tr_sayi`, `tr_isaretli`, `tr_yuzde`, `TelegramNotifier`; yalnız `scripts/report_run.py` içinde).

**Yasak:** `trader_ml.*` (tümü; gerek yok); `trader_core.ledger.open_ledger`/`Ledger` (göç çalıştırabilir, sürüm 2 defteri reddeder); `trader_core.counterfactual.CounterfactualStore` (yoksa dosya oluşturabilir); `pandas` (gerek yok, bellek); paket içinde `datetime.now()`/`time.time()` (saat yalnız CLI'dan `now` olarak enjekte edilir); her türlü ağ çağrısı. `trader_engine`, `trader_core`, `trader_ml` içinden `trader_reports` içe aktarılamaz.

**SQLite açılışı (tek yardımcı, `inputs.open_ro`):** `sqlite3.connect("file:<mutlak yol>?mode=ro", uri=True, timeout=5.0, isolation_level=None)` + `PRAGMA busy_timeout=5000` + `PRAGMA query_only=ON`. Paket kaynağında `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `DROP`, `VACUUM`, `ATTACH` SQL sözcükleri bulunmaz. Dosya yoksa oluşturulmaz (`*_missing` hatası).

## 2. Girdiler (alan adları koddan doğrulandı)

### 2.1 Defter (`var/<bot>/ledger.sqlite`; backtest: `<koşu>/ledger.sqlite`)

`PRAGMA user_version` **2, 3 ya da 4** kabul edilir (eski backtest çıktıları 2, sürüm 3 defterler, güncel kod 4: `ledger.py SCHEMA_VERSION = 4`). 1 ya da >4 ⇒ `ledger_schema` hatası. Göç **çalıştırılmaz**. Sürüm 4'te `v_trades`/`v_closed_trades` sütun listesinin sonuna `entry_order_ts … exit_regime` (on beş sütun) eklenir; rapor yalnız adlandırdığı sütunları okur, `v_decisions` değişmez.

- `v_decisions` (yerine geçilmemiş kararlar): `id, bot, bar_close_ts, trigger_tf('1h'|'15m'), pair, side('long'|'short'), setup('T1'|'R1'), regime('trend_up'|'trend_down'|'range'|'volatile'|'unclear'), atr_ratio, features (JSON: atr_tf ya da atr_1h, atr_4h, stop_dist_atr, …), planned_entry, planned_stop, planned_target, param_version_id, veto_status('allowed'|'blocked'|'missing'|'stale'|'not_evaluated'), veto_reason, risk_allowed, risk_reason, size_qty, size_notional, size_margin, size_risk_amount, leverage, final_action('entered'|'skipped'), skip_reason, recorded_at`; sürüm 3'te ayrıca `ml_score`.
  - `skip_reason` kümesi: `stop_width, rr_below_min, veto_blocked, veto_missing, veto_stale, risk_denied, entry_gate_closed, order_failed, other` (+ sürüm 3: `ml_filter`).
  - Çiftten bağımsız kapılar `veto_reason = "gate:<kod>"` olarak yazılır (`gates.py`): `params_unavailable, trigger_tf_changed, degraded, kill, paused…, stale_data, rules_missing, day_start_missing` ve defter sağlık kodları.
  - `risk_reason` Türkçe serbest metindir (`risk.py _check_entry`); sınıflandırma §7.1.
- `v_closed_trades`: `trade_id, decision_id, pair, side, setup, regime (girişteki), atr_ratio, param_version_id, entry_ts, entry_price, planned_entry, planned_stop, planned_target, qty, leverage, planned_risk, fee_entry, slippage_entry, exit_ts, exit_price, exit_reason('stop'|'target'|'trail_stop'|'regime_flip'|'time_stop'|'manual'|'force_exit'|'liquidation'|'other'), planned_exit, fee_exit, funding_paid, gross_pnl, realized_pnl, r_multiple, slippage_exit, mfe_r, mae_r, bars_held, excursion_tf`.
  - `r_multiple = realized_pnl / planned_risk` (net: komisyon + fonlama dahil). `mfe_r = max(0, yön·(en iyi fiyat − entry_price)·qty / planned_risk)`, `mae_r` simetrik; ikisi de ≥ 0 ya da ikisi de NULL.
  - **`exit_regime`** sürüm 4'te vardır (`trade_exits.exit_regime`, `v_closed_trades.exit_regime`; çıkış dolumundan önceki son karar adımındaki hizalanmış 4s koşul etiketi, bilinmiyorsa NULL); sürüm 2/3'te yoktur. Varlığı `PRAGMA table_info(trade_exits)` / görünüm sütunuyla sorulur (§8.5).
- `v_shadow_decisions` (**sürüm 4**; `defter-ek-alanlar-spec.md` §2.4; aday bastıran blokların gölge satırları): `id, bot, block('regime_volatile'|'regime_unclear'|'r1_disabled'|'same_bar_reentry'|'tf_15m'), bar_close_ts, trigger_tf, pair, side, setup, regime, atr_ratio, rh, rl, features, planned_entry, planned_stop, planned_target, param_version_id, strategy, reasons, pos_open, gate_code, recorded_at, final_action('shadow')`. Satırlar `v_decisions`'a **girmez** ve karar paydasına (`n_total`) sayılmaz. Görünüm yoksa (sürüm < 4) §7.4 eski davranışı korur.
- `counterfactual.sqlite` içinde `cf_shadow_outcomes` (gece işi, `defter-ek-alanlar-spec.md` §7): `cf_outcomes` ile aynı sütunlar, `decision_id` yerine `shadow_id`, `skip_reason` yerine `block`; tablo yoksa karşı-olgu sütunları boş (`bekleyen`).
- Zaman damgaları metin `YYYY-MM-DDTHH:MM:SS.mmmZ` (UTC); sözlük sırası = zaman sırası.

### 2.2 Backtest çıktısı (`var/backtests/<id>/`)

`trades.csv` sütunları (`metrics.py TRADES_COLUMNS`): `trade_id, pair, side, setup, regime, entry_ts, exit_ts, entry_price, exit_price, qty, leverage, planned_entry, planned_stop, planned_target, exit_reason, planned_exit, planned_risk, equity_at_entry, gross_pnl, fee_entry, fee_exit, funding_paid, realized_pnl, r_multiple, mfe_r, mae_r, bars_held, excursion_tf, slippage_entry, slippage_exit, slip_cost, decision_id, param_version_id`. Aynı dizinde `ledger.sqlite` (kararlar; `features`, `atr_ratio`, atlananlar buradan), `meta.json` (`period: [başlangıç, bitiş]`, `pairs`, `trigger_tf`, `rules_source`, `fill_model`), `summary.json`. Backtest kipinde işlemler `trades.csv`'den, kararlar `ledger.sqlite`'tan okunur; `equity_at_entry` yalnız `trades.csv`'de vardır.

### 2.3 Karşı-olgu deposu (`var/<bot>/counterfactual.sqlite`, tablo `cf_outcomes`)

`bot, decision_id, method('barrier'|'plan'), pair, side, setup, trigger_tf, skip_reason, decision_ts, planned_entry, planned_stop, planned_target, window_start_ts, window_end_ts, hyp_outcome(0|1|NULL), hyp_r_gross, hyp_r_net, cost_r, exit_reason('target'|'stop'|'time'|'data_gap'|'invalid_plan'), bars_held, computed_at, version`. `barrier`: 2R hedef / ilk stop / 72 adet 1h mum; `plan`: planlanan hedef, 48 mum, yalnız `version >= 2`. Yalnız `window_end_ts <= now` satırları okunur. Depo yoksa ilgili sütunlar `—`, rapor hata vermez (`cf_missing` uyarısı). Backtest koşularında depo yoktur; kapı karnesi o kipte yalnız sayım üretir.

### 2.4 Mumlar

- **Sunucu:** `var/market.sqlite` (`user_version = 1`), tablo `bars(kind, pair, tf, open_ms, o, h, l, c, v, written_ms)`. Yalnız `kind='last'`, `tf IN ('15m','1h')`, ve yalnız kapanıştan sonra yazılmış mumlar: `written_ms >= open_ms + tf_ms`. `1m` ve `mark` okunmaz.
- **Yerel/backtest:** `--history DİZİN`, dosya `<PAIR>_USDT_USDT-<tf>-futures.feather` (ör. `BTC_USDT_USDT-1h-futures.feather`), sütunlar `date, open, high, low, close, volume`; `memory_map=True`. `1m` dosyaları açılmaz.
- Tek arayüz: `BarReader.window(pair, tf, start_ms, n) -> [(open_ms, h, l, c)]`. Dönen dizinin `open_ms` değerleri tam olarak `start_ms + k·tf_ms, k = 0..n−1` değilse pencere **eksik** sayılır (`data_gap`); kısmi pencere kullanılmaz.

### 2.5 Borsa kuralları (madde 19)

Öncelik sırası: `market.sqlite` tablo `rules(pair, json, fetched_ms)` → `<history>/rules.json` → `--synthetic-rules` (açıkça verilirse; raporda **"SENTETİK kural"** etiketi). JSON `spec_from_json` + `to_symbol_rules` ile `SymbolRules(tick, step, min_qty, max_qty, min_notional)`'a çevrilir. Sentetik kural tablosu paket içinde sabittir: `min_notional` BTC/USDT 100, ETH/USDT 20, diğerleri 5; `step`/`min_qty` CLI'dan `--synthetic-step PAIR=DEĞER` ile verilir (mum okumadan; verilmeyen çift raporda `kural yok`).

### 2.6 Bütçe (veto maliyeti, madde 7)

`user_data/budget.sqlite`, tablo `reservations(service, day, month, state, charged_micro, …)`. Veto maliyeti = `SUM(charged_micro)/1e6` USD, `service='veto' AND state='settled' AND day ∈ dönem`. Dosya yoksa maliyet `—`.

### 2.7 Yapılandırma

`config/engine.base.json`: `pairs`, `wallet_start`, `target_trade_risk` (kağıt 0,005). Risk sabitleri `trader_core.risk.LOCKED_CFG` (`fee_rate = slippage_rate = 0,0005`, `max_notional_ratio = 1,0`, `min_leverage = 3`, `max_trade_risk = 0,02`); paket kendi kopyasını tanımlamaz.

## 3. Ortak tanımlar

- `yön` = +1 (long), −1 (short). `r_px = planned_risk / qty` (1R'ye karşılık gelen fiyat mesafesi; `mfe_r`/`mae_r` ile aynı birim). Karar satırlarında (işlem yok) `r_px = |planned_entry − planned_stop|`.
- `gross_r = gross_pnl / planned_risk`; `net_r = r_multiple`.
- `ceil_saat(ts)` = `ts`'den küçük olmayan ilk tam saat (ms). `ts` tam saatteyse kendisi.
- Dönem: `--since`/`--until` (varsayılan: tüm kayıt, `until = now`). İşlemler `exit_ts`'ye, kararlar `bar_close_ts`'ye göre döneme girer.
- Gün kümesi anahtarı: işlemde `entry_ts`'nin UTC tarihi, kararda `bar_close_ts`'nin UTC tarihi.
- Hafta: ISO haftası (Pazartesi 00:00 UTC başlar), anahtar `YYYY-Www`.

## 4. Kilitli dönem koruması (`guard.py`)

`H0, H1 = trader_engine.holdout.HOLDOUT`. Sabitler pakette yeniden yazılmaz.

1. **Koşu düzeyi:** backtest kipinde `meta.json period` için `check_holdout(start, end)` çağrılır; `BacktestArgError("holdout_locked")` ⇒ koşu **okunmaz**; çıktı yalnız `{"status": "holdout_locked"}` içeren `rapor.json` + tek satırlık `rapor.md`, çıkış kodu 3.
2. **Satır düzeyi (SQL'de, satır belleğe alınmadan):** `PAD = 72 saat` (en uzun ileri pencere). İşlem sorguları `NOT (entry_ts < :H1 AND exit_ts >= :H0_eksi_PAD)` koşulunu, karar ve `cf_outcomes` sorguları `NOT (ts < :H1 AND ts >= :H0_eksi_PAD)` koşulunu taşır. Atlanan satır sayısı ayrı `COUNT(*)` sorgusuyla (yalnız sayı) `holdout_skipped` olarak raporlanır. **Tanım:** `holdout_skipped` = atlanan kapanmış işlem sayısı + atlanan `final_action='skipped'` karar sayısı. Girilmiş kararlar kendi işlemiyle birlikte sayılır (aynı olay), karşı-olgu satırları atlanan kararla aynı olaydır (ayrı kırılımda `holdout_skipped_cf`); kilitli bölgedeki girilmiş ama henüz kapanmamış kararlar hiçbir yerde sayılmaz. Kilitli bir işlemin giriş kararı da okunmaz. `meta.json period` eksik, 2 elemanlı olmayan ya da ayrıştırılamıyorsa koşu `meta_period` hatasıyla (kod 2) reddedilir; `--compare-backtest` koşusu aynı denetimden geçer, kesişirse karşılaştırma uyarıyla atlanır ve o koşu okunmaz. `trades.csv` satırları aynı koşulla, satır ayrıştırılırken ilk iş olarak elenir.
3. **Mum düzeyi (tek geçit):** her `BarReader.window` çağrısı I/O'dan **önce** `check_holdout(start, end)` çağırır; kesişme ⇒ okuma yapılmaz, çağıran satır `holdout_skipped` olur. Feather okuyucuda yalnız `date` sütunu konum bulmak için taranabilir; kilitli döneme ait `open/high/low/close/volume` değerleri hiçbir zaman dilimlenmez, numpy dizisine çevrilmez (mevcut `HistoricalSource._synthetic_rules` ile aynı sözleşme).
4. Yıl satırlarında (§5.5) 2026 yılı `kısmi (kilitli dönem hariç)` notuyla basılır.
5. Rapor başlığında her zaman şu satır bulunur: `Kilitli dönem 2026-05-01..2026-11-01 okunmadı; atlanan satır: <holdout_skipped>.`

## 5. İstatistik kuralları (`stats.py`) ve raporda gösterilen uyarılar

### 5.1 Ortalama ve %90 aralık (gün-kümelenmiş, CR1; `lesson.cluster_mean` ile aynı formül)

`x_i` değerleri, `g(i)` gün anahtarı, `n` adet, `G` ayrı gün: `m = Σx_i/n`; `u_g = Σ_{i∈g}(x_i − m)/n`; `SE = sqrt(G/(G−1) · Σ_g u_g²)`; aralık `m ± 1,645·SE`. `G < 8` ya da `SE < 1e-12` ⇒ aralık tanımsız (`—`).

### 5.2 Oranlar

Wilson %90 (`z = 1,645`): `merkez = (p + z²/2n)/(1 + z²/n)`, `yarı = z·sqrt(p(1−p)/n + z²/4n²)/(1 + z²/n)`. `n = 0` ⇒ `—`. Her oran tablosunun altında sabit not: *"Aralık işlemleri bağımsız sayar; aynı gün açılan işlemler birlikte hareket ettiği için gerçek belirsizlik daha geniştir (varsayım)."*

### 5.3 `yetersiz` etiketi

`n < 30` **ya da** `G < 8` ⇒ satır etiketi `yetersiz`; ortalama yine basılır, aralık `—`, satır hiçbir bayrak alamaz. **İstisna:** §9 `bozulma` bayrağı `yetersiz` etiketiyle bastırılmaz (test S4); satır `bayrak_not = "(yetersiz)"` taşır.

### 5.4 Alt grup çıtası (madde 17, A-13)

Bir **alt grup tablosu** = aynı örneklemi K hücreye bölen her döküm (çift, yön, kurulum, giriş koşulu, koşul × oynaklık, çıkış nedeni, UTC saat dilimi `00–08 / 08–16 / 16–24`, haftanın günü, kapı satırları …). `K_tablo` = o tabloda `n ≥ 1` hücre sayısı; `K_rapor` = aynı koşudaki **tüm** alt grup tablolarının hücre toplamı. Bağlayıcı olan `K_rapor`'dur.

Hücre için:
- Fark istatistiği (`lesson.cluster_diff` formülü; A = tablonun geri kalanı, B = hücre): `d = m_B − m_A`; `u_g = Σ_{i∈B,g}(x_i − m_B)/n_B − Σ_{i∈A,g}(x_i − m_A)/n_A`; `SE = sqrt(G/(G−1)·Σ u_g²)`; `z = d/SE`.
- Çıta: `z_K = Φ⁻¹(1 − 0,05/(2·K_rapor))` (iki yönlü Bonferroni). Örnek: K=1 → 1,960; K=10 → 2,807; K=20 → 3,023; K=50 → 3,291.
- Yarı uyumu: tablonun tüm örneklemi zaman sırasına dizilir, medyan zaman damgasından ikiye bölünür (eşitlikte ilk yarı). Her yarıda hücrede `n ≥ 10` ve `işaret(d_1) = işaret(d_2) ≠ 0` olmalı.
- Etiket: `yetersiz` (§5.3) → değilse `|z| ≥ z_K` **ve** yarı uyumu varsa `çıtayı geçti` → aksi halde **`varsayım`**.
- Tek hücreli tablo ya da geri kalanı boş hücre: etiket `varsayım`, `z = —`.

Her alt grup tablosunun başlığında: `K_tablo`, `K_rapor`, `z_K`. Altında sabit not: *"`varsayım` = tesadüften ayırt edilemedi. `çıtayı geçti` de kural değildir; değişiklik ön kayıt ve onay ister."*

### 5.5 Yıl satırları

Tüm örneklem ve her `kurulum × yön` için takvim yılına (`entry_ts` UTC yılı) göre: `n`, ortalama net R, toplam R, etiket. `pozitif_yil_orani` = ortalaması > 0 olan yıl sayısı / `yetersiz` olmayan yıl sayısı (payda 0 ⇒ `—`). Tek yıllık veri ⇒ not: *"Tek yıl: 'her koşulda çalışır' denemez."*

### 5.6 Sabit uyarılar (her raporda, başlığın altında)

Sıra ve metin sabittir; ilgili bölüm yoksa satır da yoktur:
1. Kilitli dönem satırı (§4.5).
2. *"Bu rapor ayar değiştirmez; geçmişe bakarak 'keşke' okuması içerir."*
3. *"Alınmayan sinyallerin sonucu (karşı-olgu) üst sınırdır: emir gerçekleşmesi, sonraki kapılar ve gerçek çıkış kuralı hesaba katılmaz (varsayım)."*
4. *"Çıkış sonrası yol ve 'trend ödedi' etiketi geleceği kullanır; yalnız değerlendirmedir."*
5. Kaynak satırı: kip (`paper|testnet|backtest:<id>`), dönem, `now`, defter sürümü, kural kaynağı, mum kaynağı ve çözünürlüğü.

## 6. Madde 4 — Çıkış karnesi (`exits.py`)

Evren: dönemdeki kapanmış işlemler. `mfe_r IS NULL` işlemler 6.2–6.5'e girmez, `n_gezinti_yok` olarak sayılır.

### 6.1 Çıkış sonrası yol (B-01)

Her işlem ve `h ∈ {24, 72}` için pencere: `tf='1h'`, `start = ceil_saat(exit_ts)`, `n = h`. Durum: `now < start + h saat` ⇒ `pending`; kilit ⇒ `holdout_skipped`; eksik mum ⇒ `data_gap`; aksi `ok`. Yalnız `ok` satırlar:

| Sütun | Tanım |
|---|---|
| `post_fav_r_h` | long: `max(0, max(h_k) − exit_price)/r_px`; short: `max(0, exit_price − min(l_k))/r_px` |
| `post_adv_r_h` | long: `max(0, exit_price − min(l_k))/r_px`; short: `max(0, max(h_k) − exit_price)/r_px` |
| `post_close_r_h` | `yön·(c_son − exit_price)/r_px` |
| `ilk_dokunus_h` | `lehte`: lehte 1R'ye (`exit_price + yön·r_px`) dokunan ilk mum, aleyhte 1R'ye dokunan ilk mumdan **kesin önce**; aynı mum ya da sonra ⇒ `aleyhte`; ikisi de yok ⇒ `yok` |
| `erken_cikis_h` | `ilk_dokunus_h == 'lehte'` (0/1) |

`exit_reason` başına tablo (alt grup tablosu, §5.4 uygulanır; ölçüt `post_close_r_72`): `n`, `n_ok`, `erken_cikis_24` ve `erken_cikis_72` oranı (Wilson), ortalama `post_close_r_72` (§5.1), ortalama `post_fav_r_72` (not: *"tepe önceden bilinemez; üst sınır"*), `pending`/`data_gap`/`holdout_skipped` sayıları. `stop` satırının yanında: *"stopu genişletme kanıtı sayılmaz"*.

### 6.2 Geri verme (B-02 1. adım)

`θ ∈ {0,5; 1,0}` için: `n_ulasan = #(mfe_r ≥ θ)`, `n_geri = #(mfe_r ≥ θ ve net_r < 0)`, `oran = n_geri/n_ulasan` (Wilson), `toplam_r_geri = Σ net_r` (o işlemler). İşlem başına `geri_verme_r = mfe_r − gross_r`. Ayrık bantlar `mfe_r ∈ [0,5;1) / [1;2) / [2;∞)`: `n`, zararla kapanan oranı, ortalama `geri_verme_r`. `exit_reason` başına ortalama `geri_verme_r`.

### 6.3 Çıkış verimi (C-01)

`verim = (gross_r + mae_r)/(mfe_r + mae_r)`; payda `< 0,05` ⇒ NULL (`n_tanimsiz`); `[0, 1]` dışı değer kırpılır (`n_kirpilan`). Ortalama: kurulum başına, `exit_reason` başına, ve `exit_ts` ISO haftası başına (haftalık seri; `n < 5` hafta `—`).

### 6.4 Kazananların ters gezintisi (A-10)

Kazanan = `net_r > 0`. `mae_r` için %50/75/85/95 yüzdelikleri (doğrusal ara değer; `numpy.percentile` varsayılanı), `mae_r ≥ 0,9` olan kazanan payı. ATR birimi: `mae_atr = mae_r · r_px / atr`, `atr = features.atr_tf` (yoksa `features.atr_1h`; ikisi de yoksa `—`). Kurulum × yön başına. Okuma cümlesi (yalnız `n ≥ 30`): `p85 ≤ 0,6` ⇒ *"stop gerekenden geniş olabilir (varsayım)"*; `mae_r ≥ 0,9` payı `≥ 0,20` ⇒ *"stop dar olabilir (varsayım)"*; aksi cümle yok. Sabit not: *"Stop olan işlemler tanım gereği kazanan değildir; bu dağılım 1R'de kesiktir (hayatta kalan yanlılığı)."*

### 6.5 +1R'den önceki ters gezinti (B-03)

Alınan işlemler: `tf='15m'` mumları, `[taban15(entry_ts), exit_ts]` (yuvarlama aşağı; mum sayısı > 3000 ise `tf='1h'`). `k*` = lehte ucu `entry_price + yön·r_px`'e ulaşan ilk mum (yoksa pencere sonu). `mae_on1r_r` = `k*`'dan **kesin önceki** mumlarda en büyük aleyhte gezinti / `r_px` (hiç mum yoksa 0). `kullanim = mae_on1r_r · r_px / |entry_price − planned_stop|` (stop mesafesinin kullanılan payı). Gruplar: `1R'ye ulaştı` / `ulaşmadı`. Her grup için `kullanim` %50/75/85/95, ve ATR biriminde aynı yüzdelikler. Alınmayan adaylar (karşı-olgu `barrier`, `exit_reason ∈ {target, stop, time}`): aynı hesap `planned_entry`, `|planned_entry − planned_stop|`, `tf='1h'`, pencere `window_start_ts`'den 72 mum; ayrı satır grubu `aday (alınmadı)`. Not: *"Stop mesafesi değişirse pozisyon boyutu ve RR kapısı da değişir; bu tablo tek başına stop ayarı kanıtı değildir."*

### 6.6 Bariyer yarışı merdiveni (A-09)

Evren: dönemdeki **tüm** kararlar (alınan + atlanan; `stop_width`/`rr_below_min`/`ml_filter` dahil). `e = entry_price` (alınan) ya da `planned_entry`; `s = planned_stop`; `tf='1h'`, `start = ceil_saat(bar_close_ts)`, 72 mum. `k ∈ {0,5; 1; 1,5; 2; 3}` için hedef `e + yön·k·|e − s|`; aynı mumda stop ve hedef ⇒ **stop önce**; 72 mumda ikisi de yoksa `zaman_asimi` (ulaşmadı sayılır, ayrıca sayılır). Kurulum × yön başına: `n`, `P_k` (0/1 göstergesinin §5.1 ortalaması ve aralığı), başabaş `1/(1+k)` ve maliyetli başabaş `(1 + c)/(1 + k)`, `c` = `2·(0,0005+0,0005)·e/|e − s|` örneklem ortalaması. Not: *"1 saatlik mumla; mum içi sıra bilinmez (stop önce varsayımı)."* Plasebo satırı A-02 (madde 10) gelince eklenir; şimdi yok.

### 6.7 İşlem başına tek satır neden (B-27)

Kural tabanlı, LLM yok. Şablon (`mfe_r` varsa): `"{pair} {yön_tr}: en çok +{mfe_r}R gördü, {neden_tr} ile {net_r}R kapandı; tepeden {geri_verme_r}R geri verdi."`; yoksa `"{pair} {yön_tr}: {neden_tr} ile {net_r}R kapandı."` Sayılar `tr_isaretli(x, 1)` / `tr_sayi(x, 1)`. `yön_tr`: `alış`/`satış`. `neden_tr`: `stop`→`ilk stop`, `trail_stop`→`iz süren stop`, `target`→`hedef`, `regime_flip`→`piyasa koşulu değişimi`, `time_stop`→`süre sınırı`, `manual`→`elle kapatma`, `force_exit`→`zorunlu kapatma`, `liquidation`→`likidasyon`, `other`→`diğer`. Örnek: `mfe_r=1,8; net_r=0,9; gross_r=0,95` ⇒ `"BTC/USDT alış: en çok +1,8R gördü, iz süren stop ile +0,9R kapandı; tepeden 0,9R geri verdi."`

## 7. Madde 7 — Kapı ve veto karnesi (`gates.py`)

### 7.1 Satır anahtarı (`kapi`)

Dönemdeki `v_decisions` satırları `final_action='skipped'`:
- `stop_width`, `rr_below_min`, `ml_filter`, `order_failed`: `skip_reason` kendisi.
- `veto_blocked` → **`veto:claude`**; `veto_missing`, `veto_stale` → `veto:yok`, `veto:bayat` (erişilebilirlik; Claude'un kararı değil).
- `entry_gate_closed`, `other`: `veto_reason` `gate:` ile başlıyorsa `gate:<kod>`, değilse `skip_reason`.
- `risk_denied`: `risk:<sınıf>`, `risk_reason` ön ekine göre: `aynı yön` → `ayni_yon`; `günlük zarar bütçesi` → `gunluk_butce`; `günlük sınır aşıldı` → `gunluk_sinir`; `toplam açık risk` → `acik_risk`; `toplam teminat` → `teminat_toplam`; `likidasyon çok yakın` → `likidasyon`; `boyutlandırma reddedildi` → `boyut` (metinde `en küçük emir` geçiyorsa `boyut_min_emir`); içinde `zaten açık pozisyon` → `cift_acik`; diğer her şey → `diger`.

Beklenen kapı listesi (hiç satırı olmasa da basılır): yukarıdaki tüm `skip_reason` değerleri, `veto:claude`, `veto:yok`, `veto:bayat`, tüm `risk:` sınıfları, `gate:kill`, `gate:stale_data`, `gate:rules_missing`, `gate:day_start_missing`, `gate:params_unavailable`, `gate:trigger_tf_changed`.

### 7.2 Sütunlar

| Sütun | Tanım |
|---|---|
| `n_engel` | dönemde bu kapının atladığı karar sayısı |
| `pay` | `n_engel / (tüm kararlar)` |
| `n_cf` | `cf_outcomes method='barrier'`, `hyp_r_net IS NOT NULL` eşleşen (`bot, decision_id`) satır sayısı |
| `ort_r_cf`, `%90` | `hyp_r_net` ortalaması ve aralığı (§5.1; gün = `decision_ts`) |
| `hedef_once` | `hyp_outcome = 1` oranı (Wilson) |
| `ort_r_plan` | `method='plan' AND version>=2` ortalaması (bilgi) |
| `bekleyen` | `n_engel − (bu kararlar için herhangi bir barrier satırı olanlar)` |
| `veri_yok` | `exit_reason IN ('data_gap','invalid_plan')` sayısı |
| `yargi` | `yetersiz` (§5.3, `n_cf` üzerinden) · `kanit_yok` (`n_engel = 0` ya da `n_cf = 0`) · `uyumlu` (aralık üst ucu < 0) · `celiskili` (aralık alt ucu > 0) · `belirsiz` (aralık 0'ı içerir). `n ≥ 30`, `G ≥ 8` iken `SE < 1e-12` (ör. sabit değerli seri) ise aralık `[m, m]` dejenere sayılır ve yalnız `yargi` için kullanılır (`m > 0` ⇒ `celiskili`, `m < 0` ⇒ `uyumlu`); gösterilen aralık `—` kalır. |
| `bayrak` | `kazanani_engelliyor` (`yargi = celiskili`) · `hic_devreye_girmedi` (`n_engel = 0`, dönem ≥ 28 gün) · boş |

Karşılaştırma satırı `alınanlar`: `n`, ortalama `r_multiple`, aralık (not: *"gerçek çıkışla; karşı-olgu satırlarıyla birebir kıyaslanamaz"*). Kapı tablosu alt grup tablosudur (§5.4; ölçüt `hyp_r_net`); `kazanani_engelliyor` bayrağı etiketi `varsayım` olan satırda *"(varsayım)"* ekiyle basılır. **Otomatik devre dışı bırakma yoktur.**

### 7.3 Claude veto satırı (B-07, D-17)

`veto:claude` için ek sütunlar: `maliyet_usd` (§2.6), `engel_basina_usd = maliyet_usd / n_engel`, `kacinilan_r = −Σ hyp_r_net`, `kacinilan_usd = kacinilan_r · risk_usd` (`risk_usd = --risk-usd`, varsayılan `target_trade_risk · wallet_start`; etiket `varsayım`), `net_usd = kacinilan_usd − maliyet_usd`. Tahminci çizelgesi: `P(kazanç | izin)` = alınanlarda `r_multiple > 0` oranı; `P(kazanç | engel)` = `hedef_once`; `ayirma = P(kazanç|izin) − P(kazanç|engel)` (not: *"iki taraf farklı çıkış tanımı kullanır (varsayım)"*). Backtest kipinde (`veto_reason = 'not_evaluated:backtest'`) bu bölüm *"veto bu koşuda değerlendirilmedi"* satırıdır.

### 7.4 Aday üretmeyen yasaklar (A-11) ve ölü ayar denetimi (A-16)

- Sabit satırlar (**v1.1**): `koşul:volatile`, `koşul:unclear`, `R1 kapalı (v1b)`, `15m kapalı`, `aynı mumda yeniden giriş`. Kaynak `v_decisions` üzerindeki yüklemler **değil**, `v_shadow_decisions.block` sütunudur: `koşul:volatile` ← `regime_volatile`; `koşul:unclear` ← `regime_unclear`; `R1 kapalı (v1b)` ← `r1_disabled`; `15m kapalı` ← `tf_15m`; `aynı mumda yeniden giriş` ← `same_bar_reentry`. `n_engel` = blok satır sayısı; ek sütun `n_pozisyon_acik` = `pos_open = 1` satır sayısı (gerçekte hiç alınamayacak satırlar; iki sayı ayrı gösterilir); `pay` sütunu bu tabloda `—` (gölge satırlar karar paydasına girmez). Karşı-olgu sütunları (`n_cf`, `ort_r_cf`, `hedef_once`, `yargi`, `bayrak`) `cf_shadow_outcomes`'tan (yöntem `barrier`; `tf_15m` 1 saatlik ızgarada, yaklaşık) §5 kurallarıyla hesaplanır. Satır notları: koşul satırlarında *"yalnız T1 (bu koşulda R1 tanımsız)"*, `15m kapalı` satırında *"1 saatlik ızgarada oynatılır (yaklaşık)"*; tablo altında *"gölge satırlar karar paydasına girmez; n_pozisyon_acik gerçekte hiç alınamayacak satırları ayrı gösterir"*. **`v_shadow_decisions` yoksa** (sürüm < 4) bugünkü davranış korunur: satır `yargi = kanit_yok`, not *"gölge karar satırı WP-3'te"* (yeni satır dahil, `n_engel = 0`). Kapı karnesinin 2.1 tablosu, `n_engel_toplam` ve `pay` paydası gölge satırlardan **etkilenmez**. Kilitli dönem koruması (§4) gölge satır okumasına (`bar_close_ts`) ve `cf_shadow_outcomes` (`decision_ts`) okumasına aynen uygulanır.
- `--compare-backtest KOŞU_DİZİNİ` verilirse: backtest `trades.csv`'de görülüp canlı/kağıt defterde hiç görülmeyen `exit_reason` değerleri ve backtest'te `n_engel > 0` olup canlıda `n_engel = 0` olan kapılar listelenir (kağıt dönemi ≥ 28 gün ise; değilse *"erken"*). A-16 (1) (ders ayarlarının motor çıktısını değiştirdiğini sınayan test) bu paketin kapsamı dışındadır.

## 8. Madde 16 — Piyasa koşuluna göre tablolar (`regimes.py`)

Hepsi alt grup tablosudur (§5.4), ölçüt `net_r`, evren kapanmış işlemler.

1. **Giriş koşulu × yön × kurulum:** `n`, `G`, ortalama R, %90, kazanç oranı, toplam R, etiket.
2. **Giriş koşulu × oynaklık (A-14):** oynaklık durumu `atr_ratio`'dan, **sabit** sınırlarla: `düşük < 0,80 ≤ orta < 1,00 ≤ yüksek` (`atr_ratio` NULL ⇒ `bilinmiyor`). Sınırlar 1h_IS geri testindeki aday dağılımının yaklaşık üçte birlik noktalarıdır (0,80 / 1,00), bu belgede sabitlenmiştir, veriyle yeniden hesaplanmaz. Ek sütun `tutuyor`: etiket `çıtayı geçti` **ve** hücrenin kendi %90 aralığı 0'ı içermiyorsa `evet`, aksi `hayır`. Not: *"İncelenen botlarda hiçbir koşul hücresi kalıcı çıkmadı; hücre 'tutuyor' demeden koşula bağlı kural yazılmaz."*
3. **Giriş koşulu × çıkış nedeni (D-05):** `n`, toplam R, `pay = |toplam R| / Σ|toplam R|` (tablo geneli).
4. **Haftalık "trend ödedi" etiketi (B-18):** havuz = o ISO haftasında `bar_close_ts`'si olan alınan işlemlerin `r_multiple`'ı ∪ atlanan kararların `barrier` `hyp_r_net`'i (depo yoksa yalnız alınanlar; `etiket_kaynagi = alinan|aday`). Hafta etiketi: `n < 5` ⇒ `yetersiz`; ortalama > 0 ⇒ `trend_odedi`; aksi `trend_odemedi`. Haftalık liste (hafta, n, ortalama, etiket) basılır. Etikete göre sonuç tablosunda döngüselliği azaltmak için her işlem **kendi çifti hariç** hesaplanan hafta etiketini alır. Not: *"Etiket geleceği ve iki farklı getiri tanımını kullanır; yalnız değerlendirme (varsayım)."*
5. **Çıkıştaki koşul:** `trade_exits.exit_regime` sütunu yoksa (sürüm < 4) bölüm tek satırdır: *"`exit_regime` alanı defterde yok (WP-3 ekleyecek); tablo üretilmedi."* Varsa (sürüm 4; kod değişmeden): giriş koşulu × çıkış koşulu geçiş tablosu (`n`, ortalama R, etiket); NULL değerler `bilinmiyor`.

Ardından standart dökümler (madde 17'nin uygulama alanı): çift, yön, kurulum, UTC saat dilimi, haftanın günü; ve §5.5 yıl satırları.

## 9. Madde 19 — Küçük hesapta boyut bozulması (`sizing.py`)

Evren: dönemdeki kararlardan `planned_entry`, `planned_stop` geçerli (`> 0`, yön tarafı doğru) olanlar; `ana` evren `final_action='entered'` ∪ `skip_reason='risk_denied'`, `geniş` evren tüm kararlar (ayrı tablo). Cüzdanlar `--wallets` (varsayılan `250,300,1000`), risk `--risk` (varsayılan: yapılandırmadaki `target_trade_risk`; backtest kipinde ayrıca `0.014`). `kaldıraç` = kararın `leverage` değeri, yoksa `LOCKED_CFG.min_leverage`.

Her (karar, W, τ) için (`risk.size_position` ile aynı aritmetik; `c = fee_rate + slippage_rate`):

```
birim     = |e − s| + e·c + s·c
qty_risk  = τ·W / birim
qty_tavan = max_notional_ratio·W / e
qty_ham   = min(qty_risk, qty_tavan)
qty       = adım'a aşağı yuvarla(qty_ham)            # Decimal(repr(.)) ile, risk._floor_to_step gibi
sonuç     = 'red_min_emir'   eğer qty ≤ 0 ya da qty·e < min_notional
            'red_teminat'    eğer qty·e/kaldıraç > W
            'red_min_adet'   eğer qty < min_qty      # motorun boyut adımı bunu denetlemez; emir yolunda reddedilir (ayrı sayılır)
            'kabul'          aksi
risk      = qty·birim ;  risk_orani = risk / (τ·W) ;  adim_kaybi = 1 − qty/qty_ham
tavan_bagli = qty_tavan < qty_risk
```

Çift × W × τ tablosu: `n_aday`, `red_min_emir` / `red_min_adet` / `red_teminat` sayı ve oranı (Wilson), `tavan_bagli` oranı, `risk_orani` (yalnız `kabul`) en küçük / %5 / %25 / medyan / ortalama, `adim_kaybi` medyanı, bayrak `bozulma` (toplam red oranı ≥ 0,05 **ya da** medyan `risk_orani` < 0,90). Karşılaştırma tablosu: her küçük cüzdan için 1000'e göre red oranı farkı ve medyan `risk_orani` farkı. Gerçekleşen (yalnız backtest kipi; `equity_at_entry` var): `gercek_oran = planned_risk / (τ·equity_at_entry)` dağılımı çift başına.

Sabit notlar: *"Varsayım: özsermaye W'de sabit, başka açık pozisyon yok, giriş fiyatı planlanan fiyat. Portföy sınırları (aynı yön, günlük bütçe) hesaba katılmaz."* ve kural kaynağı etiketi. Çalışan örnek (test §12-S1): `e=100000, s=98000, long, c=0,001, adım=0,001, min_notional=100` ⇒ `birim = 2198`; `W=250, τ=0,005` ⇒ `qty_risk = 0,000568…`, `qty = 0` ⇒ `red_min_emir`; `W=1000, τ=0,014` ⇒ `qty_risk = 0,006369…`, `qty = 0,006`, tutar 600, `risk = 13,188`, `risk_orani = 0,942`.

`bozulma` bayrağı, §5.3'ün `yetersiz` bayrak yasağının istisnasıdır: küçük örneklemde de basılır ve `bayrak_not = "(yetersiz)"` ile işaretlenir. `--risk` ve `--synthetic-step` değerleri pozitif olmalıdır (aksi halde kod 2, `arg_error`); `risk_usd` (§7.3) yalnız yapılandırmadaki `target_trade_risk · wallet_start` değerinden türetilir, `--risk-usd` tek geçersiz kılmadır.

## 10. Çıktılar, CLI, Telegram

### 10.1 Dosyalar

`<out>/<hedef>/<now tarihi YYYY-MM-DD>/` (`hedef` = `learner`, `twin`, ya da `bt_<koşu id>`):

| Dosya | İçerik |
|---|---|
| `rapor.md` | başlık + sabit uyarılar (§5.6) + bölümler: 1 Çıkış karnesi · 2 Kapı ve veto karnesi · 3 Piyasa koşulu · 4 Alt grup ve yıl satırları · 5 Küçük hesap. Düz Türkçe, tablo başlıkları Türkçe |
| `rapor.json` | `{"schema": 1, "status": "ok"|"holdout_locked"|"empty", "meta": {...}, "counters": {holdout_skipped, pending, data_gap, …}, "k_rapor": …, "z_k": …, "exits": {...}, "gates": {...}, "regimes": {...}, "sizing": {...}, "warnings": [...]}`; anahtarlar sıralı, sayılar 6 ondalığa yuvarlı, NaN yok (`null`) |
| `cikis_islemler.csv` | işlem başına: `trade_id, pair, side, setup, regime, exit_reason, net_r, gross_r, mfe_r, mae_r, geri_verme_r, verim, post_fav_r_24, post_adv_r_24, post_close_r_24, ilk_dokunus_24, erken_cikis_24, (aynıları _72), durum_24, durum_72, ozet` |
| `ozet.txt` | tek satır özet (§10.3) |

Yazım atomiktir (aynı dizinde geçici dosya + `os.replace`). Aynı girdiler + aynı `--now` ⇒ dört dosya bayt bayt aynıdır. `--sections` ile yalnız seçilen bölümler üretilir (`exits,gates,regimes,sizing`; `K_rapor` yalnız üretilen tablolardan sayılır).

### 10.2 CLI (`scripts/report_run.py`)

```
report_run.py --bot learner|twin [--ledger YOL] [--cf YOL] [--market YOL] [--budget YOL]
              [--since ISO] [--until ISO] [--days N] [--now ISO] [--out DİZİN]
              [--sections LİSTE] [--wallets 250,300,1000] [--risk 0.005] [--risk-usd X]
              [--compare-backtest KOŞU_DİZİNİ] [--telegram] [--dry-run]
report_run.py --run-dir var/backtests/<id> --history var/history [--synthetic-rules [--synthetic-step PAIR=X ...]] [...]
```

Varsayılan yollar: `var/<bot>/ledger.sqlite`, `var/<bot>/counterfactual.sqlite`, `var/market.sqlite`, `user_data/budget.sqlite`, `--out var/reports`. `--bot` ve `--run-dir` birlikte verilemez. stdout: tek satır JSON `{status, out_dir, n_trades, n_decisions, holdout_skipped, pending, data_gap, k_rapor, duration_s}`. Çıkış kodları: 0 başarılı (boş veri dahil, `status="empty"`); 2 argüman/girdi hatası (`ledger_missing`, `ledger_schema`, `market_schema` …); 3 `holdout_locked`. `--dry-run` hiçbir dosya yazmaz. Sunucuda haftalık zamanlayıcı (deploy birimi ayrı iş; bu belgenin kapsamı dışında) `--bot learner --days 7 --telegram` ve ayda bir tüm dönem koşar.

### 10.3 Telegram tek satır (isteğe bağlı)

`--telegram` verilirse `ozet.txt` içeriği `TelegramNotifier.send_text(metin, "INFO", dedup_key="rapor:<hedef>:<now tarihi>")` ile gönderilir. Gönderim hatası raporu başarısız kılmaz (uyarı, çıkış 0). Backtest kipinde `--telegram` reddedilir (kod 2). Biçim (düz Türkçe, kısaltma ve İngilizce terim yok, ≤ 300 karakter):

`Haftalık karne: {n} işlem kapandı, ortalama {net_r}R. Kâra geçip zararla kapanan: {n_geri}/{n_ulasan}. Çıkıştan sonra 1R daha giden: {erken}/{n_ok}. Filtreler {n_engel} sinyali engelledi{; engellenenler kazanırdı görünen: {kapı listesi} (varsayım)}. Küçük hesapta reddedilen: %{red}. Ayrıntı raporda; bu rapor ayar değiştirmez.`

`n_geri/n_ulasan` θ = 0,5 içindir; `erken` 72 mumluk; `red` en küçük cüzdan ve ana evren içindir. Veri olmayan parça cümlesiyle birlikte atlanır; hiç işlem yoksa: `Haftalık karne: bu dönemde kapanan işlem yok. Filtreler {n_engel} sinyali engelledi.`

## 11. Bellek, süre, eşzamanlılık

- Sunucu 2 GB ve motorla aynı makinede: tepe RSS **≤ 300 MB**, 90 günlük kağıt verisinde süre ≤ 5 dk; yerelde 2 yıllık backtest (≈ 2 000 karar, 600 işlem) ≤ 10 dk.
- Mumlar işlem/karar başına küçük pencerelerle okunur (≤ 72 adet 1h ya da ≤ 3000 adet 15m); bir çiftin tüm geçmişi belleğe alınmaz; `1m` hiç okunmaz. Feather dosyaları `memory_map` ile, yalnız gerekli dilim numpy'ye çevrilir. Defter satırları imleçle akıtılır; `features` JSON'undan yalnız `atr_tf`/`atr_1h`/`stop_dist_atr` tutulur.
- Okuma işlemleri kısa tutulur (tek uzun okuma işlemi WAL kontrol noktasını bekletmesin): sorgu başına ayrı örtük işlem, `busy_timeout` 5 sn; kilit hatasında bir kez yeniden dene, sonra `*_unreadable` (kod 2).
- Paket `pandas` içe aktarmaz. Tek süreç, tek iş parçacığı.

## 12. Kabul testleri (bağımsız test ajanı; kodu okumadan yazılır)

Testler `tests/reports/` altında, sentetik defter/depo/mum dosyalarını kendisi kurar (defter şeması §2.1'deki görünümlerle; sürüm 2 ve 3 ayrı ayrı).

**Salt okunurluk ve yalıtım**
- G1. Rapor koşusundan önce/sonra `ledger.sqlite`, `counterfactual.sqlite`, `market.sqlite`, `budget.sqlite`, `trades.csv`, `summary.json`, `meta.json` sha256 değerleri aynı; girdi dizinlerinde yeni dosya yok (`-shm`/`-wal` hariç).
- G2. Girdi dosyaları ve dizinleri salt okunur izinle (0444/0555) verildiğinde koşu başarılı.
- G3. Olmayan defter/depo yolu ⇒ dosya **oluşturulmaz**; defter için kod 2 `ledger_missing`, depo için uyarı + rapor üretilir.
- G4. Statik (`ast`) tarama: `src/trader_reports/**` içinde `trader_ml` içe aktarması yok; `pandas` yok; `datetime.now`/`utcnow`/`time.time` çağrısı yok; yazma SQL sözcükleri yok; `sqlite3.connect` yalnız `inputs.open_ro` içinde. `src/trader_engine`, `src/trader_core`, `src/trader_ml` içinde `trader_reports` içe aktarması yok.
- G5. Paket varken ve yokken (ya da rapor koşusundan önce/sonra) referans geri test `trades.csv` + `summary.json` bayt bayt aynı (küçük sentetik koşu yeterli).
- G6. `user_version = 1` ve `= 5` defter ⇒ kod 2 `ledger_schema`; 2, 3 ve 4 ⇒ başarılı, aynı tablolar (v1.1).
- G7. Aynı girdiler + aynı `--now` iki koşu ⇒ dört çıktı dosyası bayt bayt aynı. `--dry-run` ⇒ `--out` altında dosya yok.

**Kilitli dönem**
- H1. `meta.json period` kilitli dönemle kesişen koşu ⇒ kod 3, `status="holdout_locked"`, hiçbir mum/defter sorgusu yapılmadı (sorgu izleyicisi: `set_trace_callback` ya da sahte okuyucu).
- H2. `exit_ts = 2026-04-28T00:00Z` (H0 − 72 saat) işlem atlanır, `2026-04-27T23:59Z` işlem okunur; `entry_ts = 2026-10-31T23:59Z` atlanır, `entry_ts = 2026-11-01T00:00Z` okunur. `holdout_skipped` sayacı doğru; atlanan satırların hiçbir alanı çıktılarda yok.
- H3. Mum sorgu izleyicisi: hiçbir SQL sorgusunun `open_ms` aralığı `[H0, H1)` ile kesişmiyor; feather okuyucuda kilitli döneme denk gelen fiyat dilimi istenmiyor (dosyanın o bölümüne `NaN` yerleştirilir; çıktılarda NaN/None sızıntısı yok ve sonuç değişmez).
- H4. Çıkış sonrası penceresi kilide uzanan işlem (ör. `exit_ts = 2026-04-29`) §4.2 gereği tümden atlanır; `durum` sütunlarında görünmez.
- H5. Rapor başlığında kilit satırı ve doğru sayaç var; yıl satırlarında 2026 `kısmi` notu taşıyor.

**İstatistik**
- I1. Elle hesap: `x = [1, −1, 2, 0]`, günler `[a, a, b, c]` ⇒ `m = 0,5`; `u_a = −0,25`, `u_b = 0,375`, `u_c = −0,125`; `SE = sqrt(3/2·(0,0625 + 0,140625 + 0,015625)) = 0,5728…`; `G = 3 < 8` ⇒ aralık `—`. Aynı desen 8+ güne çoğaltılınca aralık `m ± 1,645·SE`.
- I2. Wilson: `p = 0,5, n = 100` ⇒ `[0,4188; 0,5812]` (±1e-4); `n = 0` ⇒ `—`.
- I3. `z_K`: K = 1, 10, 20, 50 ⇒ 1,960; 2,807; 3,023; 3,291 (±0,001).
- I4. Saf gürültü (sabit tohum, 2000 işlem, 20 hücre): `çıtayı geçti` hücre sayısı 0; her hücre `varsayım` ya da `yetersiz`.
- I5. Gömülü etki (bir hücreye +1R, iki yarıda da, n ≥ 100): `çıtayı geçti`. Aynı etki yalnız ilk yarıda ⇒ `varsayım`.
- I6. `n = 29` ya da `G = 7` hücre ⇒ `yetersiz`, aralık `—`, bayrak yok.
- I7. Tabloya hücre eklemek `K_rapor` ve `z_K`'yı büyütür; `--sections` ile bölüm çıkarmak küçültür; başlıkta ikisi de yazıyor.
- I8. Yıl satırları: 2 yıl (biri +, biri −) ⇒ `pozitif_yil_orani = 0,5`; `n < 30` yıl paydaya girmez.

**Çıkış karnesi**
- E1. Long, `exit_price = 100`, `r_px = 2`; çıkıştan sonraki 1h mumları (h,l,c): `(101,99,100), (103,100,102), (102,97,98)` ve kalanlar sabit 98 ⇒ `post_fav_r_24 = 1,5`, `post_adv_r_24 = 1,5`, `post_close_r_24 = −1,0`, `ilk_dokunus = lehte` (2. mum 102'ye, 3. mum 98'e dokunur), `erken_cikis = 1`. Short için simetrik.
- E2. Aynı mumda hem +1R hem −1R ⇒ `aleyhte`, `erken_cikis = 0`.
- E3. `exit_ts` tam saatte ⇒ pencere o saatin mumuyla başlar; `12:20` ⇒ `13:00` mumuyla.
- E4. `now < pencere sonu` ⇒ `pending`; bir mum eksik ⇒ `data_gap`; ikisi de oran ve ortalamalara girmez, sayaçlarda görünür.
- E5. Geri verme: `mfe_r = [0,6; 1,2; 0,4; 2,0]`, `net_r = [−1; −0,2; −1; 1,5]` ⇒ θ=0,5: `2/3`; θ=1,0: `1/2`; `toplam_r_geri(0,5) = −1,2`.
- E6. Verim: `gross_r = 1, mfe_r = 2, mae_r = 0,5` ⇒ `0,6`; payda < 0,05 ⇒ tanımsız; 1'den büyük değer 1'e kırpılır ve sayılır.
- E7. Kazanan MAE yüzdelikleri `numpy.percentile` ile aynı; `p85 ≤ 0,6` ve `n ≥ 30` ⇒ "geniş olabilir (varsayım)" cümlesi; `n = 29` ⇒ cümle yok; hayatta kalan notu her zaman var.
- E8. `mfe_r` NULL işlemler 6.2–6.5 dışında, `n_gezinti_yok` doğru.
- E9. +1R öncesi gezinti: +1R'ye 3. mumda ulaşan işlemde yalnız ilk iki mumun aleyhte ucu sayılır; hiç ulaşmayan işlemde tüm tutma süresi.
- E10. Bariyer merdiveni: aynı mumda stop + hedef ⇒ ulaşmadı; 72 mumda hiçbiri ⇒ `zaman_asimi`; `k = 1` başabaş `0,5`; maliyetli başabaş `(1 + c)/2`.
- E11. Tek satır neden: §6.7 örneği harfi harfine; `mfe_r` NULL ⇒ kısa şablon; her `exit_reason` için Türkçe karşılık.
- E12. `stop` satırında "stopu genişletme kanıtı sayılmaz" metni var.

**Kapı karnesi**
- K1. Sentetik defterde her `skip_reason` ve §7.1'deki her `risk_reason` metni doğru `kapi` anahtarına düşer; bilinmeyen metin `risk:diger`.
- K2. `hyp_r_net` hepsi +0,5 olan 40 satır / 10 gün kapı ⇒ `yargi = celiskili`, bayrak `kazanani_engelliyor`; hepsi −0,5 ⇒ `uyumlu`; karışık ⇒ `belirsiz`; 10 satır ⇒ `yetersiz`; depo yok ⇒ `kanit_yok`, kod 0.
- K3. `window_end_ts > now` satırları sayılmaz (`bekleyen`); `data_gap`/`invalid_plan` satırları `veri_yok`.
- K4. Hiç satırı olmayan beklenen kapılar tabloda `n_engel = 0`; dönem ≥ 28 gün ise `hic_devreye_girmedi`, kısaysa bayrak yok.
- K5. Veto maliyeti: `reservations` `service='veto', state='settled'`, `charged_micro` toplamı 250000 ⇒ `0,25 USD`; `state='released'` ve `service='lesson'` satırları sayılmaz; `net_usd` formülü; bütçe dosyası yok ⇒ `—`.
- K6. Backtest kipi: veto bölümü "değerlendirilmedi" satırı; karşı-olgu sütunları `—`.
- K7. Sabit satırlar (`koşul:volatile` …) her zaman var; karar yokken `kanit_yok`.
- K8. Çıktıların hiçbirinde ve paket kaynağında kapı kapatan/ayar yazan bir yol yok (G1 + G4); bayraklı satırda "otomatik değişiklik yapılmaz" notu var.
- K9. `--compare-backtest`: backtest'te `time_stop` var, canlıda yok ⇒ listede; kağıt < 28 gün ⇒ "erken".

**Piyasa koşulu**
- R1. Oynaklık sınırları: `atr_ratio = 0,7999` düşük; `0,80` orta; `0,9999` orta; `1,00` yüksek; NULL `bilinmiyor`.
- R2. `exit_regime` sütunu olmayan defter ⇒ bölümde §8.5 cümlesi, hata yok; sütun eklenmiş sentetik defter ⇒ geçiş tablosu üretilir.
- R3. Haftalık etiket: 6 işlemli, ortalaması +0,2 hafta ⇒ `trend_odedi`; 4 işlemli ⇒ `yetersiz`; kendi çifti hariç kuralı: yalnız tek çiftin işlemleri olan haftada o çiftin işlemleri `yetersiz` etiket alır.
- R4. Çıkış nedeni payları toplamı 1 (±1e-9).
- R5. Tüm tablolarda `n`, `G`, aralık ve etiket sütunları var.

**Küçük hesap**
- S1. §9 çalışan örneği (iki cüzdan) sayı sayı.
- S2. Parite: rastgele 500 girdi (sabit tohum) için `kabul` durumunda `qty` ve `risk` `trader_core.risk.size_position` ile aynı (1e-12 göreli); `red_min_emir`/`red_teminat` durumlarında `size_position` `ValueError` verir.
- S3. `qty < min_qty` ama `qty·e ≥ min_notional` ⇒ `red_min_adet` (ayrı sütun).
- S4. Red oranı tam 0,05 ⇒ `bozulma`; medyan `risk_orani` 0,8999 ⇒ `bozulma`; 0,90 ve red < 0,05 ⇒ bayrak yok.
- S5. Kural kaynağı etiketi: sentetik kuralda "SENTETİK kural" metni; kuralı olmayan çift `kural yok` ve hesaplara girmez.
- S6. Varsayım notu (sabit özsermaye, tek pozisyon) bölümde var.

**Çıktı ve CLI**
- C1. `rapor.json` geçerli JSON, `schema = 1`, NaN/Infinity yok; `rapor.md` §5.6 uyarılarını sırayla içerir.
- C2. Boş defter ⇒ kod 0, `status="empty"`, dört dosya üretilir, özet "kapanan işlem yok" cümlesi.
- C3. `ozet.txt` tek satır, ≤ 300 karakter, şu sözcükleri içermez: `MFE`, `MAE`, `CI`, `counterfactual`, `gate`, `regime`; ondalık ayırıcı virgül.
- C4. `--telegram`: sahte bildirici bir kez, `dedup_key = rapor:<hedef>:<tarih>`, önem `INFO` ile çağrılır; bildirici hata verirse kod 0; `--run-dir` ile birlikte kod 2.
- C5. `--bot` + `--run-dir` birlikte ⇒ kod 2. `--sections sizing` ⇒ yalnız o bölüm.
- C6. Bellek: 600 işlem + 2 000 karar + 10 çift × 2 yıl 1h/15m sentetik veriyle tepe RSS ≤ 300 MB; alt süreçte `/proc/self/status` `VmHWM` ile ölçülür (`getrusage` ru_maxrss kullanılmaz: çocuk süreç, fork öncesi üst sürecin tepe RSS değerini devralır); `1m` tablosuna/dosyasına hiç erişilmez (izleyici).
- C7. Gerçek veriyle duman testi (varsa, yoksa atlanır): `--run-dir var/backtests/1h_IS_f1_s0_native_last --history var/history --synthetic-rules` kod 0; `n_trades = 610`.

## 13. Açık noktalar (mentor notu; uygulamayı engellemez)

1. `exit_regime` ve aday üretmeyen yasakların gölge karar satırları WP-3 ile sürüm 4'te geldi (v1.1); bu paket ikisini de okur (§7.4, §8.5), kendisi alan eklemez.
2. Canlı/kağıt defterde giriş anındaki özsermaye yok (`state.sqlite` `eq:<trade_id>` anahtarında var); v1 `state.sqlite` okumaz, "gerçekleşen risk oranı" yalnız backtest kipinde üretilir.
3. Plasebo giriş satırı (A-02, madde 10) ve `real_exit` karşı-olgusu (A-01, madde 6) geldiğinde §6.6 ve §7.2'ye birer sütun eklenir; `rapor.json schema` 2 olur.
4. Wilson aralığının kümelenmemiş olması bilinen sadeleştirmedir (§5.2 notu); bağlayıcı hiçbir karar buna dayanmaz.
5. Bu raporlardan bağlayıcı bir kontrol türetilirse (A-13 "binding") ayrı ön kayıt gerekir ve yalnız sıkılaştırma yönünde olabilir.
