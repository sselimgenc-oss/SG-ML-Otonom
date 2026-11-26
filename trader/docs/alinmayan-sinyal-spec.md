# Alınmayan sinyal gece işi (plan 25a)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


Amaç: atlanan kararların "alsaydık ne olurdu" sonucunu saklamak; ders kuralları (gevşetme) ve ML derlemi, yalnız aldığımız işlemlerden öğrenip kendi önyargısını büyütmesin (tasarım kararları, 17 Kasım).
Kod: `src/trader_core/counterfactual.py` (saf hesap + depo), `scripts/counterfactual_run.py` (CLI). Birim: `deploy/trader-counterfactual@.service|.timer`.

## 1. Girdiler (yalnız salt okunur)
- **Defter** `var/<bot>/ledger.sqlite`: `final_action='skipped'` kararlar, **her** `skip_reason` (veto_*, risk_denied, stop_width, rr_below_min, entry_gate_closed, order_failed, ml_filter, other). Kullanılan alanlar: `id, pair, side, setup, trigger_tf, bar_close_ts, planned_entry, planned_stop, planned_target, skip_reason`. Defter `mode=ro` açılır (`open_ledger(read_only=True, migrate=False)`); alınan kararlara dokunulmaz.
- **market.sqlite** `var/market.sqlite`: 1 saatlik `last` mumları (`mode=ro`, düz `sqlite3`; `trader_engine` içe aktarılmaz). 1 dakikalık mum kullanılmaz: ML etiketi 1 saatliktir, parite için aynı ızgara.

## 2. Sonuç tanımı
Pencere: karar mumunun kapanışından (`bar_close_ts`, yukarı 1 saate yuvarlı) sonraki ilk mumun açılışından başlayan **72 adet** 1 saatlik mum (karar mumunun kendisi dahil değil). Giriş fiyatı = `planned_entry` (gerçek dolum değil; ML etiketiyle aynı). R = |planned_entry − planned_stop|. Aynı mumda iki bariyer de değerse **stop önce** sayılır. Maliyet: tur başına `2·(fee+slip)·entry/R` R, `fee=slip=0,0005` taraf başına (R cinsinden `cost_r`).

İki yöntem, her karar için iki satır (`method`):
| method | alt bariyer | üst bariyer | zaman |
|---|---|---|---|
| `barrier` | planned_stop (−1 R) | entry ± 2 R (`planned_target` kullanılmaz) | 72. mum kapanışında `±(close−entry)/R` |
| `plan` | planned_stop (−1 R) | `planned_target` (yoksa — T1 — yalnız stop/zaman) | aynı |

**Plan ufku (v2):** `plan` yöntemi 72 değil **48 mum** (`PLAN_HORIZON_BARS`) oynatılır (ders kanıtı planlanan stop/hedefin elde tutma süresine yakın olsun diye; zaman çıkışı 48. kapanıştadır, `bars_held ≤ 48`); pencere/sızıntı kuralı yine 72 mumun tamamını bekler. `barrier` 72 kalır.

`barrier`, `trader_ml.labels.label_candidates` etiketiyle (`label`, `barrier_net_r`) **bit düzeyinde aynıdır** (formül `trader_core`'a kopyalandı: trader_ml eğitim tarafıdır, çekirdek ona bağlanamaz; `tests/ml/test_counterfactual_parity.py` sabitleri ve rastgele yollarda etiket/net R/bitiş zamanını eşitler). ML'in 48 mumluk "referans çıkış" net R'si ayrı bir ölçüdür ve burada **yok**; `plan` ufku 48 mumdur (yukarıdaki not).

## 3. Saklanan alanlar (`cf_outcomes`, anahtar: bot, decision_id, method)
`hyp_outcome` (1 = hedef önce, 0 = stop/zaman; NULL = hesaplanamadı), `hyp_r_gross`, `hyp_r_net` (= gross − cost_r), `cost_r`, `exit_reason` (`target|stop|time|data_gap|invalid_plan`), `bars_held` (çıkışın pencere içindeki sırası, 1..72), `computed_at`, `version` (kural sürümü; sabitler/formül değişirse artar, eski satırlar yeniden yazılmaz; **v2**: plan ufku 48 + geçersiz hedef; `outcomes(method='plan')` yalnız `version ≥ 2` okur — v1 plan satırları ders kanıtına girmez, depo henüz üretimde değilse silinip yeniden hesaplanabilir), ayrıca karar kimliği: `pair, side, setup, trigger_tf, skip_reason, decision_ts, planned_*, window_start_ts, window_end_ts`.
Geçersiz plan (stop yanlış tarafta/eşit): iki satır `invalid_plan`, sayı yok. **Hedef kâr tarafında kesinlikle değilse** (long: `target ≤ entry`; short: `target ≥ entry`; ya da sonlu olmayan) yalnızca `plan` satırı `invalid_plan` olur (barrier etkilenmez); aksi halde yanlış taraftaki hedef sahte kazanç (`outcome=1`) üretirdi (ör. long giriş 100, stop 99, hedef 99,5). `r_net` NULL olan satırlar özet/rapora girmez.

## 4. Sızıntı ve idempotans
- Bir karar yalnızca `now ≥ pencere_bitişi` (kararın ufku **tamamen** dolmuş) ise hesaplanır; erken bariyer vurusu bile beklenir (sonuç aynı olurdu, ama "yarım veriye bakmama" kuralı sadedir). `now` enjekte edilir.
- Pencere 72 mumun **tamamını** içermeli (açılış zamanları aralıksız) ve her mumun `written_ms ≥ kapanış` olmalı (kapanmadan yazılmış mum sayılmaz). Eksikse bekler; ufuk + 24 saat sonra hâlâ eksikse `data_gap` satırları yazılır (kalıcı, bir daha denenmez).
- Kilitli dönem (2026-05-01 → 2026-11-01): pencere ile kesişen karar **hiç okunmaz** (sayaç `holdout_skipped`).
- Satır yazıldıktan sonra değişmez: `INSERT … ON CONFLICT DO NOTHING`; iki yöntem tek işlemde yazılır; zaten tam olan karar taranmaz. Yeniden çalıştırmak güvenlidir.

## 5. Depo: ayrı `var/<bot>/counterfactual.sqlite` (ledger'a göç yok)
Seçim gerekçesi: (1) **Motor defterin tek yazarıdır**; v3→v4 göçü motoru, ders servisini, panoyu, rapor ve yedeği aynı anda sürüm bağımlısı yapar (`SCHEMA_VERSION` uyuşmazlığı motoru durdurur) — bu iş için çok geniş etki. (2) Ayrı dosya yazıcıyı (bu iş) ve okuyucuları ayırır: motor/defter kilidi ve `synchronous=FULL` yazma yolu etkilenmez; iş çökerse/bozulursa defter hiç etkilenmez, dosya silinip baştan hesaplanabilir (türetilmiş veri). (3) Birim sandbox'ı net: defter ve market `ReadOnlyPaths`, yazılabilir yalnız `var/<bot>`. (4) Bot başına dosya (`learner`, `twin`); yedek (`health_backup`, `var` altını kapsar) ve panel (`ReadOnlyPaths=var`) kendiliğinden görür. Bedel: defterle tek işlemde birleşik sorgu yok; okuyucu `decision_id` ile ayrı bağlanır (ML derlemi bunu zaten yapar). `journal_mode=DELETE` (WAL yok): salt okunur okuyucular `-shm` yazmadan açar.

## 6. Çalıştırma ve çıkış
`counterfactual_run.py --bot learner|twin --once [--since ISO] [--dry-run]`; `--ledger/--market/--out` yol geçersiz kılar. Çıktı: tek satır JSON sayaçlar (`scanned, already, computed, gap, pending, holdout_skipped, rows_written`). Çıkış: 0 başarılı (defter yoksa da — ikiz kapalı), 1 kullanım, 3 bozulmuş (market/defter/depo okunamadı) → `OnFailure`. Zamanlayıcı: her gün 23:10 UTC (= 02:10 TSI) + ≤15 dk rastgele gecikme, `Persistent=true`; `MemoryMax=128M`, ağ ve anahtar yok.

## 7. Okuma ve rapor
`counterfactual.outcomes(path, bot, now=, days=, method=)` ders için ham satırları döner (yalnız `window_end_ts ≤ now`; `side, setup, trigger_tf, planned_*` dahil; plan için `version ≥ 2`). `counterfactual.summary(path, bot, now=, days=7, method="barrier")` → `{n, mean_r_net, by_reason{skip_reason: {n, mean_r_net}}}` (karar zamanına göre pencere; salt okunur). 21:00 Telegram raporuna satır: `Alınmayan sinyaller (son 7 gün): N (varsayımsal net R, üst sınır; sonraki kapıları ve dolumları yok sayar, işlem yapılabilir kâr değildir) — neden: n, R; …` (en çok 3 neden) (öğrenen; depo yoksa "henüz hesaplanmadı"). Ders kuralları ve ML derlemi (kaynak ağırlığı `counterfactual` 0,5) bu fonksiyon/tablodan okur; bağlama (ders istemine ekleme, derleme birleşimi) ayrı iştir.

## 8. Bilinen sınırlar
- Dolum yok: giriş `planned_entry` varsayılır (gerçekte limit dolmayabilir/kayabilir); gerçek işlemlerle kıyas için optimistik.
- Üst üste binen sinyaller bağımsız sayılır (aynı çifte birden çok atlanan karar).
- `supersedes` ile değiştirilen eski karar kimliklerinin satırları kalır; okuma tarafında geçerli karar kimliğine göre süzmek gerekirse `decision_id` ile birleştirilir.
- Sonuçlar üst sınırdır: sonraki kapıları (risk, ML, giriş kapısı) ve dolumları yok sayar; işlem yapılabilir kâr değildir.
- `trigger_tf='15m'` kararları 1 saatlik ızgarada oynatılır (yaklaşık); ders kanıtından çıkarılır (satırlar `trigger_tf` ile işaretli kalır) — 15 dakikalık ızgara tekrar oynatımı yapılana dek.
- Ders kanıtında SE 3 günlük bloklara kümelenir; 72 saatlik sonuçlar blok sınırında hâlâ az örtüşür.
