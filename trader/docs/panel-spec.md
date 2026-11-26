# Panel (pano) spesifikasyonu v1 — salt okunur, tek süreç

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. Panelde veto satırı ve ikiz kolu kaldırıldı (veto/ikiz yok).

Kaynak: 1L3A panosu (`/home/user/sselimgenc-oss/1l3a-proje`, **güvenilmez kopya: yalnız okunur, hiçbir şey kurulmaz/çalıştırılmaz**). Analiz: `otonom-trading-arastirma/research_notes/kullanici-projeleri/1l3a_analiz.md` §2, `1l3a_motor_derin_inceleme.md`. Bu belge kod ve commit içermez.

## 1. Değişmez kurallar

1. Yalnız `127.0.0.1` dinler (`0.0.0.0`/`::` yasak; başlangıçta bind adresi doğrulanır, farklıysa süreç çıkar). Erişim SSH tüneliyle: `ssh -L 8080:127.0.0.1:8080 <kullanici>@<droplet>`.
2. Panelde API anahtarı, Telegram token'ı, Binance anahtarı **yok**: `EnvironmentFile` yok, süreç bu değişkenleri görmez. `trader-telegram.env` vb. okunmaz.
3. v1 salt okunur: yalnız `GET`/`HEAD`; `POST/PUT/DELETE` → 405. İşlem, kill, onay/ret yok; bunlar Telegram'dan (`/onayla`, kill dosyası) yapılır. Panel kill dosyasını **okur** ama yazmaz.
4. Çalışma anında dış ağ yok: CDN, font, analitik, `fetch` ile dış URL yasak. Her varlık depoda (vendored) ve `Content-Security-Policy: default-src 'self'` ile zorlanır. Panel dışarı bağlantı da açmaz.
5. Bellek tavanı ≈ 60 MB (systemd `MemoryMax=64M`), 2 GB paylaşımlı droplet; botları/sağlık/ders süreçlerini aç bırakmaz (`Nice=10`).
6. Tüm okumalar `mode=ro` SQLite URI veya salt okunur dosya; panel hiçbir veri dosyasına yazmaz, ikinci yazar olmaz (defter-spec §9).
7. Panel yeni hesap yapmaz (1L3A ilkesi korunur): sayılar motor/defter/bütçe/ders/sağlık çıktısından aynen gösterilir; yalnız biçimleme, sıralama, ilk-N kesme, zaman farkı (bayatlık) ve çizim ölçeklemesi yapılır. Okunamayan kaynak "veri yok: <kod>" gösterilir, değer uydurulmaz (fail-closed gösterim).

## 2. 1L3A'dan neyin alınacağı (kaynak yol: `1l3a-proje/` altında)

1L3A panosu = `motor/canli/pano.py` (2065 satır, tek dosyalık statik HTML üreticisi; CSS 172–328, JS 329–~388) + 15 JSON/JSONL durum dosyası (`motor/canli/durum.py::DOSYALAR/EK_DOSYALAR`, sözleşme `motor/canli/DURUM_SOZLESMESI.md`). Üretici o JSON şemasına sıkı bağlı; bizim veri (status.json + SQLite defter + bütçe + ders + sağlık) farklı olduğundan **üretici doğrudan monte edilmez**. Karar tablosu:

| Parça | 1L3A kaynağı | Karar | Not |
|---|---|---|---|
| CSS (koyu/açık tema, kutu/tablo/chip/uyarı bandı) | `pano.py` `CSS` (satır 172–328) | **Monte (kopya, tek dosya `static/panel.css`)** | Dış font/URL yok (doğrulandı: `pano.py`'de `http(s)://` yok). Kopyadan önce satır satır okunur. |
| JS: tema düğmesi, yenile/yazdır, bayatlık bandı (`data-zaman`/`data-esik-dk`), tablo sıralama, süzgeç | `pano.py` `JS` (329–) | **Monte (uyarlama)** | `fetch('/api/…')` ile kısmi yenileme eklenir (§5). Bağımlılık yok. |
| Sekme iskeleti (radyo+label, CSS-yalnız sekmeler; JS'siz çalışır) | `html_olustur` (1993–2035), `SEKMELER` | **Fikir, yeniden yaz** | Bizim sekmeler §3. |
| Kutu/tablo/kullanım çubuğu yardımcıları | `_kutu`, `_tablo`, `_kullanim_cubugu`, `_p`, `_h`(escape) (399–520) | **Fikir, yeniden yaz** (JS'te; her metin `textContent` ile, `innerHTML` yok) | Python string HTML yerine JSON+JS render: sunucu küçük kalır. |
| Özsermaye eğrisi / düşüş grafiği (satır içi SVG) | `_egri`, `_dusus_grafigi`, `_mini_egri`, `_eksen` (528–720) | **Fikir** (kendi SVG'miz, ~60 satır JS) | Chart.js alınmaz (vendored 200 KB gereksiz; `arsiv/sg-pano/vendor/` kullanılmaz). |
| Kill-switch/uyarı şeridi (üstte, her sekmede görünür), `uyarilar()` | `pano.py` 60–104, `_serit` (817) | **Fikir** | Bizim uyarı kaynağı health raporu + status. |
| Açık pozisyon tablosu + stop riski | `_poz_tablosu`, `_stop_riski` (1275, 1380) | **Fikir** | Veri: `status.json.open_positions` (+ defter açık işlemler). |
| İşlem satırı çekmecesi (neden/MFE-MAE) | `_cekmece*` (1896–1940) | **Fikir (v1.1)** | Bizde defter karar olayı `features`/`skip_reason` var; v1'de yalnız satır, çekmece sonra. |
| Sağlık/kalp atışı kutuları | `_sekme_saglik`, `_kalp_atisi_kutulari` (1681–1720) | **Fikir** | Bizim kaynak: `health` raporu §3. |
| Dersler / koç / öneri kartı | `_dersler_html`, `_koc_html` (1733–1866) | **Fikir** | Veri: `lesson.py` deposu (§3). |
| Karne radarı, koni (Monte Carlo), kıyas, korelasyon, yoğunlaşma, aylık rapor | `_karne*`, `_koni_html`, `_kiyas_html`, `_korelasyon_html`, `_yogunlasma_html`, `_sekme_rapor` | **Alınmaz (v1)** | Bizde bu veriyi üreten motor yok; strateji sayısı az (learner+twin). Gerekirse v2. |
| Telegram metni üreticisi | `telegram_metni`, `terminal_ozet` (124–388) | **Alınmaz** | Bizde `trader_core/telegram.py` var. |
| Yerel sunum | `deploy/1l3a-pano-sunucu.service` (`http.server 8080 --bind 127.0.0.1`) | **Fikir (aynı model)**, kendi unit'imiz | Statik `http.server` yerine küçük API sunucusu gerekir (§4). |
| Üretim zamanlayıcısı (5 dk `oneshot`) | `deploy/1l3a-pano.{service,timer}` | **Alınmaz** | Biz isteğe bağlı canlı okuruz; zamanlayıcı yok. |
| Cloudflare Worker, Basic Auth, `pano_yayinla.sh`, `PANO_KILITSIZ` | `deploy/pano_worker.js`, `pano_yayinla.sh` | **Alınmaz (v1)** | Dış yayın kapsam dışı (kural 1,2). `PANO_KILITSIZ` yolu kesinlikle yok. Telefon erişimi SSH tüneliyle. |
| `atomik_yaz_json` | `motor/canli/durum.py` 94–112 | **Gerekmez** | Panel yazmaz; bizim `trader_engine/fileio.py` zaten var. |
| Eski paneller | `arsiv/sg-pano`, `arsiv/strateji-test-pano`, `arsiv/swing-sg/…/panel`, `arsiv/codex-algo/dashboard.py` | **Alınmaz** | Dış API/GitHub raw'dan veri çeker (kural 4'e aykırı); yalnız ekran düzeni fikri. |

Özet: **doğrudan monte = CSS + istemci JS çekirdeği (tema, bayatlık bandı, sıralama)**; geri kalan tüm ekranlar fikir olarak alınıp bizim veri kaynaklarımıza göre yeniden yazılır. `pano.py` hiçbir hâliyle içe aktarılmaz. Kopyalanan her dosyanın başına kaynak yol + tarih yorumu konur, `THIRD_PARTY_NOTICES.md`'ye eklenir (1L3A kullanıcının kendi projesi; yine de not düşülür).

## 3. Ekranlar ve veri eşlemesi

Bot adları: `learner`, `twin`. Yol ayarları `config/panel.json` (yeni, §6); telegram `TelegramConfig` ile aynı alan adları (`status_path`, `ledger_path`, `twin_ledger_path`, `budget_config`, `lesson_store`, `health_state`, `kill_file`).

| Sekme / widget | Kaynak (salt okunur) | Alanlar / çağrı | Not |
|---|---|---|---|
| **Üst şerit** (her sekmede): kill, kapı, bayatlık | `status.json` (her bot) | `kill`, `kill_state`, `gate.code`, `entries_open`, `entries_blocked_reason`, `loop_at`, `mode`, `dry_run` | `now − loop_at > 120 sn` → bayat bandı (05 §8.2 `health_run` eşlemesi ile aynı eşik). Dosya yok/bozuk → kırmızı "veri yok". |
| **Özet**: equity, gün başı equity, günlük zarar/bütçe %5, açık poz sayısı, sürüm | `status.json` | `equity`, `day_start_equity`, `wallet`, `counters`, `param_version_id`, `strategy`, `trigger_tf` | Günlük bütçe çubuğu: `0.05×day_start_equity` (telegram `section_ledger` ile aynı formül; paylaşılan sabit). |
| **Özet**: learner ↔ twin yan yana | iki `status.json` + iki defter | gün PnL/R, kapanan, kazanan/kaybeden, fark | Telegram `section_ledger` satırının yapısal hâli. |
| **Pozisyonlar** | `status.json.open_positions` + `Ledger.list_open_trades()` | `pair, side, qty, entry_price, stop`; defterden `leverage`, giriş zamanı | İkisi uyuşmazsa uyarı rozeti (mutabakat göstergesi). |
| **İşlemler**: son kapanan işlemler, süzgeç (bot/sembol/yön) | `Ledger._trades(...)` kapalı; ya da kamusal sorgu varsa o | `exit_ts, pair, side, realized_pnl, r_multiple, fee*` | Sayfalama: son 200. "Bugün" sınırı TSİ (`_istanbul_day_bounds_utc`). |
| **İşlemler**: karar olayları (girdi/atlanan, `skip_reason`) | `Ledger.list_decisions(since_ts, until_ts)` | `final_action, skip_reason, veto_status, risk_allowed` | 1L3A "reddedilen" kartı fikri (stop-uzaklık filtresi sessiz engelliyor dersi, analiz §180-182): atlama nedenleri sayılarla görünür. |
| **Eğri**: günlük kümülatif R / PnL (SVG) | Defter kapanan işlemler | `exit_ts`, `realized_pnl`, `r_multiple` | Hesap = toplama; "yeni hesap" sayılmaz, ama kaynak ve formül ipucuna yazılır. |
| **Bütçe** | `budget.BudgetGuard(cfg).status()` | `month_used_usd/monthly_cap_usd/month_state`, `services[k].used_usd/cap_usd/state`, `prices_verified`, `config_ok/store_ok` | `telegram.section_budget` içindeki yapılandırma çözümü (db yolu göreli → mutlak) ortak yardımcıya taşınır. |
| **Ders**: bekleyen öneriler, gölge dönem, son çalışma | `LessonStore(path, read_only=True, create=False)` | `open_requests()`, `get_state("shadow_start_day"/"shadow_end_day")`, `lesson_runs` son satır + `run_events` | Öneri kartında "Onay Telegram'dan: `/onayla <id>`" yazar; düğme yok. Defter `list_proposals(status=…, limit=…)` de okunur. |
| **Sağlık** | `health` durum dosyası (`/var/lib/trader-health/state.json`, saglik-spec §5.3) + her botun defterinden son yazma zamanı (§4 `last_write_at`) | `last_overall`, `last_run_at`, `fingerprints` (açık uyarılar), `restart_counts` | Panel `health.evaluate` çalıştırmaz (ölçüm toplamak `scripts/health_run.py` işi); yalnız son raporu/durumu gösterir. `last_run_at` eskiyse "sağlık denetimi çalışmıyor" uyarısı. |
| **Süreç/kaynak** (küçük kutu) | `/proc/meminfo`, `os.statvfs` | boş bellek, swap, disk | Sağlık spec'indeki eşiklerle renk; ek ölçüm yok. |

Telegram yeniden kullanımı: `section_ledger/budget/lesson` **metin** döndürür (panele uygun değil); bu yüzden altındaki yapısal yardımcılar (`_ledger_day`, `_istanbul_day_bounds_utc`, bütçe yapılandırma çözümü, ders deposu okuma) `trader_core`'da küçük bir `panel_data.py` altında paylaşılır ve **telegram.py bu dosyayı kullanacak şekilde sonradan** (ayrı iş, davranış değişmeden) yeniden düzenlenir; v1'de panel, `telegram` modülünün özel (`_`) adlarını doğrudan çağırmaz, kopya yerine ince saran fonksiyon yazılır ve eşdeğerlik testi (§8) eklenir. Telegram'ın `SectionError` kodları ("defter_yok", "depo_okunamadi"…) panelde "veri yok: <kod>" olarak aynen gösterilir.

## 4. Süreç düzeni

- **Tek Python süreci**, yalnız standart kütüphane: `http.server.ThreadingHTTPServer` (en çok 8 iş parçacığı), `sqlite3` `mode=ro`, `json`. Starlette/uvicorn bu makinede kurulu ama droplet'te garanti değil ve ~+25 MB bellek getirir; v1 **kullanmaz**. Bağımlılık eklenmez; `pyproject.toml`'a dokunulmaz.
- Dosyalar: `src/trader_panel/{server.py, data.py, __main__.py}`, `src/trader_panel/static/{index.html, panel.css, panel.js}`, `config/panel.json`, `deploy/trader-panel.service`, `tests/test_panel_*.py`. Derleme/bundle yok; statik dosyalar belleğe bir kez okunur.
- Uç noktalar (hepsi `GET`, JSON, `Cache-Control: no-store`): `/` ve `/static/*`; `/api/status` (iki bot status + kill + bayatlık), `/api/ledger?bot=&day=` (kapanan/açık/karar özeti), `/api/curve?bot=`, `/api/budget`, `/api/lesson`, `/api/tutarlilik`, `/api/pbo`, `/api/health`, `/api/system`, `/healthz` (süreç canlı). Bilinmeyen yol 404; yol gezintisi (`..`) yok (statik harita sabit liste).
- Her istekte kaynak başına bağlantı açılıp kapatılır (`sqlite3` `timeout=2`); sonuç 5 sn bellek önbelleği (aynı anda çok sekme DB'yi yormasın). Kaynak okuma hatası o uç noktada `{"ok":false,"code":"..."}` döner, süreç çökmez. İstek başına üst süre 3 sn; yanıt boyutu üst sınırı (≈ 512 KB; işlem listeleri sayfalı).
- **Bellek bütçesi**: CPython + dilimler ≈ 25–35 MB; önbellek ≲ 5 MB; hedef RSS ≤ 45 MB, `MemoryMax=64M`. Pandas/numpy import edilmez (`08-no-framework-guard.md` ile uyumlu).
- systemd (`deploy/trader-panel.service`, özet): `Type=simple`, `User=trader` (botlarla aynı, yalnız okuma izinli grup), `ExecStart=<venv>/bin/python -m trader_panel --config config/panel.json`, `Restart=on-failure`, `RestartSec=5`, `MemoryMax=64M`, `Nice=10`, `NoNewPrivileges=true`, `PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`, `ReadOnlyPaths=` veri dizinleri, `RestrictAddressFamilies=AF_INET AF_UNIX`, `IPAddressAllow=localhost` + `IPAddressDeny=any`, `EnvironmentFile` yok, `After=` botlardan bağımsız (botlar kapalıyken de açılır, "veri yok" gösterir).

## 5. Yenileme modeli

- Sayfa bir kez yüklenir; `panel.js` her **10 sn** görünür sekmenin uç noktasını `fetch` eder (üst şerit her 10 sn; diğerleri sekme açılınca + 30 sn). Sekme gizliyken (`document.hidden`) yenileme durur. Elle "Yenile" düğmesi.
- Her yanıt `generated_at` taşır; istemci kendi saatine güvenmez: bayatlık = sunucu `now` − kaynağın `loop_at`/`probed_at`. Sunucuya ulaşılamazsa üstte kırmızı "panel bağlantısı yok" bandı (1L3A bayat bandı mantığı).
- Saatler TSİ gösterilir, API UTC `...Z` döner (defter/status biçimi).
- Sunucu tarafı olay akışı (SSE/WebSocket) yok: iş parçacığı/bellek maliyeti gereksiz.

## 6. Güvenlik

- Bind doğrulaması (§1.1); `config/panel.json` yalnız `host` (sabit `127.0.0.1`, değiştirilebilir değil), `port` (öntanımlı 8080), veri yolları. Yollar doğrulanır; yazma izni olan dizin gösterilirse uyarı.
- Kimlik doğrulama v1'de yok (tünel + loopback = erişim kontrolü; 1L3A yerel modeliyle aynı). Soru 3'e bakın.
- Yanıt başlıkları: `Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`. `Host` başlığı `127.0.0.1:<port>`/`localhost:<port>` dışındaysa 400 (DNS rebinding savunması).
- İstemcide veri `textContent` ile basılır (XSS yok; defter/ders alanlarındaki serbest metin `telegram.neutralize` gibi düz metin). Log'lara sır/yol ayrıntısı yazılmaz; `Authorization` gibi başlık yok zaten.
- Hata mesajlarında yığın izi yok; yalnız kısa kod (`defter_yok`, `depo_okunamadi`, `status_bozuk`).
- Panel hesabı veri dosyalarına yalnız okuma izni taşır; kill dosyası dizini dahil yazma izni yok.

## 7. Dağıtım

`deploy/trader-panel.service` + `deploy/trader-panel.env.example` **yok** (env gerekmiyor). Kurulum adımları belgesi: unit kopyala → `daemon-reload` → `enable --now`; SSH tüneli komutu; `journalctl -u trader-panel`. Geri alma: `systemctl disable --now trader-panel` (başka hiçbir bileşene bağımlılık yok).

## 8. Test planı (tests/test_panel_*.py, `pytest`, ağ yok)

1. **Değişmezler**: sunucu `0.0.0.0` bind isteğine açılmaz; `POST/PUT/DELETE` → 405; `Host` sahte → 400; bilinmeyen/`..` yol → 404; yanıt başlıkları (CSP vb.) var.
2. **Ağ yasağı**: `static/*` içinde `http://`, `https://`, `//cdn`, `@import url(`, `<link href=http` taraması (regex testi); CSP `default-src 'self'`.
3. **Salt okunur**: geçici defter/bütçe/ders deposu fikstürü ile uç nokta çağrıları sonrası dosyaların sha256 ve `mtime` değeri değişmemiş; `mode=ro` ile yazma girişimi `OperationalError` (veri katmanında doğrudan test).
4. **Veri eşlemesi**: örnek `status.json` (05 §8.2 örneği) → `/api/status` alanları birebir; defter fikstüründe bilinen işlemler → `/api/ledger` PnL/R toplamı = `telegram._sum` sonucu (eşdeğerlik testi, `section_ledger` metnindeki sayılarla karşılaştırma); bütçe `status()` ↔ `/api/budget`; ders `open_requests` ↔ `/api/lesson`.
5. **Fail-closed gösterim**: status.json yok/bozuk/eski, defter yok, depo kilitli → `{"ok":false,"code":…}` ve süreç ayakta; `loop_at` 121 sn eski → bayat işareti, 120 sn → yok.
6. **Telegram eşdeğerliği**: aynı fikstürde paylaşılan yardımcılar `telegram.section_*` ile aynı sayıları verir (yeniden düzenleme sonrası da).
7. **Bellek/yük**: 200 işlemli defter + 8 eşzamanlı istemci × 60 sn döngüsü; RSS ≤ 60 MB (`resource`/`/proc/self/status`); 3 sn zaman aşımı sınanır.
8. **Kaynak tarama**: `trader_panel` hiçbir sır değişkeni okumaz (`TELEGRAM_*`, `*_KEY`, `*_TOKEN` için `os.environ` erişimi yok — statik grep testi); `trader_core.telegram`'dan yalnız sabitleri/yardımcıları içe aktarır, istemci/gönderici sınıflarını değil.
9. **İstemci JS** (v1.1): Node varsa render fonksiyonları için küçük birim test (XSS dizgisi `<img onerror>` düz metin kalır); yoksa tarayıcıda elle kontrol listesi: 4 sekme, tema, bayat bandı, JS kapalıyken ilk sayfa.
10. **systemd**: `systemd-analyze verify deploy/trader-panel.service`; droplet'te `ss -ltnp` yalnız `127.0.0.1:8080`, `curl` dışarıdan reddedilir.

## 9. Mentora açık sorular

1. 1L3A `pano.py` üreticisi doğrudan monte edilmeyip yalnız CSS/JS çekirdeği alınıyor, kalan ekranlar yeniden yazılıyor. Uygun mu, yoksa 1L3A'nın karne/koni/kıyas/aylık rapor sekmeleri (bizde veri kaynağı yok) v2'de zorunlu mu?
2. Bağımlılık: stdlib `ThreadingHTTPServer` ile devam edelim mi (daha az bellek, sade) yoksa droplet'e Starlette+uvicorn kurulumu kabul mü (SSE ve daha rahat yönlendirme)?
3. Kimlik doğrulama: SSH tüneli + loopback yeterli mi, yoksa ek parola (Basic Auth, panelde sır tutmak kuralıyla çelişir; hash'lenmiş parola yapılandırması gerekir) istenir mi? Telefondan erişim yalnız SSH uygulaması üzerinden olabilir mi?
4. Telegram bölüm üreticilerinin yapısal yardımcılara ayrılması (`panel_data.py` + `telegram.py` yeniden düzenleme) şimdi mi, panel v1 sonrası mı yapılsın (telegram testlerini bozmama riski)?
5. Defter API'sinin kamusal sorgu yüzeyi: panelin `Ledger._trades` gibi özel adı çağırması yerine `list_closed_trades(since, until)` gibi kamusal bir salt okunur metot eklensin mi (`ledger.py` bu iş paketinin dışında)?
6. Sağlık durumu: panel yalnız `state.json`'u okuyor; "bot defteri yazabiliyor mu" için `health_probes.probed_at` ham okunsun mu, yoksa `gate_status_readonly()` (saglik-spec §12 Soru 2) beklensin mi?
7. Günlük bütçe çubuğu ve diğer sabitler (%5, 120 sn bayatlık) panelde sabit kodlanmak yerine `risk.py`/`engine.*.json` yapılandırmasından mı okunsun (tek doğruluk kaynağı)?
8. Gizli/kapalı süre için "panel açık bırakılırsa tarayıcı 10 sn'de bir çeker" yükü kabul mü; yoksa yenileme varsayılan 30 sn mi olsun?

## 10. Mentor kararları (16 Kasım 2026)
1. 1L3A'dan yalnız CSS/JS çekirdeği alınır, ekranlar yeniden yazılır. v2: yalnız aylık rapor ve öğrenen↔ikiz karşılaştırması; karne/koni/korelasyon/yoğunlaşma yok (veri kaynağı yok).
2. Stdlib `ThreadingHTTPServer`; Starlette ve SSE yok.
3. Ek parola yok; SSH tüneli + loopback yeterli. Telefonda Telegram ya da port yönlendirmeli SSH uygulaması.
4. `telegram.py` yeniden düzenlemesi sonra (kağıt döneminde, canlıdan önce). v1'de yeni `panel_data.py` + eşdeğerlik testleri; `telegram.py`'ye dokunulmaz.
5. `Ledger.list_closed_trades(since, until, limit)` kamusal salt-okunur yöntemi eklenir; `_trades` kullanılmaz.
6. Sağlık: yalnız `state.json` + `status.json.loop_at`; ham `health_probes` okunmaz (`gate_status_readonly()` beklenir).
7. Sabit sayı yok: günlük sınır `risk.py`/motor yapılandırmasından, bayatlık mevcut `STALE_S`'den. (`telegram.py`'deki 0.05 ve 120 sabitleri madde 4 düzenlemesinde düzeltilir.)
8. Yenileme: üst şerit 10 sn (yalnız dosya), gerisi 30 sn; sekme gizliyken durur.

Zorunlu düzeltmeler:
- Defter WAL kipinde: `ReadOnlyPaths` altında `mode=ro`, `-shm`/`-wal` yokken (botlar durmuş) açılmayabilir. Birim tasarımından önce bot çalışırken ve durmuşken salt-okunur bağlamada test edilir.
- Port 8787 (8080 1L3A paneliyle çakışır).
- En çok 8 eşzamanlı istek için semafor ve panel tarafında istek zaman aşımı açıkça yazılır (stdlib bunu kendisi uygulamaz; `Ledger` 5 sn busy timeout'u sabit).
- "JS olmadan çalışır" iddiası ve ilgili test maddesi çıkarılır.

Zamanlama: 30 Kasım için gerekli değil (kağıt başlangıcını Telegram raporu karşılar). Kağıt döneminin ilk iki haftasında gerçek veriyle yapılır; canlıdan önce kararlı olmalı.

## 11. Kullanıcı yanıtı (16 Kasım 2026)
Kullanıcı 1L3A panelinde en çok **Özet** sekmesine bakıyor (`motor/canli/pano.py` `_sekme_ozet`). Bu yüzden v1'in ana ekranı 1L3A Özet düzenini izler:
- Özsermaye eğrisi + kutular: max düşüş, başlangıç, zirve özsermaye, kapanan işlem sayısı.
- Sağ sütun: risk payı (açık risk / limitler) ve sağlık özeti.
- Zirveden düşüş grafiği, günlük K/Z grafiği.
- Takvim (günlük K/Z ısı haritası; güne dokununca o günün işlemleri).
- Öğrenen↔ikiz karşılaştırması bu ekrana kapalı bir bölüm olarak eklenir (v2 yerine v1'de, veri hazır olduğu için).
- 1L3A'daki "Kıyas", "Dönemsel getiri (ajan)", "Beklenti aralığı", "Aralık karnesi" ve "İçgörüler" alınmaz (veri kaynağı yok).
Veri: özsermaye geçmişi ve günlük K/Z defterin kapanmış işlemlerinden (`list_closed_trades`) ve status.json'dan türetilir; motor ayrı bir ozet dosyası yazmaz.

## 12. Uygulama notları (v1, 16 Kasım 2026)

**Dosyalar.** `src/trader_panel/{__init__,__main__,server,data}.py`, `src/trader_panel/static/{index.html,panel.css,panel.js}`, `src/trader_core/panel_data.py` (paylaşılan yapısal yardımcılar), `config/panel.json`, `deploy/trader-panel.service` (`install.sh` kurar ve etkinleştirir; `uninstall.sh` `trader-*.service` glob'u ile kaldırır), `Ledger.list_closed_trades(since, until, limit=200)` (`limit` ≤ 10000; çıkış zamanı yeniden eskiye; `since` dahil, `until` hariç). Testler: `tests/test_panel_*.py`, `tests/test_ledger_list_closed.py`, `tests/panel_support.py`. Kaynak yorumları: `panel.css` ilk satırı, `panel.js` başlığı, `THIRD_PARTY_NOTICES.md`.

**Sapmalar / seçimler (kapsam eklenmedi, yalnızca §10-§11'in gerektirdiği).**
1. Port 8787, `host` değiştirilemez (başka değer `ConfigError`); `config/panel.json` yolları engine sözleşmesine göre: `var/<bot>/status.json`, `var/<bot>/ledger.sqlite` (telegram'ın `user_data/ledger_*.sqlite` yolundan farklı: motor defterini buraya yazar).
2. §3'teki uç noktalara ek olarak `/api/risk` (Risk payı) ve `/api/compare` (öğrenen↔ikiz) eklendi; §11 Özet düzeni bunları gerektirir. Tüm uç noktalar `{"ok":…,"generated_at":…}` döner; kaynak okunamazsa yalnız o uç nokta `{"ok":false,"code":…}`.
3. `STALE_S` (120) `trader_core.panel_data`'da tek tanımdır: `telegram.py` `trader_engine`'i içe aktardığı için panel onu içe aktaramaz; eşitlik `tests/test_panel_equivalence.py` ile sınanır (madde 4 düzenlemesinde tek kaynağa iner). Günlük zarar sınırı ve açık/aynı yön risk sınırları `risk.LOCKED_CFG` oranlarından hesaplanır; sağlık renk eşikleri `health.DEFAULT_CFG`'den; sağlık denetimi tazelik eşiği `panel.json: health_stale_s`.
4. Başlangıç özsermayesi `config/engine.base.json: wallet_start` dosyasından (yalnız JSON okuma; `trader_engine` içe aktarılmaz). Okunamazsa eğri kümülatif K/Z'ye düşer, yüzde düşüş/başlangıç/zirve "okunamadı" gösterilir. Eğri defterin son ≤ 5000 kapanan işleminden; aşılırsa panelde not düşer.
5. Bayat/yok/bozuk `status.json`: API `data: null` ve `banner: "BAYAT: <TSİ zaman>'dan beri"` (zaman bilinmiyorsa `"BAYAT: durum dosyası okunamadı (<kod>)"`) döner; son bilinen değer hiç gönderilmez, canlı değere bağlı risk uç noktası da `ok:false` olur. Eşik: `age > STALE_S` (120 sn dahil değil bayat değil).
6. `market.sqlite` v1'de okunmaz (§3 tablosunda widget yok); bütçe `BudgetGuard.status()` ile okunur (yazmaz: rollback-journal, `write=False`; testte ayrı yetkisiz kullanıcıyla salt okunur dizinde doğrulandı) — `mode=ro` URI'si yalnız defter ve ders deposu için kullanılabiliyor.
7. Zaman aşımı: iş parçacığı 3 sn'de bırakılır (503 `zaman_asimi`) ama bitene kadar semaforu tutar; 8 üstü istek 1 sn bekler, sonra 503 `mesgul`. Yanıt üst sınırı 512 KB.
8. Test: gerçek süreçte 200 işlemli defter + 8 eşzamanlı istemci × 4 sn: RSS tepe ≈ 37 MB (tavan 60 MB).

**WAL salt okunur bağlama testi (§10 zorunlu düzeltme).** `tests/test_panel_readonly.py`, SQLite 3.53, yetkisiz kullanıcı (uid 65534, `setpriv`) ve `chmod 555` dizin (systemd `ReadOnlyPaths` benzeri). Sonuç:
- **Yazar (bot) açık, `-wal`/`-shm` var, dizin salt okunur, okuyan farklı kullanıcı: AÇILIR**, okuma doğru, hiçbir dosya oluşmaz/silinmez/değişmez (sha256+mtime aynı).
- **Yazar kapalı (temiz kapanış `-wal`/`-shm`'i siler), dizin salt okunur: AÇILAMAZ** (`attempt to write a readonly database`; `mode=ro` yine de `-shm` oluşturmak ister). Panel bunu çökmeden `veri yok: wal_yok_salt_okunur` olarak gösterir. Yani bot durmuşken Defter/Eğri/Risk/Özet defter kısımları görünmez; Bütçe/Ders/Sağlık/Durum etkilenmez (bütçe rollback-journal; ders deposu WAL olduğundan aynı kural).
- Dizin **yazılabilir** ve yazar kapalıysa `mode=ro` açılır ama SQLite `-wal`/`-shm` oluşturur (ana DB dosyası aynı kalır). Üretimde `ReadOnlyPaths` bunu engeller; geliştirme/test dizinlerinde bu yan etki beklenir.
- Karar: `immutable=1` ile yedek açma eklenmedi (yazar başlarsa tutarsız okuma riski; fail-closed seçildi). Bot hep çalıştığı için üretimde ilk durum geçerlidir; bot bakım için durdurulursa panel "veri yok" der (istenirse kararlı bir alternatif: motor kapanışta `-wal`'i bırakmaz → `gate_status_readonly()` bekleniyor, soru §9.6).

## 13. PC + iPhone erişimi (mentor kararı, 16 Kasım 2026 — revize)
Kullanıcı gereksinimi: panel hem bilgisayarda hem iPhone'da, aynı veriyle; kullanıcı cihazına kurulum istemiyor ve diğer projelerinde (1L3A, CT) Cloudflare Worker kullanıyor. İlk karar (Tailscale) bu bilgiyle **değiştirildi**. Karar: **1L3A tarzı statik yayın — Cloudflare Worker + Basic Auth.**
- Sunucu: panel "anlık görüntü" kipinde verisi gömülü, tek, kendi kendine yeten bir HTML üretir; üstünde görünür "oluşturulma zamanı" damgası ve bayatlık şeridi. Zamanlayıcı 5 dakikada bir `wrangler deploy` ile yükler (veri en çok ~6 dk eski). Canlı sunucu 127.0.0.1'de kalır.
- Worker 1L3A'dan alınır (`deploy/pano_worker.js`): Basic Auth, fail-closed, parola Worker sırrı. **Kilitsiz yayın bayrağı yok.**
- Kullanıcı: Cloudflare'da kapsamlı bir API anahtarı oluşturur (güvenli formla; sohbete yazılmaz), parolayı belirler (rastgele, 32+ karakter), adresi yer imine ekler. Kurulum yok.
- Güvenlik: Basic Auth HTTPS üzerinden, ama hız sınırı/kilitleme yok → uzun rastgele parola. Wrangler anahtarı tek Worker'a daraltılamaz: sunucu ele geçirilirse 1L3A ve CT Worker'ları da üzerine yazılabilir → ayrı Cloudflare hesabı ya da bu riski kabul (kullanıcı kararı). Anlık görüntüde yalnız pozisyon/özsermaye/özet; asla anahtar yok.
- Reddedilen: Tunnel + Access (Cloudflare DNS'te alan adı gerekir; trycloudflare'de Access yok, adres değişken); Tailscale (cihaz kurulumu).
- Sonra (doğrulanmadı): workers.dev üzerinde Cloudflare Access e-posta kodu Basic Auth'un yerini alabilir.
- **19 Kasım 2026 (kullanıcı kararı): Basic Auth ve parola KALDIRILDI; koruma Cloudflare Access.** Worker, Access JWT'sini (`Cf-Access-Jwt-Assertion`, RS256, takım `slmgncortak`) doğrular; yoksa 403 (fail-closed). `/rejim.json` ve `/gunluk_ozet_v1.json` herkese açık kalır (Access'te yol bazlı Bypass uygulaması). Kurulum adımları: `docs/sunucu-kurulum.md`.
- **20 Kasım 2026 (kullanıcı kararı): pano KİLİTSİZ.** 1L3A ve CT panoları gibi şifresiz/Access'siz; kâğıt dönemi bitince hepsi birlikte kapatılacak. Worker Access JWT doğrulaması kaldırıldı; yalnız GET/HEAD (diğerleri 405); güvenlik başlıkları ve orkestra kapısı çerçeve izni aynen. Pano anahtar/parola içermez.
- Zamanlama: ~1–2 gün; 30 Kasım'dan önce sığar.
- **Kullanıcı kararı (16 Kasım 2026):** Mevcut Cloudflare hesabı kullanılır (ayrı hesap açılmaz). Hesap çapındaki anahtar riski kabul edildi; anahtar yalnız "Workers Scripts: Edit" izinli, sunucuda 0600 dosyada tutulur.

## 14. DOĞRULAMA sekmesi: Tutarlılık ve PBO / Holdout (19 Kasım 2026)

Salt okunur iki bölüm (`/api/tutarlilik`, `/api/pbo`; anlık görüntüye de girer). Dosya okuma `trader_core.panel_data` içindedir.
- **Tutarlılık**: `var/durum/tutarlilik_v1.json` (şema `ml.tutarlilik.v1`, `docs/motor/tutarlilik-raporu-spec.md`). Yol `config/panel.json` `tutarlilik_path` ile, yoksa defter dizininin üstü + `durum/` (veri kökü). Tablo: kurulum, eşleşme %, giriş/çıkış kayma (bps), kâğıt R, geri test R, uyarı; üstte dönem, üretim, `uyari_nedenleri`. Dosya yok, bozuk, şema yanlış ya da `uretim` 8 günden eski ise `{"ok":true,"var":false,"neden":...}` ve arayüzde "rapor yok".
- **PBO / Holdout**: `research/holdout/pbo_ozet.json` (aile tablosu: PBO, DSR, yapılandırma sayısı, T, yorum) ve `muhur.json` (mühür tarihi, dosya sayısı, `acildi`, birleşik özetin ilk 12 karakteri). Yollar `pbo_path` / `muhur_path`, yoksa yapılandırma dizininin üstündeki kod ağacı `research/holdout/` (sunucuda sürüm kod ağacı). Eksik/bozuk dosya yalnız o bölümde "yok (neden)" gösterir; anlık görüntü ve diğer sekmeler etkilenmez.

### 14.1 Çıkış kanıtı ve alınmayan sinyal kartları (19 Kasım 2026; haber/duygu kartları 21 Kasım 2026'da silindi)

Doğrulama sekmesine salt okunur kartlar daha (`/api/ciktikaniti`, `/api/alinmayansonuc`; anlık görüntüye de girer). Motor/karar davranışı değişmez; `exit_counterfactual.py` yalnız okunur (şema ile uyumlu kendi salt okunur sorgusu).
- **Çıkış kanıtı**: `var/learner/exit_counterfactual.sqlite` (`config/panel.json` `exitcf_path`; yoksa defter dizini). `ecf_outcomes` (exitcf-v1: iz sürme `trail_atr` ± bir adım) ve `ecf_modes` (exitcf-v2: başa-baş / kısmi kâr). Kurulum (`setup`) başına: işlem sayısı, mevcut çıkışa göre ΣR farkı (yukarı, aşağı, başa-baş, kısmi; işlem sayısıyla), son hesap zamanı. Pencere son 120 gün, kaynak paper/testnet, yalnız pencere kapanmış satırlar (ders ile aynı). Ders deposunda açık talep ya da öneri `trail_atr` (yukarı), `exit_breakeven`, `exit_partial` içeriyorsa ilgili satırda ve üstte "öneri bekliyor". Depo yok/bozuk/boşsa "veri yok (neden)".
- **Alınmayan sinyal × sonuç (R)** (`/api/alinmayansonuc`, `alinmayan_sonuc_path`; yoksa veri kökü `durum/alinmayan_sonuc_v1.json`; belirtim `docs/alinmayan-sonuc-spec.md`): atlanan adayların "alınsaydı" sonucu engel nedenine göre (son 7 gün + tüm zamanlar) ve son satırda karşılaştırma için alınan işlemler; satır biçimi CT `rejim_sonuc_v1` ile aynı, ama birim R (başlık "Toplam PnL (R)"), çözülmeyen aday sayısı ayrıca yazılır. Dosya yok/bozuk/boş ise "veri yok".
