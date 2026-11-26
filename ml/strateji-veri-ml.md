# [ML] Strateji verisi (beyin fırtınası için)

Üretim: 26.11.2026 02:21 TSİ · Kâğıt başlangıcı (ilk kayıt): 17.11.2026 18:00 TSİ · Veri kesiti: 26.11.2026 02:15 TSİ
Kapanan işlem: 106 · Açık işlem: 9 · Karar kaydı: 11066 · Yapılandırılmış kol: 283
Kapsam: yalnız kâğıt defteri (salt okunur). Kilitli dönem (01.05.2026-01.11.2026) kayıtları okunmadı/ayıklandı (ayıklanan kayıt: 0). Yeni geri test hesaplanmadı. Yorum/öneri yok.

## Ortak 1 — Kâğıt başlangıcından beri sonuç

| Ölçü | Değer | Veri |
|---|---|---|
| Net K/Z | -$77,29 | veri: 26.11.2026 02:15 TSİ |
| İşlem sayısı (kapanan) | 106 | veri: 26.11.2026 02:15 TSİ |
| Kazanma oranı (net > 0) | %39,6 | veri: 26.11.2026 02:15 TSİ |
| Ort. kazanç | +1,13 R / +$8,05 | veri: 26.11.2026 02:15 TSİ |
| Ort. kayıp | -0,94 R / -$6,49 | veri: 26.11.2026 02:15 TSİ |
| Toplam R | -12,56 R | veri: 26.11.2026 02:15 TSİ |

## Ortak 2 — K/Z yoğunlaşması

| Ölçü | Değer | Veri |
|---|---|---|
| En iyi 1 işlemin net içindeki payı | - (+$41,53) | veri: 26.11.2026 02:15 TSİ |
| En iyi 2 işlemin net içindeki payı | - (+$73,56) | veri: 26.11.2026 02:15 TSİ |
| En iyi 3 çıkarılınca net | -$175,94 | veri: 26.11.2026 02:15 TSİ |
| En kötü 3 çıkarılınca net | -$38,36 | veri: 26.11.2026 02:15 TSİ |
| En iyi 3 + en kötü 3 çıkarılınca net | -$137,01 | veri: 26.11.2026 02:15 TSİ |

Pay: net > 0 iken hesaplanır; yetersiz işlemde (en iyi/kötü 3 için < 4, ikisi birden < 7) '-'.

## Ortak 3 — Maliyetler

| Kalem | Tutar | Brüt kâra oranı | Veri |
|---|---|---|---|
| Brüt kâr (yalnız brüt > 0 olan işlemlerin toplamı) | $366,96 | - | veri: 26.11.2026 02:15 TSİ |
| Toplam brüt K/Z (tüm işlemler) | -$12,78 | - | veri: 26.11.2026 02:15 TSİ |
| Komisyon | $65,99 | %18,0 | veri: 26.11.2026 02:15 TSİ |
| Fonlama (ödenen) | -$1,48 | %0,4 | veri: 26.11.2026 02:15 TSİ |
| Komisyon + fonlama | $64,52 | %17,6 | veri: 26.11.2026 02:15 TSİ |
| Kayma (giriş+çıkış, planlanana göre; brüte ZATEN işlenmiştir) | +$104,56 | %28,5 | veri: 26.11.2026 02:15 TSİ |
| Komisyon + fonlama + kayma | $169,08 | %46,1 | veri: 26.11.2026 02:15 TSİ |

Net K/Z = brüt - komisyon - fonlama (kayma fiyatlara işlendiğinden ayrıca düşülmez).

## Ortak 6 — Girişteki piyasa rejimine göre sonuç

| Rejim | İşlem | Net K/Z | Kazanma | Veri |
|---|---|---|---|---|
| trend_up | 8 | -$21,80 | %37,5 | veri: 25.11.2026 16:54 TSİ |
| trend_down | 88 | -$43,06 | %39,8 | veri: 26.11.2026 02:15 TSİ |
| range | 3 | -$26,98 | %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 7 | +$14,54 | %57,1 | veri: 25.11.2026 23:15 TSİ |
| volatile | 0 | - | - | veri: işlem yok |

## Ortak 7 — 30 / 100 / 300 kapanan işleme ulaşma süresi

Süre: 8,3 gün (17.11.2026 18:00 TSİ → 26.11.2026 02:15 TSİ); kapanan 106; genel hız 12,70 işlem/gün; kol medyan hızı: işlemi olan 21 kol 0,240 işlem/gün, tüm 283 yapılandırılmış kol 0,000 işlem/gün (veri: 26.11.2026 02:15 TSİ).

| Hedef | Genel (güncel hızla) | Kol medyanı (işlemi olan kollar) | Kol medyanı (tüm kollar) | Hedefe ulaşan kol | Veri |
|---|---|---|---|---|---|
| 30 | ulaşıldı | 125 gün (17,9 hafta) | hesaplanamaz (hız 0) | 0 | veri: 26.11.2026 02:15 TSİ |
| 100 | ulaşıldı | 417 gün (59,6 hafta) | hesaplanamaz (hız 0) | 0 | veri: 26.11.2026 02:15 TSİ |
| 300 | 15 gün (2,2 hafta) | 1.252 gün (178,8 hafta) | hesaplanamaz (hız 0) | 0 | veri: 26.11.2026 02:15 TSİ |

## ML 8 — Yapılandırılmış kollar: işlem açan / açmayan

Yapılandırılmış kol: 283 · ≥1 işlem açan: 26 · hiç açmayan: 257 (veri: 26.11.2026 02:15 TSİ)

| Kol | Aday (karar kaydı) | En sık skip_reason | Grup (filtre/rejim/veri/eşik/risk-limit) | Veri |
|---|---|---|---|---|
| T1@4h | 36 | stop_width=29, risk_denied=6, ml_filter=1 | eşik=29, risk/limit=6, filtre=1 | veri: 25.11.2026 19:00 TSİ |
| T1@1d | 1 | stop_width=1 | eşik=1 | veri: 20.11.2026 03:00 TSİ |
| R1@15m | 36 | risk_denied=33, etiket_duygu=3 | risk/limit=33, filtre=3 | veri: 25.11.2026 21:15 TSİ |
| R1@1h | 16 | risk_denied=11, etiket_duygu=3, arm_conflict=2 | risk/limit=13, filtre=3 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 11 | rr_below_min=9, etiket_duygu=2 | eşik=9, filtre=2 | veri: 20.11.2026 11:00 TSİ |
| R1@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1@1h | 69 | risk_denied=60, arm_conflict=6, etiket_duygu=2, cluster_cap=1 | risk/limit=67, filtre=2 | veri: 25.11.2026 19:00 TSİ |
| B1@4h | 3 | risk_denied=3 | risk/limit=3 | veri: 25.11.2026 23:00 TSİ |
| S1@1d | 4 | stop_width=3, arm_conflict=1 | eşik=3, risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| F1@1h | 82 | risk_denied=55, stop_width=10, arm_conflict=8, rr_below_min=8, etiket_duygu=1 | risk/limit=63, eşik=18, filtre=1 | veri: 25.11.2026 08:00 TSİ |
| F1@4h | 5 | stop_width=3, risk_denied=1, rr_below_min=1 | eşik=4, risk/limit=1 | veri: 23.11.2026 23:00 TSİ |
| F1@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| M1@1d | 1 | risk_denied=1 | risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| MF1-YILDIZ@15m | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@15m | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@15m | 31 | stop_width=20, risk_denied=6, arm_conflict=5 | eşik=20, risk/limit=11 | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@1h | 23 | risk_denied=13, arm_conflict=5, stop_width=2, session_closed=2, cluster_cap=1 | risk/limit=19, eşik=2, filtre=2 | veri: 26.11.2026 01:00 TSİ |
| MF1-DELICI@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@15m | 58 | stop_width=45, risk_denied=12, arm_conflict=1 | eşik=45, risk/limit=13 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@1h | 17 | risk_denied=10, stop_width=5, arm_conflict=1, cluster_cap=1 | risk/limit=12, eşik=5 | veri: 26.11.2026 02:00 TSİ |
| MF1-ICSAHTE@4h | 4 | risk_denied=2, stop_width=1, cluster_cap=1 | risk/limit=3, eşik=1 | veri: 25.11.2026 19:00 TSİ |
| MF1-ICSAHTE@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@15m | 72 | stop_width=36, risk_denied=27, arm_conflict=8, cluster_cap=1 | eşik=36, risk/limit=36 | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@1h | 15 | stop_width=5, risk_denied=4, cluster_cap=3, arm_conflict=3 | risk/limit=10, eşik=5 | veri: 26.11.2026 00:00 TSİ |
| MF1-DISBAR@4h | 3 | cluster_cap=2, risk_denied=1 | risk/limit=3 | veri: 25.11.2026 23:00 TSİ |
| MF1-DISBAR@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@15m | 155 | stop_width=96, risk_denied=53, arm_conflict=6 | eşik=96, risk/limit=59 | veri: 26.11.2026 02:00 TSİ |
| MF1-YUTAN@1h | 16 | risk_denied=8, stop_width=6, arm_conflict=2 | risk/limit=10, eşik=6 | veri: 26.11.2026 02:00 TSİ |
| MF1-YUTAN@4h | 18 | risk_denied=16, arm_conflict=2 | risk/limit=18 | veri: 25.11.2026 23:00 TSİ |
| MF1-YUTAN@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@15m | 75 | stop_width=60, risk_denied=10, arm_conflict=3, cluster_cap=1, session_closed=1 | eşik=60, risk/limit=14, filtre=1 | veri: 26.11.2026 02:00 TSİ |
| MF1-HARAMI@1h | 11 | risk_denied=7, stop_width=4 | risk/limit=7, eşik=4 | veri: 25.11.2026 23:00 TSİ |
| MF1-HARAMI@4h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 15:00 TSİ |
| MF1-HARAMI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@15m | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 12:45 TSİ |
| MF1-TERSCEKIC@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@15m | 66 | stop_width=52, risk_denied=9, arm_conflict=5 | eşik=52, risk/limit=14 | veri: 26.11.2026 02:00 TSİ |
| MF1-CIMBIZ@1h | 17 | stop_width=7, risk_denied=5, arm_conflict=5 | risk/limit=10, eşik=7 | veri: 26.11.2026 02:00 TSİ |
| MF1-CIMBIZ@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@15m | 67 | stop_width=55, risk_denied=8, arm_conflict=3, etiket_rejim=1 | eşik=55, risk/limit=11, rejim=1 | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@1h | 15 | stop_width=6, risk_denied=6, arm_conflict=2, session_closed=1 | risk/limit=8, eşik=6, filtre=1 | veri: 26.11.2026 01:00 TSİ |
| MF1-PINBAR@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@15m | 180 | stop_width=93, risk_denied=65, arm_conflict=13, cluster_cap=4, etiket_rejim=3 | eşik=93, risk/limit=82, rejim=3, filtre=2 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@1h | 66 | risk_denied=46, stop_width=9, arm_conflict=9, etiket_rejim=2 | risk/limit=55, eşik=9, rejim=2 | veri: 26.11.2026 02:00 TSİ |
| MF1-ICCUBUK@4h | 17 | risk_denied=15, arm_conflict=2 | risk/limit=17 | veri: 25.11.2026 23:00 TSİ |
| MF1-ICCUBUK@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@15m | 45 | risk_denied=25, stop_width=9, arm_conflict=8, cluster_cap=3 | risk/limit=36, eşik=9 | veri: 25.11.2026 21:30 TSİ |
| MF1-MARUBOZU@1h | 3 | risk_denied=3 | risk/limit=3 | veri: 25.11.2026 21:00 TSİ |
| MF1-MARUBOZU@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@15m | 13 | stop_width=9, risk_denied=3, cluster_cap=1 | eşik=9, risk/limit=4 | veri: 25.11.2026 19:45 TSİ |
| B1-BOLGE@1h | 2 | risk_denied=2 | risk/limit=2 | veri: 25.11.2026 13:00 TSİ |
| B1-BOLGE@4h | 2 | cluster_cap=1, stop_width=1 | risk/limit=1, eşik=1 | veri: 25.11.2026 23:00 TSİ |
| B1-BOLGE@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@15m | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@15m | 17 | stop_width=10, arm_conflict=4, risk_denied=3 | eşik=10, risk/limit=7 | veri: 26.11.2026 01:15 TSİ |
| F1-IKINCI@1h | 1 | stop_width=1 | eşik=1 | veri: 25.11.2026 08:00 TSİ |
| F1-IKINCI@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@15m | 86 | stop_width=46, risk_denied=35, arm_conflict=5 | eşik=46, risk/limit=40 | veri: 26.11.2026 02:00 TSİ |
| H2-MINI@1h | 17 | risk_denied=9, stop_width=4, arm_conflict=4 | risk/limit=13, eşik=4 | veri: 26.11.2026 02:00 TSİ |
| H2-MINI@4h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 11:00 TSİ |
| H2-MINI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@15m | 41 | risk_denied=27, stop_width=11, arm_conflict=3 | risk/limit=30, eşik=11 | veri: 26.11.2026 01:45 TSİ |
| H2-YARI@1h | 12 | risk_denied=10, stop_width=1, arm_conflict=1 | risk/limit=11, eşik=1 | veri: 25.11.2026 15:00 TSİ |
| H2-YARI@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@15m | 3 | stop_width=2, risk_denied=1 | eşik=2, risk/limit=1 | veri: 25.11.2026 21:15 TSİ |
| R1-ALT@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@15m | 3 | stop_width=2, risk_denied=1 | eşik=2, risk/limit=1 | veri: 25.11.2026 21:15 TSİ |
| R1-ERKEN@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@15m | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@15m | 7 | risk_denied=5, arm_conflict=1, stop_width=1 | risk/limit=6, eşik=1 | veri: 25.11.2026 17:00 TSİ |
| S1-HACIM@1h | 5 | risk_denied=5 | risk/limit=5 | veri: 25.11.2026 17:00 TSİ |
| S1-HACIM@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@15m | 31 | rr_below_min=13, stop_width=11, risk_denied=7 | eşik=24, risk/limit=7 | veri: 26.11.2026 01:45 TSİ |
| S1-OLCULU@1h | 18 | rr_below_min=15, arm_conflict=2, risk_denied=1 | eşik=15, risk/limit=3 | veri: 25.11.2026 21:00 TSİ |
| S1-OLCULU@4h | 5 | rr_below_min=5 | eşik=5 | veri: 25.11.2026 15:00 TSİ |
| S1-OLCULU@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@15m | 127 | risk_denied=64, stop_width=58, cluster_cap=3, arm_conflict=2 | risk/limit=69, eşik=58 | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@1h | 21 | risk_denied=12, stop_width=6, session_closed=2, arm_conflict=1 | risk/limit=13, eşik=6, filtre=2 | veri: 26.11.2026 02:00 TSİ |
| T1-GERI3@4h | 2 | risk_denied=2 | risk/limit=2 | veri: 25.11.2026 15:00 TSİ |
| T1-GERI3@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@15m | 53 | risk_denied=30, stop_width=23 | risk/limit=30, eşik=23 | veri: 25.11.2026 20:30 TSİ |
| T1-SEVIYE@1h | 16 | risk_denied=12, stop_width=4 | risk/limit=12, eşik=4 | veri: 26.11.2026 00:00 TSİ |
| T1-SEVIYE@4h | 11 | risk_denied=7, cluster_cap=3, stop_width=1 | risk/limit=10, eşik=1 | veri: 25.11.2026 23:00 TSİ |
| T1-SEVIYE@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@15m | 22 | risk_denied=15, stop_width=7 | risk/limit=15, eşik=7 | veri: 25.11.2026 16:45 TSİ |
| TF1-FITIL@1h | 9 | risk_denied=7, arm_conflict=2 | risk/limit=9 | veri: 25.11.2026 19:00 TSİ |
| TF1-FITIL@4h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 15:00 TSİ |
| TF1-FITIL@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@15m | 14 | risk_denied=12, arm_conflict=1, stop_width=1 | risk/limit=13, eşik=1 | veri: 25.11.2026 16:45 TSİ |
| TF1-HACIM@1h | 4 | risk_denied=3, arm_conflict=1 | risk/limit=4 | veri: 25.11.2026 19:00 TSİ |
| TF1-HACIM@4h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 15:00 TSİ |
| TF1-HACIM@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@15m | 159 | risk_denied=103, stop_width=38, cluster_cap=11, arm_conflict=4, rr_below_min=2 | risk/limit=118, eşik=40, filtre=1 | veri: 26.11.2026 01:30 TSİ |
| GF1-BAYRAK@1h | 23 | risk_denied=15, arm_conflict=4, stop_width=2, cluster_cap=1, session_closed=1 | risk/limit=20, eşik=2, filtre=1 | veri: 26.11.2026 00:00 TSİ |
| GF1-BAYRAK@4h | 21 | risk_denied=18, arm_conflict=2, cluster_cap=1 | risk/limit=21 | veri: 25.11.2026 19:00 TSİ |
| GF1-BAYRAK@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@15m | 2 | stop_width=1, risk_denied=1 | eşik=1, risk/limit=1 | veri: 25.11.2026 14:30 TSİ |
| GF1-FLAMA@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 11:00 TSİ |
| GF1-FLAMA@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@1h | 19 | risk_denied=14, arm_conflict=5 | risk/limit=19 | veri: 25.11.2026 22:00 TSİ |
| GF1-IKILI@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@15m | 14 | stop_width=6, risk_denied=5, cluster_cap=2, arm_conflict=1 | risk/limit=8, eşik=6 | veri: 26.11.2026 02:00 TSİ |
| GF1-KAMA@1h | 4 | risk_denied=3, cluster_cap=1 | risk/limit=4 | veri: 25.11.2026 21:00 TSİ |
| GF1-KAMA@4h | 2 | risk_denied=1, cluster_cap=1 | risk/limit=2 | veri: 25.11.2026 19:00 TSİ |
| GF1-KAMA@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@15m | 196 | stop_width=144, risk_denied=41, arm_conflict=7, cluster_cap=3, session_closed=1 | eşik=144, risk/limit=51, filtre=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@1h | 17 | stop_width=8, risk_denied=4, cluster_cap=4, arm_conflict=1 | risk/limit=9, eşik=8 | veri: 26.11.2026 02:00 TSİ |
| GF1-KANAL@4h | 2 | stop_width=1, arm_conflict=1 | eşik=1, risk/limit=1 | veri: 25.11.2026 19:00 TSİ |
| GF1-KANAL@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@15m | 4 | stop_width=2, risk_denied=2 | eşik=2, risk/limit=2 | veri: 25.11.2026 22:15 TSİ |
| GF1-KUPA@1h | 2 | risk_denied=1, cluster_cap=1 | risk/limit=2 | veri: 25.11.2026 18:00 TSİ |
| GF1-KUPA@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@15m | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 17:45 TSİ |
| GF1-OBO@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@15m | 71 | stop_width=53, risk_denied=15, rr_below_min=3 | eşik=56, risk/limit=15 | veri: 26.11.2026 01:00 TSİ |
| GF1-RETEST@1h | 15 | risk_denied=6, stop_width=5, arm_conflict=3, session_closed=1 | risk/limit=9, eşik=5, filtre=1 | veri: 26.11.2026 00:00 TSİ |
| GF1-RETEST@4h | 6 | risk_denied=4, arm_conflict=2 | risk/limit=6 | veri: 25.11.2026 23:00 TSİ |
| GF1-RETEST@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@15m | 69 | stop_width=37, risk_denied=24, arm_conflict=8 | eşik=37, risk/limit=32 | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@1h | 13 | risk_denied=10, stop_width=2, cluster_cap=1 | risk/limit=11, eşik=2 | veri: 25.11.2026 21:00 TSİ |
| GF1-SAHTE@4h | 3 | risk_denied=3 | risk/limit=3 | veri: 25.11.2026 23:00 TSİ |
| GF1-SAHTE@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@15m | 40 | risk_denied=29, arm_conflict=6, stop_width=3, etiket_rejim=1, session_closed=1 | risk/limit=35, eşik=3, rejim=1, filtre=1 | veri: 26.11.2026 02:00 TSİ |
| GF1-TREND@1h | 9 | risk_denied=7, cluster_cap=1, arm_conflict=1 | risk/limit=9 | veri: 25.11.2026 22:00 TSİ |
| GF1-TREND@4h | 4 | risk_denied=4 | risk/limit=4 | veri: 25.11.2026 23:00 TSİ |
| GF1-TREND@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@15m | 7 | risk_denied=5, arm_conflict=1, stop_width=1 | risk/limit=6, eşik=1 | veri: 25.11.2026 16:45 TSİ |
| GF1-UCGEN@1h | 5 | etiket_rejim=2, arm_conflict=1, cluster_cap=1, risk_denied=1 | risk/limit=3, rejim=2 | veri: 25.11.2026 17:00 TSİ |
| GF1-UCGEN@4h | 2 | risk_denied=2 | risk/limit=2 | veri: 25.11.2026 15:00 TSİ |
| GF1-UCGEN@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@4h | 1 | etiket_rejim=1 | rejim=1 | veri: 25.11.2026 23:00 TSİ |
| GF1-UCLU@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@15m | 140 | stop_width=77, risk_denied=57, rr_below_min=3, arm_conflict=2, cluster_cap=1 | eşik=80, risk/limit=60 | veri: 26.11.2026 02:00 TSİ |
| GF1-YATAY@1h | 32 | risk_denied=19, stop_width=10, arm_conflict=2, rr_below_min=1 | risk/limit=21, eşik=11 | veri: 25.11.2026 23:00 TSİ |
| GF1-YATAY@4h | 6 | risk_denied=5, arm_conflict=1 | risk/limit=6 | veri: 25.11.2026 23:00 TSİ |
| GF1-YATAY@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@15m | 791 | stop_width=680, risk_denied=75, arm_conflict=17, rr_below_min=16, cluster_cap=3 | eşik=696, risk/limit=95 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@4h | 55 | risk_denied=25, stop_width=22, arm_conflict=5, rr_below_min=3 | risk/limit=30, eşik=25 | veri: 25.11.2026 23:00 TSİ |
| IN1-BOLL@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@15m | 165 | risk_denied=102, stop_width=44, arm_conflict=17, cluster_cap=2 | risk/limit=121, eşik=44 | veri: 26.11.2026 00:45 TSİ |
| IN1-BOLLKIR@1h | 63 | risk_denied=49, arm_conflict=8, stop_width=5, session_closed=1 | risk/limit=57, eşik=5, filtre=1 | veri: 26.11.2026 00:00 TSİ |
| IN1-BOLLKIR@4h | 13 | risk_denied=10, arm_conflict=3 | risk/limit=13 | veri: 25.11.2026 23:00 TSİ |
| IN1-BOLLKIR@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@15m | 15 | risk_denied=11, stop_width=2, arm_conflict=2 | risk/limit=13, eşik=2 | veri: 26.11.2026 00:00 TSİ |
| IN1-FIBO@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 09:00 TSİ |
| IN1-FIBO@4h | 1 | arm_conflict=1 | risk/limit=1 | veri: 25.11.2026 15:00 TSİ |
| IN1-FIBO@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@15m | 131 | risk_denied=69, stop_width=48, arm_conflict=13, cluster_cap=1 | risk/limit=83, eşik=48 | veri: 26.11.2026 02:00 TSİ |
| IN1-FIYATMA@1h | 39 | risk_denied=21, arm_conflict=15, session_closed=2, stop_width=1 | risk/limit=36, filtre=2, eşik=1 | veri: 26.11.2026 02:00 TSİ |
| IN1-FIYATMA@4h | 12 | risk_denied=9, arm_conflict=2, cluster_cap=1 | risk/limit=12 | veri: 25.11.2026 23:00 TSİ |
| IN1-FIYATMA@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@15m | 106 | risk_denied=60, stop_width=41, arm_conflict=5 | risk/limit=65, eşik=41 | veri: 26.11.2026 00:00 TSİ |
| IN1-HACIM@1h | 38 | risk_denied=31, arm_conflict=6, stop_width=1 | risk/limit=37, eşik=1 | veri: 25.11.2026 23:00 TSİ |
| IN1-HACIM@4h | 14 | risk_denied=9, arm_conflict=5 | risk/limit=14 | veri: 25.11.2026 23:00 TSİ |
| IN1-HACIM@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@15m | 223 | risk_denied=130, stop_width=62, arm_conflict=25, cluster_cap=3, session_closed=3 | risk/limit=158, eşik=62, filtre=3 | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@1h | 47 | risk_denied=29, arm_conflict=16, stop_width=1, etiket_rejim=1 | risk/limit=45, eşik=1, rejim=1 | veri: 26.11.2026 01:00 TSİ |
| IN1-HIZLIMA@4h | 14 | risk_denied=9, arm_conflict=4, cluster_cap=1 | risk/limit=14 | veri: 25.11.2026 23:00 TSİ |
| IN1-HIZLIMA@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@15m | 93 | stop_width=48, risk_denied=35, arm_conflict=7, session_closed=2, etiket_rejim=1 | eşik=48, risk/limit=42, filtre=2, rejim=1 | veri: 26.11.2026 02:00 TSİ |
| IN1-KUMO@1h | 15 | risk_denied=6, stop_width=5, arm_conflict=4 | risk/limit=10, eşik=5 | veri: 26.11.2026 00:00 TSİ |
| IN1-KUMO@4h | 5 | risk_denied=3, arm_conflict=2 | risk/limit=5 | veri: 25.11.2026 23:00 TSİ |
| IN1-KUMO@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@15m | 215 | risk_denied=126, stop_width=57, arm_conflict=14, session_closed=10, cluster_cap=6 | risk/limit=146, eşik=57, filtre=10, rejim=2 | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@1h | 72 | risk_denied=58, arm_conflict=8, stop_width=2, cluster_cap=2, etiket_rejim=1 | risk/limit=68, eşik=2, rejim=1, filtre=1 | veri: 26.11.2026 01:00 TSİ |
| IN1-MACD@4h | 9 | risk_denied=6, arm_conflict=2, etiket_rejim=1 | risk/limit=8, rejim=1 | veri: 25.11.2026 23:00 TSİ |
| IN1-MACD@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@15m | 20 | risk_denied=11, stop_width=8, arm_conflict=1 | risk/limit=12, eşik=8 | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@1h | 3 | risk_denied=3 | risk/limit=3 | veri: 25.11.2026 19:00 TSİ |
| IN1-MAGERI@4h | 1 | arm_conflict=1 | risk/limit=1 | veri: 25.11.2026 15:00 TSİ |
| IN1-MAGERI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@15m | 8 | risk_denied=3, stop_width=2, session_closed=2, arm_conflict=1 | risk/limit=4, eşik=2, filtre=2 | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@1h | 6 | risk_denied=4, session_closed=2 | risk/limit=4, filtre=2 | veri: 26.11.2026 02:00 TSİ |
| IN1-MAKESISIM@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@15m | 38 | stop_width=33, risk_denied=4, arm_conflict=1 | eşik=33, risk/limit=5 | veri: 26.11.2026 00:45 TSİ |
| IN1-RSI@1h | 9 | stop_width=6, arm_conflict=2, risk_denied=1 | eşik=6, risk/limit=3 | veri: 26.11.2026 01:00 TSİ |
| IN1-RSI@4h | 1 | etiket_rejim=1 | rejim=1 | veri: 25.11.2026 15:00 TSİ |
| IN1-RSI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@4h | 14 | risk_denied=14 | risk/limit=14 | veri: 25.11.2026 23:00 TSİ |
| IN1-RSI2@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@15m | 122 | risk_denied=58, stop_width=53, arm_conflict=9, cluster_cap=1, session_closed=1 | risk/limit=68, eşik=53, filtre=1 | veri: 26.11.2026 01:15 TSİ |
| IN1-RSIDONUS@1h | 28 | risk_denied=16, stop_width=5, arm_conflict=5, cluster_cap=1, etiket_rejim=1 | risk/limit=22, eşik=5, rejim=1 | veri: 26.11.2026 02:00 TSİ |
| IN1-RSIDONUS@4h | 5 | risk_denied=4, arm_conflict=1 | risk/limit=5 | veri: 25.11.2026 23:00 TSİ |
| IN1-RSIDONUS@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@15m | 5 | stop_width=4, risk_denied=1 | eşik=4, risk/limit=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@1h | 2 | stop_width=1, session_closed=1 | eşik=1, filtre=1 | veri: 26.11.2026 02:00 TSİ |
| IN1-STOK@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@15m | 49 | stop_width=35, risk_denied=12, arm_conflict=1, etiket_rejim=1 | eşik=35, risk/limit=13, rejim=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@1h | 4 | risk_denied=2, arm_conflict=2 | risk/limit=4 | veri: 25.11.2026 19:00 TSİ |
| IN1-TK@4h | 13 | risk_denied=12, cluster_cap=1 | risk/limit=13 | veri: 25.11.2026 19:00 TSİ |
| IN1-TK@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@15m | 20 | stop_width=8, risk_denied=7, cluster_cap=3, arm_conflict=2 | risk/limit=12, eşik=8 | veri: 26.11.2026 01:00 TSİ |
| IN1-UYUMSUZ@1h | 9 | risk_denied=9 | risk/limit=9 | veri: 25.11.2026 22:00 TSİ |
| IN1-UYUMSUZ@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-VWAP@15m | 198 | risk_denied=118, stop_width=62, arm_conflict=10, cluster_cap=7, etiket_rejim=1 | risk/limit=135, eşik=62, rejim=1 | veri: 26.11.2026 02:00 TSİ |
| IN1-VWAP@1h | 94 | risk_denied=76, arm_conflict=13, cluster_cap=2, etiket_rejim=2, stop_width=1 | risk/limit=91, rejim=2, eşik=1 | veri: 26.11.2026 00:00 TSİ |
| PA2-EMIRBLOK@15m | 6 | risk_denied=6 | risk/limit=6 | veri: 25.11.2026 20:30 TSİ |
| PA2-EMIRBLOK@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@1h | 3 | risk_denied=2, arm_conflict=1 | risk/limit=3 | veri: 26.11.2026 01:00 TSİ |
| PA2-BOLGE@4h | 2 | risk_denied=2 | risk/limit=2 | veri: 25.11.2026 19:00 TSİ |
| PA2-BOLGE@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@15m | 41 | risk_denied=26, stop_width=11, arm_conflict=2, cluster_cap=1, session_closed=1 | risk/limit=29, eşik=11, filtre=1 | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@1h | 6 | risk_denied=5, arm_conflict=1 | risk/limit=6 | veri: 26.11.2026 00:00 TSİ |
| PA2-FVG@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-ONCEKI@15m | 13 | risk_denied=7, stop_width=5, arm_conflict=1 | risk/limit=8, eşik=5 | veri: 25.11.2026 22:45 TSİ |
| PA2-ONCEKI@1h | 11 | risk_denied=5, stop_width=4, arm_conflict=1, cluster_cap=1 | risk/limit=7, eşik=4 | veri: 26.11.2026 01:00 TSİ |
| PA2-ONCEKI@4h | 3 | risk_denied=2, etiket_rejim=1 | risk/limit=2, rejim=1 | veri: 25.11.2026 23:00 TSİ |
| PA2-TCIZGI@15m | 19 | stop_width=15, risk_denied=4 | eşik=15, risk/limit=4 | veri: 25.11.2026 19:45 TSİ |
| PA2-TCIZGI@1h | 5 | risk_denied=4, stop_width=1 | risk/limit=4, eşik=1 | veri: 26.11.2026 02:00 TSİ |
| PA2-TCIZGI@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@15m | 10 | stop_width=9, arm_conflict=1 | eşik=9, risk/limit=1 | veri: 26.11.2026 02:00 TSİ |
| PA2-SEVIYE@1h | 1 | risk_denied=1 | risk/limit=1 | veri: 25.11.2026 10:00 TSİ |
| PA2-SEVIYE@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@15m | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@4h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@1d | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-TUKENIS@15m | 1 | stop_width=1 | eşik=1 | veri: 26.11.2026 00:45 TSİ |
| PA2-TUKENIS@1h | 0 (aday üretmedi) | - | - | veri: 26.11.2026 02:15 TSİ |

Açan kollar: T1@15m, T1@1h, TF1@15m, TF1@4h, TF1@1d, B1@15m, B1@1h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, F1@15m, M1@1h, M1@4h, M1@15m, GF1-IKILI@15m, GF1-UCLU@15m, GF1-UCLU@1h, IN1-BOLL@1h, IN1-RSI2@15m, IN1-RSI2@1h, PA2-BOLGE@15m

### Kol bazında neden işlem açmıyor (tüm kayıt / son 12 saat)

Pencere: «tüm kayıt» = kilitli dönem dışındaki tüm karar satırları; «son 12 saat» = veri kesitinden (26.11.2026 02:15 TSİ) geriye 12 saat. Kâğıt risk limitleri kayıt süresince gevşetilmiş olabilir; eski `risk_denied` sayıları o günkü limitlere aittir, güncel durumu «son 12 saat» sütunları gösterir. Risk reddi `risk_reason` metninden limit adına çevrilir (max_open_risk, max_same_dir_risk, daily_max_loss ...).

| Kol | Aday (tüm) | Girdi (tüm) | Skip (tüm) | Aday (12s) | Girdi (12s) | Skip (12s) | Veri |
|---|---|---|---|---|---|---|---|
| T1@15m | 654 | 10 | stop_width=335; risk_denied=259 (margin_total=116, max_same_dir_risk=60, daily_max_loss=44, daily_limit=19, korelasyon_grubu=18, diğer=2); ml_filter=39; arm_conflict=6 (M1@1h=3, T1@1h=1, M1@4h=1); order_failed=2; etiket_duygu=2; cluster_cap=1 (hisse=1) | 16 | 0 | stop_width=9; risk_denied=6 (max_same_dir_risk=6); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| T1@1h | 191 | 10 | stop_width=89; risk_denied=64 (margin_total=31, max_same_dir_risk=20, daily_max_loss=10, korelasyon_grubu=3); ml_filter=19; veto_blocked=3; session_closed=3; veto_missing=1; cluster_cap=1 (hisse=1); arm_conflict=1 (IN1-MACD@4h=1) | 8 | 0 | stop_width=3; session_closed=3; cluster_cap=1 (hisse=1); arm_conflict=1 (IN1-MACD@4h=1) | veri: 26.11.2026 02:15 TSİ |
| T1@4h | 36 | 0 | stop_width=29; risk_denied=6 (max_same_dir_risk=4, daily_max_loss=1, margin_total=1); ml_filter=1 | 2 | 0 | stop_width=2 | veri: 26.11.2026 02:15 TSİ |
| T1@1d | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1@15m | 36 | 0 | risk_denied=33 (margin_total=27, diğer=4, daily_max_loss=1, max_same_dir_risk=1); etiket_duygu=3 | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| R1@1h | 16 | 0 | risk_denied=11 (margin_total=9, daily_max_loss=2); etiket_duygu=3; arm_conflict=2 (R1@4h=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1@4h | 11 | 0 | rr_below_min=9; etiket_duygu=2 | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| TF1@15m | 195 | 8 | risk_denied=158 (max_same_dir_risk=61, margin_total=54, daily_max_loss=20, korelasyon_grubu=15, daily_limit=8); arm_conflict=16 (TF1@1h=5, T1@1h=4, M1@1h=3, H2@1h=2, TF1@4h=1, S1@1h=1); cluster_cap=7 (hisse_teknoloji=6, hisse=1); etiket_duygu=6 | 14 | 0 | risk_denied=13 (max_same_dir_risk=12, korelasyon_grubu=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| TF1@1h | 69 | 0 | risk_denied=60 (max_same_dir_risk=23, korelasyon_grubu=14, margin_total=12, daily_max_loss=8, daily_limit=3); arm_conflict=6 (TF1@4h=2, M1@4h=2, S1@4h=1, MF1-ICSAHTE@4h=1); etiket_duygu=2; cluster_cap=1 (hisse=1) | 10 | 0 | risk_denied=8 (max_same_dir_risk=7, korelasyon_grubu=1); cluster_cap=1 (hisse=1); arm_conflict=1 (MF1-ICSAHTE@4h=1) | veri: 26.11.2026 02:15 TSİ |
| TF1@4h | 17 | 1 | risk_denied=12 (daily_max_loss=6, max_same_dir_risk=4, margin_total=1, daily_limit=1); etiket_duygu=2; cluster_cap=2 (hisse_teknoloji=2) | 2 | 0 | risk_denied=2 (max_same_dir_risk=2) | veri: 26.11.2026 02:15 TSİ |
| TF1@1d | 10 | 2 | risk_denied=8 (margin_total=3, daily_max_loss=2, korelasyon_grubu=2, max_same_dir_risk=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1@15m | 56 | 1 | risk_denied=33 (margin_total=11, max_same_dir_risk=11, daily_max_loss=7, korelasyon_grubu=3, daily_limit=1); stop_width=17; arm_conflict=4 (TF1@1h=2, S1@1h=2); entry_gate_closed=1 | 7 | 0 | risk_denied=5 (max_same_dir_risk=3, korelasyon_grubu=2); stop_width=2 | veri: 26.11.2026 02:15 TSİ |
| B1@1h | 18 | 2 | risk_denied=10 (margin_total=4, daily_max_loss=4, korelasyon_grubu=1, max_same_dir_risk=1); stop_width=4; arm_conflict=2 (TF1@4h=1, M1@4h=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1@4h | 3 | 0 | risk_denied=3 (margin_total=2, max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (margin_total=1) | veri: 26.11.2026 02:15 TSİ |
| B1@1d | 2 | 1 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| H2@15m | 237 | 9 | risk_denied=161 (max_same_dir_risk=51, margin_total=47, daily_max_loss=34, korelasyon_grubu=17, daily_limit=11, diğer=1); stop_width=43; arm_conflict=16 (TF1@15m=11, M1@1h=1, M1@4h=1, T1@15m=1, TF1@1h=1); cluster_cap=4 (hisse=3, hisse_teknoloji=1); session_closed=2; entry_gate_closed=1; order_failed=1 | 22 | 0 | risk_denied=13 (max_same_dir_risk=9, korelasyon_grubu=3, diğer=1); stop_width=4; cluster_cap=3 (hisse=3); session_closed=2 | veri: 26.11.2026 02:15 TSİ |
| H2@1h | 82 | 1 | risk_denied=59 (margin_total=25, max_same_dir_risk=14, korelasyon_grubu=13, daily_max_loss=7); stop_width=15; arm_conflict=6 (H2@4h=2, TF1@1h=1, TF1@4h=1, M1@4h=1, S1@4h=1); etiket_duygu=1 | 11 | 0 | risk_denied=5 (max_same_dir_risk=4, korelasyon_grubu=1); stop_width=5; arm_conflict=1 (S1@4h=1) | veri: 26.11.2026 02:15 TSİ |
| H2@4h | 18 | 1 | risk_denied=15 (margin_total=10, daily_max_loss=5); stop_width=2 | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| H2@1d | 3 | 1 | arm_conflict=1 (TF1@1d=1); risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| S1@15m | 510 | 8 | risk_denied=245 (margin_total=107, max_same_dir_risk=63, daily_max_loss=34, korelasyon_grubu=19, daily_limit=18, diğer=4); stop_width=200; arm_conflict=46 (TF1@15m=15, T1@15m=14, M1@1h=5, H2@15m=4, T1@1h=2, B1@15m=1, TF1@1h=1, S1@1h=1, F1@1h=1, MF1-ICCUBUK@4h=1); etiket_duygu=7; cluster_cap=4 (hisse_teknoloji=4) | 31 | 0 | risk_denied=20 (max_same_dir_risk=13, korelasyon_grubu=5, margin_total=2); stop_width=11 | veri: 26.11.2026 02:15 TSİ |
| S1@1h | 126 | 4 | risk_denied=62 (margin_total=27, max_same_dir_risk=20, korelasyon_grubu=10, daily_max_loss=4, diğer=1); stop_width=46; arm_conflict=12 (T1@1h=3, H2@1h=2, TF1@1h=2, H2@4h=2, T1@4h=1, TF1@4h=1, T1-GERI3@1h=1); order_failed=1; cluster_cap=1 (hisse=1) | 18 | 0 | risk_denied=9 (max_same_dir_risk=6, korelasyon_grubu=2, diğer=1); stop_width=8; cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| S1@4h | 29 | 2 | stop_width=16; risk_denied=8 (korelasyon_grubu=3, margin_total=2, daily_max_loss=1, daily_limit=1, max_same_dir_risk=1); arm_conflict=3 (TF1@4h=2, H2@1d=1) | 7 | 1 | stop_width=4; risk_denied=2 (korelasyon_grubu=2) | veri: 26.11.2026 02:15 TSİ |
| S1@1d | 4 | 0 | stop_width=3; arm_conflict=1 (TF1@1d=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| F1@15m | 359 | 18 | risk_denied=192 (margin_total=128, daily_max_loss=20, max_same_dir_risk=18, diğer=16, daily_limit=6, korelasyon_grubu=3, toplam_buyukluk=1); stop_width=77; rr_below_min=39; arm_conflict=17 (M1@1h=8, R1@15m=3, M1@4h=3, T1@1h=2, IN1-BOLL@1h=1); etiket_duygu=7; session_closed=4; entry_gate_closed=3; cluster_cap=2 (hisse_teknoloji=1, hisse=1) | 35 | 3 | risk_denied=23 (margin_total=10, max_same_dir_risk=9, korelasyon_grubu=3, toplam_buyukluk=1); session_closed=4; arm_conflict=2 (M1@1h=1, IN1-BOLL@1h=1); cluster_cap=1 (hisse=1); rr_below_min=1; stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| F1@1h | 82 | 0 | risk_denied=55 (margin_total=40, diğer=6, daily_max_loss=5, daily_limit=2, max_same_dir_risk=2); stop_width=10; arm_conflict=8 (R1@1h=4, M1@4h=4); rr_below_min=8; etiket_duygu=1 | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| F1@4h | 5 | 0 | stop_width=3; risk_denied=1 (daily_max_loss=1); rr_below_min=1 | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| F1@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| M1@1h | 465 | 6 | risk_denied=273 (margin_total=225, daily_max_loss=21, diğer=19, max_same_dir_risk=8); etiket_rejim=116; arm_conflict=61 (S1@1h=17, F1@1h=12, T1@1h=11, M1@4h=8, H2@4h=3, TF1@4h=1, B1@1h=1, TF1@1h=1, B1@1d=1, H2@1h=1, GF1-BAYRAK@4h=1, MF1-ICCUBUK@4h=1, B1-BOLGE@4h=1, T1-GERI3@1h=1, IN1-FIYATMA@4h=1); cluster_cap=8 (hisse=8); session_closed=1 | 19 | 1 | cluster_cap=8 (hisse=8); risk_denied=5 (diğer=2, max_same_dir_risk=2, margin_total=1); arm_conflict=4 (B1-BOLGE@4h=1, T1-GERI3@1h=1, IN1-FIYATMA@4h=1, T1@1h=1); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| M1@4h | 124 | 2 | risk_denied=114 (margin_total=73, daily_limit=17, max_same_dir_risk=15, diğer=7, daily_max_loss=2); arm_conflict=8 (H2@4h=2, S1@4h=2, R1@4h=1, H2@1d=1, T1@4h=1, M1@1d=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| M1@15m | 1453 | 13 | risk_denied=1242 (margin_total=470, max_same_dir_risk=244, daily_max_loss=214, daily_limit=193, diğer=102, korelasyon_grubu=18, toplam_buyukluk=1); arm_conflict=96 (S1@15m=30, T1@15m=18, M1@1h=14, T1@1h=9, H2@15m=6, TF1@15m=5, H2@1h=4, F1@15m=4, M1@4h=4, TF1@4h=1, B1@15m=1); etiket_rejim=89; order_failed=12; session_closed=1 | 4 | 0 | risk_denied=3 (max_same_dir_risk=3); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| M1@1d | 1 | 0 | risk_denied=1 (diğer=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@15m | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@15m | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@15m | 31 | 0 | stop_width=20; risk_denied=6 (max_same_dir_risk=6); arm_conflict=5 (GF1-TREND@1h=1, MF1-ICSAHTE@1h=1, GF1-KUPA@1h=1, GF1-KANAL@15m=1, F1@15m=1) | 25 | 0 | stop_width=14; risk_denied=6 (max_same_dir_risk=6); arm_conflict=5 (GF1-TREND@1h=1, MF1-ICSAHTE@1h=1, GF1-KUPA@1h=1, GF1-KANAL@15m=1, F1@15m=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@1h | 23 | 0 | risk_denied=13 (diğer=8, max_same_dir_risk=4, korelasyon_grubu=1); arm_conflict=5 (GF1-KANAL@1h=2, GF1-SAHTE@1h=1, PA2-ONCEKI@1h=1, T1@1h=1); stop_width=2; session_closed=2; cluster_cap=1 (hisse=1) | 18 | 0 | risk_denied=9 (diğer=7, korelasyon_grubu=1, max_same_dir_risk=1); arm_conflict=5 (GF1-KANAL@1h=2, GF1-SAHTE@1h=1, PA2-ONCEKI@1h=1, T1@1h=1); session_closed=2; stop_width=1; cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@15m | 58 | 0 | stop_width=45; risk_denied=12 (max_same_dir_risk=8, diğer=4); arm_conflict=1 (GF1-KAMA@15m=1) | 34 | 0 | stop_width=25; risk_denied=8 (max_same_dir_risk=7, diğer=1); arm_conflict=1 (GF1-KAMA@15m=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@1h | 17 | 0 | risk_denied=10 (max_same_dir_risk=7, korelasyon_grubu=2, diğer=1); stop_width=5; arm_conflict=1 (GF1-KANAL@1h=1); cluster_cap=1 (hisse=1) | 13 | 0 | risk_denied=9 (max_same_dir_risk=7, korelasyon_grubu=2); stop_width=2; arm_conflict=1 (GF1-KANAL@1h=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@4h | 4 | 0 | risk_denied=2 (max_same_dir_risk=1, diğer=1); stop_width=1; cluster_cap=1 (hisse=1) | 4 | 0 | risk_denied=2 (max_same_dir_risk=1, diğer=1); stop_width=1; cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@15m | 72 | 0 | stop_width=36; risk_denied=27 (diğer=18, max_same_dir_risk=9); arm_conflict=8 (GF1-KANAL@1h=2, IN1-BOLL@1h=2, IN1-HACIM@1h=1, IN1-RSIDONUS@1h=1, M1@1h=1, GF1-KANAL@15m=1); cluster_cap=1 (hisse=1) | 51 | 0 | risk_denied=23 (diğer=14, max_same_dir_risk=9); stop_width=20; arm_conflict=7 (GF1-KANAL@1h=2, IN1-BOLL@1h=2, IN1-RSIDONUS@1h=1, M1@1h=1, GF1-KANAL@15m=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@1h | 15 | 0 | stop_width=5; risk_denied=4 (diğer=2, korelasyon_grubu=1, max_same_dir_risk=1); cluster_cap=3 (hisse=3); arm_conflict=3 (GF1-KAMA@1h=1, MF1-ICSAHTE@1h=1, GF1-KANAL@1h=1) | 11 | 0 | cluster_cap=3 (hisse=3); risk_denied=3 (diğer=2, max_same_dir_risk=1); arm_conflict=3 (GF1-KAMA@1h=1, MF1-ICSAHTE@1h=1, GF1-KANAL@1h=1); stop_width=2 | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@4h | 3 | 0 | cluster_cap=2 (hisse=2); risk_denied=1 (diğer=1) | 3 | 0 | cluster_cap=2 (hisse=2); risk_denied=1 (diğer=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@15m | 155 | 0 | stop_width=96; risk_denied=53 (diğer=34, max_same_dir_risk=18, korelasyon_grubu=1); arm_conflict=6 (GF1-KANAL@15m=1, GF1-KANAL@1h=1, GF1-SAHTE@1h=1, M1@1h=1, IN1-BOLL@1h=1, GF1-BAYRAK@15m=1) | 107 | 0 | stop_width=55; risk_denied=46 (diğer=30, max_same_dir_risk=16); arm_conflict=6 (GF1-KANAL@15m=1, GF1-KANAL@1h=1, GF1-SAHTE@1h=1, M1@1h=1, IN1-BOLL@1h=1, GF1-BAYRAK@15m=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@1h | 16 | 0 | risk_denied=8 (diğer=4, max_same_dir_risk=3, korelasyon_grubu=1); stop_width=6; arm_conflict=2 (GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1) | 12 | 0 | risk_denied=6 (diğer=4, max_same_dir_risk=2); stop_width=4; arm_conflict=2 (GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@4h | 18 | 0 | risk_denied=16 (diğer=16); arm_conflict=2 (GF1-UCLU@4h=1, PA2-ONCEKI@4h=1) | 18 | 0 | risk_denied=16 (diğer=16); arm_conflict=2 (GF1-UCLU@4h=1, PA2-ONCEKI@4h=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@15m | 75 | 0 | stop_width=60; risk_denied=10 (max_same_dir_risk=7, diğer=3); arm_conflict=3 (IN1-RSI2@1h=1, MF1-DISBAR@1h=1, GF1-KANAL@15m=1); cluster_cap=1 (hisse=1); session_closed=1 | 48 | 0 | stop_width=34; risk_denied=9 (max_same_dir_risk=7, diğer=2); arm_conflict=3 (IN1-RSI2@1h=1, MF1-DISBAR@1h=1, GF1-KANAL@15m=1); cluster_cap=1 (hisse=1); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@1h | 11 | 0 | risk_denied=7 (diğer=6, max_same_dir_risk=1); stop_width=4 | 6 | 0 | risk_denied=4 (diğer=3, max_same_dir_risk=1); stop_width=2 | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@4h | 1 | 0 | risk_denied=1 (diğer=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@15m | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@15m | 66 | 0 | stop_width=52; risk_denied=9 (diğer=5, max_same_dir_risk=4); arm_conflict=5 (H2@15m=1, MF1-ICSAHTE@1h=1, GF1-KUPA@1h=1, T1@15m=1, IN1-BOLL@1h=1) | 46 | 0 | stop_width=33; risk_denied=8 (max_same_dir_risk=4, diğer=4); arm_conflict=5 (H2@15m=1, MF1-ICSAHTE@1h=1, GF1-KUPA@1h=1, T1@15m=1, IN1-BOLL@1h=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@1h | 17 | 0 | stop_width=7; risk_denied=5 (diğer=3, max_same_dir_risk=2); arm_conflict=5 (MF1-DELICI@1h=2, MF1-DISBAR@1h=1, PA2-ONCEKI@1h=1, T1@1h=1) | 12 | 0 | arm_conflict=5 (MF1-DELICI@1h=2, MF1-DISBAR@1h=1, PA2-ONCEKI@1h=1, T1@1h=1); stop_width=5; risk_denied=2 (max_same_dir_risk=2) | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@15m | 67 | 0 | stop_width=55; risk_denied=8 (max_same_dir_risk=4, diğer=2, margin_total=1, korelasyon_grubu=1); arm_conflict=3 (PA2-EMIRBLOK@15m=1, IN1-MAKESISIM@1h=1, MF1-HARAMI@15m=1); etiket_rejim=1 | 50 | 0 | stop_width=38; risk_denied=8 (max_same_dir_risk=4, diğer=2, margin_total=1, korelasyon_grubu=1); arm_conflict=3 (PA2-EMIRBLOK@15m=1, IN1-MAKESISIM@1h=1, MF1-HARAMI@15m=1); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@1h | 15 | 0 | stop_width=6; risk_denied=6 (diğer=4, max_same_dir_risk=2); arm_conflict=2 (GF1-TREND@1h=1, GF1-SAHTE@1h=1); session_closed=1 | 11 | 0 | risk_denied=5 (diğer=3, max_same_dir_risk=2); stop_width=3; arm_conflict=2 (GF1-TREND@1h=1, GF1-SAHTE@1h=1); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@15m | 180 | 0 | stop_width=93; risk_denied=65 (max_same_dir_risk=33, diğer=26, korelasyon_grubu=6); arm_conflict=13 (GF1-KANAL@1h=2, MF1-DELICI@1h=2, H2@15m=1, GF1-BAYRAK@15m=1, T1-GERI3@15m=1, GF1-YATAY@15m=1, GF1-UCLU@15m=1, PA2-ONCEKI@1h=1, IN1-MACD@1h=1, T1-GERI3@1h=1, T1@1h=1); cluster_cap=4 (hisse=4); etiket_rejim=3; session_closed=2 | 113 | 0 | stop_width=50; risk_denied=44 (max_same_dir_risk=20, diğer=20, korelasyon_grubu=4); arm_conflict=10 (GF1-KANAL@1h=2, MF1-DELICI@1h=2, GF1-YATAY@15m=1, GF1-UCLU@15m=1, PA2-ONCEKI@1h=1, IN1-MACD@1h=1, T1-GERI3@1h=1, T1@1h=1); cluster_cap=4 (hisse=4); etiket_rejim=3; session_closed=2 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@1h | 66 | 0 | risk_denied=46 (max_same_dir_risk=24, diğer=19, korelasyon_grubu=3); stop_width=9; arm_conflict=9 (T1-GERI3@1h=1, S1@1h=1, S1@4h=1, B1-BOLGE@4h=1, GF1-UCGEN@1h=1, MF1-ICSAHTE@1h=1, T1-SEVIYE@4h=1, T1@1h=1, GF1-BAYRAK@1h=1); etiket_rejim=2 | 48 | 0 | risk_denied=36 (diğer=18, max_same_dir_risk=17, korelasyon_grubu=1); arm_conflict=7 (S1@4h=1, B1-BOLGE@4h=1, GF1-UCGEN@1h=1, MF1-ICSAHTE@1h=1, T1-SEVIYE@4h=1, T1@1h=1, GF1-BAYRAK@1h=1); stop_width=3; etiket_rejim=2 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@4h | 17 | 0 | risk_denied=15 (max_same_dir_risk=8, korelasyon_grubu=4, diğer=2, margin_total=1); arm_conflict=2 (GF1-BAYRAK@4h=1, MF1-DISBAR@4h=1) | 6 | 0 | risk_denied=5 (max_same_dir_risk=3, diğer=2); arm_conflict=1 (MF1-DISBAR@4h=1) | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@15m | 45 | 0 | risk_denied=25 (diğer=12, max_same_dir_risk=9, korelasyon_grubu=3, margin_total=1); stop_width=9; arm_conflict=8 (GF1-YATAY@15m=1, H2@15m=1, GF1-TREND@1h=1, MF1-ICSAHTE@1h=1, GF1-KANAL@1h=1, MF1-DELICI@1h=1, IN1-MACD@1h=1, GF1-UCLU@15m=1); cluster_cap=3 (hisse=3) | 28 | 0 | risk_denied=13 (diğer=9, max_same_dir_risk=3, margin_total=1); arm_conflict=8 (GF1-YATAY@15m=1, H2@15m=1, GF1-TREND@1h=1, MF1-ICSAHTE@1h=1, GF1-KANAL@1h=1, MF1-DELICI@1h=1, IN1-MACD@1h=1, GF1-UCLU@15m=1); stop_width=4; cluster_cap=3 (hisse=3) | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@1h | 3 | 0 | risk_denied=3 (diğer=3) | 2 | 0 | risk_denied=2 (diğer=2) | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@15m | 13 | 0 | stop_width=9; risk_denied=3 (korelasyon_grubu=2, max_same_dir_risk=1); cluster_cap=1 (hisse=1) | 9 | 0 | stop_width=6; risk_denied=2 (max_same_dir_risk=1, korelasyon_grubu=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@1h | 2 | 0 | risk_denied=2 (max_same_dir_risk=2) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@4h | 2 | 0 | cluster_cap=1 (hisse=1); stop_width=1 | 2 | 0 | cluster_cap=1 (hisse=1); stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@15m | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@15m | 17 | 0 | stop_width=10; arm_conflict=4 (F1@15m=4); risk_denied=3 (max_same_dir_risk=2, diğer=1) | 15 | 0 | stop_width=9; arm_conflict=4 (F1@15m=4); risk_denied=2 (max_same_dir_risk=2) | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@1h | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@15m | 86 | 0 | stop_width=46; risk_denied=35 (max_same_dir_risk=29, korelasyon_grubu=5, diğer=1); arm_conflict=5 (T1-GERI3@15m=4, GF1-RETEST@1h=1) | 52 | 0 | risk_denied=26 (max_same_dir_risk=23, korelasyon_grubu=2, diğer=1); stop_width=22; arm_conflict=4 (T1-GERI3@15m=3, GF1-RETEST@1h=1) | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@1h | 17 | 0 | risk_denied=9 (korelasyon_grubu=8, max_same_dir_risk=1); stop_width=4; arm_conflict=4 (T1-GERI3@1h=4) | 6 | 0 | arm_conflict=3 (T1-GERI3@1h=3); stop_width=2; risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@4h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@15m | 41 | 0 | risk_denied=27 (max_same_dir_risk=19, korelasyon_grubu=7, diğer=1); stop_width=11; arm_conflict=3 (H2@15m=3) | 18 | 0 | risk_denied=13 (max_same_dir_risk=9, korelasyon_grubu=3, diğer=1); stop_width=3; arm_conflict=2 (H2@15m=2) | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@1h | 12 | 0 | risk_denied=10 (max_same_dir_risk=7, korelasyon_grubu=3); stop_width=1; arm_conflict=1 (S1@4h=1) | 6 | 0 | risk_denied=5 (max_same_dir_risk=4, korelasyon_grubu=1); arm_conflict=1 (S1@4h=1) | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@15m | 3 | 0 | stop_width=2; risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@15m | 3 | 0 | stop_width=2; risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@15m | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@15m | 7 | 0 | risk_denied=5 (korelasyon_grubu=3, max_same_dir_risk=2); arm_conflict=1 (S1@15m=1); stop_width=1 | 5 | 0 | risk_denied=4 (korelasyon_grubu=2, max_same_dir_risk=2); stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@1h | 5 | 0 | risk_denied=5 (max_same_dir_risk=3, korelasyon_grubu=2) | 4 | 0 | risk_denied=4 (max_same_dir_risk=3, korelasyon_grubu=1) | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@15m | 31 | 0 | rr_below_min=13; stop_width=11; risk_denied=7 (max_same_dir_risk=5, korelasyon_grubu=2) | 20 | 0 | rr_below_min=9; risk_denied=7 (max_same_dir_risk=5, korelasyon_grubu=2); stop_width=4 | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@1h | 18 | 0 | rr_below_min=15; arm_conflict=2 (T1-GERI3@1h=1, S1@1h=1); risk_denied=1 (max_same_dir_risk=1) | 10 | 0 | rr_below_min=10 | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@4h | 5 | 0 | rr_below_min=5 | 3 | 0 | rr_below_min=3 | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@15m | 127 | 0 | risk_denied=64 (max_same_dir_risk=57, korelasyon_grubu=6, margin_total=1); stop_width=58; cluster_cap=3 (hisse=3); arm_conflict=2 (GF1-RETEST@1h=1, T1@1h=1) | 90 | 0 | risk_denied=49 (max_same_dir_risk=45, korelasyon_grubu=4); stop_width=36; cluster_cap=3 (hisse=3); arm_conflict=2 (GF1-RETEST@1h=1, T1@1h=1) | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@1h | 21 | 0 | risk_denied=12 (korelasyon_grubu=5, max_same_dir_risk=5, margin_total=2); stop_width=6; session_closed=2; arm_conflict=1 (T1@1h=1) | 13 | 0 | risk_denied=6 (max_same_dir_risk=5, margin_total=1); stop_width=4; session_closed=2; arm_conflict=1 (T1@1h=1) | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@4h | 2 | 0 | risk_denied=2 (max_same_dir_risk=2) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@15m | 53 | 0 | risk_denied=30 (max_same_dir_risk=25, korelasyon_grubu=5); stop_width=23 | 20 | 0 | risk_denied=13 (max_same_dir_risk=12, korelasyon_grubu=1); stop_width=7 | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@1h | 16 | 0 | risk_denied=12 (max_same_dir_risk=10, korelasyon_grubu=1, diğer=1); stop_width=4 | 11 | 0 | risk_denied=8 (max_same_dir_risk=6, korelasyon_grubu=1, diğer=1); stop_width=3 | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@4h | 11 | 0 | risk_denied=7 (max_same_dir_risk=7); cluster_cap=3 (hisse=3); stop_width=1 | 11 | 0 | risk_denied=7 (max_same_dir_risk=7); cluster_cap=3 (hisse=3); stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@15m | 22 | 0 | risk_denied=15 (max_same_dir_risk=13, korelasyon_grubu=2); stop_width=7 | 9 | 0 | risk_denied=8 (max_same_dir_risk=7, korelasyon_grubu=1); stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@1h | 9 | 0 | risk_denied=7 (max_same_dir_risk=6, korelasyon_grubu=1); arm_conflict=2 (TF1@1h=1, MF1-ICSAHTE@4h=1) | 8 | 0 | risk_denied=6 (max_same_dir_risk=5, korelasyon_grubu=1); arm_conflict=2 (TF1@1h=1, MF1-ICSAHTE@4h=1) | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@4h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@15m | 14 | 0 | risk_denied=12 (max_same_dir_risk=10, korelasyon_grubu=2); arm_conflict=1 (TF1@15m=1); stop_width=1 | 9 | 0 | risk_denied=8 (max_same_dir_risk=8); stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@1h | 4 | 0 | risk_denied=3 (max_same_dir_risk=2, korelasyon_grubu=1); arm_conflict=1 (MF1-ICSAHTE@4h=1) | 3 | 0 | risk_denied=2 (max_same_dir_risk=2); arm_conflict=1 (MF1-ICSAHTE@4h=1) | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@4h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@15m | 159 | 0 | risk_denied=103 (diğer=55, max_same_dir_risk=39, korelasyon_grubu=7, margin_total=2); stop_width=38; cluster_cap=11 (hisse_teknoloji=7, hisse=4); arm_conflict=4 (IN1-RSI2@1h=2, IN1-MAKESISIM@1h=1, GF1-BAYRAK@1h=1); rr_below_min=2; session_closed=1 | 127 | 0 | risk_denied=96 (diğer=54, max_same_dir_risk=33, korelasyon_grubu=7, margin_total=2); stop_width=20; cluster_cap=4 (hisse=4); arm_conflict=4 (IN1-RSI2@1h=2, IN1-MAKESISIM@1h=1, GF1-BAYRAK@1h=1); rr_below_min=2; session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@1h | 23 | 0 | risk_denied=15 (max_same_dir_risk=13, diğer=1, korelasyon_grubu=1); arm_conflict=4 (S1@4h=1, M1@1h=1, GF1-KUPA@1h=1, T1-SEVIYE@4h=1); stop_width=2; cluster_cap=1 (hisse=1); session_closed=1 | 17 | 0 | risk_denied=10 (max_same_dir_risk=9, korelasyon_grubu=1); arm_conflict=4 (S1@4h=1, M1@1h=1, GF1-KUPA@1h=1, T1-SEVIYE@4h=1); cluster_cap=1 (hisse=1); stop_width=1; session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@4h | 21 | 0 | risk_denied=18 (max_same_dir_risk=15, korelasyon_grubu=2, margin_total=1); arm_conflict=2 (T1-SEVIYE@4h=2); cluster_cap=1 (hisse=1) | 15 | 0 | risk_denied=12 (max_same_dir_risk=11, korelasyon_grubu=1); arm_conflict=2 (T1-SEVIYE@4h=2); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@15m | 2 | 0 | stop_width=1; risk_denied=1 (max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@1h | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@15m | 53 | 1 | risk_denied=37 (diğer=20, max_same_dir_risk=16, korelasyon_grubu=1); arm_conflict=8 (GF1-UCLU@15m=5, TF1@15m=1, IN1-FIYATMA@1h=1, GF1-KANAL@1h=1); stop_width=6; cluster_cap=1 (hisse=1) | 31 | 1 | risk_denied=22 (diğer=15, max_same_dir_risk=7); arm_conflict=5 (GF1-UCLU@15m=4, GF1-KANAL@1h=1); stop_width=2; cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@1h | 19 | 0 | risk_denied=14 (diğer=12, max_same_dir_risk=2); arm_conflict=5 (GF1-UCLU@1h=1, IN1-RSI2@4h=1, S1@4h=1, IN1-HIZLIMA@4h=1, M1@1h=1) | 17 | 0 | risk_denied=13 (diğer=12, max_same_dir_risk=1); arm_conflict=4 (IN1-RSI2@4h=1, S1@4h=1, IN1-HIZLIMA@4h=1, M1@1h=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@15m | 14 | 0 | stop_width=6; risk_denied=5 (diğer=4, max_same_dir_risk=1); cluster_cap=2 (hisse=2); arm_conflict=1 (GF1-UCLU@15m=1) | 7 | 0 | cluster_cap=2 (hisse=2); risk_denied=2 (diğer=2); stop_width=2; arm_conflict=1 (GF1-UCLU@15m=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@1h | 4 | 0 | risk_denied=3 (diğer=2, max_same_dir_risk=1); cluster_cap=1 (hisse=1) | 2 | 0 | cluster_cap=1 (hisse=1); risk_denied=1 (diğer=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@4h | 2 | 0 | risk_denied=1 (korelasyon_grubu=1); cluster_cap=1 (hisse=1) | 1 | 0 | cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@15m | 196 | 0 | stop_width=144; risk_denied=41 (diğer=28, max_same_dir_risk=10, korelasyon_grubu=3); arm_conflict=7 (IN1-BOLL@1h=2, F1@15m=2, GF1-TREND@1h=1, MF1-ICSAHTE@1h=1, MF1-DISBAR@1h=1); cluster_cap=3 (hisse=3); session_closed=1 | 131 | 0 | stop_width=90; risk_denied=30 (diğer=19, max_same_dir_risk=8, korelasyon_grubu=3); arm_conflict=7 (IN1-BOLL@1h=2, F1@15m=2, GF1-TREND@1h=1, MF1-ICSAHTE@1h=1, MF1-DISBAR@1h=1); cluster_cap=3 (hisse=3); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@1h | 17 | 0 | stop_width=8; risk_denied=4 (diğer=3, max_same_dir_risk=1); cluster_cap=4 (hisse=4); arm_conflict=1 (GF1-KAMA@1h=1) | 10 | 0 | cluster_cap=4 (hisse=4); stop_width=4; risk_denied=1 (diğer=1); arm_conflict=1 (GF1-KAMA@1h=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@4h | 2 | 0 | stop_width=1; arm_conflict=1 (GF1-KAMA@4h=1) | 1 | 0 | arm_conflict=1 (GF1-KAMA@4h=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@15m | 4 | 0 | stop_width=2; risk_denied=2 (diğer=2) | 4 | 0 | stop_width=2; risk_denied=2 (diğer=2) | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@1h | 2 | 0 | risk_denied=1 (max_same_dir_risk=1); cluster_cap=1 (hisse=1) | 1 | 0 | cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@15m | 1 | 0 | risk_denied=1 (diğer=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@15m | 71 | 0 | stop_width=53; risk_denied=15 (max_same_dir_risk=8, diğer=6, korelasyon_grubu=1); rr_below_min=3 | 42 | 0 | stop_width=29; risk_denied=10 (diğer=6, max_same_dir_risk=3, korelasyon_grubu=1); rr_below_min=3 | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@1h | 15 | 0 | risk_denied=6 (max_same_dir_risk=5, diğer=1); stop_width=5; arm_conflict=3 (M1@1h=1, IN1-FIYATMA@4h=1, GF1-BAYRAK@1h=1); session_closed=1 | 11 | 0 | risk_denied=5 (max_same_dir_risk=4, diğer=1); stop_width=3; arm_conflict=2 (IN1-FIYATMA@4h=1, GF1-BAYRAK@1h=1); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@4h | 6 | 0 | risk_denied=4 (max_same_dir_risk=4); arm_conflict=2 (T1-SEVIYE@4h=1, B1@4h=1) | 6 | 0 | risk_denied=4 (max_same_dir_risk=4); arm_conflict=2 (T1-SEVIYE@4h=1, B1@4h=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@15m | 69 | 0 | stop_width=37; risk_denied=24 (diğer=23, max_same_dir_risk=1); arm_conflict=8 (GF1-TREND@1h=1, GF1-SAHTE@1h=1, MF1-ICSAHTE@1h=1, MF1-DISBAR@1h=1, GF1-KANAL@1h=1, IN1-BOLL@1h=1, T1@15m=1, F1@15m=1) | 55 | 0 | stop_width=24; risk_denied=23 (diğer=22, max_same_dir_risk=1); arm_conflict=8 (GF1-TREND@1h=1, GF1-SAHTE@1h=1, MF1-ICSAHTE@1h=1, MF1-DISBAR@1h=1, GF1-KANAL@1h=1, IN1-BOLL@1h=1, T1@15m=1, F1@15m=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@1h | 13 | 0 | risk_denied=10 (diğer=10); stop_width=2; cluster_cap=1 (hisse=1) | 7 | 0 | risk_denied=6 (diğer=6); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@4h | 3 | 0 | risk_denied=3 (diğer=3) | 2 | 0 | risk_denied=2 (diğer=2) | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@15m | 40 | 0 | risk_denied=29 (diğer=26, max_same_dir_risk=3); arm_conflict=6 (IN1-RSI2@1h=2, IN1-RSIDONUS@1h=1, GF1-UCLU@15m=1, GF1-BAYRAK@15m=1, T1-GERI3@1h=1); stop_width=3; etiket_rejim=1; session_closed=1 | 29 | 0 | risk_denied=20 (diğer=19, max_same_dir_risk=1); arm_conflict=6 (IN1-RSI2@1h=2, IN1-RSIDONUS@1h=1, GF1-UCLU@15m=1, GF1-BAYRAK@15m=1, T1-GERI3@1h=1); stop_width=1; etiket_rejim=1; session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@1h | 9 | 0 | risk_denied=7 (max_same_dir_risk=3, diğer=3, korelasyon_grubu=1); cluster_cap=1 (hisse=1); arm_conflict=1 (GF1-UCLU@1h=1) | 6 | 0 | risk_denied=4 (diğer=3, max_same_dir_risk=1); cluster_cap=1 (hisse=1); arm_conflict=1 (GF1-UCLU@1h=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@4h | 4 | 0 | risk_denied=4 (diğer=3, korelasyon_grubu=1) | 3 | 0 | risk_denied=3 (diğer=3) | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@15m | 7 | 0 | risk_denied=5 (korelasyon_grubu=3, max_same_dir_risk=2); arm_conflict=1 (TF1@15m=1); stop_width=1 | 2 | 0 | stop_width=1; risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@1h | 5 | 0 | etiket_rejim=2; arm_conflict=1 (GF1-UCLU@1h=1); cluster_cap=1 (hisse=1); risk_denied=1 (diğer=1) | 3 | 0 | cluster_cap=1 (hisse=1); risk_denied=1 (diğer=1); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@4h | 2 | 0 | risk_denied=2 (korelasyon_grubu=1, max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@15m | 61 | 1 | risk_denied=49 (diğer=24, max_same_dir_risk=21, margin_total=3, korelasyon_grubu=1); cluster_cap=5 (hisse=4, hisse_teknoloji=1); arm_conflict=3 (S1@15m=1, M1@1h=1, GF1-UCGEN@1h=1); etiket_rejim=2; stop_width=1 | 41 | 0 | risk_denied=34 (diğer=22, max_same_dir_risk=11, margin_total=1); cluster_cap=4 (hisse=4); arm_conflict=2 (M1@1h=1, GF1-UCGEN@1h=1); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@1h | 15 | 1 | risk_denied=11 (diğer=8, max_same_dir_risk=3); arm_conflict=2 (S1@4h=1, M1@1h=1); etiket_rejim=1 | 13 | 0 | risk_denied=10 (diğer=8, max_same_dir_risk=2); arm_conflict=2 (S1@4h=1, M1@1h=1); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@4h | 1 | 0 | etiket_rejim=1 | 1 | 0 | etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@15m | 140 | 0 | stop_width=77; risk_denied=57 (max_same_dir_risk=33, diğer=16, korelasyon_grubu=8); rr_below_min=3; arm_conflict=2 (GF1-KANAL@1h=1, GF1-UCLU@15m=1); cluster_cap=1 (hisse=1) | 97 | 0 | risk_denied=46 (max_same_dir_risk=25, diğer=16, korelasyon_grubu=5); stop_width=45; rr_below_min=3; arm_conflict=2 (GF1-KANAL@1h=1, GF1-UCLU@15m=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@1h | 32 | 0 | risk_denied=19 (max_same_dir_risk=13, korelasyon_grubu=4, diğer=2); stop_width=10; arm_conflict=2 (T1-GERI3@1h=1, GF1-KUPA@1h=1); rr_below_min=1 | 19 | 0 | risk_denied=11 (max_same_dir_risk=8, diğer=2, korelasyon_grubu=1); stop_width=6; arm_conflict=1 (GF1-KUPA@1h=1); rr_below_min=1 | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@4h | 6 | 0 | risk_denied=5 (max_same_dir_risk=5); arm_conflict=1 (GF1-UCLU@4h=1) | 3 | 0 | risk_denied=2 (max_same_dir_risk=2); arm_conflict=1 (GF1-UCLU@4h=1) | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@15m | 791 | 0 | stop_width=680; risk_denied=75 (diğer=43, max_same_dir_risk=29, korelasyon_grubu=3); arm_conflict=17 (M1@1h=2, F1@15m=2, IN1-HACIM@1h=1, GF1-TREND@1h=1, MF1-DISBAR@1h=1, GF1-KUPA@1h=1, IN1-BOLL@1h=1, T1@15m=1, T1-SEVIYE@4h=1, IN1-RSIDONUS@15m=1, GF1-KANAL@15m=1, PA2-EMIRBLOK@15m=1, IN1-VWAP@15m=1, IN1-MAKESISIM@1h=1, MF1-HARAMI@15m=1); rr_below_min=16; cluster_cap=3 (hisse=3) | 479 | 0 | stop_width=387; risk_denied=61 (diğer=29, max_same_dir_risk=29, korelasyon_grubu=3); arm_conflict=16 (M1@1h=2, F1@15m=2, GF1-TREND@1h=1, MF1-DISBAR@1h=1, GF1-KUPA@1h=1, IN1-BOLL@1h=1, T1@15m=1, T1-SEVIYE@4h=1, IN1-RSIDONUS@15m=1, GF1-KANAL@15m=1, PA2-EMIRBLOK@15m=1, IN1-VWAP@15m=1, IN1-MAKESISIM@1h=1, MF1-HARAMI@15m=1); rr_below_min=12; cluster_cap=3 (hisse=3) | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@1h | 295 | 1 | stop_width=186; risk_denied=82 (diğer=56, max_same_dir_risk=21, korelasyon_grubu=3, margin_total=2); arm_conflict=18 (T1-SEVIYE@4h=2, GF1-KANAL@1h=2, M1@1h=2, MF1-DELICI@1h=2, IN1-RSIDONUS@1h=1, IN1-RSI2@1h=1, GF1-TREND@1h=1, GF1-SAHTE@1h=1, MF1-ICSAHTE@1h=1, MF1-DISBAR@1h=1, GF1-KUPA@1h=1, PA2-ONCEKI@1h=1, IN1-MAKESISIM@1h=1, MF1-PINBAR@1h=1); rr_below_min=4; cluster_cap=3 (hisse=3); etiket_rejim=1 | 229 | 1 | stop_width=138; risk_denied=65 (diğer=39, max_same_dir_risk=21, korelasyon_grubu=3, margin_total=2); arm_conflict=18 (T1-SEVIYE@4h=2, GF1-KANAL@1h=2, M1@1h=2, MF1-DELICI@1h=2, IN1-RSIDONUS@1h=1, IN1-RSI2@1h=1, GF1-TREND@1h=1, GF1-SAHTE@1h=1, MF1-ICSAHTE@1h=1, MF1-DISBAR@1h=1, GF1-KUPA@1h=1, PA2-ONCEKI@1h=1, IN1-MAKESISIM@1h=1, MF1-PINBAR@1h=1); rr_below_min=4; cluster_cap=3 (hisse=3) | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@4h | 55 | 0 | risk_denied=25 (diğer=21, max_same_dir_risk=4); stop_width=22; arm_conflict=5 (T1-SEVIYE@4h=2, GF1-BAYRAK@4h=1, IN1-TK@4h=1, PA2-ONCEKI@4h=1); rr_below_min=3 | 45 | 0 | risk_denied=23 (diğer=19, max_same_dir_risk=4); stop_width=14; arm_conflict=5 (T1-SEVIYE@4h=2, GF1-BAYRAK@4h=1, IN1-TK@4h=1, PA2-ONCEKI@4h=1); rr_below_min=3 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@15m | 165 | 0 | risk_denied=102 (max_same_dir_risk=51, diğer=34, korelasyon_grubu=17); stop_width=44; arm_conflict=17 (GF1-BAYRAK@15m=5, T1-GERI3@15m=3, TF1@15m=2, S1@15m=1, T1-GERI3@1h=1, GF1-YATAY@15m=1, GF1-KANAL@1h=1, GF1-UCLU@15m=1, IN1-MACD@1h=1, MF1-MARUBOZU@15m=1); cluster_cap=2 (hisse=2) | 101 | 0 | risk_denied=76 (max_same_dir_risk=40, diğer=30, korelasyon_grubu=6); stop_width=13; arm_conflict=10 (T1-GERI3@15m=3, TF1@15m=1, GF1-YATAY@15m=1, GF1-KANAL@1h=1, GF1-UCLU@15m=1, IN1-MACD@1h=1, MF1-MARUBOZU@15m=1, GF1-BAYRAK@15m=1); cluster_cap=2 (hisse=2) | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@1h | 63 | 0 | risk_denied=49 (max_same_dir_risk=25, diğer=15, korelasyon_grubu=8, margin_total=1); arm_conflict=8 (T1-SEVIYE@4h=2, TF1@1h=1, S1@1h=1, IN1-RSI2@1h=1, IN1-FIYATMA@4h=1, GF1-KAMA@4h=1, IN1-MAKESISIM@1h=1); stop_width=5; session_closed=1 | 46 | 0 | risk_denied=34 (max_same_dir_risk=16, diğer=15, korelasyon_grubu=3); arm_conflict=8 (T1-SEVIYE@4h=2, TF1@1h=1, S1@1h=1, IN1-RSI2@1h=1, IN1-FIYATMA@4h=1, GF1-KAMA@4h=1, IN1-MAKESISIM@1h=1); stop_width=3; session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@4h | 13 | 0 | risk_denied=10 (max_same_dir_risk=8, diğer=2); arm_conflict=3 (GF1-BAYRAK@4h=1, GF1-KAMA@4h=1, GF1-UCLU@4h=1) | 8 | 0 | risk_denied=6 (max_same_dir_risk=4, diğer=2); arm_conflict=2 (GF1-KAMA@4h=1, GF1-UCLU@4h=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@15m | 15 | 0 | risk_denied=11 (max_same_dir_risk=9, diğer=2); stop_width=2; arm_conflict=2 (PA2-BOLGE@15m=1, MF1-HARAMI@15m=1) | 10 | 0 | risk_denied=8 (max_same_dir_risk=8); arm_conflict=2 (PA2-BOLGE@15m=1, MF1-HARAMI@15m=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@1h | 1 | 0 | risk_denied=1 (diğer=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@4h | 1 | 0 | arm_conflict=1 (B1-BOLGE@4h=1) | 1 | 0 | arm_conflict=1 (B1-BOLGE@4h=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@15m | 131 | 0 | risk_denied=69 (diğer=45, max_same_dir_risk=16, korelasyon_grubu=8); stop_width=48; arm_conflict=13 (IN1-VWAP@15m=5, IN1-RSI2@15m=2, GF1-KANAL@1h=1, T1@15m=1, IN1-MACD@15m=1, IN1-MACD@1h=1, GF1-KAMA@15m=1, MF1-MARUBOZU@15m=1); cluster_cap=1 (hisse=1) | 79 | 0 | risk_denied=35 (diğer=29, max_same_dir_risk=6); stop_width=30; arm_conflict=13 (IN1-VWAP@15m=5, IN1-RSI2@15m=2, GF1-KANAL@1h=1, T1@15m=1, IN1-MACD@15m=1, IN1-MACD@1h=1, GF1-KAMA@15m=1, MF1-MARUBOZU@15m=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@1h | 39 | 0 | risk_denied=21 (diğer=17, max_same_dir_risk=3, margin_total=1); arm_conflict=15 (IN1-RSI2@1h=4, IN1-MACD@1h=2, GF1-UCGEN@1h=1, IN1-RSI2@4h=1, S1@1h=1, T1@1h=1, GF1-KAMA@1h=1, MF1-DISBAR@1h=1, MF1-DISBAR@4h=1, MF1-ICCUBUK@1h=1, IN1-MAKESISIM@1h=1); session_closed=2; stop_width=1 | 32 | 0 | risk_denied=18 (diğer=16, max_same_dir_risk=2); arm_conflict=12 (IN1-MACD@1h=2, IN1-RSI2@1h=2, IN1-RSI2@4h=1, S1@1h=1, T1@1h=1, GF1-KAMA@1h=1, MF1-DISBAR@1h=1, MF1-DISBAR@4h=1, MF1-ICCUBUK@1h=1, IN1-MAKESISIM@1h=1); session_closed=2 | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@4h | 12 | 0 | risk_denied=9 (diğer=7, max_same_dir_risk=2); arm_conflict=2 (GF1-KAMA@4h=1, GF1-UCLU@4h=1); cluster_cap=1 (hisse=1) | 11 | 0 | risk_denied=8 (diğer=7, max_same_dir_risk=1); arm_conflict=2 (GF1-KAMA@4h=1, GF1-UCLU@4h=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@15m | 106 | 0 | risk_denied=60 (max_same_dir_risk=46, korelasyon_grubu=11, diğer=3); stop_width=41; arm_conflict=5 (GF1-UCLU@15m=2, GF1-YATAY@15m=1, GF1-KANAL@1h=1, GF1-KANAL@15m=1) | 73 | 0 | risk_denied=47 (max_same_dir_risk=38, korelasyon_grubu=6, diğer=3); stop_width=21; arm_conflict=5 (GF1-UCLU@15m=2, GF1-YATAY@15m=1, GF1-KANAL@1h=1, GF1-KANAL@15m=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@1h | 38 | 0 | risk_denied=31 (max_same_dir_risk=19, diğer=8, korelasyon_grubu=4); arm_conflict=6 (M1@1h=1, MF1-DISBAR@1h=1, GF1-KUPA@1h=1, GF1-KAMA@4h=1, T1-SEVIYE@4h=1, IN1-MAKESISIM@1h=1); stop_width=1 | 35 | 0 | risk_denied=28 (max_same_dir_risk=17, diğer=8, korelasyon_grubu=3); arm_conflict=6 (M1@1h=1, MF1-DISBAR@1h=1, GF1-KUPA@1h=1, GF1-KAMA@4h=1, T1-SEVIYE@4h=1, IN1-MAKESISIM@1h=1); stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@4h | 14 | 0 | risk_denied=9 (max_same_dir_risk=9); arm_conflict=5 (T1-SEVIYE@4h=3, GF1-BAYRAK@4h=1, GF1-UCLU@4h=1) | 13 | 0 | risk_denied=8 (max_same_dir_risk=8); arm_conflict=5 (T1-SEVIYE@4h=3, GF1-BAYRAK@4h=1, GF1-UCLU@4h=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@15m | 223 | 0 | risk_denied=130 (diğer=64, max_same_dir_risk=43, korelasyon_grubu=23); stop_width=62; arm_conflict=25 (IN1-RSI2@15m=7, IN1-MACD@15m=3, GF1-IKILI@15m=2, H2@15m=2, GF1-KANAL@1h=2, MF1-MARUBOZU@15m=2, IN1-RSIDONUS@1h=1, MF1-ICSAHTE@1h=1, IN1-VWAP@15m=1, MF1-DISBAR@15m=1, MF1-HARAMI@15m=1, B1@4h=1, MF1-ICCUBUK@15m=1); cluster_cap=3 (hisse=3); session_closed=3 | 113 | 0 | risk_denied=56 (diğer=33, max_same_dir_risk=22, korelasyon_grubu=1); stop_width=26; arm_conflict=25 (IN1-RSI2@15m=7, IN1-MACD@15m=3, GF1-IKILI@15m=2, H2@15m=2, GF1-KANAL@1h=2, MF1-MARUBOZU@15m=2, IN1-RSIDONUS@1h=1, MF1-ICSAHTE@1h=1, IN1-VWAP@15m=1, MF1-DISBAR@15m=1, MF1-HARAMI@15m=1, B1@4h=1, MF1-ICCUBUK@15m=1); cluster_cap=3 (hisse=3); session_closed=3 | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@1h | 47 | 0 | risk_denied=29 (diğer=25, max_same_dir_risk=3, korelasyon_grubu=1); arm_conflict=16 (IN1-MACD@1h=3, IN1-RSI2@1h=2, GF1-UCGEN@1h=2, M1@1h=2, T1-GERI3@1h=1, GF1-KAMA@1h=1, GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1, GF1-UCLU@1h=1, PA2-ONCEKI@4h=1, IN1-MACD@4h=1); stop_width=1; etiket_rejim=1 | 37 | 0 | risk_denied=22 (diğer=22); arm_conflict=14 (GF1-UCGEN@1h=2, M1@1h=2, IN1-MACD@1h=2, T1-GERI3@1h=1, GF1-KAMA@1h=1, GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1, IN1-RSI2@1h=1, GF1-UCLU@1h=1, PA2-ONCEKI@4h=1, IN1-MACD@4h=1); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@4h | 14 | 0 | risk_denied=9 (diğer=6, max_same_dir_risk=3); arm_conflict=4 (S1@4h=1, GF1-KAMA@4h=1, MF1-DISBAR@4h=1, GF1-UCLU@4h=1); cluster_cap=1 (hisse=1) | 12 | 0 | risk_denied=7 (diğer=6, max_same_dir_risk=1); arm_conflict=4 (S1@4h=1, GF1-KAMA@4h=1, MF1-DISBAR@4h=1, GF1-UCLU@4h=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@15m | 93 | 0 | stop_width=48; risk_denied=35 (diğer=29, max_same_dir_risk=6); arm_conflict=7 (GF1-BAYRAK@15m=2, PA2-FVG@15m=1, GF1-KANAL@1h=1, IN1-MACD@1h=1, IN1-RSI2@1h=1, F1@15m=1); session_closed=2; etiket_rejim=1 | 62 | 0 | stop_width=26; risk_denied=26 (diğer=23, max_same_dir_risk=3); arm_conflict=7 (GF1-BAYRAK@15m=2, PA2-FVG@15m=1, GF1-KANAL@1h=1, IN1-MACD@1h=1, IN1-RSI2@1h=1, F1@15m=1); session_closed=2; etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@1h | 15 | 0 | risk_denied=6 (diğer=5, max_same_dir_risk=1); stop_width=5; arm_conflict=4 (S1@4h=1, GF1-KAMA@4h=1, IN1-HIZLIMA@4h=1, MF1-ICCUBUK@1h=1) | 10 | 0 | arm_conflict=4 (S1@4h=1, GF1-KAMA@4h=1, IN1-HIZLIMA@4h=1, MF1-ICCUBUK@1h=1); risk_denied=4 (diğer=4); stop_width=2 | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@4h | 5 | 0 | risk_denied=3 (korelasyon_grubu=1, max_same_dir_risk=1, diğer=1); arm_conflict=2 (GF1-KAMA@4h=1, GF1-UCLU@4h=1) | 4 | 0 | risk_denied=2 (max_same_dir_risk=1, diğer=1); arm_conflict=2 (GF1-KAMA@4h=1, GF1-UCLU@4h=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@15m | 215 | 0 | risk_denied=126 (diğer=58, max_same_dir_risk=41, korelasyon_grubu=25, margin_total=2); stop_width=57; arm_conflict=14 (IN1-RSI2@15m=6, TF1@15m=2, GF1-KANAL@1h=2, MF1-MARUBOZU@15m=2, GF1-YATAY@15m=1, MF1-DELICI@1h=1); session_closed=10; cluster_cap=6 (hisse=5, hisse_teknoloji=1); etiket_rejim=2 | 117 | 0 | risk_denied=63 (diğer=29, max_same_dir_risk=27, korelasyon_grubu=5, margin_total=2); stop_width=24; arm_conflict=13 (IN1-RSI2@15m=6, GF1-KANAL@1h=2, MF1-MARUBOZU@15m=2, TF1@15m=1, GF1-YATAY@15m=1, MF1-DELICI@1h=1); session_closed=10; cluster_cap=5 (hisse=5); etiket_rejim=2 | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@1h | 72 | 0 | risk_denied=58 (diğer=39, max_same_dir_risk=13, korelasyon_grubu=4, margin_total=2); arm_conflict=8 (S1@1h=1, MF1-HARAMI@4h=1, GF1-UCGEN@1h=1, GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1, MF1-DISBAR@4h=1, GF1-UCLU@1h=1, PA2-ONCEKI@4h=1); stop_width=2; cluster_cap=2 (hisse=2); etiket_rejim=1; session_closed=1 | 44 | 0 | risk_denied=34 (diğer=24, max_same_dir_risk=8, korelasyon_grubu=1, margin_total=1); arm_conflict=7 (MF1-HARAMI@4h=1, GF1-UCGEN@1h=1, GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1, MF1-DISBAR@4h=1, GF1-UCLU@1h=1, PA2-ONCEKI@4h=1); cluster_cap=2 (hisse=2); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@4h | 9 | 0 | risk_denied=6 (max_same_dir_risk=3, diğer=3); arm_conflict=2 (GF1-KAMA@4h=1, GF1-UCLU@4h=1); etiket_rejim=1 | 8 | 0 | risk_denied=5 (diğer=3, max_same_dir_risk=2); arm_conflict=2 (GF1-KAMA@4h=1, GF1-UCLU@4h=1); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@15m | 20 | 0 | risk_denied=11 (max_same_dir_risk=9, diğer=1, margin_total=1); stop_width=8; arm_conflict=1 (PA2-BOLGE@15m=1) | 17 | 0 | risk_denied=11 (max_same_dir_risk=9, diğer=1, margin_total=1); stop_width=5; arm_conflict=1 (PA2-BOLGE@15m=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@1h | 3 | 0 | risk_denied=3 (max_same_dir_risk=2, korelasyon_grubu=1) | 2 | 0 | risk_denied=2 (max_same_dir_risk=2) | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@4h | 1 | 0 | arm_conflict=1 (B1-BOLGE@4h=1) | 1 | 0 | arm_conflict=1 (B1-BOLGE@4h=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@15m | 8 | 0 | risk_denied=3 (diğer=2, max_same_dir_risk=1); stop_width=2; session_closed=2; arm_conflict=1 (MF1-ICCUBUK@15m=1) | 7 | 0 | risk_denied=3 (diğer=2, max_same_dir_risk=1); session_closed=2; stop_width=1; arm_conflict=1 (MF1-ICCUBUK@15m=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@1h | 6 | 0 | risk_denied=4 (margin_total=2, diğer=2); session_closed=2 | 5 | 0 | risk_denied=3 (diğer=2, margin_total=1); session_closed=2 | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@15m | 38 | 0 | stop_width=33; risk_denied=4 (max_same_dir_risk=3, diğer=1); arm_conflict=1 (IN1-MAKESISIM@1h=1) | 33 | 0 | stop_width=29; risk_denied=3 (max_same_dir_risk=3); arm_conflict=1 (IN1-MAKESISIM@1h=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@1h | 9 | 0 | stop_width=6; arm_conflict=2 (M1@1h=1, IN1-FIYATMA@4h=1); risk_denied=1 (max_same_dir_risk=1) | 8 | 0 | stop_width=5; arm_conflict=2 (M1@1h=1, IN1-FIYATMA@4h=1); risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@4h | 1 | 0 | etiket_rejim=1 | 1 | 0 | etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@15m | 373 | 7 | risk_denied=177 (max_same_dir_risk=104, diğer=34, korelasyon_grubu=30, margin_total=9); stop_width=85; max_positions=49 (arm_max_positions=49); arm_conflict=28 (IN1-RSI2@1h=4, MF1-ICCUBUK@15m=3, M1@1h=3, MF1-DELICI@1h=3, MF1-MARUBOZU@15m=3, GF1-IKILI@15m=2, IN1-RSIDONUS@1h=1, GF1-UCLU@15m=1, PA2-ONCEKI@1h=1, IN1-MACD@1h=1, GF1-KAMA@15m=1, MF1-PINBAR@15m=1, GF1-TREND@15m=1, MF1-ICCUBUK@1h=1, F1@15m=1, GF1-BAYRAK@15m=1); session_closed=17; cluster_cap=9 (hisse=9); order_failed=1 | 277 | 7 | risk_denied=115 (max_same_dir_risk=77, diğer=25, margin_total=7, korelasyon_grubu=6); stop_width=51; max_positions=49 (arm_max_positions=49); arm_conflict=28 (IN1-RSI2@1h=4, MF1-ICCUBUK@15m=3, M1@1h=3, MF1-DELICI@1h=3, MF1-MARUBOZU@15m=3, GF1-IKILI@15m=2, IN1-RSIDONUS@1h=1, GF1-UCLU@15m=1, PA2-ONCEKI@1h=1, IN1-MACD@1h=1, GF1-KAMA@15m=1, MF1-PINBAR@15m=1, GF1-TREND@15m=1, MF1-ICCUBUK@1h=1, F1@15m=1, GF1-BAYRAK@15m=1); session_closed=17; cluster_cap=9 (hisse=9); order_failed=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@1h | 106 | 3 | risk_denied=68 (max_same_dir_risk=47, diğer=13, margin_total=4, korelasyon_grubu=4); max_positions=15 (arm_max_positions=15); arm_conflict=9 (M1@1h=3, GF1-UCGEN@1h=2, IN1-MAKESISIM@1h=1, IN1-RSI2@4h=1, MF1-DISBAR@1h=1, PA2-ONCEKI@4h=1); session_closed=5; stop_width=4; cluster_cap=1 (hisse_teknoloji=1); order_failed=1 | 79 | 2 | risk_denied=49 (max_same_dir_risk=43, korelasyon_grubu=3, diğer=2, margin_total=1); max_positions=15 (arm_max_positions=15); arm_conflict=6 (M1@1h=2, IN1-RSI2@4h=1, GF1-UCGEN@1h=1, MF1-DISBAR@1h=1, PA2-ONCEKI@4h=1); session_closed=5; stop_width=1; order_failed=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@4h | 14 | 0 | risk_denied=14 (max_same_dir_risk=13, margin_total=1) | 14 | 0 | risk_denied=14 (max_same_dir_risk=13, margin_total=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@15m | 122 | 0 | risk_denied=58 (diğer=35, max_same_dir_risk=20, korelasyon_grubu=3); stop_width=53; arm_conflict=9 (M1@1h=2, IN1-BOLL@1h=2, IN1-HACIM@1h=1, GF1-TREND@1h=1, GF1-SAHTE@1h=1, GF1-KUPA@1h=1, F1@15m=1); cluster_cap=1 (hisse=1); session_closed=1 | 92 | 0 | risk_denied=51 (diğer=28, max_same_dir_risk=20, korelasyon_grubu=3); stop_width=31; arm_conflict=8 (M1@1h=2, IN1-BOLL@1h=2, GF1-TREND@1h=1, GF1-SAHTE@1h=1, GF1-KUPA@1h=1, F1@15m=1); cluster_cap=1 (hisse=1); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@1h | 28 | 0 | risk_denied=16 (diğer=15, max_same_dir_risk=1); stop_width=5; arm_conflict=5 (GF1-SAHTE@1h=1, M1@1h=1, GF1-KANAL@1h=1, PA2-ONCEKI@1h=1, MF1-DELICI@1h=1); cluster_cap=1 (hisse=1); etiket_rejim=1 | 22 | 0 | risk_denied=14 (diğer=13, max_same_dir_risk=1); arm_conflict=5 (GF1-SAHTE@1h=1, M1@1h=1, GF1-KANAL@1h=1, PA2-ONCEKI@1h=1, MF1-DELICI@1h=1); cluster_cap=1 (hisse=1); etiket_rejim=1; stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@4h | 5 | 0 | risk_denied=4 (diğer=4); arm_conflict=1 (PA2-ONCEKI@4h=1) | 5 | 0 | risk_denied=4 (diğer=4); arm_conflict=1 (PA2-ONCEKI@4h=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@15m | 5 | 0 | stop_width=4; risk_denied=1 (max_same_dir_risk=1) | 4 | 0 | stop_width=3; risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@1h | 2 | 0 | stop_width=1; session_closed=1 | 1 | 0 | session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@15m | 49 | 0 | stop_width=35; risk_denied=12 (diğer=8, max_same_dir_risk=4); arm_conflict=1 (GF1-UCLU@15m=1); etiket_rejim=1 | 24 | 0 | stop_width=15; risk_denied=7 (diğer=6, max_same_dir_risk=1); arm_conflict=1 (GF1-UCLU@15m=1); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@1h | 4 | 0 | risk_denied=2 (max_same_dir_risk=2); arm_conflict=2 (TF1@1h=1, GF1-KAMA@4h=1) | 3 | 0 | arm_conflict=2 (TF1@1h=1, GF1-KAMA@4h=1); risk_denied=1 (max_same_dir_risk=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@4h | 13 | 0 | risk_denied=12 (korelasyon_grubu=7, max_same_dir_risk=5); cluster_cap=1 (hisse=1) | 5 | 0 | risk_denied=4 (max_same_dir_risk=3, korelasyon_grubu=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@15m | 20 | 0 | stop_width=8; risk_denied=7 (diğer=4, max_same_dir_risk=2, korelasyon_grubu=1); cluster_cap=3 (hisse=3); arm_conflict=2 (GF1-KANAL@1h=1, GF1-KANAL@15m=1) | 14 | 0 | risk_denied=5 (diğer=2, max_same_dir_risk=2, korelasyon_grubu=1); stop_width=4; cluster_cap=3 (hisse=3); arm_conflict=2 (GF1-KANAL@1h=1, GF1-KANAL@15m=1) | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@1h | 9 | 0 | risk_denied=9 (diğer=9) | 8 | 0 | risk_denied=8 (diğer=8) | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| IN1-VWAP@15m | 198 | 0 | risk_denied=118 (diğer=63, max_same_dir_risk=28, korelasyon_grubu=27); stop_width=62; arm_conflict=10 (IN1-RSI2@15m=4, GF1-KANAL@1h=1, T1-GERI3@15m=1, MF1-DISBAR@15m=1, IN1-MACD@15m=1, IN1-MACD@1h=1, GF1-KAMA@15m=1); cluster_cap=7 (hisse=7); etiket_rejim=1 | 83 | 0 | risk_denied=42 (diğer=31, max_same_dir_risk=11); stop_width=23; arm_conflict=10 (IN1-RSI2@15m=4, GF1-KANAL@1h=1, T1-GERI3@15m=1, MF1-DISBAR@15m=1, IN1-MACD@15m=1, IN1-MACD@1h=1, GF1-KAMA@15m=1); cluster_cap=7 (hisse=7); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| IN1-VWAP@1h | 94 | 0 | risk_denied=76 (diğer=41, korelasyon_grubu=18, max_same_dir_risk=15, margin_total=2); arm_conflict=13 (IN1-MACD@1h=3, M1@1h=2, MF1-HARAMI@4h=1, T1-GERI3@1h=1, GF1-KAMA@1h=1, GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1, MF1-ICCUBUK@1h=1, IN1-MACD@4h=1, T1@1h=1); cluster_cap=2 (hisse=2); etiket_rejim=2; stop_width=1 | 43 | 0 | risk_denied=27 (diğer=23, max_same_dir_risk=4); arm_conflict=12 (IN1-MACD@1h=2, M1@1h=2, MF1-HARAMI@4h=1, T1-GERI3@1h=1, GF1-KAMA@1h=1, GF1-KANAL@1h=1, MF1-ICSAHTE@4h=1, MF1-ICCUBUK@1h=1, IN1-MACD@4h=1, T1@1h=1); cluster_cap=2 (hisse=2); etiket_rejim=2 | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@15m | 6 | 0 | risk_denied=6 (max_same_dir_risk=5, margin_total=1) | 5 | 0 | risk_denied=5 (max_same_dir_risk=4, margin_total=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@15m | 16 | 1 | risk_denied=9 (max_same_dir_risk=7, diğer=2); stop_width=5; arm_conflict=1 (GF1-KANAL@15m=1) | 12 | 1 | risk_denied=8 (max_same_dir_risk=7, diğer=1); stop_width=2; arm_conflict=1 (GF1-KANAL@15m=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@1h | 3 | 0 | risk_denied=2 (max_same_dir_risk=2); arm_conflict=1 (T1@1h=1) | 3 | 0 | risk_denied=2 (max_same_dir_risk=2); arm_conflict=1 (T1@1h=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@4h | 2 | 0 | risk_denied=2 (max_same_dir_risk=1, diğer=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@15m | 41 | 0 | risk_denied=26 (max_same_dir_risk=12, diğer=11, korelasyon_grubu=3); stop_width=11; arm_conflict=2 (T1-GERI3@1h=1, GF1-KAMA@15m=1); cluster_cap=1 (hisse=1); session_closed=1 | 25 | 0 | risk_denied=17 (max_same_dir_risk=8, diğer=8, korelasyon_grubu=1); stop_width=5; cluster_cap=1 (hisse=1); arm_conflict=1 (GF1-KAMA@15m=1); session_closed=1 | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@1h | 6 | 0 | risk_denied=5 (max_same_dir_risk=4, diğer=1); arm_conflict=1 (GF1-RETEST@1h=1) | 4 | 0 | risk_denied=3 (max_same_dir_risk=3); arm_conflict=1 (GF1-RETEST@1h=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-ONCEKI@15m | 13 | 0 | risk_denied=7 (diğer=4, max_same_dir_risk=3); stop_width=5; arm_conflict=1 (GF1-TREND@1h=1) | 8 | 0 | risk_denied=4 (max_same_dir_risk=3, diğer=1); stop_width=3; arm_conflict=1 (GF1-TREND@1h=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-ONCEKI@1h | 11 | 0 | risk_denied=5 (diğer=4, max_same_dir_risk=1); stop_width=4; arm_conflict=1 (GF1-KANAL@1h=1); cluster_cap=1 (hisse=1) | 5 | 0 | risk_denied=2 (diğer=1, max_same_dir_risk=1); stop_width=1; arm_conflict=1 (GF1-KANAL@1h=1); cluster_cap=1 (hisse=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-ONCEKI@4h | 3 | 0 | risk_denied=2 (diğer=2); etiket_rejim=1 | 3 | 0 | risk_denied=2 (diğer=2); etiket_rejim=1 | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@15m | 19 | 0 | stop_width=15; risk_denied=4 (max_same_dir_risk=4) | 8 | 0 | stop_width=4; risk_denied=4 (max_same_dir_risk=4) | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@1h | 5 | 0 | risk_denied=4 (max_same_dir_risk=2, diğer=1, korelasyon_grubu=1); stop_width=1 | 3 | 0 | risk_denied=3 (max_same_dir_risk=2, korelasyon_grubu=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@15m | 10 | 0 | stop_width=9; arm_conflict=1 (GF1-KANAL@15m=1) | 6 | 0 | stop_width=5; arm_conflict=1 (GF1-KANAL@15m=1) | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@1h | 1 | 0 | risk_denied=1 (diğer=1) | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@15m | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@4h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@1d | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |
| PA2-TUKENIS@15m | 1 | 0 | stop_width=1 | 1 | 0 | stop_width=1 | veri: 26.11.2026 02:15 TSİ |
| PA2-TUKENIS@1h | 0 | 0 | - | 0 | 0 | - | veri: 26.11.2026 02:15 TSİ |

Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta R1@1d, F1@1d, MF1-YILDIZ@15m, MF1-YILDIZ@1h, MF1-YILDIZ@4h, MF1-YILDIZ@1d, MF1-UCASKER@15m, MF1-UCASKER@1h, MF1-UCASKER@4h, MF1-UCASKER@1d, MF1-DELICI@4h, MF1-DELICI@1d, MF1-ICSAHTE@1d, MF1-DISBAR@1d, MF1-YUTAN@1d, MF1-HARAMI@1d, MF1-TERSCEKIC@1h, MF1-TERSCEKIC@4h, MF1-TERSCEKIC@1d, MF1-CIMBIZ@4h, MF1-CIMBIZ@1d, MF1-PINBAR@4h, MF1-PINBAR@1d, MF1-ICCUBUK@1d, MF1-MARUBOZU@4h, MF1-MARUBOZU@1d, B1-BOLGE@1d, B1-MUM@15m, B1-MUM@1h, B1-MUM@4h, B1-MUM@1d, F1-IKINCI@4h, F1-IKINCI@1d, H2-MINI@1d, H2-YARI@4h, H2-YARI@1d, R1-ALT@1h, R1-ALT@4h, R1-ALT@1d, R1-ERKEN@1h, R1-ERKEN@4h, R1-ERKEN@1d, R1-HA@15m, R1-HA@1h, R1-HA@4h, R1-HA@1d, S1-HACIM@4h, S1-HACIM@1d, S1-OLCULU@1d, T1-GERI3@1d, T1-SEVIYE@1d, TF1-FITIL@1d, TF1-HACIM@1d, GF1-BAYRAK@1d, GF1-FLAMA@4h, GF1-FLAMA@1d, GF1-IKILI@4h, GF1-IKILI@1d, GF1-KAMA@1d, GF1-KANAL@1d, GF1-KUPA@4h, GF1-KUPA@1d, GF1-OBO@1h, GF1-OBO@4h, GF1-OBO@1d, GF1-RETEST@1d, GF1-SAHTE@1d, GF1-TREND@1d, GF1-UCGEN@1d, GF1-UCLU@1d, GF1-YATAY@1d, IN1-BOLL@1d, IN1-BOLLKIR@1d, IN1-FIBO@1d, IN1-FIYATMA@1d, IN1-HACIM@1d, IN1-HIZLIMA@1d, IN1-KUMO@1d, IN1-MACD@1d, IN1-MAGERI@1d, IN1-MAKESISIM@4h, IN1-MAKESISIM@1d, IN1-RSI@1d, IN1-RSI2@1d, IN1-RSIDONUS@1d, IN1-STOK@4h, IN1-STOK@1d, IN1-TK@1d, IN1-UYUMSUZ@4h, IN1-UYUMSUZ@1d, PA2-EMIRBLOK@1h, PA2-EMIRBLOK@4h, PA2-EMIRBLOK@1d, PA2-BOLGE@1d, PA2-FVG@4h, PA2-FVG@1d, PA2-TCIZGI@4h, PA2-TCIZGI@1d, PA2-SEVIYE@4h, PA2-SEVIYE@1d, PA2-UCVURUS@15m, PA2-UCVURUS@1h, PA2-UCVURUS@4h, PA2-UCVURUS@1d, PA2-TUKENIS@1h · yalnız son 12 saatte T1@1d, R1@1h, R1@4h, TF1@1d, B1@1h, B1@1d, H2@4h, H2@1d, S1@1d, F1@1h, F1@4h, M1@4h, M1@1d, MF1-TERSCEKIC@15m, B1-BOLGE@1h, F1-IKINCI@1h, H2-MINI@4h, GF1-FLAMA@1h, IN1-FIBO@1h, PA2-SEVIYE@1h.

Aday = `decision_events` satırı. Golge kararlar (shadow) ve hiç kayda girmeyen sinyaller bu sayıya girmez.

### stop_width skip'leri: dar / geniş (son 12 saat / tüm kayıt)

İzinli bant: stop/ATR 0.5 – 2.0 (signals.STOP_DIST_MIN_ATR / STOP_DIST_MAX_ATR). Yalnız ölçüm; davranış değişmez. Dar/geniş ayrımı kayıtlı `features.stop_dist_atr` değerinin banta göre karşılaştırılmasından türetilir; medyan = reddedilen adayların medyan stop/ATR'si.

| Kol | Son 12s | Tüm kayıt | Veri |
|---|---|---|---|
| T1@15m | dar=0, geniş=9 · medyan 2.46 | dar=0, geniş=335 · medyan 2.73 | veri: 26.11.2026 02:15 TSİ |
| T1@1h | dar=0, geniş=3 · medyan 2.11 | dar=0, geniş=89 · medyan 2.48 | veri: 26.11.2026 02:15 TSİ |
| T1@4h | dar=0, geniş=2 · medyan 2.94 | dar=0, geniş=29 · medyan 2.50 | veri: 26.11.2026 02:15 TSİ |
| T1@1d | - | dar=0, geniş=1 · medyan 3.45 | veri: 26.11.2026 02:15 TSİ |
| R1@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| R1@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| B1@15m | dar=0, geniş=2 · medyan 2.99 | dar=0, geniş=17 · medyan 3.41 | veri: 26.11.2026 02:15 TSİ |
| B1@1h | - | dar=1, geniş=3 · medyan 3.40 | veri: 26.11.2026 02:15 TSİ |
| B1@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| B1@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| H2@15m | dar=0, geniş=4 · medyan 2.84 | dar=0, geniş=43 · medyan 2.92 | veri: 26.11.2026 02:15 TSİ |
| H2@1h | dar=0, geniş=5 · medyan 2.88 | dar=0, geniş=15 · medyan 3.23 | veri: 26.11.2026 02:15 TSİ |
| H2@4h | - | dar=0, geniş=2 · medyan 3.48 | veri: 26.11.2026 02:15 TSİ |
| H2@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| S1@15m | dar=0, geniş=11 · medyan 3.26 | dar=0, geniş=200 · medyan 3.34 | veri: 26.11.2026 02:15 TSİ |
| S1@1h | dar=0, geniş=8 · medyan 3.60 | dar=0, geniş=46 · medyan 3.52 | veri: 26.11.2026 02:15 TSİ |
| S1@4h | dar=0, geniş=4 · medyan 3.16 | dar=0, geniş=16 · medyan 3.38 | veri: 26.11.2026 02:15 TSİ |
| S1@1d | - | dar=0, geniş=3 · medyan 3.48 | veri: 26.11.2026 02:15 TSİ |
| F1@15m | dar=0, geniş=1 · medyan 2.57 | dar=0, geniş=77 · medyan 2.51 | veri: 26.11.2026 02:15 TSİ |
| F1@1h | - | dar=0, geniş=10 · medyan 2.46 | veri: 26.11.2026 02:15 TSİ |
| F1@4h | - | dar=0, geniş=3 · medyan 2.77 | veri: 26.11.2026 02:15 TSİ |
| F1@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| M1@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| M1@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| M1@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| M1@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YILDIZ@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-UCASKER@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@15m | dar=2, geniş=0, ?=12 · medyan 0.83 | dar=2, geniş=0, ?=18 · medyan 0.91 | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@1h | dar=0, geniş=0, ?=1 · medyan 0.91 | dar=0, geniş=0, ?=2 · medyan 1.03 | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@15m | dar=7, geniş=0, ?=18 · medyan 0.66 | dar=10, geniş=0, ?=35 · medyan 0.69 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@1h | dar=1, geniş=0, ?=1 · medyan 0.65 | dar=3, geniş=0, ?=2 · medyan 0.40 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@4h | dar=1, geniş=0 · medyan 0.50 | dar=1, geniş=0 · medyan 0.50 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@15m | dar=0, geniş=1, ?=19 · medyan 1.05 | dar=0, geniş=2, ?=34 · medyan 1.09 | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@1h | dar=0, geniş=0, ?=2 · medyan 0.98 | dar=0, geniş=0, ?=5 · medyan 0.98 | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@15m | dar=15, geniş=3, ?=37 · medyan 0.78 | dar=18, geniş=3, ?=75 · medyan 0.84 | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@1h | dar=2, geniş=0, ?=2 · medyan 0.50 | dar=3, geniş=0, ?=3 · medyan 0.48 | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-YUTAN@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@15m | dar=8, geniş=0, ?=26 · medyan 0.73 | dar=10, geniş=0, ?=50 · medyan 0.74 | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@1h | dar=0, geniş=0, ?=2 · medyan 0.86 | dar=0, geniş=0, ?=4 · medyan 0.70 | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-HARAMI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@15m | - | dar=0, geniş=0, ?=1 · medyan 1.01 | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-TERSCEKIC@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@15m | dar=18, geniş=0, ?=15 · medyan 0.48 | dar=27, geniş=0, ?=25 · medyan 0.49 | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@1h | dar=3, geniş=0, ?=2 · medyan 0.37 | dar=4, geniş=0, ?=3 · medyan 0.50 | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-CIMBIZ@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@15m | dar=7, geniş=0, ?=31 · medyan 0.72 | dar=12, geniş=2, ?=41 · medyan 0.78 | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@1h | dar=1, geniş=0, ?=2 · medyan 0.99 | dar=2, geniş=0, ?=4 · medyan 0.85 | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@15m | dar=4, geniş=4, ?=42 · medyan 1.00 | dar=4, geniş=11, ?=78 · medyan 1.20 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@1h | dar=0, geniş=0, ?=3 · medyan 1.11 | dar=0, geniş=0, ?=9 · medyan 1.11 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@15m | dar=0, geniş=3, ?=1 · medyan 2.23 | dar=0, geniş=4, ?=5 · medyan 1.76 | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| MF1-MARUBOZU@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@15m | dar=1, geniş=1, ?=4 · medyan 0.82 | dar=1, geniş=1, ?=7 · medyan 0.88 | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@4h | dar=0, geniş=0, ?=1 · medyan 0.58 | dar=0, geniş=0, ?=1 · medyan 0.58 | veri: 26.11.2026 02:15 TSİ |
| B1-BOLGE@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| B1-MUM@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@15m | dar=0, geniş=0, ?=9 · medyan 0.72 | dar=0, geniş=0, ?=10 · medyan 0.75 | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@1h | - | dar=0, geniş=0, ?=1 · medyan 0.90 | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| F1-IKINCI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@15m | dar=1, geniş=0, ?=21 · medyan 0.84 | dar=1, geniş=1, ?=44 · medyan 0.95 | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@1h | dar=1, geniş=0, ?=1 · medyan 0.76 | dar=1, geniş=0, ?=3 · medyan 0.72 | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| H2-MINI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@15m | dar=0, geniş=0, ?=3 · medyan 1.03 | dar=0, geniş=2, ?=9 · medyan 1.41 | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@1h | - | dar=0, geniş=0, ?=1 · medyan 1.39 | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| H2-YARI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@15m | - | dar=0, geniş=0, ?=2 · medyan 0.81 | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ALT@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@15m | - | dar=0, geniş=0, ?=2 · medyan 0.81 | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-ERKEN@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| R1-HA@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@15m | dar=0, geniş=1 · medyan 2.57 | dar=0, geniş=1 · medyan 2.57 | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-HACIM@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@15m | dar=0, geniş=3, ?=1 · medyan 2.27 | dar=0, geniş=9, ?=2 · medyan 2.42 | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| S1-OLCULU@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@15m | dar=1, geniş=1, ?=34 · medyan 0.88 | dar=1, geniş=2, ?=55 · medyan 1.01 | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@1h | dar=1, geniş=0, ?=3 · medyan 1.16 | dar=1, geniş=0, ?=5 · medyan 1.16 | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| T1-GERI3@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@15m | dar=1, geniş=0, ?=6 · medyan 0.86 | dar=1, geniş=3, ?=19 · medyan 1.08 | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@1h | dar=0, geniş=0, ?=3 · medyan 0.65 | dar=0, geniş=0, ?=4 · medyan 0.67 | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@4h | dar=0, geniş=0, ?=1 · medyan 0.58 | dar=0, geniş=0, ?=1 · medyan 0.58 | veri: 26.11.2026 02:15 TSİ |
| T1-SEVIYE@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@15m | dar=0, geniş=0, ?=1 · medyan 1.28 | dar=0, geniş=0, ?=7 · medyan 1.34 | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-FITIL@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@15m | dar=0, geniş=0, ?=1 · medyan 1.28 | dar=0, geniş=0, ?=1 · medyan 1.28 | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| TF1-HACIM@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@15m | dar=0, geniş=4, ?=16 · medyan 1.54 | dar=0, geniş=9, ?=29 · medyan 1.54 | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@1h | dar=0, geniş=0, ?=1 · medyan 1.11 | dar=0, geniş=0, ?=2 · medyan 1.21 | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-BAYRAK@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@15m | - | dar=0, geniş=1 · medyan 2.25 | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-FLAMA@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@15m | dar=0, geniş=2 · medyan 2.23 | dar=0, geniş=6 · medyan 2.86 | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-IKILI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@15m | dar=0, geniş=1, ?=1 · medyan 2.40 | dar=0, geniş=5, ?=1 · medyan 2.47 | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KAMA@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@15m | dar=19, geniş=0, ?=71 · medyan 0.75 | dar=30, geniş=0, ?=114 · medyan 0.78 | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@1h | dar=1, geniş=0, ?=3 · medyan 0.60 | dar=2, geniş=0, ?=6 · medyan 0.60 | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@4h | - | dar=1, geniş=0 · medyan 0.45 | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@15m | dar=0, geniş=0, ?=2 · medyan 1.72 | dar=0, geniş=0, ?=2 · medyan 1.72 | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-KUPA@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-OBO@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@15m | dar=9, geniş=1, ?=19 · medyan 0.61 | dar=12, geniş=3, ?=38 · medyan 0.67 | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@1h | dar=3, geniş=0 · medyan 0.44 | dar=3, geniş=0, ?=2 · medyan 0.48 | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-RETEST@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@15m | dar=1, geniş=0, ?=23 · medyan 0.95 | dar=1, geniş=1, ?=35 · medyan 0.95 | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@1h | - | dar=0, geniş=0, ?=2 · medyan 1.04 | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-SAHTE@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@15m | dar=0, geniş=1 · medyan 2.71 | dar=0, geniş=3 · medyan 3.12 | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-TREND@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@15m | dar=0, geniş=1 · medyan 3.29 | dar=0, geniş=1 · medyan 3.29 | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCGEN@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@15m | - | dar=0, geniş=1 · medyan 5.22 | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-UCLU@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@15m | dar=7, geniş=3, ?=35 · medyan 0.84 | dar=11, geniş=4, ?=62 · medyan 0.84 | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@1h | dar=3, geniş=0, ?=3 · medyan 0.60 | dar=4, geniş=0, ?=6 · medyan 0.58 | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| GF1-YATAY@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@15m | dar=244, geniş=3, ?=140 · medyan 0.40 | dar=399, geniş=6, ?=275 · medyan 0.43 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@1h | dar=102, geniş=0, ?=36 · medyan 0.35 | dar=136, geniş=0, ?=50 · medyan 0.36 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@4h | dar=14, geniş=0 · medyan 0.21 | dar=22, geniş=0 · medyan 0.25 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@15m | dar=0, geniş=7, ?=6 · medyan 2.04 | dar=0, geniş=22, ?=22 · medyan 2.02 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@1h | dar=0, geniş=0, ?=3 · medyan 1.14 | dar=0, geniş=0, ?=5 · medyan 1.18 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLLKIR@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@15m | - | dar=0, geniş=2 · medyan 2.89 | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIBO@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@15m | dar=0, geniş=15, ?=15 · medyan 2.00 | dar=0, geniş=23, ?=25 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@1h | - | dar=0, geniş=0, ?=1 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-FIYATMA@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@15m | dar=1, geniş=3, ?=17 · medyan 0.94 | dar=3, geniş=5, ?=33 · medyan 1.12 | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@1h | dar=1, geniş=0 · medyan 0.39 | dar=1, geniş=0 · medyan 0.39 | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HACIM@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@15m | dar=0, geniş=10, ?=16 · medyan 2.00 | dar=0, geniş=30, ?=32 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@1h | - | dar=0, geniş=0, ?=1 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-HIZLIMA@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@15m | dar=8, geniş=2, ?=16 · medyan 0.88 | dar=13, geniş=5, ?=30 · medyan 0.71 | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@1h | dar=2, geniş=0 · medyan 0.14 | dar=5, geniş=0 · medyan 0.20 | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-KUMO@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@15m | dar=0, geniş=9, ?=15 · medyan 2.00 | dar=0, geniş=31, ?=26 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@1h | - | dar=0, geniş=0, ?=2 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@15m | dar=0, geniş=0, ?=5 · medyan 0.97 | dar=1, geniş=0, ?=7 · medyan 0.95 | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAGERI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@15m | dar=0, geniş=1 · medyan 2.00 | dar=0, geniş=1, ?=1 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@15m | dar=21, geniş=0, ?=8 · medyan 0.35 | dar=24, geniş=0, ?=9 · medyan 0.35 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@1h | dar=3, geniş=0, ?=2 · medyan 0.36 | dar=4, geniş=0, ?=2 · medyan 0.40 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@15m | dar=0, geniş=28, ?=23 · medyan 2.00 | dar=0, geniş=44, ?=41 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@1h | dar=0, geniş=1 · medyan 2.00 | dar=0, geniş=2, ?=2 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@15m | dar=6, geniş=2, ?=23 · medyan 0.90 | dar=8, geniş=3, ?=42 · medyan 0.95 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@1h | dar=1, geniş=0 · medyan 0.32 | dar=1, geniş=0, ?=4 · medyan 1.10 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-RSIDONUS@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@15m | dar=0, geniş=0, ?=3 · medyan 0.77 | dar=0, geniş=0, ?=4 · medyan 0.82 | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@1h | - | dar=0, geniş=0, ?=1 · medyan 0.51 | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@15m | dar=3, geniş=1, ?=11 · medyan 0.91 | dar=6, geniş=3, ?=26 · medyan 0.99 | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-TK@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@15m | dar=0, geniş=0, ?=4 · medyan 0.90 | dar=0, geniş=1, ?=7 · medyan 1.24 | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-UYUMSUZ@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| IN1-VWAP@15m | dar=0, geniş=10, ?=13 · medyan 2.00 | dar=0, geniş=33, ?=29 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| IN1-VWAP@1h | - | dar=0, geniş=0, ?=1 · medyan 2.00 | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-EMIRBLOK@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@15m | dar=0, geniş=0, ?=2 · medyan 1.34 | dar=0, geniş=1, ?=4 · medyan 1.25 | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@15m | dar=0, geniş=2, ?=3 · medyan 1.36 | dar=0, geniş=4, ?=7 · medyan 1.52 | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-ONCEKI@15m | dar=0, geniş=0, ?=3 · medyan 1.00 | dar=0, geniş=0, ?=5 · medyan 1.00 | veri: 26.11.2026 02:15 TSİ |
| PA2-ONCEKI@1h | dar=0, geniş=0, ?=1 · medyan 0.54 | dar=1, geniş=0, ?=3 · medyan 0.76 | veri: 26.11.2026 02:15 TSİ |
| PA2-ONCEKI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@15m | dar=0, geniş=0, ?=4 · medyan 1.00 | dar=0, geniş=0, ?=15 · medyan 1.00 | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@1h | - | dar=0, geniş=0, ?=1 · medyan 1.00 | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-TCIZGI@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@15m | dar=3, geniş=0, ?=2 · medyan 0.49 | dar=3, geniş=0, ?=6 · medyan 0.61 | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-SEVIYE@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@15m | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@1h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@4h | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-UCVURUS@1d | - | - | veri: 26.11.2026 02:15 TSİ |
| PA2-TUKENIS@15m | dar=0, geniş=0, ?=1 · medyan 0.78 | dar=0, geniş=0, ?=1 · medyan 0.78 | veri: 26.11.2026 02:15 TSİ |
| PA2-TUKENIS@1h | - | - | veri: 26.11.2026 02:15 TSİ |

## ML 10 — Kol bazında sanal K/Z

| Kol | İşlem | Net $ | R toplamı | Kazanma | Durum | Veri |
|---|---|---|---|---|---|---|
| F1@15m | 17 | -$45,63 | -6,68 R | %23,5 | ZARARDA | veri: 25.11.2026 20:42 TSİ |
| S1@15m | 8 | -$36,18 | -3,29 R | %25,0 | ZARARDA | veri: 23.11.2026 17:15 TSİ |
| IN1-RSI2@15m | 7 | -$16,41 | -3,49 R | %14,3 | ZARARDA | veri: 26.11.2026 02:15 TSİ |
| S1@4h | 2 | -$15,94 | -2,10 R | %0,0 | ZARARDA | veri: 25.11.2026 21:45 TSİ |
| T1@1h | 10 | -$15,27 | +0,44 R | %50,0 | ZARARDA | veri: 23.11.2026 03:57 TSİ |
| M1@1h | 6 | -$14,33 | -0,94 R | %50,0 | ZARARDA | veri: 25.11.2026 21:00 TSİ |
| H2@1h | 1 | -$11,73 | -1,00 R | %0,0 | ZARARDA | veri: 21.11.2026 16:39 TSİ |
| H2@4h | 1 | -$10,70 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:57 TSİ |
| B1@1d | 1 | -$10,54 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:58 TSİ |
| IN1-RSI2@1h | 1 | -$10,02 | -1,05 R | %0,0 | ZARARDA | veri: 25.11.2026 16:54 TSİ |
| PA2-BOLGE@15m | 1 | -$9,18 | -0,98 R | %0,0 | ZARARDA | veri: 25.11.2026 19:21 TSİ |
| M1@15m | 13 | -$8,89 | -3,26 R | %46,2 | ZARARDA | veri: 25.11.2026 10:30 TSİ |
| TF1@15m | 8 | -$4,87 | -1,27 R | %50,0 | ZARARDA | veri: 25.11.2026 17:59 TSİ |
| IN1-BOLL@1h | 1 | -$4,85 | -1,06 R | %0,0 | ZARARDA | veri: 25.11.2026 22:17 TSİ |
| H2@15m | 9 | +$0,71 | -0,37 R | %44,4 | kârda/başa baş | veri: 25.11.2026 18:00 TSİ |
| B1@15m | 1 | +$3,39 | +0,73 R | %100,0 | kârda/başa baş | veri: 19.11.2026 20:15 TSİ |
| GF1-UCLU@15m | 1 | +$7,26 | +0,76 R | %100,0 | kârda/başa baş | veri: 25.11.2026 23:15 TSİ |
| M1@4h | 2 | +$9,87 | +0,96 R | %50,0 | kârda/başa baş | veri: 23.11.2026 16:55 TSİ |
| B1@1h | 2 | +$13,14 | +1,35 R | %50,0 | kârda/başa baş | veri: 21.11.2026 14:31 TSİ |
| S1@1h | 4 | +$19,20 | +2,58 R | %75,0 | kârda/başa baş | veri: 25.11.2026 20:35 TSİ |
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
| IN1-BOLL@15m | 0 | - | - | - | - | veri: işlem yok |
| IN1-BOLL@1d | 0 | - | - | - | - | veri: işlem yok |
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
| IN1-RSI2@1d | 0 | - | - | - | - | veri: işlem yok |
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
| Ders: kol kapatma (arms_off) | var | yalnız karne/rapor bilgisi; giriş ENGELLENMEZ (sahip kararı, 19 Kasım; gates.py `arm_would_close` sayacı) | tetiklendi: B1@15m, B1@1d, F1@15m, F1@1h, GF1-KANAL@15m, GF1-RETEST@15m, GF1-SAHTE@15m, H2@1h, H2@4h, IN1-BOLLKIR@15m, IN1-FIYATMA@15m, M1@15m, M1@1h, MF1-CIMBIZ@15m, MF1-DELICI@15m, MF1-DISBAR@15m, MF1-HARAMI@15m, MF1-ICSAHTE@15m, MF1-YUTAN@15m, PA2-TCIZGI@15m, R1@15m, R1@1h, S1@15m, S1@1h | okuma: 26.11.2026 02:21 TSİ |
| Ders: 10 R freni (lesson_brake) | var | ders ayarlarını referansa döndürür, otomatik uygulamayı durdurur; kolu kapatmaz | tetiklenmedi | okuma: 26.11.2026 02:21 TSİ |
| Kol başına açık pozisyon tavanı (arm_max_positions) ve küme/hesap tavanı | var | kayıptan bağımsız konum sınırı; zarardaki kolu özel olarak ayırmaz | kayıp temelli tetik değil | okuma: 26.11.2026 02:21 TSİ |
| Risk kademe denetimi (risk_ladder, hesap düzeyi küçültme) | var (hesap düzeyi; kol düzeyi değil) | tepe-denge düşüşünde hedef işlem riskini kademeli düşürür / durdurur; motor zorunlu yalnız canlı modda | kâğıt ayarında LADDER_BOTS boş; kâğıtta kademe izlenmez | okuma: 26.11.2026 02:21 TSİ |
| Kol bazında otomatik karantina / boyut küçültme | yok | zararda kol: F1@15m, S1@15m, IN1-RSI2@15m, S1@4h, T1@1h, M1@1h, H2@1h, H2@4h, B1@1d, IN1-RSI2@1h, PA2-BOLGE@15m, M1@15m, TF1@15m, IN1-BOLL@1h; bu kolları kendiliğinden kısan kural yok | - | okuma: 26.11.2026 02:21 TSİ |

## ML 11 — Long/short dağılımı

| Yön | İşlem | Net $ | Kazanma | R | Veri |
|---|---|---|---|---|---|
| long | 15 | -$25,05 | %40,0 | -2,37 R | veri: 25.11.2026 23:15 TSİ |
| short | 91 | -$52,24 | %39,6 | -10,18 R | veri: 26.11.2026 02:15 TSİ |

| Rejim | Long (n / net $ / kazanma) | Short (n / net $ / kazanma) | Veri |
|---|---|---|---|
| trend_up | 8 / -$21,80 / %37,5 | 0 / - / - | veri: 25.11.2026 16:54 TSİ |
| trend_down | 1 / +$4,86 / %100,0 | 87 / -$47,92 / %39,1 | veri: 26.11.2026 02:15 TSİ |
| range | 2 / -$19,65 / %0,0 | 1 / -$7,33 / %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 4 / +$11,53 / %50,0 | 3 / +$3,00 / %66,7 | veri: 25.11.2026 23:15 TSİ |
| volatile | 0 / - / - | 0 / - / - | veri: işlem yok |

Güncel rejim (son karar zamanından geriye 24 saatte en sık rejim; 6785 karar): trend_down (veri: 26.11.2026 02:15 TSİ)
Long-yetkin kollar (kayıtta ≥1 long adayı olanlar) bu rejimde: aday 2339 · alınan 1

| Kol | Long aday (güncel rejim) | Alınan (güncel rejim) | Long aday (tüm kayıt) | Alınan (tüm kayıt) | Veri |
|---|---|---|---|---|---|
| T1@15m | 0 | 0 | 32 | 0 | veri: 25.11.2026 17:30 TSİ |
| T1@1h | 0 | 0 | 10 | 1 | veri: 25.11.2026 16:00 TSİ |
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
| B1@4h | 0 | 0 | 1 | 0 | veri: 25.11.2026 23:00 TSİ |
| H2@15m | 0 | 0 | 15 | 0 | veri: 26.11.2026 01:45 TSİ |
| H2@1h | 0 | 0 | 4 | 0 | veri: 25.11.2026 08:00 TSİ |
| H2@4h | 0 | 0 | 1 | 0 | veri: 21.11.2026 23:00 TSİ |
| S1@15m | 0 | 0 | 49 | 3 | veri: 25.11.2026 23:45 TSİ |
| S1@1h | 0 | 0 | 8 | 0 | veri: 25.11.2026 21:00 TSİ |
| S1@4h | 0 | 0 | 4 | 0 | veri: 25.11.2026 11:00 TSİ |
| F1@15m | 0 | 0 | 68 | 7 | veri: 25.11.2026 21:30 TSİ |
| F1@1h | 0 | 0 | 18 | 0 | veri: 24.11.2026 15:00 TSİ |
| F1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 03:00 TSİ |
| M1@1h | 107 | 1 | 110 | 1 | veri: 23.11.2026 04:00 TSİ |
| M1@15m | 37 | 0 | 38 | 0 | veri: 24.11.2026 18:00 TSİ |
| MF1-DELICI@15m | 11 | 0 | 13 | 0 | veri: 26.11.2026 02:15 TSİ |
| MF1-DELICI@1h | 13 | 0 | 14 | 0 | veri: 25.11.2026 20:00 TSİ |
| MF1-ICSAHTE@15m | 19 | 0 | 28 | 0 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICSAHTE@1h | 7 | 0 | 8 | 0 | veri: 26.11.2026 02:00 TSİ |
| MF1-ICSAHTE@4h | 1 | 0 | 1 | 0 | veri: 25.11.2026 19:00 TSİ |
| MF1-DISBAR@15m | 41 | 0 | 50 | 0 | veri: 26.11.2026 02:15 TSİ |
| MF1-DISBAR@1h | 8 | 0 | 9 | 0 | veri: 25.11.2026 18:00 TSİ |
| MF1-DISBAR@4h | 2 | 0 | 2 | 0 | veri: 25.11.2026 23:00 TSİ |
| MF1-YUTAN@15m | 75 | 0 | 93 | 0 | veri: 26.11.2026 02:00 TSİ |
| MF1-YUTAN@1h | 5 | 0 | 8 | 0 | veri: 25.11.2026 23:00 TSİ |
| MF1-YUTAN@4h | 16 | 0 | 17 | 0 | veri: 25.11.2026 23:00 TSİ |
| MF1-HARAMI@15m | 15 | 0 | 30 | 0 | veri: 26.11.2026 01:30 TSİ |
| MF1-HARAMI@1h | 5 | 0 | 7 | 0 | veri: 25.11.2026 19:00 TSİ |
| MF1-TERSCEKIC@15m | 1 | 0 | 1 | 0 | veri: 25.11.2026 12:45 TSİ |
| MF1-CIMBIZ@15m | 26 | 0 | 35 | 0 | veri: 26.11.2026 02:00 TSİ |
| MF1-CIMBIZ@1h | 11 | 0 | 11 | 0 | veri: 25.11.2026 20:00 TSİ |
| MF1-PINBAR@15m | 21 | 0 | 26 | 0 | veri: 26.11.2026 02:15 TSİ |
| MF1-PINBAR@1h | 8 | 0 | 10 | 0 | veri: 25.11.2026 18:00 TSİ |
| MF1-ICCUBUK@15m | 50 | 0 | 79 | 0 | veri: 26.11.2026 02:15 TSİ |
| MF1-ICCUBUK@1h | 20 | 0 | 29 | 0 | veri: 26.11.2026 02:00 TSİ |
| MF1-ICCUBUK@4h | 2 | 0 | 5 | 0 | veri: 25.11.2026 23:00 TSİ |
| MF1-MARUBOZU@15m | 18 | 0 | 22 | 0 | veri: 25.11.2026 21:30 TSİ |
| MF1-MARUBOZU@1h | 3 | 0 | 3 | 0 | veri: 25.11.2026 21:00 TSİ |
| B1-BOLGE@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 11:15 TSİ |
| B1-BOLGE@4h | 0 | 0 | 1 | 0 | veri: 25.11.2026 23:00 TSİ |
| F1-IKINCI@15m | 0 | 0 | 3 | 0 | veri: 25.11.2026 17:00 TSİ |
| H2-MINI@15m | 0 | 0 | 11 | 0 | veri: 26.11.2026 02:00 TSİ |
| H2-MINI@1h | 0 | 0 | 4 | 0 | veri: 26.11.2026 02:00 TSİ |
| H2-YARI@15m | 0 | 0 | 3 | 0 | veri: 26.11.2026 01:45 TSİ |
| H2-YARI@1h | 0 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| R1-ALT@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 08:45 TSİ |
| R1-ERKEN@15m | 0 | 0 | 2 | 0 | veri: 25.11.2026 08:45 TSİ |
| S1-HACIM@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 17:00 TSİ |
| S1-OLCULU@15m | 0 | 0 | 4 | 0 | veri: 25.11.2026 23:45 TSİ |
| S1-OLCULU@1h | 0 | 0 | 3 | 0 | veri: 25.11.2026 21:00 TSİ |
| T1-GERI3@15m | 0 | 0 | 13 | 0 | veri: 26.11.2026 02:00 TSİ |
| T1-GERI3@1h | 0 | 0 | 4 | 0 | veri: 26.11.2026 02:00 TSİ |
| T1-SEVIYE@15m | 0 | 0 | 4 | 0 | veri: 25.11.2026 12:15 TSİ |
| T1-SEVIYE@1h | 0 | 0 | 1 | 0 | veri: 26.11.2026 00:00 TSİ |
| T1-SEVIYE@4h | 0 | 0 | 1 | 0 | veri: 25.11.2026 23:00 TSİ |
| TF1-FITIL@15m | 0 | 0 | 1 | 0 | veri: 25.11.2026 08:00 TSİ |
| GF1-BAYRAK@15m | 63 | 0 | 80 | 0 | veri: 26.11.2026 00:00 TSİ |
| GF1-BAYRAK@1h | 1 | 0 | 3 | 0 | veri: 26.11.2026 00:00 TSİ |
| GF1-BAYRAK@4h | 0 | 0 | 1 | 0 | veri: 25.11.2026 11:00 TSİ |
| GF1-IKILI@15m | 21 | 0 | 25 | 0 | veri: 25.11.2026 22:00 TSİ |
| GF1-IKILI@1h | 10 | 0 | 13 | 0 | veri: 25.11.2026 22:00 TSİ |
| GF1-KAMA@15m | 6 | 0 | 8 | 0 | veri: 25.11.2026 20:30 TSİ |
| GF1-KAMA@1h | 0 | 0 | 1 | 0 | veri: 25.11.2026 21:00 TSİ |
| GF1-KANAL@15m | 98 | 0 | 119 | 0 | veri: 26.11.2026 02:15 TSİ |
| GF1-KANAL@1h | 8 | 0 | 8 | 0 | veri: 25.11.2026 20:00 TSİ |
| GF1-KUPA@15m | 2 | 0 | 2 | 0 | veri: 25.11.2026 22:15 TSİ |
| GF1-RETEST@15m | 16 | 0 | 24 | 0 | veri: 26.11.2026 01:00 TSİ |
| GF1-RETEST@1h | 3 | 0 | 5 | 0 | veri: 26.11.2026 00:00 TSİ |
| GF1-RETEST@4h | 0 | 0 | 1 | 0 | veri: 25.11.2026 23:00 TSİ |
| GF1-SAHTE@15m | 41 | 0 | 53 | 0 | veri: 25.11.2026 21:30 TSİ |
| GF1-SAHTE@1h | 8 | 0 | 10 | 0 | veri: 25.11.2026 21:00 TSİ |
| GF1-SAHTE@4h | 1 | 0 | 2 | 0 | veri: 25.11.2026 23:00 TSİ |
| GF1-TREND@15m | 28 | 0 | 32 | 0 | veri: 26.11.2026 00:00 TSİ |
| GF1-TREND@1h | 3 | 0 | 3 | 0 | veri: 25.11.2026 22:00 TSİ |
| GF1-TREND@4h | 3 | 0 | 3 | 0 | veri: 25.11.2026 23:00 TSİ |
| GF1-UCGEN@1h | 3 | 0 | 4 | 0 | veri: 25.11.2026 17:00 TSİ |
| GF1-UCLU@15m | 24 | 0 | 31 | 1 | veri: 25.11.2026 22:30 TSİ |
| GF1-UCLU@1h | 8 | 0 | 10 | 1 | veri: 25.11.2026 23:00 TSİ |
| GF1-UCLU@4h | 1 | 0 | 1 | 0 | veri: 25.11.2026 23:00 TSİ |
| GF1-YATAY@15m | 32 | 0 | 45 | 0 | veri: 26.11.2026 02:00 TSİ |
| GF1-YATAY@1h | 4 | 0 | 8 | 0 | veri: 25.11.2026 23:00 TSİ |
| GF1-YATAY@4h | 1 | 0 | 1 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-BOLL@15m | 385 | 0 | 490 | 0 | veri: 26.11.2026 02:15 TSİ |
| IN1-BOLL@1h | 178 | 0 | 202 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-BOLL@4h | 42 | 0 | 45 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-BOLLKIR@15m | 33 | 0 | 55 | 0 | veri: 25.11.2026 22:30 TSİ |
| IN1-BOLLKIR@1h | 17 | 0 | 22 | 0 | veri: 26.11.2026 00:00 TSİ |
| IN1-BOLLKIR@4h | 2 | 0 | 4 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-FIBO@15m | 3 | 0 | 4 | 0 | veri: 25.11.2026 14:00 TSİ |
| IN1-FIBO@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 09:00 TSİ |
| IN1-FIYATMA@15m | 59 | 0 | 76 | 0 | veri: 26.11.2026 01:45 TSİ |
| IN1-FIYATMA@1h | 20 | 0 | 26 | 0 | veri: 26.11.2026 02:00 TSİ |
| IN1-FIYATMA@4h | 8 | 0 | 8 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-HACIM@15m | 8 | 0 | 14 | 0 | veri: 25.11.2026 22:00 TSİ |
| IN1-HACIM@1h | 9 | 0 | 9 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-HACIM@4h | 1 | 0 | 1 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-HIZLIMA@15m | 88 | 0 | 112 | 0 | veri: 26.11.2026 02:00 TSİ |
| IN1-HIZLIMA@1h | 30 | 0 | 33 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-HIZLIMA@4h | 8 | 0 | 8 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-KUMO@15m | 36 | 0 | 51 | 0 | veri: 26.11.2026 01:45 TSİ |
| IN1-KUMO@1h | 6 | 0 | 6 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-KUMO@4h | 2 | 0 | 2 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-MACD@15m | 76 | 0 | 99 | 0 | veri: 26.11.2026 02:15 TSİ |
| IN1-MACD@1h | 37 | 0 | 45 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-MACD@4h | 5 | 0 | 5 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-MAGERI@15m | 4 | 0 | 5 | 0 | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@15m | 5 | 0 | 6 | 0 | veri: 26.11.2026 02:15 TSİ |
| IN1-MAKESISIM@1h | 3 | 0 | 4 | 0 | veri: 26.11.2026 02:00 TSİ |
| IN1-RSI@15m | 7 | 0 | 9 | 0 | veri: 25.11.2026 17:45 TSİ |
| IN1-RSI@1h | 4 | 0 | 6 | 0 | veri: 25.11.2026 22:00 TSİ |
| IN1-RSI@4h | 1 | 0 | 1 | 0 | veri: 25.11.2026 15:00 TSİ |
| IN1-RSI2@15m | 48 | 0 | 118 | 0 | veri: 26.11.2026 02:15 TSİ |
| IN1-RSI2@1h | 9 | 0 | 26 | 2 | veri: 25.11.2026 18:00 TSİ |
| IN1-RSI2@4h | 0 | 0 | 1 | 0 | veri: 25.11.2026 15:00 TSİ |
| IN1-RSIDONUS@15m | 72 | 0 | 79 | 0 | veri: 25.11.2026 20:00 TSİ |
| IN1-RSIDONUS@1h | 21 | 0 | 21 | 0 | veri: 25.11.2026 21:00 TSİ |
| IN1-RSIDONUS@4h | 2 | 0 | 3 | 0 | veri: 25.11.2026 23:00 TSİ |
| IN1-STOK@15m | 1 | 0 | 2 | 0 | veri: 26.11.2026 02:15 TSİ |
| IN1-STOK@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 12:00 TSİ |
| IN1-TK@15m | 10 | 0 | 19 | 0 | veri: 25.11.2026 21:45 TSİ |
| IN1-UYUMSUZ@15m | 11 | 0 | 11 | 0 | veri: 25.11.2026 20:30 TSİ |
| IN1-UYUMSUZ@1h | 7 | 0 | 9 | 0 | veri: 25.11.2026 22:00 TSİ |
| IN1-VWAP@15m | 77 | 0 | 103 | 0 | veri: 26.11.2026 01:45 TSİ |
| IN1-VWAP@1h | 44 | 0 | 50 | 0 | veri: 25.11.2026 22:00 TSİ |
| PA2-BOLGE@15m | 3 | 0 | 4 | 0 | veri: 26.11.2026 02:15 TSİ |
| PA2-BOLGE@4h | 1 | 0 | 1 | 0 | veri: 25.11.2026 19:00 TSİ |
| PA2-FVG@15m | 15 | 0 | 21 | 0 | veri: 26.11.2026 02:15 TSİ |
| PA2-FVG@1h | 1 | 0 | 2 | 0 | veri: 26.11.2026 00:00 TSİ |
| PA2-ONCEKI@15m | 8 | 0 | 9 | 0 | veri: 25.11.2026 18:00 TSİ |
| PA2-ONCEKI@1h | 8 | 0 | 8 | 0 | veri: 25.11.2026 20:00 TSİ |
| PA2-ONCEKI@4h | 3 | 0 | 3 | 0 | veri: 25.11.2026 23:00 TSİ |
| PA2-TCIZGI@15m | 5 | 0 | 7 | 0 | veri: 25.11.2026 18:00 TSİ |
| PA2-TCIZGI@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 12:00 TSİ |
| PA2-SEVIYE@15m | 5 | 0 | 5 | 0 | veri: 25.11.2026 19:15 TSİ |
| PA2-SEVIYE@1h | 1 | 0 | 1 | 0 | veri: 25.11.2026 10:00 TSİ |

## ML 12 — Kâğıt / geri test tutarlılığı

Toplam kâğıt R (n=106): -12,56 R (veri: 26.11.2026 02:15 TSİ). Yayımlanmış bant (n=106 için aradeğer): %2,5=-38,1 · %10=-25,5 · ortanca=+4,5 · %90=+45,3. Konum: %10-%90 arası (bant içinde). Kaynak: docs/kagit-degerlendirme-plani.md §4.4 (kümülatif net R, referans bootstrap bandı).

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
