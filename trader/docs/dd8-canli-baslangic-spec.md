# DD-8 — Canlı başlangıç güvenliği (uygulama şartnamesi v1, 18 Kasım 2026)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> **[ASKIDA — kullanıcı yeniden belirleyecek]** 18 Kasım: kullanıcı kararıyla gerçek paraya ilişkin bütün kararlar (başlangıç tutarı, kasa tavanı 1500 USD, duman testi/canlı tarihleri) askıya alındı; bu belgedeki değerler uygulanmaz.

**Hazırlayan:** mentor · **Taban:** `claude/charming-hawking-ab5w5q` @ `3586d93` (DD-2 birleşmiş)
**Kaynak:** `otonom-trading-arastirma/dis-denetim/triyaj-2026-11-18.md` — O4, O8, O6, D7, D2 + DD-2 incelemesinden devreden dört madde (E1–E4).
**Hedef:** 14 Aralık testnet gölge koşusundan önce birleşmiş olmak. Canlı çalışmıyor; bu paket para riski taşımaz.

Bu belge davranışı tanımlar. Test yazan ajan uygulamayı görmeden yalnız bu belgedeki adlara (çıkış kodu, hata kodu, sayaç, kv anahtarı, işlev imzası) dayanır; bu adlar **sözleşmedir**, uygulayıcı değiştiremez.

---

## 0. Kapsam, kısıtlar, ortak kurallar

**Kapsam içi:** O4, O8, O6, D7, D2, E1 (`pause_file` mutlak yol), E2 (duman betikleri aynı yükleyici), E3 (D9(17) kardeş `ledger.sqlite` denetiminin damgayla değişmesi → O8'in parçası), E4 (`.spool.corrupt.jsonl` yedek + sağlık alarmı).

**Kapsam dışı:** `config/engine.live.json`, canlı systemd birimi, canlı env örnekleri, Telegram canlı yolları (DD-9); yasak penceresi (`ban.json`, O2); canlı `var` dizininin yedeklenmesi (DD-9: `BACKUP` yapılandırması).

**Sert kısıtlar (ihlali = paket reddi):**
1. Dondurulmuş dosyalara dokunulmaz: `scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `src/trader_ml/{features,features_v2,labels,guards,config}.py`, `src/trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `src/trader_engine/holdout.py`.
2. Hiçbir kapı gevşetilmez. Bu paketteki her değişiklik ya sıkılaştırmadır ya da "süreç açılır ama giriş kapalı" yönündedir.
3. `mode ∈ {paper, backtest}` çıktısı bit-özdeş kalır: altın 3 çiftli geri test (`tests/test_wp3_golden.py`) değişmeden geçer. `mode=backtest` yolunda bu paketin hiçbir kodu çalışmaz (damga okunmaz, yazılmaz). `mode=paper` yolunda damga **yalnız okunur**, state'e ve deftere hiçbir yeni satır yazılmaz.
4. Holdout (2026-05-01 … 2026-11-01) okunmaz. freqtrade / ccxt / python-binance eklenmez.
5. Çekim yetkisi açık anahtar hiçbir yolla, hiçbir ortam değişkeniyle canlıda çalıştırılamaz (O6).
6. Deftere şema sürümü artışı yok (`SCHEMA_VERSION = 4` kalır); defter damgası mevcut `meta` tablosuna `INSERT` ile yazılır (`meta` yalnız-ekleme tablosudur: bir kez yazılır, değişmez).

**Çıkış kodları (değişmez):** 2 = yapılandırma/anahtar, 3 = motor hatası (state kilidi dahil), 5 = borsaya ulaşılamıyor (yeniden denenir), 7 = açılış kapısı, 8 = kalıcı ret (yeniden denenmez). Yeni `EngineExit(8, …)` kodları: `state_stamp_mismatch`, `ledger_stamp_mismatch`, `state_stamp_missing`, `ledger_stamp_missing`, `state_missing`.

**Zorunlu açılış sırası (`mode ∈ {testnet, live}`, `build_engine` + `Engine.start`):**

| # | Adım | Başarısızlık | Ağ |
|---|---|---|---|
| 1 | Yapılandırma doğrulama (§2.1 `var_dir` kuralı, §6 mutlak yollar) | çıkış 2 | yok |
| 2 | `LIVE_CONFIRM`, anahtarlar | çıkış 2 | yok |
| 3 | State kilidi (`<state_path>.lock`, engellemesiz `flock`) | `StateError` → çıkış 3 | yok |
| 4 | Damga doğrulaması (§2) | çıkış 8 | yok |
| 5 | `LiveBroker.startup_check()` (ilk HTTP isteği burada) | 5 ya da 8 | var |
| 6 | Cüzdan tavanı tutuşu (§1) → `protect_first()` → `_startup_gate()` → mutabakat | — | var |

**Değişmez:** 1–4. adımlarda borsaya **sıfır** HTTP isteği gider (`GET /fapi/v1/time` dahil). Testlerde "istek sayısı" sahte borsanın (`tests/engine/fake_exchange.py`) kayıt listesinden ölçülür.

---

## 1. O4 — Cüzdan tavanı aşımı: süreç açılır, girişler kapanır

**Sorun.** `startup_check` 3. adımı `totalWalletBalance > live.expected_wallet_max` ise `EngineExit(8, "wallet_above_expected")` atıyor (`binance_futures.py:437-438`); bu, state açılmadan ve `protect_first`'ten önce oluyor, birim yeniden denemiyor. Hesap kârla tavanı aştıktan sonraki ilk yeniden başlatmada açık pozisyonlar yönetimsiz kalır. Tavan çalışırken hiç denetlenmiyor.

**Gerekli davranış.**
1. `startup_check`: `wallet > expected_wallet_max` artık istisna **atmaz**; `LiveBroker.startup_findings` (salt okunur özellik, `tuple[str, ...]`) içine `"wallet_above_expected"` eklenir ve açılış 4–8. adımlarla sürer. Karşılaştırma katı `>`; eşitlik aşım değildir.
2. Okunamayan bakiye (`totalWalletBalance` yok / sayı değil / sonlu değil) **aynen** `EngineExit(8, "wallet_unreadable")` kalır.
3. Denetim artık `mode=testnet`te de çalışır (bugün yalnız `live`): gölge koşu bu yolu sınasın diye. `config/engine.testnet.json` tavanı (100000) değişmez. *(Mentor kararı; sıkılaştırma.)*
4. `Engine.start()`, `protect_first()`ten **önce**: bulgu varsa `pause.add("wallet_above_expected", by="engine:wallet_cap", note="wallet=<değer> max=<tavan>")` ve `CRITICAL` günlük (`wallet_above_expected` sözcüğünü içerir). `pause.REASONS`a `"wallet_above_expected"` eklenir.
5. **Çalışırken:** canlı döngüde motorun zaten okuduğu hesap değeri (ek REST çağrısı **yok**; `_ladder_step` içindeki `broker.account()`) sonlu ve `> expected_wallet_max` ise aynı tutuş eklenir (`add` idempotent; ilk köken korunur). Sonlu olmayan değer bu denetimde yok sayılır (kademe mantığı zaten ele alıyor). *(Mentor kararı; sıkılaştırma: davranış yeniden başlatmaya bağlı kalmasın.)*
6. Tutuş kalıcıdır: bakiye tavanın altına inse de kendiliğinden kalkmaz; Telegram `/devam` kaldıramaz (yalnız `user_cmd` kaldırır, değişmez); tek yol sunucuda `trader_engine pause --bot learner --env <env> --clear --reason wallet_above_expected --by <ad>`. Bakiye hâlâ tavanın üstündeyse motor sonraki denetimde tutuşu yeniden ekler.
7. Tutuş yalnız **girişi** kapatır (kapı kodu `pause.code()`); çıkışlar, stop kurma, iz süren stop, KILL ve mutabakat etkilenmez.
8. `trader_core/telegram.py` neden sözlüğüne Türkçe metin eklenir: `"wallet_above_expected": "hesap bakiyesi izin verilen tavanı aştı (yalnız sunucuda açılır)"`.

**Fail-closed.** `pause.add` başarısız olursa (dosya yazılamadı; `False` döner ve tutuş dosyada yok) süreç yine açılır ve korumaları çalıştırır, ama motor bellekte bir kilit tutar: süreç yaşadığı sürece hiçbir giriş emri gönderilmez ve her döngüde `add` yeniden denenir. Paper/backtest: bu maddenin hiçbir kodu çalışmaz.

**Dosyalar.** `brokers/binance_futures.py` (`startup_check`, `startup_findings`), `engine.py` (`start`, `_ladder_step` ya da eşdeğeri), `pause.py` (`REASONS`), `trader_core/telegram.py` (metin), `docs/motor/11-canli-broker.md` §3.4-3, §6.2, §9.2.

**Kabul testleri.**
- **O4-1** `live`, `totalWalletBalance = max + 0.01`, borsada stopsuz bir pozisyon (state'te `open`): `build_engine` + `start()` istisnasız tamamlanır; `"wallet_above_expected" in broker.startup_findings`; pozisyon için stop emri borsaya gönderilmiştir; `pause.holds()` içinde `reason="wallet_above_expected"`, `by="engine:wallet_cap"`.
- **O4-2** O4-1 koşulunda geçerli bir giriş sinyali işlenir: borsaya giriş emri (reduceOnly olmayan MARKET) **gönderilmez**; kapı kodu duraklatma kodudur.
- **O4-3** `totalWalletBalance == max` → bulgu yok, tutuş yok. `max - 0.01` → aynı.
- **O4-4** `totalWalletBalance` alanı yok / `"abc"` / `"nan"` → `EngineExit` kod 8, ileti `wallet_unreadable` (üç ayrı durum).
- **O4-5** `testnet`, bakiye > tavan → O4-1 ile aynı sonuç (tutuş var, süreç açık).
- **O4-6** Çalışırken: açılışta bakiye < tavan; sonra sahte borsa bakiyeyi tavanın üstüne çıkarır; hesap önbelleği süresi dolduktan sonraki `live_tick` sonunda tutuş vardır; bu denetim için ek `account` isteği yapılmamıştır (istek sayısı, denetimin olmadığı tabanla aynı).
- **O4-7** Tutuş varken bakiye tavanın altına iner, N `live_tick` → tutuş duruyor. CLI `pause --clear --reason wallet_above_expected --by x` → çıkış 0, tutuş yok. Bakiye hâlâ üstteyken temizlenirse sonraki denetimde yeniden eklenir.
- **O4-8** `pause.add` her çağrıda `False` dönecek biçimde bozulur (dosya yolu yazılamaz), bakiye > tavan: `start()` tamamlanır, `protect_first` çalışır, giriş sinyalinde giriş emri gönderilmez.
- **O4-9** `telegram.py` neden sözlüğü `pause.REASONS`ın her üyesi için metin içerir (`wallet_above_expected` dahil).
- **O4-10** `mode=paper`: `pause.REASONS` dışında hiçbir davranış değişmez; altın geri test bit-özdeş.

---

## 2. O8 (+E3) — Mod/hesap damgası, `var_dir` kuralı, `state_missing`

**Sorun.** `var_dir` serbest metin; boş/eksik `state.sqlite` sessizce sıfırdan kuruluyor; state'te ve defterde hangi moda/hesaba ait olduğunu söyleyen kayıt yok. `engine.live.json`da `var_dir` unutulursa canlı motor kâğıt defteriyle açılır (yanlış hesapla boyutlama). DD-2'nin 0 bayt denetimi (`state.py:207-213`) defteri sabit kardeş yoldan (`<dizin>/ledger.sqlite`) buluyor ve "eksik dosya" durumunu hiç yakalamıyor.

### 2.1 `var_dir` ve paylaşımlı yol kuralı (`config._validate`)
`mode ∈ {testnet, live}` iken, `os.path.normpath` sonrası:
- `var_dir`in son bileşeni `"var"` ise → `ConfigError` (ileti `var_dir` içerir). (`"var"`, `"./var"`, `"var/"`, `"/opt/trader/var"` hepsi ret.)
- `kill_file`ın son iki bileşeni `shared/KILL` ise ya da `pause_file`ın son iki bileşeni `shared/PAUSE` ise → `ConfigError` (kâğıt botlarının dosyaları).
`paper`/`backtest`te kural uygulanmaz. Bu kural yüzünden kırılan mevcut test düzenekleri (testnet/live kipinde varsayılan `var` kullananlar) düzenek tarafında düzeltilir; kural gevşetilmez.

### 2.2 Damga
- Değer: `want = f"{cfg.mode}:{cfg.live.account_tag}"` (ör. `testnet:testnet-sub`).
- State: kv anahtarı `account_stamp` (metin). Defter: `meta` tablosunda `key='account_stamp'`.
- Yeni modül `src/trader_engine/stamp.py`: `verify_or_init_stamp(cfg, state, ledger) -> None`; ret → `EngineExit(8, <kod>)`. Defter tarafı için `trader_core/ledger.py`ye `Ledger.get_meta(key) -> str | None` ve `Ledger.set_meta_once(key, value) -> None` (yoksa ekler; aynı değer varsa sessiz; farklı değer varsa `LedgerError`) eklenir.
- Tanımlar. **Defter dolu:** `trade_entries` ya da `decision_events`te en az bir satır (bugünkü `_ledger_has_history` ölçütü; paylaşılan tek işlev olur). **State bakir:** `positions` ve `orders` tabloları boş **ve** kv `initialized_at ∈ {yok, "unset"}` **ve** kv `broker_snapshot` yok. (0 baytlık ya da eksik dosyadan yeni kurulan state bakirdir.) **Kâğıt izi:** kv `broker_snapshot` var.

**Karar tablosu (`testnet`/`live`; açılış sırası 4. adım; ilk eşleşen satır uygulanır).** `S` = state damgası, `L` = defter damgası.

| # | Koşul | Sonuç |
|---|---|---|
| 1 | `S` var ve `S ≠ want` | çıkış 8 `state_stamp_mismatch` |
| 2 | `L` var ve `L ≠ want` | çıkış 8 `ledger_stamp_mismatch` |
| 3 | `S` yok, state'te kâğıt izi var | çıkış 8 `state_stamp_mismatch` |
| 4 | `S` yok, state bakir, (`L` var **ya da** defter dolu) | çıkış 8 `state_missing` |
| 5 | `S` yok, state bakir, `L` yok, defter boş | **ilk açılış:** önce `S`, sonra `L` yazılır; devam |
| 6 | `S` yok, state bakir değil | çıkış 8 `state_stamp_missing` |
| 7 | `S = want`, `L` yok, defter boş | `L` yazılır (5. satırın yarıda kalmış hâli); devam |
| 8 | `S = want`, `L` yok, defter dolu | çıkış 8 `ledger_stamp_missing` |
| 9 | `S = want`, `L = want` | devam |

Yazım sırası (5. satır) zorunludur: **önce state, sonra defter** (ters sıra, araya çökme girerse 4. satıra düşüp kendi kendini kilitler). Damga hiçbir yolla üzerine yazılmaz; bu pakette "damgayı benimse" komutu **yoktur**. 6. ve 8. satırların çaresi işletmeseldir: motor durdurulur, ilgili `var-*/<bot>` dizini arşive taşınır, motor temiz dizinle açılır (bkz. §8 Not-1).

**`paper`:** yalnız okuma. `S` var → `EngineExit(8, "state_stamp_mismatch")`; `L` var → `EngineExit(8, "ledger_stamp_mismatch")` (kâğıt hiçbir zaman damga yazmadığı için var olan her damga yabancıdır). Hiçbiri yoksa bugünkü davranış. `backtest`: denetim yok.

**`init-ledger` CLI:** defter açıldıktan sonra, yazmadan önce: `L` var ve (`mode ∈ {testnet, live}` iken `L ≠ want`; `paper` iken her `L`) → çıkış 8, hiçbir şey yazılmaz. `init-ledger` damga yazmaz.

### 2.3 E3 — kardeş yol denetiminin kaldırılması
`StateStore.__init__`e `ledger_path: str | None = None` eklenir; sabit `os.path.join(dirname, "ledger.sqlite")` kaldırılır. `ledger_path` verilmişse ve state dosyası var ama 0 bayt ise ve o defter dolu ise bugünkü `StateError` aynen atılır (kâğıt davranışı değişmez); `None` ise denetim yapılmaz. `ledger_path` yalnız **paper** kipinde geçirilir; `testnet`/`live`de `StateStore` `ledger_path` almaz, eksik/0 bayt state'i karar tablosu (4. satır) yakalar (DD-9 §9.5). `testnet`/`live`de asıl koruma karar tablosudur (4. satır eksik dosyayı da yakalar).

**Fail-closed.** Damga okunamazsa (sqlite hatası) → çıkış 8, kod ilgili `*_stamp_mismatch`. Damga yazılamazsa → çıkış 8 `state_stamp_missing` / `ledger_stamp_missing`. Hiçbir ret yolunda borsaya istek gitmez.

**Dosyalar.** `config.py` (`_validate`), yeni `stamp.py`, `state.py` (`ledger_path` parametresi, bakirlik sorgusu), `trader_core/ledger.py` (`get_meta`, `set_meta_once`), `engine.py` (`build_engine` sırası), `cli.py` (`init-ledger`, `unblock`), `deploy/trader-engine@.service` (`RestartPreventExitStatus=7 8`), `docs/motor/11-canli-broker.md` §3.1, §3.3, §6.2, §12.

**Kabul testleri.**
- **O8-1** `_validate`: `mode=testnet|live` × `var_dir ∈ {"var", "./var", "var/", "/x/y/var"}` → `ConfigError`; `"var-testnet"`, `"/x/var-live"` → geçer. `mode=paper`, `var_dir="var"` → geçer.
- **O8-2** `mode=testnet|live`, `kill_file="shared/KILL"` ya da `pause_file="shared/PAUSE"` (göreli ve mutlak biçim) → `ConfigError`; `shared/testnet/KILL` → geçer.
- **O8-3** İlk açılış: boş dizin, `testnet` → açılış sürer; state kv `account_stamp == "testnet:<tag>"`; defter `meta.account_stamp` aynı. İkinci açılış → sürer, damgalar değişmemiş.
- **O8-4** Kâğıt motorunun gerçekten çalıştırılıp ürettiği `state.sqlite` + `ledger.sqlite`, `live` yapılandırmasının `var_dir`ine kopyalanır → çıkış 8 `state_stamp_mismatch`; borsaya istek sayısı 0; dosyalar bayt-özdeş kalır (damga yazılmamış).
- **O8-5** `testnet` damgalı dizin, `live` yapılandırmasıyla (ya da başka `account_tag` ile) açılır → çıkış 8 `state_stamp_mismatch`; istek 0.
- **O8-6** Damgalı `live` dizininde açık işlem varken `state.sqlite` (+ `-wal`, `-shm`) silinir → çıkış 8 `state_missing`; istek 0; yeni oluşan state dosyası damga içermez. Aynısı `state.sqlite` 0 bayta kesilerek → `state_missing`.
- **O8-7** O8-6'nın defterinde yalnız **kapanmış** işlemler varken → yine `state_missing`. Defter damgalı ama hiç satırı yokken (ilk açılıştan hemen sonra state silindi) → yine `state_missing`.
- **O8-8** Damgasız, dolu (kâğıt) defter + boş state, `testnet` → `state_missing`. Damgasız, bakir olmayan ama kâğıt izi taşımayan state → `state_stamp_missing`.
- **O8-9** Yarım ilk açılış: state damgalı, defter damgasız ve boş → açılış sürer, defter damgalanır. Aynı durumda defter dolu → `ledger_stamp_missing`.
- **O8-10** State `want` damgalı, defter başka damgalı → `ledger_stamp_mismatch`.
- **O8-11** `paper` motoru damgalı (`live:…`) state ile → `EngineExit` kod 8 `state_stamp_mismatch`; damgalı defter + damgasız state ile → `ledger_stamp_mismatch`. Damgasız kâğıt dizininde açılış öncesi/sonrası state kv anahtar kümesinde `account_stamp` yok, defter `meta`sında `account_stamp` yok.
- **O8-12** `init-ledger --env testnet` damgası `live:…` olan defterde → çıkış 8, `param_versions` satır sayısı değişmez. `init-ledger` (paper) damgalı defterde → çıkış 8.
- **O8-13** `StateStore(path, bot=…, ledger_path=<başka dizindeki dolu defter>)`, state 0 bayt → `StateError`. `ledger_path=None` → hata yok. Kaynakta `"ledger.sqlite"` dizgisi `state.py` içinde geçmez.
- **O8-14** `set_meta_once`: yok → ekler; aynı değer → sessiz; farklı değer → `LedgerError`, satır değişmez.
- **O8-15** Altın geri test bit-özdeş; geri test koşusu `stamp.py`yi içe aktarmaz ya da çağırmaz (çağrı sayacı 0).

---

## 3. O6 — Anahtar izin denetimi: beyan yolu kaldırılır

**Sorun.** `_check_permissions` (`binance_futures.py:510-539`) yanıt herhangi bir nedenle okunamadığında (ban, ağ, eksik alan) `LIVE_PERMISSION_ATTESTED=YYYY-MM-DD` ile geçiyor. Ortamda unutulmuş bir beyan, çekim yetkisi açık anahtarı canlıda çalıştırabilir.

**Gerekli davranış (`live`; `startup_check` 2. adım).** Beyan yolu tümüyle silinir. `LIVE_PERMISSION_ATTESTED` tanımlıysa sonucu **hiçbir biçimde** etkilemez; yalnız bir `WARNING` yazılır ("artık geçerli değil"). Sonuç yalnız `GET /sapi/v1/account/apiRestrictions` yanıtına bağlıdır:

| Durum | Sonuç |
|---|---|
| Yanıt sözlük, altı alanın hepsi `bool` ve beklenen değerde | geçer |
| Herhangi bir alan `bool` ve beklenenin tersi | çıkış 8 `key_permission:<alan>` (birden çoksa `_REQUIRED_PERMS` sırasındaki ilki; eksik alan olsa da ihlal önceliklidir) |
| İhlal yok ama yanıt sözlük değil / bir alan eksik / `bool` değil | çıkış 8 `key_permission_unverifiable` |
| `ExchangeAuth` | çıkış 8 `auth_failed` |
| `ExchangeBan` http 451 ya da 403 | çıkış 8 `region_blocked` |
| Diğer `ExchangeBan` (418/429/gönderim öncesi pencere) | mevcut `_startup_ban` (en çok 300 sn bekle, çıkış 5) |
| `ExchangeUncertain` (ağ, zaman aşımı, 5xx, bozuk JSON), `ExchangeReject(-1021)` | çıkış 5 `exchange_unreachable` |
| Diğer `ExchangeReject` (uç kalıcı reddediyor) | çıkış 8 `key_permission_unverifiable` |
| Başka her istisna | çıkış 8 `key_permission_unverifiable` |

Beklenen değerler değişmez: `enableReading=True`, `enableFutures=True`, `enableWithdrawals=False`, `enableInternalTransfer=False`, `permitsUniversalTransfer=False`, `ipRestrict=True`. `scripts/smoke_live.py` kendi kopyası yerine bu demeti (`_REQUIRED_PERMS`) içe aktarır: tek kaynak. `testnet`: adım bugünkü gibi atlanır (uç testnette yok), `INFO` yazılır.

**Fail-closed.** Okunamayan her durum ya yeniden denenir (5) ya da kalıcı reddedilir (8); "geç" sonucu yalnız tablo satır 1'dir.

**Dosyalar.** `brokers/binance_futures.py` (`_check_permissions`), `scripts/smoke_live.py` (ortak demet), `docs/motor/11-canli-broker.md` §3.4-2 (beyan cümlesi silinir), `docs/sunucu-kurulum.md` (beyan anlatımı varsa silinir), beyanı geçerli sayan mevcut testler (`tests/engine/test_live_broker_impl_smoke.py`, `test_smoke_testnet.py`, `test_config_live_spec.py`) yeni davranışa çevrilir.

**Kabul testleri.**
- **O6-1** Altı alan doğru → açılış 3. adıma geçer.
- **O6-2** Altı alanın her biri için tek tek ters değer → çıkış 8 `key_permission:<alan>` (6 durum). `enableWithdrawals=True` + diğer alanlar eksik → `key_permission:enableWithdrawals`.
- **O6-3** Yanıt `[]` / `None` / bir alan eksik / bir alan `"true"` (metin) → çıkış 8 `key_permission_unverifiable`.
- **O6-4** O6-3'ün her durumu ve O6-5/O6-6 durumları, ortamda `LIVE_PERMISSION_ATTESTED=<bugün>` varken **aynı** sonucu verir (beyan sonucu değiştirmez). Özellikle: `enableWithdrawals=True` + beyan → çıkış 8.
- **O6-5** `ExchangeUncertain` → çıkış 5; 429 ban (`retry_after_s=7`) → saat 7 sn uyutulur, çıkış 5; `ExchangeBan(http=451)` ve `403` → çıkış 8 `region_blocked`.
- **O6-6** `ExchangeReject(code=-2015)` gibi kalıcı ret → çıkış 8 `key_permission_unverifiable`; `ExchangeReject(code=-1021)` → çıkış 5; `ExchangeAuth` → çıkış 8 `auth_failed`; `RuntimeError` → çıkış 8.
- **O6-7** Kaynak denetimi: `src/` altında `LIVE_PERMISSION_ATTESTED` yalnız uyarı günlüğü bağlamında geçer; değeri `date.fromisoformat` ya da herhangi bir karşılaştırmaya girmez (AST/metin testi).
- **O6-8** `testnet`: `api_restrictions` hiç çağrılmaz.
- **O6-9** İzin reddiyle biten her açılışta hesap ayarı POST'u (`marginType`, `leverage`, `positionSide/dual`, `multiAssetsMargin`) sayısı 0.

---

## 4. D7 — State kilidi hesaba dokunmadan önce alınır

**Sorun.** `build_engine` önce `_build_live_broker` → `startup_check` (hesap ayarı POST'ları), sonra `StateStore` (kilit) çalıştırıyor (`engine.py:1787` → `:1798`). Yanlışlıkla başlatılan ikinci süreç kilide takılmadan önce hesaba dokunur.

**Gerekli davranış.** `mode ∈ {testnet, live}` iken §0'daki sıra: kilit (3) ve damga (4), `startup_check`ten (5) önce. Kilit alınamazsa bugünkü `StateError("state kilitli …")` → CLI çıkış 3; borsaya istek 0. `startup_check` 5 ya da 8 ile biterse state ve defter kapatılır, kilit bırakılır (kilit dosyası kalabilir; `flock` kalmaz). `paper`/`backtest` kurulum sırası ve çıktısı değişmez. `build_engine(broker=<enjekte>)` çağrısında da kilit ve damga, enjekte edilen broker'ın herhangi bir yöntemi çağrılmadan önce tamamlanır.

**Dosyalar.** `engine.py` (`build_engine`, `_build_live_broker`), `docs/motor/11-canli-broker.md` §6.2.

**Kabul testleri.**
- **D7-1** Test `<state_path>.lock` üzerinde `flock(LOCK_EX)` tutar; `build_engine(testnet)` → `StateError`; sahte borsaya giden istek sayısı 0 (GET dahil).
- **D7-2** Birinci motor açık (kilit onda). İkinci `trader_engine run --env testnet` → çıkış 3; sahte borsada ikinci süreçten gelen istek 0; birinci motorun `status.json` döngüsü sürüyor.
- **D7-3** `startup_check` çıkış 8 ile biter (ör. `account_cannot_trade`) → hemen ardından aynı süreçte yeni `StateStore(state_path)` açılabilir (kilit sızmamış).
- **D7-4** Çağrı sırası kaydı: `flock` alınması < damga doğrulaması < ilk HTTP isteği (sahte saat/olay günlüğü ile).
- **D7-5** `paper`: `build_engine` içindeki defter/state açılış sırası ve altın geri test değişmez.

---

## 5. D2 — Giriş öncesi hesap modu doğrulaması (düz çift)

**Sorun.** Marjin tipi/kaldıraç sapması yalnız pozisyon **varken** yakalanıyor (L10, `reconcile_live.py:637-645`). Düz çiftte operatör (ya da başka bir araç) kaldıracı/marjin tipini değiştirirse sonraki giriş o ayarla açılır; `_prepared` kümesi yalnız açılışta doldurulur.

**Gerekli davranış (`LiveBroker.market_order`, yalnız `role == "entry"`).** Yerel denetimler (`_prepared`, `leverage_mismatch`, `min_notional`, kurallar) geçtikten sonra, emir POST'undan **hemen önce** tek bir **taze** okuma: `position_risk(<symbol>)` (önbellek ya da `_sync`in son okuması yeterli değildir). Girişe yalnız şu üçü birlikte doğruysa izin verilir: yanıtta o sembolün satırı var; `marginType` küçük harfe çevrilince `"isolated"`; `leverage` tam sayıya çevrilince `cfg.leverage`.
- Değer uyuşmuyor → emir **gönderilmez**, `OrderResult` reddi neden `"not_prepared"`; sayaç `account_mode_drift` +1; `CRITICAL` günlük `account_mode_drift:<pair> margin=<…> leverage=<…>`.
- Okuma başarısız (her `ExchangeError`, satır yok, alan eksik/çevrilemiyor) → emir **gönderilmez**, neden `"not_prepared"`; sayaç `account_mode_unverified` +1; `ERROR` günlük. `ExchangeBan` ayrıca mevcut `_note_ban`, `ExchangeAuth` ayrıca mevcut `exchange_auth` kilidi yoluna gider.
- İki sayaç `_COUNTERS`a eklenir ve `health()` üzerinden `status.json`a çıkar.
- `_prepared` kümesine dokunulmaz; doğrulama her girişte yeniden yapılır (operatör ayarı geri alırsa sonraki giriş geçer). Motor kendiliğinden `set_isolated` / `set_leverage` **göndermez** (çalışırken hesap ayarı POST'u yok).
- Çıkış (`role == "exit"`), stop, hedef ve iptal yolları bu okumayı **yapmaz** ve bu denetimle asla reddedilmez.
- `testnet` ve `live`de aynı. `PaperBroker`a dokunulmaz.

**Dosyalar.** `brokers/binance_futures.py` (`market_order`, `_COUNTERS`), `docs/motor/11-canli-broker.md` §5.3, §8 (L10 notu).

**Kabul testleri.**
- **D2-1** Hazırlanmış düz çift; sahte borsada kaldıraç `cfg.leverage + 1` yapılır; giriş → sonuç `rejected`/`not_prepared`; `POST /fapi/v1/order` sayısı 0; `account_mode_drift == 1`; `CRITICAL` günlük var.
- **D2-2** Aynısı `marginType="cross"` ile → aynı sonuç.
- **D2-3** Değerler doğru → giriş gönderilir; sıra: `GET positionRisk(symbol)` isteği giriş POST'undan önce ve arada başka giriş POST'u yok; giriş başına tam 1 ek okuma.
- **D2-4** `position_risk` `ExchangeUncertain` / `ExchangeBan(429)` / boş liste / `leverage` alanı yok → `not_prepared`, POST 0, `account_mode_unverified` +1 (dört durum); ban durumunda ban penceresi kaydı da oluşmuştur.
- **D2-5** Sapma sürerken açık bir pozisyonun piyasa çıkışı ve stop yenilemesi gönderilir (reddedilmez) ve bu yollarda ek `positionRisk(symbol)` okuması yoktur.
- **D2-6** Sapma düzeltilir (sahte borsa eski değerlere döner) → sonraki giriş yeniden başlatma olmadan geçer.
- **D2-7** Önbellek tuzağı: `_sync` doğru değerleri okuduktan **sonra** borsada kaldıraç değişir, araya `_sync` girmeden giriş gelir → `not_prepared` (taze okuma kanıtı).
- **D2-8** Motor düzeyi: `not_prepared` reddinde `opening` pozisyon kapanır (`_close_unopened`), `stop_failed` kilidi yazılmaz, sonraki barlarda motor çalışmayı sürdürür.
- **D2-9** Çalışma sırasında (açılış bittikten sonra) `marginType` / `leverage` POST sayısı 0.

---

## 6. E1 + E2 — `pause_file` (ve canlı `var_dir`) mutlak yol; duman betikleri aynı yükleyici

**Sorun.** DD-2 yalnız `kill_file`ı yapılandırma dizinine göre mutlak yaptı (`config.absolutize_kill_file`, `cli._load_cfg`). `pause_file` hâlâ göreli: `cli.py:290`, `:397`, `engine.py:1795/1801` çalışma dizinine, `engine.py:112` `os.path.abspath`e bağlı. Başka dizinden çalıştırılan `pause --clear` yanlış dosyada işlem yapar. `scripts/smoke_live.py:532` ve `scripts/smoke_testnet.py:750` `load_engine_config`i doğrudan çağırıp mutlaklaştırmayı atlıyor.

**Gerekli davranış.**
1. `config.py`: `absolutize_paths(cfg, base_path) -> EngineConfig`. Kök kuralı DD-2 ile aynı (yapılandırma dizini `config` ise üstü, değilse kendisi). Her modda `kill_file` ve `pause_file`; `mode ∈ {testnet, live}` iken ayrıca `var_dir` mutlak yapılır. Zaten mutlak olan alan değişmez. `paper`/`backtest`te `var_dir`, `market_db`, `history_dir`, `veto_config` **olduğu gibi** kalır. `absolutize_kill_file` adı geriye uyum için kalabilir (yeni işleve yönlenir).
2. `config.py`: `load_cli_config(config_dir, bot="learner", env=None) -> EngineConfig` = `load_engine_config(base, bot, overlay)` + `absolutize_paths`. `cli._load_cfg`, `scripts/smoke_live.py`, `scripts/smoke_testnet.py` (ve motor yapılandırmasını `load_engine_config` ile yükleyip `kill_file`/`pause_file` okuyan diğer betikler) yalnız bunu kullanır. `load_engine_config`in kendisi ham değeri döndürmeyi sürdürür ("paper config loads unchanged" sözleşmesi).
3. `build_engine`: `mode ∈ {testnet, live}` iken `kill_file`, `pause_file` ya da `var_dir` mutlak değilse `ConfigError` (ileti `relative_path:<alan>`); `paper`de bugünkü davranış. `Engine.__init__`teki `os.path.abspath` yedeği yalnız `paper` için kalır.
4. `cli run` açılışta `pause` dosyasının mutlak yolunu da (`<pause_file>.<bot>`) günlüğe yazar; `pause --list` çıktısına `"pause_file"` (mutlak yol) alanı eklenir.
5. Duman betiklerinin yol korumaları (`smoke_testnet_lib.guard_config`, `smoke_live.guard_config`) mutlak yolun **tamamında** alt dizgi aramaz (kök dizin adında "testnet" geçmesi yanlış geçiş verir); yalnız son iki yol bileşenine bakar.

**Fail-closed.** Canlıda göreli yol = açılmaz (çıkış 2).

**Dosyalar.** `config.py`, `cli.py` (`_load_cfg`, `_cmd_pause`, `_ladder_pause`, `_cmd_run`), `engine.py` (`:112`, `build_engine`), `scripts/smoke_live.py`, `scripts/smoke_testnet.py`, `scripts/smoke_testnet_lib.py`.

**Kabul testleri.**
- **E1-1** `load_cli_config("<kök>/config", env="testnet")`: `kill_file == "<kök>/shared/testnet/KILL"`, `pause_file == "<kök>/shared/testnet/PAUSE"`, `var_dir == "<kök>/var-testnet"`. Paper: `kill_file`, `pause_file` mutlak; `var_dir == "var"` (ham).
- **E1-2** Çalışma dizini `/tmp/başka` iken `trader_engine pause --bot learner --config-dir <kök>/config --reason manual --by x` → dosya `<kök>/shared/PAUSE.learner`de oluşur; `/tmp/başka/shared` oluşmaz. `--clear` aynı dosyayı kaldırır.
- **E1-3** `--env testnet` ile başka dizinden `pause` ve `capital list`: tutuş `<kök>/shared/testnet/PAUSE.learner`, denetim satırı `<kök>/var-testnet/learner/pause_audit.jsonl`; çalışma dizininde hiçbir dosya oluşmaz.
- **E1-4** Motorun `EntryPause` yolu ile `cli pause` yolu, iki farklı çalışma dizininden kurulduğunda bile aynı dizgidir.
- **E1-5** `build_engine(testnet, pause_file="shared/testnet/PAUSE")` (göreli) → `ConfigError` `relative_path:pause_file`; aynısı `kill_file`, `var_dir` için.
- **E1-6** Yapılandırma dizini adı `config` değilse (`<kök>/cfgx`) kök `<kök>/cfgx` olur (DD-2 kuralıyla aynı).
- **E2-1** Kaynak denetimi: `scripts/smoke_live.py`, `scripts/smoke_testnet.py` içinde `load_engine_config(` çağrısı yok; `load_cli_config(` var.
- **E2-2** Başka dizinden `python scripts/smoke_testnet.py --config-dir <kök>/config …` (emirsiz/kuru adım): T-15'in kullandığı KILL yolu `<kök>/shared/testnet/KILL`dir.
- **E2-3** Depo kökü `/tmp/testnet-x/` altındayken kâğıt yolu (`…/shared/KILL`) taşıyan yapılandırma `smoke_testnet_lib.guard_config`ten **geçemez** (`SafetyError`).

---

## 7. E4 — `<ledger>.spool.corrupt.jsonl`: yedek ve sağlık alarmı

**Sorun.** DD-2 okunamayan spool satırlarını `<defter>.spool.corrupt.jsonl`a taşıyor (`ledger.py:2419-2445`) ama bu dosya ne yedekleniyor ne izleniyor; sessizce kaybolmuş işlem/karar kaydı demektir.

**Gerekli davranış.**
1. **Yedek** (`scripts/health_backup.py`): defter yedeği başarılıysa, `<src>.spool.corrupt.jsonl` varsa ve boş değilse `<gün>/<ad>.spool.corrupt.jsonl` olarak kopyalanır (fsync), `MANIFEST.json`da ilgili defter girdisine `"spool_corrupt_bytes": <kopyalanan bayt>` eklenir. Dosya yok ya da 0 bayt → kopya yok, alan yok. Kopyalama hatası bugünkü `_copy_spool` hatasıyla aynı sonucu verir (girdi `ok=false`, yedek başarısız).
2. **Sağlık:** `H.LedgerProbe`a `spool_corrupt_lines: int | None = None` (sona, varsayılanlı). `scripts/health_run.py:probe_ledger` doldurur: dosya yok → 0; okunur → satır sayısı; `FileNotFoundError` dışı `OSError` → `None`.
3. `ledger_gate:<bot>`in yapıldığı her bot için yeni denetim `spool_corrupt:<bot>`: `> 0` → `CRIT`, kod `spool_corrupt`, değer = satır sayısı; `0` → `OK`; `None` → `UNKNOWN` kod `spool_corrupt_unreadable`. Ayrı denetimdir; `ledger_gate`in erken dönüşleri (ör. `spool_pending`) onu maskeleyemez. `spool_corrupt`, `IMMEDIATE_CODES`a eklenir. Isınma (`_warm`) bu denetimi yumuşatmaz.
4. Türkçe alarm metni (`health.py` metin tablosu): başlık "Deftere yazılamayan bozuk kayıt var", düzelme "Bozuk kayıt dosyası temizlendi".
5. Alarm, dosya boşalana ya da adı değişene kadar sürer. Temizleme elle yapılır: inceleme sonrası dosya `…spool.corrupt.<YYYYMMDD>.jsonl` adına taşınır (`docs/saglik-spec.md` ve `docs/motor/11-canli-broker.md` §10'a yazılır). Motor bu dosyayı hiçbir zaman silmez/kısaltmaz.

**Dosyalar.** `scripts/health_backup.py`, `scripts/health_run.py`, `src/trader_core/health.py`, `docs/saglik-spec.md`.

**Kabul testleri.**
- **E4-1** 2 satırlı `ledger.sqlite.spool.corrupt.jsonl` → `run_backup` sonrası gün dizininde `ledger_learner.sqlite.spool.corrupt.jsonl` bayt-özdeş; manifestte `spool_corrupt_bytes` = dosya boyutu; yedek `ok`.
- **E4-2** Dosya yok / 0 bayt → kopya yok, manifestte alan yok, yedek `ok`.
- **E4-3** `LedgerProbe(spool_corrupt_lines=3)` → `spool_corrupt:learner` `CRIT`, kod `spool_corrupt`, değer 3; rapor birleşik durumu `CRIT`. `0` → `OK`. `None` → `UNKNOWN` `spool_corrupt_unreadable`.
- **E4-4** `spool_lines=5` (→ `ledger_gate` `spool_pending`) ve `spool_corrupt_lines=1` aynı anda → raporda iki kod da ayrı ayrı var.
- **E4-5** `"spool_corrupt" in H.IMMEDIATE_CODES`; `plan_alerts` ilk görüşte (tekrar beklemeden) alarm üretir; dosya taşındıktan sonraki koşuda düzelme iletisi üretir.
- **E4-6** `probe_ledger`: 2 satırlı dosya → 2; dosya yok → 0; dosya yerinde dizin (okunamaz) → `None`.
- **E4-7** Uçtan uca: bozuk bir spool satırı `drain_spool` ile karantinaya alınır → bir sonraki sağlık koşusu `spool_corrupt` `CRIT` verir.
- **E4-8** Var olan `LedgerProbe(...)` konumsal kurucuları (6 argüman) bozulmadan çalışır.

---

## 8. Notlar ve teslim koşulları

- **Not-1 (testnet dizini).** Sunucudaki `var-testnet/learner` DD-8'den önce oluştuysa damgasızdır ve motor `state_stamp_missing` / `state_missing` ile açılmaz. DD-8 dağıtımında, gölge koşudan önce: motor durdurulur, dizin `var-testnet/learner.pre-dd8-<tarih>` adına **taşınır** (silinmez), birim yeniden başlatılır. Bu adım `docs/sunucu-kurulum.md`ye yazılır; `install.sh` bunu kendiliğinden yapmaz. *(Mentor kararı: testnet deneme verisi, gerçek para kaydı yok.)*
- **Not-2 (DD-9'a devir).** `engine.live.json` yazılırken: `var_dir` son bileşeni `var` olamaz, `kill_file`/`pause_file` `shared/live/…` altında olmalı; sağlık/Telegram env'leri aynı mutlak yolları taşımalı; canlı `var` dizini yedeğe alınmalı; canlı birimde `RestartPreventExitStatus=2 7 8`.
- **Not-3 (O6 kanıtı).** Alt hesap anahtarında `apiRestrictions` ucunun okunabildiği DD-5'teki "canlı-yalnız" maddesinde kanıtlanır. Okunamıyorsa motor canlıda açılmaz; aşma yolu yoktur ve konu o zaman kullanıcıya gider.
- **Belgeler.** `docs/motor/11-canli-broker.md` §3.1, §3.3 (yeni 8 kodları), §3.4-2/-3, §5.3, §6.2 (yeni sıra tablosu), §9.2 (yeni tutuş), §12 (geçiş listesi: damga, tavan tutuşu, izin) bu paketle birlikte güncellenir.
- **Test dosyaları.** Şartname testleri `tests/engine/test_dd8_spec.py` (bağımsız ajan), uygulama testleri `tests/engine/test_dd8_impl.py`. Sağlık/yedek testleri `tests/test_health_dd8.py`.
- **Teslim.** Tüm test paketi yeşil; altın 3 çiftli geri test bit-özdeş; dondurulmuş dosyalarda `git diff` boş; `src/` altında `LIVE_PERMISSION_ATTESTED` yalnız uyarı günlüğünde; yeni bağımlılık yok.

## 9. Kullanıcıya gidecek kararlar

Bu paketi başlatmak için kullanıcı kararı **gerekmiyor**; yukarıdaki seçimlerin hepsi sıkılaştırma yönünde mentor kararıdır. Canlıya geçmeden önce yanıtlanması gereken tek soru:

1. **Kasa tavanı ne kadar yukarıda dursun?** Bot, hesaptaki para belirlediğimiz tavanı geçtiği anda (yalnız yeniden başlatmada değil, çalışırken de) yeni işlem açmayı durduracak; açık işlemleri korumaya ve kapatmaya devam edecek. Yeniden işlem açması için sizin tavanı yükseltmeniz ya da kârı hesaptan çekmeniz, ardından sunucuda tek bir komutla onay verilmesi gerekecek. Bugünkü planla (300 USD başlangıç, 350 USD tavan) bu duruş yaklaşık %17 kârda gelir. Tavanı 350'de mi tutalım (erken durur, daha sık onayınız gerekir), yoksa başlangıç için daha yüksek bir değer mi seçelim?

Bilgi (karar gerekmez): 14 Aralık'tan önce testnet deneme kayıtları arşive taşınıp temiz başlatılacak; gerçek para kaydı değildir.
