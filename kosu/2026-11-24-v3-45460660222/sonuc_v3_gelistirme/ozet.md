# v3 kitap setuplari geri test ozeti (gelistirme)

- Ciftler: 43 (engine.paper.json); veri olan: 19; zaman dilimleri: 15m, 1h, 4h, 1d
- Fonlama verisi olan cift: 19/43 (fonlama maliyeti islenir; veto YOK)
- Kesim (dislayici): 2025-07-01; sure: 762 sn
- Rastgele kiyas: setup x cift x zd x yon grubu basina 200 cekilis (ayni yil/yon/stop-hedef ATR mesafesi), gercek islem sayisiyla agirlikli.
- R = net R (ucret+kayma+fonlama dusulmus). Stopu olmayan IND_MA_KESISIM / IND_FIYAT_MA'da R birimi 2 ATR(14). Yalniz arastirma.

## Ana sonuc

| setup | kat | tf | yon | sinyal | islem | kazanma | ort R | toplam R | PF | maks dusus R | stop/hedef/zaman/sinyal | rastgele ort R | fark | z |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MUM_PINBAR | MF1 | 15m | long | 16102 | 5853 | 36.4% | -0.165 | -963.4 | 0.77 | 979.1 | 3567/1653/633/0 | -0.169 | 0.004 | 0.2 |
| MUM_PINBAR | MF1 | 15m | short | 13704 | 4024 | 35.3% | -0.165 | -665.4 | 0.78 | 689.5 | 2511/1212/301/0 | -0.140 | -0.026 | -0.9 |
| MUM_PINBAR | MF1 | 15m | hepsi | 29806 | 9877 | 36.0% | -0.165 | -1628.8 | 0.77 | 1650.1 | 6078/2865/934/0 | -0.157 | -0.008 | -0.4 |
| MUM_PINBAR | MF1 | 1h | long | 7063 | 5740 | 31.6% | -0.222 | -1273.3 | 0.70 | 1293.3 | 3805/1557/378/0 | -0.160 | -0.062 | -2.5 |
| MUM_PINBAR | MF1 | 1h | short | 5805 | 4209 | 34.0% | -0.130 | -546.3 | 0.82 | 576.5 | 2745/1345/119/0 | -0.141 | 0.011 | 0.4 |
| MUM_PINBAR | MF1 | 1h | hepsi | 12868 | 9949 | 32.6% | -0.183 | -1819.6 | 0.75 | 1828.9 | 6550/2902/497/0 | -0.152 | -0.031 | -1.6 |
| MUM_PINBAR | MF1 | 4h | long | 1730 | 1595 | 29.8% | -0.215 | -343.7 | 0.71 | 351.4 | 1093/430/72/0 | -0.130 | -0.086 | -1.8 |
| MUM_PINBAR | MF1 | 4h | short | 1215 | 1075 | 37.7% | 0.037 | 40.1 | 1.06 | 48.5 | 665/383/27/0 | -0.063 | 0.101 | 1.7 |
| MUM_PINBAR | MF1 | 4h | hepsi | 2945 | 2670 | 33.0% | -0.114 | -303.6 | 0.84 | 331.3 | 1758/813/99/0 | -0.103 | -0.011 | -0.3 |
| MUM_PINBAR | MF1 | 1d | long | 292 | 266 | 36.8% | 0.038 | 10.0 | 1.06 | 37.3 | 159/89/18/0 | -0.108 | 0.145 | 1.2 |
| MUM_PINBAR | MF1 | 1d | short | 168 | 147 | 33.3% | -0.043 | -6.4 | 0.94 | 23.8 | 98/46/3/0 | 0.009 | -0.053 | -0.3 |
| MUM_PINBAR | MF1 | 1d | hepsi | 460 | 413 | 35.6% | 0.009 | 3.6 | 1.01 | 39.2 | 257/135/21/0 | -0.066 | 0.075 | 0.8 |
| MUM_IC_CUBUK | MF1 | 15m | long | 217240 | 22876 | 35.2% | -0.166 | -3794.9 | 0.77 | 3836.4 | 14201/6701/1974/0 | -0.190 | 0.024 | 1.9 |
| MUM_IC_CUBUK | MF1 | 15m | short | 217240 | 22527 | 35.5% | -0.141 | -3166.9 | 0.81 | 3166.9 | 13860/6938/1729/0 | -0.159 | 0.019 | 1.5 |
| MUM_IC_CUBUK | MF1 | 15m | hepsi | 434480 | 45403 | 35.3% | -0.153 | -6961.9 | 0.79 | 6965.5 | 28061/13639/3703/0 | -0.175 | 0.021 | 2.4 |
| MUM_IC_CUBUK | MF1 | 1h | long | 110586 | 17929 | 33.5% | -0.144 | -2589.4 | 0.80 | 2677.2 | 11614/5406/909/0 | -0.135 | -0.009 | -0.7 |
| MUM_IC_CUBUK | MF1 | 1h | short | 110586 | 17621 | 34.8% | -0.094 | -1650.5 | 0.87 | 1669.2 | 11253/5572/796/0 | -0.058 | -0.036 | -2.4 |
| MUM_IC_CUBUK | MF1 | 1h | hepsi | 221172 | 35550 | 34.1% | -0.119 | -4239.9 | 0.83 | 4267.2 | 22867/10978/1705/0 | -0.097 | -0.022 | -2.2 |
| MUM_IC_CUBUK | MF1 | 4h | long | 30381 | 5043 | 33.8% | -0.093 | -471.4 | 0.87 | 523.9 | 3267/1540/236/0 | -0.121 | 0.027 | 1.0 |
| MUM_IC_CUBUK | MF1 | 4h | short | 30381 | 4697 | 36.5% | 0.002 | 8.7 | 1.00 | 151.7 | 2938/1554/205/0 | 0.002 | 0.000 | 0.0 |
| MUM_IC_CUBUK | MF1 | 4h | hepsi | 60762 | 9740 | 35.1% | -0.048 | -462.8 | 0.93 | 494.5 | 6205/3094/441/0 | -0.062 | 0.014 | 0.7 |
| MUM_IC_CUBUK | MF1 | 1d | long | 4483 | 710 | 34.8% | -0.027 | -19.1 | 0.96 | 54.6 | 454/228/28/0 | -0.065 | 0.038 | 0.5 |
| MUM_IC_CUBUK | MF1 | 1d | short | 4483 | 708 | 38.4% | 0.081 | 57.4 | 1.13 | 75.7 | 432/235/41/0 | 0.061 | 0.020 | 0.3 |
| MUM_IC_CUBUK | MF1 | 1d | hepsi | 8966 | 1418 | 36.6% | 0.027 | 38.2 | 1.04 | 72.2 | 886/463/69/0 | -0.002 | 0.029 | 0.6 |
| MUM_YUTAN | MF1 | 15m | long | 43411 | 11278 | 33.9% | -0.193 | -2172.6 | 0.75 | 2189.8 | 7303/3445/530/0 | -0.233 | 0.040 | 2.3 |
| MUM_YUTAN | MF1 | 15m | short | 46577 | 10679 | 35.5% | -0.139 | -1488.9 | 0.81 | 1499.2 | 6721/3486/472/0 | -0.142 | 0.002 | 0.1 |
| MUM_YUTAN | MF1 | 15m | hepsi | 89988 | 21957 | 34.7% | -0.167 | -3661.5 | 0.78 | 3670.0 | 14024/6931/1002/0 | -0.189 | 0.022 | 1.7 |
| MUM_YUTAN | MF1 | 1h | long | 16377 | 9999 | 33.2% | -0.157 | -1573.1 | 0.79 | 1640.0 | 6589/3139/271/0 | -0.179 | 0.021 | 1.1 |
| MUM_YUTAN | MF1 | 1h | short | 18440 | 11165 | 35.3% | -0.088 | -987.0 | 0.88 | 1027.2 | 7136/3739/290/0 | -0.121 | 0.033 | 1.8 |
| MUM_YUTAN | MF1 | 1h | hepsi | 34817 | 21164 | 34.3% | -0.121 | -2560.0 | 0.84 | 2583.3 | 13725/6878/561/0 | -0.148 | 0.027 | 2.0 |
| MUM_YUTAN | MF1 | 4h | long | 3698 | 2814 | 36.1% | -0.026 | -72.6 | 0.96 | 195.1 | 1775/975/64/0 | -0.151 | 0.125 | 3.4 |
| MUM_YUTAN | MF1 | 4h | short | 4306 | 3293 | 35.5% | -0.025 | -83.1 | 0.96 | 227.7 | 2110/1130/53/0 | -0.029 | 0.003 | 0.1 |
| MUM_YUTAN | MF1 | 4h | hepsi | 8004 | 6107 | 35.8% | -0.026 | -155.7 | 0.96 | 346.3 | 3885/2105/117/0 | -0.085 | 0.060 | 2.3 |
| MUM_YUTAN | MF1 | 1d | long | 602 | 451 | 33.0% | -0.066 | -29.8 | 0.91 | 54.7 | 300/146/5/0 | -0.090 | 0.024 | 0.3 |
| MUM_YUTAN | MF1 | 1d | short | 646 | 510 | 38.0% | 0.091 | 46.6 | 1.14 | 36.3 | 314/182/14/0 | 0.045 | 0.047 | 0.5 |
| MUM_YUTAN | MF1 | 1d | hepsi | 1248 | 961 | 35.7% | 0.017 | 16.7 | 1.03 | 57.8 | 614/328/19/0 | -0.018 | 0.036 | 0.6 |
| MUM_YILDIZ | MF1 | 15m | long | 71 | 71 | 66.2% | 0.459 | 32.6 | 3.20 | 3.6 | 11/7/53/0 | -0.103 | 0.561 | 2.9 |
| MUM_YILDIZ | MF1 | 15m | short | 57 | 57 | 42.1% | -0.138 | -7.9 | 0.75 | 16.4 | 28/1/28/0 | -0.100 | -0.038 | -0.2 |
| MUM_YILDIZ | MF1 | 15m | hepsi | 128 | 128 | 55.5% | 0.193 | 24.7 | 1.54 | 8.0 | 39/8/81/0 | -0.101 | 0.294 | 2.0 |
| MUM_YILDIZ | MF1 | 1h | long | 207 | 207 | 44.0% | 0.211 | 43.6 | 1.38 | 10.8 | 105/38/64/0 | -0.073 | 0.284 | 1.9 |
| MUM_YILDIZ | MF1 | 1h | short | 202 | 198 | 32.8% | -0.223 | -44.2 | 0.66 | 67.0 | 121/16/61/0 | -0.038 | -0.186 | -1.4 |
| MUM_YILDIZ | MF1 | 1h | hepsi | 409 | 405 | 38.5% | -0.002 | -0.6 | 1.00 | 37.9 | 226/54/125/0 | -0.056 | 0.054 | 0.5 |
| MUM_YILDIZ | MF1 | 4h | long | 141 | 140 | 28.6% | -0.026 | -3.7 | 0.96 | 23.1 | 97/29/14/0 | -0.118 | 0.092 | 0.5 |
| MUM_YILDIZ | MF1 | 4h | short | 169 | 165 | 31.5% | 0.111 | 18.4 | 1.16 | 32.8 | 104/41/20/0 | 0.030 | 0.081 | 0.4 |
| MUM_YILDIZ | MF1 | 4h | hepsi | 310 | 305 | 30.2% | 0.048 | 14.7 | 1.07 | 45.1 | 201/70/34/0 | -0.038 | 0.086 | 0.6 |
| MUM_YILDIZ | MF1 | 1d | long | 24 | 24 | 20.8% | -0.230 | -5.5 | 0.72 | 7.0 | 19/5/0/0 | -0.025 | -0.206 | yetersiz |
| MUM_YILDIZ | MF1 | 1d | short | 32 | 32 | 21.9% | -0.224 | -7.2 | 0.72 | 10.8 | 25/6/1/0 | -0.061 | -0.162 | yetersiz |
| MUM_YILDIZ | MF1 | 1d | hepsi | 56 | 56 | 21.4% | -0.227 | -12.7 | 0.72 | 13.5 | 44/11/1/0 | -0.046 | -0.181 | -0.6 |
| FOR_YATAY_KIRILIM | GF1 | 15m | long | 29960 | 11761 | 40.5% | -0.178 | -2093.9 | 0.73 | 2121.5 | 6648/4675/438/0 | -0.168 | -0.010 | -0.6 |
| FOR_YATAY_KIRILIM | GF1 | 15m | short | 27236 | 12550 | 40.6% | -0.159 | -1989.9 | 0.76 | 1992.2 | 7114/4986/450/0 | -0.125 | -0.034 | -2.1 |
| FOR_YATAY_KIRILIM | GF1 | 15m | hepsi | 57196 | 24311 | 40.6% | -0.168 | -4083.8 | 0.75 | 4094.1 | 13762/9661/888/0 | -0.146 | -0.022 | -1.9 |
| FOR_YATAY_KIRILIM | GF1 | 1h | long | 11546 | 8459 | 38.4% | -0.138 | -1166.6 | 0.80 | 1218.5 | 5114/3206/139/0 | -0.162 | 0.024 | 1.1 |
| FOR_YATAY_KIRILIM | GF1 | 1h | short | 10406 | 8195 | 40.2% | -0.092 | -754.0 | 0.86 | 866.3 | 4801/3213/181/0 | -0.066 | -0.026 | -1.2 |
| FOR_YATAY_KIRILIM | GF1 | 1h | hepsi | 21952 | 16654 | 39.3% | -0.115 | -1920.7 | 0.83 | 1997.6 | 9915/6419/320/0 | -0.115 | -0.000 | -0.0 |
| FOR_YATAY_KIRILIM | GF1 | 4h | long | 2185 | 1884 | 38.4% | -0.114 | -214.0 | 0.83 | 226.6 | 1151/720/13/0 | -0.122 | 0.009 | 0.2 |
| FOR_YATAY_KIRILIM | GF1 | 4h | short | 1802 | 1615 | 43.7% | 0.100 | 160.8 | 1.17 | 96.6 | 893/689/33/0 | -0.011 | 0.111 | 2.0 |
| FOR_YATAY_KIRILIM | GF1 | 4h | hepsi | 3987 | 3499 | 40.8% | -0.015 | -53.2 | 0.98 | 195.5 | 2044/1409/46/0 | -0.071 | 0.056 | 1.6 |
| FOR_YATAY_KIRILIM | GF1 | 1d | long | 158 | 143 | 42.0% | 0.066 | 9.5 | 1.11 | 15.9 | 80/62/1/0 | 0.027 | 0.040 | 0.2 |
| FOR_YATAY_KIRILIM | GF1 | 1d | short | 174 | 158 | 50.0% | 0.220 | 34.8 | 1.43 | 13.2 | 77/78/3/0 | 0.066 | 0.155 | 0.9 |
| FOR_YATAY_KIRILIM | GF1 | 1d | hepsi | 332 | 301 | 46.2% | 0.147 | 44.3 | 1.27 | 21.5 | 157/140/4/0 | 0.047 | 0.100 | 0.8 |
| FOR_UCGEN | GF1 | 15m | long | 7142 | 4885 | 37.8% | -0.148 | -722.9 | 0.76 | 734.1 | 2447/873/1565/0 | -0.141 | -0.007 | -0.3 |
| FOR_UCGEN | GF1 | 15m | short | 6731 | 4516 | 38.5% | -0.116 | -524.5 | 0.80 | 529.8 | 2206/855/1455/0 | -0.069 | -0.047 | -1.8 |
| FOR_UCGEN | GF1 | 15m | hepsi | 13873 | 9401 | 38.1% | -0.133 | -1247.4 | 0.78 | 1256.3 | 4653/1728/3020/0 | -0.106 | -0.026 | -1.4 |
| FOR_UCGEN | GF1 | 1h | long | 2973 | 2287 | 38.5% | -0.046 | -104.3 | 0.92 | 141.9 | 1160/427/700/0 | -0.073 | 0.027 | 0.7 |
| FOR_UCGEN | GF1 | 1h | short | 2888 | 2199 | 40.3% | 0.001 | 2.4 | 1.00 | 75.8 | 1061/465/673/0 | -0.012 | 0.013 | 0.3 |
| FOR_UCGEN | GF1 | 1h | hepsi | 5861 | 4486 | 39.4% | -0.023 | -101.9 | 0.96 | 108.4 | 2221/892/1373/0 | -0.043 | 0.021 | 0.7 |
| FOR_UCGEN | GF1 | 4h | long | 827 | 617 | 39.1% | 0.015 | 9.3 | 1.03 | 58.5 | 312/138/167/0 | -0.005 | 0.020 | 0.2 |
| FOR_UCGEN | GF1 | 4h | short | 807 | 616 | 43.5% | 0.122 | 75.0 | 1.26 | 42.6 | 252/128/236/0 | 0.019 | 0.103 | 1.3 |
| FOR_UCGEN | GF1 | 4h | hepsi | 1634 | 1233 | 41.3% | 0.068 | 84.2 | 1.13 | 49.8 | 564/266/403/0 | 0.007 | 0.061 | 1.1 |
| FOR_UCGEN | GF1 | 1d | long | 155 | 107 | 34.6% | -0.103 | -11.0 | 0.84 | 21.1 | 63/19/25/0 | 0.002 | -0.105 | -0.5 |
| FOR_UCGEN | GF1 | 1d | short | 127 | 87 | 40.2% | -0.061 | -5.3 | 0.88 | 15.0 | 41/9/37/0 | 0.037 | -0.098 | -0.5 |
| FOR_UCGEN | GF1 | 1d | hepsi | 282 | 194 | 37.1% | -0.084 | -16.3 | 0.86 | 20.2 | 104/28/62/0 | 0.018 | -0.102 | -0.7 |
| FOR_IKILI_DIP | GF1 | 15m | long | 18691 | 12475 | 51.8% | -0.114 | -1427.6 | 0.72 | 1449.1 | 4019/5411/3045/0 | -0.111 | -0.004 | -0.4 |
| FOR_IKILI_DIP | GF1 | 15m | short | 19132 | 12712 | 54.6% | -0.081 | -1034.0 | 0.79 | 1034.6 | 3879/6115/2718/0 | -0.068 | -0.013 | -1.4 |
| FOR_IKILI_DIP | GF1 | 15m | hepsi | 37823 | 25187 | 53.2% | -0.098 | -2461.6 | 0.75 | 2469.9 | 7898/11526/5763/0 | -0.089 | -0.009 | -1.2 |
| FOR_IKILI_DIP | GF1 | 1h | long | 6967 | 4990 | 54.1% | -0.072 | -358.4 | 0.82 | 407.1 | 1661/2354/975/0 | -0.033 | -0.039 | -2.5 |
| FOR_IKILI_DIP | GF1 | 1h | short | 7281 | 5239 | 56.3% | -0.032 | -169.2 | 0.91 | 223.9 | 1679/2661/899/0 | -0.034 | 0.001 | 0.1 |
| FOR_IKILI_DIP | GF1 | 1h | hepsi | 14248 | 10229 | 55.2% | -0.052 | -527.6 | 0.87 | 552.4 | 3340/5015/1874/0 | -0.033 | -0.018 | -1.7 |
| FOR_IKILI_DIP | GF1 | 4h | long | 1139 | 915 | 55.2% | -0.039 | -35.8 | 0.90 | 69.7 | 318/473/124/0 | -0.035 | -0.004 | -0.1 |
| FOR_IKILI_DIP | GF1 | 4h | short | 1244 | 978 | 58.8% | 0.015 | 14.6 | 1.04 | 46.1 | 320/526/132/0 | 0.012 | 0.003 | 0.1 |
| FOR_IKILI_DIP | GF1 | 4h | hepsi | 2383 | 1893 | 57.1% | -0.011 | -21.2 | 0.97 | 73.1 | 638/999/256/0 | -0.011 | -0.000 | -0.0 |
| FOR_IKILI_DIP | GF1 | 1d | long | 91 | 76 | 53.9% | -0.127 | -9.6 | 0.72 | 13.2 | 32/40/4/0 | -0.016 | -0.110 | -0.9 |
| FOR_IKILI_DIP | GF1 | 1d | short | 91 | 87 | 58.6% | 0.020 | 1.7 | 1.06 | 9.9 | 28/46/13/0 | -0.016 | 0.035 | 0.3 |
| FOR_IKILI_DIP | GF1 | 1d | hepsi | 182 | 163 | 56.4% | -0.049 | -7.9 | 0.88 | 20.4 | 60/86/17/0 | -0.016 | -0.033 | -0.4 |
| FOR_OBO | GF1 | 15m | long | 122 | 116 | 46.6% | -0.218 | -25.2 | 0.54 | 33.1 | 44/42/30/0 | -0.083 | -0.134 | -1.3 |
| FOR_OBO | GF1 | 15m | short | 143 | 134 | 47.0% | -0.162 | -21.7 | 0.63 | 23.8 | 43/51/40/0 | -0.060 | -0.102 | -1.0 |
| FOR_OBO | GF1 | 15m | hepsi | 265 | 250 | 46.8% | -0.188 | -46.9 | 0.59 | 53.8 | 87/93/70/0 | -0.071 | -0.117 | -1.6 |
| FOR_OBO | GF1 | 1h | long | 41 | 40 | 50.0% | 0.041 | 1.7 | 1.11 | 5.0 | 12/17/11/0 | -0.059 | 0.100 | yetersiz |
| FOR_OBO | GF1 | 1h | short | 49 | 48 | 58.3% | 0.010 | 0.5 | 1.03 | 4.3 | 16/23/9/0 | -0.008 | 0.017 | yetersiz |
| FOR_OBO | GF1 | 1h | hepsi | 90 | 88 | 54.5% | 0.024 | 2.1 | 1.06 | 6.9 | 28/40/20/0 | -0.031 | 0.055 | 0.4 |
| FOR_OBO | GF1 | 4h | long | 6 | 6 | 50.0% | -0.032 | -0.2 | 0.90 | 1.1 | 1/3/2/0 | -0.088 | 0.056 | yetersiz |
| FOR_OBO | GF1 | 4h | short | 7 | 7 | 42.9% | -0.213 | -1.5 | 0.55 | 1.9 | 3/2/2/0 | 0.051 | -0.263 | yetersiz |
| FOR_OBO | GF1 | 4h | hepsi | 13 | 13 | 46.2% | -0.129 | -1.7 | 0.68 | 3.0 | 4/5/4/0 | -0.013 | -0.116 | yetersiz |
| FOR_OBO | GF1 | 1d | long | 2 | 2 | 50.0% | -0.468 | -0.9 | 0.07 | 1.0 | 1/0/1/0 | -0.052 | -0.416 | yetersiz |
| FOR_OBO | GF1 | 1d | short | 0 | 0 | | | | | | | | | |
| FOR_OBO | GF1 | 1d | hepsi | 2 | 2 | 50.0% | -0.468 | -0.9 | 0.07 | 1.0 | 1/0/1/0 | -0.052 | -0.416 | yetersiz |
| IND_RSI_3070 | IN1 | 15m | long | 7202 | 1135 | 32.9% | -0.165 | -187.4 | 0.78 | 217.5 | 722/0/329/84 | -0.124 | -0.041 | -0.5 |
| IND_RSI_3070 | IN1 | 15m | short | 6893 | 647 | 25.3% | -0.058 | -37.2 | 0.93 | 57.0 | 469/0/118/60 | -0.272 | 0.214 | 1.8 |
| IND_RSI_3070 | IN1 | 15m | hepsi | 14095 | 1782 | 30.1% | -0.126 | -224.6 | 0.84 | 242.5 | 1191/0/447/144 | -0.178 | 0.052 | 0.8 |
| IND_RSI_3070 | IN1 | 1h | long | 3422 | 1529 | 20.0% | -0.225 | -344.1 | 0.75 | 345.9 | 1178/0/248/103 | -0.166 | -0.059 | -0.6 |
| IND_RSI_3070 | IN1 | 1h | short | 3484 | 1112 | 17.1% | -0.198 | -220.2 | 0.79 | 241.4 | 918/0/135/59 | -0.113 | -0.085 | -0.7 |
| IND_RSI_3070 | IN1 | 1h | hepsi | 6906 | 2641 | 18.8% | -0.214 | -564.3 | 0.77 | 564.3 | 2096/0/383/162 | -0.144 | -0.070 | -0.9 |
| IND_RSI_3070 | IN1 | 4h | long | 849 | 596 | 15.1% | -0.387 | -230.6 | 0.58 | 284.7 | 494/0/70/32 | -0.088 | -0.299 | -1.3 |
| IND_RSI_3070 | IN1 | 4h | short | 1055 | 608 | 15.8% | 0.220 | 133.7 | 1.23 | 96.4 | 511/0/53/44 | -0.137 | 0.357 | 1.7 |
| IND_RSI_3070 | IN1 | 4h | hepsi | 1904 | 1204 | 15.4% | -0.080 | -96.9 | 0.91 | 260.4 | 1005/0/123/76 | -0.113 | 0.032 | 0.2 |
| IND_RSI_3070 | IN1 | 1d | long | 106 | 91 | 23.1% | 0.105 | 9.5 | 1.14 | 29.0 | 65/0/19/7 | 0.108 | -0.003 | -0.0 |
| IND_RSI_3070 | IN1 | 1d | short | 175 | 141 | 14.9% | 0.466 | 65.7 | 1.52 | 56.4 | 120/0/11/10 | -0.197 | 0.664 | 1.5 |
| IND_RSI_3070 | IN1 | 1d | hepsi | 281 | 232 | 18.1% | 0.324 | 75.3 | 1.38 | 61.3 | 185/0/30/17 | -0.078 | 0.402 | 1.0 |
| IND_MA_KESISIM | IN1 | 15m | long | 4964 | 4963 | 43.4% | -0.059 | -294.8 | 0.93 | 434.1 | 0/0/4043/920 | -0.104 | 0.045 | 0.8 |
| IND_MA_KESISIM | IN1 | 15m | short | 4971 | 4964 | 43.7% | -0.155 | -771.9 | 0.83 | 883.7 | 0/0/3985/979 | -0.114 | -0.041 | -0.8 |
| IND_MA_KESISIM | IN1 | 15m | hepsi | 9935 | 9927 | 43.5% | -0.107 | -1066.6 | 0.88 | 1156.3 | 0/0/8028/1899 | -0.109 | 0.002 | 0.0 |
| IND_MA_KESISIM | IN1 | 1h | long | 2124 | 2121 | 45.2% | 0.113 | 240.3 | 1.13 | 242.1 | 0/0/1718/403 | 0.045 | 0.068 | 0.8 |
| IND_MA_KESISIM | IN1 | 1h | short | 2120 | 2119 | 47.9% | 0.124 | 262.7 | 1.17 | 154.4 | 0/0/1748/371 | -0.117 | 0.241 | 3.2 |
| IND_MA_KESISIM | IN1 | 1h | hepsi | 4244 | 4240 | 46.6% | 0.119 | 503.0 | 1.15 | 210.1 | 0/0/3466/774 | -0.036 | 0.155 | 2.7 |
| IND_MA_KESISIM | IN1 | 4h | long | 486 | 484 | 44.6% | 0.410 | 198.5 | 1.51 | 45.2 | 0/0/377/107 | 0.138 | 0.272 | 1.4 |
| IND_MA_KESISIM | IN1 | 4h | short | 499 | 495 | 49.9% | -0.018 | -9.0 | 0.97 | 72.9 | 0/0/411/84 | -0.200 | 0.182 | 1.1 |
| IND_MA_KESISIM | IN1 | 4h | hepsi | 985 | 979 | 47.3% | 0.194 | 189.5 | 1.26 | 51.2 | 0/0/788/191 | -0.033 | 0.227 | 1.8 |
| IND_MA_KESISIM | IN1 | 1d | long | 77 | 74 | 45.9% | 0.775 | 57.3 | 2.11 | 28.2 | 0/0/63/11 | 0.923 | -0.148 | -0.2 |
| IND_MA_KESISIM | IN1 | 1d | short | 82 | 78 | 47.4% | -0.644 | -50.2 | 0.43 | 61.4 | 0/0/64/14 | -0.645 | 0.001 | 0.0 |
| IND_MA_KESISIM | IN1 | 1d | hepsi | 159 | 152 | 46.7% | 0.047 | 7.1 | 1.05 | 71.8 | 0/0/127/25 | 0.119 | -0.072 | -0.2 |
| IND_BOLL_DONUS | IN1 | 15m | long | 225750 | 33646 | 48.4% | -0.156 | -5257.0 | 0.71 | 5304.7 | 15314/18332/0/0 | -0.192 | 0.035 | 4.2 |
| IND_BOLL_DONUS | IN1 | 15m | short | 208415 | 26115 | 45.4% | -0.195 | -5101.9 | 0.66 | 5139.7 | 12423/13692/0/0 | -0.150 | -0.046 | -4.7 |
| IND_BOLL_DONUS | IN1 | 15m | hepsi | 434165 | 59761 | 47.1% | -0.173 | -10358.9 | 0.69 | 10428.7 | 27737/32024/0/0 | -0.173 | -0.000 | -0.0 |
| IND_BOLL_DONUS | IN1 | 1h | long | 102349 | 39878 | 40.8% | -0.195 | -7763.5 | 0.70 | 7795.3 | 22650/17228/0/0 | -0.153 | -0.041 | -4.3 |
| IND_BOLL_DONUS | IN1 | 1h | short | 95924 | 34087 | 40.1% | -0.177 | -6026.2 | 0.73 | 6079.4 | 19590/14497/0/0 | -0.120 | -0.057 | -5.3 |
| IND_BOLL_DONUS | IN1 | 1h | hepsi | 198273 | 73965 | 40.4% | -0.186 | -13789.6 | 0.72 | 13844.4 | 42240/31725/0/0 | -0.138 | -0.048 | -6.7 |
| IND_BOLL_DONUS | IN1 | 4h | long | 24761 | 13388 | 35.2% | -0.197 | -2632.0 | 0.72 | 2668.3 | 8470/4918/0/0 | -0.170 | -0.026 | -1.4 |
| IND_BOLL_DONUS | IN1 | 4h | short | 24094 | 12645 | 34.2% | -0.141 | -1784.4 | 0.80 | 1818.6 | 8200/4445/0/0 | -0.128 | -0.013 | -0.6 |
| IND_BOLL_DONUS | IN1 | 4h | hepsi | 48855 | 26033 | 34.7% | -0.170 | -4416.4 | 0.76 | 4451.6 | 16670/9363/0/0 | -0.150 | -0.020 | -1.4 |
| IND_BOLL_DONUS | IN1 | 1d | long | 3380 | 2012 | 33.2% | -0.147 | -295.0 | 0.79 | 414.0 | 1315/697/0/0 | -0.191 | 0.044 | 0.8 |
| IND_BOLL_DONUS | IN1 | 1d | short | 3519 | 2201 | 29.9% | -0.114 | -250.4 | 0.85 | 386.1 | 1536/665/0/0 | 0.004 | -0.118 | -1.9 |
| IND_BOLL_DONUS | IN1 | 1d | hepsi | 6899 | 4213 | 31.5% | -0.129 | -545.4 | 0.82 | 711.4 | 2851/1362/0/0 | -0.089 | -0.041 | -1.0 |
| IND_FIYAT_MA | IN1 | 15m | long | 62922 | 62899 | 14.9% | -0.170 | -10676.1 | 0.63 | 10860.5 | 0/0/4629/58270 | -0.183 | 0.014 | 1.1 |
| IND_FIYAT_MA | IN1 | 15m | short | 62932 | 62910 | 14.9% | -0.183 | -11513.3 | 0.61 | 11513.3 | 0/0/4557/58353 | -0.180 | -0.003 | -0.2 |
| IND_FIYAT_MA | IN1 | 15m | hepsi | 125854 | 125809 | 14.9% | -0.176 | -22189.4 | 0.62 | 22195.4 | 0/0/9186/116623 | -0.182 | 0.006 | 0.6 |
| IND_FIYAT_MA | IN1 | 1h | long | 25884 | 25864 | 17.0% | -0.034 | -891.7 | 0.91 | 1360.1 | 0/0/2005/23859 | 0.106 | -0.140 | -4.8 |
| IND_FIYAT_MA | IN1 | 1h | short | 25874 | 25861 | 17.6% | -0.052 | -1351.8 | 0.86 | 1491.9 | 0/0/2080/23781 | -0.228 | 0.176 | 8.5 |
| IND_FIYAT_MA | IN1 | 1h | hepsi | 51758 | 51725 | 17.3% | -0.043 | -2243.5 | 0.88 | 2639.9 | 0/0/4085/47640 | -0.061 | 0.018 | 1.0 |
| IND_FIYAT_MA | IN1 | 4h | long | 5934 | 5911 | 18.4% | 0.083 | 490.7 | 1.25 | 200.3 | 0/0/446/5465 | 0.130 | -0.046 | -0.9 |
| IND_FIYAT_MA | IN1 | 4h | short | 5932 | 5927 | 20.6% | 0.014 | 80.8 | 1.04 | 169.7 | 0/0/550/5377 | -0.257 | 0.270 | 6.4 |
| IND_FIYAT_MA | IN1 | 4h | hepsi | 11866 | 11838 | 19.5% | 0.048 | 571.5 | 1.15 | 164.8 | 0/0/996/10842 | -0.064 | 0.112 | 3.4 |
| IND_FIYAT_MA | IN1 | 1d | long | 821 | 810 | 16.8% | 0.370 | 299.8 | 2.12 | 87.4 | 0/0/61/749 | 0.644 | -0.273 | -1.3 |
| IND_FIYAT_MA | IN1 | 1d | short | 831 | 813 | 22.0% | -0.023 | -18.4 | 0.92 | 67.5 | 0/0/89/724 | -0.688 | 0.665 | 4.1 |
| IND_FIYAT_MA | IN1 | 1d | hepsi | 1652 | 1623 | 19.4% | 0.173 | 281.4 | 1.56 | 81.9 | 0/0/150/1473 | -0.023 | 0.197 | 1.5 |

sinyal = kapanis kararinda uretilen aday sayisi; islem = acik pozisyon/MIN_RISK/bosluk/veri-sonu elemelerinden sonra simule edilen.

## Alt tur dokumu (hepsi): tur: islem, ort R, toplam R

- MUM_PINBAR 15m: pinbar: 9877, -0.165, -1628.8
- MUM_PINBAR 1h: pinbar: 9949, -0.183, -1819.6
- MUM_PINBAR 4h: pinbar: 2670, -0.114, -303.6
- MUM_PINBAR 1d: pinbar: 413, 0.009, 3.6
- MUM_IC_CUBUK 15m: ic_cubuk: 45403, -0.153, -6961.9
- MUM_IC_CUBUK 1h: ic_cubuk: 35550, -0.119, -4239.9
- MUM_IC_CUBUK 4h: ic_cubuk: 9740, -0.048, -462.8
- MUM_IC_CUBUK 1d: ic_cubuk: 1418, 0.027, 38.2
- MUM_YUTAN 15m: yutan: 21957, -0.167, -3661.5
- MUM_YUTAN 1h: yutan: 21164, -0.121, -2560.0
- MUM_YUTAN 4h: yutan: 6107, -0.026, -155.7
- MUM_YUTAN 1d: yutan: 961, 0.017, 16.7
- MUM_YILDIZ 15m: yildiz: 128, 0.193, 24.7
- MUM_YILDIZ 1h: yildiz: 405, -0.002, -0.6
- MUM_YILDIZ 4h: yildiz: 305, 0.048, 14.7
- MUM_YILDIZ 1d: yildiz: 56, -0.227, -12.7
- FOR_YATAY_KIRILIM 15m: yatay: 24311, -0.168, -4083.8
- FOR_YATAY_KIRILIM 1h: yatay: 16654, -0.115, -1920.7
- FOR_YATAY_KIRILIM 4h: yatay: 3499, -0.015, -53.2
- FOR_YATAY_KIRILIM 1d: yatay: 301, 0.147, 44.3
- FOR_UCGEN 15m: alcalan: 83, -0.249, -20.6; simetrik: 9224, -0.132, -1219.4; yukselen: 94, -0.078, -7.3
- FOR_UCGEN 1h: alcalan: 38, 0.161, 6.1; simetrik: 4414, -0.023, -99.7; yukselen: 34, -0.242, -8.2
- FOR_UCGEN 4h: alcalan: 15, -0.215, -3.2; simetrik: 1212, 0.072, 87.0; yukselen: 6, 0.075, 0.5
- FOR_UCGEN 1d: simetrik: 194, -0.084, -16.3
- FOR_IKILI_DIP 15m: ikili_dip: 12475, -0.114, -1427.6; ikili_tepe: 12712, -0.081, -1034.0
- FOR_IKILI_DIP 1h: ikili_dip: 4990, -0.072, -358.4; ikili_tepe: 5239, -0.032, -169.2
- FOR_IKILI_DIP 4h: ikili_dip: 915, -0.039, -35.8; ikili_tepe: 978, 0.015, 14.6
- FOR_IKILI_DIP 1d: ikili_dip: 76, -0.127, -9.6; ikili_tepe: 87, 0.020, 1.7
- FOR_OBO 15m: obo: 134, -0.162, -21.7; tobo: 116, -0.218, -25.2
- FOR_OBO 1h: obo: 48, 0.010, 0.5; tobo: 40, 0.041, 1.7
- FOR_OBO 4h: obo: 7, -0.213, -1.5; tobo: 6, -0.032, -0.2
- FOR_OBO 1d: tobo: 2, -0.468, -0.9
- IND_RSI_3070 15m: rsi: 1782, -0.126, -224.6
- IND_RSI_3070 1h: rsi: 2641, -0.214, -564.3
- IND_RSI_3070 4h: rsi: 1204, -0.080, -96.9
- IND_RSI_3070 1d: rsi: 232, 0.324, 75.3
- IND_MA_KESISIM 15m: ma_kesisim: 9927, -0.107, -1066.6
- IND_MA_KESISIM 1h: ma_kesisim: 4240, 0.119, 503.0
- IND_MA_KESISIM 4h: ma_kesisim: 979, 0.194, 189.5
- IND_MA_KESISIM 1d: ma_kesisim: 152, 0.047, 7.1
- IND_BOLL_DONUS 15m: boll: 59761, -0.173, -10358.9
- IND_BOLL_DONUS 1h: boll: 73965, -0.186, -13789.6
- IND_BOLL_DONUS 4h: boll: 26033, -0.170, -4416.4
- IND_BOLL_DONUS 1d: boll: 4213, -0.129, -545.4
- IND_FIYAT_MA 15m: fiyat_ma: 125809, -0.176, -22189.4
- IND_FIYAT_MA 1h: fiyat_ma: 51725, -0.043, -2243.5
- IND_FIYAT_MA 4h: fiyat_ma: 11838, 0.048, 571.5
- IND_FIYAT_MA 1d: fiyat_ma: 1623, 0.173, 281.4

## Yil yil toplam R (hepsi)

- MUM_PINBAR 15m: 2023: -351.3, 2024: -798.1, 2025: -479.4
- MUM_PINBAR 1h: 2021: -187.0, 2022: -340.1, 2023: -421.0, 2024: -564.1, 2025: -307.5
- MUM_PINBAR 4h: 2021: 4.0, 2022: -72.0, 2023: -82.0, 2024: -110.4, 2025: -43.1
- MUM_PINBAR 1d: 2021: -14.9, 2022: 8.1, 2023: 5.8, 2024: 31.6, 2025: -26.9
- MUM_IC_CUBUK 15m: 2023: -1952.6, 2024: -3553.5, 2025: -1455.8
- MUM_IC_CUBUK 1h: 2021: -613.3, 2022: -1004.5, 2023: -1231.4, 2024: -1144.7, 2025: -246.0
- MUM_IC_CUBUK 4h: 2021: -267.5, 2022: -117.8, 2023: -86.7, 2024: 102.5, 2025: -93.2
- MUM_IC_CUBUK 1d: 2021: -5.0, 2022: -5.7, 2023: -1.3, 2024: 33.5, 2025: 16.7
- MUM_YUTAN 15m: 2023: -1244.4, 2024: -1469.2, 2025: -947.9
- MUM_YUTAN 1h: 2021: -510.7, 2022: -801.4, 2023: -446.7, 2024: -464.0, 2025: -337.2
- MUM_YUTAN 4h: 2021: 48.9, 2022: 32.9, 2023: -231.7, 2024: -63.8, 2025: 58.0
- MUM_YUTAN 1d: 2021: 7.8, 2022: 15.0, 2023: -33.9, 2024: 8.9, 2025: 18.8
- MUM_YILDIZ 15m: 2023: -0.9, 2024: 10.9, 2025: 14.7
- MUM_YILDIZ 1h: 2021: 10.0, 2022: -3.4, 2023: -12.6, 2024: -9.6, 2025: 15.0
- MUM_YILDIZ 4h: 2021: 28.6, 2022: 2.1, 2023: -9.8, 2024: -12.5, 2025: 6.2
- MUM_YILDIZ 1d: 2021: -1.2, 2022: -6.8, 2023: 1.5, 2024: -4.9, 2025: -1.3
- FOR_YATAY_KIRILIM 15m: 2023: -1510.8, 2024: -1686.4, 2025: -886.6
- FOR_YATAY_KIRILIM 1h: 2021: -253.2, 2022: -307.4, 2023: -686.5, 2024: -425.1, 2025: -248.4
- FOR_YATAY_KIRILIM 4h: 2021: -53.9, 2022: 53.4, 2023: -51.7, 2024: -53.8, 2025: 52.8
- FOR_YATAY_KIRILIM 1d: 2021: 1.2, 2022: 10.9, 2023: 22.8, 2024: 4.7, 2025: 4.7
- FOR_UCGEN 15m: 2023: -519.0, 2024: -554.1, 2025: -174.3
- FOR_UCGEN 1h: 2021: -39.7, 2022: -17.4, 2023: 0.4, 2024: -20.9, 2025: -24.3
- FOR_UCGEN 4h: 2021: 5.8, 2022: -5.3, 2023: 17.7, 2024: 62.5, 2025: 3.5
- FOR_UCGEN 1d: 2021: -3.5, 2022: -10.2, 2023: -1.1, 2024: 6.7, 2025: -8.1
- FOR_IKILI_DIP 15m: 2023: -908.9, 2024: -1082.6, 2025: -470.0
- FOR_IKILI_DIP 1h: 2021: -37.7, 2022: -100.3, 2023: -257.0, 2024: -110.3, 2025: -22.3
- FOR_IKILI_DIP 4h: 2021: -12.7, 2022: -0.5, 2023: -29.5, 2024: 24.6, 2025: -3.2
- FOR_IKILI_DIP 1d: 2021: -1.2, 2022: -4.8, 2023: -5.6, 2024: 4.5, 2025: -0.8
- FOR_OBO 15m: 2023: -11.4, 2024: -29.4, 2025: -6.1
- FOR_OBO 1h: 2021: -3.9, 2022: 5.1, 2023: -0.0, 2024: 0.0, 2025: 0.9
- FOR_OBO 4h: 2022: 1.3, 2024: -2.4, 2025: -0.6
- FOR_OBO 1d: 2022: -1.0, 2025: 0.1
- IND_RSI_3070 15m: 2023: -72.6, 2024: -68.4, 2025: -83.5
- IND_RSI_3070 1h: 2021: -209.2, 2022: -40.0, 2023: -45.3, 2024: -135.7, 2025: -134.1
- IND_RSI_3070 4h: 2021: 90.1, 2022: -101.4, 2023: 34.5, 2024: -132.1, 2025: 12.0
- IND_RSI_3070 1d: 2021: 12.7, 2022: 55.7, 2023: 16.1, 2024: -14.3, 2025: 5.0
- IND_MA_KESISIM 15m: 2023: -465.2, 2024: -296.9, 2025: -304.5
- IND_MA_KESISIM 1h: 2021: 117.6, 2022: 4.3, 2023: -68.7, 2024: 331.4, 2025: 118.3
- IND_MA_KESISIM 4h: 2021: 12.9, 2022: 21.1, 2023: 86.5, 2024: 99.4, 2025: -30.5
- IND_MA_KESISIM 1d: 2021: 1.6, 2022: -7.3, 2023: -18.4, 2024: 39.2, 2025: -8.0
- IND_BOLL_DONUS 15m: 2023: -3253.4, 2024: -4345.4, 2025: -2760.0
- IND_BOLL_DONUS 1h: 2021: -3408.6, 2022: -3225.4, 2023: -2148.1, 2024: -3488.1, 2025: -1519.4
- IND_BOLL_DONUS 4h: 2021: -718.7, 2022: -1308.5, 2023: -674.6, 2024: -1278.3, 2025: -436.3
- IND_BOLL_DONUS 1d: 2021: 65.3, 2022: -204.2, 2023: -191.1, 2024: -188.3, 2025: -27.2
- IND_FIYAT_MA 15m: 2023: -11817.0, 2024: -7745.7, 2025: -2626.7
- IND_FIYAT_MA 1h: 2021: 227.3, 2022: -632.9, 2023: -1243.7, 2024: -369.2, 2025: -225.1
- IND_FIYAT_MA 4h: 2021: 134.2, 2022: 39.9, 2023: 139.5, 2024: 343.1, 2025: -85.3
- IND_FIYAT_MA 1d: 2021: -3.1, 2022: -52.3, 2023: 137.2, 2024: 218.6, 2025: -18.9

## Cift dagilimi (hepsi): en iyi / en kotu 5 (toplam R) ve islem veren cift sayisi

- MUM_PINBAR 15m (19 cift): iyi [HYPE/USDT -11.7, BNB/USDT -23.6, TRX/USDT -31.8, BTC/USDT -39.2, DOT/USDT -44.2]; kotu [SOL/USDT -140.1, LINK/USDT -136.1, HBAR/USDT -127.9, SUI/USDT -119.8, XLM/USDT -118.2]
- MUM_PINBAR 1h (19 cift): iyi [HYPE/USDT 0.9, TRX/USDT -36.7, SUI/USDT -39.1, XRP/USDT -55.5, BNB/USDT -58.5]; kotu [LINK/USDT -181.9, AVAX/USDT -170.9, DOGE/USDT -129.3, BCH/USDT -129.2, XLM/USDT -128.9]
- MUM_PINBAR 4h (18 cift): iyi [BCH/USDT 18.3, BTC/USDT 5.1, ETH/USDT 0.2, HBAR/USDT -5.0, TRX/USDT -5.5]; kotu [ADA/USDT -51.4, BNB/USDT -40.8, LTC/USDT -33.3, LINK/USDT -32.9, SOL/USDT -30.8]
- MUM_PINBAR 1d (18 cift): iyi [AVAX/USDT 15.4, XLM/USDT 8.0, DOGE/USDT 7.5, TRX/USDT 4.4, XMR/USDT 2.9]; kotu [HBAR/USDT -8.9, SOL/USDT -6.9, LTC/USDT -5.9, ADA/USDT -3.5, BTC/USDT -3.0]
- MUM_IC_CUBUK 15m (19 cift): iyi [HYPE/USDT -21.4, TRX/USDT -95.0, BTC/USDT -170.9, XRP/USDT -236.2, ETH/USDT -238.5]; kotu [DOT/USDT -612.0, XMR/USDT -542.4, LINK/USDT -531.6, AVAX/USDT -505.4, SUI/USDT -469.3]
- MUM_IC_CUBUK 1h (19 cift): iyi [HYPE/USDT -10.5, SOL/USDT -75.4, SUI/USDT -105.0, XRP/USDT -151.8, BCH/USDT -153.8]; kotu [XMR/USDT -399.3, LTC/USDT -355.4, ADA/USDT -321.5, XLM/USDT -318.8, BNB/USDT -301.0]
- MUM_IC_CUBUK 4h (18 cift): iyi [1000SHIB/USDT 37.1, AVAX/USDT 27.9, BCH/USDT 12.6, DOGE/USDT 5.5, SOL/USDT 1.7]; kotu [LTC/USDT -83.9, XMR/USDT -78.3, XRP/USDT -55.8, BTC/USDT -55.5, HBAR/USDT -54.2]
- MUM_IC_CUBUK 1d (18 cift): iyi [1000SHIB/USDT 25.3, HBAR/USDT 22.0, ADA/USDT 12.6, TRX/USDT 10.3, SUI/USDT 9.9]; kotu [LINK/USDT -15.6, LTC/USDT -10.3, BNB/USDT -9.3, XRP/USDT -9.1, DOT/USDT -7.3]
- MUM_YUTAN 15m (19 cift): iyi [TRX/USDT 4.0, HYPE/USDT -21.1, BTC/USDT -53.7, BNB/USDT -61.4, ETH/USDT -70.4]; kotu [LINK/USDT -315.4, DOT/USDT -313.2, HBAR/USDT -299.9, SOL/USDT -282.0, AVAX/USDT -259.2]
- MUM_YUTAN 1h (19 cift): iyi [HYPE/USDT -3.1, BNB/USDT -34.5, ADA/USDT -53.4, BTC/USDT -58.8, SUI/USDT -75.9]; kotu [XLM/USDT -228.9, XMR/USDT -217.4, LTC/USDT -212.2, LINK/USDT -211.7, HBAR/USDT -204.7]
- MUM_YUTAN 4h (18 cift): iyi [XRP/USDT 38.8, BCH/USDT 24.4, SUI/USDT 18.8, AVAX/USDT 18.4, ETH/USDT 15.0]; kotu [XMR/USDT -66.3, BNB/USDT -54.4, XLM/USDT -42.7, ADA/USDT -37.2, BTC/USDT -27.9]
- MUM_YUTAN 1d (18 cift): iyi [AVAX/USDT 15.8, HBAR/USDT 13.7, DOT/USDT 13.2, DOGE/USDT 12.5, BCH/USDT 11.9]; kotu [TRX/USDT -18.7, XLM/USDT -18.1, BNB/USDT -14.3, XMR/USDT -14.1, LINK/USDT -5.0]
- MUM_YILDIZ 15m (18 cift): iyi [DOGE/USDT 6.9, XRP/USDT 3.9, SOL/USDT 3.1, BNB/USDT 2.8, ADA/USDT 2.5]; kotu [1000SHIB/USDT -2.6, SUI/USDT -1.1, LINK/USDT -0.3, HBAR/USDT 0.2, BTC/USDT 0.3]
- MUM_YILDIZ 1h (19 cift): iyi [XRP/USDT 13.5, BNB/USDT 12.6, BTC/USDT 10.2, LINK/USDT 3.4, BCH/USDT 3.1]; kotu [DOT/USDT -10.1, TRX/USDT -7.0, SOL/USDT -6.7, ADA/USDT -5.4, XMR/USDT -4.2]
- MUM_YILDIZ 4h (18 cift): iyi [LINK/USDT 20.6, HBAR/USDT 11.5, XLM/USDT 10.7, XMR/USDT 6.7, DOGE/USDT 6.4]; kotu [SOL/USDT -10.7, 1000SHIB/USDT -9.1, XRP/USDT -5.9, AVAX/USDT -5.9, DOT/USDT -5.2]
- MUM_YILDIZ 1d (15 cift): iyi [LTC/USDT 6.8, SOL/USDT 1.9, BNB/USDT 1.9, BTC/USDT 1.8, XRP/USDT 0.9]; kotu [ADA/USDT -4.2, DOGE/USDT -4.2, XMR/USDT -4.2, ETH/USDT -3.6, 1000SHIB/USDT -3.4]
- FOR_YATAY_KIRILIM 15m (19 cift): iyi [HYPE/USDT -26.6, TRX/USDT -44.1, BNB/USDT -106.0, BTC/USDT -124.7, XRP/USDT -155.6]; kotu [XMR/USDT -373.2, SOL/USDT -339.5, LINK/USDT -311.9, BCH/USDT -311.3, AVAX/USDT -310.4]
- FOR_YATAY_KIRILIM 1h (19 cift): iyi [HYPE/USDT 5.8, SUI/USDT -6.6, AVAX/USDT -13.3, DOGE/USDT -41.2, TRX/USDT -50.8]; kotu [XMR/USDT -250.4, XLM/USDT -187.0, BTC/USDT -177.5, LTC/USDT -172.4, BNB/USDT -159.0]
- FOR_YATAY_KIRILIM 4h (18 cift): iyi [BCH/USDT 44.8, SUI/USDT 15.8, SOL/USDT 15.7, LTC/USDT 14.1, DOGE/USDT 12.4]; kotu [XMR/USDT -56.1, XRP/USDT -46.0, TRX/USDT -35.4, BTC/USDT -24.4, DOT/USDT -16.3]
- FOR_YATAY_KIRILIM 1d (18 cift): iyi [TRX/USDT 18.2, XMR/USDT 12.3, HBAR/USDT 9.8, AVAX/USDT 6.9, BNB/USDT 4.5]; kotu [BTC/USDT -6.5, LINK/USDT -5.8, LTC/USDT -5.6, XRP/USDT -4.5, BCH/USDT -2.1]
- FOR_UCGEN 15m (19 cift): iyi [BTC/USDT 3.6, HYPE/USDT -0.2, AVAX/USDT -0.6, 1000SHIB/USDT -39.1, SUI/USDT -39.5]; kotu [XMR/USDT -143.5, ADA/USDT -112.1, BCH/USDT -107.0, LTC/USDT -92.7, SOL/USDT -91.9]
- FOR_UCGEN 1h (19 cift): iyi [XRP/USDT 42.5, ADA/USDT 27.1, DOGE/USDT 26.2, 1000SHIB/USDT 21.8, SOL/USDT 15.8]; kotu [HBAR/USDT -53.0, BCH/USDT -43.5, LINK/USDT -26.9, DOT/USDT -24.3, BNB/USDT -22.7]
- FOR_UCGEN 4h (18 cift): iyi [DOGE/USDT 23.1, SOL/USDT 20.3, BNB/USDT 18.0, HBAR/USDT 16.3, DOT/USDT 15.9]; kotu [TRX/USDT -11.5, XRP/USDT -11.4, SUI/USDT -3.6, LTC/USDT -2.8, BCH/USDT -2.3]
- FOR_UCGEN 1d (18 cift): iyi [ETH/USDT 9.1, 1000SHIB/USDT 5.0, XMR/USDT 4.0, BNB/USDT 3.1, TRX/USDT 1.6]; kotu [AVAX/USDT -7.7, XRP/USDT -5.3, XLM/USDT -4.4, DOT/USDT -3.9, BCH/USDT -3.5]
- FOR_IKILI_DIP 15m (19 cift): iyi [HYPE/USDT -1.2, SUI/USDT -8.4, SOL/USDT -70.9, ETH/USDT -79.9, HBAR/USDT -103.2]; kotu [LTC/USDT -216.1, XMR/USDT -204.9, XLM/USDT -201.6, XRP/USDT -177.5, TRX/USDT -176.0]
- FOR_IKILI_DIP 1h (19 cift): iyi [DOGE/USDT 2.9, ADA/USDT 1.3, HYPE/USDT 1.1, SUI/USDT 0.9, SOL/USDT -4.2]; kotu [BTC/USDT -84.8, BNB/USDT -78.1, XMR/USDT -48.1, LINK/USDT -43.4, TRX/USDT -41.7]
- FOR_IKILI_DIP 4h (18 cift): iyi [BCH/USDT 11.1, DOGE/USDT 7.9, LINK/USDT 5.3, 1000SHIB/USDT 5.2, TRX/USDT 1.5]; kotu [DOT/USDT -16.7, XRP/USDT -10.6, LTC/USDT -6.7, XMR/USDT -5.9, BTC/USDT -5.0]
- FOR_IKILI_DIP 1d (18 cift): iyi [1000SHIB/USDT 4.9, TRX/USDT 1.8, SUI/USDT 1.3, BTC/USDT 0.4, DOT/USDT 0.3]; kotu [LTC/USDT -4.0, LINK/USDT -2.7, ETH/USDT -2.7, AVAX/USDT -1.4, HBAR/USDT -1.3]
- FOR_OBO 15m (18 cift): iyi [ADA/USDT 2.2, 1000SHIB/USDT 1.3, SUI/USDT 0.5, HBAR/USDT -0.8, SOL/USDT -1.3]; kotu [XLM/USDT -5.7, DOGE/USDT -5.4, BCH/USDT -5.3, BNB/USDT -5.2, LINK/USDT -3.9]
- FOR_OBO 1h (18 cift): iyi [ADA/USDT 3.2, XLM/USDT 3.0, LTC/USDT 2.7, AVAX/USDT 1.5, XMR/USDT 1.4]; kotu [DOT/USDT -2.0, SOL/USDT -1.5, BCH/USDT -1.3, LINK/USDT -1.2, SUI/USDT -1.0]
- FOR_OBO 4h (11 cift): iyi [LTC/USDT 1.0, ETH/USDT 0.5, LINK/USDT 0.4, XRP/USDT 0.4, XMR/USDT 0.3]; kotu [ADA/USDT -1.0, BCH/USDT -1.0, SOL/USDT -1.0, BTC/USDT -0.6, BNB/USDT -0.4]
- FOR_OBO 1d (2 cift): iyi [TRX/USDT 0.1, LINK/USDT -1.0]; kotu [LINK/USDT -1.0, TRX/USDT 0.1]
- IND_RSI_3070 15m (19 cift): iyi [LTC/USDT 34.7, XMR/USDT 9.7, DOGE/USDT 8.7, HBAR/USDT 1.3, HYPE/USDT -1.1]; kotu [BCH/USDT -41.6, XRP/USDT -37.1, AVAX/USDT -36.7, SOL/USDT -27.5, BNB/USDT -25.7]
- IND_RSI_3070 1h (19 cift): iyi [TRX/USDT 43.5, HBAR/USDT 36.2, HYPE/USDT 1.6, XMR/USDT -5.3, 1000SHIB/USDT -5.6]; kotu [LINK/USDT -107.0, SOL/USDT -89.0, ETH/USDT -81.3, BNB/USDT -57.0, XRP/USDT -56.5]
- IND_RSI_3070 4h (18 cift): iyi [DOT/USDT 47.1, SUI/USDT 42.6, XLM/USDT 26.0, XMR/USDT 21.0, XRP/USDT 11.5]; kotu [HBAR/USDT -41.9, LINK/USDT -40.5, AVAX/USDT -39.4, ADA/USDT -32.6, ETH/USDT -32.6]
- IND_RSI_3070 1d (18 cift): iyi [XLM/USDT 37.1, DOGE/USDT 24.0, LINK/USDT 14.3, BTC/USDT 12.5, LTC/USDT 11.7]; kotu [BNB/USDT -10.4, TRX/USDT -9.7, SOL/USDT -9.7, 1000SHIB/USDT -9.6, ADA/USDT -7.7]
- IND_MA_KESISIM 15m (19 cift): iyi [SOL/USDT 40.5, AVAX/USDT 27.7, HBAR/USDT 13.3, LINK/USDT 11.6, XRP/USDT 5.4]; kotu [XMR/USDT -216.1, BTC/USDT -158.3, XLM/USDT -126.7, TRX/USDT -109.7, ETH/USDT -106.3]
- IND_MA_KESISIM 1h (19 cift): iyi [DOGE/USDT 77.5, ADA/USDT 75.3, BCH/USDT 71.5, XRP/USDT 71.1, LINK/USDT 68.6]; kotu [TRX/USDT -69.1, XMR/USDT -29.1, LTC/USDT -23.7, ETH/USDT -23.2, XLM/USDT -10.6]
- IND_MA_KESISIM 4h (18 cift): iyi [XRP/USDT 35.2, 1000SHIB/USDT 30.3, DOGE/USDT 27.1, ETH/USDT 25.8, BTC/USDT 23.8]; kotu [BCH/USDT -10.1, LTC/USDT -7.0, BNB/USDT -4.5, XMR/USDT -2.4, LINK/USDT -2.2]
- IND_MA_KESISIM 1d (18 cift): iyi [HBAR/USDT 9.4, AVAX/USDT 7.1, DOT/USDT 6.8, DOGE/USDT 6.7, SUI/USDT 5.8]; kotu [XMR/USDT -15.6, BCH/USDT -14.5, XRP/USDT -11.5, TRX/USDT -3.0, XLM/USDT -2.4]
- IND_BOLL_DONUS 15m (19 cift): iyi [HYPE/USDT -55.8, TRX/USDT -133.6, XMR/USDT -254.4, BNB/USDT -266.9, BTC/USDT -329.0]; kotu [SUI/USDT -942.8, LINK/USDT -833.3, AVAX/USDT -825.0, SOL/USDT -821.6, HBAR/USDT -812.1]
- IND_BOLL_DONUS 1h (19 cift): iyi [HYPE/USDT -10.3, TRX/USDT -394.9, SUI/USDT -406.3, XMR/USDT -410.0, BNB/USDT -611.2]; kotu [LINK/USDT -1149.2, AVAX/USDT -962.7, SOL/USDT -959.3, ADA/USDT -895.1, ETH/USDT -888.9]
- IND_BOLL_DONUS 4h (18 cift): iyi [XMR/USDT -39.2, SUI/USDT -114.9, TRX/USDT -124.7, 1000SHIB/USDT -160.1, XRP/USDT -200.9]; kotu [LINK/USDT -382.4, AVAX/USDT -378.0, BTC/USDT -351.6, DOT/USDT -329.8, ADA/USDT -309.5]
- IND_BOLL_DONUS 1d (18 cift): iyi [LTC/USDT 17.1, DOGE/USDT 5.4, LINK/USDT 5.0, XMR/USDT -0.5, XRP/USDT -0.8]; kotu [HBAR/USDT -95.9, AVAX/USDT -63.2, BTC/USDT -53.9, DOT/USDT -52.3, ADA/USDT -51.5]
- IND_FIYAT_MA 15m (19 cift): iyi [HYPE/USDT -40.6, SOL/USDT -537.6, SUI/USDT -616.0, AVAX/USDT -770.5, LINK/USDT -853.9]; kotu [XMR/USDT -2337.9, BTC/USDT -2148.6, BNB/USDT -1761.3, XLM/USDT -1514.5, TRX/USDT -1497.7]
- IND_FIYAT_MA 1h (19 cift): iyi [SOL/USDT 153.1, AVAX/USDT 28.5, HYPE/USDT -1.2, DOT/USDT -11.8, SUI/USDT -35.4]; kotu [XMR/USDT -546.9, XRP/USDT -214.5, BNB/USDT -196.9, XLM/USDT -189.9, BTC/USDT -169.8]
- IND_FIYAT_MA 4h (18 cift): iyi [1000SHIB/USDT 177.5, DOGE/USDT 120.1, LINK/USDT 62.5, BNB/USDT 56.3, AVAX/USDT 55.5]; kotu [XMR/USDT -109.9, TRX/USDT -67.0, LTC/USDT -12.5, SUI/USDT 6.8, HBAR/USDT 8.7]
- IND_FIYAT_MA 1d (18 cift): iyi [HBAR/USDT 42.9, XLM/USDT 40.8, DOGE/USDT 38.7, SOL/USDT 31.4, 1000SHIB/USDT 31.0]; kotu [LTC/USDT -23.8, TRX/USDT -14.8, XMR/USDT -14.4, BCH/USDT 0.5, BNB/USDT 1.9]

## Veri kapsami (cift x zd: mum sayisi, ilk tarih). Kisa gecmisli ya da arsivde olmayan ciftler

- HYPE/USDT 15m: 3030 mum, 2025-05-30 -> 2025-06-30 (kisa gecmis)
- HYPE/USDT 1h: 758 mum, 2025-05-30 -> 2025-06-30 (kisa gecmis)
- HYPE/USDT 4h: 190 mum, 2025-05-30 -> 2025-06-30 (kisa gecmis)
- HYPE/USDT 1d: 32 mum, 2025-05-30 -> 2025-06-30 (kisa gecmis)
- SUI/USDT 15m: 75776 mum, 2023-05-03 -> 2025-06-30 (kisa gecmis)
- SUI/USDT 1h: 18944 mum, 2023-05-03 -> 2025-06-30 (kisa gecmis)
- SUI/USDT 4h: 4736 mum, 2023-05-03 -> 2025-06-30 (kisa gecmis)
- SUI/USDT 1d: 790 mum, 2023-05-03 -> 2025-06-30 (kisa gecmis)
- HBAR/USDT 1h: 37481 mum, 2021-03-17 -> 2025-06-30 (kisa gecmis)
- HBAR/USDT 4h: 9371 mum, 2021-03-17 -> 2025-06-30 (kisa gecmis)
- HBAR/USDT 1d: 1562 mum, 2021-03-17 -> 2025-06-30 (kisa gecmis)
- 1000SHIB/USDT 1h: 36295 mum, 2021-05-10 -> 2025-06-30 (kisa gecmis)
- 1000SHIB/USDT 4h: 9074 mum, 2021-05-10 -> 2025-06-30 (kisa gecmis)
- 1000SHIB/USDT 1d: 1513 mum, 2021-05-10 -> 2025-06-30 (kisa gecmis)
- NVDA/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- NVDA/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- NVDA/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- NVDA/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- MSFT/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- MSFT/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- MSFT/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- MSFT/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AAPL/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AAPL/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AAPL/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AAPL/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- GOOGL/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- GOOGL/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- GOOGL/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- GOOGL/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMZN/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMZN/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMZN/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMZN/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- META/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- META/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- META/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- META/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AVGO/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AVGO/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AVGO/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AVGO/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- TSLA/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- TSLA/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- TSLA/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- TSLA/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BRKB/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BRKB/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BRKB/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BRKB/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- JPM/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- JPM/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- JPM/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- JPM/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- LLY/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- LLY/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- LLY/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- LLY/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- WMT/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- WMT/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- WMT/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- WMT/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- V/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- V/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- V/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- V/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- ORCL/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- ORCL/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- ORCL/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- ORCL/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XOM/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XOM/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XOM/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XOM/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- NFLX/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- NFLX/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- NFLX/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- NFLX/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- PLTR/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- PLTR/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- PLTR/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- PLTR/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COST/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COST/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COST/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COST/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMD/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMD/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMD/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- AMD/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- HD/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- HD/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- HD/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- HD/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAU/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAU/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAU/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAU/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAG/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAG/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAG/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- XAG/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BZ/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BZ/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BZ/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- BZ/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COPPER/USDT 15m: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COPPER/USDT 1h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COPPER/USDT 4h: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
- COPPER/USDT 1d: bu donemde veri YOK (arsivde yok ya da donemden sonra listelendi)
