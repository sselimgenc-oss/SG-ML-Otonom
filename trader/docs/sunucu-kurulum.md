# Sunucu kurulumu (DigitalOcean, Ubuntu)

> 18 Kasım: kullanıcı kararıyla değişti. Kurulumda ikiz birimi (`trader-engine@twin`), veto servisi/anahtarları ve gölge (`ml-shadow`) drop-in'i kâğıt için kaldırıldı; canlı anahtar konmaz (gerçek para askıda). Sunucu 2 GB kalır.

Hedef: mevcut droplet (FRA1, 1 vCPU, 2 GB RAM). Sunucuda calisan **baska proje bozulmaz**: yalniz `trader` kullanicisina, `/home/trader` dizinine ve `trader-*` adli systemd birimlerine dokunulur. Guvenlik duvari degistirilmez, disariya acik port acilmaz. Kendi bilgisayarinize hicbir sey kurulmaz.

## Tek komut

DigitalOcean paneli > droplet > **Access > Launch Droplet Console** ile konsolu acin, su satirlari yapistirip Enter'a basin:

```
apt-get install -y -qq git && git clone --branch claude/charming-hawking-ab5w5q https://github.com/sselimgenc-oss/SG-Github-AB-proje.git /root/trader-kurulum && COMMIT=<KOD> bash /root/trader-kurulum/trader/deploy/install.sh
```

**DD-9: kurulum her zaman tek bir surume sabitlenir.** `<KOD>` mentorun verdigi 40 karakterlik (kucuk harfli) commit kodudur; kisa kod, dal ya da etiket adi kabul edilmez, kod verilmeden kurulum yapilmaz (`/etc/trader-release` varsa onun `COMMIT=` satiri kullanilir). Kod yayin dalinda (`BRANCH` ucunun atasi) degilse kurulum hicbir sey degistirmeden durur. `install.sh` kodu root'un KENDI klonundan (`/usr/local/lib/trader-root/repo.git`) `git archive` ile `/usr/local/lib/trader-root/releases/<COMMIT>/` altina cikarir (root sahipli; `current` atomik baglanti); root birimleri (saglik, yedek, motor yeniden deneme) betikleri ve root'un kendi sanal ortamindan (`venv`, yalniz `requests` ve bagimliliklari, hash sabit) calistirir; `trader`in yazabildigi depodan root hicbir sey calistirmaz. Sonraki kurulumlarin olagan komutu: `COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh` (ilk gecista bir kez eski yol).

**Env dosyalari (O13):** `/etc/trader-*.env` hepsi `root:root 0600`; `trader` kullanicisi `trader-tg` grubunda DEGILDIR (grup outbox dizini icin kalir); systemd birimleri dosyalari root olarak okur. Motor/Telegram/veto/ders surecleri baslarken `prctl(PR_SET_DUMPABLE, 0)` ile ortamlarini ayni kimlikli sureclere kapatir (`proc_guard`). `install.sh --live` verilmedikce canli birim KURULMAZ; `--live` de motoru BASLATMAZ. Canli anahtar dosyasi `/etc/trader-live.env` (uc alan: `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `LIVE_CONFIRM=canli-alt1`) kullanici tarafindan `nano` ile yazilir.

Depo **ozel** (private) olursa bu komut sifre sorar ve olmaz. O durumda bir "deploy anahtari" eklenir; bunu birlikte, adim adim yapariz (anahtar sunucuda uretilir, GitHub'da depoya yalniz okuma izniyle eklenir, sunucudaki yeri `/home/trader/.ssh/deploy_key`). Sonra ayni komutun ssh surumu calisir.

## Ne yapar

1. Takas (swap) yoksa 4 GB takas dosyasi kurar (varsa dokunmaz), `swappiness=10`.
2. `trader` kullanicisi (giris yapamaz) ve `trader-tg` grubunu olusturur.
3. Yalniz `python3-venv`, `git`, `sqlite3`, `openssl` paketlerini kurar. Python 3.11'den eskiyse (ornegin Ubuntu 22.04) hicbir sey degistirmeden durur ve bunu soyler.
4. Kodu `/home/trader/SG-Github-AB-proje` icine indirir (tekrar calistirinca gunceller).
5. Yalniz calisma bagimliliklarini kurar (requests, pandas, numpy, pyarrow, anthropic); ccxt, websockets, freqtrade, ML paketleri (lightgbm/scipy) ve test paketleri yok (ML filtreleri 24.11 kullanici karariyla silindi; ML kumesi artik yok).
6. Dizinleri ve ayar dosyalarini (`/etc/trader-*.env`, yoksa) olusturur; var olan ayar dosyasini asla ezmez.
7. systemd birimlerini kurar. **Veri akisi** (`trader-feed.service`, en fazla 350 MB; Binance herkese acik REST -> `var/market.sqlite`) motordan once acilir. **Ogrenen motor** (`trader-engine@learner`, en fazla 350 MB), saglik kontrolu ve gunluk yedek acilir. **Ikiz motor** (`trader-engine@twin`, en fazla 350 MB) VARSAYILAN ACIKTIR (saglik ve yedek ikiz defterini bekler); kapatmak icin `--no-twin` (`--with-twin` geriye uyumluluk icin kabul edilir, etkisizdir). Kurulum baslarken `free -m` basar. `/etc/trader-health.env` icindeki `HEALTH_BOTS` her calistirmada ikiz durumuna gore (`learner,twin` / `learner`) guncellenir. Eski kurulumdan kalan `/etc/trader-veto.env`, `/etc/trader-veto-hmac.env` ve veto/C1 birimleri varsa silinir (24 Kasim kullanici karari). `user_data/budget.sqlite` trader sahipli 0600 onceden olusturulur.
8. Gecmis fiyat verisi yoksa Binance'in acik arsivinden indirir.
9. Ders ve Telegram **anahtarlar doldurulana kadar kapali** kalir; sonda Turkce bir "yapilacaklar" listesi basar. Anahtarlari sohbete yazmayin: `nano /etc/trader-telegram.env` ile dosyayi acip degeri yapistirin, sonra `COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh` komutunu yeniden calistirin.

## Ilk baslatma sirasi (feed -> kurallar 10/10 -> motor)

`install.sh` birimleri bu sirayla acar; motor birimi `After=/Wants=trader-feed.service` ile feed'e baglidir.

1. **Feed baslar**: ilk acilista borsa kurallarini (`exchangeInfo`) ceker (basarisizsa sinirli yeniden dener; olmazsa sifirdan farkli kodla cikar, HTTP 451 icin ayri kod/mesaj: bu sunucudan Binance vadeli erisimi yok), sonra gecmis mumlari doldurur (`backfill`, ilk seferde birkac dakika).
2. **Kurallar 10/10**: `config/engine.base.json` icindeki 10 ciftin hepsinin kurali `var/market.sqlite` icinde olmali. Elle denetim: `sqlite3 var/market.sqlite 'select pair, fetched_ms from rules'` (10 satir).
3. **Motor baslar** ve acilis kapisini calistirir: tum ciftlerde gecerli kural **ve** taze 1m last+mark verisi yoksa en fazla `startup_wait_s` (varsayilan 600 sn) bekler, sonra tek bir CRITICAL satiriyla cikis kodu 7 ile durur; birim `failed` olur ve `OnFailure` Telegram CRIT uyarisi gonderir (Telegram anahtarlari doldurulmamissa yalniz journal'a `trader-health-fail` CRIT satiri + varsa `HEARTBEAT_FAIL_URL`; kod 7 icin otomatik yeniden baslatma yoktur: once feed'i duzeltin, sonra `systemctl start trader-engine@learner`). 10/10 degilse hicbir sey acilmaz.

Komutlar: `python -m trader_engine feed --config-dir config` (feed), `python -m trader_engine rules-snapshot --config-dir config [--out yol]` (kurallari `rules.json` + `rules.json.meta.json` olarak yazar: zaman, sha256, kaynak adresi). Durum: `status.json` icindeki `counters.rules_missing` ve `counters.data_stale` sifir olmali.

## Durum kontrolu

```
systemctl status trader-feed trader-engine@learner
journalctl -u trader-feed -n 50 --no-pager
journalctl -u trader-engine@learner -n 50 --no-pager
systemctl list-timers 'trader-*'
free -m
```

Ikiz motor varsayilan acik; kapatmak icin `install.sh --no-twin`, tekrar acmak icin `install.sh` (secenek yok).

## Pano (salt okunur)

`install.sh` panoyu da kurar ve baslatir (`trader-panel.service`, en fazla 64 MB, yalniz `127.0.0.1:8787`, anahtar gerekmez). Disariya acik port yoktur; erisim SSH tuneli ile:

```
ssh -L 8787:127.0.0.1:8787 <kullanici>@<sunucu>     # sonra tarayicida http://127.0.0.1:8787
journalctl -u trader-panel -n 50 --no-pager
systemctl disable --now trader-panel                  # geri alma
```

## Telefondan/bilgisayardan pano (Cloudflare Worker, kilitsiz)

**Bellek verisi olmadan acmayin (bkz. "Bellek ölçümü"): 48 saatlik veri + >= ~900 MB bos RAM sart.** Sunucu her 5 dakikada panonun tek dosyalik anlik goruntusunu Cloudflare Worker'a yukler (`trader-panel-publish.timer`); sayfada "Olusturulma: ..." damgasi ve 10 dk'dan eskiyse kirmizi bayat seridi vardir. Cihazlariniza kurulum gerekmez. Canli pano yine yalniz `127.0.0.1:8787`'de kalir.

Sizin yapacaklariniz:
1. Cloudflare'da bir API token olusturun ("Edit Cloudflare Workers" sablonu). Token'i sohbete YAZMAYIN; size verecegimiz guvenli yolla (ya da sunucuda `nano /etc/trader-panel-cf.env`) girin. Hesap kimligini (Account ID) de ayni dosyaya yazin.
2. Pano **kilitsizdir** (20 Kasım 2026 kullanıcı kararı; 1L3A ve CT panoları gibi): parola ya da Cloudflare Access gerekmez, Worker yalnız okuma (GET/HEAD) kabul eder. Daha önce Access kurduysanız, bu sürüm sunucuya kurulduktan SONRA kaldırın (önce kaldırılırsa eski Worker her isteğe 403 verir): Zero Trust → Access → Applications → `trader-pano` uygulaması (ve varsa `trader-pano açık json`) → Delete. Ayrıca Workers & Pages → `trader-pano` → Settings → Domains & Routes → `workers.dev` satırında Access açıksa kapatın. Doğrulama (gizli pencerede): `https://trader-pano.sselimgenc-c18.workers.dev/` giriş istemeden panoyu göstermeli.
3. `https://trader-pano.<hesap>.workers.dev` adresini yer imine ekleyin. Orkestra kapısının iframe'inde giriş istemeden açılır.

RISK (karariniz): Workers duzenleme token'i tek Worker'a daraltilamaz, hesap capindadir. Sunucu ele gecirilirse ayni hesaptaki diger Worker'lariniz (1L3A, CT) da uzerine yazilabilir. Oneri: bu pano icin AYRI bir Cloudflare hesabi acin; ya da riski bilerek kabul edin. Karar sizindir.

Geri alma: `systemctl disable --now trader-panel-publish.timer`; Worker'i Cloudflare panelinden silin.

## Bellek ölçümü (soak, ilk 48 saat)

Uretim sunucusu artik **ayrilmis 2 GB RAM + 4 GB takas** (diger proje baska sunucuda; bu belgede "diger proje" gecen yerler tarihsel). Tum trader birimleri `trader.slice` altindadir (`MemoryHigh=1100M`, `MemoryMax=1300M`: **GECICI sayilar**; kesin degerler asagidaki 48 saatlik olcumden sonra belirlenir). Pano yayini (`wrangler`/node) bellek acisindan en pahali birimdir; `OOMScoreAdjust=500` ile bellek baskisinda once o olur, motor ve feed (`-200`) son sirada kalir.

Olcum (root olarak; soak baslangicinda, sonra 6-12 saatte bir ve 48. saatte):
```
free -m
systemd-cgtop -m -1 -b --depth=3 /trader.slice
systemctl show trader.slice -p MemoryCurrent -p MemoryPeak
systemctl show trader-engine@learner trader-engine@twin trader-feed -p MemoryCurrent
```
`systemd-cgtop`: `-m` bellege gore siralar, `-1` tek tur, `-b` etkilesimsiz, `--depth=3` alt cgroup'lar, `/trader.slice` kok cgroup yolu. `MemoryPeak` eski systemd surumlerinde yoksa bos doner; sorun degildir.

Bana su bilgileri bildirin: (1) her olcumde `free -m` ciktisinin "available" ve takas "used" sutunu; (2) `trader.slice` MemoryCurrent en yuksek degeri ve birim bazinda dagilim; (3) diger projenin tahmini kullanimi (RSS toplami); (4) `journalctl -k | grep -i "out of memory\|oom"` ciktisi (varsa).

**Cloudflare yayinini (`trader-panel-publish.timer`) ancak 48 saatlik bellek verisi toplandiktan sonra ve diger proje calisirken bos RAM (`available`) >= ~900 MB ise acin.** Bunu saglamak icin yayin zamanlayicisi varsayilan kapalidir (Cloudflare anahtarlari `/etc/trader-panel-cf.env` icinde bos oldugu surece `install.sh` acmaz); anahtarlari verinin gelisinden once doldurmayin.

**Testnet golge motoru bellek payi (WP-B8).** `trader-engine-testnet.service` (`MemoryHigh=250M`, `MemoryMax=320M`) ayni slice'tadir. Yumusak tavanlar toplami feed 280 + ogrenen 280 + ikiz 280 + testnet 250 = 1090 MB <= slice `MemoryHigh=1100M` (test: `test_readiness_memory`); sert tavanlar toplami slice `MemoryMax=1300M`'i asar ama gercek RSS tavanlarin cok altindadir; asan olursa once slice yumusak siniri kisar, sonra OOM (`OOMScoreAdjust` motor/feed -200, panel yayini +500). Slice degerleri **48 saatlik olcumle** kesinlesir: testnet motoru calisirken yukaridaki `systemd-cgtop` komutlarini ve `systemctl show trader-engine-testnet -p MemoryCurrent -p MemoryPeak` ciktisini ekleyin; `trader.slice` MemoryPeak > ~1000 MB ya da `available` < 400 MB ise testnet motorunu durdurun (`systemctl stop trader-engine-testnet`) ve bildirin.

## Testnet golge servisi (WP-B8)

`trader-engine-testnet.service` = `python -m trader_engine run --bot learner --env testnet` (kendi `var-testnet/`, `shared/testnet/KILL|PAUSE`; `config/engine.testnet.json`). Anahtarlar **yalniz** `/etc/trader-testnet.env` (root:root 0600; `install.sh` `deploy/trader-testnet.env.example`'dan bos olusturur; mevcut dosyaya dokunmaz). `BINANCE_API_KEY` ve `BINANCE_API_SECRET` ikisi de dolmadan birim **acilmaz/baslatilmaz** (`install.sh` OZET'te "YAPILACAKLAR"a yazar); canli anahtar dosyasi bu birimde asla kullanilmaz. Anahtarlari `nano /etc/trader-testnet.env` ile yazin (sohbete yazmayin), sonra `COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh`. Duzeltme turu bitene kadar duman/tatbikat betigi (yukaridaki bolum) ayni dosyayi kaynak alir. Cikis kodlari 2/7/8 yeniden denenmez (`RestartPreventExitStatus`). Kapatma: `systemctl disable --now trader-engine-testnet`; acil durdurma: `python -m trader_engine kill --env testnet --by <ad>`.


**Testnet sermaye kaydi (otomatik, yalniz testnet).** Risk-kademe gunlugu (`var-testnet/learner/risk_ladder.jsonl`) bos oldugunda saglik `risk_ladder:learner@testnet|capital_missing` (CRIT) verir. `install.sh`, testnet anahtarlari doluysa motoru acmadan once `python3 -m trader_engine capital init-from-exchange --bot learner --env testnet --by kurulum.testnet` calistirir: testnet borsasindan `totalWalletBalance` okunur (sonlu ve > 0 olmali) ve `capital init` ile ayni yoldan `initial` satiri yazilir (not: "testnet bakiye"). Idempotent: gunluk doluysa dokunmaz; `--env` testnet degilse reddeder; okuma hatasinda hicbir sey yazmaz, kurulum durmaz, OZET'te "YAPILACAKLAR (testnet sermaye kaydi)" satiri cikar. Motor o sirada calisiyorsa ve satir yazildiysa yalniz `trader-engine-testnet` yeniden baslatilir. Kagit (paper) ve canli yollarina dokunmaz; canlida sermaye kaydi elle `capital init` ile yapilir.

**DD-8 gecis adimi (gölge kosudan ONCE, bir kez).** Testnet/canli motor artik state ve deftere mod/hesap damgasi (`testnet:<account_tag>`) yazar; damgasiz eski dizin `state_stamp_missing` / `state_missing` ile (cikis 8, yeniden denenmez) acilmaz. DD-8 dagitiminda: `systemctl stop trader-engine-testnet`; `mv var-testnet/learner var-testnet/learner.pre-dd8-$(date +%Y%m%d)` (**tasinir, silinmez**); `systemctl start trader-engine-testnet`. `install.sh` bunu kendiliginden yapmaz. Ayni calisma cozumu 6. ve 8. retler icin de gecerlidir: motor durdurulur, ilgili `var-*/<bot>` dizini arsive tasinir, motor temiz dizinle acilir. Canli/testnet `var_dir` son bileseni `var` olamaz; `kill_file`/`pause_file` `shared/<env>/` altinda olmali (aksi `ConfigError`, cikis 2). Tavan tutusu (`wallet_above_expected`) yalniz sunucuda `python -m trader_engine pause --bot learner --env <env> --clear --reason wallet_above_expected --by <ad>` ile kalkar. Bozuk spool dosyasi (`<defter>.spool.corrupt.jsonl`) saglik alarmi verir; incelemeden sonra `mv ledger.sqlite.spool.corrupt.jsonl ledger.sqlite.spool.corrupt.$(date +%Y%m%d).jsonl` ile temizlenir.

Saglik denetcisi (5 dk) bu motoru `HEALTH_SHADOW_VAR_DIR` ile izler (anahtarlar doluysa `install.sh` doldurur). Yeni alarmlar: `naked_position` (acik testnet/canli pozisyon stopsuz: `status.exchange.naked` bos degil; CRIT, aninda), `exchange_unreachable` (`exchange.reachable=false`; `last_sync` > `EXCHANGE_UNREACH_S` (60 sn) ise CRIT, once WARN), `pause_hold_unaudited` (PAUSE tutusu var ama `pause_audit.jsonl`'de o neden icin son islem `add` degil) ve `pause_hold_lost` (onceki turda olan tutus, gunlukte `remove` olmadan kayboldu; bir tur). Esikler: `NAKED_ALARM_S` (varsayilan 0 = hemen), `EXCHANGE_UNREACH_S`. Not: zamanlayici 5 dk'dadir, yani `naked` alarm gecikmesi <= 5 dk + onay; motorun kendi 10 sn'lik kapatmasi asil korumadir (11 O-4 acik).

**Canliya cikista izleme dizini (DD-9: ELLE CEVIRME TALIMATI KALDIRILDI).** `install.sh --live` Telegram, saglik ve ders env dosyalarina canli yollari kendisi yazar (`LIVE_BOTS=learner`, `LIVE_VAR_DIR`, `LIVE_PAUSE_FILE`, `KILL_FILE`, `ENGINE_STATUS_PATH`, `LEDGER_PATH`, `LADDER_BOTS`, `ENGINE_CONFIG_DIR`); yollar `config/engine.live.json` ile tutarsizsa Telegram daemon'u acilmaz, saglik `live_paths_mismatch` CRIT verir ve `scripts/live_preflight.py` canli birimi etkinlestirmez. Eski (artik gecersiz) aciklama: Saglik ve Telegram `ENGINE_VAR_DIR`'i **kendi env dosyalarindan** okur (`/etc/trader-health.env` ve `/etc/trader-telegram.env`); motorun `var_dir`'i canli dizine (or. `var-live`) cevrilince iki dosyada da `ENGINE_VAR_DIR`'i AYNI dizine cevirin ve `PAUSE_FILE`'i (saglik + telegram) canli motorun `pause_file`'ina esitleyin; aksi halde kagit dizini izlenir (canli pozisyon gorunmez). `install.sh` bu degerlere yalniz bos ise dokunur; elle verilen deger korunur. Degisiklikten sonra `systemctl restart trader-telegram`; saglik zamanlayicisi bir sonraki turda okur.

## Acilis kapisi yeniden deneme
Motor acilis kapisinda (kural 10/10 degil ya da veri bayat) cikis 7 ile `failed` olursa `trader-engine-retry@<bot>.timer` (5 dk) besleme saglikliyken motoru yeniden baslatir; saatte en fazla 6 deneme, sonra tek CRIT Telegram uyarisi. Cikis 6 (451) ve yapilandirma hatalari yeniden denenmez (tek sert alarm). Izleme: `journalctl -u 'trader-engine-retry@*' -n 30`.

## Giris duraklatma (CLI)
Telegram `/durdur` / `/devam` disinda tek yol CLI'dir: `sudo -u trader <repo>/.venv/bin/python -m trader_engine pause --bot learner --reason manual --by ad` ; kaldirmak icin `--clear --reason <neden> --by <ad>` (ikisi de zorunlu). CLI'yi **mutlaka `sudo -u trader`** ile calistirin: root olarak calisinca `PAUSE.<bot>.lock` ve `pause_audit.jsonl` root sahipli olusur ve `trader` kullanicisi (motor, Telegram) artik yazamaz. Gerekirse: `chown trader:trader shared/PAUSE.* var/*/pause_audit.jsonl`.

## Canliya gecis gunu (DD-9; mentor eslikliginde; bu liste otomatik calismaz)

1. Kagit learner KILL ile duzlenir; `systemctl disable --now trader-engine@learner trader-engine-retry@learner.timer`.
2. Kullanici `nano /etc/trader-live.env` ile uc alani yazar (cekim/transfer yetkisi KAPALI, yalniz sunucu IP'si).
3. `COMMIT=<etiketli sha> bash /usr/local/lib/trader-root/current/deploy/install.sh --live` (commit `canli-YYYYAAGG[-N]` etiketi tasimali; on denetim `live_preflight.py` gecmeden canli birim etkinlesmez; motor BASLATILMAZ).
4. `capital init` (12 §14).
5. `bash /usr/local/lib/trader-root/current/deploy/canli_duman.sh` ile duman testi (ayri gun).
6. `python -m trader_engine pause --bot learner --env live --reason manual --by <ad>` ile ilk acilis tutusu.
7. `systemctl start trader-engine-live`.
8. Mutabakat temizse tutus kaldirilir.

Canli birimi kaldirmak icin `install.sh --no-live` (Telegram/saglik env'lerindeki canli alanlar elle kagit degerlerine alinmalidir). Not: ders servisinin `LEDGER_PATH`i canli deftere cevrilir; bu, dersin canli islemlerden ogrenmesi demektir (mentor canliya gecis kararinda ayrica gozden gecirir).

## Kurulum sonrasi koruma (otomatik guncelleme: sabit pencere, sessizlik, izleme, geri alma)

**Sabit pencereler.** `trader-oto-guncelle.timer` yalniz gunde iki kez calisir: **10:30 ve 22:30 Turkiye saati** (UTC+3 sabit; = 07:30 ve 19:30 UTC). Pencere disinda betik hicbir sey kurmaz (sessizce cikar; kurulum penceresi +60 dk tolerans). Yine yalniz GitHub'da `tests.yml`'in (artik `duman` + `tests` isleri) YESIL gectigi commit kurulur; 15 dk mum kapanisina yakinsa en fazla ~4 dk bekler. **Acil kurulum (pencereyi beklemeden):** `sudo trader-oto-simdi` (= `oto_guncelle.sh --simdi`; DURDUR dosyasi, canli koruma, yesil commit ve atalik kontrolu aynen gecerli). Belirli bir kodu elle kurmak: `COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh`. Otomatigi durdurmak/acmak: `/var/lib/trader-oto-guncelle/DURDUR` / `trader-oto-ac`.

**Kurulum isareti.** Kod degistiren her kurulumda `install.sh`, motorlar yeniden baslamadan once `/var/lib/trader-oto-guncelle/kurulum.json` yazar: `{"at","commit","onceki","tur"}` (`tur`: `oto` | `elle` | `geri-al`). Asagidaki korumalar bu isarete bakar.

**1) 15 dk sessizlik (saglik).** Kurulumdan sonraki ilk 15 dk `trader-health` YALNIZ olumcul kirmizilari iletir (`FATAL_CODES`: stopsuz pozisyon, hesap modu kaymasi, defter butunlugu, bellek kaynakli olum, motor calismiyor/yeniden baslama dongusu, API yanit yok, bozuk spool, borsa engeli + acik pozisyon, sermaye tabani, canli yol uyusmazligi). Digerleri TUTULUR (durumlari geri alinir) ve pencere bitince tek `Kurulum sonrasi tutulan uyarilar` ozetiyle (sorun suruyorsa ayrica kendi uyarisiyla) gelir. Ek uyarilar (CT, disk, tutarlilik) pencere boyunca bekler. Kagitta: yalniz bildirim; islem etkilenmez.

**2) 60 dk izleme + otomatik geri alma (`trader-kurulum-gozcu.timer`, 2 dk'da bir).** Kurulumdan sonraki ilk 4 dk (motor yeniden basliyor) sayilmaz; sonra UST USTE 2 turda sunlardan biri gorulurse `trader-geri-al --otomatik` calisir (systemd-run gecici birimi, `trader.slice` disinda, `MemoryMax=800M`): motor servisi `active` degil; motor `status.json` 300 sn'den eski; `NRestarts >= 3`; saglikte olumcul kirmizi (ust uste >= 2 saglik turu). Onceki surum (`kurulum.json.onceki`; yoksa gecmisten) kurulur, bozuk commit `gecmis.tsv`'ye `basarisiz` yazilir (oto_guncelle bir daha ASLA denemez), otomatik guncelleme DURDURULMAZ (sonraki yesil commit kurulabilir) ve tek Telegram mesaji nedenle gider. Canli birim varsa, kurulum `geri-al` turundaysa ya da onceki surum yoksa hicbir sey yapilmaz. `install.sh` mevcut + en fazla iki onceki surumu tutar.

**3) 20 dk oz-kontrol.** Kurulumdan 20 dk sonra bir kez: saglikta ust uste >= 2 tur kirmizi (olumcul olsun olmasin) varsa TEK mesaj; sorun yoksa HICBIR sey gonderilmez. Izleme zaten sorun gorurken ikinci mesaj gitmez.

**Kirmizi alarm cift dogrulama.** Hicbir kirmizi (CRIT/UNKNOWN) saglik alarmi tek basarisiz kontrolle gitmez: ilk gorulen tur "sari" (izlenir, mesaj yok), ust uste 2. turda kirmizi gider (`RED_CONFIRM_RUNS=2`). Tek istisna canli/testnet para guvenligi kodlari (`RED_SINGLE_OK`: `naked_position`, `exchange_ban_open_positions`, `account_mode_drift`, `live_paths_mismatch`; kagitta hic uretilmez). Her alarm turu icin baglam testi: `tests/test_alarm_baglam.py` (gercek kosulda 2 turda gider; zararsiz benzer kosulda gitmez).

**CI duman testi.** `.github/workflows/tests.yml` `duman` isi: `scripts/ci_duman.py` motoru iceri aktarir ve sentetik veriyle 1 gunluk kagit kosusu yapar (~5 sn). Yerelde: `cd trader && python scripts/ci_duman.py`. Hicbir risk sinirina, kagit islem ayarina ya da motor davranisina dokunmaz.

## Kaldirma

```
bash /usr/local/lib/trader-root/current/deploy/uninstall.sh
```

Yalniz `trader-*` birimlerini durdurur ve siler; veri, ayar dosyalari ve kullanici kalir. Her seyi silmek icin `uninstall.sh --purge` (veri, `/etc/trader-*.env`, `trader` kullanicisi gider; `/swapfile` kalir).

## Notlar (16 Kasım 2026)
- Sunucuya geçmiş veri olarak 15m/1h/4h/1d indirilir; 1m verisi yalnız geçmiş test aracı için gerekir, sunucuda gerekmez.

## Ilk gun runbook (bos sunucu; 30 Kasim paper baslangici)

Sira onemlidir; her adim bir sonrakinin on kosuludur. Ayrintili denetim ve acik maddeler: `docs/hazirlik-denetimi.md`. Komutlar root olarak calistirilir.

```
T=/home/trader/SG-Github-AB-proje/trader ; cd $T
run_as_trader() { runuser -u trader -- sh -c "cd $T && PYTHONPATH=$T/src $*"; }     # trader olarak, depo dizininde
```

**0. Onceden hazirla** (degerleri sohbete degil, sunucuda `nano` ile yazin). `free -m` ile bos bellegi ve diger projenin payini kontrol edin (install.sh de basar). Anahtar SIRASI (her adimdan sonra `install.sh`'i yeniden calistirin; zamanlayicilar kendi anahtarlari tamamlaninca acilir):
1. Telegram bot token + chat id (`/etc/trader-telegram.env`): daemon, gunluk rapor ve saglik uyarilari (NOTIFIER=auto) acilir.
2. `HEARTBEAT_URL` (`/etc/trader-health.env`; https://, ornegin healthchecks.io; bos kalirsa saglik birimi calisir ama yalniz uyari yazar; sunucu tamamen olurse tek alarm budur).
3. Ders icin Anthropic anahtari `ANTHROPIC_API_KEY_LESSON` (`/etc/trader-lesson.env`); ders zamanlayicisi Telegram anahtarlari da doluysa acilir.
4. Cloudflare (panel yayini) EN SON.
Ikiz motor varsayilan ACIK (saglik/yedek icin gerekli; denetim OPEN-4); kapatmak icin `--no-twin`.

**1. Kurulum**
```
COMMIT=<KOD> bash /root/trader-kurulum/trader/deploy/install.sh      # YALNIZ ilk kurulum (bir kez); sonrakiler root kopyadan
nano /etc/trader-telegram.env ; COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh      # 1) Telegram
nano /etc/trader-health.env   ; COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh      # 2) HEARTBEAT_URL
nano /etc/trader-lesson.env   ; COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh      # 3) ders anahtari
nano /etc/trader-panel-cf.env ; COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh      # 4) Cloudflare (son)
systemctl list-units 'trader-*' --no-pager ; systemctl list-timers 'trader-*' --no-pager ; free -m
```
Beklenen: ozetin sonundaki "YAPILACAKLAR" listesi bos (ya da yalniz bilerek ertelediklerin); `trader-feed`, `trader-engine@learner`, `trader-engine@twin`, `trader-panel` active.

**2. Feed: baslat + backfill** (ilk seferde birkac dk)
```
systemctl is-active trader-feed ; journalctl -u trader-feed -n 40 --no-pager
sqlite3 -readonly $T/var/market.sqlite "select kind,tf,count(*),datetime(max(open_ms)/1000,'unixepoch') from bars group by 1,2"
date -u ; ls -l $T/var/feed-status.json
```
Beklenen: `last/1m` ve `mark/1m` icin en yeni mum `date -u`'dan en fazla ~2 dk geride; `15m/1h/4h` dolu. Hata: `systemctl show trader-feed -p Result -p ExecMainStatus`: **6** = HTTP 451 (bu sunucudan Binance vadeli yok; baska bolge gerekir), **5** = kurallar alinamadi (ag/Binance), **1** = ag yok (traceback). Hepsinde birim `failed` olur ve OnFailure alarmi calisir.

**2b. OI / long-short orani toplayici (ML-G7, `trader-oi.timer`)**: her 5 dk bir kez `scripts/oi_collect.py` calisir (Binance herkese acik `/futures/data/*` GET uclari; anahtar yok; `trader-oi.service`, `MemoryMax=96M`) ve 10 cift icin `var/market.sqlite` icindeki `positioning_5m` tablosuna (pair, ts ms, OI, global/top hesap ve pozisyon orani, taker orani, fetched_at) idempotent yazar. Her kosu son satirdan simdiye (en fazla ~30 gun) boslugu kapatir; kilitli donem (2026-05-01..2026-11-01) ne istenir ne yazilir. Kontrol: `sqlite3 -readonly $T/var/market.sqlite "select pair,count(*),datetime(max(ts)/1000,'unixepoch') from positioning_5m group by 1"` (10 satir; en yeni ts `date -u`'dan ~10 dk geride) ; `systemctl list-timers trader-oi.timer` ; `journalctl -u trader-oi -n 20 --no-pager` (`event=done ... errors=0`). Cikis kodlari: 0 tamam, 2 bazi uclar alinamadi (alarm degil, sonraki tur kapatir), 3 IP yasagi/429, 6 HTTP 451 (alarm). Tablo feed'in `user_version`ine dokunmaz; feed durursa da toplama surer. Birikmesi istenmiyorsa: `systemctl disable --now trader-oi.timer`.

**3. Kurallar 10/10**
```
sqlite3 -readonly $T/var/market.sqlite "select count(*) from rules"                  # 10
sqlite3 -readonly $T/var/market.sqlite "select pair,datetime(fetched_ms/1000,'unixepoch') from rules order by 1"
sqlite3 -readonly $T/var/market.sqlite "select k,v from feed_meta where k in ('rules_fetched_at','rules_last_error')"   # last_error bos
```

**4. init-ledger** (motor birimi ExecStartPre ile kendisi yapar; elle dogrulama)
```
run_as_trader $T/.venv/bin/python -m trader_engine init-ledger --bot learner --config-dir config     # "etkin parametre var: dokunulmadi" (ikinci kez)
run_as_trader $T/.venv/bin/python -m trader_engine init-ledger --bot twin    --config-dir config
sqlite3 -readonly $T/var/learner/ledger.sqlite "select count(*) from param_versions; select count(*) from param_activations"   # 1 ve 1
```

**5. Motor acilis kapisi**
```
systemctl restart trader-engine@learner trader-engine@twin
journalctl -u trader-engine@learner -n 30 --no-pager | grep -E "acilis kapisi|CRITICAL"
systemctl show trader-engine@learner -p ActiveState -p Result -p ExecMainStatus
```
Beklenen: `engine acilis kapisi tamam: 10/10 cift kural+taze veri`, `ActiveState=active`. Cikis **7** = kapi gecmedi (CRITICAL satiri hangi cift/ne eksik oldugunu yazar); oto-yeniden baslatma YOK: feed'i duzelt, sonra `systemctl reset-failed trader-engine@learner && systemctl start trader-engine@learner`.

**6. status.json**
```
python3 - <<'PY'
import json,datetime
for b in ("learner","twin"):
    s=json.load(open("/home/trader/SG-Github-AB-proje/trader/var/%s/status.json"%b))
    print(b, s["mode"], "loop_at",s["loop_at"], "gate",s["gate"], "kill",s["kill"], "counters",{k:s["counters"][k] for k in ("rules_missing","data_stale")})
PY
date -u
```
Beklenen: `mode=paper`, `loop_at` `date -u`'dan <2 dk, `gate={'ok': True, 'code': 'ok'}`, `rules_missing=0 data_stale=0`, `kill False`. NOT: `entries_open` veto'yu kapsamaz (adim 9).

**7. Saglik**
```
systemctl start trader-health.service ; journalctl -u trader-health -n 5 --no-pager ; echo "cikis=$(systemctl show trader-health -p ExecMainStatus --value)"
cat /var/lib/trader-health/state.json | head -c 600 ; ls -l /var/backups/trader
```
Beklenen: son JSON satirinda `"overall": "OK"` (ilk saat `WARN` + `ledger_write_stale_warmup` olabilir), `"heartbeat": true`. `health_run: beklenmeyen hata: ValueError` = `HEARTBEAT_URL` bos/https degil. Dis nabiz panelinde (healthchecks vb.) ilk ping gorunmeli.

**8. Telegram test mesaji**
```
set -a ; . /etc/trader-telegram.env ; set +a
runuser -u trader -g trader-tg -- env TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" TELEGRAM_VAR_DIR="$TELEGRAM_VAR_DIR" \
  $T/.venv/bin/python -I $T/scripts/telegram_run.py send --severity INFO --dedup-key kurulum-testi-$(date +%s) "Kurulum testi"     # "sent" (ya da "spooled")
systemctl status trader-telegram --no-pager | head -5
systemctl start trader-health-fail@deneme.service ; journalctl -t trader-health-fail -n 3 --no-pager      # CRIT zinciri: Telegram "Birim basarisiz: deneme.service" + journal
```
Telefonda `/durum` yaz: `kip=paper kill=False ... entries_open=True`. `spooled` = mesaj kuyruga yazildi, daemon gonderecek (`ls $T/var/telegram/outbox`). Anahtarlar bossa Telegram timer/daemon hic acilmaz; CRIT yalniz journal + `HEARTBEAT_FAIL_URL`'e gider (sessiz degil ama telefona dusmez).

**9. (silindi)** AI veto 18 Kasim'da kaldirildi; 24 Kasim kullanici karariyla artiklari da silindi (veto belgesi, HMAC anahtari, `trader-veto*` birimleri yok). Giris kapisinda veto adimi yoktur.

**10. Pano okuyor mu**
```
curl -s http://127.0.0.1:8787/api/status | python3 -m json.tool | head -40        # bots.learner.state ve bots.twin.state = "live"; kill_file_exists=false
curl -s "http://127.0.0.1:8787/api/ledger?bot=learner" | head -c 400 ; echo ; curl -s http://127.0.0.1:8787/api/health | head -c 300
journalctl -u trader-panel -n 10 --no-pager
```
Tarayici icin: `ssh -L 8787:127.0.0.1:8787 <kullanici>@<sunucu>`. `ok:false,code:status_bayat` = motor 120 sn'dir yazmiyor.

**11. Kill anahtari tatbikati** (yol: `$T/shared/KILL`; motor, Telegram `/hepsini_kapat` ve pano ayni dosyayi kullanir)
```
run_as_trader $T/.venv/bin/python -m trader_engine kill --by runbook --reason deneme
ls -l $T/shared/KILL ; curl -s http://127.0.0.1:8787/api/status | grep -o '"kill_file_exists": *[a-z]*'      # true
journalctl -u trader-engine@learner -n 5 --no-pager
run_as_trader $T/.venv/bin/python -m trader_engine kill --clear
```

**12. Yedek**
```
systemctl start trader-backup.service ; ls -l /var/backups/trader/$(date -u +%F)/ ; cat /var/backups/trader/$(date -u +%F)/MANIFEST.json | head -c 500
```
Beklenen: 4 dosya (`ledger_*`, `state_*` x learner/twin), `"ok": true`.

**Hizli ariza tablosu**

| Belirti | Anlami | Ne yapilir |
|---|---|---|
| `trader-feed` failed, ExecMainStatus 6 | HTTP 451 | Binance vadeli bu bolgeden yok; sunucu bolgesi degisir |
| `trader-engine@*` failed, ExecMainStatus 7 | acilis kapisi: kural/veri eksik | adim 2-3, sonra `reset-failed` + `start` |
| health CRIT `market_bars_stale` | feed durdu / yavas | `journalctl -u trader-feed`; `systemctl restart trader-feed` |
| health CRIT `api_unreachable:twin` | ikiz kurulu degil | `install.sh` (ikiz varsayilan acik; `--no-twin` kullanildiysa `HEALTH_BOTS=learner`) |
| Telefona alarm gelmiyor | Telegram anahtari bos ya da `NOTIFIER=log` | adim 8; `NOTIFIER=auto` ve `/etc/trader-telegram.env` (saglik birimi bunu okur; outbox dosyalari trader-tg grubuna 0660) |


## Gecmis veriyi 2021-01'e uzatma (ML-G3; `scripts/fetch_binance_vision.py`)

Amac: ML derlemi ve geri test icin ayni 10 cifte 2021-01 -> 2024-10 gecmisini `var/history`ye eklemek (tasarim-kararlari.md, 17 Kasim kullanici karari). Yalniz data.binance.vision (acik arsiv) kullanilir; Binance API'ye (451) ihtiyac yoktur. Sunucuda canli servisler icin gerekmez; ML/geri test makinesinde calistirin.

```
cd /home/trader/SG-Github-AB-proje/trader
sudo -u trader .venv/bin/python scripts/fetch_binance_vision.py --start 2021-01 --tfs all --workers 2 --rate 4 --require-checksum --dry-run   # once plan
sudo -u trader nice -n 15 .venv/bin/python scripts/fetch_binance_vision.py --start 2021-01 --tfs all --workers 2 --rate 4 --require-checksum
```
- Ne indirir (cift basina): klines 15m, 1h, 4h, 1d, 1m; markPriceKlines 1h, 1m; fundingRate; aylik zip + `.CHECKSUM` (sha256 uyusmazsa zip kaydedilmez, cikis kodu 2). Aylik yayinlanmamissa gunluk zip'e duser.
- Cikti: `var/history/<PAIR>_USDT_USDT-<tf>-{futures|mark}.feather` (date=timestamp[ms,UTC], open, high, low, close, volume), `...-1h-funding_rate.feather` (date, funding_rate). 1m dosyalari sikistirilmamis. Ham zip onbellegi `var/vision_raw` (silinebilir; silinirse bir sonraki kosu yeniden indirir).
- Kilitli donem (2026-05-01 -> 2026-11-01): arsivden hic istenmez (`--end` en gec 2026-04). Mevcut dosyalarin kilitli doneme ait satirlari degistirilmez; yeni satirlar dosyanin basina/kilitli donem oncesine eklenir (dosya atomik yeniden yazilir; eklenecek bir sey yoksa dosyaya dokunulmaz).
- Yeniden baslatilabilir: kesilirse ayni komutu tekrar calistirin (var olan zip'ler tekrar indirilmez, ag hatalari `error` sayilir, cikis 1). Ayni anda iki kosu `.fetch.lock` ile engellenir. Calisirken geri test/ML kosusu baslatmayin (feather dosyalari yeniden yazilir).
- Bosluk raporu: `var/gap_report.json` ve `var/gap_report.md` (cift/kind/tf basina eksik aylar, eksik gunler, kismi gunler). Kosudan sonra okuyun; eksik gun varsa nedeni arsivde yok demektir (uydurulmaz).
- Boyut (mevcut 2024-11 -> 2026-04 dosyalarindan olcekli tahmin; 46 ay eklenir): `--tfs all` ~ +3,2 GB (feather ~ +2,0 GB, onun ~ +1,9 GB'i 1m; ham zip onbellegi ~ +1,2 GB); 1m'siz (`--tfs 15m,1h,4h,1d`) ~ +0,3 GB. Baslamadan once `df -h /home/trader`.
- Sure: ~7.400 istek (3.700 zip + checksum); `--rate 4` ile ~30 dk + indirme/donusturme, toplam ~45-60 dk (2 GB sunucuda `--workers 2`; bellek `MemoryMax=450M` icinde kalacak sekilde 1m dosyalari en buyuk bellek kullanicisidir, gerekirse `--tfs 15m,1h,4h,1d` ve ardindan `--only-1m` ayri kosun).


## Derlem v2 kurulumu (ML-G6; `scripts/build_corpus_v2.py`)

Amac: 2021-01 -> 2026-04 gecmisinden (yukaridaki indirme bittikten SONRA) r02/r03 icin uzun donem aday derlemi uretmek. Model egitilmez, kapi calistirilmaz. Aday tanimi 19b ile ayni kod (`trader_ml.features.feature_frame` + `candidate_rows`): **post_filter oncesi yerel v1b adaylari** (signal True, setup T1, iki yon, 10 cift; alinmis/alinmamis ayrimi ve ledger yok). Etiketler `multi_r_labels` (1R/1,5R/2R, 72 mum, `label_end_ts` her R icin), ozellikler `trader_ml.features_v2` korumali sarmalayici (r02 40 + r03 ek 3 sutun), fonlama `var/history/*-1h-funding_rate.feather`. Kilitli donem: `--end` 2026-05-01'den buyukse sert red; dosyalar okunurken `date >= 2026-05-01` satirlari hic yuklenmez.

```
cd /home/trader/SG-Github-AB-proje/trader
git status --short                      # TEMIZ olmali (kirli agacta betik reddeder)
df -h /home/trader                      # derlem + gecici ~ <100 MB
sudo systemd-run --uid=trader --gid=trader --unit=trader-corpus-v2 --collect --wait --pty \
  -p Nice=15 -p MemoryMax=900M -p MemorySwapMax=0 -p CPUQuota=100% \
  -p WorkingDirectory=/home/trader/SG-Github-AB-proje/trader -p Environment=PYTHONPATH=src \
  .venv/bin/python scripts/build_corpus_v2.py --start 2021-01-01 --end 2026-05-01 --sample-check 50
```
- Ayni komut `nohup` ile arka planda da calisir: `sudo -u trader nice -n 15 env PYTHONPATH=src .venv/bin/python scripts/build_corpus_v2.py ... > research/logs/corpus_v2.log 2>&1 &`. Indirme (`fetch_binance_vision.py`) calisirken BASLATMAYIN (feather dosyalari yeniden yazilir; `var/history/.fetch.lock` yoksa bitmistir). Gerekli dosyalar cift basina `1h-futures` ve `1h-funding_rate` (1m dosyalari gerekmez).
- Cikti (`research/ml/`): `corpus_v2.parquet` (git'e girmez), `corpus_v2.manifest.json` (commit edilir), `corpus_v2.sample_check.md`. Ayni girdi + ayni kod = ayni `corpus.sha256` (iki kez kosup karsilastirin: `sha256sum research/ml/corpus_v2.parquet`; farkli pyarrow surumunde bayt farkini `corpus.content_sha256` ayirt eder).
- Manifest: her girdi dosyasinin sha256'si ve kullanilan dilimin karmasi, kod dosyalarinin sha256'si ve git commit'i, cift/yil satir sayilari, her R icin etiket cozulme sayilari (cozulmemis = son 72 mum), 43 ozelligin NaN oranlari (toplam ve yil bazinda; 2021 basinda 200 gunluk 1g baglam yuzunden yuksek NaN beklenir), `candle_gaps` (cift basina 1s mum boslugu: > 0 ise nedeni arsiv bosluk raporuna bakarak yazin), `same_bar` (satirlar `(pair, ts)` tekil; `f_same_bar_signals` = ayni ts'deki ayri cift sayisi), `funding_stale_count`, `peak_rss_mb`, `runtime_s`.
- **Elle kontrol (50 etiket):** `corpus_v2.sample_check.md` 50 rastgele (seed 20261117, sabit) etiketli aday icin giris/stop/1R-1,5R-2R hedefleri, bariyer temaslari isaretli mum penceresi ve `labels.py`'den bagimsiz yeniden hesabi icerir. Her basliktaki `[ ]` kutusunu elle isaretleyin; sonunda "Bagimsiz yeniden hesap uyumu: 150/150" olmalidir. Tek hatali etiket varsa derlem kullanilmaz, mentora yazilir. Isaretli dosya ile manifest birlikte commit edilir.
- Bellek (2 GB sunucu): cift cift (aday + etiket) ve yil yil (ozellik, parquet satir grubu); mum cercevesi 10 cift x ~46 bin satir (~25 MB). Yerel olcum (2024-11..2026-04, 10 cift, 2.021 aday): tepe 194 MB RSS, 60 sn (tek cekirdek). 2021'e uzayinca sure ~3-4 kat, bellek ~ <400 MB beklenir; `MemoryMax=900M` bu yuzden guvenli tavandir. Gercek sunucu tepe degeri manifestteki `peak_rss_mb`'ye yazilir; farkliysa buraya not edin.
- Yeniden uretim: `--skip-build --sample-check 50` var olan derlemden yalniz kontrol dosyasini yeniden yazar. Yerel duman kosusu icin `--allow-dirty --history-dir ... --out-dir ...` (sunucuda KULLANILMAZ).


## r02/r03 kosusu: katman, on hesap, dondurma, tek kosu (ML-G7; on kayit `docs/ml/r02-r03-on-kayit.md`)

Sira DEGISMEZ. Kod (iş emri) birlesmis ve commit'li olmali: `build_corpus_v2.CODE_FILES` manifestte sha256 ile kayitlidir, kosu aninda diskle karsilastirilir (kod derlemden sonra degisirse kosu reddedilir, cikis 6).

1. **Derlem kurulumu** (yukaridaki "Derlem v2 kurulumu"): `scripts/build_corpus_v2.py --start 2021-01-01 --end 2026-05-01 --sample-check 50`; temiz agac.
2. **50 etiket elle kontrol:** `research/ml/corpus_v2.sample_check.md` kutulari isaretlenir, "Bagimsiz yeniden hesap uyumu: 150/150" sarttir; tek hata = derlem kullanilmaz. Manifest + isaretli dosya commit'lenir (agac temiz kalsin).
3. **Alinan-islem katmani** (motor backtest'i 19b ile ayni ayarlar, donem 20210101-20260501, kilitli donem koşulmaz; uzun surer, `systemd-run` ile derlemdeki gibi bellek sinirli):
   ```
   sudo systemd-run --uid=trader --gid=trader --unit=trader-corpus-v2-taken --collect --wait --pty \
     -p Nice=15 -p MemoryMax=900M -p MemorySwapMax=0 -p CPUQuota=100% \
     -p WorkingDirectory=/home/trader/SG-Github-AB-proje/trader -p Environment=PYTHONPATH=src \
     .venv/bin/python scripts/build_corpus_v2_overlay.py
   ```
   Betik backtest'ten ONCE `corpus_v2.manifest.json`'u dogrular (sha256 + 13 `code_sha256` anahtari; tutmazsa backtest baslamaz), sonra kosunun donemini (tam 2021-01-01 .. 2026-05-01) ve bayraklarini (`--id/--out-root` haric `bt_args()` ile birebir ayni) denetler; manifest `period` degeri kosunun kendi meta'sindan yazilir.
   Cikti: `research/ml/corpus_v2_taken.parquet` + `corpus_v2_taken.manifest.json` (sha256, `corpus_sha256`, `overlay_version`, `config_hash`, commit, `backtest_period`, alinan/alinmayan, donem sonu acik). **Eslesmeyen alinmis islem 0 olmali**: degilse betik cikis kodu 3 ile biter, kosu baslamaz, mentor incelemeli (derlem ile motorun aday kumesi ayrismis). Temiz agac sart; `research/ml/` altinda izlenmeyen dosyalar izinlidir.
4. **On hesap** (egitim/kapi KOSULMAZ; ozellik sagligi + guc; gereken IC rho yazdirilir, rho > 0,08 ise cikis 8 = "guc yetersiz", tarif kosulmaz):
   ```
   PYTHONPATH=src .venv/bin/python -m trader_ml.pipeline --recipe ml1-r02-long-ctx-1r --precheck-only --out research/ml/r02 \
     --corpus research/ml/corpus_v2.parquet --overlay research/ml/corpus_v2_taken.parquet --manifest research/ml/corpus_v2.manifest.json
   ```
   Bu asamada `--expect-*` verilmez (sha256'lar henuz dondurulmadi); manifest + katman manifesti yine dogrulanir.
5. **Dondurma:** `sha256sum research/ml/corpus_v2.parquet research/ml/corpus_v2_taken.parquet` ve kurulum bilgileri (commit, `config_hash`, satir sayilari, lightgbm surumu, on hesap ciktisi, n_trials) on kaydin **10. bolumundeki** tabloya yazilir ve **commit'lenir**. Tablo commit'lenmeden kosu baslamaz.
6. **Tek kosu (r02):** `--expect-*` ZORUNLU (yoksa cikis 5); sha256 uyusmazsa cikis 5, manifest/kod/katman butunlugu uyusmazsa cikis 6. Gercek kosu ayrica sunlari ister: temiz git agaci (19b `git_stamp` kurali; commit + agac durumu `gate_result.json`'a yazilir), `corpus_v2.sample_check.md` ("Bagimsiz yeniden hesap uyumu: 150/150"), katman manifestinde `corpus_sha256` == diskteki derlem. Kilitli donem ya da sema ihlali (`HoldoutViolation`/`SchemaError`) cikis 6 verir; tam sinir aninda (2026-05-01 00:00) cikis da `HoldoutViolation`dur: bu BILEREK boyledir, tetiklenirse duzeltmeye calismayin, mentora yazin.
   ```
   sudo systemd-run ... .venv/bin/python -m trader_ml.pipeline --recipe ml1-r02-long-ctx-1r --out research/ml/r02 \
     --corpus research/ml/corpus_v2.parquet --overlay research/ml/corpus_v2_taken.parquet --manifest research/ml/corpus_v2.manifest.json \
     --expect-corpus-sha256 <§10'daki sha256> --expect-overlay-sha256 <§10'daki sha256>
   ```
   Cikis kodlari: 0 tamam (KABUL/RED `gate_result.json`'da), 2 lightgbm yok, 3 ozellik sagligi reddi, 4 paket kalibrasyonu kisitlandi (RED; rapor + `gate_result.json` yazilir, paket yok), 5 sha256, 6 manifest/katman/kilitli donem/sema, 7 sira korumasi, 8 guc vetosu, 9 tek kosu kurali (`--out`'ta onceki sonuc var), 10 kirli git agaci. Rapor ve ham cikti commit'lenir (`docs/ml/r02-kapi-raporu.md`).
7. **r03** yalniz r02 raporu commit'lendikten sonra ve r02 KABUL degilse; sira korumasi `--prior-result research/ml/r02/gate_result.json` ister (tarif r02, `passed == false`, `synthetic == false`, `corpus_sha256` ve `overlay_sha256` bu kosununkilerle AYNI; yoksa/KABUL/baska girdi ise cikis 7). **r03 BLOKE durumu:** r02 cikis 3 (ozellik sagligi) ya da 8 (guc vetosu) ile biterse `gate_result.json` YAZILMAZ (sonuc degildir) -> r03 icin `--prior-result` olamaz -> r03 kosulamaz. Bu durumda kimse sira korumasini atlamaya ya da dosyayi elle uretmeye calismaz; mentor karari beklenir. Once r03 icin `--precheck-only` (sonucu 10. bolume yazin), sonra:
   ```
   ... --recipe ml1-r03-long-regime8 --out research/ml/r03 --prior-result research/ml/r02/gate_result.json \
     --corpus ... --overlay ... --manifest ... --expect-corpus-sha256 <ayni> --expect-overlay-sha256 <ayni>
   ```
- `n_trials` defterden okunur (`research/ml_trial_registry.csv`, tarif x 2 model; r02/r03 icin 10); `--n-trials` yalniz buyutebilir.
- **Tek kosu kurali (kodda zorunlu):** `--out`'ta `gate_result.json` ya da `oof_predictions.parquet` varsa gercek r02/r03 kosusu cikis 9 ile reddedilir; guc vetosu dali dahil hicbir dal mevcut sonucun/raporun uzerine yazmaz. Teknik kesintide (OOF yazilmadan; bellek/CPU limiti dahil) ayni commit/sha256'larla bir kez daha baslatilir: bos bir `--out` ile. Tek kosuda uretilen sonuc dosyalari silinmez/yeniden uretilmez.

### r02/r03 kaynak limitleri (olcum + oneri)

Tarife ozgudur (`recipes.V2_LIMITS`; r01 ve `config.py` sabitleri DEGISMEZ: 450 MB / 20 dk). `--research` limitleri kaldirir (sunucu disi). Eski 450 MB tavani derlem v2 boyutunda yetmez; asilirsa `MemoryError` ile is olur ve tek izinli yeniden baslatma yanar.

Olcum (sentetik, 43 ozellik tablosu; `taskset -c 0 nice -n 19`, 4 cekirdekli 16 GB makine; kapi tam yolda: Platt kelepcelenmesi atlanarak, 2000 bootstrap; r02 = 40, r03 = 8 ozellik; yaklasik beklenen derlem ~5,5 bin satir = r01'in 1.379 `prefiltered` adayi x 4 kat sure):

| Satir | r02 tepe RSS | r03 tepe RSS | CPU (r02 / r03) | 450 MB | 600 MB | 800 MB | 1000 MB |
|---|---|---|---|---|---|---|---|
| 5.500 | 416 MB | 410 MB | 5 sn / 2 sn | MemoryError | gecti | gecti | gecti |
| 13.000 | 790 MB | 781 MB | 9 sn / 4 sn | MemoryError | MemoryError | MemoryError | gecti |
| 26.000 | ~1.400 MB | ~1.400 MB | 13 sn / 9 sn | - | - | - | - |
| 60.000 | ~3.000 MB (r02, gurultu) | - | 41 sn | - | - | - | - |

Bellek kapidaki bootstrap (`run_gate`) tarafindan satir sayisiyla dogrusal buyur: tepe RSS ~ 140 + 0,05 MB x satir; `RLIMIT_DATA` RSS'nin ~150 MB uzerinde tetiklenir. Gercek veride LightGBM tum turlara kadar giderse en kotu durum yukaridaki "sinyalli" olcumlerdir.

**Oneri (kodda):** `RLIMIT_DATA` = **1200 MB** (beklenen boyutta ~2,9x pay; ~16 bin satira kadar yeter), `RLIMIT_CPU` = **1200 sn** (olculen 5-10 sn; sunucu 3-5x yavas olsa da 100x pay; degismedi). nice 19 ve tek cekirdek aynen. systemd tarafi: `-p MemoryMax=1500M -p MemorySwapMax=0 -p CPUQuota=100%` (2 GB sunucuda botla birlikte `free -m` ile once bakin; bos bellek < 1,8 GB ise kosuyu bot durmadan baslatmayin, mentora yazin). `--precheck-only` cikti satir sayisi 16 binden buyukse limit yetmez: kosmadan mentora yazin (tahmin formulu yukarida). Gercek tepe degeri `gate_result.json` `peak_rss_mb` ve raporda; raporda "sunucu tavani" artik tarifin limitini gosterir.

## Testnet yoklama, duman ve tatbikat betigi (WP-B7; `scripts/smoke_testnet.py`)

Ne zaman: Binance vadeli TESTNET anahtari gelince (B0 yoklamasi). **Durum: B0 yoklamasi anahtar gelince kosulabilir; T-13...T-16 ve D-1...D-8 adimlari yazildi ama duzeltme turu yeniden incelemesi (re-review) bitene kadar KAYIT ICIN KOSULMAZ (mentor karari).** Dry-run (plan yazdirma) her zaman serbesttir.

Guvenlik (kodda zorunlu, testli): yalniz `https://testnet.binancefuture.com`; `--env live` reddedilir; anahtar yalniz `BINANCE_API_KEY` / `BINANCE_API_SECRET` ortam degiskenlerinden okunur (hicbir yere yazilmaz, raporlarda maskelenir); testnette `apiRestrictions` olmadigindan cekme izninin KAPALI oldugunu `--ack-no-withdraw` ile siz onaylarsiniz (onay yoksa reddeder; live'da izin acik gorunurse reddeder); tek cift (`XRP/USDT`), asgari miktar, en fazla 1 acik pozisyon (hesapta baska pozisyon/emir varsa baslamaz); her kosu sonunda (hata olsa da) kendi emirlerini iptal eder ve actigi pozisyonu duzlestirir; `var-testnet/` ve `shared/testnet/KILL|PAUSE` yollari kullanilir.

```
cd /home/trader/SG-Github-AB-proje/trader
# anahtarlar: sudo -u trader icinde, dosyadan (komut satirina/gecmise yazmayin)
set -a; . /etc/trader-testnet.env; set +a       # BINANCE_API_KEY=... BINANCE_API_SECRET=...  (chmod 600, kok sahibi)
.venv/bin/python scripts/smoke_testnet.py --env testnet --list
.venv/bin/python scripts/smoke_testnet.py --env testnet --step b0 --dry-run              # once plan
.venv/bin/python scripts/smoke_testnet.py --env testnet --step b0-preflight --ack-no-withdraw   # salt okuma
.venv/bin/python scripts/smoke_testnet.py --env testnet --step b0 --ack-no-withdraw       # B0 yoklamasi (T-01..T-11 alt kumesi)
```
- Adimlar: `b0-preflight, b0-t01, b0-t02, b0-t03, b0-t04, b0-t05, b0-t06, b0-t07, b0-t08, b0-t09, b0-t10, b0-t11, b0-t12` (grup `b0`; T-04/T-07 tetik bekler: `--trigger-wait-s`, `--t13-stop-pct`; T-12 yalniz okuma, engelleyici degil); `t13, t14, t15, t16` (grup `t`); `d1 ... d8` (grup `drills`). `--step` virgulle ya da tekrarla.
- Cikti: `var-testnet/smoke/<zaman>/result.json` ve `result.md` (adim, durum GECTI/KALDI/FARKLI/ATLANDI/BEKLEMEDE/KISMI/GOZLEM, olculen sureler, temizlik kaydi). Gercek yanitlari `tests/engine/fixtures/binance/testnet/` altina kaydetmek ve sonucu `docs/motor/11-testnet-sonuc.md`'ye yazmak elle yapilir (anahtar/imza/hesap kimligi silinerek).
- Cikis kodu: 0 hepsi GECTI/ATLANDI; 1 KALDI/FARKLI/BEKLEMEDE/KISMI var; 2 guvenlik korkulugu (hicbir emir gitmedi).
- Etkilesimli adimlar (`t15, t16, d1...d7`): betik pozisyonu/stopu kurar ya da motorun varligini bekler, ne yapacaginizi yazar (iptables, `kill -9`, testnet arayuzunden elle iptal/emir) ve Enter bekler; sonra olculen kosullari dogrular. D-8 otomatiktir (sahte anahtarla `run`, cikis kodu 8 ve anahtar sizintisi denetimi).
- T-14: varsayilan ATLANDI (asgari miktarla kismi dolum olusmaz). Denemek icin `--partial-fill-multiple N` (N<=20, notional <= 200 USDT).
- T-15: betik KILL oncesi hesap genelinde pozisyon ve stop sayisini kaydeder; en az 2 acik pozisyon yoksa sonuc `KISMI` olur (GECTI degil). Motor iki pozisyon actiktan sonra kosulur.
- Bilinen sinirlar: "neden `trail_stop`" gibi defter alanlari motor tarafinda oldugundan elle `ledger` okunarak dogrulanir.

## Canli duman testi (28-29 Aralik; `scripts/smoke_live.py`)

**UYARI: testnet golge kosusu KABUL EDILMEDEN bu betik KOSULMAZ.** Once `docs/motor/11-testnet-sonuc.md` icinde acik KALDI olmamali, golge kosu (WP-B8) mentor tarafindan kabul edilmis olmali (11 §11-§12). Gercek para kullanir (asgari tutar; beklenen maliyet < 0,10 USD). Bir kez, 28-29 Aralik'ta, sizin basinda oldugunuz bir oturumda kosulur; cron/systemd ile calistirilmaz. Dry-run (`--dry-run`, `--list`) her zaman serbesttir.

Betigin sert kurallari (kodda, testli; atlatma bayragi YOKTUR):
- Yalniz uretim vadeli adresi (`https://fapi.binance.com`); `--env live` yazilmali, `--env testnet` reddedilir.
- `LIVE_CONFIRM` canli katmandaki `live.account_tag` ile ayni olmali; anahtarlar yalniz ortamdan (`BINANCE_API_KEY` / `BINANCE_API_SECRET`), her cikti ve raporda maskelenir.
- `api_restrictions()` para cekme ACIK ya da IP kisiti YOK diyorsa (ya da okunamazsa) **cikis kodu 8**; `LIVE_PERMISSION_ATTESTED` beyani bu betikte gecerli degildir.
- Risk kademe gunlugu (`<canli var_dir>/learner/risk_ladder.jsonl`) var ve gecerli olmali (`capital init` yapilmis) ve kademe durumu `ok`; KILL ya da herhangi bir giris duraklatma tutusu (`drawdown_review`, `capital_floor`, `user_cmd`...) varsa baslamaz.
- Tek cift (`XRP/USDT`), asgari tutar (tavan: min notional'in 2 kati, en cok 25 USDT), en fazla 1 pozisyon; hesapta baska pozisyon ya da acik emir varsa baslamaz. Yalniz betigin kendi emirleri/pozisyonu: `finally` blogunda yalniz kendi emirleri iptal edilir, yalniz kendi pozisyonu `reduceOnly` piyasa ile duzlenir (duz degilse koruyucu stop birakilir ve elle kapatma uyarisi yazilir).
- Her adimdan once `evet` beklenir; `evet` disindaki her yanit "simdi her seyi kapat"tir. Ilk gercek emirden once yazili ifade istenir: `GERCEK EMIR <account_tag>` (tam olarak). Otomatik onay bayragi yoktur.

Hazirlik (sunucuda, `trader` kullanicisi; motor ve telegram kosarken duman testi ayri `var-live/smoke/` rapor dizini kullanir, kagit botlari calismaya devam eder):
```
cd /home/trader/SG-Github-AB-proje/trader
# canli katman: config/engine.live.json (mode=live, live bloku, canli var_dir; kaldirac KONMAZ) go-live oncesi hazir olmali (11 §12, O-2)
# kademe gunlugu: capital init (12 §14) duman testinden ONCE, motor acilmadan once
.venv/bin/python -m trader_engine capital init --bot learner --env live --by <ad> --amount <alt hesaptaki tutar>
# DD-9: anahtar dosyasi root:root 0600; trader onu OKUYAMAZ. "set -a; source" yolu KALDIRILDI. Root olarak sarmalayici (systemd-run, anahtarlar
# systemd tarafindan yuklenir; betik anahtarlari okumaz/yazdirmaz):
bash /usr/local/lib/trader-root/current/deploy/canli_duman.sh --dry-run          # once plan
bash /usr/local/lib/trader-root/current/deploy/canli_duman.sh                    # gercek kosu; istemleri okuyarak ilerleyin
```
- Adimlar: S-0 acilis denetimi, S-1 kurallar/asgari miktar, S-2 izole marjin + kaldirac, (yazili onay), S-3 long giris, S-4 stop (%1, MARK_PRICE, reduceOnly), S-6 stop sikilastirma (yeni kabul, sonra eski iptal), S-9 hedef kur/iptal, S-C kendi pozisyonunu kapat, S-12 komisyon/kayit denetimi, S-13 cuzdan denetimi. Tek cift kurali nedeniyle S-5 (2. cift), S-7 (`kill -9`), S-8 (stop tetik bekleme), S-10/S-11 (duraklatma/KILL) betikte YOKTUR; elle/motorla `11-canli-broker.md` §12'ye gore yapilir.
- Cikti: `var-live/smoke/<zaman>/result.json` ve `result.md`. Sonuc `11-duman-testi-sonuc.md`'ye elle yazilir; mentor onayi olmadan canliya gecilmez.
- Cikis kodu: 0 tum adimlar GECTI; 1 KALDI/FARKLI (kalan adimlar atlanir, temizlik yapilir); 2 guvenlik korkulugu / operator durdurdu; 8 anahtar izni ya da acilis denetimi 8.
- Betik yanit vermez/kapanirsa elle yol: Binance uygulamasi -> alt hesap -> Vadeli -> Pozisyonlar -> "Tumunu kapat"; sonra sunucuda KILL kurulur.

## Disk bakimi ve disk uyarisi
- `trader-bakim.timer` (pazar 04:20 UTC, Persistent) haftada bir `scripts/bakim_run.py` calistirir (`MemoryMax=128M`, idle IO, tek seferlik; hata yutulur). `var/` altindaki sqlite dosyalarinda WAL `checkpoint(TRUNCATE)` + yalniz guvenliyse `VACUUM`; motor/feed'in surekli acik tuttugu `market.sqlite`, `ledger.sqlite`, `state.sqlite` dosyalarinda YALNIZ `wal_checkpoint(PASSIVE)` (VACUUM yok). Silme yalniz acik izin listesiyle ve 90 gunden eski: `var/rapor/**` (md/json/csv/txt/html/png), `var/*/weekly_summaries/*.md`, `exitcf_bt_*` gecici dizinleri, `var/*/snapshots/*`; her dizinde en yeni dosya kalir. Defterler, `counterfactual.sqlite`, `market.sqlite`, `var/history*`, `var/durum/*.json` asla silinmez. Ne yapildigi `journalctl -u trader-bakim` ozetinde. Elle: `sudo -u trader python3 -I scripts/bakim_run.py --var-dir var --dry-run`.
- journald siniri: `install.sh`, `deploy/trader-journald.conf` dosyasini `/etc/systemd/journald.conf.d/trader.conf` olarak kurar (`SystemMaxUse=300M`, `SystemKeepFree=1G`, `MaxRetentionSec=30day`); yalniz icerik degistiyse `systemctl restart systemd-journald` calisir (tekrar kurulumda dokunmaz).
- Saglik denetcisi `var/` dosya sistemi kullanimi >= %80 ise "Disk dolmak uzere (%NN)" (WARN), >= %95 ise ayrica CRIT uyarisi gonderir: ilk seferde bir kez, surerse en fazla 6 saatte bir, kapaninca tek "Duzeldi". journald sistem tarafinda sinirlanir; bu is ona dokunmaz.

## Canli durum dali (saatlik; `deploy/durum_yayinla.sh`, `trader-durum-yayin.timer`)

Sunucu saatte bir ozet verisini repo icindeki ayri `canli-durum` dalina, `ml/` klasorune yazar (CT'nin canli-durum duzeni). Boylece
orkestrator ve gelistirici Telegram iletimine gerek kalmadan okur. Yayimlanan dosyalar (izin listesi): `rejim.json`,
`gunluk_ozet_v1.json`, `pano.html` (ogrenme kartlari dahil anlik pano), `mutabakat_v1.json` + `mutabakat.md` (acik/kapanan islemler,
kasa), `strateji-veri-ml.md`, `tutarlilik_v1.json`, `durum.json` (motor durum dosyasi), `uretim.txt`.
Defter (sqlite), ortam dosyalari ve anahtarlar yayimlanmaz; bilinen sir kaliplari gorulurse o tur hic yayimlanmaz.

Kimlik yalniz sunucudaki SSH deploy anahtaridir (ozel kisim sunucudan cikmaz; GitHub'a yalniz `.pub` kismi eklenir). Anahtar yoksa
birim sessizce atlar. Bir kez, root olarak:

```bash
install -d -o trader -g trader -m 700 /var/lib/trader-durum-yayin /var/lib/trader-durum-yayin/.ssh
sudo -u trader ssh-keygen -t ed25519 -N "" -C "trader-durum-yayin" -f /var/lib/trader-durum-yayin/.ssh/id_ed25519
sudo -u trader sh -c 'ssh-keyscan -t ed25519 github.com > /var/lib/trader-durum-yayin/.ssh/known_hosts'
sudo -u trader ssh-keygen -lf /var/lib/trader-durum-yayin/.ssh/known_hosts   # SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU olmali; farkliysa DURUN
cat /var/lib/trader-durum-yayin/.ssh/id_ed25519.pub
```

GitHub -> repo -> Settings -> Deploy keys -> Add deploy key: baslik `trader-durum-yayin`, yukaridaki `.pub` satiri, **Allow write
access** isaretli. Sinir: deploy anahtari GitHub'da depo genelinde yazar (tek dala kisitlanamaz); betik yalniz `canli-durum`'a yazar.
`main` icin Settings -> Rules -> Rulesets ile "Restrict updates" onerilir. Deneme:

```bash
systemctl start trader-durum-yayin.service; journalctl -u trader-durum-yayin -n 5 -o cat
```

"yayimlandi" gorulmeli. "Permission denied (publickey)" = deploy anahtari eklenmemis ya da yazma izni yok. Kapatma:
`systemctl disable --now trader-durum-yayin.timer`.

## Canli/testnet anahtar carpisma denetimi (5c)
- Anahtar carpismasi: baska hesap/bot anahtarlarinin SHA256 ozetleri `/etc/trader-testnet.env` / `/etc/trader-live.env` icine `TRADER_DIGER_ANAHTAR_SHA256=etiket:hex64,...` olarak yazilirsa, bu surecin anahtari/gizlisi o ozetlerden biriyle eslesirse motor acilmaz (`key_collision: <etiket>`; deger asla yazilmaz). Ozet: `printf %s "$ANAHTAR" | sha256sum`.
