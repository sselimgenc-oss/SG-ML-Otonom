# 05 — Engine, StrategyRunner, giriş kapısı, mutabakat, kill, status (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §2.1 (veri akışı), §2.2 (`strategy_runner`, `gates`, `engine`, `reconcile`, `killswitch`, `status`, `cli`), §2.6 (mutabakat tablosu), §2.7 (ana döngü), §2.8 (TraderV1 karşılık tablosu — **hiçbir davranış kaybolmamalı**), §3.1 (P4, P7). TraderV1 davranışı (referans): `populate_indicators`, `_gate`, `_stale`, `_bar_final`/`_decided`, `veto_check` (stub), `leverage`, `custom_stake_amount` + `confirm_trade_entry`, `_account_state`, `_event`/`_features`, `_write_once`, `_record_gate_closed`/`_record_skipped_last`/`_write_risk_denied`/`_record_veto`, `order_filled`, `bot_loop_start`. Bağımlılıklar: `02` (tipler, saat, config), `01` (`MarketView`), `03` (`Broker`/`SimBroker`/`PaperBroker`), `04` (`StateStore`, `OrderManager`, `PositionManager`), `trader_core` (`signals`, `regime`, `risk`, `ledger`, `veto`). Strateji takılabilirliği: `otonom-trading-arastirma/tasarim-kararlari.md` (16 Kasım, "Öncelik"), bkz. **§13**. Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet) ve tasarımla çakışmalar

| Konu | Karar |
|---|---|
| Tek döngü | Senkron, tek iş parçacığı; dakikalık adımlar zaman sırasıyla, tf kapanışında karar adımı |
| Sıra (§2.7) | Her karar adımında: parametre yenile → **çıkışlar** → **stop güncelle** → **girişler** |
| Aynı kod | `Engine` paper, backtest ve (Faz B) canlıda **aynı** sınıftır; fark `Broker`, `MarketView`, `Clock`, `SignalSource` enjeksiyonudur |
| Tek risk kaynağı | `risk.check_entry(..., cfg.risk_config)`; `risk_config` = `LOCKED_CFG`'nin yalnız `target_trade_risk`i daha **sıkı** kopyası (varsayılan 0.014 = `LOCKED_CFG`; gevşek/geçersiz ⇒ `ConfigError`); engine hiçbir risk sayısı tanımlamaz |
| Kapı sırası | §4.1 tablosu (TraderV1 sırasıyla birebir; §2.2 sırası ile fark gerekçeli) |
| Çıkışlar kapısız | Defter/veto/kill/bayatlık hiçbir çıkışı engellemez |
| Atomiklik | Paper/backtest'te her adım (dakika ya da karar) **tek** `state.tx()`; `broker.snapshot()` aynı işlemde yazılır |
| Kalıcı "mum başına tek karar" | `state.decided(pair, bar_close_ts)` |
| Kaba kip / uyum kipi | Aynı `Engine`, yalnız `CostModel`/`MarketView` farkı (06) |
| Strateji | Takılabilir parça (§13): `Strategy` protokolü + statik kayıt defteri; v1b = `PriceActionV1` adaptörü. Kapı zinciri (§4.1), risk kilidi, çıkış güvenliği ve ledger sözleşmesi **değişmez**; strateji yalnız aday tablosu (`SIGNAL_COLUMNS`) üretir, boyut/risk/kapı kararı vermez |

**Tasarım ↔ mevcut kod çakışmaları ve çözümleri (mentor kararı gerekebilir):**

1. **Hedef çıkışı (§2.6 vs `strateji-spec` §5.4).** Tasarım §2.6 R1 hedefini borsada `TAKE_PROFIT_MARKET` olarak kurmayı söyler; `strateji-spec` §5.4 ve `TraderV1.custom_exit` hedefi **kapanmış barın high/low'u** ile değerlendirip bir sonraki adımda piyasa çıkışı verir ("v1 sadeliği; backtest ve canlı aynı"). İkisi davranışça farklıdır (bar içi tetik vs bar kapanışı) ve çapraz doğrulama (§4.2 düzey C) freqtrade kuralını ister. **Faz A kararı (MENTOR ONAYLADI, 16 Kasım 2026; tasarım §2.6 düzeltildi):** `target_mode="bar_close"` (tek geçerli değer; `place_target` Broker arayüzünde ve PaperBroker'da vardır ama motor çağırmaz). Borsada hedef emri strateji davranışını değiştirir; Faz B/sonrası için ayrı strateji-spec revizyonu ve mentor onayı gerekir.
2. **Kapı sırası.** Tasarım §2.2: `params_ok → ledger → stale → kill → tek karar → veto → check_entry`. TraderV1: `_gate`(trigger_tf, params_ok, ledger) → stale → bar_final → veto → risk. Burada **TraderV1 sırası** korunur (kill ve `entries_blocked_reason` ledger kapısının hemen arkasına, `stale`'den önce eklenir; "tek karar" kontrolü en başa alınır çünkü kayıt yazmaz). Gerekçe: aynı mumda ikinci kez kayıt/log üretmemek.
3. **Ledger `skip_reason` sözlüğü** (`stop_width, rr_below_min, veto_blocked, veto_missing, veto_stale, risk_denied, entry_gate_closed, order_failed, other, ml_filter`; `ml_filter` şema 3, ML-0a/19a) `stale_data`, `kill`, `rules_missing`, `order_unknown` gibi motor kodlarını içermez. Eşleme §4.2: bu kodlar `entry_gate_closed` (kapı) ya da `other` (veri) olarak yazılır, gerçek kod `veto_reason` alanında `gate:<kod>` biçimiyle taşınır (`not_evaluated` kararlarında serbest metin geçerlidir).
4. **`Ledger.find_unledgered_trades(freqtrade_open_trade_ids)`:** parametre adı freqtrade'e özgüdür; engine **konumsal** çağırır (`ledger.find_unledgered_trades(ids)`), yeniden adlandırma ayrı iştir (§4.3 madde 5).
5. **`health.ApiProbe`** freqtrade API alanları (`ping_ok`, `last_process_at`, `last_candle_open`, `open_trade_ids`, `dry_run`) içerir. `status.json` aynı bilgileri taşır (§8) ve `health_run.py` uyarlaması (ayrı iş; `health.evaluate` değişmez) bunlardan `ApiProbe` kurar.
6. **`bars_held` birimi** 15 dakikadır (ledger), zaman durdurma sayacı tetik tf barıdır (04 §9).
7. **`veto.json.pairs_from`** `config/base.json`'u gösterir; §4.3'te `base.json` silinecektir. Engine yapılandırması `config/engine.base.json:pairs` taşır; `pairs_from` yeniden işaretlenmesi silme adımının parçasıdır (veto kodu `dosya:nokta.yolu` serbest olduğundan kod değişmez).
8. **`pyproject.toml`** yalnız `pandas`, `numpy` içeriyor; `pyarrow`, `requests` eklenmesi 08'dedir.
9. **`ledger.Ledger` `clock` parametresi** "yalnızca test içindir" der; backtest için `SimClock.now` geçmek `strateji-spec` §6 ile aynı kullanımdır (ve `bar_close_ts ≤ now+5 sn` denetimi için **zorunludur**).

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `src/trader_engine/strategies/{__init__,base,registry,price_action_v1}.py` (§13; **yeni paket, 05'e aittir**; `_1l3a_adapter.py` Faz A dışı, aynı paket, sonradan eklenir)
- `src/trader_engine/strategy_runner.py`, `gates.py`, `engine.py`, `reconcile.py`, `killswitch.py`, `status.py`, `cli.py`, `__main__.py`
- `tests/engine/test_engine_strategy_runner_spec.py`, `test_engine_gates_spec.py`, `test_engine_engine_spec.py`, `test_engine_reconcile_spec.py`, `test_engine_killswitch_status_spec.py`, `test_engine_strategies_spec.py` (bağımsız test ajanı); `test_engine_runner_impl_smoke.py` (gerçekleme ajanı)

Dokunulmaz: tüm `trader_core`, `02`/`01`/`03`/`04`/`06`/`07` dosyaları. `backtest.py` ve `metrics.py` (06), `fileio.py` (07), `marketdata/*` (01). `scripts/health_run.py` uyarlaması bu işin **dışındadır** (ayrı iş; status.json sözleşmesi §8'de verilir).

`cli.py` alt komutlarından `backtest` `trader_engine.backtest.main(argv)`'ı, `feed` `trader_engine.marketdata.feed`'i, `rules-snapshot` 01'in işlevini **çağırır** (ince sarmalayıcı; mantık orada). `cli.py` içe aktarma anında ağır modül yüklemez (alt komut içinde tembel import).

## 3. `strategy_runner.py`

```python
@dataclass(frozen=True)
class SignalRow:                          # son kapanmış tetik barının sinyal satırı
    pair: str; bar_open_ts: datetime; bar_close_ts: datetime
    signal: bool; setup: str | None; side: str | None; skip_reason: str | None
    planned_entry: float; planned_stop: float; planned_target: float | None   # NaN -> None dönüşümü yapılır
    rr: float | None; stop_dist_atr: float | None
    atr_tf: float | None; atr_4h: float | None; atr_ratio: float | None
    regime: str; rh: float | None; rl: float | None; rh_touches: int; rl_touches: int
    ema_value: float | None; body_ratio: float | None; wick_ratio: float | None; edge_dist_atr: float | None
    pullback_ema: int; reasons: str
    param_version_id: int

@dataclass(frozen=True)
class SignalFrame:
    pair: str; status: Literal["ok","no_history","data_gap","error"]; detail: str | None
    last: SignalRow | None
    table: pd.DataFrame | None            # SIGNAL_COLUMNS + open/high/low/close; indeks = bar AÇILIŞI (UTC)

class SignalSource(Protocol):
    def frame(self, pair: str, D: datetime, params: SignalParams, version_id: int) -> SignalFrame
    def exit_context(self, pair: str, pos: Position, D: datetime) -> ExitContext | None
        # ok kareden E..son bar dilimi; frame status != "ok" ise None DEĞİL, çağıran 'veri yok' dalına gider (§6.3)

class WindowedSignalSource:
    def __init__(self, view: MarketView, strategy: Strategy, *, strict: bool = False)        # strict=True: hatalar yayılır (backtest/test)
```

### 3.1 `WindowedSignalSource.frame` (TraderV1.`populate_indicators` karşılığı; referans uygulama)

**Strateji genellemesi (§13):** aşağıdaki adım 1–3 `PriceActionV1`'in (v1b) davranışını tarif eder. Genel kural: pencereler, `STARTUP`/süreklilik eşikleri ve `compute` çağrısı `strategy.info` ve `strategy.compute(ctx)` üzerinden gelir; v1 sabitleri (`WINDOW_*`, `STARTUP_*`, 20/150) `PriceActionV1.info`'nun değerleridir. Adım 3'teki `compute_signals` çağrısı `strategy.compute` olur; sonucun şema doğrulaması §13.3'tedir.

1. `tf = params.trigger_tf`; `trig = view.bars(pair, tf, D, WINDOW_TRIGGER[tf])`, `h4 = view.bars(pair, "4h", D, WINDOW_4H)`. (`until=D` zorunlu; D'den sonra bar yok.)
2. Kontroller (sırayla; ihlal → `SignalFrame(status=…, last=None)` ve `strict` değilse sayaç+log): `len(trig) < STARTUP_BARS[tf]` ya da `len(h4) < STARTUP_BARS_4H` → `no_history`; son tetik barının açılışı `≠ D − tf` → `data_gap` (`detail="trigger_bar_missing"`); `view.contiguous_tail(pair, tf, D) < 20` ya da `contiguous_tail(pair, "4h", D) < 150` → `data_gap` (`detail="hole"`).
3. `reg = regime.classify_series(h4[["open","high","low","close"]], params.regime_params())`; `aligned = regime.align_to_base(reg, trig.index, 4)`; `sig = signals.compute_signals(trig[["open","high","low","close"]], aligned, params)`. `table = sig.join(trig[ohlc])`. `last` = son satır → `SignalRow` (NaN → `None`; `param_version_id = version_id`).
4. Hata (herhangi bir istisna): `strict` ise yayılır; değilse `SignalFrame(status="error")`, `callback_errors += 1`, `CRITICAL` log → **o çift için giriş yok** (TraderV1 `populate_indicators` hata kolu). Çıkışlar etkilenmez (§6.3).
5. Aynı `(pair, D, version_id)` için sonuç bellek içinde **tek tur** önbelleklenir (aynı karar adımında girişler ve çıkışlar tek hesaplamayı paylaşır).
6. `exit_context(pair, pos, D)`: `table`'dan `index ≥ pos.entry_bar_open` dilimi → `ExitContext(highs, lows, atrs=atr_tf, regime_last=table.regime.iloc[-1], last_close=table.close.iloc[-1], n_closed=len(dilim))`. `pos.entry_bar_open` yoksa/`table` yoksa `None` (04 `evaluate_exit` `force_exit` verir **yalnız** pozisyon verisi eksikse; veri boşluğunda motor bu yola girmez, §6.3).

**Geçmiş uzunluğu bağımlılığı (açık nokta):** EMA/ATR özyinelemeli (tohum ilk gözlem; `indicators.py`); 4h EMA100 için 300 bar sonrası tohum etkisi ≈ `0.98^300 ≈ 0.2 %` olduğundan **pencere uzunluğu** (`WINDOW_4H = 1500`) paper ile backtest (tüm geçmiş) arasında sınırda kararları değiştirebilir (`0.98^1500 ≈ 1e-13`, ihmal edilir). Kabul: paper ↔ backtest eşitlik testi 06'da `WindowedSignalSource` ile `PrecomputedSignalSource` farkını gerçek veride ölçer; ayrık sütunlar (`signal, setup, side, skip_reason, regime`) **eşit**, sürekli sütunlar `|Δ| ≤ 1e-9·max(1,|x|)` olmalıdır; aksi açıklanamayan fark = hata.

## 4. `gates.py` — giriş kapısı

```python
class VetoSource(Protocol):
    def begin_step(self, now: datetime) -> None            # dosya burada bir kez okunur
    def lookup(self, pair: str, side: str, now: datetime) -> veto.VetoLookup

class FileVeto:                                            # paper/canlı; veto_mode="required"
    def __init__(self, vcfg: veto.VetoConfig, env: Mapping[str,str])   # key = env[vcfg.hmac_key_env]; yoksa key_missing -> lookup missing
class NoVeto:                                              # yalnız backtest; veto_mode="off"
    # lookup -> VetoLookup("allowed", "not_evaluated:backtest", False); begin_step no-op

@dataclass(frozen=True)
class EntryOutcome:
    action: Literal["enter","skip","ignore"]
    event: L.DecisionEvent | None          # skip/enter için yazılacak karar
    size: K.SizeResult | None
    leverage: int | None
    code: str                              # ayrıntılı kod (günlük/sayaç)
    mandatory_record: bool                 # enter: True (yazılamazsa giriş yok); skip: best-effort

class EntryGate:
    def __init__(self, cfg: EngineConfig, ledger: L.Ledger, state: StateStore, kill: Killswitch,
                 veto: VetoSource, clock: Clock, broker: Broker, rules_fn: Callable[[str], SymbolRules],
                 entry_ref_fn: Callable[[str, datetime, SignalRow], float] | None = None)
    def pre(self, D: datetime, tf: str, params_ok: bool, active_tf: str) -> GateVerdict       # çift-bağımsız kapılar, adım başına bir kez
    def decide(self, frame: SignalFrame, D: datetime, pre: GateVerdict, active_version: int) -> EntryOutcome
```
`build_decision_event(row: SignalRow, tf: str, **override) -> L.DecisionEvent` (TraderV1 `_event`/`_features` birebir): `bar_close_ts = row.bar_close_ts`; `rh`/`rl` yalnız `regime=="range"`; `features` = `atr_tf, stop_dist_atr, atr_4h` + (T1: `pullback_ema, ema_value, body_ratio` | R1: `wick_ratio, rr, edge_dist_atr`) + `rh_touches, rl_touches`; yalnız sonlu değerler (`pullback_ema`, `*_touches` `int`, diğerleri `float`); varsayılanlar `veto_status="not_evaluated"`, `risk_allowed=None`, `final_action="skipped"`, `size_*=None`, `leverage=None`.

### 4.1 Kapı zinciri (`decide`; ilk eşleşen sonuç)

Her satırda "kayıt" ledger `record_decision`'dır; **skip** kayıtları best-effort (`LedgerError` yutulur, log), **entered** kaydı zorunludur.

| # | Koşul | Sonuç | `skip_reason` | `veto_status` / diğer alanlar |
|---|---|---|---|---|
| 0 | `frame.status != "ok"` ya da `last is None` | `ignore` (log; sayaç `data_gap`/`no_history`/`errors`) | — | kayıt yok |
| 1 | `row.signal == False`: `setup` dolu ve `skip_reason ∈ {stop_width, rr_below_min, ml_filter}` ve `record_filtered_candidates` ve `param_version_id ≥ 1` | `skip` (kayıt) | `row.skip_reason` | `not_evaluated`, `risk_allowed=None`, `veto_reason=None` |
| 1b | `row.signal == False`, diğer | `ignore` | — | kayıt yok |
| 2 | `state.is_decided(pair, D)` | `ignore` | — | kayıt yok (mum başına tek karar) |
| 3 | çiftte açık/bekleyen pozisyon (`state.position_for_pair`) | `ignore` (log) | — | kayıt yok (freqtrade aynı çiftte giriş denemez; `check_entry` kural 5 yine savunma) |
| 4 | `not params_ok` (`ledger.get_active_params()` hata) ya da `active_tf != engine tetik tf` | `skip`, `mark_decided` | `entry_gate_closed` | `not_evaluated`, `veto_reason="gate:params_unavailable"` / `"gate:trigger_tf_changed"` |
| 5 | `ledger.entries_allowed().ok == False` | `skip`, `mark_decided` | `entry_gate_closed` | `veto_reason="gate:<health.code>"` (`degraded`, `spool_pending`, `schema`, `no_active_params`, `unledgered_trades`) |
| 6 | `state.kv_get("entries_blocked_reason")` dolu | `skip`, `mark_decided` | `entry_gate_closed` | `veto_reason="gate:<neden>"` (`order_unknown`, `exit_unknown`, `stop_failed`, `reconcile_unknown_position`, `day_start_missing`, `outbox_stuck` (mentor A2: outbox satırı yazılamıyor, çözülene kadar kapalı)) |
| 7 | kill etkin (`kill.active()`) | `skip`, `mark_decided` | `entry_gate_closed` | `veto_reason="gate:kill"` |
| 8 | **bayat:** `clock.now() − D > stale_factor × tf` | `skip`, `mark_decided` | `other` | `veto_reason="gate:stale_data"` |
| 9 | `rules_fn(pair)` `DataError` | `skip`, `mark_decided` | `other` | `veto_reason="gate:rules_missing"` |
| 10 | `veto.lookup(pair, side, now).blocks` | `skip`, `mark_decided` | `f"veto_{lookup.status}"` | `veto_status=lookup.status` (`blocked`/`missing`/`stale`), `veto_reason=lookup.reason` |
| 11 | `risk.check_entry(account_state, candidate, cfg.risk_config)` `allowed == False` | `skip`, `mark_decided` | `risk_denied` | `veto_status="allowed"`, `veto_reason=lookup.reason`, `risk_allowed=False`, `risk_reason=dec.reason` |
| 12 | hepsi geçti | `enter` | `None` | `veto_status="allowed"`, `veto_reason=lookup.reason`, `risk_allowed=True`, `risk_reason=dec.reason`, `size_qty/notional/margin/risk_amount`, `leverage` |

Notlar:
- **Sıra: kurulum süzgeçleri (1) → … → veto (10) → risk (11)** (defter-spec ve TraderV1 ile aynı; "veto yalnızca girişi azaltabilir").
- `NoVeto` (backtest) `lookup.reason="not_evaluated:backtest"`, `status="allowed"` döner; ledger `entered` kuralı (`veto allowed`) bu sayede sağlanır (TraderV1 stub çözümünün karşılığı).
- Satır 4–9'da `row.signal == True` ve `setup`/`side` dolu olduğundan `DecisionEvent` kurulabilir; `param_version_id` `row`'dan gelir (`ledger` `param_version_id ≥ 1` şartı; `< 1` ise kayıt yazılmaz, `ignore`).
- **Adaya özgü kayıt (satır 4–9) yalnız `signal == True` satırlar için** yazılır; bayat veri/kill/kapı kapalıyken her çift için gürültü kaydı üretilmez.
- `veto.lookup` `blocks=False` yalnız taze belgede süresi dolmamış `allow` için döner (veto-spec); başka her şey `skip`.

### 4.2 Hesap durumu ve aday (TraderV1 `_account_state`, `_risk`)

`AccountState(equity, day_start_equity, open_positions)`:
- `equity = broker.account().equity` (paper: `wallet + unrealized`, mark ile).
- `day_start_equity = state.kv_get("day_start:<UTC YYYY-MM-DD>")` = o UTC gününün **ilk işlenen adımındaki özsermaye (mentor B6; önceden cüzdan)** (`Engine.ensure_day_start(ts)`, §6.2). Değer yoksa: `kv["initialized_at"]` bugünden önce ise (state var ama o günün anlık görüntüsü kayıp) → `entries_blocked_reason="day_start_missing"` (kapı 6) ve `ensure_day_start` cüzdanı o güne yazar (yarın açılır); taze kurulumda (`initialized_at` bugün) `wallet_start` kullanılır. Not: TraderV1 formülü (`cüzdan − bugün kapanan işlemlerin kâr/zararı`) ile **tanım olarak aynıdır**; farklı olan, açık pozisyonun funding'inin gün içinde cüzdana işlenmesidir (freqtrade işlem kapanınca işler) — bu mikro fark çapraz doğrulamada "gün başı tanımı" sınıfıdır.
- `open_positions = [OpenPosition(p.pair, p.side, p.risk_amount, p.margin) for p in state.open_positions()]` — `opening`, `open`, `closing` **hepsi** (aynı karar adımında ilk girişin riski ikinci çifte rezerve görünür; çıkış emri verilmiş ama dolmamış pozisyon da sayılır: tutucu).

`Candidate(pair, side, entry=entry_ref, stop=row.planned_stop, leverage=lev, qty_step=rules.step, min_notional=rules.min_notional)`:
- `lev = int(max(1, LOCKED_CFG.min_leverage))` (= 3; TraderV1 `leverage()` ile aynı kural).
- `entry_ref`: native/paper'da `row.planned_entry` (= tetik barı kapanışı = son 1 dk last kapanışı; fark yok). Uyum kipinde `entry_ref_fn` (06) sonraki adım **açılışını** verir (freqtrade `current_rate`); bu hile yalnız `fill_model="legacy_compat"` backtest'inde vardır, paper/canlıda `entry_ref_fn=None`.

## 5. `engine.py`

```python
@dataclass(frozen=True)
class RecoveryReport: replayed_minutes: int; replayed_decisions: int; unresolved_orders: int; reconcile: ReconcileReport

@dataclass(frozen=True)
class RunSummary: steps: int; decisions: int; trades_opened: int; trades_closed: int; open_at_end: tuple[int, ...]; counters: dict

class Engine:
    def __init__(self, cfg: EngineConfig, *, clock: Clock, view: MarketView, broker: Broker, ledger: L.Ledger,
                 state: StateStore, signals: SignalSource, strategy: Strategy, veto: VetoSource, kill: Killswitch,
                 status: StatusWriter | None, orders: OrderManager | None = None,
                 entry_ref_fn=None, strict: bool = False)
    def start(self) -> RecoveryReport
    def advance_to(self, now: datetime) -> int                 # canlı/paper: now'a kadar kapanmış dakikaları ve karar adımlarını işler
    def run_forever(self) -> None                              # while: advance_to(clock.now()); reconcile; status; clock.sleep(cfg.loop_sleep_s)
    def run_range(self, start: datetime, end: datetime) -> RunSummary    # backtest sürücüsü (span tabanlı, §5.4)
    def process_step(self, step: MinuteStep) -> None           # §5.2
    def decision_step(self, D: datetime) -> None               # §5.3
    def ensure_day_start(self, ts: datetime) -> None
    def shutdown(self, reason: str) -> None
    # gözlem: counters(), summary()

def build_engine(cfg: EngineConfig, *, clock: Clock | None = None, view: MarketView | None = None,
                 broker: Broker | None = None, env: Mapping[str,str] | None = None) -> Engine
        # paper: `registry.get_strategy(cfg.strategy)` + StoreSource(cfg.market_db) + PaperBroker + SystemClock + FileVeto + gerçek ledger/state; backtest sürücüsü (06) kendi bileşenleriyle çağırır
```

### 5.1 Başlatma (`start`)

1. (25.11: ikiz ve `start_delay_s` kaldirildi; bekleme yok.)
2. `StateStore` açılır/kilitlenir (04); `integrity_check`; `kv["engine_version"]`/`trigger_tf` doğrulanır.
3. Defter açılır (`L.open_ledger(cfg.ledger_path, cfg.bot, create=True, clock=<paper: None, backtest: clock.now>)`). `ledger.drain_spool()`; `state.drain_outbox(ledger)`.
4. Paper broker: `state.kv_get("broker_snapshot")` varsa `broker.restore(...)`; yoksa taze (`wallet_start`). `broker.prepare(pair, lev)` her çift için (idempotent).
5. `orders.resolve_unresolved()` (04 §4.2).
6. **Mutabakat** (§7) ilk kez çalışır; `ReconcileReport.fatal` ise motor **girişleri kapalı** başlar (`entries_blocked_reason`), çıkışlar çalışır.
7. İmleçler: `cursors(*, "minute")` yoksa (ilk kurulum) son kapanmış dakikaya ayarlanır, geçmiş oynatılmaz; varsa **oynatma** (§5.5).
8. Boş etkin parametre (`ledger.get_active_params()` hatası): motor başlar ama `params_ok=False` (kapı 4) — otomatik `init_params` **yapılmaz**; `python -m trader_engine init-ledger --bot X` açık işlemdir (§9).

### 5.2 `process_step(step)` — bir dakika (ya da kaba kipte 15 dk) adımı

Girdi `step.ts` = adım barı açılışı, `end = ts + step_s`. Tüm gövde **tek** `with state.tx():` (simüle broker); `Clock` backtest'te `SimClock.set_time(end)`, canlıda gerçek saat.

1. `ensure_day_start(ts)`.
2. `broker.advance(step.bars, "fills")`; `ev = broker.poll(now)`; `handle_events(ev, step)`:
   - `fill` (giriş): 04 `apply_entry_fill` (+ `update_excursion` adım barıyla), `outbox_add("entry", …)`, **dolum sonrası risk doğrulaması** (04 §5.2) → ihlalse çıkış; değilse `place_initial_stop`.
   - `fill` (çıkış/`stop`/`target`/`liquidation`): `apply_exit_fill`, `outbox_add("exit", …)`, `cancel_resting`, pozisyon `closed`.
   - `funding`: `apply_funding` (pozisyon `funding_paid` birikir).
   - `order_rejected`/`order_canceled`: giriş reddi → pozisyon `closed` (hiç açılmadı), ledger karar düzeltmesi `order_failed` (supersedes) **best-effort**; stop reddi → 04 §5.2.
3. `broker.advance(step.bars, "triggers")`; `ev = broker.poll(now)`; `handle_events`.
4. Hâlâ açık her pozisyon için (adım barı olan çiftlerde): `update_excursion(pos, bar)` (giriş/çıkış adımında zaten uygulandıysa çift sayılmaz: `update_excursion` genişletme olduğundan idempotenttir).
5. İmleçler: her çift `set_cursor(pair, "minute", ts)`; `state.kv_set("broker_snapshot", json(broker.snapshot()))` (paper). Commit.
6. Tx dışı: `state.drain_outbox(ledger)` (başarısızlık adımı geri almaz; ledger kendi spool/degraded kapısını yönetir).
7. `end` tetik tf'nin kapanışıysa (`bars.is_tf_close(end, trigger_tf)`) çağıran `decision_step(end)` çağırır (canlıda `advance_to`, backtest'te `run_range` sürücüsü).

### 5.3 `decision_step(D)`

Tek `with state.tx():` (simüle broker).
1. **Parametre yenile:** `ap = ledger.get_active_params()`; `activation_id` değiştiyse `SignalParams.from_mapping(ap.params)` kurulur; hata → `params_ok=False` (girişler kapalı, kapı 4; açık pozisyonlar dondurulmuş parametreleriyle sürer). `ap.params["trigger_tf"] != engine tf` → `trigger_tf_changed` (girişler kapalı, `CRITICAL`; yeniden başlatma gerekir).
2. `veto.begin_step(now)` (dosya tek kez okunur).
3. **Çerçeveler:** her çift için `signals.frame(pair, D, params, ap.version_id)`.
4. **Çıkışlar (kapısız):** `state.open_positions()` içinde `status == "open"` her pozisyon için (çift sırasıyla):
   - Çerçeve `ok` değilse: serbest çıkışlar bu bar için **atlanır** (§6.3); koruyucu stop borsada/PaperBroker'da duruyor. Sayaç `exit_data_gap`.
   - Aksi `ctx = signals.exit_context(...)`; `dec = evaluate_exit(pos, ctx)`:
     - `exit` → `orders.submit_exit(pos, dec.reason, D)`; pozisyon `closing`; `exit_reason` pozisyona yazılır (dolumda 04 §5.3 kullanır).
     - `stop_update` → `orders.replace_stop(pos, dec.new_stop)`; `would_trigger` notu gelirse `trail_stop` piyasa çıkışı verilir.
     - `none` → hiçbir şey.
5. **Girişler:** `pre = gate.pre(D, tf, params_ok, ap.params["trigger_tf"])`; `cfg.pairs` sırasıyla her çift için `out = gate.decide(frame, D, pre, ap.version_id)`:
   - `ignore` → devam.
   - `skip` → `ledger.record_decision(out.event)` (best-effort) ve `state.mark_decided(pair, D, "skipped:" + out.code)`.
   - `enter` → `trade_id = state.next_trade_id()`; `did = ledger.record_decision(out.event)` (**zorunlu**; `LedgerError`/herhangi bir istisna → giriş yok, `CRITICAL`, `mark_decided` **yazılmaz** (yeniden başlatmada aynı bar tekrar denenebilir; içerik farklıysa `LedgerConflictError` → giriş yok, TraderV1 ile aynı)); başarılıysa `Position(status="opening", …)` ve `Intent` kurulur: `insert_position` + `mark_decided(pair, D, "entered")` aynı tx; `orders.submit_entry(intent, trade_id)`. Sonuç `failed`/`rejected` ise pozisyon silinir/`closed`, `record_decision(supersedes_id=did, final_action="skipped", skip_reason="order_failed")` **best-effort**.
6. `state.set_cursor(pair, "decision", D)` (her çift); `kv["broker_snapshot"]`; commit; `outbox` boşalt; `status.write()`.

**Pozisyon dondurulmuş alanlar** (giriş anında, TraderV1 `_on_entry_fill` `data` sözlüğü): `initial_stop = row.planned_stop`, `planned_target = row.planned_target`, `rh/rl`, `setup`, `trail_atr = params.trail_atr`, `param_version_id`, `trigger_tf`, `risk_amount = size.risk_amount`, `decision_id = did`, `signal_bar_close_ts = row.bar_close_ts`, `strategy_name`, `strategy_version` (§13.6).

### 5.4 `run_range(start, end)` — backtest ve çevrimdışı sürücü

Span tabanlı (flat optimizasyonu): `D_k` = `(start, end]` içindeki tetik tf kapanışları. Her `D_k` için: (a) `view.minute_steps(active_pairs, cursor, D_k)` ile **yalnız** açık/bekleyen emri olan çiftlerin adımları `process_step` edilir (aktif çift yoksa adım atlanır; flat dönemde cüzdan değişmez, funding yok); (b) `SimClock.set_time(D_k)`; (c) `decision_step(D_k)`. Aktif küme `decision_step` sonrası belirlenir (girişler yeni çift ekler; çıkışlar `closed` olana dek tutar). `end` sonunda açık pozisyonlar **kapatılmaz**, `RunSummary.open_at_end` listelenir. Bu optimizasyonun tam adım adım çalışmayla **eşdeğerliği** testle kanıtlanır (06): aynı veri, `active_only=False` ile tüm çiftlerin her dakikası işlenir, ledger eşit olmalı.

### 5.5 `advance_to(now)` (canlı) ve yeniden oynatma

```
horizon = son kapanmış dakika sınırı: tüm çiftlerde o dakika barı varsa ya da now ≥ dakika_kapanış + cfg.minute_wait_s
cursor  = en küçük cursors(*,"minute")
for ts in dakikalar (cursor, horizon):                 # sırayla
    process_step(step(ts))
    if is_tf_close(ts+60s, trigger_tf) and son karar imleci < ts+60s:
        bekle: tüm çiftlerin tetik barı store'da ya da now ≥ D + cfg.bar_wait_s   (aksi dön, bir sonraki döngüde devam)
        decision_step(D)
```
- Karar adımı `D` için **dakikalar `< D` işlendikten sonra, `≥ D` işlenmeden önce** çalışır (emirler D'deki adımda dolsun diye).
- **Yeniden başlatma oynatması:** imleç → `horizon` arasındaki **tüm** dakikalar ve tf kapanışları sırayla işlenir. Oynatılan karar adımlarında girişler `stale` kapısıyla (satır 8) kendiliğinden engellenir; çıkışlar o anın verisiyle `until=D` hesaplanır (deterministik). Kaçan stop/funding PaperBroker'da aynı kodla yakalanır.
- Saat geri giderse (ardışık iki `clock.now()` negatif fark) → `ClockError`, adım işlenmez, `entries_blocked_reason="clock_skew"`.
- Feed/veri bayatsa dakika adımı ilerlemez (horizon geride kalır); girişler `stale_data` ile durur; stoplar PaperBroker'da son bilinen veriyle beklemede (feed dönünce oynatılır).

## 6. Fail-closed kuralları

### 6.1 Genel
- Her çift için hata o çifte özgüdür (`SignalFrame.status="error"`); motor çökmez, döngü sürer. Beklenmeyen istisna `process_step`/`decision_step` içinde `state.tx` geri alınır, `callback_errors` artar, `CRITICAL`; ardışık 3 hata → girişler kapanır (`entries_blocked_reason="engine_errors"`), çıkış yolu denenmeye devam eder; 10 ardışık hata → süreç çıkış kodu 3 (systemd yeniden başlatır).
- `StateError` (kilit/disk): süreç **çıkar** (durumu yazamayan motor çalışmaz; paper stopları feed dönünce yeniden oynatılır).

### 6.2 Gün başı (`ensure_day_start(ts)`)
`date(ts)` ≠ `kv["day_start_date"]` ise: `kv["day_start:<yeni>"] = broker.account().wallet` ve `kv["day_start_date"] = yeni`. Her adımın başında çağrılır (funding/komisyon o adımda işlenmeden önce).

### 6.3 Çıkış güvenliği
- Çıkışlar `ledger`, `veto`, `kill`, `stale`, `entries_blocked_reason` kapılarına **bağlı değildir**.
- Veri boşluğunda (çerçeve `ok` değil) discretionary çıkışlar atlanır **ama** `evaluate_exit` her ok çerçevede tüm `E..son` barları yeniden değerlendirdiğinden kaçan `target`/`time_stop` bir sonraki ok çerçevede yakalanır; `force_exit` **yalnızca** pozisyon çıkış verisi (setup/initial_stop/entry_bar_open) eksikse verilir (TraderV1 aynı ayrım).
- Koruyucu stop her açık pozisyonda duruyor olmalıdır: mutabakat (§7) aksini bulursa kurar, kuramazsa kapatır.

## 7. `reconcile.py` — paper alt kümesi

```python
@dataclass(frozen=True)
class ReconcileReport: ok: bool; fatal: bool; actions: tuple[str, ...]; findings: tuple[str, ...]
class Reconciler:
    def __init__(self, cfg, broker, state, ledger, orders, clock)
    def run(self, now: datetime) -> ReconcileReport
```
Çalışma: başlangıçta, her karar adımında, canlı döngüde pozisyon açıkken `reconcile_open_s` (15 sn), değilken `reconcile_flat_s` (60 sn). Backtest'te yalnız başlangıçta ve sonda.

| Durum (paper) | Eylem |
|---|---|
| Broker'da pozisyon var, state'te kayıt yok | İşlem **yapma**; `entries_blocked_reason="reconcile_unknown_position"`; `CRITICAL`; `fatal` |
| State'te `open` pozisyon var, broker'da yok | Olay türetilemez (paper'da kuyruk state ile aynı tx) → `entries_blocked_reason="reconcile_state_orphan"`; `CRITICAL`; `fatal` (paper'da bu bir **hata** sayılır) |
| Pozisyon var, duran stop yok | `place_initial_stop`/`replace_stop` ile kur; olmazsa piyasada kapat |
| Pozisyon qty ≠ stop qty | Stop miktarını pozisyona eşitle (yeni stop + eski iptal), uyarı |
| Yetim reduceOnly emir (pozisyon yok) | İptal |
| `pending`/`unknown` emir | `orders.resolve_unresolved()` |
| Ledger'da açık işlem (`list_open_trades`) var, state'te yok | `entries_blocked_reason="reconcile_ledger_orphan"`; uyarı |
| State'te açık, ledger'da giriş yok (outbox boş değil) | `drain_outbox`; başarısızsa kapı `unledgered_trades` (defter kendi bayrağı) |
| `ledger.find_unledgered_trades([state açık trade_id'ler])` | Her çalışmada çağrılır (sonuç defter kapısını günceller, §1 madde 4) |

`entries_blocked_reason` temizleme: otomatik **yok**; mutabakat bir sonraki çalışmada nedeni artık görmüyorsa (`ok`) ve neden `reconcile_*` ya da `stop_failed`/`order_unknown`/`exit_unknown` ise temizler ve `INFO` yazar; `day_start_missing` UTC gün sonunda; `clock_skew` saat düzelince.

## 8. `killswitch.py` ve `status.py`

### 8.1 Kill
```python
class Killswitch:
    def __init__(self, path: str, clock: Clock)
    def active(self) -> bool                  # dosya var mı (içerik önemsiz); okuma hatası -> True (fail-closed)
    def info(self) -> dict | None             # {"at","by","reason"} serbest JSON; bozuksa {"raw": ...}
    def set(self, by: str, reason: str) -> None     # fileio.atomic_write_json (CLI `kill`)
    def clear(self) -> None
```
Engine davranışı: `kill.active()` ilk gözlemde `kv["kill_seen_at"]` yazılır; **her karar adımı ve her dakika adımı başında** denetlenir. Etkin iken: (1) tüm yeni girişler kapalı (kapı 7); (2) `open` her pozisyon için `submit_exit(pos, "force_exit")` (bir kez; `closing` olanlara dokunulmaz); (3) çıkış doldukça `cancel_resting`; (4) düz kalınca `status.kill_state="flat"`. Kill dosyası kalkınca girişler bir sonraki karar adımında yeniden açılır (`kill_seen_at` temizlenir). İdempotent: kill sürerken yeniden başlatma aynı sonucu verir. Dosya okunamazsa `active() = True`.

### 8.2 `status.json` (atomik; `fileio.atomic_write_json`)

```json
{"schema":"engine-status/1","bot":"learner","mode":"paper","pid":1234,"started_at":"...Z","loop_at":"...Z",
 "last_minute_ts":"...Z","last_decision_bar_close":"...Z","last_candle_open":"...Z","trigger_tf":"1h",
 "param_version_id":1,"strategy":{"name":"price_action_v1","version":"1b.0"},"entries_open":true,"gate":{"ok":true,"code":"ok"},"kill":false,"kill_state":null,
 "entries_blocked_reason":null,"dry_run":true,
 "wallet":1000.0,"equity":1000.0,"day_start_equity":1000.0,
 "open_positions":[{"trade_id":1,"pair":"BTC/USDT","side":"long","qty":6.369,"entry_price":100.02,"stop":98.0}],
 "open_trade_ids":[1], "ml":null,
 "counters":{"callback_errors":0,"data_gaps":0,"ledger_errors":0,"unknown_orders":0,"mark_fallbacks":0,"minute_gaps":0,"funding_missing":0,"exit_data_gap":0}}
```
`StatusWriter(path, clock, cfg)`: `write(engine)` döngüde en çok `loop_sleep_s` aralıkla; yazma hatası döngüyü bozmaz (`WARNING`). `last_candle_open` = son kapanmış tetik barı açılışı (veri kaynağından). `loop_at` her döngüde güncellenir (kalp atışı). `health_run` eşlemesi (ayrı iş): `ApiProbe(ping_ok = (şimdi − loop_at) ≤ 120 sn, last_process_at = loop_at, last_candle_open, open_trade_ids, dry_run)`. Ayrıca `fileio.heartbeat_write` ile `kalp_atisi.json` (başlangıç/önceki kesinti bilgisi; 07) aynı dizine yazılır.

## 9. `cli.py` / `__main__.py`

`python -m trader_engine <komut>`:

| Komut | İş | Çıkış kodu |
|---|---|---|
| `feed [--config]` | 01 `Feed.run_forever` | 0, 3 (tekrarlayan hata) |
| `run --bot <learner veya twin> [--config-dir config]` | `build_engine` + `start` + `run_forever` | 0, 3 |
| `init-ledger --bot X [--reason paper_start] [--strategy NAME]` | Defter yoksa oluşturur, `init_params(DEFAULT_SIGNAL_PARAMS, reason="strategy:<ad>@<sürüm>")` (§13.6); `twin` için öğrenen defterinin **aynı** `params_hash`'i doğrulanır (uyuşmazlık → çıkış 4); var olan etkin parametreye dokunmaz | 0, 4 |
| `backtest …` | 06 | 06'da |
| `reconcile --bot X` | tek seferlik mutabakat raporu (salt okunur broker durumu) | 0, 5 (bulgu var) |
| `kill [--clear] [--by X] [--reason Y]` | `Killswitch.set/clear` | 0 |
| `rules-snapshot` | 01 işlevi: exchangeInfo → `rules` tablosu (+ `history_dir/rules.json`) | 0 |
| `smoke` | Faz B; "faz_b" mesajı | 2 |

## 10. Elle doğrulanabilir örnekler

1. **Giriş (örnek A, `D = 2026-12-01T09:00Z`, 1h, BTC/USDT long T1):** `planned_entry=100.00`, `planned_stop=98.00`; kapılar 0–10 geçti; `check_entry`: `equity=1000`, `day_start=1000`, açık pozisyon yok ⇒ `qty=6.369`, `notional=636.9`, `margin=212.3` (`size_position` çıktısı `212.29999999999998`), `risk_amount=13.999062`; likidasyon güvenliği: `|100−67.0667| = 32.93 ≥ 1.5×2` ✓. `DecisionEvent`: `final_action="entered"`, `veto_status="allowed"`, `veto_reason="ok:2026-12-01T08:50:03.120Z"`, `risk_allowed=True`, `size_qty=6.369`, `leverage=3`, `bar_close_ts=09:00Z`. Sıra: `record_decision` → state tx (`positions` `opening`, `decided`, `orders` `pending`) → `market_order`. 09:00 adımında dolum `100.02`; `place_initial_stop(98.00)`; ledger `TradeEntry(entry_price=100.02, qty=6.369, leverage=3, fee_entry=0.31851369)`.
2. **Aynı mum ikinci kez:** `decision_step(09:00Z)` yeniden çalışırsa (yeniden başlatma) `state.is_decided` ⇒ `ignore`; `decided` yazılmamış ama ledger'da karar varsa (çökme) ⇒ aynı içerikle idempotent id, farklı içerikle `LedgerConflictError` ⇒ giriş yok (TraderV1 ile aynı).
3. **Risk reddi (günlük bütçe):** `day_start=1000`, `equity=960` (bugünkü kayıp 40), açık risk 0, yeni risk 13.999 ⇒ `40 + 0 + 13.999 > 0.05×1000 = 50`? `53.999 > 50` ⇒ `check_entry` reddeder (`risk_reason` günlük bütçe) ⇒ `skip`, `skip_reason="risk_denied"`, `veto_status="allowed"`, `risk_allowed=False`.
4. **Veto engeli:** `lookup.status="blocked"`, `reason="funding asiri negatif"` ⇒ `skip_reason="veto_blocked"`, `veto_status="blocked"`, `risk_allowed=None`; `risk.check_entry` **çağrılmaz**.
5. **Bayat veri:** `D = 09:00Z`, `clock.now() = 10:30Z` (`1.5h > 1×1h`) ⇒ satır 8: `skip_reason="other"`, `veto_reason="gate:stale_data"`; aynı anda açık pozisyonun çıkış değerlendirmesi **yapılır**.
6. **Kill:** `shared/KILL` var ⇒ girişler `entry_gate_closed / gate:kill`; açık long `force_exit` piyasa çıkışı; ledger `exit_reason="force_exit"`.
7. **Çıkış önceliği (aynı adımda):** T1 long, `regime_last="trend_down"` ve iz-stop yükselişi birlikte ⇒ yalnız `regime_flip` çıkışı (stop güncellemesi **yapılmaz**).
8. **Çökme sonrası oynatma (1h tf):** (a) imleç `10:00Z`, `now=10:07Z` ⇒ dakikalar `10:01…10:06` işlenir, tf kapanışı olmadığından karar adımı yok. (b) imleç `10:58Z`, `now=11:03Z` ⇒ `10:59` dakikası işlenir, sonra `decision_step(11:00Z)` (bayat değil: `11:03 − 11:00 = 3 dk ≤ 1 sa`), ardından `11:00…11:02` dakikaları işlenir (D'de verilen emirler `11:00` adımında dolar). (c) imleç `10:58Z`, `now=13:05Z` ⇒ `11:00`, `12:00`, `13:00` karar adımları sırayla oynatılır; `11:00` ve `12:00` için girişler `stale_data` ile engellenir (çıkışlar o `D`'nin verisiyle değerlendirilir), `13:00` bayat değildir.
9. **Eş zamanlı iki giriş:** aynı karar adımında BTC ve ETH sinyali; BTC önce `enter` (risk 13.999, teminat 212.3) ⇒ ETH `check_entry` açık risk toplamını (`13.999 + yeni`) ve teminatı görür; `max_open_risk 60`, `max_same_dir_risk 40` içinde ⇒ ikisi de girer; üçüncü long için aynı yön riski `3×14 = 42 > 40` ⇒ `risk_denied`.
10. **Strateji kayıt defteri / yükleyici (§13.2):** (a) `get_strategy("price_action_v1")` ⇒ `info.name == "price_action_v1"`, `info.version == "1b.0"`, `info.setups == ("T1",)`. (b) `get_strategy("../../evil")`, `get_strategy("a.b")`, `get_strategy("")`, `get_strategy("PriceAction")` ⇒ `StrategyError(code="bad_name")`; hiçbir `import` çalışmaz (`sys.modules` aynı kalır). (c) `get_strategy("price_action_v2")` ⇒ `StrategyError(code="unknown_strategy")`, mesajda `("price_action_v1", "price_action_v1_full", "price_action_v1_ml")`. (d) `cfg.strategy` verilmemiş ⇒ `"price_action_v1"`. (e) `mode="paper"` ve `cfg.strategy="price_action_v1_full"` ⇒ `StrategyError(code="paper_not_allowed")` (`info.paper_allowed=False`; yalnız backtest/çapraz doğrulama).
11. **`PriceActionV1` (v1b) adaptörü (§13.4), `D = 2026-12-01T09:00Z`, BTC/USDT:** ham `compute_signals` son satırı (a) T1 long, `signal=True`, `planned_entry=100.00`, `planned_stop=98.00` ⇒ adaptör çıktısı **birebir aynı satır**; §10 örnek A akışı aynen sürer. (b) R1 short, `signal=True`, `planned_entry=105`, `planned_stop=106.5`, `planned_target=101` ⇒ `signal=False`, `skip_reason=None`, `setup="R1"` korunur, `reasons` `"v1b:r1_disabled|"` ile başlar; kapı satır 1b ⇒ `ignore` (kayıt yok); sayaç `shadow_r1 += 1`. (c) R1 satırı `skip_reason="stop_width"` ise de aynı (kapı satır 1'e **girmez**). (d) `validate_params({... "trigger_tf":"15m"})` ⇒ `ValueError` (v1b yalnız `"1h"`); etkin parametrede `15m` ise `params_ok=False`, kapı satır 4 (`gate:params_unavailable`). (e) **Aynı mumda yeniden giriş:** ham T1 long `signal=True`, sinyal barı `[10:00, 11:00)`; `ctx.last_exit = (10:20Z, "stop")` ⇒ satır nötrlenir (`reasons` `"v1b:same_bar_reentry|"`, sayaç `shadow_reentry += 1`); `(09:55Z, "stop")` ⇒ geçer (bar dışı); `(10:20Z, "target")` ⇒ geçer (yalnız `stop`/`trail_stop` engeller); `last_exit=None` ⇒ geçer.
12. **1l3a adaptör eşlemesi (taslak, Faz A dışı; §13.5):** 1l3a satırı `yon=1`, `stop=98.5`, `hedef=103`, kapanış `100.0`, `atr14=1.0` ⇒ `side="long"`, `planned_entry=100.0`, `planned_stop=98.5`, `stop_dist_atr=|100−98.5|/1.0=1.5` (`[0.5, 2.0]` içinde), `planned_target=103`, `rr=(103−100)/1.5=2.0`. Boyut: stratejinin kendi risk kuralı (ör. `%5`) **yok sayılır**; qty §10 örnek A ile aynı yoldan (`risk.check_entry`) çıkar. `yon=1` ve `stop=NaN` ya da `stop=101` (yanlış taraf) ⇒ satır nötr (`signal=False`, `skip_reason=None`), sayaç `adapter_invalid_stop`; `stop_dist_atr=2.4` ⇒ `signal=False`, `skip_reason="stop_width"` (v1 sabitleri; kapı satır 1).

## 11. Kabul senaryoları (test ajanı için)

Kapı zinciri: §4.1 tablosunun **her satırı** için bir test (kayıt alanları ve `mark_decided` davranışı dahil); `entered` kaydı yazılamazsa emir yok; `LedgerConflictError` yolu; çıkış kapıdan bağımsızlığı (ledger `degraded`, veto yok, kill, bayat iken çıkış çalışır); karar adımı sırası (exit → stop_update → entry) ve aynı adımda rezerve risk; `FileVeto` bayat/imzasız/anahtarsız ⇒ giriş yok; `SignalFrame` durumları (`no_history`, `data_gap`, `error`; backtest `strict` yayılır); `WindowedSignalSource` ≡ doğrudan `compute_signals` (kesilmiş veriyle: aynı satır); `run_range` flat optimizasyonu ≡ tam adım adım (06 ile ortak); `process_step` iki aşama sırası (giriş dolumu → stop → aynı adımda tetik); yeniden başlatma oynatması (her adımda öldürme: dakika ortası, karar ortası, `orders.pending` sonrası — kod yolları `FaultPlan` ve state tx geri alma ile; sonuç kesintisiz çalışmayla **bit-bit aynı** ledger+state); tek karar anahtarı kalıcılığı; kill (set, idempotent yeniden başlatma, clear, okunamayan dosya ⇒ aktif); mutabakat tablosunun her satırı; `status.json` şeması ve atomikliği (yarım dosya okunmaz); `ensure_day_start` (gün sınırı, yeniden başlatma, `day_start_missing`); TraderV1 §2.8 eşleme tablosunun her satırı için "karşılık var" testi (eksik davranış listesi).

Strateji arayüzü (§13): yükleyici örnekleri (§10.10) ve `bad_name` yolunda hiçbir dinamik import olmadığı (kaynak taraması: `strategies/` dışında ve `registry.py` içinde `importlib`/`__import__`/`exec`/`eval`/`getattr`-ile-modül-yükleme yok); `PriceActionV1` v1b nötrleme kuralları (§10.11 a–e); `price_action_v1_full` çıktısı `WindowedSignalSource` ≡ doğrudan `compute_signals` (§11 ilk eşitlik testinin v1 koşulu); `PriceActionV1.info.param_specs` ≡ `ledger.PARAM_SPECS`/`LESSON_*` (ad, aralık, adım, kapsam, `lesson_adjustable`); `validate_table` her ihlal sınıfı için (fazla/eksik sütun, `side` geçersiz, long'da `stop ≥ entry`, `setup ∉ info.setups`, `signal=True` iken sonlu olmayan fiyat) ⇒ `SignalFrame(status="error")`, çift için giriş yok, çıkışlar etkilenmez; strateji `compute`'u lookahead'li (kesme testi, 06 §6) ⇒ kırılır; kapı zinciri (§4.1) farklı bir strateji (sahte `FakeStrategy`) ile **aynı** sonuçları verir (strateji kapı kararını etkileyemez); ledger uyumsuzluğu (`ledger_incompatible`) ve strateji/sürüm uyuşmazlığı (`strategy_mismatch`) başlatmayı reddeder; açık pozisyon varken strateji değişikliği ⇒ başlatma reddi.

## 12. Belirsizlikler ve çözümleri

- **Giriş fiyatı referansı (`entry_ref`)** native'de `planned_entry`; gerçek dolum bir adım sonra olduğundan boyut dolum sonrası doğrulanır (04 §5.2). Fark ≤ 2 bp kayma + bir dakikalık hareket; hedef risk 1,4 % ile tavan 2 % arasında 0,6 puanlık tampon vardır.
- **Karar anı gecikmesi:** feed `grace_s=3` + yoklama; tipik karar `D + ~5 sn`. `stale_factor=1` ⇒ 1 tf tolerans (TraderV1 `_stale` ile eşdeğer).
- **Twin:** aynı süreç türü, farklı `--bot`; her zaman `PaperBroker`; gecikmeli başlar (`start_delay_s`). Ledger/state/status ayrı dosyalar; `market.sqlite` ortak salt okunur.
- **`minute_wait_s`** yeni yapılandırma alanıdır (varsayılan 20 sn; 02 `EngineConfig`).

## 13. Takılabilir strateji arayüzü (kullanıcı kararı, 16 Kasım 2026)

**Karar:** strateji motorun takılıp çıkarılabilir bir parçasıdır; v1b ilk takılan stratejidir; ileride 1l3a stratejileri ve başkaları aynı arayüzle denenir. **Değişmeyenler:** §4.1 kapı zinciri ve sırası, `risk.check_entry(…, LOCKED_CFG)` tek risk kaynağı, çıkışların kapısızlığı, fail-closed kuralları, `target_mode="bar_close"`, ledger yazım kuralları, kill/status. Strateji bunların **hiçbirini** göremez ya da değiştiremez; yalnızca "bu kapanmış barda şu aday var mı" sorusuna yanıt verir.

### 13.1 Sorumluluk ayrımı

| Strateji (takılan) | Motor (sabit) |
|---|---|
| Aday: `setup`, `side`, `planned_entry`, `planned_stop`, `planned_target`, `reasons` (+ rejim/özellik sütunları) | Kapı zinciri, veto, `risk.check_entry`, **boyut/kaldıraç** (her zaman `LOCKED_CFG`; stratejinin kendi boyut/kaldıraç/risk kuralı **yok sayılır**, tabloda bunun için sütun yoktur) |
| İstek: hangi tf'ler, kaç bar ısınma, hangi parametreler (sınırlarıyla) | Veri penceresi tedariki (`MarketView`, `until=D`), `no_history`/`data_gap` kontrolü |
| (İsteğe bağlı) çıkış politikası | Koruyucu stop, `force_exit`, kill, zaman/rejim güvenlik ağı olarak `engine_default` (04 §5.1) |

### 13.2 Protokol ve kayıt defteri (`strategies/base.py`, `strategies/registry.py`)

```python
@dataclass(frozen=True)
class ParamSpec:                          # ledger.PARAM_SPECS satırının strateji-bağımsız biçimi
    name: str; kind: Literal["float","int","choice"]
    lo: float | None; hi: float | None; choices: tuple | None; default: object
    lesson_adjustable: bool               # ders servisi yalnız True olanları önerebilir
    lesson_bounds: tuple[float, float] | None    # ders sınırı (lo/hi içinde); lesson_adjustable ise zorunlu
    step: float | None                    # ders adımı
    scope: tuple[str, ...] | None         # parametrenin etkilediği setup'lar

@dataclass(frozen=True)
class StrategyInfo:
    name: str                             # kayıt anahtarı, ^[a-z][a-z0-9_]{0,39}$
    version: str                          # ör. "1b.0"; mantık değişince artar
    setups: tuple[str, ...]               # üretebileceği setup adları ("T1",)
    timeframes: tuple[str, ...]           # gereken tf'ler; "trigger" = params.trigger_tf (ör. ("trigger","4h"))
    allowed_trigger_tfs: tuple[str, ...]  # ("1h",) v1b
    warmup_bars: Mapping[str, int]        # no_history eşiği (ör. {"1h":1200,"15m":4800,"4h":300})
    window_bars: Mapping[str, int]        # çekilecek bar sayısı (≥ warmup)
    min_contiguous: Mapping[str, int]     # data_gap eşiği (ör. {"trigger":20,"4h":150})
    param_specs: tuple[ParamSpec, ...]
    paper_allowed: bool                   # False: yalnız backtest/çapraz doğrulama

@dataclass(frozen=True)
class StrategyContext:
    pair: str; D: datetime                # D = karar anı (son kapanmış tetik barının kapanışı)
    tf: str                               # çözülmüş tetik tf
    params: Mapping[str, object]          # etkin parametre sürümü (validate_params'tan geçmiş)
    bars: Mapping[str, pd.DataFrame]      # tf -> OHLC (indeks = bar açılışı, UTC, yalnız kapanmış, <= D)
    last_exit: tuple[datetime, str] | None   # bu çiftteki son kapanışın (çıkış zamanı, ExitReason); yalnız post_filter kullanır; state'ten, saf veri
    model: MlModelView | None = None      # ML-0a (19a): yüklenmiş ML modeli, SALT OKUNUR (frozen); yoksa None. Motor tedarik eder (yükleme §13.4a); strateji dosya/ağ/saat görmez

class ExitPolicy(Protocol):               # saf; aynı girdi ⇒ aynı ExitDecision; defter/veto/kill/saat yok
    def evaluate(self, pos: Position, ctx: ExitContext | None) -> ExitDecision    # 04 tipleri; reason ∈ ExitReason

class Strategy(Protocol):
    info: StrategyInfo
    def validate_params(self, m: Mapping) -> Mapping                # ValueError; ledger doğrulamasına EK, onu gevşetmez
    def compute(self, ctx: StrategyContext) -> pd.DataFrame         # SIGNAL_COLUMNS (tablo §13.3); yalnız ctx.bars/params'a bağlı
    def post_filter(self, row: pd.Series, ctx: StrategyContext) -> pd.Series   # yalnız KARAR barının satırı; durum (ctx.last_exit) gerektiren nötrleme; varsayılan: row
    def exit_policy(self) -> ExitPolicy | None                      # None = engine_default (04 evaluate_exit)
```

**Çıkış kancası:** `exit_policy() is None` ⇒ motor 04 `evaluate_exit`'i (trail / hedef / zaman / rejim) kullanır (`PriceActionV1` böyledir). Dönerse `ExitPolicy.evaluate` kullanılır; **yine** (a) başlangıç stopu borsada/PaperBroker'da durur, (b) çıkış verisi eksikse `force_exit`, (c) çıkış kapısızdır, (d) `reason` yalnız `ExitReason` sözlüğünden olabilir (başka ⇒ `force_exit` ve `CRITICAL`), (e) `stop_update` yalnız stopu **sıkılaştırabilir** (long: yükselen; short: alçalan; gevşetme ⇒ yok sayılır, sayaç `exit_policy_loosen`).

**Kayıt defteri (`registry.py`):**

```python
class StrategyError(Exception): code: Literal["bad_name","unknown_strategy","paper_not_allowed","ledger_incompatible", ...]
def list_strategies() -> tuple[str, ...]
def get_strategy(name: str) -> Strategy
```
- **Statik:** kayıt `registry.py` içinde elle yazılmış `_FACTORIES: dict[str, Callable[[], Strategy]]` sözlüğüdür; `strategies/__init__.py` yalnız bu pakette bulunan modülleri **kod içinde açıkça** import eder. Yapılandırmadan, CLI'dan, ortamdan ya da ledger'dan gelen **hiçbir dize** `importlib`/`__import__`/`exec`/`eval`/`getattr` ile modül yüklemek için kullanılmaz; dosya yolu, nokta içeren ad, eklenti dizini, `entry_points` taraması yoktur.
- `get_strategy(name)`: `re.fullmatch(r"[a-z][a-z0-9_]{0,39}", name)` değilse `bad_name`; sözlükte yoksa `unknown_strategy` (mesaj izinli adları listeler); fabrika her çağrıda **yeni** örnek verir (durumsuz).
- Yeni strateji eklemek = pakete bir modül + `_FACTORIES`'e bir satır + inceleme/test; çalışma zamanında ekleme yoktur. Üçüncü taraf/1l3a kodu **kopyalanıp** (07 kopya deseni: başlık, kesinti listesi) `strategies/` altına alınır ve incelemeden geçer; yolu gösterip import edilmez.
- Seçim: `EngineConfig.strategy: str = "price_action_v1"` (`config/engine*.json:strategy`; **02'ye eklenecek alan**, §13.9). Backtest: `--strategy NAME` (06).
- **Yaşam döngüsü:** strateji **süreç başına bir** ve başlatmada seçilir; çalışırken değişmez. Açık/bekleyen pozisyon varken farklı strateji ile başlatma ⇒ **ret** (çıkış kodu 4, `strategy_change_with_open_positions`); önce pozisyonlar kapanmalı (ya da `kill`).

### 13.3 `compute` sözleşmesi ve doğrulama

- **Çıktı:** `SIGNAL_COLUMNS` (`trader_core.signals`) sütunlarının **tam** kümesi, indeks = tetik tf bar açılışı, `ctx.bars` ile aynı uzunluk. Fazla ya da eksik sütun yasaktır; bu yüzden strateji qty/kaldıraç/risk taşıyamaz.
- **Nedensellik:** satır `t`, yalnız açılışı `≤ t` olan kapanmış barlardan hesaplanır (lookahead yasağı). Doğrulama: 06 §6 kesme testi **her kayıtlı strateji** için koşar (`--strategy`).
- **Şema doğrulaması (`validate_table`, runner çağırır; ihlal ⇒ `SignalFrame(status="error")`, `callback_errors += 1`, `CRITICAL`, o çifte giriş yok):** `side ∈ {"long","short",None}`; `signal=True` ⇒ `setup ∈ info.setups`, `planned_entry/planned_stop` sonlu ve pozitif, long'da `stop < entry`, short'ta `stop > entry`, `planned_target` NaN ya da doğru tarafta; `skip_reason ∈ {None, "stop_width", "rr_below_min", "ml_filter"}` (başka kodu strateji üretemez; `ml_filter` yalnız `signal=False` nötrlemesinde, §13.4a; kapı kodları motorundur, §1 madde 3); `signal=False` satırlar kapıda yalnız satır 1/1b'ye girer.
- **`post_filter`:** runner `compute` tablosunun **son** (karar barı) satırına uygular (`SignalRow` bundan kurulur); şema doğrulaması **sonra** yeniden yapılır; `post_filter` yalnız `signal=True → False` nötrleyebilir (aday ekleyemez, fiyat değiştiremez; aksi `error`). `compute` önhesaplanıp önbelleklenebilir (backtest), `post_filter` her karar adımında çalışır.
- **Saflık:** `compute` yan etkisiz (dosya/ağ/saat/rastgelelik yok), aynı `ctx` ⇒ aynı tablo. Aynı `(pair, D, version_id)` için tek tur önbellek §3.1 madde 5 ile aynıdır.
- `row.setup`/`side`/`planned_*` kapıya ve `Candidate`'a §4.2 ile **aynı** biçimde geçer; `SignalRow`, `build_decision_event`, `Position` dondurulmuş alanları (§5.3) değişmez.

### 13.4 Adaptör `PriceActionV1` (`strategies/price_action_v1.py`)

`trader_core.signals` + `regime` çağrılarını sarar; **yeni mantık yoktur** (ham satır = `compute_signals` çıktısı). Kurucu: `PriceActionV1(setups_enabled, allowed_trigger_tfs, block_same_bar_reentry)`; kayıt defterinde iki yapılandırma:

| Kayıt adı | Yapılandırma | Kullanım |
|---|---|---|
| `price_action_v1` (**varsayılan; v1b**) | `("T1",)`, `("1h",)`, `True`; `paper_allowed=True`; `version="1b.0"` | sahte para ve canlı v1 |
| `price_action_v1_full` | `("T1","R1")`, `("1h","15m")`, `False`; `paper_allowed=False`; `version="1.0"` | yalnız backtest/çapraz doğrulama (06 §7; TraderV1 eşdeğeri) |

- `info`: `setups`, `timeframes=("trigger","4h")`, `warmup_bars={"1h":STARTUP_BARS["1h"],"15m":STARTUP_BARS["15m"],"4h":STARTUP_BARS_4H}`, `window_bars` = `WINDOW_TRIGGER`/`WINDOW_4H`, `min_contiguous={"trigger":20,"4h":150}`; `param_specs` **`trader_core.ledger.PARAM_SPECS`, `LESSON_PARAMS`, `LESSON_BOUNDS_DEFAULT`, `LESSON_STEP`, `LESSON_SCOPE`'tan türetilir** (kopya değer yok; tek doğruluk kaynağı ledger). `lesson_adjustable`: `vol_ratio_max, stop_buffer_atr, trail_atr, range_target_frac, rr_min`; kalan dördü (`range_width_atr, edge_zone_atr, pullback_ema, trigger_tf`) değil.
- `compute` = §3.1 adım 3 (`classify_series` → `align_to_base` → `compute_signals`) + **v1b nötrleme** 1 (satır düzeyi, hesap değişmez); `post_filter` = nötrleme 2:
  1. `setup ∉ setups_enabled` (v1b: R1) olan **her** satır (sinyal ya da süzülmüş aday): `signal=False`, `skip_reason=None`; `setup`/`side`/`planned_*` korunur; `reasons = "v1b:r1_disabled|" + reasons`; sayaç `shadow_r1`. (Kapı satır 1b `ignore`; defterde kayıt yok.)
  2. (`post_filter` içinde, `compute`'ta değil) `block_same_bar_reentry` ve `ctx.last_exit = (ts, reason)`, `reason ∈ {"stop","trail_stop"}`, `bar_open ≤ ts < bar_close` (sinyal barı) ise `signal=True` satırı nötrlenir: `signal=False`, `skip_reason=None`, `reasons = "v1b:same_bar_reentry|" + …`; sayaç `shadow_reentry`.
  3. Diğer satırlar **değişmeden** geçer.
- `validate_params(m)` = `SignalParams.from_mapping(m)` + `trigger_tf ∈ allowed_trigger_tfs` (15m v1b'de reddedilir).
- `exit_policy()` = `None` (04 `evaluate_exit`: T1 `regime_flip` → `trail_stop`; R1 `target` → `time_stop`).
- `last_exit` kaynağı: `strategy_runner` `state`'in kapanmış pozisyonlarından (çift başına en son) kurar; strateji `state`'e dokunmaz. (Yeniden girişin kendisi ayrıca kapı satır 2/3 ile engelli değildir; bu kural **yalnız** stratejinindir ve `position_manager`'a taşınmaz.)
- Varsayım (test doğrular): `pick_candidate` rejim ayrık olduğundan aynı barda T1 ve R1 birlikte oluşmaz; R1'in nötrlenmesi T1'i gizlemez.
- Gölge etiketler Faz A'da yalnız sayaç + `INFO` günlüğüdür; **defterde gölge kaydı** (`skip_reason`/alan) ledger sözlüğü genişlemesi ister (§13.9).

### 13.4a `price_action_v1_ml` — ML meta-etiket filtresi (ML-0a, 19a; `ml-faz-tasarimi.md` §4, §10)

Kayıt adı `price_action_v1_ml` (`strategies/price_action_v1_ml.py`; `version="1b.0-ml0"`, `paper_allowed=True`) v1b'yi (`PriceActionV1`) **sarar**: `info` (pencereler, `param_specs`, `setups`) v1b ile aynı, `exit_policy()` v1b'nin. Filtre **yalnız kaldırır**: aday ekleyemez; `planned_entry/stop/target`, boyut, kaldıraç, çıkış ve kapı zinciri değişmez (`post_filter` sözleşmesi: yalnız `signal=True → False`; runner/precomputed aksini `bad_table` sayar).

- **`ml_mode ∈ {off, shadow, active}`** (`EngineConfig.ml_mode`, varsayılan **`off`**; `config/engine.base.json`; kayıt: `get_strategy(name, ml_mode=...)`; ML'siz stratejiye `shadow/active` verilirse `StrategyError("ml_not_supported")`). `ml_model_path`: model paketi (JSON); `off`'ta okunmaz.
  - **`off`**: `compute`/`post_filter` v1b'ye **delege**; çıktı v1b ile **birebir** (test: karar akışı byte-özdeş).
  - **`shadow`**: model varsa aday satırının `reasons` başına `ml:p=<0.xxxxxx>|` (kalibre olasılık) yazılır; **hiçbir aday elenmez**. Model yok/süresi dolmuş/puanlanamamış ⇒ yalnız sayaç (`ml_no_model`, `ml_expired`, `ml_unscored`, `ml_score_errors`) ve log; işlem engellenmez.
  - **`active`**: `p < ctx.model.threshold` ⇒ satır nötrlenir: `signal=False`, **`skip_reason="ml_filter"`**, `reasons = "ml:filter|" + …`; kapı satır 1 bunu defterde `not_evaluated` karar olarak yazar (gece işi sonucunu etiketlesin; `ml_score` dolu). **Fail-closed:** `ctx.model is None` (yok/hash tutmuyor/`gate_passed≠True`/onaysız), `ctx.model.expired(ctx.D)` (21 gün) ya da aday puanlanamadıysa **yeni giriş yok** (aynı nötrleme, `reasons` `ml:no_model|` / `ml:expired|` / `ml:unscored|`); çıkışlar etkilenmez. Durum `status.json`'da görünür (aşağıda).
- **Puanlama (`compute`, saf):** yalnız `ctx.bars` ve `ctx.model`'e bağlı; özellikler `trader_core.ml_features.feature_frame` ile (**eğitim hattıyla aynı kod**; `trader_ml.features` bunu sarar ve kilitli dönem korumasını ekler) üretilip `model.score` ile puanlanır. Canlıda yalnız **karar barının** adayı puanlanır (`score_history=False`; ön hesaplı backtest tüm adayları puanlamak için `True` yapar). `post_filter` yalnız `reasons`taki `ml:p=` etiketini ve `ctx.model.threshold`/`expired(ctx.D)`'yi okur (precomputed yolunda `bars={}` olsa da çalışır).
- **Bilinen sınırlar (v0):** (1) BTC/ETH ve fonlama özellikleri canlıda `NaN` (`StrategyContext` tek çiftin mumlarını taşır; model bu sütunlarda `NaN`'a dayanıklı eğitilmeli). (2) `f_bars_since_exit` tablo düzeyindedir (`compute` `last_exit` görmez) ⇒ canlıda `NaN`. (3) Özellikler varsayılan `SignalParams` ile üretilir (eğitimle aynı). (4) 1g eğimi ATR(14) özyinelemeli olduğundan 1500 saatlik canlı pencerede eğitim değerinden ≤ ~%2 sapar (eşlik testi toleransı); kalıcı çözüm eğitimin de aynı pencereyle özellik üretmesidir (ML-1).
- **Model yükleme (motor tarafı, `trader_core.ml_package`; `trader_ml` import edilmez):** `build_engine`, `ml_mode != off` iken `load_engine_model(cfg.ml_model_path, ml_mode, now)` çağırır → `MlModelView` ya da `(None, hata_kodu)`. Kurallar `trader_ml.package.load_package` ile aynıdır (kod oradan buraya taşındı): `meta.gate_passed is True` ve `threshold` dolu (aksi ret), `model_hash`/`feature_list_hash` tutmalı, **21 gün** (`meta.expires_at` ile `created_at+21g`'ün erkeni), `meta.features == FEATURE_NAMES`; `active` ayrıca `meta.user_approved is True` ister. Ağaç okuyucu `trader_core.ml_eval` (numpy). Yükleme başlatmada bir kez yapılır (sıcak yükleme ML-3 işi; şimdilik yeniden başlatma).
- **Görünürlük:** `status.json` `"ml": {"mode","state":"off|ok|no_model|expired","model_id","threshold","expires_at","error","entries_blocked"}` (ML'siz strateji ⇒ `null`). `active` ve `no_model|expired` iken `entries_blocked=true`, `entries_open=false`, `gate={"ok":false,"code":"ml_no_model"|"ml_expired"}`. Sayaçlar `status.counters`'a girer (`ml_filter`, `ml_pass`, `ml_shadow_scored`, …).
- **Backtest notu:** `precomputed.py` henüz `ctx.model` geçirmez ⇒ backtest'te ML modu `off` kalır (active olursa tüm girişler elenir = fail-closed). Model taşıyan backtest, `PrecomputedSignalSource`'un iki `StrategyContext` çağrısına `model=` eklenmesiyle (06 sahibi) açılır; bu iş 19b'ye bağlıdır.
- **Değişmeyenler:** §4.1 kapı zinciri ve sırası, LLM vetosu, `risk.check_entry`/`LOCKED_CFG`, boyut/kaldıraç (model puanı boyutu **etkilemez**), çıkışların kapısızlığı, kill.

### 13.5 1l3a stratejisinin uyarlanması (taslak; Faz A kapsamı dışı, arayüz bunu mümkün kılar)

Kaynak şekil (`1l3a-proje/motor/strateji/temel.py`, salt okunur): `Strateji.sinyaller(mumlar)` mum kapanışında **vektörel**, aynı indeksli `yon` (1/−1/0), `stop`, `hedef` (NaN olabilir), `cikis`/`cikis_long`/`cikis_short`, `zaman_cikisi_mum` döner; `varsayilan_parametreler` + `parametre_izgarasi`; işlem sonraki mum açılışında. Adaptör deseni (`strategies/_1l3a_adapter.py`, her 1l3a stratejisi için ince alt sınıf, kopyalanmış kaynak `strategies/vendor_1l3a/` altında):

| 1l3a | Bizim aday yapımız |
|---|---|
| `yon` 1/−1 (0 ⇒ satır boş) | `side` long/short, `signal=True` |
| `stop` (yon≠0 için zorunlu) | `planned_stop`; NaN ya da yanlış taraf ⇒ satır nötr, sayaç `adapter_invalid_stop` |
| `hedef` | `planned_target` (NaN ⇒ `None`); `rr = |hedef−giriş|/|giriş−stop|` |
| (yok) | `planned_entry` = sinyal barı kapanışı (motor sözleşmesi, §4.2); 1l3a "sonraki açılış" kuralı yerine motorun dolum modeli geçerlidir |
| (yok) | `stop_dist_atr` = `|giriş−stop| / ATR14(tetik tf)`; `[STOP_DIST_MIN_ATR, STOP_DIST_MAX_ATR]` dışı ⇒ `skip_reason="stop_width"` (v1 sabitleri; kapı satır 1) |
| strateji/kart adı | `setup` (ledger sözlüğü genişlemesi şartıyla, §13.9); `reasons` = `kart_id` + tetikleyen koşullar |
| `pozisyon_risk`, kaldıraç, miktar, `CikisAyarlari.yalniz_karda_cikis`… boyut/risk alanları | **Yok sayılır.** Boyut ve kaldıraç **her zaman** `risk.check_entry` + `LOCKED_CFG`; adaptör bunları taşıyacak sütun üretmez |
| `varsayilan_parametreler` + `parametre_izgarasi` | `param_specs` (`lesson_adjustable=False` başlangıçta; ders yetkisi ayrı mentor kararı) |
| `funding_gerekli` | `info` bayrağı (Faz A dışı); veri `MarketView.funding` ile |
| `cikis`/`cikis_long`/`cikis_short`, `zaman_cikisi_mum`, `hedef` | `ExitPolicy`: sinyal çıkışı ⇒ `exit "other"` (sözlükte uygun ad yoksa), `zaman_cikisi_mum` ⇒ `"time_stop"`, `hedef` ⇒ `"target"` (bar_close kuralı); iz süren stop için `engine_default` ya da kendi `stop_update` (yalnız sıkılaştırma) |

Çıkış sütunlarının `ExitContext`'e taşınması (`exit_long/exit_short` son bar bayrakları) 04 `ExitContext` genişlemesi ister; bu yüzden uyarlama Faz A sonrasıdır. Stratejiler 1l3a'nın `ADAY_RAPORU`/`final_set` sonuçlarına göre seçilir; her biri **önce backtest'te** (`--strategy`) ve çapraz doğrulama/lookahead kilidinden geçmeden paper'a alınmaz.

### 13.6 Ledger ve ders servisi bütünleşmesi

- **Her karar kaydında strateji adı + sürüm:** her `DecisionEvent`/`TradeEntry` zaten `param_version_id` taşır; Faz A'da `param_versions.reason` (`init_params`) `"strategy:<ad>@<sürüm>"` ile başlar (`init-ledger --bot X [--strategy NAME]`, §9). Karar → `param_version_id` → `reason` zinciri adı+sürümü verir. `status.json` ve `kv["strategy"]` aynı değeri taşır. Ledger'a ayrı `strategy_name/strategy_version` alanı eklemek (append-only şema) `trader_core` değişikliğidir (§13.9).
- **Başlatma doğrulaması (fail-closed):** `ledger.get_active_params()` anahtar kümesi `{p.name for p in info.param_specs}` ile eşit ve `reason` etiketi `strategy:<ad>@<sürüm>` ile uyumlu olmalı; etiket yoksa (eski varsayılan) `price_action_v1` sayılır. Anahtar uyuşmazlığı ⇒ `StrategyError("ledger_incompatible")`, çıkış kodu 4; yalnız **sürüm** uyuşmazlığı ⇒ girişler kapalı (`entries_blocked_reason="strategy_mismatch"`), çıkışlar çalışır; `init-ledger --reason strategy_update` ile yeni parametre sürümü/etiket açılana dek.
- **Ders servisi** yalnız **etkin stratejinin** `param_specs`'inde `lesson_adjustable=True` olan parametreleri ve `lesson_bounds`/`step`/`scope` sınırları içinde önerebilir; v1b için bu küme `ledger.LESSON_PARAMS`'tır (ledger'ın mevcut doğrulaması ayrıca zorlar; strateji sınırı **gevşetemez**, yalnız daraltır). Beyan edilmeyen parametre ⇒ öneri reddi. Dondurulmuş pozisyon alanları (§5.3) ders değişse de etkilenmez; `strategy_name/version` da giriş anında pozisyona dondurulur (**04 `Position`'a alan: §13.9**) ve çıkışı o strateji yönetir.

### 13.7 Backtester (06) ile ilişki

`python -m trader_engine backtest --strategy NAME` (varsayılan `price_action_v1`): `PrecomputedSignalSource` `strategy.compute`'u çift başına bir kez çalıştırır; `WindowedSignalSource` (paranoid) aynı `strategy` ile; lookahead kesme testi ve çapraz doğrulama **seçilen** strateji için koşar. `--params` `strategy.validate_params`'tan geçer. Strateji adı+sürüm `summary.json`'a ve backtest ledger `init_params` etiketine yazılır. Ledger sözlüğüyle uyumsuz strateji backtestte de `ledger_incompatible` verir (backtest ledger'ı aynı `trader_core.ledger`; sözlük genişleyene dek yalnız `price_action_v1*` çalışır).

### 13.8 Değişmezler

1. Kapı zinciri, `risk.check_entry`, çıkış kapısızlığı, `bar_close`, kill/stale davranışı strateji **değişse de** bit-bit aynıdır (`FakeStrategy` ile test).
2. Strateji boyut/kaldıraç/emir/ledger/state/saat/ağ görmez; yalnız `StrategyContext` (saf veri) alır.
3. Strateji adı yalnız statik kayıt defterinden çözülür; güvenilmeyen girdiden kod yüklenmez.
4. Çalışma zamanında strateji değişmez; açık pozisyon varken değiştirilemez.
5. Aynı `(strateji, sürüm, parametre sürümü, veri)` ⇒ aynı aday tablosu (paper ↔ backtest eşitliği, §3.1 açık nokta kuralları).

### 13.9 Diğer birimlere etkiler (mentor onayı gerekir; bu belge onların dosyalarını değiştirmez)

| Birim | Gerekli değişiklik | Faz A'da zorunlu mu |
|---|---|---|
| 02 `config.py`, `config/engine*.json` | `EngineConfig.strategy: str = "price_action_v1"` (+ doğrulama: `^[a-z][a-z0-9_]{0,39}$`) | Evet |
| 04 `Position`/`state` | dondurulmuş `strategy_name`, `strategy_version` alanları (ve `ExitPolicy` için ileride `ExitContext` genişlemesi) | Alan: evet; `ExitContext` genişlemesi: hayır |
| 06 | `--strategy` bayrağı, `PrecomputedSignalSource(strategy)`, özet/ledger etiketi (§13.7) | Evet |
| 08 | `test_engine_module_inventory` modül listesine `strategies/{__init__,base,registry,price_action_v1}.py`; `importlib`/`__import__` taraması `strategies/` için ek korumaya (§13.2) | Evet |
| `trader_core.ledger` (dokunulmaz; ayrı iş) | `_SETUPS` ve 9 anahtarlı `PARAM_SPECS` v1'e özgüdür; v1 dışı strateji için setup sözlüğü + parametre şeması genişlemesi, ayrı `strategy_name/version` alanları, gölge etiket kaydı | **Hayır**; 1l3a uyarlaması bunu bekler |

## Netleştirmeler
- **Hedef işlem riski (kullanıcı kararı 16 Kasım 2026: canlı %0,5):** `EngineConfig.target_trade_risk` (isteğe bağlı anahtar, varsayılan `LOCKED_CFG.target_trade_risk = 0.014`; backtest davranışı değişmez). `EngineConfig.risk_config` bunu `trader_core.risk.tightened(LOCKED_CFG, …)` ile kurar: yalnız `0 < değer ≤ 0.014` kabul; gevşek, ≤ 0, NaN/inf, bool, sayı olmayan ⇒ `ConfigError` (yükleme anında, fail-closed). Giriş kapısı (kapı 11 ve boyut) tek bu nesneyi kullanır; twin ve learner aynı `engine.base.json`'dan okuduğundan aynı değeri alır (bot dosyaları bu anahtarı **taşımaz**). Gönderilen `config/engine*.json` dosyaları varsayılanda bırakıldı; canlı %0,5 için `target_trade_risk: 0.005` `engine.base.json`'a (her iki botu birlikte etkiler) canlı geçişte yazılır. Dolum sonrası doğrulama (`max_trade_risk`) kilitli kalır.
- **`entries_blocked_reason` ve karar adımındaki mutabakat:** her karar adımı mutabakatı çalıştırır (§7); mutabakat nedeni artık görmüyorsa `order_unknown`/`exit_unknown`/`stop_failed`/`reconcile_*` otomatik temizlenir, `day_start_missing` yeni UTC gününün `ensure_day_start`'ında temizlenir. Kapı 6 testleri bu temizlemeyi bilerek devre dışı bırakır; temizleme davranışı §7 tablosuyla uyumludur (belirsizlikte kapalı kalınır: neden hâlâ görülüyorsa temizlenmez).
- **`status.write` kısıtı:** yazma en çok `loop_sleep_s` aralıkla yapılır (§8); `force=True` yalnız karar adımı sonunda kullanılır.
- **Defter özellik zorunluluğu:** `DecisionEvent.features` sonlu değerler ister (T1: `atr_tf, stop_dist_atr, atr_4h, pullback_ema, ema_value, body_ratio`; R1: `wick_ratio, rr, edge_dist_atr`, ayrıca `planned_target`). Eksik/NaN ⇒ karar kaydı reddedilir; motor girişi **yapmaz** (zorunlu kayıt yazılamazsa emir yok; fail-closed), filtrelenmiş aday kaydı best-effort atlanır.

## Kâğıt gecikme kaydı (yalnız kayıt)
Kâğıt kipinde giriş dolumunda `dolum_gecikme_sn` = enjekte saat − karar mumu kapanışı (`signal_bar_close_ts`); motorun kararıyla verilen piyasa çıkışında `cikis_gecikme_sn` = enjekte saat − çıkışı tetikleyen mum kapanışı. Saniye (float, ≥ 0, 3 hane); zaman bilinmiyorsa alan yazılmaz; durdurma/hedef gibi dinlenen emir dolumlarında çıkış gecikmesi yoktur. Karar satırı dolumdan önce yazıldığı ve defter yalnız-ekleme olduğu için değerler defter şemasına girmez: motor durum veritabanında `gecikme:<trade_id>` kv satırında durur. Karar, risk ve sıralamayı etkilemez.
