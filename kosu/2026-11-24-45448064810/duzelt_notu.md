Altı maddenin hepsini uyguladım, hiçbiri atlanmadı. pytest 41 test geçti, skip/xfail yok. Kilitli dönemi çalıştırmadım, git komutu kullanmadım.

**Kod denetimi:** Sonuçları geçersiz kılan bir hata yazılmamıştı. Küçük kusurlar madde 2, 3 ve 6 içinde düzeldi.

1. **Kapatma:** `calistir.py`'ye izinli zaman dilimi tablosu ekledim: MF1 4h/1d, GF1 1h/4h/1d, IN1 1h/4h. Kapatılan hücreler hesaplanmıyor. `kol_sinyalleri.py`'deki 15m dallarını sildim. `--tf` varsayılanı artık 1h,4h,1d.
2. **GF1 stop:** İşlem stopu boyun − 1 ATR oldu ve "risk > 3 ATR" şartı kalktı. Eski formasyon dibi − 0,2 ATR yalnız kurulum iptal seviyesi olarak kaldı. B girişi geri testi `low <= boyun` ile ölçülüyor. Çıktıya şekil türü dökümü ekledim.
3. **IN1:** İkinci dip, 5-40 mum gerideki her onaylı dip pivotuyla eşleşiyor; koşulu sağlayan en yakın alınıyor. Seviye ve hacim teyitlerini çıkardım. Kapatma kuralını (1h+4h toplamı 50 işlemin altındaysa IN1 kapanır) tasarım dosyasına yazdım; `ozet.md` de bu satırı otomatik üretiyor.
4. **MF1 teyitleri:** Hacim ve üst ZD teyidini çıkardım.
5. **MF1 seviye ve hedef:** Seviye formasyonun ilk mumundan önceki değerle ölçülüyor (yutan t−2, çekiç t−1, yıldız t−3). 1d'de önceki gün dibi listeden çıktı. Delme en çok 1 ATR. Hedef, en yakın karşı seviye ile giriş + 3R'den yakın olan. Seviye türü dökümü eklendi.
6. **Ölçüm:**
   - Rastgele taban işlem başına 200 çekiliş; aynı çift, yön ve takvim yılı.
   - Gerçek ve rastgele girişlerde ilk 250 mum yok.
   - Gerçek tarafın standart hatası kaydediliyor, z raporlanıyor; 50 işlemin altında "yetersiz".
   - EMA'sı hazır olmayan üst ZD "geçersiz" sayılıyor.
   - Fonlama çıkış mumunun kapanışına kadar sayılıyor.
   - Giriş açılışında risk %0,6'nın altındaysa işlem alınmıyor.
   - Tutma penceresinde mum boşluğu varsa ya da veri bitip zaman stopuna ulaşılamazsa işlem sayılmıyor.

**Testler:** Bozulanları güncelledim ve yeni davranışlar için test ekledim. Ayrıca `tasarim_v2.md` sonuna "## Tur 2 değişiklikleri" bölümünü ekledim.

**Duman koşusu:** 3 çift (BTC, ETH, SOL), 1h, 2024-01..04 hatasız bitti. GF1 17 işlem verdi (ort −0,41 R), IN1 2 işlem. MF1 1h'de kapalı olduğu için hiç çıktı üretmedi; bu yüzden 4h/1d'yi de ayrıca denedim, o da hatasız çalıştı. Sonuçlar `/tmp/duman_tur2` ve `/tmp/duman_tur2b` altında. Bu kadar az işlemle yorum çıkarılmaz.

**Yorum gerektiren noktalar:**
- MF1 hedefinde karşı seviye yoksa eski kod işlem açmıyordu. "Yakın olan" ifadesini aynen uyguladığım için artık giriş + 3R hedefi kullanılıyor.
- z hesabında rastgele tarafın standart hatasını havuz standart sapması / √(gerçek işlem sayısı) aldım (temkinli). Bunu tasarım dosyasına da yazdım.