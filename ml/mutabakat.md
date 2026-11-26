# İşlem mutabakatı

Son kontrol: 2026-11-27 01:19 (TSİ). İşlem: 2 (kapanan 0, açık 2). Uyuşmazlık: 0.

## Kontroller

| Kontrol | Sonuç | Ayrıntı |
|---|---|---|
| Kasa = başlangıç + Σ net K/Z | geçti | Kasa 999,63 $ tutuyor |
| Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama | geçti | Defter toplamları tutuyor (+0,00 $) |
| Long toplamı (motor = panel) | geçti | Long işlemler panelle aynı (0 işlem) |
| Short toplamı (motor = panel) | geçti | Short işlemler panelle aynı (0 işlem) |
| Toplam kapanan (motor = panel 'tümü') | geçti | Kapanan işlemlerin toplamı panelle aynı (0 işlem) |
| Açık pozisyon sayısı (motor = panel = şerit = durum) | geçti | 2 açık işlem, hepsi aynı |
| Açık K/Z fiyat kaynağı (panel = motor mark) | geçti | Açık işlemlerin kâr/zararı panelle aynı; fiyat bekleniyor (piyasa kapalı/veri yok): #1, #2 |
| Günlük zarar limiti oranı (panel = kâğıt ayarı) | geçti | Günlük zarar limiti %8,00 (panelle aynı) |

## Bilgi

- Fiyatı gelmeyen açık işlemler: #1, #2 · fiyat bekleniyor (piyasa kapalı/veri yok); uyuşmazlık sayılmaz

## Telegram kaynağı

Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı. Sıra: (1) gönderim kaydı islem_gonderildi.jsonl (ts, işlem no, tür, yön, K/Z; kayıt başlangıcından itibaren), (2) outbox 'sent' işaretleri (teslim edilmiş mesajın anahtarı; mesaj metni yok), (3) islem_imleci.json (duyurulmuş işlem numaraları). Gönderim kaydından önceki işlemlerde imleç yalnız 'duyuruldu' sayıldığını gösterir, mesaj metnini kanıtlamaz; mesaj sisteminden önceki işlemler 'Telegram öncesi' sayılır, uyuşmazlık değildir.

## Uyuşmazlıklar

Yok.

## İşlemler

| İşlem no | Kol | Coin | Yön | Durum | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Brüt $ | Komisyon $ | Fonlama $ | Net K/Z $ | Panel | Telegram açıldı | Telegram kapandı |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Gösterge: RSI(2) tepe · 4 saat | SOL | short | açık | 2026-11-26 23:00 | — | 71,230000 | — | — | 0,0994 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 2 | Gösterge: RSI(2) tepe · 1 saat | ETH | short | açık | 2026-11-27 00:00 | — | 1.703,510000 | — | — | 0,2751 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
