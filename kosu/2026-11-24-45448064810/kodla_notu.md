MF1, GF1 ve IN1 geri testi `trader/research/yeni_kollar/` altında hazır; pytest 30/30 geçti, duman koşusu hatasız bitti. Tam geliştirme koşusunu (43 çift) ve kilitli dönemi çalıştırmadım. Yalnız bu klasöre yazdım. Başta salt okunur bir `git check-ignore` çalıştırdım (`var/vision_raw` ignore'lu mu diye); başka git komutu yok.

## Dosyalar
- `gostergeler.py`: EMA, ATR (Wilder), RSI (Wilder), MACD ve pivot; pivot `kesinlesmis_son` ile ancak 3 mum sonra bilinir.
- `veri_yukle.py`: mumlar (`dl1/veri.indir`), fonlama (aynı Vision yardımcıları) ve `maliyet_tablosu()`.
- `ozellikler.py`: üst zaman dilimi eşleştirme (yalnız kapanmış mum), önceki gün/hafta seviyesi, haftalık VWAP, hacim oranı, fonlama vetosu. Short, fiyatı aynalayarak aynı koddan çıkar.
- `kol_sinyalleri.py`: üç kolun sinyalleri ve teyit açma-kapama ayarları.
- `simulasyon.py`: giriş t+1 açılışında; aynı mumda stop ve hedef varsa stop; boşlukta açılıştan dolum; masraf ve fonlama net R'ye işlenir.
- `metrikler.py` ve `calistir.py`: çıktılar `sonuc.json` ve `ozet.md`. Ablation ve rastgele karşılaştırma dahil; çiftler `multiprocessing` ile paralel çalışır.
- `test_yeni_kollar.py`: testler.

`--donem kilitli` bayraksız 2 koduyla hata verir. Duman ve zamanlama için `--ciftler`, `--tf`, `--bas-ay`, `--kesim` seçeneklerini ekledim.

## Test
- Göstergeler bilinen değerle ve elle hesapla karşılaştırıldı. RSI için Wilder örneğinde ilk değer 70,46 çıkıyor; tablodaki 70,53 yuvarlanmış ara değerlerden geliyor, bağımsız saf-python referansla birebir tuttu.
- Pivot ve üst ZD için gelecek mumları bozunca t anındaki özellik ve sinyaller değişmiyor. Kodu bilerek bozunca (pivot gecikmesini sıfırlamak, üst mumu kapanmadan kullanmak) test kırıldı.
- Ayrıca kapsananlar: aynı mumda stop+hedef, boşluk dolumu, zaman stopu, masraf, fonlama, açık pozisyonda yeni giriş yok, short/long aynası, her kol için elle kurulmuş örnek.

## Duman koşusu
BTC, ETH ve SOL, 1h, 2024-01..04: 1 sn'de bitti. Tam teyitle MF1 17 işlem, GF1 2, IN1 0; "hiç teyit yok"ta MF1 315, GF1 4, IN1 1. Fonlama üç çift için indi.

Ek olarak 4 çiftle (BTC, ETH, SOL, XRP) dört zaman dilimini tam geliştirme dönemi için çalıştırdım. İndirme sonrası hesap 6 sn sürdü. 43 çift için hesap yaklaşık 1 dakika; soğuk indirme dakikalar-onlarca dakika sürebilir ama 2,5 saat sınırına yakın değil.

## Bilinen eksikler ve tasarımla ilgili bulgular
- **IN1 neredeyse hiç işlem üretmiyor.** BTC 1h'de 4,5 yılda 65 ikinci-dip olayı var, bunların yalnızca 5'i seviyede. Dört çift ve dört zaman diliminde tam teyitle 0 işlem çıktı. Hata değil, tasarımın sıkılığı.
- **İkili dip rr≥1,5 kuralını yapısal olarak geçemiyor.** Girişte hedef ≈ formasyon yüksekliği, stop ise dibin altında olduğu için rr 1'in altında kalıyor. Kurulum bulunuyor, işlem açılmıyor. Spec'i değiştirmedim, test bunu belgeliyor.
- **IN1 tetik cümlesini yorumladım.** "Aradaki mumların en yüksek tepesi" kelimesi kelimesine okunursa hedefle çakışıp rr'yi imkânsız yapar. Bu yüzden ikinci dipten tetik mumuna kadarki mumların en yüksek tepesi olarak aldım.
- **Spec'te olmayan parametreler eklendi:**
  - GF1 kurulum penceresi 30 mum.
  - TOBO'da iki tepe farkı ≤ 1 ATR, mum arası 5-60.
  - Üçgen için 80 mum pencere.
  - Sabah yıldızı ve çekiç eşikleri.
  - 1d için üst ZD: c > EMA50 ve EMA50 > EMA200.
- **Ablation'da "hiç teyit yok" tanımı:** yalnız şekil ve rr≥1,5/stop>0 kalıyor. GF1'de seviye teyidi yok, o yüzden ablation'da yer almıyor.
- **Fonlama ve rastgele giriş:**
  - Vision'da yalnız aylık fonlama dosyası var. Kilitli koşuda içinde bulunulan ay için fonlama olmaz ve veto o dönemde kapalı kalır; veri bayatsa (24 saatten eski) veto yok.
  - Rastgele karşılaştırmada açık-pozisyon kuralı uygulanmıyor.
- Yeni indirilen veriler `var/vision_raw` altında; klasör ignore'lu.