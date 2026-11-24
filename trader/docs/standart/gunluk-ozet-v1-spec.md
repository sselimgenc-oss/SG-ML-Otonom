# ML günlük özet yayını (`ortak.gunluk_ozet.v1`) — belirtim (19 Kasım 2026)

Şema sahibi orkestratör: `SG-Orkestra-Sefi/standart/gunluk-ozet-v1.md`. ML yalnız **kâğıt** botun özetini yazar. Bu iş özeti yalnız raporlar; motor, kapı ve risk davranışı değişmez.

## Yayın
- Adres: mevcut pano Worker'ı, `https://trader-pano.sselimgenc-c18.workers.dev/gunluk_ozet_v1.json`. Sunucunun GitHub'a yazma yetkisi yok, bu yüzden ham GitHub adresi yerine bu adres kullanılır. Orkestratöre bildirilir.
- `/rejim.json` ile aynı kurallar geçerli: parolasız, yalnız `GET`/`HEAD`. Başlıklar: `Content-Type: application/json`, `Cache-Control: no-store`, `Access-Control-Allow-Origin: *`. Diğer yollar eskisi gibi parolalı kalır.
- Pano yayınıyla (trader-panel-publish, 5 dk) her turda yeniden üretilir. Bu, şemadaki "21:00 + isteğe bağlı saatlik" şartını karşılar. Üretim başarısız olursa yalnız uyarı yazılır; pano yayını sürer ve dosya o turda yer almaz.

## Alanlar
Şemadaki her alan yazılır. Bilinmeyen değer `null` olur, alan hiçbir zaman atlanmaz.
- `sema`: `"ortak.gunluk_ozet.v1"`; `proje`: `"ML"`; `mod`: `"kagit"`.
- `uretim`: ISO-8601 UTC, `Z` ile.
- `gun`: Europe/Istanbul yerel tarihi. Bütün `gun_*` sayımları o yerel gün içindir (00:00–24:00 TSİ).
- `kasa`:
  - `baslangic`: kâğıt başlangıç bakiyesi (paper yapılandırması).
  - `simdi`: başlangıç + gerçekleşen PnL. Gerçekleşmemiş PnL bilinmiyorsa dahil edilmez.
  - `gun_pnl`, `toplam_pnl`.
  - `zirveden_dusus_yuzde`: kapanmış işlemlerin kümülatif eğrisinde zirveden çukura en büyük düşüş, yüzde olarak.
- `islem`:
  - `gun_acilan`, `gun_kapanan`, `kazanan`, `kaybeden`: yalnız o gün kapananlar sayılır.
  - `acik_pozisyon`: şu anki açık pozisyon sayısı.
  - `alinmayan_sinyal`: o gün kâğıt defterine girmeyen adaylar (counterfactual/alınmayan sinyal kaydı). Kayıt yoksa `null`.
- `hesaplar`: kurulum başına (setup, örn. `PA1`, `M1`, `T1`) `{ad, gun_pnl, toplam_pnl, islem}`. `islem` toplam kapanmış işlem sayısıdır. Liste `toplam_pnl` değerine göre azalan sıradadır.
- `ogrenme`:
  - `aktif_ders`, `yeni_ders` (o gün eklenen), `emekli_ders` (o gün emekli edilen).
  - `filtre_aktif`: şema anahtarı korunur; ML filtreleri 24.11'de silindiği için her zaman `null` (kaynak yok).
- `rejim`: BTC/USDT 4h rejim etiketi, `rejim_yayini` ile aynı hesap.
- `drift_uyari`: drift izleyicisinde açık uyarı varsa `true`, yoksa `false`, kaynak yoksa `null`.
- `limitler`:
  - `gunluk_kayip_yuzde`, `kaldirac_tavan`: paper risk yapılandırmasından.
  - `durdu_mu`: risk kilidi ya da engel (blok) varsa `true`.
- `saglik`:
  - `son_nabiz`: sağlık işinin son başarılı koşusu.
  - `hata_sayisi_gun`: o gün WARN/CRIT sayısı. Kaynak yoksa `null`.
- `notlar`: en fazla 5 kısa madde. Örnek: "M1 modeli eski", "en iyi kurulum: X".

## Kurallar
- Gizli bilgi, anahtar, e-posta ve hesap numarası yazılmaz.
- Sayılar ondalık (USD) ve 2 basamağa yuvarlanır.
- Saf üretim fonksiyonu (ağsız) yazılır, ayrıca CLI: `--config-dir --env paper --out <yol>`. Çıktı atomik yazılır. Hata olursa sıfır olmayan çıkış verilir ve dosya yazılmaz.
- Holdout dönemi (2026-05-01 → 2026-11-01) ile ilgisi yoktur; yalnız canlı kâğıt kayıtları okunur.
- Donuk dosyalara dokunulmaz. Yeni bağımlılık eklenmez.
