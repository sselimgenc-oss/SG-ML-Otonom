# Uctan uca test sartnamesi (faz plani madde 20 + 19d)

> 25 Kasım: sahip kararıyla ders sistemi KALDIRILDI (`trader_core/lesson.py`, `lesson_run`, gece notu, onay/ret akışı, panel/Telegram ders bölümleri; öğrenme ML1'e taşındı). Bu belgedeki ders/not/onay (`/ders`, `/onayla`, `/reddet`) bölümleri tarihsel kayıttır, geçerli değildir. Defterin parametre sürümü mekanizması (kullanıcı sürümü, etkinleştirme, `parent_version_id`) ve şeması AYNEN kalır.


> 18 Kasım: kullanıcı kararıyla değişti. Uçtan uç akışta veto adımı, ikiz ve gölge kip kaldırıldı (tek düz kâğıt bot, ML/ders ilk işlemden etkin); canlı adımları **[ASKIDA — kullanıcı yeniden belirleyecek]**.

Test: `tests/e2e/test_e2e_chain.py`. Tamamen cevrimdisi: ag yok, gercek anahtar yok, LLM cagrisi yok.

## Zincir
sinyal (`price_action_v1` / `price_action_v1_ml`) -> kapi zinciri (kill, bayat veri, kurallar) -> **veto** -> **risk boyutlama**
(`trader_core.risk.check_entry`, kilitli yapilandirma) -> emir (`PaperBroker`, `Engine` `mode=paper`) -> **defter**
(`trader_core.ledger`, sema v3: karar + giris + cikis satirlari, ucret/fonlama) -> **ders** (`scripts/lesson_run.py --once`,
`rule_proxy` kipi) -> bonus: Telegram 21:00 raporunun "Defter" bolumu uretilen defterden.

## Gercek bilesenler
Motor (`Engine`, `EntryGate`, `OrderManager`, `StateStore`, `Killswitch`, `StatusWriter`, `WindowedSignalSource`), strateji ve rejim/sinyal
kodu, `trader_core.veto.lookup` (veto kararinin cozumu), risk boyutlama, `PaperBroker` (ucret/kayma/fonlama), defter, ders servisi
(istatistik + kural vekili + calisma kaydi), `trader_core.telegram` rapor bolumleri, ML paket yukleyici ve model gorunumu.

## Sahte olanlar
- **Piyasa verisi:** tmp dizinine deterministik sentetik 15m/1h/4h + fonlama feather dosyalari (2025-01..03; kilitli donem
  2026-05..2026-10 okunmaz). Sentetik borsa kurallari (`synthetic_rules`).
- **Saat:** `SimClock` (motor), ders icin `now_fn`.
- **Veto kaynagi:** `StubFileVeto`: tmp JSON "veto sonuc dosyasi" ({"PAIR:yon": allow|block + neden}); her adimda okunur, sonuc
  gercek `veto.lookup` ile cozulur. Dosya yoksa `missing` (fail-closed).
- **LLM / bildirimci:** ders `rule_proxy` kipinde (LLM yok), bildirimci `LogNotifier` (`--allow-log-notifier`).
- **ML modeli:** kucuk lojistik test paketi (`gate_passed`, hash, ozellik listesi gecerli); `active` testinde `user_approved` yok.

## Dogrulamalar
1. Her degerlendirilen aday icin tam bir karar satiri (satir sayisi = `enter` + `skip:*` sayaclari); `final_action`/`skip_reason`/
   `veto_status`/`risk_allowed` tutarli; girilenin islem satiri var, atlananin yok.
2. Girilen islemde giris satiri + ucret; kapananda cikis satiri, ucret, `funding_paid`; `realized_pnl = brut - ucretler - fonlama`;
   `r_multiple = realized_pnl / planned_risk`; kaldirac/risk kilitli yapilandirmaya uygun.
3. Kill dosyasi: yeni giris yok, adaylar `entry_gate_closed` (`gate:kill`) ile kayitli.
4. Veto `block`: aday `skipped / veto_blocked`, `veto_reason` = dosyadaki neden, boyut/risk bos, islem yok. Veto dosyasi yok -> giris yok.
5. Ders: uretilen defterde `lesson_run.py --once` cikis 0, `lesson_runs` + `lesson_run_events` kaydi yazilir, defter v3 kalir.
6. Telegram raporu: uretilen defterden "Defter" bolumu, kapanan islem sayisi defterle uyumlu.
7. Defter sema surumu 3 (`PRAGMA user_version`, `ml_score` kolonu).
8. **19d (a)** `ml_mode=off`: zincir calisir, tum `ml_score` NULL. **(b)** `shadow` + test modeli: karar/islem ozeti (id, recorded_at,
   ml_score haric) `off` ile SHA-256 olarak birebir ayni; girilen satirlarda `ml_score` dolu [0,1]; `ml_filter` atlamasi yok.
   **(c)** `active` + `user_approved` yok: yukleme reddedilir, motor yeni giris acmaz (fail-closed, `ml_filter`).
