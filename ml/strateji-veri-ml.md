# [ML] Strateji verisi (beyin fırtınası için)

Üretim: 23.11.2026 15:20 TSİ · Kâğıt başlangıcı (ilk kayıt): 17.11.2026 18:00 TSİ · Veri kesiti: 23.11.2026 15:15 TSİ
Kapanan işlem: 49 · Açık işlem: 9 · Karar kaydı: 3012 · Yapılandırılmış kol: 32
Kapsam: yalnız kâğıt defteri (salt okunur). Kilitli dönem (01.05.2026-01.11.2026) kayıtları okunmadı/ayıklandı (ayıklanan kayıt: 0). Yeni geri test hesaplanmadı. Yorum/öneri yok.

## Ortak 1 — Kâğıt başlangıcından beri sonuç

| Ölçü | Değer | Veri |
|---|---|---|
| Net K/Z | +$21,97 | veri: 23.11.2026 13:41 TSİ |
| İşlem sayısı (kapanan) | 49 | veri: 23.11.2026 13:41 TSİ |
| Kazanma oranı (net > 0) | %44,9 | veri: 23.11.2026 13:41 TSİ |
| Ort. kazanç | +1,28 R / +$11,45 | veri: 23.11.2026 13:41 TSİ |
| Ort. kayıp | -0,97 R / -$8,51 | veri: 23.11.2026 13:41 TSİ |
| Toplam R | +2,04 R | veri: 23.11.2026 13:41 TSİ |

## Ortak 2 — K/Z yoğunlaşması

| Ölçü | Değer | Veri |
|---|---|---|
| En iyi 1 işlemin net içindeki payı | %189,0 (+$41,53) | veri: 23.11.2026 13:41 TSİ |
| En iyi 2 işlemin net içindeki payı | %334,8 (+$73,56) | veri: 23.11.2026 13:41 TSİ |
| En iyi 3 çıkarılınca net | -$76,68 | veri: 23.11.2026 13:41 TSİ |
| En kötü 3 çıkarılınca net | +$60,90 | veri: 23.11.2026 13:41 TSİ |
| En iyi 3 + en kötü 3 çıkarılınca net | -$37,75 | veri: 23.11.2026 13:41 TSİ |

Pay: net > 0 iken hesaplanır; yetersiz işlemde (en iyi/kötü 3 için < 4, ikisi birden < 7) '-'.

## Ortak 3 — Maliyetler

| Kalem | Tutar | Brüt kâra oranı | Veri |
|---|---|---|---|
| Brüt kâr (yalnız brüt > 0 olan işlemlerin toplamı) | $269,74 | - | veri: 23.11.2026 13:41 TSİ |
| Toplam brüt K/Z (tüm işlemler) | +$58,55 | - | veri: 23.11.2026 13:41 TSİ |
| Komisyon | $37,85 | %14,0 | veri: 23.11.2026 13:41 TSİ |
| Fonlama (ödenen) | -$1,27 | %0,5 | veri: 23.11.2026 13:41 TSİ |
| Komisyon + fonlama | $36,58 | %13,6 | veri: 23.11.2026 13:41 TSİ |
| Kayma (giriş+çıkış, planlanana göre; brüte ZATEN işlenmiştir) | +$60,65 | %22,5 | veri: 23.11.2026 13:41 TSİ |
| Komisyon + fonlama + kayma | $97,23 | %36,0 | veri: 23.11.2026 13:41 TSİ |

Net K/Z = brüt - komisyon - fonlama (kayma fiyatlara işlendiğinden ayrıca düşülmez).

## Ortak 6 — Girişteki piyasa rejimine göre sonuç

| Rejim | İşlem | Net K/Z | Kazanma | Veri |
|---|---|---|---|---|
| trend_up | 2 | -$8,50 | %50,0 | veri: 22.11.2026 13:30 TSİ |
| trend_down | 43 | +$49,26 | %46,5 | veri: 23.11.2026 13:41 TSİ |
| range | 3 | -$26,98 | %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 1 | +$8,20 | %100,0 | veri: 20.11.2026 05:45 TSİ |
| volatile | 0 | - | - | veri: işlem yok |

## Ortak 7 — 30 / 100 / 300 kapanan işleme ulaşma süresi

Süre: 5,9 gün (17.11.2026 18:00 TSİ → 23.11.2026 15:15 TSİ); kapanan 49; genel hız 8,33 işlem/gün; kol medyan hızı: işlemi olan 13 kol 0,510 işlem/gün, tüm 32 yapılandırılmış kol 0,000 işlem/gün (veri: 23.11.2026 15:15 TSİ).

| Hedef | Genel (güncel hızla) | Kol medyanı (işlemi olan kollar) | Kol medyanı (tüm kollar) | Hedefe ulaşan kol | Veri |
|---|---|---|---|---|---|
| 30 | ulaşıldı | 59 gün (8,4 hafta) | hesaplanamaz (hız 0) | 0 | veri: 23.11.2026 15:15 TSİ |
| 100 | 6 gün (0,9 hafta) | 196 gün (28,0 hafta) | hesaplanamaz (hız 0) | 0 | veri: 23.11.2026 15:15 TSİ |
| 300 | 30 gün (4,3 hafta) | 589 gün (84,1 hafta) | hesaplanamaz (hız 0) | 0 | veri: 23.11.2026 15:15 TSİ |

## ML 8 — Yapılandırılmış kollar: işlem açan / açmayan

Yapılandırılmış kol: 32 · ≥1 işlem açan: 18 · hiç açmayan: 14 (veri: 23.11.2026 15:15 TSİ)

| Kol | Aday (karar kaydı) | En sık skip_reason | Grup (filtre/rejim/veri/eşik/risk-limit) | Veri |
|---|---|---|---|---|
| T1@4h | 7 | stop_width=5, risk_denied=2 | eşik=5, risk/limit=2 | veri: 23.11.2026 15:00 TSİ |
| T1@1d | 1 | stop_width=1 | eşik=1 | veri: 20.11.2026 03:00 TSİ |
| R1@15m | 31 | risk_denied=28, etiket_duygu=3 | risk/limit=28, filtre=3 | veri: 20.11.2026 10:45 TSİ |
| R1@1h | 16 | risk_denied=11, etiket_duygu=3, arm_conflict=2 | risk/limit=13, filtre=3 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 11 | rr_below_min=9, etiket_duygu=2 | eşik=9, filtre=2 | veri: 20.11.2026 11:00 TSİ |
| R1@1d | 0 (aday üretmedi) | - | - | veri: 23.11.2026 15:15 TSİ |
| TF1@1h | 28 | risk_denied=22, arm_conflict=4, etiket_duygu=2 | risk/limit=26, filtre=2 | veri: 23.11.2026 14:00 TSİ |
| TF1@4h | 13 | risk_denied=9, etiket_duygu=2, cluster_cap=2 | risk/limit=11, filtre=2 | veri: 21.11.2026 07:00 TSİ |
| B1@4h | 1 | risk_denied=1 | risk/limit=1 | veri: 20.11.2026 07:00 TSİ |
| S1@1d | 3 | stop_width=3 | eşik=3 | veri: 21.11.2026 03:00 TSİ |
| F1@1h | 66 | risk_denied=43, stop_width=8, rr_below_min=8, arm_conflict=6, etiket_duygu=1 | risk/limit=49, eşik=16, filtre=1 | veri: 23.11.2026 15:00 TSİ |
| F1@4h | 2 | risk_denied=1, rr_below_min=1 | risk/limit=1, eşik=1 | veri: 20.11.2026 03:00 TSİ |
| F1@1d | 0 (aday üretmedi) | - | - | veri: 23.11.2026 15:15 TSİ |
| M1@1d | 0 (aday üretmedi) | - | - | veri: 23.11.2026 15:15 TSİ |

Açan kollar: T1@15m, T1@1h, TF1@15m, TF1@1d, B1@15m, B1@1h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, F1@15m, M1@1h, M1@4h, M1@15m

### Kol bazında neden işlem açmıyor (tüm kayıt / son 12 saat)

Pencere: «tüm kayıt» = kilitli dönem dışındaki tüm karar satırları; «son 12 saat» = veri kesitinden (23.11.2026 15:15 TSİ) geriye 12 saat. Kâğıt risk limitleri kayıt süresince gevşetilmiş olabilir; eski `risk_denied` sayıları o günkü limitlere aittir, güncel durumu «son 12 saat» sütunları gösterir. Risk reddi `risk_reason` metninden limit adına çevrilir (max_open_risk, max_same_dir_risk, daily_max_loss ...).

| Kol | Aday (tüm) | Girdi (tüm) | Skip (tüm) | Aday (12s) | Girdi (12s) | Skip (12s) | Veri |
|---|---|---|---|---|---|---|---|
| T1@15m | 406 | 6 | stop_width=208; risk_denied=159 (margin_total=108, daily_max_loss=44, max_same_dir_risk=7); ml_filter=23; arm_conflict=6 (M1@1h=3, T1@1h=1, M1@4h=1); order_failed=2; etiket_duygu=2 | 61 | 2 | stop_width=39; risk_denied=11 (margin_total=11); ml_filter=8; arm_conflict=1 (M1@4h=1) | veri: 23.11.2026 15:15 TSİ |
| T1@1h | 115 | 10 | stop_width=53; risk_denied=39 (margin_total=29, daily_max_loss=10); ml_filter=9; veto_blocked=3; veto_missing=1 | 22 | 0 | stop_width=15; risk_denied=5 (margin_total=5); ml_filter=2 | veri: 23.11.2026 15:15 TSİ |
| T1@4h | 7 | 0 | stop_width=5; risk_denied=2 (daily_max_loss=1, margin_total=1) | 1 | 0 | risk_denied=1 (margin_total=1) | veri: 23.11.2026 15:15 TSİ |
| T1@1d | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| R1@15m | 31 | 0 | risk_denied=28 (margin_total=27, daily_max_loss=1); etiket_duygu=3 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| R1@1h | 16 | 0 | risk_denied=11 (margin_total=9, daily_max_loss=2); etiket_duygu=3; arm_conflict=2 (R1@4h=1) | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| R1@4h | 11 | 0 | rr_below_min=9; etiket_duygu=2 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| R1@1d | 0 | 0 | - | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| TF1@15m | 106 | 3 | risk_denied=82 (margin_total=51, daily_max_loss=20, max_same_dir_risk=11); arm_conflict=9 (TF1@1h=4, M1@1h=3, TF1@4h=1, S1@1h=1); etiket_duygu=6; cluster_cap=6 (hisse_teknoloji=6) | 12 | 1 | risk_denied=9 (margin_total=9); arm_conflict=2 (M1@1h=1, TF1@1h=1) | veri: 23.11.2026 15:15 TSİ |
| TF1@1h | 28 | 0 | risk_denied=22 (margin_total=12, daily_max_loss=8, max_same_dir_risk=2); arm_conflict=4 (TF1@4h=2, S1@4h=1, M1@4h=1); etiket_duygu=2 | 2 | 0 | risk_denied=2 (margin_total=2) | veri: 23.11.2026 15:15 TSİ |
| TF1@4h | 13 | 0 | risk_denied=9 (daily_max_loss=6, max_same_dir_risk=2, margin_total=1); etiket_duygu=2; cluster_cap=2 (hisse_teknoloji=2) | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| TF1@1d | 6 | 2 | risk_denied=4 (margin_total=2, daily_max_loss=2) | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| B1@15m | 29 | 1 | risk_denied=16 (margin_total=9, daily_max_loss=7); stop_width=9; arm_conflict=2 (TF1@1h=2); entry_gate_closed=1 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| B1@1h | 11 | 2 | risk_denied=8 (margin_total=4, daily_max_loss=4); arm_conflict=1 (TF1@4h=1) | 1 | 0 | risk_denied=1 (margin_total=1) | veri: 23.11.2026 15:15 TSİ |
| B1@4h | 1 | 0 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| B1@1d | 2 | 1 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| H2@15m | 120 | 2 | risk_denied=86 (margin_total=44, daily_max_loss=34, max_same_dir_risk=8); stop_width=19; arm_conflict=11 (TF1@15m=7, M1@1h=1, M1@4h=1, T1@15m=1); entry_gate_closed=1; order_failed=1 | 4 | 0 | risk_denied=3 (margin_total=3); stop_width=1 | veri: 23.11.2026 15:15 TSİ |
| H2@1h | 46 | 1 | risk_denied=32 (margin_total=23, daily_max_loss=7, max_same_dir_risk=2); stop_width=7; arm_conflict=5 (H2@4h=2, TF1@1h=1, TF1@4h=1, M1@4h=1); etiket_duygu=1 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| H2@4h | 18 | 1 | risk_denied=15 (margin_total=10, daily_max_loss=5); stop_width=2 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| H2@1d | 3 | 1 | arm_conflict=1 (TF1@1d=1); risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| S1@15m | 307 | 7 | risk_denied=132 (margin_total=90, daily_max_loss=34, max_same_dir_risk=8); stop_width=123; arm_conflict=35 (TF1@15m=11, T1@15m=11, M1@1h=5, H2@15m=2, T1@1h=1, B1@15m=1, TF1@1h=1, S1@1h=1, F1@1h=1); etiket_duygu=7; cluster_cap=3 (hisse_teknoloji=3) | 31 | 2 | stop_width=14; risk_denied=9 (margin_total=9); arm_conflict=6 (T1@15m=4, M1@1h=1, F1@1h=1) | veri: 23.11.2026 15:15 TSİ |
| S1@1h | 70 | 3 | risk_denied=32 (margin_total=26, daily_max_loss=4, max_same_dir_risk=2); stop_width=25; arm_conflict=9 (H2@1h=2, T1@1h=2, H2@4h=2, T1@4h=1, TF1@4h=1, TF1@1h=1); order_failed=1 | 2 | 0 | risk_denied=2 (margin_total=2) | veri: 23.11.2026 15:15 TSİ |
| S1@4h | 15 | 1 | stop_width=8; risk_denied=3 (margin_total=2, daily_max_loss=1); arm_conflict=3 (TF1@4h=2, H2@1d=1) | 3 | 1 | risk_denied=2 (margin_total=2) | veri: 23.11.2026 15:15 TSİ |
| S1@1d | 3 | 0 | stop_width=3 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| F1@15m | 265 | 7 | risk_denied=134 (margin_total=112, daily_max_loss=20, max_same_dir_risk=2); stop_width=69; rr_below_min=30; arm_conflict=14 (M1@1h=7, R1@15m=3, M1@4h=3, T1@1h=1); etiket_duygu=7; entry_gate_closed=3; cluster_cap=1 (hisse_teknoloji=1) | 53 | 2 | risk_denied=30 (margin_total=30); arm_conflict=9 (M1@1h=6, M1@4h=3); rr_below_min=6; stop_width=6 | veri: 23.11.2026 15:15 TSİ |
| F1@1h | 66 | 0 | risk_denied=43 (margin_total=38, daily_max_loss=5); stop_width=8; rr_below_min=8; arm_conflict=6 (R1@1h=4, M1@4h=2); etiket_duygu=1 | 20 | 0 | risk_denied=14 (margin_total=14); stop_width=3; rr_below_min=2; arm_conflict=1 (M1@4h=1) | veri: 23.11.2026 15:15 TSİ |
| F1@4h | 2 | 0 | risk_denied=1 (daily_max_loss=1); rr_below_min=1 | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| F1@1d | 0 | 0 | - | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |
| M1@1h | 417 | 4 | risk_denied=244 (margin_total=223, daily_max_loss=21); etiket_rejim=116; arm_conflict=53 (S1@1h=16, F1@1h=12, T1@1h=10, M1@4h=8, H2@4h=3, TF1@4h=1, B1@1h=1, TF1@1h=1, B1@1d=1) | 63 | 1 | risk_denied=54 (margin_total=54); arm_conflict=7 (F1@1h=4, T1@1h=2, S1@1h=1); etiket_rejim=1 | veri: 23.11.2026 15:15 TSİ |
| M1@4h | 85 | 2 | risk_denied=77 (margin_total=73, daily_max_loss=2, max_same_dir_risk=2); arm_conflict=6 (H2@4h=2, S1@4h=2, R1@4h=1, H2@1d=1) | 34 | 1 | risk_denied=31 (margin_total=31); arm_conflict=2 (S1@4h=2) | veri: 23.11.2026 15:15 TSİ |
| M1@15m | 812 | 4 | risk_denied=669 (margin_total=455, daily_max_loss=214); etiket_rejim=72; arm_conflict=55 (S1@15m=20, M1@1h=14, T1@15m=6, T1@1h=5, H2@1h=3, H2@15m=2, F1@15m=2, TF1@15m=1, TF1@4h=1, M1@4h=1); order_failed=12 | 37 | 0 | risk_denied=33 (margin_total=33); etiket_rejim=2; arm_conflict=2 (M1@4h=1, S1@15m=1) | veri: 23.11.2026 15:15 TSİ |
| M1@1d | 0 | 0 | - | 0 | 0 | - | veri: 23.11.2026 15:15 TSİ |

Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta R1@1d, F1@1d, M1@1d · yalnız son 12 saatte T1@1d, R1@15m, R1@1h, R1@4h, TF1@4h, TF1@1d, B1@15m, B1@4h, B1@1d, H2@1h, H2@4h, H2@1d, S1@1d, F1@4h.

Aday = `decision_events` satırı. Golge kararlar (shadow) ve hiç kayda girmeyen sinyaller bu sayıya girmez.

### stop_width skip'leri: dar / geniş (son 12 saat / tüm kayıt)

İzinli bant: stop/ATR 0.5 – 2.0 (signals.STOP_DIST_MIN_ATR / STOP_DIST_MAX_ATR). Yalnız ölçüm; davranış değişmez. Dar/geniş ayrımı kayıtlı `features.stop_dist_atr` değerinin banta göre karşılaştırılmasından türetilir; medyan = reddedilen adayların medyan stop/ATR'si.

| Kol | Son 12s | Tüm kayıt | Veri |
|---|---|---|---|
| T1@15m | dar=0, geniş=39 · medyan 2.69 | dar=0, geniş=208 · medyan 2.80 | veri: 23.11.2026 15:15 TSİ |
| T1@1h | dar=0, geniş=15 · medyan 2.70 | dar=0, geniş=53 · medyan 2.46 | veri: 23.11.2026 15:15 TSİ |
| T1@4h | - | dar=0, geniş=5 · medyan 3.02 | veri: 23.11.2026 15:15 TSİ |
| T1@1d | - | dar=0, geniş=1 · medyan 3.45 | veri: 23.11.2026 15:15 TSİ |
| R1@15m | - | - | veri: 23.11.2026 15:15 TSİ |
| R1@1h | - | - | veri: 23.11.2026 15:15 TSİ |
| R1@4h | - | - | veri: 23.11.2026 15:15 TSİ |
| R1@1d | - | - | veri: 23.11.2026 15:15 TSİ |
| TF1@15m | - | - | veri: 23.11.2026 15:15 TSİ |
| TF1@1h | - | - | veri: 23.11.2026 15:15 TSİ |
| TF1@4h | - | - | veri: 23.11.2026 15:15 TSİ |
| TF1@1d | - | - | veri: 23.11.2026 15:15 TSİ |
| B1@15m | - | dar=0, geniş=9 · medyan 3.44 | veri: 23.11.2026 15:15 TSİ |
| B1@1h | - | - | veri: 23.11.2026 15:15 TSİ |
| B1@4h | - | - | veri: 23.11.2026 15:15 TSİ |
| B1@1d | - | - | veri: 23.11.2026 15:15 TSİ |
| H2@15m | dar=0, geniş=1 · medyan 2.76 | dar=0, geniş=19 · medyan 2.83 | veri: 23.11.2026 15:15 TSİ |
| H2@1h | - | dar=0, geniş=7 · medyan 3.70 | veri: 23.11.2026 15:15 TSİ |
| H2@4h | - | dar=0, geniş=2 · medyan 3.48 | veri: 23.11.2026 15:15 TSİ |
| H2@1d | - | - | veri: 23.11.2026 15:15 TSİ |
| S1@15m | dar=0, geniş=14 · medyan 3.38 | dar=0, geniş=123 · medyan 3.37 | veri: 23.11.2026 15:15 TSİ |
| S1@1h | - | dar=0, geniş=25 · medyan 3.53 | veri: 23.11.2026 15:15 TSİ |
| S1@4h | - | dar=0, geniş=8 · medyan 3.91 | veri: 23.11.2026 15:15 TSİ |
| S1@1d | - | dar=0, geniş=3 · medyan 3.48 | veri: 23.11.2026 15:15 TSİ |
| F1@15m | dar=0, geniş=6 · medyan 2.20 | dar=0, geniş=69 · medyan 2.50 | veri: 23.11.2026 15:15 TSİ |
| F1@1h | dar=0, geniş=3 · medyan 2.33 | dar=0, geniş=8 · medyan 2.68 | veri: 23.11.2026 15:15 TSİ |
| F1@4h | - | - | veri: 23.11.2026 15:15 TSİ |
| F1@1d | - | - | veri: 23.11.2026 15:15 TSİ |
| M1@1h | - | - | veri: 23.11.2026 15:15 TSİ |
| M1@4h | - | - | veri: 23.11.2026 15:15 TSİ |
| M1@15m | - | - | veri: 23.11.2026 15:15 TSİ |
| M1@1d | - | - | veri: 23.11.2026 15:15 TSİ |

## ML 10 — Kol bazında sanal K/Z

| Kol | İşlem | Net $ | R toplamı | Kazanma | Durum | Veri |
|---|---|---|---|---|---|---|
| F1@15m | 7 | -$37,63 | -4,56 R | %14,3 | ZARARDA | veri: 23.11.2026 12:00 TSİ |
| S1@15m | 5 | -$30,88 | -2,24 R | %20,0 | ZARARDA | veri: 23.11.2026 03:01 TSİ |
| M1@1h | 4 | -$16,88 | -1,49 R | %50,0 | ZARARDA | veri: 23.11.2026 06:13 TSİ |
| T1@1h | 10 | -$15,27 | +0,44 R | %50,0 | ZARARDA | veri: 23.11.2026 03:57 TSİ |
| H2@1h | 1 | -$11,73 | -1,00 R | %0,0 | ZARARDA | veri: 21.11.2026 16:39 TSİ |
| M1@15m | 4 | -$8,07 | -2,27 R | %25,0 | ZARARDA | veri: 22.11.2026 05:45 TSİ |
| B1@15m | 1 | +$3,39 | +0,73 R | %100,0 | kârda/başa baş | veri: 19.11.2026 20:15 TSİ |
| TF1@15m | 3 | +$4,26 | +0,27 R | %66,7 | kârda/başa baş | veri: 23.11.2026 06:11 TSİ |
| H2@15m | 2 | +$4,89 | +0,49 R | %50,0 | kârda/başa baş | veri: 21.11.2026 09:41 TSİ |
| B1@1h | 2 | +$13,14 | +1,35 R | %50,0 | kârda/başa baş | veri: 21.11.2026 14:31 TSİ |
| S1@1h | 3 | +$13,71 | +1,44 R | %66,7 | kârda/başa baş | veri: 23.11.2026 13:41 TSİ |
| M1@4h | 1 | +$20,50 | +1,99 R | %100,0 | kârda/başa baş | veri: 20.11.2026 19:00 TSİ |
| T1@15m | 6 | +$82,54 | +6,89 R | %66,7 | kârda/başa baş | veri: 23.11.2026 05:22 TSİ |
| B1@1d | 0 | - | - | - | - | veri: işlem yok |
| B1@4h | 0 | - | - | - | - | veri: işlem yok |
| F1@1d | 0 | - | - | - | - | veri: işlem yok |
| F1@1h | 0 | - | - | - | - | veri: işlem yok |
| F1@4h | 0 | - | - | - | - | veri: işlem yok |
| H2@1d | 0 | - | - | - | - | veri: işlem yok |
| H2@4h | 0 | - | - | - | - | veri: işlem yok |
| M1@1d | 0 | - | - | - | - | veri: işlem yok |
| R1@15m | 0 | - | - | - | - | veri: işlem yok |
| R1@1d | 0 | - | - | - | - | veri: işlem yok |
| R1@1h | 0 | - | - | - | - | veri: işlem yok |
| R1@4h | 0 | - | - | - | - | veri: işlem yok |
| S1@1d | 0 | - | - | - | - | veri: işlem yok |
| S1@4h | 0 | - | - | - | - | veri: işlem yok |
| T1@1d | 0 | - | - | - | - | veri: işlem yok |
| T1@4h | 0 | - | - | - | - | veri: işlem yok |
| TF1@1d | 0 | - | - | - | - | veri: işlem yok |
| TF1@1h | 0 | - | - | - | - | veri: işlem yok |
| TF1@4h | 0 | - | - | - | - | veri: işlem yok |

Zarardaki kollara karşı mevcut mekanizmalar (kod/yapılandırma; tetik durumu okunabilen durum dosyasından):

| Mekanizma | Var mı | Etki | Tetiklendi mi | Veri |
|---|---|---|---|---|
| Ders: kol kapatma (arms_off) | var | yalnız karne/rapor bilgisi; giriş ENGELLENMEZ (sahip kararı, 19 Kasım; gates.py `arm_would_close` sayacı) | tetiklendi: F1@15m, H2@15m, H2@1h, M1@15m, R1@15m, S1@15m, T1@15m, TF1@15m | okuma: 23.11.2026 15:20 TSİ |
| Ders: 10 R freni (lesson_brake) | var | ders ayarlarını referansa döndürür, otomatik uygulamayı durdurur; kolu kapatmaz | tetiklenmedi | okuma: 23.11.2026 15:20 TSİ |
| Kol başına açık pozisyon tavanı (arm_max_positions) ve küme/hesap tavanı | var | kayıptan bağımsız konum sınırı; zarardaki kolu özel olarak ayırmaz | kayıp temelli tetik değil | okuma: 23.11.2026 15:20 TSİ |
| Risk kademe denetimi (risk_ladder, hesap düzeyi küçültme) | var (hesap düzeyi; kol düzeyi değil) | tepe-denge düşüşünde hedef işlem riskini kademeli düşürür / durdurur; motor zorunlu yalnız canlı modda | kâğıt ayarında LADDER_BOTS boş; kâğıtta kademe izlenmez | okuma: 23.11.2026 15:20 TSİ |
| Kol bazında otomatik karantina / boyut küçültme | yok | zararda kol: F1@15m, S1@15m, M1@1h, T1@1h, H2@1h, M1@15m; bu kolları kendiliğinden kısan kural yok | - | okuma: 23.11.2026 15:20 TSİ |

## ML 11 — Long/short dağılımı

| Yön | İşlem | Net $ | Kazanma | R | Veri |
|---|---|---|---|---|---|
| long | 6 | -$15,10 | %50,0 | -1,32 R | veri: 22.11.2026 13:30 TSİ |
| short | 43 | +$37,07 | %44,2 | +3,36 R | veri: 23.11.2026 13:41 TSİ |

| Rejim | Long (n / net $ / kazanma) | Short (n / net $ / kazanma) | Veri |
|---|---|---|---|
| trend_up | 2 / -$8,50 / %50,0 | 0 / - / - | veri: 22.11.2026 13:30 TSİ |
| trend_down | 1 / +$4,86 / %100,0 | 42 / +$44,39 / %45,2 | veri: 23.11.2026 13:41 TSİ |
| range | 2 / -$19,65 / %0,0 | 1 / -$7,33 / %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 1 / +$8,20 / %100,0 | 0 / - / - | veri: 20.11.2026 05:45 TSİ |
| volatile | 0 / - / - | 0 / - / - | veri: işlem yok |

Güncel rejim (son karar zamanından geriye 24 saatte en sık rejim; 721 karar): trend_down (veri: 23.11.2026 15:15 TSİ)
Long-yetkin kollar (kayıtta ≥1 long adayı olanlar) bu rejimde: aday 122 · alınan 1

| Kol | Long aday (güncel rejim) | Alınan (güncel rejim) | Long aday (tüm kayıt) | Alınan (tüm kayıt) | Veri |
|---|---|---|---|---|---|
| T1@15m | 0 | 0 | 17 | 0 | veri: 23.11.2026 14:45 TSİ |
| T1@1h | 0 | 0 | 7 | 1 | veri: 23.11.2026 14:00 TSİ |
| T1@4h | 0 | 0 | 3 | 0 | veri: 23.11.2026 15:00 TSİ |
| R1@15m | 0 | 0 | 30 | 0 | veri: 20.11.2026 10:45 TSİ |
| R1@1h | 0 | 0 | 15 | 0 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 0 | 0 | 11 | 0 | veri: 20.11.2026 11:00 TSİ |
| TF1@15m | 0 | 0 | 8 | 0 | veri: 21.11.2026 20:15 TSİ |
| TF1@1h | 0 | 0 | 4 | 0 | veri: 23.11.2026 05:00 TSİ |
| TF1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 19:00 TSİ |
| B1@1h | 0 | 0 | 2 | 0 | veri: 23.11.2026 06:00 TSİ |
| H2@15m | 0 | 0 | 7 | 0 | veri: 22.11.2026 16:00 TSİ |
| H2@1h | 0 | 0 | 2 | 0 | veri: 22.11.2026 13:00 TSİ |
| H2@4h | 0 | 0 | 1 | 0 | veri: 21.11.2026 23:00 TSİ |
| S1@15m | 0 | 0 | 31 | 3 | veri: 23.11.2026 14:45 TSİ |
| S1@1h | 0 | 0 | 5 | 0 | veri: 22.11.2026 13:00 TSİ |
| S1@4h | 0 | 0 | 3 | 0 | veri: 23.11.2026 07:00 TSİ |
| F1@15m | 0 | 0 | 47 | 2 | veri: 23.11.2026 04:45 TSİ |
| F1@1h | 0 | 0 | 17 | 0 | veri: 23.11.2026 14:00 TSİ |
| F1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 03:00 TSİ |
| M1@1h | 107 | 1 | 110 | 1 | veri: 23.11.2026 04:00 TSİ |
| M1@15m | 15 | 0 | 16 | 0 | veri: 23.11.2026 14:15 TSİ |

## ML 12 — Kâğıt / geri test tutarlılığı

Toplam kâğıt R (n=49): +2,04 R (veri: 23.11.2026 13:41 TSİ). Yayımlanmış bant (n=49 için aradeğer): %2,5=-25,3 · %10=-18,0 · ortanca=+0,4 · %90=+29,1. Konum: %10-%90 arası (bant içinde). Kaynak: docs/kagit-degerlendirme-plani.md §4.4 (kümülatif net R, referans bootstrap bandı).

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
