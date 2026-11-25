# Kutuphane incelemesi

## Sonuc (birlestirilebilir mi)

**Henuz birlestirilmemeli.** Kodda engelleyici bir hata gormedim, ama birlesik dalin son hali (089838a) icin kayitli bir test sonucu yok. Inceleme salt okuma idi; testleri ben calistirmadim ve dort kutuphane dosyasindaki dedektorleri satir satir okumadim.

Bes kontrolun durumu:

- **Ileriye bakis:** sorun gormedim. Ortak altyapi yalniz son kapanmis mumu okuyor, pivotlar iki mum gecikmeyle onaylaniyor. Supheli kaliplari aradim (negatif kaydirma, ortalanmis pencere, geriye doldurma), cikmadi. Her ailede "gelecek mumlar degisince karar degismiyor" ve "pencere boyu sonucu degistirmiyor" testleri var.
- **Kagit = canli:** uyumlu. Iki ayar dosyasinda kol listesi (288 kol), kol tavanlari, aile tavanlari, toplam tavan (36), cikis kipleri ve risk ayarlari birebir ayni.
- **Hepsi acik, tam boy:** uyumlu. Tum formasyon x ZD kollari listede, on deger dosyasi bos (`{}`); bos dosyada hicbir kol kucuk ya da kapali baslamiyor.
- **6/3 kapasite:** formasyon x ZD basina 3 ve aile basina 6 uygulanmis, toplam tavan 36. PA tarafinda yorum farki var (asagida madde 2).
- **Ogrenme formasyon x ZD bazinda:** uyumlu. Kimlik `MF1-YUTAN@1h` biciminde; kol kapatma, karantina, kucultme ve defter bu kimlikle calisiyor. Aile ortalamasi ayni formasyonun diger ZD'lerinden geliyor, ana kollarla (ornegin `B1` ile `B1-BOLGE`) karismiyor.

## Duzeltilmesi gerekenler

1. **Birlesik dal icin tam test kosusu eksik (engelleyici).** `fikirler/gorev/` altindaki uc sonuc ayri gorev dallarina ait:
   - 45509533088: 8606 gecti.
   - 45509536880: 8526 gecti.
   - 45509541315 (PA varyantlari): **9 basarisiz** (modul envanteri: `s1v.py` vb. listede yok).

   Envanter sonradan 6e6186a ile duzeltilmis gorunuyor. Son birlestirme commit'i de 12 test dosyasini degistirmis, ama bunlardan sonra kosulmus bir sonuc dosyasi yok. Birlesik dalda tam kosu yapilip sonucu eklenmeli.

2. **PA aile tavani kullaniciya teyit ettirilmeli.** Karar "ayri PA ailesi varsa o da 6" diyor. Kodda PA tek aile degil: `PA2` ile yedi varyant ailesi (`T1`, `R1`, `TF1`, `B1`, `H2`, `S1`, `F1`) ayri ayri 6 aliyor. PA tarafi boylece kagit uzerinde 48 pozisyona kadar cikabiliyor; fiilen toplam 36 tavani sinirliyor. Ana kollar (`T1` vb.) aile sayimina girmiyor, eski 6 tavanlariyla devam ediyor. Niyet "tum PA icin 6" ise tek ortak aile tavani gerekir.

3. **Aile tavani giris kapisinda uctan uca test edilmiyor (kucuk).** Testler yalniz saf yardimcilari (`family_count`, `family_full`) ve ayar degerlerini dogruluyor. Gercek giris kapisinda "ailede 6 acik pozisyon varken 7. reddedilir, baska aileden aday alinir" senaryosu yok. Bir test eklenmeli.