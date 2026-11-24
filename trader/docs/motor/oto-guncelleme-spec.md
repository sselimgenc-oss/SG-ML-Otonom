# Sunucu otomatik güncelleme — belirtim (19 Kasım 2026, kullanıcı onaylı)

Kullanıcı şartları: (1) yalnız GitHub'daki otomatik testleri **yeşil** geçmiş commit kurulur; (2) her güncellemede Telegram'a hangi değişikliğin kurulduğu yazılır ve tek komutla eski sürüme dönülebilir.

## Birimler
- `deploy/oto_guncelle.sh` (root; kurulumdaki kök kopyadan çalışır: `/usr/local/lib/trader-root/current/deploy/oto_guncelle.sh`).
- `deploy/trader-oto-guncelle.service` (Type=oneshot, root) + `.timer` (`OnCalendar=*:0/5`, 5 dakikada bir; 24 Kasım kullanıcı kararı: sabit kurulum saati yok, yeşil commit en geç ~5 dk içinde kurulur). `trader-oto-simdi` zamanlayıcıyı beklemeden hemen çalıştırır. Kurulum sonrası korumalar (sessizlik, 20 dk öz-kontrol, 60 dk izleme/otomatik geri alma): `docs/sunucu-kurulum.md` → "Kurulum sonrası koruma".
- `deploy/trader-geri-al`, `deploy/trader-oto-ac` ve `deploy/trader-oto-simdi` → `install.sh` bunları `/usr/local/sbin/` altına root:root 0755 kurar.
- Durum dizini `/var/lib/trader-oto-guncelle/` (root, 0700): `gecmis.tsv` (`zaman<TAB>eski<TAB>yeni<TAB>sonuc`), `kilit` (flock).

## `oto_guncelle.sh` akışı
1. `flock` ile tek kopya. `/var/lib/trader-oto-guncelle/DURDUR` varsa çık (0).
2. **Canlı (gerçek para) koruması:** `systemctl is-enabled`/`is-active` ile adı `trader-engine-live` ile başlayan herhangi bir birim etkin ya da çalışıyorsa çık (0) ve günde bir kez Telegram: "Otomatik güncelleme canlı birim nedeniyle durdu."
3. Yeşil commit: `https://api.github.com/repos/sselimgenc-oss/SG-Github-AB-proje/actions/workflows/tests.yml/runs?branch=<BRANCH>&status=success&per_page=1` (kimlik doğrulamasız; `curl -fsS --max-time 20`; `User-Agent: trader-oto-guncelle`). JSON `python3 -c` ile ayrıştırılır; `workflow_runs[0].head_sha` (40 hex) yoksa çık (0).
4. Şu anki sürüm `/etc/trader-release` içindeki `COMMIT=`. Aynıysa çık (0).
5. Yeşil commit şu ankinin **atası** ise (eski) kurma, çık (0) — geri gitmez. (Kontrol `install.sh`'in kök klonunda `git merge-base --is-ancestor` ile; önce `install.sh`'in yaptığı gibi dal fetch edilir ya da kontrol kurulum betiğine bırakılır ve "eski" durumu ayrıca atlanır.)
6. Değişiklik listesi: kök klonda `git log --format=%s --no-merges <eski>..<yeni>` (en fazla 15 satır; fazlası "… ve N değişiklik daha").
7. `COMMIT=<yeni> bash /usr/local/lib/trader-root/current/deploy/install.sh` çalıştırılır (zaman aşımı 30 dk); çıktı `journal`a.
8. Başarı (çıkış 0 ve `/etc/trader-release` yeni commit): `gecmis.tsv`'ye satır, Telegram:
   ```
   [ML] Sunucu güncellendi: <eski7> → <yeni7>
   - <değişiklik 1>
   - ...
   Sorun olursa: trader-geri-al
   ```
9. Başarısızlık: `gecmis.tsv`'ye `basarisiz`, Telegram: `[ML] Güncelleme BAŞARISIZ (<yeni7>); <eski7> çalışmaya devam ediyor.` + `install.sh` çıktısının son 5 satırı (anahtar/parola maskelenir: `bot[0-9]+:[A-Za-z0-9_-]+`, `sk-ant-[A-Za-z0-9_-]+`). Aynı commit için bir daha denenmez (gecmis'te `basarisiz` varsa atla).
- Telegram gönderimi: `/etc/trader-telegram.env`'den `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID`; `curl --data-urlencode` ile `sendMessage`; token komut satırına değil `--config` stdin ile verilir (ps'te görünmesin). Dosya yoksa yalnız journal.

## `trader-geri-al`
- `gecmis.tsv`'deki son `basarili` satırın `eski` commit'ini kurar (`install.sh` ile), sonra `DURDUR` dosyasını oluşturur (otomatik güncelleme geri alınan sürümü tekrar kurmasın).
- `trader-geri-al --otomatik [--neden METIN]` (yalnız `trader-kurulum-gozcu` çağırır): hedef `kurulum.json`'daki `onceki` sürüm; bozuk commit `gecmis.tsv`'ye `basarisiz` yazılır (oto_guncelle bir daha denemez); `DURDUR` KONMAZ; tek Telegram mesajı nedenle birlikte gider.
- Telegram: `[ML] Geri alındı: <yeni7> → <eski7>. Otomatik güncelleme durduruldu; açmak için: trader-oto-ac`.
- Geçmiş yoksa açıklayıcı mesajla çıkış 1.

## `trader-oto-ac`
- `DURDUR` dosyasını siler, Telegram: `[ML] Otomatik güncelleme yeniden açıldı.`

## Mum kapanışı koruması
- Kurulum başlamadan hemen önce (tüm kontroller geçtikten sonra) UTC dakikası `dakika % 15 ∈ {14, 0, 1, 2}` ise (15 dk mum kapanışından 1 dk önce – 3 dk sonra; motor kararı kapanışta verir ve veri için en çok 120 sn bekler) betik `dakika % 15 == 3` olana dek uyur (en çok ~4 dk) ve sonra kurulur. Pencere dışında beklemez; kurulum gerekmiyorsa hiç beklemez.
- Test için: `OTO_SIMDI_DAKIKA`, `OTO_SIMDI_SANIYE` (UTC şimdi), `OTO_UYKU` (sleep komutu).

## install.sh
- Yeni birimleri ve iki komutu kurar; timer'ı etkinleştirir. Durum dizinini oluşturur (root, 0700).

## Testler (ağsız)
- `oto_guncelle.sh` için kabuk testleri: sahte `curl`, `systemctl`, `git`, `install.sh` ve `/etc/trader-release` yollarıyla (ortam değişkenleriyle geçersiz kılınabilir yollar): aynı commit → işlem yok; yeni yeşil → kurulum + Telegram metni; DURDUR → işlem yok; canlı birim → işlem yok; kurulum hatası → başarısız mesajı ve tekrar denememe; eski commit → işlem yok; maskeleme; mum kapanışı penceresinde ertelenir, dışında beklemez.
- `bash -n` ve (varsa) shellcheck temiz.
