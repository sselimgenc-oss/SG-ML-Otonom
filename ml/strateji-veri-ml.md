# [ML] Strateji verisi (beyin fırtınası için)

Üretim: 22.11.2026 22:34 TSİ · Kâğıt başlangıcı (ilk kayıt): 17.11.2026 18:00 TSİ · Veri kesiti: 22.11.2026 22:30 TSİ
Kapanan işlem: 40 · Açık işlem: 6 · Karar kaydı: 2475 · Yapılandırılmış kol: 32
Kapsam: yalnız kâğıt defteri (salt okunur). Kilitli dönem (01.05.2026-01.11.2026) kayıtları okunmadı/ayıklandı (ayıklanan kayıt: 0). Yeni geri test hesaplanmadı. Yorum/öneri yok.

## Ortak 1 — Kâğıt başlangıcından beri sonuç

| Ölçü | Değer | Veri |
|---|---|---|
| Net K/Z | +$79,38 | veri: 22.11.2026 17:23 TSİ |
| İşlem sayısı (kapanan) | 40 | veri: 22.11.2026 17:23 TSİ |
| Kazanma oranı (net > 0) | %50,0 | veri: 22.11.2026 17:23 TSİ |
| Ort. kazanç | +1,39 R / +$12,50 | veri: 22.11.2026 17:23 TSİ |
| Ort. kayıp | -0,99 R / -$8,53 | veri: 22.11.2026 17:23 TSİ |
| Toplam R | +7,91 R | veri: 22.11.2026 17:23 TSİ |

## Ortak 2 — K/Z yoğunlaşması

| Ölçü | Değer | Veri |
|---|---|---|
| En iyi 1 işlemin net içindeki payı | %52,3 (+$41,53) | veri: 22.11.2026 17:23 TSİ |
| En iyi 2 işlemin net içindeki payı | %92,7 (+$73,56) | veri: 22.11.2026 17:23 TSİ |
| En iyi 3 çıkarılınca net | -$19,27 | veri: 22.11.2026 17:23 TSİ |
| En kötü 3 çıkarılınca net | +$118,29 | veri: 22.11.2026 17:23 TSİ |
| En iyi 3 + en kötü 3 çıkarılınca net | +$19,64 | veri: 22.11.2026 17:23 TSİ |

Pay: net > 0 iken hesaplanır; yetersiz işlemde (en iyi/kötü 3 için < 4, ikisi birden < 7) '-'.

## Ortak 3 — Maliyetler

| Kalem | Tutar | Brüt kâra oranı | Veri |
|---|---|---|---|
| Brüt kâr (yalnız brüt > 0 olan işlemlerin toplamı) | $265,97 | - | veri: 22.11.2026 17:23 TSİ |
| Toplam brüt K/Z (tüm işlemler) | +$108,94 | - | veri: 22.11.2026 17:23 TSİ |
| Komisyon | $30,17 | %11,3 | veri: 22.11.2026 17:23 TSİ |
| Fonlama (ödenen) | -$0,61 | %0,2 | veri: 22.11.2026 17:23 TSİ |
| Komisyon + fonlama | $29,56 | %11,1 | veri: 22.11.2026 17:23 TSİ |
| Kayma (giriş+çıkış, planlanana göre; brüte ZATEN işlenmiştir) | +$49,24 | %18,5 | veri: 22.11.2026 17:23 TSİ |
| Komisyon + fonlama + kayma | $78,80 | %29,6 | veri: 22.11.2026 17:23 TSİ |

Net K/Z = brüt - komisyon - fonlama (kayma fiyatlara işlendiğinden ayrıca düşülmez).

## Ortak 6 — Girişteki piyasa rejimine göre sonuç

| Rejim | İşlem | Net K/Z | Kazanma | Veri |
|---|---|---|---|---|
| trend_up | 2 | -$8,50 | %50,0 | veri: 22.11.2026 13:30 TSİ |
| trend_down | 34 | +$106,67 | %52,9 | veri: 22.11.2026 17:23 TSİ |
| range | 3 | -$26,98 | %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 1 | +$8,20 | %100,0 | veri: 20.11.2026 05:45 TSİ |
| volatile | 0 | - | - | veri: işlem yok |

## Ortak 7 — 30 / 100 / 300 kapanan işleme ulaşma süresi

Süre: 5,2 gün (17.11.2026 18:00 TSİ → 22.11.2026 22:30 TSİ); kapanan 40; genel hız 7,71 işlem/gün; kol medyan hızı: işlemi olan 13 kol 0,386 işlem/gün, tüm 32 yapılandırılmış kol 0,000 işlem/gün (veri: 22.11.2026 22:30 TSİ).

| Hedef | Genel (güncel hızla) | Kol medyanı (işlemi olan kollar) | Kol medyanı (tüm kollar) | Hedefe ulaşan kol | Veri |
|---|---|---|---|---|---|
| 30 | ulaşıldı | 78 gün (11,1 hafta) | hesaplanamaz (hız 0) | 0 | veri: 22.11.2026 22:30 TSİ |
| 100 | 8 gün (1,1 hafta) | 259 gün (37,1 hafta) | hesaplanamaz (hız 0) | 0 | veri: 22.11.2026 22:30 TSİ |
| 300 | 34 gün (4,8 hafta) | 778 gün (111,2 hafta) | hesaplanamaz (hız 0) | 0 | veri: 22.11.2026 22:30 TSİ |

## ML 8 — Yapılandırılmış kollar: işlem açan / açmayan

Yapılandırılmış kol: 32 · ≥1 işlem açan: 15 · hiç açmayan: 17 (veri: 22.11.2026 22:30 TSİ)

| Kol | Aday (karar kaydı) | En sık skip_reason | Grup (filtre/rejim/veri/eşik/risk-limit) | Veri |
|---|---|---|---|---|
| T1@4h | 6 | stop_width=5, risk_denied=1 | eşik=5, risk/limit=1 | veri: 20.11.2026 19:00 TSİ |
| T1@1d | 1 | stop_width=1 | eşik=1 | veri: 20.11.2026 03:00 TSİ |
| R1@15m | 31 | risk_denied=28, etiket_duygu=3 | risk/limit=28, filtre=3 | veri: 20.11.2026 10:45 TSİ |
| R1@1h | 16 | risk_denied=11, etiket_duygu=3, arm_conflict=2 | risk/limit=13, filtre=3 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 11 | rr_below_min=9, etiket_duygu=2 | eşik=9, filtre=2 | veri: 20.11.2026 11:00 TSİ |
| R1@1d | 0 (aday üretmedi) | - | - | veri: 22.11.2026 22:30 TSİ |
| TF1@1h | 26 | risk_denied=20, arm_conflict=4, etiket_duygu=2 | risk/limit=24, filtre=2 | veri: 20.11.2026 19:00 TSİ |
| TF1@4h | 13 | risk_denied=9, etiket_duygu=2, cluster_cap=2 | risk/limit=11, filtre=2 | veri: 21.11.2026 07:00 TSİ |
| B1@4h | 1 | risk_denied=1 | risk/limit=1 | veri: 20.11.2026 07:00 TSİ |
| B1@1d | 1 | risk_denied=1 | risk/limit=1 | veri: 22.11.2026 03:00 TSİ |
| H2@4h | 17 | risk_denied=15, stop_width=2 | risk/limit=15, eşik=2 | veri: 22.11.2026 07:00 TSİ |
| S1@4h | 11 | stop_width=8, arm_conflict=2, risk_denied=1 | eşik=8, risk/limit=3 | veri: 20.11.2026 19:00 TSİ |
| S1@1d | 3 | stop_width=3 | eşik=3 | veri: 21.11.2026 03:00 TSİ |
| F1@1h | 42 | risk_denied=26, rr_below_min=6, stop_width=5, arm_conflict=4, etiket_duygu=1 | risk/limit=30, eşik=11, filtre=1 | veri: 22.11.2026 22:00 TSİ |
| F1@4h | 2 | risk_denied=1, rr_below_min=1 | risk/limit=1, eşik=1 | veri: 20.11.2026 03:00 TSİ |
| F1@1d | 0 (aday üretmedi) | - | - | veri: 22.11.2026 22:30 TSİ |
| M1@1d | 0 (aday üretmedi) | - | - | veri: 22.11.2026 22:30 TSİ |

Açan kollar: T1@15m, T1@1h, TF1@15m, TF1@1d, B1@15m, B1@1h, H2@15m, H2@1h, H2@1d, S1@15m, S1@1h, F1@15m, M1@1h, M1@4h, M1@15m

### Kol bazında neden işlem açmıyor (tüm kayıt / son 12 saat)

Pencere: «tüm kayıt» = kilitli dönem dışındaki tüm karar satırları; «son 12 saat» = veri kesitinden (22.11.2026 22:30 TSİ) geriye 12 saat. Kâğıt risk limitleri kayıt süresince gevşetilmiş olabilir; eski `risk_denied` sayıları o günkü limitlere aittir, güncel durumu «son 12 saat» sütunları gösterir. Risk reddi `risk_reason` metninden limit adına çevrilir (max_open_risk, max_same_dir_risk, daily_max_loss ...).

| Kol | Aday (tüm) | Girdi (tüm) | Skip (tüm) | Aday (12s) | Girdi (12s) | Skip (12s) | Veri |
|---|---|---|---|---|---|---|---|
| T1@15m | 310 | 4 | stop_width=146; risk_denied=142 (margin_total=91, daily_max_loss=44, max_same_dir_risk=7); ml_filter=10; arm_conflict=4 (M1@1h=3); order_failed=2; etiket_duygu=2 | 42 | 0 | stop_width=18; risk_denied=13 (margin_total=13); ml_filter=10; arm_conflict=1 (M1@1h=1) | veri: 22.11.2026 22:30 TSİ |
| T1@1h | 86 | 10 | stop_width=35; risk_denied=31 (margin_total=21, daily_max_loss=10); ml_filter=6; veto_blocked=3; veto_missing=1 | 11 | 0 | ml_filter=4; risk_denied=4 (margin_total=4); stop_width=3 | veri: 22.11.2026 22:30 TSİ |
| T1@4h | 6 | 0 | stop_width=5; risk_denied=1 (daily_max_loss=1) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| T1@1d | 1 | 0 | stop_width=1 | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| R1@15m | 31 | 0 | risk_denied=28 (margin_total=27, daily_max_loss=1); etiket_duygu=3 | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| R1@1h | 16 | 0 | risk_denied=11 (margin_total=9, daily_max_loss=2); etiket_duygu=3; arm_conflict=2 (R1@4h=1) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| R1@4h | 11 | 0 | rr_below_min=9; etiket_duygu=2 | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| R1@1d | 0 | 0 | - | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| TF1@15m | 90 | 2 | risk_denied=69 (margin_total=38, daily_max_loss=20, max_same_dir_risk=11); arm_conflict=7 (TF1@1h=3, M1@1h=2, TF1@4h=1, S1@1h=1); etiket_duygu=6; cluster_cap=6 (hisse_teknoloji=6) | 1 | 0 | risk_denied=1 (margin_total=1) | veri: 22.11.2026 22:30 TSİ |
| TF1@1h | 26 | 0 | risk_denied=20 (margin_total=10, daily_max_loss=8, max_same_dir_risk=2); arm_conflict=4 (TF1@4h=2, S1@4h=1, M1@4h=1); etiket_duygu=2 | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| TF1@4h | 13 | 0 | risk_denied=9 (daily_max_loss=6, max_same_dir_risk=2, margin_total=1); etiket_duygu=2; cluster_cap=2 (hisse_teknoloji=2) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| TF1@1d | 6 | 2 | risk_denied=4 (margin_total=2, daily_max_loss=2) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| B1@15m | 26 | 1 | risk_denied=15 (margin_total=8, daily_max_loss=7); stop_width=7; arm_conflict=2 (TF1@1h=2); entry_gate_closed=1 | 1 | 0 | risk_denied=1 (margin_total=1) | veri: 22.11.2026 22:30 TSİ |
| B1@1h | 10 | 2 | risk_denied=7 (daily_max_loss=4, margin_total=3); arm_conflict=1 (TF1@4h=1) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| B1@4h | 1 | 0 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| B1@1d | 1 | 0 | risk_denied=1 (margin_total=1) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| H2@15m | 116 | 2 | risk_denied=83 (margin_total=41, daily_max_loss=34, max_same_dir_risk=8); stop_width=18; arm_conflict=11 (TF1@15m=7, M1@1h=1, M1@4h=1, T1@15m=1); entry_gate_closed=1; order_failed=1 | 7 | 0 | risk_denied=5 (margin_total=5); arm_conflict=2 (M1@4h=1, T1@15m=1) | veri: 22.11.2026 22:30 TSİ |
| H2@1h | 46 | 1 | risk_denied=32 (margin_total=23, daily_max_loss=7, max_same_dir_risk=2); stop_width=7; arm_conflict=5 (H2@4h=2, TF1@1h=1, TF1@4h=1, M1@4h=1); etiket_duygu=1 | 1 | 0 | stop_width=1 | veri: 22.11.2026 22:30 TSİ |
| H2@4h | 17 | 0 | risk_denied=15 (margin_total=10, daily_max_loss=5); stop_width=2 | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| H2@1d | 2 | 1 | arm_conflict=1 (TF1@1d=1) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| S1@15m | 256 | 5 | risk_denied=114 (margin_total=72, daily_max_loss=34, max_same_dir_risk=8); stop_width=99; arm_conflict=28 (TF1@15m=11, T1@15m=6, M1@1h=4, H2@15m=2, T1@1h=1, B1@15m=1, TF1@1h=1, S1@1h=1); etiket_duygu=7; cluster_cap=3 (hisse_teknoloji=3) | 19 | 1 | risk_denied=9 (margin_total=9); stop_width=7; arm_conflict=2 (M1@1h=2) | veri: 22.11.2026 22:30 TSİ |
| S1@1h | 64 | 3 | risk_denied=27 (margin_total=21, daily_max_loss=4, max_same_dir_risk=2); stop_width=24; arm_conflict=9 (H2@1h=2, T1@1h=2, H2@4h=2, T1@4h=1, TF1@4h=1, TF1@1h=1); order_failed=1 | 1 | 0 | stop_width=1 | veri: 22.11.2026 22:30 TSİ |
| S1@4h | 11 | 0 | stop_width=8; arm_conflict=2 (TF1@4h=2); risk_denied=1 (daily_max_loss=1) | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| S1@1d | 3 | 0 | stop_width=3 | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| F1@15m | 200 | 5 | risk_denied=99 (margin_total=77, daily_max_loss=20, max_same_dir_risk=2); stop_width=59; rr_below_min=21; etiket_duygu=7; arm_conflict=5 (R1@15m=3, T1@1h=1, M1@1h=1); entry_gate_closed=3; cluster_cap=1 (hisse_teknoloji=1) | 54 | 1 | stop_width=27; risk_denied=23 (margin_total=23); rr_below_min=2; arm_conflict=1 (M1@1h=1) | veri: 22.11.2026 22:30 TSİ |
| F1@1h | 42 | 0 | risk_denied=26 (margin_total=21, daily_max_loss=5); rr_below_min=6; stop_width=5; arm_conflict=4 (R1@1h=4); etiket_duygu=1 | 18 | 0 | risk_denied=12 (margin_total=12); rr_below_min=5; stop_width=1 | veri: 22.11.2026 22:30 TSİ |
| F1@4h | 2 | 0 | risk_denied=1 (daily_max_loss=1); rr_below_min=1 | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| F1@1d | 0 | 0 | - | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |
| M1@1h | 329 | 3 | risk_denied=171 (margin_total=150, daily_max_loss=21); etiket_rejim=113; arm_conflict=42 (S1@1h=14, T1@1h=7, F1@1h=7, M1@4h=7, H2@4h=3, TF1@4h=1, B1@1h=1, TF1@1h=1, B1@1d=1) | 85 | 2 | risk_denied=47 (margin_total=47); etiket_rejim=23; arm_conflict=13 (M1@4h=6, F1@1h=6, T1@1h=1) | veri: 22.11.2026 22:30 TSİ |
| M1@4h | 33 | 1 | risk_denied=29 (margin_total=25, daily_max_loss=2, max_same_dir_risk=2); arm_conflict=3 (H2@4h=2, R1@4h=1) | 16 | 0 | risk_denied=16 (margin_total=16) | veri: 22.11.2026 22:30 TSİ |
| M1@15m | 720 | 4 | risk_denied=607 (margin_total=393, daily_max_loss=214); arm_conflict=50 (S1@15m=19, M1@1h=12, T1@15m=6, T1@1h=5, H2@1h=3, H2@15m=2, TF1@15m=1, TF1@4h=1, F1@15m=1); etiket_rejim=47; order_failed=12 | 42 | 0 | risk_denied=37 (margin_total=37); arm_conflict=3 (T1@15m=2, M1@1h=1); etiket_rejim=2 | veri: 22.11.2026 22:30 TSİ |
| M1@1d | 0 | 0 | - | 0 | 0 | - | veri: 22.11.2026 22:30 TSİ |

Aday üretmedi (sinyal tarafı, filtre değil): tüm kayıtta R1@1d, F1@1d, M1@1d · yalnız son 12 saatte T1@4h, T1@1d, R1@15m, R1@1h, R1@4h, TF1@1h, TF1@4h, TF1@1d, B1@1h, B1@4h, B1@1d, H2@4h, H2@1d, S1@4h, S1@1d, F1@4h.

Aday = `decision_events` satırı. Golge kararlar (shadow) ve hiç kayda girmeyen sinyaller bu sayıya girmez.

### stop_width skip'leri: dar / geniş (son 12 saat / tüm kayıt)

İzinli bant: stop/ATR 0.5 – 2.0 (signals.STOP_DIST_MIN_ATR / STOP_DIST_MAX_ATR). Yalnız ölçüm; davranış değişmez. Dar/geniş ayrımı kayıtlı `features.stop_dist_atr` değerinin banta göre karşılaştırılmasından türetilir; medyan = reddedilen adayların medyan stop/ATR'si.

| Kol | Son 12s | Tüm kayıt | Veri |
|---|---|---|---|
| T1@15m | dar=0, geniş=18 · medyan 2.42 | dar=0, geniş=146 · medyan 2.80 | veri: 22.11.2026 22:30 TSİ |
| T1@1h | dar=0, geniş=3 · medyan 2.08 | dar=0, geniş=35 · medyan 2.40 | veri: 22.11.2026 22:30 TSİ |
| T1@4h | - | dar=0, geniş=5 · medyan 3.02 | veri: 22.11.2026 22:30 TSİ |
| T1@1d | - | dar=0, geniş=1 · medyan 3.45 | veri: 22.11.2026 22:30 TSİ |
| R1@15m | - | - | veri: 22.11.2026 22:30 TSİ |
| R1@1h | - | - | veri: 22.11.2026 22:30 TSİ |
| R1@4h | - | - | veri: 22.11.2026 22:30 TSİ |
| R1@1d | - | - | veri: 22.11.2026 22:30 TSİ |
| TF1@15m | - | - | veri: 22.11.2026 22:30 TSİ |
| TF1@1h | - | - | veri: 22.11.2026 22:30 TSİ |
| TF1@4h | - | - | veri: 22.11.2026 22:30 TSİ |
| TF1@1d | - | - | veri: 22.11.2026 22:30 TSİ |
| B1@15m | - | dar=0, geniş=7 · medyan 4.40 | veri: 22.11.2026 22:30 TSİ |
| B1@1h | - | - | veri: 22.11.2026 22:30 TSİ |
| B1@4h | - | - | veri: 22.11.2026 22:30 TSİ |
| B1@1d | - | - | veri: 22.11.2026 22:30 TSİ |
| H2@15m | - | dar=0, geniş=18 · medyan 2.84 | veri: 22.11.2026 22:30 TSİ |
| H2@1h | dar=0, geniş=1 · medyan 4.36 | dar=0, geniş=7 · medyan 3.70 | veri: 22.11.2026 22:30 TSİ |
| H2@4h | - | dar=0, geniş=2 · medyan 3.48 | veri: 22.11.2026 22:30 TSİ |
| H2@1d | - | - | veri: 22.11.2026 22:30 TSİ |
| S1@15m | dar=0, geniş=7 · medyan 3.19 | dar=0, geniş=99 · medyan 3.39 | veri: 22.11.2026 22:30 TSİ |
| S1@1h | dar=0, geniş=1 · medyan 4.26 | dar=0, geniş=24 · medyan 3.52 | veri: 22.11.2026 22:30 TSİ |
| S1@4h | - | dar=0, geniş=8 · medyan 3.91 | veri: 22.11.2026 22:30 TSİ |
| S1@1d | - | dar=0, geniş=3 · medyan 3.48 | veri: 22.11.2026 22:30 TSİ |
| F1@15m | dar=0, geniş=27 · medyan 2.61 | dar=0, geniş=59 · medyan 2.53 | veri: 22.11.2026 22:30 TSİ |
| F1@1h | dar=0, geniş=1 · medyan 2.04 | dar=0, geniş=5 · medyan 2.81 | veri: 22.11.2026 22:30 TSİ |
| F1@4h | - | - | veri: 22.11.2026 22:30 TSİ |
| F1@1d | - | - | veri: 22.11.2026 22:30 TSİ |
| M1@1h | - | - | veri: 22.11.2026 22:30 TSİ |
| M1@4h | - | - | veri: 22.11.2026 22:30 TSİ |
| M1@15m | - | - | veri: 22.11.2026 22:30 TSİ |
| M1@1d | - | - | veri: 22.11.2026 22:30 TSİ |

## ML 10 — Kol bazında sanal K/Z

| Kol | İşlem | Net $ | R toplamı | Kazanma | Durum | Veri |
|---|---|---|---|---|---|---|
| F1@15m | 5 | -$31,95 | -3,44 R | %20,0 | ZARARDA | veri: 22.11.2026 15:19 TSİ |
| S1@15m | 4 | -$19,54 | -1,03 R | %25,0 | ZARARDA | veri: 21.11.2026 02:01 TSİ |
| M1@1h | 3 | -$16,88 | -1,49 R | %33,3 | ZARARDA | veri: 22.11.2026 17:23 TSİ |
| H2@1h | 1 | -$11,73 | -1,00 R | %0,0 | ZARARDA | veri: 21.11.2026 16:39 TSİ |
| M1@15m | 4 | -$8,07 | -2,27 R | %25,0 | ZARARDA | veri: 22.11.2026 05:45 TSİ |
| T1@1h | 9 | -$3,02 | +1,52 R | %55,6 | ZARARDA | veri: 22.11.2026 13:30 TSİ |
| B1@15m | 1 | +$3,39 | +0,73 R | %100,0 | kârda/başa baş | veri: 19.11.2026 20:15 TSİ |
| H2@15m | 2 | +$4,89 | +0,49 R | %50,0 | kârda/başa baş | veri: 21.11.2026 09:41 TSİ |
| TF1@15m | 2 | +$12,48 | +1,26 R | %100,0 | kârda/başa baş | veri: 21.11.2026 02:00 TSİ |
| B1@1h | 2 | +$13,14 | +1,35 R | %50,0 | kârda/başa baş | veri: 21.11.2026 14:31 TSİ |
| M1@4h | 1 | +$20,50 | +1,99 R | %100,0 | kârda/başa baş | veri: 20.11.2026 19:00 TSİ |
| S1@1h | 2 | +$25,31 | +2,44 R | %100,0 | kârda/başa baş | veri: 21.11.2026 16:45 TSİ |
| T1@15m | 4 | +$90,86 | +7,36 R | %75,0 | kârda/başa baş | veri: 21.11.2026 16:45 TSİ |
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
| Ders: kol kapatma (arms_off) | var | yalnız karne/rapor bilgisi; giriş ENGELLENMEZ (sahip kararı, 19 Kasım; gates.py `arm_would_close` sayacı) | tetiklendi: H2@15m, H2@1h, M1@15m, R1@15m, TF1@15m | okuma: 22.11.2026 22:34 TSİ |
| Ders: 10 R freni (lesson_brake) | var | ders ayarlarını referansa döndürür, otomatik uygulamayı durdurur; kolu kapatmaz | tetiklenmedi | okuma: 22.11.2026 22:34 TSİ |
| Kol başına açık pozisyon tavanı (arm_max_positions) ve küme/hesap tavanı | var | kayıptan bağımsız konum sınırı; zarardaki kolu özel olarak ayırmaz | kayıp temelli tetik değil | okuma: 22.11.2026 22:34 TSİ |
| Risk kademe denetimi (risk_ladder, hesap düzeyi küçültme) | var (hesap düzeyi; kol düzeyi değil) | tepe-denge düşüşünde hedef işlem riskini kademeli düşürür / durdurur; motor zorunlu yalnız canlı modda | kâğıt ayarında LADDER_BOTS boş; kâğıtta kademe izlenmez | okuma: 22.11.2026 22:34 TSİ |
| Kol bazında otomatik karantina / boyut küçültme | yok | zararda kol: F1@15m, S1@15m, M1@1h, H2@1h, M1@15m, T1@1h; bu kolları kendiliğinden kısan kural yok | - | okuma: 22.11.2026 22:34 TSİ |

## ML 11 — Long/short dağılımı

| Yön | İşlem | Net $ | Kazanma | R | Veri |
|---|---|---|---|---|---|
| long | 6 | -$15,10 | %50,0 | -1,32 R | veri: 22.11.2026 13:30 TSİ |
| short | 34 | +$94,48 | %50,0 | +9,24 R | veri: 22.11.2026 17:23 TSİ |

| Rejim | Long (n / net $ / kazanma) | Short (n / net $ / kazanma) | Veri |
|---|---|---|---|
| trend_up | 2 / -$8,50 / %50,0 | 0 / - / - | veri: 22.11.2026 13:30 TSİ |
| trend_down | 1 / +$4,86 / %100,0 | 33 / +$101,80 / %51,5 | veri: 22.11.2026 17:23 TSİ |
| range | 2 / -$19,65 / %0,0 | 1 / -$7,33 / %0,0 | veri: 21.11.2026 16:45 TSİ |
| unclear | 1 / +$8,20 / %100,0 | 0 / - / - | veri: 20.11.2026 05:45 TSİ |
| volatile | 0 / - / - | 0 / - / - | veri: işlem yok |

Güncel rejim (son karar zamanından geriye 24 saatte en sık rejim; 1002 karar): trend_down (veri: 22.11.2026 22:30 TSİ)
Long-yetkin kollar (kayıtta ≥1 long adayı olanlar) bu rejimde: aday 117 · alınan 1

| Kol | Long aday (güncel rejim) | Alınan (güncel rejim) | Long aday (tüm kayıt) | Alınan (tüm kayıt) | Veri |
|---|---|---|---|---|---|
| T1@15m | 0 | 0 | 15 | 0 | veri: 22.11.2026 17:30 TSİ |
| T1@1h | 0 | 0 | 5 | 1 | veri: 22.11.2026 13:00 TSİ |
| T1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 19:00 TSİ |
| R1@15m | 0 | 0 | 30 | 0 | veri: 20.11.2026 10:45 TSİ |
| R1@1h | 0 | 0 | 15 | 0 | veri: 20.11.2026 17:00 TSİ |
| R1@4h | 0 | 0 | 11 | 0 | veri: 20.11.2026 11:00 TSİ |
| TF1@15m | 0 | 0 | 8 | 0 | veri: 21.11.2026 20:15 TSİ |
| TF1@1h | 0 | 0 | 3 | 0 | veri: 20.11.2026 18:00 TSİ |
| TF1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 19:00 TSİ |
| B1@1h | 0 | 0 | 1 | 0 | veri: 19.11.2026 14:00 TSİ |
| H2@15m | 0 | 0 | 7 | 0 | veri: 22.11.2026 16:00 TSİ |
| H2@1h | 0 | 0 | 2 | 0 | veri: 22.11.2026 13:00 TSİ |
| H2@4h | 0 | 0 | 1 | 0 | veri: 21.11.2026 23:00 TSİ |
| S1@15m | 0 | 0 | 26 | 2 | veri: 22.11.2026 14:00 TSİ |
| S1@1h | 0 | 0 | 5 | 0 | veri: 22.11.2026 13:00 TSİ |
| S1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 15:00 TSİ |
| F1@15m | 0 | 0 | 45 | 2 | veri: 22.11.2026 09:00 TSİ |
| F1@1h | 0 | 0 | 16 | 0 | veri: 20.11.2026 17:00 TSİ |
| F1@4h | 0 | 0 | 2 | 0 | veri: 20.11.2026 03:00 TSİ |
| M1@1h | 104 | 1 | 107 | 1 | veri: 22.11.2026 22:00 TSİ |
| M1@15m | 13 | 0 | 13 | 0 | veri: 22.11.2026 13:00 TSİ |

## ML 12 — Kâğıt / geri test tutarlılığı

Toplam kâğıt R (n=40): +7,91 R (veri: 22.11.2026 17:23 TSİ). Yayımlanmış bant (n=40 için aradeğer): %2,5=-22,4 · %10=-16,4 · ortanca=-0,1 · %90=+25,9. Konum: %10-%90 arası (bant içinde). Kaynak: docs/kagit-degerlendirme-plani.md §4.4 (kümülatif net R, referans bootstrap bandı).

Arm/kurulum bazında kâğıt R/işlem ↔ geri test bandı: veri yok (tutarlılık raporu yok ya da boş; repoda arm bazında R/işlem bandı yayımlanmamış).
