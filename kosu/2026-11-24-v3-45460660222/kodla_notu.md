12 setup eklendi, testler geçiyor ve duman koşusu çalışıyor. Tam gelişme koşusunu yapmadım. Kilitli dönemi çalıştırmadım.

**Eklenen setuplar** (hepsi `calistir.py --setuplar v3` ile, 4 ZD x long/short/hepsi)
- MF1: `MUM_PINBAR`, `MUM_IC_CUBUK`, `MUM_YUTAN`, `MUM_YILDIZ`
- GF1: `FOR_YATAY_KIRILIM`, `FOR_UCGEN`, `FOR_IKILI_DIP`, `FOR_OBO`
- IN1: `IND_RSI_3070`, `IND_MA_KESISIM`, `IND_BOLL_DONUS`, `IND_FIYAT_MA`

Yeni dosyalar `trader/research/yeni_kollar/` altında: `setuplar_v3.py`, `simulasyon_v3.py`, `v3_kos.py`, `test_setuplar_v3.py`, `README_v3.md`. Ayrıca `calistir.py`'ye `--setuplar v3` ve `--setup` eklendi.

**Test:** `pytest -q research/yeni_kollar` → 85 geçti, skip/xfail yok (41 eski, 44 yeni). Yeni testler her setup için sentetik sinyal ve olumsuz örnek içeriyor. Ayrıca gelecek mumlar bozulunca t sinyalinin değişmediğini hem sentetik örneklerde hem rastgele seride sınıyor.

**Duman** (3 çift, 1h, 2024-01..04, 1 sn). İşlem sayıları:

| Setup | İşlem |
|---|---|
| `MUM_PINBAR` | 109 |
| `MUM_IC_CUBUK` | 436 |
| `MUM_YUTAN` | 207 |
| `MUM_YILDIZ` | 4 |
| `FOR_YATAY_KIRILIM` | 222 |
| `FOR_UCGEN` | 45 |
| `FOR_IKILI_DIP` | 126 |
| `FOR_OBO` | 2 |
| `IND_RSI_3070` | 29 |
| `IND_MA_KESISIM` | 40 |
| `IND_BOLL_DONUS` | 815 |
| `IND_FIYAT_MA` | 624 |

**Süre:** 4 çiftle (BTC, ETH, SOL, NVDA), tüm ZD'ler, geliştirme dönemi: 130 sn, çoğu veri indirme. İşlemci süresi yaklaşık 26 sn. 43 çiftin tamamı için 2,5 saatin çok altında kalması beklenir. 43 çiftin 15m/4h/1d verisi önbellekte yok, ilk koşuda inecek. Bunu tam koşuda ölçmedim.

**Bilinen eksikler ve varsayımlar** (ayrıntı `README_v3.md`'de)
- Kitabın sayı vermediği yerlerde tamamlama yaptım: tampon yok, pivot sol 10/sağ 2 kesin eşitsizlik, "%3 yakın" tanımı, kırılım pencereleri, simetrik üçgende 100 mum yaş sınırı, OBO önceki hareket penceresi. Bunları sen onaylamalısın.
- Stopsuz `IND_MA_KESISIM` ve `IND_FIYAT_MA`'da R birimi 2 ATR(14) aldım; MIN_RISK tabanı bunlara uygulanmıyor.
- `IND_MA_KESISIM`'de 48 mum zaman stopunu kitaptaki gibi bıraktım; çıkışların çoğu zaman stopundan geliyor.
- Rastgele kıyası "setup x çift x ZD x yön başına 200 çekiliş", gerçek işlem sayısıyla ağırlıklı yaptım. Eski turdaki "işlem başına 200" değil. Sinyal çıkışlı ve dinamik hedefli setuplarda rastgele taraf sabit eşdeğer çıkış kullanıyor, yani kıyas yaklaşık.
- `IC_CUBUK`'ta `sinyal` sayısı iki yönlü bekleyen emirleri sayıyor, ayrıca emrin dolduğu mumda stop kontrolü o mumun tamamına karşı yapılıyor (temkinli).
- Alternatif çıkışlar (OBO'da boyun+1 ATR, ikili dipte 1,4R, akşam yıldızında James'in %6/%2 değerleri) kodlanmadı.
- Dosyaya dört terim yeni girdi: 15m veri çerçeve varsayılanıyla 2023-01'den başlıyor. NVDA gibi hisse/emtia çiftlerinin geliştirme döneminde verisi yok, "bu dönemde veri YOK" diye `ozet.md`'nin kapsam bölümüne yazılıyor. Kilitli dönemde bu çiftlerin geçmişi kısa olacak.