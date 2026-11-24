# Aile bazli ML filtresi (kagit) - spec

Durum: SILINDI (24.11 kullanici karari; kod kaldirildi, belge tarihce). Eski kod: `src/trader_engine/ogrenme_filtre.py`; gece egitimi: `scripts/ml_retrain_run.py` (artik yalniz M1).

## Sorun
Eski filtre kol (arm_id = `<kurulum>@<tf>`) basina modeldi ve kol kapanmis islem >= 10 olunca devreye giriyordu; az islemli kollar
(M1@15m, M1@1d ...) hic filtre almiyordu.

## Karar
- **Aile = kurulum** (`arm_id`'nin `@` oncesi): M1@15m, M1@1h, M1@4h, M1@1d -> aile `M1`. T1 ve R1 AYRI ailelerdir (farkli `f_*`
  ozellik kumeleri; havuzlanmazlar). Tanimsiz (`?`) ya da bilinmeyen tf'li kol: filtre YOK (giris serbest).
- Ailenin kollar toplami kapanmis islem >= `MIN_ISLEM` (10) olunca havuzlanmis islemlerle TEK model egitilir ve ailenin her koluna uygulanir.
- Zaman dilimi ozellik: `tf_log2_dk` (log2 dakika) + one-hot `tf_15m/tf_1h/tf_4h/tf_1d`. Egitimde adaya, giriste puanlamadan once
  kolun tf'sinden eklenir (ayni islev: `tf_ozellikleri`).
- Esik, yeniden egitim kurali (>= 10 yeni havuz islemi ya da 20 gun), holdout dusurme, fail-open ve "yalniz bir girisi atlatabilir"
  siniri degismedi. Boyut/kaldirac/risk/limit etkilenmez; kol hicbir zaman kapatilmaz.
- Paket kimligi `aile:<kurulum>`, dosya `<defter dizini>/models/ortak_filtre/aile_<kurulum>.json`.

## Geriye uyum
Eski kol-basina paketler kullanilmaz. Gece egitimi bunlari `models/ortak_filtre/eski_kol/` altina tasir (silmez); durum dosyasindaki
eski kol anahtarlari atilir. Gece birimi calisana kadar eski paketler de motor tarafindan zaten yok sayilir (aile kimligi aranir).

## Raporlama
- `egit_hepsi` donusu: `{"aileler": {aile: {n, kollar: {arm: n}, durum, model_hash}}, "eski_tasinan"}`; durum: ok | guncel | az_islem | tek_sinif | hata.
- `var/learner/paper_models.csv`: aile basina bir satir `ortak_filtre_aile_<aile>_<tarih>` (tarif `aile=..;tf_ozellik=log2+onehot`,
  veri_penceresi `n=..;min=10;durum=..;kollar=arm=n,...`, sha256 = model hash). Model yoksa neden `durum`/`n` ile gorunur.
- Motor durumu `ml_filtre`: `aktif_kurulum` = kapsanan kol sayisi (aktif aile x 4 tf), `aktif_aile` = aktif aile listesi.
