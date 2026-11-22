# DEVİR NOTU — ML Otonom (22.11.2026 akşam)

Yeni oturum bunu baştan sona okur, sonra İLK İŞ olarak pazartesi 23.11 12:00Z (15:00 TSİ) için kendine hatırlatma kurar (send_later): "Pazartesi gündemi: fikirler/pazartesi-23-11/devir.md, kullanıcı 'okey' demeden başlama".

## Proje
- Repo: sselimgenc-oss/SG-ML-Otonom (eski adı SG-Github-AB-proje yönlendirir). Kod `trader/`. Push YALNIZ `claude/charming-hawking-ab5w5q` dalına. PR açılmaz (istenmedikçe).
- Binance USDT-M vadeli bot. Şu an YALNIZ KÂĞIT (sanal para): başlangıç 1.000 $, 22.11'de ~1.066 $. 44 enstrüman (20 kripto + 21 ABD hissesi + 4 emtia, TradFi vadeli), 8 strateji × 4 zaman dilimi = 32 kol, ML filtresi.
- Sunucu: DigitalOcean Londra (LON1, 178.128.33.149). Oto güncelleme yalnız CI'ı yeşil commitleri 10:30 ve 22:30 TSİ'de kurar; hemen kurmak için sunucuda `sudo trader-oto-simdi`.
- Durum yayını: `canli-durum` dalı, `ml/durum.json` (saatlik). Okuma: `git fetch origin canli-durum`.
- Pano: Cloudflare worker `trader-pano` (şifresiz, kullanıcı kararı).
- TESTNET KAPATILDI (22.11, kullanıcı kararı): eski price_action_v1 + ML/veto kapalı çalışıyordu, kâğıttan farklıydı. Sunucuda servis + timer disable, `/etc/trader-testnet.env` anahtarları yorum satırı (install.sh yeniden açmaz; kurulum çıktısında "MISSING testnet" uyarısı zararsız), `HEALTH_SHADOW_VAR_DIR` boş. Canlı öncesi prova gerekirse kâğıtla aynı sistemle yeniden açılır (kullanıcı kararı).
- CT projesi tamamen kapatıldı (repo, sunucu, Cloudflare, Telegram botu). ML'nin CT'ye bağı yok.

## Kullanıcı kuralları
- Kullanıcı "okey" demeden HİÇBİR işe başlama; senin yerine karar verme; kod planı onaysız uygulanmaz.
- Para, limit, canlı ve anahtar kararları yalnız kullanıcının. Anahtar/sır sohbete yazılmaz.
- Kâğıtta her şey açık ve işleme etkili (gölge/yalnız kayıt yok).
- Raporlar sade Türkçe tablo. Arşiv yok.
- Fable yalnız danışman; işi Sonnet/Haiku yapar. Token tasarrufu öncelikli.
- Holdout 2026-05-01→2026-11-01 okunmaz; `research/holdout_muhur.py dogrula` ESIT basmalı.
- Hash ile dondurulmuş dosyalara (tests/engine/test_dd12_wp18_impl.py FROZEN_SHA256 listesi) yalnız kullanıcı kararıyla, bilerek dokunulur. Test atlama/xfail yok. config JSON'da `leverage` anahtarı yasak. freqtrade/ccxt/python-binance yok. Saat için SystemClock.
- Otomatik güvenlik kontrolü bir işi engellerse ATLATMAYA ÇALIŞMA; kullanıcıya söyle.
- Commit sonu: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` + `Claude-Session: <oturum linki>`. Commit'e model adı yazılmaz.

## Çalışma yöntemi (kalıcı, kullanıcı onaylı 22.11)
1. Önce program (grep/test/betik), sonra model.
2. Önce test; iş bitti = hedefli testler + GitHub CI yeşil + holdout ESIT + `scripts/ci_duman.py`.
3. Okuyan Haiku, kod Sonnet, karar/son kontrol Fable; ana oturum yalnız yönetir.
4. Ajan özeti en çok 10–15 satır, her iddiaya dosya:satır kanıtı; ana oturum yalnız karara etkili iddiaları tek grep ile doğrular.
5. Dar görev: tam dosya yolları, keşif yok, yalnız hedefli testler (tam takım yavaş). Test: `trader/.venv/bin/python -m pytest -q -p no:cacheprovider <dosyalar>`. Bilinen ortam kaynaklı kırmızılar: test_rehearsal_empty_server_feed_rules_gate_status_health (disk_low), test_exec_lines_resolve_to_real_module_script_subcommand.
6. Kritik değişiklikte bağımsız ikinci göz — ona sonuç değil yalnız diff.
7. Kısa oturumlar + devir notu.
8. Kararlar tek seferde soru kutusuyla; tekrar eden "bekliyorum" mesajı yok.
- Worktree: Agent `isolation: worktree` bu repoda hata verebiliyor; `git worktree add -b <dal> /home/user/<dal> HEAD` ile elle aç, ajana yolu ver.

## GÜNDEM (pazartesi 23.11 15:00 TSİ sonrası, kullanıcı sırası)
### 1) Kararlar VERİLDİ — "okey" gelince uygulama planı sun (Fable öncelik sırası)
Tam tablo: `notlar.md` sonu ("KULLANICI KARARLARI 22.11").
- g) İki komut: "Durdur" = yalnız yeni giriş durur; "Hepsini kapat" = ayrı, onay sorar; açık pozisyon stopları çalışmaya devam eder.
- b) Zirveden düşüş kilidi %15, kâğıtta da açık; açıklar kalır; yalnız kullanıcı açar; zirve yeniden başlatmada silinmez; başlangıç −%20 kuralı (ladder) ikinci emniyet. Yer: `src/trader_engine/pause.py`, `ladder.py`, `gates.py`.
- c) Canlıda HEPSİ (kripto + hisse + emtia). Gerekli: `src/trader_engine/config.py` `_PAPER_ONLY_KEYS` içindeki `contract_types` canlıya da izin (22.11'de otomatik güvenlik kontrolüne takıldı — kullanıcının açık kararı burada; yine takılırsa kullanıcıdan izin ayarı iste) + broker `binance_futures.py:353` `extract_all_rules` contract_types geçirmiyor. Önce sunucuda tam sembol adları doğrulanmalı: pairs'te borsada olmayan TEK sembol motoru başlatmaz (RulesFetchError, marketdata/feed.py:322-356). Sunucu testi: gerçek Binance'te 43/44 var (TON yok); "V" yalnız önek eşleşmesiyle bulundu, doğrulanmadı.
- h) Repolar canlıdan önce private + sunucuya okuma yetkili anahtar + oto güncelleme yeniden test (oto_guncelle şu an anonim curl ile indiriyor).
- d) Canlı kasa tavanı 2.000 $ TOPLAM (vadeli cüzdan, sonradan eklenenler dahil); koddaki kilitli 1.500 $ sert sınırı kullanıcı kararıyla 2.000 $ (kilit testleri bilerek güncellenir).
- e) İlk canlı kasa 1.000–2.000 $ (kullanıcı riskleri biliyor).
- a) Kâğıt kaldıraç 3x (HARD_LIMITS max 5 ayrı), S1 stop bandı 2,0 kalır; 2 hafta ölçüm sonra karar.
- f) BNB ücret indirimi: hayır. Ek: hafta sonu hisse büyüklük tavanı: gerek yok.
- Canlı listesi şu an 19 kripto (d42c207); testnet config 20 (testnet kapalı).

### 2) ML + algoritmik fikirler (birlikte, sonra kullanıcı seçer)
- `x-algo-fikirleri.md` + aynı klasördeki 3 PDF (trading-ml-arastirmalari, trading-ml-dunya-taramasi, en-uygun-5-calisma-proje).
- 3 kitap (telifli; repo PUBLIC olduğu için repoya KONMADI): Gizlyk "MQL5 ile Algoritmik Alım Satım için Yapay Sinir Ağları" 752 sf, Jansen "Algoritmik Trading için Makine Öğrenimi" 1161 sf, Giller "Finansal Veri Biliminin İzinde" 500 sf. Kitaplar kullanıcının bilgisayarındaki arşivde (masaüstü pdfler klasörü) zaten var — yeniden yükletme; arşiv taramasıyla (Remote Control + pdftotext) birlikte okunur. Önce içindekiler, sonra yalnız ML'ye yarayan bölümler.
- Kullanıcının 3200 PDF arşivinden "Özel-Makine Öğrenmesi 1" ve "Özel-Algoritmik Trading 1" klasörleri.
- Çıktı: tek birleşik sade tablo (bizde olmayan + ML'ye yarayan).

### 3) Strateji arşivi (ayrı)
Arşivin geri kalanı: Trend/Momentum/Strateji → Swing → Price Action/Teknik. Scalp/Day Trade/Diğer/İlginç dışarıda (verimizle test edilemez).

Arşiv taraması planı (2 ve 3, Fable onaylı): PDF'ler kullanıcının bilgisayarından çıkmaz (Remote Control ile bağlan, pdftotext betiği orada); okuma Claude API Batch + Haiku ile kullanıcının Console bakiyesinden (10 $; harcama tavanı + ayrı "kitap-tarama" anahtarı; anahtar sohbete yazılmaz); ana oturum yalnız betik + seçim. Önce 30–50 kitap pilot, gerçek maliyet ölçülür. Tur başına 5–8 fikir; şartname/eşik testten önce kilitli; kümülatif deneme defteri + SPA/PBO; holdout yok; 2 tur boş çıkarsa strateji madenciliği durur. Public repoya yalnız kendi sözlerimizle katalog. Beklenti 0–2 yeni kol; asıl değer ML yöntemleri. İkinci Claude hesabı önerilmedi.

### 4) Sunucu (acele değil, en son; kullanıcı "o sende" dedi)
- Londra'dan fapi.binance.com erişimi VAR (451 yok). Belirleyici olan Binance hesap ülkesi/KYC — kullanıcıya sor, Binance kurallarını araştır (vadeli + TradFi izinleri).
- Konum değişmesi gerekirse Hetzner seçenek (Coolify önerilmedi).
- Sunucuda "System restart required": uygun saatte birlikte yap, sonra servisleri kontrol et.

## 22.11'de yapılanlar (bilgi)
- Pano: kapanan işlemlerde büyüklük/kaldıraç/marj + tüm tablolarda başlıktan sıralama (4634713, kuruldu).
- Canlı/testnet enstrüman listesi 10 → 19/20 kripto, kilit testleri yeniden sabitlendi (608a36f, d42c207, CI yeşil).
- CT kapanış kontrolü: CT'den yalnız 2 fikir alındı (zirveden düşüş kilidi + sunucu konumu); diğerleri iptal.
- Gözlem: hafta sonu hisse fiyatı seyrek gelince panoda "açık pozisyonun fiyatı gelmiyor" uyarısı çıkıyor; pazartesi açılışla düzelmesi beklenir.
- YouTube oyunlaştırma: ÇOK SONRA, ayrı proje (kullanıcı kararı).
