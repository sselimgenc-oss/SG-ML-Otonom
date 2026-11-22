# İşlem mutabakatı

Son kontrol: 2026-11-22 10:34 (TSİ). İşlem: 42 (kapanan 34, açık 8). Uyuşmazlık: 0.

## Kontroller

| Kontrol | Sonuç | Ayrıntı |
|---|---|---|
| Kasa = başlangıç + Σ net K/Z | geçti | Kasa 1.131,21 $ tutuyor |
| Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama | geçti | Defter toplamları tutuyor (+130,39 $) |
| Long toplamı (motor = panel) | geçti | Long işlemler panelle aynı (5 işlem) |
| Short toplamı (motor = panel) | geçti | Short işlemler panelle aynı (29 işlem) |
| Toplam kapanan (motor = panel 'tümü') | geçti | Kapanan işlemlerin toplamı panelle aynı (34 işlem) |
| Açık pozisyon sayısı (motor = panel = şerit = durum) | geçti | 8 açık işlem, hepsi aynı |
| Açık K/Z fiyat kaynağı (panel = motor mark) | geçti | Açık işlemlerin kâr/zararı panelle aynı; fiyat bekleniyor (piyasa kapalı/veri yok): #20, #39, #40, #59, #61, #64, #65, #66 |
| Günlük zarar limiti oranı (panel = kâğıt ayarı) | geçti | Günlük zarar limiti %8,00 (panelle aynı) |

## Bilgi

- Fiyatı gelmeyen açık işlemler: #20, #39, #40, #59, #61, #64, #65, #66 · fiyat bekleniyor (piyasa kapalı/veri yok); uyuşmazlık sayılmaz

## Telegram kaynağı

Telegram geçmişine erişim yok; motorun gönderdi kaydı (imleç) kullanıldı. Sıra: (1) gönderim kaydı islem_gonderildi.jsonl (ts, işlem no, tür, yön, K/Z; kayıt başlangıcından itibaren), (2) outbox 'sent' işaretleri (teslim edilmiş mesajın anahtarı; mesaj metni yok), (3) islem_imleci.json (duyurulmuş işlem numaraları). Gönderim kaydından önceki işlemlerde imleç yalnız 'duyuruldu' sayıldığını gösterir, mesaj metnini kanıtlamaz; mesaj sisteminden önceki işlemler 'Telegram öncesi' sayılır, uyuşmazlık değildir.

## Uyuşmazlıklar

Yok.

## İşlemler

| İşlem no | Kol | Coin | Yön | Durum | Açılış (TSİ) | Kapanış (TSİ) | Giriş | Çıkış | Brüt $ | Komisyon $ | Fonlama $ | Net K/Z $ | Panel | Telegram açıldı | Telegram kapandı |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Trend geri çekilmesi · 1 saat | ADA | short | kapalı | 2026-11-18 08:00 | 2026-11-19 07:46 | 0,152900 | 0,153300 | -0,6144 | 0,2352 | -0,0396 | -0,8100 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 2 | Trend geri çekilmesi · 1 saat | AVAX | short | kapalı | 2026-11-18 10:00 | 2026-11-19 07:46 | 7,147000 | 7,099000 | 2,4000 | 0,3562 | 0,0004 | 2,0434 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 3 | Trend geri çekilmesi · 1 saat | BTC | short | kapalı | 2026-11-18 12:00 | 2026-11-19 07:46 | 64.644,400000 | 63.634,100000 | 9,0927 | 0,5773 | -0,0873 | 8,6027 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 4 | Trend geri çekilmesi · 1 saat | ETH | short | kapalı | 2026-11-18 12:00 | 2026-11-19 04:04 | 1.810,700000 | 1.788,890000 | 6,4994 | 0,5363 | -0,0460 | 6,0090 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 5 | Trend geri çekilmesi · 1 saat | BNB | short | kapalı | 2026-11-18 12:00 | 2026-11-19 07:45 | 591,970000 | 588,020000 | 3,9500 | 0,5900 | 0,0000 | 3,3600 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 6 | Trend geri çekilmesi · 1 saat | SOL | short | kapalı | 2026-11-18 23:00 | 2026-11-19 07:34 | 73,060000 | 74,680000 | -4,9572 | 0,2260 | -0,0017 | -5,1816 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 7 | Sahte kırılım dönüşü · 15 dakika | BTC | short | kapalı | 2026-11-19 14:00 | 2026-11-19 14:33 | 63.747,600000 | 64.018,400000 | -4,0620 | 0,9582 | 0,0000 | -5,0202 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 8 | Sıkışma kırılımı · 15 dakika | HBAR | short | kapalı | 2026-11-19 14:00 | 2026-11-19 14:45 | 0,055340 | 0,056030 | -9,2957 | 0,7502 | 0,0000 | -10,0459 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 9 | Yapay zekâ adayı · 1 saat | NVDA | long | kapalı | 2026-11-19 14:00 | 2026-11-19 18:00 | 154,090000 | 155,200000 | 5,6499 | 0,7871 | 0,0000 | 4,8628 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 10 | Sıkışma kırılımı · 15 dakika | HYPE | long | kapalı | 2026-11-19 14:45 | 2026-11-19 15:25 | 68,917000 | 68,146000 | -8,9976 | 0,7998 | 0,0000 | -9,7973 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 11 | Sıkışma kırılımı · 15 dakika | AMD | long | kapalı | 2026-11-19 14:45 | 2026-11-19 16:30 | 550,750000 | 538,300000 | -13,0725 | 0,5718 | 0,0000 | -13,6443 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 12 | Sahte kırılım dönüşü · 15 dakika | WMT | long | kapalı | 2026-11-19 17:45 | 2026-11-20 05:45 | 125,030000 | 127,200000 | 8,7017 | 0,5057 | 0,0000 | 8,1960 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 13 | Kırılım yeniden testi · 15 dakika | BRKB | short | kapalı | 2026-11-19 18:15 | 2026-11-19 20:15 | 570,350000 | 567,810000 | 4,3688 | 0,9788 | 0,0000 | 3,3900 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 14 | Trend geri çekilmesi · 15 dakika | XAG | short | kapalı | 2026-11-19 18:15 | 2026-11-20 03:15 | 45,280000 | 43,150000 | 42,1122 | 0,8742 | -0,2922 | 41,5303 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 16 | Sahte kırılım dönüşü · 15 dakika | HBAR | long | kapalı | 2026-11-19 20:30 | 2026-11-19 23:27 | 0,055240 | 0,054300 | -9,3135 | 0,5427 | 0,0000 | -9,8562 | aynı | Telegram öncesi (mesaj sistemi yoktu) | Telegram öncesi (mesaj sistemi yoktu) |
| 17 | Sıkışma kırılımı · 15 dakika | TRX | short | kapalı | 2026-11-19 23:30 | 2026-11-21 02:01 | 0,309870 | 0,305190 | 15,1070 | 0,9927 | 0,1639 | 13,9505 | aynı | Telegram öncesi (mesaj sistemi yoktu) | gönderildi (kayıt) |
| 20 | Trend kırılımı · 1 gün | ORCL | short | açık | 2026-11-20 03:00 | — | 109,860000 | — | — | 0,0505 | 0,0000 | — | aynı | Telegram öncesi (mesaj sistemi yoktu) | — |
| 21 | İki bacaklı geri çekilme · 15 dakika | NVDA | short | kapalı | 2026-11-20 03:30 | 2026-11-20 11:21 | 145,870000 | 144,590963 | 6,5103 | 0,7392 | -0,0282 | 5,7993 | aynı | Telegram öncesi (mesaj sistemi yoktu) | gönderildi (kayıt) |
| 22 | Sıkışma kırılımı · 1 saat | ADA | short | kapalı | 2026-11-20 05:00 | 2026-11-21 14:32 | 0,149000 | 0,140600 | 14,2800 | 0,2462 | 0,1552 | 13,8786 | aynı | Telegram öncesi (mesaj sistemi yoktu) | gönderildi (kayıt) |
| 24 | Yapay zekâ adayı · 4 saat | BNB | short | kapalı | 2026-11-20 07:00 | 2026-11-20 19:00 | 575,090000 | 546,830000 | 20,9124 | 0,4151 | 0,0000 | 20,4973 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 27 | Sıkışma kırılımı · 1 saat | AMD | short | kapalı | 2026-11-20 13:00 | 2026-11-21 16:45 | 462,660000 | 439,340000 | 11,6600 | 0,2255 | 0,0000 | 11,4345 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 30 | Kırılım yeniden testi · 1 saat | SOL | short | kapalı | 2026-11-20 18:00 | 2026-11-20 19:00 | 71,000000 | 68,320000 | 25,6744 | 0,6673 | 0,0650 | 24,9421 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 31 | Trend kırılımı · 15 dakika | AAPL | short | kapalı | 2026-11-20 19:30 | 2026-11-21 02:00 | 347,870000 | 345,105000 | 9,2351 | 1,1573 | 0,0000 | 8,0778 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 35 | Trend kırılımı · 15 dakika | GOOGL | short | kapalı | 2026-11-20 23:15 | 2026-11-21 00:15 | 269,270000 | 267,885000 | 5,4569 | 1,0582 | 0,0000 | 4,3987 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 36 | Trend geri çekilmesi · 15 dakika | HBAR | short | kapalı | 2026-11-21 01:30 | 2026-11-21 09:40 | 0,051620 | 0,050125 | 33,2159 | 1,1303 | 0,0571 | 32,0285 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 37 | Trend geri çekilmesi · 15 dakika | XLM | short | kapalı | 2026-11-21 02:15 | 2026-11-21 09:41 | 0,128250 | 0,124590 | 26,0738 | 0,9006 | 0,0822 | 25,0910 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 38 | İki bacaklı geri çekilme · 15 dakika | NVDA | short | kapalı | 2026-11-21 02:46 | 2026-11-21 09:41 | 129,610000 | 129,670000 | -0,3534 | 0,7636 | -0,2110 | -0,9060 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 39 | İki bacaklı geri çekilme · 1 gün | BNB | short | açık | 2026-11-21 03:00 | — | 540,830000 | — | — | 0,0460 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 40 | Trend kırılımı · 1 gün | HYPE | short | açık | 2026-11-21 03:00 | — | 61,016000 | — | — | 0,0403 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 54 | Yapay zekâ adayı · 15 dakika | NFLX | short | kapalı | 2026-11-21 09:45 | 2026-11-21 15:15 | 56,970000 | 57,250000 | -6,1096 | 1,2461 | 0,0000 | -7,3557 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 55 | Yapay zekâ adayı · 15 dakika | BZ | short | kapalı | 2026-11-21 09:45 | 2026-11-21 16:45 | 89,930000 | 90,370000 | -6,0808 | 1,2459 | 0,0000 | -7,3267 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 56 | Kırılım yeniden testi · 1 saat | AVAX | short | kapalı | 2026-11-21 11:00 | 2026-11-21 14:31 | 6,270000 | 6,419000 | -11,3240 | 0,4822 | 0,0000 | -11,8062 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 57 | İki bacaklı geri çekilme · 1 saat | DOT | short | kapalı | 2026-11-21 15:00 | 2026-11-21 16:39 | 0,643100 | 0,661000 | -11,3218 | 0,4124 | 0,0000 | -11,7342 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 58 | Trend geri çekilmesi · 15 dakika | JPM | short | kapalı | 2026-11-21 15:30 | 2026-11-21 16:45 | 312,120000 | 313,890000 | -6,6198 | 1,1706 | 0,0000 | -7,7904 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 59 | Trend geri çekilmesi · 1 saat | COST | long | açık | 2026-11-21 17:00 | — | 1.110,550000 | — | — | 0,5664 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 60 | Sahte kırılım dönüşü · 15 dakika | NVDA | short | kapalı | 2026-11-21 17:15 | 2026-11-21 23:31 | 129,930000 | 131,560000 | -12,4206 | 0,9963 | -0,3769 | -13,0400 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 61 | Trend geri çekilmesi · 1 saat | AMZN | short | açık | 2026-11-21 18:00 | — | 253,810000 | — | — | 0,3858 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 62 | Yapay zekâ adayı · 15 dakika | BTC | short | kapalı | 2026-11-21 23:45 | 2026-11-22 02:13 | 60.389,900000 | 60.332,600000 | 1,0314 | 1,0865 | 0,0000 | -0,0551 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 63 | Yapay zekâ adayı · 15 dakika | ETH | short | kapalı | 2026-11-22 02:15 | 2026-11-22 05:45 | 1.682,740000 | 1.671,110000 | 7,7572 | 1,1185 | -0,0305 | 6,6692 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 64 | Trend geri çekilmesi · 1 saat | BTC | short | açık | 2026-11-22 06:00 | — | 59.463,100000 | — | — | 0,2379 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 65 | Trend geri çekilmesi · 1 saat | ETH | short | açık | 2026-11-22 06:00 | — | 1.671,050000 | — | — | 0,3534 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 66 | Sıkışma kırılımı · 1 saat | BCH | short | açık | 2026-11-22 09:00 | — | 194,620000 | — | — | 0,1707 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
