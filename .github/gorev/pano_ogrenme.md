Sen kidemli bir Python/JS gelistiricisin. Proje: "ML Otonom" (calisma dizini depo koku; pano: trader/src/trader_panel/static/panel.js, veri: trader/src/trader_core/panel_data.py
ve panoyu besleyen betik; testler `cd trader && python -m pytest ...`).
SORUN: ML filtreleri silinince (commit dadb70a) panodaki "Makine ogrenmesi" karti da kalkti; yerine bir sey konmadi. Kullanici panoda botun OGRENMESINI gormek istiyor.
GOREV: OZET sekmesine "Ogrenme" karti ve OGRENME sekmesine ayrintili tablo ekle (mevcut "Ders ogrenmesi" ve kucultme kartlarini koru, cift gosterme):
1. TUM kollar (kural kollari, M1, DL1, HB1 ve ileride eklenecek formasyon kimlikleri dahil; kol listesini ayardan/defterden dinamik al) icin kol x ZD satirlari:
   kapanan islem, net R, kazanma %, risk carpani (kol kucultme), durum (acik / kucultulmus / karantina), son ders degisikligi (varsa).
   Ozet kartta: kac kol acik / kucultulmus / karantinada, en iyi 3 ve en kotu 3 kol x ZD (net R).
2. Model kollari (M1, DL1 4 ZD): son egitim zamani (TSI), paket yasi, bugun aday / giris sayisi. Veri kaynagini koddan bul (paket dosyalari, status, defter);
   bulunamayan alan "bilinmiyor" yazsin, uydurma.
Sade Turkce etiketler, mevcut tablo siralama yapisini kullan (satirlarda ham deger v). Telefon ve PC uyumlu.
KURALLAR: kagit = canli; mevcut testleri bozma, yeni alanlar icin test ekle; skip/xfail yok; git komutu yok; hash sabitlemeli test etkilenirse gercek degerden guncelle
("24.11 kullanici karari: pano ogrenme karti"). Ilgili testleri ve sonunda tam takimi gecir. Son mesaj: kisa Turkce ne eklendi, hangi veri nereden, test sonucu.
