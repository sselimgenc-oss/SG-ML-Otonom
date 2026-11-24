# Yeni kollar geri test ozeti (gelistirme)

- Ciftler: 43 (veri olan: 19); zaman dilimleri: 1h, 4h, 1d
- Fonlama verisi olan cift: 19/43 (olmayanda veto kapali)
- Kesim (dislayici): 2025-07-01; sure: 224 sn

R = net R (ucret+kayma+fonlama dusulmus). Yalniz arastirma; canliya baglanmaz.

## Ana sonuc (tam teyit)

| kol | tf | yon | islem | kazanma | ort R | toplam R | PF | maks dusus R | ort tutma (mum) | stop/hedef/zaman | rastgele ort R | fark | z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MF1 | 4h | long | 1583 | 0.38 | -0.058 | -91.4 | 0.90 | 93.3 | 8.6 | 873/306/404 | -0.087 | 0.029 | 0.6 |
| MF1 | 4h | short | 1717 | 0.37 | -0.055 | -94.0 | 0.91 | 118.9 | 8.5 | 947/340/430 | -0.020 | -0.034 | -0.8 |
| MF1 | 4h | hepsi | 3300 | 0.38 | -0.056 | -185.5 | 0.91 | 198.3 | 8.5 | 1820/646/834 | -0.052 | -0.004 | -0.1 |
| MF1 | 1d | long | 238 | 0.39 | -0.019 | -4.6 | 0.96 | 29.0 | 10.1 | 112/31/95 | -0.008 | -0.012 | -0.1 |
| MF1 | 1d | short | 221 | 0.37 | -0.014 | -3.1 | 0.98 | 30.9 | 9.4 | 120/41/60 | 0.035 | -0.048 | -0.4 |
| MF1 | 1d | hepsi | 459 | 0.38 | -0.017 | -7.7 | 0.97 | 43.9 | 9.8 | 232/72/155 | 0.013 | -0.029 | -0.3 |
| GF1 | 1h | long | 531 | 0.31 | -0.143 | -75.7 | 0.81 | 89.9 | 12.1 | 362/145/24 | -0.135 | -0.008 | -0.1 |
| GF1 | 1h | short | 501 | 0.33 | -0.091 | -45.4 | 0.87 | 89.0 | 13.9 | 331/138/32 | -0.028 | -0.062 | -0.7 |
| GF1 | 1h | hepsi | 1032 | 0.32 | -0.117 | -121.2 | 0.84 | 163.1 | 13.0 | 693/283/56 | -0.083 | -0.034 | -0.5 |
| GF1 | 4h | long | 121 | 0.37 | 0.064 | 7.7 | 1.10 | 17.6 | 11.1 | 76/43/2 | -0.052 | 0.116 | 0.6 |
| GF1 | 4h | short | 137 | 0.31 | -0.067 | -9.2 | 0.91 | 18.4 | 14.2 | 93/37/7 | 0.048 | -0.115 | -0.6 |
| GF1 | 4h | hepsi | 258 | 0.34 | -0.006 | -1.5 | 0.99 | 23.5 | 12.8 | 169/80/9 | 0.001 | -0.007 | -0.1 |
| GF1 | 1d | long | 24 | 0.33 | -0.058 | -1.4 | 0.92 | 9.2 | 10.9 | 16/7/1 | 0.092 | -0.150 | yetersiz |
| GF1 | 1d | short | 32 | 0.28 | -0.149 | -4.8 | 0.78 | 10.1 | 21.2 | 21/4/7 | 0.003 | -0.153 | yetersiz |
| GF1 | 1d | hepsi | 56 | 0.30 | -0.110 | -6.2 | 0.84 | 13.8 | 16.8 | 37/11/8 | 0.041 | -0.151 | -0.6 |
| IN1 | 1h | long | 21 | 0.29 | -0.271 | -5.7 | 0.64 | 9.3 | 9.5 | 15/5/1 | -0.080 | -0.192 | yetersiz |
| IN1 | 1h | short | 26 | 0.50 | 0.224 | 5.8 | 1.42 | 4.4 | 14.6 | 12/8/6 | -0.038 | 0.261 | yetersiz |
| IN1 | 1h | hepsi | 47 | 0.40 | 0.002 | 0.1 | 1.00 | 7.4 | 12.3 | 27/13/7 | -0.057 | 0.059 | yetersiz |
| IN1 | 4h | long | 25 | 0.32 | -0.273 | -6.8 | 0.58 | 9.1 | 14.4 | 15/2/8 | -0.025 | -0.248 | yetersiz |
| IN1 | 4h | short | 55 | 0.44 | 0.076 | 4.2 | 1.15 | 11.0 | 14.3 | 26/12/17 | -0.017 | 0.093 | 0.4 |
| IN1 | 4h | hepsi | 80 | 0.40 | -0.033 | -2.6 | 0.94 | 10.7 | 14.3 | 41/14/25 | -0.020 | -0.013 | -0.1 |

## Sekil / seviye turune gore dokum (tam teyit, hepsi): tur: islem, ort R, toplam R

- MF1 4h: pdl: 1621, -0.047, -76.6; pwl: 441, -0.118, -51.9; ust_dip_1d: 118, -0.091, -10.7; vwap: 1120, -0.041, -46.3
- MF1 1d: kendi_pivot: 41, -0.414, -17.0; pwl: 176, -0.094, -16.5; vwap: 242, 0.107, 25.8
- GF1 1h: ikili_dip: 350, -0.123, -43.2; tobo: 80, -0.045, -3.6; ucgen: 602, -0.124, -74.4
- GF1 4h: ikili_dip: 71, 0.220, 15.6; tobo: 29, -0.411, -11.9; ucgen: 158, -0.033, -5.2
- GF1 1d: ikili_dip: 18, -0.676, -12.2; tobo: 3, 0.646, 1.9; ucgen: 35, 0.116, 4.1
- IN1 1h: gevsek_eslesme: 47, 0.002, 0.1
- IN1 4h: gevsek_eslesme: 80, -0.033, -2.6

IN1 kapatma kurali: 1h + 4h toplam islem = 127 -> >= 50: devam

## Yil yil toplam R (tam teyit, her iki yon)

- MF1 4h: 2021: -78.5, 2022: -57.8, 2023: 30.6, 2024: -30.0, 2025: -49.8
- MF1 1d: 2021: -7.1, 2022: 25.3, 2023: -17.0, 2024: -7.8, 2025: -1.1
- GF1 1h: 2021: 26.6, 2022: -38.9, 2023: -59.6, 2024: -45.7, 2025: -3.6
- GF1 4h: 2021: 12.8, 2022: -7.9, 2023: -2.7, 2024: -3.7, 2025: 0.1
- GF1 1d: 2021: 2.0, 2022: -2.6, 2023: -1.9, 2024: -3.7, 2025: 0.0
- IN1 1h: 2021: -3.9, 2022: 0.5, 2023: 4.5, 2024: -0.1, 2025: -0.8
- IN1 4h: 2021: -5.0, 2022: 11.1, 2023: -7.0, 2024: 3.8, 2025: -5.5

## Cift dagilimi (tam teyit, hepsi): en iyi / en kotu 5 (toplam R)

- MF1 4h: iyi [DOGE/USDT 17.1, TRX/USDT 14.0, HBAR/USDT 9.0, AVAX/USDT 2.9, XMR/USDT -1.4]; kotu [LINK/USDT -66.2, XRP/USDT -38.0, BNB/USDT -27.0, ADA/USDT -21.6, 1000SHIB/USDT -20.5]
- MF1 1d: iyi [SOL/USDT 9.3, HBAR/USDT 9.1, XLM/USDT 6.3, LINK/USDT 5.9, 1000SHIB/USDT 4.7]; kotu [BCH/USDT -13.0, DOGE/USDT -8.1, DOT/USDT -6.9, XMR/USDT -5.9, SUI/USDT -4.3]
- GF1 1h: iyi [DOGE/USDT 15.9, TRX/USDT 14.4, AVAX/USDT 12.4, XRP/USDT 3.5, ADA/USDT -0.8]; kotu [BTC/USDT -28.7, ETH/USDT -28.0, BCH/USDT -21.0, LTC/USDT -15.9, XLM/USDT -15.2]
- GF1 4h: iyi [1000SHIB/USDT 10.8, BCH/USDT 9.8, XRP/USDT 3.4, DOT/USDT 1.8, LTC/USDT 1.3]; kotu [XLM/USDT -7.6, ADA/USDT -6.9, BNB/USDT -6.0, XMR/USDT -3.5, SUI/USDT -1.7]
- GF1 1d: iyi [TRX/USDT 5.3, LINK/USDT 3.5, DOT/USDT 3.2, SUI/USDT 0.9, AVAX/USDT 0.7]; kotu [XMR/USDT -4.0, DOGE/USDT -3.0, XLM/USDT -3.0, HBAR/USDT -2.0, BCH/USDT -2.0]
- IN1 1h: iyi [BCH/USDT 5.3, ETH/USDT 3.0, LTC/USDT 1.5, LINK/USDT 1.4, TRX/USDT 1.4]; kotu [BNB/USDT -2.8, XLM/USDT -2.6, 1000SHIB/USDT -2.2, ADA/USDT -2.1, DOT/USDT -1.5]
- IN1 4h: iyi [DOT/USDT 4.8, ETH/USDT 3.7, HBAR/USDT 3.0, BTC/USDT 2.4, ADA/USDT 1.7]; kotu [XRP/USDT -5.3, LINK/USDT -3.5, TRX/USDT -2.2, SOL/USDT -2.1, XMR/USDT -2.1]

## Teyit acma-kapama (ablation, her iki yon)

| kol | tf | konfig | islem | ort R | toplam R | PF | kazanma |
|---|---|---|---|---|---|---|---|
| MF1 | 4h | tam | 3300 | -0.056 | -185.5 | 0.91 | 0.38 |
| MF1 | 4h | seviye_kapali | 6416 | -0.055 | -350.5 | 0.91 | 0.36 |
| MF1 | 4h | fonlama_kapali | 3357 | -0.057 | -190.5 | 0.91 | 0.38 |
| MF1 | 4h | maliyet_kapali | 3304 | -0.055 | -183.2 | 0.91 | 0.38 |
| MF1 | 4h | hic_teyit | 6551 | -0.059 | -386.5 | 0.90 | 0.36 |
| MF1 | 1d | tam | 459 | -0.017 | -7.7 | 0.97 | 0.38 |
| MF1 | 1d | seviye_kapali | 729 | 0.032 | 23.1 | 1.06 | 0.40 |
| MF1 | 1d | fonlama_kapali | 471 | -0.019 | -8.7 | 0.97 | 0.38 |
| MF1 | 1d | maliyet_kapali | 459 | -0.017 | -7.7 | 0.97 | 0.38 |
| MF1 | 1d | hic_teyit | 744 | 0.032 | 23.7 | 1.06 | 0.40 |
| GF1 | 1h | tam | 1032 | -0.117 | -121.2 | 0.84 | 0.32 |
| GF1 | 1h | zd_kapali | 1703 | -0.123 | -208.7 | 0.83 | 0.32 |
| GF1 | 1h | hacim_kapali | 1683 | -0.077 | -129.7 | 0.89 | 0.33 |
| GF1 | 1h | fonlama_kapali | 1096 | -0.129 | -140.8 | 0.83 | 0.32 |
| GF1 | 1h | maliyet_kapali | 1073 | -0.105 | -112.6 | 0.86 | 0.32 |
| GF1 | 1h | hic_teyit | 2971 | -0.102 | -304.1 | 0.86 | 0.33 |
| GF1 | 4h | tam | 258 | -0.006 | -1.5 | 0.99 | 0.34 |
| GF1 | 4h | zd_kapali | 391 | 0.032 | 12.6 | 1.05 | 0.36 |
| GF1 | 4h | hacim_kapali | 419 | 0.024 | 10.0 | 1.03 | 0.34 |
| GF1 | 4h | fonlama_kapali | 264 | -0.015 | -3.9 | 0.98 | 0.33 |
| GF1 | 4h | maliyet_kapali | 258 | -0.006 | -1.5 | 0.99 | 0.34 |
| GF1 | 4h | hic_teyit | 678 | 0.007 | 4.8 | 1.01 | 0.34 |
| GF1 | 1d | tam | 56 | -0.110 | -6.2 | 0.84 | 0.30 |
| GF1 | 1d | zd_kapali | 59 | -0.156 | -9.2 | 0.78 | 0.29 |
| GF1 | 1d | hacim_kapali | 105 | 0.088 | 9.2 | 1.13 | 0.34 |
| GF1 | 1d | fonlama_kapali | 58 | -0.142 | -8.3 | 0.80 | 0.29 |
| GF1 | 1d | maliyet_kapali | 56 | -0.110 | -6.2 | 0.84 | 0.30 |
| GF1 | 1d | hic_teyit | 111 | 0.051 | 5.7 | 1.08 | 0.33 |
| IN1 | 1h | tam | 47 | 0.002 | 0.1 | 1.00 | 0.40 |
| IN1 | 1h | zd_kapali | 797 | -0.061 | -48.9 | 0.89 | 0.42 |
| IN1 | 1h | fonlama_kapali | 49 | 0.001 | 0.0 | 1.00 | 0.41 |
| IN1 | 1h | maliyet_kapali | 47 | 0.002 | 0.1 | 1.00 | 0.40 |
| IN1 | 1h | hic_teyit | 811 | -0.059 | -48.0 | 0.89 | 0.42 |
| IN1 | 4h | tam | 80 | -0.033 | -2.6 | 0.94 | 0.40 |
| IN1 | 4h | zd_kapali | 204 | -0.161 | -32.8 | 0.73 | 0.35 |
| IN1 | 4h | fonlama_kapali | 80 | -0.033 | -2.6 | 0.94 | 0.40 |
| IN1 | 4h | maliyet_kapali | 80 | -0.033 | -2.6 | 0.94 | 0.40 |
| IN1 | 4h | hic_teyit | 206 | -0.164 | -33.7 | 0.72 | 0.35 |

Not: GF1'de 'seviye', MF1'de 'zd'+'hacim', IN1'de 'seviye'+'hacim' teyidi yoktur (uygulanmaz). 'hic_teyit' = yalniz sekil + stop/hedef (rr>=1,5).
