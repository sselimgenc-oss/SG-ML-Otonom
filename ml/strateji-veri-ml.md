# [ML] Strateji verisi (beyin fırtınası için)

Üretim: 24.11.2026 16:50 TSİ · Kâğıt başlangıcı (ilk kayıt): 17.11.2026 18:00 TSİ · Veri kesiti: 24.11.2026 16:45 TSİ
Kapanan işlem: 71 · Açık işlem: 6 · Karar kaydı: 4120 · Yapılandırılmış kol: 37
Kapsam: yalnız kâğıt defteri (salt okunur). Kilitli dönem (01.05.2026-01.11.2026) kayıtları okunmadı/ayıklandı (ayıklanan kayıt: 0). Yeni geri test hesaplanmadı. Yorum/öneri yok.

## Ortak 1 — Kâğıt başlangıcından beri sonuç

| Ölçü | Değer | Veri |
|---|---|---|
| Net K/Z | -$51,47 | veri: 24.11.2026 16:30 TSİ |
| İşlem sayısı (kapanan) | 71 | veri: 24.11.2026 16:30 TSİ |
| Kazanma oranı (net > 0) | %39,4 | veri: 24.11.2026 16:30 TSİ |
| Ort. kazanç | +1,09 R / +$9,39 | veri: 24.11.2026 16:30 TSİ |
| Ort. kayıp | -0,95 R / -$7,31 | veri: 24.11.2026 16:30 TSİ |
| Toplam R | -10,08 R | veri: 24.11.2026 16:30 TSİ |

## Ortak 2 — K/Z yoğunlaşması

| Ölçü | Değer | Veri |
|---|---|---|
| En iyi 1 işlemin net içindeki payı | - (+$41,53) | veri: 24.11.2026 16:30 TSİ |
| En iyi 2 işlemin net içindeki payı | - (+$73,56) | veri: 24.11.2026 16:30 TSİ |
| En iyi 3 çıkarılınca net | -$150,12 | veri: 24.11.2026 16:30 TSİ |
| En kötü 3 çıkarılınca net | -$12,54 | veri: 24.11.2026 16:30 TSİ |
| En iyi 3 + en kötü 3 çıkarılınca net | -$111,19 | veri: 24.11.2026 16:30 TSİ |

Pay: net > 0 iken hesaplanır; yetersiz işlemde (en iyi/kötü 3 için < 4, ikisi birden < 7) '-'.

## Ortak 3 — Maliyetler

| Kalem | Tutar | Brüt kâra oranı | Veri |
|---|---|---|---|
| Brüt kâr (yalnız brüt > 0 olan işlemlerin toplamı) | $285,57 | - | veri: 24.11.2026 16:30 TSİ |
| Toplam brüt K/Z (tüm işlemler) | -$1,15 | - | veri: 24.11.2026 16:30 TSİ |
| Komisyon | $51,60 | %18,1 | veri: 24.11.2026 16:30 TSİ |
| Fonlama (ödenen) | -$1,28 | %0,4 | veri: 24.11.2026 16:30 TSİ |
| Komisyon + fonlama | $50,32 | %17,6 | veri: 24.11.2026 16:30 TSİ |
| Kayma (giriş+çıkış, planlanana göre; brüte ZATEN işlenmiştir) | +$83,27 | %29,2 | veri: 24.11.2026 16:30 TSİ |
| Komisyon + fonlama + kayma | $133,59 | %46,8 | veri: 24.11.2026 16:30 TSİ |

Net K/Z = brüt - komisyon - fonlama (kayma fiyatlara işlendiğinden ayrıca düşülmez).

## Ortak 6 — Girişteki piyasa rejimine göre sonuç

| Rejim | İşlem | Net K/Z | Kazanma | Veri |
|---|---|---|---|---|
| trend_up | 5 | -$20,82 | %20,0 | veri: 24.11.2026 16:30 TSİ |
| trend_down | 59 | -$8,40 | %42,4 | veri: 24.11.2026 16:30 TSİ |
| range | 3 | -$26,98 | %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 4 | +$4,73 | %50,0 | veri: 24.11.2026 13:30 TSİ |
| volatile | 0 | - | - | veri: işlem yok |

## Ortak 7 — 30 / 100 / 300 kapanan işleme ulaşma süresi

Süre: 6,9 gün (17.11.2026 18:00 TSİ → 24.11.2026 16:45 TSİ); kapanan 71; genel hız 10,22 işlem/gün; kol medyan hızı: işlemi olan 15 kol 0,576 işlem/gün, tüm 37 yapılandırılmış kol 0,000 işlem/gün (veri: 24.11.2026 16:45 TSİ).

| Hedef | Genel (güncel hızla) | Kol medyanı (işlemi olan kollar) | Kol medyanı (tüm kollar) | Hedefe ulaşan kol | Veri |
|---|---|---|---|---|---|
| 30 | ulaşıldı | 52 gün (7,4 hafta) | hesaplanamaz (hız 0) | 0 | veri: 24.11.2026 16:45 TSİ |
| 100 | 3 gün (0,4 hafta) | 174 gün (24,8 hafta) | hesaplanamaz (hız 0) | 0 | veri: 24.11.2026 16:45 TSİ |
| 300 | 22 gün (3,2 hafta) | 521 gün (74,4 hafta) | hesaplanamaz (hız 0) | 0 | veri: 24.11.2026 16:45 TSİ |

## ML 8 — Yapılandırılmış kollar: işlem açan / açmayan

Yapılandırılmış kol: 37 · ≥1 işlem açan: 18 · hiç açmayan: 19 (veri: 24.11.2026 16:45 TSİ)

| Kol | Aday (karar kaydı) | En sık skip_reason | Grup (filtre/rejim/veri/eşik/risk-limit) | Veri |
|---|---|---|---|---|
| T1@4h | 29 | stop_width=24, risk_denied=4, ml_filter=1 | eşik=24, risk/limit=4, filtre=1 | veri: 24.11.2026 15:00 TSİ |
| T1@1d | 1 | stop_width=1 | eşik=1 | veri: 20.11.2026 03:00 TSİ |
| R1@15m | 33 | risk_denied=30, etiket_duygu=3 | risk/limit=30, filtre=3 | veri: 24.11.2026 14:30 TSİ |
| R1@1h | 16 | risk_denied=11, etiket_duygu=3, arm_conflict=2 | risk/limit=13, filtre=3 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 11 | rr_below_min=9, etiket_duygu=2 | eşik=9, filtre=2 | veri: 20.11.2026 11:00 TSİ |
| R1@1d | 0 (aday üretmedi) | - | - | veri: 24.11.2026 16:45 TSİ |
| TF1@1h | 35 | risk_denied=28, arm_conflict=5, etiket_duygu=2 | risk/limit=33, filtre=2 | veri: 24.11.2026 16:00 TSİ |
| TF1@4h | 14 | risk_denied=10, etiket_duygu=2, cluster_cap=2 | risk/limit=12, filtre=2 | veri: 23.11.2026 19:00 TSİ |
| B1@4h | 2 | risk_denied=2 | risk/limit=2 | veri: 24.11.2026 07:00 TSİ |
| S1@1d | 4 | stop_width=3, arm_conflict=1 | eşik=3, risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| F1@1h | 78 | risk_denied=51, stop_width=10, arm_conflict=8, rr_below_min=8, etiket_duygu=1 | risk/limit=59, eşik=18, filtre=1 | veri: 24.11.2026 15:00 TSİ |
| F1@4h | 5 | stop_width=3, risk_denied=1, rr_below_min=1 | eşik=4, risk/limit=1 | veri: 23.11.2026 23:00 TSİ |
| F1@1d | 0 (aday üretmedi) | - | - | veri: 24.11.2026 16:45 TSİ |
| M1@1d | 1 | risk_denied=1 | risk/limit=1 | veri: 24.11.2026 03:00 TSİ |
| HB1@1h | 0 (aday üretmedi) | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@15m | 0 (aday üretmedi) | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@1h | 0 (aday üretmedi) | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@4h | 0 (aday üretmedi) | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@1d | 0 (aday üretmedi) | - | - | veri: 24.11.2026 16:45 TSİ |

Açan kollar: T1@15m, T1@1h, TF1@15m, TF1@1d, B1@15m, B1@1h, B1@1d, H2@15m, H2@1h, H2@4h, H2@1d, S1@15m, S1@1h, S1@4h, F1@15m, M1@1h, M1@4h, M1@15m

### Kol bazında neden işlem açmıyor (tüm kayıt / son 12 saat)

Pencere: «tüm kayıt» = kilitli dönem dışındaki tüm karar satırları; «son 12 saat» = veri kesitinden (24.11.2026 16:45 TSİ) geriye 12 saat. Kâğıt risk limitleri kayıt süresince gevşetilmiş olabilir; eski `risk_denied` sayıları o günkü limitlere aittir, güncel durumu «son 12 saat» sütunları gösterir. Risk reddi `risk_reason` metninden limit adına çevrilir (max_open_risk, max_same_dir_risk, daily_max_loss ...).

| Kol | Aday (tüm) | Girdi (tüm) | Skip (tüm) | Aday (12s) | Girdi (12s) | Skip (12s) | Veri |
|---|---|---|---|---|---|---|---|
| T1@15m | 565 | 9 | stop_width=295; risk_denied=212 (margin_total=112, daily_max_loss=44, max_same_dir_risk=31, daily_limit=19, korelasyon_grubu=4, diğer=2); ml_filter=39; arm_conflict=6 (M1@1h=3, T1@1h=1, M1@4h=1); order_failed=2; etiket_duygu=2 | 81 | 2 | stop_width=46; risk_denied=31 (max_same_dir_risk=22, korelasyon_grubu=4, margin_total=3, diğer=2); ml_filter=2 | veri: 24.11.2026 16:45 TSİ |
| T1@1h | 157 | 10 | stop_width=73; risk_denied=51 (margin_total=31, daily_max_loss=10, max_same_dir_risk=8, korelasyon_grubu=2); ml_filter=19; veto_blocked=3; veto_missing=1 | 23 | 0 | risk_denied=10 (max_same_dir_risk=8, korelasyon_grubu=2); ml_filter=8; stop_width=5 | veri: 24.11.2026 16:45 TSİ |
| T1@4h | 29 | 0 | stop_width=24; risk_denied=4 (max_same_dir_risk=2, daily_max_loss=1, margin_total=1); ml_filter=1 | 3 | 0 | risk_denied=2 (max_same_dir_risk=2); stop_width=1 | veri: 24.11.2026 16:45 TSİ |
| T1@1d | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| R1@15m | 33 | 0 | risk_denied=30 (margin_total=27, diğer=2, daily_max_loss=1); etiket_duygu=3 | 2 | 0 | risk_denied=2 (diğer=2) | veri: 24.11.2026 16:45 TSİ |
| R1@1h | 16 | 0 | risk_denied=11 (margin_total=9, daily_max_loss=2); etiket_duygu=3; arm_conflict=2 (R1@4h=1) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| R1@4h | 11 | 0 | rr_below_min=9; etiket_duygu=2 | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| R1@1d | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| TF1@15m | 140 | 4 | risk_denied=110 (margin_total=52, max_same_dir_risk=29, daily_max_loss=20, daily_limit=8, korelasyon_grubu=1); arm_conflict=14 (TF1@1h=4, T1@1h=4, M1@1h=3, TF1@4h=1, S1@1h=1, H2@1h=1); etiket_duygu=6; cluster_cap=6 (hisse_teknoloji=6) | 24 | 1 | risk_denied=18 (max_same_dir_risk=16, margin_total=1, korelasyon_grubu=1); arm_conflict=5 (T1@1h=4, H2@1h=1) | veri: 24.11.2026 16:45 TSİ |
| TF1@1h | 35 | 0 | risk_denied=28 (margin_total=12, daily_max_loss=8, max_same_dir_risk=5, daily_limit=3); arm_conflict=5 (TF1@4h=2, M1@4h=2, S1@4h=1); etiket_duygu=2 | 3 | 0 | risk_denied=3 (max_same_dir_risk=3) | veri: 24.11.2026 16:45 TSİ |
| TF1@4h | 14 | 0 | risk_denied=10 (daily_max_loss=6, max_same_dir_risk=2, margin_total=1, daily_limit=1); etiket_duygu=2; cluster_cap=2 (hisse_teknoloji=2) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| TF1@1d | 7 | 2 | risk_denied=5 (margin_total=2, daily_max_loss=2, max_same_dir_risk=1) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| B1@15m | 39 | 1 | risk_denied=20 (margin_total=9, daily_max_loss=7, max_same_dir_risk=3, daily_limit=1); stop_width=15; arm_conflict=2 (TF1@1h=2); entry_gate_closed=1 | 9 | 0 | stop_width=6; risk_denied=3 (max_same_dir_risk=3) | veri: 24.11.2026 16:45 TSİ |
| B1@1h | 13 | 2 | risk_denied=8 (margin_total=4, daily_max_loss=4); arm_conflict=2 (TF1@4h=1, M1@4h=1); stop_width=1 | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| B1@4h | 2 | 0 | risk_denied=2 (margin_total=1, max_same_dir_risk=1) | 1 | 0 | risk_denied=1 (max_same_dir_risk=1) | veri: 24.11.2026 16:45 TSİ |
| B1@1d | 2 | 1 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| H2@15m | 168 | 4 | risk_denied=117 (margin_total=46, daily_max_loss=34, max_same_dir_risk=22, daily_limit=11, korelasyon_grubu=4); stop_width=30; arm_conflict=15 (TF1@15m=10, M1@1h=1, M1@4h=1, T1@15m=1, TF1@1h=1); entry_gate_closed=1; order_failed=1 | 33 | 2 | risk_denied=18 (max_same_dir_risk=13, korelasyon_grubu=4, margin_total=1); stop_width=11; arm_conflict=2 (TF1@1h=1, TF1@15m=1) | veri: 24.11.2026 16:45 TSİ |
| H2@1h | 49 | 1 | risk_denied=34 (margin_total=24, daily_max_loss=7, max_same_dir_risk=3); stop_width=8; arm_conflict=5 (H2@4h=2, TF1@1h=1, TF1@4h=1, M1@4h=1); etiket_duygu=1 | 1 | 0 | risk_denied=1 (margin_total=1) | veri: 24.11.2026 16:45 TSİ |
| H2@4h | 18 | 1 | risk_denied=15 (margin_total=10, daily_max_loss=5); stop_width=2 | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| H2@1d | 3 | 1 | arm_conflict=1 (TF1@1d=1); risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| S1@15m | 415 | 8 | risk_denied=184 (margin_total=99, daily_max_loss=34, max_same_dir_risk=31, daily_limit=18, diğer=1, korelasyon_grubu=1); stop_width=168; arm_conflict=45 (TF1@15m=15, T1@15m=14, M1@1h=5, H2@15m=4, T1@1h=2, B1@15m=1, TF1@1h=1, S1@1h=1, F1@1h=1); etiket_duygu=7; cluster_cap=3 (hisse_teknoloji=3) | 59 | 0 | stop_width=34; risk_denied=21 (max_same_dir_risk=18, diğer=1, margin_total=1, korelasyon_grubu=1); arm_conflict=4 (TF1@15m=2, T1@1h=1, H2@15m=1) | veri: 24.11.2026 16:45 TSİ |
| S1@1h | 80 | 3 | risk_denied=35 (margin_total=26, max_same_dir_risk=5, daily_max_loss=4); stop_width=31; arm_conflict=10 (T1@1h=3, H2@1h=2, H2@4h=2, T1@4h=1, TF1@4h=1, TF1@1h=1); order_failed=1 | 10 | 0 | stop_width=6; risk_denied=3 (max_same_dir_risk=3); arm_conflict=1 (T1@1h=1) | veri: 24.11.2026 16:45 TSİ |
| S1@4h | 17 | 1 | stop_width=9; risk_denied=4 (margin_total=2, daily_max_loss=1, daily_limit=1); arm_conflict=3 (TF1@4h=2, H2@1d=1) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| S1@1d | 4 | 0 | stop_width=3; arm_conflict=1 (TF1@1d=1) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| F1@15m | 305 | 12 | risk_denied=156 (margin_total=117, daily_max_loss=20, max_same_dir_risk=7, daily_limit=6, diğer=6); stop_width=74; rr_below_min=37; arm_conflict=15 (M1@1h=7, R1@15m=3, M1@4h=3, T1@1h=2); etiket_duygu=7; entry_gate_closed=3; cluster_cap=1 (hisse_teknoloji=1) | 25 | 5 | risk_denied=13 (diğer=6, max_same_dir_risk=5, margin_total=2); rr_below_min=4; stop_width=2; arm_conflict=1 (T1@1h=1) | veri: 24.11.2026 16:45 TSİ |
| F1@1h | 78 | 0 | risk_denied=51 (margin_total=40, daily_max_loss=5, daily_limit=2, max_same_dir_risk=2, diğer=2); stop_width=10; arm_conflict=8 (R1@1h=4, M1@4h=4); rr_below_min=8; etiket_duygu=1 | 5 | 0 | risk_denied=4 (max_same_dir_risk=2, diğer=2); arm_conflict=1 (M1@4h=1) | veri: 24.11.2026 16:45 TSİ |
| F1@4h | 5 | 0 | stop_width=3; risk_denied=1 (daily_max_loss=1); rr_below_min=1 | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| F1@1d | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| M1@1h | 423 | 4 | risk_denied=250 (margin_total=224, daily_max_loss=21, diğer=5); etiket_rejim=116; arm_conflict=53 (S1@1h=16, F1@1h=12, T1@1h=10, M1@4h=8, H2@4h=3, TF1@4h=1, B1@1h=1, TF1@1h=1, B1@1d=1) | 5 | 0 | risk_denied=5 (diğer=5) | veri: 24.11.2026 16:45 TSİ |
| M1@4h | 124 | 2 | risk_denied=114 (margin_total=73, daily_limit=17, max_same_dir_risk=15, diğer=7, daily_max_loss=2); arm_conflict=8 (H2@4h=2, S1@4h=2, R1@4h=1, H2@1d=1, T1@4h=1, M1@1d=1) | 12 | 0 | risk_denied=12 (max_same_dir_risk=7, diğer=5) | veri: 24.11.2026 16:45 TSİ |
| M1@15m | 1366 | 11 | risk_denied=1161 (margin_total=465, daily_max_loss=214, max_same_dir_risk=203, daily_limit=193, diğer=67, korelasyon_grubu=18, toplam_buyukluk=1); arm_conflict=93 (S1@15m=29, T1@15m=18, M1@1h=14, T1@1h=9, H2@15m=6, H2@1h=4, TF1@15m=4, F1@15m=4, M1@4h=4, TF1@4h=1); etiket_rejim=89; order_failed=12 | 118 | 3 | risk_denied=100 (max_same_dir_risk=48, diğer=42, margin_total=6, korelasyon_grubu=3, toplam_buyukluk=1); arm_conflict=15 (T1@15m=7, T1@1h=2, S1@15m=2, H2@1h=1, TF1@15m=1, H2@15m=1, F1@15m=1) | veri: 24.11.2026 16:45 TSİ |
| M1@1d | 1 | 0 | risk_denied=1 (diğer=1) | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| HB1@1h | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| DL1@15m | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| DL1@1h | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| DL1@4h | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |
| DL1@1d | 0 | 0 | - | 0 | 0 | - | veri: 24.11.2026 16:45 TSİ |

Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta R1@1d, F1@1d, HB1@1h, DL1@15m, DL1@1h, DL1@4h, DL1@1d · yalnız son 12 saatte T1@1d, R1@1h, R1@4h, TF1@4h, TF1@1d, B1@1h, B1@1d, H2@4h, H2@1d, S1@4h, S1@1d, F1@4h, M1@1d.

Aday = `decision_events` satırı. Golge kararlar (shadow) ve hiç kayda girmeyen sinyaller bu sayıya girmez.

### stop_width skip'leri: dar / geniş (son 12 saat / tüm kayıt)

İzinli bant: stop/ATR 0.5 – 2.0 (signals.STOP_DIST_MIN_ATR / STOP_DIST_MAX_ATR). Yalnız ölçüm; davranış değişmez. Dar/geniş ayrımı kayıtlı `features.stop_dist_atr` değerinin banta göre karşılaştırılmasından türetilir; medyan = reddedilen adayların medyan stop/ATR'si.

| Kol | Son 12s | Tüm kayıt | Veri |
|---|---|---|---|
| T1@15m | dar=0, geniş=46 · medyan 2.57 | dar=0, geniş=295 · medyan 2.75 | veri: 24.11.2026 16:45 TSİ |
| T1@1h | dar=0, geniş=5 · medyan 2.37 | dar=0, geniş=73 · medyan 2.51 | veri: 24.11.2026 16:45 TSİ |
| T1@4h | dar=0, geniş=1 · medyan 2.10 | dar=0, geniş=24 · medyan 2.49 | veri: 24.11.2026 16:45 TSİ |
| T1@1d | - | dar=0, geniş=1 · medyan 3.45 | veri: 24.11.2026 16:45 TSİ |
| R1@15m | - | - | veri: 24.11.2026 16:45 TSİ |
| R1@1h | - | - | veri: 24.11.2026 16:45 TSİ |
| R1@4h | - | - | veri: 24.11.2026 16:45 TSİ |
| R1@1d | - | - | veri: 24.11.2026 16:45 TSİ |
| TF1@15m | - | - | veri: 24.11.2026 16:45 TSİ |
| TF1@1h | - | - | veri: 24.11.2026 16:45 TSİ |
| TF1@4h | - | - | veri: 24.11.2026 16:45 TSİ |
| TF1@1d | - | - | veri: 24.11.2026 16:45 TSİ |
| B1@15m | dar=0, geniş=6 · medyan 3.73 | dar=0, geniş=15 · medyan 3.44 | veri: 24.11.2026 16:45 TSİ |
| B1@1h | - | dar=1, geniş=0 · medyan 0.43 | veri: 24.11.2026 16:45 TSİ |
| B1@4h | - | - | veri: 24.11.2026 16:45 TSİ |
| B1@1d | - | - | veri: 24.11.2026 16:45 TSİ |
| H2@15m | dar=0, geniş=11 · medyan 3.29 | dar=0, geniş=30 · medyan 2.95 | veri: 24.11.2026 16:45 TSİ |
| H2@1h | - | dar=0, geniş=8 · medyan 3.78 | veri: 24.11.2026 16:45 TSİ |
| H2@4h | - | dar=0, geniş=2 · medyan 3.48 | veri: 24.11.2026 16:45 TSİ |
| H2@1d | - | - | veri: 24.11.2026 16:45 TSİ |
| S1@15m | dar=0, geniş=34 · medyan 3.31 | dar=0, geniş=168 · medyan 3.35 | veri: 24.11.2026 16:45 TSİ |
| S1@1h | dar=0, geniş=6 · medyan 3.09 | dar=0, geniş=31 · medyan 3.44 | veri: 24.11.2026 16:45 TSİ |
| S1@4h | - | dar=0, geniş=9 · medyan 4.02 | veri: 24.11.2026 16:45 TSİ |
| S1@1d | - | dar=0, geniş=3 · medyan 3.48 | veri: 24.11.2026 16:45 TSİ |
| F1@15m | dar=0, geniş=2 · medyan 3.68 | dar=0, geniş=74 · medyan 2.48 | veri: 24.11.2026 16:45 TSİ |
| F1@1h | - | dar=0, geniş=10 · medyan 2.46 | veri: 24.11.2026 16:45 TSİ |
| F1@4h | - | dar=0, geniş=3 · medyan 2.77 | veri: 24.11.2026 16:45 TSİ |
| F1@1d | - | - | veri: 24.11.2026 16:45 TSİ |
| M1@1h | - | - | veri: 24.11.2026 16:45 TSİ |
| M1@4h | - | - | veri: 24.11.2026 16:45 TSİ |
| M1@15m | - | - | veri: 24.11.2026 16:45 TSİ |
| M1@1d | - | - | veri: 24.11.2026 16:45 TSİ |
| HB1@1h | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@15m | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@1h | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@4h | - | - | veri: 24.11.2026 16:45 TSİ |
| DL1@1d | - | - | veri: 24.11.2026 16:45 TSİ |

## ML 10 — Kol bazında sanal K/Z

| Kol | İşlem | Net $ | R toplamı | Kazanma | Durum | Veri |
|---|---|---|---|---|---|---|
| F1@15m | 12 | -$53,59 | -9,35 R | %8,3 | ZARARDA | veri: 24.11.2026 16:30 TSİ |
| S1@15m | 8 | -$36,18 | -3,29 R | %25,0 | ZARARDA | veri: 23.11.2026 17:15 TSİ |
| M1@1h | 4 | -$16,88 | -1,49 R | %50,0 | ZARARDA | veri: 23.11.2026 06:13 TSİ |
| T1@1h | 10 | -$15,27 | +0,44 R | %50,0 | ZARARDA | veri: 23.11.2026 03:57 TSİ |
| H2@1h | 1 | -$11,73 | -1,00 R | %0,0 | ZARARDA | veri: 21.11.2026 16:39 TSİ |
| H2@4h | 1 | -$10,70 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:57 TSİ |
| B1@1d | 1 | -$10,54 | -1,00 R | %0,0 | ZARARDA | veri: 23.11.2026 16:58 TSİ |
| M1@15m | 11 | -$5,97 | -2,25 R | %45,5 | ZARARDA | veri: 24.11.2026 08:15 TSİ |
| TF1@15m | 4 | -$3,49 | -0,89 R | %50,0 | ZARARDA | veri: 24.11.2026 16:30 TSİ |
| H2@15m | 4 | -$0,55 | -0,64 R | %50,0 | ZARARDA | veri: 24.11.2026 09:50 TSİ |
| B1@15m | 1 | +$3,39 | +0,73 R | %100,0 | kârda/başa baş | veri: 19.11.2026 20:15 TSİ |
| M1@4h | 2 | +$9,87 | +0,96 R | %50,0 | kârda/başa baş | veri: 23.11.2026 16:55 TSİ |
| B1@1h | 2 | +$13,14 | +1,35 R | %50,0 | kârda/başa baş | veri: 21.11.2026 14:31 TSİ |
| S1@1h | 3 | +$13,71 | +1,44 R | %66,7 | kârda/başa baş | veri: 23.11.2026 13:41 TSİ |
| T1@15m | 7 | +$73,30 | +5,92 R | %57,1 | kârda/başa baş | veri: 24.11.2026 04:10 TSİ |
| B1@4h | 0 | - | - | - | - | veri: işlem yok |
| DL1@15m | 0 | - | - | - | - | veri: işlem yok |
| DL1@1d | 0 | - | - | - | - | veri: işlem yok |
| DL1@1h | 0 | - | - | - | - | veri: işlem yok |
| DL1@4h | 0 | - | - | - | - | veri: işlem yok |
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
| Ders: kol kapatma (arms_off) | var | yalnız karne/rapor bilgisi; giriş ENGELLENMEZ (sahip kararı, 19 Kasım; gates.py `arm_would_close` sayacı) | tetiklendi: B1@15m, B1@1d, F1@15m, F1@1h, H2@15m, H2@1h, H2@4h, M1@15m, R1@15m, R1@1h, S1@15m, T1@15m, TF1@15m | okuma: 24.11.2026 16:50 TSİ |
| Ders: 10 R freni (lesson_brake) | var | ders ayarlarını referansa döndürür, otomatik uygulamayı durdurur; kolu kapatmaz | tetiklenmedi | okuma: 24.11.2026 16:50 TSİ |
| Kol başına açık pozisyon tavanı (arm_max_positions) ve küme/hesap tavanı | var | kayıptan bağımsız konum sınırı; zarardaki kolu özel olarak ayırmaz | kayıp temelli tetik değil | okuma: 24.11.2026 16:50 TSİ |
| Risk kademe denetimi (risk_ladder, hesap düzeyi küçültme) | var (hesap düzeyi; kol düzeyi değil) | tepe-denge düşüşünde hedef işlem riskini kademeli düşürür / durdurur; motor zorunlu yalnız canlı modda | kâğıt ayarında LADDER_BOTS boş; kâğıtta kademe izlenmez | okuma: 24.11.2026 16:50 TSİ |
| Kol bazında otomatik karantina / boyut küçültme | yok | zararda kol: F1@15m, S1@15m, M1@1h, T1@1h, H2@1h, H2@4h, B1@1d, M1@15m, TF1@15m, H2@15m; bu kolları kendiliğinden kısan kural yok | - | okuma: 24.11.2026 16:50 TSİ |

## ML 11 — Long/short dağılımı

| Yön | İşlem | Net $ | Kazanma | R | Veri |
|---|---|---|---|---|---|
| long | 11 | -$31,34 | %27,3 | -5,22 R | veri: 24.11.2026 16:30 TSİ |
| short | 60 | -$20,13 | %41,7 | -4,86 R | veri: 24.11.2026 16:30 TSİ |

| Rejim | Long (n / net $ / kazanma) | Short (n / net $ / kazanma) | Veri |
|---|---|---|---|
| trend_up | 5 / -$20,82 / %20,0 | 0 / - / - | veri: 24.11.2026 16:30 TSİ |
| trend_down | 1 / +$4,86 / %100,0 | 58 / -$13,26 / %41,4 | veri: 24.11.2026 16:30 TSİ |
| range | 2 / -$19,65 / %0,0 | 1 / -$7,33 / %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 3 / +$4,27 / %33,3 | 1 / +$0,45 / %100,0 | veri: 24.11.2026 13:30 TSİ |
| volatile | 0 / - / - | 0 / - / - | veri: işlem yok |

Güncel rejim (son karar zamanından geriye 24 saatte en sık rejim; 1060 karar): trend_down (veri: 24.11.2026 16:45 TSİ)
Long-yetkin kollar (kayıtta ≥1 long adayı olanlar) bu rejimde: aday 143 · alınan 1

| Kol | Long aday (güncel rejim) | Alınan (güncel rejim) | Long aday (tüm kayıt) | Alınan (tüm kayıt) | Veri |
|---|---|---|---|---|---|
| T1@15m | 0 | 0 | 25 | 0 | veri: 24.11.2026 15:45 TSİ |
| T1@1h | 0 | 0 | 9 | 1 | veri: 24.11.2026 03:00 TSİ |
| T1@4h | 0 | 0 | 4 | 0 | veri: 24.11.2026 03:00 TSİ |
| R1@15m | 0 | 0 | 32 | 0 | veri: 24.11.2026 14:30 TSİ |
| R1@1h | 0 | 0 | 15 | 0 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 0 | 0 | 11 | 0 | veri: 20.11.2026 11:00 TSİ |
| TF1@15m | 0 | 0 | 12 | 1 | veri: 24.11.2026 12:15 TSİ |
| TF1@1h | 0 | 0 | 5 | 0 | veri: 23.11.2026 23:00 TSİ |
| TF1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 19:00 TSİ |
| B1@15m | 0 | 0 | 1 | 0 | veri: 23.11.2026 21:30 TSİ |
| B1@1h | 0 | 0 | 2 | 0 | veri: 23.11.2026 06:00 TSİ |
| H2@15m | 0 | 0 | 10 | 0 | veri: 24.11.2026 02:30 TSİ |
| H2@1h | 0 | 0 | 3 | 0 | veri: 24.11.2026 05:00 TSİ |
| H2@4h | 0 | 0 | 1 | 0 | veri: 21.11.2026 23:00 TSİ |
| S1@15m | 0 | 0 | 35 | 3 | veri: 24.11.2026 12:15 TSİ |
| S1@1h | 0 | 0 | 5 | 0 | veri: 22.11.2026 13:00 TSİ |
| S1@4h | 0 | 0 | 3 | 0 | veri: 23.11.2026 07:00 TSİ |
| F1@15m | 0 | 0 | 55 | 5 | veri: 24.11.2026 14:30 TSİ |
| F1@1h | 0 | 0 | 18 | 0 | veri: 24.11.2026 15:00 TSİ |
| F1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 03:00 TSİ |
| M1@1h | 107 | 1 | 110 | 1 | veri: 23.11.2026 04:00 TSİ |
| M1@15m | 36 | 0 | 37 | 0 | veri: 24.11.2026 13:15 TSİ |

## ML 12 — Kâğıt / geri test tutarlılığı

Toplam kâğıt R (n=71): -10,08 R (veri: 24.11.2026 16:30 TSİ). Yayımlanmış bant (n=71 için aradeğer): %2,5=-31,1 · %10=-21,4 · ortanca=+1,7 · %90=+36,3. Konum: %10-%90 arası (bant içinde). Kaynak: docs/kagit-degerlendirme-plani.md §4.4 (kümülatif net R, referans bootstrap bandı).

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
