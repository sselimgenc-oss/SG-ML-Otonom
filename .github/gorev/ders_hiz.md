Sen kidemli bir kantitatif arastirmaci ve kod denetcisisin. Yalniz okuyabilirsin. Proje: "ML Otonom" (kod trader/; kagit = canli).
SORUN (kullanici): panoda "Ders karti: Acik, veri birikiyor (0/10)", hic ders uygulanmadi. 23 kapanmis islem ~40 kol x ZD'ye dagiliyor; ders esikleri
(trader/config/lesson.json, trader_core/lesson.py: min_affected 8, min_distinct_days 4, min_gap_r 0.5, min_z 1.64, shrink_n 10...) hicbir kolda dolmuyor.
Yakinda formasyon kutuphanesiyle kol x ZD sayisi 166+ olacak (kullanici karari: her formasyon kendi kimligiyle ogrenir).
Ayrica panodaki "Kademeli kucultme" kartinda B1@1h, H2@15m, M1@1h gibi kollar "%50 boyut · son 5: — R" gosteriyor (son 5 net R yok ama kucultulmus).
GOREV (kodu okuyarak, kanitla):
1. Ders sistemi "alinsaydi" (counterfactual / alinmayan_sonuc) sonuclarini veri olarak kullaniyor mu? Kullanmiyorsa eklemek mumkun mu, riskleri (sahte veri, cift sayim, secim yanliligi).
2. Dersin hizlanmasi icin secenekler: (a) alinsaydi verisi, (b) esik dusurme, (c) havuzlama (ayni formasyon farkli ZD / ayni aile verisini birlikte degerlendirme), (d) baska.
   Her biri icin beklenen hiz kazanci ve asiri uyum riski. TEK bir oneri ver (birlesim olabilir) ve uygulayici icin kesin talimat yaz.
3. Kucultme kartindaki "%50 boyut, son 5: —" neden: kucultme hangi veriye gore karar veriyor (trader_core/kol_kucultme.py, panel_pano.kucultme_view)? Hata mi, gosterim eksigi mi?
Son mesajinda YALNIZ Markdown, sade Turkce, kisa (kullanici teknik degil): # Ders neden ogrenmiyor / ## Neden / ## Secenekler (tablo) / ## Onerim / ## Uygulama talimati / ## Kucultme karti
