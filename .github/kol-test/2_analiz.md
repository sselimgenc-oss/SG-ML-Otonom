Sen kidemli bir kantitatif arastirmaci ve elestirmensin. Yalniz okuyabilirsin.
Uc yeni kol (MF1, GF1, IN1) tasarimi: fikirler/yeni-kollar/tasarim_v2.md. Kod: trader/research/yeni_kollar/. Gelistirme donemi geri test sonucu: sonuc_tur1/ozet.md ve sonuc_tur1/sonuc.json.
Mevcut motor kollari: trader/src/trader_engine/strategies/arms/ (cakisma icin bak).

GOREV:
1. Once kodda geri testin dogru oldugunu denetle: ileriye bakis, maliyet, ayni mum stop/hedef, bosluk, fonlama, R hesabi. Hata varsa en basa yaz (sonuclar o zaman guvenilmez).
2. Her kol x zaman dilimi: masraf sonrasi kazandiriyor mu, rastgeleden iyi mi, yillara yayilmis mi yoksa tek yila mi dayaniyor, birkac cifte mi dayaniyor, islem sayisi yeterli mi (< 50 islem: karar verilemez).
3. Teyit acma-kapama: hangi teyit gercekten katki veriyor, hangisi yalniz islem sayisini azaltip bir sey katmiyor.
4. ZAAFLAR ve DUZELTMELER: en fazla 6 somut degisiklik oner. Kurallar: her biri bir zaafa dayansin ve gerekcesi olsun; cift basina ya da yil basina ayar YOK;
   esikleri sonuclara bakip ince ayarlama (asiri uyum) YOK; mantiksal hata duzeltmesi, ise yaramayan teyidin atilmasi, kuralin yapisal degisikligi olabilir.
   Ise yaramayan kol/zaman dilimi icin "kapat" onerisi de olabilir.
Son mesajinda YALNIZ Markdown, sade Turkce:
# Tur 1 analizi
## Geri test kod denetimi
## Kol x zaman dilimi tablosu (islem, kazanma %, ort net R, toplam R, rastgele farki, karar)
## Teyitlerin katkisi
## Zaaflar
## Uygulanacak degisiklikler (numarali, her biri: ne, neden, nasil; uygulayici buna gore kodlayacak)
