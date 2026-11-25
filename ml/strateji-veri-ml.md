# [ML] Strateji verisi (beyin fırtınası için)

Üretim: 25.11.2026 09:22 TSİ · Kâğıt başlangıcı (ilk kayıt): 17.11.2026 18:00 TSİ · Veri kesiti: 25.11.2026 09:15 TSİ
Kapanan işlem: 83 · Açık işlem: 9 · Karar kaydı: 5046 · Yapılandırılmış kol: 288
Kapsam: yalnız kâğıt defteri (salt okunur). Kilitli dönem (01.05.2026-01.11.2026) kayıtları okunmadı/ayıklandı (ayıklanan kayıt: 0). Yeni geri test hesaplanmadı. Yorum/öneri yok.

## Ortak 1 — Kâğıt başlangıcından beri sonuç

| Ölçü | Değer | Veri |
|---|---|---|
| Net K/Z | -$44,20 | veri: 25.11.2026 06:21 TSİ |
| İşlem sayısı (kapanan) | 83 | veri: 25.11.2026 06:21 TSİ |
| Kazanma oranı (net > 0) | %42,2 | veri: 25.11.2026 06:21 TSİ |
| Ort. kazanç | +1,14 R / +$8,53 | veri: 25.11.2026 06:21 TSİ |
| Ort. kayıp | -0,96 R / -$7,14 | veri: 25.11.2026 06:21 TSİ |
| Toplam R | -6,03 R | veri: 25.11.2026 06:21 TSİ |

## Ortak 2 — K/Z yoğunlaşması

| Ölçü | Değer | Veri |
|---|---|---|
| En iyi 1 işlemin net içindeki payı | - (+$41,53) | veri: 25.11.2026 06:21 TSİ |
| En iyi 2 işlemin net içindeki payı | - (+$73,56) | veri: 25.11.2026 06:21 TSİ |
| En iyi 3 çıkarılınca net | -$142,85 | veri: 25.11.2026 06:21 TSİ |
| En kötü 3 çıkarılınca net | -$5,27 | veri: 25.11.2026 06:21 TSİ |
| En iyi 3 + en kötü 3 çıkarılınca net | -$103,92 | veri: 25.11.2026 06:21 TSİ |

Pay: net > 0 iken hesaplanır; yetersiz işlemde (en iyi/kötü 3 için < 4, ikisi birden < 7) '-'.

## Ortak 3 — Maliyetler

| Kalem | Tutar | Brüt kâra oranı | Veri |
|---|---|---|---|
| Brüt kâr (yalnız brüt > 0 olan işlemlerin toplamı) | $325,07 | - | veri: 25.11.2026 06:21 TSİ |
| Toplam brüt K/Z (tüm işlemler) | +$12,52 | - | veri: 25.11.2026 06:21 TSİ |
| Komisyon | $58,07 | %17,9 | veri: 25.11.2026 06:21 TSİ |
| Fonlama (ödenen) | -$1,36 | %0,4 | veri: 25.11.2026 06:21 TSİ |
| Komisyon + fonlama | $56,71 | %17,4 | veri: 25.11.2026 06:21 TSİ |
| Kayma (giriş+çıkış, planlanana göre; brüte ZATEN işlenmiştir) | +$94,51 | %29,1 | veri: 25.11.2026 06:21 TSİ |
| Komisyon + fonlama + kayma | $151,22 | %46,5 | veri: 25.11.2026 06:21 TSİ |

Net K/Z = brüt - komisyon - fonlama (kayma fiyatlara işlendiğinden ayrıca düşülmez).

## Ortak 6 — Girişteki piyasa rejimine göre sonuç

| Rejim | İşlem | Net K/Z | Kazanma | Veri |
|---|---|---|---|---|
| trend_up | 7 | -$11,78 | %42,9 | veri: 24.11.2026 20:15 TSİ |
| trend_down | 69 | -$10,17 | %43,5 | veri: 25.11.2026 06:21 TSİ |
| range | 3 | -$26,98 | %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 4 | +$4,73 | %50,0 | veri: 24.11.2026 13:30 TSİ |
| volatile | 0 | - | - | veri: işlem yok |

## Ortak 7 — 30 / 100 / 300 kapanan işleme ulaşma süresi

Süre: 7,6 gün (17.11.2026 18:00 TSİ → 25.11.2026 09:15 TSİ); kapanan 83; genel hız 10,87 işlem/gün; kol medyan hızı: işlemi olan 16 kol 0,458 işlem/gün, tüm 288 yapılandırılmış kol 0,000 işlem/gün (veri: 25.11.2026 09:15 TSİ).

| Hedef | Genel (güncel hızla) | Kol medyanı (işlemi olan kollar) | Kol medyanı (tüm kollar) | Hedefe ulaşan kol | Veri |
|---|---|---|---|---|---|
| 30 | ulaşıldı | 65 gün (9,3 hafta) | hesaplanamaz (hız 0) | 0 | veri: 25.11.2026 09:15 TSİ |
| 100 | 2 gün (0,2 hafta) | 218 gün (31,2 hafta) | hesaplanamaz (hız 0) | 0 | veri: 25.11.2026 09:15 TSİ |
| 300 | 20 gün (2,9 hafta) | 654 gün (93,5 hafta) | hesaplanamaz (hız 0) | 0 | veri: 25.11.2026 09:15 TSİ |

## ML 8 — Yapılandırılmış kollar: işlem açan / açmayan

Yapılandırılmış kol: 288 · ≥1 işlem açan: 19 · hiç açmayan: 269 (veri: 25.11.2026 09:15 TSİ)

| Kol | Aday (karar kaydı) | En sık skip_reason | Grup (filtre/rejim/veri/eşik/risk-limit) | Veri |
|---|---|---|---|---|
| T1@4h | 33 | stop_width=26, risk_denied=6, ml_filter=1 | eşik=26, risk/limit=6, filtre=1 | veri: 25.11.2026 03:00 TSİ |
| T1@1d | 1 | stop_width=1 | eşik=1 | veri: 20.11.2026 03:00 TSİ |
| R1@15m | 35 | risk_denied=32, etiket_duygu=3 | risk/limit=32, filtre=3 | veri: 25.11.2026 08:45 TSİ |
| R1@1h | 16 | risk_denied=11, etiket_duygu=3, arm_conflict=2 | risk/limit=13, filtre=3 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 11 | rr_below_min=9, etiket_duygu=2 | eşik=9, filtre=2 | veri: 20.11.2026 11:00 TSİ |
| R1@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1@1h | 50 | risk_denied=43, arm_conflict=5, etiket_duygu=2 | risk/limit=48, filtre=2 | veri: 25.11.2026 09:00 TSİ |
| B1@4h | 2 | risk_denied=2 | risk/limit=2 | veri: 24.11.2026 07:00 TSİ |
| S1@1d | 4 | stop_width=3, arm_conflict=1 | eşik=3, risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| F1@1h | 82 | risk_denied=55, stop_width=10, arm_conflict=8, rr_below_min=8, etiket_duygu=1 | risk/limit=63, eşik=18, filtre=1 | veri: 25.11.2026 08:00 TSİ |
| F1@4h | 5 | stop_width=3, risk_denied=1, rr_below_min=1 | eşik=4, risk/limit=1 | veri: 23.11.2026 23:00 TSİ |
| F1@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| M1@1d | 1 | risk_denied=1 | risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| HB1@1h | 4 | risk_denied=4 | risk/limit=4 | veri: 25.11.2026 05:00 TSİ |
| DL1@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| DL1@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| DL1@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| DL1@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@15m | 2 | stop_width=2 | eşik=2 | veri: 25.11.2026 08:00 TSİ |
| MF1-DELICI@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@15m | 10 | stop_width=7, risk_denied=3 | eşik=7, risk/limit=3 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@1h | 2 | stop_width=2 | eşik=2 | veri: 25.11.2026 09:00 TSİ |
| MF1-ICSAHTE@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@15m | 8 | stop_width=6, risk_denied=2 | eşik=6, risk/limit=2 | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@1h | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 09:00 TSİ |
| MF1-DISBAR@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@15m | 9 | stop_width=8, risk_denied=1 | eşik=8, risk/limit=1 | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@1h | 2 | risk_denied=1, stop_width=1 | risk/limit=1, eşik=1 | veri: 25.11.2026 09:00 TSİ |
| MF1-YUTAN@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@15m | 10 | stop_width=10 | eşik=10 | veri: 25.11.2026 09:00 TSİ |
| MF1-HARAMI@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@15m | 5 | stop_width=5 | eşik=5 | veri: 25.11.2026 09:00 TSİ |
| MF1-CIMBIZ@1h | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:00 TSİ |
| MF1-CIMBIZ@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@15m | 9 | stop_width=9 | eşik=9 | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@15m | 20 | stop_width=18, risk_denied=2 | eşik=18, risk/limit=2 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@1h | 7 | risk_denied=4, stop_width=3 | risk/limit=4, eşik=3 | veri: 25.11.2026 09:00 TSİ |
| MF1-ICCUBUK@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@15m | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@15m | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@1h | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:00 TSİ |
| F1-IKINCI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@15m | 5 | stop_width=5 | eşik=5 | veri: 25.11.2026 08:45 TSİ |
| H2-MINI@1h | 5 | risk_denied=3, stop_width=2 | risk/limit=3, eşik=2 | veri: 25.11.2026 09:00 TSİ |
| H2-MINI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@15m | 11 | risk_denied=7, stop_width=4 | risk/limit=7, eşik=4 | veri: 25.11.2026 08:45 TSİ |
| H2-YARI@1h | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:00 TSİ |
| H2-YARI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@15m | 2 | stop_width=2 | eşik=2 | veri: 25.11.2026 08:45 TSİ |
| R1-ALT@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@15m | 2 | stop_width=2 | eşik=2 | veri: 25.11.2026 08:45 TSİ |
| R1-ERKEN@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@15m | 5 | stop_width=4, rr_below_min=1 | eşik=5 | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@1h | 2 | rr_below_min=1, risk_denied=1 | eşik=1, risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| S1-OLCULU@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@15m | 8 | stop_width=8 | eşik=8 | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@1h | 2 | risk_denied=1, stop_width=1 | risk/limit=1, eşik=1 | veri: 25.11.2026 09:00 TSİ |
| T1-GERI3@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@15m | 11 | stop_width=9, risk_denied=2 | eşik=9, risk/limit=2 | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@15m | 6 | stop_width=4, risk_denied=2 | eşik=4, risk/limit=2 | veri: 25.11.2026 08:30 TSİ |
| TF1-FITIL@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| TF1-FITIL@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@1h | 3 | risk_denied=2, stop_width=1 | risk/limit=2, eşik=1 | veri: 25.11.2026 09:00 TSİ |
| GF1-BAYRAK@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@15m | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:30 TSİ |
| GF1-FLAMA@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@15m | 9 | risk_denied=6, stop_width=3 | risk/limit=6, eşik=3 | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@15m | 4 | risk_denied=2, stop_width=2 | risk/limit=2, eşik=2 | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| GF1-KAMA@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@15m | 19 | stop_width=16, risk_denied=3 | eşik=16, risk/limit=3 | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@1h | 2 | stop_width=2 | eşik=2 | veri: 25.11.2026 08:00 TSİ |
| GF1-KANAL@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| GF1-KUPA@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@15m | 11 | stop_width=10, risk_denied=1 | eşik=10, risk/limit=1 | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@15m | 5 | stop_width=4, risk_denied=1 | eşik=4, risk/limit=1 | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@1h | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:00 TSİ |
| GF1-SAHTE@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@15m | 4 | stop_width=2, risk_denied=2 | eşik=2, risk/limit=2 | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@15m | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 07:45 TSİ |
| GF1-UCGEN@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@15m | 6 | risk_denied=6 | risk/limit=6 | veri: 25.11.2026 09:00 TSİ |
| GF1-UCLU@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@15m | 13 | stop_width=12, risk_denied=1 | eşik=12, risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| GF1-YATAY@1h | 4 | stop_width=2, risk_denied=2 | eşik=2, risk/limit=2 | veri: 25.11.2026 09:00 TSİ |
| GF1-YATAY@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@15m | 65 | stop_width=63, risk_denied=2 | eşik=63, risk/limit=2 | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@1h | 3 | stop_width=3 | eşik=3 | veri: 25.11.2026 09:00 TSİ |
| IN1-BOLL@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@15m | 14 | stop_width=12, risk_denied=2 | eşik=12, risk/limit=2 | veri: 25.11.2026 09:00 TSİ |
| IN1-BOLLKIR@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@15m | 2 | risk_denied=1, stop_width=1 | risk/limit=1, eşik=1 | veri: 25.11.2026 08:00 TSİ |
| IN1-FIBO@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| IN1-FIBO@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@15m | 11 | risk_denied=6, stop_width=5 | risk/limit=6, eşik=5 | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@1h | 1 | arm_conflict=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| IN1-FIYATMA@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@15m | 6 | stop_width=4, risk_denied=2 | eşik=4, risk/limit=2 | veri: 25.11.2026 09:00 TSİ |
| IN1-HACIM@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| IN1-HACIM@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@15m | 33 | risk_denied=21, stop_width=12 | risk/limit=21, eşik=12 | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@1h | 1 | arm_conflict=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| IN1-HIZLIMA@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@15m | 7 | stop_width=6, risk_denied=1 | eşik=6, risk/limit=1 | veri: 25.11.2026 08:30 TSİ |
| IN1-KUMO@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@15m | 28 | risk_denied=17, stop_width=11 | risk/limit=17, eşik=11 | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@1h | 7 | risk_denied=7 | risk/limit=7 | veri: 25.11.2026 09:00 TSİ |
| IN1-MACD@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@15m | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:00 TSİ |
| IN1-MAGERI@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@15m | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:30 TSİ |
| IN1-RSI@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@15m | 35 | risk_denied=27, stop_width=8 | risk/limit=27, eşik=8 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@1h | 3 | risk_denied=3 | risk/limit=3 | veri: 25.11.2026 09:00 TSİ |
| IN1-RSI2@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@15m | 2 | stop_width=1, risk_denied=1 | eşik=1, risk/limit=1 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@1h | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:00 TSİ |
| IN1-RSIDONUS@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@15m | 8 | stop_width=7, risk_denied=1 | eşik=7, risk/limit=1 | veri: 25.11.2026 08:45 TSİ |
| IN1-TK@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@15m | 3 | risk_denied=2, stop_width=1 | risk/limit=2, eşik=1 | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@15m | 49 | risk_denied=30, stop_width=19 | risk/limit=30, eşik=19 | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@1h | 17 | risk_denied=16, arm_conflict=1 | risk/limit=17 | veri: 25.11.2026 09:00 TSİ |
| PA2-EMIRBLOK@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@15m | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 07:15 TSİ |
| PA2-BOLGE@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@15m | 8 | risk_denied=6, stop_width=2 | risk/limit=6, eşik=2 | veri: 25.11.2026 08:15 TSİ |
| PA2-FVG@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@15m | 2 | stop_width=1, risk_denied=1 | eşik=1, risk/limit=1 | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@1h | 2 | stop_width=2 | eşik=2 | veri: 25.11.2026 08:00 TSİ |
| PA2-ONCEKI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@15m | 6 | stop_width=6 | eşik=6 | veri: 25.11.2026 09:00 TSİ |
| PA2-TCIZGI@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@15m | 2 | stop_width=2 | eşik=2 | veri: 25.11.2026 09:00 TSİ |
| PA2-SEVIYE@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@4h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@1d | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TUKENIS@15m | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TUKENIS@1h | 0 (aday üretmedi) | - | - | veri: 25.11.2026 09:15 TSİ |

Açan kollar: T1@15m, T1@1h, TF1@15m, TF1@4h, TF1@1d, B1@15m, B1@1h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, F1@15m, M1@1h, M1@4h, M1@15m

### Kol bazında neden işlem açmıyor (tüm kayıt / son 12 saat)

Pencere: «tüm kayıt» = kilitli dönem dışındaki tüm karar satırları; «son 12 saat» = veri kesitinden (25.11.2026 09:15 TSİ) geriye 12 saat. Kâğıt risk limitleri kayıt süresince gevşetilmiş olabilir; eski `risk_denied` sayıları o günkü limitlere aittir, güncel durumu «son 12 saat» sütunları gösterir. Risk reddi `risk_reason` metninden limit adına çevrilir (max_open_risk, max_same_dir_risk, daily_max_loss ...).

| Kol | Aday (tüm) | Girdi (tüm) | Skip (tüm) | Aday (12s) | Girdi (12s) | Skip (12s) | Veri |
|---|---|---|---|---|---|---|---|
| T1@15m | 617 | 10 | stop_width=314; risk_denied=244 (margin_total=113, max_same_dir_risk=49, daily_max_loss=44, daily_limit=19, korelasyon_grubu=17, diğer=2); ml_filter=39; arm_conflict=6 (M1@1h=3, T1@1h=1, M1@4h=1); order_failed=2; etiket_duygu=2 | 37 | 0 | risk_denied=31 (max_same_dir_risk=17, korelasyon_grubu=13, margin_total=1); stop_width=6 | veri: 25.11.2026 09:15 TSİ |
| T1@1h | 181 | 10 | stop_width=85; risk_denied=63 (margin_total=31, max_same_dir_risk=19, daily_max_loss=10, korelasyon_grubu=3); ml_filter=19; veto_blocked=3; veto_missing=1 | 11 | 0 | risk_denied=8 (max_same_dir_risk=7, korelasyon_grubu=1); stop_width=3 | veri: 25.11.2026 09:15 TSİ |
| T1@4h | 33 | 0 | stop_width=26; risk_denied=6 (max_same_dir_risk=4, daily_max_loss=1, margin_total=1); ml_filter=1 | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| T1@1d | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1@15m | 35 | 0 | risk_denied=32 (margin_total=27, diğer=4, daily_max_loss=1); etiket_duygu=3 | 2 | 0 | risk_denied=2 (diğer=2) | veri: 25.11.2026 09:15 TSİ |
| R1@1h | 16 | 0 | risk_denied=11 (margin_total=9, daily_max_loss=2); etiket_duygu=3; arm_conflict=2 (R1@4h=1) | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1@4h | 11 | 0 | rr_below_min=9; etiket_duygu=2 | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| TF1@15m | 170 | 7 | risk_denied=135 (margin_total=53, max_same_dir_risk=43, daily_max_loss=20, korelasyon_grubu=11, daily_limit=8); arm_conflict=16 (TF1@1h=5, T1@1h=4, M1@1h=3, H2@1h=2, TF1@4h=1, S1@1h=1); etiket_duygu=6; cluster_cap=6 (hisse_teknoloji=6) | 12 | 0 | risk_denied=11 (max_same_dir_risk=8, korelasyon_grubu=2, margin_total=1); arm_conflict=1 (H2@1h=1) | veri: 25.11.2026 09:15 TSİ |
| TF1@1h | 50 | 0 | risk_denied=43 (margin_total=12, max_same_dir_risk=10, korelasyon_grubu=10, daily_max_loss=8, daily_limit=3); arm_conflict=5 (TF1@4h=2, M1@4h=2, S1@4h=1); etiket_duygu=2 | 5 | 0 | risk_denied=5 (korelasyon_grubu=3, max_same_dir_risk=2) | veri: 25.11.2026 09:15 TSİ |
| TF1@4h | 15 | 1 | risk_denied=10 (daily_max_loss=6, max_same_dir_risk=2, margin_total=1, daily_limit=1); etiket_duygu=2; cluster_cap=2 (hisse_teknoloji=2) | 1 | 1 | - | veri: 25.11.2026 09:15 TSİ |
| TF1@1d | 10 | 2 | risk_denied=8 (margin_total=3, daily_max_loss=2, korelasyon_grubu=2, max_same_dir_risk=1) | 3 | 0 | risk_denied=3 (korelasyon_grubu=2, margin_total=1) | veri: 25.11.2026 09:15 TSİ |
| B1@15m | 48 | 1 | risk_denied=27 (margin_total=11, daily_max_loss=7, max_same_dir_risk=7, daily_limit=1, korelasyon_grubu=1); stop_width=15; arm_conflict=4 (TF1@1h=2, S1@1h=2); entry_gate_closed=1 | 3 | 0 | risk_denied=3 (margin_total=2, max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| B1@1h | 17 | 2 | risk_denied=9 (margin_total=4, daily_max_loss=4, korelasyon_grubu=1); stop_width=4; arm_conflict=2 (TF1@4h=1, M1@4h=1) | 1 | 0 | risk_denied=1 (korelasyon_grubu=1) | veri: 25.11.2026 09:15 TSİ |
| B1@4h | 2 | 0 | risk_denied=2 (margin_total=1, max_same_dir_risk=1) | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1@1d | 2 | 1 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| H2@15m | 198 | 8 | risk_denied=138 (margin_total=47, daily_max_loss=34, max_same_dir_risk=32, korelasyon_grubu=14, daily_limit=11); stop_width=34; arm_conflict=16 (TF1@15m=11, M1@1h=1, M1@4h=1, T1@15m=1, TF1@1h=1); entry_gate_closed=1; order_failed=1 | 20 | 2 | risk_denied=18 (max_same_dir_risk=9, korelasyon_grubu=8, margin_total=1) | veri: 25.11.2026 09:15 TSİ |
| H2@1h | 65 | 1 | risk_denied=49 (margin_total=25, korelasyon_grubu=10, max_same_dir_risk=7, daily_max_loss=7); stop_width=9; arm_conflict=5 (H2@4h=2, TF1@1h=1, TF1@4h=1, M1@4h=1); etiket_duygu=1 | 13 | 0 | risk_denied=12 (korelasyon_grubu=8, max_same_dir_risk=3, margin_total=1); stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| H2@4h | 18 | 1 | risk_denied=15 (margin_total=10, daily_max_loss=5); stop_width=2 | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| H2@1d | 3 | 1 | arm_conflict=1 (TF1@1d=1); risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| S1@15m | 466 | 8 | risk_denied=221 (margin_total=105, max_same_dir_risk=47, daily_max_loss=34, daily_limit=18, korelasyon_grubu=13, diğer=4); stop_width=182; arm_conflict=45 (TF1@15m=15, T1@15m=14, M1@1h=5, H2@15m=4, T1@1h=2, B1@15m=1, TF1@1h=1, S1@1h=1, F1@1h=1); etiket_duygu=7; cluster_cap=3 (hisse_teknoloji=3) | 45 | 0 | risk_denied=34 (max_same_dir_risk=15, korelasyon_grubu=11, margin_total=5, diğer=3); stop_width=11 | veri: 25.11.2026 09:15 TSİ |
| S1@1h | 100 | 4 | risk_denied=48 (margin_total=26, max_same_dir_risk=12, korelasyon_grubu=6, daily_max_loss=4); stop_width=36; arm_conflict=11 (T1@1h=3, H2@1h=2, TF1@1h=2, H2@4h=2, T1@4h=1, TF1@4h=1); order_failed=1 | 12 | 1 | risk_denied=10 (korelasyon_grubu=5, max_same_dir_risk=5); stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| S1@4h | 18 | 1 | stop_width=10; risk_denied=4 (margin_total=2, daily_max_loss=1, daily_limit=1); arm_conflict=3 (TF1@4h=2, H2@1d=1) | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| S1@1d | 4 | 0 | stop_width=3; arm_conflict=1 (TF1@1d=1) | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| F1@15m | 319 | 15 | risk_denied=165 (margin_total=117, daily_max_loss=20, diğer=15, max_same_dir_risk=7, daily_limit=6); stop_width=76; rr_below_min=37; arm_conflict=15 (M1@1h=7, R1@15m=3, M1@4h=3, T1@1h=2); etiket_duygu=7; entry_gate_closed=3; cluster_cap=1 (hisse_teknoloji=1) | 6 | 0 | risk_denied=6 (diğer=6) | veri: 25.11.2026 09:15 TSİ |
| F1@1h | 82 | 0 | risk_denied=55 (margin_total=40, diğer=6, daily_max_loss=5, daily_limit=2, max_same_dir_risk=2); stop_width=10; arm_conflict=8 (R1@1h=4, M1@4h=4); rr_below_min=8; etiket_duygu=1 | 3 | 0 | risk_denied=3 (diğer=3) | veri: 25.11.2026 09:15 TSİ |
| F1@4h | 5 | 0 | stop_width=3; risk_denied=1 (daily_max_loss=1); rr_below_min=1 | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| F1@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| M1@1h | 430 | 4 | risk_denied=256 (margin_total=224, daily_max_loss=21, diğer=9, max_same_dir_risk=2); etiket_rejim=116; arm_conflict=54 (S1@1h=16, F1@1h=12, T1@1h=10, M1@4h=8, H2@4h=3, TF1@4h=1, B1@1h=1, TF1@1h=1, B1@1d=1, H2@1h=1) | 7 | 0 | risk_denied=6 (diğer=4, max_same_dir_risk=2); arm_conflict=1 (H2@1h=1) | veri: 25.11.2026 09:15 TSİ |
| M1@4h | 124 | 2 | risk_denied=114 (margin_total=73, daily_limit=17, max_same_dir_risk=15, diğer=7, daily_max_loss=2); arm_conflict=8 (H2@4h=2, S1@4h=2, R1@4h=1, H2@1d=1, T1@4h=1, M1@1d=1) | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| M1@15m | 1445 | 13 | risk_denied=1235 (margin_total=470, max_same_dir_risk=237, daily_max_loss=214, daily_limit=193, diğer=102, korelasyon_grubu=18, toplam_buyukluk=1); arm_conflict=96 (S1@15m=30, T1@15m=18, M1@1h=14, T1@1h=9, H2@15m=6, TF1@15m=5, H2@1h=4, F1@15m=4, M1@4h=4, TF1@4h=1, B1@15m=1); etiket_rejim=89; order_failed=12 | 78 | 2 | risk_denied=73 (max_same_dir_risk=34, diğer=34, margin_total=5); arm_conflict=3 (S1@15m=1, TF1@15m=1, B1@15m=1) | veri: 25.11.2026 09:15 TSİ |
| M1@1d | 1 | 0 | risk_denied=1 (diğer=1) | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| HB1@1h | 4 | 0 | risk_denied=4 (korelasyon_grubu=3, max_same_dir_risk=1) | 2 | 0 | risk_denied=2 (korelasyon_grubu=2) | veri: 25.11.2026 09:15 TSİ |
| DL1@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| DL1@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| DL1@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| DL1@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@15m | 2 | 0 | stop_width=2 | 2 | 0 | stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@15m | 10 | 0 | stop_width=7; risk_denied=3 (diğer=2, max_same_dir_risk=1) | 10 | 0 | stop_width=7; risk_denied=3 (diğer=2, max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@1h | 2 | 0 | stop_width=2 | 2 | 0 | stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@15m | 8 | 0 | stop_width=6; risk_denied=2 (diğer=2) | 8 | 0 | stop_width=6; risk_denied=2 (diğer=2) | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@1h | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@15m | 9 | 0 | stop_width=8; risk_denied=1 (diğer=1) | 9 | 0 | stop_width=8; risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@1h | 2 | 0 | risk_denied=1 (max_same_dir_risk=1); stop_width=1 | 2 | 0 | risk_denied=1 (max_same_dir_risk=1); stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@15m | 10 | 0 | stop_width=10 | 10 | 0 | stop_width=10 | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@15m | 5 | 0 | stop_width=5 | 5 | 0 | stop_width=5 | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@1h | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@15m | 9 | 0 | stop_width=9 | 9 | 0 | stop_width=9 | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@15m | 20 | 0 | stop_width=18; risk_denied=2 (korelasyon_grubu=1, max_same_dir_risk=1) | 20 | 0 | stop_width=18; risk_denied=2 (korelasyon_grubu=1, max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@1h | 7 | 0 | risk_denied=4 (max_same_dir_risk=4); stop_width=3 | 7 | 0 | risk_denied=4 (max_same_dir_risk=4); stop_width=3 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@15m | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@15m | 1 | 0 | risk_denied=1 (diğer=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@1h | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@15m | 5 | 0 | stop_width=5 | 5 | 0 | stop_width=5 | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@1h | 5 | 0 | risk_denied=3 (korelasyon_grubu=3); stop_width=2 | 5 | 0 | risk_denied=3 (korelasyon_grubu=3); stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@15m | 11 | 0 | risk_denied=7 (korelasyon_grubu=4, max_same_dir_risk=3); stop_width=4 | 11 | 0 | risk_denied=7 (korelasyon_grubu=4, max_same_dir_risk=3); stop_width=4 | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@1h | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@15m | 2 | 0 | stop_width=2 | 2 | 0 | stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@15m | 2 | 0 | stop_width=2 | 2 | 0 | stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@15m | 5 | 0 | stop_width=4; rr_below_min=1 | 5 | 0 | stop_width=4; rr_below_min=1 | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@1h | 2 | 0 | rr_below_min=1; risk_denied=1 (max_same_dir_risk=1) | 2 | 0 | rr_below_min=1; risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@15m | 8 | 0 | stop_width=8 | 8 | 0 | stop_width=8 | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@1h | 2 | 0 | risk_denied=1 (korelasyon_grubu=1); stop_width=1 | 2 | 0 | risk_denied=1 (korelasyon_grubu=1); stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@15m | 11 | 0 | stop_width=9; risk_denied=2 (max_same_dir_risk=2) | 11 | 0 | stop_width=9; risk_denied=2 (max_same_dir_risk=2) | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@15m | 6 | 0 | stop_width=4; risk_denied=2 (max_same_dir_risk=2) | 6 | 0 | stop_width=4; risk_denied=2 (max_same_dir_risk=2) | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@1h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@1h | 3 | 0 | risk_denied=2 (diğer=1, max_same_dir_risk=1); stop_width=1 | 3 | 0 | risk_denied=2 (diğer=1, max_same_dir_risk=1); stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@15m | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@15m | 9 | 0 | risk_denied=6 (max_same_dir_risk=4, diğer=2); stop_width=3 | 9 | 0 | risk_denied=6 (max_same_dir_risk=4, diğer=2); stop_width=3 | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@15m | 4 | 0 | risk_denied=2 (diğer=2); stop_width=2 | 4 | 0 | risk_denied=2 (diğer=2); stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@1h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@15m | 19 | 0 | stop_width=16; risk_denied=3 (diğer=3) | 19 | 0 | stop_width=16; risk_denied=3 (diğer=3) | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@1h | 2 | 0 | stop_width=2 | 2 | 0 | stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@1h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@15m | 11 | 0 | stop_width=10; risk_denied=1 (max_same_dir_risk=1) | 11 | 0 | stop_width=10; risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@15m | 5 | 0 | stop_width=4; risk_denied=1 (diğer=1) | 5 | 0 | stop_width=4; risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@1h | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@15m | 4 | 0 | stop_width=2; risk_denied=2 (max_same_dir_risk=1, diğer=1) | 4 | 0 | stop_width=2; risk_denied=2 (max_same_dir_risk=1, diğer=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@15m | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@15m | 6 | 0 | risk_denied=6 (max_same_dir_risk=5, margin_total=1) | 6 | 0 | risk_denied=6 (max_same_dir_risk=5, margin_total=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@15m | 13 | 0 | stop_width=12; risk_denied=1 (max_same_dir_risk=1) | 13 | 0 | stop_width=12; risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@1h | 4 | 0 | stop_width=2; risk_denied=2 (max_same_dir_risk=2) | 4 | 0 | stop_width=2; risk_denied=2 (max_same_dir_risk=2) | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@15m | 65 | 0 | stop_width=63; risk_denied=2 (diğer=2) | 65 | 0 | stop_width=63; risk_denied=2 (diğer=2) | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@1h | 3 | 0 | stop_width=3 | 3 | 0 | stop_width=3 | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@15m | 14 | 0 | stop_width=12; risk_denied=2 (max_same_dir_risk=2) | 14 | 0 | stop_width=12; risk_denied=2 (max_same_dir_risk=2) | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@15m | 2 | 0 | risk_denied=1 (diğer=1); stop_width=1 | 2 | 0 | risk_denied=1 (diğer=1); stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@1h | 1 | 0 | risk_denied=1 (diğer=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@15m | 11 | 0 | risk_denied=6 (diğer=3, korelasyon_grubu=3); stop_width=5 | 11 | 0 | risk_denied=6 (diğer=3, korelasyon_grubu=3); stop_width=5 | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@1h | 1 | 0 | arm_conflict=1 (IN1-RSI2@1h=1) | 1 | 0 | arm_conflict=1 (IN1-RSI2@1h=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@15m | 6 | 0 | stop_width=4; risk_denied=2 (max_same_dir_risk=2) | 6 | 0 | stop_width=4; risk_denied=2 (max_same_dir_risk=2) | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@1h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@15m | 33 | 0 | risk_denied=21 (korelasyon_grubu=11, diğer=7, max_same_dir_risk=3); stop_width=12 | 33 | 0 | risk_denied=21 (korelasyon_grubu=11, diğer=7, max_same_dir_risk=3); stop_width=12 | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@1h | 1 | 0 | arm_conflict=1 (IN1-RSI2@1h=1) | 1 | 0 | arm_conflict=1 (IN1-RSI2@1h=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@15m | 7 | 0 | stop_width=6; risk_denied=1 (max_same_dir_risk=1) | 7 | 0 | stop_width=6; risk_denied=1 (max_same_dir_risk=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@15m | 28 | 0 | risk_denied=17 (korelasyon_grubu=8, diğer=7, max_same_dir_risk=2); stop_width=11 | 28 | 0 | risk_denied=17 (korelasyon_grubu=8, diğer=7, max_same_dir_risk=2); stop_width=11 | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@1h | 7 | 0 | risk_denied=7 (diğer=5, korelasyon_grubu=1, margin_total=1) | 7 | 0 | risk_denied=7 (diğer=5, korelasyon_grubu=1, margin_total=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@15m | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@15m | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@15m | 35 | 0 | risk_denied=27 (korelasyon_grubu=20, diğer=5, margin_total=1, max_same_dir_risk=1); stop_width=8 | 35 | 0 | risk_denied=27 (korelasyon_grubu=20, diğer=5, margin_total=1, max_same_dir_risk=1); stop_width=8 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@1h | 3 | 0 | risk_denied=3 (margin_total=2, diğer=1) | 3 | 0 | risk_denied=3 (margin_total=2, diğer=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@15m | 2 | 0 | stop_width=1; risk_denied=1 (diğer=1) | 2 | 0 | stop_width=1; risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@1h | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@15m | 8 | 0 | stop_width=7; risk_denied=1 (diğer=1) | 8 | 0 | stop_width=7; risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@15m | 3 | 0 | risk_denied=2 (diğer=2); stop_width=1 | 3 | 0 | risk_denied=2 (diğer=2); stop_width=1 | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@15m | 49 | 0 | risk_denied=30 (korelasyon_grubu=15, diğer=13, max_same_dir_risk=2); stop_width=19 | 49 | 0 | risk_denied=30 (korelasyon_grubu=15, diğer=13, max_same_dir_risk=2); stop_width=19 | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@1h | 17 | 0 | risk_denied=16 (korelasyon_grubu=9, diğer=4, margin_total=2, max_same_dir_risk=1); arm_conflict=1 (IN1-MACD@1h=1) | 17 | 0 | risk_denied=16 (korelasyon_grubu=9, diğer=4, margin_total=2, max_same_dir_risk=1); arm_conflict=1 (IN1-MACD@1h=1) | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@15m | 1 | 0 | risk_denied=1 (diğer=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@15m | 8 | 0 | risk_denied=6 (max_same_dir_risk=4, korelasyon_grubu=2); stop_width=2 | 8 | 0 | risk_denied=6 (max_same_dir_risk=4, korelasyon_grubu=2); stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@15m | 2 | 0 | stop_width=1; risk_denied=1 (diğer=1) | 2 | 0 | stop_width=1; risk_denied=1 (diğer=1) | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@1h | 2 | 0 | stop_width=2 | 2 | 0 | stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@15m | 6 | 0 | stop_width=6 | 6 | 0 | stop_width=6 | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@15m | 2 | 0 | stop_width=2 | 2 | 0 | stop_width=2 | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@4h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@1d | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TUKENIS@15m | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TUKENIS@1h | 0 | 0 | - | 0 | 0 | - | veri: 25.11.2026 09:15 TSİ |

Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta R1@1d, F1@1d, DL1@15m, DL1@1h, DL1@4h, DL1@1d, MF1-YILDIZ@15m, MF1-YILDIZ@1h, MF1-YILDIZ@4h, MF1-YILDIZ@1d, MF1-UCASKER@15m, MF1-UCASKER@1h, MF1-UCASKER@4h, MF1-UCASKER@1d, MF1-DELICI@1h, MF1-DELICI@4h, MF1-DELICI@1d, MF1-ICSAHTE@4h, MF1-ICSAHTE@1d, MF1-DISBAR@4h, MF1-DISBAR@1d, MF1-YUTAN@4h, MF1-YUTAN@1d, MF1-HARAMI@1h, MF1-HARAMI@4h, MF1-HARAMI@1d, MF1-TERSCEKIC@15m, MF1-TERSCEKIC@1h, MF1-TERSCEKIC@4h, MF1-TERSCEKIC@1d, MF1-CIMBIZ@4h, MF1-CIMBIZ@1d, MF1-PINBAR@1h, MF1-PINBAR@4h, MF1-PINBAR@1d, MF1-ICCUBUK@4h, MF1-ICCUBUK@1d, MF1-MARUBOZU@1h, MF1-MARUBOZU@4h, MF1-MARUBOZU@1d, B1-BOLGE@15m, B1-BOLGE@1h, B1-BOLGE@4h, B1-BOLGE@1d, B1-MUM@15m, B1-MUM@1h, B1-MUM@4h, B1-MUM@1d, F1-IKINCI@4h, F1-IKINCI@1d, H2-MINI@4h, H2-MINI@1d, H2-YARI@4h, H2-YARI@1d, R1-ALT@1h, R1-ALT@4h, R1-ALT@1d, R1-ERKEN@1h, R1-ERKEN@4h, R1-ERKEN@1d, R1-HA@15m, R1-HA@1h, R1-HA@4h, R1-HA@1d, S1-HACIM@15m, S1-HACIM@1h, S1-HACIM@4h, S1-HACIM@1d, S1-OLCULU@4h, S1-OLCULU@1d, T1-GERI3@4h, T1-GERI3@1d, T1-SEVIYE@1h, T1-SEVIYE@4h, T1-SEVIYE@1d, TF1-FITIL@4h, TF1-FITIL@1d, TF1-HACIM@15m, TF1-HACIM@1h, TF1-HACIM@4h, TF1-HACIM@1d, GF1-BAYRAK@15m, GF1-BAYRAK@4h, GF1-BAYRAK@1d, GF1-FLAMA@1h, GF1-FLAMA@4h, GF1-FLAMA@1d, GF1-IKILI@1h, GF1-IKILI@4h, GF1-IKILI@1d, GF1-KAMA@4h, GF1-KAMA@1d, GF1-KANAL@4h, GF1-KANAL@1d, GF1-KUPA@15m, GF1-KUPA@4h, GF1-KUPA@1d, GF1-OBO@15m, GF1-OBO@1h, GF1-OBO@4h, GF1-OBO@1d, GF1-RETEST@1h, GF1-RETEST@4h, GF1-RETEST@1d, GF1-SAHTE@4h, GF1-SAHTE@1d, GF1-TREND@1h, GF1-TREND@4h, GF1-TREND@1d, GF1-UCGEN@1h, GF1-UCGEN@4h, GF1-UCGEN@1d, GF1-UCLU@1h, GF1-UCLU@4h, GF1-UCLU@1d, GF1-YATAY@4h, GF1-YATAY@1d, IN1-BOLL@4h, IN1-BOLL@1d, IN1-BOLLKIR@1h, IN1-BOLLKIR@4h, IN1-BOLLKIR@1d, IN1-FIBO@4h, IN1-FIBO@1d, IN1-FIYATMA@4h, IN1-FIYATMA@1d, IN1-HACIM@4h, IN1-HACIM@1d, IN1-HIZLIMA@4h, IN1-HIZLIMA@1d, IN1-KUMO@1h, IN1-KUMO@4h, IN1-KUMO@1d, IN1-MACD@4h, IN1-MACD@1d, IN1-MAGERI@1h, IN1-MAGERI@4h, IN1-MAGERI@1d, IN1-MAKESISIM@15m, IN1-MAKESISIM@1h, IN1-MAKESISIM@4h, IN1-MAKESISIM@1d, IN1-RSI@1h, IN1-RSI@4h, IN1-RSI@1d, IN1-RSI2@4h, IN1-RSI2@1d, IN1-RSIDONUS@4h, IN1-RSIDONUS@1d, IN1-STOK@15m, IN1-STOK@1h, IN1-STOK@4h, IN1-STOK@1d, IN1-TK@1h, IN1-TK@4h, IN1-TK@1d, IN1-UYUMSUZ@1h, IN1-UYUMSUZ@4h, IN1-UYUMSUZ@1d, PA2-EMIRBLOK@15m, PA2-EMIRBLOK@1h, PA2-EMIRBLOK@4h, PA2-EMIRBLOK@1d, PA2-BOLGE@1h, PA2-BOLGE@4h, PA2-BOLGE@1d, PA2-FVG@1h, PA2-FVG@4h, PA2-FVG@1d, PA2-ONCEKI@4h, PA2-TCIZGI@1h, PA2-TCIZGI@4h, PA2-TCIZGI@1d, PA2-SEVIYE@1h, PA2-SEVIYE@4h, PA2-SEVIYE@1d, PA2-UCVURUS@15m, PA2-UCVURUS@1h, PA2-UCVURUS@4h, PA2-UCVURUS@1d, PA2-TUKENIS@15m, PA2-TUKENIS@1h · yalnız son 12 saatte T1@1d, R1@1h, R1@4h, B1@4h, B1@1d, H2@4h, H2@1d, S1@1d, F1@4h, M1@4h, M1@1d.

Aday = `decision_events` satırı. Golge kararlar (shadow) ve hiç kayda girmeyen sinyaller bu sayıya girmez.

### stop_width skip'leri: dar / geniş (son 12 saat / tüm kayıt)

İzinli bant: stop/ATR 0.5 – 2.0 (signals.STOP_DIST_MIN_ATR / STOP_DIST_MAX_ATR). Yalnız ölçüm; davranış değişmez. Dar/geniş ayrımı kayıtlı `features.stop_dist_atr` değerinin banta göre karşılaştırılmasından türetilir; medyan = reddedilen adayların medyan stop/ATR'si.

| Kol | Son 12s | Tüm kayıt | Veri |
|---|---|---|---|
| T1@15m | dar=0, geniş=6 · medyan 2.90 | dar=0, geniş=314 · medyan 2.73 | veri: 25.11.2026 09:15 TSİ |
| T1@1h | dar=0, geniş=3 · medyan 2.23 | dar=0, geniş=85 · medyan 2.49 | veri: 25.11.2026 09:15 TSİ |
| T1@4h | - | dar=0, geniş=26 · medyan 2.49 | veri: 25.11.2026 09:15 TSİ |
| T1@1d | - | dar=0, geniş=1 · medyan 3.45 | veri: 25.11.2026 09:15 TSİ |
| R1@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| R1@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| B1@15m | - | dar=0, geniş=15 · medyan 3.44 | veri: 25.11.2026 09:15 TSİ |
| B1@1h | - | dar=1, geniş=3 · medyan 3.40 | veri: 25.11.2026 09:15 TSİ |
| B1@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| B1@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| H2@15m | - | dar=0, geniş=34 · medyan 2.91 | veri: 25.11.2026 09:15 TSİ |
| H2@1h | dar=0, geniş=1 · medyan 3.23 | dar=0, geniş=9 · medyan 3.70 | veri: 25.11.2026 09:15 TSİ |
| H2@4h | - | dar=0, geniş=2 · medyan 3.48 | veri: 25.11.2026 09:15 TSİ |
| H2@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| S1@15m | dar=0, geniş=11 · medyan 3.24 | dar=0, geniş=182 · medyan 3.34 | veri: 25.11.2026 09:15 TSİ |
| S1@1h | dar=0, geniş=1 · medyan 3.13 | dar=0, geniş=36 · medyan 3.44 | veri: 25.11.2026 09:15 TSİ |
| S1@4h | dar=0, geniş=1 · medyan 3.34 | dar=0, geniş=10 · medyan 3.91 | veri: 25.11.2026 09:15 TSİ |
| S1@1d | - | dar=0, geniş=3 · medyan 3.48 | veri: 25.11.2026 09:15 TSİ |
| F1@15m | - | dar=0, geniş=76 · medyan 2.50 | veri: 25.11.2026 09:15 TSİ |
| F1@1h | - | dar=0, geniş=10 · medyan 2.46 | veri: 25.11.2026 09:15 TSİ |
| F1@4h | - | dar=0, geniş=3 · medyan 2.77 | veri: 25.11.2026 09:15 TSİ |
| F1@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| M1@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| M1@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| M1@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| M1@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| HB1@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| DL1@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| DL1@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| DL1@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| DL1@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YILDIZ@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-UCASKER@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@15m | dar=0, geniş=0, ?=2 · medyan 1.05 | dar=0, geniş=0, ?=2 · medyan 1.05 | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DELICI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@15m | dar=1, geniş=0, ?=6 · medyan 0.83 | dar=1, geniş=0, ?=6 · medyan 0.83 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@1h | dar=1, geniş=0, ?=1 · medyan 0.57 | dar=1, geniş=0, ?=1 · medyan 0.57 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@15m | dar=0, geniş=0, ?=6 · medyan 1.18 | dar=0, geniş=0, ?=6 · medyan 1.18 | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@1h | dar=0, geniş=0, ?=1 · medyan 0.80 | dar=0, geniş=0, ?=1 · medyan 0.80 | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@15m | dar=0, geniş=0, ?=8 · medyan 0.77 | dar=0, geniş=0, ?=8 · medyan 0.77 | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@1h | dar=0, geniş=0, ?=1 · medyan 0.50 | dar=0, geniş=0, ?=1 · medyan 0.50 | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@15m | dar=1, geniş=0, ?=9 · medyan 0.57 | dar=1, geniş=0, ?=9 · medyan 0.57 | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-HARAMI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-TERSCEKIC@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@15m | dar=3, geniş=0, ?=2 · medyan 0.46 | dar=3, geniş=0, ?=2 · medyan 0.46 | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@1h | dar=1, geniş=0 · medyan 0.50 | dar=1, geniş=0 · medyan 0.50 | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-CIMBIZ@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@15m | dar=2, geniş=1, ?=6 · medyan 0.85 | dar=2, geniş=1, ?=6 · medyan 0.85 | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-PINBAR@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@15m | dar=0, geniş=1, ?=17 · medyan 1.16 | dar=0, geniş=1, ?=17 · medyan 1.16 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@1h | dar=0, geniş=0, ?=3 · medyan 1.20 | dar=0, geniş=0, ?=3 · medyan 1.20 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@15m | dar=0, geniş=0, ?=1 · medyan 1.76 | dar=0, geniş=0, ?=1 · medyan 1.76 | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| MF1-MARUBOZU@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-BOLGE@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| B1-MUM@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@1h | dar=0, geniş=0, ?=1 · medyan 0.90 | dar=0, geniş=0, ?=1 · medyan 0.90 | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| F1-IKINCI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@15m | dar=0, geniş=0, ?=5 · medyan 1.01 | dar=0, geniş=0, ?=5 · medyan 1.01 | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@1h | dar=0, geniş=0, ?=2 · medyan 0.72 | dar=0, geniş=0, ?=2 · medyan 0.72 | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-MINI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@15m | dar=0, geniş=1, ?=3 · medyan 1.68 | dar=0, geniş=1, ?=3 · medyan 1.68 | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@1h | dar=0, geniş=0, ?=1 · medyan 1.39 | dar=0, geniş=0, ?=1 · medyan 1.39 | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@15m | dar=0, geniş=0, ?=2 · medyan 0.81 | dar=0, geniş=0, ?=2 · medyan 0.81 | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ALT@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@15m | dar=0, geniş=0, ?=2 · medyan 0.81 | dar=0, geniş=0, ?=2 · medyan 0.81 | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-ERKEN@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| R1-HA@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-HACIM@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@15m | dar=0, geniş=3, ?=1 · medyan 2.38 | dar=0, geniş=3, ?=1 · medyan 2.38 | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| S1-OLCULU@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@15m | dar=0, geniş=0, ?=8 · medyan 1.15 | dar=0, geniş=0, ?=8 · medyan 1.15 | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@1h | dar=0, geniş=0, ?=1 · medyan 0.76 | dar=0, geniş=0, ?=1 · medyan 0.76 | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-GERI3@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@15m | dar=0, geniş=1, ?=8 · medyan 1.13 | dar=0, geniş=1, ?=8 · medyan 1.13 | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@15m | dar=0, geniş=0, ?=4 · medyan 1.36 | dar=0, geniş=0, ?=4 · medyan 1.36 | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| TF1-HACIM@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@1h | dar=0, geniş=0, ?=1 · medyan 1.31 | dar=0, geniş=0, ?=1 · medyan 1.31 | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-BAYRAK@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@15m | dar=0, geniş=1 · medyan 2.25 | dar=0, geniş=1 · medyan 2.25 | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-FLAMA@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@15m | dar=0, geniş=3 · medyan 3.02 | dar=0, geniş=3 · medyan 3.02 | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-IKILI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@15m | dar=0, geniş=2 · medyan 2.42 | dar=0, geniş=2 · medyan 2.42 | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@15m | dar=5, geniş=0, ?=11 · medyan 0.77 | dar=5, geniş=0, ?=11 · medyan 0.77 | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@1h | dar=0, geniş=0, ?=2 · medyan 0.69 | dar=0, geniş=0, ?=2 · medyan 0.69 | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-KUPA@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-OBO@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@15m | dar=3, geniş=0, ?=7 · medyan 0.71 | dar=3, geniş=0, ?=7 · medyan 0.71 | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@15m | dar=0, geniş=0, ?=4 · medyan 1.36 | dar=0, geniş=0, ?=4 · medyan 1.36 | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@1h | dar=0, geniş=0, ?=1 · medyan 1.10 | dar=0, geniş=0, ?=1 · medyan 1.10 | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@15m | dar=0, geniş=2 · medyan 3.52 | dar=0, geniş=2 · medyan 3.52 | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCGEN@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@15m | dar=2, geniş=0, ?=10 · medyan 0.75 | dar=2, geniş=0, ?=10 · medyan 0.75 | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@1h | dar=0, geniş=0, ?=2 · medyan 0.58 | dar=0, geniş=0, ?=2 · medyan 0.58 | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| GF1-YATAY@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@15m | dar=30, geniş=1, ?=32 · medyan 0.54 | dar=30, geniş=1, ?=32 · medyan 0.54 | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@1h | dar=3, geniş=0 · medyan 0.49 | dar=3, geniş=0 · medyan 0.49 | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@15m | dar=0, geniş=3, ?=9 · medyan 1.66 | dar=0, geniş=3, ?=9 · medyan 1.66 | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLLKIR@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@15m | dar=0, geniş=1 · medyan 2.45 | dar=0, geniş=1 · medyan 2.45 | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIBO@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@15m | dar=0, geniş=0, ?=5 · medyan 2.00 | dar=0, geniş=0, ?=5 · medyan 2.00 | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-FIYATMA@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@15m | dar=1, geniş=0, ?=3 · medyan 0.53 | dar=1, geniş=0, ?=3 · medyan 0.53 | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@15m | dar=0, geniş=7, ?=5 · medyan 2.00 | dar=0, geniş=7, ?=5 · medyan 2.00 | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-HIZLIMA@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@15m | dar=1, geniş=2, ?=3 · medyan 0.68 | dar=1, geniş=2, ?=3 · medyan 0.68 | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@15m | dar=0, geniş=5, ?=6 · medyan 2.00 | dar=0, geniş=5, ?=6 · medyan 2.00 | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@15m | dar=0, geniş=0, ?=1 · medyan 1.12 | dar=0, geniş=0, ?=1 · medyan 1.12 | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAGERI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-MAKESISIM@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@15m | dar=1, geniş=0 · medyan 0.37 | dar=1, geniş=0 · medyan 0.37 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@15m | dar=0, geniş=3, ?=5 · medyan 2.00 | dar=0, geniş=3, ?=5 · medyan 2.00 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@15m | dar=0, geniş=0, ?=1 · medyan 0.87 | dar=0, geniş=0, ?=1 · medyan 0.87 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@1h | dar=0, geniş=0, ?=1 · medyan 1.10 | dar=0, geniş=0, ?=1 · medyan 1.10 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-RSIDONUS@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-STOK@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@15m | dar=0, geniş=0, ?=7 · medyan 1.09 | dar=0, geniş=0, ?=7 · medyan 1.09 | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@15m | dar=0, geniş=0, ?=1 · medyan 1.62 | dar=0, geniş=0, ?=1 · medyan 1.62 | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-UYUMSUZ@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@15m | dar=0, geniş=10, ?=9 · medyan 2.00 | dar=0, geniş=10, ?=9 · medyan 2.00 | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-EMIRBLOK@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-BOLGE@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@15m | dar=0, geniş=0, ?=2 · medyan 1.65 | dar=0, geniş=0, ?=2 · medyan 1.65 | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-FVG@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@15m | dar=0, geniş=0, ?=1 · medyan 0.62 | dar=0, geniş=0, ?=1 · medyan 0.62 | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@1h | dar=1, geniş=0, ?=1 · medyan 0.80 | dar=1, geniş=0, ?=1 · medyan 0.80 | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@15m | dar=0, geniş=0, ?=6 · medyan 1.00 | dar=0, geniş=0, ?=6 · medyan 1.00 | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TCIZGI@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@15m | dar=0, geniş=0, ?=2 · medyan 0.81 | dar=0, geniş=0, ?=2 · medyan 0.81 | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-SEVIYE@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@1h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@4h | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-UCVURUS@1d | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TUKENIS@15m | - | - | veri: 25.11.2026 09:15 TSİ |
| PA2-TUKENIS@1h | - | - | veri: 25.11.2026 09:15 TSİ |

## ML 10 — Kol bazında sanal K/Z

| Kol | İşlem | Net $ | R toplamı | Kazanma | Durum | Veri |
|---|---|---|---|---|---|---|
| F1@15m | 15 | -$40,30 | -4,72 R | %26,7 | ZARARDA | veri: 24.11.2026 20:15 TSİ |
| S1@15m | 8 | -$36,18 | -3,29 R | %25,0 | ZARARDA | veri: 23.11.2026 17:15 TSİ |
| M1@1h | 4 | -$16,88 | -1,49 R | %50,0 | ZARARDA | veri: 23.11.2026 06:13 TSİ |
| T1@1h | 10 | -$15,27 | +0,44 R | %50,0 | ZARARDA | veri: 23.11.2026 03:57 TSİ |
| H2@1h | 1 | -$11,73 | -1,00 R | %0,0 | ZARARDA | veri: 21.11.2026 16:39 TSİ |
| S1@4h | 1 | -$11,15 | -1,10 R | %0,0 | ZARARDA | veri: 24.11.2026 17:52 TSİ |
| H2@4h | 1 | -$10,70 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:57 TSİ |
| B1@1d | 1 | -$10,54 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:58 TSİ |
| M1@15m | 12 | -$10,18 | -3,71 R | %41,7 | ZARARDA | veri: 25.11.2026 05:15 TSİ |
| TF1@15m | 6 | -$7,03 | -1,65 R | %50,0 | ZARARDA | veri: 25.11.2026 02:30 TSİ |
| H2@15m | 6 | +$1,98 | -0,11 R | %50,0 | kârda/başa baş | veri: 25.11.2026 06:12 TSİ |
| B1@15m | 1 | +$3,39 | +0,73 R | %100,0 | kârda/başa baş | veri: 19.11.2026 20:15 TSİ |
| M1@4h | 2 | +$9,87 | +0,96 R | %50,0 | kârda/başa baş | veri: 23.11.2026 16:55 TSİ |
| B1@1h | 2 | +$13,14 | +1,35 R | %50,0 | kârda/başa baş | veri: 21.11.2026 14:31 TSİ |
| S1@1h | 3 | +$13,71 | +1,44 R | %66,7 | kârda/başa baş | veri: 23.11.2026 13:41 TSİ |
| T1@15m | 10 | +$83,65 | +8,13 R | %60,0 | kârda/başa baş | veri: 25.11.2026 06:21 TSİ |
| B1-BOLGE@15m | 0 | - | - | - | - | veri: işlem yok |
| B1-BOLGE@1d | 0 | - | - | - | - | veri: işlem yok |
| B1-BOLGE@1h | 0 | - | - | - | - | veri: işlem yok |
| B1-BOLGE@4h | 0 | - | - | - | - | veri: işlem yok |
| B1-MUM@15m | 0 | - | - | - | - | veri: işlem yok |
| B1-MUM@1d | 0 | - | - | - | - | veri: işlem yok |
| B1-MUM@1h | 0 | - | - | - | - | veri: işlem yok |
| B1-MUM@4h | 0 | - | - | - | - | veri: işlem yok |
| B1@4h | 0 | - | - | - | - | veri: işlem yok |
| DL1@15m | 0 | - | - | - | - | veri: işlem yok |
| DL1@1d | 0 | - | - | - | - | veri: işlem yok |
| DL1@1h | 0 | - | - | - | - | veri: işlem yok |
| DL1@4h | 0 | - | - | - | - | veri: işlem yok |
| F1-IKINCI@15m | 0 | - | - | - | - | veri: işlem yok |
| F1-IKINCI@1d | 0 | - | - | - | - | veri: işlem yok |
| F1-IKINCI@1h | 0 | - | - | - | - | veri: işlem yok |
| F1-IKINCI@4h | 0 | - | - | - | - | veri: işlem yok |
| F1@1d | 0 | - | - | - | - | veri: işlem yok |
| F1@1h | 0 | - | - | - | - | veri: işlem yok |
| F1@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-BAYRAK@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-BAYRAK@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-BAYRAK@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-BAYRAK@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-FLAMA@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-FLAMA@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-FLAMA@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-FLAMA@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-IKILI@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-IKILI@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-IKILI@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-IKILI@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-KAMA@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-KAMA@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-KAMA@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-KAMA@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-KANAL@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-KANAL@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-KANAL@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-KANAL@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-KUPA@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-KUPA@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-KUPA@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-KUPA@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-OBO@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-OBO@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-OBO@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-OBO@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-RETEST@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-RETEST@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-RETEST@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-RETEST@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-SAHTE@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-SAHTE@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-SAHTE@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-SAHTE@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-TREND@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-TREND@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-TREND@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-TREND@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCGEN@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCGEN@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCGEN@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCGEN@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCLU@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCLU@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCLU@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-UCLU@4h | 0 | - | - | - | - | veri: işlem yok |
| GF1-YATAY@15m | 0 | - | - | - | - | veri: işlem yok |
| GF1-YATAY@1d | 0 | - | - | - | - | veri: işlem yok |
| GF1-YATAY@1h | 0 | - | - | - | - | veri: işlem yok |
| GF1-YATAY@4h | 0 | - | - | - | - | veri: işlem yok |
| H2-MINI@15m | 0 | - | - | - | - | veri: işlem yok |
| H2-MINI@1d | 0 | - | - | - | - | veri: işlem yok |
| H2-MINI@1h | 0 | - | - | - | - | veri: işlem yok |
| H2-MINI@4h | 0 | - | - | - | - | veri: işlem yok |
| H2-YARI@15m | 0 | - | - | - | - | veri: işlem yok |
| H2-YARI@1d | 0 | - | - | - | - | veri: işlem yok |
| H2-YARI@1h | 0 | - | - | - | - | veri: işlem yok |
| H2-YARI@4h | 0 | - | - | - | - | veri: işlem yok |
| H2@1d | 0 | - | - | - | - | veri: işlem yok |
| HB1@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLL@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLL@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLL@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLL@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLLKIR@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLLKIR@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLLKIR@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLLKIR@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIBO@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIBO@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIBO@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIBO@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIYATMA@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIYATMA@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIYATMA@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-FIYATMA@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-HACIM@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-HACIM@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-HACIM@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-HACIM@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-HIZLIMA@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-HIZLIMA@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-HIZLIMA@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-HIZLIMA@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-KUMO@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-KUMO@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-KUMO@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-KUMO@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-MACD@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-MACD@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-MACD@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-MACD@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAGERI@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAGERI@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAGERI@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAGERI@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAKESISIM@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAKESISIM@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAKESISIM@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-MAKESISIM@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI2@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI2@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI2@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI2@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSI@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSIDONUS@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSIDONUS@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSIDONUS@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-RSIDONUS@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-STOK@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-STOK@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-STOK@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-STOK@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-TK@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-TK@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-TK@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-TK@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-UYUMSUZ@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-UYUMSUZ@1d | 0 | - | - | - | - | veri: işlem yok |
| IN1-UYUMSUZ@1h | 0 | - | - | - | - | veri: işlem yok |
| IN1-UYUMSUZ@4h | 0 | - | - | - | - | veri: işlem yok |
| IN1-VWAP@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-VWAP@1h | 0 | - | - | - | - | veri: işlem yok |
| M1@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-CIMBIZ@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-CIMBIZ@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-CIMBIZ@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-CIMBIZ@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-DELICI@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-DELICI@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-DELICI@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-DELICI@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-DISBAR@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-DISBAR@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-DISBAR@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-DISBAR@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-HARAMI@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-HARAMI@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-HARAMI@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-HARAMI@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICCUBUK@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICCUBUK@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICCUBUK@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICCUBUK@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICSAHTE@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICSAHTE@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICSAHTE@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-ICSAHTE@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-MARUBOZU@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-MARUBOZU@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-MARUBOZU@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-MARUBOZU@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-PINBAR@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-PINBAR@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-PINBAR@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-PINBAR@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-TERSCEKIC@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-TERSCEKIC@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-TERSCEKIC@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-TERSCEKIC@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-UCASKER@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-UCASKER@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-UCASKER@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-UCASKER@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-YILDIZ@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-YILDIZ@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-YILDIZ@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-YILDIZ@4h | 0 | - | - | - | - | veri: işlem yok |
| MF1-YUTAN@15m | 0 | - | - | - | - | veri: işlem yok |
| MF1-YUTAN@1d | 0 | - | - | - | - | veri: işlem yok |
| MF1-YUTAN@1h | 0 | - | - | - | - | veri: işlem yok |
| MF1-YUTAN@4h | 0 | - | - | - | - | veri: işlem yok |
| PA2-BOLGE@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-BOLGE@1d | 0 | - | - | - | - | veri: işlem yok |
| PA2-BOLGE@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-BOLGE@4h | 0 | - | - | - | - | veri: işlem yok |
| PA2-EMIRBLOK@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-EMIRBLOK@1d | 0 | - | - | - | - | veri: işlem yok |
| PA2-EMIRBLOK@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-EMIRBLOK@4h | 0 | - | - | - | - | veri: işlem yok |
| PA2-FVG@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-FVG@1d | 0 | - | - | - | - | veri: işlem yok |
| PA2-FVG@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-FVG@4h | 0 | - | - | - | - | veri: işlem yok |
| PA2-ONCEKI@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-ONCEKI@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-ONCEKI@4h | 0 | - | - | - | - | veri: işlem yok |
| PA2-SEVIYE@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-SEVIYE@1d | 0 | - | - | - | - | veri: işlem yok |
| PA2-SEVIYE@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-SEVIYE@4h | 0 | - | - | - | - | veri: işlem yok |
| PA2-TCIZGI@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-TCIZGI@1d | 0 | - | - | - | - | veri: işlem yok |
| PA2-TCIZGI@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-TCIZGI@4h | 0 | - | - | - | - | veri: işlem yok |
| PA2-TUKENIS@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-TUKENIS@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-UCVURUS@15m | 0 | - | - | - | - | veri: işlem yok |
| PA2-UCVURUS@1d | 0 | - | - | - | - | veri: işlem yok |
| PA2-UCVURUS@1h | 0 | - | - | - | - | veri: işlem yok |
| PA2-UCVURUS@4h | 0 | - | - | - | - | veri: işlem yok |
| R1-ALT@15m | 0 | - | - | - | - | veri: işlem yok |
| R1-ALT@1d | 0 | - | - | - | - | veri: işlem yok |
| R1-ALT@1h | 0 | - | - | - | - | veri: işlem yok |
| R1-ALT@4h | 0 | - | - | - | - | veri: işlem yok |
| R1-ERKEN@15m | 0 | - | - | - | - | veri: işlem yok |
| R1-ERKEN@1d | 0 | - | - | - | - | veri: işlem yok |
| R1-ERKEN@1h | 0 | - | - | - | - | veri: işlem yok |
| R1-ERKEN@4h | 0 | - | - | - | - | veri: işlem yok |
| R1-HA@15m | 0 | - | - | - | - | veri: işlem yok |
| R1-HA@1d | 0 | - | - | - | - | veri: işlem yok |
| R1-HA@1h | 0 | - | - | - | - | veri: işlem yok |
| R1-HA@4h | 0 | - | - | - | - | veri: işlem yok |
| R1@15m | 0 | - | - | - | - | veri: işlem yok |
| R1@1d | 0 | - | - | - | - | veri: işlem yok |
| R1@1h | 0 | - | - | - | - | veri: işlem yok |
| R1@4h | 0 | - | - | - | - | veri: işlem yok |
| S1-HACIM@15m | 0 | - | - | - | - | veri: işlem yok |
| S1-HACIM@1d | 0 | - | - | - | - | veri: işlem yok |
| S1-HACIM@1h | 0 | - | - | - | - | veri: işlem yok |
| S1-HACIM@4h | 0 | - | - | - | - | veri: işlem yok |
| S1-OLCULU@15m | 0 | - | - | - | - | veri: işlem yok |
| S1-OLCULU@1d | 0 | - | - | - | - | veri: işlem yok |
| S1-OLCULU@1h | 0 | - | - | - | - | veri: işlem yok |
| S1-OLCULU@4h | 0 | - | - | - | - | veri: işlem yok |
| S1@1d | 0 | - | - | - | - | veri: işlem yok |
| T1-GERI3@15m | 0 | - | - | - | - | veri: işlem yok |
| T1-GERI3@1d | 0 | - | - | - | - | veri: işlem yok |
| T1-GERI3@1h | 0 | - | - | - | - | veri: işlem yok |
| T1-GERI3@4h | 0 | - | - | - | - | veri: işlem yok |
| T1-SEVIYE@15m | 0 | - | - | - | - | veri: işlem yok |
| T1-SEVIYE@1d | 0 | - | - | - | - | veri: işlem yok |
| T1-SEVIYE@1h | 0 | - | - | - | - | veri: işlem yok |
| T1-SEVIYE@4h | 0 | - | - | - | - | veri: işlem yok |
| T1@1d | 0 | - | - | - | - | veri: işlem yok |
| T1@4h | 0 | - | - | - | - | veri: işlem yok |
| TF1-FITIL@15m | 0 | - | - | - | - | veri: işlem yok |
| TF1-FITIL@1d | 0 | - | - | - | - | veri: işlem yok |
| TF1-FITIL@1h | 0 | - | - | - | - | veri: işlem yok |
| TF1-FITIL@4h | 0 | - | - | - | - | veri: işlem yok |
| TF1-HACIM@15m | 0 | - | - | - | - | veri: işlem yok |
| TF1-HACIM@1d | 0 | - | - | - | - | veri: işlem yok |
| TF1-HACIM@1h | 0 | - | - | - | - | veri: işlem yok |
| TF1-HACIM@4h | 0 | - | - | - | - | veri: işlem yok |
| TF1@1d | 0 | - | - | - | - | veri: işlem yok |
| TF1@1h | 0 | - | - | - | - | veri: işlem yok |
| TF1@4h | 0 | - | - | - | - | veri: işlem yok |

Zarardaki kollara karşı mevcut mekanizmalar (kod/yapılandırma; tetik durumu okunabilen durum dosyasından):

| Mekanizma | Var mı | Etki | Tetiklendi mi | Veri |
|---|---|---|---|---|
| Ders: kol kapatma (arms_off) | var | yalnız karne/rapor bilgisi; giriş ENGELLENMEZ (sahip kararı, 19 Kasım; gates.py `arm_would_close` sayacı) | tetiklendi: B1@15m, B1@1d, F1@15m, F1@1h, H2@15m, H2@1h, H2@4h, M1@15m, M1@1h, R1@15m, R1@1h, S1@15m, S1@1h, TF1@15m | okuma: 25.11.2026 09:22 TSİ |
| Ders: 10 R freni (lesson_brake) | var | ders ayarlarını referansa döndürür, otomatik uygulamayı durdurur; kolu kapatmaz | tetiklenmedi | okuma: 25.11.2026 09:22 TSİ |
| Kol başına açık pozisyon tavanı (arm_max_positions) ve küme/hesap tavanı | var | kayıptan bağımsız konum sınırı; zarardaki kolu özel olarak ayırmaz | kayıp temelli tetik değil | okuma: 25.11.2026 09:22 TSİ |
| Risk kademe denetimi (risk_ladder, hesap düzeyi küçültme) | var (hesap düzeyi; kol düzeyi değil) | tepe-denge düşüşünde hedef işlem riskini kademeli düşürür / durdurur; motor zorunlu yalnız canlı modda | kâğıt ayarında LADDER_BOTS boş; kâğıtta kademe izlenmez | okuma: 25.11.2026 09:22 TSİ |
| Kol bazında otomatik karantina / boyut küçültme | yok | zararda kol: F1@15m, S1@15m, M1@1h, T1@1h, H2@1h, S1@4h, H2@4h, B1@1d, M1@15m, TF1@15m; bu kolları kendiliğinden kısan kural yok | - | okuma: 25.11.2026 09:22 TSİ |

## ML 11 — Long/short dağılımı

| Yön | İşlem | Net $ | Kazanma | R | Veri |
|---|---|---|---|---|---|
| long | 13 | -$22,29 | %38,5 | -2,08 R | veri: 24.11.2026 20:15 TSİ |
| short | 70 | -$21,91 | %42,9 | -3,95 R | veri: 25.11.2026 06:21 TSİ |

| Rejim | Long (n / net $ / kazanma) | Short (n / net $ / kazanma) | Veri |
|---|---|---|---|
| trend_up | 7 / -$11,78 / %42,9 | 0 / - / - | veri: 24.11.2026 20:15 TSİ |
| trend_down | 1 / +$4,86 / %100,0 | 68 / -$15,03 / %42,6 | veri: 25.11.2026 06:21 TSİ |
| range | 2 / -$19,65 / %0,0 | 1 / -$7,33 / %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 3 / +$4,27 / %33,3 | 1 / +$0,45 / %100,0 | veri: 24.11.2026 13:30 TSİ |
| volatile | 0 / - / - | 0 / - / - | veri: işlem yok |

Güncel rejim (son karar zamanından geriye 24 saatte en sık rejim; 1144 karar): trend_down (veri: 25.11.2026 09:15 TSİ)
Long-yetkin kollar (kayıtta ≥1 long adayı olanlar) bu rejimde: aday 295 · alınan 1

| Kol | Long aday (güncel rejim) | Alınan (güncel rejim) | Long aday (tüm kayıt) | Alınan (tüm kayıt) | Veri |
|---|---|---|---|---|---|
| T1@15m | 0 | 0 | 28 | 0 | veri: 24.11.2026 20:30 TSİ |
| T1@1h | 0 | 0 | 9 | 1 | veri: 24.11.2026 03:00 TSİ |
| T1@4h | 0 | 0 | 4 | 0 | veri: 24.11.2026 03:00 TSİ |
| R1@15m | 0 | 0 | 34 | 0 | veri: 25.11.2026 08:45 TSİ |
| R1@1h | 0 | 0 | 15 | 0 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 0 | 0 | 11 | 0 | veri: 20.11.2026 11:00 TSİ |
| TF1@15m | 0 | 0 | 14 | 1 | veri: 25.11.2026 08:00 TSİ |
| TF1@1h | 0 | 0 | 5 | 0 | veri: 23.11.2026 23:00 TSİ |
| TF1@4h | 0 | 0 | 3 | 1 | veri: 24.11.2026 23:00 TSİ |
| TF1@1d | 0 | 0 | 1 | 0 | veri: 25.11.2026 03:00 TSİ |
| B1@15m | 0 | 0 | 2 | 0 | veri: 24.11.2026 21:30 TSİ |
| B1@1h | 0 | 0 | 5 | 0 | veri: 24.11.2026 21:00 TSİ |
| H2@15m | 0 | 0 | 11 | 0 | veri: 25.11.2026 02:15 TSİ |
| H2@1h | 0 | 0 | 4 | 0 | veri: 25.11.2026 08:00 TSİ |
| H2@4h | 0 | 0 | 1 | 0 | veri: 21.11.2026 23:00 TSİ |
| S1@15m | 0 | 0 | 45 | 3 | veri: 25.11.2026 08:00 TSİ |
| S1@1h | 0 | 0 | 5 | 0 | veri: 22.11.2026 13:00 TSİ |
| S1@4h | 0 | 0 | 3 | 0 | veri: 23.11.2026 07:00 TSİ |
| F1@15m | 0 | 0 | 62 | 7 | veri: 25.11.2026 09:15 TSİ |
| F1@1h | 0 | 0 | 18 | 0 | veri: 24.11.2026 15:00 TSİ |
| F1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 03:00 TSİ |
| M1@1h | 107 | 1 | 110 | 1 | veri: 23.11.2026 04:00 TSİ |
| M1@15m | 37 | 0 | 38 | 0 | veri: 24.11.2026 18:00 TSİ |
| MF1-DELICI@15m | 2 | 0 | 2 | 0 | veri: 25.11.2026 08:00 TSİ |
| MF1-ICSAHTE@15m | 3 | 0 | 5 | 0 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICSAHTE@1h | 2 | 0 | 2 | 0 | veri: 25.11.2026 09:00 TSİ |
| MF1-DISBAR@15m | 3 | 0 | 7 | 0 | veri: 25.11.2026 09:15 TSİ |
| MF1-DISBAR@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 09:00 TSİ |
| MF1-YUTAN@15m | 5 | 0 | 7 | 0 | veri: 25.11.2026 09:15 TSİ |
| MF1-YUTAN@1h | 0 | 0 | 1 | 0 | veri: 25.11.2026 09:00 TSİ |
| MF1-HARAMI@15m | 6 | 0 | 9 | 0 | veri: 25.11.2026 09:00 TSİ |
| MF1-CIMBIZ@15m | 2 | 0 | 5 | 0 | veri: 25.11.2026 09:00 TSİ |
| MF1-CIMBIZ@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| MF1-PINBAR@15m | 5 | 0 | 7 | 0 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@15m | 4 | 0 | 8 | 0 | veri: 25.11.2026 09:15 TSİ |
| MF1-ICCUBUK@1h | 0 | 0 | 2 | 0 | veri: 25.11.2026 09:00 TSİ |
| F1-IKINCI@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 09:15 TSİ |
| H2-YARI@1h | 0 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| R1-ALT@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 08:45 TSİ |
| R1-ERKEN@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 08:45 TSİ |
| S1-OLCULU@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| T1-GERI3@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 09:15 TSİ |
| T1-SEVIYE@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 09:15 TSİ |
| TF1-FITIL@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| GF1-BAYRAK@1h | 0 | 0 | 2 | 0 | veri: 25.11.2026 09:00 TSİ |
| GF1-IKILI@15m | 2 | 0 | 3 | 0 | veri: 25.11.2026 09:15 TSİ |
| GF1-KAMA@15m | 1 | 0 | 2 | 0 | veri: 25.11.2026 09:15 TSİ |
| GF1-KANAL@15m | 11 | 0 | 16 | 0 | veri: 25.11.2026 09:15 TSİ |
| GF1-RETEST@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 09:15 TSİ |
| GF1-SAHTE@15m | 2 | 0 | 4 | 0 | veri: 25.11.2026 09:15 TSİ |
| GF1-TREND@15m | 1 | 0 | 3 | 0 | veri: 25.11.2026 09:15 TSİ |
| GF1-UCLU@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 09:00 TSİ |
| GF1-YATAY@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 09:00 TSİ |
| GF1-YATAY@1h | 0 | 0 | 1 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-BOLL@15m | 37 | 0 | 51 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-BOLL@1h | 2 | 0 | 3 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-BOLLKIR@15m | 0 | 0 | 4 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-FIBO@15m | 2 | 0 | 2 | 0 | veri: 25.11.2026 08:00 TSİ |
| IN1-FIBO@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-FIYATMA@15m | 4 | 0 | 5 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-HACIM@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-HIZLIMA@15m | 8 | 0 | 12 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-KUMO@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 08:30 TSİ |
| IN1-MACD@15m | 8 | 0 | 12 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-MACD@1h | 2 | 0 | 3 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-MAGERI@15m | 1 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| IN1-RSI@15m | 1 | 0 | 1 | 0 | veri: 25.11.2026 08:30 TSİ |
| IN1-RSI2@15m | 4 | 0 | 12 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-RSI2@1h | 1 | 0 | 3 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-RSIDONUS@15m | 2 | 0 | 2 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-TK@15m | 1 | 0 | 4 | 0 | veri: 25.11.2026 08:15 TSİ |
| IN1-UYUMSUZ@15m | 2 | 0 | 2 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@15m | 15 | 0 | 23 | 0 | veri: 25.11.2026 09:15 TSİ |
| IN1-VWAP@1h | 2 | 0 | 5 | 0 | veri: 25.11.2026 09:00 TSİ |
| PA2-BOLGE@15m | 1 | 0 | 1 | 0 | veri: 25.11.2026 07:15 TSİ |
| PA2-ONCEKI@15m | 1 | 0 | 2 | 0 | veri: 25.11.2026 09:15 TSİ |
| PA2-ONCEKI@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| PA2-TCIZGI@15m | 2 | 0 | 2 | 0 | veri: 25.11.2026 09:00 TSİ |
| PA2-SEVIYE@15m | 2 | 0 | 2 | 0 | veri: 25.11.2026 09:00 TSİ |

## ML 12 — Kâğıt / geri test tutarlılığı

Toplam kâğıt R (n=83): -6,03 R (veri: 25.11.2026 06:21 TSİ). Yayımlanmış bant (n=83 için aradeğer): %2,5=-33,7 · %10=-22,9 · ortanca=+2,6 · %90=+39,6. Konum: %10-%90 arası (bant içinde). Kaynak: docs/kagit-degerlendirme-plani.md §4.4 (kümülatif net R, referans bootstrap bandı).

Sunucu tutarlılık raporu (kâğıt ↔ geri test, aynı dönem 2026-11-19T10:26:02Z → 2026-11-23T00:00:00Z; uyarı: True; veri: 23.11.2026 03:30 TSİ). Arm başına yayımlanmış R/işlem bandı yoktur; kurulum (setup) düzeyi yan yana:

| Kurulum | Kâğıt işlem | Kâğıt R/işlem | Geri test işlem | Geri test R/işlem | Eşleşme | Veri |
|---|---|---|---|---|---|---|
| B1 | 3 | +0,69 R | 1 | -1,25 R | %0,0 | veri: 23.11.2026 03:30 TSİ |
| F1 | 5 | -0,69 R | 8 | -0,31 R | %30,0 | veri: 23.11.2026 03:30 TSİ |
| H2 | 5 | -0,10 R | 6 | +0,05 R | %22,2 | veri: 23.11.2026 03:30 TSİ |
| M1 | 8 | -0,22 R | 14 | -0,28 R | %22,2 | veri: 23.11.2026 03:30 TSİ |
| R1 | 0 | - | 2 | -0,99 R | %0,0 | veri: 23.11.2026 03:30 TSİ |
| S1 | 8 | +0,18 R | 10 | +0,12 R | %5,9 | veri: 23.11.2026 03:30 TSİ |
| T1 | 8 | +0,75 R | 8 | +0,89 R | %23,1 | veri: 23.11.2026 03:30 TSİ |
| TF1 | 4 | +0,32 R | 6 | +0,48 R | %0,0 | veri: 23.11.2026 03:30 TSİ |
