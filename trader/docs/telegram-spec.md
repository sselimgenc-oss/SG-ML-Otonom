# Telegram: bildirim, komut ve günlük rapor — arayüz ve kurallar (spesifikasyon v2, 16 Kasım 2026 — mentor kararları işlendi)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. Veto ve ikiz ile ilgili bildirimler/komutlar kaldırıldı (LLM veto yok, ikiz yok); ders/ML bildirimleri ilk işlemden etkin.

Plan maddesi 18. Bu belge kod, test ve commit içermez; testler bu belgeden yazılır. Gerçekleme: `src/trader_core/telegram.py`, `scripts/telegram_run.py`, `deploy/trader-telegram*`. Biçim `saglik-spec.md` ile aynıdır; çelişkide `ders-spec.md`, `saglik-spec.md`, `motor/05-engine-runner.md` §8 geçerlidir. Her belirsizlikte **fail-closed** (yetki, onay, kod doğrulaması) ama **ticareti asla bloke etmez**: Telegram modülü ne motor ne defter ne risk yoluna girer.

## Mentor kararları (bağlayıcı; gövde bunlara göre yazılmıştır)

1. **KILL yalnız Faz A'da.** `/durdur` = "desteklenmiyor" yanıtı (yalnız-giriş-durdur/PAUSE canlıya geçmeden önce yeniden ele alınır; `trader_engine` değişmez).
2. **`/devam` iki adımlıdır** (`/devam` → 4 haneli kod → kod yanıtı) ve `kill_state == "exiting"` iken **reddedilir** (pozisyonlar kapanmadan giriş açılmaz).
3. **Ders onayı alt süreçle:** yeni `lesson_run.py --resolve <id> --approve|--reject` `lesson.lock`'u alır; **daemon ders defterini hiç açmaz**.
4. **Yalnız özel sohbet.** Grup ve `TELEGRAM_USER_IDS` yolları kaldırıldı.
5. **Tek chat kimliği** (`TELEGRAM_CHAT_ID`), yetki ayrımı yok.
6. **Bayatlık penceresi 120 sn; onay kodu TTL 120 sn; kod 4 haneli sayısal.**
7. **Kaçırılan 21:00 raporu:** 23:30'a kadar "gecikmiş" etiketiyle geç gönderilir, sonra atlanır; kesimi **betik uygular** (`Persistent=true` tek başına yetmez).
8. **`trader-health-fail@`** doğrudan `telegram_run.py send` ile gönderir, daemon üzerinden değil; dış nabız Telegram'dan bağımsız kalır.
9. **Canlı kipte `/devam`** yalnız `KILL` `telegram:*` tarafından `reason=user_cmd` ile kurulmuşsa **ve** durum `flat` ise serbest; başka kökenli her KILL yalnız sunucuda kaldırılır.
10. **Yeni bot, yeni token** (CT'nin token'ı paylaşılmaz).

Zorunlu düzeltmeler: (a) kapatma onayı **yalnız 4 haneli kodun düz yanıtıdır** (`/onay KOD` yok: `/onayla`'ya fazla benzer); (b) `TelegramClient` `answer_callback_query` ve `edit_message_text` içerir, callback bayatlığı `expires_at` ile denetlenir; (c) satır içi "onayla" düğmesi ikinci bir "Emin misin?" adımı ister, "reddet" tek dokunuştur; (d) `dedup_key` zorunludur (onaylarda `request_id`) ve spool ile doğrudan gönderim arasında uygulanır (çift teslim yok); (e) izinler: ortak grup + kipler (Bölüm 7, 8).

## 0. Kaynaklar (CT `copytrade/canli/telegram.py`; yalnızca okundu, içe aktarılmadı, çalıştırılmadı)

| CT parçası | Karar | Bizde |
|---|---|---|
| Bot API'ye doğrudan HTTPS, enjekte edilebilir `post(url, json)` | **Fikir alınır** (kod bağımlılığı yok; python-telegram-bot yok) | `requests` + enjekte edilebilir `http_post` (testte sahte sunucu) |
| Token/chat yalnız ortamdan; yoksa kanal kapalı, motor çökmez | Alınır | Bölüm 7 |
| `yetkili_mi`: `chat.id == chat_id` zorunlu; özel sohbette ek `from.id == chat_id` | **Alınır**, grup yolu atılır (karar 4) | Bölüm 3 (tek kimlik, yalnız özel sohbet) |
| Eski komut yürütülmez (motor başlamadan önce ya da > 15 dk), "İŞLENMEDİ" yanıtı | Alınır; **bizde sıkılaşır**: pencere 120 sn, onay kodu TTL 120 sn | Bölüm 4.2 |
| Kalıcı `offset`, yürütme bitince onay | Alınır | Bölüm 4.1 |
| Önemli mesajda 2/5/15 sn yeniden deneme + 429 `retry_after` | Alınır | Bölüm 2.2 |
| `/dur /devam /kapat /durum` | Adlar bizim kararlarla değişir (Bölüm 5) | Bölüm 5 |
| `msg_*` TR biçimleyicileri (`tr_sayi`, `tr_yuzde`, tek ikon başlığı) | Fikir alınır, kod kopyalanmaz | Bölüm 6 |

## 1. Süreç ve modül düzeni

Tek modül `src/trader_core/telegram.py` (yalnız standart kütüphane + `requests`; `trader_engine` yalnız `Killswitch`/`fileio` için içe aktarılır). Süreçler ve yazma sahipliği:

| Parça | Süreç | Yazdığı |
|---|---|---|
| `TelegramClient` (ham Bot API: `send_message`, `get_updates`, `answer_callback_query`, `edit_message_text`) | kütüphane | — |
| `TelegramNotifier` (outbound; `NOTIFIER_FACTORIES["telegram"]` ve health `Notifier` olarak kaydolur) | çağıran süreçte (ders/health/veto/bütçe tek seferlik süreçleri) | `var/telegram/outbox/` (spool) |
| `scripts/telegram_run.py daemon` (komut dinleyici + outbox boşaltıcı) | **tek** uzun ömürlü süreç, `trader-telegram.service` | `var/telegram/{offset.json,pending.json,audit.jsonl,alive.json}`, `shared/KILL` (yalnız Bölüm 5); ders onayı için **alt süreç** (Bölüm 5.3) |
| `scripts/telegram_run.py report` (günlük rapor) | tek seferlik, `trader-telegram-report.timer` 21:00 `Europe/Istanbul` | outbox, `last_report.json` |
| `scripts/telegram_run.py send` (doğrudan tek mesaj; `trader-health-fail@` kullanır) | tek seferlik | outbox |

Neden ayrı daemon: `getUpdates` tek tüketici ister (iki süreç aynı bot için aynı anda poll ederse 409 döner). Tek seferlik süreçler (ders, health) yalnız **gönderir**; poll yalnız daemon'dadır. Bütçe ve veto olayları `budget.pending_events()` (at-least-once) ile daemon'un outbox döngüsünden çekilir; başarılı gönderimden sonra `ack_events` (butce-spec §10).

## 2. Giden mesaj API'si

### 2.1 Arayüz

```
Severity: INFO | WARN | CRIT
class TelegramNotifier:
    def send(self, alert: health.Alert) -> bool                 # saglik-spec §5 (Notifier)
    def notify(self, notice: lesson.LessonNotice) -> bool       # LessonNotifier
    def request_approval(self, req: lesson.ApprovalRequest) -> bool   # LessonNotifier
    def send_text(self, text: str, severity: Severity, dedup_key: str) -> bool   # veto/bütçe/rapor; dedup_key ZORUNLU
```
Dönüş kuralı (ders-spec Revizyon 3 ile aynı): **`True` yalnız Telegram `ok:true` ve `message_id` döndürdüyse.** Disk spool'una yazmak `False`'tur (çağıran yeniden dener / `undelivered` kalır). İstisna asla fırlatılmaz. `dedup_key` her gönderimde zorunludur: `Alert` ve `LessonNotice` için `fingerprint`, onay talebi için `request_id`, `send` CLI için `--dedup-key`; anahtarsız çağrı `ValueError` (programlama hatası, süreç yolunu etkilemez: notifier dışarıya `False` döner). `build_notifier(cfg, env)` fabrikası: token/chat eksikse `None` döner (çağıran bunu başarısızlık sayar; ders servisi çıkış 1). `ApprovalRequest` mesajı: başlık, `param from→to`, `reason_code`, kanıt özeti, `expires_at`, ve satır içi komutlar `/onayla <request_id>` / `/reddet <request_id>`; ayrıca inline düğmeler (Bölüm 5.3; `callback_data` içinde `expires_at` taşınır).

### 2.2 Gönderim kuralları

- Uç nokta: `https://api.telegram.org/bot<TOKEN>/sendMessage`, `disable_web_page_preview=true`, **`parse_mode` yok** (düz metin; Markdown kaçış hatası mesajı düşürmesin). Zaman aşımı bağlantı 5 sn / okuma 10 sn.
- Yeniden deneme: ağ hatası/5xx → 2, 5, 15 sn; `429` → `parameters.retry_after` (tavan 60 sn). `400/401/403` (kalıcı) → yeniden deneme yok, `False`, `CRIT` günlük satırı (token iptal/yanlış chat). Tek `send` çağrısı toplam ≤ 30 sn; ders/health süreçlerini asılı bırakmaz.
- Hız sınırı: kanal başına ≤ 1 mesaj/sn, ≤ 15 mesaj/dk (Telegram sınırının altı); aşan `INFO` mesajlar tek "N mesaj birleştirildi" özetine toplanır; `CRIT` birleştirilmez, sıraya girer. **Aynı `dedup_key` bir kez teslim edilir** (varsayılan pencere 10 dk; onay talebinde `expires_at`'a kadar): teslim edilen anahtar `var/telegram/outbox/sent/<sha16>` işaretiyle kaydedilir ve hem doğrudan gönderim hem spool boşaltma teslimden önce bu işarete ve bekleyen spool dosyasına bakar; spool'da aynı anahtar ikinci dosya olmaz. Böylece health `revert_failed_alerts` yeniden denemesi ya da ders `undelivered` yeniden denemesi çift mesaj üretmez.
- Boyut: Telegram sınırı 4096 karakter; bizim sınırımız **3500**. Aşan mesaj son satırda "(kısaltıldı, N satır)" ile kesilir; kesme satır sınırında yapılır, onay kodu/komut satırı asla kesilmez (gövde kısalır, komut satırı sona sabitlenir).
- Sır/biçim: gövde `scrub()` (ders-spec) ve `sanitize_text` ile geçer; token, HMAC anahtarı, API anahtarı, tam yol metinde olmaz. Kullanıcı kaynaklı metin (LLM gerekçesi dahil) komut gibi görünen `/` ile başlayan satırlarda başına boşluk eklenerek etkisizleştirilir.
- Sessizlik: `INFO` `disable_notification=true`; `WARN`/`CRIT` sesli. Gece saat dilimi: bildirim kuralı yoktur (CRIT her zaman sesli).

### 2.3 Telegram kapalıyken (spool)

Gönderim `False` ise (ağ, 5xx, 429 süresi aşıldı) mesaj `var/telegram/outbox/<utc_ns>-<sha8>.json` olarak **atomik** yazılır (`fileio.atomic_write_json`; mod 0660, dizin 2770 `trader:trader-tg`; ders/health süreçleri yalnız bu dizine yazar — Bölüm 7/8). Daemon her 30 sn outbox'ı eski→yeni sırayla boşaltır; başarılı gönderilen dosya silinir. Sınırlar: ≤ 500 dosya / ≤ 5 MiB; aşılırsa en eski `INFO` düşer, sonra `WARN`; `CRIT` düşmez (sayaç `dropped` raporda). 24 saatten eski `INFO` spool'dan atılır; `CRIT`/onay talepleri yaşar (onay talebi kendi `expires_at`'ında süresi dolmuş olarak işaretlenir ve gönderilmez). Spool yazılamıyorsa (disk dolu) yalnız günlük (journal) satırı; **hiçbir durumda istisna ya da bekleme motor/ders/health yoluna sızmaz** — motor Telegram'ı hiç içe aktarmaz.

## 3. Yetkilendirme

- `TELEGRAM_CHAT_ID` (**tek** tam sayı; yetki ayrımı yok, karar 5). Boş/eksik → komut kanalı **kapalı** (yalnız giden mesaj mümkünse), daemon "komut kapalı" açılış satırı yazar. `TELEGRAM_CHAT_IDS`/`TELEGRAM_USER_IDS` **yoktur**.
- Kabul (karar 4): `message.chat.type == "private"` **ve** `message.chat.id == TELEGRAM_CHAT_ID` **ve** `message.from.id == chat.id` **ve** `from.is_bot` değil. `callback_query` için aynı kontrol `callback_query.from.id` + `callback_query.message.chat` üzerinden. Grup/kanal/süper grup sohbetleri her zaman reddedilir.
- Diğer her güncelleme: **yanıtsız yok sayılır** (kaçak bilgi yok, bot varlığı doğrulanmaz) ve `audit.jsonl`'a `{event:"unauthorized", chat_tail, update_id, cmd:ilk 20 karakter}` yazılır; tam kimlik/metin yazılmaz. Dakikada > 10 yetkisiz güncelleme → tek `WARN` (kullanıcıya) "yetkisiz komut denemesi" (hız sınırlı).
- `allowed_updates=["message","callback_query"]`; `edited_message`, kanal, inline sorgu ve diğerleri hiç alınmaz.
- Kimlik değerleri günlükte yalnız son 3 hane ile görünür.

## 4. Gelen komut döngüsü

### 4.1 Long polling (webhook yok, açık port yok)

`getUpdates(offset, timeout=30, allowed_updates=…)`, istemci okuma zaman aşımı 40 sn. Dış bağlantı yalnız `api.telegram.org:443` (giden). Döngü hatasında üstel bekleme 1→60 sn (tavan), `409 Conflict` (başka poller) → `CRIT` günlük + 60 sn bekle. `offset` = son işlenen `update_id + 1`, `var/telegram/offset.json`'a **komut yürütüldükten ve audit yazıldıktan sonra** atomik yazılır (yürütme çökmesi → aynı update yeniden gelir; komutlar idempotenttir, Bölüm 5). Aynı `update_id` (yeniden başlatma/yeniden teslim) bellekte ve `audit.jsonl` son 1000 satırında bakılarak ikinci kez **yürütülmez**. Telegram yalnız son 24 saatin güncellemelerini saklar; daemon uzun süre kapalı kaldıysa ilk turda gelenler "bayat" sayılır (4.2).

### 4.2 Bayatlık

`message.date` ile şimdi arasındaki fark > **120 sn** ya da mesaj daemon başlangıcından önceyse: **hiçbir komut yürütülmez**; tek yanıt "işlenmedi, yeniden gönder (yaş: N sn)". Bu kural kod yanıtı için de geçerlidir (4.3 sürelerinden bağımsız ek sınır). **Callback sorgularında** `message.date` kullanılmaz (düğme eski mesajdadır): bayatlık `callback_data` içindeki `expires_at` ile denetlenir; süresi geçmiş düğme "süresi doldu" yanıtı alır ve mesajdan düğmeler kaldırılır.

### 4.3 Onay durumu

`var/telegram/pending.json` (atomik): `{token_hash, salt, action, chat_id, created_at, expires_at}` kaydı (`action ∈ {kill, devam}`; aynı anda **tek** bekleyen onay, yenisi eskiyi geçersiz kılar); kod düz metin saklanmaz (SHA-256 + tuz, sabit-zamanlı karşılaştırma). Süresi dolmuş kayıtlar her turda temizlenir. Yeniden başlatma sonrası **yaşar** (TTL'i dolmadıysa), böylece kod gönderilmiş ama süreç yeniden başlamışsa yine geçerli kalır; ancak bayat güncelleme kuralı (4.2) geçerliliğini korur.

## 5. Komutlar

Komut adı = ilk sözcük (küçük harf, `@botadı` eki atılır); bilinmeyen komut → geçerli komut listesi yanıtı. Tüm yürütmeler `audit.jsonl`'a (`update_id`, `cmd`, `sonuç`, `ts`) yazılır; **Telegram'dan gelen hiçbir metin emir, pozisyon, risk ya da parametre değeri olarak yorumlanmaz** (`/onayla` yalnız ders servisinin kendi `request_id`'sini çözer).

| Komut | Etki | Onay |
|---|---|---|
| `/yardim` | komut listesi | yok |
| `/durum` | Bölüm 6.2 kısa durum (status.json, salt okunur) + `kill` durumu | yok |
| `/rapor` | günlük raporu şimdi üretir (Bölüm 6) | yok |
| `/hepsini_kapat` | killswitch'i **kurar** (Bölüm 5.1) | 2 adım (4 haneli kod) |
| `/devam` | `shared/KILL`'i **kaldırır** (Bölüm 5.2) | 2 adım (`/devam` → kod); `exiting`'de reddedilir |
| `/onayla <id>` · `/reddet <id>` | `lesson_run.py --resolve <id> --approve|--reject` alt süreci (5.3) | id doğrulaması |
| `/durdur` | **"desteklenmiyor"** (aşağı) | — |

**`/durdur`:** mevcut `Killswitch` yalnız `set/clear` sunar ve etkin iken motor açık pozisyonları da `force_exit` eder (05 §8.1). "Girişleri durdur ama pozisyonları tut" yeni bir mekanizma (`PAUSE`) gerektirir; **karar 1: Faz A'da yalnız KILL**, `/durdur` "desteklenmiyor, tam kapatma için /hepsini_kapat" yanıtı verir; canlıya geçmeden önce yeniden ele alınır.

### 5.1 `/hepsini_kapat` iki adımlı onay

1. Yetkili kullanıcı `/hepsini_kapat` yazar (ya da "hepsini kapat" metni; boşluk/büyük-küçük harf ve `ı` farkı normalize edilir; **yalnız tam eşleşme**, cümle içinde geçerse yürütülmez).
2. Daemon rastgele **4 haneli sayısal kod** üretir (`secrets.randbelow(10000)`, başı sıfırlı), mesaj: "Tüm pozisyonlar piyasadan kapatılacak ve yeni giriş durdurulacak. Onay için 120 sn içinde yalnız şu 4 haneli kodu yanıtla: KOD". Kod `pending.json`'a yazılır (TTL **120 sn**, tek kullanımlık, yalnız aynı `chat_id`'den). Onay **yalnız çıplak kod mesajıdır** (`^\d{4}$`); `/onay KOD` gibi komut biçimi yoktur (`/onayla` ile karışmasın).
3. Bekleyen `kill` kaydı varken gelen doğru kod ve TTL içinde: `Killswitch(path=cfg.kill_file).set(by="telegram:<son3>", reason="user_cmd")` çağrılır (**tek yol**: motorun izlediği dosya; yeni iptal/kapatma kodu yok). Yanıt: "KILL kuruldu; motor pozisyonları kapatıyor". Yanlış kod → kayıt silinir (tek deneme), "iptal" yanıtı; süre dolarsa "süre doldu, yeniden başlat". Bekleyen kayıt yokken gelen 4 haneli sayı: "bekleyen onay yok" (hiçbir şey yürütülmez).
4. Sonuç doğrulama: 10 sn sonra `status.json`'dan `kill` ve `kill_state` okunur; 5 dk içinde `kill_state != "flat"` ise `CRIT` "kapatma tamamlanmadı". Daemon pozisyon kapatmaz; yalnız dosyayı kurar ve izler.
5. Yeniden `/hepsini_kapat` zaten etkinken: idempotent "KILL zaten etkin (<kim>, <ne zaman>)" yanıtı.

**Telegram çökmüşken** durdurma yolu: operatör sunucuda `python -m trader_engine kill --by me --reason manual` çalıştırır ya da `shared/KILL` dosyasını elle yazar (05 §9). Telegram'a bağımlılık yoktur.

### 5.2 `/devam` iki adımlı (karar 2, 9)

> **DD-9 notu (O7):** `kill_state == "flat"` şartı **her kipte** aranır (`paper` dahil; eksik/yanlış tipte değer = flat değil → ret). `TelegramDaemon(expect_status_mode=...)` verilmişse (`LIVE_BOTS` doluyken `"live"`) durum dosyasının `mode`u eşit değilse ret ("beklenen kipte değil"). Canlıdan sonra `KILL_FILE` canlı motorun dosyasıdır; kâğıt ikizin `shared/KILL`ine Telegram dokunmaz.

1. `/devam` → ön koşullar denetlenir (aşağı); geçerse `kill`'e benzer biçimde 4 haneli kod üretilir (`action="devam"`, TTL 120 sn).
2. Çıplak kod yanıtı → ön koşullar **yeniden** denetlenir; geçerse `Killswitch.clear()`.

Ön koşullar (hepsi sağlanmalı, aksi halde reddedilir; `status.json` okunamıyorsa fail-closed reddedilir): KILL etkin olmalı (değilse "KILL etkin değil" no-op yanıtı); `kill_state != "exiting"` (**pozisyonlar kapanırken reddedilir**, "kapanış sürüyor, bekleyin"); **canlı kipte** (`status.json.mode == "live"` ya da bilinmiyor) ek olarak: `KILL` içeriği `by` `telegram:` ile başlar **ve** `reason == "user_cmd"` **ve** `kill_state == "flat"` olmalı; başka kökenli KILL için yanıt: "Bu KILL Telegram'dan kurulmadı; yalnız sunucuda kaldırılır" (karar 9). Paper kipinde köken sınırı yoktur (yalnız `exiting` reddi).

### 5.3 Ders önerileri (alt süreç; karar 3)

`ApprovalRequest.request_id` (`lr-<gün>-<proposal_id>`) mesajda görünür. `/onayla <id>`/`/reddet <id>`: id biçimi `^lr-\d{4}-\d{2}-\d{2}-\d+$` değilse reddedilir. **Daemon ders defterini açmaz**: `python -I scripts/lesson_run.py --resolve <id> --approve|--reject` alt süreci başlatılır (zaman aşımı 60 sn; ortamdan `TELEGRAM_BOT_TOKEN` çıkarılır). `--resolve` `lesson.lock`'u alır, `LessonService.resolve_request(id, approve, actor_ref="telegram")` çağırır, tek satır JSON yazar (`{"status","code","message","request_id"}`; çıkış 0 = çözüldü/bilinen durum, 1 = kullanım/yapılandırma, 2 = hata/kilit alınamadı). Daemon `status`'u ayrı yanıtla bildirir (süresi dolmuş/bayat/bilinmeyen; çift onay idempotent).

Satır içi düğmeler: `callback_data` = `<eylem>:<request_id>:<expires_at_epoch>` (≤ 64 bayt). `ok:` (onayla) **tek dokunuşla yürütülmez**: mesaj `edit_message_text` ile "Emin misin? <param from→to>" olarak düzenlenir ve `ev:` (evet, onayla) / `vz:` (vazgeç) düğmeleri gösterilir; `ev:` aynı alt süreci `--approve` ile çağırır, `vz:` özgün mesajı geri yükler. `no:` (reddet) **tek dokunuş**. Her `callback_query` `answer_callback_query` ile yanıtlanır (düğme dönme göstergesi kapanır); süre `expires_at_epoch`'a göre denetlenir (4.2). Sonuç mesajı `edit_message_text` ile yazılır, düğmeler kaldırılır. `/onayla` metin komutu tek adımdır (id'yi elle yazmak kasıtlıdır) ama `expires_at` geçmişse ders servisi `expired` döner. Bekleyen öneri sayısı `/durum`'da görünür.

## 6. Günlük rapor (21:00 Europe/Istanbul)

### 6.1 Zamanlama
`trader-telegram-report.timer`: `OnCalendar=*-*-* 21:00:00 Europe/Istanbul`, `Persistent=true` (kaçırılırsa açılışta bir kez çalışır) **ama kesimi betik uygular** (karar 7): `telegram_run.py report` zamanlanmış an = en son 21:00 İstanbul; gecikme ≤ 10 dk ise normal, 10 dk–23:30 arası **"gecikmiş"** etiketiyle gönderilir, 23:30'dan sonra (aynı İstanbul günü) ya da önceki günün raporu için gecikme 2,5 saati aşıyorsa **gönderilmez** (günlüğe "atlandı"; çıkış 0). Rapor günü = İstanbul takvim günü; `report` aynı `dedup_key` (`report-<gün>`) ile spool/doğrudan çift teslimi de engeller; veri sınırları UTC'ye çevrilerek sorgulanır (butce-spec: 21:00 TR = 18:00 UTC aynı UTC günü). Aynı gün ikinci kez üretilmez (`var/telegram/last_report.json` gün anahtarı; `/rapor` bunu etkilemez, "(manuel)" etiketlenir).

### 6.2 İçerik (salt okunur; yeni sayı hesaplanmaz, defter/status'ın verdiği gösterilir)
1. Başlık: kip (`paper`/`live`), gün, strateji adı@sürüm, `param_version_id`.
2. **Motor (`status.json`, `engine-status/1`)**: `loop_at` yaşı, `entries_open`, `gate.code`, `kill`/`kill_state`, `entries_blocked_reason`, `equity`, `day_start_equity`, günlük getiri %, açık pozisyonlar (pair, yön, giriş, stop; ≤ 10 satır, fazlası "+N"), `counters` içinde sıfır olmayanlar.
3. **Defter (`ledger_learner`, `ledger_twin` salt okunur)**: günün kapanan işlemleri (adet, kazanan/kaybeden, toplam R, ücret+funding), açılan işlemler, günün karar olayları dökümü (`entered`/`skipped`/`blocked` ve `skip_reason` sayıları), ikiz ile fark (varsa).
4. **Veto/bütçe**: `budget.status()` (gün/ay harcama / sınır, `prices_verified=False` ise "fiyatlar doğrulanmadı"), engellenen sinyal sayısı, `lesson_skipped_budget` varsa tek satır.
5. **Sağlık**: `health` durum dosyasının son `overall`, başarısız kontroller (≤ 5), yedek durumu, spool bekleyen sayısı (Telegram outbox dahil).
6. **Ders**: bekleyen/yeni öneriler (`request_id`, süre), son uygulanan sürüm, geri alma izleyici durumu.

Salt okunur kaynak okunamazsa o bölüm "okunamadı: <kod>" satırı olur (rapor yine gönderilir; boş rapor göndermek yerine eksik rapor tercih edilir). `status.json` yaşı > 120 sn ise raporun ilk satırı `CRIT` "motor kalp atışı yok". Rapor yine 3500 karakter sınırına tabidir; aşarsa 2. mesaja bölünür (ders ve sağlık bölümleri ayrı mesaj).

### 6.3 Anlık uyarı kaynakları
Sağlık `plan_alerts` çıktısı (debounce/düzeldi dahil), bütçe `pending_events()` (%70/%100), veto `veto_blocked`/`stale` seli özeti, ders bildirimleri ve onay talepleri, `KILL` kurulması/kalkması, motor `counters` artışı (`ledger_errors`, `unknown_orders`) ve `kill_state` geçişleri. Her birinin seviyesi kendi spec'indedir; Telegram yalnız taşır.

## 7. Sırlar ve izinler

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` yalnız `/etc/trader-telegram.env` (systemd `EnvironmentFile`; satır kuralları `saglik-spec` §8.3: yorum yok değerde, tırnak yok). **İzin (karar/düzeltme e):** dosya **0640 `root:trader-tg`**; `trader-tg` ortak grubuna daemon, ders ve health/health-fail süreçleri üye/`SupplementaryGroups=trader-tg` ile girer (0600 root-only olsaydı `User=trader` ders servisi okuyamazdı). Depoda yalnız değersiz `deploy/trader-telegram.env.example`. Diğer servislerin env dosyalarına **aynı token kopyalanmaz**: ortak dosya ikinci `EnvironmentFile=` olarak okunur (tek kaynak, tek rotasyon).
- Spool: `var/telegram/outbox/` mod **2770 `trader:trader-tg`** (setgid), dosyalar 0660; ders/health süreçleri yalnız buraya yazar. `offset/pending/audit/alive/last_report` yalnız daemon/rapor tarafından yazılır (0640).
- Token hiçbir günlükte, hata iletisinde, spool dosyasında, `audit.jsonl`'da ya da istisna metninde bulunmaz; URL'ler günlüğe `…/bot<gizli>/…` olarak yazılır (`requests` istisna metni token içeren URL taşır: **yakalanıp** maskelenir, `__cause__` zinciri basılmaz). Komut satırına token konmaz; ders alt sürecine token verilmez.
- Token sızarsa: BotFather `/revoke`, env güncelle, daemon yeniden başlat. Yetkisiz kimlik toplu hatası token ihlali belirtisi sayılır (Bölüm 3'teki `WARN`).
- Yeni bot, yeni token (karar 10).

## 8. systemd

`deploy/trader-telegram.service` (`Type=simple`, `Restart=always`, `RestartSec=5`, `User=trader`, `SupplementaryGroups=trader-tg`, `EnvironmentFile=/etc/trader-telegram.env`, `ExecStart=/usr/bin/python3 -I /opt/trader/scripts/telegram_run.py daemon`, `After=network-online.target`, `OnFailure=trader-health-fail@%n.service`, `MemoryMax=96M`, `CPUQuota=10%`, `Nice=10`, `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=read-only`). **`ReadWritePaths` (düzeltme e):** `/opt/trader/var/telegram /opt/trader/shared` **ve** ders alt süreci miras aldığı için ders defteri `lesson.sqlite{,-wal,-shm,.fallback.jsonl}`, **öğrenen defteri** `ledger_learner.sqlite{,-wal,-shm}` ve **`lesson.lock`** (ders birimiyle aynı liste; `-` öneki), bütçe `budget.sqlite*` (olay `ack`); ikiz defter ve `var/<bot>/status.json` `ReadOnlyPaths`. Daemon'un kendisi ders defterini açmaz; yazma izni yalnız `--resolve` alt süreci içindir.

`deploy/trader-telegram-report.{service,timer}` tek seferlik rapor (`User=trader`, `SupplementaryGroups=trader-tg`, salt okunur defter/status, yazma yalnız `var/telegram`). `trader-health-fail@.service` Telegram'a bağlanırken **daemon'a bağımlı olmaz**: `telegram_run.py send --severity CRIT --dedup-key health-fail:%i "<metin>"` (doğrudan, tek seferlik, spool'lu); mevcut `health_fail.sh` (logger + `HEARTBEAT_FAIL_URL`) **bağımsız dış nabız** olarak aynen kalır. Daemon sağlığı: `var/telegram/alive.json` (30 sn'de bir zaman damgası) `health_run`'a yeni kontrol olarak eklenir (ayrı iş; `telegram_daemon_stale`, WARN).

## 9. Kurallar özeti

1. Yetkisiz ⇒ sessiz yok sayma + audit. 2. Her yıkıcı komut iki adım + TTL (120 sn) + tek kullanım; kod çıplak 4 haneli yanıttır. 3. Telegram arıza ⇒ spool; ticaret etkilenmez. 4. Kapatma = `Killswitch.set` (tek yol). 5. Metinden değer çıkarılmaz. 6. Token yalnız env.

## 10. Test planı (`tests/test_telegram_*.py`; ağ yok)

Sahte Telegram sunucusu: `http_post` enjeksiyonu ya da yerel `http.server` (`127.0.0.1`, rastgele port) ile `sendMessage`/`getUpdates` yanıtları ve hata kipleri (429+`retry_after`, 5xx, kopan bağlantı, `ok:false`). Saat enjekte edilir; `time.sleep` enjekte edilir.

- Giden: `dedup_key` zorunlu; spool+doğrudan çift teslim yok; `True` yalnız `ok:true`+`message_id`; spool'a düşüş `False`; yeniden deneme çizelgesi (2/5/15, `retry_after` tavanı); kalıcı 400/401/403'te yeniden deneme yok; 3500 sınırı ve komut satırı korunumu; hız sınırı ve `INFO` birleştirme, `CRIT` birleştirilmez; `dedup_key`; token hiçbir çıktıda yok (istisna zinciri dahil, `grep` benzeri tarama); `build_notifier` token yokken `None`; `NullNotifier` ile ders/health sözleşme testleri.
- Spool: atomik yazım, sıra, 500/5 MiB sınırında düşme önceliği (`CRIT` düşmez), süresi dolan onay talebinin gönderilmemesi, Telegram dönünce boşaltma, süreç öldürülünce dosya bütünlüğü.
- Yetki: yabancı `chat.id` ⇒ yanıt yok + audit, yürütme yok; doğru kimlik ama grup sohbeti ⇒ ret; doğru chat yanlış `from.id`; `is_bot`; `edited_message`/kanal gönderisi yok sayılır; yetkisiz seli ⇒ tek `WARN`; audit'te tam kimlik yok.
- Polling: aynı `update_id` iki kez ⇒ tek yürütme (yeniden başlatma dahil); `offset` yalnız yürütme+audit sonrası ilerler (yürütmede çökme ⇒ yeniden teslim, idempotent sonuç); 409 davranışı; bayat (> 120 sn) ve başlangıçtan eski komut yürütülmez, "işlenmedi" yanıtı alır (her update bir kez).
- `/hepsini_kapat`: tek adımda kill yok; doğru kod ⇒ `Killswitch.set` (dosya içeriği `by/reason`), yanlış kod ⇒ iptal ve yeniden başlamak gerekir, **TTL 120 sn sonunda kod geçersiz** (sınır: 119/120/121 sn), `/onay KOD` biçimi kabul edilmez, kod tek kullanımlık, başka chat'ten kod, "hepsini kapat" metni normalizasyonu ve cümle içinde yürütülmemesi, kill zaten etkin ⇒ idempotent, `pending.json` yeniden başlatmadan sonra TTL içinde geçerli / sonra geçersiz, kod düz metin saklanmaz, Telegram tamamen kapalıyken `Killswitch.set` yerel yolu (daemon yokken) engelsiz, `kill_state` flat olmazsa `CRIT`.
- `/devam`: kod + `clear`; kill yokken no-op yanıtı; `exiting` ⇒ ret; canlıda `telegram:*`+`user_cmd`+`flat` dışı ⇒ ret; `/durdur` ⇒ "desteklenmiyor".
- `/onayla`/`/reddet`: sahte alt süreç (`runner`) ile her `ResolveResult.status`; satır içi `ok:` ⇒ "Emin misin?" (yürütme yok), `ev:` ⇒ yürütme, `no:` tek dokunuş, `expires_at` geçmiş düğme ⇒ ret; `answer_callback_query`/`edit_message_text` çağrıları; daemon hiçbir zaman `LessonService` içe aktarıp çağırmaz, bozuk id biçimi, süresi dolmuş, çift onay idempotent, callback düğmesi aynı yol; `/onayla` metinden başka hiçbir değer taşımaz (enjeksiyon: `/onayla lr-…; DROP` reddi).
- Rapor: golden metin (sabit `status.json` + sahte defter), kaynak okunamazsa "okunamadı" satırı, `status.json` bayat ⇒ ilk satır `CRIT`, 21:00 İstanbul ⇒ 18:00 UTC (yaz/kış saati yok, TR UTC+3 sabit), günde bir kez, gecikmiş etiketi ve 23:30 kesimi (betik uygular), 3500 sınırında bölme, salt okunur bağlantıda yazma denemesi yok (defter `read_only=True`).
- Ortam: kapalı kanal (token yok) ⇒ motor/ders çökmez; env dosyası biçim tuzakları (`# not`, tırnak) uyarısı.

## 11. Açık sorular

Mentor kararlarıyla kapandı (başa bakın): önceki 1–10. Kalan: `/durdur`/PAUSE canlıya geçmeden önce yeniden ele alınacak (karar 1); `telegram_daemon_stale` sağlık kontrolü ayrı iş.

## 12. Gerçekleme notları (sapmalar)

- Rapor: motor (`status.json`), sağlık durumu ve spool bölümleri gerçeklendi; defter/bütçe/ders bölümleri `build_report(..., sections=)` kancasıyla bağlanır (varsayılan boş; ayrı iş).
- `kill` sonuç doğrulaması yalnız 5 dk sonraki `CRIT` denetimidir (10 sn ara denetim yok).
- `trader-health-fail@` gönderimi `ExecStartPre=-` ile yapılır (başarısız olsa da dış nabız betiği çalışır).
