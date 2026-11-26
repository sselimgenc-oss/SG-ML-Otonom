# Sağlık izleme, dış nabız, günlük yedek ve yeniden başlatma kurtarma — arayüz ve kurallar (spesifikasyon v1, 16 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. Veto tazeliği alarmı ve ikiz sağlık kontrolleri kaldırıldı (veto/ikiz yok).

Bu belge kod ve test içermez; testler bu belgeden yazılır. Biçim `risk-kilidi-spec.md` ile aynıdır. Defter arayüzleri `defter-spec.md`'den (Bölüm 4, 7.2, 8) alınmıştır; çelişkide o belge geçerlidir.

Modül: `src/trader_core/health.py` (yalnızca standart kütüphane; `pandas`, `numpy`, `freqtrade`, `docker` SDK import edilmez; saf: dosya, ağ, saat, süreç okumaz). Ölçümleri toplayan kod modülde değil, `scripts/health_run.py` içindedir. Her belirsizlikte **fail-closed**: sağlık belirlenemiyorsa sağlıklı sayılmaz, nabız gönderilmez, uyarı gider; sağlık modülü hiçbir koşulda işlem açmaz, bot başlatmaz, defter satırı yazmaz.

## 0. Kaynaklar ve neyin yeniden kullanıldığı (yalnızca okundu; hiçbiri çalıştırılmadı, içe aktarılmadı)

| Kaynak (kullanıcının projesi) | Alınan fikir | Bizde |
|---|---|---|
| CT `copytrade/saglik.py` | Saf kontrol: girdi anlık görüntü, çıktı `Bulgu(seviye, kod, mesaj)` listesi; eşikler bilinçli sabit; **okunamayan girdi sahte alarm üretmez** (CT) | Aynı saf biçim. Ters yön: bizde okunamayan girdi `UNKNOWN` olur ve nabzı keser (fail-closed); sahte alarm gürültüsü tekrar bastırma ile (Bölüm 5) azaltılır |
| CT `.github/nabiz/worker.js` | Dış ölü adam alarmı: nabız yaşı eşiği, ilk tikte alarm, sonra N dakikada bir tekrar, "veri okunamadı" ayrı durum, saf `karar()` | Cloudflare **kullanılmaz** (hesap kapalı, CT K-20). Aynı karar mantığı dış servise bırakılır (Bölüm 4) |
| CT `deploy/*.service`, `alarm.sh` | `Type=oneshot` + timer, `ProtectSystem=strict`, `OnFailure=` alarm birimi, çıkış kodu semantiği (kalıcı neden = yeniden başlatma yok), alarm betiği token'ı komut satırına koymaz, yoksa "atlandı" ile 0 çıkar | Bölüm 8 |
| CT `ortam_dosyasi.py` | systemd `EnvironmentFile` tuzakları (satır sonu `# not` değere karışır; tırnak yok); sır değeri asla basılmaz | Bölüm 8.3 ortam dosyası kuralları |
| CT `niyet.py` | Emirden önce niyet, fsync'li ekleme | Bizde defterin `decision_events` + spool'u aynı işi görür; sağlık yalnız okur |
| 1L3A `motor/canli/durum.py` | Atomik yazma: aynı dizinde geçici dosya + `fsync` + `os.replace` | Sağlık durum dosyası ve yedek bildirimi (Bölüm 5.3, 6) |
| 1L3A `kalp_atisi.py` | Bot canlıyken düzenli zaman damgası; yeniden başlatmada "son kalp atışı → başlangıç" kesintisi ölçülür; bozuk dosya sessiz geçilmez | Bizde bot kalp atışı = defterin `health_probes.probed_at` (yeni sütun/dosya gerekmez); kesinti süresi raporda |
| 1L3A `deploy/1l3a-bildirim@.service` | `OnFailure=...@%n.service` şablon birimi: başarısız birim adı alarm metnine girer | `trader-health-fail@.service` (Bölüm 8) |

## 1. Kapsam ve dosya sahipliği

Bu belgenin iş paketi yalnızca şunlara dokunur: `src/trader_core/health.py`, `scripts/health_*.{py,sh}`, `deploy/` (yeni dizin), `tests/test_health_*.py`. `TraderV1`, `ledger.py`, `docker-compose.yml`, `config/*.json` **değiştirilmez**; gerekli değişiklikler Bölüm 11'de bir sonraki adım için listelenir. Telegram gönderimi madde 18'dedir; burada yalnız `Notifier` arayüzü tanımlanır.

Çalışma ortamı: paylaşımlı DigitalOcean droplet, 1 vCPU / 2 GB RAM, başka proje de çalışıyor. Sağlık işlemleri kısa ömürlü süreçlerdir (daemon yok): tepe bellek hedefi ≤ 40 MiB, tek çalışma ≤ 5 sn CPU (yedek hariç).

## 2. Veri yapıları (`health.py`)

```
class Status(str, Enum): OK, WARN, CRIT, UNKNOWN, SKIPPED
@dataclass(frozen=True) class CheckResult:
    name: str            # Bölüm 3'teki ad
    status: Status
    code: str            # kısa, makine okur: "ok", "stale_candle", "api_unreachable", ...
    detail: str          # sade Türkçe tek cümle; sır ve yol dışında değer içermez
    value: float | None  # ölçülen (sn, bayt, oran, adet), yoksa None
    threshold: float | None
@dataclass(frozen=True) class HealthReport:
    generated_at: datetime        # UTC, tz-aware
    results: tuple[CheckResult, ...]
    overall: Status               # OK | WARN | CRIT | UNKNOWN (SKIPPED asla overall olmaz)
    healthy: bool                 # overall in (OK, WARN)
    def failing(self) -> tuple[CheckResult, ...]   # status in (WARN, CRIT, UNKNOWN)
```

**Birleştirme kuralı (`overall`):** `SKIPPED` yok sayılır. Kalan sonuçlarda sırayla: herhangi biri `CRIT` → `CRIT`; yoksa herhangi biri `UNKNOWN` → `UNKNOWN`; yoksa herhangi biri `WARN` → `WARN`; yoksa `OK`. Kalan sonuç **yoksa** (hepsi `SKIPPED` ya da boş) → `UNKNOWN`. **Zorunlu kontroller** (Bölüm 3'te "Z" işaretli) `results` içinde bulunmuyorsa her biri için `UNKNOWN` (`code="missing_check"`) eklenir. `healthy = overall in (OK, WARN)`; yani nabız yalnız `OK`/`WARN` iken gider, `CRIT` ve `UNKNOWN` iken gitmez.

### 2.1 Anlık görüntü (`HealthSnapshot`, frozen dataclass; ölçülemeyen alan `None`)

Runner ölçüp doldurur; `health.py` yalnız değerlendirir. `None` = "ölçülemedi" (istisna, zaman aşımı, ayrıştırma hatası) ve ilgili kontrol `UNKNOWN` olur. Alanlar:

| Alan | Tür | Anlam |
|---|---|---|
| `now` | `datetime` (UTC) | Runner'ın saati; tz-aware değilse `ValueError` |
| `timeframe_s` | `int \| None` | `show_config.timeframe` saniyeye çevrilmiş (bugün `1h` → 3600) |
| `api` | `dict[str, ApiProbe]` | Anahtar: bot (`learner`, `twin`). `ApiProbe(ping_ok: bool\|None, last_process_at: datetime\|None, last_candle_open: datetime\|None, open_trade_ids: tuple[int,...]\|None, dry_run: bool\|None)` |
| `ledger` | `dict[str, LedgerProbe]` | `LedgerProbe(last_write_at: datetime\|None, spool_lines: int\|None, unledgered_ids: tuple[int,...]\|None, orphan_ids: tuple[int,...]\|None, schema_ok: bool\|None, has_active_params: bool\|None, spool_corrupt_lines: int\|None = None)` |
| `disk_free_bytes`, `disk_total_bytes` | `int \| None` | Ledger/yedek dizinlerini barındıran dosya sistemi (`os.statvfs`; en küçük boş alanlı olan) |
| `mem_available_bytes`, `swap_total_bytes`, `swap_used_bytes` | `int \| None` | `/proc/meminfo` (`MemAvailable`, `SwapTotal`, `SwapTotal-SwapFree`) |
| `containers` | `dict[str, ContainerProbe]` | `ContainerProbe(state: str\|None, restart_count: int\|None, started_at: datetime\|None, oom_killed: bool\|None)`; `docker inspect` |
| `prev_restart_counts` | `dict[str, int]` | Önceki çalışmanın sayaçları (durum dosyası, Bölüm 5.3); ilk çalışmada boş |
| `veto_file_mtime` | `datetime \| None` | **Yer tutucu**; yapılandırmada kapalıysa kullanılmaz |
| `budget_state` | `str \| None` | **Yer tutucu**: `"ok" \| "warn" \| "exhausted"` |
| `last_backup_at` | `datetime \| None` | En son **doğrulanmış** yedek zamanı (Bölüm 6.6 manifest) |

### 2.2 `HealthConfig` (frozen dataclass; geçersiz değer → `ValueError`)

Eşikler bilinçli sabit varsayılandır (CT ilkesi); `warn < crit` değilse (süre/oran yönüne göre) veya sayı sonlu/pozitif değilse `ValueError`. Hepsi Bölüm 3 tablosundadır. Ek: `warmup_s=600` (Bölüm 3.3), `require_bots=("learner","twin")`, `veto_max_age_s: int|None=None` (None = yer tutucu kapalı), `budget_check_enabled=False`.

## 3. Kontroller (`health.evaluate(snap, cfg=DEFAULT_CFG) -> HealthReport`)

`evaluate` saf ve belirleyicidir; istisna sızdırmaz: bir kontrolün hesabı beklenmedik istisna verirse o kontrol `UNKNOWN`, `code="internal_error"`. Bot bazlı kontroller her bot için ayrı sonuç üretir (`name` = `"api_reachable:learner"` vb.).

| # | `name` | Z | Girdi | OK | WARN | CRIT | `None` |
|---|---|---|---|---|---|---|---|
| 1 | `api_reachable` | Z | `api[bot].ping_ok` | `True` | — | `False` (`api_unreachable`) | UNKNOWN |
| 2 | `bot_loop_age` | Z | `now - api[bot].last_process_at` (freqtrade `/api/v1/health` `last_process`) | ≤ 120 sn | > 120 sn | > 300 sn | UNKNOWN |
| 3 | `candle_age` | Z | `now - last_candle_open`, `timeframe_s=T` | ≤ 2T+120 | > 2T+120 | > 3T+120 (`stale_candle`) | UNKNOWN |
| 4 | `ledger_write_age` | Z | `now - ledger[bot].last_write_at` (en yeni `recorded_at`/`probed_at`; Bölüm 3.1) | ≤ T+300 | > T+300 | > 2T+300 | UNKNOWN |
| 5 | `ledger_gate` | Z | `LedgerProbe` alanları (Bölüm 3.2) | kapı açık olurdu | `orphan_ids` boş değil | kapı kapalı olurdu | UNKNOWN |
| 6 | `disk_free` | Z | `disk_free_bytes` | ≥ 3 GiB | < 3 GiB | < 1 GiB (`disk_low`) | UNKNOWN |
| 7 | `memory` | Z | `mem_available_bytes` | ≥ 250 MiB | < 250 MiB | < 120 MiB | UNKNOWN |
| 8 | `swap` | — | `swap_used/swap_total` | ≤ 0,50 | > 0,50 | > 0,80; `swap_total=0` ise `SKIPPED` | UNKNOWN |
| 9 | `container_restarts` | Z | `restart_count - prev_restart_counts[c]`, `state`, `oom_killed` | delta 0 ve `running` | delta ≥ 1 | delta ≥ 3, `state != running` ya da `oom_killed` | UNKNOWN |
| 10 | `backup_age` | — | `now - last_backup_at` | ≤ 26 sa | > 26 sa | > 50 sa | UNKNOWN (ilk kurulum günü: Bölüm 6.7) |
| 11 | `veto_file_age` | — | `veto_file_mtime` | — | — | — | `veto_max_age_s is None` → `SKIPPED` (`placeholder`); verilirse yaş ≤ süre OK, > süre WARN, > 3×süre CRIT; dosya yoksa/okunamıyorsa UNKNOWN |
| 12 | `budget_status` | — | `budget_state` | `"ok"` | `"warn"` | `"exhausted"` | `budget_check_enabled=False` → `SKIPPED`; açıkken `None` UNKNOWN; bilinmeyen metin UNKNOWN |

Yaşlar negatifse (saat geri gitti): 0 sayılmaz; ölçüm güvenilmez → `UNKNOWN`, `code="clock_skew"`. Gelecek tarihli `now`'dan 5 sn'den fazla ileri damga aynı kuralla `UNKNOWN`.

Her sınırda eşitlik **iyi tarafa** düşer ("≤ eşik" OK; "> eşik" WARN), tabloda böyle yazılmıştır. Bellek/disk için "≥ eşik" OK, "< eşik" bozuk.

### 3.1 `ledger_write_age` ne ölçer

Runner, defteri `open_ledger(path, bot, create=False, read_only=True)` ile açar ve şu dört tablodaki en yeni zamanı alır: `health_probes.probed_at`, `decision_events.recorded_at`, `trade_entries.recorded_at`, `trade_exits.recorded_at` (`last_write_at = max`). Bot her mum kapanışında `entries_allowed()` çağırdığından `health_probes` doğal bir "bot defteri yazabiliyor" nabzıdır (kalp atışı fikri, 1L3A). Hiç satır yoksa (taze defter, yalnız `meta`) `last_write_at = meta` oluşturma zamanı sayılır; o da yoksa `None`. Bot bilerek durdurulmuşsa (`initial_state` ≠ running) bu kontrol UNKNOWN verir ve nabız kesilir; bu **istenen** davranıştır (durdurulmuş bot "sağlıklı" değildir; bakım için `HEALTH_MAINTENANCE` dosyası, Bölüm 9, yalnız uyarıyı bastırır, nabzı değil).

### 3.1a `exchange_ban` (DD-7)

`HealthSnapshot.bans: tuple[BanProbe, ...] | None = None` (`BanProbe(host, until, http, source, corrupt=False)`; `None` = yoklanmadı, denetim üretilmez). `scripts/health_run.py:probe_bans(ban_dir)` dizindeki her `ban.*.json` için bir satır üretir (süresi dolmuş olanlar dahil; geçersiz/okunamayan dosya → `corrupt=True, until=None`; dizin yok → `()`; `.lock`/geçici dosyalar satır üretmez). Dizin: `HEALTH_BAN_DIR`, yoksa `MARKET_DB`nin dizini, yoksa `ENGINE_VAR_DIR` (yoklama asla atlanmaz; dizin yoksa `()` = OK). Tek satırlık bot-bağımsız denetim `exchange_ban` (açık pozisyon = `has_exchange` yoklamasında `open_trade_ids` boş değil ya da `None`): `until > now` ve açık pozisyon → CRIT `exchange_ban_open_positions` (değer = en uzun kalan sn); `until > now` → WARN `exchange_ban`; yalnız `corrupt` → WARN `exchange_ban_file_corrupt`; aksi OK. İlk iki kod anında uyarır (`IMMEDIATE_CODES` / `IMMEDIATE_WARN_CODES`). CRIT metni: "Borsa geçici engel koydu, açık pozisyon var"; düzelme: "Borsa engeli kalktı". Elle yol: `docs/motor/11-canli-broker.md` §10 "Yasak sırasında elle kapatma".

### 3.1b `spool_corrupt:<bot>` (DD-8 E4)

`LedgerProbe.spool_corrupt_lines` (`scripts/health_run.py:probe_ledger`: dosya yok → 0, okunur → satır sayısı, `FileNotFoundError` dışı `OSError` → `None`). `ledger_gate`i yapılan her bot için **ayrı** denetim: `> 0` → CRIT `spool_corrupt` (değer = satır sayısı; anında uyarı, `IMMEDIATE_CODES`), `0` → OK, `None` → UNKNOWN `spool_corrupt_unreadable`. `ledger_gate`in erken dönüşleri (ör. `spool_pending`) bu denetimi maskelemez; ısınma yumuşatmaz. Metin: "Deftere yazılamayan bozuk kayıt var" / "Bozuk kayıt dosyası temizlendi". Alarm dosya boşalana ya da adı değişene kadar sürer; motor dosyayı silmez/kısaltmaz. Temizleme elle: inceleme sonrası dosya `…spool.corrupt.<YYYYMMDD>.jsonl` adına taşınır (`mv`).

### 3.2 `ledger_gate`: `entries_allowed` durumunun salt okunur türetimi

`Ledger.entries_allowed()` yazma yapar (`check_writable`, `drain_spool`) ve salt okunur bağlantıda `LedgerStateError` verir; sağlık süreci **ikinci yazar olmamalıdır** (defter-spec Bölüm 9). Bu yüzden runner kapıyı kendisi, yazmadan türetir; her koşul `LedgerProbe` alanından gelir:

1. `spool_lines > 0` → kapalı, `code="spool_pending"`.
2. `unledgered_ids` boş değil (`find_unledgered_trades(api.open_trade_ids)`, salt okunur çağrı) → kapalı, `unledgered_trades`.
3. `has_active_params is False` → kapalı, `no_active_params`.
4. `schema_ok is False` → kapalı, `schema`.
5. Yukarıdakilerden herhangi biri `None` (ölçülemedi) → `UNKNOWN` (kapının gerçekte ne yaptığı bilinmiyor).
6. Hepsi temiz → OK. `orphan_ids` (1 saatten eski, trade'e bağlanmamış `entered` kararları) boş değilse WARN, `code="orphan_decisions"`, `detail` ilk 5 kimliği listeler.

Türetilen durum, botun içindeki `degraded` bayrağını (bellekte/dosyadan) **göremez**; bu bir bilinen eksikliktir (Bölüm 12, Soru 2). Önerilen çözüm (sonraki adım, `ledger.py`'de): `Ledger.gate_status_readonly() -> Health`.

### 3.3 Isınma (warm-up)

Bir konteynerin `started_at`'i `warmup_s=600` sn içindeyse o botun `bot_loop_age`, `candle_age`, `ledger_write_age` sonuçlarında `CRIT` yalnız `WARN`e indirilir (`code` sonuna `_warmup` eklenir); `UNKNOWN` olduğu gibi kalır. `api_reachable` ve `container_restarts` ısınmada gevşemez. Amaç: restart sonrası tek seferlik bayat mum gürültüsü; nabız zaten `WARN`da gider, dış servisin tolerans süresi (Bölüm 4) boşluğu örter.

## 4. Dış nabız (dead man's switch), sağlayıcıdan bağımsız

Amaç: droplet düşse, ağ kopsa, systemd timer durup runner hiç çalışmasa bile **sessizliğin** alarm vermesi. İçeriden uyarı (Telegram) bu durumu bildiremez; bu yüzden nabız dışarıdan beklenir. Cloudflare varsayılmaz.

```
class HeartbeatSender(Protocol):
    def ok(self, report: HealthReport) -> bool       # sağlıklı: nabız ping'i
    def fail(self, report: HealthReport) -> bool     # isteğe bağlı: açık "bozuk" ping'i
```

Tek somut gerçekleme v1: `HttpsHeartbeat` (standart kütüphane `urllib.request`):
- `HEARTBEAT_URL` (zorunlu; sır sayılır): `ok()` bu adrese HTTPS `GET`. `https://` dışı şema reddedilir (`ValueError` açılışta). Zaman aşımı 10 sn; 3 deneme (bekleme 2 sn, 5 sn); 2xx başarı. Yönlendirme izlenmez (ssrf/sızıntı azaltma).
- `HEARTBEAT_FAIL_URL` (isteğe bağlı): doluysa `fail()` buraya `GET`; boşsa `fail()` hiçbir şey göndermez (sessizlik = alarm). Sağlayıcının "başarısızlık" uç noktası yoksa boş bırakılır.
- Adres ve sır günlüğe **asla** basılmaz (yalnız ana makine adı ve HTTP durum kodu). Hata metinleri adresi içermez.
- Çağrı gövdesi yok ya da en çok 200 bayt düz metin (`overall`, başarısız kontrol kodları); sır/bakiye/pozisyon içermez.

Sağlayıcı seçimi **sonraya** bırakılır: healthchecks.io tarzı herhangi bir "ping gelmezse alarm" servisi (healthchecks.io ücretsiz katmanı veya kendi barındırılan örneği, Better Stack/Cronitor/UptimeRobot heartbeat izleyicileri, ayrı bir makinedeki Uptime Kuma push monitörü) yalnızca bir URL verir; kodda sağlayıcıya özel hiçbir şey yoktur. Seçim ölçütleri: ücretsiz katman, e-posta + (varsa) Telegram/webhook entegrasyonu, ping sıklığına uygun tolerans, **bizim droplet'ten bağımsız** altyapı (aynı droplet'te barındırılan izleyici anlamsızdır).

Zamanlama: runner her **5 dakikada** çalışır; dış servis "beklenen aralık 5 dk, tolerans (grace) 15 dk" ile kurulur. Böylece art arda en çok 2 kayıp nabız (sağlıksız dahil) tolere edilir, 3. kayıp (≥ 15 dk) alarm verir; tek bir bayat mum/restart alarm vermez. Dış alarm kanalı kullanıcının seçeceği e-posta/Telegram'dır; bu kanal içeriden Telegram yolundan **bağımsızdır** (ikisi birden kırılamaz).

**Nabız kuralı (karar tablosu):**

| `overall` | `ok()` gönderilir mi | `fail()` | içeriden uyarı |
|---|---|---|---|
| OK | evet | hayır | yok (önceki bozuksa "düzeldi" bildirimi) |
| WARN | evet | hayır | var (Bölüm 5) |
| CRIT | **hayır** | evet (varsa) | var |
| UNKNOWN | **hayır** | evet (varsa) | var |
| Runner çöktü / `evaluate` istisna | **hayır** | hayır | `OnFailure` birimi (Bölüm 8) |

Nabız, kontrol hesabı tamamlandıktan sonra, **en son adım** olarak gönderilir; hesabın herhangi bir noktasında istisna olursa nabız gitmez. Nabız gönderimi başarısızsa runner yerelde `CRITICAL` günlük yazar, içeriden `heartbeat_send_failed` uyarısı üretir (dış servis zaten sessizlikten uyarır); `ok()` tekrar denenmez (bir sonraki tur 5 dk sonra).

## 5. Uyarı yolu: `Notifier` arayüzü ve tekrar bastırma

Telegram gerçeklemesi madde 18'dedir. Burada yalnız arayüz ve yerel gerçeklemeler:

```
@dataclass(frozen=True) class Alert:
    level: Status                # WARN | CRIT | UNKNOWN | OK (düzeldi bildirimi)
    code: str                    # CheckResult.code
    title: str                   # ≤ 80 karakter
    body: str                    # ≤ 500 karakter, sır içermez
    fingerprint: str             # "<name>|<code>"; tekrar bastırma anahtarı
    created_at: datetime
class Notifier(Protocol):
    def send(self, alert: Alert) -> bool    # True = iletildi; istisna fırlatmaz, False döner
```

Yerel gerçeklemeler (bu iş paketinde): `LogNotifier` (stderr/journal; her zaman çalışır, `False` dönmez) ve `NullNotifier` (testler, `send` çağrılarını listeler). `TelegramNotifier` bu belgenin kapsamı dışıdır (madde 18). Runner `NOTIFIER=log` (varsayılan) ile açılır; bilinmeyen ad → çıkış 1.

**Tekrar bastırma ve onay (debounce)** (`health.py`'deki saf `plan_alerts(report, state, now, cfg) -> (list[Alert], new_state)`):
1. Aynı `fingerprint` için seviye `CRIT`/`UNKNOWN`: ilk uyarı, bozukluğun **ardışık 2. çalışmasında** (≈ 10 dk) gider; `IMMEDIATE_CODES = {disk_low, unledgered_trades, spool_pending, spool_corrupt, schema, oom_killed}` 1. çalışmada gider. Sonra her **180 dk**'da bir hatırlatma.
2. `WARN`: ilk görüldüğünde (ardışık 2. çalışmada) bir uyarı, sonra her **720 dk**.
3. Bir `fingerprint` bir çalışmada kaybolursa `state`'te kapanır; daha önce uyarı gönderilmişse **bir** "düzeldi" (`level=OK`) uyarısı.
4. `Notifier.send` `False` dönerse `last_alert_at` güncellenmez (sonraki turda yeniden denenir); alınamayan uyarı nabzı etkilemez (nabız yalnız sağlığa bağlı).
5. Yeniden başlatma sonrası `UNKNOWN` seli: aynı turda ≥ 4 farklı `fingerprint` bozuksa tek özet uyarı (`code="multiple"`) gider, ayrıntı `body`'de (kontrol adları, ilk 5).

### 5.3 Durum dosyası

`/var/lib/trader-health/state.json` (`StateDirectory=trader-health`): `{"schema":1, "restart_counts":{...}, "fingerprints":{fp:{"first_seen","consecutive","last_alert_at","alerted":bool}}, "last_overall":"OK", "last_run_at":...}`. Atomik yazma: aynı dizinde `.state.json.tmp-<pid>` + `fsync` + `os.replace` (1L3A `atomik_yaz_json`). Dosya yoksa ya da bozuksa **boş durum** sayılır (restart sayacı sıfırdan, tüm uyarılar yeni), `WARN` `state_reset` kaydı yazılır; bozuk dosya sessizce yutulmaz ama sağlığı bozmaz. Konteyner sayaçları bu dosyada olduğundan 24 saatlik `delta` yerine "önceki çalışmadan beri" delta kullanılır (5 dk pencere): bir çalışmada ≥ 1 yeni restart `WARN`, ≥ 3 (ya da `state != running`, `oom_killed`) `CRIT`. Sürekli restart döngüsü (her turda +1) her turda WARN verir ve tekrar bastırma ile 720 dk'da bir hatırlatılır; 3 tur üst üste restart `CRIT`'e yükseltilir (`consecutive_restart_runs ≥ 3` durumda tutulur).

## 6. Günlük yedek (`scripts/health_backup.py`)

Amaç: iki defter (`ledger_learner.sqlite`, `ledger_twin.sqlite`) ve iki freqtrade veritabanı (`tradesv3.sqlite`, her botun `user_data` dizininde) günde bir yerel döner dizine yedeklenir; her yedek doğrulanır; **kaynak veritabanı kilitlenmez, yazar engellenmez**.

### 6.1 Zamanlama ve kaynak kullanımı
Günde bir, 03:10 UTC (`OnCalendar=*-*-* 03:10:00 UTC`, `Persistent=true`: makine kapalıyken kaçan çalışma açılışta yapılır). `Nice=19`, `IOSchedulingClass=idle`, `MemoryMax=96M`. Dört dosya **sırayla** (paralel değil) yedeklenir.

### 6.2 Kopyalama yöntemi
- **Dosya kopyası (`cp`) yasaktır** (WAL/`-shm` tutarsızlığı).
- Kaynak, salt okunur URI ile açılır: `sqlite3.connect("file:<yol>?mode=ro", uri=True, timeout=5)`; hedef `<dest>.partial` dosyasına `Connection.backup(hedef, pages=-1)` (tek adım, tek okuma işlemi). Defterler WAL modundadır: okuyucu yazarı bloklamaz; boyutlar küçük (MiB düzeyi) olduğundan tek adım milisaniyeler sürer. `pages=-1` seçildi çünkü sayfa sayfa kopyada araya giren yazma kopyayı baştan başlatır.
- Defter dosyaları için eşdeğer olan `Ledger.backup(dest)` (defter-spec Bölüm 4) kullanılabilir (aynı sqlite yedek API'si); ancak o yöntem şema denetimi ve açılış maliyeti getirdiği için betik ham `sqlite3` ile yapar ve sonuçta aynı doğrulamayı uygular.
- **freqtrade veritabanı**: freqtrade varsayılanı WAL **değildir** (geri alma günlüğü); okuma anında kısa süre yazara `database is locked` bekletebilir. Veritabanı küçük (trade tablosu) olduğundan kabul edilir; `timeout=5`. `OperationalError: database is locked` olursa 30 sn sonra **bir** yeniden deneme; yine başarısızsa o dosya `failed`, uyarı gider, döngü sürmez.
- DD-8 (E4) bozuk spool: `<db>.spool.corrupt.jsonl` varsa ve boş değilse `ledger_<bot>.sqlite.spool.corrupt.jsonl` olarak kopyalanır (`fsync`), manifestte ilgili defter girdisine `"spool_corrupt_bytes"` yazılır; yok/0 bayt → kopya ve alan yok.
- Spool: `<db>.spool.jsonl` varsa aynı dizine olduğu gibi kopyalanır (`shutil.copyfile`, `fsync`); boş/yok ise atlanır. Spool yedeğe girmesi, defter ile spool arasında kurtarma yapılabilmesi içindir.

### 6.3 Dizin düzeni ve adlandırma
```
/var/backups/trader/                    # BACKUP_DIR (ortam değişkeni); sahibi root, izin 0700
  2026-11-16/
    ledger_learner.sqlite
    ledger_twin.sqlite
    freqtrade_learner.sqlite
    freqtrade_twin.sqlite
    ledger_learner.sqlite.spool.jsonl   # yalnız doluysa
    MANIFEST.json
  2026-11-15/ ...
```
Gün dizini UTC tarihi. Aynı gün ikinci çalışma: gün dizini varsa ve `MANIFEST.json` `ok=true` ise **atlanır** (idempotent); `ok=false` ya da `.partial` varsa dizin `<tarih>.failed-<HHMM>` olarak yeniden adlandırılıp yeniden denenir.

### 6.4 Doğrulama (her dosya için, kopya bittikten sonra, kopya üzerinde)
1. `PRAGMA integrity_check` (tam, kopyada) sonucu tam `ok` olmalı.
2. Defter: `PRAGMA user_version` kaynağın okunduğu `user_version`'a eşit; `meta.bot` beklenen bot; `BEFORE UPDATE/DELETE` tetikleyici sayısı kaynaktaki sayıya eşit (tablo başına; `ledger.py` `_trigger_ddl` ile aynı beklenti); tablo başına `max(id)` değerleri manifestte kayıtlı.
3. freqtrade: `trades` tablosu mevcut; `count(*)` manifestte kayıtlı.
4. Kopya boyutu > 0 ve kaynaktaki `page_count × page_size` ile uyumlu (± WAL farkı kabul; yalnız > 0 ve `integrity_check` zorunlu).
5. SHA-256 hesaplanır ve manifestte saklanır (sonradan bozulma tespiti için).
Doğrulama başarısızsa kopya `<ad>.corrupt` olarak yeniden adlandırılır (silinmez), dosya `failed`.

### 6.5 `MANIFEST.json`
`{"schema":1,"created_at","host","ok":bool,"files":{ad:{"ok","bytes","sha256","integrity":"ok","user_version","max_ids":{tablo:id},"trades":int,"error":null|"kod"}}}`. Yazma atomik (Bölüm 5.3 yöntemi). `ok` = dört dosyanın hepsi `ok`. Sır içermez.

### 6.6 Dönüş (rotation)
`BACKUP_KEEP_DAYS` (varsayılan **14**, alt sınır 3, üst sınır 60; dışı `ValueError`). Kural: yeni günün manifesti `ok=true` olduktan **sonra** en yeni N gün dizini kalır, daha eskiler silinir. Güvenlik: (a) bugünkü yedek başarısızsa **hiçbir şey silinmez**; (b) silme sonrasında `ok=true` manifestli en az 3 gün dizini kalmalıdır, kalmayacaksa silme yapılmaz; (c) silinen yalnızca `BACKUP_DIR` altında, adı `YYYY-MM-DD` (ya da `.failed-*`/`.partial` kalıntısı) desenine uyan dizinlerdir (başka hiçbir yol silinmez; sembolik bağ izlenmez). Boyut tahmini: dört dosya ≈ 20 MiB/gün olarak varsayılırsa 14 gün ≈ 280 MiB (gerçek boyut Bölüm 12, Soru 4).

### 6.7 Yedek sağlığı ve çıkış kodu
Yedek betiği çıkış kodu: 0 hepsi başarılı; 20 en az bir dosya başarısız (uyarı gönderildi); 1 beklenmedik istisna (`OnFailure`). `health.backup_age` en yeni **`ok=true`** manifestten beslenir (runner `BACKUP_DIR`'in manifestlerini okur). İlk kurulum günü hiç manifest yoksa: ilk 26 saat `SKIPPED` (`code="no_backup_yet"`), sonra `UNKNOWN` (runner kurulum zamanını durum dosyasında `installed_at` olarak tutar). Yedek yoluna yazılamaması (disk dolu) `disk_free` kontrolünü zaten kırmızıya çevirir; yedek, boş alan < 1 GiB ise **hiç başlamaz** (yedek diski doldurup canlı defteri öldürmesin) ve `failed(disk_low)` olur.

### 6.8 Kapsam dışı
Droplet kaybına karşı **uzak kopya** bu sürümde yoktur (yedekler aynı makinede). Öneri: DigitalOcean anlık görüntüsü ya da `rclone`/`rsync` ile ayrı bir hedefe bir sonraki adımda (Bölüm 12, Soru 3). Şifreleme yok (dizin 0700); yedek sır içermez ama ticari veri içerir.

### 6.9 Geri yükleme (belge, otomatik değil)
Botlar `docker compose stop learner twin` ile durdurulur → bozuk dosya ve varsa `-wal`/`-shm` yan dosyaları `*.bad-<tarih>` diye **yan yana saklanır** (silinmez) → seçilen gün dizinindeki kopya + spool yerine konur → `sha256sum` manifestle karşılaştırılır → `scripts/health_recover.py --check` (Bölüm 7) çalıştırılır → botlar başlatılır. Defter geri yüklenince geri yükleme zamanından sonraki kayıtlar kaybolur; freqtrade'in açık işlemleri ile defter farkı `find_unledgered_trades` ile açığa çıkar ve kapı kapalı kalır (Bölüm 7, adım R5). Geri yükleme otomatik **yapılmaz**.

## 7. Yeniden başlatma kurtarma kontrol listesi (`scripts/health_recover.py --check`)

Salt okunur bir rapordur; hiçbir şey başlatmaz, düzeltmez, yazmaz (spool boşaltma dahil). Çıktı: adım başına `PASS | WARN | FAIL | UNKNOWN` ve yapılacak elle işlem. Aynı mantık `health.evaluate` ile paylaşılır (aynı `HealthSnapshot`); ek olarak aşağıdaki adımlar. Ne zaman çalışır: elle (restart/çökme sonrası), ayrıca runner `container_restarts` ≥ 1 gördüğünde durum raporuna "kurtarma önerilir" satırı ekler.

| Adım | Kontrol | Başarısızlıkta |
|---|---|---|
| R1 | Konteynerler `running`; `ExitCode`, `OOMKilled`, `RestartCount`, `StartedAt` | `oom_killed` ise bellek sınırını (Bölüm 11) ve `memory` kontrolünü incele; restart döngüsünde `docker logs --tail 200` |
| R2 | Canlı veritabanlarında `PRAGMA quick_check` (salt okunur, bot çalışıyorsa bile güvenli) | FAIL → botu durdur, Bölüm 6.9 ile son iyi yedeği geri yükle |
| R3 | Her defter salt okunur açılır: `user_version == SCHEMA_VERSION`, `meta.bot` doğru, tetikleyiciler tam (`LedgerSchemaError` → FAIL) | Kod/şema uyumsuzluğu: konteyner imajı ve `src` sürümünü kontrol et; göç yalnız bot durmuşken, elle |
| R4 | **Spool**: `<db>.spool.jsonl` satır sayısı. > 0 → FAIL (`spool_pending`, kapı kapalı) | Bot başlangıçta `drain_spool()` çağırır (defter-spec 8.2); bot çalışıyor ve spool hâlâ doluysa neden `ledger_gate`/`degraded` ile bakılır; elle boşaltma yalnız botlar durmuşken, tek yazar olarak `Ledger.drain_spool()` ile |
| R5 | **Açık işlemler**: freqtrade `/api/v1/status` açık işlem kimlikleri → `find_unledgered_trades(ids)`. Boş değil → FAIL (`unledgered_trades`) | Bu işlemler borsada/dry-run'da açık ama defterde girişi yok. Kapı zaten kapalıdır; otomatik düzeltme yok. Elle karar: (a) defter girişi `record_trade_entry` ile **geriye dönük** ve açıkça işaretli notla eklenir, ya da (b) pozisyon kapatılır. İkisi de insan işi |
| R6 | `find_orphan_decisions(older_than_s=3600)` | WARN; `record_decision` ile `supersedes_id`, `skipped/order_failed` düzeltmesi (defter-spec 7.2) |
| R7 | Her açık işlem için borsada koruyucu stop emri var mı (freqtrade `stoploss_on_exchange` / API alanı; **alan adı 2026.10 imajında doğrulanacak**) | Yoksa FAIL: yeniden başlatma sonrası korumasız pozisyon; stop elle ya da freqtrade'in kendi mutabakatı ile yeniden kurulana dek uyarı |
| R8 | `dry_run` değeri (API `show_config`) ve whitelist'in beklenenle aynı olduğu | Beklenmeyen `dry_run=false`: FAIL ve acil uyarı (bu belge canlı para açmaz; yalnız tespit eder) |
| R9 | `check_writable` eşdeğeri **dolaylı**: son `health_probes.probed_at` bot başlangıcından sonra mı | Değilse bot kapıyı henüz yoklamamış olabilir (ısınma); 2 mum sonra yeniden bak |
| R10 | Saat: `timedatectl show -p NTPSynchronized` = yes | `no` → WARN (mum yaşı ve nabız hesapları saate bağlı) |
| R11 | Önceki sağlık durumu (`state.json`): hangi kontroller bozuktu, ne zamandan beri | Bilgi |

**Kapı yeniden açma kuralı:** yeni işlem kapısını sağlık/kurtarma betiği **hiçbir zaman** açmaz ya da zorlamaz. Kapı yalnızca botun içinde `ledger.entries_allowed()` ≡ `ok=True` olduğunda açılır (defter-spec 8.1). Kurtarma betiğinin tek işi hangi koşulun kapıyı kapalı tuttuğunu ve ne yapılacağını söylemektir. Nabız, bu koşullar giderilene dek zaten `ledger_gate=CRIT` ile kesilidir.

## 8. Çalıştırma: runner ve systemd birimleri (`scripts/health_run.py`, `deploy/`)

### 8.1 Runner akışı (her 5 dk)
1. Ortamı oku (Bölüm 8.3). Yoksa/geçersizse: günlük + çıkış 1 (nabız gitmez, `OnFailure`).
2. Durum dosyasını oku (5.3).
3. Ölçümleri topla; **her ölçüm ayrı `try/except` ve kendi zaman aşımı** (HTTP 5 sn, `docker inspect` 10 sn). Hata → ilgili alan `None`. Toplam süre üst sınırı 60 sn (aşılırsa kalanlar `None`).
4. `health.evaluate` → `HealthReport`; `plan_alerts` → uyarılar.
5. Uyarıları gönder (`Notifier`); sonra **nabız** (Bölüm 4 tablosu); sonra durum dosyasını yaz.
6. Raporu tek satır JSON olarak stdout'a (journal) yaz (sır yok).
Salt okuma: HTTP `GET` (`/api/v1/ping`, `/api/v1/health`, `/api/v1/show_config`, `/api/v1/status`, `/api/v1/pair_candles?pair=<referans>&timeframe=<tf>&limit=2`); POST/PUT/DELETE yasak. API kimlik bilgileri ortam dosyasından, günlüğe basılmaz. Referans çift: whitelist'in ilki. freqtrade API uç noktalarının 2026.10 sürümündeki tam adları kod yazılmadan önce imajdan doğrulanacak.

### 8.2 Bellek ve süreç disiplini
Süreç ömrü < 10 sn, daemon yok (timer her seferinde başlatır; arada 0 bayt). `MemoryMax=64M`, `CPUQuota=20%`, `Nice=10`. Docker için SDK yok; `docker inspect` alt süreci. Docker soketi root'a eşdeğerdir; birim bu yüzden `User=root` ama sıkı sandbox ile çalışır (`ProtectSystem=strict`, `ReadOnlyPaths=/home/<kullanıcı>/trader/user_data`, `ReadWritePaths=/var/lib/trader-health`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectHome=read-only`). Alternatif (`docker` grubundaki ayrı kullanıcı) aynı yetkiyi verir; seçim Bölüm 12 Soru 5.

### 8.3 Ortam dosyası (`/etc/trader-health.env`, izin 0600, sahibi root)
Anahtarlar: `HEARTBEAT_URL`, `HEARTBEAT_FAIL_URL` (ops.), `FREQTRADE_API_USER`, `FREQTRADE_API_PASS`, `LEARNER_API=http://127.0.0.1:8080`, `TWIN_API=http://127.0.0.1:8081`, `LEDGER_DIR`, `FREQTRADE_USER_DATA_DIR`, `BACKUP_DIR`, `BACKUP_KEEP_DAYS`, `NOTIFIER`, `HEALTH_MAINTENANCE_FILE` (ops.). Kurallar (CT `ortam_dosyasi.py` dersi): satır ya boş, ya `#` ile başlayan tam satır yorum, ya `AD=değer`; eşittir çevresinde boşluk yok, değerde `#` yok, tırnak yok. Sır değerleri asla basılmaz. Depoda yalnız `deploy/trader-health.env.example` (değersiz) bulunur.

### 8.4 Birimler (`deploy/`, yeni)
| Dosya | İçerik özeti |
|---|---|
| `trader-health.service` | `Type=oneshot`, `ExecStart=/usr/bin/python3 -I /opt/trader/scripts/health_run.py`, `EnvironmentFile=/etc/trader-health.env`, `StateDirectory=trader-health`, `TimeoutStartSec=90`, `SuccessExitStatus=10 11 12` (sağlıksız/gönderim hatası = beklenen çıkış, `OnFailure` yalnız beklenmedik çöküşte), `OnFailure=trader-health-fail@%n.service`, sandbox (8.2) |
| `trader-health.timer` | `OnBootSec=2min`, `OnUnitActiveSec=5min`, `AccuracySec=15s`, `Persistent=false` |
| `trader-backup.service` / `.timer` | Bölüm 6; `Nice=19`, `IOSchedulingClass=idle`, `ReadWritePaths=/var/backups/trader`, `SuccessExitStatus=20`, `OnFailure=` aynı şablon; `OnCalendar=*-*-* 03:10:00 UTC`, `Persistent=true`, `RandomizedDelaySec=300` |
| `trader-health-fail@.service` | 1L3A `1l3a-bildirim@` ve CT `alarm.sh` deseni: `scripts/health_fail.sh %i` çalışır; yalnız `logger` + (varsa) `HEARTBEAT_FAIL_URL`'e `curl`; Telegram madde 18'e bağlanana dek sınırlı kalır; yapılandırma yoksa "atlandı" yazıp 0 ile çıkar (alarm zinciri ikinci hata üretmesin) |
| `trader-health.env.example` | 8.3 anahtarları, değersiz |
| `README` yok | Kurulum adımları madde 19 (dağıtım) belgesinde; burada yalnız dosya listesi |

Çıkış kodları (`health_run.py`): 0 = sağlıklı (OK/WARN) ve nabız gitti; 10 = CRIT/UNKNOWN (nabız yok, uyarı üretildi); 11 = sağlıklı ama nabız gönderilemedi; 12 = uyarı iletilemedi; 1 = beklenmedik hata.

## 9. Bakım penceresi
`HEALTH_MAINTENANCE_FILE` varsa ve içindeki ISO UTC zaman damgası gelecekteyse (en çok 4 saat ilerisi; fazlası yok sayılır) yalnız **içeriden uyarılar** bastırılır (`plan_alerts` listeyi boş döndürür). **Nabız bastırılmaz ve zorla gönderilmez**: bozuk sistem bakımdayken de sağlıklı sayılmaz; dış servis tarafında bakım için duraklatma kullanıcı işidir. Dosya yok/bozuk/süresi geçmiş → bakım yok (fail-closed: şüphede uyarı).

## 10. Fail-closed özeti
- Ölçüm istisnası, zaman aşımı, ayrıştırma hatası, negatif yaş, bozuk durum dosyası → `UNKNOWN` ve nabız yok.
- Zorunlu kontrol eksik → `UNKNOWN`. Tüm kontroller `SKIPPED`/boş → `UNKNOWN`.
- Runner çökerse nabız gönderilmez (nabız son adımdır) ve `OnFailure` çalışır.
- Timer/systemd/droplet ölürse nabız kesilir → **dış servis** alarmı (içeriden uyarı gerekmez).
- Notifier başarısızlığı nabzı ne açar ne kapatır; yalnız `12` çıkış kodu ve günlük.
- Sağlık modülü yalnız okur ve rapor eder: `forceenter`, `start`, `reload_config`, defter yazma, spool boşaltma, yedeği geri yükleme, kapıyı açma **yoktur**. (İsteğe bağlı sonraki sürüm: `CRIT` iken `/api/v1/stopentry` ile **kapatıcı** eylem; varsayılan kapalı, ayrı onay.)
- Yedek: başarısız yedek eski yedekleri silmez; boş alan < 1 GiB iken yedek başlamaz.

## 11. Sonraki adım için compose ve yapılandırma değişiklik listesi (bu iş paketinde YAPILMAZ)
1. `docker-compose.yml`: her servise `mem_limit` (öneri başlangıcı: learner 700m, twin 500m; paylaşımlı 2 GB'ta diğer proje ve swap payı için; gerçek RSS ölçümünden sonra ayarlanır) ve `memswap_limit`; `oom_kill_disable` **kullanılmaz**.
2. `docker-compose.yml`: `healthcheck` (python `urllib` ile `/api/v1/ping`; imajda `curl` olup olmadığı doğrulanacak), `interval: 60s`, `retries: 3`; `docker inspect .State.Health` ek kontrol olarak okunabilir.
3. `docker-compose.yml`: `stop_grace_period: 60s` (temiz kapanış, spool/defter yazımı bitsin).
4. `config/base.json` `api_server`: `listen_ip_address` `0.0.0.0` (konteyner içi; ana makineye yalnız `127.0.0.1` yayımlanıyor, doğru) ve **boş** `username/password/jwt_secret_key` — sağlık runner'ının `/api/v1/health`, `status`, `pair_candles` çağrıları için dolu kimlik bilgisi gerekir; değerler `.env`'den gelmeli (depoya girmez).
5. `ledger.py`: `Ledger.gate_status_readonly()` (Bölüm 3.2) ve isteğe bağlı `Ledger.last_write_at()`; sağlık betiğinin ham SQL yazmaması için.
6. Strateji: açılışta ve her mumda `health_probes` yazımı zaten `entries_allowed` ile; ek iş yok.
7. Yedek dizini compose'a girmez (ana makine yolu); `./user_data/<bot>` dizinleri ana makineden okunabilir olmalı (konteyner kullanıcı kimliği 1000 → root okur, sorun yok).

## 12. Belirsizlikler ve çözümleri
| # | Soru | Bu belgedeki çözüm |
|---|---|---|
| 1 | Dış nabız sağlayıcısı | Seçilmedi; `HttpsHeartbeat` yalnız URL ister. Sağlayıcı kullanıcı kararı (ölçütler Bölüm 4) |
| 2 | Botun bellekteki `degraded` bayrağı dışarıdan görünmez | Salt okunur türetim (3.2) + `gate_status_readonly` önerisi (11.5); bu arada `ledger_write_age` ve `spool_pending` yeterli ikinci sinyaldir |
| 3 | Droplet kaybına karşı uzak yedek | v1 kapsamı dışı; DO anlık görüntüsü ya da `rclone` sonraki adım. Kullanıcıya sorulacak |
| 4 | Gerçek veritabanı boyutları | Bilinmiyor (0 işlem); 20 MiB/gün varsayımı. İlk haftada manifestlerden ölçülüp `BACKUP_KEEP_DAYS` ve disk eşiği gözden geçirilir |
| 5 | Runner kullanıcısı (root + sandbox mı, `docker` grubu mu) | Root + sandbox önerilir; kullanıcı onayı |
| 6 | Bayat mum eşiği 2T/3T | `1h` zaman diliminde mum kapanışı sonrası ≤ 2 saat OK. Zaman dilimi değişirse formül `T`'ye bağlıdır; strateji spesifikasyonu daha sık zaman dilimi seçerse eşikler yeniden değerlendirilir |
| 7 | Veto dosyası ve bütçe yer tutucuları | Bölüm 3 satır 11–12: kapalıyken `SKIPPED`; ilgili madde tamamlanınca `HealthConfig` bayrağı ile açılır, `evaluate` imzası değişmez |
| 8 | `dry_run` iken "açık işlem" semantiği | freqtrade dry-run'da da `/status` döner; R5 aynı çalışır |

## 13. Elle doğrulanabilir örnekler (test yazarı için)

Hepsinde `now = 2026-11-16T12:30:00Z`, `timeframe_s = 3600`, `DEFAULT_CFG`.

### 13.1 Her şey sağlıklı
`ping_ok=True`; `last_process_at=12:29:30` (30 sn); son mum açılışı `12:00:00` (yaş 1800 sn ≤ 7320); defter son yazma `12:00:02` (1798 sn ≤ 3900); `spool_lines=0`, `unledgered_ids=()`, `orphan_ids=()`, `schema_ok=True`, `has_active_params=True`; disk 20 GiB boş; `MemAvailable` 900 MiB; swap 10 %; restart delta 0, `running`; `last_backup_at=03:10 bugün` (9 sa 20 dk); veto/bütçe kapalı. ⇒ `overall=OK`, `healthy=True`; satır 11 ve 12 `SKIPPED`; nabız gider.

### 13.2 Bayat mum eşikleri (T = 3600 ⇒ WARN > 7320, CRIT > 10920)
Son mum açılışı `10:30:00` (yaş 7200) ⇒ OK. `10:29:00` (7260) ⇒ OK. `10:27:00` (7380) ⇒ WARN. `09:27:00` (10980) ⇒ CRIT, `code="stale_candle"`. `09:30:00` (10800) ⇒ WARN (CRIT eşiği 10920 aşılmadı). Tam sınır: yaş = 7320 ⇒ OK (eşitlik iyi taraf).

### 13.3 Fail-closed: API okunamadı
`api["learner"]` tamamen `None` alanlı (zaman aşımı) ⇒ `api_reachable:learner` UNKNOWN, `bot_loop_age` UNKNOWN, `candle_age` UNKNOWN; diğer her şey OK ⇒ `overall=UNKNOWN`, `healthy=False` ⇒ nabız **yok**; `fail()` varsa çağrılır; uyarı ardışık 2. turda (≈ 10 dk); dış servis 15 dk sonra alarm verir.

### 13.4 Disk ve bellek
Disk boş 2,5 GiB ⇒ WARN; 0,9 GiB ⇒ CRIT `disk_low` (`IMMEDIATE`, ilk turda uyarı); tam 3 GiB ⇒ OK. `MemAvailable` 250 MiB ⇒ OK, 249 ⇒ WARN, 119 ⇒ CRIT. Swap: toplam 2048 MiB, kullanılan 1100 MiB (0,537) ⇒ WARN; 1700 MiB (0,83) ⇒ CRIT; `swap_total=0` ⇒ `SKIPPED`.

### 13.5 Konteyner restart
`prev={"trader-learner":4}`, şimdi `restart_count=4`, `running` ⇒ OK. Şimdi 5 ⇒ WARN (delta 1). Şimdi 7 ⇒ CRIT (delta 3). `restart_count=4` ama `state="restarting"` ⇒ CRIT. `oom_killed=True` ⇒ CRIT `oom_killed` (`IMMEDIATE`). `started_at=12:25:00` (5 dk önce) ve `candle_age` CRIT ⇒ ısınma içinde: WARN `stale_candle_warmup`; `api_reachable=False` ⇒ yine CRIT (3.3).

### 13.6 Defter kapısı
`spool_lines=1` ⇒ `ledger_gate` CRIT `spool_pending` (kapı kapalı olurdu), `overall=CRIT`, nabız yok. `unledgered_ids=(9,)` (freqtrade açık `[7,8,9]`, defterde 7,8) ⇒ CRIT `unledgered_trades`. `orphan_ids=(31,)` ve diğerleri temiz ⇒ WARN `orphan_decisions`, nabız gider. `spool_lines=None` ⇒ UNKNOWN. İki bot: biri OK biri CRIT ⇒ `overall=CRIT`.

### 13.7 Birleştirme ve yer tutucular
Sonuçlar: OK, OK, `SKIPPED`, WARN ⇒ `overall=WARN`, `healthy=True`. OK + UNKNOWN + WARN ⇒ UNKNOWN. Yalnız `SKIPPED`'lar ⇒ UNKNOWN. Z-işaretli bir kontrol `results`'ta yok ⇒ `missing_check` UNKNOWN eklenir. Negatif yaş (`last_process_at = 12:31`) ⇒ UNKNOWN `clock_skew`. `veto_max_age_s=900`, mtime yaşı 1000 sn ⇒ WARN; 2800 sn ⇒ CRIT; `veto_max_age_s=None` ⇒ `SKIPPED placeholder`. `budget_check_enabled=True`, `budget_state="exhausted"` ⇒ CRIT; `"weird"` ⇒ UNKNOWN.

### 13.8 Uyarı bastırma zaman çizelgesi (5 dk'lık turlar, `stale_candle` CRIT, `IMMEDIATE` değil)
t=0 CRIT (ardışık 1): uyarı yok. t=5 (ardışık 2): **uyarı 1**. t=10…175: yok. t=185 (5+180): hatırlatma. t=200 kontrol düzelir ⇒ bir "düzeldi" (`level=OK`). t=0'da `disk_low` (`IMMEDIATE`) ⇒ uyarı t=0'da. Aynı turda 5 farklı fingerprint CRIT ⇒ tek `multiple` uyarısı, `body`'de ilk 5 ad. `Notifier.send`=False ⇒ ertesi turda yeniden denenir.

### 13.9 Nabız kararı
Raporlar: OK ⇒ `ok()` çağrılır. WARN ⇒ `ok()` + uyarı. CRIT ⇒ `ok()` çağrılmaz, `fail()` varsa çağrılır. `HEARTBEAT_URL=http://x` ⇒ açılışta `ValueError` (https zorunlu). Gönderim: 1. deneme zaman aşımı, 2. deneme (2 sn sonra) 200 ⇒ başarı; üçü de hata ⇒ çıkış 11, `heartbeat_send_failed` uyarısı. Dış servis: son başarılı ping 12:00, ping'ler 12:05'te beklenir, 15 dk tolerans ⇒ 12:20'ye kadar ping yoksa alarm.

### 13.10 Yedek ve rotation
`BACKUP_KEEP_DAYS=14`, `BACKUP_DIR` içinde 16 gün dizini (11-01 … 11-16), hepsi `ok=true`; 11-16 yedeği az önce doğrulandı ⇒ en eski 2 dizin (11-01, 11-02) silinir, 14 kalır. Aynı durumda 11-16 manifesti `ok=false` ⇒ **hiçbir şey silinmez**. 11-16 `ok=true` ama eski 15 dizinin 12'si `ok=false` ⇒ silme sonrası `ok=true` sayısı ≥ 3 kuralı: kalanlarda `ok=true` en az 3 ise silinir, değilse hiçbir şey silinmez. `BACKUP_KEEP_DAYS=2` ⇒ `ValueError`. Dizin adı `notes` ⇒ asla silinmez. Boş alan 0,8 GiB ⇒ yedek başlamaz, `failed(disk_low)`, çıkış 20.
Doğrulama: kopyada `integrity_check` = `ok`, `user_version` 1 = kaynak 1, `meta.bot="learner"`, tetikleyici sayısı kaynakla eşit ⇒ `ok`. Kopya baytı elle bozulup `integrity_check` "ok" dışı dönerse ⇒ dosya `.corrupt`, `MANIFEST.ok=false`, `backup_age` eski yedekten hesaplanır (bugün başarısız ⇒ 26 sa sonra WARN). `backup_age`: 25 sa ⇒ OK, 27 sa ⇒ WARN, 51 sa ⇒ CRIT.
Aynı gün ikinci çalışma ve manifest `ok=true` ⇒ atlanır (çıkış 0).

### 13.11 Kurtarma listesi
Konteyner kill -9 sonrası: R1 `RestartCount` +1, R4 `spool_lines=2` ⇒ FAIL (kapı kapalı); bot açılışta `drain_spool()` 2 döner, spool boşalır ⇒ sonraki çalışmada R4 PASS. R5: freqtrade açık `[7,8,9]`, defterde 7, 8 ⇒ FAIL `[9]`; rapor "elle karar: geriye dönük giriş ya da kapat" der; betik hiçbir şey yazmaz. R8: `dry_run=false` ⇒ FAIL ve acil uyarı.

## 14. Test planı (kod bu belgede yok; `tests/test_health_spec.py`, `tests/test_health_backup_spec.py`)
`evaluate` için 13.1–13.7'nin her satırı; `plan_alerts` için 13.8; `HttpsHeartbeat` için sahte HTTP sunucusu (13.9, yönlendirme izlenmez, adres günlüğe girmez); yedek için geçici dizinde gerçek `sqlite3` dosyaları: WAL modunda açık yazar bağlantısı varken yedek yazarı **bloklamaz** (yazar `busy_timeout` içinde commit eder), bozuk kaynak ve bozuk kopya, rotation (13.10), idempotentlik, `.partial` kalıntısı; durum dosyası atomik yazma ve bozuk dosyada boş durum; ortam dosyası ayrıştırma (satır sonu `#`, boşluk, tırnak). `health.py` içe aktarımının `pandas`/`numpy`/`freqtrade` yüklemediği (`sys.modules` denetimi) ve `trader_core/__init__.py`'nin yalnız docstring içerdiği doğrulanır. Ağ, `docker` ve gerçek saat testlerde kullanılmaz (hepsi enjekte).


## 14. Motor uyarlaması

freqtrade kaldırıldı; girdi kaynağı kendi motorumuzun `status.json` dosyasıdır (`docs/motor/05-engine-runner.md` §8.2, şema `engine-status/1`). **Bu belgede geçen freqtrade API, `docker inspect`, `tradesv3.sqlite`, `FREQTRADE_*`, `LEARNER_API/TWIN_API`, `LEDGER_DIR` ifadeleri bu bölümle değiştirilmiştir.** `health.evaluate` ve 12 kontrolün adları/eşikleri/fail-closed davranışı aynıdır; yalnızca ölçüm toplayıcı (`scripts/health_run.py`) değişti. `ApiProbe` adı tarihsel kaldı.

**Yollar** (tek ortam anahtarı `ENGINE_VAR_DIR` = motor `var_dir`): `<var>/<bot>/status.json`, `<var>/<bot>/ledger.sqlite`, `<var>/<bot>/state.sqlite` (`bot` ∈ learner, twin). Yedek dosya adları: `ledger_<bot>.sqlite`, `state_<bot>.sqlite` (doğrulama: `positions` tablosu, manifestte `positions` sayısı).

**status.json okuma kuralları (fail-closed):** dosya yok → `ping_ok=False` (CRIT `api_unreachable`; döngü/mum UNKNOWN); okunamaz, bozuk JSON, `schema != engine-status/1`, `bot` uyuşmaz, 2 MB üstü → tüm alanlar `None` (UNKNOWN); `loop_at` 120 sn'den eskiyse `ping_ok=False`; `loop_at` gelecekteyse (saat uyumsuz) `ping_ok=None`. Twin dosyası yoksa twin bazlı kontroller CRIT/UNKNOWN olur ve `overall` sağlıksızdır (iki bot zorunlu).

| # | Kontrol | Motor kaynağı |
|---|---|---|
| 1 | `api_reachable` | `loop_at` yaşı ≤ 120 sn ve dosya geçerli |
| 2 | `bot_loop_age` | `loop_at` |
| 3 | `candle_age` | `last_candle_open`; periyot `trigger_tf` |
| 4 | `ledger_write_age` | `<var>/<bot>/ledger.sqlite` (salt okunur; değişmedi) |
| 5 | `ledger_gate` | defter yoklaması (spool, unledgered, şema, etkin param) + `gate.code` (ok/kill dışı → CRIT `engine_gate_closed`); `kill`/`gate.code=="kill"` → WARN `engine_kill`; `counters.ledger_errors > 0` → WARN `ledger_errors`; `open_trade_ids` `find_unledgered_trades` girdisi |
| 6 | `disk_free` | `ENGINE_VAR_DIR` + `BACKUP_DIR` (değişmedi) |
| 7 | `memory` / `swap` | `/proc/meminfo` (değişmedi) |
| 8 | `container_restarts` | `status.started_at` değişimi → kalıcı sayaç (+1; `state.json` `restart_counts`/`engine_started_at`); `state="running"` ⇔ `loop_at` ≤ 300 sn, aksi `not_running` (CRIT); `started_at` ısınma için kullanılır; `oom_killed` her zaman `None` |
| 9 | `backup_age` | değişmedi (`health_backup.py`: iki defter + iki motor state) |
| 10 | `veto_file_age` | değişmedi |
| 11 | `budget_status` | değişmedi |

Kurtarma (§7): R5 `open_trade_ids`; R7 `open_positions[].stop` boş/≤0 → FAIL (paper'da borsa stop'u yok, motorun stop'u var); R8 `dry_run`; R1 status tazeliği.

**Motor tarafında eksikler (rapor edildi, motor değiştirilmedi):** (a) `oom_killed`/süreç çıkış nedeni status'ta yok → `None`; (b) yeniden başlatma sayacı status'ta yok → `started_at` değişiminden türetilir (iki çalışma arasında 2 restart tek sayılır); (c) status'ta `ledger_errors` kümülatiftir (süreç başından), zaman penceresi yok; (d) status'ta son defter yazma zamanı yok → defter sqlite'ından okunur; (e) temiz kapanış (`kalp_atisi.json` `stopped`) okunmuyor.

## 15. Piyasa verisi alarmları (opt-in: `MARKET_DB`)

`HealthSnapshot.market` (`MarketProbe`) doluysa `evaluate` ek kontroller üretir; `None` ise hiçbiri çalışmaz ve `REQUIRED_CHECKS` değişmez. Okuyucu `trader_core/market_probe.py` (yalnız stdlib, `trader_engine` içe aktarmaz): `market.sqlite` salt okunur (`file:...?mode=ro`), `feed-status.json` ve motor `status.json` dosyaları ≤ 2 MB okunur. Eşikler `HealthConfig` içinde.

| Kontrol | Koşul | Sonuç (kod) |
|---|---|---|
| `feed_status_age` | `feed-status.json` yok / `ts` yaşı > `feed_status_crit_s` (180 sn) / bozuk | CRIT `feed_status_missing` / CRIT `feed_status_stale` / UNKNOWN |
| `market_bar_age` | yapılandırılmış her çift için en yeni `bars(kind='last', tf='1m')` açılışı yaşı > `market_bar_crit_s` (300 sn) ya da mum yok | CRIT `market_bars_stale` |
| `rules_coverage` | `rules` satır sayısı < yapılandırılmış çift sayısı | CRIT `rules_incomplete` |
| `rules_age` | `feed_meta.rules_fetched_at` yaşı > `rules_warn_s` (24 sa); değer yok | WARN `rules_stale`; UNKNOWN |
| `rules_missing:<bot>` | motor `status.counters.rules_missing` önceki turdakinden **büyük** | CRIT `rules_missing_increase` (`IMMEDIATE_CODES`: ilk turda uyarır) |

`market.sqlite` yoksa `market_bar_age`/`rules_coverage`/`rules_age` hepsi CRIT `market_db_missing` ("market.sqlite yok"); açılamazsa UNKNOWN. Delta durumu runner `state.json` içindeki `rules_missing` ({bot: sayı}) alanındadır; ilk turda önceki değer yoktur (taban, alarm yok), sayaç azalırsa (motor yeniden başladı) alarm yok ve taban güncellenir. Sayaç okunamazsa UNKNOWN (taban korunur).

**Döngü gecikmesi** için yeni kontrol eklenmedi: `bot_loop_age` (WARN > 120 sn, CRIT > `loop_crit_s` = 300 sn, `status.loop_at`) ve `container_restarts` (`not_running` ⇔ `loop_at` > 300 sn) zaten karşılıyor.

**Ortam** (`deploy/trader-health.env.example`): `MARKET_DB` (etkinleştirir), çift listesi `MARKET_PAIRS` (virgüllü) ya da `ENGINE_CONFIG_DIR/engine.base.json` `pairs`; ikisi de yoksa `feed-status.json` içindeki liste; `MARKET_FEED_STATUS` (varsayılan `$ENGINE_VAR_DIR/feed-status.json`). Testler: `tests/test_health_market_spec.py`.

## 16. ML model paketi süresi/tazeliği ve sapma izleyicisi kancası (ek, 17 Kasım 2026; onay listesi madde 8 ve 3)

> **[24 Kasım 2026]** ML filtreleri silindi: `ml_package:<bot>` denetimi, `MlProbe`, `ml_*` kodları ve Telegram "Model" satırı koddan kaldırıldı; 16.1-16.5 ve 16.7 yalnız tarihçedir. Sapma izleyicisi kancası (16.6) geçerlidir.

Kaynak: `repo-denetim-onay-listesi.md` madde 8 (A-18, D-06, B-25). Bu bölüm yalnız şartnamedir; uygulama WP-1 (ML kontrolü, rapor satırı, kanca yer tutucusu) ve WP-2'dir (kancanın doldurulması). Motor ve `trader_ml` kodu **değişmez**: kontrol yalnız okur.

### 16.1 Doğrulanmış olgular (kodda okundu)

1. `ml_mode ∈ {off, shadow, active}`. `status.json` `ml` bloğu (`strategy_runner.py:258-277`): `mode`, `state` (`off` | `ok` | `no_model` | `expired`), `model_id`, `threshold`, `expires_at` (ISO), `error`, `features`, `v2_error`, `v2_errors`, `entries_blocked`. ML'siz stratejide blok `null`'dır.
2. `entries_blocked = (mode == "active" ve state ∈ {no_model, expired})`. Bu durumda motor `entries_open=false` ve `gate.code = "ml_no_model"` / `"ml_expired"` yazar (`status.py`); yeni giriş açılmaz, açık pozisyonlar yönetilmeye devam eder.
3. Paket süresi: `min(meta.expires_at, meta.created_at + 21 gün)` (`ml_package.py` `expires_at`, `MODEL_EXPIRY_DAYS = 21`); `now >= sınır` ise dolmuştur.
4. **Motor paketi yalnız başlangıçta yükler** (`engine.py` kurulum; yeniden yükleme yok). Diske yeni paket koymak motor yeniden başlatılmadan etki etmez; süre ise her karar anında yeniden sınanır. Yani "yeniden eğitim başarılı ama motor yeniden başlatılmadı" durumunda da girişler 21. günde kesilir. Motor süresi dolmuş bir paketle **başlatılırsa** yükleme reddedilir ve durum `expired` değil `no_model` olur (`error` metninde neden yazar).
5. Paket `meta` alanları (`trader_ml/package.py`): `pkg_version`, `version`, `kind`, `created_at`, `expires_at`, `expiry_days`, `features`, `feature_list_hash`, `feature_ranges`, `train_window.{start,end}`, `n_train`, `data_hash`, `code_hash`, `model_hash`; ayrıca `gate_passed`, `user_approved`. `model_id = "<version>@<model_hash ilk 12>"`. Pakette "hangi piyasa anlık görüntüsünden üretildi" alanı **yoktur**; veri soyu için bugün yalnız `data_hash` ve `train_window.end` kullanılabilir.
6. `active` kipte puanlanamayan aday elenir (`price_action_v1_ml.py`: puanlama hatası → etiket yok → eleme); hatalar `counters.ml_score_errors` ve `ml.v2_errors` sayaçlarına yazılır. Bu da sessiz giriş kaybıdır.
7. Bugün `health.py`'de ML kontrolü ve günlük raporda ML satırı yoktur; kapı kapalıyken rapor yalnız "yapay zekâ filtresi hazır değil" der (`telegram.neden_tr`).

### 16.2 Veri yapıları

`health.py`'ye (yalnız stdlib; `trader_core.ml_package` **içe aktarılmaz**, numpy gerektirir):

```
MlProbe (frozen dataclass; ölçülemeyen alan None)
  # status.json `ml` bloğundan (motorun gerçekte kullandığı)
  present: bool | None            # blok var mı (None = status okunamadı)
  mode: str | None
  state: str | None
  model_id: str | None
  expires_at: datetime | None     # tz-aware UTC
  error: str | None
  score_errors: int | None        # counters.ml_score_errors + ml.v2_errors
  # diskteki paket dosyasından (meta; model gövdesi doğrulanmaz)
  file_state: str                 # "ok" | "missing" | "unreadable" | "not_configured"
  file_model_id: str | None
  file_created_at: datetime | None
  file_expires_at: datetime | None    # min(meta.expires_at, created_at + 21 gün)
  file_data_hash: str | None
  file_train_end: datetime | None     # meta.data_snapshot_at varsa o, yoksa train_window.end
  file_gate_passed: bool | None
  file_user_approved: bool | None
```

`HealthSnapshot.ml: Mapping[str, MlProbe] | None` (bot → yoklama). `None` ise bu bölümdeki kontrol hiç üretilmez ve `REQUIRED_CHECKS` değişmez (§15 ile aynı opt-in kalıbı).

`HealthConfig` yeni alanlar: `ml_warn_days = (7, 3, 1)`, `ml_data_max_age_days: float | None = None`, `drift_max_age_s = 129600` (36 saat), `drift_check_enabled = False`.

Runner (`scripts/health_run.py`): paket yolu `ML_MODEL_PATH_<BOT>` ortam anahtarından, yoksa `ENGINE_CONFIG_DIR/engine.base.json` + `engine.<bot>.json` birleşiminin `ml_model_path` alanından; ikisi de yoksa `file_state="not_configured"`. Dosya salt okunur, en çok 32 MB okunur (üstü `unreadable`). Zaman alanı tz'siz ise UTC sayılır (motorla aynı). Önceki tur bilgisi `state.json` içinde: `ml_seen[bot] = {model_id, created_at, data_hash, train_end, stale}` ve `ml_score_errors[bot]`.

### 16.3 Kontrol: `ml_package:<bot>` (zorunlu değil; bot bazlı)

Aşağıdaki satırlar sırayla değerlendirilir; birden çok satır tutarsa **en ağır** durum sonuçtur, `code` en ağır satırın kodudur, `detail` tutan bütün satırları listeler. Ağırlık: CRIT > UNKNOWN > WARN > OK.

| # | Koşul | Sonuç (kod) |
|---|---|---|
| 1 | `present is None` (status okunamadı) | UNKNOWN `ml_status_unreadable` |
| 2 | `present is False` ya da `mode == "off"` | SKIPPED `ml_off` (başka satır değerlendirilmez) |
| 3 | `mode == "active"` ve `state == "expired"` | CRIT `ml_expired` |
| 4 | `mode == "active"` ve `state == "no_model"` | CRIT `ml_no_model` (`detail` içinde `error`) |
| 5 | `mode == "shadow"` ve `state ∈ {expired, no_model}` | WARN `ml_shadow_down` |
| 6 | `state == "ok"` ve `kalan = expires_at − now`: `kalan ≤ 1 gün` | WARN `ml_expiring_1d` |
| 7 | aynı, `1 gün < kalan ≤ 3 gün` | WARN `ml_expiring_3d` |
| 8 | aynı, `3 gün < kalan ≤ 7 gün` | WARN `ml_expiring_7d` |
| 9 | `state == "ok"` ve `expires_at is None` ya da bilinmeyen `mode`/`state` metni | UNKNOWN `ml_status_invalid` |
| 10 | `file_state == "ok"`, `file_model_id != model_id`, dosya geçerli (`now < file_expires_at`, `file_gate_passed is True`, `active` ise `file_user_approved is True`) | WARN `ml_restart_needed` (yeni paket diskte, motor eskisini kullanıyor ya da hiç yükleyememiş) |
| 11 | `file_state == "ok"` ve dosya "bayat veri" işaretli (§16.4) | WARN `ml_stale_data` |
| 12 | `file_state ∈ {missing, unreadable}` ya da zorunlu meta alanı eksik/çözümlenemiyor ya da `file_created_at > now + 5 dk` | WARN `ml_file_invalid` |
| 13 | `score_errors` önceki turdakinden **büyük** | WARN `ml_score_errors` (iki kipte de; ilk turda taban alınır, alarm yok; sayaç azalırsa taban güncellenir, alarm yok) |
| 14 | hiçbiri | OK |

Notlar:

- Eşitlik iyi tarafa düşmez burada: süre için `kalan ≤ eşik` uyarır (son gün dahil); `kalan` negatifse motor zaten `expired` yazmıştır (satır 3/5). Motor `state == "ok"` derken `expires_at ≤ now` görülürse (yarış) satır 6 uygulanır.
- 7 / 3 / 1 gün ayrı kodlardır; böylece §5 tekrar bastırması her eşikte **yeni** bir uyarı çıkarır. 7 günün gerekçesi: haftalık yenilemede paket normalde 7 günlükken değişir; 14 günlük paket iki yenilemenin kaçtığını gösterir.
- `IMMEDIATE_CODES`'a eklenir: `ml_expired`, `ml_no_model` (girişler kesildi; ilk turda uyarır).
- `not_configured` dosya durumu tek başına sonuç üretmez (satır 10–12 atlanır); `detail`e "paket yolu bilinmiyor" yazılır.
- CRIT nabzı keser (mevcut kural; `veto_file_age` ve `budget_status` ile aynı sınıf: giriş durdu). WARN nabzı kesmez.
- Isınma (§3.3) uygulanmaz.

### 16.4 "Yeni dosya, eski veri" (B-25)

Amaç: yenileme işi çalışıp yeni tarihli paket ürettiği halde veri ilerlemediyse (toplayıcı durmuş, derlem yeniden kurulmamış) bunu yakalamak. Dosya değişiklik zamanı (mtime) **kullanılmaz**; yalnız paket içindeki kayıtlar.

Runner her turda diskteki paketi `ml_seen[bot]` ile karşılaştırır:

1. `ml_seen[bot]` yok → taban olarak kaydedilir (`stale=false`); alarm yok.
2. `file_model_id` aynı → değişiklik yok; `stale` bayrağı korunur.
3. `file_model_id` farklı ve `file_created_at > ml_seen.created_at`: `file_data_hash == ml_seen.data_hash` **ve** `file_train_end <= ml_seen.train_end` ise yeni kayıt `stale=true`; aksi halde `stale=false`. Kayıt yeni paketle güncellenir.
4. `file_model_id` farklı ve `file_created_at <= ml_seen.created_at` (eski pakete dönülmüş) → `stale=true` ("daha eski paket konmuş").
5. Mutlak yaş (isteğe bağlı): `ml_data_max_age_days` verilmişse ve `file_created_at − file_train_end > sınır` → `stale=true`. **Varsayılan `None`**: kilitli dönem (2026-05-01 → 2026-11-01) eğitimde kullanılamadığı için bugün her paketin eğitim sonu aylar öncesidir; sabit bir yaş eşiği sürekli çalardı. Değeri haftalık yeniden eğitim şartnamesi (plan maddesi I) belirler.

`stale=true` olduğu sürece satır 11 WARN verir; veri ilerlemiş yeni bir paket gelince kendiliğinden kapanır.

**Paket şemasına öneri (bu iş paketinde yapılmaz; `trader_ml` r02/r03 raporları işlenene kadar dondurulmuştur):** r04+ şablonunda `meta.data_snapshot_at` (derlemin kurulduğu piyasa verisinin en yeni mum zamanı) ve `meta.corpus_sha256`. Kontrol bu alan varsa onu, yoksa `train_window.end`i kullanır (ileri uyumlu).

### 16.5 Telegram: uyarı metinleri ve günlük rapor satırı

`health.py` `_HEALTH_TR` / `_HEALTH_TR_CODE` (sorun, düzeldi, anlamı); ham kod, model kimliği, dosya yolu kullanıcıya gösterilmez:

| Anahtar | Sorun | Düzeldi | Anlamı |
|---|---|---|---|
| `ml_package` (genel) | "Yapay zekâ modeli sorunlu" | "Yapay zekâ modeli yeniden normal" | "Modelin durumu için günlük rapora bak." |
| `ml_expired` | "Modelin süresi doldu — yeni işlemler durdu" | "Model yenilendi, yeni işlemler yeniden açık" | "Model 21 günden eski olduğu için bot yeni işlem açmıyor; açık pozisyonlar korunuyor. Model yenilenip motor yeniden başlatılmalı." |
| `ml_no_model` | "Model yüklenemedi — yeni işlemler durdu" | "Model yüklendi, yeni işlemler yeniden açık" | "Model dosyası yok, geçersiz ya da süresi dolmuş; bot yeni işlem açmıyor, açık pozisyonlar korunuyor." |
| `ml_shadow_down` | "Gölgedeki model çalışmıyor" | "Gölgedeki model yeniden çalışıyor" | "İşlemler etkilenmiyor; yalnız modelin izleme kaydı duruyor." |
| `ml_expiring_7d` | "Modelin süresi 7 gün içinde doluyor" | "Model yenilendi" | "Yenilenmezse süre dolduğunda yeni işlemler durur." |
| `ml_expiring_3d` | "Modelin süresi 3 gün içinde doluyor" | "Model yenilendi" | aynı |
| `ml_expiring_1d` | "Modelin süresi yarın doluyor!" | "Model yenilendi" | "Bugün yenilenmezse yeni işlemler durur." |
| `ml_restart_needed` | "Yeni model hazır ama devrede değil" | "Yeni model devrede" | "Motor yeniden başlatılana kadar eski model kullanılır." |
| `ml_stale_data` | "Yeni model eski veriyle üretilmiş" | "Model güncel veriyle yenilendi" | "Model dosyası yeni ama içindeki veri ilerlememiş; veri toplama ve eğitim hattı kontrol edilmeli." |
| `ml_file_invalid` | "Model dosyası okunamıyor" | "Model dosyası yeniden okunuyor" | "Sıradaki yeniden başlatmada model yüklenemeyebilir." |
| `ml_score_errors` | "Model bazı fırsatları puanlayamıyor" | "Model yeniden puanlıyor" | "Puanlanamayan fırsatlar alınmaz; işlem sayısı düşebilir." |

`shadow` kipte `ml_expiring_*` "anlamı" metni: "Yenilenmezse gölge izleme durur; işlemler etkilenmez."

**Günlük rapor** (`telegram.default_sections` yeni bölüm `"Model"`; `build_report` sıralamasında "Risk kademesi"nden hemen önce). Kaynak yalnız `status.json` `ml` bloğu ve sağlık `state.json` (`ml_seen[bot].stale`, son rapordaki `ml_package:<bot>` kodu). Bot başına tek satır; ikiz bot için sonuna " (ikiz bot)". Kalan süre: `g = floor(kalan_saniye / 86400)`; `g ≥ 1` ise "g gün", değilse "s saat" (`s = floor(kalan_saniye / 3600)`, en az 1).

| Durum | Satır |
|---|---|
| blok yok / `off` | `🤖 Model filtresi kapalı (bot filtresiz çalışıyor)` |
| `shadow`, `ok`, kalan > 7 gün | `🤖 Model gölgede izliyor, kararları etkilemiyor · süresi 12 gün sonra doluyor` |
| `active`, `ok`, kalan > 7 gün | `🤖 Model filtresi açık · süresi 12 gün sonra doluyor` |
| `active`, `ok`, kalan ≤ 7 gün | `⚠️ Model filtresi açık ama süresi 5 gün sonra doluyor; yenilenmezse yeni işlemler durur` |
| `shadow`, `ok`, kalan ≤ 7 gün | `⚠️ Gölgedeki modelin süresi 5 gün sonra doluyor (işlemler etkilenmez)` |
| `active`, `expired` | `🚨 Modelin süresi doldu: yeni işlem açılmıyor, açık pozisyonlar korunuyor` |
| `active`, `no_model` | `🚨 Model yüklenemedi: yeni işlem açılmıyor, açık pozisyonlar korunuyor` |
| `shadow`, `expired` / `no_model` | `⚠️ Gölgedeki model çalışmıyor (işlemler etkilenmiyor)` |

Ek cümleler (satırın sonuna, " · " ile): `ml_restart_needed` → "yeni model hazır, motorun yeniden başlatılması gerekiyor"; `ml_stale_data` → "yeni model eski veriyle üretilmiş görünüyor"; `ml_score_errors` → "bazı fırsatlar puanlanamadı". Bölüm okunamazsa mevcut kural geçerlidir (genel "Bazı bilgiler okunamadı" satırı; ham hata yok).

`active` + girişler kesikken `_risk_satirlari` zaten "🛑 Yeni işlemler kapalı: yapay zekâ filtresi hazır değil" yazar; `neden_tr` için özel metinler eklenir: `ml_expired` → "modelin süresi doldu", `ml_no_model` → "model yüklenemedi" (diğer `ml_*` kodları mevcut genel metinde kalır).

### 16.6 Sapma izleyicisi kancası: `drift_monitor:<bot>` (WP-2 için yer tutucu)

İzleyicinin kuralları ve eşikleri `docs/kagit-degerlendirme-plani.md` §4'tedir; sağlık yalnız onun çıktı dosyasını (`<var>/<bot>/drift.json`, şema `drift/1`) okur, hiçbir istatistik hesaplamaz.

`HealthSnapshot.drift: Mapping[str, DriftProbe] | None`; `DriftProbe(file_state: "ok"|"missing"|"unreadable", generated_at: datetime | None, overall: str | None, rules_at_uyari: tuple[str, ...])`.

| Koşul | Sonuç (kod) |
|---|---|
| `drift_check_enabled is False` ya da `snap.drift is None` | SKIPPED `placeholder` (WP-1 teslimindeki tek davranış) |
| `file_state == "missing"` / `"unreadable"` / şema ya da `bot` uyuşmuyor | WARN `drift_missing` / WARN `drift_unreadable` |
| `now − generated_at > drift_max_age_s` (36 sa) | WARN `drift_stale` |
| `overall == "UYARI"` | WARN `drift_alert` (`detail`: kural kimlikleri; yalnız günlükte/panoda, Telegram metninde değil) |
| `overall ∈ {OK, IZLE, YETERSIZ}` | OK |
| bilinmeyen `overall` | WARN `drift_unreadable` |

**Bilinçli istisna (fail-closed kuralından):** bu kontrol hiçbir koşulda `CRIT` ya da `UNKNOWN` üretmez ve nabzı kesmez. Gerekçe: izleyici para koruması değil istatistiksel bir bilgi aracıdır ve kullanıcı kararıyla proje durdurma ölçütü değildir; dosyasının eksikliği "sunucu öldü" alarmını tetiklememelidir. Eksik/bayat dosya yine de WARN ile görünür kalır.

`_HEALTH_TR`: `drift_monitor` → ("Bot beklenenden farklı davranıyor", "Bot yeniden beklendiği gibi davranıyor", "Bot durdurulmadı; ayrıntı günlük raporda. İnceleme gerekir."); `drift_missing` / `drift_stale` / `drift_unreadable` → ("Davranış izleyicisi çalışmıyor", "Davranış izleyicisi yeniden çalışıyor", "Günlük karşılaştırma yapılamıyor; işlemler etkilenmez.").

**Tek gönderici:** izleyici Telegram'a kendisi mesaj atmaz, yalnız `drift.json` yazar. Anlık `UYARI` mesajı bu kontrolün `drift_alert` sonucu üzerinden, mevcut uyarı yolu ve §5 tekrar bastırmasıyla gider (aynı olay iki kez gönderilmez); kural bazlı ayrıntı günlük rapordadır. `drift_check_enabled` WP-2 tesliminde açılır; o zamana kadar anlık mesaj yoktur.

### 16.7 Kabul testleri (bağımsız test yazarı için; `tests/test_health_ml_spec.py`, `tests/test_telegram_ml_spec.py`)

Hepsinde `now = 2026-12-10T12:00:00Z`, bot `learner`, aksi yazılmadıkça `file_state="not_configured"`, `score_errors` değişmemiş.

Sağlık kontrolü (`evaluate` sonucu içinde `ml_package:learner`):

1. `snap.ml is None` → sonuçlarda `ml_package` adlı kontrol **yok**; `REQUIRED_CHECKS` değişmemiş.
2. `present=False` → SKIPPED `ml_off`. `mode="off"` → SKIPPED `ml_off`.
3. `present=None` → UNKNOWN `ml_status_unreadable`.
4. `active`, `ok`, `expires_at = now + 7 gün + 1 sn` → OK.
5. `active`, `ok`, `expires_at = now + 7 gün` → WARN `ml_expiring_7d`.
6. `active`, `ok`, `expires_at = now + 3 gün` → WARN `ml_expiring_3d`; `now + 3 gün + 1 sn` → `ml_expiring_7d`.
7. `active`, `ok`, `expires_at = now + 1 gün` → WARN `ml_expiring_1d`; `now + 1 sn` → `ml_expiring_1d`.
8. `active`, `expired` → CRIT `ml_expired`; `overall` CRIT; `ml_expired ∈ IMMEDIATE_CODES`.
9. `active`, `no_model`, `error="PackageError: model suresi dolmus"` → CRIT `ml_no_model`; `detail` hata metnini içerir.
10. `shadow`, `expired` → WARN `ml_shadow_down` (CRIT değil); `shadow`, `no_model` → aynı.
11. `shadow`, `ok`, `expires_at = now + 2 gün` → WARN `ml_expiring_3d`.
12. `active`, `ok`, `expires_at=None` → UNKNOWN `ml_status_invalid`; `mode="turbo"` → UNKNOWN `ml_status_invalid`.
13. Yeniden başlatma gerekli: `active`, `ok`, `expires_at = now + 10 gün`, `model_id="r02@aaaaaaaaaaaa"`, dosya `ok`, `file_model_id="r02@bbbbbbbbbbbb"`, `file_expires_at = now + 20 gün`, `file_gate_passed=True`, `file_user_approved=True` → WARN `ml_restart_needed`. Aynı girdi `file_user_approved=False` → OK (dosya `active` için geçerli değil). Aynı girdi `shadow` ve `file_user_approved=False` → WARN `ml_restart_needed`.
14. En ağır kazanır: 13'teki dosya + `active`, `expired` → CRIT `ml_expired`; `detail` her iki durumu da anar.
15. Dosya geçersiz: `file_state="missing"` (`active`, `ok`, kalan 10 gün) → WARN `ml_file_invalid`; `file_created_at = now + 6 dk` → WARN `ml_file_invalid`; `now + 4 dk` → tetiklemez.
16. Bayat veri (runner düzeyi, `ml_seen` ile): (a) ilk tur, `ml_seen` yok → alarm yok, taban yazıldı; (b) ikinci tur, yeni `file_model_id`, daha yeni `created_at`, **aynı** `data_hash` ve **aynı** `train_end` → WARN `ml_stale_data`; (c) üçüncü tur, yeni paket, farklı `data_hash`, daha ileri `train_end` → OK; (d) yeni paket, farklı `data_hash` ama `train_end` aynı → OK; (e) yeni `file_model_id` ama `created_at` öncekinden eski → WARN `ml_stale_data`; (f) (b)'den sonra dosya değişmeden bir tur daha → WARN sürer.
17. Mutlak yaş: `ml_data_max_age_days=None` iken `created_at − train_end = 220 gün` → tetiklemez; `ml_data_max_age_days=14` iken 15 gün → WARN `ml_stale_data`, 14 gün → tetiklemez.
18. Puanlama hataları: önceki 3, şimdi 5 → WARN `ml_score_errors`; önceki yok, şimdi 5 → tetiklemez; önceki 5, şimdi 0 → tetiklemez ve taban 0 olur; `score_errors=None` → tetiklemez, `detail`de "sayaç okunamadı".
19. Dosya meta okuma (runner): tz'siz `created_at` UTC sayılır; `meta.expires_at = created_at + 40 gün` olan dosyada `file_expires_at = created_at + 21 gün`; `meta.data_snapshot_at` varsa `file_train_end` odur, yoksa `train_window.end`; 32 MB üstü dosya → `unreadable`; dosya okunurken yazılmaz (sha256 önce/sonra aynı).
20. `health.py` içe aktarıldığında `numpy`, `trader_core.ml_package`, `trader_engine` yüklenmiş olmaz (`sys.modules` denetimi).

Uyarı metinleri:

21. `plan_alerts` çıktısındaki Telegram metinlerinde `ml_expired`, `ml_no_model`, `ml_package`, model kimliği ve dosya yolu **geçmez**; 16.5 tablosundaki Türkçe "sorun" cümlesi geçer; düzelince "düzeldi" cümlesi gönderilir.
22. 7 gün eşiğinde uyarı gönderildikten sonra aynı durumda sonraki turlarda §5 kurallarına göre bastırılır; 3 gün eşiğine girildiğinde **yeni** uyarı çıkar; 1 günde yine yeni uyarı.
23. `ml_expired` ilk turda uyarır (IMMEDIATE).

Günlük rapor (`build_report` çıktısı; `status.json` sentetik):

24. `ml` bloğu `null` → çıktıda `🤖 Model filtresi kapalı (bot filtresiz çalışıyor)`.
25. `shadow`, `ok`, kalan 12 gün 5 saat → `🤖 Model gölgede izliyor, kararları etkilemiyor · süresi 12 gün sonra doluyor`.
26. `active`, `ok`, kalan 5 gün 23 saat → `⚠️ Model filtresi açık ama süresi 5 gün sonra doluyor; yenilenmezse yeni işlemler durur`; kalan 20 saat → "… 20 saat sonra doluyor …"; kalan 20 dakika → "… 1 saat sonra doluyor …".
27. `active`, `expired` → `🚨 Modelin süresi doldu: yeni işlem açılmıyor, açık pozisyonlar korunuyor` ve risk satırında "modelin süresi doldu" ("yapay zekâ filtresi hazır değil" değil).
28. `shadow`, `no_model` → `⚠️ Gölgedeki model çalışmıyor (işlemler etkilenmiyor)`; raporda "🛑 Yeni işlemler kapalı" satırı ML yüzünden çıkmaz.
29. Sağlık durumunda `ml_restart_needed` varken satırın sonunda " · yeni model hazır, motorun yeniden başlatılması gerekiyor".
30. Rapor metninde `expired`, `no_model`, `shadow`, `active`, `model_id` değeri ve İngilizce alan adı geçmez; `ml` bloğu bozuk tipteyse (ör. dizi) rapor çökmeden üretilir ve "Bazı bilgiler okunamadı" satırı çıkar.

Sapma kancası:

31. `drift_check_enabled=False` → `drift_monitor:learner` SKIPPED `placeholder`; `overall` etkilenmez.
32. Açıkken: dosya yok → WARN `drift_missing`; `generated_at = now − 36 sa` → OK; `now − 36 sa − 1 sn` → WARN `drift_stale`; `overall="UYARI"` → WARN `drift_alert`; `"IZLE"` / `"YETERSIZ"` / `"OK"` → OK; `overall="CRIT"` (bilinmeyen) → WARN `drift_unreadable`.
33. 32'deki hiçbir girdide sonuç CRIT ya da UNKNOWN olmaz ve nabız kararı (`should_send_ok`) bu kontrol yüzünden değişmez.

### 16.8 Kapsam dışı / açık noktalar

- Motorun paketi çalışırken yeniden yüklemesi (yeniden başlatma gereksinimini kaldırır) ayrı bir motor işidir; bu ek onu gerektirmez, yalnız görünür kılar.
- `meta.data_snapshot_at` alanı (§16.4) r04+ şablonuna kadar yoktur; o zamana dek soy kontrolü `data_hash` + `train_window.end` ile sınırlıdır.
- Veto dosyası ve rejim girdileri için aynı soy kontrolü (B-25'in kalanı) ve "her açık pozisyonun güncel veto/rejim girdisi var mı" kontrolü bu ekte yoktur; ayrı iş.
- Strateji parametre sürümünün yaşı (D-06'nın ikinci yarısı) için eşik konmadı: ders servisi değişikliği zorunlu değildir, yaş tek başına sorun göstermez.


## 17. DD-9 ekleri: hesap modu alarmı, canlı kip, yol tutarlılığı

- **`account_mode:<bot>`** (yalnız `_live_mode`: `has_exchange` ya da `mode ∈ {testnet, live}` ya da `expect_exchange`): `status.exchange.account_mode = {drift, unverified, unverified_ban}` sayaçlarının tur başına **artışı** değerlendirilir (süreç yeniden başlamışsa şimdiki değer artış sayılır). `drift` artışı ≥ 1 → CRIT `account_mode_drift` (anında); `unverified − unverified_ban` artışı ≥ 1 → WARN `account_mode_unverified` (anında; yasak kaynaklı doğrulanamama sayılmaz); sayaçlar okunamıyorsa UNKNOWN `account_mode_unknown`. Önceki tur değerleri durum dosyasında `account_mode` anahtarıyla saklanır. `ApiProbe`: `acct_drift`, `acct_unverified`, `expect_exchange`; `HealthSnapshot`: `prev_account_mode`, `live_path_issues`.
- **Canlı kip yapılandırmadan türetilir:** `LIVE_BOTS` içindeki botlar ve `learner@testnet` gölge yoklaması `expect_exchange=True` ile kurulur (durum dosyası okunamasa da `naked_position`, `exchange_reachable`, `account_mode` üretilir; `exchange_ban` açık pozisyonu bilinmiyorsa var sayar → CRIT `exchange_ban_open_positions`).
- **`live_paths`** (yalnız `LIVE_BOTS` doluyken): `check_against_config(env, ENGINE_CONFIG_DIR)` + `status_mode_mismatch:<bot>`; boş → OK; aksi CRIT `live_paths_mismatch` (anında).
- **Sapma izleyicisi:** `LIVE_BOTS` içindeki bot için `drift_monitor:<bot>` üretilmez (canlı yol desteği ayrı paket); kâğıt botlar değişmez.
- Canlı bot `LIVE_VAR_DIR` altından izlenir; disk yoklamasına `LIVE_VAR_DIR` eklenir; yedek `ledger_<bot>@live.sqlite` ve `state_<bot>@live.sqlite` dosyalarını da alır (`health_backup`).
