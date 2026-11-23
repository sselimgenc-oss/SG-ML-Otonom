# Veri toplama belirtimi (haber + piyasa pozisyonu)

Karar: 23 Kasım 2026. Amaç: ileride gölgede çalışacak modeller (LLM haber okuyucu, derin öğrenme; "üst lig" hattı) için ham veriyi ŞİMDİDEN biriktirmek.

**Bu veri bir karar girdisi DEĞİLDİR.** Kapı, kural, ML özelliği, not, panel/Telegram metni: hiçbirine girmez. `trader_engine` altındaki hiçbir modül (motor, kapılar, strateji, ML süzgeci) `var/veri/haber` ya da `var/veri/piyasa` dizinlerini okumaz ve toplayıcı modülleri içe almaz. `tests/test_veri_toplama.py` bunu kaynak taraması ile zorlar. 21 Kasım'da silinen etiket/duygu kuralı/otomatik kapat-aç mekanizması GERİ GELMEDİ; yalnız toplayıcı ve depo geri eklendi.

## Haber (`var/veri/haber/`, saatlik, `trader-haber.timer`)
- `haber.jsonl`: ham RSS ögeleri. Satır: `ts` (yayın zamanı, ms; yoksa alım zamanı), `alim` (alım ms), `kaynak`, `baslik`, `baglanti`, `ozet` (varsa, HTML'siz, en çok 500 karakter). Tekilleştirme anahtarı: kaynak + bağlantı (yoksa başlık).
- `fng.jsonl`: alternative.me Fear & Greed geçmişi (`ts` endeksin kendi zaman damgası, `deger` 0-100, `sinif`). Anahtar: `ts`. Her turda son 10 gün istenir; eksik günler kendiliğinden dolar.
- Kaynaklar: CoinDesk, Cointelegraph, Decrypt, Bitcoin Magazine (hepsi RSS 2.0, anahtarsız, yalnız https GET). Tek kaynak hatası diğerlerini durdurmaz; kimse alınamazsa dosyaya dokunulmaz.
- Betik: `scripts/haber_run.py`; modül: `src/trader_core/veri_haber.py`.

## Piyasa pozisyonu (`var/veri/piyasa/<uc>/<SEMBOL>.jsonl`, saatlik, `trader-piyasa-veri.timer`)
Kapsam: `engine.base.json` içindeki 19 kripto çifti (hisse/emtia `optional_pairs` hariç). Uçlar (Binance USDⓈ-M, herkese açık GET, anahtar yok):

| `<uc>` | Uç | Alanlar |
|---|---|---|
| `oi` | `/futures/data/openInterestHist` (1h) | `oi`, `oi_value` |
| `gls` | `/futures/data/globalLongShortAccountRatio` (1h) | `ratio`, `long`, `short` |
| `tpp` | `/futures/data/topLongShortPositionRatio` (1h) | `ratio`, `long`, `short` |
| `taker` | `/futures/data/takerlongshortRatio` (1h) | `ratio`, `buy`, `sell` |
| `funding` | `/fapi/v1/fundingRate` (8 saatte bir olay) | `rate`, `mark` |

- İlk çalıştırmada API'nin izin verdiği kadar (yaklaşık 30 gün) geriye doldurulur; sonraki turlar yalnız son satırdan sonrasını ister.
- Kilitli dönem (HOLDOUT, 2026-05-01..2026-11-01) zaman damgaları ne istenir ne yazılır (geri doldurma 30 gün olduğundan yalnız 24 Ekim-1 Kasım arası atlanır).
- Henüz kapanmamış olabilecek son saatlik satır (`ts > şimdi - 1 saat`) yazılmaz; yazılan satır sonradan değişmez.
- İstemci ve ban koruması `oi_collector` ile AYNIDIR: ortak `ban.<host>.json` dosyası (418/429 → tüm toplayıcılar susar), ağırlık tavanı (dakikalık 1200), asgari istek aralığı 0,5 sn, tur başına en çok 900 istek.
- Betik: `scripts/piyasa_veri_run.py`; modül: `src/trader_engine/marketdata/veri_piyasa.py`.

## Mevcut olan (yeni değil)
`trader-oi` (5 dakikalık OI/long-short toplayıcısı, `var/market.sqlite` `positioning_5m`, ML-G7) zaten vardı ve DEĞİŞMEDİ. Yeni hat ondan ayrıdır (saatlik, JSONL, farklı dizin; `topLongShortAccountRatio` yok, funding var). Funding için `feed`in `funding` tablosu da vardır; burada ham olay olarak ayrıca saklanır.

## Depo ilkeleri
- Yalnız-ekleme: var olan satır değiştirilmez ya da silinmez; yeni satır dosya sonuna tek yazım + `fsync` ile eklenir. Yarım kalmış son satır yeni yazımda satır sonu ile ayrılır, okuyucu bozuk satırı atlar.
- Sıkıştırma/ayıklama sonradan, ayrı bir işle (şimdilik yok). Tahmini büyüklük: piyasa ~19 × 5 uç × 24 satır/gün; haber birkaç yüz satır/gün.
- Kurulum: `deploy/install.sh` `var/veri` dizinlerini açar ve iki zamanlayıcıyı etkinleştirir. Servisler yalnız `var/veri` (haber) ve `var` (piyasa; ban dosyası için) yazabilir.

## Kullanım ve sınır
Gölge/üst lig modelleri bu veriyi YALNIZ çevrimdışı okur ve gölgede (kayıt amaçlı, işlem etkisiz) çalışır. Canlı karara bağlanmadan önce ayrı bir kullanıcı kararı ve kanıt gerekir. Haber başlıklarının yeniden yayımı yoktur; yalnız dahili araştırma.
