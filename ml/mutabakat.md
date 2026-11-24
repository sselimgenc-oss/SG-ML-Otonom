# İşlem mutabakatı

Son kontrol: 2026-11-24 15:58 (TSİ). İşlem: 77 (kapanan 69, açık 8). Uyuşmazlık: 0.

## Kontroller

| Kontrol | Sonuç | Ayrıntı |
|---|---|---|
| Kasa = başlangıç + Σ net K/Z | geçti | Kasa 964,18 $ tutuyor |
| Net K/Z: SQL toplamı = motor toplamı = brüt - komisyon - fonlama | geçti | Defter toplamları tutuyor (-40,17 $) |
| Long toplamı (motor = panel) | geçti | Long işlemler panelle aynı (10 işlem) |
| Short toplamı (motor = panel) | geçti | Short işlemler panelle aynı (59 işlem) |
| Toplam kapanan (motor = panel 'tümü') | geçti | Kapanan işlemlerin toplamı panelle aynı (69 işlem) |
| Açık pozisyon sayısı (motor = panel = şerit = durum) | geçti | 8 açık işlem, hepsi aynı |
| Açık K/Z fiyat kaynağı (panel = motor mark) | geçti | Açık işlemlerin kâr/zararı panelle aynı; fiyat bekleniyor (piyasa kapalı/veri yok): #20, #39, #40, #80, #96, #98, #99, #101 |
| Günlük zarar limiti oranı (panel = kâğıt ayarı) | geçti | Günlük zarar limiti %8,00 (panelle aynı) |

## Bilgi

- Fiyatı gelmeyen açık işlemler: #20, #39, #40, #80, #96, #98, #99, #101 · fiyat bekleniyor (piyasa kapalı/veri yok); uyuşmazlık sayılmaz

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
| 59 | Trend geri çekilmesi · 1 saat | COST | long | kapalı | 2026-11-21 17:00 | 2026-11-22 13:30 | 1.110,550000 | 1.116,705000 | 6,2781 | 1,1359 | 0,0000 | 5,1422 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 60 | Sahte kırılım dönüşü · 15 dakika | NVDA | short | kapalı | 2026-11-21 17:15 | 2026-11-21 23:31 | 129,930000 | 131,560000 | -12,4206 | 0,9963 | -0,3769 | -13,0400 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 61 | Trend geri çekilmesi · 1 saat | AMZN | short | kapalı | 2026-11-21 18:00 | 2026-11-23 03:57 | 253,810000 | 257,750000 | -11,9776 | 0,7776 | -0,5093 | -12,2459 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 62 | Yapay zekâ adayı · 15 dakika | BTC | short | kapalı | 2026-11-21 23:45 | 2026-11-22 02:13 | 60.389,900000 | 60.332,600000 | 1,0314 | 1,0865 | 0,0000 | -0,0551 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 63 | Yapay zekâ adayı · 15 dakika | ETH | short | kapalı | 2026-11-22 02:15 | 2026-11-22 05:45 | 1.682,740000 | 1.671,110000 | 7,7572 | 1,1185 | -0,0305 | 6,6692 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 64 | Trend geri çekilmesi · 1 saat | BTC | short | kapalı | 2026-11-22 06:00 | 2026-11-22 12:50 | 59.463,100000 | 60.668,200000 | -9,6408 | 0,4805 | -0,0259 | -10,0954 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 65 | Trend geri çekilmesi · 1 saat | ETH | short | kapalı | 2026-11-22 06:00 | 2026-11-22 11:36 | 1.671,050000 | 1.697,930000 | -11,3702 | 0,7125 | 0,0078 | -12,0906 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 66 | Sıkışma kırılımı · 1 saat | BCH | short | kapalı | 2026-11-22 09:00 | 2026-11-23 13:41 | 194,620000 | 200,930000 | -11,0677 | 0,3469 | 0,1852 | -11,5999 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 67 | Yapay zekâ adayı · 1 saat | AVAX | short | kapalı | 2026-11-22 12:00 | 2026-11-22 12:56 | 6,595000 | 6,680000 | -10,2000 | 0,7965 | 0,0000 | -10,9965 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 68 | Yapay zekâ adayı · 1 saat | XMR | short | kapalı | 2026-11-22 13:00 | 2026-11-22 17:23 | 484,830000 | 492,930000 | -10,1331 | 0,6116 | 0,0000 | -10,7447 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 69 | Sahte kırılım dönüşü · 15 dakika | NVDA | short | kapalı | 2026-11-22 13:45 | 2026-11-22 15:19 | 132,220000 | 133,580000 | -11,1384 | 1,0885 | 0,0000 | -12,2269 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 70 | Sıkışma kırılımı · 15 dakika | GOOGL | short | kapalı | 2026-11-22 15:30 | 2026-11-23 03:01 | 274,500000 | 277,110000 | -10,2573 | 1,0839 | 0,0000 | -11,3412 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 71 | İki bacaklı geri çekilme · 4 saat | 1000SHIB | short | kapalı | 2026-11-22 23:00 | 2026-11-23 16:57 | 0,003580 | 0,003696 | -10,3162 | 0,3235 | 0,0557 | -10,6955 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 72 | Kırılım yeniden testi · 1 gün | XLM | short | kapalı | 2026-11-23 03:00 | 2026-11-23 16:58 | 0,127660 | 0,132900 | -10,2599 | 0,2551 | 0,0232 | -10,5383 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 73 | Trend geri çekilmesi · 15 dakika | TRX | short | kapalı | 2026-11-23 03:15 | 2026-11-23 04:38 | 0,305190 | 0,304325 | 2,9725 | 1,0475 | 0,0000 | 1,9250 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 74 | Yapay zekâ adayı · 1 saat | BTC | short | kapalı | 2026-11-23 04:00 | 2026-11-23 06:13 | 61.303,500000 | 61.242,200000 | 0,7969 | 0,7965 | 0,0000 | 0,0004 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 75 | Trend geri çekilmesi · 15 dakika | XMR | short | kapalı | 2026-11-23 04:45 | 2026-11-23 05:22 | 491,750000 | 496,020000 | -9,1848 | 1,0623 | 0,0000 | -10,2471 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 76 | Trend kırılımı · 15 dakika | DOGE | short | kapalı | 2026-11-23 05:30 | 2026-11-23 06:11 | 0,054610 | 0,054980 | -7,1602 | 1,0604 | 0,0000 | -8,2206 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 77 | Sahte kırılım dönüşü · 15 dakika | BRKB | short | kapalı | 2026-11-23 06:30 | 2026-11-23 12:00 | 573,640000 | 573,750000 | -0,1969 | 1,0269 | -0,3431 | -0,8807 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 78 | Sahte kırılım dönüşü · 15 dakika | ADA | short | kapalı | 2026-11-23 06:45 | 2026-11-23 08:31 | 0,144200 | 0,145500 | -4,3199 | 0,4813 | 0,0000 | -4,8012 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 79 | Yapay zekâ adayı · 4 saat | NVDA | short | kapalı | 2026-11-23 07:00 | 2026-11-23 16:55 | 134,260000 | 138,510000 | -10,4125 | 0,3341 | -0,1239 | -10,6227 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 80 | Sıkışma kırılımı · 4 saat | AAPL | short | açık | 2026-11-23 11:00 | — | 346,480000 | — | — | 0,2477 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 81 | Sıkışma kırılımı · 15 dakika | WMT | long | kapalı | 2026-11-23 12:15 | 2026-11-23 17:00 | 127,960000 | 127,970000 | 0,0588 | 0,7524 | 0,0000 | -0,6936 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 82 | Sıkışma kırılımı · 15 dakika | ADA | short | kapalı | 2026-11-23 14:00 | 2026-11-23 16:56 | 0,145700 | 0,147600 | -4,6930 | 0,3622 | 0,0000 | -5,0552 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 83 | Sıkışma kırılımı · 15 dakika | HD | short | kapalı | 2026-11-23 17:00 | 2026-11-23 17:15 | 343,650000 | 343,090000 | 1,1648 | 0,7142 | 0,0000 | 0,4506 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 84 | Trend geri çekilmesi · 15 dakika | BTC | short | kapalı | 2026-11-24 02:45 | 2026-11-24 04:10 | 61.133,400000 | 61.689,300000 | -8,3385 | 0,9212 | -0,0261 | -9,2335 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 85 | Yapay zekâ adayı · 15 dakika | XRP | short | kapalı | 2026-11-24 02:45 | 2026-11-24 03:41 | 0,937500 | 0,945600 | -4,1577 | 0,4833 | 0,0616 | -4,7026 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 86 | Yapay zekâ adayı · 15 dakika | TRX | short | kapalı | 2026-11-24 03:45 | 2026-11-24 04:34 | 0,311020 | 0,310710 | 0,9576 | 0,9603 | 0,0000 | -0,0027 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 87 | Yapay zekâ adayı · 15 dakika | ETH | short | kapalı | 2026-11-24 04:15 | 2026-11-24 05:15 | 1.718,010000 | 1.706,470000 | 3,1735 | 0,4709 | 0,0000 | 2,7026 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 88 | Yapay zekâ adayı · 15 dakika | SOL | short | kapalı | 2026-11-24 04:15 | 2026-11-24 05:30 | 72,390000 | 71,575000 | 5,1997 | 0,4592 | 0,0000 | 4,7405 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 89 | Yapay zekâ adayı · 15 dakika | JPM | short | kapalı | 2026-11-24 04:45 | 2026-11-24 06:15 | 318,220000 | 317,530000 | 2,0631 | 0,9504 | 0,0000 | 1,1127 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 90 | Yapay zekâ adayı · 15 dakika | XRP | short | kapalı | 2026-11-24 05:30 | 2026-11-24 06:29 | 0,943800 | 0,939050 | 2,4320 | 0,4820 | 0,0000 | 1,9500 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 91 | İki bacaklı geri çekilme · 15 dakika | MSFT | short | kapalı | 2026-11-24 06:00 | 2026-11-24 08:30 | 492,730000 | 496,970000 | -4,8760 | 0,5691 | 0,0000 | -5,4451 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 92 | Sahte kırılım dönüşü · 15 dakika | TSLA | long | kapalı | 2026-11-24 06:30 | 2026-11-24 09:23 | 386,180000 | 386,170000 | -0,0176 | 0,6797 | 0,0000 | -0,6973 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 93 | Yapay zekâ adayı · 15 dakika | JPM | short | kapalı | 2026-11-24 06:30 | 2026-11-24 08:15 | 317,580000 | 318,900000 | -2,9832 | 0,7192 | 0,0000 | -3,7024 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 94 | Sahte kırılım dönüşü · 15 dakika | XRP | short | kapalı | 2026-11-24 08:30 | 2026-11-24 08:34 | 0,952900 | 0,957200 | -3,7668 | 0,8366 | 0,0000 | -4,6034 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 95 | İki bacaklı geri çekilme · 15 dakika | BTC | short | kapalı | 2026-11-24 09:00 | 2026-11-24 09:50 | 60.590,500000 | 60.529,900000 | 0,7878 | 0,7873 | 0,0000 | 0,0005 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 96 | Trend geri çekilmesi · 15 dakika | AVAX | short | açık | 2026-11-24 09:15 | — | 6,793000 | — | — | 0,2004 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 97 | Sahte kırılım dönüşü · 15 dakika | HD | long | kapalı | 2026-11-24 10:00 | 2026-11-24 12:00 | 345,770000 | 344,700000 | -2,9318 | 0,9459 | 0,0000 | -3,8777 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 98 | Trend geri çekilmesi · 15 dakika | ADA | short | açık | 2026-11-24 10:15 | — | 0,148300 | — | — | 0,2379 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 99 | Trend kırılımı · 15 dakika | WMT | long | açık | 2026-11-24 12:15 | — | 130,340000 | — | — | 0,4810 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
| 100 | Sahte kırılım dönüşü · 15 dakika | TSLA | long | kapalı | 2026-11-24 12:30 | 2026-11-24 13:30 | 384,770000 | 381,360000 | -2,8985 | 0,3256 | 0,0000 | -3,2241 | aynı | gönderildi (kayıt) | gönderildi (kayıt) |
| 101 | Sahte kırılım dönüşü · 15 dakika | BZ | short | açık | 2026-11-24 14:45 | — | 86,930000 | — | — | 0,2282 | 0,0000 | — | aynı | gönderildi (kayıt) | — |
