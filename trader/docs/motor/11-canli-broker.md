# 11 — Canlı broker, mutabakat (canlı), giriş duraklatma, testnet ve duman testi (Faz B şartnamesi v1, 17 Kasım 2026)

Kaynak kararlar: `motor-tasarimi.md` §1.3 (ham `requests`, ccxt/python-binance yok), §2.3 (Broker arayüzü), §2.6 (stop yönetimi ve mutabakat tablosu), §3.2–§3.4 (Faz B takvimi, testnet listesi, duman testi), §5 risk 1/8/11; `faz-plani.md` madde 25–28 (alt hesap anahtarı kağıdın 2. haftası, duman testi 28–29 Aralık, 1000 USD canlı); `risk-kademe-kurali.md` §5 ve §9 (−%20'de "girişi durdur, pozisyonu tut"; kendiliğinden açılmaz), §11 madde 3; `telegram-spec.md` karar 1/2/9 (`/durdur` bugün "desteklenmiyor"); `07-copied-1l3a.md` §4.5 (Faz B kopya kuralları, senaryo başlıkları r1–r12); `04-order-position.md` §1 (Faz B ön koşulu: canlıda `max_attempts=1`); `09-mentor-inceleme.md` B7 ve C notları. Bağımlılıklar: `02`, `03` (`Broker` protokolü), `04` (`OrderManager`, `StateStore`), `05` (`Engine`, `EntryGate`, `Reconciler`, `Killswitch`), `07` (`PublicRestClient`, `exchange/rules.py`). Dış çerçeve yok: yalnız `requests`, `hmac`, `hashlib`, `decimal`, standart kütüphane. Bu belge kod, test ve commit içermez.

**Okuyana not — doğrulanmamış borsa varsayımları.** Bu ortam Binance'e erişemiyor (HTTP 451). Aşağıda **[V-n]** ile işaretli her cümle belgeye ve 1l3a koduna dayanan varsayımdır; testnet listesindeki (§11) karşılık gelen madde gerçek yanıtla doğrulanmadan canlıya çıkılmaz. Doğrulama varsayımı çürütürse ilgili bölüm mentor onayıyla revize edilir; gerçekleyen ajan kendi başına "çalışan" bir yol uydurmaz.

- **[V-1]** Koşullu emirler (`STOP_MARKET`, `TAKE_PROFIT_MARKET`) Aralık 2025'ten beri `/fapi/v1/order` yerine Algo servisindedir: `POST/GET/DELETE /fapi/v1/algoOrder`, `GET /fapi/v1/openAlgoOrders`, `algoType=CONDITIONAL`, `clientAlgoId`, `triggerPrice`; eski uç `-4120` döner.
- **[V-2]** Testnet tabanı `https://testnet.binancefuture.com`; anahtar bu tabanda çalışmazsa `https://demo-fapi.binance.com` denenir.
- **[V-3]** Aynı pozisyon için iki miktar bazlı `reduceOnly` stop aynı anda durabilir (`closePosition=true` ile duramaz).
- **[V-4]** `reduceOnly` emirler `MIN_NOTIONAL` filtresinden muaftır.
- **[V-5]** Yinelenen `newClientOrderId` yalnız açık emirler arasında reddedilir (`-4116`); dolmuş piyasa emrinin kimliği yeniden kabul edilebilir.
- **[V-6]** Anahtar izinleri `GET https://api.binance.com/sapi/v1/account/apiRestrictions` ile okunur (alt hesap anahtarıyla da); testnette karşılığı yoktur.
- **[V-7]** Tetiklenen algo emri sorguda `actualOrderId` taşır; `userTrades.orderId` bununla eşleşir. Likidasyon emrinin `clientOrderId`'si `autoclose-` ile, ADL `adl_autoclose` ile başlar.

## 1. Kararlar (özet)

| Konu | Karar |
|---|---|
| Sınıf / dosya | `LiveBroker` (`brokers/binance_futures.py`), `Broker` protokolünü (03 §3) birebir uygular; `SimBroker` yöntemleri (`advance/snapshot/restore`) **yoktur**; `is_simulated = False` |
| Kipler | `mode ∈ {backtest, paper, testnet, live}`. `testnet` ve `live` aynı kod yoludur; tek fark taban adresi, izin denetimi ve `LIVE_CONFIRM` |
| Giriş emri | **MARKET** (`newOrderRespType=RESULT`). Limit giriş yok (strateji "sonraki açılışta piyasa" ile sınandı; limit, dolmama ve kısmi dolum durum makinesi ister) |
| Koruyucu stop | Borsada `STOP_MARKET`, **miktar bazlı `reduceOnly=true`**, `workingType=MARK_PRICE`, `priceProtect=false`, GTC. `closePosition=true` kullanılmaz (iki stop aynı anda duramaz) |
| Stop zamanı | Giriş dolumu öğrenildiği **aynı çağrı zincirinde** kurulur. Değişmez: borsada stopsuz pozisyon en fazla `stop_deadline_s = 10` sn (§10) |
| İz süren stop | **Önce yeni, sonra eski iptal**; yalnız sıkılaşır; yeni kurulamazsa eski yerinde kalır (asla çıplak değil) |
| Hedef (TP) | Canlı v1'de borsada TP **kurulmaz** (`target_mode="bar_close"`, 00-index §5 madde 1). `place_target` arayüz eşliği ve duman testi için gerçeklenir |
| Kısmi dolum | Giriş: pozisyon = `executedQty`. Çıkış: çıkış kaydı **tek olaydır**, borsa pozisyonu sıfırlanınca girişten beri tüm azaltan işlemlerin VWAP'ıyla üretilir |
| Hesap kipi | İzole teminat, tek yönlü (one-way), çoklu varlık kipi kapalı; kaldıraç `EngineConfig.leverage` (risk kilidi aralığında) |
| Kimlik | `make_client_id` (04 §4) aynen; canlıda `max_attempts=1` (kör yeniden gönderim yok) — T-08 geçene kadar |
| Olay kaynağı | **REST yoklama.** Kullanıcı veri akışı (listenKey/WS) canlı v1'de **yok** (§7; ertelendi) |
| Mutabakat | Açılışta (veri kapısından **önce** `protect_first`), pozisyon/çözülmemiş emir varken 15 sn, düzken 60 sn; `reconcile_live.py` |
| Bilinmeyen pozisyon | Alarm + kalıcı duraklatma; **asla** otomatik kapatılmaz. Tek istisna: kullanıcı KILL kurmuşsa kapatılır (§8 L2) |
| Giriş duraklatma | Yeni `EntryPause` (`pause.py`): kalıcı dosya, nedenli tutuşlar, **motor asla kaldırmaz**; `/durdur` ve `/devam` iki adımlı; `drawdown_review` aynı mekanizmayı kullanır (§9) |
| Yeniden deneme | Emir **POST**'u ağ hatası/zaman aşımı/5xx'te **asla** otomatik tekrarlanmaz (belirsiz → kimlikle sorgu). Okuma/iptal/ayar üstel geri çekilmeyle tekrarlanır |
| Anahtar | Yalnız ortam dosyasından (`/etc/trader-live.env` canlı, `/etc/trader-testnet.env` testnet; `root:root 0600`); hiçbir günlükte, hata iletisinde, `status.json`'da, Telegram'da görünmez |
| İzin denetimi | Canlı açılışta para çekme izni açıksa ya da IP kısıtı yoksa motor **başlamaz** (çıkış kodu 8) |
| Paper eşliği | Kağıt ve backtest davranışı **bit-bit değişmez** (kabul ölçütü §13 WP-B4) |

## 2. DOSYA SAHİPLİĞİ

Yeni dosyalar (bu şartname sahibidir):

- `src/trader_engine/exchange/binance_rest.py` (WP-B1), `src/trader_engine/brokers/binance_futures.py` (WP-B3), `src/trader_engine/reconcile_live.py` (WP-B5), `src/trader_engine/pause.py` (WP-B6)
- `tests/engine/fake_exchange.py` (yalnız test kodu; 07 §4.5 `kuru.py` uyarlaması), `tests/engine/fixtures/binance/testnet/*.json` (kayıtlı gerçek yanıtlar; anahtar/imza/`listenKey` alanları silinmiş)
- `scripts/smoke_testnet.py`, `scripts/smoke_live.py`
- `deploy/trader-engine-testnet.service`, `deploy/trader-engine-live.service`, `deploy/trader-live.env.example`, `deploy/trader-engine-env-retry@.{service,timer}` (DD-9; `live.conf.example` ve `trader-binance.env.example` kaldırıldı)
- Testler: `tests/engine/test_engine_binance_rest_spec.py`, `test_engine_live_broker_spec.py`, `test_engine_live_lifecycle_spec.py`, `test_engine_reconcile_live_spec.py`, `test_engine_pause_spec.py`, `test_engine_live_config_spec.py` (bağımsız test ajanı); `test_engine_live_impl_smoke.py` (gerçekleme ajanı)

Değiştirilen dosyalar (sahibi başka şartname; değişiklik yalnız burada sayılan kadardır, ilgili belgeye "11 ile güncellendi" notu düşülür):

| Dosya | Değişiklik | WP |
|---|---|---|
| `config.py` | `mode` kümesi, `live` bloğu, `leverage`, `pause_file` (§3) | B2 |
| `cli.py` | `run` canlı kurulum, `pause` alt komutu, `smoke` yönlendirmesi, çıkış kodu 8 | B2, B6 |
| `engine.py` | canlı yol: dış işlem (tx) yok, `protect_first`, `live_tick`, olayların adımsız işlenmesi, yalnız son karar barı (§6) | B4 |
| `order_manager.py` | stop süre sınırı, canlıda giriş çözüm penceresi, `closing` pozisyonda stop (§6) | B4 |
| `gates.py`, `status.py` | duraklatma kapısı, `leverage`, `status.json` alanları (§9.4) | B6 |
| `trader_core/telegram.py`, `scripts/telegram_run.py` | `/durdur`, `/devam` genişlemesi, `/durum` satırı (§9.5); `telegram-spec.md` karar 1 revizyonu | B6 |
| `tests/engine/test_engine_module_inventory.py` | `PHASE = "B"`; izinli modüllere yukarıdaki dört dosya eklenir; `FORBIDDEN_TEXT` Faz B'de uygulanmaz ama `listenKey`/`websockets` metni yine **yasak** kalır (ertelendi) | B2 |
| `deploy/install.sh` | testnet birimi, ortam dosyaları (`0600`), canlı drop-in | B8 |

Dokunulmaz: `trader_core/risk.py`, `trader_core/ledger.py`, `brokers/paper.py`, `brokers/base.py` (protokol değişmez), `marketdata/**`, `backtest.py`, `strategies/**`.

## 3. Yapılandırma, kipler, anahtarlar

### 3.1 `EngineConfig` ekleri

```python
mode: Literal["paper", "backtest", "testnet", "live"]
leverage: int = LOCKED_CFG.min_leverage          # [LOCKED_CFG.min_leverage, LOCKED_CFG.max_leverage] dışı => ConfigError
pause_file: str = "shared/PAUSE"                 # gerçek yol: f"{pause_file}.{bot}"
live: LiveSettings | None = None                 # mode ∈ {testnet, live} ise ZORUNLU; diğer kiplerde verilirse ConfigError

@dataclass(frozen=True)
class LiveSettings:
    account_tag: str                  # ^[a-z0-9-]{3,32}$ ; canlıda LIVE_CONFIRM ile eşleşmeli
    expected_wallet_max: float        # > 0; açılışta cüzdan bundan büyükse başlamaz (yanlış hesap koruması)
    conditional_mode: Literal["algo", "classic"] = "algo"     # T-01 sonucu; elle değiştirilmez
    recv_window_ms: int = 5000        # [1000, 10000]
    poll_open_s: float = 5.0          # [1, 15]
    poll_flat_s: float = 30.0         # [5, 120]
    stop_deadline_s: float = 10.0     # [5, 15]; gevşetilemez (üst sınır 15)
    entry_resolve_window_s: float = 60.0
    max_attempts: int = 1             # yalnız 1 ya da 2; 2 için T-08 kanıtı + mentor onayı
```

Kurallar: `mode="live"` yalnız `bot="learner"` ile geçerlidir (ikiz kağıtta kalır); `veto_mode="required"` zorunlu; `cost.trigger_source="mark"` zorunlu. `entry_leverage()` (gates) artık `cfg.leverage` döner; varsayılan değer bugünküyle aynıdır (3), kağıt sonuçları değişmez. Taban adresleri yapılandırmada **yoktur**: `binance_rest.py` içinde sabittir (`live → https://fapi.binance.com`, `testnet →` [V-2]); böylece canlı kip yanlış adrese, testnet kipi gerçek adrese yönlendirilemez. `ConfigError("faz_b")` reddi kalkar; hata iletilerinde `faz_b` sarmalayıcısı da **yoktur**.

**Çift onay (yalnız `mode="live"`):** ortam değişkeni `LIVE_CONFIRM` `live.account_tag` ile **birebir** eşit değilse `ConfigError("live_confirm")`, çıkış kodu 2. Değer günlüğe yazılmaz.

**DD-8 yol kuralı (§3.1 eki):** `mode ∈ {testnet, live}` iken `var_dir`in son bileşeni `var` olamaz; `kill_file` son iki bileşeni `shared/KILL`, `pause_file` son iki bileşeni `shared/PAUSE` olamaz (kâğıt botlarının dosyaları) — `ConfigError`. `kill_file`, `pause_file` (her kipte) ve testnet/live'da `var_dir` yapılandırma dizinine göre mutlaklaştırılır (`config.absolutize_paths`, tek yükleyici `config.load_cli_config`; duman betikleri de bunu kullanır); `build_engine` testnet/live'da göreli yolu `ConfigError("relative_path:<alan>")` ile reddeder. **Mod/hesap damgası:** state kv `account_stamp` ve defter `meta.account_stamp` = `f"{mode}:{live.account_tag}"` (`stamp.py`); yabancı/eksik damga ya da silinmiş state = çıkış 8 (`state_stamp_mismatch`, `ledger_stamp_mismatch`, `state_stamp_missing`, `ledger_stamp_missing`, `state_missing`). Karar tablosu ve işletme çaresi: `docs/dd8-canli-baslangic-spec.md` §2.2, `docs/sunucu-kurulum.md`.

**Kanonik sıra (kurulum):** önce onay (`check_live_confirm`, yalnız live), **sonra** anahtarlar (`load_keys`). `build_engine` ve `_build_live_broker` aynı sırayı izler; eksik anahtar düz `ConfigError("keys_missing: <DEĞİŞKEN>")` olarak yükselir (sarmalanmaz).

### 3.2 Anahtarlar

- Ortam dosyası: `/etc/trader-testnet.env` ve `/etc/trader-live.env` (DD-9), `root:root 0600`, systemd `EnvironmentFile=` ile; değişkenler `BINANCE_API_KEY`, `BINANCE_API_SECRET`. Depoda, `config/*.json`'da, komut satırında, `status.json`'da, defterde, Telegram'da **bulunmaz**. Birim dosyasında iki ortam dosyası aynı anda yüklenmez.
- `load_keys(env: Mapping[str, str]) -> tuple[str, str]`: eksik, boş, boşluk içeren ya da 32 karakterden kısa değer → `ConfigError("keys_missing")` (iletide değer yok, yalnız değişken adı).
- Günlük hijyeni (WP-B1 kabul): istemcinin ürettiği hiçbir ileti sorgu dizgesi, imza, anahtar ya da `X-MBX-APIKEY` başlığı içermez; hata iletisi = `yöntem yol http=<kod> code=<borsa kodu> msg=<en fazla 200 karakter>`. `SignedRestClient.__repr__` anahtarı göstermez. Test: gizli değer `"SIZMA-TESTI-…"` ile her hata yolu çalıştırılır, yakalanan günlük ve istisna metinlerinde değer **yok**.
- Varsayım (kullanıcı sağlar, §14): anahtarda para çekme ve iç transfer kapalı, yalnız sunucu IP'si izinli, yalnız vadeli işlem + okuma açık; alt hesapta USDT dışında varlık yok (komisyon USDT'den kesilir).

### 3.3 Çıkış kodları

Mevcutlar (0, 2, 3, 4, 5, 7) korunur. Yeni: **8 = borsa yetki/izin/bölge reddi** (anahtar geçersiz, IP izinli değil, izin denetimi başarısız, 451). **DD-7:** `5` ayrıca `exchange_ban_persisted` taşır (ban dosyasında etkin kayıt var; bkz. §3.4-1). DD-8 ile 8 ayrıca şu kalıcı retleri taşır: `state_stamp_mismatch`, `ledger_stamp_mismatch`, `state_stamp_missing`, `ledger_stamp_missing`, `state_missing`, `wallet_unreadable`, `key_permission:<alan>`, `key_permission_unverifiable`, `region_blocked`, `auth_failed`. Kâğıt motor birimi `RestartPreventExitStatus=7 8`; testnet ve canlı birimler `2 7 8` (DD-9 §2.2; yeniden başlatma döngüsü yerine `failed` + Telegram CRIT) ve diğer her çıkışta (3, 4, 5, sinyal, OOM) 5 sn'den 120 sn'ye büyüyen aralıkla **süresiz** yeniden denenir (`StartLimitIntervalSec=0`); defter/damga işi `run --ensure-ledger` ile motor sürecinde yapılır (ExecStartPre'de çıkış 8 döngüye girerdi).

### 3.4 Açılış denetimi — `LiveBroker.startup_check()` (sırayla; ilk başarısızlıkta `EngineExit(8, <kod>)`)

1. **DD-7 (ilk satır, saat eşitlemesinden önce, istek 0):** `rest.health()["ban_until_ms"]` (ban dosyasından benimsenen pencere dahil) `> now` ise `wait = min(kalan_sn + 2, 300)`, `CRITICAL` günlük (`exchange_ban_persisted`, host, kalan sn), `clock.sleep(wait)`, `EngineExit(5, "exchange_ban_persisted")`. Kayıttaki `http` ne olursa olsun (403 ve bozuk kayıt dahil) kod 5'tir; kalıcı ret (8) kararını bayat dosya değil, pencere bitince atılan gerçek istek verir. DD-8 sırası değişmez: damga denetimi bu adımdan önce gelir. Ardından `GET /fapi/v1/time` → saat farkı (§4.2). 451/403 → `region_blocked`; ağ yok → 3 deneme sonra `exchange_unreachable` (çıkış kodu 5, yeniden başlatılır). **418/429** (ban penceresi): `Retry-After` kadar (en çok 300 sn) beklenir, `CRITICAL` yazılır, sonra çıkış kodu 5 (supervisor ban bitmeden yeniden başlatıp pencereyi uzatmasın). Açılış sırasındaki herhangi bir `ExchangeReject(-1021)` (yeniden eşitleme başarısız) kurulum hatası değil ağ sorunudur: çıkış kodu **5** (8 değil).
2. **Yalnız `live`:** `apiRestrictions` [V-6]. Zorunlu: `enableReading=true`, `enableFutures=true`, `enableWithdrawals=false`, `enableInternalTransfer=false`, `permitsUniversalTransfer=false`, `ipRestrict=true` (tek kaynak: `binance_futures._REQUIRED_PERMS`; `smoke_live.py` aynı demeti içe aktarır). Sonuç **yalnız** yanıta bağlıdır (DD-8 O6; beyan yolu kaldırıldı): altı alan `bool` ve beklenen değerde → geçer; herhangi bir alan beklenenin tersi → `key_permission:<alan>` (`_REQUIRED_PERMS` sırasındaki ilk; eksik alan olsa da ihlal önceliklidir); yanıt sözlük değil / alan eksik / `bool` değil / kalıcı `ExchangeReject` / başka istisna → `key_permission_unverifiable` (8); `ExchangeAuth` → `auth_failed` (8); `ExchangeBan` 451/403 → `region_blocked` (8), diğer ban → en çok 300 sn bekle + çıkış 5; `ExchangeUncertain` ve `ExchangeReject(-1021)` → `exchange_unreachable` (5). `LIVE_PERMISSION_ATTESTED` ortamda tanımlıysa sonucu etkilemez, yalnız `WARNING` yazılır ("artık geçerli değil"). Not: `/fapi/v*/account` içindeki `canWithdraw` **hesap** bayrağıdır, anahtar izni değildir; kanıt sayılmaz. Testnette bu adım atlanır ve `INFO` yazılır.
3. Hesap (`GET /fapi/v2/account`): `canTrade=true` değilse `account_cannot_trade`; `totalWalletBalance > live.expected_wallet_max` (katı `>`) ise **istisna atılmaz**: `LiveBroker.startup_findings`e `"wallet_above_expected"` eklenir, açılış sürer ve `Engine.start()` `protect_first`'ten ÖNCE `pause.add("wallet_above_expected", by="engine:wallet_cap")` ekler (§9.2; DD-8 O4). Denetim `testnet`te de çalışır. **Fail-closed:** `totalWalletBalance` yok/sayı değil/sonlu değilse `wallet_unreadable` (çıkış 8, her iki kipte); okunamayan bakiye tavan denetimini atlatamaz.
4. Çoklu varlık kipi (`GET /fapi/v1/multiAssetsMargin`) açıksa: pozisyon yoksa kapatılır, varsa `multi_asset_mode`.
5. Pozisyon kipi (`GET /fapi/v1/positionSide/dual`): hedge açıksa ve hiç pozisyon/emir yoksa one-way yapılır; pozisyon varsa `hedge_mode_with_positions`.
6. `cfg.pairs` içindeki her sembol: `marginType=ISOLATED` (`-4046` = zaten öyle = başarı) ve `leverage=cfg.leverage`; ardından `positionRisk` ile doğrulama (`marginType=="isolated"`, `leverage==cfg.leverage`). **Çift başına ret açılışı durdurmaz:** `set_isolated`/`set_leverage` `ExchangeReject` (`-4048` açık pozisyonla marjin tipi, `-4047` açık emirle marjin tipi, `-4161` açık pozisyonla kaldıraç düşürme, …) verirse hata çift bazında yakalanır, doğrulama yine yapılır, çift **hazırlanmamış** kalır (`prepare_failed` sayacı; pozisyon varsa `CRITICAL`, yoksa `ERROR`) ve sonraki çiftlere geçilir. Auth/ban/belirsizlik açılışı yine bitirir. Uyuşmazlık (açık pozisyonlu ya da **düz**) düzeltilemezse o çift için giriş kapanır (`not_prepared`); motor başlar (çıkışlar çalışmalı). Düz çiftte ret/uyuşmazlık beklenmez; aynı yoldan geçer (`ERROR`).
7. Kurallar: `exchangeInfo` **bu ortamdan** çekilir (§5.2; istemci içi yeniden denemelerle birlikte en çok 2 tur, aralarında bekleme). Okunamazsa `exchange_unreachable` (çıkış kodu **5**): kuralsız başlanmaz. Bir çiftin kuralı yoksa o çifte giriş yok (`rules_missing`); o çiftte **tutulan pozisyon** varsa `CRITICAL` (stop kurulamaz, çıkış §5.2 gereği yine gönderilir).
8. Komisyon oranı: `GET /fapi/v1/commissionRate` (çift başına, `takerCommissionRate`); alınamazsa `cfg.cost.taker_fee` kullanılır ve `fee_rate_fallback` sayacı artar.

## 4. `exchange/binance_rest.py` — imzalı istemci

07 §4.5 kuralıyla 1l3a `binance_futures.py`'den **(a) kopya + kesinti**: başlık üç satırı zorunlu; kimlikler İngilizce; `time.sleep`/`time.time` varsayılanları kaldırılır (zorunlu enjeksiyon). `PublicRestClient` ile ortak taban sınıfa birleştirme **yapılmaz** (ertelendi).

```python
class ExchangeReject(ExchangeError):      # borsa isteği işledi ve reddetti (kesin)
    code: int | None; http: int; msg: str
class ExchangeUncertain(ExchangeError):   # isteğin işlenip işlenmediği bilinmiyor
    http: int | None
class ExchangeAuth(ExchangeError): ...    # 401, -2014, -2015, -1022
# ExchangeBan (rest_public'ten içe aktarılır): 418, 429 penceresi, 451, 403

class SignedRestClient:
    def __init__(self, *, env: Literal["testnet", "live"], api_key: str, api_secret: str, session=None,
                 now_ms: Callable[[], int], sleep: Callable[[float], None], recv_window_ms: int = 5000,
                 read_timeout_s: float = 10.0, order_timeout_s: tuple[float, float] = (2.0, 3.0),   # (bağlan, oku)
                 max_attempts: int = 4, weight_soft: int = 1200, weight_hard: int = 1800,
                 order_cap_10s: int = 20, order_cap_1m: int = 100, conditional_mode: str = "algo")
    def sync_time(self) -> int                      # ms; offset = serverTime − (t0 + t1)/2
    def request(self, method: str, path: str, params: dict | None, *, kind: Literal["read", "cancel", "setup", "order"],
                signed: bool = True, protective: bool = False) -> Any
    def health(self) -> dict                        # used_weight, order_count_10s/1m, clock_offset_ms, ban_until_ms, last_ok_ms
    # uç sarmalayıcıları (hepsi request üzerinden)
    def exchange_info(self) -> dict                                      # imzasız
    def mark_price(self, symbol: str) -> Decimal                         # /fapi/v1/premiumIndex, imzasız
    def account(self) -> dict                                            # /fapi/v2/account
    def position_risk(self, symbol: str | None = None) -> list[dict]     # /fapi/v2/positionRisk
    def open_orders(self, symbol: str | None = None) -> list[dict]       # /fapi/v1/openOrders
    def open_conditionals(self, symbol: str | None = None) -> list[dict] # algo: /fapi/v1/openAlgoOrders ; classic: openOrders süzgeci
    def new_market(self, symbol, side, qty: str, client_id: str, reduce_only: bool) -> dict
    def new_conditional(self, symbol, order_type, side, qty: str, trigger: str, client_id: str, working_type: str) -> dict
    def query_order(self, symbol, client_id) -> dict | None              # -2013 => None
    def query_conditional(self, symbol, client_id) -> dict | None
    def cancel_order(self, symbol, client_id) -> None                    # -2011/-2013 => no-op
    def cancel_conditional(self, symbol, client_id) -> None
    def user_trades(self, symbol, start_ms: int, end_ms: int | None = None) -> list[dict]   # 7 günlük pencereler, sayfalı
    def income(self, symbol, income_type: str, start_ms: int, end_ms: int) -> list[dict]
    def commission_rate(self, symbol) -> dict
    def api_restrictions(self) -> dict                                   # yalnız live; taban https://api.binance.com
    def position_mode(self) -> bool; def set_one_way(self) -> None
    def multi_assets(self) -> bool; def set_single_asset(self) -> None
    def set_isolated(self, symbol) -> None; def set_leverage(self, symbol, leverage: int) -> None
```

### 4.1 İmza

Parametreler eklenme sırasıyla `urlencode` edilir, sona `recvWindow` ve `timestamp = now_ms() + offset` eklenir; `signature = HMAC-SHA256(secret, sorgu).hexdigest()` en sona; başlık `X-MBX-APIKEY`. Sayılar **dizge** olarak gider: `Decimal(repr(x))` adım/tick'e nicemlenir, üstel gösterim yok (`format(d, "f")`), sondaki sıfırlar atılır. Parametreler POST'ta da sorgu dizgesinde gider (gövde boş).

### 4.2 Saat

`sync_time()` açılışta, 30 dakikada bir ve her `-1021`'de çağrılır. `|offset| > 1000 ms` → `WARNING` + `clock_offset` sayacı; `|offset| > 5000 ms` → motor `entries_blocked_reason="clock_skew"` kurar (mevcut neden; ölçüm 5000 altına inince mevcut kural temizler) ve `CRITICAL` (sunucu NTP'si bozuk). Koruyucu emirler bu durumda da gönderilir (offset düzeltmesi imzayı geçerli kılar).

### 4.3 Yeniden deneme ve hata sınıfları

| Durum | `read` / `cancel` / `setup` | `order` (emir POST'u) |
|---|---|---|
| Ağ hatası, zaman aşımı, HTTP 5xx, `-1001`, `-1007` | 1, 2, 4 sn geri çekilmeyle `max_attempts` kez; sonra `ExchangeUncertain` | **Tekrar yok.** Hemen `ExchangeUncertain` (→ `BrokerUncertain` → 04 belirsizlik yolu) |
| `-1021` (zaman damgası pencere dışı; yalnız HTTP < 500) | tek `sync_time()` denemesi (geri çekilme yok) + tekrar | aynı, emir zaman aşımıyla + **bir** tekrar (istek işlenmedi; güvenli). Eşitleme herhangi bir nedenle başarısızsa özgün istek için `ExchangeReject(code=-1021, http=400)` |
| 429 | `Retry-After` kadar **hiçbir** istek yok (koruyucular dahil). Satır içi uyku yalnız `Retry-After <= 5 sn` ise (bekle + tekrar); daha uzunsa hemen `ExchangeBan(429, retry_after_s)`, pencere saatle kapanır. `Retry-After` 429/418'de [1, 3600] sn'ye kısılır | `ExchangeReject(code=None, http=429)`; `reason="rate_limited"` (istek işlenmedi) |
| 418 | `ExchangeBan(retry_after)`; pencere bitene kadar hiçbir istek yok | aynı |
| 451, 403 | `ExchangeBan(http)`; 403: 300 sn, sonra ikiye katlanarak en fazla 1800 sn bekle | aynı |
| 401, `-2014`, `-2015`, `-1022` | `ExchangeAuth` (tekrar yok) | aynı |
| Diğer 4xx + borsa kodu | `ExchangeReject` (tekrar yok); `cancel`'da `-2011/-2013`, `setup`'ta `-4046/-4059` **başarı** | `ExchangeReject` yalnız 4xx **ve** tamsayı kod varsa (200 + gövdede `code<0` aynı sınıflanır); kodsuz 4xx / 408 / HTML 404 / 302 → `ExchangeUncertain(http)` |

Ağırlık: her yanıtta `X-MBX-USED-WEIGHT-1M` okunur (IP geneli; feed'in kullanımını da içerir). `≥ weight_soft` → `protective=False` okumalar **uyutulmadan**, gönderilmeden `ExchangeBan(http=None, retry_after_s=<dakika penceresi sonuna kalan sn>)` ile reddedilir (çağıran taramayı atlar); `≥ weight_hard` → yalnız `protective=True` istekler geçer. Emir sayısı: `X-MBX-ORDER-COUNT-10S/1M` okunur; yerel tavan (`20/10 sn`, `100/dk`) aşılırsa `protective=False` emir **gönderilmeden** `ExchangeReject(code=None, msg="order_rate_cap")`; koruyucu emirler borsa sınırının %80'ine kadar geçer. **Testnet muafiyeti:** `env="testnet"` iken başlık ağırlığı paylaşımlı/gürültülü olduğundan (mentor) `weight_soft`/`weight_hard` kapıları uygulanmaz (başlık yine okunur ve `used_weight`'te görünür; ≥ `weight_soft` ise dakikada en çok bir WARNING yazılır); gerçek 429/418/403 ve sessizlik penceresi aynen geçerlidir; canlı davranış değişmez. Beklenen kullanım sınırların %5'inin altındadır; 429/418 görülmesi **hatadır** (§10).

**Gönderim öncesi `ExchangeBan`** (sessizlik penceresi, `weight_hard`, `weight_soft`) = istek borsaya **kesinlikle gönderilmedi**. Çağrı başına `attempts=` (yalnız anahtar sözcük; `request`, `query_order`, `query_conditional`) `max_attempts`'i geçersiz kılar; WP-B3/B4 durdurma süresi sınırı için `attempts=1` geçer. İstemci tek iş parçacıklıdır.

**DD-7 — ban dosyası.** Kurucuya `ban_guard: BanGuard | None = None` (anahtar sözcük; `None` = eski davranış). Pencere (`trader_core/ban_store.py`) host başına `<ban_dir>/ban.<host>.json` dosyasında kalıcıdır (`ban_dir` = sürecin açtığı piyasa veritabanının dizini; motor, feed ve OI toplayıcı aynı IP'yi paylaştığı için üçü de okur/yazar). Kurucuda etkin kayıt varsa pencere benimsenir (`ban_file_seeded`); her `_send` öncesi ve `health()` içinde başka sürecin daha uzun kaydı benimsenir (bellekteki pencere asla kısalmaz). 429/418/403 penceresi atandıktan hemen sonra dosyaya yazılır (kalan < 10 sn yazılmaz; yazılamazsa `ban_persist_failed` + ERROR, süreç bellekteki pencereyle sürer). 451 yazılmaz. Bozuk taze dosya 15 dk boyunca yasak sayılır (fail-closed). `SAPI_BASE` yasağı da istemcinin ana host dosyasına yazılır. Paper/backtest'te guard kurulmaz.

`protective=True` yalnız şunlardır: stop kurma, `reduceOnly` piyasa çıkışı, bunların sorgusu ve `protect_first`/mutabakatın pozisyon-emir okumaları.

## 5. `brokers/binance_futures.py` — `LiveBroker`

```python
class LiveBroker:                      # Broker protokolü (03 §3); tasarımdaki adı BinanceFuturesBroker
    is_simulated = False
    def __init__(self, live: LiveSettings, env: Literal["testnet", "live"], leverage: int, pairs: Sequence[str],
                 rest: SignedRestClient, clock: Clock, taker_fee_fallback: float,
                 environ: Mapping[str, str] | None = None)            # environ: yalnız LIVE_PERMISSION_ATTESTED uyarısı için okunur, sonucu etkilemez (DD-8; varsayılan os.environ)
    def startup_check(self) -> None                                    # §3.4
    def closing_events(self, pair: str, since: datetime, client_ids: Sequence[str] = ()) -> list[BrokerEvent]   # §5.5; mutabakat da kullanır
    def register_position(self, pair: str, opened_ts: datetime, client_ids: Sequence[str] = ()) -> None
        # B5 protect_first (yeniden başlatma) ve B4 (giriş dolumunda): yetkili açılış zamanı (funding penceresi başlangıcı) ve
        # pozisyona ait kimlikler (stop/çıkış; çıkış atfı için ipucu). Kayıtsız pozisyon yalnız `_sync` onu açık görürse izlenir.
    def foreign_open_orders(self) -> list[dict]                        # kimliği bizim önek + geçerli rol harfi taşımayan açık emirler
    def health(self) -> dict                                           # rest.health() + sayaçlar, reachable, last_sync_ts, naked, entries_blocked_reasons
    def margin_types(self) -> dict[str, str]                           # son positionRisk okumasından {pair: "isolated"|"cross"} (marginType); ağ çağrısı yok; mutabakat L10 okur
    def counters(self) -> dict; def set_naked(self, rows: list) -> None; last_ban: tuple[http, retry_after_s] | None
    # last_ban: ban penceresi (418/451/403) VE emir yolundaki 429 `rate_limited` retinde de (429, retry_after_s) olarak doldurulur (F8)
    entries_blocked_reason: str | None   # salt okunur; entries_blocked_reasons (öncelik sıralı demet) yapışkan KÜMEDEN türetilir
```

**Giriş engelleri yapışkan kümedir:** `exchange_auth`, `exchange_unknown_code`, `working_type_unverified`, `exchange_unreachable` birbirinin üstüne yazmaz; `entries_blocked_reason` öncelik sırasının ilkini verir. Yalnız `exchange_unreachable` ilk başarılı `_sync`'te kalkar; diğerleri yalnız temiz yeniden başlatmayla.

### 5.1 Eşlik tablosu (PaperBroker ↔ LiveBroker)

| Yöntem | LiveBroker davranışı | Paper'dan fark |
|---|---|---|
| `rules(pair)` | §5.2 önbelleği; yoksa `DataError` | kaynak borsanın kendisi |
| `account()` | `/fapi/v2/account`: `wallet=totalWalletBalance`, `unrealized=totalUnrealizedProfit`, `equity=totalMarginBalance`, `used_margin=totalInitialMargin`, `available=availableBalance`; 2 sn önbellek | değerler borsadan |
| `positions()` | `positionRisk`, `positionAmt != 0`: `side` işaretten, `qty=abs`, `entry_price`, `leverage`, `margin=isolatedMargin`, `liq_price=liquidationPrice`, `mark_price`, `unrealized`; `funding_paid=0.0`, `fee_paid_entry=0.0`, `opened_ts=updateTime` (**yetkili değil**) | funding/komisyon alanları boş |
| `open_orders(pair)` | açık normal + koruyucu emirler, **yalnız** kimliği `trL`/`trT` ile başlayanlar; rol kimlik harfinden (`e/s/t/x`) | yabancı emirler ayrı yöntemde |
| `prepare(pair, lev)` | süreç içi önbellek: `startup_check` adım 6 geçtiyse ve `lev == cfg.leverage` ise **istek atmaz**; değilse `BrokerError` | idempotent, ağsız |
| `market_order(req)` | §5.3 | **anında dolum** (`filled`) |
| `place_stop(req)` | §5.4; `accepted` | aynı ret adları |
| `place_target(req)` | `TAKE_PROFIT_MARKET`, aynı kurallar; motor çağırmaz | — |
| `cancel(pair, cid)` | rol harfine göre normal/koruyucu iptal; yoksa no-op; belirsizlikte `BrokerUncertain` | — |
| `query(pair, cid)` | rol harfine göre sorgu (**her rolde `attempts=1`**); yok (`-2013`) → `None`; yalnız borsanın bildirdiği `executedQty`/`actualQty` `filled_qty` olur (yoksa 0); sonuç kimlik öğrenmeye girer (§5.5); durum eşlemesi: `NEW/PARTIALLY_FILLED→new`, `FILLED/TRIGGERED/FINISHED→filled`, `CANCELED→canceled`, `REJECTED→rejected`, `EXPIRED→expired` | — |
| `poll(now)` | §7: iç kuyruğu zaman sırasıyla boşaltır; gerekirse önce `_sync(now)` | bar değil duvar saati |

Ret adı eşlemesi (`OrderResult.reason`; paper ile aynı sözlük + `exchange_<kod>`): `-2021 → would_trigger`; `-4116 → duplicate_client_id`; `-2019 → insufficient_margin`; `-4164 → min_notional`; `-2022 → reduce_only_exceeds`; `-1111, -1013, -4003, -4005, -4131 → filter:<kod>` (giriş yolunda kurallar **hemen** yenilenir; koruyucu yolda — stop/hedef/çıkış — satır içi yenileme **yok**: kural kirli işaretlenir, sonraki `_sync` yeniler, §5.2); `-1021 → exchange_-1021` (bilinen: `clock_rejects`, giriş engeli yok); ban penceresi (gönderim öncesi, emir kesin gitmedi) `→ exchange_ban` (`last_ban` doldurulur); emir POST'unda `ExchangeAuth` `→ exchange_auth` (+ `exchange_auth` sayacı, yapışkan giriş engeli, `CRITICAL`); stop yanıt durumu terminal `→ exchange_status:<durum>` (§5.4); piyasa emri `REJECTED` `→ exchange_rejected`; `429 → rate_limited`; `order_rate_cap`; tanınmayan her kod → `exchange_<kod>`, sayaç `unknown_reject_codes`, `CRITICAL`, `entries_blocked_reason="exchange_unknown_code"` (yapışkan; hiçbir başka neden onu ezmez; mutabakat temizlemez; yalnız temiz bir yeniden başlatma temizler). Kodlar T-09'da gerçek yanıtla sabitlenir.

### 5.2 Kurallar (min notional / adım / tick)

`LiveBroker` kuralları **kendi ortamının** `exchangeInfo`'sundan alır (testnet kuralları gerçek ortamdan farklı olabilir): açılışta, saatte bir ve her `filter:*` reddinde (giriş: hemen; koruyucu yol: bir sonraki `_sync`'te). Ayrıştırma ve yuvarlama **yalnız** `exchange/rules.py` işlevleriyle: `extract_all_rules` → `to_symbol_rules`; miktar `round_market_qty` (aşağı), stop `round_stop_tight`, hedef `round_target_easy`. Kural yaşı 6 saati geçerse o çift için `rules()` `DataError` verir (giriş yok; çıkışlar son bilinen kuralla sürer). **reduceOnly çıkış hiçbir zaman kural eksikliği yüzünden yerel olarak engellenmez:** çiftin kuralı hiç yoksa miktar verildiği gibi gönderilir (kural kirli işaretlenir); borsa reddederse ret eşlemesi geçerlidir. Kuralı olmayan çifte giriş ve stop `rules_missing` ile reddedilir (stop için tick bilinmez); tutulan pozisyonla `CRITICAL`. `live` kipinde açılışta feed'in `market.sqlite` kurallarıyla karşılaştırılır; fark varsa `WARNING` (`rules_drift:<pair>`), broker'ın taze kopyası geçerlidir.

Gönderim öncesi yerel doğrulama (ret = ağ çağrısı yok, paper ile aynı adlar): `qty` sonlu `> 0`, `step`'in tam katı, `≤ max_qty`; giriş için `qty × referans ≥ min_notional` (referans = o çift için görülen **son `positionRisk` mark'ı**; hiç yoksa kontrol atlanır, borsa `-4164` verir); `trigger_price` tick'in tam katı. Eksik min-notional için varsayılan **yoktur** (07 §7).

### 5.3 Piyasa emri

`POST /fapi/v1/order`: `symbol, side, type=MARKET, quantity, newClientOrderId, newOrderRespType=RESULT`, çıkışta `reduceOnly=true`. `positionSide` gönderilmez (one-way).

| Yanıt | Sonuç |
|---|---|
| `status=FILLED` | Giriş: `OrderResult("filled", filled_qty=executedQty, avg_price=avgPrice, fee=cumQuote × taker_rate)` ve kuyruğa `Fill(reason="market")` olayı. Çıkış: `OrderResult("accepted")`; dolum olayı §5.5 yoluyla (kesin komisyonla) |
| `NEW` / `PARTIALLY_FILLED` | 0,3 sn aralıkla en fazla `fill_wait_s = 3` sn sorgulanır; son duruma göre üst/alt satır. Hâlâ açıksa `accepted`, emir `_pending_market`'te izlenir; **her `poll` turunda** (`attempts=1`) sorgulanır ve sonlandığında olay üretir; emir artık bulunamazsa (`-2013`) izlemeden çıkarılır + bulgu `pending_order_not_found:<cid>` (`CRITICAL`). Giriş `accepted` dönebilir: B4 bunu "dolum henüz bilinmiyor" sayar ve dolum olayını `poll`'dan bekler |
| `EXPIRED`/`CANCELED`, `executedQty > 0` (kısmi) | Giriş: `executedQty` ile `filled` (pozisyon küçük açılır; risk yalnız azalır). Çıkış: dolum olayı **üretilmez**; `order_rejected` olayı (`detail="partial_exit:<executedQty>"`) → motor pozisyonu `open`'a döndürür, mutabakat L4 miktarı ve stopu küçültür |
| `EXPIRED`/`CANCELED`, `executedQty == 0` | `order_rejected` olayı (`detail="expired_unfilled"`); **dönüş `accepted`** (olay satırı aynı zamanda sonucu taşır). B4 her piyasa emrinden sonra `poll`'u hemen çağırır |
| `REJECTED` | `OrderResult("rejected", reason="exchange_rejected")` |
| `ExchangeReject` | `OrderResult("rejected", reason=<§5.1>)` |
| `ExchangeUncertain` | `BrokerUncertain` yükseltilir |

Giriş komisyonu `cumQuote × takerCommissionRate` ile hesaplanır (oran §3.4 adım 8); çıkışta `userTrades` giriş işlemlerini de kapsadığından gerçek komisyonla karşılaştırılır, fark `%1`'i aşarsa `fee_drift` sayacı + `WARNING` (defter düzeltilmez).

**DD-8 D2 — giriş öncesi hesap modu doğrulaması.** `market_order` yalnız `role == "entry"` için, yerel denetimlerden sonra ve POST'tan hemen önce **taze** `position_risk(<symbol>)` okur (önbellek/`_sync` yetmez; giriş başına tam 1 ek okuma). Satır var + `marginType` küçük harfle `isolated` + `leverage` tam sayı olarak `cfg.leverage` değilse emir **gönderilmez**: `OrderResult` reddi `not_prepared`; uyuşmazlıkta sayaç `account_mode_drift` + `CRITICAL`, okunamazsa (her `ExchangeError`, satır/alan yok) `account_mode_unverified` + `ERROR`. `ExchangeBan` ayrıca `_note_ban`, `ExchangeAuth` ayrıca `exchange_auth` kilidi. `_prepared` kümesine dokunulmaz; doğrulama her girişte yeniden yapılır; motor kendiliğinden `set_isolated`/`set_leverage` göndermez. Çıkış, stop, hedef ve iptal yolları bu okumayı yapmaz.

### 5.4 Koruyucu emir

`conditional_mode="algo"` [V-1]: `POST /fapi/v1/algoOrder` — `algoType=CONDITIONAL, symbol, side, type=STOP_MARKET, quantity, triggerPrice, workingType=MARK_PRICE, reduceOnly=true, priceProtect=false, clientAlgoId`. `"classic"`: `POST /fapi/v1/order` — `type=STOP_MARKET, stopPrice, workingType=MARK_PRICE, reduceOnly=true, newClientOrderId`. `req.working_type != "MARK_PRICE"` ya da `req.reduce_only is not True` → yerel ret (`not_reduce_only` / `bad_working_type`), istek gitmez. **Yanıt doğrulaması (kabul yanıtı incelenmeden `accepted` dönülmez):** durum (`algoStatus`/`status`) `NEW` (ya da `TRIGGERING/TRIGGERED/FINISHED/PARTIALLY_FILLED/FILLED`: çıkış olayı §5.5'ten akar) ise kabul. Terminal dolumsuz (`REJECTED/EXPIRED/CANCELED`) → kesin ret `rejected`, `reason="exchange_status:<durum>"` (F2 yolu). Durum yok/tanınmıyor/gövde boş → **tek** `query_conditional(attempts=1)`; hâlâ bilinmiyorsa `BrokerUncertain`. Yankı varsa doğrulanır: `clientAlgoId`(klasik: `clientOrderId`) `== cid`, `reduceOnly is True`, `closePosition is not True`; uyuşmazlık → emir iptal edilir (iptal edilemezse bulgu `uncancelled_protective:<cid>`), `rejected` (`reason="response_mismatch:<alan>"`, sayaç `stop_response_mismatch`, `CRITICAL`). `workingType` `MARK_PRICE` değilse emir **hemen iptal edilir**, `rejected` (`reason="working_type_mismatch"`), `CRITICAL`. `workingType` yanıtta yoksa tek `query_conditional(attempts=1)` ile aranır; hâlâ yoksa emir kabul edilir ama `CRITICAL`, sayaç `working_type_unverified` ve yapışkan giriş engeli `working_type_unverified` (kullanıcı borsada elle doğrular).

Hemen tetiklenecek konumdaki stop: borsa `-2021` ile reddederse `would_trigger`. Algo servisi reddetmeyip kabul edip anında tetiklerse bu da güvenlidir: pozisyon kapanır, §5.5 çıkışı `stop` olarak üretir (T-06 hangisinin olduğunu kaydeder).

### 5.5 Çıkış olaylarının türetilmesi — `closing_events(pair, since)`

Çıkış kaydı tek olaydır. Tetik: bir sembolün borsa pozisyonu sıfıra indiğinde (`_sync` geçişi görünce, eşzamanlı piyasa çıkışı `FILLED` dönünce hemen, ya da mutabakat L3).

1. `user_trades(symbol, since_ms − 1000)`; sondan başa yürünür ve pozisyon sıfırdan başlayana dek (girişler Σ = azaltmalar Σ) pozisyonu **azaltan** TÜM işlemler (stop + araya giren dış azaltmalar) kapanışa dahildir (tek mod; miktar çıkarımı ile bilinen-miktar kipi ayrışmaz). Son bilinen pozisyon miktarı yalnız **tamamlanma alt sınırıdır**: azaltmalar Σ bunun altındaysa 1 sn arayla en fazla 3 kez yeniden okunur; yine eksikse (ya da giriş görünmüyor ve alt sınır yoksa, ya da bozuk/eksik satır varsa: `malformed_trades`) boş liste döner (sonraki turda yeniden denenir; borsa düz olduğundan risk yoktur). Giriş pencere dışındaysa azaltmalar bilinen miktarda kesilir. `_pending_close` yeniden denemesi ilk 3 denemeden sonra `poll_open_s`'te bir ile sınırlıdır; 60 sn çözülemezse bulgu `close_unresolved:<pair>` (`CRITICAL`). Pozisyonu `register_position` ile kaydedilmemiş ve `_sync`'in açık görmediği (yalnız `positions()` okumasıyla görülen) çiftte `_sync` kapanış türetmez; bunu mutabakat L3 yapar. `_sync`'in kendi gördüğü pozisyonun `since`'ı `min(şimdi, updateTime) − 2 sn`'dir (yetkili değil; B4/B5 `register_position` ile düzeltir).
2. `Fill`: `qty = Σ qty`, `price = Σ(qty×price)/Σ qty`, `fee = Σ commission`, `ts = son işlemin zamanı`. `commissionAsset != "USDT"` görülürse `fee = qty × price × taker_rate`, sayaç `fee_asset_unexpected`, `CRITICAL`.
3. `reason` ve `client_id`, pozisyonu **sıfırlayan** işlemin emrinden. Çözüm sırası: (a) `userTrades` satırındaki kimlik; (b) bellekte **hatırlanan/öğrenilen** `orderId`/`actualOrderId → kimlik` (her `open_orders()`/`query()` sonucu ve piyasa emri yanıtı bunu besler; yeniden başlatma sonrası stop bu yolla bulunur); (c) ipuçları: `closing_events(client_ids)`, `register_position` kimlikleri, çiftin bilinen stopları (en yeniden eskiye) ve **son 3 iptal edilen** koruyucu kimliği, çiftin bilinen `x` kimlikleri — her biri `attempts=1` ile sorgulanıp `actualOrderId`/`orderId` eşleşmesine bakılır (iptal başarılı olunca stop bilinenlerden çıkar; kapanışta çift başına tüm kimlik durumu budanır); (d) `GET /fapi/v1/order?orderId=` (`SignedRestClient.query_order_by_id`): **yalnız `-2013` "emir yok" demektir**; başka her ret/ağ hatası boş liste + sonraki turda yeniden deneme (asla `foreign_close` sebebi değil); (e) yabancı ilan etmeden önce `GET /fapi/v1/forceOrders` (`SignedRestClient.force_orders`, `LIQUIDATION` ve `ADL`): `orderId` orada geçiyorsa `liquidation` (emir sorgulanamasa bile). Sonuç: kimlik `autoclose-`/`adl_autoclose` ile başlıyorsa ya da forceOrders'ta bulunduysa `liquidation` (olay türü `liquidation`); bizim tetiklenmiş stopumuzsa [V-7] `stop` (kimlik = stop kimliği); bizim `x` kimlikli emrimizse `market`; hiçbiri değilse `market` + `detail="foreign_close"` (motor `exit_reason="manual"` yazar, `CRITICAL`). Okuma/ağ hatası = boş liste + yeniden deneme.
4. Funding: `income(symbol, "FUNDING_FEE", since_ms, ts_ms + 5000)` kayıtları çıkış olayından **önce** `funding` olayları olarak verilir (`funding_paid = −income`; pozitif = ödenen). Okunamazsa 60 sn boyunca her turda yeniden denenir; sonra çıkış `funding_paid=0` ile verilir ve bulgu `funding_unresolved:<pair>` (`CRITICAL`; elle düzeltme).
4b. Funding tekilleştirme anahtarı `(symbol, tranId)`'dir (farklı sembollerde aynı `tranId` birbirini bastırmaz).
5. Aynı kapanış iki kez teslim edilmez: teslim edilen `tradeId` kümesi süreç belleğinde tutulur; motor tarafında ikinci savunma §6.6.

**B4/B5 için notlar (LiveBroker sözleşmesi):** (1) mutabakat L3'ten önce `poll` çağrılır; (2) giriş `accepted` dönebilir (dolum sonradan `poll`'dan gelir) ve `order_rejected` olay satırı olsa bile `OrderResult` `accepted` olabilir: B4 her piyasa emrinden sonra `poll`'u hemen çağırır; (3) state'te pozisyonu olmayan çift için gelen dolum olayları tolere edilir (yeniden başlatma, geç dolum); (4) çıkış emri borsadaki pozisyondan **az** doldurursa (kısmi) kapanış olayı üretilmez (pozisyon sıfırlanmadı); mutabakat L4 miktarı küçültür; (5) yeniden başlatmada B5 `protect_first` bulduğu her pozisyon için `register_position(pair, opened_ts, client_ids)` çağırır, B4 giriş dolumunda aynısını çağırır.

## 6. Emir yaşam döngüsü — motor ve `OrderManager` değişiklikleri (WP-B4)

### 6.1 İşlem (tx) düzeni

Bugün `_decision_step` ve `_process_step` tek dış `state.tx()` içinde çalışır; `StateStore.barrier(allow_outer=False)` gerçek brokerda bunu `StateError` ile reddeder. Canlı kural:

- `is_simulated` ise dış tx **aynen** kalır. Değilse dış tx **açılmaz** (`contextlib.nullcontext`).
- Tx dışında yazan her yazma grubu kendi `with self.state.tx():` bloğuna alınır (paper'da iç içe sayaçla etkisizdir, canlıda gerçek commit'tir). Atomik gruplar: **G1 giriş niyeti** = `insert_position` + `mark_decided` + `kv eq:<tid>`; **G2 dolum** = pozisyon `open` + emir `filled` + `outbox_add("entry")`; **G3 çıkış** = pozisyon `closed` + `outbox_add("exit")` + emir `filled`; **G4** imleçler ve gün başı. Her emir POST'u bu gruplardan birinin commit'inden **sonra**, tx dışında yapılır.
- `broker.advance/snapshot/restore` çağrıları yalnız `is_simulated` iken. `cfg.mode == "paper"` karşılaştırmaları ikiye ayrılır: "feed'li canlı döngü" anlamı `cfg.mode in ("paper", "testnet", "live")`, "benzetimli broker" anlamı `self.is_paper`. Dokunulan yerler: `start` (açılış kapısı, imleç), `_decision_step` (mutabakat), `_periodic_input_check`, `run_range`, `build_engine` (broker kurulumu, defter saati).

### 6.2 Açılış sırası (canlı)

0. **DD-8 zorunlu açılış sırası (`testnet`/`live`; `build_engine` + `Engine.start`):** (1) yapılandırma doğrulama (§3.1 yol kuralı, mutlak yollar; ihlal → 2); (2) `LIVE_CONFIRM`, anahtarlar (→ 2); (3) state kilidi `<state_path>.lock` (engellemesiz `flock`; `StateError` → 3); (4) damga doğrulaması (§3.1 eki; → 8); (5) `LiveBroker.startup_check()` (ilk HTTP isteği; → 5/8); (6) cüzdan tavanı tutuşu → `protect_first()` → `_startup_gate()` → mutabakat. 1–4'te borsaya **sıfır** HTTP isteği gider (`GET /fapi/v1/time` dahil); `build_engine(broker=<enjekte>)`te de kilit ve damga broker'ın hiçbir yöntemi çağrılmadan önce tamamlanır. `startup_check` 5/8 ile biterse state ve defter kapatılır (kilit bırakılır).
1. `load_keys` → `SignedRestClient` → `LiveBroker.startup_check()` (§3.4).
2. **`protect_first()`** — açılış veri kapısından **önce**, piyasa verisi gerektirmez. Sıra: **önce çöz, sonra oku** — `orders.resolve_unresolved()` (L1, koşulsuz; bekleyen satırlar + yolda kalmış giriş/çıkış emirleri, L3c), **ardından** borsa pozisyonları ve açık emirler okunur (anlık görüntü L1'den sonra alınır, bayatlamaz). Geç dolum (L2a) `protect_first`'te de çalışır. State'te karşılığı olan (`open`/`closing`) ve borsada stopu olmayan her pozisyon için `current_stop`'ta (yoksa `initial_stop`) borsadaki miktarla stop kurulur (§8 L5); `opening` pozisyon yalnız §8 L2b kanıtıyla benimsenir. Bilinmeyen pozisyona dokunulmaz (§8 L2).
3. Açılış kapısı (`_startup_gate`) **testnet/live'da da** çalışır (`protect_first`'ten SONRA; kâğıttaki 10/10 kural + taze 1 dk last/mark kuralı, aksi hâlde `EngineExit(7)`); sonra parametreler, strateji; sonra tam mutabakat (§8).
4. Canlıda `advance_to` kaçan karar barlarını **yeniden oynatmaz**: yalnız en son kapanmış tetik barı değerlendirilir, aradakiler `skipped_decisions` sayacına yazılır ve karar imleci ona alınır. (Çıkış bağlamı girişten beri tüm barları taşıdığı için iz süren stop/hedef/rejim sonucu aynıdır; kaçan girişler zaten `stale_data` ile reddedilirdi.) Dakika adımları canlıda yalnız MFE/MAE, gün başı ve imleç içindir.

### 6.3 `live_tick(now)` — her döngüde (`loop_sleep_s`), veri akışından bağımsız

Sıra: (1) KILL denetimi (`_kill_step`; besleme dursa da çalışır — mentor B7) → (2) `events = broker.poll(now)` → `_handle_events(events, step=None, now)` → defter outbox'ı boşalt (`_post_commit`) → (3) stop bekçisi (§6.5) → (3b) **ban/yetki yansıtması:** `broker.last_ban` son görülenle karşılaştırılır (okuma yolundaki yasaklar da yakalanır; F8–F11) ve brokerın `entries_blocked_reasons` listesi (`exchange_auth` dahil) kapıya/duraklatmaya yansıtılır → (3c) girdi denetimi: `check_inputs()` dakikada bir (`rules_missing`/`data_stale` sayaçları; karar vermez) → (4) zamanı geldiyse mutabakat → (5) `advance_to(now)` → (6) `status.json`. **DD-6 eklemeleri:** (a) `advance_to` `DataError` verirse motor çıkmaz: `advance_errors` sayılır, 2 sn'den başlayıp ikiye katlanan (üst sınır 30 sn) geri çekilmeyle yeniden denenir; art arda 5 hatada girişler `engine_errors` ile kapanır (KILL, bekçi, mutabakat sürer; blokaj elle kalkar). (b) Karar adımı hata verirse aynı barın yazılım çıkışları 5/10/20 sn sonra en çok 3 kez yeniden denenir (`decision_failures`, `exit_retry_ok`); yeni karar adımı bekleyen denemeyi geçersiz kılar. (c) Stop bekçisi `open`/`closing` pozisyonlardan SONRA `opening` pozisyonları da izler: çifti `broker.positions()` içinde görünürse hemen `protect_first` (en sık 5 sn'de bir okuma; deneme anı yazılır; önce `resolve_unresolved`). (d) Açılış kapısı beklerken (canlı) her `loop_sleep_s` adımında KILL, olaylar ve bekçi çalışır. (e) Giriş kapısı (`pre`) canlıda her çiftten önce yeniden okunur; bir önceki girişin `stop_failed`ı kalan çiftleri `gate:stop_failed` ile atlatır. (f) Ayrı pozisyonlarda 24 saat içinde ikinci `stop_failed` (`would_trigger` sayılmaz) kalıcı duraklatma `stop_failed_repeat` ekler (yalnız sunucuda CLI ile kalkar). Sabitler (`engine.py`): `ADVANCE_BACKOFF_BASE_S=2`, `ADVANCE_BACKOFF_CAP_S=30`, `ADVANCE_ERRORS_ENTRIES_OFF=5`, `DECISION_EXIT_RETRIES=3`, `DECISION_EXIT_RETRY_BASE_S=5`, `STOP_FAILED_REPEAT_WINDOW_S=86400`, `OPENING_PROTECT_MIN_GAP_S=5`, `TESTNET_PRICE_DIVERGENCE_MAX=0.005`. Adım hataları **etiket başına** ardışık sayılır (başka adımın başarısı sayacı sıfırlamaz): 3 ardışık → `engine_errors`, 10 → `EngineExit(3)`. `_handle_events`, `_on_entry_fill`, `_on_exit_fill` `step=None` kabul eder (`bar=None`; MFE/MAE dolum fiyatından başlar).

### 6.4 Giriş → stop

1. G1 commit. `submit_entry` (emir satırı `pending` commit → POST).
2. `filled` dönerse motor **hemen** `self._handle_events(self.broker.poll(now), None, now)` çağırır (bir sonraki döngü beklenmez): G2 commit → dolum sonrası risk denetimi → `place_initial_stop`.
3. **Stop süre sınırı:** `t_fill` dolumun öğrenildiği andır. `place_initial_stop` sıra 0 ile dener; başarısızsa ve `now − t_fill ≤ stop_deadline_s − 5` ise (5 sn = emir POST'unun azami süresi, bağlan 2 + oku 3) sıra 1 ile bir kez daha; aksi hâlde ya da ikincisi de başarısızsa `submit_exit(…, "other")` (reduceOnly piyasa) + `entries_blocked_reason="stop_failed"`. `would_trigger` → doğrudan piyasada kapat.
4. **Dolum sonrası risk ihlali** (`fill_risk_violation`): canlıda **önce stop kurulur, sonra** çıkış verilir (mentor C notu: stopsuz `closing` pozisyon kalmaz). Küçültme (r6) yok: kapatılır.
5. **Belirsiz giriş** (canlı, `max_attempts=1`): iki sorgu da "emir yok" derse emir satırı `unknown` **kalır**, pozisyon `opening` kalır, `entries_blocked_reason="order_unknown"`. Mutabakat her turda kimlikle yeniden sorgular; emir bulunursa dolum uygulanır ve stop kurulur (r4/r5). `entry_resolve_window_s` (60 sn) boyunca "emir yok" **ve** borsada o çiftte pozisyon yoksa: emir `failed`, pozisyon motorun `_close_unopened`'ı ile kapanır (`OrderManager._entry_failed` bunu geri çağrıyla motora devreder): defter kararı `skipped`/`order_failed` ile düzeltilir (`supersedes_id`) ve `_entry_events` kaydı atılır. Sonradan geç dolum görülürse §8 L2a.
6. `opening` pozisyon + hiç emir satırı yok (G1 ile POST arasında çökme): açılışta borsada pozisyon yoksa `_close_unopened`; varsa L2a.

### 6.5 Stop bekçisi

Her `live_tick`'te: `open` ya da `closing` durumundaki her pozisyon için `stop_client_id` var ve emir satırı `accepted` mı? Değilse `naked_since` (kv `naked:<tid>`) yazılır; süre `stop_deadline_s`'i aşarsa pozisyon reduceOnly piyasa ile kapatılır, başarısızsa her turda yeniden denenir. **Tüm canlı piyasa çıkışları** (bekçi, KILL, stop kurulamama, dolum sonrası risk ihlali, mutabakat L5/L2b) motorun `_submit_exit`'inden geçer: hemen `poll` + ban penceresi denetimi (pencere içinde yeni kimlik/satır üretilmez). `status.json.exchange.naked` = `[{trade_id, pair, seconds}]`; boş değilse sağlık denetçisi **hemen** CRIT üretir (WP-B8).

### 6.6 İz süren stop (iptal/yenile sırası)

`replace_stop` (04) aynen: sıra `seq+1` kimliğiyle **yeni stop önce**, kabul edilince state güncellenir, **sonra** eski iptal edilir.

| Olay | Davranış |
|---|---|
| Yeni stop reddedildi (`would_trigger` dışı) / belirsiz | Eski stop durur; state değişmez; `WARNING`; belirsizse `order_unknown` + mutabakat çözer. **Eski asla önce iptal edilmez** |
| Yeni stop `would_trigger` | Piyasada kapat (`trail_stop`); kapanınca eski stop iptal |
| Yeni kabul, eski iptali başarısız/belirsiz | İki stop durur (güvenli); mutabakat L7 gevşek olanı iptal eder |
| Yeni kabul, eski iptal edilmeden çökme | Aynı: L7 |
| T-04 "iki stop duramaz" derse | Bu bölüm **geçersizdir**; "iptal → hemen yeni" çeşidi ayrı mentor kararıyla yazılır (motor bekçiliği + süre sınırı); o karar olmadan canlıya çıkılmaz |

Güncelleme sıklığı: tetik barı başına en fazla bir (bar kapanışı). Çıkış dolunca `cancel_resting`; iptal edilemeyen stop yetim kalır ve L8 iptal eder (reduceOnly olduğundan pozisyon açamaz).

Çift teslim savunması: `_on_exit_fill`, pozisyon zaten `closed` ve olayın kimliğindeki emir `filled` ise olayı sessizce yok sayar (`duplicate_fill_ignored` sayacı); `unexpected_fills` yalnız gerçekten karşılıksız dolumda artar.

### 6.7 KILL (canlı)

Mevcut davranış + : her `live_tick`'te denetlenir; `open` pozisyonlar reduceOnly piyasa ile kapatılır (**stop iptal edilmez**; çıkış dolunca iptal edilir — r3); çıkış reddedilirse sonraki turda yeni kimlikle yeniden denenir (`at = now`; her ret/kısmi/bulunamayan deneme `exit_retry` sayacına işler, limit sonrası `exit_unknown` + her turda CRIT — F16); bilinmeyen pozisyonlar §8 L2 istisnasıyla kapatılır (**KILL etkinleştirmesi başına tek deneme**, §8 L2). KILL duraklatmayı kaldırmaz, duraklatma KILL'i kaldırmaz (§9.3).

## 7. Olay kaynağı: REST yoklama (kullanıcı veri akışı ertelendi)

**Karar:** canlı v1'de listenKey/WebSocket **yok**. Gerekçe: (i) döngü tek iş parçacıklı ve senkron; (ii) pozisyonu koruyan şey borsadaki stoptur, motorun dolumu saniyeler geç öğrenmesi güvenliği etkilemez; (iii) giriş/çıkış piyasa emirleri eşzamanlı sonuç döner; (iv) WS yeniden bağlanma, 60 dakikalık listenKey ömrü, 24 saatlik bağlantı kesilmesi ve sıra boşlukları yeni arıza sınıflarıdır ve yine REST mutabakatı ister. Doğruluk yolu her zaman REST'tir (tasarım §1.3).

`LiveBroker._sync(now)` (yalnız `poll` içinden): son eşitlemeden beri `poll_open_s` (izlenen pozisyon ya da `_pending_market` varsa) ya da `poll_flat_s` geçtiyse `position_risk()` (tek çağrı, tüm semboller) okunur ve bellekteki önceki görüntüyle karşılaştırılır:

- sıfır dışı → sıfır: `closing_events(pair, since=ilk görülme zamanı)` kuyruğa;
- miktar azaldı ama sıfır değil: olay yok (mutabakat L4);
- `_pending_market` emirleri sorgulanır; sonlananlar olay üretir.

Borsaya ulaşılamıyorsa `poll` boş liste döner, `health().reachable=False` olur; 3 ardışık başarısız eşitlemede `exchange_unreachable` giriş engeli kurulur (ilk başarılı eşitleme + temiz mutabakatla kalkar; diğer engel nedenlerini ezmez, §5). Ban penceresi (418/429/403) boyunca `reachable=False`, `exchange_bans` sayacı ban başına **bir** kez artar (pencere içindeki yerel retler sayılmaz). `_sync` içinde çalışma zamanı `ExchangeAuth` "ulaşılamıyor" değil `exchange_auth` (sayaç + yapışkan giriş engeli + `CRITICAL`) sayılır. Bekleyen piyasa emirleri ve çözülmemiş kapanışlar `poll_open_s` aralığına bakmaksızın her `poll`'da (kapanışlar kısıtlı, §5.5) denenir. Yeniden başlatmada bellek görüntüsü yoktur; kapanmış pozisyonları L3 yakalar. Beklenen gecikme: stop dolumu en geç `poll_open_s + ağ` içinde (≈ 5–6 sn) deftere düşer. Ağırlık bütçesi (pozisyon açıkken, dakikada): `positionRisk` 12×5 + mutabakat 4×(5+1+1) ≈ 90; düzken ≈ 60; sınır 2400.

İleride WS eklenirse (ertelenenler §15) yalnız **tetik** olur: olay gelince `_sync` hemen çalışır; listenKey 30 dakikada bir yenilenir; durum hiçbir zaman WS iletisinden yazılmaz.

## 8. `reconcile_live.py` — canlı mutabakat

```python
class LiveReconciler(Reconciler):           # ReconcileReport aynen (05 §7)
    def __init__(self, cfg, broker: LiveBroker, state, ledger, orders, clock, kill: Killswitch, pause: EntryPause)
    def protect_first(self) -> ReconcileReport     # L1, L2a, L2/L2b bulgusu, L5; §6.2
    def run(self, now: datetime) -> ReconcileReport
```

Zaman: açılışta `protect_first`, kapıdan sonra tam `run`; pozisyon ya da çözülmemiş emir varken `reconcile_open_s` (15 sn), düzken `reconcile_flat_s` (60 sn). Açık kipte açık emirler yalnız pozisyonlu semboller için sembol bazında okunur; düz kipte sembolsüz tam tarama yapılır (yetim ve yabancı emirler burada bulunur). **Sıra: önce çöz, sonra oku.** Her tur (`protect_first` ve `run`) L1'i (`resolve_unresolved`) borsa okumasından **önce** koşar; pozisyon/emir anlık görüntüsü L1'den sonra alınır. Okumalardan biri başarısızsa tur L1 dışında **hiçbir eylem yapmadan** biter (`findings=("exchange_unreachable",)`); eksik veriyle karar verilmez.

| # | Durum | Eylem |
|---|---|---|
| L1 | **Her tur koşulsuz** (bekleyen satır olmasa da) | `orders.resolve_unresolved()`: `pending`/`unknown` satırlar (canlı giriş penceresi §6.4 madde 5) + L3c |
| L2 | Borsada pozisyon var, state'te açık kayıt yok (ya da yön ters / borsa miktarı state'ten **büyük**) | L2a tutmuyorsa: **hiçbir emir verilmez, iptal edilmez.** `pause.add("unknown_position", by="engine:reconcile")` (kalıcı), `CRITICAL`, bulgu `unknown_position:<pair>`, `fatal`. **İstisna (tek kural):** `kill.active()` ise pozisyon reduceOnly piyasa ile kapatılır (miktar adıma aşağı; kimlik `tr<L/T>x-sha1("<bot>|kill|<symbol>|<kill.at>")[:24]`). **KILL etkinleştirmesi başına TEK deneme** (kimlik `kill.at`'ten; aynı kimlikli satır varsa yeniden gönderilmez); pozisyon durdukça **her turda** `CRITICAL` (`kill_close_pending`). `kill.at` yoksa (operatörün boş `touch KILL` dosyası) kimlik için **kill dosyasının mtime'ı** (`mtime:<ns>`; etkinleştirme başına sabit) kullanılır; dosya hiç okunamıyorsa kapanış **reddedilir** (sabit kimlik üretilmez; `CRITICAL`, `kill_close_refused`). Borsa miktarı state'ten **büyükse** (fazla miktar) mevcut stop/yeniden kurulum **state miktarı** (`min(borsa, state)`) ile yapılır, borsanın tam miktarıyla değil |
| L2a | L2 adayı, ama o çiftte son 24 saatte `failed`/`unknown` durumda bizim giriş emrimiz var ve `query` onu `filled` gösteriyor (geç dolum). `protect_first`'te de çalışır | Pozisyon satırı yeniden açılır (dolum `query`'den), stop o satırın `initial_stop`'unda **hemen** kurulur (kurulamazsa kapatılır), `pause.add("late_fill", …)`, `CRITICAL`. **Sorgu başarısızsa** (veri eksik): bulgu `late_fill_unverified:<pair>`, tutuş **yok**, o turda KILL kapanışı **yok**; sonraki turda yeniden denenir. Yeniden açılan işlemin defter girişi, kararı `skipped` ile düzeltilmiş olsa da outbox'tan boşalır |
| L2b | State `opening` + borsada pozisyon var (benimseme) | **Kanıt şartı:** giriş emri satırı VAR **ve** `query(cid)` terminal (`filled`, ya da `filled_qty>0` ile `canceled`/`expired`) **ve** `filled_qty>0` **ve** yön eşleşir **ve** `bp.qty ≤ filled_qty + step/2` → dolum **sorgudan** (miktar `filled_qty`, fiyat `avg_price`, zaman `updated_ts`) benimsenir, stop kurulur. Satır yok / sorguda "emir yok" / dolumsuz terminal / yön ters / borsa miktarı fazla → **L2** (dokunulmaz, tutuş); `opening` satırı L3b'yi bekler. Sorgu **hatası** → bulgu `opening_unverified:<tid>`, eylem yok, sonraki turda yeniden. Emir hâlâ `new` → poll'a bırakılır. Kanıtsız benimseme **yoktur** (yabancı/ters yönlü/kısmi pozisyon) |
| L3 | State `open`/`closing`, borsada pozisyon yok | `broker.closing_events(pair, pos.entry_ts)` → olaylar normal yoldan işlenir (çıkış kaydı, artık emirler iptal). Olay türetilemiyorsa bulgu `exit_unresolved:<tid>`, girişler kapalı (`reconcile_state_orphan`), sonraki turda yeniden; 10 dakikayı aşarsa `CRITICAL`. Emir verilmez |
| L3b | State `opening`, pencere doldu, emir yok, borsa düz | `_close_unopened` |
| L3c | `opening`/`closing` pozisyonun yolda kalmış piyasa emri (L1'in parçası; her tur tek sorgu, `attempts=1`) | **Çıkış:** `closing` + çıkış satırı `failed`/`rejected`/`canceled`/`expired`, ya da `accepted` iken sorguda terminal-dolumsuz/yok → pozisyon **hemen `open`'a döner**, `exit_retry` sayılır (F16); sorgu **hatası** → eylem yok. Dolmuş/yolda `new` satır poll/L3'e bırakılır. **Giriş:** `accepted` giriş satırı sorgulanır; dolu → benimsenir (motor dolum yolu), yok → `failed`, `new` → bırakılır |
| L4 | İkisi de var, borsa miktarı state'ten **küçük** (dış azaltma, ADL, kısmi çıkış) | **State `qty` ORİJİNAL giriş miktarı olarak KALIR** (`closing_events` pozisyonu azaltan TÜM işlemleri kapsadığından nihai çıkış olayı `qty` = giriş miktarı ve VWAP'ı dış azaltmanın gerçekleşen kâr/zararını zaten içerir; satır ile olay eşleşir). Borsadaki gerçek miktar ve dış azaltmanın tahmini kâr/zararı kv `ext_reduction:<tid>` kaydına yazılır (denetim; defterde çift sayılmaz). Stop ve çıkış emri miktarı **borsa miktarı** olur (`exchange_qty_override`; stop L6 ile yeni önce, eski sonra); **bulgu değil**: `WARNING`/`CRITICAL` günlüğü (değişimde bir kez) + `qty_reduced_external` sayacı + kv kaydı |
| L5 | Pozisyon var (`open`/`closing`), borsada bizim stopumuz **yok** | **Hemen** yeni sıra numarasıyla stop (`current_stop`, sıkı yuvarlama, borsa miktarı). `would_trigger` → piyasada kapat. İkinci deneme de başarısız → piyasada kapat + `stop_failed`. Sayaç `stops_reinstalled` |
| L6 | Stop miktarı ≠ pozisyon miktarı | Doğru miktarla yeni stop, sonra eskiler iptal (r8: yeni stop iptal edilmez) |
| L7 | Aynı pozisyonda birden çok bizim stopumuz (emir satırının `trade_id`'si o pozisyonunki olanlar) | En sıkısı kalır (long: en yüksek tetik; short: en düşük); diğerleri iptal; state `current_stop`/`stop_client_id` kalana eşitlenir |
| L8 | Bizim önekli `reduceOnly` emir, pozisyon yok (yetim) | İptal. Bizim önekli ama `orders` tablosunda olmayan emir: iptal + `CRITICAL` |
| L9 | Yabancı açık emir (`foreign_open_orders()`) | **İptal edilmez.** Bulgu `foreign_order:<symbol>`, `CRITICAL`, `entries_blocked_reason="reconcile_foreign_order"` (emir kalkınca mutabakat temizler) |
| L10 | Açık pozisyonda `marginType != isolated` ya da kaldıraç ≠ `cfg.leverage` | Bulgu `account_mode_drift:<pair>`, `CRITICAL`, `entries_blocked_reason="reconcile_account_mode_drift"` — blok **global**dir (tek çifte değil, `entries_blocked_reason` tekildir); otomatik düzeltme yok. **DD-8 D2:** düz çiftte sapma giriş anında taze okumayla yakalanır (§5.3; `account_mode_drift` sayacı, giriş reddi `not_prepared`) |
| L11 | Defter denetimleri (05 §7 son üç satır) | Aynen |

**Sapma toleransları:** miktar — `|Δ| < step/2` eşit sayılır; stop tetik fiyatı — `|Δ| < tick/2` eşit, borsadaki daha **sıkıysa** state ona çekilir, daha **gevşekse** L6 gibi yeniden kurulur; giriş fiyatı — `|borsa − state| / state > %0,1` ise yalnız `WARNING` + `entry_price_drift` sayacı: **bulgu değildir** (`ok` bozulmaz), eylem yok; aynı şekilde `qty_reduced_external` bulgu değildir. **"Temiz mutabakat" = turun okumalarını tamamlaması** (`exchange_unreachable` bulgusu yok); başka bulgular `exchange_unreachable`/`exchange_rate_limited` mandallarının kalkmasını engellemez; cüzdan — canlı v1'de otomatik denetim yok (§15), günlük raporda bilgi satırı.

Blokaj temizleme: `reconcile_*`, `stop_failed`, `order_unknown`, `exit_unknown` mevcut kuralla (bulgu kalkınca) temizlenir; istisna: `exit_retry` sayacı `_EXIT_RETRY_LIMIT`'e varmış bir pozisyon açık/`closing` durdukça mutabakat `exit_unknown` nedenini her tur yeniden üretir (mandal titremez; pozisyon kapanınca kalkar). Motor ayrıca (`_after_live_reconcile`) turun okumaları tamamlandığında `exchange_unreachable` (broker artık listelemiyorsa) ve — ban penceresi geçtiyse — `exchange_rate_limited` mandallarını kaldırır; ikisi de **temiz yeniden başlatmada** da sıfırlanır. `EntryPause` tutuşlarını mutabakat **asla** kaldırmaz.

## 9. Giriş duraklatma — "girişleri durdur, pozisyonları koru"

### 9.1 İlke

KILL "her şeyi kapat"tır. Duraklatma yalnız **yeni girişi** kapatır: açık pozisyonlar borsadaki stoplarıyla ve normal çıkış kurallarıyla (iz süren stop, rejim, zaman) yönetilmeye devam eder; mutabakat ve stop bekçisi çalışır. Duraklatma **kalıcıdır** ve **kendiliğinden kalkmaz**: süre dolunca, motor yeniden başlayınca, bakiye toparlanınca, mutabakat temiz çıkınca açılmaz. `entries_blocked_reason` bu iş için kullanılmaz (bazı nedenleri motor kendisi temizliyor).

### 9.2 `pause.py`

```python
@dataclass(frozen=True)
class PauseHold: reason: str; by: str; at: str | None; note: str

REASONS = ("user_cmd", "drawdown_review", "unknown_position", "late_fill", "exchange_ban", "exchange_auth", "manual",
           "capital_floor", "stop_failed_repeat", "wallet_above_expected")

class EntryPause:
    def __init__(self, path: str, clock: Clock)          # path = f"{cfg.pause_file}.{cfg.bot}"
    def active(self) -> bool            # dosya var mı; FileNotFoundError dışındaki her OSError -> True (fail-closed)
    def holds(self) -> tuple[PauseHold, ...]   # bozuk/boş/şema dışı dosya -> (PauseHold("unreadable", "system", None, <ilk 200 karakter>),)
    def code(self) -> str | None        # None | "drawdown_review" (o tutuş varsa) | "paused"
    def add(self, reason: str, by: str, note: str = "") -> bool      # aynı nedenli tutuş varsa DEĞİŞTİRMEZ (ilk at/by korunur) -> False
    def remove(self, reason: str, by: str) -> bool                    # son tutuş kalkınca dosya silinir; "unreadable" yalnız dosya elle düzeltilince kalkar
```

Dosya (`fileio.atomic_write_json`): `{"schema": "pause/1", "bot": "learner", "holds": [{"reason": "user_cmd", "by": "telegram:482", "at": "2026-12-30T10:00:00Z", "note": ""}]}`. Oku-değiştir-yaz `f"{path}.lock"` üzerinde `flock` ile (motor ve Telegram süreci aynı dosyaya yazar). Her `add`/`remove` `var/<bot>/pause_audit.jsonl`'e bir satır ekler (`at, op, reason, by, note`). `reason` `REASONS` dışında ise `ValueError`.

**Değişmezler:** (1) `active()` yalnız dosya varlığına bakar; içerik bozuksa da etkindir. (2) `src/trader_engine` içinde `remove` çağrısı **yalnız** `cli.py`'dedir (mimari koruma testi: AST taraması). (3) Motor yalnız `add` çağırır. (4) Dosyayı elle silmek geçerli acil yoldur ve denetim günlüğünde iz bırakmaz; bu yüzden sağlık denetçisi "denetim günlüğünde `remove` yokken tutuş kayboldu" durumunu CRIT verir (WP-B8).

**`wallet_above_expected` (DD-8 O4).** Hesap cüzdanı `live.expected_wallet_max`ı aşınca (açılışta `startup_findings` ile, çalışırken `_ladder_step`in zaten okuduğu `broker.account()` değeriyle; ek REST çağrısı yok) motor `pause.add("wallet_above_expected", by="engine:wallet_cap", note="wallet=<değer> max=<tavan>")` ve `CRITICAL` günlük yazar. Yalnız **girişi** kapatır (çıkış, stop, iz süren stop, KILL, mutabakat etkilenmez). Kalıcıdır; bakiye inse de kendiliğinden kalkmaz; Telegram `/devam` kaldıramaz (yalnız `user_cmd`); tek yol sunucuda `trader_engine pause --bot learner --env <env> --clear --reason wallet_above_expected --by <ad>`; bakiye hâlâ tavanın üstündeyse sonraki denetimde yeniden eklenir. `pause.add` başarısızsa (dosya yazılamadı) süreç açık kalır ama bellekte kilit tutulur: süreç yaşadığı sürece giriş emri gönderilmez, her döngüde `add` yeniden denenir. Paper/backtest'te çalışmaz.

### 9.3 Kapı ve öncelik

`EntryGate.pre` sırası: `params_unavailable` → `trigger_tf_changed` → defter kapısı → `entries_blocked_reason` → `kill` → **duraklatma** → `stale_data`. Duraklatma etkinse `GateVerdict(False, pause.code(), "entry_gate_closed")`; karar olayında `veto_reason = "gate:drawdown_review"` ya da `"gate:paused"`. `Engine._live_gate_code` aynı sırayı izler. Kağıt kipinde de çalışır (kağıt döneminde sınanır).

| Durum | Sonuç |
|---|---|
| Yalnız duraklatma | Giriş yok; pozisyonlar yaşar |
| Yalnız KILL | Giriş yok; pozisyonlar kapatılır |
| İkisi birden | KILL davranışı; kapı kodu `kill` |
| KILL kaldırıldı, duraklatma duruyor | Giriş **hâlâ** kapalı |
| Duraklatma kaldırıldı, KILL duruyor | Giriş hâlâ kapalı |
| Birden çok tutuş | Hepsi kalkana kadar kapalı; biri kalkınca diğerleri etkilenmez |

### 9.4 Risk kademe kuralı ve `drawdown_review`

RK-1 (ayrı şartname `12-risk-kademe.md`; mentor yazar; canlıdan önce zorunlu) düşüş ≥ %20'yi gördüğünde `pause.add("drawdown_review", by="engine:rk1", note="peak=<…> equity=<…>")` çağırır. Bu tutuşu **yalnız kullanıcı** kaldırır: RK-1'in kendi iki adımlı komutu (`/kademe_devam`; tepe değeri de yeniler) ya da sunucuda CLI. `/devam` bu tutuşu **kaldırmaz**. İkiz bu tutuştan etkilenmez (dosya bot bazındadır; `risk-kademe-kurali.md` §5 madde 4). `status.json` ekleri: `"pause": {"active": bool, "holds": [...]}`, `"dry_run": is_simulated`, `"exchange": {"env", "reachable", "last_sync", "clock_offset_ms", "used_weight", "ban_until", "naked"}` (canlı kiplerde).

*12 ile güncellendi (RK-1 uygulandı):* ikinci tutuş nedeni `capital_floor` (özsermaye ≤ net yatırılanın %60'ı; `pause.code()` önceliği `capital_floor` → `drawdown_review` → `paused`; Telegram'dan **açılamaz**, yalnız sunucuda `ladder floor-restart` + yazılı karar). `drawdown_review` yalnız `/kademe_devam` (iki adımlı kod, en erken durmadan 24 saat sonra; kademe satırı yazıldıktan **sonra** tutuş kalkar) ya da sunucuda `ladder resume` ile kalkar; ölçü tabanı yatırılan tutardır, tepe değer değil. Kademe kapısı `EntryGate.pre` sırasında duraklatmadan sonra, `stale_data`'dan önce gelir (`capital_missing`, `ladder_invalid`, `equity_unreadable`, `capital_mismatch`, `capital_unverified`). `LiveBroker.transfers(since, until)` [V-8] eklendi. Ayrıntı: `12-risk-kademe.md` §2–§11.

### 9.5 Telegram ve CLI (`telegram-spec.md` karar 1 bununla kapanır)

Köken kuralı: bir tutuşu Telegram'dan yalnız Telegram'ın kurduğu neden (`user_cmd`) için kaldırabilirsin; motorun kurduğu her tutuş ya kendi özel akışıyla ya sunucuda kalkar.

- **`/durdur`** — iki adımlı (mevcut `pending.json` düzeni: 4 haneli kod, TTL 120 sn, tek kullanım, yalnız çıplak kod yanıtı; `action="pause"`). Onayda yapılandırmadaki **her bot** için `EntryPause.add("user_cmd", by="telegram:<son3>")`. Yanıt: "Yeni giriş durduruldu. Açık pozisyonlar zarar durdurlarıyla açık kalır. Hepsini kapatmak için /hepsini_kapat." Zaten varsa idempotent yanıt (kim, ne zaman). KILL etkinken de kabul edilir.
- **`/devam`** — iki adımlı, çağrı başına **tek katman**: (a) KILL etkinse yalnız mevcut KILL akışı (DD-9 §7: `kill_state == "flat"` şartı **her kipte**, kâğıtta da; `LIVE_BOTS` doluyken durum dosyası `mode=live` değilse ret) (telegram-spec §5.2, karar 2 ve 9 aynen); yanıt, duruyorsa duraklatmayı da bildirir. (b) KILL yok ve `user_cmd` tutuşu varsa: kod → her botta `remove("user_cmd", by="telegram:<son3>")`; yanıt kalan tutuşları bot bot sayar ("learner: drawdown_review — girişler hâlâ kapalı" ya da "girişler açık"). (c) İkisi de yoksa no-op yanıtı. `user_cmd` dışı tutuşlar için: "Bu durdurma Telegram'dan kaldırılamaz: <neden>".
- **`/durum`** ve 21:00 raporu: bot başına duraklatma satırı (neden, kim, ne zaman).
- **CLI:** `python -m trader_engine pause --bot <b> [--reason manual] [--by ad] [--note …]` ve `pause --bot <b> --clear --reason <neden> --by <ad>`; `--list`. Telegram çökmüşken tek yol budur.
- **Giriş engeli nedenleri (DD-2):** `entries_blocked_reasons` bir **kümedir** (hiçbir neden diğerini ezmez; `entries_blocked_reason` kümenin öncelikli üyesidir). Elle kalkan nedenler (`engine_errors`, `strategy_mismatch`) yalnız motor DURUKEN `python -m trader_engine unblock --bot <b> --reason <neden> --by <ad> [--note …]` ile kalkar (kayıt: `<var>/<bot>/block_audit.jsonl`); `unblock --bot <b> --list` kümeyi gösterir.
- **Defter spool onarımı (DD-2 / O14):** yapısal olarak okunamayan spool satırı (bozuk/yarım JSON, dict değil, `type` yok/bilinmiyor) `<defter>.spool.corrupt.jsonl`e taşınır; ayrıştırılabilen ama kayda reddedilen satır spool'da KALIR (girişler kapalı, `spool_pending`, CRIT). Onarım: `<defter>.spool.corrupt.jsonl` içindeki satırdan eksik kaydı (ör. yarım giriş) elle yeniden kurup spool'a ekle, sonra `drain_spool` (motor/`entries_allowed` bir sonraki turda bosaltir) ile boşalt.

## 10. Arıza kipleri ve zorunlu davranış

**Değişmez (X):** borsada pozisyon varken borsada duran stop yokluğu **10 sn**'yi (`stop_deadline_s`) aşamaz; aşarsa motor pozisyonu reduceOnly piyasa ile kapatır. Çökme sonrası yol için hedef **≤ 45 sn** (birim `RestartSec=2`, `protect_first` veri kapısından önce; D-2'de ölçülür). Motor borsaya hiç ulaşamıyorsa süre motor tarafından sınırlanamaz; o durumda koruma: izole teminat + düşük kaldıraç (kayıp o pozisyonun teminatıyla sınırlı), dış kalp atışı alarmı ve kullanıcının Binance uygulamasından elle kapatması (§12 son madde).

| # | Arıza | Zorunlu davranış |
|---|---|---|
| F1 | Pozisyon açıkken ağ kesildi (stop borsada) | Emir gönderilmez, tekrar fırtınası yok. 3 başarısız eşitlemede `exchange_unreachable` (giriş kapalı). Mutabakat eylemsiz. Bağlantı gelince: `_sync` → mutabakat; pozisyon kapanmışsa L3 çıkışı türetir. Kesinti > 60 sn → CRIT (sağlık) |
| F2 | Giriş doldu, stop **reddedildi** | Süre uygunsa yeni kimlikle bir deneme daha; olmazsa reduceOnly piyasa çıkışı + `stop_failed`. `would_trigger` → doğrudan çıkış |
| F3 | Giriş doldu, stop POST'u **belirsiz** | Kimlikle sorgu; bulunduysa benimse. İki sorgu "yok" → (süre varsa) sıra 1 ile yeni stop; yoksa çıkış. Sorgu başarısızsa ve süre uygunsa **yeni kimlikle (sıra 1) ikinci stop** denenebilir (iki stop durması güvenlidir, L7 gevşeği iptal eder); sonra çıkış. Çıkış da başarısız → bekçi her turda yeniler |
| F4 | Giriş doldu, stop kurulmadan **süreç öldü** | Yeniden başlatma → `protect_first`: emir sorgusu → dolum benimsenir → stop `initial_stop`'ta kurulur. Hedef ≤ 45 sn |
| F5 | Giriş POST'u belirsiz + çökme | Açılışta L1; emir doluysa F4; yoksa pencere sonunda `_close_unopened`. Kör yeniden gönderim **yok** |
| F6 | Kısmi dolum + çökme | Stop borsadaki gerçek miktarla kurulur (`protect_first` miktarı `positionRisk`'ten alır) |
| F7 | Saat kayması (`-1021`) | Eşitle + bir tekrar. `|offset| > 5 sn` → `clock_skew` (giriş kapalı), CRIT; koruyucular çalışır |
| F8 | 429 | `Retry-After` boyunca tam sessizlik: **ilk** 429'dan (emir reddi `rate_limited` ya da okuma yasağı) itibaren motor yeni gönderim yapmaz (`_ban_until`); `entries_blocked_reason="exchange_rate_limited"`; CRIT. **DD-7:** pencere ban dosyasına yazılır (`Retry-After` ≥ 10 sn), başka süreçlerce de görülür. **Kaldıran: motor** (`_after_live_reconcile`): pencere geçtiyse ve bir mutabakat turu okumalarını tamamladıysa (ya da temiz yeniden başlatmada) kv'den silinir |
| F9 | 418 (IP yasağı) | Pencere bitene kadar tam sessizlik; `pause.add("exchange_ban")` (kalıcı: yasak bir **hata** göstergesidir, insan bakar); CRIT. Bitince `protect_first` → mutabakat. **Tutuşu motor ekler**: her `live_tick`'te `broker.last_ban` (emir *ve okuma* yolu) taranır; yalnız emir ret yoluna bağlı değildir. **DD-7:** pencere diske yazılır; yeniden başlatma pencere içinde istek atmaz (açılışta bekle + çıkış 5, §3.4-1); feed/OI toplayıcının yazdığı kayıt çalışırken de benimsenir (`live_tick`) |
| F10 | 451 / 403 | Açılışta çıkış kodu 8. Çalışırken (her yolda, `last_ban` taramasıyla): `pause.add("exchange_ban")`, CRIT ("sunucu bölgesi/WAF"), okumalar 5 dakikada bir denenir. **DD-7:** 403 penceresi de ban dosyasına yazılır (451 yazılmaz, pencere değildir) |
| F11 | Anahtar geçersiz / IP izinli değil (`-2014/-2015`, 401) | Açılışta çıkış kodu 8. Çalışırken: brokerın `exchange_auth` nedeni motorca görülünce `pause.add("exchange_auth", by="engine:broker")` (her yolda), CRIT, okumalar 60 sn'de bir denenir (emir gönderilmez) |
| F12 | İz süren stop: yeni kabul, eski iptal edilemedi | İki stop durur; L7 |
| F13 | Stop tetiklendi, motor kapalıydı | Açılışta L3: `userTrades`'ten çıkış, neden `stop`/`trail_stop`; yetim emirler L8 |
| F14 | Likidasyon / ADL | L3 → `liquidation`; CRIT; risk kademe kuralı madde 7 (ayrı iş) |
| F15 | Bilinmeyen pozisyon / yabancı emir | L2 / L9; emir verilmez |
| F16 | Çıkış emri reddedildi, kısmi doldu ya da (iki sorguda) bulunamadı | Pozisyon **hemen** `open`'a döner (`closing`te beklemez; §8 L3c), stop yerinde; sonraki bar/tur yeni kimlikle. **Reddedilen ve kısmi çıkışlar da `exit_retry` sayacına girer**; `_EXIT_RETRY_LIMIT` sonrası `exit_unknown` + CRIT (KILL/bekçi her turda yeniden gönderse de sessiz kalınmaz) |
| F17 | `state.sqlite` yazılamıyor (`StateError`) | Süreç çıkar (mevcut); borsadaki stop korur; yeniden başlatma `protect_first`. POST öncesi commit çiti sayesinde kaydı olmayan emir olamaz |
| F18 | Tanınmayan borsa hata kodu | Emir `rejected`; `exchange_unknown_code` (giriş kapalı, yeniden başlatmaya kadar); CRIT. Stop yolundaysa F2 |
| F19 | Kurallar bayat / filtre reddi | Kurallar hemen yenilenir; o çifte giriş yok; çıkışlar son bilinen kuralla |
| F21 | `<defter>.spool.corrupt.jsonl` doldu (DD-8 E4: okunamayan spool satırı karantinada; sessizce kaybolmuş işlem/karar kaydı) | Sağlık: `spool_corrupt:<bot>` CRIT (anında), yedek dosyayı `ledger_<bot>.sqlite.spool.corrupt.jsonl` olarak kopyalar (`MANIFEST.json`: `spool_corrupt_bytes`). Alarm dosya boşalana/adı değişene kadar sürer. **Motor bu dosyayı hiçbir zaman silmez/kısaltmaz.** Temizleme elle: inceleme sonrası dosya `…spool.corrupt.<YYYYMMDD>.jsonl` adına taşınır |
| F20 | Feed durdu (borsa erişimi var) | `live_tick` çalışır: KILL, olaylar, bekçi, mutabakat. Karar adımı yok → giriş yok, iz süren stop güncellenmez (eski stop korur) |

**Yasak sırasında elle kapatma (DD-7).** Borsa geçici engel koyduğunda (418/429/403) bot engel bitene kadar **hiç** emir göndermez (koruyucu istek dahil: göndermek engeli uzatır); borsadaki zarar-kes emirleri yerinde durur. Açık pozisyon varsa sağlık en geç ≈ 5 dakikada `exchange_ban_open_positions` CRIT alarmı gönderir (Telegram: "Borsa geçici engel koydu, açık pozisyon var"). Pozisyonu kapatmak istersen: Binance uygulaması → Vadeli → Pozisyonlar → "Piyasadan kapat". Bot engel bitince kapanışı mutabakatta `manual` olarak kaydeder. `exchange_ban` duraklatma tutuşu sunucuda `pause --clear` ile kalkar. Ban dosyası (`var/ban.<host>.json`) yalnız yanlış kayıt **kesinse** elle silinir; süresi dolan dosya zararsızdır, silinmez. Sağlık denetimi: `exchange_ban` (WARN `exchange_ban`, CRIT `exchange_ban_open_positions`, WARN `exchange_ban_file_corrupt`).

## 11. Testnet planı — 28 Aralık'tan önce geçmesi gerekenler

Her madde `scripts/smoke_testnet.py` ile çalıştırılır (T-01…T-12 `b0-t01…b0-t12` adımlarıyla: ham uç davranışı, tek çift/asgari miktar; T-13+ ve D-tatbikatları: motor sınıflarıyla). T-12 (funding) yalnız **okuma/gözlem**dir ve engelleyici değildir (durum `GOZLEM`); T-04/T-07 tetik bekler (`--trigger-wait-s`, `--t13-stop-pct`). Defterde olan alanlar (ör. neden `trail_stop`) betikçe değil **elle** doğrulanır: tam komutlar `11-testnet-sonuc.md`'de; gerçek yanıt `tests/engine/fixtures/binance/testnet/<madde>_<ad>.json` olarak kaydedilir (anahtar, imza, hesap kimliği silinir); sonuç `trader/docs/motor/11-testnet-sonuc.md`'ye **GEÇTİ / KALDI / FARKLI** olarak yazılır. "FARKLI" = borsa beklenenden farklı ama güvenli davranıyor; mentor kararı gerekir. Bir tane bile açık KALDI varken duman testine geçilmez. Durum sözlüğü ayrıca `KISMI` (ölçüt kısmen sağlandı; ör. T-15'te < 2 pozisyon — **GEÇTİ sayılmaz**), `BEKLEMEDE` (tetik gelmedi; yinelenir) ve `GOZLEM` (T-12; engelleyici değil) içerir. T-03/T-13/D-4'te tetik anındaki **mark ve son fiyat** kaydedilir; stop mark eşiği geçilmeden tetiklendiyse `FARKLI`dır.

| # | Denetim | Beklenen (kesin ölçüt) |
|---|---|---|
| T-01 | Koşullu emir ucu [V-1][V-2] | `algoOrder` ile `STOP_MARKET` kabul; yanıtta kimlik alanı adı, durum sözlüğü, `workingType` alanı kaydedilir. Eski uç ne dönüyor kaydedilir. Sonuç `conditional_mode`'u sabitler |
| T-02 | Hesap hazırlığı | `ISOLATED`, one-way, kaldıraç 3 ayarlanır; ikinci çağrıda `-4046`/`-4059`; **açık pozisyon/emir varken** `marginType` ve kaldıraç düşürme ret kodları (beklenen `-4048`, `-4047`, `-4161`; fake_exchange bunları modeller, §3.4 adım 6 çift başına yakalar); `positionRisk` `marginType="isolated"`, `leverage="3"` |
| T-03 | **MARK_PRICE tetik** | Stop sorgusunda `workingType="MARK_PRICE"`. Mark'tan %0,1 uzağa stop kurulur; 1 sn aralıkla `premiumIndex.markPrice` ve son fiyat kaydedilir; tetik anında **mark** eşiği geçmiş olmalı; son fiyat eşiği mark'tan ≥ 2 sn önce geçtiyse o sürede tetiklenmemiş olmalı (bu gözlem yakalanamazsa 3 kez yinelenir ve "yalnız alan doğrulandı" diye not edilir) |
| T-04 | İki stop aynı anda [V-3] | Aynı pozisyona iki `reduceOnly` stop (farklı tetik) kabul; biri tetiklenince diğerinin akıbeti (iptal / süresi doldu / duruyor) kaydedilir. Kabul edilmezse §6.6 son satırı devreye girer |
| T-05 | **reduceOnly davranışı** | (a) pozisyonsuz `reduceOnly` stop: ret kodu; (b) pozisyondan büyük `reduceOnly` piyasa: ret mi kırpma mı; (c) pozisyon dışarıdan küçültüldükten sonra eski (büyük) stop tetiklenince yalnız kalan miktar kapanıyor, ters pozisyon **açılmıyor**; (d) min notional altı `reduceOnly` kabul [V-4] |
| T-06 | Hemen tetiklenecek stop | `-2021` ile ret **ya da** kabul + anında tetik; hangisi olduğu kaydedilir; ikisinde de pozisyon stopsuz kalmıyor |
| T-07 | Tetiklenen stop ↔ `userTrades` [V-7] | Tetik sonrası sorguda gerçek emir kimliği alanı; `userTrades.orderId` eşleşmesi; **algo emrinin çocuk (gerçek) emrinin `clientOrderId`'si** (stop kimliğiyle aynı mı, otomatik mi — fake_exchange `child_cid_mode="auto"` temkinli varsayılanı bu sonuca dek; `"same"` yalnız T-07 öyle derse varsayılan olur); **likidasyon emrinin `GET /fapi/v1/order?orderId` ile sorgulanabilirliği** (`liquidation_queryable`) ve `GET /fapi/v1/forceOrders` yanıt alanları (`orderId`, `clientOrderId`, `autoCloseType`); `commission`, `commissionAsset="USDT"`, `realizedPnl` işaretleri |
| T-08 | Kimlik ve belirsizlik [V-5] | Açık emirle aynı kimlik: ret kodu. Dolmuş piyasa emrinin kimliğiyle ikinci emir: kabul mü ret mi (kabulse `max_attempts=1` kalıcıdır). Zaman aşımı benzetimi (istemci 1 ms okuma süresiyle) sonrası kimlikle sorgu emri buluyor; "yok" yanıtının gecikmesi ölçülür |
| T-09 | Ret kodları | min notional altı, adım dışı miktar, tick dışı fiyat, yetersiz teminat, `PERCENT_PRICE`; her biri için kod §5.1 tablosuna işlenir |
| T-10 | Piyasa emri yanıtı | `RESULT` ile `status`, `executedQty`, `avgPrice`, `cumQuote`; `FILLED` gelme süresi; `commissionRate` × `cumQuote` = `userTrades` komisyon toplamı (fark < %1) |
| T-11 | Hız başlıkları | `X-MBX-USED-WEIGHT-1M`, `X-MBX-ORDER-COUNT-10S/1M` var; uçların gerçek ağırlıkları §7 bütçesiyle karşılaştırılır |
| T-12 | Funding ve gelir | Funding anını geçen pozisyonda `income` `FUNDING_FEE` kaydı; işaret (ödenen negatif); gecikme |
| T-13 | Tam yaşam döngüsü (motor sınıfları) | giriş → ≤ 10 sn içinde stop (ölçülen süre kaydedilir; hedef < 2 sn) → iz süren stop 2 kez sıkılaşır (yeni önce) → stop tetiklenir → çıkış kaydı defterde, neden `trail_stop`, artık emir yok |
| T-14 | Kısmi dolum | Büyük piyasa emriyle kısmi dolum üretilebiliyorsa: stop miktarı = `executedQty`. Üretilemiyorsa yalnız `fake_exchange` kanıtı kabul edilir (not edilir) |
| T-15 | KILL | 2 açık pozisyon → KILL → ikisi de düz, stoplar iptal, `kill_state="flat"`; KILL kalkınca giriş açılır; duraklatma varsa açılmaz |
| T-16 | Duraklatma | `/durdur` (iki adım) → açık pozisyon yaşar, iz süren stop güncellenir, yeni sinyal `gate:paused` ile atlanır; yeniden başlatmada sürer; `/devam` yalnız `user_cmd`'yi kaldırır |

**Tatbikatlar (her biri testnette, açık pozisyonla; sonuç ve ölçülen süre kaydedilir):**

| # | Tatbikat | Geçme ölçütü |
|---|---|---|
| D-1 | **Yeniden bağlanma:** `iptables` ile borsa çıkışı 3 dakika kesilir | Emir fırtınası yok (kesinti boyunca 0 POST); `exchange_unreachable`; bağlantı gelince ≤ 30 sn'de temiz mutabakat; stop yerinde |
| D-2 | Giriş dolumundan hemen sonra `kill -9` (stop kurulmadan) | Yeniden başlatmada `protect_first` stopu kurar; çıplak süre ≤ 45 sn (ölçülür) |
| D-3 | İz süren stop ortasında `kill -9` (yeni kuruldu, eski iptal edilmedi) | Açılışta iki stop bulunur, gevşek olan iptal (L7); state tutarlı |
| D-4 | Kesinti sırasında stop tetiklenir (D-1 + fiyat) ya da motor kapalıyken elle tetiklenir | L3 çıkışı doğru neden/fiyat/komisyonla türetir; yetim emir kalmaz |
| D-5 | **Mutabakat — stop silme:** stop testnet arayüzünden elle iptal edilir | ≤ 15 sn + ağ içinde yeniden kurulur (L5); `stops_reinstalled` artar |
| D-6 | **Mutabakat — bilinmeyen pozisyon:** arayüzden elle pozisyon açılır | Motor dokunmaz; `unknown_position` tutuşu; CRIT; elle kapatılınca tutuş **kalkmaz** (CLI ile kalkar) |
| D-7 | **Mutabakat — dış azaltma ve yabancı emir:** pozisyonun yarısı elle kapatılır; ayrıca elle bir limit emir konur | L4 (miktar ve stop küçülür); L9 (yabancı emir iptal edilmez, giriş kapalı, emir kalkınca açılır) |
| D-8 | Yanlış anahtar / izinli olmayan IP ile açılış | Çıkış kodu 8, birim `failed`, CRIT; günlüklerde anahtar yok |
| D-9 | Gölge koşu: 14–27 Aralık kesintisiz `mode="testnet"` | 14 gün içinde: stopsuz pozisyon olayı 0 (`naked` > 10 sn), çözülmemiş emir 0, açıklanmamış mutabakat bulgusu 0, plansız yeniden başlatma 0; her gün fark raporu |

**Gölge koşunun sınırı:** sinyaller gerçek piyasa verisinden, emirler testnet fiyatından gelir; iki fiyat ayrışır. `mode="testnet"` iken giriş öncesi testnet mark'ı `planned_entry`'den `%0,5`'ten fazla sapıyorsa giriş `testnet_price_divergence` ile atlanır (yalnız testnet kipinde var olan kapı). Fiyat kaynağı `bookTicker` orta fiyatıdır (emir anı sorgusuyla aynı, yasak/ağırlık denetimli); okunamazsa kapı **fail-open**: giriş engellenmez, `testnet_price_unchecked` sayacı artar. Sapma `testnet_price_divergence` sayacı ve `gate:testnet_price_divergence` karar satırıyla görünür. Gölge koşu **tesisatı** sınar (yaşam döngüsü, mutabakat, yeniden başlatma); kâr/zarar, kayma ve dolum kalitesi hakkında kanıt **değildir**. Ayrı `var_dir` (`var-testnet`) ve ayrı defter kullanır; raporlara girmez.

## 12. Gerçek hesap duman testi — 28–29 Aralık (`scripts/smoke_live.py`)

Ön koşullar: §11'de açık KALDI yok; D-9 ölçütleri tutuyor; RK-1 asgari kısmı ve duraklatma canlı dalda; canlı anahtar sunucuda, izin denetimi (§3.4 adım 2) **GEÇTİ**; alt hesapta ≥ 30 USDT; kağıt botları çalışmaya devam eder (duman testi ayrı `var-smoke/` dizini ve ayrı state kullanır, defteri raporlara girmez). Betik her adımda durur, ne yapacağını yazar ve `evet` yanıtı bekler; her adımın borsa yanıtı `var-smoke/log/` altına kaydedilir. Kâr-zarar testi değildir; beklenen toplam maliyet < 0,10 USD.

| Adım | İşlem | Geçme ölçütü |
|---|---|---|
| S-0 | Açılış denetimi (§3.4) | Para çekme kapalı, IP kısıtlı, one-way, tek varlık; cüzdan ≤ `expected_wallet_max` |
| S-1 | Kurallar ve en küçük tutar | İki çift seçilir (min notional'ı en düşük olanlar; öneri XRP/USDT long, DOGE/USDT short); miktar = `ceil(min_notional × 1,2 / mark)` adıma yuvarlı |
| S-2 | Hazırlık | Her iki sembol: izole, kaldıraç `cfg.leverage`; `positionRisk` doğrular |
| S-3 | **Long** piyasa girişi (A çifti) | `FILLED`; `executedQty` beklenen; teminat = nominal / kaldıraç (±%2); izole |
| S-4 | Stop (mark'ın %1 altı) | Dolumdan stop kabulüne süre ≤ 10 sn (ölçülür); borsada görünür; `workingType=MARK_PRICE`, `reduceOnly=true`, miktar = pozisyon |
| S-5 | **Short** piyasa girişi (B çifti) + stop (mark'ın %1 üstü) | S-3/S-4 ölçütleri |
| S-6 | A'da stopu sıkılaştır (mark'ın %0,5 altı) | Yeni stop kabulünden **sonra** eski iptal; arada her an ≥ 1 stop (betik iki açık emir listesi anlık görüntüsüyle kanıtlar) |
| S-7 | Motoru öldür, yeniden başlat (`kill -9`) | `protect_first` + mutabakat: bulgu yok, eylem yok; pozisyon ve stoplar aynen |
| S-8 | A'da stopu mark'ın %0,15 altına sıkılaştır, tetiklenmesini bekle (en çok 30 dk; olmazsa %0,05) | Borsa stopu **kendisi** tetikler; motor ≤ 10 sn'de düz görür; çıkış kaydı: neden `trail_stop`, fiyat ve komisyon `userTrades` ile aynı |
| S-9 | B'de hedef emri kur, borsada gör, iptal et | `TAKE_PROFIT_MARKET` kabul ve iptal (arayüz eşliği; motor kullanmıyor) |
| S-10 | Duraklatma | `/durdur` → B pozisyonu ve stopu yerinde; `/devam` → kalkar |
| S-11 | KILL | `/hepsini_kapat` → B reduceOnly piyasa ile kapanır, stop iptal, `kill_state="flat"`; sonra `/devam` |
| S-12 | Kayıt denetimi | İki işlem defterde giriş+çıkış; komisyonlar `userTrades` toplamına eşit (±0,0001 USDT); funding satırı tutarlı; açık emir 0, pozisyon 0 |
| S-13 | Hesap denetimi | Cüzdan değişimi = Σ gerçekleşen − Σ komisyon − Σ funding (±0,01 USDT) |
| S-14 | Sonuç | `11-duman-testi-sonuc.md`; mentor onayı → canlı kararı. Herhangi bir adım KALDI ise canlı **başlamaz**; düzeltme + adımın tekrarı |

Her adım için geri dönüş: betik her duraklamada "şimdi her şeyi kapat" seçeneği sunar (reduceOnly piyasa + tüm bizim emirlerimizin iptali). **Kullanıcı için elle yol:** motor ya da sunucu yanıt vermiyorsa Binance uygulaması → alt hesap → Vadeli → Pozisyonlar → "Tümünü kapat"; sonra sunucuda KILL kurulur ki motor geri gelince yeniden açmasın.

**Canlıya geçişte risk kademe operatör adımları (12 §14; geçiş listesine eklenir; hepsi sunucuda, `--by <ad>` zorunlu):** (1) `python -m trader_engine capital init --bot learner --env live --by <ad> --amount <alt hesaptaki tutar>` (250–300 USD; duman testinden sonra, motor açılmadan önce; günlük `var/<canlı var_dir>/learner/risk_ladder.jsonl`); (2) `deploy/trader-telegram.env`'de `LADDER_BOTS=learner` ve `engine.twin.json` ile canlıyla birlikte çalışan kağıt botuna `ladder_follow` = canlı günlüğün yolu (O-2 `var_dir` kararına bağlı; ikiz canlının basamağını izler, durmasından etkilenmez); (3) motor açıldıktan sonra Telegram `/kademe` çıktısının kontrolü: basamak K0, durma seviyesi 0,80 × yatırılan, son taban 0,60 × yatırılan, kapı kodu boş; ayrıca `ladder status`; (4) 3–4 hafta ya da 40–50 işlem sonra 1000 USD'ye tamamlanırken önce `capital deposit --amount <tutar>` (ya da önce aktarım; arada giriş `capital_mismatch` ile kapalı kalır, sahte durma üretilmez); kaydedilen tutar borsa aktarımıyla eşleşene kadar ([V-8], `income?incomeType=TRANSFER`) giriş kapalıdır. Testnet tatbikatları D-1…D-3 (12 §12) canlıdan önce `11-testnet-sonuc.md`'ye yazılır; D-4 ilk gerçek yatırmada.

**DD-7 geçiş listesi:** ban dosyası (`var/ban.<host>.json`) motor/feed/OI toplayıcıda aynı dizinde olmalı (`market_db` dizini; sağlık `HEALTH_BAN_DIR` ya da `MARKET_DB` dizinini yoklar); canlı kipte kullanılan ağırlık `weight_soft` (1200) ve üstündeyken yeni giriş `weight_high` ile reddedilir (çıkış/stop/iptal etkilenmez; testnette atlanır); yasak sırasında elle kapatma yolu §10 sonunda.

**DD-8 geçiş listesi:** `engine.live.json`da `var_dir` son bileşeni `var` olamaz, `kill_file`/`pause_file` `shared/live/…` altında olmalı; canlı birimde `RestartPreventExitStatus=2 7 8`; ilk açılışta damga yazılır (temiz `var-live/learner`); tavan tutuşu (`wallet_above_expected`) ve izin denetimi (beyan yok) yukarıdaki gibi çalışır.

**Canlıya geçiş (duman testinden sonra, 30 Aralık – 2 Ocak) — DD-9 ile yeniden yazıldı:** canlıya geçiş `engine.learner.json` değiştirilerek DEĞİL, `run --bot learner --env live` ile `config/engine.live.json` katmanı üzerinden yapılır (`mode="live"`, `var_dir="var-live"`, `kill_file="shared/live/KILL"`, `pause_file="shared/live/PAUSE"`, `live.account_tag="canli-alt1"`, `expected_wallet_max=2000` (23.11 kullanıcı kararı; önce 1500)); `engine.learner.json` kâğıt kalır. `kill_file`/`pause_file` **canlı** yollardır (önceki "varsayılan kalır" cümlesi DD-8 ile çelişiyordu, geçersizdir). Telegram ve sağlık yollarını `install.sh --live` yazar (`/etc/trader-telegram.env`, `/etc/trader-health.env`, `/etc/trader-lesson.env`; `LIVE_BOTS`, `LIVE_VAR_DIR`, `LIVE_PAUSE_FILE`, `KILL_FILE`, `ENGINE_STATUS_PATH`, `LEDGER_PATH`, `LADDER_BOTS`); yollar `config/engine.live.json` ile tutarsızsa Telegram daemon'u açılmaz ve sağlık `live_paths_mismatch` CRIT verir. Canlıdan sonra Telegram `/hepsini_kapat` ve `/devam` yalnız canlı botu etkiler (kâğıt ikizin `shared/KILL`ine dokunmaz); `/durdur` her iki bota kendi dosyasından uygulanır. Sıra, `docs/dd9-canli-paket-spec.md` §10 "Canlıya geçiş günü" listesidir: (1) kâğıt learner KILL ile düzlenir, `systemctl disable --now trader-engine@learner trader-engine-retry@learner.timer`; (2) kullanıcı `nano /etc/trader-live.env` ile üç alanı yazar; (3) `COMMIT=<etiketli sha> bash /usr/local/lib/trader-root/current/deploy/install.sh --live`; (4) `capital init` (12 §14); (5) `canli_duman.sh` ile duman testi (ayrı gün); (6) `pause --bot learner --env live --reason manual --by <ad>` ile ilk açılış tutuşu; (7) `systemctl start trader-engine-live`; (8) mutabakat temizse tutuş kaldırılır.

## 13. İş paketleri

Her paket: gerçekleme ajanı (Sonnet) + **bağımsız** test ajanı (şartnameden yazar; 00-index §8) + mentor incelemesi. Tahminler gerçekleme günüdür; test yazımı paraleldir. Sıra bağlayıcıdır; aynı satırdaki paketler paralel yürür.

| WP | İçerik | Dosyalar | Asgari testler (başlıklar) | Mentor | Gün |
|---|---|---|---|---|---|
| **B1** | İmzalı istemci | `exchange/binance_rest.py` | İmza örneği (§16.1); sayı biçimleme (üstel yok); `-1021` eşitle+tek tekrar; **emir POST'u ağ hatasında/5xx'te tekrar edilmez** (r1); okuma tekrar eder; 429 sessizliği; 418/451/403/401 sınıfları; ağırlık eşikleri ve `protective` önceliği; emir tavanı; **gizli değer sızma testi**; saat enjeksiyonu (gerçek saat okunmaz) | **Evet** (tekrar politikası satır satır) | 2 |
| **B2** | Yapılandırma, kipler, açılış denetimi kabuğu, envanter | `config.py`, `cli.py`, `test_engine_module_inventory.py`, `config/engine.testnet.json` | `testnet/live` kabulü; `live` bloğu zorunluluğu; `LIVE_CONFIRM` eşleşmezse ret; `leverage` kilit aralığı; `live` + `twin` reddi; `keys_missing`; çıkış kodu 8; kağıt yapılandırması değişmeden yüklenir | Evet | 1 |
| **B6** | Duraklatma (B1/B2 ile **paralel**, kağıt başlar başlamaz sunucuya) | `pause.py`, `gates.py`, `status.py`, `cli.py`, `trader_core/telegram.py`, `scripts/telegram_run.py` | Dosya var = etkin; bozuk dosya etkin; `add` idempotent ve ilk kökeni korur; iki tutuş bağımsız; yeniden başlatmada sürer; **motor kodunda `remove` yok** (AST); kapı sırası ve kodları; KILL etkileşim tablosu (§9.3) altı satır; `/durdur` iki adım + TTL sınırı (119/120/121 sn); `/devam` tek katman, köken kuralı, `drawdown_review` reddi; eşzamanlı yazma (iki süreç) kayıpsız; denetim günlüğü | **Evet** | 1,5 |
| **B0** | Testnet yoklaması (anahtar gelince; T-01…T-12) | `scripts/smoke_testnet.py` (`b0-*` adımları), `fixtures/binance/testnet/` | — (çıktı: `11-testnet-sonuc.md` ilk yarısı; [V-n] kararları) | **Evet** (sonuçlar şartnameyi revize edebilir) | 1 |
| **B3** | `LiveBroker` + sahte borsa | `brokers/binance_futures.py`, `tests/engine/fake_exchange.py` | Eşlik tablosu §5.1 satır satır; ret adı eşlemesi; `RESULT` durum tablosu §5.3 beş satır; `workingType` uyuşmazlığında iptal; `closing_events`: VWAP, komisyon toplamı, neden seçimi (stop/çıkış/likidasyon/yabancı), eksik işlemde boş dönüş, çift teslim yok; funding sırası; kurallar yenileme ve 6 saat bayatlık; `prepare` ağsız; hesap önbelleği | **Evet** | 3 |
| **B4** | Motor canlı yolu | `engine.py`, `order_manager.py` | **Kağıt/backtest bit-bit aynı** (mevcut tüm testler değişmeden yeşil + kilitli dönem öncesi bir referans backtest'in `summary.json` ve `trades.csv` özeti öncesi/sonrası eşit); canlıda dış tx yok ve POST tx dışında (çit testi); giriş→stop aynı çağrıda; stop süre sınırı (9/10/11 sn sınır değerleri); risk ihlalinde önce stop; belirsiz giriş penceresi; çökme noktaları: POST öncesi, POST sonrası, dolum sonrası-stop öncesi, iz süren stop ortası (r1, r2, r4/r5, r7, r9); KILL `live_tick`'te beslemesiz çalışır (r3); yalnız son karar barı; çift dolum yok sayılır | **Evet** (satır satır) | 3 |
| **B5** | Canlı mutabakat | `reconcile_live.py` | L1–L11 her satır için bir senaryo; L2 istisnası yalnız KILL ile; L2a geç dolum; toleranslar sınır değerleriyle; okuma başarısızken **eylem yok**; `protect_first` piyasa verisi istemez; duraklatma tutuşları kaldırılmaz; r8 | **Evet** | 2 |
| **B7** | Testnet motor denetimleri ve tatbikatlar (T-13…T-16, D-1…D-8) | `scripts/smoke_testnet.py` | — (çıktı: `11-testnet-sonuc.md` tamamı) | **Evet** | 2 |
| **B8** | Gölge servis, sağlık alarmları, kurulum | `deploy/trader-engine-testnet.service`, `deploy/install.sh`, `deploy/live.conf.example`, sağlık denetçisi ekleri (`naked`, `exchange.reachable`, tutuş kaybı, yasak) | Birim dosyası çözülür; ortam dosyası izinleri `0600`; alarm eşikleri | Hayır (denetim listesiyle) | 1 + 14 gün koşu |
| **B9** | Duman testi betiği ve geçiş listesi | `scripts/smoke_live.py`, `11-duman-testi-sonuc.md` şablonu | Betik `fake_exchange` üzerinde uçtan uca; her adımda onaysız ilerlemez; "şimdi kapat" yolu | **Evet** (+ 28–29 Aralık'ta canlı izleme) | 1 |
| RK-1 (asgari) | −%20 denetimi, tepe değer, iniş; B6'ya bağlı | ayrı şartname `12-risk-kademe.md` (uygulandı: `trader_core/risk_ladder.py`, `trader_engine/ladder.py`; 12 ile güncellendi) | — | Evet | (ayrı) |

Takvim: **30 Kas – 6 Ara** B1, B2, B6 (paralel); B0 anahtar gelir gelmez (4–5 Ara). **7 – 13 Ara** B3 → B4 ∥ B5 → B7. **14 – 27 Ara** B8 (D-9 gölge koşu) + bulgu düzeltmeleri; B9 hazırlığı 21–27 Ara. **28 – 29 Ara** duman testi. Toplam ≈ 17 gerçekleme günü + ≈ 5 mentor inceleme günü; pay yok denecek kadar azdır — B0 4 Aralık'ı kaçırırsa B3'ün koşullu emir kısmı ve tüm sonrası aynı gün kadar kayar, canlı da (en geç 2–5 Ocak sınırı içinde kalmak üzere).

## 14. Kullanıcıdan gerekenler

| Ne | Ne zaman | Not |
|---|---|---|
| Binance **vadeli testnet** API anahtarı + gizli anahtar | **En geç 4 Aralık** | Güvenli form üzerinden; sohbete, depoya, Telegram'a yazılmaz. Testnet hesabında sahte USDT olmalı |
| Sunucudan erişim denetimi | 4 Aralık'a kadar | Testnet ve `fapi.binance.com` + `api.binance.com` 200 dönmeli (451/403 ise sunucu bölgesi kararı) |
| Binance **alt hesap** + vadeli izni + canlı API anahtarı | Kağıdın 2. haftası (7–13 Aralık) | Anahtarda: okuma + vadeli **açık**; para çekme, iç transfer, evrensel transfer **kapalı**; **yalnız sunucu IP'si**; alt hesapta BNB ile komisyon ödeme kapalı / BNB yok. Güvenli form üzerinden |
| Alt hesabın adı (`account_tag`) ve beklenen azami bakiye | Anahtarla birlikte | `LIVE_CONFIRM` ve yanlış hesap koruması için |
| Duman testi için ≥ 30 USDT | 27 Aralık | 1000 USD duman testi geçtikten sonra yatırılır |
| 28–29 Aralık'ta ~2 saat hazır bulunma | 28–29 Aralık | Telegram adımları (S-10, S-11) ve her adımın onayı |
| Kararlar | 20 Aralık'a kadar | `risk-kademe-kurali.md` §10 madde 1–3 (RK-1 için); açık nokta O-2 (canlı defter dizini) |

## 15. Ertelenenler (canlı v1'de **yok**; her biri ayrı karar + şartname revizyonu ister)

Kullanıcı veri akışı / listenKey / WebSocket; limit giriş ve bekleyen giriş emirleri; borsada kâr al emri (motor kullanımı); giriş öncesi stop ("ön stop"); dolum sonrası riskte kapatmak yerine küçültme (r6); stop için emir değiştirme (amend) ucu ve toplu emir; hedge kipi, çapraz teminat, çoklu varlık kipi; BNB ile komisyon; pozisyon açıkken dönemsel funding kaydı (v1'de yalnız kapanışta toplanır); otomatik cüzdan sapma denetimi; `rest_public` ile ortak taban sınıf; `max_attempts=2` (yeniden gönderim); çift başına birden çok pozisyon; ikizin canlıya alınması; haftalık otomatik testnet duman testi (elle koşulur); emir defteri/kayma tahmini.

## 16. Elle doğrulanabilir örnekler

1. **İmza.** Gizli anahtar `ornek-gizli-anahtar`; sorgu `symbol=XRPUSDT&side=BUY&type=MARKET&quantity=10&newClientOrderId=trLe-df350276c5ff969f6d18cd15&newOrderRespType=RESULT&recvWindow=5000&timestamp=1798449600000` ⇒ `signature=b4ecba7924301b8e54b162bcfd1acfb2c42f5b30d0b083b2bab9ce3af8a737e9`.
2. **Kimlikler.** `make_client_id("learner", rol, "XRP/USDT", "long", 2026-12-28T09:00:00Z, sıra)`: giriş/0 `trLe-df350276c5ff969f6d18cd15`; stop/0 `trLs-f506d5650826460114e3bf1b`; stop/1 `trLs-088cb2337fb73d7c364e491d`; çıkış/0 `trLx-6652e315ab5690ac110b9e70` (29 karakter ≤ 36). KILL altında bilinmeyen pozisyon kapatma: `sha1("learner|kill|XRPUSDT|2026-12-28T09:05:00Z")[:24] = 362ae964d08b3d0f1b93fcf7` ⇒ `trLx-362ae964d08b3d0f1b93fcf7`.
3. **Stop yuvarlama.** Long, `initial_stop=2.03457`, `tick=0.0001` ⇒ `round_stop_tight` yukarı ⇒ `2.0346`, gönderilen dizge `"2.0346"`. Short, `2.03457` ⇒ `2.0345`.
4. **Çıkış VWAP.** Giriş 10 @ 2,0500. Azaltan işlemler: 4 @ 2,0300 (komisyon 0,00406), 6 @ 2,0280 (0,006084) ⇒ `qty=10`, `price=(4×2,0300+6×2,0280)/10=2,0288`, `fee=0,010144`; sıfırlayan işlem bizim stopumuzun emri ⇒ `reason="stop"`.
5. **Stop süre sınırı.** `t_fill=0`. (a) Stop/0 0,4 sn'de kesin retle döner (`filter:-1111`) ⇒ `0,4 ≤ 10 − 5` ⇒ stop/1 denenir; o da 3,6 sn'de zaman aşımı, sorgular 3,8 ve 5,8 sn'de "yok" ⇒ 5,8 sn'de reduceOnly piyasa çıkışı + `stop_failed`. (b) Stop/0 POST'u 3,0 sn'de zaman aşımı; sorgular 3,2 ve 5,2 sn'de "yok" ⇒ `5,2 > 5` ⇒ ikinci deneme **atlanır**, 5,2 sn'de doğrudan çıkış.
6. **Duraklatma katmanları.** 10:00 `/durdur` (onaylı) ⇒ `holds=[user_cmd]`. 14:00 RK-1 ⇒ `holds=[user_cmd, drawdown_review]`, kapı kodu `drawdown_review`. 15:00 `/devam` (onaylı) ⇒ `holds=[drawdown_review]`; yanıt "learner: drawdown_review — girişler hâlâ kapalı". Motor yeniden başlar ⇒ aynı. Özsermaye toparlanır ⇒ aynı.
7. **Ağırlık.** Yanıt başlığı `X-MBX-USED-WEIGHT-1M: 1250` ⇒ düz mutabakat taraması ertelenir; stop kurma (`protective=True`) gider. `1850` ⇒ yalnız koruyucu istekler.

## 17. Açık noktalar

- **O-1 (testnet, mentor):** [V-1]…[V-7]; özellikle T-04 "iki stop" çürürse §6.6 yeniden yazılır ve takvim en az 2 gün kayar.
- **O-2 (kullanıcı/mentor):** canlıya geçişte defter ve state. Öneri: canlı için yeni `var_dir` (temiz `state.sqlite` ve yeni defter); kağıt defteri salt okunur saklanır ve ders servisine yalnız geçmiş kanıt olarak bağlanır (risk kademe kuralı zaten kağıt işlemlerini saymıyor). Alternatif (aynı defterde kip sütunu) `defter-spec` değişikliği ister.
- **O-3 (mentor):** gölge koşunun belleği. 2 GB sunucuda üçüncü motor süreci ≈ 300 MB ister; yetmezse gölge koşu yalnız tatbikat günlerinde çalıştırılır ve D-9 ölçütü "toplam ≥ 7 gün" olarak yeniden yazılır (mentor kararı).
- **O-4 (mentor):** motorun anlık Telegram uyarısı. Bu şartname alarmları `status.json` + sağlık denetçisi üzerinden verir; `naked` alarmı için denetçi aralığı ≤ 60 sn olmalıdır (WP-B8'de ölçülür; değilse motorun bildirim kuyruğuna doğrudan yazması ayrı karar).
- **O-5 (bilgi):** `telegram-spec.md` karar 1 ve §5 `/durdur` satırı, `05` §4.1 kapı sırası, `05` §7 (canlı tablo artık burada), `05` §8.2 (`status.json` ekleri) ve `00-index.md` birim tablosu bu belgeye göre güncellenmelidir; bu belge onları değiştirmedi.
