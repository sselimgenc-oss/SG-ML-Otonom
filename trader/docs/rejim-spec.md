# Rejim etiketi — arayüz ve kurallar (spesifikasyon v1, 16 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


Kaynak kural: `otonom-trading-arastirma/strateji-v1.md` Bölüm 2, 3 ve 6. Bu belge o bölümlerdeki rejim kurallarını koda dökülebilir hale getirir; sayılar kârlılık kanıtı değil, backtest ile sınanacak başlangıç değerleridir. Bu belge kod ve test içermez; testler bu belgeden yazılır.

Modüller:
- `src/trader_core/indicators.py` — EMA, SMA, true range, ATR (Wilder). Yalnızca pandas + numpy.
- `src/trader_core/regime.py` — etiketleme, range kenarları, 4s → 1s hizalama. `indicators.py`'yi kullanır.

Bu iki modül `risk.py`'nin aksine freqtrade'e bağlı değildir ama saf Python da değildir: **pandas ve numpy gerekir.** Karar: girdi pandas `DataFrame` (freqtrade'in yerel biçimi). Venv'de şu an yalnızca pytest/pyyaml var; `pyproject.toml` `dependencies` listesine `pandas>=2.0` ve `numpy>=1.26` eklenecek (freqtrade ikisini de zaten getirir, ayrı bir yük değil). Bu ekleme koda geçerken ayrı adım olarak yapılır; bu belge `pyproject.toml`'a dokunmaz.

## Etiket kümesi

`Regime(str, Enum)`; değerler (DataFrame'de saklanan metin) şunlardır:

| Üye | Değer | Anlam |
|---|---|---|
| `TREND_UP` | `"trend_up"` | Trend yukarı |
| `TREND_DOWN` | `"trend_down"` | Trend aşağı |
| `RANGE` | `"range"` | Tanımlı range (RH/RL geçerli) |
| `VOLATILE` | `"volatile"` | Volatilite çok yüksek |
| `UNCLEAR` | `"unclear"` | Belirsiz, veri yetersiz veya veri bozuk |

`volatile` ve `unclear` etiketinde yeni işlem açılmaz (strateji-v1 Bölüm 3). `RegimeResult.tradeable` yalnızca `trend_up`, `trend_down`, `range` için `True`. Etiketi tüketen kod (strateji, veto, ders servisi) yalnızca bu beş metni bilir.

## Parametreler

`RegimeParams` (frozen dataclass). Rejim modülü yalnızca strateji-v1 Bölüm 6.1'deki 1–3 numaralı parametrelere sahiptir; 4–8 kurulum (T1/R1) parametreleridir, bu modülde yoktur. `edge_zone_atr` R1 ile ortaktır: R1 aynı `RegimeParams` nesnesinden okur, kopya tutmaz.

| Alan | Varsayılan | Geçerli aralık (doğrulama, uçlar dahil) | Ders servisi | Ders servisi sınırı |
|---|---|---|---|---|
| `range_width_atr` | 4.0 | 3.0 – 6.0 | Hayır | — |
| `vol_ratio_max` | 1.5 | 1.25 – 2.0 | Evet | 1.3 – 1.7 |
| `edge_zone_atr` | 0.25 | 0.15 – 0.50 | Hayır | — |

- Geçerli aralık, backtest tarama aralığıdır (strateji-v1 6.1). Aralık dışı, sonlu olmayan (NaN/inf), `bool`, `None`, metin, sayı olmayan değer → `ValueError` (`__post_init__`). Tarama adımı (0.5, 0.25, 0.05) doğrulanmaz; adım yalnızca tarama betiğinin işidir.
- Modül sabiti `DEFAULT_PARAMS = RegimeParams()`.
- Modül sabiti `LESSON_BOUNDS = {"vol_ratio_max": (1.3, 1.7)}`. Ders servisi yalnızca bu anahtara dokunabilir; `RegimeParams` bunu **zorlamaz** (backtest 1.25–2.0 taramak zorunda), zorlama ders servisinin işidir. Backtest sonrası sınırların yeniden ortalanması ders servisi modülünün konusudur, bu modülün değil.
- Sayı kabulü `risk-kilidi-spec.md` ile aynı: `int`/`float` veya `numbers.Real` (numpy dahil), `float()` ile dönüştürülür; `bool`, `None`, metin, NaN, inf geçersiz.

Sabitler (taranmaz, `regime.py` modül sabiti; parametre değildir, `RegimeParams`'a girmez):

| Sabit | Değer |
|---|---|
| `ATR_LEN` | 14 |
| `EMA_FAST`, `EMA_MID`, `EMA_SLOW` | 20, 50, 100 |
| `RANGE_WINDOW` | 20 |
| `MIN_EDGE_TOUCHES` | 2 |
| `VOL_AVG_WINDOW` | 100 |
| `MIN_BARS` | 113 (aşağıda türetildi) |

## Girdi sözleşmesi

- `df`: `pandas.DataFrame`; sütunlar `open`, `high`, `low`, `close` zorunlu. `volume` rejim için kullanılmaz; varsa yok sayılır, yoksa hata değil.
- Satır = **kapanmış** mum. Oluşmakta olan son mumu çıkarmak çağıranın sorumluluğudur (freqtrade'de `populate_indicators` zaten kapanmış mumları verir; canlıda son satırın kapanmış olduğu doğrulanır).
- İndeks: kesin artan (strictly increasing) ve tekrarsız. Zaman damgası olması `classify_series` için şart değil; `align_to_base` için `DatetimeIndex` şart (mum **açılış** zamanı, freqtrade `date` sütunu `set_index("date")` ile indeks yapılır).
- Yapısal bozukluk (DataFrame değil, zorunlu sütun yok, indeks artan değil/tekrarlı) → `ValueError`. Değer bozukluğu (NaN, sonsuz, `high < low`, `open/high/low/close ≤ 0`, `close` aralık dışı yani `close > high` veya `close < low`, `open` aralık dışı) → istisna **değil**; o mum "geçersiz mum" sayılır ve etiketi `unclear` olur (aşağıda).
- Fonksiyonlar girdiyi değiştirmez (yerinde değişiklik yok).

## `indicators.py` — kesin formüller

Tüm fonksiyonlar girdiyle aynı indeksli `pandas.Series` döner, girdiyi değiştirmez, ileriye bakmaz (çıktı[t] yalnızca girdi[≤ t]'ye bağlıdır). `length` tam sayı ≥ 1 olmalı, değilse `ValueError`.

### Ortak ısınma ve NaN kuralı

- Gerçek gözlem = NaN olmayan girdi değeri. Çıktı[t], ancak `t` dahil o ana kadar en az `length` gerçek gözlem birikmişse geçerlidir; öncesi `NaN` (ısınma). Bu, referans depodaki davranıştan bilinçli sapmadır (referans ısınma bölgesinde de sayı döndürür; biz döndürmeyiz, yanlış güvenin önüne geçmek için).
- Girdi[t] NaN ise çıktı[t] = NaN; iç durum (özyineleme değeri) **değiştirilmeden** taşınır, sonraki gerçek gözlem son durumdan devam eder. Başta gelen NaN'lar atlanır (özyineleme ilk gerçek gözlemle başlar).
- `±inf` girdi → `ValueError` (fonksiyon düzeyinde). Rejim katmanı infi önceden geçersiz mum olarak ayıklar, indicators'a NaN verir.

### `ema(series, length) -> pd.Series`

`α = 2 / (length + 1)`. İlk gerçek gözlem `x₀` için `e₀ = x₀`; sonra `e_t = α·x_t + (1 − α)·e_{t−1}`. Tohum ilk değerdir (SMA tohumu değil); pandas karşılığı `series.ewm(span=length, adjust=False).mean()`, ısınma bölgesi NaN'a çevrilmiş hali. Sonuç: yeterince uzun geçmişte (≳ 3·length) tohum etkisi ihmal edilir, ama kısa geçmişte etiket geçmiş uzunluğuna hafifçe bağlıdır (bkz. "Geçmiş uzunluğu" notu).

### `sma(series, length) -> pd.Series`

Son `length` değerin aritmetik ortalaması; penceredeki herhangi bir NaN → NaN (`min_periods=length`). Rejim katmanı ATR ortalaması için kullanır.

### `true_range(df) -> pd.Series`

`TR_t = max(high_t − low_t, |high_t − close_{t−1}|, |low_t − close_{t−1}|)`.
- İlk satırda (önceki kapanış yok) ve önceki kapanışı NaN olan satırlarda `TR_t = high_t − low_t` (yalnızca mevcut terimler arasından max; pandas `max(axis=1)` skipna davranışı).
- `high_t` veya `low_t` NaN ise `TR_t = NaN`.
- Isınma yok (TR ilk satırdan itibaren tanımlı).

### `atr(df, length=14) -> pd.Series`

Wilder yumuşatması: `α = 1/length`; ilk gerçek `TR` için `ATR₀ = TR₀`; sonra `ATR_t = ATR_{t−1} + (TR_t − ATR_{t−1}) / length`. Pandas karşılığı `true_range(df).ewm(alpha=1/length, adjust=False).mean()` + ortak ısınma kuralı (ilk `length − 1` gerçek gözlem NaN, ATR ilk kez indeks `length − 1`'de geçerli). Wilder'ın klasik tanımındaki "ilk `length` TR'nin SMA'sı ile tohumlama" **kullanılmaz** (uzun geçmişte fark ihmal edilir; ikisini karıştırmamak için bu belgede tek tanım budur).

## `regime.py` — arayüz

```
class Regime(str, Enum): TREND_UP, TREND_DOWN, RANGE, VOLATILE, UNCLEAR   # değerler yukarıdaki tabloda

@dataclass(frozen=True)
class RegimeParams: range_width_atr: float = 4.0; vol_ratio_max: float = 1.5; edge_zone_atr: float = 0.25

@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    rh: float | None            # yalnızca regime == RANGE iken dolu, değilse None
    rl: float | None
    rh_touches: int             # yalnızca RANGE iken anlamlı, değilse 0
    rl_touches: int
    atr: float | None           # ATR14 (sınıflandırılan mumda); hesaplanamadıysa None
    atr_ratio: float | None     # ATR14 / ort(ATR14, 100); hesaplanamadıysa None
    reason: str                 # kısa açıklama, ör. "ATR oranı 1.98 > 1.5"
    @property tradeable -> bool

def count_edge_touches(highs, lows, rh, rl, zone) -> tuple[int, int]
def classify_series(df, params=DEFAULT_PARAMS) -> pd.DataFrame
def classify_last(df, params=DEFAULT_PARAMS) -> RegimeResult
def align_to_base(regime_df, base_index, informative_hours=4) -> pd.DataFrame
```

### `classify_series(df, params) -> DataFrame`

`df` ile aynı indeksli; sütunlar ve dtype'lar:

| Sütun | dtype | İçerik |
|---|---|---|
| `regime` | `object` (str) | `Regime` değerinin metni; her satırda dolu, hiçbir zaman NaN |
| `rh`, `rl` | `float64` | Yalnızca `regime == "range"` satırlarında dolu, aksi `NaN` |
| `rh_touches`, `rl_touches` | `int64` | Yalnızca `range` satırlarında anlamlı; diğerlerinde 0 |
| `atr` | `float64` | ATR14; hesaplanamayan satırda NaN |
| `atr_ratio` | `float64` | ATR14 / ort(ATR14, 100); hesaplanamayan satırda NaN |

Gerçekleştirme (vektörel veya döngü) serbest; anlam aşağıdaki algoritmayla birebir aynı olmak zorunda. Fonksiyon deterministiktir ve yan etkisizdir.

### `classify_last(df, params) -> RegimeResult`

`classify_series`'in son satırını `RegimeResult`'a çevirir. **Hata durumunda her zaman kapalı:** her istisna (yapısal bozukluk dahil) `RegimeResult(UNCLEAR, None, None, 0, 0, None, None, reason="iç hata: ...")` olur; istisna dışarı sızmaz. (`classify_series` ise yapısal hatada `ValueError` verir; test ve backtest hatayı görmek ister.)

### `count_edge_touches(highs, lows, rh, rl, zone) -> (rh_touches, rl_touches)`

Saf yardımcı; testte tek başına doğrulanabilsin diye genel (pencere uzunluğu 20 ile sınırlı değil). `highs`, `lows` aynı uzunlukta, eski → yeni sıralı 1-boyutlu dizilerdir. `zone` ≥ 0 sonlu sayı (fiyat birimi, ATR değil). Tanım:
- Üst bölge: `high_i ≥ rh − zone`. Alt bölge: `low_i ≤ rl + zone`. Eşitlik bölgeye dahildir.
- Bir **dokunuş** = bölgede olan ardışık mumların bir **koşusu** (run). Ardışık mumlar tek dokunuş sayılır; iki dokunuşu ayıran asgari ayrım **bölge dışında en az 1 mum**dur. Başka eşik (ek ATR mesafesi, ek mum sayısı) yoktur.
- Pencerenin başında başlayan koşu (pencere öncesine taşan) pencere içinde görünen kısmıyla bir dokunuş sayılır.
- Sonuç iki tam sayıdır: üst bölge koşu sayısı, alt bölge koşu sayısı. Boş dizi → `(0, 0)`. Uzunlukları farklı dizi → `ValueError`.
- Bir mum hem üst hem alt bölgede olabilir (bölgeler çakışırsa); iki tarafta da ayrı sayılır.

## Sınıflandırma algoritması

Her satır `t` (4s mumu kapanışı) için, yalnızca `t` dahil önceki satırlar kullanılarak. Önce göstergeler:

- `ATR_t = atr(df, 14)[t]`.
- `EMA20_t`, `EMA50_t`, `EMA100_t = ema(close, ·)[t]`.
- `avgATR_t = sma(ATR, 100)[t]` (en son 100 ATR değeri, **t dahil**).
- `atr_ratio_t = ATR_t / avgATR_t`.
- Pencere `W_t` = indeksler `t−19 … t` (20 mum, t dahil; "son 20 kapanmış 4s mum" = kapanmış t mumu dahil son 20).

### Adım 0 — Geçerlilik (sırasız ön koşul; hiçbiri sağlanmazsa `unclear`)

Aşağıdakilerden biri doğruysa `regime = unclear`, `rh/rl = NaN`, touches = 0 ve sonraki adımlara geçilmez (göstergelerden hesaplanabilenler `atr`, `atr_ratio` sütunlarına yine yazılır):

1. `t < MIN_BARS − 1` (yani 0 tabanlı indeks 112'den önce): yetersiz geçmiş. `MIN_BARS = 113`: ATR14 ilk kez indeks 13'te geçerli; `sma(ATR,100)` için 100 geçerli ATR gerekir → indeks 13 + 99 = 112 → 113 mum. EMA100 indeks 99'dan, range penceresi indeks 19'dan itibaren zaten hazırdır; sınırlayıcı olan ATR ortalamasıdır.
2. Mum `t` geçersiz (NaN, sonsuz, `high < low`, `open/high/low/close ≤ 0`, `open` veya `close` `[low, high]` dışında). Geçersiz mum göstergelere NaN olarak girer (bkz. NaN kuralı); böylece bir geçersiz mum, penceresi kapsadığı sürece sonraki satırları da `unclear` yapar (ör. `W_t` içinde NaN → aşağıdaki NaN kontrolü).
3. `ATR_t`, `EMA20_t`, `EMA50_t`, `EMA100_t`, `avgATR_t` veya `W_t` içindeki herhangi bir `high`/`low` NaN.
4. `ATR_t ≤ 0` veya `avgATR_t ≤ 0` (düz fiyat, sıfır ATR): oran tanımsız, hiçbir etiket güvenilir değil → `unclear`.

### Adım 1 — Volatil

`atr_ratio_t > vol_ratio_max` (kesin büyük) → `volatile`. (PA-FLT-03.) RH/RL verilmez.

### Adım 2 — Range

- `RH_t = max(high[W_t])`, `RL_t = min(low[W_t])`.
- `width_t = (RH_t − RL_t) / ATR_t`.
- `zone_t = edge_zone_atr × ATR_t` (**t anındaki tek ATR değeri**; pencere boyunca sabit, bar başına ATR kullanılmaz).
- `(rh_touches, rl_touches) = count_edge_touches(high[W_t], low[W_t], RH_t, RL_t, zone_t)`.
- Koşul: `width_t ≤ range_width_atr` (eşitlik dahil) **ve** `rh_touches ≥ 2` **ve** `rl_touches ≥ 2` → `range`; `rh = RH_t`, `rl = RL_t`, touches dolu.
- Koşul tutmazsa touches/RH/RL çıktıya yazılmaz (0 / NaN) ve Adım 3'e geçilir.
- Range, trendin **önünde** gelir: güçlü eğimli ama dar penceredeki bir hareket `range` etiketi alabilir (strateji-v1 sırası böyle; bu belge sırayı değiştirmez).

### Adım 3 — Trend

- `close_t > EMA100_t` ve `EMA20_t > EMA50_t` → `trend_up`.
- `close_t < EMA100_t` ve `EMA20_t < EMA50_t` → `trend_down`.
- İki koşul grubu birbirini dışlar; eşitlik (`==`) iki gruba da girmez.

### Adım 4 — Belirsiz

Hiçbiri tutmadıysa `unclear`.

### İleriye bakmama (no-lookahead) kuralı

1. Etiket[t], yalnızca `df` satır `0…t`'ye bağlıdır. Bunu doğrulayan değişmezlik: `classify_series(df)[0:k]` ile `classify_series(df.iloc[:k])` tüm sütunlarda **birebir aynı** olmalıdır (her `k ≥ 1` için; NaN'lar eşit sayılır). Test yazarı bunu rastgele ve elle kurulmuş serilerde kontrol etmelidir.
2. EMA ve ATR özyinelemesi tohumu ilk satırdan aldığı için etiket, verilen **geçmişin başlangıcına** bağlıdır (daha uzun geçmiş verince EMA/ATR hafifçe değişir). Bu ileriye bakma değildir ama tekrarlanabilirlik için: backtest ve canlı aynı başlangıç noktasından, yani yeterince uzun (öneri: ≥ 300 adet 4s mum, freqtrade `startup_candle_count = 300` ve 4s informative için aynı) geçmişle çalışmalıdır. Spesifikasyonun kesin garantisi yalnızca (1)'dir.
3. Pencere ve ortalamalarda hiçbir yerde `shift(-1)`, merkezli pencere veya t'den sonraki satır yoktur.

## 4s etiketinin 1s mumlarına bağlanması — `align_to_base`

`align_to_base(regime_df, base_index, informative_hours=4) -> DataFrame`

- `regime_df`: `classify_series` çıktısı, `DatetimeIndex` (4s mumlarının **açılış** zamanı). `base_index`: 1s mumlarının açılış zamanları (`DatetimeIndex`, artan; `regime_df` ile aynı saat dilimi/naiflik, aksi `ValueError`).
- 4s mumu `O` açılışlı ise **kapanış zamanı** `C = O + informative_hours`.
- 1s mumu `T` açılışlı ise kullanabileceği etiket, `C ≤ T` olan **en büyük C**'ye sahip 4s mumunundur (yani 4s mumunun kapandığı anda **açılan** 1s mumundan itibaren). Eşitlik kullanılabilir: `C == T` olan 1s mumu o etiketi kullanır. Bu, "4s verisi 1s'e bir mum kaydırılarak birleştirilir" kuralıdır ve freqtrade `merge_informative_pair`'in ffill davranışıyla aynı sonucu verir; 4s kapanışıyla aynı anda **kapanan** 1s mumu (açılışı `C − 1s`) hâlâ önceki etiketi kullanır.
- **Bayatlık sınırı:** etiket yalnızca `T − C < informative_hours` ise geçerlidir (yani 4s mumu `O` etiketi `[O+4s, O+8s)` aralığında açılan 1s mumlarına verilir). Eksik 4s mumu yüzünden daha eskiye düşülürse etiket `unclear` olur, ileri taşınmaz.
- Eşleşen 4s mumu yoksa (başlangıç) etiket `unclear`, `rh/rl = NaN`, touches 0.
- Çıktı: `base_index` ile aynı indeks, `regime_df` ile aynı sütunlar. 1s tarafında etiket 4s'in o anki halinden **yeniden hesaplanmaz**, sadece taşınır; `rh/rl` de taşınan değerdir.
- R1, giriş anında RH/RL'yi dondurur (strateji-v1 5.8); bu hizalama fonksiyonunun değil, kurulum modülünün işidir.

Örnek (saatler UTC, `informative_hours=4`): 4s mumu 08:00 açılışlı, 12:00'de kapanır.

| 1s mumu açılışı | Kullanılan 4s etiketi (açılış) |
|---|---|
| 08:00, 09:00, 10:00, 11:00 | 04:00 açılışlı mum (08:00'de kapandı) |
| 12:00, 13:00, 14:00, 15:00 | 08:00 açılışlı mum |
| 16:00 | 12:00 açılışlı mum (16:00'da kapandı) |
| 20:00, ama 12:00 açılışlı 4s mumu veride yok (en yeni 4s mumu 08:00 açılışlı, `C = 12:00`) | `T − C = 8s ≥ 4s` → `unclear` (bayat) |

## Hata kenarları (özet)

| Durum | Sonuç |
|---|---|
| Satır sayısı < 113 (indeks < 112) | `unclear` |
| Boş DataFrame | `classify_series` boş sonuç döner (yapısal hata değil); `classify_last` `unclear` döner |
| Tek satır | `unclear` |
| Satırda NaN/inf/`high<low`/≤0 fiyat | O satır `unclear`; pencere kapsadığı süre sonraki satırlar da `unclear` (pencere ATR için 100, EMA için sonsuz geriye doğru etkili; ayrıntı aşağıda) |
| Düz fiyat (tüm OHLC eşit) | `ATR = 0` → `unclear` |
| `ATR_t = 0` ama ortalama > 0 | `unclear` (adım 0.4) |
| Eksik mum (zaman boşluğu) | Bu modül zaman boşluğunu **görmez** (4s için indeks kontrolü yok); boşluğu temizleme/ileri doldurma çağıranın işidir. Yalnızca `align_to_base` bayat etiketi `unclear` yapar |
| Geçersiz `params` | `RegimeParams` oluşturulurken `ValueError` |

NaN yayılımı: indicators'ın "durum taşıma" kuralı nedeniyle tek bir NaN mumu EMA/ATR'yi kalıcı olarak bozmaz, ama o satırın değeri NaN'dır; `sma(ATR,100)` penceresinde NaN olduğu 100 satır boyunca NaN verir (o satırlar `unclear`), `W_t` penceresinde NaN olan 20 satır `unclear` olur. EMA'lar NaN satırın dışında geçerli kalır. Bu yüzden etkili sonuç: geçersiz bir mum en az sonraki 100 satır boyunca `unclear` üretir. Bu bilinçli ve muhafazakârdır (kapalı-hata).

## Elle hesaplanabilir örnekler

Test yazarı aşağıdakileri tam sayı/kesir aritmetiğiyle doğrulayabilir. Örnek 1 `indicators.py`'yi, Örnek 2 `count_edge_touches`'ı, Örnek 3 uçtan uca etiketleri sınar.

### Örnek 1 — EMA, TR, ATR (`length=3`)

EMA: `x = [2, 4, 8, 6]`, `length=3` → `α = 0.5`. `e = [2, 3, 5.5, 5.75]`. Isınma: ilk `length − 1 = 2` değer NaN → `ema(x,3) = [NaN, NaN, 5.5, 5.75]`.

TR / ATR, `length=3` (`α = 1/3`), mumlar (high, low, close):

| t | high | low | close | TR | gerekçe |
|---|---|---|---|---|---|
| 0 | 10 | 8 | 9 | 2 | önceki kapanış yok → `high−low` |
| 1 | 11 | 9 | 10 | 2 | `max(2, \|11−9\|=2, \|9−9\|=0)` |
| 2 | 13 | 10 | 12 | 3 | `max(3, \|13−10\|=3, \|10−10\|=0)` |
| 3 | 15 | 14 | 14.5 | 3 | `max(1, \|15−12\|=3, \|14−12\|=2)` (boşluk) |

`true_range = [2, 2, 3, 3]`. ATR özyinelemesi: `A₀=2`, `A₁=2`, `A₂=2+(3−2)/3=7/3≈2.3333`, `A₃=7/3+(3−7/3)/3=23/9≈2.5556`. Isınma: `atr(df,3) = [NaN, NaN, 7/3, 23/9]`.

### Örnek 2 — Dokunuş sayımı (`count_edge_touches`)

`rh=10`, `rl=8`, `zone=0.3` (üst eşik `9.7`, alt eşik `8.3`). Sekiz mum:

- `highs = [10, 9.9, 9.0, 9.8, 10, 9.0, 9.95, 9.2]` → bölgede mi (`≥ 9.7`): `T T F T T F T F` → koşular: `[0,1]`, `[3,4]`, `[6]` → **3** üst dokunuş.
- `lows = [8.0, 8.5, 8.4, 8.2, 8.9, 8.1, 8.8, 8.0]` → bölgede mi (`≤ 8.3`): `T F F T F T F T` → koşular: `[0]`, `[3]`, `[5]`, `[7]` → **4** alt dokunuş.
- Beklenen: `(3, 4)`.

(Her satırda `low ≤ high` olduğuna dikkat: `lows[i] ≤ highs[i]` tüm i için sağlanıyor.)

Sınır: `highs=[10, 10, 10]` (hepsi bölgede) → üst **1** dokunuş (tek koşu); aynı mumlarla `zone=0` ve `highs=[10, 9, 10]` → **2**.

### Örnek 3 — Uçtan uca etiketler (150 mum, varsayılan `RegimeParams`)

Her üç senaryoda ATR sabit 2 olacak biçimde kuruldu; ATR özyinelemesi tohumu 2 ile başlayıp her adımda 2 kaldığı için `ATR_t = 2` tam eşittir. `t = 149` satırı kontrol edilir (`150 ≥ 113`).

**3a — Trend yukarı (merdiven).** `t = 0…149` için `open = 100+t`, `close = 101+t`, `high = close + 0.5`, `low = open − 0.5`.
- `TR₀ = 2`; `t ≥ 1` için `prev_close = 100+t`: `high−low = 2`, `|high − prev_close| = 1.5`, `|low − prev_close| = 0.5` → `TR_t = 2` → `ATR_t = 2`, `atr_ratio = 1` → volatil değil.
- Pencere `W₁₄₉`: `RH = high₁₄₉ = 101.5 + 149 = 250.5`, `RL = low₁₃₀ = 99.5 + 130 = 229.5`; `width = 21 / 2 = 10.5 > 4.0` → range değil.
- Doğrusal artan girdide EMA gecikir ve kısa EMA uzun EMA'dan yüksektir: `d_t = x_t − EMA_t = Σ_{k=1..t} (1−α)^k`, `α` küçüldükçe `d_t` büyür → `close > EMA20 > EMA50 > EMA100`.
- Beklenen `regime[149] = "trend_up"`, `rh = rl = NaN`. Fiyatları ayna alınan (azalan, pozitif kalan, TR yine 2) bir seri `trend_down` verir; test yazarı bunu aynı gerekçeyle kurar.

**3b — Volatil.** 3a'nın ilk 149 mumu (`t = 0…148`) aynen; `t = 149` mumu: `open = 249`, `low = 249`, `high = 279`, `close = 270` (`prev_close = 249`).
- `TR₁₄₉ = max(30, |279−249|=30, |249−249|=0) = 30`. `ATR₁₄₉ = 2 + (30−2)/14 = 4`.
- `avgATR₁₄₉` = indeks 50…149'un ATR ortalaması = `(99·2 + 4)/100 = 2.02`. `atr_ratio = 4/2.02 ≈ 1.9802 > 1.5` → `volatile`. Beklenen `regime[149] = "volatile"` (range ve trend koşullarına bakılmaz; `rh/rl = NaN`). `regime[148] = "trend_up"`.

**3c — Range (üçgen dalga).** Her mum için bir orta değer `m_t`: `t mod 8 = 0,1,2,3,4,5,6,7` için `m = 100,101,102,103,104,103,102,101`. `open = close = m_t`, `high = m_t + 1`, `low = m_t − 1`.
- `|m_t − m_{t−1}| ≤ 1` olduğundan `TR_t = 2` her satırda (`t=0` dahil) → `ATR = 2`, `atr_ratio = 1`.
- `t = 149`, `W = 130…149`. Zirveler (`t mod 8 = 4`): 132, 140, 148; çukurlar (`t mod 8 = 0`): 136, 144. `RH = 104+1 = 105`, `RL = 100−1 = 99`; `width = 6/2 = 3 ≤ 4` ✓.
- `zone = 0.25 × 2 = 0.5`. Üst bölge `high ≥ 104.5` ⇒ yalnız `m = 104` (zirveler) → koşular 132, 140, 148 → `rh_touches = 3`. Alt bölge `low ≤ 99.5` ⇒ yalnız `m = 100` → 136, 144 → `rl_touches = 2` (pencerede 128 yok; 130’dan başlıyor).
- Beklenen: `regime[149] = "range"`, `rh = 105`, `rl = 99`, `rh_touches = 3`, `rl_touches = 2`.
- Duyarlılık kontrolü: `range_width_atr = 3.0` (≥ 3) hâlâ range; `range_width_atr` 3.0 alt sınırında `width = 3 ≤ 3.0` eşitlik dahil → `range` (eşitlik testi). `edge_zone_atr = 0.15` → zone 0.3: üst bölge `high ≥ 104.7` → yine yalnız `m=104`; aynı sonuç.

Ek tek satırlık beklentiler: ilk 112 satır (indeks 0…111) her senaryoda `unclear` (yetersiz geçmiş); `classify_series(df.iloc[:112])` tamamı `unclear`; `classify_series(df.iloc[:113])`'ün son satırı sınıflanabilir (`unclear` olmayabilir). Tümü sabit fiyat (`open=high=low=close=100`, 150 mum) → son satır `unclear` (ATR = 0).

## Kaynak ve atıf (MIT)

Referans: `regime-trading-bot` (https://github.com/danny123-sudo/regime-trading-bot, incelenen commit `508d7d9157f7597acf6de276cc517b70548775e3`), MIT Lisansı, `Copyright (c) 2026 danny123-sudo`. Yalnızca statik okundu; çalıştırılmadı, kurulmadı, içe aktarılmadı. Kod doğrudan kopyalanmayacak, uyarlanacak; yine de "önemli bir bölümü" sayılabilecek türetme olduğundan MIT bildirimi korunur.

Türetilen bölümler:
- `indicators.py`: `_wilder` (ewm, α=1/length), `ema` (ewm, `adjust=False`), `sma`, `true_range`, `atr` gösterge matematiği ve fonksiyon imzaları (`core/indicators.py` 25–48. satırlar) — formüller aynı, **sapmalar:** ısınma bölgesi NaN, NaN durum taşıma kuralı, giriş doğrulaması.
- `regime.py`: iskelet — `Regime(str, Enum)` + `RegimeResult` dataclass (`regime`, `reason`, `tradeable` özelliği) + `classify` fonksiyon deseni, `reason` metni (`core/regime.py` 15–51. satırlar). **Alınmayanlar:** ADX/Bollinger/Keltner/Ichimoku/squeeze tabanlı koşullar ve eşikler, `confidence`, `BREAKOUT_WATCH`, `strategy_allows_entry`, `size_multiplier_for`. Etiket kümesi, koşullar, eşikler, RH/RL ve dokunuş sayımı **strateji-v1'den**dir, referanstan değil.
- Test düzeni: `tests/test_indicators.py` (elle özyineleme ile EMA karşılaştırması, TR'nin üç ölçüden en genişini alması) ve `tests/test_regime.py` (yardımcı üretici ile alan geçersiz kılma deseni) test **stili** olarak alınır; test içerikleri bu belgeden yeniden yazılır, referans testlerin kapsam yüzdesi devredilmez.

Zorunlu başlık (hem `indicators.py` hem `regime.py` dosyasının en üstünde, modül docstring'inden önce yorum olarak):

```
# Portions of this file (indicator math and the regime-label interface skeleton)
# are adapted from regime-trading-bot (https://github.com/danny123-sudo/regime-trading-bot,
# commit 508d7d9), licensed under the MIT License.
#
# MIT License
#
# Copyright (c) 2026 danny123-sudo
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Modifications: NaN warm-up, state-carrying NaN policy, label set and all
# classification rules are original to this project (see docs/rejim-spec.md).
```

Ayrıca depo kökünde (veya `docs/`) bir `THIRD_PARTY_NOTICES` girdisi bu atfı listeler; başlık yorumu tek başına yeterli kabul edilmez, ikisi de tutulur.

## strateji-v1'deki belirsizlikler ve bu belgedeki çözümleri

| # | Belirsizlik | Çözüm |
|---|---|---|
| 1 | "Son 20 kapanmış mum" t mumunu içeriyor mu | Evet, `t−19…t`; etiket t kapanışında verilir |
| 2 | `ort(ATR14, 100)` t'yi içerir mi, kaç mum gerekir | Evet, t dahil son 100 ATR14; bu yüzden `MIN_BARS = 113` |
| 3 | Kenar bölgesinde hangi ATR | t anındaki tek ATR14 (pencere boyunca sabit); bar bazlı ATR yok |
| 4 | "Ardışık mumlar tek dokunuş" ve asgari ayrım | Koşu = tek dokunuş; ayrım = bölge dışında ≥ 1 mum; ek eşik yok |
| 5 | Eşitlik durumları (`≤ range_width_atr`, bölge sınırı, `> vol_ratio_max`) | Metindeki gibi: width `≤` dahil, bölge sınırı dahil, volatil kesin `>`; trend eşitliği `unclear` |
| 6 | Range, trendden önce geliyor: dar pencerede güçlü hareket range olabilir | Sıra korundu, değiştirilmedi; backtest'te izlenecek zayıf nokta |
| 7 | ATR = 0 / düz fiyat | `unclear` (strateji-v1 sessiz) |
| 8 | Yetersiz geçmiş, geçersiz mum | `unclear`; fail-closed (strateji-v1 sessiz) |
| 9 | "Bir mum kaydırarak birleştirme" | 4s etiketi, 4s mumu kapandığı anda **açılan** 1s mumundan itibaren geçerli; bayatlık sınırı 4s |
| 10 | EMA/ATR tohumu | İlk değer tohumu, ısınmada NaN (SMA tohumu değil); uzun geçmişle çalışma önerisi |
| 11 | `edge_zone_atr` R1 ile ortak | Tek `RegimeParams` nesnesinden okunur |
| 12 | `range_width_atr` ve `edge_zone_atr` ders servisine kapalı | `LESSON_BOUNDS` yalnızca `vol_ratio_max`'ı içerir |
