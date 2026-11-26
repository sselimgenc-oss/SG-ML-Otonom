# 06 — Backtester, metrikler, lookahead kilidi, freqtrade çapraz doğrulaması (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §4.1 (kendi backtester'ımız: aynı `Engine` + `HistoricalSource` + `SimClock` + `PaperBroker`; `--paranoid`), §4.2 (çapraz doğrulama: düzeyler A–D, kabul eşikleri, ≥ 4 çalışma, uyum kipi sonra yerel kip, "model farkı raporu"), §4.3 (freqtrade'in silinmesi için kapı), §3.1 (P5, P6), §5 risk 2/4/12. Mevcut referans: `research/run_bt.py` (`analyze`, `ledger_check`, metrik anahtarları), `research/runs/*.json`, `user_data/backtest_results/<id>/{ledger.sqlite,trades_enriched.csv,overlay.json}`. Bağımlılıklar: `05-engine-runner.md` (`Engine`, `SignalSource`, `VetoSource`), `03-paper-broker.md` (uyum kipi), `01-feed.md` (`HistoricalSource`, `StoreSource`), `02-clock-bars.md`. Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Tek motor | Backtest'te ayrı strateji/dolum/çıkış kodu **yoktur**: `build_engine`'in backtest bileşenleriyle (`HistoricalSource`, `SimClock`, `PaperBroker`, `PrecomputedSignalSource`, `NoVeto`) çağrılmasıdır |
| Sinyal | `PrecomputedSignalSource`: `compute_signals` çift başına **bir kez** (tüm geçmiş, `end`'e kadar kesilmiş veri); `--paranoid` örneklem modunda her seçili bar kesilmiş veriyle `WindowedSignalSource` ile yeniden hesaplanıp eşitlik denetlenir |
| Lookahead kilidi | (1) `GuardedView`: her `bars/minute_steps/funding` çağrısı `until/end ≤ clock.now()` değilse `LookaheadError`; (2) `--paranoid`; (3) **motor düzeyi kesme testi** (`--truncate-check`, §6) |
| Çıktı | Çalışma başına **taze** `ledger.sqlite` (var olan dosya → hata), `trades.csv`, `summary.json`, `meta.json` |
| Metrikler | `research/run_bt.py::analyze` anahtarlarıyla aynı (`research/runs/*.json` ile karşılaştırılabilir); freqtrade'e bağımlı kısımlar (stats) ledger'dan türetilir |
| Dönemler | IS `20241101-20251101`, WF `20251101-20260501`; **HOLDOUT `[20260501, 20261101)` ile kesişen her dönem reddedilir** (geçersiz kılma anahtarı yoktur) |
| Çapraz doğrulama | Önce `legacy_compat`, sonra `native`; freqtrade **yeniden çalıştırılmaz**, yalnız üretilmiş sonuç dosyaları okunur |
| Paper ↔ backtest | Aynı veri (`market.sqlite`), aynı parametre/veto kayıtları ile işlem listesi **birebir** eşit olmalı |

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `src/trader_engine/backtest.py` (`main(argv)`, `BacktestRunner`; `--strategy` bayrağı ve strateji adı+sürümünün `summary.json`/`meta.json`/ledger `init_params` etiketine yazılması, bkz. 05 §13.7), `precomputed.py` (`PrecomputedSignalSource`, `GuardedView`, `LedgerReplayVeto`, `LookaheadError`), `metrics.py`
- `research/bt_crosscheck.py`, `research/run_bt_engine.py` (`run_bt.py`'nin metrik/yazım kısmının **motor sürümü**; `research/run_bt.py` dokunulmaz, §4.3 silme commit'inin işidir)
- `scripts/fetch_binance_vision.py` (mevcut dosya; yalnız 1m last + 1m mark ekleme)
- `tests/engine/test_engine_backtest_spec.py`, `test_engine_metrics_spec.py`, `test_engine_precomputed_spec.py`, `test_engine_lookahead_spec.py`, `test_engine_crosscheck_spec.py` (bağımsız test ajanı); `test_engine_backtest_impl_smoke.py` (gerçekleme ajanı)
- `research/reference/` **oluşturmaz** (§4.3 silme adımında oluşur).

Dokunulmaz: `engine.py`, `gates.py`, `strategy_runner.py` (05), `brokers/*` (03), `marketdata/*` (01), `types.py`/`config.py` (02), `research/run_bt.py`, `queue.sh`, `jobs_*.txt`, `user_data/**`.

## 3. `backtest.py` — komut ve akış

`python -m trader_engine backtest` (05 `cli.py` çağırır):

| Bayrak | Anlam |
|---|---|
| `--id ID` (zorunlu) | Çıktı dizini `var/backtests/<id>/`; var ise hata |
| `--period IS\|WF\|YYYYMMDD-YYYYMMDD` | `run_bt.PERIODS` ile aynı; HOLDOUT ile kesişen dönem → çıkış 2 ("holdout_locked") |
| `--strategy NAME` | Kayıtlı strateji (05 §13; varsayılan `price_action_v1` = v1b). `price_action_v1_full` (R1 + 15m, yeniden giriş yasağı yok) TraderV1 eşdeğeridir ve **çapraz doğrulama (§7) yalnız onunla** koşar; ledger sözlüğüyle uyumsuz strateji ⇒ çıkış 2 (`ledger_incompatible`) |
| `--tf 1h\|15m` | `trigger_tf` (parametre `trigger_tf` ile aynı) |
| `--fill-model native\|legacy_compat` | `CostModel.fill_model` |
| `--fee-mult F` (1), `--slip-bps S` (verilmezse: uyum kipinde 0, native'de 2/2/5) | **uyum kipinde** `taker_fee = fee_eff = 0.0005·F + S/1e4` (`run_bt.py` ile aynı; kayma komisyona katılır, ayrı kayma yok). **native kipte** `taker_fee = 0.0005·F`; `--slip-bps` **verilmişse** `slip_entry_bps = slip_exit_bps = S` ve `slip_stop_bps = 2.5·S` (varsayılan 2/2/5 oranı), verilmemişse `2/2/5` |
| `--params '{"trail_atr":3.5}'` | kısmi geçersiz kılma (`strategy.validate_params` doğrulaması; v1'de `SignalParams.from_mapping`); `trigger_tf` bayrağı ezer |
| `--granularity 1m\|15m` | `cost.granularity`; uyum kipinde zorunlu `15m` |
| `--source history\|store` | `HistoricalSource(history_dir)` ya da `StoreSource(--market-db)` (paper ↔ backtest eşitliği) |
| `--synthetic-rules` | `HistoricalSource(synthetic_rules=True)` (rules.json yoksa; raporda etiket) |
| `--veto none\|ledger:PATH` | `NoVeto` ya da `LedgerReplayVeto(PATH)` |
| `--record-filtered` / `--no-record-filtered` | `record_filtered_candidates` (uyum çalışmasında `--no-record-filtered`) |
| `--no-skip-flat` | span optimizasyonunu kapatır (her dakika/çift işlenir; eşdeğerlik testi için) |
| `--paranoid [N]` | N örneklem (varsayılan 200), `--seed 17` |
| `--truncate-check END` | §6 |
| `--from-paper-ledger PATH` | §8 eşitlik raporu |
| `--env paper\|eski` | **Varsayılan `paper` (26.11, P6-03): kâğıt botla aynı yapılandırma** (`engine.paper.json`: `arms`, kümeler, maliyet, 14 çift, `price_action_lab_ml`, `target_mode=resting`, `target_trade_risk=0.01`) + kâğıtla aynı çok kurulumlu sinyal kaynağı. `eski` = 5 çiftli taban yol (yalnız çapraz doğrulama/araştırma; `meta.json` `kagit_paritesi=false`, stderr uyarısı). `--strategy/--tf/--target-trade-risk` yalnız `--env eski`. Programatik `BacktestSpec.env` varsayılanı (None) değişmedi. |
| `--wallet-start W` | Yalnız `--env paper` ile: başlangıç özsermayesi (kâğıt defterinden pencere başı için türetilir) |

Akış:
1. Yapılandırma: `config/engine.base.json` + bayrak geçersiz kılmaları (`apply_overrides`); `mode="backtest"`, `veto_mode="off"` (ya da `LedgerReplayVeto`), `bot="learner"`.
2. Bileşenler: `SimClock(start)`; `HistoricalSource`; `GuardedView(view, clock)`; `PaperBroker(cfg.cost, mmr=LOCKED_CFG.maint_margin_rate, rules_fn, funding_fn, clock)`; `StateStore(":memory:" ya da tmp, durability="off")`; `L.open_ledger(out/ledger.sqlite, "learner", create=True, clock=clock.now)` + `ledger.init_params({9 anahtar}, reason="backtest")` (TraderV1 `_open_ledger_if_configured` ile aynı); `PrecomputedSignalSource`; `Killswitch` boş (dosya yok); `StatusWriter=None`.
3. `engine.run_range(start, end)` (05 §5.4).
4. Çıktılar: `trades.csv`, `summary.json`, `meta.json`, `open_at_end.json`.
5. Çıkış kodları: 0; 2 (holdout/argüman); 3 (`LookaheadError`/paranoid eşitsizliği); 4 (veri yok: `DataError`); 5 (`--truncate-check` başarısız).

`meta.json`: bayraklar, `git_commit` (`git rev-parse --short HEAD` + `+dirty`), `fill_model`, `granularity`, `trigger_source`, `rules_source` (`snapshot`/`synthetic`), `coarse` (bool), `data_range` (çift başına ilk/son açılış), `engine_version`, `param_version_id`, süre.

### 3.1 `PrecomputedSignalSource`

`SignalSource` (05) uygulaması: kurucu `(view, strategy, ...)` alır (05 §13.7); kurucuda her çift için (yalnız `end` öncesi barlar) `strategy.compute` **bir kez** (v1: `regime.classify_series` + `align_to_base` + `compute_signals` + v1b R1 nötrleme); `frame()` her karar adımında `strategy.post_filter(son satır, ctx)` uygular (`ctx.last_exit` backtest `state`'inden; v1b yeniden giriş yasağı) — sonuç `WindowedSignalSource` ile aynı olmalıdır, `--paranoid` bunu denetler; `frame(pair, D, params, version_id)` → `table.index == D − tf` satırı + `status` kuralları **`WindowedSignalSource` ile aynı**: o zamana kadar mevcut tetik bar sayısı `< STARTUP_BARS[tf]` ya da 4h bar sayısı `< STARTUP_BARS_4H` → `no_history`; son 20 tetik/150 4h barda delik → `data_gap`. İlk giriş bu yüzden veri başından ~50 gün (1h) sonradır (freqtrade `startup_candle_count` ile aynı; mevcut sonuçlarda ilk işlem 2024-12-21). Parametre sürümü çalışma boyunca sabittir (ledger'da etkinleştirme olmaz); `activation_id` değişirse `PrecomputedSignalSource` hata verir ("params_changed_during_backtest") — yeniden hesap yok (ders servisi backtest'te çalışmaz). `exit_context`: dilim `index ≥ pos.entry_bar_open`.

### 3.2 `GuardedView`

`MarketView` sarmalayıcısı; her çağrı `until/end ≤ clock.now()` denetler (uyum kipinde `entry_ref_fn`'in "sonraki adım açılışı" okuması için tek istisna: `view.open_at(pair, ts)` yöntemi, **yalnız** `fill_model="legacy_compat"` iken kullanılabilir ve her kullanım `meta.json.peek_uses` sayacına yazılır). İhlal → `LookaheadError` (çalışma durur, çıkış 3). `HistoricalSource.open_at(pair, ts)` 01'de tanımlıdır (§6.2); uyum kipi `entry_ref_fn` (sonraki adım açılışını `open_at` ile okuyan işlev) bu birimde (`backtest.py`) yazılır ve `EntryGate`'e (05) enjekte edilir.

### 3.3 `LedgerReplayVeto(path)`

Paper ledger'ının `decision_events` satırlarını `(pair, side, bar_close_ts)` anahtarıyla okur (salt okunur): `veto_status ∈ {allowed, blocked, stale, missing}` ve `veto_reason` aynen döner; kayıt yoksa **`veto_status="missing"` (blok)** — paper'da o bar için hiç karar kaydı yoksa (motor kapalıydı) backtest de girmez ve bu bar raporda `no_paper_record` olarak ayrı sayılır. `begin_step` no-op.

## 4. `metrics.py`

Saf işlevler (pandas serbest). `run_bt.analyze` anahtarları **aynen** üretilir:

`n_trades, expectancy_R, n_R, median_R, profit_factor, profit_abs, profit_pct, max_dd_pct, max_dd_abs, avg_duration, avg_duration_min, fees_total, fee_only, slip_approx, funding_net, funding_paid, costs_total, gross_pnl, gross_winners, costs_over_gross, costs_over_gross_winners, win_rate, backtest_start, backtest_end, by_setup, by_regime, by_pair, by_side, by_exit, riskcheck{n_viol_2pct, max_loss_pct_eq, n_loss_gt_1p1x_actual_risk, n_R_lt_minus1, min_R, viol[], over_plan[]}`. (`freqtrade_pf` ve `unmatched_ledger_rows` yok; yerine `engine{fill_model, granularity, coarse, rules_source, counters}`.)

Tanımlar (kaynak `run_bt.py`, bire bir):
- `profit_abs` (işlem) = `ledger.realized_pnl` (`gross − fee_entry − fee_exit − funding_paid`); `profit_pct = Σ profit_abs / wallet_start × 100`.
- `R = profit_abs / risk_amt`, `risk_amt = risk.loss_at_stop(qty, entry_price, planned_stop, LOCKED_CFG)` (gerçek dolumla yeniden hesap); `r_ledger = ledger.r_multiple` (`realized / planned_risk`); her ikisi raporlanır, `expectancy_R` `R` ortalamasıdır (eski anahtar).
- `pf(x) = Σ pozitif / −Σ negatif` (ikisi de yoksa `nan`; kayıp yoksa `inf`).
- `fee_paid = fee_entry + fee_exit`; `slip_paid = qty × (entry+exit) × slip_bps/1e4` (uyum kipinde komisyona katılmış kayma; native'de `slip_paid` gerçek dolum−ham fiyat farkından: `trades.csv:slip_cost`); uyum kipinde `fee_only = fee_paid − slip_paid`; native kipte `fee_only = fee_paid` (kayma dolum fiyatındadır, `costs_total`'a girmez); `funding_net = −funding_paid` (+ alınan, − ödenen; **freqtrade `funding_fees` işaretiyle aynı**); `costs_total = fee_paid − funding_net`.
- `gross = ledger.gross_pnl`; `gross_winners = Σ gross>0`.
- `max_dd_pct/abs`: kapanış zamanına göre sıralı **gerçekleşmiş** bakiye eğrisi `wallet_start + cumsum(profit_abs)` üzerinde tepe-dip (`max_drawdown_account` tanımı: tepeye göre göreli; `abs` = tepe−dip). Açık pozisyon eğrisi yoktur.
- `equity_entry_est` (riskcheck): engine `trades.csv:equity_at_entry` (karar anı `AccountState.equity`) kullanılır (run_bt'nin tahmini yerine **gerçek**); `loss_pct_eq = loss / equity_at_entry`.
- `avg_duration`: `exit_ts − entry_ts` ortalaması (`timedelta` metin).

`trades.csv` sütunları (ledger `v_trades` + motor alanları): `trade_id, pair, side, setup, regime, entry_ts, exit_ts, entry_price, exit_price, qty, leverage, planned_entry, planned_stop, planned_target, exit_reason, planned_exit, planned_risk, equity_at_entry, gross_pnl, fee_entry, fee_exit, funding_paid, realized_pnl, r_multiple, mfe_r, mae_r, bars_held, excursion_tf, slippage_entry, slippage_exit, slip_cost, decision_id, param_version_id`.

## 5. Veri: `scripts/fetch_binance_vision.py` genişletmesi

- Eklenen: `1m` last (`klines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip`) ve `1m` mark (`markPriceKlines/<SYM>/1m/<SYM>-1m-YYYY-MM.zip`); *yol ve alan biçimi `data.binance.vision` düzenine göre "doğrulanacak"*; aylık yoksa günlüğe düşme mantığı mevcut kodla aynı; `.CHECKSUM` doğrulaması korunur.
- Çıktı: `{stem}-1m-futures.feather`, `{stem}-1m-mark.feather`; sütunlar `date, open, high, low, close, volume`; **`compression="uncompressed"`** (01 `HistoricalSource` `memory_map` ile okur). Bayraklar: `--tfs` (varsayılan hepsi), `--pairs`, `--start`; 1m için `--only-1m`.
- Boyut uyarısı: ≈ 1,05 M satır × 6 sütun × 8 bayt ≈ 50 MB/dosya/çift (20 dosya ≈ 1 GB); yalnız geliştirme makinesinde.
- Mevcut klasördeki (`user_data/data/binance/futures/`) dosya adları değişmez; `history_dir` ayarlanabilir (§4.3 sonrası `var/history/`).
- Bu geliştirme ortamında Binance REST **HTTP 451** verir (bkz. `scripts/freqtrade_offline.py` başlığı); `data.binance.vision` erişilebilirliği ayrıca doğrulanır. 1m veri yokken uyum kipi (15m adım) çalışır, native kip `DataError` verir ve kaba kip **açıkça** seçilmeden sessizce açılmaz.

## 6. Lookahead kilidi — motor düzeyi kesme testi

`--truncate-check END'`: aynı yapılandırmayla iki çalışma: **A** `[start, end]`, **B** `[start, END']` (`start < END' < end`, `END'` bir tetik tf kapanışı). Kabul (hepsi):
1. B'nin ledger `decision_events` (karar anahtarı: `pair, side, setup, trigger_tf, bar_close_ts`) kümesi, A'nın `bar_close_ts ≤ END'` olanlarıyla **eşit** (tüm alanlar, `id`/`recorded_at` hariç).
2. A'da `exit_ts ≤ END'` olan her işlem B'de **aynı** (`trades.csv` satırı eşit; sayısal alanlar `1e-12` göreli).
3. A'da `entry_ts ≤ END' < exit_ts` olan işlem B'de açık (`open_at_end`) ve `entry_price, qty, initial_stop, current_stop(END')` eşit.
İhlal → çıkış 5 ve fark tablosu `truncate_diff.csv`. Bu test CI'da küçük sentetik veriyle (kasıtlı gelecek-bakan `SignalSource` ile **kırılan** bir kontrol senaryosu dahil) ve gerçek veride bir dönemle koşar.

`--paranoid [N]`: `D` örnekleri (tetik tf kapanışları, `STARTUP` sonrası, çift başına N/çift sayısı, `random.Random(seed)`); her biri için `WindowedSignalSource(view_kesilmiş).frame` ile `PrecomputedSignalSource.frame` karşılaştırılır: ayrık sütunlar (`signal, setup, side, skip_reason, regime, rh_touches, rl_touches`) **eşit**, sürekli sütunlar `|Δ| ≤ 1e-9·max(1,|x|)`. İhlal → çıkış 3 ve `paranoid_diff.json`.

## 7. Çapraz doğrulama: `research/bt_crosscheck.py`

Girdi: freqtrade referans çalışması `user_data/backtest_results/<ID>/` (`ledger.sqlite`, `trades_enriched.csv`, `overlay.json`) ve aynı dönem/parametre/maliyet için motor çalışması (`var/backtests/<ID>_compat/`). **Freqtrade çalıştırılmaz.** Zorunlu çalışmalar (§4.2): `1h_IS_f1_s0`, `1h_WF_f1_s0`, `15m_IS_f1_s0`, `1h_IS_f2_s5` (`fee_mult 2, slip_bps 5`: `fee_eff = 0.0010 + 0.0005 = 0.0015`). Motor komutu (örnek): `backtest --id 1h_IS_f1_s0_compat --period IS --tf 1h --fill-model legacy_compat --fee-mult 1 --slip-bps 0 --granularity 15m --synthetic-rules --no-record-filtered` (freqtrade `--timeframe-detail 15m` ile aynı adım; 15m kolunda ayrıntı yok, adım zaten 15m).

### 7.1 Eşleme anahtarı ve okuma

Her iki taraf da **ledger** (`v_decisions`, `v_trades`) üzerinden okunur (ortak sözlük; freqtrade `trades_enriched.csv` yalnız komisyon/funding sağlaması içindir). İşlem anahtarı `K = (pair, side, entry_ts)`; `trade_id` (freqtrade `trade.id` vs motor sayacı) **kullanılmaz**. Çift adı `canon_pair`. Karar anahtarı `(pair, side, setup, trigger_tf, bar_close_ts)`.

### 7.2 Düzeyler ve kabul

| Düzey | Karşılaştırma | Kabul |
|---|---|---|
| **A — kararlar** | Her iki kümede ortak anahtarlı kararlar: `regime, atr_ratio, rh, rl, rh_touches, rl_touches, features (anahtar kümesi ve değerler, 1e-9 göreli), planned_entry, planned_stop, planned_target`. Risk durumuna bağlı alanlar (`final_action, skip_reason=risk_denied, size_*, risk_*, leverage`) **dışarıda** | Ortak anahtarlarda **%100** eşit. Yalnız bir tarafta olan karar anahtarları tek tek **açıklanmalı** (genelde "önceki işlem sapması yüzünden pozisyon durumu farklı") |
| **B — girişler** | `entry_ts` eşit; `entry_price` göreli `1e-9`; boyut oranı `planned_risk / equity_at_entry` göreli `0.5 %` içinde (freqtrade tarafı için `trades_enriched.equity_entry_est`) | Referans giriş sayısının **≥ %99'u** eşleşir; her fark tek tek açıklanır |
| **C — çıkışlar** | `exit_ts` eşit (±1 adım yalnız `trail` sınıfı için kabul, ayrıca sayılır); `exit_reason` (ledger kodları) eşit; `exit_price` göreli `1e-6` | Eşleşen girişlerin **≥ %97'si**; farklar sınıflandırılır (§7.3) |
| **D — toplamlar** | `Σ r_multiple` (ledger), `Σ fee_entry+fee_exit`, `Σ funding_paid`, işlem sayısı | R farkı **≤ %2** (mutlak fark ΔΣR ≤ 0.02 × max(ΣR_ref mutlak değeri, 1)), komisyon ≤ %2, funding ≤ %5 (ya da mutlak ≤ 0.5 USDT), işlem sayısı ±max(1, %1); her aşım açıklanır |

İşaret sağlaması: motor `funding_paid` (pozitif = ödenen) = `−freqtrade funding_fees` (`run_bt.py` yorumu "+ alınan, − ödenen"); tek tek `1e-6` içinde eşit olmalı (aksi sınıf `funding_sign`/`funding_data`).

### 7.3 İlk sapma yöntemi ve sınıflandırma (zorunlu prosedür)

Sapma zincirlenir (özsermaye ayrışır → boyut ayrışır → riskte durum farkı). Bu yüzden:
1. İki işlem listesini `entry_ts`'ye göre sıralı yürüt; **çalışma başına ilk anahtar farkını** (eksik/fazla işlem, farklı çıkış, farklı fiyat) bul.
2. İlk sapmanın kök nedenini incele (veri, kural, dolum, yuvarlama) ve **sınıflandır**; sonraki farkları "zincir" olarak ayrı kovada say (`chained_after_first`).
3. Mutlak miktar yerine R ve zaman üzerinden karşılaştır.
4. Sınıflar (genişletilebilir): `trail_timing` (iz stop bir bar önce/sonra), `same_bar_order` (stop/hedef aynı adımda), `time_stop_count` (48 bar sayımı ±1), `entry_ref` (giriş referansı), `qty_rounding` (adım/`synthetic_rules`), `price_rounding` (tick), `gap_fill` (açılışta stop ötesi), `day_start_def` (açık pozisyon funding'inin gün başı tanımına etkisi), `funding_data` (eksik funding noktası), `funding_sign`, `fee_model`, `liquidation`, `unexplained`.
5. **Açıklanamayan fark = hata.** Rapor her açıklanamayan satırda hatanın **motorda mı yoksa freqtrade bağdaştırıcısında (`TraderV1`) mı** olduğunu yazar (kanıt: ilgili bar verisi, iki tarafın hesap adımları); hata TraderV1'de ise referans sonuç dosyası **değiştirilmez**, rapor "referans hatası" olarak not düşer ve motor doğru kabul edilir (mentor onayı).

Çıktı: `research/crosscheck/<ID>.json` + `.md` (A–D tabloları, her fark satırı: anahtar, sınıf, kanıt, kök neden, taraf). Kapı geçmesi §4.3 ön koşuludur (tüm 4 çalışmada A–D kabul + açıklanamayan = 0 + mentor onayı).

### 7.4 Yerel kip ve model farkı raporu

Aynı dönemler `native` (1m, mark tetik, ayrı kayma) ile koşar; `bt_crosscheck.py --model-diff` **üç** çalışmayı karşılaştırır: (1) `compat` (15m adım, last tetik, kayma komisyonda); (2) `native_last` (1m adım, **last** tetik, native maliyet); (3) `native_mark` (1m adım, **mark** tetik, native maliyet). Etki ayrıştırması: (1)→(2) = ayrıntı+maliyet modeli; (2)→(3) = **mark ↔ last** etkisi. Rapor: her çalışmada `n_trades, expectancy_R, Σ R, profit_factor`; (2)→(3) için `n_stop_native_last`, `n_stop_native_mark`, `n_stops_removed_by_mark` (last stop tetiklerken mark tetiklemedi), `n_stops_added_by_mark`, `ΔΣR`, işlem başına ort. `ΔR`; ve her değişen stop için örnek satır. Bu rapor mark/last riskinin ölçümüdür (risk tablosu 2). **HOLDOUT kullanılmaz.**

## 8. Paper ↔ backtest eşitliği (paper 1. hafta sonunda ve haftalık)

`backtest --source store --market-db var/market.sqlite --start <paper_start> --end <son tam tetik kapanışı> --veto ledger:var/<bot>/ledger.sqlite --from-paper-ledger var/<bot>/ledger.sqlite --id paper_<tarih> --fill-model native --granularity 1m`. Önkoşullar: aynı `market.sqlite` (feed kayıtları), aynı `rules` (store), aynı parametre sürümü tüm dönem boyunca (aksi rapor "param_activation_changed" der ve eşitlik testi ilgili dönemi dışarıda bırakır), aynı `cost`. Karşılaştırma anahtarı `(pair, side, entry_ts)`; alanlar `entry_price, qty, exit_ts, exit_price, exit_reason, fee_entry, fee_exit, funding_paid, realized_pnl` göreli `1e-9`. **Beklenen: birebir eşit.** Fark = motor hatası; tek açıklama kabul edilen sınıflar: `paper_gap` (paper ledger'ında o bar için `entry_gate_closed`/`other:stale_data` kaydı var — backtest girdi), `no_paper_record` (paper'da o bar için hiç karar kaydı yok: motor kapalıydı), `data_conflict` (`feed_meta.counters.conflicts > 0` ve ilgili bar). Çıktı `equality_report.json` ve çıkış kodu (0 eşit / 6 fark).

## 9. Değişmezler

1. İki çalışma aynı girdiyle **aynı** `ledger.sqlite` içeriğini üretir (`recorded_at` dahil; SimClock). Test: tablo dökümlerinin SHA-256'sı (`id` sırasıyla) eşit.
2. `run_range` flat optimizasyonu ≡ `--no-skip-flat` (aynı ledger).
3. Backtest hiçbir zaman gerçek saat, ağ, rastgelelik (kural yolunda) kullanmaz.
4. HOLDOUT ile kesişen dönem hiçbir bayrakla çalışmaz.
5. Çıktı dizini önceden varsa çalışma başlamaz.
6. Sonda açık pozisyonlar kapatılmaz; `open_at_end` ayrı raporlanır ve `metrics` bunları **dışarıda** bırakır (ya da "mark-to-market" ayrı alan).
7. Uyum kipi çalışmasında `meta.json.coarse=true`, `rules_source="synthetic"`, `peek_uses>0` etiketleri zorunludur; rapor bu çalışmaları "uyum çalışması, yerel sonuç değildir" diye işaretler.

## 10. Uç durumlar

| Durum | Davranış |
|---|---|
| Veri bitişi `end`'den önce | `DataError` (çıkış 4) — sessiz kısaltma yok |
| 1m veri yok, `native` istendi | `DataError`; `--granularity 15m` açık seçilmeli |
| Pair'in verisi diğerlerinden geç başlıyor | O çift `no_history` olana dek giriş yok; işlem açık/raporlanır |
| Funding dosyası dönemi kapsamıyor | `funding_missing` sayacı > 0; rapor uyarı satırı (uyum kipinde freqtrade ile aynı ayrışma sınıfı `funding_data`) |
| `LedgerConflictError` backtest'te | Hata yayılır (strict) — backtest'te aynı mum iki kez karar verilmez; ortaya çıkarsa motor hatası |
| Paranoid örneklem `N > mevcut bar` | Tüm uygun barlar kullanılır |
| `--truncate-check` `END'` kapanış değil | Argüman hatası (çıkış 2) |

## 11. Elle doğrulanabilir örnekler

1. **Metrik:** üç işlem `profit_abs = [+20, −10, −10]`, `wallet_start=1000`: `profit_pct = 0.0`, `pf = 20/20 = 1.0`, `win_rate = 1/3`; bakiye eğrisi `[1020, 1010, 1000]` ⇒ `max_dd_abs = 20`, `max_dd_pct = 20/1020 = 1.96 %`.
2. **fee_eff:** `--fee-mult 2 --slip-bps 5` ⇒ `0.0005×2 + 5/1e4 = 0.0015`; `--fee-mult 1 --slip-bps 0` ⇒ `0.0005` (`research/runs/1h_IS_f1_s0.json`: `fee_eff = 0.0005` ✓).
3. **Native `--slip-bps 4`:** `slip_entry = slip_exit = 4`, `slip_stop = 10`.
4. **Sinyal eşitliği:** `D = 2025-03-01T09:00Z` için `Windowed.frame(...).last.planned_stop == Precomputed.frame(...).last.planned_stop` (göreli `1e-9`); `D`'den sonraki bir barın verisi değiştirilince Windowed sonucu **değişmez**, kasıtlı gelecek-bakan kaynak değişir ⇒ `--truncate-check` hata verir.
5. **Çapraz doğrulama sınıfı:** referans işlem `exit_ts = 2024-12-22 12:00`, `exit_reason="trail_stop"`, motor `exit_ts = 2024-12-22 11:00` ve `exit_price` bir önceki bar stop güncellemesiyle uyumlu ⇒ sınıf `trail_timing`; kanıt: iki tarafın `trail_stop_path` değerleri 11:00 ve 12:00 barlarında. (Gerçek sonuç çalıştırılmadan beklenmez; örnek yalnız rapor biçimidir.)
6. **Paper eşitliği:** paper'da ETH `entry_gate_closed / gate:stale_data` kaydı olan bar için backtest işlem açtı ⇒ sınıf `paper_gap` (hata değil); kayıt yokken fark ⇒ hata.

## 12. Kabul senaryoları (test ajanı için)

`BacktestRunner` uçtan uca küçük sentetik veriyle (T1 ve R1'in ikisi de içeren; sabit tohumlu fiyat üretimi test koduna aittir): taze ledger zorunluluğu; HOLDOUT reddi; determinizm (iki çalışma eşit dökümü); flat optimizasyonu eşdeğerliği; `GuardedView` ihlali (kasıtlı bozuk kaynak) ⇒ çıkış 3; `--truncate-check` hem geçer hem (bozuk kaynakla) kırılır; `--paranoid` eşitsizlik yakalar; `metrics` §11 örnek 1 ve `run_bt` anahtar kümesi eşitliği (anahtar listesi testi); `fee_eff`/maliyet eşlemesi; `LedgerReplayVeto` (allowed/blocked/yok); paper eşitliği: önce motoru paper kipinde sentetik `market.sqlite` üzerinde yürüt, sonra `--source store` ile backtest ⇒ eşit; `bt_crosscheck` küçük hazırlanmış iki ledger çifti ile (eşleşen, ilk sapma, zincir, açıklanamayan) düzey A–D ve sınıflandırma çıktısı; `fetch_binance_vision` 1m eklentisi sahte zip ile (uncompressed yazım, sütunlar).

## 13. Belirsizlikler ve çözümleri

- **Uyum kipi tam birebirlik** `legacy_compat` kuralları (03 §4.5) iki madde "doğrulanacak" taşır (tick yuvarlamama, stop gap fiyatı). Çapraz doğrulamanın ilk çalıştırması bunları **belirler**; bulgu 03 şartnamesine revizyon olarak işlenir (kuralı sessizce değiştirmeyin).
- **Sentetik kurallar** (`freqtrade_offline.py` türetmesi) `qty_rounding` sınıfında ayrışma doğurabilir; bu beklenir ve ayrı etiketlenir. Aynı sentetik kural türetimi uyum çalışmasında kullanılır (01 §6.2).
- **`equity_entry_est`** freqtrade tarafı için run_bt'nin tahminidir (1h kapanış mark'ıyla); B düzeyi boyut oranı toleransı bu yüzden %0,5'tir.
- **Performans:** 10 çift × 2 yıl 1h için `compute_signals` birkaç on saniye, 15m için birkaç dakika (Python döngüsü); native 1m adımları yalnız aktif çiftlerde (span tabanlı) olduğundan toplam süre dakikalar mertebesindedir. Hedef, matris (≥ 28 çalışma) için paralel süreç (`queue.sh` benzeri; freqtrade çağrısı olmadan) — kapsam 06 dışı, §4.3 madde 3.
- **`research/run_bt.py` kalıcılığı:** §4.3 öncesi dokunulmaz; `run_bt_engine.py` aynı CLI bayrak adlarını (`--id --period --fee-mult --slip-bps --tf --params --notes`) taşır ki `jobs_*.txt` yalnız komut adı değişikliğiyle yeniden kullanılsın.
