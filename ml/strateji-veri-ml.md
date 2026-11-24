# [ML] Strateji verisi (beyin fırtınası için)

Üretim: 24.11.2026 09:21 TSİ · Kâğıt başlangıcı (ilk kayıt): 17.11.2026 18:00 TSİ · Veri kesiti: 24.11.2026 09:15 TSİ
Kapanan işlem: 65 · Açık işlem: 7 · Karar kaydı: 3902 · Yapılandırılmış kol: 33
Kapsam: yalnız kâğıt defteri (salt okunur). Kilitli dönem (01.05.2026-01.11.2026) kayıtları okunmadı/ayıklandı (ayıklanan kayıt: 0). Yeni geri test hesaplanmadı. Yorum/öneri yok.

## Ortak 1 — Kâğıt başlangıcından beri sonuç

| Ölçü | Değer | Veri |
|---|---|---|
| Net K/Z | -$32,37 | veri: 24.11.2026 08:34 TSİ |
| İşlem sayısı (kapanan) | 65 | veri: 24.11.2026 08:34 TSİ |
| Kazanma oranı (net > 0) | %41,5 | veri: 24.11.2026 08:34 TSİ |
| Ort. kazanç | +1,13 R / +$9,73 | veri: 24.11.2026 08:34 TSİ |
| Ort. kayıp | -0,94 R / -$7,77 | veri: 24.11.2026 08:34 TSİ |
| Toplam R | -5,09 R | veri: 24.11.2026 08:34 TSİ |

## Ortak 2 — K/Z yoğunlaşması

| Ölçü | Değer | Veri |
|---|---|---|
| En iyi 1 işlemin net içindeki payı | - (+$41,53) | veri: 24.11.2026 08:34 TSİ |
| En iyi 2 işlemin net içindeki payı | - (+$73,56) | veri: 24.11.2026 08:34 TSİ |
| En iyi 3 çıkarılınca net | -$131,02 | veri: 24.11.2026 08:34 TSİ |
| En kötü 3 çıkarılınca net | +$6,56 | veri: 24.11.2026 08:34 TSİ |
| En iyi 3 + en kötü 3 çıkarılınca net | -$92,09 | veri: 24.11.2026 08:34 TSİ |

Pay: net > 0 iken hesaplanır; yetersiz işlemde (en iyi/kötü 3 için < 4, ikisi birden < 7) '-'.

## Ortak 3 — Maliyetler

| Kalem | Tutar | Brüt kâra oranı | Veri |
|---|---|---|---|
| Brüt kâr (yalnız brüt > 0 olan işlemlerin toplamı) | $284,79 | - | veri: 24.11.2026 08:34 TSİ |
| Toplam brüt K/Z (tüm işlemler) | +$13,79 | - | veri: 24.11.2026 08:34 TSİ |
| Komisyon | $47,45 | %16,7 | veri: 24.11.2026 08:34 TSİ |
| Fonlama (ödenen) | -$1,28 | %0,5 | veri: 24.11.2026 08:34 TSİ |
| Komisyon + fonlama | $46,16 | %16,2 | veri: 24.11.2026 08:34 TSİ |
| Kayma (giriş+çıkış, planlanana göre; brüte ZATEN işlenmiştir) | +$75,53 | %26,5 | veri: 24.11.2026 08:34 TSİ |
| Komisyon + fonlama + kayma | $121,69 | %42,7 | veri: 24.11.2026 08:34 TSİ |

Net K/Z = brüt - komisyon - fonlama (kayma fiyatlara işlendiğinden ayrıca düşülmez).

## Ortak 6 — Girişteki piyasa rejimine göre sonuç

| Rejim | İşlem | Net K/Z | Kazanma | Veri |
|---|---|---|---|---|
| trend_up | 3 | -$9,20 | %33,3 | veri: 23.11.2026 17:00 TSİ |
| trend_down | 57 | -$4,84 | %42,1 | veri: 24.11.2026 08:34 TSİ |
| range | 3 | -$26,98 | %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 2 | +$8,65 | %100,0 | veri: 23.11.2026 17:15 TSİ |
| volatile | 0 | - | - | veri: işlem yok |

## Ortak 7 — 30 / 100 / 300 kapanan işleme ulaşma süresi

Süre: 6,6 gün (17.11.2026 18:00 TSİ → 24.11.2026 09:15 TSİ); kapanan 65; genel hız 9,80 işlem/gün; kol medyan hızı: işlemi olan 15 kol 0,452 işlem/gün, tüm 33 yapılandırılmış kol 0,000 işlem/gün (veri: 24.11.2026 09:15 TSİ).

| Hedef | Genel (güncel hızla) | Kol medyanı (işlemi olan kollar) | Kol medyanı (tüm kollar) | Hedefe ulaşan kol | Veri |
|---|---|---|---|---|---|
| 30 | ulaşıldı | 66 gün (9,5 hafta) | hesaplanamaz (hız 0) | 0 | veri: 24.11.2026 09:15 TSİ |
| 100 | 4 gün (0,5 hafta) | 221 gün (31,6 hafta) | hesaplanamaz (hız 0) | 0 | veri: 24.11.2026 09:15 TSİ |
| 300 | 24 gün (3,4 hafta) | 664 gün (94,8 hafta) | hesaplanamaz (hız 0) | 0 | veri: 24.11.2026 09:15 TSİ |

## ML 8 — Yapılandırılmış kollar: işlem açan / açmayan

Yapılandırılmış kol: 33 · ≥1 işlem açan: 18 · hiç açmayan: 15 (veri: 24.11.2026 09:15 TSİ)

| Kol | Aday (karar kaydı) | En sık skip_reason | Grup (filtre/rejim/veri/eşik/risk-limit) | Veri |
|---|---|---|---|---|
| T1@4h | 26 | stop_width=23, risk_denied=2, ml_filter=1 | eşik=23, risk/limit=2, filtre=1 | veri: 24.11.2026 03:00 TSİ |
| T1@1d | 1 | stop_width=1 | eşik=1 | veri: 20.11.2026 03:00 TSİ |
| R1@15m | 31 | risk_denied=28, etiket_duygu=3 | risk/limit=28, filtre=3 | veri: 20.11.2026 10:45 TSİ |
| R1@1h | 16 | risk_denied=11, etiket_duygu=3, arm_conflict=2 | risk/limit=13, filtre=3 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 11 | rr_below_min=9, etiket_duygu=2 | eşik=9, filtre=2 | veri: 20.11.2026 11:00 TSİ |
| R1@1d | 0 (aday üretmedi) | - | - | veri: 24.11.2026 09:15 TSİ |
| TF1@1h | 33 | risk_denied=26, arm_conflict=5, etiket_duygu=2 | risk/limit=31, filtre=2 | veri: 24.11.2026 08:00 TSİ |
| TF1@4h | 14 | risk_denied=10, etiket_duygu=2, cluster_cap=2 | risk/limit=12, filtre=2 | veri: 23.11.2026 19:00 TSİ |
| B1@4h | 2 | risk_denied=2 | risk/limit=2 | veri: 24.11.2026 07:00 TSİ |
| S1@1d | 4 | stop_width=3, arm_conflict=1 | eşik=3, risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| F1@1h | 75 | risk_denied=49, stop_width=10, rr_below_min=8, arm_conflict=7, etiket_duygu=1 | risk/limit=56, eşik=18, filtre=1 | veri: 24.11.2026 05:00 TSİ |
| F1@4h | 5 | stop_width=3, risk_denied=1, rr_below_min=1 | eşik=4, risk/limit=1 | veri: 23.11.2026 23:00 TSİ |
| F1@1d | 0 (aday üretmedi) | - | - | veri: 24.11.2026 09:15 TSİ |
| M1@1d | 1 | risk_denied=1 | risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| HB1@1h | 0 (aday üretmedi) | - | - | veri: 24.11.2026 09:15 TSİ |

Açan kollar: T1@15m, T1@1h, TF1@15m, TF1@1d, B1@15m, B1@1h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, F1@15m, M1@1h, M1@4h, M1@15m

### Kol bazında neden işlem açmıyor (tüm kayıt / son 12 saat)

Pencere: «tüm kayıt» = kilitli dönem dışındaki tüm karar satırları; «son 12 saat» = veri kesitinden (24.11.2026 09:15 TSİ) geriye 12 saat. Kâğıt risk limitleri kayıt süresince gevşetilmiş olabilir; eski `risk_denied` sayıları o günkü limitlere aittir, güncel durumu «son 12 saat» sütunları gösterir. Risk reddi `risk_reason` metninden limit adına çevrilir (max_open_risk, max_same_dir_risk, daily_max_loss ...).

| Kol | Aday (tüm) | Girdi (tüm) | Skip (tüm) | Aday (12s) | Girdi (12s) | Skip (12s) | Veri |
|---|---|---|---|---|---|---|---|
| T1@15m | 516 | 8 | stop_width=267; risk_denied=192 (margin_total=110, daily_max_loss=44, daily_limit=19, max_same_dir_risk=17, korelasyon_grubu=2); ml_filter=39; arm_conflict=6 (M1@1h=3, T1@1h=1, M1@4h=1); order_failed=2; etiket_duygu=2 | 76 | 2 | risk_denied=32 (daily_limit=19, max_same_dir_risk=10, korelasyon_grubu=2, margin_total=1); stop_width=29; ml_filter=13 | veri: 24.11.2026 09:15 TSİ |
| T1@1h | 142 | 10 | stop_width=68; risk_denied=41 (margin_total=31, daily_max_loss=10); ml_filter=19; veto_blocked=3; veto_missing=1 | 17 | 0 | ml_filter=9; stop_width=7; risk_denied=1 (margin_total=1) | veri: 24.11.2026 09:15 TSİ |
| T1@4h | 26 | 0 | stop_width=23; risk_denied=2 (daily_max_loss=1, margin_total=1); ml_filter=1 | 19 | 0 | stop_width=18; ml_filter=1 | veri: 24.11.2026 09:15 TSİ |
| T1@1d | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| R1@15m | 31 | 0 | risk_denied=28 (margin_total=27, daily_max_loss=1); etiket_duygu=3 | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| R1@1h | 16 | 0 | risk_denied=11 (margin_total=9, daily_max_loss=2); etiket_duygu=3; arm_conflict=2 (R1@4h=1) | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| R1@4h | 11 | 0 | rr_below_min=9; etiket_duygu=2 | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| R1@1d | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| TF1@15m | 126 | 3 | risk_denied=99 (margin_total=52, daily_max_loss=20, max_same_dir_risk=19, daily_limit=8); arm_conflict=12 (TF1@1h=4, M1@1h=3, T1@1h=2, TF1@4h=1, S1@1h=1, H2@1h=1); etiket_duygu=6; cluster_cap=6 (hisse_teknoloji=6) | 19 | 0 | risk_denied=16 (max_same_dir_risk=8, daily_limit=7, margin_total=1); arm_conflict=3 (T1@1h=2, H2@1h=1) | veri: 24.11.2026 09:15 TSİ |
| TF1@1h | 33 | 0 | risk_denied=26 (margin_total=12, daily_max_loss=8, max_same_dir_risk=3, daily_limit=3); arm_conflict=5 (TF1@4h=2, M1@4h=2, S1@4h=1); etiket_duygu=2 | 4 | 0 | risk_denied=3 (daily_limit=2, max_same_dir_risk=1); arm_conflict=1 (M1@4h=1) | veri: 24.11.2026 09:15 TSİ |
| TF1@4h | 14 | 0 | risk_denied=10 (daily_max_loss=6, max_same_dir_risk=2, margin_total=1, daily_limit=1); etiket_duygu=2; cluster_cap=2 (hisse_teknoloji=2) | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| TF1@1d | 7 | 2 | risk_denied=5 (margin_total=2, daily_max_loss=2, max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 24.11.2026 09:15 TSİ |
| B1@15m | 30 | 1 | risk_denied=17 (margin_total=9, daily_max_loss=7, daily_limit=1); stop_width=9; arm_conflict=2 (TF1@1h=2); entry_gate_closed=1 | 1 | 0 | risk_denied=1 (daily_limit=1) | veri: 24.11.2026 09:15 TSİ |
| B1@1h | 13 | 2 | risk_denied=8 (margin_total=4, daily_max_loss=4); arm_conflict=2 (TF1@4h=1, M1@4h=1); stop_width=1 | 2 | 0 | stop_width=1; arm_conflict=1 (M1@4h=1) | veri: 24.11.2026 09:15 TSİ |
| B1@4h | 2 | 0 | risk_denied=2 (margin_total=1, max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 24.11.2026 09:15 TSİ |
| B1@1d | 2 | 1 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| H2@15m | 141 | 4 | risk_denied=101 (margin_total=46, daily_max_loss=34, daily_limit=11, max_same_dir_risk=10); stop_width=20; arm_conflict=14 (TF1@15m=9, M1@1h=1, M1@4h=1, T1@15m=1, TF1@1h=1); entry_gate_closed=1; order_failed=1 | 19 | 2 | risk_denied=13 (daily_limit=10, max_same_dir_risk=2, margin_total=1); arm_conflict=3 (TF1@15m=2, TF1@1h=1); stop_width=1 | veri: 24.11.2026 09:15 TSİ |
| H2@1h | 49 | 1 | risk_denied=34 (margin_total=24, daily_max_loss=7, max_same_dir_risk=3); stop_width=8; arm_conflict=5 (H2@4h=2, TF1@1h=1, TF1@4h=1, M1@4h=1); etiket_duygu=1 | 2 | 0 | risk_denied=2 (max_same_dir_risk=1, margin_total=1) | veri: 24.11.2026 09:15 TSİ |
| H2@4h | 18 | 1 | risk_denied=15 (margin_total=10, daily_max_loss=5); stop_width=2 | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| H2@1d | 3 | 1 | arm_conflict=1 (TF1@1d=1); risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| S1@15m | 372 | 8 | risk_denied=169 (margin_total=99, daily_max_loss=34, daily_limit=18, max_same_dir_risk=17, diğer=1); stop_width=142; arm_conflict=43 (T1@15m=14, TF1@15m=13, M1@1h=5, H2@15m=4, T1@1h=2, B1@15m=1, TF1@1h=1, S1@1h=1, F1@1h=1); etiket_duygu=7; cluster_cap=3 (hisse_teknoloji=3) | 48 | 0 | risk_denied=29 (daily_limit=18, max_same_dir_risk=9, diğer=1, margin_total=1); stop_width=11; arm_conflict=8 (T1@15m=3, TF1@15m=2, H2@15m=2, T1@1h=1) | veri: 24.11.2026 09:15 TSİ |
| S1@1h | 73 | 3 | risk_denied=32 (margin_total=26, daily_max_loss=4, max_same_dir_risk=2); stop_width=27; arm_conflict=10 (T1@1h=3, H2@1h=2, H2@4h=2, T1@4h=1, TF1@4h=1, TF1@1h=1); order_failed=1 | 3 | 0 | stop_width=2; arm_conflict=1 (T1@1h=1) | veri: 24.11.2026 09:15 TSİ |
| S1@4h | 17 | 1 | stop_width=9; risk_denied=4 (margin_total=2, daily_max_loss=1, daily_limit=1); arm_conflict=3 (TF1@4h=2, H2@1d=1) | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| S1@1d | 4 | 0 | stop_width=3; arm_conflict=1 (TF1@1d=1) | 1 | 0 | arm_conflict=1 (TF1@1d=1) | veri: 24.11.2026 09:15 TSİ |
| F1@15m | 290 | 9 | risk_denied=149 (margin_total=116, daily_max_loss=20, daily_limit=6, max_same_dir_risk=4, diğer=3); stop_width=73; rr_below_min=34; arm_conflict=14 (M1@1h=7, R1@15m=3, M1@4h=3, T1@1h=1); etiket_duygu=7; entry_gate_closed=3; cluster_cap=1 (hisse_teknoloji=1) | 12 | 2 | risk_denied=7 (diğer=3, max_same_dir_risk=2, daily_limit=1, margin_total=1); stop_width=2; rr_below_min=1 | veri: 24.11.2026 09:15 TSİ |
| F1@1h | 75 | 0 | risk_denied=49 (margin_total=40, daily_max_loss=5, daily_limit=2, max_same_dir_risk=2); stop_width=10; rr_below_min=8; arm_conflict=7 (R1@1h=4, M1@4h=3); etiket_duygu=1 | 4 | 0 | risk_denied=3 (max_same_dir_risk=2, daily_limit=1); arm_conflict=1 (M1@4h=1) | veri: 24.11.2026 09:15 TSİ |
| F1@4h | 5 | 0 | stop_width=3; risk_denied=1 (daily_max_loss=1); rr_below_min=1 | 3 | 0 | stop_width=3 | veri: 24.11.2026 09:15 TSİ |
| F1@1d | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |
| M1@1h | 419 | 4 | risk_denied=246 (margin_total=224, daily_max_loss=21, diğer=1); etiket_rejim=116; arm_conflict=53 (S1@1h=16, F1@1h=12, T1@1h=10, M1@4h=8, H2@4h=3, TF1@4h=1, B1@1h=1, TF1@1h=1, B1@1d=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 24.11.2026 09:15 TSİ |
| M1@4h | 119 | 2 | risk_denied=109 (margin_total=73, daily_limit=17, max_same_dir_risk=12, diğer=5, daily_max_loss=2); arm_conflict=8 (H2@4h=2, S1@4h=2, R1@4h=1, H2@1d=1, T1@4h=1, M1@1d=1) | 25 | 0 | risk_denied=23 (max_same_dir_risk=10, daily_limit=8, diğer=5); arm_conflict=2 (T1@4h=1, M1@1d=1) | veri: 24.11.2026 09:15 TSİ |
| M1@15m | 1346 | 11 | risk_denied=1143 (margin_total=465, daily_max_loss=214, max_same_dir_risk=203, daily_limit=193, diğer=50, korelasyon_grubu=18); arm_conflict=91 (S1@15m=28, T1@15m=18, M1@1h=14, T1@1h=9, H2@15m=6, H2@1h=4, TF1@15m=4, M1@4h=4, F1@15m=3, TF1@4h=1); etiket_rejim=89; order_failed=12 | 510 | 7 | risk_denied=470 (max_same_dir_risk=203, daily_limit=193, diğer=50, korelasyon_grubu=18, margin_total=6); arm_conflict=33 (T1@15m=12, S1@15m=7, H2@15m=4, T1@1h=3, TF1@15m=3, M1@4h=3, H2@1h=1) | veri: 24.11.2026 09:15 TSİ |
| M1@1d | 1 | 0 | risk_denied=1 (diğer=1) | 1 | 0 | risk_denied=1 (diğer=1) | veri: 24.11.2026 09:15 TSİ |
| HB1@1h | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 09:15 TSİ |

Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta R1@1d, F1@1d, HB1@1h · yalnız son 12 saatte T1@1d, R1@15m, R1@1h, R1@4h, TF1@4h, B1@1d, H2@4h, H2@1d, S1@4h.

Aday = `decision_events` satırı. Golge kararlar (shadow) ve hiç kayda girmeyen sinyaller bu sayıya girmez.

### stop_width skip'leri: dar / geniş (son 12 saat / tüm kayıt)

İzinli bant: stop/ATR 0.5 – 2.0 (signals.STOP_DIST_MIN_ATR / STOP_DIST_MAX_ATR). Yalnız ölçüm; davranış değişmez. Dar/geniş ayrımı kayıtlı `features.stop_dist_atr` değerinin banta göre karşılaştırılmasından türetilir; medyan = reddedilen adayların medyan stop/ATR'si.

| Kol | Son 12s | Tüm kayıt | Veri |
|---|---|---|---|
| T1@15m | dar=0, geniş=29 · medyan 2.30 | dar=0, geniş=267 · medyan 2.76 | veri: 24.11.2026 09:15 TSİ |
| T1@1h | dar=0, geniş=7 · medyan 2.64 | dar=0, geniş=68 · medyan 2.51 | veri: 24.11.2026 09:15 TSİ |
| T1@4h | dar=0, geniş=18 · medyan 2.46 | dar=0, geniş=23 · medyan 2.50 | veri: 24.11.2026 09:15 TSİ |
| T1@1d | - | dar=0, geniş=1 · medyan 3.45 | veri: 24.11.2026 09:15 TSİ |
| R1@15m | - | - | veri: 24.11.2026 09:15 TSİ |
| R1@1h | - | - | veri: 24.11.2026 09:15 TSİ |
| R1@4h | - | - | veri: 24.11.2026 09:15 TSİ |
| R1@1d | - | - | veri: 24.11.2026 09:15 TSİ |
| TF1@15m | - | - | veri: 24.11.2026 09:15 TSİ |
| TF1@1h | - | - | veri: 24.11.2026 09:15 TSİ |
| TF1@4h | - | - | veri: 24.11.2026 09:15 TSİ |
| TF1@1d | - | - | veri: 24.11.2026 09:15 TSİ |
| B1@15m | - | dar=0, geniş=9 · medyan 3.44 | veri: 24.11.2026 09:15 TSİ |
| B1@1h | dar=1, geniş=0 · medyan 0.43 | dar=1, geniş=0 · medyan 0.43 | veri: 24.11.2026 09:15 TSİ |
| B1@4h | - | - | veri: 24.11.2026 09:15 TSİ |
| B1@1d | - | - | veri: 24.11.2026 09:15 TSİ |
| H2@15m | dar=0, geniş=1 · medyan 3.69 | dar=0, geniş=20 · medyan 2.84 | veri: 24.11.2026 09:15 TSİ |
| H2@1h | - | dar=0, geniş=8 · medyan 3.78 | veri: 24.11.2026 09:15 TSİ |
| H2@4h | - | dar=0, geniş=2 · medyan 3.48 | veri: 24.11.2026 09:15 TSİ |
| H2@1d | - | - | veri: 24.11.2026 09:15 TSİ |
| S1@15m | dar=0, geniş=11 · medyan 3.26 | dar=0, geniş=142 · medyan 3.37 | veri: 24.11.2026 09:15 TSİ |
| S1@1h | dar=0, geniş=2 · medyan 3.04 | dar=0, geniş=27 · medyan 3.52 | veri: 24.11.2026 09:15 TSİ |
| S1@4h | - | dar=0, geniş=9 · medyan 4.02 | veri: 24.11.2026 09:15 TSİ |
| S1@1d | - | dar=0, geniş=3 · medyan 3.48 | veri: 24.11.2026 09:15 TSİ |
| F1@15m | dar=0, geniş=2 · medyan 2.35 | dar=0, geniş=73 · medyan 2.47 | veri: 24.11.2026 09:15 TSİ |
| F1@1h | - | dar=0, geniş=10 · medyan 2.46 | veri: 24.11.2026 09:15 TSİ |
| F1@4h | dar=0, geniş=3 · medyan 2.77 | dar=0, geniş=3 · medyan 2.77 | veri: 24.11.2026 09:15 TSİ |
| F1@1d | - | - | veri: 24.11.2026 09:15 TSİ |
| M1@1h | - | - | veri: 24.11.2026 09:15 TSİ |
| M1@4h | - | - | veri: 24.11.2026 09:15 TSİ |
| M1@15m | - | - | veri: 24.11.2026 09:15 TSİ |
| M1@1d | - | - | veri: 24.11.2026 09:15 TSİ |
| HB1@1h | - | - | veri: 24.11.2026 09:15 TSİ |

## ML 10 — Kol bazında sanal K/Z

| Kol | İşlem | Net $ | R toplamı | Kazanma | Durum | Veri |
|---|---|---|---|---|---|---|
| F1@15m | 8 | -$42,23 | -5,52 R | %12,5 | ZARARDA | veri: 24.11.2026 08:34 TSİ |
| S1@15m | 8 | -$36,18 | -3,29 R | %25,0 | ZARARDA | veri: 23.11.2026 17:15 TSİ |
| M1@1h | 4 | -$16,88 | -1,49 R | %50,0 | ZARARDA | veri: 23.11.2026 06:13 TSİ |
| T1@1h | 10 | -$15,27 | +0,44 R | %50,0 | ZARARDA | veri: 23.11.2026 03:57 TSİ |
| H2@1h | 1 | -$11,73 | -1,00 R | %0,0 | ZARARDA | veri: 21.11.2026 16:39 TSİ |
| H2@4h | 1 | -$10,70 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:57 TSİ |
| B1@1d | 1 | -$10,54 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:58 TSİ |
| M1@15m | 11 | -$5,97 | -2,25 R | %45,5 | ZARARDA | veri: 24.11.2026 08:15 TSİ |
| H2@15m | 3 | -$0,55 | -0,64 R | %33,3 | ZARARDA | veri: 24.11.2026 08:30 TSİ |
| B1@15m | 1 | +$3,39 | +0,73 R | %100,0 | kârda/başa baş | veri: 19.11.2026 20:15 TSİ |
| TF1@15m | 3 | +$4,26 | +0,27 R | %66,7 | kârda/başa baş | veri: 23.11.2026 06:11 TSİ |
| M1@4h | 2 | +$9,87 | +0,96 R | %50,0 | kârda/başa baş | veri: 23.11.2026 16:55 TSİ |
| B1@1h | 2 | +$13,14 | +1,35 R | %50,0 | kârda/başa baş | veri: 21.11.2026 14:31 TSİ |
| S1@1h | 3 | +$13,71 | +1,44 R | %66,7 | kârda/başa baş | veri: 23.11.2026 13:41 TSİ |
| T1@15m | 7 | +$73,30 | +5,92 R | %57,1 | kârda/başa baş | veri: 24.11.2026 04:10 TSİ |
| B1@4h | 0 | - | - | - | - | veri: işlem yok |
| F1@1d | 0 | - | - | - | - | veri: işlem yok |
| F1@1h | 0 | - | - | - | - | veri: işlem yok |
| F1@4h | 0 | - | - | - | - | veri: işlem yok |
| H2@1d | 0 | - | - | - | - | veri: işlem yok |
| HB1@1h | 0 | - | - | - | - | veri: işlem yok |
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
| Ders: kol kapatma (arms_off) | var | yalnız karne/rapor bilgisi; giriş ENGELLENMEZ (sahip kararı, 19 Kasım; gates.py `arm_would_close` sayacı) | tetiklendi: B1@15m, B1@1d, F1@15m, F1@1h, H2@15m, H2@1h, H2@4h, M1@15m, R1@15m, R1@1h, S1@15m, T1@15m, TF1@15m | okuma: 24.11.2026 09:21 TSİ |
| Ders: 10 R freni (lesson_brake) | var | ders ayarlarını referansa döndürür, otomatik uygulamayı durdurur; kolu kapatmaz | tetiklenmedi | okuma: 24.11.2026 09:21 TSİ |
| Kol başına açık pozisyon tavanı (arm_max_positions) ve küme/hesap tavanı | var | kayıptan bağımsız konum sınırı; zarardaki kolu özel olarak ayırmaz | kayıp temelli tetik değil | okuma: 24.11.2026 09:21 TSİ |
| Risk kademe denetimi (risk_ladder, hesap düzeyi küçültme) | var (hesap düzeyi; kol düzeyi değil) | tepe-denge düşüşünde hedef işlem riskini kademeli düşürür / durdurur; motor zorunlu yalnız canlı modda | kâğıt ayarında LADDER_BOTS boş; kâğıtta kademe izlenmez | okuma: 24.11.2026 09:21 TSİ |
| Kol bazında otomatik karantina / boyut küçültme | yok | zararda kol: F1@15m, S1@15m, M1@1h, T1@1h, H2@1h, H2@4h, B1@1d, M1@15m, H2@15m; bu kolları kendiliğinden kısan kural yok | - | okuma: 24.11.2026 09:21 TSİ |

## ML 11 — Long/short dağılımı

| Yön | İşlem | Net $ | Kazanma | R | Veri |
|---|---|---|---|---|---|
| long | 7 | -$15,79 | %42,9 | -1,46 R | veri: 23.11.2026 17:00 TSİ |
| short | 58 | -$16,58 | %41,4 | -3,63 R | veri: 24.11.2026 08:34 TSİ |

| Rejim | Long (n / net $ / kazanma) | Short (n / net $ / kazanma) | Veri |
|---|---|---|---|
| trend_up | 3 / -$9,20 / %33,3 | 0 / - / - | veri: 23.11.2026 17:00 TSİ |
| trend_down | 1 / +$4,86 / %100,0 | 56 / -$9,70 / %41,1 | veri: 24.11.2026 08:34 TSİ |
| range | 2 / -$19,65 / %0,0 | 1 / -$7,33 / %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 1 / +$8,20 / %100,0 | 1 / +$0,45 / %100,0 | veri: 23.11.2026 17:15 TSİ |
| volatile | 0 / - / - | 0 / - / - | veri: işlem yok |

Güncel rejim (son karar zamanından geriye 24 saatte en sık rejim; 1065 karar): trend_down (veri: 24.11.2026 09:15 TSİ)
Long-yetkin kollar (kayıtta ≥1 long adayı olanlar) bu rejimde: aday 139 · alınan 1

| Kol | Long aday (güncel rejim) | Alınan (güncel rejim) | Long aday (tüm kayıt) | Alınan (tüm kayıt) | Veri |
|---|---|---|---|---|---|
| T1@15m | 0 | 0 | 22 | 0 | veri: 24.11.2026 06:30 TSİ |
| T1@1h | 0 | 0 | 9 | 1 | veri: 24.11.2026 03:00 TSİ |
| T1@4h | 0 | 0 | 4 | 0 | veri: 24.11.2026 03:00 TSİ |
| R1@15m | 0 | 0 | 30 | 0 | veri: 20.11.2026 10:45 TSİ |
| R1@1h | 0 | 0 | 15 | 0 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 0 | 0 | 11 | 0 | veri: 20.11.2026 11:00 TSİ |
| TF1@15m | 0 | 0 | 11 | 0 | veri: 24.11.2026 06:30 TSİ |
| TF1@1h | 0 | 0 | 5 | 0 | veri: 23.11.2026 23:00 TSİ |
| TF1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 19:00 TSİ |
| B1@15m | 0 | 0 | 1 | 0 | veri: 23.11.2026 21:30 TSİ |
| B1@1h | 0 | 0 | 2 | 0 | veri: 23.11.2026 06:00 TSİ |
| H2@15m | 0 | 0 | 10 | 0 | veri: 24.11.2026 02:30 TSİ |
| H2@1h | 0 | 0 | 3 | 0 | veri: 24.11.2026 05:00 TSİ |
| H2@4h | 0 | 0 | 1 | 0 | veri: 21.11.2026 23:00 TSİ |
| S1@15m | 0 | 0 | 32 | 3 | veri: 24.11.2026 00:15 TSİ |
| S1@1h | 0 | 0 | 5 | 0 | veri: 22.11.2026 13:00 TSİ |
| S1@4h | 0 | 0 | 3 | 0 | veri: 23.11.2026 07:00 TSİ |
| F1@15m | 0 | 0 | 50 | 3 | veri: 24.11.2026 09:15 TSİ |
| F1@1h | 0 | 0 | 17 | 0 | veri: 23.11.2026 14:00 TSİ |
| F1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 03:00 TSİ |
| M1@1h | 107 | 1 | 110 | 1 | veri: 23.11.2026 04:00 TSİ |
| M1@15m | 32 | 0 | 33 | 0 | veri: 23.11.2026 17:15 TSİ |

## ML 12 — Kâğıt / geri test tutarlılığı

Toplam kâğıt R (n=65): -5,09 R (veri: 24.11.2026 08:34 TSİ). Yayımlanmış bant (n=65 için aradeğer): %2,5=-29,5 · %10=-20,5 · ortanca=+1,3 · %90=+34,4. Konum: %10-%90 arası (bant içinde). Kaynak: docs/kagit-degerlendirme-plani.md §4.4 (kümülatif net R, referans bootstrap bandı).

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
