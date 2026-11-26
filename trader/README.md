# Trader - Binance USDT-M vadeli islem botu

Kendi motorumuzla (`trader_engine`) calisan, once sahte para (paper) sonra canli Binance global
USDT-M vadeli islem botu. Iki ornek calisir:

- **learner (L)**: derslerin uygulandigi bot.
- **twin (T)**: dondurulmus kopya; parametreleri asla degismez.

Tasarim ve kararlar: `../otonom-trading-arastirma/` (`motor-tasarimi.md`, `tasarim-kararlari.md`),
motor sartnameleri: `docs/motor/`.

## Klasor yapisi

```
config/engine.*.json      motor ayarlari (base + bot/mod ustleri), budget.json, panel.json
deploy/                   systemd birimleri ve install.sh (sunucu kurulumu)
shared/                   ortak dosyalar (KILL)
src/trader_core/          cekirdek: risk, rejim, sinyal, defter, saglik, telegram
src/trader_engine/        kendi motoru: feed, saat/bar, paper/canli broker, backtester
research/                 arastirma araclari; research/reference/ degismez referans sonuclari
scripts/                  fetch_binance_vision.py, download_data.sh, smoke_binance.sh, servis girisleri
var/                      calisma verisi (gitignore'da): var/history = gecmis feather verisi
user_data/                bota ozel sqlite dosyalari (butce) (gitignore'da)
tests/                    pytest testleri
```

## Gecmis veri

`api.binance.com` / `fapi.binance.com` erisilemiyorsa gecmis veri `data.binance.vision` arsivinden gelir:

```bash
./scripts/download_data.sh                       # var/history altina (idempotent, sha256 dogrular)
python scripts/fetch_binance_vision.py --help    # --history-dir, --tfs, --end ...
```

- Dosyalar `var/history/<PAIR>_USDT_USDT-<tf>-futures|mark|funding_rate.feather` (yalniz `pyarrow` ile okunur);
  ham zip onbellegi `var/vision_raw/`. Adlandirma bizim sozlesmemizdir.
- Funding verisi ayin sonunda yayinlanir; icinde bulunulan ayin funding'i eksiktir.

## Backtest

```bash
PYTHONPATH=src python -m trader_engine backtest --id <ad> --period IS --tf 1h
PYTHONPATH=src python research/run_bt_engine.py --id 1h_IS_f2_s2 --period IS --fee-mult 2 --slip-bps 2 --tf 1h
```

Kilitli donem (2026-05-01 -> 2026-11-01) reddedilir.

## Sunucu

Binance ABD IP'lerini HTTP 451 ile engeller; sunucu Frankfurt'ta olmali. Kurulum: `deploy/install.sh`
(`docs/sunucu-kurulum.md`). `./scripts/smoke_binance.sh` iki satirda da HTTP 200 beklenir.

## Test

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]' && .venv/bin/pytest
```
