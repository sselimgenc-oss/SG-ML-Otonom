# 02 — Ortak tipler, saat, bar aritmetiği, yapılandırma (spesifikasyon v1, 16 Kasım 2026)

Kaynak kararlar: `otonom-trading-arastirma/motor-tasarimi.md` §1.0 (dış çerçeve yasağı), §2.2 (`types.py`, `clock.py`, `config.py`), §2.3 (Broker arayüzü tipleri), §2.5 (maliyet modeli), §3.1 (Faz A kapsamı). Bu birim **diğer tüm birimlerin ortak sözleşmesidir**: buradaki dataclass alanları ve fonksiyon imzaları donmuştur; değişiklik mentor onayı ve etkilenen birimlerin şartname revizyonu gerektirir. Bu belge kod, test ve commit içermez.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Kanonik çift biçimi | `"BTC/USDT"` (büyük harf, `:` sonrası atılmış). `risk._norm_pair`, `ledger._norm_pair`, `veto.pair_key` ile aynı sonucu verir. Borsa sembolü `"BTCUSDT"`; feather kökü `"BTC_USDT_USDT"` (freqtrade adlandırması) |
| Zaman | Her yerde tz-aware UTC `datetime`. SQLite'ta epoch **milisaniye** (`int`). Saat dilimsiz `datetime` her yerde `ValueError` |
| Sayılar | Motor içi `float`; borsa sınırında `Decimal` (`exchange/rules.py`, Faz B). Her fiyat/miktar sonlu ve `> 0` olmalı (NaN/inf/bool/None → ret) |
| Saat | `datetime.now()`, `datetime.utcnow()`, `time.time()`, `time.sleep()` yalnızca `clock.py` içinde. Başka her yer `Clock` enjekte alır (test: `08-no-framework-guard.md`) |
| tf aritmetiği | Saf standart kütüphane (`bars.py` pandas/numpy import **etmez**; feed süreci pandas yüklemez, bkz. `01-feed.md`) |
| Risk sayıları | Bu pakette **hiçbir risk sabiti tanımlanmaz**; yalnızca `trader_core.risk.LOCKED_CFG` okunur. Maliyet modeli (`CostModel`) risk değildir ve burada yaşar |
| Faz A modları | `paper`, `backtest`. `testnet`/`live` → `ConfigError("faz_b")` |
| Hata sınıfları | `errors.py`; `trader_core.config_loader.ConfigError` **kullanılmaz** (o freqtrade yapılandırmasına özgü; ad çakışması) |

## 2. DOSYA SAHİPLİĞİ

Bu birim yalnızca şunlara dokunur:

- `src/trader_engine/__init__.py` (yalnızca `__version__ = "0.1.0"`; hiçbir import)
- `src/trader_engine/errors.py`, `types.py`, `numeric.py`, `clock.py`, `bars.py`, `config.py`
- `config/engine.base.json`, `config/engine.learner.json`, `config/engine.twin.json`
- `tests/engine/__init__.py` **yok** (mevcut `tests/` düzeni paket değildir; `pythonpath = ["src"]`). Tüm `tests/engine/` dosya adları `test_engine_*` önekiyle **benzersiz** olmalıdır (pytest `rootdir` içe aktarma modu çakışmasın)
- `tests/engine/test_engine_types_spec.py`, `test_engine_clock_bars_spec.py`, `test_engine_config_spec.py` (bağımsız test ajanı), `test_engine_clock_bars_impl_smoke.py` (gerçekleme ajanı)

Dokunulmaz: `src/trader_core/*` (yalnızca çağrılır), `pyproject.toml` (08'e ait), `src/trader_engine/marketdata/*`, `brokers/*`, `exchange/*` ve diğer birimlerin dosyaları.

Yapım sırası notu: bu birim **dalga 0**'dır; diğer birimler bu belgedeki tip tanımlarına karşı paralel başlayabilir (tipler burada eksiksiz verilmiştir), ama birleştirme `types.py` iner inmez yapılır.

## 3. `errors.py`

```
class EngineError(Exception)            # taban
class ConfigError(EngineError, ValueError)
class ClockError(EngineError)           # saat geri gitti / tz-naive
class DataError(EngineError)            # veri boşluğu, bozuk bar, eksik kural
class StateError(EngineError)           # state.sqlite açılamadı / kilitli / bozuk   (04 kullanır)
class BrokerError(EngineError)          # beklenmeyen broker hatası                    (03 kullanır)
class BrokerUncertain(BrokerError)      # ağ belirsizliği: emir gitti mi bilinmiyor    (03/04)
class FailClosed(EngineError)           # "bu yolda giriş yok" sinyali; çıkışı engellemez
```

## 4. `types.py` — donmuş sözleşme

Tüm sınıflar `@dataclass(frozen=True)`, `slots` yok, yöntemsiz (yalnızca belirtilen özellikler). Alan sırası aşağıdaki gibi. Kurucuda doğrulama **yoktur** (hız); doğrulama sınırlarda yapılır (`config.py`, `feed`, `broker`). Yardımcı doğrulayıcı `require_utc(dt, name)` (modül işlevi, `ClockError` değil `ValueError`).

```python
Side      = Literal["long", "short"]
OrderSide = Literal["buy", "sell"]
Role      = Literal["entry", "stop", "target", "exit"]
Kind      = Literal["last", "mark"]
ExitReason = Literal["stop","target","trail_stop","regime_flip","time_stop","manual","force_exit","liquidation","other"]
         # = trader_core.ledger._EXIT_REASONS ile birebir (uyum testi zorunlu)

def canon_pair(p: str) -> str          # strip, upper, ":" sonrasını at; ^[A-Z0-9]{1,20}/[A-Z0-9]{1,20}$ değilse ValueError
def pair_symbol(pair: str) -> str      # "BTC/USDT" -> "BTCUSDT"
def pair_stem(pair: str) -> str        # "BTC/USDT" -> "BTC_USDT_USDT"   (feather dosya kökü)
def order_side_for(side: Side, role: Role) -> OrderSide
        # entry: long->buy short->sell ; stop/target/exit (reduceOnly): long->sell short->buy
def require_utc(dt: datetime, name: str = "ts") -> datetime
```

```python
@dataclass(frozen=True)
class Bar:                                  # tf barı (kapanmış)
    pair: str; kind: Kind; tf: str          # tf ∈ {"1m","15m","1h","4h"}
    open_ts: datetime                       # UTC, tf'ye hizalı
    o: float; h: float; l: float; c: float
    v: float = 0.0
    # özellik: close_ts -> open_ts + tf_delta(tf)

@dataclass(frozen=True)
class MinuteBar:                            # adım barı: last + mark birlikte (native: 1 dk; kaba mod: 15 dk)
    pair: str
    open_ts: datetime
    step_s: int                             # 60 (native) | 900 (kaba mod)
    last_o: float; last_h: float; last_l: float; last_c: float
    mark_o: float | None; mark_h: float | None; mark_l: float | None; mark_c: float | None   # yoksa None
    volume: float = 0.0
    # özellik: close_ts -> open_ts + step_s sn

@dataclass(frozen=True)
class FundingPoint:
    pair: str; ts: datetime; rate: float; mark: float | None    # ts: 00:00/08:00/16:00 UTC; rate ondalık (0.0001 = %0,01)

@dataclass(frozen=True)
class SymbolRules:                          # float; borsa filtrelerinin motor içi görünümü
    pair: str; symbol: str
    tick: float; step: float; min_qty: float; max_qty: float; min_notional: float

@dataclass(frozen=True)
class OrderRequest:
    client_id: str; pair: str; role: Role; order_side: OrderSide
    qty: float
    trigger_price: float | None             # stop/target için dolu, entry/exit için None
    reduce_only: bool                       # entry False; stop/target/exit True
    leverage: int | None                    # yalnız entry
    working_type: Literal["MARK_PRICE","CONTRACT_PRICE"] = "MARK_PRICE"
    signal_bar_close_ts: datetime | None = None
    created_ts: datetime | None = None

@dataclass(frozen=True)
class OrderResult:
    status: Literal["filled","accepted","rejected","unknown"]
    client_id: str
    order_id: str | None = None
    filled_qty: float = 0.0
    avg_price: float | None = None
    fee: float = 0.0
    reason: str | None = None               # rejected/unknown için kod: "min_notional","step","would_trigger","duplicate_client_id",…
    ts: datetime | None = None

@dataclass(frozen=True)
class BrokerOrder:
    client_id: str; pair: str; role: Role; order_side: OrderSide
    qty: float; trigger_price: float | None; reduce_only: bool
    status: Literal["new","filled","canceled","rejected","expired"]
    filled_qty: float; avg_price: float | None
    created_ts: datetime; updated_ts: datetime

@dataclass(frozen=True)
class Fill:
    client_id: str; pair: str; role: Role; order_side: OrderSide
    qty: float; price: float; fee: float; ts: datetime
    reason: Literal["market","stop","target","liquidation"]

@dataclass(frozen=True)
class BrokerEvent:
    kind: Literal["fill","funding","liquidation","order_canceled","order_rejected"]
    ts: datetime; pair: str; client_id: str | None = None
    fill: Fill | None = None                # kind in {"fill","liquidation"}
    funding_paid: float = 0.0               # kind=="funding": POZİTİF = ödenen (ledger işareti)
    rate: float | None = None; mark: float | None = None
    detail: str | None = None

@dataclass(frozen=True)
class BrokerPosition:
    pair: str; side: Side; qty: float; entry_price: float; leverage: int
    margin: float                           # izole teminat = qty*entry/leverage
    liq_price: float
    funding_paid: float                     # bu pozisyon için birikmiş (pozitif = ödenen)
    fee_paid_entry: float
    opened_ts: datetime
    mark_price: float | None = None
    unrealized: float = 0.0

@dataclass(frozen=True)
class BrokerAccount:
    wallet: float                           # gerçekleşmiş nakit bakiye (USDT)
    unrealized: float
    equity: float                           # wallet + unrealized
    used_margin: float
    available: float                        # wallet - used_margin
    ts: datetime

@dataclass(frozen=True)
class Intent:                               # motorun iç niyeti; OrderManager emre çevirir
    kind: Literal["entry","exit","stop_update"]
    bot: str; pair: str; side: Side
    signal_bar_close_ts: datetime           # giriş: sinyal barının kapanışı; çıkış/stop: karar anı D
    setup: Literal["T1","R1"] | None
    qty: float | None; leverage: int | None
    planned_entry: float | None; stop_price: float | None; target_price: float | None
    reason: str                             # ExitReason (exit) ya da "entry"/"trail"
    decision_id: int | None = None

@dataclass(frozen=True)
class Position:                             # state.sqlite `positions` satırının görünümü (04 sahibi, burada tip)
    trade_id: int; bot: str; pair: str; side: Side; setup: Literal["T1","R1"]
    status: Literal["opening","open","closing","closed"]
    decision_id: int; signal_bar_close_ts: datetime
    entry_ts: datetime | None; entry_bar_open: datetime | None
    entry_price: float | None; qty: float | None; leverage: int
    initial_stop: float; current_stop: float; stop_seq: int; stop_client_id: str | None
    planned_target: float | None; trail_atr: float
    param_version_id: int; trigger_tf: str
    risk_amount: float; margin: float
    rh: float | None; rl: float | None
    fee_entry: float; funding_paid: float
    mfe_price: float | None; mae_price: float | None      # ham uçlar (long: mfe=max high, mae=min low; short ters)
    exit_reason: str | None; exit_client_id: str | None
    closed_ts: datetime | None
```

Değişmezler:
- `Position.entry_bar_open = floor_tf(entry_ts, trigger_tf)`; `initial_stop` giriş anında dondurulur ve bir daha değişmez; `current_stop` yalnızca **sıkılaşır** (long: artar, short: azalır).
- `OrderRequest.reduce_only == (role != "entry")`; `entry` dışında `leverage is None`; `stop`/`target` dışında `trigger_price is None`.
- `Fill.reason == "liquidation"` yalnızca `BrokerEvent.kind == "liquidation"` ile birlikte gelir.
- `BrokerEvent.funding_paid` işareti **ledger işaretidir** (pozitif = ödenen); freqtrade `funding_fees` ile ters işaretlidir (bkz. `06-backtester.md` çapraz doğrulama).

## 5. `numeric.py` — küçük sayısal yardımcılar (tümü saf)

Yüzdürme hatasına karşı `decimal.Decimal(repr(x))` ile çalışır; sonuç `float`.

```
def floor_step(x: float, step: float) -> float            # aşağı, step'in tam katı
def ceil_step(x: float, step: float) -> float             # yukarı
def is_multiple(x: float, step: float, rel_tol: float = 1e-9) -> bool
def round_tight(price: float, side: Side, tick: float) -> float
        # koruyucu stop: girişe doğru (sıkı) — long: yukarı (ceil), short: aşağı (floor)   [1l3a stop_yuvarla ile aynı kural]
def round_adverse(price: float, order_side: OrderSide, tick: float) -> float
        # dolum fiyatı aleyhte: buy -> yukarı, sell -> aşağı
def bps(x: float) -> float                                # x/1e4
```
Kenarlar: `step <= 0` veya sonlu değil → `ValueError`; `floor_step(0.0, s) == 0.0`; negatif x → `ValueError`.

## 6. `clock.py`

```python
class Clock(Protocol):
    def now(self) -> datetime            # tz-aware UTC, mikrosaniye dahil
    def sleep(self, seconds: float) -> None

class SystemClock:                       # TEK izinli duvar saati kullanımı; datetime.now(timezone.utc), time.sleep
class SimClock:
    def __init__(self, start: datetime)  # require_utc
    def now(self) -> datetime
    def set_time(self, t: datetime) -> None   # t < now ise ClockError (geri gitmez); eşitse no-op
    def advance(self, seconds: float) -> None # seconds < 0 -> ClockError
    def sleep(self, seconds: float) -> None   # gerçek uyku YOK: advance(seconds)
```
- `Ledger(clock=...)` için `clock.now` doğrudan geçilir (`Callable[[], datetime]`). Backtest'te ledger saati motor saatidir: `bar_close_ts ≤ now + 5 sn` denetimi (ledger `_prep_decision`) bu yüzden SimClock'un karar anına (`D`) ayarlanmasını **şart** koşar.
- `SystemClock.now()` hiçbir zaman tz-naive dönmez. `SimClock.set_time` tz-naive → `ValueError`.

## 7. `bars.py` — bar aritmetiği (pandas yok)

```
TF_SECONDS = {"1m": 60, "15m": 900, "1h": 3600, "4h": 14400}
TRIGGER_TFS = ("1h", "15m")             # ledger/signals ile aynı
WINDOW_TRIGGER = {"1h": 1500, "15m": 5000}     # StrategyRunner penceresi (kapanmış tetik barı sayısı)
WINDOW_4H = 1500
STARTUP_BARS = {"1h": 1200, "15m": 4800}       # TraderV1.startup_candle_count = 300*4/tf_saat ile aynı
STARTUP_BARS_4H = 300

def tf_delta(tf: str) -> timedelta                       # bilinmeyen tf -> ValueError
def floor_tf(ts: datetime, tf: str) -> datetime          # epoch'a göre aşağı hizalama; 4h bar 00/04/08/12/16/20 UTC'de açılır
def is_tf_close(ts: datetime, tf: str) -> bool           # ts == floor_tf(ts, tf) ve saniye/mikrosaniye 0
def closing_tfs(ts: datetime, tfs=("15m","1h","4h")) -> list[str]   # ts anında kapanan tf'ler, kısadan uzuna
def last_closed_open(now: datetime, tf: str) -> datetime # now anında kapanmış en son barın AÇILIŞI = floor_tf(now, tf) - tf_delta(tf)
def bar_close_ts(open_ts: datetime, tf: str) -> datetime
def expected_opens(start: datetime, end: datetime, tf: str) -> Iterator[datetime]   # açılışı [start, end) içinde olan tüm bar açılışları
def to_ms(ts: datetime) -> int ; def from_ms(ms: int) -> datetime
def aggregate_minutes(minutes: Sequence[MinuteBar], tf: str, kind: Kind = "last") -> Bar
        # 1 dk -> tf toplama (o=ilk açılış, h=max, l=min, c=son kapanış, v=Σ). Süre dolu değilse (eksik dakika) DataError
def funding_times(start: datetime, end: datetime) -> list[datetime]   # (start, end] içindeki 00:00/08:00/16:00 UTC anları
```
Kenar durumlar:
- `last_closed_open(now=12:00:00Z, "4h") == 08:00:00Z` (08:00 barı tam 12:00'de kapanmıştır); `now=11:59:59.999Z → 04:00Z`.
- `floor_tf` mikrosaniye taşır: `09:17:30.5Z, "1h" → 09:00:00Z`.
- `aggregate_minutes` girdisi tek çift, art arda ve sıralı olmalı; aksi `DataError`.

## 8. `config.py` ve JSON dosyaları

```python
@dataclass(frozen=True)
class CostModel:
    fill_model: Literal["native","legacy_compat"] = "native"
    taker_fee: float = 0.0005                    # 0 ≤ x ≤ 0.005
    slip_entry_bps: float = 2.0                  # 0 ≤ x ≤ 100
    slip_exit_bps: float = 2.0
    slip_stop_bps: float = 5.0
    trigger_source: Literal["mark","last"] = "mark"
    granularity: Literal["1m","15m"] = "1m"      # "15m" = kaba mod (raporda işaretlenir)

@dataclass(frozen=True)
class EngineConfig:
    schema: str                                  # "engine/1"
    mode: Literal["paper","backtest"]            # Faz A
    bot: Literal["learner","twin"]
    pairs: tuple[str, ...]                       # canon_pair, tekrarsız, ≥1
    wallet_start: float                          # 1000.0 (paper cüzdanı)
    cost: CostModel
    target_mode: Literal["bar_close"]            # Faz A: yalnız "bar_close" (bkz. 05 §1, çakışma notu)
    veto_mode: Literal["required","off"]         # "off" yalnızca mode=="backtest" ile geçerli
    record_filtered_candidates: bool             # stop_width/rr_below_min adaylarını defterde yaz (varsayılan True)
    stale_factor: float                          # 1.0: karar anı bar kapanışından > 1 tf geçtiyse giriş yok
    loop_sleep_s: float                          # 5.0
    bar_wait_s: float                            # 120.0: tf barı (karar adımı) gelmeyi bekleme üst sınırı
    minute_wait_s: float                         # 20.0: dakika barı gelmeyi bekleme üst sınırı (sonra dakika boşluğu sayılır)
    reconcile_open_s: float                      # 15.0
    reconcile_flat_s: float                      # 60.0
    var_dir: str; market_db: str; history_dir: str
    veto_config: str; kill_file: str
    # türetilmiş yollar (özellik): ledger_path, state_path, status_path = <var_dir>/<bot>/{ledger.sqlite,state.sqlite,status.json}

def load_engine_config(base_path, bot_path=None, *, env=None) -> EngineConfig
def apply_overrides(cfg: EngineConfig, **kw) -> EngineConfig       # dataclasses.replace + yeniden doğrulama (backtest CLI kullanır)
```
- Birleştirme: `trader_core.config_loader.deep_merge(base, override)` yeniden kullanılır (yalnız o işlev; `validate`/`ConfigError` kullanılmaz).
- Doğrulama (hepsi `ConfigError`): bilinmeyen anahtar; `schema != "engine/1"`; `mode ∉ {paper, backtest}` (`testnet`/`live` → mesaj `"faz_b"`); `pairs` boş/yinelenen/biçim bozuk; `wallet_start ≤ 0` ya da sonsuz; `cost` aralıkları; `fill_model=="legacy_compat"` ise `trigger_source=="last"` ve `granularity=="15m"` **zorunlu** (aksi ret: uyum kipi mark/1 dk kullanamaz); `granularity=="15m"` ise `trigger_source=="last"`; `veto_mode=="off"` ve `mode!="backtest"` → ret; `stale_factor ∈ [1, 3]`; sayısal alanlar `bool` olamaz.
- **Risk sayısı yasağı:** JSON'da `max_trade_risk`, `leverage`, `risk` vb. anahtarlar bilinmeyen anahtar olarak reddedilir; kaldıraç, boyut ve riskin tek kaynağı `LOCKED_CFG`'dir.
- `bot` yalnız `learner|twin`; `twin` için `start_delay_s ≥ 0`.

`config/engine.base.json` (başlangıç içeriği):

```json
{
  "schema": "engine/1",
  "mode": "paper",
  "pairs": ["BTC/USDT","ETH/USDT","BNB/USDT","SOL/USDT","XRP/USDT","DOGE/USDT","ADA/USDT","TRX/USDT","LINK/USDT","AVAX/USDT"],
  "wallet_start": 1000.0,
  "cost": {"fill_model": "native", "taker_fee": 0.0005, "slip_entry_bps": 2.0, "slip_exit_bps": 2.0,
           "slip_stop_bps": 5.0, "trigger_source": "mark", "granularity": "1m"},
  "target_mode": "bar_close",
  "veto_mode": "required",
  "record_filtered_candidates": true,
  "stale_factor": 1.0,
  "loop_sleep_s": 5.0, "bar_wait_s": 120.0, "minute_wait_s": 20.0, "reconcile_open_s": 15.0, "reconcile_flat_s": 60.0,
  "start_delay_s": 0.0,
  "var_dir": "var", "market_db": "var/market.sqlite", "history_dir": "user_data/data/binance/futures",
  "veto_config": "config/veto.json", "kill_file": "shared/KILL"
}
```
`engine.learner.json` = `{"bot": "learner"}`; `engine.twin.json` = `{"bot": "twin", "start_delay_s": 3.0}`. (`config/base.json` listesi `"BTC/USDT:USDT"` biçimindedir; `canon_pair` ikisini de kabul eder, `veto.load_pairs` `pair_key` ile normalleştirir; `veto.json.pairs_from` serbest `dosya:nokta.yolu` olduğundan §4.3 silme adımında `"config/engine.base.json:pairs"` olarak yeniden işaretlenir — ayrı iş.)

## 9. Fail-closed kuralları

- Tanınmayan her yapılandırma değeri `ConfigError`; "varsayılana düş" yok.
- `SimClock` geri gitmez; `SystemClock` geri giderse (NTP) `now()` yine döner ama çağıran `Engine` ardışık iki okumada negatif fark görürse `ClockError` (05).
- `canon_pair` biçim dışı girdide istisna fırlatır; sessiz düzeltme yok.

## 10. Elle doğrulanabilir örnekler

1. `canon_pair(" btc/usdt:usdt ") == "BTC/USDT"`; `pair_symbol → "BTCUSDT"`; `pair_stem → "BTC_USDT_USDT"`.
2. `floor_tf(2026-12-01T09:17:30Z, "4h") == 2026-12-01T08:00:00Z`; `is_tf_close(2026-12-01T12:00:00Z, "4h") is True`; `closing_tfs(12:00Z) == ["15m","1h","4h"]`, `closing_tfs(13:00Z) == ["15m","1h"]`, `closing_tfs(13:15Z) == ["15m"]`, `closing_tfs(13:01Z) == []`.
3. `funding_times(2026-12-01T07:59Z, 2026-12-01T16:00Z) == [08:00Z, 16:00Z]` (uçta `end` dahil, `start` hariç).
4. `round_tight(97.951, "long", 0.01) == 97.96` (yukarı); `round_tight(102.049, "short", 0.01) == 102.04`; `round_adverse(100.02, "buy", 0.01) == 100.02` (zaten tam kat; kayan nokta kaydı `100.02000000000001` sonucu `100.03` yapmamalı); `round_adverse(97.951, "sell", 0.01) == 97.95`.
5. `floor_step(6.3694, 0.001) == 6.369`; `is_multiple(6.369, 0.001) is True`.
6. `aggregate_minutes` 60 dakikalık seri: `o`=ilkin açılışı, `h`=max, `l`=min, `c`=son kapanış, `v`=Σ; 59 dakika → `DataError`.
7. `load_engine_config(base, learner)`: `ledger_path == "var/learner/ledger.sqlite"`; `mode: "live"` → `ConfigError` ("faz_b"); `fill_model="legacy_compat"` + `trigger_source="mark"` → `ConfigError`; JSON'a `"max_trade_risk": 0.03` eklenirse → `ConfigError` (bilinmeyen anahtar).

## 11. Kabul senaryoları (test ajanı için)

`ExitReason` literal kümesi `ledger._EXIT_REASONS` ile eşit; `TRIGGER_TFS`, `STARTUP_BARS` `signals`/`TraderV1` kurallarıyla tutarlı (`300*4/tf_saat`); tüm yukarıdaki örnekler; `SimClock` geri gitme/tz-naive ret; `numeric` sınır değerleri (`step` çok küçük, `x` tam kat, `x` kat − 1e-12, negatif); `Intent`/`Position` alan kümesi bu belgeyle birebir (alan adı listesi testi); tüm kamu işlevleri tz-naive girdiyi reddeder; `engine.base.json` `load_engine_config` ile yüklenir ve `pairs` 10 öğedir; modül import'u `pandas`/`numpy`/`requests` yüklemez (alt süreçte `sys.modules` denetimi — feed hafifliği şartı).

## 12. Belirsizlikler ve çözümleri

- **`MinuteBar.mark_*` yok (None):** kaynak mark barı vermediyse `None`. PaperBroker `trigger_source="mark"` iken `None` görürse last'a düşer ve sayaç artırır (`03-paper-broker.md`); sessiz değil, sayılır.
- **`Bar`/`MinuteBar` sadece veri:** DataFrame'e dönüşüm `marketdata/sources.py` ve `strategy_runner.py` içindedir; bu pakette pandas yok.
- **`Position.status == "opening"`** giriş emri gitmiş, dolmamış demektir; risk ve teminat `AccountState`'te rezerve sayılır (bkz. `05-engine-runner.md`).
