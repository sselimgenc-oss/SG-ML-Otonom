Sen kidemli bir kantitatif arastirmaci ve yazilim mimarisin. Yalniz okuyabilirsin. Proje: Binance USDT-M vadeli botu "ML Otonom" (kod trader/; kagit = canli).

KULLANICI KARARI (24.11, kesin): Uc yeni kol FORMASYON KUTUPHANESI olacak, tek setup DEGIL:
- MF1 = kitaplardaki TUM mum formasyonlari; GF1 = TUM grafik formasyonlari (ikili tepe/dip, OBO/TOBO, bayrak/flama, ucgenler, kama, yatay kirilim, kanal ...);
  IN1 = TUM indikator setuplari (RSI, MACD, Bollinger, MA kesisimleri, hacim, uyumsuzluk, Stokastik ...).
- Bot 43 enstrumani 4 zaman diliminde (15m, 1h, 4h, 1d) tarar; hangi formasyonu yakalarsa ona girer.
- Her formasyon kendi kimligiyle (or. MF1-YUTAN@1h) mevcut ogrenme sistemine girer: kol kucultme / karantina / gece dersleri / alinsaydi formasyon x ZD bazinda calisir.
- BASLANGIC: HEPSI ACIK (zarar edenler dahil, 15m dahil); bot kagitta ogrenecek.

KAYNAKLAR:
- Kurallar: fikirler/yeni-kollar/kurallar.jsonl (69 kitap, 443 kural).
- Gecmis test (duz dosya olarak acildi): onceki/kosu/ altinda; v3 klasoru: setup_secimi.md, rapor.md, sonuc_v3_*/, yeni_kollar/ (12 setupun dedektorleri,
  ileriye bakissiz pivot, cikis simulasyonu). Onceki turlar da ayni yerde.
- Motor: trader/src/trader_engine/strategies/arms/ (__init__.py kesif kurali "her kurulum tek dosya", find_arm), strategies/lab.py, engine.py (_entry_order, _pair_entries,
  limits, arm_max_positions), gates.py, arm_guard.py, trader_core/kol_kucultme.py, trader_core/ledger.py (LESSON_SCOPE), trader_core/kol_yasam.py, counterfactual / alinmayan_sonuc,
  trader/config/engine.paper.json ve engine.live.json (arms listesi, arm_max_positions, PRIORITY), trader_core/indicators.py, panel ve Telegram'da kol listeleri.

GOREV: Sonnet'in AYNEN kodlayacagi uygulama tasarimini yaz.
1. Formasyon listesi: kurallar.jsonl'den mekanik olarak kodlanabilen HER formasyonu cikar (kategori basina tahminen 8-15). Her biri icin kod adi, kitaplarin cogunlugunun
   tarifi: giris, stop, hedef, zaman stopu, gerekiyorsa filtre (kitapta varsa). Gecmis testte kodlanmis 12 setupu oldugu gibi kullan.
2. Kimlik ve kesif: alt formasyonlar motora nasil girer (or. tek dosya mf1.py icinde formasyon tablosu, arm_id = "MF1-YUTAN@1h"); find_arm/registry/ayar arms listesi,
   ARM_SCOPE, lesson kapsami, kol kucultme ve karantinanin formasyon x ZD bazinda calismasi icin neler degisir.
3. Catisma: ayni mumda ayni ciftte birden fazla formasyon -> hangisi (oncelik kurali); yeni kollarin mevcut 10 kola gore oncelik yeri; kapasite tavanlari
   (arm_max_positions su an kol x ZD basina; kutuphanede formasyon basina mi, aile basina mi; toplam riski ne korur). Sinyal seli (or. Bollinger 15m'de cok sinyal) icin
   yalniz mevcut tavanlar ve ogrenme kullan (kullanici hepsi acik dedi).
4. Ogrenme: mevcut mekanizmalarin formasyon bazinda dogru calistigini garanti eden degisiklikler; gecmis test sonuclarinin (48 hucre) ogrenmeye ilk bilgi olarak nasil
   verilecegi (or. on deger / sadece rapor) — kullanici karari "hepsi acik" bozulmadan.
5. Gerekli gostergeler ve ileriye bakis kurallari, panel/Telegram/rapor etkisi, testler (her formasyon icin sentetik ornek + ileriye bakis + kagit=canli ayar esitligi),
   hash sabitlemeli testlerin guncellenmesi.
6. Is bolumu: Sonnet'in kac adimda yapacagi (or. 1: altyapi + MF1, 2: GF1, 3: IN1), her adimin kabul olcutu.
Son mesajinda YALNIZ Markdown, sade Turkce, uygulayici icin kesin: # Formasyon kutuphanesi tasarimi ... (bolumler 1-6).
