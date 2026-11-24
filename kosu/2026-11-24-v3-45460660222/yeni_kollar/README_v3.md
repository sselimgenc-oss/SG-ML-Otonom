# v3: kitap setuplari (12) geri testi

Kaynak: `setup_secimi.md` (repo kokunde). Her setup ayri kimlik; kategori: `MUM_*` = MF1, `FOR_*` = GF1, `IND_*` = IN1.
Yalniz arastirma; motor/ayar degismez. Setuplar kitapta yazdigi gibi kodlandi, **ust ZD / hacim / seviye / fonlama vetosu gibi kendi teyidimiz yok**.

## Calistirma (trader/ icinden)
```
# testler
PYTHONPATH=src:paket python -m pytest -q research/yeni_kollar
# gelistirme: veri basi .. 2025-07-01 (4 ZD x 12 setup x yon; --setup ile alt kume, --ciftler ile cift secimi)
PYTHONPATH=src:paket python research/yeni_kollar/calistir.py --setuplar v3 --donem gelistirme --cikti ../sonuc_v3_gelistirme
# kilitli: 2025-07-01 .. bugun (YALNIZ kullanici karariyla)
PYTHONPATH=src:paket python research/yeni_kollar/calistir.py --setuplar v3 --donem kilitli --kilidi-ac --cikti ../sonuc_v3_kilitli
# duman (3 cift, 1h, 2024-01..2024-04)
PYTHONPATH=src:paket python research/yeni_kollar/calistir.py --setuplar v3 --donem gelistirme --ciftler BTC/USDT,ETH/USDT,SOL/USDT --tf 1h --bas-ay 2024-01 --kesim 2024-05-01 --cikti /tmp/duman_v3
```
Cikti: `sonuc.json` + `ozet.md` (setup x ZD x yon: sinyal, islem, kazanma, ort net R, toplam R, PF, en buyuk dusus R, yil yil R, cift dagilimi,
rastgele kiyas, cikis turleri [stop/hedef/zaman/sinyal], alt tur dokumu, veri kapsami).

## Dosyalar
- `setuplar_v3.py`: 12 setupun sinyal uretimi (long uzayi, short = ayna), `gercek_sinyaller`.
- `simulasyon_v3.py`: simulasyon (onceki turla ayni kurallar + stop'suz R birimi, dinamik hedef, sinyal cikisi, bekleyen emir).
- `v3_kos.py`: cift basina is, rastgele kiyas, ozet. `calistir.py --setuplar v3` bunu cagirir.
- `test_setuplar_v3.py`: her setup icin sentetik sinyal + olumsuz ornek, ileriye bakis (sentetik + rastgele seri), simulasyon/kosu testleri.

## Degismeyen kurallar (onceki turdan)
Karar t kapanisi, giris t+1 acilisi (ucret+kayma), ayni mumda stop+hedef -> stop, bosluk dolumu, pivot onay gecikmesi, fonlama R'ye islenir (veto yok),
mum boslugu / veri sonu -> islem yok, ilk 250 mumda giris yok, MIN_RISK (risk/giris >= %0,6; yalniz gercek stopu olan setuplarda), ayni cift+setup+ZD'de
acik pozisyon varken yeni giris yok. Ust ZD hic kullanilmaz (setuplarda ust ZD sarti yok), bu yuzden ust mum sizintisi olusamaz.

## Kitabin sayi vermedigi yerlerde YAPILAN TAMAMLAMALAR (karar kullanicinin; hepsi kodda sabit/yorumlu)
1. Tampon yok: "hemen otesi / altinda" stoplari seviyenin kendisi (stop dokunusu = tetik).
2. "Son N mumun en dusugu" = N mumluk pencere, ilgili mum DAHIL (pin 10; yutan: onceki mum icin 5; yildiz: 1. mum icin 2 -> dibi bir onceki mumdan dusuk/esit).
3. Pivot: sol 10 / sag 2, KESIN esitsizlik (kitap "hepsinden buyuk"); pivot i, i+2 kapanisinda kullanilir. Kesin esitsizlik yuzunden duz (esit) tepeler/dipler pivot olmaz.
4. Seviye/boyun penceresi: seviye, ikinci pivotun onayindan ayni turden SONRAKI pivotun onayina kadar gecerli; kirilim = pencerede ilk kapanis; pencere
   oncesinde (ilk pivottan sonra) kapanisla kirilmissa kurulum yok (taze kirilim). Ilk pivot onayi aninda zaten disaridaysa giris yok.
5. "%3 yakin" = |a-b| <= 0,03 * min(|a|,|b|). Yatay aralik yuksekligi = L - pivotlar arasi en dusuk DUSUK (fiyat dibi, pivot dip olmasi sart degil).
6. Pivot cifti hep ARDISIK pivotlar (yatay/ikili: ardisik tepe/dip; OBO: ardisik 3 pivot dip/tepe).
7. Ucgen: yukselen/alcalan icin aradaki pivot dipler (tepeler) kesin yukselen olmali; simetrikte yapi yasi sinirsiz olamayacagi icin en eski pivottan kirilima
   <= 100 mum (UCGEN_MAX_YAS; kitapta yok). Ayni mumda iki alt tur uyarsa ilk (yukselen) alinir. Hedefte "kirilim noktasi" = kirilan seviye/cizginin t'deki degeri.
8. OBO "onceki hareket": sol omuzdan once, formasyon genisligi (sol->sag omuz) kadar geriye en uc deger ile sol omuz arasi >= 2 x (bas-boyun); yeterli gecmis yoksa yok.
   Boyun = omuz-bas-omuz arasindaki en uc iki pivot tepe/dibin dogrusu; bas-boyun = boynun bas konumundaki degeri ile bas ucu arasi. TOBO = long, OBO = short.
   Alternatif stop (boyun + 1 ATR) ve ikili dibin alternatif hedefi (1,4R) KODLANMADI (ana tanim).
9. IC_CUBUK: bekleyen stop emri (kitapta oyle): giris seviyeden (bosluk varsa acilistan), kayma dahil; iki yonlu OCO; ayni mumda iki emir de tetiklenirse aciliste
   daha yakin olan dolar ve (stop prensibiyle) ayni mumda stop olur. Doldugu mumda stop/hedef de o mumun tamamina karsi denenir (muhafazakar; stop onceligi).
   `sinyal` sayisi bekleyen emirleri (iki yon) sayar.
10. Stopsuz setuplar (IND_MA_KESISIM, IND_FIYAT_MA): R birimi = 2 ATR(14) (sinyal mumunda), cikisi etkilemez; kitaptaki cikis (ters kesisim / kapanisla MA'nin
    karsi tarafi) + 48 mum zaman stopu. IND_MA_KESISIM'de 48 mumluk zaman stopu kitap tanimindadir (setup_secimi.md uyarisi: 50/200'u erken keser) — oldugu gibi birakildi.
11. Sinyal cikislari (RSI > 70, ters MA kesisimi, kapanisla MA'nin karsisi) mum kapanisinda tespit edilir, ertesi mum ACILISINDA kapanir (kayma = cikis kaymasi).
    Dinamik hedef (Bollinger orta bandi): bar j icin emir seviyesi j-1 kapanisindaki 20 SMA; bosluk acilistan dolar. Ters kesisimde ayni acilista ters yone gecis serbest.
12. Bollinger: periyot 20, sapma 2, populasyon std (ddof=0).
13. MUM_YILDIZ short: `evening star` icin James'in farkli degerleri (%6 stop / %2 hedef) KULLANILMADI; ayna degerler kullanildi (yuzdeler |fiyat| ile).
14. Rastgele kiyas: setup x cift x ZD x yon grubu basina 200 cekilis (gercek islemlerden yerine koyarak; ayni yil, yon, stop/hedef ATR mesafesi; stopsuzda 2 ATR R birimi),
    ortalama gercek islem sayisiyla agirlikli. Sinyal cikisli / dinamik hedefli setuplarda rastgele taraf STATIK esdeger cikis kullanir (stop+hedef ya da yalniz zaman stopu);
    bu yuzden o setuplarda "fark" yaklasik bir kiyastir. z: N >= 50 degilse "yetersiz".

## Evren ve veri
Cift listesi `engine.paper.json` (43 cift) = maliyet tablosu. Hisse/emtia (NVDA..COPPER, XAU/XAG/BZ) arsivde listelendikleri aydan baslar; gecmisleri kisadir ve
`ozet.md` sonundaki "Veri kapsami" bolumunde cift x ZD olarak yazilir. 15m verisi cerceve varsayilaniyla 2023-01'den baslar (`veri_yukle.BAS_AY`); 1h/4h/1d 2021-01.
