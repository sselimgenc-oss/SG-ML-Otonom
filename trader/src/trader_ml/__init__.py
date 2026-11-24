"""M1 gece egitimi ve DL1 egitim yardimcilari (motordan `trader_engine` ve cekirdekten `trader_core` AYRI paket).

`pa_proposer`: M1 onerici egitimi (numpy ridge lojistik; kilit donemi yapisal reddi). `walkforward`: purged walk-forward izgarasi
(DL1 egitimi). Kilitli donem (2026-05 -> 2026-10) kilit kapaliyken hicbir kod yolunda okunmaz (`guards`).
"""
