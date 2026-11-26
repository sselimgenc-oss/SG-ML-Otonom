# İşlem mutabakatı

Son kontrol: 2026-11-26 21:21 (TSİ). İşlem: 0 (kapanan 0, açık 0). Uyuşmazlık: 0.

## Kontroller

| Kontrol | Sonuç | Ayrıntı |
|---|---|---|
| Kasa = başlangıç + Σ net K/Z | geçti | Kasa 1.000,00 $ tutuyor |
| Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama | geçti | Defter toplamları tutuyor (+0,00 $) |
| Long toplamı (motor = panel) | geçti | Long işlemler panelle aynı (0 işlem) |
| Short toplamı (motor = panel) | geçti | Short işlemler panelle aynı (0 işlem) |
| Toplam kapanan (motor = panel 'tümü') | geçti | Kapanan işlemlerin toplamı panelle aynı (0 işlem) |
| Açık pozisyon sayısı (motor = panel = şerit = durum) | geçti | 0 açık işlem, hepsi aynı |
| Açık K/Z fiyat kaynağı (panel = motor mark) | geçti | Açık işlem yok |
| Günlük zarar limiti oranı (panel = kâğıt ayarı) | geçti | Günlük zarar limiti %8,00 (panelle aynı) |

## Bilgi

- Açık işlemlerin anlık kâr/zararı: kasada +0,00 $, panelde +0,00 $ · fark 0,00 $ (fiyat zamanlaması, uyuşmazlık sayılmaz)

## Telegram kaynağı

Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı. Sıra: (1) gönderim kaydı islem_gonderildi.jsonl (ts, işlem no, tür, yön, K/Z; kayıt başlangıcından itibaren), (2) outbox 'sent' işaretleri (teslim edilmiş mesajın anahtarı; mesaj metni yok), (3) islem_imleci.json (duyurulmuş işlem numaraları). Gönderim kaydından önceki işlemlerde imleç yalnız 'duyuruldu' sayıldığını gösterir, mesaj metnini kanıtlamaz; mesaj sisteminden önceki işlemler 'Telegram öncesi' sayılır, uyuşmazlık değildir.

## Uyuşmazlıklar

Yok.

## İşlemler

| İşlem no | Kol | Coin | Yön | Durum | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Brüt $ | Komisyon $ | Fonlama $ | Net K/Z $ | Panel | Telegram açıldı | Telegram kapandı |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
