# Claude API harcama koruması (bütçe) — arayüz ve kurallar (spesifikasyon v1, 16 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. LLM aylık bütçe **10 USD** (19 Kasım kullanıcı kararı: 30 USD önerisi geri alındı, tavan 10 USD kalır; veto 0,25 $/gün geçersiz); veto payı kaldırıldı (LLM veto yok); LLM aday önerisi açık, günlük adet sınırı yok.

Kaynak kararlar: `otonom-trading-arastirma/tasarim-kararlari.md` ("15–16 Kasım kararları", Claude API bütçesi maddesi ve MVP ek notu: limit dolarsa yeni işlem açılmaz, açık pozisyonlar SL/TP ile yönetilmeye devam eder), `mimari-taslak.md` (parça 5: analist + veto + harcama koruması; dosya yok/bayat/limit dolu → giriş yok), `research_notes/diger-hesap/gorev9_claude_api_maliyet.md` (fiyat tablosu, `usage` alanları, 400/429 davranışı, hata sınıfları).

Modül: `src/trader_core/budget.py`. Yalnızca standart kütüphane (`sqlite3`, `json`, `decimal`, `dataclasses`, `datetime`, `os`, `uuid`); anthropic SDK, pandas/numpy ve freqtrade import edilmez. Modül **hiçbir HTTP çağrısı yapmaz** ve **API anahtarını okumaz**; yalnızca "bu çağrıya izin var mı, ne kadar harcandı" sorusunu yanıtlar. Hata durumunda her zaman kapalı (fail-closed): bütçe doğrulanamıyorsa Claude çağrısı yapılmaz.

Bu belge kod, test veya commit içermez; yalnızca sözleşmedir. Aşağıdaki "Dondurulmuş arayüz" bölümündeki adlar, imzalar ve dönüş tipleri veto servisi ile ders servisi tarafından ortak kullanılır; değişiklik iki servisin spesifikasyonunu birlikte etkiler (bkz. Bölüm 12).

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Aylık sınır | Ayrı Console workspace, aylık limit 10 USD (Anthropic uygular; uygulama ayrıca kendi izler ve 10 USD'yi aşacak çağrıya izin vermez) |
| Günlük sınır | Servis başına, birbirinden bağımsız: `veto` 0,25 USD/gün, `lesson` 0,10 USD/gün. Ders, vetonun bütçesini yiyemez |
| Anahtarlar | İki ayrı anahtar (veto, ders), ortam değişkeninden gelir; dosyaya ve loga asla yazılmaz |
| Uyarılar | Günlük sınırın %70'inde uyarı; %100'ünde "durdu" mesajı; aylık izlenen toplam 5 USD'yi geçince ay başına tek uyarı; tahmini kredi bakiyesi 3 USD altına inince uyarı |
| Ön ödeme | 10 USD kredi, otomatik yükleme kapalı (Console ayarı; uygulama doğrulayamaz, operatör kontrol listesinde) |
| Sınıra dayanma | HTTP 400 (kendi limitimiz) veya 429 + `enforced_spend_limit_reached` → dur, yeniden deneme yok. Diğer 429 / 5xx / ağ hatası → sınırlı yeniden deneme + geri çekilme |
| Veto bütçesi bitince | Yeni giriş yok (fail-closed); açık pozisyonlar etkilenmez |
| Ders bütçesi bitince | O günün dersi atlanır, ertesi güne taşınmaz |
| Gün sınırı | **UTC** (00:00:00Z) |
| Saklama | Küçük SQLite dosyası, tek yazar kilidiyle serileştirilmiş, önce-rezerve-sonra-kapat (reserve-then-settle) |

## 2. Zaman ve para kuralları

- **Gün anahtarı** `YYYY-MM-DD` ve **ay anahtarı** `YYYY-MM`, ikisi de **UTC** takvimine göredir. Telegram günlük raporu 21:00 TR = 18:00 UTC olduğundan aynı UTC gününe düşer. Anthropic faturalama günü/ayı da UTC kabul edilir (doğrulanmalı; sapma olursa uygulama tarafı daha erken kapanmış sayılır, kabul edilebilir).
- **Rezervasyonun günü, `authorize` anının gün anahtarıdır.** Çağrı gece yarısını aşıp `record` ertesi gün gelse bile maliyet rezervasyonun gününe yazılır (gün sınırında çifte veya eksik sayım olmaz). Ders servisinin Batch işi bu yüzden başladığı günün bütçesinden düşer.
- **Monoton saat.** Modül `meta.last_ts`'i (gördüğü en büyük zaman) saklar; etkin zaman `max(clock(), last_ts)`'dir. Sistem saati geri giderse gün anahtarı geriye dönmez (eski güne dönüp sayacı sıfırlamak mümkün olmaz). `clock` enjekte edilebilir (yalnızca test).
- Zaman damgaları metin: `YYYY-MM-DDTHH:MM:SS.mmmZ`, UTC, tz-naive reddedilir (defter-spec ile aynı kural).
- **Para içte tam sayı mikro-dolardır** (`micro` = 1e-6 USD, `int`). Float toplama hatası ve yüzde karşılaştırma belirsizliği olmaz. Dışarıya (status, olay, log) USD `float` (6 ondalık) olarak da verilir.
- Fiyat tablosu `Decimal` ile okunur (`Decimal(str(x))`); 1 USD / MTok = 1 µUSD / token olduğundan maliyet `token × fiyat` doğrudan µUSD'dir. **Her maliyet kaleminin toplamı tek seferde yukarı yuvarlanır (`ceil`)**; yani hata hep fazla saymak yönündedir, asla eksik değil.
- Sayı kabulü `risk-kilidi-spec.md` ile aynı: `int`/`float`/`Decimal`/`numbers.Real`; `bool`, `None`, metin, NaN, inf, negatif → geçersiz.

## 3. Yapılandırma: `config/budget.json`

Anahtar değerleri **burada yoktur**; yalnızca ortam değişkeni **adları** vardır.

```json
{
  "version": 1,
  "db_path": "user_data/budget.sqlite",
  "daily_cap_usd": {"veto": 0.25, "lesson": 0.10},
  "monthly_cap_usd": 10.0,
  "monthly_warn_usd": 5.0,
  "warn_fraction": 0.70,
  "prepaid_credit_usd": 10.0,
  "credit_start_ts": "2026-11-16T00:00:00.000Z",
  "credit_low_usd": 3.0,
  "price_safety_factor": 1.0,
  "prices_verified_on": null,
  "batch_multiplier": 0.5,
  "api_key_env": {"veto": "ANTHROPIC_API_KEY_VETO", "lesson": "ANTHROPIC_API_KEY_LESSON"},
  "reservation_ttl_s": {"veto": 600, "lesson": 108000},
  "retry": {"max_retries": 3, "base_s": 2.0, "factor": 2.0, "max_sleep_s": 20.0, "jitter": 0.2,
            "deadline_s": {"veto": 60, "lesson": 300}},
  "prices_usd_per_mtok": {
    "claude-haiku-5-5":  {"input": 0.10, "output": 0.50, "cache_write_5m": 0.125, "cache_write_1h": 0.20, "cache_read": 0.01},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write_5m": 2.50, "cache_write_1h": 4.00, "cache_read": 0.10}
  }
}
```

**Fiyat uyarısı (doğrulanmalı).** `prices_usd_per_mtok`, `batch_multiplier` ve model ID'leri `gorev9` notundan alınmıştır; notun kendisi Haiku 5.5 fiyatının "özetlenmiş çekimden" geldiğini ve ID'lerin yalnızca Batch sayfasından teyit edildiğini söyler. Kod hiçbir fiyatı sabit gerçek olarak içermez; tablo yalnızca bu dosyadadır. `prices_verified_on` operatör resmî fiyat sayfasıyla karşılaştırınca tarih (`"2026-11-xx"`) yazar; `null` iken `status().prices_verified=False` olur ve panel/Telegram günlük raporu "fiyatlar doğrulanmadı" satırı gösterir (engellemez). Fiyat değiştiğinde yalnızca bu dosya güncellenir; geçmiş kayıtlar eski fiyatla kalır (maliyet satıra yazılıdır).

`price_safety_factor` fiyat/tokenizer belirsizliği için tampon çarpanıdır (`≥ 1.0`).

### 3.1 Kilitli üst sınırlar (modül sabiti `HARD_LIMITS`, dict)

`daily_cap_usd.veto ≤ 0.25`, `daily_cap_usd.lesson ≤ 0.10`, `monthly_cap_usd ≤ 10.0`, `monthly_warn_usd ≤ monthly_cap_usd`, `warn_fraction ∈ (0, 1]` ve `≤ 0.70`, `price_safety_factor ≥ 1.0`, `batch_multiplier ≥ 0.5`, `max_retries ≤ 3`. Her fiyat > 0 ve sonlu. `BudgetConfig` daha gevşek değerle oluşturulursa `BudgetConfigError(ValueError)`. Daha sıkı değerler serbest. Bilinmeyen anahtar, eksik servis, eksik fiyat alanı, `db_path` boş → hata. `load_config(path) -> BudgetConfig`; modül `DEFAULT_PATH = "config/budget.json"` bilir.

Yapılandırma okunamaz/geçersizse: `authorize` her çağrıda `Denial(reason="config_invalid")` döner (fail-closed); `status()` `store_ok=False, config_ok=False` bildirir.

## 4. Dondurulmuş arayüz

```python
Service = Literal["veto", "lesson"]

@dataclass(frozen=True)
class Usage:                      # API yanıtındaki usage alanlarının birebir karşılığı
    input_tokens: int = 0                 # yalnızca son önbellek kesme noktasından sonrası (toplam girdi değil)
    output_tokens: int = 0                # düşünme tokenleri dahil
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    cache_read_tokens: int = 0

@dataclass(frozen=True)
class Grant:                      # authorize başarısı; record/release/report_error buna bağlanır
    grant_id: str                         # uuid4 hex
    service: Service
    est_micro: int
    day: str                              # UTC gün anahtarı (rezervasyon günü)
    created_at: str
    expires_at: str                       # created_at + reservation_ttl_s[service]

@dataclass(frozen=True)
class Denial:
    service: Service
    reason: str      # "daily_cap" | "monthly_cap" | "provider_blocked" | "store_unavailable"
                     # | "store_missing" | "config_invalid" | "invalid_request"
    detail: str      # insan okunur, anahtar/istem içeriği içermez
    retry_after: str | None   # UTC zaman damgası (bilinen en erken yeniden deneme); yoksa None

@dataclass(frozen=True)
class Settlement:
    ok: bool
    cost_micro: int                       # defterde sayılan kesin tutar
    overrun_micro: int                    # max(0, cost - est)
    day: str
    duplicate: bool                       # aynı grant ikinci kez kapatıldı (etkisiz)
    estimated_instead: bool               # usage geçersizdi/model bilinmiyordu; tahmin tutarı sayıldı
    code: str                             # "ok" | "duplicate" | "bad_usage" | "unknown_model" | "unknown_grant" | "store_error"

@dataclass(frozen=True)
class ErrorAction:
    kind: Literal["retry", "stop", "fail"]
    sleep_s: float                        # kind == "retry" iken beklenecek süre
    blocked_until: str | None             # kind == "stop" iken

def authorize(service: Service, est_cost_usd: float) -> Grant | Denial: ...
def record(service: Service, grant: Grant, actual_usage: Usage,
           model: str, batch: bool = False) -> Settlement: ...
def release(grant: Grant) -> None: ...            # çağrı HİÇ faturalanmadı (yanıt alındı: 4xx/5xx)
def report_error(service: Service, grant: Grant, attempt: int, status_code: int | None,
                 error_type: str | None = None, error_code: str | None = None,
                 message: str | None = None, retry_after_s: float | None = None) -> ErrorAction: ...
def estimate_cost(model: str, input_tokens: int, max_output_tokens: int,
                  cache_write_1h_tokens: int = 0, cache_write_5m_tokens: int = 0,
                  cache_read_tokens: int = 0, batch: bool = False) -> float: ...   # USD, ÜST SINIR tahmini
def status() -> BudgetStatus: ...
def pending_events() -> list[BudgetEvent]: ...
def ack_events(event_ids: Sequence[int]) -> None: ...
def api_key_env(service: Service) -> str: ...     # yalnızca ortam değişkeni ADI
```

Modül düzeyi fonksiyonlar, `load_config(DEFAULT_PATH)` ile kurulan tembel tekil bir `BudgetGuard` örneğine yönlendirir; testler ve özel yapılandırma için `BudgetGuard(config, clock=None)` sınıfı aynı yöntemleri sunar (modül fonksiyonları ince sarmalayıcıdır). **Dondurulan şey fonksiyon/yöntem adları, parametre adları/sırası, dönüş tipleri ve `Denial.reason` / `Settlement.code` / olay `kind` değerlerinin kümesidir.** Yeni alan eklemek (sonda, varsayılanlı) geriye uyumludur; mevcutları değiştirmek veya silmek değildir.

### 4.1 Genel davranış

- `authorize`, `record`, `release`, `report_error`, `status`, `pending_events`, `ack_events` **iş kuralı gereği istisna fırlatmaz**; her iç hata (`sqlite3.Error`, G/Ç, bozuk dosya, yapılandırma) `Denial`/`Settlement(ok=False)`/`BudgetStatus(store_ok=False)` olarak döner ve loglanır. İstisna yalnızca programlama hatası için (`service` geçersiz değer → `ValueError`; `Grant` farklı servise ait → `ValueError`). Çağıran `ValueError`'u da yakalayıp "bütçe yok" sayar.
- `estimate_cost` modeli fiyat tablosunda bulamazsa `BudgetConfigError` fırlatır; çağıran bunu "Claude çağrısı yok" sayar.
- Kullanım kalıbı (veto/ders servisleri):
  1. `est = estimate_cost(model, input_tokens=..., max_output_tokens=...)` — üst sınır: çıktıyı `max_tokens` kadar say, önbellek yazımını yazıldı say.
  2. `g = authorize(service, est)`; `Denial` ise **çağrı yapılmaz** (Bölüm 9).
  3. API çağrısı (`max_retries=0` ile; SDK'nın gizli yeniden denemeleri koruma dışı kalmasın; yeniden deneme döngüsü servisin kendisinde, `report_error` kararıyla).
  4. Başarıda `record(service, g, usage, model, batch)`; HTTP hata yanıtında `report_error`, sonunda `release`.
- Aynı `Grant` **yalnızca bir başarılı çağrıyı** kapsar. Retry yeni `authorize` gerektirmez (başarısız istek faturalanmaz), ama başarılı çağrı başına bir `record` yapılır.

## 5. Saklama ve eşzamanlılık

SQLite dosyası (`db_path`), **WAL yok**: `journal_mode=DELETE`, `synchronous=FULL`, `busy_timeout=5000` ms. Gerekçe: iki süreç (veto ve ders konteynerleri) aynı docker volume'ünü paylaşır; rollback günlüğü yalnızca dosya kilidine dayanır, WAL'in paylaşımlı bellek (`-shm`) şartı yoktur; yazma hacmi günde en fazla birkaç yüz satırdır. Dosya yerel dosya sisteminde olmalı (ağ paylaşımı olmaz). İzinler `0600`.

Her `authorize`/`record`/`release`/`report_error` işlemi **tek `BEGIN IMMEDIATE` işlemidir** (SQLite'ın dosya kilidi tek yazar sağlar). Bu, iki sürecin aynı anda aynı bütçeyi harcamasını engeller: kilit alan işlem toplamları okur, kararı verir, rezervasyonu yazar, `COMMIT` eder; ikincisi ancak sonra toplamları görür. Kilit 5 sn içinde alınamazsa `Denial("store_unavailable")`.

### 5.1 Şema (sürüm 1; `PRAGMA user_version=1`)

- `meta(key PRIMARY KEY, value)`: `schema_version`, `created_at`, `last_ts`.
- `reservations`: `grant_id TEXT PK`, `service`, `day`, `month`, `state ∈ {open, settled, released, expired}`, `est_micro`, `charged_micro`, `model NULL`, `batch INT`, `usage_json NULL`, `created_at`, `settled_at NULL`.
  `charged_micro` kuralı: `open`/`expired` iken `= est_micro`; `settled` iken gerçek maliyet; `released` iken `0`.
- `blocks(id=1 PK, blocked_until TEXT, reason, set_at)`: sağlayıcı kaynaklı küresel engel (Bölüm 8).
- `events(id AUTOINCREMENT, ev_key UNIQUE, kind, service NULL, day, ts, payload_json, acked INT)`.

Toplamlar **her seferinde satırlardan hesaplanır** (`SUM(charged_micro)`); ayrı sayaç tutulmaz, bu yüzden sayaç/satır sapması olamaz. Hacim küçüktür; indeks `(service, day)` ve `(month)`. Satırlar silinmez (en az 400 gün saklanır; sonra elle).

### 5.2 Çökme güvenliği: önce rezerve, sonra kapat

1. `authorize` işlemi `est_micro` kadar `open` satır yazar **ve bu tutar hemen kullanılmış sayılır** (`used = settled + open + expired`).
2. API çağrısı yapılır. Süreç burada çökerse satır `open` kalır → tutar zaten sayılıdır; **eksik sayım imkânsızdır**.
3. `record` satırı `settled` yapar ve `charged_micro`'yu gerçek maliyete **değiştirir** (tahmin düşer, gerçek yazılır). Gerçek tahminden büyükse (`overrun`) fazlası da yazılır; limit aşılabilir, ama bir sonraki `authorize` reddedilir ve `budget_overrun` olayı üretilir.
4. TTL (`reservation_ttl_s`) dolmuş `open` satırlar bir sonraki `authorize` içinde `expired` olur. **Tutar silinmez, serbest bırakılmaz**; `est` olarak sayılmaya devam eder (çökmüş çağrının faturalandığı varsayılır). Geç gelen `record` (`open` veya `expired` → `settled`) gerçek tutarı yazar; gerçek bilgi tahminden üstündür.
5. Zaman aşımı / bağlantı kopması gibi **yanıt alınamayan** çağrılarda `release` **çağrılmaz** (sunucu işlemiş ve faturalamış olabilir); rezervasyon `est` kadar sayılı kalır ve TTL'de `expired` olur.
6. `release` yalnızca **yanıtı alınmış hata** (4xx/5xx gövdesi var) için çağrılır: `open → released`, `charged=0`. `settled` satıra etkisizdir.

Bu nedenle `est` **üst sınır** olmalıdır; düşük tahmin yalnızca kısa süreli düşük sayımdır ve `record` ile düzelir, ama çökme anında düşük kalır. `estimate_cost` bu yüzden `max_output_tokens` esas alır.

### 5.3 Depo erişilemezken (fail-closed)

- Dosya açılamıyor/kilitlenemiyor/`database disk image is malformed`/şema sürümü koddan yeni/`meta` eksik → `authorize` `Denial("store_unavailable")`. Hiçbir durumda "bütçe bilinmiyor, izin ver" yoktur.
- **Bozuk dosya otomatik silinmez veya yeniden oluşturulmaz** (sayaç sıfırlanıp eksik sayım yaratılır). Dosya yoksa ve yanında `<db>.initialized` işaret dosyası da yoksa ilk kurulumdur: dosya + işaret oluşturulur. Dosya yok ama işaret var → `Denial("store_missing")` (silinmiş/kayıp volume). Operatör, yedekten geri yükler ya da dondurulmuş arayüze **dahil olmayan** `BudgetGuard.reinitialize(assumed_spent_today_usd: dict[Service, float])` ile yeni dosya açar; bu, bugünkü her servis için o tutarda `settled` "recovery" satırı ekler (Anthropic Console'daki bugünkü kullanımdan okunur).
- Anthropic'in Console workspace limiti (10 USD) bu modülden bağımsız son savunmadır; uygulama içi koruma çökse bile aylık zarar tavanı 10 USD'dir.

## 6. Maliyet hesabı (`record` ve `estimate_cost`)

`model` fiyat tablosunda `prices_usd_per_mtok[model]` ile aranır. İlgili `batch` ise tüm token kalemlerine `batch_multiplier` (0,5) uygulanır; önbellek ve Batch birleşir (notta belirtildiği gibi; doğrulanmalı).

```
cost_micro = ceil( price_safety_factor * ( 1 if not batch else batch_multiplier ) *
  ( input_tokens*P.input + output_tokens*P.output + cache_write_5m_tokens*P.cache_write_5m
    + cache_write_1h_tokens*P.cache_write_1h + cache_read_tokens*P.cache_read ) )
```

Fiyatlar USD/MTok olduğundan çarpım doğrudan µUSD verir.

- `usage` doğrulaması: beş alan da `int ≥ 0`. Geçersizse (negatif, `bool`, `None`, NaN) `record`, **tahmin tutarını** (`est_micro`) sayar, `Settlement(ok=False, estimated_instead=True, code="bad_usage")`; satır `settled` yapılmaz, `expired` kuralı sürer.
- Model tabloda yoksa aynı şekilde `code="unknown_model"`, tahmin sayılır, bir kez `unknown_model` olayı.
- API yalnızca toplam `cache_creation_input_tokens` verir ve 5m/1h kırılımı yoksa: tamamı `cache_write_1h_tokens` olarak geçirilir (pahalı olan; eksik sayım olmasın). `Usage` toplam girdi değildir: gerçek girdi `input_tokens + cache_write_* + cache_read` toplamıdır (Anthropic'te `input_tokens` yalnızca son kesme noktasından sonrasıdır); modül bunları ayrı fiyatlar, toplamı ayrıca düzeltmez.
- 100.000 token üstü Haiku 5.5 isteği daha pahalı banda girer (nota göre 0,50/2,50; doğrulanmalı). MVP istekleri ~7k token olduğundan tabloda ayrı bant yoktur. Toplam girdi (`input + cache_write + cache_read`) > 100.000 ise `estimate_cost` `BudgetConfigError` fırlatır (çağrı yapılmaz) ve `record` tahmin tutarını sayar (`code="bad_usage"`, `estimated_instead=True`).

## 7. `authorize` kuralları (sırayla; ilk ihlal `Denial`)

1. `service` geçerli, `est_cost_usd` sonlu ve `> 0` (aksi `invalid_request`). `est_micro = ceil(est * 1e6)`.
2. Yapılandırma geçerli değilse `config_invalid`; depo açılamıyorsa `store_unavailable` / `store_missing`.
3. Etkin zaman (monoton) hesapla; `day`, `month` çıkar. Süresi dolmuş `open` satırları `expired` yap.
4. **Sağlayıcı engeli:** `blocks.blocked_until > şimdi` → `provider_blocked` (`retry_after = blocked_until`). Engel iki servisi birden kapsar (aynı workspace/limit).
5. **Aylık:** `ay_toplamı(tüm servisler) + est > monthly_cap_usd` → `monthly_cap`; olay `monthly_stopped` (ay başına tek).
6. **Günlük:** `gün_toplamı(service) + est > daily_cap_usd[service]` → `daily_cap`; olay `daily_stopped_100` (servis+gün başına tek). `retry_after` = sonraki UTC gece yarısı.
7. Hepsi geçerse `open` satırı yaz, olayları üret (Bölüm 10), `Grant` dön.

`authorize` işlemi kendi rezervasyonunu da toplama katar: ikinci eşzamanlı çağrı birincinin rezervasyonunu görür. **Servisler birbirinin günlük bütçesini asla görmez** (kontrol yalnızca kendi servisinin toplamı); tek ortak sayaç aylıktır.

"Eşik" karşılaştırmaları tam sayıdır: `kullanılan_micro * 100 >= cap_micro * 70` (yüzde için `warn_fraction` 0,70 → `*100 ≥ *70`; genel biçim `kullanılan >= ceil(cap_micro * warn_fraction)`).

## 8. Hata sınıflandırma ve yeniden deneme (`report_error`)

`report_error`, HTTP yanıtı (veya ağ hatası) sonrası servisin ne yapacağını söyler; kendisi uyumaz ve çağrı yapmaz. `attempt` 1'den başlar (şu ana kadar yapılan başarısız deneme sayısı).

| Girdi | `kind` | Yan etki |
|---|---|---|
| 400 + `invalid_request_error` + mesajda `API usage limits` geçiyor (kendi org/workspace limitimiz; "specified API usage limits" / "workspace API usage limits") | `stop` | Küresel engel `blocked_until` = **sonraki UTC gece yarısı**; yarın tek yoklama çağrısına izin (hâlâ 400 ise yeniden engel). `release(grant)` otomatik. Olay `provider_limit_hit` |
| 429 + `error_code == "enforced_spend_limit_reached"` (katman tavanı) | `stop` | Küresel engel `blocked_until` = **sonraki ayın 1'i 00:00 UTC** (nota göre erişim o zaman döner; `retry-after` yoktur). Olay `provider_limit_hit` |
| Diğer 400 (şema, parametre) , 401, 402, 403, 404, 413 | `fail` | Engel yok; hata loglanır (anahtar/istem içeriği yazılmaz). `release` |
| 429 (diğer, ör. `rate_limit_error`, `ramp_limit_exceeded`), 408, 409, 5xx (529, 504 dahil), `status_code=None` (bağlantı/zaman aşımı) | `retry` | `sleep_s = min(max_sleep_s, base_s * factor^(attempt-1))` × `(1 ± jitter)`; `retry_after_s` verilmişse `max(sleep_s, min(retry_after_s, max_sleep_s))`. |
| `attempt > max_retries` veya toplam süre `deadline_s[service]` aşıldı | `fail` | Çağıran sonucu "Claude yok" sayar (veto: Bölüm 9). Yanıt alındıysa `release`; alınmadıysa rezervasyon `est` olarak kalır (5.2/5) |

`stop` iken `ErrorAction.blocked_until` doludur ve çağıran **aynı gün başka çağrı denemez**; sonraki `authorize` `provider_blocked` döner. Geçerli bir sınıflandırma yapılamıyorsa (bilinmeyen kod) `fail`. `report_error` yalnızca sınıflandırır; Batch API'nin workspace limitini hafifçe aşabileceği (nota göre) için ders işi küçük tutulur ve aşım `record` ile `overrun` olarak yazılır.

## 9. Servis davranış sözleşmesi (bu modülü çağıranlar için)

- **Veto servisi:** `Denial` (her neden) veya `report_error → stop/fail` sonrası: veto dosyasını **yazmaz** ya da `status="unavailable"` + `reason="budget_<reason>"` içeren geçerli bir belge yazar. İkisi de strateji tarafında "yeni giriş yok" demektir (dosya yok/bayat/limit dolu → giriş yok; mevcut dosya TTL'i dolarak bayatlar, eski `allowed` kararı **tazelenmez**). Defterde bu durum mevcut `veto_status ∈ {missing, stale}` ile ifade edilir; yeni değer eklenmez. Açık pozisyonların yönetimi (SL/TP, çıkışlar) etkilenmez.
- **Ders servisi:** `Denial` → o günkü ders çalışması **atlanır**, `lesson_skipped_budget` olarak loglanır ve (varsa) Telegram günlük raporuna tek satır girer; ertesi güne taşınmaz, yeniden denenmez (aynı gün `store_unavailable` için bir sonraki zamanlanmış çalıştırmada tekrar sorulabilir). Hiçbir parametre değişikliği uygulanmaz.
- İki servis **farklı API anahtarı** kullanır: `os.environ[api_key_env("veto")]`, `os.environ[api_key_env("lesson")]`. Ortam değişkeni yoksa servis Claude'u çağırmaz (veto için fail-closed). Anahtarlar `config/*.json`, SQLite, olay yükü, log, istisna mesajı, `status()` ve panele **asla** girmez. Modül, kendi log/hata metinlerinden `sk-ant-` ile başlayan her dizgiyi `***` ile değiştirir (savunma).

## 10. Uyarı olayları

Olaylar `events` tablosunda saklanır; `ev_key UNIQUE` olduğundan bir olay anahtarı **bir kez** üretilir (süreçler yarışsa da).

| `kind` | `ev_key` | Koşul | Mesaj amacı |
|---|---|---|---|
| `daily_warn_70` | `daily_warn_70:<service>:<day>` | Servisin günlük kullanımı `≥ %70 × cap` (rezervasyon dahil), bir `authorize`/`record` sonrası | Uyarı |
| `daily_stopped_100` | `daily_stopped_100:<service>:<day>` | Kullanım `≥ cap`, **veya** ilk `daily_cap` reddi | "Durdu": veto → yeni giriş yok; ders → bugünkü ders atlandı |
| `monthly_warn_5usd` | `monthly_warn_5usd:<month>` | Aylık izlenen toplam (iki servis) `> monthly_warn_usd` (5 USD) | Ay başına **tek** uyarı |
| `monthly_stopped` | `monthly_stopped:<month>` | İlk `monthly_cap` reddi veya toplam `≥ monthly_cap_usd` | "Durdu" |
| `credit_low` | `credit_low:<day>` | Tahmini kalan kredi `prepaid_credit_usd − (credit_start_ts'den beri toplam harcama) < credit_low_usd` | Günde en fazla bir kez; **tahmindir**, Console e-postası/bakiye gerçektir |
| `provider_limit_hit` | `provider_limit_hit:<day>:<status>` | `report_error` `stop` döndü | Anthropic tarafı limit doldu |
| `budget_overrun` | `budget_overrun:<grant_id>` | `record`'da `cost > est` | Tahmin yetersizdi |
| `unknown_model` | `unknown_model:<model>` | Fiyat tablosunda olmayan model | Yapılandırma uyarısı |
| `store_error` | `store_error:<day>` | Depo hatası (günde bir kez, mümkünse) | Fail-closed devrede |

`pending_events()` `acked=0` olayları `id` sırasıyla verir; `BudgetEvent(id, kind, service, day, ts, message, payload)` — `message` Türkçe, hazır Telegram metni (ör. `veto günlük bütçesi %70'e ulaştı: 0.176 / 0.25 $`). Teslimat en az bir kez (at-least-once): gönderici başarılı gönderimden sonra `ack_events` çağırır; çökerse olay yeniden gelir. Telegram'ı çağıran modül bu işin dışındadır; bu modül yalnızca olay üretir. `ack_events` bilinmeyen id'yi yok sayar.

## 11. `status()` (panel / Telegram günlük raporu)

`BudgetStatus` (frozen dataclass, `to_dict()` ile JSON'a uygun):

| Alan | Anlam |
|---|---|
| `generated_at`, `day`, `month` | UTC |
| `store_ok`, `config_ok` | Depo/yapılandırma sağlıklı mı |
| `services["veto"|"lesson"]` | `ServiceStatus`: `cap_usd`, `settled_usd`, `unsettled_usd` (open+expired), `used_usd`, `pct` (0–100+, 1 ondalık), `remaining_usd` (≥0), `calls_today`, `state ∈ {ok, warn, stopped, blocked, unavailable}` |
| `month_used_usd`, `monthly_cap_usd`, `monthly_warn_usd`, `month_state ∈ {ok, warn, stopped}` | Aylık izlenen (iki servis) |
| `provider_blocked_until` | `None` veya zaman |
| `credit_estimate_usd` | `prepaid_credit_usd − toplam harcama` (tahmin) |
| `prices_verified` | `prices_verified_on is not None` |
| `pending_event_count` | Teslim edilmemiş olay sayısı |

`state`: `unavailable` (depo/yapılandırma hatası) > `blocked` (sağlayıcı engeli) > `stopped` (`used ≥ cap`) > `warn` (`≥ %70`) > `ok`. `status()` hata durumunda istisna fırlatmaz: `store_ok=False`, her servis `unavailable`. `status()` salt okunurdur (rezervasyon/olay üretmez); süresi dolmuş `open` satırları hesaplamada `unsettled` sayar (durumu değiştirmeden).

## 12. Dosya sahipliği ve dondurma süreci

- Bu işin dokunabileceği dosyalar **yalnızca**: `src/trader_core/budget.py`, `tests/test_budget.py` (ve ona ait yardımcı `tests/` dosyaları), `config/budget.json`. `TraderV1` ve diğer modüller (`risk.py`, `ledger.py`, `regime.py`, `signals.py`, `config_loader.py`, strateji, veto/ders servisleri, docker-compose) **düzenlenmez**; `config_loader.py` bu dosyayı okumaz (modül kendi `load_config`'ini kullanır).
- Veto ve ders servisleri başka işlerdir; bu modülü yalnızca Bölüm 4 arayüzü üzerinden çağırır. Arayüz değişikliği, bu belgenin sürümünün artırılması ve iki servis sahibinin onayı olmadan yapılamaz.
- Operatör kontrol listesi (kod değil, tek seferlik): ayrı workspace + iki anahtar; workspace aylık limiti 10 USD; 10 USD kredi, **auto-reload kapalı**; `prices_verified_on` doldurma; e-posta bildirimi (Console).

## 13. Hesapla doğrulanabilir örnekler

Fiyatlar Bölüm 3 tablosundan (doğrulanmalı); `price_safety_factor = 1.0`.

**13.1 Haiku 5.5 veto çağrısı (standart).** `input_tokens=4800`, `cache_read=1500`, `output=800`:
`4800×0,10 + 1500×0,01 + 800×0,50 = 480 + 15 + 400 = 895 µUSD = 0,000895 $`.

**13.2 Aynı çağrı, saatin ilk çağrısı (1 saat önbellek yazımı).** `input=4800`, `cache_write_1h=1500`, `output=800`: `480 + 300 + 400 = 1180 µUSD`. 5 dk yazım olsaydı `1500×0,125 = 187,5` → toplam `1067,5` → `ceil` = `1068`.

**13.3 Güvenlik çarpanı.** 13.1 `price_safety_factor=1.1` ile: `895×1,1 = 984,5` → `985 µUSD`.

**13.4 Sonnet 5.5 ders işi, Batch.** `input=6000`, `output=1500`: standart `6000×2 + 1500×10 = 12000 + 15000 = 27000`; `batch=True` → `27000×0,5 = 13500 µUSD = 0,0135 $`. Günde 1 çalıştırma × 30 = 0,405 $/ay (nottaki 0,41 ile uyumlu).

**13.5 Üst sınır tahmini.** `estimate_cost("claude-haiku-5-5", input_tokens=4800, max_output_tokens=1000, cache_read_tokens=1500)` = `480 + 15 + 500 = 995 µUSD` → `0.000995`. Gerçek 13.1'de 895 → `overrun=0`, kayıt 895'e düşer (100 µUSD serbest kalır).

**13.6 %70 eşiği ve %100.** Veto cap `250 000 µUSD`; %70 eşiği `175 000`. Kullanım `174 000`; `authorize(veto, 0.002)` (`est=2 000`): `176 000 ≤ 250 000` → `Grant`; `176 000 ≥ 175 000` → `daily_warn_70:veto:<gün>` olayı (mesaj: "%70.4"). Aynı gün sonraki çağrılarda tekrar üretilmez. Kullanım `249 000`, `est=1 500`: `250 500 > 250 000` → `Denial("daily_cap")` ve `daily_stopped_100` (kullanım henüz %99,6 olsa da çağrı karşılanamadığı için "durdu").

**13.7 Servis yalıtımı.** Aynı anda `lesson` kullanımı `100 000` (cap `100 000`), `veto` kullanımı `0`: `authorize(lesson, 0.0135)` → `Denial("daily_cap")`; `authorize(veto, 0.001)` → `Grant`. Ders hiçbir koşulda veto bütçesinden düşmez, tersi de.

**13.8 Aylık.** İki servisin ay toplamı `4 999 000` iken `0.002` USD'lik çağrı `5 001 000` yapar → `monthly_warn_5usd:<ay>` bir kez; ay içinde sonra tekrar yok. Toplam `9 999 000`, `est=2 000` → `10 001 000 > 10 000 000` → `Denial("monthly_cap")` (iki servis için de); ayın 1'inde (UTC) ay anahtarı değişince sıfırdan başlar.

**13.9 Çökme.** `10:00:00Z` `authorize(veto, 0.003)` → `open`, `est=3 000`; süreç çöker. `10:05` yeniden başlatma: `status().services.veto.unsettled_usd = 0.003` (sayılı). `10:11` (TTL 600 sn) sonraki `authorize` satırı `expired` yapar, `3 000` sayılı kalır. `10:20` geç `record` gerçek `895` ile gelirse (örn. süreç aslında bitirmişti) satır `settled`, `charged=895`. Çökmüş çağrıda `record` hiç gelmezse `3 000` günün sonuna kadar (ve ayda) sayılı kalır: fazla sayım, eksik değil.

**13.10 Eşzamanlılık.** Veto kullanımı `240 000`; iki süreç aynı anda `est=8 000` ister. `BEGIN IMMEDIATE` sıralar: birincisi `248 000 ≤ 250 000` → `Grant`; ikincisi `256 000 > 250 000` → `Denial("daily_cap")`. Aşım olmaz.

**13.11 Gün sınırı ve saat geri gitmesi.** `23:59:59.900Z` (gün D) `authorize`; `record` `00:00:03Z` (gün D+1) → maliyet **D**'ye yazılır; D+1 sayacı `0` başlar. Sonra sistem saati `23:50Z` (D) gösterirse `last_ts=00:00:03Z (D+1)` olduğundan etkin zaman geri gitmez, gün D+1 kalır.

**13.12 Hata sınıfları.** (a) `400, invalid_request_error, "You have reached your specified API usage limits..."` → `stop`, `blocked_until` = ertesi gün `00:00:00Z`; ardından her iki servis `provider_blocked`. (b) `429, error_code="enforced_spend_limit_reached"` 15 Aralık'ta → `stop`, `blocked_until = 2027-01-01T00:00:00Z` (ay Aralık). (c) `429 rate_limit_error`, `attempt=1` → `retry`, `sleep_s ≈ 2 s ± %20` (`attempt=2` → ~4, `attempt=3` → ~8); `attempt=4` → `fail`. (d) `529`, `retry_after_s=40` → `sleep_s = min(40, max_sleep 20) = 20`. (e) `400` şema hatası → `fail`, engel yok.

**13.13 Depo hatası.** `budget.sqlite` bozuk: `authorize` → `Denial("store_unavailable")`; veto dosya yazmaz → strateji giriş açmaz. Dosya silinmiş ama `.initialized` var: `Denial("store_missing")` (sayaç sıfırlanmaz).

## 14. Test planı (yalnızca başlıklar; kod bu işin dışında)

`tests/test_budget.py`: (1) maliyet örnekleri 13.1–13.5, yukarı yuvarlama, batch, güvenlik çarpanı, geçersiz usage/model/büyük istek; (2) `HARD_LIMITS` ve yapılandırma doğrulaması, gevşek değer `BudgetConfigError`; (3) eşikler 13.6–13.8 (tam sayı kenarları: tam `%70`, tam `%100`, `est` ile tam cap); (4) servis yalıtımı; (5) olayların tekilliği ve `ack` yeniden teslim; (6) çökme: `open` satırı yeniden açılışta sayılı, `expired` sayılı, geç `record`, çift `record` idempotent, `release` yalnızca yanıtlı hata; (7) iki süreçle eşzamanlılık (`multiprocessing`, tek kota için yarış, toplam hiçbir zaman cap'i `est` ile aşmaz); (8) gün sınırı, ay sınırı, saat geri gitmesi; (9) depo bozuk/kilitli/eksik/işaret dosyası, şema sürümü, her durumda `Denial` ve istisna yok; (10) hata sınıflandırma tablosu (13.12) ve geri çekilme süreleri; (11) anahtar sızıntısı: sahte `sk-ant-...` dizgisi log, olay, `status().to_dict()`, hata metni ve veritabanı dosyası baytlarında bulunmaz; (12) `status()` durum önceliği ve hatada istisnasızlık; (13) `config/budget.json`'ın şu anki değerlerle `load_config` geçmesi ve `HARD_LIMITS` ile uyumu.

## 15. Çözülen belirsizlikler (karar kaydı)

1. "%100 durdu" ne zaman: kullanım `≥ cap` **veya** ilk reddedilen çağrı (karşılanamayan tahmin).
2. 5 USD aylık uyarı: izlenen **iki servis toplamı**, **ay başına bir kez**.
3. Aylık 10 USD uygulama tarafında da sert sınırdır (tek ortak sayaç); günlük sınırlar servis başına bağımsız.
4. 400/429-limit engeli **küresel** (iki anahtar aynı workspace'te); 400 için günlük yoklama, 429-tavan için ayın 1'i.
5. Yanıtsız hatada rezervasyon **bırakılmaz** (eksik sayım yerine fazla sayım).
6. `est` üst sınır olmalı; gerçek maliyet tahminden büyükse yine de yazılır (sınır aşılabilir, sonraki çağrı kapanır).
7. Gün/ay UTC; rezervasyon günü `authorize` anındaki gündür.
8. SQLite rollback günlüğü (WAL yok) iki konteyner arası güvenli kilit için seçildi; kilit = SQLite dosya kilidi (`BEGIN IMMEDIATE`).
9. Depo kaybı sayacı sıfırlamaz (`store_missing`); operatör bilinçli yeniden başlatır.
10. Fiyatlar yalnızca yapılandırmada ve "doğrulanmalı"; doğrulanana kadar engellemez, ama panelde görünür.
