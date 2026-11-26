# DD-12: Kâğıt bot ana planı — 44 enstrüman, bütün kurulum aileleri, ML ve ders ilk işlemden etkin

> **[19 Kasım 2026 — kullanıcı kesin kararı, bu belgedeki tüm takvimin ÜSTÜNDEDİR]** Kâğıt testin bitiş tarihi yok; canlı tarihi yok (30 Kasım, 14 Aralık testnet koşusu, 27 Aralık, aralık sonu/ocak başı gibi hedefler kalktı). "Dönem biter, devam mı dur mu" karar noktaları ve "en az N işlem / süre" şartları kaldırıldı; proje zarar etse de sürer, kullanıcı geliştirir. Gerçek paraya geçişin zamanı ve şekli yalnız kullanıcının kararıdır. Teknik ölçümler (ML kalite kapısı, ders emekliliği, risk limitleri) kalır.

Tarih: 18 Kasım 2026 (mentor). Sürüm 4 (v3'ün yerine geçer; dosya adı tarihseldir). Dayanak: kullanıcı kararları, 18 Kasım 2026 (`tasarim-kararlari.md`: "Tur 6 sonrası kullanıcı kararları", LLM bütçesi kararı) ve `research_notes/tur6-karsilastirma/D-sentez.md` (öneriler; kullanıcı eşik ve seans önerilerini reddetti, aşağıda kullanıcı kararı geçerlidir). Bu belge kod, test ve commit içermez.

v3 → v4 özeti: **LLM veto kaldırıldı**; risk %0,5 → %1, 10 → 16 pozisyon, kümeler yeniden; seans yasağı yok, seans etiketi var; ML ve ders için hiçbir asgari işlem/kanıt eşiği, haftalık değişiklik sınırı ve bekleme yok; her kapanan işlem gece notu alır, notlar ders ve ML verisidir; LLM kendi adayını önerir (aylık toplam 10 $); aylık enstrüman güncelleme işi; 1 günlük zaman dilimi dahil; faz takvimi yerine iş paketleri (WP) ve yayın noktaları; gerçek para kararlarının tamamı askıda.

## 0. Kararlar (kullanıcı) ve bu planın sınırı

- **Tek, düz kâğıt bot:** mevcut `learner` kâğıt motoru. Ayrı bot, kol ya da etiket yok. **İkiz yok, silinir.** Kâğıtta **gölge kip hiçbir yerde yok**; testnet/canlı yoluna dokunulmaz.
- **İçinde her şey:** 44 enstrüman (20 kripto + 20 ABD hissesi + XAU, XAG, BZ, COPPER), bütün kurulum aileleri (trend takip, geri çekilme, kırılım, yatay piyasa) × 15dk / 1s / 4s / **1g**, ML (aday eler, kendi adayını üretir), ders, LLM aday önerisi.
- **Risk (kâğıt):** işlem başı %1; en çok 16 eşzamanlı pozisyon; toplam açık risk %12, aynı yön %8, günlük zarar %8 (D-sentez seçenek A). Yalnız kâğıt istisnası (§4). **[20 Kasım 2026 güncellemesi, kullanıcı onaylı, yalnız kâğıt: en çok 24 pozisyon; toplam açık risk %24, aynı yön %16; işlem başı %1 ve günlük zarar %8 aynı; kol tavanı 6 (M1/L1: 4); küme tavanları 6/9/8/5/3/3. Kâğıt üst sınırları `PAPER_LIMITS` aynı değerlere çekildi; testnet/canlı sınırları değişmedi.]**
- **Seans yasağı yok** (hisse ve emtia 7/24 işlem alabilir). Her aday ve işlem seans durumu etiketi taşır (§4.2); ders ve ML bundan öğrenir.
- **ML ve ders ilk işlemden etkin.** Asgari işlem/kanıt eşiği yok (30 işlem, ≥ 300 etiketli aday, ≥ 40 aday yok), haftalık değişiklik sınırı yok, "M1'den sonra" bekleme yok (§5, §6).
- **LLM:** **veto kaldırıldı** (kullanıcı: "veto nedir, kaldır"); kâğıtta hiçbir LLM veto kapısı yoktur. Aylık LLM bütçesi **toplam 10 $** (kullanıcı kararı, 19 Kasım): işlem notu + ders ve LLM aday önerisi; öneri sayısında günlük sınır yok, yalnız bütçe payı sınırlar (§5.4, §6.5).
- **Sunucu büyütülmez;** plan 2 GB'a sığar (§8).
- **Gerçek para: bütün kararlar askıda** (kullanıcı, 18 Kasım gece: "reddediyorum, tekrar belirleyeceğim"). CANLI-K1 ölçütü, başlangıç tutarı, kasa tavanı, duman testi/canlı takvimi, risk kademe artış takvimi ve 5B adaylık ölçütü askıdadır; kullanıcı yeniden belirleyene kadar gerçek para adımı yapılmaz, canlı anahtar konmaz. Bu belgedeki hiçbir iş bunlara tarih ya da ön şart koymaz.
- **Değişmeyenler:** testnet/canlı kodu ve yolu (dokunulmaz); S2 ön kaydı; kilitli dönem (2026-05-01 → 2026-11-01); `engine.base.json`.

İş sırası ve yayın noktaları §9'dadır: "ileri tarihli" her şey şimdi başlar; tek sınır aynı anda en çok 2 iş paketi.

## 1. Enstrümanlar (44) ve aylık güncelleme

Kaynak: `data.binance.vision` USDⓈ-M arşiv dizini (18 Kasım; yalnız dizin/dosya adları listelendi, veri indirilmedi). Parantez = arşivdeki ilk ay. Piyasa değeri sıralaması mentorun bilgisine dayanır, **doğrulanmadı**.

**Kripto (20)** — stabil ve sarılı/stake kopyalar hariç; LEO Binance vadelide yok: BTC, ETH, XRP, BNB, SOL, DOGE, TRX, ADA, HYPE (2025-05), LINK, BCH, XLM, SUI, AVAX, HBAR, LTC, TON (2024-03), SHIB (`1000SHIBUSDT`), DOT, XMR. Mevcut 10 çiftin hepsi içindedir.

**ABD hisseleri (20):** NVDA (2026-03), MSFT (04), AAPL (04), GOOGL (03), AMZN (02), META (03), AVGO (04), TSLA (01), BRKB (05), JPM (05), LLY (06), WMT (05), V (05), ORCL (05), XOM (09), NFLX (06), PLTR (02), COST (06), AMD (05), HD (05). Mastercard ve J&J Binance'te listeli değil; kullanıcı kararıyla AMD ve Home Depot eklendi.

**Emtia (4):** XAU (2025-12), XAG (2026-01), BZ Brent (2026-04), COPPER (2026-03).

**Sunucuda doğrulanacak (WP-00; bu ortamdan Binance API 451 döndü):** 44 sembol `exchangeInfo`'da `TRADING` mi, hisse/emtia `contractType` (beklenen `TRADIFI_PERPETUAL`), filtreler, kapalı seansta ve hafta sonu 1 dk mum geliyor mu, **seans dışı ve hafta sonu gerçek alış-satış farkı ve hacim** (kayma varsayımı §4.3 bununla düzeltilir). `TRADING` olmayan sembol çıkarılır, kullanıcıya bildirilir.

**KALDIRILDI (sahip kararı: evren 14 çift SABİT, otomatik güncelleme yok; `trader-universe.*` birimleri install.sh ile durdurulur/silinir, `--apply` reddedilir, kaplama uygulanmaz). Aşağıdaki açıklama tarihsel kayıttır.**

**Aylık enstrüman güncelleme işi (kâğıt; WP-16):** her ayın 1'i 00:30 UTC `trader-universe.timer`.
- Kripto: kural aynıdır (stabil/sarılı hariç, Binance vadelide `TRADING` olan, en yüksek piyasa değerli 20). Kaynak: piyasa değeri listesi (dış kaynak, ana makine adı WP-16'da yazılır; ağ izni gerekirse `update_environment` ile istenir, kullanıcıya bildirilir); kaynak erişilemezse Binance 30 günlük USDT hacmi sıralaması yedeği kullanılır ve rapora yazılır.
- Hisse: yapılandırmadaki sıralı yedek listeden (`config/universe.json`, ilk 20 + 10 yedek, mentor yazar) `TRADING` olmayan/çıkarılan sembolün yerine sıradaki girer. Emtia 4 sabit; `TRADING` değilse yalnız o çift beklemeye alınır.
- Çıktı `var/universe/paper_pairs.json` (git'e girmez); `engine.paper.json` bunun üstüne `pairs` kaplamasıdır. Toplam her zaman 44'tür. Motor/feed ay başı yeniden başlar; açık pozisyonu olan çift çıkarılsa bile yönetimi (stop/hedef/çıkış) sürer, yeni giriş almaz (`optional` olarak kalır). Yeni çiftin ısınması bitene kadar o çift bekler. Her değişiklik Telegram'a "bilgi" olarak gider, onay istemez. `ml_pairs` (r03 için sabit 10) ve S2 listesi bu işten etkilenmez.

## 2. Yapı

- Tek motor (`trader-engine@learner`), tek feed, tek `var/market.sqlite`, tek defter (`var/learner/ledger.sqlite`). Mevcut açık pozisyonlar ve defter sürer.
- `config/engine.base.json` **değişmez** (10 çift, v1b). Kâğıt botun ayarı tek katmandadır: `config/engine.paper.json`. Birim: `run --bot learner --env paper`.
- Kurallar gerçek `exchangeInfo`'dan gelir (feed saatte bir yeniler). `--synthetic-rules` yalnız geri testte.
- Hisse/emtia sembolleri feed'de "isteğe bağlı": birinin kuralı ya da verisi gelmezse yalnız o çift bekler. Açılış kapısı: kripto için kural + taze veri şart; hisse/emtia için yalnız kural (bayat çift giriş yapmaz, motor çalışır).
- Isınma ≈ 50 gün (1s 1200, 15dk 4800, 4s 300 bar). En yeni sembol XOM (2026-09) sınırdadır; yetmezse yalnız o çift bekler. 1g kurulumları için gerekli 4s geçmişi ısınmanın içindedir.

## 3. Kurulumlar ve zaman dilimleri

Kimlik `arm_id` = `<kurulum>@<zaman dilimi>`. Katalog: `price-action-kural-katalogu.md`. Hepsi başlangıçtan açıktır (sıralama yalnız yazım sırasıdır, §9).

| Kurulum | Aile (katalog) | Zaman dilimleri | WP |
|---|---|---|---|
| `T1` trend içi geri çekilme | geri çekilme (PA-TRD-01/05; mevcut) | 1s (mevcut), 15dk, 4s | 05 / 11 |
| `R1` yatay piyasa kenarı | yatay piyasa (PA-YTY-02; mevcut) | 1s (mevcut), 4s | 05 / 11 |
| `TF1` yapı kırılımı yönünde devam | trend takip (PA-YAP-03, PA-FLT-01) | 4s, 1g | 12a |
| `B1` kırılım + yeniden test | kırılım (PA-KIR-01/02) | 1s, 4s | 12a |
| `F1` sahte kırılım | kırılım (PA-KIR-03) | 15dk, 1s | 12b |
| `S1` sıkışma kırılımı (iç bar / NR7) | kırılım (PA-MUM-05, PA-TRD-04) | 1s, 1g | 12b |
| `M1` ML'in kendi adayı | §5.3 | 1s; sonra 15dk, 4s | 14 |
| `L1` LLM adayı | §5.4 | 1s (öneri bir bar kapanışında girer) | 15 |

- Her yeni kurulumun kesin tanımı (giriş, stop, hedef, sabitler) kodlanmadan önce bu belgeye tarihli **Ek-K** olarak yazılır (mentor, WP-11 ile paralel; sabitler katalogdan). WP-12a/12b Ek-K olmadan başlamaz.
- `signals.py` donuktur: `T1`/`R1` onu çağırır; `T1@4h` beklemedeki `price_action_v1_4h.py` dosyasını kullanır. Yeni kurulumlar yeni dosyalardadır.
- 1 günlük bar feed'e eklenmez; 4 saatlik barlardan (6 × 4s, UTC gün) motor içinde toplanır. `market.sqlite` şeması değişmez.
- Çift başına tek pozisyon kuralı aynen. Aynı çiftte aynı anda birden çok kurulum sinyal verirse büyük zaman dilimi önceliklidir; alınmayanlar `arm_conflict` ile yazılır. **Aynı mum yasağı** bütün kurulumlara, kurulumun kendi zaman dilimiyle uygulanır (yasak kalkmadı; yalnız gölge kaydı kapalıdır, bkz. §9 WP-05).
- Her kurulumun karnesi bütün adaylarından çıkar: alınanlar gerçek kâğıt sonucuyla, alınmayanlar gece işinin "alınsaydı" sonucuyla (`counterfactual`).
- Kurulum başına en çok 4 açık pozisyon; `M1` için 3; `L1` için 3.

## 4. Risk, kümeler, seans etiketi

### 4.1 Risk (yalnız kâğıt katmanı)

İşlem başı risk **%1**. `risk.py` sabitleri (toplam açık risk, aynı yön, günlük zarar, işlem başı) yalnız `mode="paper"` yapılandırmasından ayarlanabilir; testnet/canlı/geri test yapılandırmasında bu anahtarlar `ConfigError`, verilmezse eski sabitler bit bit aynıdır. Kâğıt değerleri: toplam açık risk **%12**, aynı yön **%8**, günlük zarar **%8**. (v3'teki "`risk.py` dokunulmaz" bu parametreleştirme için tek, kapsamı dar istisnadır; tarafsızlık testi D-T13 kapsar.) **20 Kasım 2026: kâğıt değerleri toplam açık risk %24, aynı yön %16 (günlük %8 değişmedi).**

Not: %1 riskle toplam açık risk %12 tavanı, tam riskli pozisyonlarda 12. pozisyonda bağlar; 16 pozisyona ancak riski küçülmüş (kısmen kapanan, stopu girişe çekilen) pozisyonlar varken ulaşılır. Bu bilinçli kabul edilmiştir (§13).

Hesap ve küme tavanları (seans sütunu yok):

| Sınır | Kapsam | Tavan |
|---|---|---|
| hesap geneli | 44 | **16** pozisyon |
| `kripto_buyuk` | BTC, ETH, XRP, BNB, SOL | 4 |
| `kripto_diger` | kalan 15 | 6 |
| `hisse` | 20 hisse | 5 |
| `hisse_teknoloji` | NVDA, MSFT, AAPL, GOOGL, AMZN, META, AVGO, TSLA, ORCL, NFLX, PLTR, AMD | 3 |
| `metal` | XAU, XAG | 2 |
| `enerji_sanayi` | BZ, COPPER | 2 |

Bir çift birden çok kümede olabilir; hepsinde yer olmalıdır. Sayım açık ve açılmakta olan pozisyonları kapsar. Aynı gün toplu stop riski (16 pozisyonda korelasyon) bilinen sınırdır; günlük rapor ölçülen korelasyonu bilgi olarak yazar.

### 4.2 Seans etiketi (yasak değil)

Seans yüzünden giriş **engellenmez**. Her aday, karar satırı ve işlem `session_tag` taşır:

- `open`: hisse için New York 09:30–16:00 Pzt–Cum (yaz/kış saatine göre); metal ve enerji/sanayi için Paz 23:00 → Cum 21:00 UTC (günlük kısa mola dahil kabul).
- `closed`: hafta içi seans dışı.
- `weekend`: hafta sonu (hisse: Cts–Paz; emtia: Cum 21:00 → Paz 23:00 UTC).
- Kripto: `open` (7/24).

Korumalar aynen: son kapanmış tetik barı `volume == 0` ya da `high == low` ise giriş yok (tatil/ölü mum; skip_reason `flat_bar`). Açık pozisyonun stop/hedef yönetimi her zaman sürer; hafta sonuna taşınan pozisyon kapatılmaz. Kâğıt brokerde fiyat sıçramalı mumda stop, stop fiyatından değil sıçrama sonrası fiyattan dolar (test D-T31).

`session_tag` ders ve ML'e açık girdidir: ders servisi varlık sınıfı × seans durumu başına ortalama R'yi görür; ders, `session_off` ayarıyla (varlık sınıfı başına `open/closed/weekend` kapatma) bir seans durumunu kendisi kapatabilir (varsayılan: hepsi açık). `skip_reason = session_closed` **yalnız** dersin kapattığı seans için kullanılır. ML süzgeci ve `M1` özellik olarak `session_tag` ve seans başlangıcından geçen süreyi alır.

### 4.3 Kayma

Kripto kayması tabanda aynen. Hisse/emtia kayması seansa göre (**tahmin**, WP-00 ölçümüyle düzeltilir): seans içi tabanın 2 katı (giriş 4, çıkış 4, stop 10 bp), `closed` 3 katı (6 / 6 / 15 bp), `weekend` 4 katı (8 / 8 / 20 bp). Seans dışı kâğıt dolumları buna rağmen iyimser sayılır (§13). `cost_overrides` bu üç katsayıyı çift ve seans başına tutar; "alınsaydı" hesabı aynı tablodan dolum maliyeti kullanır.

### 4.4 Veto: kaldırıldı

Kullanıcı kararıyla LLM veto bütün kâğıt botta kaldırılır (kripto dahil): motor kapısında veto adımı yoktur (`gates.py` sırası §9 WP-04'tür, veto adımı çıkarılır), `trader-veto.service`/`.timer` durdurulur ve devre dışı bırakılır, `config/veto.json`, `veto_exempt_pairs`, `veto_path` bağımlılığı, `shared/veto/` okuması ve "veto yok/eski → işlem yok" davranışı kâğıt yolundan çıkarılır. Eski veto kararı satırları defterde okunur kalır (`veto_status` sütunu şema CHECK'i için aynı kalır; yeni satırlar `veto_status='not_evaluated'` yazar). Veto bütçe payı not + ders ile `L1` adaylarına gider (§6.5). Testnet/canlı yoluna dokunulmaz; orada veto kodu bugünkü gibi kalır (gerçek para kararları askıda; bu belge o yol için karar vermez). Bu işi WP-06a yapar. Ders etkisinin "veto etkisi" satırı artık yoktur.

## 5. ML — ilk işlemden etkin

Kapı şartı kâğıtta aranmaz; asgari örnek, eşik, "M1 sonrası" bekleme yoktur. Model puanı boyutu değiştirmez; risk kilidi son sözü söyler. Testnet/canlıya kapıdan geçmemiş model yüklenemez (mevcut kural, aynen).

Eşiksiz çalışmanın tek teknik şartı: model yoksa ya da eğitim kümesi tek sınıftan oluşuyorsa (eğitim matematiksel olarak yapılamaz) puan üretilmez ve aday geçer (`ml_no_model`); bu bir istatistik eşiği değildir, ilk iki karşıt sınıflı kayıtla model oluşur. Küçük örnekte sönümleme (§6.3) kullanılır.

### 5.1 Süzgeç 1: r03 (mevcut)
r03 taban 10 çiftle eğitildi ve 200 günlük geçmiş ister; bağlamı o 10 çiftle sabit (`ml_pairs`), puanları bugünküyle aynı. Bu 10 çiftin eşik altı adayları **elenir**; diğer 34'ün adayları elenmeden geçer (`out_of_universe`). r03 kapıda başarısızdı (AUC 0,50); etkisi ML etkisi ölçümüyle (§6.5) görülür.

### 5.2 Süzgeç 2: kurulum bazlı süzgeçler (WP-10, en erken yayında)
- Her `arm_id` için ayrı küçük model (LightGBM derinlik 2–3 ya da sönümlü lojistik), 44 enstrümanı kapsar; hedef: adayın "alınsaydı/gerçek" net R'si > 0.
  **Güncel durum (23.11): canlı gece süzgeci LightGBM değil, ridge lojistiktir** (`paket/ortak_ogrenme/filtre.py`, kurulum ailesi başına paket); etiket gerçekleşen işlemin R > 0 olması, gradient boosting ve üçlü bariyer etiketi yalnız araştırma tarafında (`src/trader_ml`).
- Eğitim verisi (tasarım): kâğıtta biriken **bütün adaylar ve sonuçları** (alınan + alınmayan, `counterfactual` sonucu dahil), ilk kayıttan itibaren. **Güncel durum: canlı gece yolu yalnız alınan (kapanan) işlemlerden öğrenir** (`src/trader_engine/ogrenme_filtre.py`); alınmayanlardan öğrenme henüz yok.
- Özellikler karar anında bilinenlerdir: kurulum özellikleri, rejim, `session_tag`, varlık sınıfı, **o adaya uyan yaşayan ders kimlikleri** (§6.2). İşlem sonrası notun sonuç etiketleri özellik değildir (ileriye bakma); yalnız eğitim hedefi ve ders ölçümü içindir.
- **Yeniden eğitim: her gece 00:40 UTC (03:40 TSI; 24.11'de 03:40 UTC'den alındı), sunucuda**, tek oneshot birim (`trader-ml-retrain.service`, `MemoryHigh=250M`, `MemoryMax=300M`, `CPUQuota=50%`, `Nice=10`, yalnız numpy (tasarımda numpy + lightgbm; canlı süzgeçte lightgbm yok), pandas yok, tavan 50 bin satır, hedef < 3 dk), DL1 eğitimi (GitHub Actions, 01:00 UTC) arkasından başlar; ders (02:40) ve not (02:55) işleri sonradan çalışır, eğitim onların çıktısını kullanmaz. Bellek ölçümü D-T20/D-T14'te tutmazsa sunucu dışına alınır (karar kullanıcıya sorulmaz; bu belgeye ek yazılır, çıktı aynı paket yoluyla gelir). Paket sha256 ile `models/` altına yazılır, motor bar kapanışında sıcak yükler (yeniden başlatma yok).
- Hiçbir değişiklik sınırı yok: her gece yeni model hemen devreye girer; önceki paket bir sürüm yedek tutulur.

### 5.3 `M1`: ML'in kendi adayı (WP-14, en erken yayında)
- Girdi: son 64 barın ATR'ye ölçekli mum dizisi + yapı özellikleri (son salınıma uzaklık, aralık içi konum, eğimler, sıkışma ölçüsü, üst zaman dilimi yönü) + `session_tag`. Enstrüman kimliği özelliği yok.
- Etiket: üçlü bariyer (stop 1,5 ATR, hedef 3 ATR, süre 48 bar), uzun/kısa ayrı. Model: LightGBM, üç sınıf; eşik eğitim dışı dilimde en yüksek puanlı ≈ %2'yi seçecek biçimde.
- Eğitim sunucu dışında. Başlangıç verisi: 20 kripto 2021-01 → 2026-04-30; **kilitli dönem eğitime ve değerlendirmeye girmez**. Kilit sonrası (2026-11-01 →) gelen **kâğıt kayıtları** (alınan + alınmayan aday sonuçları, 44 enstrüman, ders etiketleri) eğitime her dönüşte eklenir; böylece hisse/emtia da öğrenilir.
- **Yeniden eğitim sıklığı: her gün 04:30 UTC'de bir sunucu dışı çalıştırma hedeftir; operatör imkânı yoksa en az haftada bir (Pazar).** Çıktı paket + sha256 + `paper_models.csv` satırı; sunucuya `scp` ile konur, motor bar kapanışında yükler. Paket yoksa/eskiyse `M1` aday üretmez, motor durmaz (süre sınırı yok sayılmaz: sağlık alarmı paketi 8 günden eskiyse uyarır).
- `M1@1h` ile başlar, küme/risk/ML-süzgeci kapılarının hepsinden geçer; ilk pakete kadar yalnız kod yolu hazırdır, ilk paketle ilk işlemde etkindir. 15dk/4s `M1` aynı pakette ek çıktı olarak gelir.
- **20 Kasım 2026 (kâğıt): `M1@15m` ve `M1@1d` de `engine.paper.json`'da açık** (4 zaman diliminin hepsi; yalnız kâğıt, taban/canlı/testnet değişmez). Her zaman dilimi kendi paketini gece eğitiminden (00:40 UTC, `ml_retrain_run.py`, `--m1-tfs` varsayılanı `1h,4h,15m,1d`) alır; kilit dönemi aynen dışarıda. Paket yoksa arm aday üretmez, diğer kolları ve motoru etkilemez; ilk geçerli paket oluşunca kendiliğinden işlem açmaya başlar. Eşik uydurulmadı: mevcut kural (≥ 2 örnek ve iki sınıf) geçerlidir; paket oluşmazsa gece çıktısı ve `paper_models.csv` satırı nedeni yazar ("model yok: N örnek, en az 2").
- Kod yeni pakettedir (`src/trader_ml/pa_proposer/`); dondurulmuş dosyalara dokunulmaz.

### 5.4 `L1`: LLM adayı (WP-15)
- Günlük aday sayısı sınırı yok; yalnız aylık bütçe payı sınırlar (§6.5). Çalışma toplu çağrıdır (bar kapanışı sonrası, günde birkaç tur; tur sıklığı `llm_proposer.json` `run_every_min`, varsayılan 60), model Sonnet, kâğıt botun `arm_id` karnesiyle `L1@1h`; girdi: 44 enstrüman özet bağlamı, açık pozisyonlar, yaşayan dersler. Çıktı: yapılandırılmış öneri (çift, yön, giriş bar kapanışında piyasa, stop, hedef). Giriş, stop, hedef kuralları motor tarafında doğrulanır (stop mesafesi sınırı, ATR çarpanı); geçersiz öneri `llm_invalid` ile atılır. Günlük sınır olmadığı için pay birkaç günde tükenebilir (§13); sınır yalnız aylık paydır.
- Öneri bütün kapılardan (küme, risk, ML süzgeci, aynı mum) geçer; veto yoktur.
- Yapılandırma anahtarı: `config/llm_proposer.json` içinde `enabled: true` (kullanıcı kararı), `budget_share_usd_month` (§6.5). Anahtar kapatılınca kol hiçbir çağrı yapmaz.

### 5.5 Kayıt
Kâğıtta çalışan her model `research/paper_models.csv`'ye yazılır (ad, tarif, veri penceresi, commit, sha256, tarih); gece süzgeç paketleri ayrı satır sınıfı `nightly` ile toplu tek satır/gün yazılır. (Gerçek para kararları askıda olduğundan bu kayıt yalnız ileride kullanılmak üzere tutulur; deneme sayısı muhasebesi askıdır.)

## 6. Ders — ilk işlemden etkin, ikizsiz, eşiksiz

İkiz yok; "iyileşti mi" botun kendi kayıtlarından yanıtlanır: defter her adayı özellikleriyle yazar, gece işi alınmayanların "alınsaydı" sonucunu hesaplar.

### 6.1 Ders etkisi ve geri alma
- **Referans sürüm:** kullanıcının son onayladığı (başlangıçta bugünkü) ayar sürümü.
- **Ders etkisi (R):** aynı dönemde bugünkü ayarlarla referansın **farklı karar verdiği** adaylar: `etki = Σ R(bugünkü ayarın aldığı, referansın almayacağı; gerçek sonuç) − Σ R(referansın alacağı, bugünkü ayarın elediği; "alınsaydı")`. Tavan ve sıra etkileşimleri hesaba girmez (yaklaşık).
- **Tek değişikliğin geri alınması:** o değişiklikten sonra farklı karar verilen adaylarda sönümlü etki (§6.3) ≤ −3 R ise geri alınır. Asgari aday sayısı yok; her gece ölçülür.
- **10 R freni:** referanstan beri toplam ders etkisi ≤ −10 R ise referans sürüme dönülür, otomatik uygulama durur, Telegram'a haber gider.
- Referans sürümden en çok 2 adım (ayar sınırlarıyla). Tek ayar/tek adım ve ayar sınırları kalır; **haftalık değişiklik sınırı kaldırıldı**, bir gecede birden çok ayar değişebilir (her biri kendi etkisiyle ölçülür).
- Otomatik uygulama ilk günden açık: sıkılaştırma, gevşetme ve "alınsaydı" kanıtlı öneriler onaysız uygulanır, Telegram'a bilgi gider (ders-spec'teki "alınsaydı kanıtı her zaman kullanıcıya sorulur" kuralı kâğıt için kaldırılır, gerçek para için askıda kalır). Eşik kalibrasyonu (`lesson_calibrate.py`) bilgi içindir, ön şart değildir. `min_affected`, `min_distinct_days`, `min_z`, `min_gap_r`, `checkpoints` gibi kanıt eşikleri kâğıtta kapatılır (§15).

### 6.2 İşlem notları ve ders yaşam döngüsü (2A; WP-09)
- **Her kapanan işlem** gece notu alır (eşik yok): 02:55 UTC toplu çağrı (Haiku, toplu mod), sabit etiket sözlüğüyle (giriş kalitesi, stop yeri, seans, rejim, haber/olay, kurulum uyumu, kaçınılabilir mi, ders önerisi) kısa metin + etiket listesi. Not defterde `trade_notes` tablosunda tutulur.
- Notun ders önerisi **ertesi gün "aday ders"** olarak kullanılır: `L1` istemine (en çok 8 ders) ve ders servisine girer; eşleşen adaylara kimliğiyle işaretlenir (`lesson_ids`).
- **Emeklilik:** her gece aday/yaşayan dersin etkisi §6.1 yöntemiyle ölçülür (dersin etkilediği adaylarda sönümlü etki). Etki > 0 ise yaşar; ≤ 0 ise emekli olur (kayıt kalır, istemden çıkar). "İşe yaramadı" için bekleme süresi yoktur.
- **Dersler ML'in eğitim verisidir:** dersin kimliği, uyduğu adayların `lesson_ids` sütunu ve sonuç etiketleri nightly süzgeç ve `M1` tablosuna girer (§5.2, §5.3); işlem sonrası etiketler hedef/ölçüm tarafındadır, özellik değildir.
- Notlar olay sonrası yorumdur; LLM yanlış öğretebilir. Koruma: ders yaşamı ölçülen etkiye bağlıdır, metne değil.

### 6.3 Küçük örnek (eşiksiz çalışmanın tek ayarı)
Asgari örnek istenmez ama tek işlemin kararı sürüklemesi istenmez. Bu yüzden her ortalama/etki **sönümlüdür**: `ortalama = Σ R / (n + 10)` (10 sahte aday, 0 R). n büyüdükçe etki kaybolur; n = 1'de bir −1 R kayıp −0,09 sayılır. Sönüm sabiti 10 mentor tercihidir ve yapılandırmadandır (`shrink_n`; 0 yapılırsa tam eşiksiz, sönümsüz); kullanıcı isterse 0 yapılır.

### 6.4 Kurulum dersi ve ML etkisi
- **Kurulum aç/kapa:** son en çok 40 aday (alınan + "alınsaydı") üzerinde sönümlü ortalama ≤ −0,15 R ise kurulum kapanır (aday ve sonuç kaydı sürer); aynı pencerede ≥ +0,05 R ise yeniden açılır. Asgari aday yok.
- **ML etkisi:** `−Σ R(ML'nin elediği adaylar; "alınsaydı")` ve `M1`/`L1` işlemlerinin gerçek R toplamı; ayrıca nightly süzgeç için kurulum bazında.

### 6.5 LLM bütçesi (kullanıcı kararı 19 Kasım: aylık toplam 10 $)
Bütün LLM harcaması (işlem notu, ders, LLM adayı) tek `monthly_cap_usd = 10` altındadır (veto yok). 19 Kasım: tavan 10 $ kalır (30 $ önerisi geri alındı); aşağıdaki pay tablosu 30 $ varsayımıyla yazılmış tarihsel öneridir, uygulanan paylar `config/budget.json`'dadır:

| Pay | Aylık | Günlük tavan | Not |
|---|---|---|---|
| not + ders (Haiku batch + Sonnet) | 8 $ | 0,30 $ | her kapanan işlem notu |
| not + ders (Haiku batch + Sonnet) | 6 $ | 0,20 $ | |
| `L1` LLM adayı (Sonnet batch) | 19 $ | yok (aday sayısı sınırı yok) | yalnız aylık pay sınırlar |
| yedek | 3 $ | — | kimse payına yazmaz; payı biten kalemi yalnız yönetici (`budget.py`) yedekten karşılayabilir, loglanır |
| **Toplam (tarihsel öneri)** | **30 $** | | `monthly_warn_usd` 15 $, uyarı oranı %70 aynen |

Kural: `L1` payı biterse yalnız `L1` o ay durur (not ve ders payı devredilmez, `L1` onlardan çekmez). Pay toplamı `monthly_cap_usd`'u geçemez (`budget.py` yüklemede denetler; yoksa hata). Yedek yalnız `budget.py` tarafından, loglanarak kullanılır. Ön ödemeli kredi 10 $ kalır; artırmak kullanıcı adımıdır (kredi yükleme; otomatik yükleme kapalı). `L1` için üçüncü anahtar eklenir (`ANTHROPIC_API_KEY_PROPOSER`). Eski veto anahtarı ve `veto` payı/günlük tavanı kaldırılır.

## 7. Telegram ve pano

Sade başlıklar: "Kâğıt bot". Özel etiket yok.

- Günlük rapor: net R (bugün/toplam), açık pozisyonlar (küme adıyla), **ders etkisi**, **ML etkisi**, `L1` karnesi, seans kırılımı (`open/closed/weekend` × varlık sınıfı ortalama R), ölçülen korelasyon bilgisi, atlama sayıları (tatil barı, küme tavanı, hesap tavanı, kurulum çakışması, ML elemesi, `session_closed` yalnız dersin kapattığı).
- Kurulum karnesi (haftalık rapor ve `/kurulumlar`): kurulum başına aday, alınan, ortalama R (alınan), ortalama R (alınan + alınsaydı), varlık sınıfı kırılımı, açık/kapalı.
- Ders: her otomatik uygulama, geri alma, aday ders doğumu/emekliliği bildirimi (günlük özet; mesaj sayısı tek mesaja toplanır).
- LLM harcama satırı (pay başına bu ay / tavan).
- İkizle ilgili her satır, komut ve alan kaldırılır. `config/panel.json`: `max_concurrent` 8 → 16.
- Sağlık: hisse/emtiada kapalı seans bayatlığı alarm üretmez; beklenen bot listesi yalnız `learner`; paket tazeliği alarmı (`M1`, nightly).

## 8. Kapasite — 2 GB'da kalınır

Bellek ve işlemci sayıları **tahmindir**; dağıtımda ölçülür.

- **REST ağırlığı** (sınır 2400/dk, istemci eşiği 1800): sürekli 88/dk; saat başı tepe ≈ 270/dk; ilk geri doldurma ≈ 4100 (istemci kısar, 3–4 dk). Aylık güncelleme işi (§1) ek ağırlık getirmez.
- **Disk:** 1 dk barlar (14 gün) ≈ 200 MB; uzun barlar ≈ 180 MB/yıl; defter (notlar ve `lesson_ids` dahil) yılda < 1,5 GB. Sorun değil.
- **Bellek (tahmini RSS, MB):**

| Birim | Bugün | Yayın-1 | Yayın-3 sonrası |
|---|---|---|---|
| feed (44) | 55 | 85 | 85 |
| öğrenen | 200 | 320 | 450–520 |
| ikiz | 160 | **0 (kaldırıldı)** | 0 |
| testnet (14 Aralık; testnet planı bu belgeden bağımsız) | — | — | 180 |
| pano + telegram | 110 | 110 | 120 |
| işletim sistemi | 230 | 230 | 230 |
| geçici işler (pano yayını, ders, not, `L1`, gece ML eğitimi; seri çalışır, en büyük tek iş 300 MB) | 300 | 300 | 400 |
| **En kötü an** | 1055 | **1045** | **1465–1535 / 1960** |

`trader.slice` aynen (1100M / 1300M). Birim tavanları: öğrenen `MemoryHigh=600M`, `MemoryMax=750M`; feed 200M/260M; testnet 250M/320M; `trader-ml-retrain` 250M/300M (yalnız gece, öğrenenin yoğun saat başı adımıyla çakışmaz: 00:40 UTC, kâğıt kararı 15 dakikalık adımlarda en çok 120 sn sürer). Fiili tepe: feed 85 + öğrenen 520 + testnet 180 + eğitim işi 250 = 1035 ≤ 1100; yumuşak tavan toplamı 200 + 600 + 250 + 250 = 1300 = slice sert tavanı (test D-T14).

- **Boyutlama kuralları (öğrenen ≤ 550 MB hedefi):** çift × zaman dilimi başına yalnız son pencere (15dk 5000, 1s 1500, 4s 1500 bar); gösterge tabloları adımlar arası saklanmaz; 1g bar anında türetilir; ML özellik tamponu son 64 bar; aynı türden tek model bellekte (nightly süzgeç paketleri: kurulum başına küçük ağaç, toplam < 20 MB; `M1` paketi tek). 16 pozisyon ve not/ders tabloları bellek etkisi ihmal edilebilir.
- **İşlemci:** yalnız kapanan zaman diliminin kurulumları hesaplanır (15dk adımda 2 kurulum, saat başı 8, 4 saatte 12, gün başı 14). Hedef: karar adımı < 120 sn; `CPUQuota=90%`.
- **Sığmazsa (sessizce kısılmaz, kullanıcıya sorulur):** öğrenen > 550 MB ya da saat başı adımı > 120 sn ise en küçük kısıntı: **15 dakikalık kurulumlar (`T1@15m`, `F1@15m`) yalnız 20 kriptoda çalışır** (≈ 100 MB kazanç). İkinci basamak: 14 Aralık testnet başlarken pano yayınını 5 → 15 dakikaya seyreltmek.
- **İzlenecek:** `systemctl show trader-engine@learner trader-feed trader-ml-retrain -p MemoryCurrent -p MemoryPeak`; `free -m`; `journalctl -k | grep -i oom`; karar adımı süresi (`status.json`); feed `used_weight`; gece zinciri (00:40 eğitim → 02:40 ders → 02:55 not) toplam süresi.

## 9. İş paketleri (WP), sıra ve yayın noktaları

Kural: her WP bir uygulayıcı + bağımsız bir test yazarı içindir; test yazarı uygulayıcının testlerini değil §12'deki davranışları yazar. Her WP'nin dosya listesi başka WP ile **kesişmez** (aynı anda koşanlar için); **aynı anda en çok 2 WP**. Her WP birleşmeden önce mentor incelemesi; altın ve S2 tarafsızlık testleri değişmeden geçer. Bir WP'nin tek dosyaya sahipliği o dosyanın sonraki WP'lere devrini bekler (sıra aşağıda).

**Dokunulmaz:** `s2-on-kayit.md` §1.8 listesi (`scripts/build_corpus_v2.py`, `research/ml_build_candidates.py`, `trader_ml/{features,features_v2,labels,guards,config}.py`, `trader_core/{ml_features,ml_features_v2,signals,regime,indicators}.py`, `trader_engine/holdout.py`); `engine.base.json`, `engine.learner.json`, `engine.testnet.json`, `engine.live.json`; `brokers/*` (yalnız WP-05'in test eklediği kâğıt broker davranışı hariç: D-T31 mevcut davranışı doğrular, değiştirmez; farklıysa mentor kararı), `order_manager.py`; `research/s2_run.py`; testnet/canlı birimleri. `risk.py`: yalnız §4.1 parametreleştirmesi (WP-01). freqtrade/ccxt/python-binance yok. Yeni anahtarlar verilmediğinde (taban, testnet, canlı, geri test) davranış bit bit aynıdır.

| WP | Ad | Dosyalar | Bağımlı | Testler |
|---|---|---|---|---|
| **00** | Sunucu yoklaması (operatör, kod yok) | — (çıktı bu belgeye tarihli ek) | — | — |
| **01** | Kâğıt yapılandırması + risk parametreleri | `config/engine.paper.json` (yeni; `pairs` 44, `optional_pairs` 24 (hisse/emtia; veto muafı kavramı kalktı), `strategy`, `ml_mode:"active"`, `ml_pairs`, `ml_features:"r03"`, `ml_model_path`, `ml_experimental:true`, `shadow_blocks:[]`, `max_positions:16`, `risk` (§4.1), `clusters` (§4.1, seanssız), `flat_bar_guard`, `contract_types`, `cost_overrides`), `config/engine.paper-ml.json` ve `engine.twin.json` silinir, `src/trader_engine/config.py`, `src/trader_engine/cli.py` (`--env paper`; `--bot twin` kalkar), `src/trader_core/risk.py` (yalnız parametre okuma) | — | D-T1, D-T2, D-T13, D-T30 |
| **02** | Defter şeması v5 | `src/trader_core/ledger.py` (**tek sahip**): tablo yeniden kurma 4 → 5 (`_FK_OFF_MIGRATIONS`'a 4; göç öncesi yedek mevcut); `trigger_tf IN ('15m','1h','4h','1d')`; `setup` uzunluk denetimi (`length(setup) BETWEEN 2 AND 8`); sütunlar `arm_id` (eski satır `setup||'@'||trigger_tf`), `session_tag`, `lesson_ids` (JSON), `source` (`arm`/`m1`/`l1`); `trade_entries.arm_id`, `session_tag`; yeni tablo `trade_notes(trade_id, note_date, tags, text, model, cost_usd)`; `skip_reason` listesine `arm_conflict`, `arm_disabled`, `session_closed`, `flat_bar`, `cluster_cap`, `max_positions`, `ml_no_model`, `llm_invalid`; `_require_learner` ve ikiz dalları sadeleşir, `bot` CHECK'i eski satırlar için kalır | — | D-T15 |
| **03** | Evren ve feed | `src/trader_engine/exchange/rules.py` (`extract_rules(..., contract_types=("PERPETUAL",))`), `src/trader_engine/marketdata/feed.py` (`--env`; isteğe bağlı çift hatası ölümcül değil; pandas yok) | 01 | D-T3, D-T4 |
| **04** | Kapılar | `src/trader_engine/arm_guard.py` (yeni, saf: küme üyeliği, tavan sayımı, `session_tag` hesabı, tatil barı), `src/trader_engine/gates.py` (sıra: kural → tatil barı → ders-kapalı seans → küme tavanı → hesap tavanı; veto adımı yok; red satırı `skip_reason` değerleriyle) | 01, 02 | D-T6, D-T7 |
| **05** | Motor entegrasyonu (Yayın-1 çekirdeği) | `src/trader_engine/engine.py` (açılış kapısı §2, `ml_pairs` bağlamı, seansa göre kayma §4.3, `session_tag` yazımı, `status.json` küme sayıları, ikiz başlatma gecikmesi kalkar), `src/trader_engine/strategies/price_action_v1_ml.py`, `strategies/registry.py` (`price_action_v1_full_ml`: T1 + R1 sarar; evren dışı aday puanlanmaz ve elenmez; `ml_no_model` geçişi), kâğıt broker sıçrama davranışı testi | 01, 02, 03, 04 | D-T5, D-T8, D-T12, D-T29, D-T31 |
| **06a** | Veto kaldırma | `src/trader_engine/gates.py` ve `engine.py` içinde kalan veto bağlantısı (WP-04/05'ten devralır; yalnız kâğıt yolu), `config/veto.json` silinir, `src/trader_core/veto.py` kâğıt yolundan ayrılır (dosya testnet/canlı için kalır), `scripts/veto_run.py`, `deploy/trader-veto.{service,timer}` + `trader-veto*.env.example` (kâğıt kurulumundan çıkar; `install.sh` kaldırma adımı: durdur, devre dışı), `src/trader_core/{telegram,health,panel_data}.py` ve `src/trader_panel/*` içindeki veto satırları/alanları (kâğıt için), `scripts/{health_run,report_run}.py` veto bayatlık denetimi, `config/panel.json` veto alanı; sağlık `require` listesinden veto çıkar | 04, 05, 07 | D-T9 |
| **06b** | LLM bütçe yeniden paylaşımı | `src/trader_core/budget.py` (üç pay + yedek: not+ders 8, `L1` 19, yedek 3; toplam ≤ aylık tavan; `L1` anahtarı; `veto` payı kaldırılır), `config/budget.json` (§15) | 01 | D-T27 (bütçe kısmı) |
| **07** | İkiz kaldırma | `src/trader_core/{telegram,health,panel_data,live_paths}.py`, `src/trader_panel/*`, `scripts/{telegram_run,health_run,report_run,drift_run,counterfactual_run,health_backup,engine_retry}.py`, `config/panel.json`, `deploy/` (`trader-engine@.service` `--env paper` ve tavanlar §8; `trader-engine@learner.service.d/ml-shadow.conf` silinir; `trader-feed.service` `--env paper` 200M/260M; `install.sh`/`uninstall.sh`: ikiz birimleri durdurur/devre dışı, `--with-twin`/`--no-twin` kalkar, `HEALTH_BOTS=learner`, `var/twin/` silinmez, `var/arsiv/twin-<tarih>/`'e taşınır); `tests/` ikizli testler bağımsız yazarca güncellenir | 01 | D-T11, D-T23 (ikiz kısmı) |
| **08** | Ders ikizsiz ve eşiksiz | `src/trader_core/lesson.py`, `scripts/lesson_run.py`, `scripts/lesson_calibrate.py`, `scripts/lesson_stats_check.py`; `LESSON_PARAMS` genişletmesi (`session_off`, stop sonrası bekleme mumu 0–3; `ledger.py` dosyasına WP-02 bitince küçük ek WP-08 sahipliğinde yapılır) | 02, 07 | D-T10, D-T26 (ders kısmı) |
| **09** | İşlem notu ve ders yaşam döngüsü | `src/trader_core/trade_notes.py` (yeni), `scripts/notes_run.py` (yeni), `deploy/trader-notes.{service,timer}` (yeni), `lesson.py` yaşam döngüsü kancası (WP-08 bitince); aday dersler `L1` istemine WP-15 üzerinden girer | 02, 06b, 08 | D-T25 |
| **10** | Kurulum bazlı ML süzgeci + gece eğitimi | `src/trader_ml/setup_filter/{features,train,package}.py` (yeni), `scripts/ml_retrain_run.py` (yeni), `deploy/trader-ml-retrain.{service,timer}` (yeni), `src/trader_core/ml_package.py`, `src/trader_core/ml_live_v2.py` (çok paket, sıcak yükleme) | 02, 05, 09 | D-T26 |
| **11** | Çok kurulumlu strateji altyapısı | `src/trader_engine/strategies/lab.py` (yeni; `price_action_lab_ml`), `strategies/arms/{__init__,t1,r1}.py` (yeni; `__init__` kurulumları adla bulur, başka WP kayıt dosyasına dokunmaz), `src/trader_engine/strategy_runner.py`, `src/trader_engine/bars.py` (çok zaman dilimi, 1g = 6 × 4s), `engine.py` (15 dk karar adımı, kurulum başına tavan, `arm_id`; **WP-05'ten devralır**), `config/engine.paper.json` (`strategy`, `arms`, `arm_max_positions`; WP-01'den devralır) | 05 | D-T16, D-T18 |
| **12a** | Kurulumlar TF1, B1 | `strategies/arms/{tf1,b1}.py` (yeni, saf) | 11, Ek-K | D-T17 |
| **12b** | Kurulumlar F1, S1 | `strategies/arms/{f1,s1}.py` (yeni, saf) | 11, Ek-K | D-T17 |
| **13** | Alınsaydı ve kurulum karnesi | `src/trader_core/counterfactual.py`, `scripts/counterfactual_run.py` (yeni zaman dilimleri, `arm_id`, seansa göre kayma), `src/trader_core/lesson.py` (kurulum aç/kapa, `arm_id` kanıtı; WP-08'den devralır) | 11, 12a, 12b | D-T19, D-T22 (kurulum dersi) |
| **14** | `M1` kendi adayı | `src/trader_ml/pa_proposer/{features,labels,train,package}.py` (yeni; kilitli dönemi yapısal reddeder), `research/pa_proposer_build.py`, `research/paper_models.csv` (yeni), `strategies/arms/m1.py` (yeni), `scripts/health_run.py` (paket tazeliği alarmı; WP-07'den devralır), kâğıt kayıtlarını dışa aktaran `scripts/export_paper_records.py` (yeni) | 11 | D-T21, D-T22 (`M1` kısmı) |
| **15** | `L1` LLM adayı | `src/trader_core/llm_proposer.py` (yeni), `strategies/arms/l1.py` (yeni), `scripts/proposer_run.py` (yeni), `deploy/trader-proposer.{service,timer}` (yeni), `config/llm_proposer.json` (yeni) | 06, 09, 11 | D-T27 |
| **16** | Aylık enstrüman güncelleme | `src/trader_core/universe.py` (yeni, saf), `scripts/universe_run.py` (yeni), `deploy/trader-universe.{service,timer}` (yeni), `config/universe.json` (yeni), `src/trader_engine/config.py` (`var/universe/paper_pairs.json` kaplaması; WP-01'den devralır) | 03, 05 | D-T28 |
| **17** | Rapor, Telegram, pano | `src/trader_core/{telegram,panel_data}.py`, `src/trader_panel/*`, `scripts/{report_run,telegram_run}.py` (§7: ders/ML etkisi, seans kırılımı, kurulum karnesi, LLM harcama; WP-07'den devralır) | 06a, 07, 09, 10, 13, 15 | D-T23 |
| **18** | Kapasite ve kapanış | `deploy/install.sh` (yeni birimlerin kurulumu), bellek ve adım süresi ölçümü, `tests/` bütçe testleri | hepsi | D-T14, D-T20, D-T24 |

### Sıra (aynı anda en çok 2)

1. **WP-01 ‖ WP-02** (WP-00 operatör olarak paralel koşar, uygulayıcı sayılmaz)
2. **WP-03 ‖ WP-04**
3. **WP-05 ‖ WP-07**
4. **WP-06a ‖ WP-06b** (veto kaldırma ‖ bütçe)
5. **WP-08 ‖ WP-11** (Ek-K mentor, bu adımda yazılır) → **YAYIN-1**
6. **WP-09 ‖ WP-14**
7. **WP-10 ‖ WP-12a** → **YAYIN-2**
8. **WP-12b ‖ WP-15**
9. **WP-13 ‖ WP-16** → **YAYIN-3**
10. **WP-17**
11. **WP-18** → **YAYIN-4**

Hedef tarihler (tahmin, kayarsa kullanıcıya bildirilir; sıra korunur): Yayın-1 ≤ 22 Kasım, Yayın-2 ≤ 28 Kasım, Yayın-3 ≤ 5 Aralık, Yayın-4 ≤ 12 Aralık. Takvim yüzünden hiçbir şey kesilmez, yalnız sırası kayar.

### Yayınlar
- **Yayın-1** (WP-01…08, 06a/b, 11): 44 enstrüman, `T1@1h` + `R1@1h`, risk %1/16, kümeler, seans etiketi, r03 etkin, ikiz yok, **veto yok**, ders eşiksiz ve ikizsiz, çok kurulumlu altyapı, defter v5 (arm/session/not tabloları hazır). Defter ilk açılışta 4 → 5 göçer; `trader-veto` birimleri durur.
- **Yayın-2** (WP-09, 10, 14, 12a): işlem notları, nightly süzgeç, `M1@1h` ilk paketle, `TF1`, `B1`.
- **Yayın-3** (WP-12b, 13, 15, 16): `F1`, `S1`, kurulum karnesi ve dersi, `L1`, aylık güncelleme.
- **Yayın-4** (WP-17, 18): tam rapor/pano, ölçüm.

### Yayın usulü (her yayın)
**WP-00:** sunucuda `exchangeInfo` ve 1m `klines`/`markPriceKlines` yoklaması 44 sembol için, bir kez de hafta sonu saatinde; seans dışı alış-satış farkı; bellek ön ölçümü. Yayın-1 öncesi.
1. WP'ler birleşir (mentor incelemesi; altın ve S2 testleri değişmeden).
2. Yayın-1'de: ikiz durdurulur, birimleri devre dışı, `var/twin/` arşive taşınır.
3. `install.sh`; `rules-snapshot --env paper` → 44/44 (eksik bildirilir).
4. `systemctl restart trader-feed`; geri doldurma biter.
5. Motor durur → defter yedeği → kod → ilk açılışta göç (Yayın-1) → `ledger verify` → başlat; açık pozisyonlar ve defter sürer.
6. Denetim: açılış kapısı tamam; veto adımı yok ve `trader-veto` birimleri durmuş; `ml_filter` satırları; ders servisi tur attı; `session_tag` dolu; bellek ve adım süresi ölçümü §8 eşiğini aşarsa §8 kısıntısı kullanıcıya sorulur.
7. `tasarim-kararlari.md`'ye geçiş tarihi (ayrı commit).

**Geri alma:** birim `--env` eki olmadan taban yapılandırmaya döner (10 çift, v1b); önce `pause` ile yeni giriş kapatılır, taban dışı kâğıt pozisyonlar kapanınca dönülür. Defter v5 geri alınmaz (taban davranış v5 defterle aynen çalışır); gerekirse göç öncesi yedekten dönülür. İkiz arşivden geri getirilebilir.

## 10. S2, kilitli dönem, araştırma kuralları

- S2 ön kaydı donuktur (10 çift, taban dosya, 6 hak). S2-1 beklemede; bu plan onu koşmaz ve tanımını değiştirmez. S2 §8 tarafsızlık testleri ve altın testler her kod commit'inde geçer.
- Kilitli dönem: canlı feed'in ısınma geri doldurması o döneme ait barları `market.sqlite`'a yazar (canlı karar için gerekli). Yasak olan o döneme değen geri test, eğitim, tarama, dilimlemedir. `backtest`/`run_range` ve `fetch_binance_vision.py` yapısal olarak engeller; `pa_proposer` ve nightly süzgeç eğitimi aynı sınırı uygular (kilit sonrası kâğıt kayıtları eğitime girebilir; kilit içi tarihli kayıt girmez).
- Kurulumlar geçmişte başarıma göre seçilmez; doğrudan kâğıtta denenir. Yeni kurulum için geçmiş koşu yalnız teknik doğrulamadır (2021-01 → 2024-01).
- **Gerçek para: askıda.** "Kâğıtta iyi görünen gerçek paraya gider" ilkesi, CANLI-K1, adaylık ölçütü (5B: "kullanıcıya soruldu"), başlangıç tutarı, kasa tavanı, canlı takvimi, risk kademesi — hepsi kullanıcı yeniden belirleyene kadar geçersizdir; bu belge gerçek parayla ilgili hiçbir tarih, ölçüt ya da ön şart içermez. Önceki sürümlerdeki CANLI-K1 atıfları kaldırılmıştır.
- Hisse/emtiada kilit öncesi geçmiş neredeyse yok; yalnız ileriye dönük gözlemdir.

## 11. Tutarsızlık düzeltmeleri (D-sentez A bölümü)

1. `config/lesson.json` (shadow_weeks, twin_*): §15 listesi, WP-08/WP-07 sonrası uygulanır.
2. ML-5 zamanlaması: `ml-faz-tasarimi.md`'deki "ML-5, 6 ay kayıttan sonra" ifadesi kâğıt için geçersizdir; kâğıtta bu belge (§5.3, `M1`) geçerlidir; 6 ay + ayrı ön kayıt + gölge şartları gerçek para için askıdadır (mentor, o belgeye not ekler).
3. `ders-spec.md`: "alınsaydı kanıtına dayanan öneri her zaman kullanıcıya sorulur" kâğıt için kaldırılır (§6.1).
4. `config/panel.json` `max_concurrent` 8 → 16.
5. `shadow_blocks: []`: yalnız gölge **kaydı** kapanır; "aynı mum yasağı"nın kendisi çalışır (§3).
6. `tasarim-kararlari.md` "Paper'da ders ve makine öğrenmesi açık" bölümünün başına "sonraki bölümlerle değişti" notu (mentor).
7. faz-plani.md: 1g zaman dilimi (23), aylık coin güncellemesi (6, 23), 25a (alınsaydı gece işi), ML-4 haftalık yenileme ve ML-5 artık bu belgede şimdi başlar (WP-16, 13, 10/14); mentor işaretler.

## 12. Testler (bağımsız yazar)

| Kod | WP | Davranış |
|---|---|---|
| D-T1 | 01 | Katmansız yükleme (`learner`, `testnet`, `live`) önceki `EngineConfig` ile eşit; `engine.base.json` sabit karma; `bot="twin"` reddedilir. |
| D-T2 | 01 | `--env paper`: 44 çift (taban 10 üst kümesi), kümeler (4/6/5/3/2/2), ML etkin, `shadow_blocks` boş, `max_positions=16`. Yeni anahtarlar testnet/canlıda `ConfigError`; küme çifti / `ml_pairs` / `optional_pairs` `pairs` dışında → hata. |
| D-T3 | 03 | `extract_rules`: `TRADIFI_PERPETUAL` varsayılanla reddedilir, kabul listesiyle döner; `PERPETUAL` iki durumda aynı. |
| D-T4 | 03 | Feed: isteğe bağlı çiftin hatası süreci düşürmez; zorunlu çiftin hatası bugünkü çıkış koduyla; `--env` yokken çıktı aynı; pandas yüklenmez. |
| D-T5 | 05 | Açılış kapısı: kripto bayat → çıkış 7; hisse bayat → geçer, o çift giriş yapmaz; hissede kural yok → yalnız o çift bekler. |
| D-T6 | 04 | Tavanlar: küme, çok üyelik (teknoloji 3 doluyken teknoloji dışı hisse girer; hisse 5 doluyken girmez), hesap 16; aynı barda sıra `pairs` sırası. |
| D-T7 | 04 | **Seans etiketi:** hisse için Cts, Pzt 09:29, 16:00 NY → `closed/weekend` ve **giriş engellenmez**; 09:30 `open`; yaz/kış saati haftaları; metal için Cum 21:00 ve Paz 22:59 UTC `weekend`, Paz 23:00 `open`; kripto hep `open`; etiket karar satırı, aday ve işlemde dolu; tatil barı (`volume==0`/`high==low`) giriş engeller; seans dışında stop/hedef çıkışı çalışır; dersin kapattığı seans `session_closed` ile reddedilir, kapatılmamış seansta ret yok. |
| D-T8 | 05 | ML etkin: evren içi çiftin puanı `pairs` 10 iken ve 44 iken **bit bit aynı**; eşik altı aday `ml_filter` ile elenir; evren dışı aday elenmez; model yok → `ml_no_model`, aday geçer; kâğıt yapılandırmasında gölge satır 0. |
| D-T9 | 06a | Veto kaldırma: `--env paper` motorunda veto adımı çalışmaz ve veto dosyası okunmaz (dosya yok/eski → işlem engellenmez); kripto adayları vetosuz kapılardan geçer; `trader-veto` birimleri `install.sh` sonrası durmuş ve devre dışı; sağlık, Telegram, pano ve rapor çıktısında veto satırı yok; testnet/canlı yapılandırması ve `veto.py` testnet/canlı davranışı değişmedi; eski defter satırları okunur. |
| D-T10 | 08 | Ders ikizsiz ve eşiksiz: farklı-karar kümesi doğru; **aday sayısı şartı yok** (n = 1 ile çalışır; sönümlü ortalama `Σ R/(n+10)`); sönümlü etki ≤ −3 R → o değişiklik geri alınır; toplam ≤ −10 R → referans sürüme dönüş, otomatik uygulama durur, bildirim; referanstan en çok 2 adım; **haftalık sınır yok** (bir gecede iki ayar uygulanır); gevşetme onaysız; `shrink_n=0` tam eşiksiz; ikiz defteri yokken hata yok. |
| D-T11 | 07 | İkiz kaldırma: `install.sh` ikiz birimlerini durdurur/devre dışı, `var/twin` arşive taşınır (silinmez); sağlık, Telegram, pano, yedek ikizsiz temiz çalışır; hiçbir çıktıda ikiz satırı yok. |
| D-T12 | 05 | Geçiş: 10 çiftli, açık pozisyonlu durum/defter 44 çiftle açılır; pozisyon, imleç, parametre sürümü korunur. |
| D-T13 | 01 (her WP'de tekrar) | Tarafsızlık: yeni anahtarlar boşken altın testler (`tests/test_wp3_golden.py`, `test_t28_backtest_digest_unchanged`, `test_engine_compat_equity.py`) ve S2 §8 testleri aynen; `risk.py` varsayılan sabitleri bit bit aynı; testnet/canlı birim dosyaları değişmedi. |
| D-T14 | 18 | Bellek bütçe testi: yumuşak tavan toplamı (200 + 600 + 250 + 250 = 1300) ≤ slice sert tavanı; her servis (eğitim işi dahil) `trader.slice`'ta. |
| D-T15 | 02 | Defter göçü 4 → 5: satır sayıları ve içerik korunur, `arm_id` eski satırda dolu, `session_tag` boş-kabul, yabancı anahtar denetimi temiz, yedek oluştu; yeni zaman dilimleri (`1d`), kurulum kodları, atlama nedenleri ve `trade_notes` kabul edilir, geçersizler reddedilir; yarıda kesilen göç defteri v4'te bırakır. |
| D-T16 | 11 | Bileşik strateji: yalnız kapanan zaman diliminin kurulumları çalışır; 1g bar = 6 × 4s (UTC), eksik 4s barla 1g bar üretilmez; öncelik büyük zaman dilimi; kaybedenler `arm_conflict`; kurulum başına tavan (4; `M1`/`L1` 3). |
| D-T17 | 12a/12b | Her kurulum: ileriye bakma yok, belirlenimci, ısınma eksikken yalnız o kurulum bekler. |
| D-T18 | 11 | Eşdeğerlik: bileşik strateji yalnız `T1@1h` + `R1@1h` ile, aynı veride `price_action_v1_full` ile aynı girişleri üretir. |
| D-T19 | 13 | Gece işi: `arm_conflict`, tavan, ders-kapalı seans ve ML redleri etiketlenir; "alınsaydı" seansa göre kayma kullanır; kurulum karnesi alınan + alınsaydı toplamını doğru verir. |
| D-T20 | 18 | Boyutlama: 44 çift × 14 kurulumla tepe RSS ve saat başı adım süresi ve gece zinciri (ders → not → eğitim) süresi/belleği ölçülür ve raporlanır (eşik 550 MB / 120 sn; aşım testi kırmaz, uyarı üretir). |
| D-T21 | 14 | `pa_proposer`: eğitim girdisinde kilitli döneme ait tek satır varsa hata; özellikler yalnız kapanmış barlardan; aynı girdi → aynı paket sha256; canlı özellik = eğitim özelliği (bit bit); kilit sonrası kâğıt kayıtları kabul edilir. |
| D-T22 | 13/14 | `M1`: paket yok/süresi dolmuş → aday yok, motor çalışır; aday bütün kapılardan geçer. Kurulum dersi: sönümlü ortalama ≤ −0,15 R → kapanır (n = 1 kayıpta kapanmaz, n büyüyünce kapanır), kaydı sürer, ≥ +0,05 R'de açılır. |
| D-T23 | 07/17 | Telegram/pano: sade başlıklar; ders ve ML etkisi sayıları defterle tutarlı; seans kırılımı doğru; hisse kapalı seansında bayatlık alarmı yok; ikiz satırı yok. |
| D-T24 | 18 | Yasak içe aktarma taraması (freqtrade, ccxt, python-binance); dondurulmuş dosyaların sha256'ları değişmedi. |
| D-T25 | 09 | Notlar: her kapanan işlem için bir not satırı (eşik yok); sabit etiket sözlüğü dışı etiket reddedilir; ertesi gün aday ders istemde; etkisi ≤ 0 → emekli, > 0 → yaşar; harcama `budget.py` payına yazılır; pay bitince not işi durur, motor etkilenmez. |
| D-T26 | 10 | Nightly süzgeç: ilk karşıt sınıflı kayıtla model oluşur, öncesi `ml_no_model`; özellikler karar anında bilinenlerdir (`lesson_ids`, `session_tag`), işlem sonrası etiket özellikte yok; paket sha256; sıcak yükleme motoru durdurmaz; eğitim işi bellek tavanında kalır; kilit içi tarihli satır eğitime girmez. Ders kimlikleri eğitim tablosunda. |
| D-T27 | 06b/15 | Bütçe ve `L1`: pay toplamı > aylık tavan → yükleme hatası; `veto` payı yok; `L1` payı bitince yalnız `L1` durur, not/ders etkilenmez; **günlük aday sınırı yok** (bir turda 3'ten fazla öneri geçerlidir); `enabled:false` → sıfır çağrı; geçersiz öneri `llm_invalid`; öneri bütün kapılardan geçer; aylık toplam hiçbir senaryoda 10 $'ı aşmaz. |
| D-T28 | 16 | Aylık güncelleme: toplam 44 kalır; `TRADING` olmayan hisse yedekten değişir; açık pozisyonlu çıkan çift yönetilir ama yeni giriş almaz; `ml_pairs`/S2 listesi değişmez; kaynak yoksa hacim yedeği; kaplama dosyası yoksa `engine.paper.json` aynen. |
| D-T29 | 05 | Kayma: seans içi/`closed`/`weekend` katsayıları (2×/3×/4×) doğru uygulanır; kripto tabanda aynı. |
| D-T30 | 01 | `risk.py`: kâğıtta %1 / %12 / %8 / %8 uygulanır; aynı anahtarlar testnet/canlıda `ConfigError`; verilmezse eski sabitler. |
| D-T31 | 05 | Kâğıt broker: fiyat sıçramalı mumda stop, sıçrama sonrası fiyattan dolar. |

## 13. Bilinen sınırlar

- v1b uzun dönem geri testte zarardaydı ve r03 kapıdan geçmedi; ikisi de kâğıtta bilerek çalışır.
- İkiz olmadığı için ders ve ML etkisi §6'daki yaklaşık ölçüyle izlenir; tavan ve sıra etkileşimlerini içermez.
- Eşiksiz öğrenme küçük örnekte gürültüyü uygular; sönüm (§6.3) bunu hafifletir, kaldırmaz. Hızlı değişen ayarlar birbirinin etkisini karıştırabilir (bir gecede birden çok değişiklik).
- Seans dışı kâğıt dolumları iyimser: gerçek piyasada alış-satış farkı açılır; kayma katsayıları tahmindir (WP-00 ile düzelir). Kazanç açıklaması boşlukları ve yarım gün seansları için koruma yok.
- %1 riskle 16 pozisyon: toplam açık risk %12 tavanı 12. tam riskli pozisyonda bağlar; 16 yalnız küçülmüş riskli pozisyonlarda erişilir. 16 pozisyonda aynı gün toplu stop mümkün (günlük zarar %8 bunu keser).
- LLM notları olay sonrası yorumdur; öğretici olabilir ve yanıltıcı da olabilir. `L1` ve notlar LLM çıktısıdır; bütçe payı bitince yalnız o kalem durur.
- Piyasa değeri sıralaması doğrulanmadı; hisse vadelilerinin fonlaması ölçülmedi.
- `M1` hisse/emtiaya başta kripto eğitimiyle uygulanır; kâğıt kayıtları geldikçe 44 enstrümanı öğrenir.
- Bellek ve işlemci sayıları tahmindir; §8 eşikleri aşılırsa kısıntı kullanıcıya sorulur.
- Gerçek para kararları askıdadır; kâğıt sonuçlarının gerçek paraya bir anlamı bu belgede tanımlı değildir.

## 14. Kullanıcıya kalanlar

1. 44 enstrüman listesinin onayı (kripto sıralaması doğrulanmadı) ve aylık güncelleme için piyasa değeri kaynağı (§1: dış kaynak ağ izni gerekebilir; yoksa hacim yedeği).
2. Sönüm sabiti (§6.3, `shrink_n = 10`): tam eşiksiz isterseniz 0; varsayılan 10.
3. %1 risk / 16 pozisyon / %12 toplam risk uyumu (§4.1 notu): pratik tavan 12 pozisyon; toplam riski %16'ya çıkarmak ister misiniz? Varsayılan: %12 (D-sentez A).
4. LLM kredisi: ön ödemeli kredinin 10 $ aylık kullanıma yetmesi için yükleme sizin/operatörün adımıdır.
5. Gerçek para kararları (CANLI-K1, adaylık ölçütü 5B, başlangıç tutarı, canlı takvimi) askıda; yeniden belirlediğinizde ayrı belgeyle işlenir.

## 15. Yapılandırma değişiklikleri (bu belge `config/lesson.json` dahil hiçbir config dosyasını yazmaz; ilgili WP uygular)

**`config/lesson.json` (WP-07/08 sonrası; mentor onayıyla):** `shadow_weeks` 4 → 0; `twin_enabled` true → false; `twin_ledger_path`, `twin_min_keys`, `twin_z`, `twin_margin_r`, `report_show_twin` kaldırılır; `max_steps_from_twin` → `max_steps_from_ref: 2`; kanıt eşikleri kapatılır: `checkpoints` (30/45/60) kaldırılır, `min_affected` 8 → 1, `min_distinct_days` 8 → 1, `min_z` 2.0 → 0, `min_gap_r` 0.5 → 0, `early_min_n` 10 → 1, `early_min_days` 4 → 1, `monitor_*` ve `recheck_*` süreleri ölçüm penceresi olarak kalır ama asgari sayı yok; `max_user_requests_per_week` kaldırılır; `calibration` ön şart değil (bilgi); yeni: `shrink_n: 10`, `notes_enabled: true`, `notes_model: "claude-haiku-5-5"`, `lesson_candidate_max_in_prompt: 8`, `ref_version`, `max_changes_per_night: null` (sınırsız).

**`config/engine.paper.json`:** §9 WP-01 listesi; WP-11'de `strategy: "price_action_lab_ml"`, `arms`, `arm_max_positions` (4; `M1`/`L1` 3); WP-16'da evren kaplaması.

**`config/veto.json`:** silinir (WP-06a). `veto_exempt_pairs` ve `veto_path` yapılandırması `engine.paper.json`'da yoktur.

**`config/budget.json`:** `monthly_cap_usd` 10 → 30; `monthly_warn_usd` 5 → 15; `daily_cap_usd`: `veto` kaldırılır, `lesson` 0,30 (not dahil), `proposer` günlük tavan yok; yeni `monthly_share_usd`: `lesson` 8, `proposer` 19, `reserve` 3; `api_key_env`: `veto` kaldırılır, `proposer`: `ANTHROPIC_API_KEY_PROPOSER`; `prepaid_credit_usd` kullanıcı kredisine göre; `reservation_ttl_s`/`retry.deadline_s` için `proposer` ve not girdileri eklenir; `prices_usd_per_mtok` aynı.

**`config/llm_proposer.json` (yeni):** `enabled: true`, `run_every_min: 60`, `model: "claude-sonnet-5-5"`, `batch: true`, `arm_max_positions: 3`; günlük sayı anahtarı yoktur.

**`config/universe.json` (yeni):** hisse sıralı listesi (20 + 10 yedek), emtia 4, kripto dışlama kuralları, kaynak ayarı.

**`config/panel.json`:** `max_concurrent` 16; `twin_status_path`, `twin_ledger_path` kaldırılır.

**`config/engine.base.json`, `engine.learner.json`, `engine.testnet.json`, `engine.live.json`:** değişmez. `engine.paper-ml.json`, `engine.twin.json`: silinir.

## Ek (18 Kasım 2026, kullanıcı kararı) — LLM rolü daraldı
- İşlem notu (WP-09) **kodla** yazılır: sabit şablon + sayısal alanlar (`trade_notes.model = "code"`, `cost_usd = 0`); LLM çağrısı yok.
- LLM yalnız **haftalık özet** yazar (sahibin okuması için), mevcut 10 USD kredi bitene kadar; bütçe: aylık tavan bugünkü 10 USD, yeni kredi yok. `L1` (LLM aday önerisi) ve **WP-15 iptal**; WP-06b bütçe paylaşımı: yalnız "haftalık özet" payı (veto payı kalkar). WP-17'deki LLM harcama satırı haftalık özet harcamasını gösterir.

## Kapasite ölçümü (19 Kasım 2026, WP-18)

**Ölçüm betiği:** `scripts/capacity_probe.py` (gerçek `load_cli_config(config,'learner','paper')`: 44 çift, 30 kol incl. `M1@1h`/`M1@4h`, `models/pa_proposer` paketleri yüklü). Veri: sentetik feather, pencereler üretim boyutunda (15dk 5000, 1s 1500, 4s 1500; 1g 4s'ten). Motor ayrı alt süreçte koşar; `ru_maxrss` yalnız motoru ölçer. 96 karar adımı (24 saat: 72 × 15dk, 18 × saat başı, 5 × 4s, 1 × 1g). Kaynak: `scratchpad/capacity_96.json`. Olcum makinesi: 4 çekirdek, 16 GB (sunucu değil).

| Ölçüm | Sonuç | §8 eşiği |
|---|---|---|
| Tepe RSS (motor süreci) | **160,8 MB** (açılış 123 MB, ithalat 116 MB) | öğrenen < 550 MB (D-T20), birim MemoryHigh 600M / MemoryMax 750M: **aşım yok** |
| 15dk adımı (n=72) | medyan **11,8 s**, en kötü 13,0 s | < 120 s: **uygun** |
| Saat başı adımı (n=18) | medyan **17,1 s**, en kötü **18,6 s** | < 120 s: **uygun** |
| 4s adımı (n=5) | medyan 23,3 s, en kötü 23,7 s | < 120 s: **uygun** |
| 1g adımı (n=1, ilk adım) | 24,8 s | < 120 s: **uygun** |
| Toplam 96 adım | 1302 s (ortalama ~13,6 s/adım) | — |

**Karşılaştırma (§8):** tahmini öğrenen tepe 450–520 MB'nin çok altında kaldı; 1100M slice ve 600M/750M birim tavanları sağlanıyor. Saat başı adımı 120 sn sınırının yaklaşık altıda biri. **Önerilen kısıntı yok** (§8 "sığmazsa" yolu tetiklenmedi).

**Sınırlar (dürüst not):** Veri kaynağı canlıda `StoreSource` (`market.sqlite`, 1 dk bar) iken ölçümde `HistoricalSource` (feather, 15dk) kullanıldı; bellek alt-üst değil ama farklı olabilir. Kâğıt kayıt defteri boştu (ilk adımlar). Kurulum süzgeci paketleri (`models/setup_filter`) motora yüklenmedi (küçük, §8 "< 20 MB"). Tarih 30 Nisan 2026 (kilit öncesi; sentetik kural gereği).

### Gece M1 eğitimi (WP-18 b) ölçümü

`scripts/ml_retrain_run.py --once` (kurulum süzgeci + `M1@1h` + `M1@4h`), gerçek `var/history` (10 kripto, 1s/4s), kilit öncesi, ciftbasi kuyruk: tepe RSS **263,6 MB**, süre ~6 s. Önceki sürüm (tüm geçmiş etiketlenip 400k satır) 768 MB verdi; bu yüzden ciftbasi kuyruk ve 50 000 satır tavanı (spec §5.2) uygulandı. Pandas, dondurulmuş `trader_core/indicators.py` üzerinden gelir (~100 MB); bu nedenle pyarrow ile okumak tek başına yetmez.

**Birim kararı:** `deploy/trader-ml-retrain.service`: `MemoryHigh=250M` korundu (ölçüm 263 MB, yumuşak sınır birkaç saniye kısar); `MemoryMax` **300M → 350M** (sert tavan; ölçülen tepe ile marj). Yumuşak tavan toplamı (200+600+250+250 = 1300) değişmedi (D-T14). §8 tablosundaki "250M/300M" satırı bu nedenle 250M/350M olarak okunur.

### Önerilen kısıntı (uygulanmadı)
Yok. Ölçüm §8 eşiklerinin içinde. Gerçek sunucuda `systemctl show trader-engine@learner trader-ml-retrain -p MemoryPeak` ile ilk 48 saat doğrulanmalı (§8 "İzlenecek").

## Ek (19 Kasım 2026) — Hiçbir şey kapanmaz, ML engellemez (sahip kararı)
- **Kurulum kapatma yok:** `arm_lifecycle_step` ve `arms_off.json` yalnız karne/rapor bilgisidir. Kapı (`gates.py`) ders kararıyla
  `arm_disabled` atlaması YAPMAZ; yalnız `arm_would_close` sayacı artar. Evrenden çıkmış çiftlerin (`retired_pairs`) giriş engeli sürer.
- **ML yalnız puan yazar:** `price_action_lab_ml` içinde r03 süzgeci `ml_block=False`; eşik altı aday ELENMEZ, gerekçeye `ml:below`
  eklenir (`ml_below_noblock` sayacı). M1 kendi adaylarını önermeye devam eder. Testnet/canlı stratejileri (`price_action_v1_ml`) değişmez.
