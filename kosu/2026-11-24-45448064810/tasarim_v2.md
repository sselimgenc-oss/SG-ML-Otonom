# Yeni kollar tasarimi, surum 2 (Fable, 24.11; kullanici "guclendir" dedi, "gecmis veride test et" onayladi)

Kaynak: kullanicinin PDF kutuphanesinden Haiku Batch ile cikarilan 443 kural (netlik>=3: 300). Kollar 15m/1h/4h/1d calisir. Short = long'un aynasi.
Karar son KAPANMIS mumda. Risk %1. ATR(14).

## Ortak teyit katmani (uc kol da kullanir)
| Teyit | Tanim (long) |
|---|---|
| Ust ZD yonu | 15m -> 1h ve 4h; 1h -> 4h; 4h -> 1d; 1d -> kendi EMA50/200. "Yukari" = son KAPANMIS ust mumda c > EMA50 ve EMA50 yukseliyor (EMA50[t] > EMA50[t-5]). "Yatay" = ne yukari ne asagi |
| Onemli seviye | Onceki gun dibi, onceki hafta dibi (UTC'ye gore biten donem), ust ZD dip pivotu, haftalik VWAP (yalniz kapanmis mumlardan). "Seviyede" = mesafe <= 0,3 ATR |
| Hacim | v >= 1,5 x 20 mum ortalamasi |
| Fonlama (veto) | Karar anindan once kesinlesmis son fonlama > +%0,05 ise long yok (short icin < -%0,05) |
| Maliyet tabani | Stop mesafesi < %0,6 ise islem yok |

## MF1, seviyede mum donusu
- Sartlar (hepsi): ust ZD yukari ya da yatay; mum dibi bir onemli seviyeye deger ya da deler, kapanis seviyenin ustunde; sekil yutan / cekic / sabah yildizi; formasyon araligi >= 1 ATR; hacim teyidi; fonlama vetosu.
  - Yutan: t-1 kirmizi, t yesil, t govdesi t-1 govdesini kapsar. Cekic: alt fitil >= 2 x govde, ust fitil <= araligin %10'u, kapanis ust ucte birde. Sabah yildizi: 3 mum (t-2 buyuk kirmizi, t-1 kucuk govde, t yesil ve kapanisi t-2 govde ortasinin ustunde).
- 15m ek sart: 1h ve 4h ikisi de yukari.
- Stop: formasyon dibi - 0,2 ATR. Hedef: en yakin karsi seviye (onceki gun tepesi ya da son onayli tepe pivotu); rr < 1,5 ise islem yok. Zaman stopu 16 mum.

## GF1, formasyon (ikili dip, TOBO, yukselen ucgen)
- Pivot: sol 5, sag 3 mum; pivot ancak 3 mum sonra kesinlesir (t-3 ve oncesi).
- Ikili dip: iki dip pivotu, arasi 8-60 mum, fark <= 0,5 ATR; aradaki tepe (boyun) diplerden >= 2 ATR yukarida.
- TOBO: uc dip; bas iki omuzdan >= 0,5 ATR asagida; omuz farki <= 1 ATR; boyun = aradaki iki tepe pivotunun yuksegi (yatay).
- Yukselen ucgen: >= 2 tepe pivotu 0,3 ATR icinde yatay, >= 2 yukselen dip pivotu.
- Daralma: sag taraftaki ortalama ATR, sol taraftakinden kucuk. Ust ZD asagi trend degil.
- Giris A: kapanis boyun + 0,3 ATR ustunde, hacim >= 1,5x, kapanis mumun ust ceyreginde, boyundan uzaklik <= 1,5 ATR.
- Giris B: A tutmadiysa 10 mum icinde boyuna geri test, boyun altinda kapanis yok, yukari kapanis.
- Sahte kirilim: kirilimdan sonra boyun altinda kapanis olursa kurulum iptal.
- Stop: son dip pivotu - 0,2 ATR; > 3 ATR ise islem yok. Hedef: formasyon yuksekligi; rr < 1,5 ise islem yok. Zaman stopu 48 mum.
- 15m ek sart: 1h + 4h yukari ve formasyon yuksekligi >= 3 ATR.

## IN1, seviyede pivot onayli uyumsuzluk
- Iki onayli dip pivotu, arasi 5-40 mum. Ikinci dip fiyatta >= 0,2 ATR daha dusuk. RSI(14) ikinci dipte >= 3 puan daha yuksek, ilk dipte RSI < 35. MACD(12,26,9) histogrami ikinci dipte daha yuksek.
- Ikinci dip bir onemli seviyede. Ust ZD yukari ya da yatay. Fonlama vetosu.
- Tetik: ikinci dipten sonraki 8 mum icinde kapanis, aradaki mumlarin en yuksek tepesinin ustunde; hacim >= 1,2x.
- Stop: ikinci dip - 0,3 ATR. Hedef: iki dip arasindaki tepe pivotu; rr < 1,5 ise islem yok. Zaman stopu 24 mum.

## Ileriye bakis kurallari
Pivot yalniz t-3 ve oncesi. Ust ZD mumu kapanmadan kullanilmaz. Onceki gun/hafta seviyesi UTC'ye gore biten donemden. VWAP yalniz kapanmis mumlardan.
Fonlama yalniz karar anindan once kesinlesmis oran.


## Tur 2 degisiklikleri
Kaynak: analiz_tur1.md "Uygulanacak degisiklikler". Esik ince ayari yapilmadi; yalniz asagidaki maddeler uygulandi. Kod: trader/research/yeni_kollar/.
Geri test kod denetiminde sonuclari gecersiz kilan hata yoktu; kucuk kusurlar (fonlama, risk tabani, rastgele taban, isinma, veri sonu/bosluk) madde 6 ile giderildi. IN1 eslesme ve GF1 B geri testi sapmalari madde 2-3 ile.

1. **Kapatilan hucreler:** uc kolun 15m'si, MF1 1h, IN1 1d. `calistir.py` icinde `IZINLI` tablosu: MF1 4h/1d, GF1 1h/4h/1d, IN1 1h/4h; digerleri hesaplanmaz. `kol_sinyalleri.py`'deki 15m ozel dallari (zd_siki, formasyon yuksekligi >= 3 ATR) silindi. Varsayilan `--tf` = 1h,4h,1d.
2. **GF1 stop:** islem stopu = boyun - 1 ATR (giris mumunun ATR'si); "risk > 3 ATR ise islem yok" kalkti. Hedef (formasyon yuksekligi) ve rr >= 1,5 ayni. Formasyon dibi - 0,2 ATR artik yalniz kurulum IPTAL seviyesi (kapanis altina inerse kurulum duser). B girisi geri testi `low <= boyun` (eskiden boyun + 0,3 ATR). Ciktiya sekil turu (ikili dip / TOBO / ucgen) dokumu eklendi.
3. **IN1 gevsetme:** ikinci dip, 5-40 mum gerideki HER onayli dip pivotuyla eslenir; kosullari (>= 0,2 ATR daha dusuk, RSI +3 ve ilk dip < 35, MACD hist. yuksek, arada tepe pivotu) saglayan en yakin alinir. Seviye ve hacim teyidi kaldirildi; ust ZD, fonlama vetosu, maliyet tabani kaldi. **Kapatma kurali (onceden yazildi):** Tur 2'de 1h + 4h toplam islem < 50 ise IN1 tumuyle kapanir, baska gevsetme yapilmaz (ozet.md bu satiri otomatik yazar).
4. **MF1:** hacim ve ust ZD teyidi cikarildi (`UYGULANAN["MF1"]` = seviye, fonlama, maliyet).
5. **MF1 seviye ve hedef:** seviye formasyonun ilk mumundan onceki degerle olculur (yutan t-2, cekic t-1, yildiz t-3). 1d'de "onceki gun dibi" listeden cikti (pwl, vwap, kendi pivot kaldi). Delme siniri: dip seviyenin en cok 1 ATR altinda. Hedef = en yakin karsi seviye ile giris + 3R'den yakin olan (3R sabit, taranmaz; karsi seviye yoksa 3R); rr >= 1,5 kaldi. Ciktiya seviye turu dokumu eklendi.
6. **Olcum:** (a) Rastgele taban: her gercek islem icin ayni cift, yon ve takvim yilindan 200 rastgele giris; z = fark / sqrt(se_gercek^2 + se_rastgele^2), 50 islem altinda "yetersiz". se_rastgele = havuz std / sqrt(gercek islem sayisi) (temkinli secim). Gercek ve rastgele girislerde ilk 250 mum yok. (b) Ust ZD'de EMA'si hazir olmayan durum "gecersiz" (filtreden gecmez). (c) Simulasyon: fonlama cikis mumunun kapanisina kadar sayilir; giris acilisinda risk/giris < %0,6 ise islem yok (maliyet teyidi acikken); tutma penceresinde mum boslugu ya da (stop/hedef olmadan) veri bitip zaman stopuna ulasilamazsa islem sayilmaz.

Yorum notlari: MF1 hedefinde karsi seviye yoksa eski kod islem acmazdi, simdi 3R hedefi kullanilir (maddenin "yakin olan" ifadesinin dogrudan sonucu). Rastgele tabanda stop/hedef mesafesi gercek islemden ATR cinsinden kopyalanir.
