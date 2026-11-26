# Strateji v1 — arayüz ve kurallar (spesifikasyon v1, 16 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. Kâğıtta bütün kurulum aileleri × 15dk/1s/4s/1g, 44 enstrüman; 15 dk/R1 kapatma, seans/hafta sonu yasağı ve gölge etiket kararları kalktı; LLM veto yok.

Kaynak kural: `otonom-trading-arastirma/strateji-v1.md` (Bölüm 2–6; kural kimlikleri PA-TRD-01, PA-FLT-01, PA-MUM-06, PA-STP-01, PA-STP-02a, PA-RSK-02, PA-HDF-06 ve PA-YTY-02, PA-KIR-03, PA-MUM-01, PA-HDF-02, PA-HDF-01, PA-STP-03). Bu belge o kuralları koda dökülebilir hale getirir; sayılar kârlılık kanıtı değildir, backtest ile sınanacak başlangıç değerleridir. Bu belge kod, test ve commit içermez; testler bu belgeden yazılır. Rejim etiketi `rejim-spec.md`, boyutlandırma ve risk `risk-kilidi-spec.md`, kayıt ve parametre sürümleri `defter-spec.md` belgelerindedir; burada tekrarlanmaz, yalnızca bağlanır.

## 1. Bölünme

| Parça | Dosya | Bağımlılık | Görev |
|---|---|---|---|
| (a) Sinyal çekirdeği | `src/trader_core/signals.py` | yalnızca pandas, numpy, `indicators.py`, `regime.py` (freqtrade, `risk.py`, `ledger.py` import **edilmez**) | Mum + hizalı 4s rejim sütunları + parametre → mum başına kurulum, yön, planlı giriş/stop/hedef, gerekçe. Çıkış yardımcıları (iz süren stop, zaman durdurma, hedef, rejim dönüşü) saf skaler/seri fonksiyonlar |
| (b) Freqtrade bağdaştırıcısı | `user_data/strategies/TraderV1.py` | freqtrade, `signals.py`, `risk.py`, `ledger.py`, `regime.py` | `IStrategy` kabuğu: veri hazırlama, risk kilidi, defter yazımı, borsa stop'u, çıkış geri çağrıları |

Kural: tüm kural mantığı (a)'dadır; (b)'de sayı, eşik veya koşul **yoktur**, yalnızca çağırır, boyutlandırır, kaydeder. (a) tek başına pytest ile sınanır (freqtrade kurulu olmadan). (b) için birim test, geri çağrıları sahte `Trade`/`DataProvider` ile sınar; kural doğruluğu (a)'da kanıtlanmış sayılır.

`user_data/strategies/` bota salt-okunur bağlanır (`docker-compose.yml`); `src/trader_core` paketinin freqtrade imajında içe aktarılabilir olması kurulum konusudur (bu belgenin kapsamı dışı, bkz. Bölüm 11 madde 14).

## 2. Parametreler (9)

`SignalParams` (frozen dataclass, `signals.py`). Alan adları ve aralıklar `ledger.PARAM_SPECS` ile **birebir** aynıdır; `RegimeParams` bunun ilk üç alanının alt kümesidir (`SignalParams.regime_params()` bunu üretir, kopya tutulmaz).

| # | Alan | Varsayılan | Geçerli aralık (uçlar dahil) | Ders servisi | Ders sınırı | Kapsam |
|---|---|---|---|---|---|---|
| 1 | `range_width_atr` | 4.0 | 3.0 – 6.0 | Hayır | — | rejim |
| 2 | `vol_ratio_max` | 1.5 | 1.25 – 2.0 | Evet | 1.3 – 1.7 | rejim (T1, R1) |
| 3 | `edge_zone_atr` | 0.25 | 0.15 – 0.50 | Hayır | — | rejim + R1 |
| 4 | `pullback_ema` | 50 | {20, 50} (tam sayı) | Hayır | — | T1 |
| 5 | `stop_buffer_atr` | 0.3 | 0.1 – 1.0 | Evet | 0.2 – 0.5 | T1, R1 |
| 6 | `trail_atr` | 3.0 | 2.0 – 4.0 | Evet | 2.5 – 3.5 | T1 |
| 7 | `range_target_frac` | 0.75 | 0.5 – 1.0 | Evet | 0.6 – 0.9 | R1 |
| 8 | `rr_min` | 1.5 | 1.0 – 2.0 | Evet | 1.2 – 2.0 | R1 |
| 9 | `trigger_tf` | `"1h"` | {`"1h"`, `"15m"`} | Hayır | — | tetik zaman dilimi |

- Ders servisinin dokunabildiği: yalnızca 2, 5, 6, 7, 8 (`ledger.LESSON_PARAMS`). Adım: 0.25, 0.1, 0.5, 0.125, 0.25 (`ledger.LESSON_STEP`). Adım ve ders sınırı `SignalParams`'ta **doğrulanmaz** (rejim-spec ile aynı ilke: zorlama ders servisinin/defterin işidir); `SignalParams` yalnızca tarama aralığını doğrular.
- Sayı kabulü `risk-kilidi-spec.md` ile aynı (`bool`, `None`, metin, NaN, inf geçersiz). Aralık dışı → `ValueError`. `pullback_ema` yalnızca tam sayı 20 veya 50 (`50.0` kabul, `"50"` ret). `trigger_tf` yalnızca iki metin.
- `SignalParams.from_mapping(m)`: tam olarak 9 anahtar (ledger `_norm_params` ile aynı: eksik/fazla → `ValueError`); değerleri `round(·, 6)` ile normalleştirir. `DEFAULT_SIGNAL_PARAMS` = tablodaki varsayılanlar.
- Uyum testi (zorunlu): `SignalParams` aralıkları, varsayılanları, `ledger.PARAM_SPECS` ve `regime.RegimeParams` aralıklarıyla ve `LESSON_PARAMS` ile birebir eşit olmalı; biri değişirse test kırılır (üç yerde tutulan aynı sayı, bkz. Bölüm 11 madde 2).

Sabitler (taranmaz, `signals.py` modül sabiti, parametre değildir): `ATR_LEN = 14`, `STOP_LOOKBACK = 5`, `BODY_RATIO_MIN = 0.5`, `WICK_RATIO_MIN = 0.5`, `STOP_DIST_MIN_ATR = 0.5`, `STOP_DIST_MAX_ATR = 2.0`, `TRAIL_START_R = 1.0`, `TIME_STOP_BARS = 48`, `EPS = 1e-9`. Rejim sabitleri (`RANGE_WINDOW`, `MIN_BARS` vb.) `regime.py`'dedir.

**Eşitlik/tolerans kuralı:** "≥" ve "≤" kapsayıcı karşılaştırmalar `EPS` payıyla yapılır (`x ≥ eşik − EPS`, `x ≤ eşik + EPS`); "dar/geniş ise atla" kesin karşılaştırmadır ama aynı payla (`mesafe < 0.5·ATR − EPS` veya `> 2.0·ATR + EPS` ise atla; tam sınırda **geçer**). Amaç: 0.5 gövde oranı gibi ikili-kayan-nokta sınırlarında yöntem farkıyla sonuç değişmemesi.

## 3. `signals.py` — arayüz

```
SETUPS = ("T1", "R1"); SIDES = ("long", "short")

@dataclass(frozen=True)
class SignalParams: <9 alan, Bölüm 2>; from_mapping(m); regime_params() -> RegimeParams

SIGNAL_COLUMNS: list[str]                      # Bölüm 3.2

def compute_signals(df, regime_df, params=DEFAULT_SIGNAL_PARAMS) -> pd.DataFrame

# Skaler saf yardımcılar (tek mum, elle sınanabilir)
@dataclass(frozen=True)
class Candidate:                                # modül içi adı; risk.Candidate ile karışmaması için `SetupCandidate`
    setup, side, entry, stop, target|None, rr|None, stop_dist_atr, skip_reason|None, reasons, features
def evaluate_t1(side, o, h, l, c, ema_value, recent_lows_or_highs, atr_tf, params) -> SetupCandidate | None
def evaluate_r1(side, o, h, l, c, rh, rl, atr_tf, atr_4h, params) -> SetupCandidate | None
def pick_candidate(candidates) -> SetupCandidate | None     # öncelik/çakışma, Bölüm 3.4

# Çıkış yardımcıları (saf)
def trail_stop_path(side, fill_price, initial_stop, highs, lows, atrs, trail_atr) -> pd.Series
def time_stop_due(bars_closed_since_entry, limit=TIME_STOP_BARS) -> bool
def target_reached(side, target, bar_high, bar_low) -> bool
def regime_flip_exit(side, aligned_regime) -> bool
```

`SetupCandidate` aday bir kurulumdur: tetik koşulları tuttu; `skip_reason is None` ise filtreleri (stop genişliği, rr) de geçti, aksi halde elenmiştir.

### 3.1 Girdi sözleşmesi

- `df`: `DataFrame`, `DatetimeIndex` (mum **açılış** zamanı, UTC, kesin artan, tekrarsız), sütunlar `open, high, low, close` zorunlu (`volume` yok sayılır). Satır = kapanmış tetik mumu (trigger_tf: 1h veya 15m). Oluşmakta olan mumu çıkarmak çağıranın işidir.
- `regime_df`: `regime.align_to_base(classify_series(df_4h, regime_params), df.index, 4)` çıktısı; **aynı indeks** (eşit değilse `ValueError`), sütunlar `regime, rh, rl, rh_touches, rl_touches, atr, atr_ratio`. Burada `atr` **4s ATR14**'tür (sinyaldeki tetik ATR'si ayrıdır, `atr_tf`). İleriye bakmama garantisi `align_to_base`'e aittir (4s mumu kapandığı anda açılan tetik mumundan itibaren geçerli); `compute_signals` ek hizalama yapmaz.
- Yapısal bozukluk (DataFrame değil, zorunlu sütun yok, indeks artan/tekrarsız/`DatetimeIndex` değil, iki indeks eşit değil, `params` tipi yanlış) → `ValueError`. Değer bozukluğu istisna **değil**: o mum "geçersiz mum" (`rejim-spec.md` tanımı: NaN, sonsuz, `high<low`, fiyat ≤ 0, `open`/`close` `[low, high]` dışında) sayılır ve aday üretmez.
- Girdi değiştirilmez; fonksiyon deterministiktir, yan etkisizdir, `shift(-1)`/merkezli pencere yoktur.

### 3.2 Çıktı (`compute_signals`)

`df` ile aynı indeksli, aynı uzunlukta DataFrame; her satır için aşağıdaki sütunlar (`SIGNAL_COLUMNS` sırası):

| Sütun | dtype | İçerik |
|---|---|---|
| `setup` | object | `"T1"` / `"R1"` / `None` (tetik koşulları tutan aday, elenmiş olsa da dolu) |
| `side` | object | `"long"` / `"short"` / `None` |
| `signal` | bool | `True` yalnızca aday **tüm** filtreleri geçtiyse (giriş izni); aksi `False` |
| `skip_reason` | object | `None`, `"stop_width"`, `"rr_below_min"` veya `"other"` (çakışma, Bölüm 3.4); ledger `skip_reason` kodlarıdır |
| `planned_entry` | float64 | Tetik mumunun `close`'u (gerçek dolum sonraki mum açılışıdır); aday yoksa NaN |
| `planned_stop` | float64 | Aday yoksa NaN |
| `planned_target` | float64 | Yalnızca R1; T1'de her zaman NaN (ledger T1'de `planned_target` NULL ister) |
| `rr` | float64 | Yalnızca R1: `|hedef−giriş|/|giriş−stop|`; T1'de NaN |
| `stop_dist_atr` | float64 | `|giriş−stop| / atr_tf` |
| `atr_tf` | float64 | Tetik TF ATR14 (mum t) |
| `atr_4h` | float64 | `regime_df["atr"]` aynen |
| `atr_ratio` | float64 | `regime_df["atr_ratio"]` aynen |
| `regime`, `rh`, `rl`, `rh_touches`, `rl_touches` | | `regime_df`'den aynen geçirilir (her satır; aday olsun olmasın) |
| `ema_value` | float64 | T1: `EMA(close, pullback_ema)`; diğer NaN |
| `body_ratio` | float64 | T1: `|c−o|/(h−l)`; diğer NaN |
| `wick_ratio` | float64 | R1: ilgili fitil/range; diğer NaN |
| `edge_dist_atr` | float64 | R1: long `(c − rl)/atr_4h`, short `(rh − c)/atr_4h`; diğer NaN |
| `pullback_ema` | int64 | `params.pullback_ema` (T1 satırlarında dolu, diğerlerinde 0) |
| `reasons` | object | Virgülle ayrılmış kod listesi, boşluk yok (Bölüm 3.5) |

Ledger `features` eşlemesi (adaptör bunu kurar, sinyal modülü sütunları verir): ortak `atr_tf` (ledger `atr_1h` yerine `atr_tf` anahtarını kabul eder), `stop_dist_atr`, `atr_4h`; T1: `pullback_ema`, `ema_value`, `body_ratio`; R1: `wick_ratio`, `rr`, `edge_dist_atr`. Fazla anahtar serbesttir (ör. `rh_touches`).

### 3.3 Kurulum formülleri (mum `t`, tetik TF kapanışı)

Göstergeler: `atr_tf = atr(df, 14)[t]` (Wilder, `indicators.py`); `ema_p = ema(close, pullback_ema)[t]`; `range_t = h−l`; `body_ratio = |c−o|/range_t`; `lower_wick = min(o,c) − l`; `upper_wick = h − max(o,c)`. `range_t == 0` ise oranlar tanımsız → aday yok (`bad_bar`).

**T1 long** (short tam ayna: karşılaştırmalar ters, `trend_down`):
1. `regime[t] == "trend_up"` (PA-FLT-01).
2. `l ≤ ema_p ≤ c` ve `c > o` ve `body_ratio ≥ 0.5` (PA-TRD-01, PA-MUM-06).
3. `stop = min(low[t−4 … t]) − stop_buffer_atr × atr_tf` (son 5 mum, **tetik mumu dahil**; PA-STP-01). Short: `max(high[t−4 … t]) + stop_buffer_atr × atr_tf`.
4. `entry = c`; `stop_dist = |entry − stop|`; `stop_dist < 0.5·atr_tf` veya `> 2.0·atr_tf` → aday elenir, `skip_reason = "stop_width"` (PA-RSK-02).
5. Hedef yok (`planned_target = NaN`); çıkış Bölüm 5.

**T1 short:** `regime == "trend_down"`; `h ≥ ema_p ≥ c` ve `c < o` ve `body_ratio ≥ 0.5`.

**R1 long** (short ayna: `rh` tarafı):
1. `regime[t] == "range"`; `rh`, `rl` aligned satırdan (dondurma: Bölüm 5.3). `zone = edge_zone_atr × atr_4h`.
2. `l ≤ rl + zone` (RL'yi delmesi şart değil), `c > rl`, `lower_wick / range_t ≥ 0.5` (PA-YTY-02, PA-KIR-03, PA-MUM-01).
3. `stop = l − stop_buffer_atr × atr_tf` (tetik mumunun dibi; short `h + …`).
4. `target = rl + range_target_frac × (rh − rl)` (short: `rh − range_target_frac × (rh − rl)`) (PA-HDF-02). Tek hedef, pozisyonun tamamı.
5. Önce stop genişliği (T1 ile aynı, 0.5–2.0 × `atr_tf`) → `"stop_width"`; sonra `rr = (target − entry)/(entry − stop)` (short: `(entry − target)/(stop − entry)`); `rr < rr_min` → `"rr_below_min"` (PA-HDF-01). Hedef girişin ötesindeyse (`rr ≤ 0`) da `"rr_below_min"`.
6. **R1 short:** `regime == "range"`; `h ≥ rh − zone`, `c < rh`, `upper_wick / range_t ≥ 0.5`.

Kısa-yol: `signal = (setup is not None) and (skip_reason is None)`.

**Giriş fiyatı notu:** `planned_entry` tetik kapanışıdır; piyasa emri sonraki mum açılışında dolar (strateji-v1 5.3). Stop mesafesi ve `rr` süzgeçleri **planlı** değerlerle hesaplanır, dolumda yeniden hesaplanmaz; fark ledger'a `slippage_entry` olarak yansır. Boyutlandırma gerçek dolum fiyatına göre yapılır (Bölüm 4.4).

### 3.4 Çakışma ve öncelik (`pick_candidate`)

- T1 ve R1 aynı mumda **mantıksal olarak birlikte tutamaz**: ikisi de tek 4s etiketine bağlıdır (`trend_*` ile `range` dışlayıcıdır). Yine de savunma amaçlı kural: ikisi birlikte gelirse **T1 önceliklidir** (R1 atılır); bu durum testte sentetik girdiyle zorlanır, canlıda ulaşılamaz sayılır.
- Aynı kurulumda iki yön (yalnızca R1, dar range'de bir mum her iki kenar bölgesine girip her iki fitil şartını sağlayabilir): iki aday da tutarsa **hiçbiri üretilmez**; `setup` = `"R1"`, `side = None`, `signal = False`, `skip_reason = "other"`, `reasons = "conflict:long_short"`. (Belirsiz yönde işlem açılmaz; ledger kaydı yazılmaz çünkü yön yok, yalnızca log.)
- Her mum en çok bir aday üretir.

### 3.5 `reasons` kodları

Aday satırları: `"<setup>_<side>:<koşullar>"` + `,<süzgeç sonucu>`. T1: `T1_long:trend_up,ema_touch,bull_body` ya da `T1_short:trend_down,ema_touch,bear_body`; R1: `R1_long:range,edge_zone,reject_wick` ya da `R1_short:range,edge_zone,reject_wick`. Sonuna: geçtiyse `,stop_ok` (T1) / `,stop_ok,rr_ok` (R1); elendiyse `,stop_width` veya `,rr_below_min`. Aday olmayan satırlar: `""`; ek olarak `"no_history"` (rejim `trend_*`/`range` ama bir gösterge NaN: ısınma, geçersiz mum penceresi), `"bad_bar"` (tetik mumu geçersiz veya range 0), `"regime_blocked"` (etiket `volatile`/`unclear`). Bir satırda tek kod; öncelik: `bad_bar` > `regime_blocked` > `no_history` > `""`.

### 3.6 İleriye bakmama ve değişmezlik

`compute_signals(df, r)[0:k]` ile `compute_signals(df.iloc[:k], r.iloc[:k])` tüm sütunlarda **birebir** eşit olmalı (NaN eşit sayılır; her `k ≥ 1`). Satır `t` yalnızca `df` ve `regime_df` satır `0…t`'ye bağlıdır. EMA/ATR tohumu ilk satırdan alındığı için sonuç geçmiş başlangıcına hafifçe bağlıdır; backtest ve canlı aynı başlangıçla çalışmalıdır: freqtrade `startup_candle_count` = 300 adet 4s mumunu karşılayacak sayı (1h tetikte 1200, 15m tetikte 4800; Bölüm 4.1).

## 4. `TraderV1.py` — bağdaştırıcı (KALDIRILDI)

> **Bölüm 4–6 (IStrategy bağdaştırıcısı) kaldırıldı (17 Kasım 2026, `motor-tasarimi.md` §4.3): bkz. `motor-spec.md` ve `docs/motor/`.** Aşağıdaki metin yalnızca tarihsel kayıttır; bağdaştırıcı kodu silinmiştir (son referans commit `bfe5185`). Çıkış kuralları `position_manager`'da, sinyaller `signals.py`'dedir.

`class TraderV1(IStrategy)`. Yalnızca çağırma, boyutlandırma ve kayıt; kural eşiği yok.

### 4.1 Sınıf ayarları

- `INTERFACE_VERSION = 3`, `can_short = True`, `process_only_new_candles = True`, `position_adjustment_enable = False`.
- **timeframe:** `__init__` sonunda (`super().__init__(config)` sonrası) `self.timeframe = trigger_tf` ve `self.startup_candle_count = 300 × 4 / tf_saat` (1h: 1200, 15m: 4800) atanır. `trigger_tf` kaynağı: defter yapılandırılmışsa `ledger.get_active_params().params["trigger_tf"]`, değilse `config["trader_v1"]["params"]["trigger_tf"]`, o da yoksa `"1h"`. `bot_start()` içinde `config["timeframe"]` varsa ve `self.timeframe`'den farklıysa `OperationalException` (sessiz ayrışma yok); yani `config/base.json` `timeframe` değeri `trigger_tf` ile elle tutarlı tutulur. `trigger_tf` ders servisine kapalıdır; yalnızca `author="user"` sürümüyle değişir ve **yeniden başlatma gerektirir**: `bot_loop_start`'ta etkin `trigger_tf != self.timeframe` bulunursa kapı kapatılır (yeni giriş yok, `CRITICAL` log, kod `"trigger_tf_changed"`); açık pozisyonlar yönetilmeye devam eder.
- `informative_pairs()`: whitelist'teki her çift için `(pair, "4h")`. 4s verisi `self.dp.get_pair_dataframe(pair, "4h")` ile alınır (`@informative` dekoratörü **kullanılmaz**: bayatlık sınırı ve saat-dilimi kontrolü `align_to_base`'de).
- Çıkış mekanizması: `use_custom_stoploss = True`, `stoploss = -0.99` (yalnızca geri dönüş; gerçek stop `custom_stoploss`), `minimal_roi = {"0": 100}` (fiilen kapalı), `use_exit_signal = True`, `exit_profit_only = False`, `ignore_roi_if_entry_signal = False`. Çıkış sinyal sütunları (`exit_long`, `exit_short`) **hiç set edilmez**.
- `order_types = {"entry": "market", "exit": "market", "stoploss": "market", "stoploss_on_exchange": True, "stoploss_on_exchange_interval": 60}`. `stoploss_on_exchange` dry-run ve canlıda zorunludur (strateji-v1 Bölüm 7 çelişki 4: bar içi borsada duran stop); backtest simülasyonunda stop bar içi uygulanır, bayrak etkisizdir. Başlangıçta `stoploss_on_exchange` `False` bulunursa (`bot_start`) `OperationalException`.
- `startup_candle_count` yukarıdaki gibi; `timeframe_detail` yalnızca backtest komutunda verilir (1h kolu için `15m` önerilir: aynı mumda stop/hedef sırasını çözer; 15m kolu için yok).

### 4.2 Parametre yönetimi (`bot_loop_start`)

- Defter yapılandırılmışsa her döngüde `ledger.get_active_params()`; `activation_id` öncekinden farklıysa `SignalParams.from_mapping(ap.params)` kurulur ve `self._active = (version_id, params, params_hash)` olur. Değişiklik "bir sonraki mum kapanışına" yansır (`defter-spec` 7.1, 9): `populate_*` çağrıları o mumdaki `self._active`'i kullanır; aynı mum işlenirken sürüm değişimi o mumu etkilemez (sinyal bağlamı sürüm kimliğini taşır, Bölüm 4.4).
- `get_active_params()` veya `from_mapping` hata verirse: son bilinen geçerli parametreler **giriş için kullanılmaz**; kapı kapanır (kod `"params_unavailable"`), açık pozisyonlar kendi dondurulmuş çıkış parametreleriyle sürer.
- **Açık pozisyonun parametreleri giriş anında dondurulur** (`defter-spec` 9 sonu burayı strateji spesifikasyonuna bırakır): `trail_atr`, `stop_buffer_atr` (yalnızca kayıt), `param_version_id`, `setup`, `rh`, `rl`, `range_target_frac` sonucu `planned_target`, `initial_stop`, `trigger_tf` işlemin `custom_data`'sında saklanır. Giriş sonrası ders servisi bir parametreyi değiştirse açık işlem etkilenmez.
- `ledger` yoksa (yalnızca backtest, Bölüm 6) parametreler `config["trader_v1"]["params"]` ile `DEFAULT_SIGNAL_PARAMS` birleşiminden (`SignalParams.from_mapping`, Bölüm 2 doğrulaması) kurulur.

### 4.3 Sinyal üretimi

`populate_indicators(df, metadata)`: (1) `df_4h = dp.get_pair_dataframe(pair, "4h")` → `date` indeks yapılır; (2) `reg = classify_series(df_4h, params.regime_params())`; (3) `aligned = align_to_base(reg, tetik_indeks, 4)`; (4) `sig = compute_signals(df_idx, aligned, params)`; (5) sütunlar `df`'ye eklenir (`sig` sütun adları aynen; `date` indeksi geri kaldırılır). Saat dilimi UTC; freqtrade `date` sütunu mum açılışıdır. Bu adım sayı hesabı içermez.

`populate_entry_trend(df, metadata)`:
1. Canlı/dry-run: önce `ledger.entries_allowed()`; `ok=False` ise hiçbir satır giriş almaz ve son satırda aday varsa `entry_gate_closed` kararı yazılmaya çalışılır (`defter-spec` 8.1; yazılamazsa yalnızca log). Backtest: defter yoksa kapı atlanır, varsa her giriş denemesinde `confirm_trade_entry`'de denetlenir (populate backtest'te tüm geçmiş için bir kez çalışır, kapı orada anlamsızdır).
2. `signal == True` ve `side == "long"` → `enter_long = 1`; `side == "short"` → `enter_short = 1`; `enter_tag = setup` (`"T1"`/`"R1"`).
3. Canlı/dry-run, **yalnızca son satır** için: elenmiş aday (`skip_reason in {stop_width, rr_below_min}`) ledger'a `final_action="skipped"`, `veto_status="not_evaluated"`, `risk_allowed=None` ile yazılır (aday başına bir kez). Backtest'te bu elenmiş-aday kayıtları yazılmaz (yalnızca giriş denemeleri kaydedilir; Bölüm 6).
4. İstisna: canlı/dry-run'da `compute`/`classify` hatası → giriş yok, `CRITICAL` log (fail-closed); backtest/hyperopt'ta istisna **yayılır** (hata görünür).
5. Son kapanmış mum, bugünkü beklenen son mumdan bir mumdan fazla eskiyse (veri boşluğu/bayat) o döngüde giriş yok (`entries blocked: stale_data`); `signals.py` zaman boşluğunu görmez.

Bir mum başına bir çift için en fazla bir karar kaydı vardır; ledger `UNIQUE(bot,pair,side,setup,trigger_tf,bar_close_ts)` olduğundan aynı içerik idempotenttir, **farklı içerik** (ör. farklı `size_qty`) `LedgerConflictError` verir. Bu yüzden adaptör her `(pair, bar_close_ts)` için kararı bellekte tek seferlik önbelleğe alır; yeniden başlatmada çakışma alınırsa o mum için giriş **yapılmaz** (fail-closed) ve log yazılır. `bar_close_ts = mum açılışı + tetik TF` (UTC, 15 dakikanın tam katı; `defter-spec` kuralı).

### 4.4 Boyutlandırma ve risk kilidi

Hesap durumu her çağrıda şöyle kurulur (`risk.AccountState`):
- `equity` = gerçek cüzdan özsermayesi: stake para biriminde cüzdan toplamı (`wallets.get_total(stake_currency)`) + açık işlemlerin gerçekleşmemiş kâr/zararı. (Dry-run'da cüzdan `dry_run_wallet`'tan başlar; backtest'te freqtrade'in simüle cüzdanıdır.) `config["stake_amount"]` (100) kullanılmaz.
- `day_start_equity` = UTC gün başı (00:00) özsermayesi, **yeniden başlatmaya dayanıklı** türetim: `wallet_realized_total_şimdi − Σ(bugün (UTC 00:00'dan sonra) kapanan işlemlerin kapanış kâr/zararı)`. Yani her çağrıda cüzdan toplamından bugünkü gerçekleşen kâr/zarar çıkarılır; bellekte saat tutulmaz, gün sınırı `current_time` tarihinden gelir (backtest'te de aynı formül, `Trade.get_trades_proxy(is_open=False)`). Gerçekleşmemiş kâr/zarar `day_start_equity`'ye dahil değildir (bilinçli: günlük bütçe kuralı bugünkü **kayıp**la ilgilenir, bkz. Bölüm 11 madde 6).
- `open_positions` = açık işlemler için `OpenPosition(pair, side, risk_amount, margin)`: `risk_amount` işlemin giriş anında dondurulmuş `size.risk_amount`'ı (`custom_data`; iz süren stop riski azaltsa da değiştirilmez, muhafazakâr), `margin` = `trade.stake_amount`.

Geri çağrılar:
- `leverage(pair, current_time, current_rate, proposed_leverage, max_leverage, entry_tag, side)`: sabit `float(max(1, min(LOCKED_CFG.min_leverage, max_leverage)))` döner (yani 3). Gerekçe: pozisyon değeri özsermayeyi ve risk kilidi `target_trade_risk`'i aşamaz; boyut kaldıraçtan bağımsızdır, kaldıraç yalnızca teminatı ve likidasyon mesafesini belirler; en düşük kaldıraç likidasyonu en uzağa koyar. Daha büyük kaldıraç seçilmez.
- `custom_stake_amount(pair, current_time, current_rate, proposed_stake, min_stake, max_stake, leverage, entry_tag, side)`: (1) bu çift ve mumun sinyal bağlamını (`setup`, `planned_stop`, `planned_target`, `skip` yok, `version_id`, satır) al; yoksa `0.0` dön. (2) `Candidate(pair, side, entry=current_rate, stop=planned_stop, leverage, qty_step, min_notional)`; `qty_step` ve `min_notional` borsa piyasa bilgisinden (`dp.market(pair)`: miktar adımı, en küçük emir değeri). (3) `risk.check_entry(AccountState, Candidate, LOCKED_CFG)`. (4) `allowed` ise `size.margin` döner (freqtrade futures'ta stake = teminat; pozisyon değeri = stake × kaldıraç); değilse `0.0` döner ve (canlı/dry-run, ayrıca defter varsa backtest'te) `risk_allowed=False`, `skip_reason="risk_denied"`, `risk_reason=decision.reason` kararı yazılır. `current_rate` backtest'te sonraki mum açılışı, canlıda emir defteri fiyatıdır (config `entry_pricing`).
- `confirm_trade_entry(pair, order_type, amount, rate, time_in_force, current_time, entry_tag, side)` (**yetkili son kapı**):
  1. Kapı: defter varsa `entries_allowed().ok` değilse `False` (karar `entry_gate_closed`).
  2. Veto kancası çağrılır (Bölüm 4.6); `blocks=True` ise karar `veto_*` ile yazılıp `False` dönülür (v1'de asla).
  3. `check_entry`'yi **gerçek** `rate` ile yeniden çalıştır; `allowed=False` veya `amount > size.qty × (1 + 1e-6)` ise `risk_denied` kararı yazılır, `False`.
  4. Karar (`final_action="entered"`, `veto_status` Bölüm 4.6'daki eşlemeyle, `risk_allowed=True`, `size_*`, `leverage`, `features`, `planned_*`, `param_version_id` = sinyal bağlamındaki sürüm, `regime` alanları) `record_decision` ile **emirden önce** yazılır; `decision_id` bellekte `pair`'e bağlanır. Herhangi bir `LedgerError`/istisna → `False` + `CRITICAL` log (`defter-spec` 8.1.2); ledger yoksa (backtest) bu adım atlanır.
  5. `True`.
  Aynı çiftte zaten açık işlem varsa freqtrade yeni giriş denemez (`position_adjustment_enable=False`); `check_entry` kural 5 ayrıca savunma katmanıdır.
- `order_filled(pair, trade, order, current_time)`: giriş emriyse `custom_data`'ya `decision_id`, `risk_amount`, `initial_stop`, `planned_target`, `rh`, `rl`, `setup`, `trail_atr`, `param_version_id`, `trigger_tf`, `entry_bar_open` yazılır; defter varsa `TradeEntry(trade_id=trade.id, decision_id, entry_ts, entry_price=order fiyatı, qty=order miktarı, leverage=int(trade.leverage), fee_entry)` ile `record_trade_entry`. Başarısızlık işlemi geri almaz (`defter-spec` 8.1.3: spool, kapı kapanır). Çıkış emri ve işlem kapandıysa `TradeExit` yazılır (Bölüm 5.5); çıkışlar hiçbir koşulda engellenmez (`defter-spec` 8.2).

### 4.5 Çıkış geri çağrıları

Çıkış kuralları Bölüm 5'te; bu bölüm yalnızca bağlama:
- `custom_stoploss(pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs)`: Bölüm 5.1–5.2'deki stop fiyatını hesaplar ve `stoploss_from_absolute(stop_fiyatı, current_rate, is_short=trade.is_short, leverage=trade.leverage)` ile döner. Bu değer `stoploss_on_exchange` ile borsadaki stop emrini günceller. Stop **hiçbir zaman geri çekilmez** (Bölüm 5.2'deki yol fonksiyonu monoton).
- `custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)`: sırayla `"time_stop"` (yalnız R1), `"target"` (yalnız R1), `"regime_flip"` (yalnız T1), `"trail_stop"` (hesaplanan stop güncel fiyatın aşağıda/yukarıda **ötesinde** kaldıysa, bkz. 5.2) ve `"force_exit"` (işlem için çıkış meta verisi yoksa: stopsuz pozisyon kabul edilmez, hemen kapatılır; fail-closed) döndürür. İlk eşleşen etiketi döner; yoksa `None`. Çıkış emri bir sonraki mum açılışında piyasa emridir (kapanmış mumda değerlendirme).
- Çıkış verisi (`custom_data`) bir işlem için eksikse ve analiz DataFrame'inden de yeniden kurulamıyorsa (`entry_bar_open` mumundan önceki sinyal satırı) `"force_exit"`.

### 4.6 Veto kancası (taslak)

```
@dataclass(frozen=True)
class VetoVerdict: status: str; reason: str | None; blocks: bool
def veto_check(self, pair, side, setup, bar_close_ts, planned_entry, planned_stop, planned_target) -> VetoVerdict
```
v1: her çağrıda `VetoVerdict("not_evaluated", None, False)` döner; hiçbir girişi engellemez. Çağrı sırası: kurulum süzgeçleri (`stop_width`, `rr`) → **veto** → risk kilidi (defter-spec ile aynı sıra). Gelecek: `blocked`/`missing`/`stale` → `blocks=True`, ledger `veto_status` aynı değer, `skip_reason="veto_<status>"`, `final_action="skipped"`; veto yalnızca girişi **azaltabilir**, hiçbir koşulda boyut/stop/hedef değiştirmez.

**Ledger uyumsuzluğu ve çözümü:** ledger, `final_action="entered"` için `veto_status="allowed"` şartı koşar; `not_evaluated` yalnızca `risk_allowed=None` ve `skip_reason ∈ {stop_width, rr_below_min, other, entry_gate_closed}` ile geçerlidir. Bu yüzden kanca `"not_evaluated"` dönse bile, kancanın `blocks=False` olduğu girişte adaptör ledger'a **`veto_status="allowed"`, `veto_reason="not_evaluated:v1_stub"`** yazar (hem `entered` hem `risk_denied` kararlarında). `not_evaluated` ledger'a yalnızca veto'dan **önce** elenen adaylar için (`stop_width`, `rr_below_min`, `entry_gate_closed`) yazılır. Veto gerçekten bağlandığında `reason` alanındaki `v1_stub` işareti ayırt edicidir.

## 5. Çıkış kuralları (bağdaştırıcı kısmı kaldırıldı; bkz. Bölüm 4 notu)

Hepsi **kapanmış** tetik TF mumları üzerinden değerlendirilir; yalnızca borsadaki stop emri bar içi çalışır. Giriş mumu `E` = dolumun gerçekleştiği mum (tetik mumundan sonraki). "Girişten beri" mum kümesi `E, E+1, …, son kapanmış mum`.

### 5.1 Ortak: ilk stop

`initial_stop = planned_stop` (tetik mumundan). Dolumdan hemen sonra borsada bu stop durur. `R = |fill_price − initial_stop|` (gerçek dolum fiyatıyla). Dolum fiyatı stopun yanlış tarafına düşerse (boşluk) `confirm_trade_entry` yeniden `check_entry` ile zaten reddeder (stop yanlış tarafta).

### 5.2 T1: iz süren stop (`trail_stop_path`)

Pure fonksiyon: `highs`, `lows`, `atrs` = `E`'den son kapanmış muma kadar tetik TF değerleri (`atrs` tetik TF ATR14). Long için, her `k` mumu sonunda:
- `hh_k = max(highs[E..k])`; **devrede** (`armed_k`) ⇔ `hh_k ≥ fill_price + 1.0 × R`. Bir kez devreye giren sonra devrede kalır (`hh` monoton olduğundan zaten kalır).
- `cand_k = hh_k − trail_atr × atrs[k]` (devredeyse).
- `stop_k = max(initial_stop, max(cand_j : j ≤ k, armed_j))`; devrede değilse `initial_stop`.
Short ayna (`ll_k = min(lows[E..k])`, `cand = ll + trail_atr × atr`, `stop = min(...)`, eşik `fill − R`). Dönen seri `stop_k` mum başına; `custom_stoploss` son elemanı kullanır (kapanmış mumdan sonra sonraki mum boyunca geçerli). Monotonluk (stop asla geri çekilmez) tanım gereğidir. Sabit hedef ve kısmi çıkış yoktur. `trail_atr` işlemin giriş anındaki dondurulmuş değeridir.

Yol, `custom_data`'da durum tutmadan her çağrıda DataFrame'den yeniden hesaplanır (yeniden başlatmaya dayanıklı, deterministik). Giriş mumu `E` tespiti: `trade.open_date_utc`'nin tetik TF'ye aşağı yuvarlanmışı.

Hesaplanan stop güncel fiyatın ötesinde kaldıysa (long: `stop ≥ current_rate`; borsa bu stop emrini "anında tetiklenir" diye reddeder) `custom_exit` `"trail_stop"` etiketiyle piyasa çıkışı verir.

### 5.3 T1: rejim dönüşü

Long için aligned etiket `"trend_down"`, short için `"trend_up"` olursa (`regime_flip_exit`) bir sonraki mum açılışında piyasa çıkışı (`exit_reason="regime_flip"`). Yalnızca **karşıt trend**; `range`, `volatile`, `unclear` çıkış üretmez (strateji-v1 4.6). Değerlendirme, son kapanmış tetik mumunun aligned etiketiyle yapılır (4s kapanışıyla aynı anda kapanan mum önceki etiketi görür; etiket bir mum gecikmeli yansır, bkz. Bölüm 11 madde 8).

### 5.4 R1: hedef ve zaman durdurma

- Giriş anında `rh`, `rl` ve `planned_target` işlemde dondurulur (strateji-v1 5.8); sonraki etiket değişimi çıkış üretmez (R1'de `regime_flip` yok).
- **Hedef:** son kapanmış mumun `high ≥ target` (long) / `low ≤ target` (short) ise (`target_reached`) bir sonraki mum açılışında piyasa çıkışı, `exit_reason="target"`, `planned_exit = target`. Not: hedef bar içi limit emir değildir (v1 sadeliği; backtest ve canlı aynı); gerçek dolum hedeften iyi veya kötü olabilir, `slippage_exit` bunu kaydeder.
- **Stop:** sabit `initial_stop` (iz yok), borsada.
- **Zaman durdurma:** girişten beri kapanmış mum sayısı (`E` dahil) ≥ 48 ise (`time_stop_due`, 48 **tetik TF** mumu: 1h kolunda 48 saat, 15m kolunda 12 saat; bkz. Bölüm 11 madde 9) bir sonraki mum açılışında çıkış, `exit_reason="time_stop"`. Aynı mumda hedef ve zaman durdurma birlikte tutarsa `target` önceliklidir.
- Aynı kapanmış mumda hedef ve stop birlikte aşılmış olabilir (bar içi sıra bilinmez): backtest'te `timeframe_detail` bunu çözer; detay yoksa freqtrade'in varsayılan muhafazakâr sırası (stop önce) geçerlidir; canlıda sıra borsada olanıdır.

### 5.5 Ledger çıkış kodu eşlemesi

`TradeExit.exit_reason` (ledger `_EXIT_REASONS`): borsa/simülatör stop'u çalıştı → iz süren stop devredeyken `"trail_stop"`, değilken `"stop"` (devre durumu çıkış anında `trail_stop_path`'ten yeniden hesaplanır); `custom_exit` etiketleri aynen (`"target"`, `"time_stop"`, `"regime_flip"`, `"trail_stop"` Bölüm 5.2'den, `"force_exit"`); kullanıcının `forceexit`'i `"manual"`; freqtrade likidasyonu `"liquidation"`; diğer `"other"`. `planned_exit`: stop/iz için o andaki stop fiyatı, `target` için hedef, diğerlerinde `None`. `funding_paid` işareti ledger'da **pozitif = ödenen** (örnek 12.4'te −0.05 alınan); freqtrade `funding_fees` işareti gerçeklemede doğrulanıp eşlenir (Bölüm 11 madde 12).

## 6. Backtest modu (kaldırıldı; yerine `python -m trader_engine backtest`, bkz. `docs/motor/06-backtester.md`)

- Algılama: `self.dp.runmode` ∈ {`BACKTEST`, `HYPEROPT`}.
- Yapılandırma bloğu (`config/backtest.json` ile birleşir; blok yoksa tüm varsayılanlar):
  ```
  "trader_v1": { "bot": "learner", "ledger_path": null, "params": { …kısmi geçersiz kılma… } }
  ```
  - `ledger_path = null` (**varsayılan**): defter yok. Kapı (`entries_allowed`) atlanır; parametreler `DEFAULT_SIGNAL_PARAMS` + `params` geçersiz kılmaları (Bölüm 2 aralık doğrulamasıyla; hata → başlatma durur); karar/işlem yazımı yok; veto kancası yine çağrılır (stub). Bu mod hızlı, tarama/hyperopt içindir.
  - `ledger_path` bir dosya yolu: **yeni** dosya zorunlu (var olan dosya → `OperationalException`; backtest sonuçları tekrarlanamaz karışmasın). `open_ledger(path, bot, create=True, clock=<simüle saat>)` + `init_params(tüm 9 değer, reason="backtest")`. Sonra gerçek akış (kapı, kararlar, giriş/çıkış kayıtları). Test/CI için `":memory:"` **desteklenmez** (ledger iş parçacığı başına bağlantı açar, bellek veritabanı bağlantılar arasında paylaşılmaz); geçici dosya (`tempfile.mkdtemp`) kullanılır ve çalışma sonunda silinebilir.
  - `bot = "twin"` ise `init_params`/parametre yazımı yapılmaz (ledger kuralı); backtest için `learner` varsayılır.
- Saat: ledger'a verilen `clock`, geri çağrıdaki `current_time`'ı (UTC, tz-aware) döndürür; `recorded_at` ve gelecek-mum denetimi bu yüzden backtest'te deterministiktir.
- Özsermaye/gün başı: Bölüm 4.4 formülleriyle freqtrade'in simüle cüzdanından (`dry_run_wallet`, 1000) ve `Trade.get_trades_proxy` geçmişinden; yapay sabit değer yok.
- Determinizm: kural yolunda rastgelelik, duvar saati, ağ veya sözlük/küme sırası bağımlılığı yoktur; zaman yalnızca mum/`current_time`'dan gelir; iki çalıştırma aynı işlem listesini ve aynı ledger içeriğini (`recorded_at` dahil) üretmelidir. `PYTHONHASHSEED`'e bağımlı davranış yasaktır.
- Backtest ledger'ında yalnızca giriş denemeleri (`entered` ve `risk_denied`) ve işlemler yazılır; `stop_width`/`rr_below_min`/`entry_gate_closed` aday kayıtları yazılmaz (populate tüm geçmiş için bir kez çalışır; mum başına defter yazımı hız ve çakışma riski doğurur). Elenen adaylar yine de `signals` DataFrame'inde (`skip_reason`) bulunur ve backtest analizinde okunabilir.
- Hatalar (sinyal/rejim/parametre/veri) backtest'te **yayılır**, canlıda fail-closed yutulur (Bölüm 4.3).
- Ders servisi/veto backtest'te çalışmaz; veto stub'ı çağrılır ve engellemez.
- Önerilen backtest bayrakları (strateji-v1 6.3): walk-forward, maliyet ×2 (ücret/kayma ayrıca `risk.py` içinde sabit varsayımla zaten uygulanır), `timeframe_detail=15m` (1h kolu).

## 7. Uç durumlar

| Durum | Davranış |
|---|---|
| Yetersiz geçmiş (ATR/EMA/5-mum penceresi NaN, 4s için `MIN_BARS=113` altı) | Aday yok; `reasons="no_history"` (rejim tradeable ise) veya rejim `unclear` → `"regime_blocked"`. Hiçbir şey yazılmaz |
| Rejim `volatile` / `unclear` | Aday yok (`regime_blocked`); açık pozisyonlar kendi stop/çıkışlarıyla sürer |
| Rejim `trend_up`/`range` fakat mum bozuk (NaN, `h<l`, `range=0`…) | Aday yok, `bad_bar`; bozuk mum 5-mum geri bakış penceresinde kaldığı sürece sonraki satırlar `no_history` (stop hesaplanamaz) |
| Hesaplanan herhangi bir planlı alan sonlu değil | Aday yok (`no_history`); NaN/inf asla `signal=True` olmaz |
| Aynı çift için ikinci sinyal / açık işlem varken sinyal | freqtrade girişi denemez; `check_entry` kural 5 savunması; ledger'da `UNIQUE` ile mum başına tek kayıt |
| T1 ve R1 aynı mumda | Mantıksal olarak imkânsız; savunma: T1 önce (Bölüm 3.4) |
| R1 long ve short birlikte | Hiçbiri; `skip_reason="other"`, `conflict:long_short` |
| Stop mesafesi sınırda (tam 0.5 veya 2.0 × ATR) | Geçer (kapsayıcı, `EPS` payıyla) |
| `rr == rr_min` | Geçer |
| Hedef girişin ötesinde (R1) | `rr_below_min` |
| Dolum fiyatı stopun yanlış tarafı | `check_entry` red, `risk_denied` |
| Defter kapısı kapalı (`degraded`, `spool_pending`, `no_active_params`, `schema`, `unledgered_trades`) / parametre okunamıyor / `trigger_tf` uyuşmazlığı | Yeni giriş yok; çıkışlar asla engellenmez |
| Karar yazımı sırasında `LedgerError` | `confirm_trade_entry` `False`, `degraded` |
| `LedgerConflictError` (yeniden başlatma, aynı mum farklı boyut) | O mum için giriş yok, log |
| Veri boşluğu / son mum bayat | O döngüde giriş yok; `align_to_base` bayat 4s etiketi `unclear` yapar |
| Yinelenen/artmayan indeks | `compute_signals` `ValueError`; canlıda yutulur ve giriş yok, backtest'te yayılır |
| Çıkış verisi eksik işlem | `custom_exit="force_exit"` |
| Çıkış sırasında ledger yazılamaz | Çıkış yapılır; kayıt spool'a düşer (`defter-spec` 8.2) |
| Hesaplanan iz süren stop güncel fiyatın ötesinde | `custom_exit="trail_stop"` piyasa çıkışı |
| Boyut `qty_step`/`min_notional` altında kalır (küçük hesap) | `check_entry` red (`risk_denied`), giriş yok |

## 8. Elle hesaplanabilir örnekler (yalnızca `signals.py`)

Aksi belirtilmedikçe varsayılan `SignalParams`, karşılaştırmalar `EPS` toleransıyla. Test yazarı bunları tam sayı/kesir aritmetiğiyle doğrular.

### 8.1 T1 long, uçtan uca (`compute_signals`, `pullback_ema=20`)

20 mum (`t = 0…19`). `t = 0…18`: `o = c = 100`, `h = 101`, `l = 99`. `t = 19`: `o = 99.5`, `h = 101`, `l = 99`, `c = 100.5`. `regime_df`: tüm satırlarda `regime="trend_up"`, `rh=rl=NaN`, touches 0, `atr=4.0`, `atr_ratio=1.0`.

- ATR: `TR₀ = 2`; `t ≥ 1` için `max(2, |101−100|, |99−100|) = 2`; `t = 19` için önceki kapanış 100 → yine 2. `ATR = 2` her yerde; ilk geçerli indeks 13.
- EMA20: `t ≤ 18`'de 100; ilk geçerli indeks 19 (20 gözlem). `α = 2/21`: `e₁₉ = 100 + (2/21)·0.5 = 100 + 1/21 ≈ 100.047619`.
- `t = 19`: `l = 99 ≤ 100.0476 ≤ 100.5 = c` ✓; `c > o` ✓; `body_ratio = |100.5−99.5|/(101−99) = 0.5 ≥ 0.5` ✓ (tam sınır). Son 5 dip (15…19) hepsi 99 → `stop = 99 − 0.3×2 = 98.4`; `entry = 100.5`; `stop_dist = 2.1 = 1.05 × ATR` ∈ [0.5, 2.0] ✓.
- Beklenen satır 19: `setup="T1"`, `side="long"`, `signal=True`, `skip_reason=None`, `planned_entry=100.5`, `planned_stop=98.4`, `planned_target=NaN`, `rr=NaN`, `stop_dist_atr=1.05`, `atr_tf=2.0`, `atr_4h=4.0`, `ema_value≈100.047619`, `body_ratio=0.5`, `reasons="T1_long:trend_up,ema_touch,bull_body,stop_ok"`.
- Satır 0…12: ATR NaN → `reasons="no_history"`; 13…18: EMA NaN → `"no_history"`; hepsinde `signal=False`, `setup=None`.
- Değişmezlik: `compute_signals(df.iloc[:19], r.iloc[:19])` tüm satırlarında `signal=False`; `df.iloc[:20]` satır 19 yukarıdakiyle aynı.
- `pullback_ema=50` varsayılanıyla aynı veri: tüm 20 satırda `no_history` (EMA50 en erken indeks 49).

### 8.2 T1 short (ayna)

8.1 verisi, yalnızca `t = 19`: `o = 100.5`, `h = 101`, `l = 99`, `c = 99.5`; `regime="trend_down"`. `e₁₉ = 100 − 1/21 ≈ 99.952381`. `h = 101 ≥ 99.9524 ≥ 99.5 = c` ✓, `c < o` ✓, `body_ratio = 0.5` ✓. `stop = max(highs 15…19) + 0.6 = 101.6`; `entry = 99.5`; `stop_dist = 2.1` ✓. Beklenen: `side="short"`, `planned_stop=101.6`, `reasons="T1_short:trend_down,ema_touch,bear_body,stop_ok"`. Aynı mum `regime="trend_up"` ile: long şartı `l ≤ ema ≤ c` tutmaz (`c = 99.5 < ema`) ve `c < o` → aday yok.

### 8.3 T1 stop genişliği (skaler `evaluate_t1`)

`atr_tf = 2`, `entry c = 100.5`, tetik mumu `o=100.2, h=100.6, l=100.0, c=100.5`, `ema=100.2` (`l ≤ ema ≤ c` ✓, `body_ratio = 0.3/0.6 = 0.5` ✓).
- Dar: son 5 dip `[100.0, 100.1, 100.2, 100.1, 100.0]`, `stop_buffer_atr = 0.1` → `stop = 100.0 − 0.2 = 99.8`; `stop_dist = 0.7 = 0.35 ATR < 0.5` → `skip_reason="stop_width"`, `signal=False`.
- Geniş: dipler `[95, 100.1, 100.2, 100.1, 100.0]` (min 95), `buffer=0.3` → `stop = 94.4`; `stop_dist = 6.1 = 3.05 ATR > 2.0` → `"stop_width"`.
- Sınır: `stop_dist = 1.0` (0.5 ATR) ve `4.0` (2.0 ATR) **geçer**.

### 8.4 R1 long (skaler `evaluate_r1`)

`rl = 100`, `rh = 108`, `atr_4h = 2` (`zone = 0.5`), `atr_tf = 1.0`, tetik mumu `o=100.6, h=101.0, l=100.0, c=100.9`:
- `l = 100.0 ≤ rl + zone = 100.5` ✓; `c = 100.9 > 100` ✓; `lower_wick = min(100.6,100.9) − 100.0 = 0.6`, `range = 1.0`, `wick_ratio = 0.6 ≥ 0.5` ✓.
- `stop = 100.0 − 0.3×1.0 = 99.7`; `entry = 100.9`; `stop_dist = 1.2 = 1.2 ATR` ✓.
- `target = 100 + 0.75×8 = 106.0`; `rr = (106 − 100.9)/1.2 = 4.25 ≥ 1.5` ✓. `edge_dist_atr = (100.9 − 100)/2 = 0.45`.
- Beklenen: `signal=True`, `planned_target=106.0`, `rr=4.25`, `reasons="R1_long:range,edge_zone,reject_wick,stop_ok,rr_ok"`.
- `rh = 102` ile: `target = 100 + 0.75×2 = 101.5`, `rr = (101.5 − 100.9)/1.2 = 0.5 < 1.5` → `skip_reason="rr_below_min"`.
- `rh = 103.6` ile: `target = 100 + 0.75×3.6 = 102.7`, `rr = 1.8/1.2 = 1.5 == rr_min` → geçer (sınır).
- `edge_zone_atr = 0.25`, `l = 100.6` (bölge dışı, `> 100.5`) → aday yok.

### 8.5 R1 short (ayna)

Aynı `rl=100`, `rh=108`, `atr_4h=2`, `atr_tf=1.0`; mum `o=107.4, h=108.0, l=107.0, c=107.1`. `h ≥ rh − zone = 107.5` ✓; `c < 108` ✓; `upper_wick = 108.0 − 107.4 = 0.6`, `wick_ratio = 0.6` ✓. `stop = 108 + 0.3 = 108.3`; `entry = 107.1`; `stop_dist = 1.2` ✓; `target = 108 − 6 = 102.0`; `rr = (107.1 − 102)/1.2 = 4.25` ✓; `edge_dist_atr = (108 − 107.1)/2 = 0.45`.

### 8.6 R1 çakışma (`pick_candidate`)

`rl = 100`, `rh = 100.8`, `zone = 0.5`; mum `o=c=100.4, h=100.8, l=100.0`: long (`l ≤ 100.5`, `c > 100`, `lower_wick = 0.4/0.8 = 0.5`) ve short (`h ≥ 100.3`, `c < 100.8`, `upper_wick = 0.4/0.8 = 0.5`) ikisi de tetik koşulunu sağlar → `pick_candidate` `side=None`, `signal=False`, `skip_reason="other"`, `reasons="conflict:long_short"`. T1 long adayı ile R1 long adayı birlikte verilirse sonuç T1.

### 8.7 İz süren stop (`trail_stop_path`, long)

`fill_price = 100.5`, `initial_stop = 98.4` → `R = 2.1`, devreye giriş eşiği `102.6`, `trail_atr = 3.0`. Giriş mumundan itibaren üç kapanmış mum: `highs = [102.0, 103.0, 102.8]`, `atrs = [1.0, 1.0, 2.0]`.
- `k=0`: `hh = 102.0 < 102.6` → devrede değil → `stop = 98.4`.
- `k=1`: `hh = 103.0 ≥ 102.6` → devrede; `cand = 103 − 3×1.0 = 100.0` → `stop = max(98.4, 100.0) = 100.0`.
- `k=2`: `hh = 103.0`; `cand = 103 − 3×2.0 = 97.0` → `stop = max(100.0, 97.0) = 100.0` (geri çekilmez).
- Beklenen seri: `[98.4, 100.0, 100.0]`. Short ayna: `fill = 99.5`, `initial = 101.6` (`R = 2.1`, eşik `97.4`), `lows = [98.0, 97.0, 97.2]`, `atrs` aynı → `[101.6, 100.0, 100.0]`.

### 8.8 Çıkış yardımcıları

- `time_stop_due(47) = False`, `time_stop_due(48) = True` (giriş mumu dahil kapanmış mum sayısı).
- `target_reached("long", 106.0, bar_high=105.9, bar_low=…) = False`; `bar_high=106.0 → True`. Short: `target_reached("short", 102.0, bar_high=…, bar_low=102.1) = False`; `bar_low=102.0 → True`.
- `regime_flip_exit("long", "trend_down") = True`; `("long", "range") = False`; `("long", "volatile") = False`; `("short", "trend_up") = True`.

## 9. Test kapsamı (özet)

(a) `signals.py`: Bölüm 8'in tüm örnekleri; değişmezlik (rastgele ve elle serilerde `[0:k]` eşitliği); `ledger.PARAM_SPECS`/`regime.RegimeParams` uyum testi; girdi doğrulama; tüm sütun/dtype sözleşmesi; sınır eşitlikleri; NaN/bozuk mum yayılımı; T1 tam ayna simetrisi (fiyatı `2·P − p` aynalayınca long ↔ short). (b) Bağdaştırıcı: sahte freqtrade nesneleriyle geri çağrı sırası (kapı → veto → risk → karar yazımı), `LedgerError` → `False`, çıkış eşlemesi, `custom_data` dondurma, backtest/canlı mod ayrımı. Uçtan uca backtest (sentetik veri, deterministik tekrar) bu belgenin kapsamı dışıdır.

## 10. Kapsam dışı

Veto servisi gerçek mantığı; ders servisi; hyperopt/tarama betikleri; Telegram; `pyproject.toml`/Docker imajına `trader_core` yükleme adımı; 1g filtresi (PA-FLT-01 eki, strateji-v1 Bölüm 2); 15m kolunun walk-forward kabul kararı (yalnızca `trigger_tf` anahtarı vardır).

## 11. Belirsizlikler ve çözümleri; uyumsuzluklar

| # | Konu | Bulgu / çözüm |
|---|---|---|
| 1 | `trigger_tf` yazımı | strateji-v1 `1s`/`15dk` der; ledger ve bu belge `"1h"`/`"15m"` (ledger değerleri esas; yalnızca adlandırma farkı, anlam aynı) |
| 2 | Parametre aralıkları üç yerde | strateji-v1 6.1, `ledger.PARAM_SPECS` ve `regime.RegimeParams` aralıkları **eşit** (9 anahtar; ders sınırları ve adımlar eşit; ders parametreleri 2, 5, 6, 7, 8). Uyuşmazlık bulunmadı; kaynak ayrışmasın diye uyum testi zorunlu kılındı (Bölüm 2) |
| 3 | `veto_status` ve `entered` | ledger `entered` için `allowed` ister; stub `not_evaluated` dönüyor. Çözüm: adaptör stub durumunda `allowed` + `veto_reason="not_evaluated:v1_stub"` yazar (Bölüm 4.6). Gerçek uyumsuzluk |
| 4 | Stop geri bakışı "son 5 mum" tetik mumu içeriyor mu | Evet (`t−4…t`) |
| 5 | R1 `stop_width` ile `rr` süzgeç sırası | Önce `stop_width`, sonra `rr_below_min` |
| 6 | `day_start_equity` tanımı | Gün başı gerçekleşmiş özsermaye (cüzdan toplamından bugünkü kapanan işlem kâr/zararı çıkarılarak); gün başındaki gerçekleşmemiş kâr/zarar dahil değil. `risk.py` gün başı özsermayeyi "gerçekleşmemiş dahil" bekliyor olabilir; fark, açık pozisyon varken gün başında marjinal (günlük sınıra yaklaşmayı biraz erken/geç yapabilir). Gerçekleme sonrası backtest/dry-run ile doğrulanacak |
| 7 | Hedef/zaman çıkışı bar içi mi kapanış mı | Kapanmış mumda değerlendirilir, sonraki açılışta piyasa; hedef bar içi limit değil (v1 sadeliği, backtest = canlı). strateji-v1 5.5 "tek hedef" der, emir türünü belirtmez |
| 8 | Rejim dönüşü çıkışı gecikmesi | "1s kapanışında çık" ifadesi; hizalama gereği etiket bir mum gecikmeli görülür (4s kapanışıyla aynı anda kapanan mum önceki etiketi görür). Kabul edildi |
| 9 | 15m kolunda 48 mum ve 5 mum geri bakışı | strateji-v1 15m kolu için "aynı kurallar, tetik ve stop 15m'ye alınır" der; sayılar tetik TF mumu cinsinden uygulanır (48×15dk = 12 saat). Ayrı karar gerekirse yeni sabit değil, backtest bulgusu |
| 10 | `edge_dist_atr` hangi ATR | 4s ATR (aralık ve bölge 4s nesneleri) |
| 11 | Çift yönlü R1 çakışması | Hiçbiri; strateji-v1 sessiz |
| 12 | Freqtrade sürümüne bağlı noktalar (imaj `2026.10`) | Gerçeklemede doğrulanacak: `order_filled` geri çağrısının backtest'te de çağrılması ve ilk `custom_stoploss`'tan önce gelmesi; `custom_data` API'si; `wallets.get_total` kapsamı (gerçekleşmemiş kâr/zarar, `tradable_balance_ratio=0.99` etkisi); `funding_fees` işareti; `stoploss_on_exchange` ile `custom_stoploss` güncelleme aralığı; `__init__`'te `timeframe` atamasının `config["timeframe"]` (şu an `"1h"`) ile etkileşimi |
| 13 | İç hata kapsamı | Canlıda fail-closed, backtest'te yayılır |
| 14 | `trader_core` paketinin freqtrade imajında bulunması | `docker-compose.yml` yalnızca `user_data/strategies`'i bağlar; `src/trader_core` için bağlama/kurulum ayrı adım (kapsam dışı) |


### Kütüphane kurulumlarında risk/ödül tabanı yok (sahip kararı, 26.11)

Kazanç/risk tabanı ve ATR cinsinden stop üst sınırı kütüphane kurulumlarında BİLEREK yoktur (sahip kararı, 26.11): ML1 zayıf oranlı adayları da görür; `rr_below_min` burada yalnız "hedef yanlış tarafta" demektir.
