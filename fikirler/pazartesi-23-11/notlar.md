# Orkestratör devri (21.11.2026) — Pazartesi 23.11 15:00 TSİ gündemi ve açık sorular

Kaynak: sselimgenc-oss/SG-Orkestra-Sefi (silinmeden önce kopyalandı). Yalnız bilgi; kullanıcı onayı olmadan uygulanmaz.

## Pazartesi gündemi
1. X algo fikirleri (`x-algo-fikirleri.md`): ML'yi ilgilendirenleri özetle, hangilerinin başlatılacağını kullanıcıya sor.
2. Bu klasördeki 3 PDF: bizde olmayan ve ML'ye yarayacak fikirler, sade tablo.
3. Kararlar (21.11 kullanıcı): kâğıt kaldıraç 3x kalır; S1 stop bandı 2,0 ATR kalır.
4. Canlı sonrası fikir: aşağıda (a).

## (a) Canlı sonrası fikir (yalnız konuşma)
ML+CT'yi izometrik 3D ofis gibi oyunlaştırıp YouTube canlı yayını. Şartlar: önce birkaç ay canlı kâr kanıtı; pozisyonlar gecikmeli gösterilir; yatırım tavsiyesi gibi görünmemeli; anahtar/sunucu bilgisi ekranda olmamalı; gelir reklam/üyelik/bağış.

## (b) Canlı öncesi açık sorular
| No | Soru |
|---|---|
| K1 | Sunucu konumu / yasal durum. CT notu (binance-arastirma.md): Binance vadeli Hollanda'da kapalı; Amsterdam sunucu IP'si canlıda 451 ile reddedilebilir — canlı öncesi sunucu bölgesi doğrulanmalı |
| K2 | Hesap ülke kaydı, KYC, TradFi sözleşmesi |
| K3 | 1.500 $ tavan: CT alt hesabı mı, toplam mı? |
| K4 | İlk canlı tavanı (öneri 100–150 $) |
| K6 | BNB ile ücret indirimi |
| — | "Durdur" tanımı: yalnız yeni giriş mi, açık pozisyonlar da mı? |
| — | Repoların private yapılması |

## (a) ek — 21.11 sohbet notu (yalnız fikir, iş yok)
- Görsel hedef: izometrik ofis/plaza ya da strateji oyunu havasında (köy/üs kurma türü) ÖZGÜN çizim; mevcut oyunların karakter/çizimleri kopyalanmaz.
- Yayın: YouTube canlı, 09:00–24:00 TSİ; yayın sunucusu/OBS botla tamamen ayrı (yayın çökse bot etkilenmez).
- Veri eşlemesi: kol = bina/ekip, açık pozisyon = çalışan masa, kasa = hazine, risk kademesi = surlar, gece eğitimi = laboratuvar, reddedilen sinyal = kapıdan dönen. Kaynak: canli-durum (durum.json) — salt okuma.
- Örnek: "ETRE v2" ofis görünümü (v3'te sade panoya dönmüş — bakım yükü/asıl işi gölgeleme uyarısı).
- Sıra: önce kâğıt → küçük canlı kâr kanıtı (birkaç ay) → basit 2D/izometrik ofis ekranı + kısa videolarla ilgi ölçümü → tam oyun görseli + günlük yayın.
- KULLANICI KARARI (21.11): Oyun/ofis görseli ÇOK SONRA ve ayrı proje; tek amaç YouTube geliri. Gerekçe: önceki bir projede ofis görsellerini düzenlemek asıl işi gölgeledi ve proje başarısız oldu. Şimdilik yalnız sade pano.

## KULLANICI KARARLARI (22.11 akşam, Fable görüşü okunduktan sonra)
| Madde | Karar |
|---|---|
| a | Kâğıt kaldıraç 3x kalır; S1 stop bandı 2,0 kalır, 2 hafta ölçülür sonra karar |
| b | (23.11 DEĞİŞTİ) Kilit ZİRVEDEN DEĞİL ANA PARADAN: kasa ana paranın %15 altına inince (kâğıt 1.000 $ → 850 $) yeni giriş kilitlenir; kâğıtta da açık; açık pozisyonlar kalır, yalnız kullanıcı açar; başlangıç −%20 kuralı ikinci emniyet olarak kalır |
| c | Canlıda HEPSİ (kripto + hisse + emtia). TradFi için kod değişikliği gerekli (config contract_types + broker extract_all_rules); sembol adları sunucuda doğrulanacak |
| d | Canlı kasa tavanı 2.000 $ (toplam vadeli cüzdan, sonradan eklenenler dahil) — koddaki kilitli 1.500 $ sınırı kullanıcı kararıyla 2.000 $ olacak |
| e | İlk canlı kasa en az 1.000 $, en çok 2.000 $ (kullanıcı: riskleri biliyorum) |
| f | BNB ile ücret indirimi: hayır (şimdilik) |
| g | İki komut: "Durdur" = yalnız yeni girişler durur; "Hepsini kapat" = ayrı komut, onay sorar |
| h | Repolar canlıdan önce private; sunucuya yalnız okuma yetkili anahtar; otomatik güncelleme yeniden test edilir |
| ek | Hafta sonu hisse büyüklük tavanı: gerek yok (kullanıcı: riskleri biliyorum) |
Uygulama: pazartesi 15:00 TSİ sonrası, kullanıcı "okey" deyince.

## PAZARTESİ İLK İŞ (22.11 gece eklendi)
Telegram: "HYPE, BCH, 1000SHIB için fiyat gelmiyor" uyarısı. Muhtemelen yanlış alarm:
sağlık kontrolü fiyatı yalnız engine.base.json'daki 10 coinde arıyor (scripts/health_run.py:404 market_pairs),
kâğıt bot 44 enstrümanla çalışıyor (health.py:690 _c_open_price).
1) Kullanıcı sunucuda teyit eder:
   sudo sqlite3 -readonly /home/trader/SG-Github-AB-proje/trader/var/market.sqlite "SELECT pair, datetime(MAX(open_ms)/1000,'unixepoch') FROM bars WHERE kind='last' AND tf='1m' AND pair IN ('HYPE/USDT','BCH/USDT','1000SHIB/USDT','BTC/USDT') GROUP BY pair;"
2) Düzeltme: açık pozisyon çiftleri doğrudan DB'den sorgulansın (seans kapalı hisseler yine uyarı vermesin). Test önce.
3) Asıl eksik: genel "1m mum bayat" kontrolü (health.py ~664 market_bars) de yalnız 10 coini izliyor; diğer 34 enstrümanın
   fiyatı kesilse alarm gelmez. Düzeltme 44'ün hepsini kapsasın; hisse/emtia seans dışındayken uyarı vermesin (session_tag).
4) 23.11 sabah Telegram: "Açık işlemlerin kâr/zararı panelle tutmuyor". canli-durum 09:05Z: 8 açık pozisyonun hepsinde mark var,
   mutabakat 10:34 TSİ "geçti". Motor 07:34Z (10:34 TSİ, oto-güncelleme) yeniden başlamış; ilk dakikalarda mark yok -> geçici uyarı şüphesi.
   Kontrol: iki uyarı da yeniden başlatmaya denk mi? health _c_open_price'ta mutabakat'taki _yeni_basladi benzeri susturma yok.

## KARARLAR (23.11 öğleden sonra)
- d uygulandı: canlı kasa tavanı 2000 $ (85a5aa9). b uygulandı: ana para kilidi %15, Telegram /devam ile açılır, yeniden silahlanma kalıcı (e952096).
- TON kâğıttan çıkarıldı (Binance SETTLING), evren hariç listesinde.
- Repo GİZLİ yapıldı (kullanıcı). oto_guncelle GitHub token desteği (c3500fa); kullanıcı sunucuda /etc/trader-github-token (fine-grained, yalnız Actions:read) oluşturacak; bir kez elle kurulum.
- CANLI = KÂĞIT BİREBİR (c genişledi): price_action_lab_ml + 32 kol + ML filtresi, veto kapalı, 43 enstrüman (kripto+hisse+emtia), aynı kümeler/flat_bar_guard.
  - Risk sınırları kâğıtla aynı: açık %24 / aynı yön %16 / günlük %8 (yalnız canlıya ayrı sınır; HARD_LIMITS testnet/geri test için dokunulmaz).
  - İşlem başına risk %1 (kâğıtla aynı) — risk kademe üst sınırı buna göre yükseltilecek.
  - Günlük zarar kuralı kâğıttaki gibi (açık risk sayılmaz).
  - Çıkış kuralları (başa baş stop + kısmi kapama) canlı borsa için de yazılacak; canlıdan önce prova.
  - ML modeli: canlı, kâğıdın model klasörünü salt-okur (öneri, teknik).
- h GERİ ALINDI (23.11): gizli repoda Actions kotası doldu (eski CT reposu tüketmiş), CI başlamıyordu. Repo canlıya kadar PUBLIC; canlıdan hemen önce gizli + CI maliyet kararı. Sunucudaki /etc/trader-github-token kalıyor.
- Arşiv taraması (23.11): HİÇBİR klasör atlanmaz. Scalp/Day Trade ileride açılacak kısa vadeli kollar için; Diğer ve İlgi Çekici klasörlerinden alışılmadık fikirler bekleniyor (kart_batch --genis, ilginçlik puanı).

## MADDE 2 KARARI (23.11)
- Fable'ın 7 maddesi: 1 yön sınırı, 6 basit rakip kıyası, 7 gecikme/masraf testi, 8 sıra karıştırma, 9 canlı şartları, 10 filtrede yön denetimi, 13 v2 paketini aç (fikirler/pazartesi-23-11/madde2_ml_tablo.md).
- + "ÜST LİG" HATTI (kullanıcı: es geçilmez). DÜZELTME 23.11: GÖLGE YOK — kâğıtta her şey açık ve işlemi etkiler; yeni kollar kâğıtta gerçek işlem açar ve canlı=kâğıt paritesiyle canlıda da hazır durur (ayrı karne, önceden yazılı tut/kaldır eşikleri):
  1) Veri toplama hemen: haber akışı (21.11'de silinen toplayıcı YENİDEN AÇILIR — karar girdisi değil, yalnız kayıt), fonlama, açık pozisyon, long/short oranı.
  2) LLM haber okuyucu (gölge): haber → olumlu/olumsuz/önemsiz, kayıt; haftalar sonra fiyatla ölç.
  3) Derin öğrenme fiyat verisinden (milyonlarca mum): yön/oynaklık tahmini → filtreye özellik, gölgede ölç.
  4) YZ ajanı yorumcu: günlük işlem incelemesi/rapor, işlem yetkisi yok.
- Not: LLM veto 19-20.11'de kullanıcı kararıyla kaldırılmıştı ("veto nedir, kaldır"), kanıt nedeniyle değil. LLM zaten sistemde: işlem notu + ders + M1 "yapay zekâ adayı" kolu (aylık LLM bütçesi config/budget.json).

## MADDE 3 KARARI (23.11)
- Seçilen (madde3_strateji_tablo.md): 2 korelasyon/tek bahis, 3 kayıp serisi freni, 4 toplam büyüklük tavanı, 12 kayıp kümeleri raporu. 14 göreceli güç bir sonraki tura.
## 1. TUR UYGULAMA SIRASI
- Aşama A (botu değiştirmez, ölçer): basit rakip kıyası, gecikme/masraf/mum kaydırma, sıra karıştırma + en iyi N çıkar, canlı şartları, filtrede yön denetimi, kayıp kümeleri raporu.
- Aşama B (botu değiştirir; eşikler testten ÖNCE kilitlenir, kullanıcı onaylar): yön sınırı, v2 özellik paketi, korelasyon sınırı, kayıp freni, toplam tavan. Holdout okunmaz.

## ÇALIŞMA KURALI (23.11 akşam, kullanıcı)
- Yeni işe başlanabilir ama HER İŞ için önce kullanıcıdan onay alınır. Tek tek, ne yapılacağı sade anlatılarak.
- BEKLEYEN (kullanıcı eve gidince): ders sistemi 0 ders üretmiş (gunluk_ozet: aktif/yeni ders 0). Şüphe: /etc/trader-lesson.env ANTHROPIC_API_KEY_LESSON boş. Kontrol: awk ile anahtar dolu/boş + journalctl -u trader-lesson -u trader-notes --since -2d.
