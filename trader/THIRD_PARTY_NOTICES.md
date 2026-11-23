# Üçüncü taraf bildirimleri

## regime-trading-bot (MIT)
- Kaynak: github.com/danny123-sudo/regime-trading-bot @ 508d7d9
- Uyarlanan dosyalar: `src/trader_core/indicators.py`, `src/trader_core/regime.py` (gösterge hesapları ve etiket arayüzü iskeleti; sınıflandırma koşulları bize ait).
- Copyright (c) 2026 danny123-sudo. MIT lisans metni ilgili dosyaların başında yer alır.

## freqtrade (GPL-3.0) — kaldırıldı (17 Kas 2026)
- Artık çalıştırılmaz ve kodu bu depoda yoktur; kendi motorumuz (`trader_engine`) kullanılır. Yalnız dondurulmuş sonuç dosyaları salt veri olarak `research/reference/freqtrade-2026.10/` altında saklanır (kod değil). Son referans commit: `bfe5185`.

## 1L3A panosu (kullanıcının kendi projesi)
- Kaynak: `1l3a-proje/motor/canli/pano.py` (kullanıcının kendi deposu; yalnız okunarak kopyalandı, çalıştırılmadı), 2026-11-16.
- Kopyalanan/uyarlanan: `src/trader_panel/static/panel.css` (CSS dizgisi, satır 172-327, değiştirilmeden) ve `src/trader_panel/static/panel.js` içindeki tema düğmesi ile tablo sıralama çekirdeği (JS dizgisi, satır 329-380).

## 1L3A pano Worker'ı ve yayın betiği (kullanıcının kendi projesi)
- Kaynak: `1l3a-proje/deploy/pano_worker.js` ve `deploy/pano_yayinla.sh` (kullanıcının kendi deposu; yalnız okunarak uyarlandı, çalıştırılmadı), 2026-11-16.
- Uyarlanan: `deploy/panel_worker.js` (Basic Auth, fail-closed, sabit zamanlı karşılaştırma; kullanıcı adı/secret adı değişti, kilitsiz yayın bayrağı çıkarıldı) ve `deploy/panel_yayinla.sh` (yayın akışı; kilitsiz kip ve parola-hash dosyası çıkarıldı).

## Aurum v2 (MIT)
- Kaynak: Aurum v2 `aurum/research/stats.py` ve `aurum/research/splits.py`, commit 49f073dfdb2f8831e2fcb39b321c1a02bc4bba5f (yerel klon `sselimgenc-oss/inceleme/tradingbot`; yalnız okunarak kopyalandı, çalıştırılmadı/kurulmadı), 2026-11-16.
- Kopyalanan: `src/trader_core/stats/stats.py` (PSR/DSR, MinTRL, Holm/BH düzeltmeleri, PBO/CSCV, durağan bootstrap) ve `src/trader_core/stats/splits.py` (purged/anchored walk-forward, purged K-fold, CPCV). Değişiklik: `scipy` kaldırıldı (normal dağılım cdf/sf/ppf/isf ve çarpıklık/basıklık `math`/`numpy` ile yeniden yazıldı); yeni bağımlılık eklenmedi. Dosya başlarında MIT başlığı vardır.
- Copyright (c) 2025 zero-was-here. MIT lisans metni ilgili dosyaların başındaki başlıkta atıf olarak yer alır.
- ML-G2 (17 Kas 2026): `aurum/labels/triple_barrier.py` satır 618-687 (aynı commit 49f073d, MIT; yalnız okunarak uyarlandı, çalıştırılmadı) -> `src/trader_ml/weights.py`: `average_uniqueness`, `uniqueness_weights`, `time_decay_weights` (AFML 4.4/4.5). Değişiklik: aralıklar 1 saatlik ızgarada zaman damgası, mean=1 normalizasyonu, `oldest` parametresi; yeni bağımlılık yok.
- ML-G4 (17 Kas 2026): `aurum/features/regime.py` satır 113-134 (`efficiency_ratio`, `variance_ratio`) + `aurum/features/volatility.py` `safe_div` (aynı commit 49f073d, MIT; yalnız okunarak uyarlandı, çalıştırılmadı) -> `src/trader_core/ml_features_v2.py`. Değişiklik: `safe_div` dosyaya gömüldü; yeni bağımlılık yok. Dosya başında MIT atıf başlığı vardır.

## LightGBM (MIT) — yalnız ML eğitim/araştırma tarafı
- Kod kopyalanmadı; `requirements-ml.txt` içinde tam sürüm (4.6.0) + hash sabitli isteğe bağlı bağımlılık. Motor ve bot süreci yüklemez; motor tarafı kendi ağaç okuyucumuzu (`src/trader_ml/treeeval.py`) kullanır. scipy yalnız lightgbm'in dolaylı bağımlılığıdır.

## CT haber/duygu çözücüleri (kullanıcının kendi projesi) — yalnız veri toplama
- Kaynak: `copytrade/canli/haber.py` (CT projesi, kullanıcının kendi kodu; yalnız okunarak uyarlandı, çalıştırılmadı), 2026-11-19; 23 Kasım 2026'da yalnız VERİ TOPLAMA olarak yeniden eklendi (etiket/ton/kural yok; bkz. `docs/veri-toplama-spec.md`).
- Uyarlanan: `src/trader_core/veri_haber.py` (`duygu_coz`, `rss_coz`; ağ `requests` yerine stdlib `urllib`). Kaynaklar (herkese açık, anahtarsız): alternative.me Fear & Greed, CoinDesk RSS, Cointelegraph RSS, Decrypt RSS (`decrypt.co/feed`), Bitcoin Magazine RSS (`bitcoinmagazine.com/.rss/full/`). Yalnız başlık/bağlantı/özet ham olarak saklanır; yeniden yayımlanmaz.

## Hisse ve emtia haber beslemeleri (23 Kasım 2026; KARAR-2) — yalnız başlık okuma
- Tek liste: `src/trader_core/veri_haber.py` `KAYNAK_LISTESI` (ad, url, kategori). Anahtarsız, herkese açık RSS; yalnız https GET, saatte bir, 8 sn zaman aşımı, kimlikli User-Agent (`trader-veri-haber/1`). Başlık/bağlantı/kısa özet saklanır; yeniden yayımlanmaz; yalnız başlık modele (Haiku 5.5) gider ve motor ham haberi okumaz. Kod kopyalanmadı (standart `xml.etree`).
- hisse: CNBC Earnings `cnbc.com/id/15839135/device/rss/rss.html`, CNBC Technology `.../id/19854910/...`, CNBC Finance `.../id/10000664/...` (CNBC RSS Terms); MarketWatch/Dow Jones `feeds.content.dowjones.io/public/rss/mw_topstories` ve `mw_marketpulse`; Nasdaq `nasdaq.com/feed/rssoutbound?category=Markets`; Yahoo Finance `finance.yahoo.com/news/rssindex`.
- emtia: OilPrice.com `oilprice.com/rss/main`; Mining.com `mining.com/feed/` (altın/gümüş/bakır); CNBC Energy `cnbc.com/id/19836768/device/rss/rss.html`.
- Not: şartlar çevrimdışı yazıldı, kullanım koşulları kuruluma geçmeden her yayıncının sitesinde teyit edilmeli; bir yayıncı otomatik okumayı yasaklıyorsa ilgili satır listeden silinir (tek satır). URL'ler canlı doğrulanmadı; ölü/boş besleme yalnız `hata` sayacını artırır, diğerlerini durdurmaz.
