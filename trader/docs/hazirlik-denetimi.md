# Paper hazirlik denetimi (30 Kasim baslangici; DigitalOcean 2 GB, baska proje ile paylasimli)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. İkiz, veto tazeliği/HMAC, gölge dönem ve canlı hazırlık maddeleri kâğıt için geçersiz (ikiz/veto/gölge kaldırıldı; gerçek para askıda).

Kapsam: statik + kuru kosu. Strateji/ML mantigi, kilitli donem ve canli islem kapsam disi. Ag yok (Binance 451), gercek anahtar yok.
Yontem: `deploy/install.sh`'in GERCEK `render()` sed'i ve env kopyalama adimlari tmp dizinde calistirildi; sahte Binance REST + tmp "sunucu" agaci ile
feed/motor/saglik/panel/yedek surec-ici ve alt surec olarak kosturuldu. Kanitlar `tests/readiness/` altindadir
(`.venv/bin/python -m pytest tests/readiness -q`). `xfail(strict)` testler ACIK kusurlari belgeler: duzeltilince test kirilir, isareti kaldirin.

Durum: **OK** = dogrulandi, **FIX** = bu denetimde duzeltildi, **OPEN** = acik (duzeltme onerisi asagida; uygulanmadi).

## 1. Ozet

| Sayi | Durum |
|---|---|
| OK | 26 (madde 8 bellek: OK+belgeli risk) |
| FIX | 5 |
| OPEN | 10 (1 engelleyici P0, 5 yuksek P1, 4 dusuk/orta) |

**Karar:** Bu haliyle paper baslangici icin ENGELLEYICI olan: OPEN-1 (motor HMAC anahtarini gormuyor -> veto belgesi ne olursa olsun hicbir giris acilmaz).
30 Kasim'dan once duzeltilmesi gerekenler: OPEN-1, OPEN-3, OPEN-4, OPEN-5. Ders servisi (OPEN-2, OPEN-6) paper baslangicinda KAPALI tutulursa engel degil.

## 2. Madde tablosu

| # | Madde | Durum | Kanit |
|---|---|---|---|
| 1.1 | Her ExecStart/ExecStartPre gercek modul + alt komut/betige cozulur (engine run/init-ledger, feed, panel, 8 betik) | OK | `test_readiness_units_render::test_exec_lines_resolve_to_real_module_script_subcommand` (render sonrasi metin uzerinde) |
| 1.2 | Render sonrasi `/opt/trader`, `/usr/bin/python3`, eski `/home/trader/trader` kalintisi yok; python = `<repo>/.venv/bin/python` | OK | `test_no_placeholder_left_after_render` (17 birim) |
| 1.3 | WorkingDirectory ve `PYTHONPATH=<repo>/src` dogru; `python -m trader_*` birimlerinde ikisi de var; `-I` betikler kendi `sys.path`'ini kurar | OK | `test_working_directory_and_pythonpath...`, `test_module_units_have_workingdirectory_and_pythonpath`, `test_readiness_imports` (betikler `-I` ile calisir) |
| 1.4 | Her EnvironmentFile install.sh tarafindan olusturuluyor (5 dosya) | OK | `test_environment_files_are_created_by_install` |
| 1.5 | `ReadOnlyPaths=/var/lib/trader-health` (panel) ilk acilista yok -> `226/NAMESPACE`, panel baslamaz; install `trader-health.timer`'dan once/es zamanli panel'i baslatir (yaris) | **FIX** | `deploy/trader-panel.service`: `-/var/lib/trader-health`. `test_namespace_paths_exist_after_install` (onekisiz her yol sunucuda olusacak mi?) |
| 1.6 | `RestartPreventExitStatus` = kodun cikis kodlari (motor 7, feed 6); 8 birimde `OnFailure=trader-health-fail@%n` | OK | `test_restart_semantics_match_exit_codes` |
| 1.7 | `docs/sunucu-kurulum.md` kurulan paketler listesi yanlisti (websockets, ccxt) | **FIX** | install.sh yalniz requests pandas numpy pyarrow anthropic kurar; belge duzeltildi |
| 1.8 | Timer -> servis eslesmesi, her timer install.sh'te etkinlestiriliyor/kapili | OK | `test_every_timer_has_a_service_and_is_enabled_or_gated` |
| 2.1 | install.sh paket kumesi 9 giris noktasinin (engine, feed, panel, health, lesson, veto, telegram, telegram-report, backup) tum ice aktarmalarini (tembel olanlar dahil: `requests`, `anthropic`, `pandas`) karsiliyor | OK | `test_readiness_imports` (her biri ayri `python -I` sureci; yuklenen 3. parti modul kapanisi = bildirilen paketler + gecisli bagimliliklar) |
| 2.2 | `ml_mode=off` iken ML/gelistirme paketi (scipy, lightgbm, sklearn, yaml, pytest, ccxt, websockets, trader_ml) yuklenmiyor; `requirements-ml.txt` sunucuya kurulmuyor | OK | ayni test (`ml_loaded` bos); `test_install_declares_expected_runtime_packages` |
| 2.3 | `requests` (Telegram, feed) pip satirinda var | OK | ayni test (`requests` her iki giriste yuklenir) |
| 2.4 | Node/wrangler yalniz pano yayini icin; Cloudflare anahtari yokken zamanlayici kapali | OK (statik) | `test_publish_timer_gated_and_wrangler_pinned` (kuru kosu yapilamadi: npm agi yok) |
| 3.1 | `engine.base/learner/twin.json` anahtarlari dogrulaniyor; mode=paper, veto_mode=required, ml_mode=off, 10 cift | OK | `test_engine_configs_load_for_both_bots_and_pairs_agree_everywhere` |
| 3.2 | `veto.json` cift listesi (`config/base.json:exchange.pair_whitelist`) motorun `pairs` listesiyle ayni (iki ayri liste; birini degistirip digerini unutmak veto'yu eksik birakir) | OK (kirilgan) | ayni test |
| 3.3 | veto/panel/lesson/budget yapilandirmalari yukleniyor | OK | `test_other_configs_load` |
| 3.4 | Env ornekleri render sonrasi dogru yollar: `ENGINE_VAR_DIR`, `MARKET_DB`, `ENGINE_CONFIG_DIR`, `TELEGRAM_VAR_DIR`, `KILL_FILE` motorla birebir | OK | `test_engine_var_paths_match_health_panel_telegram`, `test_kill_file_...`, `test_telegram_outbox_dir...` |
| 3.5 | `ENGINE_STATUS_PATH=` bos: Telegram `/durum` ve gunluk rapor "durum okunamadi" derdi | **FIX** | `deploy/trader-telegram.env.example` -> `/opt/trader/var/learner/status.json`. `test_telegram_engine_status_path_points_to_learner_status` |
| 3.6 | `HEARTBEAT_URL` bos birakilirsa `trader-health` her 5 dk `rc=1` ("beklenmeyen hata: ValueError") ile coker; install ozeti uyarmiyordu | **FIX** | `deploy/install.sh` "YAPILACAKLAR" listesine `HEARTBEAT_URL` eklendi (davranis degismedi, yalniz uyari). Kalan: hata mesaji eksik degiskenin adini gizliyor (kozmetik) |
| 3.7 | var/ alt dizinleri ve sahiplik: `var`, `shared`, `shared/veto`, `user_data`, `var/telegram` (0750 trader), `var/telegram/outbox` (2770 trader:trader-tg), `/var/backups/trader` (0750 root). Yazma: motor+feed `var shared user_data`; telegram `var/telegram shared`; veto `shared/veto user_data var`; health `/var/lib/trader-health`; yedek `/var/backups/trader`; panel yalniz okur | OK | `test_install_pre_creates_what_strict_units_need`, `test_telegram_outbox...`, `test_backup_paths_and_timer` |
| 3.8 | `shared/veto/veto.json` 0644, dizin trader:0750; veto root yazar, motor/panel/telegram (trader) okur | OK | `veto.write_veto_file` (`chmod 0644`), install.sh `install -d -m 0750 -o trader` |
| 4 | Ilk baslatma runbook'u (12 adim, komut + beklenen cikti) | **FIX** (yeni) | `docs/sunucu-kurulum.md` "Ilk gun runbook"; adimlarin cekirdegi tatbikat testinde calisir: `test_rehearsal_empty_server_feed_rules_gate_status_health` |
| 5.1 | Ag yok / HTTP 451 (feed): 451 -> cikis 6 + CRITICAL, `RestartPreventExitStatus=6`; kural 5xx -> cikis 5; ag yok -> kural yazilmaz, motor kapisi acilmaz | OK | `test_drill_feed_451_exits_6...`, `test_drill_feed_exchangeinfo_5xx_exits_5`, `test_drill_feed_no_network_fails_loudly_not_silently` |
| 5.2 | Feed olur -> motor `data_stale=10` (status.json) -> saglik `market_bars_stale` CRIT, dis nabiz `fail` hemen, bildirim 2. turda (~5-10 dk, `confirm_runs`) | OK | `test_drill_feed_killed_midrun_engine_data_stale_and_health_crit` |
| 5.3 | Bir cift kuralsiz -> motor kapisi cikis 7, tek CRITICAL satir cifti adlandirir; veri bayat -> cikis 7 "veri bayat"; 10/10 + taze -> kalkar, `status.json` yazar, SIGTERM ile 0 | OK | `test_drill_one_pair_missing_rules_engine_gate_exit_7`, `..._stale_data_...`, `..._gate_passes_...` (gercek `python -m trader_engine`, goreli yollar, cwd=tmp) |
| 5.4 | Veto: anahtar yok / belge yok / belge eski / yanlis imza / butce siniri -> `lookup` her durumda `blocks=True` (`missing`/`stale` + neden kodu); gecerli taze belge -> `allowed` | OK (motor tarafi) | `test_drill_veto_failure_modes_block_entries_visibly`, `test_drill_veto_fresh_valid_document_allows`. Gozlenebilirlik kusuru: OPEN-5 |
| 5.5 | Telegram anahtari yok: `telegram_run.py send` cikis 1 + "telegram yapilandirilmamis"; OnFailure zincirinde `-` onekli, zincir kirilmaz; `health_fail.sh` journal'a `daemon.crit` yazar, `HEARTBEAT_FAIL_URL` yoksa "atlandi" yazar. Yani CRIT YALNIZ journal'da (+ dis nabiz); telefona dusmez | OK (belgeli) | `test_drill_telegram_keys_missing_crit_goes_to_journal_not_silence`. Anahtar var ama ag yok: mesaj spool'a yazilir (`test_drill_telegram_send_with_keys_but_no_network_spools_not_drops`). Saglik CRIT'i Telegram'a gitmez: OPEN-3 |
| 6.1 | Ikiz: ayri `var/twin/{ledger,state,status}`, tek `market.sqlite` (motor `read_only=True`), ortak KILL, `start_delay_s=3` (yalniz ikiz), sablon birim tek feed'e bagli, `install.sh` once feed sonra motorlar | OK | `test_twin_is_isolated_from_learner_but_shares_feed`, `test_sqlite_market_db_opened_read_only_by_engine` |
| 6.2 | Varsayilan kurulumda ikiz KAPALI ama saglik ikizi zorunlu sayar -> `api_unreachable:twin` CRIT surekli, nabiz hep `fail`; yedek ikiz defterini ister -> her gun `source_missing` | OPEN-4 | `test_OPEN_health_is_not_crit_in_learner_only_deployment`, `test_OPEN_backup_is_ok_in_learner_only_deployment` (xfail). Iki bot varken saglik OK/WARN(warmup), yedek OK, geri yuklenebilir: `test_rehearsal_...`, `test_backup_of_running_engines_ledgers_is_ok_and_restorable` |
| 7.1 | KILL yolu motor (`shared/KILL`), Telegram (`KILL_FILE`), panel (`kill_file`) ayni; yazma izinleri dogru (motor/telegram RW, panel RO); tatbikatta motor kill'i koyunca iki bot + panel gorur | OK | `test_kill_file_same_path_in_engine_telegram_panel`, `test_panel_reads_status_ledger_health_and_kill_file_is_shared` |
| 7.2 | Yedek zamanlayici (03:10 UTC, root, `/var/backups/trader` RW, `var` RO, `ENGINE_VAR_DIR` ayni); canli (WAL acik) defter yedegi alinir ve `integrity_check=ok` | OK | `test_backup_paths_and_timer`, `test_backup_of_running_engines...` |
| 7.3 | Pano: 2 botu `live` okur, defter/saglik uclari `ok` | OK | `test_panel_reads_...` |
| 8 | Bellek: her zaman acik tavanlar 350+350+350+64+96 = **1210 MB**; kisa omurlu en kotu ek 1072 MB -> **2282 MB** > 2048 MB RAM, < 6144 MB (RAM+takas) | OK (belgeli) / OPEN-9 | `test_readiness_memory.py`. Olculen ice aktarma RSS: feed ~19 MB, panel ~25, telegram ~21, veto ~17 (+pandas ~100), motor ~105 MB; gercek kullanim tavanlarin cok altinda beklenir ama olculmedi |

## 3. ACIK maddeler (oncelik sirasiyla)

### OPEN-1 (P0, ENGELLEYICI) Motor veto HMAC anahtarini gormuyor
`gates.FileVeto` anahtari `os.environ["TRADER_VETO_HMAC_KEY"]`'ten okur (`engine.py:898,910`). `trader-engine@.service`'te `EnvironmentFile` yok;
anahtar yalniz `/etc/trader-veto.env`'de (root:root 0600, ayrica API anahtarini da icerir). Sonuc: veto servisi kusursuz calissa bile motor her adayi
`veto_missing / key_missing` ile eler; HICBIR giris acilmaz. (`ders-spec`/`veto-spec` "iki botun ortamina ayni anahtar" der; birim bunu yapmiyor.)
Kanit: `test_OPEN_engine_unit_receives_veto_hmac_key` (xfail).
Oneri (secim gerektirir, uygulanmadi): `/etc/trader-veto-hmac.env` (root:root 0600, yalniz `TRADER_VETO_HMAC_KEY=`); `trader-veto.service` ve
`trader-engine@.service` ikisi de `EnvironmentFile=` olarak okusun; `/etc/trader-veto.env` yalniz `ANTHROPIC_API_KEY_VETO` kalsin (API anahtari motora sizmasin);
install.sh'e `copy_env` + `has_value` kapisi + ornek dosya. Alternatif (daha kotu): motor birimine `EnvironmentFile=-/etc/trader-veto.env` (API anahtari motor surecine girer).

### OPEN-2 (P1) Ders ve Telegram birimleri SQLite yan dosyalarini olusturamaz (ProtectSystem=strict)
`trader-lesson.service` ve `trader-telegram.service` `user_data` altinda yalniz DOSYA yollari listeler (`-.../budget.sqlite`, `lesson.sqlite`, `-wal`, `-shm`);
dizin salt okunur kalir. `budget.sqlite` `journal_mode=DELETE` (her yazimda `budget.sqlite-journal` olusturulur), `lesson.sqlite` WAL (`-wal/-shm` olusur)
-> `unable to open database file`. Mount namespace'te (`unshare -m`, `ro` dizin + dosya bind) tekrarlandi: dosya-duzeyi RW basarisiz, dizin-duzeyi RW calisir.
Kanit: `test_sandbox_file_level_rw_cannot_create_sqlite_journal_or_wal` (fizik), `test_OPEN_lesson_and_telegram_can_create_sqlite_sidecars` (xfail). Gercek systemd'de dogrulanmadi (bu konteynerde yok).
Oneri: iki birimde `ReadWritePaths=/opt/trader/user_data` (motor ve veto zaten boyle). Telegram'da ikiz defteri `ReadOnlyPaths` ile salt okunur kalir.

### OPEN-3 (P1) Saglik CRIT'i Telegram'a gitmiyor
`trader-health.service` yalniz `/etc/trader-health.env` okur (`NOTIFIER=log` varsayilan); `trader-telegram.env` yok, `/var/.../var/telegram` yazma izni yok.
Sonuc: `plan_alerts` bildirimleri (ornegin `market_bars_stale`) yalniz journal'a (`LogNotifier`) yazilir. Telefona yalniz (a) birim `failed` olunca OnFailure CRIT'i,
(b) gunluk rapor ve (c) dis nabiz servisinin kendi alarmi duser. Feed oldugunda (birim aktif ama veri akmiyor) telefon alarmi YOK.
Oneri: health.service'e `EnvironmentFile=-/etc/trader-telegram.env`, `SupplementaryGroups=trader-tg`, `ReadWritePaths=... /opt/trader/var/telegram`; `NOTIFIER=telegram` (anahtar yokken `make_notifier` ValueError verir: install.sh
yalniz anahtarlar doluyken `NOTIFIER=telegram` yazsin). O zamana kadar: dis nabiz servisinde e-posta/SMS alarmi sart; runbook adim 7.

### OPEN-4 (P1) Varsayilan kurulum (ikiz kapali) saglik ve yedegi bozuk gosterir
Bkz. tablo 6.2. Kanit: iki xfail test. Oneri (en basiti): 30 Kasim'da `install.sh --with-twin` (350 MB tavan; bellek tablosu uygun). Kalici: saglik/yedek `require_bots`'u `engine@*` etkin birimlerinden ya da env'den (`HEALTH_BOTS=learner`) alsin.

### OPEN-5 (P1) Veto durumu gercek zamanli GORUNMUYOR
`health.evaluate` veto kontrolu (`veto_file_age`) `SKIPPED` (health_run `veto_file_mtime`/`veto_max_age_s` beslemiyor); `status.json` `entries_open: true` der (kapi veto'yu kapsamaz);
panel veto'yu gostermez. Veto durmus/anahtarsiz ise yalniz defterde `skip_reason=veto_missing|veto_stale` ve gunluk Telegram raporunda gorunur; saatlerce sessiz "giris yok" olabilir (belgeli "giris kapali" durumu ama alarm yok).
Kanit: `test_rehearsal_...` (`veto_file_age == SKIPPED`), `test_drill_gate_passes_...` (`entries_open True`). Oneri: health_run `shared/veto/veto.json` mtime + `veto_max_age_s≈5400` besler (kod mevcut, yalniz baglanti); runbook adim 9 sorgusu gunluk el ile.

### OPEN-6 (P1) Ders servisi uc ayri nedenle calismaz
(a) `config/lesson.json` `notifier: null` -> `lesson_run.py --once` cikis 1 "bildirimci yapilandirilmamis" (dogrudan calistirilarak dogrulandi) -> her saat OnFailure.
(b) `LEDGER_PATH`/`ledger_path` = `user_data/ledger_learner.sqlite` (`ledger_twin` de ayni) ama motor defterleri `var/<bot>/ledger.sqlite`; telegram env'i de ayni yolu kullanir -> gunluk raporun defter bolumleri bos/"defter yok". Pano ve saglik dogru yolu kullanir.
(c) OPEN-2.
Kanit: `test_OPEN_lesson_config_has_a_notifier`, `test_OPEN_lesson_and_telegram_ledger_path_is_the_engine_ledger` (xfail). Oneri: paper baslangicinda `/etc/trader-lesson.env` BOS birakin (timer acilmaz; runbook adim 0). Sonra: notifier=`telegram`; env/config yollarini `var/learner|twin/ledger.sqlite` yapin; lesson ve telegram birimlerine `var/learner` (yazma, aktivasyon icin) ve `var/twin` (okuma) yollarini verin.

### OPEN-7 (dusuk) Feed: ag yok iken traceback, cikis 1
`Feed.start -> _measure_offset -> GET /time` kurallardan once calisir; `ExchangeError` `feed.main()`'de yakalanmaz. Etki yok (yine `failed` + OnFailure; `Restart=always` 20 sn arayla dener), yalniz cikis kodu 1 + traceback.
Oneri: `main()`'de `except (ExchangeError, DataError)` -> `log.critical` + `EXIT_RULES`. Test: `test_drill_feed_no_network_fails_loudly_not_silently`.

### OPEN-8 (orta, kod okumasi; calistirilmadi) `budget.sqlite` sahibi
`budget.py` ilk olusturmada dosyayi 0600 yapar (sahip = olusturan). Veto root calisir; ilk olusturan veto ise dosya root:root 0600 olur ve `trader` kullanicili ders/telegram acamaz.
Oneri: install.sh `install -m 0600 -o trader -g trader /dev/null user_data/budget.sqlite` (bos dosya "ilk olusturma" sayilir; root yine yazar).

### OPEN-9 (orta) Bellek: slice tavani yok, diger proje payi bilinmiyor
**Durum (WP-D): slice YAPILDI, sayilar GECICI.** `deploy/trader.slice` (`MemoryHigh=1100M`, `MemoryMax=1300M`) eklendi; her `deploy/*.service` `Slice=trader.slice` icinde; `trader-panel-publish` `OOMScoreAdjust=500`, motor ve feed `OOMScoreAdjust=-200` (system birimi, root yonetici uygular; `NoNewPrivileges`/`ProtectSystem` engellemez; bir konteynerde reddedilirse birim yine baslar ancak ayar uygulanmaz). install.sh slice'i kurar + daemon-reload; uninstall.sh siler. Kesin sayilar soak'in ilk 48 saatlik `systemd-cgtop` verisinden sonra (docs/sunucu-kurulum.md "Bellek ölçümü"). Cloudflare yayini bellek verisi (48 sa) + bos RAM >= ~900 MB olmadan acilmaz. Testler: `tests/readiness/test_readiness_memory.py`.
Tavan toplamlari: her zaman acik 1210 MB (RAM'in %59'u), en kotu ust uste binme 2282 MB. Diger projenin kullanimi bu depodan olculemez. `MemoryHigh` (280 MB) yumusak sinir, `vm.swappiness=10`, 4 GB takas var.
Oneri: (1) kurulumdan once `free -m` + diger projenin RSS'i; (2) `trader.slice` (`MemoryMax=1300M`, `MemoryHigh=1100M`) altina tum trader birimleri; (3) pano yayini (node/wrangler, 400 MB tavan, 5 dk'da bir) en pahali kisa omurlu birimdir: ilk hafta kapali tutulabilir; (4) ikizi 2. gun acmak yerine ilk gunden acmak OPEN-4 icin gerekli (350 MB).

### OPEN-10 (dusuk) Motor durmusken yedek/pano/saglik defteri okuyamaz
Dizin salt okunur bagli iken WAL defteri yalniz yazici baglanti aciksa (`-wal/-shm` var) okunur; temiz kapanista bu dosyalar silinir. Motor `failed` (kapi 7) iken 03:10 yedegi `backup_error`, pano `wal_yok_salt_okunur` (pano bunu kodlu bildirir; fizik `unshare` ile dogrulandi). Yedek basarisizligi `exit 20` + manifest `ok:false` -> saglik `backup_age`.
Oneri: yedek birimi `ReadOnlyPaths` yerine `ReadWritePaths=var` ile (root, yedek `mode=ro` URI kullanmaya devam eder).

## 4. Motor birimi `RestartPreventExitStatus=7`: arti/eksi ve oneri (YAPILDI: WP-C)

**Durum (17 Kasim 2026):** `RestartPreventExitStatus=7` kaldi; `scripts/engine_retry.py` + `deploy/trader-engine-retry@.service/.timer` eklendi (install.sh learner ve ikiz icin etkinlestirir). Yalniz `failed` + cikis 7 + saglikli besleme (feed-status <=180 sn, rules >= cift sayisi, her cift son 1m bar <=180 sn) iken yeniden baslatir; cikis 6/yapilandirma hatasi yeniden denenmez; saatte en fazla 6 deneme (`/var/lib/trader-health/engine-retry.json`), tukenince tek CRIT. Testler: `tests/readiness/test_readiness_retry.py`.

Davranis: kapi (kural/veri 10/10 degil, `startup_wait_s=600` sn sonra) cikis 7 -> `Restart=on-failure` bunu YENIDEN BASLATMAZ -> birim `failed` -> OnFailure CRIT.

| Arti | Eksi |
|---|---|
| Kapi 10 dk bekledikten sonra yeniden baslatma "yeniden 10 dk bekle" dongusu olurdu; alarm 5x (StartLimit) sonra gelirdi. Simdi tek, hizli, net alarm | Gecici feed gecikmesi (Binance 5xx, feed yeniden baslama, ilk backfill uzun) tek basina motoru **kalici** kapatir; kimse mudahale edene kadar paper islem yok, zaman kaybi (ozellikle gece/hafta sonu) |
| Hatali yapilandirmada (cift listesi/kural) sonsuz dongu yok; `StartLimit` yorulmasi yok | Feed `Restart=always` ile kendini toparlasa bile motor ayakta kalmaz; saglik "motor yok" CRIT'i, alarm yorgunlugu |
| `systemctl start` ile bilincli yeniden baslatma sureci | Boot sirasinda: feed ilk backfill'i bitirmeden `startup_wait_s` bitebilir (soguk bos sunucu: ilk acilista tam bu senaryo) |

Oneri (uygulandi): **`trader-engine-retry@.timer`** (her 5 dk) + oneshot servis: `systemctl is-failed trader-engine@%i` ise VE feed saglikliyse (`var/feed-status.json` taze, `market.sqlite` `rules` 10 satir, son 1m mum < 3 dk) `systemctl reset-failed` + `systemctl start`; en fazla N=6 deneme/saat, deneme sayisi `/var/lib/trader-health` altinda tutulur; her denemede INFO, limit dolunca tekrar CRIT. Boylece (1) gecici feed sorunu kendiliginden iyilesir, (2) kalici sorun (451/yanlis cift) yine tek net alarmla kalir. Ek kucuk adim: `trader-engine@.service`'e `After=` yerine ilk acilista feed'in ilk backfill'ini bekleyen bir `ExecStartPre` yoktur; `startup_wait_s`'i ilk gun 1800'e cikarmak (config'te mevcut anahtar) en ucuz azaltimdir.

## 5. Bu denetimde yapilan degisiklikler (hepsi mekanik)

| Dosya | Degisiklik |
|---|---|
| `deploy/trader-panel.service` | `ReadOnlyPaths`: `/var/lib/trader-health` -> `-/var/lib/trader-health` (+ aciklama) |
| `deploy/trader-telegram.env.example` | `ENGINE_STATUS_PATH=/opt/trader/var/learner/status.json` (bos degil) |
| `deploy/install.sh` | `HEARTBEAT_URL` bos ise "YAPILACAKLAR" listesinde uyar |
| `docs/sunucu-kurulum.md` | paket listesi duzeltildi; Telegram'siz OnFailure notu; "Ilk gun runbook" eklendi |
| `docs/hazirlik-denetimi.md` | bu belge |
| `tests/readiness/` | `readiness_support.py`, `test_readiness_{units_render,imports,paths,drills,memory}.py` (50 gecer + 6 xfail) |

Dokunulmadi: `marketdata/sources.py`, `backtest.py`, `research/ml_build_candidates.py`, `tests/ml/*`, `tests/engine/test_engine_01_spec.py`, calisan sureclere.
