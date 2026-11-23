# Madde 2: Makine öğrenmesi ve algoritmik işlem fikirleri

**Kaynaklar (yalnız bunlar):** sizin X fikirleriniz ve 3 PDF araştırma dosyası (35 kart), Jansen, Giller ve Gizlyk kitapları (24 kart), 43 kitaplık ML/Algo arşivi (16 kitaptan 41 güçlü kart + 26 adet 3 puanlık risk/doğrulama kartı). Strateji arşivi bu tabloda sayılmadı; o Madde 3'te.

**"Kaç kaynakta" nasıl okunur:** X/PDF tek kaynak, her kitap bir kaynak sayıldı. Sayılar küçük, çünkü bu maddede toplam kaynak az.

**"Bizde var mı"** koda bakılarak dolduruldu.

## A. Açığımızı kapatır (para kaybını önler)

| # | Fikir | Ne işe yarar (1 basit cümle) | Kaç kaynakta | Bizde var mı | Emek | Puan |
|---|---|---|---|---|---|---|
| 1 | Yön karnesi + aynı yön sınırını sıkılaştır | 41/47 short gibi tek yöne yığılmayı görünür kılar ve frenler. | 2 (X/PDF + 1 kitap) | Kısmen. Sınır var ama kâğıtta %16; 16 aynı yönlü işleme izin veriyor. | az | 5 |
| 2 | Birlikte hareket eden pozisyonları tek bahis say | Farklı görünen 10 pozisyonun tek büyük bahis olmasını engeller. | 6 (X/PDF, Jansen + 4 kitap) | Kısmen. Sabit grup sınırı var; canlı benzerlik ölçümü yok. | orta | 5 |
| 3 | Sert hareket döneminde stop ve boyutu küçült | Ani sıçramaların sıklaştığı günlerde beklenenden büyük kaybı azaltır. | 3 (Giller + 2 kitap) | Kısmen. "Volatil" etiketi girişi atlatabiliyor; boyut küçültme yok. | orta | 3 |
| 4 | Pozisyon boyutunu filtre güvenine göre ayarla (yarım ölçek) | Emin olunmayan işleme daha az para koyar. | 4 (Jansen, Giller + 2 kitap) | Kısmen. Sabit %1; ölçekleme yok. 47 işlemle erken. | orta | 3 |
| 5 | İşlem büyüdükçe artan masraf modeli ve büyüklük tavanı | Az işlem gören varlıkta büyük emirle fiyatı kendi aleyhimize itmeyi önler. | 2 kitap | Yok. Masraf sabit oranla hesaplanıyor. | orta | 2 |

## B. Kendimizi kandırmayı önler (sadece ölçer, botu değiştirmez)

| # | Fikir | Ne işe yarar (1 basit cümle) | Kaç kaynakta | Bizde var mı | Emek | Puan |
|---|---|---|---|---|---|---|
| 6 | Basit rakiplerle kıyas (rastgele giriş, hep short, al-ve-tut) | Kârın kurallardan mı, düşen piyasada short olmaktan mı geldiğini gösterir. | 3 (X/PDF, Giller + 1 kitap) | Kısmen. Rastgele giriş aracı yazılmış ama hiçbir rapora bağlı değil. | az | 5 |
| 7 | Gecikme ve masraf dayanıklılık testi | Kârın 1-2 mum geç girişle ya da biraz pahalı işlemle eriyip erimediğini gösterir. | 6 (X/PDF, Jansen + 4 kitap) | Kısmen. Filtre kapısında masraf stresi var; geç giriş testi yok. | az | 4 |
| 8 | İşlem sırasını karıştırarak en kötü düşüşü ölç | Şans kötü giderse kasanın ne kadar eriyeceğini gösterir. | 2 (X/PDF + 1 kitap) | Kısmen. Yeniden örnekleme yalnız getiri kalitesi için; düşüş dağılımı yok. | az | 4 |
| 9 | Canlıya geçiş şartları + iki varyantı eşleştirerek kıyaslama | Az sayıda şanslı işleme bakıp erken karar vermeyi engeller. | 4 (X/PDF + 3 kitap) | Kısmen. Kapı ve güven aralığı var; eşleştirilmiş kıyas yok. | az | 4 |
| 10 | Filtrede "yön" bilgisinin ağırlığını denetle | Filtrenin long'ları sırf long olduğu için eleyip elemediğini gösterir. | 1 (Jansen) | Kısmen. Özellik önemi hesabı var; yön odaklı rapor yok. | az | 4 |
| 11 | Deneme bütçesi + "komşu ayarlar da iyi mi" kontrolü | Çok deneyip şans eseri iyi görüneni seçmeyi önler. | 9 (X/PDF, Jansen, Gizlyk + 6 kitap) | Kısmen. Deneme kaydı ve düzeltme var; üst sınır ve komşu ayar raporu yok. | az | 3 |
| 12 | Kol karnesini genişlet (ortalama kazanç/kayıp, likit/az likit ayrımı) | "Çok kazanıyor ama az kazandırıyor" tuzağını yakalar. | 1 (X/PDF, 3 kart) | Kısmen. Kol, rejim, parite, yön dökümü var; güven aralığı ve likidite ayrımı yok. | az | 3 |

## C. Botu geliştirebilir (daha çok kazanç)

| # | Fikir | Ne işe yarar (1 basit cümle) | Kaç kaynakta | Bizde var mı | Emek | Puan |
|---|---|---|---|---|---|---|
| 13 | Hazır duran yeni özellik paketini (v2) aç, eskisiyle yan yana ölç | Hacim, BTC durumu ve fonlama bilgisini filtreye verir; long tarafını canlandırabilir. | 3 (X/PDF + 2 kitap) | Kısmen. Kod ve testleri hazır; kâğıt ayarında kapalı. Long/short oranı yok. | az | 4 |
| 14 | Önceki hafta ve ay tepe-dip seviyelerine uzaklık | Kırılım kollarına herkesin baktığı seviyeleri bilgi olarak verir. | 2 (X/PDF + 1 kitap) | Kısmen. v2'de son 20/50 mum tepe-dip var; takvim seviyeleri yok. | orta | 3 |
| 15 | Düşüşte oynaklığın daha çok arttığını ölçen özellik | Filtreye düşüş ile yükselişin farklı davrandığını öğretir. | 2 (Giller + 1 kitap) | Yok. | az | 3 |

## Zaten var — tekrar yapma

Bu kaynakların önerip kodda bulunanlar: boşluklu ileri-yürüyen test, deneme sayısına göre düzeltilmiş başarı ölçüsü, filtre puanı ile gerçek sonucun sıra uyumu, üçlü bariyer etiketi, beklenen-gerçekleşen sapma izleyicisi, alınmayan sinyallerin sanal takibi, eksik mum onarımı, borsa ile pozisyon eşitleme, likidasyon güvenlik payı, acil durdurma.

## Derin öğrenme ve LLM neden şimdi değil

- **Veri az.** 47 işlem var. Derin ağlar (CNN, Transformer) binlerce örnek ister; bu kadar veride ezberler. Kaynaktaki kart da 1 puan aldı.
- **Pekiştirmeli öğrenme ve hazır "zaman serisi temel modeli":** masraf eklenince kâr eriyor; kaynakların kendisi de bunu söylüyor (1 puan).
- **Haber okuyan LLM ve çok ajanlı LLM sistemi:** 0-1 puan. Kararı denetlenemiyor, her çağrı para, ve haber/duygu verisini 21 Kasım'da zaten kaldırdınız.
- **Emir defterinden yön tahmini:** 4 kitapta 7 kart, hepsi 1-3 puan. Verisi bizde yok; kısa vadeli kollar kurulursa yeniden bakılır.
- Şu anki ağaç tabanlı filtre bu veri boyutu için doğru araç. Önce onun girdilerini (satır 13) ve dürüstlüğünü (satır 10) düzeltmek daha çok kazandırır.

## Öneri

1. Önce **1** (yön sınırı) ve **6** (basit rakip kıyası): biri bilinen açığı kapatır, diğeri kârın gerçek olup olmadığını söyler; ikisi de az emek.
2. Sonra **7, 8, 9** ölçümleri ve **10, 13**: botu değiştirmeden dayanıklılığı ölçer, hazır paketi açarak long tarafını dener.
3. **2** (korelasyon) bu maddenin en çok desteklenen fikri ama orta emek, ölçümlerden sonra; derin öğrenme ve LLM en az birkaç yüz işlem birikene kadar beklesin.
