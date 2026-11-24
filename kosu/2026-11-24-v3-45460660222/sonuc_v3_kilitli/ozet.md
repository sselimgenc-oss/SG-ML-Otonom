# v3 kitap setuplari geri test ozeti (kilitli)

- Ciftler: 43 (engine.paper.json); veri olan: 43; zaman dilimleri: 15m, 1h, 4h, 1d
- Fonlama verisi olan cift: 43/43 (fonlama maliyeti islenir; veto YOK)
- Kesim (dislayici): 2026-11-24; sure: 663 sn
- Rastgele kiyas: setup x cift x zd x yon grubu basina 200 cekilis (ayni yil/yon/stop-hedef ATR mesafesi), gercek islem sayisiyla agirlikli.
- R = net R (ucret+kayma+fonlama dusulmus). Stopu olmayan IND_MA_KESISIM / IND_FIYAT_MA'da R birimi 2 ATR(14). Yalniz arastirma.

## Ana sonuc

| setup | kat | tf | yon | sinyal | islem | kazanma | ort R | toplam R | PF | maks dusus R | stop/hedef/zaman/sinyal | rastgele ort R | fark | z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MUM_PINBAR | MF1 | 15m | long | 16159 | 3554 | 31.9% | -0.285 | -1014.4 | 0.63 | 1014.4 | 2260/873/421/0 | -0.241 | -0.044 | -1.5 |
| MUM_PINBAR | MF1 | 15m | short | 15233 | 2397 | 35.7% | -0.161 | -385.2 | 0.78 | 429.7 | 1441/718/238/0 | -0.124 | -0.037 | -0.9 |
| MUM_PINBAR | MF1 | 15m | hepsi | 31392 | 5951 | 33.4% | -0.235 | -1399.6 | 0.69 | 1400.0 | 3701/1591/659/0 | -0.194 | -0.041 | -1.7 |
| MUM_PINBAR | MF1 | 1h | long | 3490 | 1984 | 32.8% | -0.232 | -460.2 | 0.69 | 469.8 | 1280/542/162/0 | -0.208 | -0.024 | -0.6 |
| MUM_PINBAR | MF1 | 1h | short | 3079 | 1521 | 38.3% | -0.050 | -75.8 | 0.93 | 182.9 | 911/526/84/0 | -0.121 | 0.071 | 1.4 |
| MUM_PINBAR | MF1 | 1h | hepsi | 6569 | 3505 | 35.2% | -0.153 | -536.0 | 0.79 | 571.4 | 2191/1068/246/0 | -0.170 | 0.017 | 0.5 |
| MUM_PINBAR | MF1 | 4h | long | 781 | 682 | 27.1% | -0.314 | -213.9 | 0.60 | 221.9 | 480/169/33/0 | -0.165 | -0.149 | -2.1 |
| MUM_PINBAR | MF1 | 4h | short | 611 | 496 | 28.6% | -0.279 | -138.6 | 0.64 | 155.9 | 352/128/16/0 | -0.069 | -0.211 | -2.4 |
| MUM_PINBAR | MF1 | 4h | hepsi | 1392 | 1178 | 27.8% | -0.299 | -352.6 | 0.62 | 355.7 | 832/297/49/0 | -0.124 | -0.175 | -3.2 |
| MUM_PINBAR | MF1 | 1d | long | 78 | 68 | 16.2% | -0.532 | -36.1 | 0.37 | 38.1 | 54/11/3/0 | -0.193 | -0.339 | -1.6 |
| MUM_PINBAR | MF1 | 1d | short | 45 | 44 | 27.3% | -0.221 | -9.7 | 0.70 | 15.1 | 32/12/0/0 | 0.051 | -0.271 | yetersiz |
| MUM_PINBAR | MF1 | 1d | hepsi | 123 | 112 | 20.5% | -0.409 | -45.9 | 0.49 | 45.9 | 86/23/3/0 | -0.097 | -0.312 | -1.8 |
| MUM_IC_CUBUK | MF1 | 15m | long | 216219 | 14869 | 34.1% | -0.216 | -3217.3 | 0.71 | 3289.2 | 9151/4056/1662/0 | -0.282 | 0.066 | 4.4 |
| MUM_IC_CUBUK | MF1 | 15m | short | 216219 | 15667 | 36.2% | -0.147 | -2298.5 | 0.80 | 2328.1 | 9331/4624/1712/0 | -0.103 | -0.043 | -2.9 |
| MUM_IC_CUBUK | MF1 | 15m | hepsi | 432438 | 30536 | 35.2% | -0.181 | -5515.8 | 0.75 | 5521.1 | 18482/8680/3374/0 | -0.190 | 0.010 | 0.9 |
| MUM_IC_CUBUK | MF1 | 1h | long | 59220 | 7269 | 33.8% | -0.181 | -1312.9 | 0.76 | 1488.8 | 4638/2120/511/0 | -0.177 | -0.003 | -0.1 |
| MUM_IC_CUBUK | MF1 | 1h | short | 59220 | 7288 | 36.1% | -0.095 | -695.7 | 0.87 | 848.2 | 4445/2339/504/0 | -0.097 | 0.002 | 0.1 |
| MUM_IC_CUBUK | MF1 | 1h | hepsi | 118440 | 14557 | 34.9% | -0.138 | -2008.6 | 0.81 | 2126.6 | 9083/4459/1015/0 | -0.137 | -0.001 | -0.0 |
| MUM_IC_CUBUK | MF1 | 4h | long | 15791 | 2319 | 33.5% | -0.120 | -279.2 | 0.83 | 354.7 | 1515/741/63/0 | -0.143 | 0.022 | 0.6 |
| MUM_IC_CUBUK | MF1 | 4h | short | 15791 | 2351 | 35.4% | -0.065 | -152.5 | 0.91 | 264.1 | 1493/766/92/0 | -0.056 | -0.009 | -0.2 |
| MUM_IC_CUBUK | MF1 | 4h | hepsi | 31582 | 4670 | 34.5% | -0.092 | -431.7 | 0.87 | 487.3 | 3008/1507/155/0 | -0.099 | 0.006 | 0.2 |
| MUM_IC_CUBUK | MF1 | 1d | long | 1766 | 266 | 27.4% | -0.249 | -66.3 | 0.66 | 84.6 | 190/67/9/0 | -0.071 | -0.179 | -1.6 |
| MUM_IC_CUBUK | MF1 | 1d | short | 1766 | 307 | 36.8% | 0.039 | 11.9 | 1.06 | 39.2 | 190/102/15/0 | 0.068 | -0.029 | -0.3 |
| MUM_IC_CUBUK | MF1 | 1d | hepsi | 3532 | 573 | 32.5% | -0.095 | -54.4 | 0.86 | 99.0 | 380/169/24/0 | 0.004 | -0.099 | -1.2 |
| MUM_YUTAN | MF1 | 15m | long | 38459 | 7489 | 33.0% | -0.242 | -1812.2 | 0.69 | 1813.7 | 4803/2107/579/0 | -0.242 | -0.000 | -0.0 |
| MUM_YUTAN | MF1 | 15m | short | 39006 | 6742 | 35.8% | -0.167 | -1125.1 | 0.77 | 1200.6 | 4113/2023/606/0 | -0.149 | -0.018 | -0.8 |
| MUM_YUTAN | MF1 | 15m | hepsi | 77465 | 14231 | 34.3% | -0.206 | -2937.3 | 0.73 | 2937.3 | 8916/4130/1185/0 | -0.198 | -0.009 | -0.6 |
| MUM_YUTAN | MF1 | 1h | long | 9161 | 4116 | 31.4% | -0.240 | -986.2 | 0.69 | 1029.6 | 2728/1174/214/0 | -0.211 | -0.029 | -1.0 |
| MUM_YUTAN | MF1 | 1h | short | 9642 | 4318 | 36.5% | -0.096 | -413.5 | 0.87 | 481.9 | 2650/1424/244/0 | -0.115 | 0.019 | 0.7 |
| MUM_YUTAN | MF1 | 1h | hepsi | 18803 | 8434 | 34.0% | -0.166 | -1399.7 | 0.78 | 1436.0 | 5378/2598/458/0 | -0.162 | -0.004 | -0.2 |
| MUM_YUTAN | MF1 | 4h | long | 2073 | 1392 | 32.6% | -0.148 | -206.0 | 0.80 | 245.0 | 928/438/26/0 | -0.169 | 0.021 | 0.4 |
| MUM_YUTAN | MF1 | 4h | short | 2242 | 1478 | 38.2% | 0.013 | 19.7 | 1.02 | 107.6 | 904/533/41/0 | -0.101 | 0.114 | 2.2 |
| MUM_YUTAN | MF1 | 4h | hepsi | 4315 | 2870 | 35.5% | -0.065 | -186.3 | 0.91 | 223.6 | 1832/971/67/0 | -0.134 | 0.069 | 1.9 |
| MUM_YUTAN | MF1 | 1d | long | 219 | 184 | 37.5% | 0.061 | 11.3 | 1.09 | 29.1 | 114/68/2/0 | -0.201 | 0.262 | 1.8 |
| MUM_YUTAN | MF1 | 1d | short | 256 | 203 | 37.9% | 0.068 | 13.8 | 1.11 | 26.1 | 126/72/5/0 | -0.008 | 0.076 | 0.5 |
| MUM_YUTAN | MF1 | 1d | hepsi | 475 | 387 | 37.7% | 0.065 | 25.1 | 1.10 | 46.9 | 240/140/7/0 | -0.100 | 0.164 | 1.6 |
| MUM_YILDIZ | MF1 | 15m | long | 23 | 23 | 39.1% | -0.026 | -0.6 | 0.95 | 9.0 | 11/2/10/0 | -0.133 | 0.107 | yetersiz |
| MUM_YILDIZ | MF1 | 15m | short | 23 | 23 | 43.5% | 0.425 | 9.8 | 2.08 | 3.6 | 7/1/15/0 | -0.071 | 0.497 | yetersiz |
| MUM_YILDIZ | MF1 | 15m | hepsi | 46 | 46 | 41.3% | 0.200 | 9.2 | 1.42 | 12.3 | 18/3/25/0 | -0.102 | 0.302 | yetersiz |
| MUM_YILDIZ | MF1 | 1h | long | 52 | 51 | 49.0% | 0.108 | 5.5 | 1.25 | 4.9 | 19/3/29/0 | -0.106 | 0.214 | 0.9 |
| MUM_YILDIZ | MF1 | 1h | short | 42 | 42 | 28.6% | -0.358 | -15.0 | 0.44 | 19.7 | 24/1/17/0 | -0.017 | -0.340 | yetersiz |
| MUM_YILDIZ | MF1 | 1h | hepsi | 94 | 93 | 39.8% | -0.103 | -9.5 | 0.80 | 15.5 | 43/4/46/0 | -0.066 | -0.037 | -0.2 |
| MUM_YILDIZ | MF1 | 4h | long | 54 | 52 | 19.2% | -0.418 | -21.7 | 0.49 | 31.0 | 40/5/7/0 | -0.200 | -0.218 | -0.8 |
| MUM_YILDIZ | MF1 | 4h | short | 59 | 58 | 34.5% | 0.038 | 2.2 | 1.06 | 6.6 | 33/8/17/0 | -0.000 | 0.038 | 0.1 |
| MUM_YILDIZ | MF1 | 4h | hepsi | 113 | 110 | 27.3% | -0.177 | -19.5 | 0.75 | 31.0 | 73/13/24/0 | -0.095 | -0.083 | -0.4 |
| MUM_YILDIZ | MF1 | 1d | long | 20 | 20 | 10.0% | -0.655 | -13.1 | 0.31 | 18.9 | 18/2/0/0 | -0.205 | -0.450 | yetersiz |
| MUM_YILDIZ | MF1 | 1d | short | 19 | 19 | 10.5% | -0.625 | -11.9 | 0.33 | 12.5 | 17/2/0/0 | 0.170 | -0.795 | yetersiz |
| MUM_YILDIZ | MF1 | 1d | hepsi | 39 | 39 | 10.3% | -0.640 | -25.0 | 0.32 | 30.6 | 35/4/0/0 | -0.022 | -0.618 | yetersiz |
| FOR_YATAY_KIRILIM | GF1 | 15m | long | 27590 | 8155 | 40.1% | -0.221 | -1801.6 | 0.66 | 1868.5 | 4458/3307/390/0 | -0.208 | -0.013 | -0.7 |
| FOR_YATAY_KIRILIM | GF1 | 15m | short | 26532 | 8744 | 42.2% | -0.173 | -1512.4 | 0.73 | 1520.5 | 4659/3617/468/0 | -0.152 | -0.021 | -1.1 |
| FOR_YATAY_KIRILIM | GF1 | 15m | hepsi | 54122 | 16899 | 41.2% | -0.196 | -3314.0 | 0.70 | 3351.9 | 9117/6924/858/0 | -0.179 | -0.017 | -1.3 |
| FOR_YATAY_KIRILIM | GF1 | 1h | long | 6536 | 3667 | 40.3% | -0.155 | -568.3 | 0.76 | 644.7 | 2055/1486/126/0 | -0.131 | -0.024 | -0.8 |
| FOR_YATAY_KIRILIM | GF1 | 1h | short | 6392 | 3983 | 39.2% | -0.150 | -598.3 | 0.77 | 654.5 | 2266/1506/211/0 | -0.084 | -0.066 | -2.1 |
| FOR_YATAY_KIRILIM | GF1 | 1h | hepsi | 12928 | 7650 | 39.7% | -0.153 | -1166.6 | 0.77 | 1216.6 | 4321/2992/337/0 | -0.107 | -0.046 | -2.1 |
| FOR_YATAY_KIRILIM | GF1 | 4h | long | 1297 | 1017 | 38.6% | -0.143 | -145.8 | 0.79 | 194.4 | 609/390/18/0 | -0.119 | -0.024 | -0.4 |
| FOR_YATAY_KIRILIM | GF1 | 4h | short | 1375 | 1100 | 40.9% | -0.046 | -51.1 | 0.93 | 143.5 | 642/431/27/0 | -0.018 | -0.028 | -0.4 |
| FOR_YATAY_KIRILIM | GF1 | 4h | hepsi | 2672 | 2117 | 39.8% | -0.093 | -196.9 | 0.86 | 287.7 | 1251/821/45/0 | -0.067 | -0.027 | -0.6 |
| FOR_YATAY_KIRILIM | GF1 | 1d | long | 67 | 61 | 47.5% | 0.238 | 14.5 | 1.43 | 12.6 | 32/29/0/0 | 0.046 | 0.192 | 0.7 |
| FOR_YATAY_KIRILIM | GF1 | 1d | short | 95 | 84 | 51.2% | 0.232 | 19.5 | 1.47 | 10.8 | 40/43/1/0 | 0.126 | 0.105 | 0.5 |
| FOR_YATAY_KIRILIM | GF1 | 1d | hepsi | 162 | 145 | 49.7% | 0.234 | 34.0 | 1.45 | 13.8 | 72/72/1/0 | 0.093 | 0.142 | 0.8 |
| FOR_UCGEN | GF1 | 15m | long | 6083 | 3306 | 36.6% | -0.191 | -630.5 | 0.69 | 645.6 | 1583/644/1079/0 | -0.171 | -0.020 | -0.7 |
| FOR_UCGEN | GF1 | 15m | short | 5946 | 3279 | 40.5% | -0.093 | -306.1 | 0.83 | 325.2 | 1463/696/1120/0 | -0.071 | -0.022 | -0.8 |
| FOR_UCGEN | GF1 | 15m | hepsi | 12029 | 6585 | 38.5% | -0.142 | -936.6 | 0.76 | 960.9 | 3046/1340/2199/0 | -0.121 | -0.021 | -1.0 |
| FOR_UCGEN | GF1 | 1h | long | 1373 | 996 | 39.8% | -0.034 | -33.8 | 0.94 | 111.3 | 474/248/274/0 | -0.094 | 0.060 | 1.0 |
| FOR_UCGEN | GF1 | 1h | short | 1430 | 1069 | 42.6% | -0.001 | -0.8 | 1.00 | 64.5 | 483/223/363/0 | -0.041 | 0.040 | 0.7 |
| FOR_UCGEN | GF1 | 1h | hepsi | 2803 | 2065 | 41.2% | -0.017 | -34.6 | 0.97 | 138.9 | 957/471/637/0 | -0.067 | 0.050 | 1.2 |
| FOR_UCGEN | GF1 | 4h | long | 372 | 298 | 36.6% | -0.045 | -13.4 | 0.92 | 51.9 | 152/58/88/0 | -0.083 | 0.038 | 0.3 |
| FOR_UCGEN | GF1 | 4h | short | 368 | 285 | 43.5% | 0.038 | 10.8 | 1.07 | 32.9 | 142/65/78/0 | 0.030 | 0.008 | 0.1 |
| FOR_UCGEN | GF1 | 4h | hepsi | 740 | 583 | 40.0% | -0.004 | -2.6 | 0.99 | 54.8 | 294/123/166/0 | -0.028 | 0.023 | 0.3 |
| FOR_UCGEN | GF1 | 1d | long | 49 | 41 | 41.5% | 0.152 | 6.2 | 1.30 | 8.9 | 19/10/12/0 | 0.044 | 0.107 | yetersiz |
| FOR_UCGEN | GF1 | 1d | short | 44 | 30 | 53.3% | 0.497 | 14.9 | 2.42 | 8.7 | 9/4/17/0 | 0.202 | 0.295 | yetersiz |
| FOR_UCGEN | GF1 | 1d | hepsi | 93 | 71 | 46.5% | 0.298 | 21.1 | 1.68 | 8.3 | 28/14/29/0 | 0.111 | 0.186 | 0.7 |
| FOR_IKILI_DIP | GF1 | 15m | long | 16914 | 10206 | 51.0% | -0.148 | -1507.9 | 0.64 | 1546.4 | 3165/4454/2587/0 | -0.118 | -0.029 | -2.8 |
| FOR_IKILI_DIP | GF1 | 15m | short | 17192 | 10234 | 54.3% | -0.095 | -974.7 | 0.75 | 1000.6 | 2972/4873/2389/0 | -0.107 | 0.012 | 1.1 |
| FOR_IKILI_DIP | GF1 | 15m | hepsi | 34106 | 20440 | 52.7% | -0.121 | -2482.5 | 0.70 | 2485.4 | 6137/9327/4976/0 | -0.113 | -0.009 | -1.1 |
| FOR_IKILI_DIP | GF1 | 1h | long | 4164 | 2872 | 53.5% | -0.104 | -299.8 | 0.74 | 341.2 | 914/1374/584/0 | -0.090 | -0.014 | -0.7 |
| FOR_IKILI_DIP | GF1 | 1h | short | 4148 | 2895 | 56.0% | -0.059 | -171.6 | 0.84 | 209.6 | 891/1452/552/0 | -0.060 | 0.000 | 0.0 |
| FOR_IKILI_DIP | GF1 | 1h | hepsi | 8312 | 5767 | 54.7% | -0.082 | -471.4 | 0.79 | 491.6 | 1805/2826/1136/0 | -0.075 | -0.007 | -0.5 |
| FOR_IKILI_DIP | GF1 | 4h | long | 767 | 561 | 59.0% | -0.006 | -3.2 | 0.98 | 29.2 | 186/318/57/0 | -0.085 | 0.079 | 1.7 |
| FOR_IKILI_DIP | GF1 | 4h | short | 797 | 616 | 55.8% | -0.034 | -20.7 | 0.91 | 61.2 | 210/317/89/0 | -0.027 | -0.007 | -0.1 |
| FOR_IKILI_DIP | GF1 | 4h | hepsi | 1564 | 1177 | 57.3% | -0.020 | -24.0 | 0.95 | 70.2 | 396/635/146/0 | -0.055 | 0.034 | 1.0 |
| FOR_IKILI_DIP | GF1 | 1d | long | 52 | 43 | 53.5% | -0.094 | -4.0 | 0.79 | 8.3 | 18/23/2/0 | -0.050 | -0.044 | yetersiz |
| FOR_IKILI_DIP | GF1 | 1d | short | 37 | 29 | 58.6% | 0.027 | 0.8 | 1.07 | 4.7 | 11/17/1/0 | 0.069 | -0.042 | yetersiz |
| FOR_IKILI_DIP | GF1 | 1d | hepsi | 89 | 72 | 55.6% | -0.045 | -3.3 | 0.89 | 8.8 | 29/40/3/0 | -0.002 | -0.043 | -0.3 |
| FOR_OBO | GF1 | 15m | long | 134 | 94 | 45.7% | -0.204 | -19.2 | 0.54 | 21.6 | 31/37/26/0 | -0.124 | -0.080 | -0.7 |
| FOR_OBO | GF1 | 15m | short | 159 | 123 | 50.4% | -0.128 | -15.7 | 0.69 | 20.5 | 38/59/26/0 | -0.073 | -0.055 | -0.6 |
| FOR_OBO | GF1 | 15m | hepsi | 293 | 217 | 48.4% | -0.161 | -34.9 | 0.62 | 37.1 | 69/96/52/0 | -0.095 | -0.066 | -0.9 |
| FOR_OBO | GF1 | 1h | long | 33 | 30 | 50.0% | -0.156 | -4.7 | 0.70 | 8.3 | 13/13/4/0 | -0.100 | -0.057 | yetersiz |
| FOR_OBO | GF1 | 1h | short | 29 | 29 | 44.8% | -0.265 | -7.7 | 0.45 | 8.0 | 11/11/7/0 | -0.085 | -0.180 | yetersiz |
| FOR_OBO | GF1 | 1h | hepsi | 62 | 59 | 47.5% | -0.210 | -12.4 | 0.58 | 14.5 | 24/24/11/0 | -0.092 | -0.117 | -0.7 |
| FOR_OBO | GF1 | 4h | long | 5 | 5 | 80.0% | 1.012 | 5.1 | 20.98 | 0.3 | 0/4/1/0 | -0.122 | 1.135 | yetersiz |
| FOR_OBO | GF1 | 4h | short | 5 | 5 | 40.0% | -0.209 | -1.0 | 0.68 | 3.3 | 3/2/0/0 | -0.139 | -0.070 | yetersiz |
| FOR_OBO | GF1 | 4h | hepsi | 10 | 10 | 60.0% | 0.402 | 4.0 | 2.14 | 3.5 | 3/6/1/0 | -0.131 | 0.533 | yetersiz |
| FOR_OBO | GF1 | 1d | long | 1 | 1 | 0.0% | -1.035 | -1.0 | 0.00 | 1.0 | 1/0/0/0 | -0.385 | -0.650 | yetersiz |
| FOR_OBO | GF1 | 1d | short | 1 | 1 | 100.0% | 1.643 | 1.6 | - | 0.0 | 0/1/0/0 | 0.154 | 1.489 | yetersiz |
| FOR_OBO | GF1 | 1d | hepsi | 2 | 2 | 50.0% | 0.304 | 0.6 | 1.59 | 1.0 | 1/1/0/0 | -0.115 | 0.419 | yetersiz |
| IND_RSI_3070 | IN1 | 15m | long | 7026 | 505 | 29.7% | -0.179 | -90.4 | 0.77 | 111.0 | 326/0/140/39 | -0.262 | 0.083 | 0.7 |
| IND_RSI_3070 | IN1 | 15m | short | 7010 | 399 | 27.1% | -0.208 | -82.8 | 0.75 | 117.7 | 274/0/93/32 | -0.188 | -0.019 | -0.1 |
| IND_RSI_3070 | IN1 | 15m | hepsi | 14036 | 904 | 28.5% | -0.192 | -173.2 | 0.76 | 210.0 | 600/0/233/71 | -0.230 | 0.038 | 0.4 |
| IND_RSI_3070 | IN1 | 1h | long | 1991 | 448 | 20.5% | -0.270 | -120.9 | 0.71 | 138.8 | 349/0/60/39 | -0.192 | -0.077 | -0.5 |
| IND_RSI_3070 | IN1 | 1h | short | 2083 | 420 | 21.4% | -0.002 | -1.0 | 1.00 | 80.7 | 325/0/42/53 | -0.149 | 0.146 | 0.8 |
| IND_RSI_3070 | IN1 | 1h | hepsi | 4074 | 868 | 21.0% | -0.140 | -121.9 | 0.85 | 174.6 | 674/0/102/92 | -0.171 | 0.031 | 0.3 |
| IND_RSI_3070 | IN1 | 4h | long | 472 | 217 | 12.0% | -0.415 | -90.1 | 0.58 | 90.1 | 187/0/15/15 | -0.147 | -0.269 | -0.9 |
| IND_RSI_3070 | IN1 | 4h | short | 497 | 200 | 15.0% | -0.055 | -11.1 | 0.94 | 79.3 | 170/0/16/14 | 0.009 | -0.064 | -0.2 |
| IND_RSI_3070 | IN1 | 4h | hepsi | 969 | 417 | 13.4% | -0.243 | -101.2 | 0.75 | 149.5 | 357/0/31/29 | -0.072 | -0.170 | -0.8 |
| IND_RSI_3070 | IN1 | 1d | long | 54 | 46 | 4.3% | -0.842 | -38.7 | 0.10 | 38.7 | 38/0/8/0 | -0.208 | -0.634 | yetersiz |
| IND_RSI_3070 | IN1 | 1d | short | 72 | 59 | 10.2% | -0.055 | -3.2 | 0.94 | 32.3 | 53/0/2/4 | 0.210 | -0.265 | -0.4 |
| IND_RSI_3070 | IN1 | 1d | hepsi | 126 | 105 | 7.6% | -0.400 | -42.0 | 0.57 | 51.9 | 91/0/10/4 | 0.027 | -0.427 | -0.9 |
| IND_MA_KESISIM | IN1 | 15m | long | 4637 | 4633 | 39.6% | -0.344 | -1592.8 | 0.71 | 1758.4 | 0/0/3688/945 | -0.381 | 0.038 | 0.6 |
| IND_MA_KESISIM | IN1 | 15m | short | 4622 | 4619 | 40.7% | -0.373 | -1724.8 | 0.68 | 1823.9 | 0/0/3685/934 | -0.428 | 0.054 | 0.8 |
| IND_MA_KESISIM | IN1 | 15m | hepsi | 9259 | 9252 | 40.2% | -0.359 | -3317.6 | 0.70 | 3475.6 | 0/0/7373/1879 | -0.404 | 0.046 | 1.0 |
| IND_MA_KESISIM | IN1 | 1h | long | 1089 | 1087 | 43.5% | -0.015 | -15.8 | 0.99 | 284.1 | 0/0/837/250 | -0.126 | 0.111 | 0.8 |
| IND_MA_KESISIM | IN1 | 1h | short | 1115 | 1115 | 42.3% | -0.134 | -148.9 | 0.87 | 311.0 | 0/0/899/216 | -0.071 | -0.062 | -0.5 |
| IND_MA_KESISIM | IN1 | 1h | hepsi | 2204 | 2202 | 42.9% | -0.075 | -164.7 | 0.93 | 458.4 | 0/0/1736/466 | -0.098 | 0.023 | 0.3 |
| IND_MA_KESISIM | IN1 | 4h | long | 263 | 263 | 38.0% | -0.124 | -32.6 | 0.89 | 129.2 | 0/0/202/61 | -0.054 | -0.070 | -0.3 |
| IND_MA_KESISIM | IN1 | 4h | short | 273 | 269 | 49.4% | -0.253 | -68.1 | 0.79 | 117.7 | 0/0/204/65 | -0.044 | -0.209 | -0.8 |
| IND_MA_KESISIM | IN1 | 4h | hepsi | 536 | 532 | 43.8% | -0.189 | -100.7 | 0.84 | 184.5 | 0/0/406/126 | -0.049 | -0.140 | -0.8 |
| IND_MA_KESISIM | IN1 | 1d | long | 35 | 34 | 32.4% | -0.132 | -4.5 | 0.87 | 25.9 | 0/0/28/6 | -0.355 | 0.224 | yetersiz |
| IND_MA_KESISIM | IN1 | 1d | short | 28 | 21 | 61.9% | 0.694 | 14.6 | 3.40 | 2.2 | 0/0/18/3 | 0.480 | 0.214 | yetersiz |
| IND_MA_KESISIM | IN1 | 1d | hepsi | 63 | 55 | 43.6% | 0.184 | 10.1 | 1.24 | 25.9 | 0/0/46/9 | -0.036 | 0.220 | 0.5 |
| IND_BOLL_DONUS | IN1 | 15m | long | 196040 | 18140 | 45.5% | -0.226 | -4091.3 | 0.59 | 4098.9 | 8200/9940/0/0 | -0.226 | 0.001 | 0.1 |
| IND_BOLL_DONUS | IN1 | 15m | short | 188392 | 14738 | 46.7% | -0.196 | -2895.4 | 0.64 | 2935.2 | 6532/8206/0/0 | -0.129 | -0.067 | -5.4 |
| IND_BOLL_DONUS | IN1 | 15m | hepsi | 384432 | 32878 | 46.1% | -0.213 | -6986.7 | 0.61 | 7024.5 | 14732/18146/0/0 | -0.183 | -0.030 | -3.6 |
| IND_BOLL_DONUS | IN1 | 1h | long | 52424 | 13358 | 41.2% | -0.211 | -2820.0 | 0.67 | 2841.6 | 7142/6216/0/0 | -0.189 | -0.022 | -1.4 |
| IND_BOLL_DONUS | IN1 | 1h | short | 50497 | 11359 | 44.1% | -0.176 | -1997.7 | 0.71 | 2045.3 | 5778/5581/0/0 | -0.131 | -0.045 | -2.6 |
| IND_BOLL_DONUS | IN1 | 1h | hepsi | 102921 | 24717 | 42.5% | -0.195 | -4817.6 | 0.69 | 4845.3 | 12920/11797/0/0 | -0.162 | -0.033 | -2.9 |
| IND_BOLL_DONUS | IN1 | 4h | long | 12902 | 5884 | 35.2% | -0.209 | -1228.5 | 0.71 | 1291.8 | 3653/2231/0/0 | -0.208 | -0.001 | -0.0 |
| IND_BOLL_DONUS | IN1 | 4h | short | 11886 | 4835 | 38.4% | -0.128 | -617.9 | 0.81 | 672.3 | 2852/1983/0/0 | -0.107 | -0.021 | -0.7 |
| IND_BOLL_DONUS | IN1 | 4h | hepsi | 24788 | 10719 | 36.7% | -0.172 | -1846.4 | 0.75 | 1904.4 | 6505/4214/0/0 | -0.162 | -0.010 | -0.5 |
| IND_BOLL_DONUS | IN1 | 1d | long | 1430 | 936 | 24.7% | -0.198 | -185.7 | 0.75 | 281.6 | 690/245/1/0 | -0.213 | 0.014 | 0.2 |
| IND_BOLL_DONUS | IN1 | 1d | short | 1316 | 809 | 31.5% | -0.115 | -92.7 | 0.84 | 132.1 | 554/255/0/0 | -0.040 | -0.074 | -0.8 |
| IND_BOLL_DONUS | IN1 | 1d | hepsi | 2746 | 1745 | 27.9% | -0.160 | -278.4 | 0.79 | 323.1 | 1244/500/1/0 | -0.133 | -0.027 | -0.4 |
| IND_FIYAT_MA | IN1 | 15m | long | 57299 | 57272 | 13.4% | -0.437 | -25010.5 | 0.40 | 25188.1 | 0/0/4222/53050 | -0.361 | -0.076 | -4.7 |
| IND_FIYAT_MA | IN1 | 15m | short | 57315 | 57264 | 13.5% | -0.445 | -25468.5 | 0.39 | 25498.7 | 0/0/4283/52981 | -0.408 | -0.037 | -2.4 |
| IND_FIYAT_MA | IN1 | 15m | hepsi | 114614 | 114536 | 13.5% | -0.441 | -50479.1 | 0.39 | 50622.6 | 0/0/8505/106031 | -0.384 | -0.057 | -5.1 |
| IND_FIYAT_MA | IN1 | 1h | long | 12850 | 12814 | 16.1% | -0.140 | -1795.0 | 0.71 | 1998.6 | 0/0/986/11828 | -0.140 | -0.001 | -0.0 |
| IND_FIYAT_MA | IN1 | 1h | short | 12837 | 12828 | 17.4% | -0.131 | -1682.6 | 0.73 | 1809.4 | 0/0/1193/11635 | -0.147 | 0.016 | 0.5 |
| IND_FIYAT_MA | IN1 | 1h | hepsi | 25687 | 25642 | 16.7% | -0.136 | -3477.6 | 0.72 | 3647.3 | 0/0/2179/23463 | -0.143 | 0.008 | 0.3 |
| IND_FIYAT_MA | IN1 | 4h | long | 2883 | 2872 | 17.2% | 0.003 | 7.5 | 1.01 | 253.0 | 0/0/198/2674 | -0.165 | 0.168 | 2.6 |
| IND_FIYAT_MA | IN1 | 4h | short | 2906 | 2880 | 20.3% | 0.010 | 30.2 | 1.03 | 279.0 | 0/0/317/2563 | -0.068 | 0.078 | 1.3 |
| IND_FIYAT_MA | IN1 | 4h | hepsi | 5789 | 5752 | 18.8% | 0.007 | 37.7 | 1.02 | 295.5 | 0/0/515/5237 | -0.116 | 0.123 | 2.8 |
| IND_FIYAT_MA | IN1 | 1d | long | 317 | 317 | 15.8% | 0.105 | 33.3 | 1.30 | 67.7 | 0/0/24/293 | -0.348 | 0.453 | 2.6 |
| IND_FIYAT_MA | IN1 | 1d | short | 324 | 303 | 23.4% | 0.188 | 56.8 | 1.67 | 25.7 | 0/0/47/256 | 0.336 | -0.148 | -0.9 |
| IND_FIYAT_MA | IN1 | 1d | hepsi | 641 | 620 | 19.5% | 0.145 | 90.1 | 1.46 | 53.4 | 0/0/71/549 | -0.014 | 0.159 | 1.3 |

sinyal = kapanis kararinda uretilen aday sayisi; islem = acik pozisyon/MIN_RISK/bosluk/veri-sonu elemelerinden sonra simule edilen.

## Alt tur dokumu (hepsi): tur: islem, ort R, toplam R

- MUM_PINBAR 15m: pinbar: 5951, -0.235, -1399.6
- MUM_PINBAR 1h: pinbar: 3505, -0.153, -536.0
- MUM_PINBAR 4h: pinbar: 1178, -0.299, -352.6
- MUM_PINBAR 1d: pinbar: 112, -0.409, -45.9
- MUM_IC_CUBUK 15m: ic_cubuk: 30536, -0.181, -5515.8
- MUM_IC_CUBUK 1h: ic_cubuk: 14557, -0.138, -2008.6
- MUM_IC_CUBUK 4h: ic_cubuk: 4670, -0.092, -431.7
- MUM_IC_CUBUK 1d: ic_cubuk: 573, -0.095, -54.4
- MUM_YUTAN 15m: yutan: 14231, -0.206, -2937.3
- MUM_YUTAN 1h: yutan: 8434, -0.166, -1399.7
- MUM_YUTAN 4h: yutan: 2870, -0.065, -186.3
- MUM_YUTAN 1d: yutan: 387, 0.065, 25.1
- MUM_YILDIZ 15m: yildiz: 46, 0.200, 9.2
- MUM_YILDIZ 1h: yildiz: 93, -0.103, -9.5
- MUM_YILDIZ 4h: yildiz: 110, -0.177, -19.5
- MUM_YILDIZ 1d: yildiz: 39, -0.640, -25.0
- FOR_YATAY_KIRILIM 15m: yatay: 16899, -0.196, -3314.0
- FOR_YATAY_KIRILIM 1h: yatay: 7650, -0.153, -1166.6
- FOR_YATAY_KIRILIM 4h: yatay: 2117, -0.093, -196.9
- FOR_YATAY_KIRILIM 1d: yatay: 145, 0.234, 34.0
- FOR_UCGEN 15m: alcalan: 108, -0.013, -1.4; simetrik: 6359, -0.147, -935.1; yukselen: 118, -0.001, -0.1
- FOR_UCGEN 1h: alcalan: 37, -0.164, -6.1; simetrik: 1990, -0.017, -33.4; yukselen: 38, 0.127, 4.8
- FOR_UCGEN 4h: alcalan: 6, 0.377, 2.3; simetrik: 569, -0.002, -1.1; yukselen: 8, -0.466, -3.7
- FOR_UCGEN 1d: simetrik: 71, 0.298, 21.1
- FOR_IKILI_DIP 15m: ikili_dip: 10206, -0.148, -1507.9; ikili_tepe: 10234, -0.095, -974.7
- FOR_IKILI_DIP 1h: ikili_dip: 2872, -0.104, -299.8; ikili_tepe: 2895, -0.059, -171.6
- FOR_IKILI_DIP 4h: ikili_dip: 561, -0.006, -3.2; ikili_tepe: 616, -0.034, -20.7
- FOR_IKILI_DIP 1d: ikili_dip: 43, -0.094, -4.0; ikili_tepe: 29, 0.027, 0.8
- FOR_OBO 15m: obo: 123, -0.128, -15.7; tobo: 94, -0.204, -19.2
- FOR_OBO 1h: obo: 29, -0.265, -7.7; tobo: 30, -0.156, -4.7
- FOR_OBO 4h: obo: 5, -0.209, -1.0; tobo: 5, 1.012, 5.1
- FOR_OBO 1d: obo: 1, 1.643, 1.6; tobo: 1, -1.035, -1.0
- IND_RSI_3070 15m: rsi: 904, -0.192, -173.2
- IND_RSI_3070 1h: rsi: 868, -0.140, -121.9
- IND_RSI_3070 4h: rsi: 417, -0.243, -101.2
- IND_RSI_3070 1d: rsi: 105, -0.400, -42.0
- IND_MA_KESISIM 15m: ma_kesisim: 9252, -0.359, -3317.6
- IND_MA_KESISIM 1h: ma_kesisim: 2202, -0.075, -164.7
- IND_MA_KESISIM 4h: ma_kesisim: 532, -0.189, -100.7
- IND_MA_KESISIM 1d: ma_kesisim: 55, 0.184, 10.1
- IND_BOLL_DONUS 15m: boll: 32878, -0.213, -6986.7
- IND_BOLL_DONUS 1h: boll: 24717, -0.195, -4817.6
- IND_BOLL_DONUS 4h: boll: 10719, -0.172, -1846.4
- IND_BOLL_DONUS 1d: boll: 1745, -0.160, -278.4
- IND_FIYAT_MA 15m: fiyat_ma: 114536, -0.441, -50479.1
- IND_FIYAT_MA 1h: fiyat_ma: 25642, -0.136, -3477.6
- IND_FIYAT_MA 4h: fiyat_ma: 5752, 0.007, 37.7
- IND_FIYAT_MA 1d: fiyat_ma: 620, 0.145, 90.1

## Yil yil toplam R (hepsi)

- MUM_PINBAR 15m: 2025: -519.8, 2026: -879.8
- MUM_PINBAR 1h: 2025: -248.9, 2026: -287.0
- MUM_PINBAR 4h: 2025: -90.4, 2026: -262.2
- MUM_PINBAR 1d: 2025: -16.5, 2026: -29.4
- MUM_IC_CUBUK 15m: 2025: -1591.7, 2026: -3924.1
- MUM_IC_CUBUK 1h: 2025: -474.5, 2026: -1534.1
- MUM_IC_CUBUK 4h: 2025: -96.0, 2026: -335.6
- MUM_IC_CUBUK 1d: 2025: -46.3, 2026: -8.1
- MUM_YUTAN 15m: 2025: -1006.0, 2026: -1931.3
- MUM_YUTAN 1h: 2025: -437.7, 2026: -962.0
- MUM_YUTAN 4h: 2025: -5.8, 2026: -180.5
- MUM_YUTAN 1d: 2025: 37.6, 2026: -12.5
- MUM_YILDIZ 15m: 2025: 13.6, 2026: -4.4
- MUM_YILDIZ 1h: 2025: 4.2, 2026: -13.7
- MUM_YILDIZ 4h: 2025: -17.5, 2026: -2.0
- MUM_YILDIZ 1d: 2025: 3.2, 2026: -28.2
- FOR_YATAY_KIRILIM 15m: 2025: -1130.6, 2026: -2183.4
- FOR_YATAY_KIRILIM 1h: 2025: -434.1, 2026: -732.6
- FOR_YATAY_KIRILIM 4h: 2025: -27.3, 2026: -169.6
- FOR_YATAY_KIRILIM 1d: 2025: 12.5, 2026: 21.5
- FOR_UCGEN 15m: 2025: -230.7, 2026: -705.9
- FOR_UCGEN 1h: 2025: 17.5, 2026: -52.1
- FOR_UCGEN 4h: 2025: 17.3, 2026: -19.9
- FOR_UCGEN 1d: 2025: 19.1, 2026: 2.0
- FOR_IKILI_DIP 15m: 2025: -463.4, 2026: -2019.2
- FOR_IKILI_DIP 1h: 2025: -77.5, 2026: -393.9
- FOR_IKILI_DIP 4h: 2025: 22.4, 2026: -46.4
- FOR_IKILI_DIP 1d: 2025: -0.3, 2026: -2.9
- FOR_OBO 15m: 2025: -1.4, 2026: -33.5
- FOR_OBO 1h: 2025: -6.8, 2026: -5.6
- FOR_OBO 4h: 2026: 4.0
- FOR_OBO 1d: 2025: 1.6, 2026: -1.0
- IND_RSI_3070 15m: 2025: -12.8, 2026: -160.4
- IND_RSI_3070 1h: 2025: -56.3, 2026: -65.5
- IND_RSI_3070 4h: 2025: 28.9, 2026: -130.1
- IND_RSI_3070 1d: 2025: -16.9, 2026: -25.0
- IND_MA_KESISIM 15m: 2025: -421.9, 2026: -2895.6
- IND_MA_KESISIM 1h: 2025: -26.4, 2026: -138.3
- IND_MA_KESISIM 4h: 2025: -88.4, 2026: -12.3
- IND_MA_KESISIM 1d: 2025: 21.6, 2026: -11.5
- IND_BOLL_DONUS 15m: 2025: -2570.0, 2026: -4416.7
- IND_BOLL_DONUS 1h: 2025: -1508.1, 2026: -3309.6
- IND_BOLL_DONUS 4h: 2025: -391.2, 2026: -1455.2
- IND_BOLL_DONUS 1d: 2025: 29.5, 2026: -308.0
- IND_FIYAT_MA 15m: 2025: -4153.5, 2026: -46325.6
- IND_FIYAT_MA 1h: 2025: -303.1, 2026: -3174.5
- IND_FIYAT_MA 4h: 2025: 96.6, 2026: -58.9
- IND_FIYAT_MA 1d: 2025: 25.6, 2026: 64.6

## Cift dagilimi (hepsi): en iyi / en kotu 5 (toplam R) ve islem veren cift sayisi

- MUM_PINBAR 15m (43 cift): iyi [XAU/USDT 1.9, COPPER/USDT 1.0, COST/USDT -1.3, XOM/USDT -1.4, AAPL/USDT -2.1]; kotu [HYPE/USDT -115.4, DOT/USDT -100.6, LINK/USDT -95.8, SUI/USDT -89.6, ADA/USDT -75.7]
- MUM_PINBAR 1h (43 cift): iyi [WMT/USDT 8.2, GOOGL/USDT 6.2, BTC/USDT 5.9, COST/USDT 5.7, SOL/USDT 3.3]; kotu [1000SHIB/USDT -57.5, ADA/USDT -53.1, LINK/USDT -43.3, DOGE/USDT -37.2, HYPE/USDT -36.4]
- MUM_PINBAR 4h (43 cift): iyi [NFLX/USDT 5.5, ORCL/USDT 4.6, HD/USDT 3.4, AVGO/USDT 1.9, GOOGL/USDT 1.3]; kotu [AVAX/USDT -32.2, XRP/USDT -27.0, SOL/USDT -26.5, ETH/USDT -21.5, BTC/USDT -21.2]
- MUM_PINBAR 1d (22 cift): iyi [TRX/USDT 5.1, BCH/USDT 4.6, HBAR/USDT 2.9, XMR/USDT 0.1, HYPE/USDT -1.0]; kotu [LINK/USDT -7.3, SUI/USDT -6.7, AVAX/USDT -6.3, XRP/USDT -4.4, BNB/USDT -4.4]
- MUM_IC_CUBUK 15m (43 cift): iyi [AAPL/USDT -7.3, NFLX/USDT -10.1, BRKB/USDT -15.4, COST/USDT -15.9, HD/USDT -16.0]; kotu [XMR/USDT -486.8, DOT/USDT -348.8, XLM/USDT -309.1, HYPE/USDT -291.4, ADA/USDT -271.7]
- MUM_IC_CUBUK 1h (43 cift): iyi [BRKB/USDT 0.2, ORCL/USDT -2.1, XOM/USDT -3.5, BZ/USDT -7.8, LLY/USDT -9.8]; kotu [ADA/USDT -137.9, ETH/USDT -127.3, XMR/USDT -126.6, XLM/USDT -116.0, BNB/USDT -111.7]
- MUM_IC_CUBUK 4h (43 cift): iyi [BNB/USDT 21.0, ETH/USDT 16.7, XLM/USDT 12.0, ADA/USDT 10.7, SOL/USDT 5.9]; kotu [TRX/USDT -38.8, LTC/USDT -36.2, COPPER/USDT -29.8, AAPL/USDT -28.6, GOOGL/USDT -27.5]
- MUM_IC_CUBUK 1d (22 cift): iyi [ETH/USDT 7.1, SOL/USDT 6.7, DOGE/USDT 4.9, HYPE/USDT 4.7, BTC/USDT 2.8]; kotu [BCH/USDT -17.7, AVAX/USDT -13.1, LINK/USDT -11.5, XLM/USDT -9.7, LTC/USDT -8.6]
- MUM_YUTAN 15m (43 cift): iyi [MSFT/USDT 3.4, META/USDT 3.0, HD/USDT 0.2, NVDA/USDT -1.3, COST/USDT -1.7]; kotu [XMR/USDT -280.8, DOT/USDT -241.3, XLM/USDT -230.1, SUI/USDT -198.7, ADA/USDT -178.8]
- MUM_YUTAN 1h (43 cift): iyi [MSFT/USDT 4.6, BRKB/USDT 4.5, BTC/USDT 4.2, HD/USDT -2.0, WMT/USDT -3.6]; kotu [HBAR/USDT -106.8, XMR/USDT -90.0, HYPE/USDT -86.3, DOT/USDT -83.7, AVAX/USDT -81.0]
- MUM_YUTAN 4h (43 cift): iyi [TRX/USDT 32.6, NVDA/USDT 17.4, 1000SHIB/USDT 10.8, HYPE/USDT 10.4, XLM/USDT 8.9]; kotu [BTC/USDT -48.8, BNB/USDT -39.8, SUI/USDT -23.1, XRP/USDT -21.2, DOT/USDT -17.7]
- MUM_YUTAN 1d (22 cift): iyi [ADA/USDT 11.5, BTC/USDT 9.7, SUI/USDT 8.9, SOL/USDT 5.8, TSLA/USDT 5.6]; kotu [LINK/USDT -7.6, AVAX/USDT -6.6, DOT/USDT -4.8, HYPE/USDT -4.6, XMR/USDT -3.2]
- MUM_YILDIZ 15m (20 cift): iyi [AVAX/USDT 5.2, XLM/USDT 4.8, DOT/USDT 2.5, HBAR/USDT 2.5, SOL/USDT 2.0]; kotu [ADA/USDT -2.8, HYPE/USDT -1.8, AMD/USDT -1.2, SUI/USDT -1.1, DOGE/USDT -1.0]
- MUM_YILDIZ 1h (23 cift): iyi [ETH/USDT 3.9, SUI/USDT 3.5, AVAX/USDT 1.7, XAG/USDT 1.3, AVGO/USDT 1.1]; kotu [XMR/USDT -5.2, DOGE/USDT -3.5, ADA/USDT -2.3, HYPE/USDT -2.2, XRP/USDT -2.0]
- MUM_YILDIZ 4h (21 cift): iyi [ETH/USDT 6.8, HBAR/USDT 4.1, TSLA/USDT 2.9, SOL/USDT 2.0, BZ/USDT 2.0]; kotu [LINK/USDT -8.4, SUI/USDT -5.4, LTC/USDT -5.4, 1000SHIB/USDT -5.2, ADA/USDT -4.2]
- MUM_YILDIZ 1d (14 cift): iyi [SOL/USDT 1.9, BNB/USDT 0.8, XLM/USDT -0.2, XMR/USDT -1.0, AVAX/USDT -1.1]; kotu [XRP/USDT -5.5, SUI/USDT -3.2, 1000SHIB/USDT -3.2, HBAR/USDT -3.1, DOT/USDT -2.1]
- FOR_YATAY_KIRILIM 15m (43 cift): iyi [XAU/USDT 4.5, COST/USDT -2.4, HD/USDT -4.2, BRKB/USDT -8.7, XOM/USDT -9.1]; kotu [XMR/USDT -293.4, HYPE/USDT -260.9, SUI/USDT -167.5, LTC/USDT -165.5, DOT/USDT -157.4]
- FOR_YATAY_KIRILIM 1h (43 cift): iyi [AMD/USDT 6.8, XAG/USDT 2.9, BNB/USDT -3.1, JPM/USDT -4.1, SUI/USDT -4.4]; kotu [HYPE/USDT -86.5, XMR/USDT -81.0, LINK/USDT -69.8, DOGE/USDT -49.3, LTC/USDT -48.5]
- FOR_YATAY_KIRILIM 4h (43 cift): iyi [XLM/USDT 10.7, 1000SHIB/USDT 6.4, AMD/USDT 5.8, BNB/USDT 5.3, XAU/USDT 5.1]; kotu [BTC/USDT -35.8, HYPE/USDT -19.4, PLTR/USDT -15.4, AAPL/USDT -14.5, ETH/USDT -13.3]
- FOR_YATAY_KIRILIM 1d (22 cift): iyi [TRX/USDT 11.9, DOT/USDT 5.7, ETH/USDT 5.2, XRP/USDT 4.6, LINK/USDT 4.2]; kotu [ADA/USDT -4.2, TSLA/USDT -2.1, SUI/USDT -1.8, XMR/USDT -1.8, 1000SHIB/USDT -1.4]
- FOR_UCGEN 15m (43 cift): iyi [BCH/USDT 16.9, COPPER/USDT 0.1, COST/USDT -0.9, XOM/USDT -1.0, BRKB/USDT -2.8]; kotu [SUI/USDT -72.8, LINK/USDT -60.2, XLM/USDT -59.1, BNB/USDT -56.6, HBAR/USDT -49.4]
- FOR_UCGEN 1h (43 cift): iyi [ETH/USDT 27.5, XRP/USDT 23.6, SUI/USDT 21.0, XAG/USDT 14.5, BTC/USDT 10.7]; kotu [PLTR/USDT -19.9, BCH/USDT -16.0, XLM/USDT -14.9, TSLA/USDT -12.0, DOT/USDT -11.7]
- FOR_UCGEN 4h (42 cift): iyi [SUI/USDT 12.1, XRP/USDT 11.0, AVGO/USDT 7.3, AVAX/USDT 4.9, HBAR/USDT 4.9]; kotu [ETH/USDT -8.3, 1000SHIB/USDT -7.0, XMR/USDT -6.5, LLY/USDT -5.8, XAG/USDT -4.9]
- FOR_UCGEN 1d (20 cift): iyi [ETH/USDT 6.5, BTC/USDT 5.3, XMR/USDT 4.9, AVAX/USDT 4.9, TRX/USDT 3.9]; kotu [1000SHIB/USDT -4.0, XRP/USDT -2.8, BNB/USDT -2.4, HYPE/USDT -1.9, DOT/USDT -1.3]
- FOR_IKILI_DIP 15m (43 cift): iyi [XOM/USDT -7.1, COST/USDT -23.1, AMD/USDT -23.5, LLY/USDT -24.0, MSFT/USDT -25.6]; kotu [BCH/USDT -113.7, LTC/USDT -109.5, DOGE/USDT -96.7, XLM/USDT -91.7, XMR/USDT -91.6]
- FOR_IKILI_DIP 1h (43 cift): iyi [XLM/USDT 6.3, BZ/USDT 6.1, HBAR/USDT 2.7, COST/USDT -0.8, XOM/USDT -0.9]; kotu [HYPE/USDT -38.0, GOOGL/USDT -29.3, ADA/USDT -26.9, LTC/USDT -24.7, SUI/USDT -24.5]
- FOR_IKILI_DIP 4h (43 cift): iyi [LTC/USDT 7.1, HBAR/USDT 7.0, BTC/USDT 6.7, XRP/USDT 6.4, ADA/USDT 5.8]; kotu [ETH/USDT -10.0, BNB/USDT -10.0, BCH/USDT -7.7, XMR/USDT -6.7, AMZN/USDT -6.5]
- FOR_IKILI_DIP 1d (21 cift): iyi [AVAX/USDT 1.8, ETH/USDT 1.0, DOGE/USDT 0.9, TRX/USDT 0.8, HYPE/USDT 0.7]; kotu [HBAR/USDT -2.6, LTC/USDT -2.0, SUI/USDT -1.3, BTC/USDT -1.1, XAU/USDT -1.0]
- FOR_OBO 15m (38 cift): iyi [XMR/USDT 6.2, SOL/USDT 4.8, LLY/USDT 2.1, HBAR/USDT 1.6, BTC/USDT 1.1]; kotu [LINK/USDT -6.5, TSLA/USDT -4.6, PLTR/USDT -3.9, DOT/USDT -3.3, HYPE/USDT -3.2]
- FOR_OBO 1h (35 cift): iyi [GOOGL/USDT 2.7, PLTR/USDT 2.0, XMR/USDT 1.2, AVAX/USDT 1.0, V/USDT 0.9]; kotu [LTC/USDT -2.8, LINK/USDT -2.5, MSFT/USDT -2.3, AAPL/USDT -2.3, META/USDT -2.0]
- FOR_OBO 4h (9 cift): iyi [ORCL/USDT 2.3, TRX/USDT 2.2, AVGO/USDT 1.3, HBAR/USDT 1.1, AMZN/USDT 0.6]; kotu [TSLA/USDT -1.2, HYPE/USDT -1.0, ADA/USDT -1.0, BRKB/USDT -0.3, AMZN/USDT 0.6]
- FOR_OBO 1d (2 cift): iyi [ETH/USDT 1.6, XRP/USDT -1.0]; kotu [XRP/USDT -1.0, ETH/USDT 1.6]
- IND_RSI_3070 15m (43 cift): iyi [ADA/USDT 22.3, SUI/USDT 14.5, LTC/USDT 6.6, BCH/USDT 5.5, META/USDT 4.2]; kotu [DOGE/USDT -37.3, XLM/USDT -27.8, DOT/USDT -19.9, HYPE/USDT -19.3, HBAR/USDT -12.1]
- IND_RSI_3070 1h (42 cift): iyi [DOT/USDT 20.7, ORCL/USDT 16.0, XAG/USDT 9.9, MSFT/USDT 8.0, BZ/USDT 6.9]; kotu [ETH/USDT -23.7, XLM/USDT -22.9, HBAR/USDT -22.5, SUI/USDT -19.5, LINK/USDT -16.6]
- IND_RSI_3070 4h (41 cift): iyi [HBAR/USDT 14.6, DOT/USDT 12.7, PLTR/USDT 10.5, XRP/USDT 9.0, LINK/USDT 6.3]; kotu [SUI/USDT -22.8, DOGE/USDT -15.1, BTC/USDT -14.1, SOL/USDT -13.6, AVAX/USDT -13.2]
- IND_RSI_3070 1d (19 cift): iyi [BTC/USDT 14.6, LINK/USDT 11.2, HBAR/USDT 2.6, AVAX/USDT 0.7, TRX/USDT 0.1]; kotu [SUI/USDT -9.9, SOL/USDT -8.6, ADA/USDT -6.9, LTC/USDT -6.4, DOT/USDT -5.6]
- IND_MA_KESISIM 15m (43 cift): iyi [BNB/USDT 32.7, SOL/USDT 30.1, XLM/USDT -3.0, NFLX/USDT -3.1, AMD/USDT -4.1]; kotu [XAU/USDT -258.8, XAG/USDT -200.6, PLTR/USDT -190.8, COST/USDT -173.2, NVDA/USDT -156.7]
- IND_MA_KESISIM 1h (43 cift): iyi [HYPE/USDT 36.8, AAPL/USDT 19.1, PLTR/USDT 17.1, AMD/USDT 16.2, SOL/USDT 13.0]; kotu [AVAX/USDT -58.1, LINK/USDT -51.9, 1000SHIB/USDT -34.7, AMZN/USDT -32.6, BRKB/USDT -27.7]
- IND_MA_KESISIM 4h (42 cift): iyi [XAU/USDT 16.5, LINK/USDT 15.5, XMR/USDT 14.4, BNB/USDT 14.0, META/USDT 12.9]; kotu [BTC/USDT -23.1, 1000SHIB/USDT -22.8, BCH/USDT -21.3, PLTR/USDT -21.3, COPPER/USDT -19.0]
- IND_MA_KESISIM 1d (19 cift): iyi [HYPE/USDT 6.2, ETH/USDT 6.0, BNB/USDT 4.4, XMR/USDT 3.9, TRX/USDT 3.5]; kotu [DOT/USDT -3.6, XRP/USDT -3.1, XLM/USDT -2.8, ADA/USDT -2.6, SUI/USDT -2.4]
- IND_BOLL_DONUS 15m (43 cift): iyi [BRKB/USDT -5.0, COST/USDT -10.1, COPPER/USDT -12.0, XOM/USDT -13.9, V/USDT -17.3]; kotu [HYPE/USDT -547.3, SUI/USDT -442.3, DOT/USDT -421.9, ADA/USDT -411.9, HBAR/USDT -385.5]
- IND_BOLL_DONUS 1h (43 cift): iyi [BRKB/USDT -8.7, XOM/USDT -13.3, COST/USDT -14.4, COPPER/USDT -15.6, HD/USDT -18.4]; kotu [SOL/USDT -268.4, HBAR/USDT -265.9, HYPE/USDT -257.4, LINK/USDT -256.1, ETH/USDT -246.6]
- IND_BOLL_DONUS 4h (43 cift): iyi [XOM/USDT -2.2, COST/USDT -3.1, LLY/USDT -7.3, BRKB/USDT -7.7, XAU/USDT -10.5]; kotu [ETH/USDT -113.8, XRP/USDT -108.4, ADA/USDT -104.4, HBAR/USDT -98.4, LTC/USDT -84.8]
- IND_BOLL_DONUS 1d (22 cift): iyi [XMR/USDT 17.9, TSLA/USDT 11.8, SUI/USDT 2.9, XAU/USDT 2.8, BCH/USDT 2.2]; kotu [XRP/USDT -39.7, DOGE/USDT -37.3, HBAR/USDT -28.9, ETH/USDT -28.6, XLM/USDT -23.6]
- IND_FIYAT_MA 15m (43 cift): iyi [XOM/USDT -341.8, AMD/USDT -429.9, AVAX/USDT -484.8, HYPE/USDT -492.2, LINK/USDT -514.6]; kotu [XAU/USDT -4128.7, XAG/USDT -2211.3, AMZN/USDT -2107.5, BRKB/USDT -2053.9, AAPL/USDT -1911.1]
- IND_FIYAT_MA 1h (43 cift): iyi [BZ/USDT 23.5, ORCL/USDT -0.2, ETH/USDT -3.6, XOM/USDT -3.7, HYPE/USDT -5.4]; kotu [AAPL/USDT -203.8, COST/USDT -173.8, JPM/USDT -171.8, XMR/USDT -170.1, COPPER/USDT -147.4]
- IND_FIYAT_MA 4h (43 cift): iyi [XLM/USDT 66.1, XRP/USDT 29.6, SUI/USDT 28.9, SOL/USDT 27.4, PLTR/USDT 25.8]; kotu [AAPL/USDT -36.0, GOOGL/USDT -28.1, JPM/USDT -26.4, AVAX/USDT -20.0, TRX/USDT -19.8]
- IND_FIYAT_MA 1d (22 cift): iyi [ETH/USDT 20.6, BTC/USDT 13.1, BNB/USDT 12.4, LINK/USDT 11.0, XRP/USDT 11.0]; kotu [TRX/USDT -7.4, DOT/USDT -5.8, TSLA/USDT -3.2, BCH/USDT -2.1, 1000SHIB/USDT -1.3]

## Veri kapsami (cift x zd: mum sayisi, ilk tarih). Kisa gecmisli ya da arsivde olmayan ciftler

- HYPE/USDT 15m: 52086 mum, 2025-05-30 -> 2026-11-23 (kisa gecmis)
- HYPE/USDT 1h: 13022 mum, 2025-05-30 -> 2026-11-23 (kisa gecmis)
- HYPE/USDT 4h: 3256 mum, 2025-05-30 -> 2026-11-23 (kisa gecmis)
- HYPE/USDT 1d: 543 mum, 2025-05-30 -> 2026-11-23 (kisa gecmis)
- SUI/USDT 15m: 124832 mum, 2023-05-03 -> 2026-11-23 (kisa gecmis)
- SUI/USDT 1h: 31208 mum, 2023-05-03 -> 2026-11-23 (kisa gecmis)
- SUI/USDT 4h: 7802 mum, 2023-05-03 -> 2026-11-23 (kisa gecmis)
- SUI/USDT 1d: 1301 mum, 2023-05-03 -> 2026-11-23 (kisa gecmis)
- HBAR/USDT 1h: 49745 mum, 2021-03-17 -> 2026-11-23 (kisa gecmis)
- HBAR/USDT 4h: 12437 mum, 2021-03-17 -> 2026-11-23 (kisa gecmis)
- HBAR/USDT 1d: 2073 mum, 2021-03-17 -> 2026-11-23 (kisa gecmis)
- 1000SHIB/USDT 1h: 48559 mum, 2021-05-10 -> 2026-11-23 (kisa gecmis)
- 1000SHIB/USDT 4h: 12140 mum, 2021-05-10 -> 2026-11-23 (kisa gecmis)
- 1000SHIB/USDT 1d: 2024 mum, 2021-05-10 -> 2026-11-23 (kisa gecmis)
- NVDA/USDT 15m: 23270 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- NVDA/USDT 1h: 5818 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- NVDA/USDT 4h: 1455 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- NVDA/USDT 1d: 243 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- MSFT/USDT 15m: 20874 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- MSFT/USDT 1h: 5219 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- MSFT/USDT 4h: 1305 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- MSFT/USDT 1d: 218 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- AAPL/USDT 15m: 22217 mum, 2026-04-06 -> 2026-11-23 (kisa gecmis)
- AAPL/USDT 1h: 5555 mum, 2026-04-06 -> 2026-11-23 (kisa gecmis)
- AAPL/USDT 4h: 1389 mum, 2026-04-06 -> 2026-11-23 (kisa gecmis)
- AAPL/USDT 1d: 232 mum, 2026-04-06 -> 2026-11-23 (kisa gecmis)
- GOOGL/USDT 15m: 23269 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- GOOGL/USDT 1h: 5818 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- GOOGL/USDT 4h: 1455 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- GOOGL/USDT 1d: 243 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- AMZN/USDT 15m: 27590 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- AMZN/USDT 1h: 6898 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- AMZN/USDT 4h: 1725 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- AMZN/USDT 1d: 288 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- META/USDT 15m: 23270 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- META/USDT 1h: 5818 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- META/USDT 4h: 1455 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- META/USDT 1d: 243 mum, 2026-03-26 -> 2026-11-23 (kisa gecmis)
- AVGO/USDT 15m: 20874 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- AVGO/USDT 1h: 5219 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- AVGO/USDT 4h: 1305 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- AVGO/USDT 1d: 218 mum, 2026-04-20 -> 2026-11-23 (kisa gecmis)
- TSLA/USDT 15m: 28742 mum, 2026-01-28 -> 2026-11-23 (kisa gecmis)
- TSLA/USDT 1h: 7186 mum, 2026-01-28 -> 2026-11-23 (kisa gecmis)
- TSLA/USDT 4h: 1797 mum, 2026-01-28 -> 2026-11-23 (kisa gecmis)
- TSLA/USDT 1d: 300 mum, 2026-01-28 -> 2026-11-23 (kisa gecmis)
- BRKB/USDT 15m: 18185 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- BRKB/USDT 1h: 4547 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- BRKB/USDT 4h: 1137 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- BRKB/USDT 1d: 190 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- JPM/USDT 15m: 18186 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- JPM/USDT 1h: 4547 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- JPM/USDT 4h: 1137 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- JPM/USDT 1d: 190 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- LLY/USDT 15m: 16842 mum, 2026-06-01 -> 2026-11-23 (kisa gecmis)
- LLY/USDT 1h: 4211 mum, 2026-06-01 -> 2026-11-23 (kisa gecmis)
- LLY/USDT 4h: 1053 mum, 2026-06-01 -> 2026-11-23 (kisa gecmis)
- LLY/USDT 1d: 176 mum, 2026-06-01 -> 2026-11-23 (kisa gecmis)
- WMT/USDT 15m: 18186 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- WMT/USDT 1h: 4547 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- WMT/USDT 4h: 1137 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- WMT/USDT 1d: 190 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- V/USDT 15m: 18185 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- V/USDT 1h: 4547 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- V/USDT 4h: 1137 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- V/USDT 1d: 190 mum, 2026-05-18 -> 2026-11-23 (kisa gecmis)
- ORCL/USDT 15m: 18474 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- ORCL/USDT 1h: 4619 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- ORCL/USDT 4h: 1155 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- ORCL/USDT 1d: 193 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- XOM/USDT 15m: 5435 mum, 2026-09-28 -> 2026-11-23 (kisa gecmis)
- XOM/USDT 1h: 1359 mum, 2026-09-28 -> 2026-11-23 (kisa gecmis)
- XOM/USDT 4h: 340 mum, 2026-09-28 -> 2026-11-23 (kisa gecmis)
- XOM/USDT 1d: 57 mum, 2026-09-28 -> 2026-11-23 (kisa gecmis)
- NFLX/USDT 15m: 16092 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- NFLX/USDT 1h: 4023 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- NFLX/USDT 4h: 1006 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- NFLX/USDT 1d: 168 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- PLTR/USDT 15m: 27588 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- PLTR/USDT 1h: 6897 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- PLTR/USDT 4h: 1725 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- PLTR/USDT 1d: 288 mum, 2026-02-09 -> 2026-11-23 (kisa gecmis)
- COST/USDT 15m: 16092 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- COST/USDT 1h: 4023 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- COST/USDT 4h: 1006 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- COST/USDT 1d: 168 mum, 2026-06-09 -> 2026-11-23 (kisa gecmis)
- AMD/USDT 15m: 19338 mum, 2026-05-06 -> 2026-11-23 (kisa gecmis)
- AMD/USDT 1h: 4835 mum, 2026-05-06 -> 2026-11-23 (kisa gecmis)
- AMD/USDT 4h: 1209 mum, 2026-05-06 -> 2026-11-23 (kisa gecmis)
- AMD/USDT 1d: 202 mum, 2026-05-06 -> 2026-11-23 (kisa gecmis)
- HD/USDT 15m: 18473 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- HD/USDT 1h: 4619 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- HD/USDT 4h: 1155 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- HD/USDT 1d: 193 mum, 2026-05-15 -> 2026-11-23 (kisa gecmis)
- XAU/USDT 15m: 33376 mum, 2025-12-11 -> 2026-11-23 (kisa gecmis)
- XAU/USDT 1h: 8344 mum, 2025-12-11 -> 2026-11-23 (kisa gecmis)
- XAU/USDT 4h: 2086 mum, 2025-12-11 -> 2026-11-23 (kisa gecmis)
- XAU/USDT 1d: 348 mum, 2025-12-11 -> 2026-11-23 (kisa gecmis)
- XAG/USDT 15m: 30776 mum, 2026-01-07 -> 2026-11-23 (kisa gecmis)
- XAG/USDT 1h: 7694 mum, 2026-01-07 -> 2026-11-23 (kisa gecmis)
- XAG/USDT 4h: 1924 mum, 2026-01-07 -> 2026-11-23 (kisa gecmis)
- XAG/USDT 1d: 321 mum, 2026-01-07 -> 2026-11-23 (kisa gecmis)
- BZ/USDT 15m: 22716 mum, 2026-04-01 -> 2026-11-23 (kisa gecmis)
- BZ/USDT 1h: 5679 mum, 2026-04-01 -> 2026-11-23 (kisa gecmis)
- BZ/USDT 4h: 1420 mum, 2026-04-01 -> 2026-11-23 (kisa gecmis)
- BZ/USDT 1d: 237 mum, 2026-04-01 -> 2026-11-23 (kisa gecmis)
- COPPER/USDT 15m: 25212 mum, 2026-03-06 -> 2026-11-23 (kisa gecmis)
- COPPER/USDT 1h: 6303 mum, 2026-03-06 -> 2026-11-23 (kisa gecmis)
- COPPER/USDT 4h: 1576 mum, 2026-03-06 -> 2026-11-23 (kisa gecmis)
- COPPER/USDT 1d: 263 mum, 2026-03-06 -> 2026-11-23 (kisa gecmis)
