# İşlem mutabakatı

Son kontrol: 2026-11-28 07:40 (TSİ). İşlem: 17 (kapanan 10, açık 7). Uyuşmazlık: 0.

## Kontroller

| Kontrol | Sonuç | Ayrıntı |
|---|---|---|
| Kasa = başlangıç + Σ net K/Z | geçti | Kasa 994,90 $ tutuyor |
| Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama | geçti | Defter toplamları tutuyor (-3,80 $) |
| Long toplamı (motor = panel) | geçti | Long işlemler panelle aynı (1 işlem) |
| Short toplamı (motor = panel) | geçti | Short işlemler panelle aynı (9 işlem) |
| Toplam kapanan (motor = panel 'tümü') | geçti | Kapanan işlemlerin toplamı panelle aynı (10 işlem) |
| Açık pozisyon sayısı (motor = panel = şerit = durum) | geçti | 7 açık işlem, hepsi aynı |
| Açık K/Z fiyat kaynağı (panel = motor mark) | geçti | Açık işlemlerin kâr/zararı panelle aynı |
| Günlük zarar limiti oranı (panel = kâğıt ayarı) | geçti | Günlük zarar limiti %8,00 (panelle aynı) |

## Bilgi

- Açık işlemlerin anlık kâr/zararı: kasada -17,46 $, panelde -17,49 $ · fark 0,03 $ (fiyat zamanlaması, uyuşmazlık sayılmaz)

## Telegram kaynağı

Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı. Sıra: (1) gönderim kaydı islem_gonderildi.jsonl (ts, işlem no, tür, yön, K/Z; kayıt başlangıcından itibaren), (2) outbox 'sent' işaretleri (teslim edilmiş mesajın anahtarı; mesaj metni yok), (3) islem_imleci.json (duyurulmuş işlem numaraları). Gönderim kaydından önceki işlemlerde imleç yalnız 'duyuruldu' sayıldığını gösterir, mesaj metnini kanıtlamaz; mesaj sisteminden önceki işlemler 'Telegram öncesi' sayılır, uyuşmazlık değildir.

## Uyuşmazlıklar

Yok.

## İşlemler

| İşlem no | Kol | Coin | Yön | Durum | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Brüt $ | Komisyon $ | Fonlama $ | Net K/Z $ | Panel | Telegram açıldı | Telegram kapandı |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Gösterge: RSI(2) tepe · 4 saat | SOL | short | kapalı | 2026-11-26 23:00 | 2026-11-28 03:00 | 71,230000 | 71,640000 | -1,1439 | 0,1993 | -0,0445 | -1,2987 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 2 | Gösterge: RSI(2) tepe · 1 saat | ETH | short | kapalı | 2026-11-27 00:00 | 2026-11-27 02:00 | 1.703,510000 | 1.693,470000 | 3,2429 | 0,5486 | 0,0000 | 2,6943 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 3 | Düşüş trendi: tepkiden satış · 1 saat | TRX | short | kapalı | 2026-11-27 02:00 | 2026-11-27 06:08 | 0,303910 | 0,305300 | -4,5884 | 1,0055 | 0,0099 | -5,6038 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 4 | Düşüş trendi: 3 yükselen dibin kırılımıyla satış · 1 saat | BTC | short | kapalı | 2026-11-27 02:00 | 2026-11-27 05:07 | 60.511,200000 | 61.009,500000 | -7,9728 | 0,9722 | -0,0955 | -8,8495 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 5 | Düşüş trendi: tepkiden satış · 4 saat | XRP | short | kapalı | 2026-11-27 03:00 | 2026-11-27 08:52 | 0,943300 | 0,970300 | -9,5256 | 0,3376 | 0,0000 | -9,8632 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 6 | PA: önceki dönem tepesi · 1 saat | BTC | short | kapalı | 2026-11-27 08:00 | 2026-11-27 11:17 | 61.379,300000 | 62.036,700000 | -8,5462 | 0,8022 | -0,0403 | -9,3081 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 7 | Gösterge: RSI 70 altına dönüş · 1 saat | ETH | short | kapalı | 2026-11-27 10:00 | 2026-11-27 17:38 | 1.733,280000 | 1.691,720000 | 16,3331 | 0,6730 | -0,0480 | 15,7081 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 8 | Gösterge: RSI(2) tepe · 4 saat | TRX | short | kapalı | 2026-11-27 11:00 | 2026-11-27 19:00 | 0,305280 | 0,301130 | 8,4618 | 0,6182 | 0,0599 | 7,7837 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 9 | Mum: pin bar (üst fitil) · 1 saat | XRP | short | kapalı | 2026-11-27 12:00 | 2026-11-27 17:34 | 0,975700 | 0,954100 | 16,0574 | 0,7173 | 0,0000 | 15,3401 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 10 | Gösterge: RSI(2) dip · 1 saat | BZ | long | kapalı | 2026-11-27 18:00 | 2026-11-27 19:36 | 91,250000 | 90,020000 | -9,6924 | 0,7142 | 0,0000 | -10,4066 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 11 | Grafik: üçlü tepe · 1 saat | MSFT | short | açık | 2026-11-27 18:00 | — | 490,760000 | — | — | 0,1914 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 12 | Mum: iç çubuk aşağı kırılımı · 1 saat | NVDA | short | açık | 2026-11-27 18:00 | — | 146,500000 | — | — | 0,0747 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 13 | Grafik: üçlü tepe · 1 saat | GOOGL | short | açık | 2026-11-27 18:00 | — | 272,170000 | — | — | 0,1238 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 15 | Grafik: üçlü tepe · 1 saat | BTC | short | açık | 2026-11-27 18:00 | — | 59.166,100000 | — | — | 0,0887 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 16 | PA: değer boşluğu · 4 saat | META | long | açık | 2026-11-27 19:00 | — | 635,720000 | — | — | 0,1271 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 17 | Mum: iç çubuk · 1 saat | BZ | long | açık | 2026-11-27 23:00 | — | 90,840000 | — | — | 0,3502 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 18 | Mum: ayı yutan · 1 saat | SOL | short | açık | 2026-11-28 06:00 | — | 71,650000 | — | — | 0,4077 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
