# DD-12: Sunucuda yapılacaklar (adım adım)

Bu belge sunucu sahibi için. Her adımı sırayla yapın. Her adımın sonunda **"Kontrol"** satırındaki sonucu görmeden bir sonrakine geçmeyin. Komutlar sunucuda **root** olarak çalışır (DigitalOcean > droplet > **Access > Launch Droplet Console**).

**Bu adımlar gerçek para değildir.** Canlı (gerçek para) birimi kurulmaz, açılmaz. Testnet motoru bu adımlarda yalnız durdurulur ve tekrar başlatılır.

Yollar (kurulum betiğindeki gibi): kod `/home/trader/SG-Github-AB-proje/trader`, yapılandırma `config`, sanal ortam `.venv`.

---

## Adım 1: Kodu GitHub'a gönderin (sizin bilgisayarınızda)

1. Depoda DD-12 değişikliklerini commit edin. Commit mesajı örneği: `DD-12 WP-18: kapasite olcumu, M1 gece egitimi, evrenden cikan ciftler, kurulum`.
2. Commit'i GitHub'a gönderin (`git push`). Dal: `claude/charming-hawking-ab5w5q`.
3. Commit kodunu kopyalayın (40 karakter). Komut: `git rev-parse HEAD`. Bu kodu aşağıda `<KOD>` yerine yazacaksınız.

**Kontrol:** GitHub'da commit görünüyor ve kodu 40 karakter.

---

## Adım 2: Mevcut sürümü görün ve yedek alın

Sunucuda:

```
cat /etc/trader-release
```

**Kontrol:** `COMMIT=...` satırı görünüyor. Bu, şu anki sürümdür (kurulumdan sonra değişecek).

Kurulumdan ÖNCE elle yedek alın (defter, durum ve veto dosyaları; kurulum bunlara dokunur):

```
systemctl start trader-backup.service
systemctl show trader-backup.service -p Result -p ExecMainStatus
```

**Kontrol:** `Result=success` ve `ExecMainStatus=0`. Başka bir şey görürseniz kuruluma geçmeyin, çıktıyı bana bildirin.

---

## Adım 3: Kurulumu çalıştırın (yeni birimleri kurar)

```
COMMIT=<KOD> bash /usr/local/lib/trader-root/current/deploy/install.sh
```

`<KOD>` yerine Adım 1'deki 40 karakteri yazın. Betik kendini yeni sürümün kopyasıyla yeniden başlatır. Bitince ekrandaki **"DD-12 zamanlayıcı denetimi"** bölümüne bakın:

- `etkin: ...` satırları olmalı (notes, weekly-summary, ml-retrain, universe, counterfactual, weekly-collect).
- `UYARI: ... etkin değil` görürseniz: `systemctl enable --now <birim-adi>` yazın.
- `UYARI: eski birim duruyor` görürseniz: install.sh'i bir kez daha çalıştırın.

**Kontrol:** `cat /etc/trader-release` çıktısı `COMMIT=<KOD>` gösteriyor.

**Not:** Betik testnet motorunu, anahtar dolu ise, kendisi başlatabilir. Adım 6 bunu durdurur.

**Not:** Kod değiştiyse install.sh önce besleme birimini (`trader-feed`), sonra çalışan motorları yeniden başlatır. Motorlar 44 çiftlik yapılandırmayı bu sayede besleme üzerinden alır.

---

## Adım 4: Besleme (feed) birimini doğrulayın

install.sh kod değiştiyse feed'i zaten yeniden başlattı. Yine de çalıştırmak zararsızdır:

```
systemctl restart trader-feed.service
```

Besleme 44 çifti izlemeye başlayana kadar 1-2 dakika bekleyin. Ardından:

```
systemctl is-active trader-feed.service
journalctl -u trader-feed.service -n 100 --no-pager | grep -i "cift\|pair"
systemctl show trader-feed -p MemoryPeak
```

**Kontrol:**
- `active`.
- Günlükte 44 çift yazıyor. Günlük satır biçimi farklıysa pano kontrolü (Adım 12): kâğıt botta 44 çift görünmeli.
- `MemoryPeak=` değerini not alın ve bana bildirin.

Feed 44 çifte ulaşmadan öğrenen motoru (Adım 5) başlatmayın; motor eksik veriyle kural kontrolüne takılır.

---

## Adım 5: Kâğıt öğrenenin strateji etiketini değiştirin (price_action_lab_ml)

Kurulum ve besleme tamam olduktan sonra, dolaşan çıkış kuyruğundan (Adım 6-9) ÖNCE yapılır. Bu adım öğrenen motoru kısa süre durdurur ve defterdeki etiketi günceller. Parametreler aynı kalır, yalnız strateji adı değişir.

Bu adımdan önce motor (`trader-engine@learner`) `failed` ya da alarm gösterebilir (eski etiket). Bu beklenen bir durumdur, etiket güncellenince düzelir.

```
systemctl stop trader-engine@learner.service
cd /home/trader/SG-Github-AB-proje/trader
sudo -u trader env PYTHONPATH=src .venv/bin/python -m trader_engine init-ledger --bot learner --env paper --config-dir config --reason strategy_update
systemctl start trader-engine@learner.service
```

**Kontrol:**
- `init-ledger` çıktısı `strateji etiketi guncellendi: ... -> price_action_lab_ml ...` demeli. (`etkin surum zaten price_action_lab_ml: dokunulmadi` de kabul: etiket zaten doğru.)
- Çıktı `defter eski semada` diyorsa: defter henüz yeni şemada değil. Motor bir kez açılınca şemayı kendisi geçirir. Sırayla yapın: `systemctl start trader-engine@learner.service`, bir dakika bekleyin, `systemctl stop trader-engine@learner.service`, sonra yukarıdaki `init-ledger` komutunu bir kez daha çalıştırın.
- `systemctl is-active trader-engine@learner.service` → `active` (bu adımın sonunda).
- Hata: `ledger_stamp_mismatch` görürseniz durun ve çıktıyı bana bildirin (anahtar veya parola yapıştırmayın).

---

## Adım 6: Testnet motorunu durdurun (dolaşan çıkış kuyruğu için)

```
systemctl stop trader-engine-env-retry@testnet.timer
systemctl stop trader-engine-testnet.service
systemctl is-active trader-engine-testnet.service
```

**Kontrol:** son satır `inactive` (ya da `failed`) olmalı. `active` ise yukarıdaki stop komutunu tekrar yazın.

---

## Adım 7: DD-11 çıkış kuyruğu (outbox) için kuru koşu

Motor durdu. Önce yalnız rapor alın, hiçbir şey değişmez:

```
cd /home/trader/SG-Github-AB-proje/trader
sudo -u trader env PYTHONPATH=src .venv/bin/python -m trader_engine outbox-quarantine --bot learner --env testnet --config-dir config --dry-run
```

**Kontrol:** Çıktıda taşınacak satır sayısı yazar. Bu sayıyı not alın.
- Sayı **0** ise Adım 8'i atlayın (Adım 9 yine yapılır).
- Sayı **0'dan büyük** ise Adım 8'e geçin.

---

## Adım 8: Çıkış kuyruğunu uygulayın (yalnız Adım 7 sayı > 0 ise)

Motor hâlâ durmuş olmalı (Adım 6).

```
cd /home/trader/SG-Github-AB-proje/trader
sudo -u trader env PYTHONPATH=src .venv/bin/python -m trader_engine outbox-quarantine --bot learner --env testnet --config-dir config --apply
```

**Kontrol:** Çıktı taşınan satır sayısını gösterir (Adım 7'deki sayı ile aynı olmalı). Hata yoksa devam edin.

---

## Adım 9: Testnet motorunu yeniden başlatın (her durumda)

Bu adım Adım 8 çalıştırılmış ya da atlanmış olsun, mutlaka yapılır:

```
systemctl start trader-engine-testnet.service
systemctl start trader-engine-env-retry@testnet.timer
systemctl is-active trader-engine-testnet.service
```

**Kontrol:** `active`.

**Not:** Testnet artık veto'suz çalışır (LLM veto kaldırıldı; `config/engine.testnet.json` içinde `veto_mode: "off"`). `shared/veto/veto.json` olmasa da motor girişleri açmaya devam eder. Eski kurulumda bu dosyanın yokluğu yaklaşık 45 dakika sonra girişleri durdururdu; bu artık olmaz. Canlı (live) kip değişmedi ve bu adımlarda dokunulmaz.

---

## Adım 10: Birimleri ve zamanlayıcıları kontrol edin

Etkin birimler:

```
systemctl is-active trader-feed trader-engine@learner trader-panel trader-health.timer
```

**Kontrol:** dört satır da `active`.

Zamanlayıcılar (sonraki çalışma zamanları):

```
systemctl list-timers 'trader-*' --all --no-pager
```

**Kontrol:** şu zamanlayıcılar listede: `trader-lesson` (her saat :17), `trader-notes` (her gün 02:55 UTC), `trader-ml-retrain` (her gün 00:40 UTC; 24.11'de 03:40'tan alındı, DL1 eğitimi 01:00 UTC'de arkasından başlar), `trader-counterfactual@learner` (her gün 23:10 UTC), `trader-universe` (ayın 1'i 00:30 UTC), `trader-weekly-summary` (Pazar 18:10 UTC; YZ yorumu Message Batches ile gönderilir, sonucu `trader-weekly-collect` her 3 saatte :40 UTC toplar; tur 1 haftalık yorumu da aynı yolla).

Bellek sınırları:

```
systemctl show trader-ml-retrain.service -p MemoryHigh -p MemoryMax
systemctl show trader.slice -p MemoryMax
```

**Kontrol:** ml-retrain `MemoryHigh=250M` ve `MemoryMax=350M`; slice `MemoryMax=1300M`.

Eski veto ve ikiz birimler kalmamış olmalı:

```
systemctl list-units 'trader-veto*' 'trader-*twin*' --all --no-pager
```

**Kontrol:** liste boş ya da yalnız `not-found` / `inactive` satırları var.

---

## Adım 11: Gece eğitimini (ML) ilk kez görün

Gece 00:40 UTC'de (03:40 TSI) eğitim çalışır: kurulum süzgeci ve M1 (kendi adayı). Eğitim çıktıları sunucuda `var/learner/models/` altına yazılır (depodaki `models/` dizini değişmez). İlk çalıştırmayı sonraki sabah kontrol edin:

```
systemctl status trader-ml-retrain.service --no-pager | head -12
journalctl -u trader-ml-retrain.service -n 30 --no-pager
```

**Kontrol:** son çalıştırma `status=0/SUCCESS` ve günlükte `"status": "ok"` satırı var (M1 için `M1@1h`, `M1@4h`, `M1@15m`, `M1@1d` ayrı ayrı; paket oluşmayan zaman dilimi `"status": "no_model"` ve `"reason": "model yok: N örnek, en az M"` yazar;  `"status": "ok"`, `"m1_error": null`). `ls` ile dosya aramayın. Hata varsa `journalctl` çıktısını bana bildirin.

---

## Adım 12: Pano (salt okunur) kontrolü

Pano sunucuda yalnız `127.0.0.1:8787` adresinde çalışır. Kendi bilgisayarınızdan SSH tüneliyle açın:

1. Kendi bilgisayarınızda bir terminal açın:
   ```
   ssh -L 8787:127.0.0.1:8787 root@<sunucu-adresi>
   ```
2. Tarayıcıda `http://127.0.0.1:8787` adresini açın.
3. Sunucuda kontrol: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8787/` → `200`.

**Kontrol:** pano açılıyor; kâğıt botta 44 çift görünüyor; veto satırı yok; ML satırları (M1) listeleniyor. Pano için şifre ya da anahtar gerekmez.

---

## Sorun olursa

- Herhangi bir adımda beklenmeyen hata: çıktıyı kopyalayın, **anahtar, token ya da parola yapıştırmayın**, bana bildirin.
- Öğrenen motoru geri almak için: `systemctl stop trader-engine@learner.service` (kâğıt; gerçek para etkilenmez).
- Telegram ve ders servislerinin anahtarları `nano /etc/trader-*.env` ile doldurulur; sohbete yazılmaz.
