# DD-9 — Canlı paket ve kurulum sertleştirme (uygulama şartnamesi v1, 18 Kasım 2026)

> **[ASKIDA — kullanıcı yeniden belirleyecek]** 18 Kasım: kullanıcı kararıyla gerçek para kararları (1000 USD, 1500 USD tavan, canlı tarihi) askıya alındı; canlı yapılandırma değerleri uygulanmaz.

**Hazırlayan:** mentor · **Taban:** `claude/charming-hawking-ab5w5q` @ `0f2ef52` (DD-2, DD-7, DD-8 birleşmiş)
**Kaynak:** `otonom-trading-arastirma/dis-denetim/triyaj-2026-11-18.md` — K1 (paket), O7, O12, O13, O15; `docs/dd7-ban-kalicilik-spec.md` "DD-9 için devredilenler" (8 madde); `docs/dd8-canli-baslangic-spec.md` Not-2; DD-7 mentor inceleme notları; `tasarim-kararlari.md` 18 Kasım (kasa tavanı 1500 USD).
**Hedef:** O12/O13 **canlı anahtar sunucuya konmadan önce**; birim değişiklikleri 14 Aralık gölge koşusundan önce (gölge koşu canlı birimin provasıdır). Canlı çalışmıyor; bu paket para riski taşımaz.

Bu belge davranışı tanımlar. Test yazan ajan uygulamayı görmeden yalnız bu belgedeki adlara (dosya adı, ortam değişkeni, işlev imzası, hata/sağlık kodu, çıkış kodu, birim anahtarı) dayanır; bu adlar **sözleşmedir**.

---

## 0. Kapsam, kısıtlar, yeni adlar

**Kapsam içi:** K (canlı yapılandırma), U (motor birimleri, `--ensure-ledger`, yeniden başlatma), E (env dosyaları, O13), R (root kod kopyası, veto kullanıcısı, süreç ortam koruması, O12), C (`COMMIT` sabitleme, canlı etiketi, `--live`, O15), Y (canlı yolları: tek kaynak modül, Telegram, sağlık, yedek, ön denetim), T (`/devam`, O7), H (sağlık alarmları), D (devralınan küçükler), B (belgeler).

**Kapsam dışı (kayıt altında, ayrı iş):** yayın dalının seçimi ve dal koruması (triyaj kullanıcı kararı 1; §11); canlı bot için sapma izleyicisi, karşı-olgu gece işi ve pano yolları (canlıya geçişten önce ayrı küçük paket; o zamana kadar sağlık bu denetimi canlı bot için üretmez, §8.4); ikizin `ladder_follow` ayarı (11 §12 geçiş listesinde kalır); DD-5 testnet kampanyası; canlı motorun gerçekten başlatılması.

**Sert kısıtlar (ihlali = paket reddi):**
1. Dondurulmuş dosyalara dokunulmaz: `scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `src/trader_ml/{features,features_v2,labels,guards,config}.py`, `src/trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `src/trader_engine/holdout.py`.
2. `mode ∈ {paper, backtest}` çıktısı bit-özdeş: altın geri test (`tests/test_wp3_golden.py`) değişmeden geçer. `deploy/trader-engine@.service` (kâğıt birimi) **değişmez**. Bu paketin motor içi kodu (`--ensure-ledger`, `proc_guard`, damga ön denetimi) `paper`/`backtest` yolunda çalışmaz.
3. Holdout (2026-05-01 … 2026-11-01) okunmaz. freqtrade / ccxt / python-binance eklenmez. Yeni Python bağımlılığı yok.
4. Hiçbir kapı gevşetilmez; çıkış kodları (2, 3, 4, 5, 7, 8) ve DD-7/DD-8 sözleşme adları değişmez.
5. Sır (API anahtarı, token) depoya, birim dosyasına, komut satırına, günlüğe, betik çıktısına girmez. Sırlar yalnız `/etc/trader-*.env` dosyalarında durur ve kullanıcı tarafından `nano` ile yazılır; `install.sh` yalnız sır **olmayan** yol/ad alanlarını doldurur (tek istisna mevcut veto HMAC üretimi). Çekim yetkisi açık anahtar hiçbir yolla çalıştırılamaz (DD-8 O6 aynen).
6. `install.sh --live` verilmedikçe canlı birim sunucuya **kurulmaz**; `--live` de motoru **başlatmaz**.

**Yeni adlar.** Dosyalar: `config/engine.live.json`, `deploy/trader-engine-live.service`, `deploy/trader-engine-env-retry@.service`, `deploy/trader-engine-env-retry@.timer`, `deploy/trader-live.env.example`, `deploy/requirements-root.lock`, `deploy/canli_duman.sh`, `scripts/live_preflight.py`, `src/trader_core/live_paths.py`, `src/trader_core/proc_guard.py`. Ortam: `COMMIT`, `LIVE_BOTS`, `LIVE_VAR_DIR`, `LIVE_PAUSE_FILE`, `TRADER_DATA_ROOT`. Sunucu yolları: `/etc/trader-live.env`, `/etc/trader-release`, `/usr/local/lib/trader-root/`. CLI: `run --ensure-ledger`; `engine_retry.py --unit`. Sağlık kodları: `account_mode_drift`, `account_mode_unverified`, `account_mode_unknown`, `live_paths_mismatch`. Sayaç: `account_mode_unverified_ban`. Git etiketi kalıbı: `canli-YYYYAAGG[-N]`.

**Ortak tanım — kök dizin.** Bu belgede `<kök>` = `trader/` dizini (sunucuda `/home/trader/SG-Github-AB-proje/trader`; birim şablonlarında `/opt/trader`, `install.sh` `render()` gerçek yola çevirir).

---

## 1. K — `config/engine.live.json`

**Sorun.** Canlı katman dosyası yok (K1); içeriği O4/O8 kurallarıyla birlikte tanımlanmalı.

**Gerekli davranış.** Dosya tam olarak şudur (başka anahtar **yok**; `leverage`, `pairs`, `wallet_start`, `ml_mode`, `veto_mode`, `market_db` konmaz, tabandan gelir):

```json
{
  "mode": "live",
  "var_dir": "var-live",
  "kill_file": "shared/live/KILL",
  "pause_file": "shared/live/PAUSE",
  "live": {
    "account_tag": "canli-alt1",
    "expected_wallet_max": 2000.0,
    "conditional_mode": "algo",
    "recv_window_ms": 5000,
    "poll_open_s": 5.0,
    "poll_flat_s": 30.0,
    "stop_deadline_s": 10.0,
    "entry_resolve_window_s": 60.0,
    "max_attempts": 1,
    "order_quote": true
  }
}
```

`account_tag` bir **etikettir** (Binance'teki alt hesap adıyla aynı olması gerekmez); state ve defter damgası `live:canli-alt1` olur, ilk canlı açılıştan sonra değiştirilemez (DD-8 §2.2). `conditional_mode` testnet katmanıyla aynı kalır; T-01 sonucu testnet katmanını değiştirirse aynı commit'te canlı katman da değişir. `max_attempts=1` (T-08 kanıtı olmadan 2 yapılamaz).

**Fail-closed.** Dosya yok/bozuk → `run --env live` çıkış 2 (mevcut davranış).

**Dosyalar.** `config/engine.live.json` (yeni).

**Kabul testleri.**
- **K-1** `load_cli_config("<kök>/config", "learner", env="live")` istisnasız; `mode == "live"`, `var_dir == "<kök>/var-live"`, `kill_file == "<kök>/shared/live/KILL"`, `pause_file == "<kök>/shared/live/PAUSE"`, `live.account_tag == "canli-alt1"`, `live.expected_wallet_max == 2000.0` (23.11 kullanıcı kararı; önce 1500.0), `live.max_attempts == 1`, `leverage == LOCKED_CFG.min_leverage`, `veto_mode == "required"`, `cost.trigger_source == "mark"`.
- **K-2** Dosyanın üst düzey anahtar kümesi tam `{"mode","var_dir","kill_file","pause_file","live"}`; `live` anahtar kümesi `engine.testnet.json` ile aynı.
- **K-3** `engine.live.json["live"]` ile `engine.testnet.json["live"]` yalnız `account_tag` ve `expected_wallet_max` alanlarında farklıdır.
- **K-4** `load_cli_config(..., "twin", env="live")` → `ConfigError`.
- **K-5** `build_engine(cfg_live, env={})` → `ConfigError("live_confirm")`; `env={"LIVE_CONFIRM": "canli-alt1"}` anahtarsız → `ConfigError` iletisi `keys_missing` ile başlar. İki durumda sahte borsaya istek 0.
- **K-6** `mode=paper` yüklemesi (`load_cli_config(..., "learner")`) dosyanın varlığından etkilenmez (alanlar öncekiyle aynı).

---

## 2. U — Motor birimleri: canlı birim, testnet eşliği, `--ensure-ledger`, yeniden başlatma

**Sorun.** (a) Canlı birim yok. (b) `ExecStartPre=… init-ledger` çıkış 8 verdiğinde `RestartPreventExitStatus` uygulanmaz (yalnız ana süreci kapsar); birim yeniden başlatma döngüsüne girer (DD-7 devir 1). (c) Testnet birimi `StartLimitBurst=5` ile kısa bir ağ kesintisinde kalıcı `failed` olur; açık pozisyon yönetimsiz kalır (O1'in birim tarafı). (d) Çıkış 7'yi yeniden deneyen iş yalnız `trader-engine@<bot>` birimini tanır.

### 2.1 `run --ensure-ledger`
`trader_engine run` yeni bayrak alır: `--ensure-ledger` (varsayılan kapalı) ve `--ledger-reason` (varsayılan `paper_start`). Bayrak verilirse `_cmd_run`, yapılandırma yüklendikten ve (`testnet`/`live`de) `_live_startup` `None` döndükten **sonra**, `build_engine`den **önce** `init-ledger` alt komutunun yaptığı işin aynısını aynı süreçte yapar (ortak işlev; `init-ledger` alt komutu aynen kalır). Sonuç 0 değilse `run` o kodla döner (`2` yapılandırma, `4` strateji/şema, `8` yabancı damga) ve `build_engine` **çağrılmaz**; borsaya istek gitmez. Bayrak verilmezse davranış bayt-özdeştir.

### 2.2 Birimler
`deploy/trader-engine-live.service` (yeni) ve `deploy/trader-engine-testnet.service` (güncellenir) aşağıdaki anahtarları **aynı değer ve aynı sırayla** taşır; yalnız "fark" sütunundaki satırlar ayrışabilir.

| Bölüm | Anahtar = değer | Fark (testnet / canlı) |
|---|---|---|
| Unit | `After=network-online.target trader-feed.service`, `Wants=` aynı, `OnFailure=trader-health-fail@%n.service` | — |
| Unit | `StartLimitIntervalSec=0` (başlatma sınırı yok; `StartLimitBurst` satırı **yok**) | — |
| Unit | `ConditionPathExists=` | `/etc/trader-testnet.env` / `/etc/trader-live.env` |
| Unit | `Description=` | serbest; canlıda `CANLI` sözcüğünü içerir |
| Service | `Slice=trader.slice`, `Type=simple`, `User=trader`, `Group=trader`, `WorkingDirectory=/opt/trader` | — |
| Service | `EnvironmentFile=` (ilk) | `/etc/trader-testnet.env` / `/etc/trader-live.env` |
| Service | `EnvironmentFile=/etc/trader-veto-hmac.env`, `Environment=PYTHONPATH=/opt/trader/src`, `Environment=PYTHONUNBUFFERED=1` | — |
| Service | `ExecStartPre=` yalnız mevcut `market.sqlite` bekleme satırı; `init-ledger` içeren `ExecStartPre` **yok** | — |
| Service | `ExecStart=/usr/bin/python3 -m trader_engine run --bot learner --env <env> --config-dir config --ensure-ledger` | `testnet` / `live` |
| Service | `Restart=on-failure`, `RestartSec=5`, `RestartSteps=5`, `RestartMaxDelaySec=120`, `RestartPreventExitStatus=2 7 8` | — |
| Service | `MemoryHigh=`, `MemoryMax=`, `OOMScoreAdjust=`, `Nice=` | testnet `250M`/`320M`/(yok)/`10`; canlı `280M`/`350M`/`-300`/`5` |
| Service | `CPUQuota=60%`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=read-only` | — |
| Service | `ProtectProc=invisible`, `ProtectKernelTunables=true`, `ProtectKernelModules=true`, `ProtectControlGroups=true`, `RestrictSUIDSGID=true`, `LockPersonality=true`, `RestrictNamespaces=true`, `CapabilityBoundingSet=` (boş), `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` | — |
| Service | `ReadWritePaths=/opt/trader/var /opt/trader/<vardir> /opt/trader/shared /opt/trader/user_data` | `var-testnet` / `var-live` |
| Install | `WantedBy=multi-user.target` | — |

Canlı birimde testnet env dosyası, testnet biriminde canlı env dosyası **geçmez**. Canlı birimde `Conflicts=` **yoktur** (simetrik etkisi canlı motoru durdurabilir). Kâğıt birimi (`trader-engine@.service`) değişmez.

**Yeniden başlatma anlamı.** Çıkış 2, 7, 8 → `failed` + `OnFailure` alarmı. Diğer her çıkış (3, 4, 5, sinyal, OOM) 5 sn'den 120 sn'ye büyüyen aralıkla **süresiz** yeniden denenir; her açılışta `protect_first` çalışır. Döngü alarmını mevcut sağlık denetimleri verir (`api_unreachable`, `container_not_running`, `restart_loop`).

### 2.3 Çıkış 7 yeniden denemesi (testnet ve canlı)
`scripts/engine_retry.py`ye `--unit <ad>` eklenir (varsayılan `trader-engine@<bot>.service`; yalnız `^trader-engine(@(learner|twin)|-testnet|-live)\.service$` kabul edilir, aksi çıkış 1 ve hiçbir `systemctl` çağrısı yok). `unit_state` ve yeniden başlatma bu birime uygulanır; deneme sayacı ve Telegram `dedup_key` birim adına göre ayrılır (kâğıt birimlerinin mevcut anahtarları değişmez). Yeni şablon `trader-engine-env-retry@.service` (`%i` = `testnet` | `live`): `trader-engine-retry@.service` ile aynı, farklar `ExecStart=… engine_retry.py --bot learner --unit trader-engine-%i.service` ve §4 gereği root kopyadan çalışması. `trader-engine-env-retry@.timer` mevcut zamanlayıcıyla aynı aralıkta. `install.sh` `testnet` örneğini testnet birimiyle, `live` örneğini yalnız `--live` ile etkinleştirir.

**Fail-closed.** Bilinmeyen birim adı → hiçbir şey yeniden başlatılmaz. `--ensure-ledger` reddi → motor kurulmaz.

**Dosyalar.** `src/trader_engine/cli.py`, `deploy/trader-engine-live.service` (yeni), `deploy/trader-engine-testnet.service`, `deploy/trader-engine-env-retry@.{service,timer}` (yeni), `scripts/engine_retry.py`, `tests/readiness/test_readiness_memory.py` (düzenek: bütçe = feed + max(kâğıt learner, canlı) + ikiz + testnet; canlı ile kâğıt learner aynı anda çalışmaz).

**Kabul testleri.**
- **U-1** `cli.main(["run","--bot","learner","--env","testnet","--config-dir",d,"--ensure-ledger"])`, defter `meta.account_stamp = "live:x"` → dönüş 8; `build_engine` çağrılmamış (yama ile sayılır); sahte borsaya istek 0; `param_versions` satır sayısı değişmemiş.
- **U-2** Aynı çağrı boş dizinde (geçerli anahtarlar, sahte borsa enjekte) → defter oluşur, etkin parametre vardır, `build_engine` bir kez çağrılır. İkinci çağrıda `param_versions` satır sayısı değişmez.
- **U-3** `--ensure-ledger` olmadan `run`: defter yokken `init-ledger` işi yapılmaz (davranış tabanla aynı).
- **U-4** `testnet`, anahtarlar eksik + `--ensure-ledger` → dönüş 2; defter dosyası **oluşmamış** (onay/anahtar denetimi önce).
- **U-5** Birim eşliği: iki birim dosyasının `(bölüm, anahtar, değer)` listeleri, tablodaki "fark" anahtarları (`Description`, `ConditionPathExists`, ilk `EnvironmentFile`, `ExecStart`, `ReadWritePaths`, `MemoryHigh`, `MemoryMax`, `OOMScoreAdjust`, `Nice`) çıkarıldığında **eşit**.
- **U-6** Her iki birimde: `init-ledger` dizgisi yok; `ExecStart` `--ensure-ledger` ile biter; `StartLimitIntervalSec=0`; `StartLimitBurst` yok; `RestartPreventExitStatus` değeri tam `2 7 8`; tablodaki dokuz sertleştirme satırı var.
- **U-7** Canlı birim metninde `trader-testnet.env` ve `--env testnet` yok; testnet biriminde `trader-live.env`, `LIVE_CONFIRM` ve `--env live` yok; hiçbir birim dosyasında `BINANCE_API_KEY=` atanması yok.
- **U-8** `render_units` çıktısında iki birimde `/opt/trader` ve `/usr/bin/python3` kalmaz; `ExecStart` `<kök>/.venv/bin/python -m trader_engine run --bot learner --env live|testnet` içerir.
- **U-9** `deploy/trader-engine@.service` içeriği taban commit ile bayt-özdeş.
- **U-10** `engine_retry.main(["--bot","learner","--unit","trader-engine-live.service"], ctl=sahte)`: birim `failed` + çıkış 7 + besleme sağlıklı → `restart trader-engine-live.service` bir kez; çıkış 8 → yeniden başlatma yok. `--unit foo.service` → dönüş 1, `ctl` hiç çağrılmamış. `--unit` verilmezse `ctl` çağrıları tabanla aynı.
- **U-11** `trader-engine-env-retry@.service` `ExecStart`ı `--unit trader-engine-%i.service` içerir.

---

## 3. E — Env dosyaları: canlı örnek, `0600`, grup üyeliği (O13)

**Sorun.** `trader` kullanıcısı `trader-tg` grubunda ve üç env dosyası `0640`; motor, feed ve pano Telegram token'ını ve ders Anthropic anahtarını okuyabiliyor. Canlı env örneği yok; belgelerde üç farklı ad geçiyor.

**Gerekli davranış.**
1. Canlı anahtar dosyasının adı **`/etc/trader-live.env`**dir (belgelerdeki `/etc/trader-binance-*.env`, `trader-binance.env.example`, `live.conf.example` adları kaldırılır). `deploy/trader-live.env.example` yorum satırları dışında tam üç boş satır taşır: `BINANCE_API_KEY=`, `BINANCE_API_SECRET=`, `LIVE_CONFIRM=`. Yorumlar: yalnız gerçek alt hesap anahtarı; çekim/transfer kapalı, yalnız sunucu IP'si; testnet anahtarı buraya yazılmaz; `LIVE_CONFIRM` değeri `engine.live.json` `live.account_tag` ile aynı.
2. `install.sh` her çalıştırmada, `/etc/trader-*.env` kalıbındaki **var olan her dosyayı** (yeni oluşturduğu dahil) `root:root 0600` yapar (`harden_env_file <yol>`: sembolik bağ ise dokunmaz ve `fail`). `copy_env` çağrılarının hepsi `"root:root" 0600` kullanır. `/etc/trader-live.env` boş örnekten her kurulumda oluşturulur (var olan ezilmez).
3. `usermod -aG` satırı kalkar. `trader` kullanıcısı `trader-tg` üyesiyse çıkarılır (`gpasswd -d`, üye değilse sessiz). Grup silinmez: outbox dizini (`2770 trader:trader-tg`) ve birimlerdeki `SupplementaryGroups=trader-tg` aynen kalır (root yazan sağlık birimi ile `trader` okuyan daemon arasındaki tek köprü).
4. Env örneklerinin başlık yorumları `0600, root:root` der.
5. `uninstall.sh --purge` listesine `/etc/trader-live.env`, `/etc/trader-veto-hmac.env`, `/etc/trader-release` ve `/usr/local/lib/trader-root` eklenir; canlı ve env-retry birimleri de kaldırılır.

**Fail-closed.** Env dosyası sembolik bağ → kurulum durur. İzin düzeltilemezse (`chmod`/`chown` hatası) kurulum durur (`set -e`).

**Dosyalar.** `deploy/install.sh`, `deploy/uninstall.sh`, `deploy/trader-live.env.example` (yeni), `deploy/*.env.example` (başlık), `tests/readiness/readiness_support.py` (düzenek).

**Kabul testleri.**
- **E-1** `trader-live.env.example`: yorum dışı satırlar `{"BINANCE_API_KEY": "", "BINANCE_API_SECRET": "", "LIVE_CONFIRM": ""}`.
- **E-2** `install.sh` metninde `0640` ve `usermod -aG` geçmez; her `copy_env` satırı `"root:root"` ve `0600` taşır; `/etc/trader-live.env` için `copy_env` var.
- **E-3** Env adımı tmp dizinde çalıştırılır (`render_env_files` yöntemi): üretilen **her** `trader-*.env` dosyasının kipi `0600`. Önceden `0640` kipli var olan dosya adımdan sonra `0600` ve içeriği bayt-özdeş.
- **E-4** `harden_env_file` işlevi çıkarılıp çalıştırılır: düz dosya → `0600`; sembolik bağ → sıfırdan farklı çıkış, hedef dosyanın kipi değişmemiş.
- **E-5** `install.sh` metninde `gpasswd -d` `trader` ve `trader-tg` ile, üyelik denetimi koşulu altında geçer; `groupdel` geçmez.
- **E-6** Telegram, sağlık, sağlık-hata, ders, rapor ve env-retry birimlerinde `SupplementaryGroups=trader-tg` duruyor.
- **E-7** `uninstall.sh` metni beşinci maddedeki dört yolu içerir.

---

## 4. R — Root kod kopyası, veto kullanıcısı, süreç ortam koruması (O12)

**Sorun.** Dört root birimi (`veto`, `backup`, `health`, `engine-retry`) `trader`ın yazabildiği depodaki betikleri ve `trader`ın yazabildiği `.venv` yorumlayıcısını çalıştırıyor; `install.sh` de root olarak aynı depodan çalışıyor ve kendini oradan yeniden başlatıyor. `trader` kimliği ele geçirilirse root'a yükselir ve `/etc/trader-*.env` okunur. Ayrıca aynı kimlikle çalışan süreçler birbirinin `/proc/<pid>/environ` içeriğini (dolayısıyla anahtarlarını) okuyabilir.

### 4.1 Root sahipli ağaç: `/usr/local/lib/trader-root/` (`ROOT_DIR`)
(`/opt/trader-root` **kullanılmaz**: `render()` içindeki `s#/opt/trader#…#` onu bozar.)

| Yol | İçerik | Sahip / kip |
|---|---|---|
| `ROOT_DIR/ssh/` | dağıtım anahtarının kopyası, sabit `known_hosts` | `root:root`, dizin `0700`, dosyalar `0600` |
| `ROOT_DIR/repo.git` | root'un **kendi** çıplak klonu (GitHub'dan root çeker) | `root:root` |
| `ROOT_DIR/releases/<COMMIT>/` | `git archive <COMMIT>` çıktısı: `src/`, `scripts/`, `deploy/`, `config/`, `requirements.lock` (`trader/` öneki atılmış) | `root:root`, grup/diğer yazamaz |
| `ROOT_DIR/current` | etkin sürüme sembolik bağ (atomik değişir: yeni bağ + `mv -T`) | `root:root` |
| `ROOT_DIR/venv/` | root'un sanal ortamı; yalnız `deploy/requirements-root.lock` | `root:root` |

Kurallar:
1. Root, `trader` sahipli depoda **hiçbir `git` komutu çalıştırmaz** ve oradan hiçbir betik/şablon **çalıştırmaz/okumaz** (o depodaki `git` işlemleri `as_trader` ile sürer). Root'un çalıştırdığı her şey (`install.sh`in kendisi, birim şablonları, env örnekleri, root birimlerinin betikleri) `ROOT_DIR/releases/<COMMIT>/` altından gelir.
2. `install.sh` sürümü hazırladıktan sonra, çalışan betiğin sha256'sı `ROOT_DIR/releases/<COMMIT>/deploy/install.sh` ile aynı değilse **o dosyayla** bir kez yeniden başlar (`TRADER_INSTALL_REEXEC`); `trader` deposundaki `install.sh` ile yeniden başlatma kaldırılır. Sunucu belgesi olağan komut olarak `bash /usr/local/lib/trader-root/current/deploy/install.sh` yazar (ilk geçişte bir kez eski yol).
3. `deploy/requirements-root.lock`: `requirements.lock` içinden yalnız `requests`, `certifi`, `charset-normalizer`, `idna`, `urllib3` paket bloklarının (sürüm + bütün `--hash` satırları) **birebir** kopyası. `ROOT_DIR/venv` root tarafından kurulur: `pip install --require-hashes --no-deps -r …/requirements-root.lock`.
4. Root birimleri (`trader-health.service`, `trader-backup.service`, `trader-engine-retry@.service`, `trader-engine-env-retry@.service`): `ExecStart=/usr/local/lib/trader-root/venv/bin/python -I /usr/local/lib/trader-root/current/scripts/<betik>.py …` ve `Environment=TRADER_DATA_ROOT=/opt/trader`. Bu birimlerde `/opt/trader/scripts`, `/opt/trader/src`, `/usr/bin/python3` ve `.venv` **geçmez**.
5. `TRADER_DATA_ROOT`: veri kökü. `scripts/health_run.py` içinde göreli veri yolu çözen yerler (`pause_base`, veto belgesi yolu) ve `TelegramConfig.from_env` içindeki `here`, değişken tanımlı ve mutlaksa onu kök alır; tanımsızsa bugünkü davranış. Kod kökü (içe aktarma yolu, `config/veto.json` okuması) betiğin kendi konumundan gelmeye devam eder.
6. Bu üç betiğin (ve içe aktardıklarının) üçüncü taraf bağımlılığı yalnız `requests` ve onun dört bağımlılığıdır; `pandas`, `numpy`, `pyarrow`, `anthropic` içe aktarılmaz.
7. Eski sürümler: `current` ve ondan önceki en çok iki sürüm kalır, diğerleri silinir (yalnız `ROOT_DIR/releases/` altındaki 40 onaltılık adlı dizinler).

### 4.2 Veto birimi
`trader-veto.service`: `User=trader`, `Group=trader` (root değil); `ExecStart` aynen (`<kök>` altından, `.venv` ile). `install.sh` her çalıştırmada `<kök>/shared/veto` ve `<kök>/user_data` altını `chown -hR trader:trader` yapar (önceden root'un yazdığı dosyalar). Birimin diğer satırları aynen.

### 4.3 Süreç ortam koruması — `src/trader_core/proc_guard.py` (yalnız stdlib/`ctypes`)
```python
def set_nondumpable() -> bool      # prctl(PR_SET_DUMPABLE, 0); başarı True; Linux değil/hata → False (istisna sızmaz)
def is_dumpable() -> bool | None   # prctl(PR_GET_DUMPABLE); okunamazsa None
```
Dökülemez süreçte `/proc/<pid>/environ` aynı kimlikli başka süreçlerce okunamaz. Çağrı yerleri (her biri sürecin ilk işlerinden, anahtar okunmadan önce):
- `cli._cmd_run`, yalnız `mode ∈ {testnet, live}`: `live`de `False` dönerse `ConfigError("proc_guard_failed")` → çıkış 2; `testnet`te `WARNING` ve devam. `paper`/`backtest`te **çağrılmaz**.
- `scripts/veto_run.py`, `scripts/lesson_run.py`, `scripts/telegram_run.py` (`main` başı): `False` → `WARNING`, devam.
- `scripts/smoke_live.py`, `scripts/smoke_testnet.py`: `False` → `WARNING`, devam.

**Fail-closed.** Root klonu `COMMIT`i içermiyorsa ya da arşiv çıkarılamazsa kurulum, `current` değişmeden durur (eski sürüm çalışmaya devam eder). Canlıda dökülemezlik kurulamazsa motor açılmaz.

**Dosyalar.** `deploy/install.sh`, `deploy/requirements-root.lock` (yeni), `deploy/trader-{health,backup,veto}.service`, `deploy/trader-engine-retry@.service`, `deploy/trader-engine-env-retry@.service`, `src/trader_core/proc_guard.py` (yeni), `src/trader_engine/cli.py`, `scripts/{health_run,veto_run,lesson_run,telegram_run,smoke_live,smoke_testnet}.py`, `src/trader_core/telegram.py` (`from_env`).

**Kabul testleri.**
- **R-1** Dört root biriminde (`health`, `backup`, `engine-retry@`, `engine-env-retry@`): `User=root`; `ExecStart` `/usr/local/lib/trader-root/venv/bin/python -I /usr/local/lib/trader-root/current/scripts/` ile başlar; metinde `/opt/trader/scripts`, `/opt/trader/src`, `/usr/bin/python3` yok; `Environment=TRADER_DATA_ROOT=/opt/trader` var. `render_units` sonrası `ExecStart` hâlâ `/usr/local/lib/trader-root/` ile başlar ve `TRADER_DATA_ROOT=<kök>` olur.
- **R-2** `deploy/` altında `User=root` taşıyan birim kümesi tam bu dörttür; `trader-veto.service` `User=trader` ve `Group=trader` taşır.
- **R-3** `requirements-root.lock`un yorum/boş dışı her satırı `requirements.lock` içinde birebir vardır; paket adları kümesi tam `{requests, certifi, charset-normalizer, idna, urllib3}`; her paketin `--hash` satır sayısı ana kilittekiyle eşit.
- **R-4** İçe aktarma kapanışı: `python -I` alt sürecinde `sys.path`e yalnız `scripts/` ve `src/` eklenip `health_run`, `health_backup`, `engine_retry`, `trader_core.telegram`, `trader_core.live_paths` içe aktarılır; `sys.modules` içinde `pandas`, `numpy`, `pyarrow`, `anthropic` yoktur.
- **R-5** `install.sh` metni: `git archive` ve `ROOT_DIR` (= `/usr/local/lib/trader-root`) geçer; root'un `git -C "$REPO_DIR"` çağrısı yoktur (`REPO_DIR` üzerindeki her `git` satırı `as_trader` ile başlar); `exec bash` hedefi `ROOT_DIR` altındadır, `$TRADER_DIR/deploy/install.sh` değildir; birim ve env şablonları sürüm dizininden okunur (`"$TRADER_DIR"/deploy/trader-` kalıbı kalmaz).
- **R-6** `install.sh` `chown -hR` ile `shared/veto` ve `user_data` yollarını `trader` sahipliğine alır.
- **R-7** `TRADER_DATA_ROOT=/x` iken `health_run.pause_base({"TRADER_DATA_ROOT": "/x"})` → `/x/shared/PAUSE`; `TelegramConfig.from_env({…token, chat…, "TRADER_DATA_ROOT": "/x"}).var_dir` → `/x/var/telegram`. Değişken yokken iki sonuç tabanla aynı. Göreli değer (`"x"`) yok sayılır (tabanla aynı).
- **R-8** `proc_guard`: alt süreçte `set_nondumpable()` → `True`, ardından `is_dumpable()` → `False`; aynı alt süreçte `open("/proc/self/environ")` sahibi (stat `st_uid`) 0'dır (Linux; değilse test atlanır).
- **R-9** `cli.main(["run", …, "--env","live"])`, `proc_guard.set_nondumpable` `False` dönecek biçimde yamalı → dönüş 2; `build_engine` çağrılmamış. Aynısı `testnet` → açılış sürer, `WARNING` var. `paper` → `set_nondumpable` çağrı sayısı 0.
- **R-10** `veto_run.main`, `lesson_run.main`, `telegram_run.main` çağrıldığında `set_nondumpable` tam bir kez çağrılır (yama ile); `False` dönüşü sonucu değiştirmez.
- **R-11** `proc_guard.py` yalnız stdlib içe aktarır.

---

## 5. C — `COMMIT` sabitleme, canlı etiketi, `install.sh --live` (O15)

**Sorun.** `install.sh` bir özellik dalının ucunu kuruyor; o dala giden her gönderim bir sonraki kurulumda root tarafından çalıştırılıyor. Canlı birim için "varsayılan kapalı" kuralı yok.

**Gerekli davranış.**
1. **`COMMIT` zorunlu.** Kaynak sırası: ortam değişkeni `COMMIT`; yoksa `/etc/trader-release` içindeki `COMMIT=` satırı; ikisi de yoksa `fail` ("COMMIT gerekli"), hiçbir şey değişmeden. Geçerli biçim tam 40 küçük onaltılık karakter (kısa sha, dal adı, etiket adı ret). İşlevler: `valid_commit <değer>` (çıkış 0/1) ve `resolve_commit` (stdout'a değeri yazar ya da 1 döner).
2. Root klonu `BRANCH` dalını ve `refs/tags/canli-*` etiketlerini çeker. `COMMIT` klonda yoksa ya da `origin/$BRANCH`in atası/kendisi değilse (`git merge-base --is-ancestor`) `fail` ("COMMIT yayın dalında değil"). `BRANCH` varsayılanı kullanıcı kararına kadar bugünkü değerdir (§11).
3. `trader` deposu: `as_trader git fetch` + `as_trader git checkout --quiet --detach "$COMMIT"`; `merge --ff-only` kalkar. Sonra `as_trader git rev-parse HEAD` `COMMIT`e eşit değilse ya da izlenen dosyalarda yerel değişiklik varsa (`git status --porcelain --untracked-files=no` boş değil) `fail`.
4. Kurulum başarıyla bitince `/etc/trader-release` (`root:root 0644`) tek satır `COMMIT=<sha>` ile yazılır (sır değildir). `CODE_CHANGED` = önceki `/etc/trader-release` değeri ile yeni `COMMIT` farklı mı.
5. **Canlı kipi.** `LIVE=1` şu iki durumda: `--live` bayrağı verildi **ya da** `/etc/systemd/system/trader-engine-live.service` zaten kurulu (yapışkan). `--no-live`: canlı birim ve `trader-engine-env-retry@live.timer` `disable --now` edilir, birim dosyası silinir, `LIVE=0`. `--live` ile `--no-live` birlikte → kullanım hatası (çıkış 2).
6. `LIVE=0` iken: `render` döngüsü `trader-engine-live.service` dosyasını **atlar**; canlıya özgü hiçbir `enable`/`start` çağrısı yapılmaz.
7. `LIVE=1` iken, sürüm hazırlandıktan hemen sonra ve herhangi bir birim/env değişmeden **önce** şu ön koşullar sırayla denetlenir; biri tutmazsa `fail`:
   a. `/etc/trader-live.env` var, `root:root 0600`, `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `LIVE_CONFIRM` dolu (`has_value`);
   b. `COMMIT` klonda `^canli-[0-9]{8}(-[0-9]+)?$` kalıbına uyan en az bir etiket taşıyor (`is_live_tag <ad>` işlevi kalıbı sınar);
   c. `as_trader <kök>/.venv/bin/python -m trader_engine pause --bot learner --env live --config-dir <kök>/config --list` çıkış 0 (canlı katman motorun kendi doğrulayıcısıyla yüklenir; `LIVE_CONFIRM` gerekmez, hiçbir şey yazılmaz).
8. `LIVE=1` ve ön koşullar tamam: (i) §6.4 canlı yol alanları env dosyalarına yazılır (`set_kv <dosya> <AD> <değer>`: satır varsa değiştirir, yoksa ekler; dosya sonu satır sonu korunur); (ii) canlı birim kurulur; (iii) `scripts/live_preflight.py` (§6.5) root kopyadan çalıştırılır, sıfırdan farklı çıkış → `fail` ve canlı birim `enable` edilmez; (iv) `systemctl enable trader-engine-live.service` (**`--now` yok; başlatılmaz**) ve `enable --now trader-engine-env-retry@live.timer`; (v) `enable_now trader-engine@learner.service` ve `trader-engine-retry@learner.timer` çağrıları **atlanır**; kâğıt learner hâlâ etkinse durdurulmaz, özete "kâğıt learner çalışıyor; canlıya geçiş listesine göre durdurun" uyarısı yazılır; (vi) Telegram daemon'u yeniden başlatılır.
9. `ACTIVE_ENGINES` listesine `trader-engine-live.service` eklenir (kod değiştiyse ve **zaten çalışıyorsa** yeniden başlatılır; çalışmıyorsa başlatılmaz).
10. `install -d` listesine `<kök>/var-live`, `<kök>/shared/live` eklenir (`0750 trader:trader`), her kurulumda.

**Fail-closed.** `COMMIT` yok/geçersiz/dal dışı → hiçbir şey değişmez. Etiketsiz commit canlıya kurulamaz; canlı kurulduktan sonra etiketsiz commit'le yapılan her kurulum da durur (yapışkan `LIVE`). Ön denetim başarısızsa canlı birim etkinleşmez.

**Dosyalar.** `deploy/install.sh`, `deploy/uninstall.sh`, `docs/sunucu-kurulum.md`.

**Kabul testleri** (işlevler `^ad\(\) \{.*?^\}` ile çıkarılıp `bash` altında çalıştırılır; mevcut `readiness_support` yöntemi).
- **C-1** `valid_commit`: 40 küçük onaltılık → 0; 39/41 karakter, büyük harf içeren, `main`, `canli-20261230`, boş → 1.
- **C-2** `resolve_commit`: ortamda `COMMIT=<a>` ve dosyada `COMMIT=<b>` → `<a>`; yalnız dosya → `<b>`; hiçbiri → çıkış 1; ortamda geçersiz değer → çıkış 1 (dosyaya düşmez). (Dosya yolu test için değişkenle değiştirilebilir: `RELEASE_FILE`.)
- **C-3** `is_live_tag`: `canli-20261230`, `canli-20261230-2` → 0; `canli-2026`, `live-20261230`, `canli-20261230-`, `xcanli-20261230` → 1.
- **C-4** `set_kv`: var olan `AD=eski` → `AD=yeni` (tek satır, diğer satırlar bayt-özdeş); olmayan anahtar sona eklenir; son satırı satır sonu olmadan biten dosyada ekleme ayrı satıra düşer; iki kez çalıştırma idempotent.
- **C-5** Metin: `merge --ff-only` yok; `checkout --quiet --detach` var; `merge-base --is-ancestor` var; `/etc/trader-release` yazımı var.
- **C-6** Metin: `--live` ve `--no-live` seçenekleri ayrıştırılır; `render` döngüsünde `trader-engine-live.service` `LIVE` koşuluna bağlı atlanır; `enable_now trader-engine-live.service` ve `enable --now trader-engine-live` **hiç geçmez**; `systemctl enable trader-engine-live.service` yalnız `LIVE` koşulu ve `live_preflight` çağrısından sonra geçer.
- **C-7** Kapı bloğu tmp dosyalarla çalıştırılır (test_wp_b8'deki `install_gate` yöntemi): `LIVE=1` iken (a) canlı env'de üç alandan biri boş → `fail` çağrılır, `systemctl` sahte kaydında canlı birim yok; (b) etiket listesi boş → `fail`; (c) hepsi dolu, etiket var, ön denetim 0 → kayıtta `enable trader-engine-live.service` var, `start`/`--now` canlı birim için yok. `LIVE=0` → kayıtta canlı birim hiç yok.
- **C-8** `--live --no-live` → çıkış 2.
- **C-9** `created_dirs()` `<kök>/var-live` ve `<kök>/shared/live` içerir.

---

## 6. Y — Canlı yolları: tek kaynak, Telegram, sağlık, yedek, ön denetim

**Sorun.** DD-8 canlı motoru `var-live` ve `shared/live/…` yollarına zorluyor; ama Telegram, sağlık ve yedek tek bir `ENGINE_VAR_DIR` / `PAUSE_FILE` / `KILL_FILE` biliyor. Canlıda öğrenen bot canlı dizinde, ikiz kâğıt dizininde çalışacak. Yol elle çevrilirse ve bir dosya unutulursa Telegram kâğıt KILL dosyasını kurar (canlı motor görmez), sağlık kâğıt dizinini izler, canlı defter yedeklenmez. `11-canli-broker.md` §12'deki "`kill_file`/`pause_file` varsayılan kalır" cümlesi DD-8 ile çelişir ve geçersizdir.

### 6.1 `src/trader_core/live_paths.py` (yeni, yalnız stdlib)
```python
class LivePathError(ValueError):
    code: str
def live_bots(env) -> tuple[str, ...]                 # LIVE_BOTS virgüllü; boş/yok → ()
def validate_live_env(env) -> None                    # LIVE_BOTS boşsa hiçbir şey; değilse aşağıdaki kurallar, ihlal → LivePathError
def bot_var_dir(env, bot: str, default_var: str) -> str        # bot canlıysa LIVE_VAR_DIR, değilse default_var
def bot_pause_base(env, bot: str, default_base: str) -> str    # bot canlıysa LIVE_PAUSE_FILE, değilse default_base
def expected_from_config(config_dir) -> dict          # engine.live.json → {"var_dir","kill_file","pause_file","account_tag"} (yollar mutlak)
def check_against_config(env, config_dir) -> tuple[str, ...]   # uyuşmazlık kodları (boş demet = tutarlı)
```
`validate_live_env` kuralları (ilk ihlalin kodu): `LIVE_BOTS` `("learner",)` dışında bir şey → `live_bots_invalid`; `LIVE_VAR_DIR` yok/boş → `live_var_dir_missing`, mutlak değil → `live_var_dir_relative`, son bileşeni `var` → `live_var_dir_paper`; `LIVE_PAUSE_FILE` yok/boş → `live_pause_missing`, mutlak değil → `live_pause_relative`, son iki bileşeni `shared/PAUSE` → `live_pause_paper`. `bot_var_dir` / `bot_pause_base` canlı bot için önce `validate_live_env` çağırır (geçersizse `LivePathError`).

`expected_from_config`: `<config_dir>/engine.live.json` doğrudan JSON olarak okunur (`trader_engine` içe aktarılmaz); kök kuralı `config.absolutize_paths` ile aynı (dizin adı `config` ise üstü, değilse kendisi); dosya yok/bozuk/alan eksik → `LivePathError("live_config_missing")`.

`check_against_config` (yollar `os.path.normpath` sonrası dizgi olarak karşılaştırılır; ortamda **bulunmayan** anahtar denetlenmez): `validate_live_env` hatası → `(<o kod>,)`; `live_config_missing`; `LIVE_VAR_DIR ≠ var_dir` → `var_dir_mismatch`; `LIVE_PAUSE_FILE ≠ pause_file` → `pause_file_mismatch`; `KILL_FILE ≠ kill_file` → `kill_file_mismatch`; `ENGINE_STATUS_PATH ≠ <var_dir>/learner/status.json` → `status_path_mismatch`; `LEDGER_PATH ≠ <var_dir>/learner/ledger.sqlite` → `ledger_path_mismatch`; `LADDER_BOTS` kümesi `LIVE_BOTS` kümesinden farklı → `ladder_bots_mismatch`. `LIVE_BOTS` boşsa sonuç `()`.

### 6.2 Telegram (`scripts/telegram_run.py`, `src/trader_core/telegram.py`)
1. `build_pauses` ve `build_ladders`: her bot için `var = bot_var_dir(env, b, <ENGINE_VAR_DIR çözümü>)`, `base = bot_pause_base(env, b, <PAUSE_FILE çözümü>)`. `LIVE_BOTS` boşken çıktı tabanla aynı.
2. `main` (`daemon` ve `report`): `check_against_config(env, <config dizini>)` boş değilse stderr'e yalnız kodları yazar ve `EXIT_CONFIG` döner (yanlış dosyaya KILL/duraklatma yazan daemon çalışmaz; alarmı §8.3 verir). Config dizini: `ENGINE_CONFIG_DIR`, yoksa `<kod kökü>/config`.
3. `LIVE_BOTS` doluysa daemon `expect_status_mode="live"` ile kurulur (§7).
4. **Karar (mentor):** canlıdan sonra Telegram'ın `KILL_FILE`ı canlı motorun dosyasıdır; `/hepsini_kapat` ve `/devam` (KILL katmanı) yalnız canlı botu etkiler, kâğıt ikizin `shared/KILL` dosyasına Telegram dokunmaz (ikiz sunucuda CLI ile durdurulur). `/durdur` her iki bota kendi dosyasından uygulanır.

### 6.3 Sağlık ve yedek (`scripts/health_run.py`, `scripts/health_backup.py`)
1. `health_run.collect`: bot başına `<var>/<bot>/…` kuran **her** yer (durum, defter, süreç, duraklatma denetim günlüğü, ML durumu) `bot_var_dir` kullanır; duraklatma tabanı `bot_pause_base`. Disk yoklamasına `LIVE_VAR_DIR` eklenir. `LivePathError` olursa canlı botlar için boş yoklamalar (`ApiProbe(expect_exchange=True)`, `LedgerProbe()`, `PauseProbe()`) üretilir ve §8.3 kodu taşınır; sağlık koşusu çökmez.
2. `health_backup.run_backup(..., bot_dirs: Mapping[str, str] | None = None)`: `bot_dirs` canlı botların dizinini verir. İş listesi: her bot için bugünkü iki iş (`ledger_<bot>.sqlite`, `state_<bot>.sqlite`; kaynak `ENGINE_VAR_DIR`) **artı** her canlı bot için `ledger_<bot>@live.sqlite`, `state_<bot>@live.sqlite` (kaynak `LIVE_VAR_DIR`; spool ve `.spool.corrupt` kopyaları aynı kuralla). Canlı bir botun kâğıt işi, kaynak `ledger.sqlite` iş listesi kurulurken **yoksa** listeye alınmaz (arşivlenmiş kâğıt dizini yedeği başarısız saymaz); varsa yedeklenmeye devam eder (kâğıt geçmişi 14 günlük dönüşte kaybolmasın). `main`: `LIVE_BOTS` doluysa `bot_dirs` kurar; `LivePathError` → canlı işler `ok=false`, neden `live_env_invalid`, diğer işler sürer, çıkış `EXIT_FAILED`.
3. `trader-backup.service` `ReadWritePaths`ine `-/opt/trader/var-live` eklenir. `trader-telegram.service` ve `trader-lesson.service` `ReadWritePaths`ine `-/opt/trader/var-live/learner`, `trader-telegram-report.service` `ReadOnlyPaths`ine `-/opt/trader/var-live/learner` eklenir.

### 6.4 `install.sh --live`in yazdığı alanlar (sır değil; `set_kv`)
| Dosya | Alanlar |
|---|---|
| `/etc/trader-telegram.env` | `KILL_FILE=<kök>/shared/live/KILL`, `ENGINE_STATUS_PATH=<kök>/var-live/learner/status.json`, `LEDGER_PATH=<kök>/var-live/learner/ledger.sqlite`, `LIVE_BOTS=learner`, `LIVE_VAR_DIR=<kök>/var-live`, `LIVE_PAUSE_FILE=<kök>/shared/live/PAUSE`, `LADDER_BOTS=learner`, `ENGINE_CONFIG_DIR=<kök>/config` |
| `/etc/trader-health.env` | `LIVE_BOTS=learner`, `LIVE_VAR_DIR=<kök>/var-live`, `LIVE_PAUSE_FILE=<kök>/shared/live/PAUSE` |
| `/etc/trader-lesson.env` | `LEDGER_PATH=<kök>/var-live/learner/ledger.sqlite` |

`ENGINE_VAR_DIR`, `PAUSE_FILE`, `PAUSE_BOTS`, `HEALTH_BOTS`, `TWIN_LEDGER_PATH` **değişmez** (ikiz kâğıtta kalır). Env örneklerine bu alanlar boş değerle ve "install.sh --live doldurur" yorumuyla eklenir; `trader-health.env.example` sonundaki "CANLIYA CIKISTA ENGINE_VAR_DIR'i çevirin" yorumu silinir. Not: sağlık birimleri iki env dosyasını da yükler ve aynı adlı alanlarda Telegram dosyası geçerli olur; iki dosyanın eşitliğini §6.5 denetler.

### 6.5 Ön denetim — `scripts/live_preflight.py` (root kopyadan, root venv ile; ağ yok)
`main(argv=None, *, etc_dir="/etc", config_dir=None, id_groups=None) -> int`. Her denetim için stdout'a tek satır `OK <kod>` ya da `FAIL <kod>` yazar; **hiçbir değer yazmaz**. Biri `FAIL` → dönüş 1, hepsi `OK` → 0. Denetimler (kodlar):
- `env_perms`: `etc_dir` altındaki her `trader-*.env` düz dosya, sahibi uid 0, kipi tam `0600` (test için sahip denetimi `--skip-owner` ile kapatılabilir).
- `live_env_complete`: `trader-live.env` içinde üç alan dolu; anahtar ve gizli anahtar en az 32 karakter, boşluksuz.
- `live_confirm_matches`: `LIVE_CONFIRM` = `expected_from_config(...)["account_tag"]`.
- `keys_not_testnet`: `trader-live.env` `BINANCE_API_KEY` değeri `trader-testnet.env`deki dolu değerle **aynı değil** (testnet dosyası yok/boşsa `OK`).
- `telegram_paths`, `health_paths`, `lesson_paths`: ilgili env dosyası tek başına ayrıştırılıp `check_against_config` boş; ayrıca Telegram ve sağlık dosyalarında `LIVE_BOTS == "learner"`.
- `trader_not_in_tg`: `trader` kullanıcısının grupları arasında `trader-tg` yok (`id_groups` enjekte edilebilir; varsayılan `grp`/`pwd` ile).
- `release_pinned`: `etc_dir/trader-release` var ve `COMMIT=` 40 onaltılık.

### 6.6 `deploy/canli_duman.sh` (root çalıştırır; duman testi sarmalayıcısı)
Anahtar dosyası `0600 root` olduğundan `trader` kullanıcısı onu okuyamaz; belgede geçen `set -a; . /etc/trader-live.env` yolu kaldırılır. Betik `systemd-run --pty --wait --collect -p User=trader -p Group=trader -p WorkingDirectory=<kök> -p EnvironmentFile=/etc/trader-live.env -p Environment=PYTHONPATH=<kök>/src <kök>/.venv/bin/python scripts/smoke_live.py --env live "$@"` çalıştırır. Anahtarları okumaz, yazdırmaz, `set -x` içermez; root değilse ya da `/etc/trader-live.env` yoksa çıkış 1.

**Fail-closed.** Tutarsız canlı yolu = Telegram daemon'u açılmaz + sağlık CRIT + canlı birim etkinleştirilmez. `LIVE_BOTS` boşken bu bölümün hiçbir kodu davranış değiştirmez.

**Dosyalar.** `src/trader_core/live_paths.py`, `scripts/live_preflight.py`, `deploy/canli_duman.sh` (yeniler); `scripts/telegram_run.py`, `scripts/health_run.py`, `scripts/health_backup.py`, `deploy/install.sh`, `deploy/trader-{telegram,health}.env.example`, `deploy/trader-lesson.env.example`, `deploy/trader-{backup,telegram,telegram-report,lesson}.service`.

**Kabul testleri.**
- **Y-1** `validate_live_env`: `{}` ve `{"LIVE_BOTS": ""}` → istisnasız. `LIVE_BOTS=twin` / `learner,twin` → `live_bots_invalid`. Sırasıyla eksik/göreli/`…/var` `LIVE_VAR_DIR` → `live_var_dir_missing` / `_relative` / `_paper`; eksik/göreli/`…/shared/PAUSE` `LIVE_PAUSE_FILE` → `live_pause_missing` / `_relative` / `_paper`. Geçerli küme → istisnasız.
- **Y-2** `bot_var_dir(env, "learner", "/k/var")` → `LIVE_VAR_DIR`; `bot_var_dir(env, "twin", "/k/var")` → `/k/var`; `LIVE_BOTS` boşken ikisi de `/k/var`. `bot_pause_base` aynı kalıpla.
- **Y-3** `expected_from_config("<kök>/config")` sonucu `load_cli_config("<kök>/config", "learner", env="live")` ile alan alan eşit (`var_dir`, `kill_file`, `pause_file`, `live.account_tag`). Dizin adı `cfgx` iken kök `cfgx`. Dosya yok → `LivePathError`, `code == "live_config_missing"`.
- **Y-4** `check_against_config`: §6.4 tablosundaki Telegram alanlarının tamamı (kök = geçici dizin) → `()`. Her alan tek tek bozulduğunda yalnız ilgili kod döner: `var_dir_mismatch`, `pause_file_mismatch`, `kill_file_mismatch` (ör. `<kök>/shared/KILL`), `status_path_mismatch` (ör. `<kök>/var/learner/status.json`), `ledger_path_mismatch`, `ladder_bots_mismatch` (`LADDER_BOTS=""`). `KILL_FILE` anahtarı hiç yokken `kill_file_mismatch` dönmez. `LIVE_BOTS` boş → `()`.
- **Y-5** `build_pauses(env)`: `PAUSE_BOTS=learner,twin`, canlı alanlar dolu → `learner` yolu `<LIVE_PAUSE_FILE>.learner`, denetim günlüğü `<LIVE_VAR_DIR>/learner/pause_audit.jsonl`; `twin` yolu `<PAUSE_FILE>.twin`, günlük `<ENGINE_VAR_DIR>/twin/pause_audit.jsonl`. `build_ladders` `learner` için günlük `<LIVE_VAR_DIR>/learner/risk_ladder.jsonl`, durum `<LIVE_VAR_DIR>/learner/status.json`.
- **Y-6** `telegram_run.main(["daemon"], env=…)`: `LIVE_BOTS=learner` + `KILL_FILE=<kök>/shared/KILL` → dönüş `EXIT_CONFIG`; daemon kurulmamış (HTTP çağrısı 0); stderr `kill_file_mismatch` içerir, token içermez. Tutarlı env → daemon kurulur. `LIVE_BOTS` yok → tabanla aynı.
- **Y-7** `health_run.collect`: `HEALTH_BOTS=learner,twin`, canlı alanlar dolu; `var-live/learner/status.json` `mode=live`, `var/twin/status.json` `mode=paper` → `api["learner"].mode == "live"`, `api["twin"].mode == "paper"`; `pause["learner"]` canlı dosyadan okunmuş (yalnız canlı dosyada tutuş varken `holds` dolu).
- **Y-8** `collect`, `LIVE_BOTS=learner`, `LIVE_VAR_DIR` yok → istisnasız; `api["learner"].expect_exchange is True` ve `ping_ok is None`; `live_path_issues == ("live_var_dir_missing",)`.
- **Y-9** `run_backup(..., bots=("learner","twin"), bot_dirs={"learner": <var-live>})`: manifest dosya anahtarları `ledger_learner.sqlite`, `state_learner.sqlite`, `ledger_twin.sqlite`, `state_twin.sqlite`, `ledger_learner@live.sqlite`, `state_learner@live.sqlite`; hepsi `ok`. Kâğıt `var/learner/ledger.sqlite` yokken → kâğıt learner anahtarları manifestte yok, yedek `ok`. `bot_dirs=None` → manifest tabanla aynı anahtarlar.
- **Y-10** `health_backup.main`, `LIVE_BOTS=learner`, `LIVE_VAR_DIR` eksik → çıkış `EXIT_FAILED`; canlı girdiler `ok=false`; ikiz girdileri `ok`.
- **Y-11** `live_preflight.main`: tutarlı düzenek → dönüş 0, her satır `OK …`. Tek tek bozulan durumlar ilgili `FAIL` kodunu verir ve dönüş 1: bir env dosyası `0640`; `LIVE_CONFIRM` farklı; canlı ve testnet anahtarı aynı; Telegram dosyasında `KILL_FILE` kâğıt yolu; sağlık dosyasında `LIVE_VAR_DIR` farklı; `id_groups=("trader","trader-tg")`; `trader-release` yok. Hiçbir durumda stdout/stderr anahtar, gizli anahtar ya da `LIVE_CONFIRM` değerini içermez (sızma testi: değerler `SIZMA-…` ile başlar).
- **Y-12** `canli_duman.sh`: `bash -n` geçer; metinde `systemd-run`, `User=trader`, `EnvironmentFile=/etc/trader-live.env`, `smoke_live.py --env live` var; `set -x`, `cat /etc/trader-live.env`, `source`, `. /etc/` yok.
- **Y-13** Env örnekleri: `trader-telegram.env.example` ve `trader-health.env.example` `LIVE_BOTS=`, `LIVE_VAR_DIR=`, `LIVE_PAUSE_FILE=` satırlarını boş değerle taşır; `render_env_files` çıktısında (canlısız kurulum) üçü de boştur.
- **Y-14** `live_paths.py` yalnız stdlib içe aktarır (`trader_engine`, `requests` yok).

---

## 7. T — Telegram `/devam`: "pozisyonlar kapandı mı" her kipte (O7)

**Sorun.** `_devam_refusal` `status.mode ∈ {paper, backtest}` ise `kill_state == "flat"` şartını atlıyor (`telegram.py:1055-1060`). `ENGINE_STATUS_PATH` kâğıt dosyasında kalırsa `/devam` canlı pozisyonlar kapanmadan KILL'i kaldırabilir.

**Gerekli davranış.** `TelegramDaemon.__init__`e `expect_status_mode: str | None = None` eklenir. `_devam_refusal` sırası:
1. KILL yapılandırılmamış → "kill dosyasi yapilandirilmadi" (aynen).
2. KILL etkin değil → "KILL etkin degil" (aynen).
3. Durum okunamıyor → "durum okunamadı, reddedildi" (aynen).
4. **Yeni:** `expect_status_mode` verilmiş ve `status.mode` ona eşit değil → ret; ileti "beklenen kipte değil" ifadesini içerir.
5. `kill_state == "exiting"` → "kapanis suruyor, bekleyin" (aynen).
6. `mode` `paper`/`backtest` değilse köken kuralı (KILL `telegram:` + `user_cmd` değilse ret; aynen).
7. **Değişen:** `kill_state != "flat"` → "pozisyonlar kapanmadi (durum flat degil), reddedildi" — **her kipte** (`paper` dahil).

Duraklatma katmanı (`_pause_devam_refusal`) ve `tick_kill_watch` değişmez.

**Fail-closed.** Eksik/yanlış tipte `kill_state` = `flat` değildir → ret.

**Dosyalar.** `src/trader_core/telegram.py`, `scripts/telegram_run.py`, `docs/telegram-spec.md` (§5.2 notu).

**Kabul testleri.**
- **T-1** KILL etkin, `status = {"mode": "paper", "kill_state": "exiting"}` → ret (aynen). `{"mode": "paper", "kill_state": None}` / anahtar yok / `"none"` → **ret** ("flat degil"); KILL dosyası yerinde. (Tabanda bu durum kabul ediliyordu.)
- **T-2** `{"mode": "paper", "kill_state": "flat"}` → kod gönderilir; onayda KILL kalkar.
- **T-3** `{"mode": "live", "kill_state": "flat"}`, KILL `by="telegram:482"`, `reason="user_cmd"` → kabul. `kill_state="exiting"` → ret. KILL `by="cli"` → ret (köken; aynen).
- **T-4** `expect_status_mode="live"`, `status.mode="paper"`, `kill_state="flat"`, KILL Telegram kökenli → **ret** ("beklenen kipte"). `status.mode` anahtarı yok → ret. `expect_status_mode=None` → bu denetim yapılmaz.
- **T-5** Kod gönderildikten sonra, onaydan önce durum `exiting`e dönerse onay adımı da reddeder (onay yolu `_devam_refusal`i yeniden çağırır; aynen).
- **T-6** `telegram_run.main(["daemon"])`: `LIVE_BOTS=learner` (tutarlı env) → daemon `expect_status_mode == "live"` ile kurulur; `LIVE_BOTS` yok → `None`.
- **T-7** Mevcut `/devam` testlerinden kâğıt kipinde `kill_state` vermeden kabul bekleyenler düzenek tarafında `kill_state="flat"` ile güncellenir; kural gevşetilmez.

---

## 8. H — Sağlık: hesap modu alarmı, canlı kipin yapılandırmadan türetilmesi, yol tutarlılığı

### 8.1 `account_mode` alarmı (DD-7 devir 2 + inceleme notu)
**Sorun.** DD-8 `account_mode_drift` / `account_mode_unverified` sayaçları yalnız günlükte; `status.json` `exchange` bloğu beyaz listeli olduğu için dosyaya da çıkmıyor (DD-8 §5'teki "status.json'a çıkar" cümlesi fiilen doğru değil). Ayrıca yasak penceresinde her giriş denemesi `account_mode_unverified`i artırıyor; alarm bağlanırsa her yasakta yanlış alarm üretir.

**Gerekli davranış.**
1. `brokers/binance_futures.py`: yeni sayaç `account_mode_unverified_ban` (`_COUNTERS`a eklenir). `_verify_account_mode`in `ExchangeBan` dalında `account_mode_unverified` **ile birlikte** bu sayaç da +1 (DD-8 D2-4 değişmez). Başka dalda artmaz.
2. `status.py` `_exchange_block`: yeni alan `"account_mode": {"drift": int|None, "unverified": int|None, "unverified_ban": int|None}` (broker sağlık sözlüğünden; `int` olmayan/eksik → `None`).
3. `H.ApiProbe` sona, varsayılanlı: `acct_drift: int | None = None`, `acct_unverified: int | None = None`, `expect_exchange: bool = False`. `probe_status`: `acct_drift = drift`; `acct_unverified = max(unverified - unverified_ban, 0)` (üçünden biri `None` ise ilgili alan `None`).
4. `H.HealthSnapshot` sona: `prev_account_mode: Mapping[str, tuple[int, int]] | None = None` (bot → önceki koşudaki `(acct_drift, acct_unverified)`); `health_run` bunu durum dosyasında `account_mode` anahtarıyla saklar (`ml_score_errors` ile aynı düzen; `None` değerler saklanmaz).
5. Yeni denetim `account_mode:<bot>`, yalnız `_live_mode(a)` doğruysa. Artış hesabı (her iki sayaç için): önceki değer yok → 0; şimdiki < önceki (süreç yeniden başlamış) → şimdiki; aksi → fark. Öncelik: `acct_drift`/`acct_unverified` `None` → `UNKNOWN` `account_mode_unknown`; drift artışı ≥ 1 → `CRIT` `account_mode_drift` (değer = artış); unverified artışı ≥ 1 → `WARN` `account_mode_unverified`; aksi `OK`.
6. `account_mode_drift` `IMMEDIATE_CODES`a, `account_mode_unverified` `IMMEDIATE_WARN_CODES`a eklenir. Türkçe metinler: drift başlık "Hesap ayarı değişmiş, yeni işlem açılmadı" (gövde: kaldıraç ya da marjin tipi botun ayarından farklı; Binance'te elle değiştirildiyse eski haline getirin), düzelme "Hesap ayarı yeniden doğru"; unverified başlık "Hesap ayarı doğrulanamadı, bir giriş atlandı", düzelme "Hesap ayarı yeniden doğrulanıyor".

### 8.2 Canlı kip yapılandırmadan türetilir (inceleme notu)
**Sorun.** `status.json` yok ya da okunamıyorsa `has_exchange=False` ve `mode=None` olur; `_c_exchange_ban` "açık pozisyon var" saymaz (yalnız `WARN`), `naked_position` ve `exchange_reachable` denetimleri hiç üretilmez.

**Gerekli davranış.** `health_run.collect` şu yoklamalarda `expect_exchange=True` kurar (dosya okunamasa da): `LIVE_BOTS` içindeki botlar ve `learner@testnet` gölge yoklaması. `_live_mode(a)` = `a.has_exchange or a.mode in ("testnet","live") or a.expect_exchange`. `_c_exchange_ban`de "açık pozisyon var" = herhangi bir yoklamada `(has_exchange or expect_exchange)` ve `open_trade_ids` boş değil **ya da `None`**.

### 8.3 Yol tutarlılığı
`H.HealthSnapshot` sona: `live_path_issues: tuple[str, ...] | None = None`. `collect`: `LIVE_BOTS` boş → `None`; dolu → `check_against_config(env, ENGINE_CONFIG_DIR)` sonucu **artı** her canlı bot için durum dosyası okunabildiği halde `mode != "live"` ise `status_mode_mismatch:<bot>`. Denetim `live_paths` (tek satır): `None` → üretilmez; `()` → `OK`; aksi → `CRIT` kod `live_paths_mismatch`, ayrıntıda kodlar. `IMMEDIATE_CODES`a eklenir. Metin başlık "Canlı bot ayar yolları tutarsız", gövde "Telegram ya da sağlık yanlış dosyaya bakıyor olabilir; sunucuda kurulum yeniden çalıştırılmalı", düzelme "Canlı bot ayar yolları düzeldi".

### 8.4 Sapma izleyicisi
`LIVE_BOTS` içindeki bot için `drift_monitor:<bot>` denetimi üretilmez (canlı yol desteği ayrı paket; yanlış `drift_missing` alarmı istenmez). Kâğıt botlar için değişmez.

**Fail-closed.** Bilinmeyen = alarm (`UNKNOWN`/`CRIT`); canlı botun durum dosyası yoksa yasak sırasında `CRIT` verilir.

**Dosyalar.** `src/trader_engine/brokers/binance_futures.py`, `src/trader_engine/status.py`, `src/trader_core/health.py`, `scripts/health_run.py`, `docs/saglik-spec.md`.

**Kabul testleri.**
- **H-1** Broker: `position_risk` `ExchangeBan(429)` → `account_mode_unverified == 1` ve `account_mode_unverified_ban == 1`; `ExchangeUncertain` → `1` ve `0`. `health()` sözlüğü üç sayacı taşır.
- **H-2** Canlı/testnet motorun `status.json` `exchange.account_mode` bloğu üç tam sayı taşır; `mode=paper` durum dosyasında `exchange` bloğu yoktur (tabanla aynı anahtar kümesi).
- **H-3** `probe_status`: `{"drift": 2, "unverified": 5, "unverified_ban": 3}` → `acct_drift == 2`, `acct_unverified == 2`. `unverified_ban > unverified` → `0`. Blok yok → ikisi de `None`.
- **H-4** `evaluate`: `mode="live"`, `prev=(0, 0)`: `(1, 0)` → `CRIT` `account_mode_drift`; `(0, 1)` → `WARN` `account_mode_unverified`; `(0, 0)` → `OK`; `(None, 0)` → `UNKNOWN` `account_mode_unknown`. `prev` yok, şimdiki `(4, 7)` → `OK`. `prev=(5, 9)`, şimdiki `(1, 0)` → `CRIT` (yeniden başlama). `mode="paper"` yoklamada denetim yok.
- **H-5** Yalnız yasak kaynaklı artış (ör. `unverified` 0→4, `unverified_ban` 0→4) → `account_mode:<bot>` `OK`.
- **H-6** `plan_alerts`: iki kod da ilk görüşte alarm üretir; sonraki koşuda artış 0 → düzelme iletisi. Metin tablosunda üç kodun Türkçe karşılığı var.
- **H-7** Uçtan uca: `run_once` iki kez; ilk koşuda `(0,0)`, ikincide `(0,2)` içeren durum dosyası → ikinci koşuda `account_mode_unverified` alarmı; durum dosyasında `account_mode` anahtarı güncel.
- **H-8** `bans=(etkin kayıt,)` + `api={"learner": ApiProbe(expect_exchange=True)}` (durum dosyası yok hâli) → `exchange_ban` `CRIT` `exchange_ban_open_positions`. `expect_exchange=False` aynı yoklama → `WARN` `exchange_ban` (tabanla aynı).
- **H-9** `ApiProbe(expect_exchange=True)` → raporda `naked_position:<bot>` ve `exchange_reachable:<bot>` denetimleri vardır (`UNKNOWN`).
- **H-10** `collect`: `HEALTH_SHADOW_VAR_DIR` dolu, gölge durum dosyası yok → `api["learner@testnet"].expect_exchange is True`. `LIVE_BOTS=learner`, canlı durum dosyası yok → `api["learner"].expect_exchange is True`. Kâğıt bot → `False`.
- **H-11** `live_path_issues=None` → raporda `live_paths` yok; `()` → `OK`; `("kill_file_mismatch",)` → `CRIT` `live_paths_mismatch`, ilk koşuda alarm.
- **H-12** `collect`: `LIVE_BOTS=learner`, canlı durum dosyası `mode="paper"` → `live_path_issues` `status_mode_mismatch:learner` içerir.
- **H-13** `LIVE_BOTS=learner` iken raporda `drift_monitor:learner` yok, `drift_monitor:twin` var.
- **H-14** Var olan `ApiProbe(...)` ve `HealthSnapshot(...)` kurucuları bozulmadan çalışır.

---

## 9. D — Devralınan küçükler

### 9.1 `write_ban` dizini `fsync` etmiyor (DD-7 inceleme notu)
`ban_store.write_ban`: `os.replace` başarılı olduktan sonra hedef dizin `O_RDONLY` açılıp `fsync` edilir ve kapatılır. Dizin `fsync` hatası (`OSError`) `WARNING` yazar ve sonuç yine `True`dur (dosya yerindedir; davranış değişmez).
- **D1-1** Başarılı yazımda `os.fsync` en az iki kez çağrılır ve çağrılardan biri bir **dizin** tanımlayıcısıdır (`os.fstat` + `stat.S_ISDIR`; yama ile kayıt).
- **D1-2** Dizin `fsync`i `OSError` atacak biçimde yamalanır → `write_ban` `True`; dosya geçerli kayıt taşır; istisna sızmaz. DD-7 P-1…P-11 değişmeden geçer.

### 9.2 `health_backup._copy_corrupt` (DD-7 devir 3)
Boyut okuması yalnız `FileNotFoundError`ı "dosya yok" sayar (→ 0). Başka her `OSError` yükselir (çağıran girdiyi `ok=false` yapar, yedek başarısız). `_copy_spool` aynı kurala çekilir.
- **D2-1** `.spool.corrupt.jsonl` yerinde okunamayan bir giriş (ör. `os.path.getsize` `PermissionError` atacak biçimde yamalı) → ilgili defter girdisi `ok=false`, çıkış `EXIT_FAILED`. Dosya yok → DD-8 E4-2 aynen.

### 9.3 `smoke_live.guard_config` (DD-7 devir 4)
Bugün yalnız "son bileşenlerde `testnet` geçmesin" deniyor; kâğıt yolu (`shared/KILL`) ya da rastgele bir dizin geçer. Yeni kural **olumlu eşleşmedir**: `var_dir` son bileşeni tam `var-live`; `kill_file` son üç bileşeni `shared/live/KILL`; `pause_file` son üç bileşeni `shared/live/PAUSE`; aksi `SafetyError`. Kip ve `LIVE_CONFIRM` denetimleri aynen. (Bu kural `config._validate`e **konmaz**; DD-8 O8-1 sözleşmesi değişmez.)
- **D3-1** Depodaki canlı katman (`load_cli_config(..., env="live")`) + doğru `LIVE_CONFIRM` → geçer.
- **D3-2** `var_dir="/x/var-canli"`, `kill_file="/x/shared/KILL"`, `kill_file="/x/live/KILL"`, `pause_file="/x/shared/testnet/PAUSE"` → her biri `SafetyError`. Kök dizin adı `var-live` olan ama son bileşeni farklı yol → `SafetyError`.

### 9.4 Damga, şema göçünden önce (DD-7 devir 5)
**Sorun.** `build_engine` (`testnet`/`live`) defteri `create=True` ile açarken eski şemalı **yabancı** bir defteri damga reddinden önce göç ettiriyor (dosyayı değiştiriyor, `premigrate` yedeği bırakıyor).

**Gerekli davranış.** `trader_core/ledger.py`: `peek_meta(path, key) -> str | None` — dosya yok ya da 0 bayt → `None`; salt okunur açar (göç, şema kurulumu, yazma yok); `meta` tablosu ya da satır yok → `None`; okunamayan dosya → `LedgerError`. `build_engine` (`testnet`/`live`), state kilidinden sonra ve defteri açmadan önce: `Lp = peek_meta(cfg.ledger_path, "account_stamp")`; `LedgerError` → `EngineExit(8, "ledger_stamp_mismatch")`; `Lp` var ve `≠ want` → `EngineExit(8, "ledger_stamp_mismatch")`; sonra `open_ledger(create=True, migrate=(Lp == want))`; `migrate=False` iken `LedgerSchemaError` (eski şema, damgasız) → `EngineExit(8, "ledger_stamp_missing")`. Ardından DD-8 karar tablosu aynen. `paper`/`backtest` yolu değişmez.
- **D4-1** Eski şemalı (v3; `tests/test_wp3_impl.py` düzeneğiyle kurulan) defter, `meta.account_stamp="live:baska"`, kip `testnet` → çıkış 8 `ledger_stamp_mismatch`; defter dosyası sha256'sı ve `PRAGMA user_version` değişmemiş; dizinde `premigrate` içeren ad yok; borsaya istek 0.
- **D4-2** Eski şemalı damgasız defter → çıkış 8 `ledger_stamp_missing`; dosya değişmemiş, `premigrate` yok.
- **D4-3** Eski şemalı, damgası `want` olan defter + `want` damgalı state → göç çalışır (`user_version` güncel, `premigrate` yedeği var), açılış sürer.
- **D4-4** Defter dosyası yok → ilk açılış DD-8 O8-3 ile aynı. `peek_meta` yok/0 bayt/`meta`sız dosyada `None`; bozuk dosyada `LedgerError`; hiçbir durumda dosya içeriği değişmez.
- **D4-5** `paper` motor kurulumu `peek_meta`yı çağırmaz (çağrı sayacı 0); altın geri test bit-özdeş.

### 9.5 Şartname metin düzeltmeleri (kod değişmez)
- DD-8 şartnamesi §2.3: "`build_engine` ve `cli._cmd_unblock` `cfg.ledger_path` geçirir" cümlesi "`ledger_path` yalnız **paper** kipinde geçirilir; `testnet`/`live`de `StateStore` `ledger_path` almaz, eksik/0 bayt state'i karar tablosu (4. satır) yakalar" olarak düzeltilir (DD-7 devir 6). Aynı belgede §5'teki "`health()` üzerinden `status.json`a çıkar" cümlesi "DD-9 §8.1 ile `exchange.account_mode` bloğunda çıkar" olarak düzeltilir; §8 "Test dosyaları" satırındaki `tests/test_health_dd8.py` gerçek dosyalara göre düzeltilir.
- DD-7 şartnamesindeki iki düzeltme (§5 ret etiketi, §7 test dosya adları) bu şartnameyle birlikte mentor tarafından yapıldı.

---

## 10. B — Belgeler, notlar, teslim koşulları

**Belgeler (bu paketle birlikte güncellenir).**
- `docs/motor/11-canli-broker.md`: §2 dosya adları (`trader-live.env.example`, canlı birim; `live.conf.example` ve `trader-binance.env.example` silinir); §3.2 env dosyası adı `/etc/trader-live.env`; §3.3 birim satırı (`2 7 8`, süresiz yeniden deneme); §9.5 `/devam` kuralı; §12 "Canlıya geçiş" paragrafı yeniden yazılır: `kill_file`/`pause_file` `shared/live/…`, Telegram ve sağlık yollarını `install.sh --live` yazar, Telegram KILL'i yalnız canlı botu etkiler, sıra aşağıdaki "Canlıya geçiş günü" listesidir.
- `docs/sunucu-kurulum.md`: `COMMIT` ile kurulum, root kopya yolu, env izinleri, "Canlıya çıkışta izleme dizini" paragrafı (elle çevirme talimatı silinir), duman testi hazırlığı (`canli_duman.sh`), canlıya geçiş günü listesi, testnet dizini arşiv adımı (mevcut DD-8 paragrafı korunur).
- `docs/saglik-spec.md`: yeni denetimler ve alanlar. `docs/telegram-spec.md`: §5.2 notu.

**Canlıya geçiş günü listesi (belgeye yazılır; bu paket bunu çalıştırmaz).** (1) kâğıt learner KILL ile düzlenir, `systemctl disable --now trader-engine@learner trader-engine-retry@learner.timer`; (2) kullanıcı `nano /etc/trader-live.env` ile üç alanı yazar; (3) `COMMIT=<etiketli sha> bash /usr/local/lib/trader-root/current/deploy/install.sh --live`; (4) `capital init` (12 §14); (5) `canli_duman.sh` ile duman testi (ayrı gün); (6) `pause --bot learner --env live --reason manual --by <ad>` ile ilk açılış tutuşu; (7) `systemctl start trader-engine-live`; (8) mutabakat temizse tutuş kaldırılır. Sıra mentor eşliğinde uygulanır.

**Notlar.**
- **Not-1 (gölge koşu = prova).** Testnet birimi canlı birimle aynı sertleştirme ve yeniden başlatma ayarlarını taşıdığı için 14 günlük gölge koşu bu ayarların kanıtıdır. D-9 "plansız yeniden başlatma" sayımı `status.started_at` değişiminden yapılır; süresiz yeniden deneme ölçütü değiştirmez.
- **Not-2 (ders servisi).** `LEDGER_PATH`in canlı deftere çevrilmesi ders servisinin canlı işlemlerden öğrenmesi demektir; canlıya geçiş kararında mentor ayrıca gözden geçirir (§6.4 satırı o güne kadar yalnız `--live` ile etkinleşir).
- **Not-3 (kalan risk).** Süreç başlangıcı ile `set_nondumpable` arasındaki birkaç milisaniyede ortam aynı kimlikli süreçlerce okunabilir; kabul. Tam ayrım (canlı motor için ayrı kullanıcı) ertelendi.
- **Not-4 (etiket).** `canli-YYYYAAGG[-N]` etiketini CI yeşil olduktan sonra mentor atar; imzalı etiket şartı yok (süreç disiplini; teknik koruma `COMMIT` + dal atası denetimidir).

**Test dosyaları.** Şartname testleri (bağımsız ajan): `tests/engine/test_dd9_spec.py` (K, U-1…U-4, R-8…R-11, H-1, H-2, D3, D4) ve `tests/test_dd9_deploy_spec.py` (geri kalanı: birimler, `install.sh`, `live_paths`, Telegram, sağlık, yedek, `ban_store`). Uygulama testleri: `tests/engine/test_dd9_impl.py`, `tests/test_dd9_deploy_impl.py`. Dosya adları tekildir (`test_engine_test_names_unique`).

**Teslim.** Tüm test paketi yeşil; altın geri test bit-özdeş; dondurulmuş dosyalarda ve `deploy/trader-engine@.service`te `git diff` boş; `bash -n` ve (varsa) `shellcheck -S warning` `install.sh`, `uninstall.sh`, `canli_duman.sh` için temiz; `tests/engine/test_engine_module_inventory.py` değişmeden geçer (yeni modüller `trader_core` altında); yeni bağımlılık yok; depoda hiçbir sır yok.

---

## 11. Kullanıcıya gidecek kararlar ve sunucu adımları

**Karar gereken tek konu (bu paketi başlatmayı engellemez):**
1. **Yayın dalı.** Triyajdaki "kullanıcı kararı 1" (telifli PDF'lerin temizliği için depoyu silip yeniden oluşturma ve dağıtım dalının `main` olması) hâlâ açık. DD-9 her kurulumu tek bir sürüme sabitliyor; "hangi daldan" sorusu bu karara bağlı. Karar gelene kadar bugünkü dal kullanılır.

**Bilgi (karar gerekmez; hepsi sıkılaştırma, mentor kararı):**
- Canlı hesap etiketi `canli-alt1` olarak sabitlendi; canlıya geçiş günü anahtar dosyasına bu sözcük de yazılacak.
- Kasa tavanı kararınız (1500 USD) canlı ayar dosyasına işlendi.
- Canlıdan sonra Telegram'daki "hepsini kapat" yalnız gerçek parayla çalışan botu kapatır; kâğıttaki ikiz bot bundan etkilenmez. "Durdur" ikisine de uygulanır.
- Bundan sonra kurulum komutu her seferinde mentorun verdiği 40 karakterlik sürüm koduyla çalışır; kod verilmeden kurulum yapılmaz.
- Canlı bot, kurulumda özel bir sözcük (`--live`) yazılmadıkça sunucuya hiç kurulmaz; yazılsa bile kendiliğinden başlamaz.

**Sunucu adımları — şimdi (DD-9 birleştikten sonra, en geç 13 Aralık).** Hepsi DigitalOcean konsolunda, sırayla, her seferinde tek komut. `<KOD>` yerine mentorun vereceği 40 karakter yazılır.
1. Testnet deneme motorunu durdurun: `systemctl stop trader-engine-testnet`
2. Eski deneme klasörü daha önce taşınmış mı bakın: `ls /home/trader/SG-Github-AB-proje/trader/var-testnet` — listede `learner.pre-dd8-…` diye bir ad **varsa 3. adımı atlayın**.
3. Eski deneme kayıtlarını arşive taşıyın (silinmez): `mv /home/trader/SG-Github-AB-proje/trader/var-testnet/learner /home/trader/SG-Github-AB-proje/trader/var-testnet/learner.pre-dd8-$(date +%Y%m%d)` — "No such file" derse sorun değil, devam edin.
4. Yeni sürümü kurun (birkaç dakika sürer): `COMMIT=<KOD> bash /home/trader/SG-Github-AB-proje/trader/deploy/install.sh`
5. Deneme motorunun çalıştığını görün: `systemctl status trader-engine-testnet --no-pager` — yeşil "active (running)" yazmalı.
6. Ayar dosyalarının kilitli olduğunu görün: `ls -l /etc/trader-*.env` — her satır `-rw-------` ile başlamalı ve `root root` yazmalı.
7. Çıktıları (4, 5 ve 6. adımların ekranını) mentora iletin. Dosyaların **içini** göndermeyin.

Bundan sonraki kurulumlarda 4. adımın komutu şudur: `COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh`

**Canlıya geçiş günü (şimdi değil; mentor eşliğinde):** gerçek anahtarın `nano /etc/trader-live.env` ile yazılması ve §10'daki sekiz adım. O güne kadar bu dosya boş kalır.
