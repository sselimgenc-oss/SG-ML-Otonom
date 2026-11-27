# İşlem mutabakatı

Son kontrol: 2026-11-27 03:21 (TSİ). İşlem: 5 (kapanan 1, açık 4). Uyuşmazlık: 0.

## Kontroller

| Kontrol | Sonuç | Ayrıntı |
|---|---|---|
| Kasa = başlangıç + Σ net K/Z | geçti | Kasa 1.001,54 $ tutuyor |
| Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama | geçti | Defter toplamları tutuyor (+2,69 $) |
| Long toplamı (motor = panel) | geçti | Long işlemler panelle aynı (0 işlem) |
| Short toplamı (motor = panel) | geçti | Short işlemler panelle aynı (1 işlem) |
| Toplam kapanan (motor = panel 'tümü') | geçti | Kapanan işlemlerin toplamı panelle aynı (1 işlem) |
| Açık pozisyon sayısı (motor = panel = şerit = durum) | geçti | 4 açık işlem, hepsi aynı |
| Açık K/Z fiyat kaynağı (panel = motor mark) | geçti | Açık işlemlerin kâr/zararı panelle aynı |
| Günlük zarar limiti oranı (panel = kâğıt ayarı) | geçti | Günlük zarar limiti %8,00 (panelle aynı) |

## Bilgi

- Açık işlemlerin anlık kâr/zararı: kasada -1,44 $, panelde -1,24 $ · fark 0,20 $ (fiyat zamanlaması, uyuşmazlık sayılmaz)

## Telegram kaynağı

Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı. Sıra: (1) gönderim kaydı islem_gonderildi.jsonl (ts, işlem no, tür, yön, K/Z; kayıt başlangıcından itibaren), (2) outbox 'sent' işaretleri (teslim edilmiş mesajın anahtarı; mesaj metni yok), (3) islem_imleci.json (duyurulmuş işlem numaraları). Gönderim kaydından önceki işlemlerde imleç yalnız 'duyuruldu' sayıldığını gösterir, mesaj metnini kanıtlamaz; mesaj sisteminden önceki işlemler 'Telegram öncesi' sayılır, uyuşmazlık değildir.

## Uyuşmazlıklar

Yok.

## İşlemler

| İşlem no | Kol | Coin | Yön | Durum | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Brüt $ | Komisyon $ | Fonlama $ | Net K/Z $ | Panel | Telegram açıldı | Telegram kapandı |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Gösterge: RSI(2) tepe · 4 saat | SOL | short | açık | 2026-11-26 23:00 | — | 71,230000 | — | — | 0,0994 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 2 | Gösterge: RSI(2) tepe · 1 saat | ETH | short | kapalı | 2026-11-27 00:00 | 2026-11-27 02:00 | 1.703,510000 | 1.693,470000 | 3,2429 | 0,5486 | 0,0000 | 2,6943 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 3 | Düşüş trendi: tepkiden satış · 1 saat | TRX | short | açık | 2026-11-27 02:00 | — | 0,303910 | — | — | 0,5016 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 4 | Düşüş trendi: 3 yükselen dibin kırılımıyla satış · 1 saat | BTC | short | açık | 2026-11-27 02:00 | — | 60.511,200000 | — | — | 0,4841 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 5 | Düşüş trendi: tepkiden satış · 4 saat | XRP | short | açık | 2026-11-27 03:00 | — | 0,943300 | — | — | 0,1664 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
